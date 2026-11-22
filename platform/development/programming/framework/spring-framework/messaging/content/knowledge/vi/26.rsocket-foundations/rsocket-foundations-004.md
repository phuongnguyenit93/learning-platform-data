# Fire-and-forget và giới hạn xác nhận xử lý trong RSocket

## Mục tiêu

RSocket hỗ trợ nhiều kiểu tương tác giữa hai đầu kết nối. **Fire-and-forget** (FNF) là kiểu gửi một message một chiều: requester gửi payload tới responder và không yêu cầu response payload. Đây là lựa chọn nhẹ cho những sự kiện có thể chấp nhận xử lý theo kiểu best-effort, chẳng hạn telemetry, chỉ báo đang gõ hoặc cập nhật trạng thái tạm thời.

Điểm cần hiểu rõ nhất là: **gửi thành công không đồng nghĩa xử lý thành công**. Trong Spring, phương thức **RSocketRequester.send()** trả về một **Mono không phát ra giá trị**. Theo tài liệu Spring, Mono này chỉ cho biết message đã được gửi thành công; nó không xác nhận responder đã nhận, lưu, xử lý hoặc hoàn tất nghiệp vụ.

Vì vậy, chọn FNF phải dựa trên mức độ quan trọng của message và mức xác nhận mà nghiệp vụ cần. Nếu cần biết server đã chấp nhận một lệnh hoặc đã hoàn tất xử lý, hãy dùng Request-Response hoặc một giao thức xác nhận riêng.

## 1. Fire-and-forget trong bốn interaction model của RSocket

RSocket là giao thức giao tiếp hai chiều, multiplex trên một kết nối và hỗ trợ các transport như TCP hoặc WebSocket. Hai phía đều có thể khởi tạo request; vì vậy thuật ngữ chính xác là requester và responder thay vì mặc định client và server.

RSocket có bốn interaction model chính:

| Interaction model | Dữ liệu gửi | Dữ liệu nhận | Trường hợp sử dụng |
|---|---|---|---|
| Request-Response | Một message | Một response | Gửi lệnh và cần kết quả hoặc xác nhận |
| Request-Stream | Một message | Một stream response | Gửi tiêu chí tìm kiếm rồi nhận nhiều kết quả |
| Request-Channel | Một stream message | Một stream response hai chiều | Trao đổi dữ liệu liên tục theo hai hướng |
| Fire-and-Forget | Một message | Không có response payload | Gửi telemetry hoặc sự kiện tạm thời, không cần xác nhận xử lý |

Trong protocol, Fire-and-Forget được biểu diễn bằng frame REQUEST_FNF. Requester gửi một payload cho responder. Responder không gửi một response payload tương ứng như Request-Response hoặc Request-Stream.

Một request FNF vẫn có route và payload. Metadata có thể chứa route hoặc thông tin khác; data chứa nội dung nghiệp vụ. Nhưng không có response message để requester đọc kết quả xử lý.

## 2. Giới hạn xác nhận: send hoàn tất không phải handler hoàn tất

Ở phía Spring, cách gọi FNF phổ biến là:

~~~java
Mono<Void> result = requester
        .route("telemetry.record")
        .data(event)
        .send();
~~~

Phương thức send() trả về Mono không phát ra giá trị. Khi Mono hoàn tất bình thường, điều đó chỉ xác nhận thao tác gửi của requester đã hoàn tất theo API Spring. Nó **không chứng minh** các việc sau đã xảy ra:

- Responder đã chạy phương thức xử lý.
- Payload đã vượt qua mọi validation nghiệp vụ.
- Database đã ghi dữ liệu thành công.
- Message đã được lưu bền vững.
- Consumer tiếp theo đã nhận hoặc xử lý sự kiện.
- Một side effect như gửi email, cập nhật số dư hoặc tạo đơn hàng đã hoàn tất.

Cần tách ba mốc thời gian:

1. **Send completion**: phía gửi hoàn tất thao tác gửi message.
2. **Handler completion**: responder hoàn tất xử lý trong ứng dụng.
3. **Business completion**: kết quả nghiệp vụ đã đạt điều kiện mà hệ thống cam kết, ví dụ dữ liệu đã commit hoặc side effect đã hoàn tất.

Với FNF, requester không nhận được application-level acknowledgement để biết mốc 2 hoặc mốc 3. Dù handler phía responder trả về Mono không phát giá trị và Mono đó hoàn tất sau khi ghi database, completion đó vẫn không được gửi ngược thành một response của request FNF.

Đây là giới hạn cốt lõi của interaction model, không phải lỗi của Reactor hay Spring.

## 3. Gửi Fire-and-Forget bằng RSocketRequester

Ví dụ requester kết nối tới RSocket server qua TCP:

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;

RSocketRequester requester =
        RSocketRequester.builder().tcp("localhost", 7000);
~~~

Trong Spring, builder tạo một RSocketRequester. Kết nối được thiết lập khi requester thực hiện request đầu tiên; các request sau có thể dùng chung kết nối.

Tạo một publisher gửi telemetry:

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class TelemetryPublisher {

    private final RSocketRequester requester;

    public TelemetryPublisher(RSocketRequester requester) {
        this.requester = requester;
    }

    public Mono<Void> publish(TelemetryEvent event) {
        return requester
                .route("telemetry.record")
                .data(event)
                .send();
    }
}

record TelemetryEvent(
        String eventId,
        String type,
        long occurredAt
) {}
~~~

Các bước:

1. route("telemetry.record") chọn route của responder.
2. data(event) cung cấp payload cần gửi.
3. send() chọn interaction Fire-and-Forget và trả về Mono không có giá trị.
4. Caller quyết định cách kết hợp Mono với luồng xử lý reactive của mình.

Nếu một service khác đang chạy trong Reactor, hãy trả Mono này cho caller hoặc ghép nó vào pipeline:

~~~java
public Mono<Void> recordAndPublish(TelemetryEvent event) {
    return telemetryRepository.save(event)
            .then(telemetryPublisher.publish(event));
}
~~~

Đoạn trên chỉ minh họa composition của reactive pipeline. Nếu việc lưu telemetry và gửi RSocket phải có tính nguyên tử hoặc không được mất message khi tiến trình dừng, cần một thiết kế bền vững như Transactional Outbox; một lệnh save rồi send riêng lẻ không tạo thành transaction phân tán.

### Phải subscribe để request thực sự được thực thi

Reactor Publisher có tính lazy. Việc tạo Mono chưa tự chạy thao tác gửi. Mono cần được subscribe, hoặc được framework/caller subscribe khi pipeline được thực thi.

Trong một reactive controller hoặc service, thông thường hãy trả Mono về cho framework hoặc caller quản lý:

~~~java
public Mono<Void> handleTelemetry(TelemetryEvent event) {
    return telemetryPublisher.publish(event);
}
~~~

Ở một ranh giới imperative như scheduled job, có thể chủ động subscribe và xử lý lỗi:

~~~java
telemetryPublisher.publish(event)
        .doOnError(error ->
                log.warn("Không gửi được telemetry qua RSocket", error))
        .subscribe();
~~~

Không gọi block() trong event loop hoặc reactive request path vì có thể chặn thread xử lý. Cũng không nên gọi subscribe() tùy tiện bên trong mọi service: làm như vậy sẽ tách việc gửi khỏi lifecycle và error handling của caller.

Tên log nên phản ánh đúng điều đã xác nhận. Ví dụ “FNF send completed” phù hợp hơn “Telemetry processed successfully”.

## 4. Nhận Fire-and-Forget bằng @MessageMapping

Ở phía responder, Spring dùng @MessageMapping để ánh xạ route tới phương thức xử lý. Ví dụ server nhận telemetry tại route telemetry.record:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class TelemetryController {

    private final TelemetryService telemetryService;

    public TelemetryController(TelemetryService telemetryService) {
        this.telemetryService = telemetryService;
    }

    @MessageMapping("telemetry.record")
    public Mono<Void> record(TelemetryEvent event) {
        return telemetryService.record(event);
    }
}

record TelemetryEvent(
        String eventId,
        String type,
        long occurredAt
) {}

interface TelemetryService {
    Mono<Void> record(TelemetryEvent event);
}
~~~

Ứng dụng cần cấu hình RSocket server và RSocketMessageHandler để phát hiện các annotated responder. Đoạn code trên là controller/service minh họa, không phải một chương trình Java độc lập.

Với một payload đầu vào và kết quả không phát giá trị, Spring có thể ánh xạ phương thức responder cho interaction FNF. Kiểu Mono không phát giá trị cho phép xử lý bất đồng bộ mà không tạo response payload.

Trong responder:

- Validate payload trước khi thực hiện side effect.
- Dùng event ID để hỗ trợ deduplication nếu producer có thể gửi lại.
- Ghi log có correlation ID và route.
- Xử lý lỗi trong pipeline hoặc chuyển lỗi tới cơ chế xử lý lỗi của ứng dụng.
- Không giả định requester sẽ nhận được exception hoặc kết quả từ handler như một response nghiệp vụ.

Nếu cần trả trạng thái accepted hoặc rejected cho requester, hãy đổi contract sang Request-Response.

## 5. Khi nào nên dùng Fire-and-Forget?

FNF phù hợp khi mất một message riêng lẻ không làm sai lệch trạng thái nghiệp vụ quan trọng, hoặc dữ liệu mới hơn sẽ sớm thay thế dữ liệu cũ.

Ví dụ thường phù hợp:

- Telemetry và metric có thể chấp nhận mất một số mẫu.
- Chỉ báo người dùng đang gõ trong một cuộc trò chuyện.
- Cập nhật vị trí con trỏ hoặc trạng thái giao diện tạm thời.
- Sự kiện quan sát không quyết định kết quả nghiệp vụ.
- Tín hiệu refresh cache có thể được phát lại từ nguồn khác.

FNF thường không phù hợp khi requester cần biết một lệnh có được chấp nhận hay không:

- Tạo đơn hàng.
- Thanh toán hoặc hoàn tiền.
- Trừ tồn kho hoặc thay đổi số dư.
- Thay đổi quyền truy cập.
- Ghi audit bắt buộc.
- Gửi thông báo quan trọng có yêu cầu theo dõi giao nhận.
- Một thao tác mà người dùng phải nhìn thấy rõ trạng thái thành công hoặc thất bại.

Không chọn FNF chỉ vì nó ngắn hơn hoặc ít code hơn. Hãy chọn theo hợp đồng giao tiếp mà nghiệp vụ có thể chấp nhận.

## 6. Giới hạn phản hồi và backpressure

FNF không cung cấp response payload hay acknowledgement theo từng request. Do đó requester không có tín hiệu ở cấp nghiệp vụ để biết responder đang xử lý nhanh hay chậm, hoặc một message đã được xử lý xong chưa.

### Không có xác nhận để điều chỉnh tốc độ theo kết quả xử lý

Với Request-Stream và Request-Channel, RSocket có cơ chế demand để requester và responder điều tiết số lượng message trong stream. FNF không có response stream tương ứng và không cung cấp demand dựa trên việc hoàn tất từng tác vụ nghiệp vụ.

Transport vẫn có cơ chế quản lý truyền dữ liệu, nhưng điều đó không thay thế giới hạn tốc độ xử lý ở tầng ứng dụng. Nếu producer gửi nhanh hơn consumer có thể xử lý, hệ thống vẫn có nguy cơ tích tụ công việc, tăng độ trễ hoặc cạn tài nguyên.

Nên áp dụng:

- Giới hạn tốc độ phát message.
- Queue có giới hạn dung lượng.
- Giới hạn concurrency ở worker xử lý.
- Batch hoặc gộp các cập nhật có thể hợp nhất.
- Drop policy rõ ràng cho telemetry có thể mất.
- Metric cho số message nhận, xử lý, lỗi và bị loại bỏ.

Không tạo một queue vô hạn trong RAM với kỳ vọng responder sẽ xử lý kịp mọi message.

### Không có response để truyền lỗi nghiệp vụ về requester

Nếu responder từ chối payload, validation thất bại hoặc xử lý database phát sinh lỗi, requester không nhận một response payload để biết chi tiết kết quả của thao tác đó.

Ứng dụng responder phải tự quan sát lỗi bằng log, metric, tracing hoặc cơ chế xử lý nội bộ. Nếu producer cần biết lý do từ chối, hãy dùng Request-Response với một kiểu kết quả rõ ràng.

### Không có bảo đảm hoàn tất đúng một lần

FNF không tự tạo ra bảo đảm exactly-once cho xử lý nghiệp vụ. Nếu producer không rõ message đã tới responder hay chưa và tự gửi lại, responder có thể xử lý trùng. Nếu producer không gửi lại, một sự cố kết nối có thể làm message không được xử lý.

Khi retry, hãy dùng event ID hoặc idempotency key và thiết kế consumer xử lý lặp an toàn. Đừng dùng việc không nhận được response làm bằng chứng chắc chắn rằng responder chưa xử lý.

## 7. Chọn Request-Response khi cần xác nhận

Nếu caller cần biết server đã chấp nhận hoặc xử lý xong lệnh, dùng Request-Response. Responder trả một object; requester dùng retrieveMono() để nhận response.

Ví dụ contract xác nhận server đã ghi nhận lệnh:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("orders.submit")
    public Mono<SubmissionAck> submit(OrderCommand command) {
        return orderService.accept(command)
                .map(orderId -> new SubmissionAck(orderId, "ACCEPTED"));
    }
}

record OrderCommand(String idempotencyKey, String productId, int quantity) {}

record SubmissionAck(String orderId, String status) {}
~~~

Requester:

~~~java
Mono<SubmissionAck> acknowledgement = requester
        .route("orders.submit")
        .data(command)
        .retrieveMono(SubmissionAck.class);
~~~

Ở đây, requester nhận một response có kiểu. Tuy nhiên, ý nghĩa của acknowledgement phụ thuộc thời điểm responder tạo nó:

- ACCEPTED: server đã xác thực, kiểm tra và lưu lệnh vào nơi bền vững để xử lý sau.
- COMPLETED: nghiệp vụ đã hoàn tất theo điều kiện được contract định nghĩa.
- REJECTED: server từ chối lệnh và có thể trả mã/lý do phù hợp.

Đừng trả COMPLETED ngay sau khi chỉ đưa lệnh vào một queue nội bộ. Đặt tên trạng thái theo mốc thực tế mà server đã đạt được.

Nếu thao tác mất nhiều thời gian, một mẫu thường dùng là trả ACCEPTED cùng operation ID, sau đó cung cấp endpoint hoặc stream trạng thái để caller theo dõi đến khi hoàn tất.

## 8. So sánh cách chọn interaction model

| Nhu cầu | Interaction nên chọn | Lý do |
|---|---|---|
| Gửi một sự kiện tạm thời, không cần kết quả | Fire-and-Forget | Một chiều, không có response payload |
| Gửi lệnh và cần accepted/rejected | Request-Response | Có một response xác nhận |
| Gửi tiêu chí rồi nhận nhiều kết quả | Request-Stream | Một request, nhiều response |
| Hai bên trao đổi nhiều message liên tục | Request-Channel | Stream hai chiều và có demand |
| Gửi lệnh quan trọng cần theo dõi hoàn tất | Request-Response cộng operation status | Tách xác nhận tiếp nhận khỏi trạng thái xử lý cuối |

Một ứng dụng có thể dùng nhiều interaction model trên cùng kết nối RSocket. Chọn theo từng route và contract, không cần ép toàn bộ API dùng một kiểu.

## 9. Làm cho FNF an toàn hơn khi được phép mất hoặc gửi lặp

Dù FNF không có acknowledgement, vẫn có thể tăng khả năng quan sát và giảm tác động khi message bị mất hoặc trùng.

### Gắn event ID và thời điểm phát

Mỗi message nên có ID duy nhất hoặc idempotency key, thời điểm phát và loại sự kiện:

~~~java
record TelemetryEvent(
        String eventId,
        String source,
        String type,
        long occurredAt
) {}
~~~

Responder có thể dùng event ID để loại bỏ sự kiện trùng nếu nghiệp vụ yêu cầu. Timestamp giúp phát hiện dữ liệu cũ hoặc đảo thứ tự. Không dùng timestamp đơn lẻ làm khóa idempotency vì nhiều sự kiện có thể cùng thời điểm.

### Giới hạn queue và chính sách drop

Nếu producer tạo event nhanh, hãy chọn chính sách cụ thể:

- Drop newest: bỏ message mới khi queue đầy.
- Drop oldest: bỏ message cũ để giữ trạng thái mới hơn.
- Coalesce: gộp nhiều cập nhật thành một cập nhật cuối.
- Reject upstream: báo cho thành phần tạo dữ liệu giảm tốc.
- Persist: ghi dữ liệu vào storage bền vững nếu không thể mất.

Chọn policy theo loại dữ liệu. Với vị trí con trỏ, giữ trạng thái mới nhất có thể hợp lý. Với audit event, drop không phù hợp.

### Dùng Transactional Outbox khi producer không được phép làm mất sự kiện

Nếu một thay đổi database và một message phải được phát cùng nhau, ghi thay đổi nghiệp vụ và bản ghi outbox trong cùng transaction. Worker đọc outbox rồi phát message sau.

Outbox giải quyết rủi ro tiến trình dừng sau khi commit dữ liệu nhưng trước khi gửi message. Tuy nhiên, nếu worker chỉ phát FNF, nó vẫn không biết responder đã hoàn tất xử lý. Outbox phía producer giúp quản lý việc phát lại; nó không biến FNF thành một giao thức có xác nhận xử lý.

Nếu cần theo dõi xác nhận từ responder, hãy bổ sung Request-Response, acknowledgement route riêng hoặc một cơ chế bền vững có trạng thái giao nhận được định nghĩa rõ.

## 10. Kiểm thử Fire-and-Forget đúng cách

Nên kiểm thử hai phía riêng biệt vì completion ở requester không xác nhận completion của responder.

### Kiểm thử requester

Có thể xác minh rằng requester tạo và subscribe đúng publisher, xử lý lỗi kết nối hoặc lỗi serialization, và không biến lỗi gửi thành thành công giả.

Với Reactor Test, StepVerifier có thể xác minh Mono hoàn tất hoặc phát lỗi:

~~~java
StepVerifier.create(publisher.publish(event))
        .verifyComplete();
~~~

Test này chỉ xác minh publisher phía requester hoàn tất bình thường trong test setup. Nó không chứng minh responder đã ghi dữ liệu hoặc hoàn tất side effect.

### Kiểm thử responder và luồng tích hợp

Với integration test, cần quan sát trực tiếp kết quả ở phía responder:

1. Khởi động RSocket server và handler.
2. Kết nối requester.
3. Gửi một event FNF có event ID xác định.
4. Chờ tín hiệu test hoặc truy vấn storage phía responder.
5. Xác minh handler đã xử lý event theo contract.
6. Gửi lại cùng event ID và xác minh deduplication nếu được yêu cầu.
7. Ngắt kết nối hoặc dừng server trong lúc gửi để kiểm tra error path.
8. Xác minh metric/log phản ánh đúng số lần gửi và số lần xử lý.

Không dùng một verifyComplete() ở requester làm bằng chứng duy nhất rằng nghiệp vụ phía responder đã hoàn tất.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Tưởng send() hoàn tất nghĩa là server xử lý xong | Nhầm send completion với handler/business completion | Dùng Request-Response nếu cần acknowledgement |
| Mono được tạo nhưng không có message nào được gửi | Chưa subscribe hoặc chưa trả publisher cho framework | Kết nối Mono vào pipeline được thực thi |
| Service tự subscribe khiến lỗi bị mất khỏi caller | Tách publisher khỏi lifecycle của luồng gọi | Trả Mono cho caller; subscribe ở ranh giới imperative |
| Gọi block trong reactive request path | Chặn event-loop hoặc thread xử lý | Compose Mono thay vì block |
| Producer làm đầy tài nguyên responder | Không giới hạn tốc độ hoặc queue | Rate limit, bounded queue, concurrency limit |
| Retry tạo xử lý trùng | Không có event ID hoặc idempotency | Deduplicate theo idempotency key |
| Không biết vì sao responder từ chối event | FNF không trả response nghiệp vụ | Ghi log/metric phía responder hoặc chuyển sang Request-Response |
| Outbox được đánh dấu hoàn tất quá sớm | Chỉ dựa vào local send completion | Định nghĩa rõ mốc xác nhận; dùng acknowledgement nếu cần |

## 12. Checklist trước khi chọn Fire-and-Forget

- [ ] Message thực sự không cần response payload.
- [ ] Nghiệp vụ chấp nhận việc requester không biết responder đã xử lý hay chưa.
- [ ] Mất một message riêng lẻ không gây sai lệch trạng thái quan trọng.
- [ ] Có event ID hoặc idempotency key nếu gửi lặp có thể xảy ra.
- [ ] Producer có giới hạn tốc độ và queue.
- [ ] Responder có logging, metric và error handling riêng.
- [ ] Mono từ send được subscribe hoặc trả cho framework/caller quản lý.
- [ ] Không diễn giải send completion thành business completion.
- [ ] Có chính sách retry/drop/persist phù hợp với loại dữ liệu.
- [ ] Dùng Request-Response nếu caller cần accepted/rejected hoặc kết quả hoàn tất.
- [ ] Kiểm thử riêng requester send và responder processing.

## Tài liệu tham khảo

- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Javadoc — RSocketRequester](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html)
- [Spring Javadoc — RSocketRequester.RequestSpec](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.RequestSpec.html)
- [Project Reactor — Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
- [RSocket Protocol](https://rsocket.io/about/protocol/)
