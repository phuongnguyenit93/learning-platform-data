# Ghi nhận từ chối truy cập mà không làm lộ dữ liệu bằng Aspect (AOP)

## 1. Mục tiêu và phạm vi

Một hệ thống có kiểm soát truy cập cần biết **ai đã cố thực hiện loại thao tác nào, quyết định cho phép hay từ chối, và vì sao phải điều tra**. Ghi nhận này giúp phát hiện truy cập trái quyền, hiểu lỗi cấu hình chính sách và kiểm toán. Nhưng chính việc ghi log khi từ chối có thể trở thành một kênh rò rỉ mới nếu advice in nguyên đối số, tài nguyên, thông báo lỗi, token, nội dung bản ghi hoặc toàn bộ đối tượng principal.

Với **Aspect-Oriented Programming (AOP)**, kiểm tra quyền và ghi nhận kết quả có thể đặt tại **join point** của một thao tác có ý nghĩa nghiệp vụ. Advice đứng trước lời gọi, phối hợp với bộ đánh giá chính sách, từ chối thực thi khi không đủ quyền, rồi tạo **sự kiện audit đã làm sạch**. Điều thiết yếu là audit phải hữu dụng để điều tra nhưng **không chứa dữ liệu mà người bị từ chối không được phép biết**.

Sau bài này, bạn có thể:

- Đặt **Policy Enforcement Point (PEP)** tại ranh giới thao tác và ghi nhận `DENY` nhất quán.
- Phân biệt **thông báo trả caller**, **sự kiện audit nội bộ**, **log kỹ thuật** và **metric tổng hợp**.
- Xác định dữ liệu được phép ghi theo allowlist; loại bỏ secret, payload, resource metadata nhạy cảm và lỗi có nội dung chưa được kiểm duyệt.
- Thiết kế schema sự kiện `action/decision/reason/time/correlation` có kiểm soát danh tính, mức chi tiết và quyền truy cập.
- Xử lý các trường hợp **không tồn tại tài nguyên, khác tenant, sai owner, sai quyền, lỗi policy**, mà không vô tình tiết lộ sự tồn tại hoặc thuộc tính của tài nguyên.
- Bảo vệ khỏi log injection, cardinality quá cao, quá tải audit sink, gọi trùng advice, lỗi async, race condition và các đường gọi bypass.
- Kiểm tra một ví dụ **Java 17 chạy được** với JDK dynamic proxy để minh họa interception kiểu AOP.

Bài tập trung vào **AOP cơ bản và nâng cao nói chung**. Những điểm khác nhau giữa interception bằng proxy và weaving được giải thích theo khả năng thực tế của từng kỹ thuật; không giả định có một bộ API đặc thù.

## 2. Từ chối truy cập không chỉ là một ngoại lệ

Hệ thống thường có các bước:

```text
Caller
   |
   v
Xác thực danh tính (trusted identity)
   |
   v
[ AOP join point của business operation ]
   |
   +--> Xác định action và resource theo hợp đồng
   +--> Policy Decision Point (PDP) đánh giá
   |       |
   |       +--> ALLOW -> proceed() -> business operation
   |       |
   |       +--> DENY  -> tạo audit event được kiểm soát
   |                     -> không gọi proceed()
   |                     -> trả lỗi an toàn cho caller
   |
   +--> Hoàn tất scope, trạng thái, telemetry
```

Các vai trò:

| Thành phần | Trách nhiệm |
|---|---|
| **Authentication** | Xác minh chủ thể; cung cấp principal đáng tin, tenant và quyền/delegation |
| **PDP** | Tính allow/deny dựa trên subject, action, resource, context và policy |
| **PEP** | Thực thi quyết định: chỉ gọi `proceed()` khi hợp lệ |
| **Audit producer** | Dựng sự kiện tối thiểu, có schema và phân loại mức nhạy cảm |
| **Audit sink** | Lưu, bảo vệ, phân quyền đọc, kiểm soát tính toàn vẹn và vòng đời bản ghi |
| **Client error mapper** | Trả thông điệp/trạng thái không tiết lộ thông tin bị từ chối |

Một `DENY` là **quyết định chính sách**. Nó khác `AUTHENTICATION_FAILED`, lỗi nghiệp vụ, lỗi hệ thống, lỗi policy store hoặc lời gọi đã được cho phép nhưng thực thi thất bại. Phân loại đúng sẽ giúp tránh tình trạng mọi lỗi đều trở thành “người dùng không đủ quyền”, hoặc dùng thông tin kỹ thuật nhạy cảm trong thông báo công khai.

**Nguyên tắc trung tâm:** log của một quyết định từ chối không phải bản chụp toàn bộ request hay object graph. Nó là một **sự kiện an toàn được dựng có chủ đích** từ dữ liệu đã được phê duyệt.

## 3. Mô hình đe dọa đối với nhật ký từ chối

Kẻ tấn công có thể không xem được đối tượng đích nhưng vẫn quan sát được response, thời gian phản hồi, độ dài lỗi, ID trả về, rate-limit behavior hoặc dữ liệu gián tiếp ở log được chia sẻ. Một người vận hành hoặc công cụ thu thập log có thể có quyền xem các trường mà caller không được xem. Vì vậy phải xác định hai nhóm rủi ro:

1. **Rò rỉ ra bên ngoài:** thông điệp trả caller tiết lộ “tài liệu tồn tại nhưng thuộc user X”, phân biệt resource ID thật/không tồn tại, hoặc phản hồi khác nhau theo tenant. Đây là kênh suy đoán tồn tại tài nguyên.
2. **Rò rỉ vào hệ thống quan sát:** advice ghi token, URL chứa query nhạy cảm, email, số tài khoản, đối tượng người dùng, request body, SQL parameter, exception message hoặc stack trace có chứa dữ liệu cá nhân.

Một số nguồn vô tình lộ dữ liệu:

- `logger.info("Denied " + args)`; `Arrays.deepToString(args)`; JSON serializer tự duyệt DTO, getter và collection.
- `Throwable.getMessage()`, `toString()` của exception hay in stack trace tùy ý. Thông báo có thể nhúng toàn bộ payload hoặc đường dẫn dữ liệu.
- `principal.toString()` hoặc `resource.toString()`; đối tượng có thể chứa token, claims hoặc field riêng tư.
- Tự động lấy mọi attribute làm span tag, metric label, tracing baggage hoặc MDC.
- Log URL đầy đủ: path và query có thể chứa token, mã xác minh hay ID nhạy cảm.
- Mã hóa Base64 “để an toàn” nhưng thực chất giữ nguyên dữ liệu có thể giải mã.
- Trả về `403 Forbidden: record 987 belongs to alice@...` hay `404` khác biệt theo trạng thái tài nguyên mà caller không nên biết.
- Dữ liệu bị từ chối được đẩy sang queue rồi serializer xử lý sau, tạo thêm bản sao tồn tại lâu.

**Không có một phép redact theo regex duy nhất đủ bảo vệ mọi trường hợp.** Nên sử dụng allowlist, policy phân loại và các giới hạn rõ ràng ở cả producer lẫn consumer.

## 4. Chọn dữ liệu cần ghi: tối thiểu nhưng có giá trị điều tra

Một sự kiện audit tốt có thể chứa:

| Trường | Ví dụ được duyệt | Lưu ý |
|---|---|---|
| `event_type` | `AUTHZ_DECISION` | Tập hằng số cố định |
| `action` | `DOCUMENT_READ`, `PAYMENT_APPROVE` | Mã action định nghĩa sẵn; không lấy từ input tự do |
| `decision` | `DENY` | Không nhầm với outcome nghiệp vụ |
| `reason_code` | `NOT_PERMITTED`, `POLICY_UNAVAILABLE` | Enum có ý nghĩa nhưng tránh tiết lộ dữ liệu |
| `occurred_at` | Timestamp do hệ thống tạo | Đồng bộ thời gian phù hợp |
| `request_correlation` | ID ngẫu nhiên do hệ thống cấp | Chỉ dùng ở kênh được phân quyền; không đưa ID tùy ý vào metric label |
| `actor_ref` | Định danh nội bộ được kiểm soát | Có thể là pseudonym được quản lý; phân quyền/retention riêng |
| `resource_type` | `DOCUMENT` | Danh mục cho phép; có thể không ghi ID |
| `resource_ref` | Reference hạn chế và có bảo vệ | Chỉ khi nhu cầu điều tra đòi hỏi, không mặc định xuất |
| `policy_version` | Mã phiên bản cấu hình | Hữu ích khi kiểm toán thay đổi quyết định |

Ngược lại, **không tự động xuất** mật khẩu, access/refresh token, session cookie, nội dung document, email/số điện thoại, request/response body, toàn URL, raw principal claims, stack trace hoặc thông điệp exception chưa được lọc.

Phân biệt rõ ba cấp sự kiện:

- **Bản ghi audit bảo vệ nghiêm ngặt:** phục vụ điều tra có thẩm quyền; có thể dùng reference/tokens được quản lý, thời gian lưu và quyền truy cập riêng.
- **Log vận hành thông thường:** nên dùng những trường ít nhạy cảm, số lượng giá trị thấp, không phải kho dữ liệu danh tính.
- **Metric:** chủ yếu đếm số `DENY` theo action hoặc reason chuẩn hóa. **Không dùng actor ID, resource ID, email hoặc idempotency key làm label có cardinality không giới hạn.**

Nếu nghiệp vụ thực sự cần liên kết sự kiện với actor/resource, hãy xác định chủ sở hữu dữ liệu, mục đích, quyền truy cập, thời hạn và cách tra cứu an toàn. Hash thường của email hoặc ID có miền nhỏ **không tự tạo ẩn danh**; nhiều giá trị có thể bị đoán bằng từ điển, còn hash ổn định hỗ trợ liên kết hoạt động xuyên thời gian. Nếu cần pseudonym, cân nhắc HMAC có quản lý khóa và kiểm soát phạm vi/rotation theo nhu cầu thực tế.

## 5. Chính sách thông báo: không làm lộ sự tồn tại của tài nguyên

Ví dụ người dùng ở `tenant-a` cố đọc `doc-7`. Ba tình huống có thể có:

1. `doc-7` thực sự không tồn tại.
2. `doc-7` tồn tại nhưng nằm ở `tenant-b`.
3. `doc-7` thuộc `tenant-a` nhưng principal không được chia sẻ.

Nếu caller không được quyền biết tình trạng của tài nguyên, phản hồi cho cả ba trường hợp có thể dùng **một thông báo trung tính**, chẳng hạn `Not available`; loại trạng thái giao thức (ví dụ lựa chọn giữa 403/404) phải dựa trên hợp đồng bảo mật của API.

Một bản ghi nội bộ có thể biết chi tiết hơn, nhưng ngay cả audit cũng không nên ghi trực tiếp email owner, tenant khác hoặc tên tài liệu. Nếu cần mã nguyên nhân chi tiết để phân tích, phải phân loại quyền truy cập và ranh giới lưu trữ của audit: không để lý do `CROSS_TENANT_OWNER_EMAIL=...` nằm trong log công khai.

**Không hứa che giấu chỉ bằng thông điệp.** Dù text giống nhau, endpoint còn có thể rò tồn tại qua thời gian truy vấn, kích thước response, header, redirect, số lần thử, số truy vấn cache hoặc hành vi rate limit. Cần đánh giá các kênh phụ này theo mô hình đe dọa và thiết kế truy vấn phù hợp.

Một số hệ thống bắt buộc phân biệt “chưa đăng nhập” và “đã đăng nhập nhưng thiếu quyền”; điều đó có thể hợp lệ khi loại phản hồi không tiết lộ tài nguyên cấm. Hãy **định nghĩa phân loại** và kiểm thử thay vì quyết định tùy ý ở từng advice.

## 6. Điểm chặn AOP: ghi đúng một lần khi policy từ chối

Một `around advice` có thể:

1. Xác định thao tác nghiệp vụ từ metadata đáng tin.
2. Xác định principal đã xác thực và resource cần kiểm tra.
3. Gọi PDP; nếu allow, gọi `proceed()` đúng theo hợp đồng.
4. Nếu deny, dựng **một sự kiện `AUTHZ_DECISION/DENY` đã làm sạch**, không gọi `proceed()` và phát lỗi an toàn.
5. Khi rời lời gọi, dọn context và duy trì tính đúng đắn của ứng dụng.

Mã giả:

```text
around(securedOperation):
    action = operationPolicyRegistry.lookup(joinPoint)
    if action is missing:
        denySafely(reason = POLICY_MISSING)  // fail closed

    actor = trustedIdentity.current()
    resource = trustedResourceReference(args)
    decision = policy.evaluate(actor, action, resource)

    if decision == DENY:
        audit.emit(safeEvent(
            action = action,
            outcome = DENY,
            reason = boundedReasonCode(decision)))
        throw publicSafeDenial()

    if decision == INDETERMINATE:
        audit.emit(safeEvent(action, DENY, POLICY_UNAVAILABLE))
        throw publicSafeDenial()

    return proceed()
```

Đây là **pseudocode** minh họa ngữ nghĩa, không phải chương trình Java độc lập. Chính sách đối với lỗi audit sink sẽ được bàn riêng ở phần dưới.

**Ranh giới quan trọng:** chỉ dùng exception type đặc thù hoặc một quyết định PDP có cấu trúc để nhận biết **lỗi bị từ chối quyền**. Không nên bắt mọi `RuntimeException` hay mọi lỗi nghiệp vụ rồi ghi `DENY`, vì điều đó khiến audit sai và che giấu lỗi hệ thống.

Nếu chính sách được kiểm tra thêm ở tầng database/transaction, lỗi deny có thể xuất hiện **sau khi `proceed()` bắt đầu**. Hệ thống cần quyết định ai là nguồn ghi audit chính để không đếm hai lần cùng một decision. Có thể tạo một `decision_id` nội bộ và cơ chế dedup theo logical operation khi cần độ chính xác mạnh; không tự tin rằng mỗi join point chỉ chạy một lần.

## 7. Khi policy lỗi: fail closed và phân biệt nguyên nhân

PDP đôi khi không có đủ dữ liệu: principal thiếu, tenant chưa xác định, resource metadata lỗi, policy store timeout, hoặc việc đọc ACL thất bại. Đây không phải tín hiệu ALLOW.

Các kết quả nên phân biệt:

| Kết quả policy | Hành động tại PEP | Sự kiện an toàn |
|---|---|---|
| `ALLOW` | Cho phép đi tiếp | Có thể ghi allow nếu có yêu cầu audit |
| `DENY` | Không gọi tác vụ | `DENY / NOT_PERMITTED` |
| `INDETERMINATE` / policy unavailable | Không gọi tác vụ theo fail-closed | `DENY / POLICY_UNAVAILABLE` hoặc outcome chuyên biệt theo schema |
| Không có rule/metadata bắt buộc | Không gọi tác vụ | `DENY / POLICY_MISSING` |
| Principal không được xác thực | Dừng tại ranh giới xác thực | `AUTHN_FAILURE` hoặc event tương ứng, không gán bừa lý do quyền |

**Fail closed** là nguyên tắc cho quyết định quyền: không thể chứng minh được allow thì không thực hiện side effect. Tuy nhiên, fail closed khi PDP lỗi **khác** với chuyện có bắt buộc audit sink phải ghi thành công trước khi trả lỗi hay không. Hai chính sách có hệ quả vận hành khác nhau.

Không đẩy toàn bộ exception hay trạng thái nội bộ ra caller. Với observability, có thể ghi loại lỗi được kiểm duyệt và mã nguồn gốc ổn định vào một kênh có quyền phù hợp, nhưng không lấy chuỗi lỗi raw.

## 8. Ví dụ Java 17: chặn lời gọi và ghi một DENY event an toàn

Chương trình sau dùng **JDK dynamic proxy** làm cơ chế interception kiểu AOP trên interface `Documents`. Chương trình thể hiện:

- `@Guarded(Action.DOCUMENT_READ)` gắn mã thao tác ổn định vào method.
- `Actor` đại diện danh tính được cấp **từ phạm vi thử nghiệm tin cậy**; trong ứng dụng thật, actor phải do thành phần xác thực tạo và chuyển qua ranh giới tin cậy.
- `requireAccess` từ chối khi document thiếu, khác tenant hoặc khác owner, nhưng chỉ ném một loại lỗi có thông điệp trung tính.
- Khi bị từ chối, handler **không gọi method đích**; audit chỉ ghi `action`, `outcome` và `reason` từ enum cố định, không ghi document ID, nội dung, actor ID hay exception message.
- `Store.read` kiểm tra lại quyền khi thực thi thật trong phương thức đồng bộ của `Store`, minh họa lớp bảo vệ sát tài nguyên nếu có đường truy cập khác hoặc trạng thái thay đổi giữa lúc check và lúc đọc.

Lưu thành **DenialAuditAspectDemo.java**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

public class DenialAuditAspectDemo {
    enum Action { DOCUMENT_READ }
    enum Outcome { DENY }
    enum Reason { NOT_PERMITTED }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface Guarded { Action value(); }

    record Actor(String id, String tenant) {}
    record Document(String owner, String tenant, String content) {}

    static final class AccessDenied extends RuntimeException {
        AccessDenied() { super("Not available"); }
    }

    static final class Store {
        private final Map<String, Document> documents = new HashMap<>();
        final AtomicInteger targetCalls = new AtomicInteger();

        synchronized void add(String id, Document document) {
            documents.put(id, document);
        }

        synchronized Document snapshot(String id) {
            return documents.get(id);
        }

        synchronized String read(Actor actor, String id) {
            targetCalls.incrementAndGet();
            Document document = documents.get(id);
            requireAccess(actor, document);
            return document.content();
        }
    }

    static void requireAccess(Actor actor, Document document) {
        if (actor == null || document == null
                || !document.tenant().equals(actor.tenant())
                || !document.owner().equals(actor.id())) {
            throw new AccessDenied();
        }
    }

    interface Documents {
        @Guarded(Action.DOCUMENT_READ)
        String read(String id);
    }

    static Documents guarded(Actor actor, Store store) {
        Documents target = id -> store.read(actor, id);
        return (Documents) Proxy.newProxyInstance(
                Documents.class.getClassLoader(),
                new Class<?>[] { Documents.class },
                (proxy, method, args) -> {
                    Guarded rule = method.getAnnotation(Guarded.class);
                    if (rule == null) {
                        throw new IllegalStateException("Access policy missing");
                    }
                    try {
                        requireAccess(actor, store.snapshot((String) args[0]));
                    } catch (AccessDenied denied) {
                        System.out.println("audit action=" + rule.value()
                                + " outcome=" + Outcome.DENY
                                + " reason=" + Reason.NOT_PERMITTED);
                        throw denied;
                    }
                    try {
                        return method.invoke(target, args);
                    } catch (InvocationTargetException ex) {
                        throw ex.getCause();
                    }
                });
    }

    static void tryRead(Documents documents, String id) {
        try {
            System.out.println("read=" + documents.read(id));
        } catch (AccessDenied denied) {
            System.out.println("client=" + denied.getMessage());
        }
    }

    public static void main(String[] args) {
        Store store = new Store();
        store.add("doc-7", new Document("alice", "team-a", "report-ready"));

        Documents owner = guarded(new Actor("alice", "team-a"), store);
        Documents colleague = guarded(new Actor("bob", "team-a"), store);
        Documents outsider = guarded(new Actor("eve", "team-b"), store);

        tryRead(owner, "doc-7");
        tryRead(colleague, "doc-7");
        tryRead(outsider, "doc-7");
        tryRead(owner, "missing");
        System.out.println("target_calls=" + store.targetCalls.get());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 DenialAuditAspectDemo.java
java DenialAuditAspectDemo
```

Kết quả đã xác minh:

```text
read=report-ready
audit action=DOCUMENT_READ outcome=DENY reason=NOT_PERMITTED
client=Not available
audit action=DOCUMENT_READ outcome=DENY reason=NOT_PERMITTED
client=Not available
audit action=DOCUMENT_READ outcome=DENY reason=NOT_PERMITTED
client=Not available
target_calls=1
```

Thứ tự kịch bản:

1. Chủ tài liệu `alice` trong `team-a` đọc `doc-7` thành công; nội dung trả về chỉ in ở **luồng kết quả được phép** của chương trình demo.
2. `bob` ở cùng tenant nhưng không phải owner bị từ chối, audit ghi một dòng cố định.
3. `eve` ở tenant khác cũng bị từ chối, không có thông tin của tenant đích trong dòng audit.
4. `alice` yêu cầu tài liệu `missing` và vẫn nhận cùng thông điệp bên ngoài.
5. `target_calls=1` chứng minh ba yêu cầu bị từ chối ở proxy **không chạy vào method `Store.read`**; chỉ lần hợp lệ chạy vào.

**Giới hạn cố ý:** đây là ví dụ đơn luồng, lưu trong bộ nhớ và in ra console để dễ thấy. Nó **không** cung cấp tính bền vững, chống sửa audit, atomicity xuyên tiến trình, quy tắc retention, kênh phân quyền hay bảo đảm non-leakage của thời gian phản hồi. `synchronized` chỉ bảo vệ một instance `Store` trong một JVM. Proxy chỉ intercept lời gọi đi qua interface; annotation thiếu làm handler ném `IllegalStateException` (fail closed trong demo), nhưng ứng dụng production phải ánh xạ lỗi này sang phản hồi công khai an toàn và có chính sách audit cho sự cố cấu hình.

Phương thức `tryRead` nằm **phía caller**, vì vậy các dòng `client=...` là mô phỏng phản hồi công khai; không phải lời khuyên in nguyên nội dung truy cập được trong audit. Việc đọc thành công trả `report-ready` chứng minh kết quả nghiệp vụ vẫn đúng, trong khi sự kiện từ chối không lấy dữ liệu đó.

## 9. Cách xây dựng schema audit có kiểm soát

Có thể định nghĩa một contract typed thay vì truyền map tùy ý:

```java
// Ví dụ cấu trúc minh họa; không phải chương trình độc lập.
enum AuditDecision { ALLOW, DENY }
enum AuditReason { NOT_PERMITTED, POLICY_MISSING, POLICY_UNAVAILABLE }
enum BusinessAction { DOCUMENT_READ, DOCUMENT_APPROVE }

record AuthorizationAudit(
    BusinessAction action,
    AuditDecision decision,
    AuditReason reason,
    java.time.Instant occurredAt,
    String safeCorrelationReference
) {}
```

Trong contract thực tế, `safeCorrelationReference` phải do thành phần đáng tin tạo/chuẩn hóa, có giới hạn kích thước và chính sách truy cập. **Không** cho caller truyền nguyên chuỗi log field hoặc tên event tùy ý.

Khuyến nghị thiết kế:

- **Enum/constant cho action và reason:** tránh code dùng nguyên tên phương thức hay message động làm lý do.
- **Timestamp có nguồn tin cậy:** chụp thời điểm quyết định tại nơi thực thi; bổ sung sequence/event ID khi thứ tự giữa nhiều instance quan trọng.
- **Correlation có phạm vi:** có thể tra cứu một điều tra được phép, nhưng không được tùy tiện lộ ID người dùng hoặc khai thác nó làm tracking identifier không kiểm soát.
- **Phân loại trường:** có catalog trường được phép, owner, hạn lưu và mức độ truy cập; schema mới phải được review.
- **Version schema và policy:** khi format hoặc logic cho phép/từ chối thay đổi, người điều tra cần biết điều kiện tương ứng; policy version thường là thông tin ít nhạy cảm hơn toàn policy document.
- **Giới hạn kích thước:** event phải bounded; mã lý do và action cố định giúp tránh input không tin cậy tạo bản ghi vô hạn.

Giữa các môi trường, không nên bật tùy chọn `debugAllArguments=true` trong production để “giải quyết nhanh” vì nó vô hiệu hóa toàn bộ nguyên tắc minimization. Những cuộc điều tra cần dữ liệu nhạy cảm phải đi qua cơ chế kiểm soát riêng.

## 10. Sanitization, escape và giới hạn tài nguyên

Ngay cả một trường cho phép ghi vẫn có thể bị kiểm soát bởi dữ liệu bên ngoài, chẳng hạn correlation ID hoặc resource reference. Trước khi xuất:

1. **Validate** độ dài, cú pháp và nguồn tạo. Ưu tiên ID do ứng dụng sinh.
2. **Normalize** nếu hợp đồng yêu cầu; không normalize bừa làm đổi danh tính.
3. **Escape** theo định dạng đích, bao gồm CR, LF, TAB, dấu nháy, backslash và ký tự điều khiển.
4. **Limit** theo byte biểu diễn cuối; tính cả tên trường và dấu phân cách, tránh cắt giữa mã Unicode/escape.
5. **Serialize** bằng writer có cấu trúc và kiểm soát schema; không nối string thô.
6. **Enforce quota/rate** để actor độc hại không thể tạo hàng triệu event chiếm tài nguyên.

Ví dụ một correlation string chứa:

```text
request-123
ERROR admin login accepted
```

Nếu được in nguyên thành hai dòng, log parser có thể hiểu dòng thứ hai là sự kiện riêng (**log injection**). Một event JSON/structured event qua serializer đúng sẽ escape ký tự điều khiển và giữ một bản ghi logic. Tuy nhiên, serializer không biến secret thành dữ liệu an toàn: **lọc quyền xuất trường phải xảy ra trước serialize**.

Nếu phải ghi payload sau khi redact, hãy xây dựng bản sao tối thiểu từ các field đã cho phép. Không dùng `obj.toString()` hoặc deep serializer trên đối tượng lạ; getter có thể truy vấn dữ liệu, có side effect hoặc lỗi, và quá trình serialize có thể quét tài nguyên rất lớn. Truncation của token vẫn có thể lộ token, nên secret cần **omit/redact hoàn toàn**.

Một `StackTrace` thường dài, có thể chứa đường dẫn nội bộ, thông tin request trong message và nhiều suppressed exceptions. Đừng coi việc log mọi throwable ở mức `WARN` là an toàn. Nếu cần trace kỹ thuật để điều tra, hãy sử dụng kênh có phân quyền, giới hạn, lọc thông điệp và cấu hình retention riêng.

## 11. Phản hồi công khai, audit nội bộ và side channel

Không nên dùng trực tiếp `decision.reason()` làm thông điệp cho người dùng. Cần một bảng ánh xạ được review:

| Ngữ cảnh | Phản hồi có thể công khai | Audit phân loại |
|---|---|---|
| Chưa xác thực | Yêu cầu xác thực | `AUTHN_REQUIRED` |
| Đã xác thực nhưng thiếu quyền đối với tài nguyên ẩn | `Not available` theo hợp đồng | `NOT_PERMITTED` |
| Tài nguyên không tồn tại và không được phép biết sự tồn tại | Có thể cùng `Not available` | Có thể dùng mã nội bộ chung |
| Chính sách không sẵn sàng | Thông báo lỗi trung tính | `POLICY_UNAVAILABLE`, phân quyền riêng |
| Tài nguyên có công khai nhưng thao tác bị cấm | Có thể trả “Forbidden” nếu hợp đồng cho phép | `NOT_PERMITTED` |

Tính không tiết lộ còn phụ thuộc các tín hiệu khác: thời gian xử lý, HTTP status, kích thước response, số lượng kết quả, location header, cache behavior, tốc độ rate limiting và khả năng đo sự tồn tại qua retry. Không thể hứa bảo vệ mọi side channel chỉ bằng một chuỗi thông điệp giống nhau. Khi sự tồn tại của tài nguyên là bí mật, cần thiết kế từ query/data access đến network response và thử nghiệm timing side channel theo mô hình đe dọa.

**Không ghi nội dung bị từ chối trong audit dù chỉ "để tìm lỗi".** Việc denied xảy ra thường là lúc độ tin cậy của nguồn dữ liệu thấp nhất; attacker có thể cố ý dùng input độc hại để phá log.

## 12. Đảm bảo việc từ chối thật sự chặn thao tác

Lập trình viên đôi khi ghi audit rồi vẫn gọi `proceed()` hoặc log một ngoại lệ sau khi side effect đã chạy. Một lời từ chối đúng nghĩa phải:

- Chặn trước side effect được bảo vệ khi chính sách không cho phép.
- Chuyển lỗi ra caller theo hợp đồng nhất quán, không biến deny thành kết quả hợp lệ.
- Không làm lộ object/args trong exception.
- Không phụ thuộc việc format/log thành công để tự nhiên đổi từ `DENY` thành `ALLOW`.
- Có chính sách riêng cho resource thay đổi trạng thái trong lúc xử lý.

**TOCTOU (time-of-check/time-of-use):** advice đánh giá quyền ở `t1`, đến `t2` mới có ghi/đọc dữ liệu; resource hoặc quyền có thể thay đổi giữa hai thời điểm. Pre-check ở AOP là lớp kiểm tra sớm. Với invariant quan trọng, cần xác minh ở sát commit bằng transaction, optimistic locking, conditional update, tenant predicate hay guard ở storage. Tránh ghi audit “DENY vì không được duyệt” cho một giao dịch đã thực sự commit trước khi lỗi khác xảy ra: audit phải phản ánh đúng thời điểm và lớp quyết định.

Một phương thức bị deny ngay tại AOP không được gọi target; có thể kiểm tra bằng counter/mock có kiểm soát. Trường hợp deny ở lớp dưới sau một pre-check allow cần được mô tả là **một quyết định sau**, tránh tạo hai sự kiện không thể phân biệt.

## 13. Các đường đi có thể bỏ qua advice

Một bảo vệ dùng proxy không tự áp dụng khi caller giữ tham chiếu đến object gốc hoặc một phương thức trong cùng object gọi trực tiếp phương thức khác bằng `this`. Cơ chế weaving có phạm vi khác nhưng vẫn cần xác minh join point được hỗ trợ. Vì audit gắn với enforcement, **bypass PEP có thể đồng thời bypass cả quyết định quyền và bản ghi DENY**.

Phải kiểm tra:

- HTTP endpoint, CLI, batch, message handler, callback, scheduler và đường quản trị.
- Self-invocation, raw implementation instance, reflection, overload, interface-vs-implementation annotation.
- Phương thức không có policy metadata và các join point không thuộc pointcut.
- Gọi trực tiếp storage hoặc API ngoài từ code không đi qua operation boundary.
- Library/worker dùng service identity hoặc delegated identity khác principal request.

Các lớp bảo vệ:

- Công khai API có ngữ nghĩa business operation thay vì cho phép gọi raw storage rộng khắp.
- Ràng buộc mọi command nhạy cảm với policy; **thiếu metadata ⇒ fail closed** tại boundary được quản lý.
- Tái kiểm tra quyền/tenant/bất biến sát dữ liệu, ngay cả khi AOP đã kiểm tra.
- Ghi audit tại enforcement layer phù hợp và dùng correlation/dedup để hiểu nhiều lớp quyết định.
- Test interception coverage thực tế bằng entrypoint, không chỉ unit test hàm PDP.

Không nên dựa trên một lời gọi tên phương thức hay annotation để chứng minh rằng mọi đường truy cập đã được bảo vệ.

## 14. Ghi audit dưới tải cao, lỗi sink và độ bền

Một sự kiện DENY có thể là **best-effort telemetry**, hoặc **audit bắt buộc** theo hợp đồng hệ thống. Cần quy định trước:

**Trường hợp best-effort:** khi collector không sẵn sàng, ứng dụng vẫn giữ quyết định `DENY` và trả lỗi an toàn cho caller; event có thể bị mất, nên hệ thống phải đo drop count và báo động. Nếu tác vụ *được phép* phụ thuộc tính sẵn sàng của audit cho quy định nghiệp vụ, không được tự áp dụng chính sách best-effort này.

**Trường hợp audit bắt buộc:** phải có một ranh giới lưu bền vững phù hợp để đáp ứng cam kết kiểm toán, ví dụ append-only store có bảo vệ, transaction/outbox nếu audit và effect thuộc cùng domain transaction, hoặc broker được cấu hình durability. Nếu ghi thất bại, quyết định tiếp tục hay dừng thao tác được xác định bởi chính sách bắt buộc, **không** để exception từ logger tự quyết định ngẫu nhiên.

Đối với riêng `DENY`, không được biến từ chối thành cho phép chỉ vì sink gặp lỗi. Nhưng cũng không nên bị treo vô thời hạn nếu hệ thống log đang đầy. Thiết kế giới hạn timeout, bounded queue, backpressure, sampling có điều kiện và đường cảnh báo. Một số audit bắt buộc **không thể sampling**; thay vì âm thầm bỏ, phải dùng cơ chế lưu phù hợp và quy trình sự cố.

Bảo vệ audit store:

- Giới hạn quyền đọc/ghi, tách quyền quản trị và truy vấn.
- Mã hóa khi lưu/truyền và bảo vệ khóa.
- Phòng sửa/xóa trái phép theo mức bảo đảm thực tế: append-only/WORM, integrity chain hoặc signed batches khi cần.
- Đồng bộ thời gian, event ID và policy version để phục vụ điều tra.
- Chính sách retention/xóa phù hợp với trách nhiệm dữ liệu; audit không được giữ mọi ID vô thời hạn chỉ vì “để dự phòng”.
- Bảo vệ bản sao ở export, alert, dashboard, index, backup và môi trường test.
- Theo dõi lỗi ghi audit, dropped/duplicated events và độ trễ xử lý mà không đưa raw principal/resource ID vào metric label.

## 15. Ghi một lần trong kiến trúc retry và bất đồng bộ

Đơn vị **logical operation** có thể qua nhiều attempt. Ví dụ HTTP client retry, message consumer redelivery, callback hoặc worker xử lý chậm. Một caller có thể bị deny nhiều lần thật; nhưng cùng một logical request bị quan sát ở nhiều interceptor cũng có thể tạo audit trùng.

Cần làm rõ các ngữ nghĩa:

- **Authorization attempt**: mỗi lần PDP/PEP quyết định.
- **Logical request**: một ý định nghiệp vụ gốc, có correlation được tạo đáng tin.
- **Business effect**: thay đổi dữ liệu thực sự xảy ra.
- **Audit event**: bản ghi một quyết định cụ thể, có event ID riêng.

Không nhầm “một event mỗi attempt” với “một event duy nhất mọi hoàn cảnh”. Có thể ghi mỗi attempt để phát hiện tấn công lặp; khi tổng hợp cần tránh tính mỗi lớp interceptor thành một request khác. Nếu yêu cầu *exactly-once audit* trong một miền lỗi cụ thể, cần thiết kế durable event identity và dedup ở đúng nơi, không thể chỉ dựa vào advice chạy một lần.

**Asynchronous context:** truyền principal/correlation qua executor hoặc message không được mặc định lấy từ `ThreadLocal` còn sót của request trước. Gắn và restore context quanh task/callback; xác định ai có quyền khi thực thi muộn (người khởi tạo, delegated principal, hay service identity). Nếu permission bị thu hồi trong thời gian queue chờ, chính sách có thể yêu cầu đánh giá lại tại nơi thực thi.

**Không giữ live reference đến args** trong event queue. Chụp các trường đã lọc và giới hạn vào một giá trị bất biến tại điểm quyết định, rồi mới enqueue. Đây là cách tránh vừa giữ object graph lớn, vừa phát sinh log dữ liệu thay đổi sau thời điểm policy.

## 16. Trường hợp cảnh báo và xử lý an ninh

Không phải DENY nào cũng là tấn công. Người dùng có thể thử URL cũ, có quyền bị thu hồi, làm sai thao tác hoặc gõ nhầm ID. Ngược lại, các chuỗi DENY lặp trên nhiều resource/tenant có thể báo hiệu enumeration.

Đối với cảnh báo, ưu tiên các mẫu có ngữ nghĩa:

- Tỷ lệ DENY tăng mạnh cho một action.
- DENY nhiều lần sau khi quyền vừa thay đổi.
- Nhiều request không có principal đáng tin, thiếu policy metadata hoặc policy service unavailable.
- Kết hợp DENY với rate-limit hits, dấu hiệu credential abuse hoặc activity bất thường.

Khi cần nhóm theo actor hoặc địa chỉ nguồn, dùng pipeline an ninh có phân quyền và retention rõ ràng. Không phát từng actor ID/IP vào metric label toàn hệ thống; nên dùng thống kê giới hạn cardinality và tham chiếu điều tra qua hệ thống riêng.

Một policy deny **không có nghĩa đã phát hiện xâm nhập**. Đặt nhãn “suspicious” phải dựa trên tiêu chí và dữ liệu được phép quan sát, tránh suy luận từ duy nhất một lỗi 403/404.

## 17. Kiểm thử để chứng minh không lộ dữ liệu

Các test hữu ích nhất kiểm tra **đầu ra thực tế của cả client và audit sink**, không chỉ xác minh `Policy.evaluate()` trả `DENY`:

1. **Sai owner:** caller cùng tenant nhưng không sở hữu tài nguyên; target không được gọi, response trung tính, audit không có chủ sở hữu/tài liệu.
2. **Khác tenant:** thử tài liệu của tenant khác; không có target invocation, không leak tenant hay resource ID.
3. **Resource không tồn tại:** response và audit theo cùng chính sách không tiết lộ tồn tại; xem cả status/header/độ dài phản hồi.
4. **Principal không xác thực:** phân loại đúng authentication vs authorization, không ngầm biến null principal thành allow.
5. **Policy unavailable/missing:** fail closed; lý do kỹ thuật chỉ trong kênh audit được phân quyền, caller không nhận stack trace.
6. **Canary bí mật:** truyền token/email/chữ ký giả có dấu nhận diện qua args, principal, resource, exception; assert chuỗi đó không xuất hiện ở log, trace, metric, audit và response bị từ chối.
7. **Log injection:** truyền CR/LF, ký tự điều khiển, dấu quote và separator vào những trường được phép xuất; event vẫn là một bản ghi hợp lệ sau serialization.
8. **Giới hạn kích thước:** dữ liệu rất dài, collection lớn, DTO có `toString()` độc hại; formatter không duyệt/chuyển đổi dữ liệu bị cấm và không vượt quota.
9. **Đường gọi bypass:** raw object, self-invocation, reflection, overload, async, queue và batch. Bảo đảm deny vẫn chặn tại enforcement layer.
10. **Race/TOCTOU:** quyền hoặc trạng thái tài nguyên thay đổi giữa pre-check và commit; side effect không vi phạm policy.
11. **Lỗi audit sink:** sink throw, timeout, queue đầy; quyết định từ chối vẫn giữ nguyên, ứng dụng tuân theo chế độ best-effort hoặc mandatory đã khai báo.
12. **Retry/multiple interceptors:** mỗi quyết định có event identity/correlation đúng; không nhân đôi nghiệp vụ hoặc đếm sai metric.
13. **Quyền truy cập kho audit:** người chỉ được xem log vận hành không xem được reference nhạy cảm ở audit bảo vệ riêng.
14. **Clock/sampling/retention:** sự kiện audit bắt buộc không biến mất vì sampling; thời gian lưu, xóa và export hoạt động theo chính sách.

Kiểm thử unit cho renderer và PDP cần đi cùng integration test đúng entrypoint. Nếu chỉ test một hàm tạo chuỗi log, bạn chưa chứng minh đường gọi thực tế luôn đi qua advice hoặc framework ghi log không bổ sung thông tin nhạy cảm.

## 18. Lỗi thường gặp và cách khắc phục

| Biểu hiện | Nguyên nhân | Cách xử lý |
|---|---|---|
| DENY log có email/token | Ghi nguyên principal, claims hoặc args | Allowlist field, redact/omit trước serialize |
| Caller biết tài liệu tồn tại | Thông điệp lỗi khác nhau theo owner/tenant/existence | Response trung tính và đánh giá side channel |
| Ghi thiếu sự kiện DENY | Raw implementation/self-invocation/worker bypass | Audit join-point coverage, guard sát dữ liệu |
| Mọi exception đều báo `ACCESS_DENIED` | Catch-all không phân biệt lỗi policy và lỗi nghiệp vụ | Enum quyết định/lỗi rõ ràng, preserve cause ở nơi phù hợp |
| DENY vẫn gọi method đích | Advice log rồi proceed | Nhánh DENY phải chặn, test invocation count |
| Log bị tách thành sự kiện giả | Chuỗi tùy ý chứa CR/LF/quote | Structured writer, escape theo format và bounded fields |
| Log nổ bộ nhớ | Serialize object lớn rồi cắt | Chỉ dựng schema an toàn, chặn trước serializer |
| Sink lỗi khiến thao tác bất ngờ được phép | Catch lỗi log và chạy đường mặc định | Giữ quyết định quyền độc lập với ghi telemetry |
| Sink lỗi làm hệ thống treo | Unbounded blocking/log queue | Timeout, bounded queue và chính sách degrade rõ |
| Event DENY bị trùng | Cùng logical request qua nhiều advice/retry | Event ID, correlation và aggregation semantics |
| Log chứa resource ID dù deny | “Để debug” tự ghi raw ID | Chỉ dùng reference an toàn trong kênh điều tra có quyền |
| Metric tăng cardinality | Dùng user/resource ID làm nhãn | Nhãn action/reason cố định, điều tra chi tiết ở kho khác |

## 19. Quy trình áp dụng

**Bước 1 — Liệt kê thao tác bảo vệ.** Chọn business operation, pointcut và chính sách cụ thể; không dựa chỉ vào getter, setter hay URL. Mỗi action có hợp đồng về dữ liệu kiểm tra và phản hồi khi deny.

**Bước 2 — Xây dựng PDP và PEP có phân loại.** Quyết định có dạng typed `ALLOW/DENY/INDETERMINATE`; khi không đủ bằng chứng allow thì chặn. Bảo đảm thiếu policy metadata bị phát hiện, không được mặc nhiên public.

**Bước 3 — Định nghĩa event contract.** Chỉ khai báo các trường và mã lý do đã duyệt, có giới hạn byte và ngữ nghĩa correlation. Tách protected audit khỏi log thường và metric.

**Bước 4 — Phát DENY đúng điểm.** Trước side effect, không proceed nếu bị từ chối, không ghi raw exception/args. Ở tầng khác có guard riêng cần xác định event owner để tránh trùng không kiểm soát.

**Bước 5 — Bảo vệ kho audit.** Xác định mức bền vững, quyền đọc, retention, integrity, cơ chế quá tải và lỗi sink. Với audit bắt buộc, chọn giao dịch/append-only mechanism phù hợp.

**Bước 6 — Kiểm thử theo mô hình đe dọa.** Thử sai tenant, sai owner, resource thiếu, policy unavailable, canary secret, bypass AOP, async/retry, log injection và sink failure. Kiểm tra cả client response, audit store và metric thực.

### Checklist rà soát cuối

- [ ] Không cho phép thao tác khi PDP trả `DENY` hoặc không thể quyết định allow.
- [ ] Mọi ranh giới thao tác nhạy cảm được enforce; có kiểm tra coverage.
- [ ] Nhánh bị từ chối **không gọi proceed/target**, không tạo side effect.
- [ ] Log DENY chỉ gồm trường allowlist; không có raw args, token, object, exception hay private resource data.
- [ ] Mã action/reason, kích thước event và nguồn correlation được kiểm soát.
- [ ] Caller không nhận thông tin về resource/tenant/owner bị cấm.
- [ ] Có kế hoạch giảm rò qua status, timing, cache và response length.
- [ ] Kênh audit có phân quyền, retention, integrity và chính sách khi sink lỗi.
- [ ] Dị bộ/retry không dùng sai principal, không nhân bản dữ liệu nhạy cảm hoặc làm sai số đếm.
- [ ] Test canary và integration chứng minh không leak ở response, log, trace, metric và audit.
- [ ] Kiểm tra quyền sát side effect đối với trạng thái có thể đổi giữa check và use.

## 20. Ghi nhớ

**Một quyết định từ chối có ích cho điều tra chỉ khi nó được ghi bằng dữ liệu tối thiểu, đáng tin và đúng ngữ nghĩa.** AOP giúp đặt PEP và audit ở cùng ranh giới nghiệp vụ, nhưng không tự bảo đảm rằng mọi lời gọi đều đi qua advice, rằng log không lộ secret, hoặc rằng audit store có độ bền cần thiết. Cần kết hợp **fail-closed enforcement, sự kiện allowlist, phản hồi công khai trung tính, bảo vệ sink và kiểm thử mọi đường đi** để ghi nhận `DENY` mà không biến hệ thống quan sát thành một kênh tiết lộ dữ liệu.
