// A small, safe markdown renderer: everything is escaped first, then a known
// set of constructs is turned into HTML. Model output can never inject markup.
"use strict";

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function renderInline(text) {
  // text is already escaped
  const codes = [];
  text = text.replace(/`([^`\n]+)`/g, (_, code) => {
    codes.push(code);
    return `\u0000${codes.length - 1}\u0000`;
  });
  text = text
    .replace(/\[([^\]\n]+)\]\((https?:\/\/[^)\s]+)\)/g,
      (_, label, url) => `<a href="#" data-url="${url}" class="ext">${label}</a>`)
    .replace(/(^|[\s(])(https?:\/\/[^\s<)]+[^\s<).,!?;:'"])/g,
      (_, pre, url) => `${pre}<a href="#" data-url="${url}" class="ext">${url}</a>`)
    .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
    .replace(/__([^_\n]+)__/g, "<strong>$1</strong>")
    .replace(/(^|[^*\w])\*([^*\s][^*\n]*?)\*(?!\w)/g, "$1<em>$2</em>")
    .replace(/~~([^~\n]+)~~/g, "<del>$1</del>");
  return text.replace(/\u0000(\d+)\u0000/g, (_, i) => `<code>${codes[Number(i)]}</code>`);
}

// Math: $$...$$ and \[...\] as a block, $...$ and \(...\) inline. Code spans and
// fences are matched first and left alone. A "$" only opens math when text follows
// it directly and closes it when the next character is not a digit, so "$5 and $10"
// stays text. Placeholders (\u0001n\u0001) survive escaping and are filled in last.
const MATH = /(```[\s\S]*?(?:```|$)|`[^`\n]+`)|\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\]|\\\(([\s\S]+?)\\\)|\$(?=[^\s$])((?:\\.|[^$\\\n])*?[^\s\\$])\$(?!\d)/g;

function takeMath(source) {
  const found = [];
  const text = source.replace(MATH, (all, code, block, bracket, paren, inline) => {
    if (code !== undefined) return all;
    const display = block !== undefined || bracket !== undefined;
    const tex = [block, bracket, paren, inline].find((part) => part !== undefined);
    found.push({ tex: tex.trim(), display, raw: all });
    return `\u0001${found.length - 1}\u0001`;
  });
  return { text, found };
}

function renderMath(item) {
  if (typeof katex === "undefined") return escapeHtml(item.raw);
  try {
    return katex.renderToString(item.tex, { displayMode: item.display, throwOnError: false, output: "htmlAndMathml", trust: false, maxExpand: 500 });
  } catch (_) {
    return escapeHtml(item.raw);
  }
}

function putMath(html, found) {
  return html.replace(/\u0001(\d+)\u0001/g, (_, i) => (found[Number(i)] ? renderMath(found[Number(i)]) : ""));
}

function splitRow(line) {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
}

function renderMarkdown(source) {
  const math = takeMath(String(source || "").replace(/\r\n/g, "\n"));
  return putMath(renderBlocks(math.text), math.found);
}

function renderBlocks(source) {
  const lines = escapeHtml(source).split("\n");
  const out = [];
  let i = 0;
  let paragraph = [];

  const flush = () => {
    if (paragraph.length) {
      out.push(`<p>${paragraph.map(renderInline).join("<br>")}</p>`);
      paragraph = [];
    }
  };

  while (i < lines.length) {
    const line = lines[i];
    const fence = line.match(/^\s*```\s*([\w+-]*)\s*$/);
    if (fence) {
      flush();
      const body = [];
      i++;
      while (i < lines.length && !/^\s*```\s*$/.test(lines[i])) body.push(lines[i++]);
      i++;
      out.push(`<div class="code"><div class="code-head"><span>${fence[1] || ""}</span>` +
        `<button class="copy-code" type="button">${t("msg.copy")}</button></div>` +
        `<pre><code>${body.join("\n")}</code></pre></div>`);
      continue;
    }
    if (/^\s*\|.*\|\s*$/.test(line) && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])) {
      flush();
      const head = splitRow(line);
      i += 2;
      const rows = [];
      while (i < lines.length && /^\s*\|/.test(lines[i])) rows.push(splitRow(lines[i++]));
      out.push(`<div class="table-wrap"><table><thead><tr>${head.map((c) => `<th>${renderInline(c)}</th>`).join("")}</tr></thead>` +
        `<tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${renderInline(c)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`);
      continue;
    }
    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      flush();
      const level = Math.min(6, heading[1].length + 2);
      out.push(`<h${level}>${renderInline(heading[2])}</h${level}>`);
      i++;
      continue;
    }
    if (/^\s*([-*_])\s*\1\s*\1[\s\-*_]*$/.test(line)) {
      flush();
      out.push("<hr>");
      i++;
      continue;
    }
    if (/^\s*&gt;\s?/.test(line)) {
      flush();
      const quote = [];
      while (i < lines.length && /^\s*&gt;\s?/.test(lines[i])) quote.push(lines[i++].replace(/^\s*&gt;\s?/, ""));
      out.push(`<blockquote>${quote.map(renderInline).join("<br>")}</blockquote>`);
      continue;
    }
    const bullet = line.match(/^(\s*)([-*+•]|\d+[.)])\s+(.*)$/);
    if (bullet) {
      flush();
      const ordered = /\d/.test(bullet[2]);
      const items = [];
      while (i < lines.length) {
        const m = lines[i].match(/^(\s*)([-*+•]|\d+[.)])\s+(.*)$/);
        if (m) {
          const nested = m[1].length >= 2;
          items.push(`<li${nested ? ' class="nested"' : ""}>${renderInline(m[3])}</li>`);
          i++;
        } else if (/^\s{2,}\S/.test(lines[i]) && items.length && !/^\s*```/.test(lines[i])) {
          items[items.length - 1] = items[items.length - 1].replace(/<\/li>$/, `<br>${renderInline(lines[i].trim())}</li>`);
          i++;
        } else break;
      }
      const start = ordered ? parseInt(bullet[2], 10) : 1;
      out.push(ordered ? `<ol${start > 1 ? ` start="${start}"` : ""}>${items.join("")}</ol>` : `<ul>${items.join("")}</ul>`);
      continue;
    }
    if (!line.trim()) {
      flush();
      i++;
      continue;
    }
    paragraph.push(line);
    i++;
  }
  flush();
  return out.join("");
}
