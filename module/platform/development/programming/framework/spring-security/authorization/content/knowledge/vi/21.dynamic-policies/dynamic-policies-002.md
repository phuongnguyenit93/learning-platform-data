# Thiết kế kiểm tra theo chủ thể, tài nguyên, hành động và ngữ cảnh trong Spring Security

## 1. Vấn đề: cùng một người dùng, cùng một chức năng, nhưng kết quả có thể khác

Trong ứng dụng nhỏ, việc phân quyền thường bắt đầu bằng `hasRole("ADMIN")` hoặc `hasAuthority("document:read")`. Quy tắc đó hữu ích, nhưng chưa đủ cho các tình huống như:

- Alice có quyền sửa tài liệu **do mình sở hữu**, không sửa được tài liệu riêng tư của Bob.
- Alice có vai trò EDITOR trong tenant A nhưng chỉ là VIEWER trong tenant B.
- Bob được chia sẻ quyền đọc Document 42 **đến 10:00**, nhưng không được tải file gốc.
- Người duyệt hóa đơn phải thuộc bộ phận tài chính, không được tự duyệt hóa đơn của mình và chỉ được duyệt khi hóa đơn ở trạng thái `PENDING`.
- Quản trị viên có thể thực hiện một thao tác nhạy cảm chỉ khi đã xác thực đa yếu tố theo chính sách hiện tại.
- Một khách hàng không được xem dữ liệu khi tài khoản bị khóa, dù token đăng nhập chưa hết hạn.

Vì vậy, quyết định cấp quyền cần nhiều thông tin hơn tên role:

```text
allow = policy(subject, resource, action, context)
```

Trong đó:

- **Subject (chủ thể):** ai hoặc tác nhân nào đang yêu cầu thao tác.
- **Resource (tài nguyên):** chính xác đối tượng nào sẽ được đọc/ghi.
- **Action (hành động):** quyền nào đang được yêu cầu, ví dụ READ, EDIT, DELETE, APPROVE.
- **Context (ngữ cảnh):** các điều kiện có liên quan tại thời điểm đánh giá: tenant, trạng thái tài khoản, workflow, thời gian, loại authentication, quan hệ chia sẻ, môi trường thực thi...

Đó là cách thiết kế một **chính sách động**: quyền không chỉ được tính từ một chuỗi role tĩnh, mà từ các thuộc tính/quan hệ/trạng thái đáng tin **ở thời điểm thực hiện thao tác**.

Mục tiêu bài học là thiết kế cơ chế kiểm tra **có thể kiểm thử, giải thích, audit, cập nhật và áp dụng nhất quán** với Spring Security, tránh cả lỗ hổng IDOR/BOLA lẫn việc nhúng những điều kiện phân quyền rời rạc khắp controller.

## 2. Phân biệt Authentication, Authorization và dữ liệu quyết định

| Câu hỏi | Cơ chế | Ví dụ |
| --- | --- | --- |
| Ai đang gọi? | Authentication | JWT đã xác minh với subject Alice |
| Có quyền dùng chức năng không? | Coarse authorization | Alice có `document:read` |
| Có quyền trên đối tượng này không? | Resource authorization | Document 42 thuộc tenant Alice được phép |
| Có được làm hành động này trong trạng thái hiện tại không? | Contextual policy | Document chưa archived, grant còn hiệu lực |
| Nếu được, dữ liệu nào có thể xuất ra? | Data/property authorization | Chỉ trả field được phép, không lộ private notes |

Trong Spring Security, `Authentication` nằm trong `SecurityContext`; `GrantedAuthority` thể hiện những authority được cấp. `AuthorizationManager<T>` đánh giá quyền trên một đối tượng/ngữ cảnh bảo vệ, ví dụ HTTP request hay method invocation. `AuthenticationManager` là API phục vụ **xác thực** và không phải công cụ tự quyết định ACL cho Document 42.

Một principal được xác thực **không tự động** được đọc mọi object. Một user có `ROLE_EDITOR` cũng **không tự động** được sửa object trong tất cả tenant, workflow và phân loại dữ liệu.

### Hai tầng kiểm tra nên phối hợp

```text
HTTP / SecurityFilterChain
  -> request phải authenticated hoặc có coarse authority
         |
         v
Application service
  -> kiểm tra subject + resource + action + context
         |
         v
Repository / database
  -> query/mutation được scope theo tenant, owner, ACL
         |
         v
Response DTO / side effects
  -> chỉ đưa dữ liệu đã được phép ra ngoài
```

Tầng request giúp chặn truy cập sớm; tầng service/domain bảo vệ các đường gọi ngoài HTTP; tầng dữ liệu làm **defense in depth** và giảm rủi ro check-then-use. Không dựa vào việc chỉ ẩn nút trên frontend.

## 3. Subject: dùng danh tính đã xác minh, không dùng identity do client tự khai

**Subject** nên được mô hình hóa bằng các thuộc tính cần thiết và được xác minh:

| Thuộc tính | Ví dụ | Lưu ý |
| --- | --- | --- |
| `subjectId` | `u-1001` | ID nội bộ ổn định, tránh dùng display name |
| `issuer` | IdP/issuer đã được tin cậy | Cần khi nhiều identity providers có subject trùng |
| `authorities` | `document:read`, `invoice:approve` | Có thể global hoặc tenant-scoped; phải biết phạm vi |
| `tenantMemberships` | Alice là EDITOR ở A, VIEWER ở B | Đọc từ nguồn đáng tin hoặc claims có vòng đời rõ |
| `accountStatus` | ACTIVE/SUSPENDED | Có thể thay đổi sau khi token phát hành |
| `authenticationStrength` | Password, MFA/WebAuthn | Dùng cho step-up/risk policy nếu thực sự cần |
| `delegation` | Service acting-on-behalf-of user | Cần xác nhận scope và người ủy quyền |

**Đừng** lấy `request.userId`, `X-User-Id`, email trong JSON hoặc role trong form làm subject. Đó là dữ liệu đầu vào có thể sửa được.

Với JWT, `sub`, `iss`, `aud` chỉ đáng tin sau khi Resource Server đã xác minh token theo cấu hình issuer/chữ ký/audience/expiry thích hợp. `Authentication.getName()` có thể được tùy biến theo loại principal; nếu dùng nhiều issuer, cần namespace hoặc map về ID nội bộ tránh hai subject từ hai issuer cùng mang một giá trị chuỗi.

### User và service principal

Đừng mặc định mọi subject là con người. Một worker, scheduled job, API client hoặc service account cũng phải có identity và scope rõ. Nếu worker tạo báo cáo hộ Alice, phải quyết định nó:

1. Dùng **quyền của chính service principal** đã được phê duyệt?
2. Dùng **delegated permission** của Alice có hạn và giới hạn tài nguyên?
3. Có cần kiểm tra lại membership của Alice khi job thực thi hay không?

Câu trả lời là một phần của policy nghiệp vụ, không được suy ra từ việc “không có HTTP session” là toàn quyền.

## 4. Resource: xác minh đối tượng thật, không tin thuộc tính do client gửi

**Resource** có thể là entity trong database, object storage key, hóa đơn, project, file, task, thông điệp, bản ghi search hoặc hành động tạo mới.

Ví dụ thuộc tính của `Document`:

```text
Resource:
  type: Document
  id: 42
  tenantId: tenant-a
  ownerSubjectId: alice
  projectId: 10
  classification: INTERNAL
  status: ACTIVE
  deleted: false
  version: 7
```

Những trường này nên được lấy từ **nguồn server đáng tin**. Nếu client gửi:

```json
{"documentId":42,"ownerSubjectId":"alice","tenantId":"tenant-a"}
```

thì `ownerSubjectId` và `tenantId` không được sử dụng làm bằng chứng để cấp quyền. Chỉ có ID là một **yêu cầu tra cứu**; server phải tìm document thật rồi xem tenant/owner từ database hoặc nơi lưu trữ đã kiểm soát.

### IDOR/BOLA

Người dùng có `document:read` gửi ID của người khác là trường hợp kinh điển. Tham chiếu có thể xuất hiện trong path, query, body, form, GraphQL hoặc batch IDs. UUID khó đoán **không thay thế** kiểm tra quyền khi ID đã bị lộ.

Đối với list/search/export, quyền phải được áp dụng trên **toàn bộ tập dữ liệu trả ra**, không chỉ object detail. Query toàn bộ rồi lọc sau pagination có thể lộ số lượng object, tốn tài nguyên và gây sai count.

### Khi resource chưa tồn tại

Với `POST /projects/10/documents`, tài liệu chưa có ID. Quy tắc đúng là kiểm tra **CREATE_DOCUMENT trên Project 10** và tenant, status, quota, quyền của subject trước khi tạo mới. Không mặc định `hasPermission(null, "CREATE")` phải cho phép.

## 5. Action: không dùng một cờ "được truy cập" cho mọi thao tác

Một tài nguyên thường có các hành động riêng:

| Action | Ví dụ điều kiện |
| --- | --- |
| `READ` | Owner hoặc share READ còn hiệu lực |
| `EDIT` | Có quyền sửa, document còn editable, field được phép |
| `DELETE` | Owner hoặc admin trong đúng tenant, chưa bị legal hold |
| `APPROVE` | Người duyệt hợp lệ, không phải creator, workflow PENDING |
| `SHARE` | Có quyền chia sẻ, không cấp vượt quyền của mình |
| `EXPORT` | Có quyền xuất dữ liệu và tuân thủ classification |
| `CREATE` | Có quyền trong project/collection đã tồn tại |
| `TRANSFER_OWNER` | Có quyền quản trị và receiver hợp lệ |

**READ ≠ EDIT ≠ DELETE ≠ SHARE ≠ EXPORT.** Đừng sử dụng `canRead` thay cho `canDelete` vì cả hai cùng nhắm Document 42. Một user có thể đọc hóa đơn nhưng không có quyền xuất hàng loạt hay duyệt hóa đơn đó.

Hệ thống nên chuẩn hóa tên action (enum hoặc typed object), tránh ghép chuỗi tùy tiện từ client rồi dùng làm biểu thức SpEL. Nếu cần action tùy biến theo domain, định nghĩa contract rõ ràng, không gộp tất cả thành `"access"`.

## 6. Context: điều kiện thời điểm và môi trường

**Context** khác resource state: nó mô tả thông tin bổ sung có thể làm quyền thay đổi theo mỗi lần gọi. Ví dụ:

- Tenant/workspace đang được chọn **và đã xác minh membership**.
- Thời gian server: grant từ `validFrom` tới `expiresAt`.
- Authentication strength: MFA/step-up đã hoàn thành theo tiêu chí tin cậy.
- Account có bị suspended, membership có active?
- Project có đang locked, invoice có ở bước PENDING?
- Địa chỉ IP/vùng mạng/trạng thái thiết bị nếu có nguồn xác thực đáng tin.
- Tính chất thao tác: bulk export, amount/limit, risk level, số bản ghi.
- Delegation/impersonation đã được phê duyệt hay chưa.
- Phiên bản policy/config và trạng thái feature rollout.

### Độ tin cậy của context

Không phải mọi trường context đều có độ tin cậy như nhau:

| Context | Nguồn phù hợp | Bẫy |
| --- | --- | --- |
| `now` | `Clock` server/DB | Không dựa vào `Date.now()` từ browser |
| `tenantId` | Selector từ request **đã verify membership** | `X-Tenant-Id` không tự chứng minh quyền |
| MFA | Authentication đã được IdP/AS xác minh và có assurance claims hợp lệ | Header `X-MFA-Complete: true` do client gửi |
| `document.status` | Database có transaction/locking phù hợp | Dùng JSON client tự khai status=PENDING |
| Source IP | Chuỗi proxy/trust config được thiết lập an toàn | Tin `X-Forwarded-For` bất kỳ |
| Environment/feature flag | Server config/remote configuration được kiểm soát | User tùy chỉnh flag authorization |
| Share expiry/revoke | Grant store đáng tin | JWT còn hạn ≠ share còn hạn |

Nếu một điều kiện quan trọng **không thể xác minh** (timeout, missing context, invalid tenant), mặc định **DENY** hoặc trả lỗi hạ tầng an toàn thay vì tự cấp quyền. **Fail closed** không có nghĩa nuốt mọi lỗi DB thành 403/404 rồi mất khả năng giám sát; phải tách lỗi kết nối khỏi quyền bị từ chối.

### Context bất biến theo request/transaction

Một request nên có một `VerifiedContext` được xác minh rồi dùng nhất quán. Không đặt active tenant vào một static mutable field hoặc ThreadLocal không cleanup: thread pool có thể đưa context tenant A sang request tenant B.

Một số chính sách cần snapshot theo transaction; khi trạng thái đổi giữa check và mutation, phải bảo vệ thêm bằng conditional SQL, optimistic locking hoặc transaction isolation phù hợp.

## 7. RBAC, ABAC, ReBAC và chính sách kết hợp

| Mô hình | Quyết định dựa trên | Ví dụ |
| --- | --- | --- |
| **RBAC** | Role của subject | `ROLE_AUDITOR` được phép truy cập màn hình audit |
| **ABAC** | Attributes của subject, resource, action, environment | READ nếu tenant trùng, classification phù hợp, grant chưa hết hạn |
| **ReBAC** | Quan hệ giữa subject và resource | Alice là owner, Bob là member của project chứa document |
| **Policy-based** | Tập rule kết hợp nhiều nguồn và thứ tự ưu tiên | Tenant boundary AND business state AND (owner OR share) |

Một hệ thống thực tế thường kết hợp:

```text
ALLOW READ nếu
  subject.active
  AND subject.hasFunctionAuthority("document:read")
  AND resource.tenant == verifiedTenant
  AND resource.active
  AND (
        resource.owner == subject.id
        OR activeAclOrShareGrant(subject, resource, READ, now)
      )
```

ABAC không bắt buộc dùng một “policy engine” riêng. Một bean Java có unit tests và repository scope rõ có thể là policy động tốt. Với số lượng rule lớn, nhiều hệ thống/ngôn ngữ hoặc yêu cầu duyệt policy bởi nhóm khác, có thể tách một Policy Decision Point nhưng phải hiểu trade-off latency, cache, versioning và lỗi phụ thuộc.

### Deny rules và precedence

Không nên để nhiều đường allow OR vô tình vượt các điều kiện bất biến. Ví dụ **tenant boundary** và **account suspended** phải kiểm tra trước nhánh owner/share:

```text
DENY nếu account suspended
DENY nếu tenant không được phép
DENY nếu resource locked theo policy
ALLOW nếu owner và đúng action
ALLOW nếu share grant còn hiệu lực và đúng action
DENY nếu không có nhánh ALLOW nào
```

Trong code có thể viết thành điều kiện AND với một nhóm OR, thay vì trông chờ thứ tự `if` rời rạc. Nếu hệ thống có các rule grant/deny xung đột, định nghĩa rõ precedence (deny-overrides, explicit priority, first applicable...). **Không giả định tất cả engine, Spring ACL và AuthorizationManager có một luật deny-overrides toàn cục giống nhau.**

## 8. PEP, PDP, PIP và PAP: tách điểm cưỡng chế khỏi quyết định

Một hệ thống chính sách động lớn thường sử dụng các vai trò khái niệm:

- **PEP — Policy Enforcement Point:** nơi **chặn/cho thực thi** request, method hoặc data mutation.
- **PDP — Policy Decision Point:** nơi **đánh giá** subject-resource-action-context để tạo decision.
- **PIP — Policy Information Point:** nơi lấy attributes/relationships/trusted resource state.
- **PAP — Policy Administration Point:** nơi quản trị, kiểm duyệt, phiên bản hóa và xuất bản policy.

Trong Spring Security:

```text
                    HTTP / method call
                           |
                           v
                PEP (Filter / interceptor)
                           |
                           v
              PDP (AuthorizationManager
                   hoặc policy bean)
                     /         \
                    v           v
             PIP: subject    PIP: resource
             + membership    + ACL + state
                    \           /
                     v         v
                   PolicyDecision
                 /               \
               GRANT             DENY
                 |                 |
                 v                 v
             repository        access denied
             scoped query      / HTTP policy
```

Một Java bean chính sách có thể đóng vai PDP và truy repository làm PIP, không bắt buộc có service mạng riêng. Nếu PDP là external service, phải thiết kế authentication giữa PEP/PDP, request attributes tối thiểu, timeouts, retries, circuit breaker và **mặc định deny khi PDP không thể xác minh quyền**. Không để stale decision trong cache kéo dài một grant đã bị revoke.

### Decision không nên chỉ là String

Một mô hình nội bộ có thể chứa:

```text
Decision {
  effect: ALLOW | DENY
  policyVersion: "doc-policy-7"
  reasonCode: "NOT_OWNER_OR_SHARED"
  evaluatedAt: Instant
  obligations: ["AUDIT_ACCESS"]
}
```

Đây là cấu trúc **minh họa do ứng dụng thiết kế**, không phải DTO mặc định của Spring Security. `reasonCode` có thể dùng cho audit nội bộ, nhưng không đưa owner/tenant/private policy chi tiết vào HTTP response cho người chưa có quyền biết tài nguyên tồn tại.

**Obligations** như bắt audit, watermark, step-up MFA, giới hạn xuất file phải được **PEP thực thi**; chỉ trả một mảng obligations mà service bỏ qua là policy không thực sự được áp dụng.

## 9. Spring Security AuthorizationManager<T>: ngữ cảnh ra quyết định

Spring Security hiện đại sử dụng `AuthorizationManager<T>` ở HTTP, method và một số integration khác. Hợp đồng khái niệm:

```java
AuthorizationResult authorize(
    Supplier<? extends Authentication> authentication,
    T secureObject
);
```

Chữ ký thực tùy phiên bản có nullability annotations và kiểu generic cụ thể; từ Spring Security 6.4, `authorize` trả `AuthorizationResult`, còn một số tài liệu/phiên bản trước đó dùng `check(...)` trả `AuthorizationDecision`. Khi viết ứng dụng, đối chiếu **Javadoc của phiên bản được resolve**, không copy chữ ký giản lược như một file độc lập.

`T` có thể là:

- `RequestAuthorizationContext` cho Servlet HTTP request: request, method, matcher variables.
- `MethodInvocation` cho method call: phương thức và arguments.
- Một đối tượng context/domain tùy biến trong policy khác.

Một manager có thể trả **allow**, **deny**, hoặc `null` khi không có quyết định theo hợp đồng API. Với các điểm bảo vệ nhạy cảm, thiết kế nên trả kết quả tường minh DENY khi thiếu dữ liệu; không dùng `null` như đường allow ngầm mà chưa hiểu cách manager aggregator xử lý abstain.

### Custom AuthorizationManager cho HTTP

Ví dụ một bean Spring quản lý URL tài liệu:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

@Configuration
public class DocumentHttpSecurityConfig {

    @Bean
    SecurityFilterChain documentChain(
            HttpSecurity http,
            DocumentAccessPolicy policy) throws Exception {

        AuthorizationManager<RequestAuthorizationContext> checkRead =
            (authenticationSupplier, context) -> {

                var authentication = authenticationSupplier.get();
                String idText = context.getVariables().get("documentId");
                Long id;

                try {
                    id = Long.valueOf(idText);
                } catch (NumberFormatException ex) {
                    return new AuthorizationDecision(false);
                }

                boolean allowed = policy.canRead(authentication, id);
                return new AuthorizationDecision(allowed);
            };

        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(
                org.springframework.http.HttpMethod.GET,
                "/api/documents/{documentId}"
            ).access(checkRead)
            .anyRequest().denyAll()
        );

        return http.build();
    }
}
```

Đây là **config component**; `DocumentAccessPolicy` là bean domain tự triển khai, cần dependency Spring Security và authentication configuration thực. Dùng matcher path variable phù hợp với kiểu matcher đã cấu hình. `Long.valueOf(null)` ném `NumberFormatException` nên nhánh trên từ chối. Với path ID sai cú pháp, controller cũng có thể áp HTTP 400/404; đừng giả định authorization manager kiểm soát toàn bộ error mapping.

**Giới hạn:** request-level manager chỉ thấy request và ID; policy phải đọc Document thật với tenant/owner/ACL từ server. Nếu service cũng được gọi từ batch hoặc một controller khác, phải **bảo vệ ở service/domain** chứ không trông chờ một URL matcher.

### Method-level authorization thường gần resource hơn

`@EnableMethodSecurity` bật `@PreAuthorize` trên Spring-managed method:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {}
```

Service:

```java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    private final DocumentRepository documents;

    public DocumentService(DocumentRepository documents) {
        this.documents = documents;
    }

    @PreAuthorize(
        "hasAuthority('document:read') and " +
        "@documentAccessPolicy.canRead(authentication, #documentId)"
    )
    public DocumentView read(@P("documentId") Long documentId) {
        Document doc = documents
            .findById(documentId)
            .orElseThrow();

        return new DocumentView(doc.getId(), doc.getTitle());
    }

    public record DocumentView(Long id, String title) {}
}
```

Đây là **thành phần ứng dụng**, cần `Document`, repository và bean `documentAccessPolicy`. `@P` cung cấp tên tham số cho SpEL. **Ví dụ này mới cho thấy cách gắn policy**, chưa phải cách truy vấn dữ liệu production tối ưu: `findById` rộng sau pre-check có thể tạo race/TOCTOU. Với dữ liệu tenant-sensitive, ưu tiên lấy theo tenant/owner/ACL-scope hoặc kiểm tra thêm trong transaction.

Trong Spring AOP proxy mode, `this.read(...)` gọi bên trong cùng class có thể bypass interceptor. `@EnableMethodSecurity` không được bật tự động chỉ vì thêm spring-boot-starter-security. Service nên thiết kế bảo vệ đa tầng để việc đổi đường gọi không làm mất chính sách.

## 10. Xây một API policy Java rõ subject-resource-action-context

Thay vì truyền hàng chục tham số vào mọi method, có thể định nghĩa **mô hình dữ liệu bất biến**. Ví dụ:

```java
public enum DocumentAction {
    READ, EDIT, DELETE, SHARE
}

public record VerifiedSubject(
    String subjectId,
    String tenantId,
    java.util.Set<String> authorities,
    boolean active
) {}

public record ResourceFacts(
    long documentId,
    String tenantId,
    String ownerSubjectId,
    String status,
    boolean deleted
) {}

public record DecisionContext(
    java.time.Instant evaluatedAt,
    boolean mfaConfirmed
) {}
```

Đây là **các type ứng dụng**, không phải class Spring Security. Trong triển khai thật:

- `VerifiedSubject` chỉ được tạo từ principal/tenant membership đã xác minh, không bind trực tiếp JSON.
- `ResourceFacts` chỉ lấy từ database/trusted domain service.
- `DecisionContext` dùng server `Clock` và chứng cứ MFA đã verify, không lấy boolean client khai.
- Có thể dùng enum cho status và authorities để giảm lỗi typo.
- Khi nhiều request đồng thời, object bất biến giúp ngăn thay tenant/ngữ cảnh giữa chừng.

Policy function:

```java
public boolean can(
        VerifiedSubject subject,
        ResourceFacts resource,
        DocumentAction action,
        DecisionContext context) {

    if (subject == null || resource == null
            || action == null || context == null) {
        return false;
    }
    if (!subject.active() || resource.deleted()) {
        return false;
    }
    if (!subject.tenantId().equals(resource.tenantId())) {
        return false;
    }

    String authority = switch (action) {
        case READ -> "document:read";
        case EDIT -> "document:edit";
        case DELETE -> "document:delete";
        case SHARE -> "document:share";
    };

    if (!subject.authorities().contains(authority)) {
        return false;
    }
    if ("ARCHIVED".equals(resource.status())
            && action != DocumentAction.READ) {
        return false;
    }

    boolean owner = subject.subjectId()
        .equals(resource.ownerSubjectId());

    if (action == DocumentAction.DELETE && !context.mfaConfirmed()) {
        return false;
    }

    return owner;
}
```

**Đây là skeleton** chỉ cho owner thực hiện action và là một policy minh họa chưa có share grants/ACL. Phần dưới sẽ bổ sung quan hệ được chia sẻ và test runnable. Mục đích là làm rõ **các điều kiện global deny đặt trước đường allow**. Không viết `if (owner) return true` trước khi kiểm tra tenant, account suspended hoặc workflow lock.

### Dùng repository là Policy Information Point

Một policy bean thực tế có thể lấy dữ liệu theo kiểu:

```java
public boolean canRead(Authentication auth, Long documentId) {
    VerifiedSubject subject = subjects.fromTrustedAuthentication(auth);
    if (subject == null || documentId == null || documentId <= 0) {
        return false;
    }
    if (!subject.authorities().contains("document:read")) {
        return false;
    }

    var document = documents
        .findByIdAndTenantIdAndDeletedFalse(
            documentId, subject.tenantId())
        .orElse(null);

    if (document == null) {
        return false;
    }

    if (subject.subjectId().equals(document.getOwnerSubjectId())) {
        return true;
    }

    return grants.hasActiveReadGrant(
        documentId, subject.tenantId(),
        subject.subjectId(), clock.instant());
}
```

**Fragment minh họa**: `subjects`, `documents`, `grants` và `clock` là bean ứng dụng cần triển khai. `hasActiveReadGrant` phải kiểm tra đúng object ID, tenant, recipient, permission, `validFrom <= now < expiresAt`, revoke và các điều kiện nghiệp vụ khác. Không sử dụng một grant row do client gửi mà chưa xác minh.

Với tenant selection từ HTTP, `subjects.fromTrustedAuthentication` phải biết tenant đã verify qua service, hoặc được truyền một `VerifiedTenantScope` độc lập. `Authentication.getName()` không phải lúc nào cũng trùng subjectId thực; nhiều issuer cần namespace/identity mapping.

### Không tự biến context thành quyền

Một IP nằm trong công ty, giờ hành chính hoặc MFA đã hoàn thành có thể là **điều kiện bổ sung**, nhưng không tự chứng minh owner/ACL của Document 42. Quyền cần kết hợp:

```text
validPrincipal
AND verifiedTenant
AND hasActionPermission
AND resourceInTenant
AND resourceBusinessStateAllows
AND (owner OR activeShareGrant)
AND requiredContextChecks
```

Nếu vì đang làm việc từ VPN mà bỏ mọi object-level authorization, policy động đã trở thành một lỗ hổng IDOR.

## 11. Khi nào cần policy engine ngoài JVM?

Khi chỉ vài service, rule Java typed và tests thường dễ kiểm tra nhất. Một engine/chính sách tập trung có thể hữu ích khi:

- Nhiều microservices phải thực thi cùng policy.
- Quy tắc thay đổi thường xuyên, cần approval, audit, rollback và policy version.
- Cần biểu diễn ReBAC với nhiều cấp project, folder, team, group.
- Nhiều nguồn metadata/identity phải được kết hợp có kiểm soát.
- Có yêu cầu policy-as-code, dry-run, đánh giá shadow và differential tests.

Nhưng một engine mạng cũng có chi phí:

| Khía cạnh | Câu hỏi cần thiết kế |
| --- | --- |
| Latency | Mỗi API cần bao nhiêu lần gọi PDP? Có batch decisions không? |
| Availability | PDP không phản hồi thì DENY an toàn hay trả 503? |
| Consistency | Quyền bị revoke cần có hiệu lực trong bao lâu? |
| Attributes | PEP gửi resource facts hay PDP tự truy? Ai xác minh? |
| Policy version | Log và test bằng phiên bản nào? |
| Cache | Cache key có subject, tenant, action, resource, context version không? |
| Data minimization | Có gửi thông tin cá nhân nhạy cảm sang PDP không? |
| Obligations | Ai đảm bảo audit, MFA step-up, watermark thực sự xảy ra? |

**Không** gửi toàn bộ JPA entity hoặc raw JWT đến PDP chỉ vì tiện; gửi attributes tối thiểu được ký/tra từ nguồn tin cậy, không làm lộ secrets trong logs.

### Quyết định nhóm: allOf, anyOf và precedence

Ví dụ policy có thể được phân rã:

```text
mandatory =
  authenticated
  AND account active
  AND verified tenant
  AND resource not deleted

resourcePermission =
  owner OR active share OR explicit approved administrator

ALLOW =
  mandatory
  AND action authority
  AND resourcePermission
  AND action-specific context
```

Những predicate bắt buộc không được đặt lẫn vào nhóm `OR`. Nếu một branch admin bypass được phép, nó cũng cần tenant scope và business conditions theo thiết kế. Khi có explicit deny và grant, không đơn giản chọn bất kỳ grant để vượt deny mà chưa định nghĩa combining algorithm.

## 12. Chính sách động, thời gian và trạng thái

Quyền có thể thay đổi mà user không đăng xuất:

- Admin thu hồi role.
- User bị xóa khỏi tenant.
- Document chuyển owner, bị archived, soft-deleted hoặc classified.
- Grant chia sẻ hết hạn.
- Hóa đơn chuyển từ PENDING sang APPROVED.
- Account bị suspended.
- MFA status/assurance không còn đủ cho thao tác nhạy cảm.

Một quyết định `ALLOW` hôm qua không có giá trị vĩnh viễn. Ứng dụng nên kiểm tra dữ liệu cần thiết **ở thời điểm thao tác**, trừ khi có một mô hình cache/snapshot nhất quán được thiết kế rõ.

### Thời gian: khoảng nửa mở

Grant tạm thời nên dùng `[validFrom, expiresAt)`:

```java
boolean valid = !now.isBefore(validFrom)
    && now.isBefore(expiresAt)
    && revokedAt == null;
```

Đúng tại `expiresAt` phải bị từ chối. Dùng `Clock` inject để test, tránh ngủ thật trong unit test. Nếu database và JVM có clock lệch, phải chọn nguồn giờ chuẩn và SLA; `JWT exp` của access token không đồng nghĩa thời hạn resource-sharing grant.

### Race/TOCTOU

```text
T1: check canEdit(alice, doc42) => ALLOW
T2: admin revokes access / changes tenant or owner
T1: repository.save(doc42) continues
```

Một `@PreAuthorize` đơn thuần có thể chạy **trước** transaction advice của method. Vì vậy nếu cần đảm bảo dữ liệu tại thời điểm cập nhật:

- Đọc và kiểm tra điều kiện quyền trong cùng transaction.
- Dùng lệnh `UPDATE ... WHERE id = ? AND tenant_id = ? AND owner_id = ? AND status = ?`, kết hợp version/ACL conditions khi phù hợp.
- Dùng optimistic/pessimistic locking theo mức độ nhạy cảm và chi phí.
- Xác định thứ tự giữa commit revoke và operation đang diễn ra.
- Kiểm tra số row bị thay đổi; nếu 0 thì không mặc nhiên thành công.

Không khẳng định `@Transactional` mặc định tự loại bỏ mọi race; dưới `READ_COMMITTED`, membership và trạng thái vẫn có thể thay đổi giữa nhiều query.

## 13. Data-scoped query quan trọng không kém policy bean

Dù policy service đã kiểm tra object, repository cũng nên có tenant/owner/ACL scope khi truy cập dữ liệu nhạy cảm.

Ví dụ SELECT:

```sql
SELECT id, title, status
FROM documents
WHERE id = :requested_id
  AND tenant_id = :verified_tenant
  AND deleted = FALSE;
```

Nếu policy chỉ cho owner:

```sql
SELECT id, title
FROM documents
WHERE id = :requested_id
  AND tenant_id = :verified_tenant
  AND owner_subject_id = :authenticated_subject
  AND deleted = FALSE;
```

Với hành động EDIT:

```sql
UPDATE documents
SET title = :new_title
WHERE id = :requested_id
  AND tenant_id = :verified_tenant
  AND owner_subject_id = :authenticated_subject
  AND status = 'DRAFT'
  AND deleted = FALSE;
```

SQL trên là **mẫu logic**, không phải schema Spring mặc định; với share/ACL, biểu diễn policy đầy đủ trong query hoặc dùng transaction/locking phù hợp. `:verified_tenant` và `:authenticated_subject` phải từ server, không phải raw header/body.

### RLS, Hibernate filter và các đường bypass

PostgreSQL Row-Level Security có thể thêm một lớp bảo vệ DB; nhưng nếu application set tenant context từ input chưa verify, RLS chỉ thi hành tenant **sai** đó. Role chạy request không được có `BYPASSRLS` và connection pool phải bảo đảm tenant context không leak giữa requests.

Hibernate filters/tenant resolver không tự bảo vệ mọi native SQL, bulk query, file storage, search index hoặc service bên ngoài. Tất cả đường đọc/ghi/export phải có ranh giới phù hợp.

### Dữ liệu trả về và property-level authorization

Được READ Document 42 không có nghĩa được xem `privateNotes`, `legalHold` hoặc token API gắn với document. DTO nên chỉ cho các field policy cho phép; khi cần, tách permission `READ_PUBLIC_FIELDS` và `READ_CONFIDENTIAL_FIELDS`. Với update, không binding nguyên JSON vào entity và lưu fields như `ownerId`, `tenantId`, `approvedBy`.

## 14. Test Java 17 chạy độc lập: chính sách nhiều chiều

Chương trình sau dùng **Java thuần**, không cần Spring Security hoặc database. Nó mô phỏng cách policy duy nhất nhận đủ subject–resource–action–context; không sử dụng `Thread.sleep` và có stdout xác định. Các hành vi authentication/tenant membership là dữ liệu fixture tin cậy **trong demo**, không phải cách xác thực production.

Tạo file `ContextualAuthorizationDemo.java`:

```java
import java.time.Instant;
import java.util.Map;
import java.util.Set;

public class ContextualAuthorizationDemo {

    enum Action { READ, EDIT, DELETE, SHARE }

    record Subject(
        String id, String tenant, Set<Action> actions, boolean active
    ) {}

    record Resource(
        long id, String tenant, String owner, boolean archived,
        boolean deleted
    ) {}

    record Share(
        long resourceId, String grantee, Action action,
        Instant from, Instant until, boolean revoked
    ) {}

    record Context(
        Instant now, boolean strongAuthentication
    ) {}

    static boolean hasActiveShare(
            Subject subject, Resource resource,
            Action action, Context context, Share share) {

        return share != null
            && share.resourceId() == resource.id()
            && share.grantee().equals(subject.id())
            && share.action() == action
            && !share.revoked()
            && !context.now().isBefore(share.from())
            && context.now().isBefore(share.until());
    }

    static boolean can(
            Subject subject, Resource resource,
            Action action, Context context, Share share) {

        if (subject == null || resource == null
                || action == null || context == null
                || !subject.active() || resource.deleted()) {
            return false;
        }

        // Mandatory boundary: tenant + action capability.
        if (!subject.tenant().equals(resource.tenant())
                || !subject.actions().contains(action)) {
            return false;
        }

        // Archived resources cannot be modified or shared.
        if (resource.archived() && action != Action.READ) {
            return false;
        }

        // DELETE requires stronger authentication for everyone.
        if (action == Action.DELETE
                && !context.strongAuthentication()) {
            return false;
        }

        boolean isOwner = subject.id().equals(resource.owner());
        boolean shared = hasActiveShare(
            subject, resource, action, context, share);

        return isOwner || shared;
    }

    public static void main(String[] args) {
        Instant start = Instant.parse("2026-11-05T09:00:00Z");
        Context normal = new Context(start.plusSeconds(60), false);
        Context strong = new Context(start.plusSeconds(60), true);

        Subject alice = new Subject(
            "alice", "tenant-a", Set.of(Action.READ,
                Action.EDIT, Action.DELETE, Action.SHARE), true);
        Subject bob = new Subject(
            "bob", "tenant-a", Set.of(Action.READ, Action.EDIT), true);
        Subject carol = new Subject(
            "carol", "tenant-b", Set.of(Action.READ), true);
        Subject blocked = new Subject(
            "alice", "tenant-a", Set.of(Action.READ), false);

        Resource doc42 = new Resource(
            42, "tenant-a", "alice", false, false);
        Resource archived = new Resource(
            50, "tenant-a", "alice", true, false);

        Share bobRead = new Share(
            42, "bob", Action.READ,
            start, start.plusSeconds(300), false);

        System.out.println("Owner read: "
            + can(alice, doc42, Action.READ, normal, null));
        System.out.println("Shared read: "
            + can(bob, doc42, Action.READ, normal, bobRead));
        System.out.println("Shared edit denied: "
            + can(bob, doc42, Action.EDIT, normal, bobRead));
        System.out.println("Cross tenant denied: "
            + can(carol, doc42, Action.READ, normal, bobRead));
        System.out.println("Delete without MFA: "
            + can(alice, doc42, Action.DELETE, normal, null));
        System.out.println("Delete with MFA: "
            + can(alice, doc42, Action.DELETE, strong, null));
        System.out.println("Archived edit: "
            + can(alice, archived, Action.EDIT, strong, null));
        System.out.println("Inactive owner: "
            + can(blocked, doc42, Action.READ, normal, null));
        System.out.println("Share at expiry: "
            + can(bob, doc42, Action.READ,
                new Context(start.plusSeconds(300), false), bobRead));
        System.out.println("Share revoked: "
            + can(bob, doc42, Action.READ, normal,
                new Share(42, "bob", Action.READ,
                    start, start.plusSeconds(300), true)));
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac ContextualAuthorizationDemo.java
java ContextualAuthorizationDemo
```

Stdout chính xác:

```text
Owner read: true
Shared read: true
Shared edit denied: false
Cross tenant denied: false
Delete without MFA: false
Delete with MFA: true
Archived edit: false
Inactive owner: false
Share at expiry: false
Share revoked: false
```

**Giải thích từng nhóm điều kiện:**

- Alice là owner nên được READ, và được DELETE chỉ khi ngữ cảnh xác thực mạnh đã được server xác minh.
- Bob được READ nhờ grant đúng resource ID, action, recipient và thời gian; grant READ không cấp EDIT.
- Carol không thuộc tenant của document nên bị deny trước mọi share path.
- Tài liệu archived không nhận EDIT.
- Tài khoản bị inactive bị từ chối kể cả khi là owner.
- Đúng tại `until`, grant hết hiệu lực do dùng điều kiện `now < until`; grant bị revoke cũng không thể cấp quyền.

**Giới hạn:** demo không tự xác minh JWT, MFA, Membership hay ACL thật; `Subject`/`Share` được tạo từ fixture. `Set.of(...)` là dữ liệu cấp quyền do chương trình kiểm soát. Trong ứng dụng thật, các object này phải được dựng từ nguồn tin cậy và kết quả phải được áp vào repository/transaction/HTTP enforcement. Không dùng bản demo như policy production mà thiếu các điều kiện nghiệp vụ khác.

## 15. Tư duy theo bảng quyết định để tránh rule mâu thuẫn

Thay vì chỉ viết một expression dài, hãy lập bảng quyết định. Giả sử policy Document:

| Subject | Resource | Action | Context | Kỳ vọng |
| --- | --- | --- | --- | --- |
| Alice owner | Document 42 cùng tenant | READ | Active | ALLOW |
| Alice owner | Document 42 cùng tenant | DELETE | Chưa xác thực mạnh | DENY |
| Alice owner | Document 42 cùng tenant | DELETE | MFA đã xác minh | ALLOW nếu không có chặn khác |
| Bob recipient | Document 42 cùng tenant | READ | Grant active | ALLOW |
| Bob recipient | Document 42 cùng tenant | EDIT | Chỉ có share READ | DENY |
| Bob recipient | Document 42 cùng tenant | READ | Grant expired | DENY |
| Bob recipient | Document 42 cùng tenant | READ | Grant revoked | DENY |
| Carol | Document 42 tenant khác | READ | Có authority chung | DENY |
| Alice suspended | Document 42 là owner | READ | Account inactive | DENY |
| Alice owner | Document archived | EDIT | Có authority EDIT | DENY |
| Anonymous | Document 42 | READ | Không authenticated | DENY |
| Service principal chưa được ủy quyền | Document 42 | EXPORT | Job background | DENY |

Các điều kiện bắt buộc có thể được kiểm thử như **invariants**:

```text
For every subject, resource, action, context:
  if subject inactive -> DENY
  if resource deleted -> DENY
  if tenant not verified -> DENY
  if action not authorized -> DENY
  if no owner/share/ACL relationship -> DENY
```

Một regression test tốt còn thử đổi **một chiều duy nhất** của input: chỉ đổi tenant, chỉ đổi ID, chỉ đổi action hoặc chỉ đổi thời gian. Nếu policy được viết đúng, kết quả phải đổi ở những biên đã công bố.

## 16. Kiểm thử Spring Security thực qua interceptor

Unit test trực tiếp một policy bean là cần thiết nhưng **chưa chứng minh** Spring Security đang gọi nó. Có thể policy đúng nhưng:

- `@EnableMethodSecurity` chưa bật.
- Service được tạo bằng `new`, không phải Spring bean.
- Lời gọi nội bộ `this.method()` bypass AOP proxy.
- Một endpoint mới gọi repository trực tiếp và bỏ qua service.
- @PreAuthorize dùng sai tên tham số SpEL, hoặc dùng role global của tenant khác.
- SecurityFilterChain matcher không khớp route thật.
- Request-level policy chặn GET nhưng PUT/DELETE dùng đường khác.

Nên dùng `@SpringBootTest`/`MockMvc` hoặc HTTP integration test và `spring-security-test` để kiểm tra:

1. Authentication mapping trùng production: JWT subject/issuer, custom principal, authorities.
2. Policy bean có được gọi với đúng ID/resource/action không.
3. Tenant membership lấy từ server, không phải header chưa xác minh.
4. Deny ngăn service method/side effects khi cần.
5. Repository không trả dữ liệu ngoài tenant hoặc object scope.
6. Đúng mã lỗi 401/403/404 theo API contract.
7. Hết hạn/revoked share grants có tác dụng khi cache nóng và khi request chạy trên node khác.
8. Thao tác ghi thực sự bị từ chối trong transaction, không chỉ response trả 403 sau khi dữ liệu đã thay đổi.

Ví dụ test fragment cho một API có policy che giấu resource ngoài phạm vi:

```java
mockMvc.perform(get("/api/documents/{id}", 42L)
        .with(user("bob").authorities(
            new SimpleGrantedAuthority("document:read"))))
    .andExpect(status().isNotFound());
```

Đây là **fragment**, cần bean `MockMvc`, static imports, fixtures user/tenant và policy được triển khai tương ứng. Nếu Bob được share READ thì kỳ vọng phải là 200; fixture cần kiểm soát grant để kết quả đáng tin. `@WithMockUser`/`user(...)` cũng không tự tái hiện mọi mapping JWT/issuer/MFA của production.

### Test lỗi hạ tầng

Đặt repository membership/ACL ở trạng thái timeout và xác minh:

- Không được ALLOW.
- Không trả dữ liệu.
- Log nội bộ nhận diện dependency failure.
- HTTP có thể trả 5xx/503 hợp lý thay vì tự chuyển mọi outage thành “không tồn tại”.
- Không có cache positive cũ vượt SLA revoke.
- Không có “fallback = owner by default” khi thiếu resource facts.

**Fail closed** là không cấp quyền khi không thể chứng minh, không phải cứ nuốt lỗi thì hệ thống được xem là an toàn.

## 17. Performance, batch decisions và cache

Policy động thường tra:

- Membership/roles.
- Resource/owner/tenant.
- ACL/share grants.
- Status/feature flags.
- Account state/MFA assurance.

Nếu một list gồm 500 documents và ứng dụng gọi policy 500 lần, từng lần fetch resource + grants riêng, có thể tạo **N+1 queries**.

Các hướng cải thiện:

1. Lọc và phân trang **trong SQL theo scope** trước khi lấy dữ liệu.
2. Bulk fetch facts/relationships/ACL cho một tập ID đã được xác minh.
3. Gộp request tới PDP nếu engine hỗ trợ batch.
4. Cache dữ liệu reference ít biến động với invalidation; tránh cache ALLOW quá lâu khi quyền biến động.
5. Tách coarse action checks khỏi resource checks để loại request rõ ràng không hợp lệ sớm.
6. Theo dõi số decisions, deny rate, query latency, p95/p99 và source errors, **không log token/secret**.

### Cache key phải chứa đúng chiều của quyết định

Một key kiểu `canRead:document42` là **sai** nếu user Bob và Alice dùng chung. Tối thiểu cần xét:

```text
subjectId | tenantId | resourceType | resourceId | action
| policyVersion | relevantSubjectOrAclVersion | relevantContextBucket
```

Nếu thời gian là điều kiện, một cached ALLOW phải **hết hiệu lực không muộn hơn grant expiry**, và revoke giữa kỳ phải có invalidation/online check. Không thể hứa revoke trong 1 giây nếu cache cho phép giữ kết quả GRANT trong 15 phút mà không kiểm tra nguồn sự thật.

Đối với môi trường nhạy cảm, cache **resource facts** và re-evaluate policy từ source đáng tin có thể phù hợp hơn cache booleans. Cần test khi role, owner, tenant, account status và document classification thay đổi.

### Cache và data leak từ các tầng khác

Tách cache key tenant/principal còn cần tại:

- HTTP/CDN responses.
- Search index và pagination count.
- Object storage/presigned URLs.
- Export results, email attachments, background report.
- Frontend query state khi đổi tenant.

Một policy đúng ở controller không giúp gì nếu CDN trả dữ liệu của tenant A từ cache cho tenant B.

## 18. Quản trị policy động và rollout

Khi rule thay đổi mà không cần redeploy, bề mặt tấn công chuyển sang **ai được sửa policy**.

Quy trình đáng tin:

1. Soạn policy trong kho có access control và audit.
2. Review bởi người có thẩm quyền; không để user thường gửi JSON policy tùy ý.
3. Validate cú pháp và schema các attributes/actions.
4. Dùng regression tests với bảng quyết định đại diện.
5. Kiểm tra **negative tests**: cross-tenant, thiếu role, revoked, expired, mismatched resource.
6. Chạy shadow evaluation để so sánh old policy với candidate khi thích hợp; **shadow không được thay enforcement**.
7. Rollout theo version/canary, có khả năng rollback.
8. Log policy version và reason code nội bộ để đối soát.
9. Invalidating cache và policy bundles sau khi publish hoặc revoke.
10. Đặt “deny by default” cho action/resource type chưa biết.

**Không** cho admin UI viết trực tiếp một SpEL expression từ input của người dùng rồi evaluate như mã trên server. Dynamic policy nên là rule data có schema/DSL được kiểm soát, hoặc code/config được reviewed. Một chuỗi SpEL do người không tin cậy cung cấp có thể trở thành rủi ro thực thi biểu thức ngoài dự tính.

### Policy version và audit

Một audit event nên ghi những dữ liệu đủ để giải thích:

```text
requestId: req-123
subject: u-1001
tenant: tenant-a
resource: Document/42
action: EDIT
decision: DENY
reasonCode: ARCHIVED_RESOURCE
policyVersion: doc-policy-8
evaluatedAt: 2026-11-05T09:00:00Z
```

Nội dung chỉ là mẫu. Log phải tuân thủ privacy/retention và không chứa access token, password, full content hay claims nhạy cảm. Không gửi lý do nội bộ “owner is Bob, tenant is Finance” trong phản hồi cho user không có quyền biết document tồn tại.

### Có nên công bố lý do DENY?

Đối với người có quyền biết một object tồn tại, UI có thể hiển thị “Không thể sửa tài liệu đã archived”. Với user ngoài tenant hoặc không biết object tồn tại, API có thể trả `404 Not Found` trung tính cho cả không tồn tại và bị che giấu. **Không** mặc định mọi deny đều trả 404; policy HTTP cần nhất quán và riêng biệt với quyết định domain.

## 19. Những lỗi phổ biến và cách khắc phục

| Sai lầm | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| Chỉ dùng `hasRole('USER')` | Không biết resource/tenant/action | Bổ sung kiểm tra subject–resource–action–context |
| Tin owner/tenant từ request JSON | Client giả mạo attributes để được quyền | Load resource facts từ server |
| Dùng role admin của tenant A ở tenant B | Privilege escalation | Tenant-scoped membership và rights |
| Coi MFA header do client gửi là trusted | Bypass step-up | Dùng authenticated assurance từ hệ thống xác thực |
| Dùng giờ browser cho expiry | Người dùng chỉnh đồng hồ | Server `Instant` và injected `Clock` |
| Đặt owner allow trước tenant/global deny | Owner vượt tenant/status/account lock | Kiểm tra invariants trước các nhánh allow |
| Dùng `READ` cho cả EDIT/EXPORT/SHARE | Quyền quá rộng | Action enum và policy riêng |
| Resource ID khớp nhưng type khác | ID collision cross-type | Type + ID + tenant identity rõ |
| Trả entity JPA trực tiếp | Lộ property/relations | DTO allowlist/field authorization |
| Dùng một `@PreAuthorize` rồi update không scope | Race/TOCTOU | Conditional DB mutation, transaction/version |
| Dùng `@PostAuthorize` để bảo vệ write | Side effect có thể commit trước deny | Pre-check và scope mutation |
| Dùng Java `new Service()` test method annotation | Bypass Spring proxy | Integration test qua Spring bean |
| Coi `Authentication.isAuthenticated()` đủ chống anonymous | Anonymous token có thể cần trust resolver | Kiểm tra principal và authenticated trust đúng |
| Dùng `null`/abstain như implicit permit | Chính sách không rõ khi thiếu rule | Explicit DENY/default deny |
| Cache ALLOW không có subject/action/tenant | Data leak giữa user | Cache key đủ scope hoặc re-check |
| Cache vượt share expiry | Cấp quyền đã hết hạn | TTL tới expiry và revoke invalidation |
| Nuốt DB timeout thành ALLOW | Fail open | Trả lỗi an toàn, không cấp quyền |
| Nuốt mọi exception thành 404 | Khó debug, sai availability/error contract | Phân loại deny và dependency failures |
| Chấp nhận SpEL/policy script tùy ý từ client | Injection/unsafe execution | Structured DSL/allowlist, review policy |
| Chỉ test positive/happy path | Bỏ sót IDOR và privilege escalation | Negative matrix theo bốn chiều |
| Bật RBAC nhưng bỏ query scope | Tài nguyên tenant khác vẫn bị đọc/ghi | Repository/DB enforcement |
| Remote PDP lỗi thì trả permitAll | Cho phép khi mất hệ thống policy | Fail closed, circuit breaker và 5xx khi cần |
| Quên background jobs/exports | Đường bypass HTTP policy | Service/domain authorization và trusted service identity |

## 20. Checklist áp dụng vào dự án

Trước khi đưa một policy động vào production, trả lời được:

1. **Subject:** identity lấy từ đâu, có được xác minh và namespace theo issuer khi cần không?
2. **Tenant:** tenant đã verify membership và trạng thái chưa, có vai trò scoped đúng không?
3. **Resource:** tải facts/owner/status/tenant từ database nào, có đọc đúng object ID/type không?
4. **Action:** hành động có typed enum và chính sách riêng chưa?
5. **Context:** thời gian, MFA, IP, device, request risk lấy từ nguồn đáng tin nào?
6. **Precedence:** global deny và local allow kết hợp thế nào, default deny có rõ ràng không?
7. **Create:** tài nguyên chưa có ID thì kiểm tra quyền trên parent/collection thế nào?
8. **Consistency:** policy check và mutation có nguy cơ TOCTOU không, cần transaction/lock/version nào?
9. **Database:** mọi SELECT/UPDATE/DELETE/list/count/export có tenant/ACL scope không?
10. **Spring:** `SecurityFilterChain`, `@EnableMethodSecurity`, proxies và request matcher có hoạt động thực không?
11. **Dynamic updates:** ai được sửa policy, versioning/review/canary/rollback được làm thế nào?
12. **PDP availability:** mất kết nối policy service thì vẫn fail closed chứ?
13. **Caching:** key có subject/tenant/resource/action/context/version, revoke/expiry có hiệu lực?
14. **Observability:** có audit decision, source, policy version nhưng không lộ dữ liệu không?
15. **HTTP contract:** 401/403/404 được map có chủ đích, tránh existence oracle không?
16. **Tests:** có bảng positive/negative theo đủ bốn chiều chưa?
17. **Concurrency:** có test thu hồi role/share và cập nhật đồng thời không?
18. **Non-HTTP:** worker/async/queue/microservice có identity và policy phù hợp không?
19. **Sensitive fields:** response DTO, field-level update và export có giới hạn đúng không?
20. **Security review:** đã kiểm tra policy bypass, default allow và admin cross-tenant chưa?

**Kết luận:** Thiết kế chính sách động hiệu quả không bắt đầu từ một biểu thức dài trong `@PreAuthorize`, mà bắt đầu từ **mô hình quyết định rõ subject–resource–action–context**. Xác minh nguồn của từng thuộc tính, tách điều kiện bắt buộc khỏi các nhánh allow, mặc định deny, kiểm tra ở service và database, quản lý thay đổi theo phiên bản, và kiểm thử trên nhiều biến thể quyền/tài nguyên/thời điểm. Spring Security cung cấp `AuthorizationManager`, HTTP authorization và method security; ứng dụng phải xây dựng **domain policy đáng tin và nhất quán** với dữ liệu nghiệp vụ.

## Tài liệu tham khảo chính thức

- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): `Authentication`, `GrantedAuthority`, `AuthorizationManager`, decision/abstain và cấu trúc interception.
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `AuthorizationFilter`, `RequestAuthorizationContext` và custom request access managers.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, policy bean, proxy/AOP và customization.
- [Spring Security API — AuthorizationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationManager.html): hợp đồng `authorize`/`verify` trong version hiện hành.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege, deny by default và kiểm tra từng request.
- [OWASP — Insecure Direct Object Reference Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html): object-level checks và query tài nguyên theo scope.
- [OWASP API Security Top 10 — API1:2023 BOLA](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/): bảo vệ đúng resource ID.
- [NIST SP 800-162 — ABAC](https://csrc.nist.gov/pubs/sp/800/162/upd2/final): mô hình attribute-based access control, chủ thể/đối tượng/hành động/môi trường và chính sách.
