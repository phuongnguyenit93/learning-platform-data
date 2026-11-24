# Xử lý request-response với Mono và fire-and-forget với Mono<Void>

Trong Spring Messaging cho RSocket, kiểu reactive mà một method @MessageMapping trả về thể hiện kết quả mà handler tạo ra. Với request-response, handler thường trả Mono<T> để phát đúng một đối tượng phản hồi. Với fire-and-forget, handler trả Mono<Void> để biểu diễn quá trình xử lý bất đồng bộ mà không tạo payload phản hồi.

Hai kiểu này nhìn gần giống nhau vì đều dùng Mono, nhưng semantics giao thức khác nhau. Request-response cho requester nhận kết quả hoặc lỗi của tương tác. Fire-and-forget chỉ gửi một request một chiều; requester không nhận response payload để xác nhận nghiệp vụ đã hoàn tất. Bài học này hướng dẫn triển khai cả hai phía bằng Spring Boot, @MessageMapping và RSocketRequester.

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích cách Spring ánh xạ route RSocket tới method @MessageMapping.
- Viết handler request-response trả Mono<T>.
- Viết handler fire-and-forget trả Mono<Void>.
- Gọi request-response bằng RSocketRequester.retrieveMono(...).
- Gửi fire-and-forget bằng RSocketRequester.send().
- Xử lý validation, kết quả rỗng, lỗi và timeout.
- Phân biệt hoàn tất thao tác gửi với xác nhận nghiệp vụ phía server.
- Thiết kế idempotency, kiểm thử và quan sát cho tương tác một chiều.

## 1. Spring ánh xạ request tới handler như thế nào?

Client gửi request RSocket kèm routing metadata. Spring dùng route để tìm method được đánh dấu bằng @MessageMapping. Frame interaction type quyết định cách request được thực hiện; chữ ký method cho Spring biết handler sẽ phát kết quả theo dạng nào.

| Interaction | Handler phía server | API phía client | Kết quả protocol |
|---|---|---|---|
| Request-response | Mono<T> | retrieveMono(T.class) | Một response payload |
| Fire-and-forget | Mono<Void> | send() | Không có response payload |
| Request-stream | Flux<T> | retrieveFlux(T.class) | Nhiều response payload |
| Request-channel | Flux<T> đầu vào và/hoặc đầu ra | requestChannel(...) | Trao đổi chuỗi payload |

@MessageMapping gắn route với method. Ví dụ route devices.status có thể xử lý truy vấn trạng thái, còn route devices.events tiếp nhận sự kiện một chiều.

~~~mermaid
flowchart LR
    C[Client RSocketRequester] --> ROUTE[Routing metadata]
    ROUTE --> M[Spring @MessageMapping]
    M --> TYPE{Interaction type}
    TYPE -->|REQUEST_RESPONSE| RR[Handler Mono<T>]
    RR --> RESP[Response payload]
    RESP --> C
    TYPE -->|REQUEST_FNF| FNF[Handler Mono<Void>]
    FNF --> DONE[Hoàn tất xử lý phía server]
    DONE -. không có response payload .-> C
~~~

Điểm cần nhớ: Mono<T> và Mono<Void> đều mô tả một kết quả reactive có thể hoàn tất bất đồng bộ. Nhưng chỉ Mono<T> phát ra một giá trị để tạo response payload. Mono<Void> hoàn tất mà không phát giá trị.

## 2. Tạo DTO cho request và response

Dùng DTO rõ ràng giúp client và server thống nhất schema. Ví dụ một client hỏi trạng thái thiết bị bằng deviceId và nhận về trạng thái hiện tại:

~~~java
import jakarta.validation.constraints.NotBlank;

public record DeviceStatusQuery(
        @NotBlank String deviceId
) {}

public record DeviceStatus(
        String deviceId,
        String state,
        long updatedAt
) {}
~~~

Với sự kiện một chiều, nên có event ID để hỗ trợ deduplication khi producer phải gửi lại sau sự cố:

~~~java
import jakarta.validation.constraints.NotBlank;

public record DeviceEvent(
        @NotBlank String eventId,
        @NotBlank String deviceId,
        @NotBlank String eventType,
        long occurredAt
) {}
~~~

eventId là định danh nghiệp vụ do ứng dụng tạo. Nó không phải RSocket stream ID. Stream ID thuộc phạm vi connection; event ID cần ổn định qua các lần retry hoặc gửi lại để consumer nhận ra một sự kiện đã được xử lý.

## 3. Request-response: handler trả Mono<T>

Request-response phù hợp khi requester cần nhận một kết quả từ server. Handler trả Mono<T> để phát một response object sau khi công việc bất đồng bộ hoàn tất.

Ví dụ service:

~~~java
public interface DeviceStatusService {
    Mono<DeviceStatus> findStatus(String deviceId);
}
~~~

Handler Spring:

~~~java
import jakarta.validation.Valid;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class DeviceStatusController {

    private final DeviceStatusService statusService;

    public DeviceStatusController(DeviceStatusService statusService) {
        this.statusService = statusService;
    }

    @MessageMapping("devices.status")
    public Mono<DeviceStatus> status(
            @Valid @Payload DeviceStatusQuery query) {

        return statusService.findStatus(query.deviceId())
                .switchIfEmpty(Mono.error(
                        new DeviceNotFoundException(query.deviceId())));
    }
}
~~~

Handler không chặn thread để truy vấn database. Nó trả publisher từ service; Spring subscribe và chuyển giá trị phát ra thành response payload. Khi publisher phát lỗi, request-response có thể kết thúc bằng lỗi để requester xử lý.

### Vì sao cần xác định trường hợp không tìm thấy?

Một request-response được thiết kế để trả một response payload. Nếu service có thể trả Mono.empty(), cần quyết định rõ API muốn biểu diễn trường hợp đó như thế nào:

- Trả một DTO có trạng thái NOT_FOUND nếu đây là kết quả nghiệp vụ bình thường.
- Phát lỗi miền như DeviceNotFoundException nếu requester cần xử lý nhánh lỗi.
- Không để Mono.empty() vô tình trở thành một hợp đồng mơ hồ mà client không biết nên diễn giải ra sao.

Ví dụ khác là trả DTO bao gồm found, data và message, để mọi kết quả nghiệp vụ vẫn có cùng schema.

## 4. Gọi request-response bằng RSocketRequester

RSocketRequester là API Spring cấp cao để gửi request. route(...) chọn route; data(...) cung cấp payload; retrieveMono(...) khai báo kiểu response mà client muốn nhận.

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.core.publisher.Mono;

import java.time.Duration;

public class DeviceStatusClient {

    private final RSocketRequester requester;

    public DeviceStatusClient(RSocketRequester requester) {
        this.requester = requester;
    }

    public Mono<DeviceStatus> findStatus(String deviceId) {
        DeviceStatusQuery query = new DeviceStatusQuery(deviceId);

        return requester
                .route("devices.status")
                .data(query)
                .retrieveMono(DeviceStatus.class)
                .timeout(Duration.ofSeconds(3));
    }
}
~~~

retrieveMono(DeviceStatus.class) giải mã response payload thành DeviceStatus. timeout(...) giới hạn thời gian client chờ kết quả ở tầng ứng dụng; timeout này không tự chứng minh server chưa xử lý request. Nếu timeout xảy ra sau khi server đã thực hiện side effect, retry có thể lặp lại thao tác.

Có thể dùng onErrorResume để chuyển một lỗi kỹ thuật thành fallback có chủ đích, hoặc onErrorMap để chuẩn hóa exception. Tránh biến mọi lỗi thành dữ liệu mặc định vì điều đó có thể che giấu sự cố kết nối hoặc lỗi server.

### Cấu hình requester trong Spring Boot

Có thể tạo requester từ builder được Spring Boot cấu hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.rsocket.RSocketRequester;

@Configuration
public class RSocketClientConfiguration {

    @Bean
    RSocketRequester deviceRequester(
            RSocketRequester.Builder builder) {

        return builder.tcp("localhost", 7000);
    }
}
~~~

Ứng dụng có thể inject bean này vào client service. Trong môi trường thật, endpoint, transport, authentication và TLS cần được cấu hình theo profile triển khai. Không tạo một requester mới cho từng message nếu có thể tái sử dụng connection lâu dài.

## 5. Fire-and-forget: handler trả Mono<Void>

Fire-and-forget phù hợp khi client gửi một sự kiện hoặc thông điệp mà không cần response payload. Handler có thể thực hiện công việc bất đồng bộ như ghi event, đẩy vào queue hoặc cập nhật một bộ xử lý phía server.

Ví dụ service:

~~~java
public interface DeviceEventService {
    Mono<Void> accept(DeviceEvent event);
}
~~~

Handler Spring:

~~~java
import jakarta.validation.Valid;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class DeviceEventController {

    private final DeviceEventService eventService;

    public DeviceEventController(DeviceEventService eventService) {
        this.eventService = eventService;
    }

    @MessageMapping("devices.events")
    public Mono<Void> receive(
            @Valid @Payload DeviceEvent event) {

        return eventService.accept(event);
    }
}
~~~

Mono<Void> biểu diễn quá trình xử lý của handler. Nếu service trả về Mono<EventRecord> sau khi lưu, có thể dùng then() để bỏ giá trị record và chỉ giữ tín hiệu hoàn tất:

~~~java
@MessageMapping("devices.events")
public Mono<Void> receive(@Payload DeviceEvent event) {
    return eventRepository.save(toEntity(event)).then();
}
~~~

Không trả Mono<EventRecord> nếu route này được gọi bằng fire-and-forget và ứng dụng không có ý định gửi response. Request FNF không có response payload; Mono<Void> làm rõ điều đó trong chữ ký method.

### Vì sao không dùng void?

Một method Java trả void có thể thực hiện xử lý đồng bộ, nhưng không mô tả được một tác vụ reactive chưa hoàn tất. Mono<Void> cho phép Spring theo dõi vòng đời xử lý bất đồng bộ, nối tiếp thao tác database hoặc queue, và truyền tín hiệu complete/error trong pipeline phía server.

Không tự gọi subscribe() trong handler. Hãy trả Mono<Void> cho Spring để framework quản lý subscription và vòng đời của request.

## 6. Gửi fire-and-forget bằng RSocketRequester.send()

Ở phía client, dùng send() khi không cần response payload:

~~~java
public class DeviceEventClient {

    private final RSocketRequester requester;

    public DeviceEventClient(RSocketRequester requester) {
        this.requester = requester;
    }

    public Mono<Void> publish(DeviceEvent event) {
        return requester
                .route("devices.events")
                .data(event)
                .send();
    }
}
~~~

send() trả Mono<Void> vì client không nhận response object. Khi publisher hoàn tất, thao tác gửi ở phía requester đã hoàn tất theo semantics của API. Điều đó không xác nhận service phía server đã commit database hoặc hoàn thành side effect.

Phân biệt ba mốc:

| Mốc | Có thể biết từ client FNF? |
|---|---|
| Client đã gọi API và thao tác gửi hoàn tất | Có, theo tín hiệu của send() |
| Server đã nhận và dispatch request | Không có response nghiệp vụ để client xác nhận |
| Server đã hoàn tất xử lý và commit dữ liệu | Không thể suy ra từ completion của send() |

Nếu client cần biết server đã tiếp nhận hoặc xử lý thành công, hãy dùng request-response với một acknowledgement DTO hoặc xây dựng một kênh xác nhận riêng.

## 7. So sánh hai chữ ký Mono

| Tiêu chí | Request-response | Fire-and-forget |
|---|---|---|
| Chữ ký handler | Mono<Response> | Mono<Void> |
| Client API | retrieveMono(Response.class) | send() |
| Có response payload | Có, một payload | Không |
| Client nhận lỗi request từ server | Có thể nhận error signal | Không có response channel để trả lỗi nghiệp vụ |
| Mục đích | Truy vấn hoặc command cần kết quả | Event/command một chiều |
| Có thể chờ xử lý bất đồng bộ ở server | Có | Có ở phía server, nhưng client không chờ ACK nghiệp vụ |
| Retry | Cần xem xét idempotency và trạng thái kết quả | Cần event ID/deduplication vì không biết chắc server đã xử lý tới đâu |

Đừng chọn interaction model chỉ vì muốn dùng một method trả Mono. Hãy bắt đầu từ câu hỏi: client có cần một kết quả từ server hay chỉ cần gửi một thông điệp một chiều?

## 8. Xử lý lỗi trong request-response

Với request-response, lỗi từ handler có thể được truyền về requester dưới dạng error signal. Nên phân loại lỗi miền và lỗi kỹ thuật:

~~~java
@MessageMapping("devices.status")
public Mono<DeviceStatus> status(@Payload DeviceStatusQuery query) {
    return statusService.findStatus(query.deviceId())
            .switchIfEmpty(Mono.error(
                    new DeviceNotFoundException(query.deviceId())))
            .onErrorMap(DatabaseException.class,
                    error -> new DeviceServiceUnavailableException(error));
}
~~~

Ở phía client:

~~~java
public Mono<DeviceStatus> findStatus(String deviceId) {
    return requester.route("devices.status")
            .data(new DeviceStatusQuery(deviceId))
            .retrieveMono(DeviceStatus.class)
            .timeout(Duration.ofSeconds(3))
            .onErrorMap(
                    TimeoutException.class,
                    error -> new DeviceQueryTimeoutException(deviceId, error));
}
~~~

Không nên gửi stack trace, SQL hoặc thông tin nội bộ trong error message. Dùng error code hoặc kiểu lỗi miền ổn định để client quyết định hiển thị, retry hoặc yêu cầu người dùng thử lại.

## 9. Xử lý lỗi trong fire-and-forget

Vì FNF không có response payload, lỗi xử lý phía server không thể trở thành một response lỗi nghiệp vụ gửi về requester qua chính tương tác đó. Handler vẫn nên xử lý error signal ở server để log, tăng metric hoặc chuyển event vào dead-letter queue:

~~~java
@MessageMapping("devices.events")
public Mono<Void> receive(@Payload DeviceEvent event) {
    return eventService.accept(event)
            .doOnError(error ->
                    log.error("Cannot process eventId={}", event.eventId(), error));
}
~~~

doOnError chỉ quan sát lỗi, không biến lỗi thành thành công. Nếu ứng dụng chủ động dùng onErrorResume để ghi dead-letter rồi hoàn tất, cần bảo đảm thao tác ghi dead-letter thực sự hoàn tất và metric phản ánh kết quả đó.

Ở phía client, send() vẫn có thể phát lỗi nếu request không thể được gửi do connection, serialization hoặc điều kiện protocol. Hãy xử lý các lỗi gửi này:

~~~java
public Mono<Void> publish(DeviceEvent event) {
    return requester.route("devices.events")
            .data(event)
            .send()
            .doOnError(error ->
                    log.warn("FNF send failed eventId={}", event.eventId(), error));
}
~~~

Lỗi từ send() cho biết thao tác gửi gặp vấn đề; completion của send() cũng không phải acknowledgement rằng nghiệp vụ phía server đã hoàn tất.

## 10. Retry, idempotency và độ tin cậy

Request-response có thể timeout dù server đã xử lý request. Fire-and-forget còn khó đối soát hơn vì không có response để cho biết request đã đi tới đâu. Retry mù quáng có thể tạo side effect trùng lặp ở cả hai mô hình.

Với event có thể gửi lại, nên thiết kế:

1. **Event ID ổn định:** tạo ID một lần ở producer và giữ nguyên qua các lần gửi lại.
2. **Deduplication phía nhận:** lưu ID đã xử lý hoặc dùng unique constraint để tránh áp dụng side effect lần thứ hai.
3. **Idempotent handler:** cùng một event được xử lý nhiều lần vẫn cho ra trạng thái cuối như nhau.
4. **Checkpoint rõ ràng:** chỉ đánh dấu event hoàn tất sau khi nghiệp vụ đã commit.
5. **Retry có giới hạn:** exponential backoff, jitter và phân loại lỗi retryable/non-retryable.
6. **Dead-letter queue:** giữ event không thể xử lý để điều tra hoặc phát lại có kiểm soát.

Ví dụ client retry một event có event ID cố định:

~~~java
public Mono<Void> publishWithRetry(DeviceEvent event) {
    return requester.route("devices.events")
            .data(event)
            .send()
            .retryWhen(
                    Retry.backoff(3, Duration.ofMillis(200))
                            .maxBackoff(Duration.ofSeconds(2)));
}
~~~

Ví dụ này chỉ minh họa retry có giới hạn. Trước khi dùng, consumer phải hỗ trợ deduplication theo eventId; nếu không, retry có thể lưu hoặc thực hiện event nhiều lần. Không retry các lỗi serialization, validation hoặc từ chối cố định như thể chúng là lỗi mạng tạm thời.

## 11. Điều tiết tải khi gửi nhiều FNF

FNF không tạo response stream và không dùng REQUEST_N để điều tiết payload phản hồi. Vì vậy, producer có thể phát nhiều request liên tiếp nếu không có giới hạn riêng. TCP flow control chỉ điều tiết byte trên transport; nó không thay thế queue giới hạn hay quota nghiệp vụ.

Khi gửi từ một Flux, có thể giới hạn concurrency:

~~~java
public Mono<Void> publishAll(Flux<DeviceEvent> events) {
    return events
            .flatMap(this::publish, 32)
            .then();
}
~~~

Giá trị 32 là ví dụ. Hãy điều chỉnh theo năng lực server, kích thước payload và giới hạn queue. Nếu cần giữ thứ tự event, dùng concatMap hoặc phân vùng theo device/key để xử lý tuần tự.

Khi hệ thống bật RSocket LEASE, requester còn phải tuân thủ quota request do peer cấp. Lease giới hạn số request được khởi tạo trong khoảng thời gian cho phép; nó không xác nhận rằng từng event đã được xử lý nghiệp vụ.

## 12. Bảo mật và validation

Cả request-response và FNF đều là request ứng dụng, nên phải áp dụng cùng nguyên tắc bảo mật:

- Xác thực peer ở transport hoặc tầng ứng dụng theo kiến trúc triển khai.
- Phân quyền theo route và resource; không tin deviceId hoặc tenant ID chỉ vì client gửi trong payload.
- Dùng @Valid và Bean Validation cho DTO đầu vào.
- Giới hạn kích thước payload và số request mỗi connection.
- Không ghi token, credential hoặc payload nhạy cảm vào log.
- Dùng TLS khi dữ liệu cần bảo vệ trên đường truyền.
- Giới hạn concurrency và queue để giảm nguy cơ event flood.

Validation lỗi ở request-response có thể được chuyển thành error signal cho requester. Với FNF, server cần ghi nhận và xử lý lỗi ở phía nhận; client không nhận một response lỗi cho từng event.

## 13. Kiểm thử request-response

Có thể kiểm tra client nhận đúng một DTO và publisher hoàn tất:

~~~java
StepVerifier.create(client.findStatus("sensor-17"))
        .expectNextMatches(status ->
                status.deviceId().equals("sensor-17"))
        .verifyComplete();
~~~

Nên có thêm các ca:

- Route hợp lệ trả DTO đúng schema.
- Device không tồn tại trả kết quả hoặc lỗi theo hợp đồng đã chọn.
- Payload thiếu field bắt buộc bị validation từ chối.
- Service lỗi được ánh xạ thành error signal phù hợp.
- Timeout client được kích hoạt khi server phản hồi quá chậm.
- Client và server dùng MIME type/codec tương thích.

## 14. Kiểm thử fire-and-forget

Kiểm thử FNF cần xác minh hai phía riêng biệt. Phía client kiểm tra send() hoàn tất hoặc phát lỗi gửi. Phía server kiểm tra service thực sự nhận event và hoàn tất xử lý.

Ví dụ kiểm tra thao tác gửi:

~~~java
StepVerifier.create(client.publish(event))
        .verifyComplete();
~~~

Kiểm tra trên server nên chờ tín hiệu từ service hoặc một test sink/spy để xác nhận event được dispatch. Không dùng riêng completion của client.publish(event) làm bằng chứng rằng database phía server đã ghi xong.

Các ca kiểm thử nên có:

- Event hợp lệ được dispatch đúng route.
- Event ID trùng được deduplicate theo chính sách.
- Service phía server phát lỗi và metric/dead-letter được cập nhật.
- Connection đóng trước khi gửi thì client nhận lỗi gửi phù hợp.
- Burst event không làm queue vượt giới hạn.
- Retry không tạo side effect trùng lặp.

## 15. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Request-response client không nhận được DTO | Handler trả Mono<Void> hoặc route không đúng | Trả Mono<T> và kiểm tra route |
| Client dùng send() nhưng mong response | Chọn FNF trong khi cần acknowledgement | Dùng retrieveMono() và DTO xác nhận |
| FNF send hoàn tất nhưng database chưa có event | Send completion không phải business ACK; server có thể đang xử lý | Theo dõi metric phía nhận hoặc dùng request-response |
| Handler FNF trả Mono<Event> | Chữ ký không thể hiện đúng semantics một chiều | Dùng Mono<Void> và then() nếu cần bỏ giá trị |
| Handler gọi subscribe() nội bộ | Tách xử lý khỏi vòng đời request, lỗi khó quan sát | Trả publisher cho Spring |
| Retry làm event xuất hiện nhiều lần | Không có idempotency/deduplication | Giữ event ID ổn định và deduplicate |
| Request-response timeout nhưng server đã thực hiện side effect | Timeout không hủy chắc chắn nghiệp vụ đã chạy | Dùng idempotency key và kiểm tra trạng thái |
| FNF handler lỗi nhưng client không thấy lỗi | FNF không có response channel | Log/metric/dead-letter ở server hoặc dùng ACK riêng |

## 16. Checklist trước khi đưa vào production

- [ ] Route được đặt tên rõ và thống nhất giữa client/server.
- [ ] Request-response handler trả Mono<T> với schema response ổn định.
- [ ] Fire-and-forget handler trả Mono<Void> và không phát response object.
- [ ] Client dùng retrieveMono() cho request-response và send() cho FNF.
- [ ] Trường hợp không tìm thấy dữ liệu được định nghĩa rõ.
- [ ] Timeout và retry phù hợp với tính idempotent của thao tác.
- [ ] Event một chiều có event ID, deduplication và chính sách dead-letter nếu cần.
- [ ] Đã giới hạn tốc độ/concurrency và kích thước payload.
- [ ] Đã đo riêng số request gửi, số event server xử lý và số event lỗi.
- [ ] Đã kiểm thử lỗi transport, validation, service và shutdown.

## Kết luận

Trong Spring RSocket, request-response thường dùng handler trả Mono<T> và client gọi retrieveMono(...) để nhận một response payload. Fire-and-forget dùng handler trả Mono<Void> và client gọi send() để gửi một chiều. Mono<Void> cho phép server thực hiện công việc bất đồng bộ mà không tạo response; completion của send() ở client chỉ phản ánh thao tác gửi, không phải xác nhận nghiệp vụ phía server đã commit. Hãy chọn interaction model theo nhu cầu phản hồi, xử lý lỗi đúng phía, và dùng event ID cùng idempotency khi cần retry.

## Tài liệu tham khảo

- [Spring Framework Reference – RSocket Messaging](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework Javadoc – RSocketRequester](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html)
- [RSocket Protocol – Request-response and Fire-and-forget](https://rsocket.io/about/protocol/)
