# Hủy công việc và trường hợp đã bắt đầu tạo tác dụng phụ

## 1. Hủy một job không đồng nghĩa hoàn tác kết quả của nó

Một REST API nhận yêu cầu xuất báo cáo, gửi email hàng loạt hoặc xử lý thanh toán rồi trả **202 Accepted** vì công việc sẽ chạy bất đồng bộ. Sau đó, người dùng nhấn **Hủy**. Nếu job chưa được worker nhận, hệ thống có thể ngăn nó chạy. Nhưng nếu email đã được gửi, tiền đã được thu hoặc thông điệp đã được phát tới hệ thống khác thì điều gì xảy ra?

**Cancellation là yêu cầu cố gắng dừng phần việc chưa xảy ra, không phải giao dịch hoàn tác mọi tác dụng phụ đã xảy ra.** Chính sách phải phân biệt:

- **Yêu cầu hủy được tiếp nhận:** API đã ghi lại mong muốn hủy, nhưng worker có thể vẫn đang chạy.
- **Hủy thành công:** hệ thống xác nhận job dừng trước khi tạo ra những tác dụng phụ mà hợp đồng yêu cầu ngăn chặn.
- **Quá muộn để hủy:** một bước không thể đảo ngược đã được commit hoặc job đã kết thúc.
- **Kết quả chưa rõ:** hệ thống ngoài có thể đã thực hiện tác dụng phụ nhưng response bị mất; cần đối soát thay vì tuyên bố đã hủy.
- **Bù trừ (compensation):** nếu nghiệp vụ cho phép, thực hiện **hành động mới** để giảm hoặc đảo ngược tác động (ví dụ refund), không xóa lịch sử giao dịch cũ.

Bài thuộc chương **Xử lý bất đồng bộ** của module **INTEGRATION_API_REST**. Trọng tâm là thiết kế resource/URI, HTTP methods/status code, hợp đồng dữ liệu, idempotency, xác thực/phân quyền, lỗi và kiểm thử REST API với Java/Spring hoặc công nghệ tương đương.

**Mục tiêu:** sau bài học, bạn có thể thiết kế cancellation resource, xử lý race giữa worker và người dùng, xác định “điểm không thể hủy”, ghi trạng thái chính xác khi tác dụng phụ đã bắt đầu, và kiểm chứng cơ chế bằng test đồng thời cùng fault injection.

## 2. Ví dụ xuyên suốt: job xuất báo cáo và gửi thông báo

Giả sử client yêu cầu tạo báo cáo tài chính và gửi email thông báo khi hoàn tất:

~~~http
POST /v1/report-jobs HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json
Idempotency-Key: "6ed92942-93ab-412b-a05e-6df548a92b35"

{"reportId":"r-42","notifyByEmail":true}

HTTP/1.1 202 Accepted
Location: /v1/report-jobs/job-701
Retry-After: 3
Content-Type: application/json

{"id":"job-701","status":"QUEUED"}
~~~

**202 chỉ xác nhận đã nhận yêu cầu để xử lý**, không hứa báo cáo đã tạo hoặc email đã gửi. API cung cấp resource trạng thái:

~~~http
GET /v1/report-jobs/job-701 HTTP/1.1
Authorization: Bearer <access-token>

HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "id":"job-701",
  "status":"RUNNING",
  "phase":"RENDERING",
  "cancellation":{"requested":false},
  "result":null
}
~~~

Để hủy, client **không gọi GET với `?cancel=true`**. Ta mô hình hóa một resource ghi nhận ý định:

~~~http
POST /v1/report-jobs/job-701/cancellation-requests HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json
Idempotency-Key: "c4f0a337-96ea-419a-8b21-f83ab2edb94e"

{"reason":"USER_REQUESTED"}

HTTP/1.1 202 Accepted
Location: /v1/report-jobs/job-701/cancellation-requests/cr-19
Content-Type: application/json
Cache-Control: no-store

{
  "id":"cr-19",
  "jobId":"job-701",
  "status":"ACCEPTED",
  "message":"Yêu cầu hủy đã được ghi nhận; kết quả chưa được xác nhận."
}
~~~

Client tiếp tục **GET job hoặc cancellation-request** để biết kết quả cuối. **Không hiển thị “Đã hủy” chỉ dựa trên 202.** Khi job đã bị dừng an toàn, job chuyển `CANCELLED`; nếu email đã gửi, response có thể báo **TOO_LATE** và job vẫn `SUCCEEDED`.

## 3. Hai vòng đời: trạng thái job và trạng thái yêu cầu hủy

Không nên gộp hai câu hỏi “job đang làm gì?” và “yêu cầu hủy đã được xử lý chưa?” vào một cờ Boolean.

### 3.1. State machine của job

~~~mermaid
stateDiagram-v2
    [*] --> QUEUED
    QUEUED --> RUNNING: Worker claim
    QUEUED --> CANCELLED: Hủy trước khi claim
    RUNNING --> CANCEL_REQUESTED: Ghi nhận hủy
    RUNNING --> SUCCEEDED: Hoàn tất tác dụng phụ
    RUNNING --> FAILED: Lỗi đã xác định
    CANCEL_REQUESTED --> CANCELLED: Dừng trước điểm commit
    CANCEL_REQUESTED --> SUCCEEDED: Toàn bộ công việc đã commit
    CANCEL_REQUESTED --> PARTIALLY_COMPLETED: Một phần effect đã commit
    CANCEL_REQUESTED --> OUTCOME_UNKNOWN: Kết quả bên ngoài chưa rõ
    OUTCOME_UNKNOWN --> SUCCEEDED: Đối soát xác nhận đã làm
    OUTCOME_UNKNOWN --> CANCELLED: Đối soát xác nhận chưa làm và đã dừng
~~~

Sơ đồ là **một thiết kế tham khảo**, không phải chuẩn trạng thái HTTP. `FAILED` khác `CANCELLED`; `PARTIALLY_COMPLETED` ghi nhận một số effect đã commit dù phần còn lại bị dừng. **Không đổi `SUCCEEDED` thành `CANCELLED`** để che lịch sử; nếu cần hoàn tiền/xóa file, tạo workflow bù trừ có audit.

### 3.2. State machine của cancellation request

| Trạng thái yêu cầu hủy | Ý nghĩa | Trạng thái job có thể tương ứng |
|---|---|---|
| `ACCEPTED` | Đã ghi nhận, đang chờ worker hoặc transaction xác nhận | `CANCEL_REQUESTED` / `RUNNING` |
| `COMPLETED` | Job thực sự được dừng theo cam kết hủy | `CANCELLED` |
| `TOO_LATE` | Job đã hoàn tất hoặc tác dụng phụ không thể ngăn | `SUCCEEDED` / `PARTIALLY_COMPLETED` |
| `REJECTED` | Người gọi không đủ điều kiện hủy theo quy tắc nghiệp vụ | Không thay đổi job |
| `REQUIRES_RECONCILIATION` | Chưa biết thao tác ngoài đã commit hay chưa | `OUTCOME_UNKNOWN` |

Một implementation có thể không cần persist tất cả các trạng thái trên; nhưng **contract phải phân biệt rõ tiếp nhận với kết quả**. Không dùng `status=CANCELLED` của cancellation request để ám chỉ đã hoàn tác một khoản tiền đã thu.

### 3.3. “Điểm không thể hủy” phụ thuộc loại tác dụng phụ

| Bước công việc | Hủy có thể bảo đảm điều gì? | Cần làm nếu quá muộn |
|---|---|---|
| Đang xếp hàng, chưa claim | Ngăn worker bắt đầu nếu claim/hủy nguyên tử | Không cần bù trừ |
| Đang tính toán/ghi file tạm | Dừng tại checkpoint, dọn dữ liệu chưa công bố | Cleanup có thể cần retry |
| File đã được công bố cho người dùng | Không thể nói “chưa từng tạo file” | Thu hồi quyền truy cập/xóa artifact bằng thao tác riêng |
| Email đã được provider chấp nhận/gửi | Không thể thu hồi email đã đến người nhận | Có thể gửi thông báo đính chính |
| Thanh toán đã capture | Không thể biến capture thành “chưa xảy ra” | Tạo yêu cầu refund/void theo trạng thái provider |
| Event đã publish tới broker | Không kiểm soát được mọi consumer đã xử lý | Event bù trừ và consumer idempotent nếu nghiệp vụ hỗ trợ |

**Tên phase không đủ làm chứng cứ:** chuyển `phase=EMAIL_SENDING` không khẳng định email đã gửi; một request timeout cũng không chứng minh email chưa gửi. Muốn kết luận phải dựa trên **bằng chứng kết quả** từ provider, transaction hay business reference.

## 4. HTTP contract: tiếp nhận, từ chối và truy vấn kết quả

Có thể chọn **DELETE /jobs/{id}** để yêu cầu loại bỏ resource nếu semantics hệ thống thật sự là xóa hoặc kết thúc job và tài liệu hóa rõ. Nhưng nhiều hệ thống cần giữ job để audit và có quá trình hủy kéo dài. Khi đó, **POST /jobs/{id}/cancellation-requests** biểu diễn rõ một **ý định có vòng đời riêng**, thích hợp hơn việc xóa ngay job.

| Request hoặc tình huống | HTTP status gợi ý | Body/Header |
|---|---|---|
| POST tạo job được xếp hàng | `202 Accepted` | `Location` của job, URI theo dõi |
| GET trạng thái job được phép xem | `200 OK` | `status`, `phase`, kết quả hoặc lỗi |
| POST yêu cầu hủy, job đang chạy | `202 Accepted` | `Location` của cancellation request, `status=ACCEPTED` |
| POST yêu cầu hủy, job còn QUEUED và hủy nguyên tử | `201 Created` hoặc `200 OK` theo hợp đồng | Có thể trả cancellation request `COMPLETED` ngay |
| POST hủy job đã `SUCCEEDED`/`CANCELLED` bằng **ý định mới** | `409 Conflict` | Problem Details với mã `JOB_ALREADY_TERMINAL` |
| Gửi lại **cùng Idempotency-Key/payload** | Replay kết quả đã lưu | Không tạo yêu cầu hủy/hậu quả mới |
| Thiếu hoặc sai credential | `401 Unauthorized` | `WWW-Authenticate` thích hợp |
| Đã xác thực nhưng không có quyền hủy | `403 Forbidden` | Không tiết lộ dữ liệu không được phép |
| Job thuộc tenant khác hoặc phải che giấu | `404 Not Found` | Body trung tính |
| Cùng key nhưng payload khác | `409`/`422` theo hợp đồng | Mã lỗi xác định, không xử lý mới |
| Body sai cú pháp hoặc thiếu field bắt buộc | `400 Bad Request` | `application/problem+json` |

**Phân biệt hai trường hợp:** request hủy mới gửi khi job đã kết thúc có thể bị **409**, nhưng một lần **replay chính request hủy đã được tiếp nhận trước đó** phải được nhận diện bằng key và trả kết quả của request cũ theo chính sách. Không cho retry do mất mạng tự nhiên trở thành một yêu cầu mới thất bại vì trạng thái job đổi.

### 4.1. Polling không gây thay đổi trạng thái

`GET /v1/report-jobs/job-701/cancellation-requests/cr-19` trả `200` với receipt hiện hành (ví dụ `status=COMPLETED`), không tạo side effect. Client dùng `Retry-After` của 202 hoặc backoff có giới hạn để poll. Với dữ liệu riêng tư, cân nhắc `Cache-Control: no-store`; nếu dùng ETag, **304 chỉ có nghĩa representation không đổi**, không khẳng định job đã hủy.

### 4.2. Phiên bản job và điều kiện HTTP

Nếu client cần hủy **chỉ khi job vẫn đúng phiên bản đã thấy**, có thể:

- Gửi `PATCH /jobs/{id}` với `If-Match` của **chính resource job**, trong hợp đồng cho phép thay đổi trạng thái/yêu cầu hủy; `412` khi ETag không còn khớp.
- Hoặc dùng `POST /jobs/{id}/cancellation-requests` với trường `expectedJobVersion` **do ứng dụng định nghĩa**; handler kiểm tra version trong transaction và trả `409` nếu không còn phù hợp.

**Không tự lấy ETag của GET job làm `If-Match` cho POST tới URI cancellation-requests** rồi giả định HTTP tự kiểm tra phiên bản của resource cha. `If-Match` áp dụng cho **target resource của request**; nếu muốn bảo vệ job version khi POST tới resource con, cần hợp đồng và kiểm tra riêng.

## 5. Race giữa hủy và worker: chỉ kiểm tra cờ là chưa đủ

Hủy và bắt đầu thực thi có thể đến **đồng thời**, thậm chí trên nhiều instance. Nếu dùng biến `cancelled` trong bộ nhớ JVM, mỗi instance có trạng thái khác nhau; nếu chỉ `SELECT` rồi `UPDATE` không điều kiện, cả hai phía có thể nghĩ mình thắng.

### 5.1. Claim và hủy khi còn QUEUED

Hai thay đổi nên được thực hiện **nguyên tử tại storage**:

~~~sql
-- Worker chỉ nhận một job còn đang xếp hàng.
UPDATE jobs
SET status = 'RUNNING', version = version + 1
WHERE id = :jobId
  AND tenant_id = :tenantId
  AND status = 'QUEUED';

-- Cancellation handler có thể kết thúc ngay một job chưa claim.
UPDATE jobs
SET status = 'CANCELLED', version = version + 1
WHERE id = :jobId
  AND tenant_id = :tenantId
  AND status = 'QUEUED';
~~~

Với transaction/locking đúng, **chỉ một cập nhật được áp dụng cho trạng thái QUEUED**. Bên cập nhật sau thấy số hàng bị ảnh hưởng bằng 0 rồi đọc trạng thái mới để quyết định: worker bỏ qua job đã `CANCELLED`; handler ghi `CANCEL_REQUESTED` nếu job đã `RUNNING` và còn có thể dừng.

Lưu ý `WHERE id + tenant_id` chỉ bảo vệ **phạm vi tồn tại**; trước đó handler phải xác định principal có quyền hủy job. Đừng sử dụng `tenant_id` lấy trực tiếp từ body hoặc request header không được xác thực.

### 5.2. Checkpoint và cửa sổ “vừa kiểm tra, vừa thực hiện”

Worker có thể kiểm tra `cancelRequested=false` lúc 10:00:01 rồi ngay sau đó handler đặt cờ hủy. Nếu worker bắt đầu bước gửi email lúc 10:00:02 mà không kiểm tra lại, yêu cầu hủy có thể đến **trước tác dụng phụ** nhưng vẫn không ngăn được nó.

Đối với **tác dụng phụ nằm trong cùng database**, hãy khóa job hoặc dùng một lệnh cập nhật có điều kiện trong transaction **cùng lúc** ghi effect:

~~~text
transaction:
  lock job row
  if status == CANCEL_REQUESTED: stop before effect
  if status != RUNNING: do not process
  write business effect (same database)
  record effect committed and terminal status
commit
~~~

Nếu cancellation handler khóa job trước, nó chuyển trạng thái yêu cầu hủy; worker thấy và dừng. Nếu worker khóa trước, nó ghi effect và trạng thái kết thúc rồi commit; cancellation handler đọc trạng thái mới và báo **quá muộn**. Đây là **điểm tuyến tính hóa (linearization point)**: kết quả phản ánh thứ tự commit, không phụ thuộc thời điểm người dùng nhấn nút.

**Không giữ database transaction/row lock trong suốt cuộc gọi HTTP dài tới payment provider.** Lock đó không bao trùm side effect của provider và có thể gây nghẽn hệ thống. Với hệ thống ngoài, dùng mô hình operation, idempotency và reconciliation ở Mục 6.

### 5.3. Worker dừng có hợp tác, không phải bị giết tùy tiện

Sau khi thấy `CANCEL_REQUESTED`, worker nên dừng ở checkpoint an toàn: trước khi bắt đầu bước mới, giữa các lô dữ liệu, trước khi publish hoặc ghi kết quả cuối. Chỉ kết luận `CANCELLED` khi đã xác nhận các bước còn lại không tiếp tục phát sinh side effect ngoài hợp đồng.

`Future.cancel(true)` hoặc `Thread.interrupt()` trong Java **chỉ yêu cầu ngắt** luồng đang chạy và phụ thuộc code/library có hợp tác xử lý interrupt hay không. Nó **không rollback transaction đã commit**, không thu hồi request đã gửi sang provider, không bảo đảm dừng một worker ở process/pod khác. Hủy process/container cưỡng bức thậm chí làm hệ thống mất bằng chứng về kết quả.

### 5.4. Lease khi worker có thể chạy trùng

Queue thường giao event theo kiểu **at least once**. Sau timeout hoặc crash, hai worker có thể cùng tin mình xử lý job. Dùng lease có hạn, `ownerId`, version/fencing token và kiểm tra token tại các thao tác ghi kết quả. Worker cũ không được ghi đè trạng thái của worker mới.

Tuy nhiên, fencing chỉ bảo vệ hệ thống có **thực sự xác minh token**; không thể khiến một email đã gửi hoặc payment đã capture biến mất. Từng side effect cần business reference/idempotency riêng. **Cancellation và duplicate delivery là hai rủi ro khác nhau** phải cùng được xử lý.

## 6. Khi đã bắt đầu side effect bên ngoài

Giả sử job có chuỗi bước:

~~~text
QUEUED -> dựng báo cáo -> upload file -> gửi email -> SUCCEEDED
~~~

Ở mỗi điểm, chính sách hủy phải trả lời: **có ngăn bước tiếp theo không, đã có effect nào commit, biết chắc hay chưa và phải bù trừ ra sao?**

### 6.1. Ba loại trạng thái của một side effect

| Loại | Bằng chứng | Quyết định |
|---|---|---|
| **Chưa bắt đầu** | Chưa gửi command và đã khóa/ghi checkpoint chặn bước mới | Có thể hủy trước bước |
| **Đã commit** | Provider transaction ID, event receipt, record transaction hoặc artifact công bố | **Không tuyên bố rollback**; nếu cần, tạo bù trừ |
| **Không rõ kết quả** | Command đã gửi, connection timeout, không có response cuối | Chuyển `OUTCOME_UNKNOWN`, đối soát bằng reference/webhook |

**Timeout không chứng minh thất bại.** Nếu payment provider trả timeout sau khi nhận lệnh capture, retry bằng một key mới có thể thu tiền lần hai. Giữ **cùng provider idempotency key** hoặc truy vấn outcome bằng business reference; không tự động phát lệnh đối nghịch khi chưa biết bước đầu đã commit hay chưa.

### 6.2. Dùng outbox/operation và bản ghi từng bước

Một thiết kế lưu **jobs** (status, phase, version, cancelRequested, lease), **job_steps** (type, state, externalReference, committedAt) và **outbox** (eventId, stepId, payload, publishedAt).

Trong một transaction, tạo job/step và outbox; worker công bố ra hệ thống ngoài với **key ổn định theo step**. Khi kết quả đến, lưu reference và trạng thái. Nếu cancel được yêu cầu trong lúc chờ provider, handler **không khẳng định `CANCELLED`** mà đánh dấu cần xác minh, sau đó quyết định bước tiếp theo.

Tránh phát outbox event **ngoài transaction** rồi đánh dấu job `CANCELLED` ngay khi thấy cờ: event có thể đã được consumer nhận. Cũng đừng giả định “xóa outbox row” sẽ thu hồi event đã gửi.

### 6.3. Bù trừ là workflow mới

Sau khi effect commit, chỉ có thể **thực hiện một hành động mới** nếu nghiệp vụ cho phép: refund/void sau payment capture, release inventory reservation, thu hồi file đã công bố hoặc gửi email đính chính. Các bước ấy có quyền, idempotency, trạng thái và lỗi riêng; việc hoàn tiền có thể phát sinh phí, file đã tải xuống không thu hồi được, email đã đến người nhận không thể xóa.

Nếu mới gửi command nhưng provider timeout, lưu `OUTCOME_UNKNOWN` và đối soát bằng business reference. Chỉ sau khi biết effect đã xảy ra hay chưa mới chọn bù trừ hoặc xác nhận hủy. Ví dụ provider email báo “accepted” chưa chắc đồng nghĩa “delivered”: hợp đồng phải xác định milestone nào là điểm không thể hủy.

## 7. Java/Spring Boot: tiếp nhận hủy nguyên tử

Ví dụ dùng **Java 17+, Spring Boot 3, Spring MVC, JPA**; đây là mã minh họa phần cốt lõi, cần bổ sung entity, repository, mapper, exception handler và cấu hình bảo mật để chạy độc lập. Đặc biệt, **cơ chế hàng đợi/outbox** và worker phải có chung nguồn trạng thái bền vững thay vì chỉ chia sẻ biến JVM.

### 7.1. DTO và controller

~~~java
enum JobStatus {
    QUEUED, RUNNING, CANCEL_REQUESTED, CANCELLED,
    SUCCEEDED, PARTIALLY_COMPLETED, FAILED, OUTCOME_UNKNOWN
}

enum CancelStatus {
    ACCEPTED, COMPLETED, TOO_LATE, REJECTED, REQUIRES_RECONCILIATION
}

record CancelJobRequest(@NotBlank String reason) {}

record CancelReceipt(
    UUID id,
    UUID jobId,
    CancelStatus status
) {}

record CancelResult(
    CancelReceipt receipt,
    boolean completedSynchronously
) {}

@RestController
@RequestMapping("/v1/report-jobs/{jobId}/cancellation-requests")
class JobCancellationController {
    private final JobCancellationService service;
    private final ActorFactory actors;

    JobCancellationController(
            JobCancellationService service, ActorFactory actors) {
        this.service = service;
        this.actors = actors;
    }

    @PostMapping
    ResponseEntity<CancelReceipt> cancel(
            @PathVariable UUID jobId,
            @RequestHeader("Idempotency-Key") String key,
            @Valid @RequestBody CancelJobRequest body,
            @AuthenticationPrincipal Jwt jwt) {

        Actor actor = actors.fromVerifiedJwt(jwt);
        CancelResult result = service.requestCancel(
            actor, jobId, key, body.reason()
        );
        URI uri = URI.create(
            "/v1/report-jobs/" + jobId
            + "/cancellation-requests/" + result.receipt().id()
        );

        return ResponseEntity.status(
                result.completedSynchronously()
                    ? HttpStatus.CREATED
                    : HttpStatus.ACCEPTED
            )
            .location(uri)
            .cacheControl(CacheControl.noStore())
            .body(result.receipt());
    }
}
~~~

Controller dùng **UUID**, còn `job-701` phía trên chỉ là ID giả lập. **`ActorFactory` phải dùng JWT đã xác thực**, không tin tenant/role từ body.

**Replay phải trả outcome tiếp nhận ban đầu** (status/Location/body đã lưu). Controller minh họa chưa tự đóng băng response nếu receipt đổi từ `ACCEPTED` sang `COMPLETED`; production cần lưu snapshot kết quả lần đầu. Client dùng **GET cancellation resource** để xem trạng thái mới.

### 7.2. Service ghi yêu cầu hủy và thay đổi trạng thái job

~~~java
@Service
class JobCancellationService {
    private final JobRepository jobs;
    private final CancelRequestRepository requests;
    private final JobPolicy policy;
    private final OutboxRepository outbox;

    // Constructor injection được lược bớt.

    @Transactional
    CancelResult requestCancel(
            Actor actor, UUID jobId, String rawKey, String reason) {

        String key = validateIdempotencyKey(rawKey);
        Job job = jobs.lockVisibleInTenant(
            jobId, actor.validatedTenantId()
        ).orElseThrow(HiddenNotFoundException::new);
        policy.requireCanRequestCancellation(actor, job);

        // Scope: tenant + job + actor + key.
        CancelRequest existing = requests.findByScopeAndKey(
            job.getTenantId(), jobId, actor.id(), key
        );
        if (existing != null) {
            if (!existing.sameOriginalReason(reason)) {
                throw new IdempotencyKeyReusedException(); // 422
            }
            return existing.originalHttpResult();
        }

        boolean immediate;
        if (job.getStatus() == JobStatus.QUEUED) {
            job.setStatus(JobStatus.CANCELLED);
            immediate = true;
        } else if (job.getStatus() == JobStatus.RUNNING) {
            job.setStatus(JobStatus.CANCEL_REQUESTED);
            immediate = false;
        } else {
            // Bao gồm terminal và đã có yêu cầu hủy từ key khác.
            throw new JobCannotBeCancelledException(); // 409
        }

        CancelRequest created = requests.create(
            job, actor, key, reason,
            immediate ? CancelStatus.COMPLETED : CancelStatus.ACCEPTED
        );
        jobs.save(job);
        requests.save(created);
        outbox.enqueueCancellationSignal(job.getId());

        // Transaction commit cả job, receipt và outbox.
        return created.originalHttpResult();
    }
}
~~~

`JobRepository.lockVisibleInTenant` giả định dùng **SELECT ... FOR UPDATE** trong cùng transaction. Mọi luồng **worker claim job, chuyển trạng thái và ghi effect** phải áp dụng khóa/CAS tương thích; nếu chỉ handler hủy dùng lock còn worker ghi tự do, hệ thống vẫn có race.

**Idempotency key cần unique constraint** đúng scope, dù handler đã khóa job để tuần tự hóa request hủy. `sameOriginalReason` tượng trưng cho **fingerprint request chuẩn hóa**, không chỉ so chuỗi khi body có thêm trường.

Nếu job `QUEUED`, cập nhật `CANCELLED` ngay chỉ đúng khi hệ thống **bảo đảm chưa có worker/effect nào claim trước** và nguồn hàng đợi sẽ bỏ qua thông điệp đến muộn. Với job `RUNNING`, đặt `CANCEL_REQUESTED` **không tự hủy thread**; worker phải đọc cờ và dừng an toàn.

### 7.3. Worker kiểm tra trước bước có side effect

~~~java
@Service
class JobStepService {
    private final JobRepository jobs;
    private final ReportRepository reports;
    private final CancelRequestRepository requests;

    @Transactional
    void commitInternalReport(UUID jobId, UUID tenantId, ReportData data) {
        Job job = jobs.lockVisibleInTenant(jobId, tenantId)
            .orElseThrow(JobGoneException::new);

        if (job.getStatus() == JobStatus.CANCEL_REQUESTED) {
            job.setStatus(JobStatus.CANCELLED);
            requests.markAcceptedAsCompleted(jobId);
            return;
        }
        if (job.getStatus() != JobStatus.RUNNING) {
            return; // Worker cũ không được ghi khi job không RUNNING.
        }

        reports.saveReportResult(jobId, data); // Cùng database transaction.
        job.setStatus(JobStatus.SUCCEEDED);
        requests.markAcceptedAsTooLate(jobId);
    }
}
~~~

Đoạn code chỉ minh họa **commit báo cáo trong cùng database**. Nếu báo cáo gồm upload file object storage hay gửi email, `reports.saveReportResult` không thể tự làm toàn bộ side effect ngoài trở nên nguyên tử: cần các bước/operation riêng và đối soát. Việc đánh dấu `TOO_LATE` trong ví dụ là dành cho request hủy đã được chấp nhận nhưng **không kịp ngăn commit**; trường hợp một job chưa có cancellation request thì không có record nào cần đổi.

### 7.4. Response khi quá muộn

Nếu worker đã xác nhận effect và job `SUCCEEDED`, hủy mới bị từ chối:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type":"https://api.example.com/problems/job-already-terminal",
  "title":"Conflict",
  "status":409,
  "code":"JOB_ALREADY_TERMINAL",
  "detail":"Công việc đã hoàn tất; không thể hủy bằng thao tác này."
}
~~~

Nếu user cần **xóa báo cáo đã tạo hoặc hoàn tiền đã thu**, API nên cung cấp **resource/workflow mới** được phân quyền, không tái sử dụng request hủy cũ với lời hứa sai về hoàn tác.

## 8. Bảo mật và quan sát khi hủy job

Người có quyền **xem** job không mặc nhiên có quyền **hủy** nó. Worker hoặc API không được coi việc biết `jobId`/`cancellationId` là bằng chứng được phép thao tác.

- **Xác thực và cách ly tenant:** GET job, POST yêu cầu hủy, GET cancellation request và các resource bù trừ đều kiểm tra principal/tenant từ nguồn đáng tin; dùng 404 trung tính để tránh dò ID ngoài phạm vi.
- **Phân quyền theo hành động:** owner hủy export của mình; manager theo phạm vi; payment job có thể cần approval riêng. Kiểm tra lại cả khi replay key.
- **Không tự ý hủy bằng link:** nếu representation có action `cancel`, đó chỉ là gợi ý UX; endpoint vẫn kiểm tra quyền, trạng thái và race.
- **Chống lạm dụng:** giới hạn tần suất yêu cầu hủy/retry/poll, không để người dùng tạo vô hạn request mới gây tải worker; audit ai hủy, khi nào, lý do và kết quả.
- **Bảo vệ kết quả:** receipt không lộ file URL, email người nhận, provider transaction ID hoặc thông tin của tenant khác; khi cần xem chi tiết đối soát, yêu cầu quyền riêng.

Theo dõi `jobId`, `cancelRequestId`, phase, thời điểm commit, provider outcome, `TOO_LATE`, **cancellation latency**, job `CANCEL_REQUESTED` tồn đọng, `OUTCOME_UNKNOWN` quá hạn và lỗi bù trừ. Đặt cảnh báo; không log token hay dữ liệu nhạy cảm.

## 9. Kiểm thử các điểm tranh chấp thực tế

| Ca | Điều kiện | Điều cần xác nhận |
|---|---|---|
| T01 | Hủy trước khi worker claim | Job `CANCELLED`, worker không tạo effect |
| T02 | Worker claim và hủy đến đồng thời | Có một thứ tự commit xác định; không có cả “hủy chắc chắn” và effect mới |
| T03 | Job RUNNING, hủy trước checkpoint | Worker thấy cờ, dừng an toàn, receipt `COMPLETED` |
| T04 | Effect đã commit trước khi hủy | Job vẫn phản ánh kết quả thật, request `TOO_LATE` hoặc 409 |
| T05 | Provider timeout ngay sau khi đã nhận capture/email | `OUTCOME_UNKNOWN`, đối soát; không gửi lại với key mới |
| T06 | Hai worker xử lý trùng event, một worker mất lease | Fencing/idempotency ngăn kết quả ghi trùng |
| T07 | Retry cùng key sau khi mất HTTP response | Trả kết quả request cũ; không tạo cancellation request mới |
| T08 | Cùng key, reason/payload khác | Lỗi fingerprint; không thay đổi job |
| T09 | Tenant khác gửi jobId hoặc cancellationId | 404/ẩn theo policy; không làm lộ trạng thái |
| T10 | Actor chỉ có quyền xem nhưng POST hủy | 403; job không bị sửa |
| T11 | Cleanup artifact thất bại sau khi đã dừng worker | Không tuyên bố cleanup hoàn tất; retry/giám sát |
| T12 | Cancellation được nhận, worker crash rồi chạy lại | Trạng thái/cờ hủy bền vững, không chạy tiếp bước không được phép |

### MockMvc: quyền và job đã kết thúc

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class JobCancellationApiTest {
    @Autowired MockMvc mvc;

    UUID finishedJobId; // Fixture: SUCCEEDED ở tenant-a

    @Test
    void terminalJobRejectsNewCancellation() throws Exception {
        mvc.perform(post(
                "/v1/report-jobs/{id}/cancellation-requests",
                finishedJobId
            )
            .with(jwt().jwt(j -> j.claim("tenant_id", "tenant-a")))
            .header("Idempotency-Key", "\"new-intent-test\"")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"reason\":\"USER_REQUESTED\"}"))
            .andExpect(status().isConflict())
            .andExpect(jsonPath("$.code").value("JOB_ALREADY_TERMINAL"));
    }

    @Test
    void otherTenantCannotCancel() throws Exception {
        mvc.perform(post(
                "/v1/report-jobs/{id}/cancellation-requests",
                finishedJobId
            )
            .with(jwt().jwt(j -> j.claim("tenant_id", "tenant-b")))
            .header("Idempotency-Key", "\"another-test\"")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"reason\":\"USER_REQUESTED\"}"))
            .andExpect(status().isNotFound());
    }
}
~~~

Đây là **test minh họa**, cần fixture, quyền `cancel` thích hợp, các import và ProblemDetail mapper thực tế. `jwt()` của Spring Security Test không tự kiểm chứng chữ ký/issuer/audience token thật; cần thêm security integration test riêng. Test song song T02/T06 phải chạy trên **database và worker/queue gần production**, dùng barrier/fault injection ở đúng điểm claim/commit; một MockMvc test tuần tự không chứng minh được chống race.

## 10. Bài tập và checklist

**Bài tập:** job tạo hóa đơn gồm ba bước: (1) tính toán, (2) capture payment qua provider, (3) gửi email. Lập chính sách hủy nếu request đến **trước bước 1**, **đang gọi bước 2**, và **sau khi email được nhận**.

**Lời giải tham khảo:** trước khi claim, hủy nguyên tử job `QUEUED`, không bắt đầu bước nào; nếu bước tính toán đã chạy thì dừng ở checkpoint an toàn. Trong khi gọi provider, ghi `CANCEL_REQUESTED` nhưng **không tuyên bố CANCELLED**; nếu kết quả không rõ, chuyển `OUTCOME_UNKNOWN` và đối soát bằng reference/idempotency key. Nếu đã capture, cần refund/void theo một workflow riêng khi nghiệp vụ cho phép. Nếu email đã được provider nhận, không thể “thu hồi” email bằng việc xóa job; ghi nhận outcome thực và có thể gửi thông báo đính chính.

**Checklist trước triển khai:**

- [ ] Hợp đồng phân biệt **request hủy đã nhận** và **job thực sự đã dừng**.
- [ ] Có trạng thái `QUEUED`/`RUNNING`/`CANCEL_REQUESTED`/terminal và quy tắc chuyển nguyên tử.
- [ ] Worker kiểm tra cờ hủy tại checkpoint; không coi interrupt là rollback.
- [ ] Bước có effect đã xác định điểm commit và cách nhận biết kết quả **unknown**.
- [ ] Có idempotency cho request hủy và cho external side effect; retry không tạo tác dụng phụ mới.
- [ ] Có outbox, lease/fencing, reconciliation và bù trừ khi kiến trúc cần.
- [ ] HTTP `202/201/200/409/401/403/404` và Problem Details được tài liệu hóa; `Location` dẫn tới resource theo dõi.
- [ ] Phân quyền hủy khác quyền đọc, cách ly tenant và audit đầy đủ.
- [ ] Test race claim-vs-cancel, crash, timeout provider, replay, cross-tenant và cleanup lỗi.

**Tài liệu đọc thêm:** [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110) (202, POST, GET, preconditions); [RFC 9457 — Problem Details](https://www.rfc-editor.org/rfc/rfc9457); [OpenAPI 3.1](https://spec.openapis.org/oas/v3.1.0).

**Kết luận:** hủy job bất đồng bộ là một **giao thức phối hợp trạng thái** giữa client, API, worker và các hệ thống có tác dụng phụ. Thiết kế đúng không hứa rollback những gì đã xảy ra; nó cho biết chính xác **đã nhận yêu cầu, đã dừng, quá muộn hay chưa rõ kết quả**, đồng thời ngăn bước mới bằng transaction/checkpoint và phục hồi bằng đối soát hoặc bù trừ khi cần.
