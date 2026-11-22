# Đặt kiểm tra quyền tại ranh giới thao tác có ý nghĩa bằng Aspect (AOP)

## 1. Mục tiêu và vấn đề

Một hệ thống có thể xác thực danh tính người dùng thành công nhưng vẫn thực hiện thao tác sai quyền: xem tài liệu của tenant khác, phê duyệt đơn do chính mình tạo, sửa một đơn đã khóa, hoặc gọi chức năng quản trị từ một đường thực thi nội bộ. Với **Aspect-Oriented Programming (AOP)**, ta có thể dùng **pointcut** chọn các thao tác nghiệp vụ và **advice** kiểm tra chính sách trước khi cho phép tác vụ chạy.

Khó khăn nằm ở **vị trí đặt kiểm tra**. Nếu chỉ kiểm tra khi người dùng mở giao diện hoặc truy cập một URL, những đường vào khác có thể bỏ qua. Nếu gắn kiểm tra cho mọi getter/setter, chính sách bị phân tán, khó hiểu và có thể kiểm tra sai đối tượng. Cách thiết kế tốt hơn là nhận diện **ranh giới của hành động có ý nghĩa nghiệp vụ**: tạo đơn, chấp thuận, chuyển tiền, xuất dữ liệu, mời thành viên, thay đổi quyền, xem hồ sơ riêng tư hoặc giải ngân.

Mục tiêu của bài:

- Phân biệt **authentication**, **authorization** và kiểm tra **business invariant**.
- Chọn đúng **đơn vị thao tác** và **join point** để một quyết định quyền tương ứng một hành động nghiệp vụ cụ thể.
- Xác định **chủ thể (subject)**, **hành động (action)**, **tài nguyên (resource)** và **ngữ cảnh (environment)** bằng dữ liệu đáng tin.
- Phối hợp kiểm tra ở **ranh giới thao tác** với kiểm tra sát dữ liệu/side effect để tránh lỗ hổng bypass và **time-of-check/time-of-use (TOCTOU)**.
- Xử lý quyền theo tenant, ownership, trạng thái, dữ liệu trả về, tác vụ bất đồng bộ và yêu cầu kiểm toán.
- Xây dựng ví dụ Java 17 chạy được sử dụng **JDK dynamic proxy** làm một hình thức interception kiểu AOP.

Đây là kiến thức **AOP tổng quát**, độc lập thư viện. Những giới hạn của proxy và weaving được nêu rõ vì không phải mọi cơ chế AOP đều có cùng tập join point.

## 2. Xác thực khác phân quyền

**Authentication (xác thực)**: trả lời *ai đang yêu cầu?*, có bằng chứng đăng nhập đáng tin hay không. Đầu ra có thể là định danh principal/actor, tenant và thuộc tính được hệ thống xác thực.

**Authorization (phân quyền)**: trả lời *principal đó có được thực hiện hành động này đối với tài nguyên này, trong trạng thái và ngữ cảnh hiện tại, hay không?*

**Business invariant (bất biến nghiệp vụ)**: quy tắc phải luôn đúng của miền dữ liệu. Một số quy tắc vừa có yếu tố quyền vừa phụ thuộc trạng thái, như “người duyệt không được duyệt yêu cầu của chính họ”. Một số quy tắc chỉ là hợp lệ nghiệp vụ, như “đơn đã hủy không thể giao hàng”. Đừng ép tất cả vào một nhãn vai trò đơn giản.

Ví dụ một request `POST /documents/doc-7/approve`:

| Câu hỏi | Dữ kiện cần xét | Hệ quả |
|---|---|---|
| Ai gọi? | Principal đã xác thực, tenant hiện tại | Không tin tên người dùng do body tự khai |
| Họ định làm gì? | Hành động `document.approve` | Khác với quyền đọc tài liệu |
| Đối tượng nào? | Document `doc-7` và tenant sở hữu | Không chỉ xét route hoặc loại Java |
| Tài nguyên đang ở trạng thái nào? | `SUBMITTED` hay `APPROVED` | Một quyết định dựa vào snapshot cũ có thể sai |
| Có ràng buộc bổ sung nào? | Người duyệt không phải người tạo, giới hạn thẩm quyền | Quyền theo vai trò chưa đủ |
| Cho phép tạo hiệu ứng nào? | Thay trạng thái, phát event, gửi thông báo | Cần ngăn toàn bộ hành động nếu denied |

Một principal có vai trò `REVIEWER` không mặc nhiên được duyệt *mọi tài liệu trên mọi tenant*. Quyết định thường có dạng:

```text
allow = authenticated(actor)
     AND action_is_authorized(actor, action)
     AND within_same_tenant(actor, resource)
     AND subject_resource_relationship_is_valid(actor, resource)
     AND business_state_allows(action, resource)
```

Điều kiện thực tế phải được biểu diễn trong một chính sách được kiểm thử. **Thiếu dữ liệu xác thực, tài nguyên không tìm thấy hoặc không đủ quyền ⇒ deny theo chính sách**.

## 3. "Ranh giới thao tác có ý nghĩa" là gì?

Đó là điểm tại đó mã ứng dụng bắt đầu hoặc cam kết thực hiện một **hành động mà người dùng/hệ thống xem như một đơn vị quyền**. Nó thường có tên nghiệp vụ rõ ràng và hiệu ứng quan sát được.

So sánh:

| Điểm chặn | Vấn đề | Điểm phù hợp hơn |
|---|---|---|
| `setStatus(APPROVED)` | Setter không chứa ai duyệt, tài liệu nào và vì sao | `approveDocument(documentId)` |
| `repository.save(entity)` | Một lệnh save có thể phục vụ hàng chục mục đích | `publishArticle(articleId)` hoặc `updateBillingAddress(...)` |
| `getUser()` | Getter có thể dùng cho cả truy cập công khai lẫn riêng tư | `viewPrivateProfile(userId)` |
| `executeSql(...)` | Khó xác định ý định và actor ở tầng truy cập dữ liệu | Thao tác domain + lọc dữ liệu ở tầng lưu trữ |
| `sendEmail(...)` | Hành vi kỹ thuật xuất phát từ nhiều workflow | `inviteTeamMember(teamId, email)` với quyền tương ứng |

Không có nghĩa mọi điểm chặn kỹ thuật đều vô dụng. **Kiểm soát truy cập theo bản ghi**, tenant filter và bảo vệ ở kho dữ liệu vẫn cần. Nhưng nếu hỏi “người này có quyền phê duyệt tài liệu này không?”, nơi dễ hiểu và dễ kiểm chứng nhất thường là **đầu vào của thao tác phê duyệt**, trước side effect.

Một thao tác có thể chứa nhiều bước hoặc nhiều side effect. Quyết định quyền phải bao phủ **toàn logical operation**. Nếu gọi trực tiếp bước con có thể bỏ qua kiểm tra ở đầu thao tác, cần thêm hàng rào tương ứng tại nơi có thể đi vòng.

## 4. AOP tổ chức kiểm tra quyền ra sao?

Các khái niệm chung:

- **Join point:** điểm thực thi có thể bị chặn, tùy cơ chế weaving/interception.
- **Pointcut:** biểu thức/quy tắc chọn những join point thuộc phạm vi kiểm soát.
- **Advice:** mã chạy ở join point; một `before advice` phù hợp với kiểm tra quyền trước lời gọi, còn `around advice` có quyền quyết định có tiếp tục lời gọi hay không.
- **Proceed:** hành động chuyển quyền điều khiển tới phần xử lý đích; khi không được phép, advice **không được** gọi proceed.
- **Policy Decision Point (PDP):** nơi tính quyết định allow/deny theo actor, action, resource, context.
- **Policy Enforcement Point (PEP):** nơi thật sự chặn việc thực thi khi quyết định là deny.

Trong kiến trúc nhỏ, advice có thể vừa đọc metadata vừa gọi policy và chặn. Trong hệ thống lớn, nên tách **PEP/interceptor** khỏi **PDP/chính sách** để dễ test, audit và dùng chung nhiều giao thức gọi.

Luồng minh họa:

```text
Entry point (HTTP / message / CLI / scheduler)
         |
         v
Trusted identity context
         |
         v
AOP interception: business operation join point (PEP)
         |
         +--> xác định semantic action
         +--> lấy resource ID từ tham số đã xác minh
         +--> nạp dữ liệu tối thiểu cần cho quyết định
         +--> PDP.evaluate(actor, action, resource, context)
                    |
             +------+------+
             |             |
           DENY           ALLOW
             |             |
             v             v
        dừng gọi        proceed()
                           |
                 Domain/data-level guard
                           |
                  business side effect
```

Advice phải chạy trước khi có side effect. Nếu policy chưa nhận đủ ngữ cảnh để quyết định, thông thường nên từ chối hoặc yêu cầu thêm dữ liệu đáng tin, không suy đoán quyền từ trạng thái mặc định.

## 5. Chọn pointcut theo ý định nghiệp vụ

Ba cách biểu diễn phổ biến:

### 5.1. Ranh giới khai báo rõ

Ví dụ một interface có các thao tác:

```java
// Mảnh minh họa API, không phải chương trình độc lập.
interface DocumentCommands {
    DocumentView viewDocument(String documentId);
    ApprovalReceipt approveDocument(String documentId);
}
```

Cơ chế interceptor gắn action `document.read` với phương thức `viewDocument` và `document.approve` với `approveDocument`. Đây là mapping có ngữ nghĩa: **tên thao tác** và **quyền** phải được review cùng nhau.

### 5.2. Annotation chính sách

Có thể gắn annotation cho phương thức/loại thao tác để công cụ AOP nhận diện điểm chặn. Annotation chỉ là **metadata**, không phải bản thân hàng rào bảo mật: nếu một lời gọi không đi qua interception thì annotation có thể không được thực thi.

Chú ý metadata trên **interface vs implementation**, method override, generic bridge method, method được gọi qua reflection và giới hạn proxy/weaver. Nếu phương thức mới được thêm mà không có annotation, cần chính sách **fail closed**: hoặc từ chối ở cấp boundary, hoặc xác nhận nó được phân loại public/không cần guard một cách tường minh. Chỉ lọc các phương thức *có annotation* còn lại chạy tự do là lỗ hổng nếu toàn interface lẽ ra phải được bảo vệ.

### 5.3. Pointcut theo namespace/loại

Quy tắc như “mọi phương thức thuộc `application.commands`” có thể dùng để cưỡng chế chính sách mặc định, nhưng phải tránh tự suy quyền chỉ từ prefix `get*` hay `admin*`. Kết hợp điều kiện về **vùng boundary** với metadata về semantic action và kiểm thử coverage.

Dù dùng cách nào, phải lập một bảng bao phủ:

| Hành động | Entry points | Guard bắt buộc | Dữ liệu cho quyết định |
|---|---|---|---|
| Xem tài liệu riêng | Web, job nội bộ, message consumer | `document.view` | Principal, tenant, owner, trạng thái chia sẻ |
| Duyệt tài liệu | Web, batch job | `document.approve` | Reviewer, owner, trạng thái submitted |
| Xuất dữ liệu | API, báo cáo theo lịch | `report.export` | Tenant, phạm vi dữ liệu, quota |
| Quản lý thành viên | API, CLI quản trị | `team.members.manage` | Người thao tác, team, quan hệ và role |

Mỗi đường vào hợp lệ phải chạm vào **một enforcement path** tương đương, hoặc được chặn riêng với cùng chính sách trước khi phát sinh hiệu ứng.

## 6. Dữ liệu đầu vào cho policy phải đáng tin

Một quyết định quyền thường cần bộ bốn:

```text
DecisionRequest(
    subject = authenticated principal,
    action = semantic business action,
    resource = resource identified and loaded by trusted code,
    context = tenant / time / state / ownership / attributes
)
```

Các quy tắc quan trọng:

1. **Subject:** không lấy vai trò, user ID, tenant ID hay danh sách quyền từ JSON do caller tự khai. Principal phải đến từ đường xác thực đáng tin; nếu có delegation, quyết định cần kiểm tra chuỗi ủy quyền.
2. **Action:** lấy từ hợp đồng phương thức/pointcut đã định nghĩa, không dùng tham số text `"approve"` của request làm chứng cứ cấp quyền.
3. **Resource:** không quyết định chỉ dựa vào ID do client gửi; cần nạp dữ liệu/metadata thật với tenant, owner, project, tổ chức, trạng thái và policy liên quan.
4. **Context:** thời gian, IP, thiết bị, yêu cầu hai người duyệt, quota hoặc phân vùng dữ liệu nếu policy sử dụng thì phải có nguồn đáng tin và ngữ nghĩa được ghi rõ.
5. **Unknown:** resource không tồn tại, policy lỗi, principal thiếu hoặc dữ liệu cần cho quyết định không đầy đủ thì thông thường **deny**; phản hồi bên ngoài có thể che sự tồn tại của tài nguyên nếu yêu cầu bảo mật đòi hỏi.

Một người có quyền trong `tenant-a` không được mở tài nguyên thuộc `tenant-b` chỉ bằng cách thay ID. Đó là lỗi **object-level authorization/IDOR**: xác thực thành công và thao tác route đúng vẫn chưa đủ.

**Nạp tài nguyên trước khi cho phép** cũng cần thận trọng: phép đọc metadata để ra quyết định phải có phạm vi và không tự phát side effect. Không xuất dữ liệu nhạy cảm của resource bị từ chối qua thông báo lỗi, log, trace hoặc thời gian phản hồi nếu có thể tránh.

## 7. RBAC, ABAC và quan hệ chủ thể–tài nguyên

AOP không quyết định nên dùng mô hình quyền nào. Nó đưa **điểm thực thi chính sách** tới ranh giới thao tác; PDP có thể áp dụng:

- **RBAC (Role-Based Access Control):** vai trò như `READER`, `EDITOR`, `REVIEWER`. Dễ hiểu nhưng riêng vai trò thường thiếu phạm vi tài nguyên.
- **ABAC (Attribute-Based Access Control):** kết hợp role, tenant, phòng ban, thuộc tính resource, thời gian, phân loại dữ liệu và trạng thái nghiệp vụ.
- **Quan hệ chủ thể–tài nguyên (ReBAC):** người dùng là chủ sở hữu, thành viên workspace, người được chia sẻ hoặc cấp phê duyệt trong sơ đồ quan hệ.

Ví dụ: `approveDocument(doc)` yêu cầu reviewer có quyền trong tenant sở hữu tài liệu, khác owner và tài liệu ở trạng thái `SUBMITTED`. Đây là phối hợp **role + tenant + quan hệ + trạng thái**, vượt xa một điều kiện “user có role reviewer”.

Chính sách có thể thay đổi theo tổ chức hoặc thời gian. Cache quyết định quyền phải xác định key đầy đủ (subject, action, resource, version/thuộc tính và tenant), thời hạn ngắn, khả năng vô hiệu hóa khi quyền bị thu hồi và xử lý khi policy service không sẵn sàng. Cache nhầm principal/resource hoặc dùng quyết định cũ có thể trở thành lỗ hổng nghiêm trọng.

## 8. Ví dụ Java 17: AOP proxy tại ranh giới đọc và duyệt tài liệu

Ví dụ chạy được sau dùng **JDK dynamic proxy** để chặn các lời gọi đến `DocumentActions`:

- Annotation `@Guarded(Action.VIEW)` và `@Guarded(Action.APPROVE)` mô tả ý nghĩa bảo vệ của mỗi method.
- `Policy.require` kiểm tra tài liệu tồn tại, cùng tenant, ownership/reviewer và trạng thái.
- `guarded` tạo proxy, tra chính sách trước khi gọi `Service`.
- `Store` cũng kiểm tra quyền **bên trong phương thức `synchronized`, ngay tại lúc đọc hoặc thay đổi dữ liệu**, để minh họa lớp bảo vệ thứ hai chống race giữa lần kiểm tra ở proxy và thao tác thực tế.
- Actor được **gắn sẵn khi tạo service/proxy trong ví dụ**. Trong hệ thống thật, chỉ thành phần đã xác thực và được tin cậy mới được gắn actor; không để request bên ngoài tự chọn một actor bất kỳ.

Lưu mã nguồn sau vào **AuthorizationAspectDemo.java**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.util.HashMap;
import java.util.Map;

public class AuthorizationAspectDemo {
    enum Action { VIEW, APPROVE }
    enum State { SUBMITTED, APPROVED }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface Guarded { Action value(); }

    record Actor(String id, String tenant, boolean reviewer) {}
    record Document(String id, String tenant, String owner, State state) {}

    static final class Denied extends RuntimeException {
        Denied() { super("Not available"); }
    }

    static final class Policy {
        void require(Actor actor, Action action, Document doc) {
            if (doc == null || !doc.tenant().equals(actor.tenant())) {
                throw new Denied();
            }
            boolean allowed = switch (action) {
                case VIEW -> doc.owner().equals(actor.id()) || actor.reviewer();
                case APPROVE -> actor.reviewer()
                    && !doc.owner().equals(actor.id())
                    && doc.state() == State.SUBMITTED;
            };
            if (!allowed) throw new Denied();
        }
    }

    static final class Store {
        private final Map<String, Document> documents = new HashMap<>();

        synchronized void add(Document doc) { documents.put(doc.id(), doc); }

        synchronized Document snapshot(String id) { return documents.get(id); }

        synchronized String view(Actor actor, String id, Policy policy) {
            Document doc = documents.get(id);
            policy.require(actor, Action.VIEW, doc);
            return "view=" + doc.id() + " status=" + doc.state();
        }

        synchronized String approve(Actor actor, String id, Policy policy) {
            Document doc = documents.get(id);
            policy.require(actor, Action.APPROVE, doc);
            documents.put(id, new Document(doc.id(), doc.tenant(), doc.owner(), State.APPROVED));
            return "approved=" + id;
        }
    }

    interface DocumentActions {
        @Guarded(Action.VIEW) String view(String id);
        @Guarded(Action.APPROVE) String approve(String id);
    }

    static final class Service implements DocumentActions {
        private final Actor actor;
        private final Store store;
        private final Policy policy;

        Service(Actor actor, Store store, Policy policy) {
            this.actor = actor;
            this.store = store;
            this.policy = policy;
        }

        public String view(String id) {
            return store.view(actor, id, policy);
        }

        public String approve(String id) {
            return store.approve(actor, id, policy);
        }
    }

    static DocumentActions guarded(Actor actor, Store store, Policy policy) {
        DocumentActions target = new Service(actor, store, policy);
        return (DocumentActions) Proxy.newProxyInstance(
            DocumentActions.class.getClassLoader(),
            new Class<?>[] { DocumentActions.class },
            (proxy, method, args) -> {
                Guarded rule = method.getAnnotation(Guarded.class);
                if (rule != null) {
                    policy.require(actor, rule.value(), store.snapshot((String) args[0]));
                }
                try {
                    return method.invoke(target, args);
                } catch (InvocationTargetException ex) {
                    throw ex.getCause();
                }
            });
    }

    static void checkDenied(String label, Runnable command) {
        try {
            command.run();
            System.out.println(label + "=UNEXPECTED_ALLOW");
        } catch (Denied ex) {
            System.out.println(label + "=DENIED");
        }
    }

    public static void main(String[] args) {
        Policy policy = new Policy();
        Store store = new Store();
        store.add(new Document("doc-7", "tenant-a", "alice", State.SUBMITTED));

        DocumentActions alice = guarded(
            new Actor("alice", "tenant-a", false), store, policy);
        DocumentActions bob = guarded(
            new Actor("bob", "tenant-a", true), store, policy);
        DocumentActions eve = guarded(
            new Actor("eve", "tenant-b", true), store, policy);

        System.out.println(alice.view("doc-7"));
        checkDenied("owner_approve", () -> alice.approve("doc-7"));
        System.out.println(bob.approve("doc-7"));
        checkDenied("cross_tenant_view", () -> eve.view("doc-7"));
        System.out.println(bob.view("doc-7"));
    }
}
```

Lệnh biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 AuthorizationAspectDemo.java
java AuthorizationAspectDemo
```

Kết quả đã chạy và kiểm chứng:

```text
view=doc-7 status=SUBMITTED
owner_approve=DENIED
approved=doc-7
cross_tenant_view=DENIED
view=doc-7 status=APPROVED
```

Giải thích:

1. `alice` là chủ của `doc-7` trong `tenant-a` nên được xem tài liệu.
2. `alice` không có vai trò reviewer và không thể phê duyệt tài liệu của mình: `DENIED`.
3. `bob` có quyền reviewer trong cùng tenant, không phải owner và tài liệu đang ở `SUBMITTED`, nên được phê duyệt.
4. `eve` có vai trò reviewer nhưng thuộc `tenant-b`, vì vậy ngay cả quyền đọc tài liệu của tenant khác cũng bị từ chối.
5. Sau khi phê duyệt, `bob` đọc lại trạng thái `APPROVED`.

**Giới hạn của demo:** đây là mô hình in-memory trong một JVM; `synchronized` chỉ đồng bộ các luồng dùng **chung instance `Store`**, không đảm bảo nguyên tử giữa nhiều tiến trình hay với database bên ngoài. Một transaction/conditional update thích hợp ở nơi lưu trữ thật mới bảo vệ ranh giới dữ liệu trong môi trường phân tán.

Proxy chỉ áp dụng cho lời gọi đi qua `DocumentActions`; lời gọi trực tiếp đến `Service`/`Store` có thể không qua advice. Demo cố ý đặt guard thứ hai tại `Store` và không cung cấp endpoint cho client bên ngoài. Handler minh họa chỉ xem annotation **trên interface** và chỉ gọi policy đối với method có `@Guarded`; trong thiết kế production có yêu cầu “mọi command đều phải có policy”, hãy **deny method thiếu khai báo** hoặc dùng registry bắt buộc, đồng thời xử lý các phương thức `Object` của proxy theo hợp đồng rõ. Không được coi “thiếu annotation” là “tự động public”.

## 9. Ranh giới kiểm tra và time-of-check/time-of-use

Nếu đọc trạng thái để cấp quyền ở thời điểm `t1`, sau đó dùng trạng thái đó để ghi ở `t2`, các thay đổi đồng thời có thể làm quyết định trở nên lỗi thời:

```text
t1: advice đọc document.status = SUBMITTED -> allow
    |
    +-- worker khác hủy document hoặc thu hồi role
    |
t2: thao tác cập nhật document -> APPROVED
    (đã dùng quyết định dựa trên thông tin cũ)
```

Đây là lớp rủi ro **TOCTOU**. AOP check *trước* lời gọi rất hữu ích để từ chối sớm, nhưng không đủ đảm bảo bất biến phụ thuộc trạng thái được giữ đến commit.

Những kỹ thuật cần cân nhắc:

- **Kiểm tra sát side effect trong cùng transaction/critical section.** Đọc trạng thái, xác minh quyền/điều kiện và thay đổi dữ liệu trong một cơ chế đồng bộ phù hợp.
- **Conditional update:** ví dụ `UPDATE document SET state='APPROVED' WHERE id=? AND tenant_id=? AND state='SUBMITTED' AND version=?`; số dòng bị sửa giúp phát hiện trạng thái đã đổi. Đây chỉ là mảnh SQL minh họa; yêu cầu reviewer/ownership vẫn phải được chứng minh bằng chính sách và dữ liệu đáng tin.
- **Optimistic locking/version:** so sánh version khi ghi, xử lý xung đột thay vì âm thầm ghi đè.
- **Row lock/transaction isolation:** chọn khi điều kiện phải cố định trong một giao dịch và mức cô lập thực sự hỗ trợ.
- **Thu hồi quyền:** nếu policy có thể thay đổi giữa check và commit, cần xác định ranh giới thời gian được phép (đầu thao tác, lúc commit, hay tại cả hai). Một số thao tác nhạy cảm cần đánh giá lại hoặc dùng phiên bản policy ổn định trong transaction.

Dù kiểm tra ở nhiều lớp, phải dùng **cùng ngữ nghĩa chính sách** hoặc chỉ rõ kiểm tra nào là quyền và kiểm tra nào là bất biến. Hai lớp cho kết quả trái nhau thường gây khó vận hành và dễ làm người viết bỏ một lớp.

## 10. Vượt qua proxy, gọi nội bộ và phạm vi weaving

Đây là điểm đặc biệt quan trọng với AOP dùng cho bảo mật.

Một cơ chế **proxy interception** chỉ chặn lời gọi đi qua đối tượng proxy. Ví dụ:

```text
external caller -> proxy -> securedService.approve()    [có advice]
securedService.internalMethod() -> this.approve()       [có thể bỏ qua proxy]
external caller -> rawService.approve()                 [bỏ qua proxy]
```

Lời gọi `this.approve()` bên trong cùng object thường không đi qua proxy của kiểu proxy-based interception. Với các cơ chế weaving khác, tập join point có thể bao gồm nhiều lời gọi nội bộ hơn, nhưng vẫn phải xác minh rõ ngữ nghĩa của công cụ đang dùng. Không suy ra rằng thêm annotation đồng nghĩa mọi đường chạy đều được chặn.

Các đường bypass cần audit:

- Đối tượng raw/implementation bị giữ và gọi trực tiếp.
- Self-invocation, method private/final/static hoặc constructor mà interceptor không hỗ trợ.
- Interface có overload/generic bridge method và metadata không được đọc đúng.
- Batch job, event handler, message consumer, callback, test helper hoặc tác vụ quản trị gọi thẳng vào lớp thấp hơn.
- Truy cập dữ liệu trực tiếp bằng SQL/script mà không đi qua command được bảo vệ.
- Gọi từ module hoặc thư viện khác có thể truy cập public method ngoài đường chuẩn.

Các cách bảo vệ bổ sung:

1. **Đóng đường truy cập implementation** bằng API/module boundary và dependency wiring hợp lý.
2. **Có guard sát dữ liệu/side effect** cho invariant cốt lõi.
3. **Test coverage của interception**, chứng minh từng entry point/overload bắt buộc đi qua guard.
4. **Bảo vệ tài nguyên ở tầng dữ liệu** nếu có nhiều đường đọc/ghi, tenant filter, row-level security hoặc constraint phù hợp.
5. **Fail closed với command chưa khai báo policy**, có cơ chế xét duyệt rõ cho thao tác thực sự public.

Đừng giấu toàn bộ logic cấp quyền trong một aspect vô danh mà không có tài liệu/hợp đồng. Đường đi để biết ai có quyền thực hiện một operation phải dễ truy vết và test.

## 11. Kiểm tra dữ liệu trả về, danh sách và field-level access

Không phải mọi truy cập đều là lệnh ghi. Một lời gọi được phép “xem danh sách” không có nghĩa mọi dòng và cột trong danh sách đều được phép xuất:

- **Row/object-level:** lọc kết quả theo tenant, owner, ACL hoặc phạm vi tổ chức; không phân trang toàn bộ rồi mới bỏ item, vì sẽ làm lộ tổng số/nhịp dữ liệu và tính toán sai pagination.
- **Field-level:** cùng một tài liệu có thể công khai tiêu đề nhưng riêng tư số điện thoại, số tiền hoặc nội dung thẩm định; policy phải xác định trường nào được đọc.
- **Aggregate/report:** tổng hợp dữ liệu đôi khi vẫn tiết lộ một cá nhân nếu nhóm quá nhỏ; cần chính sách phạm vi và ngưỡng.
- **Export/bulk:** xuất nhiều tài nguyên là một thao tác riêng (ví dụ `report.export`), thường cần quyền mạnh hơn thao tác xem một item và có giới hạn số lượng/tốc độ.
- **Query filter:** cần áp quyền sớm trong truy vấn hoặc tầng lưu trữ; một advice chỉ kiểm tra “được gọi search” nhưng trả toàn bộ database không tạo an toàn.

AOP có thể chặn entrypoint xuất dữ liệu và áp dụng chính sách chung, nhưng **lọc bản ghi và trường** vẫn phải thực hiện ở nơi hiểu được dữ liệu, tránh biến interceptor thành một serializer phức tạp không thể chứng minh là an toàn.

## 12. Thực thi bất đồng bộ và ngữ cảnh danh tính

Một thao tác nghiệp vụ có thể đi qua executor, callback, queue hoặc nhiều dịch vụ. Quyết định cấp quyền ở luồng gọi không tự lan truyền sang nơi phát sinh side effect sau đó.

Các tình huống:

**Executor/callback:** `ThreadLocal` trên luồng gọi không tự xuất hiện ở worker. Nếu cần dùng actor trong tác vụ, truyền một snapshot danh tính đã được chuẩn hóa qua cơ chế đáng tin, gắn vào phạm vi thực thi và **restore/clear** khi kết thúc. Không để actor của request cũ lưu trên thread pool.

**Job lên lịch:** tác vụ chạy sau nhiều giờ không nhất thiết còn được phép theo vai trò lúc tạo job. Hãy xác định job chạy theo **service identity** với quyền hạn rõ ràng, hay theo **delegated authority** có thời hạn và phạm vi. Với thao tác nhạy cảm, cần đánh giá lại quyền trước khi thực hiện.

**Queue/message consumer:** message có thể đến từ nguồn không đáng tin. Trường `userId` trong payload không phải principal đã xác thực; consumer cần xác thực nguồn, bảo vệ toàn vẹn metadata được ủy quyền và quyết định quyền tại nơi xử lý.

**Remote calls:** thông tin actor chuyển qua mạng cần giao thức và ranh giới tin cậy. Không coi header `X-Role: admin` do caller tự đặt là bằng chứng được cấp quyền. Dịch vụ nhận phải áp chính sách của mình với principal/credential đã xác thực.

**Async completion:** kiểm tra trước khi submit có thể phù hợp với “quyền được xếp lịch”, nhưng chưa chắc đủ để “quyền thực thi/cập nhật” khi hàng đợi xử lý sau đó. Hãy phân biệt hai quyền và quyết định thời điểm hiệu lực.

Cần định nghĩa rõ **ai là subject của automation**: người tạo lịch, người bấm duyệt, hay tài khoản dịch vụ thay mặt tổ chức. Tránh chuyển mọi tác vụ nền sang một danh tính siêu quyền mà không có ràng buộc hoạt động.

## 13. Lỗi, phản hồi bị từ chối và kiểm toán

Một deny phải ngăn nghiệp vụ chạy và trả trạng thái/exception được phép công khai. Không trả thông điệp chi tiết như “Tài liệu này của tenant X do người Y tạo” cho actor vốn không được biết tài liệu tồn tại.

Phân biệt:

| Tình huống | Ý nghĩa nội bộ | Cách xử lý |
|---|---|---|
| Principal chưa xác thực | Chưa có danh tính tin cậy | Dừng tại ranh giới yêu cầu đăng nhập/xác thực |
| Đã xác thực nhưng không đủ quyền | Authorization deny | Không gọi proceed hoặc side effect |
| Resource không tồn tại/ngoài tenant | Không được công khai sự tồn tại | Có thể trả thông báo trung tính theo hợp đồng |
| Policy store tạm thời không truy cập được | Không thể xác định allow | Fail closed; có cơ chế vận hành/giám sát phù hợp |
| Business invariant thay đổi trong transaction | Conflict hoặc trạng thái không hợp lệ | Không commit effect sai; trả lỗi theo hợp đồng |
| Lỗi xuất audit | Không đồng nhất với lỗi quyền | Chọn chính sách bảo đảm audit và xử lý lỗi riêng |

Nếu có yêu cầu audit mạnh, cần đảm bảo bản ghi **who, action, resource, policy decision, thời điểm và request correlation** đáng tin, không đưa access token, dữ liệu cá nhân nhạy cảm hoặc toàn bộ payload vào log. Với nghiệp vụ cần audit không mất sự kiện, dùng cơ chế transaction/outbox hoặc log chuyên dụng theo hợp đồng; một logger không đồng bộ “best effort” không tạo bảo đảm ghi nhận bất biến.

Không đưa resource ID hoặc user ID cardinality cao làm nhãn metric không giới hạn. Có thể đo tỷ lệ allow/deny theo action chuẩn hóa, tenant class hoặc mã lỗi khi đã được duyệt.

**Bản thân việc phân quyền phải có thể quan sát**, nhưng không làm rò chính thông tin mà nó bảo vệ.

## 14. Kiểm thử đúng boundary, không chỉ kiểm tra hàm policy

Bộ test quan trọng:

1. **Đúng quyền, đúng resource:** allow thao tác hợp lệ và kiểm tra side effect thật.
2. **Sai quyền:** deny khi actor không có action; assert target không được gọi, không tạo dữ liệu, không phát event.
3. **Sai tenant/owner:** thử thay resource ID của tenant khác; deny thống nhất ở mọi entry point.
4. **Trạng thái thay đổi:** sau khi quyết định đầu tiên, concurrent worker chuyển trạng thái; kiểm tra bước commit không ghi sai.
5. **Principal không xác thực/không đầy đủ:** thiếu actor, tenant hoặc thông tin policy; deny.
6. **Phương thức mới chưa khai báo:** kiểm tra fail-closed theo hợp đồng của boundary.
7. **Self-invocation/raw object:** xác định mọi đường có thể bypass proxy; test trực tiếp đường vào thật để thấy guard ở tầng thấp hơn vẫn thực thi.
8. **Mảng/list/report:** chỉ xuất các hàng/trường được phép; kiểm tra count, pagination và export.
9. **Async/queue:** truyền metadata bị giả mạo, identity đã hết hạn hoặc role bị thu hồi; không thực thi với quyền cũ ngoài hợp đồng.
10. **Lỗi policy store:** policy evaluation timeout/exception; không vô tình allow.
11. **Tác dụng phụ của kiểm tra:** denied phải xảy ra **trước** side effect; kiểm tra không vô tình gọi getter/hành vi có side effect.
12. **Audit:** denied, allowed, conflict và error có sự kiện phù hợp; không chứa dữ liệu bí mật.
13. **Concurrency:** nhiều yêu cầu thao tác trên cùng resource; trạng thái cuối và số effect phải đúng. Dùng latch/barrier để tạo interleaving có chủ ý.
14. **Mọi đường vào:** HTTP, CLI, worker, callback, message consumer và đường quản trị đều được kiểm tra theo chính sách đúng.

Tách rõ test **policy** (actor/action/resource/context → decision), **interception** (guard có chặn đúng lời gọi không), **domain invariant** (không thể tạo trạng thái cấm) và **end-to-end** (mọi entry point thật đều bảo vệ). Một unit test trực tiếp gọi `Policy.require` thành công không chứng minh proxy đã được nối vào luồng ứng dụng.

## 15. Những sai lầm phổ biến

| Sai lầm | Hệ quả | Cách khắc phục |
|---|---|---|
| Chỉ kiểm tra role ở controller | Đường vào batch/message/direct invocation bị bỏ qua | Kiểm tra ở business command boundary, có thêm guard sát effect |
| Coi URL được bảo vệ là resource được bảo vệ | Đổi `documentId` để lấy dữ liệu của người khác | Kiểm tra object-level/tenant/owner tại policy |
| Annotation nhưng không có interception thật | Lời gọi đi qua raw instance, self-invocation hoặc method ngoài pointcut | Audit tập join point, wiring và coverage |
| Lời gọi mới không annotation được chạy tự do | Thao tác thiếu policy được ngầm cho phép | Fail closed hoặc yêu cầu explicit public classification |
| Lấy vai trò từ request body | Caller có thể giả role/tenant | Principal chỉ từ trusted authentication boundary |
| Cho phép trước rồi trạng thái bị đổi | TOCTOU cho phép thao tác đáng lẽ không hợp lệ | Kiểm tra sát commit, locking/conditional update |
| Cache quyết định theo mỗi user | Quyền trên tài nguyên/tenant khác bị dùng lẫn | Cache key đầy đủ, TTL/invalidation và kiểm tra thuộc tính |
| Cố giải quyết row-level access bằng check method | Method được phép nhưng dữ liệu trả về vượt phạm vi | Lọc tại tầng query/data và field projection |
| Dùng service account toàn quyền cho mọi job | Job nền vượt quyền người yêu cầu | Service identity/delegation có phạm vi, hạn và audit |
| Log nguyên payload khi deny | Rò dữ liệu qua hệ thống quan sát | Log mã action/quyết định an toàn, redact dữ liệu nhạy cảm |

## 16. Hướng dẫn áp dụng vào thiết kế thật

Một quy trình thực tế:

**Bước 1 – Liệt kê các thao tác cần bảo vệ.** Đọc kịch bản nghiệp vụ thay vì chọn pointcut từ tên getter, setter. Ghi rõ `actor + action + resource + context` cho từng thao tác.

**Bước 2 – Định nghĩa policy tập trung.** Mỗi quyền có tên ổn định, phạm vi tenant, quy tắc ownership/relationship và điều kiện trạng thái. Quy định trường hợp unknown/failure và hành vi deny.

**Bước 3 – Đặt PEP ở command/query boundary.** Dùng annotation, mapping hoặc registry để buộc mỗi thao tác đi qua cơ chế interception. Kiểm tra metadata interface/implementation và các đường có thể bỏ qua.

**Bước 4 – Bảo vệ bất biến ở dữ liệu/side effect.** Với trạng thái thay đổi đồng thời, dùng transaction, conditional update hoặc constraint phù hợp. Không trông chờ một pre-check bảo vệ trạng thái mãi mãi.

**Bước 5 – Kiểm tra cả read/export và background worker.** Kiểm tra row/field-level; xác định principal cho message, cron job và callback; không tin metadata do bên ngoài tự khai.

**Bước 6 – Audit và kiểm thử phủ toàn bộ boundary.** Test allow, deny, tenant crossing, race, policy failure, bypass, async và leak; rà soát khi thêm method hoặc nguồn dữ liệu mới.

### Checklist trước khi triển khai

- [ ] Mọi thao tác nhạy cảm có tên hành động nghiệp vụ, tài nguyên và principal rõ.
- [ ] Actor/tenant/role lấy từ nguồn xác thực đáng tin.
- [ ] Policy có **deny-by-default**, xử lý missing/unknown nhất quán.
- [ ] Mọi entry point bắt buộc đi qua PEP hoặc guard tương đương.
- [ ] Quyền theo đối tượng, owner và tenant được kiểm tra trên resource thật.
- [ ] Side effect có check nhất quán ở ranh giới lưu trữ/transaction.
- [ ] Không có self-invocation/raw-instance route vô tình bypass hàng rào.
- [ ] Kết quả tìm kiếm, export và dữ liệu theo field không vượt phạm vi.
- [ ] Async, queue, job chạy theo identity/ủy quyền hợp lệ.
- [ ] Event audit không lộ bí mật; policy failure không ngầm cấp quyền.
- [ ] Có test concurrency, policy changes, caller denied và các đường vào thật.

## 17. Kết luận

**Một kiểm tra quyền có giá trị khi nó bảo vệ đúng hành động nghiệp vụ và mọi đường có thể kích hoạt hành động đó.** AOP hữu ích để biểu diễn và áp dụng chính sách tại các ranh giới thao tác có ý nghĩa, nhưng interceptor không thay thế việc lấy principal đáng tin, xác minh resource/tenant thật, xử lý điều kiện trạng thái ngay khi ghi và bảo vệ các đường gọi có thể bypass. Khi kết hợp **business action boundary + policy quyết định rõ + enforcement sát side effect + kiểm thử phủ đường vào**, hệ thống mới có thể giữ đúng quyền kể cả khi kiến trúc có nhiều lớp và nhiều luồng thực thi.
