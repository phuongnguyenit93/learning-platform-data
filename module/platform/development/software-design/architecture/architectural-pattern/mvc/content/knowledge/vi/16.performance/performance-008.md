# Tác vụ bất đồng bộ và phản hồi tiến độ

Trong ứng dụng MVC, một request HTTP thường được xử lý trong thời gian ngắn: Controller nhận dữ liệu, gọi use case, tạo response và kết thúc. Nhưng có những công việc mất nhiều giây hoặc nhiều phút như xuất báo cáo lớn, nhập dữ liệu, xử lý tệp, gửi hàng loạt thông báo hoặc đồng bộ với hệ thống bên ngoài. Nếu giữ request mở trong suốt quá trình, người dùng phải chờ, kết nối có thể timeout và tài nguyên của web server bị chiếm dụng.

Một cách thiết kế phù hợp là **tiếp nhận yêu cầu nhanh, đưa công việc vào xử lý nền và trả cho client một mã công việc (job ID)**. Worker thực hiện tác vụ độc lập; trạng thái và tiến độ được lưu ở nơi có thể truy xuất; View dùng polling, Server-Sent Events (SSE) hoặc WebSocket để cập nhật thông tin. Controller vẫn giữ vai trò HTTP adapter, còn application service điều phối use case và worker thực hiện phần công việc dài.

Tác vụ bất đồng bộ không đơn giản là chạy một thread khác. Cần thiết kế vòng đời job, trạng thái bền vững, quyền truy cập, retry, hủy, idempotency, transaction và cách phục hồi khi tiến trình bị dừng. Bài học thuộc module **MODEL_VIEW_CONTROLLER**, nơi người học theo dõi luồng request, thiết kế hợp đồng dữ liệu, xử lý lỗi, bảo mật và kiểm thử ứng dụng web.

## 1. Khi nào nên xử lý tác vụ bất đồng bộ?

Một tác vụ phù hợp để chạy nền khi thời gian xử lý dài hoặc không cần hoàn tất trước khi trả response HTTP. Ví dụ:

- Xuất báo cáo lớn hoặc tạo tệp PDF/Excel.
- Nhập hàng nghìn bản ghi và kiểm tra dữ liệu.
- Xử lý video, ảnh hoặc tệp tải lên.
- Đồng bộ dữ liệu với hệ thống đối tác.
- Gửi email hoặc thông báo theo lô.
- Tính toán hoặc tổng hợp dữ liệu tốn thời gian.
- Chạy quy trình gồm nhiều bước có thể theo dõi và khôi phục.

Không phải mọi thao tác chậm đều nên chuyển sang background job. Truy vấn chậm do thiếu index, N+1 query hoặc thuật toán kém cần được tối ưu trước. Việc đưa một thao tác nhỏ vào queue có thể làm hệ thống phức tạp hơn và khiến người dùng phải chờ kết quả qua nhiều bước.

Có thể dùng các tiêu chí sau:

| Tiêu chí | Xử lý đồng bộ | Xử lý nền |
|---|---|---|
| Thời gian | Ngắn, dự đoán được | Dài hoặc biến động lớn |
| Kết quả cần ngay | Client cần kết quả trong response | Client có thể nhận job ID và chờ |
| Tài nguyên | Không chiếm worker lâu | Có thể dùng worker riêng |
| Khả năng phục hồi | Request có thể gửi lại đơn giản | Cần lưu job và trạng thái |
| Theo dõi tiến độ | Không cần hoặc chỉ có loading ngắn | Cần status, progress hoặc event |
| Tác dụng phụ | Thường nằm trong request | Có thể cần retry và idempotency |

Nếu người dùng cần kết quả để tiếp tục ngay bước tiếp theo và tác vụ chỉ mất thời gian ngắn, đồng bộ thường đơn giản hơn. Nếu tác vụ có thể vượt giới hạn timeout của proxy hoặc cần tiếp tục sau khi trình duyệt đóng, nên cân nhắc job nền có trạng thái bền vững.

## 2. Phân biệt async request và background job

Hai khái niệm thường bị nhầm:

**Asynchronous request processing** trong Spring MVC cho phép servlet request tạm nhường thread xử lý và hoàn tất response sau đó bằng Callable, DeferredResult hoặc WebAsyncTask. Request vẫn đang chờ hoàn thành; nó không tự biến công việc thành một job bền vững.

**Background job** là công việc có vòng đời độc lập với request ban đầu. Server trả response tiếp nhận công việc, worker thực hiện sau đó và client có thể truy vấn trạng thái bằng một request mới. Job có thể tiếp tục dù trình duyệt đã đóng, nếu hạ tầng lưu job và queue được thiết kế để phục hồi.

| Đặc điểm | MVC async request | Background job |
|---|---|---|
| Request ban đầu | Chưa kết thúc cho đến khi response được hoàn tất | Kết thúc sớm sau khi tiếp nhận |
| Thread servlet | Có thể được giải phóng trong lúc chờ async result | Thường chỉ xử lý bước enqueue ban đầu |
| Vòng đời | Gắn với request/timeout của container | Độc lập với request |
| Trạng thái sau restart | Không mặc định được lưu bền vững | Có thể phục hồi nếu job được lưu và queue bền vững |
| Theo dõi tiến độ | Có thể stream hoặc hoàn tất response | Thường dùng job resource, polling, SSE hoặc WebSocket |
| Phù hợp | Tác vụ bất đồng bộ ngắn trong một request | Tác vụ dài, có retry, hủy hoặc theo dõi |

~~~mermaid
flowchart TD
    A["Người dùng gửi yêu cầu"] --> B["Controller tiếp nhận"]
    B --> C{"Công việc kéo dài hoặc độc lập request?"}
    C -->|Không| D["Gọi use case đồng bộ"]
    D --> E["Trả kết quả HTTP"]
    C -->|Có| F["Tạo Job và enqueue"]
    F --> G["Trả 202 Accepted + job URL"]
    G --> H["Worker xử lý nền"]
    H --> I["Lưu trạng thái và tiến độ"]
    I --> J["Client truy vấn hoặc nhận sự kiện"]
    J --> K["View hiển thị tiến độ/kết quả"]
~~~

Điểm cốt lõi: giải phóng thread servlet không đồng nghĩa với việc công việc đã được lưu bền vững hoặc có thể phục hồi sau khi server dừng.

## 3. Thiết kế hợp đồng HTTP cho background job

Với tác vụ nền, request tạo job thường không trả kết quả cuối cùng. Nó trả thông tin cho biết server đã tiếp nhận yêu cầu và nơi client có thể theo dõi.

Ví dụ:

~~~http
POST /api/reports
Content-Type: application/json
~~~

~~~json
{
  "from": "2026-01-01",
  "to": "2026-03-31",
  "format": "PDF"
}
~~~

Response có thể là:

~~~http
HTTP/1.1 202 Accepted
Location: /api/jobs/8b1e4f5a
Retry-After: 3
Content-Type: application/json
~~~

~~~json
{
  "jobId": "8b1e4f5a",
  "status": "QUEUED",
  "statusUrl": "/api/jobs/8b1e4f5a"
}
~~~

HTTP 202 Accepted có nghĩa yêu cầu đã được tiếp nhận để xử lý, nhưng việc xử lý chưa hoàn tất và có thể chưa chắc thành công. Nó không phải bằng chứng rằng worker đã chạy hoặc dữ liệu đã được tạo xong. API nên công bố rõ client cần truy vấn ở đâu và trạng thái nào thể hiện kết quả cuối cùng.

### 3.1. Job resource

Có thể mô hình hóa trạng thái job như một tài nguyên:

~~~http
GET /api/jobs/8b1e4f5a
~~~

~~~json
{
  "jobId": "8b1e4f5a",
  "status": "RUNNING",
  "progress": {
    "completed": 420,
    "total": 1000,
    "percent": 42
  },
  "message": "Đang xử lý dữ liệu",
  "createdAt": "2026-11-19T10:00:00Z",
  "startedAt": "2026-11-19T10:00:02Z",
  "updatedAt": "2026-11-19T10:00:18Z"
}
~~~

Job resource có thể chứa:
- ID job.
- Trạng thái hiện tại.
- Tiến độ dạng số hoặc giai đoạn.
- Thời điểm tạo, bắt đầu, cập nhật và hoàn tất.
- Thông báo ngắn, không chứa dữ liệu nhạy cảm.
- Link đến kết quả khi thành công.
- Mã lỗi công khai khi thất bại.
- Thông tin retry hoặc hủy nếu hợp đồng cần.

Không nên trả stack trace, SQL, tên máy chủ, đường dẫn nội bộ hoặc thông tin credential trong job resource.

### 3.2. Các endpoint thường gặp

Một hợp đồng API có thể gồm:

| Endpoint | Mục đích |
|---|---|
| POST /api/reports | Tạo job xuất báo cáo |
| GET /api/jobs/{id} | Lấy trạng thái và tiến độ |
| GET /api/jobs/{id}/result | Tải kết quả nếu job thành công |
| POST /api/jobs/{id}/cancel | Yêu cầu hủy job |
| GET /api/jobs | Liệt kê job mà người dùng được phép xem |

Có thể dùng DELETE để xóa metadata job sau khi hoàn tất theo hợp đồng, nhưng xóa job không nên vô tình xóa dữ liệu nghiệp vụ hoặc kết quả cần lưu trữ. Cần định nghĩa rõ vòng đời kết quả và thời hạn lưu file.

## 4. Mô hình trạng thái và vòng đời job

Một job cần trạng thái rõ ràng để Controller, worker và View hiểu cùng một ý nghĩa. Ví dụ:

| Trạng thái | Ý nghĩa |
|---|---|
| QUEUED | Đã được tiếp nhận và đang chờ worker |
| RUNNING | Worker đang thực hiện |
| SUCCEEDED | Hoàn tất thành công |
| FAILED | Kết thúc do lỗi không thể phục hồi |
| CANCEL_REQUESTED | Người dùng đã yêu cầu hủy; worker chưa xác nhận dừng |
| CANCELLED | Công việc đã dừng theo yêu cầu hủy |
| RETRY_WAIT | Chờ lần thử tiếp theo |
| EXPIRED | Job hoặc kết quả đã hết thời hạn lưu |

Không phải hệ thống nào cũng cần tất cả trạng thái. Điều quan trọng là chuyển trạng thái hợp lệ và có quy tắc cho từng chuyển tiếp.

~~~mermaid
stateDiagram-v2
    [*] --> QUEUED
    QUEUED --> RUNNING
    QUEUED --> CANCELLED
    RUNNING --> SUCCEEDED
    RUNNING --> FAILED
    RUNNING --> RETRY_WAIT
    RUNNING --> CANCEL_REQUESTED
    RETRY_WAIT --> QUEUED
    CANCEL_REQUESTED --> CANCELLED
    CANCEL_REQUESTED --> SUCCEEDED
    SUCCEEDED --> EXPIRED
    FAILED --> EXPIRED
    CANCELLED --> EXPIRED
~~~

Một số hệ thống có thể không cho phép CANCEL_REQUESTED chuyển sang SUCCEEDED; hệ thống khác có thể cho phép nếu tác vụ đã hoàn tất trước khi worker nhận yêu cầu hủy. Hợp đồng cần định nghĩa cuộc đua này. Ví dụ, nếu job hoàn tất trước khi lệnh hủy được xử lý, endpoint cancel có thể trả trạng thái đã hoàn tất thay vì giả vờ hủy thành công.

### 4.1. Chuyển trạng thái phải được kiểm soát

Không cho phép client gửi trực tiếp status=SUCCEEDED hoặc progress=100. Trạng thái do server và worker quản lý. API chỉ nhận lệnh như create, cancel hoặc retry nếu được phép.

Khi cập nhật, cần kiểm tra trạng thái hiện tại. Ví dụ, chỉ QUEUED hoặc RUNNING mới có thể nhận yêu cầu hủy. FAILED có thể được retry theo chính sách; SUCCEEDED thường không được chạy lại cùng job ID.

Có thể dùng optimistic locking hoặc cập nhật có điều kiện để tránh hai worker cùng chiếm một job:

~~~sql
UPDATE jobs
SET status = 'RUNNING',
    started_at = CURRENT_TIMESTAMP,
    version = version + 1
WHERE id = ?
  AND status = 'QUEUED';
~~~

Worker chỉ được xem là nhận job nếu số hàng cập nhật bằng 1. Cú pháp thời gian và cách trả số hàng thay đổi theo database, nhưng nguyên tắc là chuyển trạng thái nguyên tử có điều kiện.

## 5. Lưu trạng thái và tiến độ ở đâu?

Nếu tiến độ chỉ nằm trong biến của thread worker, client khác không thể đọc được; khi worker restart, trạng thái cũng mất. Với job dài hoặc cần phục hồi, trạng thái cần được lưu bền vững.

Một bảng job có thể chứa:

~~~sql
CREATE TABLE jobs (
    id              VARCHAR(64) PRIMARY KEY,
    owner_id        VARCHAR(64) NOT NULL,
    job_type        VARCHAR(80) NOT NULL,
    status          VARCHAR(24) NOT NULL,
    progress_done   BIGINT,
    progress_total  BIGINT,
    progress_unit   VARCHAR(32),
    stage           VARCHAR(80),
    result_ref      VARCHAR(512),
    error_code      VARCHAR(80),
    created_at      TIMESTAMP NOT NULL,
    started_at      TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL,
    completed_at    TIMESTAMP,
    version         BIGINT NOT NULL
);
~~~

Đây là schema minh họa; kiểu ID, timestamp, index và cột cần thiết phụ thuộc database và loại job. Nên có index theo owner_id, status và created_at nếu thường truy vấn job theo người dùng hoặc hàng đợi.

Có thể lưu dữ liệu ở:
- Database quan hệ cho job metadata và trạng thái có độ bền.
- Message broker cho hàng đợi phân phối công việc.
- Object storage cho file kết quả lớn.
- Cache cho dữ liệu tiến độ tạm thời có thể tái tạo, nếu database vẫn giữ trạng thái cuối cùng cần thiết.

Không nên lưu file kết quả lớn trực tiếp trong một cột text hoặc payload job nếu object storage phù hợp hơn. Job resource có thể giữ result_ref hoặc một link tải có thời hạn.

### 5.1. Phân biệt trạng thái, tiến độ và kết quả

- **Status** nói job đang ở giai đoạn nào.
- **Progress** mô tả mức hoàn thành có thể đo được.
- **Result** là đầu ra sau khi hoàn tất.
- **Message** là thông tin trình bày cho người dùng.

Một job có thể RUNNING nhưng chưa có phần trăm tiến độ vì chưa biết tổng khối lượng. Không nên bịa ra ước lượng chính xác. Có thể hiển thị giai đoạn như “Đang chuẩn bị dữ liệu” hoặc spinner khi tổng số bước chưa xác định.

### 5.2. Tiến độ phải phản ánh công việc thực tế

Nếu job xử lý 1.000 bản ghi, có thể cập nhật completed sau mỗi lô:

~~~java
for (int start = 0; start < rows.size(); start += batchSize) {
    List<Row> batch = rows.subList(
        start,
        Math.min(start + batchSize, rows.size())
    );

    processBatch(batch);
    progressStore.update(jobId, start + batch.size(), rows.size());
}
~~~

Tiến độ 42% chỉ có ý nghĩa nếu completed và total đo cùng một đơn vị và mẫu số ổn định. Nếu tổng số bản ghi thay đổi trong lúc xử lý, cần chọn cách tính hoặc hiển thị giai đoạn phù hợp.

Không cập nhật database cho mỗi byte hoặc mỗi dòng nếu tốc độ quá cao. Có thể gom cập nhật theo lô, theo thời gian hoặc theo mức thay đổi phần trăm để giảm tải. Tuy nhiên, phải cân bằng giữa độ mới của tiến độ và chi phí ghi trạng thái.

## 6. Tách Controller, application service và worker

Trong MVC, Controller không nên trực tiếp tạo thread và chứa toàn bộ logic xử lý nền. Có thể phân chia:

- **Controller:** xác thực request, binding, gọi use case tiếp nhận job và trả 202.
- **Application service:** kiểm tra quyền, tạo job record, ghi ý định enqueue và áp dụng quy tắc nghiệp vụ.
- **Queue/Dispatcher:** chuyển công việc đến worker.
- **Worker:** claim job, chạy use case, cập nhật tiến độ, kết quả và trạng thái cuối.
- **Repository:** lưu job metadata và dữ liệu nghiệp vụ.
- **View:** hiển thị trạng thái và cho phép người dùng theo dõi hoặc yêu cầu hủy.

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant View
    participant C as MVC Controller
    participant S as Job Application Service
    participant DB as Job Store
    participant Q as Queue
    participant W as Worker
    User->>View: Bấm xuất báo cáo
    View->>C: POST /api/reports
    C->>S: createReportJob(command)
    S->>DB: Tạo job QUEUED
    S->>Q: Enqueue job ID
    S-->>C: Job ID
    C-->>View: 202 Accepted + status URL
    Q->>W: Job ID
    W->>DB: Claim job, RUNNING
    W->>W: Xử lý từng giai đoạn
    W->>DB: Cập nhật progress
    View->>C: GET /api/jobs/{id}
    C->>DB: Đọc trạng thái
    DB-->>C: Status/progress
    C-->>View: JSON progress
    W->>DB: Lưu kết quả, SUCCEEDED
~~~

Trong triển khai thật, việc enqueue và lưu job cần được phối hợp để tránh trường hợp job record đã commit nhưng message không được gửi, hoặc message được gửi trước khi record tồn tại.

## 7. Spring @Async và TaskExecutor

Spring cung cấp @Async và TaskExecutor cho tác vụ bất đồng bộ trong cùng ứng dụng. Chúng phù hợp với công việc nền đơn giản, có tải được giới hạn và không cần broker bền vững riêng. Tuy nhiên, @Async tự nó không cung cấp job persistence, retry bền vững, dashboard tiến độ hoặc phục hồi sau process restart.

Ví dụ cấu hình executor có giới hạn:

~~~java
@Configuration
@EnableAsync
class AsyncConfiguration {

    @Bean("jobExecutor")
    ThreadPoolTaskExecutor jobExecutor() {
        ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("job-");
        executor.setRejectedExecutionHandler(
            new ThreadPoolExecutor.AbortPolicy()
        );

        return executor;
    }
}
~~~

Không nên dùng thread pool không giới hạn hoặc queue không giới hạn cho tác vụ có thể tăng đột biến. Nếu queue đầy, hệ thống cần một chính sách từ chối hoặc backpressure rõ ràng. Có thể trả 429 hoặc 503 nếu chưa tiếp nhận được công việc, thay vì trả 202 rồi âm thầm bỏ job.

### 7.1. Gọi @Async qua Spring proxy

Ví dụ:

~~~java
@Service
class ReportWorker {
    @Async("jobExecutor")
    public CompletableFuture<ReportResult> generate(
        GenerateReportCommand command
    ) {
        ReportResult result = doGenerate(command);
        return CompletableFuture.completedFuture(result);
    }
}
~~~

Lời gọi @Async cần đi qua proxy Spring trong cấu hình proxy-based thông thường. Gọi phương thức async từ một phương thức khác trong cùng instance (self-invocation) thường không kích hoạt async interception. Đặt worker ở bean riêng và inject vào application service giúp ranh giới rõ hơn.

Nếu phương thức @Async trả CompletableFuture, exception xảy ra trong tác vụ được lưu vào future. Caller cần quan sát kết quả hoặc có cơ chế xử lý lỗi; nếu bỏ qua future, lỗi có thể không được báo cáo đúng. Với phương thức void, cần cấu hình AsyncUncaughtExceptionHandler để xử lý exception không được trả qua future.

### 7.2. Không dùng @Async làm hàng đợi bền vững

Thread pool trong RAM có thể mất công việc đang chờ khi tiến trình dừng. Nếu job phải tồn tại qua restart, cần lưu job record và sử dụng queue bền vững hoặc cơ chế dispatcher có thể quét lại job QUEUED/RETRY_WAIT.

Có thể dùng message broker hoặc bảng job làm nguồn công việc. Worker cần claim job an toàn và chịu được message gửi lại. @Async vẫn có thể được dùng để chạy bước xử lý trong một instance, nhưng không nên là nơi duy nhất giữ trạng thái công việc quan trọng.

### 7.3. Không truyền request object vào worker

Request, response, session hoặc request-scoped bean có vòng đời gắn với HTTP request. Worker có thể chạy sau khi request kết thúc hoặc trên thread khác. Hãy trích xuất dữ liệu cần thiết thành command immutable:

~~~java
GenerateReportCommand command = new GenerateReportCommand(
    principal.userId(),
    request.from(),
    request.to(),
    request.format()
);

reportWorker.generate(command);
~~~

Không truyền HttpServletRequest, HttpServletResponse, BindingResult hoặc entity manager đang gắn với request vào tác vụ nền. Worker nên tải dữ liệu cần thiết theo ID và mở transaction riêng.

## 8. Đảm bảo job record và queue không bị lệch

Một lỗi phổ biến là ghi job vào database rồi gửi message sang broker trong hai thao tác độc lập:

1. Database commit job QUEUED.
2. Ứng dụng chết trước khi gửi message.
3. Job tồn tại nhưng không bao giờ được worker nhận.

Chiều ngược lại cũng có thể xảy ra: message được gửi nhưng transaction tạo job rollback, worker nhận một ID không tồn tại.

Một giải pháp là transactional outbox:

~~~mermaid
flowchart TD
    A["Transaction bắt đầu"] --> B["Insert Job: QUEUED"]
    B --> C["Insert Outbox event"]
    C --> D["Commit cùng database transaction"]
    D --> E["Outbox dispatcher đọc event"]
    E --> F["Publish message vào broker"]
    F --> G["Đánh dấu event đã publish"]
    G --> H["Worker nhận Job ID"]
~~~

Job record và outbox event được ghi trong cùng transaction database. Dispatcher gửi event sau commit. Nếu gửi thất bại, dispatcher có thể retry. Vì message có thể được gửi nhiều lần, worker phải xử lý idempotent hoặc claim job bằng cập nhật có điều kiện.

Một cách khác là worker định kỳ quét job QUEUED chưa được claim. Cách này có thể phù hợp hệ thống nhỏ, nhưng cần khóa hoặc claim atomic để tránh nhiều worker cùng xử lý một job.

## 9. Theo dõi tiến độ bằng polling

Polling là cách đơn giản: View định kỳ gọi endpoint trạng thái cho đến khi job hoàn tất.

~~~javascript
async function pollJob(jobId) {
    const response = await fetch(
        "/api/jobs/" + encodeURIComponent(jobId)
    );

    if (!response.ok) {
        throw new Error("Không thể đọc trạng thái công việc.");
    }

    const job = await response.json();
    renderJob(job);

    if (["SUCCEEDED", "FAILED", "CANCELLED", "EXPIRED"]
        .includes(job.status)) {
        return;
    }

    window.setTimeout(() => pollJob(jobId), 2000);
}
~~~

Đây là mã phía trình duyệt minh họa. Ứng dụng thực tế cần xử lý lỗi mạng, token/cookie, hủy timer khi rời trang, giới hạn tần suất và tránh nhiều vòng polling trùng nhau.

Ưu điểm:
- Dễ triển khai và dễ kiểm thử.
- Dùng HTTP request thông thường.
- Phù hợp số lượng job và người theo dõi vừa phải.
- Có thể dùng ETag hoặc Last-Modified để giảm dữ liệu truyền.

Nhược điểm:
- Có thể tạo nhiều request khi tiến độ ít thay đổi.
- Trạng thái hiển thị trễ tối đa gần bằng chu kỳ polling.
- Nhiều client cùng polling có thể tạo tải lớn.

Có thể dùng Retry-After hoặc trường pollAfterMs trong response để client điều chỉnh nhịp. Tăng khoảng thời gian khi job chạy lâu hoặc trạng thái ít thay đổi; giảm khi cần phản hồi nhanh nhưng vẫn phải giới hạn.

### 9.1. Tránh polling dồn dập

Không nên polling mỗi 50 ms cho một job chạy vài phút. Một chu kỳ 1–5 giây có thể là điểm khởi đầu cho nhiều giao diện, nhưng cần chọn theo yêu cầu thực tế, số lượng client và tải server.

Có thể dùng exponential backoff khi request trạng thái thất bại tạm thời. Khi server trả 429 hoặc 503, client nên tôn trọng Retry-After nếu có. Không retry vô hạn hoặc đồng thời từ nhiều tab mà không có giới hạn.

## 10. Theo dõi tiến độ bằng Server-Sent Events

SSE cho phép server gửi sự kiện một chiều qua kết nối HTTP đang mở. Nó phù hợp khi browser chỉ cần nhận tiến độ từ server, còn lệnh tạo/hủy vẫn dùng HTTP thông thường.

Ví dụ event stream:

~~~text
event: job-progress
id: 18
data: {"jobId":"8b1e4f5a","status":"RUNNING","percent":42}

event: job-progress
id: 19
data: {"jobId":"8b1e4f5a","status":"RUNNING","percent":58}

event: job-completed
id: 20
data: {"jobId":"8b1e4f5a","status":"SUCCEEDED","resultUrl":"/api/jobs/8b1e4f5a/result"}
~~~

Trình duyệt có thể sử dụng EventSource:

~~~javascript
const source = new EventSource(
    "/api/jobs/" + encodeURIComponent(jobId) + "/events"
);

source.addEventListener("job-progress", (event) => {
    renderJob(JSON.parse(event.data));
});

source.addEventListener("job-completed", (event) => {
    renderJob(JSON.parse(event.data));
    source.close();
});

source.addEventListener("job-failed", (event) => {
    renderJob(JSON.parse(event.data));
    source.close();
});
~~~

EventSource tự hỗ trợ reconnect theo cơ chế của trình duyệt và có thể gửi Last-Event-ID khi kết nối lại. Server cần quyết định có lưu event history để phát lại hay chỉ gửi snapshot hiện tại. Nếu chỉ lưu trạng thái mới nhất, client có thể lấy lại job resource sau khi reconnect.

SSE là kênh một chiều. Nếu client cần gửi lệnh, dùng endpoint HTTP riêng. EventSource gốc cũng có giới hạn về cách thiết lập header tùy chỉnh; với token trong Authorization header, cần chọn giải pháp xác thực tương thích hoặc dùng cookie an toàn và bảo vệ CSRF cho endpoint thay đổi trạng thái.

## 11. Theo dõi bằng WebSocket

WebSocket cung cấp kênh hai chiều giữa browser và server. Nó phù hợp khi ứng dụng cần tương tác liên tục theo thời gian thực, chẳng hạn nhiều loại lệnh, phản hồi và cập nhật từ server.

Tuy nhiên, WebSocket phức tạp hơn polling hoặc SSE:
- Cần quản lý kết nối, heartbeat và reconnect.
- Cần xác thực khi kết nối và phân quyền từng subscription.
- Cần giới hạn số kết nối và tốc độ message.
- Cần xử lý khi client mất mạng hoặc mở nhiều tab.
- Cần định nghĩa thứ tự, trùng lặp và khôi phục event.
- Không nên gửi mọi thay đổi nội bộ cho mọi client.

Nếu chỉ cần server đẩy phần trăm tiến độ một chiều, SSE thường đơn giản hơn. Nếu ứng dụng đã dùng WebSocket cho cộng tác trực tiếp hoặc hai chiều, có thể dùng chung hạ tầng với topic/job subscription được kiểm soát quyền.

### 11.1. Chọn kênh phù hợp

| Cơ chế | Hướng dữ liệu | Độ phức tạp | Khi phù hợp |
|---|---|---|---|
| Polling | Client hỏi server định kỳ | Thấp | Job ít, tiến độ không cần tức thời |
| SSE | Server đẩy một chiều | Trung bình | Cập nhật trạng thái/tiến độ liên tục |
| WebSocket | Hai chiều | Cao hơn | Tương tác thời gian thực hai chiều |
| MVC async response | Một response được hoàn tất sau | Trung bình | Request ngắn hơn nhưng không cần job bền vững |

Không có một cơ chế luôn tốt nhất. Chọn dựa trên số client, tần suất cập nhật, yêu cầu latency, hạ tầng proxy, bảo mật và khả năng vận hành.

## 12. Hủy tác vụ và trạng thái kết thúc

Hủy job thường là một yêu cầu hợp tác (cooperative cancellation), không phải cưỡng bức dừng thread. Worker kiểm tra cờ hủy ở các điểm an toàn, chẳng hạn giữa các batch hoặc trước một tác dụng phụ.

Luồng có thể là:

1. Client gọi POST /api/jobs/{id}/cancel.
2. Controller xác minh người dùng có quyền hủy job.
3. Application service chuyển trạng thái sang CANCEL_REQUESTED nếu job còn có thể hủy.
4. Worker kiểm tra yêu cầu hủy.
5. Worker dừng tại điểm an toàn và lưu CANCELLED.
6. Client đọc trạng thái cuối.

Không nên gọi Thread.stop hoặc cưỡng bức ngắt thread theo cách có thể để dữ liệu ở trạng thái dở dang. Nếu worker đang gọi dịch vụ ngoài, hủy cục bộ không thể đảm bảo đối tác đã hủy thao tác. Cần thiết kế timeout, cancellation token hoặc API hủy của dịch vụ phụ thuộc nếu có.

Một job có thể không hủy được sau khi đã commit một bước không thể đảo ngược. Hợp đồng nên cho biết trạng thái nào có thể hủy và cách xử lý phần đã hoàn tất, ví dụ cleanup hoặc compensation.

## 13. Retry, idempotency và xử lý lỗi worker

Worker có thể thất bại do timeout, database tạm thời không sẵn sàng, broker redelivery hoặc tiến trình bị dừng. Không phải lỗi nào cũng nên retry.

| Loại lỗi | Chính sách thường gặp |
|---|---|
| Lỗi mạng tạm thời, timeout | Có thể retry có giới hạn |
| Database tạm thời unavailable | Retry với backoff và jitter |
| Dữ liệu đầu vào không hợp lệ | Không retry tự động |
| Không có quyền hoặc tài nguyên bị xóa | Thường kết thúc FAILED |
| Xung đột version | Tùy use case; có thể tải lại và thử lại có kiểm soát |
| Lỗi lập trình không dự kiến | Ghi nhận, cảnh báo; tránh retry vô hạn |

Retry nên có:
- Số lần thử tối đa.
- Exponential backoff và jitter.
- Phân biệt lỗi retryable và non-retryable.
- Dead-letter queue hoặc trạng thái cần can thiệp nếu vượt giới hạn.
- Log và metric theo job type.
- Cơ chế tránh tác dụng phụ lặp lại.

### 13.1. Idempotency

Một message có thể được giao nhiều lần. Worker có thể xử lý xong nhưng chết trước khi ack message; broker gửi lại và job được nhận lần nữa. Vì vậy, không nên giả định mỗi job chỉ chạy đúng một lần.

Thiết kế idempotent có thể dùng:
- Job ID hoặc operation key duy nhất.
- Trạng thái claim có điều kiện.
- Unique constraint cho kết quả chỉ được tạo một lần.
- Bảng ghi nhận event/step đã xử lý.
- API đối tác hỗ trợ idempotency key.
- Ghi kết quả và trạng thái hoàn tất trong cùng transaction khi có thể.

Nếu job tạo file, có thể ghi file vào đường dẫn tạm gắn với job ID rồi publish result_ref khi hoàn tất. Worker retry phải biết file tạm đã tồn tại có thể được tái sử dụng hoặc ghi đè an toàn hay không.

### 13.2. Không retry mọi exception

Retry lỗi validation, quyền truy cập hoặc dữ liệu không tồn tại thường không giúp ích. Nó chỉ tăng tải và kéo dài thời gian thất bại. Phân loại lỗi ở application/adapter layer và lưu error_code ổn định để client hiểu kết quả.

Không đưa exception message nội bộ vào job status. Có thể lưu error_code và một thông báo an toàn; chi tiết kỹ thuật được ghi log với job ID và trace ID.

## 14. Transaction trong tác vụ nền

Worker thường cần transaction riêng cho từng bước hoặc từng batch. Không nên mở một transaction database duy nhất kéo dài nhiều phút nếu job có thể chia thành các phần độc lập.

Một cách tổ chức:
- Transaction ngắn để claim job.
- Xử lý batch với transaction ngắn phù hợp.
- Transaction để ghi progress hoặc checkpoint.
- Transaction cuối để lưu result reference và trạng thái SUCCEEDED.

Nếu toàn bộ tác vụ phải nguyên tử, có thể cần một transaction lớn, nhưng phải đánh giá thời gian giữ lock, dung lượng undo log và khả năng timeout. Với quy trình dài qua nhiều hệ thống, saga hoặc trạng thái trung gian thường phù hợp hơn.

Không nên giả định transaction của request tạo job tự truyền sang worker. Worker chạy trên thread/process khác nên cần mở transaction riêng. Nếu enqueue message trong cùng request, hãy xử lý khoảng trống giữa database commit và publish bằng outbox hoặc cơ chế nhất quán tương đương.

## 15. Bảo mật job và kết quả

Job ID không phải bí mật hoặc bằng chứng quyền truy cập. Nếu người dùng biết ID của job khác, server vẫn phải kiểm tra quyền.

Các kiểm soát cần có:

- Gắn owner hoặc tenant vào job record.
- Khi GET status, cancel hoặc download result, kiểm tra quyền trên job.
- Không tin ownerId, tenantId hoặc job status do client gửi.
- Worker tải dữ liệu theo quyền và phạm vi đã được xác định ở server.
- File kết quả cần kiểm soát quyền và thời hạn link tải.
- Không đặt thông tin nhạy cảm trong event stream công khai.
- Giới hạn kích thước request, số job và số job chạy đồng thời trên mỗi người dùng.
- Không cho phép client chọn job type tùy ý hoặc truyền lệnh worker tự do.
- Ghi audit cho thao tác tạo, hủy, retry và tải kết quả khi cần.

Nếu dùng signed URL cho file kết quả, URL cần có thời hạn ngắn và phạm vi đối tượng cụ thể. Không ghi URL có token vào log công khai hoặc thông báo có thể chia sẻ ngoài ý muốn.

### 15.1. Job nhiều tenant

Với ứng dụng multi-tenant, queue message thường chỉ mang job ID. Worker đọc job record rồi lấy tenant context từ dữ liệu do server lưu. Không lấy tenant từ header hoặc payload message không đáng tin mà không xác minh.

Khi query dữ liệu nghiệp vụ, mọi truy vấn phải được giới hạn theo tenant và quyền đã gắn với job. Cần kiểm tra job vẫn được phép chạy nếu membership hoặc quyền người dùng thay đổi trong thời gian chờ.

## 16. View hiển thị tiến độ dễ hiểu và dễ tiếp cận

View nên biểu diễn status và progress rõ ràng:
- QUEUED: “Đang chờ xử lý”.
- RUNNING: “Đang tạo báo cáo”.
- SUCCEEDED: “Đã hoàn tất”, kèm liên kết tải.
- FAILED: “Không thể hoàn tất”, kèm mã tham chiếu hoặc hướng dẫn.
- CANCEL_REQUESTED: “Đang dừng công việc”.
- CANCELLED: “Đã hủy”.

Nếu có progress phần trăm, dùng progress element hoặc thanh tiến độ có ngữ nghĩa:

~~~html
<label for="job-progress">Tiến độ xuất báo cáo</label>
<progress id="job-progress" value="42" max="100">
    42%
</progress>
<p id="job-status" role="status" aria-live="polite">
    Đang xử lý dữ liệu
</p>
~~~

Không chỉ dùng màu sắc để phân biệt thành công, lỗi hoặc đang chạy. Thông báo trạng thái nên được cập nhật cho công nghệ hỗ trợ nhưng không phát thông báo quá thường xuyên. Nếu tiến độ cập nhật liên tục, có thể chỉ thông báo khi giai đoạn hoặc trạng thái thay đổi, thay vì đọc từng phần trăm.

Khi job hoàn tất, giữ liên kết kết quả hiển thị rõ và cho phép người dùng tải lại nếu cần. Nếu job thất bại, cung cấp cách thử lại khi lỗi có thể phục hồi, nhưng phải tạo thao tác retry có kiểm soát ở server.

## 17. Giới hạn tải và backpressure

Tác vụ nền có thể làm cạn CPU, RAM, disk, connection pool hoặc quota của dịch vụ bên ngoài. Queue giúp tách tốc độ tiếp nhận khỏi tốc độ xử lý, nhưng queue không thể tăng năng lực xử lý vô hạn.

Cần quản lý:
- Số worker và concurrency theo loại job.
- Dung lượng queue và ngưỡng từ chối.
- Giới hạn job đang chạy theo user/tenant.
- Giới hạn kích thước file và tổng dữ liệu đầu vào.
- Timeout cho mỗi bước và toàn job.
- Rate limit cho API tạo job.
- Ưu tiên và fairness giữa các loại công việc.
- Metric queue depth, wait time, run time, failure rate và retry count.

Nếu queue tăng liên tục, đó là dấu hiệu tốc độ tiếp nhận lớn hơn tốc độ xử lý. Cần áp dụng backpressure, giảm tải hoặc tăng worker có kiểm soát. Không nên chỉ tăng queue capacity vì điều đó có thể làm thời gian chờ kéo dài và tiêu thụ bộ nhớ.

## 18. Kiểm thử tác vụ bất đồng bộ

Kiểm thử cần bao phủ cả request tiếp nhận, worker, trạng thái, kênh tiến độ và tình huống lỗi.

| Phạm vi | Điều cần xác minh |
|---|---|
| Controller | Trả 202, job ID và status URL khi tiếp nhận thành công |
| Application service | Quyền tạo job, validation và tạo metadata đúng |
| Dispatcher/queue | Job không mất giữa commit và enqueue |
| Worker | Claim job, xử lý, cập nhật tiến độ và trạng thái cuối |
| Retry | Lỗi tạm thời retry có giới hạn; lỗi vĩnh viễn không retry |
| Cancellation | Hủy được ở điểm an toàn; trạng thái cuối chính xác |
| Authorization | Người dùng không đọc, hủy hoặc tải job của người khác |
| Progress transport | Polling/SSE/WebSocket gửi đúng trạng thái và reconnect |
| Persistence | Restart không làm mất job đã được lưu bền vững |
| Load | Queue và executor có giới hạn; hệ thống từ chối khi quá tải |

Các kịch bản quan trọng:

1. Tạo job thành công trả 202 và Location/status URL.
2. Client truy vấn job khi QUEUED rồi RUNNING và cuối cùng SUCCEEDED.
3. Worker chết giữa batch; job được phục hồi hoặc retry mà không tạo kết quả trùng.
4. Người dùng hủy job khi đang chạy; worker dừng ở điểm an toàn.
5. Job thất bại do dữ liệu sai không bị retry vô hạn.
6. Job thuộc tenant A không thể được tenant B đọc hoặc tải kết quả.
7. Server restart khi job đang QUEUED; worker khác có thể tiếp nhận lại.
8. Queue đầy; API từ chối tiếp nhận rõ ràng thay vì trả thành công giả.
9. SSE reconnect hoặc polling tiếp tục hiển thị trạng thái mới nhất.
10. Job hoàn tất nhưng client đã đóng trình duyệt; kết quả vẫn truy xuất được theo quyền.

Không nên viết test dựa trên sleep cố định rồi giả định worker đã hoàn thành. Dùng latch, awaitility, test queue hoặc cơ chế đồng bộ kiểm thử để chờ điều kiện trạng thái cụ thể với timeout có giới hạn.

## 19. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Giữ HTTP request mở cho job nhiều phút | Timeout và chiếm thread | Trả 202 và tạo job resource |
| Dùng thread mới cho mỗi request | Quá nhiều thread và thiếu giới hạn | Dùng bounded executor hoặc worker pool |
| Chỉ giữ tiến độ trong biến RAM | Mất trạng thái khi restart | Lưu job metadata và checkpoint bền vững |
| Trả 202 trước khi job được lưu/enqueue an toàn | Client theo dõi job không tồn tại hoặc bị bỏ quên | Dùng transaction/outbox hoặc cơ chế phục hồi |
| Coi message chỉ giao một lần | Tác dụng phụ trùng khi redelivery | Thiết kế worker idempotent |
| Retry vô hạn | Queue nghẽn và lặp lỗi | Phân loại lỗi, giới hạn retry, backoff |
| Hủy bằng cách dừng thread cưỡng bức | Dữ liệu có thể dở dang | Cooperative cancellation |
| Dùng @Async như queue bền vững | Job chờ có thể mất khi restart | Lưu job và dùng queue/dispatcher phục hồi |
| Cho phép xem job chỉ dựa vào ID | Lộ trạng thái hoặc file của người khác | Kiểm tra owner/tenant ở mọi endpoint |
| Cập nhật progress quá thường xuyên | Tăng tải database và event channel | Gom batch/throttle cập nhật |
| Queue không có giới hạn | Bộ nhớ và thời gian chờ tăng không kiểm soát | Backpressure, quota và capacity |
| Dùng một transaction kéo dài toàn job | Giữ connection/lock lâu | Transaction ngắn theo batch hoặc saga |

## 20. Quy trình thiết kế một tác vụ nền trong MVC

Khi thêm một chức năng chạy lâu, hãy xác định:

1. Công việc có thực sự cần bất đồng bộ không, hay có thể tối ưu truy vấn/thuật toán?
2. Request nào tạo job và hợp đồng HTTP trả 202 ra sao?
3. Job resource chứa status, progress, result và error code nào?
4. Ai sở hữu job và ai được phép đọc, hủy hoặc tải kết quả?
5. Job metadata và queue được lưu thế nào để tránh mất công việc?
6. Worker claim job và cập nhật trạng thái bằng cơ chế nào?
7. Tiến độ đo theo đơn vị nào; có cần phần trăm hay chỉ giai đoạn?
8. Client theo dõi bằng polling, SSE hay WebSocket?
9. Retry, idempotency và cancellation được định nghĩa ra sao?
10. Transaction nào ngắn và độc lập; có tác dụng phụ ngoài database nào?
11. Queue, executor, rate limit và quota có giới hạn không?
12. Kiểm thử restart, lỗi, hủy, quyền và tải như thế nào?

Bắt đầu với mô hình đơn giản nhất đáp ứng yêu cầu. Polling và job table có thể đủ cho nhiều ứng dụng. Khi cần đẩy cập nhật tức thời, bổ sung SSE. Khi có yêu cầu phân phối qua nhiều dịch vụ, queue bền vững và outbox có thể cần thiết. Không nên thêm broker, WebSocket hoặc workflow engine nếu chưa có nhu cầu vận hành rõ.

## 21. Những điểm cần ghi nhớ

Tác vụ bất đồng bộ giúp request MVC trả response sớm và chuyển công việc dài sang worker. Với job độc lập request, API thường trả 202 Accepted cùng job ID và URL trạng thái. Client đọc trạng thái bằng polling hoặc nhận cập nhật qua SSE/WebSocket; View trình bày status, tiến độ, lỗi và kết quả.

Một background job cần vòng đời rõ, trạng thái bền vững, quyền sở hữu, retry có giới hạn, idempotency và hủy hợp tác. @Async và TaskExecutor hữu ích cho tác vụ trong ứng dụng nhưng không tự cung cấp queue bền vững hay khả năng phục hồi sau restart. Không truyền request object sang worker; hãy dùng command immutable và transaction riêng.

Hãy phối hợp lưu job với enqueue bằng outbox hoặc cơ chế phục hồi, giới hạn executor/queue để tạo backpressure và kiểm tra quyền ở mọi endpoint status/cancel/result. Tiến độ cần phản ánh công việc thật, không cập nhật quá dày và phải dễ hiểu với cả người dùng bàn phím lẫn công nghệ hỗ trợ.

Khi vòng đời job và hợp đồng phản hồi được thiết kế rõ, MVC có thể tiếp nhận công việc dài mà không giữ request mở, đồng thời cho người dùng biết công việc đang ở đâu, đã hoàn tất hay cần hành động tiếp theo.
