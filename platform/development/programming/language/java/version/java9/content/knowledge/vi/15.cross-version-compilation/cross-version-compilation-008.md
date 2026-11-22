# Kiểm thử bằng runtime đích sau khi biên dịch thành công

Biên dịch thành công chỉ xác nhận mã nguồn có thể được biên dịch với compiler, cấu hình và các thư viện đang có trong quá trình build. Điều đó chưa chứng minh chương trình có thể khởi động và hoạt động đúng trên môi trường Java sẽ triển khai. Bước kiểm thử bằng runtime đích xác nhận bytecode, thư viện phụ thuộc, cấu hình JVM và môi trường thực thi tương thích với nơi ứng dụng chạy thật.

Mục tiêu của bước này là chạy **đúng artifact đã build** bằng runtime mục tiêu, kiểm tra luồng chức năng quan trọng và phát hiện lỗi chỉ xuất hiện khi JVM nạp hoặc thực thi chương trình.

## 1. Phân biệt biên dịch và thực thi

Quá trình biên dịch và quá trình chạy kiểm tra hai nhóm điều kiện khác nhau:

| Giai đoạn | Thành phần chính | Điều được kiểm tra |
|---|---|---|
| Biên dịch | Compiler của JDK, ví dụ javac | Cú pháp, kiểu dữ liệu, khả năng truy cập API và khả năng tạo bytecode theo release được chọn |
| Thực thi | Lệnh java, JVM và thư viện runtime | Khả năng nạp, xác minh, liên kết và thực thi bytecode; khả năng tìm thư viện; cấu hình và tài nguyên của môi trường |

Khi chạy, JVM phải nạp các class, xác minh bytecode, liên kết các tham chiếu tới class và method, khởi tạo class rồi mới thực thi logic ứng dụng. Một chương trình có thể vượt qua bước biên dịch nhưng thất bại ở bất kỳ bước nào trong số này.

Các nguyên nhân thường gặp:

- **Sai phiên bản bytecode:** ứng dụng hoặc một dependency được biên dịch bằng release mới hơn khả năng runtime hỗ trợ. JVM có thể ném UnsupportedClassVersionError.
- **Thiếu class hoặc dependency:** classpath, module path hoặc gói triển khai không chứa thư viện cần thiết. Tùy cách nạp class, lỗi có thể là ClassNotFoundException hoặc NoClassDefFoundError.
- **API không tương thích:** mã được biên dịch với một phiên bản thư viện nhưng khi chạy lại nạp phiên bản khác không có method hoặc field đã được biên dịch tham chiếu. Lỗi thường gặp là NoSuchMethodError hoặc NoSuchFieldError.
- **Khác biệt môi trường:** cấu hình, biến môi trường, quyền truy cập file, chứng chỉ TLS, DNS, cổng mạng, locale, timezone hoặc giới hạn tài nguyên khác với môi trường build.
- **Thư viện native không phù hợp:** thiếu thư viện hệ điều hành hoặc sai kiến trúc CPU, có thể gây UnsatisfiedLinkError.

Vì vậy, kết quả biên dịch là điều kiện cần; chạy thử trên runtime đích mới xác nhận được khả năng tương thích khi thực thi.

## 2. Xác định runtime mục tiêu

Trước khi kiểm thử, cần ghi rõ môi trường mà ứng dụng phải hỗ trợ:

1. **Java feature release:** ví dụ Java 17 hoặc Java 21. Đây là phiên bản chính cần đối chiếu giữa compiler, bytecode và runtime.
2. **Bản phân phối JDK/runtime:** ghi nhận nhà cung cấp và bản cập nhật cụ thể nếu hệ thống phụ thuộc vào một bản phân phối nhất định.
3. **Hệ điều hành và kiến trúc:** ví dụ Linux x86_64, Linux ARM64 hoặc Windows x64.
4. **Cách đóng gói và khởi chạy:** executable JAR, ứng dụng modular, container image hoặc runtime image tùy biến.
5. **Tùy chọn JVM và cấu hình triển khai:** memory limits, system properties, environment variables, truststore, timezone và các tham số khởi động.

Nếu ứng dụng hỗ trợ nhiều Java release, hãy lập ma trận runtime được hỗ trợ và chạy kiểm thử trên từng release đó. Một lần chạy thành công trên máy phát triển không đại diện cho mọi runtime trong ma trận.

### Dùng --release khi biên dịch

Với compiler JDK hiện đại, tùy chọn **--release** là cách rõ ràng để chọn release mục tiêu. Ví dụ:

~~~bash
javac --release 21 -d out src/RuntimeSmokeTest.java
~~~

Tùy chọn này điều khiển mức ngôn ngữ Java được chấp nhận, phiên bản class file được tạo và tập API Java SE được phép tham chiếu cho release mục tiêu. Compiler phải là phiên bản có hỗ trợ release được chọn.

**--release không chạy chương trình.** Nó cũng không bảo đảm mọi thư viện bên thứ ba, native library, reflection, cấu hình hoặc dịch vụ bên ngoài tương thích với runtime mục tiêu. Các dependency vẫn cần được kiểm tra và kiểm thử trong môi trường thực thi thực tế.

## 3. Quy trình kiểm thử sau khi biên dịch

Một quy trình có thể lặp lại nên thực hiện theo thứ tự sau:

1. **Chốt release mục tiêu.** Ghi phiên bản Java, hệ điều hành, kiến trúc và cấu hình JVM mà ứng dụng cần hỗ trợ.
2. **Biên dịch theo release đó.** Dùng --release để kiểm soát bytecode và API Java SE được phép sử dụng.
3. **Xác nhận runtime thực sự được gọi.** Dùng đường dẫn tuyệt đối tới executable java của runtime mục tiêu hoặc cấu hình toolchain rõ ràng. Không chỉ dựa vào Java đầu tiên tìm thấy trong PATH.
4. **Chạy smoke test.** Khởi động ứng dụng hoặc một entry point nhỏ để xác nhận JVM có thể nạp và chạy bytecode.
5. **Chạy unit test và integration test.** Test process phải chạy trên runtime mục tiêu; kiểm tra phiên bản runtime ngay trong test log để xác nhận.
6. **Chạy artifact đã đóng gói.** Khởi chạy JAR hoặc gói triển khai bằng chính runtime mục tiêu. Kiểm tra cả cấu hình, dependency và tài nguyên được đóng gói.
7. **Lặp lại trên từng runtime được hỗ trợ.** Lưu lại phiên bản Java, hệ điều hành, kết quả test và log lỗi để có thể tái hiện.

Giữ nguyên artifact trong suốt các lượt kiểm thử giúp kết quả phản ánh đúng bytecode đã build. Nếu mỗi release cần một artifact riêng, hãy gắn nhãn rõ release tương ứng và kiểm thử đúng artifact đó.

## 4. Ví dụ smoke test kiểm tra runtime

Tạo file **src/RuntimeSmokeTest.java**:

~~~java
public final class RuntimeSmokeTest {
    public static void main(String[] args) {
        int actual = Runtime.version().feature();
        int expected = Integer.parseInt(
            System.getProperty("expected.java.feature", "21")
        );

        if (actual != expected) {
            throw new IllegalStateException(
                "Expected Java " + expected + " but running on Java " + actual
            );
        }

        System.out.println("Runtime feature: " + actual);
        System.out.println("Smoke test: PASS");
    }
}
~~~

Ví dụ này đọc feature release của JVM đang chạy và so sánh với release được yêu cầu. Nó giúp phát hiện trường hợp lệnh java trỏ nhầm sang một runtime khác. Đây là smoke test kiểm tra runtime; nó không thay thế test nghiệp vụ của ứng dụng.

Giả sử **BUILD_JDK_HOME** trỏ tới JDK dùng để build và **TARGET_JAVA_HOME** trỏ tới runtime Java 21 cần kiểm thử. JDK build phải hỗ trợ tùy chọn --release 21.

Trên Linux hoặc macOS:

~~~bash
mkdir -p out
"$BUILD_JDK_HOME/bin/javac" --release 21 -d out src/RuntimeSmokeTest.java
"$TARGET_JAVA_HOME/bin/java" -version
"$TARGET_JAVA_HOME/bin/java" -Dexpected.java.feature=21 -cp out RuntimeSmokeTest
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
& "$env:BUILD_JDK_HOME/bin/javac.exe" --release 21 -d out src/RuntimeSmokeTest.java
& "$env:TARGET_JAVA_HOME/bin/java.exe" -version
& "$env:TARGET_JAVA_HOME/bin/java.exe" -Dexpected.java.feature=21 -cp out RuntimeSmokeTest
~~~

Khi chạy chương trình bằng Java 21, stdout của chương trình là:

~~~text
Runtime feature: 21
Smoke test: PASS
~~~

Lệnh **java -version** cũng hiển thị thông tin runtime được gọi. Kết quả cụ thể phụ thuộc nhà cung cấp và bản cập nhật cài đặt. Nếu runtime thực tế không phải Java 21, smoke test sẽ dừng bằng IllegalStateException và nêu release mong đợi cùng release thực tế.

Trong dự án thực tế, có thể đặt kiểm tra này trong test setup hoặc log khởi động để ghi nhận runtime. Nếu chính sách sản phẩm cho phép nhiều release, hãy thay điều kiện bằng quy tắc hỗ trợ đã công bố, chẳng hạn kiểm tra runtime không thấp hơn release tối thiểu, rồi vẫn chạy test trên từng release cần hỗ trợ.

## 5. Kiểm thử artifact và dependency thực tế

Sau smoke test, hãy chạy ứng dụng theo cách nó được triển khai:

- Với executable JAR, dùng executable java của runtime đích để chạy **java -jar application.jar**.
- Với ứng dụng dùng classpath, bảo đảm toàn bộ dependency cần thiết có trong classpath và phiên bản được chọn đúng.
- Với ứng dụng modular, kiểm tra module path, module descriptor và các module cần thiết.
- Với ứng dụng dùng ServiceLoader hoặc reflection, kiểm thử đường nạp class và cấu hình provider thực tế.
- Với ứng dụng dùng JDBC, messaging, HTTP client hoặc SDK bên ngoài, chạy integration test với phiên bản dịch vụ và driver tương ứng với môi trường triển khai.

Đặc biệt cần kiểm tra dependency bắc cầu. Mã nguồn của ứng dụng có thể được biên dịch bằng --release 21 nhưng một thư viện đi kèm lại chứa class file cần runtime mới hơn. Trong trường hợp đó, ứng dụng vẫn có thể thất bại khi JVM nạp thư viện.

Các công cụ như **jdeps** hỗ trợ phân tích phụ thuộc tĩnh của JAR:

~~~bash
jdeps --multi-release 21 --ignore-missing-deps -summary application.jar
~~~

Kết quả giúp nhận diện các phụ thuộc tới package và module Java. Phân tích tĩnh không thay thế việc khởi chạy ứng dụng và kiểm thử các đường chạy thực tế.

## 6. Những nhóm hành vi cần kiểm tra

Phạm vi kiểm thử cần bám sát cách ứng dụng vận hành:

- **Khởi động và nạp class:** entry point, classpath/module path, cấu hình logging, dependency injection và ServiceLoader.
- **Luồng nghiệp vụ chính:** các thao tác đọc, ghi, xử lý dữ liệu và xử lý lỗi quan trọng.
- **Kết nối bên ngoài:** DNS, HTTP/TLS, database, message broker, proxy, chứng chỉ và timeout.
- **Hệ thống file:** đường dẫn, quyền đọc ghi, thư mục làm việc, file tạm và dung lượng đĩa.
- **Dữ liệu và môi trường:** encoding, locale, timezone, định dạng ngày giờ và system properties.
- **Tài nguyên JVM:** heap, memory limit của container, thread, GC, thời gian khởi động và hành vi shutdown.
- **Native integration:** thư viện native, kiến trúc CPU và các gói hệ điều hành cần thiết.
- **Vận hành:** health check, log, metrics, signal xử lý dừng ứng dụng và khả năng khởi động lại.

Một ứng dụng chỉ khởi động thành công vẫn có thể lỗi khi xử lý request, tải dữ liệu lớn, kết nối dịch vụ hoặc đóng tiến trình. Vì vậy, smoke test cần đi cùng unit test và integration test có đại diện cho các luồng sử dụng quan trọng.

## 7. Tích hợp vào Maven, Gradle và CI

### Maven

Có thể khai báo release mục tiêu trong cấu hình Maven Compiler Plugin:

~~~xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
~~~

Nếu compiler JDK và runtime dùng để chạy test khác nhau, hãy cấu hình toolchain cho compiler và test process một cách tường minh. Khi chạy test, ghi nhận Runtime.version() từ bên trong test để xác nhận JVM thực tế.

### Gradle

Có thể cấu hình Java toolchain và release biên dịch như sau:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 21
}
~~~

Java toolchain giúp Gradle chọn JDK phù hợp cho các task Java. Vẫn cần xác nhận runtime của test process và runtime triển khai, đặc biệt khi pipeline sử dụng nhiều JDK hoặc container khác nhau.

### CI pipeline

Trong CI, tạo job hoặc matrix theo từng runtime mục tiêu. Mỗi job nên:

1. In phiên bản và đường dẫn Java đang dùng.
2. Build artifact theo release đã khai báo.
3. Chạy unit test và integration test bằng runtime của job.
4. Chạy ứng dụng đã đóng gói bằng đúng runtime đó.
5. Lưu log, kết quả test và thông tin môi trường khi thất bại.

Nếu sản phẩm triển khai bằng container, hãy chạy test trên cùng base image hoặc image runtime tương đương với production. Nên cố định phiên bản image để lần chạy sau có thể tái hiện cùng môi trường.

## 8. Chẩn đoán lỗi thường gặp

| Dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| UnsupportedClassVersionError | Class của ứng dụng hoặc dependency được biên dịch cho release cao hơn runtime | Kiểm tra runtime đang chạy, release build và bytecode của dependency |
| ClassNotFoundException | Cơ chế nạp class không tìm thấy tên class được yêu cầu | Kiểm tra classpath, module path và cấu hình reflection |
| NoClassDefFoundError | JVM cần một class nhưng không thể nạp hoặc khởi tạo class đó | Kiểm tra dependency, lỗi khởi tạo trước đó và log đầy đủ |
| NoSuchMethodError hoặc NoSuchFieldError | Phiên bản class lúc chạy không tương thích với phiên bản lúc biên dịch | Kiểm tra dependency tree và phiên bản thư viện thực tế |
| UnsatisfiedLinkError | Thiếu native library hoặc binary không đúng hệ điều hành/kiến trúc | Kiểm tra thư viện native, đường dẫn nạp và kiến trúc CPU |
| Chỉ lỗi trên môi trường triển khai | Khác biệt cấu hình, quyền, network, TLS, timezone hoặc giới hạn tài nguyên | So sánh cấu hình và chạy test trong môi trường tương đương production |

Một số lệnh hỗ trợ xác định runtime và bytecode:

~~~bash
java -version
java -XshowSettings:properties -version
javap -verbose -classpath out RuntimeSmokeTest
~~~

Trong kết quả javap, trường **major version** cho biết phiên bản class file. Ví dụ, class file của Java 21 có major version 65. Đây là cách kiểm tra bytecode; việc chạy bằng runtime đích vẫn là bước xác nhận cuối cùng.

Trên Windows, có thể dùng **where.exe java** để xem các executable java tìm thấy trong PATH. Trên Linux hoặc macOS, dùng **command -v java**. Khi cần loại bỏ sự mơ hồ, gọi trực tiếp executable theo đường dẫn của runtime mục tiêu.

Khi điều tra lỗi, hãy lưu toàn bộ stack trace và thông tin runtime. Đừng chỉ dựa vào dòng lỗi cuối cùng: nguyên nhân gốc có thể nằm trong exception lồng bên trong hoặc ở lần khởi tạo class trước đó.

## 9. Checklist nghiệm thu

- [ ] Đã xác định Java release, bản phân phối, hệ điều hành và kiến trúc mục tiêu.
- [ ] Đã cấu hình compiler bằng --release phù hợp.
- [ ] Đã xác nhận executable java thực sự được dùng cho test.
- [ ] Smoke test xác nhận đúng runtime feature release.
- [ ] Unit test và integration test chạy trên runtime mục tiêu.
- [ ] Dependency trực tiếp và bắc cầu tương thích với release mục tiêu.
- [ ] Artifact đã đóng gói được khởi chạy bằng runtime mục tiêu.
- [ ] Đã kiểm tra cấu hình, kết nối, quyền hệ thống file và tài nguyên JVM liên quan.
- [ ] Đã chạy trên từng runtime trong ma trận hỗ trợ.
- [ ] Log và thông tin môi trường đủ để tái hiện lỗi.

**Tiêu chí hoàn thành:** artifact được biên dịch theo release đã chọn, chạy thành công trên runtime mục tiêu và vượt qua các test đại diện cho chức năng cùng môi trường triển khai. Kết quả phải gắn với phiên bản Java và môi trường cụ thể để có thể kiểm chứng lại.