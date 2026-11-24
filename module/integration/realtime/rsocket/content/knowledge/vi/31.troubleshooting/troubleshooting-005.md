# Không có dữ liệu do chưa subscribe hoặc chưa phát nhu cầu nhận

Khi một RSocket stream không trả dữ liệu, nguyên nhân có thể nằm ở hai bước khác nhau của Reactive Streams: publisher chưa được subscribe, hoặc subscriber đã subscribe nhưng chưa phát demand bằng `request(n)`. Hai tình huống này thường có cùng biểu hiện là không thấy payload, nhưng cách khắc phục khác nhau.

Trong Reactor, Flux và Mono mô tả một pipeline xử lý bất đồng bộ. Việc tạo pipeline chưa khởi chạy nó. Một Subscriber phải đăng ký để bắt đầu xử lý; sau đó Subscriber phát nhu cầu nhận dữ liệu để publisher biết có thể gửi bao nhiêu phần tử. RSocket truyền demand này qua flow control: REQUEST_STREAM/REQUEST_CHANNEL mang initial Request N, còn REQUEST_N cấp thêm credit trong quá trình stream.

Bài học tập trung vào cách phân biệt hai nguyên nhân, quan sát subscription và demand ở cả client lẫn server, sửa các lỗi phổ biến trong Spring RSocket, và kiểm thử luồng dữ liệu có kiểm soát.

## Mục tiêu học tập

Sau bài học, người học có thể:

- Phân biệt publisher chưa subscribe với subscriber chưa request dữ liệu.
- Giải thích vai trò của Subscription và request(n) trong Reactive Streams.
- Hiểu initial Request N và REQUEST_N của RSocket.
- Viết client Spring RSocket đăng ký và tiêu thụ Flux đúng cách.
- Tránh gọi subscribe() rời rạc bên trong @MessageMapping.
- Phát demand hữu hạn rồi bổ sung demand khi xử lý xong dữ liệu.
- Phân biệt cold publisher và hot publisher khi người nhận đăng ký muộn.
- Dùng log, doOnSubscribe, doOnRequest, doOnNext, doOnCancel và StepVerifier để khoanh vùng lỗi.
- Phân biệt lỗi flow control với lỗi route, transport, codec hoặc nguồn dữ liệu.

## 1. Hai điều kiện để dữ liệu đi tới Subscriber

Một pipeline Reactor chỉ mô tả công việc cần làm. Để dữ liệu đi tới ứng dụng tiêu thụ, cần có hai điều kiện:

1. Có subscription: Subscriber đăng ký với Publisher.
2. Có demand dương: Subscriber yêu cầu một số phần tử bằng request(n), với n lớn hơn 0.

~~~mermaid
flowchart TD
    P[Publisher: Flux / Mono] --> S{Đã subscribe?}
    S -- Không --> N[Pipeline chưa chạy]
    S -- Có --> D{Có demand > 0?}
    D -- Không --> W[Đã đăng ký nhưng đang chờ request]
    D -- Có --> E{Nguồn có dữ liệu?}
    E -- Không --> I[Chưa có phần tử để phát]
    E -- Có --> V[onNext: Subscriber nhận dữ liệu]
~~~

| Tình trạng | Subscription | Demand | Biểu hiện |
|---|---|---|---|
| Chỉ tạo Flux, chưa subscribe | Chưa có | Chưa có | Không có xử lý nào bắt đầu |
| Đã subscribe bằng Subscriber tùy chỉnh nhưng không request | Có | 0 | Không có onNext |
| Đã request một số phần tử | Có | Dương | Publisher được phép phát tối đa số phần tử đã yêu cầu |
| Đã dùng hết demand | Có | 0 | Publisher chờ REQUEST_N hoặc request tiếp theo |
| Có demand nhưng nguồn chưa có dữ liệu | Có | Dương | Không có onNext cho tới khi nguồn phát |
| Đã cancel hoặc complete | Đã kết thúc | Không còn hiệu lực | Không nhận thêm dữ liệu trên subscription đó |

Không có onNext chưa đủ để kết luận server không phát dữ liệu. Hãy xác định subscription và demand trước, rồi mới kiểm tra nguồn dữ liệu.

## 2. Tạo Flux chưa có nghĩa là đã đăng ký

Ví dụ tạo một pipeline:

~~~java
Flux<Reading> readings = readingService.stream("sensor-17");
~~~

Dòng lệnh này chỉ tạo một đối tượng Publisher. Nếu không có thành phần nào subscribe, pipeline chưa được thực thi. Các operator như map, filter, doOnNext và doOnError cũng chỉ định nghĩa các bước sẽ chạy khi có subscription.

Client cần subscribe để bắt đầu nhận dữ liệu:

~~~java
Flux<Reading> readings = requester
        .route("devices.readings")
        .data(new ReadingQuery("sensor-17"))
        .retrieveFlux(Reading.class);

readings.subscribe(
        reading -> log.info("Received: {}", reading),
        error -> log.error("Stream failed", error),
        () -> log.info("Stream completed"));
~~~

Với các overload subscribe nhận callback thông thường, Reactor yêu cầu demand không giới hạn ngay khi subscribe. Điều đó thuận tiện cho ví dụ đơn giản, nhưng trong ứng dụng thật cần quản lý subscription và cancellation theo vòng đời của màn hình, session hoặc service.

Nếu muốn giữ quyền điều khiển demand, dùng Subscriber tùy chỉnh hoặc Reactor BaseSubscriber như phần sau.

### Lỗi thường gặp: tạo publisher nhưng không subscribe

~~~java
public void startStreaming() {
    requester.route("devices.readings")
            .data(new ReadingQuery("sensor-17"))
            .retrieveFlux(Reading.class)
            .doOnNext(reading -> log.info("{}", reading));

    // Không có subscribe: request chưa được khởi chạy.
}
~~~

Cách sửa:

~~~java
public Disposable startStreaming() {
    return requester.route("devices.readings")
            .data(new ReadingQuery("sensor-17"))
            .retrieveFlux(Reading.class)
            .doOnNext(reading -> log.info("{}", reading))
            .subscribe(
                    reading -> updateDashboard(reading),
                    error -> log.error("Cannot receive readings", error));
}
~~~

Giữ lại Disposable nếu cần chủ động dừng stream. Khi người dùng rời màn hình hoặc component bị hủy, gọi dispose() để giải phóng subscription.

## 3. Đã subscribe nhưng vẫn không có dữ liệu: kiểm tra demand

Reactive Streams không chỉ yêu cầu đăng ký. Subscriber còn phải báo số phần tử mà nó sẵn sàng nhận.

API cốt lõi:

~~~java
subscription.request(10);
~~~

Lệnh trên cho phép Publisher phát tối đa 10 phần tử bổ sung. Khi Subscriber đã nhận và xử lý các phần tử đó, nó có thể gọi request(n) lần nữa.

Các quy tắc cần nhớ:

- Demand được cộng dồn qua nhiều lần request.
- request(1) cho phép phát thêm một phần tử.
- request(10) cho phép phát thêm mười phần tử.
- request(0) và request số âm không hợp lệ theo Reactive Streams.
- Không gọi request lần nữa nghĩa là demand có thể cạn và stream tạm dừng.
- cancel() kết thúc subscription; request sau khi cancel không khởi động lại stream.

### Subscriber tùy chỉnh không phát demand

Đây là một lỗi phổ biến:

~~~java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;

readings.subscribe(new BaseSubscriber<Reading>() {
    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        // Không gọi request(n).
        // Subscription tồn tại nhưng không có demand.
    }

    @Override
    protected void hookOnNext(Reading reading) {
        log.info("Received: {}", reading);
    }
});
~~~

BaseSubscriber cho phép ứng dụng tự quyết định demand. Khi ghi đè hookOnSubscribe, hãy gọi request(n) ít nhất một lần nếu muốn nhận dữ liệu.

Ví dụ yêu cầu 16 phần tử ban đầu và bổ sung một phần tử sau mỗi lần xử lý:

~~~java
readings
        .doOnRequest(n -> log.debug("Downstream requested {}", n))
        .subscribe(new BaseSubscriber<Reading>() {

            @Override
            protected void hookOnSubscribe(Subscription subscription) {
                request(16);
            }

            @Override
            protected void hookOnNext(Reading reading) {
                process(reading);
                request(1);
            }

            @Override
            protected void hookOnError(Throwable error) {
                log.error("Reading stream failed", error);
            }

            @Override
            protected void hookOnComplete() {
                log.info("Reading stream completed");
            }

            @Override
            protected void hookOnCancel() {
                log.info("Reading stream cancelled");
            }
        });
~~~

Ví dụ này giữ khoảng 16 phần tử demand đang chờ: ban đầu yêu cầu 16; mỗi khi xử lý xong một phần tử, yêu cầu thêm một. Nếu xử lý mất nhiều thời gian, việc bổ sung demand sau khi xử lý giúp nguồn không đẩy thêm dữ liệu nhanh hơn khả năng tiêu thụ.

Đừng gọi request(1) trước khi xử lý xong nếu mục tiêu là giới hạn số phần tử đang chờ trong tầng ứng dụng.

## 4. Demand được truyền qua RSocket như thế nào?

RSocket dùng Reactive Streams semantics để điều tiết stream và channel. Requester cấp credit cho Responder, và Responder không được gửi nhiều PAYLOAD hơn số credit còn lại.

Với request-stream:

1. Requester mở stream bằng REQUEST_STREAM.
2. Frame này mang initial Request N.
3. Responder có thể gửi tối đa N PAYLOAD.
4. Khi cần nhận thêm, Requester gửi REQUEST_N.
5. Credit được cộng dồn; Responder chờ nếu đã dùng hết credit.

~~~mermaid
sequenceDiagram
    participant C as Requester
    participant S as Responder
    C->>S: REQUEST_STREAM (initial N = 2)
    S-->>C: PAYLOAD 1
    S-->>C: PAYLOAD 2
    Note over S: Hết credit, chờ demand mới
    C->>S: REQUEST_N (N = 2)
    S-->>C: PAYLOAD 3
    S-->>C: PAYLOAD 4
    S-->>C: COMPLETE
~~~

Initial Request N trong REQUEST_STREAM và REQUEST_CHANNEL phải lớn hơn 0 theo protocol. Các REQUEST_N tiếp theo cũng yêu cầu số credit dương. Vì vậy, nếu Subscriber chưa có demand, implementation có thể trì hoãn việc mở request stream hoặc chưa cấp credit để Responder phát PAYLOAD. Không gửi REQUEST_N bằng 0 để biểu diễn trạng thái chờ.

Demand ở RSocket đếm số message/payload, không phải số byte. Một payload lớn vẫn tính là một item demand; giới hạn kích thước payload và bộ nhớ cần được quản lý riêng.

### Request-channel có hai chiều demand

Request-channel là interaction hai chiều. Cả requester và responder có thể phát PAYLOAD; mỗi phía phải tôn trọng demand mà phía kia cấp.

- Initial Request N trong REQUEST_CHANNEL biểu thị số payload responder được phép gửi ban đầu tới requester.
- Responder phải gửi REQUEST_N để cấp credit cho requester gửi các PAYLOAD tiếp theo trên channel.
- Sau đó hai bên có thể gửi REQUEST_N độc lập để điều tiết hướng dữ liệu tương ứng.

Do đó, khi channel chỉ nhận được dữ liệu một chiều, cần kiểm tra demand của đúng hướng đang bị dừng. Việc requester đã subscribe channel không tự động có nghĩa là responder đã cấp credit cho requester gửi payload ngược lại.

## 5. Spring RSocket: trả Flux từ handler, không tự subscribe bên trong

Trong Spring Messaging, handler có thể trả về Flux để framework quản lý subscription, demand, cancellation và lifecycle của RSocket interaction.

Ví dụ server:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import reactor.core.publisher.Flux;

// Reading, ReadingQuery, ReadingService và log là các thành phần của ứng dụng.
@Controller
public class ReadingController {

    private static final Logger log =
            LoggerFactory.getLogger(ReadingController.class);

    private final ReadingService readingService;

    public ReadingController(ReadingService readingService) {
        this.readingService = readingService;
    }

    @MessageMapping("devices.readings")
    public Flux<Reading> readings(@Payload ReadingQuery query) {
        return readingService.stream(query.deviceId())
                .doOnSubscribe(subscription ->
                        log.info("Reading stream subscribed: {}", query.deviceId()))
                .doOnRequest(n ->
                        log.debug("Reading demand: {}", n))
                .doOnNext(reading ->
                        log.debug("Produced reading: {}", reading.sequence()))
                .doOnCancel(() ->
                        log.info("Reading stream cancelled: {}", query.deviceId()))
                .doOnComplete(() ->
                        log.info("Reading stream completed: {}", query.deviceId()))
                .doOnError(error ->
                        log.warn("Reading stream failed: {}", query.deviceId(), error));
    }
}
~~~

Spring nhận Publisher được trả về và kết nối lifecycle của nó với request RSocket. Khi client gửi CANCEL hoặc connection đóng, cancellation có thể được truyền ngược tới publisher.

### Không gọi subscribe() bên trong @MessageMapping

Sai:

~~~java
@MessageMapping("devices.readings")
public void readings(@Payload ReadingQuery query) {
    readingService.stream(query.deviceId())
            .subscribe(reading -> log.info("{}", reading));
}
~~~

Handler trả void nên Spring không có Flux response để liên kết với request-stream. Subscription được tạo riêng, có thể tiếp tục chạy sau khi client đã hủy request, và backpressure từ RSocket không còn được nối với publisher này.

Đúng:

~~~java
@MessageMapping("devices.readings")
public Flux<Reading> readings(@Payload ReadingQuery query) {
    return readingService.stream(query.deviceId());
}
~~~

Chỉ tự subscribe khi thực sự muốn tạo một tác vụ độc lập không thuộc lifecycle của request hiện tại, chẳng hạn ghi audit nền. Tác vụ độc lập đó cần cơ chế quản lý lỗi, cancellation, giới hạn concurrency và vòng đời riêng.

## 6. Instrument client và server để tìm điểm bị dừng

Hãy đặt log ở nhiều vị trí trong pipeline. Mỗi hook trả lời một câu hỏi khác nhau:

| Hook | Câu hỏi chẩn đoán |
|---|---|
| doOnSubscribe | Publisher đã có Subscriber chưa? |
| doOnRequest | Subscriber đang yêu cầu bao nhiêu phần tử? |
| doOnNext | Có phần tử đi qua vị trí này không? |
| doOnComplete | Publisher đã hoàn tất bình thường chưa? |
| doOnError | Có lỗi kết thúc stream không? |
| doOnCancel | Subscriber hoặc request đã bị hủy chưa? |
| doFinally | Subscription kết thúc bằng complete, error hay cancel? |

Client có thể đặt các hook trước và sau operator:

~~~java
import reactor.core.Disposable;

Flux<Reading> source = requester
        .route("devices.readings")
        .data(new ReadingQuery("sensor-17"))
        .retrieveFlux(Reading.class);

Disposable subscription = source
        .doOnSubscribe(s -> log.info("Client subscribed"))
        .doOnRequest(n -> log.info("Client demand: {}", n))
        .doOnNext(item -> log.info("Client received: {}", item.sequence()))
        .doOnError(error -> log.error("Client stream error", error))
        .doOnComplete(() -> log.info("Client stream complete"))
        .doOnCancel(() -> log.info("Client cancelled"))
        .doFinally(signal -> log.info("Client final signal: {}", signal))
        .subscribe();
~~~

Nếu client log có subscribe nhưng không có request, hãy kiểm tra Subscriber và operator cuối pipeline. Nếu client có demand nhưng server không thấy request handler được subscribe, hãy kiểm tra route, SETUP và việc request có được gửi qua transport hay chưa. Nếu server thấy demand nhưng không có doOnNext, hãy kiểm tra nguồn dữ liệu.

Đặt doOnRequest ở nhiều vị trí có thể cho thấy operator thay đổi demand. Ví dụ buffer, publishOn, limitRate và các operator kết hợp luồng có thể yêu cầu upstream theo batch khác với số item mà subscriber cuối cùng nhìn thấy.

## 7. Kiểm tra operator có làm mất dữ liệu hay không

Ngay cả khi subscribe và demand đều đúng, operator vẫn có thể làm đầu ra rỗng.

Ví dụ filter loại mọi phần tử:

~~~java
Flux<Reading> result = readingService.stream(deviceId)
        .filter(reading -> reading.value() > 100);
~~~

Nếu tất cả giá trị đều nhỏ hơn hoặc bằng 100, downstream không nhận phần tử nào dù upstream vẫn phát dữ liệu.

Đặt doOnNext ở hai phía của filter:

~~~java
Flux<Reading> result = readingService.stream(deviceId)
        .doOnNext(reading -> log.debug("Before filter: {}", reading.value()))
        .filter(reading -> reading.value() > 100)
        .doOnNext(reading -> log.debug("After filter: {}", reading.value()));
~~~

Các operator khác cần kiểm tra:

- take(0) kết thúc luồng mà không phát item.
- next() chỉ lấy phần tử đầu tiên rồi hoàn tất.
- skip(n) bỏ qua n phần tử đầu.
- distinct() có thể loại các giá trị lặp.
- onErrorResume(error -> Flux.empty()) có thể biến lỗi thành complete rỗng, khiến lỗi gốc khó phát hiện.
- switchIfEmpty() chỉ chạy nhánh thay thế khi publisher hoàn tất mà không có item; nó không giúp một stream còn đang chờ vô hạn.
- Flux.empty() phát onComplete ngay mà không có onNext; Flux.never() không phát item, complete hay error. Hai trường hợp cần cách chẩn đoán khác nhau.

Trong lúc chẩn đoán, đừng dùng onErrorResume để nuốt mọi lỗi. Hãy log lỗi gốc và chỉ chuyển sang empty khi đó là hành vi nghiệp vụ đã được định nghĩa.

## 8. Cold publisher và hot publisher

Không phải mọi nguồn dữ liệu đều giữ item để subscriber nhận sau.

**Cold publisher** thường bắt đầu tạo dữ liệu theo từng subscription. Mỗi subscriber có thể nhận một chuỗi dữ liệu độc lập. Ví dụ Flux.defer, Flux.fromIterable hoặc một truy vấn reactive tới database.

**Hot publisher** có thể phát dữ liệu theo thời gian thực, không phụ thuộc subscriber. Nếu sự kiện phát ra trước khi client subscribe, subscriber đến muộn có thể không nhận lại sự kiện đó.

| Loại nguồn | Subscriber đăng ký muộn | Cần kiểm tra |
|---|---|---|
| Cold publisher | Thường bắt đầu một luồng mới từ lúc subscribe | Publisher có được subscribe không? |
| Hot multicast | Có thể chỉ nhận sự kiện từ lúc đăng ký | Sự kiện đã phát trước subscription chưa? |
| Replay publisher | Có thể nhận lại số sự kiện đã lưu | Replay size/retention có đủ không? |
| Unicast publisher | Thường chỉ cho phép một subscriber | Có subscriber khác đã chiếm nguồn chưa? |

Nếu dùng Reactor Sinks, chọn loại sink theo yêu cầu nghiệp vụ. Ví dụ replay có thể giữ lại lịch sử giới hạn; multicast phù hợp với các subscriber đang hoạt động; unicast dành cho một subscriber. Chính sách buffer, overflow và số subscriber phải được cấu hình rõ.

Một hot publisher có subscriber nhưng không có demand cũng có thể buffer, drop hoặc báo lỗi tùy loại sink và chiến lược overflow. Vì vậy hãy kiểm tra cả thời điểm subscribe lẫn demand, đồng thời quan sát metric buffer/drop nếu nguồn có hỗ trợ.

## 9. Kiểm tra từng lớp khi vẫn không có dữ liệu

Sau khi xác nhận subscribe và demand, kiểm tra các lớp còn lại theo thứ tự:

1. **Handler có được gọi không?** Log route và đầu vào tại server.
2. **Route có khớp không?** So sánh route client gửi với @MessageMapping, kể cả prefix và chữ hoa/chữ thường.
3. **Publisher server có subscribe không?** Đặt doOnSubscribe trong handler và service.
4. **Server có demand không?** Đặt doOnRequest và xem initial Request N/REQUEST_N.
5. **Nguồn có phát không?** Đặt doOnNext ngay sau source, trước filter/map.
6. **Có terminal signal không?** Kiểm tra doOnComplete, doOnError, doOnCancel và doFinally.
7. **Codec có giải mã được không?** Kiểm tra data MIME type, serializer và lỗi decode.
8. **Connection còn sống không?** Kiểm tra SETUP, keepalive, WebSocket/TCP, reconnect và connection close.

Không kết luận là lỗi codec chỉ vì client không thấy item. Codec thường gây decode error; một subscriber chưa phát demand có thể không tạo ra payload nào để decode.

## 10. Kiểm thử demand bằng StepVerifier

StepVerifier có thể subscribe vào Publisher với demand ban đầu bằng 0, sau đó phát request rõ ràng để kiểm tra flow control.

Ví dụ dùng thư viện reactor-test trong test scope của dự án.

~~~java
import java.time.Duration;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class ReadingStreamTest {

    @Test
    void emitsOnlyAfterDemandAndCompletes() {
        Flux<String> readings = Flux.just("r1", "r2", "r3");

        StepVerifier.create(readings, 0)
                .thenRequest(2)
                .expectNext("r1", "r2")
                .thenRequest(1)
                .expectNext("r3")
                .expectComplete()
                .verify(Duration.ofSeconds(3));
    }
}
~~~

Test này xác minh:

- StepVerifier đã subscribe nhưng bắt đầu với demand bằng 0.
- Hai phần tử đầu chỉ được yêu cầu khi thenRequest(2) chạy.
- Phần tử thứ ba chỉ được yêu cầu sau thenRequest(1).
- Publisher hoàn tất sau khi phát đủ ba phần tử.

Có thể kiểm tra cancellation:

~~~java
StepVerifier.create(readingService.stream("sensor-17"), 0)
        .thenRequest(1)
        .expectNextCount(1)
        .thenCancel()
        .verify(Duration.ofSeconds(3));
~~~

Khi test integration với RSocket thật, quan sát thêm log ở server để xác nhận demand được chuyển qua protocol. Unit test StepVerifier chỉ kiểm tra publisher trong JVM, chưa chứng minh transport hoặc hai đầu RSocket cấu hình đúng.

## 11. Ma trận triệu chứng và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xác minh | Cách sửa |
|---|---|---|---|
| Không có log từ pipeline | Chưa subscribe | Kiểm tra doOnSubscribe | Gọi subscribe hoặc trả Publisher cho framework |
| Có subscribe nhưng không có doOnRequest | Subscriber tùy chỉnh chưa request | Ghi log hookOnSubscribe và doOnRequest | Gọi request(n) với n dương |
| Có một vài item rồi dừng | Đã dùng hết demand | So sánh tổng request với số onNext | Request thêm khi xử lý xong |
| Server không thấy handler chạy | Request chưa được gửi hoặc route sai | Log client route và server handler | Sửa route/connection, xác minh subscription |
| Server có doOnNext nhưng client không có | Demand, transport hoặc lỗi decode | Kiểm tra REQUEST_N, ERROR và codec | Khôi phục demand hoặc sửa MIME/serializer |
| Upstream có item, downstream rỗng | Filter/skip/distinct loại dữ liệu | Log trước và sau operator | Sửa điều kiện hoặc thứ tự operator |
| Subscriber đăng ký muộn và bỏ lỡ event | Hot source không replay | Kiểm tra thời điểm emit và subscribe | Dùng replay hoặc lưu event theo cursor |
| Stream dừng ngay sau khi mở | Đã cancel/dispose hoặc take(0) | Log doOnCancel/doFinally | Sửa lifecycle và toán tử kết thúc |
| Handler server chạy nhưng client không nhận | Handler tự subscribe rồi trả void | Kiểm tra kiểu trả về handler | Trả Flux/Mono trực tiếp |
| Channel chỉ chạy một chiều | Demand của hướng ngược chưa được cấp | Kiểm tra REQUEST_N của từng hướng | Cấp demand cho đúng hướng gửi |

## 12. Quy trình xử lý sự cố tại môi trường thật

Khi nhận báo cáo “stream không có dữ liệu”, thu thập bằng chứng theo thứ tự sau:

1. Ghi nhận route, interaction model và connection ID.
2. Xác minh client đã subscribe bằng log doOnSubscribe.
3. Xác minh Subscriber đã phát demand bằng log doOnRequest.
4. Nếu demand hữu hạn, so sánh tổng credit với số item đã nhận.
5. Kiểm tra server handler có được gọi và publisher có được subscribe.
6. Đặt log doOnNext trước/sau các operator để tìm điểm dữ liệu biến mất.
7. Kiểm tra terminal signal: complete, error hoặc cancel.
8. Nếu client/server log không khớp, kiểm tra RSocket frame và transport.
9. Sau khi xác định nguyên nhân, thêm regression test có kiểm soát demand.

Tránh tăng demand lên vô hạn như một cách chữa mặc định. Việc đó có thể che lỗi Subscriber và làm tăng bộ nhớ hoặc tải xử lý. Chỉ dùng demand không giới hạn khi consumer thực sự có khả năng xử lý tốc độ phát của nguồn.

## 13. Checklist trước khi kết luận server không phát dữ liệu

- [ ] Client tạo đúng route và đúng interaction model.
- [ ] Publisher đã được subscribe.
- [ ] Subscriber không bị cancel hoặc dispose ngay sau subscribe.
- [ ] Subscriber đã gọi request(n) với n lớn hơn 0.
- [ ] Demand chưa bị dùng hết hoặc đã được bổ sung.
- [ ] Server handler trả Flux/Mono thay vì tự subscribe rồi trả void.
- [ ] Server publisher đã được subscribe và có demand.
- [ ] Nguồn dữ liệu thực sự có item trong khoảng thời gian kiểm tra.
- [ ] Filter, skip, take, next và error fallback không loại toàn bộ dữ liệu.
- [ ] Hot publisher không phát event trước khi subscriber đăng ký hoặc có replay phù hợp.
- [ ] Với request-channel, demand của cả hai hướng đã được kiểm tra.
- [ ] Không có ERROR, CANCEL, COMPLETE hoặc connection close bị bỏ qua.
- [ ] Integration test xác nhận initial demand và REQUEST_N.

## Kết luận

Không có dữ liệu từ RSocket stream có thể do publisher chưa được subscribe hoặc Subscriber chưa phát demand. Subscribe tạo mối liên kết giữa Publisher và Subscriber; request(n) cho phép Publisher phát một số lượng phần tử cụ thể. RSocket truyền demand qua initial Request N và REQUEST_N, nên khi hết credit, Responder phải chờ requester cấp thêm. Trong Spring RSocket, hãy trả Flux trực tiếp từ @MessageMapping để framework quản lý subscription và cancellation. Khi chẩn đoán, quan sát subscribe, request, next và terminal signal trước khi chuyển sang kiểm tra route, codec hoặc transport.

## Tài liệu tham khảo

- [RSocket Protocol – REQUEST_STREAM, REQUEST_CHANNEL and REQUEST_N](https://rsocket.io/about/protocol/)
- [Spring Framework Reference – RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Project Reactor Reference – Subscribe and Demand](https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html)
- [Project Reactor Reference – Backpressure and Ways to Reshape Requests](https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html)
- [Reactive Streams JVM Specification](https://github.com/reactive-streams/reactive-streams-jvm)
