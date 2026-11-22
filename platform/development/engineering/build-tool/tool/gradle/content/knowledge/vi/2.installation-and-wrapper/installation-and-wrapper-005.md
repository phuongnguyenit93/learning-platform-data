# Khởi tạo và sử dụng Gradle Wrapper nhất quán trên Windows, Linux và macOS

## 1. Gradle Wrapper giải quyết vấn đề gì?

**Gradle Wrapper** là bộ tệp nằm ngay trong repository để chạy **phiên bản Gradle do dự án chỉ định**. Khi chạy `gradlew` hoặc `gradlew.bat`, Wrapper đọc cấu hình, tải bản phân phối Gradle nếu máy chưa có, sau đó chuyển các tham số như `build`, `test` hoặc `tasks` cho Gradle thực thi.

Sự khác biệt quan trọng:

- `gradle build` gọi Gradle đã cài trên máy và phụ thuộc phiên bản của từng người.
- `./gradlew build` (Linux/macOS) hoặc `.\gradlew.bat build` (Windows PowerShell) gọi Gradle do chính repository cấu hình. Khi đã có Wrapper, thành viên mới và CI **không phải tự cài Gradle toàn cục**.
- Wrapper thống nhất **phiên bản Gradle**, nhưng không tự cố định phiên bản JDK, plugin, dependency hay kết quả tác vụ phụ thuộc hệ điều hành. Muốn build tái lập tốt, cần quản lý các yếu tố đó riêng.

**Mục tiêu thực hành:** một repository chứa cùng bốn tệp Wrapper; trên Windows, Linux và macOS, mỗi môi trường gọi đúng script của mình và nhận cùng phiên bản Gradle.

## 2. Chuẩn bị

1. Mở terminal tại **thư mục gốc của Gradle build** (nơi thường có `settings.gradle` hoặc `settings.gradle.kts`, `build.gradle` hoặc `build.gradle.kts`).
2. Có **JDK tương thích** với phiên bản Gradle dự định dùng. Kiểm tra `java -version` và, nếu biên dịch Java, `javac -version`. Trên máy có nhiều JDK, kiểm tra cả `JAVA_HOME` và công cụ IDE/CI đang chọn JDK nào. JVM dùng để **chạy Gradle** có thể khác toolchain dùng để **biên dịch**.
3. Có mạng để tải bản phân phối Gradle ở lần chạy đầu (hoặc đã cache bản đó). Được phép đọc/ghi vào Gradle User Home, mặc định là thư mục `.gradle` của người dùng.
4. **Chỉ khi tạo Wrapper lần đầu cho dự án chưa có Wrapper**, cần có một bản Gradle cài sẵn hoặc dùng `gradle init` để khởi tạo dự án; từ những lần tiếp theo dùng script đã commit.

Các lệnh dưới đây dùng **Gradle 8.14.3 làm ví dụ cố định**, phù hợp với JDK 17/21. Đây không phải yêu cầu nâng mọi dự án lên phiên bản này: hãy chọn phiên bản đã được xác nhận tương thích với JDK, plugin và môi trường của dự án. Trước khi đổi major version, đọc hướng dẫn nâng cấp của Gradle và plugin liên quan.

## 3. Bốn tệp Wrapper phải có trong Git

```text
project-root/
├── settings.gradle                 # hoặc settings.gradle.kts
├── build.gradle                    # hoặc build.gradle.kts
├── gradlew                         # script sh cho Linux/macOS
├── gradlew.bat                     # batch script cho Windows
└── gradle/
    └── wrapper/
        ├── gradle-wrapper.jar      # mã khởi động Wrapper
        └── gradle-wrapper.properties  # URL, phiên bản, cấu hình tải
```

- `gradlew` là script chạy qua shell trên Linux/macOS (và thường trong WSL/Git Bash).
- `gradlew.bat` là script dùng trong Command Prompt và PowerShell trên Windows.
- `gradle-wrapper.jar` chứa mã tải/chạy bản phân phối; **phải commit cùng repository** dù là tệp nhị phân.
- `gradle-wrapper.properties` chứa `distributionUrl`, nơi xác định bản phân phối Gradle dùng cho tất cả máy. Đừng xem `gradle-wrapper.jar` là JAR ứng dụng của bạn.

Đây là **một Wrapper ở gốc một Gradle build**, kể cả build nhiều subproject. Không cần tạo Wrapper riêng cho từng subproject; nếu đang ở thư mục con, dùng đường dẫn tương đối về script tại gốc.

## 4. Khởi tạo Wrapper lần đầu

### Trường hợp A — đã có Gradle project nhưng chưa có Wrapper

Cài một bản Gradle trên máy khởi tạo, mở terminal tại project root và chạy:

```bash
gradle --version
gradle :wrapper --gradle-version=8.14.3 --distribution-type=bin
```

Trong Windows PowerShell hoặc Command Prompt, hai lệnh `gradle` ở trên vẫn giống nhau nếu Gradle đã nằm trên `PATH`. Dấu `:` chỉ rõ task `wrapper` tại root project. `bin` chứa Gradle runtime và đủ cho hầu hết trường hợp; `all` còn có tài liệu, source và ví dụ, phù hợp khi cần hỗ trợ IDE/offline documentation.

Sau khi sinh tệp, **chuyển ngay sang gọi Wrapper**, thay vì tiếp tục dùng lệnh `gradle` toàn cục:

```bash
# Linux/macOS
./gradlew --version
./gradlew help
```

```powershell
# Windows PowerShell
.\gradlew.bat --version
.\gradlew.bat help
```

```bat
REM Windows Command Prompt
gradlew.bat --version
gradlew.bat help
```

Lệnh `--version` phải hiển thị **Gradle 8.14.3** trong ví dụ này. `help` xác nhận Gradle đọc được cấu hình dự án. Lần đầu có thể thấy quá trình download và unzip; các lần sau tái dùng bản đã cache.

### Trường hợp B — chưa có Gradle project

Trong một thư mục mới, có thể chạy `gradle init` với Gradle được cài tạm để tạo cấu trúc dự án; công cụ khởi tạo của Gradle tự sinh các tệp Wrapper. Ví dụ:

```bash
gradle init --type basic --dsl groovy
gradle :wrapper --gradle-version=8.14.3 --distribution-type=bin
```

`gradle init` có thể hỏi thêm tuỳ chọn theo phiên bản; trả lời theo nhu cầu dự án. Nếu đã tạo bằng IDE hoặc mẫu dự án có sẵn Wrapper thì **không cần tạo lại**. Một project mới cũng có thể dùng Kotlin DSL (`*.gradle.kts`); cách gọi Wrapper **không đổi**.

### Tình huống không có quyền cài Gradle

Nếu clone một dự án **đã commit đủ bốn tệp Wrapper**, chỉ cần JDK và mạng/cache: chạy script của repository trực tiếp. Không cần tải riêng `gradle-wrapper.jar` từ nguồn không xác minh, cũng không nên sao chép Wrapper ngẫu nhiên từ repository khác.

## 5. Gọi cùng task trên từng hệ điều hành

| Môi trường | Kiểm tra phiên bản | Chạy build | Chạy test |
| --- | --- | --- | --- |
| Linux (bash, zsh, sh) | `./gradlew --version` | `./gradlew build` | `./gradlew test` |
| macOS (zsh, bash) | `./gradlew --version` | `./gradlew build` | `./gradlew test` |
| Windows PowerShell | `.\gradlew.bat --version` | `.\gradlew.bat build` | `.\gradlew.bat test` |
| Windows Command Prompt | `gradlew.bat --version` | `gradlew.bat build` | `gradlew.bat test` |

Task `build` và `test` tồn tại khi plugin của dự án cung cấp chúng, ví dụ `java`/`java-library`; một project `base` trống có thể chưa có task `test`. Dùng `help` hoặc `tasks --all` để xem task thực tế.

**PowerShell:** tiền tố `.\` chỉ định thực thi file trong thư mục hiện tại; gõ mỗi `gradlew` có thể bị báo “not recognized”. **Linux/macOS:** tiền tố `./` có nghĩa thực thi file nằm tại thư mục hiện tại. **WSL:** nếu đang ở shell Linux của WSL thì dùng `./gradlew` và Java/JDK của WSL, không dùng nhầm batch script Windows.

Ví dụ chạy nhiều task hoặc yêu cầu log dễ đọc:

```bash
./gradlew clean build --console=plain
./gradlew tasks --all
```

```powershell
.\gradlew.bat clean build --console=plain
.\gradlew.bat tasks --all
```

Gradle có thể thực thi task theo dependency và trạng thái up-to-date; “cùng task + cùng Gradle” không đồng nghĩa log, thời gian chạy hay output nhị phân tuyệt đối giống nhau trên mọi OS.

## 6. Thực hành kiểm tra chéo với một task nhỏ

Để chứng minh **cùng một nhiệm vụ** chạy được trên ba OS, có thể tạo Gradle project Groovy DSL tối giản (dành cho project demo mới, không chép đè build script của dự án thật).

`settings.gradle`:

```groovy
rootProject.name = 'wrapper-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'base'
}

tasks.register('helloWrapper') {
    doLast {
        println 'Gradle Wrapper OK'
    }
}
```

Sinh Wrapper như phần 4. Chạy bằng terminal tương ứng:

```bash
# Linux/macOS
./gradlew -q helloWrapper
```

```powershell
# Windows PowerShell
.\gradlew.bat -q helloWrapper
```

```bat
REM Windows Command Prompt
gradlew.bat -q helloWrapper
```

Kết quả stdout của **task demo này** ở cả ba môi trường:

```text
Gradle Wrapper OK
```

Tùy môi trường, lần chạy đầu có thể xuất hiện thông tin tải Gradle trên luồng khác. Tuỳ chọn `-q` giảm log Gradle để dễ đối chiếu stdout. Vì ví dụ dùng plugin `base`, nó minh họa riêng Wrapper và task, không cần thêm source Java. Với một dự án Java thật, thay `helloWrapper` bằng `test` hoặc `build` và kiểm tra báo cáo/test kết quả thực tế.

## 7. Wrapper làm gì khi chạy?

```text
Lệnh của người dùng
  ├── Linux/macOS: ./gradlew
  └── Windows:    gradlew.bat
          |
          v
   gradle-wrapper.jar
          |
          v
   Đọc gradle-wrapper.properties
          |
          v
   Tìm Gradle distribution trong cache
          |
     Có --+-- Chưa có -> Tải ZIP -> Kiểm tra SHA-256 nếu cấu hình
          |                         -> Giải nén/cache
          v
   Khởi chạy đúng Gradle distribution
          |
          v
   Thực thi task: help / build / test / ...
```

Mặc định Gradle lưu bản phân phối tại `GRADLE_USER_HOME/wrapper/dists` (thường là `~/.gradle/wrapper/dists` trên Linux/macOS, thư mục `.gradle\wrapper\dists` trong profile người dùng trên Windows). Có thể đặt `GRADLE_USER_HOME` khác cho môi trường đặc biệt; đây là cache theo máy và không commit vào repository.

Ví dụ nội dung điển hình của `gradle/wrapper/gradle-wrapper.properties`:

```properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\://services.gradle.org/distributions/gradle-8.14.3-bin.zip
networkTimeout=10000
validateDistributionUrl=true
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
```

Trong ví dụ, `distributionUrl` cố định Gradle **8.14.3**. Các key khác điều khiển nơi lưu, timeout và xác thực URL; bộ tệp thực tế có thể có thêm cấu hình. Không thay `distributionUrl` thành `latest` nếu mục tiêu là phiên bản tái lập, và không chỉnh sửa script/JAR bằng tay để “nâng cấp”.

## 8. Commit Wrapper để đồng đội và CI cùng dùng

Commit **cả bốn tệp**, không bỏ `gradle-wrapper.jar` khỏi Git chỉ vì nó có đuôi `.jar`. Nếu `.gitignore` dùng quy tắc bỏ qua mọi JAR, phải cho phép đúng `gradle/wrapper/gradle-wrapper.jar`.

```bash
git add gradlew gradlew.bat gradle/wrapper/gradle-wrapper.jar gradle/wrapper/gradle-wrapper.properties
git status --short
git diff --cached -- gradlew gradlew.bat gradle/wrapper/gradle-wrapper.properties
```

Trên Linux/macOS, script Unix phải có bit execute:

```bash
chmod +x gradlew
git add gradlew
git ls-files --stage gradlew
```

Với Git, mode mong muốn của `gradlew` là `100755`, không phải `100644`. Nếu đang dùng Windows và cần gán bit execute trong index Git, dùng:

```powershell
git add --chmod=+x gradlew
git ls-files --stage gradlew
```

Để hạn chế lỗi xuống dòng khi phát triển đa nền tảng, repository có thể cấu hình `.gitattributes`:

```gitattributes
gradlew text eol=lf
gradlew.bat text eol=crlf
gradle/wrapper/gradle-wrapper.jar binary
```

`gradlew` cần dòng kết thúc **LF**, vì CRLF có thể tạo lỗi `/bin/sh^M` trên Linux. `gradlew.bat` chạy trên Windows. Khi bổ sung `.gitattributes` cho repo có sẵn, kiểm tra và chuẩn hóa thay đổi một cách có chủ đích; không đổi hàng loạt file không liên quan.

Không commit thư mục `.gradle/`, `build/` hoặc Gradle distribution ZIP vào Git chỉ để làm Wrapper chạy được. Các máy tự tải/cache bản phân phối được chỉ định.

## 9. Nâng cấp Gradle Wrapper có kiểm soát

Khi dự án đã có Wrapper và quyết định đổi sang phiên bản mới, dùng **task của Wrapper hiện tại**. Ví dụ, chuyển sang Gradle 8.14.3 từ một phiên bản cũ tương thích:

```bash
# Linux/macOS
./gradlew :wrapper --gradle-version=8.14.3 --distribution-type=bin
./gradlew :wrapper
./gradlew --version
./gradlew build
```

```powershell
# Windows PowerShell
.\gradlew.bat :wrapper --gradle-version=8.14.3 --distribution-type=bin
.\gradlew.bat :wrapper
.\gradlew.bat --version
.\gradlew.bat build
```

**Vì sao chạy `:wrapper` hai lần?** Lần một thường đổi `gradle-wrapper.properties`. Lần hai chạy qua bản phân phối vừa được chỉ định để làm mới cả script và JAR; Gradle khuyến nghị cách này khi muốn đồng bộ đủ bộ Wrapper. Nếu dự án đã bật checksum `distributionSha256Sum` và đổi phiên bản/ZIP, phải cung cấp checksum chính xác của ZIP mới cho task Wrapper; nếu không, task có thể từ chối cập nhật.

Sau nâng cấp, review diff của **bốn tệp**, kiểm tra tương thích JDK/plugin, chạy task và test trên những OS dự án hỗ trợ, sau đó commit. Không lẫn nâng cấp Gradle với nâng cấp đồng thời tất cả dependency nếu không có nhu cầu.

## 10. Bảo mật và tính nhất quán khi tải Gradle

- **Đối chiếu SHA-256 của distribution ZIP:** lấy checksum chính thức từ trang release của Gradle hoặc file `.sha256` cùng phiên bản và đúng loại ZIP. Với ZIP minh họa, nguồn chính thức là `https://services.gradle.org/distributions/gradle-8.14.3-bin.zip.sha256`. Thêm giá trị 64 ký tự hex nhận được vào key `distributionSha256Sum` của `gradle-wrapper.properties`, hoặc truyền tùy chọn `--gradle-distribution-sha256-sum` khi chạy task Wrapper. **Không bịa checksum** và không dùng checksum của `all.zip` cho `bin.zip`.
- **Giới hạn của phép kiểm tra:** Wrapper kiểm tra SHA-256 của bản phân phối **khi bản phân phối đó chưa được tải xuống**. Một ZIP đã nằm trong cache không được tự xác minh lại mỗi lần chạy.
- **Xác minh Wrapper JAR:** bản thân `gradle-wrapper.jar` là mã có thể thực thi, nên cần review file thay đổi và xác minh checksum JAR theo tài liệu chính thức khi nâng cấp hoặc nhận pull request. Action `gradle/actions/setup-gradle@v4` trên GitHub Actions tích hợp kiểm tra Wrapper JAR.
- **Giữ nguồn tải tin cậy:** dùng `services.gradle.org` hoặc mirror doanh nghiệp được kiểm soát; tránh link/ZIP trôi nổi và không commit mật khẩu proxy/token trong file Wrapper.
- **Đồng bộ môi trường:** pin JDK/toolchain và plugin/dependency quan trọng; với phụ thuộc ngoài, cân nhắc dependency locking/verification. Wrapper chỉ đảm bảo bản Gradle đang gọi, không đảm bảo mọi nguồn đầu vào của build giống nhau.

Nếu công ty dùng proxy hoặc mirror nội bộ, cấu hình theo hướng dẫn Gradle và chính sách tổ chức; phân phối qua mạng có thể thất bại do TLS, DNS, proxy hoặc certificate, dù script Wrapper hoàn toàn đúng.

## 11. Kiểm chứng trên CI Windows + Linux + macOS

GitHub Actions có thể chạy cùng repository trên ba runner để phát hiện sớm khác biệt của shell, quyền file và JDK. Ví dụ file `.github/workflows/gradle-wrapper.yml`:

```yaml
name: Verify Gradle Wrapper

on:
  push:
  pull_request:

jobs:
  verify:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
      - uses: gradle/actions/setup-gradle@v4
      - name: Verify on Linux and macOS
        if: runner.os != 'Windows'
        run: ./gradlew --version && ./gradlew help
      - name: Verify on Windows
        if: runner.os == 'Windows'
        shell: pwsh
        run: .\gradlew.bat --version; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; .\gradlew.bat help; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

Đây là smoke test chung cho mọi Gradle build. Với dự án Java có task `test`/`build`, thay hoặc bổ sung task đó để kiểm chứng đầy đủ. Các runner sử dụng **script đã commit trong Git**, không gọi Gradle cài sẵn. Action setup Gradle hỗ trợ cache và xác minh Wrapper JAR; việc chọn JDK 17 trong ví dụ cần đổi cho phù hợp với dự án.

## 12. Lỗi phổ biến và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `./gradlew: Permission denied` (Linux/macOS) | File `gradlew` thiếu execute bit | `chmod +x gradlew`, commit mode `100755`; kiểm tra bằng `git ls-files --stage gradlew` |
| `/bin/sh^M: bad interpreter` hoặc lỗi ký tự `\r` | Script Unix bị đổi sang CRLF | Đưa `gradlew` về LF, đặt `.gitattributes` và commit lại |
| PowerShell báo `gradlew` không được nhận diện | Thiếu tiền tố thư mục hoặc dùng sai script | Chạy `.\gradlew.bat help` tại root |
| `java` không tồn tại hoặc “JAVA_HOME is set to an invalid directory” | Chưa cài JDK, `PATH`/`JAVA_HOME` sai | Cài/chọn JDK tương thích; kiểm tra `java -version` và biến môi trường |
| “Unsupported class file major version”, lỗi phiên bản JVM | Gradle/plugin/JDK chưa tương thích | Đối chiếu compatibility matrix, JVM chạy Gradle và toolchain; thay phiên bản có hỗ trợ |
| `Could not find or load main class org.gradle.wrapper.GradleWrapperMain` | Thiếu/hỏng `gradle-wrapper.jar` hoặc checkout không đủ tệp | Khôi phục JAR đã xác minh từ Git/nguồn phát hành chính thức; commit đủ bốn tệp |
| Download timeout, `PKIX path building failed`, lỗi proxy | Mạng/TLS/certificate/proxy | Kiểm tra URL, mạng, CA/proxy đáng tin; cấu hình Gradle theo môi trường; không tắt kiểm tra TLS tùy tiện |
| Checksum mismatch | ZIP không khớp SHA đã khai báo hoặc đã dùng nhầm loại/phát hành | Đối chiếu đúng `distributionUrl` và SHA chính thức; không xóa kiểm tra để lách lỗi |
| `Task 'test' not found` | Build không áp dụng plugin cung cấp task `test` | Kiểm tra `./gradlew tasks --all` hoặc `gradlew.bat tasks --all` |
| Offline build thất bại ở máy mới | Distribution/dependency chưa có trong cache | Cho phép tải lần đầu qua mạng; sau đó mới cân nhắc chế độ offline nếu đầy đủ cache |

**Không giải quyết lỗi bằng cách cài Gradle “phiên bản nào cũng được” rồi đổi sang `gradle build`:** như vậy sẽ bỏ qua hợp đồng phiên bản Gradle của repository.

## 13. Checklist nghiệm thu cho một repository đa nền tảng

1. Repository có đủ `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.jar` và `gradle/wrapper/gradle-wrapper.properties`; tất cả được commit.
2. `distributionUrl` chỉ về **một phiên bản và một loại ZIP cụ thể**; checksum SHA-256, nếu cấu hình, khớp ZIP đó.
3. `gradlew` dùng LF và được commit với execute bit; `gradlew.bat` hiện diện cho Windows.
4. Cả ba OS chạy `--version` hiển thị cùng phiên bản Gradle từ Wrapper; máy không cần Gradle toàn cục.
5. Task `help` thành công và task thực tế (`build`/`test` khi có) được kiểm chứng; CI chạy bằng Wrapper với JDK đã chọn.
6. Khi nâng cấp Gradle, làm mới đầy đủ bộ Wrapper, kiểm tra checksum, review diff và chạy lại CI.

## Tài liệu chính thức để tra cứu

- [Gradle Wrapper — thêm, chạy, nâng cấp, checksum](https://docs.gradle.org/current/userguide/gradle_wrapper.html)
- [Wrapper Basics — chức năng các tệp và lệnh theo OS](https://docs.gradle.org/current/userguide/gradle_wrapper_basics.html)
- [Gradle Compatibility Matrix — JDK/Gradle](https://docs.gradle.org/current/userguide/compatibility.html)
- [Gradle 8.14.3 release notes — ví dụ phiên bản dùng trong bài](https://docs.gradle.org/8.14.3/release-notes.html)
- [Gradle best practices for security](https://docs.gradle.org/current/userguide/best_practices_security.html)
