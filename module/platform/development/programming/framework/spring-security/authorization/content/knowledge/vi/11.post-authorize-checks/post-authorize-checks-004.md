# Giới hạn của @PostAuthorize với thao tác ghi và tác động không thể hoàn tác

> **Module:** Spring Security – authorization  
> **Nhóm:** Kiểm tra sau phương thức  
> **Mục tiêu:** Hiểu `@PostAuthorize` được đánh giá sau method body, không phải bảo đảm hoàn tác; phân biệt denial, transaction rollback và các side effect ngoài database; chọn `@PreAuthorize`, object-level policy, transaction/locking, outbox và integration test để bảo vệ thao tác ghi.

## 1. Tình huống mở đầu: HTTP 403 nhưng dữ liệu đã đổi?

Một ứng dụng cho phép sửa tài liệu:

~~~java
// THIẾT KẾ NGUY HIỂM – không áp dụng cho thao tác ghi.
@PostAuthorize("returnObject.ownerId == authentication.name")
public DocumentDto update(long id, UpdateCommand command) {
    Document document = repository.findById(id).orElseThrow();
    document.apply(command);
    repository.save(document);
    mailClient.sendDocumentUpdated(document);
    return mapper.toDto(document);
}
~~~

Giả sử Bob sửa tài liệu thuộc Alice. Ý định của lập trình viên: nếu Bob không phải owner, Spring Security sẽ từ chối. Trình tự thực tế của `@PostAuthorize` có thể là:

~~~text
1. Bob gọi update(documentId=7).
2. Spring AOP cho method body thực thi.
3. document.apply(command) thay đổi object.
4. repository.save(document) được gọi.
5. mailClient.sendDocumentUpdated(...) được gọi.
6. method trả DocumentDto.
7. @PostAuthorize đọc returnObject.ownerId.
8. So với authentication.name, không khớp -> DENY.
9. Caller nhận AccessDeniedException / HTTP 403 tùy entrypoint.
~~~

**Ở bước 8, các bước 3–5 đã xảy ra.** Không thể nhìn status 403 rồi kết luận database chưa thay đổi, email chưa gửi hoặc tác động nghiệp vụ đã được đảo ngược. Có thể database commit hoặc rollback tùy transaction boundary; email đã gửi không tự thu hồi bằng một exception Java.

**Điểm cốt lõi:** `@PostAuthorize` kiểm tra **kết quả sau khi method thực hiện**, không phải cơ chế kiểm quyền trước mutation, cũng không phải distributed rollback. Spring Security documentation chính thức không khuyến nghị dùng `@PostAuthorize` cho class thực hiện database writes, đặc biệt khi kết hợp `@Transactional`.

## 2. So sánh @PreAuthorize và @PostAuthorize

| Tiêu chí | `@PreAuthorize` | `@PostAuthorize` |
|---|---|---|
| Thời điểm | Trước khi body chạy | Sau khi body chạy |
| Dữ liệu dễ dùng | Authentication, authorities, method arguments, policy bean | Authentication, arguments, `returnObject` |
| Nếu denial | Chặn method body nếu invocation đi qua advisor | Body đã thực thi trước denial |
| Phù hợp | Write/delete/approve/export/send | Đọc object, kiểm kết quả sau truy vấn |
| Rủi ro quan trọng | Data race/TOCTOU nếu kiểm rồi mới ghi | Mutation đã xảy ra, transaction có thể commit, external effects còn |
| Cơ chế | Before-method interceptor | After-method interceptor |

Luồng minh họa:

~~~text
Caller
   |
   v
Spring AOP proxy
   |
   +--> @PreAuthorize
   |       - nếu DENY: method không chạy
   |       - nếu ALLOW: tiếp tục
   |
   v
Business method
   |
   +--> SQL update / HTTP call / message / email / return
   |
   v
@PostAuthorize
   |
   +--> Kiểm tra returnObject / authentication
   +--> nếu DENY: chặn return cho caller
   |
   v
Caller nhận result nếu được phép
~~~

Nhiều annotation khác loại có thể được xử lý nối tiếp; `@PreAuthorize` và `@PostAuthorize` không tự triệt tiêu nhau. Tuy nhiên `@PostAuthorize` vẫn chỉ có quyết định sau khi body đã tạo giá trị trả về.

### 2.1. @PostAuthorize hữu ích khi method chỉ đọc

~~~java
@PostAuthorize("returnObject.owner == authentication.name")
public Account readAccount(long accountId) {
    return repository.findById(accountId).orElseThrow();
}
~~~

Điều kiện chỉ cho trả Account nếu owner trùng người đăng nhập. Đây là ví dụ chính thức về hậu kiểm trên return object, có ích để chống IDOR/BOLA **ở khâu trả kết quả**. Class snippet cần Spring Security, bean/repository, identity contract và `@EnableMethodSecurity`; không phải chương trình JDK độc lập.

Phương thức đọc vẫn phải thực sự không thực hiện business mutation: một method tên `readAccount` có thể ghi audit, gọi API, trigger lazy-load hoặc gây side effect gián tiếp. Cần kiểm call graph.

### 2.2. @PostAuthorize trên write không phù hợp

~~~java
// KHÔNG DÙNG làm biện pháp chặn xóa:
@PostAuthorize("returnObject.owner == authentication.name")
public Account deleteAccount(long id) {
    Account account = repository.findById(id).orElseThrow();
    repository.delete(account);
    return account;
}
~~~

Nếu không được phép, deletion vẫn được gọi trước khi hậu kiểm. Dù một số cấu hình transaction có thể rollback, thiết kế đã đặt bảo mật sau thao tác; không được coi đó là mặc định an toàn.

## 3. Method security hoạt động qua Spring AOP

Bật method security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Với Spring Security Servlet 6.x/7.x, các annotation phổ biến có interceptors riêng:

- `@PreAuthorize` qua `AuthorizationManagerBeforeMethodInterceptor` và `PreAuthorizeAuthorizationManager`.
- `@PostAuthorize` qua `AuthorizationManagerAfterMethodInterceptor` và `PostAuthorizeAuthorizationManager`.
- `@PreFilter` và `@PostFilter` xử lý lọc đối số/kết quả theo cơ chế liên quan.

Nếu `@PostAuthorize` từ chối, hạ tầng có thể ném `AccessDeniedException`. Trong request HTTP đi qua Spring Security filters, exception translation có thể tạo HTTP 403 hoặc kích hoạt xử lý authentication phù hợp. Trong batch/job/service không qua HTTP, caller phải xử lý exception.

**Denial khác rollback.** `AccessDeniedException` là biểu hiện kết quả authorization, không tự chứng minh các resource từng bị method body thay đổi đã được đưa về trạng thái cũ.

### 3.1. Proxy bypass

Dù annotation đặt đúng, lời gọi nội bộ:

~~~java
@Service
class DocumentService {
    void entrypoint() {
        protectedDelete(7);  // self-invocation, có thể bypass proxy.
    }

    @PreAuthorize("hasAuthority('document:delete')")
    public void protectedDelete(long id) {
        // ...
    }
}
~~~

trong proxy mode thông thường có thể đi trực tiếp qua `this` mà không chạy advice. Tương tự, object tạo bằng `new` không được Spring proxy; private/final methods có giới hạn tùy proxy strategy.

Một thiết kế bảo mật cho thao tác ghi cần **gọi qua Spring-managed proxy** hoặc có bước kiểm nghiệp vụ trực tiếp trong service không thể bypass. Annotation không phải câu lệnh Java tự chạy trong body.

## 4. Những loại side effect @PostAuthorize không xóa được

| Side effect trước hậu kiểm | Có thể còn sau denial? | Vì sao |
|---|---|---|
| SQL write đã commit | Có | Commit không tự bị đảo bởi exception sau đó |
| SQL write chưa commit | Có thể rollback | Tùy transaction nesting, rollback rules, resource |
| Autocommit SQL | Có | Lệnh có thể lưu ngay |
| Email/SMS | Có | Bên ngoài ứng dụng có thể đã nhận |
| Kafka/RabbitMQ publish | Có | Broker/consumer có transaction và thời điểm xử lý riêng |
| Webhook | Có | Receiver có thể xử lý |
| Payment capture/refund | Có | Provider là hệ thống riêng |
| File/object storage delete | Có | Không tự phục hồi nếu thiếu version/compensation |
| Cache/Redis mutation | Có | Không nằm trong DB transaction mặc định |
| Audit log bên ngoài | Có | Đã ghi vào hệ thống khác |
| In-memory shared state | Có | Throw exception không đảo shared object |
| HTTP call tới microservice khác | Có | Microservice có transaction riêng |
| Cấp quyền hoặc phát JWT | Có | Token có thể đã cấp/trở nên sử dụng được |

Một số thao tác có **compensation** (ví dụ refund, restore file, gửi thông báo đính chính), nhưng compensation là **hành động mới**, có thể thất bại; không phải rollback nguyên tử.

### 4.1. SQL save chưa chắc đồng nghĩa commit

Với ORM/JPA, `save`, dirty checking, `flush` và `commit` là các thời điểm khác nhau. Một entity có thể bị sửa trong persistence context nhưng SQL chưa flush; cũng có thể SQL chạy trước method return hoặc commit ngoài method. Không được nói chung rằng `repository.save` chắc chắn commit, cũng không nói `@Transactional` chắc chắn khiến mọi write rollback. Phải inspect advisor chain và test DB thật.

### 4.2. HTTP status không nói trạng thái tài nguyên

`403 Forbidden` từ client chỉ cho biết request bị từ chối theo cơ chế xử lý HTTP tại thời điểm response. Nó **không xác nhận** zero database writes, zero outbound calls hay không có messages. Test cần assert business state và external interactions.

## 5. @Transactional có luôn rollback sau @PostAuthorize deny không?

Không. Cùng một method:

~~~java
@Transactional
@PostAuthorize("returnObject.ownerId == authentication.name")
public DocumentDto update(long id, UpdateCommand command) {
    Document doc = repository.findById(id).orElseThrow();
    doc.apply(command);
    return mapper.toDto(doc);
}
~~~

có thể được bọc bởi **nhiều AOP advisors**. Vị trí outer/inner ảnh hưởng việc postcheck được đánh giá trước hay sau transaction completion.

### 5.1. Postcheck ở ngoài transaction

~~~text
PostAuthorize advisor (outer)
   |
   +--> Transaction advisor (inner)
   |      BEGIN
   |      method body: changes
   |      COMMIT
   |
   +--> evaluate returnObject -> DENY
~~~

Trong cấu trúc này, database đã có thể commit khi `@PostAuthorize` mới ném exception. Transaction không thể retroactively rollback.

### 5.2. Transaction ở ngoài postcheck

~~~text
Transaction advisor (outer)
   BEGIN
   |
   +--> PostAuthorize advisor (inner)
   |      method body: changes
   |      evaluate returnObject -> DENY
   |      throw AccessDeniedException
   |
   ROLLBACK nếu rollback rules áp dụng
~~~

Ở cấu trúc này, runtime `AccessDeniedException` được propagate qua transaction interceptor có thể khiến DB rollback theo mặc định. Tuy nhiên email/webhook/payment đã gửi vẫn có thể tồn tại, `REQUIRES_NEW` đã commit vẫn có thể không rollback, và resource thứ hai không quản lý cùng transaction cũng không tự đảo.

**Thứ tự advisor không được xác định bằng thứ tự hai annotation được gõ trong source.** Tài liệu Spring Security đề cập thứ tự `@EnableTransactionManagement` và `@EnableMethodSecurity` khi bắt buộc phối hợp post-authorization với transaction. Đó là một cấu hình cần kiểm chứng, **không phải thay thế thiết kế kiểm quyền trước write**.

### 5.3. Các rollback rules

Spring Framework mặc định rollback cho `RuntimeException` và `Error`. Checked exception thông thường không tự rollback trừ khi cấu hình `rollbackFor` phù hợp.

~~~java
@Transactional(rollbackFor = Exception.class)
public void process() throws Exception {
    // ...
}
~~~

Snippet này không có nghĩa nên “chữa” lỗi đặt hậu kiểm bằng `rollbackFor`. Khi exception bị bắt và nuốt bên trong transaction, hoặc khi transaction đã commit, rollback vẫn có thể không xảy ra.

### 5.4. REQUIRES_NEW độc lập

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void writeIndependentRecord() {
    // ...
}
~~~

`REQUIRES_NEW` sử dụng một physical transaction độc lập. Inner transaction có thể commit ngay cả khi outer transaction rollback. Điều này đôi khi đúng cho audit nhưng nguy hiểm nếu dùng để thay đổi quyền/tài nguyên trước khi postcheck của outer method.

### 5.5. Transaction khác nhau giữa microservices

Database transaction trên service A không tự undo lệnh gọi payment processor, HTTP service B hoặc Kafka consumer C. Nếu C đã xử lý sự kiện, việc A rollback không có nghĩa C biết để hoàn tác. Cần thiết kế workflow, idempotency và compensation riêng.

## 6. Thiết kế mặc định: @PreAuthorize và policy trên resource

Ví dụ sửa đổi an toàn hơn:

~~~java
@PreAuthorize(
    "hasAuthority('document:update') and " +
    "@documentPolicy.canUpdate(authentication, #id)"
)
public DocumentDto update(
        @P("id") long id,
        UpdateDocumentCommand command) {
    Document document = repository.findById(id).orElseThrow();
    document.apply(command);
    return mapper.toDto(document);
}
~~~

Ở đây:

1. `hasAuthority('document:update')` kiểm permission chức năng.
2. `@documentPolicy.canUpdate(authentication,#id)` kiểm principal, tenant, owner và trạng thái resource từ nguồn server.
3. Nếu deny, method body **không chạy** qua invocation được Spring proxy bảo vệ.
4. Nếu allow, mới tiếp tục mutation.

Snippet thuộc **ứng dụng Spring**; cần `@EnableMethodSecurity`, Spring-managed service, bean `documentPolicy`, `@P`, repository và domain types. Không phải Java JDK độc lập.

### 6.1. Không tin ownerId từ request body

~~~java
// POLICY SAI nếu ownerId do client tự điền:
@PreAuthorize("#command.ownerId == authentication.name")
public void update(long id, UpdateCommand command) {
    // ...
}
~~~

User có thể tự đặt `ownerId` trong command để phù hợp `authentication.name`. Quyền phải dựa trên **resource thực tương ứng id** trong database, không dựa vào một trường ownerId do caller tự khai.

### 6.2. Bean policy đọc dữ liệu tin cậy

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {
    private final DocumentRepository repository;
    private final IdentityResolver identityResolver;

    public DocumentPolicy(
            DocumentRepository repository,
            IdentityResolver identityResolver) {
        this.repository = repository;
        this.identityResolver = identityResolver;
    }

    public boolean canUpdate(Authentication auth, long documentId) {
        InternalIdentity actor = identityResolver.resolve(auth);
        if (actor == null) return false;
        return repository.existsEditableByTenantAndOwner(
                documentId, actor.tenantId(), actor.userId());
    }
}
~~~

Đây là skeleton phụ thuộc `DocumentRepository`, `IdentityResolver` và `InternalIdentity` của ứng dụng. Resolver phải từ chối anonymous/unverified identity, map JWT issuer+subject hoặc session principal vào internal user ID, không tin tenant/owner từ client. Repository phải enforce tenant, owner và document state.

### 6.3. Permission không đủ nếu thiếu object policy

User có `document:update` vẫn có thể không được sửa tài liệu của tenant khác. Cần kiểm:

- Chủ thể được xác thực.
- Permission đúng action (update khác read/delete/export).
- Tenant membership hợp lệ.
- Resource owner/assignee hoặc scoped override.
- Trạng thái resource cho phép sửa.
- Các điều kiện workflow như approval, MFA hoặc hạn mức.
- Không có user bị khóa/thu hồi quyền.

Không cho role ADMIN tự động bypass mọi tenant/owner policy nếu nghiệp vụ không cho phép.

## 7. Race condition sau precheck: TOCTOU

Ngay cả `@PreAuthorize` có thể gặp:

~~~text
T1: Bob có quyền chỉnh document 7 -> precheck ALLOW.
T2: Document 7 chuyển owner sang Alice.
T1: Bob cập nhật document 7 dựa vào kết quả quyền cũ.
~~~

Đây là **time-of-check/time-of-use**, không phải lỗi riêng của Spring Security. Cần gắn authorization invariant vào thời điểm write/commit:

- Pessimistic locking khi load entity.
- Optimistic locking bằng `@Version` và kiểm lại quyền khi retry.
- Conditional update theo tenant/owner/state/version.
- Transaction isolation phù hợp.
- Domain policy kiểm resource ngay trước mutation.

Một skeleton:

~~~java
@Service
public class DocumentCommandService {
    private final DocumentRepository repository;
    private final DocumentPolicyService policy;

    public DocumentCommandService(
            DocumentRepository repository,
            DocumentPolicyService policy) {
        this.repository = repository;
        this.policy = policy;
    }

    @PreAuthorize("hasAuthority('document:update')")
    @Transactional
    public void update(long id, UpdateCommand command) {
        Document doc = repository.findByIdForUpdate(id).orElseThrow();
        policy.requireCanUpdate(doc);
        doc.apply(command);
    }
}
~~~

`findByIdForUpdate` là **quy ước API của ví dụ**, cần tự triển khai locking phù hợp; `policy.requireCanUpdate` phải lấy authenticated identity đáng tin và ném denial **trước `doc.apply`**. Method nên được gọi qua Spring proxy để `@Transactional` và `@PreAuthorize` hoạt động.

### 7.1. Conditional SQL update

~~~sql
UPDATE documents
SET status = :new_status,
    version = version + 1
WHERE id = :id
  AND tenant_id = :tenant_id
  AND owner_user_id = :actor_id
  AND status = 'EDITABLE'
  AND version = :expected_version;
~~~

Nếu 0 rows updated, quyền/trạng thái/concurrency không thỏa; use case phải xử lý theo policy. Ví dụ này giả định **owner có quyền update**, không áp dụng nguyên xi cho workflow có sharing/delegation. Vẫn cần function-level permission và tenant context từ authentication.

## 8. Một cách tận dụng @PostAuthorize: đọc trước rồi ghi

Spring Security hướng dẫn có thể **đọc resource và kiểm hậu quyền trên dữ liệu đọc**, sau đó mới thực hiện mutation trong một lời gọi khác.

~~~java
@Service
public class DocumentLookupService {
    @PostAuthorize(
        "hasAuthority('document:update') and " +
        "@documentPolicy.canUpdateReturned(authentication, returnObject)"
    )
    public DocumentSnapshot requireEditable(long id) {
        return repository.findSnapshotById(id).orElseThrow();
    }
}
~~~

Sau đó:

~~~java
@Service
public class DocumentCommandService {
    private final DocumentLookupService lookup;
    private final DocumentRepository repository;

    @Transactional
    public void update(long id, UpdateCommand command) {
        DocumentSnapshot snapshot = lookup.requireEditable(id);
        Document doc = repository.findByIdForUpdate(id).orElseThrow();
        // Kiểm lại trạng thái/quyền trong transaction khi có race.
        doc.apply(command);
    }
}
~~~

Những snippet này cần constructors/imports/domain types. Điểm quan trọng là `lookup.requireEditable` được gọi qua **bean proxy khác**, nên `@PostAuthorize` có thể chạy trước khi command method viết. Tuy nhiên giữa read và write vẫn có khoảng TOCTOU; phải check lại/lock trước mutation nếu cần.

**Không** viết `this.requireEditable(id)` trong cùng service rồi tin chắc @PostAuthorize được áp dụng: self-invocation có thể bypass proxy.

## 9. Outbox và @TransactionalEventListener: giải quyết external effects đúng chỗ

Với database write + event publish, cân nhắc **transactional outbox**:

~~~text
1. Xác thực và kiểm quyền trước action.
2. Mở DB transaction.
3. Kiểm resource state/owner/tenant và concurrency.
4. Update business row.
5. Insert outbox row trong cùng DB transaction.
6. Commit.
7. Dispatcher đọc outbox và gửi event bên ngoài.
8. Receiver xử lý idempotent, dispatcher retry/đánh dấu delivered.
~~~

Lợi ích: nếu transaction ở bước 2–6 rollback, business row và outbox row cùng rollback. Nếu commit thành công rồi process crash, event vẫn nằm trong DB chờ dispatcher gửi. Nhưng **outbox không cứu được việc đã commit trái phép do kiểm quyền đặt sau mutation**.

Outbox không tự mang bảo đảm exactly-once end-to-end: dispatcher có thể gửi thành công rồi crash trước khi mark delivered; receiver cần idempotency key và deduplication.

### 9.1. AFTER_COMMIT listener

Spring Framework hỗ trợ:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onDocumentChanged(DocumentChangedEvent event) {
    notificationClient.send(event);
}
~~~

Listener có thể chạy sau commit thành công. Tuy vậy:

- Nếu transaction commit **trước khi `@PostAuthorize` deny**, listener vẫn có thể chạy.
- Event in-memory có nguy cơ mất khi process crash sau commit.
- External send có thể thất bại; cần retry/monitoring nếu quan trọng.
- Không có transaction active thì behavior phụ thuộc `fallbackExecution` và cấu hình.
- AFTER_COMMIT **không** thay thế authorization trước mutation.

### 9.2. Payment và webhook

Với payment capture, SMS, email chứa PII hoặc webhook:

~~~text
Authenticated actor
    |
    v
Permission + owner/tenant/amount/workflow approval
    |
    v
Authorized command & idempotent intent
    |
    v
Commit local state/outbox
    |
    v
Send external request with idempotency key
    |
    v
Reconcile response, audit, handle retries/compensation
~~~

Một payment provider có thể đã capture tiền khi caller nhận 403. Compensation/refund là một giao dịch mới có khả năng thất bại; không phải `@PostAuthorize` rollback.

## 10. Java 17 độc lập: mô phỏng hậu kiểm sau khi thay đổi

Ví dụ này dùng Java chuẩn, **không có Spring Security hoặc database thật**. Hai danh sách ghi nhận “database writes” và “external sends” chỉ nhằm minh họa thứ tự thao tác. Nó không mô phỏng rollback Spring hay AOP advisors.

Tạo file `PostAuthorizationWriteDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class PostAuthorizationWriteDemo {

    record Actor(String userId) {}
    record Resource(String id, String ownerId) {}

    static final class Effects {
        final List<String> databaseWrites = new ArrayList<>();
        final List<String> externalMessages = new ArrayList<>();
    }

    static String unsafePostCheck(Actor actor, Resource target, Effects effects) {
        effects.databaseWrites.add("UPDATED:" + target.id());
        effects.externalMessages.add("SENT:" + target.id());
        return actor.userId().equals(target.ownerId())
                ? "ALLOW_AFTER" : "DENY_AFTER";
    }

    static String preCheckedWrite(Actor actor, Resource target, Effects effects) {
        if (!actor.userId().equals(target.ownerId())) {
            return "DENY_BEFORE";
        }
        effects.databaseWrites.add("UPDATED:" + target.id());
        effects.externalMessages.add("SENT:" + target.id());
        return "ALLOW";
    }

    public static void main(String[] args) {
        Actor bob = new Actor("u-bob");
        Actor alice = new Actor("u-alice");
        Resource document = new Resource("doc-7", "u-alice");

        Effects unsafe = new Effects();
        System.out.println("unsafe decision: "
                + unsafePostCheck(bob, document, unsafe));
        System.out.println("unsafe database writes: "
                + unsafe.databaseWrites.size());
        System.out.println("unsafe external sends: "
                + unsafe.externalMessages.size());

        unsafe.databaseWrites.clear();
        System.out.println("rollback simulated database writes: "
                + unsafe.databaseWrites.size());
        System.out.println("rollback cannot undo sends: "
                + unsafe.externalMessages.size());

        Effects safeDenied = new Effects();
        System.out.println("safe decision: "
                + preCheckedWrite(bob, document, safeDenied));
        System.out.println("safe database writes: "
                + safeDenied.databaseWrites.size());
        System.out.println("safe external sends: "
                + safeDenied.externalMessages.size());

        Effects safeAllowed = new Effects();
        System.out.println("safe owner decision: "
                + preCheckedWrite(alice, document, safeAllowed));
        System.out.println("safe owner database writes: "
                + safeAllowed.databaseWrites.size());
        System.out.println("safe owner external sends: "
                + safeAllowed.externalMessages.size());
    }
}
~~~

Biên dịch/chạy với JDK 17:

~~~bash
javac --release 17 PostAuthorizationWriteDemo.java
java PostAuthorizationWriteDemo
~~~

Kết quả đúng đã kiểm thử:

~~~text
unsafe decision: DENY_AFTER
unsafe database writes: 1
unsafe external sends: 1
rollback simulated database writes: 0
rollback cannot undo sends: 1
safe decision: DENY_BEFORE
safe database writes: 0
safe external sends: 0
safe owner decision: ALLOW
safe owner database writes: 1
safe owner external sends: 1
~~~

**Cách đọc:** Bob không phải owner. Hàm unsafe đã ghi và “gửi” trước khi trả `DENY_AFTER`; hai list vẫn có dữ liệu. Lệnh `unsafe.databaseWrites.clear()` chỉ **mô phỏng** việc DB write được khôi phục, còn externalMessages vẫn chứa event đã gửi. Hàm pre-checked deny trước nên không có side effects. Alice là owner được qua check rồi mới ghi.

Không lấy ví dụ này làm bằng chứng Spring transaction sẽ hoặc sẽ không rollback trong một cấu hình thật. Đó là vấn đề phải kiểm thử với real transaction manager và advisor ordering.

## 11. Integration test: assert denial VÀ zero side effects

Một test chỉ có:

~~~java
assertThrows(
    AccessDeniedException.class,
    () -> service.update(id, command)
);
~~~

**chưa đủ**. Nó không kiểm tra committed database state, outbox row, email sends, payment calls, cache writes hoặc broker publish.

### 11.1. Bộ kiểm thử tối thiểu

| Case | Expected security outcome | Side effects phải kiểm |
|---|---|---|
| User đúng owner, đủ `document:update` | Allow | Mutation đúng, event đúng một lần theo contract |
| User thiếu `document:update` | Deny trước body | DB/outbox/external = 0 |
| User đủ permission nhưng sai owner | Deny | DB giữ nguyên, external calls = 0 |
| User đúng owner nhưng sai tenant | Deny | Không mutate resource khác tenant |
| User anonymous | Deny | Không có business mutation |
| Resource đã khóa | Deny | Không lưu/publish |
| Owner đổi đồng thời | Conflict/deny | Không commit mutation trái phép |
| `@PostAuthorize` trên read-only method | Deny returned object | Không ghi DB/không gửi dữ liệu ra ngoài |
| `@PostAuthorize` trên write method | Có nguy cơ deny muộn | Test phải phát hiện leaked side effects |
| Transaction advisor order khác | Deny | Kiểm commit/rollback thật |
| Inner `REQUIRES_NEW` | Outer deny | Phát hiện inner commit ngoài ý muốn |
| Outbox transactional rollback | Deny | Business row và outbox row đều không commit |
| Email trước denial | Deny | Test phát hiện email invocation; thiết kế phải ngăn |
| Proxy bypass bằng `this.` hoặc `new` | Bị phát hiện | Không cho đường gọi bỏ qua policy |

### 11.2. Test Spring Security thật

Một test skeleton thuộc Spring Boot project:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class DocumentCommandSecurityTest {
    @Autowired
    DocumentCommandService commands;

    @Autowired
    DocumentRepository repository;

    @Test
    @WithMockUser(username = "bob", authorities = "document:update")
    void otherOwnerCannotModifyDocument() {
        long id = 7L; // Fixture: document 7 thuộc Alice.
        assertThrows(AccessDeniedException.class,
                () -> commands.update(id, new UpdateCommand()));

        // Trong test đầy đủ:
        // - Đọc lại DB ở transaction mới và assert row không đổi.
        // - Assert outbox không có event mới.
        // - Verify notification/payment mocks không được gọi.
    }
}
~~~

**Đây là skeleton, không phải test hoàn chỉnh copy-paste.** Nó cần service/repository types, fixture Alice/Bob và các assertions xác minh state thật. Không tuyên bố QA production đã pass chỉ vì `assertThrows` pass.

### 11.3. Tránh test rollback che một commit trái phép

Spring Test có thể tự rollback transaction của test nếu test annotated `@Transactional`. Điều này có thể làm bạn không nhìn thấy commit/sự kiện theo cách production.

Cách kiểm:

1. Tạo fixture đã commit.
2. Gọi protected service qua Spring-managed proxy.
3. Để transaction của use case kết thúc thật.
4. Đọc committed state từ persistence context/transaction mới.
5. So fields, version, status, audit/outbox.
6. Verify external mock interactions chính xác.
7. Với concurrency, dùng transaction/threads tách biệt và DB phù hợp môi trường.

Không dựa duy nhất vào `404`/`403` HTTP response hoặc in-memory entity cache để chứng minh an toàn.

## 12. Advisor ordering: phải đo thay vì đoán

Một lời gọi có thể đi qua:

~~~text
Security before-method advice
Transaction advice
Retry advice
Caching advice
Custom audit advice
Business method
Security after-method advice
~~~

Sơ đồ chỉ minh họa, **không cam kết thứ tự cụ thể**. Ngoài `@Order` và advisor order constants, cấu hình transaction/method security/version có thể ảnh hưởng nesting.

Để làm rõ runtime:

- Xác định phiên bản Spring Security/Spring Framework/Boot.
- Xem `@EnableMethodSecurity`, `@EnableTransactionManagement`, `@Order`, custom advisors.
- Bật log transaction begin/commit/rollback và method authorization trong staging.
- Test denial sau method có ghi DB thật: DB commit hay rollback?
- Test `REQUIRES_NEW`/event listener và cross-service effects.
- Chạy lại regression tests khi nâng version.

Không được sử dụng thứ tự hai annotation ở code làm căn cứ xác định transaction nesting.

## 13. Các dấu hiệu thiết kế cần sửa ngay

| Dấu hiệu | Rủi ro | Hướng sửa |
|---|---|---|
| `@PostAuthorize` là check duy nhất trên update/delete | Check sau mutation | `@PreAuthorize` + object policy |
| 403 được coi như proof “không ghi” | Commit có thể đã xảy ra | Test committed state |
| Email/payment trong method có postcheck | Không thể thu hồi ngoại vi | Precheck trước outbound call |
| `@Transactional` được xem là undo mọi thứ | Chỉ các resources thuộc transaction | Phân tích boundary + outbox |
| `REQUIRES_NEW` trước deny | Inner commit độc lập | Tránh business write trước auth |
| Catch rồi nuốt `AccessDeniedException` | Transaction có thể tiếp tục | Fail closed/propagate |
| Gửi event trước commit | Consumer thấy sự kiện không nhất quán | Outbox/transaction-aware dispatch |
| Dùng `AFTER_COMMIT` như cách cứu postcheck | Commit có thể trước postcheck | Sửa thứ tự authorization |
| Precheck chỉ so ownerId client gửi | Owner spoof | Query trusted resource |
| Thiếu tenant/owner check | BOLA/IDOR | Object-level authorization |
| Race giữa precheck và write | TOCTOU | Lock, version, conditional update |
| Protected method bị gọi qua `this.` | Proxy bypass | Tách bean/integration test |
| Test chỉ assert exception | Bỏ sót side effects | DB + broker + email assertions |

## 14. Checklist trước khi merge

- [ ] Method có thay đổi DB, cache, file, message, email, payment hoặc state nào không?
- [ ] Nếu có, quyền đã được kiểm **trước điểm side effect đầu tiên** chưa?
- [ ] `@EnableMethodSecurity` đã bật, bean/method invocation đi qua Spring proxy?
- [ ] Quyền chức năng và quyền trên **resource thật** (owner/tenant/state) đều được kiểm?
- [ ] Không dùng ownerId/tenantId do client tự khai làm proof?
- [ ] Có lock/version/conditional write chống TOCTOU?
- [ ] Có phân biệt transaction begin, flush, commit và postcheck?
- [ ] Test advisor order, rollback rule và propagation của deployment thật?
- [ ] Có biết `REQUIRES_NEW` hoặc service khác có thể commit độc lập không?
- [ ] External effects được thực hiện sau authorization và có idempotency/retry?
- [ ] Outbox được commit atomically với business row khi cần?
- [ ] `@TransactionalEventListener` không bị hiểu nhầm thành bảo đảm delivery?
- [ ] Nếu có `@PostAuthorize` trên read, method body thật không có business side effects?
- [ ] Test denials assert **DB unchanged, outbox unchanged, external calls = 0**?
- [ ] Test không bị test-level rollback che committed state?
- [ ] Không có đường gọi bypass security qua self-invocation, instance `new` hoặc methods không thể proxy?
- [ ] Có audit và monitoring cho thao tác không thể hoàn tác?

**Kết luận:** *Dùng `@PostAuthorize` để giới hạn kết quả được trả về sau một lời gọi phù hợp. Với thao tác thay đổi trạng thái, kiểm quyền trước side effect, kiểm resource trong transaction và xử lý external effects theo hợp đồng đáng tin cậy.*

## 15. Tự kiểm tra kiến thức

**1. `@PostAuthorize` chạy khi nào?**  
Sau khi method body đã tạo kết quả cho after-method interceptor.

**2. Nếu `@PostAuthorize` từ chối, `repository.save` có chắc chưa chạy?**  
Không; body có thể đã gọi save/flush trước denial.

**3. HTTP 403 có chứng minh DB không đổi không?**  
Không. Cần đọc committed state và kiểm outbound side effects.

**4. `@Transactional` luôn rollback khi postcheck deny?**  
Không. Còn advisor order, transaction boundary, propagation và rollback rules.

**5. Vì sao email đã gửi khó hoàn tác?**  
External delivery không thuộc local DB transaction; message có thể đã đến người nhận.

**6. `@PreAuthorize` bảo vệ write tốt hơn ở điểm nào?**  
Nó có thể chặn trước khi body chạy, nếu invocation được proxy và policy đúng.

**7. Vì sao vẫn cần check owner/tenant trong transaction?**  
Để chống trạng thái thay đổi giữa precheck và mutation (TOCTOU).

**8. Outbox có sửa được write trái phép đã commit không?**  
Không. Outbox đảm bảo liên kết DB + event intent; authorization phải đúng trước commit.

**9. `AFTER_COMMIT` listener có đảm bảo không gửi khi postcheck deny?**  
Không nếu commit đã xảy ra trước postcheck.

**10. Vì sao `REQUIRES_NEW` nguy hiểm ở đây?**  
Nó có physical transaction độc lập, có thể commit bất chấp outer denial/rollback.

**11. Test chỉ assert `AccessDeniedException` có đủ?**  
Không; phải kiểm committed DB state và những lời gọi bên ngoài.

**12. Compensation có giống rollback không?**  
Không; compensation là action mới, không bảo đảm xóa toàn bộ hậu quả đã xảy ra.

## 16. Tài liệu tham khảo chính thức

- Spring Security – **Method Security**, mục *Authorizing Method Results with @PostAuthorize* và cảnh báo với database writes: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security – **Method Security Testing**: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Framework – **Declarative Transactions: Rolling Back**: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework – **Transaction Propagation** và `REQUIRES_NEW`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework – **Transaction-bound Events** và `@TransactionalEventListener`: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework – **Proxying Mechanisms**: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Security – **Authorization Architecture**: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
