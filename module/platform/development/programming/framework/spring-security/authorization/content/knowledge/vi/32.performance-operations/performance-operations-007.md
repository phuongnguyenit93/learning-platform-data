# Kiểm tra quyền trong tác vụ nền với danh tính thực thi rõ ràng

## 1. Vấn đề và mục tiêu

Trong ứng dụng Spring Security, một yêu cầu HTTP thường có danh tính rõ ràng: ai đã xác thực, có authority nào, và được phép thao tác trên bản ghi nào. Khi công việc được chuyển sang `@Async`, thread pool, `@Scheduled`, queue, batch processor hoặc worker ở một tiến trình khác, các giả định đó thay đổi. Một tác vụ vẫn có thể chạy **sau khi HTTP request kết thúc, trên thread/máy khác, dưới tài khoản dịch vụ**, hoặc sau khi người yêu cầu đã mất quyền.

Bài học tập trung vào nguyên tắc: **mỗi tác vụ nền phải có danh tính thực thi được xác định và kiểm chứng, đồng thời phải giữ được danh tính người khởi tạo để đánh giá quyền dữ liệu.** Không đánh đồng “service có quyền chạy worker” với “mọi người dùng có quyền yêu cầu worker thao tác trên mọi dữ liệu”.

Ví dụ xuyên suốt: Alice thuộc tenant A và được xuất báo cáo tenant A; Bob thuộc tenant B. Alice gửi yêu cầu xuất tài liệu A-101, API tạo job `J-100`. Worker dùng service identity `report-worker` để đọc dữ liệu và tạo file. Nếu worker chỉ dựa vào quyền rộng của service mà không kiểm người yêu cầu, Alice có thể gửi `documentId=B-202` hoặc thay tenant trong payload rồi lấy dữ liệu B. Nếu quyền của Alice bị thu hồi giữa khi tạo job và khi chạy, việc chạy theo “quyền cũ” cũng có thể vi phạm chính sách.

**Mục tiêu sau bài học:**

- Xác định được **initiator/requester**, **execution principal**, **data subject/tenant** và hành động của job; quyết định quyền phù hợp ở các mốc tạo job, chạy job và lấy kết quả.
- Hiểu khi nào `SecurityContext` mất qua ranh giới thread; dùng đúng công cụ Spring Security để chuyển context cho tác vụ ngắn, biết giới hạn của cơ chế này.
- Thiết kế queue/batch/scheduler với danh tính service rõ ràng, dấu vết “on behalf of”, kiểm quyền hiện hành, scope dữ liệu, thay đổi membership, retry và cancellation.
- Kiểm thử cả allow/deny, side effects, audit và tính cô lập dữ liệu của worker trong điều kiện concurrency.

## 2. Bốn thực thể khác nhau trong một job

| Thành phần | Câu hỏi phải trả lời | Ví dụ | Tác dụng bảo mật |
| --- | --- | --- | --- |
| **Requester/initiator** | Ai yêu cầu công việc? | `user:alice` | Chứng minh quyền tạo yêu cầu và quyền sử dụng dữ liệu; phục vụ audit |
| **Execution principal** | Worker chạy dưới danh tính nào? | `service:report-worker` | Chứng minh quyền gọi dịch vụ/hạ tầng cần thiết; không tự nhận quyền trên mọi tenant |
| **Resource/data scope** | Bản ghi, tenant, cột và bản xuất thuộc phạm vi nào? | `tenant:A`, `document:A-101` | Ràng buộc object-level authorization và tránh truy cập chéo tenant |
| **Job identity** | Công việc nào, trạng thái nào, ai được xem/kết quả? | `job:J-100`, owner Alice | Ràng buộc read/cancel/retry/download và truy vết một lần thực thi |

Cần phân biệt:

- **Authentication**: xác minh user token tại API hoặc service credential tại worker.
- **Functional authorization**: ví dụ user có `SCOPE_report.export` để tạo job; service có `report-job:execute` để thực thi loại job.
- **Object/data authorization**: actor có được đọc những tài liệu/cột/tenant được xuất không?
- **Delegation/on-behalf-of**: service đang làm công việc cho Alice trên dữ liệu Alice có quyền, với contract rõ về phạm vi và thời hạn. Một service token không tự biến thành user token.
- **Audit identity**: log đủ `requestedBy`, `executedBy`, `jobId`, `tenantId`, `action`, `decision`, `policyVersion` để điều tra; không ghi access token hoặc credentials thô.

Một job có thể có **hai điều kiện đồng thời**: “worker hợp lệ được phép xử lý loại job này” **VÀ** “requester hiện được phép thực hiện thao tác trên đúng dữ liệu”. Nếu thiếu một điều kiện, job phải dừng an toàn. Có thể có job “do hệ thống chủ động” không có requester người dùng; lúc đó phải khai báo loại job và service identity với phạm vi riêng, không giả mạo một user ngẫu nhiên.

## 3. Ranh giới thread: `SecurityContextHolder` không tự đi theo công việc

Trong cấu hình Servlet thông thường, `SecurityContextHolder` lưu context theo **thread hiện tại**, mặc định sử dụng chiến lược kiểu `ThreadLocal`. Authentication của HTTP request vì thế không tự hiện diện trong worker thread. Một lời gọi `@Async` hoặc `CompletableFuture.supplyAsync` có thể nhận context rỗng, trừ khi có cơ chế truyền context rõ ràng.

Các trạng thái có thể xảy ra:

1. **Không truyền context:** `SecurityContextHolder.getContext().getAuthentication()` trong thread worker thường là `null`. Một method có `@PreAuthorize` cần authentication sẽ từ chối; code tự “bỏ qua kiểm tra nếu null” tạo lỗ hổng.
2. **Truyền context đúng cho tác vụ ngắn:** Spring Security cung cấp `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextExecutor`, `DelegatingSecurityContextAsyncTaskExecutor` và các biến thể; chúng gắn context khi thực thi delegate và dọn/restores context theo cơ chế wrapper, tránh để danh tính của task này dính vào task sau.
3. **Truyền nhầm context hoặc giữ quá lâu:** dùng một `SecurityContext` cố định của admin cho **mọi task**, hoặc lưu context của người dùng nhiều giờ rồi khôi phục khi chạy, có thể tạo quyền quá rộng, quyền đã hết hiệu lực và rò dữ liệu giữa request.
4. **`@Scheduled`/message worker:** thường không có request user hiện hành. Không giả định một principal của HTTP request sẽ xuất hiện; phải thiết kế explicit execution identity và policy.

> `SecurityContext` là ngữ cảnh bảo mật trong một lần thực thi. Nó **không** phải hồ sơ ủy quyền bền vững cho queue job, không phải chứng cứ quyền mãi mãi và không phải nơi để lưu toàn bộ state nghiệp vụ.

### Khi nào truyền `SecurityContext` là hợp lý?

Tác vụ `@Async` rất ngắn, chạy cùng tiến trình và cần gọi method security theo danh tính hiện hành có thể sử dụng wrapper. Điều kiện là caller thực sự được phép submit, ranh giới thời gian được kiểm soát, và worker vẫn kiểm quyền đối tượng. Nếu job phải sống qua restart, message broker, retry lâu hoặc chạy từ máy khác, **truyền object `SecurityContext` không phù hợp**; queue chỉ giữ metadata định danh/bảo mật tối thiểu và rehydrate policy từ nguồn server tin cậy lúc thực thi.

## 4. Ví dụ `@Async` ngắn: propagation đúng nhưng không phải toàn bộ chính sách

Đoạn cấu hình sau là **mảnh Java/Spring cho Servlet Spring Security 6.x/7.x**, cần các dependency spring-context/spring-task và spring-security. Nó không là chương trình Java thuần độc lập. Wrapper lấy context của **thread submit task** khi enqueue vào executor:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor;

@Configuration
@EnableAsync
class AsyncSecurityConfiguration {
    @Bean("contextAwareExecutor")
    AsyncTaskExecutor contextAwareExecutor() {
        ThreadPoolTaskExecutor delegate = new ThreadPoolTaskExecutor();
        delegate.setCorePoolSize(4);
        delegate.setMaxPoolSize(8);
        delegate.setQueueCapacity(64);
        delegate.setThreadNamePrefix("report-short-");
        delegate.initialize();

        return new DelegatingSecurityContextAsyncTaskExecutor(delegate);
    }
}
~~~

Một method khác, gọi qua bean do Spring quản lý:

~~~java
@Service
class QuickPreviewService {
    private final DocumentPolicy policy;
    private final ReportRenderer renderer;

    QuickPreviewService(DocumentPolicy policy, ReportRenderer renderer) {
        this.policy = policy;
        this.renderer = renderer;
    }

    @Async("contextAwareExecutor")
    @PreAuthorize("hasAuthority('SCOPE_report.preview')")
    public CompletableFuture<ReportPreview> preview(long documentId) {
        Authentication actor =
            SecurityContextHolder.getContext().getAuthentication();

        policy.requireCanPreview(actor, documentId);
        return CompletableFuture.completedFuture(renderer.preview(documentId));
    }
}
~~~

Cần các import `@Service`, `@Async`, `@PreAuthorize`, `CompletableFuture`, `Authentication`, `SecurityContextHolder` cùng collaborator theo dự án. **Đây chỉ là ví dụ tích hợp**, và `@PreAuthorize` có thể được áp dụng tại ranh giới khác trong chuỗi interceptor khi kết hợp async; phải kiểm thử bằng Spring context thực để xác định chính xác thời điểm policy chạy. Hãy kiểm quyền ở **endpoint submit** để phản hồi từ chối ngay, đồng thời **kiểm lại** khi task bắt đầu nếu chính sách yêu cầu; không dựa hoàn toàn vào thứ tự annotation.

Những điều cần kiểm chứng:

- Khi submit task bởi Alice, task quan sát Alice chứ không phải principal từ request Bob khác dùng cùng pool.
- Khi task kết thúc hoặc ném exception, context không tồn tại trên thread được tái sử dụng cho task sau.
- `@Async` chỉ có tác dụng khi đi qua Spring proxy; `this.preview(...)`/self-invocation có thể không async và có thể bỏ qua một số interceptor.
- Nếu task được submit trước khi quyền bị thu hồi, context truyền sang vẫn có thể chứa authorities **cũ**; wrapper không tự revalidate revocation.
- Không dùng `SecurityContextHolder.MODE_INHERITABLETHREADLOCAL` như giải pháp mặc định cho thread pool: thread sống lâu và được tái sử dụng có thể giữ context ngoài dự kiến.
- Không đưa authentication bí mật hoặc toàn bộ serialized `SecurityContext` vào queue, database, Kafka message hay log.

`DelegatingSecurityContextExecutor` cũng có constructor nhận một `SecurityContext` **cố định**. Chế độ đó có trường hợp dùng riêng cho tác vụ hệ thống được kiểm soát, nhưng không được dùng cho một executor dùng chung rồi vô tình chạy tất cả tác vụ “on behalf of Alice” dưới tài khoản đặc quyền.

## 5. Queue job bền vững: mô hình danh tính tách bạch

Với tác vụ xuất báo cáo bất đồng bộ, cách an toàn là lưu job metadata **ở phía server** ngay khi đã xác thực yêu cầu. Một schema gợi ý:

~~~json
{
  "jobId": "J-100",
  "jobType": "REPORT_EXPORT",
  "requestedBy": "user:alice",
  "requestedTenant": "tenant:A",
  "resourceIds": ["A-101"],
  "requestedAction": "report.export",
  "createdAt": "2026-11-06T07:00:00Z",
  "expiresAt": "2026-11-06T08:00:00Z",
  "authorizationMode": "RECHECK_AT_EXECUTION",
  "status": "PENDING"
}
~~~

Đây là ví dụ schema nghiệp vụ, **không phải token hoặc thông tin cấp quyền tự chứng thực**. `jobId`, `requestedBy`, `requestedTenant`, `jobType` và resource selection phải đến từ record/job store được bảo vệ; mọi field ảnh hưởng quyền trong payload public phải được xác minh trước khi lưu. Trong queue message, có thể chỉ mang `jobId` và version để worker nạp lại record tin cậy. Nếu chuyển metadata giữa các trust boundary, cần xác thực nguồn message, integrity, tenant routing và chống sửa/replay.

Không lưu `Authentication`, JWT access token, refresh token, password hay quyền “snapshot” vào job rồi mặc nhiên tin lại ở thời điểm thực thi. Một snapshot quyền chỉ được dùng nếu hợp đồng nghiệp vụ **chủ động** cho phép, có time bound/audit/giới hạn quyền cụ thể. Với xuất dữ liệu và thao tác có tác động lớn, chính sách thực tiễn thường là **recheck tại lúc chạy** và trước khi giao kết quả.

### Luồng từ HTTP đến kết quả

~~~mermaid
flowchart TD
    A[HTTP: Alice yêu cầu export] --> B[Validate token và kiểm quyền submit]
    B --> C{Alice được export tài liệu A-101?}
    C -->|Không| X[Từ chối, không tạo job]
    C -->|Có| D[Lưu job có requester, tenant, action, scope]
    D --> E[Queue chỉ chứa ID/version, worker xác thực nguồn]
    E --> F[Service identity được xác thực: report-worker]
    F --> G{Service được execute job type?}
    G -->|Không| Y[Fail closed, audit]
    G -->|Có| H[Nạp lại requester và policy hiện hành]
    H --> I{Requester còn quyền trên dữ liệu?}
    I -->|Không| Z[DENIED/CANCELLED, không xuất file]
    I -->|Có| J[Query dữ liệu có ràng buộc scope]
    J --> K[Kiểm tra nội dung file, lưu kết quả an toàn]
    K --> L[Download: kiểm requester/quyền hiện hành]
~~~

**Điểm quan trọng:** quyền tạo job, quyền chạy job và quyền tải output là **ba lần kiểm** có mục đích khác nhau. Không dùng việc API trả `202 Accepted` làm bằng chứng rằng export cuối cùng được phép. `202` thường chỉ biểu thị yêu cầu đã được chấp nhận để xử lý bất đồng bộ, không bảo đảm thành công.

## 6. Chính sách quyền tại từng thời điểm

### 6.1. Trước khi ghi job (submit)

- Xác thực requester và đúng `issuer`/`audience` cho API. Kiểm functional authority (`SCOPE_report.export`) và policy đọc/xuất từng tài nguyên theo tenant, organization, owner, ACL.
- Chuẩn hóa/cố định danh sách `resourceIds` hoặc bộ lọc đã được duyệt; không tin tenant/owner từ header `X-Tenant` hoặc JSON body. Với filter động như “export toàn bộ tenant”, ghi rõ bộ lọc được cho phép và tenant server đã xác minh.
- Áp quota/size và rate limit trước khi enqueue để tránh người dùng hợp lệ tạo hàng triệu công việc làm nghẽn worker; quota không thay thế authorization.
- Không cho caller lựa chọn `runAs=admin`, `executorRole=superuser` hay service identity trong payload.
- Lưu audit `requestedBy`, thời điểm, scope đã yêu cầu, decision, policy source/version và correlation ID; tránh lưu PII/file bí mật vào message log.

### 6.2. Khi worker nhận công việc (execute)

- Worker xác thực **execution principal** bằng cơ chế nội bộ phù hợp: service account, workload identity/mTLS hoặc token machine-to-machine có audience rõ. Nếu hạ tầng không cung cấp principal framework, ít nhất job handler phải có danh tính service được cấu hình đáng tin và ràng buộc quyền thực thi.
- Kiểm service có quyền cho `jobType` đang chạy; một worker chỉ làm báo cáo không được tự thực hiện thao tác quản trị người dùng.
- Nạp job từ kho bảo vệ, kiểm trạng thái `PENDING/RETRY`, chữ ký/nguồn message, deadline, tenant, version/idempotency token. Không coi message queue là nguồn authority.
- Nạp lại requester theo `requestedBy`; xác minh account còn hoạt động, membership còn hiệu lực, scope/tài nguyên còn thuộc quyền người đó, policy version và giới hạn khác. Nếu không còn quyền, từ chối/đánh dấu denied; không “fallback” sang quyền của service.
- Đọc/ghi dữ liệu qua query có predicate scope trong transaction phù hợp; với export lớn, kiểm phạm vi cho từng batch/cursor và tránh query toàn bảng rồi filter sau khi dữ liệu nhạy cảm đã rời DB.
- Nếu xử lý quá lâu, xác định ngưỡng checkpoint/reauthorization theo policy; một quyết định tại giây đầu có thể không đủ cho job chạy hàng giờ.

### 6.3. Khi giao kết quả (download, retry, cancel)

- Chủ sở hữu job không luôn là người duy nhất được tải; phải có chính sách cụ thể cho admin được ủy quyền, nhóm chia sẻ, trợ lý của owner... Không suy từ việc biết `jobId` hay URL.
- Download endpoint phải kiểm quyền `view/download` đối với **job + file + dữ liệu thực tế**, kể cả khi file được tạo trước lúc thu hồi quyền. Với signed URL, giới hạn thời hạn/audience và quy trình vô hiệu hóa theo mức nhạy cảm.
- Retry không tự nâng quyền: chạy lại đúng metadata được xác minh; recheck requester, không đổi tenant bằng retry payload. Cancel/restore/purge cũng phải kiểm actor và job scope.
- Xóa tệp tạm khi job bị từ chối/thất bại; bảo đảm file từng được tạo không thể tải nhờ URL cũ nếu policy yêu cầu thu hồi.

### 6.4. Nếu job do hệ thống chủ động

`@Scheduled` tổng hợp hóa đơn lúc nửa đêm có thể **không có requester là user**. Xác định rõ `origin=SYSTEM_SCHEDULE` và `executedBy=service:billing-scheduler` với whitelist loại job/tenant/data policy chuyên biệt. Chạy dưới principal của service đã xác thực và ủy quyền, không dùng account “admin” gắn thủ công chỉ để vượt method security. Hệ thống có thể có quyền batch liên tenant, nhưng phải được cấp và audit rõ; tenant routing không thể do tham số không tin cậy tự quyết định.

## 7. Mẫu service Spring: phân chia quyền submit và execute

Các đoạn sau là **khung Spring Boot/Spring Security cần repository/policy/job store thật**, nhằm mô tả vị trí kiểm soát; không phải mã độc lập.

Submit từ request có principal hợp lệ:

~~~java
@Service
class ExportJobSubmission {
    private final ExportPolicy exportPolicy;
    private final ExportJobRepository jobs;

    ExportJobSubmission(ExportPolicy exportPolicy, ExportJobRepository jobs) {
        this.exportPolicy = exportPolicy;
        this.jobs = jobs;
    }

    @PreAuthorize("hasAuthority('SCOPE_report.export')")
    @Transactional
    public String submit(Authentication actor, String documentId) {
        // Trả về tenant đã xác minh từ server; KHÔNG dùng tenant client cung cấp.
        String tenant = exportPolicy.requireCanExport(actor, documentId);

        ExportJob job = ExportJob.pending(
            actor.getName(), tenant, documentId, "REPORT_EXPORT");
        jobs.save(job);
        return job.getId();
    }
}
~~~

Ở controller, truyền `Authentication` lấy từ Spring Security sau khi đã xác thực. `@PreAuthorize` ở đây kiểm authority chức năng; `requireCanExport` kiểm resource/tenant. Ngoài job row cần outbox/transactional message publishing nếu muốn tránh tình huống commit database thành công nhưng message gửi queue thất bại, hoặc ngược lại. Không đưa `actor.getAuthorities()` đã có từ lúc submit làm nguồn quyền không đổi cho worker sau này.

Worker với service identity:

~~~java
@Service
class ExportJobRunner {
    private final ExportJobRepository jobs;
    private final ExportPolicy policy;
    private final DocumentRepository documents;
    private final ExportStorage storage;

    ExportJobRunner(ExportJobRepository jobs, ExportPolicy policy,
                    DocumentRepository documents, ExportStorage storage) {
        this.jobs = jobs;
        this.policy = policy;
        this.documents = documents;
        this.storage = storage;
    }

    // Được gọi qua một service adapter đã xác thực workload identity,
    // hoặc bởi scheduler nội bộ được cấp service identity đã cấu hình.
    public void execute(String jobId, ExecutionIdentity executor) {
        policy.requireCanExecute(executor, "REPORT_EXPORT");

        ExportJob job = jobs.lockPending(jobId);
        if (!"REPORT_EXPORT".equals(job.getType())) {
            throw new AccessDeniedException("Wrong job type");
        }

        // Chính sách recheck nạp membership/role hiện hành của requester.
        policy.requireCanStillExport(job.getRequestedBy(),
                                     job.getTenantId(),
                                     job.getDocumentId());

        // Truy vấn bắt buộc ràng buộc scope đã xác minh.
        var doc = documents.findByIdAndTenantId(
            job.getDocumentId(), job.getTenantId()
        ).orElseThrow(() -> new AccessDeniedException("Out of scope"));

        storage.writeAuthorized(job.getId(), doc);
        jobs.markCompleted(job.getId());
    }
}
~~~

Cần xử lý transaction/outbox, lock lease, tính idempotent và lỗi file/DB ở bản thật. `ExecutionIdentity` phải được tạo bởi thành phần xác thực service tin cậy, không từ trường `executor` trong queue body. `lockPending` và `markCompleted` cần ràng buộc owner/state/version để hai worker không đồng thời xuất cùng job. Không dùng một transaction DB dài xuyên toàn bộ upload file khi điều đó gây giữ lock kéo dài; thay bằng lease + state machine với kết quả tạm và commit/cleanup thích hợp.

Nếu đặt `@PreAuthorize` trên worker, method phải được gọi **qua proxy Spring** và với `Authentication` tương ứng hiện diện. Trong queue bền vững, policy nhận `ExecutionIdentity` tường minh thường rõ ràng hơn việc giả mạo `Authentication` của người dùng trong `SecurityContextHolder`. Có thể kết hợp method security cho service identity và policy nghiệp vụ cho `requestedBy`, nhưng phải xác định cái nào quyết định quyền nào.

### Không tái sử dụng context bằng tay trên thread pool

Anti-pattern dễ gây rò danh tính:

~~~java
// Nguy hiểm nếu không restore/clear context và revalidate quyền.
SecurityContextHolder.getContext().setAuthentication(userAuthentication);
workerPool.execute(() -> writeDataWithoutObjectCheck(job));
~~~

Lệnh `setAuthentication(...)` ở **thread request** không chứng minh task chạy trên thread worker sẽ nhận context đó; nếu code tự gắn context trong worker mà không có `finally` restore/clear, một pooled thread có thể “dính” danh tính sang task tiếp theo. Dùng executor wrapper cho tác vụ ngắn, hoặc explicit job execution identity và policy cho job lâu dài.

Nếu thật sự cần context tạm ở một adapter nội bộ, nguyên tắc cốt lõi là:

~~~java
SecurityContext previous = SecurityContextHolder.getContext();
try {
    SecurityContext next = SecurityContextHolder.createEmptyContext();
    next.setAuthentication(verifiedServiceAuthentication);
    SecurityContextHolder.setContext(next);
    invokeSecuredService();
} finally {
    SecurityContextHolder.setContext(previous);
}
~~~

Đây là **mảnh mã minh họa**, không hướng dẫn tự dựng một service authentication giả hợp lệ. `verifiedServiceAuthentication` phải đến từ authentication path tin cậy của worker. Nên dùng cơ chế wrapper chính thức khi phù hợp vì code tự quản lý context dễ sai trong môi trường concurrent. Đặc biệt tránh chia sẻ/mutate cùng một `SecurityContext` giữa nhiều thread.

## 8. Java 17 độc lập: job không nhận quyền từ executor

Chương trình dưới đây mô phỏng API enqueue, queue store, service identity và worker kiểm lại requester. Nó **không sử dụng Spring Security**, nhằm kiểm chứng bất biến quyền bằng Java 17+ trước khi tích hợp vào Spring. Lưu thành `BackgroundAuthorizationDemo.java`; chạy `javac BackgroundAuthorizationDemo.java` rồi `java BackgroundAuthorizationDemo`.

~~~java
import java.util.*;

public class BackgroundAuthorizationDemo {
    record Actor(String id, String tenant, boolean active,
                 Set<String> permissions) {}
    record Document(String id, String tenant) {}
    record Job(long id, String requestedBy, String tenant,
               String documentId) {}

    static final class Denied extends RuntimeException {}

    static final class Platform {
        final Map<String, Actor> users = new HashMap<>();
        final Map<String, Document> documents = new HashMap<>();
        final Map<Long, Job> jobs = new LinkedHashMap<>();
        long nextId = 1;

        private boolean canExport(Actor actor, Document doc) {
            return actor != null
                && actor.active()
                && actor.permissions().contains("report.export")
                && doc != null
                && actor.tenant().equals(doc.tenant());
        }

        Job enqueue(String requesterId, String documentId) {
            Actor actor = users.get(requesterId);
            Document doc = documents.get(documentId);
            if (!canExport(actor, doc)) throw new Denied();

            Job job = new Job(nextId++, actor.id(),
                              actor.tenant(), documentId);
            jobs.put(job.id(), job);
            return job;
        }

        void run(long jobId, String serviceIdentity) {
            // Danh tính thực thi phải được xác thực bởi worker adapter.
            if (!"service:report-worker".equals(serviceIdentity)) {
                throw new Denied();
            }

            Job job = jobs.get(jobId);
            if (job == null) throw new Denied();
            Actor current = users.get(job.requestedBy());
            Document doc = documents.get(job.documentId());

            // Không cấp quyền dữ liệu theo quyền rộng của service.
            if (!canExport(current, doc)
                    || !current.tenant().equals(job.tenant())) {
                throw new Denied();
            }

            System.out.println("executed job=" + job.id()
                + " by=" + serviceIdentity
                + " for=" + job.requestedBy());
        }
    }

    static void expectDenied(Runnable action) {
        try {
            action.run();
        } catch (Denied expected) {
            return;
        }
        throw new AssertionError("Expected access denial");
    }

    public static void main(String[] args) {
        Platform p = new Platform();
        p.users.put("alice", new Actor(
            "alice", "A", true, Set.of("report.export")));
        p.documents.put("A-101", new Document("A-101", "A"));
        p.documents.put("B-202", new Document("B-202", "B"));

        Job job = p.enqueue("alice", "A-101");
        System.out.println("queued job=" + job.id());

        expectDenied(() -> p.enqueue("alice", "B-202"));
        System.out.println("denied cross-tenant submit");

        // Giả lập thu hồi quyền sau khi job đã được lưu.
        p.users.put("alice", new Actor(
            "alice", "A", true, Set.of()));
        expectDenied(() -> p.run(job.id(), "service:report-worker"));
        System.out.println("denied revoked permission");

        // Worker không chấp nhận một danh tính thực thi tự chọn.
        expectDenied(() -> p.run(job.id(), "service:untrusted"));
        System.out.println("denied wrong executor");

        p.users.put("alice", new Actor(
            "alice", "A", true, Set.of("report.export")));
        p.run(job.id(), "service:report-worker");
    }
}
~~~

Kết quả chuẩn:

~~~text
queued job=1
denied cross-tenant submit
denied revoked permission
denied wrong executor
executed job=1 by=service:report-worker for=alice
~~~

Từ ví dụ, hãy nhận ra: enqueue được chấp nhận **không đảm bảo** worker chạy được; thu hồi quyền phải ảnh hưởng lần thực thi khi policy chọn recheck. `service:report-worker` chỉ chứng minh worker hợp lệ trong ví dụ, không thay người dùng. Trong môi trường thật, chuỗi tên service là không đủ để xác thực: cần mTLS/workload identity/credential được xác minh bởi adapter; job phải có idempotency, state transition và kiểm quyền tải kết quả.

## 9. Mẫu SQL ràng buộc dữ liệu và trạng thái job

Không truy vấn bản ghi theo mỗi `documentId` rồi dựa vào việc worker là service đáng tin để bỏ qua scope. Ví dụ:

~~~sql
SELECT d.id, d.tenant_id, d.content
FROM documents AS d
WHERE d.id = :documentId
  AND d.tenant_id = :authorizedTenant;
~~~

`:authorizedTenant` phải là tenant đã xác minh cho requester **tại thời điểm policy áp dụng**. Nếu ứng dụng có row-level security, ACL hoặc shared workspace, predicate phải phản ánh đầy đủ chính sách, không coi equality tenant là đủ. Với export dữ liệu lớn, áp cùng predicate vào `COUNT`, pagination/cursor, join, file streaming và các job con.

Để một job không bị hai worker cùng claim, có thể dùng state transition có điều kiện, ví dụ minh họa SQL khái niệm:

~~~sql
UPDATE export_jobs
SET status = 'RUNNING',
    claimed_by = :verifiedServiceId,
    lease_until = :leaseDeadline
WHERE id = :jobId
  AND status IN ('PENDING', 'RETRY')
  AND tenant_id = :verifiedJobTenant;
~~~

Kiểm **số hàng bị cập nhật** bằng 1 trước khi xử lý; nếu 0 thì job không được claim. Cần thiết kế thêm lease expiry, attempts, isolation và cơ chế tránh hai worker tái chiếm lease cũ khi một worker vẫn chạy. `claimed_by` phục vụ truy vết service, không chứng minh requester có quyền dữ liệu; việc authorize requester vẫn phải tách riêng. Job trạng thái `RUNNING` không nên trở thành giấy phép xuất dữ liệu nếu permission vừa bị thu hồi.

## 10. Hiệu năng, độ bền vận hành và quyền hạn

Bảo vệ job nền không có nghĩa là mỗi hàng dữ liệu phải gọi một API phân quyền từ xa theo cách gây N+1. Cần chọn **đơn vị kiểm** phù hợp:

- **Trước enqueue:** kiểm một lần quyền tạo job, quota và filter.
- **Trước mỗi lần chạy/retry:** kiểm service identity, job integrity, requester, membership, policy hiện hành và resource scope.
- **Tại query/batch:** áp predicate từ server vào DB/search, dùng ACL join/RLS hoặc policy query đã được tối ưu, tránh lọc record sau khi lấy về. Với hàng triệu dòng, kiểm quyền cấp batch/checkpoint và abort khi revoked theo contract.
- **Cache policy:** nếu cache decision “Alice có quyền tenant A”, key phải gắn actor, tenant, action, resource/policy version và thời hạn hợp lệ. Khi thu hồi quyền, invalidation/TTL phải phù hợp tính nhạy cảm; cache hit không tự chứng minh quyền vẫn còn.
- **Retry/backoff:** lỗi authorization nên đưa job sang `DENIED`/`CANCELLED`, không retry vô hạn. Lỗi hạ tầng tạm thời nên có backoff, giới hạn attempts và trạng thái chờ, nhưng **không** fallback sang service-admin để hoàn tất.
- **Concurrency/isolation:** queue partition, thread pool, transaction và job locks không được làm lẫn context tenant A/B; kiểm cả cache, temporary files, report path và output metadata.
- **Backpressure:** quota theo actor/tenant, max concurrent jobs, memory/file size và queue depth giữ cho một actor không làm cạn worker capacity. Rate limit là kiểm tài nguyên, không thay authorization.

### Audit và observability

Mỗi lần enqueue/run/download nên ghi nhận có cấu trúc: `eventType`, `jobId`, `requestedBy`, `executedBy`, `tenantId`, `scope/action`, `decision`, `reasonCode`, `timestamp`, `correlationId` và version policy khi cần. Với scheduler hệ thống, `requestedBy` nên là `SYSTEM` hoặc null có lý do rõ, **không** biến nó thành username người dùng giả.

Metric hữu ích: số job `DENIED_AT_SUBMIT`, `DENIED_AT_EXECUTION`, `REVOKED_DURING_RUN`, `FAILED_AUTH_SERVICE`, thời gian chờ queue, retry rate, stale job và quota throttling. Alert khi tỷ lệ job bị từ chối tăng bất thường hoặc nhiều request đòi truy cập tenant khác. Không đưa token/refresh token/PII vào label metrics hoặc log để tránh rò qua hệ thống quan sát.

## 11. Kiểm thử an toàn đúng ranh giới

### Ma trận test tối thiểu

| Tình huống | Điều cần chứng minh |
| --- | --- |
| Alice có quyền export A, worker hợp lệ | Enqueue thành công; chạy đúng tenant A, output đúng record |
| Alice gửi ID tài liệu B | Từ chối tại submit; không tạo job/không enqueue |
| Alice gửi ID A nhưng đổi tenant trong message | Worker lấy tenant từ job store đã bảo vệ; không xuất B |
| Alice mất `report.export` sau enqueue | Worker recheck và từ chối; không xuất file |
| Alice bị khóa/mất membership khi job pending | Worker từ chối dù job ban đầu đã được chấp nhận |
| Service không có quyền loại job hoặc credential không hợp lệ | Worker từ chối trước khi truy vấn DB; không cấp quyền nhờ user |
| User khác đoán `jobId` hoặc download URL | Không đọc, hủy, retry hoặc tải file ngoài quyền |
| Context A và B chia cùng thread pool | Task B không quan sát principal A; cleanup sau exception |
| Retry sau crash, queue gửi trùng message | Một chuyển trạng thái idempotent; không chạy hai lần hoặc nâng quyền |
| Policy/auth server tạm thời lỗi | Fail closed hoặc hoãn retry có kiểm soát; không export toàn DB |
| Export lớn gồm dữ liệu A/B | Tất cả trang/chunk/row/count chỉ chứa dữ liệu được phép |
| Scheduler hệ thống | Có service identity, job type whitelist và scope hệ thống rõ; không cần giả requester |

### Ba cấp test bổ sung cho nhau

**1. Unit test policy:** đưa `requestedBy`, `executorIdentity`, `action`, `documentId`, `tenantId`, `membership` và `jobStatus` vào hàm policy. Assert allow và deny, đặc biệt “executor có quyền nhưng requester mất quyền”, “requester có quyền nhưng executor không hợp lệ” và “cả hai có quyền chức năng nhưng document ngoài tenant”. Mock dữ liệu nguồn nếu logic policy là đối tượng kiểm; không mock luôn quyết định cần được chứng minh.

**2. Integration test với Spring security/thread pool:** dùng `@SpringBootTest` và executor thật, submit hai task ở hai danh tính khác nhau, xác nhận mỗi task đọc đúng authentication; kiểm cleanup cả khi task ném exception. Dùng `CountDownLatch`/`Future` có timeout để đồng bộ, tránh `Thread.sleep(...)` làm test flaky. Kiểm `@Async` đi qua bean/proxy và method security kích hoạt. Với token kiểm JWT runtime, test thêm decoder/issuer/audience; `jwt()` trong MockMvc có thể dựng authentication mà bỏ qua xác minh token thật.

**3. E2E với broker/storage:** gửi request tạo job thật, để worker nhận bản tin, thay membership trước khi xử lý, xác nhận state transition và DB/file không đổi khi deny. Test job replay, duplicate, download/cancel unauthorized, batch export nhiều trang và retry sau crash. Sử dụng actor A/B fixture cùng ID dữ liệu rõ ràng; mỗi negative test phải có positive control để tránh một hệ thống luôn trả deny nhưng vẫn được xem là pass.

### Khung test minh họa cho Spring

~~~java
@SpringBootTest
class ExportWorkerAuthorizationTest {
    @Autowired ExportJobSubmission submission;
    @Autowired ExportJobRunner runner;
    @Autowired TestFixtures fixtures;

    @Test
    void revocationBetweenSubmitAndExecutionMustDeny() {
        Authentication alice = fixtures.authenticatedAliceWithExport();
        String jobId = submission.submit(alice, "A-101");

        fixtures.revokeExportPermission("alice");

        assertThatThrownBy(() -> runner.execute(
                jobId, fixtures.verifiedReportWorker()))
            .isInstanceOf(AccessDeniedException.class);

        assertThat(fixtures.exportFileExists(jobId)).isFalse();
        assertThat(fixtures.jobStatus(jobId)).isEqualTo("DENIED");
    }
}
~~~

Đây là **khung** cần repository, policy, fixture và exception handling thật. Không thể khẳng định compile độc lập. Trong ứng dụng thực, method submit có `@PreAuthorize` cần `SecurityContext` thật của Alice nếu gọi qua Spring proxy; việc truyền tham số `Authentication` đơn lẻ không tự làm method-security thấy principal đó. Hãy tạo authentication bằng cơ chế test của Spring Security (ví dụ `@WithMockUser` hoặc `SecurityContextHolder` được thiết lập đúng trong test) rồi đảm bảo test xác minh cả việc kiểm authority tại submit. Trạng thái job `DENIED` cần được ghi khi catch lỗi theo workflow thật; code runner minh họa ở trên có thể ném exception mà chưa persist trạng thái này. Test phải gắn với state machine thực tế.

## 12. Các lỗi và anti-pattern thường thấy

| Lỗi | Vì sao nguy hiểm | Cách tránh |
| --- | --- | --- |
| “Async không có authentication nên bỏ `@PreAuthorize`” | Cơ chế nền có thể chạy rộng hơn quyền user | Định nghĩa execution identity và kiểm policy rõ ràng |
| Copy user `SecurityContext` vào queue | Token/quyền cũ, nguy cơ lộ credentials và serialization không an toàn | Chỉ lưu identity/job metadata; revalidate tại execute |
| Mọi task dùng fixed `SecurityContext` admin | Một user bất kỳ tận dụng quyền service để thao tác ngoài scope | Service dùng capability cụ thể, kèm requester/object policy |
| `MODE_INHERITABLETHREADLOCAL` cho pool | Thread tái sử dụng làm lẫn principal | Wrapper chuẩn hoặc explicit job identity; test cleanup |
| Worker tin `tenantId`/`requestedBy` từ message client | Mạo danh requester và truy cập chéo tenant | Lấy từ job store phía server, xác minh message nguồn |
| Chỉ kiểm khi enqueue | Membership/scope có thể bị thu hồi sau đó | Recheck trước chạy/retry và tại checkpoint nếu cần |
| Worker query `findAll()` rồi filter trong Java | Dữ liệu đã bị tải ngoài scope, leak qua logs/cache/file | Predicate scope trong DB và export stream |
| Download chỉ kiểm biết `jobId` | IDOR, lộ file dù job chạy đúng | Kiểm quyền riêng trên job/file khi download |
| Retry dùng service-admin hoặc bỏ qua policy | Nâng quyền sau lỗi hạ tầng | Retry luôn đi lại qua policy, giới hạn attempts |
| Dùng `@Async` + `@PreAuthorize` mà không test interceptor | Khác thread có thể đổi context/thời điểm kiểm | Test integration và tách submit/run policy |
| Chỉ kiểm HTTP 202 | Job có thể sai quyền khi worker thực hiện | Assert DB/file, job state, actor/executor audit |
| Log access token cùng job | Rò credential qua hệ thống log | Log identity đã chuẩn hóa và correlation ID |

## 13. Checklist thiết kế và nghiệm thu

- [ ] Mỗi job có `requestedBy` (hoặc `SYSTEM` được định nghĩa), `executedBy`, `jobType`, resource/tenant scope, trạng thái và audit trail.
- [ ] Requester được xác thực và có quyền submit theo action **và** đúng tài nguyên; client không được chọn service identity hoặc giả requester.
- [ ] Worker xác thực service identity, có quyền loại job và không chạy dựa vào token/role tự gửi của requester.
- [ ] Chính sách nêu rõ kiểm quyền tại submit, execute, retry và download; revocation/expiry có cách xử lý có chủ đích.
- [ ] Job store và message integrity được bảo vệ; worker không tin payload không xác minh.
- [ ] Dữ liệu được truy vấn theo tenant/ACL chính xác, không dùng service quyền rộng làm lối tắt.
- [ ] Tác vụ ngắn qua pool dùng context propagation phù hợp và cleanup; job lâu dài dùng identity metadata + recheck.
- [ ] Scheduler có quyền hệ thống riêng, whitelist action/tenant, không mạo danh user để qua security.
- [ ] Có state transition/idempotency/lease, retry có giới hạn và cancellation khi quyền bị thu hồi.
- [ ] Kết quả/file riêng được cấp quyền, file tạm bị từ chối được dọn, log không chứa credentials.
- [ ] Unit/integration/E2E test đủ ca happy path, cross-tenant, revoke, pool reuse, broker duplicate và download trái phép.
- [ ] Quyết định quyền được log với requester và executor riêng, đủ truy vết nhưng không lộ thông tin nhạy cảm.

**Tiêu chí đạt:** một job chạy dưới service identity hợp lệ **chỉ** thực hiện thao tác được phép trên dữ liệu requester (hoặc system policy) được phép theo thời điểm/chế độ ủy quyền đã định nghĩa. Không có đường chạy nền nào tự động trở thành bypass cho Spring Security, kể cả khi request ban đầu đã được xác thực thành công.

### Tài liệu tham khảo

- [Spring Security — Concurrency Support](https://docs.spring.io/spring-security/reference/features/integrations/concurrency.html): `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextExecutor` và các wrapper cho `ThreadLocal`.
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): `SecurityContextHolder`, `SecurityContext` và `Authentication`.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@PreAuthorize`, bean proxy và kiểm quyền ở method.
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): quyền tại request entrypoint.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@Async`, `@Scheduled` và task executor.
