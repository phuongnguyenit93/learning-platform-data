# Phát sự kiện đơn hàng từ REST bằng StreamBridge

Một ứng dụng Spring Cloud Stream không nhất thiết phải nhận message đầu tiên từ Kafka, RabbitMQ hoặc Pulsar. Nguồn phát có thể là một REST API: khách hàng gửi yêu cầu tạo đơn hàng, ứng dụng kiểm tra dữ liệu, tạo sự kiện nghiệp vụ rồi chuyển sự kiện vào broker để các service phía sau xử lý độc lập.

`StreamBridge` là cầu nối cho trường hợp đó. Nó cho phép controller hoặc service không phải `Supplier` gửi một object hoặc `Message` đến output binding của Spring Cloud Stream. Binder vẫn thực hiện chuyển đổi payload, partitioning và gửi message theo cấu hình của binding. Bài thực hành xây dựng luồng **REST → Order API → StreamBridge → Kafka/RabbitMQ/Pulsar → consumer**; đồng thời làm rõ binding tĩnh và destination động, phản hồi HTTP, schema sự kiện, lỗi gửi, idempotency, outbox và kiểm thử.

## 1. Mục tiêu và luồng xử lý

Sau bài thực hành, bạn có thể:

- Nhận yêu cầu tạo đơn hàng qua REST và validate request.
- Tạo event độc lập với DTO của REST API.
- Gửi event qua `StreamBridge` vào output binding có tên rõ ràng.
- Cấu hình destination, binder, content type và headers.
- Trả HTTP `202 Accepted` phù hợp với xử lý bất đồng bộ.
- Phân biệt binding tĩnh với dynamic destination.
- Xử lý trường hợp send bị từ chối hoặc lỗi publish bất đồng bộ.
- Thiết kế idempotency và transactional outbox khi cần bảo đảm không mất yêu cầu.
- Kiểm thử bằng Test Binder và integration test với broker thật.

### Dependency tối thiểu

Ví dụ Maven cho REST API phát qua Kafka:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-stream-kafka</artifactId>
</dependency>
~~~

Quản lý phiên bản Spring Boot và Spring Cloud Stream bằng BOM tương thích với nhau; không tự trộn các phiên bản binder và framework khác release train. Nếu dùng RabbitMQ hoặc Pulsar, thay dependency binder tương ứng.

Luồng cơ bản:

~~~text
Client
  |
  | POST /api/orders
  v
Order REST Controller
  | validate request / authenticate
  v
Order Application Service
  | create OrderCreated event
  v
StreamBridge.send("orders-out-0", message)
  |
  v
Spring Cloud Stream output binding
  |
  v
Kafka topic / Rabbit exchange+queue / Pulsar topic
  |
  +--> inventory-service
  +--> payment-service
  +--> notification-service
~~~

REST request và event message có mục đích khác nhau. Request mô tả điều khách hàng muốn; event mô tả điều hệ thống xác nhận đã xảy ra. Không phát nguyên DTO request nếu nó chứa trường chỉ phục vụ giao diện, thông tin bí mật hoặc cấu trúc dễ thay đổi.

## 2. Chọn output binding tĩnh

Nếu đơn hàng luôn được gửi đến một destination đã biết trước, khai báo output binding khi ứng dụng khởi động:

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: orders-out-0
      bindings:
        orders-out-0:
          destination: orders.created
          content-type: application/json
          binder: kafka
~~~

Trong ví dụ:

- `orders-out-0` là tên binding logic mà code truyền cho `StreamBridge`.
- `orders.created` là destination trên broker, ví dụ Kafka topic hoặc destination tương ứng của binder.
- `content-type: application/json` mô tả định dạng payload để Spring Cloud Stream thực hiện conversion.
- `binder: kafka` chọn binder được cấu hình tên `kafka`. Nếu ứng dụng chỉ có một binder mặc định, có thể không cần chỉ rõ thuộc tính này.
- `output-bindings` yêu cầu tạo binding trước khi REST request đầu tiên đến.

Đây là lựa chọn phù hợp khi luồng nghiệp vụ có destination cố định. Nó giúp lỗi cấu hình xuất hiện sớm lúc khởi động, dễ giám sát và dễ kiểm soát quyền truy cập destination.

Nếu ứng dụng dùng RabbitMQ, đổi binder và cấu hình connection tương ứng, giữ tên binding logic nếu muốn code không phụ thuộc broker:

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: orders-out-0
      bindings:
        orders-out-0:
          destination: orders.created
          content-type: application/json
          binder: rabbit
~~~

Với Pulsar, dùng binder Pulsar đã được cấu hình và destination theo quy ước của binder đó. Không dùng cấu hình producer Kafka hoặc RabbitMQ cho Pulsar chỉ vì tên binding giống nhau.

## 3. Khai báo event contract

Tạo event biểu diễn một đơn hàng đã được chấp nhận:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

public record OrderCreated(
    UUID eventId,
    int schemaVersion,
    String orderId,
    String customerId,
    List<OrderLine> lines,
    BigDecimal total,
    String currency,
    Instant occurredAt,
    String correlationId
) {
    public OrderCreated {
        lines = List.copyOf(lines);
    }

    public record OrderLine(
        String sku,
        int quantity,
        BigDecimal unitPrice
    ) { }
}
~~~

Các trường nên có ý nghĩa ổn định:

| Trường | Mục đích |
|---|---|
| `eventId` | ID duy nhất cho lần phát event; hỗ trợ deduplication |
| `schemaVersion` | Phiên bản contract để consumer biết cách diễn giải |
| `orderId` | ID đơn hàng trong domain |
| `customerId` | Chủ thể nghiệp vụ; chỉ đưa vào event nếu consumer cần |
| `lines` | Các dòng hàng đã được xác nhận |
| `total`/`currency` | Tổng tiền và đơn vị tiền tệ |
| `occurredAt` | Thời điểm nghiệp vụ xảy ra, UTC |
| `correlationId` | Liên kết các bước xử lý cùng một yêu cầu |

Không dùng thời điểm consumer nhận message thay cho `occurredAt`. Không dùng `eventId` thay `orderId`: một đơn hàng có thể phát nhiều loại event trong vòng đời của nó.

Event nên là immutable record hoặc class chỉ có getter. Sau khi đã publish, không sửa event cũ theo kiểu ghi đè; nếu cần thông tin mới, phát event tiếp theo hoặc định nghĩa schema tương thích.

## 4. Tạo REST request và response riêng

DTO nhận từ HTTP không phải event:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Positive;
import java.math.BigDecimal;
import java.util.List;

public record CreateOrderRequest(
    @NotBlank String customerId,
    @jakarta.validation.constraints.Pattern(regexp = "[A-Z]{3}")
    String currency,
    @NotEmpty List<@Valid OrderLineRequest> lines
) {
    public record OrderLineRequest(
        @NotBlank String sku,
        @Positive int quantity,
        @Positive BigDecimal unitPrice
    ) { }
}
~~~

Response thể hiện API đã nhận yêu cầu:

~~~java
import java.net.URI;

public record OrderAcceptedResponse(
    String orderId,
    String eventId,
    String status
) { }
~~~

Một API có thể trả `orderId` để client truy vấn trạng thái ở endpoint khác. Không khẳng định đơn hàng đã thanh toán, trừ khi thanh toán thực sự đã hoàn tất trong cùng quy trình.

## 5. Tạo event từ request và gửi bằng StreamBridge

Service chịu trách nhiệm chuyển đổi request thành event:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;
import org.springframework.util.MimeTypeUtils;

@Service
public class OrderCommandService {

    private final StreamBridge streamBridge;

    public OrderCommandService(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public OrderCreated submit(CreateOrderRequest request) {
        BigDecimal total = request.lines().stream()
            .map(line -> line.unitPrice()
                .multiply(BigDecimal.valueOf(line.quantity())))
            .reduce(BigDecimal.ZERO, BigDecimal::add);

        UUID eventId = UUID.randomUUID();
        String orderId = UUID.randomUUID().toString();
        String correlationId = UUID.randomUUID().toString();

        var lines = request.lines().stream()
            .map(line -> new OrderCreated.OrderLine(
                line.sku(), line.quantity(), line.unitPrice()))
            .toList();

        OrderCreated event = new OrderCreated(
            eventId,
            1,
            orderId,
            request.customerId(),
            lines,
            total,
            request.currency(),
            Instant.now(),
            correlationId
        );

        Message<OrderCreated> message = MessageBuilder
            .withPayload(event)
            .setHeader("eventId", eventId.toString())
            .setHeader("correlationId", correlationId)
            .setHeader(
                org.springframework.messaging.MessageHeaders.CONTENT_TYPE,
                MimeTypeUtils.APPLICATION_JSON
            )
            .build();

        boolean sent = streamBridge.send("orders-out-0", message);
        if (!sent) {
            throw new EventPublicationRejectedException(
                "Output binding did not accept the order event");
        }

        return event;
    }
}
~~~

Đây là ví dụ thực hành đường đi của event; dự án thật cần bổ sung kiểm tra giá, tồn kho, quy tắc tiền tệ, quyền mua hàng và lưu đơn hàng theo transaction nghiệp vụ.

Điểm cần nhớ:

- Inject `StreamBridge` từ package `org.springframework.cloud.stream.function`.
- Truyền tên **binding logic** `orders-out-0`, không phải tên topic `orders.created` khi đã khai báo binding tĩnh.
- Có thể truyền POJO trực tiếp; framework thực hiện output conversion theo cấu hình binding. Truyền `Message` khi cần đặt headers rõ ràng.
- Header `contentType` giúp chỉ định conversion; cấu hình binding cũng có thể xác định content type.
- `send` trả về boolean. Nếu `false`, channel không nhận message; ứng dụng không nên trả trạng thái accepted như thể đã gửi.
- Nếu binder có kết quả gửi bất đồng bộ, lỗi broker có thể xảy ra sau lời gọi `send`; cần cấu hình và xử lý send failure phù hợp với binder.

Không đưa toàn bộ HTTP headers vào event. Chỉ truyền correlation ID, tenant hoặc trace context khi có hợp đồng rõ, đã lọc dữ liệu nhạy cảm và consumer thực sự cần.

## 5.1. Consumer downstream nhận event

Để hoàn tất luồng minh họa, một service độc lập có thể nhận event bằng function:

~~~java
@Configuration(proxyBeanMethods = false)
class InventoryFunctions {

    @Bean
    Consumer<OrderCreated> reserveInventory(InventoryService inventory) {
        return event -> inventory.reserve(
            event.orderId(),
            event.lines()
        );
    }
}
~~~

Cấu hình input binding ở service inventory (các thuộc tính binding nằm dưới `spring.cloud.stream`):

~~~yaml
spring:
  cloud:
    function:
      definition: reserveInventory
    stream:
      bindings:
        reserveInventory-in-0:
          destination: orders.created
          group: inventory-service
          content-type: application/json
~~~

Producer và consumer phải dùng schema tương thích. Consumer cần xử lý idempotent theo `eventId`/`orderId` vì broker có thể redeliver sau restart hoặc lỗi commit. Mỗi service có consumer group riêng nếu đều cần nhận bản sao của mọi event; các instance của cùng service dùng chung group để chia tải.

## 6. Tạo REST endpoint

Controller validate request trước khi gọi service:

~~~java
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import java.net.URI;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderCommandService orderCommandService;

    public OrderController(OrderCommandService orderCommandService) {
        this.orderCommandService = orderCommandService;
    }

    @PostMapping
    public ResponseEntity<OrderAcceptedResponse> create(
            @Valid @RequestBody CreateOrderRequest request) {

        OrderCreated event = orderCommandService.submit(request);

        var response = new OrderAcceptedResponse(
            event.orderId(),
            event.eventId().toString(),
            "ACCEPTED"
        );

        return ResponseEntity
            .accepted()
            .location(URI.create("/api/orders/" + event.orderId()))
            .body(response);
    }
}
~~~

HTTP `202 Accepted` phù hợp khi yêu cầu đã được nhận để xử lý bất đồng bộ nhưng quy trình phía sau chưa hoàn tất. Nó không có nghĩa inventory, payment hoặc notification đã thành công.

Nếu `send` trả `false` hoặc phát sinh lỗi đồng bộ trước khi yêu cầu được chấp nhận, API có thể trả `503 Service Unavailable` để client retry theo chính sách. Nếu request sai, trả `400 Bad Request`. Nếu idempotency key đã được dùng cho nội dung khác, có thể trả `409 Conflict`.

Ví dụ exception và ánh xạ lỗi publish đồng bộ:

~~~java
public class EventPublicationRejectedException
        extends RuntimeException {
    public EventPublicationRejectedException(String message) {
        super(message);
    }
}
~~~

~~~java
@RestControllerAdvice
class OrderApiExceptionHandler {

    @ExceptionHandler(EventPublicationRejectedException.class)
    ResponseEntity<Map<String, String>> publicationRejected(
            EventPublicationRejectedException exception) {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
            .body(Map.of(
                "code", "EVENT_PUBLICATION_REJECTED",
                "message", "Order event could not be accepted"
            ));
    }
}
~~~

Không trả nội dung exception nội bộ cho client. Trong hệ thống production, bổ sung error code/correlation ID và log nguyên nhân đã được lọc dữ liệu nhạy cảm.

## 7. Send thành công không đồng nghĩa consumer đã xử lý xong

Phân biệt các mốc:

| Mốc | Ý nghĩa |
|---|---|
| REST validation passed | Request hợp lệ về mặt cấu trúc và quy tắc đã kiểm tra |
| `StreamBridge.send` trả `true` | Output channel chấp nhận message theo cơ chế gửi của binding |
| Broker publisher acknowledgement | Broker xác nhận publish theo semantics của binder/protocol |
| Consumer nhận message | Một consumer group/subscription đã lấy được message |
| Consumer xử lý xong | Nghiệp vụ downstream hoàn tất |
| Consumer commit/ack | Tiến độ nhận message được xác nhận theo broker |

`StreamBridge.send` trả `true` không chứng minh consumer đã nhận hoặc xử lý event. Với producer/binder gửi bất đồng bộ, cũng không được diễn giải boolean này thành bằng chứng message đã được broker lưu bền vững. Cần đọc tài liệu binder, bật publisher confirms/acknowledgement hoặc cơ chế send-result phù hợp nếu yêu cầu API phụ thuộc vào broker acknowledgement.

Mặc định `StreamBridge` gửi trên thread của caller. Có thể gọi `setAsync(true)` để chuyển việc gửi sang executor khi muốn tránh chặn request thread; tuy nhiên việc này làm thay đổi thời điểm lỗi được quan sát và có thể ảnh hưởng context tracing. Chỉ bật sau khi đã có giới hạn executor, metrics, error handling và kiểm thử tải.

~~~java
streamBridge.setAsync(true);
boolean acceptedByChannel =
    streamBridge.send("orders-out-0", message);
~~~

Đoạn code trên chỉ minh họa API asynchronous; không dùng riêng boolean trả về để quyết định một publish đã được broker xác nhận. Khi bật async, cấu hình Micrometer context propagation nếu cần giữ trace context qua ranh giới thread, và xử lý lỗi gửi theo binder.

## 8. Pre-create output binding hay dùng dynamic destination?

### Output binding tạo lúc khởi động

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: orders-out-0
      bindings:
        orders-out-0:
          destination: orders.created
          content-type: application/json
~~~

Gửi bằng:

~~~java
streamBridge.send("orders-out-0", event);
~~~

Ưu điểm: destination cố định, cấu hình rõ, provisioning xảy ra khi khởi động và có thể quan sát binding như một output binding thông thường.

### Dynamic destination khi thật sự cần chọn đích lúc chạy

~~~java
streamBridge.send("orders.created", event);
~~~

Nếu `orders.created` chưa là binding, StreamBridge có thể tạo output binding động và yêu cầu binder provision destination theo tên đó. Các binding động được cache để tái sử dụng; cache có cơ chế tự loại bỏ với kích thước mặc định 10 trong tài liệu hiện hành. Binding động không được quản lý trong application context giống binding khai báo tĩnh.

Nếu cho phép client truyền destination tùy ý từ URL hoặc JSON, một request có thể tạo nhiều destination và làm tăng rủi ro tài nguyên, dữ liệu sai tuyến hoặc lạm dụng broker. Nếu thật sự cần dynamic destination:

- Dùng allow-list bằng `spring.cloud.stream.dynamicDestinations`.
- Chuyển một business code đã được kiểm tra thành destination từ danh mục server-side.
- Không dùng trực tiếp path variable hoặc field request chưa xác thực làm tên topic/exchange.
- Theo dõi số binding động, cache eviction và provisioning errors.

Ví dụ giới hạn destination:

~~~yaml
spring:
  cloud:
    stream:
      dynamic-destinations:
        - orders.created
        - orders.priority
~~~

Khi destination đã biết trước, ưu tiên output binding tĩnh thay vì dynamic binding.

## 9. Nhiều binder trong cùng ứng dụng

Một ứng dụng có thể nhận message từ Kafka và phát event sang RabbitMQ. Với StreamBridge, có overload để chỉ rõ binder name khi tạo binding động:

~~~java
streamBridge.send("orders-out-0", "rabbit", message);
~~~

Tuy nhiên, nếu output binding đã được tạo bởi `spring.cloud.stream.output-bindings` hoặc đã được bind trước với một binder, tham số binder name của `send` không thay đổi binder đã gắn. Khi muốn chọn binder cố định, khai báo ngay trong binding:

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: orders-out-0
      bindings:
        orders-out-0:
          destination: orders.created
          binder: rabbit
~~~

Tên `rabbit` phải khớp với named binder instance đã cấu hình. Đừng nhầm binder name với loại middleware hoặc destination name.

## 10. Chọn content type và headers

Spring Cloud Stream hỗ trợ content type từ binding hoặc header của message. Với REST → StreamBridge:

- Binding tĩnh có thể đặt `content-type: application/json`.
- Gửi `Message` có thể đặt `MessageHeaders.CONTENT_TYPE`.
- Overload `send(bindingName, data, MimeType)` cho phép chỉ định output content type.

Ví dụ:

~~~java
boolean sent = streamBridge.send(
    "orders-out-0",
    event,
    MimeTypeUtils.APPLICATION_JSON
);
~~~

Chỉ chọn một contract nhất quán giữa producer và consumer. Nếu bật `useNativeEncoding` cho Kafka, serialization được giao cho Kafka client serializer và không còn dựa trên content type conversion như trường hợp mặc định. Khi đó cấu hình serializer/deserializer phải tương thích giữa các ứng dụng.

Headers thường hữu ích:

| Header | Mục đích |
|---|---|
| `eventId` | Định danh event và deduplication |
| `correlationId` | Theo dõi một luồng nghiệp vụ |
| `contentType` | Hướng dẫn conversion |
| `traceparent` | W3C trace context nếu được propagation đúng cách |
| `tenantId` | Chỉ khi multi-tenant contract cho phép và đã kiểm tra giá trị |

Không truyền Authorization bearer token, cookie, session ID, password hoặc toàn bộ HTTP header sang broker.

## 11. Lỗi publish và cách phản hồi REST

Lỗi có thể xuất hiện ở nhiều thời điểm:

| Thời điểm | Ví dụ | Xử lý |
|---|---|---|
| Trước send | Request validation, mapping event lỗi | Trả 400 hoặc lỗi nghiệp vụ thích hợp |
| Binding creation | Sai binder, thiếu destination, không provision được | Ghi log/correlation, trả lỗi dịch vụ; sửa cấu hình |
| Channel send | Channel từ chối hoặc không có subscriber phù hợp | Kiểm tra boolean, không trả accepted |
| Producer/broker async | Network timeout, broker unavailable, authorization | Bật cơ chế send failure phù hợp, alert/retry có kiểm soát |
| Sau publish | Consumer lỗi, schema không tương thích, downstream timeout | Consumer retry/DLQ/recovery; REST API không thể đồng bộ kết quả này |

Binding property `error-channel-enabled` có thể bật error channel cho async send result khi binder hỗ trợ. Với Kafka binder, send failure có thể được gửi thành `ErrorMessage` chứa `KafkaSendFailureException`; binder không tự động chuyển producer exception sang DLQ như consumer failure. Cần tạo flow xử lý producer error phù hợp và không giả định DLQ consumer áp dụng cho REST producer.

Không retry vô hạn ngay trong REST request. Client có thể timeout rồi gửi lại, trong khi publish đầu tiên đã thành công. Dùng idempotency key và trạng thái request để tránh tạo hai đơn hàng.

## 12. Idempotency cho REST retry

Một tình huống thường gặp:

1. Client gửi `POST /api/orders`.
2. Server publish event thành công nhưng response bị mất trên mạng.
3. Client gửi lại cùng yêu cầu.
4. Nếu server tạo `orderId`/`eventId` mới, downstream có thể tạo hai đơn hàng.

Thiết kế API nên nhận `Idempotency-Key`:

~~~http
POST /api/orders
Idempotency-Key: 8e5a...client-generated-key
Content-Type: application/json
~~~

Lưu key cùng hash của request và kết quả xử lý trong kho dữ liệu có unique constraint:

- Key mới: ghi nhận request và tạo một operation.
- Key đã tồn tại với cùng request hash: trả lại cùng `orderId`/`eventId` hoặc trạng thái operation hiện tại.
- Key đã tồn tại với request hash khác: trả `409 Conflict`.

Không lưu idempotency key chỉ trong memory của một pod: request retry có thể đến instance khác hoặc sau restart. TTL/retention của key phải dài hơn cửa sổ retry của client và quy trình nghiệp vụ.

Idempotency ở REST không thay thế idempotency ở consumer. Consumer vẫn cần deduplicate theo `eventId` hoặc áp dụng unique constraint/inbox pattern vì broker có thể redeliver.

Khi áp dụng vào controller ở phần trước, thêm header bắt buộc và chuyển request qua một thành phần idempotency có lưu trữ bền vững:

~~~java
@PostMapping
public ResponseEntity<OrderAcceptedResponse> create(
        @Valid @RequestBody CreateOrderRequest request,
        @RequestHeader("Idempotency-Key") String idempotencyKey) {

    // This facade atomically claims the key, checks the request hash,
    // and returns the same operation for a repeated identical request.
    OrderCreated event =
        idempotentOrderSubmission.submit(idempotencyKey, request);

    return ResponseEntity.accepted()
        .location(URI.create("/api/orders/" + event.orderId()))
        .body(new OrderAcceptedResponse(
            event.orderId(), event.eventId().toString(), "ACCEPTED"));
}
~~~

`IdempotentOrderSubmission` là service ứng dụng dựa trên repository/transaction của database; không thay bằng `ConcurrentHashMap` trong bộ nhớ vì nhiều instance và restart sẽ làm mất tính duy nhất. Nếu dùng transactional outbox ở phần kế tiếp, thao tác claim idempotency, lưu order và insert outbox row nên nằm trong cùng transaction database.

## 13. Transactional outbox khi không được phép mất yêu cầu

Gửi event trực tiếp từ REST qua broker và ghi đơn hàng vào database là hai thao tác trên hai hệ thống khác nhau. Nếu database commit nhưng publish thất bại, đơn hàng tồn tại mà event không được phát. Nếu publish thành công rồi database rollback, consumer có thể nhận event của một đơn hàng không được lưu.

Khi yêu cầu chấp nhận đơn hàng phải bền vững, dùng **transactional outbox**:

~~~text
REST request
   |
   v
Database transaction
   |-- insert order
   |-- insert outbox event (same transaction)
   v
Commit database
   |
   v
Outbox relay reads pending event
   |
   v
StreamBridge -> broker
   |
   v
Broker confirms publish
   |
   v
Mark outbox row as published
~~~

REST API trả `202 Accepted` sau khi transaction database lưu cả order và outbox record. Relay có thể retry khi broker unavailable. Nếu relay crash sau khi broker đã nhận event nhưng trước khi đánh dấu outbox đã publish, event có thể được gửi lại; consumer phải idempotent theo `eventId`.

Không đánh dấu outbox published chỉ vì `StreamBridge.send` trả `true` nếu binder gửi bất đồng bộ và chưa có broker confirmation. Cần tích hợp publisher confirm/ack hoặc cơ chế send result của binder để xác định thời điểm đánh dấu an toàn. Không tuyên bố exactly-once xuyên database và broker khi chưa có transaction phân tán phù hợp.

Outbox cũng cần:

- Index cho trạng thái pending và thời gian tạo.
- Giới hạn batch/claim để nhiều relay không gửi trùng cùng row.
- Retry với backoff và cảnh báo khi row quá cũ.
- Cơ chế cleanup sau thời gian lưu trữ.
- Metrics pending count, oldest pending age, publish error và retry count.
- Consumer inbox/deduplication để chịu được duplicate.

## 14. Cấu hình producer theo binder

### Kafka Binder

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.created
          content-type: application/json
      kafka:
        bindings:
          orders-out-0:
            producer:
              sync: false
              configuration:
                acks: all
                enable.idempotence: true
                compression.type: lz4
~~~

Các thuộc tính Kafka cần được chọn theo yêu cầu durability và tải. `acks=all` cùng replication/min.insync.replicas phù hợp khi cần broker xác nhận theo điều kiện replica; `enable.idempotence` giảm duplicate do producer retry trong phạm vi bảo đảm Kafka producer. Compression giảm network/disk nhưng tiêu thụ CPU. Không coi idempotence của producer là idempotency nghiệp vụ của order consumer.

### RabbitMQ Binder

RabbitMQ dùng exchange, queue, routing key, delivery mode và publisher confirms theo cấu hình binder. Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.created
          content-type: application/json
      rabbit:
        bindings:
          orders-out-0:
            producer:
              delivery-mode: PERSISTENT
~~~

Kiểm tra exchange/queue durability, message persistence và publisher confirm/return theo version binder và broker policy. Một queue durable không tự làm mọi message persistent; durability của topology và delivery mode là hai khía cạnh riêng.

### Pulsar Binder

Pulsar có topic, schema, producer batching và send timeout riêng. Giữ `content-type`/schema contract nhất quán với consumer và cấu hình producer theo tài liệu Pulsar binder của phiên bản dự án. Không copy `acks` hoặc `delivery-mode` của Kafka/RabbitMQ sang Pulsar.

## 15. Bảo mật endpoint và destination

REST endpoint là ranh giới public của luồng event. Cần:

- Xác thực client và kiểm tra quyền tạo đơn hàng.
- Validate quantity, currency, SKU và giới hạn số dòng hàng.
- Giới hạn request body, rate limit và timeout.
- Không để client chỉ định trực tiếp topic/exchange/binder.
- Không cho client tự đặt event ID nếu không có quy ước xác thực.
- Lọc headers; không chuyển token/cookie vào message.
- Dùng TLS và credentials phù hợp cho REST và broker.
- Phân quyền producer chỉ publish vào destination cần thiết.
- Bảo vệ Actuator, metrics và error endpoint.
- Log event ID/correlation ID, không log thông tin thanh toán hoặc payload nhạy cảm.

Nếu nhiều tenant, tenant ID phải được lấy từ security context đã xác thực hoặc được kiểm tra với danh mục server-side; không tin một header tùy ý từ client.

## 16. Kiểm thử service với StreamOperations

`StreamBridge` triển khai contract `StreamOperations` gồm các phương thức send. Có thể inject interface này để mock trong unit test:

~~~java
@ExtendWith(MockitoExtension.class)
class OrderCommandServiceTest {

    @Mock
    StreamOperations streamOperations;

    @Test
    void publishesOrderCreatedEvent() {
        when(streamOperations.send(
            eq("orders-out-0"), any(Message.class)))
            .thenReturn(true);

        // Construct service with StreamOperations in this test variant.
        // Submit a valid request and capture the Message.

        ArgumentCaptor<Message<?>> captor =
            ArgumentCaptor.forClass(Message.class);
        verify(streamOperations).send(
            eq("orders-out-0"), captor.capture());

        assertThat(captor.getValue().getPayload())
            .isInstanceOf(OrderCreated.class);
    }
}
~~~

Ví dụ tập trung vào cách mock/capture message; constructor của service có thể nhận `StreamOperations` thay vì concrete `StreamBridge` để test dễ hơn. Trong application context, Spring cung cấp `StreamBridge` implement interface này.

Các assertion cần có:

- Binding name đúng.
- Payload là `OrderCreated`, không phải REST request DTO.
- `eventId` và `orderId` khác nhau theo contract.
- Header `contentType` là JSON.
- `correlationId` được giữ nguyên giữa log/response/event.
- Khi send trả `false`, service không trả kết quả accepted.

## 17. Integration test với Test Binder

Test Binder kiểm tra đường đi trong JVM mà không cần Kafka/Rabbit/Pulsar:

~~~java
@SpringBootTest(properties = {
    "spring.cloud.stream.output-bindings=orders-out-0",
    "spring.cloud.stream.bindings.orders-out-0.destination=orders.created",
    "spring.cloud.stream.bindings.orders-out-0.content-type=application/json"
})
@EnableTestBinder
class OrderStreamBridgeIntegrationTest {

    @Autowired
    StreamBridge streamBridge;

    @Autowired
    OutputDestination output;

    @Test
    void sendsOrderEventToConfiguredOutputBinding() {
        OrderCreated event = sampleOrderCreated();

        assertThat(streamBridge.send("orders-out-0", event))
            .isTrue();

        Message<byte[]> received =
            output.receive(1_000, "orders-out-0");

        assertThat(received).isNotNull();
        assertThat(received.getHeaders().get(
            MessageHeaders.CONTENT_TYPE).toString())
            .contains("application/json");
    }
}
~~~

Trong một số version/test configuration, destination argument của `OutputDestination.receive` là binding name hoặc destination name tùy cách test binder expose output; kiểm tra API của version đang dùng. Có thể deserialize payload bytes thành `OrderCreated` bằng Jackson rồi assert các trường. Nếu không dùng `@EnableTestBinder`, có thể cấu hình test binder theo hướng dẫn của version dự án.

Test Binder không xác minh broker thật đã provision topic/queue, publisher confirms, Kafka partition/acks, Rabbit exchange/queue durability hoặc Pulsar subscription. Hãy có integration test với broker đích trong CI hoặc môi trường kiểm thử.

## 18. REST API test và hợp đồng HTTP

Dùng MockMvc/WebTestClient để xác minh:

| Request | Kết quả mong đợi |
|---|---|
| Body hợp lệ | `202 Accepted`, có order ID/event ID |
| Thiếu customer ID | `400 Bad Request` |
| Quantity bằng 0 hoặc âm | `400 Bad Request` |
| Currency không hỗ trợ | `400 Bad Request` hoặc lỗi domain đã quy định |
| StreamBridge trả false | Lỗi tạm thời, ví dụ `503` |
| Broker send lỗi theo cơ chế đồng bộ | Lỗi được map thành response phù hợp |
| Cùng idempotency key và cùng request | Trả cùng operation/order, không tạo event mới |
| Cùng idempotency key nhưng request khác | `409 Conflict` |
| Không có quyền tạo order | `401`/`403` |

Không đưa stack trace hoặc tên broker nội bộ vào response public. Trả error code và correlation ID để đội vận hành tra cứu.

## 19. Vận hành và quan sát

Dashboard cho REST → StreamBridge nên theo dõi:

- Số request tạo đơn hàng, 2xx/4xx/5xx và latency p50/p95/p99.
- Validation failures, idempotency hits/conflicts.
- Số lần `StreamBridge.send` được gọi, true/false/exception.
- Producer send latency, async send failure và broker confirmation nếu có.
- Binding creation/provisioning failure và dynamic binding cache eviction nếu dùng dynamic destination.
- Broker topic/queue depth, consumer lag, retry và DLQ.
- Outbox pending count/oldest age/retry count nếu dùng outbox.
- Event ID và correlation ID xuyên suốt producer/consumer.

Không dùng `orderId` hoặc `eventId` làm metric label vì cardinality tăng theo traffic. Chúng phù hợp với log/traces có kiểm soát. Metrics nên dùng tên binding, destination đã chuẩn hóa, status code và loại lỗi có tập giá trị giới hạn.

Đặt alert khi producer send errors tăng, outbox quá hạn, queue/lag tăng liên tục hoặc consumer completion rate giảm. REST endpoint có thể vẫn trả 202 trong khi downstream đang bị nghẽn; vì vậy phải giám sát cả broker và consumer.

## 20. Quy trình chạy thực hành

1. Tạo Spring Boot app có Spring Web, Validation, Spring Cloud Stream và binder Kafka hoặc RabbitMQ.
2. Tạo `OrderCreated` event và `CreateOrderRequest` DTO riêng.
3. Khai báo output binding `orders-out-0` trỏ tới destination `orders.created`.
4. Inject `StreamBridge` vào service; chuyển request thành event và gửi message.
5. Tạo REST `POST /api/orders` với `@Valid` và response `202 Accepted`.
6. Gửi request hợp lệ và xác minh event trên broker hoặc Test Binder.
7. Thử request thiếu trường, số lượng âm, currency sai và event conversion lỗi.
8. Tạm dừng broker hoặc thu hồi quyền publish trong môi trường test để kiểm tra lỗi gửi.
9. Gửi cùng idempotency key nhiều lần; xác nhận không tạo nhiều order/event.
10. Chạy consumer downstream, xác nhận event có schema đúng và business logic xử lý idempotent.
11. Nếu yêu cầu durable acceptance, bổ sung database transaction + outbox relay + broker confirmation.
12. Chạy tải tăng dần và theo dõi REST latency, producer send errors, broker backlog và consumer lag.

Ví dụ HTTP:

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{
    "customerId": "customer-42",
    "currency": "VND",
    "lines": [
      {"sku": "SKU-100", "quantity": 2, "unitPrice": 125000},
      {"sku": "SKU-200", "quantity": 1, "unitPrice": 75000}
    ]
  }'
~~~

Request trên khớp với controller minh họa cơ bản. Nếu đã áp dụng biến thể idempotency ở mục 12, thêm header `Idempotency-Key` theo hợp đồng API.

Kết quả response có dạng:

~~~http
HTTP/1.1 202 Accepted
Location: /api/orders/<order-id>
Content-Type: application/json

{
  "orderId": "<order-id>",
  "eventId": "<event-id>",
  "status": "ACCEPTED"
}
~~~

Giá trị ID chỉ minh họa; server sinh ID thật và lưu theo quy tắc idempotency.

## 21. Sự cố thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không tìm thấy output binding | Gõ sai binding name hoặc thiếu output binding/dynamic setup | So sánh tên trong code với `output-bindings` và `bindings` |
| Topic/exchange mới xuất hiện | Dùng destination động hoặc thiếu `destination` | Khai báo binding tĩnh và destination rõ |
| `send` trả false | Channel không nhận message | Kiểm tra binding lifecycle, channel và binder |
| `send` true nhưng consumer không thấy event | Broker send async lỗi, sai topic/group, consumer chưa chạy hoặc serialization mismatch | Kiểm tra send failure, broker metadata, destination và consumer |
| JSON không deserialize | Content type, serializer hoặc schema không khớp | Kiểm tra binding content type, Message header và native encoding |
| REST trả 202 nhưng event mất | Chỉ dựa vào channel send, không có durable outbox/confirm | Dùng publisher confirmation hoặc transactional outbox |
| Client retry tạo hai order | Thiếu idempotency key hoặc key chỉ lưu in-memory | Dùng persistent unique constraint |
| Consumer xử lý event hai lần | Redelivery hoặc outbox relay retry | Deduplicate bằng event ID/inbox/unique constraint |
| Dynamic binding tăng liên tục | Destination lấy trực tiếp từ input | Allow-list, chuẩn hóa destination và theo dõi cache |
| Trace bị đứt khi async send | Thread boundary không propagate context | Cấu hình Micrometer context propagation |
| Producer lỗi nhưng không vào DLQ | DLQ consumer không xử lý producer send failure | Dùng binder producer error channel/send result |
| Nhiều binder gửi nhầm broker | Binder name không khớp hoặc binding đã được tạo với binder khác | Khai báo binder ở binding tĩnh và kiểm tra named binder |

## 22. Checklist trước khi đưa vào production

- [ ] REST request DTO và event contract tách biệt.
- [ ] Request được validate và xác thực/ủy quyền trước khi publish.
- [ ] Event có event ID, schema version, occurredAt và correlation ID.
- [ ] Output binding tĩnh có destination và binder rõ ràng nếu destination đã biết.
- [ ] Content type, serializer và consumer deserializer tương thích.
- [ ] Không chuyển HTTP token/cookie hoặc dữ liệu nhạy cảm vào message.
- [ ] Phân biệt channel send result, broker publisher confirmation và consumer completion.
- [ ] Lỗi đồng bộ và bất đồng bộ có cơ chế xử lý/alert.
- [ ] Dynamic destinations được allow-list và không lấy trực tiếp từ input chưa kiểm tra.
- [ ] REST retry có idempotency key lưu bền vững.
- [ ] Consumer downstream idempotent với duplicate event.
- [ ] Nếu yêu cầu durable acceptance, đã có transactional outbox và publisher confirmation.
- [ ] Đã kiểm thử Test Binder, REST contract và broker integration.
- [ ] Đã kiểm thử broker unavailable, serialization failure, retry và duplicate.
- [ ] Dashboard có REST latency, producer error, broker backlog và consumer lag.
- [ ] Đã có quy trình replay/reconciliation cho event lỗi.

**Kết luận:** REST API là một nguồn phát event hợp lệ trong ứng dụng Spring Cloud Stream. Dùng `StreamBridge` để gửi event vào output binding, ưu tiên binding tĩnh khi destination đã biết và dùng dynamic destination có allow-list khi thực sự cần. Trả `202 Accepted` đúng với mức cam kết của hệ thống; phân biệt channel send với broker confirmation và consumer completion. Khi không được phép mất yêu cầu, kết hợp transactional outbox, publisher confirmation và consumer idempotency để xử lý an toàn qua lỗi và retry.

## Tài liệu tham khảo

- [Spring Cloud Stream — Producing and Consuming Messages / StreamBridge](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream 5.1 — StreamBridge, Async Send and Dynamic Destinations](https://docs.spring.io/spring-cloud-stream/reference/5.1/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream — Error Handling](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html)
- [Spring Cloud Stream — Kafka Binder Error Channels](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/error-channels.html)
- [Spring Cloud Stream — Event Routing and Dynamic Destinations](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/event-routing.html)
