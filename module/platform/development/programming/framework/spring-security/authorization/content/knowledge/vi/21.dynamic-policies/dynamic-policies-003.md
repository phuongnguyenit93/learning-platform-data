# Tách điểm thực thi chính sách khỏi thành phần quyết định chính sách

## 1. Vấn đề: một quyết định đúng vẫn có thể được thực thi sai

Trong ứng dụng Spring Security, kiểm tra quyền thường bắt đầu bằng điều kiện rất ngắn:

~~~java
@PreAuthorize("hasAuthority('document:write')")
public void updateDocument(Long documentId, String title) {
    // ...
}
~~~

Điều kiện này phù hợp với **quyền chức năng** nếu mọi document thực sự có cùng chính sách. Tuy nhiên, ứng dụng nhiều tenant và có chia sẻ tài nguyên cần kiểm tra thêm actor, tenant, owner, ACL, trạng thái tài liệu và action. Khi các điều kiện ấy nằm rải rác trong controller, service, repository, background worker, rất dễ xảy ra ba lỗi:

1. **Policy drift:** API đọc dùng một quy tắc, API tải file dùng quy tắc khác, worker chạy sau lại bỏ qua kiểm tra.
2. **Enforcement gap:** một component tính được quyết định DENY nhưng đường ghi dữ liệu vẫn được gọi; hoặc thiếu quyết định rồi mặc định ALLOW.
3. **Coupling:** mỗi thay đổi rule phải sửa nhiều nơi, làm tăng rủi ro triển khai và khó audit.

Một cách tổ chức là tách **Policy Enforcement Point (PEP)** khỏi **Policy Decision Point (PDP)**. PEP là nơi **chặn hoặc cho hành động thực sự diễn ra**; PDP là thành phần **đánh giá và trả về quyết định** dựa trên input đáng tin, dữ liệu chính sách và policy hiện hành.

Ví dụ: Alice là EDITOR trong tenant north nhưng Document #42 thuộc tenant south. PEP của API WRITE phải xin quyết định cho đúng actor, tenant, action và document; PDP trả DENY; PEP không cho repository ghi dù client biết đúng ID. Một batch worker xử lý tài liệu tương tự cũng phải đi qua enforcement hợp lệ, không dựa vào việc HTTP controller đã kiểm tra trong quá khứ.

**Bài Knowledge này tập trung vào trách nhiệm, ranh giới tin cậy và cách phối hợp PEP–PDP** trong Spring Security, đặc biệt khi chính sách thay đổi động. Nó không yêu cầu mọi dự án phải triển khai một policy server bên ngoài: tách trách nhiệm **về mặt kiến trúc** đã có giá trị kể cả khi PDP là một bean chạy cùng JVM.

## 2. PEP, PDP, PIP và PAP: ai làm việc gì?

| Thành phần | Tên | Trách nhiệm | Không nên làm |
|---|---|---|---|
| **PEP** | Policy Enforcement Point | Chặn hành động, gửi câu hỏi quyền, thực thi ALLOW/DENY/ERROR, bảo vệ side effect | Tự suy luận rằng PDP lỗi nghĩa là được phép |
| **PDP** | Policy Decision Point | Đánh giá rule với input và policy data, trả kết quả cho một action/resource cụ thể | Tự ghi dữ liệu nghiệp vụ thay PEP |
| **PIP** | Policy Information Point | Cung cấp thuộc tính actor, tenant membership, owner, ACL, resource state, environment có nguồn gốc đáng tin | Tin trực tiếp owner/role client tự gửi mà không xác minh |
| **PAP** | Policy Administration Point | Quản lý viết, duyệt, version, phân phối và rollback chính sách | Tự động đưa policy chưa test lên production |
| **Audit/Decision log** | Thành phần quan sát bổ trợ | Ghi ai hỏi quyền gì, policy revision và kết quả để truy vết | Log token/secret hoặc nội dung tài nguyên ngoài quyền |

Đây là các **vai trò kiến trúc**, không bắt buộc là bốn microservice. Một ứng dụng Spring nhỏ có thể dùng:
- PEP: Spring Method Security interceptor và service method.
- PDP: bean `DocumentPolicyDecisionService`.
- PIP: repository tra membership/ACL và business data.
- PAP: cấu hình policy được version-control, review và triển khai.
- Audit: domain audit và event/metrics bảo mật.

Khi lớn lên, có thể chuyển PDP thành **sidecar OPA** hoặc service quyết định quyền riêng mà giữ giao diện PEP. Chọn topology dựa trên latency, availability, nhu cầu dùng lại và rủi ro nhất quán, không phải vì “microservice thì luôn tốt hơn”.

## 3. Luồng đầy đủ từ request đến hành động

~~~text
Client / HTTP / message / scheduler
               |
               v
   Authentication + trusted identity
               |
               v
     PEP: trước hành động nhạy cảm
               |
               +---- PolicyInput(subject, tenant, action, resource) ----+
               |                                                      |
               |                                          PDP: evaluate policy
               |                                                      |
               |                                          PIP: memberships,
               |                                               ACL, owner,
               |                                               state, clock
               |                                                      |
               +<----- ALLOW / DENY / ERROR + metadata ----------------+
               |
      +--------+-------------+
      |          |           |
    ALLOW       DENY        ERROR / unknown
      |          |           |
      v          v           v
  Scoped      Do not      Do not
  action      execute     execute
      |
      v
  Transaction / DTO / side effect
~~~

Một **PDP trả ALLOW không trực tiếp thực hiện business mutation**. PEP giữ trách nhiệm quyết định có gọi repository, file storage, queue publisher hay external API hay không. Ngược lại, PDP không phải nơi biết cách trả HTTP 403, đóng transaction hay dừng worker job theo mọi giao thức; đó là trách nhiệm PEP/adapters.

Đừng đưa toàn bộ business logic vào một authorization filter HTTP: worker, CLI và direct service call có thể không đi qua HTTP. PEP nên xuất hiện tại **ranh giới thực thi** phù hợp, thường gồm cả coarse HTTP gate lẫn resource-specific service gate.

## 4. Phân biệt “quyết định”, “áp dụng”, và “giải thích”

Một kết quả PDP đáng thiết kế có thể có:

~~~json
{
  "effect": "DENY",
  "reasonCode": "RESOURCE_TENANT_MISMATCH",
  "policyVersion": "doc-policy-v17",
  "decisionId": "dec-8f01",
  "validUntil": null
}
~~~

Đây là **contract minh họa của ứng dụng**, không phải response JSON mặc định của Spring Security hoặc OPA. Các field có mục đích:
- `effect`: ALLOW hoặc DENY, đôi khi ERROR/INDETERMINATE theo contract đã chọn.
- `reasonCode`: hỗ trợ audit/test; không nhất thiết được phép trả nguyên văn cho client.
- `policyVersion`: biết rule nào tạo ra quyết định.
- `decisionId`: correlation ID để tra log, không thay chứng minh quyền.
- `validUntil`: thời hạn có thể cache/sử dụng nếu business cho phép; null không phải “vĩnh viễn”.

Một số hệ có khái niệm **obligations/advice**, ví dụ “phải mask cột lương” hoặc “phải audit before download”. Nếu PDP trả ALLOW kèm obligation mà PEP không thể thực hiện nghĩa vụ bắt buộc, PEP **không được bỏ qua nghĩa vụ rồi cho truy cập toàn bộ**.

Đừng trộn các trạng thái:
- **DENY:** chính sách đã đánh giá và từ chối.
- **NOT_APPLICABLE/ABSTAIN:** policy không đưa ra quyết định ở nhánh đó.
- **ERROR/INDETERMINATE:** không đánh giá được do input thiếu, timeout hoặc lỗi.
- **ALLOW:** có bằng chứng đủ theo policy.

PEP cần có **quy tắc tổng hợp/fail-closed** rõ. Nếu dùng Spring `AuthorizationManager`, một kết quả `null` có thể biểu diễn abstain; **không bao giờ coi null là ALLOW** trong adapter mà bài toán yêu cầu quyết định bắt buộc.

## 5. Bất biến PEP: không có ALLOW xác thực thì không có side effect

Một PEP an toàn cho hành động riêng tư tuân theo:

~~~text
ALLOW -> có thể tiếp tục, nhưng vẫn phải giữ các guard khác.
DENY  -> không gọi mutation / không trả dữ liệu ngoài quyền.
ERROR -> không gọi mutation; trả lỗi có kiểm soát.
NULL  -> không gọi mutation; coi là chưa đủ bằng chứng.
TIMEOUT -> không gọi mutation; ghi telemetry / circuit handling.
UNKNOWN EFFECT -> không gọi mutation; contract violation.
~~~

Nhiều lỗi lớn xuất hiện khi developer viết:

~~~java
boolean allowed = true;
try {
    allowed = policyClient.isAllowed(...);
} catch (Exception ex) {
    log.warn("Policy service unavailable", ex);
}
if (allowed) {
    repository.deleteById(id);
}
~~~

Đây là **anti-pattern fail-open**: biến khởi tạo `true`, nên khi PDP lỗi hành động vẫn chạy. Với dữ liệu nhạy cảm, nên phân biệt exception kỹ thuật với policy DENY nhưng **cả hai đều không dẫn đến hành động**.

Một điểm tinh tế: sau khi nhận ALLOW, PEP vẫn phải bảo đảm business transaction đúng tài nguyên đã hỏi, tenant đúng scope và action không đổi. Đừng hỏi PDP về Document #42 rồi dùng kết quả để cập nhật Document #57. Quyết định phải được **gắn đúng subject, action, resource, tenant và thời điểm hiệu lực**.

## 6. PDP nên nhận input nào?

Mô hình theo chiều quyền:

| Nhóm input | Ví dụ | Vì sao cần? |
|---|---|---|
| Subject | issuer+sub, internal principal ID, workload identity | Không nhầm người dùng/issuer, tránh giả mạo |
| Tenant | tenant được yêu cầu và đã xác minh membership | Tránh role của tenant A áp dụng cho tenant B |
| Action | DOCUMENT_READ / WRITE / DELETE / SHARE | Quyền đọc không tự là quyền xóa |
| Resource | type, stable ID, tenant, owner, project, classification, state/version | Quyết định đúng object và điều kiện dữ liệu |
| Context | server time, policy revision, delegation, device posture nếu cần | Chính sách động phụ thuộc ngữ cảnh |
| Request metadata | requestId/correlationId, source service | Trace/audit; không biến correlation ID thành quyền |

Ví dụ input:

~~~json
{
  "subject": {
    "issuer": "https://idp.example",
    "id": "alice",
    "tenantRoles": ["DOCUMENT_EDITOR"]
  },
  "tenant": "north",
  "action": "DOCUMENT_WRITE",
  "resource": {
    "type": "Document",
    "id": "42",
    "tenant": "north",
    "ownerId": "bob",
    "locked": false
  },
  "environment": {
    "requestId": "req-120",
    "policyRevision": "v17"
  }
}
~~~

Đây là **payload minh họa giữa PEP và PDP**, không nên nhận toàn bộ từ client. Actor identity phải lấy từ authentication đã xác minh; tenant role từ nguồn đáng tin; resource tenant/owner/locked từ repository/trusted PIP. Một client có thể gửi resource ID và tenant target, nhưng không được tự chọn `ownerId` hay `tenantRoles` để được ALLOW.

Không truyền object domain quá lớn hoặc bí mật không cần thiết sang PDP. Áp dụng **data minimization**: gửi những thuộc tính đủ để ra quyết định, theo version schema rõ. Nếu PDP cần thông tin rất nhạy cảm, cân nhắc PIP đặt gần dữ liệu hoặc hỏi membership bằng reference đáng tin.

## 7. Ai chuẩn bị input: PEP, PIP hay PDP?

Có hai mô hình chính:

**Push attributes:** PEP/service lấy actor, tenant, resource attributes từ DB/trusted PIP rồi gửi một input đầy đủ cho PDP.

Ưu điểm: PDP thuần/pure dễ test, không cần quyền đọc nhiều database. Nhược điểm: PEP phải lấy đúng dữ liệu, có thể stale; nhiều PEP có nguy cơ dựng input không nhất quán.

**Pull attributes:** PEP gửi identity/resource reference, PDP hoặc PIP tra DB/ACL/membership cần thiết.

Ưu điểm: policy logic và data retrieval nhất quán hơn, PEP đơn giản. Nhược điểm: PDP có thêm dependency, latency, quyền truy cập DB và xử lý outage.

**Hybrid:** PEP gửi các trường đã xác minh, PDP tra những thuộc tính động trong PIP riêng. Nhiều hệ thực tế dùng hybrid, nhưng cần định nghĩa freshness, cache và authorization cho PIP.

Điều bất biến: **nguồn dữ liệu phải được đánh dấu trust/provenance**. Một field `tenantId` được copy từ request và field `tenantId` được lấy từ database có cùng kiểu Java `String` nhưng khác cấp độ tin cậy. Đừng dùng tên `VerifiedTenant` để thay việc xác minh thật.

## 8. PDP thuần quyết định, PEP không tự viết lại policy

Một interface domain đơn giản không phụ thuộc Spring:

~~~java
public interface PolicyDecisionPoint {
    PolicyDecision decide(PolicyInput input);
}
~~~

Đây là **snippet tích hợp kiến trúc**, các kiểu `PolicyDecision`/`PolicyInput` do ứng dụng định nghĩa. Một implementation có thể:
- Chạy chính sách Java nội bộ.
- Dùng rule đã được cấu hình và version hóa.
- Gọi sidecar OPA hoặc PDP từ xa.
- Truy vấn ACL/relationship service đã được bảo vệ.
- Kết hợp nhiều chính sách theo thứ tự/precedence được mô tả và test.

Một PEP/adaptor dùng:

~~~java
PolicyDecision decision = pdp.decide(input);

if (decision == null || decision.effect() != Effect.ALLOW) {
    throw new AccessDeniedException("No usable authorization grant");
}

return documentRepository.findScopedForRead(
        input.resourceId(), input.verifiedTenant());
~~~

Mã **minh họa**, chưa độc lập: cần các class, repository và imports. Quan trọng: PDP trả dữ liệu, PEP kiểm tra chính xác `ALLOW` và truy vấn scoped tiếp theo. Khi PDP lỗi, PEP có thể phân biệt 5xx với 403, nhưng không được trả dữ liệu nhạy cảm.

Phải tránh cách “PEP chỉ tin tên role” rồi PDP lại kiểm tra owner khác: khi chính sách phân tán, cần một **contract thống nhất** về input/action/decision. Một phần role check có thể ở HTTP PEP để bảo vệ sơ bộ, nhưng resource PDP vẫn phải nhận đủ scope.

## 9. Tích hợp với Spring Security: AuthorizationManager là cầu nối

Spring Security dùng `AuthorizationManager<T>` để đánh giá quyền đối với HTTP request, method invocation và các loại secured object tương ứng. Các thành phần như `AuthorizationFilter` và method security interceptor có thể đóng vai trò **PEP**, còn `AuthorizationManager` có thể đóng vai trò **adapter ra quyết định** tới PDP của ứng dụng.

Khác biệt cần lưu ý:
- `AuthorizationManager` là **API quyết định/điều phối trong Spring Security**, không mặc nhiên là remote PDP.
- `AuthorizationFilter` là enforcement trong HTTP chain; method interceptor là enforcement trước/sau method.
- Cùng một PDP của ứng dụng có thể được gọi qua adapter `AuthorizationManager<RequestAuthorizationContext>`, adapter method security, policy bean hoặc service boundary.
- Không phải mọi thao tác bảo mật đều bắt buộc dùng AuthorizationManager nếu domain service có policy gate đúng; nhưng khi tích hợp, phải theo contract version đang sử dụng.

Tài liệu Spring Security hiện hành dùng method `authorize(Supplier<Authentication>, T)` trả `AuthorizationResult` (có thể null cho abstain). Một số phiên bản/tài liệu cũ còn nói đến `check(...)` trả `AuthorizationDecision`. Khi viết adapter cụ thể, phải đối chiếu **version API trong project**, không copy một chữ ký từ blog cũ rồi đoán.

Từ góc nhìn kiến trúc, tách policy engine bằng một interface domain giúp nâng version Spring Security mà không sửa mọi business rule.

## 10. HTTP PEP: bảo vệ coarse-grained trước tiên

Ví dụ cấu hình Spring Servlet:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/documents/**").authenticated()
        .anyRequest().denyAll());
    return http.build();
}
~~~

Đây là **snippet Spring integration**; cần imports, dependency, CSRF/session và filter configuration thực tế. Nó bảo vệ HTTP entrypoint bằng authentication nhưng **chưa** chứng minh tài liệu số 42 thuộc tenant nào hoặc user được WRITE.

Có thể dùng `.access(customAuthorizationManager)` để yêu cầu custom PDP cho một route, nhưng nên cân nhắc:
- HTTP request có đủ resource metadata để quyết định không? Nếu chỉ có path ID, manager cần truy vấn DB.
- Predicate có bị gọi hai lần, một ở filter và một ở service, khiến latency không cần thiết không?
- Các entrypoint ngoài HTTP có bị bypass không?
- Policy có side effect hay request logging nhạy cảm không? PDP nên không tự mutate.
- Có một fallback `anyRequest().denyAll()` rõ cho những route chưa khai báo không?

Một thiết kế phổ biến là **HTTP PEP kiểm tra authentication và coarse authority**, **service PEP kiểm tra quyền trên resource bằng PDP**, repository thêm tenant/resource predicate. Defense in depth có giá trị hơn tập trung toàn bộ object ACL trong một filter không thấy ngữ cảnh domain.

## 11. Method PEP: @PreAuthorize gọi một policy bean

Trong Spring Security Method Security, có thể gọi bean qua SpEL:

~~~java
@PreAuthorize(
    "isAuthenticated() and " +
    "@documentAccess.canRead(authentication, #tenantId, #documentId)"
)
@Transactional(readOnly = true)
public DocumentView read(String tenantId, Long documentId) {
    return documentService.loadScopedDocument(tenantId, documentId);
}
~~~

Đây là **snippet tích hợp**. Bean `documentAccess` nên là một adapter thực thi:
1. Lấy subject đáng tin từ Authentication.
2. Xác minh tenant target và membership.
3. Lấy resource từ DB với tenant guard.
4. Dựng PolicyInput chuẩn và gọi PDP.
5. Chỉ trả true khi PDP quyết định ALLOW.
6. Không biến exception/null/timeout thành true.

Lưu ý:
- Bật `@EnableMethodSecurity`.
- Annotation hoạt động trên lời gọi đi qua **Spring proxy** trong proxy mode; `this.read(...)` tự gọi trong bean có thể bypass interceptor.
- SpEL parameter names cần discover được bằng `-parameters`, `@P` hoặc cách hỗ trợ tương ứng.
- `@PreAuthorize` là kiểm tra trước method; nó **không tự đảm bảo** transaction/ACL không đổi trước lúc mutation commit.
- Method `loadScopedDocument` cần query tenant/owner/ACL phù hợp, không dùng kết quả precheck để load object khác.

Một PDP dùng chung là có lợi, nhưng PEP ở service vẫn phải giữ ranh giới dữ liệu đáng tin.

## 12. Ví dụ adapter @Component không làm PDP thành controller

Giả sử ứng dụng có `VerifiedActorResolver`, `DocumentMetadataRepository` và `PolicyDecisionPoint`:

~~~java
@Component("documentAccess")
public class DocumentAccessGate {
    private final VerifiedActorResolver actors;
    private final DocumentMetadataRepository documents;
    private final PolicyDecisionPoint policy;

    public DocumentAccessGate(VerifiedActorResolver actors,
            DocumentMetadataRepository documents,
            PolicyDecisionPoint policy) {
        this.actors = actors;
        this.documents = documents;
        this.policy = policy;
    }

    public boolean canRead(Authentication authentication,
            String tenantId, Long documentId) {

        VerifiedActor actor =
                actors.requireMember(authentication, tenantId);

        if (documentId == null || documentId <= 0) {
            return false;
        }

        DocumentMetadata doc = documents
                .findByIdAndTenantId(documentId, actor.tenantId())
                .orElse(null);

        if (doc == null) {
            return false;
        }

        PolicyInput input = PolicyInput.forRead(actor, doc);
        PolicyDecision decision = policy.decide(input);
        return decision != null && decision.effect() == Effect.ALLOW;
    }
}
~~~

Đây là **mẫu class tích hợp**; imports và các domain components thuộc project, chưa phải file Java độc lập. `requireMember` phải thật sự xác thực membership và namespace subject; `DocumentMetadata` lấy resource tenant/owner/status từ DB; `PolicyInput.forRead` phải dựng input từ nguồn trusted.

Đây là cách tách trách nhiệm:
- `DocumentAccessGate` là một **adapter vào PDP**, không chứa mọi rule.
- `PolicyDecisionPoint` trả quyết định theo policy.
- Spring method interceptor chặn method khi điều kiện false.
- Repository/service sau đó thực hiện read scope.

Trong production, cần **quy định exception handling**. Nếu `policy.decide` ném lỗi kỹ thuật, không tiếp tục action; Spring MVC/exception mapper có thể trả 5xx và telemetry thay vì gộp mọi outage thành 403. Một boolean adapter có thể chỉ trả false cho DENY, còn ERROR ném exception riêng để không mất tín hiệu vận hành. Dù map mã HTTP thế nào, dữ liệu không được trả khi chưa có ALLOW.

## 13. PEP của WRITE phải nằm gần mutation

Một lần gọi PDP trả ALLOW không phải quyền sửa vĩnh viễn. Nếu actor được phép ở T1 nhưng owner/ACL thay đổi tại T2, service ghi tại T3 có thể dùng quyết định cũ.

~~~text
T1: PDP -> ALLOW WRITE document 42
T2: admin revoke WRITE / chuyển owner / khóa document
T3: repository.updateTitleById(42, "New title")
~~~

Đoạn cuối chỉ theo ID có thể ghi trái quyền. Với owner-only WRITE, nên dùng **conditional update** gắn điều kiện hiện hành:

~~~sql
UPDATE documents
SET title = :title,
    version = version + 1
WHERE id = :id
  AND tenant_id = :verified_tenant
  AND owner_user_id = :verified_subject
  AND status = 'ACTIVE'
  AND version = :expected_version;
~~~

Kiểm tra affected rows = 1, không coi 0 là success. Điều kiện `tenant`/`subject` phải lấy từ trusted context, không từ client body. Nếu WRITE được cấp qua grant/ACL ở bảng khác, cần query/transaction/lock/version protocol phù hợp; một `@Version` trên Document **không tự** kiểm tra việc thu hồi grant ở DB khác.

Một service PEP có thể:
- Dùng PDP để kiểm tra các rule phức tạp.
- Thực hiện write trong transaction với guard actor/resource/action còn hiệu lực theo policy.
- Chỉ commit và publish side effect khi toàn bộ guard đạt.
- Dùng outbox/idempotency nếu có event sau commit.

**Không nên tuyên bố “đã tách PDP nên hết TOCTOU”**. Tách trách nhiệm cải thiện maintainability nhưng cũng tạo thêm ranh giới thời gian/network. Cần giải quyết concurrency riêng.

## 14. Policy động: thay đổi rule mà không sửa từng PEP

Điểm mạnh của kiến trúc PEP–PDP là **policy lifecycle độc lập** với enforcement code. Ví dụ:
- Thêm điều kiện chặn WRITE trên tài liệu `LEGAL_HOLD`.
- Giới hạn SHARE cho tenant admin trong giờ làm việc.
- Cấp quyền READ cho một nhóm review có membership động.
- Yêu cầu classification/clearance trước export.
- Thay đổi chính sách vùng địa lý/cấp quyền theo hợp đồng.

PAP quản lý policy version:
1. Đề xuất/chỉnh sửa policy qua Git hoặc bảng quản trị được phân quyền.
2. Review bởi người chịu trách nhiệm an toàn và domain owner.
3. Static validation/type checking, unit tests và permission matrix.
4. Deploy tới PDP có version/rollback và quan sát sai khác.
5. Phân phối/invalidate cache theo policy revision.
6. Audit ai duyệt, policy đổi gì, hiệu lực từ khi nào.
7. Rollback an toàn nếu policy mới có lỗi, không tự rơi về `permitAll`.

PDP nên trả/ghi policy revision để truy vết. Một PEP có thể giữ interface ổn định khi policy đổi, nhưng input schema, action names và obligation semantics cũng phải được version hóa nếu thay đổi.

Không cho các team tự bật policy qua UI không có kiểm tra quyền, approval hoặc audit; một thay đổi policy có thể tương đương việc cấp đặc quyền sản xuất.

## 15. Local PDP, sidecar hay remote PDP?

| Mô hình | Cách chạy | Ưu điểm | Rủi ro/chi phí |
|---|---|---|---|
| **In-process** | Library/bean Java trong application | Thấp latency, dễ transaction/context, ít dependency mạng | Phân phối policy phải đồng bộ nhiều instance |
| **Sidecar** | Policy engine cạnh service/pod | Gần PEP, giảm network hop, policy có thể cập nhật riêng | Lifecycle/bundle/cache và memory mỗi pod |
| **Remote PDP** | Service tập trung dùng HTTP/gRPC | Dùng chung rule, audit/administration tập trung | Network latency, availability, failure domains, thundering herd |
| **Hybrid** | PDP local cho phần đơn giản, remote cho quyết định khó | Cân bằng latency và độ phong phú policy | Cần contract rõ để không có hai nơi cho kết quả mâu thuẫn |

**Tách logic không đồng nghĩa bắt buộc thêm network call.** Với hệ nhỏ, một Spring bean quyết định quyền được dùng bởi nhiều service PEP có thể là điểm khởi đầu tốt. Khi dùng nhiều service với chung policy, có thể cân nhắc sidecar/remote, nhưng cần đo p95/p99 và tác động nếu PDP outage.

Đừng thiết kế một “single point of authorization failure” không có retry/timeout/circuit breaker/fallback an toàn. Fallback **an toàn** có thể là deny/503 hoặc một cache quyết định còn hiệu lực theo contract; không phải tự cho phép mọi request để giữ uptime.

## 16. OPA là ví dụ về PDP, không phải mặc định của Spring Security

Open Policy Agent (OPA) là một policy engine hỗ trợ tách policy decision khỏi enforcement. Ứng dụng (PEP) gửi input có cấu trúc cho OPA, OPA đánh giá rule/data và trả kết quả. OPA có thể chạy in-process theo phương pháp tích hợp, sidecar hoặc server; kiến trúc cụ thể phải theo sản phẩm.

Ví dụ request tới OPA Data API:

~~~http
POST /v1/data/app/documents/allow HTTP/1.1
Content-Type: application/json

{
  "input": {
    "subject": "alice",
    "tenant": "north",
    "action": "DOCUMENT_READ",
    "resource": {
      "id": "42",
      "tenant": "north",
      "owner": "bob"
    }
  }
}
~~~

Response **nếu** policy tại đường dẫn đó định nghĩa và đánh giá true:

~~~json
{
  "result": true
}
~~~

Đây là ví dụ **contract OPA Data API**, không nói mọi endpoint OPA luôn trả boolean. Nếu đường dẫn/rule không định nghĩa hoặc decision không được xác lập, Data API có thể trả HTTP 200 **không có property `result`**. PEP **không được coi HTTP 200 là ALLOW**. Phải kiểm tra kiểu `result` và semantics policy đúng; undefined/missing/wrong type → không cho thực thi.

Ví dụ mô tả Rego cho đường dẫn quyết định:

~~~rego
package app.documents

default allow := false

allow if {
    input.action == "DOCUMENT_READ"
    input.tenant == input.resource.tenant
    input.subject == input.resource.owner
}
~~~

Đây là **một rule Rego minh họa tối thiểu**, không thay policy production (chưa có authentication proof, membership, sharing, classification). Các thuộc tính `input.subject` và `input.resource.owner` phải do PEP/PIP đáng tin chuẩn bị, không chỉ copy client body. Hãy kiểm tra cú pháp/semantics theo phiên bản OPA sử dụng và test cả negative cases.

Nguồn tham khảo: [Open Policy Agent documentation](https://www.openpolicyagent.org/docs) và [OPA REST API](https://www.openpolicyagent.org/docs/rest-api).

## 17. Không cho PDP tự tin dữ liệu client

Một lỗi trust boundary:

~~~text
Client sends:
  subject = "admin"
  tenant = "finance"
  role = "SUPER_ADMIN"
  resource.owner = "admin"

PEP forwards unchanged to PDP
PDP sees role and owner -> ALLOW
~~~

PDP có thể thực thi rule **đúng trên dữ liệu sai**. Tách PDP/PEP không tự xác minh input; nếu PEP không chuẩn hóa actor hoặc PIP không xác nhận owner, kết quả ALLOW không đáng tin.

Thiết kế an toàn:
- Authentication xác minh caller; subject key là issuer + sub hoặc internal principal từ nguồn đáng tin.
- Tenant target được kiểm tra membership; role theo đúng tenant.
- Resource ID từ URL chỉ là target; owner/tenant/classification/status phải được lấy từ DB.
- Action được ánh xạ từ use case phía server, không cho client chọn action mềm để dùng cho mutation mạnh.
- Context như time lấy server clock; device posture/gateway claims cần trust rõ.
- PDP request nên được xác thực giữa các service qua mTLS/service identity và bảo vệ khỏi replay/tamper khi qua network.
- Domain object ID và tenant phải thống nhất giữa bước quyết định và bước sử dụng.

Nếu architecture dùng PIP do PDP tự gọi, phải bảo vệ PIP khỏi truy vấn tenant ngoài quyền của decision request. PIP không nên trả toàn bộ ACL của tổ chức chỉ vì PDP hỏi mà không có giới hạn kỹ thuật/audit.

## 18. Quyền trên resource không chỉ là role

Role/authority thường là **coarse gate**. Với document/folder/project cần owner, ACL hoặc relationship checks:

~~~text
ALLOW_READ =
    isAuthenticated
    AND belongsToRequestedTenant
    AND tenantRoleAllowsRead
    AND document.tenant == requestedTenant
    AND (
        subjectIsOwner
        OR activeShareReadGrant
        OR activeProjectReadMembership
    )
    AND document.isReadable
~~~

Đừng đặt điều kiện tenant bên trong một nhánh OR khiến nhánh admin/ACL được phép vượt tenant ngoài ý muốn.

Với Spring ACL, `AclPermissionEvaluator` có thể cung cấp đánh giá permission theo object; nó có thể là thành phần PDP/PIP của kiến trúc, còn Spring method security hoặc service đóng vai PEP. Nếu policy kết hợp hàng loạt thuộc tính động (time, classification, relationship), có thể phải có PDP business rule rộng hơn.

Không tự suy luận WRITE ngầm có SHARE hoặc DELETE. PDP cần input action đúng, và PEP phải dùng quyết định cho chính action đó.

## 19. Decision caching: đúng key, hạn dùng và thu hồi

Một key tham khảo:

~~~text
(
  issuer,
  subjectId,
  tenantId,
  resourceType,
  resourceId,
  action,
  resourceVersion,
  policyVersion,
  aclRevision
)
~~~

Đây là mô hình minh họa. Không phải mọi rule đều cần đủ trường, nhưng cache **không được trộn actor, tenant, resource hoặc action**. Nếu một quyết định phụ thuộc environment time/device, key/TTL cũng phải phản ánh điều đó.

Các vấn đề cần xác định:
- TTL tối đa cho ALLOW là bao lâu?
- Khi ACL grant bị revoke, PEP/PDP cache có nhận event invalidation không?
- Khi group membership đổi, có tăng authz revision hoặc cache epoch không?
- Khi policy được deploy từ v17 sang v18, cache cũ bị vô hiệu ở đâu?
- Mỗi instance cache có thể stale bao lâu khi event propagation chậm?
- Có lưu DENY ngắn hạn để giảm tải không, và có gây user vừa được cấp quyền vẫn bị từ chối không?
- Khi cache backend lỗi, có fallback an toàn với data quan trọng không?

**Cached ALLOW là quyết định trong quá khứ.** Với mutation hoặc dữ liệu rất nhạy cảm, cân nhắc recheck/guard tại thời điểm thực thi. Không hứa revoke tức thì trong khi token/decision cache còn hiệu lực 30 phút mà không có revocation mechanism.

## 20. PDP timeout, circuit breaker và phân biệt lỗi

Một network PDP có thể lỗi theo nhiều kiểu:
- Connect timeout, read timeout, DNS/TLS failure.
- HTTP 5xx hoặc response malformed.
- Input không đủ trường/trust.
- Policy missing/undefined.
- Version mismatch giữa client PEP và PDP.
- Rate limiting/overload.
- PDP trả DENY hợp lệ.

**DENY policy khác ERROR hạ tầng.** PEP đều không thực thi action, nhưng vận hành cần phân biệt:
- DENY → thường 403 hoặc 404 tùy leak policy.
- ERROR/timeout → thường 5xx/503 và alert, không success.
- Unauthenticated → 401/challenge hoặc redirect theo auth stack.
- Missing resource trong tập được phép → 404.

Timeout phải **bounded** để không treo request/transaction; retry có giới hạn và jitter phù hợp nhưng không lặp vô hạn. Circuit breaker có thể fail-closed khi PDP không sẵn sàng. Đừng bật fallback `permitAll` trong circuit-open.

Nếu quyết định được trả bởi cached entry còn hiệu lực và business chấp nhận dùng cached ALLOW khi PDP outage, phải có chính sách chặt về TTL, security criticality, revocation guarantees và bảo vệ cache key. Với action nhạy cảm, deny/503 thường an toàn hơn “stale allow”.

## 21. Obligations/advice: PEP phải thực hiện trọn, không chỉ check effect

Một số PDP có thể trả:

~~~json
{
  "effect": "ALLOW",
  "obligations": [
    {"type": "REDACT_FIELDS", "fields": ["salary", "personalId"]},
    {"type": "AUDIT_READ", "required": true}
  ]
}
~~~

Contract trên do **ứng dụng tự thiết kế**, không phải chuẩn response của Spring AuthorizationManager. Nếu PDP cho READ nhưng chỉ khi mask hai trường nhạy cảm, PEP trả DTO toàn phần là lỗi enforcement.

Cách an toàn:
1. PEP validate obligation types/schema/version.
2. Chỉ ALLOW khi tất cả mandatory obligations mà PEP có thể thực thi đã được áp dụng.
3. Projection/DTO mapper hoặc query phải loại trường ngoài quyền **trước khi serialize**.
4. Audit bắt buộc phải có bảo đảm theo contract (có thể transaction/outbox) trước khi hoàn tất hành động.
5. Obligation không hiểu được → DENY/ERROR, không bỏ qua.

PDP nên không gửi raw sensitive data như salary/personal ID trong decision; PEP sử dụng danh sách field hoặc policy labels để tạo projection an toàn.

## 22. Log/audit: PDP quyết định, PEP xác nhận thực thi

Một decision log và enforcement log trả lời hai câu hỏi khác nhau:

| Log | Câu hỏi | Field hữu ích |
|---|---|---|
| PDP decision | Vì sao policy quyết định như vậy? | decisionId, actor, tenant, action, resource, policyVersion, effect, reasonCode |
| PEP enforcement | Request đã bị chặn hay thực thi? | decisionId, endpoint/method, result, correlationId, latency, transaction outcome |
| Policy administration | Rule nào đã đổi? | actor editor, reviewer, revision, deploy time, rollback |
| PIP data provenance | Thuộc tính quyền từ nguồn nào? | membershipVersion, aclRevision, resourceVersion |

Không chỉ log PDP “ALLOW” rồi suy luận mutation đã thành công: repository có thể lỗi, transaction rollback hoặc PEP có thể chặn do obligation. Ngược lại, một PEP log “EXECUTED” mà không có decisionId/actor/resource đáng tin khó điều tra sự cố.

**Bảo vệ dữ liệu log:** không ghi JWT thô, session cookie, secret URL, raw policy credentials, nội dung tài liệu ngoài quyền. Correlation ID không phải bằng chứng quyền.

Có thể đo latency p50/p95/p99 của PDP, timeout/denial rates, cache hit, policy version drift và tỉ lệ mismatch giữa decision và enforcement. Một spike DENY sau rollout policy mới có thể là đúng policy hoặc bug; cần quan sát theo dimension nhưng không lộ PII.

## 23. Mở rộng nhiều PEP không tạo nhiều nơi “được phép”

Khi có HTTP controller, GraphQL, WebSocket, scheduler, message listener và file download, cần vẽ map các **điểm có thể tạo side effect hoặc tiết lộ dữ liệu**:

- Detail READ API và list/search/export.
- WRITE/DELETE service, bulk operation.
- File download/presigned URL.
- Queue consumer chạy sau hàng giờ.
- Scheduled job/service-to-service call.
- Admin console, support tools, data migration script.

Tất cả nơi này cần một enforcement boundary thích hợp. Không bắt buộc mỗi nơi phải gửi remote PDP call giống hệt, nhưng policy semantics và trusted input phải nhất quán.

Ví dụ:
- HTTP PEP xác thực user và chặn role coarse.
- Document service PEP kiểm tra tenant/resource action với PDP.
- Repository áp query scope `id AND tenant AND permittedObject`.
- Export worker có workload/actor delegation contract và recheck tại thời điểm export.
- Object-storage signed link được cấp với TTL đúng risk; sau khi cấp link, quyền của link có thể còn tồn tại đến expiry nếu storage không hỗ trợ revocation.

**Một PDP tập trung không chữa được những chỗ quên đặt PEP.** Công việc quan trọng nhất là inventory toàn bộ entrypoint và side effect, rồi bảo đảm mọi đường truy cập dữ liệu đều đi qua enforcement có kiểm thử.

## 24. Java 17 độc lập: PDP quyết định, PEP chặn và đếm side effect

Ví dụ sau **biên dịch/chạy với JDK 17**, không cần Spring. Nó mô phỏng chính sách local đơn giản và enforcement không thực hiện operation nếu quyết định DENY, PDP trả null hoặc PDP ném lỗi.

Tạo file `PepPdpDemo.java`:

~~~java
import java.util.Set;

public class PepPdpDemo {

    enum Action { READ, WRITE }
    enum Effect { ALLOW, DENY, ERROR }

    record Actor(String userId, String tenant, Set<String> roles) { }
    record Resource(long id, String tenant, String ownerId,
                    boolean locked) { }
    record Grant(String tenant, long resourceId,
                 String userId, Action action) { }
    record Input(Actor actor, Resource resource, Action action) { }
    record Decision(Effect effect, String reason) { }

    @FunctionalInterface
    interface DecisionPoint {
        Decision decide(Input input);
    }

    static final class LocalPdp implements DecisionPoint {
        private final Set<Grant> grants;

        LocalPdp(Set<Grant> grants) {
            this.grants = grants;
        }

        @Override
        public Decision decide(Input input) {
            if (input == null || input.actor() == null
                    || input.resource() == null || input.action() == null) {
                return new Decision(Effect.DENY, "MISSING_INPUT");
            }

            Actor actor = input.actor();
            Resource resource = input.resource();
            Action action = input.action();

            if (actor.userId() == null || actor.tenant() == null
                    || actor.roles() == null
                    || resource.id() <= 0 || resource.tenant() == null
                    || !actor.tenant().equals(resource.tenant())) {
                return new Decision(Effect.DENY, "INVALID_SCOPE");
            }

            boolean roleAllows = actor.roles().contains("TENANT_ADMIN")
                    || (action == Action.READ
                        && actor.roles().contains("READER"))
                    || (actor.roles().contains("EDITOR"));
            if (!roleAllows) {
                return new Decision(Effect.DENY, "ROLE");
            }

            if (resource.locked() && action == Action.WRITE) {
                return new Decision(Effect.DENY, "LOCKED");
            }

            boolean owner = actor.userId().equals(resource.ownerId());
            boolean tenantAdmin = actor.roles().contains("TENANT_ADMIN");
            boolean shared = grants.contains(new Grant(
                    resource.tenant(), resource.id(),
                    actor.userId(), action));

            if (owner || tenantAdmin || shared) {
                return new Decision(Effect.ALLOW, "GRANTED");
            }
            return new Decision(Effect.DENY, "OBJECT");
        }
    }

    static final class EnforcementPoint {
        private final DecisionPoint pdp;
        private int executed;

        EnforcementPoint(DecisionPoint pdp) {
            this.pdp = pdp;
        }

        String attempt(Input input) {
            Decision decision;
            try {
                decision = pdp.decide(input);
            } catch (RuntimeException failure) {
                return "BLOCKED_ERROR";
            }

            if (decision == null || decision.effect() == null
                    || decision.effect() == Effect.ERROR) {
                return "BLOCKED_ERROR";
            }
            if (decision.effect() != Effect.ALLOW) {
                return "BLOCKED_DENY";
            }

            // Chỉ nhánh ALLOW mới thực hiện side effect minh họa.
            executed++;
            return "EXECUTED";
        }

        int executed() {
            return executed;
        }
    }

    public static void main(String[] args) {
        Actor an = new Actor("an", "north", Set.of("EDITOR"));
        Actor binh = new Actor("binh", "north", Set.of("READER"));
        Actor southAdmin = new Actor(
                "admin", "south", Set.of("TENANT_ADMIN"));

        Resource document = new Resource(42, "north", "an", false);
        Resource locked = new Resource(43, "north", "an", true);
        Set<Grant> grants =
                Set.of(new Grant("north", 42, "binh", Action.READ));

        EnforcementPoint pep = new EnforcementPoint(new LocalPdp(grants));

        System.out.println("owner-write=" + pep.attempt(
                new Input(an, document, Action.WRITE)));
        System.out.println("shared-read=" + pep.attempt(
                new Input(binh, document, Action.READ)));
        System.out.println("shared-write=" + pep.attempt(
                new Input(binh, document, Action.WRITE)));
        System.out.println("other-tenant-admin=" + pep.attempt(
                new Input(southAdmin, document, Action.READ)));
        System.out.println("locked-owner-write=" + pep.attempt(
                new Input(an, locked, Action.WRITE)));

        EnforcementPoint missing = new EnforcementPoint(input -> null);
        System.out.println("no-decision=" + missing.attempt(
                new Input(an, document, Action.READ)));

        EnforcementPoint broken = new EnforcementPoint(input -> {
            throw new IllegalStateException("PDP unavailable");
        });
        System.out.println("pdp-failure=" + broken.attempt(
                new Input(an, document, Action.READ)));

        System.out.println("executed-count=" + pep.executed());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac PepPdpDemo.java
java PepPdpDemo
~~~

Stdout chính xác:

~~~text
owner-write=EXECUTED
shared-read=EXECUTED
shared-write=BLOCKED_DENY
other-tenant-admin=BLOCKED_DENY
locked-owner-write=BLOCKED_DENY
no-decision=BLOCKED_ERROR
pdp-failure=BLOCKED_ERROR
executed-count=2
~~~

Đọc kết quả:
1. An là owner và EDITOR trong tenant north, nên được WRITE.
2. Bình chỉ là READER nhưng được share READ trên đúng document nên được READ.
3. Grant READ không chuyển thành WRITE.
4. Admin tenant south không vượt qua tenant north.
5. Document locked chặn WRITE kể cả owner.
6. PDP không trả quyết định hoặc ném lỗi đều không cho side effect.
7. PEP chỉ tăng `executed` hai lần khi nhận ALLOW.

**Giới hạn:** actor/role/grants trong demo được tạo trực tiếp trong mã, không có JWT validation, database, transaction, cache hoặc concurrency. Một PEP thực tế phải lấy identity và resource attributes từ nguồn tin cậy, bảo vệ operation DB/file/queue thật, xử lý exception và đảm bảo không dùng một ALLOW cũ ngoài thời hạn. Đếm `executed` chỉ là side effect minh họa.

## 25. Kiểm thử đơn vị PDP và kiểm thử tích hợp PEP là hai việc khác nhau

**Unit test PDP** kiểm tra quy tắc cho input tĩnh:
- Owner READ/WRITE khi role tenant đúng.
- Non-owner không có grant → DENY.
- Grant READ không cho WRITE.
- Tenant mismatch → DENY, kể cả admin tenant khác.
- Resource LOCKED → WRITE DENY.
- Membership/ACL revoked, expired → DENY.
- Subject issuer khác nhưng cùng `sub` → không được trùng quyền.
- Policy revision A/B cho kết quả theo rule đã công bố.
- Input thiếu và thuộc tính invalid → DENY/ERROR có contract rõ.

**Integration test PEP** chứng minh quyết định thực sự được thực thi:
- HTTP route hoặc method invocation bị DENY thì controller/service không chạy body.
- PDP timeout/exception không có side effect.
- PDP trả null/undefined/malformed response không cấp quyền.
- PEP không gọi repository.update/delete khi DENY.
- Với ALLOW, PEP dùng **chính resource/action** đã được xác minh; không có ID swap.
- Không log/serialize resource ngoài quyền khi bị từ chối.
- `@PreAuthorize` qua Spring bean proxy thực, không chỉ new instance.
- Non-HTTP entrypoint vẫn có enforcement.
- Mandatory obligations được thực thi trước trả response.
- Query list/count/export có tenant/ACL filtering đúng.
- Transaction rollback hoặc version conflict không bị báo success giả.

Trong Spring, có thể dùng Spring Security Test/MockMvc, method-security integration tests và database thực qua Testcontainers khi concurrency/SQL có ý nghĩa. `@WithMockUser` mặc định không cung cấp custom JWT issuer/tenant claims; với app dùng custom principal phải tạo fixture tương ứng.

## 26. Test hợp đồng giữa PEP và PDP

Với remote PDP, cần **contract tests** cho cả serialization và policy semantics:

| Input/response | Kỳ vọng PEP |
|---|---|
| `{"effect":"ALLOW"}` đúng schema | Cho tiếp tục theo guard/obligation |
| `{"effect":"DENY"}` | Chặn hành động |
| Response HTTP 200 nhưng thiếu effect/result | Chặn; báo contract error |
| `effect="MAYBE"` | Chặn, không fallback allow |
| PDP timeout/connect fail | Chặn; có telemetry |
| PDP HTTP 500 | Chặn, báo lỗi kỹ thuật |
| Actor/resource/tenant mismatch | Không nhận ALLOW dù backend bị cấu hình sai |
| Chính sách yêu cầu mask field | PEP thực thi mask hoặc chặn |
| Decision đã hết TTL | Không dùng để grant |
| Version policy/PIP không tương thích | Không cho đến khi resolve an toàn |
| Response của tenant khác | Không áp dụng cho request này |
| Trùng decisionId nhưng khác resource | Không tái sử dụng |
| PDP trả ALLOW cho READ, request là DELETE | Không được áp dụng |
| Cache ALLOW bị revoke | Không dùng sau revocation SLA |

Khi chạy load test, đo PDP QPS, cache hit rate, latency tail, circuit breaker transitions và retries. Test cả PDP outage kéo dài: hệ có dừng ghi nhạy cảm đúng không? Có queue tích tụ không? Có fallback ẩn nào bật `permitAll` khi lỗi mạng không?

## 27. Migration từ policy rải rác sang PEP–PDP

Một lộ trình giảm rủi ro:

1. **Inventory hành động nhạy cảm:** READ/WRITE/DELETE/SHARE, download/export, async và admin.
2. **Lập decision matrix hiện tại:** ai được làm gì trên object nào, kể cả ngoại lệ tenant/ACL.
3. **Tách PolicyInput/PolicyDecision contract:** actor, tenant, action, resource, effect, reason, revision, obligations.
4. **Đặt PEP ở service boundary:** không chỉ HTTP route; chuẩn hóa việc gọi PDP và enforce.
5. **Đưa rule vào PDP local trước:** test output giống behavior đã chấp nhận, sửa lỗ hổng có kế hoạch.
6. **Phân biệt dữ liệu trusted/untrusted:** resolver và PIP có kiểm chứng.
7. **Shadow evaluation nếu cần:** gọi PDP mới để log so sánh nhưng vẫn enforce bằng đường cũ trong giai đoạn kiểm thử; shadow chỉ quan sát, không tự grant.
8. **Canary policy/PDP:** tăng dần lưu lượng, đo mismatch, latency, error và deny rates.
9. **Chuyển enforcement chính:** một nguồn quyết định rõ; tránh cả hai đường có fallback lẫn nhau tạo permit.
10. **Kích hoạt audit/cache/revision:** rollback policy, invalidation, runbook khi PDP down.
11. **Kiểm thử TOCTOU và side effect:** mỗi ALLOW dùng đúng resource/action, guarded mutation đúng thời điểm.
12. **Loại policy trùng rải rác:** giữ defense-in-depth cần thiết nhưng tránh các rule khác nhau vô tình mâu thuẫn.

Nếu chuyển PDP sang remote service, migration không chỉ đổi endpoint URL. Nó thêm trust boundary, network failure và consistency model, cần threat model lại, không thể dùng một HTTP client không có timeout hay xác thực.

## 28. Những sai lầm thường gặp

**1. “PDP trả ALLOW nên tự ghi DB được.”** PDP không thay PEP. **Sửa:** PEP chặn/cho trước khi gọi side effect và kiểm tra nghĩa vụ.

**2. “Đã có PEP ở HTTP controller nên worker không cần.”** Message/scheduler có đường vào khác. **Sửa:** enforcement ở service hoặc worker boundary.

**3. “HTTP 200 từ PDP là ALLOW.”** Một API có thể trả 200 với kết quả undefined. **Sửa:** validate schema và effect cụ thể.

**4. “PDP timeout thì cho qua cho khỏi ảnh hưởng uptime.”** Đây là fail-open. **Sửa:** deny/503 hoặc cache còn hiệu lực theo contract rủi ro.

**5. “PDP luôn nhận role/owner đúng.”** Client có thể giả trường đó nếu PEP copy thẳng. **Sửa:** authentication+trusted PIP.

**6. “Role editor đủ để sửa mọi document.”** Thiếu tenant/owner/ACL. **Sửa:** input action và resource scope đầy đủ.

**7. “Tách PDP nghĩa là hết TOCTOU.”** Quyền có thể bị revoke sau check. **Sửa:** guarded operation/version/lock.

**8. “Một cached ALLOW dùng cho mọi action trên object.”** READ không phải WRITE/DELETE. **Sửa:** cache key chứa action và resource revision.

**9. “Policy đổi không cần version.”** Không thể truy vết lỗi/rollback/canary. **Sửa:** PAP, policy revision và audit.

**10. “PEP có thể bỏ qua obligations không hỗ trợ.”** PDP có thể chỉ cấp quyền theo điều kiện mask/audit. **Sửa:** obligation bắt buộc phải thực thi hoặc deny.

**11. “Không cần test PEP vì PDP unit test đã PASS.”** PDP logic đúng nhưng middleware có thể bypass. **Sửa:** integration tests cho side effect và entrypoint.

**12. “Mọi policy phải đưa thành microservice.”** Thêm network và failure domain không cần thiết. **Sửa:** tách interface/trách nhiệm trước, chọn topology theo nhu cầu.

**13. “Dùng Spring @PreAuthorize ở một bean là mọi lời gọi được bảo vệ.”** Self-invocation có thể bypass proxy. **Sửa:** service boundaries và test qua Spring-managed bean.

**14. “Có thể dùng cùng một ALLOW cho Document #42 và #43.”** Decision binding sai. **Sửa:** gắn subject/tenant/action/resource và TTL với kết quả.

## 29. Checklist thiết kế hệ PEP–PDP

- [ ] Đã xác định các side effect và điểm PEP phải chặn.
- [ ] PDP chỉ quyết định, không âm thầm mutate dữ liệu nghiệp vụ.
- [ ] PolicyInput gồm subject, tenant, action, resource và context cần thiết.
- [ ] Mọi trường actor/role/tenant/resource có nguồn provenance đáng tin.
- [ ] PEP chỉ thực thi khi có ALLOW hợp lệ, đúng action/resource và chưa hết hạn.
- [ ] DENY, ERROR, NULL, undefined, timeout và contract mismatch đều fail closed.
- [ ] 401/403/404/5xx được map theo API không lộ dữ liệu ngoài quyền.
- [ ] Mandatory obligations như mask/audit được thực thi hoặc request bị chặn.
- [ ] Role gate theo tenant và object ACL/owner được kết hợp đúng.
- [ ] HTTP, service, message, job, download/export có enforcement tương ứng.
- [ ] Spring Method Security đã bật và không bị proxy self-invocation bypass.
- [ ] Query-time tenant/resource scope bảo vệ dữ liệu ngay cả khi PDP đã ALLOW.
- [ ] WRITE/DELETE có guarded transaction hoặc consistency protocol xử lý TOCTOU.
- [ ] Cache key có subject, tenant, resource, action, revision và TTL phù hợp.
- [ ] PAP quản lý policy version, review, tests, rollout và rollback.
- [ ] PDP remote có auth, timeout, retry giới hạn, circuit breaker và monitoring.
- [ ] Có unit tests PDP, integration tests PEP và contract tests PEP–PDP.
- [ ] Decision log và enforcement log đủ correlation, không chứa secrets/PII ngoài quyền.

**Kết luận:** Tách **nơi quyết định** (PDP) khỏi **nơi chặn và thực thi** (PEP) giúp chính sách động dễ dùng lại, test, audit và thay đổi mà không sao chép rule khắp hệ thống. Nhưng lợi ích chỉ có khi PEP thật sự bao phủ mọi đường truy cập, input PDP có nguồn tin cậy, mọi tình huống thiếu/ lỗi quyết định đều **fail closed**, và quyền được gắn đúng subject–tenant–action–resource tại thời điểm hành động. Spring Security cung cấp các interceptor và API để kết nối lớp này; việc bảo vệ transaction, object data và vòng đời policy vẫn là trách nhiệm thiết kế của ứng dụng.

## Tài liệu tham khảo

- [Spring Security – Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): vai trò của AuthorizationManager và các interceptor.
- [Spring Security – AuthorizationManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationManager.html): hợp đồng authorize/verify và kết quả.
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@PreAuthorize`, custom managers, bean-based policy và interception.
- [Spring Security – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): HTTP PEP, custom `AuthorizationManager` và fallback policy.
- [Spring Security – Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html): quyền riêng theo resource.
- [Open Policy Agent – Documentation](https://www.openpolicyagent.org/docs): decouple policy decision/enforcement và Rego.
- [Open Policy Agent – REST API](https://www.openpolicyagent.org/docs/rest-api): `POST /v1/data/...`, `input`, `result`/undefined và decision logging.
- [OWASP API Security Top 10 – Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): vì sao cần thực thi quyền theo object ID ở mọi API.
