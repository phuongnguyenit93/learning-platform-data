# Phân biệt kiểm tra quyền tổng quát và quyền trên từng đối tượng bằng AOP

## 1. Một người được dùng chức năng chưa chắc được thao tác trên mọi dữ liệu

Trong kiểm soát truy cập, một người dùng có thể có quyền **đọc tài liệu**, nhưng không được phép đọc **mọi tài liệu** của hệ thống. Có hai lớp quyết định khác nhau:

- **Kiểm tra quyền tổng quát** (*action-level authorization*): chủ thể có quyền thực hiện **loại hành động** này không? Chẳng hạn Alice có quyền DOCUMENT_READ để sử dụng chức năng đọc tài liệu.
- **Kiểm tra quyền trên từng đối tượng** (*object/resource-level authorization*): chủ thể có quyền thực hiện **hành động ấy trên tài nguyên cụ thể** không? Chẳng hạn Alice được đọc tài liệu mình sở hữu hoặc tài liệu được chia sẻ trong tenant hiện tại, nhưng không được đọc tài liệu riêng tư của Bob.

Aspect-Oriented Programming (AOP) cho phép thực hiện các kiểm tra xuyên suốt tại những ranh giới đã chọn bằng advice. Tuy nhiên, chỉ nhìn vào tên phương thức hoặc sự hiện diện của quyền DOCUMENT_READ **không đủ để kết luận** người dùng được đọc tài liệu có ID bất kỳ.

Ví dụ: Alice có quyền sử dụng chức năng xem đơn hàng, rồi thay ID đơn hàng của mình thành ID đơn của Bob. Nếu hệ thống chỉ kiểm tra ORDER_READ rồi trả dữ liệu dựa trên ID, Alice có thể đọc thông tin không thuộc quyền của mình. Đây là lỗi *Broken Object Level Authorization* (BOLA), thường thể hiện dưới dạng *Insecure Direct Object Reference* (IDOR).

Bài học này giải thích hai lớp quyết định, cách gắn với AOP, cách xác định tài nguyên thật, vai trò của kiểm tra tại tầng dữ liệu, và những trường hợp dễ tạo đường vượt quyền.

## 2. Quyền tổng quát và quyền trên tài nguyên khác nhau thế nào?

### 2.1. Kiểm tra quyền tổng quát

Một chính sách tổng quát có thể yêu cầu:

- DOCUMENT_READ: quyền gọi thao tác đọc tài liệu.
- DOCUMENT_EDIT: quyền dùng tính năng chỉnh sửa tài liệu.
- INVOICE_APPROVE: quyền dùng chức năng duyệt hóa đơn.
- REPORT_EXPORT: quyền yêu cầu xuất báo cáo.

Quyết định ở cấp này dựa trên danh tính đã xác thực và các permission, capability hoặc thuộc tính chủ thể đáng tin. Nếu người dùng không có DOCUMENT_READ, một advice có thể từ chối trước khi truy xuất tài liệu.

Quyền tổng quát **không đồng nghĩa hoàn toàn với role-based access control (RBAC)**. Role có thể cung cấp các permission, nhưng hệ thống cũng có thể cấp permission trực tiếp, giới hạn theo scope hoặc điều kiện khác. Tương tự, user có role ADMIN không mặc định có quyền với mọi tenant hay mọi trạng thái tài nguyên; phạm vi admin phải được định nghĩa rõ.

### 2.2. Kiểm tra quyền trên từng đối tượng

Một quyết định object-level thông thường xét:

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Subject | Alice trong tenant T1 | Ai yêu cầu |
| Action | READ, EDIT hoặc DELETE | Định làm gì |
| Resource | Tài liệu D-103 của Bob | Đối tượng thực bị tác động |
| Resource attributes | Owner, tenant, trạng thái, mức chia sẻ | Tính chất thực của đối tượng |
| Context | Thời điểm, nhóm, mục đích hoặc điều kiện khác | Điều kiện áp dụng chính sách |
| Decision | ALLOW hoặc DENY | Kết quả kiểm tra |

Các mô hình thường dùng là attribute-based access control (ABAC), relationship-based access control (ReBAC), access control list (ACL), ownership hoặc sự kết hợp giữa chúng. Kiểm tra object-level **không thay thế** kiểm tra quyền tổng quát; cả hai cùng đóng góp vào quyết định cuối.

Ví dụ chính sách của hệ thống tài liệu giả định:

> Chỉ chủ thể có DOCUMENT_READ mới được dùng chức năng đọc. Tài liệu phải thuộc cùng tenant; trong tenant ấy, chủ sở hữu hoặc người được phép xem tài liệu chia sẻ mới được nhận nội dung.

Bảng kết quả:

| DOCUMENT_READ | Tenant khớp | Có quan hệ được phép | Kết quả |
| --- | --- | --- | --- |
| Không | Có | Có | DENY vì thiếu quyền tổng quát |
| Có | Không | Có hoặc không | DENY vì khác tenant |
| Có | Có | Không | DENY ở đối tượng |
| Có | Có | Có | ALLOW |
| Có | Có | Tài nguyên không tồn tại | Không được cấp quyền |

Quy tắc này chỉ là ví dụ; ứng dụng thực cần xác định phạm vi quyền, các trường hợp ngoại lệ và mốc hiệu lực của chính sách theo domain.

## 3. Xác thực và nguồn dữ liệu đáng tin

**Authentication** xác định người đang thực hiện yêu cầu; **authorization** quyết định người đó được phép làm gì.

Một security context đáng tin thường chứa principal/user ID, tenant hiện tại và tập permission đã được xác minh. Không được sử dụng giá trị client tự gửi như tenantId, ownerId hoặc role để chứng minh quyền. Người dùng có thể thay những tham số ấy bằng chính công cụ gửi yêu cầu.

Đối tượng cần được xác định từ nguồn dữ liệu đáng tin. Ví dụ, nếu client gửi documentId=d3 và ownerId=alice, nhưng bản ghi d3 thực sự thuộc Bob, ứng dụng phải quyết định dựa trên owner của **bản ghi d3**, không dựa trên ownerId do client khai.

Các thuộc tính quan trọng ở cấp đối tượng có thể gồm tenant, owner, nhóm được chia sẻ, trạng thái tài liệu, đơn vị quản lý, mức độ bảo mật, assignment hoặc quyền được cấp riêng. Một permission tổng quát không tự mang theo những thuộc tính này.

Quyết định truy cập nên có cấu trúc rõ:

~~~text
authorize(subject, action, resource, context) -> ALLOW | DENY
~~~

Nếu không xác định được subject, resource hoặc policy, mặc định **DENY** theo nguyên tắc *fail closed*. Lỗi đọc quyền hoặc thiếu dữ liệu không được tự chuyển thành ALLOW.

## 4. AOP xử lý phần nào của kiểm soát truy cập?

### 4.1. Các khái niệm cần biết

- **Join point:** vị trí can thiệp, chẳng hạn khi một phương thức được gọi/thực thi.
- **Pointcut:** tiêu chí chọn những join point cần bảo vệ.
- **Advice:** logic kiểm tra quyền chạy trước hoặc quanh join point.
- **Aspect:** tập hợp pointcut và advice mang cùng trách nhiệm.
- **Weaving/interception:** cơ chế kết nối aspect với mã ứng dụng; những lời gọi nằm ngoài cơ chế này sẽ không được advice quan sát.

Một *around advice* cho quyền tổng quát có thể kiểm tra permission trước khi gọi phương thức gốc. Nếu DENY, nó từ chối và **không gọi proceed()**. Nếu ALLOW, nó chuyển điều khiển tới phương thức gốc theo đúng hợp đồng.

Việc kiểm tra object-level đôi khi cũng có thể được đóng gói trong advice, nhưng advice phải có đủ thông tin về **tài nguyên thực**, không chỉ resource ID hoặc tên phương thức.

### 4.2. Luồng hai lớp kiểm tra

~~~text
Người gọi yêu cầu đọc D-103
       |
       v
Xác thực danh tính và lấy security context đáng tin
       |
       v
AOP: kiểm tra quyền tổng quát DOCUMENT_READ
       |
       +--- DENY ---> không gọi phương thức đích
       |
       v
Tải đúng tài nguyên D-103 trong phạm vi tin cậy
       |
       +--- không tồn tại / không được tiết lộ ---> từ chối
       |
       v
Kiểm tra tenant, owner, ACL, trạng thái và điều kiện khác
       |
       +--- DENY ---> không tiết lộ nội dung
       |
       v
Sử dụng hoặc trả kết quả đúng phạm vi được phép
~~~

Một cách tổ chức hiệu quả là dùng AOP ở ranh giới chức năng để kiểm tra permission tổng quát, còn việc kiểm tra object-level được thực hiện nơi đã tải được đối tượng thật và có thể bảo đảm điều kiện cập nhật. Nếu áp dụng tất cả thông qua aspect, policy service của advice vẫn phải lấy dữ liệu chính xác và giải quyết nguy cơ thay đổi trạng thái sau lúc kiểm tra.

Chức năng READ, EDIT, APPROVE, DELETE không nhất thiết dùng chung điều kiện object-level. Cùng một tài liệu, người dùng có thể được xem nhưng không được sửa; với invoice, chỉ được duyệt khi được phân công và tài liệu còn trạng thái PENDING.

## 5. Ví dụ Java 17 chạy độc lập bằng dynamic proxy

Chương trình minh họa cơ chế can thiệp của AOP nói chung bằng **Java dynamic proxy**. Proxy đọc một annotation do chính ví dụ định nghĩa rồi kiểm tra DOCUMENT_READ trước khi gọi service. Service sau đó tải bản ghi thật, kiểm tra tenant và điều kiện owner/visibility. Không cần thư viện AOP bên ngoài để chạy ví dụ.

Giả định dữ liệu:

- d1 là tài liệu riêng của Alice thuộc T1.
- d2 là tài liệu được chia sẻ trong T1 nhưng của Bob.
- d3 là tài liệu riêng của Bob trong T1.
- d4 được chia sẻ trong T2, không được phép đọc từ T1.

Tạo tệp **AuthorizationAopDemo.java**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.Objects;
import java.util.Set;

public class AuthorizationAopDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface RequiresPermission {
        String value();
    }

    record UserContext(String username, String tenant, Set<String> permissions) {
        UserContext {
            Objects.requireNonNull(username);
            Objects.requireNonNull(tenant);
            permissions = Set.copyOf(permissions);
        }
    }

    record Document(
            String id,
            String tenant,
            String owner,
            boolean publicWithinTenant,
            String body) {}

    interface DocumentApi {
        @RequiresPermission("DOCUMENT_READ")
        String read(UserContext user, String documentId);
    }

    static final class DocumentService implements DocumentApi {
        private final Map<String, Document> store = Map.of(
                "d1", new Document("d1", "T1", "alice", false, "Alice draft"),
                "d2", new Document("d2", "T1", "bob", true, "Team guide"),
                "d3", new Document("d3", "T1", "bob", false, "Bob private"),
                "d4", new Document("d4", "T2", "carol", true, "Other tenant")
        );

        @Override
        public String read(UserContext user, String documentId) {
            Document document = store.get(documentId);
            if (document == null || !document.tenant().equals(user.tenant())) {
                throw new NoSuchElementException("document unavailable");
            }
            boolean owner = document.owner().equals(user.username());
            if (!owner && !document.publicWithinTenant()) {
                throw new SecurityException("object denied");
            }
            return document.body();
        }
    }

    static DocumentApi withGeneralAuthorization(DocumentApi target) {
        InvocationHandler handler = (Object proxy, Method method, Object[] args) -> {
            RequiresPermission policy =
                    method.getAnnotation(RequiresPermission.class);
            if (policy != null) {
                UserContext user = (UserContext) args[0];
                if (user == null || !user.permissions().contains(policy.value())) {
                    throw new SecurityException("general denied");
                }
            }

            try {
                return method.invoke(target, args);
            } catch (InvocationTargetException ex) {
                throw ex.getCause();
            }
        };

        return (DocumentApi) Proxy.newProxyInstance(
                DocumentApi.class.getClassLoader(),
                new Class<?>[] { DocumentApi.class },
                handler
        );
    }

    static void attempt(
            String label, DocumentApi api, UserContext user, String id) {
        try {
            System.out.println(label + "=" + api.read(user, id));
        } catch (SecurityException | NoSuchElementException ex) {
            System.out.println(label + "=" + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        DocumentApi api = withGeneralAuthorization(new DocumentService());
        UserContext alice = new UserContext(
                "alice", "T1", Set.of("DOCUMENT_READ"));
        UserContext noPermission = new UserContext(
                "alice", "T1", Set.of());

        attempt("own", api, alice, "d1");
        attempt("shared", api, alice, "d2");
        attempt("private-of-other", api, alice, "d3");
        attempt("other-tenant", api, alice, "d4");
        attempt("no-general-permission", api, noPermission, "d1");
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac --release 17 AuthorizationAopDemo.java
java AuthorizationAopDemo
~~~

**Stdout theo thứ tự xác định:**

~~~text
own=Alice draft
shared=Team guide
private-of-other=object denied
other-tenant=document unavailable
no-general-permission=general denied
~~~

Đọc kết quả:

1. Alice có quyền tổng quát, là chủ của d1 và cùng tenant: ALLOW.
2. d2 không phải của Alice nhưng được chia sẻ trong tenant T1: ALLOW.
3. d3 của Bob và riêng tư: **có quyền tổng quát nhưng thiếu quyền trên đối tượng**, DENY.
4. d4 được chia sẻ ở T2 nhưng Alice ở T1: DENY vì khác tenant.
5. Alice sở hữu d1 nhưng không có DOCUMENT_READ: **thiếu quyền tổng quát**, DENY.

Proxy kiểm tra annotation trên phương thức của interface. Đây là ví dụ một cơ chế interception cụ thể; nó không tự bảo vệ constructor, các phương thức không đi qua proxy, hoặc lời gọi trực tiếp đến DocumentService. Ở hệ thống thật, cần đảm bảo mọi đường vào đáng tin đều được bảo vệ, và chính sách object-level vẫn hiện diện tại ranh giới truy cập tài nguyên.

**Giới hạn của ví dụ:** UserContext được truyền trực tiếp để người học dễ tái lập tình huống. Trong hệ thống thực, context phải đến từ thành phần xác thực đáng tin chứ không phải nội dung do người gọi tự quyết định. Map trong bộ nhớ không có transaction, persistence hoặc cập nhật quyền đồng thời.

## 6. Vì sao chỉ kiểm tra quyền tổng quát vẫn có thể lộ dữ liệu?

### 6.1. IDOR và thay ID

Giả sử người dùng có quyền đọc tài liệu rồi gửi hai yêu cầu:

~~~text
GET /documents/d1
GET /documents/d3
~~~

Nếu cả hai chỉ kiểm tra DOCUMENT_READ, hệ thống có thể trả d3 của người khác. ID có dạng UUID ngẫu nhiên cũng không thay thế authorization: người dùng có thể biết ID thông qua liên kết, log hoặc một nguồn dữ liệu khác. **Khó đoán ID khác với có quyền truy cập ID đó.**

### 6.2. Tin vào thuộc tính tự khai

Một yêu cầu chứa documentId=d3 và ownerId=alice có thể là dữ liệu giả mạo; bản ghi d3 vẫn thuộc Bob. Phải tải hoặc kiểm tra điều kiện truy vấn trên đối tượng đáng tin, rồi quyết định từ thuộc tính thật.

### 6.3. Coi quyền trên đối tượng là một thuộc tính duy nhất

Ownership có thể chưa đủ. Người sở hữu hóa đơn chưa chắc được tự duyệt hóa đơn; người từng được chia sẻ tài liệu có thể đã bị thu hồi quyền; quyền xem trong tenant có thể bị hạn chế bởi trạng thái tài liệu. Policy cần xét đúng action và trạng thái hiện tại, không chỉ owner ID.

### 6.4. Chỉ bảo vệ nút bấm trên giao diện

Ẩn nút EDIT, vô hiệu hóa liên kết hoặc lọc menu ở phía client giúp trải nghiệm người dùng nhưng không thay thế enforcement. Client có thể gọi trực tiếp endpoint hoặc đường nội bộ khác. Quyết định cuối phải diễn ra ở ranh giới phía hệ thống đáng tin.

## 7. Chọn nơi kiểm tra object-level

### 7.1. Advice tải resource trước khi proceed()

Một advice có thể đọc resource ID từ tham số, gọi policy service để nạp resource và kiểm tra quyền rồi cho phép proceed(). Điều này chỉ đúng khi có cách đảm bảo quyết định còn hiệu lực khi phương thức thực sự sử dụng đối tượng.

Vấn đề là resource có thể bị chuyển chủ, khóa hoặc thu hồi chia sẻ **sau khi advice kiểm tra** nhưng **trước khi service cập nhật**. Đây là nguy cơ *time-of-check to time-of-use* (TOCTOU).

### 7.2. Service kiểm tra ngay trên resource được sử dụng

Mẫu trong ví dụ đặt object-level check trong service sau khi tải tài liệu. Với thao tác ghi, cần phối hợp kiểm tra với transaction, phiên bản bản ghi hoặc câu lệnh cập nhật có điều kiện để tránh race. Một policy service riêng có thể giúp dùng chung quy tắc giữa nhiều use case mà không sao chép các điều kiện tenant/owner.

### 7.3. Ràng buộc ngay trong truy vấn hoặc tầng dữ liệu

Thay vì tải một resource bất kỳ rồi lọc, hệ thống có thể truy vấn trong tenant và phạm vi được phép; hoặc sử dụng chính sách ở tầng lưu trữ khi phù hợp. Điều này đặc biệt hữu ích với truy vấn danh sách, pagination và cập nhật có điều kiện. Tuy nhiên, chính sách ở tầng dữ liệu không mặc nhiên thay thế mọi quy tắc nghiệp vụ cần nhiều nguồn thông tin.

**Nguyên tắc:** điều kiện quyền phải được đánh giá trên dữ liệu có thẩm quyền, và quyết định phải còn hợp lệ tại thời điểm resource được sử dụng.

## 8. Quyền trên từng phần tử trong danh sách và batch

Một điểm dễ bỏ sót là list/export/search. Nếu người dùng có REPORT_EXPORT, điều đó mới cho phép gọi tính năng, không có nghĩa toàn bộ bản ghi trong báo cáo đều thuộc phạm vi được xem.

Cần kiểm tra hoặc ràng buộc **từng tài nguyên trong tập kết quả**. Ưu tiên lọc tại nguồn theo policy để số lượng, phân trang, thống kê và tổng hợp cũng đúng phạm vi. Trả tổng số bản ghi bị cấm, dù không trả nội dung, vẫn có thể lộ thông tin.

Với bulk edit/delete có nhiều resource ID, chính sách cần quyết định xử lý toàn bộ cùng thành công hay cho phép thành công một phần, và kiểm tra từng resource. Một lần kiểm tra quyền tổng quát trước vòng lặp không đủ.

Các luồng xử lý kéo dài như export nền, đăng ký stream hoặc tác vụ bất đồng bộ cũng cần xác định **lúc nào quyền được đánh giá và có cần kiểm tra lại không**. Việc được phép gửi một tác vụ không tự đảm bảo quyền vẫn còn hợp lệ tại thời điểm worker thực thi.

## 9. Tương tác với các aspect khác

AOP thường có nhiều aspect cùng áp dụng: authorization, cache, retry, tracing, transaction và xử lý lỗi. Thứ tự của chúng có thể thay đổi kết quả bảo mật:

- **Cache:** nếu cache trả dữ liệu trước khi kiểm tra object-level, người dùng có thể nhận dữ liệu không được phép. Khóa cache có thể cần scope/tenant/phạm vi quyền và chính sách invalidation khi quyền thay đổi; không coi cache là nguồn phân quyền.
- **Transaction:** nếu kiểm tra quyền trước một transaction nhưng thay đổi resource trong transaction sau, state có thể thay đổi giữa hai mốc. Thiết kế cần bảo đảm đúng mức nhất quán.
- **Retry:** mỗi lần cố gắng xử lý có thể chịu điều kiện quyền mới; không giả định quyền được đánh giá một lần mãi mãi.
- **Async:** permission tại bước gửi không tự chứng minh worker được phép đọc hay sửa đối tượng ở thời điểm khác.
- **Tracing/logging:** chỉ ghi dữ liệu cần thiết cho audit và chẩn đoán; tránh log nội dung resource, token hoặc thông tin quyền nhạy cảm.

Nếu cơ chế proxy không can thiệp self-invocation hoặc lời gọi trực tiếp đến đối tượng gốc, một phương thức được bảo vệ bằng advice có thể bị gọi qua đường khác. Vì vậy, cần kiểm thử chính các đường thực thi được dùng khi triển khai, bảo đảm ranh giới tin cậy không thể bị vượt qua.

## 10. Fail closed, lỗi và ghi nhận truy cập

Khi thiếu subject đáng tin, policy chưa xác định, resource không tải được hoặc authorization service thất bại, mặc định DENY theo hợp đồng bảo mật. Không nuốt lỗi kiểm tra quyền rồi cho phép truy cập.

Có thể tách phản hồi thành không xác thực, thiếu quyền thao tác, thiếu quyền trên resource, và resource không tồn tại. Đôi khi trả “không tìm thấy” cho tài nguyên ở tenant khác để tránh tiết lộ sự tồn tại, như ví dụ Java; đây là một lựa chọn của API contract, không thay thế kiểm tra quyền và audit.

Audit nên ghi loại hành động, định danh chủ thể đã kiểm chứng, quyết định ALLOW/DENY, lý do được phép công khai và thông tin tương quan ở mức cần thiết. Không ghi token hoặc toàn bộ nội dung dữ liệu nhạy cảm. Việc ghi audit bắt buộc theo pháp lý/nghiệp vụ có thể có hợp đồng độ bền riêng, cần phân biệt với log chẩn đoán best-effort.

## 11. Kiểm thử hai cấp quyền

| Trường hợp | Kỳ vọng |
| --- | --- |
| Thiếu quyền tổng quát dù là owner | DENY trước thao tác |
| Có quyền tổng quát và là owner trong tenant | ALLOW nếu các điều kiện khác hợp lệ |
| Có quyền tổng quát nhưng object thuộc người khác, riêng tư | DENY |
| Object được chia sẻ hợp lệ trong cùng tenant | ALLOW theo policy |
| Object ở tenant khác, dù đánh dấu công khai trong tenant đó | DENY |
| Client sửa ownerId hoặc tenantId trong request | Không vượt được quyền từ dữ liệu thật |
| Resource không tồn tại | Không trả dữ liệu, phản hồi đúng contract |
| Cùng role nhưng khác trạng thái tài liệu | Quyết định theo trạng thái và action |
| Quyền bị thu hồi trước khi ghi | Không được cập nhật trái phép |
| Danh sách chứa cả resource được phép và bị cấm | Chỉ trả dữ liệu trong phạm vi |
| Có đường gọi trực tiếp không qua proxy | Không tạo lối vòng qua kiểm tra bắt buộc |
| Cache hit từ một người dùng khác | Không tiết lộ dữ liệu vì thiếu ràng buộc quyền |

Ngoài happy path, nên ưu tiên các phép thử **DENY** để phát hiện BOLA/IDOR. Với thao tác thay đổi dữ liệu, kiểm thử race condition và transaction giúp xác minh quyết định còn hiệu lực tại lúc cập nhật. Khi dùng AOP runtime, cần kiểm tra pointcut, thứ tự advice và khả năng interception theo đường gọi thực tế.

## 12. Sai lầm thường gặp và hướng sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Có role VIEWER thì đọc được mọi tài liệu | Lộ object không thuộc phạm vi | Kết hợp permission và object policy |
| So sánh ownerId do client gửi | Người dùng có thể giả mạo | Dùng thuộc tính từ resource đáng tin |
| Chỉ kiểm tra ở UI | Direct request vượt qua kiểm tra | Enforce tại server/resource boundary |
| Tin ID khó đoán là đủ an toàn | ID bị lộ vẫn bị dùng để xem dữ liệu | Kiểm tra từng resource |
| Kiểm tra quyền trước rồi cập nhật khi state đã đổi | TOCTOU | Kiểm tra và cập nhật nhất quán trong transaction/version |
| Coi mọi admin được vượt tenant | Vượt phạm vi quản trị | Định nghĩa rõ tenant scope và ngoại lệ |
| Chỉ kiểm tra một lần cho cả danh sách | Lẫn bản ghi trái phép | Filter/check từng resource |
| Cache trả nội dung trước policy | Bypass object authorization | Thiết kế thứ tự advice và phân vùng cache đúng |
| Nuốt lỗi authorization và tiếp tục | Biến DENY thành ALLOW | Fail closed |
| Coi annotation là tự bảo vệ mọi đường gọi | Self-call/direct call có thể bypass | Kiểm thử phạm vi weaving/interception |

## 13. Checklist khi thiết kế aspect kiểm soát truy cập

1. Xác định subject, action, resource và ngữ cảnh đáng tin cho từng operation.
2. Phân biệt permission tổng quát với policy xét resource cụ thể.
3. Lấy tenant/owner/state từ dữ liệu có thẩm quyền; không tin trường client tự khai.
4. Đặt điểm enforcement ở nơi thực sự có thể chặn mọi đường chạm tới dữ liệu.
5. Bảo đảm policy object-level được đánh giá trên resource đang được sử dụng, với mức nhất quán phù hợp.
6. Quy định DENY/NOT_FOUND, mức độ tiết lộ và audit.
7. Kiểm soát thứ tự authorization với cache, retry, transaction và async.
8. Bảo vệ truy vấn danh sách, export và bulk theo từng resource.
9. Viết kiểm thử quyền bị từ chối, IDOR, cross-tenant, race và bypass proxy.
10. Xem lại chính sách mỗi khi thêm một loại action, thay đổi model chia sẻ hoặc mở rộng ranh giới dữ liệu.

**Điểm cốt lõi:** kiểm tra quyền tổng quát trả lời **“người này có được dùng loại thao tác này?”**; kiểm tra quyền trên từng đối tượng trả lời **“người này có được dùng thao tác đó trên tài nguyên cụ thể trong trạng thái hiện tại?”**. AOP giúp tổ chức enforcement xuyên suốt, còn quyết định an toàn phải dựa trên ngữ cảnh danh tính đáng tin và dữ liệu thực của resource.
