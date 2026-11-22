# Request-response và một kết quả phản hồi

## Mục tiêu

RSocket hỗ trợ nhiều kiểu tương tác giữa hai đầu kết nối. Với **Request-Response**, bên gửi gửi một request và chờ đúng một kết quả phản hồi cho request đó. Trong Spring Framework, có thể triển khai phía nhận bằng method `@MessageMapping` trả về một giá trị hoặc `Mono<T>`, và gọi phía gửi bằng `RSocketRequester.retrieveMono(...)`.

Bài học này giải thích:

- Request-Response hoạt động như thế nào trong giao thức RSocket.
- Khi nào nên chọn Request-Response thay vì Request-Stream, Channel hoặc Fire-and-Forget.
- Cách ánh xạ request và response bằng `@MessageMapping`.
- Cách gọi route từ client bằng `RSocketRequester` và nhận một `Mono<T>`.
- Cách cấu hình route, codec, MIME type và xử lý lỗi.
- Những giới hạn cần lưu ý khi dùng một kết quả phản hồi trong ứng dụng reactive.

## 1. Request-Response trong RSocket

RSocket là giao thức giao tiếp hai chiều, bất đồng bộ và hỗ trợ multiplexing trên một kết nối TCP, WebSocket hoặc một transport dạng byte stream khác. Sau khi kết nối được thiết lập, hai phía đều có thể khởi tạo request. Vì vậy, trong thuật ngữ RSocket, bên gửi request được gọi là **requester**, bên xử lý request là **responder**; vai trò này không nhất thiết trùng với client và server ở tầng transport.

Với Request-Response:

1. Requester gửi một message chứa dữ liệu yêu cầu.
2. Responder xử lý request.
3. Responder gửi lại một message chứa kết quả duy nhất, hoặc kết thúc request bằng lỗi.
4. Request kết thúc sau khi requester nhận response hoặc error. Requester cũng có thể hủy request đang chờ.

Ở tầng giao thức, thao tác bắt đầu bằng frame `REQUEST_RESPONSE`. Responder trả về một `PAYLOAD` hoàn tất stream hoặc một `ERROR`. Mỗi request có stream ID riêng, vì vậy nhiều request-response có thể cùng hoạt động trên một kết nối RSocket mà không cần mở một TCP connection cho từng request.

Có thể hình dung:

~~~text
Requester                              Responder
    |                                      |
    |------ REQUEST_RESPONSE -------------->|
    |          request payload              |
    |                                      | xử lý
    |<------------- PAYLOAD ----------------|
    |          response payload             |
    |                                      |
    |          request hoàn tất             |
~~~

Request-Response phù hợp với thao tác có một kết quả rõ ràng, ví dụ:

- Tra cứu thông tin sản phẩm theo mã.
- Lấy hồ sơ người dùng theo ID.
- Tính phí giao dịch và trả về một kết quả.
- Kiểm tra trạng thái đơn hàng tại một thời điểm.
- Gửi lệnh cần nhận kết quả xử lý ngay trong cùng interaction.

Không nên dùng kiểu này nếu responder cần phát nhiều kết quả theo thời gian. Khi đó, Request-Stream phù hợp hơn.

## 2. So sánh các kiểu tương tác

RSocket định nghĩa bốn kiểu request chính:

| Kiểu tương tác | Dữ liệu gửi | Dữ liệu nhận | Trường hợp phù hợp |
| --- | --- | --- | --- |
| Request-Response | Một message | Một response | Tra cứu hoặc xử lý cần một kết quả |
| Request-Stream | Một message | Một stream response | Theo dõi giá, vị trí hoặc trạng thái thay đổi liên tục |
| Channel | Một stream request | Một stream response | Trao đổi dữ liệu liên tục theo cả hai hướng |
| Fire-and-Forget | Một message | Không có response | Gửi sự kiện hoặc lệnh không cần kết quả trực tiếp |

Ví dụ cùng một nghiệp vụ tra cứu:

- Request-Response: gửi mã sản phẩm và nhận một bản ghi sản phẩm.
- Request-Stream: gửi tiêu chí và nhận liên tiếp các sản phẩm phù hợp.
- Channel: client gửi liên tục các vị trí, server đồng thời gửi kết quả tính toán.
- Fire-and-Forget: gửi sự kiện ghi nhận một thao tác mà caller không cần response trong interaction đó.

Đừng chọn kiểu tương tác chỉ dựa trên việc payload có phải object hay không. Hãy dựa vào số lượng message đầu vào và số lượng kết quả mà nghiệp vụ thực sự cần.

## 3. Ánh xạ Request-Response trong Spring

Spring dùng cardinality (số lượng phần tử) của request và response để xác định interaction type khi xử lý method được đánh dấu `@MessageMapping`.

| Cardinality đầu vào | Cardinality đầu ra | Kiểu tương tác |
| --- | --- | --- |
| 0 hoặc 1 | 0 | Fire-and-Forget hoặc Request-Response |
| 0 hoặc 1 | 1 | Request-Response |
| 0 hoặc 1 | Nhiều | Request-Stream |
| Nhiều | 0, 1 hoặc nhiều | Request-Channel |

Trong bảng này:

- Cardinality `1`: một giá trị cụ thể hoặc một publisher đơn trị như `Mono<T>`.
- Cardinality `Nhiều`: publisher đa trị như `Flux<T>`.
- Cardinality `0`: không có payload đầu vào, hoặc method không trả dữ liệu như `void` hay `Mono<Void>`.

Để triển khai một request có payload và một response, dùng một giá trị đầu vào và một giá trị đầu ra. Cách thường gặp là nhận một DTO và trả về `Mono<DTO>`.

Ví dụ:

~~~java
@Controller
public class ProductRSocketController {

    private final ProductService productService;

    public ProductRSocketController(ProductService productService) {
        this.productService = productService;
    }

    @MessageMapping("products.find-by-id")
    public Mono<ProductResponse> findById(ProductRequest request) {
        return productService.findById(request.productId())
                .map(product -> new ProductResponse(
                        product.id(),
                        product.name(),
                        product.price()
                ));
    }
}
~~~

Method `findById` nhận một `ProductRequest` và trả về `Mono<ProductResponse>`. Vì đầu vào là một message và đầu ra là một kết quả đơn trị, Spring ánh xạ method này thành Request-Response.

Nếu method trả về `Flux<ProductResponse>`, Spring hiểu đầu ra là nhiều kết quả và interaction phù hợp sẽ là Request-Stream. Không đổi `Mono` thành `Flux` chỉ vì muốn dùng reactive API; kiểu publisher thể hiện số lượng kết quả mà contract cung cấp.

## 4. Xây dựng request và response DTO

Ví dụ dùng Java 17 record:

~~~java
import java.math.BigDecimal;

public record ProductRequest(String productId) {
}

public record ProductResponse(
        String productId,
        String name,
        BigDecimal price
) {
}
~~~

Request và response là hai kiểu dữ liệu riêng. Việc tách DTO giúp API có contract rõ ràng và tránh trả trực tiếp entity nội bộ của persistence layer.

Một response nên chứa những trường mà caller cần để hoàn thành nghiệp vụ. Nếu cần biểu diễn kết quả nghiệp vụ như không tìm thấy sản phẩm, có thể định nghĩa trường trạng thái hoặc kiểu kết quả rõ ràng. Không nên để caller phải suy luận từ các trường null tùy tiện.

Ví dụ response mở rộng:

~~~java
public record ProductLookupResponse(
        boolean found,
        String productId,
        String name,
        BigDecimal price,
        String message
) {
}
~~~

Với contract này, “không tìm thấy sản phẩm” có thể là một kết quả nghiệp vụ hợp lệ. Lỗi hạ tầng hoặc lỗi xử lý bất ngờ vẫn nên được biểu diễn bằng error signal.

## 5. Gửi request bằng RSocketRequester

`RSocketRequester` cung cấp fluent API để tạo request và nhận response dưới dạng object Java thay vì tự thao tác với byte buffer và frame giao thức.

Ví dụ requester kết nối qua TCP:

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;

RSocketRequester requester =
        RSocketRequester.builder()
                .tcp("localhost", 7000);
~~~

Lệnh trên tạo requester được cấu hình để kết nối tới server TCP tại port `7000`. Theo cách hoạt động của builder, kết nối được thiết lập khi request đầu tiên được thực hiện; không nhất thiết mở kết nối ngay tại thời điểm tạo requester.

Thực hiện Request-Response:

~~~java
import reactor.core.publisher.Mono;

Mono<ProductResponse> response =
        requester
                .route("products.find-by-id")
                .data(new ProductRequest("P-100"))
                .retrieveMono(ProductResponse.class);
~~~

Các bước có ý nghĩa:

- `route("products.find-by-id")` đặt route của request trong metadata.
- `data(...)` cung cấp một payload đầu vào.
- `retrieveMono(ProductResponse.class)` khai báo kiểu dữ liệu mong đợi và thực hiện Request-Response.

`retrieveMono(...)` trả về `Mono<ProductResponse>`. Đây là một publisher lazy: request thường chỉ được thực hiện khi publisher được subscribe hoặc được kết hợp vào một reactive chain có subscriber.

Trong ứng dụng reactive, hãy trả publisher về cho tầng gọi tiếp theo hoặc kết hợp với các operator:

~~~java
public Mono<ProductResponse> getProduct(String productId) {
    return requester
            .route("products.find-by-id")
            .data(new ProductRequest(productId))
            .retrieveMono(ProductResponse.class);
}
~~~

Nếu đang ở một điểm tích hợp imperative, có thể dùng `block()` để chờ kết quả, nhưng không nên block trên event-loop thread hoặc bên trong reactive pipeline:

~~~java
ProductResponse result = requester
        .route("products.find-by-id")
        .data(new ProductRequest("P-100"))
        .retrieveMono(ProductResponse.class)
        .block();
~~~

Đoạn cuối chỉ phù hợp ở ranh giới imperative được kiểm soát; code WebFlux hoặc service reactive nên giữ kiểu trả về `Mono<T>`.

## 6. Cấu hình responder và RSocket server

Để các method `@MessageMapping` được phát hiện, Spring cần `RSocketMessageHandler`. Ví dụ cấu hình handler trong Spring Framework:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.messaging.rsocket.annotation.support.RSocketMessageHandler;
import org.springframework.web.util.pattern.PathPatternRouteMatcher;

@Configuration
public class RSocketServerConfiguration {

    @Bean
    RSocketMessageHandler rsocketMessageHandler(
            RSocketStrategies strategies) {

        RSocketMessageHandler handler = new RSocketMessageHandler();
        handler.setRSocketStrategies(strategies);
        handler.setRouteMatcher(new PathPatternRouteMatcher());
        return handler;
    }
}
~~~

`RSocketMessageHandler` phát hiện các bean controller có method `@MessageMapping` và tạo responder cho RSocket server. `PathPatternRouteMatcher` là lựa chọn được Spring khuyến nghị khi có module `spring-web`.

Ở mức Java RSocket API, handler được gắn vào server:

~~~java
RSocketMessageHandler handler =
        applicationContext.getBean(RSocketMessageHandler.class);

CloseableChannel server = RSocketServer.create(handler.responder())
        .bind(TcpServerTransport.create("localhost", 7000))
        .block();
~~~

Đây là đoạn bind minh họa. Trong ứng dụng thực tế, quản lý vòng đời `CloseableChannel` cùng vòng đời ApplicationContext và đóng server khi ứng dụng shutdown. Nếu dùng Spring Boot, RSocket server có thể được auto-configure bằng `spring-boot-starter-rsocket` và các thuộc tính `spring.rsocket.server`; khi đó không cần tự bind theo cách trên.

## 7. Route và metadata

Route là địa chỉ logic để responder tìm method xử lý. Trong ví dụ, route là `products.find-by-id`. Nó được truyền dưới dạng metadata của RSocket message, không phải HTTP URL path.

Một số điểm cần nhớ:

- Route phải khớp giữa `RSocketRequester.route(...)` và `@MessageMapping`.
- Route có thể phân cấp, thường dùng dấu chấm làm separator.
- `SimpleRouteMatcher` mặc định dùng `AntPathMatcher`; `PathPatternRouteMatcher` có thể dùng khi `spring-web` hiện diện.
- Route matcher của RSocket không xử lý như URL path và không thực hiện URL decoding như HTTP.
- Route không thay thế xác thực hoặc phân quyền. Server vẫn phải xác minh caller và quyền truy cập dữ liệu.

Có thể khai báo route có biến:

~~~java
@Controller
public class ProductRSocketController {

    @MessageMapping("products.{productId}.details")
    public Mono<ProductResponse> details(
            @DestinationVariable String productId) {

        return productService.findById(productId)
                .map(product -> new ProductResponse(
                        product.id(),
                        product.name(),
                        product.price()
                ));
    }
}
~~~

Requester gọi route tương ứng:

~~~java
Mono<ProductResponse> response = requester
        .route("products.P-100.details")
        .retrieveMono(ProductResponse.class);
~~~

Dùng payload DTO khi request có nhiều trường hoặc cần contract dễ mở rộng. Dùng destination variable khi giá trị đó thực sự là một phần định tuyến.

## 8. Serialization, codec và MIME type

RSocket truyền data và metadata dưới dạng byte buffer. Spring cần encoder và decoder để chuyển đổi object Java thành payload và ngược lại.

Theo mặc định, `RSocketStrategies` chỉ có các codec cơ bản từ `spring-core` cho `String`, `byte[]` và `ByteBuffer`. Khi truyền DTO như `ProductRequest` và `ProductResponse`, ứng dụng cần codec phù hợp, thường đến từ module `spring-web` như Jackson JSON hoặc CBOR codecs.

Hai phía cần thống nhất cách serialize:

- Data MIME type mô tả định dạng payload, ví dụ JSON hoặc CBOR.
- Metadata MIME type mô tả cách mã hóa metadata. Mặc định thường dùng composite metadata để mang nhiều loại metadata trên cùng request.
- MIME type được khai báo trong SETUP frame và áp dụng cho connection.
- Route và metadata bảo mật có thể dùng metadata format riêng; không trộn metadata với payload nghiệp vụ.

Ví dụ cấu hình strategies với Jackson CBOR codecs:

~~~java
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.http.codec.cbor.JacksonCborEncoder;
import org.springframework.http.codec.cbor.JacksonCborDecoder;

RSocketStrategies strategies = RSocketStrategies.builder()
        .encoders(encoders -> encoders.add(new JacksonCborEncoder()))
        .decoders(decoders -> decoders.add(new JacksonCborDecoder()))
        .build();
~~~

Cùng một cấu hình tương thích cần được áp dụng cho requester và responder. Nếu encoder hoặc decoder không hỗ trợ kiểu dữ liệu hay MIME type đã chọn, request có thể lỗi trong bước encode/decode.

Spring Boot với `spring-boot-starter-rsocket` có thể auto-configure `RSocketStrategies` cùng các codec Jackson CBOR/JSON. Với Spring Framework thuần, hãy đăng ký encoder/decoder phù hợp và cấu hình strategies dùng chung cho `RSocketRequester` và `RSocketMessageHandler`.

## 9. Xử lý lỗi và timeout

Request-Response có thể kết thúc bằng một response hoặc một error. Ở phía requester, lỗi từ responder hoặc lỗi transport được chuyển thành error signal của Reactor `Mono`.

Có thể đặt timeout ở phía gọi:

~~~java
import java.time.Duration;

Mono<ProductResponse> response = requester
        .route("products.find-by-id")
        .data(new ProductRequest("P-100"))
        .retrieveMono(ProductResponse.class)
        .timeout(Duration.ofSeconds(3));
~~~

`timeout` phát lỗi nếu không có kết quả trong thời gian quy định. Chọn timeout theo SLA và độ trễ thực tế của nghiệp vụ; timeout quá ngắn gây lỗi giả khi hệ thống đang tải cao, còn timeout quá dài giữ request và tài nguyên lâu hơn cần thiết.

Có thể xử lý lỗi bằng Reactor:

~~~java
Mono<ProductResponse> response = requester
        .route("products.find-by-id")
        .data(new ProductRequest("P-100"))
        .retrieveMono(ProductResponse.class)
        .onErrorResume(error -> {
            log.warn("Product lookup failed", error);
            return Mono.error(
                    new ProductLookupException("Không thể tra cứu sản phẩm", error));
        });
~~~

Trong ví dụ, lỗi được chuyển thành exception ở tầng ứng dụng. Với lỗi nghiệp vụ dự kiến, có thể trả về một response có trạng thái rõ ràng; với lỗi bất ngờ, lỗi hệ thống hoặc lỗi giao tiếp, hãy giữ error signal để caller có thể retry, ghi log hoặc trả lỗi phù hợp.

Không đưa stack trace, SQL message hoặc thông tin nội bộ nhạy cảm vào response gửi cho caller. Hãy ánh xạ exception sang mã lỗi và thông điệp ổn định.

## 10. Hủy request và giới hạn của một response

Vì requester nhận kết quả dưới dạng `Mono<T>`, việc hủy subscription có thể hủy request đang chờ ở phía RSocket. Giao thức có frame `CANCEL` cho phép requester thông báo rằng không còn cần response. Responder nên dừng công việc có thể hủy nếu nghiệp vụ và implementation hỗ trợ.

Tuy nhiên, hủy request không đồng nghĩa mọi side effect đã được rollback. Nếu responder đã bắt đầu ghi dữ liệu hoặc gọi hệ thống bên ngoài, việc cancel có thể đến sau khi side effect xảy ra. Với lệnh ghi hoặc giao dịch quan trọng, cần transaction và idempotency phù hợp.

Request-Response chỉ có một response. Nếu cần nhiều kết quả, đừng gom nhiều phần tử thành một object khổng lồ chỉ để giữ kiểu tương tác; cân nhắc Request-Stream. Nếu cần trao đổi liên tục hai chiều, cân nhắc Channel.

## 11. Kiểm thử Request-Response

Nên kiểm tra cả logic responder lẫn kết nối RSocket thực tế.

### Unit test cho handler

Có thể kiểm tra method handler bằng Reactor Test:

~~~java
@Test
void returnsProductDetails() {
    ProductRequest request = new ProductRequest("P-100");

    StepVerifier.create(controller.findById(request))
            .expectNextMatches(response ->
                    response.productId().equals("P-100"))
            .verifyComplete();
}
~~~

Test này xác nhận logic reactive của handler trả về một kết quả rồi hoàn tất. Nó chưa kiểm tra route mapping, transport, serialization hoặc RSocket protocol.

### Integration test

Một integration test nên:

1. Khởi động RSocket server trên TCP hoặc WebSocket transport phù hợp.
2. Tạo `RSocketRequester` trỏ tới server.
3. Gửi request tới đúng route với DTO đầu vào.
4. Dùng `StepVerifier` để xác nhận nhận đúng một response và publisher hoàn tất.
5. Kiểm tra lỗi khi route không tồn tại hoặc responder phát sinh exception.
6. Kiểm tra lỗi encode/decode nếu hai phía cấu hình MIME type hoặc codec không tương thích.
7. Kiểm tra timeout và cancellation trong các tình huống có thể tái hiện ổn định.

Ví dụ kiểm tra đúng một phần tử:

~~~java
StepVerifier.create(
        requester.route("products.find-by-id")
                .data(new ProductRequest("P-100"))
                .retrieveMono(ProductResponse.class)
)
.expectNextMatches(response ->
        response.productId().equals("P-100"))
.verifyComplete();
~~~

`expectNextMatches` cùng `verifyComplete` xác nhận publisher phát ra một kết quả phù hợp rồi kết thúc. Nếu nhận nhiều kết quả, publisher `Mono` không thể phát chúng như một stream nhiều phần tử.

## 12. Lỗi thường gặp

### Route không tìm thấy handler

Kiểm tra chuỗi route trong `requester.route(...)` có khớp `@MessageMapping` không. Kiểm tra `RSocketMessageHandler` đã được đăng ký, controller đã nằm trong ApplicationContext và route matcher có cấu hình phù hợp.

### retrieveMono bị lỗi với request Publisher nhiều phần tử

Request-Response là kiểu một request đầu vào và một response đầu ra. `retrieveMono` không hỗ trợ payload đầu vào là Publisher đa trị như `Flux<T>`. Nếu gửi nhiều request element, dùng Request-Channel hoặc một interaction phù hợp khác.

### Không serialize được DTO

Kiểm tra encoder/decoder đã hỗ trợ class DTO và MIME type hay chưa. Codec mặc định chỉ xử lý các kiểu cơ bản; DTO cần codec như Jackson JSON/CBOR hoặc codec tùy chỉnh. Đảm bảo requester và responder dùng định dạng tương thích.

### Client chờ mãi không có response

Kiểm tra responder có trả về đúng một giá trị, có bị treo ở dependency reactive hay không, và có timeout ở phía requester. Tránh tạo publisher không phát tín hiệu kết thúc.

### Dùng block() trong reactive pipeline

`block()` chặn thread để chờ kết quả. Nếu gọi trên event-loop thread, có thể gây nghẽn hoặc lỗi runtime. Giữ dữ liệu ở dạng `Mono<T>` và compose bằng các operator reactive.

### Retry gây xử lý trùng

Nếu timeout xảy ra sau khi responder đã thực hiện side effect nhưng trước khi caller nhận response, caller không biết chắc thao tác đã hoàn tất hay chưa. Retry có thể chạy nghiệp vụ lần thứ hai. Với command ghi dữ liệu, gửi request ID/idempotency key và xử lý trùng ở responder.

## 13. Nguyên tắc sử dụng

- Dùng Request-Response khi mỗi request có đúng một kết quả nghiệp vụ.
- Dùng `Mono<T>` cho một response đơn trị; dùng `Flux<T>` khi cần stream nhiều kết quả.
- Dùng route rõ ràng và nhất quán giữa requester và responder.
- Dùng DTO riêng cho request và response để giữ contract ổn định.
- Cấu hình encoder/decoder và MIME type giống nhau ở hai phía.
- Đặt timeout phù hợp với SLA và xử lý error signal.
- Tránh `block()` trong reactive pipeline.
- Không retry mù quáng các request có side effect; dùng idempotency key.
- Không nhầm việc nhận response với việc đã có transaction phân tán hoặc bảo đảm exactly-once.
- Kiểm thử cả route, codec, lỗi, timeout và transport bằng integration test.

## 14. Tổng kết

Request-Response là interaction trong đó requester gửi một message và nhận một response duy nhất hoặc một lỗi. Trong Spring Framework, responder thường là method `@MessageMapping` nhận một payload và trả về một giá trị hoặc `Mono<T>`. Requester gọi route bằng `RSocketRequester` và dùng `retrieveMono(ResponseType.class)` để thực hiện Request-Response.

Mẫu cốt lõi:

~~~java
Mono<ProductResponse> response = requester
        .route("products.find-by-id")
        .data(new ProductRequest("P-100"))
        .retrieveMono(ProductResponse.class);
~~~

Để hoạt động đúng, hai phía cần thống nhất route, kiểu payload, encoder/decoder và MIME type. Giữ kết quả ở dạng reactive, xử lý timeout/error rõ ràng và thiết kế idempotency cho các request có side effect.

## Tài liệu tham khảo

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework Javadoc — RSocketRequester.RetrieveSpec](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.RetrieveSpec.html)
- [RSocket Protocol — Request-Response](https://github.com/rsocket/rsocket/blob/master/Protocol.md)
- [Spring Boot Reference — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html)
