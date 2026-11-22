# Cấu hình bản phân phối và phiên bản trong `gradle-wrapper.properties`

## 1. Mục tiêu và vai trò của tệp

`gradle/wrapper/gradle-wrapper.properties` quyết định **Gradle Wrapper tải bản phân phối Gradle nào, từ đâu, xác minh thế nào và lưu ở đâu**. Nhờ đó, mỗi thành viên và máy CI có thể chạy cùng phiên bản Gradle đã chốt cho dự án, kể cả khi chưa cài Gradle toàn cục.

Một dự án có Wrapper thường có cấu trúc:

~~~text
project/
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── settings.gradle.kts  (hoặc settings.gradle)
└── build.gradle.kts     (hoặc build.gradle)
~~~

- `gradlew` (Linux/macOS) và `gradlew.bat` (Windows) là lệnh khởi động.
- `gradle-wrapper.jar` là chương trình bootstrap: đọc tệp properties, tải/giải nén bản phân phối khi cần và khởi chạy Gradle.
- `gradle-wrapper.properties` cấu hình bản phân phối chạy khi gọi Wrapper. Đây **không phải** `gradle.properties` (nơi thường đặt các tùy chọn Gradle, JVM, proxy hoặc thuộc tính build).
- `build.gradle(.kts)` quy định cách build; phiên bản plugin và Java toolchain được cấu hình ở nơi thích hợp khác, không tự thay đổi khi đổi `distributionUrl`.

Luồng thực thi: `./gradlew build` → Wrapper đọc `distributionUrl` → tìm bản phân phối trong cache → tải và kiểm tra nếu chưa có → khởi chạy đúng Gradle → Gradle thực hiện task `build`. Vì vậy, lệnh nên dùng trong dự án là `./gradlew ...` hoặc `.\gradlew.bat ...`, thay cho `gradle ...` cài toàn cục.

## 2. Cấu hình mẫu hoàn chỉnh

Ví dụ dùng **Gradle 9.6.1** và bản phân phối `bin`. Phiên bản này là **ví dụ có checksum cụ thể để dễ kiểm tra**, không phải yêu cầu mọi dự án phải nâng cấp lên 9.6.1; hãy chọn phiên bản đã được kiểm tra tương thích với Java, plugin và hệ thống build của dự án.

Tệp `gradle/wrapper/gradle-wrapper.properties`:

~~~properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\://services.gradle.org/distributions/gradle-9.6.1-bin.zip
distributionSha256Sum=9c0f7faeeb306cb14e4279a3e084ca6b596894089a0638e68a07c945a32c9e14
networkTimeout=10000
validateDistributionUrl=true
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
~~~

Diễn giải:

| Khóa | Vai trò |
| --- | --- |
| `distributionUrl` | URL của **tệp ZIP bản phân phối Gradle**. Tên `gradle-9.6.1-bin.zip` chốt cả phiên bản `9.6.1` lẫn loại `bin`. Đây là khóa chính khi chọn phiên bản. |
| `distributionSha256Sum` | SHA-256 của **chính tệp ZIP** được chỉ định trong `distributionUrl`; Wrapper từ chối bản tải mới nếu hash không khớp. Giá trị mẫu trên khớp checksum công bố cho `gradle-9.6.1-bin.zip`. |
| `distributionBase`, `distributionPath` | Nơi lưu **bản Gradle đã giải nén**: gốc và đường dẫn tương đối. |
| `zipStoreBase`, `zipStorePath` | Nơi lưu **tệp ZIP đã tải**: gốc và đường dẫn tương đối. |
| `networkTimeout` | Thời gian timeout cho hoạt động mạng của Wrapper, tính bằng **mili giây**; `10000` = 10 giây. |
| `validateDistributionUrl` | Điều khiển bước **kiểm tra URL khi task `wrapper` tạo/cập nhật cấu hình**; không thay thế kiểm tra checksum tệp tải về. |

`GRADLE_USER_HOME` là thư mục dữ liệu Gradle của người dùng (thường `~/.gradle` trên Linux/macOS hoặc `%USERPROFILE%\.gradle` trên Windows), có thể đổi bằng biến môi trường `GRADLE_USER_HOME`. Giá trị gốc khác có thể dùng là `PROJECT`, đặt dữ liệu theo thư mục dự án; mặc định dùng `GRADLE_USER_HOME` giúp các build chia sẻ cache bản phân phối. `wrapper/dists` là đường dẫn **tương đối** với gốc đã chọn; Wrapper tự quản lý các thư mục con theo phiên bản và URL.

Trong file Java `.properties` được Gradle tạo ra, `https\://` là cách biểu diễn URL có ký tự `:` được escape. Không dùng dấu nháy bao URL, không gõ nhầm thành đường dẫn tới trang HTML hoặc tới JAR. Nên để task `wrapper` sinh/cập nhật tệp để tránh lỗi cú pháp.

## 3. Chọn loại bản phân phối: `-bin` hay `-all`

| Loại | Nội dung và khi nào dùng |
| --- | --- |
| `gradle-X.Y.Z-bin.zip` | Chứa runtime Gradle để chạy build; tải nhỏ hơn, thường là lựa chọn phù hợp cho dev và CI. |
| `gradle-X.Y.Z-all.zip` | Chứa runtime kèm mã nguồn và tài liệu của Gradle; hữu ích khi cần nguồn/tài liệu trong IDE, nhưng tải và cache lớn hơn. |

Ví dụ hai URL hợp lệ cùng phiên bản:

~~~properties
# Chọn một trong hai dòng distributionUrl sau:
distributionUrl=https\://services.gradle.org/distributions/gradle-9.6.1-bin.zip
# distributionUrl=https\://services.gradle.org/distributions/gradle-9.6.1-all.zip
~~~

Nếu đổi `bin` thành `all`, **phải thay `distributionSha256Sum` bằng checksum của tệp `-all.zip`**. Hai ZIP khác nội dung nên không thể dùng chung checksum. Với Gradle 9.x, chuỗi phiên bản trong `gradle-wrapper.properties` cần đầy đủ dạng `X.Y.Z`; tránh tự ghi URL kiểu `gradle-9-bin.zip` hoặc `gradle-9.6-bin.zip`.

## 4. Thay đổi phiên bản bằng task `wrapper`

**Cách ưu tiên:** chạy task `wrapper`, commit các thay đổi Wrapper, rồi xác minh bằng chính Wrapper. Chọn một phiên bản cụ thể, kiểm tra [ma trận tương thích của Gradle](https://docs.gradle.org/current/userguide/compatibility.html) và ghi nhớ rằng nâng Gradle có thể buộc nâng plugin/AGP/JDK riêng biệt.

Trong thư mục gốc của dự án **đã có Wrapper**, ví dụ chọn phiên bản và checksum khớp với cấu hình mẫu trên:

~~~bash
# Linux/macOS
./gradlew wrapper --gradle-version 9.6.1 --distribution-type bin --gradle-distribution-sha256-sum 9c0f7faeeb306cb14e4279a3e084ca6b596894089a0638e68a07c945a32c9e14
./gradlew wrapper
./gradlew --version
./gradlew help
~~~

~~~powershell
# Windows PowerShell
.\gradlew.bat wrapper --gradle-version 9.6.1 --distribution-type bin --gradle-distribution-sha256-sum 9c0f7faeeb306cb14e4279a3e084ca6b596894089a0638e68a07c945a32c9e14
.\gradlew.bat wrapper
.\gradlew.bat --version
.\gradlew.bat help
~~~

Lệnh `wrapper` lần đầu cập nhật thông tin bản phân phối; lần thứ hai, sau khi khởi động bằng phiên bản mới, giúp đồng bộ cả script và `gradle-wrapper.jar` với Gradle mới khi cần. Với Wrapper hiện đại, một số thuộc tính cũ được giữ lại khi sinh lại file, nhưng `distributionUrl` sẽ được tạo lại; **luôn kiểm tra diff** và các tùy chọn sau khi chạy. Nếu chưa có `gradlew`/`gradlew.bat`, trên máy đã cài Gradle phải chạy `gradle wrapper --gradle-version 9.6.1 --distribution-type bin` để tạo bộ Wrapper trước.

`--gradle-version` nhận phiên bản đích; `--distribution-type` chọn `bin` hoặc `all`; `--gradle-distribution-sha256-sum` cung cấp checksum tương ứng. Có thể dùng `--gradle-distribution-url` khi tổ chức cần mirror riêng; lúc đó URL do bạn cung cấp xác định cả phiên bản và loại phân phối. Tùy Gradle phiên bản đang chạy, một số option mới có thể chưa được hỗ trợ; khi ấy hãy đọc hướng dẫn đúng phiên bản hiện tại và nâng từng bước.

Lệnh `./gradlew --version` phải thể hiện `Gradle 9.6.1` trong thông tin phiên bản; các dòng JVM, hệ điều hành, thời gian build có thể khác nhau nên không nên so sánh nguyên văn toàn bộ output. Lệnh `./gradlew help` xác nhận Wrapper khởi chạy được Gradle trong dự án; tiếp theo chạy task build/test mà dự án thực sự có.

**Có thể sửa tay `distributionUrl`**, nhưng cách này chỉ đổi bản Gradle sẽ tải, **không tự nâng** JAR và script Wrapper. Nếu sửa tay, phải kiểm tra đồng thời checksum, chạy lại task `wrapper` vào thời điểm thích hợp và xem diff. Trong repo, commit đủ bốn thành phần `gradlew`, `gradlew.bat`, `gradle-wrapper.jar`, `gradle-wrapper.properties` để developer/CI nhận đúng môi trường.

## 5. Pin phiên bản và checksum để build lặp lại được

Việc đặt URL phiên bản cụ thể giúp các máy dùng cùng bản Gradle. Với CI và dự án nhóm, nên:

1. Dùng **phiên bản đầy đủ** trong `distributionUrl`, tránh giá trị động hoặc đường dẫn không được kiểm soát.
2. Dùng **HTTPS** đến nguồn tin cậy; nếu qua mirror nội bộ, kiểm soát nguồn và tính toàn vẹn của ZIP.
3. Lấy SHA-256 từ nguồn phát hành độc lập, chẳng hạn [Gradle release checksums](https://gradle.org/release-checksums/), và ghi vào `distributionSha256Sum`. Ví dụ ở mục 2 sử dụng checksum `bin` chính thức của 9.6.1.
4. Khi đổi phiên bản hoặc `bin`/`all`, cập nhật URL **và checksum cùng một thay đổi**. Không bỏ hash chỉ để tránh lỗi.
5. Kiểm tra `gradle-wrapper.jar` khi nâng cấp; JAR chạy trước build nên nên đối chiếu checksum được Gradle công bố hoặc dùng công cụ kiểm tra Wrapper trong CI.

Lưu ý: cơ chế `distributionSha256Sum` kiểm tra tệp ZIP **khi Wrapper tải bản phân phối chưa có trong cache**; không coi việc chạy thành công từ một bản đã cache là bằng chứng ZIP tải mới đã được kiểm tra. Khi cần xác nhận quy trình tải sạch, dùng môi trường CI sạch hoặc `GRADLE_USER_HOME` tạm mới.

Tách rõ hai đối tượng kiểm tra: `distributionSha256Sum` kiểm tra **ZIP Gradle**; checksum `gradle-wrapper.jar` là việc kiểm tra **mã bootstrap JAR** và không được cấu hình bởi cùng khóa đó.

## 6. Tùy chỉnh đường dẫn, timeout và mạng

Giữ các đường dẫn mặc định thường đơn giản nhất. Khi cần điều chỉnh, nhớ cặp `distributionBase`/`distributionPath` dành cho bản đã giải nén, còn `zipStoreBase`/`zipStorePath` dành cho ZIP tải về. Tùy chọn này chỉ ảnh hưởng nơi Wrapper cất bản phân phối; chúng **không** chọn thư mục chứa dependency cache thông thường hay output `build/`.

Khi mạng chậm, có thể đặt:

~~~properties
networkTimeout=30000
retries=3
retryBackOffMs=1000
~~~

Ở đây timeout là 30 giây, Wrapper thử tải lại tối đa số lần cấu hình và khoảng chờ ban đầu là 1 giây, rồi tăng dần. `retries` và `retryBackOffMs` là các tùy chọn của Wrapper ở những phiên bản Gradle hỗ trợ chúng; kiểm tra phiên bản/JAR hiện có nếu thuộc tính không có tác dụng. Không tăng timeout vô hạn để che lỗi DNS, proxy hoặc quyền truy cập.

Nếu doanh nghiệp dùng proxy, cấu hình các **system properties liên quan proxy** trong `gradle.properties` của người dùng/qua tham số JVM thích hợp; không thêm khóa proxy không được Gradle Wrapper nhận biết vào `gradle-wrapper.properties`. Nếu mirror cần xác thực, giữ token/mật khẩu ngoài tệp Wrapper đã commit, dùng cơ chế xác thực qua system properties do Gradle hỗ trợ, chỉ dùng HTTPS và tránh đưa bí mật lên URL trong Git.

## 7. Chọn version phù hợp và nghiệm thu

Một checklist thiết thực cho PR thay đổi Wrapper:

- [ ] `distributionUrl` trỏ đúng ZIP, đúng phiên bản và `bin`/`all` đã chọn; URL không trả 404.
- [ ] `distributionSha256Sum` đúng 64 ký tự hex, lấy từ nguồn tin cậy, khớp chính xác tệp ZIP.
- [ ] `./gradlew --version` (hoặc `.\gradlew.bat --version`) hiển thị phiên bản đã chốt; Wrapper tải thành công nếu máy chưa có cache.
- [ ] `./gradlew help` chạy được; thực hiện build/test chính của dự án và kiểm tra tương thích JDK, Android Gradle Plugin hoặc plugin khác nếu có.
- [ ] Diff chỉ chứa thay đổi Wrapper mong muốn; script/JAR được đồng bộ nếu đã nâng.
- [ ] CI chạy bằng lệnh Wrapper và repo lưu đầy đủ các tệp Wrapper.

`gradle --version` chỉ cho biết bản Gradle **cài trên máy**; nó có thể khác bản mà `./gradlew --version` thực sự dùng. Chính thông tin từ Wrapper mới là bằng chứng phiên bản của dự án.

## 8. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `404`, không tải được ZIP | Sai chính tả hoặc phiên bản trong `distributionUrl` không tồn tại | Đối chiếu URL phát hành chính thức, dùng phiên bản đầy đủ, kiểm tra truy cập từ CI. |
| `Checksum verification failed` | SHA-256 không khớp URL, đã đổi `bin`/`all` mà quên đổi hash, hoặc ZIP bị sai/hỏng | Xác nhận URL và checksum từ nguồn chính thức; kiểm tra nguồn tải/mirror trước khi thử lại. Không tắt xác minh để bỏ qua lỗi. |
| Timeout, DNS, proxy, `401/403` | Mạng/proxy/firewall hoặc quyền truy cập mirror | Kiểm tra URL, cấu hình proxy và xác thực hợp lệ; điều chỉnh `networkTimeout` khi thật sự cần. |
| `Could not find or load main class org.gradle.wrapper.GradleWrapperMain` | Thiếu/hỏng `gradle-wrapper.jar` hoặc chạy bộ script không đồng bộ | Khôi phục JAR đáng tin cậy từ Git hoặc tái tạo Wrapper từ môi trường tin cậy rồi kiểm tra checksum. |
| `./gradlew`: permission denied | Script chưa có quyền execute trên Linux/macOS | Khôi phục quyền execute cho `gradlew` và lưu bit này trong Git. |
| Lệnh `gradle --version` khác `./gradlew --version` | Gradle toàn cục khác bản Wrapper đã pin | Dùng `./gradlew` cho thao tác dự án; không lấy bản toàn cục làm chuẩn. |
| Nâng Gradle xong build/plugin lỗi | Phiên bản Gradle mới không tương thích JDK, plugin, AGP hoặc Gradle DSL | Kiểm tra compatibility/release notes, nâng plugin/JDK theo hướng dẫn hoặc chọn phiên bản Gradle tương thích. |
| Đã sửa `distributionUrl` nhưng script/JAR vẫn cũ | Thay thủ công chỉ đổi URL phân phối | Chạy task `wrapper` lần nữa để đồng bộ và kiểm tra diff; giữ checksum đúng. |
| Thêm khóa timeout/retry nhưng không thấy hiệu lực | Wrapper JAR quá cũ hoặc khóa viết sai | Xác nhận tài liệu theo phiên bản Wrapper hiện có, nâng Wrapper đúng cách. |

## 9. Tự kiểm tra hiểu bài

1. Nếu muốn mọi thành viên dùng một phiên bản Gradle cố định, cần sửa khóa nào? **`distributionUrl`** là nguồn quyết định; đồng bộ checksum và Wrapper files đi kèm.
2. Đổi từ `gradle-9.6.1-bin.zip` sang `gradle-9.6.1-all.zip` nhưng giữ nguyên SHA-256 có ổn không? **Không**; hai ZIP khác nhau nên checksum cũng khác.
3. Vì sao `gradle --version` không đủ để kiểm tra cấu hình dự án? Vì lệnh đó có thể gọi bản toàn cục; dùng **`./gradlew --version`** hoặc **`.\gradlew.bat --version`**.
4. `distributionSha256Sum` có xác minh JAR bootstrap không? **Không**; nó xác minh ZIP khi tải. Cần kiểm tra `gradle-wrapper.jar` riêng.
5. Lưu cache bản phân phối vào đâu theo mẫu? **Gradle User Home**, dưới `wrapper/dists`; không phải thư mục output `build/` của dự án.

## Tài liệu tham khảo chính thức

- [Gradle Wrapper — cấu hình URL, phiên bản, task wrapper, checksum, cache và mạng](https://docs.gradle.org/current/userguide/gradle_wrapper.html).
- [Gradle Wrapper basics — cấu trúc bốn tệp và cách chạy](https://docs.gradle.org/current/userguide/gradle_wrapper_basics.html).
- [Gradle release checksums — SHA-256 ZIP và Wrapper JAR](https://gradle.org/release-checksums/).
- [Gradle compatibility matrix — Java và phiên bản Gradle](https://docs.gradle.org/current/userguide/compatibility.html).
- [Gradle security best practices — xác minh bản phân phối và JAR](https://docs.gradle.org/current/userguide/best_practices_security.html).
