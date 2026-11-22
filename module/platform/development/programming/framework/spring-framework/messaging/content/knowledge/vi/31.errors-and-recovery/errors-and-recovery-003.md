# Timeout không đồng nghĩa với tác vụ phía nhận đã dừng

## 1. Tình huống và mục tiêu

Một ứng dụng gửi yêu cầu tạo báo cáo tới service khác. Client chỉ chờ tối đa ba giây. Sau ba giây, Reactor phát TimeoutException và ứng dụng trả lỗi timeout cho người dùng. Nhưng service nhận có thể đã bắt đầu truy vấn dữ liệu, ghi kết quả vào cơ sở dữ liệu hoặc đẩy công việc vào một executor. Việc client ngừng chờ không tự chứng minh những hoạt động đó đã dừng.

Cần tách bốn sự kiện:

1. **Caller timeout:** phía gọi hết thời gian chờ và không muốn tiếp tục đợi kết quả.
2. **Subscription cancellation:** subscriber hủy subscription đang theo dõi publisher.
3. **Remote stream cancellation:** cancellation được truyền qua transport/giao thức tới stream đang hoạt động ở phía nhận.
4. **Task termination:** code nghiệp vụ, worker hoặc hệ thống bên ngoài thực sự dừng công việc.

Bốn sự kiện có thể nối tiếp nhau, nhưng không đồng nghĩa và không phải lúc nào cũng xảy ra đầy đủ. Một timeout ở client có thể hủy subscription upstream; RSocket có thể truyền việc hủy đó bằng frame CANCEL. Tuy vậy, tác vụ phía nhận chỉ dừng nếu nó còn gắn với vòng đời của stream và có khả năng phản ứng với cancellation. Side effect đã commit cũng không tự động được hoàn tác.

Mục tiêu của bài là biết timeout đang giới hạn điều gì, xác định cancellation dừng ở lớp nào, thiết kế công việc có thể hủy và xử lý kết quả không chắc chắn sau timeout.

## 2. Phân biệt timeout, cancellation và task termination

| Khái niệm | Ý nghĩa | Có bảo đảm tác vụ nghiệp vụ đã dừng? |
| --- | --- | --- |
| Caller timeout | Người gọi hết thời gian chờ một kết quả. | Không. |
| Subscription cancellation | Subscriber gọi cancel hoặc operator hủy upstream. | Chỉ yêu cầu publisher dừng; publisher phải phản ứng với yêu cầu đó. |
| RSocket CANCEL | Frame hủy một stream đang hoạt động theo stream ID. | Kết thúc stream ở responder; không tự định nghĩa cách dừng worker hay rollback nghiệp vụ. |
| Task termination | Code thực thi đã thoát, worker đã ngừng hoặc hệ thống đích xác nhận hủy. | Có, trong phạm vi task được xác nhận đã dừng. |
| Side-effect rollback | Dữ liệu đã ghi được hoàn tác theo transaction hoặc nghiệp vụ bù trừ. | Không được suy ra từ timeout hay cancellation. |

Hãy dùng câu hỏi cụ thể khi điều tra: “Caller đã hết hạn chờ?”, “Subscription có nhận cancel?”, “RSocket stream có nhận CANCEL?”, “Worker đã dừng?”, “Side effect đã commit chưa?”. Một log duy nhất ghi “timeout” không trả lời được tất cả câu hỏi này.

### 2.1. Timeout là giới hạn thời gian quan sát

Timeout thường trả lời câu hỏi: “Tôi còn chờ kết quả này bao lâu?”. Nó không nhất thiết trả lời câu hỏi: “Công việc ở service nhận được phép chạy bao lâu?”.

Ví dụ, timeout ba giây ở client có thể xảy ra khi:

- Request chưa tới service nhận vì mạng hoặc hàng đợi bị chậm.
- Service đã nhận request nhưng chưa bắt đầu xử lý.
- Service đang xử lý và chưa có kết quả.
- Service đã ghi kết quả thành công nhưng response chưa về tới client.
- Response đã về nhưng client hoặc gateway không xử lý kịp.

Ở phía client, các tình huống này có thể đều biểu hiện thành timeout. Nhưng trạng thái thực tế của nghiệp vụ khác nhau.

### 2.2. Cancellation là yêu cầu dừng, không phải bằng chứng đã dừng

Reactive Streams định nghĩa Subscription.cancel() để subscriber yêu cầu publisher ngừng phát dữ liệu. Cancellation là tín hiệu điều khiển theo chiều subscriber → publisher. Nó không phải onComplete, không phải onError và không có nghĩa các side effect trước đó đã bị xóa.

Publisher cần hợp tác với cancellation. Một publisher dựa trên timer hoặc nguồn reactive có thể hủy công việc upstream. Một hàm blocking, vòng lặp CPU không kiểm tra interruption, truy vấn database không hỗ trợ cancel hoặc tác vụ đã được đẩy vào queue có thể tiếp tục chạy.

Cancellation cũng có thể đua với việc hoàn tất: worker có thể hoàn thành hoặc commit dữ liệu ngay trước khi nhận được yêu cầu hủy. Ứng dụng phải xác định trạng thái nghiệp vụ bằng dữ liệu có thẩm quyền, không suy đoán từ thời điểm client timeout.

## 3. Các loại timeout cần phân biệt

| Loại timeout | Phạm vi | Điều cần nhớ |
| --- | --- | --- |
| Timeout ở caller | Thời gian ứng dụng gọi chờ response. | Caller có thể dừng chờ trong khi receiver tiếp tục làm việc. |
| Reactor Mono.timeout | Thời gian chờ tín hiệu dữ liệu đầu tiên từ Mono. | Khi hết hạn, Mono phát TimeoutException hoặc chuyển sang fallback và hủy subscription nguồn. |
| Reactor Flux.timeout(Duration) | Khoảng thời gian không có phần tử mới. | Timer áp dụng từ lúc subscribe cho phần tử đầu tiên và được tính lại từ phần tử trước; đây là idle timeout theo từng phần tử, không phải tổng thời lượng stream. |
| Transport/connection timeout | Trạng thái truyền thông, keepalive hoặc kết nối. | Kết nối không phản hồi không cho biết chắc worker phía nhận đã dừng. |
| Server-side deadline | Ngân sách thời gian mà service nhận tự áp dụng cho nghiệp vụ. | Phải được thực thi ở phía nhận và truyền tiếp cho các công việc con nếu muốn giới hạn toàn bộ chuỗi xử lý. |

### 3.1. Reactor Mono.timeout

Với Mono, timeout(Duration) phát TimeoutException nếu không có phần tử dữ liệu đến trong thời gian quy định. Phiên bản có fallback chuyển sang publisher dự phòng khi timeout. Khi timeout xảy ra, operator hủy subscription tới source cũ.

Điểm quan trọng là vị trí đặt hook quan sát:

~~~java
Mono<Report> result = reportService.generate()
    .doFinally(signal ->
        log.info("source lifecycle: {}", signal))
    .timeout(Duration.ofSeconds(3))
    .doOnError(TimeoutException.class, error ->
        log.warn("caller timed out"))
    .doFinally(signal ->
        log.info("caller pipeline lifecycle: {}", signal));
~~~

Nếu source chưa phát dữ liệu sau ba giây:

- doFinally đặt trước timeout nằm ở phía source, nên nhận SignalType.CANCEL khi timeout hủy subscription nguồn.
- doOnError đặt sau timeout quan sát TimeoutException ở phía caller.
- doFinally cuối pipeline nhận SignalType.ON_ERROR nếu lỗi được chuyển xuống downstream.

Một timeout có thể vì thế tạo ra **CANCEL ở source và ON_ERROR ở caller** trong cùng một pipeline. Hai hook quan sát hai vị trí khác nhau.

Nếu thêm onErrorResume để trả fallback, caller có thể nhận kết quả dự phòng và pipeline cuối cùng hoàn tất với ON_COMPLETE. Việc fallback thành công không chứng minh công việc ban đầu đã dừng.

### 3.2. Reactor Flux.timeout là idle timeout

Với Flux, timeout(Duration) đo khoảng cách giữa hai phần tử liên tiếp: từ lúc subscribe tới phần tử đầu tiên, rồi từ mỗi phần tử tới phần tử tiếp theo. Nếu một khoảng chờ vượt giới hạn, operator phát TimeoutException hoặc chuyển sang fallback.

Nếu yêu cầu nghiệp vụ là “toàn bộ stream phải kết thúc trong 30 giây”, idle timeout không diễn đạt đúng yêu cầu đó. Hãy áp dụng một deadline tổng riêng cho stream, ví dụ dùng giới hạn thời gian tổng phù hợp hoặc một timer/deadline publisher độc lập. Đặt tên metric và cấu hình rõ ràng để phân biệt idle timeout với total deadline.

### 3.3. Timeout ở transport và ở server

Keepalive/timeout của kết nối phát hiện vấn đề ở lớp truyền thông. Chúng không tự đặt deadline cho truy vấn, tác vụ nền hay transaction trong ứng dụng.

Nếu server cần dừng công việc sau một ngân sách nhất định, server phải tự kiểm tra deadline. Khi request đi qua nhiều service, mỗi service cần nhận ngân sách còn lại hoặc deadline chung và áp dụng giới hạn cho công việc của mình. Không nên để mỗi hop tự cấp lại toàn bộ timeout ban đầu vì tổng thời gian có thể vượt xa ngân sách caller.

## 4. Cancellation qua RSocket

RSocket truyền các interaction bằng stream có ID riêng. Bên mở một request là **requester**, bên nhận request là **responder**. Một kết nối có thể có request theo cả hai hướng.

### 4.1. Frame CANCEL

RSocket định nghĩa frame **CANCEL** với frame type **0x09**. Frame chứa stream ID của request cần hủy.

Khi requester gửi CANCEL cho stream đang hoạt động:

1. Stream kết thúc ở requester.
2. Responder nhận CANCEL và kết thúc stream tương ứng.
3. Responder không nên gửi response cho Request-Response sau khi đã nhận CANCEL.

Đây là ngữ nghĩa vòng đời stream trong giao thức. Nó không quy định rằng một executor, thread, database query, message queue hoặc dịch vụ bên ngoài phải tự động hủy công việc. Framework có thể truyền cancellation tới publisher được handler trả về; code nghiệp vụ phải tiếp tục nối cancellation tới tài nguyên thực tế.

Nếu response đã được gửi và stream đã kết thúc trước khi CANCEL tới, cancellation đến quá muộn để thu hồi response hoặc side effect.

### 4.2. CANCEL không giống ERROR[CANCELED]

Cần phân biệt hai thông điệp:

- **Frame CANCEL (0x09):** requester yêu cầu kết thúc một stream đang hoạt động.
- **ERROR[CANCELED] (error code 0x00000203):** responder báo rằng nó đã hủy request. Theo giao thức, responder có thể đã bắt đầu xử lý; thông báo này không bảo đảm không có side effect.

Đặc tả RSocket phân biệt ERROR[REJECTED] với ERROR[CANCELED]: REJECTED bảo đảm request không được xử lý, còn CANCELED không bảo đảm điều đó. Vì vậy không được coi mọi trạng thái “canceled” là bằng chứng an toàn để gửi lại một lệnh ghi dữ liệu.

### 4.3. Các interaction model và khả năng hủy

| Interaction | Hành vi | Ý nghĩa khi timeout |
| --- | --- | --- |
| Request-Response | Một request, tối đa một response. | Nếu request còn hoạt động, requester có thể hủy stream bằng CANCEL. Nếu service đã commit trước khi response bị trễ, side effect vẫn tồn tại. |
| Request-Stream | Một request, chuỗi response. | Requester có thể gửi CANCEL khi không còn cần stream. Publisher nguồn phải hợp tác để dừng công việc. |
| Request-Channel | Hai phía trao đổi chuỗi dữ liệu; mỗi phía có thể gửi COMPLETE. | COMPLETE từ một phía chỉ kết thúc chiều gửi của phía đó. CANCEL kết thúc stream đang hoạt động. |
| Request-Fire-and-Forget | Gửi thông điệp một chiều, không có response. | Stream kết thúc theo giao thức sau khi request được gửi/nhận; không có request đang hoạt động để gửi CANCEL về sau. Muốn hủy job đã nhận phải có cơ chế nghiệp vụ riêng. |

Đặc biệt, Fire-and-Forget thường được dùng để kích hoạt công việc nền. Nếu service nhận đưa công việc vào queue rồi kết thúc stream, caller không thể dựa vào cancellation của stream đã kết thúc để thu hồi job. Hãy trả về job ID bằng Request-Response nếu cần theo dõi trạng thái, rồi thiết kế route/command riêng cho yêu cầu hủy.

### 4.4. Luồng sự kiện khi timeout ở requester

~~~text
Requester / ứng dụng gọi
    |
    | Mono.timeout(3 giây) hết hạn
    v
TimeoutException ở caller
    |
    +--> timeout operator hủy subscription nguồn
             |
             v
       RSocket requester
             |
             | Nếu stream còn hoạt động và transport còn dùng được
             v
       Frame CANCEL(streamId)
             |
             v
       RSocket responder
             |
             v
       Publisher của @MessageMapping nhận cancel
             |
             v
       Service / worker có thể nhận yêu cầu dừng
             |
             v
       Task thực sự dừng nếu triển khai cancellation-aware
~~~

Đường đi có thể bị ngắt bởi race, lỗi kết nối hoặc subscription tách rời. Dù responder nhận CANCEL, task vẫn có thể tiếp tục nếu code đã tách nó khỏi publisher hoặc thư viện phía dưới không hỗ trợ hủy.

## 5. Áp dụng trong Spring Framework và Reactor

### 5.1. Đặt timeout ở requester

Ví dụ với RSocketRequester:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;

import reactor.core.publisher.Mono;

Mono<Report> report = requester.route("reports.generate")
    .data(command)
    .retrieveMono(Report.class)
    .doFinally(signal ->
        log.info("RSocket source ended: {}", signal))
    .timeout(Duration.ofSeconds(3))
    .doOnError(TimeoutException.class, error ->
        log.warn("Report request exceeded caller deadline"))
    .doFinally(signal ->
        log.info("Caller pipeline ended: {}", signal));
~~~

Đây là giới hạn thời gian chờ của requester. Khi timeout, source subscription bị hủy. Với request RSocket còn hoạt động, client implementation có thể truyền cancellation bằng CANCEL. Ứng dụng vẫn phải kiểm tra trạng thái công việc nếu kết quả có thể đã được tạo hoặc commit.

Nếu dùng fallback:

~~~java
Mono<ReportResult> result = requester.route("reports.generate")
    .data(command)
    .retrieveMono(ReportResult.class)
    .timeout(
        Duration.ofSeconds(3),
        Mono.just(ReportResult.pending(command.requestId()))
    );
~~~

Fallback ở đây chỉ là phản hồi thay thế cho caller. Giá trị pending không tự tạo ra trạng thái job ở server; server phải có cơ chế lưu và tra cứu trạng thái thật.

### 5.2. Handler responder giữ publisher trong vòng đời request

Một handler reactive có thể quan sát cancellation:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
class ReportController {

    private final ReportService reportService;

    ReportController(ReportService reportService) {
        this.reportService = reportService;
    }

    @MessageMapping("reports.generate")
    public Mono<Report> generate(@Payload GenerateReport command) {
        return reportService.generateReactive(command)
            .doOnCancel(() ->
                log.info("Requester cancelled report {}", command.requestId()))
            .doFinally(signal ->
                log.info("Report publisher ended: {}", signal));
    }
}
~~~

Handler trả publisher cho Spring quản lý. Khi requester hủy stream, cancellation có thể truyền tới publisher và các operator upstream. Tuy nhiên, reportService.generateReactive phải thực sự nối publisher tới công việc có thể hủy.

Tránh tạo subscription tự quản lý bên trong handler:

~~~java
@MessageMapping("reports.generate")
public Mono<Void> generate(@Payload GenerateReport command) {
    reportService.generateReactive(command).subscribe();
    return Mono.empty();
}
~~~

Trong ví dụ sai này, handler trả Mono.empty và subscription do subscribe() tạo ra chạy độc lập. Request RSocket có thể kết thúc ngay, trong khi công việc tự subscribe vẫn tiếp tục. Cancellation của request không tự động sở hữu subscription độc lập đó.

### 5.3. Nối cancellation tới một tác vụ blocking

Nếu buộc phải chạy API blocking, cần có handle để yêu cầu dừng và code blocking phải hợp tác. Ví dụ minh họa với Future:

~~~java
Mono<Report> generateWithCancellableWorker(GenerateReport command) {
    return Mono.create(sink -> {
        Future<?> task = executor.submit(() -> {
            try {
                Report report = reportService.generateBlocking(command);
                sink.success(report);
            }
            catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                sink.error(error);
            }
            catch (Exception error) {
                sink.error(error);
            }
        });

        sink.onCancel(() -> task.cancel(true));
    });
}
~~~

Khi subscription bị hủy, onCancel gọi Future.cancel(true), yêu cầu thread đang chạy nhận interrupt. Đây là một yêu cầu ngắt, không phải lệnh cưỡng chế dừng thread. generateBlocking phải kiểm tra interruption hoặc gọi API bên dưới có hỗ trợ cancel. Không nuốt InterruptedException rồi tiếp tục vòng lặp như chưa có gì xảy ra.

Nếu thư viện database, HTTP client hoặc SDK có API cancel riêng, hãy nối handle cancellation tới đúng API đó. Đóng resource trong finally hoặc dùng cơ chế quản lý tài nguyên phù hợp để cleanup cả khi complete, error và cancel. Không giả định interrupt sẽ rollback transaction hoặc thu hồi side effect đã commit.

## 6. Khi nào nên dùng job ID và lệnh hủy riêng?

Nếu công việc có thể kéo dài hơn thời gian caller chờ, hoặc cần tồn tại độc lập với kết nối RSocket, hãy mô hình hóa nó thành **background job**.

Một flow thường dùng:

1. Client gửi lệnh tạo job bằng Request-Response, kèm idempotency key.
2. Server xác thực request, ghi job vào kho trạng thái bền vững và trả job ID.
3. Worker nhận job và cập nhật trạng thái QUEUED → RUNNING → SUCCEEDED hoặc FAILED.
4. Client dùng job ID để truy vấn trạng thái và lấy kết quả sau.
5. Nếu muốn dừng, client gửi lệnh cancel job riêng kèm job ID.
6. Server xác thực quyền, lưu CANCEL_REQUESTED và chuyển tín hiệu tới worker.
7. Worker kiểm tra yêu cầu hủy tại các điểm an toàn, dừng tài nguyên có thể hủy và cập nhật CANCELLED nếu đã dừng thành công.

Trạng thái có thể dùng:

| Trạng thái | Ý nghĩa |
| --- | --- |
| QUEUED | Đã nhận và lưu job, đang chờ worker. |
| RUNNING | Worker đang xử lý. |
| CANCEL_REQUESTED | Đã nhận yêu cầu hủy; worker chưa xác nhận dừng. |
| CANCELLED | Worker đã dừng theo quy tắc nghiệp vụ. |
| SUCCEEDED | Công việc đã hoàn tất thành công. |
| FAILED | Công việc kết thúc do lỗi. |

Không chuyển thẳng từ CANCEL_REQUESTED sang CANCELLED chỉ vì endpoint cancel trả HTTP/RSocket response thành công. Response đó có thể chỉ xác nhận server đã nhận yêu cầu. Chỉ ghi CANCELLED khi worker hoặc hệ thống thực thi xác nhận task đã dừng theo định nghĩa nghiệp vụ. Nếu task đã commit và không thể hoàn tác, có thể cần trạng thái COMPLETED hoặc COMPENSATION_REQUIRED thay vì giả vờ rằng task chưa từng chạy.

Job ID hữu ích khi:

- Công việc cần vài giây hoặc vài phút.
- Kết nối client có thể đóng giữa chừng.
- Người dùng cần xem tiến độ hoặc tải kết quả sau.
- Có nhiều worker hoặc queue.
- Cần audit việc yêu cầu hủy và thời điểm worker dừng.
- Cần xử lý retry sau một timeout không rõ kết quả.

## 7. Deadline phải được thực thi ở phía nhận

Nếu nghiệp vụ có giới hạn tổng thời gian, hãy truyền deadline hoặc ngân sách còn lại tới service nhận và các service con.

Ví dụ payload có thể chứa:

~~~json
{
  "requestId": "report-2026-00421",
  "deadlineEpochMillis": 1794067200000,
  "idempotencyKey": "report-2026-00421"
}
~~~

Đây là cấu trúc minh họa; ứng dụng có thể đặt các trường trong payload hoặc metadata tùy schema và codec.

Ở phía nhận:

1. Xác thực deadline và giới hạn tối đa cho phép.
2. Tính ngân sách còn lại khi bắt đầu xử lý.
3. Không khởi chạy công việc nếu deadline đã hết.
4. Áp dụng timeout/deadline cho publisher, query, HTTP call và các bước con.
5. Truyền deadline còn lại hoặc deadline chung cho service kế tiếp.
6. Ghi rõ kết quả khi deadline hết: dừng được, đang yêu cầu dừng hay đã hoàn tất side effect.

Nếu dùng timestamp tuyệt đối giữa nhiều máy, cần tính đến clock skew và đồng bộ thời gian. Một lựa chọn khác là truyền remaining budget và trừ thời gian đã tiêu thụ ở mỗi hop. Đừng cấp lại toàn bộ budget gốc cho từng service.

Deadline cũng không phải cơ chế hủy tự động. Server cần gắn timer với task, yêu cầu hủy resource bên dưới và lưu kết quả thực tế của quá trình dừng.

## 8. Timeout làm kết quả nghiệp vụ trở nên không chắc chắn

Giả sử client gửi lệnh chuyển tiền, service đã ghi giao dịch thành công, nhưng response bị trễ. Client hết timeout và không biết giao dịch đã commit hay chưa.

Nếu client gửi lại lệnh ngay, giao dịch có thể bị thực hiện hai lần. Timeout chỉ nói rằng client không nhận được response trong thời gian mong muốn; nó không chứng minh request chưa được xử lý.

### 8.1. Idempotency key và deduplication

Với thao tác có side effect, tạo một idempotency key ổn định cho cùng một ý định nghiệp vụ. Server lưu key cùng trạng thái/kết quả theo cách có tính nhất quán với thao tác ghi:

- Nếu key chưa tồn tại, tạo bản ghi và thực hiện nghiệp vụ.
- Nếu key đã tồn tại và đã hoàn tất, trả lại kết quả đã lưu.
- Nếu key đang xử lý, trả trạng thái đang chạy hoặc cho caller chờ theo chính sách.
- Nếu key bị hủy hoặc thất bại, áp dụng quy tắc tiếp tục/retry được định nghĩa trước.

Key phải giữ nguyên qua các lần retry của cùng một thao tác. Nếu mỗi lần retry tạo key mới, deduplication không còn tác dụng.

### 8.2. Kiểm tra trạng thái trước khi retry

Sau timeout, ưu tiên truy vấn theo request ID hoặc job ID nếu nghiệp vụ hỗ trợ:

- SUCCEEDED: lấy lại kết quả đã lưu, không thực hiện lại.
- RUNNING hoặc CANCEL_REQUESTED: tiếp tục theo dõi hoặc gửi yêu cầu hủy có chủ đích.
- QUEUED: đợi worker hoặc hủy job theo chính sách.
- FAILED: quyết định retry dựa trên loại lỗi và tính idempotent.
- Không tìm thấy: chỉ kết luận chưa nhận request khi hệ thống trạng thái bảo đảm điều đó; nếu không, trạng thái vẫn có thể chưa được đồng bộ.

Retry chỉ an toàn khi thao tác idempotent hoặc server có deduplication bền vững. Dùng backoff và giới hạn số lần retry để tránh làm quá tải service đang chậm.

### 8.3. Đừng nhầm từ “canceled” với “không có side effect”

Trong RSocket, ERROR[REJECTED] bảo đảm responder không xử lý request. ERROR[CANCELED] cho biết responder đã hủy nhưng có thể đã bắt đầu xử lý. Timeout phía caller không tự tạo ra một trong hai kết luận đó.

Nếu không có bằng chứng về trạng thái xử lý, hãy coi kết quả là **unknown outcome** và truy vấn trạng thái theo request ID trước khi gửi lại một lệnh có side effect.

## 9. Ví dụ Java 17+ chạy độc lập

Ví dụ dùng Reactor Core để mô phỏng hai vòng đời: publisher phản hồi bị timeout và một công việc detached ở receiver vẫn hoàn tất. Chương trình chạy trong một JVM để minh họa nguyên lý; nó không mở kết nối RSocket thực.

### 9.1. Cấu hình Maven

Tạo file pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>timeout-cancellation-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.8.6</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 9.2. Chương trình

Tạo file src/main/java/TimeoutDoesNotStopRemoteWorkDemo.java:

~~~java
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import reactor.core.publisher.Mono;

public class TimeoutDoesNotStopRemoteWorkDemo {

    public static void main(String[] args) throws InterruptedException {
        ExecutorService receiverExecutor =
            Executors.newSingleThreadExecutor();
        CountDownLatch receiverFinished = new CountDownLatch(1);

        try {
            Mono<String> request = Mono.defer(() -> {
                // Mô phỏng công việc receiver đã tách khỏi request publisher.
                receiverExecutor.submit(() -> {
                    try {
                        Thread.sleep(300);
                        System.out.println(
                            "receiver: detached work completed");
                    }
                    catch (InterruptedException error) {
                        Thread.currentThread().interrupt();
                    }
                    finally {
                        receiverFinished.countDown();
                    }
                });

                // Mô phỏng response không về trước deadline.
                return Mono.<String>never()
                    .doFinally(signal ->
                        System.out.println(
                            "request publisher: " + signal));
            });

            String result = request
                .timeout(Duration.ofMillis(50))
                .doOnError(TimeoutException.class, error ->
                    System.out.println(
                        "caller observed: TimeoutException"))
                .onErrorResume(TimeoutException.class, error ->
                    Mono.just("timed out"))
                .block();

            System.out.println("caller result: " + result);

            if (!receiverFinished.await(2, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                    "Receiver task did not finish in time");
            }
        }
        finally {
            receiverExecutor.shutdownNow();
        }
    }
}
~~~

Chạy bằng Java 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=TimeoutDoesNotStopRemoteWorkDemo
~~~

Stdout:

~~~text
request publisher: CANCEL
caller observed: TimeoutException
caller result: timed out
receiver: detached work completed
~~~

Giải thích:

1. Mono.defer bắt đầu công việc trong executor và trả về Mono.never để mô phỏng response không đến.
2. timeout 50 ms hết hạn, hủy subscription của Mono.never. doFinally nằm trên source nhận CANCEL.
3. Caller nhận TimeoutException và onErrorResume thay lỗi bằng kết quả "timed out".
4. Công việc trong executor đã được submit độc lập, không nối cancellation với request publisher. Nó tiếp tục chạy và in "receiver: detached work completed".
5. CountDownLatch chỉ giúp chương trình đợi để quan sát kết quả; nó không phải cơ chế hủy công việc.

Ví dụ này mô phỏng tình huống phổ biến: caller timeout và source publisher bị hủy, nhưng task detached vẫn tiếp tục. Trong hệ thống phân tán, executor/queue ở service nhận có thể ở một tiến trình khác; caller càng không thể dùng timeout cục bộ để cưỡng chế dừng tiến trình đó.

## 10. Kiểm tra và quan sát trong môi trường thật

Khi một request timeout nhưng CPU, query hoặc job vẫn chạy, thu thập dữ liệu theo từng lớp:

1. **Correlation ID / request ID:** dùng một ID xuyên suốt caller, RSocket stream, handler và worker.
2. **Deadline:** ghi deadline ban đầu, ngân sách còn lại ở từng hop và thời điểm timeout.
3. **Caller:** ghi timeout phát sinh ở lớp nào, TimeoutException hay lỗi transport, và caller có retry hay không.
4. **Publisher:** đặt doFinally ở cả trước và sau timeout để phân biệt CANCEL upstream với ON_ERROR downstream.
5. **RSocket:** nếu có thể, quan sát stream ID, request type, thời điểm gửi/nhận CANCEL và trạng thái connection.
6. **Handler:** ghi nhận doOnCancel trên publisher mà @MessageMapping trả về.
7. **Worker:** ghi thời điểm bắt đầu, thời điểm nhận yêu cầu dừng, thời điểm thực sự thoát và lý do thoát.
8. **Side effect:** ghi thời điểm transaction commit hoặc request bên ngoài được chấp nhận; không coi log timeout là rollback.
9. **Retry:** ghi idempotency key, số lần thử và trạng thái deduplication.

Một kiểm thử có ích nên bao gồm:

- Timeout trước khi request tới responder.
- Timeout sau khi handler bắt đầu nhưng trước side effect.
- Timeout trong lúc worker đang chạy và worker có hỗ trợ cancellation.
- Timeout khi worker detached khỏi publisher.
- Timeout sau khi side effect commit nhưng trước khi response về.
- Request-Fire-and-Forget đã được nhận rồi caller muốn hủy job.
- Retry cùng idempotency key sau khi caller không biết kết quả lần đầu.

Dùng latch, barrier hoặc fake service để tạo các thời điểm kiểm soát được. Kiểm tra trạng thái worker và dữ liệu nghiệp vụ thật, không chỉ kiểm tra rằng hook doOnCancel đã chạy.

## 11. Lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Coi TimeoutException là bằng chứng request thất bại | Có thể gửi lại lệnh đã thực hiện thành công. | Tra cứu trạng thái theo request ID và dùng idempotency key. |
| Chỉ đặt timeout ở client | Receiver có thể tiếp tục làm việc vô hạn. | Thực thi deadline ở server và các service con. |
| Nghĩ CANCEL tự dừng mọi thread | Task blocking hoặc detached vẫn chạy. | Nối cancellation tới Future, token, API cancel hoặc worker checkpoint. |
| Gọi subscribe() trong @MessageMapping | Tạo subscription nằm ngoài vòng đời request. | Trả publisher đã compose để Spring quản lý subscription. |
| Dùng Fire-and-Forget cho job cần theo dõi | Không có response/job ID để kiểm tra kết quả. | Dùng Request-Response để nhận job ID và route riêng để query/cancel. |
| Dùng Flux.timeout làm tổng deadline | Stream vẫn có thể chạy mãi nếu luôn phát phần tử đúng hạn. | Dùng deadline tổng riêng, ngoài idle timeout. |
| Coi Future.cancel(true) là cưỡng chế dừng | Code có thể bỏ qua interruption hoặc đang ở API không hỗ trợ cancel. | Thiết kế cooperative cancellation và xác nhận worker đã thoát. |
| Retry ngay sau timeout | Side effect có thể bị lặp. | Deduplicate, query trạng thái và chỉ retry khi an toàn. |
| Ghi CANCELLED ngay khi nhận yêu cầu hủy | Job có thể vẫn đang chạy. | Dùng CANCEL_REQUESTED rồi chỉ ghi CANCELLED sau khi worker xác nhận dừng. |
| Cho rằng timeout rollback transaction | Dữ liệu đã commit vẫn tồn tại. | Dùng transaction/compensation theo quy tắc nghiệp vụ. |

## 12. Ghi nhớ

- Timeout giới hạn thời gian caller chờ; nó không phải trạng thái cuối của task phía nhận.
- Reactor timeout hủy subscription nguồn và phát TimeoutException hoặc chuyển fallback cho caller.
- doFinally ở source có thể nhận CANCEL trong khi downstream nhận ON_ERROR vì TimeoutException.
- RSocket CANCEL (0x09) kết thúc stream theo stream ID; nó không tự dừng một worker detached hay hoàn tác side effect.
- Request-Fire-and-Forget không có stream response còn hoạt động để hủy về sau; cần cơ chế cancel job riêng.
- Server phải thực thi deadline, hợp tác với cancellation và báo trạng thái task thực tế.
- Với thao tác có side effect, timeout tạo ra unknown outcome; dùng request ID, idempotency key và trạng thái bền vững trước khi retry.
- Chỉ báo CANCELLED khi worker đã xác nhận dừng theo định nghĩa nghiệp vụ.

## 13. Tài liệu tham khảo

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): RSocketRequester, @MessageMapping và các interaction model.
- [RSocket Protocol](https://rsocket.io/about/protocol/): CANCEL frame, stream ID, REQUEST_FNF, Request-Response, Request-Stream, Request-Channel và các mã ERROR.
- [Reactor Core — Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): timeout, doOnCancel và doFinally.
- [Reactor Core — Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): timeout theo khoảng cách giữa các phần tử.
- [Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/): cách compose publisher, xử lý lỗi và quản lý cancellation.
- [Reactive Streams for the JVM](https://github.com/reactive-streams/reactive-streams-jvm): hợp đồng Publisher, Subscriber, Subscription, request và cancel.
