# Backpressure qua REQUEST_N và nhu cầu nhận dữ liệu

RSocket hỗ trợ truyền dữ liệu dạng stream với cơ chế flow control dựa trên nhu cầu của bên nhận. Thay vì để producer gửi vô hạn, consumer cấp một lượng quyền nhận bằng frame REQUEST_N. Producer chỉ được gửi số payload trong phạm vi nhu cầu còn lại; khi consumer cần thêm dữ liệu, nó gửi REQUEST_N tiếp theo.

Trong Spring, cơ chế này được biểu diễn ở tầng ứng dụng bằng Reactive Streams: subscriber gọi request(n), Reactor truyền nhu cầu qua chuỗi publisher và RSocket chuyển nhu cầu đó thành flow-control trên kết nối. Vì vậy, cách subscribe và xử lý Flux ảnh hưởng trực tiếp đến tốc độ dữ liệu được phép truyền.

Cần phân biệt backpressure với rate limiting. Backpressure điều tiết số phần tử đang được phép truyền dựa trên khả năng nhận; rate limiting giới hạn tốc độ theo thời gian. Một consumer có thể yêu cầu 1.000 phần tử rồi nhận chúng rất nhanh. Nếu nghiệp vụ cần tối đa 20 yêu cầu mỗi giây, vẫn cần rate limiter riêng.

## 1. REQUEST_N là gì?

Trong Reactive Streams, subscriber thông báo số phần tử mà nó sẵn sàng nhận bằng Subscription.request(n). Publisher không được phát nhiều phần tử hơn tổng demand mà subscriber đã cấp.

RSocket đưa quy tắc đó qua mạng bằng flow-control frame:

- Với request-stream, frame REQUEST_STREAM mở stream và mang initial request N.
- Khi consumer cần thêm dữ liệu, nó gửi REQUEST_N để cộng thêm credit cho stream.
- Với request-channel, hai hướng dữ liệu có demand độc lập. Mỗi bên điều tiết lượng payload mà nó sẵn sàng nhận từ bên kia.
- Producer chỉ phát payload trong phạm vi credit hiện có. Khi credit cạn, producer phải chờ nhu cầu tiếp theo.

REQUEST_N mang ý nghĩa cấp thêm số lượng payload được phép gửi, không phải thiết lập lại một giới hạn tuyệt đối. Nếu consumer yêu cầu thêm 10 sau khi còn 3 credit, tổng credit còn lại trở thành 13.

Ví dụ một consumer ban đầu yêu cầu 2 phần tử, sau đó mỗi lần xử lý xong một phần tử lại yêu cầu thêm 1:

~~~text
Consumer -> REQUEST_STREAM(initialRequestN = 2)
Producer -> NEXT(item-1)
Producer -> NEXT(item-2)
Consumer -> REQUEST_N(1)
Producer -> NEXT(item-3)
Consumer -> REQUEST_N(1)
Producer -> NEXT(item-4)
~~~

Producer không được tự ý gửi item-3 trước khi có credit mới. Cơ chế này giúp giới hạn lượng dữ liệu đang chờ ở phía nhận và điều chỉnh tốc độ giữa hai đầu kết nối.

## 2. Những kiểu interaction có và không có REQUEST_N

Không phải mọi RSocket interaction đều tạo một stream cần cấp credit nhiều lần.

| Interaction model | Kết quả | Ý nghĩa của REQUEST_N |
|---|---|---|
| Fire-and-forget | Client gửi một payload, không nhận response stream | Không có luồng response để cấp demand |
| Request-response | Một request và tối đa một response | Không cần cửa sổ REQUEST_N cho chuỗi response |
| Request-stream | Một request mở ra nhiều response | Consumer cấp initial demand rồi gửi REQUEST_N bổ sung |
| Request-channel | Hai bên trao đổi các stream payload | Mỗi hướng có flow control riêng |

Nếu một API chỉ trả về một kết quả, dùng request-response thường đơn giản hơn. Nếu server cần phát nhiều event theo thời gian, request-stream phù hợp hơn. Nếu client cũng liên tục gửi dữ liệu trong khi nhận dữ liệu phản hồi, request-channel có thể phù hợp.

Không nên chọn request-stream chỉ vì muốn gửi nhiều lần. Hãy xác định rõ ai là producer của từng hướng, ai kiểm soát tốc độ nhận và liệu hai bên có cần stream đồng thời hay không.

## 3. Reactive Streams demand trong Spring

Spring RSocket tích hợp với Reactor và Reactive Streams. Ở phía server, một handler trả về Flux biểu diễn một luồng response. Ở phía client, retrieveFlux trả về Flux mà subscriber có thể điều khiển demand.

Cấu hình server TCP tối thiểu trong Spring Boot:

~~~properties
spring.rsocket.server.transport=tcp
spring.rsocket.server.port=7000
~~~

Thêm dependency Spring Boot RSocket starter tương ứng với phiên bản Spring Boot đang sử dụng:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-rsocket")
}
~~~

Một controller có thể trả về Flux:

~~~java
import reactor.core.publisher.Flux;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;

@Controller
public class QuoteController {

    private final QuoteService quoteService;

    public QuoteController(QuoteService quoteService) {
        this.quoteService = quoteService;
    }

    @MessageMapping("quotes.stream")
    public Flux<Quote> stream(QuoteRequest request) {
        return quoteService.streamQuotes(request.symbol())
            .doOnRequest(n ->
                System.out.println("Downstream requested: " + n)
            )
            .doOnCancel(() ->
                System.out.println("Quote stream cancelled")
            );
    }

    public record QuoteRequest(String symbol) {}

    public record Quote(String symbol, long sequence, double price) {}
}
~~~

Route quotes.stream được client gọi bằng RSocketRequester. Khi publisher phía server tuân thủ Reactive Streams, demand từ consumer được truyền ngược qua response stream. Khi consumer chưa yêu cầu thêm dữ liệu, publisher không được phát vượt quá demand.

doOnRequest chỉ quan sát số lượng demand đi qua vị trí operator đó. Giá trị có thể phản ánh batch hoặc prefetch của các operator trung gian, không nhất thiết tương ứng một frame REQUEST_N cho mỗi lời gọi request(n).

## 4. RSocketRequester và retrieveFlux

Spring cung cấp RSocketRequester để tạo request-response, request-stream, fire-and-forget và request-channel.

Một bean requester kết nối đến server TCP:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.rsocket.RSocketRequester;

@Configuration
public class RSocketClientConfig {

    @Bean
    RSocketRequester quoteRequester(RSocketRequester.Builder builder) {
        return builder.tcp("localhost", 7000);
    }
}
~~~

Client yêu cầu một stream quote:

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.core.publisher.Flux;

public class QuoteClient {

    private final RSocketRequester requester;

    public QuoteClient(RSocketRequester requester) {
        this.requester = requester;
    }

    public Flux<Quote> streamQuotes(String symbol) {
        return requester
            .route("quotes.stream")
            .data(new QuoteRequest(symbol))
            .retrieveFlux(Quote.class);
    }

    public record QuoteRequest(String symbol) {}

    public record Quote(String symbol, long sequence, double price) {}
}
~~~

retrieveFlux trả về một publisher. Tại thời điểm tạo Flux, client chưa nhất thiết đã tiêu thụ toàn bộ dữ liệu. Khi có subscriber và subscriber phát demand, RSocket client mới điều tiết việc nhận payload theo flow control.

Các API trả kết quả khác:

- retrieveMono(Type.class): request-response với một kết quả.
- retrieveFlux(Type.class): interaction trả về một stream.
- send(): fire-and-forget, không có response body.
- Với request-channel, RequestSpec nhận một Publisher làm dữ liệu đầu vào và retrieveFlux mô tả stream phản hồi.

Ví dụ request-channel:

~~~java
Flux<ChatReply> replies = requester
    .route("chat.channel")
    .data(outgoingMessages)
    .retrieveFlux(ChatReply.class);
~~~

Trong request-channel, outgoingMessages cũng là một publisher. Demand cho dữ liệu đi từ client đến server và demand cho response đi từ server đến client được điều tiết độc lập. Không nên giả định một phía yêu cầu thêm dữ liệu sẽ tự động tăng demand ở phía còn lại.

## 5. Consumer kiểm soát demand bằng BaseSubscriber

Các cách subscribe thông thường thường yêu cầu dữ liệu không giới hạn. Ví dụ subscribe() của Reactor sử dụng subscriber mặc định yêu cầu unbounded demand. Điều này tiện cho stream nhẹ, nhưng không phù hợp khi muốn xử lý từng batch hoặc giới hạn lượng công việc đang chờ.

BaseSubscriber cho phép tự quyết định thời điểm request thêm dữ liệu:

~~~java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;

public final class QuoteSubscriber extends BaseSubscriber<Quote> {

    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        request(2);
    }

    @Override
    protected void hookOnNext(Quote quote) {
        process(quote);

        // Chỉ yêu cầu thêm sau khi xử lý đồng bộ phần tử hiện tại.
        request(1);
    }

    @Override
    protected void hookOnError(Throwable throwable) {
        System.err.println("Quote stream failed: " + throwable.getMessage());
    }

    @Override
    protected void hookOnComplete() {
        System.out.println("Quote stream completed");
    }

    private void process(Quote quote) {
        System.out.println("Processing " + quote);
    }
}
~~~

Đăng ký subscriber:

~~~java
Disposable subscription = quoteClient
    .streamQuotes("ACME")
    .subscribeWith(new QuoteSubscriber());
~~~

Consumer bắt đầu với demand bằng 2. Sau khi xử lý một quote, nó yêu cầu thêm 1. Nếu xử lý chậm, producer sẽ phải chờ demand thay vì tiếp tục đẩy vô hạn phần tử.

Có một lưu ý quan trọng: nếu process chỉ gửi công việc sang executor rồi trả về ngay, request(1) tiếp theo không còn phản ánh việc công việc thực sự hoàn tất. Khi xử lý bất đồng bộ, chỉ cấp thêm demand khi có chỗ trống trong giới hạn concurrency hoặc khi tác vụ đã hoàn thành. Nếu không, queue công việc phía client vẫn có thể tăng không giới hạn dù đã dùng BaseSubscriber.

## 6. limitRate và điều tiết demand theo batch

Nếu không cần tự viết BaseSubscriber, Reactor cung cấp limitRate để chia demand upstream thành các đợt nhỏ hơn.

~~~java
quoteClient.streamQuotes("ACME")
    .limitRate(32)
    .subscribe(quote -> process(quote));
~~~

limitRate điều tiết lượng request mà operator gửi upstream theo batch. Nó hữu ích khi subscriber cuối yêu cầu nhiều dữ liệu nhưng ứng dụng muốn giới hạn lượng prefetch và lượng công việc có thể dồn lên các tầng phía trước.

limitRate không phải rate limiter theo giây. Nó kiểm soát request theo số lượng phần tử; nếu producer đáp ứng nhanh, 32 phần tử vẫn có thể đến trong thời gian rất ngắn. Muốn giới hạn tốc độ theo thời gian, cần thêm rate limiter.

Các operator khác có thể làm thay đổi cách demand truyền đi:

- **publishOn:** chuyển xử lý sang scheduler khác và có prefetch, do đó có thể có một lượng phần tử đang chờ trong hàng đợi.
- **buffer:** gom nhiều phần tử thành một batch; phải giới hạn kích thước buffer.
- **flatMap:** có thể chạy nhiều publisher con đồng thời; cần đặt concurrency và prefetch phù hợp.
- **concatMap:** xử lý publisher con tuần tự, thường dễ kiểm soát thứ tự và concurrency hơn.
- **limitRate:** chia nhỏ request upstream, giúp kiểm soát prefetch.

Khi phân tích backpressure, cần nhìn toàn bộ chuỗi operator từ subscriber đến source. Một operator có thể giữ phần tử trong buffer hoặc yêu cầu upstream nhiều hơn nhu cầu tức thời của đoạn code phía sau.

## 7. onBackpressureBuffer, Drop, Latest và Error

Một nguồn dữ liệu có thể phát độc lập với demand, ví dụ callback từ thư viện bên ngoài hoặc một event source dạng push. Khi đó ứng dụng cần chọn rõ cách xử lý nếu producer phát nhanh hơn consumer.

~~~java
Flux<Event> buffered = source
    .onBackpressureBuffer(1_000);

Flux<Event> latest = source
    .onBackpressureLatest();

Flux<Event> dropped = source
    .onBackpressureDrop();

Flux<Event> failOnOverflow = source
    .onBackpressureError();
~~~

Các lựa chọn có ngữ nghĩa khác nhau:

| Operator | Hành vi | Phù hợp với |
|---|---|---|
| onBackpressureBuffer(1000) | Giữ tối đa 1.000 phần tử chờ; overflow phát lỗi | Event cần giữ trong một khoảng ngắn, có giới hạn |
| onBackpressureDrop() | Bỏ phần tử đến khi downstream chưa có demand | Typing indicator, trạng thái tạm thời |
| onBackpressureLatest() | Giữ giá trị mới nhất, bỏ giá trị cũ đang chờ | Giá trị đo lường hoặc snapshot chỉ cần mới nhất |
| onBackpressureError() | Phát lỗi khi không thể đáp ứng demand | Luồng cần báo lỗi rõ thay vì âm thầm bỏ dữ liệu |

Các operator này tạo một chính sách xử lý chênh lệch tốc độ; chúng không thay thế flow control của RSocket. Một số operator backpressure chủ động yêu cầu upstream unbounded demand rồi tự buffer/drop ở phía ứng dụng. Khi đặt chúng trên RSocket stream, demand từ RSocket peer có thể bị che khuất bởi operator và dữ liệu được tích lại ở local buffer.

Nếu mục tiêu là để REQUEST_N thực sự phản ánh khả năng nhận của client, hãy giữ chuỗi publisher demand-aware và tránh đặt một operator chuyển thành unbounded request ở giữa mà không có lý do. Nếu cần buffer, luôn đặt dung lượng hữu hạn, chọn hành vi overflow và theo dõi số phần tử bị bỏ hoặc lỗi.

Không dùng onBackpressureDrop hoặc onBackpressureLatest cho lệnh thanh toán, cập nhật trạng thái đơn hàng hoặc event audit nếu mất một phần tử sẽ làm sai nghiệp vụ. Những loại dữ liệu đó cần lưu trữ bền vững và retry/acknowledgement phù hợp.

## 8. Phân biệt backpressure với buffering và rate limiting

Ba khái niệm này thường bị nhầm lẫn:

- **Backpressure:** consumer cấp demand; producer chỉ được gửi trong giới hạn demand còn lại.
- **Buffering:** lưu tạm phần tử khi producer và consumer lệch tốc độ; buffer hữu hạn cần chính sách overflow.
- **Rate limiting:** giới hạn số lượng phần tử hoặc request trong một đơn vị thời gian.

Ví dụ consumer có thể yêu cầu 100 phần tử cùng lúc. Nếu server phát nhanh, 100 phần tử đó có thể đến trong vài mili giây. Backpressure vẫn hoạt động đúng vì producer không vượt quá demand, nhưng ứng dụng có thể cần rate limiting để tránh một burst quá lớn.

Ngược lại, rate limit 10 message/giây không tự giới hạn số phần tử đang nằm trong queue nếu consumer xử lý chậm. Cần kết hợp demand, buffer hữu hạn, giới hạn concurrency và rate limit theo mục tiêu.

## 9. REQUEST_N có phải luôn tương ứng một request(n)?

Không nên giả định mỗi lời gọi request(n) trong code sẽ tạo ra đúng một frame REQUEST_N trên mạng. Reactor và RSocket có thể gộp demand, phát initial request N khi mở stream hoặc chia demand thành các batch. Các operator như limitRate, publishOn hoặc flatMap cũng có thể tạo prefetch.

Điều quan trọng ở tầng giao thức là tổng credit được cấp và số payload đã được gửi không vượt quá credit còn lại. REQUEST_N bổ sung credit; nó không yêu cầu producer gửi ngay đúng N phần tử nếu source chưa có dữ liệu.

Ví dụ subscriber gọi request(1) nhiều lần. RSocket implementation có thể tối ưu việc truyền demand thành các batch phù hợp. Vì vậy, khi debug nên quan sát tổng demand, số payload và trạng thái stream thay vì viết test phụ thuộc số frame REQUEST_N chính xác cho từng lần gọi API.

## 10. Hủy stream và giải phóng tài nguyên

Khi consumer không còn cần dữ liệu, nó có thể cancel subscription. Với RSocket stream, việc hủy stream được truyền đến peer bằng cơ chế cancel tương ứng của protocol. Producer nên dừng việc tạo dữ liệu và giải phóng tài nguyên liên quan.

~~~java
Disposable subscription = quoteClient
    .streamQuotes("ACME")
    .subscribe(this::processQuote);

// Khi màn hình hoặc tác vụ kết thúc:
subscription.dispose();
~~~

Ở phía server, có thể theo dõi cancel để đóng resource:

~~~java
@MessageMapping("quotes.stream")
public Flux<Quote> stream(QuoteRequest request) {
    return quoteService.streamQuotes(request.symbol())
        .doOnCancel(() -> quoteService.release(request.symbol()));
}
~~~

Nếu source dùng listener hoặc subscription đến hệ thống ngoài, cần gắn cleanup vào doFinally hoặc cơ chế dispose tương ứng để cả cancel, complete và error đều giải phóng tài nguyên. Không giữ một publisher vô hạn cho mỗi client sau khi session đã đóng.

## 11. Kiểm thử demand với StepVerifier

StepVerifier cho phép điều khiển demand của subscriber trong test. Có thể bắt đầu với initial request bằng 0 rồi tăng demand từng bước:

~~~java
import java.time.Duration;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class BackpressureTest {

    @Test
    void emitsOnlyWhenDemandIsGranted() {
        Flux<Integer> source = Flux.range(1, 5);

        StepVerifier.create(source, 0)
            .thenRequest(2)
            .expectNext(1, 2)
            .thenRequest(1)
            .expectNext(3)
            .thenRequest(2)
            .expectNext(4, 5)
            .verifyComplete();
    }
}
~~~

Test này chứng minh publisher tuân thủ demand trong Reactive Streams. Nó chưa chứng minh RSocket đã gửi một chuỗi REQUEST_N cụ thể qua socket.

Để kiểm thử tích hợp RSocket, dùng RSocketRequester thật kết nối đến server, yêu cầu một route trả Flux và dùng StepVerifier với initial request bằng 0:

~~~java
StepVerifier.create(
        requester.route("quotes.stream")
            .data(new QuoteRequest("ACME"))
            .retrieveFlux(Quote.class),
        0
    )
    .thenRequest(2)
    .expectNextCount(2)
    .thenRequest(3)
    .expectNextCount(3)
    .thenCancel()
    .verify(Duration.ofSeconds(5));
~~~

Test tích hợp này xác minh stream qua RSocket chỉ phát dữ liệu khi consumer cấp demand. Nếu cần điều tra frame REQUEST_N ở tầng wire, cần bật logging/tracing frame của RSocket hoặc dùng công cụ quan sát protocol. Không suy ra số frame chỉ từ số lần gọi request(n).

## 12. Các tình huống cần kiểm tra trong production

- Subscriber xử lý chậm trong khi server phát dữ liệu liên tục.
- Client tạm dừng demand rồi tiếp tục request sau một khoảng thời gian.
- Client cancel stream khi server đang tạo dữ liệu.
- Source là cold publisher có thể tạo theo demand so với hot source phát độc lập.
- Một operator trung gian vô tình tạo unbounded demand hoặc prefetch lớn.
- Buffer đầy và overflow theo đúng chính sách đã chọn.
- Request-channel có hai hướng dữ liệu với demand riêng.
- Client reconnect phải tạo stream mới và khôi phục vị trí đọc nếu nghiệp vụ yêu cầu.
- Một consumer yêu cầu demand rất lớn; server vẫn phải kiểm soát chi phí xử lý và fan-out.
- Các stream vô hạn cần cleanup khi cancel, error hoặc session đóng.

Với stream dài hạn, nên có sequence number hoặc cursor nếu client cần tiếp tục từ vị trí đã nhận sau reconnect. Backpressure chỉ điều tiết dữ liệu trong một stream đang hoạt động; nó không lưu lại phần tử đã phát khi kết nối bị mất.

## 13. Checklist chẩn đoán backpressure

- API đang dùng request-stream hay request-channel? Có đúng là interaction cần nhiều response không?
- Client đang dùng subscribe() mặc định hay một subscriber tự kiểm soát request(n)?
- Initial demand được cấp bao nhiêu? Khi nào consumer yêu cầu thêm?
- Publisher phía server có thực sự tôn trọng Reactive Streams demand không?
- Có operator nào buffer, drop hoặc request upstream unbounded không?
- limitRate, publishOn, flatMap có prefetch/concurrency vượt khả năng xử lý không?
- Với request-channel, demand của hai hướng đã được xem xét độc lập chưa?
- Cancel có truyền đến source và giải phóng resource không?
- Test đang kiểm tra Reactive Streams demand hay đang khẳng định một số frame REQUEST_N cụ thể?
- Khi reconnect, ứng dụng có cơ chế đồng bộ lại dữ liệu đã bỏ lỡ không?

REQUEST_N là cơ chế flow control ở tầng RSocket protocol; request(n) là cách consumer thể hiện nhu cầu trong Reactive Streams. Spring và Reactor nối hai tầng này để producer biết khi nào có thể gửi thêm dữ liệu. Khi thiết kế stream, hãy kiểm soát demand ở consumer, tránh buffer không giới hạn, chọn chính sách cho nguồn push và kiểm thử riêng cả hành vi Reactive Streams lẫn tích hợp RSocket qua mạng.