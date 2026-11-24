# Mô hình request-stream: một yêu cầu và nhiều phần tử phản hồi

Request-stream là interaction model của RSocket trong đó bên yêu cầu gửi một payload ban đầu và bên phản hồi phát ra một luồng gồm không, một hoặc nhiều phần tử. Mô hình này phù hợp khi client cần đăng ký nhận dữ liệu liên tục, chẳng hạn giá thị trường, trạng thái thiết bị, tiến độ xử lý hoặc các sự kiện của một đơn hàng.

Khác với request-response, nơi một request mong đợi tối đa một kết quả, request-stream giữ tương tác mở để gửi nhiều kết quả theo thời gian. Client vẫn có thể điều tiết lượng dữ liệu muốn nhận bằng backpressure và hủy stream khi không còn nhu cầu. RSocket kết hợp mô hình này với Reactive Streams, vì vậy Java thường biểu diễn luồng phản hồi bằng Reactor <code>Flux&lt;T&gt;</code>.

## 1. Request-stream giải quyết bài toán nào?

Giả sử một ứng dụng theo dõi nhiệt độ của một cảm biến. Client gửi mã cảm biến một lần, sau đó server gửi các lần đo mới khi chúng xuất hiện. Nếu dùng request-response, client phải gửi request lặp đi lặp lại để hỏi giá trị mới. Với request-stream, client chỉ cần mở một tương tác và nhận nhiều giá trị trên cùng stream.

Một số trường hợp sử dụng điển hình:

- Theo dõi giá cổ phiếu, tỷ giá hoặc giá sản phẩm theo thời gian.
- Nhận trạng thái và tiến độ của một tác vụ chạy lâu.
- Theo dõi telemetry như nhiệt độ, độ ẩm, CPU hoặc trạng thái thiết bị IoT.
- Nhận sự kiện cập nhật của đơn hàng, chuyến giao hàng hoặc phiên làm việc.
- Phát dữ liệu phân trang hoặc kết quả tính toán thành nhiều phần.

Request-stream phù hợp khi client chỉ cần gửi một yêu cầu đầu vào và nhận một chiều dữ liệu phản hồi. Nếu client cũng cần liên tục gửi nhiều phần tử đầu vào trong cùng tương tác, hãy xem xét request-channel.

## 2. Cấu trúc của một tương tác request-stream

Một request-stream bắt đầu bằng một request duy nhất từ requester. Request này mang payload đầu vào và số lượng phần tử phản hồi ban đầu mà requester sẵn sàng nhận. Responder sau đó phát các payload phản hồi trên cùng stream.

~~~text
Requester (client)                         Responder (server)
       |                                           |
       |--- REQUEST_STREAM ----------------------->|
       |    initial request payload                |
       |    initial request N                      |
       |                                           |
       |<---------------- PAYLOAD (NEXT) -----------|
       |<---------------- PAYLOAD (NEXT) -----------|
       |                                           |
       |--- REQUEST_N ---------------------------->|
       |                                           |
       |<---------------- PAYLOAD (NEXT) -----------|
       |<---------------- PAYLOAD (COMPLETE) -------|
       |                                           |
~~~

Ở mức giao thức, các frame chính có ý nghĩa như sau:

| Frame | Hướng thường gặp | Ý nghĩa |
| --- | --- | --- |
| REQUEST_STREAM | Requester → Responder | Mở stream, mang payload yêu cầu ban đầu và demand ban đầu. |
| PAYLOAD với NEXT | Responder → Requester | Mang một phần tử phản hồi. |
| REQUEST_N | Requester → Responder | Yêu cầu thêm một số lượng phần tử phản hồi. |
| PAYLOAD với COMPLETE | Responder → Requester | Báo chiều phản hồi đã hoàn tất; có thể đi kèm phần tử cuối. |
| CANCEL | Requester → Responder | Hủy stream vì requester không còn cần dữ liệu. |
| ERROR (stream-level) | Responder → Requester | Kết thúc stream này do lỗi; ERROR ở cấp connection có phạm vi ảnh hưởng rộng hơn. |

Một stream có stream ID riêng. Nhiều request-stream có thể cùng tồn tại trên một RSocket connection; việc một stream hoàn tất hoặc bị hủy không tự động đóng các stream khác.

## 3. Vòng đời tín hiệu của request-stream

Ở phía client, Subscriber nhận các tín hiệu Reactive Streams theo thứ tự hợp lệ:

1. <code>onSubscribe</code>: nhận Subscription để điều khiển nhu cầu hoặc hủy stream.
2. Không hoặc nhiều lần <code>onNext</code>: mỗi lần mang một phần tử phản hồi.
3. Một tín hiệu kết thúc: <code>onComplete</code> nếu hoàn tất bình thường hoặc <code>onError</code> nếu có lỗi.

Một request-stream có thể hoàn tất mà không phát phần tử nào. Ví dụ, client yêu cầu theo dõi một thiết bị không còn tồn tại và server quyết định trả về luồng rỗng. Điều này khác với trường hợp server phát lỗi vì thiết bị không hợp lệ hoặc client không có quyền truy cập.

~~~text
onSubscribe
    |
    +---- onNext(item 1)
    |
    +---- onNext(item 2)
    |
    +---- onNext(item 3)
    |
    +---- onComplete
       hoặc
         onError(error)
~~~

Sau <code>onComplete</code> hoặc <code>onError</code>, không có phần tử tiếp theo trong cùng stream. Nếu requester gọi cancel, nó chủ động kết thúc nhu cầu nhận dữ liệu; không nên chờ server gửi <code>onComplete</code> như một xác nhận hủy.

## 4. Backpressure và điều tiết luồng phản hồi

Request-stream được thiết kế để requester điều khiển số phần tử mà nó sẵn sàng nhận. Cơ chế này gọi là backpressure. Khi mở stream, requester gửi initial request N trong frame REQUEST_STREAM. Khi đã tiêu thụ một phần demand, requester có thể gửi REQUEST_N để yêu cầu thêm phần tử.

Ví dụ, client ban đầu yêu cầu 5 phần tử. Server có thể phát tối đa 5 phần tử theo demand đó. Sau khi client xử lý xong một số phần tử, nó yêu cầu thêm 3 phần tử. Server chỉ được tiếp tục phát theo nhu cầu còn lại.

Backpressure giúp hạn chế việc server đẩy quá nhiều dữ liệu vào hàng đợi hoặc bộ nhớ của client. Tuy nhiên, backpressure không phải giới hạn tốc độ theo giây, không phải quota người dùng và cũng không tự giải quyết mọi vấn đề của nguồn dữ liệu nóng. Ứng dụng vẫn cần chọn chiến lược buffer, giới hạn stream và xử lý nguồn phát nhanh hơn tốc độ tiêu thụ.

Với Reactor, các toán tử trung gian và Subscriber quyết định demand được truyền ngược lên nguồn. Nếu client chỉ cần xử lý từng phần tử rồi yêu cầu phần tử tiếp theo, có thể dùng <code>BaseSubscriber</code>:

~~~java
prices.subscribe(new BaseSubscriber<PriceUpdate>() {

    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        request(5);
    }

    @Override
    protected void hookOnNext(PriceUpdate update) {
        process(update);
        request(1);
    }

    @Override
    protected void hookOnError(Throwable error) {
        log.error("Price stream failed", error);
    }

    @Override
    protected void hookOnComplete() {
        log.info("Price stream completed");
    }
});
~~~

Subscriber này yêu cầu ban đầu 5 phần tử. Sau mỗi lần xử lý một phần tử, nó yêu cầu thêm một phần tử. Trong ứng dụng thật, cần bảo đảm <code>process</code> không chặn quá lâu; nếu xử lý nặng, hãy tổ chức thực thi và giới hạn concurrency phù hợp.

### Nguồn dữ liệu nóng và chính sách buffer

Một nguồn như <code>Flux.interval</code>, callback từ thiết bị hoặc message broker có thể phát dữ liệu theo đồng hồ riêng. Nếu nguồn phát nhanh hơn tốc độ tiêu thụ, ứng dụng phải quyết định cách xử lý:

| Chiến lược | Hành vi | Khi phù hợp |
| --- | --- | --- |
| Buffer có giới hạn | Giữ tối đa số phần tử đã cấu hình; cần quyết định khi đầy. | Sự kiện cần giữ thứ tự và có thể chấp nhận độ trễ ngắn. |
| Drop | Bỏ phần tử mới hoặc phần tử cũ theo chính sách. | Dữ liệu lấy mẫu mà không cần giữ mọi lần phát. |
| Latest | Giữ giá trị mới nhất, bỏ các giá trị trung gian. | Dashboard chỉ cần trạng thái hiện tại. |
| Giảm tốc nguồn | Yêu cầu nguồn phát theo demand nếu nguồn hỗ trợ. | Nguồn có thể điều tiết theo Reactive Streams. |

Ví dụ dashboard chỉ cần giá mới nhất có thể dùng chính sách latest:

~~~java
Flux<PriceUpdate> latestPrices =
    priceFeed(symbol)
        .onBackpressureLatest();
~~~

Chính sách này có thể làm mất các giá trị trung gian. Với audit log, giao dịch hoặc sự kiện cần bảo toàn đầy đủ, không được tùy tiện drop hoặc latest; cần buffer có giới hạn, lưu trữ bền vững hoặc thiết kế một luồng xử lý có xác nhận.

## 5. Triển khai request-stream ở phía server với Spring Boot

Trong Spring Boot, một method được đánh dấu bằng <code>@MessageMapping</code> có thể trả về <code>Flux&lt;T&gt;</code>. Khi client gọi route bằng request-stream, Spring chuyển payload đầu vào thành tham số method và chuyển các phần tử của Flux thành phản hồi trên stream.

Ví dụ một server cung cấp dữ liệu giá:

~~~java
@Controller
public class PriceStreamController {

    private final PriceService priceService;

    public PriceStreamController(PriceService priceService) {
        this.priceService = priceService;
    }

    @MessageMapping("prices.watch")
    public Flux<PriceUpdate> watch(PriceWatchRequest request) {
        return priceService.watch(request.symbol())
            .doOnSubscribe(subscription ->
                log.info("Start watching {}", request.symbol()))
            .doOnNext(update ->
                log.debug("New price for {}: {}", request.symbol(), update.price()))
            .doOnCancel(() ->
                log.info("Client stopped watching {}", request.symbol()))
            .doOnError(error ->
                log.warn("Price stream failed for {}", request.symbol(), error));
    }
}
~~~

Request đầu vào có thể là:

~~~java
public record PriceWatchRequest(String symbol) {}

public record PriceUpdate(
    String symbol,
    BigDecimal price,
    Instant observedAt
) {}
~~~

Method <code>watch</code> nhận một <code>PriceWatchRequest</code> duy nhất và trả về <code>Flux&lt;PriceUpdate&gt;</code>. Mỗi phần tử trong Flux trở thành một phần tử phản hồi. Khi nguồn hoàn tất, client nhận tín hiệu hoàn tất; khi nguồn lỗi và lỗi không được phục hồi, client nhận lỗi của stream.

Không nên gọi <code>subscribe()</code> bên trong handler rồi trả về một Publisher khác không liên quan. Spring cần quản lý Publisher được trả về để truyền demand, cancellation và lỗi qua RSocket. Nếu tự subscribe và tách luồng, việc hủy từ client có thể không dừng được công việc phía server.

### Nguồn phát theo chu kỳ

Nếu dữ liệu được tạo theo chu kỳ, có thể tạo Flux từ nguồn thời gian:

~~~java
public Flux<PriceUpdate> watch(String symbol) {
    return Flux.interval(Duration.ofSeconds(1))
        .map(tick -> priceRepository.currentPrice(symbol))
        .map(price -> new PriceUpdate(symbol, price, Instant.now()));
}
~~~

Ví dụ này minh họa nguồn cập nhật theo chu kỳ. Trong triển khai thật, không nên gọi repository đồng bộ chặn event loop; hãy dùng API non-blocking hoặc chuyển thao tác blocking sang scheduler phù hợp. Cũng cần đặt chính sách buffer/drop/latest nếu nguồn không thể giảm tốc theo demand.

## 6. Gọi request-stream từ client bằng RSocketRequester

Client dùng <code>RSocketRequester</code> để chọn route, gửi payload ban đầu và nhận nhiều phần tử bằng <code>retrieveFlux</code>.

~~~java
Flux<PriceUpdate> prices = requester
    .route("prices.watch")
    .data(new PriceWatchRequest("ACME"))
    .retrieveFlux(PriceUpdate.class);

Disposable subscription = prices.subscribe(
    update -> log.info(
        "{} price={}",
        update.symbol(),
        update.price()
    ),
    error -> log.error("Unable to receive prices", error),
    () -> log.info("Price stream completed")
);
~~~

Lời gọi trên tạo một request-stream. Client gửi một payload <code>PriceWatchRequest</code>, sau đó nhận các <code>PriceUpdate</code> trong một Flux. Ba callback lần lượt xử lý dữ liệu, lỗi và hoàn tất.

Nếu người dùng rời màn hình hoặc không còn theo dõi mã đó, client có thể hủy subscription:

~~~java
subscription.dispose();
~~~

Với Reactor, dispose subscription sẽ truyền cancellation về upstream. RSocket chuyển việc hủy thành tín hiệu CANCEL cho stream tương ứng. Server nên dùng tín hiệu cancellation để dừng subscription tới nguồn dữ liệu, giải phóng listener hoặc hủy tác vụ đang chạy nếu có thể.

Một connection có thể phục vụ nhiều request-stream đồng thời. Vì vậy, ứng dụng nên giữ Disposable theo từng tác vụ hoặc từng người dùng; không dùng một biến subscription chung cho nhiều stream độc lập.

## 7. Xử lý lỗi và timeout của stream

Lỗi trong request-stream có thể xuất hiện trước khi có phần tử đầu tiên hoặc sau khi client đã nhận một số phần tử. Khi lỗi xảy ra, stream kết thúc bằng <code>onError</code>; những phần tử đã nhận trước đó vẫn đã được xử lý và không tự động bị hoàn tác.

Một số nguồn lỗi thường gặp:

- Route không tồn tại hoặc client không có quyền truy cập.
- Nguồn dữ liệu phía server bị lỗi.
- Kết nối transport bị mất hoặc session đóng.
- Serializer không giải mã được payload.
- Một thao tác downstream trong pipeline phát sinh exception.

Có thể xử lý lỗi bằng các toán tử Reactor:

~~~java
Flux<PriceUpdate> safePrices = requester
    .route("prices.watch")
    .data(new PriceWatchRequest("ACME"))
    .retrieveFlux(PriceUpdate.class)
    .doOnError(error -> log.warn("Price stream error", error))
    .onErrorResume(error -> fallbackPriceFeed("ACME"));
~~~

<code>doOnError</code> chỉ quan sát lỗi, còn <code>onErrorResume</code> thay nhánh lỗi bằng một Publisher khác. Nếu fallback là luồng rỗng, client nhận hoàn tất bình thường sau khi phục hồi. Cần bảo đảm fallback có cùng ý nghĩa nghiệp vụ và không che giấu lỗi cần được hiển thị cho người dùng.

Timeout cũng cần được chọn theo loại stream. Một stream cập nhật liên tục có thể cần timeout cho khoảng thời gian không nhận được phần tử; stream chỉ phát khi có sự kiện có thể im lặng hợp lệ trong thời gian dài. Ví dụ:

~~~java
Flux<PriceUpdate> prices = requester
    .route("prices.watch")
    .data(new PriceWatchRequest("ACME"))
    .retrieveFlux(PriceUpdate.class)
    .timeout(Duration.ofSeconds(30));
~~~

Timeout ở đây áp dụng cho thời gian chờ tín hiệu tiếp theo theo semantics của Reactor. Với nguồn event thưa, nên dùng heartbeat hoặc timeout theo SLA phù hợp để tránh kết thúc stream chỉ vì không có thay đổi nghiệp vụ.

## 8. Reconnect và khôi phục stream

Khi RSocket connection bị mất, các request-stream đang chạy trên connection đó có thể kết thúc bằng lỗi. Tạo một connection mới không tự động khôi phục các stream cũ. Ứng dụng cần quyết định stream nào nên được đăng ký lại và cách tiếp tục dữ liệu từ vị trí nào.

Một quy trình khôi phục thường gồm:

1. Phát hiện connection hoặc stream đã lỗi.
2. Kết nối lại và chờ RSocket session mới sẵn sàng.
3. Đăng ký lại các stream còn cần thiết.
4. Nếu nguồn hỗ trợ, gửi cursor, sequence number hoặc timestamp trong payload để tiếp tục từ vị trí đã nhận.
5. Loại bỏ bản ghi trùng nếu server có thể phát lại một khoảng dữ liệu.

Không nên retry request-stream một cách mù quáng. Việc đăng ký lại có thể tạo stream mới và nhận dữ liệu từ đầu, từ thời điểm hiện tại hoặc từ cursor do ứng dụng cung cấp, tùy thiết kế của server. Nếu sự kiện có thể bị phát lại, client cần xử lý duplicate bằng sequence number hoặc event ID.

RSocket Resume là một extension ở cấp phiên giúp tiếp tục truyền frame trong các điều kiện cấu hình và lưu giữ trạng thái phù hợp. Nó không thay thế cursor nghiệp vụ hoặc cơ chế chống trùng khi ứng dụng cần khôi phục một subscription theo logic miền.

## 9. So sánh request-stream với các interaction model khác

Các interaction model có thể cùng dùng payload và route, nhưng khác nhau về số lượng dữ liệu và chiều truyền:

| Interaction model | Dữ liệu đầu vào | Dữ liệu đầu ra | Trường hợp phù hợp |
| --- | --- | --- | --- |
| Request-response | Một request | Tối đa một response | Tra cứu một đơn hàng hoặc lấy hồ sơ. |
| Fire-and-forget | Một request | Không có response nghiệp vụ | Gửi một sự kiện hoặc lệnh không cần xác nhận kết quả ngay. |
| Request-stream | Một request | Nhiều response | Theo dõi giá, telemetry hoặc tiến độ. |
| Request-channel | Một luồng request | Một luồng response | Đồng bộ dữ liệu hai chiều hoặc xử lý tương tác liên tục. |

Nếu client chỉ cần gửi mã thiết bị rồi nhận các lần đo, request-stream là lựa chọn tự nhiên. Nếu client cũng gửi liên tục lệnh điều khiển hoặc dữ liệu cảm biến lên server trong cùng tương tác, request-channel có thể phù hợp hơn.

## 10. Kiểm thử request-stream bằng StepVerifier

Có thể kiểm thử Publisher phản hồi bằng <code>StepVerifier</code> mà không cần kiểm tra log. Ví dụ với một luồng hữu hạn:

~~~java
Flux<Integer> response = Flux.just(10, 20, 30);

StepVerifier.create(response)
    .expectNext(10, 20, 30)
    .verifyComplete();
~~~

Để xác nhận backpressure, bắt đầu với demand bằng không rồi yêu cầu từng phần tử:

~~~java
StepVerifier.create(Flux.range(1, 3), 0)
    .thenRequest(1)
    .expectNext(1)
    .thenRequest(2)
    .expectNext(2, 3)
    .verifyComplete();
~~~

Có thể kiểm thử cancellation bằng Publisher quan sát tín hiệu hủy:

~~~java
AtomicBoolean cancelled = new AtomicBoolean();

Flux<Long> source = Flux.interval(Duration.ofMillis(100))
    .doOnCancel(() -> cancelled.set(true));

StepVerifier.create(source)
    .expectNext(0L)
    .thenCancel()
    .verify();

assertTrue(cancelled.get());
~~~

Ngoài kiểm thử Publisher đơn lẻ, integration test nên mở RSocket server và client thật trên transport thử nghiệm, gọi route request-stream và xác nhận dữ liệu, lỗi, hoàn tất cũng như cancellation đi qua đúng hai phía.

Các tình huống cần kiểm tra:

- Server phát nhiều phần tử theo đúng thứ tự.
- Server trả stream rỗng và hoàn tất bình thường.
- Server phát lỗi trước phần tử đầu tiên.
- Server phát một số phần tử rồi mới lỗi.
- Client yêu cầu theo nhóm và server tôn trọng demand.
- Client cancel và server giải phóng nguồn dữ liệu.
- Nhiều client mở các stream đồng thời mà không dùng chung trạng thái subscription.
- Reconnect và đăng ký lại stream không tạo dữ liệu trùng ngoài chính sách đã công bố.

## 11. Những lỗi thường gặp khi triển khai

| Hiện tượng | Nguyên nhân có thể có | Cách kiểm tra hoặc xử lý |
| --- | --- | --- |
| Chỉ nhận được một phần tử | Client dùng request-response hoặc server chỉ trả một giá trị. | Dùng request-stream và trả về Flux ở server. |
| Không nhận được phần tử nào | Nguồn chưa phát, filter loại bỏ hết dữ liệu hoặc stream rỗng. | Kiểm tra nguồn, filter và điều kiện đăng ký. |
| Client nhận lỗi khi tải tăng | Nguồn nóng phát nhanh hơn demand hoặc buffer vượt giới hạn. | Chọn chính sách buffer/drop/latest và đo tốc độ tiêu thụ. |
| Server tiếp tục làm việc sau khi client rời đi | Nguồn không phản ứng với cancellation hoặc handler đã tự subscribe. | Truyền cancellation tới nguồn và để framework quản lý Publisher trả về. |
| Dữ liệu bị lặp sau reconnect | Client đăng ký lại từ đầu hoặc server phát lại event. | Dùng cursor, sequence number hoặc event ID để deduplicate. |
| Stream tự timeout dù không có lỗi | Timeout ngắn hơn khoảng im lặng hợp lệ của nguồn. | Chọn timeout theo SLA hoặc bổ sung heartbeat. |

## 12. Ghi nhớ

- Request-stream gửi một payload yêu cầu ban đầu và nhận không hoặc nhiều payload phản hồi trên cùng stream.
- Trong Java, client thường nhận <code>Flux&lt;T&gt;</code>; Spring handler thường trả về <code>Flux&lt;T&gt;</code>.
- REQUEST_STREAM mở stream và mang initial demand; REQUEST_N yêu cầu thêm dữ liệu; CANCEL hủy stream.
- Backpressure điều tiết số phần tử được phát theo demand, nhưng không thay thế quota, rate limit hoặc chính sách buffer cho nguồn nóng.
- Cancellation cần được truyền tới nguồn để giải phóng listener và công việc không còn cần thiết.
- Reconnect tạo tương tác mới; muốn tiếp tục đúng vị trí cần cursor hoặc sequence nghiệp vụ, và có thể cần deduplication.
- Hãy kiểm thử cả dữ liệu, hoàn tất, lỗi, backpressure và cancellation bằng StepVerifier cùng integration test RSocket.
