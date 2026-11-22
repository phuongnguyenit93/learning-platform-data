# Tổ chức cấu trúc kho mã và ranh giới thư mục nên đưa vào Git

Một repository Git tốt cần có ranh giới rõ ràng: người đọc biết mã nguồn nằm ở đâu, cách build và test thế nào, cấu hình nào được chia sẻ, còn file nào chỉ thuộc máy cá nhân. Cấu trúc thư mục ảnh hưởng trực tiếp tới khả năng tìm kiếm, review, phân quyền, tự động hóa và bảo trì lịch sử. Git có thể theo dõi gần như mọi loại file, nhưng không phải mọi file trong workspace đều nên trở thành một phần của repository.

Mục tiêu khi tổ chức repository là giữ những thứ cần thiết để phát triển, kiểm thử, build và hiểu dự án; loại khỏi lịch sử những dữ liệu có thể tạo lại, phụ thuộc môi trường cá nhân hoặc chứa bí mật.

## 1. Xác định repository root trước khi tạo cấu trúc

Repository root là thư mục mà Git xem là gốc của working tree. Khi chạy `git init` trong một thư mục, Git tạo metadata quản lý repository tại đó. Các file và thư mục con bên dưới root có thể được đưa vào lịch sử, trừ những đường dẫn bị ignore hoặc không được stage.

Ví dụ:

```text
customer-api/
  .git/
  README.md
  src/
  tests/
```

Trong ví dụ, `customer-api/` là repository root. `.git/` chứa object database, refs, index và cấu hình Git; thư mục này không được commit như nội dung dự án. Các thư mục `src/`, `tests/` và file `README.md` là nội dung dự án có thể được theo dõi.

Kiểm tra root của repository hiện tại:

```bash
git rev-parse --show-toplevel
git rev-parse --show-prefix
```

Lệnh đầu trả về đường dẫn tuyệt đối tới root. Lệnh thứ hai cho biết đường dẫn tương đối từ root tới thư mục hiện tại; nếu đang ở root, kết quả rỗng.

Hãy khởi tạo Git ở đúng cấp dự án. Nếu chạy `git init` quá cao, chẳng hạn ở thư mục chứa nhiều dự án không liên quan, Git có thể gom tất cả vào một lịch sử không mong muốn. Nếu chạy quá sâu, các file cần chia sẻ ở thư mục cha sẽ nằm ngoài repository.

## 2. Nguyên tắc chọn nội dung đưa vào repository

Trước khi tạo thư mục, hãy phân loại nội dung theo mục đích:

| Nhóm nội dung | Thường nên đưa vào Git? | Ví dụ |
|---|---|---|
| Mã nguồn và tài nguyên cần để chạy ứng dụng | Có | `src/`, template, static assets |
| Test và dữ liệu test nhỏ, không nhạy cảm | Có | `tests/`, fixtures, mock data |
| Tài liệu và hướng dẫn phát triển | Có | `README.md`, `docs/`, ADR |
| Cấu hình build và dependency manifest | Có | `pom.xml`, `build.gradle`, `package.json`, lockfile |
| Cấu hình mẫu không chứa bí mật | Có | `.env.example`, `application-local.example.yml` |
| Script build, test, migration và phát triển | Có | `scripts/`, `Makefile`, CI workflow |
| File build sinh ra và cache | Thường không | `target/`, `build/`, `.gradle/`, `node_modules/` |
| Log, file tạm và trạng thái IDE | Thường không | `*.log`, `.idea/workspace.xml`, `.vscode/settings.local.json` |
| Credential và dữ liệu cá nhân | Không | `.env`, private key, token, file credential |
| Artifact lớn có thể tải hoặc tái tạo | Tùy chính sách | archive, binary release, model, video |

Một câu hỏi hữu ích cho từng file là: *Một thành viên mới clone repository có cần file này để hiểu, build, test hoặc vận hành dự án theo cách được hỗ trợ không?* Nếu không, file có thể là đầu ra, cache, dữ liệu riêng hoặc dependency được quản lý ở nơi khác.

## 3. Một cấu trúc cơ bản cho dự án đơn

Với một ứng dụng hoặc thư viện độc lập, cấu trúc có thể bắt đầu đơn giản:

```text
customer-api/
  .gitignore
  .gitattributes
  README.md
  LICENSE
  pom.xml
  src/
    main/
      java/
      resources/
    test/
      java/
      resources/
  docs/
  scripts/
```

Ý nghĩa các thành phần:

- `src/main/`: mã nguồn và tài nguyên runtime của ứng dụng.
- `src/test/`: test tự động, fixture và dữ liệu test được phép chia sẻ.
- `docs/`: tài liệu kiến trúc, hướng dẫn, quy trình và quyết định kỹ thuật.
- `scripts/`: script lặp lại được cho build, kiểm tra, phát triển hoặc bảo trì.
- `pom.xml`: khai báo build và dependency; file lock hoặc version catalog cũng nên được quản lý khi công cụ hỗ trợ.
- `.gitignore`: loại file local, cache và đầu ra không cần theo dõi.
- `.gitattributes`: quy tắc line ending, diff, merge hoặc LFS cho các loại file.

Không cần tạo sẵn mọi thư mục nếu dự án chưa dùng tới. Cấu trúc nên phản ánh thành phần thật, không tạo nhiều tầng rỗng chỉ để trông có vẻ chuẩn hóa.

## 4. Ví dụ cấu trúc cho dự án Java

Một dự án Java dùng Maven hoặc Gradle có thể tổ chức như sau:

```text
inventory-service/
  .gitignore
  .gitattributes
  README.md
  pom.xml
  mvnw
  mvnw.cmd
  .mvn/
    wrapper/
  src/
    main/
      java/com/example/inventory/
      resources/
    test/
      java/com/example/inventory/
      resources/
  docs/
    architecture.md
    local-development.md
  scripts/
    check.sh
```

Các file Maven Wrapper như `mvnw`, `mvnw.cmd` và thư mục `.mvn/wrapper/` thường nên được commit vì chúng giúp thành viên dùng phiên bản Maven nhất quán mà không cần cài Maven toàn cục. Với Gradle Wrapper, các file `gradlew`, `gradlew.bat`, `gradle/wrapper/` cũng thường được commit. Kiểm tra chính sách checksum và phiên bản wrapper của tổ chức.

Đầu ra như `target/` của Maven hoặc `build/` của Gradle thường được tạo lại từ source và build configuration, nên đưa vào `.gitignore`. Không bỏ qua toàn bộ `src/main/resources/` chỉ vì có một số file cấu hình local; hãy tách cấu hình mẫu được chia sẻ khỏi file chứa bí mật.

## 5. Ví dụ cấu trúc cho monorepo

Monorepo chứa nhiều ứng dụng hoặc package có liên quan trong một repository. Cấu trúc cần giúp người dùng nhận biết ranh giới từng thành phần và cách build/test độc lập:

```text
platform/
  README.md
  .gitignore
  .gitattributes
  docs/
  services/
    customer-api/
      README.md
      pom.xml
      src/
      tests/
    billing-worker/
      package.json
      src/
      tests/
  libraries/
    auth-client/
      pom.xml
      src/
  tools/
    release/
  scripts/
```

README ở root giải thích toàn bộ workspace, các thành phần, dependency giữa chúng và lệnh thường dùng. README trong từng service có thể mô tả cách chạy riêng. Cấu hình CI nên xác định thành phần nào cần build/test khi các đường dẫn tương ứng thay đổi.

Một monorepo không có nghĩa mọi thành phần phải dùng chung ngôn ngữ, công cụ build hoặc nhịp release. Hãy giữ ranh giới thư mục rõ, khai báo dependency minh bạch và tránh để một service đọc trực tiếp file nội bộ của service khác nếu giao diện chia sẻ nên là package hoặc API.

## 6. Khi nào nên tách nhiều repository?

Không phải dự án nào cũng nên nằm trong một monorepo. Nhiều repository có thể phù hợp khi các thành phần:

- Có vòng đời phát hành và quyền truy cập khác nhau.
- Thuộc các nhóm sở hữu độc lập và ít thay đổi cùng nhau.
- Có chính sách bảo mật hoặc giấy phép khác nhau.
- Có dependency và quy trình CI riêng, không cần commit đồng bộ.
- Được tái sử dụng như sản phẩm độc lập ở nhiều dự án.

Ngược lại, monorepo thường hữu ích khi nhiều thành phần cần thay đổi đồng bộ, chia sẻ công cụ, có dependency nội bộ chặt chẽ hoặc cần một commit nguyên tử cập nhật nhiều package.

| Tiêu chí | Monorepo | Nhiều repository |
|---|---|---|
| Commit thay đổi nhiều thành phần cùng lúc | Thuận tiện, một commit có thể cập nhật nhiều thư mục | Cần nhiều commit/PR hoặc quy trình phối hợp |
| Quyền truy cập theo thành phần | Có thể phức tạp hơn | Dễ tách quyền ở cấp repository |
| CI | Cần tối ưu theo path và dependency | Mỗi repository có pipeline riêng |
| Chia sẻ công cụ và quy ước | Dễ tập trung | Cần đồng bộ giữa các repository |
| Lịch sử và clone | Có thể lớn khi nhiều thành phần tích lũy | Mỗi repository có lịch sử và dung lượng riêng |

Hãy chọn ranh giới theo cách nhóm phát triển, phát hành và sở hữu phần mềm. Không nên tách repository chỉ để có thêm thư mục, cũng không nên gom các hệ thống không liên quan vào cùng một lịch sử chỉ vì chúng nằm cạnh nhau trên ổ đĩa.

## 7. Giữ cấu hình chia sẻ và cấu hình local riêng biệt

Repository nên chứa cấu hình cần thiết để hiểu cách chạy ứng dụng, nhưng không chứa credential hoặc thiết lập chỉ đúng trên một máy.

Ví dụ cấu trúc cấu hình:

```text
config/
  application.yml
  application-example.yml
  logging.yml
```

File mẫu có thể chứa giá trị giả hoặc placeholder:

```yaml
database:
  url: ${DATABASE_URL:jdbc:postgresql://localhost:5432/inventory}
  username: ${DATABASE_USERNAME:app}
  password: ${DATABASE_PASSWORD:}
```

Thông tin nhạy cảm được truyền qua biến môi trường hoặc secret manager. File local như `.env`, `application-local.yml` có credential thật nên bị ignore và không được commit.

Đặt một file mẫu để người mới biết cần khai báo gì:

```text
.env.example
```

File này nên chứa tên biến và giá trị minh họa, không chứa token hoặc mật khẩu dùng thật. README mô tả cách sao chép file mẫu thành `.env` và lấy credential từ nguồn được tổ chức phê duyệt.

## 8. Không đưa build output, cache và dependency đã cài vào Git

Các thư mục được tạo lại từ mã nguồn và build configuration thường không cần commit:

| Công cụ | Đường dẫn thường bỏ qua |
|---|---|
| Maven | `target/` |
| Gradle | `.gradle/`, `build/` |
| Node.js | `node_modules/`, một số thư mục cache |
| Python | `.venv/`, `__pycache__/`, `.pytest_cache/` |
| Java IDE | `.idea/workspace.xml`, `.classpath`, `.project` tùy chính sách dự án |
| Hệ điều hành | `.DS_Store`, `Thumbs.db`, `Desktop.ini` |

Không phải mọi file trong nhóm này đều luôn bị bỏ qua. Ví dụ, một dự án Eclipse có thể chủ động commit `.project` và `.classpath`; một ứng dụng web có thể commit `dist/` nếu đó là artifact được triển khai theo quy trình cụ thể. Hãy dựa trên cách dự án build và release thực tế.

Dependency manifest và lockfile thường nên được commit để tái lập môi trường. Thư mục dependency đã cài thường không nên commit vì có thể được cài lại từ manifest và lockfile.

## 9. Thiết kế `.gitignore` theo ranh giới thư mục

`.gitignore` quy định những đường dẫn chưa được theo dõi mà Git nên bỏ qua. Có thể đặt file ở root để áp dụng cho toàn dự án hoặc đặt thêm file trong thư mục con để nhóm quy tắc theo thành phần.

Ví dụ `.gitignore` ở root cho một dự án Java:

```gitignore
# Maven / Gradle output
target/
build/
.gradle/

# Local environment and secrets
.env
.env.*
!.env.example
application-local.yml
*.pem
*.key

# IDE and OS local files
.idea/workspace.xml
.vscode/settings.local.json
.DS_Store
Thumbs.db

# Logs and temporary files
*.log
*.tmp
```

Các pattern cần được review. Ví dụ `*.key` có thể bỏ qua cả file key giả dùng trong test; nếu dự án có fixture cần commit, hãy thiết kế ngoại lệ cụ thể và bảo đảm fixture không chứa khóa thật.

Một `.gitignore` trong `services/customer-api/` có thể chứa quy tắc chỉ liên quan tới service đó. Pattern tương đối với vị trí file `.gitignore`; điều này giúp nhóm quản lý quy tắc gần nơi phát sinh file.

### 9.1. Kiểm tra lý do một file bị ignore

Dùng:

```bash
git check-ignore -v path/to/file
```

Git hiển thị file `.gitignore`, số dòng và pattern đã khớp. Nếu muốn kiểm tra cả file đã tracked, thêm `--no-index`:

```bash
git check-ignore -v --no-index path/to/file
```

File đã được theo dõi không tự ngừng được track chỉ vì bạn thêm nó vào `.gitignore`. Nếu thật sự muốn ngừng theo dõi file nhưng giữ file trên máy, dùng `git rm --cached path/to/file` rồi commit thay đổi. Chỉ làm điều đó sau khi xác nhận file không còn là nội dung cần chia sẻ.

### 9.2. Không dùng ignore để che lỗi tổ chức

Nếu `.gitignore` ngày càng dài với nhiều ngoại lệ cho file cá nhân, có thể repository root đang quá rộng hoặc dự án chưa phân biệt cấu hình chia sẻ với local state. Hãy xem lại ranh giới thư mục, cách build và nơi lưu dữ liệu riêng thay vì thêm pattern rộng để làm sạch `git status`.

## 10. Bí mật và dữ liệu nhạy cảm không thuộc repository

Không commit:

- `.env` chứa token hoặc mật khẩu thật.
- Private key, certificate key, SSH key và signing key.
- File credential cloud, database dump có dữ liệu thật hoặc export người dùng.
- Log chứa access token, session ID, thông tin cá nhân hoặc header xác thực.
- File cấu hình có URL nội bộ kèm username/password.

Git lưu lịch sử lâu dài. Xóa file ở commit mới không xóa dữ liệu nhạy cảm khỏi các commit cũ. Nếu secret đã được commit hoặc push, hãy thu hồi/rotate credential trước, đánh giá phạm vi truy cập và xử lý lịch sử theo quy trình phối hợp.

Để giảm nguy cơ:

1. Dùng secret manager hoặc biến môi trường cho credential.
2. Commit file cấu hình mẫu với placeholder.
3. Thêm file local vào `.gitignore` trước khi tạo commit đầu tiên.
4. Dùng secret scanning trong pre-commit hoặc CI.
5. Review `git diff --cached` trước khi commit.

## 11. File lớn, dữ liệu và artifact

Không phải mọi dữ liệu lớn đều nên đặt trong repository. Hãy phân biệt:

- **Fixture nhỏ, ổn định, không nhạy cảm:** có thể commit để test tái lập.
- **Dataset lớn hoặc thay đổi thường xuyên:** cân nhắc object storage, data registry hoặc hệ thống versioning dữ liệu.
- **File nhị phân cần đồng bộ phiên bản cùng source:** cân nhắc Git LFS nếu hosting hỗ trợ và nhóm chấp nhận quota/băng thông.
- **Artifact build hoặc release:** thường nên lưu trong artifact registry hoặc release storage thay vì commit vào source repository.
- **Dữ liệu production:** không đưa vào Git; quản lý qua hệ thống dữ liệu và backup phù hợp.

Nếu sử dụng LFS, khai báo pattern trong `.gitattributes` và hướng dẫn cách cài Git LFS cho thành viên. Nếu dùng object storage, repository có thể lưu manifest, checksum, phiên bản hoặc script tải dữ liệu, còn nội dung thực ở hệ thống lưu trữ riêng.

## 12. Cẩn thận với repository lồng nhau

Một thư mục con có thể chứa repository Git riêng, ví dụ:

```text
workspace/
  .git/
  app/
  vendor-library/
    .git/
```

Nếu bạn chạy `git add vendor-library`, Git có thể cảnh báo rằng bạn đang thêm một embedded Git repository. Entry được stage có thể trở thành gitlink (mode `160000`) trỏ tới commit của repository con, thay vì đưa toàn bộ file con vào repository cha như file thông thường.

Người clone repository cha sẽ không tự có nội dung repository con nếu bạn chỉ vô tình stage gitlink. Nếu muốn dependency độc lập và có URL/commit rõ ràng, hãy khai báo submodule qua `git submodule add`. Nếu muốn nội dung nằm trong cùng lịch sử repository cha, hãy bảo đảm thư mục con không còn metadata `.git` riêng trước khi add như thư mục thông thường; chỉ xóa metadata sau khi xác nhận lịch sử con đã được lưu hoặc không còn cần.

Kiểm tra các gitlink trong index hoặc tree:

```bash
git ls-files --stage
git ls-tree HEAD
```

Entry có mode `160000` là dấu hiệu đường dẫn đang được lưu như gitlink. Đừng xóa `.git` bên trong một thư mục con một cách vội vàng: nó có thể là repository độc lập chứa lịch sử cần bảo toàn.

## 13. Symbolic link và file đặc biệt

Git có thể theo dõi symbolic link trên hệ thống hỗ trợ. Tree lưu mode `120000` và blob chứa đường dẫn đích của link, không lưu nội dung file mà link trỏ tới.

Điều này có nghĩa một symlink trỏ tới file ngoài repository không đưa nội dung file ngoài đó vào Git. Người clone có thể nhận symlink nhưng đích không tồn tại trên máy họ. Hãy tránh dùng symlink để tham chiếu file cá nhân hoặc thư mục nằm ngoài repository nếu dự án yêu cầu chạy được trên nhiều môi trường.

Git chủ yếu theo dõi file thông thường, executable bit trên nền tảng hỗ trợ, symlink và gitlink. Các thuộc tính filesystem khác như owner, ACL hoặc timestamp không được lưu như một bản sao đầy đủ của filesystem. Nếu dự án cần quyền hoặc metadata đặc biệt, hãy dùng script provisioning hoặc công cụ triển khai để thiết lập.

## 14. Đặt tên file và cấu trúc có tính di động

Repository thường được clone trên Windows, macOS và Linux. Vì vậy, nên tránh tên file chỉ khác nhau ở chữ hoa/chữ thường, tên dành riêng của Windows, dấu phân cách không nhất quán hoặc đường dẫn quá dài.

Ví dụ hai file `Config.yml` và `config.yml` có thể cùng tồn tại trên filesystem phân biệt hoa thường nhưng gây xung đột khi checkout trên một số cấu hình Windows/macOS. Hãy chọn một quy ước tên nhất quán, thường là chữ thường và dấu gạch ngang hoặc gạch dưới.

Không dùng tên file chứa ký tự điều khiển hoặc các ký tự khó biểu diễn trong shell. Với script xử lý danh sách đường dẫn, ưu tiên tùy chọn NUL-delimited như `git ls-files -z` thay vì tách output theo khoảng trắng.

## 15. README và tài liệu giúp cấu trúc có ý nghĩa

Một cấu trúc thư mục tốt vẫn cần được giải thích. README ở root nên trả lời:

- Dự án giải quyết vấn đề gì và các thành phần chính nằm ở đâu?
- Yêu cầu môi trường và công cụ nào cần cài?
- Cách build, chạy test và chạy ứng dụng?
- Cấu hình local lấy từ đâu và biến môi trường nào cần khai báo?
- Thư mục nào chứa mã nguồn, tài liệu, script và dữ liệu test?
- Quy trình đóng góp, review và phát hành được thực hiện thế nào?

Tài liệu chuyên sâu có thể đặt trong `docs/`, còn hướng dẫn riêng của service đặt ngay trong thư mục service. Tránh sao chép cùng một hướng dẫn ở nhiều nơi vì nội dung dễ lệch nhau; README root nên liên kết tới tài liệu chi tiết.

## 16. Kiểm tra những gì sẽ được đưa vào commit

Trước khi commit cấu trúc ban đầu, xem trạng thái:

```bash
git status --short --untracked-files=all
```

Stage các đường dẫn có chủ đích thay vì mặc định dùng `git add .` khi workspace có nhiều file không rõ nguồn:

```bash
git add README.md .gitignore .gitattributes pom.xml src/ tests/ docs/
```

Sau đó review nội dung staged:

```bash
git diff --cached --stat
git diff --cached --name-status
git diff --cached
```

Kiểm tra file bị ignore:

```bash
git check-ignore -v .env target/example.class
```

Kiểm tra file nào thực sự đang được theo dõi:

```bash
git ls-files
```

Nếu có nhiều file, dùng `git ls-files` kết hợp filter hoặc `git ls-files -z` trong script để xử lý tên file an toàn. Kiểm tra các file lớn, binary, file cấu hình và đường dẫn nhạy cảm trước khi tạo commit.

## 17. Quy trình thiết kế repository từ đầu

Một quy trình thực tế có thể đi theo các bước:

1. **Xác định phạm vi:** một ứng dụng, một thư viện, một monorepo hay nhiều repository độc lập.
2. **Chọn root:** đặt repository ở đúng thư mục chứa nội dung và lịch sử cần chia sẻ.
3. **Phác thảo thư mục:** phân tách source, test, docs, config mẫu, scripts và thành phần độc lập.
4. **Phân loại file:** đánh dấu nội dung cần commit, file có thể tạo lại, dữ liệu local, bí mật và artifact.
5. **Tạo `.gitignore` và `.gitattributes`:** đặt quy tắc ngay từ đầu, trước khi stage file phát sinh.
6. **Viết README:** mô tả cấu trúc, cách cài đặt, build/test và cấu hình local.
7. **Kiểm tra nested repository:** xác định thư mục nào là submodule hoặc thư mục thường.
8. **Review staging area:** dùng `git status`, `git diff --cached` và `git ls-files` để xác nhận phạm vi.
9. **Commit cấu trúc ban đầu:** tạo commit dễ hiểu, ví dụ `chore: initialize repository structure`.
10. **Kiểm tra trên clone sạch:** xác nhận thành viên mới có thể clone, cài dependency, build và test theo README.

## 18. Những lỗi thường gặp

- **Khởi tạo Git ở thư mục cha quá rộng:** vô tình đưa nhiều dự án không liên quan vào cùng lịch sử.
- **Khởi tạo Git quá sâu:** bỏ sót tài liệu hoặc cấu hình chung nằm ở thư mục cha.
- **Commit build output và cache:** làm repository lớn, diff nhiễu và dễ xung đột.
- **Ignore nhầm source hoặc lockfile:** khiến clone mới không thể build hoặc tái lập dependency.
- **Commit file `.env` hoặc credential:** bí mật có thể tồn tại trong lịch sử ngay cả sau khi xóa file.
- **Thêm repository con như thư mục thường mà không nhận ra gitlink:** người clone không nhận được nội dung như mong đợi.
- **Tạo quá nhiều tầng thư mục:** làm khó tìm file và tăng chi phí di chuyển, đổi tên.
- **Dùng symlink tới file ngoài repository:** môi trường khác không có đích liên kết.
- **Chỉ kiểm tra working tree mà không xem index:** commit có thể chứa phiên bản khác với file đang mở trong editor.
- **Không thử clone sạch:** cấu hình cá nhân hoặc dependency cache trên máy người tạo che giấu file còn thiếu.

## 19. Ví dụ `.gitignore` tổng hợp cho dự án Java

Đây là điểm khởi đầu có thể điều chỉnh theo build tool và IDE thực tế:

```gitignore
# Maven
target/

# Gradle
.gradle/
build/

# Local environment
.env
.env.*
!.env.example
application-local.yml

# IDE local state
.idea/workspace.xml
.vscode/settings.local.json
*.iml

# Logs and temporary files
*.log
*.tmp

# OS files
.DS_Store
Thumbs.db
Desktop.ini
```

Nếu dự án dùng IntelliJ, Eclipse hoặc VS Code, hãy thống nhất file cấu hình nào cần chia sẻ và file nào thuộc workspace cá nhân. Một số cấu hình launch hoặc formatter có thể nên commit để mọi người dùng cùng quy tắc; không ignore toàn bộ thư mục IDE một cách máy móc nếu dự án cần chia sẻ cấu hình.

## 20. Ghi nhớ

Repository root xác định ranh giới lịch sử Git. Hãy tổ chức bên trong root theo thành phần và mục đích: source, test, docs, cấu hình mẫu, scripts và metadata build cần được chia sẻ; build output, cache, dependency đã cài, trạng thái IDE, credential và dữ liệu local thường cần nằm ngoài lịch sử. Dùng `.gitignore` để quản lý file chưa tracked, kiểm tra nested repository để tránh gitlink ngoài ý muốn, và review staging area trước commit. Một repository được tổ chức tốt phải cho phép thành viên clone sạch, hiểu cấu trúc và build/test theo hướng dẫn mà không cần các file bí mật hoặc trạng thái riêng của máy người tạo.
