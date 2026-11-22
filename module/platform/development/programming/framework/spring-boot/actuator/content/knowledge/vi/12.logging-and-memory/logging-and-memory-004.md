# Sử dụng endpoint logfile khi ứng dụng đã cấu hình tệp log

Khi điều tra một lỗi trên ứng dụng Spring Boot đang chạy, người vận hành có thể cần đọc những thông điệp đã được ghi vào tệp log. Endpoint `logfile` của Actuator cung cấp một đường HTTP để đọc nội dung tệp log mà ứng dụng đã xác định.

Để sử dụng được, cần có đủ ba phần: **ứng dụng thực sự ghi ra một tệp → Actuator xác định được tệp cần đọc → người gọi được phép truy cập endpoint**. Chỉ thêm `logfile` vào danh sách exposure chưa làm một ứng dụng chỉ ghi console tự có tệp log.

Bài này sử dụng **Java 21, Spring Boot 3.3.13, Spring MVC và cấu hình Logback mặc định của starter**. Các lệnh HTTP đọc toàn bộ tệp hoặc một vùng byte; chúng không tạo luồng theo dõi liên tục những dòng mới.

## 1. Endpoint này đọc dữ liệu gì?

Với một ứng dụng đã có tệp log:

```text
Lời gọi logger
    ↓
Bộ ghi ra tệp (file appender)
    ↓
Tệp log trên hệ thống tệp của tiến trình
    ↓
GET /actuator/logfile
    ↓
Nội dung tệp gửi trong HTTP response
```

Body là dữ liệu tệp, thường là văn bản log. Đây không phải một đối tượng JSON mô tả logger hoặc mức log.

Các ranh giới cần nhớ:

| Nhu cầu | Khả năng của `logfile` |
| --- | --- |
| Đọc tệp log đã được xác định | Có |
| Đọc một phần theo vị trí byte | Có trên Spring MVC của ví dụ |
| Tự biến stdout của mọi tiến trình thành tệp | Không |
| Tự tìm và hợp nhất log của mọi bản sao ứng dụng | Không |
| Tự nối toàn bộ tệp đã xoay vòng và tệp nén | Không |
| Giữ kết nối chờ những dòng log mới như `tail -f` | Không |
| Chọn tùy ý tệp trên máy bằng tham số đường dẫn | Không phải giao diện của endpoint chuẩn |

Thông điệp phải được ghi tới tệp đã chọn thì mới xuất hiện trong dữ liệu đọc được. Một dòng in trực tiếp ra console hoặc được gửi vào đích khác có thể không nằm trong tệp đó.

Cấu trúc HTTP chính thức: [Log File endpoint — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/logfile.html).

## 2. Cấu hình tệp log và cấu hình exposure là hai việc riêng

### 2.1. Chọn tệp với cấu hình logging mặc định

Spring Boot mặc định ghi console. Để ghi thêm ra tệp với cấu hình logging mặc định, có thể dùng một trong hai thuộc tính:

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `logging.file.name` | Chỉ định tên hoặc đường dẫn đầy đủ tới tệp | `logs/application.log` |
| `logging.file.path` | Chỉ định thư mục; tên tệp mặc định là `spring.log` | `logs` |

Ví dụ chỉ định một tệp:

```yaml
logging:
  file:
    name: logs/application.log
```

Ví dụ thay thế, chỉ định thư mục:

```yaml
logging:
  file:
    path: logs
```

Trong trường hợp thứ hai, tệp là `logs/spring.log`. Nếu đặt cả `logging.file.name` và `logging.file.path`, Spring Boot dùng `name` và bỏ qua `path`; không tự ghép hai thuộc tính thành một đường dẫn mới.

Đường dẫn tương đối được tính từ **thư mục làm việc của tiến trình**, không mặc nhiên từ thư mục chứa JAR hoặc từ thư mục module trong mã nguồn. Một IDE, một dịch vụ hệ điều hành và một container có thể khởi chạy cùng JAR từ những thư mục làm việc khác nhau.

Tham chiếu: [Spring Boot Logging — File Output](https://docs.spring.io/spring-boot/3.3/reference/features/logging.html#features.logging.file-output).

### 2.2. Cho phép truy cập endpoint qua HTTP

Thêm endpoint vào danh sách cho phép:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,logfile
```

Với Spring Boot 3.3, nếu chính sách ứng dụng đã tắt endpoint mặc định hoặc tắt riêng `logfile`, cần bật lại có chủ đích:

```properties
management.endpoint.logfile.enabled=true
```

Kích hoạt và exposure vẫn chưa thay thế cho kiểm soát truy cập. Người gọi còn phải tới được đúng cổng, đúng đường dẫn và có quyền đọc nếu ứng dụng được bảo vệ.

Nếu có `management.endpoints.web.exposure.exclude`, kiểm tra cả danh sách đó vì `exclude` thắng `include`.

### 2.3. Tệp phải tồn tại và đọc được

Ở thời điểm gọi endpoint, xác minh:

- Tiến trình đã thực sự tạo hoặc mở đúng tệp.
- Tài khoản chạy ứng dụng có quyền đọc đường dẫn đó.
- Tệp nằm trong hệ thống tệp hoặc volume mà tiến trình nhìn thấy.
- Một cấu hình logging tùy chỉnh không chuyển thông điệp sang tệp khác.

Cấu hình endpoint thành công không bảo đảm nội dung tệp luôn tồn tại trong mọi thời điểm. Việc xoay vòng, đổi volume hoặc thay đổi quyền có thể làm một lần đọc sau có kết quả khác lần đọc trước.

## 3. Ví dụ chạy độc lập

Tạo dự án riêng:

```text
actuator-logfile-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── learning/
        │       └── actuator/
        │           └── LogfileDemoApplication.java
        └── resources/
            └── application.yml
```

Cần JDK 21 và Maven 3.6.3 trở lên. Lần đóng gói đầu cần kết nối kho Maven để tải phụ thuộc.

### 3.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>learning</groupId>
    <artifactId>actuator-logfile-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 3.2. `src/main/java/learning/actuator/LogfileDemoApplication.java`

```java
package learning.actuator;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class LogfileDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(LogfileDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner writeExampleMessages() {
        return args -> {
            Logger logger = LoggerFactory.getLogger("demo.filelog");
            logger.info("FILE_DEMO started");
            logger.warn("FILE_DEMO completed");
        };
    }
}
```

Runner tạo hai thông điệp bằng logger tên `demo.filelog`. Đây là chương trình đầy đủ; không cần thêm controller nghiệp vụ để sử dụng endpoint Actuator có sẵn.

### 3.3. `src/main/resources/application.yml`

```yaml
server:
  address: 127.0.0.1
  port: 18083

spring:
  main:
    banner-mode: "off"

management:
  endpoints:
    web:
      exposure:
        include: health,logfile

logging:
  file:
    name: logs/application.log
  level:
    root: WARN
    demo.filelog: INFO
  pattern:
    console: "%msg%n"
    file: "%msg%n"
```

Trong thí nghiệm:

- Tệp log là `logs/application.log` dưới thư mục làm việc.
- Logger minh họa được bật từ `INFO`; logger gốc ở `WARN` để giảm log khởi động không liên quan.
- Pattern chỉ giữ nội dung thông điệp, giúp đối chiếu file và HTTP body dễ dàng.
- Máy chủ lắng nghe loopback tại `127.0.0.1:18083`.

Ví dụ không thêm Spring Security để tập trung vào thao tác trên máy cá nhân. Khi triển khai thật, endpoint đọc tệp log cần đi qua kiểm soát mạng, xác thực và quyền đọc phù hợp.

### 3.4. Đóng gói và chạy

Tại thư mục chứa `pom.xml`:

```shell
mvn clean package
java -jar target/actuator-logfile-demo-1.0.0.jar
```

Nếu cổng `18083` đã được dùng, chọn cổng khác bằng đối số `--server.port` và đổi URL kiểm tra.

Đảm bảo không có cấu hình ngoài, biến môi trường hoặc đối số khác ghi đè `logging.file.name`, mức log hay exposure của thí nghiệm.

Hai thông điệp do runner ghi là:

```text
FILE_DEMO started
FILE_DEMO completed
```

Với lần chạy đầu trong thư mục mới, không có cảnh báo môi trường bổ sung, đó cũng là nội dung minh họa trong tệp log. Nếu chạy lại, cấu hình ghi nối tiếp có thể giữ cả các dòng từ lần chạy trước; không kỳ vọng tệp tự rỗng khi khởi động JAR.

Pattern tối giản chỉ phục vụ kiểm chứng. Trong vận hành thực tế, thường cần giữ thời gian, mức log, tên logger và thông tin tương quan phù hợp để truy vết.

## 4. Đọc hoặc tải nội dung tệp

Mở terminal thứ hai trong khi ứng dụng đang chạy:

```shell
curl -i "http://127.0.0.1:18083/actuator/logfile"
```

Trên Windows PowerShell, dùng `curl.exe` nếu `curl` đang là bí danh của lệnh PowerShell.

Một lần đọc toàn bộ tệp thành công trả `200 OK`. Trong ví dụ, body là văn bản log; phản hồi có kiểu nội dung `text/plain` và hỗ trợ phạm vi byte qua `Accept-Ranges: bytes`.

Các header như ngày giờ và độ dài phụ thuộc lần chạy. Ký tự xuống dòng cũng có thể khác giữa hệ điều hành, nên không dùng số ký tự nhìn thấy để tự suy ra mọi giá trị `Content-Length`.

### Lưu body vào tệp cục bộ

```shell
curl --fail --output downloaded-application.log "http://127.0.0.1:18083/actuator/logfile"
```

Tệp `downloaded-application.log` được tạo tại máy gọi HTTP. Nó là kết quả tải về; tệp nguồn trên máy chủ vẫn là `logs/application.log`.

Nếu cần lưu riêng cả header và body:

```shell
curl --fail --dump-header logfile-response.headers --output downloaded-application.log "http://127.0.0.1:18083/actuator/logfile"
```

Không thêm `-i` khi cần body thuần trong tệp tải về, vì tùy chọn đó đưa cả header vào luồng output. Kiểm tra mã thoát của công cụ và mã phản hồi trước khi coi một lần tải là thành công.

Một máy khách luôn kỳ vọng JSON cần được điều chỉnh cho phản hồi văn bản này. Tránh đưa nội dung log qua bộ phân tích JSON.

## 5. Đọc một phần tệp bằng HTTP Range

Tệp log production có thể lớn. Khi chỉ cần một đoạn, gửi header `Range` để giới hạn vùng byte cần lấy thay vì tải toàn bộ tệp lặp lại.

### 5.1. Lấy chín byte đầu để kiểm chứng

```shell
curl -i -H "Range: bytes=0-8" "http://127.0.0.1:18083/actuator/logfile"
```

Vị trí bắt đầu từ `0`, cả hai đầu đều được tính vào phạm vi: `0-8` là **9 byte**.

Với tệp minh họa bắt đầu bằng `FILE_DEMO started`, body là chuỗi ASCII `FILE_DEMO`. Một phản hồi phạm vi thành công trả `206 Partial Content`.

Các header cần đọc:

| Header | Ý nghĩa |
| --- | --- |
| `Accept-Ranges: bytes` | Tài nguyên hỗ trợ yêu cầu theo phạm vi byte |
| `Content-Range` | Vùng byte đã trả và tổng kích thước được báo cáo |
| `Content-Length` | Số byte trong phần body được gửi cho lần đáp ứng đó |

Không đọc `Content-Length` của phản hồi `206` như kích thước toàn bộ tệp. Tổng kích thước được thể hiện trong `Content-Range` khi có thông tin đó.

### 5.2. Lấy một khối đầu hoặc một khối cuối

Lấy tối đa 1024 byte đầu:

```shell
curl -i -H "Range: bytes=0-1023" "http://127.0.0.1:18083/actuator/logfile"
```

Lấy tối đa 4096 byte cuối:

```shell
curl -i -H "Range: bytes=-4096" "http://127.0.0.1:18083/actuator/logfile"
```

Một dạng khác là lấy từ một vị trí đến cuối:

```text
Range: bytes=1024-
```

Dạng này chỉ hợp lệ khi điểm bắt đầu phù hợp với tài nguyên. Với tệp minh họa rất nhỏ, vị trí `1024` đã nằm ngoài tệp; không dùng nó rồi kỳ vọng luôn có một phần dữ liệu.

Nếu tệp ngắn hơn số byte yêu cầu ở cuối, không tự giả định body vẫn có đúng 4096 byte. Đọc header và số byte thực tế.

### 5.3. Range không phải số dòng

`bytes=-4096` có nghĩa lấy một phần cuối theo **byte**, không phải 4096 dòng, 4096 ký tự hoặc mọi thông điệp trong một khoảng thời gian.

Một điểm cắt có thể rơi:

- Giữa một dòng log.
- Giữa các byte của một ký tự UTF-8.
- Giữa một stack trace gồm nhiều dòng.

Vì vậy phần đầu của body có thể là một dòng không đầy đủ hoặc một đoạn ký tự không giải mã độc lập được. Khi xử lý văn bản, cần cân nhắc ranh giới mã hóa và ranh giới dòng; không coi một khối byte tùy ý là tập bản ghi log hoàn chỉnh.

Trong thí nghiệm dùng ASCII, `bytes=0-8` dễ đối chiếu vì từng ký tự của `FILE_DEMO` có một byte. Quy tắc đó không áp dụng chung cho tiếng Việt.

### 5.4. Phạm vi không đáp ứng được

Thử một vị trí rất xa ngoài tệp nhỏ của ví dụ:

```shell
curl -i -H "Range: bytes=999999999-" "http://127.0.0.1:18083/actuator/logfile"
```

Với Spring MVC của thí nghiệm, phản hồi là `416 Range Not Satisfiable`; `Content-Range` báo dạng phạm vi không đáp ứng được cùng kích thước tài nguyên.

Đó là lỗi lựa chọn vùng byte, không tự đồng nghĩa ứng dụng không còn ghi log. Đọc lại kích thước hoặc lấy một vùng phù hợp. Nếu tệp đã bị xoay vòng hoặc thu nhỏ, offset lấy từ một lần gọi cũ có thể không còn dùng được.

Cần kiểm tra mã phản hồi thực tế: một proxy ở giữa có thể làm thay đổi việc chuyển tiếp hoặc xử lý `Range`. Không xử lý một body toàn tệp trả về bằng `200` như thể chắc chắn nó là mảnh kế tiếp của lần tải trước.

Tài liệu Spring Boot cũng ghi rõ đọc một phần tệp bằng cách này không được hỗ trợ khi dùng Jersey. Ví dụ trong bài sử dụng Spring MVC, không phải Jersey.

## 6. Khi tệp được tạo ngoài cấu hình logging mặc định

Một ứng dụng có thể ghi log bằng cấu hình backend tùy chỉnh hoặc được hệ điều hành chuyển hướng output vào một tệp. Khi Actuator không thể xác định đúng tệp qua `logging.file.name` hoặc `logging.file.path`, Spring Boot 3.3 có thuộc tính:

```yaml
management:
  endpoint:
    logfile:
      external-file: /var/log/my-service/service.log
```

Đây là ví dụ cấu hình bổ sung cho một hệ thống có tệp tại đường dẫn đó. Phải tiếp tục có exposure, quyền truy cập HTTP và quyền đọc hệ thống tệp phù hợp.

`external-file` xác định **tệp mà endpoint đọc**. Nó không tự tạo file appender, chuyển stdout sang tệp hoặc thay đích ghi của mọi logger. Cơ chế tạo tệp cần được cấu hình riêng và phải đang hoạt động.

Khi vừa có `external-file` vừa có `logging.file.name`, endpoint sử dụng tệp ngoài đã chỉ định. Kết quả là ứng dụng có thể đang ghi vào một tệp nhưng endpoint lại đọc tệp khác nếu người triển khai cấu hình không nhất quán.

Trong ví dụ chạy độc lập, không cần `external-file`: `logging.file.name=logs/application.log` đã đủ để Actuator xác định tệp.

Tham chiếu thuộc tính: [Common Application Properties — management.endpoint.logfile.external-file](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html#application-properties.actuator.management.endpoint.logfile.external-file).

### Endpoint không phải trình duyệt hệ thống tệp

Đường dẫn đọc do cấu hình phía máy chủ quyết định. API chuẩn không định nghĩa thao tác chọn một tệp bất kỳ bằng URL như:

```text
/actuator/logfile?file=some-other.log
```

Không xây công cụ vận hành dựa trên giả định rằng tham số này đổi tệp nguồn. Trong Spring MVC của thí nghiệm, tham số không được định nghĩa đó không làm thay đổi tài nguyên đọc.

Nếu cần điều tra một tệp lưu trữ khác, dùng công cụ và quyền truy cập được thiết kế cho nhiệm vụ đó; không biến endpoint thành một giao diện nhận đường dẫn tùy ý từ người gọi.

## 7. Hiểu đúng dữ liệu khi log tiếp tục tăng hoặc được xoay vòng

### 7.1. Mỗi lần gọi là một lần đọc tệp

Sau khi một yêu cầu kết thúc, kết nối không tiếp tục gửi những dòng mới được ghi sau đó. Muốn quan sát lại phải có yêu cầu khác hoặc dùng hệ thống theo dõi log chuyên dụng.

Tệp đang được ghi có thể thay đổi giữa hoặc trong các lần đọc. Một chuỗi yêu cầu Range không mặc nhiên tạo ra ảnh chụp bất biến của cùng một phiên bản tệp.

Khi cần bằng chứng ổn định cho một thời điểm điều tra, dùng quy trình tạo bản sao hoặc snapshot phù hợp tại hệ thống nguồn, rồi ghi nhận thời điểm, bản sao ứng dụng và nguồn tệp.

### 7.2. Xoay vòng thay đổi tài nguyên cần quan sát

Khi logging backend xoay vòng, tệp hiện hành có thể được đổi tên, chuyển sang tệp lưu trữ hoặc thay bằng một tệp mới tại cùng đường dẫn.

Endpoint đọc tài nguyên đã cấu hình; nó không tự hợp nhất `application.log`, các tệp ngày cũ và tệp `.gz` thành một lịch sử liền mạch.

Do đó:

- Số byte hiện tại không nhất thiết lớn hơn lần trước.
- Offset đã dùng có thể trỏ sang nội dung khác hoặc nằm ngoài tệp mới.
- Một đoạn cuối đọc được có thể thuộc tệp hiện hành mới, chưa chứa lỗi xảy ra trước lần xoay vòng.
- Ghép mù quáng các mảnh tải ở những thời điểm khác nhau có thể tạo dữ liệu trùng hoặc thiếu.

Thiết kế việc lấy log theo cách xoay vòng của hệ thống. Endpoint thuận tiện để đọc tệp hiện hành, còn tìm kiếm lịch sử qua nhiều tệp thường phù hợp hơn với kho log tập trung hoặc công cụ lưu trữ đã được cấp quyền.

## 8. Sử dụng trong production

Tệp log có thể chứa token, thông tin cá nhân, chuỗi kết nối, nội dung yêu cầu, stack trace hoặc dữ liệu nội bộ được ghi ngoài ý muốn. Khi cho đọc tệp, phải xét **toàn bộ nội dung có thể đã được ghi**, không chỉ những thông điệp mới nhất.

Chính sách che giá trị của `env` hoặc `configprops` không tự che nội dung văn bản của `logfile`. Đặt `show-values=never` cho những endpoint đó không làm tệp log trở thành dữ liệu đã được khử nhạy cảm.

Một cách vận hành phù hợp cần xác định:

- Vai trò hoặc tài khoản nào được đọc log, qua kênh mạng nào.
- Endpoint có được công bố thường trực hay chỉ trong một nhiệm vụ điều tra.
- Mỗi lần cần đọc bao nhiêu dữ liệu; có thể dùng Range để giới hạn phạm vi tải hay không.
- Ai được giữ bản tải về, ở đâu và trong bao lâu.
- Cách theo dõi truy cập và đóng lại quyền khi nhiệm vụ hoàn tất.

Với ứng dụng có Spring Security, phải bảo vệ đúng endpoint và chuỗi bảo mật thực tế. Danh sách exposure chỉ chọn khả năng công bố; nó không cấp một mô hình phân quyền hoàn chỉnh.

Tải toàn bộ một tệp lớn lặp lại có thể tốn I/O, băng thông và tài nguyên ở máy gọi. Range giảm phần dữ liệu cần truyền khi được hỗ trợ; nó không thay thế cho chính sách dung lượng và quyền đọc.

Tham chiếu về kích hoạt, exposure và bảo vệ endpoint: [Actuator Endpoints — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

### Trường hợp container chỉ ghi stdout

Nếu kiến trúc triển khai chủ đích chỉ ghi stdout và nền tảng đã thu thập log, dùng cơ chế đọc log của nền tảng hoặc kho tập trung. Không cần tạo thêm tệp chỉ để có endpoint này.

Khi hệ thống đã chọn ghi tệp, xác minh đường dẫn volume, quyền của tài khoản tiến trình và vòng đời lưu trữ. Tệp bên trong container có thể không ở cùng vị trí với tệp trên máy chủ và có thể mất khi container được thay thế nếu không được lưu bền theo thiết kế.

### Trường hợp nhiều bản sao ứng dụng

Mỗi bản sao có thể có tệp cục bộ riêng. Hai lần gọi cùng URL qua load balancer có thể đọc log của hai bản sao khác nhau.

Muốn liên kết với một sự cố, ghi rõ nguồn bản sao và thời điểm. Không suy ra “không có lỗi trong hệ thống” chỉ vì một tệp của một bản sao không chứa dòng đang tìm.

## 9. Chẩn đoán khi không đọc được tệp mong đợi

| Hiện tượng | Cách kiểm tra |
| --- | --- |
| Chỉ thấy log trên console, endpoint không có dữ liệu | Đã cấu hình ghi tệp hoặc chọn một `external-file` hợp lệ chưa? |
| `404` khi gọi `logfile` | Kiểm tra đường dẫn HTTP, trạng thái kích hoạt, exposure, cấu hình tệp và sự tồn tại của tài nguyên |
| `401` hoặc `403` | Kiểm tra tài khoản, vai trò và chính sách truy cập |
| `416` khi gửi Range | Kiểm tra offset, kích thước hiện tại và việc xoay vòng |
| Có body nhưng không thấy thông điệp mới | Kiểm tra đúng tệp, đúng bản sao, mức log, đích ghi và độ trễ flush nếu có |
| Body là nội dung cũ hoặc khác tệp đang xem trên máy | Kiểm tra thư mục làm việc, `external-file`, volume và cấu hình ghi đè |
| Dữ liệu một phần có ký tự lạ hoặc thiếu đầu dòng | Kiểm tra ranh giới byte, UTF-8 và ranh giới dòng |
| Nhận lỗi đọc hoặc lỗi máy chủ | Kiểm tra quyền hệ thống tệp, lỗi I/O, mount và log vận hành qua kênh khác |
| Công cụ báo lỗi phân tích JSON | Endpoint trả nội dung tệp; chọn cách xử lý văn bản hoặc byte phù hợp |

Với cấu hình đã kiểm chứng trong ví dụ, chỉ thêm exposure mà không chọn tệp log không làm xuất hiện endpoint có dữ liệu đọc. Khi cấu hình tệp ngoài trỏ tới tài nguyên không tồn tại, yêu cầu đọc trả `404`.

Không dùng riêng một mã `404` để kết luận nguyên nhân chính xác. Lỗi URL, endpoint chưa khả dụng và tài nguyên tệp không tồn tại có thể cần các bước kiểm tra khác nhau.

Một thứ tự kiểm tra hữu ích là: **đúng tiến trình và URL → endpoint được kích hoạt/công bố → quyền HTTP → đúng đường dẫn nguồn → tệp tồn tại/đọc được → nội dung và phạm vi byte**.

## 10. Bài tập thực hành

Thực hiện trên dự án minh họa:

1. Chạy ứng dụng lần đầu trong thư mục làm việc mới, xác định vị trí `logs/application.log`.
2. Gọi `GET /actuator/logfile`; tìm hai thông điệp `FILE_DEMO` trong body.
3. Tải body về `downloaded-application.log` và phân biệt tệp tải về với tệp nguồn trên máy chạy ứng dụng.
4. Gọi `Range: bytes=0-8`; giải thích vì sao body là `FILE_DEMO` và dài 9 byte.
5. Gọi một phạm vi nằm ngoài tệp nhỏ; giải thích mã `416`.
6. Thử lấy một đoạn cuối bằng suffix range; giải thích vì sao số byte không đồng nghĩa số dòng.
7. Dừng và chạy lại ứng dụng, rồi kiểm tra nội dung có nối tiếp dữ liệu cũ hay không.

Tự trả lời thêm ba tình huống:

- Đổi sang `logging.file.path=logs` và bỏ `logging.file.name`: tệp mặc định sẽ là `logs/spring.log`.
- Đặt đồng thời `logging.file.name=logs/custom.log` và `logging.file.path=other-logs`: với cấu hình mặc định của Spring Boot, tệp được chọn theo `name`, không tự ghép thành `other-logs/logs/custom.log`.
- Đọc được hai thông điệp ở bản sao A nhưng không thấy ở bản sao B: cần xác minh nguồn tệp và luồng xử lý của từng bản sao trước khi kết luận dữ liệu bị mất.

Một lần sử dụng endpoint đúng cần xác định được **tệp nguồn nào, thuộc tiến trình nào, phần dữ liệu nào đã được đọc và ai được phép nhận bản sao đó**.
