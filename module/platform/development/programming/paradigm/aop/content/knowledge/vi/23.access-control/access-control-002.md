# Liên kết danh tính và ngữ cảnh quyền với lời gọi trong AOP

## 1. Bài toán

Lập trình hướng khía cạnh (**Aspect-Oriented Programming – AOP**) cho phép một **aspect** áp dụng mối quan tâm xuyên suốt như kiểm soát truy cập vào các **join point** do **pointcut** lựa chọn. Khi một lời gọi được chặn, **advice** có thể xác định người gọi, hành động, tài nguyên và chính sách quyền trước khi chuyển quyền điều khiển sang nghiệp vụ.

Chủ đề **“Liên kết danh tính và ngữ cảnh quyền với lời gọi”** đòi hỏi hiểu một điều: **quyết định quyền thuộc về một lần gọi cụ thể, với danh tính đã xác thực và tài nguyên cụ thể tại thời điểm liên quan**. Không thể chỉ hỏi “method này có cần role ADMIN không?” mà bỏ qua tenant, quyền sở hữu tài nguyên, ủy quyền và vòng đời ngữ cảnh.

Ví dụ, phương thức publish("doc-1") có thể cho phép Alice, từ chối Bob và cũng từ chối Alice nếu “doc-1” chuyển sang tenant khác. Việc một method được đánh dấu là “cần quyền publish” mới xác định **action**; principal và resource vẫn phải được kiểm tra.

Mô hình khái niệm:

~~~text
Trusted entry point
  -> xác minh danh tính caller
  -> tạo invocation context đáng tin cậy
  -> Authorization aspect
       -> lấy subject + action + resource + environment
       -> kiểm tra policy trước side effect
       -> DENY hoặc proceed đúng một lần
  -> đóng/khôi phục scope context
~~~

Không có một phương thức truyền context duy nhất cho mọi kiến trúc. Điều quan trọng là **nguồn danh tính đáng tin, scope chính xác, ngữ cảnh không bị rò và authorization không bị bỏ qua**.

## 2. Những khái niệm phải phân biệt

**Authentication (xác thực)**: xác minh caller thật sự là ai, qua token, chứng chỉ hoặc phương thức xác thực phù hợp. Kết quả là danh tính đã được tin cậy theo chính sách.

**Authorization (phân quyền)**: quyết định subject đã xác thực có được thực hiện action cụ thể trên resource cụ thể theo policy hiện tại không.

**Principal/subject**: chủ thể cần xét quyền, có thể là người dùng, service identity hoặc một subject được ủy quyền hợp lệ.

**Invocation context**: dữ liệu gắn với một occurrence lời gọi, thường có principal, tenant, permissions/scope, correlation ID và các thuộc tính cần thiết. Nó không đồng nhất với HTTP request hay một thread cố định.

**Join point**: điểm thực thi mà cơ chế AOP có thể can thiệp, chẳng hạn method-call hoặc method-execution. Những join point hỗ trợ được phụ thuộc vào kiểu weaving, proxy hay interceptor.

**Pointcut**: điều kiện chọn các join point cần kiểm tra quyền; ví dụ các method đại diện cho use case nhạy cảm.

**Advice**: mã chạy trước/sau/quanh join point; với phân quyền chủ động, logic kiểm tra thường phải xảy ra **trước proceed()**.

**Policy decision**: ALLOW hoặc DENY sau khi áp dụng luật lên subject, action, resource và bối cảnh. Một context có principal không chứng minh là được phép.

| Câu hỏi | Thành phần trả lời | Ví dụ |
| --- | --- | --- |
| Ai đang gọi? | Xác thực | Alice, service-X |
| Muốn làm gì? | Operation/action metadata | document.publish |
| Làm trên cái gì? | Resource resolver | doc-1 |
| Phạm vi nào? | Context + resource metadata | tenant-a, team-a |
| Có được phép? | Policy evaluator | ALLOW/DENY |
| Gọi có đi qua kiểm tra? | Pointcut + AOP interception | advice thực sự chạy |
| Context còn hợp lệ? | Scope/expiry/revalidation | token expiry, revoke |

Điểm dễ nhầm: **đúng role** chưa chắc **đúng tài nguyên**, và **đúng tài nguyên** tại lúc kiểm tra chưa chắc còn đúng lúc commit nếu có thay đổi đồng thời.

## 3. Bắt đầu từ ranh giới tin cậy

Client có thể gửi subject, roles, tenant hoặc isAdmin trong payload, nhưng các trường đó chỉ là **claim từ nguồn không tin cậy**. Nếu advice tin ngay vào chúng, caller có thể tự nâng quyền.

Một đường xử lý tốt thường là:

1. Entry point xác thực bằng chứng danh tính.
2. Thông tin subject và scope được suy ra từ **nguồn được tin cậy**, có xét expiry và trạng thái phiên.
3. Tạo invocation context bất biến hoặc không thể sửa tùy tiện trong vòng đời đang xử lý.
4. Aspect đọc context và các tham số đã được kiểm tra cơ bản, rồi hỏi policy logic.
5. Với operation được phép, mới gọi nghiệp vụ.
6. Scope của invocation được tháo/khôi phục cả khi thành công lẫn khi ném ngoại lệ.

Không lấy quyền từ tên method một cách tự động; annotation mô tả action, không tạo credential. Không coi một correlation ID là bằng chứng xác thực. Khi danh tính được upstream service chuyển tiếp, cần xác minh upstream, định dạng/nguồn ủy quyền và trust boundary tương ứng.

Một service chạy định kỳ không có “người dùng hiện tại” nên phải dùng **service/job principal** rõ ràng, thay vì gán giả tên một người dùng đặc quyền.

## 4. Gắn quyền với đúng occurrence của lời gọi

Một ngữ cảnh khái niệm có thể là:

~~~text
InvocationAccessContext:
    authenticated_actor = alice
    effective_subject = alice
    action = document.publish
    target_resource = doc-1
    trusted_tenant = tenant-a
    permission_scope = document.publish
    correlation_id = req-42
    authorization_expiry = <time>
~~~

Đây là dữ liệu minh họa; không phải tất cả trường đều nên log. Khi đổi effective subject theo delegation, vẫn phải giữ actor đã xác thực.

Một invocation không nên lấy một instance mutable currentUser được chia sẻ cho mọi request. Hai request đồng thời có thể ghi đè nhau, làm Alice bị đánh giá theo quyền Bob hoặc ngược lại. Ngay cả context lưu theo thread cũng không tự theo được executor, callback hay lời gọi qua một thread khác.

**Một lời gọi, một scope xác định**: xác định lúc tạo, cách truy xuất và thời điểm kết thúc. Với nested invocation, phải restore ngữ cảnh cha; với async, phải tạo scope ở nơi task thực sự chạy.

## 5. Quy tắc viết authorization advice

Giả mã chung:

~~~text
around protectedOperation:
    context = requireTrustedContext()
    action = resolveActionFromMethodContract()
    resource = resolveResourceFromInvocationArguments()
    decision = policy.evaluate(context, action, resource)

    if decision != ALLOW:
        auditSanitizedDenial()
        throw AccessDenied

    return proceedExactlyOnce()
~~~

Cần chú ý:

- **Deny by default** nếu context không có, principal không hợp lệ, action không rõ, resource không xác định hoặc policy không cho phép.
- Không để lỗi kết nối policy server ngầm biến thành ALLOW; fail-closed cho thao tác cần bảo vệ.
- Không gọi proceed() trước policy check nếu có thể gây side effect.
- Không gọi proceed() hai lần vì side effect có thể bị lặp.
- Không nuốt exception nghiệp vụ hay thay kết quả bằng success giả.
- Không tự động log args/return vì chứa dữ liệu nhạy cảm.
- Không giả định proxy chặn mọi lời gọi, đặc biệt self-invocation, direct target access hoặc đường vào khác.
- Nếu method trả đối tượng biểu thị lỗi, chính sách phân quyền vẫn được thực hiện **trước** khi gọi; business result là một khái niệm khác authorization decision.

Một security aspect nên phối hợp với **business invariants**. Nếu bảo mật phụ thuộc hoàn toàn vào proxy nhưng code khác dễ dàng gọi target trực tiếp, thiết kế phải chặn đường bypass hoặc kiểm tra thêm tại domain/storage boundary.

## 6. Kết hợp permission, tenant và quyền trên tài nguyên

Ba mô hình thông dụng:

**RBAC (role-based access control):** người dùng có role, role ánh xạ permission. Phù hợp việc định nghĩa trách nhiệm nhưng không đủ nếu từng tài liệu có chủ sở hữu/tenant riêng.

**ABAC (attribute-based access control):** xét thuộc tính subject, resource, action và môi trường, như trạng thái tài liệu, tổ chức, nhãn nhạy cảm hoặc thời gian.

**Quan hệ tài nguyên:** cho phép nếu principal thuộc team sở hữu tài liệu hoặc được chia sẻ quyền hợp lệ. Thường kết hợp với RBAC/ABAC.

Ví dụ chính sách:

~~~text
ALLOW document.publish WHEN
    subject.authenticated = true
    AND "document.publish" in subject.permissions
    AND subject.tenant = resource.tenant
    AND subject.team in resource.publisherTeams
    AND resource.status = DRAFT
~~~

Cần kiểm tra metadata tài nguyên từ **nguồn có thẩm quyền**. Không coi chuỗi tenantId do client gửi là bằng chứng rằng resource thật thuộc tenant đó. Nếu resource không tồn tại hoặc bị ẩn đối với caller, chính sách phản hồi cần tránh vô tình tiết lộ sự tồn tại.

Một thao tác batch trên nhiều tài nguyên phải quy định rõ **all-or-nothing** hay partial success; quyền đối với tài nguyên thứ nhất không cho phép xử lý luôn tất cả phần tử còn lại.

## 7. Ba cách vận chuyển context

### 7.1. Truyền tham số tường minh

~~~java
// Chỉ là khai báo minh họa; AccessContext và Receipt phải được định nghĩa.
Receipt publish(AccessContext context, String documentId);
~~~

Ưu điểm: phụ thuộc vào identity hiện rõ, dễ kiểm thử, thuận tiện khi truyền sang task. Nhưng nếu caller không tin cậy tự khởi tạo AccessContext thì vẫn bị giả mạo; lớp xây dựng context và entry point phải được quản lý đúng trust boundary.

### 7.2. Scope theo thread

Có thể gắn context đã xác thực trong ThreadLocal cho lời gọi đồng bộ. Khi một method trả hoặc ném ngoại lệ, cần **remove/restore trong finally**. Với nested scope, ghi nhớ previous để khôi phục chính xác.

Không có gì trong ThreadLocal bảo đảm principal do bên đáng tin tạo ra. Nó chỉ là carrier. Trong cùng process, code được phép gọi setter không kiểm soát có thể tự đặt danh tính; cần hạn chế entry points và ranh giới có thẩm quyền.

### 7.3. Scope của asynchronous task

Với executor hoặc callback, tạo immutable context snapshot từ nguồn đáng tin rồi truyền qua tham số hoặc một cơ chế propagation được thiết kế cho task. Worker gắn scope riêng và đóng tại worker:

~~~text
Caller:
  verifiedContext = trustedSource()
  snapshot = immutableSubset(verifiedContext)
  submit(task, snapshot)
  closeCallerScope()

Worker:
  attachTaskScope(snapshot)
  try:
      recheckPolicyIfRequired()
      performWork()
  finally:
      detachTaskScope()
~~~

Đây là giả mã, không phải chương trình độc lập. Không giả định ThreadLocal tự theo thread mới. Không truyền scope có thread affinity từ caller rồi nhờ callback thread khác đóng. Task dài hạn cần chính sách expiry/revocation riêng, không giữ quyền vô hạn theo token lúc submit.

## 8. Ví dụ Java 17: ràng buộc subject, action và resource tại invocation

Ví dụ chạy được dùng **JDK dynamic proxy** để mô phỏng AOP ở ranh giới interface. Chương trình giả định hai principal đã được xác thực trước; nó minh họa permission checks, tenant/team restrictions và cleanup context, **không triển khai hệ thống xác thực hoàn chỉnh**.

Tạo tệp **InvocationAuthorizationDemo.java**:

~~~java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.function.Supplier;

public final class InvocationAuthorizationDemo {
    record Identity(String subject, Set<String> permissions,
                    Set<String> teams) {
        Identity {
            if (subject == null || subject.isBlank()) {
                throw new IllegalArgumentException("subject required");
            }
            permissions = Set.copyOf(Objects.requireNonNull(permissions));
            teams = Set.copyOf(Objects.requireNonNull(teams));
        }
    }

    static final class Scope {
        private static final ThreadLocal<Identity> ACTIVE =
                new ThreadLocal<>();

        static Identity current() {
            return ACTIVE.get();
        }

        static <T> T call(Identity identity, Supplier<T> operation) {
            Objects.requireNonNull(identity);
            Objects.requireNonNull(operation);
            Identity previous = ACTIVE.get();
            ACTIVE.set(identity);
            try {
                return operation.get();
            } finally {
                if (previous == null) {
                    ACTIVE.remove();
                } else {
                    ACTIVE.set(previous);
                }
            }
        }
    }

    interface DocumentService {
        String publish(String documentId);
    }

    static final class DocumentServiceImpl implements DocumentService {
        @Override
        public String publish(String documentId) {
            return "PUBLISHED:" + documentId;
        }
    }

    static final class AccessAdvice implements InvocationHandler {
        private final DocumentService target;
        private final Map<String, String> ownerTeam;

        AccessAdvice(DocumentService target,
                     Map<String, String> ownerTeam) {
            this.target = Objects.requireNonNull(target);
            this.ownerTeam = Map.copyOf(ownerTeam);
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {
            if (method.getName().equals("publish")) {
                Identity identity = Scope.current();
                String documentId = (String) args[0];
                String team = documentId == null
                        ? null : ownerTeam.get(documentId);

                boolean allow = identity != null
                        && team != null
                        && identity.permissions().contains("document.publish")
                        && identity.teams().contains(team);

                if (!allow) {
                    System.out.println("DENY action=document.publish");
                    throw new SecurityException("access denied");
                }
                System.out.println("ALLOW action=document.publish");
            }
            try {
                return method.invoke(target, args);
            } catch (InvocationTargetException wrapped) {
                throw wrapped.getCause();
            }
        }
    }

    public static void main(String[] args) {
        Identity alice = new Identity("alice",
                Set.of("document.publish"), Set.of("team-a"));
        Identity bob = new Identity("bob",
                Set.of("document.read"), Set.of("team-b"));

        DocumentService service = (DocumentService) Proxy.newProxyInstance(
                DocumentService.class.getClassLoader(),
                new Class<?>[] { DocumentService.class },
                new AccessAdvice(new DocumentServiceImpl(),
                        Map.of("doc-1", "team-a", "doc-2", "team-b"))
        );

        String result = Scope.call(alice,
                () -> service.publish("doc-1"));
        System.out.println("result=" + result);

        try {
            Scope.call(bob, () -> service.publish("doc-1"));
        } catch (SecurityException ex) {
            System.out.println("bob_denied=true");
        }

        try {
            Scope.call(alice, () -> service.publish("doc-2"));
        } catch (SecurityException ex) {
            System.out.println("wrong_team_denied=true");
        }

        System.out.println("scope_cleared="
                + (Scope.current() == null));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac InvocationAuthorizationDemo.java
java InvocationAuthorizationDemo
~~~

Kết quả stdout:

~~~text
ALLOW action=document.publish
result=PUBLISHED:doc-1
DENY action=document.publish
bob_denied=true
DENY action=document.publish
wrong_team_denied=true
scope_cleared=true
~~~

### Vì sao mỗi lần gọi có kết quả như vậy?

- **Alice + doc-1:** có permission publish, thuộc team-a và doc-1 do team-a sở hữu. Advice cho phép, target chạy đúng một lần.
- **Bob + doc-1:** Bob chỉ có quyền read, nên bị từ chối trước khi thực hiện nghiệp vụ.
- **Alice + doc-2:** có permission publish nhưng không thuộc team-b, nên bị từ chối theo resource scope.
- **Sau mọi lời gọi:** Scope.call khôi phục context trước đó hoặc xóa ThreadLocal trong finally, tránh giữ principal trong thread sau khi scope kết thúc.

**Giới hạn của demo:** Identity và Scope là mã học tập chạy trong một process; một caller có quyền thực thi mã Java cùng trust boundary có thể tự tạo Identity và gọi Scope.call. Trong hệ thống thực, nguồn tạo principal, đối tượng target và API attach scope phải được quản lý tại ranh giới xác thực. Map sở hữu tài liệu trong demo là dữ liệu bất biến giả định đáng tin, còn dữ liệu thật cần được tra cứu với tenant isolation và chính sách nhất quán. Proxy chỉ bảo vệ lời gọi đi qua nó: việc gọi trực tiếp DocumentServiceImpl có thể bỏ qua advice. ThreadLocal phù hợp demo đồng bộ, không tự bảo vệ task nền. Hệ thống thực nên dùng structured audit/logger và một policy service/logic được kiểm tra đầy đủ.

## 9. Lời gọi lồng nhau và scope stacking

Một invocation có thể gọi invocation khác. Nếu cần tạm dùng một context được ủy quyền, điều đúng là **khôi phục context của lời gọi cha**:

~~~text
outer invocation: subject Alice
    inner invocation: delegated subject Service-X
    inner ends -> restore Alice
outer ends -> remove context
~~~

Dùng remove() trong inner mà không restore sẽ khiến outer không còn principal. Ngược lại, quên remove() sau outer sẽ rò context sang tác vụ kế tiếp trên cùng pooled thread.

Nhưng thao tác push/pop principal không tự tạo quyền ủy nhiệm. Phải xác minh delegation scope, actor, effective subject, expiry và resource. **Không cho phép đổi principal sang admin chỉ bằng việc gọi một helper**.

## 10. Quyền ủy nhiệm và confused deputy

Phân biệt:

- **Authenticated actor:** thực thể đã xác thực thật ở entry point (ví dụ report-service).
- **Effective subject:** chủ thể thay mặt được dùng để đánh giá policy (ví dụ Alice).
- **Delegation:** bằng chứng hợp lệ rằng actor được phép thực hiện action cụ thể cho subject.
- **Resource scope:** tài nguyên được phép, có thể hẹp hơn quyền mặc định của actor.
- **Audit identity:** vẫn lưu actor thực và chủ thể được thay mặt, nếu phù hợp chính sách bảo mật.

Ví dụ:

~~~text
actor = report-service
effective_subject = alice
delegated_action = report.export
delegated_resource = report-17
delegation_expiry = 2026-10-20T03:00:00Z
~~~

Không dùng service account có quyền cao để tự động phê duyệt mọi yêu cầu của caller; điều này tạo nguy cơ **confused deputy**: thành phần đặc quyền bị dùng để làm việc mà caller không có quyền. Delegated capability phải hạn chế action, resource, tenant và thời hạn.

## 11. Quyền có thể thay đổi giữa check và use

**TOCTOU (time-of-check to time-of-use)** xuất hiện khi một kiểm tra ALLOW trở nên lỗi thời trước lúc có side effect:

~~~text
T1: advice xác minh Alice được publish doc-1
T2: quyền bị thu hồi hoặc doc-1 đổi owner
T3: nghiệp vụ publish dựa trên ALLOW cũ
~~~

Tùy hệ thống, có thể cần:

1. Đọc trạng thái tài nguyên có thẩm quyền và ghi trong cùng transaction/snapshot thích hợp.
2. Kiểm tra version khi update/commit, không chỉ kiểm tra lúc entry.
3. Re-authorize trước side effect sau một khoảng chờ dài.
4. Giới hạn thời gian hiệu lực hoặc policy version của authorization decision.
5. Đặt quy tắc rõ cho task đã lên lịch trước khi quyền bị thu hồi.
6. Phân biệt quyền **submit job** và quyền **thực hiện job**.

Around advice kiểm tra đầu method **không tự giải quyết tất cả race condition** ở database hoặc trong workflow phân tán. Bất biến bảo mật của tài nguyên cần được giữ ở điểm cập nhật có thẩm quyền khi cần.

## 12. Asynchronous workflow và vòng đời quyền

Khi một method trả Future/CompletionStage hoặc chỉ gửi việc vào queue, invocation trả về trước task hoàn tất. Một context được gắn với caller thread thường đã đóng trước khi worker chạy.

**Không nên:**

- Dùng ThreadLocal của caller trong executor mà không truyền ngữ cảnh.
- Capture request/session mutable rồi giữ nhiều giờ.
- Giữ scope của caller mở cho đến callback chạy trên thread khác.
- Tin snapshot permissions mãi mãi dù token hết hạn hoặc policy đã thay đổi.
- Dùng service admin rộng hơn phạm vi cần cho một task.

**Nên:**

- Chụp immutable context snapshot từ nguồn tin cậy, chỉ giữ các trường thật cần.
- Chuyển qua task/callback một cách tường minh.
- Attach/detach ở worker trong try/finally.
- Định nghĩa thời điểm policy check: lúc submit, lúc execute và khi commit tùy rủi ro.
- Áp dụng least privilege, expiry, revocation và audit actor/subject thích hợp.
- Kiểm tra cancellation và timeout: một handle đã timeout không chứng minh task nền đã dừng và cleanup xong.

Chú ý một CompletionStage hoàn tất exceptionally sau khi method return: quyết định **được phép gửi việc** không đồng nghĩa công việc **đã thành công**. Authorization log và business outcome log phải phân biệt.

## 13. Policy decision với cache và dữ liệu thiếu

Nếu authorization service, dữ liệu principal, permission hoặc resource metadata không sẵn sàng, nên có trạng thái **không thể xác nhận quyền** được xử lý theo fail-closed cho thao tác bảo vệ. Không mở rộng quyền mặc định chỉ để giảm latency.

Cache authorization decision cần cân nhắc khóa theo subject, action, resource, tenant, policy version và các thuộc tính liên quan. Một cache key chỉ chứa resource ID là nguy hiểm: ALLOW của Alice có thể bị tái sử dụng sai cho Bob. Cache phải có TTL và invalidation khi quyền bị thu hồi.

Khi policy phụ thuộc resource status, tenant hay owner, snapshot ở cache phải đủ mới theo yêu cầu an toàn. **Authentication cache** và **authorization cache** có mục tiêu/vòng đời khác nhau; token hợp lệ không bảo đảm quyền tài nguyên vẫn còn.

## 14. Lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Tin role/tenant trong payload chưa xác minh | Caller tự nâng quyền | Chỉ lấy từ trusted authentication/identity source |
| Chỉ kiểm tra principal != null | Người dùng nào cũng truy cập được | Kiểm tra action + resource + policy |
| Chỉ check permission mà bỏ tenant | Cross-tenant access | Resource-scoped authorization |
| Context ở biến global mutable | Lẫn danh tính giữa request | Per-invocation scope |
| Không cleanup ThreadLocal | Thread pool giữ principal cũ | try/finally, restore/remove |
| Giả định ThreadLocal truyền qua async | Worker thiếu hoặc sai context | Truyền snapshot, attach ở worker |
| Proxy có đường bypass | Lời gọi chạy không qua advice | Kiểm tra mọi entry path; invariant ở domain |
| Chấp nhận ALLOW cũ vô thời hạn | Thu hồi quyền không có hiệu lực | Expiry/revalidation/version check |
| Policy service lỗi thì cho phép | Quyền không xác định thành ALLOW | Fail-closed phù hợp |
| Đổi principal thành admin nội bộ | Confused deputy | Delegation có scope và audit |
| Batch kiểm tra một phần tử | Truy cập trái phép phần tử khác | Check mọi resource |
| Log token và context đầy đủ | Rò credential, dữ liệu nhạy cảm | Audit allowlist, redaction, access control |

## 15. Audit quyết định quyền mà không lộ bí mật

Aspect có thể ghi nhận một quyết định, nhưng cần phân biệt:

- **Authorization decision:** ALLOW hoặc DENY tại thời điểm đánh giá.
- **Invocation execution outcome:** business method chạy thành công hay lỗi.
- **Durable business change:** thay đổi đã commit hay chưa, có thể xảy ra muộn hơn.

Một quyết định ALLOW **không phải** sự kiện “tài liệu đã xuất bản”. Nếu nghiệp vụ sau đó thất bại, audit cần mô tả đúng hai mốc.

Ví dụ sự kiện đã làm sạch:

~~~json
{
  "event": "authorization_decision",
  "operation": "document.publish",
  "outcome": "deny",
  "reason_code": "RESOURCE_SCOPE_MISMATCH",
  "correlation_id": "req-42"
}
~~~

Không ghi password, bearer token, private key, authorization headers hoặc toàn bộ request object. Subject ID cũng có thể là dữ liệu cá nhân; cần kiểm soát truy cập, retention và cách mask phù hợp. Khi audit có yêu cầu bắt buộc về tính đầy đủ, phải thiết kế lưu trữ và nhất quán riêng; advice gọi logger thông thường không tự tạo bảo đảm giao dịch.

## 16. Thứ tự advice và những đường gọi khác nhau

Một call chain có thể là:

~~~text
TracingAdvice
   -> AuthorizationAdvice
       -> TransactionAdvice
           -> businessOperation
~~~

Kiểm tra trước TransactionAdvice có thể tránh mở transaction cho một lệnh bị từ chối. Nhưng thứ tự thực tế phụ thuộc cấu hình và cơ chế AOP. Nếu retry advice nằm ngoài authorization, mỗi attempt có thể được xét quyền; nếu authorization ở ngoài retry, quyền có thể chỉ xét một lần. Với operation có độ trễ dài hoặc quyền có thể thay đổi, cần lựa chọn phù hợp và kiểm thử.

Những câu hỏi nên đặt:

- Pointcut chọn đúng method có side effect hay bỏ sót overload?
- Lời gọi nội bộ cùng object có đi qua proxy không?
- Có endpoint batch, job, message listener hay CLI gọi target trực tiếp không?
- Annotation đặt trên interface có được tìm thấy trên implementation trong cơ chế hiện tại không?
- Với quyền nhạy cảm, bất biến nào phải được kiểm tra gần storage commit?
- Một policy denial có bị retry vô hạn bởi lớp retry khác không?
- Code phản hồi lỗi có vô tình tiết lộ tài nguyên không tồn tại hay thuộc tenant nào không?

Thiết kế pointcut cần đi kèm test coverage, không chỉ dựa vào tên class hay annotation.

## 17. Kiểm thử những trường hợp có ý nghĩa

| Kịch bản | Kỳ vọng |
| --- | --- |
| Principal hợp lệ, đúng action và resource | Target được gọi đúng một lần |
| Principal thiếu quyền | DENY, target không được gọi |
| Đúng quyền nhưng sai tenant/owner | DENY, target không được gọi |
| Không có context | DENY |
| Context hết hạn/bị thu hồi | DENY hoặc re-authorize theo chính sách |
| Policy service lỗi | Không vô tình ALLOW |
| Nghiệp vụ ném exception | Advice giữ nguyên exception, cleanup scope |
| Hai caller đồng thời khác principal | Context không lẫn |
| Nested invocation có delegated subject | Restore context cha |
| Thread pool được tái sử dụng | Không rò principal cũ |
| Task async bắt đầu sau caller return | Snapshot đúng và worker scope riêng |
| Resource đổi owner giữa check và update | Không bỏ qua chính sách chống TOCTOU |
| Batch có resource bị cấm | Không cấp quyền cho cả batch sai |
| Direct call bypass proxy | Có biện pháp bảo vệ đường gọi |
| Input có forged role/tenant | Không được nâng thành trusted context |
| Access decision được log | Không chứa token hoặc dữ liệu bí mật |

Một kiểm thử đặc biệt hữu ích là spy đếm target invocation. Trong case DENY, count phải bằng **0**; ALLOW bình thường phải bằng **1**. Ngoài unit test advice, nên kiểm thử tích hợp với đường vào thật và nhiều thread để phát hiện bypass, mất context hoặc rò context.

## 18. Quy trình triển khai

**Bước 1. Xác định trust boundary:** danh tính được xác thực bởi ai? Module nào có quyền tạo/gắn context và nhận delegation?

**Bước 2. Liệt kê protected operations:** mỗi action tương ứng một nghiệp vụ và resource resolver rõ ràng; đánh dấu các side effects nhạy cảm.

**Bước 3. Thiết kế authorization model:** subject, permissions, tenant/resource metadata, trạng thái, scope ủy quyền và những điều kiện thời gian.

**Bước 4. Chọn context transport:** tham số tường minh khi phù hợp; thread scope có restore/remove cho xử lý đồng bộ; task-scoped immutable snapshot cho async.

**Bước 5. Đặt advice đúng thứ tự:** authorization trước side effect, proceed đúng một lần; phối hợp retry/transaction/audit theo ngữ nghĩa.

**Bước 6. Đảm bảo enforcement đầy đủ:** kiểm tra proxy/weaving và mọi entry point; giữ kiểm tra domain/storage phù hợp nơi cần bảo vệ invariant.

**Bước 7. Thiết kế revoke, expiry và TOCTOU:** policy cache không tồn tại vô hạn, re-check tại mốc phù hợp, đặc biệt khi workflow kéo dài.

**Bước 8. Kiểm thử behavior và vận hành:** allow/deny, nested, concurrency, thread reuse, async, direct call, failure của policy, audit dữ liệu nhạy cảm.

## 19. Ghi nhớ

- Danh tính phải đến từ **nguồn xác thực đáng tin**, không từ tham số caller tự khai.
- Context phải ràng buộc với **một invocation**, gồm principal, action và resource cụ thể.
- AOP giúp thực thi kiểm tra nhất quán, nhưng phải xác minh **mọi đường gọi đều được bảo vệ**.
- **Deny by default** khi không chứng minh được quyền; policy error không tự thành ALLOW.
- Với quyền trên tài nguyên, **permission không thay thế tenant/owner check**.
- Scope phải có **vòng đời rõ ràng** và cleanup cả khi exception; async cần context của riêng task.
- Delegation phải giữ **actor thật, effective subject và giới hạn ủy quyền**, tránh confused deputy.
- Quyền có thể hết hạn hoặc bị thu hồi; authorization ở method entry không tự khắc phục race ở commit.
- Logging ALLOW/DENY phải phân biệt với business outcome và bảo vệ dữ liệu nhạy cảm.

**Khi danh tính và quyền được liên kết chính xác với từng lời gọi**, aspect có thể bảo vệ nhiều use case một cách thống nhất. Tính đúng đắn đến từ sự kết hợp giữa nguồn context đáng tin, chính sách dựa trên tài nguyên, vòng đời invocation chặt chẽ và điểm enforcement khó bị bỏ qua.