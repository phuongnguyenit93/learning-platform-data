# Khởi tạo lịch sử cho dự án có sẵn mà không đưa nhầm tệp sinh ra

Khi một dự án đã có mã nguồn, tài liệu và các thư mục build nhưng chưa được quản lý bằng Git, bước khởi tạo repository đầu tiên cần được thực hiện có chủ đích. Nếu chạy `git add .` hoặc `git add -A` ngay khi chưa kiểm tra, bạn có thể đưa vào commit đầu tiên các tệp sinh ra, cache, log, cấu hình cá nhân hoặc thông tin bí mật.

Quy trình an toàn là xác định đúng thư mục gốc và kiểm tra repository hiện có, tạo `.gitignore` trước khi stage, rà soát những gì Git dự định thêm, stage có chọn lọc rồi kiểm tra index trước commit. Bài học thuộc chương **Khởi tạo kho mã** của module `SOURCE_CONTROL_GIT`. Module hướng dẫn working tree, staging area, commit, lịch sử, branch, merge, rebase, remote và tag; commit đầu tiên là nền móng để các hoạt động cộng tác sau này có lịch sử rõ ràng.

## 1. Kiểm tra dự án trước khi chạy git init

Trước khi khởi tạo, xác định chính xác thư mục bạn muốn trở thành repository root. Đừng mặc định thư mục đang mở trong terminal là gốc dự án.

Xem vị trí hiện tại:

~~~bash
pwd
~~~

Trên Windows PowerShell:

~~~powershell
Get-Location
Get-ChildItem -Force
~~~

Kiểm tra xem thư mục đã thuộc một repository khác hay chưa:

~~~bash
git rev-parse --show-toplevel
~~~

- Nếu Git trả về một đường dẫn, thư mục hiện tại đang nằm bên trong một repository. Hãy kiểm tra đường dẫn đó và `git status` trước khi làm gì thêm.
- Nếu Git báo không phải repository, kiểm tra thư mục cha và các thư mục con có repository lồng nhau hay không.
- Nếu đã có `.git` là thư mục hoặc tệp, đây có thể là repository thường, linked worktree hoặc submodule. Không xóa hoặc ghi đè `.git` để “khởi tạo lại”.

Trong PowerShell, có thể kiểm tra sự hiện diện của `.git` ở thư mục hiện tại:

~~~powershell
Get-Item -Force -LiteralPath .git -ErrorAction SilentlyContinue
~~~

`.git` có thể là thư mục trong repository thường hoặc tệp trỏ đến Git directory của linked worktree/submodule. Hãy dùng `git rev-parse --show-toplevel` và `git rev-parse --git-dir` khi Git đã nhận diện được repository.

### Tránh tạo repository lồng nhau ngoài ý muốn

Ví dụ cấu trúc:

~~~text
workspace/
  .git/
  project-a/
    src/
  project-b/
    src/
~~~

Nếu `workspace` đã là repository, chạy `git init` trong `project-a` có thể tạo repository lồng nhau. Khi stage từ repository cha, Git có thể cảnh báo về embedded repository. Điều này thường không phải mục tiêu khi bạn chỉ muốn đưa dự án con vào lịch sử của repository cha.

Nếu dự án con thực sự cần lịch sử và quyền quản lý riêng, hãy quyết định rõ dùng submodule hoặc giữ nó là repository độc lập. Nếu không, hãy khởi tạo Git ở đúng root dự án và tránh tạo thêm `.git` trong thư mục con.

### Kiểm tra các thư mục con có Git metadata

Một dự án được sao chép từ nhiều nguồn có thể chứa repository lồng nhau hoặc thư mục submodule. Hãy kiểm tra các thư mục quan trọng như `vendor/`, `tools/`, `examples/` hoặc các component được ghép vào dự án. Nếu `git add` báo embedded repository, dừng lại và xác định mục tiêu trước khi stage tiếp.

## 2. Chuẩn bị .gitignore trước lần stage đầu tiên

`.gitignore` khai báo các đường dẫn chưa được theo dõi mà Git không nên đề xuất hoặc thêm bằng các thao tác add thông thường. Tạo tệp này trước khi stage giúp tránh đưa các tệp sinh ra và tệp máy cá nhân vào commit đầu tiên.

Ví dụ cấu trúc dự án:

~~~text
app/
  src/
  tests/
  target/
  build/
  dist/
  node_modules/
  .idea/
  .env
  .env.example
  README.md
  pom.xml
  package.json
  package-lock.json
~~~

Một `.gitignore` khởi đầu có thể như sau:

~~~gitignore
# Build outputs
/target/
/build/
/dist/
/out/
/coverage/

# Dependencies installed locally
/node_modules/

# Logs and temporary files
*.log
*.tmp
*.swp

# Local environment and secrets
.env
.env.*
!.env.example
/secrets/

# Local IDE and operating system files
.idea/
.DS_Store
Thumbs.db
~~~

Đây chỉ là mẫu chung. Hãy điều chỉnh theo stack và quy ước của dự án. Ví dụ, `dist/` có thể là đầu ra build không cần commit trong một dự án, nhưng lại là artifact được publish hoặc lưu trong repository của dự án khác. Không thêm pattern chỉ vì tên thư mục nghe có vẻ là tệp sinh ra.

### Những thứ thường nên giữ trong Git

Không phải tệp nào được công cụ tạo ra cũng nên ignore. Các tệp sau thường cần được commit để người khác tái tạo môi trường giống nhau:

- `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`.
- `pom.xml`, `build.gradle`, `settings.gradle` và Gradle wrapper.
- `requirements.txt`, `poetry.lock`, `Pipfile.lock`.
- Migration database, cấu hình build dùng chung và script CI.
- Tài liệu, mã nguồn, test và fixture được dự án chủ động duy trì.

Phân biệt **dependency manifest/lockfile** với thư mục dependency đã cài. Ví dụ, thường commit `package-lock.json` nhưng ignore `node_modules/`.

### Không commit secret và cấu hình cá nhân

Những tệp cần kiểm tra kỹ trước khi thêm:

- `.env`, tệp chứa API token hoặc mật khẩu.
- Private key, credential, file cấu hình cloud cá nhân.
- Log có request header, cookie hoặc dữ liệu người dùng.
- File database cục bộ và bản dump có dữ liệu nhạy cảm.
- IDE workspace chứa đường dẫn hoặc cấu hình cá nhân.

Nếu dự án cần mẫu biến môi trường, tạo `.env.example` với tên biến và giá trị giả hoặc rỗng; không sao chép token thật vào mẫu.

`.gitignore` không phải hệ thống quản lý secret. Nếu một secret đã được commit hoặc push, xóa tệp khỏi branch hiện tại không làm secret cũ biến mất khỏi lịch sử. Hãy thu hồi/rotate credential ngay và xử lý lịch sử theo quy trình ứng phó của nhóm.

## 3. Hiểu pattern trong .gitignore

Một số quy tắc thường dùng:

| Pattern | Ý nghĩa |
| --- | --- |
| `*.log` | Bỏ qua tệp có đuôi `.log` ở các cấp phù hợp |
| `/build/` | Chỉ bỏ qua thư mục `build` ở cùng cấp với `.gitignore` này |
| `build/` | Bỏ qua thư mục tên `build` ở các cấp bên dưới vị trí đặt `.gitignore` |
| `**/cache/` | Bỏ qua thư mục `cache` ở nhiều cấp |
| `!important.log` | Bỏ qua ngoại lệ trước đó để theo dõi lại tệp này nếu các thư mục cha vẫn được duyệt |
| `*.tmp` | Bỏ qua các tệp tạm có phần mở rộng `.tmp` |

Dấu `/` ở đầu pattern giới hạn đường dẫn tương đối với vị trí `.gitignore`. Dấu `/` cuối pattern cho biết chỉ khớp thư mục. Dấu `!` dùng để loại một đường dẫn khỏi quy tắc ignore trước đó.

Ví dụ:

~~~gitignore
# Bỏ qua mọi file log
*.log

# Nhưng vẫn theo dõi log mẫu
!important.log

# Bỏ qua build ở root repository
/build/
~~~

Nếu một thư mục cha đã bị ignore hoàn toàn, chỉ thêm `!` cho tệp con có thể chưa đủ vì Git không đi xuống thư mục đó để tìm tệp. Cần mở lại thư mục cha rồi mới mở lại đường dẫn con theo đúng thứ tự pattern.

### .gitignore nhiều cấp và ignore toàn máy

Git có thể đọc `.gitignore` ở root và các thư mục con. Quy tắc ở vị trí gần tệp hơn có thể bổ sung hoặc ghi đè quy tắc từ thư mục cha theo quy tắc pattern.

Bạn cũng có thể cấu hình ignore cá nhân trên máy bằng `core.excludesFile`:

~~~bash
git config --global core.excludesFile ~/.config/git/ignore
~~~

Tệp ignore toàn cục phù hợp cho file hệ điều hành hoặc IDE cá nhân mà nhóm không cần áp dụng. Những quy tắc ảnh hưởng đến toàn bộ thành viên dự án nên nằm trong `.gitignore` được commit cùng repository.

## 4. Khởi tạo repository và chọn tên branch mặc định

Sau khi xác nhận đúng root và chuẩn bị ignore, khởi tạo repository:

~~~bash
git init -b main
~~~

`-b main` đặt tên branch mặc định là `main` ngay khi khởi tạo, nếu phiên bản Git hỗ trợ tùy chọn này.

Kiểm tra:

~~~bash
git rev-parse --show-toplevel
git branch --show-current
git status --short
~~~

Repository mới chưa có commit nên branch `main` có thể là unborn branch: tên branch đã được xác định nhưng chưa trỏ đến commit nào.

Nếu phiên bản Git cũ không hỗ trợ `git init -b`, có thể dùng:

~~~bash
git init
git symbolic-ref HEAD refs/heads/main
~~~

Không chạy `git init` lặp lại chỉ để đổi tên branch nếu repository đã có lịch sử. Với repository đã tồn tại, dùng lệnh đổi branch phù hợp sau khi kiểm tra trạng thái.

## 5. Kiểm tra Git sẽ bỏ qua và sẽ thêm những gì

Sau khi tạo `.gitignore`, xem trạng thái gồm cả các đường dẫn bị ignore:

~~~bash
git status --short --ignored
~~~

Các ký hiệu trong output giúp nhận biết:

- `??`: tệp/thư mục chưa được theo dõi.
- `!!`: đường dẫn bị ignore.
- Các ký hiệu ở hai cột đầu của tracked path biểu thị thay đổi trong index và working tree.

Để biết quy tắc nào đã ignore một đường dẫn:

~~~bash
git check-ignore -v -- target/
git check-ignore -v -- .env
~~~

Lệnh `git check-ignore -v` cho biết file ignore và dòng pattern khớp. Nếu đường dẫn không bị ignore, lệnh có thể không trả kết quả và exit code khác 0; điều đó không nhất thiết là lỗi repository.

Chạy các lệnh preview từ repository root để danh sách bao phủ toàn dự án. Để xem trước những đường dẫn một lần `git add` sẽ stage mà không thực hiện staging:

~~~bash
git add --dry-run --all
~~~

Hoặc dạng ngắn:

~~~bash
git add -n -A
~~~

Đọc danh sách này trước khi stage. Nếu thấy `target/`, `node_modules/`, `build/`, `.env`, log hoặc tệp nhị phân không mong muốn, quay lại chỉnh `.gitignore` rồi chạy dry-run lại.

### Kiểm tra tệp lớn và dữ liệu nhạy cảm

Không chỉ kiểm tra tên thư mục. Một tệp dump database, archive hoặc video có thể nằm ngay ở root. Hãy xem kích thước và nội dung các tệp chưa được theo dõi; mở các file cấu hình có khả năng chứa credential.

Có thể liệt kê tệp chưa theo dõi bằng:

~~~bash
git ls-files --others --exclude-standard
~~~

Lệnh này không liệt kê các tệp bị ignore. Để xem tệp ignored, dùng `git status --short --ignored` hoặc `git ls-files --others --ignored --exclude-standard`.

## 6. Stage có chọn lọc thay vì thêm tất cả ngay lập tức

Khi đã rà soát, cách rõ ràng nhất là stage theo đường dẫn:

~~~bash
git add README.md .gitignore src/ tests/ pom.xml
~~~

Thay các đường dẫn ví dụ bằng những thành phần thực tế cần quản lý. Stage theo đường dẫn giúp bạn kiểm soát phạm vi commit đầu tiên.

Nếu muốn thêm toàn bộ nội dung hợp lệ sau khi đã kiểm tra dry-run và ignore rules:

~~~bash
git add --all
~~~

Khi chạy từ repository root, `git add --all` cập nhật index với thay đổi ở mọi đường dẫn trong repository, bao gồm thêm, sửa và xóa; các tệp bị ignore sẽ không được thêm theo cách thông thường. Nếu chạy từ thư mục con, phạm vi có thể chỉ giới hạn ở thư mục đó và các thư mục bên dưới.

Không nên dùng `git add *` như một thói quen. Wildcard có thể được shell mở rộng trước khi Git nhận lệnh và có thể bỏ sót tệp ẩn như `.gitignore`, `.editorconfig` hoặc các file cấu hình root.

### Stage một phần tệp

Nếu chỉ muốn commit một số đoạn thay đổi trong một tệp:

~~~bash
git add -p
~~~

Git hiển thị từng hunk để bạn chọn stage. Điều này hữu ích khi dự án đã có sửa đổi từ trước và bạn muốn commit phần khởi tạo hoặc cấu hình riêng biệt.

## 7. Review index trước commit đầu tiên

Sau khi stage, index là nội dung Git sẽ đưa vào commit. Working tree có thể tiếp tục có thay đổi chưa stage, nên đừng chỉ nhìn tệp trên đĩa để đoán commit sẽ chứa gì.

Kiểm tra danh sách tệp đã stage:

~~~bash
git diff --cached --name-only
~~~

Xem thống kê:

~~~bash
git diff --cached --stat
~~~

Xem nội dung chính xác sẽ commit:

~~~bash
git diff --cached
~~~

Kiểm tra whitespace error:

~~~bash
git diff --cached --check
~~~

Cuối cùng xem trạng thái:

~~~bash
git status
~~~

Hãy kiểm tra kỹ:

1. Có thư mục build, cache hoặc dependency đã cài không?
2. Có file `.env`, token, private key hoặc credential không?
3. Có database dump, log, file upload của người dùng hoặc dữ liệu cá nhân không?
4. Có repository con bị stage nhầm không?
5. Có lockfile, manifest hoặc script cần giữ nhưng lại bị ignore không?
6. Nội dung staged có đúng là phiên bản muốn lưu trong commit đầu tiên không?

### Nếu lỡ stage tệp không mong muốn

Để bỏ một tệp khỏi index nhưng giữ nguyên tệp trong working tree, trong repository đã có commit:

~~~bash
git restore --staged -- .env
~~~

Hoặc dùng lệnh tương thích với các phiên bản Git cũ:

~~~bash
git reset HEAD -- .env
~~~

Trong repository mới chưa có commit đầu tiên, `HEAD` chưa tồn tại nên cách dùng `git reset HEAD` có thể không phù hợp. Có thể bỏ tệp khỏi index bằng:

~~~bash
git rm --cached -- .env
~~~

Lệnh `git rm --cached` bỏ tệp khỏi index và giữ file trên đĩa. Chỉ dùng với đúng đường dẫn cần loại khỏi lần commit này.

Sau đó thêm pattern phù hợp vào `.gitignore` và kiểm tra lại:

~~~bash
git status --short --ignored
git diff --cached --name-only
~~~

Nếu secret đã được commit hoặc push, cần rotate/revoke secret ngay. Việc xóa khỏi commit mới không thu hồi credential và không xóa bản sao trong lịch sử, clone hoặc cache của người khác.

## 8. Tạo commit đầu tiên

Khi index đã đúng, kiểm tra danh tính commit:

~~~bash
git var GIT_AUTHOR_IDENT
git var GIT_COMMITTER_IDENT
~~~

Nếu cần, cấu hình tên/email phù hợp với dự án:

~~~bash
git config user.name "Nguyen An"
git config user.email "an@example.com"
~~~

Tạo commit:

~~~bash
git commit -m "Initial commit"
~~~

Commit đầu tiên tạo mốc lịch sử cho repository. Sau đó kiểm tra:

~~~bash
git status
git log --oneline --decorate -1
git show --stat --oneline HEAD
~~~

Nếu `git status` báo working tree clean, toàn bộ thay đổi hiện tại đã được commit hoặc ignore. Nếu còn tệp chưa theo dõi hoặc thay đổi chưa stage, kiểm tra xem chúng có cần được thêm vào commit tiếp theo hay không.

## 9. Kết nối remote sau khi khởi tạo local

Sau khi commit đầu tiên đã được tạo, bạn có thể kết nối remote:

~~~bash
git remote add origin https://example.com/team/app.git
git remote -v
~~~

Nếu remote đã chứa README hoặc commit khởi tạo riêng, lịch sử local và remote có thể không có chung ancestor. Đừng vội dùng force push. Hãy fetch và xem lịch sử hai phía trước, sau đó tích hợp theo đúng mục tiêu:

~~~bash
git fetch origin
git log --oneline --graph --decorate --all
~~~

Nếu remote thực sự rỗng, có thể push branch đầu tiên:

~~~bash
git push -u origin main
~~~

`-u` thiết lập upstream để các lần push/pull sau có thể dùng tên branch mặc định. Nếu remote đã có lịch sử, hãy chọn merge/rebase hoặc quy trình import phù hợp trước khi push.

## 10. Quy trình hoàn chỉnh cho một dự án mới đưa vào Git

~~~bash
# 1. Vào đúng thư mục gốc dự án
cd /path/to/project

# 2. Xác nhận không nằm trong repository khác
git rev-parse --show-toplevel

# 3. Tạo .gitignore trước khi stage
# (soạn nội dung phù hợp với dự án)

# 4. Khởi tạo branch mặc định
git init -b main

# 5. Xem các tệp sẽ được theo dõi và bị ignore
git status --short --ignored
git add --dry-run --all

# 6. Stage theo lựa chọn đã review
git add README.md .gitignore src/ tests/

# 7. Review index
git diff --cached --name-only
git diff --cached --stat
git diff --cached --check
git diff --cached

# 8. Tạo commit đầu tiên
git commit -m "Initial commit"

# 9. Xác minh lịch sử và trạng thái
git status
git log --oneline --decorate -1
~~~

Các đường dẫn trong ví dụ chỉ là minh họa. Điều chỉnh danh sách stage theo cấu trúc dự án và kết quả kiểm tra thực tế.

## 11. Những sai lầm thường gặp

- **Chạy `git add -A` trước khi tạo `.gitignore`:** dễ đưa build output, dependency, cache và file local vào index.
- **Nghĩ thêm pattern vào `.gitignore` sẽ bỏ theo dõi tệp đã tracked:** ignore không tác động đến tệp đã có trong index/commit.
- **Dùng `git add *`:** có thể bỏ sót file ẩn và phụ thuộc shell expansion.
- **Ignore mọi file có tên “lock”:** lockfile của dependency manager thường cần commit để tái lập môi trường.
- **Ignore toàn bộ `dist/` hoặc `build/` theo mẫu máy móc:** một số dự án chủ động lưu artifact hoặc tài liệu build.
- **Không kiểm tra repository lồng nhau:** có thể tạo embedded repository ngoài ý muốn hoặc stage sai ranh giới dự án.
- **Chỉ xem `git status` mà không xem staged diff:** nội dung index có thể khác working tree.
- **Commit file `.env` rồi chỉ xóa ở commit sau:** secret vẫn còn trong lịch sử và cần rotate.
- **Force-push ngay sau khi tạo local commit:** remote có thể có lịch sử cần giữ; fetch và xem graph trước khi tích hợp.
- **Xem commit đầu tiên là backup đầy đủ dự án:** Git không tự lưu ignored files, tệp chưa stage, secret ngoài repository hoặc dữ liệu dịch vụ bên ngoài.

## 12. Sơ đồ quyết định trước commit đầu tiên

~~~mermaid
flowchart TD
    A[Dự án đã có mã nguồn] --> B{Đã nằm trong Git repository?}
    B -- Có --> C[Kiểm tra root, status và lịch sử hiện có]
    B -- Không --> D[Kiểm tra repository lồng và thư mục con]
    D --> E[Tạo .gitignore phù hợp]
    E --> F[git init -b main]
    C --> G[Không khởi tạo lại ngoài ý muốn]
    F --> H[git status --short --ignored]
    H --> I[git add --dry-run --all]
    I --> J{Có file sinh ra hoặc secret?}
    J -- Có --> K[Điều chỉnh ignore và kiểm tra lại]
    K --> H
    J -- Không --> L[Stage có chọn lọc]
    L --> M[Review git diff --cached]
    M --> N{Index đúng?}
    N -- Không --> O[Unstage và stage lại]
    O --> M
    N -- Có --> P[Commit đầu tiên]
    P --> Q[Kiểm tra status và log]
~~~

Trước khi commit, hãy tự xác nhận:

1. Tôi đã xác định đúng repository root và không tạo nested repository ngoài ý muốn chưa?
2. `.gitignore` đã có trước lần stage đầu tiên chưa?
3. Các thư mục build, cache, dependency và file cá nhân đã được phân loại đúng chưa?
4. Tôi đã kiểm tra secret, credential và dữ liệu nhạy cảm chưa?
5. Các manifest, lockfile và cấu hình dùng chung có được giữ lại không?
6. Tôi đã xem trước danh sách file và nội dung staged chưa?
7. Commit đầu tiên có đúng phạm vi, đúng danh tính và thông điệp rõ ràng không?

Khởi tạo lịch sử cho dự án có sẵn không chỉ là chạy `git init` rồi thêm mọi tệp. Hãy xác định ranh giới repository, chuẩn bị ignore rules, kiểm tra trước những gì Git sẽ stage và review index như một bản nội dung độc lập. Khi commit đầu tiên chỉ chứa mã nguồn và cấu hình cần thiết, lịch sử về sau sẽ dễ review, build lại và cộng tác hơn.

## Tài liệu tham khảo

- [Git documentation: git-init](https://git-scm.com/docs/git-init) — khởi tạo repository và chọn branch ban đầu.
- [Git documentation: gitignore](https://git-scm.com/docs/gitignore) — pattern, negation và thứ tự áp dụng ignore rules.
- [Git documentation: git-add](https://git-scm.com/docs/git-add) — stage đường dẫn, dry-run và cập nhật index.
- [Git documentation: git-check-ignore](https://git-scm.com/docs/git-check-ignore) — xác định quy tắc ignore khớp với đường dẫn.
- [Git documentation: git-diff](https://git-scm.com/docs/git-diff) — xem nội dung staged và unstaged.
- [Pro Git: Recording Changes to the Repository](https://git-scm.com/book/en/v2/Git-Basics-Recording-Changes-to-the-Repository) — staging area và commit đầu tiên.
