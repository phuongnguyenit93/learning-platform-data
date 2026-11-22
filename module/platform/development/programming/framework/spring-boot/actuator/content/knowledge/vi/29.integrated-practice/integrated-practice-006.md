# Quan sát một lời gọi qua hai dịch vụ với trace và log được liên kết

## 1. Bài thực hành giải quyết vấn đề gì?

Giả sử người dùng hỏi: “Vì sao lần kiểm tra hàng này bị lỗi?”. Một dòng log ở dịch vụ đặt hàng chưa cho biết dịch vụ kho đã nhận yêu cầu hay chưa. Nếu cả hai dịch vụ đều xử lý nhiều yêu cầu cùng lúc, ghép log chỉ bằng thời gian hoặc mã sản phẩm rất dễ nhầm.

Trong bài này, một yêu cầu đi qua hai tiến trình Java độc lập:

```text
curl
  |
  | GET /orders/P100
  v
order-service :8081
  |
  | GET /inventory/P100 + ngữ cảnh trace
  v
inventory-service :8082

Cả hai dịch vụ:
  - ghi log tại tiến trình của mình
  - gửi span tới Zipkin :9411
```

Kết quả cần đạt:

1. Phản hồi nghiệp vụ đi qua đúng hai dịch vụ.
2. Log xử lý yêu cầu ở cả hai bên mang cùng traceId.
3. Mỗi thao tác có spanId phù hợp; không ép hai dịch vụ dùng cùng một span.
4. Zipkin hiển thị quan hệ giữa span nhận yêu cầu ở A, span gọi HTTP từ A và span nhận yêu cầu ở B.
5. Từ một dòng log, tìm được trace tương ứng; từ trace, biết cần tìm tiếp log của dịch vụ nào.

Zipkin nhận dữ liệu span để dựng trace. Các dòng log ứng dụng vẫn nằm trong terminal hoặc tệp log; bài không cấu hình hệ thống thu gom log tập trung. Liên kết giữa hai loại bằng chứng ở đây là traceId và spanId.

Dự án dùng Java 21, Gradle 8.5, Spring Boot 3.3.x, Micrometer Tracing với Brave và Zipkin. Đây là một dự án thí nghiệm độc lập; các đoạn mã dưới đủ để tạo và chạy hai ứng dụng.

## 2. Các khái niệm phải phân biệt

| Khái niệm | Ý nghĩa trong bài |
| --- | --- |
| Trace | Toàn bộ chuỗi công việc liên quan đến một yêu cầu |
| Span | Một thao tác có thời điểm bắt đầu/kết thúc, ví dụ nhận HTTP hoặc gọi HTTP |
| traceId | Định danh chung để tìm các span và log thuộc cùng trace |
| spanId | Định danh của một span cụ thể |
| parentId | Định danh span cha, giúp dựng quan hệ nhân quả |
| Propagation | Truyền ngữ cảnh trace qua ranh giới tiến trình |
| MDC | Ngữ cảnh khóa–giá trị mà hệ thống logging dùng để thêm định danh vào log |
| Export | Gửi dữ liệu span từ ứng dụng tới nơi thu thập như Zipkin |

Hai log mang cùng traceId không nhất thiết mang cùng spanId. Ví dụ, log bên trong controller A thuộc span nhận yêu cầu của A; log bên trong controller B thuộc span nhận yêu cầu của B.

Việc đặt span vào phạm vi thực thi cho phép tracer và cơ chế logging gắn ngữ cảnh vào các dòng log trong phạm vi đó. Xem [Micrometer Tracing API](https://docs.micrometer.io/tracing/reference/api.html).

Cần giữ riêng hai đường đi:

- **Đường nghiệp vụ:** A gọi B qua cổng 8082 và truyền header ngữ cảnh.
- **Đường quan sát:** A và B gửi span đến cổng 9411 của Zipkin.

Zipkin không đứng giữa A và B để chuyển tiếp yêu cầu nghiệp vụ. Gửi được span đến Zipkin cũng chưa chứng minh header ngữ cảnh giữa A và B đã đúng.

## 3. Chuẩn bị và tạo dự án

Chuẩn bị JDK 21, Gradle 8.5 để tạo wrapper lần đầu, Docker để chạy Zipkin và các cổng 8081, 8082, 9411 còn trống.

Tạo cấu trúc:

```text
tracing-two-services/
├── settings.gradle
├── build.gradle
├── order-service/
│   └── src/main/
│       ├── java/com/example/order/
│       │   ├── OrderApplication.java
│       │   └── OrderController.java
│       └── resources/application.yml
├── inventory-service/
│   └── src/main/
│       ├── java/com/example/inventory/
│       │   ├── InventoryApplication.java
│       │   └── InventoryController.java
│       └── resources/application.yml
└── tools/
    └── TraceEvidenceCheck.java
```

Hai thư mục dịch vụ không cần build.gradle riêng trong mẫu vì cấu hình chung nằm trong khối subprojects ở root.

### 3.1. settings.gradle

```groovy
rootProject.name = 'tracing-two-services'
include 'order-service', 'inventory-service'
```

### 3.2. build.gradle

Mẫu cố định Spring Boot 3.3.0 trong dòng 3.3.x. BOM đi cùng plugin quản lý phiên bản cho các thư viện, bao gồm các dependency quan sát.

```groovy
plugins {
    id 'org.springframework.boot' version '3.3.0' apply false
}

subprojects {
    apply plugin: 'java'
    apply plugin: 'org.springframework.boot'

    group = 'com.example'
    version = '1.0.0'

    java {
        toolchain {
            languageVersion = JavaLanguageVersion.of(21)
        }
    }

    repositories {
        mavenCentral()
    }

    dependencies {
        implementation platform(
                org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
        implementation 'org.springframework.boot:spring-boot-starter-web'
        implementation 'org.springframework.boot:spring-boot-starter-actuator'
        implementation 'io.micrometer:micrometer-tracing-bridge-brave'
        implementation 'io.zipkin.reporter2:zipkin-reporter-brave'
    }
}
```

Các dependency có vai trò khác nhau:

- Web starter cung cấp Spring MVC và web server nhúng.
- Actuator cung cấp cấu hình tự động cho hạ tầng quan sát.
- `micrometer-tracing-bridge-brave` nối API tracing của Micrometer với Brave.
- `zipkin-reporter-brave` cung cấp việc báo cáo span đến Zipkin.

Tổ hợp Brave–Zipkin này được Spring Boot hỗ trợ trong [Tracing — OpenZipkin Brave With Zipkin](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html#actuator.micrometer-tracing.tracer-implementations.brave-zipkin).

Không cần thêm Spring Cloud Sleuth vào mẫu Spring Boot 3 này. Cũng không trộn thêm một bridge OpenTelemetry khi bài đã chọn Brave làm tracer.

## 4. Viết dịch vụ đặt hàng

### 4.1. OrderApplication.java

Tệp `order-service/src/main/java/com/example/order/OrderApplication.java`:

```java
package com.example.order;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
```

### 4.2. OrderController.java

Tệp `order-service/src/main/java/com/example/order/OrderController.java`:

```java
package com.example.order;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;

@RestController
public class OrderController {
    private static final Logger log =
            LoggerFactory.getLogger(OrderController.class);

    private final RestClient inventory;

    public OrderController(
            RestClient.Builder builder,
            @Value("${inventory.base-url}") String inventoryBaseUrl) {
        SimpleClientHttpRequestFactory requestFactory =
                new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(2000);
        requestFactory.setReadTimeout(3000);

        this.inventory = builder
                .baseUrl(inventoryBaseUrl)
                .requestFactory(requestFactory)
                .build();
    }

    @GetMapping("/orders/{productId}")
    public OrderView order(@PathVariable("productId") String productId) {
        log.info("order.start productId={}", productId);

        try {
            InventoryView result = inventory.get()
                    .uri("/inventory/{productId}", productId)
                    .retrieve()
                    .body(InventoryView.class);

            if (result == null) {
                throw new IllegalStateException("Inventory response is empty");
            }

            log.info("order.done productId={} available={}",
                    productId, result.available());
            return new OrderView(productId, result.available());
        } catch (RestClientResponseException exception) {
            log.error("order.inventory_error productId={} downstreamStatus={}",
                    productId, exception.getStatusCode().value());
            throw exception;
        }
    }

    public record InventoryView(String productId, boolean available) {
    }

    public record OrderView(String productId, boolean available) {
    }
}
```

Các điểm cần quan sát:

- `RestClient.Builder` được tiêm từ Spring Boot, rồi mới cấu hình base URL và request factory.
- URI dùng mẫu `/inventory/{productId}`; không tự ghép header trace bằng chuỗi.
- Hai log `order.start` và `order.done` bao quanh lời gọi đồng bộ tới kho.
- Giới hạn kết nối là 2.000 ms và đọc phản hồi là 3.000 ms; đây không phải một deadline tổng duy nhất cho mọi bước.
- Khi B trả mã HTTP lỗi, A ghi `downstreamStatus` rồi ném tiếp ngoại lệ. Mẫu chưa có lớp ánh xạ lỗi riêng.

Một điều kiện quan trọng của truyền ngữ cảnh tự động là dùng builder đã được Spring Boot cấu hình. Tạo client bằng `RestClient.create(...)` hoặc một builder mới ngoài cơ chế này có thể làm mất cấu hình quan sát cần thiết. Xem [Propagating Traces](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html#actuator.micrometer-tracing.propagating-traces).

Việc chọn request factory trong ví dụ vẫn đi qua builder được tiêm. Nó không thay bằng một RestClient hoàn toàn mới.

## 5. Viết dịch vụ kho

### 5.1. InventoryApplication.java

Tệp `inventory-service/src/main/java/com/example/inventory/InventoryApplication.java`:

```java
package com.example.inventory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InventoryApplication {
    public static void main(String[] args) {
        SpringApplication.run(InventoryApplication.class, args);
    }
}
```

### 5.2. InventoryController.java

Tệp `inventory-service/src/main/java/com/example/inventory/InventoryController.java`:

```java
package com.example.inventory;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class InventoryController {
    private static final Logger log =
            LoggerFactory.getLogger(InventoryController.class);

    @GetMapping("/inventory/{productId}")
    public InventoryView inventory(@PathVariable("productId") String productId) {
        if ("FAIL".equals(productId)) {
            log.warn("inventory.failure productId={}", productId);
            throw new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE,
                    "Inventory failure for tracing exercise");
        }

        boolean available = !"P-OUT".equals(productId);
        log.info("inventory.check productId={} available={}",
                productId, available);
        return new InventoryView(productId, available);
    }

    public record InventoryView(String productId, boolean available) {
    }
}
```

Ba mã sản phẩm tạo ba tình huống có chủ đích:

| productId | Kết quả ở B | Mục đích |
| --- | --- | --- |
| P100 | HTTP 200, available=true | Quan sát đường thành công |
| P-OUT | HTTP 200, available=false | Phân biệt kết quả nghiệp vụ âm với lỗi HTTP |
| FAIL | HTTP 503 | Quan sát đường lỗi qua hai dịch vụ |

Đây là quy tắc cố định phục vụ thí nghiệm, chưa phải cách kiểm tra tồn kho thật. B không tự đọc một header bất kỳ rồi ghi nó thành traceId; hạ tầng tracing tiếp nhận ngữ cảnh theo chuẩn truyền đã cấu hình.

## 6. Cấu hình tracing và logging ở cả hai bên

### 6.1. order-service/application.yml

Tệp `order-service/src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: order-service
  jmx:
    enabled: false

server:
  address: 127.0.0.1
  port: 8081

management:
  endpoints:
    enabled-by-default: false
    web:
      exposure:
        include: health
  endpoint:
    health:
      enabled: true
      show-details: never
  tracing:
    sampling:
      probability: 1.0
    propagation:
      type: w3c
    brave:
      span-joining-supported: false
  zipkin:
    tracing:
      endpoint: http://127.0.0.1:9411/api/v2/spans

logging:
  file:
    name: logs/order-service.log
  pattern:
    console: "%d{HH:mm:ss.SSS} %-5level [app=${spring.application.name} trace=%X{traceId:-} span=%X{spanId:-}] %logger{24} - %msg%n"
    file: "%d{HH:mm:ss.SSS} %-5level [app=${spring.application.name} trace=%X{traceId:-} span=%X{spanId:-}] %logger{24} - %msg%n"

inventory:
  base-url: http://127.0.0.1:8082
```

### 6.2. inventory-service/application.yml

Tệp `inventory-service/src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: inventory-service
  jmx:
    enabled: false

server:
  address: 127.0.0.1
  port: 8082

management:
  endpoints:
    enabled-by-default: false
    web:
      exposure:
        include: health
  endpoint:
    health:
      enabled: true
      show-details: never
  tracing:
    sampling:
      probability: 1.0
    propagation:
      type: w3c
    brave:
      span-joining-supported: false
  zipkin:
    tracing:
      endpoint: http://127.0.0.1:9411/api/v2/spans

logging:
  file:
    name: logs/inventory-service.log
  pattern:
    console: "%d{HH:mm:ss.SSS} %-5level [app=${spring.application.name} trace=%X{traceId:-} span=%X{spanId:-}] %logger{24} - %msg%n"
    file: "%d{HH:mm:ss.SSS} %-5level [app=${spring.application.name} trace=%X{traceId:-} span=%X{spanId:-}] %logger{24} - %msg%n"
```

### 6.3. Vì sao cần các thiết lập này?

Hai `spring.application.name` khác nhau giúp nhận biết dịch vụ trong log và backend. Cổng 8081 và 8082 cho phép chạy đồng thời trên một máy. Các đường dẫn tệp log khác nhau tránh hai tiến trình ghi vào cùng tệp.

Cả hai bên dùng W3C propagation. `span-joining-supported: false` chọn mô hình không dùng chung span ID giữa span phía client và phía server. Chính sách lấy mẫu và địa chỉ nhận span được khai báo rõ để dễ quan sát trong bài. Tra các khóa tại [Common Application Properties — tracing và Zipkin](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html).

Xác suất lấy mẫu 1.0 phục vụ thí nghiệm với ít yêu cầu. Nó không phải cấu hình mặc định cần sao chép nguyên sang mọi hệ thống có tải lớn. Với ngữ cảnh từ phía trước truyền vào, quyết định lấy mẫu còn có thể được tiếp nối từ ngữ cảnh đó; không dùng xác suất 1.0 để suy ra mọi trace chắc chắn đã tới backend.

Mẫu log chứa ba trường app, trace và span. `%X{traceId:-}` và `%X{spanId:-}` đọc MDC, không tự sinh định danh. Nếu không có span hiện hành, các trường này có thể trống. Do đó log khởi động chưa có traceId là bình thường.

Các endpoint Actuator HTTP chỉ mở health để kiểm tra tiến trình. Việc gửi trace tới Zipkin không đòi hỏi mở tất cả endpoint Actuator hoặc công bố một endpoint tên traces.

Các địa chỉ 127.0.0.1 áp dụng khi hai JVM chạy trực tiếp trên cùng máy. Nếu chuyển chúng vào container, phải thiết kế lại tên máy đích và mạng; localhost trong container không tự trỏ đến container Zipkin hoặc dịch vụ còn lại.

## 7. Khởi động theo đúng thứ tự

Thực hiện các lệnh tại root `tracing-two-services`.

### 7.1. Chạy Zipkin

Trong một terminal:

```powershell
docker run --rm --name tracing-lab-zipkin -p 127.0.0.1:9411:9411 openzipkin/zipkin
```

Lệnh giữ Zipkin ở foreground để dễ thấy trạng thái khởi động. Chờ server sẵn sàng. Có thể mở [Zipkin cục bộ](http://127.0.0.1:9411/zipkin/) để xem giao diện.

Cách chạy Docker cơ bản và chức năng truy tìm trace được giới thiệu trong [dự án OpenZipkin](https://github.com/openzipkin/zipkin). Mẫu dùng lưu trữ mặc định phục vụ thực hành; không coi trace trong container này là kho lưu trữ bền vững.

### 7.2. Tạo wrapper và đóng gói hai JAR

Trong terminal khác, dùng Gradle 8.5 đã chuẩn bị:

```powershell
gradle wrapper --gradle-version 8.5
.\gradlew.bat :order-service:bootJar :inventory-service:bootJar
```

Lần đầu cần tải plugin và dependency nếu chưa có trong cache. Hai JAR thu được:

```text
order-service/build/libs/order-service-1.0.0.jar
inventory-service/build/libs/inventory-service-1.0.0.jar
```

### 7.3. Chạy B rồi chạy A

Mở hai terminal, đều đứng tại root dự án.

Terminal B:

```powershell
java -jar inventory-service/build/libs/inventory-service-1.0.0.jar
```

Terminal A:

```powershell
java -jar order-service/build/libs/order-service-1.0.0.jar
```

Chờ cả hai ứng dụng khởi động xong. Tệp log tương ứng nằm tại `logs/order-service.log` và `logs/inventory-service.log` dưới root vì đó là thư mục làm việc của hai lệnh Java.

Kiểm tra sức khỏe nếu cần:

```powershell
curl.exe -i http://127.0.0.1:8081/actuator/health
curl.exe -i http://127.0.0.1:8082/actuator/health
```

Các yêu cầu health cũng có thể tạo dữ liệu quan sát. Vì vậy về sau tìm theo traceId của yêu cầu nghiệp vụ, không dựa vào tổng số trace hiển thị.

Trên Linux/macOS, dùng `curl` và `./gradlew` thay cho `curl.exe` và `.\gradlew.bat`.

## 8. Gửi một yêu cầu và đọc log theo ngữ cảnh

Gọi A, không gọi thẳng B trong bước đầu:

```powershell
curl.exe -i http://127.0.0.1:8081/orders/P100
```

Kỳ vọng HTTP 200 và JSON tương đương:

```json
{
  "productId": "P100",
  "available": true
}
```

Mỗi yêu cầu mới không mang ngữ cảnh từ trước thường tạo một trace mới. Sao chép traceId từ log `order.start`, rồi tìm nó ở cả hai tệp.

Một ví dụ log rút gọn dưới đây minh họa hình dạng; thời gian và các ID span là dữ liệu ví dụ, không phải stdout cố định:

```text
12:00:00.000 INFO [app=order-service trace=11111111111111111111111111111111 span=aaaaaaaaaaaaaaaa] OrderController - order.start productId=P100
12:00:00.005 INFO [app=inventory-service trace=11111111111111111111111111111111 span=bbbbbbbbbbbbbbbb] InventoryController - inventory.check productId=P100 available=true
12:00:00.010 INFO [app=order-service trace=11111111111111111111111111111111 span=aaaaaaaaaaaaaaaa] OrderController - order.done productId=P100 available=true
```

Cách đọc:

- Ba dòng cùng traceId nên có thể tìm chúng như một nhóm.
- Hai dòng A mang cùng spanId vì mã đang chạy trong cùng span xử lý yêu cầu của A.
- Dòng B có spanId khác vì đó là thao tác xử lý ở dịch vụ khác.
- Mã sản phẩm giúp hiểu tình huống; chính traceId mới là khóa liên kết lần gọi cụ thể khi có nhiều yêu cầu cho cùng sản phẩm.

Span HTTP client của A được hạ tầng quan sát tạo quanh lời gọi RestClient. Nó không bắt buộc có một dòng log nghiệp vụ riêng trong mẫu.

Trong một hệ thống nhiều máy, thứ tự timestamp giữa log của các máy có thể lệch do đồng hồ. Dùng quan hệ cha–con của span để hiểu luồng; không dựa hoàn toàn vào việc sắp các dòng log theo thời gian.

## 9. Kiểm chứng header W3C và tìm đúng trace

Header `traceparent` mang các thành phần dạng:

```text
version-trace-id-parent-id-trace-flags
```

Với phiên bản 00, trace-id có 32 ký tự hex và parent-id có 16 ký tự hex; hai ID không được toàn số 0. Khi A gọi B, parent-id truyền sang thể hiện span của bên gửi tại chặng đó. Định dạng được quy định trong [W3C Trace Context](https://www.w3.org/TR/trace-context/#traceparent-header).

Không lấy spanId trong log controller A rồi mặc định đó là parent-id mà B nhận. Giữa chúng còn có span HTTP client của A.

### Một lần gọi có traceId đã biết

Để dễ đối chiếu thủ công trong thí nghiệm, gửi đúng một lần yêu cầu sau:

```powershell
curl.exe -i -H "traceparent: 00-11111111111111111111111111111111-2222222222222222-01" http://127.0.0.1:8081/orders/P100
```

Khi ngữ cảnh hợp lệ được tiếp nhận, traceId cần tìm trong log hai dịch vụ là:

```text
11111111111111111111111111111111
```

`2222222222222222` đóng vai trò span cha giả lập từ phía người gọi. Bài không gửi span đó lên Zipkin, nên backend có thể không tìm thấy bản ghi cho cha ngoài hệ thống này. Đây không phải bằng chứng mất span A hoặc B.

Header cố định chỉ phục vụ một lần kiểm tra có kiểm soát. Không dùng lại cùng traceId cho nhiều yêu cầu độc lập vì chúng có thể bị hiểu thành một trace. Những lần gọi thông thường ở mục 8 để tracer tạo ngữ cảnh tự nhiên.

Tìm log bằng PowerShell:

```powershell
Select-String -Path logs/order-service.log,logs/inventory-service.log -SimpleMatch '11111111111111111111111111111111'
```

Nếu hai dịch vụ hiển thị hai traceId khác nhau, kiểm tra builder HTTP, định dạng propagation và sự tồn tại của header tại ranh giới A–B trước khi điều chỉnh mẫu logging.

TraceId là định danh tương quan, không phải thông tin xác thực hay bằng chứng người gọi đã được cấp quyền.

## 10. Đọc trace trên Zipkin rồi quay lại log

Sau khi yêu cầu kết thúc, chờ đợt gửi span và làm mới Zipkin. Tìm theo traceId vừa ghi nhận; tên nút/tính năng lọc có thể khác giữa các phiên bản giao diện.

Trong mô hình đã cấu hình, cần nhận ra các thao tác chính:

```text
Span cha bên gọi: 2222222222222222 (giả lập, không có bản ghi)
└── A: nhận GET /orders/{productId}
    └── A: gọi HTTP tới B
        └── B: nhận GET /inventory/{productId}
```

Đây là sơ đồ vai trò, không cam kết chuỗi tên span hiển thị đúng nguyên văn như trên. Tên cụ thể và các tag phụ thuộc quy ước của instrumentation.

Có thể kiểm tra dữ liệu trace bằng API Zipkin:

```powershell
$trace = Invoke-RestMethod -Uri 'http://127.0.0.1:9411/api/v2/trace/11111111111111111111111111111111'
$trace | Select-Object traceId,id,parentId,kind,@{Name='service';Expression={$_.localEndpoint.serviceName}}
```

API được mô tả tại [Zipkin API](https://zipkin.io/zipkin-api/). Khi dữ liệu chưa được gửi đến backend, gọi API ngay lập tức có thể chưa trả được trace; cần chờ và đối chiếu log báo cáo span.

Đọc theo thứ tự:

1. Tìm span phía server của order-service.
2. Tìm span phía client bên A và đối chiếu parentId của nó với id của span A.
3. Tìm span server của inventory-service và đối chiếu parentId với span client.
4. So sánh id của span server A/B với spanId trên log controller tương ứng.
5. Xem thời lượng, trạng thái và thông tin lỗi của từng chặng.

Nếu span A dài nhưng phần B xử lý ngắn, chưa thể kết luận B là nguồn toàn bộ độ trễ. Còn có thời gian phía A, kết nối, truyền dữ liệu hoặc chờ đợi. Các khoảng thời gian span lồng nhau chồng lấn, nên cộng tất cả duration sẽ đếm trùng thời gian.

Nếu chỉ có một ID trace trong log nhưng Zipkin chưa có dữ liệu, đó là một nhánh điều tra khác với việc A và B có hai traceId khác nhau. Một bên liên quan export/lấy mẫu/lưu trữ; bên kia liên quan truyền và tiếp nhận ngữ cảnh.

## 11. Tự động kiểm tra bằng chứng log của đường thành công

Bộ kiểm tra sau đọc tệp log theo đúng mẫu đã cấu hình. Nó kiểm tra dòng bắt đầu/kết thúc ở A và dòng kiểm tra hàng ở B cùng trace, hai dòng A cùng span, và B có span khác A.

Tệp `tools/TraceEvidenceCheck.java`:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class TraceEvidenceCheck {
    private static final Pattern CONTEXT = Pattern.compile(
            "\\[app=([^ ]+) trace=([0-9a-f]{32}) span=([0-9a-f]{16})\\]");

    private record Evidence(String app, String traceId, String spanId) {
    }

    private static Evidence latest(
            Path file, String traceId, String message) throws Exception {
        List<String> lines = Files.readAllLines(file);
        for (int index = lines.size() - 1; index >= 0; index--) {
            String line = lines.get(index);
            Matcher match = CONTEXT.matcher(line);
            if (line.endsWith(" - " + message)
                    && match.find()
                    && traceId.equals(match.group(2))) {
                return new Evidence(
                        match.group(1), match.group(2), match.group(3));
            }
        }
        throw new IllegalStateException(
                "Missing evidence in " + file + " for " + message);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3 || !args[0].matches("[0-9a-f]{32}")
                || args[0].equals("00000000000000000000000000000000")) {
            throw new IllegalArgumentException(
                    "Arguments: nonzero-32-hex-trace-id order-log inventory-log");
        }

        String traceId = args[0];
        Evidence start = latest(
                Path.of(args[1]), traceId, "order.start productId=P100");
        Evidence done = latest(
                Path.of(args[1]), traceId,
                "order.done productId=P100 available=true");
        Evidence inventory = latest(
                Path.of(args[2]), traceId,
                "inventory.check productId=P100 available=true");

        boolean services = start.app().equals("order-service")
                && done.app().equals("order-service")
                && inventory.app().equals("inventory-service");
        boolean sameTrace = start.traceId().equals(done.traceId())
                && start.traceId().equals(inventory.traceId());
        boolean stableOrderSpan = start.spanId().equals(done.spanId());
        boolean differentSpans = !start.spanId().equals(inventory.spanId());
        boolean nonzeroSpans =
                !start.spanId().equals("0000000000000000")
                && !inventory.spanId().equals("0000000000000000");

        System.out.println("same-trace=" + sameTrace);
        System.out.println("order-span-stable=" + stableOrderSpan);
        System.out.println("different-service-spans=" + differentSpans);

        if (!(services && sameTrace && stableOrderSpan
                && differentSpans && nonzeroSpans)) {
            throw new IllegalStateException("Trace evidence mismatch");
        }
        System.out.println("evidence=PASS");
    }
}
```

Đây là chương trình Java độc lập dùng thư viện chuẩn, chạy được bằng JDK 17 trở lên. Tại root dự án, sau lần gọi có traceId đã biết:

```powershell
javac -encoding UTF-8 -d tools tools/TraceEvidenceCheck.java
java -cp tools TraceEvidenceCheck 11111111111111111111111111111111 logs/order-service.log logs/inventory-service.log
```

Khi dữ liệu đáp ứng các điều kiện, stdout chính xác:

```text
same-trace=true
order-span-stable=true
different-service-spans=true
evidence=PASS
```

Nếu không tìm được dòng phù hợp, có spanId không hợp lệ theo điều kiện hoặc quan hệ kiểm tra bị sai, chương trình ném ngoại lệ và kết thúc không thành công.

Giới hạn của phép kiểm tra:

- Nó chứng minh các trường tương quan trong log tuân theo hợp đồng của bài.
- Nó không chứng minh span đã được xuất tới Zipkin.
- Nó không chứng minh quan hệ parentId trong dữ liệu backend.
- Nó chỉ chọn các dòng cho P100 và mẫu log đã định nghĩa.
- Nó không chứng minh hệ thống chống được việc mã ứng dụng giả mạo các trường log.

Vì vậy cần giữ cả kiểm tra log và kiểm tra trace trên backend. Không coi việc in cùng một chuỗi định danh vào hai tệp là đã triển khai distributed tracing.

## 12. Quan sát đường lỗi và phân biệt lỗi nghiệp vụ

### 12.1. Kết quả nghiệp vụ âm nhưng HTTP thành công

```powershell
curl.exe -i http://127.0.0.1:8081/orders/P-OUT
```

Kỳ vọng HTTP 200:

```json
{
  "productId": "P-OUT",
  "available": false
}
```

Log vẫn có `order.done` và `inventory.check`. Kết quả hết hàng trong quy ước này là dữ liệu nghiệp vụ, không tự biến HTTP thành lỗi.

### 12.2. B trả lỗi HTTP

```powershell
curl.exe -i http://127.0.0.1:8081/orders/FAIL
```

Trong mẫu chưa có lớp xử lý ngoại lệ riêng, B trả 503, lời gọi RestClient tại A ném ngoại lệ và yêu cầu tới A thường kết thúc bằng HTTP 500.

Tìm traceId từ `order.start productId=FAIL`, rồi đối chiếu:

- B có log `inventory.failure productId=FAIL`.
- A có log `order.inventory_error productId=FAIL downstreamStatus=503`.
- Không có log `order.done` cho lần gọi thất bại đó.
- Các span thể hiện trạng thái ở từng chặng; không giả định mã HTTP ở A phải giống mã HTTP ở B.

Không dùng tệp log của một lần gọi FAIL để chạy bộ kiểm tra P100 ở mục 11; bộ kiểm tra đó dành riêng cho đường thành công.

### 12.3. B không chạy hoặc kết nối thất bại

Dừng riêng tiến trình inventory-service và gọi lại A. Đây là lỗi kết nối/đọc, khác với việc đã nhận được HTTP 503.

`RestClientResponseException` trong mã chỉ bắt trường hợp đã có phản hồi HTTP lỗi. Lỗi mạng có thể đi theo một loại ngoại lệ khác; đừng chờ nhất thiết có dòng `order.inventory_error` với một mã HTTP.

Khi B chưa nhận được yêu cầu, việc không có log controller B là bằng chứng hợp lý. Kiểm tra span client A và lỗi kết nối trước khi kết luận propagation bị hỏng.

Khởi động lại B sau thí nghiệm; tạo một yêu cầu mới để kiểm tra đường thành công trở lại.

## 13. Bảng chẩn đoán khi liên kết không như mong đợi

| Hiện tượng | Nhánh kiểm tra |
| --- | --- |
| Hai bên có traceId khác nhau | Builder HTTP, instrumentation phía nhận, propagation, header bị proxy loại |
| Hai bên cùng traceId nhưng spanId khác | Phù hợp với các span riêng trong mô hình bài; xem parentId để xác nhận |
| A có traceId, B trống cả trace/span | Kiểm tra tracing bên B, MDC và vị trí phát sinh log |
| Log có đủ ID nhưng Zipkin không có trace | Exporter, endpoint /api/v2/spans, lấy mẫu, thời điểm gửi và backend |
| Zipkin có trace nhưng không có log liên quan | Mức log, vị trí tệp, mẫu log, bộ lọc và phạm vi thực thi |
| Chỉ thấy span A, không thấy span B | B có thực nhận yêu cầu không, B có export không, hay B tạo trace khác |
| Log khởi động có trace/span trống | Bình thường nếu không có span hiện hành |
| Ngữ cảnh mất sau khi chuyển sang executor hoặc luồng mới | Cơ chế truyền ngữ cảnh qua luồng; không chỉ là header HTTP |

Không tự tạo một UUID tại mỗi dịch vụ để làm traceId. Hai UUID khác nhau không nối được lời gọi; chép một UUID giống nhau vào MDC cũng chưa tạo ra các span có quan hệ cha–con.

Không tự đưa header Authorization hoặc toàn bộ payload vào log để tìm liên kết. Trong bài, traceId, spanId, tên dịch vụ, mã thao tác và productId thử nghiệm đã đủ để truy tìm.

Khi mở rộng sang xử lý bất đồng bộ, không mặc định MDC hoặc ngữ cảnh tracing tự đi theo mọi executor. Cần cơ chế hỗ trợ context propagation và phép kiểm tra riêng cho ranh giới đó.

## 14. Điều kiện hoàn thành và dọn thí nghiệm

Bài hoàn thành khi có đủ bằng chứng cho một lần gọi thành công:

- A nhận P100 và gọi B, phản hồi có available=true.
- Hai tệp log liên kết bằng cùng traceId.
- SpanId trên log phù hợp với span xử lý tại từng dịch vụ.
- Backend có các span chính cùng trace và quan hệ cha–con đúng.
- Bộ kiểm tra log báo PASS.
- Đã quan sát ít nhất một tình huống B trả lỗi và phân biệt nó với lỗi kết nối.

Khi kết thúc, dừng hai JVM bằng Ctrl+C tại terminal tương ứng. Dừng container của bài:

```powershell
docker stop tracing-lab-zipkin
```

Vì container được tạo bằng `--rm`, Docker xóa container sau khi dừng. Lưu lại bằng chứng cần thiết trước khi kết thúc nếu muốn giữ kết quả thực hành.

Điều cần mang sang hệ thống thực tế là cách lần theo một lần gọi bằng định danh và quan hệ span, rồi dùng log để hiểu quyết định tại từng chặng. Mức lấy mẫu, thời gian lưu, dữ liệu được ghi và quyền truy cập hệ thống quan sát cần được thiết kế theo môi trường vận hành cụ thể.
