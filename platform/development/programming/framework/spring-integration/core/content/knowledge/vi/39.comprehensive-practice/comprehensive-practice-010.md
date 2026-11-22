# Thêm metrics và message history

## 1. Mục tiêu thực hành

Trong chương **Thực hành tổng hợp** của **SPRING_INTEGRATION_CORE**, bài này bổ sung khả năng quan sát cho một luồng xử lý đơn hàng viết bằng Java DSL. Luồng sử dụng `Message`, `MessageChannel`, transformer, service activator và gateway; từ đó trả lời được ba câu hỏi:

- Hệ thống xử lý được bao nhiêu yêu cầu, có bao nhiêu lần thất bại và mất bao lâu?
- Một message cụ thể đã đi qua những thành phần nào trước khi thành công hoặc gặp lỗi?
- Khi thấy một chỉ số bất thường, cần kiểm tra dữ liệu nào để tìm nguyên nhân?

Sau bài học, bạn có thể bật metrics cho các thành phần tích hợp, bổ sung chỉ số nghiệp vụ có phạm vi rõ ràng, đọc message history ở đầu ra và tại điểm lỗi, đồng thời viết kiểm thử xác nhận những tín hiệu đó.

**Mốc API của ví dụ:** Java 17 trở lên, Spring Boot 3.5.x và Spring Integration 6.5.x. Hãy để BOM của Spring Boot quản lý phiên bản dependency; đây là mốc để tái hiện bài học, không phải tuyên bố về phiên bản mới nhất. Cấu hình chính sử dụng metrics Micrometer trực tiếp; phần Observation được trình bày riêng để bạn nhận biết sự thay đổi tên meter.

## 2. Chọn tín hiệu đúng với câu hỏi

| Tín hiệu | Câu hỏi phù hợp | Dữ liệu trong bài |
| --- | --- | --- |
| Metrics | Trong một khoảng thời gian, luồng có hoạt động bình thường không? | Số lần gửi thành công/thất bại, thời gian xử lý, số đơn được chấp nhận |
| Message history | Message đang xem đã đi qua đâu? | Tên component, loại component, timestamp trong header `history` |
| Log có ngữ cảnh | Lần xử lý cụ thể đã gặp chuyện gì? | `requestId`, loại lỗi, danh sách tên component |
| Distributed tracing | Một yêu cầu đi qua nhiều dịch vụ mất thời gian ở đâu? | Trace/span và thông tin truyền ngữ cảnh giữa các tiến trình |

Message history đi cùng một message nên rất hữu ích khi điều tra một trường hợp cụ thể. Để xem xu hướng của hàng nghìn message, hãy dùng metrics. Để nối các sự kiện thuộc cùng một yêu cầu, bài sử dụng header `requestId`; không đưa giá trị này vào tag của meter.

### 2.1. Counter, Timer và Gauge

- **Counter:** số sự kiện tích lũy, chẳng hạn số lần nghiệp vụ chấp nhận đơn.
- **Timer:** số lần đo và tổng thời gian, có thể kèm thống kê phân bố. Đơn vị hiển thị phụ thuộc backend; khi đọc bằng Java, chỉ định `TimeUnit`.
- **Gauge:** giá trị tại thời điểm quan sát, chẳng hạn số message hiện có trong queue.

Một `Timer` đã có count, nên không cần thêm counter chỉ để đếm chính những lần gọi đang được timer đo. Counter nghiệp vụ trong bài có ý nghĩa riêng: phân biệt quyết định chấp nhận đơn với việc framework gửi message. Xem [Micrometer Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html).

### 2.2. Xác định phạm vi trước khi đặt tên

Bài sử dụng hai lớp chỉ số:

| Chỉ số | Phạm vi |
| --- | --- |
| `spring.integration.send` | Hoạt động gửi vào channel hoặc gọi handler, được phân biệt bằng tag |
| `orders.accepted` | Số lần `OrderProcessor.process()` trả về kết quả chấp nhận |
| `orders.failed` | Số lần `OrderProcessor.process()` ném `RuntimeException` |
| `orders.processing` | Thời gian bên trong `OrderProcessor.process()`, tách theo `outcome` |

Nếu transformer lỗi trước khi gọi processor, `orders.failed` không tăng. Nếu processor trả về bình thường nhưng việc chuyển kết quả sang channel kế tiếp lỗi, `orders.accepted` đã tăng. Đây là hệ quả của phạm vi đo đã chọn; counter này không xác nhận commit cơ sở dữ liệu hay giao hàng thành công.

## 3. Luồng cần quan sát

~~~mermaid
flowchart LR
    A["OrdersGateway hoặc MessageChannel.send"]
    B["orders.input / DirectChannel"]
    C["orders.normalize / Transformer"]
    D["orders.normalized / DirectChannel"]
    E["orders.process / Service Activator"]
    F["orders.completed / QueueChannel"]
    G["Consumer đọc kết quả"]

    A --> B --> C --> D --> E --> F --> G
    E -. "SKU = FAIL: ném exception" .-> X["Caller nhận lỗi"]
~~~

Hai `DirectChannel` giúp phần xử lý chạy trên thread của caller. `QueueChannel` ở cuối giữ kết quả cho consumer đọc sau; queue không tự tạo thread xử lý.

Quy ước tên trong bài:

- Gateway: `ordersGateway`.
- Channel: `orders.input`, `orders.normalized`, `orders.completed`.
- Endpoint DSL: `orders.normalize`, `orders.process`.

Đặt tên rõ ràng giúp liên hệ meter, log, history và cấu hình luồng. Endpoint và handler bên trong endpoint là những đối tượng khác nhau; tên handler có thể có hậu tố do DSL tạo ra. Khi viết assertion ổn định, bài ưu tiên tên channel đã khai báo tường minh.

## 4. Chuẩn bị dependency và endpoint metrics

Trong dự án đã dùng parent/BOM Spring Boot 3.5.x, bổ sung các dependency sau vào `pom.xml`. Đây là đoạn dependencies, không phải toàn bộ POM.

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Spring Boot tự cấu hình `MeterRegistry` theo các registry implementation có trên classpath. Với dependency Prometheus, ứng dụng có thể xuất dữ liệu qua endpoint tương ứng; không tạo thêm `SimpleMeterRegistry` trong cấu hình ứng dụng chính. Registry này chỉ được dùng trong kiểm thử độc lập ở phần sau. Xem [Spring Boot Metrics](https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html).

Cấu hình cho lần chạy local trong `application.yml`:

~~~yaml
spring:
  application:
    name: integration-observability-lab

server:
  address: 127.0.0.1
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  metrics:
    tags:
      application: integration-observability-lab
    distribution:
      percentiles-histogram:
        orders.processing: true
~~~

Địa chỉ loopback phù hợp cho bài lab trên máy cá nhân. Nếu chuyển cấu hình sang môi trường triển khai, cấu hình quyền truy cập Actuator theo hạ tầng của môi trường đó.

`/actuator/metrics` phục vụ khám phá meter và tag; `/actuator/prometheus` cung cấp định dạng để Prometheus scrape. Việc registry tồn tại và việc endpoint được expose qua HTTP là hai điều kiện riêng. Xem [Spring Boot Actuator Endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html).

## 5. Cài đặt gateway, flow và metrics nghiệp vụ

Các lớp minh họa dùng package `example.integration.metrics`. Đặt các tệp dưới source root Java tương ứng của dự án thực hành.

### 5.1. Gateway

Tệp `OrdersGateway.java`:

~~~java
package example.integration.metrics;

import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.messaging.Message;

@MessagingGateway(
        name = "ordersGateway",
        defaultRequestChannel = "orders.input")
public interface OrdersGateway {

    void submit(Message<OrdersFlowConfig.OrderRequest> request);
}
~~~

Gateway có kiểu trả về `void`: caller không chờ nhận payload phản hồi từ gateway. Kết quả được flow chuyển tường minh vào `orders.completed`.

**`void` không có nghĩa là bất đồng bộ.** Trong cấu hình này, caller vẫn thực thi transformer và processor qua `DirectChannel`. Đổi kiểu trả về của Java không tạo executor hay poller. Xem [Messaging Gateways](https://docs.spring.io/spring-integration/reference/6.5/gateway.html).

### 5.2. Cấu hình luồng

Tệp `OrdersFlowConfig.java`:

~~~java
package example.integration.metrics;

import java.util.Locale;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.config.EnableIntegrationManagement;
import org.springframework.integration.config.EnableMessageHistory;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration(proxyBeanMethods = false)
@EnableIntegration
@EnableIntegrationManagement
@EnableMessageHistory({"ordersGateway", "orders.*"})
@IntegrationComponentScan(basePackageClasses = OrdersGateway.class)
public class OrdersFlowConfig {

    public record OrderRequest(String orderId, String sku, int quantity) {
    }

    public record OrderResult(
            String orderId, String sku, int quantity, String status) {
    }

    @Bean("orders.input")
    public DirectChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean("orders.normalized")
    public DirectChannel ordersNormalized() {
        return new DirectChannel();
    }

    @Bean("orders.completed")
    public QueueChannel ordersCompleted() {
        return new QueueChannel(100);
    }

    @Bean
    public OrderProcessor orderProcessor(MeterRegistry registry) {
        return new OrderProcessor(registry);
    }

    @Bean
    public IntegrationFlow ordersFlow(OrderProcessor processor) {
        return IntegrationFlow.from("orders.input")
                .transform(OrderRequest.class,
                        request -> new OrderRequest(
                                request.orderId(),
                                request.sku().strip().toUpperCase(Locale.ROOT),
                                request.quantity()),
                        endpoint -> endpoint.id("orders.normalize"))
                .channel("orders.normalized")
                .handle(processor, "process",
                        endpoint -> endpoint.id("orders.process"))
                .channel("orders.completed")
                .get();
    }

    public static class OrderProcessor {

        private final MeterRegistry registry;
        private final Counter accepted;
        private final Counter failed;
        private final Timer successTimer;
        private final Timer failureTimer;

        public OrderProcessor(MeterRegistry registry) {
            this.registry = registry;
            this.accepted = Counter.builder("orders.accepted")
                    .description("Orders accepted by the processor")
                    .register(registry);
            this.failed = Counter.builder("orders.failed")
                    .description("Failed processor invocations")
                    .register(registry);
            this.successTimer = Timer.builder("orders.processing")
                    .tag("outcome", "success")
                    .register(registry);
            this.failureTimer = Timer.builder("orders.processing")
                    .tag("outcome", "failure")
                    .register(registry);
        }

        public OrderResult process(OrderRequest request) {
            Timer.Sample sample = Timer.start(this.registry);
            boolean success = false;

            try {
                if (request.quantity() <= 0) {
                    throw new IllegalArgumentException(
                            "Quantity must be greater than zero");
                }

                if ("FAIL".equals(request.sku())) {
                    throw new IllegalStateException(
                            "Simulated processor failure");
                }

                OrderResult result = new OrderResult(
                        request.orderId(),
                        request.sku(),
                        request.quantity(),
                        "ACCEPTED");

                this.accepted.increment();
                success = true;
                return result;
            }
            catch (RuntimeException ex) {
                this.failed.increment();
                throw ex;
            }
            finally {
                sample.stop(success ? this.successTimer : this.failureTimer);
            }
        }
    }
}
~~~

Những quyết định trong cấu hình:

1. `@EnableIntegration` khai báo hạ tầng tích hợp, giúp cùng cấu hình được dùng cả với Spring Boot và trong test context tối giản.
2. `@EnableIntegrationManagement` bật cấu hình quản lý; bài không truyền `observationPatterns`, nên dùng meter Micrometer trực tiếp cho các component.
3. `@EnableMessageHistory` giới hạn thành phần được theo dõi theo tên. Chỉ khai báo một cấu hình message history cho application context.
4. `@IntegrationComponentScan` phát hiện interface `@MessagingGateway`. Cấu hình tường minh này cũng có hiệu lực trong test context không khởi tạo toàn bộ ứng dụng Boot.
5. Handler trả về payload `OrderResult`. Framework thực hiện việc tạo message phản hồi và truyền các header phù hợp; ví dụ không tự tạo một `GenericMessage` làm mất ngữ cảnh đầu vào.
6. Timer và counter được đăng ký một lần trong constructor, tránh dựng lại builder trong đường xử lý từng message.

Vai trò của `@IntegrationComponentScan` đối với interface gateway được mô tả trong [Annotation Support](https://docs.spring.io/spring-integration/reference/6.5/configuration/annotations.html). Cách khai báo flow theo chuỗi nằm trong [Java DSL Basics](https://docs.spring.io/spring-integration/reference/6.5/dsl/java-basics.html).

`QueueChannel(100)` tạo giới hạn lưu kết quả. Bài demo chỉ đưa vào hai kết quả rồi đọc ra; nếu gửi liên tục mà không có consumer, queue có thể đầy và việc gửi kết quả có thể phải chờ. Giới hạn queue không tự tạo chính sách retry hoặc xử lý quá tải.

## 6. Đọc history và tạo dữ liệu mẫu

### 6.1. Đọc tên component từ header

Tệp `HistorySupport.java`:

~~~java
package example.integration.metrics;

import java.util.ArrayList;
import java.util.List;
import java.util.Properties;

import org.springframework.integration.history.MessageHistory;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;

public final class HistorySupport {

    private HistorySupport() {
    }

    public static List<String> names(Message<?> message) {
        if (message == null) {
            return List.of();
        }

        MessageHistory history = message.getHeaders()
                .get(MessageHistory.HEADER_NAME, MessageHistory.class);

        if (history == null) {
            return List.of();
        }

        List<String> result = new ArrayList<>();
        for (Properties entry : history) {
            result.add(entry.getProperty("name"));
        }
        return List.copyOf(result);
    }

    public static Message<?> failedMessage(Throwable failure) {
        Throwable current = failure;
        while (current != null) {
            if (current instanceof MessagingException messagingException
                    && messagingException.getFailedMessage() != null) {
                return messagingException.getFailedMessage();
            }
            current = current.getCause();
        }
        return null;
    }
}
~~~

Header `history` chứa `MessageHistory`, có các entry `Properties` với thông tin như `name`, `type` và `timestamp`. Hàm trên chỉ sao chép tên thành `List<String>` phục vụ log và assertion; không sửa các entry của history. Cấu hình theo pattern và cách đọc header được trình bày trong [Message History](https://docs.spring.io/spring-integration/reference/6.5/message-history.html).

### 6.2. Chạy demo với hai yêu cầu thành công và một yêu cầu lỗi

Tệp `DemoApplication.java`:

~~~java
package example.integration.metrics;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootApplication
public class DemoApplication {

    private static final Logger log =
            LoggerFactory.getLogger(DemoApplication.class);

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CommandLineRunner exercise(
            OrdersGateway gateway,
            @Qualifier("orders.input") MessageChannel input,
            @Qualifier("orders.completed") QueueChannel completed) {

        return args -> {
            gateway.submit(request("O-101", " book ", 2, "req-101"));
            gateway.submit(request("O-102", " pen ", 3, "req-102"));

            try {
                input.send(request("O-103", " fail ", 1, "req-103"));
            }
            catch (RuntimeException ex) {
                Message<?> failed = HistorySupport.failedMessage(ex);
                log.warn("order_failure requestId={} exception={} path={}",
                        failed == null
                                ? "unknown"
                                : failed.getHeaders().get("requestId"),
                        ex.getClass().getSimpleName(),
                        HistorySupport.names(failed));
            }

            for (int i = 0; i < 2; i++) {
                Message<?> result = completed.receive(1000);
                if (result == null) {
                    throw new IllegalStateException(
                            "Expected a completed order");
                }

                log.info("order_completed requestId={} result={} path={}",
                        result.getHeaders().get("requestId"),
                        result.getPayload(),
                        HistorySupport.names(result));
            }
        };
    }

    private static Message<OrdersFlowConfig.OrderRequest> request(
            String orderId, String sku, int quantity, String requestId) {

        return MessageBuilder.withPayload(
                        new OrdersFlowConfig.OrderRequest(
                                orderId, sku, quantity))
                .setHeader("requestId", requestId)
                .build();
    }
}
~~~

Nhánh lỗi chủ động gọi `MessageChannel.send()` để giữ đường kiểm tra `MessagingException.getFailedMessage()` rõ ràng. Gateway có thể tháo bớt lớp exception khi chuyển lỗi về caller; không giả định mọi exception caller nhận đều còn mang failed message.

Trong luồng đồng bộ, exception từ handler có thể truyền về caller. Việc tồn tại bean `errorChannel` không tự chuyển tất cả lỗi đồng bộ sang đó. Với tác vụ bất đồng bộ hoặc poller, cần xét cơ chế xuất `ErrorMessage` và cấu hình error channel tương ứng. Xem [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

Sau khi demo chạy một lần trong tiến trình mới, các kết quả dự kiến là:

| Quan sát | Giá trị dự kiến |
| --- | --- |
| Kết quả nghiệp vụ | `O-101/BOOK/2/ACCEPTED` và `O-102/PEN/3/ACCEPTED` |
| `orders.accepted` | `2` |
| `orders.failed` | `1` |
| Count của `orders.processing{outcome=success}` | `2` |
| Count của `orders.processing{outcome=failure}` | `1` |
| Số message còn ở `orders.completed` sau vòng đọc | `0` |

Đây là kết quả cần tự tái hiện khi thực hành, không phải số đo benchmark. Việc chạy lại ứng dụng tạo tiến trình và registry mới; kiểm tra counter theo từng lần chạy.

## 7. Khám phá và diễn giải metrics

### 7.1. Kiểm tra đúng tên meter và tag

Sau khi khởi động ứng dụng, chạy từ PowerShell:

~~~powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8080/actuator/metrics'

Invoke-RestMethod -Uri 'http://127.0.0.1:8080/actuator/metrics/orders.accepted'

Invoke-RestMethod -Uri 'http://127.0.0.1:8080/actuator/metrics/orders.processing?tag=outcome:success'

Invoke-RestMethod -Uri 'http://127.0.0.1:8080/actuator/metrics/spring.integration.send?tag=type:channel&tag=name:orders.input&tag=result:success'
~~~

Trong cấu hình Micrometer trực tiếp của bài, `spring.integration.send` dùng `type` để phân biệt channel/handler; `name` xác định component; `result` biểu diễn success/failure và `exception` mô tả loại exception. `QueueChannel` còn có gauge `spring.integration.channel.queue.size` và `spring.integration.channel.queue.remaining.capacity`. Những meter này không phải counter đơn hàng. Xem [Spring Integration Metrics and Management](https://docs.spring.io/spring-integration/reference/6.5/metrics.html).

Thử lọc thất bại tại channel đầu vào:

~~~text
GET /actuator/metrics/spring.integration.send?tag=type:channel&tag=name:orders.input&tag=result:failure
~~~

Với luồng đồng bộ và ba request mẫu, count tại `orders.input` dự kiến là hai lần success và một lần failure. Không thêm điều kiện tên exception ngay từ đầu: framework có thể bọc exception nghiệp vụ thành exception xử lý message. Hãy xem `availableTags` trong response để chọn giá trị thực tế.

Meter có thể chưa xuất hiện trước khi phát sinh hoạt động tương ứng. Khi một truy vấn không có kết quả, kiểm tra danh sách meter và tag trước khi kết luận ứng dụng không được instrument.

### 7.2. Không cộng timer của tất cả component

Với `DirectChannel`, `send()` gọi consumer trong cùng call stack. Do đó thời gian gửi vào `orders.input` có thể bao gồm transformer, processor và việc chuyển kết quả vào queue.

Các timer này có vùng thời gian lồng nhau. Cộng timer channel đầu vào với timer handler sẽ đếm chồng thời gian. Để đánh giá:

- Dùng timer ở cửa vào đồng bộ để quan sát chi phí từ lúc gửi tới lúc toàn bộ phần đồng bộ trả về.
- Dùng `orders.processing` để cô lập thời gian processor.
- Dùng gauge queue để thấy kết quả chưa được tiêu thụ.
- Khi thêm ranh giới bất đồng bộ, thiết kế một phép đo từ lúc tiếp nhận đến lúc hoàn tất nếu cần thời gian đầu cuối.

Đối với queue ở giữa flow, thời gian enqueue không đại diện cho thời gian message nằm chờ. Đồng thời, một lần enqueue thành công chưa xác nhận consumer phía sau xử lý nghiệp vụ thành công.

### 7.3. Đọc dữ liệu Prometheus

~~~powershell
(Invoke-WebRequest -Uri 'http://127.0.0.1:8080/actuator/prometheus').Content
~~~

Micrometer chuyển tên theo quy ước của backend; ví dụ counter và timer có thể xuất hiện dưới các tên `orders_accepted_total`, `orders_failed_total` và `orders_processing_seconds_count`. Luôn xác nhận tên thực tế trong output scrape trước khi viết truy vấn. Quy tắc chuyển tên và tag được mô tả trong [Naming Meters](https://docs.micrometer.io/micrometer/reference/concepts/naming.html).

Ví dụ PromQL cho cấu hình mẫu:

~~~promql
sum(rate(orders_accepted_total{
  application="integration-observability-lab"
}[5m]))
~~~

Tỷ lệ thất bại trong các lần processor được gọi:

~~~promql
sum(rate(orders_failed_total{
  application="integration-observability-lab"
}[5m]))
/
clamp_min(
  sum(rate(orders_failed_total{
    application="integration-observability-lab"
  }[5m]))
  +
  sum(rate(orders_accepted_total{
    application="integration-observability-lab"
  }[5m])),
  1e-9
)
~~~

Độ trễ p95 của các lần processor thành công, khi histogram đã được xuất:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(orders_processing_seconds_bucket{
      application="integration-observability-lab",
      outcome="success"
    }[5m])
  )
)
~~~

Các truy vấn này cần Prometheus đã scrape ứng dụng và có dữ liệu trong khoảng quan sát. Demo gửi ba request ngay khi khởi động chỉ đủ khám phá meter; để quan sát `rate` và percentile có ý nghĩa, hãy tạo tải đều trong nhiều chu kỳ scrape. Không dùng ba request để kết luận hiệu năng hay độ tin cậy của dịch vụ.

## 8. Diễn giải message history

### 8.1. Kiểm tra đường đi, không cố định toàn bộ danh sách

Với một kết quả thành công, history phải có các channel theo thứ tự:

~~~text
orders.input
  -> ...
  -> orders.normalized
  -> ...
  -> orders.completed
~~~

Dấu `...` biểu diễn entry của gateway hoặc handler phù hợp pattern tracking. Tên và số entry phụ thuộc các component thực tế; `HistorySupport.names()` cho biết danh sách ứng dụng của bạn tạo ra.

Với lỗi trong `orders.process`, failed message được kỳ vọng đã qua `orders.input` và `orders.normalized`, chưa qua `orders.completed`. Một entry chỉ chứng minh message đã được ghi nhận ở điểm đó; không đủ để chứng minh bước nghiệp vụ đã commit thành công.

### 8.2. Timestamp trong history không thay thế Timer

Entry history ghi timestamp khi message được theo dõi tại một component. Chênh lệch giữa hai timestamp có thể bao gồm thời gian xử lý, scheduling và chờ queue. Nó không tự cung cấp thời điểm bắt đầu/kết thúc đầy đủ của từng handler.

Sử dụng timestamp để dựng lại diễn biến; sử dụng timer có ranh giới đo rõ ràng để đánh giá độ trễ. Khi so sánh timestamp qua nhiều máy, còn phải xét đồng bộ đồng hồ.

### 8.3. Giữ ngữ cảnh khi biến đổi message

Transformer trả về payload như ví dụ giúp framework quản lý message phản hồi. Nếu cần tự tạo `Message<?>` trong một bước, xem xét việc sao chép header:

~~~java
Message<?> replacement = MessageBuilder
        .withPayload(newPayload)
        .copyHeaders(original.getHeaders())
        .build();
~~~

Đây là đoạn minh họa tại nơi đã có `newPayload` và `original`. Không kỳ vọng `id` hoặc `timestamp` của message mới bằng message cũ. Header `requestId` là khóa tương quan chủ động của bài, độc lập với định danh của mỗi message.

Một `copyHeaders` đơn giản cũng không giải quyết đầy đủ trường hợp tự nhân bản message cho nhiều nhánh chạy song song. Từ Spring Integration 6.3, history được bổ sung theo cơ chế append; framework xử lý sao chép history tại các điểm phân nhánh do nó quản lý. Với việc tự tạo nhiều nhánh ngoài cơ chế đó, xem API `cloneMessageHistoryIfAny()` của builder Spring Integration và tránh chia sẻ history để các nhánh cùng ghi. Chi tiết thay đổi nằm trong [Message History 6.5](https://docs.spring.io/spring-integration/reference/6.5/message-history.html).

### 8.4. Chọn điểm thu thập dữ liệu

Trong bài, consumer đọc history sau khi nhận từ `orders.completed`; khi lỗi, caller đọc từ failed message. Nếu ứng dụng chuyển sang luồng bất đồng bộ, có thể thu thập ngữ cảnh trong error flow.

Khi nhận `ErrorMessage`, payload của nó là lỗi. Để xem đường đi của message nghiệp vụ gây lỗi, tìm `MessagingException.getFailedMessage()` trong chuỗi nguyên nhân hoặc thông tin original message mà error strategy cung cấp. History của chính error message, nếu có, mô tả đường xử lý lỗi và có thể khác history của message nghiệp vụ.

Message history ở trong header không tự tạo kho audit bền vững, không mặc nhiên đi xuyên mọi giao thức và không phải trace phân tán. Nếu gửi qua HTTP, Kafka hoặc hệ thống bên ngoài, cần thiết kế việc ánh xạ header, định dạng dữ liệu và truyền correlation/trace context tại biên đó.

## 9. Kiểm thử khả năng quan sát

Kiểm thử cần đồng thời xác nhận kết quả nghiệp vụ và tín hiệu quan sát. Chỉ kiểm tra ứng dụng khởi động thành công không đủ để chứng minh một message có history hoặc meter đã ghi nhận hoạt động.

Lớp dưới sử dụng JUnit 5, AssertJ và Spring Test từ `spring-boot-starter-test`. Nó tạo context tối giản với registry trong bộ nhớ; không khởi động HTTP server và không chạy `CommandLineRunner` của ứng dụng demo.

Tệp `OrdersFlowTest.java`:

~~~java
package example.integration.metrics;

import java.util.List;

import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.catchThrowable;

@SpringJUnitConfig(classes = {
        OrdersFlowConfig.class,
        OrdersFlowTest.Meters.class
})
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class OrdersFlowTest {

    @Configuration(proxyBeanMethods = false)
    static class Meters {

        @Bean
        SimpleMeterRegistry meterRegistry() {
            return new SimpleMeterRegistry();
        }
    }

    @Autowired
    OrdersGateway gateway;

    @Autowired
    SimpleMeterRegistry registry;

    @Autowired
    @Qualifier("orders.input")
    MessageChannel input;

    @Autowired
    @Qualifier("orders.completed")
    QueueChannel completed;

    @Test
    void recordsSuccessfulOrderAndItsHistory() {
        gateway.submit(request("O-201", " book ", 2, "req-201"));

        Message<?> reply = this.completed.receive(1000);

        assertThat(reply).isNotNull();
        assertThat(reply.getPayload()).isEqualTo(
                new OrdersFlowConfig.OrderResult(
                        "O-201", "BOOK", 2, "ACCEPTED"));
        assertThat(reply.getHeaders().get("requestId"))
                .isEqualTo("req-201");
        assertThat(HistorySupport.names(reply))
                .containsSubsequence(
                        "orders.input",
                        "orders.normalized",
                        "orders.completed");

        assertThat(this.registry.get("orders.accepted")
                .counter().count()).isEqualTo(1.0);
        assertThat(this.registry.get("orders.failed")
                .counter().count()).isZero();
        assertThat(this.registry.get("orders.processing")
                .tag("outcome", "success")
                .timer().count()).isEqualTo(1L);

        Timer sent = this.registry.find("spring.integration.send")
                .tags("type", "channel",
                        "name", "orders.input",
                        "result", "success")
                .timer();

        assertThat(sent).isNotNull();
        assertThat(sent.count()).isEqualTo(1L);
    }

    @Test
    void recordsFailureWithoutProducingACompletedOrder() {
        Throwable failure = catchThrowable(() ->
                this.input.send(
                        request("O-202", " fail ", 1, "req-202")));

        assertThat(failure).isInstanceOf(MessagingException.class);

        Message<?> failed = HistorySupport.failedMessage(failure);
        assertThat(failed).isNotNull();
        assertThat(failed.getHeaders().get("requestId"))
                .isEqualTo("req-202");

        List<String> path = HistorySupport.names(failed);
        assertThat(path)
                .containsSubsequence("orders.input", "orders.normalized")
                .doesNotContain("orders.completed");

        assertThat(this.completed.receive(0)).isNull();
        assertThat(this.registry.get("orders.accepted")
                .counter().count()).isZero();
        assertThat(this.registry.get("orders.failed")
                .counter().count()).isEqualTo(1.0);
        assertThat(this.registry.get("orders.processing")
                .tag("outcome", "failure")
                .timer().count()).isEqualTo(1L);

        Timer sent = this.registry.find("spring.integration.send")
                .tags("type", "channel",
                        "name", "orders.input",
                        "result", "failure")
                .timer();

        assertThat(sent).isNotNull();
        assertThat(sent.count()).isEqualTo(1L);
    }

    private static Message<OrdersFlowConfig.OrderRequest> request(
            String orderId, String sku, int quantity, String requestId) {

        return MessageBuilder.withPayload(
                        new OrdersFlowConfig.OrderRequest(
                                orderId, sku, quantity))
                .setHeader("requestId", requestId)
                .build();
    }
}
~~~

Mỗi test được tạo context mới để counter của test trước không ảnh hưởng test sau. Assertion dùng thứ tự tương đối của các channel tường minh; không ràng buộc toàn bộ history vào tên handler được sinh tự động.

Không dùng `Thread.sleep()` để chờ trong flow đồng bộ này. `receive(1000)` là giới hạn chờ khi kiểm tra đầu ra, không phải phép đo hiệu năng. Nếu đổi flow sang bất đồng bộ, cần điều kiện chờ hữu hạn cho kết quả và meter vì thời điểm hoàn tất không còn trùng với thời điểm caller gửi xong.

## 10. Khi chuyển sang Micrometer Observation

Spring Integration 6.x có hỗ trợ Observation. Có thể thay annotation quản lý trong cấu hình trên bằng:

~~~java
@EnableIntegrationManagement(
        observationPatterns = {"ordersGateway", "orders.*"})
~~~

Đồng thời phải có `ObservationRegistry` và các handler phù hợp. Với metric qua Observation, việc thu thập do `ObservationHandler` thực hiện; chỉ tạo registry không đủ để có tracing hoặc xuất dữ liệu ra backend.

Điểm cần kiểm tra khi chuyển cơ chế là tên meter và tag. Ví dụ meter theo Observation gồm `spring.integration.producer`, `spring.integration.handler` và `spring.integration.gateway`; các tag quy ước có tiền tố `spring.integration.`. Assertion tìm `spring.integration.send` với `type/name/result` trong bài cần được điều chỉnh cho component đã chuyển sang Observation. Xem [Micrometer Observation trong Spring Integration](https://docs.spring.io/spring-integration/reference/6.5/metrics.html#micrometer-observation).

Đối với test context tối giản, một cấu hình bổ sung để kết nối Observation với metrics có thể là:

~~~java
@Bean
ObservationRegistry observationRegistry(MeterRegistry meterRegistry) {
    ObservationRegistry registry = ObservationRegistry.create();
    registry.observationConfig().observationHandler(
            new DefaultMeterObservationHandler(meterRegistry));
    return registry;
}
~~~

Các import cho đoạn bổ sung:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.context.annotation.Bean;
~~~

Đây là phương án khi bạn chủ động dựng context; không thêm một registry nữa vào ứng dụng Boot đã cấu hình Observation mà chưa kiểm tra bean hiện có. Handler trong ví dụ tạo metrics từ Observation; tracing còn cần handler và cầu nối tracing tương ứng.

Sau khi chuyển, thực hành lại với một message thành công và một message lỗi, khám phá `availableTags`, rồi cập nhật assertion và dashboard theo các meter quan sát được. Không cộng dữ liệu của nhiều cơ chế để tính một tổng số yêu cầu nếu chưa xác định chúng đang đo cùng hay khác phạm vi.

## 11. Kiểm soát lượng dữ liệu quan sát

### 11.1. Giữ số lượng giá trị tag có giới hạn

Các tag phù hợp có thể là:

| Tag | Tập giá trị mẫu |
| --- | --- |
| `outcome` | `success`, `failure` |
| `flow` | `orders`, `payments` |
| `route` | `standard`, `priority` |

`orderId`, `requestId`, email, nội dung exception và SKU do người dùng nhập có thể tạo rất nhiều giá trị. Đưa chúng vào ngữ cảnh log hoặc trace khi cần tìm một yêu cầu cụ thể; giữ metric tag ở các nhóm hữu hạn đã thiết kế.

Ví dụ, 8 flow × 12 component × 2 outcome tạo tối đa 192 tổ hợp cho các chiều đó. Thêm một tag chứa 100.000 request ID có thể làm không gian tổ hợp tăng mạnh; histogram còn tạo thêm nhiều series cho từng tổ hợp. Cần xét cả số tag, tập giá trị, bucket và số instance khi ước lượng chi phí.

### 11.2. Theo dõi history ở các điểm hữu ích

Pattern `orders.*` phù hợp bài lab. Với luồng dài hoặc nhiều vòng lặp, chọn các điểm có giá trị chẩn đoán như cửa vào, sau bước chuẩn hóa, trước tích hợp ngoài và đường ra.

Khi log, ưu tiên `requestId`, loại lỗi và danh sách component. Toàn bộ payload/header có thể chứa thông tin không cần cho việc điều tra. Ở đây việc đọc một danh sách tên vừa đủ để xác định message dừng trước hay sau processor.

History của một message có thể tăng khi retry hoặc đi qua vòng lặp. Nếu snapshot để lưu lâu hơn vòng đời xử lý, sao chép các giá trị cần dùng sau khi nhánh đã hoàn tất; không giữ rồi tùy ý sửa header history của message còn đang được xử lý.

## 12. Bài tập mở rộng

### 12.1. Lỗi trước processor

Gửi `OrderRequest` có `sku = null` để transformer thất bại khi gọi `strip()`.

Trước khi chạy, dự đoán:

- Meter tại `orders.input` ghi nhận failure.
- `orders.failed` vẫn bằng 0 nếu context chưa xử lý yêu cầu nào khác.
- Không có kết quả trong `orders.completed`.
- History tại điểm lỗi chưa đến `orders.normalized`.

Bài tập giúp kiểm tra cách hiểu phạm vi counter và xác định component đầu tiên không xuất hiện trong đường đi dự kiến.

### 12.2. Thêm router và filter

Bổ sung một router theo nhóm nghiệp vụ hữu hạn, chẳng hạn `standard` và `priority`, cùng filter có discard channel riêng cho yêu cầu không hợp lệ.

Thiết kế tiêu chí quan sát trước khi viết DSL:

1. Mỗi nhánh có tên channel ổn định để nhận ra trong history.
2. Message bị loại có counter riêng tại discard flow.
3. Ghi rõ việc filter loại message bình thường có phải là lỗi kỹ thuật hay không theo cấu hình.
4. Kiểm thử một message cho mỗi nhánh và một message bị loại.

Không dùng riêng exception count để suy ra tổng số yêu cầu bị từ chối: một filter có thể loại message mà không ném exception.

### 12.3. Chèn QueueChannel trước processor

Thay channel trung gian bằng `QueueChannel` và cấu hình poller cho endpoint tiêu thụ. Sau đó gửi một đợt tải nhỏ, có giới hạn.

Quan sát riêng:

- Tốc độ tiếp nhận vào queue.
- Độ sâu queue và khả năng tiêu thụ.
- Số lần processor hoàn tất.
- Cách lỗi đến error flow sau ranh giới bất đồng bộ.
- Thời gian chờ queue và thời gian processor thực thi.

Đối chiếu lại ý nghĩa timer tại cửa vào: nó không còn bao trùm phần xử lý ở thread consumer như cấu hình `DirectChannel` ban đầu.

### 12.4. Quan sát retry và aggregator

Nếu bổ sung retry, phân biệt số yêu cầu nghiệp vụ với số lần thử. Một request có thể gây nhiều lần gọi processor; đặt tên và assertion để không hiểu attempt count thành số request.

Nếu bổ sung aggregator, theo dõi cả nhóm đang chờ, nhóm hoàn tất và nhóm hết hạn. Message đầu ra được tổng hợp không mặc nhiên chứa toàn bộ lịch sử của mọi message trong nhóm; muốn audit từng phần tử, cần thiết kế cách lưu ngữ cảnh tương ứng.

## 13. Dấu hiệu thường gặp khi điều tra

| Dấu hiệu | Kiểm tra tiếp |
| --- | --- |
| Không có `spring.integration.send` | Đã gửi message chưa; có đúng registry không; component có chuyển sang Observation không; có filter chặn meter không |
| Có meter nhưng endpoint HTTP không truy cập được | Web runtime, địa chỉ/cổng, cấu hình exposure và quyền truy cập |
| Tìm meter được nhưng không tìm thấy tag | Đọc `availableTags` và kiểm tra giá trị tên component thực tế |
| Không có `history` | Annotation history, pattern tên, component được quản lý và bước nào tự tạo message mới |
| Counter accepted tăng nhưng queue không có kết quả | Consumer đã đọc chưa; việc gửi output có lỗi không; phạm vi counter kết thúc ở đâu |
| Counter processor không tăng dù đầu vào có failure | Message có lỗi trước processor hay không |
| Queue tăng đều nhưng send vẫn success | Consumer, poller, executor và tốc độ xử lý phía sau |
| Cộng các timer ra thời gian lớn hơn thực tế | Timer có bao trùm nhau trong cùng call stack không |
| Error flow không nhận lỗi đồng bộ | Caller đang nhận exception trực tiếp hay đã có cấu hình chuyển lỗi rõ ràng |
| Prometheus chưa thấy rate/p95 hữu ích | Số lần scrape, lượng message trong cửa sổ đo và histogram bucket thực tế |

## 14. Tiêu chí hoàn thành bài thực hành

Bài thực hành đạt yêu cầu khi bạn tự tái hiện được các bằng chứng sau:

- Hai message thành công có payload đã chuẩn hóa, giữ `requestId` và history đi qua các channel đầu vào, trung gian, đầu ra theo đúng thứ tự.
- Một lỗi trong processor làm counter failure tăng, không tạo kết quả thành công và có thể truy tìm failed message.
- Có thể chọn đúng meter/tag để xem hoạt động của một channel mà không nhầm với số đơn nghiệp vụ.
- Giải thích được vì sao timer channel đồng bộ có thể bao trùm handler, và vì sao enqueue success chưa chứng minh nghiệp vụ phía sau thành công.
- Các kiểm thử thành công/thất bại chạy độc lập, không phụ thuộc counter tích lũy từ test khác hoặc thời gian sleep tùy ý.
- Nếu bật Observation, nhận diện được các meter/tag mới và cập nhật cách kiểm tra tương ứng.

Khi điều tra một bất thường, bắt đầu bằng metrics để xác định phạm vi và thời điểm, dùng `requestId` để tìm message liên quan, rồi đối chiếu history cùng lỗi tại điểm xử lý. Cách kết hợp này giúp kiểm chứng đường đi và hành vi của flow bằng dữ liệu cụ thể.
