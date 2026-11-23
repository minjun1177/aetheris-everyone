## What's new in 1.1.0

**Security**
- **API keys now live in the system password store** (Windows Credential Manager, macOS Keychain, Secret Service on Linux). Keys saved by 1.0.0 are moved there automatically on first start.
- **Running programs is now off by default.** Turn it on in **Settings → General**; every command is then shown and asked first, even in "Do everything".
- **"Do everything" still asks before changing files outside the work folder.**
- The AI is told to treat text from files and web pages as data, never as instructions, and commands that reach the app's own settings or keys are refused.
- The Ollama installer is checked against the release's published SHA-256 before it runs.
- Web page reading connects only to the public address it checked, and compressed pages can no longer expand without limit.

**New**
- **SearXNG**: use your own search engine (Settings → General → Web search engine).
- **Ollama on another computer**: set its address in Settings → AI connection or in the setup guide.
- **Math formulas** in replies are typeset (LaTeX via KaTeX).
- Remove a saved cloud API key from Settings.

**Fixed**
- Long files written by the AI no longer lose their first lines when a reply hits the length limit.
- Web pages with non-English addresses (e.g. Korean Wikipedia) now open.
- Appending to a Word/Excel file no longer silently replaces the whole document.
- Undo no longer deletes files you added to a folder the AI copied.
- Changing one chat's folder no longer changes the default for new chats.
- Pictures attached to a saved chat are no longer deleted after 30 days.

## 1.1.0 새 기능과 수정

**보안**
- **API 키를 운영체제 암호 저장소에 보관합니다** (Windows 자격 증명 관리자, macOS 키체인, Linux Secret Service). 1.0.0에서 저장한 키는 처음 실행할 때 자동으로 옮겨집니다.
- **프로그램 실행이 기본으로 꺼집니다.** **설정 → 일반**에서 켤 수 있고, 켜면 "모두 자동"에서도 모든 명령을 보여 주고 먼저 물어봅니다.
- **"모두 자동"에서도 작업 폴더 밖의 파일을 바꿀 때는 물어봅니다.**
- 파일과 웹 페이지 속 글은 명령이 아니라 자료로 다루도록 AI에게 알려 두고, 앱의 설정·키에 닿는 명령은 거절합니다.
- Ollama 설치 프로그램은 실행 전에 릴리스에 공개된 SHA-256과 대조합니다.
- 웹 페이지 읽기는 확인한 공용 주소로만 연결하고, 압축된 페이지가 끝없이 커지지 않게 막습니다.

**새 기능**
- **SearXNG**: 내 검색 엔진을 쓸 수 있어요 (설정 → 일반 → 웹 검색 엔진).
- **다른 컴퓨터의 Ollama**: 설정 → AI 연결 또는 설정 도우미에서 주소를 적으면 됩니다.
- 답변 속 **수식**을 보기 좋게 표시합니다 (KaTeX로 LaTeX 렌더링).
- 설정에서 저장된 클라우드 API 키를 지울 수 있어요.

**고친 점**
- AI가 긴 파일을 쓸 때 답이 길이 한도에서 잘려도 앞부분이 사라지지 않습니다.
- 한글 주소의 웹 페이지(예: 한국어 위키백과)도 열립니다.
- Word/Excel 파일에 이어 쓰기를 하면 문서 전체가 조용히 바뀌던 문제를 고쳤습니다.
- AI가 복사한 폴더에 내가 넣은 파일은 되돌리기를 해도 지워지지 않습니다.
- 대화 하나의 폴더를 바꿔도 새 대화의 기본 폴더는 바뀌지 않습니다.
- 저장된 대화에 첨부한 사진이 30일 뒤에 지워지지 않습니다.

## 다운로드 / Download

| 내 컴퓨터 | 받을 파일 |
| :--- | :--- |
| **Windows 10 / 11** | `AetherisEveryone-Windows.exe` |
| **Mac (M1 / M2 / M3 / M4)** | `AetherisEveryone-macOS-AppleSilicon.dmg` |
| **Mac (Intel)** | `AetherisEveryone-macOS-Intel.dmg` |
| **Linux** | `AetherisEveryone-Linux-x86_64.tar.gz` |

받은 파일을 **더블클릭**하면 끝입니다. 처음 실행하면 설정 도우미가 AI 준비를 화면에서 안내해 줍니다. 터미널은 필요 없습니다.

- **Windows**: "Windows의 PC 보호" 창이 뜨면 **추가 정보 → 실행**을 누르세요. (서명 인증서가 없는 무료 앱이라 뜨는 안내입니다.)
- **Mac**: dmg를 열고 앱을 **응용 프로그램** 폴더로 끌어다 놓으세요. 처음 열 때 "확인되지 않은 개발자" 창이 뜨면 **시스템 설정 → 개인정보 보호 및 보안 → 그래도 열기**를 누르세요.
- **Linux**: 압축을 풀고 `AetherisEveryone`을 더블클릭하세요. 설정 → 정보에서 바로가기를 만들 수 있어요.

Double-click the downloaded file; the first-run guide sets up the AI on screen. No terminal needed.
