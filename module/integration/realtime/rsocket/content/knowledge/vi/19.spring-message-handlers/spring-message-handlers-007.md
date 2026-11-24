# Xử lý request-stream với Flux và request-channel với Publisher đầu vào

Trong Spring RSocket, kiểu dữ liệu đầu vào và đầu ra của phương thức @MessageMapping giúp biểu diễn kiểu tương tác RSocket. Khi server cần nhận một request rồi phát nhiều response, phương thức handler thường trả về Flux. Khi server cần nhận một luồng request từ client và đồng thời phát một luồng response về client, handler nhận một Publisher ở tham số đầu vào và trả về Publisher, thường là Flux.

Hai kiểu tương tác này đều sử dụng Reactive Streams, nhưng giải quyết hai nhu cầu khác nhau:

- Request-stream: client gửi một request ban đầu; server trả về một luồng gồm nhiều phần tử.
- Request-channel: client gửi một luồng phần tử request; server có thể phát một luồng response trong khi luồng request vẫn đang tiếp tục.

Bài này dùng ví dụ theo dõi giá và thu thập dữ liệu cảm biến để minh họa cách Spring ánh xạ hai kiểu tương tác đó, cách client gọi bằng RSocketRequester, cũng như cách kiểm soát backpressure, cancellation và lỗi.

## 1. Flux và Publisher trong Spring RSocket

Flux là kiểu publisher của Project Reactor, có thể phát không, một hoặc nhiều phần tử rồi kết thúc bằng complete hoặc error. Publisher là interface Reactive Streams mô tả một nguồn dữ liệu bất đồng bộ có thể phát nhiều phần tử theo nhu cầu của subscriber.

Trong Spring RSocket:

- Dùng Flux ở kiểu trả về khi handler cần phát nhiều response.
- Dùng Publisher<T> hoặc Flux<T> ở tham số đầu vào khi handler nhận một luồng request.
- Dùng Mono<T> khi handler trả tối đa một kết quả.
- Spring và RSocket chuyển đổi payload thành kiểu Java thông qua các codec trong RSocketStrategies.

Publisher là abstraction tổng quát; Flux là một implementation cụ thể có thêm các toán tử như map, concatMap, filter và onErrorResume. Nhận Publisher ở tham số giúp handler không phụ thuộc trực tiếp vào Reactor, trong khi chuyển sang Flux.from(...) cho phép sử dụng các toán tử Reactor khi cần.

## 2. Request-stream: một request mở một luồng response

Request-stream phù hợp khi client chỉ cần gửi một thông tin truy vấn, sau đó server liên tục phát dữ liệu. Ví dụ, client gửi mã chứng khoán và server trả các lần cập nhật giá mới.

~~~mermaid
sequenceDiagram
    participant C as RSocket client
    participant S as Spring RSocket server
    participant P as Price service
    C->>S: REQUEST_STREAM prices.watch
    Note over C,S: Một payload PriceRequest
    S->>P: watch(symbol)
    loop Mỗi lần có cập nhật
        P-->>S: PriceUpdate
        S-->>C: PAYLOAD
    end
    Note over C,S: Luồng kết thúc khi nguồn complete hoặc lỗi
~~~

Handler nhận một đối tượng request bình thường và trả về Flux:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

@Controller
public class PriceController {

    private final PriceService priceService;

    public PriceController(PriceService priceService) {
        this.priceService = priceService;
    }

    @MessageMapping("prices.watch")
    public Flux<PriceUpdate> watch(PriceRequest request) {
        return priceService.watch(request.symbol());
    }
}
~~~

PriceRequest là một payload đơn, chẳng hạn chứa symbol = ACME. PriceService.watch(...) trả về Flux<PriceUpdate> và có thể phát dữ liệu từ event source, message broker hoặc một publisher khác. Mỗi phần tử được gửi về client như một response trong cùng request-stream.

Phía client dùng RSocketRequester gửi một request rồi nhận Flux:

~~~java
Flux<PriceUpdate> updates = requester
    .route("prices.watch")
    .data(new PriceRequest("ACME"))
    .retrieveFlux(PriceUpdate.class);
~~~

Publisher updates là lazy. Dữ liệu chỉ bắt đầu được tiêu thụ khi có subscriber. Trong một ứng dụng reactive, có thể ghép publisher này vào pipeline giao diện hoặc service; không cần block để lấy toàn bộ dữ liệu.

Request-stream không nhận một Publisher request ở phía server. Nó nhận một request ban đầu duy nhất. Nếu cần client tiếp tục gửi dữ liệu trong khi server phát response, hãy dùng request-channel.

## 3. Request-channel: một luồng request và một luồng response

Request-channel dùng khi cả hai phía đều cần phát nhiều phần tử trong cùng một tương tác. Client gửi một Publisher request; server nhận publisher đó, xử lý các phần tử và trả về một Publisher response.

Ví dụ, một thiết bị gửi liên tục các mẫu cảm biến lên server. Server kiểm tra từng mẫu và phát kết quả xử lý hoặc cảnh báo về client trong khi thiết bị vẫn tiếp tục gửi dữ liệu.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Spring RSocket handler
    participant P as Telemetry service
    C->>S: REQUEST_CHANNEL
    loop Client gửi dữ liệu
        C->>S: PAYLOAD TelemetrySample
        S->>P: evaluate(sample)
        P-->>S: TelemetryReply
        S-->>C: PAYLOAD TelemetryReply
    end
    Note over C,S: Hai hướng có thể tiếp tục trao đổi độc lập
    C->>S: Hoàn tất luồng request
    S-->>C: Hoàn tất luồng response khi xử lý xong
~~~

Trong Spring, tham số Publisher cho biết handler nhận một luồng payload đầu vào. Kiểu trả về Flux biểu diễn luồng payload đầu ra:

~~~java
import org.reactivestreams.Publisher;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

@Controller
public class TelemetryController {

    private final TelemetryService telemetryService;

    public TelemetryController(TelemetryService telemetryService) {
        this.telemetryService = telemetryService;
    }

    @MessageMapping("telemetry.channel")
    public Flux<TelemetryReply> channel(
        Publisher<TelemetrySample> samples
    ) {
        return Flux.from(samples)
            .concatMap(telemetryService::evaluate);
    }
}
~~~

TelemetrySample là một phần tử request, ví dụ gồm deviceId, sequence và temperature. TelemetryService.evaluate(...) trả về Mono<TelemetryReply>. concatMap gọi service cho từng mẫu theo thứ tự và phát kết quả tương ứng vào luồng response.

Service có thể khai báo một contract reactive đơn giản:

~~~java
import reactor.core.publisher.Mono;

public interface TelemetryService {
    Mono<TelemetryReply> evaluate(TelemetrySample sample);
}
~~~

Vì phương thức trả về Flux, response có thể được phát dần khi từng phần tử đầu vào được xử lý xong. Client không cần hoàn tất toàn bộ luồng request trước rồi mới nhận tất cả kết quả. Điều này giúp xây dựng tương tác hai chiều liên tục.

## 4. Client gửi Publisher và nhận Flux bằng RSocketRequester

Client tạo một publisher các mẫu cảm biến, sau đó gửi publisher đó làm dữ liệu đầu vào của request-channel:

~~~java
import reactor.core.publisher.Flux;

Flux<TelemetrySample> samples = Flux.just(
    new TelemetrySample("device-7", 1, 26.4),
    new TelemetrySample("device-7", 2, 27.1),
    new TelemetrySample("device-7", 3, 31.8)
);

Flux<TelemetryReply> replies = requester
    .route("telemetry.channel")
    .data(samples, TelemetrySample.class)
    .retrieveFlux(TelemetryReply.class);
~~~

Ở đây:

- data(samples, TelemetrySample.class) cung cấp luồng request đầu vào. Class phần tử giúp Spring chọn cách encode payload.
- retrieveFlux(TelemetryReply.class) khai báo kiểu phần tử response mà client muốn nhận.
- Cả request publisher và response Flux đều được tiêu thụ theo subscription và demand.

Để quan sát kết quả trong một chương trình thử nghiệm:

~~~java
replies
    .doOnNext(System.out::println)
    .doOnError(error -> log.error("Telemetry channel failed", error))
    .blockLast();
~~~

blockLast() chỉ tiện cho ví dụ chạy đồng bộ hoặc test. Trong luồng xử lý reactive của ứng dụng, hãy subscribe ở ranh giới phù hợp hoặc ghép replies vào pipeline. Không gọi blockLast() trên event-loop thread.

## 5. So sánh request-stream và request-channel

| Tiêu chí | Request-stream | Request-channel |
|---|---|---|
| Payload đầu vào | Một request | Một luồng request |
| Kiểu tham số handler | DTO hoặc payload đơn | Publisher<T> hoặc Flux<T> |
| Kiểu trả về handler | Flux<T> khi có nhiều response | Publisher<R> hoặc Flux<R> cho response stream |
| Chiều dữ liệu | Một request, nhiều response | Nhiều request và nhiều response |
| Khi nào phù hợp | Theo dõi giá, nhận log, đọc sự kiện | Telemetry hai chiều, xử lý lô liên tục, trao đổi tương tác |
| API client | data(request).retrieveFlux(...) | data(publisher, Element.class).retrieveFlux(...) |

Một cách kiểm tra nhanh khi đọc handler:

- Tham số đầu vào là một DTO đơn và kết quả là Flux: thường là request-stream.
- Tham số đầu vào là Publisher<T> và kết quả là Flux<R>: request-channel.
- Tham số đầu vào là DTO đơn và kết quả là Mono<R>: thường là request-response.

Việc chọn kiểu tương tác cần xuất phát từ hợp đồng dữ liệu. Không nên dùng request-channel chỉ vì server trả nhiều response; nếu client chỉ gửi một request ban đầu, request-stream đơn giản và rõ nghĩa hơn.

## 6. Publisher đầu vào là luồng lazy

Publisher không nhất thiết phát dữ liệu ngay khi được tạo. Ví dụ Flux.fromIterable(...), Flux.interval(...) hoặc publisher từ message broker chỉ thực thi khi có subscriber. Spring/RSocket đăng ký với publisher đầu vào khi tương tác channel bắt đầu.

Trong handler, nên biến đổi Publisher thành pipeline trả về:

~~~java
@MessageMapping("telemetry.channel")
public Flux<TelemetryReply> channel(
    Publisher<TelemetrySample> samples
) {
    return Flux.from(samples)
        .filter(this::isValid)
        .concatMap(telemetryService::evaluate);
}
~~~

Không gọi subscribe() thủ công bên trong handler:

~~~java
// Không nên: tạo một subscription tách rời khỏi vòng đời RSocket.
Flux.from(samples).subscribe(telemetryService::process);
return Flux.empty();
~~~

Nếu tự subscribe rồi trả Flux.empty(), Spring không còn quản lý được quan hệ giữa stream request, stream response, cancellation và lỗi của pipeline con. Công việc có thể tiếp tục chạy sau khi client đã ngắt kết nối, và lỗi có thể không được truyền về đúng peer. Hãy trả publisher đã được compose để framework quản lý subscription.

## 7. Backpressure khi nhận và phát nhiều phần tử

Reactive Streams dùng demand để subscriber yêu cầu số phần tử mà nó có thể tiếp nhận. Với request-channel, cơ chế này áp dụng cho cả luồng request và luồng response:

- Client điều tiết số mẫu gửi tới server bằng demand của publisher đầu vào.
- Server điều tiết số response phát về client theo demand ở chiều response.
- Các toán tử như concatMap và flatMap có thể tạo hàng đợi hoặc concurrency; cần chọn cấu hình phù hợp với năng lực xử lý.

concatMap xử lý tuần tự và giữ thứ tự kết quả, phù hợp khi mỗi mẫu cần được xử lý lần lượt hoặc trạng thái nghiệp vụ phụ thuộc phần tử trước. Nếu xử lý độc lập và cần tăng throughput, có thể dùng flatMap với concurrency giới hạn:

~~~java
@MessageMapping("telemetry.channel")
public Flux<TelemetryReply> channel(
    Publisher<TelemetrySample> samples
) {
    return Flux.from(samples)
        .flatMap(telemetryService::evaluate, 8);
}
~~~

Giá trị 8 là giới hạn concurrency minh họa, không phải mặc định tối ưu. flatMap có thể phát kết quả không theo thứ tự đầu vào vì các tác vụ hoàn tất ở thời điểm khác nhau. Nếu thứ tự quan trọng, dùng concatMap hoặc thiết kế sequence number để client sắp xếp/kiểm tra.

Backpressure không tự giới hạn mọi bộ đệm trong ứng dụng. Một service có thể tạo hàng đợi không giới hạn hoặc tích lũy dữ liệu ở ngoài Reactive Streams. Cần kiểm tra các nguồn dữ liệu, scheduler, buffer và giới hạn concurrency trên toàn pipeline.

## 8. Cancellation và vòng đời channel

Một channel có thể kết thúc khi client hoàn tất luồng request và server hoàn tất luồng response. Một phía cũng có thể hủy tương tác trước khi cả hai luồng hoàn tất.

Ví dụ, người dùng rời màn hình telemetry và client hủy subscription. RSocket có thể gửi tín hiệu CANCEL để yêu cầu server dừng stream tương ứng. Pipeline phía server nên truyền cancellation tới nguồn dữ liệu hoặc tác vụ bên dưới.

Với Flux.from(samples).concatMap(...), cancellation của subscriber được truyền qua pipeline Reactor. Nếu telemetryService gọi một hệ thống bên ngoài không hỗ trợ cancellation, ứng dụng cần có timeout hoặc cơ chế dừng riêng để tránh tiếp tục tiêu tốn tài nguyên.

Không nhầm cancellation với complete bình thường:

- Complete: publisher kết thúc tự nhiên sau khi phát xong dữ liệu.
- Cancel: subscriber không còn muốn nhận dữ liệu và yêu cầu dừng subscription.
- Error: publisher kết thúc do lỗi; lỗi được truyền qua stream tương ứng.

## 9. Xử lý lỗi trong request-stream và request-channel

Lỗi từ service nghiệp vụ có thể kết thúc stream tương ứng. Với request-stream, lỗi thường kết thúc luồng response. Với request-channel, lỗi trong pipeline xử lý đầu vào hoặc phát response cũng có thể làm channel kết thúc.

Có thể xử lý lỗi đã biết bằng onErrorResume, nhưng chỉ nên chuyển lỗi thành dữ liệu khi hợp đồng ứng dụng định nghĩa rõ điều đó:

~~~java
import org.reactivestreams.Publisher;
import org.springframework.messaging.handler.annotation.MessageMapping;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@MessageMapping("telemetry.channel")
public Flux<TelemetryReply> channel(
    Publisher<TelemetrySample> samples
) {
    return Flux.from(samples)
        .concatMap(sample ->
            telemetryService.evaluate(sample)
                .onErrorResume(error ->
                    Mono.just(TelemetryReply.failed(
                        sample.deviceId(),
                        sample.sequence(),
                        "PROCESSING_FAILED"
                    ))
                )
        );
}
~~~

Trong ví dụ, TelemetryReply.failed(...) là factory method do ứng dụng định nghĩa. Nó biến lỗi xử lý một mẫu thành một response nghiệp vụ có sequence tương ứng. Nếu lỗi làm session hoặc transport không thể tiếp tục, không nên che giấu lỗi bằng response giả. Cần để lỗi truyền tới RSocket và để client quyết định phục hồi.

Client có thể áp dụng timeout cho response stream:

~~~java
import java.time.Duration;

Flux<TelemetryReply> replies = requester
    .route("telemetry.channel")
    .data(samples, TelemetrySample.class)
    .retrieveFlux(TelemetryReply.class)
    .timeout(Duration.ofSeconds(10));
~~~

Timeout là chính sách phía client. Với timeout(Duration) trên Flux, thời gian chờ được tính lại giữa các tín hiệu; nó thường dùng để phát hiện luồng im lặng quá lâu, không phải deadline tổng cho toàn bộ channel. Khi hết hạn, subscription kết thúc và tương tác có thể bị hủy. Không suy luận rằng server chưa xử lý các mẫu đã gửi; nếu xử lý có tác dụng phụ, hãy dùng sequence hoặc idempotency để tránh áp dụng lặp khi client kết nối lại.

## 10. DTO và message conversion

Payload đầu vào và đầu ra cần có hợp đồng rõ ràng. Ví dụ:

~~~java
public record TelemetrySample(
    String deviceId,
    long sequence,
    double temperature
) {
}

public record TelemetryReply(
    String deviceId,
    long sequence,
    String status,
    String message
) {
    public static TelemetryReply failed(
        String deviceId,
        long sequence,
        String code
    ) {
        return new TelemetryReply(
            deviceId,
            sequence,
            code,
            "Không thể xử lý mẫu dữ liệu"
        );
    }
}
~~~

Spring dùng message codec trong RSocketStrategies để chuyển payload thành DTO và encode response. Client và server phải thống nhất MIME type, codec và schema. Nếu một phía gửi JSON nhưng phía kia mong đợi định dạng khác, lỗi giải mã có thể xảy ra trước khi logic handler chạy.

Với stream dài, mỗi phần tử nên mang sequence hoặc timestamp để client phát hiện phần tử trùng, sai thứ tự hoặc bị bỏ lỡ. Nếu cần tiếp tục sau reconnect, cursor nghiệp vụ nên được thiết kế riêng; request-channel không tự cung cấp khả năng lưu lịch sử hay replay.

## 11. Kiểm thử handler với StepVerifier

Có thể kiểm tra logic stream mà không cần mở transport bằng cách gọi publisher do handler trả về:

~~~java
import org.reactivestreams.Publisher;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class TelemetryControllerTest {

    @Test
    void shouldProcessEachIncomingSample() {
        TelemetryService service = sample -> Mono.just(
            new TelemetryReply(
                sample.deviceId(),
                sample.sequence(),
                "ACCEPTED",
                "Sample processed"
            )
        );
        TelemetryController controller = new TelemetryController(service);

        Publisher<TelemetrySample> input = Flux.just(
            new TelemetrySample("device-7", 1, 26.4),
            new TelemetrySample("device-7", 2, 31.8)
        );

        StepVerifier.create(controller.channel(input))
            .expectNextMatches(reply ->
                reply.sequence() == 1
            )
            .expectNextMatches(reply ->
                reply.sequence() == 2
            )
            .verifyComplete();
    }
}
~~~

Test dùng một implementation đơn giản của TelemetryService để trả Mono<TelemetryReply> tương ứng với từng mẫu. Trong kiểm thử tích hợp, hãy khởi chạy RSocket server và dùng RSocketRequester để xác nhận route, codec, request-channel và response stream hoạt động qua transport thật.

Các tình huống nên kiểm thử:

1. Publisher đầu vào phát nhiều phần tử rồi complete; server phát response tương ứng và complete.
2. Publisher đầu vào phát error; xác nhận lỗi được truyền tới tương tác hoặc được chuyển đổi theo hợp đồng.
3. Client hủy response subscription; xác nhận công việc phía server được cancellation khi nguồn hỗ trợ.
4. Client gửi nhiều phần tử với demand giới hạn; xác nhận hệ thống không tích lũy hàng đợi không giới hạn.
5. Một phần tử xử lý chậm; xác nhận concatMap giữ thứ tự hoặc flatMap concurrency hoạt động đúng theo thiết kế.
6. MIME type hoặc schema không khớp; xác nhận lỗi decode được quan sát và ghi log đúng tầng.

## 12. Lỗi thường gặp khi khai báo handler

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Handler chỉ nhận một DTO nhưng mong nhiều request | Đang khai báo request-stream thay vì request-channel | Nhận Publisher<T> ở tham số |
| Client gửi Publisher nhưng handler không map được payload | Thiếu kiểu phần tử hoặc codec không phù hợp | Khai báo generic type cụ thể và cấu hình RSocketStrategies |
| Handler không phát response khi client vẫn gửi dữ liệu | Publisher đầu ra chỉ được tạo sau khi chờ toàn bộ input hoặc có thao tác block | Compose pipeline reactive và phát kết quả dần |
| Dữ liệu phản hồi sai thứ tự | Dùng flatMap với tác vụ hoàn tất không đồng đều | Dùng concatMap hoặc sequence để sắp xếp |
| Công việc tiếp tục sau khi client ngắt | Tự subscribe trong handler hoặc nguồn không hỗ trợ cancellation | Trả publisher đã compose và quản lý tài nguyên nguồn |
| Bộ nhớ tăng khi tải lớn | Buffer hoặc concurrency không giới hạn | Giới hạn demand, buffer, concurrency và kích thước payload |

## 13. Chọn đúng kiểu tương tác

Hãy chọn request-stream khi client có một điều kiện truy vấn ổn định và chỉ cần server phát dữ liệu liên tục. Ví dụ: client gửi mã sản phẩm rồi nhận giá thay đổi.

Hãy chọn request-channel khi client cần tiếp tục gửi dữ liệu trong lúc server trả kết quả. Ví dụ: thiết bị gửi mẫu cảm biến liên tục và nhận cảnh báo cho từng mẫu; một phiên phân tích tương tác gửi từng phần đầu vào và nhận kết quả từng phần.

Nếu dữ liệu đầu vào là một luồng lớn nhưng server chỉ cần trả một response cuối cùng, có thể cân nhắc request-channel với response đơn hoặc một kiểu tương tác khác phù hợp với hợp đồng. Điều quan trọng là xác định rõ hai phía cần phát dữ liệu bao lâu, response có thể xuất hiện trước khi input hoàn tất hay không, và cách xử lý cancellation/lỗi.

## 14. Kết luận

Trong Spring RSocket, Flux ở kiểu trả về cho phép handler phát nhiều response. Request-stream thường nhận một DTO đơn và trả Flux. Request-channel nhận một Publisher đầu vào và trả một Publisher/Flux đầu ra, cho phép hai phía trao đổi nhiều phần tử trong cùng tương tác.

Hãy compose Publisher đầu vào thành pipeline reactive, tránh tự subscribe trong handler, chọn concatMap hoặc flatMap theo yêu cầu thứ tự và concurrency, đồng thời kiểm thử backpressure, cancellation và lỗi. Khi hợp đồng DTO, codec và vòng đời stream được xác định rõ, request-stream và request-channel trở thành nền tảng tốt cho các ứng dụng realtime hai chiều.
