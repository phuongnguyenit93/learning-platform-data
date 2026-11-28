# Gửi trace tới Zipkin hoặc OTLP

## 1. Mục tiêu bài thực hành tổng hợp

Spring Modulith giúp chia một ứng dụng Spring Boot thành các **application module**, tạo module graph và kiểm chứng phụ thuộc. Khi bật quan sát tương tác, tracing giúp trả lời câu hỏi mà sơ đồ tĩnh không thể tự trả lời: *một request thực sự đã đi qua những module nào, mất thời gian ở bước nào và lỗi ở đâu?*

Bài thực hành **“Gửi trace tới Zipkin hoặc OTLP”** trong module `SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY` hướng dẫn xây ứng dụng nhỏ có hai module `ordering` và `notification`, tạo trace bằng Micrometer Observation, rồi chọn một trong hai đường xuất:

- **Zipkin:** ứng dụng xuất span qua Zipkin HTTP API và xem trace trong giao diện Zipkin.
- **OTLP:** ứng dụng xuất span bằng OpenTelemetry Protocol (ví dụ OTLP/HTTP) tới OpenTelemetry Collector, quan sát spans mà Collector nhận, rồi có thể nối Collector tới backend tương thích để lưu và truy vấn lâu dài.

Hai đường xuất cùng phục vụ việc quan sát ứng dụng; **không cần bật cả hai để hoàn thành bài**. Ta sẽ dùng một bản ứng dụng chung, chọn bridge/exporter phù hợp với từng nhánh.

Khi hoàn thành, người học cần chứng minh được:

1. Spring Boot tạo spans cho HTTP request, một operation nghiệp vụ và xử lý sự kiện giữa application modules.
2. Dữ liệu được chuyển tới đích bằng cấu hình đúng giao thức, endpoint và exporter.
3. Trace hiển thị được tên dịch vụ, tên operation, duration và quan hệ cha-con phù hợp với xử lý đồng bộ.
4. Có thể dùng module graph, Actuator và event metrics để đối chiếu với trace khi chẩn đoán.
5. Không đưa access token, dữ liệu cá nhân, order ID động hoặc raw event payload vào metric labels và span attributes.

## 2. Kiến trúc thực hành và điều kiện chạy

Ta xây ứng dụng `modulith-tracing-demo`:

~~~mermaid
flowchart LR
    C["HTTP client"] --> B["Spring Boot"]
    subgraph M["Spring Modulith application"]
      O["ordering module"] --> N["notification module"]
    end
    B --> O
    B --> X["Micrometer Observation/Tracing"]
    X --> Z["Zipkin HTTP API"]
    X --> T["OTLP/HTTP Collector"]
~~~

Các bước thực tế:

- `POST /orders` gọi `OrderService` ở module `ordering`.
- `OrderService` phát `OrderPlaced`, một hợp đồng public ở package gốc của module.
- `NotificationListener` trong module `notification` xử lý event đồng bộ, tạo một observation có tên ổn định.
- Spring Boot và Micrometer dựng trace; exporter Zipkin hoặc OTLP gửi spans ra receiver.
- Người học kiểm tra trace tại Zipkin UI hoặc trong log debug của Collector.

Bản đầu dùng **listener đồng bộ** để quan hệ parent-child rõ ràng. Phần mở rộng cuối bài thử listener bất đồng bộ, context propagation, sampling và lỗi exporter.

### Yêu cầu môi trường

| Thành phần | Vai trò |
| --- | --- |
| JDK 21 | Chạy ví dụ Java |
| Maven 3.9+ | Build dự án |
| Spring Boot 3.4.x và Spring Modulith 1.3.x tương thích | Application, Actuator, cấu trúc module, observations |
| Micrometer Tracing và một exporter | Gửi span |
| Docker hoặc Docker Compose | Chạy Zipkin hoặc OpenTelemetry Collector cục bộ |
| HTTP client/cURL | Gọi API thử nghiệm |

Các phiên bản `3.4.3` và `1.3.3` dưới đây là **mốc ví dụ** của nhánh Spring Boot 3/Spring Modulith 1, không phải khẳng định chúng là bản mới nhất. Nếu dự án dùng nhánh mới hơn, cần chọn Spring Boot/Modulith BOM tương thích, xác minh lại dependency và tên property theo tài liệu đúng phiên bản. Không ghép ngẫu nhiên nhiều bridge tracing trong cùng một profile.

### Sự khác nhau giữa một số thuật ngữ

| Khái niệm | Nhiệm vụ |
| --- | --- |
| Spring Modulith | Nhận diện module, ranh giới, documentation và tương tác |
| Spring Boot Actuator | Endpoint quản trị và tích hợp Micrometer |
| Micrometer Observation | API ghi nhận operation và context quan sát |
| Micrometer Tracing bridge | Nối Observation với hệ tracing Brave hoặc OpenTelemetry |
| Zipkin reporter | Xuất spans theo API Zipkin |
| OpenTelemetry OTLP exporter | Xuất spans theo OTLP |
| Collector | Nhận, xử lý, chuyển spans tới backend hoặc debug exporter |
| Zipkin UI / trace backend | Tra cứu và đọc trace |

**Observation không tự đồng nghĩa với trace đã tới backend.** Để nhìn thấy trace, hệ thống cần bridge phù hợp, span exporter, receiver khả dụng, sampling cho phép, và pipeline không bỏ dữ liệu.

## 3. Cấu trúc dự án

~~~text
modulith-tracing-demo/
├── pom.xml
├── compose-otel.yaml                  # Nhánh OTLP
├── otel-collector.yaml                # Nhánh OTLP
└── src/
    ├── main/
    │   ├── java/com/example/shop/
    │   │   ├── ShopApplication.java
    │   │   ├── ordering/
    │   │   │   ├── OrderController.java
    │   │   │   ├── OrderService.java
    │   │   │   ├── PlaceOrder.java
    │   │   │   ├── OrderResult.java
    │   │   │   └── OrderPlaced.java
    │   │   └── notification/
    │   │       └── NotificationListener.java
    │   └── resources/
    │       ├── application.yml
    │       ├── application-local.yml
    │       ├── application-zipkin.yml
    │       └── application-otlp.yml
    └── test/java/com/example/shop/
        └── ModulithArchitectureTest.java
~~~

`ordering` và `notification` là hai subpackage trực tiếp của package chứa lớp `@SpringBootApplication`. Với mô hình phát hiện mặc định, Spring Modulith coi chúng là hai application modules. Kiểu sự kiện `OrderPlaced` nằm trong package gốc của `ordering` để module khác có thể tham chiếu qua API công khai.

## 4. Thiết lập Maven và tách hai nhánh exporter

Ví dụ `pom.xml` dưới đây giữ dependencies ứng dụng trong phần chung, dùng Maven profile để chọn **Brave + Zipkin** hoặc **OpenTelemetry + OTLP**. Khi tạo dự án thật, có thể lấy skeleton từ Spring Initializr rồi thêm phần Modulith/tracing tương đương.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.3</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>modulith-tracing-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
        <spring-modulith.version>1.3.3</spring-modulith.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.modulith</groupId>
                <artifactId>spring-modulith-bom</artifactId>
                <version>${spring-modulith.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.modulith</groupId>
            <artifactId>spring-modulith-starter-core</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.modulith</groupId>
            <artifactId>spring-modulith-observability</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.modulith</groupId>
            <artifactId>spring-modulith-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.modulith</groupId>
            <artifactId>spring-modulith-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.modulith</groupId>
            <artifactId>spring-modulith-docs</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <profiles>
        <profile>
            <id>zipkin</id>
            <dependencies>
                <dependency>
                    <groupId>io.micrometer</groupId>
                    <artifactId>micrometer-tracing-bridge-brave</artifactId>
                </dependency>
                <dependency>
                    <groupId>io.zipkin.reporter2</groupId>
                    <artifactId>zipkin-reporter-brave</artifactId>
                </dependency>
            </dependencies>
        </profile>

        <profile>
            <id>otlp</id>
            <dependencies>
                <dependency>
                    <groupId>io.micrometer</groupId>
                    <artifactId>micrometer-tracing-bridge-otel</artifactId>
                </dependency>
                <dependency>
                    <groupId>io.opentelemetry</groupId>
                    <artifactId>opentelemetry-exporter-otlp</artifactId>
                </dependency>
            </dependencies>
        </profile>
    </profiles>
</project>
~~~

Spring Boot quản lý versions của nhiều phụ thuộc tích hợp thông qua parent/BOM; Spring Modulith BOM quản lý các artifact Modulith. **Maven profile** `zipkin` và `otlp` quyết định thư viện có trong runtime classpath. **Spring profile** `zipkin` và `otlp` trong các file YAML chỉ quyết định cấu hình ứng dụng: chúng phải được chọn đồng bộ.

Nếu chạy với cả hai Maven profiles, có thể mang đồng thời hai bridge tracing lên classpath, gây hành vi auto-configuration không mong muốn. Bài này chọn **một Maven profile tại một thời điểm**.

## 5. Mã nguồn Spring Boot và hai module

### 5.1. Entrypoint

`src/main/java/com/example/shop/ShopApplication.java`:

~~~java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

### 5.2. Hợp đồng request, result và sự kiện

`ordering/PlaceOrder.java`:

~~~java
package com.example.shop.ordering;

public record PlaceOrder(String sku, int quantity) {
}
~~~

`ordering/OrderResult.java`:

~~~java
package com.example.shop.ordering;

public record OrderResult(String orderId, String status) {
}
~~~

`ordering/OrderPlaced.java`:

~~~java
package com.example.shop.ordering;

public record OrderPlaced(String orderId, String sku, int quantity) {
}
~~~

`OrderPlaced` nằm ở **package gốc của module ordering** để `notification` có thể tham chiếu theo API mặc định của module đóng. Trong thực tế, hợp đồng event nên chứa dữ liệu nghiệp vụ tối thiểu và tránh lưu secret hoặc full HTTP request. Ở ví dụ này ID xuất hiện trong event phục vụ nghiệp vụ, nhưng không được gắn vào low-cardinality metric tags.

### 5.3. Service tạo order và publish sự kiện

`ordering/OrderService.java`:

~~~java
package com.example.shop.ordering;

import java.util.UUID;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final ApplicationEventPublisher events;
    private final ObservationRegistry observations;

    public OrderService(ApplicationEventPublisher events,
                        ObservationRegistry observations) {
        this.events = events;
        this.observations = observations;
    }

    public OrderResult place(PlaceOrder request) {
        return Observation
                .createNotStarted("ordering.place-order", observations)
                .lowCardinalityKeyValue("module", "ordering")
                .lowCardinalityKeyValue("operation", "place-order")
                .observe(() -> {
                    if (request.sku() == null
                            || request.sku().isBlank()
                            || request.quantity() <= 0) {
                        throw new IllegalArgumentException(
                                "Invalid order request");
                    }

                    String orderId = UUID.randomUUID().toString();
                    events.publishEvent(new OrderPlaced(
                            orderId, request.sku(), request.quantity()));

                    return new OrderResult(orderId, "ACCEPTED");
                });
    }
}
~~~

Observation được tạo quanh operation nghiệp vụ. Đây là nguồn span thủ công dùng để kiểm chứng pipeline. Việc Spring Modulith tự quan sát một số lời gọi module tùy phiên bản và cấu hình có thể tạo thêm spans; khi đó xem trace thực tế rồi loại instrumentation trùng lặp không cần thiết.

### 5.4. REST controller

`ordering/OrderController.java`:

~~~java
package com.example.shop.ordering;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<OrderResult> place(
            @RequestBody PlaceOrder request) {
        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body(service.place(request));
    }
}
~~~

### 5.5. Listener tại module khác

`notification/NotificationListener.java`:

~~~java
package com.example.shop.notification;

import com.example.shop.ordering.OrderPlaced;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class NotificationListener {

    private final ObservationRegistry observations;

    public NotificationListener(ObservationRegistry observations) {
        this.observations = observations;
    }

    @EventListener
    public void on(OrderPlaced event) {
        Observation
            .createNotStarted(
                "notification.handle-order-placed", observations)
            .lowCardinalityKeyValue("module", "notification")
            .lowCardinalityKeyValue("event.type", "OrderPlaced")
            .observe(() -> {
                // Mô phỏng xử lý: tại đây có thể gọi email adapter.
                // Không ghi nguyên event hoặc orderId vào span tags.
                if (event.quantity() < 1) {
                    throw new IllegalStateException(
                            "Invalid event quantity");
                }
            });
    }
}
~~~

Listener hiện tại là **đồng bộ** (`@EventListener` không kèm `@Async`). Đường xử lý sẽ chạy trong cùng lời gọi publisher và thường có thể kế thừa observation context của operation cha. Đây là lựa chọn có chủ đích để người học dễ xác minh parent-child. Đoạn xử lý chỉ minh họa, chưa gửi email, chưa dùng database và chưa đảm bảo tính bền vững của event sau khi process dừng.

### 5.6. Kiểm thử kiến trúc module

`src/test/java/com/example/shop/ModulithArchitectureTest.java`:

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModulithArchitectureTest {

    @Test
    void verifiesApplicationModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Kiểm thử xác nhận phụ thuộc tĩnh giữa module theo các quy tắc Spring Modulith hỗ trợ. Nó **không kiểm chứng exporter đã gửi spans**; để làm điều đó cần chạy các bài kiểm tra end-to-end ở phần sau.

## 6. Cấu hình chung, local và profile exporter

`src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: modulith-tracing-demo

server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: "health"
  endpoint:
    health:
      show-details: never
  tracing:
    sampling:
      probability: 0.10
~~~

`application-local.yml`:

~~~yaml
spring:
  config:
    activate:
      on-profile: local

management:
  tracing:
    sampling:
      probability: 1.0
~~~

Bài thực hành dùng sampling 100% trong **local** để dễ tìm các trace vừa tạo. Production cần tỷ lệ theo nhu cầu quan sát và chi phí; sampling không phải cơ chế lọc dữ liệu nhạy cảm.

`application-zipkin.yml`:

~~~yaml
spring:
  config:
    activate:
      on-profile: zipkin

management:
  zipkin:
    tracing:
      endpoint: "http://localhost:9411/api/v2/spans"
~~~

`application-otlp.yml`:

~~~yaml
spring:
  config:
    activate:
      on-profile: otlp

management:
  otlp:
    tracing:
      endpoint: "http://localhost:4318/v1/traces"
~~~

Ví dụ OTLP sử dụng **HTTP/protobuf** trên cổng 4318. Nó khác với OTLP/gRPC thường dùng cổng 4317. Không gửi gRPC vào endpoint HTTP `/v1/traces` hoặc ngược lại. Cấu hình trên là kiểu property thường dùng cho Spring Boot 3.x với Micrometer tracing; khi chuyển nhánh Boot khác, phải đối chiếu cơ chế exporter/properties tương ứng.

**Lưu ý về `localhost`:** nếu ứng dụng Java chạy trên máy host và Zipkin/Collector chạy trong Docker với port publish ra host, `localhost` là đúng. Nếu cả Java và receiver chạy trong Docker Compose, `localhost` bên trong container Java là chính container Java; cần dùng tên service (ví dụ `http://zipkin:9411` hoặc `http://otelcol:4318`) theo mạng Compose.

## 7. Nhánh A — Gửi trace trực tiếp đến Zipkin

### 7.1. Chạy Zipkin cục bộ

Với Docker:

~~~bash
docker run --rm --name tracing-zipkin \
  -p 9411:9411 \
  openzipkin/zipkin:3
~~~

Lệnh trên minh họa cách khởi động Zipkin v3, expose cổng 9411 và dùng lưu trữ mặc định phục vụ thử nghiệm. Khi áp dụng ở môi trường thật, pin phiên bản image cụ thể theo quy trình dự án và cấu hình lưu trữ, truy cập, TLS, retention phù hợp.

Mở giao diện:

~~~text
http://localhost:9411
~~~

### 7.2. Chạy ứng dụng với Brave + Zipkin reporter

Mở terminal thứ hai; ví dụ PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "local,zipkin"
mvn -Pzipkin spring-boot:run
~~~

Ở môi trường bash:

~~~bash
SPRING_PROFILES_ACTIVE=local,zipkin \
  mvn -Pzipkin spring-boot:run
~~~

Hai lệnh đều chọn Maven profile `zipkin` (Brave bridge + Zipkin reporter) và Spring profiles `local,zipkin` (sampling và URL exporter). Kiểm tra console cho biết ứng dụng khởi động thành công trên cổng 8080 và không có exception auto-configuration.

### 7.3. Tạo request thử

~~~bash
curl --request POST "http://localhost:8080/orders" \
  --header "Content-Type: application/json" \
  --data '{"sku":"BOOK-001","quantity":2}'
~~~

Kết quả mong đợi tương tự:

~~~json
{
  "orderId": "6f84371a-7a64-4ba2-a83f-ae859b0e710e",
  "status": "ACCEPTED"
}
~~~

`orderId` minh họa là UUID ngẫu nhiên; mỗi lần gọi sẽ khác. Không dùng ID này làm span name hoặc metric tag.

### 7.4. Xác nhận trace tại Zipkin

Tại Zipkin UI, lọc service `modulith-tracing-demo` và khoảng thời gian có request. Trên giao diện hoặc qua API, bạn cần nhận diện được ít nhất operation HTTP và các observations đã được exporter ghi nhận, ví dụ:

~~~text
HTTP POST /orders
  ordering.place-order
    notification.handle-order-placed
~~~

Cây span trên là **kỳ vọng về quan hệ** cho listener đồng bộ trong ví dụ; tên span HTTP/chi tiết tự động và số span thật có thể khác theo instrumentation và phiên bản framework. Nếu Spring Modulith thêm span tương tác module, hãy xem chúng có bổ sung ngữ nghĩa hay đang trùng với span thủ công.

Để kiểm tra receiver, có thể gọi Zipkin API sau khi trace đã xuất:

~~~bash
curl "http://localhost:9411/api/v2/services"
~~~

Kỳ vọng có tên service sau khi spans được ghi. Exporter có thể dùng batch, nên nếu request vừa trả xong nhưng UI chưa có trace, trước tiên xác minh pipeline/receiver và hoạt động batch/export thay vì lập tức thay đổi sampling hoặc thêm nhiều spans.

## 8. Nhánh B — Gửi trace bằng OTLP/HTTP đến Collector

Nhánh này dùng **OpenTelemetry bridge và OTLP exporter**. Để thấy receiver có nhận dữ liệu hay không mà chưa cần triển khai một tracing backend khác, ta cấu hình Collector đưa spans tới `debug exporter`. Debug output chỉ phù hợp cho local/lab; không dùng để in payload trace chi tiết lên log production.

### 8.1. Cấu hình OpenTelemetry Collector

Tạo `otel-collector.yaml` tại thư mục gốc dự án:

~~~yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: "0.0.0.0:4318"

processors:
  batch: {}

exporters:
  debug:
    verbosity: detailed

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
~~~

Các ý chính:

- `receivers.otlp.protocols.http` lắng nghe OTLP/HTTP trên cổng 4318.
- `batch` gom dữ liệu trước khi chuyển đến exporter, giúp mô phỏng pipeline thực tế.
- `debug` ghi spans ra log của Collector, là cách xác nhận nhanh receiver hoạt động.
- Không có storage backend ở nhánh này; **debug exporter không phải hệ lưu trace để tìm kiếm lâu dài**.

`compose-otel.yaml`:

~~~yaml
services:
  otelcol:
    image: otel/opentelemetry-collector:0.104.0
    command: ["--config=/etc/otelcol/config.yaml"]
    volumes:
      - ./otel-collector.yaml:/etc/otelcol/config.yaml:ro
    ports:
      - "4318:4318"
~~~

Image tag `0.104.0` là ví dụ đã được cố định để bài thực hành tái lập; khi dùng bản Collector khác, kiểm tra exporter `debug`, cú pháp cấu hình và khả năng tương thích của bản đó.

### 8.2. Khởi động Collector

~~~bash
docker compose -f compose-otel.yaml up -d
docker compose -f compose-otel.yaml logs -f otelcol
~~~

Giữ cửa sổ log mở để quan sát output. Trong môi trường multi-user, Collector debug có thể in nhiều thuộc tính tracing, nên chỉ dùng dữ liệu giả và hạn chế quyền xem log này.

### 8.3. Chạy ứng dụng với OpenTelemetry bridge

PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "local,otlp"
mvn -Potlp spring-boot:run
~~~

Bash:

~~~bash
SPRING_PROFILES_ACTIVE=local,otlp \
  mvn -Potlp spring-boot:run
~~~

Sau khi ứng dụng sẵn sàng, gửi request giống phần Zipkin:

~~~bash
curl --request POST "http://localhost:8080/orders" \
  --header "Content-Type: application/json" \
  --data '{"sku":"BOOK-OTLP","quantity":1}'
~~~

### 8.4. Xác nhận bằng log Collector

Trong cửa sổ `docker compose logs`, tìm thông tin tương đương:

~~~text
ResourceSpans
  Resource attributes:
    service.name: modulith-tracing-demo
  ScopeSpans
    Span: ordering.place-order
      Trace ID: ...
      Span ID: ...
    Span: notification.handle-order-placed
      Trace ID: ...
      Parent ID: ...
~~~

Đây là **minh họa nội dung** cần nhận diện, không phải định dạng log chính xác của mọi phiên bản Collector. Cần có `ResourceSpans`, service name và thông tin span/trace ID; listener đồng bộ thường phải liên kết với trace của request ban đầu.

Nếu muốn **xem cây trace như UI Zipkin**, cần nối Collector tới backend hỗ trợ lưu/truy vấn, ví dụ một triển khai Jaeger, Tempo hoặc dịch vụ tracing phù hợp, rồi dùng exporter tương ứng. Đừng nhầm debug exporter với backend. Trong production, Collector phải có TLS, authentication, giới hạn tài nguyên, retry/queue và chính sách bảo mật thích hợp.

## 9. So sánh hai đường xuất trace

| Tiêu chí | Zipkin trực tiếp | OTLP/HTTP qua Collector |
| --- | --- | --- |
| Tracing bridge | `micrometer-tracing-bridge-brave` | `micrometer-tracing-bridge-otel` |
| Exporter | `zipkin-reporter-brave` | `opentelemetry-exporter-otlp` |
| Đích của ứng dụng | Zipkin HTTP API | OTLP receiver |
| URL local trong bài | `http://localhost:9411/api/v2/spans` | `http://localhost:4318/v1/traces` |
| Quan sát kết quả | Giao diện Zipkin | Log `debug` của Collector |
| Khả năng lưu/truy vấn trace | Zipkin có backend/UI | Collector cần backend bổ sung |
| Điểm cần kiểm tra | URL Zipkin khác URL OTLP | OTLP/HTTP khác OTLP/gRPC |

Nếu backend tương thích có OTLP receiver và bảo mật phù hợp, ứng dụng có thể xuất OTLP trực tiếp; Collector là thành phần để chuẩn hóa pipeline, xử lý và chuyển tiếp, không phải yêu cầu bắt buộc của giao thức.

## 10. Kiểm tra end-to-end ở từng chặng

Một request trả HTTP 201 **chưa chứng minh trace đã đến receiver**. Kiểm tra độc lập ba tầng:

### Tầng ứng dụng

~~~bash
curl --include --request POST "http://localhost:8080/orders" \
  --header "Content-Type: application/json" \
  --data '{"sku":"LAB-100","quantity":3}'
~~~

Kỳ vọng `201 Created` và JSON có `orderId`, `status=ACCEPTED`. Với PowerShell:

~~~powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8080/orders" -ContentType "application/json" -Body '{"sku":"LAB-100","quantity":3}'
~~~

### Tầng tracing/exporter

1. Xác nhận đúng Maven profile (`-Pzipkin` hoặc `-Potlp`) và Spring profiles (`local,zipkin` hoặc `local,otlp`).
2. Kiểm tra dependencies bằng `mvn -Pzipkin dependency:tree` hoặc `mvn -Potlp dependency:tree`; mỗi lần chạy chỉ dùng bridge dự kiến.
3. Xác minh sampling local bằng `management.tracing.sampling.probability=1.0`.
4. Kiểm tra URL và giao thức của exporter khớp receiver. `localhost` phải đúng từ mạng của process Java.
5. Xác minh exporter không báo lỗi kết nối, 404, sai content type hoặc authorization.
6. Xác nhận receiver có `service.name=modulith-tracing-demo` và các spans tên nghiệp vụ.
7. Đối chiếu trace ID/parent-child để kiểm tra listener đồng bộ kế thừa context.

### Tầng kiến trúc module

Dùng `ApplicationModules.verify()` để kiểm tra dependency giữa `notification` và API của `ordering`. Có thể sinh tài liệu module graph (với dependency `spring-modulith-docs` của phần 4):

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

class ModulithDocumentationTest {

    @Test
    void writesModuleGraph() {
        ApplicationModules modules =
                ApplicationModules.of(ShopApplication.class);
        modules.verify();
        new Documenter(modules).writeDocumentation();
    }
}
~~~

Sơ đồ module là **quan hệ phụ thuộc tĩnh**; trace là **đường thực thi của một request**. Kiểm tra cả hai khi đánh giá kiến trúc. Tài liệu sinh ra và metadata Modulith trong Actuator chỉ nên có trong phạm vi quản trị được kiểm soát.

## 11. Mở rộng: listener bất đồng bộ và context propagation

Listener `@EventListener` ở phần 5 chạy đồng bộ nên thường có thể kế thừa observation context của `ordering.place-order`. Để thử listener chạy trên thread khác, dùng executor có task decorator truyền context.

Trong Spring Boot 3.4.x/Spring Framework 6.2.x, có thể dùng `ContextPropagatingTaskDecorator`. Cần có Micrometer context propagation trên classpath; nếu dependency tree chưa cung cấp, bổ sung dependency:

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>context-propagation</artifactId>
</dependency>
~~~

Tạo `TraceAsyncConfiguration.java` tại package `com.example.shop`:

~~~java
package com.example.shop;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskDecorator;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class TraceAsyncConfiguration {

    @Bean("traceAwareExecutor")
    ThreadPoolTaskExecutor traceAwareExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("notification-");
        TaskDecorator decorator = new ContextPropagatingTaskDecorator();
        executor.setTaskDecorator(decorator);
        executor.initialize();
        return executor;
    }
}
~~~

Trên **method `on(OrderPlaced event)` đã có** ở listener, thêm annotation `@Async`:

~~~java
import org.springframework.scheduling.annotation.Async;

@Async("traceAwareExecutor")
@EventListener
public void on(OrderPlaced event) {
    // Giữ phần Observation của NotificationListener tại mục 5.5.
}
~~~

Đây là đoạn hướng dẫn **sửa method hiện có**, không tạo class thứ hai. Khi publisher gửi event bên trong observation scope, task decorator có thể chuyển ngữ cảnh đến thread xử lý.

Bộ kiểm tra:

- Listener thực sự được gọi; không kết luận từ HTTP response vì async có thể chạy sau khi response trả.
- Span listener có quan hệ trace hợp lý với request ban đầu.
- Gửi hai request liên tiếp qua cùng pool, xác nhận MDC/context của request A không xuất hiện trong B.
- Tạo lỗi giả ở listener và xem error/span status; không nuốt exception.
- Theo dõi thread pool queue, shutdown và task rejection.

Nếu chuyển sang `@ApplicationModuleListener` với giao dịch và xử lý after-commit, còn phải cấu hình transaction manager và kiểm thử event publication lifecycle. Bài cơ bản chưa có transaction manager, nên không được giả định durability, replay hoặc transaction guarantees. Với retry sau nhiều phút, một **trace mới có span link** tới publish context (nếu có lưu/khôi phục context) có thể phù hợp hơn ép một parent-child tree kéo dài.

## 12. Bảo mật và kiểm soát chi phí telemetry

Không đưa ID đơn hàng, email, token, raw HTTP payload hoặc serialized event vào span names, metric labels hoặc baggage. Ví dụ **không nên**:

~~~java
// ID thay đổi mỗi request, có thể gây metric cardinality rất cao.
Observation.createNotStarted("ordering.place-order", registry)
    .lowCardinalityKeyValue("order.id", orderId);
~~~

Nên sử dụng những giá trị có tập ổn định:

~~~text
service.name = modulith-tracing-demo
module = ordering
operation = place-order
event.type = OrderPlaced
outcome = success
~~~

Tránh các trường:

~~~text
authorization = Bearer eyJ...
customer.email = person@example.test
payment.card = 4111...
event.payload = toàn bộ dữ liệu JSON của người dùng
~~~

Các biện pháp cần kết hợp:

1. **Tại ứng dụng:** tạo span với tên/thuộc tính an toàn và có ý nghĩa; không sinh PII, secret.
2. **Tại Collector:** có thể thêm processor lọc/chuyển thuộc tính được phê duyệt, nhưng không dựa hoàn toàn vào Collector để bảo vệ secret.
3. **Tại backend:** TLS, authentication, phân quyền và retention.
4. **Tại exporter:** giám sát dropped spans, queue, lỗi kết nối và băng thông.
5. **Tại sampling:** chọn lượng dữ liệu vừa đủ cho điều tra; sampling không phải cơ chế giấu secret.

Dùng event metrics theo `module`, `event.type` và `outcome` để đo tỷ lệ lỗi/tần suất trên toàn hệ thống, vì traces có thể bị sampling loại bớt và không cho số đếm đầy đủ.

## 13. Các lỗi thường gặp và cách khoanh vùng

| Triệu chứng | Nguyên nhân có thể | Cách xác nhận |
| --- | --- | --- |
| API trả HTTP 201 nhưng không có trace | Sai profiles, exporter thiếu, sampling loại | Kiểm tra dependency tree, config hiệu lực và exporter logs |
| Zipkin không có tên service | Zipkin chưa chạy, URL sai hoặc export lỗi | Cổng 9411, `/api/v2/services`, thông báo gửi span |
| OTLP Collector không có `ResourceSpans` | Sai endpoint, sai protocol hoặc pipeline | Receiver HTTP 4318, đường `/v1/traces`, log container |
| OTLP trả HTTP 404 | URL thiếu `/v1/traces` hoặc receiver khác | Kiểm tra cấu hình `management.otlp.tracing.endpoint` |
| Connection refused | Receiver chưa chạy hoặc Java trỏ sai host/port | Port Docker, network và địa chỉ nhìn từ JVM |
| TLS/401/403 | Receiver yêu cầu HTTPS/authentication | Kiểm tra chứng chỉ và quyền cấu hình đúng nơi |
| Chỉ thấy HTTP server span | Observation chưa có tracing handler hoặc operation không được gọi | Kiểm tra bridge, code path, sampling và logs |
| Listener không có span | Event không chạy, context mất, exporter drop | Event processing state, span name và trace IDs |
| Span listener nằm ở trace khác | Async propagation không đúng hoặc lifecycle độc lập | Thử executor decorator, kiểm tra parent/link |
| Spans trùng lặp | Auto instrumentation và wrapper thủ công cùng đo một operation | So sánh tên, duration và thứ bậc spans |
| Trace IDs thành metric labels | Custom convention đưa ID động vào metric | Loại ID khỏi low-cardinality tags |
| Actuator vô tình công khai dữ liệu | Exposure hoặc cấu hình profile bị ghi đè | Test qua ingress, kiểm tra quyền |

### Quy trình phân nhánh khi không thấy trace

~~~mermaid
flowchart TD
    A["POST /orders trả 201?"] -->|Không| B["Sửa lỗi controller/service"]
    A -->|Có| C["Bridge và Spring/Maven profiles đúng?"]
    C -->|Không| D["Kiểm tra dependency và cấu hình hiệu lực"]
    C -->|Có| E["Exporter kết nối được receiver?"]
    E -->|Không| F["Sửa host, port, protocol, TLS, auth"]
    E -->|Có| G["Receiver thấy spans?"]
    G -->|Không| H["Kiểm tra sampling, queue/drop và receiver pipeline"]
    G -->|Có| I["Parent-child và module spans đúng?"]
    I -->|Không| J["Kiểm tra Observation và async context"]
    I -->|Có| K["PASS, đánh giá bảo mật và chi phí"]
~~~

Một số tình huống dễ nhầm:

- **Đổi Spring profile nhưng không đổi Maven profile:** YAML chỉ chọn endpoint, không bổ sung bridge/exporter cần thiết.
- **Chạy Java trong Docker:** `localhost` chỉ container Java; đổi thành tên service của receiver trên cùng mạng Compose.
- **Receiver có trace nhưng UI không thấy:** OTLP Collector đang dùng `debug exporter` và không có UI; hoặc người học tìm sai service/time window.
- **Thiếu trace sau khi gửi một request:** kiểm tra sampling và batch exporter trước; đừng thêm nhiều spans để đoán.
- **Sự kiện replay sau thời gian dài:** không giả định parent-child luôn nối tiếp request ban đầu.

## 14. Kiểm tra tính sẵn sàng trước khi dùng trong production

Cấu hình lab chứng minh pipeline gửi trace hoạt động, nhưng production cần thêm giới hạn:

| Hạng mục | Điều cần xác nhận |
| --- | --- |
| Endpoint và transport | TLS, xác thực, certificate và network policy |
| Collector | Resource limits, health, queue, backpressure, retry |
| Sampling | Tỷ lệ/chiến lược phù hợp traffic và khả năng điều tra |
| Storage/retention | Backend lưu và truy vấn trace, thời hạn, quyền truy cập |
| Data minimization | Không có secret, PII, raw event hay credential |
| Span names/attributes | Tên ổn định; không đưa unique IDs vào metric tags |
| Context propagation | Thread/async/event/retry được xử lý theo ngữ nghĩa thật |
| Export failure | Backend hỏng không làm dừng nghiệp vụ chính |
| Module boundaries | `ApplicationModules.verify()` đạt |
| Actuator exposure | Chỉ mở endpoint cần thiết, đúng quyền |
| Telemetry cost | Spans/sec, bytes, ingestion, queue và backend cost trong ngân sách |

Không bật sampling 100% vô thời hạn trên production chỉ vì bài lab chạy tốt. Việc thay đổi instrumentation hoặc sampling cần có giới hạn, khả năng rollback và quan sát được hiệu năng ứng dụng khi exporter trục trặc.

Nếu tích hợp HTTP client hoặc database spans tự động, hãy kiểm tra trace có duplicate spans với module observations hay không. Tracing nên giúp tìm lỗi mà không buộc người vận hành đọc hàng trăm span cho một request đơn giản.

## 15. Tiêu chí nghiệm thu dự án

| Mục tiêu | Bằng chứng cần nộp |
| --- | --- |
| Ứng dụng chạy và nhận request | `POST /orders` trả 201 cùng JSON kết quả |
| Nhận diện cấu trúc module | Hai module `ordering` và `notification`, kiểm tra `verify()` thành công |
| Có instrumentation | Có HTTP span và observations cho operation nghiệp vụ |
| Quan hệ trong trace | Listener đồng bộ thuộc đúng trace của request |
| Nhánh Zipkin | Zipkin UI hoặc API nhận service và spans |
| Nhánh OTLP | Collector debug logs có `ResourceSpans` và tên operations |
| Cấu hình rõ ràng | Một Maven profile và Spring profile tương ứng mỗi lần chạy |
| Bảo vệ dữ liệu | Không có token, email hay raw event payload trong spans/metrics |
| Mở rộng async (nếu làm) | Context propagation/cleanup có kết quả kiểm thử |
| Tài liệu kiến trúc | Module graph và mô tả luồng telemetry |

Ghi vào báo cáo thực hành: công cụ/versions, lệnh khởi chạy, request/response giả, tên service, tên spans, kết quả thử exporter và giải thích quan hệ cha-con. Nếu dùng screenshot hoặc log Collector, chỉ đính kèm dữ liệu đã làm sạch.

### Câu hỏi tự đánh giá

1. Zipkin HTTP API `/api/v2/spans` khác OTLP/HTTP `/v1/traces` như thế nào?
2. Vì sao HTTP 201 không chứng minh Zipkin hoặc Collector nhận trace?
3. Maven profile và Spring profile có vai trò khác nhau ở đâu?
4. Khi Java chạy trong Docker, `localhost:4318` trỏ tới đâu?
5. Một Micrometer Observation cần những thành phần nào để được xuất thành trace?
6. Vì sao `@EventListener` đồng bộ dễ kiểm tra parent-child hơn listener bất đồng bộ?
7. Nếu listener được retry lâu sau request, parent-child hay span link phản ánh thực tế tốt hơn?
8. Head sampling có thể làm mất trace lỗi hiếm như thế nào?
9. Vì sao `traceId` và `orderId` không nên là nhãn Counter/Timer?
10. Tại sao Collector `debug exporter` không thay thế một backend tracing có UI?
11. Vì sao cần kết hợp module graph, Actuator, event metrics và tracing khi đánh giá kiến trúc?

## 16. Checklist hoàn thành

- [ ] Đã chọn bộ phiên bản Spring Boot và Spring Modulith tương thích.
- [ ] Đã tạo ứng dụng Spring Boot với hai application modules.
- [ ] `OrderPlaced` là hợp đồng public của module `ordering`.
- [ ] Có observation nghiệp vụ tại `ordering` và `notification`.
- [ ] `ApplicationModules.verify()` được kiểm tra.
- [ ] Đúng Maven profile và Spring profile của nhánh exporter.
- [ ] Zipkin hoặc Collector có receiver endpoint chính xác.
- [ ] Có request thật và bằng chứng receiver đã nhận spans.
- [ ] Service name, operation names và trace IDs khớp kỳ vọng.
- [ ] Listener đồng bộ có parent-child đúng; async có kiểm tra propagation nếu sử dụng.
- [ ] Không có token, raw payload, email hay ID động trong metric labels.
- [ ] Đã phân biệt Collector debug với trace backend có lưu trữ/UI.
- [ ] Có quy trình kiểm tra exporter lỗi, sampling, port và profile.
- [ ] Hiểu giới hạn production về bảo mật, retention, sampling và chi phí.

**Kết quả cuối bài:** gửi được trace của ứng dụng Spring Modulith qua **Zipkin** hoặc **OTLP/HTTP**, xác minh receiver thực sự nhận spans và diễn giải được luồng từ HTTP request sang operation/module. Người học cũng phải biết kiểm tra cấu trúc module, giới hạn dữ liệu quan sát và các trường hợp context propagation có thể làm trace bất đồng bộ bị đứt.
