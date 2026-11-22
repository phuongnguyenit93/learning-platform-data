# Đưa công việc kéo dài ra ngoài thời gian xử lý giao diện

Trong module **MODEL_VIEW_CONTROLLER**, Controller tiếp nhận request, gọi tầng ứng dụng hoặc Model rồi trả response cho trình duyệt hay API client. Một số thao tác hoàn thành nhanh, nhưng có thao tác cần nhiều thời gian: xuất báo cáo lớn, nhập dữ liệu, xử lý ảnh/video, tổng hợp hàng nghìn bản ghi hoặc gọi nhiều dịch vụ bên ngoài. Nếu giữ toàn bộ công việc trong thời gian xử lý request, người dùng phải chờ lâu và kết nối HTTP có thể hết thời gian chờ trước khi công việc hoàn tất.

Với những tác vụ phù hợp, ứng dụng nên tiếp nhận yêu cầu nhanh, lưu một công việc (job) có thể theo dõi, sau đó giao phần xử lý kéo dài cho worker chạy bên ngoài luồng xử lý giao diện. Controller trả lời rằng yêu cầu đã được tiếp nhận; giao diện hiển thị trạng thái và cho phép người dùng xem kết quả khi hoàn thành. Cách tổ chức này giúp luồng MVC phản hồi nhanh hơn và tách vòng đời của công việc khỏi vòng đời của một request HTTP.

## 1. Khi nào nên đưa công việc ra khỏi request?

Trong xử lý đồng bộ thông thường, request chỉ kết thúc sau khi toàn bộ thao tác hoàn thành. Luồng này phù hợp với công việc ngắn, có giới hạn rõ và cần kết quả ngay, chẳng hạn đọc một trang dữ liệu hoặc cập nhật một trường đơn giản.

Nên cân nhắc xử lý nền khi công việc:

- Có thời gian thực thi dài hoặc không dự đoán được, chẳng hạn tạo báo cáo từ hàng triệu dòng dữ liệu.
- Cần xử lý nhiều bản ghi, chuyển đổi tệp lớn hoặc tạo nhiều tài nguyên.
- Gọi nhiều dịch vụ bên ngoài và có thể phải retry khi dịch vụ tạm thời không khả dụng.
- Không cần trả kết quả cuối cùng ngay trong response của request khởi tạo.
- Có thể tiếp tục sau khi người dùng đóng tab hoặc mất kết nối.
- Cần theo dõi tiến độ, lịch sử, trạng thái thất bại hoặc khả năng chạy lại.

Không phải mọi thao tác chậm đều nên đưa vào queue. Nếu người dùng cần kết quả tức thời và công việc có giới hạn nhỏ, xử lý đồng bộ có thể đơn giản và dễ hiểu hơn. Trước khi tách nền, cần xác định chi phí vận hành của queue, worker, lưu trạng thái và xử lý lỗi có tương xứng với lợi ích hay không.

## 2. Vì sao không nên giữ request mở quá lâu?

Một request HTTP thường đi qua trình duyệt, proxy, load balancer, web server và ứng dụng. Mỗi lớp có thể có timeout riêng. Khi công việc kéo dài, một số vấn đề có thể xuất hiện:

- **Timeout:** client hoặc proxy đóng kết nối trước khi server hoàn thành.
- **Giữ tài nguyên:** thread xử lý request, connection pool hoặc tài nguyên liên quan bị chiếm trong thời gian dài.
- **Trải nghiệm kém:** người dùng không biết công việc còn chạy, đã thất bại hay có thể thử lại.
- **Khó phục hồi:** khi tiến trình ứng dụng khởi động lại, công việc chỉ tồn tại trong bộ nhớ có thể bị mất.
- **Khó kiểm soát retry:** người dùng bấm gửi lại vì không nhận được response, dẫn đến công việc bị chạy hai lần.
- **Khó quan sát:** log của một request dài không đủ để theo dõi tiến trình và các lần thử của công việc.

Một response bị ngắt không chứng minh rằng công việc phía server đã dừng. Vì vậy, không nên dùng trạng thái kết nối HTTP làm nguồn sự thật về trạng thái nghiệp vụ của một tác vụ dài.

## 3. Mô hình xử lý nền: tiếp nhận, xếp hàng và thực thi

Một mô hình phổ biến tách công việc thành ba phần:

1. **Tiếp nhận yêu cầu:** Controller xác thực request, kiểm tra quyền và dữ liệu đầu vào, sau đó gọi use case tạo job.
2. **Lưu và xếp hàng:** tầng ứng dụng lưu thông tin job cùng trạng thái ban đầu, rồi gửi thông điệp để worker biết có công việc cần xử lý.
3. **Thực thi:** worker nhận job, tải dữ liệu cần thiết, thực hiện nghiệp vụ, lưu kết quả hoặc lỗi và cập nhật trạng thái.

~~~mermaid
flowchart LR
    U[Người dùng] --> C[Controller]
    C --> A[Use case tiếp nhận job]
    A --> J[(Job store)]
    A --> Q[Queue]
    Q --> W[Background worker]
    W --> D[(Database / file storage)]
    W --> J
    U --> S[Trang trạng thái job]
    S --> C2[Job status Controller]
    C2 --> J
    C2 --> U
~~~

Controller khởi tạo job và trả response sớm. Worker thực hiện công việc trong vòng đời riêng. Trang trạng thái đọc tiến độ từ kho lưu trữ để người dùng có thể rời trang rồi quay lại sau.

Queue và job store có vai trò khác nhau:

- **Queue** thông báo rằng có công việc cần xử lý, thường hỗ trợ phân phối, retry và điều phối worker.
- **Job store** lưu trạng thái có thể truy vấn như người yêu cầu, thời điểm tạo, trạng thái hiện tại, tiến độ và tham chiếu kết quả.

Một hệ thống nhỏ có thể dùng bảng database làm hàng đợi công việc; hệ thống lớn hơn có thể dùng message broker. Cần chọn theo yêu cầu độ bền, thông lượng, khả năng retry và độ phức tạp vận hành.

## 4. Vòng đời của một job

Job cần có trạng thái được định nghĩa rõ để Controller, worker và View hiểu cùng một ý nghĩa. Một tập trạng thái cơ bản:

| Trạng thái | Ý nghĩa | Hành động tiếp theo thường gặp |
| --- | --- | --- |
| QUEUED | Đã tiếp nhận, đang chờ worker | Worker nhận việc |
| RUNNING | Worker đang xử lý | Cập nhật tiến độ hoặc hoàn tất |
| SUCCEEDED | Hoàn thành thành công | Cho phép xem hoặc tải kết quả |
| FAILED | Xử lý thất bại | Hiển thị thông báo an toàn, cho phép yêu cầu chạy lại nếu phù hợp |
| CANCEL_REQUESTED | Đã nhận yêu cầu hủy | Worker kiểm tra và dừng an toàn |
| CANCELLED | Đã hủy | Kết thúc |

Các chuyển trạng thái cần được kiểm soát. Ví dụ, job không nên chuyển từ FAILED sang SUCCEEDED chỉ vì một request status đến muộn. Nếu hỗ trợ retry, có thể tạo lần chạy mới hoặc chuyển về QUEUED theo quy tắc được ghi nhận.

~~~mermaid
stateDiagram-v2
    [*] --> QUEUED
    QUEUED --> RUNNING
    RUNNING --> SUCCEEDED
    RUNNING --> FAILED
    QUEUED --> CANCELLED
    RUNNING --> CANCEL_REQUESTED
    CANCEL_REQUESTED --> CANCELLED
    CANCEL_REQUESTED --> SUCCEEDED
    FAILED --> QUEUED: Retry được chấp nhận
~~~

Sơ đồ chỉ là ví dụ. Có hệ thống không cho hủy sau khi worker bắt đầu; hệ thống khác cho phép yêu cầu hủy nhưng chỉ dừng tại các điểm an toàn. Cần định nghĩa rõ những chuyển trạng thái nào hợp lệ và ai được phép yêu cầu chúng.

## 5. Trả lời request bằng HTTP 202 Accepted

Với API, khi server đã nhận yêu cầu nhưng chưa hoàn tất công việc, mã **202 Accepted** thường phù hợp. Nó cho biết request đã được chấp nhận để xử lý; nó không khẳng định công việc đã thành công.

Ví dụ Controller:

~~~java
@RestController
@RequestMapping("/api/exports")
public class ExportController {
    private final RequestExportUseCase requestExport;

    public ExportController(RequestExportUseCase requestExport) {
        this.requestExport = requestExport;
    }

    @PostMapping
    public ResponseEntity<JobAcceptedResponse> create(
            @Valid @RequestBody ExportRequest request,
            @AuthenticationPrincipal AppPrincipal principal) {
        JobId jobId = requestExport.execute(
                principal.userId(),
                request.toCommand()
        );

        URI statusUri = URI.create("/api/jobs/" + jobId.value());
        JobAcceptedResponse body = new JobAcceptedResponse(
                jobId.value(),
                "QUEUED",
                statusUri.toString()
        );

        return ResponseEntity.accepted()
                .location(statusUri)
                .body(body);
    }
}
~~~

Response DTO có thể được định nghĩa như sau:

~~~java
public record JobAcceptedResponse(
        String jobId,
        String status,
        String statusUrl
) {}
~~~

Client nhận ID và URL để kiểm tra trạng thái. Endpoint trạng thái có thể trả 200 OK cùng trạng thái hiện tại, còn endpoint tạo job đã trả 202 Accepted. Không nên trả 200 với thông điệp “hoàn thành” nếu worker vẫn chưa xử lý xong.

## 6. Lưu job và thông điệp công việc

Một job thường cần lưu các thông tin tối thiểu:

| Trường | Mục đích |
| --- | --- |
| id | Định danh duy nhất của job |
| type | Loại công việc, ví dụ ORDER_EXPORT |
| requested_by | Người dùng khởi tạo |
| tenant_id | Phạm vi tổ chức nếu ứng dụng multi-tenant |
| status | Trạng thái hiện tại |
| created_at, started_at, finished_at | Mốc thời gian theo dõi |
| progress | Tiến độ nếu có thể đo đáng tin cậy |
| result_ref | Tham chiếu đến tệp hoặc kết quả đã lưu |
| error_code | Mã lỗi an toàn để hiển thị hoặc hỗ trợ tra cứu |
| attempt | Số lần worker đã thử |

Thông điệp queue nên chứa định danh job hoặc command tối thiểu để worker tải dữ liệu cần thiết. Tránh đưa toàn bộ entity, HTTP request, session hay đối tượng principal vào message. Những đối tượng đó có thể lớn, không tuần tự hóa ổn định hoặc chứa dữ liệu nhạy cảm.

Ví dụ command:

~~~java
public record ExportOrdersCommand(
        JobId jobId,
        UserId requestedBy,
        TenantId tenantId,
        Instant requestedAt
) {}
~~~

Worker dùng jobId để lấy cấu hình công việc đã được lưu, rồi truy vấn dữ liệu trong phạm vi requestedBy và tenantId. Dữ liệu đầu vào của job nên được lưu thành snapshot hoặc tham chiếu ổn định nếu kết quả cần phản ánh trạng thái tại thời điểm người dùng gửi yêu cầu.

## 7. Tránh mất job giữa lúc lưu và gửi queue

Một lỗi thường gặp là lưu job vào database rồi gửi message riêng rẽ:

1. Database commit job thành công.
2. Ứng dụng gặp lỗi trước khi gửi message.
3. Job tồn tại ở trạng thái QUEUED nhưng worker không bao giờ nhận được thông báo.

Chiều ngược lại cũng có thể xảy ra: message đã được gửi nhưng transaction lưu job rollback. Worker nhận message nhưng không tìm thấy job hợp lệ.

Với hệ thống cần độ tin cậy cao, có thể dùng **Transactional Outbox**. Trong cùng transaction database, ứng dụng lưu job và một bản ghi outbox. Một publisher đọc outbox và gửi message đến queue; sau khi gửi thành công, nó đánh dấu bản ghi đã phát. Nhờ vậy, ý định gửi message được lưu bền vững cùng transaction tạo job.

~~~mermaid
sequenceDiagram
    participant C as Controller
    participant A as Application service
    participant DB as Database
    participant P as Outbox publisher
    participant Q as Queue
    participant W as Worker
    C->>A: Yêu cầu tạo job
    A->>DB: BEGIN
    A->>DB: INSERT job (QUEUED)
    A->>DB: INSERT outbox event
    A->>DB: COMMIT
    P->>DB: Đọc outbox chưa phát
    P->>Q: Publish JobRequested
    Q-->>W: Chuyển thông điệp
    P->>DB: Đánh dấu outbox đã phát
    W->>DB: Cập nhật trạng thái job
~~~

Publisher có thể gửi trùng nếu tiến trình dừng sau khi publish nhưng trước khi đánh dấu outbox. Vì vậy, worker vẫn cần xử lý thông điệp lặp một cách an toàn. Outbox giúp tránh mất ý định gửi, nhưng không tự tạo ra bảo đảm exactly-once cho toàn bộ nghiệp vụ.

## 8. Worker thực hiện công việc như thế nào?

Worker là thành phần chạy công việc nền. Nó có thể chạy trong cùng ứng dụng nhưng trên executor riêng, hoặc chạy ở tiến trình/dịch vụ riêng. Với hệ thống cần độ bền và khả năng mở rộng, worker riêng thường dễ điều chỉnh tài nguyên và triển khai độc lập hơn.

Một worker thường thực hiện:

1. Nhận message hoặc lấy job đang chờ.
2. Kiểm tra job còn hợp lệ và claim job để tránh nhiều worker cùng xử lý.
3. Chuyển trạng thái sang RUNNING và ghi nhận thời điểm bắt đầu.
4. Tải dữ liệu cần thiết, kiểm tra phạm vi truy cập và thực hiện nghiệp vụ.
5. Cập nhật tiến độ ở những mốc có ý nghĩa.
6. Lưu kết quả vào database hoặc object storage.
7. Chuyển sang SUCCEEDED, hoặc ghi lỗi an toàn và chuyển sang FAILED.

Ví dụ khung xử lý:

~~~java
public final class ExportOrdersWorker {
    private final JobRepository jobs;
    private final OrderExportService exporter;

    public void handle(JobId jobId) {
        Job job = jobs.claim(jobId).orElse(null);
        if (job == null) {
            return; // Job không còn ở trạng thái có thể nhận
        }

        try {
            jobs.markRunning(jobId);
            ExportResult result = exporter.export(
                    job.requestedBy(),
                    job.tenantId()
            );
            jobs.markSucceeded(jobId, result.reference());
        } catch (RetryableExportException exception) {
            throw exception; // Để cơ chế queue retry theo chính sách
        } catch (Exception exception) {
            jobs.markFailed(jobId, "EXPORT_FAILED");
            // Ghi chi tiết exception vào log có kiểm soát
        }
    }
}
~~~

Đây là khung minh họa. Cách claim, transaction, retry và ghi lỗi phải được thiết kế theo queue và database cụ thể. Không giữ transaction database mở trong toàn bộ thời gian tạo tệp lớn hoặc gọi dịch vụ ngoài; nên chia công việc thành các bước có transaction ngắn và điểm phục hồi rõ ràng.

## 9. Retry, idempotency và xử lý thông điệp lặp

Worker hoặc message broker có thể giao cùng một công việc nhiều lần. Tiến trình có thể chết sau khi hoàn thành một phần nhưng trước khi xác nhận message. Vì vậy, không nên giả định mỗi job chỉ chạy đúng một lần.

**Idempotency** nghĩa là thực hiện lại cùng một thao tác không tạo ra tác động phụ ngoài dự kiến. Một số cách áp dụng:

- Lưu jobId hoặc idempotency key duy nhất và kiểm tra trước khi tạo công việc mới.
- Dùng trạng thái job và thao tác claim có điều kiện để chỉ một worker nhận job ở một thời điểm.
- Khi ghi kết quả, dùng khóa duy nhất hoặc thao tác upsert phù hợp để tránh tạo kết quả trùng.
- Với dịch vụ bên ngoài, gửi idempotency key nếu nhà cung cấp hỗ trợ.
- Thiết kế từng bước có thể tiếp tục hoặc xác định rõ bước nào đã hoàn thành.

Retry cần có chính sách:

- Chỉ retry lỗi tạm thời như timeout hoặc lỗi dịch vụ có thể phục hồi.
- Dùng exponential backoff và giới hạn số lần thử.
- Thêm jitter để nhiều worker không cùng retry vào một thời điểm.
- Không retry vô hạn lỗi dữ liệu hoặc lỗi nghiệp vụ không thể khắc phục.
- Sau số lần thử tối đa, chuyển job sang trạng thái thất bại cuối cùng hoặc hàng đợi xử lý riêng (dead-letter queue).

Không phải mọi thao tác đều có thể retry an toàn. Ví dụ gửi email hoặc trừ tiền có thể tạo tác động lặp nếu không có idempotency phù hợp. Cần xác định điểm commit và cách nhận biết một tác động đã xảy ra.

## 10. Theo dõi tiến độ và hiển thị kết quả

Khi job kéo dài, người dùng cần biết công việc đang ở trạng thái nào. Một endpoint trạng thái có thể trả:

~~~java
public record JobStatusResponse(
        String jobId,
        String status,
        Integer progressPercent,
        String message,
        Instant createdAt,
        Instant finishedAt,
        String resultUrl
) {}
~~~

Controller chỉ trả thông tin mà người dùng hiện tại có quyền xem:

~~~java
@GetMapping("/api/jobs/{id}")
public JobStatusResponse status(
        @PathVariable String id,
        @AuthenticationPrincipal AppPrincipal principal) {
    return jobQuery.getStatusForOwner(new JobId(id), principal.userId());
}
~~~

Giao diện có thể:

- Hiển thị “Đang chờ”, “Đang xử lý”, “Đã hoàn tất” hoặc “Không thể hoàn thành”.
- Hiển thị phần trăm nếu worker có thể đo tiến độ thực tế.
- Cung cấp nút tải kết quả khi job thành công.
- Cho phép yêu cầu hủy nếu công việc hỗ trợ hủy.
- Cho phép gửi lại hoặc tạo job mới theo chính sách khi job thất bại.

Không nên tạo phần trăm giả chỉ để giao diện trông sinh động. Nếu không thể đo tiến độ đáng tin cậy, hiển thị trạng thái và thông điệp ngắn sẽ trung thực hơn.

### Polling, Server-Sent Events và WebSocket

Có nhiều cách cập nhật trạng thái cho trình duyệt:

| Cách | Đặc điểm | Phù hợp khi |
| --- | --- | --- |
| Polling | Trình duyệt gọi GET theo khoảng thời gian | Cách đơn giản, số lượng job và người dùng vừa phải |
| Server-Sent Events (SSE) | Server đẩy sự kiện một chiều đến trình duyệt | Cần cập nhật tiến độ liên tục theo chiều server → client |
| WebSocket | Kết nối hai chiều lâu dài | Giao diện cần trao đổi sự kiện hai chiều thường xuyên |

Polling nên có khoảng thời gian hợp lý, dừng khi job ở trạng thái cuối và tránh gửi request quá dày. SSE hoặc WebSocket cần quản lý kết nối, xác thực và phân phối sự kiện đúng người nhận. Dù dùng cách nào, database/job store vẫn là nguồn trạng thái có thể truy vấn sau khi trình duyệt tải lại.

## 11. Hiển thị kết quả cho đúng người dùng

Job thường chứa dữ liệu riêng của người yêu cầu. Biết jobId không đồng nghĩa có quyền xem trạng thái hoặc tải kết quả. Endpoint trạng thái và kết quả phải kiểm tra chủ sở hữu hoặc tenant giống như các tài nguyên khác.

Các nguyên tắc cần giữ:

- Gắn job với user/tenant đã được xác thực tại thời điểm tạo.
- Kiểm tra quyền trên job khi xem trạng thái, yêu cầu hủy hoặc tải kết quả.
- Không dùng URL tệp công khai có thể đoán được; dùng endpoint được bảo vệ hoặc URL ký có thời hạn theo chính sách.
- Không đưa token, dữ liệu nhạy cảm hoặc toàn bộ request vào message queue.
- Xác định thời gian lưu kết quả và thời điểm xóa tệp tạm.
- Ghi nhận người yêu cầu và phạm vi dữ liệu để hỗ trợ audit.

Nếu người dùng bị thu hồi quyền trong lúc job đang chạy, ứng dụng cần có chính sách rõ: quyền được kiểm tra tại thời điểm tạo job, trong lúc xử lý hay cả khi tải kết quả. Với dữ liệu nhạy cảm, kiểm tra lại quyền khi truy cập kết quả thường là cần thiết.

## 12. Hủy công việc và giới hạn tài nguyên

Hủy một job không phải lúc nào cũng có thể dừng ngay lập tức. Worker có thể đang xử lý một batch, ghi tệp hoặc gọi dịch vụ bên ngoài. Cơ chế hủy thường là yêu cầu hủy được lưu vào job; worker kiểm tra yêu cầu đó tại các điểm an toàn rồi dừng.

Một số giới hạn cần thiết:

- Giới hạn số job đang chờ và số worker chạy đồng thời.
- Giới hạn kích thước tệp, số bản ghi, thời gian chạy và dung lượng kết quả.
- Áp dụng timeout riêng cho từng lời gọi dịch vụ ngoài.
- Giới hạn retry và thời gian sống của job.
- Có cơ chế dọn job cũ, tệp tạm và kết quả hết hạn.
- Ưu tiên hoặc phân bổ tài nguyên theo loại job nếu có nhiều nhóm công việc.

Không nên cho phép một người dùng tạo số lượng job không giới hạn. Endpoint tạo job cần xác thực, phân quyền, validation và giới hạn tần suất phù hợp để tránh hàng đợi bị lấp đầy.

## 13. Tác vụ nền và giao dịch dữ liệu

Một tác vụ nền thường đọc nhiều dữ liệu, tạo kết quả và cập nhật trạng thái. Cần xác định ranh giới transaction:

- Transaction ngắn để tạo job và bản ghi outbox.
- Transaction ngắn để claim job và đổi trạng thái.
- Các transaction theo batch nếu công việc cập nhật nhiều bản ghi.
- Transaction riêng để lưu tham chiếu kết quả và đánh dấu thành công.

Không giữ một transaction mở trong suốt một tác vụ kéo dài nhiều phút. Điều đó có thể giữ khóa, chiếm connection và làm tăng nguy cơ deadlock hoặc timeout.

Nếu job thực hiện nhiều bước không thể gộp trong một transaction, cần thiết kế tính nhất quán theo từng bước. Có thể lưu checkpoint, dùng saga/compensation khi có thao tác cần hoàn tác, hoặc tạo kết quả tạm rồi công bố khi hoàn tất. Cách chọn phụ thuộc vào nghiệp vụ và hậu quả nếu công việc dừng giữa chừng.

## 14. Quan sát, log và xử lý lỗi

Một request tạo job và một worker thực thi có thể chạy ở hai tiến trình và hai thời điểm khác nhau. Cần có định danh liên kết chúng:

- jobId duy nhất để tra cứu toàn bộ vòng đời công việc.
- correlationId hoặc trace ID để liên kết request khởi tạo với log và message.
- Thời điểm tạo, bắt đầu, kết thúc và thời lượng thực thi.
- Số lần thử, worker nhận việc và loại lỗi.
- Số lượng bản ghi xử lý, số lượng thành công/thất bại nếu có.

Người dùng chỉ nên thấy mã lỗi và thông báo an toàn, ví dụ “Không thể tạo báo cáo. Vui lòng thử lại hoặc liên hệ hỗ trợ với mã job…”. Log phía server có thể chứa stack trace và chi tiết kỹ thuật theo chính sách bảo mật, nhưng không nên ghi token, mật khẩu hoặc toàn bộ dữ liệu cá nhân.

Các chỉ số vận hành hữu ích gồm số job đang chờ, tuổi của job lâu nhất, số job thất bại, thời gian xử lý trung vị và tỷ lệ retry. Chúng giúp phát hiện worker bị dừng hoặc queue bị ùn tắc trước khi người dùng phản ánh.

## 15. Ví dụ luồng MVC hoàn chỉnh

Giả sử người dùng yêu cầu xuất báo cáo đơn hàng:

1. Người dùng chọn bộ lọc và nhấn “Xuất báo cáo”.
2. Controller xác thực request, kiểm tra quyền và gọi RequestExportUseCase.
3. Use case tạo job ở trạng thái QUEUED và lưu thông điệp outbox trong cùng transaction.
4. Controller trả redirect đến trang trạng thái nếu là form HTML, hoặc 202 Accepted cùng status URL nếu là API.
5. Outbox publisher gửi message đến queue.
6. Worker nhận job, claim job, truy vấn dữ liệu theo user/tenant, tạo tệp và lưu vào vùng lưu trữ riêng.
7. Worker cập nhật job thành SUCCEEDED cùng tham chiếu kết quả; nếu lỗi, cập nhật FAILED với mã lỗi an toàn.
8. View truy vấn trạng thái và hiển thị liên kết tải khi người dùng được phép truy cập.

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant C as ExportController
    participant A as RequestExportUseCase
    participant DB as Job store + Outbox
    participant Q as Queue
    participant W as Worker
    participant FS as File storage
    User->>C: POST /exports
    C->>A: Tạo yêu cầu export
    A->>DB: Lưu job QUEUED và outbox
    DB-->>A: Commit
    A-->>C: JobId
    C-->>User: 202 Accepted / redirect
    DB->>Q: Publisher gửi JobRequested
    Q->>W: Nhận job
    W->>DB: Claim và đánh dấu RUNNING
    W->>DB: Đọc dữ liệu theo phạm vi
    W->>FS: Tạo và lưu tệp
    FS-->>W: Result reference
    W->>DB: Đánh dấu SUCCEEDED
    User->>C: GET /jobs/{id}
    C->>DB: Đọc trạng thái theo owner
    DB-->>C: SUCCEEDED + result reference
    C-->>User: Hiển thị liên kết tải an toàn
~~~

View không cần biết worker chạy ở máy nào hoặc queue dùng công nghệ gì. Nó chỉ cần hợp đồng trạng thái job và đường dẫn kết quả mà Controller cung cấp.

## 16. Kiểm thử công việc chạy nền

Kiểm thử không nên chỉ xác nhận endpoint trả 202. Cần kiểm tra cả việc job được lưu, worker thực hiện đúng và trạng thái cuối được phản ánh.

| Phạm vi | Điều cần xác minh |
| --- | --- |
| Controller | Request hợp lệ tạo job và trả 202/redirect đúng; request sai bị từ chối |
| Use case | Job được tạo với user/tenant và tham số đúng |
| Outbox publisher | Bản ghi chưa phát được gửi; lỗi gửi có thể thử lại |
| Worker | Job chuyển QUEUED → RUNNING → SUCCEEDED hoặc FAILED |
| Idempotency | Message lặp không tạo kết quả hoặc tác động phụ trùng |
| Retry | Lỗi tạm thời được thử lại theo giới hạn; lỗi vĩnh viễn không retry vô hạn |
| Authorization | Người khác không xem trạng thái hoặc tải kết quả của job |
| Hủy | Job dừng tại điểm an toàn và chuyển trạng thái đúng |
| Phục hồi | Worker khởi động lại có thể tiếp tục hoặc nhận lại job bị bỏ dở |

Với test tích hợp, có thể dùng queue giả hoặc adapter trong bộ nhớ để kiểm tra luồng mà không cần phụ thuộc vào broker thật. Tuy nhiên, vẫn nên có kiểm thử riêng cho cấu hình broker, transaction và cơ chế retry khi hệ thống phụ thuộc vào chúng.

## 17. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Hướng xử lý |
| --- | --- | --- |
| Chạy tác vụ lớn ngay trong Controller | Request chậm, dễ timeout và giữ thread | Controller chỉ tiếp nhận job; worker thực thi |
| Chỉ lưu job trong bộ nhớ | Mất công việc khi tiến trình khởi động lại | Lưu trạng thái bền vững và dùng queue phù hợp |
| Trả 200 như thể đã hoàn thành | Client hiểu sai trạng thái | Trả 202 khi mới tiếp nhận và cung cấp status URL |
| Không kiểm tra quyền trên job | Người khác có thể xem hoặc tải kết quả | Kiểm tra owner/tenant ở mọi endpoint job |
| Giả định message chỉ giao một lần | Tác động phụ có thể lặp | Thiết kế idempotency và claim job |
| Retry vô hạn | Queue bị chiếm bởi lỗi không thể phục hồi | Giới hạn retry, backoff và dead-letter |
| Giữ transaction mở trong toàn bộ job | Giữ khóa và connection quá lâu | Chia công việc thành các bước/transaction ngắn |
| Không lưu lỗi hoặc lịch sử chạy | Khó hỗ trợ và điều tra | Lưu mã lỗi, attempt và mốc thời gian |
| Trả tiến độ giả | Người dùng mất niềm tin | Chỉ báo phần trăm khi đo được; nếu không hiển thị trạng thái |

## 18. Quy trình quyết định và triển khai

Khi có một thao tác chậm, hãy thực hiện theo trình tự:

1. Đo hoặc ước lượng thời gian và tài nguyên thực tế; xác định có cần chạy nền hay không.
2. Xác định dữ liệu đầu vào, người yêu cầu, tenant và quyền cần có.
3. Định nghĩa trạng thái job, kết quả, lỗi, retry và quy tắc hủy.
4. Chọn cơ chế thực thi: executor đơn giản, bảng job hoặc message queue bền vững.
5. Thiết kế cách lưu job và bảo đảm không mất thông điệp giữa transaction và publish.
6. Tạo Controller nhận yêu cầu nhanh và trả 202 hoặc redirect đến trang trạng thái.
7. Xây dựng worker có claim, idempotency, giới hạn tài nguyên và transaction ngắn.
8. Tạo endpoint/trang xem trạng thái và tải kết quả với kiểm tra quyền.
9. Bổ sung log, metrics, cleanup và chính sách lưu trữ.
10. Kiểm thử lỗi, retry, message lặp, restart worker và truy cập chéo người dùng.

## Kết luận

Đưa công việc kéo dài ra ngoài thời gian xử lý giao diện giúp request phản hồi nhanh và cho phép công việc tiếp tục dù người dùng rời trang. Trong MVC, Controller tiếp nhận yêu cầu và trả mã job; tầng ứng dụng lưu trạng thái và xếp hàng; worker thực thi, lưu kết quả và cập nhật tiến độ; View hiển thị trạng thái và kết quả theo quyền của người dùng. Thiết kế job bền vững, idempotency, retry có giới hạn, transaction phù hợp và kiểm tra quyền giúp quy trình nền đáng tin cậy hơn.
