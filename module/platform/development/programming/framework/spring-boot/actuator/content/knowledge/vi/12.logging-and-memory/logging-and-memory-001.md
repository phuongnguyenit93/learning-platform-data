# Đọc mức log được cấu hình và mức log có hiệu lực bằng endpoint loggers

Khi một dòng `DEBUG` không xuất hiện, câu hỏi đầu tiên thường là “logger này đang ở mức nào?”. Trong một ứng dụng có nhiều gói và thư viện, nhìn một dòng `logging.level.root` chưa đủ để trả lời: từng logger có thể được đặt mức riêng hoặc kế thừa mức từ một logger cha gần hơn.

Endpoint `loggers` của Spring Boot Actuator giúp đọc trạng thái mức log của tiến trình đang chạy. Hai thông tin cần tách rõ là:

- **Mức được cấu hình trực tiếp — `configuredLevel`**: mức đang được gán riêng cho logger được hỏi.
- **Mức có hiệu lực — `effectiveLevel`**: mức cuối cùng logger sử dụng sau khi xét cơ chế kế thừa của hệ thống logging.

Bài này tập trung vào các yêu cầu `GET` để quan sát và diễn giải hai trường trên. Ví dụ sử dụng **Java 21, Spring Boot 3.3.13 và Logback mặc định của Spring Boot starter**.

## 1. Logger có tên và có quan hệ cha–con

Logger là đối tượng nhận các lời gọi như `debug()`, `info()`, `warn()` và `error()`. Tên logger thường là tên lớp đầy đủ, nhưng cũng có thể là một chuỗi do ứng dụng chọn:

```java
// Đoạn minh họa cách lấy logger; chưa phải chương trình độc lập.
org.slf4j.Logger logger =
        org.slf4j.LoggerFactory.getLogger("demo.orders.InventoryService");
```

Trong Logback, dấu chấm tạo quan hệ phân cấp. Ví dụ:

```text
ROOT
└── demo
    └── demo.orders
        └── demo.orders.InventoryService
```

`demo.orders` là một tổ tiên của `demo.orders.InventoryService`. Tên này có thể giống tên package, nhưng logger không cần tương ứng với một đối tượng package hay một lớp thực sự đã được khai báo trong mã Java.

Tên logger phân biệt chữ hoa và chữ thường. `demo.orders.InventoryService` và `demo.orders.inventoryservice` là hai tên khác nhau.

### Cách tìm mức có hiệu lực trong Logback

Bắt đầu từ logger được hỏi:

1. Nếu nó có mức riêng, dùng mức đó.
2. Nếu chưa có, đi lên logger cha.
3. Tiếp tục đến tổ tiên gần nhất có mức riêng.
4. Cuối cùng có logger gốc `ROOT` làm điểm kế thừa.

Ví dụ:

```text
ROOT                                      WARN
└── demo.orders                           DEBUG
    ├── demo.orders.InventoryService      không đặt riêng
    ├── demo.orders.payment               INFO
    │   └── ...payment.RefundService      không đặt riêng
    └── ...audit.SecurityAudit            ERROR
```

Kết quả:

| Logger | Mức riêng | Mức có hiệu lực | Nguồn của mức có hiệu lực |
| --- | --- | --- | --- |
| `ROOT` | `WARN` | `WARN` | Chính logger gốc |
| `demo.orders` | `DEBUG` | `DEBUG` | Chính logger này |
| `demo.orders.InventoryService` | Không đặt | `DEBUG` | `demo.orders` |
| `demo.orders.payment` | `INFO` | `INFO` | Chính logger này |
| `demo.orders.payment.RefundService` | Không đặt | `INFO` | `demo.orders.payment` |
| `demo.orders.audit.SecurityAudit` | `ERROR` | `ERROR` | Chính logger này |

`RefundService` nhận `INFO` từ tổ tiên gần hơn, dù nhánh `demo.orders` phía trên được đặt `DEBUG`.

Tài liệu nền tảng: [Logback — Logger hierarchy và level inheritance](https://logback.qos.ch/manual/architecture.html).

## 2. Đọc hai trường mà không nhầm ý nghĩa

Một logger có mức riêng có thể được báo cáo:

```json
{
  "configuredLevel": "INFO",
  "effectiveLevel": "INFO"
}
```

Trong ví dụ dùng Logback, nếu logger không có mức riêng mà kế thừa `DEBUG`, phản hồi mặc định có dạng:

```json
{
  "effectiveLevel": "DEBUG"
}
```

Trường `configuredLevel` không xuất hiện vì không có mức trực tiếp để báo cáo. Khi đọc bằng mô hình dữ liệu của công cụ, trạng thái này cũng có thể được biểu diễn bằng `null`.

**Không có mức riêng vẫn có thể đi cùng một mức có hiệu lực hợp lệ.** Không được đổi cách hiểu này thành `OFF`, lỗi cấu hình hoặc “logger chưa hoạt động”.

| Trạng thái quan sát | Cách hiểu |
| --- | --- |
| `configuredLevel=DEBUG`, `effectiveLevel=DEBUG` | Logger đang có mức riêng là `DEBUG` |
| Không có `configuredLevel`, `effectiveLevel=DEBUG` | Logger đang kế thừa `DEBUG` |
| Không có `configuredLevel`, `effectiveLevel=WARN` | Logger đang kế thừa `WARN` |
| `configuredLevel=OFF`, `effectiveLevel=OFF` | Logger có mức riêng `OFF`; khác với trạng thái chưa đặt riêng |

Mức được cấu hình trực tiếp là trạng thái hiện tại trong hệ thống logging. Endpoint không nói rằng giá trị đó nhất thiết đến từ `application.yml`: nó có thể xuất phát từ cấu hình khởi động, tệp logging hoặc một thay đổi trong thời gian chạy.

Endpoint cũng không kèm nguồn tệp và số dòng để giải thích ai đã đặt mức. Khi cần truy nguồn, phải đối chiếu thêm cấu hình triển khai, cấu hình logging và lịch sử thao tác vận hành.

## 3. Hai dạng yêu cầu đọc chính

### 3.1. Đọc tổng quan

```text
GET /actuator/loggers
```

Các phần chính của phản hồi:

| Trường | Nội dung |
| --- | --- |
| `levels` | Các mức mà hệ thống logging hỗ trợ |
| `loggers` | Bảng logger, khóa là tên logger |
| `groups` | Những nhóm logger được khai báo, gồm danh sách thành viên |

Danh sách thực tế có thể dài và chứa nhiều logger của framework hoặc thư viện. Đây không phải danh sách toàn bộ lớp Java của ứng dụng; một lớp chưa tạo logger không nhất thiết có một mục tương ứng.

Không cố định số lượng logger hoặc thứ tự JSON khi viết công cụ kiểm tra. Dùng tên đầy đủ làm khóa tìm kiếm.

### 3.2. Đọc một logger

```text
GET /actuator/loggers/{logger.name}
```

Ví dụ:

```shell
curl "http://127.0.0.1:18082/actuator/loggers/demo.orders.InventoryService"
curl "http://127.0.0.1:18082/actuator/loggers/ROOT"
```

Trong cấu hình Spring Boot, logger gốc thường được đặt bằng khóa `logging.level.root`; khi đọc endpoint, tên gốc chuẩn là `ROOT`.

Nếu ứng dụng có context path, base path hoặc cổng quản trị riêng, dùng địa chỉ tương ứng thay vì mặc định trong ví dụ. Với tên có ký tự đặc biệt trong URL, cần mã hóa URL phù hợp và giữ nguyên tên logger sau giải mã.

Cấu trúc phản hồi chính thức: [Loggers endpoint REST API — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/loggers.html).

## 4. Một dự án chạy độc lập để đối chiếu

Tạo thư mục:

```text
actuator-loggers-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── learning/
        │       └── actuator/
        │           └── LoggersDemoApplication.java
        └── resources/
            └── application.yml
```

Cần JDK 21 và Maven 3.6.3 trở lên. Lần đóng gói đầu cần truy cập kho Maven để tải phụ thuộc.

### 4.1. `pom.xml`

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
    <artifactId>actuator-loggers-demo</artifactId>
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

Starter sử dụng Logback mặc định. Nếu thay logging backend, đối chiếu cơ chế và những mức được hỗ trợ của backend mới.

### 4.2. `src/main/java/learning/actuator/LoggersDemoApplication.java`

```java
package learning.actuator;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class LoggersDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(LoggersDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner emitExampleLogs() {
        return args -> {
            emit("demo.orders.InventoryService");
            emit("demo.orders.payment.RefundService");
            emit("demo.orders.audit.SecurityAudit");
            emit("external.health.Probe");
        };
    }

    private static void emit(String name) {
        Logger logger = LoggerFactory.getLogger(name);
        logger.trace("{} TRACE", name);
        logger.debug("{} DEBUG", name);
        logger.info("{} INFO", name);
        logger.warn("{} WARN", name);
        logger.error("{} ERROR", name);
    }
}
```

Bốn chuỗi tên logger cố ý tạo ra bốn trường hợp khác nhau. Không cần tạo thêm các lớp `InventoryService`, `RefundService`, `SecurityAudit` hoặc `Probe`: đây là các tên truyền vào `LoggerFactory.getLogger(String)`.

Mỗi logger được gọi lần lượt ở năm mức `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`. `ApplicationRunner` chạy phần minh họa một lần sau khi ứng dụng đã khởi động thành công.

### 4.3. `src/main/resources/application.yml`

```yaml
server:
  address: 127.0.0.1
  port: 18082

spring:
  main:
    banner-mode: "off"

management:
  endpoints:
    web:
      exposure:
        include: loggers

logging:
  level:
    root: WARN
    demo.orders: DEBUG
    demo.orders.payment: INFO
    demo.orders.audit.SecurityAudit: ERROR
  group:
    orderops: demo.orders,demo.shipping
  pattern:
    console: "%msg%n"
```

Các lựa chọn phục vụ thí nghiệm:

- `server.address=127.0.0.1` giới hạn máy chủ ở loopback.
- Chỉ endpoint `loggers` được đưa vào danh sách HTTP.
- `root=WARN` làm rõ rằng từng nhánh có thể có mức chi tiết hơn logger gốc.
- `logging.pattern.console=%msg%n` chỉ in nội dung thông điệp, giúp đối chiếu đầu ra dễ dàng.
- Nhóm `orderops` được khai báo để quan sát sự khác nhau giữa logger và nhóm logger.

Ví dụ không thêm Spring Security để tập trung vào cách đọc dữ liệu trên máy cá nhân. Endpoint `loggers` có cả khả năng thay đổi mức log; đưa nó vào exposure không tự biến nó thành endpoint chỉ đọc. Trong production, phải giới hạn mạng và quyền theo thao tác; bài này chỉ thực hiện `GET`.

### 4.4. Đóng gói và chạy

Tại thư mục chứa `pom.xml`:

```shell
mvn clean package
java -jar target/actuator-loggers-demo-1.0.0.jar
```

Đảm bảo không có đối số, biến môi trường hoặc cấu hình ngoài ghi đè các mức `logging.level.*` của thí nghiệm. Nếu cổng `18082` đang được dùng, chọn cổng khác bằng đối số `--server.port` và đổi các URL kiểm tra tương ứng.

Với cấu hình trên, mười thông điệp do runner phát ra và được ghi tới console là:

```text
demo.orders.InventoryService DEBUG
demo.orders.InventoryService INFO
demo.orders.InventoryService WARN
demo.orders.InventoryService ERROR
demo.orders.payment.RefundService INFO
demo.orders.payment.RefundService WARN
demo.orders.payment.RefundService ERROR
demo.orders.audit.SecurityAudit ERROR
external.health.Probe WARN
external.health.Probe ERROR
```

Các thông điệp `TRACE` đều bị loại theo ngưỡng mức log của ví dụ. Nhánh inventory ghi từ `DEBUG`; nhánh payment ghi từ `INFO`; logger audit chỉ ghi `ERROR`; logger ngoài nhánh orders kế thừa `WARN` từ `ROOT`.

Danh sách trên là đầu ra của phần minh họa. Cảnh báo vận hành phát sinh từ môi trường, nếu có, cần được phân biệt với các thông điệp này.

## 5. Đọc từng logger và giải thích phản hồi

Mở một terminal thứ hai trong khi ứng dụng đang chạy. Trên Windows PowerShell, dùng `curl.exe` thay cho `curl` nếu tên `curl` đang là bí danh của lệnh PowerShell.

### 5.1. Logger gốc

```shell
curl "http://127.0.0.1:18082/actuator/loggers/ROOT"
```

Body trong thí nghiệm:

```json
{
  "configuredLevel": "WARN",
  "effectiveLevel": "WARN"
}
```

Đây là mức gốc đang được áp dụng trong tiến trình. Nó không chứng minh mọi logger con đều có mức hiệu lực `WARN`.

### 5.2. Logger nhận mức từ nhánh orders

```shell
curl "http://127.0.0.1:18082/actuator/loggers/demo.orders.InventoryService"
```

Body:

```json
{
  "effectiveLevel": "DEBUG"
}
```

Logger inventory không có mức riêng. Đọc tiếp logger cha:

```shell
curl "http://127.0.0.1:18082/actuator/loggers/demo.orders"
```

Body:

```json
{
  "configuredLevel": "DEBUG",
  "effectiveLevel": "DEBUG"
}
```

Hai phản hồi kết hợp giải thích được nguồn kế thừa trong cấu hình này: mức `DEBUG` của inventory đến từ `demo.orders`.

### 5.3. Logger nhận mức từ tổ tiên gần hơn

```shell
curl "http://127.0.0.1:18082/actuator/loggers/demo.orders.payment.RefundService"
```

Body:

```json
{
  "effectiveLevel": "INFO"
}
```

Kiểm tra logger `demo.orders.payment` sẽ thấy nó có mức riêng `INFO`. Vì tổ tiên này gần hơn `demo.orders`, logger refund kế thừa `INFO` thay vì `DEBUG`.

Khi điều tra một cây logger lớn, bắt đầu từ logger đích rồi đi ngược theo từng tiền tố để tìm mức riêng gần nhất. Không chỉ đọc `ROOT` rồi dừng.

### 5.4. Logger có mức riêng

```shell
curl "http://127.0.0.1:18082/actuator/loggers/demo.orders.audit.SecurityAudit"
```

Body:

```json
{
  "configuredLevel": "ERROR",
  "effectiveLevel": "ERROR"
}
```

Mức `ERROR` trực tiếp trên logger này được dùng dù tổ tiên `demo.orders` đang ở `DEBUG`.

Bảng đối chiếu cuối cùng của thí nghiệm:

| Logger được hỏi | `configuredLevel` | `effectiveLevel` |
| --- | --- | --- |
| `ROOT` | `WARN` | `WARN` |
| `demo.orders` | `DEBUG` | `DEBUG` |
| `demo.orders.InventoryService` | Không có trường | `DEBUG` |
| `demo.orders.payment` | `INFO` | `INFO` |
| `demo.orders.payment.RefundService` | Không có trường | `INFO` |
| `demo.orders.audit.SecurityAudit` | `ERROR` | `ERROR` |
| `external.health.Probe` | Không có trường | `WARN` |

## 6. Đọc toàn bộ logger và phân biệt nhóm logger

Gọi:

```shell
curl "http://127.0.0.1:18082/actuator/loggers"
```

Trong `loggers`, tìm bằng đúng tên đầy đủ. Những logger đã được runner sử dụng sẽ có thể đối chiếu theo bảng ở phần 5. Các mục của framework và những logger cha trung gian có thể xuất hiện cùng chúng.

Trường `levels` giúp xác định hệ thống logging hỗ trợ các mức nào. Không nên suy luận rằng mọi logging backend có cùng mức riêng hoặc cùng cách ánh xạ; chẳng hạn Spring Boot ánh xạ `FATAL` sang `ERROR` khi dùng Logback.

### Nhóm là danh sách thành viên, không phải một logger cha

Nhóm `orderops` trong YAML chứa hai thành viên được đặt tên:

```text
demo.orders
demo.shipping
```

Có thể đọc nhóm bằng cùng mẫu đường dẫn:

```shell
curl "http://127.0.0.1:18082/actuator/loggers/orderops"
```

Body của thí nghiệm:

```json
{
  "members": [
    "demo.orders",
    "demo.shipping"
  ]
}
```

Nhóm chưa được đặt mức riêng nên không có `configuredLevel`. Phản hồi nhóm cũng không có một `effectiveLevel` chung cho mọi thành viên.

Tên nhóm gom các logger để quản lý cấu hình; nó không tạo ra quan hệ cha–con theo tên như `demo.orders → demo.orders.InventoryService`. Muốn biết mức có hiệu lực của một logger cụ thể trong nhóm, vẫn phải đọc logger đó.

Một thành viên được liệt kê theo tên trong nhóm cũng không chứng minh mọi lớp hoặc logger con trong nhánh ấy đã được tạo. Không dùng danh sách nhóm để suy ra số lớp đã thực thi.

## 7. Từ mức có hiệu lực đến thông điệp thực sự được ghi

Với quy tắc ngưỡng thông thường của Logback và không có bộ lọc tùy chỉnh làm thay đổi quyết định:

```text
TRACE < DEBUG < INFO < WARN < ERROR
```

Thông điệp có mức bằng hoặc cao hơn ngưỡng của logger có thể vượt qua bước kiểm tra mức log.

| `effectiveLevel` | Những mức thông điệp vượt qua ngưỡng thông thường |
| --- | --- |
| `TRACE` | `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR` |
| `DEBUG` | `DEBUG`, `INFO`, `WARN`, `ERROR` |
| `INFO` | `INFO`, `WARN`, `ERROR` |
| `WARN` | `WARN`, `ERROR` |
| `ERROR` | `ERROR` |
| `OFF` | Không mức nào trong năm mức trên |

Do đó, `effectiveLevel=INFO` không có nghĩa logger chỉ ghi thông điệp `INFO`. Nó vẫn cho các thông điệp `WARN` và `ERROR` vượt qua ngưỡng.

### Vì sao root là WARN mà vẫn thấy DEBUG?

Trong thí nghiệm, inventory có mức hiệu lực `DEBUG`. Thông điệp `DEBUG` của nó vượt qua kiểm tra tại logger phát thông điệp, rồi được chuyển tới console appender kế thừa từ nhánh cha.

Với cấu hình Logback thông thường này, mức `WARN` của root không được áp dụng lại như một bộ lọc chung để loại thông điệp `DEBUG` đã được logger con chấp nhận. Nếu muốn hiểu một thông điệp cụ thể, phải đọc logger đã phát ra nó.

### Mức có hiệu lực chưa mô tả toàn bộ đường ghi log

Sau hoặc quanh bước kiểm tra mức, kết quả còn phụ thuộc các thành phần như:

- Bộ lọc theo ngưỡng hoặc nội dung trên appender.
- `TurboFilter` tùy chỉnh của Logback.
- Cách kế thừa appender và thuộc tính `additivity`.
- Đích ghi log: console, tệp, bộ thu thập hoặc đường truyền khác.
- Bộ đệm và giới hạn của đường ghi bất đồng bộ, nếu được cấu hình.

Vì vậy, `effectiveLevel=DEBUG` là bằng chứng về mức hiện tại của logger, chưa đủ để khẳng định một thông điệp nhất định đã được ghi vào một tệp cụ thể. Cần kiểm tra thêm lời gọi logging đã thực sự chạy và đường xử lý tới đích.

Ngược lại, logger có mức `INFO` hiện tại không chứng minh các dòng `DEBUG` trong một tệp cũ là bất thường. Tệp có thể chứa dữ liệu từ thời điểm có cấu hình khác hoặc từ nhiều tiến trình.

## 8. Quy trình đọc khi cần chẩn đoán

### Bước 1: Xác định đúng logger phát thông điệp

Tìm tên logger mà mã thực sự dùng. Với `LoggerFactory.getLogger(SomeClass.class)`, đó thường là tên lớp đầy đủ. Với `getLogger(String)`, dùng chuỗi được truyền vào.

Tên logger trên console có thể bị rút gọn bởi pattern. Không sao chép tên rút gọn đó rồi coi nó là tên đầy đủ để truy vấn.

Cũng cần bảo đảm dòng đang tìm được phát qua hệ thống logging mà Actuator đang quản lý. Một lời gọi `System.out.println` không được điều khiển bởi ngưỡng của logger này.

### Bước 2: Đọc logger đích

Gọi `GET /actuator/loggers/<tên-đầy-đủ>` và ghi lại:

- Tên/logger được hỏi.
- `configuredLevel` có xuất hiện hay không.
- Giá trị `effectiveLevel`.
- Bản sao ứng dụng và thời điểm quan sát.

### Bước 3: Lần theo nguồn kế thừa

Nếu không có mức riêng, đọc các logger tổ tiên phù hợp hoặc tra chúng trong bảng tổng quan. Tổ tiên gần nhất có mức riêng giải thích kết quả kế thừa trong ví dụ Logback.

Nếu logger có mức riêng, kiểm tra cấu hình nào hoặc thao tác thời gian chạy nào đã đặt nó. Endpoint báo trạng thái hiện tại, không cung cấp lịch sử tác giả thay đổi.

### Bước 4: So ngưỡng với mức của lời gọi

Nếu thông điệp là `DEBUG` mà mức hiệu lực là `INFO`, việc không thấy thông điệp phù hợp với cơ chế lọc mức thông thường.

Nếu mức hiệu lực là `DEBUG` nhưng vẫn không thấy thông điệp, tiếp tục xác minh nhánh mã có chạy không, logger có đúng tên không, có bộ lọc hoặc đích ghi khác không. Việc đổi thêm mức toàn cục có thể làm tăng nhiều log mà chưa xử lý đúng nguyên nhân.

### Bước 5: Đối chiếu cùng tiến trình và cùng thời điểm

Trong hệ thống nhiều bản sao, mỗi JVM có trạng thái logging riêng. Một lần đọc qua load balancer có thể đi vào bản sao khác với bản sao đã tạo dòng log cần điều tra.

Ghi rõ địa chỉ bản sao hoặc thông tin định danh vận hành phù hợp. Không so phản hồi hiện tại của bản sao A với tệp log của bản sao B rồi kết luận cơ chế kế thừa sai.

## 9. Khi endpoint không trả dữ liệu mong đợi

| Hiện tượng | Cách kiểm tra |
| --- | --- |
| Không kết nối được | Ứng dụng có khởi động thành công không, đúng cổng và tuyến mạng chưa? |
| `401` hoặc `403` | Kiểm tra thông tin xác thực và quyền đọc trong ứng dụng thật |
| `404` cho endpoint | Kiểm tra starter, trạng thái kích hoạt, exposure, base path và cổng quản trị |
| `404` chỉ với một tên logger | Kiểm tra tên chính xác và logger có tồn tại trong hệ thống logging hiện tại không |
| Không có `configuredLevel` nhưng có `effectiveLevel` | Logger có thể đang kế thừa; đó là kết quả hợp lệ |
| Nhận `members` thay vì `effectiveLevel` | Đang đọc một nhóm logger |
| Giá trị khác YAML dự kiến | Kiểm tra nguồn ghi đè, tệp logging, profile và thay đổi trong thời gian chạy |
| `DEBUG` được bật nhưng không thấy dòng log | Kiểm tra logger phát thực tế, luồng chạy, bộ lọc, appender và đích ghi |

Với Logback trong thí nghiệm, một logger chưa tồn tại như `does.not.exist.LoggerInThisDemo` trả `404` khi được hỏi qua đường đọc một logger. Không suy ra mức kế thừa bằng cách coi phản hồi `404` là `configuredLevel=null`: một bên là không có kết quả cho tên được hỏi, bên kia là đã có logger với mức có hiệu lực.

Cũng không dùng endpoint như một phép dò tên lớp có trong JAR. Tên logger và sự tồn tại của lớp là hai dữ kiện riêng.

## 10. Tự kiểm tra

Với cấu hình thí nghiệm ban đầu, trả lời:

1. Vì sao inventory không có `configuredLevel` nhưng vẫn ghi được `DEBUG`?
2. Vì sao refund nhận `INFO` dù nhánh orders ở `DEBUG`?
3. Vì sao audit chỉ ghi `ERROR` trong năm lời gọi của runner?
4. Vì sao không thể dùng mức `WARN` của root để kết luận inventory không ghi `DEBUG`?
5. Vì sao phản hồi nhóm `orderops` không có một `effectiveLevel` chung?

Đáp án cần chỉ ra đúng logger hoặc nguồn kế thừa: inventory nhận `DEBUG` từ `demo.orders`; refund nhận `INFO` từ `demo.orders.payment`; audit có mức riêng `ERROR`; mỗi logger phát thông điệp được xét theo mức hiệu lực của nó; nhóm là danh sách thành viên để quản lý cấu hình.

Sau đó dừng ứng dụng và khởi động lại với:

```shell
java -jar target/actuator-loggers-demo-1.0.0.jar --logging.level.demo.orders=TRACE
```

Dự đoán rồi đọc lại:

| Logger | Mức có hiệu lực dự đoán |
| --- | --- |
| `demo.orders` | `TRACE` |
| `demo.orders.InventoryService` | `TRACE` |
| `demo.orders.payment.RefundService` | `INFO` |
| `demo.orders.audit.SecurityAudit` | `ERROR` |
| `external.health.Probe` | `WARN` |

Inventory nhận mức mới từ nhánh orders; nhánh payment và logger audit vẫn có điểm đặt mức riêng. Đây là thay đổi bằng cấu hình của **lần khởi động mới**, giúp quan sát cùng cơ chế mà không cần gửi yêu cầu cập nhật endpoint.

Đối chiếu thêm [Spring Boot Logging](https://docs.spring.io/spring-boot/3.3/reference/features/logging.html) và [LoggerConfiguration API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/logging/LoggerConfiguration.html) khi làm việc với hệ thống logging hoặc phiên bản khác. Một kết luận chẩn đoán có ích cần nêu rõ **logger nào, mức riêng nào, mức hiệu lực nào và tại thời điểm nào**.
