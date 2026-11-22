# 303 See Other để điều hướng tới kết quả khi phù hợp

## 1. Bài toán: công việc chạy nền hoàn thành thì client lấy kết quả ở đâu?

Một REST API cho phép người dùng xuất báo cáo doanh thu. Việc tổng hợp nhiều triệu bản ghi có thể mất hàng chục giây hoặc vài phút; giữ kết nối POST chờ tới khi báo cáo xong dễ gây timeout ở client, gateway và load balancer. Cách thiết kế thông thường là **nhận yêu cầu, tạo một công việc nền (job), rồi cho client theo dõi tiến độ**.

Khi job chạy xong, có hai tài nguyên khác nhau:

- **Job resource**, ví dụ **/jobs/job-71**, mô tả tiến độ và kết quả xử lý: QUEUED, RUNNING, SUCCEEDED hoặc FAILED.
- **Result resource**, ví dụ **/reports/report-92**, chứa báo cáo cuối cùng có thể tải hoặc xem.

Một câu hỏi quan trọng là: khi client GET job đã thành công, API nên trả JSON chứa URL hay **chỉ dẫn client chuyển sang GET kết quả**? Mã **303 See Other** là một lựa chọn phù hợp khi server muốn nói: *thông tin cần lấy tiếp nằm ở một tài nguyên khác; hãy truy xuất URI trong Location*.

Bài thuộc chương **Xử lý bất đồng bộ** của module **INTEGRATION_API_REST**, đặt trong bối cảnh thiết kế REST API với resource, URI, phương thức, mã trạng thái HTTP, hợp đồng dữ liệu, idempotency, OpenAPI, bảo mật và kiểm thử Java/Spring.

**Mục tiêu:** hiểu chính xác 303, chọn đúng thời điểm chuyển hướng, xây hợp đồng 202 → job monitor → 303 → result, xử lý các trạng thái lỗi và thiết kế bảo mật/kiểm thử thực tế. Trọng tâm là **điều hướng tới kết quả của một công việc đã hoàn tất**, không phải khảo sát mọi mô hình queue hay mọi mã chuyển hướng.

## 2. Ngữ nghĩa HTTP của 303 See Other

Theo **RFC 9110 (HTTP Semantics)**, **303 See Other** là phản hồi chuyển hướng cho biết server đang chỉ đến một tài nguyên khác qua header **Location**. User agent có thể thực hiện **request truy xuất** tại URI đó, thông thường là **GET** (hoặc HEAD nếu thích hợp), để lấy phản hồi gián tiếp liên quan đến request ban đầu.

~~~http
HTTP/1.1 303 See Other
Location: /reports/report-92
Cache-Control: no-store
~~~

Ba ý cần phân biệt:

1. **303 không chứa chính kết quả**. Nó chỉ ra nơi kết quả có thể được truy xuất; client cần một request tới Location.
2. **303 không bảo toàn POST để gửi lại đến đích**. Sau POST, user agent theo 303 thông thường chuyển sang GET/HEAD, không phát lại body POST ở URI mới.
3. **303 không mặc nhiên tuyên bố một resource vừa được tạo**. Nó nói về *nơi lấy một phản hồi gián tiếp*. Nếu tài nguyên mới đã được tạo trực tiếp, **201 Created + Location** có ngữ nghĩa riêng và thường rõ ràng hơn.

URI của Location có thể là URI tương đối; trong ví dụ **/reports/report-92** được phân giải theo URI của request phát sinh phản hồi. Khi công bố absolute URL, server phải dùng origin công khai đã được tin cậy, không ghép từ Host do client tùy ý điều khiển.

### 2.1. So với những mã gần kề

| Mã | Nghĩa chính trong luồng này | Khi phù hợp |
| --- | --- | --- |
| **200 OK** | Truy xuất job hoặc result thành công, có thể kèm representation. | GET job còn RUNNING; GET báo cáo cuối. |
| **201 Created** | Request đã tạo resource mới. | POST tạo ngay một resource, cần công bố URI mới. |
| **202 Accepted** | Request đã được chấp nhận nhưng **chưa hoàn tất**; kết quả cuối chưa được bảo đảm. | POST bắt đầu công việc dài chạy nền. |
| **303 See Other** | Có tài nguyên khác nên truy xuất để lấy phản hồi gián tiếp. | GET job đã SUCCEEDED chuyển sang GET báo cáo cuối. |
| **302 Found** | Redirect tạm với lịch sử hành vi đổi method không đồng nhất. | Không rõ ràng bằng 303 nếu chủ đích là POST → GET. |
| **307 Temporary Redirect** | Redirect tạm **giữ nguyên phương thức**. | Không phù hợp để chuyển POST tạo job thành GET báo cáo. |
| **308 Permanent Redirect** | Redirect lâu dài **giữ nguyên phương thức**. | Không phù hợp cho chuyển tiếp trạng thái job động. |

**Không coi 202 và 303 là hai cách viết tương đương của “đang xử lý”**: 202 có thể đi cùng một tài nguyên theo dõi; 303 nên trỏ tới đích có ý nghĩa để client truy xuất ở giai đoạn đó. Đối với job còn QUEUED/RUNNING, redirect 303 tới báo cáo chưa tồn tại chỉ khiến client gặp 404 hoặc vòng lặp.

## 3. Hợp đồng end-to-end: POST → 202 → GET job → 303 → GET result

### 3.1. Tạo công việc

~~~http
POST /exports HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
Idempotency-Key: export-req-9ad1
Content-Type: application/json

{"format":"csv","period":"2026-10"}
~~~

Server lưu nhận yêu cầu và tạo job có thể theo dõi:

~~~http
HTTP/1.1 202 Accepted
Location: /jobs/job-71
Content-Type: application/json
Cache-Control: no-store

{
  "id": "job-71",
  "state": "QUEUED",
  "monitorUrl": "/jobs/job-71",
  "pollAfterSeconds": 3
}
~~~

**202 không hứa job sẽ thành công.** Trong hợp đồng ví dụ, **Location** của phản hồi 202 chỉ tới **job monitor**, không phải báo cáo cuối; đây là quy ước ứng dụng cần được mô tả rõ. Header Location ở 202 **không tự buộc user agent redirect** như phản hồi 303. Client chủ động đọc monitorUrl hoặc Location theo hợp đồng.

**pollAfterSeconds** là trường riêng của API để gợi ý khoảng polling, không phải thành viên chuẩn của HTTP. Có hệ thống dùng **Retry-After** cho hướng dẫn polling; nếu sử dụng trên 202/200, phải nói rõ đó là quy ước API, không nên giả định mọi HTTP client tự hiểu và thực thi.

### 3.2. Job còn chạy

~~~http
GET /jobs/job-71 HTTP/1.1
Authorization: Bearer <access-token>

HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "id": "job-71",
  "state": "RUNNING",
  "progress": 65,
  "pollAfterSeconds": 3
}
~~~

**200** có nghĩa GET tài nguyên job thành công, **không có nghĩa báo cáo nghiệp vụ hoàn thành**. Client theo dõi trường state, không coi mọi HTTP 2xx là trạng thái SUCCEEDED.

### 3.3. Job đã thành công

Ở lần GET sau, server thấy job **SUCCEEDED**, kết quả đã sẵn sàng và có URI được phép truy xuất:

~~~http
GET /jobs/job-71 HTTP/1.1
Authorization: Bearer <access-token>

HTTP/1.1 303 See Other
Location: /reports/report-92
Cache-Control: no-store
~~~

Client theo Location bằng GET:

~~~http
GET /reports/report-92 HTTP/1.1
Authorization: Bearer <access-token>

HTTP/1.1 200 OK
Content-Type: text/csv
Content-Disposition: attachment; filename="revenue-2026-10.csv"
Cache-Control: private, no-store

date,total
2026-10-01,1200
~~~

Ví dụ trên minh họa luồng, không phải một bản ghi kết nối HTTP nguyên khối. **Status 303 nằm trên response GET job**, còn **200 nằm trên GET result**. Đối với file lớn, endpoint result có thể hỗ trợ Range/206 theo hợp đồng tải file; **303 không thay thế** cơ chế đó.

### 3.4. Sơ đồ sequence

~~~mermaid
sequenceDiagram
    participant C as Client
    participant API as REST API
    participant Q as Job Store / Queue
    participant W as Worker
    C->>API: POST /exports + Idempotency-Key
    API->>Q: Ghi job bền vững
    API-->>C: 202 Location /jobs/71
    Q->>W: Phân phối công việc
    C->>API: GET /jobs/71
    API-->>C: 200 state RUNNING
    W->>Q: Lưu result và đánh dấu SUCCEEDED
    C->>API: GET /jobs/71
    API-->>C: 303 Location /reports/92
    C->>API: GET /reports/92
    API-->>C: 200 CSV / JSON
~~~

**Điều kiện bắt buộc trước 303:** kết quả phải thực sự đọc được, đã commit metadata/đường dẫn cần thiết, và client có thể được phân quyền để lấy result. Nếu đánh dấu SUCCEEDED trước khi file hoặc bản ghi result sẵn sàng, client có thể bị redirect tới 404, tạo race condition ở ranh giới hoàn tất.

## 4. Không phải lúc nào hoàn tất job cũng nên trả 303

Có nhiều thiết kế hợp lệ. **303 là một lựa chọn**, không phải quy định bắt buộc cho mọi API bất đồng bộ.

| Tình huống | Lựa chọn hợp lý | Đánh đổi |
| --- | --- | --- |
| Job SUCCEEDED và có result resource riêng, truy cập bằng GET. | **303 + Location** khi GET monitor. | Client nhận luôn result nếu HTTP library theo redirect; trạng thái job có thể bị che. |
| Client cần biết chi tiết job, thời gian chạy, log, lỗi, tiến độ sau khi xong. | **200 OK** với state SUCCEEDED và trường **resultUrl**. | Client phải tự gọi GET result, nhưng luôn nhìn thấy metadata job. |
| Job hoàn thành ngay trong POST và tạo resource mới. | **201 Created + Location** theo semantics tạo tài nguyên. | Không cần mô hình monitor nếu không có việc nền. |
| POST là một thao tác cần chuyển sang trang GET xác nhận hoặc kết quả đã có. | **303 ngay sau POST** khi URI đích đã có ý nghĩa truy xuất. | Phù hợp mô hình POST/Redirect/GET, nhưng không có trạng thái queue để theo dõi. |
| Job FAILED hoặc CANCELLED. | **200** khi GET monitor với trạng thái FAILED/CANCELLED; lỗi nghiệp vụ nằm trong body theo hợp đồng. | Không redirect tới result thành công không tồn tại. |
| Result hết hạn hoặc đã bị thu hồi. | **404/410/403** theo chính sách vòng đời/quyền, hoặc giữ job metadata và thông báo result không còn. | Không phát 303 trỏ tới resource biết chắc không truy xuất được. |

### 4.1. 303 ngay sau POST

**POST/Redirect/GET** là một trường hợp khác: server xử lý POST rồi trả **303 + Location** tới trang kết quả/xác nhận đã có để client GET, tránh gửi lại form khi tải lại trang. Nếu POST tạo resource mới trực tiếp, **201** thường rõ hơn; nếu mới nhận job chưa chạy, dùng **202**. Không chọn 303 chỉ vì request là POST.

### 4.2. Khi muốn giữ client ở monitor resource

Ví dụ:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":"job-71","state":"SUCCEEDED","resultUrl":"/reports/report-92"}
~~~

Thiết kế này phù hợp dashboard cần lịch sử, thời lượng hoặc checksum. Nếu hỗ trợ cả 200 và 303, phải có hợp đồng hoặc negotiation rõ ràng để SDK không bất ngờ nhận loại phản hồi khác.

## 5. Máy trạng thái job và tính nhất quán

~~~mermaid
stateDiagram-v2
    [*] --> QUEUED
    QUEUED --> RUNNING
    RUNNING --> SUCCEEDED
    RUNNING --> FAILED
    QUEUED --> CANCELLED
    RUNNING --> CANCELLED
    SUCCEEDED --> [*]
    FAILED --> [*]
    CANCELLED --> [*]
~~~

Đây là máy trạng thái minh họa. Dự án có thể có **RETRYING**, **CANCEL_REQUESTED**, **EXPIRED** hoặc trạng thái khác, nhưng cần quy tắc chuyển trạng thái hợp lệ, không lặp/nhảy tùy tiện.

### 5.1. Những bất biến quan trọng

1. **202** chỉ phát khi đã ghi nhận job đủ bền vững; tránh chỉ lưu vào RAM rồi mất job khi process chết.
2. **SUCCEEDED/303** chỉ được công bố sau khi result đã publish và sẵn sàng GET cho người có quyền.
3. Worker có thể nhận job trùng; cần lease, unique constraint hoặc idempotent consumer để tránh tạo tác dụng phụ trùng.
4. **FAILED** được đọc qua monitor, không chuyển hướng giả; TTL của job/result phải có hợp đồng hết hạn.

### 5.2. Lỗi sau khi đã trả 202

Khi POST đã kết thúc bằng **202**, worker thất bại về sau không thể thay response đó thành 500. Client biết lỗi qua monitor hoặc callback/webhook đã thỏa thuận.

Ví dụ GET job thất bại:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "job-71",
  "state": "FAILED",
  "error": {"code":"SOURCE_UNAVAILABLE","message":"Không thể đọc nguồn báo cáo."}
}
~~~

**200** là trạng thái GET job thành công; **FAILED** là kết quả nghiệp vụ. Nếu backend monitor hỏng, 5xx mô tả lỗi của chính GET, không phải trạng thái của job.

### 5.3. Chống chuyển trạng thái sai thứ tự

Đánh dấu SUCCEEDED bằng ghi có điều kiện, chẳng hạn **UPDATE ... WHERE id = :job_id AND state = 'RUNNING'**, kèm result ID đã xác minh hợp lệ. Nếu dùng object storage khác giao dịch với database, cần bước kiểm chứng kết quả trước khi publish trạng thái và xử lý worker retry/cancellation.

## 6. Client thực sự thấy gì khi theo 303?

Nhiều HTTP client tự động theo redirect. Khi client thực hiện GET **/jobs/job-71**, thư viện có thể tự gọi tiếp GET **/reports/report-92** và trả cho ứng dụng **200 CSV**, khiến code phía trên **không nhìn thấy response trung gian 303**.

Điều đó có thể là trải nghiệm mong muốn cho một nút “tải báo cáo”, nhưng không phù hợp nếu màn hình cần hiển thị **state job**, kiểm tra audit hay nhận biết chính xác lúc nào redirect xảy ra.

### 6.1. Hai chế độ client

Nếu **tự follow**, ứng dụng thường nhận response cuối từ GET result; nếu **tắt redirect**, ứng dụng nhận 303/Location và tự quyết định lúc nào gọi tiếp. Cần chọn một chế độ rõ ràng cho SDK.

Ví dụ curl:

~~~bash
# Xem nguyên phản hồi monitor, bao gồm 303/Location nếu có.
curl -i \
  -H 'Authorization: Bearer <access-token>' \
  'https://api.example.com/jobs/job-71'

# Theo redirect của GET để tải tài nguyên kết quả.
curl -i -L \
  -H 'Authorization: Bearer <access-token>' \
  'https://api.example.com/jobs/job-71'
~~~

**Lưu ý:** lệnh trên chỉ minh họa trên origin được tin cậy. Tránh kết hợp ép **-X POST** với **-L** khi muốn kiểm thử hành vi POST → 303 → GET, vì việc ép phương thức trong curl có thể làm lệch kỳ vọng redirect. Tài liệu SDK nên nói rõ mặc định thư viện có theo redirect hay không và cách truy cập status/header trung gian.

### 6.2. Phản hồi cuối có thể không phải JSON

Nếu SDK chỉ parse Job JSON nhưng thư viện tự theo 303 tới **text/csv**, parse sẽ lỗi. Kiểm tra **Content-Type**, URL/redirect history khi cần và xử lý trường hợp GET result trả 403/404/410. Trong browser, **fetch** thường tự theo redirect; việc quan sát Location trung gian, nhất là cross-origin, bị giới hạn bởi chính sách bảo mật.

## 7. Java/Spring MVC: ví dụ controller

Ví dụ Spring Boot 3 minh họa hai endpoint **POST /exports** và **GET /jobs/{id}**. Service và worker queue được giả định đã triển khai; điểm chính là chọn status, Location và bảo mật.

~~~java
import java.net.URI;
import java.security.Principal;
import java.util.UUID;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

enum JobState { QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELLED }
record ExportRequest(String format, String period) {}
record JobSnapshot(
        UUID id, JobState state, UUID resultId, String errorCode) {}
record JobView(
        UUID id, JobState state, String monitorUrl,
        Integer pollAfterSeconds, String errorCode) {}

interface ExportJobService {
    JobSnapshot submit(
            String actor, String idempotencyKey, ExportRequest request);
    JobSnapshot findAuthorized(String actor, UUID jobId);
}

@RestController
class ExportController {
    private final ExportJobService service;

    ExportController(ExportJobService service) {
        this.service = service;
    }

    @PostMapping("/exports")
    ResponseEntity<JobView> submit(
            Principal principal,
            @RequestHeader("Idempotency-Key") String key,
            @RequestBody ExportRequest request) {

        JobSnapshot job = service.submit(
                principal.getName(), key, request);
        String monitor = "/jobs/" + job.id();
        JobView body = new JobView(
                job.id(), job.state(), monitor, 3, null);

        return ResponseEntity.status(HttpStatus.ACCEPTED)
                .location(URI.create(monitor))
                .cacheControl(CacheControl.noStore())
                .body(body);
    }

    @GetMapping("/jobs/{id}")
    ResponseEntity<?> monitor(
            Principal principal,
            @PathVariable UUID id) {

        JobSnapshot job = service.findAuthorized(
                principal.getName(), id);

        if (job.state() == JobState.SUCCEEDED) {
            // Chỉ dùng ID kết quả đã được xác nhận ở server.
            URI result = URI.create("/reports/" + job.resultId());
            return ResponseEntity.status(HttpStatus.SEE_OTHER)
                    .location(result)
                    .cacheControl(CacheControl.noStore())
                    .build();
        }

        JobView body = new JobView(
                job.id(), job.state(),
                "/jobs/" + job.id(),
                job.state() == JobState.RUNNING
                    || job.state() == JobState.QUEUED ? 3 : null,
                job.errorCode());
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(body);
    }
}
~~~

**Giải thích giới hạn mẫu code:**

- **ExportJobService.submit** phải xác thực format/period, phạm vi người dùng, idempotency key và ghi job bền vững trước khi controller trả 202.
- **findAuthorized** phải kiểm tra chủ sở hữu/tenant của job. Kết quả ở **GET /reports/{id}** phải kiểm tra quyền **lần nữa**, không chỉ dựa vào việc client đến từ redirect.
- Code giả định **resultId != null khi SUCCEEDED**; phải bảo đảm bất biến ở service/database trước khi phát 303.
- Không lấy đường dẫn Location từ JSON yêu cầu hoặc thông tin do worker ngoài tin cậy trả về mà chưa kiểm tra. Dựng URI theo route nội bộ được phép giúp tránh open redirect.
- **Principal.getName()** là minh họa định danh actor; hệ thống thật có thể dùng account/tenant/scope từ security principal và quy tắc ủy quyền riêng.
- Đoạn code chưa cài đặt validator, queue, storage, auth filter hay Problem Details; không xem nó là hệ thống production hoàn chỉnh.

### 7.1. Tầng worker phải commit theo thứ tự

Một service có thể làm:

~~~text
POST handler:
  authenticate and authorize export scope
  reserve idempotency key for actor + request fingerprint
  atomically persist job QUEUED and outbox message
  commit
  respond 202 with monitor URI

Worker:
  claim job with lease or conditional update
  generate report and store result securely
  verify result available for GET
  atomically publish result mapping and state SUCCEEDED
  acknowledge work; retries must not create duplicate effects
~~~

Nếu kết quả được lưu ở object storage không cùng transaction với database, phải thiết kế bước publish và xử lý orphan file khi có lỗi. **303 chỉ được phát sau bước publish đáng tin cậy**, không dựa vào việc worker “gần xong”.

## 8. Bảo mật: redirect không cấp quyền

### 8.1. Chặn truy cập job và result khác tenant

Biết URI **/jobs/job-71** hoặc **/reports/report-92** không có nghĩa được xem dữ liệu. Server phải:

1. Xác thực từng request.
2. Phân quyền theo actor/tenant/scope khi GET monitor.
3. Phân quyền độc lập khi GET result, kể cả khi request vừa theo 303.
4. Không đưa ID, đường dẫn, metadata hoặc tình trạng tài nguyên của tenant khác vào response lỗi.
5. Dùng 403 hoặc 404 theo chính sách che sự tồn tại, nhất quán giữa monitor và result.

UUID khó đoán không thay thế authorization. Nếu result là file chứa dữ liệu khách hàng, nên giới hạn thời gian tồn tại, chính sách cache, audit và quyền tải xuống.

### 8.2. Open redirect và chuyển token sang host khác

Không làm như sau:

~~~http
GET /jobs/job-71?returnTo=https://attacker.example/collect

HTTP/1.1 303 See Other
Location: https://attacker.example/collect
~~~

Nếu server copy nguyên **returnTo** từ client vào Location, API có thể trở thành **open redirect**. Nếu HTTP client tự động theo Location, nguy cơ phát sinh truy cập sang host không tin cậy hoặc lộ dữ liệu qua URL/referrer. Với backend HTTP client, theo redirect tới IP nội bộ có thể tạo **SSRF**.

Đề xuất:

- Ưu tiên **relative Location cùng origin** cho result do API quản lý.
- Nếu bắt buộc cross-origin, dùng allowlist scheme/host và cấu hình redirect trong SDK; đừng tự động chuyển bearer token sang host khác.
- Nếu dùng pre-signed download URL, coi nó là **credential có hạn sử dụng**: TTL ngắn, scope chỉ một object và tránh log/phát tán URL.
- Kiểm tra cả redirect thứ hai từ result endpoint nếu client cho phép theo chuỗi.

### 8.3. Cache và vòng đời result

Với dữ liệu riêng và trạng thái biến động, áp dụng **Cache-Control: private, no-store** cho monitor/303 như ví dụ để tránh redirect cũ. **303 vẫn có thể được cache khi có freshness tường minh phù hợp**; không mặc định mọi 303 đều tự động không cache. Định nghĩa rõ TTL và 404/410 khi kết quả hết hạn, tránh phát 303 tới file đã xóa.

## 9. Idempotency và retry không được giải quyết bởi 303

Nếu client POST /exports rồi gặp timeout trước khi nhận 202, request có thể đã được ghi vào queue. Gửi lại POST một cách mù quáng có thể tạo **hai job** và tốn tài nguyên, hoặc tạo hai báo cáo/tác dụng phụ nếu worker không chống trùng.

Ví dụ:

~~~http
POST /exports HTTP/1.1
Idempotency-Key: export-req-9ad1
Content-Type: application/json

{"format":"csv","period":"2026-10"}
~~~

Server cần ràng buộc key với actor/tenant và fingerprint yêu cầu, xử lý hai request đồng thời bằng cơ chế nguyên tử, ghi lại job/kết quả theo thời hạn rõ ràng:

- **Cùng key + cùng payload:** trả cùng job hoặc kết quả tương đương theo hợp đồng; không tạo job thứ hai.
- **Cùng key + payload khác:** từ chối rõ ràng, ví dụ **409 Conflict** theo hợp đồng.
- **Key hết hạn:** nêu rõ liệu có thể tạo job mới; không lẳng lặng hứa exactly-once vĩnh viễn.

GET monitor và GET result là thao tác truy xuất, có thể retry có giới hạn khi lỗi mạng, nhưng cần xét **429/503 và Retry-After**, backoff, jitter và ngân sách timeout. **303 không thay thế idempotency của POST**; nó chỉ là cách điều hướng tới tài nguyên khác khi server đã quyết định đó là bước tiếp phù hợp.

## 10. Mô tả bằng OpenAPI 3.1

Một hợp đồng hữu ích cần công bố **202/Location**, trạng thái 200 của monitor, phản hồi **303/Location**, lỗi và kiểu kết quả cuối. Ví dụ rút gọn:

~~~yaml
openapi: 3.1.0
info:
  title: Report Export API
  version: 1.0.0
paths:
  /exports:
    post:
      summary: Đặt công việc xuất báo cáo
      parameters:
        - name: Idempotency-Key
          in: header
          required: true
          schema: {type: string}
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ExportRequest'
      responses:
        '202':
          description: Job đã được chấp nhận và có URI theo dõi
          headers:
            Location:
              description: URI job monitor, không phải redirect tự động
              schema: {type: string, format: uri-reference}
          content:
            application/json:
              schema: {$ref: '#/components/schemas/Job'}
        '409':
          description: Idempotency key xung đột payload
  /jobs/{id}:
    get:
      summary: Theo dõi trạng thái job hoặc điều hướng result
      parameters:
        - in: path
          name: id
          required: true
          schema: {type: string, format: uuid}
      responses:
        '200':
          description: Trạng thái job, kể cả FAILED nếu xảy ra
          content:
            application/json:
              schema: {$ref: '#/components/schemas/Job'}
        '303':
          description: Job hoàn tất và result sẵn sàng truy xuất
          headers:
            Location:
              description: URI resource kết quả để GET
              required: true
              schema: {type: string, format: uri-reference}
        '404':
          description: Không tồn tại hoặc không được tiết lộ
  /reports/{id}:
    get:
      summary: Tải báo cáo hoàn tất
      parameters:
        - in: path
          name: id
          required: true
          schema: {type: string, format: uuid}
      responses:
        '200':
          description: Nội dung báo cáo
          content:
            text/csv:
              schema: {type: string}
        '403':
          description: Không có quyền tải
components:
  schemas:
    ExportRequest:
      type: object
      required: [format, period]
      properties:
        format: {type: string, enum: [csv]}
        period: {type: string}
    Job:
      type: object
      required: [id, state, monitorUrl]
      properties:
        id: {type: string, format: uuid}
        state:
          type: string
          enum: [QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELLED]
        monitorUrl: {type: string, format: uri-reference}
        pollAfterSeconds: {type: [integer, 'null']}
        errorCode: {type: [string, 'null']}
~~~

Đây là **trích đoạn**: production phải bổ sung securitySchemes, Problem Details, 400/401/403/404/410/429, TTL và giới hạn file. OpenAPI khai báo 303 **không bảo đảm SDK nhìn thấy response trung gian** khi thư viện tự follow redirect.

## 11. Kiểm thử thực tế: status, Location, quyền và race

### 11.1. Ma trận kiểm thử

| ID | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| A01 | POST hợp lệ | **202**, Location trỏ job, body QUEUED/RUNNING; job đã lưu bền vững. |
| A02 | GET job chưa chạy xong | **200**, state QUEUED/RUNNING, **không 303**. |
| A03 | GET job SUCCEEDED, result đã lưu | **303**, Location đúng URI result được phép; không tạo thêm job. |
| A04 | GET result theo Location | **200**, content type/data đúng; chủ sở hữu được phép đọc. |
| A05 | Job FAILED | GET job **200** với FAILED/errorCode; không redirect giả. |
| A06 | Worker chưa publish result hoặc xử lý trùng | Không 303 sớm; không nhân đôi result/tác dụng phụ. |
| A07 | POST retry đồng thời cùng key, hoặc cùng key khác payload | Chỉ một job logic; payload khác bị từ chối 409. |
| A08 | Truy cập từ tenant khác vào job/result | 403/404 theo chính sách ở cả hai endpoint. |
| A09 | Location bị điều khiển hoặc client theo redirect lạ | Không open redirect/SSRF, không gửi token sai host. |
| A10 | Job/result hết hạn, proxy/cache tham gia | Không 303 tới file đã xóa; không trả redirect cũ cho user khác. |

### 11.2. Spring MockMvc: hoàn thành mới phát 303

Trong test MVC, mock service trả job SUCCEEDED cùng result ID:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

mockMvc.perform(get("/jobs/{id}", completedJobId)
        .principal(() -> "user-17"))
    .andExpect(status().isSeeOther())
    .andExpect(header().string(
        "Location", "/reports/" + reportId))
    .andExpect(header().string("Cache-Control", "no-store"));
~~~

Kiểm thử job RUNNING:

~~~java
mockMvc.perform(get("/jobs/{id}", runningJobId)
        .principal(() -> "user-17"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.state").value("RUNNING"))
    .andExpect(header().doesNotExist("Location"));
~~~

Các ID và service mock phải được chuẩn bị trong fixture; nếu ứng dụng có Spring Security, test cần thiết lập **authentication hợp lệ trong security context**, không dựa vào việc gắn Principal đơn thuần để chứng minh authorization.

### 11.3. Integration test nên xác minh gì?

MockMvc chưa chứng minh được queue và storage có thứ tự commit đúng. Test tích hợp với database/worker hoặc test double kiểm soát được thời điểm:

1. Giữ worker tạm dừng sau khi nhận job: POST đã trả 202 nhưng GET monitor vẫn là QUEUED/RUNNING.
2. Cho worker ghi file nhưng chưa commit mapping: GET monitor **không trả 303**.
3. Commit mapping và state SUCCEEDED: GET monitor trả 303, theo Location đọc được file hợp lệ.
4. Worker cố xử lý trùng: chỉ một result được công bố.
5. Thử lỗi I/O sau khi POST trả 202: GET monitor hiển thị FAILED, không thành 303.
6. Kiểm tra same-origin Location, quyền tenant khi gọi monitor **và** result.
7. Thử hai request POST cùng key đồng thời: DB chỉ chứa một job logic.

Đối với SDK, thử cả **redirect disabled** và **redirect enabled** để xác nhận client không cố parse CSV thành Job JSON hoặc đánh mất quyền kiểm soát URL. Khi dùng gateway thật, thử Host header, TLS termination, route prefix và cross-origin redirect.

## 12. Những phản mẫu cần tránh

| Phản mẫu | Hệ quả | Cách sửa |
| --- | --- | --- |
| Trả **303 khi job còn QUEUED** hoặc chưa publish result | Client GET result gặp 404. | 202 nhận việc, 200 monitor, 303 chỉ sau publish. |
| Coi **202** là job thành công | Bỏ qua khả năng FAILED. | Theo dõi trạng thái cuối qua monitor/webhook. |
| Dùng **307/308** thay 303 để POST → GET | 307/308 giữ nguyên method/body. | Dùng 303 cho truy xuất gián tiếp bằng GET. |
| Dùng **303** thay mọi **201** | Mất ngữ nghĩa tạo tài nguyên trực tiếp. | Chọn theo kết quả thực của POST. |
| Client tự theo mọi redirect và parse JSON | Lộ token, SSRF hoặc parse CSV sai. | Kiểm soát origin, Content-Type, redirect policy. |
| Không chống POST retry hoặc worker chạy trùng | Nhân đôi job/result. | Idempotency-Key và worker claim/unique. |
| Chia sẻ 303 chứa link riêng qua cache | Lộ result tenant khác. | no-store, phân quyền monitor/result. |

## 13. Checklist trước khi dùng 303 cho kết quả bất đồng bộ

- [ ] Phân biệt đúng **202 Accepted**, **200 job status**, **303 See Other** và **200 result**.
- [ ] POST trả 202 sau khi job được ghi nhận đáng tin cậy; không hứa công việc chắc chắn thành công.
- [ ] **Location** của 202 được tài liệu hóa là monitor URI theo hợp đồng; không giả định client tự redirect.
- [ ] **303 chỉ xuất hiện khi result sẵn sàng**, có Location đúng URI và phương thức truy xuất GET/HEAD phù hợp.
- [ ] Job FAILED/CANCELLED có trạng thái đọc được; không dùng 303 dẫn tới result không tồn tại.
- [ ] Client được thông báo rõ redirect có thể tự động được theo, làm response cuối khác Job JSON.
- [ ] Không dùng 307/308 thay cho 303 nếu muốn chuyển POST thành GET.
- [ ] Có idempotency cho POST, chống duplicate worker và cơ chế publish result trước SUCCEEDED.
- [ ] Monitor và result đều kiểm tra authentication/authorization; không lộ tài nguyên tenant khác.
- [ ] Location không lấy trực tiếp từ input không tin cậy; redirect cross-origin được giới hạn chặt.
- [ ] Chính sách Cache-Control, TTL, 404/410 và dữ liệu cá nhân được định nghĩa rõ.
- [ ] OpenAPI mô tả status 202/200/303, Location, schema job và result.
- [ ] Test chứng minh job RUNNING không 303, SUCCEEDED chỉ 303 sau commit, Location đọc được, FAILED không redirect.
- [ ] Test retry POST, worker chạy trùng, quyền tenant, redirect policy ở client và proxy thật.

**Kết luận:** **303 See Other** thích hợp khi API muốn chuyển client từ **tài nguyên theo dõi một job đã hoàn tất** sang **tài nguyên kết quả có thể truy xuất**. Nó không thay thế 202 khi công việc còn chạy, không bảo đảm kết quả nghiệp vụ nếu server chưa publish, và không tự giải quyết idempotency hay phân quyền. Thiết kế tốt đặt 303 đúng thời điểm, phát Location an toàn, giữ hợp đồng trạng thái rõ ràng và kiểm thử cả HTTP client lẫn thứ tự commit của worker.
