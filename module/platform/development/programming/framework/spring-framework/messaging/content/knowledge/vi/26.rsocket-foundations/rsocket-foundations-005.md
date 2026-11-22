# Request-stream và nhiều phần tử phản hồi

RSocket hỗ trợ nhiều kiểu tương tác. Với **Request-Stream**, requester gửi một request payload và responder trả về một luồng gồm không, một hoặc nhiều response payload. Trong Spring, responder thường khai báo method **@MessageMapping** trả về **Flux<T>**, còn requester dùng **RSocketRequester.retrieveFlux(...)** để nhận các phần tử.

Điểm quan trọng của Request-Stream là luồng có backpressure: requester báo số phần tử mình sẵn sàng nhận, responder phải tôn trọng demand đó. Nhờ vậy ứng dụng có thể truyền dữ liệu lớn hoặc dữ liệu liên tục mà không phải gom toàn bộ kết quả thành một List trong bộ nhớ.

## 1. Request-Stream là gì?

RSocket định nghĩa bốn interaction model chính:

| Interaction | Request từ requester | Response từ responder | Dùng khi |
| --- | --- | --- | --- |
| Request-Response | Một payload | Một payload | Truy vấn một kết quả |
| Request-Stream | Một payload | Một stream payload | Một yêu cầu trả về nhiều kết quả |
| Request-Channel | Một stream payload | Một stream payload | Hai phía vừa gửi vừa nhận nhiều phần tử |
| Fire-and-Forget | Một payload | Không có response payload | Gửi thông báo một chiều |

Request-Stream không phải là nhiều request độc lập. Requester gửi một request ban đầu, ví dụ “lấy các số đo của thiết bị A”, rồi responder phát các phần tử kết quả thành một stream. Nếu requester muốn gửi thêm nhiều phần tử request trong khi nhận stream phản hồi, interaction phù hợp là Request-Channel.

Trong Spring, kiểu dữ liệu phản ánh cardinality:

- **Mono<T>** biểu diễn tối đa một giá trị bất đồng bộ.
- **Flux<T>** biểu diễn một chuỗi có thể có nhiều giá trị bất đồng bộ.
- **Mono<Void>** biểu diễn hoàn tất mà không có response payload.
- Giá trị thông thường biểu diễn một payload đồng bộ.

Một method nhận một request object và trả về Flux thường được ánh xạ thành Request-Stream.

## 2. Cách Spring ánh xạ @MessageMapping thành Request-Stream

Ví dụ responder nhận yêu cầu theo dõi thiết bị và trả về nhiều lần đo:

~~~java
package com.example.rsocket;

import java.time.Instant;

public record WatchRequest(String deviceId) {
}

public record SensorReading(
        String deviceId,
        long sequence,
        Instant measuredAt,
        double value) {
}
~~~

Service cung cấp một Flux:

~~~java
package com.example.rsocket;

import reactor.core.publisher.Flux;

public interface SensorService {
    Flux<SensorReading> streamReadings(String deviceId);
}
~~~

Responder dùng **@MessageMapping**:

~~~java
package com.example.rsocket;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

@Controller
public class SensorRSocketController {

    private final SensorService sensorService;

    public SensorRSocketController(SensorService sensorService) {
        this.sensorService = sensorService;
    }

    @MessageMapping("sensor.watch")
    public Flux<SensorReading> watch(
            @Payload WatchRequest request) {

        return sensorService.streamReadings(request.deviceId());
    }
}
~~~

Method nhận một **WatchRequest** và trả về **Flux<SensorReading>**. Spring suy ra đây là Request-Stream dựa trên số lượng phần tử đầu vào và đầu ra. Mỗi phần tử do Flux phát ra được tuần tự hóa thành một response payload trên cùng logical RSocket stream.

Route trong ví dụ là **sensor.watch**. RSocket route là metadata, không phải HTTP URL; Spring mặc định dùng dấu chấm làm route separator. Client phải gọi đúng route này.

## 3. Cấu hình codec cho DTO

Các ví dụ trên trao đổi object Java như WatchRequest và SensorReading. Để gửi và nhận DTO, requester và responder cần Encoder/Decoder tương ứng. Đây là điểm quan trọng khi dùng Spring Framework trực tiếp.

RSocketStrategies mặc định của Spring Framework chỉ đăng ký các codec cơ bản cho String, byte[] và ByteBuffer. Nếu dùng DTO, hãy thêm codec JSON hoặc CBOR phù hợp. Với Jackson JSON, cấu hình có thể như sau:

~~~java
package com.example.rsocket;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
import org.springframework.messaging.rsocket.RSocketMessageHandler;
import org.springframework.messaging.rsocket.RSocketStrategies;

@Configuration
public class RSocketCodecConfiguration {

    @Bean
    public RSocketStrategies rsocketStrategies() {
        return RSocketStrategies.builder()
                .encoders(encoders -> encoders.add(new Jackson2JsonEncoder()))
                .decoders(decoders -> decoders.add(new Jackson2JsonDecoder()))
                .build();
    }

    @Bean
    public RSocketMessageHandler rsocketMessageHandler(
            RSocketStrategies strategies) {
        RSocketMessageHandler handler = new RSocketMessageHandler();
        handler.setRSocketStrategies(strategies);
        return handler;
    }
}
~~~

Các lớp Jackson codec thuộc module spring-web. Ứng dụng Spring Framework thuần cần dependency spring-web cùng Jackson phù hợp. Nếu dùng Spring Boot, starter **spring-boot-starter-rsocket** cung cấp các dependency cần thiết và auto-configure RSocketStrategies; Boot thử đăng ký codec CBOR với Jackson rồi JSON với Jackson theo thứ tự. Khi tùy biến strategies, bảo đảm cả requester và responder dùng codec tương thích và MIME type phù hợp.

Requester dùng cùng strategies khi kết nối:

~~~java
RSocketRequester requester = RSocketRequester.builder()
        .rsocketStrategies(strategies)
        .tcp("localhost", 7000);
~~~

Nếu chỉ truyền String, byte[] hoặc ByteBuffer, codec cơ bản có thể đủ. Với record/DTO, không nên bỏ qua cấu hình serialization vì lỗi codec có thể khiến request không encode được hoặc response không decode được.

## 4. Requester nhận nhiều response bằng retrieveFlux

Requester có thể kết nối qua TCP hoặc WebSocket. Ví dụ kết nối TCP:

~~~java
RSocketRequester requester =
        RSocketRequester.builder()
                .tcp("localhost", 7000);
~~~

Lời gọi trên chuẩn bị requester; kết nối được thiết lập khi có request đầu tiên. Gửi một request và nhận nhiều response:

~~~java
WatchRequest request = new WatchRequest("sensor-17");

Flux<SensorReading> readings = requester
        .route("sensor.watch")
        .data(request)
        .retrieveFlux(SensorReading.class);
~~~

**retrieveFlux(SensorReading.class)** khai báo kiểu của từng response element. Nó không trả về một List chứa tất cả phần tử. Thay vào đó, requester nhận một Flux và có thể xử lý từng phần tử khi nó đến.

Có thể subscribe để xử lý dữ liệu liên tục:

~~~java
Disposable subscription = readings.subscribe(
        reading -> System.out.println(
                reading.sequence() + ": " + reading.value()),
        error -> System.err.println(
                "Stream failed: " + error.getMessage()),
        () -> System.out.println("Stream completed"));
~~~

Nếu stream là vô hạn hoặc chạy lâu, giữ handle để có thể hủy:

~~~java
subscription.dispose();
~~~

Khi requester hủy subscription, cancellation được truyền qua RSocket để responder có thể dừng công việc upstream. Ứng dụng nên giải phóng tài nguyên khi nhận cancellation, ví dụ đóng cursor, hủy polling hoặc dừng subscription tới nguồn dữ liệu.

## 5. Mỗi phần tử là một response payload riêng

Một Request-Stream có thể trả về:

- **0 phần tử:** stream hoàn tất mà không có response payload.
- **1 phần tử:** chỉ có một response payload, nhưng interaction vẫn có thể là Request-Stream nếu responder khai báo Flux.
- **N phần tử:** mỗi phần tử được gửi như một payload trên cùng stream.
- **Lỗi:** stream kết thúc bằng lỗi; requester nhận onError.
- **Hoàn tất:** responder kết thúc stream bình thường; requester nhận onComplete.

Ví dụ một stream hữu hạn:

~~~java
@MessageMapping("numbers.range")
public Flux<Integer> range(@Payload NumberRange request) {
    return Flux.range(request.start(), request.count());
}

public record NumberRange(int start, int count) {
}
~~~

Nếu request có start=10 và count=3, response lần lượt là 10, 11, 12 rồi stream hoàn tất. Đây là ba response payload riêng, không phải một payload JSON chứa mảng gồm cả ba số.

Để trả về một mảng/list như một kết quả duy nhất, dùng **Mono<List<T>>** hoặc một DTO chứa list. Để truyền nhiều phần tử có thể được xử lý dần, dùng **Flux<T>**.

## 6. Backpressure: requester kiểm soát tốc độ response

RSocket tích hợp Reactive Streams semantics qua network. Requester không chỉ đăng ký nhận stream; nó còn báo cho responder biết mình sẵn sàng nhận bao nhiêu phần tử.

Ở cấp giao thức:

1. Requester gửi frame **REQUEST_STREAM** kèm số lượng demand ban đầu, gọi là initial Request N.
2. Responder có thể gửi tối đa số PAYLOAD tương ứng với demand đang có.
3. Khi requester cần thêm phần tử, nó gửi **REQUEST_N** với số lượng bổ sung.
4. Responder phải tôn trọng demand và không gửi vượt quá số phần tử đã được yêu cầu.
5. Requester có thể gửi **CANCEL** để kết thúc stream đang hoạt động.

Initial Request N phải lớn hơn 0. Các khoản demand bổ sung được cộng dồn; credit đã cấp không thể bị thu hồi. Việc này giúp responder biết chính xác có thể phát bao nhiêu phần tử tiếp theo.

Ví dụ requester ban đầu yêu cầu 3 phần tử:

~~~text
Requester -> Responder: REQUEST_STREAM (initial Request N = 3)
Responder -> Requester: PAYLOAD #1
Responder -> Requester: PAYLOAD #2
Responder -> Requester: PAYLOAD #3
Requester -> Responder: REQUEST_N (N = 2)
Responder -> Requester: PAYLOAD #4
Responder -> Requester: PAYLOAD #5
Responder -> Requester: COMPLETE
~~~

Responder phải đợi demand mới sau khi đã gửi hết 3 phần tử ban đầu. Nếu stream hoàn tất sau 5 phần tử, responder gửi COMPLETE và không cần demand thêm.

## 7. Backpressure được truyền qua Flux

Spring dùng Reactor để ánh xạ Reactive Streams demand qua RSocket. Khi subscriber ở phía requester chỉ yêu cầu một phần tử, demand có thể được truyền ngược qua RSocket để giới hạn tốc độ phát từ responder.

Ví dụ với Reactor:

~~~java
Flux<SensorReading> readings = requester
        .route("sensor.watch")
        .data(new WatchRequest("sensor-17"))
        .retrieveFlux(SensorReading.class);

readings
        .limitRate(32)
        .subscribe(this::processReading);
~~~

**limitRate(32)** điều tiết request upstream theo từng đợt, giúp giới hạn lượng demand mà subscriber chuyển tiếp. Giá trị thực tế và nhịp request còn phụ thuộc operator chain và implementation; không nên hiểu 32 là một cam kết rằng mỗi frame mạng luôn chứa đúng 32 phần tử.

Backpressure đặc biệt hữu ích khi nguồn dữ liệu có thể phát chậm lại, ví dụ reactive database driver, publisher dựa trên demand hoặc pipeline Reactor. Khi consumer xử lý chậm, demand giảm và responder có thể tạm dừng phát thêm.

Nếu nguồn dữ liệu là push-only, chẳng hạn callback từ thiết bị hoặc listener không thể tạm dừng, adapter phải quyết định cách xử lý khi consumer chậm: buffer có giới hạn, drop dữ liệu cũ/mới, giữ latest value, ghi bền vững hoặc điều tiết tại nguồn nếu có thể. Không nên dùng buffer không giới hạn vì nó có thể làm bộ nhớ tăng liên tục.

## 8. Không gom toàn bộ stream nếu không cần

Một lỗi thường gặp là biến Flux thành List quá sớm:

~~~java
List<SensorReading> allReadings = readings.collectList().block();
~~~

Cách này chỉ phù hợp với stream hữu hạn và số lượng phần tử nhỏ. Nó chờ toàn bộ stream hoàn tất, giữ tất cả phần tử trong bộ nhớ và làm mất lợi ích xử lý tăng dần. Nếu stream là vô hạn, **collectList()** không hoàn tất cho tới khi stream kết thúc, do đó ứng dụng có thể chờ mãi.

Ưu tiên xử lý từng phần tử:

~~~java
readings
        .filter(reading -> reading.value() > 0)
        .map(this::toMetric)
        .subscribe(this::storeMetric);
~~~

Nếu chỉ cần một số lượng hữu hạn:

~~~java
Flux<SensorReading> firstHundred = readings.take(100);
~~~

**take(100)** phát tối đa 100 phần tử rồi hủy upstream. Với RSocket, cancellation được truyền tới responder để dừng stream nếu có thể.

Nếu chỉ cần một phần tử đầu tiên, dùng **next()** hoặc **take(1)** để chuyển thành Mono phù hợp với mục đích xử lý.

## 9. Kết thúc stream, lỗi và cancellation

Request-Stream có vòng đời riêng:

- Responder phát các PAYLOAD.
- Responder có thể hoàn tất bình thường.
- Responder có thể kết thúc bằng ERROR.
- Requester có thể hủy bằng CANCEL.
- Khi requester hủy, responder cần dừng việc phát thêm dữ liệu và giải phóng tài nguyên upstream.

Ví dụ thêm cleanup cho stream:

~~~java
@MessageMapping("sensor.watch")
public Flux<SensorReading> watch(@Payload WatchRequest request) {
    return sensorService.streamReadings(request.deviceId())
            .doFinally(signal -> {
                // Dừng tài nguyên hoặc ghi nhận trạng thái kết thúc.
                // signal có thể là ON_COMPLETE, ON_ERROR hoặc CANCEL.
            });
}
~~~

Không nên giả định CANCEL lập tức dừng một thao tác blocking không thể interrupt. Nếu service dùng API blocking, cần thiết kế adapter, executor và cơ chế hủy phù hợp. Reactive cancellation chỉ có tác dụng đầy đủ khi các thành phần upstream tôn trọng cancellation.

Nếu có lỗi giữa stream, requester nhận **onError** và stream kết thúc; các phần tử tiếp theo không được gửi trên stream đã lỗi. Có thể phục hồi lỗi trước khi trả về từ responder nếu domain cho phép:

~~~java
return sensorService.streamReadings(request.deviceId())
        .onErrorResume(
                SensorUnavailableException.class,
                error -> Flux.empty());
~~~

Ví dụ trên biến lỗi nguồn dữ liệu thành stream rỗng. Chỉ làm vậy nếu stream rỗng là kết quả nghiệp vụ chấp nhận được; nếu không, hãy để lỗi truyền tới requester để client có thể hiển thị hoặc retry phù hợp.

## 10. Phân biệt Request-Stream với Request-Channel

Hai interaction đều có thể trao đổi nhiều payload nhưng khác hướng:

| Đặc điểm | Request-Stream | Request-Channel |
| --- | --- | --- |
| Requester gửi | Một request payload ban đầu | Một stream request payload |
| Responder trả | Một stream response payload | Một stream response payload |
| Dùng khi | Một yêu cầu, nhiều kết quả | Hai phía cần streaming đồng thời |
| Spring responder thường dùng | Một payload input, trả Flux | Flux input, trả Flux/Mono/void |

Ví dụ Request-Stream: client gửi một request chứa deviceId và nhận liên tục các số đo.

Ví dụ Request-Channel: client gửi liên tục các dữ liệu sensor trong khi server đồng thời trả về các cảnh báo phân tích. Đây là tương tác hai chiều có backpressure ở cả hai hướng.

Không dùng Request-Stream chỉ vì response có nhiều phần tử; nếu requester cũng phải gửi một luồng dữ liệu, hãy xem xét Request-Channel.

## 11. Giữ thứ tự các response element

Một Flux phát các phần tử theo thứ tự tín hiệu mà publisher tạo ra. Tuy nhiên, operator dùng concurrency có thể thay đổi thứ tự hoàn tất.

Ví dụ:

~~~java
Flux<EnrichedReading> unordered = readings.flatMap(
        reading -> enrichmentService.enrich(reading),
        8);
~~~

**flatMap** cho phép nhiều tác vụ con chạy đồng thời. Nếu phần tử thứ hai hoàn tất trước phần tử thứ nhất, nó có thể được phát trước. Điều này hữu ích khi ưu tiên throughput và các phần tử độc lập.

Nếu cần giữ thứ tự đầu vào, dùng **concatMap**:

~~~java
Flux<EnrichedReading> ordered = readings.concatMap(
        reading -> enrichmentService.enrich(reading));
~~~

**concatMap** chỉ subscribe tới publisher con tiếp theo sau khi publisher con hiện tại hoàn tất, vì vậy giữ thứ tự nhưng giảm concurrency.

Một lựa chọn là **flatMapSequential**:

~~~java
Flux<EnrichedReading> orderedConcurrent = readings.flatMapSequential(
        reading -> enrichmentService.enrich(reading),
        8);
~~~

Operator này cho phép tác vụ con chạy đồng thời nhưng phát kết quả theo thứ tự nguồn. Đổi lại, kết quả hoàn tất sớm có thể phải được buffer để chờ phần tử trước. Hãy chọn operator dựa trên yêu cầu thứ tự và giới hạn bộ nhớ.

Ngay cả khi Flux giữ đúng thứ tự, nhiều stream RSocket khác nhau không tự có thứ tự toàn cục. Nếu các event thuộc cùng một aggregate, nên mang theo sequence/version và kiểm tra tại consumer.

## 12. Một ví dụ client xử lý stream có giới hạn

Ví dụ requester lấy 100 số đo đầu tiên, xử lý từng phần tử và hủy khi đủ số lượng:

~~~java
Flux<SensorReading> readings = requester
        .route("sensor.watch")
        .data(new WatchRequest("sensor-17"))
        .retrieveFlux(SensorReading.class);

Disposable subscription = readings
        .take(100)
        .doOnNext(reading -> System.out.println(
                reading.sequence() + " = " + reading.value()))
        .doOnError(error -> System.err.println(
                "RSocket stream failed: " + error.getMessage()))
        .doOnComplete(() -> System.out.println("Received 100 or fewer readings"))
        .subscribe();
~~~

Nếu responder hoàn tất sớm, client nhận số phần tử ít hơn 100 và onComplete. Nếu đủ 100, take hủy upstream và hoàn tất phía client. Trong cả hai trường hợp, client không cần chờ toàn bộ nguồn dữ liệu vô hạn kết thúc.

Nếu ứng dụng cần quản lý vòng đời rõ hơn, giữ **Disposable** và gọi **dispose()** khi người dùng rời màn hình hoặc không còn cần stream. Hãy tránh subscribe lồng nhau trong service mà không giữ handle, vì có thể tạo stream không được hủy khi component đã đóng.

## 13. Kiểm thử backpressure và cancellation

Dùng **StepVerifier** để kiểm tra demand ở mức Reactor. Ví dụ kiểm tra subscriber ban đầu chưa yêu cầu phần tử, sau đó yêu cầu lần lượt:

~~~java
StepVerifier.create(Flux.range(1, 5), 0)
        .thenRequest(1)
        .expectNext(1)
        .thenRequest(2)
        .expectNext(2, 3)
        .thenRequest(2)
        .expectNext(4, 5)
        .verifyComplete();
~~~

Test này kiểm tra publisher tuân thủ demand của subscriber. Để kiểm thử RSocket qua network, cần integration test với RSocket server/client thực tế và xác nhận stream bị hủy khi requester cancel.

Các trường hợp nên có:

- Responder phát nhiều response và requester nhận đúng kiểu, đúng số phần tử.
- Requester yêu cầu ít phần tử ban đầu rồi bổ sung demand; responder không phát vượt demand.
- Requester cancel; upstream publisher nhận cancellation và giải phóng tài nguyên.
- Stream hoàn tất bình thường; requester nhận onComplete.
- Stream lỗi; requester nhận onError và không nhận phần tử sau terminal error.
- Một operator parallel/flatMap làm thay đổi thứ tự; concatMap hoặc flatMapSequential giữ thứ tự mong muốn.
- Stream lớn hoặc dài; bộ nhớ không tăng không giới hạn khi consumer chậm.

StepVerifier kiểm tra Reactive Streams behavior của publisher. Nó không thay thế kiểm thử protocol flow-control qua RSocket; để xác minh REQUEST_N/CANCEL trên wire hoặc tích hợp broker/transport, hãy dùng integration test phù hợp và quan sát metrics/log của RSocket.

## 14. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Stream trả về một list lớn sau thời gian chờ | Đã gọi collectList hoặc block | Xử lý Flux từng phần tử |
| Consumer chậm làm memory tăng | Buffer không giới hạn hoặc nguồn push-only | Dùng bounded buffer, drop/latest hoặc điều tiết producer |
| Requester không nhận thêm phần tử | Demand chưa được bổ sung, stream đã complete/error hoặc bị cancel | Kiểm tra subscriber demand, onComplete/onError và cancellation |
| Phần tử response về sai thứ tự | flatMap hoặc xử lý song song | Dùng concatMap/flatMapSequential hoặc sequence number |
| Cancel client nhưng server vẫn chạy tác vụ | Upstream blocking hoặc không tôn trọng cancellation | Thiết kế API cancellable, dùng reactive I/O và cleanup |
| Hai client có thứ tự khác nhau | Hai RSocket stream độc lập, không có global ordering | Định nghĩa sequence theo aggregate/business key |
| Một request nhận quá nhiều dữ liệu | Stream không giới hạn hoặc không có giới hạn ở domain | Dùng take, filter, paging hoặc time window |
| Lỗi xuất hiện sau vài phần tử | Responder phát error giữa stream | Kiểm tra onError, retry policy và trạng thái partial result |

## 15. Tài liệu tham khảo

- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): interaction model, Request-Stream, RSocketRequester và annotated responders.
- [RSocket Protocol — Request-Stream](https://rsocket.io/about/protocol/): REQUEST_STREAM, REQUEST_N, PAYLOAD, CANCEL và flow-control.
- [Reactive Streams Specification](https://www.reactive-streams.org/): demand, Subscription, request(n), cancel và nguyên tắc backpressure.
- [Project Reactor — Flux](https://projectreactor.io/docs/core/release/reference/coreFeatures/flux.html): xử lý chuỗi nhiều phần tử.
- [Project Reactor — Backpressure](https://projectreactor.io/docs/core/release/reference/): demand, operator và cách kiểm soát luồng.
