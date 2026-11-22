# Cập nhật giao diện sau tác vụ nền

Trong module **MODEL_VIEW_CONTROLLER**, không phải request nào cũng có thể hoàn tất ngay trong thời gian người dùng chờ. Xuất báo cáo lớn, xử lý tệp, gửi thông báo hàng loạt, đồng bộ dữ liệu hoặc tạo bản sao lưu có thể mất từ vài giây đến vài phút. Nếu giữ request HTTP mở trong suốt thời gian đó, kết nối có thể timeout, tài nguyên server bị giữ lâu và người dùng không biết công việc đang tiến triển đến đâu.

Một cách tổ chức phù hợp là tiếp nhận yêu cầu, tạo một tác vụ nền, trả mã theo dõi cho client rồi cập nhật giao diện khi tác vụ thay đổi trạng thái. Controller vẫn tiếp nhận request và trả response theo hợp đồng MVC; dịch vụ ứng dụng điều phối việc tạo tác vụ; worker thực hiện công việc; Model hoặc kho trạng thái lưu tiến trình; View nhận thông tin qua polling, Server-Sent Events (SSE), WebSocket hoặc một cơ chế thông báo tương đương.

Bài học thuộc chương **MVC tương tác**. Trọng tâm là cách giữ cho giao diện phản ánh đúng trạng thái của tác vụ nền, kể cả khi người dùng chuyển trang, mất kết nối, tải lại trình duyệt hoặc nhận thông báo đến sai thứ tự.

## 1. Khi nào nên đưa công việc ra nền?

Một request đồng bộ phù hợp khi công việc ngắn, có thời gian hoàn tất dễ dự đoán và kết quả cần trả ngay để hoàn thành tương tác. Ví dụ, đọc một trang danh sách hoặc cập nhật một trường đơn giản thường không cần tạo job riêng.

Một công việc nên được cân nhắc chạy nền khi:

- Thời gian xử lý dài hoặc khó dự đoán.
- Công việc cần xử lý nhiều bản ghi, tệp lớn hoặc nhiều bước.
- Có thể cần retry khi dịch vụ bên ngoài tạm thời không khả dụng.
- Người dùng không cần giữ nguyên kết nối HTTP trong lúc xử lý.
- Công việc cần được theo dõi, tiếp tục hoặc kiểm tra kết quả sau khi người dùng rời trang.
- Nhiều tác vụ cần được xếp hàng để giới hạn mức sử dụng tài nguyên.

Ví dụ, người dùng yêu cầu xuất 80.000 giao dịch thành tệp CSV. Server có thể kiểm tra quyền và tham số, ghi nhận một yêu cầu xuất, đưa công việc vào hàng đợi rồi trả về mã tác vụ. Worker xử lý dữ liệu và lưu tệp. Giao diện hiển thị trạng thái đang chờ, đang xử lý, phần trăm hoàn thành hoặc thông báo lỗi; khi xong, người dùng nhận liên kết tải xuống.

Không phải cứ một thao tác mất hơn một ngưỡng thời gian cố định là bắt buộc phải tạo job. Hãy cân nhắc trải nghiệm người dùng, độ dài xử lý, giới hạn timeout, chi phí vận hành và nhu cầu phục hồi. Một request đồng bộ ngắn vẫn đơn giản hơn nếu nó hoàn thành ổn định trong giới hạn của hệ thống.

### 1.1. Request-response đồng bộ và tác vụ nền

| Khía cạnh | Xử lý đồng bộ | Xử lý nền |
|---|---|---|
| Thời điểm hoàn tất | Trước khi response cuối cùng được trả | Sau response tiếp nhận ban đầu |
| Kết nối HTTP | Có thể giữ mở trong lúc xử lý | Được giải phóng sớm |
| Kết quả ban đầu | Thường là kết quả nghiệp vụ cuối cùng | Thường là mã job và địa chỉ theo dõi |
| Theo dõi tiến độ | Không cần nếu xử lý ngắn | Có thể polling hoặc nhận sự kiện |
| Retry | Thường do client hoặc tầng request quyết định | Worker/queue có chính sách retry riêng |
| Phục hồi sau khi rời trang | Client thường gửi lại request nếu cần | Job tiếp tục tồn tại độc lập với trang |
| Phù hợp | CRUD ngắn, truy vấn nhanh | Export, import, xử lý media, batch, đồng bộ |

Với HTTP, phản hồi **202 Accepted** cho biết server đã chấp nhận yêu cầu để xử lý; nó không có nghĩa công việc đã hoàn tất, thậm chí worker có thể chưa bắt đầu. Hợp đồng nên cung cấp mã tác vụ và URL trạng thái để client biết bước tiếp theo.

## 2. Luồng tương tác từ lúc gửi yêu cầu đến khi hoàn tất

Một luồng tác vụ nền thường có hai phần: request khởi tạo và kênh cập nhật sau đó.

1. Người dùng chọn một thao tác có thể mất thời gian, chẳng hạn Xuất báo cáo.
2. View gửi request đến Controller.
3. Controller xác thực, kiểm tra quyền và validation đầu vào.
4. Dịch vụ ứng dụng tạo bản ghi Job, ghi nhận yêu cầu xử lý và phát lệnh cho hàng đợi.
5. Controller trả 202 Accepted cùng mã job và URL theo dõi.
6. View hiển thị trạng thái Đang chờ và bắt đầu polling hoặc đăng ký kênh sự kiện.
7. Worker nhận job, cập nhật trạng thái và tiến độ trong quá trình xử lý.
8. View nhận trạng thái mới, cập nhật tiến trình hoặc thông báo lỗi.
9. Khi job hoàn tất, View hiển thị kết quả, ví dụ liên kết tải tệp.

~~~mermaid
flowchart TD
    U["Người dùng yêu cầu xuất báo cáo"] --> V["View gửi request"]
    V --> C["Controller xác thực, phân quyền, validate"]
    C --> A["Application Service tạo Job"]
    A --> DB[("Job Store")]
    A --> Q["Queue / Broker"]
    C --> R["202 Accepted + jobId + statusUrl"]
    R --> V2["View hiển thị Đang chờ"]
    Q --> W["Background Worker"]
    W --> DB
    W --> P["Cập nhật tiến độ"]
    P --> DB
    DB --> S["Polling / SSE / WebSocket"]
    S --> V2
    W --> T{"Kết quả"}
    T -- "Thành công" --> D["Job Succeeded"]
    T -- "Thất bại" --> F["Job Failed"]
    D --> DB
    F --> DB
    DB --> S
    V2 --> E["Hiển thị kết quả hoặc lỗi"]
~~~

Job Store là nơi lưu trạng thái có thẩm quyền. Queue giúp phân phối công việc cho worker; queue không nhất thiết là nơi lưu trạng thái cuối cùng mà giao diện đọc. Kênh thông báo có thể phát tín hiệu rằng trạng thái đã thay đổi, còn View có thể đọc lại Job Store qua endpoint trạng thái để nhận dữ liệu đầy đủ.

### 2.1. Sơ đồ trình tự

~~~mermaid
sequenceDiagram
    autonumber
    actor User as Người dùng
    participant View as View
    participant C as MVC Controller
    participant App as Application Service
    participant Store as Job Store
    participant Queue as Message Queue
    participant Worker as Background Worker
    participant Notify as Notification Channel

    User->>View: Chọn Xuất báo cáo
    View->>C: POST /exports
    C->>App: startExport(command)
    App->>Store: Tạo Job ở trạng thái QUEUED
    App->>Queue: Phát lệnh xử lý
    App-->>C: JobId
    C-->>View: 202 Accepted + statusUrl
    View->>C: GET /jobs/{jobId}
    C->>Store: Đọc trạng thái
    Store-->>C: QUEUED
    C-->>View: Trạng thái Đang chờ
    Queue-->>Worker: Nhận lệnh
    Worker->>Store: Chuyển sang RUNNING
    Worker->>Store: Cập nhật progress
    Worker->>Notify: Phát sự kiện tiến độ
    Notify-->>View: Tiến độ mới
    View->>C: GET /jobs/{jobId}
    C->>Store: Đọc trạng thái mới nhất
    Store-->>C: RUNNING, progress
    C-->>View: Trạng thái mới
    Worker->>Store: Ghi SUCCEEDED và kết quả
    Worker->>Notify: Phát sự kiện hoàn tất
    Notify-->>View: Job hoàn tất
    View->>C: GET /jobs/{jobId}
    C->>Store: Đọc kết quả
    Store-->>C: SUCCEEDED, resultUrl
    C-->>View: Kết quả cuối cùng
    View-->>User: Hiển thị nút tải tệp
~~~

Sơ đồ cho thấy thông báo và dữ liệu trạng thái là hai việc có thể tách nhau. Sự kiện giúp View biết cần cập nhật; endpoint trạng thái cung cấp bản ghi mới nhất. Cách này giúp xử lý reconnect và thông báo đến sai thứ tự dễ hơn.

## 3. Biểu diễn trạng thái của Job

Job là một tài nguyên có vòng đời. Nó cần một định danh, trạng thái, thông tin tiến độ và dữ liệu kết quả phù hợp. Không nên chỉ lưu một cờ boolean như **isDone**, vì giao diện cần phân biệt đang chờ, đang chạy, thất bại hoặc bị hủy.

Một mô hình trạng thái cơ bản:

| Trạng thái | Ý nghĩa | Trạng thái kết thúc? |
|---|---|---|
| **QUEUED** | Đã tiếp nhận, đang chờ worker | Không |
| **RUNNING** | Worker đang thực hiện | Không |
| **CANCEL_REQUESTED** | Đã nhận yêu cầu hủy, worker cần kiểm tra và dừng an toàn | Không |
| **SUCCEEDED** | Công việc hoàn tất thành công | Có |
| **FAILED** | Công việc thất bại sau chính sách xử lý/retry | Có |
| **CANCELLED** | Công việc đã dừng theo yêu cầu hủy | Có |

Có thể bổ sung **RETRY_WAIT** hoặc **PAUSED** nếu trải nghiệm và chính sách vận hành cần phân biệt các trạng thái này. Không nên tạo quá nhiều trạng thái chỉ để phản ánh chi tiết nội bộ mà người dùng không cần biết.

~~~mermaid
stateDiagram-v2
    [*] --> QUEUED
    QUEUED --> RUNNING
    QUEUED --> CANCELLED: Hủy trước khi chạy
    RUNNING --> SUCCEEDED: Hoàn tất
    RUNNING --> FAILED: Hết retry / lỗi cuối
    RUNNING --> CANCEL_REQUESTED: Yêu cầu hủy
    CANCEL_REQUESTED --> CANCELLED: Worker dừng an toàn
    CANCEL_REQUESTED --> SUCCEEDED: Hoàn tất trước khi dừng
    CANCEL_REQUESTED --> FAILED: Gặp lỗi khi dừng
~~~

Việc cho phép **CANCEL_REQUESTED** chuyển thành **SUCCEEDED** phản ánh một tình huống có thể xảy ra: yêu cầu hủy đến muộn, trong khi công việc vừa hoàn tất. Hệ thống cần định nghĩa thứ tự ưu tiên và quy tắc chuyển trạng thái để tránh hai kết quả cuối cùng cạnh tranh nhau.

### 3.1. Những trường dữ liệu cần thiết

Một Job có thể chứa các trường như:

| Trường | Mục đích |
|---|---|
| **id** | Định danh tác vụ |
| **type** | Loại công việc, ví dụ REPORT_EXPORT |
| **ownerId / tenantId** | Chủ sở hữu và phạm vi dữ liệu |
| **status** | Trạng thái hiện tại |
| **progress** | Phần trăm hoặc chỉ số tiến độ, nếu có thể đo |
| **currentStep** | Bước hiện tại để giải thích tiến trình |
| **createdAt, startedAt, updatedAt, finishedAt** | Thời điểm trong vòng đời |
| **attempt** | Số lần worker đã thử |
| **messageCode** | Mã thông báo có thể hiển thị an toàn |
| **resultRef** | Tham chiếu đến kết quả, ví dụ tệp xuất |
| **errorCode** | Mã lỗi có thể phân loại |
| **version** | Phiên bản để phát hiện cập nhật cũ hoặc cạnh tranh |

Không nên lưu toàn bộ stack trace hoặc dữ liệu nhạy cảm trong trường message trả về cho client. Chi tiết kỹ thuật có thể được ghi trong log nội bộ với quyền truy cập phù hợp.

### 3.2. Tiến độ phải có ý nghĩa

Một con số phần trăm chỉ hữu ích nếu nó phản ánh công việc thực tế. Nếu hệ thống chưa thể ước lượng, hiển thị trạng thái theo bước như “Đang đọc dữ liệu”, “Đang tạo tệp”, “Đang hoàn tất” thường trung thực hơn việc hiển thị một phần trăm giả định.

Nếu dùng phần trăm, cần xác định cách tính. Ví dụ, khi xử lý 10.000 dòng và đã hoàn thành 4.000 dòng, tiến độ có thể là 40%. Với các bước có chi phí rất khác nhau, tỷ lệ số bước đã xong có thể gây hiểu lầm; cần trọng số hoặc mô tả theo giai đoạn.

Tiến độ nên tăng theo quy tắc nhất quán trong một lần chạy. Nếu worker retry từ đầu, UI có thể thấy tiến độ giảm. Khi điều đó xảy ra, cần công bố rằng job đang chạy lại hoặc hiển thị attempt mới, thay vì để người dùng tưởng hệ thống bị lỗi.

### 3.3. Phiên bản và thời điểm cập nhật

Mỗi lần thay đổi trạng thái có thể tăng **version** hoặc cập nhật **updatedAt**. View dùng version để bỏ qua thông báo cũ đến muộn. Ví dụ, UI đã nhận version 12 thì không nên thay bằng một sự kiện version 10 được phát trễ.

Thời gian server nên là nguồn chuẩn cho thời điểm bắt đầu và kết thúc. Client có thể định dạng thời gian theo múi giờ người dùng, nhưng không nên tự suy ra thời lượng chính xác từ đồng hồ máy khách nếu cần audit.

## 4. Vai trò của Controller, Application Service và Worker

Tác vụ nền không làm mất vai trò của MVC. Nó mở rộng luồng tương tác qua một worker chạy độc lập với request.

| Thành phần | Trách nhiệm |
|---|---|
| View | Gửi yêu cầu, hiển thị trạng thái, nhận thông báo, cho phép tải kết quả hoặc yêu cầu hủy |
| Controller | Nhận request khởi tạo, truy vấn trạng thái, yêu cầu hủy và trả response theo hợp đồng |
| Application Service | Kiểm tra điều kiện use case, tạo Job, điều phối giao dịch và cổng hàng đợi |
| Job Store / Repository | Lưu trạng thái có thẩm quyền, tiến độ, kết quả và quyền sở hữu |
| Queue / Broker | Phân phối thông điệp công việc đến worker |
| Background Worker | Thực hiện công việc, cập nhật trạng thái, xử lý retry và hủy |
| Notification Gateway | Phát sự kiện cho client qua SSE, WebSocket hoặc cơ chế thông báo khác |

Worker không phải một Controller thứ hai. Worker thường không nhận HTTP request từ người dùng; nó nhận một lệnh nội bộ, tải dữ liệu job và thực hiện công việc. Nghiệp vụ quan trọng vẫn nên được đặt trong application/domain service có thể kiểm thử độc lập.

### 4.1. Controller trả về mã theo dõi

Ví dụ một endpoint khởi tạo export:

~~~java
public record StartExportRequest(
    LocalDate from,
    LocalDate to,
    String format
) {}

public record JobAcceptedResponse(
    UUID jobId,
    String status,
    URI statusUrl
) {}

@PostMapping("/exports")
public ResponseEntity<JobAcceptedResponse> startExport(
    @Valid @RequestBody StartExportRequest request
) {
    var jobId = exports.start(
        new StartExportCommand(request.from(), request.to(), request.format())
    );

    var statusUrl = URI.create("/api/jobs/" + jobId);
    var body = new JobAcceptedResponse(jobId, "QUEUED", statusUrl);

    return ResponseEntity.accepted()
        .location(statusUrl)
        .body(body);
}
~~~

Response 202 cùng **Location** cho biết nơi client có thể đọc trạng thái. Tên trường và URL cụ thể là hợp đồng của API; có thể chọn cách biểu diễn khác miễn là nhất quán.

### 4.2. Endpoint đọc trạng thái

~~~java
public record JobStatusResponse(
    UUID id,
    String status,
    Integer progress,
    String currentStep,
    Instant updatedAt,
    URI resultUrl,
    String errorCode
) {}

@GetMapping("/jobs/{jobId}")
public JobStatusResponse getJob(@PathVariable UUID jobId) {
    return jobs.getStatusForCurrentUser(jobId);
}
~~~

Phương thức **getStatusForCurrentUser** cần kiểm tra quyền xem job theo người dùng hoặc tenant hiện tại. Biết một job ID không tự động có quyền xem trạng thái hay tải kết quả.

### 4.3. Endpoint yêu cầu hủy

~~~java
@PostMapping("/jobs/{jobId}/cancel")
public ResponseEntity<Void> cancel(@PathVariable UUID jobId) {
    jobs.requestCancellationForCurrentUser(jobId);
    return ResponseEntity.accepted().build();
}
~~~

Hủy một tác vụ đang chạy thường là yêu cầu hợp tác. Controller ghi nhận yêu cầu; worker kiểm tra cờ hủy tại các điểm an toàn và dừng công việc khi có thể. Response 202 có thể có nghĩa yêu cầu hủy đã được tiếp nhận, chưa chắc worker đã dừng ngay.

## 5. Tạo và phân phối Job một cách tin cậy

Một lỗi phổ biến là lưu Job trong database rồi gửi message đến queue bằng hai thao tác độc lập. Nếu database commit thành công nhưng gửi message thất bại, job nằm ở trạng thái QUEUED nhưng không có worker xử lý. Nếu message được gửi trước khi transaction commit rồi transaction rollback, worker có thể nhận một job chưa tồn tại.

Có thể dùng **Transactional Outbox**: trong cùng transaction, application service ghi Job và một bản ghi Outbox. Một publisher đọc Outbox rồi gửi message đến broker. Sau khi gửi thành công, publisher đánh dấu event đã phát. Cách này giảm nguy cơ mất thông điệp giữa database và queue.

~~~mermaid
flowchart LR
    A["Application Service"] --> TX["Một transaction"]
    TX --> J[("Job record")]
    TX --> O[("Outbox record")]
    O --> P["Outbox Publisher"]
    P --> Q["Message Broker"]
    Q --> W["Worker"]
    W --> J
~~~

Outbox publisher có thể gửi trùng khi gặp lỗi sau khi broker đã nhận message nhưng publisher chưa kịp đánh dấu đã gửi. Vì vậy, worker cần xử lý message theo cách idempotent hoặc có cơ chế deduplication. Không nên giả định queue chỉ giao message đúng một lần.

### 5.1. Worker phải chịu được retry

Một worker có thể bị dừng giữa chừng do process restart, máy chủ lỗi hoặc timeout. Hàng đợi có thể giao lại message. Worker nên:

- Kiểm tra job còn ở trạng thái có thể nhận xử lý.
- Ghi nhận attempt và thời điểm bắt đầu.
- Chỉ thực hiện các bước có thể retry an toàn hoặc dùng idempotency key.
- Cập nhật trạng thái theo điều kiện để tránh worker cũ ghi đè kết quả mới.
- Áp dụng retry có giới hạn và backoff cho lỗi tạm thời.
- Chuyển sang FAILED hoặc dead-letter theo chính sách khi hết retry.

Không retry vô hạn với lỗi dữ liệu hoặc lỗi nghiệp vụ không thể khắc phục. Người dùng cần nhận một kết quả cuối cùng có ý nghĩa thay vì thấy “Đang xử lý” mãi mãi.

### 5.2. Giữ ranh giới transaction ngắn

Không giữ transaction database mở trong toàn bộ thời gian xử lý một tệp lớn hoặc gọi nhiều dịch vụ ngoài. Worker có thể đọc dữ liệu theo batch, cập nhật tiến độ trong các transaction ngắn và ghi kết quả cuối cùng ở bước phù hợp.

Nếu job có nhiều bước, lưu checkpoint hoặc trạng thái bước để có thể tiếp tục từ vị trí an toàn. Cần xác định dữ liệu đầu vào của job là snapshot tại thời điểm khởi tạo hay dữ liệu mới nhất tại thời điểm worker chạy. Quyết định này ảnh hưởng đến kết quả và cần được thể hiện trong hợp đồng nghiệp vụ.

## 6. Các cách cập nhật giao diện

Có ba cơ chế thường dùng: polling, Server-Sent Events và WebSocket. Không có cơ chế nào tốt nhất cho mọi ứng dụng.

| Cơ chế | Cách hoạt động | Ưu điểm | Hạn chế | Phù hợp khi |
|---|---|---|---|---|
| Polling | Client định kỳ gọi GET trạng thái | Đơn giản, dễ triển khai và phục hồi sau mất kết nối | Có request lặp và độ trễ theo chu kỳ | Ít job, tần suất cập nhật thấp |
| SSE | Server giữ kết nối HTTP và gửi event một chiều | Phù hợp cập nhật tiến độ từ server đến trình duyệt; tự reconnect trong môi trường hỗ trợ | Một chiều; cần quản lý kết nối và proxy timeout | Server chủ yếu đẩy trạng thái đến UI |
| WebSocket | Client và server trao đổi hai chiều qua kết nối lâu dài | Tương tác hai chiều, độ trễ thấp | Phức tạp hơn về kết nối, scale, auth và vận hành | Có nhiều tương tác thời gian thực liên tục |

### 6.1. Polling

Polling là cách dễ bắt đầu nhất. Sau khi nhận job ID, client gọi GET /api/jobs/{id} theo chu kỳ để đọc trạng thái.

Một số nguyên tắc:

- Bắt đầu polling sau khi nhận 202.
- Chỉ polling khi job còn ở trạng thái chưa kết thúc.
- Dùng khoảng thời gian phù hợp, ví dụ vài giây, tùy độ quan trọng của cập nhật.
- Tăng dần khoảng chờ (backoff) nếu job kéo dài hoặc server trả 429/503.
- Dừng polling khi job thành công, thất bại hoặc bị hủy.
- Dừng hoặc giảm polling khi tab ở nền nếu không cần cập nhật tức thời.
- Dùng **Retry-After**, ETag hoặc updatedAt nếu API hỗ trợ để giảm tải.

Không polling quá dày, chẳng hạn nhiều lần mỗi giây cho hàng nghìn trình duyệt. Điều đó có thể tạo tải lớn hơn chính tác vụ nền.

### 6.2. Server-Sent Events (SSE)

SSE cho phép server gửi luồng event một chiều đến trình duyệt qua HTTP. Client mở một kết nối EventSource và nhận các event như job-progress, job-completed hoặc job-failed.

Ví dụ payload:

~~~text
event: job-progress
id: 18
data: {"jobId":"...","status":"RUNNING","progress":45,"currentStep":"Đang tạo tệp"}

event: job-completed
id: 19
data: {"jobId":"...","status":"SUCCEEDED","resultUrl":"/api/jobs/.../result"}
~~~

SSE phù hợp khi server chủ yếu thông báo cho UI và client không cần gửi lệnh qua cùng kết nối. Trình duyệt có thể tự kết nối lại; server có thể dùng event ID để tiếp tục từ sự kiện cuối cùng nếu hạ tầng hỗ trợ. Khi reconnect, client vẫn nên đọc trạng thái hiện tại từ endpoint để tránh bỏ sót thay đổi.

Cần lưu ý xác thực và vận hành: EventSource gốc có giới hạn cách thiết lập header tùy chỉnh, kết nối có thể bị proxy đóng, và mỗi kết nối chiếm tài nguyên. Có thể dùng cookie session, URL ký có thời hạn hoặc thư viện client phù hợp với cơ chế auth; tránh đưa bearer token lâu dài vào URL.

### 6.3. WebSocket

WebSocket tạo kết nối hai chiều. Client có thể subscribe vào kênh job, gửi yêu cầu hủy hoặc tương tác thời gian thực khác. Server phát tiến độ qua kết nối đó.

WebSocket phù hợp khi ứng dụng có nhiều luồng trao đổi liên tục, ví dụ bảng điều khiển theo dõi nhiều worker hoặc giao diện cộng tác. Nếu chỉ cần hiển thị tiến độ của một tác vụ xuất báo cáo, WebSocket có thể là mức phức tạp không cần thiết.

Khi dùng WebSocket, cần xác thực lúc thiết lập kết nối, kiểm tra quyền subscribe từng job, giới hạn số kết nối và xử lý reconnect. Không phát mọi event cho mọi client; mỗi người dùng chỉ nhận thông tin của job mà họ được phép xem.

### 6.4. Kết hợp thông báo và đọc trạng thái

Một thiết kế bền vững thường dùng event như tín hiệu “có thay đổi” và endpoint GET như nguồn dữ liệu chuẩn. Khi nhận event, client có thể gọi GET /jobs/{id} để lấy snapshot mới nhất. Cách này giúp xử lý event bị trùng, bị mất hoặc đến sai thứ tự.

Với hệ thống ít yêu cầu thời gian thực, polling một mình có thể đủ. Chọn cơ chế theo tần suất cập nhật, số client, yêu cầu độ trễ, hạ tầng và độ phức tạp mà nhóm có thể vận hành.

## 7. Cập nhật trạng thái View một cách nhất quán

View cần biểu diễn rõ trạng thái của job. Không chỉ thay phần trăm; người dùng cần biết hệ thống đã tiếp nhận yêu cầu chưa, đang làm gì, có thất bại không và kết quả nằm ở đâu.

| Trạng thái Job | Cách View có thể hiển thị |
|---|---|
| **QUEUED** | “Đã tiếp nhận, đang chờ xử lý” |
| **RUNNING** | Thanh tiến độ và bước hiện tại |
| **CANCEL_REQUESTED** | “Đang dừng tác vụ…” |
| **SUCCEEDED** | “Hoàn tất” và nút xem/tải kết quả |
| **FAILED** | Thông báo lỗi an toàn và hướng thử lại |
| **CANCELLED** | “Đã hủy” |

### 7.1. Không hiển thị thành công trước khi server xác nhận

Với một tác vụ nền, việc nhận 202 chỉ xác nhận yêu cầu đã được tiếp nhận. View không nên hiển thị “Xuất báo cáo thành công” ngay sau response này. Thông điệp phù hợp là “Đã bắt đầu yêu cầu xuất báo cáo” hoặc “Đang chờ xử lý”.

Chỉ khi nhận trạng thái **SUCCEEDED** và kết quả hợp lệ, View mới hiển thị nút tải tệp. Nếu job thất bại, View hiển thị lỗi và hành động tiếp theo được phép, ví dụ thử lại.

### 7.2. Tránh cập nhật bằng dữ liệu cũ

Polling và event có thể hoàn tất không theo thứ tự. Ví dụ, request polling cũ mất nhiều thời gian hơn request mới và trả về sau. Nếu UI áp dụng mọi response theo thứ tự đến, trạng thái RUNNING cũ có thể ghi đè SUCCEEDED mới.

Có thể dùng **version** tăng dần, **updatedAt** do server cấp hoặc sequence number. Chỉ áp dụng snapshot có phiên bản mới hơn phiên bản hiện tại. Với event đến trùng, thao tác cập nhật UI nên idempotent.

### 7.3. Tránh nhầm trạng thái giữa các job

Một trang có thể theo dõi nhiều tác vụ cùng lúc. State nên được lập chỉ mục theo job ID. Không dùng một biến progress toàn cục cho mọi tác vụ, vì tiến độ của job này có thể ghi đè job khác.

Nếu người dùng gửi lại cùng yêu cầu, server có thể trả một job mới hoặc nhận diện một yêu cầu trùng bằng idempotency key. View cần biết job ID nào tương ứng với thao tác nào để hiển thị kết quả chính xác.

### 7.4. Giữ trạng thái khi người dùng tải lại hoặc chuyển trang

Job tồn tại độc lập với component hoặc tab. Nếu người dùng tải lại trang, giao diện có thể khôi phục danh sách job đang hoạt động từ server bằng một endpoint như GET /api/jobs?status=active. Nếu người dùng mở lại trang sau vài phút, View đọc trạng thái hiện tại và hiển thị kết quả cuối cùng.

Không chỉ lưu job ID trong biến JavaScript tạm thời nếu trải nghiệm yêu cầu tiếp tục theo dõi sau khi reload. Có thể lưu tham chiếu không nhạy cảm trong URL hoặc trạng thái ứng dụng, nhưng quyền truy cập vẫn phải được kiểm tra ở server.

## 8. Ví dụ giao diện polling

Đoạn JavaScript sau minh họa polling có backoff và dừng khi job đạt trạng thái kết thúc. Đây là pseudocode để giải thích luồng; trong ứng dụng thực tế nên dùng cơ chế lifecycle của framework UI để hủy request và giải phóng tài nguyên khi component bị tháo.

~~~javascript
async function watchJob(jobId, onUpdate, signal) {
  let delayMs = 2000;

  while (!signal.aborted) {
    try {
      const response = await fetch("/api/jobs/" + jobId, {
        headers: { "Accept": "application/json" },
        signal
      });

      if (!response.ok) {
        if (response.status === 429 || response.status >= 500) {
          await wait(delayMs, signal);
          delayMs = Math.min(delayMs * 2, 15000);
          continue;
        }
        throw new Error("Không thể đọc trạng thái tác vụ");
      }

      const job = await response.json();
      onUpdate(job);

      if (["SUCCEEDED", "FAILED", "CANCELLED"].includes(job.status)) {
        return;
      }

      delayMs = 2000;
      await wait(delayMs, signal);
    } catch (error) {
      if (signal.aborted) {
        return;
      }
      if (error instanceof TypeError) {
        await wait(delayMs, signal);
        delayMs = Math.min(delayMs * 2, 15000);
        continue;
      }
      throw error;
    }
  }
}
~~~

Caller có thể tạo AbortController và truyền signal vào watchJob; gọi abort() khi component bị tháo hoặc người dùng rời màn hình. Hàm wait cần hỗ trợ signal để thời gian chờ cũng có thể bị hủy. Vòng lặp cần tránh tạo nhiều watcher cho cùng job và kiểm tra version trước khi cập nhật UI. Ví dụ trên chỉ nêu cấu trúc khái niệm, không phải một polling library hoàn chỉnh.

### 8.1. Cập nhật View theo state

Một View có thể ánh xạ trạng thái thành phần trình bày:

~~~javascript
function renderJob(job) {
  switch (job.status) {
    case "QUEUED":
      return showStatus("Đã tiếp nhận, đang chờ xử lý");

    case "RUNNING":
      return showProgress(job.progress, job.currentStep);

    case "CANCEL_REQUESTED":
      return showStatus("Đang dừng tác vụ...");

    case "SUCCEEDED":
      return showDownloadLink(job.resultUrl);

    case "FAILED":
      return showError(job.message);

    case "CANCELLED":
      return showStatus("Tác vụ đã được hủy");

    default:
      return showStatus("Không xác định được trạng thái");
  }
}
~~~

Nếu server trả một trạng thái mới chưa biết do phiên bản API thay đổi, View nên có cách hiển thị dự phòng và ghi nhận lỗi tương thích. Không giả định mọi trạng thái ngoài danh sách đều có nghĩa là thành công.

## 9. Hủy, retry và timeout

### 9.1. Hủy là một yêu cầu, không phải phép dừng tức thời

Một worker có thể đang thực hiện bước không thể ngắt ngay, ví dụ ghi một tệp hoặc gọi dịch vụ ngoài. Endpoint hủy thường ghi nhận **CANCEL_REQUESTED**; worker kiểm tra cờ này tại các điểm an toàn rồi dừng.

Cần xác định:

- Job ở trạng thái QUEUED có thể bị loại khỏi queue hay được đánh dấu hủy để worker bỏ qua?
- Job đang chạy kiểm tra hủy sau mỗi batch hay sau mỗi bước?
- Nếu công việc đã hoàn tất trước khi yêu cầu hủy đến, trạng thái cuối cùng là SUCCEEDED hay CANCELLED?
- Các tài nguyên tạm thời có được dọn dẹp khi hủy không?
- Một phần kết quả đã tạo có được giữ lại hay phải xóa?

Không hứa với người dùng “Đã hủy” ngay khi server mới nhận yêu cầu. Hãy hiển thị “Đang dừng” cho đến khi worker xác nhận trạng thái kết thúc.

### 9.2. Retry phải phân biệt lỗi tạm thời và lỗi cuối cùng

Lỗi mạng, dịch vụ ngoài tạm thời không khả dụng hoặc giới hạn rate có thể được retry với exponential backoff và jitter. Lỗi dữ liệu không hợp lệ, thiếu quyền hoặc vi phạm quy tắc nghiệp vụ thường không nên retry tự động.

UI có thể hiển thị “Đang thử lại” nếu trạng thái này có ý nghĩa với người dùng. Nếu không, có thể giữ trạng thái đang xử lý và chỉ hiển thị FAILED khi hết số lần thử. Cần ghi attempt để vận hành có thể chẩn đoán.

### 9.3. Timeout và job bị treo

Job có thể bị kẹt nếu worker chết mà không cập nhật trạng thái. Cần có heartbeat hoặc lease để hệ thống nhận biết worker không còn hoạt động. Một bộ giám sát có thể đánh dấu job quá hạn, đưa lại vào queue hoặc chuyển sang lỗi tùy chính sách.

Không dùng một timeout duy nhất cho mọi loại job. Export nhỏ và xử lý video lớn có thời gian kỳ vọng khác nhau. Giới hạn cần phù hợp với tài nguyên và SLA của từng loại tác vụ.

## 10. Bảo mật và quyền truy cập trạng thái

Job status endpoint, event stream và result URL đều là bề mặt truy cập dữ liệu. Chỉ vì người dùng biết job ID không có nghĩa họ được quyền đọc.

- Kiểm tra owner hoặc tenant của job trên mỗi request đọc trạng thái.
- Kiểm tra quyền hủy trước khi nhận lệnh cancel.
- Kiểm tra quyền tải kết quả; không dùng URL đoán được làm cơ chế bảo vệ.
- Với liên kết tải tạm thời, dùng URL ký có thời hạn và phạm vi hẹp nếu phù hợp.
- Không phát dữ liệu cá nhân, nội dung file hoặc thông tin nội bộ trong event tiến độ.
- Giới hạn số job đang hoạt động và tần suất polling theo người dùng/tenant.
- Bảo vệ SSE/WebSocket bằng xác thực và kiểm tra quyền subscribe.
- Ghi audit cho thao tác khởi tạo, hủy và tải kết quả theo yêu cầu hệ thống.

Nếu job chạy dưới quyền của người dùng, cần xác định quyền được kiểm tra tại thời điểm tạo job hay tại thời điểm worker thực thi. Một số hệ thống cần kiểm tra lại quyền hoặc phạm vi dữ liệu trước khi truy cập tài nguyên nhạy cảm, vì quyền có thể bị thu hồi sau khi job được xếp hàng.

## 11. Khả năng quan sát và vận hành

Một job có thể đi qua Controller, application service, database, queue, worker và dịch vụ ngoài. Để điều tra lỗi, cần một mã tương quan hoặc trace ID xuyên suốt các thành phần.

Nên ghi nhận:

- Job ID, loại job, owner/tenant và correlation ID.
- Thời gian xếp hàng, thời gian chờ, thời gian chạy và thời điểm hoàn tất.
- Attempt, worker nhận xử lý và mã lỗi phân loại.
- Các mốc tiến độ quan trọng, không nhất thiết log từng phần trăm.
- Số job QUEUED/RUNNING/FAILED và độ trễ queue.
- Tỷ lệ retry, job quá hạn và lỗi phát sinh khi gửi notification.

Log cần tránh chứa access token, dữ liệu cá nhân hoặc nội dung kết quả nhạy cảm. Có thể dùng message code để giao diện hiển thị thông báo thân thiện trong khi log nội bộ giữ thông tin kỹ thuật cần thiết.

## 12. Kiểm thử luồng tác vụ nền

Kiểm thử cần xác nhận cả request ban đầu, vòng đời job, worker và cập nhật View.

### 12.1. Kiểm thử Controller và hợp đồng HTTP

- Request hợp lệ tạo job và trả 202 Accepted.
- Response có job ID và status URL hợp lệ.
- Request không hợp lệ không tạo job.
- Người dùng không có quyền không thể khởi tạo hoặc xem job.
- Job ID không tồn tại trả 404 theo hợp đồng.
- Job thuộc tenant khác không bị lộ trạng thái hoặc kết quả.

### 12.2. Kiểm thử application service và worker

- Job mới được tạo ở trạng thái QUEUED.
- Message chỉ được phát theo cơ chế bảo đảm nhất quán đã chọn.
- Worker chuyển trạng thái đúng và cập nhật tiến độ.
- Worker chạy lại không tạo tác dụng phụ trùng ngoài chính sách.
- Lỗi tạm thời được retry có giới hạn.
- Lỗi cuối cùng chuyển job sang FAILED.
- Yêu cầu hủy được worker nhận biết và xử lý an toàn.
- Worker chết hoặc hết lease được phát hiện theo chính sách.

### 12.3. Kiểm thử kênh cập nhật

- Polling dừng khi job ở trạng thái kết thúc.
- SSE reconnect không làm UI bỏ qua trạng thái cuối.
- Event trùng hoặc đến sai thứ tự không làm lùi version.
- Mất kết nối rồi kết nối lại vẫn lấy được snapshot mới nhất.
- Nhiều job được cập nhật độc lập theo job ID.
- UI không hiển thị thành công khi mới nhận 202.
- Người dùng tải lại trang vẫn xem được job đang chạy hoặc đã hoàn tất.

### 12.4. Kiểm thử giao diện và khả năng truy cập

- Trạng thái đang chờ, đang chạy, thành công, thất bại và hủy được hiển thị rõ.
- Thanh tiến độ có nhãn và giá trị phù hợp; nếu không đo được thì dùng trạng thái dạng bước.
- Thông báo trạng thái được công bố cho trình đọc màn hình qua vùng live phù hợp.
- Màu sắc không phải tín hiệu duy nhất.
- Người dùng có thể điều hướng bằng bàn phím và tải kết quả bằng thao tác rõ ràng.
- Khi lỗi, giao diện đưa ra hành động tiếp theo phù hợp.

## 13. Những lỗi thiết kế thường gặp

| Dấu hiệu | Hệ quả | Cách cải thiện |
|---|---|---|
| Giữ request HTTP mở cho công việc kéo dài | Timeout và giữ tài nguyên kết nối | Trả 202 cùng job ID và status URL |
| Trả 200/202 nhưng giao diện báo hoàn tất | Người dùng hiểu sai trạng thái | Phân biệt tiếp nhận với hoàn thành |
| Chỉ lưu trạng thái trong memory của worker | Mất trạng thái khi process restart | Lưu Job trong kho bền vững |
| Ghi Job và gửi queue tách rời không có cơ chế phục hồi | Job có thể không được xử lý hoặc message mồ côi | Dùng outbox hoặc cơ chế điều phối tin cậy |
| Giả định message chỉ giao đúng một lần | Retry có thể chạy trùng tác dụng | Thiết kế worker idempotent và deduplication |
| Polling quá thường xuyên | Tạo tải không cần thiết | Backoff, giới hạn tần suất và dừng đúng lúc |
| Event là nguồn trạng thái duy nhất | Mất event khiến UI không thể đồng bộ | Đọc snapshot từ Job Store |
| Không kiểm tra version | Event cũ ghi đè trạng thái mới | Dùng version hoặc sequence number |
| Job ID là bí mật duy nhất | Lộ trạng thái hoặc kết quả của người khác | Authorization theo owner/tenant |
| Hủy được coi là tức thời | UI báo hủy trong khi worker vẫn đang chạy | Dùng trạng thái CANCEL_REQUESTED và xác nhận từ worker |
| Không có trạng thái lỗi cuối cùng | Job có thể hiển thị đang chạy vô hạn | Heartbeat, lease và timeout |
| Không giữ lịch sử job cần thiết | Người dùng không thể tra cứu kết quả sau khi rời trang | Lưu trạng thái và chính sách retention |

## 14. Checklist thiết kế cập nhật giao diện

- [ ] Công việc dài được tiếp nhận như một Job có định danh.
- [ ] Controller trả 202 Accepted và URL đọc trạng thái.
- [ ] Job Store lưu trạng thái có thẩm quyền và tiến độ cần thiết.
- [ ] Worker có cơ chế retry, idempotency và phục hồi khi process dừng.
- [ ] View phân biệt QUEUED, RUNNING, SUCCEEDED, FAILED và CANCELLED.
- [ ] Chọn polling, SSE hoặc WebSocket theo nhu cầu thực tế.
- [ ] Event chỉ thông báo thay đổi; UI có thể đọc lại snapshot mới nhất.
- [ ] Version hoặc sequence giúp bỏ qua cập nhật cũ và trùng.
- [ ] Trạng thái vẫn khôi phục được sau reload hoặc reconnect.
- [ ] Hủy là yêu cầu hợp tác và có trạng thái kết thúc được xác nhận.
- [ ] Quyền đọc, hủy và tải kết quả được kiểm tra theo owner/tenant.
- [ ] Có quan sát queue, worker, retry, job quá hạn và lỗi cuối cùng.
- [ ] Kiểm thử request, worker, kênh thông báo và giao diện ở cả trường hợp lỗi.

Cập nhật giao diện sau tác vụ nền là một hợp đồng xuyên suốt giữa Controller, dịch vụ ứng dụng, worker, kho trạng thái và View. Khi job có vòng đời rõ ràng, server lưu trạng thái bền vững và client biết cách đồng bộ lại, người dùng có thể rời trang hoặc mất kết nối mà vẫn hiểu công việc đang ở đâu và nhận được kết quả đáng tin cậy.
