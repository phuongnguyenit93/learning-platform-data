# Profile local cho quan sát dễ kiểm tra

> **Chương:** Cấu hình môi trường  
> **Phạm vi:** Spring Modulith — sinh tài liệu ranh giới application module, kiểm tra module graph và quan sát tương tác giữa các module trong ứng dụng Spring Boot.  
> **Mục tiêu:** Có một môi trường `local` đủ tín hiệu để kiểm tra kiến trúc, Actuator, metric và trace, nhưng vẫn khởi động được khi chưa có hệ thống giám sát bên ngoài.

## 1. Bài toán: quan sát module ngay trên máy phát triển

Giả sử ứng dụng Spring Boot `store` có ba application module:

- `catalog`: quản lý mặt hàng;
- `orders`: tiếp nhận đơn hàng, phát hành sự kiện `OrderPlaced`;
- `billing`: nghe sự kiện và tạo công việc xuất hóa đơn.

Một lập trình viên thay đổi cách module `billing` tương tác với `orders`. Trước khi đưa lên môi trường dùng chung, cần trả lời các câu hỏi:

1. **Kiến trúc:** `billing` đang phụ thuộc những module nào? Có truy cập lớp `internal` của module khác hoặc tạo chu kỳ phụ thuộc không?
2. **Trạng thái lúc chạy:** Actuator có liệt kê đúng các module và mối quan hệ của chúng không?
3. **Sự kiện:** Thao tác tạo đơn hàng có phát hành `OrderPlaced` không? Có thể thấy số lần xử lý ở metric hoặc log không?
4. **Đường đi yêu cầu:** Một request HTTP đi qua `orders` rồi tới `billing` có tạo được thông tin trace hữu ích không?
5. **Bất đồng bộ:** Nếu listener chạy ở executor khác, trace context có được chuyển tiếp không?

Một **profile `local`** nên làm các việc này dễ kiểm tra bằng cách bật các điểm quan sát cần thiết, gắn nhãn môi trường, ghi log có correlation ID và ưu tiên địa chỉ loopback. Cấu hình chỉ tác động khi chủ động kích hoạt profile.

Cần phân biệt rõ bốn lớp:

| Lớp kiểm tra | Công cụ | Trả lời câu hỏi |
|---|---|---|
| Cấu trúc tĩnh | `ApplicationModules.verify()` | Ranh giới module và dependency có hợp lệ? |
| Tài liệu | `Documenter`, PlantUML, Module Canvas | Module graph và API đã công bố trông như thế nào? |
| Trạng thái runtime | `/actuator/modulith`, `/actuator/metrics` | Ứng dụng chạy thực tế công bố module và meter nào? |
| Quan sát giao dịch | Log có trace ID, tracing exporter, dashboard | Một tương tác đi qua các module và thread ra sao? |

**Lưu ý:** Sinh tài liệu và kiểm thử cấu trúc là việc ở build/test time. Profile chỉ quản lý cấu hình runtime; bật profile `local` không tự sinh sơ đồ và không thay `modules.verify()`.

## 2. Chuẩn bị dependency phù hợp

Ví dụ dành cho dự án sử dụng **Spring Boot 3.x**, **Spring Modulith 1.x** và Micrometer. Đặt phiên bản Spring Modulith qua BOM tương thích với bản Spring Boot đang dùng; nếu ứng dụng sử dụng Spring Boot 4 / Spring Modulith 2, cần đối chiếu lại dependency và tên thuộc tính theo tài liệu phiên bản tương ứng.

Trong `pom.xml` (chỉ là các phần cần ghép vào POM đã có Spring Boot parent hoặc BOM):

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.modulith</groupId>
            <artifactId>spring-modulith-bom</artifactId>
            <version>1.4.5</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <!-- HTTP endpoint demo và actuator -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <!-- Tích hợp quan sát module và endpoint Actuator Modulith -->
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-starter-insight</artifactId>
    </dependency>

    <!-- Expose metrics theo định dạng Prometheus tại /actuator/prometheus -->
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>

    <!-- Tracing trong tiến trình và correlation ID trong log -->
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-tracing-bridge-otel</artifactId>
    </dependency>

    <!-- Kiểm tra kiến trúc và sinh tài liệu khi chạy test -->
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
~~~

Phiên bản `1.4.5` trên chỉ minh họa cách khóa một bản BOM thuộc nhánh 1.x; **không coi đây là cặp tương thích mặc định với mọi bản Boot 3.x**. Trong dự án thực tế, chọn BOM được hướng dẫn cho bản Spring Boot đang dùng, đồng bộ toàn bộ dependency Spring Modulith rồi kiểm tra phân giải dependency.

Các thành phần có vai trò riêng:

- `spring-modulith-starter-insight` tích hợp khả năng quan sát và hỗ trợ đưa thông tin Modulith ra Actuator; đây là dependency quan trọng nếu muốn thấy ranh giới module ở runtime.
- `spring-boot-starter-actuator` cung cấp hạ tầng endpoint, health và metrics.
- `micrometer-registry-prometheus` cung cấp định dạng scrape Prometheus; thiếu registry này sẽ không có endpoint `prometheus` dù đã cấu hình exposure.
- `micrometer-tracing-bridge-otel` nối Micrometer Observation với OpenTelemetry tracing; **không tự tạo một giao diện xem trace**. Muốn gửi trace ra collector cần bổ sung exporter và collector riêng.
- `spring-modulith-starter-test` và `spring-modulith-docs` dành cho bài kiểm tra kiến trúc và sinh tài liệu. Chúng không phải phần cần bật bởi profile `local`.

Để quan sát từ HTTP đến các module, ứng dụng phải có một luồng nghiệp vụ thực sự phát sinh lời gọi hoặc sự kiện. Có dependency observability nhưng không có tương tác nào thì danh sách metric/span liên quan module có thể trống.

## 3. Tách cấu hình chung và cấu hình local

Giữ cấu hình chung gọn trong `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: store-modulith

management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Tạo `src/main/resources/application-local.yml`:

~~~yaml
server:
  address: 127.0.0.1
  port: 8080

management:
  server:
    address: 127.0.0.1
    port: 8081

  endpoints:
    web:
      exposure:
        include: health,info,modulith,metrics,prometheus

  endpoint:
    health:
      show-details: always

  metrics:
    tags:
      application: store-modulith
      environment: local

  tracing:
    sampling:
      probability: 1.0

logging:
  level:
    com.example.store: DEBUG
    org.springframework.modulith: INFO
  pattern:
    level: "%5p [traceId=%X{traceId:-},spanId=%X{spanId:-}]"
~~~

**Ý nghĩa từng nhóm cấu hình:**

| Cấu hình | Vì sao hữu ích khi kiểm tra local? |
|---|---|
| `server.address=127.0.0.1` | Demo HTTP chỉ lắng nghe trên máy phát triển. |
| `management.server.port=8081` | Tách endpoint quản trị khỏi API nghiệp vụ chạy trên port 8080. |
| `management.server.address=127.0.0.1` | Chỉ cho phép truy cập Actuator từ loopback của máy đang chạy ứng dụng. |
| `exposure.include=...` | Công bố đúng các endpoint cần xem thủ công. |
| `management.endpoint.health.show-details=always` | Hiển thị chi tiết health khi thử nghiệm; chỉ áp dụng ở local. |
| `management.metrics.tags.environment=local` | Gắn nhãn để nhận biết metric của môi trường phát triển. |
| `management.tracing.sampling.probability=1.0` | Thu thập toàn bộ trace đủ điều kiện được tạo ở local, thuận tiện cho thử nghiệm có ít request. |
| `logging.pattern.level` | Thêm trace ID/span ID vào dòng log nếu tracing đang hoạt động và layout log hỗ trợ MDC. |

Chọn port 8081 chỉ là quy ước trong ví dụ, có thể thay bằng port trống khác. Địa chỉ `127.0.0.1` có hiệu lực trong **network namespace của tiến trình**: khi chạy ứng dụng trong Docker/container và muốn truy cập từ host, cần cân nhắc cấu hình bind/port mapping phù hợp. Không sao chép cấu hình exposure hoặc mức sampling này nguyên xi sang production.

**Kích hoạt profile:** Spring Boot tự nạp `application-local.yml` khi profile `local` đang active. Không cần khai báo `spring.profiles.active` bên trong chính `application-local.yml`.

Có thể chạy ứng dụng đã đóng gói bằng:

~~~bash
java -jar target/store-modulith.jar --spring.profiles.active=local
~~~

Hoặc dùng Spring Boot Maven Plugin:

~~~bash
mvn spring-boot:run -Dspring-boot.run.profiles=local
~~~

Tên JAR phải đổi theo tên artifact thực tế. Khi khởi động, log nên cho thấy profile `local` được chọn; cổng ứng dụng 8080 và cổng management 8081 hoạt động. Trong môi trường phát triển có nhiều profile, tránh vô tình bật đồng thời cấu hình `prod` khiến các thuộc tính bị ghi đè theo thứ tự nạp cấu hình.

## 4. Kiểm tra nhanh bằng Actuator

Sau khi chạy ứng dụng với profile `local`, sử dụng terminal trên máy đang chạy ứng dụng:

~~~bash
curl -i http://127.0.0.1:8081/actuator/health
curl -i http://127.0.0.1:8081/actuator
curl -i http://127.0.0.1:8081/actuator/modulith
curl -i http://127.0.0.1:8081/actuator/metrics
curl -i http://127.0.0.1:8081/actuator/prometheus
~~~

Các kết quả cần kiểm tra:

1. `/actuator/health` trả về trạng thái ứng dụng (thường là `UP` khi các health indicator ổn định).
2. `/actuator` cung cấp các liên kết endpoint được công bố, tùy cấu hình discovery và bảo mật.
3. `/actuator/modulith` trả mô hình module mà Spring Modulith nhận diện khi ứng dụng chạy.
4. `/actuator/metrics` trả danh sách tên meter Micrometer đã đăng ký.
5. `/actuator/prometheus` trả chuỗi số liệu theo định dạng Prometheus nếu registry đã được cài đặt.

Với mô hình có `orders` và `billing`, thông tin ở `/actuator/modulith` có thể có dạng sau (rút gọn để giải thích ý nghĩa, cấu trúc chính xác tùy phiên bản):

~~~json
{
  "orders": {
    "displayName": "Orders",
    "basePackage": "com.example.store.orders",
    "dependencies": []
  },
  "billing": {
    "displayName": "Billing",
    "basePackage": "com.example.store.billing",
    "dependencies": [
      {"target": "orders", "types": ["USES_COMPONENT"]}
    ]
  }
}
~~~

Ở đây `orders` và `billing` là **định danh logic**. `basePackage` cho biết vị trí code. Một thay đổi package không nhất thiết phải làm đổi ID module nếu đã khai báo ID rõ ràng. Loại quan hệ `types` là dữ liệu được công cụ tính từ code, không nên gán cứng dựa trên ý định kiến trúc.

Nếu endpoint trả 404, lần lượt kiểm tra: đúng cổng 8081 hay chưa, profile `local` có được kích hoạt không, dependency `spring-modulith-starter-insight` có trên classpath không, và tên `modulith` có nằm trong exposure không. Nếu HTTP 401/403, kiểm tra quy tắc Spring Security thay vì kết luận endpoint chưa được tạo.

## 5. Tạo tương tác mẫu để thấy metric và trace

Actuator chỉ có ý nghĩa khi ứng dụng thực sự tạo tương tác. Dưới đây là mô hình thử nghiệm đơn giản ở các package trực tiếp dưới root `com.example.store`.

~~~text
com.example.store
├── StoreApplication.java
├── orders
│   ├── OrderService.java
│   ├── OrderPlaced.java
│   └── OrderDemoController.java
└── billing
    └── BillingListener.java
~~~

Để thuận tiện, lớp khởi động ở `com.example.store`:

~~~java
package com.example.store;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StoreApplication {
    public static void main(String[] args) {
        SpringApplication.run(StoreApplication.class, args);
    }
}
~~~

Trong `orders/OrderPlaced.java`:

~~~java
package com.example.store.orders;

public record OrderPlaced(String orderId) {}
~~~

Trong `orders/OrderService.java`:

~~~java
package com.example.store.orders;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private static final Logger log =
        LoggerFactory.getLogger(OrderService.class);

    private final ApplicationEventPublisher publisher;

    public OrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void create(String orderId) {
        log.info("Accepting order {}", orderId);
        publisher.publishEvent(new OrderPlaced(orderId));
    }
}
~~~

Trong `orders/OrderDemoController.java`:

~~~java
package com.example.store.orders;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/demo/orders")
public class OrderDemoController {
    private final OrderService service;

    public OrderDemoController(OrderService service) {
        this.service = service;
    }

    @PostMapping("/{id}")
    public ResponseEntity<Void> create(@PathVariable String id) {
        service.create(id);
        return ResponseEntity.accepted().build();
    }
}
~~~

Trong `billing/BillingListener.java`:

~~~java
package com.example.store.billing;

import com.example.store.orders.OrderPlaced;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class BillingListener {
    private static final Logger log =
        LoggerFactory.getLogger(BillingListener.class);

    @EventListener
    public void on(OrderPlaced event) {
        log.info("Billing received order {}", event.orderId());
    }
}
~~~

Ở ví dụ này, `@EventListener` chạy **đồng bộ** theo cơ chế mặc định của Spring khi không cấu hình executor bất đồng bộ cho event multicaster. Vì vậy log trong `OrderService` và `BillingListener` thường nằm trong cùng HTTP request và trace context. Đây là kịch bản nền đơn giản trước khi kiểm thử propagation qua luồng khác.

Kích hoạt request:

~~~bash
curl -i -X POST http://127.0.0.1:8080/demo/orders/ORD-1001
~~~

Kết quả cần thấy:

- HTTP 202 Accepted từ controller.
- Log `Accepting order ORD-1001` và `Billing received order ORD-1001`.
- Nếu tracing hoạt động, log có `traceId`, `spanId`; các dòng của cùng thao tác có thể chung trace ID, còn span ID có thể khác nhau vì mỗi đoạn xử lý có span riêng.
- Ở `/actuator/metrics`, meter về HTTP thường xuất hiện sau request, và các meter về module/event **chỉ xuất hiện khi phiên bản, dependency và điểm instrumentation hỗ trợ đồng thời đã có hoạt động được quan sát**.

Lưu ý: `billing` phụ thuộc vào public type `OrderPlaced` thuộc package API của `orders`, không truy cập class ở `orders.internal`. Việc đổi sự kiện thành `@ApplicationModuleListener` không phải thay thế tương đương một-một: annotation đó mang ngữ nghĩa xử lý sự kiện theo giao dịch và bất đồng bộ; nó cần ngữ cảnh giao dịch commit và cấu hình executor phù hợp.

## 6. Đọc metrics đúng cách

Liệt kê các meter đang có:

~~~bash
curl -s http://127.0.0.1:8081/actuator/metrics
~~~

Ví dụ hỏi một meter phổ biến về HTTP server:

~~~bash
curl -s http://127.0.0.1:8081/actuator/metrics/http.server.requests
~~~

Truy vấn có thể lọc theo tag, nếu meter và tag thực tế đã tồn tại:

~~~text
GET /actuator/metrics/http.server.requests?tag=method:POST
~~~

Các loại metric cần phân biệt:

| Loại | Ví dụ điều cần quan sát | Lưu ý |
|---|---|---|
| HTTP | Số lượt, thời lượng và trạng thái request | Phản ánh cạnh vào ứng dụng, chưa cho biết toàn bộ module graph |
| JVM/process | Heap, thread, CPU, GC | Giúp nhận diện hiệu năng môi trường local |
| Event/module | Event được phát hành, lượt gọi hoặc xử lý ở ranh giới module | Phụ thuộc cơ chế observability mà phiên bản Spring Modulith đang dùng cung cấp |
| Business metric tự định nghĩa | Số đơn được tạo, số hóa đơn được phát hành | Cần instrument thêm trong ứng dụng để có ý nghĩa nghiệp vụ |

Không giả định tên metric event cố định giữa các phiên bản Modulith. Quy trình đúng là **liệt kê tên meter trước, phát sinh sự kiện, liệt kê lại, rồi kiểm tra meter có thực**. Một số metric chỉ được tạo sau lần tương tác đầu tiên. Nếu meter có tag `module.identifier`, dùng tag đó để đối chiếu module; nếu không có, không nên suy luận ID module từ tên Java class.

Prometheus trả tên metric được chuẩn hóa cho hệ thống scrape, chẳng hạn dấu chấm được đổi thành dấu gạch dưới. Vì thế tên trong `/actuator/metrics` có thể không trùng hoàn toàn với tên xuất hiện tại `/actuator/prometheus`. Khi lập dashboard, chọn đúng tên theo hệ thống thu thập.

### Bài thực nghiệm nhỏ

1. Mở `/actuator/metrics` và ghi nhận tên meter liên quan trước thao tác.
2. Gửi ba request `POST /demo/orders/{id}` với ID khác nhau.
3. Mở lại `/actuator/metrics` và kiểm tra `http.server.requests` (hoặc meter tương đương của phiên bản), số mẫu và tag `uri`, `method`, `status`.
4. Tìm thêm meter/module tag liên quan event nếu có; xác minh mức tăng sau thao tác.
5. Trả lời: metric cho biết **đã xử lý bao nhiêu**; trace cho biết **một lần xử lý đi qua đâu**. Hai nguồn này bổ sung cho nhau.

## 7. Tracing local theo hai cấp độ

### Cấp 1: không cần collector — đọc trace ID trong log

Ở cấu hình `application-local.yml`, `management.tracing.sampling.probability=1.0` giúp thuận tiện thử các trace được hệ thống instrumentation tạo ra. Khi có `micrometer-tracing-bridge-otel`, HTTP server observation thông thường có thể tạo trace/span, và logback MDC thể hiện ID theo mẫu:

~~~text
INFO [traceId=36f0676b7b1d4e6f8a7e9fbe24c12abc,spanId=691dbc5109b905d4] Accepting order ORD-1001
INFO [traceId=36f0676b7b1d4e6f8a7e9fbe24c12abc,spanId=691dbc5109b905d4] Billing received order ORD-1001
~~~

Đây là **giá trị minh họa**; ID thực tế được tạo theo từng request. Nếu thấy `traceId=-` và `spanId=-`, xác minh tracing bridge, classpath, đoạn xử lý có active observation/span hay không và cấu hình logback. Nếu dự án có `logback-spring.xml` riêng, `logging.pattern.level` có thể không chi phối layout mong muốn; cần kiểm tra pattern trong cấu hình logging thực tế.

Log có trace ID là cách nhanh để nhóm các dòng log, nhưng **không tương đương một trace visualization đầy đủ**: muốn xem cây span, thời lượng và parent/child relationship, dùng một exporter cùng backend hỗ trợ trace.

### Cấp 2: tùy chọn exporter OTLP và collector local

Chỉ bật thêm khi đã có collector tương thích OpenTelemetry OTLP đang lắng nghe. Thêm dependency:

~~~xml
<dependency>
    <groupId>io.opentelemetry</groupId>
    <artifactId>opentelemetry-exporter-otlp</artifactId>
</dependency>
~~~

Tạo `src/main/resources/application-local-otel.yml` để giữ tính năng này tùy chọn:

~~~yaml
management:
  otlp:
    tracing:
      endpoint: http://127.0.0.1:4318/v1/traces
~~~

Khởi chạy với cả hai profile:

~~~bash
java -jar target/store-modulith.jar --spring.profiles.active=local,local-otel
~~~

Ở ví dụ này, `4318` là cổng thường dùng cho OTLP/HTTP. Endpoint và exporter phải cùng giao thức; cấu hình không thể gửi thành công tới collector chỉ mở OTLP/gRPC trên `4317`. Collector có thể chuyển dữ liệu sang Zipkin, Jaeger hoặc một trace backend khác, tùy cấu hình triển khai. Nếu không có collector, chỉ bật `local` để tránh thông báo lỗi kết nối exporter.

Khi xem trace, kiểm tra tên service, root HTTP span, span nội bộ và các attribute định danh module (nếu instrumentation của Spring Modulith phát hành chúng). Không ép mọi phiên bản phải có cùng tên span hoặc bộ attribute; **kiểm tra những gì được sinh ra thật**.

## 8. Kiểm chứng context propagation khi chuyển sang xử lý bất đồng bộ

Với listener đồng bộ, trace context thường nằm trên cùng thread. Khi chuyển listener qua executor hoặc message broker, việc truyền context phải được cấu hình và kiểm tra riêng.

Ví dụ executor có `ContextPropagatingTaskDecorator`, khả dụng với Spring Framework 6.1+ và thư viện Micrometer Context Propagation phù hợp trên classpath:

~~~java
package com.example.store;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncObservationConfig {

    @Bean("observedExecutor")
    public ThreadPoolTaskExecutor observedExecutor() {
        var executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setThreadNamePrefix("observed-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        executor.initialize();
        return executor;
    }
}
~~~

Một listener bất đồng bộ sử dụng **đúng executor này**:

~~~java
package com.example.store.billing;

import com.example.store.orders.OrderPlaced;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

@Component
public class AsyncBillingListener {
    private static final Logger log =
        LoggerFactory.getLogger(AsyncBillingListener.class);

    @Async("observedExecutor")
    @EventListener
    public void on(OrderPlaced event) {
        log.info("Async billing received order {}", event.orderId());
    }
}
~~~

Đây là phương án **thay listener đồng bộ trong ví dụ**, không đồng thời đăng ký cả `BillingListener` và `AsyncBillingListener` nếu chỉ muốn xử lý hóa đơn một lần. Khi dùng `@ApplicationModuleListener` của Spring Modulith, phải tính đến executor mà annotation đó sử dụng và ngữ nghĩa transaction commit, không mặc định rằng bean `observedExecutor` sẽ được chọn.

Cần đối chiếu:

| Bước | Kết quả cần kiểm tra |
|---|---|
| HTTP request vào `orders` | Có trace ID A khi HTTP server span hoạt động |
| `OrderService` phát sự kiện | Log cho biết request thực sự đã phát event |
| `AsyncBillingListener` xử lý | Chạy ở thread `observed-*` và có trace ID tương ứng |
| Quan hệ span | Backend trace cho thấy quan hệ hợp lý, hoặc log cho thấy liên tục trace context |
| Định danh module | Module ID tương ứng `orders` và `billing` nếu instrumentation cung cấp thông tin này |

**Cảnh báo về suy luận:** Hai log có cùng `traceId` cho thấy chúng được gắn cùng ngữ cảnh trace; chưa đủ để xác minh parent/child span hay thứ tự toàn bộ nghiệp vụ. Kiểm tra span trong backend khi cần kết luận về quan hệ nhân quả. Ngược lại, bật sampling 100% không tự sửa một executor thiếu context propagation.

Nếu ứng dụng dùng message broker, `TaskDecorator` trong tiến trình chưa đủ: trace headers cần được inject lúc gửi và extract lúc nhận thông điệp. Việc truyền context qua mạng là một bước riêng.

## 9. So sánh module graph với quan sát runtime

Actuator giúp xem mô hình module của phiên bản ứng dụng đang chạy; `Documenter` tạo tài liệu để review kiến trúc. Cả hai nên dựa trên cùng source code.

Ví dụ test dùng Spring Modulith:

~~~java
package com.example.store;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

class ModuleArchitectureTest {

    @Test
    void verifyAndDocumentModules() {
        ApplicationModules modules =
            ApplicationModules.of(StoreApplication.class);

        // Xác minh dependency cycles và các ràng buộc truy cập module.
        modules.verify();

        new Documenter(modules)
            .writeModulesAsPlantUml()
            .writeIndividualModulesAsPlantUml()
            .writeModuleCanvases();
    }
}
~~~

Sơ đồ phụ thuộc mong muốn với ví dụ ở trên (mũi tên chỉ phụ thuộc ở source code):

~~~mermaid
flowchart LR
    C["catalog"]
    O["orders\npublish OrderPlaced"]
    B["billing\nlisten OrderPlaced"]
    B -->|tham chiếu kiểu OrderPlaced| O
~~~

`catalog` không tự có cạnh chỉ vì được khai báo là một module. Kiểm tra thực tế mới cho biết phụ thuộc nào tồn tại. Nếu test `verify()` thất bại do truy cập class `internal` hoặc chu kỳ, hãy sửa source code/ranh giới module; không thể chữa lỗi kiến trúc chỉ bằng `application-local.yml`.

Lập bảng đối chiếu trước và sau thay đổi:

| Tín hiệu | Dùng để kiểm tra | Điều kiện đạt |
|---|---|---|
| `modules.verify()` | Ràng buộc tĩnh | PASS |
| Documenter PlantUML | Node/edge ở mức module | Phù hợp thiết kế đã thống nhất |
| `/actuator/modulith` | Mô hình module runtime | ID, base package và dependency đúng |
| `/actuator/metrics` | Số liệu tổng hợp | Có meter mong đợi sau tương tác |
| Log MDC | Correlation tại local | Đọc được trace ID từ luồng yêu cầu |
| Trace backend (nếu bật) | Đường đi và thời lượng | Span và context khớp các thao tác kiểm thử |

## 10. Khi profile local không cho thấy dữ liệu

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| `/actuator/modulith` trả 404 | Thiếu insight/Actuator, profile không active hoặc endpoint chưa exposure | Kiểm tra dependency, profile, `/actuator` và cổng 8081 |
| `/actuator/prometheus` trả 404 | Chưa có Prometheus registry | Kiểm tra `micrometer-registry-prometheus` |
| `/actuator/metrics` không có meter sự kiện | Chưa phát sự kiện, phiên bản không instrument điểm đó hoặc thiếu dependency | Thử request trước, xem lại tên meter thực và khả năng observability của phiên bản |
| Log hiện `traceId=-` | Không có span đang active, thiếu bridge hoặc layout logging ghi MDC không đúng | Kiểm tra classpath và correlation trên một HTTP request |
| Tracing backend không có dữ liệu | Chưa cấu hình exporter, collector chưa chạy hoặc sai giao thức/địa chỉ | Kiểm tra profile `local-otel`, cổng 4318, collector và log exporter |
| Listener async mất trace ID | Executor không truyền context | Xác nhận decorator áp dụng **đúng executor** của listener |
| Test module PASS nhưng runtime khác kỳ vọng | So nhầm build/profile, cấu trúc classpath hoặc module discovery | So build đang chạy, tập ID và base package thực tế |
| Chạy container không gọi được Actuator từ host | Bind `127.0.0.1` trong container | Điều chỉnh port mapping và bind theo network context |
| Có trace nhưng không thấy “module span” | Chưa có lời gọi/module interaction được instrument, hoặc phiên bản có mô hình span khác | Kiểm tra luồng xử lý thật và tài liệu observability của phiên bản |

## 11. Checklist nghiệm thu

Hoàn thành bài thực hành khi có thể chứng minh:

- Ứng dụng khởi động với profile `local` và có log xác nhận profile được chọn.
- HTTP API phục vụ trên port 8080; Actuator phục vụ qua loopback trên port 8081.
- `/actuator/health` truy cập được; `/actuator/modulith` liệt kê các module đang chạy.
- `ApplicationModules.verify()` PASS và `Documenter` tạo được sơ đồ/Canvas từ cấu trúc source.
- Gửi thử request tạo đơn hàng và thấy log tại `orders` cùng `billing`.
- `/actuator/metrics` phản ánh request; nếu meter module/event được hỗ trợ, kiểm tra thêm dữ liệu phát sinh từ tương tác.
- Log có trace ID có ý nghĩa khi instrumentation tạo span; có thể bật profile `local-otel` nếu muốn dùng backend tracing.
- Nếu kiểm thử listener async, xác minh executor được dùng có context propagation và trace không bị ngắt ngoài ý muốn.
- Profile local không bị bật mặc định trong triển khai production; thiết lập exposure, log level và sampling của production được quản lý riêng.

**Câu hỏi tự đánh giá:**

1. Vì sao `application-local.yml` có thể giúp quan sát metric và trace, nhưng không thể thay test `ApplicationModules.verify()`?
2. Vì sao xuất hiện metric `http.server.requests` chưa chứng minh được giao tiếp `orders → billing` là đúng?
3. Với cùng một request, làm cách nào phân biệt việc thiếu span vì không có instrumentation và vì context không truyền qua executor?
4. Vì sao nên tách cấu hình collector OTLP thành profile `local-otel` tùy chọn thay vì đưa vào mọi lần chạy local?

## 12. Tham khảo

- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): endpoint exposure và cách truy cập.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): Micrometer Observation và tracing.
- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): Actuator, observability và tín hiệu liên quan module.
- [Spring Modulith — Documenting Application Modules](https://docs.spring.io/spring-modulith/reference/documentation.html): module graph, PlantUML và Module Canvas.
- [Spring Framework — Task Execution](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@Async`, task executor và cấu hình bất đồng bộ.

> **Ghi nhớ:** Profile `local` giúp tạo môi trường quan sát có thể lặp lại. Hãy kiểm tra **mô hình module**, **dữ liệu vận hành** và **trace context** như ba bằng chứng bổ sung cho nhau; mỗi bằng chứng chỉ khẳng định đúng phần mà nó đo được.
