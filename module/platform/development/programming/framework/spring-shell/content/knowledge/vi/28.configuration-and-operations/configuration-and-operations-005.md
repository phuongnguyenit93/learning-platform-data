# Giảm banner hoặc log khởi động khi cần đầu ra máy đọc

Khi chạy Spring Shell CLI bằng script hoặc tích hợp với một hệ thống khác, đầu ra của command đôi khi cần được máy đọc như JSON, CSV hoặc một dòng trạng thái. Banner ASCII, log khởi động và log debug có thể chen vào luồng dữ liệu, khiến parser không đọc được kết quả.

Spring Boot cung cấp các cấu hình riêng để điều khiển banner và thông tin khởi động. Logging framework lại có cấu hình mức log và nơi ghi log riêng. Cần phân biệt các lớp này để giảm phần hiển thị không cần thiết mà vẫn giữ được thông tin lỗi khi ứng dụng gặp sự cố.

## 1. Phân biệt banner, startup info và log ứng dụng

Ba nguồn đầu ra thường xuất hiện khi ứng dụng khởi chạy:

| Nguồn | Ví dụ | Cấu hình điều khiển |
|---|---|---|
| Spring Boot banner | Logo ASCII và phiên bản Spring Boot | **spring.main.banner-mode** |
| Thông tin khởi động | Tên ứng dụng, Java version, PID, active profiles | **spring.main.log-startup-info** |
| Log của framework và ứng dụng | **INFO**, **WARN**, **ERROR**, thông tin service | **logging.level.*** và cấu hình logging |

**spring.main.banner-mode** chỉ điều khiển banner của Spring Boot. Nó không xóa output do command tự in, prompt của terminal UI, hoặc log từ các thư viện khác.

Tương tự, **spring.main.log-startup-info=false** tắt phần startup information do **SpringApplication** ghi, bao gồm thông tin active profiles. Các logger khác vẫn có thể ghi log theo level đã cấu hình.

## 2. Tắt banner Spring Boot bằng application.yml

Để tắt banner khi chạy CLI, đặt **spring.main.banner-mode** thành **off**:

~~~yaml
spring:
  main:
    banner-mode: "off"
~~~

Trong YAML, cần đặt **off** trong dấu nháy. Một số bộ phân tích YAML coi từ **off** không có dấu nháy là giá trị boolean **false**, trong khi Spring Boot mong đợi một giá trị thuộc **Banner.Mode**.

Có thể dùng file **application.properties** thay thế:

~~~properties
spring.main.banner-mode=off
~~~

Spring Boot hỗ trợ ba chế độ:

| Giá trị | Hành vi |
|---|---|
| **console** | In banner ra **System.out** |
| **log** | Gửi banner qua logging system đã cấu hình |
| **off** | Không in banner |

Khi command phải trả JSON hoặc CSV trên stdout, **off** thường là lựa chọn phù hợp. Chế độ **log** vẫn tạo output qua logger và có thể xuất hiện trên console.

Nếu dự án có file **banner.txt** trong classpath, **spring.main.banner-mode=off** vẫn tắt việc in banner. **spring.banner.location** chỉ thay đổi vị trí đọc banner; nó không phải cấu hình tắt banner.

## 3. Giảm thông tin khởi động

Để không ghi thông tin khởi động và active profiles, đặt:

~~~yaml
spring:
  main:
    log-startup-info: false
~~~

Hoặc:

~~~properties
spring.main.log-startup-info=false
~~~

Thuộc tính này hữu ích khi script chỉ cần kết quả command. Nó không tắt toàn bộ logging và không thay thế cấu hình mức log.

Nếu ứng dụng vẫn cần thông tin chẩn đoán, có thể giữ startup info trong môi trường phát triển hoặc môi trường vận hành, rồi tắt riêng cho profile chạy tự động.

Ví dụ tạo file riêng **application-machine.yml**:

~~~yaml
spring:
  main:
    banner-mode: "off"
    log-startup-info: false
~~~

Khi profile **machine** được kích hoạt bằng **--spring.profiles.active=machine**, các thiết lập trong file này áp dụng cho lần chạy đó. Cách này giúp tách cấu hình dành cho script khỏi cấu hình interactive mặc định.

## 4. Đặt log level để giảm log console

Spring Boot cho phép cấu hình level theo logger bằng tiền tố **logging.level**:

~~~yaml
logging:
  level:
    root: ERROR
~~~

Với cấu hình trên:

- Log **ERROR** tiếp tục được ghi.
- Log **WARN**, **INFO**, **DEBUG** và **TRACE** bị loại khỏi root logger.
- Logger có level riêng có thể có hành vi khác tùy cấu hình kế thừa.

Có thể giảm log của framework nhưng vẫn giữ log nghiệp vụ ở mức cần thiết:

~~~yaml
logging:
  level:
    root: ERROR
    org.springframework: WARN
    com.example.admin: INFO
~~~

Ví dụ này vẫn cho phép package ứng dụng ghi **INFO**, vì vậy không thích hợp nếu stdout phải chứa duy nhất JSON hoặc CSV. Hãy chọn level dựa trên nơi nhận log và yêu cầu chẩn đoán.

Các level thường dùng:

| Level | Mục đích |
|---|---|
| **TRACE** | Chi tiết rất sâu, thường chỉ dùng khi điều tra |
| **DEBUG** | Thông tin phục vụ phát triển và gỡ lỗi |
| **INFO** | Sự kiện vận hành thông thường |
| **WARN** | Tình huống bất thường cần chú ý |
| **ERROR** | Lỗi khiến một thao tác hoặc thành phần thất bại |
| **OFF** | Tắt logger |

Không nên đặt **root: OFF** chỉ để làm sạch output máy đọc nếu vẫn cần nhận lỗi. Cấu hình **ERROR** hoặc chuyển log sang stderr/file thường giữ được khả năng chẩn đoán tốt hơn.

## 5. Kết hợp các cấu hình cho chế độ machine

Một cấu hình cơ bản cho command chạy tự động:

~~~yaml
spring:
  main:
    banner-mode: "off"
    log-startup-info: false

logging:
  level:
    root: ERROR
~~~

Trong **application.properties**:

~~~properties
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=ERROR
~~~

Kết hợp này tắt banner, giảm startup info và chỉ giữ log lỗi theo cấu hình root. Các thông báo do command chủ động ghi ra stdout vẫn xuất hiện; hãy bảo đảm command chỉ in dữ liệu mà script mong đợi.

## 6. Truyền cấu hình khi chạy JAR

Có thể đặt các thuộc tính Spring Boot bằng system property của JVM:

~~~bash
java \
  -Dspring.main.banner-mode=off \
  -Dspring.main.log-startup-info=false \
  -Dlogging.level.root=ERROR \
  -jar target/admin-cli.jar \
  report export --format json
~~~

Các tùy chọn **-D...** phải đứng trước **-jar**. Chúng được JVM đặt thành system properties trước khi Spring Boot tạo environment.

Có thể dùng biến môi trường:

~~~bash
SPRING_MAIN_BANNER_MODE=off \
SPRING_MAIN_LOG_STARTUP_INFO=false \
LOGGING_LEVEL_ROOT=ERROR \
java -jar target/admin-cli.jar report export --format json
~~~

Trong PowerShell:

~~~powershell
$env:SPRING_MAIN_BANNER_MODE = 'off'
$env:SPRING_MAIN_LOG_STARTUP_INFO = 'false'
$env:LOGGING_LEVEL_ROOT = 'ERROR'
java -jar "target/admin-cli.jar" report export --format json
~~~

Biến môi trường phù hợp với CI hoặc container vì có thể thay đổi theo môi trường triển khai mà không phải sửa JAR.

## 7. Cấu hình SpringApplication bằng Java

Nếu cần đặt chế độ này trực tiếp trong mã khởi động, tạo **SpringApplication** rồi cấu hình trước khi gọi **run**:

~~~java
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AdminCliApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(AdminCliApplication.class);

        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);
        application.run(args);
    }
}
~~~

**setBannerMode(Banner.Mode.OFF)** tắt banner. **setLogStartupInfo(false)** tắt thông tin khởi động do **SpringApplication** ghi. Log level vẫn cần cấu hình qua logging properties hoặc logging configuration.

Nếu dùng **SpringApplication.run(...)** trực tiếp, không có instance để tùy chỉnh trước khi chạy. Khi cần cấu hình lập trình, hãy tạo instance như ví dụ trên hoặc dùng **SpringApplicationBuilder**.

## 8. Giữ stdout sạch cho JSON hoặc CSV

Khi một chương trình khác đọc stdout, hãy xem stdout là luồng dữ liệu có hợp đồng. Không in banner, tiến độ, lời nhắc hoặc log vào giữa dữ liệu.

Một lệnh có thể ghi kết quả và chuyển stderr sang file:

~~~bash
java -jar target/admin-cli.jar report export --format json \
  > report.json \
  2> admin-cli.log
~~~

Lệnh chuyển hướng này chỉ tách được log nếu logging framework thực sự ghi log vào stderr. Nếu appender console đang ghi log vào stdout, **2>** không thể chuyển những dòng đó sang file.

Một cấu hình Logback có thể hướng log console sang **System.err** bằng **logback-spring.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <appender name="STDERR" class="ch.qos.logback.core.ConsoleAppender">
        <target>System.err</target>
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="WARN">
        <appender-ref ref="STDERR"/>
    </root>
</configuration>
~~~

Với cấu hình này, log **WARN** trở lên được ghi vào stderr; command có thể dùng stdout cho dữ liệu máy đọc. Nếu ứng dụng dùng Log4j2 hoặc JUL, hãy cấu hình appender/handler tương ứng thay vì sao chép XML Logback.

## 9. Ghi log vào file

Spring Boot hỗ trợ **logging.file.name** và **logging.file.path**:

~~~yaml
logging:
  file:
    name: logs/admin-cli.log
~~~

Thuộc tính **logging.file.name** thêm file output bên cạnh console output theo cấu hình mặc định. Chỉ đặt thuộc tính này không có nghĩa là log console đã bị tắt.

Nếu cần file-only logging, dùng cấu hình native của logging system. Với Logback, tạo **logback-spring.xml** và chỉ gắn file appender vào root logger; không thêm console appender. Có thể dùng rolling policy để giới hạn dung lượng và thời gian lưu log.

Chọn cách ghi log theo nhu cầu:

| Nơi ghi | Khi nên dùng |
|---|---|
| stderr | Cần giữ stdout sạch nhưng vẫn muốn thấy cảnh báo/lỗi trên terminal |
| File | Chạy batch hoặc CI cần lưu log để kiểm tra sau |
| Console stdout | Ứng dụng tương tác với người dùng và log không làm nhiễu dữ liệu |
| Không ghi log | Chỉ dùng trong trường hợp có cơ chế chẩn đoán khác và đã chấp nhận mất log |

## 10. Không nhầm banner với output của command

**spring.main.banner-mode=off** chỉ ngăn Spring Boot in banner lúc khởi động. Nếu command tự ghi các nội dung sau, chúng vẫn xuất hiện:

- **System.out.println(...)** hoặc **System.err.println(...)** trong mã ứng dụng.
- Thông báo tiến độ do service hoặc listener ghi ra.
- Prompt và nội dung terminal UI trong chế độ interactive.
- Kết quả định dạng mặc định của command hoặc result handler.

Khi xây dựng command có output máy đọc, nên tách phần tạo dữ liệu khỏi phần trình bày. Chỉ ghi JSON/CSV vào stdout; ghi tiến độ và thông tin chẩn đoán vào logger hoặc stderr.

Không trộn nội dung chẩn đoán vào JSON, ví dụ:

~~~text
Starting report export...
{"status":"ok","count":12}
~~~

Một parser JSON mong đợi một tài liệu JSON duy nhất sẽ thất bại khi dòng đầu tiên không phải JSON. Dòng tiến độ nên được ghi vào stderr hoặc file log.

## 11. Chạy non-interactive cho tác vụ tự động

Khi command được gọi từ cron, CI hoặc script, hãy chạy theo chế độ non-interactive và truyền đủ đối số cần thiết. Không để command chờ prompt nếu không có terminal tương tác.

Ví dụ:

~~~bash
java -jar target/admin-cli.jar report export \
  --format json \
  --output "build/reports/daily report.json"
~~~

Nếu command yêu cầu xác nhận, hãy cung cấp option rõ ràng như **--yes** hoặc **--force** theo thiết kế của command và kiểm tra quyền trước khi thực hiện thao tác nguy hiểm. Không dựa vào prompt ẩn trong script.

Trong Spring Shell 3.3.x trở lên, non-interactive runner được bật mặc định; interactive runner cần được bật rõ ràng khi muốn mở REPL. Dù runner nào được dùng, banner và logging vẫn do cấu hình Spring Boot và logging system điều khiển.

## 12. Kiểm tra output bằng redirect

Sau khi cấu hình, chạy command với stdout và stderr tách riêng:

~~~bash
java -jar target/admin-cli.jar report export --format json \
  > result.json \
  2> startup-and-error.log
~~~

Kiểm tra:

1. **result.json** bắt đầu bằng ký tự JSON hợp lệ, không có banner hoặc log.
2. Nội dung JSON parse được bằng công cụ như **jq**.
3. **startup-and-error.log** chỉ chứa log hoặc thông báo chẩn đoán.
4. Command trả mã thoát đúng cho trường hợp thành công và thất bại.

Ví dụ kiểm tra JSON:

~~~bash
jq . result.json
~~~

Nếu **jq** báo lỗi ngay đầu file, hãy xem những dòng đầu để xác định banner, log hoặc thông báo tiến độ nào còn đi vào stdout.

## 13. Kiểm thử cấu hình startup

Có thể kiểm tra trực tiếp bằng cách khởi chạy JAR trong tiến trình con và thu riêng hai luồng:

~~~java
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;

Path stdoutFile = Path.of("build", "test-output.txt");
Path stderrFile = Path.of("build", "test-error.txt");
java.nio.file.Files.createDirectories(stdoutFile.getParent());

Process process = new ProcessBuilder(
        "java",
        "-Dspring.main.banner-mode=off",
        "-Dspring.main.log-startup-info=false",
        "-Dlogging.level.root=ERROR",
        "-jar",
        "target/admin-cli.jar",
        "report",
        "export",
        "--format",
        "json"
).redirectOutput(stdoutFile.toFile())
 .redirectError(stderrFile.toFile())
 .start();

boolean finished = process.waitFor(30, TimeUnit.SECONDS);
if (!finished) {
    process.destroyForcibly();
    throw new IllegalStateException("CLI process timed out");
}

int exitCode = process.exitValue();
String stdout = java.nio.file.Files.readString(stdoutFile);
String stderr = java.nio.file.Files.readString(stderrFile);
~~~

Ví dụ này minh họa cách tách stream và giới hạn thời gian chờ. Trong test thực tế, hãy xác nhận stdout parse được thành JSON, stderr chứa lỗi cần thiết khi thất bại, và exit code phản ánh kết quả command.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Banner vẫn xuất hiện | Property không được nạp hoặc cấu hình bị ghi đè | Kiểm tra profile, biến môi trường và **spring.main.banner-mode** |
| YAML báo sai kiểu banner mode | Viết **off** không có dấu nháy | Dùng **banner-mode: "off"** |
| Tắt banner nhưng vẫn có log Starting... | Chỉ tắt banner | Đặt thêm **spring.main.log-startup-info=false** |
| Vẫn thấy log INFO | Chưa cấu hình logger level | Đặt **logging.level.root** hoặc level theo package |
| Không còn thấy lỗi khi chạy script | Đặt root level thành **OFF** hoặc tắt logging quá rộng | Giữ **ERROR** và chuyển log sang stderr/file |
| Redirect **2>** nhưng log vẫn nằm trong file JSON | Console appender ghi vào stdout | Cấu hình appender sang **System.err** |
| **logging.file.name** vẫn có log trên console | Thuộc tính này thêm file output, không tắt console | Dùng custom file-only logging config nếu cần |
| JSON có thêm dòng tiến độ | Command hoặc service tự in thông báo | Chuyển tiến độ sang stderr/logger |
| Log active profiles vẫn xuất hiện | Startup info chưa bị tắt hoặc logger khác ghi lại | Kiểm tra **spring.main.log-startup-info** và logger tương ứng |
| Output thay đổi giữa các profile | Mỗi profile có logging config khác nhau | Kiểm tra cấu hình đã được nạp cho profile đang chạy |
| Log debug tăng đột ngột | Truyền **--debug** hoặc **debug=true** | Bỏ debug flag trong lệnh chạy máy đọc |

## 15. Checklist cho đầu ra máy đọc

Trước khi tích hợp CLI với script hoặc pipeline, kiểm tra:

1. Banner Spring Boot được tắt bằng **spring.main.banner-mode: "off"** nếu không cần.
2. Startup information được tắt khi không cần bằng **spring.main.log-startup-info=false**.
3. Log level được cấu hình để vẫn giữ lỗi cần chẩn đoán.
4. stdout chỉ chứa dữ liệu command theo hợp đồng.
5. Log và thông báo tiến độ được ghi vào stderr hoặc file.
6. Không nhầm **logging.file.name** với chế độ file-only.
7. Command không yêu cầu prompt khi chạy non-interactive.
8. Không bật **--debug** hoặc **--trace** trong pipeline thông thường.
9. JSON/CSV được kiểm tra bằng parser thực tế.
10. Exit code được kiểm tra riêng cho thành công và thất bại.

## 16. Bài tập thực hành

Tạo command **report export --format json** trả về dữ liệu báo cáo ở dạng JSON:

1. Cấu hình **spring.main.banner-mode** thành **"off"**.
2. Cấu hình **spring.main.log-startup-info=false**.
3. Đặt root log level thành **ERROR**.
4. Chuyển log console sang stderr bằng **logback-spring.xml**.
5. Chạy JAR và redirect stdout vào **report.json**, stderr vào **report.log**.
6. Dùng **jq** hoặc một parser JSON để xác nhận file stdout là JSON hợp lệ.
7. Tạo tình huống lỗi và xác nhận thông báo lỗi vẫn xuất hiện ở stderr.
8. Xác nhận exit code khác **0** khi export thất bại.
9. Chạy lại ở chế độ tương tác và so sánh prompt/output với chế độ non-interactive.

Sau bài tập, hãy giải thích được vì sao tắt banner, tắt startup info và chuyển logger sang stderr là ba thao tác riêng biệt.

## Tài liệu tham khảo

- [Spring Boot 3.5 – SpringApplication và Banner](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html)
- [Spring Boot 3.5 – Logging](https://docs.spring.io/spring-boot/3.5/reference/features/logging.html)
- [Spring Boot 3.5 – Logging How-to](https://docs.spring.io/spring-boot/3.5/how-to/logging.html)
- [Spring Boot 3.5 API – SpringApplication](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/SpringApplication.html)
- [Logback – ConsoleAppender](https://logback.qos.ch/manual/appenders.html#ConsoleAppender)
