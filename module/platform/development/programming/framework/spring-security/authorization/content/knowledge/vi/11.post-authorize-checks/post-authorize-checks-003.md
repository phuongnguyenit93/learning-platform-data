# Phân biệt chưa thực thi nghiệp vụ với đã thực thi nhưng bị chặn kết quả

Một API trả **403 Forbidden** không đủ để biết nghiệp vụ đã thực thi hay chưa. Trong Spring Security method security, một lỗi bị từ chối **trước** khi target method chạy khác hoàn toàn với việc **method đã chạy, tạo return value, rồi kết quả bị hậu kiểm từ chối**. Hai trường hợp có thể cùng ném `AccessDeniedException` và cùng được tầng HTTP chuyển thành 403, nhưng trạng thái DB, sự kiện phát ra và hiệu ứng ở hệ thống khác có thể rất khác.

Bài học này đi sâu vào **Kiểm tra sau phương thức** qua `@PostAuthorize` và so sánh với `@PreAuthorize`, áp dụng cho Spring Security 6.x / Spring Boot 3.x trên Servlet stack và Java 17+. Nội dung làm rõ Spring AOP proxy, thời điểm có `returnObject`, điều kiện khiến body chưa chạy, những gì xảy ra khi hậu kiểm DENY, transaction ordering/rollback, side effects như email và event, cách chuyển authorization về trước mutation, và bài test chứng minh thời điểm thực thi. Có chương trình Java 17 độc lập biên dịch/chạy được với stdout đã kiểm chứng.

## 1. Hai loại từ chối, một status tương tự

~~~text
A. BEFORE-METHOD DENY                    B. AFTER-METHOD DENY

caller -> service proxy                  caller -> service proxy
             |                                         |
       @PreAuthorize                                method body
             |                                         |
             +-- DENY                                 +-- xử lý nghiệp vụ
             |                                         +-- trả returnObject
             v                                         |
     AccessDeniedException                       @PostAuthorize
     target body CHƯA chạy                            |
                                                     +-- DENY
                                                     |
                                                     v
                                               AccessDeniedException
                                               target body ĐÃ chạy
~~~

| Câu hỏi | `@PreAuthorize` từ chối | `@PostAuthorize` từ chối |
| --- | --- | --- |
| Method body đã được gọi? | **Chưa** khi đi qua before-interceptor. | **Đã**, vì phải có kết quả để xét sau. |
| Đã truy vấn DB? | Policy pre-check có thể đọc DB, nhưng body bị chặn chưa chạy. | Body có thể đã đọc hoặc ghi tùy implementation. |
| Có side effect? | Không có side effect từ body bị chặn; những tầng trước vẫn có thể làm việc. | **Có thể có**, không tự hoàn tác. |
| Caller nhận kết quả? | Không, khi DENY mặc định. | Không, khi DENY mặc định. |
| HTTP có thể trả gì? | 403, 401 hoặc redirect tùy authentication/exception handler. | Có thể cùng HTTP 403; status không thể hiện thời điểm. |
| Dùng để bảo vệ mutation? | Thường hữu ích để chặn sớm, vẫn cần invariant trong transaction. | **Không** nên làm chốt quyền duy nhất cho write. |

**Diễn đạt chính xác:** “Chưa thực thi nghiệp vụ” nên hiểu là **thân target method được kiểm soát chưa chạy**, không có nghĩa chưa có bất kỳ Java code, SQL SELECT, security filter hay policy bean nào được gọi.

## 2. Điều kiện để annotation thật sự có hiệu lực

Spring Boot Starter Security **không bật method security tự động**. Cần khai báo:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Spring Security 6.x mặc định đăng ký pre/post method annotations khi `@EnableMethodSecurity` hoạt động. Các thành phần chính:

- `AuthorizationManagerBeforeMethodInterceptor` + `PreAuthorizeAuthorizationManager` thực hiện `@PreAuthorize` **trước** target invocation.
- `AuthorizationManagerAfterMethodInterceptor` + `PostAuthorizeAuthorizationManager` thực hiện `@PostAuthorize` **sau** khi target invocation trả bình thường.
- `MethodSecurityExpressionHandler` xây dựng ngữ cảnh SpEL để xét Authentication, arguments và `returnObject`.

Điều kiện thiết yếu là caller gọi **Spring-managed service bean qua AOP proxy**. Lời gọi `this.securedMethod()` ở cùng instance (self-invocation) hoặc `new Service()` thủ công có thể bỏ qua proxy ở cấu hình AOP mặc định. Khi đó annotation xuất hiện trong source nhưng không chặn gì. Cần test đối tượng **inject từ ApplicationContext**, không chỉ test một instance Java tạo trực tiếp.

Nếu một request bị `AuthorizationFilter` hoặc CSRF filter chặn trước controller, method body cũng chưa chạy, nhưng **đó không phải bằng chứng `@PreAuthorize` đã chạy**. Lớp HTTP authorization và lớp method authorization là hai cửa khác nhau.

## 3. `@PreAuthorize`: chặn trước target method

Ví dụ Spring service:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportReadService {
    private final ReportRepository reports;

    public ReportReadService(ReportRepository reports) {
        this.reports = reports;
    }

    @PreAuthorize("hasAuthority('REPORT_READ')")
    public ReportView read(long id) {
        return reports.loadView(id);
    }
}
~~~

Đây là snippet **phụ thuộc Spring và các kiểu `ReportRepository`/`ReportView` do ứng dụng viết**, không biên dịch chỉ bằng JDK. Người thiếu `REPORT_READ` bị từ chối trước khi gọi `reports.loadView(id)` trong body.

Có thể kiểm tra quyền theo ID bằng policy bean:

~~~java
@PreAuthorize(
    "hasAuthority('REPORT_READ') and @reportPolicy.mayRead(authentication, #id)")
public ReportView read(long id) {
    return reports.loadView(id);
}
~~~

Bean `reportPolicy` cần được định nghĩa và phương thức `mayRead(Authentication,long)` phải dựa trên dữ liệu **server xác minh** (owner/tenant/status), không chỉ ID hoặc owner do client khai báo. Policy có thể gọi SELECT để quyết định; vì vậy ngay cả pre-denial cũng không chứng minh “không có SQL nào được thực hiện”. Điểm được bảo đảm là **body của method bị chặn không chạy**, nếu interception đã diễn ra đúng.

Đối với thao tác ghi, pre-check quyền là bước quan trọng nhưng **không thay thế** kiểm tra bất biến tại lúc UPDATE: dữ liệu có thể đổi sau khi policy kiểm tra (TOCTOU). Cần version/locking hoặc conditional update phù hợp.

## 4. `@PostAuthorize`: kiểm tra kết quả đã được tạo

Một phương thức đọc một object:

~~~java
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportLookupService {
    private final ReportRepository reports;

    public ReportLookupService(ReportRepository reports) {
        this.reports = reports;
    }

    @PostAuthorize(
        "returnObject != null and returnObject.owner == authentication.name")
    public ReportView find(long id) {
        return reports.loadView(id);
    }
}
~~~

Đây cũng là snippet Spring có `ReportView`, repository, Authentication và bean thật, **không phải chương trình Java độc lập**. Giả sử Alice gọi report có owner Bob: body đã gọi repository, nhận `ReportView` Bob và return. `@PostAuthorize` thấy `returnObject.owner` khác `authentication.name`, vì thế caller không nhận đối tượng mà nhận DENY theo cơ chế mặc định.

Những giới hạn phải hiểu:

- `returnObject` chỉ có sau khi method return bình thường, không phải biến dùng để chặn query ở đầu body.
- `returnObject != null` là null guard; nếu muốn 404 khi không tìm thấy, nên xử lý not-found nhất quán trong domain/exception handling.
- Owner bằng username có thể chưa đủ: phải kiểm tra **tenant membership, sharing scope và quyền thực tế**, không tin mỗi tên owner.
- `Authentication.getName()` có thể là JWT subject hoặc identity khác với username DB; policy cần mapping đúng.
- Method có thể đã log/cache/phát event trước khi return; hậu kiểm chỉ ngăn **đường trả result qua proxy**, không thu hồi dữ liệu từ những kênh khác.
- Nếu method ném exception trước lúc return, không có normal `returnObject` cho biểu thức ở trên; đó là exception của body, **không phải post-denial boolean**.

Spring Security 6.5 xem `@PostAuthorize` là công cụ hữu ích chống **Insecure Direct Object Reference (IDOR)** khi chính object trả về mang thuộc tính chủ sở hữu cần xét. Tuy nhiên, nếu khả thi, hãy giới hạn query ngay ở DB để tránh tải dữ liệu ngoài scope trước khi xét.

## 5. Cùng method có cả kiểm tra trước và sau

~~~java
@PreAuthorize("hasAuthority('REPORT_READ')")
@PostAuthorize(
    "returnObject != null and @reportPolicy.maySee(authentication, returnObject)")
public ReportView read(long id) {
    return reports.loadView(id);
}
~~~

Trong ví dụ này, `reportPolicy` là Spring bean, `maySee` nhận Authentication và ReportView; logic phải được ứng dụng triển khai, không có sẵn. Ba trường hợp:

~~~text
1) Thiếu REPORT_READ:
   @PreAuthorize DENY -> body CHƯA chạy -> không có returnObject.

2) Có REPORT_READ nhưng report thuộc tenant khác:
   @PreAuthorize ALLOW -> body chạy và return ReportView
   -> @PostAuthorize DENY -> caller không nhận ReportView.

3) Có REPORT_READ và quyền xem trên report:
   @PreAuthorize ALLOW -> body chạy -> @PostAuthorize ALLOW
   -> caller nhận ReportView.
~~~

Khi cả hai annotation áp dụng, những authorization decisions tương ứng phải đạt để lời gọi hoàn tất. Thứ tự advisor Spring AOP được quyết định bởi framework/configuration, không nên lấy thứ tự in trên source để suy ra order của **transaction, cache, audit hay custom advisors**.

Lưu ý: `@PostFilter` khác `@PostAuthorize`. `@PostFilter` có thể loại từng phần tử khỏi collection rồi trả list rút gọn; `@PostAuthorize` mặc định ra quyết định **cho/không cho trao cả result**. Một response 200 với list rỗng không tự chứng minh hậu kiểm authorization đã từ chối.

## 6. Anti-pattern: đã mutation xong mới hậu kiểm

Đây là ví dụ **cố ý sai về thiết kế bảo mật**:

~~~java
@PostAuthorize("returnObject.approver == authentication.name")
public ApprovalReceipt approve(long reportId) {
    reportRepository.markApproved(reportId);
    eventPublisher.sendApproved(reportId);
    return receipts.load(reportId);
}
~~~

Các bean/kiểu ở trên là giả định của ứng dụng. Luồng thực thi:

~~~text
1. User gọi approve(reportId)
2. Method body UPDATE dữ liệu
3. Method body phát event hoặc gửi email
4. Method body tạo biên nhận và RETURN
5. @PostAuthorize kiểm tra returnObject.approver
6. Predicate false -> AccessDeniedException
7. HTTP caller có thể thấy 403
~~~

**Ở bước 7 không thể kết luận bước 2 và 3 chưa chạy.** Nếu update đã commit, dữ liệu đã đổi; nếu broker đã nhận event, consumer có thể đã xử lý; email đã gửi không tự được rút lại. Nếu client retry vì nghĩ lệnh chưa thành công, có nguy cơ **thực hiện lặp thao tác** khi thiếu idempotency.

Nhưng cũng không được khẳng định “post-denial luôn có nghĩa DB đã COMMIT”. Method body đã chạy và đã trả, còn commit/rollback phụ thuộc transaction advice ordering, transaction propagation, rollback rules và implementation. **Tác động cần được xác minh bằng DB state và side-effect logs/test fixture.**

Spring Security 6.5 **không khuyến nghị `@PostAuthorize` cho method ghi DB**, vì sự thay đổi có thể xảy ra trước khi kiểm tra bảo mật. Với mutation, phải đưa quyết định quyền lên trước update và kiểm tra domain invariant tại thời điểm cập nhật.

## 7. Transaction và thứ tự advisor: đừng suy đoán rollback

Một method có cả `@Transactional` và `@PostAuthorize` chịu tác động của **ít nhất hai advisor**. Nếu transaction advice nằm **bên trong** after-method interceptor, một đường đi có thể là:

~~~text
outer @PostAuthorize advice
  inner @Transactional advice
    BEGIN
    target method body UPDATE
    COMMIT
  @PostAuthorize kiểm tra -> DENY
caller thấy 403 / AccessDeniedException
~~~

Nếu transaction advisor **bao ngoài** hậu kiểm, exception của `@PostAuthorize` có thể đi qua transaction boundary trước quyết định commit, và rollback có thể xảy ra cho DB writes thuộc transaction theo rules. Cả hai mô tả là **mô hình về nesting**, không phải cam kết thứ tự cố định cho mọi Spring Boot version/setup.

Tài liệu Spring Framework quy định advice precedence và default transaction advisor order; tài liệu Spring Security 6.5 còn chỉ ra cách điều chỉnh thứ tự bật transaction/method security khi buộc phải dùng hậu kiểm cho write. Tuy vậy, **điều chỉnh advisor order không làm chiến lược này thành an toàn mặc định**:

- Email đã gửi không tự rollback.
- API chuyển tiền hoặc webhook ngoài process không rollback theo DB.
- Message broker có thể đã nhận thông điệp.
- `REQUIRES_NEW` transaction hoặc service khác có thể commit riêng.
- File/cache/telemetry có thể bị thay đổi độc lập.
- Transactional test tự rollback có thể che một lỗi production.

Vì thế hãy quan sát **trạng thái DB sau transaction**, outbox/broker, external calls và retry behavior, không chỉ xem exception. `@Transactional(readOnly = true)` cũng không bảo đảm toàn bộ body side-effect-free: code có thể gọi API, cache hoặc file system dù transaction read-only.

## 8. Thiết kế an toàn hơn cho thao tác ghi

Đối với duyệt hóa đơn, nên bảo vệ permission trước và điều kiện nghiệp vụ ngay trong transaction:

~~~java
@Service
public class InvoiceApprovalService {
    private final InvoiceRepository invoices;
    private final ApprovalPolicy policy;
    private final OutboxRepository outbox;

    public InvoiceApprovalService(InvoiceRepository invoices,
                                  ApprovalPolicy policy,
                                  OutboxRepository outbox) {
        this.invoices = invoices;
        this.policy = policy;
        this.outbox = outbox;
    }

    @PreAuthorize("hasAuthority('INVOICE_APPROVE')")
    @Transactional
    public ApprovalReceipt approve(long id) {
        Invoice invoice = invoices.findForUpdate(id)
            .orElseThrow(InvoiceNotFoundException::new);

        Authentication actor =
            SecurityContextHolder.getContext().getAuthentication();
        if (!policy.mayApprove(actor, invoice)) {
            throw new AccessDeniedException("Access denied");
        }

        invoice.approveIfPending();
        outbox.recordApproved(invoice);
        return new ApprovalReceipt(invoice.getId());
    }
}
~~~

Đây là **mẫu cấu trúc Spring cần imports/bean/DTO/repository/transaction thật**, không biên dịch độc lập bằng JDK. Trong production phải dùng lock/version hoặc update có điều kiện để tránh state đổi giữa check và write. `policy.mayApprove` phải xét tenant, owner, separation of duties, trạng thái còn PENDING và permission hiện hành trên **dữ liệu server**. Event ghi vào transactional outbox nên được phát sau commit qua worker có idempotency.

Như vậy, một request bị từ chối **trước update** không thực thi mutation. Không dựa vào việc `@PostAuthorize` trên `ApprovalReceipt` chặn một update đã hoàn tất. Với kết quả đọc chứa dữ liệu nhạy cảm, vẫn có thể dùng hậu kiểm trên method **chỉ đọc**, nhưng đó là một mối quan tâm khác với quyền phê duyệt.

## 9. “Body chưa chạy” không có nghĩa hệ thống hoàn toàn chưa làm gì

Một ví dụ:

~~~java
@PreAuthorize("@invoicePolicy.mayRead(authentication, #id)")
public InvoiceView read(long id) {
    return repository.loadView(id);
}
~~~

Nếu policy trả false:

- `repository.loadView(id)` trong body **chưa chạy**.
- Bean `invoicePolicy` có thể **đã chạy SELECT** để biết owner/tenant.
- HTTP authentication filter có thể đã tra user store.
- Controller có thể gọi logging/audit trước service.
- Một AOP advisor khác có thể đã tạo trace.

Vì vậy log chính xác là:

~~~text
stage=BEFORE_METHOD
decision=DENY
target_body_invoked=false
policy_database_reads=possible
other_filters_or_advice=may_have_run
~~~

Để đảm bảo an toàn, policy bean nên **không tạo business side effects**. Chỉ kiểm tra quyền là nhiệm vụ của policy; nếu nó gửi email hoặc cập nhật trạng thái trong lúc đánh giá SpEL, đó là lỗi thiết kế. Tránh kết luận không có SQL hoặc log nào chỉ dựa vào pre-denial.

Ngược lại, một post-denial có nghĩa **body đã trả bình thường**, nhưng một body thuần đọc/tính toán có thể không gây mutation nào. Hãy nêu cụ thể đã có truy vấn nào, thay đổi nào, event nào thay vì suy từ annotation.

## 10. Java 17 độc lập: chứng minh thời điểm bằng bộ đếm và sự kiện

Ví dụ này mô phỏng pre-check và post-check bằng **Java thuần**; không cần Spring Security và không giả lập transaction/SpEL. Nó dùng `bodyRuns` để đếm body đã chạy, và `emittedEvents` để biểu diễn side effect đã sinh.

Lưu đúng tên **`AfterMethodDecisionDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;

public class AfterMethodDecisionDemo {
    record Actor(String name, Set<String> permissions) {}
    record Invoice(long id, String owner, String status) {}

    static final class InvoiceService {
        final AtomicInteger bodyRuns = new AtomicInteger();
        final List<String> emittedEvents = new ArrayList<>();

        Invoice preGuardedRead(Actor actor, Invoice invoice) {
            if (actor == null || !actor.permissions().contains("INVOICE_READ")
                    || !actor.name().equals(invoice.owner())) {
                throw new SecurityException("Denied before invocation");
            }
            bodyRuns.incrementAndGet();
            return invoice;
        }

        Invoice postGuardedRead(Actor actor, Invoice invoice) {
            Invoice result = loadInvoice(invoice);
            if (actor == null || !actor.permissions().contains("INVOICE_READ")
                    || !actor.name().equals(result.owner())) {
                throw new SecurityException("Denied after invocation");
            }
            return result;
        }

        String unsafePostGuardedApproval(Actor actor, Invoice invoice) {
            String result = approveAndEmit(invoice);
            if (actor == null || !actor.permissions().contains("INVOICE_APPROVE")
                    || actor.name().equals(invoice.owner())) {
                throw new SecurityException("Denied after mutation");
            }
            return result;
        }

        String safePreGuardedApproval(Actor actor, Invoice invoice) {
            if (actor == null || !actor.permissions().contains("INVOICE_APPROVE")
                    || actor.name().equals(invoice.owner())) {
                throw new SecurityException("Denied before mutation");
            }
            return approveAndEmit(invoice);
        }

        private Invoice loadInvoice(Invoice invoice) {
            bodyRuns.incrementAndGet();
            return invoice;
        }

        private String approveAndEmit(Invoice invoice) {
            bodyRuns.incrementAndGet();
            emittedEvents.add("invoice-" + invoice.id() + "-approved");
            return "approved-" + invoice.id();
        }
    }

    public static void main(String[] args) {
        InvoiceService service = new InvoiceService();
        Actor alice = new Actor("alice", Set.of("INVOICE_READ"));
        Actor reviewer = new Actor("reviewer", Set.of("INVOICE_APPROVE"));
        Invoice bobInvoice = new Invoice(41L, "bob", "PENDING");
        Invoice aliceInvoice = new Invoice(42L, "alice", "PENDING");

        try {
            service.preGuardedRead(alice, bobInvoice);
        } catch (SecurityException ex) {
            System.out.println("Pre denied: " + ex.getMessage());
        }
        System.out.println("Body after pre deny: " + service.bodyRuns.get());

        try {
            service.postGuardedRead(alice, bobInvoice);
        } catch (SecurityException ex) {
            System.out.println("Post denied: " + ex.getMessage());
        }
        System.out.println("Body after post deny: " + service.bodyRuns.get());
        System.out.println("Allowed post read id: "
                + service.postGuardedRead(alice, aliceInvoice).id());
        System.out.println("Body after allowed read: " + service.bodyRuns.get());

        try {
            service.unsafePostGuardedApproval(alice, aliceInvoice);
        } catch (SecurityException ex) {
            System.out.println("Unsafe approval denied: " + ex.getMessage());
        }
        System.out.println("Events after unsafe denial: "
                + service.emittedEvents);
        try {
            service.safePreGuardedApproval(alice, aliceInvoice);
        } catch (SecurityException ex) {
            System.out.println("Safe approval denied: " + ex.getMessage());
        }
        System.out.println("Events after safe denial: "
                + service.emittedEvents);
        System.out.println("Reviewer approval: "
                + service.safePreGuardedApproval(reviewer, aliceInvoice));
        System.out.println("Events final: " + service.emittedEvents);
        System.out.println("Body final: " + service.bodyRuns.get());
    }
}
~~~

Biên dịch và chạy trên **JDK 17 trở lên**:

~~~bash
javac --release 17 AfterMethodDecisionDemo.java
java AfterMethodDecisionDemo
~~~

Stdout đã kiểm chứng:

~~~text
Pre denied: Denied before invocation
Body after pre deny: 0
Post denied: Denied after invocation
Body after post deny: 1
Allowed post read id: 42
Body after allowed read: 2
Unsafe approval denied: Denied after mutation
Events after unsafe denial: [invoice-42-approved]
Safe approval denied: Denied before mutation
Events after safe denial: [invoice-42-approved]
Reviewer approval: approved-42
Events final: [invoice-42-approved, invoice-42-approved]
Body final: 4
~~~

Hai con số **0** và **1** chứng minh sự khác biệt: pre-denial không vào body; post-denial đã vào body. Danh sách event **không rỗng** sau unsafe post-denial cho thấy chặn result không xóa side effect. Safe pre-denial không thêm event. Demo có mục đích giải thích thời điểm, **không phải bằng chứng Spring DB sẽ commit/rollback theo một cách cố định**.

## 11. Kiểm thử method security thật bằng counter và Spring proxy

Nếu test chỉ `assertThrows(AccessDeniedException.class)`, bạn vẫn chưa phân biệt được exception đến trước hay sau body. Dùng fixture Spring-managed có counter:

~~~java
@Service
class TimingFixtureService {
    final AtomicInteger preBodyRuns = new AtomicInteger();
    final AtomicInteger postBodyRuns = new AtomicInteger();

    @PreAuthorize("hasAuthority('REPORT_ACCESS')")
    public String beforeGuard() {
        preBodyRuns.incrementAndGet();
        return "executed";
    }

    @PostAuthorize("returnObject == authentication.name")
    public String afterGuard() {
        postBodyRuns.incrementAndGet();
        return "someone-else";
    }
}
~~~

Đây là class fixture **cần import và Spring Test setup**, không là file hoàn chỉnh. Test skeleton:

~~~java
@SpringBootTest
class TimingMethodSecurityIT {
    @Autowired TimingFixtureService fixture;

    @Test
    @WithMockUser(username = "alice", authorities = "OTHER")
    void beforeDeniedNoBody() {
        fixture.preBodyRuns.set(0);
        assertThrows(AccessDeniedException.class, fixture::beforeGuard);
        assertEquals(0, fixture.preBodyRuns.get());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "OTHER")
    void afterDeniedBodyAlreadyRan() {
        fixture.postBodyRuns.set(0);
        assertThrows(AccessDeniedException.class, fixture::afterGuard);
        assertEquals(1, fixture.postBodyRuns.get());
    }
}
~~~

Dự án cần `spring-boot-starter-test`, `spring-security-test`, JUnit imports và test context. Các bộ đếm singleton chỉ dùng fixture có reset/isolated execution đúng cách. Không dùng body counter toàn cục chứa identity người dùng trong production.

Kiểm thử đầy đủ cần:

| Tình huống | Bằng chứng cần có |
| --- | --- |
| `@PreAuthorize` false | Body counter = 0, exception ném trước method. |
| `@PostAuthorize` false | Body counter = 1, caller không nhận result bình thường. |
| `@PostAuthorize` true | Body counter = 1, caller nhận result. |
| Body ném exception trước return | Exception từ body, không gán nhầm cho post-denial. |
| Self-invocation | Phát hiện annotation không chạy do proxy bị bypass. |
| HTTP 403 từ security filter | Service body = 0, nhưng không phải bằng chứng method annotation deny. |
| Post-denial sau DB write | Kiểm tra DB **sau transaction** và outbox/message, không chỉ exception. |
| Post-denial sau external call | Fake broker/HTTP server/spies cho biết effect đã xảy ra. |
| Data khác owner/tenant | Không trao result ngoài scope; không có side effect không được phép. |

**Cảnh báo test transaction:** Một test gắn `@Transactional` có thể tự rollback khi kết thúc, che việc service đã thực hiện SQL trước hậu kiểm. Khi kiểm tra commit/rollback, đặt boundaries giống production và quan sát state **ngoài test transaction**; kiểm tra thêm outbox, email và retry/idempotency. `MockMvc` 403 không đủ chứng minh thứ tự nếu không có counter/spy.

## 12. Khi nào dùng hậu kiểm và khi nào phải chuyển quyền về trước?

| Nghiệp vụ | Phương án chính | Giải thích |
| --- | --- | --- |
| Đọc một object cần xem owner trong result | `@PostAuthorize`, có thể kết hợp pre-authority và query scoped | Chặn result nếu ngoài quyền, body không được gây side effect. |
| Trả danh sách lớn/phân trang | Pre-authority + repository WHERE tenant/owner | Tránh tải nhiều object ngoài scope; pagination đúng. |
| Duyệt hóa đơn, sửa trạng thái, thanh toán | Pre-check + domain invariant trong transaction | Không chờ đến hậu kiểm mới quyết định được phép ghi. |
| Gửi email/webhook | Kiểm tra trước gửi, outbox và idempotency khi thích hợp | External effects không rollback theo DB. |
| Xuất file riêng tư | Kiểm tra quyền trước khi tạo/stream file | Không tạo hoặc rò dữ liệu lớn rồi mới DENY. |
| Scheduler/message consumer gọi service | Method/domain policy với security identity hợp lệ | Không có HTTP filter tự động cho lời gọi ấy. |
| Method đọc object nhưng có audit/cache | Hậu kiểm chỉ nếu audit/cache không lộ dữ liệu ngoài scope | Read-only không nhất thiết đồng nghĩa không có side effect. |

Cách suy nghĩ an toàn: nếu một method **có thể tạo effect không thể đảo ngược**, authorization để thực hiện effect phải xảy ra **trước effect đó**. Nếu điều kiện quyền chỉ biết sau khi load object, hãy **load + kiểm tra quyền** ở bước đọc và đảm bảo policy trước thao tác thay đổi state. Không coi việc ném exception muộn là một cơ chế undo.

## 13. Quy trình chẩn đoán lỗi “trả 403 nhưng nghiệp vụ vẫn chạy”

1. Xác định user/tenant, request ID và HTTP rule nào đang được áp dụng.
2. Tìm xem HTTP filter chặn trước controller hay không.
3. Xác nhận service được gọi **qua Spring AOP proxy**.
4. Tách origin của exception: before-interceptor, body/domain policy hay after-interceptor.
5. Quan sát body counter/method spy: không suy từ response status.
6. Kiểm tra SQL SELECT và UPDATE **theo call site**, phân biệt query trong pre-policy với query trong body.
7. Với hậu kiểm false, xác minh DB state, commit/rollback, broker/outbox, email/webhook, file/cache.
8. Kiểm tra transaction advisor ordering trên dependency version thực; không đoán từ thứ tự annotation.
9. Xem client retry hoặc message redelivery có tạo thêm side effect không.
10. Đưa authorization sớm lên pre-check và giữ kiểm tra bất biến trong transaction.
11. Bổ sung test DENY/ALLOW, owner khác, tenant khác, body exception và concurrent update.
12. Không log JWT, PII hay toàn bộ report/returnObject để chẩn đoán.

Một log tốt có thể có thông tin `authorization_stage=BEFORE_METHOD` hoặc `AFTER_METHOD`, `decision=DENY`, `target_body_invoked=true/false` (được instrument thật) và correlation ID. Không gán giá trị đã hay chưa commit nếu không có bằng chứng từ persistence/outbox.

## 14. Checklist trước khi triển khai

- [ ] `@EnableMethodSecurity` được kích hoạt, service được gọi qua Spring proxy.
- [ ] Đã phân loại method: chỉ đọc hay có DB write/external side effect.
- [ ] Không dùng `@PostAuthorize` làm lớp bảo vệ duy nhất cho mutation.
- [ ] Body chỉ đọc và trả object được hậu kiểm thì không log/cache/gửi dữ liệu ngoài scope trước khi DENY.
- [ ] Dữ liệu owner/tenant được xác minh từ server, không tin DTO/header client.
- [ ] `returnObject` null và not-found có contract rõ.
- [ ] Permission chung và domain invariant được kiểm tra trước write, kiểm soát TOCTOU.
- [ ] Transaction advisor ordering/rollback được test thật, không suy diễn từ 403.
- [ ] External effects dùng outbox/idempotency/compensation khi thích hợp.
- [ ] Pre-denial test chứng minh body chưa chạy; post-denial test chứng minh body đã chạy.
- [ ] Có test exception phát sinh trong body khác với post-denial.
- [ ] Có test HTTP filter-denial riêng với method-denial.
- [ ] Có test DB/outbox state khi DENY và khi client retry.
- [ ] Khi ghi log/audit, nêu đúng pha từ chối và không lộ dữ liệu nhạy cảm.

**Kết luận:** Trong Spring method security, `@PreAuthorize` có thể từ chối **trước khi target method body chạy**, còn `@PostAuthorize` xét **returnObject sau khi body đã chạy**. Cả hai có thể khiến caller thấy 403, nhưng post-denial không xóa mutation hoặc side effect đã xảy ra. Dùng hậu kiểm cho dữ liệu **đọc** khi phù hợp, và dùng **authorization trước tác dụng phụ + kiểm tra bất biến lúc ghi** cho hành động nghiệp vụ có thể thay đổi trạng thái.

### Tài liệu tham khảo chính thức

- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — @PreAuthorize API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/prepost/PreAuthorize.html)
- [Spring Security 6.5 — @PostAuthorize API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/prepost/PostAuthorize.html)
- [Spring Security 6.5 — After-Method Interceptor API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/method/AuthorizationManagerAfterMethodInterceptor.html)
- [Spring Framework — @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — AOP Advice Ordering](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html)
