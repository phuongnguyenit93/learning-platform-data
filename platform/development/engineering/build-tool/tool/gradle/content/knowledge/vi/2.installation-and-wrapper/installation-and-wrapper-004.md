# Gradle Wrapper: vai trò của `gradlew`, `gradlew.bat` và `gradle-wrapper`

## 1. Gradle Wrapper giải quyết vấn đề gì?

Khi làm việc nhóm, máy lập trình viên, máy chủ CI và môi trường triển khai có thể cài các phiên bản Gradle khác nhau. Nếu ai cũng chạy lệnh `gradle build`, chương trình sẽ dùng bản Gradle đang có trong `PATH` của từng máy; khác phiên bản có thể dẫn đến khác hành vi, lỗi plugin hoặc kết quả build không nhất quán.

**Gradle Wrapper** là bộ tệp nhỏ được lưu cùng mã nguồn dự án. Thay vì yêu cầu mọi người cài đúng phiên bản Gradle, dự án khai báo một bản phân phối Gradle trong `gradle-wrapper.properties`; các script `gradlew` hoặc `gradlew.bat` sẽ khởi động bản đó và tự tải về nếu máy chưa có.

Điểm cần phân biệt:

- **Không cần cài Gradle toàn cục** để chạy *một dự án đã có Wrapper đầy đủ*.
- **Vẫn cần Java/JDK phù hợp** để khởi động Wrapper và chạy bản Gradle đã chọn; Java toolchain của dự án là một khái niệm liên quan nhưng khác với Java dùng để chạy chính Gradle.
- **Lần đầu có thể cần mạng** để tải bản phân phối; những lần sau thường dùng bản được lưu trong bộ nhớ đệm.
- Wrapper giúp thống nhất **phiên bản công cụ build**; nó không tự bảo đảm mọi dependency, môi trường, biến cấu hình hay đầu vào build đều giống nhau.

## 2. Bốn tệp cấu thành một Wrapper hoàn chỉnh

Một dự án dùng Gradle Kotlin DSL có thể trông như sau (với Groovy DSL, tên tệp tương ứng là `settings.gradle` và `build.gradle`):

```text
my-project/
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── settings.gradle.kts
├── build.gradle.kts
└── src/
```

| Tệp | Chức năng chính | Khi nào được sử dụng? |
| --- | --- | --- |
| `gradlew` | Script shell dành cho Linux, macOS và môi trường Unix; xác định Java rồi gọi Wrapper JAR | Chạy `./gradlew ...` trong terminal Unix |
| `gradlew.bat` | Batch script dành cho Windows, thực hiện vai trò tương tự `gradlew` | Chạy `gradlew.bat ...` hoặc `.\\gradlew.bat ...` trên Windows |
| `gradle/wrapper/gradle-wrapper.jar` | Chứa mã Java để đọc cấu hình, tải/giải nén bản Gradle cần thiết và khởi động nó | Được cả hai script gọi thông qua JVM |
| `gradle/wrapper/gradle-wrapper.properties` | Khai báo URL và tùy chọn tải bản phân phối Gradle | Được Wrapper JAR đọc trước khi khởi chạy Gradle |

**`gradle-wrapper` không phải tên một lệnh riêng.** Người học thường dùng tên này để chỉ thành phần Wrapper nói chung hoặc hai tệp `gradle-wrapper.jar` và `gradle-wrapper.properties` trong thư mục `gradle/wrapper/`.

`settings.gradle(.kts)` mô tả cấu trúc build, `build.gradle(.kts)` khai báo plugin/task/dependency. Chúng là tệp cấu hình *dự án*, không thay thế bốn tệp Wrapper.

## 3. Luồng thực thi: ai gọi ai?

```text
Người dùng chạy ./gradlew test (Linux/macOS)
             hoặc .\gradlew.bat test (Windows)
                         │
                         ▼
            gradlew / gradlew.bat
           tìm Java và gọi JVM với
          gradle-wrapper.jar trong classpath
                         │
                         ▼
             GradleWrapperMain
       đọc gradle-wrapper.properties
                         │
            ┌────────────┴────────────┐
            │                         │
       Đã có Gradle            Chưa có bản Gradle
       trong cache?            tương ứng trong cache?
            │                         │
            │                  tải ZIP từ distributionUrl
            │                  kiểm checksum nếu cấu hình
            │                  giải nén vào GRADLE_USER_HOME
            └────────────┬────────────┘
                         ▼
              khởi động Gradle
          chuyển tiếp các tham số: test
                         │
                         ▼
             Gradle thực thi task
```

Cụ thể, mỗi script chuyển các đối số của người dùng tới chương trình Java `org.gradle.wrapper.GradleWrapperMain` trong JAR. Chương trình này dùng `distributionUrl` để xác định bản Gradle cần chạy; nếu cần, nó tải và giải nén bản phân phối trong `GRADLE_USER_HOME/wrapper/dists` (thường nằm dưới `~/.gradle` trên Linux/macOS hoặc thư mục người dùng Windows). Sau đó Gradle thực thi task và tham số được yêu cầu.

Ví dụ, `./gradlew test --info` không phải script shell tự chạy các bài test: script chỉ **khởi động Gradle** rồi chuyển `test --info` cho Gradle xử lý. Nếu dự án không định nghĩa task `test`, Gradle có thể báo không tìm thấy task; Wrapper vẫn có thể hoạt động bình thường.

Bộ nhớ đệm **bản phân phối Gradle** trong `wrapper/dists` khác với cache dependency của Gradle và khác với thư mục `.gradle/` nằm trong dự án. Không cần commit bản Gradle đã giải nén vào Git.

## 4. Vai trò của `gradlew` trên Linux/macOS

`gradlew` là script shell được tạo bởi Gradle, nằm ở thư mục gốc của build. Nó thiết lập đường dẫn và môi trường cần thiết để gọi Wrapper JAR qua Java. Người dùng phải chỉ rõ đường dẫn tương đối `./` vì thư mục hiện tại thường không nằm trong `PATH`.

```bash
# Đứng tại thư mục gốc dự án đã có Wrapper
./gradlew --version
./gradlew tasks
./gradlew build

# Chỉ dùng khi dự án có task test
./gradlew test
```

Ý nghĩa:

- `--version`: in thông tin phiên bản Gradle **mà Wrapper khởi động**; đây là bước kiểm tra thiết lập dễ nhất, không cần giả định dự án có task nào.
- `tasks`: liệt kê các task được Gradle công bố cho build hiện tại.
- `build`: gọi task `build` khi các plugin/cấu hình dự án cung cấp task đó.
- `test`: gọi task `test` khi dự án có task tương ứng, thường gặp trong dự án Java.

Trên Linux/macOS, script thường cần quyền thực thi. Nếu nhận `Permission denied`, có thể dùng:

```bash
chmod +x gradlew
./gradlew --version
```

Trong Git, thuộc tính executable của `gradlew` cần được lưu cùng commit, để thành viên mới và runner CI dùng được sau khi clone. Không chỉnh thủ công nội dung script đã sinh nếu không có lý do được kiểm soát; hãy tái tạo thông qua task `wrapper`.

## 5. Vai trò của `gradlew.bat` trên Windows

Windows thông thường chạy **batch script** `gradlew.bat`, cũng xác định Java và gọi cùng `gradle-wrapper.jar`. Hai script hướng tới cùng cấu hình `gradle-wrapper.properties`, nên cùng dự án sẽ chọn cùng bản phân phối Gradle.

Trong **Command Prompt** (cmd.exe):

```bat
gradlew.bat --version
gradlew.bat tasks
gradlew.bat build
```

Trong **PowerShell** (tại thư mục gốc dự án):

```powershell
.\gradlew.bat --version
.\gradlew.bat tasks
.\gradlew.bat build
```

PowerShell thường cần `.\` để chạy chương trình ở thư mục hiện tại. File `.bat` không dùng bit executable kiểu Unix, nên lệnh `chmod +x` không phải giải pháp cho lỗi chạy trên Windows. Nếu một người dùng chạy trên Linux và một người dùng chạy trên Windows, **họ chọn script khác nhau nhưng dùng cùng cấu hình phiên bản Gradle**.

## 6. `gradle-wrapper.jar`: trình khởi động thực sự

`gradle/wrapper/gradle-wrapper.jar` là JAR chứa chương trình Java của Wrapper, không phải toàn bộ bản phân phối Gradle và cũng không phải JAR của ứng dụng do dự án build. Trách nhiệm chính của nó là đọc tệp properties, tìm hoặc tải bản Gradle tương ứng, giải nén khi cần và bàn giao việc chạy build cho Gradle.

Vì vậy:

1. Có `gradlew` nhưng thiếu `gradle-wrapper.jar` thì script không thể khởi động đúng chương trình Wrapper; lỗi thường liên quan tới `org.gradle.wrapper.GradleWrapperMain`.
2. **Cần đưa JAR vào Git** cùng các script và properties; quy tắc bỏ qua `*.jar` quá rộng có thể làm mất tệp này khi commit.
3. JAR là mã nhị phân sẽ được chạy, nên cần bảo đảm xuất xứ đáng tin và kiểm tra checksum Wrapper JAR khi nâng cấp hoặc tiếp nhận thay đổi từ nguồn không tin cậy.
4. Không tự thay thế JAR bằng một tệp JAR tùy ý và không tải JAR từ nguồn lạ để “sửa nhanh” lỗi thiếu Wrapper.

## 7. `gradle-wrapper.properties`: phiên bản và địa chỉ tải

Ví dụ minh họa cho bản Gradle `9.9.0` (phiên bản trong URL là **ví dụ cố định**; khi áp dụng phải chọn bản tương thích với dự án):

```properties
# gradle/wrapper/gradle-wrapper.properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\://services.gradle.org/distributions/gradle-9.9.0-bin.zip
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
networkTimeout=10000
validateDistributionUrl=true
```

Các thuộc tính chính:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `distributionUrl` | URL bản Gradle cần tải và chạy; phiên bản nằm trong tên ZIP, ví dụ `gradle-9.9.0-bin.zip` |
| `distributionBase`, `distributionPath` | Vị trí thư mục bản phân phối đã được cài/giải nén |
| `zipStoreBase`, `zipStorePath` | Vị trí lưu ZIP tải về |
| `networkTimeout` | Thời gian chờ khi tải, đơn vị mili giây |
| `validateDistributionUrl` | Thiết lập kiểm tra URL khi cấu hình/tạo lại Wrapper |
| `distributionSha256Sum` | Tùy chọn checksum SHA-256 **thực** của ZIP bản phân phối, dùng để kiểm tra lần tải mới |

Trong định dạng Java `.properties`, dạng `https\://` là cách biểu diễn hợp lệ của URL `https://`; dấu `\\` trước `:` là ký tự escape. Lựa chọn `-bin.zip` cung cấp runtime Gradle đủ cho phần lớn build và tải nhẹ hơn; `-all.zip` còn có mã nguồn và tài liệu Gradle, hữu ích cho vài nhu cầu IDE nhưng nặng hơn. Đây là **bản phân phối Gradle**, không phải kiểu đóng gói ứng dụng của bạn.

Khi cần kiểm tra tính toàn vẹn của bản phân phối, lấy SHA-256 công bố cho **đúng URL/phiên bản/loại ZIP** từ nguồn Gradle chính thức rồi đặt vào `distributionSha256Sum`. Không chèn một hash giả hoặc hash của file JAR vào thuộc tính này. Việc kiểm tra checksum bản phân phối diễn ra khi Wrapper cần tải bản đó; nếu bản phân phối đã được cài trong cache, lần chạy sau có thể không tải hoặc kiểm lại ZIP.

Đừng nhầm `gradle-wrapper.properties` với `gradle.properties`: tệp thứ nhất điều khiển **việc tìm và khởi động Gradle**, còn tệp thứ hai thường chứa thuộc tính/cấu hình dành cho chính quá trình Gradle build.

## 8. Tạo Wrapper lần đầu cho dự án

Với một dự án Gradle mới hoặc dự án cũ chưa có Wrapper, có thể sử dụng Gradle đã cài trên máy **một lần** để sinh các tệp:

```bash
# Chạy tại thư mục gốc dự án đã được khởi tạo Gradle
gradle :wrapper --gradle-version 9.9.0 --distribution-type bin

# Từ lần này, sử dụng Wrapper của dự án
./gradlew --version
```

Dấu `:` trong `:wrapper` yêu cầu task của root project. Nếu tạo dự án bằng `gradle init`, công cụ thường tự tạo các tệp Wrapper trong quá trình khởi tạo. Trên Windows, sau khi tạo Wrapper, kiểm tra bằng `.\gradlew.bat --version`.

Sau khi sinh, đưa **đủ bốn tệp** vào version control:

```bash
git add gradlew gradlew.bat gradle/wrapper/gradle-wrapper.jar gradle/wrapper/gradle-wrapper.properties
git commit -m "Add Gradle Wrapper"
```

Lệnh `git commit` ở đây chỉ là ví dụ thao tác của người học; không phải điều kiện để Wrapper chạy trên máy hiện tại. Kiểm tra tình trạng executable của `gradlew` trên hệ Unix trước khi commit.

## 9. Nâng cấp phiên bản Gradle một cách kiểm soát

Khi cần đổi phiên bản, nên chạy task `:wrapper` của dự án thay vì thay tay các script/JAR. Ví dụ dưới đây chuyển sang `9.9.0` khi dự án đang dùng bản cũ và **chưa bật `distributionSha256Sum`**:

```bash
./gradlew :wrapper --gradle-version 9.9.0 --distribution-type bin
./gradlew :wrapper --gradle-version 9.9.0 --distribution-type bin
./gradlew --version
```

Lần chạy đầu có thể chỉ cập nhật `gradle-wrapper.properties`; lần thứ hai chạy bằng bản Gradle mới để làm mới cả Wrapper JAR và các script. Sau đó chạy các task kiểm thử thích hợp, xem thay đổi bốn tệp rồi commit chúng cùng nhau. Trên Windows dùng `.\gradlew.bat` thay cho `./gradlew`.

**Nếu properties đã có `distributionSha256Sum`**, khi đổi phiên bản phải cung cấp SHA-256 mới phù hợp, ví dụ qua tùy chọn `--gradle-distribution-sha256-sum` với checksum thực lấy từ trang phát hành; task có thể từ chối nâng cấp nếu checksum cũ không được cập nhật. Không giữ checksum của phiên bản cũ, không bỏ qua lỗi mismatch chỉ để build chạy được.

Trước khi nâng cấp, đọc tài liệu tương thích của bản Gradle đích (Java chạy Gradle, plugin, Android/Kotlin nếu có), chạy kiểm thử và xem ghi chú phát hành. **Pin một phiên bản cụ thể** trong dự án để CI có đầu vào ổn định; các nhãn động như `latest` phù hợp cho việc thử nghiệm có kiểm soát hơn là build muốn tái lập.

## 10. Wrapper trong làm việc nhóm, IDE và CI

Cùng một kho mã nguồn, mỗi môi trường dùng lệnh phù hợp hệ điều hành:

| Môi trường | Ví dụ lệnh | Điều kiện |
| --- | --- | --- |
| Máy Linux/macOS | `./gradlew build` | Có Java tương thích; script executable |
| Windows PowerShell | `.\\gradlew.bat build` | Có Java tương thích |
| CI runner Linux | `./gradlew --no-daemon build` | Runner cấp Java, quyền thực thi, quyền truy cập distribution/caches |
| IDE hỗ trợ Gradle | Chọn sử dụng **Gradle Wrapper của dự án** | IDE đọc cấu hình Wrapper thay vì áp bản Gradle cài toàn cục |

Trong CI, thông lệ là checkout mã nguồn, chuẩn bị JDK phù hợp, cho phép Wrapper tải/đọc bản phân phối và chạy `./gradlew ...`. Tùy dự án, có thể cache `GRADLE_USER_HOME` để tránh tải lại; cần bảo vệ cache và khóa cache hợp lý khi đổi phiên bản. Wrapper không cấp JDK cho runner, không tự tạo task chưa tồn tại và không thay thế cấu hình proxy/chứng chỉ khi môi trường mạng yêu cầu.

## 11. Các lỗi thường gặp và cách tìm nguyên nhân

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `./gradlew: Permission denied` | `gradlew` chưa có quyền thực thi trên Unix | `chmod +x gradlew`, lưu executable bit trong Git |
| `java: command not found` hoặc lỗi `JAVA_HOME` | Chưa có Java hoặc môi trường trỏ sai JDK | Cài/chọn JDK tương thích; kiểm tra `java -version` và `JAVA_HOME` |
| `Could not find or load main class org.gradle.wrapper.GradleWrapperMain` | Thiếu/hỏng `gradle-wrapper.jar` hoặc script/classpath sai | Kiểm tra đủ bốn tệp, khôi phục JAR chính thống và xác minh tính toàn vẹn |
| Wrapper báo không tải được ZIP, TLS, proxy, 404/403 | Sai `distributionUrl`, không có mạng, proxy/chứng chỉ hoặc quyền truy cập | Kiểm URL, kết nối và cấu hình proxy/chứng chỉ/mirror hợp lệ; không tắt kiểm tra bảo mật tùy tiện |
| SHA-256 không khớp | ZIP bị thay đổi/hỏng hoặc hash không đúng phiên bản/loại ZIP | So URL và SHA-256 với nguồn phát hành chính thức; xử lý bản tải lỗi rồi tải lại từ nguồn tin cậy |
| Unix báo `/bin/sh^M`, `bad interpreter` | Script bị đổi sang CRLF khi lưu/chuyển hệ điều hành | Khôi phục kết thúc dòng LF cho `gradlew` và lưu cấu hình Git thích hợp |
| `gradle --version` khác `./gradlew --version` | Lệnh đầu dùng Gradle toàn cục, lệnh sau dùng bản của dự án | Dùng Wrapper khi build dự án; xem `distributionUrl` nếu cần xác định phiên bản |
| Lần chạy đầu thất bại khi dùng `--offline` | Chưa có bản phân phối Gradle trong cache | Cho phép tải lần đầu hoặc cấp trước bản phân phối; `--offline` không tự tạo bản Gradle bị thiếu |

Nếu `./gradlew --version` đã thành công mà `./gradlew test` báo `Task 'test' not found`, hãy xem cấu hình plugin/task của dự án: đây là vấn đề task, chưa đủ cơ sở kết luận Wrapper hỏng.

## 12. Tự kiểm tra sau khi clone dự án

Từ thư mục gốc, làm tuần tự:

1. Xác nhận có `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.jar` và `gradle/wrapper/gradle-wrapper.properties`.
2. Mở properties, xem `distributionUrl` có chỉ tới phiên bản Gradle dự kiến và checksum (nếu có) tương ứng chính xác với ZIP đó không.
3. Kiểm tra Java đang dùng bằng `java -version`; bảo đảm phiên bản Java đáp ứng yêu cầu của Gradle.
4. Chạy `./gradlew --version` (Linux/macOS) hoặc `.\gradlew.bat --version` (Windows), đối chiếu phiên bản được in với URL.
5. Chạy `tasks` để xem các task hiện có; sau đó chạy `build`/`test` theo thực tế cấu hình dự án.
6. Nếu onboarding/CI gặp lỗi, phân biệt lỗi **script → JAR → tải bản phân phối → JVM/Gradle → task/dependency** để xác định đúng tầng cần sửa.

**Ghi nhớ:** `gradlew` và `gradlew.bat` là hai điểm vào theo hệ điều hành; `gradle-wrapper.jar` là mã khởi động/tải Gradle; `gradle-wrapper.properties` quy định bản Gradle và cách tải. Bốn tệp phải đi cùng nhau trong repository để mọi máy chạy đúng bản công cụ build mà dự án chọn.

## Tài liệu tham khảo

- [Gradle User Manual — Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html): cơ chế, cách tạo, sử dụng, nâng cấp, tùy chọn URL/checksum.
- [Gradle User Manual — Installing Gradle](https://docs.gradle.org/current/userguide/installation.html): Java cần thiết và cách bootstrap dự án.
- [Gradle User Manual — Best Practices for Security](https://docs.gradle.org/current/userguide/best_practices_security.html): xác minh checksum bản phân phối và Wrapper JAR.
