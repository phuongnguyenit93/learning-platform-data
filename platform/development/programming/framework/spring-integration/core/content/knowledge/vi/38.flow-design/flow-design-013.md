# Thiết kế flow có thể quan sát

Trong chương **Thiết kế flow** của module **SPRING_INTEGRATION_CORE**, một flow cần thể hiện được cả đường đi của thông điệp và kết quả của từng lần xử lý. Khi khách hàng hỏi “đơn hàng của tôi đang ở đâu?”, nhóm vận hành phải lần được từ điểm tiếp nhận, qua transformer, filter, router và endpoint, đến kết quả cuối cùng hoặc nơi đang chờ.

Bài học sử dụng Message, MessageChannel và Java DSL làm nền tảng; gateway, aggregator, xử lý lỗi và kiểm thử được đặt trong cùng bài toán quan sát. Mục tiêu là thiết kế thông tin chẩn đoán ngay khi thiết kế flow, để có thể giải thích hành vi của hệ thống khi chạy.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

- Đặt tên channel và endpoint ổn định để liên kết sơ đồ, log, metric và trace.
- Duy trì định danh nghiệp vụ qua biến đổi, phân nhánh và xử lý lại thông điệp.
- Định nghĩa rõ thời điểm tiếp nhận, hoàn tất, từ chối và thất bại.
- Chọn điểm đo phù hợp cho xử lý đồng bộ và bất đồng bộ.
- Thiết kế nhánh quan sát có giới hạn tài nguyên.
- Kiểm tra rằng bật quan sát vẫn giữ đúng kết quả nghiệp vụ.

Xét flow nhận đơn hàng: kiểm tra dữ liệu, chuẩn hóa mã đơn, rồi gọi bước xử lý. Dữ liệu không hợp lệ đi vào nhánh từ chối; lỗi kỹ thuật cần có đường chẩn đoán riêng. Nếu chỉ có một dòng “đã nhận đơn”, bạn chưa biết đơn đã hoàn tất, bị loại hay còn nằm trong hàng đợi.

## 2. Bắt đầu từ những điều cần giải thích

Trước khi thêm công cụ, hãy xác định các câu hỏi vận hành.

| Câu hỏi | Bằng chứng cần thu thập |
| --- | --- |
| Hệ thống nhận bao nhiêu yêu cầu? | Số lần tiếp nhận tại một ranh giới xác định |
| Bao nhiêu yêu cầu đạt kết quả cuối? | Kết quả nghiệp vụ tại endpoint kết thúc |
| Đơn cụ thể đang ở đâu? | Khóa nghiệp vụ, correlation ID và các mốc xử lý |
| Flow chậm ở đâu? | Thời gian chờ, thời gian xử lý và thời gian toàn luồng |
| Yêu cầu bị mất dấu ở nhánh nào? | Dấu vết quyết định route, reject, timeout hoặc recovery |
| Nhánh quan sát có đang quá tải? | Dung lượng đệm, số sự kiện bị bỏ và lỗi xuất telemetry |

Bốn loại thông tin bổ sung cho nhau:

| Loại thông tin | Công dụng trong flow đơn hàng | Giới hạn cần hiểu |
| --- | --- | --- |
| Log | Mô tả một sự kiện với khóa tra cứu cụ thể | Khó tổng hợp khi chỉ ghi văn bản tự do |
| Metric | Phát hiện thay đổi về lưu lượng, lỗi, độ trễ, tồn đọng | Không thích hợp để lưu riêng từng mã đơn |
| Trace | Liên kết các bước của một lần thực thi qua nhiều ranh giới | Phụ thuộc truyền context và chính sách lấy mẫu |
| Topology | Cho biết các thành phần và mối nối đang tồn tại | Không chứng minh một đơn cụ thể đã đi qua mọi mối nối |

Một dashboard báo lỗi tăng giúp phát hiện sự cố. Một trace hoặc correlation ID giúp khoanh vùng lần xử lý. Log tại endpoint liên quan giúp giải thích quyết định nghiệp vụ. Thiết kế tốt cho phép đi qua ba mức này mà không phải dò toàn bộ log.

## 3. Vẽ cả đường thành công, đường từ chối và đường lỗi

~~~mermaid
flowchart LR
    A["Caller hoặc gateway"] --> B["ordersInput"]
    B --> C["ordersValidate: filter"]
    C -->|hợp lệ| D["ordersNormalize: transformer"]
    C -->|không hợp lệ| R["ordersRejected"]
    R --> S["ordersRecordRejected"]
    D --> E["ordersNormalized"]
    E --> F["ordersProcess"]
    F --> G["processed"]
    F -. "exception đồng bộ" .-> A
    E -. "tap tùy chọn" .-> T["ordersTelemetry: queue có giới hạn"]
    T --> U["telemetry consumer"]
~~~

Sơ đồ này dành cho ví dụ đồng bộ ở phần 6. Khi đổi đầu vào sang hàng đợi và dùng poller, lỗi phát sinh trong tác vụ xử lý cần được quan sát qua cơ chế lỗi của tác vụ đó.

### 3.1. Đặt tên theo ý nghĩa

Dùng tên channel thể hiện trạng thái dữ liệu: `ordersInput`, `ordersNormalized`, `ordersRejected`. Dùng ID endpoint thể hiện trách nhiệm: `ordersValidate`, `ordersNormalize`, `ordersProcess`.

Trong Java DSL, đặt ID qua endpoint configurer:

~~~java
.filter(Order.class, ObservableOrderFlowApplication::valid,
        endpoint -> endpoint
                .id("ordersValidate")
                .discardChannel("ordersRejected"))
~~~

Tên bean channel và ID endpoint là hai định danh khác nhau. Một số thành phần phụ trợ hoặc handler do DSL tạo có tên dẫn xuất; khi xây dashboard, hãy kiểm tra tên thực tế được registry và graph công bố.

Tên dùng cho dashboard cần ổn định qua các lần triển khai. Đổi một tên endpoint có thể làm chuỗi số liệu cũ và mới bị tách rời, dù nghiệp vụ vẫn giống nhau.

### 3.2. Ghi ranh giới thực thi lên sơ đồ

Với `DirectChannel`, handler được gọi trên luồng gửi. Với `QueueChannel`, thao tác gửi có thể hoàn tất sau khi đặt thông điệp vào hàng đợi; consumer còn phải lấy thông điệp ra để xử lý. Hàng đợi trong bộ nhớ cũng không tự cung cấp độ bền khi tiến trình dừng. Các đặc điểm này được mô tả trong [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

Khi review sơ đồ, đánh dấu những nơi đổi thread, ghi vào kho bền vững, gọi dịch vụ ngoài hoặc tạo thêm thông điệp. Những điểm đó quyết định cách hiểu kết quả đo và cách lần theo yêu cầu.

## 4. Phân biệt các loại định danh

| Định danh | Ý nghĩa | Cách dùng |
| --- | --- | --- |
| `MessageHeaders.ID` | Định danh kỹ thuật của một Message | Đối chiếu một thông điệp cụ thể |
| `businessCorrelationId` | Header do ứng dụng quy ước cho một yêu cầu nghiệp vụ | Nối các mốc xử lý qua nhiều bước |
| `orderId` | Khóa của đơn hàng trong miền nghiệp vụ | Tra cứu trạng thái đơn |
| `correlationId` của mẫu tích hợp | Có thể phục vụ ghép nhóm, ví dụ splitter/aggregator | Giữ đúng ngữ nghĩa của mẫu đang dùng |
| Trace ID, span ID | Định danh thực thi do hạ tầng tracing quản lý | Điều hướng giữa các span và log liên quan |
| `attempt` nếu ứng dụng định nghĩa | Lần thử xử lý của cùng một yêu cầu | Phân biệt retry với yêu cầu mới |

Không dùng ID của Message làm khóa duy nhất cho toàn bộ vòng đời đơn hàng. Một bước tạo Message mới có thể tạo ID mới; retry hoặc gửi lại từ hệ thống ngoài cũng có thể tạo Message khác cho cùng một nghiệp vụ.

Trong bài này, `businessCorrelationId` là tên header tùy chỉnh. Nó không phải header tự động của Spring Integration và không tự trở thành trace context. Chọn tên riêng còn giúp tránh vô tình ghi đè header `correlationId` mà splitter hoặc aggregator đang sử dụng.

Tại biên tiếp nhận:

1. Kiểm tra correlation ID từ bên ngoài theo quy ước độ dài và ký tự.
2. Tạo giá trị mới nếu bên ngoài không cung cấp.
3. Gắn giá trị vào Message và giữ nó qua các bước nội bộ cần liên kết.
4. Khi đi qua adapter hoặc broker, xác định rõ header mapping.
5. Với yêu cầu retry, giữ khóa nghiệp vụ và ghi rõ lần thử theo hợp đồng retry.

Ví dụ tạo Message trong Java, giả sử `ordersInput` là channel đã inject:

~~~java
var message = org.springframework.messaging.support.MessageBuilder
        .withPayload(new ObservableOrderFlowApplication.Order(
                "ord-101", "APAC", 2))
        .setHeader("businessCorrelationId", "checkout-101")
        .build();

ordersInput.send(message);
~~~

Một header chỉ có mặt trong bộ nhớ hiện tại chưa bảo đảm nó được truyền qua HTTP, Kafka hay JMS. Cần kiểm tra header mapper, định dạng truyền và quy ước tin cậy tại từng biên.

## 5. Định nghĩa hợp đồng sự kiện và nhãn metric

### 5.1. Mỗi sự kiện phải có nghĩa rõ

Đề xuất hợp đồng cho flow đơn hàng:

| Sự kiện | Khi nào phát sinh? | Kết luận được phép rút ra |
| --- | --- | --- |
| `received` | Thông điệp đi vào điểm quan sát đầu vào | Đã đến ranh giới đó |
| `normalized` | Đã qua bước chuẩn hóa | Dữ liệu chuẩn hóa sẵn sàng cho bước sau |
| `processed` | Bước xử lý minh họa hoàn tất | Hoàn tất phạm vi được ví dụ định nghĩa |
| `rejected` | Filter loại theo quy tắc dữ liệu | Đã từ chối có chủ đích |
| `failed` | Bước xử lý gặp lỗi kỹ thuật | Lần xử lý này thất bại |
| `retry_scheduled` | Recovery thực sự lên lịch thử lại | Sẽ có lần thử tiếp theo theo chính sách |
| `expired` | Hết thời hạn chờ đã quy định | Không còn tiếp tục chờ theo hợp đồng đó |

Không phát `processed` ngay sau khi enqueue nếu nghiệp vụ vẫn còn chạy phía sau. Với ghi cơ sở dữ liệu, cần quyết định sự kiện thành công có nghĩa là “handler trả về” hay “transaction đã commit”. Với gọi dịch vụ ngoài, cần phân biệt “đã gửi yêu cầu” và “đã nhận xác nhận”.

Log ví dụ theo dạng trường:

~~~text
event=processed flow=orders endpoint=ordersProcess
orderId=ORD-101 correlationId=checkout-101
~~~

Trong ứng dụng thực tế, có thể dùng encoder JSON để lưu từng trường riêng. Ví dụ trên chỉ biểu diễn nội dung cần có, không giả định bộ thu log nào.

### 5.2. Giữ số lượng giá trị nhãn trong giới hạn

Một metric có các nhãn `flow`, `outcome` và `region` với lần lượt 4, 3 và 5 giá trị có thể tạo đến `4 × 3 × 5 = 60` tổ hợp, trước khi tính instance và các chuỗi phụ của backend.

Nếu thêm `orderId` với một triệu giá trị, số chuỗi có thể tăng theo từng đơn. Hãy dùng mã đơn trong log hoặc thuộc tính trace đã kiểm soát, còn metric dùng tập giá trị hữu hạn.

| Trường | Log/trace | Metric tag |
| --- | --- | --- |
| Flow, endpoint cố định | Phù hợp | Phù hợp |
| Outcome trong tập quy định | Phù hợp | Phù hợp |
| Region trong danh mục hữu hạn | Phù hợp | Phù hợp khi cần phân tích |
| Mã đơn, correlation ID | Dùng khi được phép | Tránh |
| Nội dung exception từ đối tác | Cần lọc và giới hạn | Tránh |
| `errorCategory` như `timeout`, `validation` | Phù hợp | Phù hợp nếu danh mục hữu hạn |

Không tạo tag từ `exception.getMessage()`, toàn bộ URL hay payload. Với lỗi, nên ánh xạ sang nhóm được quản lý: `dependency_timeout`, `dependency_unavailable`, `unexpected`.

## 6. Ví dụ Java DSL: quan sát luồng đồng bộ

Ví dụ dùng Java 17 trở lên, Spring Integration 6.x trở lên và Spring Boot quản lý dependency tương thích. Các dependency cần có:

- `spring-boot-starter-integration` cho Spring Integration và Java DSL.
- `spring-boot-starter-actuator` để có hạ tầng metric do Boot cấu hình.
- `spring-boot-starter-web` nếu muốn truy cập Actuator qua HTTP.

Đặt các dependency trong dự án Boot có parent hoặc BOM tương thích; không trộn phiên bản thủ công. Đây là ứng dụng nhận thông điệp qua channel, chưa có REST controller. Phần xử lý được mô phỏng trong bộ nhớ để làm rõ tín hiệu quan sát.

~~~java
package example.integration;

import java.util.Locale;
import java.util.Set;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.handler.LoggingHandler;
import org.springframework.messaging.Message;

@SpringBootApplication
@EnableIntegration
public class ObservableOrderFlowApplication {

    private static final Logger LOG =
            LoggerFactory.getLogger("orders.flow");

    public static void main(String[] args) {
        SpringApplication.run(ObservableOrderFlowApplication.class, args);
    }

    public record Order(String orderId, String region, int quantity) {
    }

    @Bean
    DirectChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean
    DirectChannel ordersNormalized() {
        return new DirectChannel();
    }

    @Bean
    DirectChannel ordersRejected() {
        return new DirectChannel();
    }

    @Bean
    OrderTelemetry orderTelemetry(MeterRegistry registry) {
        return new OrderTelemetry(registry);
    }

    @Bean
    IntegrationFlow ordersFlow(OrderTelemetry telemetry) {
        return IntegrationFlow.from("ordersInput")
                .log(LoggingHandler.Level.INFO, "orders.flow",
                        message -> summary("received", message))
                .filter(Order.class, ObservableOrderFlowApplication::valid,
                        endpoint -> endpoint
                                .id("ordersValidate")
                                .discardChannel("ordersRejected"))
                .transform(Order.class,
                        order -> new Order(
                                order.orderId().toUpperCase(Locale.ROOT),
                                order.region(),
                                order.quantity()),
                        endpoint -> endpoint.id("ordersNormalize"))
                .channel("ordersNormalized")
                .log(LoggingHandler.Level.INFO, "orders.flow",
                        message -> summary("normalized", message))
                .handle(Order.class, (order, headers) -> {
                    try {
                        telemetry.processing.record(() -> {
                            // Mô phỏng lỗi để thực hành quan sát.
                            if (order.orderId().startsWith("FAIL-")) {
                                throw new IllegalStateException(
                                        "Simulated processing failure");
                            }
                            // Thay bằng bước xử lý thực tế trong ứng dụng.
                        });
                    }
                    catch (RuntimeException failure) {
                        telemetry.failed.increment();
                        LOG.error(
                                "event=failed flow=orders endpoint=ordersProcess "
                                        + "orderId={} correlationId={} errorType={}",
                                safe(order.orderId()),
                                safe(headers.get("businessCorrelationId")),
                                failure.getClass().getSimpleName());
                        throw failure;
                    }

                    telemetry.processed.increment();
                    LOG.info(
                            "event=processed flow=orders endpoint=ordersProcess "
                                    + "orderId={} correlationId={}",
                            safe(order.orderId()),
                            safe(headers.get("businessCorrelationId")));
                    return null;
                }, endpoint -> endpoint.id("ordersProcess"))
                .get();
    }

    @Bean
    IntegrationFlow ordersRejectedFlow(OrderTelemetry telemetry) {
        return IntegrationFlow.from("ordersRejected")
                .handle(Order.class, (order, headers) -> {
                    telemetry.rejected.increment();
                    LOG.info(
                            "event=rejected flow=orders "
                                    + "endpoint=ordersRecordRejected "
                                    + "reason=invalid_order "
                                    + "orderId={} correlationId={}",
                            safe(order.orderId()),
                            safe(headers.get("businessCorrelationId")));
                    return null;
                }, endpoint -> endpoint.id("ordersRecordRejected"))
                .get();
    }

    static boolean valid(Order order) {
        return order.orderId() != null
                && order.orderId().matches("[A-Za-z0-9-]{1,40}")
                && order.region() != null
                && Set.of("APAC", "EU", "US").contains(order.region())
                && order.quantity() > 0;
    }

    static String summary(String event, Message<?> message) {
        Object orderId = message.getPayload() instanceof Order order
                ? order.orderId() : null;
        return "event=" + event
                + " flow=orders"
                + " messageId=" + message.getHeaders().getId()
                + " orderId=" + safe(orderId)
                + " correlationId="
                + safe(message.getHeaders().get("businessCorrelationId"));
    }

    static String safe(Object value) {
        if (value == null) {
            return "-";
        }
        String text = value.toString();
        return text.matches("[A-Za-z0-9._:-]{1,80}")
                ? text : "[redacted]";
    }

    static final class OrderTelemetry {
        final Counter processed;
        final Counter rejected;
        final Counter failed;
        final Timer processing;

        OrderTelemetry(MeterRegistry registry) {
            processed = registry.counter(
                    "orders.flow.outcomes",
                    "flow", "orders", "outcome", "processed");
            rejected = registry.counter(
                    "orders.flow.outcomes",
                    "flow", "orders", "outcome", "rejected");
            failed = registry.counter(
                    "orders.flow.outcomes",
                    "flow", "orders", "outcome", "failed");
            processing = Timer.builder("orders.flow.processing")
                    .tag("flow", "orders")
                    .description("Duration of the simulated processing step")
                    .register(registry);
        }
    }
}
~~~

Các điểm cần nhận ra:

- `ordersValidate` có discard channel, nên yêu cầu bị loại vẫn có endpoint ghi nhận kết quả.
- Transformer trả về một `Order` mới. Không sửa payload tại chỗ.
- `ordersProcess` kết thúc bằng `return null` vì ví dụ có hợp đồng một chiều.
- Timer chỉ bao quanh khối xử lý mô phỏng. Thời gian filter, transform, log và chờ hàng đợi nằm ngoài phạm vi timer đó.
- Counter `failed` chỉ đếm lỗi trong khối xử lý được bao quanh. Lỗi chuyển đổi kiểu hoặc lỗi ở endpoint khác cần điểm quan sát riêng.
- `safe` giới hạn trường được ghi; đây là quy tắc minh họa cho các ID, không thay thế chính sách dữ liệu của toàn ứng dụng.

Counter kết quả diễn đạt kết thúc nghiệp vụ trong ví dụ. Timer có sẵn count cho số lần chạy bước xử lý; count đó bao gồm cả lần ném exception, còn yêu cầu bị filter loại không đến bước này. Micrometer trình bày count và các phép đo thời gian trong [Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html).

`processed` ở đây có nghĩa “khối xử lý mô phỏng đã hoàn tất”. Khi thay bằng lưu đơn thật, hãy chuyển điểm ghi nhận sang ranh giới xác nhận phù hợp, kể cả yêu cầu commit hoặc xác nhận từ hệ thống đích.

### 6.1. Dữ liệu thực hành và kết quả mong đợi

Gửi ba Message có correlation ID khác nhau:

| Payload | Đường đi mong đợi | Kết quả |
| --- | --- | --- |
| `Order("ord-101", "APAC", 2)` | Validate → normalize → process | Mã đơn thành `ORD-101`, tăng `processed` |
| `Order("ord-102", "APAC", 0)` | Validate → rejected | Tăng `rejected`, không chạy process |
| `Order("fail-103", "EU", 1)` | Validate → normalize → process | Tăng `failed`, exception truyền về caller |

Các counter tăng theo **lần thực thi**, chưa có bảo đảm đếm duy nhất theo mã đơn. Gửi lại một đơn hai lần sẽ tạo hai lần ghi nhận nếu không có cơ chế idempotency.

### 6.2. Khi đưa gateway vào đầu flow

Gateway có thể che API messaging sau một interface. Chọn hợp đồng một chiều hoặc request-reply trước khi đo thời gian tại gateway; tham khảo [Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html).

Với flow trên, có thể định nghĩa interface một chiều trong package được integration component scan:

~~~java
@org.springframework.integration.annotation.MessagingGateway(
        defaultRequestChannel = "ordersInput")
public interface OrderGateway {
    void submit(
            ObservableOrderFlowApplication.Order order,
            @org.springframework.messaging.handler.annotation.Header(
                    "businessCorrelationId") String correlationId);
}
~~~

Khi thêm interface này, bật `@IntegrationComponentScan` trên cấu hình thích hợp để đăng ký gateway. Với flow đồng bộ, thời gian gọi `submit` bao phủ công việc thực hiện trên call stack. Nếu chuyển sang enqueue, thời gian gọi có thể chỉ phản ánh việc giao thông điệp.

Nếu cần trả `OrderResult`, phải thiết kế nhánh thành công và từ chối đều tạo phản hồi tương ứng. Một filter kết thúc im lặng có thể khiến phía request-reply chờ hết timeout.

## 7. Đọc metric đúng ranh giới

### 7.1. Metric kỹ thuật có sẵn

Khi có `MeterRegistry`, Spring Integration hỗ trợ các meter cho thành phần được quản lý. Những tên hữu ích gồm:

| Meter | Ý nghĩa |
| --- | --- |
| `spring.integration.send` | Timer của channel hoặc handler |
| `spring.integration.receive` | Counter của thao tác nhận |
| `spring.integration.channel.queue.size` | Số phần tử trong QueueChannel |
| `spring.integration.channel.queue.remaining.capacity` | Dung lượng còn lại |

Với `spring.integration.send`, các tag như `type`, `name`, `result`, `exception` giúp chọn thành phần và kết quả kỹ thuật. Hãy kiểm tra meter thực tế trước khi viết truy vấn. Chi tiết tại [Metrics and Management](https://docs.spring.io/spring-integration/reference/metrics.html).

### 7.2. Kết quả kỹ thuật và kết quả nghiệp vụ

Một handler nhận được thông điệp rồi loại theo quy tắc filter có thể hoàn thành thao tác của nó bình thường. Vì vậy, “không ném exception” chưa đủ để suy ra “đơn được chấp nhận”.

Tương tự, gửi vào queue thành công chỉ chứng minh bước giao vào queue đã thành công theo cấu hình hiện tại. Muốn biết đơn hoàn tất phải quan sát endpoint kết thúc hoặc trạng thái nghiệp vụ bền vững.

Nên giữ hai góc nhìn:

- Metric kỹ thuật để phát hiện endpoint lỗi, channel nghẽn hoặc dependency chậm.
- Metric nghiệp vụ để biết số kết quả xử lý, từ chối, hết hạn và cần can thiệp.

### 7.3. Không cộng thời gian các bước một cách máy móc

Trong chuỗi đồng bộ, một endpoint có thể tiếp tục gửi kết quả xuống các endpoint sau trước khi trả về. Các khoảng đo có thể lồng nhau.

Ví dụ thời gian quan sát tại đầu flow là 120 ms, trong đó xử lý cuối mất 90 ms. Nếu một timer trung gian cũng bao gồm 90 ms đó, cộng chúng sẽ đếm trùng.

Với flow bất đồng bộ, phân rã mục tiêu:

~~~text
Thời gian toàn luồng
  = thời gian tiếp nhận
  + tổng thời gian chờ
  + thời gian trên đường xử lý quyết định kết quả
  + thời gian chờ retry hoặc dependency
~~~

Với các nhánh song song, thời gian quyết định kết quả phụ thuộc nhánh cần chờ cuối cùng và điều kiện ghép nhóm. Tổng CPU của tất cả nhánh không bằng độ trễ mà người dùng trải nghiệm.

Dùng đồng hồ đơn điệu để đo thời lượng trong cùng tiến trình. Đối với tuổi thông điệp qua nhiều máy, định nghĩa mốc thời gian truyền được, yêu cầu đồng bộ đồng hồ và mức sai lệch chấp nhận được.

## 8. Observation và tracing

Micrometer Observation mô hình hóa vòng đời quan sát. Các handler đăng ký với `ObservationRegistry` có thể tạo metric hoặc span theo cấu hình. Một registry đứng riêng chưa tự cung cấp đầy đủ pipeline xuất trace; xem [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html).

Với Spring Integration từ 6.0, có thể chọn thành phần được instrument bằng annotation:

~~~java
@org.springframework.integration.config.EnableIntegrationManagement(
        observationPatterns = "orders*")
~~~

Thêm annotation này vào lớp cấu hình phù hợp và cung cấp `ObservationRegistry` cùng các handler cần thiết. Pattern chọn tên component, nên cần đối chiếu cả tên handler do DSL sinh. Chi tiết thuộc tính nằm trong [EnableIntegrationManagement](https://docs.spring.io/spring-integration/api/org/springframework/integration/config/EnableIntegrationManagement.html).

Không giả định dashboard cho cơ chế meter trực tiếp vẫn dùng nguyên tên và tag khi chuyển sang Observation. Đối chiếu registry của ứng dụng sau thay đổi.

Để trace có ích qua một flow:

1. Xác nhận có tracing bridge và exporter thích hợp trong stack đang dùng.
2. Kiểm tra context có đi qua executor, poller và adapter thực tế.
3. Giữ business correlation ID để còn tra cứu khi trace bị lấy mẫu.
4. Giới hạn dữ liệu đưa vào span theo chính sách của hệ thống.
5. Kiểm tra parent-child hoặc liên kết giữa các lần retry theo semantics của thư viện.

MDC thường gắn với thread. Đặt một giá trị trong thread tiếp nhận không bảo đảm thread xử lý sau đó nhìn thấy giá trị ấy. Nếu bổ sung MDC thủ công, phải quản lý vòng đời và dọn context sau xử lý để tránh gán nhầm ID cho yêu cầu kế tiếp.

Không tự tạo `traceId` bằng cách đổi tên business correlation ID. Hai loại định danh có vòng đời và vai trò khác nhau.

## 9. Wire tap và chi phí của nhánh quan sát

`wireTap` cho phép đưa thông điệp tới nhánh phụ. Tính đồng bộ phụ thuộc channel đích; một tap tới `DirectChannel` vẫn có thể làm caller chờ xử lý nhánh phụ. Tham khảo phần [Wire Tap](https://docs.spring.io/spring-integration/reference/channel/configuration.html#channel-wiretap).

Trong Java DSL, `log()` dùng cơ chế wire tap với logging handler. Điểm đặt log quyết định mốc được ghi; log sau filter chỉ nhìn thấy thông điệp vượt qua filter. Xem [Operator log()](https://docs.spring.io/spring-integration/reference/dsl/java-log.html).

### 9.1. Thêm một tap có bộ đệm hữu hạn

Trong lớp ứng dụng ở phần 6, thêm hai bean dưới đây. Cần import `QueueChannel` và `Pollers` từ Spring Integration.

~~~java
@Bean
org.springframework.integration.channel.QueueChannel ordersTelemetry() {
    return new org.springframework.integration.channel.QueueChannel(1000);
}

@Bean
IntegrationFlow ordersTelemetryFlow() {
    return IntegrationFlow.from("ordersTelemetry")
            .handle(Order.class, (order, headers) -> {
                LOG.info(
                        "event=observed flow=orders "
                                + "orderId={} correlationId={}",
                        safe(order.orderId()),
                        safe(headers.get("businessCorrelationId")));
                return null;
            }, endpoint -> endpoint
                    .id("ordersTelemetryLog")
                    .poller(org.springframework.integration.dsl.Pollers
                            .fixedDelay(100)
                            .maxMessagesPerPoll(100)))
            .get();
}
~~~

Sau `.channel("ordersNormalized")` trong flow chính, thêm:

~~~java
.wireTap("ordersTelemetry", tap -> tap.timeout(0))
~~~

Cấu hình `timeout(0)` yêu cầu gửi vào channel đích mà không chờ chỗ trống. API được mô tả tại [WireTapSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/WireTapSpec.html) và [WireTap.setTimeout](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/interceptor/WireTap.html#setTimeout(long)).

Tap ở vị trí này ghi nhận thông điệp tại channel chuẩn hóa, trước khi biết kết quả `ordersProcess`. Vì thế sự kiện `observed` không đồng nghĩa `processed`. Sau ranh giới queue, thứ tự dòng log giữa hai thread cũng có thể khác thứ tự bạn nhìn trên sơ đồ.

### 9.2. Quyết định rõ chính sách quá tải

Với nhánh chẩn đoán, có thể chấp nhận bỏ sự kiện khi bộ đệm đầy. Với bằng chứng nghiệp vụ bắt buộc lưu, cần thiết kế cơ chế lưu và xác nhận phù hợp với yêu cầu độ bền.

Ví dụ tap trên không tự định nghĩa một custom counter đếm sự kiện bị bỏ. Nếu cần số liệu chính xác về overflow, phải instrument điểm giao vào bộ đệm, kiểm tra kết quả `send` hoặc lỗi giao nhận và thử nghiệm hành vi đó với phiên bản đang dùng. Không suy số sự kiện bị bỏ chỉ từ counter ở consumer.

Cần quyết định trước:

| Tình huống | Quyết định thiết kế |
| --- | --- |
| Queue telemetry đầy | Chờ tối đa bao lâu, bỏ sự kiện hay làm thất bại giao nhận? |
| Log backend chậm | Bounded buffer, giới hạn tài nguyên và tín hiệu quá tải |
| Exporter lỗi kéo dài | Giữ bao nhiêu dữ liệu, retry bao lâu, theo dõi lỗi ở đâu? |
| Ứng dụng dừng | Đợi flush bao lâu và chấp nhận mất phần nào? |
| Nhánh quan sát gặp lỗi | Nơi nhận lỗi và cơ chế tránh tạo vòng lặp lỗi |

Không coi wire tap là cơ chế sao chép sâu payload. Nếu payload chứa đối tượng mutable, nhánh phụ phải tránh thay đổi đối tượng dùng chung. Với dữ liệu lớn hoặc nhạy cảm, nên tạo một sự kiện telemetry gọn gồm các trường được cho phép trước khi lưu hay gửi ra ngoài.

Nếu dùng interceptor hoặc tap toàn cục, loại nhánh telemetry và nhánh xử lý lỗi telemetry khỏi phạm vi áp dụng. Việc ghi nhận chính hoạt động ghi nhận có thể tạo vòng lặp và làm tăng tải rất nhanh.

## 10. Quan sát lỗi theo đúng mô hình thực thi

### 10.1. Flow đồng bộ

Trong ví dụ phần 6, lỗi ở `ordersProcess` truyền về phía gửi vì chuỗi chạy qua `DirectChannel`. Framework có thể bọc lỗi trong một `MessagingException`; hãy kiểm tra chuỗi nguyên nhân khi chẩn đoán.

Chỉ đặt header `errorChannel` trên Message rồi gọi `DirectChannel.send` không tự biến mọi exception thành thông điệp lỗi. Nếu cần gateway chuyển lỗi, phải cấu hình hợp đồng lỗi của gateway tương ứng. Quy tắc nền tảng được mô tả trong [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

Đối với caller, cần phân biệt lỗi giao vào flow, lỗi thực thi và timeout chờ phản hồi. Một timeout không chứng minh side effect chưa xảy ra; khi gửi lại cần dựa trên hợp đồng idempotency.

### 10.2. Flow bất đồng bộ

Khi công việc chạy trong poller hoặc tác vụ do framework quản lý, cần thiết kế nơi nhận `ErrorMessage`. Ví dụ nếu đổi `ordersInput` thành `QueueChannel`, consumer đầu tiên phải có poller và có thể cấu hình:

~~~java
endpoint -> endpoint
        .id("ordersValidate")
        .discardChannel("ordersRejected")
        .poller(org.springframework.integration.dsl.Pollers
                .fixedDelay(100)
                .maxMessagesPerPoll(20)
                .errorChannel("ordersErrors"))
~~~

Đây là phần thay thế endpoint configurer của filter trong flow chính, chỉ áp dụng khi đầu vào đã đổi sang pollable channel. Đồng thời khai báo channel `ordersErrors` và consumer cho channel đó. Nếu header lỗi hoặc adapter có quy tắc riêng, cần kiểm tra đường phân giải của cấu hình thực tế.

Đoạn dưới có thể thêm vào lớp ví dụ để đọc thông điệp lỗi. Nó ghi nhận lỗi được chuyển đến channel, chưa thực hiện retry hay recovery:

~~~java
@Bean
DirectChannel ordersErrors() {
    return new DirectChannel();
}

@Bean
IntegrationFlow ordersErrorFlow() {
    return IntegrationFlow.from("ordersErrors")
            .handle((org.springframework.messaging.MessageHandler) message -> {
                Throwable failure = (Throwable) message.getPayload();

                Message<?> failedMessage =
                        failure instanceof
                                org.springframework.messaging.MessagingException ex
                                ? ex.getFailedMessage() : null;

                Object correlationId = failedMessage == null
                        ? null
                        : failedMessage.getHeaders()
                                .get("businessCorrelationId");

                LOG.error(
                        "event=error_observed flow=orders "
                                + "correlationId={} errorType={}",
                        safe(correlationId),
                        failure.getClass().getSimpleName());
            }, endpoint -> endpoint.id("ordersErrorLog"))
            .get();
}
~~~

Thông tin nghiệp vụ thường cần lấy từ Message thất bại nếu exception cung cấp nó. Header của `ErrorMessage` không phải lúc nào cũng giống header của Message gốc. Cần chấp nhận trường hợp không có failed message và cung cấp thông tin khác từ adapter hoặc error strategy khi cần.

Trong ví dụ chuyển sang poller, `failed` ở handler và `error_observed` ở nhánh lỗi có thể cùng nói về một lần thất bại. Chỉ endpoint sở hữu kết quả mới tăng counter kết quả; nhánh ghi nhận lỗi không tăng thêm cùng counter.

Phân biệt ba mốc:

- **Lỗi một lần thử:** lần thực thi hiện tại không thành công.
- **Đã recovery:** đã chuyển sang phương án phục hồi được chấp nhận.
- **Thất bại cuối:** không còn tiếp tục xử lý theo chính sách.

Một dòng log lỗi không tự xác nhận đã rollback, đã vào dead-letter queue hay đã lên lịch retry.

## 11. Message history và runtime graph

### 11.1. Message history để kiểm tra đường đi nội bộ

Có thể bật theo tên component:

~~~java
@org.springframework.integration.annotation.EnableMessageHistory("orders*")
~~~

Message history ghi dấu các thành phần được theo dõi vào header `history`. Nó giúp xem đường đi trong phạm vi instrumentation đã bật; cấu hình được trình bày trong [Message History](https://docs.spring.io/spring-integration/reference/message-history.html).

Sử dụng có mục đích: header có thể lớn hơn khi qua nhiều bước, có thể không được truyền qua adapter và không thay thế kho trace hoặc nhật ký bền vững. Không tính service time chỉ bằng cách trừ timestamp của hai entry mà chưa hiểu chúng đánh dấu thời điểm nào.

### 11.2. Runtime graph để đối chiếu cấu hình đang chạy

Spring Integration cung cấp `IntegrationGraphServer` để lấy mô hình runtime của các thành phần và liên kết; xem [Integration Graph](https://docs.spring.io/spring-integration/reference/graph.html).

Graph hữu ích để kiểm tra tên thực tế, nhánh discard, các channel trung gian do DSL tạo và wiring sau triển khai. Nó không phải lịch sử xử lý theo mã đơn, cũng không tự chứng minh message đã được tiêu thụ.

Trong ứng dụng Boot có Actuator, endpoint `integrationgraph` và `metrics` hỗ trợ kiểm tra cấu hình và số liệu. Nếu dùng HTTP, cấu hình exposure thích hợp, ví dụ trong môi trường thực hành:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,integrationgraph
~~~

Sau khi có lưu lượng, xem danh sách meter ở `/actuator/metrics` và graph ở `/actuator/integrationgraph` với base path mặc định. Việc truy cập còn phụ thuộc web stack, cấu hình access và bảo mật. Xem [Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).

Graph có thể làm lộ tên thành phần hoặc biểu thức cấu hình. Chọn phạm vi truy cập phù hợp với người cần chẩn đoán hệ thống.

## 12. Áp dụng cho các mẫu tích hợp khác

Các quy tắc dưới đây là đề xuất thiết kế tín hiệu quan sát cho ứng dụng, không phải tên metric tự động do framework luôn tạo.

| Thành phần | Điểm cần thấy | Nguy cơ nếu thiếu quan sát |
| --- | --- | --- |
| Transformer | Kiểu dữ liệu trước/sau, phiên bản chuyển đổi, lỗi ánh xạ | Không biết dữ liệu hỏng tại biên nào |
| Filter | Số thông điệp đi tiếp, bị loại và reason code | Lưu lượng biến mất mà không có kết quả |
| Router | Route key đã chuẩn hóa, nhánh được chọn, fallback | Nhánh sai hoặc nhánh mặc định tăng mà khó phát hiện |
| Splitter | Số phần tạo ra, khóa nhóm và metadata thứ tự cần thiết | Khó đối chiếu phần thiếu với yêu cầu gốc |
| Aggregator | Số nhóm đang chờ, tuổi nhóm, release, expiry, discard | Group chờ vô hạn hoặc kết quả thiếu phần |
| Gateway | Hợp đồng phản hồi, timeout, lỗi và kết quả caller nhận | Caller timeout nhưng downstream vẫn hoàn tất |
| Outbound endpoint | Thời gian gọi, lần thử, xác nhận từ hệ thống đích | Nhầm đã gửi với đã được chấp nhận |

Với splitter/aggregator, số message vào và ra thường không bằng nhau. Ví dụ một đơn có năm dòng tạo năm message con, sau đó ghép thành một kết quả. Dashboard phải phân biệt đơn hàng, phần tử con, nhóm và lần thử.

Với aggregator, một metric “số nhóm mở” chưa cho biết chúng đang xử lý bình thường hay bị kẹt. Nên kết hợp tuổi nhóm, số phần đã nhận, điều kiện release và hành động khi hết hạn. Dùng ID nhóm cụ thể trong log chẩn đoán; tránh tạo metric tag cho từng ID nhóm.

Với router, chọn reason code và route label trong một danh mục hữu hạn. Nếu tên route được tạo động từ dữ liệu đầu vào, cần kiểm soát cả số route lẫn số series metric.

## 13. Thiết kế dashboard và cảnh báo theo kết quả

Một dashboard đầu tiên nên giúp trả lời năm điều: có nhận việc không, có hoàn tất không, tỷ lệ lỗi thay đổi ra sao, mất bao lâu và việc đang dồn ở đâu.

### 13.1. Các phép tính cần định nghĩa mẫu số

Ví dụ với flow không retry, mỗi yêu cầu có một kết quả cuối:

~~~text
Tỷ lệ thất bại kỹ thuật trong một cửa sổ
  = số kết quả failed
    / (số processed + số rejected + số failed)
~~~

Nếu cần đo tỷ lệ lỗi của bước xử lý sau filter, mẫu số có thể là `processed + failed`. Hai phép đo trả lời hai câu hỏi khác nhau; ghi rõ tên và ý nghĩa trên dashboard.

Khi có retry, phải xác định đang đo theo lần thử hay theo yêu cầu duy nhất. Một đơn lỗi hai lần rồi thành công tạo ba lần thử nhưng chỉ một kết quả cuối. Không gọi counter theo lần thử là “số đơn thất bại cuối”.

Counter tích lũy phụ thuộc tuổi tiến trình. Đối với biểu đồ lưu lượng, thường xem tốc độ tăng theo cửa sổ và xử lý reset khi restart. Micrometer giải thích cách diễn giải counter trong [Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html).

### 13.2. Độ trễ và tồn đọng

Theo dõi đồng thời:

- Độ trễ toàn luồng theo hợp đồng nghiệp vụ.
- Thời gian tại bước xử lý hoặc dependency quan trọng.
- Số phần tử chờ và mức sử dụng capacity.
- Tuổi công việc cũ nhất nếu hệ thống đo được.
- Lưu lượng vào và lưu lượng ra.

Không lấy trung bình các giá trị p95 của từng instance để tạo p95 chung. Nếu cần percentile tổng hợp, chọn histogram và cách truy vấn backend phù hợp; cấu hình thu thập phân phối phải có trước.

Ví dụ queue tăng từ 100 lên 900 phần tử trong khi thời gian handler gần như giữ nguyên: kiểm tra chênh lệch tốc độ vào/ra, số consumer, executor và thời gian chờ poller trước khi kết luận thuật toán xử lý chậm.

Ngược lại, queue không lớn nhưng tuổi message cao có thể liên quan đến một phần tử bị kẹt, ưu tiên xử lý hoặc retry kéo dài. Mỗi triệu chứng cần một giả thuyết và bằng chứng bổ sung.

### 13.3. Cảnh báo gắn với hành động

| Điều kiện tham khảo | Hành động điều tra |
| --- | --- |
| Lỗi kỹ thuật tăng kéo dài và đủ lưu lượng | Chọn endpoint lỗi, lấy trace/correlation ID đại diện |
| Tuổi công việc vượt giới hạn nghiệp vụ | Kiểm tra consumer, backlog và dependency |
| Có đầu vào nhưng lâu không có kết quả cuối | Kiểm tra filter, router, nhóm aggregator, endpoint dừng |
| Nhánh telemetry liên tục bỏ sự kiện | Kiểm tra capacity, exporter và chính sách lấy mẫu |
| Tỷ lệ reject tăng bất thường | So sánh schema, nguồn gửi và thay đổi quy tắc |

Ngưỡng phải dựa trên mục tiêu phục vụ và lưu lượng của hệ thống. Ví dụ “95% đơn hợp lệ hoàn tất trong 2 giây” chỉ có nghĩa khi xác định điểm bắt đầu, điểm kết thúc, cách xử lý retry và yêu cầu hết hạn.

## 14. Kiểm tra khả năng quan sát

Không chỉ kiểm tra có dòng log. Hãy kiểm tra tín hiệu có phản ánh đúng hành vi và có thể dùng để lần theo yêu cầu.

| Kịch bản | Kiểm tra nghiệp vụ | Kiểm tra quan sát |
| --- | --- | --- |
| Đơn hợp lệ | Chạy đúng bước xử lý | Một kết quả processed, correlation ID giữ nguyên |
| Dữ liệu sai | Không gọi process | Có rejected và reason code hữu hạn |
| Handler ném exception | Caller nhận lỗi hoặc đi đường lỗi đã cấu hình | Có mốc lỗi đúng endpoint, không đếm trùng kết quả |
| Message tạo mới sau transform | Giá trị chuẩn hóa đúng | Không phụ thuộc ID kỹ thuật giữ nguyên |
| Retry rồi thành công | Side effect đúng hợp đồng idempotency | Phân biệt lần thử với kết quả cuối |
| Nhánh telemetry bị dừng | Hành vi đúng chính sách quá tải | Có tín hiệu buffer đầy hoặc mất telemetry |
| ID chứa xuống dòng hoặc dữ liệu nhạy cảm | Validation đúng quy tắc | Trường log được lọc, không ghi toàn payload |
| Đổi DirectChannel sang queue | Giao nhận và poller đúng | Thời gian gửi không bị hiểu thành thời gian hoàn tất |

Với ví dụ phần 6, chụp giá trị counter trước khi gửi rồi so phần tăng sau từng Message. Nếu test dùng chung registry hoặc application context, không giả định mọi counter đều bắt đầu bằng 0.

Đối với bất đồng bộ, đợi một điều kiện cụ thể với timeout hữu hạn: kết quả xuất hiện, counter tăng hoặc Message đến channel kiểm thử. Tránh chỉ ngủ một khoảng cố định rồi kết luận, vì thời gian lập lịch thay đổi theo tải.

Để kiểm tra ảnh hưởng của telemetry, so sánh kết quả nghiệp vụ khi bật và tắt nhánh quan sát, đồng thời gây tình huống exporter chậm hoặc buffer đầy. Kiểm tra cả dữ liệu đầu ra, side effect, lỗi caller nhận và giới hạn tài nguyên.

Để kiểm tra cardinality, gửi nhiều đơn với mã khác nhau nhưng cùng tập outcome/region. Số tổ hợp tag nghiệp vụ phải giữ trong phạm vi đã thiết kế.

## 15. Trình tự chẩn đoán một yêu cầu mất dấu

Giả sử khách hàng báo đơn `ORD-101` chưa có kết quả.

1. Tìm trạng thái nghiệp vụ bền vững theo mã đơn để biết kết quả đã được xác nhận chưa.
2. Tìm log tiếp nhận và lấy business correlation ID.
3. Đối chiếu các mốc chuẩn hóa, route, reject, process, retry hoặc expiry.
4. Nếu có trace, xem đoạn thực thi cuối cùng và ranh giới bất đồng bộ.
5. Kiểm tra backlog, tuổi công việc, poller, executor hoặc nhóm aggregator tại đoạn còn chờ.
6. Đối chiếu runtime graph với wiring dự kiến.
7. Kiểm tra nhánh telemetry có bị lấy mẫu, lỗi xuất hoặc bỏ sự kiện trước khi kết luận thông điệp bị mất.
8. Chọn hành động phục hồi dựa trên trạng thái nghiệp vụ và hợp đồng idempotency.

Không tìm thấy log là một dấu hiệu cần điều tra, chưa phải bằng chứng duy nhất rằng công việc không chạy.

## 16. Các lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách điều chỉnh |
| --- | --- | --- |
| Log toàn Message ở mọi bước | Lộ dữ liệu, tăng dung lượng và chi phí | Chọn mốc và trường được phép |
| Gọi enqueue thành công là xử lý thành công | Dashboard tốt trong khi backlog tăng | Ghi kết quả tại endpoint sở hữu hoàn tất |
| Chỉ theo dõi nhánh thành công | Không giải thích được dữ liệu bị filter loại | Quan sát discard, fallback và expiry |
| Dùng mã đơn làm tag | Số chuỗi tăng theo dữ liệu | Đưa mã đơn vào log/trace phù hợp |
| Tưởng wire tap tự chạy bất đồng bộ | Nhánh log làm tăng thời gian caller chờ | Chọn channel đích và giới hạn rõ |
| Cộng mọi timer thành thời gian toàn luồng | Đếm trùng khoảng xử lý | Xác định ranh giới và quan hệ lồng nhau |
| Tăng cùng counter ở handler và error logger | Tỷ lệ lỗi bị phóng đại | Chọn một nơi sở hữu sự kiện kết quả |
| Dùng message ID làm khóa nghiệp vụ xuyên suốt | Đứt liên kết sau tạo message mới | Dùng khóa nghiệp vụ và correlation ID |
| Chỉ đếm exception | Bỏ sót reject, timeout và chờ nhóm | Theo dõi trạng thái nghiệp vụ |
| Nhánh quan sát không giới hạn buffer | Tốn tài nguyên và ảnh hưởng flow | Bounded buffer, chính sách overflow, số liệu quá tải |

Một flow có thể quan sát cần một hợp đồng nhất quán giữa topology, định danh, sự kiện và kết quả đo. Khi hợp đồng đó rõ, từng tín hiệu đều giúp giải thích một phần cụ thể của hành vi đang chạy.
