# Dùng `-e`, `-X` để đọc lỗi chi tiết và bảo vệ dữ liệu trong log Maven

## 1. Khi nào cần log chi tiết hơn?

Khi chạy Maven, phần lớn lần build chỉ cần log mặc định: các goal đã chạy, thông tin plugin, cảnh báo, lỗi và dòng kết luận `BUILD SUCCESS` hoặc `BUILD FAILURE`. Tuy nhiên, đôi khi log kết thúc bằng thông điệp khá chung như:

```text
[ERROR] Failed to execute goal ... on project demo: ...
[ERROR] To see the full stack trace of the errors, re-run Maven with the -e switch.
[ERROR] Re-run Maven using the -X switch to enable full debug logging.
```

Lúc này cần hiểu thêm **lỗi được ném từ đâu**, **cấu hình thực tế của Maven/plugin là gì** hoặc **vì sao artifact không resolve được**. Maven cung cấp hai tùy chọn dòng lệnh:

- **`-e`, `--errors`:** hiện thêm thông tin lỗi thực thi, bao gồm **stack trace** của những exception Maven thu thập để báo cáo. Hữu ích để xác định chuỗi `Caused by` và vị trí gây lỗi khi thông báo mặc định không đủ.
- **`-X`, `--debug`:** bật **debug logging** cho Maven. Thường thêm thông tin về phiên bản/môi trường, quá trình nạp plugin, cấu hình goal, dependency resolution, classpath và nhiều chi tiết khác tùy plugin. Phù hợp khi cần điều tra sâu; log có thể rất dài.

**Hai tùy chọn chỉ thay đổi mức thông tin được ghi**, không tự sửa lỗi, không tự nâng cấp plugin và không bảo đảm build thành công. Chúng cũng **không phải công cụ bảo mật**: log càng chi tiết, càng có khả năng tiết lộ thông tin nội bộ. Khi xử lý log, luôn cân nhắc ai được xem và log sẽ được lưu ở đâu.

## 2. So sánh các mức log thường gặp

| Cách chạy | Mục đích | Thông tin chính | Khi nên dùng |
| --- | --- | --- | --- |
| `mvn clean verify` | Build theo mức log thường | Dòng goal, INFO/WARNING/ERROR và kết luận | Lượt chạy đầu tiên, tái hiện lỗi |
| `mvn -e clean verify` | Xem chi tiết exception | Thông báo lỗi và stack trace bổ sung nếu có | Lỗi plugin hoặc Maven chưa rõ nguyên nhân |
| `mvn -X clean verify` | Xem debug sâu | Log thường và các thông tin debug từ Maven/plugin | Lỗi dependency, plugin, classpath, cấu hình phức tạp |
| `mvn -e -X clean verify` | Yêu cầu cả hai | Debug và thông tin lỗi chi tiết | Khi một lần chẩn đoán sâu có kiểm soát là cần thiết |
| `mvn -q clean verify` | Giảm log thường | Chủ yếu là thông báo lỗi | Chạy ít tiếng ồn; không thích hợp để học dòng thực thi |
| `mvn -B -ntp clean verify` | Log dễ đọc trong CI | Tắt tương tác, ẩn tiến độ chuyển tải | Build tự động; có thể kết hợp với `-e` hoặc `-X` |

`-B` (batch mode) và `-ntp` (no transfer progress) **không đồng nghĩa** debug. Chúng chỉ làm log gọn hoặc phù hợp môi trường tự động. `-q` làm log ngắn đi, còn `-X` làm log dài hơn; tránh gộp những tùy chọn có mục đích trái nhau khi đang học cách điều tra.

Nếu dự án có Maven Wrapper, thay `mvn` bằng `./mvnw` trên Linux/macOS hoặc `.\mvnw.cmd` trên Windows. Các tùy chọn `-e` và `-X` vẫn được truyền vào Maven mà Wrapper chạy.

## 3. Dự án mẫu Java 17 để tự quan sát lỗi

Ta xây dựng một dự án nhỏ tên `maven-log-lab`:

```text
maven-log-lab/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── App.java
```

Nội dung đầy đủ của `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>maven-log-lab</artifactId>
    <version>1.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Tệp `src/main/java/example/App.java` ban đầu:

```java
package example;

public class App {
    public static void main(String[] args) {
        System.out.println("Log demo OK");
    }
}
```

Yêu cầu JDK 17+ và Maven tương thích. Kiểm tra môi trường bằng `mvn -version`, đặc biệt là dòng **Java version** và **Java home** mà Maven đang dùng. Từ thư mục có `pom.xml`, chạy:

```bash
mvn -B -ntp clean verify
java -cp target/classes example.App
```

Khi build thành công, Maven có dòng kết luận `BUILD SUCCESS`. Lệnh Java thứ hai in chính xác:

```text
Log demo OK
```

Lưu ý: `mvn clean verify` không tự gọi phương thức `main`; thông điệp `Log demo OK` xuất hiện do **lệnh `java` riêng**. Pha `verify` bao gồm các bước cần thiết trước đó theo lifecycle và cấu hình dự án, nhưng không chứng minh mọi loại test đều chạy nếu chúng đã bị bỏ qua theo cấu hình.

### Cố ý gây lỗi biên dịch

Thay **toàn bộ** nội dung `App.java` thành:

```java
package example;

public class App {
    public static void main(String[] args) {
        System.out.println(missingMessage);
    }
}
```

`missingMessage` không được khai báo. Trong đoạn tệp đúng như trên, tên biến nằm ở dòng 5, bắt đầu tại cột 28. Chạy lại:

```bash
mvn -B -ntp clean verify
```

Một trích đoạn log minh họa (bỏ các dòng trung gian và dùng đường dẫn ví dụ) là:

```text
[INFO] --- compiler:3.13.0:compile (default-compile) @ maven-log-lab ---
[ERROR] COMPILATION ERROR :
[ERROR] /work/maven-log-lab/src/main/java/example/App.java:[5,28] cannot find symbol
[ERROR]   symbol:   variable missingMessage
[ERROR]   location: class example.App
[INFO] BUILD FAILURE
[ERROR] Failed to execute goal org.apache.maven.plugins:maven-compiler-plugin:3.13.0:compile (default-compile) on project maven-log-lab: Compilation failure
```

Đọc thông báo cụ thể trước: **`App.java:[5,28] cannot find symbol`**, kết hợp với dòng `symbol: variable missingMessage`. Đây là lỗi biên dịch Java; có thể sửa ngay tại dòng 5. `BUILD FAILURE` chỉ là kết luận, còn `Failed to execute goal` cho biết goal nào đã dừng. Khi đã có thông điệp rõ như vậy, **không nhất thiết phải bật `-X`**.

## 4. Dùng `-e` để tìm chuỗi nguyên nhân

Khi log thông thường báo lỗi Maven/plugin nhưng thông điệp chi tiết vẫn chưa đủ, thử chạy lại **cùng pha và cùng điều kiện** với `-e`:

```bash
mvn -B -ntp -e clean verify
```

Trong trường hợp Java không biên dịch, các dòng báo `cannot find symbol` vẫn là chẩn đoán quan trọng nhất. `-e` có thể bổ sung stack trace cho exception do Maven/plugin đưa ra. Ví dụ **rút gọn theo cấu trúc**:

```text
[ERROR] Failed to execute goal ...:compile ... : Compilation failure
org.apache.maven.lifecycle.LifecycleExecutionException: ...
    at org.apache.maven.lifecycle.internal...
Caused by: org.apache.maven.plugin.compiler.CompilationFailureException: ...
    at org.apache.maven.plugin.compiler...
```

Đường dẫn class và số dòng stack trace khác nhau theo phiên bản Maven/plugin. Không nên học thuộc chúng. Hãy tìm:

1. **Thông báo lỗi cụ thể ở phía trên:** tệp nào, goal nào, dependency nào, test nào.
2. **Exception ngoài cùng:** thường cho biết Maven đang xử lý một goal/lifecycle bị thất bại.
3. **`Caused by:` sâu hơn:** có thể cho biết nguyên nhân trong plugin, Java, HTTP/TLS, classloading hoặc plugin execution.
4. **Frame stack trace đầu tiên thuộc mã của bạn hoặc plugin liên quan:** giúp xác định chỗ cần điều tra.

Một stack trace có thể gồm nhiều `Caused by`, mỗi tầng bọc tầng dưới; không coi mỗi tầng là một lỗi độc lập. Không phải lần build thất bại nào cũng có exception hữu ích hơn thông điệp compiler/test ở đầu log.

**Quy tắc thực hành:** ưu tiên thông báo có tính hành động (ví dụ `cannot find symbol`, `Could not resolve artifact`, tên test fail) hơn một stack trace dài nhưng chỉ nói `LifecycleExecutionException`.

## 5. Dùng `-X` để tìm thông tin plugin, dependency và môi trường

Nếu `-e` chưa giải thích được vì sao Maven chọn plugin/version nào, dùng classpath nào, lấy dependency ở repository nào hoặc đọc cấu hình gì, bật debug:

```bash
mvn -B -ntp -X clean verify
```

Thông thường log xuất hiện nhiều dòng `[DEBUG]` hơn, có thể chứa:

- Phiên bản Maven và Java, thông tin hệ điều hành, các đường dẫn Maven home, Java home, local repository.
- Quá trình chọn repository/mirror, tải artifact và xử lý dependency/plugin. Với lỗi resolve, tìm artifact coordinates và thông điệp thực tế về kết nối hoặc không tìm thấy artifact.
- Quá trình tạo class realm/classpath của plugin và các dependency liên quan, hữu ích khi lỗi `ClassNotFoundException` hoặc `NoClassDefFoundError`.
- Cấu hình goal/plugin đang được Maven thực thi. Một số plugin in thông tin chi tiết về tham số có giá trị thực tế đã được resolve.
- Stack trace hoặc phần chẩn đoán bổ sung, tùy lỗi và phiên bản.

Ví dụ các từ khóa để **tìm trong log**, không phải cam kết mọi bản Maven đều in đúng câu chữ:

```text
[DEBUG] ...
[INFO] --- compiler:3.13.0:compile (default-compile) @ maven-log-lab ---
[ERROR] Could not resolve dependencies for project ...
[ERROR] Caused by: ...
```

Khi debug dependency, phân tích cụ thể:

1. **Artifact nào?** `groupId:artifactId:version` và type/classifier nếu có.
2. **Maven tra cứu ở đâu?** Repository và mirror cấu hình; URL hoặc hostname có thể là dữ liệu nội bộ, cần che khi chia sẻ.
3. **Lỗi mạng hay tọa độ?** `Unknown host`, `401/403`, `PKIX path building failed`, `Could not find artifact` có hướng xử lý khác nhau. Thông báo HTTP chỉ là ví dụ; cần xem nguyên nhân đầy đủ.
4. **Cấu hình hiệu lực nào?** Parent POM, dependency management, plugin management, profile, `settings.xml` có thể làm kết quả khác với những gì thấy trong một POM đơn lẻ.

Với lỗi JDK, so `mvn -version` với `maven.compiler.release`, Maven Toolchains (nếu có) và `JAVA_HOME`. Với lỗi test, thường đọc `target/surefire-reports` trước khi cần `-X`.

**Không bật `-X` mặc định cho mọi build CI.** Mức debug tăng khối lượng log, có thể chậm hơn trong môi trường có logging nặng, khó tìm lỗi chính và làm tăng dữ liệu cần bảo vệ/lưu trữ.

## 6. Chọn chiến lược chẩn đoán theo mức tối thiểu cần thiết

Sơ đồ quyết định:

```text
Build thất bại
    |
    v
Đọc lỗi mặc định và goal thất bại
    |
    +-- Có thông điệp cụ thể? --> Sửa nguyên nhân, chạy lại
    |
    +-- Chưa rõ --> Chạy lại với -e
                        |
                        +-- Stack trace đủ giải thích? --> Sửa, chạy lại
                        |
                        +-- Cần hiểu cấu hình/dependency/plugin? --> -X trong môi trường được kiểm soát
                                                                  |
                                                                  v
                                                         Rà soát log, lọc dữ liệu,
                                                         chia sẻ đoạn cần thiết
```

| Hiện tượng | Bắt đầu với | Vì sao |
| --- | --- | --- |
| `cannot find symbol` ở `App.java:[5,28]` | Log mặc định | Compiler đã nói rõ vị trí và ký hiệu thiếu. |
| `NullPointerException` trong plugin nhưng không rõ chỗ gây ra | `-e` | Stack trace giúp định vị plugin/mã gọi. |
| `Could not resolve dependencies` và nghi mirror/profile/classpath | Log mặc định, sau đó `-X` nếu cần | Debug có thể cho biết thêm đường resolve và cấu hình. |
| Test fail với tên test/assertion rõ | Báo cáo test + log thường | Tránh ngập trong debug không liên quan. |
| Maven chạy với JDK khác dự kiến | `mvn -version`, sau đó `-X` nếu cần | Xác nhận JVM trước khi phân tích classpath/plugin. |
| Lỗi không tái hiện ở CI | So lệnh, JDK, profile, settings, biến môi trường đã **ẩn giá trị nhạy cảm** | Tìm khác biệt môi trường trước khi mở rộng log. |

Khi chạy lại để chẩn đoán, cố gắng giữ nguyên code, POM, profile, JDK và lệnh build; chỉ thêm `-e` hoặc `-X`. Nếu cùng lúc đổi nhiều thứ, khó biết vì sao kết quả thay đổi. Tuy nhiên, trong hệ thống sử dụng dependency snapshot, repository từ xa hay test không ổn định, kết quả có thể vẫn biến động; ghi lại môi trường để so sánh.

## 7. Dữ liệu nào có thể lộ trong log Maven?

`-X` tạo thêm quan sát về cấu hình thực tế. Các plugin Maven là mã có thể ghi log tùy ý. Vì thế, **không thể cam kết toàn bộ secret sẽ luôn được Maven hoặc plugin tự động che đi**. Các nhóm dữ liệu cần rà soát:

| Nhóm dữ liệu | Ví dụ có thể xuất hiện | Vì sao nhạy cảm |
| --- | --- | --- |
| Credential/secret | Token API, password repository, private key, cookie, header Authorization | Có thể cấp quyền truy cập hệ thống. |
| Cấu hình Maven | Một số tham số plugin, `-D...`, `settings.xml`, repository ID/URL | Có thể chứa giá trị cấu hình riêng hoặc secret nếu truyền sai cách. |
| Hạ tầng | Tên máy chủ nội bộ, host/proxy, port, đường dẫn server | Tiết lộ topology và tên dịch vụ nội bộ. |
| Định danh | User name trong `/home/<user>`, đường dẫn workspace, tên tài khoản | Có thể xác định người dùng hoặc nơi chứa dự án. |
| Mã và dữ liệu dự án | Artifact coordinates chưa công khai, đường dẫn module, test data, exception message | Có thể tiết lộ sản phẩm hoặc dữ liệu nghiệp vụ. |
| CI/CD | Dòng lệnh script, environment, đường dẫn artifact log, metadata job | Dễ lan truyền từ log terminal sang artifact và dịch vụ lưu trữ. |

Vấn đề không chỉ là dòng có `[DEBUG]`: một `[ERROR]` cũng có thể chứa URL riêng, tên người dùng hoặc thông tin phản hồi từ server. Stack trace của `-e` có thể tiết lộ đường dẫn tệp hoặc dữ liệu được plugin chèn vào message.

**Cảnh báo quan trọng về tùy chọn:** Không đặt token/password trực tiếp trong lệnh như `-Dtoken=GIÁ_TRỊ_BÍ_MẬT` vì shell history, danh sách tiến trình hoặc hệ thống CI có thể ghi lại đối số. Dùng secret store của CI và cơ chế cấp credential phù hợp của Maven/settings/plugin; vẫn kiểm tra xem plugin có vô tình in giá trị ra log không.

## 8. Rủi ro từ `settings.xml`, Maven Help Plugin và log hiệu lực

Maven có thể đọc cấu hình người dùng từ `~/.m2/settings.xml`, gồm server credentials, mirror, proxy và profile. Trong Maven, thông tin này phục vụ xác thực vào artifact repository và điều khiển cách resolve dependency; **không nên đính kèm nguyên bản `settings.xml` vào issue**.

Goal `help:effective-settings` có thể hiển thị settings đã hợp nhất. Theo tài liệu chính thức của Maven Help Plugin, tham số `showPasswords` mặc định là `false`, nghĩa là plugin cố gắng ẩn password trong kết quả. Dù vậy, không xem đây là **bảo đảm tất cả dữ liệu đều an toàn để công khai**: URL nội bộ và các thông tin khác vẫn có thể xuất hiện; plugin bên thứ ba cũng có cách logging riêng.

Tránh bật `showPasswords=true` để tạo bằng chứng hoặc gửi bug report. Không đăng giá trị trong `settings.xml`, `toolchains.xml`, biến môi trường hoặc Maven command-line properties lên nơi công khai nếu chúng chứa thông tin riêng. Khi cần kiểm tra cấu hình, chỉ trích xuất **phần không nhạy cảm** liên quan đến lỗi, ví dụ repository ID/mirror ID đã được thay bằng nhãn trung tính.

Nếu môi trường sử dụng Maven password encryption, đừng coi chuỗi password đã mã hóa là dữ liệu có thể tự do chia sẻ; bảo vệ cả file cấu hình và các khóa giải mã tương ứng.

## 9. Lưu log cục bộ mà không vô tình phát tán

Trong môi trường riêng, có thể dùng tham số Maven `-l` (hay `--log-file`) để ghi log ra file:

```bash
mvn -B -ntp -e -l maven-errors.log clean verify
```

Nếu cần debug sâu, chỉ bật trong môi trường có kiểm soát:

```bash
mvn -B -ntp -X -l maven-debug.log clean verify
```

`-l` ghi build output mà Maven quản lý vào file được chỉ định. Tên đường dẫn tương đối ở ví dụ là ngay thư mục thực thi. Các tiến trình hoặc công cụ ngoài Maven tự ghi file riêng có thể cần cơ chế thu thập riêng. **File log có thể chứa secret**, nên đừng tự động đẩy nó lên Git, phát hành dưới dạng artifact công khai hoặc gửi nguyên trạng trong chat.

Nếu log nằm trong thư mục dự án, có thể thêm các đường dẫn log chẩn đoán vào `.gitignore`, ví dụ:

```gitignore
/maven-errors.log
/maven-debug.log
```

`.gitignore` chỉ giảm nguy cơ **commit nhầm file chưa được Git theo dõi**; nó không bảo vệ file khỏi người khác có quyền đọc ổ đĩa, không xóa lịch sử nếu file đã được commit và không ngăn CI tự upload log. Với CI, hạn chế phạm vi quyền truy cập artifact, thời gian lưu và đối tượng được phép xem. Nên lưu bản đầy đủ ở vị trí riêng được phân quyền, chỉ chia sẻ bản đã rà soát.

Lưu ý: nếu dùng `mvn clean` rồi ghi log **trong thư mục `target/`**, plugin clean có thể xóa thư mục đó giữa lượt build; khi lưu bằng `-l`, nên đặt log ở thư mục không bị lifecycle clean xóa. Tránh đặt log trong thư mục build artifact có cơ chế publish tự động.

## 10. Quy trình rà soát và ẩn dữ liệu trước khi chia sẻ log

Hãy coi log debug là dữ liệu có thể nhạy cảm cho tới khi đã kiểm tra. Một quy trình thực tế:

1. **Tạo log trong môi trường tin cậy:** bật `-e` trước; chỉ bật `-X` nếu cần. Tránh bật thêm plugin logging quá chi tiết không phục vụ câu hỏi đang điều tra.
2. **Xác định đoạn cần gửi:** lệnh build sau khi đã che giá trị riêng, `BUILD FAILURE`, goal thất bại, thông báo lỗi nguyên nhân và vài dòng stack trace/DEBUG trực tiếp liên quan. Thường không cần toàn bộ log.
3. **Rà soát tất cả nơi có thể mang dữ liệu riêng:** dòng `-D...`, URL chứa userinfo/query token, headers, credential, file path, repository hostname, proxy, tên người dùng, environment, dữ liệu test và thông báo exception tùy biến.
4. **Thay giá trị thật bằng nhãn trung tính:** `[REDACTED_TOKEN]`, `[INTERNAL_REPO]`, `[LOCAL_PATH]`; cố gắng giữ cấu trúc lỗi có ích như `401`, loại exception, artifact coordinates đã được phép công bố.
5. **Đọc lại bản sắp gửi từ đầu tới cuối:** kiểm tra những giá trị xuất hiện nhiều lần, các ký tự đã URL-encode/base64, và stack trace nhiều tầng. Regex hoặc một tính năng mask tự động có thể bỏ sót; phải rà soát thủ công.
6. **Chỉ gửi qua kênh được phép:** nếu cần đầy đủ log chưa che để xử lý nội bộ, dùng nơi lưu và phân quyền phù hợp với chính sách của dự án, không dán vào issue công khai.

Ví dụ trích log đã ẩn dữ liệu:

```text
$ mvn -B -ntp -e clean verify
[INFO] --- compiler:3.13.0:compile (default-compile) @ maven-log-lab ---
[ERROR] [LOCAL_PATH]/src/main/java/example/App.java:[5,28] cannot find symbol
[ERROR]   symbol:   variable missingMessage
[ERROR]   location: class example.App
[ERROR] Failed to execute goal ...:compile ... : Compilation failure
[INFO] BUILD FAILURE
```

Bản này vẫn giữ **goal, tệp, dòng/cột và lỗi gốc**, nhưng bỏ đường dẫn tuyệt đối. Với lỗi repository, bản đã che có thể giữ thông điệp như `HTTP 401 from [INTERNAL_REPO]` để người nhận hiểu nhóm lỗi mà không lộ hostname hoặc token. Đừng chèn dữ liệu bí mật giả giống token thật trong ví dụ công khai.

### Nếu đã lỡ chia sẻ log chứa secret

Xử lý theo mức rủi ro thực tế: **thu hồi/đổi secret đã lộ**, hạn chế hoặc xóa bản log tại những nơi có thể, kiểm tra nơi log bị sao chép và audit việc sử dụng credential nếu phù hợp. Chỉ xóa một tin nhắn **không có nghĩa** mọi bản sao, cache hoặc lịch sử đã biến mất. Đưa việc xử lý secret vào quy trình bảo mật của tổ chức.

## 11. Diễn giải log debug mà không bị lạc trong tiếng ồn

Một cách đọc có cấu trúc:

- Bắt đầu từ `BUILD FAILURE` và xác định project bị lỗi. Trong reactor nhiều module, nhìn `Reactor Summary` để biết module nào SUCCESS/FAILURE/SKIPPED; đừng chỉ dựa vào module xuất hiện cuối log.
- Tìm dòng `--- plugin:version:goal (...) @ artifact ---` ngay trước cụm lỗi. Đây là điểm neo quan trọng để giới hạn vùng đọc.
- Trong cụm `[ERROR]`, chọn thông điệp **cụ thể đầu tiên có thể hành động**: tên tệp/dòng, tọa độ artifact, tên test, mã HTTP hoặc `Caused by` có ý nghĩa.
- Nếu đã bật `-e`, đọc chuỗi `Caused by` từ ngoài vào trong, chú ý tầng nguyên nhân sâu nhất **có liên quan tới sự cố**. Một exception sâu hơn không phải lúc nào cũng là hành động đúng nếu nó chỉ là lỗi tầng thấp chung.
- Khi bật `-X`, tìm theo project, plugin, `[DEBUG]` gần goal thất bại; có thể xác định classpath/configuration. Nhiều dòng DEBUG không liên quan là bình thường.
- Đối chiếu **chính xác lệnh và môi trường** giữa lần bình thường và lần có debug. `-X` không sửa classpath hay dependency, nhưng thời điểm tải remote artifact hoặc điều kiện ngoài có thể thay đổi giữa hai lần chạy.

Tránh các kết luận vội: `[ERROR] BUILD FAILURE` không có nghĩa Java compile lỗi; `ClassNotFoundException` trong plugin có thể do dependency/class realm của plugin chứ không phải mã ứng dụng; `401 Unauthorized` từ repository cần phân biệt thông tin xác thực, repository ID/mirror và quyền mạng; `test failed` nên xem báo cáo test trước.

## 12. Bài tập thực hành có đáp án

**Bài 1.** `mvn clean verify` báo `App.java:[5,28] cannot find symbol`. Có cần chạy `-X` ngay không?  
**Đáp án:** Không. Lỗi đã chỉ đúng vị trí và ký hiệu; sửa biến `missingMessage` trong mã Java trước.

**Bài 2.** Log Maven báo `Failed to execute goal`, plugin ném exception nhưng không rõ nguyên nhân. Bạn bật gì?  
**Đáp án:** Thử `-e` để có stack trace và tìm `Caused by`. Nếu vẫn cần điều tra cấu hình/plugin/dependency, cân nhắc `-X`.

**Bài 3.** `-X` có bảo đảm mask tất cả credential trước khi chia sẻ lên issue công khai không?  
**Đáp án:** Không. Core Maven và từng plugin có thể ghi nhiều loại thông tin; phải rà soát và ẩn dữ liệu thủ công, hạn chế nơi lưu log.

**Bài 4.** Tại sao không nên chạy `mvn -X -l target/debug.log clean verify` khi mục tiêu là giữ lại log?  
**Đáp án:** Lifecycle `clean` có thể xóa thư mục `target/` trong lúc build; nên đặt log ngoài vùng đầu ra bị dọn.

**Bài 5.** `.gitignore` đã có `/maven-debug.log`. Như vậy log chắc chắn không bị lộ?  
**Đáp án:** Không. Gitignore không ngăn người khác đọc file, không áp dụng cho file đã được Git theo dõi và không kiểm soát việc CI upload artifact.

**Bài 6.** Vì sao `mvn -q clean verify` không tốt cho việc học trình tự Maven chạy goal?  
**Đáp án:** Quiet ẩn phần lớn dòng INFO chứa dấu mốc goal; dùng log thường hoặc `-e` khi cần chẩn đoán.

**Bài 7.** Maven Help Plugin `help:effective-settings` mặc định ẩn password. Có thể gửi toàn bộ output công khai không?  
**Đáp án:** Không suy ra được. Output có thể còn chứa repository hostname, proxy, tên đường dẫn và cấu hình riêng; phải kiểm tra, che các trường nhạy cảm và tránh cố ý bật `showPasswords=true`.

**Bài 8.** Sau khi sửa `App.java`, cách xác nhận lỗi đã hết?  
**Đáp án:** Chạy lại `mvn -B -ntp clean verify` với cùng môi trường; kỳ vọng `BUILD SUCCESS`. Sau đó chạy `java -cp target/classes example.App` với mã đã sửa để kiểm tra stdout. Ví dụ thay `missingMessage` bằng chuỗi `"Log demo OK"` sẽ in `Log demo OK`.

## 13. Checklist khi điều tra lỗi thực tế

- [ ] Ghi nhận lệnh `mvn`/`mvnw`, Maven/JDK, project/module và goal thất bại.
- [ ] Đọc thông báo lỗi thường, tìm lỗi cụ thể trước khi tăng mức logging.
- [ ] Dùng `-e` khi cần stack trace của Maven/plugin; ghi lại chuỗi `Caused by` phù hợp.
- [ ] Dùng `-X` chỉ khi cần kiểm tra classpath, dependency resolution hoặc plugin configuration.
- [ ] Lưu bản log chi tiết trong vị trí được bảo vệ, tránh thư mục bị `clean` hoặc publish tự động.
- [ ] Trước khi chia sẻ, rà soát đường dẫn, URL, credential, `-D` properties, môi trường và dữ liệu test.
- [ ] Ẩn giá trị nhạy cảm, giữ lại bằng chứng chẩn đoán và đọc lại toàn bộ đoạn trích.
- [ ] Sau khi sửa, chạy lại cùng lệnh không bật debug để xác nhận build bình thường thành công.

## Tài liệu chính thức

- [Apache Maven 3.9.11 — Maven CLI Options Reference](https://maven.apache.org/ref/3.9.11/maven-embedder/cli.html): ý nghĩa `-e, --errors`, `-X, --debug`, `-l, --log-file`, `-q`, `-B`, `-ntp`.
- [Apache Maven Help Plugin — help:effective-settings](https://maven.apache.org/plugins/maven-help-plugin/effective-settings-mojo.html): cấu hình hiệu lực và tham số `showPasswords` mặc định là `false`.
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): phase, plugin goal và cách đọc kết quả build.

**Nguyên tắc cốt lõi:** đọc log thường trước, dùng `-e` để hiểu exception và `-X` để kiểm tra ngữ cảnh kỹ thuật sâu hơn. Log chi tiết là công cụ chẩn đoán có giá trị, đồng thời là dữ liệu phải được bảo vệ, giảm phạm vi và ẩn thông tin nhạy cảm trước khi chia sẻ.
