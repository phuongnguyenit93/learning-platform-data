# @Payload, @Header, @Headers và @DestinationVariable cho RSocket

Trong Spring Messaging, một method được đánh dấu bằng @MessageMapping có thể nhận dữ liệu từ nhiều phần khác nhau của một request RSocket. Bốn annotation trong bài này giúp phân biệt rõ nguồn dữ liệu: phần data của message, metadata đã được giải mã, hoặc route dùng để chọn handler. Chọn đúng annotation giúp chữ ký method thể hiện chính xác hợp đồng giao tiếp giữa requester và responder.

## 1. Nhìn nhanh bốn nguồn dữ liệu

| Annotation | Lấy dữ liệu từ | Dùng khi |
|---|---|---|
| @Payload | Phần data (payload) của request | Cần nhận DTO, chuỗi, hoặc luồng dữ liệu nghiệp vụ |
| @Header | Một giá trị metadata đã được MetadataExtractor đưa vào header map | Cần một giá trị riêng như tenant-id hoặc correlation-id |
| @Headers | Toàn bộ các giá trị metadata đã được giải mã và trích xuất | Cần đọc nhiều metadata trong cùng handler |
| @DestinationVariable | Biến được khớp từ route pattern của @MessageMapping | Route chứa mã định danh hoặc tham số định tuyến |

Điểm cần nhớ: payload và metadata là hai phần khác nhau của một message RSocket. Route cũng được truyền qua metadata, nhưng Spring dùng route để tìm handler và tách các biến route cho @DestinationVariable. @Header và @Headers làm việc với các giá trị metadata đã được giải mã thành key-value.

## 2. @Payload — nhận phần data của request

@Payload đánh dấu tham số nhận nội dung data của message. Nội dung này thường được giải mã thành một DTO bằng Decoder đã đăng ký trong RSocketStrategies.

~~~java
@MessageMapping("orders.create")
public Mono<OrderView> create(@Payload CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

Trong ví dụ, requester gửi một CreateOrderRequest trong phần data; Spring giải mã data thành đối tượng request rồi truyền vào tham số request.

Một số điểm quan trọng:

- @Payload có thể nhận một đối tượng cụ thể hoặc kiểu reactive như Mono<T> và Flux<T>.
- Annotation này có thể được bỏ qua khi tham số là kiểu phức hợp, không thuộc một loại tham số đặc biệt khác và được Spring suy luận là payload. Dùng @Payload tường minh giúp chữ ký dễ đọc, nhất là khi method có nhiều tham số.
- Với kiểu đơn giản như String, byte[] hoặc kiểu scalar, nên khai báo @Payload rõ ràng thay vì dựa vào suy luận.
- Nếu request chỉ cần route hoặc metadata và không có data, handler có thể không khai báo tham số @Payload.

Không nên đưa tenant-id, token hay route vào DTO chỉ để lấy chúng ra ở handler. Hãy giữ payload cho dữ liệu nghiệp vụ và dùng metadata hoặc route cho đúng mục đích.

## 3. @Header — nhận một metadata value

@Header dùng để lấy một giá trị đơn lẻ từ header map mà MetadataExtractor tạo ra sau khi giải mã metadata của RSocket message.

~~~java
@MessageMapping("orders.create")
public Mono<OrderView> create(
        @Payload CreateOrderRequest request,
        @Header(name = "tenant-id", required = false) String tenantId) {

    return orderService.createForTenant(request, tenantId);
}
~~~

Trong ví dụ, tenant-id là tên key mà ứng dụng đã đăng ký trong MetadataExtractor. required = false cho phép request không gửi giá trị này; khi đó tham số có thể nhận null. Nếu giá trị bắt buộc, giữ required mặc định hoặc cung cấp defaultValue phù hợp với hợp đồng của ứng dụng.

@Header trong RSocket không có nghĩa là HTTP request header. RSocket message có phần metadata riêng. Spring cần giải mã metadata và ánh xạ nó thành một key trước khi handler có thể nhận bằng @Header.

### Đăng ký metadata tùy chỉnh

DefaultMetadataExtractor có hỗ trợ sẵn routing metadata và đưa route vào key route. Với metadata tùy chỉnh, cần có Decoder phù hợp với MIME type của metadata và đăng ký ánh xạ MIME type đó sang tên key mà handler sử dụng.

Ví dụ phần đăng ký trong RSocketStrategies:

~~~java
.metadataExtractorRegistry(registry ->
    registry.metadataToExtract(tenantMimeType, String.class, "tenant-id"))
~~~

Ở đây tenantMimeType là MIME type mà requester dùng khi gửi metadata. Decoder tương ứng phải được cấu hình trong strategies. Phía requester cũng cần Encoder phù hợp để tuần tự hóa giá trị metadata. Tên key "tenant-id" phải khớp với tên trong @Header.

## 4. @Headers — nhận tất cả metadata đã trích xuất

@Headers thường được khai báo cùng Map<String, Object>. Spring truyền vào map chứa các metadata value đã được MetadataExtractor giải mã và đăng ký.

~~~java
@MessageMapping("orders.create")
public Mono<OrderView> create(
        @Payload CreateOrderRequest request,
        @Headers Map<String, Object> metadata) {

    Object route = metadata.get("route");
    Object tenantId = metadata.get("tenant-id");

    // Có thể dùng metadata cho logging, tracing hoặc kiểm tra ngữ cảnh.
    return orderService.create(request, tenantId);
}
~~~

Phân biệt hai cách nhận:

- @Header(name = "tenant-id") chỉ lấy một key cụ thể, phù hợp khi handler phụ thuộc trực tiếp vào giá trị đó.
- @Headers Map<String, Object> nhận nhiều key đã trích xuất, phù hợp khi cần kiểm tra metadata theo ngữ cảnh hoặc chuyển tiếp một tập metadata.

Map này không phải bản sao thô của toàn bộ byte metadata trên đường truyền. Nó chứa các giá trị mà MetadataExtractor đã giải mã và đưa vào map. Vì vậy, nếu một metadata MIME type chưa được đăng ký hoặc chưa có Decoder tương ứng, không thể mặc định rằng key đó sẽ xuất hiện trong map.

## 5. @DestinationVariable — lấy biến từ route

@DestinationVariable lấy một phần của route được khớp với placeholder trong pattern của @MessageMapping. Nó không lấy giá trị từ payload hoặc một metadata key tùy chỉnh.

~~~java
@MessageMapping("orders.{orderId}.status")
public Mono<OrderStatus> status(
        @DestinationVariable("orderId") String orderId) {

    return orderService.findStatus(orderId);
}
~~~

Nếu requester gửi route orders.ord-100.status, Spring khớp pattern orders.{orderId}.status và truyền ord-100 vào orderId.

Ví dụ requester:

~~~java
Mono<OrderStatus> result = requester
        .route("orders.ord-100.status")
        .retrieveMono(OrderStatus.class);
~~~

Route RSocket là route logic trong metadata, không phải URL HTTP. Route matcher mặc định dùng dấu chấm (.) làm dấu phân cách. Vì vậy, hãy giữ pattern và route do requester gửi thống nhất với cấu hình route matcher của ứng dụng. Nếu thay route matcher hoặc quy ước phân cách, cần kiểm tra lại cách pattern được khớp.

Dùng @DestinationVariable cho các thành phần định tuyến như orderId, userId hoặc roomId. Nếu dữ liệu đó là nội dung nghiệp vụ của request, hãy đặt nó trong payload; nếu nó là metadata tùy chỉnh, hãy dùng @Header hoặc @Headers.

## 6. Ví dụ kết hợp

Đoạn controller sau minh họa cả bốn annotation trong một ngữ cảnh đơn giản. Các record dùng cú pháp Java 17. Đây là ví dụ handler, không phải một ứng dụng RSocket độc lập: ứng dụng vẫn cần đăng ký controller, cấu hình RSocketMessageHandler/server, cùng Encoder và Decoder phù hợp.

~~~java
import java.util.Map;
import java.util.Objects;

import org.springframework.messaging.handler.annotation.DestinationVariable;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Headers;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Mono;

@Controller
public class OrderRSocketController {

    @MessageMapping("orders.create")
    public Mono<OrderView> create(
            @Payload CreateOrderRequest request,
            @Header(name = "tenant-id", required = false) String tenantId,
            @Headers Map<String, Object> metadata) {

        String route = Objects.toString(metadata.get("route"), "unknown");

        return Mono.just(new OrderView(
                "ord-100",
                request.sku(),
                request.quantity(),
                tenantId,
                route
        ));
    }

    @MessageMapping("orders.{orderId}.status")
    public Mono<OrderStatus> status(
            @DestinationVariable("orderId") String orderId) {

        return Mono.just(new OrderStatus(orderId, "CONFIRMED"));
    }

    public record CreateOrderRequest(String sku, int quantity) {}

    public record OrderView(
            String orderId,
            String sku,
            int quantity,
            String tenantId,
            String route) {}

    public record OrderStatus(String orderId, String status) {}
}
~~~

Cách đọc chữ ký create:

1. CreateOrderRequest request đến từ data của request nhờ @Payload.
2. tenantId đến từ metadata key tenant-id đã được MetadataExtractor đăng ký nhờ @Header.
3. metadata chứa các metadata value đã giải mã; ví dụ route là key được DefaultMetadataExtractor hỗ trợ sẵn.
4. Handler trả Mono<OrderView>, tức một kết quả bất đồng bộ cho request-response.

Cách đọc chữ ký status:

1. Route pattern khai báo placeholder {orderId}.
2. Requester gửi route cụ thể orders.ord-100.status.
3. @DestinationVariable("orderId") nhận phần ord-100 đã được khớp.
4. Handler không cần payload nếu chỉ cần route để tìm trạng thái.

Phía requester có thể gửi payload và metadata như sau (tenantMimeType phải trùng với MIME type đã đăng ký ở phía responder):

~~~java
Mono<OrderRSocketController.OrderView> created = requester
        .route("orders.create")
        .metadata(tenantId, tenantMimeType)
        .data(new OrderRSocketController.CreateOrderRequest("SKU-01", 2))
        .retrieveMono(OrderRSocketController.OrderView.class);
~~~

Trong request trên, route chọn handler, metadata cung cấp tenant-id, còn data mang CreateOrderRequest. Ba phần này có vai trò riêng và được Spring phân giải vào các tham số tương ứng.

## 7. Quan hệ với kiểu tương tác RSocket

Kiểu tương tác được xác định từ số lượng phần tử đầu vào và đầu ra của method:

- Một payload đơn và một kết quả đơn như Mono<T> phù hợp với Request-Response.
- Một payload đơn và kết quả nhiều phần tử như Flux<T> phù hợp với Request-Stream.
- Payload đầu vào nhiều phần tử như Flux<T> phù hợp với Request-Channel.
- Method không có payload có thể xử lý request chỉ dựa trên route hoặc metadata.

Do đó, @Payload không chỉ quyết định kiểu dữ liệu đầu vào; kiểu reactive của tham số và kiểu trả về còn ảnh hưởng đến interaction model mà handler hỗ trợ. @Header, @Headers và @DestinationVariable chỉ xác định cách lấy tham số, không tự thay đổi interaction model.

## 8. Lỗi thường gặp và cách kiểm tra

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| @Header luôn nhận null hoặc thiếu key | Metadata MIME type chưa được giải mã hoặc chưa đăng ký key | Kiểm tra MIME type, Decoder và metadataToExtract ở responder; kiểm tra Encoder và MIME type ở requester |
| @Header không nhận được HTTP header | Đang nhầm metadata của RSocket với HTTP header | Gửi metadata qua RSocket và đăng ký MetadataExtractor |
| @Headers không có key mong đợi | Map chỉ chứa giá trị đã được giải mã và trích xuất | Kiểm tra extractor; không giả định raw metadata tự xuất hiện trong Map |
| @DestinationVariable không khớp | Route requester không khớp pattern hoặc khác quy ước phân cách | So sánh route thực tế với @MessageMapping và cấu hình route matcher |
| Tham số payload nhận sai kiểu hoặc không được bind | Data không tương thích với Decoder/DTO hoặc thiếu @Payload cho kiểu đơn giản | Kiểm tra MIME type data, Encoder/Decoder, cấu trúc DTO và khai báo @Payload |
| Handler không được gọi | Route không khớp hoặc annotated responder chưa được đăng ký | Kiểm tra @Controller, RSocketMessageHandler và route pattern |

Khi debug, kiểm tra theo thứ tự:

1. Requester gửi đúng route chưa?
2. Phần data có đúng kiểu và MIME type mà Decoder hỗ trợ không?
3. Metadata có được gửi với MIME type phù hợp không?
4. MetadataExtractor đã ánh xạ metadata tùy chỉnh thành đúng key chưa?
5. Tên placeholder trong @MessageMapping có trùng với tên trong @DestinationVariable không?

## 9. Quy tắc chọn annotation

- Cần nội dung nghiệp vụ của request: dùng @Payload.
- Cần đúng một metadata value đã trích xuất: dùng @Header.
- Cần nhiều metadata value đã trích xuất: dùng @Headers Map<String, Object>.
- Cần một phần của route: dùng @DestinationVariable.

Đừng dùng một annotation để thay thế nguồn dữ liệu của annotation khác. Việc tách payload, metadata và route giúp API RSocket rõ ràng, dễ kiểm thử và ít phụ thuộc vào cách tuần tự hóa message.

## Tài liệu tham khảo

- Spring Framework Reference — RSocket, Annotated Responders, RSocketRequester và MetadataExtractor: https://docs.spring.io/spring-framework/reference/rsocket.html
- RSocket Protocol: https://rsocket.io/about/protocol/
