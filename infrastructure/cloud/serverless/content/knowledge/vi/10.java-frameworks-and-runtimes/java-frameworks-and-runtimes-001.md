# Xây dựng function bằng Java thuần và adapter nền tảng

Một serverless function không nhất thiết phải được viết bằng một framework cụ thể. Ở mức ứng dụng, function có thể chỉ là một lớp Java nhận dữ liệu đầu vào, gọi logic nghiệp vụ và trả kết quả. Khi triển khai lên AWS Lambda, Azure Functions, Google Cloud Functions hoặc một nền tảng khác, một lớp adapter chuyển đổi định dạng trigger và context của nền tảng thành hợp đồng mà phần Java thuần hiểu được.

Cách tổ chức này tách hai mối quan tâm: **logic nghiệp vụ** quyết định ứng dụng làm gì; **adapter nền tảng** quyết định dữ liệu HTTP, message hoặc event được nhận và phản hồi theo giao thức nào. Lõi Java có thể được kiểm thử bằng unit test thông thường, còn adapter chỉ cần kiểm tra việc ánh xạ input, output, lỗi, danh tính và metadata của trigger.

## 1. Function Java thực chất cần những gì?

Ở mức đơn giản, một function có ba phần:

1. **Input contract:** dữ liệu đầu vào và các metadata cần thiết như request ID, tenant, correlation ID hoặc thời hạn xử lý.
2. **Business logic:** xác thực quy tắc nghiệp vụ, đọc/ghi dữ liệu và quyết định kết quả.
3. **Output contract:** kết quả thành công hoặc lỗi có cấu trúc để adapter chuyển thành HTTP response, message acknowledgement hoặc event result.

Ví dụ một function tạo đơn hàng có thể nhận `PlaceOrderRequest`, kiểm tra các mặt hàng và trả `PlaceOrderResult`. Lõi nghiệp vụ không cần biết request đến từ API Gateway, Azure HTTP trigger hay một queue consumer.

```text
HTTP / Queue / Event
        |
        v
Platform adapter
  - deserialize input
  - read identity and metadata
  - map platform context
        |
        v
Plain Java function / use case
  - validate business rules
  - call repository and services
  - return result or domain error
        |
        v
Platform adapter
  - map result/error
  - HTTP response or ACK/retry
```

Adapter không phải nơi chứa toàn bộ nghiệp vụ. Nếu một function có nhiều trigger, nhiều endpoint hoặc nhiều nền tảng, việc giữ lõi nghiệp vụ độc lập sẽ giảm trùng lặp và giúp thay đổi hạ tầng ít ảnh hưởng đến domain.

## 2. Thiết kế lõi bằng Java thuần

Java thuần ở đây có nghĩa là lớp nghiệp vụ chỉ phụ thuộc JDK và các interface do ứng dụng định nghĩa. Nó không cần import annotation, request class hoặc SDK riêng của cloud provider. Có thể dùng record, class, interface và exception thông thường.

Có thể biểu diễn một phép biến đổi đồng bộ trong process bằng `java.util.function.Function<PlaceOrderRequest, PlaceOrderResult>` hoặc method reference như `useCase::execute`. Đây chỉ là functional interface của Java; nó không tự tạo ra deployment entry point, trigger, retry hay cơ chế scale của FaaS. Runtime vẫn cần adapter hoặc framework để biết cách gọi ứng dụng.

Ví dụ contract cho yêu cầu tạo đơn:

```java
import java.util.List;

public record PlaceOrderRequest(
        String customerId,
        List<OrderLineRequest> items,
        String idempotencyKey
) {}

public record OrderLineRequest(
        String productId,
        int quantity
) {}

public record PlaceOrderResult(
        String orderId,
        String status
) {}
```

Các kiểu dữ liệu trên là contract của ứng dụng. Không đưa `APIGatewayProxyRequestEvent`, `HttpRequestMessage`, `CloudEvent` hoặc class của SDK vào DTO nghiệp vụ nếu không cần thiết. Adapter có thể chuyển các kiểu dữ liệu nền tảng sang DTO này.

`record` có từ Java 16. Nếu runtime mục tiêu dùng Java 11 hoặc thấp hơn, hãy biểu diễn contract bằng class thông thường với constructor, getter và quy tắc bất biến tương đương. Luôn chọn cú pháp theo JDK mà nền tảng triển khai hỗ trợ.

Tiếp theo, định nghĩa interface cho các phụ thuộc mà use case cần:

```java
import java.util.Optional;

public interface OrderRepository {
    Optional<PlaceOrderResult> findByIdempotencyKey(
            String customerId,
            String idempotencyKey
    );

    void save(String customerId, PlaceOrderRequest request,
              PlaceOrderResult result);
}

public interface OrderIdGenerator {
    String nextId();
}
```

Use case xử lý quy tắc nghiệp vụ và dùng các interface trên thay vì tự khởi tạo database client hoặc đọc biến môi trường:

```java
import java.util.Objects;

public final class PlaceOrderUseCase {
    private final OrderRepository orders;
    private final OrderIdGenerator ids;

    public PlaceOrderUseCase(OrderRepository orders,
                             OrderIdGenerator ids) {
        this.orders = Objects.requireNonNull(orders);
        this.ids = Objects.requireNonNull(ids);
    }

    public PlaceOrderResult execute(PlaceOrderRequest request) {
        validate(request);

        var previous = orders.findByIdempotencyKey(
                request.customerId(), request.idempotencyKey());
        if (previous.isPresent()) {
            return previous.get();
        }

        var result = new PlaceOrderResult(ids.nextId(), "PLACED");
        orders.save(request.customerId(), request, result);
        return result;
    }

    private void validate(PlaceOrderRequest request) {
        if (request == null || request.customerId() == null
                || request.customerId().isBlank()) {
            throw new InvalidOrderException("customerId is required");
        }
        if (request.idempotencyKey() == null
                || request.idempotencyKey().isBlank()) {
            throw new InvalidOrderException("idempotencyKey is required");
        }
        if (request.items() == null || request.items().isEmpty()) {
            throw new InvalidOrderException("at least one item is required");
        }
        for (var item : request.items()) {
            if (item == null || item.productId() == null
                    || item.productId().isBlank() || item.quantity() <= 0) {
                throw new InvalidOrderException("invalid order item");
            }
        }
    }
}
```

`InvalidOrderException` là exception do ứng dụng định nghĩa. Trong hệ thống thật, việc tìm idempotency key và lưu đơn phải được bảo vệ bằng unique constraint hoặc transaction/conditional write; đoạn code rút gọn trên chỉ minh họa luồng gọi, không tự bảo đảm an toàn khi hai invocation chạy đồng thời. Nếu key đã tồn tại với request hash khác, use case cần trả conflict thay vì trả kết quả cũ một cách mù quáng.

Một exception tối giản có thể được khai báo như sau:

```java
public final class InvalidOrderException extends RuntimeException {
    public InvalidOrderException(String message) {
        super(message);
    }
}
```

Lõi này không biết function chạy trên cloud nào. Có thể gọi `execute` từ unit test, HTTP adapter, message handler hoặc một ứng dụng Java chạy cục bộ.

## 3. Phân biệt function handler với adapter nền tảng

Trong nhiều nền tảng, người triển khai phải cung cấp một entry point theo interface hoặc quy ước mà runtime nhận biết. Entry point đó là adapter. Runtime gọi adapter, adapter đọc trigger envelope và gọi lõi Java.

| Loại trigger | Dữ liệu adapter nhận | Việc adapter thường phải làm |
| --- | --- | --- |
| HTTP | Method, path, headers, query, body, identity | Validate giao thức, parse body, map status/header/body |
| Queue/message | Message ID, body, receive count, visibility/ack metadata | Parse message, gọi handler, ACK hoặc để retry theo giao thức |
| Event bus | Event envelope, source, type, time, data | Validate schema/source, map event và chống duplicate |
| Scheduler | Thời điểm kích hoạt, schedule metadata | Xác định kỳ chạy, tránh chạy trùng và xử lý thời gian trễ |

Một HTTP adapter cần quan tâm status code và response headers. Một queue adapter cần hiểu ACK, batch và retry. Một event adapter cần kiểm tra `eventId`, `source`, `type` và schema. Không nên dùng cùng một cách trả lỗi cho mọi trigger: HTTP có thể trả 4xx/5xx, trong khi queue thường cần ném lỗi hoặc trả partial batch failure để event source giao lại message.

## 4. Một adapter HTTP độc lập với nhà cung cấp

Trước khi nối SDK cụ thể, có thể tạo một lớp adapter nội bộ với contract nhỏ:

```java
public record FunctionRequest<T>(
        T body,
        String requestId,
        String correlationId,
        String tenantId
) {}

public record FunctionResponse<T>(
        int statusCode,
        T body,
        String correlationId
) {}

public final class PlaceOrderFunction {
    private final PlaceOrderUseCase useCase;

    public PlaceOrderFunction(PlaceOrderUseCase useCase) {
        this.useCase = useCase;
    }

    public FunctionResponse<PlaceOrderResult> handle(
            FunctionRequest<PlaceOrderRequest> request
    ) {
        var result = useCase.execute(request.body());
        return new FunctionResponse<>(201, result,
                request.correlationId());
    }
}
```

Lớp `PlaceOrderFunction` là entry point của ứng dụng, nhưng vẫn chưa gắn với cloud provider. Adapter nền tảng sẽ tạo `FunctionRequest`, gọi `handle` và chuyển `FunctionResponse` sang kiểu response của runtime.

Với ví dụ này, tenant và customer identity phải được lấy từ danh tính đã xác thực, không tin trường do client tự khai báo. Trong code rút gọn, phần xác thực được giả định đã thực hiện trước khi gọi function.

## 5. Adapter AWS Lambda bằng RequestHandler

AWS Lambda Java runtime cung cấp interface `RequestHandler<I, O>`. Runtime deserialize payload thành kiểu `I`, gọi `handleRequest` và serialize giá trị trả về thành output. Đây là cách đơn giản để xử lý một event JSON có cấu trúc.

```java
import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;

public final class PlaceOrderLambdaHandler
        implements RequestHandler<PlaceOrderRequest, PlaceOrderResult> {

    private final PlaceOrderUseCase useCase =
            ApplicationFactory.createPlaceOrderUseCase();

    @Override
    public PlaceOrderResult handleRequest(
            PlaceOrderRequest input,
            Context context
    ) {
        // Request ID hữu ích cho log và tracing.
        String requestId = context.getAwsRequestId();
        context.getLogger().log("Handling place order: " + requestId);
        return useCase.execute(input);
    }
}
```

Ví dụ trên minh họa Lambda invocation trực tiếp với JSON có cấu trúc tương ứng `PlaceOrderRequest`. `Context` cung cấp metadata của invocation như request ID, function name, memory limit và thời gian còn lại. Không đưa `Context` vào domain model; nếu cần deadline hoặc correlation ID, hãy ánh xạ các giá trị cần thiết sang một object nội bộ.

Nếu Lambda được gọi qua API Gateway, input thường là một event envelope chứa method, path, headers, body và request context. Khi đó, handler cần dùng kiểu event tương ứng (ví dụ API Gateway HTTP API event) hoặc adapter/framework hỗ trợ gateway để parse body và tạo HTTP response. `RequestHandler<PlaceOrderRequest, PlaceOrderResult>` không tự động biến thành một HTTP API handler.

Với SQS hoặc stream, event có thể chứa nhiều record trong một invocation. Adapter phải xử lý semantics của batch, ACK và partial batch response theo event source mapping. Không được giả định một invocation luôn tương ứng một message.

## 6. Adapter Azure Functions bằng Java annotation

Azure Functions Java dùng annotation để khai báo function name và trigger binding. Runtime gọi method có annotation; method nhận các kiểu request/context của Azure và trả response theo binding.

Ví dụ HTTP trigger dùng body dạng chuỗi để adapter chủ động deserialize:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.microsoft.azure.functions.HttpMethod;
import com.microsoft.azure.functions.HttpRequestMessage;
import com.microsoft.azure.functions.HttpResponseMessage;
import com.microsoft.azure.functions.HttpStatus;
import com.microsoft.azure.functions.ExecutionContext;
import com.microsoft.azure.functions.annotation.AuthorizationLevel;
import com.microsoft.azure.functions.annotation.FunctionName;
import com.microsoft.azure.functions.annotation.HttpTrigger;
import java.util.Optional;

public final class PlaceOrderAzureFunction {
    private static final ObjectMapper JSON = new ObjectMapper();
    private final PlaceOrderUseCase useCase =
            ApplicationFactory.createPlaceOrderUseCase();

    @FunctionName("placeOrder")
    public HttpResponseMessage run(
            @HttpTrigger(name = "request",
                    methods = {HttpMethod.POST},
                    authLevel = AuthorizationLevel.FUNCTION)
            HttpRequestMessage<Optional<String>> request,
            ExecutionContext context
    ) throws Exception {
        String rawBody = request.getBody().orElse("");
        PlaceOrderRequest input = JSON.readValue(
                rawBody, PlaceOrderRequest.class);

        PlaceOrderResult result = useCase.execute(input);
        context.getLogger().info(
                "Place order invocation: " + context.getInvocationId());

        return request.createResponseBuilder(HttpStatus.CREATED)
                .header("Content-Type", "application/json")
                .body(JSON.writeValueAsString(result))
                .build();
    }
}
```

Đây là ví dụ minh họa cách nối Azure HTTP trigger với lõi Java. Cần khai báo dependency Azure Functions Java library, annotation processor/plugin đóng gói theo hướng dẫn của phiên bản runtime đang dùng và cấu hình authorization phù hợp. `AuthorizationLevel.FUNCTION` là một mức bảo vệ bằng function key; API production thường cần xác thực người dùng/ứng dụng và phân quyền nghiệp vụ rõ ràng. Không ghi function key hoặc token vào log.

Azure cũng có trigger cho queue, timer, Event Hubs và các dịch vụ khác. Mỗi binding có kiểu dữ liệu và hành vi retry riêng; hãy viết adapter phù hợp với trigger thay vì cố chuyển tất cả thành HTTP request giả.

## 7. Adapter Google Cloud Functions Framework cho HTTP

Functions Framework cho Java định nghĩa interface `HttpFunction`. Runtime gọi method `service` với request và response abstraction. Adapter đọc request, parse body, gọi lõi và ghi response.

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.cloud.functions.HttpFunction;
import com.google.cloud.functions.HttpRequest;
import com.google.cloud.functions.HttpResponse;
import java.io.IOException;

public final class PlaceOrderGoogleFunction implements HttpFunction {
    private static final ObjectMapper JSON = new ObjectMapper();
    private final PlaceOrderUseCase useCase =
            ApplicationFactory.createPlaceOrderUseCase();

    @Override
    public void service(HttpRequest request, HttpResponse response)
            throws IOException {
        if (!"POST".equalsIgnoreCase(request.getMethod())) {
            response.setStatusCode(405);
            response.getWriter().write("Method not allowed");
            return;
        }

        PlaceOrderRequest input = JSON.readValue(
                request.getReader(), PlaceOrderRequest.class);
        PlaceOrderResult result = useCase.execute(input);

        response.setStatusCode(201);
        response.setContentType("application/json");
        JSON.writeValue(response.getWriter(), result);
    }
}
```

Lớp này minh họa HTTP adapter của Functions Framework. Khi chạy local, framework có thể khởi động function bằng entry point được cấu hình; khi deploy, môi trường đích cung cấp runtime và cấu hình target. Xác thực, authorization, request size limit và error mapping vẫn phải được thiết kế theo dịch vụ triển khai.

Google cũng hỗ trợ function nhận CloudEvents qua interface tương ứng. Trong adapter event, hãy đọc event ID, source, type và data; sau đó map sang command/event nội bộ. Không giả định CloudEvent có cùng schema với HTTP request.

Ví dụ một CloudEvents adapter chỉ đọc envelope và chuyển payload sang handler nội bộ:

```java
import com.google.cloud.functions.CloudEventsFunction;
import io.cloudevents.CloudEvent;
import java.nio.charset.StandardCharsets;

public final class OrderCreatedCloudEventFunction
        implements CloudEventsFunction {
    private final OrderCreatedHandler handler =
            ApplicationFactory.createOrderCreatedHandler();

    @Override
    public void accept(CloudEvent event) throws Exception {
        if (!"com.example.orders.order-created.v1".equals(event.getType())) {
            throw new IllegalArgumentException("unsupported event type");
        }
        if (event.getData() == null) {
            throw new IllegalArgumentException("event data is required");
        }

        String json = new String(
                event.getData().toBytes(), StandardCharsets.UTF_8);
        OrderCreatedMessage message =
                JsonSupport.mapper().readValue(json, OrderCreatedMessage.class);

        // Envelope ID là định danh delivery ổn định cho event.
        OrderCreatedMessage normalized = new OrderCreatedMessage(
                event.getId(), message.orderId(), message.customerId(),
                event.getSource().toString(), message.schemaVersion());
        handler.handle(normalized);
    }
}
```

`JsonSupport` là helper cấu hình Jackson của ứng dụng trong ví dụ. Khi triển khai, cần kiểm tra schema/version và nguồn event được phép, xử lý trường hợp `data` có media type hoặc encoding khác, đồng thời bảo đảm handler idempotent vì event có thể được giao lại.

## 8. Adapter cho message và event

Một queue consumer thường không trả response nghiệp vụ về cho producer. Kết quả quan trọng là message đã được xử lý và ACK hay chưa. Ví dụ một handler nội bộ có thể nhận message đã chuẩn hóa:

```java
public record OrderCreatedMessage(
        String eventId,
        String orderId,
        String customerId,
        String source,
        int schemaVersion
) {}

public interface OrderCreatedHandler {
    void handle(OrderCreatedMessage message);
}
```

Adapter của queue sẽ deserialize message, validate schema/version, gọi handler và quyết định ACK/retry theo giao thức. Nếu xử lý thành công, adapter xác nhận message. Nếu lỗi tạm thời, nó có thể ném exception hoặc đánh dấu record thất bại để event source giao lại. Nếu lỗi dữ liệu không thể phục hồi, cần chuyển sang DLQ hoặc luồng xử lý lỗi theo chính sách.

Ví dụ handler dùng idempotency theo event ID:

```java
public interface ProcessedEventRepository {
    boolean markProcessedIfAbsent(String eventId);
}

public final class OrderCreatedEventHandler
        implements OrderCreatedHandler {
    private final ProcessedEventRepository processedEvents;
    private final CustomerNotificationService notifications;

    public OrderCreatedEventHandler(
            ProcessedEventRepository processedEvents,
            CustomerNotificationService notifications
    ) {
        this.processedEvents = processedEvents;
        this.notifications = notifications;
    }

    @Override
    public void handle(OrderCreatedMessage message) {
        if (!processedEvents.markProcessedIfAbsent(message.eventId())) {
            return;
        }
        notifications.sendOrderConfirmation(message.orderId());
    }
}
```

Đoạn code này chỉ phác họa ý tưởng; trong hệ thống thật, đánh dấu event đã xử lý và tạo side effect phải được phối hợp nguyên tử hoặc qua outbox/inbox. Nếu đánh dấu trước rồi gửi thông báo thất bại, lần retry sẽ bị bỏ qua và thông báo bị mất. Nếu gửi trước rồi đánh dấu thất bại, thông báo có thể bị gửi trùng. Hãy dùng transaction/outbox, idempotency của downstream hoặc trạng thái xử lý đủ chi tiết.

Với batch trigger, adapter phải trả đúng danh sách record thất bại nếu nền tảng hỗ trợ partial batch response. Nếu một record lỗi nhưng adapter ném lỗi cho toàn batch, các record đã thành công có thể bị giao lại và cần idempotent.

## 9. Context của nền tảng: chỉ lấy điều ứng dụng thực sự cần

Runtime thường cung cấp context khác nhau. Một số thông tin hữu ích gồm:

- Request/invocation ID để nối log và trace.
- Deadline hoặc thời gian còn lại để giới hạn downstream call.
- Function name, version, region hoặc deployment metadata để chẩn đoán.
- Identity/claims đã được xác thực nếu trigger và gateway cung cấp đáng tin cậy.
- Correlation ID, traceparent hoặc event ID để liên kết các bước.
- Cancellation/interruption signal nếu runtime hoặc thư viện hỗ trợ.

Không chuyển toàn bộ context object của provider vào service nghiệp vụ. Tạo một kiểu context nội bộ nhỏ, chỉ chứa dữ liệu cần thiết:

```java
import java.time.Duration;

public record InvocationMetadata(
        String invocationId,
        String correlationId,
        String tenantId,
        Duration remainingTime
) {}
```

Adapter đọc metadata từ context nền tảng, xác thực nguồn gốc, rồi tạo `InvocationMetadata`. `tenantId` phải đến từ identity/claim đã được xác thực hoặc từ mapping đáng tin cậy, không lấy tùy tiện từ header do client gửi. Nếu nền tảng không cung cấp deadline, adapter có thể dùng timeout ứng dụng đã cấu hình và chừa khoảng dự phòng.

Khi gọi HTTP client, database hoặc SDK, hãy dùng thời gian còn lại để đặt timeout nhỏ hơn deadline function. Nếu function còn 800 ms, không nên bắt đầu một lời gọi downstream có thể chờ 10 giây. Không phải runtime nào cũng cho phép hủy hoàn toàn tác vụ phụ thuộc khi invocation kết thúc; do đó side effect vẫn cần idempotency.

## 10. Khởi tạo dependency và vòng đời runtime

Serverless runtime có thể tái sử dụng một execution environment cho nhiều invocation, nhưng không đảm bảo điều đó. Một số object có thể được tạo một lần khi runtime khởi động và dùng lại; các object khác nên được tạo theo invocation.

| Loại tài nguyên | Cách quản lý thường phù hợp |
| --- | --- |
| JSON mapper, validator, cấu hình bất biến | Tái sử dụng nếu thread-safe |
| HTTP client/SDK client thread-safe | Tái sử dụng giữa invocation khi thư viện và runtime hỗ trợ |
| Connection pool | Dùng pool nhỏ, có health check/timeout và giới hạn tổng concurrency |
| Request DTO, mutable state, security context | Tạo riêng cho invocation |
| Transaction, connection, stream, temporary file | Mở và đóng trong phạm vi thao tác; dọn dẹp đúng cách |
| Dữ liệu nghiệp vụ cần sống qua invocation | Lưu trong database/object storage/workflow state |

Có thể dùng factory để tạo use case và dependency:

```java
public final class ApplicationFactory {
    private ApplicationFactory() {}

    public static PlaceOrderUseCase createPlaceOrderUseCase() {
        OrderRepository repository = createOrderRepository();
        OrderIdGenerator ids = new UuidOrderIdGenerator();
        return new PlaceOrderUseCase(repository, ids);
    }

    private static OrderRepository createOrderRepository() {
        // Tạo repository dựa trên cấu hình và client dùng chung phù hợp.
        throw new UnsupportedOperationException("configure persistence adapter");
    }
}
```

Factory ở đây là điểm minh họa cho composition root. Trong ứng dụng thật, có thể dùng constructor injection với DI framework, factory tự viết hoặc cơ chế dependency injection mà nền tảng hỗ trợ. Không khởi tạo một database connection mới cho mỗi request nếu có thể dùng pool/client an toàn; cũng không giữ một transaction hoặc request state trong field dùng chung.

Các field dùng chung phải an toàn với concurrency. Runtime có thể xử lý nhiều request đồng thời tùy nền tảng và cấu hình. Tránh lưu `currentUser`, request body hoặc biến mutable theo invocation trong field `static`/instance dùng chung.

## 11. Error mapping và semantics của trigger

Lõi Java nên phân loại lỗi theo ý nghĩa nghiệp vụ và khả năng retry. Adapter quyết định biểu diễn lỗi theo giao thức:

| Lỗi từ lõi | HTTP adapter | Queue/event adapter |
| --- | --- | --- |
| Input không hợp lệ | `400 Bad Request` | Thường là lỗi không retry; chuyển DLQ/quarantine theo chính sách |
| Không xác thực/không đủ quyền | `401`/`403` | Từ chối xử lý; kiểm tra cấu hình quyền và tránh retry vô hạn |
| Tài nguyên nghiệp vụ không tồn tại | `404` hoặc mã nghiệp vụ theo contract | Có thể là lỗi dữ liệu không retry |
| Xung đột idempotency/state | `409 Conflict` | Có thể bỏ qua duplicate đã xử lý hoặc đưa vào điều tra nếu conflict bất thường |
| Downstream tạm thời lỗi | `502`/`503`/`504` tùy API | Retry có giới hạn và backoff |
| Lỗi không dự kiến | `500 Internal Server Error` | Retry theo policy, sau đó DLQ/cảnh báo |

Không trả stack trace, SQL, tên host nội bộ hoặc secret ra client. Log chi tiết ở phía server với request ID và correlation ID. Với HTTP, một response 500 có thể khiến client retry; nếu thao tác đã tạo side effect trước lỗi, cần idempotency. Với queue, ném exception thường khiến message được retry theo event source policy; hành vi cụ thể tùy nền tảng.

Đừng bắt mọi exception rồi trả kết quả thành công rỗng. Điều đó làm runtime ACK message hoặc báo request thành công dù nghiệp vụ chưa hoàn tất. Hãy phân biệt lỗi có thể retry, lỗi không retry và kết quả đã được xử lý idempotent.

## 12. Kiểm thử lõi và adapter

Tách lõi và adapter giúp chia chiến lược test:

### Unit test cho Java thuần

Unit test gọi trực tiếp use case, thay repository bằng fake hoặc mock. Không cần khởi động cloud runtime hay tạo HTTP server.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class PlaceOrderUseCaseTest {
    @Test
    void createsOrderWhenRequestIsValid() {
        OrderRepository repository = new InMemoryOrderRepository();
        OrderIdGenerator ids = () -> "order-100";
        var useCase = new PlaceOrderUseCase(repository, ids);

        var request = new PlaceOrderRequest(
                "customer-1",
                java.util.List.of(new OrderLineRequest("book-1", 2)),
                "checkout-100");

        var result = useCase.execute(request);

        assertEquals("order-100", result.orderId());
        assertEquals("PLACED", result.status());
    }
}
```

`InMemoryOrderRepository` là fake dành cho test. Nên có thêm test cho input sai, idempotency key lặp, key trùng với request hash khác, lỗi repository và concurrency. Những test này xác minh logic nghiệp vụ, không phụ thuộc annotation hoặc runtime.

### Adapter test

Adapter test kiểm tra:

- JSON body được deserialize đúng và lỗi parse được map thành 400.
- HTTP method/path/header và response status/body đúng contract.
- Identity và correlation ID được lấy từ nguồn đáng tin.
- Message ID/event ID được truyền nguyên vẹn vào handler.
- Lỗi tạm thời được báo cho runtime để retry; lỗi không retry đi vào luồng xử lý phù hợp.
- Batch adapter chỉ báo thất bại cho record lỗi nếu hỗ trợ partial batch.

### Local integration và cloud test

Có thể chạy Functions Framework hoặc emulator/local runtime để kiểm tra đóng gói, entry point và binding. Sau đó dùng môi trường cloud thử quyền IAM, timeout, retry, concurrency, payload size và observability. Unit test không chứng minh adapter được cấu hình đúng trong deployment; ngược lại, một lần deploy thành công cũng không thay thế test logic nghiệp vụ.

## 13. Đóng gói và cấu hình entry point

Runtime cần biết class hoặc function entry point nào phải gọi, dependency nào cần có và cách khởi động ứng dụng. Cách cấu hình khác nhau theo nền tảng:

- AWS Lambda Java thường đóng gói JAR (thường là shaded/uber JAR hoặc ZIP chứa dependency theo runtime model) và cấu hình handler class/method theo quy ước Lambda.
- Azure Functions Java dùng Maven/Gradle plugin và annotation/binding để tạo artifact, metadata function và cấu hình host.
- Google Cloud Functions Framework Java dùng dependency framework, class implement interface phù hợp và target entry point do môi trường deploy cấu hình.
- Container-based function/runtime có thể đóng gói JAR cùng base image và command khởi động; nền tảng gọi theo HTTP hoặc event adapter mà container cung cấp.

Đừng sao chép cấu hình handler của một provider sang provider khác. Kiểm tra phiên bản JDK được runtime hỗ trợ, target bytecode, dependency packaging, biến môi trường, memory/CPU, timeout, network access và quyền truy cập dịch vụ.

### Cấu hình ngoài mã nguồn

Đưa các giá trị thay đổi theo môi trường ra configuration:

- Tên bảng, bucket, queue/topic và endpoint của downstream.
- Timeout ứng dụng, retry limit và batch size.
- Feature flag, giới hạn kích thước payload và retention.
- Mức log và tracing.

Secret và credential nên được lấy từ secret manager hoặc cơ chế bảo mật tương đương, không commit vào source hoặc ghi vào log. Mỗi function nên có identity/role riêng với quyền tối thiểu cần thiết.

## 14. Framework Java: khi nào cần và khi nào không?

Java thuần đủ cho một function nhỏ, ít dependency, logic rõ ràng và adapter đơn giản. Framework có thể giúp khi cần routing, dependency injection, validation, serialization, observability, cấu hình và tích hợp nhiều dịch vụ.

| Cách triển khai | Điểm mạnh | Điều cần cân nhắc |
| --- | --- | --- |
| Java thuần + adapter SDK | Ít abstraction, dễ hiểu vòng đời runtime, kiểm soát dependency | Phải tự tổ chức DI, validation, error mapping và cấu hình |
| Spring Cloud Function | Định nghĩa function bean và adapter cho nhiều loại binding/runtime | Cần hiểu function catalog, binder và chi phí khởi động/context |
| Quarkus | Có hướng tối ưu startup/memory và tích hợp cloud/native | Cần đánh giá extension, native compatibility và build pipeline |
| Micronaut | DI/AOP compile-time, có thể giảm reflection/runtime overhead | Cần kiểm tra tương thích thư viện và cách cấu hình adapter |
| Framework/provider SDK trực tiếp | Tích hợp trigger và context của provider thuận tiện | Tăng coupling; thay provider có thể cần viết adapter mới |

Không có framework tốt nhất cho mọi function. So sánh bằng cold start, warm latency, memory, artifact size, dependency count, khả năng tương thích JDK, độ phức tạp build và mức độ hỗ trợ trigger cần dùng. Một framework giảm thời gian khởi động nhưng tăng độ phức tạp hoặc giới hạn thư viện có thể không phải lựa chọn phù hợp.

## 15. Cold start và tối ưu runtime Java

Cold start là thời gian nền tảng chuẩn bị execution environment mới trước khi function xử lý request. Với Java, phần khởi tạo có thể gồm nạp JVM, class loading, khởi tạo DI container, đọc cấu hình, tạo SDK client và mở kết nối.

Một số biện pháp thường hữu ích:

1. Giảm dependency không cần thiết và tránh kéo toàn bộ framework khi function chỉ cần một handler nhỏ.
2. Không thực hiện truy vấn hoặc gọi service từ static initializer nếu không cần thiết.
3. Tạo client dùng chung an toàn và trì hoãn khởi tạo tài nguyên đắt cho đến khi thực sự cần.
4. Chọn framework và serialization library dựa trên số liệu startup/memory thực tế.
5. Benchmark cả cold và warm invocation với cấu hình memory/CPU gần production.
6. Cân nhắc native image, snapshot hoặc tính năng khởi động nhanh của provider khi có lợi và thư viện tương thích.

Tối ưu cold start không được làm giảm tính đúng đắn. Runtime có thể được tái sử dụng, đóng băng hoặc tạo mới bất kỳ lúc nào; mọi dữ liệu cần tồn tại giữa invocation phải được lưu bền vững. Đừng giữ request-scoped state trong singleton hoặc giả định shutdown hook luôn được gọi.

## 16. Concurrency và thread safety

Một execution environment có thể phục vụ một hoặc nhiều invocation đồng thời tùy runtime, framework và cấu hình. Dù nền tảng thường cô lập một số invocation, vẫn cần giả định object dùng chung có thể bị truy cập đồng thời nếu runtime/framework cho phép.

- Dùng immutable DTO và service stateless khi có thể.
- Không lưu dữ liệu người dùng hiện tại trong field dùng chung.
- Chỉ tái sử dụng client được tài liệu xác nhận thread-safe.
- Dùng connection pool nhỏ; giới hạn tổng concurrency theo khả năng database/downstream.
- Đặt timeout cho mọi I/O và đóng resource bằng try-with-resources.
- Không tạo thread nền để tiếp tục công việc sau khi handler trả về nếu nền tảng không bảo đảm vòng đời thread đó.
- Với tác vụ bất đồng bộ, đưa công việc vào queue/workflow và để invocation khác tiếp tục.

Java `static` không đồng nghĩa với dữ liệu bền vững. Nó chỉ tồn tại trong vòng đời classloader/process tương ứng và có thể mất khi runtime bị thay thế. Cũng không nên coi một runtime cụ thể là singleton của toàn bộ function: nền tảng có thể chạy nhiều instance cùng lúc.

## 17. Quyền truy cập và xác thực theo trigger

Adapter là nơi tiếp xúc với ranh giới bảo mật của nền tảng, nhưng authorization nghiệp vụ vẫn phải được thực hiện trong ứng dụng.

- HTTP adapter xác minh token/identity từ gateway hoặc middleware đáng tin, sau đó truyền principal/tenant đã xác thực vào use case.
- Queue adapter xác minh message đến từ nguồn được phép qua IAM/resource policy; payload không tự chứng minh danh tính producer.
- Event adapter kiểm tra `source`, `type`, schema và chữ ký nếu giao thức yêu cầu.
- Scheduler adapter chỉ chấp nhận schedule/metadata thuộc cấu hình được cấp quyền.
- Mỗi function chỉ có quyền đọc/ghi queue, bucket, bảng hoặc secret cần thiết.

Không tin `tenantId`, `role`, `userId` hoặc quyền hạn nằm trong JSON body nếu chưa được đối chiếu với danh tính xác thực. Không ghi access token, secret, presigned URL hoặc toàn bộ payload nhạy cảm vào log.

## 18. Checklist xây dựng Java function có thể chuyển nền tảng

- [ ] Input/output contract của ứng dụng độc lập với SDK và request class của provider.
- [ ] Business logic được đặt trong use case/service Java thuần và nhận dependency qua constructor/interface.
- [ ] Adapter chỉ làm deserialize, validate giao thức, map context và map response/ACK.
- [ ] HTTP, queue, event và scheduler có adapter/semantics riêng.
- [ ] Context được chuyển thành metadata nội bộ tối thiểu; domain không phụ thuộc provider context.
- [ ] Lỗi nghiệp vụ, lỗi input và lỗi hạ tầng được phân loại và map đúng giao thức.
- [ ] Side effect có idempotency; batch có partial failure khi trigger hỗ trợ.
- [ ] Client/connection pool được quản lý theo lifecycle và thread-safety.
- [ ] Không giữ state nghiệp vụ trong heap/static hoặc thread nền sau khi handler trả về.
- [ ] Entry point, JDK, dependency packaging, memory, timeout và environment được cấu hình đúng provider.
- [ ] IAM/identity theo quyền tối thiểu; tenant và principal đến từ nguồn xác thực.
- [ ] Có unit test cho lõi, adapter test và integration test trên runtime/emulator phù hợp.
- [ ] Đã đo cold start, warm latency, memory, concurrency và chi phí với tải đại diện.

Java thuần giúp giữ logic nghiệp vụ độc lập với nền tảng; adapter chuyển đổi trigger và runtime contract thành lời gọi mà lõi ứng dụng hiểu được. Khi ranh giới này được thiết kế rõ, cùng một use case có thể được gọi từ HTTP, queue hoặc event, được kiểm thử nhanh ở local và triển khai lên nhiều runtime mà không phải viết lại quy tắc nghiệp vụ. Chất lượng của function phụ thuộc cả contract, lifecycle, error semantics, security và cấu hình triển khai, chứ không chỉ vào method xử lý chính.
