# Thiết kế adapter để giảm phụ thuộc nền tảng

Trong chương **Edge và nền tảng mở**, một ứng dụng serverless có thể chạy trên nhiều môi trường: cloud function của nhà cung cấp, nền tảng container, edge runtime hoặc một máy chủ Java truyền thống. Mỗi môi trường có cách nhận request, xác thực, đọc message, lưu dữ liệu, phát event và quản lý vòng đời khác nhau. Nếu logic nghiệp vụ gọi trực tiếp SDK hoặc phụ thuộc vào kiểu event của một nền tảng, việc chuyển môi trường sẽ kéo theo thay đổi ở nhiều lớp.

Adapter tạo một ranh giới chuyển đổi giữa hợp đồng của nền tảng và mô hình ứng dụng. Một adapter nhận dữ liệu từ HTTP, queue hoặc event rồi chuyển thành lệnh nghiệp vụ. Adapter khác triển khai các cổng truy cập dữ liệu, message broker, object storage hoặc dịch vụ bên ngoài. Nhờ vậy, phần nghiệp vụ có thể giữ ổn định khi thay đổi cách triển khai.

Bài học thuộc module **CLOUD_SERVERLESS**, tập trung vào phát triển và triển khai ứng dụng serverless, đặc biệt là Java function kích hoạt bởi HTTP, thông điệp hoặc sự kiện. Người học cần xử lý trigger, trạng thái, quyền truy cập, retry, idempotency, cold start, mở rộng và chi phí để xác định khi nào nên dùng FaaS. Thiết kế adapter tốt phải giữ được các ngữ nghĩa vận hành này, đồng thời giảm phụ thuộc vào API và kiểu dữ liệu riêng của nhà cung cấp.

Các ví dụ Java dùng record, pattern matching cơ bản của thư viện và một số API chuẩn có trong Java 17 trở lên. Khi dùng runtime khác, cần điều chỉnh cú pháp và kiểm tra phiên bản SDK hoặc thư viện của adapter tương ứng.

## 1. Vì sao cần adapter?

Một function thường bắt đầu bằng cách dùng trực tiếp SDK của nền tảng:

- Handler nhận kiểu request do nhà cung cấp định nghĩa.
- Logic nghiệp vụ đọc trực tiếp header, message attribute hoặc event wrapper.
- Use case gọi thẳng SDK database, queue hoặc object storage.
- Cấu hình, secret và danh tính thực thi được truy cập qua API riêng của nhà cung cấp.

Cách làm này có thể nhanh cho một thử nghiệm nhỏ. Nhưng khi hệ thống phát triển, dependency nền tảng lan vào domain và application service. Ví dụ, một quy tắc tạo đơn hàng có thể nhận một lớp request của AWS Lambda, gọi DynamoDB SDK và phát EventBridge event ngay trong cùng method.

Khi chuyển sang một nền tảng khác, nhóm phát triển phải sửa cả handler, logic nghiệp vụ, truy cập dữ liệu, xử lý lỗi và kiểm thử. Thậm chí việc chạy use case trong unit test cũng cần tạo object giả theo SDK của nhà cung cấp.

Adapter giúp cô lập thay đổi:

- Nền tảng có thể thay đổi cách gọi function mà không buộc domain model thay đổi.
- Có thể thay database hoặc message broker bằng một implementation khác.
- Logic nghiệp vụ có thể được kiểm thử bằng fake hoặc in-memory adapter.
- Có thể chạy cùng use case trong Lambda, container hoặc môi trường local.
- Những khác biệt không thể chuẩn hóa vẫn được giữ rõ ở ranh giới adapter.

Adapter không làm cho mọi nền tảng giống nhau. Nó giúp đặt khác biệt vào một nơi có chủ đích và bảo vệ phần nghiệp vụ khỏi các chi tiết không cần biết.

## 2. Ports and Adapters (Hexagonal Architecture)

Một cách tổ chức phổ biến là **Ports and Adapters**, còn gọi là kiến trúc lục giác. Application core định nghĩa các port — những hợp đồng mà nghiệp vụ cần hoặc cung cấp. Adapter kết nối port với công nghệ cụ thể.

- **Inbound port:** hợp đồng để yêu cầu ứng dụng thực hiện một ca sử dụng.
- **Inbound adapter:** nhận trigger từ bên ngoài và gọi inbound port.
- **Outbound port:** hợp đồng mà ứng dụng cần để truy cập dữ liệu hoặc dịch vụ.
- **Outbound adapter:** triển khai outbound port bằng database, queue, API hoặc nền tảng cụ thể.

~~~mermaid
flowchart TB
    subgraph IN["Inbound adapters"]
      HTTP["HTTP / API Gateway"]
      QUEUE["Queue / Event adapter"]
      EDGE["Edge request adapter"]
    end

    subgraph CORE["Application core"]
      USE["Use cases"]
      DOMAIN["Domain model"]
      PORTIN["Inbound ports"]
      PORTOUT["Outbound ports"]
    end

    subgraph OUT["Outbound adapters"]
      DB["Database adapter"]
      BUS["Message broker adapter"]
      OBJ["Object storage adapter"]
      EXT["External API adapter"]
    end

    HTTP --> PORTIN
    QUEUE --> PORTIN
    EDGE --> PORTIN
    PORTIN --> USE
    USE --> DOMAIN
    USE --> PORTOUT
    PORTOUT --> DB
    PORTOUT --> BUS
    PORTOUT --> OBJ
    PORTOUT --> EXT
~~~

Điểm quan trọng là dependency hướng vào application core. Domain và use case không import SDK của cloud provider. Adapter biết cả hợp đồng nội bộ lẫn API nền tảng để chuyển đổi ở ranh giới.

### 2.1. Tận dụng chuẩn mở ở ranh giới

Chuẩn mở giúp giảm số hợp đồng riêng phải tự định nghĩa, nhưng không tự làm các dịch vụ tương đương nhau:

- **HTTP và OpenAPI** mô tả giao tiếp request/response và schema API.
- **CloudEvents** chuẩn hóa context của event như id, source, type và time; payload nghiệp vụ vẫn do ứng dụng định nghĩa.
- **OpenTelemetry** cung cấp API và định dạng trace context để liên kết hoạt động qua nhiều dịch vụ.
- **OCI container image** chuẩn hóa định dạng image; runtime, quyền và giới hạn của nền tảng vẫn có thể khác nhau.
- **JDBC** tạo abstraction cho thao tác SQL, nhưng không xóa khác biệt về transaction isolation, dialect, quota hoặc connection behavior giữa database.

Hãy dùng chuẩn mở ở nơi chúng giải quyết đúng vấn đề. Ví dụ, CloudEvents có thể làm envelope chung cho adapter queue và event bus, còn adapter vẫn phải giữ semantics ACK, ordering và retry của từng nguồn.

## 3. Nguyên tắc thiết kế adapter

### 3.1. Đặt hợp đồng theo ngôn ngữ nghiệp vụ

Port nên mô tả điều ứng dụng cần làm, không nên phản chiếu API của nhà cung cấp.

Ví dụ, một port nghiệp vụ có thể là:

- Lưu đơn hàng đã được xác nhận.
- Tra cứu trạng thái thanh toán.
- Phát thông báo đơn hàng đã tạo.
- Lưu file chứng từ.
- Kiểm tra một idempotency key đã được xử lý chưa.

Không nên đặt tên port như AwsDynamoClientWrapper hoặc GcpPubSubFacade nếu mục tiêu là giữ application core độc lập. Tên port nên thể hiện trách nhiệm, ví dụ OrderRepository, EventPublisher hoặc DocumentStore.

### 3.2. Adapter chỉ chuyển đổi và điều phối giao thức

Inbound adapter nên:

1. Nhận cấu trúc trigger.
2. Xác thực giao thức và lấy metadata cần thiết.
3. Deserialize và validate đầu vào.
4. Chuyển thành command hoặc application event.
5. Gọi use case.
6. Ánh xạ kết quả hoặc lỗi thành response phù hợp với nền tảng.

Adapter không nên chứa quy tắc như tính phí vận chuyển, xác định đơn có đủ điều kiện thanh toán hay quyết định trạng thái đơn. Những quy tắc đó thuộc application/domain core.

### 3.3. Không để kiểu SDK rò rỉ qua port

Nếu một interface trong application core nhận AWS Lambda Context, SQSMessage hoặc DynamoDB AttributeValue, core vẫn phụ thuộc AWS dù đã có interface.

Port nên dùng kiểu Java hoặc kiểu nghiệp vụ do ứng dụng sở hữu. Adapter chịu trách nhiệm chuyển kiểu provider-specific sang kiểu nội bộ.

### 3.4. Không trừu tượng hóa quá mức

Không cần tạo một interface chung cho mọi dịch vụ cloud nếu các dịch vụ có ngữ nghĩa khác nhau. Queue, stream, object storage và database không có cùng cách xử lý lỗi, thứ tự hoặc trạng thái.

Hãy trừu tượng hóa những hành vi mà ứng dụng thực sự cần. Nếu một use case cần transaction quan hệ, một interface KeyValueStore chung có thể làm mất những bảo đảm quan trọng. Nếu ứng dụng cần partition ordering, một port chỉ có phương thức send(message) là chưa đủ.

## 4. Phân biệt các lớp trong Java

Một cấu trúc dự án có thể tổ chức theo trách nhiệm:

~~~text
src/main/java/com/example/orders/
├── domain/
│   ├── Order.java
│   ├── OrderStatus.java
│   └── OrderPlaced.java
├── application/
│   ├── port/
│   │   ├── in/
│   │   │   └── PlaceOrderUseCase.java
│   │   └── out/
│   │       ├── OrderStore.java
│   │       ├── IdempotencyStore.java
│   │       └── EventPublisher.java
│   └── service/
│       └── PlaceOrderService.java
├── adapter/
│   ├── in/
│   │   ├── http/
│   │   ├── queue/
│   │   └── event/
│   └── out/
│       ├── postgres/
│       ├── dynamodb/
│       ├── pubsub/
│       └── objectstorage/
└── bootstrap/
    └── ApplicationComposition.java
~~~

Tên package là ví dụ. Một dự án nhỏ có thể dùng ít thư mục hơn, nhưng vẫn nên giữ nguyên tắc: domain không phụ thuộc adapter; application định nghĩa port; adapter triển khai port; bootstrap kết nối các thành phần.

Không nên tạo package theo tên nhà cung cấp ở cấp domain. Các package như adapter.out.aws hoặc adapter.in.lambda là nơi phù hợp để chứa code phụ thuộc AWS.

## 5. Xây dựng inbound port và use case

Giả sử ứng dụng cần tạo đơn hàng. Inbound port mô tả hành động mà các adapter có thể yêu cầu:

~~~java
import java.util.List;

public interface PlaceOrderUseCase {
    OrderResult place(PlaceOrderCommand command);
}

public record PlaceOrderCommand(
        String customerId,
        List<OrderLineInput> lines,
        String idempotencyKey) {
}

public record OrderLineInput(
        String productId,
        int quantity) {
}

public record OrderResult(
        String orderId,
        String status) {
}
~~~

Đây là hợp đồng của application core. Nó không biết request đến từ API Gateway, HTTP server, queue hay một bài kiểm thử.

Domain model có thể định nghĩa các quy tắc riêng:

~~~java
import java.util.List;

public record Order(
        String id,
        String customerId,
        List<OrderLineInput> lines,
        OrderStatus status) {

    public static Order create(
            String id,
            String customerId,
            List<OrderLineInput> lines) {

        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException("customerId is required");
        }

        if (lines == null || lines.isEmpty()) {
            throw new IllegalArgumentException("order must contain lines");
        }

        if (lines.stream().anyMatch(line -> line.quantity() <= 0)) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        return new Order(id, customerId, List.copyOf(lines),
                OrderStatus.PENDING);
    }
}

public enum OrderStatus {
    PENDING,
    CONFIRMED,
    CANCELLED
}
~~~

Các quy tắc ở ví dụ chỉ là phần tối thiểu. Trong ứng dụng thật, domain có thể dùng value object cho ID, tiền tệ và số lượng, đồng thời kiểm tra những bất biến nghiệp vụ đầy đủ hơn.

## 6. Định nghĩa outbound port theo nhu cầu nghiệp vụ

Application core cần một nơi lưu đơn và một nơi lưu ý định phát event. Có thể định nghĩa:

~~~java
import java.util.Optional;

public interface OrderStore {
    Optional<OrderResult> findByIdempotencyKey(String key);

    void saveOnce(
            String idempotencyKey,
            Order order,
            OrderPlaced event);
}

public interface EventPublisher {
    void publish(OrderPlaced event);
}

public record OrderPlaced(
        String eventId,
        String orderId,
        String customerId) {
}
~~~

Tên saveOnce diễn đạt một hợp đồng quan trọng: cùng idempotency key không được tạo thêm một đơn mới. Implementation phải bảo đảm điều đó bằng unique constraint hoặc cơ chế lưu trữ nguyên tử, không chỉ kiểm tra trong bộ nhớ.

Trong production, việc ghi đơn và ghi ý định phát event cần được phối hợp an toàn. Nếu database commit thành công nhưng publish event thất bại, các service khác không biết đơn đã được tạo. Có thể triển khai OrderStore bằng transaction ghi cả đơn và transactional outbox; một publisher riêng đọc outbox rồi phát event. Port giữ hợp đồng nghiệp vụ ổn định, còn adapter quyết định cách thực hiện trên database cụ thể.

## 7. Use case không phụ thuộc cloud SDK

Use case điều phối nghiệp vụ thông qua port:

~~~java
import java.util.UUID;

public final class PlaceOrderService implements PlaceOrderUseCase {
    private final OrderStore orderStore;

    public PlaceOrderService(OrderStore orderStore) {
        this.orderStore = orderStore;
    }

    @Override
    public OrderResult place(PlaceOrderCommand command) {
        var previous = orderStore.findByIdempotencyKey(
                command.idempotencyKey());

        if (previous.isPresent()) {
            return previous.get();
        }

        String orderId = UUID.randomUUID().toString();

        Order order = Order.create(
                orderId,
                command.customerId(),
                command.lines());

        OrderPlaced event = new OrderPlaced(
                UUID.randomUUID().toString(),
                order.id(),
                order.customerId());

        orderStore.saveOnce(
                command.idempotencyKey(),
                order,
                event);

        return new OrderResult(order.id(), order.status().name());
    }
}
~~~

Use case chỉ biết OrderStore. Nó không biết dữ liệu được lưu ở PostgreSQL, DynamoDB hay một dịch vụ dữ liệu khác. Nó cũng không biết event được gửi qua EventBridge, Pub/Sub, Kafka hay một broker nội bộ.

Ví dụ rút gọn có bước đọc idempotency trước khi lưu; trong hệ thống đồng thời, thao tác kiểm tra và tạo đơn phải được bảo vệ nguyên tử ở implementation của OrderStore. Không dựa vào lần đọc trước để ngăn hai invocation chạy song song cùng key.

## 8. Inbound adapter cho HTTP

HTTP adapter chuyển request từ nền tảng thành command. Ví dụ, phần controller trung lập với nhà cung cấp có thể nhận kiểu nội bộ:

~~~java
public record HttpInput(
        String body,
        String idempotencyKey,
        String requestId) {
}

public record HttpOutput(
        int statusCode,
        String contentType,
        String body) {
}
~~~

Adapter HTTP:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.core.JsonProcessingException;

public final class PlaceOrderHttpAdapter {
    private final ObjectMapper mapper;
    private final PlaceOrderUseCase useCase;

    public PlaceOrderHttpAdapter(
            ObjectMapper mapper,
            PlaceOrderUseCase useCase) {
        this.mapper = mapper;
        this.useCase = useCase;
    }

    public HttpOutput handle(HttpInput input) {
        PlaceOrderRequest request;
        try {
            request = mapper.readValue(
                    input.body(), PlaceOrderRequest.class);
        } catch (JsonProcessingException invalidJson) {
            return new HttpOutput(
                    400,
                    "application/json",
                    "{\"error\":\"invalid_json\"}");
        } catch (IllegalArgumentException invalidRequest) {
            return new HttpOutput(
                    400,
                    "application/json",
                    "{\"error\":\"invalid_request\"}");
        }

        try {
            PlaceOrderCommand command = new PlaceOrderCommand(
                    request.customerId(),
                    request.lines(),
                    input.idempotencyKey());

            OrderResult result = useCase.place(command);

            return new HttpOutput(
                    202,
                    "application/json",
                    mapper.writeValueAsString(result));
        } catch (Exception failure) {
            return new HttpOutput(
                    500,
                    "application/json",
                    "{\"error\":\"internal_error\"}");
        }
    }
}

public record PlaceOrderRequest(
        String customerId,
        java.util.List<OrderLineInput> lines) {
}
~~~

Adapter không trả stack trace hoặc nội dung exception cho client. Trong production, cần phân loại lỗi nghiệp vụ, lỗi parse và lỗi tạm thời; không gom mọi exception thành 500 nếu có thể trả mã phù hợp hơn.

Một adapter cụ thể của API Gateway sẽ nhận class event của AWS, đọc body/header/request ID rồi tạo HttpInput. Một adapter trên Cloud Run hoặc một Java HTTP server có thể nhận request framework tương ứng rồi tạo cùng HttpInput. Use case không cần thay đổi.

Ví dụ wrapper AWS Lambda cho API Gateway proxy event:

~~~java
import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;
import com.amazonaws.services.lambda.runtime.events.APIGatewayProxyRequestEvent;
import com.amazonaws.services.lambda.runtime.events.APIGatewayProxyResponseEvent;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.Map;

public final class ApiGatewayPlaceOrderHandler implements
        RequestHandler<APIGatewayProxyRequestEvent,
                       APIGatewayProxyResponseEvent> {

    private final PlaceOrderHttpAdapter adapter =
            ApplicationComposition.placeOrderHttpAdapter();

    @Override
    public APIGatewayProxyResponseEvent handleRequest(
            APIGatewayProxyRequestEvent event,
            Context context) {

        String idempotencyKey = header(
                event.getHeaders(), "Idempotency-Key");

        String body = Boolean.TRUE.equals(event.getIsBase64Encoded())
                ? new String(Base64.getDecoder().decode(event.getBody()),
                        StandardCharsets.UTF_8)
                : event.getBody();

        HttpOutput output = adapter.handle(new HttpInput(
                body,
                idempotencyKey,
                context.getAwsRequestId()));

        return new APIGatewayProxyResponseEvent()
                .withStatusCode(output.statusCode())
                .withHeaders(Map.of(
                        "Content-Type", output.contentType()))
                .withBody(output.body());
    }

    private static String header(
            Map<String, String> headers,
            String expectedName) {
        if (headers == null) {
            return null;
        }

        return headers.entrySet().stream()
                .filter(entry -> entry.getKey() != null
                        && entry.getKey().equalsIgnoreCase(expectedName))
                .map(Map.Entry::getValue)
                .findFirst()
                .orElse(null);
    }
}
~~~

Đây là lớp phụ thuộc AWS: nó biết kiểu API Gateway event và Lambda Context. Nó chuyển dữ liệu sang HttpInput rồi ủy quyền cho adapter HTTP trung lập. Với nền tảng khác, thay wrapper này bằng một entry point tương ứng; PlaceOrderHttpAdapter và use case vẫn dùng cùng hợp đồng nội bộ. Trong production, cần xử lý trường hợp body được mã hóa Base64 theo cấu hình API Gateway và chuẩn hóa header nhiều giá trị nếu hợp đồng cần.

## 9. Inbound adapter cho queue và event

Queue trigger thường đưa cho function một wrapper chứa nhiều record. Adapter cần chuyển từng record sang mô hình nội bộ và tuân thủ cơ chế acknowledgement của nền tảng.

Ví dụ hợp đồng nội bộ:

~~~java
public record IncomingMessage(
        String messageId,
        String eventType,
        String body,
        int deliveryAttempt,
        String correlationId) {
}

public interface OrderMessageHandler {
    void handle(OrderPlaced event);
}
~~~

Adapter xử lý:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;

public final class OrderPlacedMessageAdapter {
    private final ObjectMapper mapper;
    private final OrderMessageHandler handler;

    public OrderPlacedMessageAdapter(
            ObjectMapper mapper,
            OrderMessageHandler handler) {
        this.mapper = mapper;
        this.handler = handler;
    }

    public void handle(IncomingMessage message) throws Exception {
        if (!"com.example.orders.order-placed".equals(
                message.eventType())) {
            throw new UnsupportedOperationException(
                    "Unsupported event type");
        }

        OrderPlaced event = mapper.readValue(
                message.body(), OrderPlaced.class);

        handler.handle(event);
    }
}
~~~

Adapter này không trực tiếp xác nhận message. Lớp tích hợp với nền tảng sẽ quyết định khi nào ACK, delete, commit offset hoặc trả partial batch failure. Việc tách như vậy giúp application handler giữ cùng hợp đồng, trong khi adapter nền tảng vẫn thể hiện đúng ngữ nghĩa giao nhận.

Không được coi ACK của mọi queue là giống nhau. Có nguồn xóa message sau ACK; có nguồn dùng visibility timeout; stream dùng offset/checkpoint; một số trigger yêu cầu function trả danh sách record lỗi. Những khác biệt này cần được giữ trong adapter chuyên biệt.

## 10. Outbound adapter cho database và broker

Một outbound adapter triển khai port bằng công nghệ cụ thể. Ví dụ, PostgreSQL adapter có thể dùng JDBC:

~~~java
import javax.sql.DataSource;

public final class PostgresOrderStore implements OrderStore {
    private final DataSource dataSource;

    public PostgresOrderStore(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    @Override
    public java.util.Optional<OrderResult> findByIdempotencyKey(
            String key) {
        // Query bảng idempotency bằng PreparedStatement.
        // Trả kết quả đã lưu nếu key tồn tại.
        return java.util.Optional.empty();
    }

    @Override
    public void saveOnce(
            String key,
            Order order,
            OrderPlaced event) {
        // Một transaction:
        // 1. Ghi idempotency key với unique constraint.
        // 2. Ghi order.
        // 3. Ghi event vào transactional outbox.
        // Commit tất cả hoặc rollback tất cả.
    }
}
~~~

Đây là skeleton để thể hiện ranh giới; phần SQL, xử lý unique conflict và transaction phải được triển khai theo schema thật. Nếu thay PostgreSQL bằng một database khác, chỉ adapter và cấu hình composition root cần thay đổi nếu hợp đồng port vẫn đáp ứng được các bảo đảm mà use case cần.

Tương tự, EventPublisher có thể được triển khai bằng một broker cụ thể. Adapter chịu trách nhiệm serialize event, gắn metadata, xác thực và gửi message. Application core chỉ yêu cầu phát một sự kiện nghiệp vụ.

## 11. Composition root: nơi lắp ghép adapter

Các interface chỉ hữu ích khi có một nơi tạo implementation và nối chúng lại. Composition root là điểm khởi tạo object graph:

~~~java
public final class ApplicationComposition {
    private ApplicationComposition() {
    }

    public static PlaceOrderUseCase placeOrderUseCase() {
        javax.sql.DataSource dataSource =
                DatabaseFactory.createDataSource();

        OrderStore orderStore =
                new PostgresOrderStore(dataSource);

        return new PlaceOrderService(orderStore);
    }
}
~~~

Ví dụ trên chọn PostgreSQL adapter. Trong môi trường khác, composition root có thể chọn adapter khác dựa trên dependency injection hoặc cấu hình triển khai.

Với Java Lambda, có thể khởi tạo object graph một lần cho mỗi execution environment để giảm chi phí init. Các client bất biến và thread-safe có thể được tái sử dụng. Không giữ trạng thái nghiệp vụ của request trong static field; các invocation có thể chạy song song hoặc environment có thể bị thay thế bất cứ lúc nào.

Composition root là nơi hợp lý để đọc cấu hình, tạo client, chọn adapter và inject dependency. Domain model không nên tự đọc environment variable hoặc tự khởi tạo SDK.

## 12. Adapter cho edge runtime

Edge platform thường đặt function gần người dùng hoặc thiết bị để giảm độ trễ và xử lý một số quyết định tại biên mạng. Nhưng runtime, ngôn ngữ, giới hạn tài nguyên và khả năng kết nối khác nhau đáng kể giữa các nền tảng.

Adapter ở edge có thể thực hiện:

- Chuẩn hóa HTTP request và header.
- Xác thực token hoặc kiểm tra policy đơn giản.
- Định tuyến theo host, path hoặc tenant.
- Kiểm tra cache và quyết định có gọi origin không.
- Chuẩn hóa lỗi và response.
- Chuyển request sang một API backend có hợp đồng ổn định.

Không nên đưa toàn bộ nghiệp vụ phụ thuộc database vào edge nếu runtime không có kết nối ổn định hoặc không hỗ trợ driver cần thiết. Có thể giữ logic nhạy độ trễ, ít trạng thái tại edge và chuyển các thao tác cần transaction đến backend.

### 12.1. Giới hạn runtime

Không phải mọi edge platform đều hỗ trợ JVM hoặc Java runtime đầy đủ. Một số nền tảng chỉ chạy JavaScript, WebAssembly hoặc runtime được giới hạn. Vì vậy, adapter giúp tách hợp đồng nhưng không tự làm bytecode Java chạy được trên bất kỳ edge runtime nào.

Các lựa chọn có thể gồm:

- Chạy Java ở cloud function/container và dùng edge adapter nhẹ để định tuyến.
- Biên dịch Java thành native executable nếu nền tảng cho phép và thư viện tương thích.
- Dùng WebAssembly khi toolchain, runtime và API hệ thống hỗ trợ đầy đủ.
- Đặt một gateway nhỏ ở edge, còn use case chính ở backend.

GraalVM Native Image có thể giảm thời gian khởi động và footprint trong một số môi trường, nhưng cần cấu hình reflection, resource, proxy và native library. Không phải mọi thư viện Java đều hoạt động ngay khi biên dịch native. Phải kiểm thử artifact trên runtime đích.

### 12.2. Tính locality và dữ liệu

Edge có thể giảm round-trip tới người dùng nhưng dữ liệu chính có thể nằm ở region trung tâm. Nếu mỗi request edge đều phải gọi database ở xa, lợi ích latency có thể biến mất.

Hãy xác định rõ dữ liệu nào được cache, TTL, cách invalidation và cách xử lý khi edge mất kết nối. Không lưu trạng thái nghiệp vụ duy nhất trong memory của edge instance vì instance có thể bị thay thế và các request có thể đến nhiều location.

Nếu cho phép cập nhật dữ liệu tại edge khi offline, cần có mô hình đồng bộ, conflict resolution và định danh thao tác. Đây là quyết định nghiệp vụ và dữ liệu, không chỉ là chi tiết adapter.

## 13. Giữ ngữ nghĩa trigger khi chuyển nền tảng

Một adapter có thể chuẩn hóa tên method nhưng không được làm mất ngữ nghĩa của nguồn.

### 13.1. HTTP

Cần giữ:

- Method, path, query và header có ý nghĩa.
- Mã trạng thái HTTP.
- Timeout và giới hạn payload.
- Xác thực caller và quyền trên resource.
- Quy tắc retry của client hoặc gateway.
- Streaming, binary body hoặc multi-value header nếu nghiệp vụ cần.

Không nên biến mọi request thành một lệnh chung chung mà bỏ method hoặc status semantics. Một GET không nên vô tình có side effect chỉ vì adapter gọi cùng một method với POST.

### 13.2. Queue và stream

Cần giữ:

- Message ID hoặc event ID.
- Delivery attempt và visibility/lease nếu có.
- ACK/delete hoặc offset/checkpoint.
- Partial batch failure.
- Ordering, partition key và consumer group.
- Retry, dead-letter và replay.
- Correlation/trace context.

Nếu một adapter pull stream nhưng nền tảng khác push batch, cả hai vẫn có thể gọi cùng use case; tuy nhiên, adapter cần bảo đảm checkpoint chỉ tiến khi xử lý thành công theo đúng quy tắc nguồn.

### 13.3. Scheduled trigger

Scheduler có thể có timezone, lịch chạy trùng, retry và semantics khác nhau. Adapter nên chuyển trigger thành một command nội bộ có định danh lần chạy, thời điểm dự kiến và phạm vi dữ liệu cần xử lý.

Không giả định một lịch chỉ kích hoạt đúng một lần. Cần idempotency hoặc khóa công việc nếu hai invocation có thể chạy chồng lấn.

## 14. Trạng thái, idempotency và retry nằm ở đâu?

Adapter có trách nhiệm chuyển tiếp metadata và phản hồi đúng giao thức. Application core chịu trách nhiệm quy tắc nghiệp vụ và tính idempotent. Infrastructure adapter thực hiện lưu trữ, lock hoặc deduplication theo khả năng của nền tảng.

Ví dụ, một message có thể được giao lại vì function timeout sau khi database đã commit. Nếu adapter chỉ nhìn exception và retry toàn bộ, nghiệp vụ có thể bị thực hiện hai lần. Do đó:

- Giữ message/event ID hoặc idempotency key khi chuyển vào command.
- Lưu kết quả xử lý trong kho bền vững.
- Dùng unique constraint hoặc transaction để chống race.
- Chỉ ACK khi kết quả đã được lưu bền vững.
- Phân biệt lỗi tạm thời với lỗi không thể khắc phục.
- Dùng outbox khi cần đồng bộ ghi dữ liệu và phát event.

Không để adapter che giấu mọi lỗi bằng cách trả success. Nếu nguồn hiểu 2xx là đã xử lý xong, trả 2xx trước khi ghi trạng thái bền vững có thể làm mất message.

## 15. Bảo mật và danh tính theo adapter

Mỗi nền tảng có cách xác thực khác nhau: IAM role, service account, workload identity, token, mTLS hoặc API key. Application core không nên chứa logic lấy credential từ nhà cung cấp.

Adapter và bootstrap chịu trách nhiệm:

- Lấy danh tính thực thi từ môi trường.
- Tạo client với credential provider phù hợp.
- Xác thực nguồn phát của HTTP hoặc message.
- Cấp quyền tối thiểu cho database, queue và object storage.
- Truyền principal hoặc security context đã chuẩn hóa khi use case cần kiểm tra quyền.
- Không đưa secret vào command, event hoặc log.
- Làm mới token và xử lý credential hết hạn.

Không nên tạo một interface AuthProvider quá chung nếu các nền tảng có semantics khác nhau. Có thể dùng port cho nhu cầu nghiệp vụ như AuthorizationService hoặc TenantAccessPolicy, còn adapter cụ thể xác thực caller và chuyển thành một principal nội bộ.

Việc chuẩn hóa principal không được làm mất thông tin cần thiết như tenant, issuer, subject hoặc scope. Nếu ứng dụng dựa vào một claim để phân quyền, adapter phải xác minh claim đó từ nguồn tin cậy trước khi chuyển vào core.

## 16. Cấu hình và secret

Không hardcode endpoint, bucket, topic, database URL hoặc secret trong use case. Có thể định nghĩa cấu hình nội bộ theo ý nghĩa:

~~~java
public record OrderApplicationConfig(
        String eventDestination,
        int maxBatchSize,
        java.time.Duration operationTimeout) {
}
~~~

Bootstrap đọc cấu hình từ environment, file hoặc secret manager của nền tảng rồi tạo config object. Application core nhận cấu hình cần thiết qua constructor.

Tuy nhiên, không phải mọi cấu hình nên được trừu tượng hóa. Region, ARN, IAM role, edge location hoặc queue visibility timeout có thể là cấu hình triển khai đặc thù. Giữ chúng trong deployment layer hoặc adapter configuration để không làm core phụ thuộc.

Secret nên được lấy từ secret manager hoặc workload identity của môi trường. Tránh đọc secret ở mỗi thao tác nếu SDK có cơ chế cache an toàn; đồng thời phải tôn trọng rotation và thời hạn token.

## 17. Quan sát và correlation xuyên adapter

Adapter là nơi phù hợp để gắn metadata vận hành vào log và trace:

- Request ID của nền tảng.
- Event/message ID.
- Correlation ID của nghiệp vụ.
- Trace context.
- Tên adapter hoặc transport.
- Delivery attempt.
- Function version hoặc deployment revision.

Không đưa tất cả metadata vào domain object nếu use case không cần. Có thể truyền một ExecutionContext nội bộ nhỏ cho mục đích quan sát và bảo mật, nhưng không nên biến nó thành túi chứa mọi thông tin của SDK.

Ví dụ:

~~~java
public record ExecutionContext(
        String requestId,
        String correlationId,
        String traceId,
        String tenantId) {
}

public interface ContextAwarePlaceOrderUseCase {
    OrderResult place(
            PlaceOrderCommand command,
            ExecutionContext context);
}
~~~

Đây là biến thể của inbound port khi use case thật sự cần context. Nếu context chỉ phục vụ log và trace, nên giữ nó trong adapter hoặc tracing scope để tránh làm mọi use case phải nhận thêm tham số vận hành.

Nếu application core không cần context để quyết định nghiệp vụ, có thể ghi context ở adapter và truyền vào tracing/logging scope. Nếu tenantId ảnh hưởng đến quyền truy cập hoặc phạm vi dữ liệu, cần đưa nó qua một kiểu có ý nghĩa và xác thực nguồn gốc.

## 18. Thiết kế adapter không đồng nghĩa với lowest common denominator

Một rủi ro là tạo interface quá đơn giản để mọi provider đều triển khai được, rồi đánh mất các tính năng quan trọng.

Ví dụ, một port MessageQueue chỉ có send và receive có thể không biểu diễn được:

- FIFO hoặc ordering key.
- Visibility timeout và lease extension.
- Batch acknowledgement.
- Offset commit.
- Delayed delivery.
- Dead-letter policy.
- Transactional publish.

Có ba cách xử lý:

1. **Port theo năng lực nghiệp vụ:** chỉ đưa vào hợp đồng các bảo đảm mà use case thật sự cần.
2. **Capability interface:** tách một khả năng tùy chọn, ví dụ OrderedMessagePublisher hoặc BatchAcknowledger, khi một số adapter hỗ trợ.
3. **Provider-specific adapter:** giữ tính năng đặc thù trong adapter hoặc use case triển khai riêng nếu nghiệp vụ phụ thuộc trực tiếp vào tính năng đó.

Không nên che giấu khác biệt bằng cách giả vờ mọi adapter đều cung cấp exactly-once, transaction phân tán hoặc thứ tự toàn cục. Nếu nền tảng không hỗ trợ một bảo đảm, phải thể hiện rõ trong hợp đồng hoặc tài liệu triển khai.

## 19. Kiểm thử adapter và tính thay thế

Một port chỉ thật sự hữu ích khi các implementation có thể được kiểm tra theo cùng một hợp đồng.

### 19.1. Unit test cho application core

Dùng fake adapter để kiểm tra use case mà không cần cloud SDK:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

public final class InMemoryOrderStore implements OrderStore {
    private final Map<String, OrderResult> results = new HashMap<>();

    @Override
    public Optional<OrderResult> findByIdempotencyKey(String key) {
        return Optional.ofNullable(results.get(key));
    }

    @Override
    public void saveOnce(
            String key,
            Order order,
            OrderPlaced event) {
        if (results.containsKey(key)) {
            throw new IllegalStateException("Duplicate key");
        }

        results.put(
                key,
                new OrderResult(order.id(), order.status().name()));
    }
}
~~~

Fake trên phù hợp unit test đơn luồng. Nó không mô phỏng transaction, concurrency hoặc outbox thật; không dùng nó để kết luận adapter production an toàn khi có nhiều invocation đồng thời.

### 19.2. Contract test cho outbound adapter

Chạy cùng bộ test đối với từng implementation của port:

- Lưu đơn và đọc lại cho kết quả đúng.
- Idempotency key lặp không tạo đơn thứ hai.
- Lỗi kết nối được chuyển thành lỗi có thể phân loại.
- Transaction rollback không để lại trạng thái nửa chừng.
- Event/outbox được ghi cùng transaction theo hợp đồng.
- Dữ liệu và encoding giữ nguyên khi serialize.

Với database adapter, có thể dùng database test hoặc container phù hợp. Với broker adapter, cần kiểm tra ACK, retry và ordering theo cấu hình thực tế.

### 19.3. Integration test cho inbound adapter

Kiểm tra adapter với event mẫu hoặc runtime emulator:

- HTTP status và response body.
- Header xác thực và idempotency.
- Queue batch và partial failure.
- Event type không hỗ trợ.
- Payload sai schema.
- Request timeout và giới hạn kích thước.
- Trace/correlation context được giữ qua mapping.

Một adapter giả lập thành công không chứng minh deployment role, network, trigger mapping hoặc permission đã đúng. Cần có smoke test trên môi trường triển khai đại diện.

### 19.4. Architecture test

Có thể dùng ArchUnit hoặc kiểm tra dependency trong build để bảo đảm package domain/application không phụ thuộc package adapter hoặc SDK provider. Ví dụ, dependency hướng vào core cần được giữ nhất quán qua các lần refactor.

## 20. Chiến lược chuyển đổi sang nền tảng khác

Khi chuyển từ một cloud provider sang nền tảng khác, không nên bắt đầu bằng việc thay mọi SDK cùng lúc. Có thể tiến hành theo từng ranh giới:

1. Liệt kê dependency nền tảng trong handler, use case và domain.
2. Xác định các ca sử dụng và hợp đồng nội bộ cần giữ.
3. Tạo inbound port cho từng use case đang bị gọi trực tiếp từ handler.
4. Chuyển logic nghiệp vụ ra khỏi provider-specific handler.
5. Tạo outbound port cho database, queue và external API có khả năng thay đổi.
6. Đóng gói implementation hiện tại thành adapter mà không thay hành vi.
7. Viết contract test để cố định semantics hiện tại.
8. Triển khai adapter mới cho nền tảng đích.
9. Chạy cùng bộ test và so sánh kết quả, latency, retry và chi phí.
10. Chuyển traffic hoặc workload theo từng bước, có quan sát và rollback.

Nếu nền tảng mới không có cùng bảo đảm, ví dụ không hỗ trợ partial batch failure hoặc transaction tương đương, cần thiết kế bù trừ hoặc thay đổi workflow. Không nên chỉ đổi adapter rồi giả định hành vi hệ thống không thay đổi.

## 21. Những lỗi thiết kế thường gặp

**Đặt SDK trong domain:** Domain import kiểu của nhà cung cấp nên không thể kiểm thử hoặc chạy độc lập. Chuyển SDK vào adapter và dùng kiểu nội bộ ở port.

**Chỉ đổi tên SDK thành interface:** Interface vẫn nhận hoặc trả kiểu provider-specific nên dependency chưa được cô lập. Thiết kế hợp đồng theo nhu cầu nghiệp vụ.

**Để adapter chứa quy tắc nghiệp vụ:** Khi có hai trigger, logic bị sao chép và có thể xử lý khác nhau. Chuyển quy tắc vào use case hoặc domain service.

**Một adapter chung cho mọi transport:** HTTP, queue và stream có semantics khác nhau về response, ACK, ordering và retry. Tạo adapter riêng rồi dùng chung application port khi phù hợp.

**Ẩn khác biệt bằng lowest common denominator:** Hợp đồng quá nghèo khiến mất transaction, ordering hoặc batch failure. Mô hình hóa capability cần thiết và ghi rõ giới hạn.

**Dùng static mutable state để chia sẻ trạng thái giữa invocation:** Execution environment có thể bị thay thế hoặc chạy đồng thời. Lưu trạng thái nghiệp vụ trong kho bền vững.

**Cho rằng adapter bảo đảm portability hoàn toàn:** Runtime, IAM, network, quota và dịch vụ dữ liệu vẫn khác nhau. Kiểm thử trên nền tảng đích và tài liệu hóa capability.

**Không quản lý version của event contract:** Hai adapter có thể serialize cùng event theo cách khác nhau. Chuẩn hóa schema, type, time, null và version.

**Không kiểm thử semantics của retry:** Adapter mới có thể ACK sớm hoặc retry khác nguồn cũ. Kiểm thử message lặp, timeout và kết quả không rõ.

**Tạo quá nhiều lớp không có ranh giới thực:** Mỗi class chỉ chuyển tiếp một lời gọi mà không thêm hợp đồng hoặc chuyển đổi. Chỉ tạo adapter/port khi có một ranh giới cần cô lập hoặc kiểm thử.

## 22. Checklist trước khi triển khai

- [ ] Domain và use case không import SDK hoặc kiểu event của nhà cung cấp.
- [ ] Inbound adapter chuyển HTTP/message/event thành command hoặc application event rõ ràng.
- [ ] Outbound port mô tả nhu cầu nghiệp vụ, không phản chiếu API provider.
- [ ] Outbound adapter triển khai port bằng công nghệ cụ thể.
- [ ] Composition root chịu trách nhiệm tạo và inject implementation.
- [ ] Handler không chứa quy tắc nghiệp vụ ngoài validation giao thức.
- [ ] DTO nội bộ không làm mất event ID, correlation ID hoặc metadata cần thiết.
- [ ] ACK, delete, offset và partial batch failure tuân đúng semantics của nguồn.
- [ ] Retry, idempotency, transaction và outbox được thiết kế rõ.
- [ ] Trạng thái nghiệp vụ được lưu bền vững, không dựa vào memory của instance.
- [ ] Quyền IAM/service account và secret được cấp ở adapter/bootstrap với nguyên tắc tối thiểu.
- [ ] Timeout, concurrency, cold start và giới hạn payload của nền tảng được tính đến.
- [ ] Edge adapter không phụ thuộc runtime hoặc API không được nền tảng hỗ trợ.
- [ ] Capability đặc thù không bị che giấu dưới một interface quá chung.
- [ ] Có unit test cho core, contract test cho adapter và integration test cho trigger.
- [ ] Có log, metric và trace để theo dõi qua các ranh giới.
- [ ] Đã đánh giá chi phí và khả năng rollback khi thay adapter hoặc nền tảng.

## Kết luận

Adapter tạo ranh giới giữa nền tảng và ứng dụng. Inbound adapter chuyển trigger thành yêu cầu nghiệp vụ; outbound adapter triển khai các port mà use case cần để lưu dữ liệu, phát event hoặc gọi dịch vụ khác. Domain và application core giữ hợp đồng ổn định, còn chi tiết về SDK, event wrapper, xác thực, ACK, checkpoint và triển khai nằm ở adapter hoặc bootstrap.

Muốn giảm phụ thuộc nền tảng mà không làm mất tính đúng đắn, cần giữ nguyên semantics của HTTP, queue, stream, retry, idempotency và quyền truy cập. Adapter không làm runtime hay dịch vụ cloud trở nên giống nhau; nó giúp đặt khác biệt vào đúng ranh giới, kiểm thử được và thay đổi có kiểm soát. Với edge platform, còn phải xác nhận runtime Java, native image hoặc WebAssembly có thực sự được hỗ trợ. Khi port phản ánh đúng nhu cầu nghiệp vụ và adapter được kiểm thử theo hợp đồng, cùng một application core có thể chạy qua nhiều trigger và môi trường triển khai với mức thay đổi nhỏ hơn.

