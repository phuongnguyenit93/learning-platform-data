# Kết nối lười, tái sử dụng requester và quản lý tài nguyên

## 1. Mục tiêu và bối cảnh

Trong Spring Messaging, **RSocketRequester** là API cấp cao để gửi request qua một kết nối RSocket. Nó giúp ứng dụng làm việc với object Java và metadata thay vì tự thao tác trực tiếp với byte buffer của RSocket. Chủ đề này tập trung vào ba quyết định có ảnh hưởng trực tiếp đến hiệu năng và độ ổn định:

- Khi nào kết nối mạng thực sự được mở.
- Vì sao nên tái sử dụng một requester cho nhiều request.
- Ai chịu trách nhiệm đóng kết nối và dừng các luồng đang chạy.

RSocket hỗ trợ các kiểu tương tác Request-Response, Request-Stream, Request-Channel và Fire-and-Forget. Một kết nối có thể mang nhiều request đồng thời; vì vậy, requester thường đại diện cho một kênh giao tiếp lâu dài với một dịch vụ từ xa, thay vì một lần gọi đơn lẻ.

## 2. Kết nối lười hoạt động như thế nào?

Với API hiện hành từ Spring Framework 5.3 trở lên, có thể tạo requester bằng TCP hoặc WebSocket:

~~~java
RSocketRequester tcpRequester =
        RSocketRequester.builder().tcp("localhost", 7000);

RSocketRequester webSocketRequester =
        RSocketRequester.builder()
                .websocket(URI.create("ws://localhost:8080/rsocket"));
~~~

Hai lời gọi trên tạo cấu hình client và trả về RSocketRequester. Chúng **chưa mở kết nối mạng ngay tại thời điểm tạo requester**. Khi request đầu tiên được thực thi, RSocket client mới thiết lập transport và gửi frame SETUP. Kết nối được dùng chung cho các request tiếp theo.

Đây là kết nối lười ở cấp transport. Cần phân biệt nó với tính lazy của Reactor:

1. Tạo RSocketRequester chỉ chuẩn bị client và cấu hình kết nối.
2. Gọi route, data và retrieveMono/retrieveFlux tạo một Publisher mô tả request.
3. Publisher chỉ bắt đầu xử lý khi có subscriber. Khi request thực sự chạy, client mới kết nối nếu chưa có kết nối dùng được.

Ví dụ:

~~~java
RSocketRequester requester =
        RSocketRequester.builder().tcp("localhost", 7000);

Mono<Product> productMono = requester
        .route("catalog.find")
        .data("SKU-001")
        .retrieveMono(Product.class);

// Chưa gửi request chỉ vì biến productMono đã được tạo.
// Request bắt đầu khi Publisher được subscribe.
~~~

Trong ứng dụng WebFlux, hãy trả Mono hoặc Flux về cho tầng gọi để framework quản lý subscription:

~~~java
@GetMapping("/products/{sku}")
public Mono<Product> find(@PathVariable String sku) {
    return catalogClient.find(sku);
}
~~~

Không gọi block() trên event-loop của ứng dụng reactive. block() biến lời gọi bất đồng bộ thành lời gọi chặn và có thể làm giảm khả năng phục vụ đồng thời. Chỉ cân nhắc block() ở ranh giới đồng bộ thật sự, chẳng hạn một chương trình dòng lệnh, và luôn đặt timeout phù hợp.

Kết nối lười giúp ứng dụng không phải mở socket đến một dịch vụ chưa từng được gọi. Nó cũng cho phép khởi tạo các service phụ thuộc RSocket trong lúc Spring dựng ApplicationContext mà không buộc dịch vụ từ xa phải sẵn sàng ngay tại thời điểm đó. Đổi lại, lỗi DNS, lỗi transport, xác thực ở frame SETUP hoặc server chưa sẵn sàng có thể chỉ xuất hiện ở request đầu tiên. Nếu cần kiểm tra readiness, hãy chủ động thực hiện một health request có timeout trong quy trình kiểm tra sức khỏe của ứng dụng.

## 3. Tái sử dụng requester và kết nối dùng chung

Một RSocketRequester được tạo bằng tcp() hoặc websocket() dùng một RSocketClient bên dưới. Các request được gửi đồng thời qua một kết nối dùng chung; client có thể thiết lập lại kết nối khi cần. Điều này phù hợp với mô hình multiplexing của RSocket: nhiều request và stream cùng tồn tại trên một kết nối.

Với một dịch vụ từ xa cố định, cách thông dụng là tạo một requester trong Spring context và inject nó vào các service cần dùng. Không tạo requester mới cho mỗi HTTP request, mỗi lần gọi repository hoặc mỗi lần gọi một phương thức service.

Lợi ích của việc tái sử dụng:

- Giảm số lần thiết lập TCP/WebSocket và trao đổi SETUP.
- Tránh tạo nhiều client và nhiều kết nối không cần thiết.
- Cho phép các request đồng thời chia sẻ một kết nối RSocket.
- Tập trung cấu hình transport, codec, metadata và vòng đời vào một nơi.

Một requester thường được tái sử dụng trong cùng một phạm vi endpoint, transport và cấu hình kết nối. Nếu hai dịch vụ có host, port, transport hoặc thông tin xác thực ở cấp kết nối khác nhau, hãy tạo requester riêng cho từng cấu hình. Không dùng chung một requester chỉ vì hai dịch vụ có cùng kiểu dữ liệu.

### Cấu hình một requester trong Spring Boot

Spring Boot tự cấu hình RSocketRequester.Builder và các RSocketStrategies cần thiết khi có cấu hình RSocket phù hợp. Builder được đăng ký ở scope prototype vì nó có trạng thái cấu hình; mỗi điểm inject nhận một instance mới. Hãy dùng builder một lần để tạo một requester có cấu hình xác định.

Ví dụ cấu hình properties:

~~~java
@ConfigurationProperties(prefix = "app.rsocket.catalog")
public record CatalogRSocketProperties(String host, int port) {
}
~~~

~~~yaml
app:
  rsocket:
    catalog:
      host: localhost
      port: 7000
~~~

Đăng ký requester dưới dạng bean:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CatalogRSocketProperties.class)
public class RSocketClientConfiguration {

    @Bean(destroyMethod = "dispose")
    RSocketRequester catalogRequester(
            RSocketRequester.Builder builder,
            CatalogRSocketProperties properties) {

        return builder.tcp(properties.host(), properties.port());
    }
}
~~~

Phương thức bean nhận một builder mới từ Spring Boot, cấu hình endpoint rồi trả về requester. Bean có thể được inject vào nhiều service. Thuộc tính destroyMethod = "dispose" yêu cầu Spring đóng requester khi ApplicationContext dừng.

Có thể thay TCP bằng WebSocket nếu server công bố endpoint RSocket qua WebSocket:

~~~java
return builder.websocket(
        URI.create("ws://localhost:8080/rsocket"));
~~~

Endpoint và route phải khớp với cấu hình phía responder. Với WebSocket bảo mật, dùng URI HTTPS/WSS phù hợp với môi trường và cấu hình xác thực của hệ thống.

### Dùng requester trong service

~~~java
@Service
public class CatalogClient {

    private final RSocketRequester requester;

    public CatalogClient(
            @Qualifier("catalogRequester") RSocketRequester requester) {
        this.requester = requester;
    }

    public Mono<Product> find(String sku) {
        return requester.route("catalog.find")
                .data(sku)
                .retrieveMono(Product.class)
                .timeout(Duration.ofSeconds(3));
    }

    public Flux<Product> watch(String category) {
        return requester.route("catalog.watch")
                .data(category)
                .retrieveFlux(Product.class);
    }

    public Mono<Void> publish(CatalogChanged event) {
        return requester.route("catalog.changed")
                .data(event)
                .send();
    }
}
~~~

Các kiểu dữ liệu trao đổi có thể là record:

~~~java
public record Product(String sku, String name) {
}

public record CatalogChanged(String sku, String status) {
}
~~~

Đây là mã minh họa phía client; server cần triển khai các route catalog.find, catalog.watch và catalog.changed với kiểu payload/response tương thích. Các object phải được codec đã đăng ký encode và decode được.

Nếu có nhiều requester cố định, có thể khai báo nhiều bean với tên và endpoint riêng. Mỗi phương thức @Bean nên nhận builder riêng. Nếu tạo requester động cho nhiều endpoint, có thể lấy builder mới qua ObjectProvider<RSocketRequester.Builder>; khi đó ứng dụng cũng phải quản lý requester đã tạo và dispose chúng khi endpoint bị loại khỏi hệ thống.

## 4. Request, data, metadata và Publisher

Request thường được mô tả theo chuỗi thao tác:

- route(String): chọn route của handler ở phía nhận; route được truyền trong metadata.
- data(Object): đặt payload dữ liệu. Có thể truyền object đơn hoặc Publisher như Mono/Flux.
- metadata(Object, MimeType): thêm metadata cho request, ví dụ token xác thực hoặc thông tin tracing.
- retrieveMono(Class): nhận tối đa một kết quả.
- retrieveFlux(Class): nhận một luồng kết quả.
- send(): gửi Fire-and-Forget và trả Mono<Void>.

Ví dụ Request-Response:

~~~java
Mono<Product> result = requester.route("catalog.find")
        .data("SKU-001")
        .retrieveMono(Product.class);
~~~

Ví dụ Request-Stream:

~~~java
Flux<Product> results = requester.route("catalog.by-category")
        .data("books")
        .retrieveFlux(Product.class);
~~~

Ví dụ Request-Channel, trong đó cả đầu vào và đầu ra đều có thể là stream:

~~~java
Flux<Reply> replies = requester.route("chat.channel")
        .data(incomingMessages, ChatMessage.class)
        .retrieveFlux(Reply.class);
~~~

Với Publisher nhiều phần tử cùng kiểu, overload data(Publisher, Class) hoặc data(Publisher, ParameterizedTypeReference) giúp khai báo rõ kiểu phần tử để encoder không phải suy luận lại cho từng phần tử.

RSocket hỗ trợ Reactive Streams và backpressure. Với Request-Stream hoặc Request-Channel, nhu cầu của subscriber được truyền về phía phát dữ liệu. Subscriber có thể yêu cầu từng lượng dữ liệu phù hợp và hủy subscription khi không còn cần stream. Vì vậy, hãy giữ nguyên Mono/Flux trong chuỗi xử lý thay vì chuyển sớm sang collection bằng block hoặc tự thu toàn bộ stream vào bộ nhớ.

### Metadata theo request và metadata theo kết nối

Metadata có thể được gắn cho từng request:

~~~java
MimeType bearerMimeType =
        MimeType.valueOf(
                "message/x.rsocket.authentication.bearer.v0");

Mono<Product> result = requester.route("catalog.find")
        .metadata(accessToken, bearerMimeType)
        .data("SKU-001")
        .retrieveMono(Product.class);
~~~

Ví dụ trên cần metadata encoder phù hợp và responder phải hỗ trợ MIME type tương ứng. Composite metadata mặc định cho phép ghép nhiều mục metadata với MIME type riêng.

Builder cũng có setupData(), setupRoute() và setupMetadata(). Những giá trị này được đưa vào frame SETUP ở cấp kết nối, vì vậy phù hợp với thông tin dùng chung cho toàn bộ vòng đời kết nối. Metadata như token thay đổi theo từng người dùng hoặc từng request thường nên được truyền ở cấp request. Nếu danh tính xác thực gắn với SETUP, hãy tạo requester theo đúng phạm vi danh tính đó và không chia sẻ nó giữa các người dùng khác nhau.

### Fire-and-Forget không phải xác nhận nghiệp vụ

send() trả Mono<Void> báo rằng thao tác gửi message đã hoàn tất ở phía requester. Nó **không xác nhận handler phía nhận đã xử lý thành công nghiệp vụ**. Nếu cần biết phía nhận đã lưu dữ liệu, cập nhật trạng thái hoặc hoàn thành tác vụ, hãy thiết kế route Request-Response để responder trả về kết quả/acknowledgement rõ ràng.

## 5. Vòng đời và đóng tài nguyên

RSocketRequester triển khai Reactor Disposable. dispose() đóng kết nối transport ở client bên dưới và thông báo cho các subscriber; isDisposed() cho biết requester đã được dispose hay chưa. API dispose() có từ Spring Framework 5.3.7.

Với requester do ứng dụng sở hữu, hãy đóng nó khi ứng dụng dừng:

~~~java
@Bean(destroyMethod = "dispose")
RSocketRequester catalogRequester(RSocketRequester.Builder builder) {
    return builder.tcp("localhost", 7000);
}
~~~

Spring gọi dispose() khi bean bị hủy trong quá trình đóng ApplicationContext. Nếu tạo requester ngoài Spring container, hãy xác định rõ nơi sở hữu và gọi dispose() trong hook đóng ứng dụng hoặc khối finally phù hợp.

**Không dispose requester sau từng request.** Nhiều service và nhiều request đồng thời có thể đang dùng chung requester. Dispose ở cấp request sẽ đóng kết nối của những request khác và khiến các lần gọi tiếp theo phải khởi tạo lại client/kết nối. Quyền sở hữu nên tập trung ở bean hoặc thành phần quản lý vòng đời, còn các service sử dụng chỉ gọi request.

Đối với stream dài hạn, quản lý subscription riêng với vòng đời requester. Khi một người dùng rời màn hình hoặc một tác vụ kết thúc, hủy subscription của stream đó để dừng việc nhận dữ liệu. Khi ứng dụng dừng, dispose requester sẽ đóng client và thông báo cho các subscription còn hoạt động. Không giữ một Flux đã subscribe vô thời hạn nếu không còn nơi tiêu thụ dữ liệu.

Requester được inject vào phương thức @MessageMapping hoặc @ConnectMapping ở phía server đại diện cho kết nối của client đang gọi đến. Đây là requester gắn với một kết nối cụ thể; không đưa nó vào một singleton dùng chung cho mọi client. Hãy dùng nó trong phạm vi xử lý của kết nối đó và để hạ tầng RSocket quản lý vòng đời kết nối phía server.

## 6. Mất kết nối, timeout và retry

Với requester được tạo từ tcp() hoặc websocket(), RSocket client sử dụng kết nối dùng chung và có thể thiết lập lại kết nối khi cần. Điều này giúp các request sau tiếp tục hoạt động sau một số tình huống mất kết nối. Tuy nhiên, không nên hiểu rằng mọi request đang chạy đều tự động được gửi lại hoặc hoàn thành. Một request đang bay có thể thất bại khi transport bị ngắt; ứng dụng cần xử lý lỗi của Publisher đó.

Có thể đặt timeout và retry cho thao tác phù hợp:

~~~java
return requester.route("catalog.find")
        .data(sku)
        .retrieveMono(Product.class)
        .timeout(Duration.ofSeconds(3))
        .retryWhen(
                Retry.backoff(2, Duration.ofMillis(200)));
~~~

Retry chỉ nên áp dụng khi nghiệp vụ cho phép. Truy vấn đọc thường dễ retry hơn lệnh ghi. Nếu retry một lệnh tạo đơn hàng, trừ tiền hoặc gửi sự kiện, request có thể được xử lý ở lần đầu nhưng phản hồi bị mất; lần retry có thể thực hiện nghiệp vụ lần nữa. Hãy dùng idempotency key, mã giao dịch hoặc cơ chế deduplication ở phía nhận trước khi retry các thao tác ghi.

Timeout ở ví dụ trên giới hạn thời gian chờ cho Publisher của request. Nó không thay thế cấu hình keepalive, timeout kết nối hoặc chính sách reconnect ở tầng RSocketConnector. Khi cần tùy chỉnh keepalive, session resumption, interceptor hoặc reconnect, dùng callback rsocketConnector(...) của builder và chọn chính sách phù hợp với hệ thống.

## 7. RSocketStrategies và codec

RSocketRequester làm việc với object Java thông qua RSocketStrategies, nơi đăng ký Encoder và Decoder cho data và metadata. Nếu codec không hỗ trợ kiểu payload, request có thể thất bại khi encode hoặc decode.

Mặc định của Spring Framework chỉ có codec cơ bản cho String, byte[] và ByteBuffer. Spring Boot tự cấu hình RSocketStrategies và có thể đăng ký CBOR/JSON khi các thư viện Jackson tương ứng có mặt. Nếu cần định dạng khác, hãy thêm encoder/decoder tương ứng và cấu hình tập trung.

RSocketStrategies được thiết kế để tái sử dụng. Có thể dùng chung cấu hình codec giữa client và server trong cùng ứng dụng. Cấu hình codec nên ổn định theo requester; không tạo lại strategies cho từng request. Nếu một kết nối cần MIME type khác, hãy tạo requester với cấu hình kết nối tương ứng.

## 8. Các lỗi thường gặp

| Cách làm sai | Hậu quả | Cách xử lý |
|---|---|---|
| Tạo requester cho mỗi HTTP request | Tăng số client và kết nối, tốn tài nguyên | Tạo bean dùng chung cho endpoint cố định |
| Dispose sau mỗi lần gọi | Đóng kết nối mà request khác đang dùng | Dispose khi bean hoặc ứng dụng dừng |
| Tạo Mono/Flux nhưng không subscribe | Request không chạy | Trả Publisher cho tầng gọi hoặc subscribe ở ranh giới phù hợp |
| Gọi subscribe() tùy tiện trong service | Luồng chạy tách khỏi chuỗi xử lý, khó quản lý lỗi và hủy | Ưu tiên compose và trả Publisher; nếu tách luồng, xử lý lỗi và giữ quyền hủy |
| Dùng một Builder để tạo nhiều requester có cấu hình khác nhau | Cấu hình builder có thể bị tích lũy hoặc dùng nhầm | Lấy builder mới cho mỗi cấu hình |
| Coi send() là xác nhận đã xử lý | Có thể mất xác nhận nghiệp vụ | Dùng Request-Response nếu cần ack |
| Giả định reconnect sẽ phát lại request đang lỗi | Có thể bỏ sót hoặc thực hiện trùng nghiệp vụ | Xử lý lỗi và retry có kiểm soát, ưu tiên idempotency |
| Đặt token riêng của từng người dùng vào setupMetadata rồi chia sẻ requester | Có nguy cơ dùng sai danh tính giữa các request | Dùng metadata theo request hoặc requester riêng theo phạm vi xác thực |
| Không hủy stream dài hạn khi không còn dùng | Subscriber và luồng dữ liệu tiếp tục chiếm tài nguyên | Hủy subscription khi tác vụ kết thúc |

## 9. Cách kiểm tra và gỡ lỗi

Khi kiểm tra một requester, nên xác nhận theo thứ tự:

1. **Cấu hình endpoint:** host, port hoặc URI WebSocket đúng; server đang lắng nghe đúng transport.
2. **Kết nối đầu tiên:** tạo bean không đồng nghĩa đã kết nối. Gửi một request thật và kiểm tra log SETUP/transport để xác nhận kết nối.
3. **Route và payload:** route ở client khớp với @MessageMapping ở responder; kiểu dữ liệu và codec tương thích.
4. **Tái sử dụng:** gọi nhiều request qua cùng bean và quan sát log kết nối phía server. Với cùng requester, các request nên dùng chung kết nối đang hoạt động.
5. **Đồng thời và backpressure:** thử nhiều request song song và stream có lượng dữ liệu lớn; xác nhận subscriber có thể điều tiết hoặc hủy stream.
6. **Đóng ứng dụng:** dừng Spring context và kiểm tra requester được dispose; không còn stream thuộc ứng dụng tiếp tục chạy.

Có thể dùng @ConnectMapping ở responder để ghi log khi một kết nối mới được thiết lập. Nếu log SETUP xuất hiện mỗi lần một request thông thường được gọi, hãy kiểm tra xem ứng dụng có đang tạo requester mới liên tục hoặc dispose requester quá sớm hay không.

RSocketRequester được tạo bằng tcp()/websocket() sử dụng RSocketClient. Trong trường hợp này, phương thức rsocket() có thể trả về null vì requester chưa giữ một RSocket đã kết nối trực tiếp. Không dùng rsocket() như cách kiểm tra requester đã kết nối hay chưa. Hãy kiểm tra hành vi request, trạng thái dispose và log/metrics ở tầng transport.

## 10. Ghi nhớ khi thiết kế

- Một endpoint và một phạm vi xác thực ổn định thường có một RSocketRequester được tái sử dụng.
- Kết nối được mở khi request đầu tiên thực sự chạy; việc tạo bean không chứng minh server đã sẵn sàng.
- Mono/Flux chỉ thực thi khi có subscription; hãy giữ luồng reactive xuyên suốt ứng dụng.
- Nhiều request có thể chạy đồng thời trên kết nối dùng chung.
- Requester thuộc quyền sở hữu của thành phần quản lý vòng đời; dispose khi thành phần đó dừng.
- Hủy subscription của stream khi không còn nhu cầu; không dispose requester dùng chung để dừng một stream đơn lẻ.
- Dùng metadata theo request cho thông tin thay đổi theo request; dùng SETUP cho cấu hình cấp kết nối.
- Retry cần xét đến tính idempotent của nghiệp vụ và khả năng responder đã xử lý request trước khi kết nối bị ngắt.

## 11. Khác biệt API theo phiên bản

- Từ Spring Framework 5.3, ưu tiên Builder.tcp(host, port), Builder.websocket(uri) và Builder.transport(...). Các phương thức connectTcp(), connectWebSocket() và connect() cũ đã deprecated từ 5.3.
- API cũ connectTcp()/connectWebSocket() trả Mono<RSocketRequester>; kết nối được thực hiện khi Publisher được subscribe. Khi bảo trì mã Spring 5.2, cần subscribe hoặc block với timeout ở đúng ranh giới và quản lý requester sau khi nhận được.
- RSocketRequester có dispose()/isDisposed() từ Spring Framework 5.3.7. Với phiên bản cũ hơn, kiểm tra API thực tế trước khi dùng destroyMethod = "dispose".
- Ví dụ Spring Boot ở trên dùng builder do Boot auto-configure. Trong ứng dụng chỉ dùng Spring Framework, cần tự cung cấp RSocketStrategies và các cấu hình client cần thiết.

## Tài liệu tham khảo

- Spring Framework Reference — RSocket: https://docs.spring.io/spring-framework/reference/rsocket.html
- Spring Framework Javadoc — RSocketRequester: https://docs.spring.io/spring-framework/docs/7.0.x/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html
- Spring Framework Javadoc — RSocketRequester.Builder: https://docs.spring.io/spring-framework/docs/7.0.x/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.Builder.html
- Spring Boot Reference — RSocket: https://docs.spring.io/spring-boot/reference/messaging/rsocket.html
