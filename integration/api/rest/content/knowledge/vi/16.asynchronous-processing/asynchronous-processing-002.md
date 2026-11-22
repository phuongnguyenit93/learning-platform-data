# 202 Accepted và thông tin theo dõi công việc

## 1. Khi REST API không thể hoàn tất ngay trong một request

Ứng dụng quản lý báo cáo nhận yêu cầu **xuất dữ liệu sáu tháng**. Công việc cần truy vấn nhiều bảng, tổng hợp và tạo tệp, mất khoảng vài chục giây đến vài phút. Nếu giữ HTTP connection cho tới khi xử lý xong, request có thể hết hạn ở browser, API gateway hoặc load balancer dù công việc vẫn đang chạy.

Thiết kế bất đồng bộ tách **việc chấp nhận yêu cầu** khỏi **việc hoàn tất nghiệp vụ**:

1. Client gửi **POST /report-jobs** với tham số báo cáo.
2. Server kiểm tra quyền, dữ liệu đầu vào và **ghi nhận công việc có thể theo dõi**.
3. Server trả **202 Accepted**, cùng thông tin để client theo dõi.
4. Worker xử lý trong nền, cập nhật trạng thái và tạo kết quả.
5. Client **GET /report-jobs/{id}** để xem tiến độ, kết quả hoặc lỗi cuối.

**Điểm cốt lõi:** **202 Accepted không nói công việc đã thành công**. Nó chỉ thông báo rằng yêu cầu đã được chấp nhận để xử lý, nhưng việc xử lý **chưa hoàn tất**. Công việc sau đó có thể thành công, thất bại hoặc không được thực hiện. Một phản hồi 202 không phải cam kết giao dịch đã commit hoặc tài nguyên kết quả đã tồn tại.

Trong module **INTEGRATION_API_REST**, bài học này tập trung vào ngữ nghĩa HTTP, thiết kế resource/URI và contract theo dõi công việc, cách triển khai đáng tin cậy bằng Java/Spring và kiểm thử hành vi bất đồng bộ; không mở rộng sang hướng dẫn vận hành message broker toàn diện.

### Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **202 Accepted**, **200 OK**, **201 Created** và **303 See Other** trong luồng công việc dài.
- Thiết kế **status monitor resource** có URI ổn định, trạng thái, link kết quả và thời gian hết hạn.
- Hiểu ý nghĩa/giới hạn của **Location**, **Retry-After** và **Cache-Control** khi polling.
- Phân biệt lỗi **khi tiếp nhận request** với lỗi **xảy ra sau khi công việc đã được chấp nhận**.
- Tổ chức xử lý nền bằng Spring với kho trạng thái bền vững, worker và chuyển trạng thái an toàn.
- Kiểm thử response 202, quá trình chuyển trạng thái, retry, phân quyền và tình huống worker lỗi.

## 2. Ngữ nghĩa HTTP của 202 Accepted

### 2.1. Phương thức, status và thời điểm hoàn tất

Theo **RFC 9110, mục 15.3.3**, **202 Accepted** cho biết request đã được chấp nhận để xử lý nhưng xử lý **chưa hoàn tất**; cuối cùng nó có thể được hoặc không được thực hiện. Đây là status **noncommittal**: HTTP không có cơ chế chuẩn để sau đó tự gửi một status code mới nhằm “hoàn tất” response 202 đã trả.

Vì vậy, thiết kế API cần cung cấp **cách hỏi trạng thái về sau** thay vì yêu cầu client hiểu 202 là thành công cuối.

| Tình huống | Status phù hợp thường gặp | Ý nghĩa |
|---|---|---|
| GET trạng thái một job và trả JSON mô tả job | **200 OK** | Truy xuất resource trạng thái thành công, dù job còn chạy hay đã thất bại |
| POST tạo resource và **đã hoàn tất tạo** | **201 Created** | Resource mới đã được tạo theo ngữ nghĩa request |
| POST yêu cầu xử lý dài, **chưa hoàn tất** | **202 Accepted** | Yêu cầu được tiếp nhận để xử lý sau |
| GET status monitor thành công, client được chuyển tới kết quả đã tạo | **303 See Other** nếu API lựa chọn redirect | Client theo Location bằng GET để lấy kết quả |
| Request không hợp lệ hoặc không được phép | **4xx phù hợp** | Không nên trả 202 nếu chưa chấp nhận request |
| Không thể tiếp nhận yêu cầu vì hệ thống hiện không sẵn sàng | **503 Service Unavailable** hoặc mã khác đúng nguyên nhân | Không tuyên bố đã nhận nếu không thể bảo đảm theo contract |

**Không dùng 202 để “né” validation hoặc authorization.** Các lỗi xác định được trước khi chấp nhận, như thiếu quyền, payload sai định dạng, cấu hình báo cáo không hợp lệ, nên được phản hồi ngay bằng mã HTTP thích hợp.

### 2.2. 202 thường xuất hiện với phương thức nào?

Với ví dụ xuất báo cáo, **POST /report-jobs** là lựa chọn tự nhiên: client yêu cầu tạo một job mới. Một API khác có thể dùng **PUT/PATCH/DELETE** với 202 khi tác động được tiếp nhận nhưng chưa hoàn tất, tùy contract của resource. **202 không phải một phương thức HTTP**, và không thay đổi ngữ nghĩa safe/idempotent của phương thức đã dùng.

Ví dụ:

~~~http
POST /report-jobs HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Content-Type: application/json
Accept: application/json

{
  "type": "sales-summary",
  "from": "2026-01-01",
  "to": "2026-06-30"
}
~~~

Một response 202 có thể là:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
Location: /report-jobs/job-8f27
Cache-Control: no-store
Retry-After: 3

{
  "id": "job-8f27",
  "state": "QUEUED",
  "statusUrl": "/report-jobs/job-8f27",
  "submittedAt": "2026-11-18T09:30:00Z"
}
~~~

Đây là **hợp đồng API minh họa**. HTTP không bắt buộc 202 phải có **Location** hay **Retry-After**. RFC 9110 khuyến nghị representation của response 202 mô tả trạng thái hiện tại và trỏ tới hoặc nhúng **status monitor**; **Location trỏ tới monitor** là một quy ước thiết kế hữu ích nhưng cần được tài liệu hóa rõ.

### 2.3. Không nhầm tiếp nhận với hoàn thành

~~~mermaid
sequenceDiagram
    participant C as Client
    participant API as REST API
    participant DB as Job Store
    participant W as Worker
    C->>API: POST /report-jobs
    API->>DB: Ghi job QUEUED bền vững
    DB-->>API: Commit
    API-->>C: 202 + Location: /report-jobs/j-1
    W->>DB: Claim job, state=RUNNING
    C->>API: GET /report-jobs/j-1
    API-->>C: 200 {state: RUNNING}
    W->>DB: Lưu kết quả và state=SUCCEEDED
    C->>API: GET /report-jobs/j-1
    API-->>C: 200 {state: SUCCEEDED, resultUrl: ...}
    C->>API: GET /reports/r-1
    API-->>C: 200 + dữ liệu báo cáo
~~~

Response **GET status monitor** có thể mang mã **200** ngay cả khi job là **RUNNING** hoặc **FAILED**. 200 lúc đó nghĩa là **đọc được thông tin trạng thái**, không phải “job thành công”.

## 3. Thiết kế status monitor như một tài nguyên REST

### 3.1. URI và cấu trúc tài nguyên

Trong ví dụ:

- **POST /report-jobs**: tiếp nhận yêu cầu tạo job xuất báo cáo.
- **GET /report-jobs/{jobId}**: đọc trạng thái một job.
- **GET /reports/{reportId}**: đọc sản phẩm kết quả sau khi xuất xong.
- **DELETE /report-jobs/{jobId}**: *nếu được API hỗ trợ*, yêu cầu hủy hoặc xóa job theo hợp đồng cụ thể.

Không nên bắt client biết địa chỉ broker, tên topic, worker instance hoặc khóa nội bộ của hàng đợi. **Job ID/URI là hợp đồng HTTP**; worker là chi tiết triển khai.

Ví dụ monitor đang chạy:

~~~http
GET /report-jobs/job-8f27 HTTP/1.1
Authorization: Bearer <access-token>
Accept: application/json

HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "id": "job-8f27",
  "state": "RUNNING",
  "submittedAt": "2026-11-18T09:30:00Z",
  "startedAt": "2026-11-18T09:30:04Z",
  "completedAt": null,
  "resultUrl": null,
  "failure": null
}
~~~

Ví dụ monitor hoàn tất:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "id": "job-8f27",
  "state": "SUCCEEDED",
  "submittedAt": "2026-11-18T09:30:00Z",
  "startedAt": "2026-11-18T09:30:04Z",
  "completedAt": "2026-11-18T09:32:19Z",
  "resultUrl": "/reports/r-991",
  "failure": null
}
~~~

**resultUrl** chỉ xuất hiện khi kết quả đã sẵn sàng và người dùng có quyền truy cập. Không trả signed download URL dài hạn trong log hoặc payload nếu ứng dụng cần phát URL tạm thời tại thời điểm download.

### 3.2. Vòng đời job

Một state machine nhỏ, đủ cho nhiều bài toán:

~~~mermaid
stateDiagram-v2
    [*] --> QUEUED: POST được chấp nhận
    QUEUED --> RUNNING: Worker claim job
    RUNNING --> SUCCEEDED: Kết quả hoàn tất
    RUNNING --> FAILED: Xử lý thất bại
    QUEUED --> CANCELLED: Hủy trước khi chạy
    RUNNING --> CANCELLATION_REQUESTED: Yêu cầu hủy
    CANCELLATION_REQUESTED --> CANCELLED: Worker dừng an toàn
    CANCELLATION_REQUESTED --> SUCCEEDED: Đã hoàn tất trước khi hủy
    CANCELLATION_REQUESTED --> FAILED: Xử lý vẫn lỗi
~~~

**QUEUED** và **RUNNING** là trạng thái chưa hoàn tất; **SUCCEEDED**, **FAILED** và **CANCELLED** là trạng thái cuối theo ví dụ. **CANCELLATION_REQUESTED** không khẳng định đã hủy thành công. Những ứng dụng không hỗ trợ hủy có thể bỏ trạng thái và endpoint hủy.

| State | Client nên hiểu | Thông tin tối thiểu |
|---|---|---|
| QUEUED | Đã nhận, đang chờ xử lý | id, submittedAt, status URL |
| RUNNING | Đang xử lý | id, startedAt; progress nếu có giá trị |
| SUCCEEDED | Đã hoàn thành | completedAt, result URL/ID |
| FAILED | Không hoàn thành | completedAt, mã lỗi an toàn và hướng xử lý |
| CANCELLATION_REQUESTED | Hệ thống đang cố hủy | Thời điểm và trạng thái hiện tại |
| CANCELLED | Đã hủy theo quy tắc nghiệp vụ | completedAt, không giả vờ có kết quả |

**Progress** như 65% chỉ nên xuất hiện khi có cách tính đáng tin cậy; nếu không, trả state và thời gian là đủ. Không tự tăng phần trăm theo thời gian rồi tạo kỳ vọng hoàn thành sai.

### 3.3. Kết quả lỗi nằm ở trạng thái công việc

Một job có thể thất bại **sau** khi request POST đã nhận 202. Không thể quay lại thay status của POST thành 500. Client truy vấn monitor:

~~~http
GET /report-jobs/job-8f27 HTTP/1.1

HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "id": "job-8f27",
  "state": "FAILED",
  "completedAt": "2026-11-18T09:31:20Z",
  "resultUrl": null,
  "failure": {
    "code": "SOURCE_UNAVAILABLE",
    "message": "Nguồn dữ liệu chưa sẵn sàng. Có thể tạo yêu cầu mới sau."
  }
}
~~~

**HTTP 200** là trạng thái của thao tác **GET /report-jobs/{id}** thành công. **FAILED** là trạng thái của **nghiệp vụ chạy nền**. Chỉ khi **không thể đọc monitor** do lỗi server, response GET mới cần một mã **5xx** phù hợp. Đừng biến mọi job FAILED thành HTTP 500 ở endpoint GET monitor và khiến HTTP client cache/retry/error handler hiểu sai.

Nếu lỗi xảy ra **ngay ở bước POST**, trước khi công việc được tiếp nhận, dùng 400/401/403/409/422/429/503... tùy ngữ nghĩa, có thể kèm **application/problem+json** (RFC 9457). Cấu trúc **failure trong job** ở trên là một hợp đồng dữ liệu ứng dụng, không mặc định là một response Problem Details top-level.

## 4. Location, Retry-After, Content-Location và cách polling

### 4.1. Location nên trỏ đến đâu?

Với quy ước trong bài, response **202** đặt:

~~~http
Location: /report-jobs/job-8f27
~~~

để client biết **monitor URI**. Tuy nhiên, **Location trong 202 không được RFC định nghĩa là “bắt buộc trỏ tới job monitor”**. Hợp đồng API phải nói rõ đó là URI nào, cách xác thực và thời gian truy cập. Nếu chỉ cung cấp **statusUrl trong JSON** mà không dùng Location, client vẫn có thể hoạt động khi contract mô tả được.

**Content-Location** là header khác, dùng để định danh URI tương ứng với **representation được trả** trong những ngữ cảnh HTTP; không thay thế Location một cách máy móc. Với một API đơn giản, chỉ cần **Location + body có statusUrl** hoặc một trong hai được tài liệu hóa rõ.

### 4.2. Retry-After không tự định nghĩa giao thức polling cho 202

Ví dụ response:

~~~http
HTTP/1.1 202 Accepted
Location: /report-jobs/job-8f27
Retry-After: 3
Content-Type: application/json
~~~

Header **Retry-After** có ngữ nghĩa chuẩn rõ ràng ở một số trường hợp như **503** và các response chuyển hướng. Với **202**, việc dùng nó để gợi ý **“hãy kiểm tra trạng thái sau khoảng 3 giây”** là **quy ước của API**, không phải một quy tắc polling bắt buộc do RFC 9110 đặt riêng cho 202. Nếu chọn dùng, tài liệu phải nêu rõ ý nghĩa, đơn vị **delay-seconds** hoặc HTTP-date và fallback khi header vắng mặt.

Có thể thay bằng trường **pollAfterSeconds** trong body khi muốn tách khỏi header. Đừng yêu cầu client polling ngay lập tức sau 202, đặc biệt khi job kéo dài.

### 4.3. Thiết kế polling có giới hạn

Một client tốt:

1. Đọc monitor URI từ Location hoặc response body theo contract.
2. Chờ **đủ khoảng thời gian được khuyến nghị**, có thể thêm jitter để tránh nhiều client cùng kiểm tra một thời điểm.
3. **GET monitor** và kiểm tra cả status HTTP lẫn field **state**.
4. Dừng khi **SUCCEEDED / FAILED / CANCELLED**, hoặc khi đạt deadline phía client.
5. Với **SUCCEEDED**, theo **resultUrl** để lấy kết quả nếu được phép.
6. Với lỗi mạng/429/503, áp dụng retry/backoff có giới hạn, không đồng nhất lỗi GET monitor với lỗi job.

~~~text
POST /report-jobs
  -> 202 + monitor URL
  -> wait 3 seconds (theo contract)
  -> GET monitor -> 200 RUNNING
  -> wait theo chính sách
  -> GET monitor -> 200 SUCCEEDED
  -> GET resultUrl -> 200
~~~

Nếu có hàng nghìn client, polling dày có thể làm quá tải API. Có thể cho phép **ETag/If-None-Match trên monitor**, polling có backoff, long polling hoặc cơ chế push như webhook/SSE tùy yêu cầu; đây là **lựa chọn bổ sung**, không phải đặc tính tự có của 202.

### 4.4. Cache trạng thái job

Vì monitor thường chứa thông tin cá nhân và thay đổi liên tục, ví dụ dùng:

~~~http
Cache-Control: no-store
~~~

cho response POST 202 và GET monitor. Nếu ứng dụng có chủ đích dùng HTTP caching, phải xử lý authorization, độ mới và validators chính xác. Một monitor có state **RUNNING** bị cache lâu có thể khiến client không thấy **SUCCEEDED**; một monitor của tenant A bị cache dùng chung cho B còn là lỗi phân quyền.

## 5. Tài nguyên kết quả, redirect và vòng đời giữ trạng thái

### 5.1. Hoàn tất công việc không nhất thiết có cùng URI

**/report-jobs/job-8f27** mô tả **tiến trình**. **/reports/r-991** mô tả **kết quả**. Tách hai resource giúp:

- Job có vòng đời queued/running/failed/cancelled.
- Kết quả có quyền truy cập, thời hạn lưu và cache policy riêng.
- Client có thể theo dõi lỗi mà không cần biết lưu trữ nội bộ.

Trong một số API, kết quả đủ nhỏ để nhúng vào monitor ở trạng thái SUCCEEDED. Khi tệp hoặc dữ liệu lớn, **resultUrl** rõ ràng hơn.

### 5.2. Có nên dùng 303 See Other?

Khi job đã **SUCCEEDED**, API có thể chọn một trong hai contract:

**Phương án A — giữ GET monitor luôn 200:**

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":"job-8f27","state":"SUCCEEDED","resultUrl":"/reports/r-991"}
~~~

**Phương án B — tùy chọn redirect tới resource kết quả:**

~~~http
HTTP/1.1 303 See Other
Location: /reports/r-991
~~~

**303** hướng client tới URI khác bằng **GET**, phù hợp khi muốn định hướng sang kết quả. Tuy nhiên, nếu endpoint luôn redirect khi hoàn thành, client muốn đọc metadata cuối của job cần cách khác. Không được trả 303 khi chưa có result resource hợp lệ hoặc để lộ URI kết quả trước khi kiểm tra quyền. Với bài học và ví dụ Spring dưới đây, chọn **phương án A** để monitor thống nhất schema.

### 5.3. Monitor hết hạn và 404/410

Không nên giữ trạng thái mọi job vô hạn. Hợp đồng cần ghi rõ:

- Job được theo dõi tối thiểu bao lâu sau khi hoàn thành.
- Kết quả được giữ bao lâu và download có thể hết hạn độc lập ra sao.
- Với ID **không tồn tại hoặc không được phép công bố**, trả **404** là lựa chọn phổ biến.
- Với job **đã từng tồn tại và đã bị xóa vĩnh viễn**, server **có thể** trả **410 Gone** nếu có khả năng xác nhận và muốn thông báo; không bắt buộc mọi job hết hạn phải trả 410.

API không nên lộ lịch sử job của tenant khác chỉ qua việc phân biệt 404 với 410.

### 5.4. Hủy công việc không phải rollback mọi tác dụng phụ

Nếu API hỗ trợ **DELETE /report-jobs/{id}** để yêu cầu hủy:

- **202** có thể phù hợp nếu đã nhận lệnh hủy nhưng worker chưa dừng.
- **204** có thể phù hợp khi thao tác đã hoàn tất và không trả body.
- **409** có thể phù hợp khi job đã ở trạng thái không thể hủy.

Từng lựa chọn phải được định nghĩa trong hợp đồng. **CANCELLED** không nhất thiết có nghĩa đã hoàn tác email gửi đi, file đã xuất bản hoặc khoản thanh toán đã thực hiện. Những tác dụng phụ không thể đảo ngược cần quy tắc nghiệp vụ riêng. Trong một hệ thống không hỗ trợ hủy, đừng công bố DELETE chỉ vì job có URI.

## 6. Điều kiện để trả 202 một cách đáng tin cậy

### 6.1. “Đã nhận” phải có bằng chứng

Nếu controller gọi một hàm **@Async** chạy trong bộ nhớ rồi lập tức trả 202, tiến trình có thể chết trước khi worker kịp thực hiện. Client vẫn giữ monitor URL nhưng server đã mất thông tin về job. Đây là khoảng trống giữa **HTTP acceptance** và **độ bền trạng thái**.

Một contract đáng tin cậy nên quy định: **chỉ trả 202 sau khi đã commit một bản ghi job hoặc ghi bền vững yêu cầu vào một hệ thống tiếp nhận được bảo đảm phù hợp**. Tùy hệ thống, có thể dùng:

- **Database-backed job queue:** tạo row job ở trạng thái QUEUED, commit rồi worker lấy ra.
- **Durable message broker:** bảo đảm broker đã tiếp nhận theo cơ chế acknowledgement phù hợp, đồng thời có kho monitor tra cứu được.
- **Transactional outbox:** ghi job/outbox cùng transaction, một tiến trình khác chuyển lệnh sang broker sau commit.

Không được tuyên bố một cách chung chung rằng **“gửi vào queue là exactly-once”**. Broker có thể giao lại message, worker có thể crash và cùng job có thể được thử lại. Cần bảo vệ side effects và trạng thái cuối.

~~~mermaid
flowchart LR
    C[Client] --> API[POST /report-jobs]
    API --> V{Validate + Authorize}
    V -->|Không hợp lệ| ERR[4xx phù hợp]
    V -->|Hợp lệ| DB[(Commit Job QUEUED)]
    DB --> ACK[202 + Monitor URI]
    DB --> W[Worker claim atomically]
    W --> RUN[Thực hiện xuất dữ liệu]
    RUN --> END[(Ghi SUCCEEDED / FAILED)]
    C --> STATUS[GET Monitor]
    STATUS --> END
~~~

Nếu DB không thể ghi job hoặc quyền/giới hạn tiếp nhận không được thỏa, server nên trả **mã lỗi tương ứng**, không trả 202 giả. Chẳng hạn **429 Too Many Requests** khi client vượt giới hạn yêu cầu, hoặc **503 Service Unavailable** khi hệ thống tạm không có khả năng tiếp nhận. Một job đã được chấp nhận vẫn có thể thất bại khi chạy; điều này cần được thể hiện qua monitor.

### 6.2. Trạng thái cần chống cập nhật sai thứ tự

Khi nhiều worker cùng quét queue, chúng không được cùng claim một job hoặc ghi kết quả của một lần chạy cũ đè lên lần chạy mới. Có thể dùng **atomic compare-and-set**, optimistic version hoặc khóa DB.

Ví dụ claim một job đã biết ID bằng SQL:

~~~sql
UPDATE report_jobs
SET state = 'RUNNING',
    started_at = CURRENT_TIMESTAMP,
    version = version + 1
WHERE id = :job_id
  AND state = 'QUEUED';
~~~

Chỉ worker nhận **affected rows = 1** được coi là đã claim thành công. Những worker khác phải bỏ qua; không được thấy job QUEUED bằng SELECT rồi mặc định mình sở hữu.

Trong production, cần cơ chế **lease/heartbeat và recovery** khi worker chết ở RUNNING. Nếu cho phép thu hồi lease, kết quả từ worker cũ phải bị từ chối bằng **attempt token/fencing token** hoặc điều kiện cập nhật tương đương. Ví dụ một cập nhật kết thúc nên kiểm tra **id + state + attempt token hiện tại**, không chỉ **id**, để tránh worker hết lease hoàn thành muộn và ghi đè kết quả của worker mới.

### 6.3. Khi nào job thực sự thành công?

Chỉ chuyển sang **SUCCEEDED** khi **kết quả đã được ghi/kiểm tra đủ để client truy xuất theo contract**. Ví dụ export file:

1. Worker tạo dữ liệu và upload file.
2. Kiểm tra kích thước/checksum và quyền truy cập.
3. Ghi thông tin result resource vào kho.
4. Chuyển job sang SUCCEEDED cùng result URL/ID phù hợp.

Nếu cập nhật job SUCCEEDED xảy ra **trước khi file có thể đọc được**, client thấy kết quả hoàn thành nhưng GET result trả 404. Nếu hai hệ thống lưu trữ không có transaction chung, cần thứ tự thao tác, cơ chế retry/reconcile và idempotent result publication để trạng thái cuối không nói sai.

## 7. Java/Spring: endpoint tiếp nhận và đọc monitor

Ví dụ chọn **Spring Boot 3 / Spring Framework 6**, REST controller và **database-backed job store**. API xuất báo cáo chỉ minh họa luồng cần thiết; các kiểu service/repository là abstraction của ứng dụng.

### 7.1. DTO và REST controller

~~~java
import java.net.URI;
import java.security.Principal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

record CreateReportRequest(
    @NotBlank String type,
    @NotNull LocalDate from,
    @NotNull LocalDate to
) {}

record JobFailure(String code, String message) {}

record ReportJobView(
    UUID id,
    String state,
    Instant submittedAt,
    Instant startedAt,
    Instant completedAt,
    String resultUrl,
    JobFailure failure
) {}

@RestController
@RequestMapping("/report-jobs")
class ReportJobController {
    private final ReportJobService service;

    ReportJobController(ReportJobService service) {
        this.service = service;
    }

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    ResponseEntity<ReportJobView> submit(
            @Valid @RequestBody CreateReportRequest request,
            Principal principal) {

        // Service kiểm tra date range, loại báo cáo, quota,
        // tenant và ghi job bền vững trước khi trả kết quả.
        ReportJobView job = service.accept(request, principal);
        URI monitor = URI.create("/report-jobs/" + job.id());

        return ResponseEntity.accepted()
            .location(monitor)
            .header(HttpHeaders.RETRY_AFTER, "3")
            .cacheControl(CacheControl.noStore())
            .body(job);
    }

    @GetMapping(
        path = "/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    ResponseEntity<ReportJobView> status(
            @PathVariable UUID id,
            Principal principal) {

        // Service chỉ trả job mà caller thực sự được xem.
        ReportJobView job = service.findVisible(id, principal);
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(job);
    }
}
~~~

**Giới hạn và giả định của ví dụ:**

- **ReportJobService** phải được triển khai; đoạn controller không đủ tạo một job chạy được.
- @Valid xử lý ràng buộc đơn giản; **from <= to**, hạn mức thời gian, loại báo cáo và quyền phải được validate tại service.
- **Principal.getName() không tự đại diện cho tenant đã xác thực**; cần lấy tenant/role theo mô hình bảo mật của ứng dụng.
- **Location và Retry-After** thể hiện quy ước của API này, không phải yêu cầu bắt buộc của 202.
- Lỗi 400/401/403/404/422/429/503 phải có error mapping đúng. Không biến mọi exception thành 202.
- Các URI ví dụ là relative URI references; khi client ở ngoài gateway, cần bảo đảm URL có thể giải quyết đúng theo base URI công khai.

### 7.2. Service: commit bản ghi trước khi trả 202

Giao diện triển khai tối thiểu:

~~~java
interface ReportJobService {
    ReportJobView accept(CreateReportRequest request, Principal caller);
    ReportJobView findVisible(UUID id, Principal caller);
}
~~~

Giả mã phần tiếp nhận:

~~~text
@Transactional
accept(request, authenticatedCaller):
    validate request and user/tenant quota
    job = new ReportJob(
        id = random UUID,
        tenantId = trusted tenant from auth,
        ownerId = trusted principal,
        state = QUEUED,
        submittedAt = now
    )
    persist job
    commit transaction
    return view(job)
~~~

Phương thức được Spring quản lý transaction sẽ **commit khi rời khỏi lời gọi service qua proxy**; chỉ sau khi service trả thành công thì controller tạo response 202. Với kiến trúc publish lên broker, dùng transaction/outbox phù hợp để tránh DB đã commit nhưng lệnh vào queue bị mất. **Không khởi chạy @Async trong transaction rồi lập tức trả response** như cách bảo đảm bền vững.

### 7.3. Worker dùng trạng thái bền vững

Ví dụ cấu trúc worker có thể triển khai như sau:

~~~java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
class ReportJobWorker {
    private final ReportJobProcessor processor;

    ReportJobWorker(ReportJobProcessor processor) {
        this.processor = processor;
    }

    @Scheduled(fixedDelayString = "${reports.worker.poll-ms:1000}")
    void poll() {
        processor.claimAndRunOne();
    }
}

// ReportJobProcessor là service giả định:
// - claim job qua atomic update/transaction ngắn;
// - xử lý bên ngoài transaction claim;
// - kết thúc với trạng thái + attempt token đúng;
// - ghi SUCCEEDED hoặc FAILED và lưu failure code an toàn;
// - có lease/recovery khi worker ngừng giữa chừng.
~~~

Đây là **skeleton**, không phải implementation production đầy đủ. Muốn chạy @Scheduled cần bật scheduling (ví dụ **@EnableScheduling** trong cấu hình), có concurrency/transaction controls và cơ chế giám sát worker. **Không giữ transaction mở trong toàn bộ thời gian xuất báo cáo** nếu có thể tách claim, xử lý và publish result an toàn.

### 7.4. Vì sao @Async chưa đủ?

~~~java
// Phản mẫu nếu hệ thống hứa lưu bền vững nhưng không có job store:
@PostMapping("/reports/export")
ResponseEntity<Void> export() {
    exportService.startInMemoryAsyncTask();
    return ResponseEntity.accepted().build();
}
~~~

Một lần restart hoặc crash có thể làm mất tác vụ. Client không có monitor URI để biết chuyện gì xảy ra. **@Async phù hợp để chạy công việc không đồng bộ trong JVM**, nhưng bản thân nó **không định nghĩa job resource, durable acceptance, retry, recovery hoặc cách client theo dõi**.

## 8. Xác thực, phân quyền và giới hạn tài nguyên theo dõi

Status monitor có thể chứa:

- Loại báo cáo, khoảng thời gian và dữ liệu lọc.
- Kết quả xuất bản hoặc link tới tệp riêng tư.
- Thông tin lỗi liên quan đến dữ liệu hoặc hệ thống.

Vì vậy, **GET /report-jobs/{id} phải thực hiện authorization mỗi lần**; không coi ID khó đoán là quyền truy cập. Ví dụ:

| Request | Hành vi đề xuất |
|---|---|
| Caller không có xác thực hợp lệ | **401 Unauthorized** theo cơ chế auth |
| Caller có quyền và job còn lưu | **200** với monitor |
| Job không tồn tại | **404 Not Found** |
| Caller không có quyền xem job tenant khác | **403**, hoặc **404** nếu chính sách che giấu sự tồn tại |
| Job đã bị xóa và server muốn thông báo rõ | **410 Gone** khi phù hợp |
| Poll vượt rate limit | **429 Too Many Requests**, có thể có Retry-After |

Job cần lưu **tenantId/ownerId hoặc phạm vi quyền đã được xác định đáng tin cậy**. Không lấy tenant từ header/query do client tự chọn rồi coi là đã phân quyền. Khi kết quả được tải qua **GET /reports/{id}**, phải kiểm tra quyền tại resource kết quả, không chỉ tại monitor.

### 8.1. Chống polling quá mức

Một API có thể giới hạn số lần GET monitor theo caller, tenant hoặc job. Khi vượt giới hạn, **429** là mã phù hợp; client đọc **Retry-After** nếu có rồi giảm tần suất. Bổ sung backoff/jitter và theo dõi tỷ lệ polling để tránh nhiều client phát request cùng nhịp gây tải đỉnh.

### 8.2. Không rò lỗi kỹ thuật vào failure

Khi worker thất bại, có thể lưu nội bộ stack trace, trace ID và sự kiện chẩn đoán theo chính sách; monitor công khai chỉ nên trả **mã lỗi ổn định, thông điệp an toàn và hành động có thể làm**. Không đưa SQL, hostname, access token, object storage credential hoặc raw exception message vào **failure.message**.

## 9. Retry khi POST bị timeout và ngữ nghĩa idempotency

Trường hợp khó nhất: server đã **commit job** và gửi 202, nhưng kết nối bị ngắt nên client không nhận được response. Nếu client gửi **POST /report-jobs** lần nữa mà API không có cơ chế nhận diện thao tác logic, nó có thể tạo **hai job xuất cùng một báo cáo**.

Nếu nghiệp vụ yêu cầu chống trùng, API có thể hỗ trợ **Idempotency-Key**:

~~~http
POST /report-jobs HTTP/1.1
Content-Type: application/json
Idempotency-Key: export-sales-2026-h1-9e31

{"type":"sales-summary","from":"2026-01-01","to":"2026-06-30"}
~~~

Các yêu cầu thiết kế chính:

| Tình huống | Hành vi cần làm rõ trong hợp đồng |
|---|---|
| Cùng key, cùng request logic, đồng thời | Không tạo hai job; trả cùng monitor hoặc trạng thái retry theo contract |
| Cùng key sau khi job đã hoàn thành | Có thể trả lại thông tin job cũ trong thời hạn lưu key |
| Cùng key, body khác | Từ chối tái sử dụng sai key; không coi là một job mới |
| Key khác nhau | Là các thao tác logic độc lập, trừ khi nghiệp vụ còn có quy tắc chống trùng khác |
| Retry sau TTL key | Không thể hứa luôn dedup; cần công bố TTL và chính sách tra cứu lịch sử |

**Key cần có phạm vi theo tenant/principal và loại thao tác**, được lưu/kiểm tra nguyên tử với việc tiếp nhận job. Không coi một **correlation ID** hoặc **job ID do server phát hành** là tự động thay thế idempotency key phía client. Đây là cơ chế riêng với 202; chỉ dùng khi hợp đồng nghiệp vụ cần.

**Phân biệt 201 và 202:** nếu request **chỉ yêu cầu tạo resource job** và resource đó đã được tạo xong, API có thể hợp lý trả **201 Created**, dù quá trình xử lý báo cáo của job còn pending. Nếu request được diễn đạt là **“thực hiện báo cáo”** và việc thực hiện mới được tiếp nhận, **202 Accepted** phù hợp. Chọn theo ngữ nghĩa **resource mà request yêu cầu**, rồi sử dụng nhất quán trong OpenAPI. Không có quy định rằng mọi thao tác tạo job dài phải luôn dùng 202.

## 10. Mô tả hợp đồng bằng OpenAPI

Ví dụ OpenAPI 3.0.3 rút gọn cho contract đã chọn **202 + monitor**:

~~~yaml
openapi: 3.0.3
info:
  title: Asynchronous Reports API
  version: 1.0.0
paths:
  /report-jobs:
    post:
      summary: Tiếp nhận yêu cầu xuất báo cáo
      description: >
        API chỉ trả 202 sau khi ghi nhận job bền vững.
        Location trỏ đến monitor URI theo hợp đồng này.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [type, from, to]
              properties:
                type: {type: string, enum: [sales-summary]}
                from: {type: string, format: date}
                to: {type: string, format: date}
      responses:
        "202":
          description: Đã chấp nhận, xử lý chưa hoàn tất
          headers:
            Location:
              description: URI tài nguyên theo dõi công việc
              schema: {type: string, format: uri-reference}
            Retry-After:
              description: >
                Quy ước API: thời gian đề nghị chờ trước lần GET monitor
              schema: {type: string}
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/JobView"
        "400": {description: Tham số không hợp lệ}
        "401": {description: Chưa xác thực}
        "403": {description: Không được phép}
        "422": {description: Yêu cầu không hợp lệ về nghiệp vụ}
        "429": {description: Vượt giới hạn tiếp nhận}
        "503": {description: Tạm thời không thể tiếp nhận}
  /report-jobs/{id}:
    get:
      summary: Xem trạng thái công việc
      parameters:
        - in: path
          name: id
          required: true
          schema: {type: string, format: uuid}
      responses:
        "200":
          description: >
            Đọc monitor thành công; state có thể là FAILED
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/JobView"
        "401": {description: Chưa xác thực}
        "403": {description: Không có quyền}
        "404": {description: Không tìm thấy hoặc không công bố job}
        "410": {description: Job đã bị xóa vĩnh viễn nếu API hỗ trợ}
        "429": {description: Polling quá nhiều}
components:
  schemas:
    JobView:
      type: object
      properties:
        id: {type: string, format: uuid}
        state:
          type: string
          enum: [QUEUED, RUNNING, SUCCEEDED, FAILED,
                 CANCELLATION_REQUESTED, CANCELLED]
        submittedAt: {type: string, format: date-time}
        startedAt: {type: string, format: date-time, nullable: true}
        completedAt: {type: string, format: date-time, nullable: true}
        resultUrl: {type: string, nullable: true}
        failure:
          nullable: true
          allOf:
            - $ref: "#/components/schemas/JobFailure"
      required: [id, state, submittedAt]
    JobFailure:
      type: object
      properties:
        code: {type: string}
        message: {type: string}
      required: [code, message]
~~~

Trong production, cần bổ sung **security schemes**, schema lỗi **application/problem+json**, header cache và các response khác theo ứng dụng. OpenAPI **không tự triển khai** durability, polling, transaction hay quyền truy cập.

## 11. Kiểm thử HTTP contract và vòng đời công việc

### 11.1. Ma trận kiểm thử trọng tâm

| ID | Điều kiện | Điều phải xác minh |
|---|---|---|
| T01 | POST hợp lệ | **202**, Location hợp lệ, body chứa id/state và job đã được ghi bền vững |
| T02 | GET monitor ngay sau 202 | **200**, đúng job và trạng thái chưa hoàn tất |
| T03 | Worker bắt đầu xử lý | GET trả **RUNNING**, không bịa result URL |
| T04 | Worker hoàn thành | GET trả **SUCCEEDED** và result URL đọc được theo quyền |
| T05 | Worker lỗi sau 202 | GET vẫn **200**, state **FAILED**, failure code an toàn |
| T06 | POST payload sai hoặc không có quyền | Trả 4xx thích hợp, **không tạo job** |
| T07 | Không thể commit job store | Không trả 202 giả; không phát sinh job mồ côi |
| T08 | Hai POST cùng Idempotency-Key | Một job logic, kết quả trùng được xử lý theo contract |
| T09 | Worker chết ở RUNNING | Có lease/recovery, không kẹt vĩnh viễn hoặc ghi đè kết quả |
| T10 | Hai worker claim cùng job | Chỉ một worker sở hữu attempt hợp lệ |
| T11 | Caller tenant khác GET monitor | 403/404 theo chính sách, không lộ thông tin |
| T12 | Client polling dày | 429 hoặc cơ chế giới hạn theo hợp đồng |
| T13 | Job đã hết thời hạn lưu | 404/410 đúng chính sách, không rò lịch sử |
| T14 | Yêu cầu hủy đúng lúc hoàn tất | Một trạng thái cuối hợp lệ, không có state chuyển lùi |
| T15 | SUCCEEDED nhưng kết quả chưa sẵn sàng | **Không chấp nhận**; chỉ thành công khi result có thể truy cập |

**Giá trị của test** nằm ở việc quan sát cả **HTTP response, bản ghi job, kết quả và side effects**, không chỉ status 202.

### 11.2. MockMvc: tạo job rồi GET monitor

Ví dụ dùng Spring Security Test cho principal giả định:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MvcResult;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@Test
void acceptedJobHasReadableMonitor() throws Exception {
    MvcResult created = mockMvc.perform(
            post("/report-jobs")
                .with(user("alice"))
                .contentType("application/json")
                .content("""
                    {
                      "type":"sales-summary",
                      "from":"2026-01-01",
                      "to":"2026-06-30"
                    }
                    """))
        .andExpect(status().isAccepted())
        .andExpect(header().exists("Location"))
        .andExpect(jsonPath("$.state").value("QUEUED"))
        .andReturn();

    String monitor = created.getResponse().getHeader("Location");

    mockMvc.perform(get(monitor).with(user("alice")))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.state").value("QUEUED"))
        .andExpect(jsonPath("$.id").exists());
}
~~~

Đây là **đoạn test minh họa**: giả định đã có MockMvc, một job store test tách biệt và worker không tự động chuyển QUEUED trước khi GET. Trong môi trường thật, có thể tắt scheduler và **điều khiển worker bằng fixture**; nếu không, assert cứng QUEUED sau 202 có thể gây test flaky vì worker đã chuyển sang RUNNING.

Đoạn test giả định class test đã khai báo **MockMvc mockMvc** được inject (chẳng hạn qua **@SpringBootTest** và **@AutoConfigureMockMvc**) cùng cấu hình security fixture. Với các controller dùng CSRF protection, test POST phải thêm token CSRF hợp lệ theo cấu hình. Nếu thiếu authentication/CSRF, test có thể trả 401/403 trước khi tới controller.

### 11.3. Kiểm thử vòng đời không phụ thuộc thời gian thực

Một test integration tốt có thể:

~~~text
Arrange:
    tạo user/tenant test có quyền
    dùng DB test thật, worker được kiểm soát qua test fixture
    tạo request hợp lệ
Act:
    POST /report-jobs
Assert:
    202, Location, job đã commit trong kho

Act:
    fixture.claim(jobId)
    GET monitor
Assert:
    200, state RUNNING

Act:
    fixture.complete(jobId, resultId)
    GET monitor
    GET resultUrl
Assert:
    200, state SUCCEEDED, kết quả đọc được

Act:
    tạo job khác, fixture.fail(jobId, "SOURCE_UNAVAILABLE")
    GET monitor
Assert:
    200, state FAILED, error không lộ stack trace
~~~

Không dùng **Thread.sleep(5000)** như cách chính để chờ worker. Hãy dùng fixture chuyển trạng thái chủ động hoặc poll với deadline/điều kiện rõ. Nếu test tự chạy scheduler, cần kiểm tra kết quả cuối thay vì giả định job chắc chắn còn QUEUED ngay sau response 202.

### 11.4. Test retry và nhiều instance

Ở mức HTTP integration:

1. Gửi hai POST **cùng key/payload** gần như đồng thời qua hai API instance dùng chung DB.
2. Kiểm tra chỉ một job được tạo cho scope/key và body phản hồi/monitor phù hợp contract.
3. Khởi động hai worker cùng claim; kiểm tra **affected rows/attempt token** và không xử lý trùng side effect.
4. Giả lập worker crash sau claim; cho lease hết hạn theo fake clock hoặc điều khiển test, xác minh reclaim an toàn.
5. Giả lập response bị mất **sau khi commit**; retry, kiểm tra không tạo job mới.

Test một service mock trong JVM thường chưa đủ kiểm chứng race về transaction, locking và durability. Nên có kiểm thử với database engine sát production; kiểm thử qua gateway riêng để xác nhận Location, HTTPS base path, auth và cache headers đúng trên tuyến thật.

## 12. Case study: xuất báo cáo bán hàng cuối tháng

Một doanh nghiệp cho phép người quản lý xuất báo cáo 12 tháng. Dữ liệu lớn và việc tạo file không thể hoàn tất trong timeout HTTP thông thường.

**Hợp đồng được chọn:**

| Hành động | HTTP | Kết quả |
|---|---|---|
| Tạo yêu cầu hợp lệ | POST /report-jobs → **202** | Monitor URI, state QUEUED |
| Xem công việc đang chạy | GET /report-jobs/j-42 → **200** | state RUNNING |
| Xem công việc hoàn thành | GET /report-jobs/j-42 → **200** | state SUCCEEDED, resultUrl |
| Tải file | GET /reports/r-42 → **200** | File kết quả nếu có quyền |
| Xem công việc thất bại | GET /report-jobs/j-43 → **200** | state FAILED, mã lỗi nghiệp vụ |
| Client khác tenant xem job | GET /report-jobs/j-42 → **404** theo chính sách che giấu | Không lộ trạng thái hoặc link file |

### Tình huống 1: DB commit job, worker chưa chạy

Server đã commit job QUEUED nhưng worker thiếu tài nguyên để bắt đầu ngay. Trả **202** vẫn nhất quán với contract: job được tiếp nhận để xử lý sau, chưa cam kết thời điểm hoàn tất. Monitor thể hiện QUEUED và client polling có giới hạn.

Nếu hàng đợi vượt khả năng tiếp nhận **trước khi tạo được job**, API nên áp dụng admission control và trả lỗi phù hợp như **429/503**, thay vì tạo vô hạn job mà không có năng lực xử lý theo chính sách.

### Tình huống 2: worker mất kết nối nguồn dữ liệu

Worker chuyển job sang **FAILED**, lưu **SOURCE_UNAVAILABLE**, timestamp và thông tin nội bộ vào log có phân quyền. GET monitor vẫn **200** với **state FAILED**; người dùng có thể gửi yêu cầu mới khi điều kiện cho phép. Client không cần diễn giải 500 của API status monitor để biết job thất bại.

### Tình huống 3: client mất response 202

POST đã tạo **j-42**, nhưng response bị mất. Client retry cùng **Idempotency-Key**. Nếu API đã thiết kế dedup, server nhận diện request cũ và trả thông tin **j-42** theo contract, không tạo **j-44**. Nếu không hỗ trợ dedup, client phải được cảnh báo rằng retry POST có thể tạo job thứ hai.

### Tình huống 4: người dùng rời trang và quay lại

Frontend có thể lưu **monitor URI/job ID** trong trạng thái ứng dụng hoặc nhận lại danh sách job của chính user qua endpoint được ủy quyền. Khi quay lại, nó GET monitor thay vì giả định job chạy cùng vòng đời của tab trình duyệt. **Không cần giữ HTTP request POST mở** cho tới khi xuất xong.

## 13. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “202 nghĩa là xử lý đã thành công” | 202 chỉ cho biết tiếp nhận; job có thể thất bại hoặc không hoàn tất |
| “Trả 202 là server tự động gọi lại client khi hoàn thành” | HTTP không tự gửi response mới; cần monitor, polling hoặc cơ chế thông báo được thiết kế riêng |
| “202 luôn bắt buộc có Location” | Location là quy ước hữu ích cho monitor trong contract này, không phải bắt buộc của mã 202 |
| “Retry-After với 202 có nghĩa polling chuẩn cho mọi API” | Gợi ý polling qua Retry-After ở 202 cần được API định nghĩa riêng |
| “GET monitor phải trả 202 khi job RUNNING” | Thường **200** vì đọc monitor thành công; trạng thái chạy nằm trong body |
| “Job FAILED thì GET monitor phải là 500” | GET có thể 200, state FAILED; 500 dành cho lỗi truy xuất monitor |
| “@Async + 202 đồng nghĩa durable job” | @Async không tự cung cấp persistence, monitor hoặc recovery |
| “Đẩy message vào broker bảo đảm exactly-once” | Có thể redelivery/crash; phải xử lý idempotency, claim và side effects |
| “Một request POST retry chắc chắn chỉ tạo một job” | Không mặc định; cần contract dedup/idempotency |
| “Job ID là secret cấp quyền” | Mỗi request monitor và kết quả phải authorization |
| “Job SUCCEEDED thì file chắc chắn có” | Chỉ đúng nếu hệ thống gắn SUCCEEDED sau khi result sẵn sàng và có kiểm chứng |
| “Hủy job nghĩa là mọi tác dụng phụ đã rollback” | Cần quy tắc hủy/compensation riêng cho side effects |
| “Bật cache GET monitor để giảm polling mà không xét state” | Cache stale có thể giữ RUNNING hoặc làm lộ job của user khác |

## 14. Bài thực hành thiết kế và kiểm thử

Một API cần tạo **file tổng hợp doanh thu theo chi nhánh**; quá trình chạy trong nền và kết quả chỉ người quản lý chi nhánh được xem.

### Yêu cầu

1. Viết request và response cho **POST /exports**, chọn **202** theo contract “yêu cầu xuất dữ liệu được tiếp nhận”; có monitor URI.
2. Định nghĩa body **GET /exports/{id}** cho **QUEUED, RUNNING, SUCCEEDED, FAILED**. Không lộ dữ liệu nguồn hoặc stack trace.
3. Nêu khi nào dùng **200** và **303** cho monitor ở trạng thái SUCCEEDED; chọn một phương án và giữ nhất quán.
4. Nếu user gửi lại POST sau timeout, API dùng cơ chế gì để tránh tạo hai job? Nếu hai POST thực sự độc lập thì sao?
5. Nếu hai worker cùng claim một job, cần bảo đảm bất biến nào ở DB? Nếu worker mất kết nối khi RUNNING, xử lý recovery thế nào?
6. Viết ba kiểm thử HTTP, hai kiểm thử race/retry và hai kiểm thử authorization liên quan.
7. Đề xuất chính sách polling để 10.000 client không gọi GET monitor mỗi 100 ms.

### Hướng giải tham khảo

- **POST thành công:** ghi job bền vững, trả **202** với **Location: /exports/{id}** và body có **id, state, submittedAt**; body có thể cho biết polling interval theo quy ước.
- **GET monitor:** trả **200** cho cả QUEUED/RUNNING/SUCCEEDED/FAILED. SUCCEEDED có resultUrl; FAILED có failure code an toàn. Nếu chọn **303** khi hoàn tất, tài liệu hóa redirect và cách xem metadata job.
- **Retry:** dùng Idempotency-Key theo scope user/tenant và fingerprint request, xử lý đồng thời bằng ràng buộc DB; key khác nhau là thao tác độc lập nếu nghiệp vụ cho phép.
- **Worker:** claim nguyên tử, có attempt token/lease; recovery không làm hai worker cùng publish kết quả hoặc phát side effect trùng.
- **Test:** xác nhận 202 có monitor đọc được, chuyển trạng thái đến SUCCEEDED, FAILED được biểu diễn trong body 200, không nhận job khi request sai, hai request cùng key không tạo hai job, tenant B không đọc được monitor/file của tenant A.
- **Polling:** bắt đầu với khoảng đợi do API đề xuất, sau đó backoff có giới hạn/jitter, tôn trọng 429 và deadline phía client; không polling khi job terminal.

## 15. Checklist và tài liệu chuẩn

- [ ] Đã phân biệt **đã chấp nhận** với **đã hoàn tất**; không công bố 202 là kết quả nghiệp vụ thành công.
- [ ] POST/PUT/PATCH/DELETE và resource URI phản ánh đúng thao tác mà client yêu cầu.
- [ ] Response 202 mô tả trạng thái hiện tại và cách theo dõi; Location/statusUrl có hợp đồng rõ.
- [ ] Nếu dùng Retry-After ở 202, client biết đây là **quy ước polling của API**.
- [ ] Chỉ trả 202 sau khi đáp ứng chính sách tiếp nhận/ghi nhận công việc; không làm mất job khi server restart.
- [ ] Monitor có schema trạng thái rõ, trạng thái cuối và link kết quả an toàn.
- [ ] GET monitor phân biệt **HTTP status** với **job state**; FAILED không bị biến thành HTTP 500 tùy tiện.
- [ ] Có giới hạn polling, cache policy, thời hạn giữ monitor/kết quả và xử lý 404/410.
- [ ] Mỗi job/monitor/result đều kiểm tra authorization theo principal/tenant.
- [ ] Worker claim nguyên tử, quản lý retry/lease và không publish SUCCEEDED trước khi kết quả sẵn sàng.
- [ ] Nếu POST có thể retry sau timeout, có chiến lược idempotency được công bố.
- [ ] Worker failure lưu mã lỗi an toàn; log nội bộ đủ chẩn đoán nhưng không lộ qua response.
- [ ] Có kiểm thử HTTP 202/200/4xx, state transitions, retry đồng thời, worker crash và cross-tenant access.
- [ ] OpenAPI mô tả Location, response schema, các mã lỗi và thời gian giữ job.

Tài liệu tham khảo:

- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): ý nghĩa **202 Accepted**, **201 Created**, **303 See Other**, **Location** và các mã HTTP.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): lỗi HTTP có cấu trúc ở bước tiếp nhận/truy xuất.
- [RFC 6585 — Additional HTTP Status Codes](https://www.rfc-editor.org/rfc/rfc6585): **429 Too Many Requests** cho giới hạn polling.
- [Spring Framework — Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): **@Scheduled**, **@Async** và giới hạn của xử lý nền trong JVM.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction và thời điểm commit.
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html): mô tả response 202, header, schemas và các resource theo dõi.

**Ghi nhớ:** **202 Accepted** xác nhận một yêu cầu **đã được tiếp nhận nhưng chưa hoàn tất**. Một REST API hữu ích cần đưa client đến **status monitor** có quyền truy cập đúng, trạng thái tin cậy, thông báo lỗi cuối và đường dẫn kết quả khi sẵn sàng. Chất lượng thiết kế được chứng minh bằng **durable acceptance, state transitions, HTTP contract và kiểm thử**, không chỉ bằng việc trả status 202 thật nhanh.
