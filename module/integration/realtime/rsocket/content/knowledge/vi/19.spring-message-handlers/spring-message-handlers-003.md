# Nhận dữ liệu bằng @Payload và tham số DTO

Trong Spring RSocket, một method được đánh dấu `@MessageMapping` có thể nhận trực tiếp phần data của request thông qua tham số `@Payload`. Tham số này có thể là kiểu đơn giản như `String`, `byte[]`, hoặc một DTO Java như `CreateOrderRequest`. Spring dùng các encoder/decoder trong `RSocketStrategies` để chuyển đổi byte của payload thành kiểu tham số mà handler khai báo.

Điều này giúp handler tập trung vào dữ liệu nghiệp vụ thay vì tự đọc từng byte. Để binding hoạt động đúng, client và server cần thống nhất data MIME type và có codec hỗ trợ kiểu dữ liệu tương ứng. Route của request và metadata vẫn là những thành phần riêng; chúng không tự động trở thành thuộc tính của DTO.

## 1. `@Payload` nhận phần data của RSocket message

Một RSocket `Payload` có hai vùng chính:

- **Data**: nội dung chính mà ứng dụng muốn xử lý, chẳng hạn chuỗi, JSON hoặc dữ liệu nhị phân.
- **Metadata**: thông tin bổ sung như route, tracing hoặc thông tin xác thực.

Trong Spring Messaging, `@Payload` đánh dấu tham số method được bind từ phần data. Ví dụ:

```java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class GreetingController {

    @MessageMapping("greeting")
    public Mono<String> greet(@Payload String name) {
        return Mono.just("Xin chào " + name);
    }
}
```

Khi client gửi data là chuỗi, Spring giải mã data thành `String` rồi truyền vào `greet`. `@Payload` làm rõ nguồn dữ liệu của tham số. Với handler có nhiều tham số, nên đánh dấu rõ tham số nào là body, tham số nào là header hoặc route variable.

Không nhầm `@Payload` với `@RequestBody` của Spring MVC/WebFlux. RSocket không nhận HTTP request body theo cách của controller HTTP; method handler nhận message RSocket và phần data của message đó.

## 2. Nhận DTO thay vì tự phân tích chuỗi

Với dữ liệu có nhiều trường, hãy định nghĩa DTO thể hiện hợp đồng request. Ví dụ yêu cầu tạo đơn hàng:

```java
public record CreateOrderRequest(
    String customerId,
    int quantity,
    String note
) {}
```

Handler nhận DTO bằng `@Payload`:

```java
@Controller
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("orders.create")
    public Mono<OrderView> create(
            @Payload CreateOrderRequest request) {
        return orderService.create(request);
    }
}
```

Khi request tới route `orders.create`, Spring chọn handler theo route, giải mã data thành `CreateOrderRequest`, rồi gọi method. Handler không cần tự đọc JSON hay gọi `ObjectMapper` trong trường hợp codec đã được cấu hình.

DTO nên mô tả dữ liệu mà client được phép gửi. Không dùng trực tiếp entity database làm request DTO vì entity có thể chứa trường nội bộ, trạng thái do server quản lý hoặc quan hệ không nên nhận từ client.

## 3. Data MIME type và codec quyết định cách chuyển đổi DTO

RSocket truyền data dưới dạng byte. Data MIME type được khai báo trong quá trình `SETUP`; codec dùng thông tin đó để chọn cách encode/decode. Ví dụ:

| Data MIME type | Nội dung | Kiểu Java thường dùng |
|---|---|---|
| `text/plain` | Văn bản UTF-8 | `String` |
| `application/json` | JSON | DTO, record, map hoặc collection |
| MIME type nhị phân riêng | Byte theo schema đã thống nhất | `byte[]`, `ByteBuffer` hoặc kiểu được codec hỗ trợ |

Với Spring Boot, starter RSocket tích hợp hệ thống codec của Spring. Khi dùng DTO JSON, bảo đảm Jackson JSON encoder/decoder có trong `RSocketStrategies` và client khai báo data MIME type phù hợp. Trong ví dụ dưới đây, client đặt MIME type là JSON:

```java
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.util.MimeTypeUtils;

Mono<OrderView> response = RSocketRequester.builder()
    .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
    .tcp("localhost", 7000)
    .flatMap(requester -> requester
        .route("orders.create")
        .data(new CreateOrderRequest("customer-01", 2, "Giao buổi chiều"))
        .retrieveMono(OrderView.class));
```

Client encode DTO thành JSON bytes; server decode bytes thành DTO tham số của handler. Response cũng được encode/decode theo codec và data MIME type đã thống nhất.

Nếu ứng dụng cần codec riêng, có thể đăng ký encoder/decoder trong `RSocketStrategies`. Ví dụ, khi dùng một định dạng nhị phân riêng, cả client lẫn server phải có codec tương thích. Chỉ khai báo một MIME type mà không có codec giải mã tương ứng sẽ không đủ để Spring tạo DTO.

## 4. Ví dụ đầy đủ request-response với DTO

Khai báo request và response:

```java
public record CreateOrderRequest(
    String customerId,
    int quantity,
    String note
) {}

public record OrderView(
    String orderId,
    String status,
    int quantity
) {}
```

Handler phía server:

```java
@Controller
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("orders.create")
    public Mono<OrderView> create(
            @Payload CreateOrderRequest request) {
        return orderService.create(request);
    }
}
```

Client gửi DTO và nhận response DTO:

```java
Mono<OrderView> created = requester
    .route("orders.create")
    .data(new CreateOrderRequest("customer-01", 2, "Giao buổi chiều"))
    .retrieveMono(OrderView.class);
```

Với `request-response`, handler thường trả về một `Mono<OrderView>`. Spring subscribe và chuyển kết quả reactive thành payload phản hồi theo lifecycle của RSocket. Client khai báo `OrderView.class` để giải mã payload phản hồi thành kiểu mong muốn.

## 5. Nhận DTO kèm validation

DTO là ranh giới dữ liệu từ client vào server, vì vậy cần kiểm tra dữ liệu trước khi gọi service nghiệp vụ. Có thể dùng Jakarta Bean Validation với `@Valid` và các constraint:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;

public record CreateOrderRequest(
    @NotBlank String customerId,
    @Positive int quantity,
    String note
) {}
```

Đánh dấu tham số bằng `@Valid`:

```java
import jakarta.validation.Valid;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import reactor.core.publisher.Mono;

@MessageMapping("orders.create")
public Mono<OrderView> create(
        @Valid @Payload CreateOrderRequest request) {
    return orderService.create(request);
}
```

Để sử dụng các constraint trong Spring Boot, thêm dependency validation nếu dự án chưa có:

```kotlin
implementation("org.springframework.boot:spring-boot-starter-validation")
```

`@NotBlank` yêu cầu `customerId` có nội dung; `@Positive` yêu cầu `quantity` lớn hơn 0. Validation cần được kích hoạt và cấu hình trong ứng dụng. Khi dữ liệu không hợp lệ, Spring phát sinh lỗi validation; hãy ánh xạ lỗi đó thành hợp đồng lỗi mà client có thể hiểu, thay vì để client phụ thuộc vào stack trace hoặc thông điệp exception nội bộ.

Validation cấu trúc không thay thế kiểm tra nghiệp vụ. Ví dụ, `quantity` có thể là số dương nhưng vẫn vượt giới hạn tồn kho. Điều kiện đó cần được kiểm tra trong service nghiệp vụ.

## 6. Phân biệt DTO payload với route và metadata

Một request RSocket có thể mang đồng thời route, data và metadata. Mỗi phần phục vụ mục đích khác nhau:

| Thành phần | Ví dụ | Cách nhận trong handler |
|---|---|---|
| Route | `orders.create` | Chọn method qua `@MessageMapping` |
| Data payload | `customerId`, `quantity`, `note` | `@Payload CreateOrderRequest` |
| Route variable | `orderId` trong route pattern | `@DestinationVariable` |
| Metadata/header | correlation ID, tenant context hoặc thông tin đã được trích xuất | `@Header` |

Ví dụ route variable và DTO cùng xuất hiện trong một handler:

```java
@MessageMapping("orders.{orderId}.notes.add")
public Mono<OrderView> addNote(
        @DestinationVariable String orderId,
        @Payload AddOrderNoteRequest request) {
    return orderService.addNote(orderId, request.note());
}
```

Trong ví dụ, `orderId` đến từ route; nội dung ghi chú đến từ data payload. Không cần lặp `orderId` trong DTO nếu route đã là nguồn định danh của thao tác và hợp đồng không yêu cầu trường đó.

Nếu cần nhận metadata tùy chỉnh bằng `@Header`, metadata phải được gửi đúng định dạng và được `MetadataExtractor` ánh xạ thành header của Spring Message. `@Payload` không tự giải mã metadata và cũng không tự lấy route.

## 7. Nhận DTO và header trong cùng một method

Một handler có thể nhận DTO và metadata đã được trích xuất:

```java
@MessageMapping("orders.find")
public Mono<OrderView> find(
        @Payload FindOrderRequest request,
        @Header("correlationId") String correlationId) {

    return orderService.find(request.orderId())
        .doOnEach(signal -> log.debug(
            "orders.find correlationId={}", correlationId));
}
```

`FindOrderRequest` được giải mã từ data. `correlationId` đến từ metadata đã ánh xạ vào header. Để ví dụ hoạt động, cấu hình `RSocketStrategies`/`MetadataExtractor` ở server để trích xuất metadata MIME type tương ứng thành key `correlationId`, và client gửi đúng loại metadata đó.

Không đưa token, secret hoặc thông tin nhạy cảm vào DTO chỉ vì handler đang nhận được payload. Thông tin xác thực nên đi qua cơ chế bảo mật và metadata được kiểm tra riêng; server không được tin các trường như `role`, `isAdmin` hoặc `tenantId` do client tự khai báo.

## 8. Nhận dữ liệu trong request-stream và request-channel

`@Payload` không chỉ dùng cho một object đơn. Với request-stream, client gửi một payload ban đầu và handler có thể trả một `Flux` kết quả:

```java
@MessageMapping("orders.search")
public Flux<OrderView> search(@Payload OrderSearchRequest request) {
    return orderService.search(request.status(), request.customerId());
}
```

Với request-channel, đầu vào là một luồng DTO. Handler nhận `Flux<ClientEvent>` và có thể trả về một luồng acknowledgement:

```java
@MessageMapping("events.ingest")
public Flux<EventAck> ingest(@Payload Flux<ClientEvent> events) {
    return events.concatMap(event -> eventService.accept(event)
        .map(result -> new EventAck(event.eventId(), result.status())));
}
```

`concatMap` xử lý từng event theo thứ tự và chỉ chuyển sang event tiếp theo khi publisher con hoàn tất. Nếu cần throughput cao hơn và chấp nhận xử lý song song, có thể chọn `flatMap` với concurrency được giới hạn. Việc chọn operator phải phản ánh yêu cầu thứ tự và tải của service.

Client có thể gửi channel bằng `RSocketRequester`:

```java
Flux<EventAck> acknowledgements = requester
    .route("events.ingest")
    .data(Flux.just(
        new ClientEvent("evt-1", "connected"),
        new ClientEvent("evt-2", "typing")
    ), ClientEvent.class)
    .retrieveFlux(EventAck.class);
```

Với stream/channel, lỗi có thể kết thúc toàn bộ tương tác. Nếu mỗi DTO có thể được xử lý độc lập và stream cần tiếp tục sau lỗi của một phần tử, hãy biểu diễn kết quả từng phần tử bằng một response envelope có trường trạng thái/lỗi.

## 9. Xử lý payload không hợp lệ và lỗi decode

Không phải mọi lỗi đều đến từ logic handler. Một số lỗi xuất hiện trước khi method được gọi:

- Data MIME type không được hỗ trợ.
- JSON sai cú pháp hoặc không thể chuyển thành DTO.
- Trường bắt buộc có kiểu dữ liệu không tương thích, ví dụ gửi chuỗi vào trường số.
- Payload rỗng trong khi handler yêu cầu một DTO.
- Metadata không đúng định dạng hoặc route không khớp handler.

Những lỗi decode có thể phát sinh trước khi handler được gọi, do đó không thể trông chờ một `try/catch` đặt bên trong method xử lý DTO để bắt tất cả. Hãy kiểm tra MIME type và codec, cấu hình xử lý lỗi tập trung phù hợp với phiên bản Spring đang dùng, và không để lộ chi tiết parser nội bộ cho client.

Với lỗi nghiệp vụ phát sinh trong handler, có thể dùng `@MessageExceptionHandler` để ánh xạ exception sang payload lỗi có cấu trúc:

```java
public record ApiError(String code, String message) {}

@MessageExceptionHandler(OrderNotFoundException.class)
public ApiError handleNotFound(OrderNotFoundException ex) {
    return new ApiError("ORDER_NOT_FOUND", "Không tìm thấy đơn hàng");
}
```

Client nên xử lý mã lỗi ổn định như `ORDER_NOT_FOUND`, không phân tích chuỗi exception hoặc stack trace.

## 10. Kiểm thử binding DTO

Nên kiểm tra ít nhất ba điều: route gọi đúng handler, data được decode thành đúng DTO và kết quả trả về có đúng kiểu. Có thể dùng `RSocketRequester` trong integration test và `StepVerifier` để kiểm tra reactive result:

```java
StepVerifier.create(
        requester.route("orders.create")
            .data(new CreateOrderRequest("customer-01", 2, "test"))
            .retrieveMono(OrderView.class)
    )
    .assertNext(order -> {
        assertThat(order.status()).isEqualTo("CREATED");
        assertThat(order.quantity()).isEqualTo(2);
    })
    .verifyComplete();
```

Ngoài trường hợp hợp lệ, hãy kiểm thử JSON sai định dạng, thiếu trường bắt buộc, giá trị vi phạm validation, MIME type không khớp và metadata thiếu. Với request-channel, kiểm tra thứ tự xử lý, hành vi khi một event lỗi và việc stream hoàn tất hoặc kết thúc lỗi đúng contract.

## 11. Những lỗi thường gặp khi dùng @Payload và DTO

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Handler không được gọi | Route không khớp `@MessageMapping` | Kiểm tra routing metadata và tên route |
| DTO không decode được | MIME type hoặc codec không tương thích | Thống nhất data MIME type và đăng ký encoder/decoder |
| DTO nhận giá trị null hoặc mặc định | JSON field không khớp tên/property hoặc cấu hình Jackson | Kiểm tra JSON, record component và Jackson configuration |
| `@Header` không có giá trị | Metadata chưa được trích xuất thành message header | Cấu hình `MetadataExtractor` và MIME type metadata |
| Validation không chạy | Thiếu validation starter hoặc chưa kích hoạt validation | Thêm `spring-boot-starter-validation` và `@Valid` |
| Payload lớn gây lỗi | Vượt giới hạn inbound payload hoặc giới hạn codec | Kiểm tra max inbound payload và cân nhắc stream/chunk ở tầng ứng dụng |
| Client nhận lỗi decode | Data không khớp schema DTO | Kiểm tra version schema và hợp đồng request |

Khi debug, hãy kiểm tra theo thứ tự: kết nối/SETUP, route metadata, data MIME type, codec, JSON/schema, validation, rồi mới tới logic service. Cách này giúp xác định lỗi xảy ra trước hay sau khi Spring gọi handler.

## 12. Checklist thiết kế handler nhận DTO

- [ ] Method có `@MessageMapping` với route rõ ràng.
- [ ] Tham số data được đánh dấu `@Payload` để thể hiện nguồn dữ liệu.
- [ ] DTO chỉ chứa các trường client được phép gửi.
- [ ] Client và server thống nhất data MIME type.
- [ ] `RSocketStrategies` có encoder/decoder hỗ trợ kiểu DTO.
- [ ] Dùng `@Valid` và Jakarta Validation cho dữ liệu đầu vào cần kiểm tra cấu trúc.
- [ ] Route variable, metadata/header và data payload được xử lý riêng.
- [ ] Không tin trường phân quyền hoặc tenant do client tự khai báo.
- [ ] Lỗi decode, validation và nghiệp vụ có cách phản hồi phù hợp.
- [ ] Có integration test cho request hợp lệ, payload sai định dạng và lỗi validation.

`@Payload` giúp Spring chuyển phần data của RSocket message thành tham số Java mà handler có thể sử dụng trực tiếp. DTO tạo ra hợp đồng request rõ ràng, dễ kiểm tra và dễ thay đổi theo phiên bản. Khi data MIME type, codec và metadata được cấu hình đúng, cùng một cách binding có thể dùng cho request-response, request-stream và request-channel mà vẫn giữ ranh giới rõ ràng giữa dữ liệu nghiệp vụ, route và ngữ cảnh kết nối.
