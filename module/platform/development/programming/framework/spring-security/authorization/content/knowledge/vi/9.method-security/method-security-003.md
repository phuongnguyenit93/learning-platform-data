# @PreAuthorize, @PostAuthorize, @PreFilter và @PostFilter trong Spring Security

Spring Security có thể kiểm soát quyền tại URL và tại **method của Spring-managed service**. Bốn annotation `@PreAuthorize`, `@PostAuthorize`, `@PreFilter` và `@PostFilter` đều thuộc **method security**, nhưng **không cùng chức năng**. Hai annotation `Authorize` quyết định được phép hay bị từ chối, còn hai annotation `Filter` loại từng phần tử của input/output. Dùng nhầm chúng đặc biệt nguy hiểm khi xử lý hàng loạt tài nguyên hoặc khi method đã gây side effect trước lúc hậu kiểm.

Bài viết giải thích cơ chế trên **Spring Security 6.x, Spring Boot 3.x, Java 17+ và Servlet stack**: cách bật method security, vòng đời interceptor, cú pháp SpEL, xử lý input/output và tenant, lỗi proxy, chi phí lọc, giao dịch và kiểm thử. Các snippet framework phải đặt trong dự án Spring có dependencies/bean thật. Phần Java thuần ở cuối chạy độc lập để quan sát chính xác sự khác nhau về thứ tự và hành vi.

## 1. Bốn annotation khác nhau thế nào?

| Annotation | Khi nào? | Mục tiêu | Khi không thỏa |
| --- | --- | --- | --- |
| `@PreAuthorize` | **Trước method body** | Kiểm tra cả lời gọi có được chạy không. | Mặc định ném `AccessDeniedException`; body chưa chạy. |
| `@PostAuthorize` | **Sau method body** | Kiểm tra caller có được nhận object kết quả hay không. | Mặc định ném `AccessDeniedException`; body đã chạy. |
| `@PreFilter` | **Trước body** | Lọc từng phần tử trong một tham số được hỗ trợ. | Loại phần tử không thỏa; không tự từ chối cả batch. |
| `@PostFilter` | **Sau body** | Lọc từng phần tử trong collection kết quả. | Loại phần tử không thỏa; method đã chạy. |

Sơ đồ tư duy:

~~~text
Caller -> Spring AOP proxy
  | @PreFilter:    [docA, docB, docC] -> [docA, docC]
  | @PreAuthorize: allowed ? YES : throw AccessDeniedException
  v
METHOD BODY (có thể truy vấn/ghi/gọi API bên ngoài)
  | @PostAuthorize: result có thể được trao cho caller không?
  | @PostFilter:    [docA, docB, docC] -> [docA, docC]
  v
Caller nhận result hoặc exception
~~~

Sơ đồ chỉ minh họa **trước/sau** và mục đích. Spring AOP có interceptor riêng cho từng annotation; thứ tự cố định thực tế phụ thuộc advisor ordering. Nếu kết hợp nhiều annotation trong cùng method, hãy test từng điểm chặn. Không được lặp hai `@PreAuthorize` trên cùng method vì Spring Security không hỗ trợ repeated annotation cùng loại theo kiểu đó; dùng một biểu thức logic hoặc policy bean rõ ràng.

**Để nhớ:** `Authorize` = quyết định **ALLOW/DENY**, `Filter` = biến đổi **tập phần tử**. `Post` = body **đã chạy**; không tự hoàn tác side effect.

## 2. Bật method security và hiểu Spring AOP proxy

Trong Spring Boot 3, `spring-boot-starter-security` **không tự bật method-level authorization**. Cần cấu hình:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Với Spring Security 6.5, `@EnableMethodSecurity` mặc định kích hoạt cả bốn annotation trong nhóm pre/post. Nếu cấu hình `@EnableMethodSecurity(prePostEnabled = false)`, chúng không tự hoạt động. Cơ chế `@Secured` và `@RolesAllowed` thuộc những interceptor khác và không phải cùng annotation.

Các dependencies Spring Boot thường dùng trong Gradle Groovy:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Đây chỉ là **phần dependencies**, không phải build.gradle đầy đủ. Chọn phiên bản do Spring Boot quản lý. `@EnableGlobalMethodSecurity` của thế hệ cũ nên được thay bằng `@EnableMethodSecurity` cho dự án Spring Security 6 mới.

Để annotation có hiệu lực, **caller phải gọi qua proxy của bean được Spring quản lý**:

~~~text
HTTP -> controller bean -> service proxy -> method security interceptor
message consumer bean ----^                      |
scheduled job bean ------^                       v
                                           service method body
~~~

Những trường hợp dễ bỏ qua proxy: tạo service bằng `new`, gọi `this.securedMethod()` trong cùng instance (self-invocation), method private/final không thể intercept theo kiểu proxy đang dùng, hoặc bean không được component scan. Một integration test dùng bean inject từ Spring là bắt buộc để tránh tin nhầm annotation chỉ hiện diện ở source.

## 3. Các interceptor và SpEL nhận dữ liệu gì?

Spring Security dùng những thành phần tiêu biểu:

| Annotation | Interceptor/manager |
| --- | --- |
| `@PreAuthorize` | `AuthorizationManagerBeforeMethodInterceptor` kết hợp `PreAuthorizeAuthorizationManager`. |
| `@PostAuthorize` | `AuthorizationManagerAfterMethodInterceptor` kết hợp `PostAuthorizeAuthorizationManager`. |
| `@PreFilter` | `PreFilterAuthorizationMethodInterceptor`. |
| `@PostFilter` | `PostFilterAuthorizationMethodInterceptor`. |

SpEL được xử lý qua `MethodSecurityExpressionHandler` (mặc định thường dùng `DefaultMethodSecurityExpressionHandler`) với `Authentication`/principal và method invocation. Các biến đặc biệt:

| Ký hiệu | Nghĩa |
| --- | --- |
| `authentication` | Caller `Authentication` từ security context. |
| `principal` | Principal của Authentication, có type tùy auth mechanism. |
| `hasAuthority('DOC_READ')` | Xét chuỗi authority nguyên văn. |
| `hasRole('ADMIN')` | Theo prefix mặc định yêu cầu `ROLE_ADMIN`. |
| `#id`, `#documentId` | Tham số method khi resolver lấy được tên. |
| `@policy.mayRead(...)` | Gọi Spring bean có logic quyền nghiệp vụ. |
| `returnObject` | Giá trị method đã trả, dùng trong `@PostAuthorize`. |
| `filterObject` | Từng phần tử của input/output khi filter. |
| `filterObject.value` | Giá trị của Map entry khi lọc Map. |
| `filterTarget="items"` | Chọn tên tham số cần `@PreFilter` lọc. |

`#id` cần tên tham số lúc runtime: có thể dùng Java compiler flag **`-parameters`** hoặc `@P("id")` của Spring Security. `principal.tenantId` không phải property mặc định của mọi user/JWT; cần xác định Authentication/claims đã xác thực thực tế. Logic phức tạp nên đặt trong **policy bean Java** thay vì biểu thức SpEL dài khó test.

## 4. @PreAuthorize: ngăn thực thi khi không có quyền

Một method nhạy cảm yêu cầu authority:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ExportService {

    @PreAuthorize("hasAuthority('REPORT_EXPORT')")
    public String requestExport() {
        return "created";
    }
}
~~~

Người không có `REPORT_EXPORT` bị từ chối trước body. Đây là lựa chọn phù hợp để bảo vệ **hành động ghi hoặc tác vụ có side effect**, nhưng phải kiểm tra thêm quyền trên tài nguyên cụ thể.

Các dạng SpEL độc lập:

~~~java
@PreAuthorize("isAuthenticated()")
@PreAuthorize("hasRole('ADMIN')")
@PreAuthorize("hasAuthority('DOC_READ')")
@PreAuthorize("hasAnyAuthority('DOC_READ', 'DOC_ADMIN')")
@PreAuthorize("hasAuthority('DOC_WRITE') and #id > 0")
~~~

Đây là các **ví dụ annotation riêng**, không nên đặt cả năm trên một method. Với `hasRole('ADMIN')`, mặc định cần `ROLE_ADMIN`; `hasAuthority('DOC_READ')` cần authority chính xác. JWT resource server thường chuyển scope thành dạng `SCOPE_...`, không tự cho người có `SCOPE_admin` được `ROLE_ADMIN`.

Khi cần kiểm tra owner/tenant, gọi policy bean dựa trên dữ liệu **server**:

~~~java
@PreAuthorize(
    "hasAuthority('DOC_APPROVE') and @documentPolicy.canApprove(authentication, #documentId)")
public void approve(long documentId) {
    documentWriter.approveWithCurrentStateChecks(documentId);
}
~~~

Đoạn này là **pseudocode đặt trong service Spring**, cần bean `documentPolicy`, `documentWriter`, repository/transaction; không chạy chỉ với JDK. `#documentId` phải resolve được. Dùng alias tường minh:

~~~java
import org.springframework.security.access.method.P;

@PreAuthorize("@documentPolicy.canRead(authentication, #id)")
public DocumentView read(@P("id") long documentId) {
    return documentReader.find(documentId);
}
~~~

Nếu client gửi một DTO có field `owner="alice"`, đó **không** phải chứng cứ tài liệu thuộc Alice. Policy phải lấy owner/tenant/status đáng tin từ DB bằng ID. Đối với ghi dữ liệu, có thể xảy ra TOCTOU (check rồi record đổi trước khi write); bảo vệ bất biến gần transaction/update và dùng optimistic locking, row lock hoặc conditional update khi cần.

## 5. @PostAuthorize: kiểm tra returnObject nhưng body đã thực thi

Một truy vấn trả một tài khoản:

~~~java
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.stereotype.Service;

@Service
public class AccountLookupService {

    @PostAuthorize(
        "returnObject != null and returnObject.owner == authentication.name")
    public AccountView find(long accountId) {
        return accountRepository.loadView(accountId);
    }
}
~~~

Đây là **lớp minh họa cần AccountView/repository thực**, không biên dịch độc lập. `returnObject` là object trả về; SpEL so owner với caller hiện tại. Với Alice yêu cầu account của Bob, repository **đã chạy**, kết quả bị chặn **không trao cho Alice**. Cơ chế này hữu ích để chống IDOR ở *đường trả dữ liệu* cho những phương thức đọc không side effect.

~~~text
Caller -> body chạy -> trả AccountView
                         |
                         v
                   @PostAuthorize
                     /         \
                    /           \
                TRUE             FALSE
                 |                 |
          caller nhận result   AccessDeniedException
~~~

**Không dùng `@PostAuthorize` làm rào cuối cho transferMoney, deleteOrder, approvePayment, sendEmail, updateDatabase.** Với method có side effect, khi post-check fail thì side effect có thể **đã xảy ra**, kể cả response là 403. Kết hợp `@Transactional` chưa chắc bảo đảm hoàn tác tất cả: thứ tự interceptor và tác động ngoài DB (email/webhook) là vấn đề riêng. Spring Security 6.5 cũng cảnh báo về `@PostAuthorize` trên database writes.

Với result null, biểu thức truy `returnObject.owner` không có guard có thể lỗi khi đánh giá. Chọn chính sách null/not-found rõ (ví dụ 404 ở service hoặc fail-closed). Nếu method trả một danh sách, `@PostAuthorize` là **quyết định trên cả result**, không tự lọc từng phần tử — cần `@PostFilter` khi chủ đích là lọc list.

## 6. @PreFilter: chỉ giữ phần tử đầu vào hợp lệ

`@PreFilter` lọc từng phần tử của **tham số collection/array/map/stream được phiên bản hỗ trợ** trước khi body nhận dữ liệu:

~~~java
import java.util.List;
import org.springframework.security.access.prepost.PreFilter;
import org.springframework.stereotype.Service;

@Service
public class DraftService {

    @PreFilter("filterObject.owner == authentication.name")
    public int countOwned(List<DraftView> drafts) {
        return drafts.size();
    }
}
~~~

Đây là **mã Spring cần DraftView có owner và bean Spring**. Với input [draft Alice, draft Bob], Alice có thể chỉ gửi phần Alice vào body. Phần Bob **bị lọc bỏ**, không làm cả method mặc định ném AccessDeniedException. Vì vậy không dùng một prefilter làm bằng chứng rằng “lô có item sai sẽ bị từ chối”.

Với nhiều tham số, dùng `filterTarget`:

~~~java
@PreFilter(
    value = "filterObject.tenantId == @tenantContext.currentTenantId()",
    filterTarget = "items")
public void inspect(String batchId, List<WorkItem> items) {
    // items chứa phần tử đã qua prefilter
}
~~~

Đoạn này là snippet phụ thuộc bean `tenantContext`, DTO và tên param `items` có thể được phát hiện. SpEL `filterObject` chính là từng phần tử. Nếu input là **Map**, tài liệu Spring Security 6.5 đưa ví dụ với `filterObject.value` (mỗi map entry):

~~~java
@PreFilter("filterObject.value.owner == authentication.name")
public void inspectMap(Map<String, AccountView> items) {
    // Mỗi entry cần được đánh giá theo value.
}
~~~

Theo tài liệu 6.5, prefilter có thể xử lý arrays, collections, maps, streams còn mở; **kiểu cụ thể và version phải được test**. Một số implementation loại phần tử bằng `remove`, nên immutable `List.of(...)` có thể lỗi. Dùng mutable `ArrayList` trong test cho collection filtering; với stream tránh đối tượng đã tiêu thụ. Không suy rằng `@PreFilter` là một thuật toán kiểm tra batch atomic.

### Nếu lô phải all-or-nothing thì sao?

Giả sử caller yêu cầu duyệt ba hóa đơn 10,11,12 nhưng chỉ sở hữu 10. `@PreFilter` có thể loại 11/12 và vẫn duyệt 10. Đó là **partial success**, có thể vi phạm hợp đồng API, gây sai audit hoặc rò số lượng item được phép.

Nếu cần hủy cả lô khi một item sai phạm vi, nên:

1. Bảo vệ quyền gọi bằng `@PreAuthorize("hasAuthority('DOC_APPROVE')")`.
2. Tải **mọi document thật** theo ID/tenant từ DB.
3. Xác minh tất cả thuộc phạm vi, còn trạng thái cho phép, không trùng/sót ID.
4. Nếu **bất kỳ** điều kiện nào sai, throw một exception an toàn trước khi update.
5. Thực hiện cập nhật có kiểm tra trạng thái trong transaction, xử lý race.

Một pseudocode Java/Spring:

~~~java
@Transactional
@PreAuthorize("hasAuthority('DOC_APPROVE')")
public void approveAll(List<Long> ids) {
    List<Document> docs = repository.findAllById(ids);
    if (docs.size() != ids.size()) {
        throw new EntityNotFoundException();
    }
    if (!docs.stream().allMatch(d -> policy.mayApprove(actor.get(), d))) {
        throw new AccessDeniedException("Access denied");
    }
    repository.approveWithInvariantChecks(docs);
}
~~~

Mã trên thiếu những bean/kiểu do project định nghĩa, cần xử lý ID trùng, dữ liệu concurrent và transaction thật. **Không phải file độc lập**. Nếu API chủ đích cho phép xử lý subset, `@PreFilter` có giá trị, nhưng response và audit phải nói rõ cách xử lý một phần, không âm thầm báo “thành công toàn bộ”.

## 7. @PostFilter: lọc những gì caller được nhìn thấy sau query

`@PostFilter` dùng `filterObject` trên tập **giá trị trả về**:

~~~java
import java.util.ArrayList;
import java.util.List;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.stereotype.Service;

@Service
public class AccountSearchService {

    @PostFilter("filterObject.owner == authentication.name")
    public List<AccountView> findCandidates(String keyword) {
        return new ArrayList<>(repository.search(keyword));
    }
}
~~~

Repository **đã đọc dữ liệu** trước khi filter. Alice có thể chỉ nhận các phần tử owner Alice, nhưng dữ liệu owner Bob đã được load lên memory. Spring Security 6.5 mô tả hỗ trợ arrays, collections, maps, streams (nếu còn mở); với Map có thể dùng:

~~~java
@PostFilter("filterObject.value.owner == authentication.name")
public Map<String, AccountView> findMap() {
    return repository.loadMap();
}
~~~

Các snippet chỉ minh họa cú pháp, cần repository, types và Spring context. `@PostFilter` **không thay thế** điều kiện SQL theo tenant/owner.

Tại sao không dùng postfilter để phân trang?

- DB trả 20 item đầu, postfilter xóa 18 item thuộc người khác, caller thấy trang chỉ 2 item.
- Metadata như totalElements/totalPages vẫn được tính từ query chưa lọc.
- Data được load ngoài scope có thể gây N+1 khi đọc owner lazy.
- Nếu body đã ghi log/event/cache chứa item trước lọc, hậu lọc không thu hồi được.
- `Page<T>`/cursor response không tự được postfilter sửa đúng cấu trúc.

**Khuyến nghị:** trong hệ nhiều tenant, đưa predicate authorization vào repository/query, ví dụ `WHERE tenant_id = ? AND owner_id = ?` hoặc model sharing quyền phù hợp; `@PostFilter` chỉ là bảo vệ bổ sung khi dữ liệu nhỏ và semantics lọc rõ ràng. Với Map và immutable collection phải kiểm thử concrete type.

### So sánh PostAuthorize với PostFilter

`@PostAuthorize("returnObject.owner == authentication.name")` trên một object → nếu không phải owner thì DENY **cả kết quả**. `@PostFilter("filterObject.owner == authentication.name")` trên nhiều objects → loại từng phần tử, có thể trả list rỗng **vẫn 200**. Không lấy status 200 làm bằng chứng các item đã qua policy nếu method bị self-invocation bypass proxy.

## 8. Ví dụ service tổng hợp (mã Spring minh họa)

Giả định ứng dụng có `DocumentRepository`, `DocumentView`, `DocumentDraft` với getter `owner` và authentication setup:

~~~java
import java.util.ArrayList;
import java.util.List;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreFilter;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    private final DocumentRepository repository;

    public DocumentService(DocumentRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('DOC_READ')")
    public DocumentView read(long id) {
        return repository.findById(id);
    }

    @PostAuthorize(
        "returnObject != null and returnObject.owner == authentication.name")
    public DocumentView readOwned(long id) {
        return repository.findById(id);
    }

    @PreFilter(
        value = "filterObject.owner == authentication.name",
        filterTarget = "drafts")
    public int processDrafts(List<DocumentDraft> drafts, String batch) {
        return repository.processDrafts(drafts, batch);
    }

    @PostFilter("filterObject.owner == authentication.name")
    public List<DocumentView> listVisible() {
        return new ArrayList<>(repository.loadCandidates());
    }
}
~~~

**Đây là ví dụ API cần framework và các interface do ứng dụng viết, không chạy với JDK thuần.** Nó cố tình thiếu một số domain policies để minh họa chính xác phạm vi của annotation: `read` chỉ có quyền chung (chưa an toàn trước IDOR); `readOwned` chỉ xét owner (chưa tenant); `processDrafts` có thể xử lý một phần lô; `listVisible` load rồi mới filter. Production cần owner/tenant/status/permission từ dữ liệu tin cậy, all-or-nothing khi cần, và tối ưu repository theo phạm vi.

Không chồng cả bốn annotation lên một method chỉ để “bảo mật mạnh hơn”. Hãy chọn từng cơ chế theo hợp đồng chức năng, viết test thực thi và kiểm tra kiểu input/output.

## 9. Quan hệ với HTTP authorization và SecurityContext

Tầng HTTP có thể cấu hình:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/documents/**")
        .hasAuthority("DOC_READ")
    .anyRequest().denyAll()
);
~~~

Tầng method có thể áp thêm các annotation. Luồng kết quả:

~~~text
HTTP AuthorizationFilter
  DENY -> không đến controller
  ALLOW -> Controller -> Spring service proxy
             @PreAuthorize DENY -> body không chạy
             @PreAuthorize ALLOW -> body chạy
                @PostAuthorize DENY -> body đã chạy, không trả object
                @PostFilter -> có thể trả list rút gọn
~~~

HTTP 403 có thể do CSRF/filter, request authorization, method authorization hoặc policy service; phải xác minh **điểm gây từ chối**, không chỉ nhìn mã 403. Nếu service được gọi từ scheduler, message listener hoặc job, không có request HTTP đi qua `SecurityFilterChain`: method security và policy domain mới là lớp cần có. Với `@Async`/thread pool, `SecurityContextHolder` mặc định dựa vào ThreadLocal nên có thể không có authentication ở worker nếu không truyền context đúng cách.

## 10. Ví dụ Java 17 độc lập chứng minh bốn giai đoạn

Ví dụ sau **không dùng Spring** và cố ý dùng Java thuần để mô phỏng các quyết định. `preFilter`/`postFilter` của demo trả danh sách mới, không sao chép cách Spring interceptor thao tác trực tiếp với collection.

Lưu đúng tên **`FourMethodSecurityStagesDemo.java`**:

~~~java
import java.util.List;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;

public class FourMethodSecurityStagesDemo {
    record Actor(String user, String tenant, Set<String> authorities) {}
    record Document(int id, String owner, String tenant) {}

    static boolean hasAuthority(Actor actor, String authority) {
        return actor != null && actor.authorities().contains(authority);
    }

    static boolean visible(Actor actor, Document doc) {
        return actor != null && doc != null
                && actor.user().equals(doc.owner())
                && actor.tenant().equals(doc.tenant());
    }

    static List<Integer> ids(List<Document> docs) {
        return docs.stream().map(Document::id).toList();
    }

    static List<Document> preFilter(Actor actor, List<Document> incoming) {
        return incoming.stream().filter(doc -> visible(actor, doc)).toList();
    }

    static List<Document> postFilter(Actor actor, List<Document> returned) {
        return returned.stream().filter(doc -> visible(actor, doc)).toList();
    }

    static void require(boolean allowed) {
        if (!allowed) throw new SecurityException("Access denied");
    }

    static String readOne(Actor actor, Document doc, AtomicInteger bodyRuns) {
        require(hasAuthority(actor, "DOC_READ"));         // @PreAuthorize
        bodyRuns.incrementAndGet();                      // actual method body
        require(visible(actor, doc));                    // @PostAuthorize
        return "record-" + doc.id();
    }

    static int exportAllowed(Actor actor, List<Document> docs) {
        require(hasAuthority(actor, "DOC_EXPORT"));
        return preFilter(actor, docs).size();             // @PreFilter model
    }

    public static void main(String[] args) {
        Actor alice = new Actor("alice", "shop-a",
                Set.of("DOC_READ", "DOC_EXPORT"));
        Actor bob = new Actor("bob", "shop-a", Set.of("DOC_READ"));
        Actor guest = new Actor("guest", "shop-a", Set.of());
        Document first = new Document(10, "alice", "shop-a");
        Document second = new Document(11, "bob", "shop-a");
        Document crossTenant = new Document(12, "alice", "shop-b");
        List<Document> docs = List.of(first, second, crossTenant);
        AtomicInteger bodyRuns = new AtomicInteger();

        System.out.println("PreAuthorize Alice DOC_READ: "
                + hasAuthority(alice, "DOC_READ"));
        System.out.println("PreAuthorize guest DOC_READ: "
                + hasAuthority(guest, "DOC_READ"));
        System.out.println("PreFilter Alice IDs: " + ids(preFilter(alice, docs)));
        System.out.println("PostFilter Alice IDs: " + ids(postFilter(alice, docs)));
        System.out.println("PostFilter Bob IDs: " + ids(postFilter(bob, docs)));

        boolean deniedBefore = false;
        try {
            readOne(guest, first, bodyRuns);
        } catch (SecurityException ex) {
            deniedBefore = true;
        }
        System.out.println("PreAuthorize guest denied before body: " + deniedBefore);
        System.out.println("Body executions after pre-denial: " + bodyRuns.get());

        boolean deniedAfter = false;
        try {
            readOne(bob, first, bodyRuns);
        } catch (SecurityException ex) {
            deniedAfter = true;
        }
        System.out.println("PostAuthorize Bob denied after body: " + deniedAfter);
        System.out.println("Body executions after post-denial: " + bodyRuns.get());

        System.out.println("PostAuthorize Alice result: "
                + readOne(alice, first, bodyRuns));
        System.out.println("Body executions final: " + bodyRuns.get());
        System.out.println("Batch export accepted count: "
                + exportAllowed(alice, docs));
    }
}
~~~

Chạy trên JDK 17+:

~~~bash
javac --release 17 FourMethodSecurityStagesDemo.java
java FourMethodSecurityStagesDemo
~~~

Stdout chuẩn (đã xác minh bằng lệnh trên):

~~~text
PreAuthorize Alice DOC_READ: true
PreAuthorize guest DOC_READ: false
PreFilter Alice IDs: [10]
PostFilter Alice IDs: [10]
PostFilter Bob IDs: [11]
PreAuthorize guest denied before body: true
Body executions after pre-denial: 0
PostAuthorize Bob denied after body: true
Body executions after post-denial: 1
PostAuthorize Alice result: record-10
Body executions final: 2
Batch export accepted count: 1
~~~

Dòng body count bằng **0** sau pre-denial chứng minh chặn trước body. Count bằng **1** sau post-denial chứng minh hậu kiểm không ngăn body đã chạy. Alice chỉ thấy document 10; document 12 có owner Alice nhưng khác tenant nên bị lọc. Batch count bằng 1 chứng minh lọc chỉ giữ subset, không tự ném lỗi cho toàn bộ lô.

## 11. Kiểm thử method security thật trong Spring Boot

Spring Security Test có `@WithMockUser` để mô phỏng `Authentication` và kiểm tra service trực tiếp qua Spring proxy:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class DocumentMethodSecurityIT {
    @Autowired DocumentService documents;

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void allowedRead() {
        assertNotNull(documents.read(10L));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "OTHER_PERMISSION")
    void deniedRead() {
        assertThrows(AccessDeniedException.class,
                () -> documents.read(10L));
    }
}
~~~

Đây là **test skeleton** cần repository fixtures và Spring Test context thực; không chạy độc lập với JDK. Với `@PreAuthorize`, bổ sung spy/counter chứng minh method body **chưa chạy** khi DENY. Với `@PostAuthorize`, test owner đúng/sai và chứng minh repository lookup **đã chạy** khi hậu kiểm DENY. Với `@PreFilter`, dùng mutable `ArrayList` nhiều owner, kiểm tra input **mà body thấy** và trường hợp `filterTarget`. Với `@PostFilter`, kiểm tra result chỉ chứa item hợp lệ, map entry đúng và pagination policy.

Ma trận test:

| Ca thử | Kỳ vọng |
| --- | --- |
| User thiếu authority, `@PreAuthorize` | Exception, body chưa chạy. |
| Có authority nhưng khác tenant | Domain policy vẫn DENY. |
| `@PostAuthorize` trả object của người khác | Body đã chạy, caller không nhận result. |
| `@PreFilter` nhận batch Alice/Bob | Body chỉ thấy subset, nếu nghiệp vụ cho phép. |
| Batch phải all-or-nothing | Một phần tử sai → reject toàn bộ, không partial commit. |
| `@PostFilter` trả list nhiều owner | Chỉ owner hợp lệ, không lộ item khác. |
| Map input/output | Biểu thức dùng đúng `filterObject.value`. |
| Phân trang nhiều tenant | Filter tại query, total count hợp lệ. |
| Gọi từ bean/job ngoài HTTP | Proxy và security context vẫn cần đúng. |
| Self-invocation/private/final | Test phát hiện proxy bypass. |

Một test `MockMvc` trả 403 **không đủ** chứng minh method annotation làm việc, vì `AuthorizationFilter` hoặc CSRF có thể chặn trước controller. Phải test service riêng, rồi mới test HTTP→controller→service.

## 12. Những lỗi phổ biến

1. **Quên `@EnableMethodSecurity`.** → Bật cấu hình và test negative.
2. **Dùng `@PostAuthorize` để bảo vệ method ghi.** → Chặn quyền trước side effect và bảo vệ transaction.
3. **Tưởng `@PreFilter` từ chối cả batch.** → Nó lọc phần tử; cần all-or-nothing policy nếu nghiệp vụ đòi.
4. **Tưởng `@PostFilter` tối ưu hóa query.** → Lọc trong DB theo owner/tenant thay vì tải tất cả.
5. **Dùng immutable collection vào interceptor cần remove.** → Test kiểu cụ thể, dùng mutable collection khi cần.
6. **Quên `filterTarget` hoặc tên tham số không resolve.** → Kiểm tra `-parameters`/`@P`.
7. **Lọc Map như List.** → Chú ý `filterObject.value`.
8. **Tham chiếu `returnObject.owner` mà không xử lý null.** → Fail-closed hoặc not-found rõ ràng.
9. **Chỉ đọc owner từ DTO do client gửi.** → Truy vấn record server đáng tin.
10. **Service tự gọi method có annotation trong cùng instance.** → Gọi qua proxy/bean khác.
11. **Nhầm `ROLE_ADMIN` với `SCOPE_admin`.** → Mapping authorities đúng.
12. **Bỏ qua actor/tenant ở background thread.** → Propagate context hoặc service identity có chủ đích.
13. **Chỉ test response 200/403.** → Test stage-specific, body counter, input/output và domain policy.

## 13. Checklist triển khai

- [ ] Đã bật method security và gọi qua Spring proxy.
- [ ] Dùng `@PreAuthorize` cho quyền thực hiện trước side effect.
- [ ] Dùng `@PostAuthorize` khi cần xét **một kết quả đọc**, không dùng làm chốt cuối cho ghi.
- [ ] Dùng `@PreFilter` chỉ khi API **cho phép xử lý subset**, nếu không thì reject toàn batch.
- [ ] Dùng `@PostFilter` cho collection nhỏ phù hợp; đặt data-scope lớn ở DB/query.
- [ ] Quyền chung và owner/tenant/state thực được kiểm tra trên dữ liệu server, không tin DTO.
- [ ] Xác minh `filterObject`, Map entry, `filterTarget`, nullable return, immutable collections.
- [ ] Có test pre-denial trước body và post-denial sau body.
- [ ] Có test quyền sai, khác tenant, input/output nhiều owner và concurrent writes.
- [ ] Có test service gọi qua HTTP và ngoài HTTP; không tin security context tự lan sang mọi async thread.
- [ ] Không coi lỗi 403 ở HTTP là bằng chứng annotation service đúng.

**Kết luận:** `@PreAuthorize`/`@PostAuthorize` ra quyết định **cho phép hay từ chối** trước/sau lời gọi; `@PreFilter`/`@PostFilter` **lọc phần tử** trước/sau method. Phải phân biệt hai loại hành vi này để bảo vệ dữ liệu đúng ranh giới: **chặn trước tác dụng phụ, không âm thầm partial update khi cần atomic batch và đẩy data-scope xuống truy vấn khi quy mô lớn**.

### Tài liệu tham khảo chính thức

- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — @PreAuthorize API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/prepost/PreAuthorize.html)
- [Spring Security 6.5 — @PostAuthorize API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/prepost/PostAuthorize.html)
- [Spring Security 6.5 — @PreFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/prepost/PreFilter.html)
- [Spring Security 6.5 — @PostFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/prepost/PostFilter.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
