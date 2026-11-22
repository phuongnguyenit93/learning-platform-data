# Mô hình hóa timeout, giới hạn dung lượng và danh sách máy chủ bằng record

Trong Spring Boot Externalized Configuration, một hệ thống thường cần đọc đồng thời ba nhóm dữ liệu: **thời lượng chờ (timeout)**, **giới hạn kích thước dữ liệu (data size)** và **danh sách các máy chủ đích (servers)**. Dùng một chuỗi `String` cho mỗi giá trị rồi tự parse trong nhiều service dễ tạo lỗi: timeout được hiểu nhầm là milliseconds, giới hạn dung lượng bị nhầm giữa MB và byte, còn máy chủ trong danh sách thiếu URL hoặc có cấu trúc không đồng nhất.

Một cách tiếp cận phù hợp với Spring Boot 3.x và Java 17+ là dùng **Java record bất biến** kết hợp `@ConfigurationProperties`, `Duration`, `DataSize`, `List<Server>`, `@DefaultValue` và Bean Validation. Spring Boot Binder đọc các nguồn cấu hình, chuyển giá trị sang kiểu Java, xây record bằng constructor binding, và nếu có cơ chế validation phù hợp sẽ từ chối cấu hình không đáp ứng hợp đồng.

Bài thực hành này xây mô hình **`app.transfer`** cho một thành phần chuyển dữ liệu đến nhiều upstream servers. Mục tiêu là tạo được **một object cấu hình tập trung, type-safe và có quy tắc rõ ràng**, không dùng `@Value` rải rác; sau đó chạy các case thành công/sai, hiểu behavior của profile overrides, ghi đè bằng biến môi trường, đọc lỗi khi startup và áp dụng các thực hành bảo mật.

**Kết quả mong đợi sau bài học:**

- Xác định cấu trúc `application.yml` cho timeout, dung lượng, danh sách máy chủ.
- Xây `TransferProperties` dưới dạng record và một nested record `Server`.
- Hiểu cách Binder chuyển `2s` thành `Duration`, `20MB` thành `DataSize` và YAML sequence thành `List<Server>`.
- Phân biệt **thiếu giá trị**, **giá trị sai kiểu** và **giá trị sai quy tắc nghiệp vụ**.
- Đặt default an toàn bằng `@DefaultValue`, đồng thời yêu cầu danh sách máy chủ bắt buộc.
- Dùng `@Validated`, `@Valid` và Jakarta Validation để kiểm cấu hình sau binding.
- Test binding, default, conversion, validation và profile list replacement.
- Tránh hardcode secret trong cấu hình và không log object nhạy cảm.

Ví dụ dùng Spring Boot 3.x, Java 17+, Spring Boot configuration binding và Jakarta Bean Validation. Trong project thực, sử dụng cùng phiên bản Spring Boot cho các starter và kiểm đặc điểm minor version đang chạy.

---

## 1. Bài toán: một cấu hình có ba loại dữ liệu

Giả sử ứng dụng nhận file cần chuyển đến các máy chủ khác nhau. Nó cần:

1. `connect-timeout`: thời gian tối đa dành cho bước thiết lập kết nối.
2. `read-timeout`: giới hạn thời gian chờ đọc dữ liệu theo cách HTTP client của ứng dụng định nghĩa.
3. `max-payload-size`: kích thước tối đa một payload được phép xử lý.
4. `servers`: danh sách máy chủ đích, mỗi phần tử có tên, base URL, độ ưu tiên và timeout riêng.

Một file YAML dễ đọc:

~~~yaml
app:
  transfer:
    connect-timeout: 2s
    read-timeout: 10s
    max-payload-size: 20MB
    servers:
      - name: primary
        base-url: https://primary.example.test
        priority: 10
        health-timeout: 3s
      - name: secondary
        base-url: https://secondary.example.test
        priority: 20
        health-timeout: 5s
~~~

Trong ví dụ này:

- `2s` là chuỗi biểu diễn **2 giây**, không phải một integer mơ hồ.
- `20MB` là giá trị dung lượng mà Binder có thể chuyển thành `DataSize`.
- `servers` là **sequence YAML**, do đó phù hợp với một `List`.
- Hai phần tử server có cùng cấu trúc và cùng Java type.
- `priority` là số nguyên để ứng dụng có thể sắp xếp thứ tự thử, **không phải một cơ chế load balancing tự hoạt động**.
- `base-url` là URL đích được biểu diễn bằng kiểu `URI`; tính reachable của server là vấn đề runtime khác với khả năng bind.

**Không đưa credential thật vào URL trong ví dụ.** Nếu upstream cần token, quản lý credential bằng kênh secret riêng và tránh log URL có thông tin bí mật.

## 2. Bản đồ từ YAML đến Java record

~~~text
application.yml
  app.transfer
    connect-timeout: "2s"          ──> Duration
    read-timeout: "10s"            ──> Duration
    max-payload-size: "20MB"       ──> DataSize
    servers:                      ──> List<Server>
      - name: "primary"            ──> String
        base-url: "https://..."    ──> URI
        priority: 10               ──> int
        health-timeout: "3s"       ──> Duration
      - name: "secondary"          ──> String
        ...
                      |
                      v
              Spring Boot Binder
          tên property + conversion
          constructor binding record
                      |
                      v
          TransferProperties object
             ├─ Duration
             ├─ Duration
             ├─ DataSize
             └─ List<Server> immutable view*
                      |
                      v
            Bean Validation (nếu bật)
                      |
                      v
             Consumer service
~~~

Dấu `*`: Java record là **shallow immutable**. Các component tham chiếu như `List<Server>` không tự trở thành bất biến sâu chỉ vì nằm trong record. Cần thiết kế defensive copy nếu muốn ngăn code consumer thay đổi list.

## 3. Tạo project Spring Boot với dependencies phù hợp

Với Maven, dự án có thể sử dụng các dependency chính:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Ví dụ giả định parent hoặc dependency management của Spring Boot đang quản lý versions. Nếu ứng dụng là web service, có thể thêm `spring-boot-starter-web`, nhưng bản thân configuration binding không cần controller.

Với Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

`spring-boot-starter-validation` cung cấp Bean Validation integration/provider phù hợp để những annotation như `@NotBlank`, `@NotEmpty` và `@Min` được thực thi. Trong Spring Boot 3.x, các constraints thuộc package `jakarta.validation.*`.

Không sử dụng `javax.validation.*` của code cũ một cách lẫn lộn với Jakarta API ở ứng dụng Boot 3.

## 4. Gợi ý cấu trúc source

~~~text
src/
  main/
    java/
      com/example/transfer/
        TransferApplication.java
        config/
          TransferProperties.java
        service/
          TransferPlanner.java
    resources/
      application.yml
      application-dev.yml
      application-prod.yml
  test/
    java/
      com/example/transfer/
        config/
          TransferBindingTest.java
          TransferProfileTest.java
~~~

Một nhóm cấu hình nên được gom ở `config/TransferProperties.java`, còn thuật toán chọn upstream và xử lý dữ liệu thuộc `service/`. Không đưa network I/O vào record chỉ vì nó có `baseUrl`.

## 5. Record gốc: TransferProperties

Đầu tiên xây một version chỉ có typed fields:

~~~java
package com.example.transfer.config;

import java.time.Duration;
import java.net.URI;
import java.util.List;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "app.transfer")
public record TransferProperties(
    Duration connectTimeout,
    Duration readTimeout,
    DataSize maxPayloadSize,
    List<Server> servers
) {
    public record Server(
        String name,
        URI baseUrl,
        int priority,
        Duration healthTimeout
    ) {}
}
~~~

Dòng:

~~~java
@ConfigurationProperties(prefix = "app.transfer")
~~~

là ranh giới nhóm key mà Binder cần đọc. Component `connectTimeout` tương ứng với canonical property `app.transfer.connect-timeout`. Tương tự, `maxPayloadSize` tương ứng `app.transfer.max-payload-size`.

`record` cung cấp canonical constructor và accessors `connectTimeout()`, `readTimeout()`, `maxPayloadSize()`, `servers()`. Với Spring Boot 3.x, một record có một constructor phù hợp thường được bind theo constructor binding khi được đăng ký bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.

**Không cần setter**. Đây chính là một lợi ích của record: cấu hình được tạo một lần với trạng thái có kiểu rõ ràng.

## 6. Đăng ký record đúng cách

Main application:

~~~java
package com.example.transfer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class TransferApplication {

    public static void main(String[] args) {
        SpringApplication.run(TransferApplication.class, args);
    }
}
~~~

`@ConfigurationPropertiesScan` quét những class cấu hình thích hợp trong package scope, tạo bean và kích hoạt binding.

Một cách khác:

~~~java
package com.example.transfer.config;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(TransferProperties.class)
public class TransferConfig {}
~~~

Chỉ cần một cơ chế đăng ký phù hợp. Đừng thêm `@Component` vào record constructor-bound để “cho Spring thấy bean”: component scanning và Configuration Properties constructor binding là hai con đường tạo object khác nhau. Với `@Component`, Spring có thể cố dependency injection vào tham số constructor thay vì lấy value từ property sources.

### Khi dùng @ConstructorBinding?

Với record có một canonical constructor duy nhất trong Spring Boot 3.x, thông thường không cần thêm `@ConstructorBinding`. Nếu target có nhiều constructor và cần chỉ định rõ constructor dành cho binding, hãy xem quy tắc annotation tương ứng với version; trong Boot 3, phạm vi sử dụng annotation này khác những ví dụ cũ trên Internet.

## 7. Viết application.yml

~~~yaml
spring:
  application:
    name: transfer-service

app:
  transfer:
    connect-timeout: 2s
    read-timeout: 10s
    max-payload-size: 20MB
    servers:
      - name: primary
        base-url: https://primary.example.test
        priority: 10
        health-timeout: 3s
      - name: secondary
        base-url: https://secondary.example.test
        priority: 20
        health-timeout: 5s
~~~

Phần indentation rất quan trọng. Các key trong một phần tử list phải được thụt đúng vào sau ký hiệu `-`. Nếu viết:

~~~yaml
app:
  transfer:
    servers:
      name: primary
      base-url: https://primary.example.test
~~~

thì `servers` được biểu diễn như mapping/object, không phải YAML sequence cần cho `List<Server>`.

Một file cấu hình có thể được parse YAML thành công nhưng vẫn không bind đúng Java model do shape mismatch. Vì vậy, kiểm cả **cú pháp YAML** lẫn **kiểu Java mục tiêu**.

## 8. Duration: dùng kiểu Java để tránh nhầm đơn vị

`Duration` thuộc `java.time.Duration`, biểu diễn một khoảng thời gian. Spring Boot Binder hỗ trợ các dạng chuỗi có đơn vị phù hợp, ví dụ:

| YAML/property value | Ý nghĩa |
| --- | --- |
| `500ms` | 500 mili giây |
| `2s` | 2 giây |
| `3m` | 3 phút |
| `1h` | 1 giờ |
| `PT5S` | ISO-8601 duration, 5 giây |
| `PT1M` | ISO-8601 duration, 1 phút |

Ví dụ:

~~~yaml
app:
  transfer:
    connect-timeout: 750ms
    read-timeout: 2m
~~~

Sau khi bind:

~~~java
Duration connect = props.connectTimeout();
Duration read = props.readTimeout();

long connectMillis = connect.toMillis();
long readSeconds = read.toSeconds();
~~~

Không viết:

~~~java
int connectTimeout = 2; // 2 gì?
~~~

rồi yêu cầu mọi caller tự biết là seconds hay milliseconds. Kiểu `Duration` giúp code truyền đạt ngữ nghĩa và tránh lỗi chuyển đổi đơn vị.

### Đơn vị khi chỉ khai báo số

Spring Boot có quy tắc unit mặc định khi bind một number vào `Duration`; có thể dùng `@DurationUnit` khi cần chỉ định. Tuy nhiên, trong file cấu hình của bài này **luôn ghi rõ `ms`, `s`, `m`, `h`** để dễ review và hạn chế phụ thuộc vào giả định về unit.

Ví dụ:

~~~java
@DurationUnit(ChronoUnit.SECONDS)
Duration connectTimeout
~~~

là một tùy chọn khi bạn chủ ý hỗ trợ bare number với nghĩa seconds. Imports tương ứng:

~~~java
import java.time.temporal.ChronoUnit;
import org.springframework.boot.convert.DurationUnit;
~~~

Không cần annotation này nếu YAML đã dùng `2s` và `750ms` rõ ràng.

## 9. Read timeout và connect timeout không cùng vai trò

**Connect timeout** thường liên quan thời gian cho phép thiết lập kết nối mạng. **Read/response timeout** có thể là thời gian chờ phản hồi hoặc thao tác đọc, tùy HTTP client và transport đang dùng.

Hai property:

~~~yaml
connect-timeout: 2s
read-timeout: 10s
~~~

không tự động áp dụng vào bất kỳ HTTP client nào. Chúng mới là **typed configuration**. Khi tạo `WebClient`, `RestClient`, Apache HttpClient, Reactor Netty hoặc một SDK cụ thể, bạn phải map chúng vào đúng timeout controls của library đó.

Không giả định một API tên `readTimeout` ở framework X có cùng semantics tuyệt đối với `responseTimeout` ở framework Y. Luôn xem tài liệu của HTTP client thực tế, nhất là khi có connection pooling, streaming hoặc idle timeout.

### Không tạo network request trong record

Constructor record nên tạo data object, không kiểm tra endpoint qua network. Nếu Binder tạo record rồi mỗi lần khởi động nó tự ping tất cả servers, việc bind configuration sẽ phụ thuộc availability và dễ bị timeout không kiểm soát. Sự hợp lệ cú pháp và giá trị của cấu hình khác với trạng thái network lúc chạy.

## 10. DataSize: biểu diễn dung lượng bằng kiểu phù hợp

Spring Boot hỗ trợ bind giá trị dung lượng vào `org.springframework.util.unit.DataSize`. Ví dụ:

| Config value | Ý nghĩa sử dụng |
| --- | --- |
| `512B` | 512 bytes |
| `256KB` | 256 kilobytes theo unit của DataSize |
| `20MB` | 20 megabytes theo unit của DataSize |
| `1GB` | 1 gigabyte theo unit của DataSize |

Ví dụ:

~~~java
import org.springframework.util.unit.DataSize;

DataSize max = props.maxPayloadSize();

long allowedBytes = max.toBytes();
long allowedMegabytes = max.toMegabytes();
~~~

Với `max-payload-size: 20MB`, ứng dụng không cần tự phân tích chuỗi `20MB`. Binder sử dụng cơ chế conversion phù hợp để tạo `DataSize`.

**Không dùng `String maxPayloadSize` chỉ để gọi `Integer.parseInt(...)` ở service.** Định dạng có unit không thể parse nguyên bằng `Integer.parseInt`, và việc tự đổi MB sang byte dễ bị sai hoặc overflow.

### MB, MiB và cách hiểu đơn vị

`DataSize` của Spring dùng định nghĩa đơn vị cụ thể (ví dụ `DataSize.ofMegabytes(n)` theo hệ số nhị phân của API). Đừng viết một tài liệu nghiệp vụ chỉ nói “20 MB” rồi giả định mọi đối tác hiểu cùng tiêu chuẩn SI/IEC nếu byte limit phải chính xác. Khi giao tiếp với external API, giới hạn tải lên hoặc header HTTP, **so sánh bằng byte** và document semantics.

Ví dụ:

~~~java
long maxBytes = props.maxPayloadSize().toBytes();
if (payloadBytes > maxBytes) {
    throw new IllegalArgumentException(
        "Payload exceeds configured maximum");
}
~~~

`payloadBytes` là số bytes đã được đo theo một cách đáng tin cậy. Đo lường thực tế cần tránh đọc toàn bộ body vào memory rồi mới kiểm limit.

## 11. DataSize và giới hạn thực sự tại tầng web server

Đặt:

~~~yaml
app:
  transfer:
    max-payload-size: 20MB
~~~

**không tự thay đổi** những giới hạn multipart request của Spring MVC, reverse proxy, API Gateway hoặc servlet container.

Nếu ứng dụng nhận multipart uploads qua Spring MVC, còn có các property chuyên biệt như:

~~~yaml
spring:
  servlet:
    multipart:
      max-file-size: 20MB
      max-request-size: 25MB
~~~

Đây là **hai loại policy khác nhau**:

- `app.transfer.max-payload-size`: giới hạn nghiệp vụ mà code của bạn cần kiểm/enforce.
- `spring.servlet.multipart.*`: giới hạn multipart ở tầng HTTP handling của Spring Boot.

Nếu dùng Spring WebFlux, streaming hoặc gateway khác, các giới hạn và API tương ứng có thể khác. Không coi một custom `DataSize` trong record là cơ chế bảo vệ request-size tự động.

## 12. List<Server>: cách diễn đạt danh sách server

Nested record:

~~~java
public record Server(
    String name,
    URI baseUrl,
    int priority,
    Duration healthTimeout
) {}
~~~

đại diện cho **một phần tử**. Root property:

~~~java
List<Server> servers
~~~

đại diện cho toàn bộ danh sách.

YAML cần sequence:

~~~yaml
servers:
  - name: primary
    base-url: https://primary.example.test
    priority: 10
    health-timeout: 3s
  - name: secondary
    base-url: https://secondary.example.test
    priority: 20
    health-timeout: 5s
~~~

Khi bind thành công:

~~~java
List<TransferProperties.Server> servers =
    properties.servers();

for (TransferProperties.Server server : servers) {
    System.out.println(server.name());
}
~~~

Ví dụ chỉ in tên server không nhạy cảm. Đừng in nguyên URL nếu nó có token/query signature. Cũng không log toàn bộ record chứa credentials nếu bạn mở rộng model sau này.

### Tại sao tên server vẫn hữu ích?

`name` là định danh ổn định để observability, health status, routing table và migration. Nhưng Binder **không tự bảo đảm các tên là unique**. Nếu uniqueness là một business rule, cần validation/domain check bổ sung.

## 13. Một dạng .properties tương đương

YAML sequence cũng có thể biểu diễn bằng indexed properties:

~~~properties
app.transfer.connect-timeout=2s
app.transfer.read-timeout=10s
app.transfer.max-payload-size=20MB

app.transfer.servers[0].name=primary
app.transfer.servers[0].base-url=https://primary.example.test
app.transfer.servers[0].priority=10
app.transfer.servers[0].health-timeout=3s

app.transfer.servers[1].name=secondary
app.transfer.servers[1].base-url=https://secondary.example.test
app.transfer.servers[1].priority=20
app.transfer.servers[1].health-timeout=5s
~~~

Lưu ý `[0]` và `[1]` là chỉ số list, không phải một phần của tên Java accessor. Nếu bỏ index:

~~~properties
app.transfer.servers.name=primary
~~~

thì không nên kỳ vọng Binder tự tạo một `List<Server>` đúng ý bạn.

Khi ứng dụng dùng một Config Data source, nên chọn convention chủ đạo YAML hoặc properties; không cần duy trì đồng thời hai file có cùng tên base chỉ để “phòng khi cần”. Nếu tồn tại cả hai, phải hiểu precedence và hành vi khi key trùng.

## 14. Bổ sung default bằng @DefaultValue trên record

Để tránh phải khai báo mọi timeout/dung lượng ở từng môi trường, có thể cung cấp default rõ ràng cho **những value thực sự tùy chọn**:

~~~java
import java.time.Duration;
import java.net.URI;
import java.util.List;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "app.transfer")
public record TransferProperties(
    @DefaultValue("2s") Duration connectTimeout,
    @DefaultValue("10s") Duration readTimeout,
    @DefaultValue("20MB") DataSize maxPayloadSize,
    List<Server> servers
) {
    public record Server(
        String name,
        URI baseUrl,
        @DefaultValue("10") int priority,
        @DefaultValue("3s") Duration healthTimeout
    ) {}
}
~~~

`@DefaultValue` gắn với constructor parameter/record component trong cơ chế constructor binding. Binder dùng chuỗi default khi parameter không có value cần bind và chuyển nó sang type đích.

Ví dụ nếu YAML chỉ có:

~~~yaml
app:
  transfer:
    servers:
      - name: primary
        base-url: https://primary.example.test
~~~

các default được khai báo có thể cho:

~~~text
connectTimeout  = 2s
readTimeout     = 10s
maxPayloadSize  = 20MB
servers[0].priority      = 10
servers[0].healthTimeout = 3s
~~~

**Không gán default list nếu danh sách server là bắt buộc**. Thay vì tạo một server hư cấu, yêu cầu deploy khai báo ít nhất một server hợp lệ.

### Không nhầm @DefaultValue với @Value

`@DefaultValue("2s")` ở đây không phải `@Value("\${...:2s}")`. Nó dùng trong binder constructor-binding, không phải Spring bean field injection. Hai cơ chế cần được hiểu đúng trách nhiệm.

## 15. Có cần một default ở application.yml nếu đã có @DefaultValue?

Không bắt buộc. Cả hai đều có thể hoạt động, nhưng lặp cùng giá trị mặc định ở nhiều nơi làm tăng chi phí bảo trì.

Một chính sách ví dụ:

- **Default mang ý nghĩa của type**: dùng `@DefaultValue` để object vẫn có behavior nhất quán khi key vắng.
- **Default vận hành của sản phẩm**: đặt trong `application.yml` để thay đổi qua Config Data mà không sửa Java.
- **Giá trị môi trường bắt buộc**: không default; dùng validation/fail-fast.
- **Giá trị chỉ khác theo profile**: đặt profile-specific override.

Trong ví dụ thực hành, ta dùng `@DefaultValue` để minh họa cơ chế record. Với hệ thống production, chọn **một nguồn sự thật chủ đạo** và viết test cho hành vi khi thiếu key.

## 16. Record bất biến nhưng List chưa chắc bất biến

Với record:

~~~java
public record TransferProperties(
    Duration connectTimeout,
    Duration readTimeout,
    DataSize maxPayloadSize,
    List<Server> servers
) {}
~~~

Java tạo field `final` cho component, nhưng `List<Server>` tham chiếu đến một object collection có thể mutable. Một consumer bất cẩn:

~~~java
properties.servers().clear();
~~~

có thể thành công nếu list backing implementation cho phép mutation. Khi đó “immutable config” đã bị phá vỡ theo nghĩa dữ liệu danh sách bị đổi dù field không thể gán lại.

Một cách bảo vệ ở compact constructor:

~~~java
public TransferProperties {
    if (servers != null) {
        servers = List.copyOf(servers);
    }
}
~~~

Đây là cú pháp **compact canonical constructor** của record; assignment vào parameter `servers` làm bản sao bất biến được gán vào component khi record khởi tạo. `List.copyOf` không chấp nhận phần tử null, nên nếu Binder có element null thì constructor có thể thất bại sớm.

**Lưu ý:** đây là shallow copy của list; các `Server` cũng là record chỉ có components bất biến về mặt tham chiếu trong ví dụ. Nếu Server sau này chứa mutable collection, có thể cần defensive copy thêm.

## 17. Model hoàn chỉnh với Bean Validation

Để đảm bảo cấu hình cần thiết không bị bỏ sót, nâng cấp `TransferProperties`:

~~~java
package com.example.transfer.config;

import java.net.URI;
import java.time.Duration;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.util.unit.DataSize;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.transfer")
public record TransferProperties(
    @DefaultValue("2s") @NotNull Duration connectTimeout,
    @DefaultValue("10s") @NotNull Duration readTimeout,
    @DefaultValue("20MB") @NotNull DataSize maxPayloadSize,
    @NotEmpty List<@Valid Server> servers
) {
    public TransferProperties {
        if (servers != null) {
            servers = List.copyOf(servers);
        }
    }

    @AssertTrue(message = "timeouts must be positive")
    public boolean isValidTimeouts() {
        return connectTimeout == null
            || readTimeout == null
            || (connectTimeout.compareTo(Duration.ZERO) > 0
                && readTimeout.compareTo(Duration.ZERO) > 0);
    }

    @AssertTrue(message = "max-payload-size must be positive")
    public boolean isPositivePayloadLimit() {
        return maxPayloadSize == null
            || maxPayloadSize.toBytes() > 0;
    }

    public record Server(
        @NotBlank String name,
        @NotNull URI baseUrl,
        @DefaultValue("10") @Min(1) @Max(100) int priority,
        @DefaultValue("3s") @NotNull Duration healthTimeout
    ) {
        @AssertTrue(message = "server URL must use http or https")
        public boolean isHttpEndpoint() {
            if (baseUrl == null) {
                return true; // @NotNull handles missing value.
            }
            String scheme = baseUrl.getScheme();
            return "http".equalsIgnoreCase(scheme)
                || "https".equalsIgnoreCase(scheme);
        }

        @AssertTrue(message = "health-timeout must be positive")
        public boolean isPositiveHealthTimeout() {
            return healthTimeout == null
                || healthTimeout.compareTo(Duration.ZERO) > 0;
        }
    }
}
~~~

**Ý nghĩa các annotation:**

- `@Validated` kích hoạt cơ chế validation trên configuration properties bean được Spring Boot quản lý.
- `@NotNull` kiểm những reference fields bắt buộc.
- `@NotEmpty` yêu cầu list không null và có ít nhất một phần tử.
- `@Valid` trên element type yêu cầu cascade validation đến từng `Server` khi provider hỗ trợ Bean Validation container element constraints.
- `@NotBlank` yêu cầu tên server không null, không rỗng/chỉ toàn whitespace.
- `@Min(1) @Max(100)` giới hạn priority sau khi Binder chuyển giá trị thành `int`.
- `@AssertTrue` trên JavaBean-style boolean getter minh họa kiểm nghiệp vụ không có sẵn constraint thích hợp.

Trong ví dụ, `@AssertTrue` trên `isValidTimeouts`, `isPositivePayloadLimit` và các method `is...` áp dụng như **getter constraints** của Bean Validation; test thật cần có provider được cài và việc validate trên configuration bean đang hoạt động. Đối với validation phức tạp hoặc muốn gắn lỗi chính xác vào property path, có thể tạo custom **class-level constraint** và `ConstraintValidator`.

**Không dùng `@Positive` trực tiếp trên `Duration` hoặc `DataSize`** mà chưa xác nhận validator hỗ trợ kiểu đó. `@Positive` của Bean Validation áp dụng cho các number types được hỗ trợ, không mặc định kiểm mọi arbitrary value object.

## 18. Vì sao có @AssertTrue cho Duration/DataSize?

Một value:

~~~yaml
connect-timeout: -2s
max-payload-size: -10MB
~~~

về mặt cú pháp có thể được chuyển thành `Duration` và `DataSize`; nhưng giá trị âm thường không hợp lệ với giới hạn timeout hoặc dung lượng tối đa.

Nếu code không validate, ứng dụng có thể chỉ thất bại khi tạo HTTP client hoặc xử lý request. Kiểm sớm giúp báo lỗi ngay khi startup thay vì lúc nhận traffic.

Các rule trong model hoàn chỉnh:

~~~text
connectTimeout > 0
readTimeout > 0
maxPayloadSize > 0
servers không rỗng
server.name không blank
server.baseUrl không null và scheme http/https
1 <= server.priority <= 100
server.healthTimeout > 0
~~~

Những rule trên là **quy ước của bài thực hành**, không phải quy tắc cố định của Spring Boot. Một hệ thống có thể cho phép timeout zero để diễn đạt vô hạn hoặc tắt tính năng, nhưng phải chọn semantics rõ ràng; không đặt rule “>0” máy móc nếu thư viện HTTP định nghĩa zero có ý nghĩa đặc biệt.

## 19. Kiểm mối quan hệ giữa hai timeout

Bài thực hành đang chỉ yêu cầu cả hai timeout dương. Một domain khác có thể yêu cầu `readTimeout >= connectTimeout`. Đây là **cross-field validation**, không phải type conversion.

Có thể mở rộng method:

~~~java
@AssertTrue(message = "read-timeout must be >= connect-timeout")
public boolean isTimeoutOrderValid() {
    if (connectTimeout == null || readTimeout == null) {
        return true; // @NotNull sẽ phát hiện thiếu value.
    }
    return readTimeout.compareTo(connectTimeout) >= 0;
}
~~~

Tuy nhiên, **mối quan hệ này không phải lúc nào cũng cần thiết về mặt network**. Connect timeout và read timeout kiểm những giai đoạn khác nhau; một số HTTP clients cho phép read timeout nhỏ hơn connect timeout hoàn toàn hợp lệ. Chỉ áp dụng khi đó là một contract nghiệp vụ thật, không tự áp đặt.

Custom class-level validation hữu ích khi cần nhiều quan hệ phức tạp hoặc thông báo lỗi gắn với các field cụ thể.

## 20. Thiếu cả nhóm, thiếu một field, có value sai

Xem ba trường hợp.

**A. Không có bất kỳ `app.transfer.*` nào.** Với việc đăng ký configuration properties bean, Spring Boot có thể cố tạo/bind target tùy cơ chế và defaults. Nếu model yêu cầu `@NotEmpty servers`, policy mong muốn là startup thất bại do thiếu danh sách. Cần test context để xác nhận behavior trong đúng phiên bản/dependencies.

**B. Có servers nhưng thiếu timeout.**

~~~yaml
app:
  transfer:
    servers:
      - name: primary
        base-url: https://primary.example.test
~~~

`@DefaultValue` cung cấp timeout, DataSize và priority/health timeout phù hợp.

**C. Có timeout sai cú pháp.**

~~~yaml
app:
  transfer:
    connect-timeout: tomorrow
    servers:
      - name: primary
        base-url: https://primary.example.test
~~~

`tomorrow` không phải duration mà converter thông thường hiểu; Binder có thể thất bại ở bước conversion. **`@DefaultValue("2s")` không có nghĩa bỏ qua một value đã được khai báo nhưng sai kiểu.**

| Case | Tầng cần xét |
| --- | --- |
| Key vắng, có default | Constructor default |
| Key vắng, không default, có @NotNull/@NotEmpty | Constraint validation nếu bean được tạo/validate |
| Value `tomorrow` cho Duration | Conversion |
| Value `many` cho int priority | Conversion |
| Value `-2s` có thể convert thành Duration | Domain/constraint validation nếu policy cấm |
| List sai shape | Binding structure |
| Record không được scan | Bean registration |
| Object được tạo nhưng consumer sai | Runtime integration |

## 21. Khi nào khởi động thất bại vì validation?

Ví dụ:

~~~yaml
app:
  transfer:
    servers:
      - name: " "
        base-url: ftp://legacy.example.test
        priority: 0
        health-timeout: -1s
~~~

Nếu Bean Validation được bật đúng cách và Binder tạo thành công target, có thể có nhiều violations:

- `name` blank.
- `baseUrl` có scheme không phù hợp theo rule HTTP/HTTPS.
- `priority` dưới `@Min(1)`.
- `healthTimeout` không dương.

Đây là lỗi **value đúng kiểu nhưng không thỏa domain constraints**. Ngược lại, `priority: many` là conversion failure vì chuỗi không chuyển được thành `int` để constraint `@Min` kiểm.

Lỗi Bean Validation trong configuration properties binding có thể xuất hiện qua `BindException` hoặc `ConfigurationPropertiesBindException` ở lớp ngoài; cần đọc nguyên nhân sâu hơn và failure analysis, không chỉ dừng ở chữ “bind”.

## 22. Map báo lỗi rõ hơn khi cần uniqueness

`List<Server>` hợp lý nếu thứ tự server trong YAML có ý nghĩa. Nhưng nếu muốn đảm bảo tên server không trùng nhau, một danh sách cần thêm rule:

~~~java
Set<String> names = new HashSet<>();

for (TransferProperties.Server server : properties.servers()) {
    if (!names.add(server.name())) {
        throw new IllegalStateException(
            "Duplicate server name: " + server.name());
    }
}
~~~

Đây là ví dụ kiểm domain ở một lớp được gọi khi khởi tạo consumer, không phải code nên nhồi vào mọi constructor record. Với dữ liệu nhạy cảm, cần tránh in names nếu chúng là private identifiers.

Một lựa chọn khác là `Map<String, Server>` để identity được diễn đạt qua map key:

~~~yaml
app:
  transfer:
    servers:
      primary:
        base-url: https://primary.example.test
      secondary:
        base-url: https://secondary.example.test
~~~

Khi dùng map, key identity có thể unique theo cấu trúc map. Nhưng nếu **thứ tự/priority selection** là yêu cầu chính, list kèm validation rõ ràng vẫn phù hợp.

## 23. Dùng record trong consumer service

Một service có thể inject `TransferProperties` qua constructor:

~~~java
package com.example.transfer.service;

import java.util.Comparator;
import java.util.List;
import org.springframework.stereotype.Service;

import com.example.transfer.config.TransferProperties;

@Service
public class TransferPlanner {
    private final TransferProperties settings;

    public TransferPlanner(TransferProperties settings) {
        this.settings = settings;
    }

    public List<TransferProperties.Server> orderedServers() {
        return settings.servers().stream()
            .sorted(Comparator.comparingInt(
                TransferProperties.Server::priority))
            .toList();
    }
}
~~~

Ở đây **priority nhỏ hơn đứng trước** là quy tắc do ứng dụng định nghĩa; Spring Boot Binder không tự chọn upstream. `stream().toList()` trên Java hiện đại trả list không hỗ trợ thay đổi; chúng ta đã có defensive copy trong record nên nguồn không bị consumer sửa trực tiếp.

Nếu cần fallback khi server đầu tiên không phản hồi, service thực tế phải có logic retry/failover, health checks và policy nhất quán. Không gọi network trong `TransferProperties` để quyết định server ngay khi binding.

## 24. Lấy Duration và DataSize để cấu hình client

Giả sử component nghiệp vụ cần `long timeoutMs` và `long maxBytes`:

~~~java
Duration connect = settings.connectTimeout();
Duration read = settings.readTimeout();
DataSize limit = settings.maxPayloadSize();

long connectMillis = connect.toMillis();
long readMillis = read.toMillis();
long maxBytes = limit.toBytes();
~~~

Các dòng này có thể nằm ở factory tạo HTTP client hoặc transfer handler. Thứ tự quan trọng:

1. **Binder** chuyển external config thành kiểu Java.
2. **Validation** bảo đảm typed values phù hợp với contract.
3. **Factory/service** chuyển sang API của client cụ thể.
4. **Client runtime** áp dụng timeout, payload limits và lựa chọn server.

Không dùng `Math.toIntExact`/ép `long` sang `int` mà không kiểm giới hạn nếu thư viện chỉ nhận milliseconds dạng int. Một DataSize hàng gigabytes có thể vượt range của integer hoặc buffer capacity.

### Không nhầm maxPayloadSize với max memory

`max-payload-size` là **giới hạn nghiệp vụ cho một payload**, không tự ngăn việc nạp cả file vào RAM. Một ứng dụng đọc stream cần kiểm số bytes đã nhận theo kiểu incremental, hạn chế buffer và xử lý backpressure. Type-safe config chỉ là bước đầu, chưa thay thế resource management.

## 25. Java record không thực hiện refresh động mặc định

`TransferProperties` là object được tạo/bind trong lifecycle Spring context. Khi bạn sửa `application.yml` sau startup:

~~~text
10:00 Spring Boot khởi động, timeout=2s
10:05 developer sửa file thành timeout=4s
10:06 TransferProperties hiện tại vẫn có thể giữ 2s
~~~

Spring Boot Config Data thường được nạp lúc startup; không tự theo dõi file và cập nhật mọi record bean. Dù một cơ chế riêng cập nhật Environment, consumer HTTP client đã tạo cũng có thể giữ timeout cũ.

Muốn live reload phải có thiết kế rõ về nguồn cập nhật, rebind/recreate bean và client, consistency giữa các request, và quyền cập nhật. Không coi `record` hay `@ConfigurationProperties` là công cụ hot reload tự động.

## 26. Tách file theo profile mà không copy toàn bộ

Base:

~~~yaml
# application.yml
app:
  transfer:
    connect-timeout: 2s
    read-timeout: 10s
    max-payload-size: 20MB
    servers:
      - name: primary
        base-url: https://primary.example.test
        priority: 10
        health-timeout: 3s
      - name: secondary
        base-url: https://secondary.example.test
        priority: 20
        health-timeout: 5s
~~~

Development delta:

~~~yaml
# application-dev.yml
app:
  transfer:
    connect-timeout: 500ms
    read-timeout: 3s
    max-payload-size: 5MB
~~~

Production delta:

~~~yaml
# application-prod.yml
app:
  transfer:
    read-timeout: 15s
    max-payload-size: 50MB
~~~

Với các scalar, profile-specific config có thể override key tương ứng, trong khi các keys không được cung cấp vẫn đến từ base khi không có source khác ưu tiên hơn.

**Nhưng list servers không được deep-merge theo từng index giữa các profile một cách tùy ý.** Nếu production cần một danh sách khác, cần khai báo đầy đủ list hoặc cân nhắc model khác.

## 27. List replacement giữa application.yml và application-prod.yml

Giả sử base có:

~~~yaml
app:
  transfer:
    servers:
      - name: primary
        base-url: https://primary.example.test
        priority: 10
      - name: backup
        base-url: https://backup.example.test
        priority: 20
~~~

Production chỉ viết:

~~~yaml
app:
  transfer:
    servers:
      - priority: 1
~~~

Không được mặc định kỳ vọng rằng production chỉ đổi `priority` của server đầu tiên còn `name`/`base-url` và server thứ hai vẫn được kế thừa. **Spring Boot list binding thường dùng list từ source ưu tiên cao hơn, không merge nested values từ các nguồn theo index.**

Kết quả có thể là list chỉ có một phần tử, thiếu required fields, rồi fail validation. Nếu thực sự cần list khác ở production:

~~~yaml
# application-prod.yml
app:
  transfer:
    servers:
      - name: primary
        base-url: https://primary.example.test
        priority: 1
        health-timeout: 3s
      - name: backup
        base-url: https://backup.example.test
        priority: 20
        health-timeout: 5s
~~~

Nếu số servers lớn và chỉ muốn override một entry theo tên ổn định, cân nhắc `Map<String, Server>` với test binding behavior. Đổi list sang map là thay đổi contract; không thực hiện tùy tiện.

## 28. Các file profile có nên chứa server URLs?

Đây là quyết định vận hành:

- Một URL sandbox có thể hợp với `application-dev.yml`.
- Production URLs có thể do deployment cấp từ Config Data external hoặc config store.
- API credentials không nên nằm trong source-controlled YAML.
- DNS service names và regions khác giữa môi trường có thể hợp với deployment-specific config.
- Có thể dùng profile file cho non-secret values nếu artifact và repository access policy cho phép.

Không copy production credentials vào YAML chỉ để “tạo ví dụ chạy được”. Trong README này, tất cả URLs thuộc miền `example.test` để tránh vô tình gọi dịch vụ thật.

## 29. Ghi đè scalar từ biến môi trường

Spring Boot Binder hỗ trợ relaxed binding cho `@ConfigurationProperties`. Với các key canonical:

| Property | Env var thường dùng |
| --- | --- |
| `app.transfer.connect-timeout` | `APP_TRANSFER_CONNECTTIMEOUT` |
| `app.transfer.read-timeout` | `APP_TRANSFER_READTIMEOUT` |
| `app.transfer.max-payload-size` | `APP_TRANSFER_MAXPAYLOADSIZE` |
| `app.transfer.servers[0].name` | `APP_TRANSFER_SERVERS_0_NAME` |
| `app.transfer.servers[0].base-url` | `APP_TRANSFER_SERVERS_0_BASEURL` |
| `app.transfer.servers[0].priority` | `APP_TRANSFER_SERVERS_0_PRIORITY` |

Ví dụ Docker Compose:

~~~yaml
services:
  transfer:
    image: example/transfer-service:local
    environment:
      SPRING_PROFILES_ACTIVE: "prod"
      APP_TRANSFER_CONNECTTIMEOUT: "3s"
      APP_TRANSFER_MAXPAYLOADSIZE: "50MB"
~~~

Các biến này đi vào môi trường container rồi Spring Boot có thể bind tương ứng. **File `.env` riêng của Compose chỉ dùng cho interpolation nếu không được service truyền qua `environment` hoặc `env_file`.**

Lưu ý list: truyền một phần index của list từ env có ưu tiên cao hơn có thể dẫn tới list replacement; phải kiểm kết quả cuối, không dựa vào assumptions về merge từng element.

## 30. Không nhầm @Value với @ConfigurationProperties

Một cách viết rải rác:

~~~java
@Value("\${app.transfer.connect-timeout:2s}")
Duration connectTimeout;

@Value("\${app.transfer.max-payload-size:20MB}")
DataSize maxPayloadSize;
~~~

Với một nhóm lớn có nested list, việc dùng nhiều `@Value` sẽ khó quản lý:

- Không có một typed contract rõ cho cả nhóm.
- Placeholder defaults dễ khác nhau giữa các consumer.
- Nested lists phải xử lý thủ công hoặc qua SpEL/logic riêng.
- Validation có thể bị rải ở nhiều service.
- Test khó khẳng định trạng thái hợp lệ của toàn group.

`@ConfigurationProperties` kết hợp record là lựa chọn tự nhiên cho **cấu hình có cấu trúc**. Với một scalar đơn giản, `@Value` vẫn có chỗ dùng; không phải annotation “sai”.

## 31. Test binding thành công bằng ApplicationContextRunner

`ApplicationContextRunner` của `spring-boot-test` cho phép tạo context nhỏ, cấp properties riêng và kiểm typed binding.

Ví dụ dựa trên model hoàn chỉnh ở phần 17:

~~~java
package com.example.transfer.config;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;
import org.springframework.util.unit.DataSize;

class TransferBindingTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(TestConfig.class);

    @Test
    void bindsDurationsDataSizeAndServers() {
        runner.withPropertyValues(
                "app.transfer.connect-timeout=750ms",
                "app.transfer.read-timeout=8s",
                "app.transfer.max-payload-size=12MB",
                "app.transfer.servers[0].name=primary",
                "app.transfer.servers[0].base-url=https://primary.example.test",
                "app.transfer.servers[0].priority=5",
                "app.transfer.servers[0].health-timeout=2s",
                "app.transfer.servers[1].name=secondary",
                "app.transfer.servers[1].base-url=https://secondary.example.test"
            )
            .run(context -> {
                assertThat(context).hasNotFailed();
                TransferProperties p =
                    context.getBean(TransferProperties.class);

                assertThat(p.connectTimeout())
                    .isEqualTo(Duration.ofMillis(750));
                assertThat(p.readTimeout())
                    .isEqualTo(Duration.ofSeconds(8));
                assertThat(p.maxPayloadSize())
                    .isEqualTo(DataSize.ofMegabytes(12));
                assertThat(p.servers()).hasSize(2);
                assertThat(p.servers().get(0).name())
                    .isEqualTo("primary");
                assertThat(p.servers().get(1).priority())
                    .isEqualTo(10); // @DefaultValue
            });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(TransferProperties.class)
    static class TestConfig {}
}
~~~

Test trên tập trung vào **binding và default**. Nếu muốn assert Bean Validation, cần cấu hình validator/provider trong test context tương ứng như phần sau. Không dùng test này để kết luận file `application-prod.yml` tự được load; nó cung cấp properties trực tiếp.

## 32. Test @DefaultValue khi thiếu timeout và dung lượng

Một test riêng:

~~~java
@Test
void defaultsWorkWhenOptionalScalarsAreMissing() {
    runner.withPropertyValues(
            "app.transfer.servers[0].name=primary",
            "app.transfer.servers[0].base-url=https://primary.example.test"
        )
        .run(context -> {
            assertThat(context).hasNotFailed();
            TransferProperties p =
                context.getBean(TransferProperties.class);

            assertThat(p.connectTimeout())
                .isEqualTo(Duration.ofSeconds(2));
            assertThat(p.readTimeout())
                .isEqualTo(Duration.ofSeconds(10));
            assertThat(p.maxPayloadSize())
                .isEqualTo(DataSize.ofMegabytes(20));
            assertThat(p.servers().get(0).priority())
                .isEqualTo(10);
            assertThat(p.servers().get(0).healthTimeout())
                .isEqualTo(Duration.ofSeconds(3));
        });
}
~~~

Ở đây list có một server hợp lệ, nên Binder có cơ sở tạo `TransferProperties`; các scalar thiếu được lấp bằng `@DefaultValue`.

Nếu bạn sửa default trong annotation và base YAML vẫn có key, giá trị từ YAML có thể thắng default annotation. Test “missing optional scalar” cần **thực sự không cấp key đó**.

## 33. Test conversion failure: Duration không hợp định dạng

~~~java
import static org.assertj.core.api.Assertions.assertThat;

@Test
void invalidDurationFailsBinding() {
    runner.withPropertyValues(
            "app.transfer.connect-timeout=tomorrow",
            "app.transfer.servers[0].name=primary",
            "app.transfer.servers[0].base-url=https://primary.example.test"
        )
        .run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure())
                .isNotNull();
        });
}
~~~

Giá trị `tomorrow` không convert được sang `Duration` bởi converter mặc định phù hợp. Đây là **lỗi conversion được bọc bởi binding failure**; việc có `@DefaultValue("2s")` không chuyển value sai thành default.

Với test thật, để phân loại chính xác, có thể kiểm root cause hoặc exception type của phiên bản Spring Boot mà project sử dụng. Tránh assert nguyên văn cả khối failure analyzer output vì wording có thể thay đổi.

## 34. Test conversion failure: DataSize không hợp định dạng

~~~java
@Test
void invalidDataSizeFailsBinding() {
    runner.withPropertyValues(
            "app.transfer.max-payload-size=very-big",
            "app.transfer.servers[0].name=primary",
            "app.transfer.servers[0].base-url=https://primary.example.test"
        )
        .run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure())
                .isNotNull();
        });
}
~~~

`very-big` không phải giá trị `DataSize` mà conversion mặc định hiểu. Sửa thành `5MB`, `512KB` hoặc một giá trị có đơn vị hợp lệ theo policy.

Phân biệt:

~~~text
max-payload-size: very-big  -> conversion failure
max-payload-size: -10MB     -> có thể convert, domain validation failure
max-payload-size: 0B        -> có thể convert, domain validation failure
max-payload-size: 12MB      -> valid nếu giới hạn cho phép
~~~

## 35. Test validation: thiếu danh sách máy chủ

Để test Bean Validation, context cần một validator có thể thực thi các Jakarta constraints. Khi dùng Boot test context nhỏ, có thể đưa `ValidationAutoConfiguration` vào:

~~~java
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;

private final ApplicationContextRunner validatedRunner =
    new ApplicationContextRunner()
        .withUserConfiguration(TestConfig.class)
        .withConfiguration(
            AutoConfigurations.of(ValidationAutoConfiguration.class)
        );
~~~

Sau đó:

~~~java
@Test
void missingServersIsRejected() {
    validatedRunner.withPropertyValues(
            "app.transfer.connect-timeout=2s",
            "app.transfer.read-timeout=10s",
            "app.transfer.max-payload-size=20MB"
        )
        .run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure())
                .isNotNull();
        });
}
~~~

Khi binding tạo được root bean và Bean Validation được cấu hình đúng, `@NotEmpty List<Server> servers` làm thiếu list thành lỗi khởi động.

Nếu test bất ngờ pass, kiểm provider dependency, registration của record và validation integration trong context; đừng vội kết luận `@NotEmpty` không có hiệu lực.

## 36. Test validation: server name blank, priority sai

~~~java
@Test
void invalidServerConstraintsAreRejected() {
    validatedRunner.withPropertyValues(
            "app.transfer.servers[0].name= ",
            "app.transfer.servers[0].base-url=https://primary.example.test",
            "app.transfer.servers[0].priority=0"
        )
        .run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure())
                .isNotNull();
        });
}
~~~

Những value này có kiểu Java phù hợp:

- `" "` là String, nhưng vi phạm `@NotBlank`.
- `0` là int, nhưng vi phạm `@Min(1)`.

Nếu muốn bảo đảm nested element được validate, phải có `@Valid` và test provider phù hợp. Chỉ đặt `@Validated` ở root mà thiếu cascading phù hợp có thể khiến constraints trong danh sách không được đánh giá như kỳ vọng.

## 37. Test validation: giới hạn dung lượng phải dương

~~~java
@Test
void nonPositivePayloadSizeIsRejected() {
    validatedRunner.withPropertyValues(
            "app.transfer.max-payload-size=0B",
            "app.transfer.servers[0].name=primary",
            "app.transfer.servers[0].base-url=https://primary.example.test"
        )
        .run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure())
                .isNotNull();
        });
}
~~~

Ví dụ dựa vào `@AssertTrue` getter `isPositivePayloadLimit()` của model hoàn chỉnh. `0B` có thể bind thành `DataSize` với 0 bytes nhưng không vượt qua domain validation.

Khác với `very-big`, đây **không phải lỗi parse DataSize**. Việc chia test theo conversion/validation giúp log và chính sách sửa lỗi rõ hơn.

## 38. Test validation: URI có cú pháp hợp lệ nhưng scheme không đúng

~~~java
@Test
void unsupportedUriSchemeIsRejected() {
    validatedRunner.withPropertyValues(
            "app.transfer.servers[0].name=primary",
            "app.transfer.servers[0].base-url=ftp://legacy.example.test"
        )
        .run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure())
                .isNotNull();
        });
}
~~~

`ftp://legacy.example.test` có thể là một `URI` đúng cú pháp. Tuy vậy, domain rule của bài thực hành chỉ cho phép HTTP/HTTPS, nên đây là **validation failure**, không phải conversion failure.

Nếu ứng dụng thật cần gRPC, FTP hoặc một scheme custom, đừng sao chép nguyên rule; hãy định nghĩa constraint theo protocol hợp lệ của ứng dụng.

## 39. @SpringBootTest để thử đúng YAML và profile

`ApplicationContextRunner` kiểm tốt typed binding từ các giá trị cấp trực tiếp, nhưng muốn kiểm liệu `application.yml` và `application-prod.yml` có được nạp theo profile thực hay không, dùng integration test phù hợp.

Ví dụ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("prod")
class TransferProfileTest {
    @Autowired
    TransferProperties transfer;

    @Test
    void usesProductionTimeout() {
        assertThat(transfer.readTimeout())
            .isEqualTo(Duration.ofSeconds(15));
    }
}
~~~

Test giả định base và production YAML từ phần 26 đã được đưa vào test classpath đúng cách, record được scan/enable và không có test-specific source ưu tiên cao hơn đang ghi đè.

Với profile list override, nên assert cả `servers()`: số phần tử, tên, URLs, priorities và defaults; không chỉ test một scalar rồi kết luận toàn cấu hình production đúng.

## 40. Kiểm tra danh sách phải không được thay đổi bởi consumer

Với record có defensive copy:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Test
void serversListCannotBeMutated() {
    TransferProperties p = ...; // được tạo bằng Binder trong test.
    assertThatThrownBy(() -> p.servers().clear())
        .isInstanceOf(UnsupportedOperationException.class);
}
~~~

Đây là **mẫu assertion** cho test dùng một instance `p` thực sự đã có; dấu `...` là phần setup do test method cung cấp, không phải code Java compile được khi dán trực tiếp. Trong một test hoàn chỉnh, có thể lấy `p` từ `context.getBean(TransferProperties.class)` ngay trong callback của `ApplicationContextRunner`.

Lợi ích của defensive copy là việc một service vô tình gọi `clear()` hoặc `add()` trên list cấu hình không làm thay đổi trạng thái những service khác đang dùng cùng bean.

## 41. Kiểm thử thiếu file cấu hình so với lỗi binding

Một lỗi thường gặp: application chạy local với file `application.yml` đầy đủ, nhưng trong container chỉ có một file external chứa:

~~~yaml
app:
  transfer:
    max-payload-size: 50MB
~~~

Nếu file external **thay thế** location cơ sở hoặc một cấu hình khác vô tình không được nạp, danh sách `servers` có thể thiếu. Khi đó:

- Có thể là lỗi **Config Data location/loading**.
- Hoặc là lỗi **missing property/Bean Validation** nếu không có server list trong source hiệu lực.
- Nếu list có cấu trúc sai, là lỗi **binding shape**.
- Nếu URI không parse được, là **conversion**.
- Nếu URI parse được nhưng sai policy HTTP/HTTPS, là **validation**.

Không chỉ nhìn thấy `BindException` rồi quy kết “YAML sai cú pháp”. Đọc property path, origin/source và root cause để sửa đúng tầng.

## 42. Error handling và thông điệp khi startup

Một lỗi giả định:

~~~text
Failed to bind properties under 'app.transfer.connect-timeout'
to java.time.Duration

Property: app.transfer.connect-timeout
Value: "tomorrow"
Origin: class path resource [application.yml] - 5:22
Reason: failed to convert String to Duration
~~~

Đây là **mẫu minh họa**, log cụ thể tùy phiên bản Spring Boot và source. Khi debug:

1. `Property`: key nào lỗi?
2. `Value`: value thực tế Binder nhận?
3. `Origin`: đến từ file/profile/env/CLI nào?
4. `Reason`: lỗi convert, thiếu mandatory value hay validation?
5. **Type target**: `Duration`, `DataSize`, `URI` hay integer?
6. **Active profiles**: tài liệu nào được chọn?
7. **Precedence**: có source nào ghi đè file bạn đang sửa không?

Nếu property chứa credential, không paste value vào issue/README. Trong bài này, values đều là non-secret minh họa.

## 43. Sử dụng Java record làm configuration object không có nghĩa là domain model

Một `Server` trong record cấu hình:

~~~java
public record Server(
    String name,
    URI baseUrl,
    int priority,
    Duration healthTimeout
) {}
~~~

là **mô tả cách ứng dụng được cấu hình**. Nó không tự đại diện cho:

- Trạng thái health thực tại thời điểm này.
- Bộ đếm lỗi và circuit breaker.
- Kết quả DNS resolution.
- Số connection đang mở.
- Thống kê latency.
- Quyền truy cập hoặc credential đã verify.
- Endpoint có reachable hay không.

Những trạng thái này cần các object/runtime services riêng. Giữ record cấu hình thuần dữ liệu giúp binding dễ test, immutable snapshots rõ ràng và loại bỏ side effects khi startup.

## 44. Khi nào cần Map<String, Server> thay cho List<Server>?

Dùng `List<Server>` nếu:

- Thứ tự khai báo có ý nghĩa.
- Consumer đi qua server theo một thứ tự.
- Một server có thể xuất hiện nhiều lần theo contract.
- Tập server thường được thay nguyên khối khi profile đổi.

Dùng `Map<String, Server>` nếu:

- Tên/ID server là khóa duy nhất.
- Thường override settings của một server theo identity.
- Truy xuất server bằng tên quan trọng hơn thứ tự.
- Muốn profile-specific config không phải copy toàn danh sách trong nhiều tình huống.

Ví dụ map:

~~~yaml
app:
  transfer:
    servers:
      primary:
        base-url: https://primary.example.test
        health-timeout: 2s
      secondary:
        base-url: https://secondary.example.test
        health-timeout: 5s
~~~

Map có quy tắc binding và precedence riêng, không mặc định deep merge mọi object tùy ý. Khi đổi model từ list sang map, cập nhật code, docs, tests và tất cả nguồn cấu hình ngoài JAR.

## 45. Tránh gắn credential vào nested Server record

Trong thực tế có thể cần API token cho từng upstream. Không nên viết:

~~~yaml
app:
  transfer:
    servers:
      - name: primary
        base-url: https://primary.example.test
        api-token: REAL_SECRET_VALUE
~~~

và commit file vào Git. Token là secret. Một hướng tốt hơn là giữ server URLs, names và timeouts trong Config Data không nhạy cảm, còn token được cấp từ secret manager/secret mount/runtime sources và phân quyền phù hợp.

Nếu record cuối có chứa secret, **record `toString()` mặc định in tất cả components**. Không log nguyên record, không expose qua endpoint debug, không serialize thành JSON gửi client. Hạn chế Actuator env/configprops, sử dụng masking và xác thực phù hợp.

## 46. Thực hành thay đổi giới hạn dung lượng ở runtime deployment

Giả sử base:

~~~yaml
app:
  transfer:
    max-payload-size: 20MB
~~~

Production cần 50MB và deploy đặt biến môi trường:

~~~text
APP_TRANSFER_MAXPAYLOADSIZE=50MB
~~~

Trong cấu hình Spring Boot thông thường, environment variable có thể override Config Data file base khi đúng canonical name và cùng process. Nhưng thay biến ở shell của host **không tự đổi environment của container đã chạy**, và Spring record đã bind **không tự refresh**.

Kế hoạch đổi an toàn:

1. Xác định nguồn thắng và instance cần thay.
2. Đưa override vào deployment spec/runtime environment.
3. Recreate/rollout process theo môi trường.
4. Kiểm startup binding và validation thành công.
5. Xác nhận consumer limit đã áp dụng.
6. Kiểm tầng reverse proxy/server HTTP có giới hạn khác.
7. Rollback có kế hoạch nếu ảnh hưởng memory/throughput.

Với limit lớn, tăng kích thước file có thể ảnh hưởng resource usage nghiêm trọng; typed config không thay performance test.

## 47. Thực hành chọn timeout theo môi trường

Mẫu base + delta:

~~~yaml
# application.yml
app:
  transfer:
    connect-timeout: 2s
    read-timeout: 10s
~~~

~~~yaml
# application-dev.yml
app:
  transfer:
    connect-timeout: 500ms
    read-timeout: 3s
~~~

~~~yaml
# application-prod.yml
app:
  transfer:
    connect-timeout: 3s
    read-timeout: 15s
~~~

Không nên copy cả `servers` list sang dev/prod nếu nó thật sự giống nhau và không có lý do override. Tuy nhiên, nếu endpoint list khác giữa môi trường, khai báo trọn list ở mỗi source cần thiết và test final binding.

**Đừng chọn timeout chỉ bằng thói quen.** Giá trị cần dựa trên network latency, SLA, retry strategy, overall request budget và thời gian upstream xử lý. Connect timeout 2s và read timeout 10s chỉ là ví dụ học tập.

## 48. Ưu tiên test contract, không test số dòng YAML

Một ứng dụng có thể cấu hình bằng:

- `application.yml` đóng gói.
- `application-prod.yml`.
- Config Data import từ classpath hoặc external file.
- OS environment variables.
- JVM system properties.
- Spring command-line arguments.

Test có giá trị khi assert **typed result**:

~~~java
assertThat(props.connectTimeout())
    .isEqualTo(Duration.ofSeconds(2));

assertThat(props.maxPayloadSize())
    .isEqualTo(DataSize.ofMegabytes(20));

assertThat(props.servers()).hasSize(2);
~~~

Chỉ grep trong một file để thấy `20MB` không chứng minh đó là value cuối nếu một nguồn ưu tiên cao hơn đã ghi đè thành `50MB`.

## 49. Các sai lầm thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `Duration` null dù YAML có timeout | Prefix/name sai, file không được nạp, record chưa bind | Kiểm key, active profile, registration |
| `timeout=tomorrow` làm startup fail | Lỗi conversion | Dùng `ms`/`s`/`m` hoặc ISO-8601 hợp lệ |
| `max-payload-size=very-big` fail | Không parse được DataSize | Dùng value hợp lệ có unit |
| `max-payload-size=0B` được bind nhưng sai policy | Domain validation chưa chạy | Bật `@Validated`/constraint thích hợp |
| `@Positive DataSize` báo lỗi validation type | Constraint không hỗ trợ type | Dùng custom class-level / getter constraint |
| Không nhận danh sách server | YAML object thay vì list, sai index properties | Dùng YAML sequence hoặc `[0]`, `[1]` |
| Nested constraints không chạy | Thiếu `@Valid`/validator provider | Cấu hình cascading và validation |
| `@Component record` gây lỗi constructor injection | Sai registration path | Dùng scan/enable configuration properties |
| Production mất server backup | List nguồn cao hơn thay toàn list | Khai báo trọn list hoặc đổi map |
| Record vẫn bị sửa list | Shallow immutability | `List.copyOf` trong compact constructor |
| Dùng `server.port` để giải thích payload limit | Nhầm domain custom property và web server config | Cấu hình đúng tầng |
| Custom `max-payload-size` không giới hạn upload HTTP | Chưa enforce ở transport/app | Cấu hình multipart/proxy và kiểm stream |
| Đổi .yml khi đang chạy nhưng giá trị không đổi | Không có refresh/restart | Recreate/rebind theo thiết kế |
| Cấu hình đúng nhưng URL không reachable | Health/network runtime, không phải Binder | Kiểm DNS, TLS, firewall, availability |
| Debug log lộ token | In record/config/env nguyên văn | Redact, limit access, không log secrets |

## 50. Bài tập 1 — Xác định Java types

Cho YAML:

~~~yaml
app:
  transfer:
    connect-timeout: 800ms
    max-payload-size: 8MB
    servers:
      - name: first
        base-url: https://first.example.test
~~~

**Câu hỏi:** nên chọn Java types gì?

**Đáp án:** `Duration connectTimeout`, `DataSize maxPayloadSize`, `List<Server> servers`; trong `Server` dùng `String name` và `URI baseUrl`. Các value optional còn lại có thể nhận `@DefaultValue` nếu domain cho phép.

## 51. Bài tập 2 — Vì sao number không có unit nguy hiểm?

~~~yaml
connect-timeout: 2000
~~~

**Đáp án:** Spring Boot có quy tắc unit mặc định/có thể dùng `@DurationUnit`, nhưng người review có thể hiểu nhầm 2000 giây hoặc milliseconds. Thực hành an toàn hơn là ghi `2000ms` hoặc `2s` để contract rõ ràng.

## 52. Bài tập 3 — Conversion hay validation?

~~~yaml
max-payload-size: very-big
~~~

**Đáp án:** conversion failure vì `very-big` không parse được thành `DataSize` thông thường.

~~~yaml
max-payload-size: 0B
~~~

**Đáp án:** có thể convert thành `DataSize` nhưng vi phạm rule `> 0` trong model mẫu, nên validation failure nếu rule được bật.

## 53. Bài tập 4 — List shape sai

~~~yaml
servers:
  name: primary
  base-url: https://primary.example.test
~~~

**Đáp án:** đây là YAML mapping, không phải sequence cần cho `List<Server>`. Thêm `-` và thụt lề đúng.

## 54. Bài tập 5 — Nested @Valid

Một root có `@Validated`, một `Server` có `@NotBlank name`, nhưng list không được cascade thích hợp.

**Đáp án:** nested constraint có thể không được thực thi như mong đợi. Dùng `List<@Valid Server>` và một validator provider thích hợp; test case có blank name để chứng minh validation hoạt động.

## 55. Bài tập 6 — Record vs mutable list

Consumer gọi:

~~~java
properties.servers().clear();
~~~

**Đáp án:** record không tự bảo vệ list nếu backing collection mutable. `List.copyOf(servers)` trong compact constructor có thể tạo list không cho phép mutation.

## 56. Bài tập 7 — Profile override

Base có 2 servers. Production khai báo:

~~~yaml
servers:
  - name: only
    base-url: https://prod.example.test
~~~

**Đáp án:** xem đây là list production thay cho list cơ sở, không mặc định bổ sung server thứ ba. Test full `servers()` trong profile prod.

## 57. Bài tập 8 — Secret trong URL

Một `base-url` chứa `?token=...`.

**Đáp án:** toàn URL trở thành nhạy cảm; không log hoặc commit token thật. Nếu protocol hỗ trợ, dùng auth header và secret manager riêng.

## 58. Bài tập 9 — Missing servers

Config có timeout, DataSize nhưng không có `servers`. **Đáp án:** đây là một required configuration thiếu; `@NotEmpty` phải được test để startup từ chối khi Bean Validation hoạt động đúng. Không tự tạo default server giả.

## 59. Bài tập 10 — HTTP limit không tự áp dụng

Có `max-payload-size: 20MB` trong `TransferProperties`, nhưng controller vẫn nhận file lớn hơn.

**Đáp án:** custom property không tự áp dụng cho Spring multipart/streaming/proxy. Cần cấu hình HTTP layer và logic enforce phù hợp.

## 60. Checklist trước khi triển khai

- [ ] `TransferProperties` dùng prefix canonical `app.transfer`.
- [ ] Record được đăng ký bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.
- [ ] `Duration` values có đơn vị tường minh.
- [ ] `DataSize` values có đơn vị tường minh.
- [ ] `servers` là YAML sequence hoặc indexed properties đúng dạng.
- [ ] Mỗi `Server` có `name` và `base-url` đúng contract.
- [ ] `@DefaultValue` chỉ áp dụng cho những field có default an toàn.
- [ ] Danh sách server bắt buộc có `@NotEmpty`.
- [ ] Nested Server constraints được cascade qua `@Valid`.
- [ ] `@Validated` và Bean Validation provider được cấu hình.
- [ ] Rule Duration/DataSize dương được kiểm đúng type.
- [ ] Không gắn `@Positive` một cách thiếu căn cứ lên `Duration`/`DataSize`.
- [ ] Record có defensive copy nếu cần immutability của list.
- [ ] Không dùng `@Component` sai chỗ cho constructor-bound record.
- [ ] Test conversion failure và validation failure riêng.
- [ ] Test default behavior khi các scalar thiếu.
- [ ] Test profile override của toàn list, không chỉ một element.
- [ ] Kiểm effective property source/env/CLI trong deployment.
- [ ] Không hardcode secret hoặc đưa token vào URL đã commit.
- [ ] Tầng HTTP/server/proxy thực sự enforce upload/request limits phù hợp.
- [ ] Consumer client thực sự áp dụng timeout và failover policy, không chỉ đọc record.

## 61. Tổng kết

Để mô hình hóa timeout, giới hạn dung lượng và danh sách máy chủ trong Spring Boot, một hướng thiết kế rõ ràng là:

~~~text
application.yml / profile / env / CLI
                    |
                    v
            Spring Boot Binder
                    |
                    v
       @ConfigurationProperties record
       ├── Duration connectTimeout
       ├── Duration readTimeout
       ├── DataSize maxPayloadSize
       └── List<Server>
           ├── String name
           ├── URI baseUrl
           ├── int priority
           └── Duration healthTimeout
                    |
                    v
         @Validated / @Valid rules
                    |
                    v
       Immutable configuration snapshot
                    |
                    v
       HTTP client / transfer service
~~~

**`Duration` giải quyết đơn vị thời gian; `DataSize` giải quyết đơn vị dung lượng; `List<Server>` diễn đạt cấu trúc nhiều endpoint; record gom tất cả thành một typed contract.** `@DefaultValue` giúp cấp default có chủ đích, `@Validated` và `@Valid` giúp phát hiện thiếu hoặc sai ràng buộc, còn `List.copyOf` bảo vệ list khỏi thay đổi ngoài ý muốn khi cần.

Quan trọng nhất: **binding thành công không chứng minh consumer đã áp dụng timeout hoặc giới hạn tải lên**, và **record bất biến không tự làm mọi collection bất biến sâu**. Khi tách rõ cấu hình, validation và runtime behavior, ứng dụng có thể chạy qua nhiều profile/môi trường với dữ liệu có kiểu, dễ kiểm thử và ít lỗi khó truy vết hơn.
