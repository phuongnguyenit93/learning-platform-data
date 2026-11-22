# @PostAuthorize và quyết định dựa trên returnObject trong Spring Security

> **Chủ đề:** Spring Security — **Kiểm tra sau phương thức**. Bài học trình bày cách `@PostAuthorize` kiểm soát **kết quả mà một Spring-managed method sắp trả về**, vai trò của biến SpEL `returnObject`, quan hệ với `@PreAuthorize`, xử lý quyền sở hữu (owner), lỗi null/404, rủi ro side effect, cách kiểm thử và giới hạn khi dùng cho API thực tế. Ví dụ sử dụng **Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x** theo Spring MVC/Servlet.

## 1. Câu hỏi cốt lõi: đã đọc được object, có được trả cho người gọi?

Giả sử một method trả về tài liệu:

~~~java
public Document readDocument(String id) {
    return repository.findById(id);
}
~~~

Hai người có thể cùng đăng nhập và cùng được phép gọi chức năng “đọc tài liệu”, nhưng **không** có nghĩa người A được nhận dữ liệu thuộc người B.

Ví dụ:

| Người gọi | Tài liệu | Chủ sở hữu | Quyết định trả kết quả |
| --- | --- | --- | --- |
| Alice | A-1 | Alice | ALLOW |
| Alice | B-1 | Bob | DENY |
| Bob | B-1 | Bob | ALLOW |
| Bob | A-1 | Alice | DENY |

Nếu chỉ dùng `@PreAuthorize("isAuthenticated()")` hoặc HTTP `authenticated()`, ta chưa bảo đảm quy tắc chủ sở hữu. Một cách diễn đạt ở method security là:

~~~java
@PostAuthorize("returnObject.owner == authentication.name")
public Document readDocument(String id) {
    return repository.load(id);
}
~~~

Đây là **fragment Spring**, không tự chạy độc lập; cần `Document` có thuộc tính `owner`, một `repository` thật và cấu hình method security.

**Ý nghĩa:** method được gọi để tạo/tải một `Document`; sau đó Spring Security đánh giá biểu thức SpEL. Nếu `Document.owner` trùng danh tính người gọi, kết quả **được trả ra**. Nếu không trùng, Spring Security **từ chối trả kết quả** và thông thường ném `AccessDeniedException` (hay một ngoại lệ dẫn xuất phù hợp như `AuthorizationDeniedException`).

**Điểm phải nhớ:** `@PostAuthorize` là **hậu kiểm**. Nó không ngăn việc target method đã thực thi; nó ngăn việc **trả kết quả** nếu policy không thỏa.

## 2. Kích hoạt `@PostAuthorize` bằng `@EnableMethodSecurity`

`@PostAuthorize` thuộc nhóm **pre/post method security**. Nhóm này được bật mặc định khi có:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Có thể đặt `@EnableMethodSecurity` trên main class `@SpringBootApplication` thay cho cấu hình riêng. Spring Boot Starter Security **không tự bật method-level authorization** nếu chưa có cấu hình tương ứng.

### 2.1. Những annotation nào được bật?

| Annotation | Điểm xử lý | Mặc định trong `@EnableMethodSecurity` |
| --- | --- | --- |
| `@PreAuthorize` | Trước khi target method chạy | Bật |
| `@PostAuthorize` | Sau khi target trả kết quả | Bật |
| `@PreFilter` | Lọc collection input | Bật |
| `@PostFilter` | Lọc collection output | Bật |
| `@Secured` | Kiểm role/authority trước method | Cần `securedEnabled = true` |
| `@RolesAllowed` | Kiểm JSR-250 role | Cần `jsr250Enabled = true` |

`@EnableMethodSecurity(prePostEnabled = false)` sẽ tắt cả `@PostAuthorize` trong nhóm mặc định. Đừng đặt cờ này chỉ vì muốn “bỏ bớt một annotation không dùng”; nó có thể làm các chính sách đã viết **không còn được kiểm tra**.

### 2.2. Import và vị trí annotation

~~~java
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    @PreAuthorize("hasAuthority('document:read')")
    @PostAuthorize("returnObject.owner == authentication.name")
    public Document read(String id) {
        // ...
        return null;
    }
}
~~~

Đây là **fragment chỉ minh họa annotation** (không phải implementation dùng được: phương thức trả null). Ứng dụng đầy đủ ở phần 9 dùng dữ liệu thực trong memory, không trả null và có test.

Nên đặt bảo vệ ở **service layer** để cùng policy được áp dụng khi service bị gọi từ nhiều controller hoặc bean khác. Controller vẫn có thể có guard riêng, nhưng không nên coi nó là ranh giới duy nhất.

## 3. Vòng đời của một lời gọi có `@PostAuthorize`

Khi Spring AOP proxy nhận lời gọi:

~~~text
HTTP request
    |
    v
SecurityFilterChain
    |-- authentication / HTTP authorization
    |-- DENY -> 401 hoặc 403 tùy ngữ cảnh
    v
Controller
    |
    v
Spring proxy của DocumentService
    |
    +-- @PreAuthorize (nếu có)
    |       |-- DENY -> KHÔNG chạy target method
    |       v ALLOW
    +-- target method thực thi
    |       +-- đọc dữ liệu, có thể phát sinh side effect
    |       +-- trả Document
    v
@PostAuthorize
    |-- SpEL đọc returnObject + Authentication
    |-- DENY -> AccessDeniedException (không trả Document)
    v ALLOW
Controller / serializer -> HTTP response
~~~

Sơ đồ nhấn mạnh **thời điểm kiểm**; còn filter chain/interceptor thực tế có thể chứa nhiều thành phần khác.

Spring Security 6.5 dùng `AuthorizationManagerAfterMethodInterceptor` cho `@PostAuthorize` và `PostAuthorizeAuthorizationManager` để đánh giá biểu thức. `returnObject` đại diện cho **đối tượng mà target method đã trả**, không phải request body, không phải tham số đầu vào và cũng không phải JSON sau khi serialize.

**Chỉ ra điểm quan trọng từ sơ đồ:** với Alice đọc B-1, target method **đã lấy được B-1 vào JVM**, nhưng hậu kiểm từ chối việc trả object ấy qua lời gọi có proxy. Đây là cơ chế chống rò rỉ ở boundary, nhưng không chứng minh rằng method không gây tác động nào trước đó.

## 4. `returnObject` là gì trong SpEL?

### 4.1. So sánh với principal đang xác thực

~~~java
@PostAuthorize("returnObject.owner == authentication.name")
public Document find(String id) {
    return repository.load(id);
}
~~~

SpEL đọc như sau:

1. `returnObject`: đối tượng `Document` vừa được method trả.
2. `returnObject.owner`: property `owner` được Spring Expression Language truy xuất (ví dụ getter `getOwner()`).
3. `authentication`: `Authentication` hiện tại từ `SecurityContext`.
4. `authentication.name`: tên người dùng đã được xác thực, không phụ thuộc giá trị username do client tự điền trong URL.
5. `==`: so sánh hai giá trị theo ngữ nghĩa SpEL, quyết định ALLOW/DENY.

Với POJO:

~~~java
public class Document {
    private final String id;
    private final String owner;

    public Document(String id, String owner) {
        this.id = id;
        this.owner = owner;
    }

    public String getId() { return id; }
    public String getOwner() { return owner; }
}
~~~

Đây là một **lớp POJO chạy độc lập**, nhưng đoạn annotation trước đó cần Spring. Getter `getOwner()` giúp SpEL/Jackson nhận diện property `owner`. Tránh dựa vào tên field private nếu không kiểm chứng cơ chế truy cập property trong cấu hình thực.

### 4.2. Kiểm owner hoặc cho người có quyền audit

Một policy nghiệp vụ có thể cho phép chủ sở hữu đọc tài liệu và cho auditor được đọc phục vụ kiểm toán:

~~~java
@PostAuthorize(
    "returnObject.owner == authentication.name or hasAuthority('document:audit')"
)
public Document read(String id) {
    return repository.load(id);
}
~~~

**Giải thích:** một user đã được xác thực có thể nhận kết quả khi là owner **hoặc** có authority literal `document:audit`. Không cần giả định `ROLE_ADMIN` tự có mọi quyền. Quyền audit là một ngoại lệ chính sách **được cấp tường minh**, phải có lý do nghiệp vụ và log/audit phù hợp.

Khi biểu thức bắt đầu truy cập property của `returnObject`, cần quan tâm giá trị null, kiểu trả về và trường owner có đáng tin cậy hay không.

### 4.3. Kết hợp với `@PreAuthorize`

~~~java
@PreAuthorize("hasAuthority('document:read')")
@PostAuthorize(
    "returnObject.owner == authentication.name or hasAuthority('document:audit')"
)
public Document read(String id) {
    return repository.load(id);
}
~~~

Hai annotation tạo **hai bước kiểm độc lập**:

- **Bước trước:** thiếu `document:read` → không được chạy method.
- **Bước sau:** dù có `document:read`, chỉ được nhận kết quả nếu là owner hoặc có `document:audit`.

Không có nghĩa là `@PostAuthorize` có thể “cấp lại quyền” cho user đã bị `@PreAuthorize` từ chối. Một lần DENY ở pre-check sẽ dừng trước khi có `returnObject` để xét.

### 4.4. Kiểm thêm thuộc tính của giá trị trả về

~~~java
@PostAuthorize(
    "returnObject.owner == authentication.name and returnObject.status == 'ACTIVE'"
)
public Document readActive(String id) {
    return repository.load(id);
}
~~~

Đây là **fragment** yêu cầu `Document` có property `status` và repository thực. Điều kiện ở đây bảo đảm chỉ owner nhận document ở trạng thái ACTIVE. Không tự hiểu rằng biểu thức này kiểm luôn tenant hoặc mọi rule quản trị khác.

## 5. Giá trị null, Optional và exception: đừng viết SpEL dễ lỗi

### 5.1. Khi method có thể trả null

Biểu thức:

~~~java
@PostAuthorize("returnObject.owner == authentication.name")
~~~

không an toàn nếu method đôi khi trả `null`: việc truy xuất `owner` có thể gây lỗi đánh giá biểu thức. Nên quyết định rõ ý nghĩa của “không tìm thấy”:

- Nếu không tìm thấy là một lỗi nghiệp vụ, **ném exception phù hợp** trong target method (ví dụ HTTP 404 trong lớp web/service demo) thay vì trả null.
- Nếu bắt buộc trả null, biểu thức cần explicit null guard, nhưng phải thống nhất liệu **null được ALLOW hay DENY**.
- Nếu yêu cầu không tiết lộ tài nguyên có tồn tại hay không, cần policy 403/404 và lookup bảo vệ phù hợp, không đơn giản chỉ ném 404 dựa trên ID.

Ví dụ **không cho null**:

~~~java
@PostAuthorize(
    "returnObject != null and returnObject.owner == authentication.name"
)
public Document nullableRead(String id) {
    return repository.findOrNull(id);
}
~~~

Đây là fragment; không dùng nếu contract của controller mong null được biểu diễn là 404. `and` giúp bỏ qua truy cập `owner` khi `returnObject` null, và quyết định DENY cho null.

Ví dụ **chấp nhận null vì không có dữ liệu**:

~~~java
@PostAuthorize(
    "returnObject == null or returnObject.owner == authentication.name"
)
public Document optionalLikeRead(String id) {
    return repository.findOrNull(id);
}
~~~

Đây cũng là fragment. Việc ALLOW null **không** đồng nghĩa truy cập dữ liệu được phép; nó chỉ cho phép kết quả vắng mặt. Nhưng hành vi 404/204 khi nhận null cần do tầng API thiết kế và được kiểm thử.

### 5.2. `Optional<Document>` không phải `Document`

Nếu method trả `Optional<Document>`, `returnObject` thường là **Optional wrapper**, không phải object được chứa bên trong. Vì vậy:

~~~java
// KHÔNG đúng nếu method trả Optional<Document>:
@PostAuthorize("returnObject.owner == authentication.name")
~~~

không phải cách kiểm owner của `Document` nằm trong Optional. Cần thiết kế biểu thức/bean policy có kiểm `isPresent`, xử lý `empty`, hoặc chuyển sang contract “không thấy thì ném exception” và trả `Document` trực tiếp. Ví dụ dùng một policy bean rõ ràng:

~~~java
// Fragment: bean documentPolicy phải do ứng dụng tự implement.
@PostAuthorize("@documentPolicy.mayReceive(authentication, returnObject)")
public Optional<Document> findOptional(String id) {
    return repository.findOptional(id);
}
~~~

Đây là **fragment**, không phải API có sẵn tên `documentPolicy`. Bean cần nhận đúng kiểu `Optional<Document>`, kiểm tra `isPresent()` trước `get()`, đánh giá owner/tenant và quyết định kết quả empty như đã thống nhất.

### 5.3. Exception khi target method chưa trả bình thường

Nếu method ném exception (như `DocumentNotFoundException` hoặc `ResponseStatusException(404)`) **trước khi trả**, interceptor hậu kiểm thông thường **không có kết quả returnObject bình thường để đánh giá**. Không thể coi `@PostAuthorize` là cơ chế bảo mật mặc định cho mọi nhánh lỗi.

Điều này quan trọng nếu response 403 cho document tồn tại nhưng không thuộc user, còn 404 cho ID không tồn tại; cách phân biệt đó có thể làm lộ sự tồn tại của ID. Cần xác định rõ API nên dùng 403, 404 “ẩn tài nguyên” hay cùng một response có chủ đích, phù hợp threat model và thống nhất trên dữ liệu thật.

## 6. Những giới hạn quan trọng của hậu kiểm

### 6.1. Hậu kiểm không rollback mọi side effect

Giả sử code sau:

~~~java
// KHÔNG dùng làm rào cản duy nhất cho thao tác ghi:
@PostAuthorize("returnObject.owner == authentication.name")
public Document changeOwner(String id, String newOwner) {
    Document document = repository.load(id);
    document.setOwner(newOwner);
    repository.save(document); // DB write có thể đã xảy ra!
    return document;
}
~~~

Đây là **phản ví dụ**. Nếu Spring từ chối sau khi method đã viết DB, ta không thể mặc định side effect đã được rollback. Thứ tự proxy advice của `@Transactional` và `@PostAuthorize` có thể ảnh hưởng transaction timing; thay đổi thứ tự bean/advisor không phải lời giải đơn giản cho mọi external side effects như message, email, payment hoặc cache.

Tài liệu Spring Security **không khuyến nghị `@PostAuthorize` như hàng rào chính ở code ghi database**. Phương pháp đúng hơn là kiểm quyền **trước khi thay đổi** và kết hợp constraint của domain:

~~~java
// Fragment minh họa: cần bean documentPolicy và repository thực.
@PreAuthorize("@documentPolicy.canModify(authentication, #id)")
@Transactional
public void rename(String id, String title) {
    Document document = repository.loadForUpdate(id);
    document.rename(title);
    repository.save(document);
}
~~~

Mục tiêu của fragment là thứ tự **kiểm quyền trước thao tác ghi**, không phải lời hứa an toàn tuyệt đối: cần tránh time-of-check/time-of-use race, kiểm tenant/owner trong transaction phù hợp, và xử lý các trạng thái tài nguyên thay đổi đồng thời. Với hành động tài chính/nhạy cảm, audit và cơ chế idempotency/authorization ở domain vẫn rất quan trọng.

### 6.2. Hậu kiểm cho read cũng không luôn miễn side effect

Một truy vấn có thể ghi access log, tạo cache entry, tăng counter, phát sự kiện hoặc đọc dữ liệu nhạy cảm vào memory. Nếu hậu kiểm DENY, các side effect đó **có thể đã xảy ra**; không nên dựa vào việc response 403 để khẳng định không có gì được chạm tới.

Hậu kiểm hữu ích khi cần xem thuộc tính của object để quyết định cho/không cho **trả kết quả**, nhưng vẫn nên giới hạn truy vấn ban đầu theo tenant/scope khi có thể.

### 6.3. Không thay thế policy theo đối tượng, tenant hay field

`returnObject.owner == authentication.name` chỉ là một điều kiện:

- Không xác định resource thuộc tenant nào.
- Không chứng minh owner vẫn có quyền sau khi bị thu hồi.
- Không chặn rò rỉ từ các log/sự kiện tạo trong method.
- Không cấp quyền theo trường dữ liệu riêng (ví dụ số tài khoản có thể chỉ được xem một phần).
- Không bảo đảm việc phân trang/filter list ở tầng database.

Trong hệ thống lớn, phải kết hợp domain-level checks với truy vấn có scope và kiểm điều kiện ở thời điểm thực hiện thao tác.

## 7. So sánh với các annotation liên quan

| Cơ chế | Đầu vào đối chiếu | Thời điểm | Kết quả khi không đạt |
| --- | --- | --- | --- |
| `@PreAuthorize` | Authentication, tham số method, bean policy | **Trước** target method | Thường DENY toàn lời gọi |
| `@PostAuthorize` | Authentication, **returnObject** sau khi method chạy | **Sau** target method | Thường DENY **toàn kết quả** |
| `@PreFilter` | Các phần tử collection **đầu vào** | Trước target method | Loại phần tử không đạt |
| `@PostFilter` | Các phần tử collection **đầu ra** | Sau target method | Loại phần tử không đạt |
| `@AuthorizeReturnObject` | Proxy trên object trả về/nested methods | Khi object hoặc getter được sử dụng | Có thể bảo vệ từng thành phần theo annotations |

### 7.1. `@PostAuthorize` khác `@PostFilter` như thế nào?

~~~java
@PostAuthorize("returnObject.owner == authentication.name")
public Document getOne(String id) { /* trả một Document */ }

@PostFilter("filterObject.owner == authentication.name")
public List<Document> getSome() { /* trả collection */ }
~~~

Đây là **fragment ý tưởng**, không phải code độc lập. Với `getOne`, nếu object không thuộc caller thì **cả lời gọi bị từ chối**. Với `getSome`, Spring có thể **lọc những phần tử không đạt** khỏi collection trả về, không nhất thiết từ chối toàn bộ lời gọi.

Với nhiều dữ liệu, `@PostFilter` sau khi load chưa thay thế truy vấn `WHERE tenant_id = ... AND ...` ở database. Nếu danh sách phân trang trước rồi mới lọc, số lượng và ranh giới trang còn có thể gây khó hiểu hoặc rò rỉ metadata.

### 7.2. `@AuthorizeReturnObject` là cơ chế khác

Ở Spring Security 6.5, `@AuthorizeReturnObject` có thể yêu cầu proxy một object được trả về, để các method/property trên object đó mang annotation bảo vệ riêng. Khác với `@PostAuthorize`: cái sau quyết định **có trả nguyên kết quả method hay không**, trong khi cơ chế proxy giá trị trả về có thể kiểm **các thao tác lên object được trả**.

Không cần đưa `@AuthorizeReturnObject` vào ví dụ cơ bản nếu chỉ cần trả hoặc từ chối một `Document`. Nếu dùng nó, phải chú ý nested types, serialization, final/value types và AOT hints theo phiên bản đang chạy.

### 7.3. `@HandleAuthorizationDenied` thay đổi hành vi từ chối

Spring Security 6.5 hỗ trợ `@HandleAuthorizationDenied` và `MethodAuthorizationDeniedHandler` để tùy biến cách trả giá trị khi một method authorization bị từ chối, ví dụ trả null hoặc che thông tin có kiểm soát. Đây là **cơ chế mở rộng**, không mặc định được bật cho tất cả `@PostAuthorize`. Trả object đã bị từ chối một cách vô ý là lỗ hổng; cần đặc biệt cẩn thận với masking/partial response.

Trong bài này, ví dụ dùng hành vi DENY mặc định để phân tích 403 rõ ràng.

## 8. Java 17 độc lập: mô phỏng trước và sau khi đọc

Để nắm chắc thứ tự, hãy chạy một ví dụ Java 17 **không cần Spring**. Nó cố ý trả chuỗi minh bạch “DENY:pre” và “DENY:post”; HTTP của Spring Security thật không trả những chuỗi này mặc định.

Tạo file **`PostAuthorizeFlowDemo.java`**:

~~~java
import java.util.Map;

public class PostAuthorizeFlowDemo {

    record Document(String id, String owner) {}

    private static final Map<String, Document> DOCUMENTS = Map.of(
        "A-1", new Document("A-1", "alice"),
        "B-1", new Document("B-1", "bob")
    );

    static String read(
            String username,
            boolean hasReadPermission,
            boolean auditor,
            String id
    ) {
        // Giả lập @PreAuthorize.
        if (!hasReadPermission) {
            return "DENY:pre";
        }

        // Target method đã thực thi phần đọc.
        Document result = DOCUMENTS.get(id);
        if (result == null) {
            return "NOT_FOUND";
        }

        // Giả lập @PostAuthorize trên returnObject.
        if (!username.equals(result.owner()) && !auditor) {
            return "DENY:post";
        }
        return "ALLOW:" + result.id();
    }

    public static void main(String[] args) {
        System.out.println("alice->A-1: "
            + read("alice", true, false, "A-1"));
        System.out.println("alice->B-1: "
            + read("alice", true, false, "B-1"));
        System.out.println("bob->B-1: "
            + read("bob", true, false, "B-1"));
        System.out.println("auditor->B-1: "
            + read("auditor", true, true, "B-1"));
        System.out.println("guest->A-1: "
            + read("guest", false, false, "A-1"));
        System.out.println("alice->X-9: "
            + read("alice", true, false, "X-9"));
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac PostAuthorizeFlowDemo.java
java PostAuthorizeFlowDemo
~~~

**Stdout xác định của chương trình:**

~~~text
alice->A-1: ALLOW:A-1
alice->B-1: DENY:post
bob->B-1: ALLOW:B-1
auditor->B-1: ALLOW:B-1
guest->A-1: DENY:pre
alice->X-9: NOT_FOUND
~~~

Ý nghĩa:

- `guest` bị từ chối **trước** khi tra bản đồ tài liệu.
- Alice truy vấn B-1 và tra được tài liệu, nhưng hậu kiểm không cho nhận kết quả.
- Auditor được đọc B-1 nhờ quyền tường minh trong chính sách giả lập.
- Tài liệu không tồn tại được xử lý như nhánh lỗi riêng, không tự trở thành ALLOW hay DENY dựa trên owner.

Ví dụ này **mô phỏng logic**, không mô phỏng Spring AOP, SpEL hay HTTP exception translation. Phần tiếp theo sẽ dùng Spring Security thật.

## 9. Ứng dụng Spring Boot Java 17+ hoàn chỉnh

### 9.1. Chức năng của ứng dụng

Một API tài liệu có hai bản ghi:

| ID | Owner | Title |
| --- | --- | --- |
| `A-1` | `alice` | `Plan A` |
| `B-1` | `bob` | `Plan B` |

Tài khoản:

| Principal | GrantedAuthority trực tiếp |
| --- | --- |
| `alice` | `document:read` |
| `bob` | `document:read` |
| `auditor` | `document:read`, `document:audit` |
| `charlie` | `ROLE_USER` |

Đường dẫn:

- `GET /public/ping`: công khai.
- `GET /api/documents/{id}`: cần đăng nhập ở HTTP, cần `document:read` ở `@PreAuthorize`, và cần **owner hoặc document:audit** ở `@PostAuthorize`.
- `GET /api/unlisted`: dù có controller, HTTP `denyAll()` vẫn chặn.
- `GET /api/documents/X-9`: minh họa **404 khi tài liệu không tồn tại**, nếu đã vượt pre-check.

Trong ví dụ chỉ có **GET**, nên CSRF mặc định không gây nhiễu các ca 403 (CSRF chủ yếu áp dụng method ghi như POST/PUT/PATCH/DELETE). Mật khẩu demo không được dùng trong production.

### 9.2. Project Maven

Tạo project Spring Boot **3.5.x** với Java **17+**, dependencies:

- `spring-boot-starter-web`
- `spring-boot-starter-security`
- `spring-boot-starter-test` (test scope)
- `spring-security-test` (test scope)

Sử dụng dependency management của Spring Boot, không tự chọn một tổ hợp phiên bản Spring Framework/Security không tương thích.

### 9.3. Mã ứng dụng đầy đủ

Tạo file **`src/main/java/com/example/postauth/PostAuthApplication.java`**:

~~~java
package com.example.postauth;

import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
@EnableMethodSecurity
public class PostAuthApplication {

    public static void main(String[] args) {
        SpringApplication.run(PostAuthApplication.class, args);
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .requestMatchers("/api/documents/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo123"))
            .authorities("document:read")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("demo456"))
            .authorities("document:read")
            .build();

        UserDetails auditor = User.withUsername("auditor")
            .password(encoder.encode("demo789"))
            .authorities("document:read", "document:audit")
            .build();

        UserDetails charlie = User.withUsername("charlie")
            .password(encoder.encode("demo000"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(
            alice, bob, auditor, charlie
        );
    }

    public static class Document {
        private final String id;
        private final String owner;
        private final String title;

        public Document(String id, String owner, String title) {
            this.id = id;
            this.owner = owner;
            this.title = title;
        }

        public String getId() { return id; }
        public String getOwner() { return owner; }
        public String getTitle() { return title; }
    }

    @Service
    public static class DocumentService {
        private final Map<String, Document> documents = Map.of(
            "A-1", new Document("A-1", "alice", "Plan A"),
            "B-1", new Document("B-1", "bob", "Plan B")
        );

        // Chỉ để test chứng minh method đã chạy trước hậu kiểm.
        private final AtomicInteger readCount = new AtomicInteger();

        @PreAuthorize("hasAuthority('document:read')")
        @PostAuthorize(
            "returnObject.owner == authentication.name or "
          + "hasAuthority('document:audit')"
        )
        public Document read(String id) {
            Document result = documents.get(id);
            if (result == null) {
                throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Document not found"
                );
            }

            readCount.incrementAndGet();
            return result;
        }

        public int getReadCount() {
            return readCount.get();
        }
    }

    @RestController
    static class Api {
        private final DocumentService service;

        Api(DocumentService service) {
            this.service = service;
        }

        @GetMapping("/public/ping")
        String ping() {
            return "pong";
        }

        @GetMapping("/api/documents/{id}")
        Document document(@PathVariable("id") String id) {
            return service.read(id);
        }

        @GetMapping("/api/unlisted")
        String unlisted() {
            return "must not be returned";
        }
    }
}
~~~

### 9.4. Phân tích code theo đúng thứ tự bảo vệ

**Tầng HTTP:** `GET /api/documents/{id}` cần danh tính đã xác thực. Nếu anonymous gửi yêu cầu, HTTP Basic thường trả `401`. `/api/unlisted` bị `anyRequest().denyAll()` chặn, bất kể role.

**Tầng trước method:** `@PreAuthorize("hasAuthority('document:read')")` chặn Charlie (chỉ có `ROLE_USER`) **trước khi tài liệu được đọc**. Có đăng nhập không có nghĩa có quyền nghiệp vụ.

**Tầng sau method:** khi Alice đọc `B-1`, method tìm thấy `Document(owner="bob")` và tăng bộ đếm đọc, nhưng `@PostAuthorize` từ chối việc trả object. Auditor được xem tài liệu của Alice/Bob nhờ `document:audit`, **không** nhờ một role ADMIN được ngầm định.

**Tài liệu không tồn tại:** service ném `ResponseStatusException(404)` trước khi có kết quả trả bình thường. Nhánh đó không phải một lần `@PostAuthorize` ALLOW. Trong API thật cần thiết kế chính sách 403/404 sao cho không làm lộ ID tài liệu của người khác.

**Bộ đếm đọc:** chỉ phục vụ minh họa rằng target method **đã được thực thi** khi bị từ chối hậu kiểm. Trong production nên tránh những side effects không cần thiết trước authorization và không dùng counter này làm dữ liệu bảo mật.

## 10. Ma trận kiểm chứng ALLOW và DENY

Với cùng một HTTP method GET:

| Request | Anonymous | Alice | Bob | Auditor | Charlie |
| --- | :---: | :---: | :---: | :---: | :---: |
| `GET /public/ping` | **200** | **200** | **200** | **200** | **200** |
| `GET /api/documents/A-1` | 401 | **200** | 403 | **200** | 403 |
| `GET /api/documents/B-1` | 401 | 403 | **200** | **200** | 403 |
| `GET /api/documents/X-9` | 401 | **404** | **404** | **404** | 403 |
| `GET /api/unlisted` | 401* | 403 | 403 | 403 | 403 |

`*` Với anonymous và `denyAll()` trong cấu hình HTTP Basic mẫu, kết quả thường là `401` do authentication entry point. Việc một user đã xác thực nhận `403` là kết quả DENY ở HTTP authorization. Một cấu hình `AuthenticationEntryPoint`/filter khác có thể thay status; đây là **dự kiến cho ứng dụng demo**.

**Nhìn vào những ca quan trọng:**

- Alice A-1 **200**, Alice B-1 **403**: biểu thức dựa trên **returnObject.owner** thật, không chỉ phụ thuộc tham số URL.
- Bob B-1 **200**, Bob A-1 **403**: cùng quy tắc cho chủ thể khác.
- Auditor A-1/B-1 **200**: nhánh OR `hasAuthority('document:audit')` được kiểm.
- Charlie A-1/B-1 **403**: thiếu `document:read`, nên bị chặn trước target.
- Alice/Bob/Auditor X-9 **404**: method ném not-found; không có return object để hậu kiểm.
- Bất kỳ user đã xác thực nào vào unlisted **403**: fallback HTTP từ chối.

### Body cho trường hợp được phép

`GET /api/documents/A-1` với Alice trả một JSON tương tự:

~~~json
{
  "id": "A-1",
  "owner": "alice",
  "title": "Plan A"
}
~~~

Đây là body dự kiến do controller/Jackson serialize lớp `Document`, không phải chuỗi do `@PostAuthorize` sinh ra. Nếu bị từ chối, JSON tài liệu đó **không được trả** cho caller qua đường gọi có proxy.

## 11. Chạy thử thủ công bằng curl

Ở thư mục root Maven project:

~~~bash
# Linux/macOS:
./mvnw spring-boot:run

# Windows PowerShell / Command Prompt:
mvnw.cmd spring-boot:run
~~~

Sau khi app chạy tại `http://localhost:8080`:

~~~bash
# Public và anonymous:
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/documents/A-1

# Owner có quyền nhận kết quả:
curl -i -u alice:demo123 http://localhost:8080/api/documents/A-1
curl -i -u bob:demo456 http://localhost:8080/api/documents/B-1

# User có document:read nhưng không phải owner:
curl -i -u alice:demo123 http://localhost:8080/api/documents/B-1
curl -i -u bob:demo456 http://localhost:8080/api/documents/A-1

# Auditor được phép theo policy OR:
curl -i -u auditor:demo789 http://localhost:8080/api/documents/B-1

# Charlie đã xác thực nhưng thiếu document:read:
curl -i -u charlie:demo000 http://localhost:8080/api/documents/A-1

# Tài liệu không tồn tại / URL chưa có chính sách:
curl -i -u alice:demo123 http://localhost:8080/api/documents/X-9
curl -i -u auditor:demo789 http://localhost:8080/api/unlisted
~~~

Dự kiến các mã lần lượt bao gồm 200, 401, 403, 404 như ma trận. Không so sánh body “Forbidden” cứng giữa các môi trường vì exception handler/error controller có thể tùy chỉnh định dạng. Đừng dùng Basic credential trên HTTP không mã hóa trong production; môi trường thật phải dùng HTTPS và nguồn user/authority đáng tin.

## 12. Viết bộ test MockMvc + Spring Security Test

### 12.1. Dependencies kiểm thử

Trong `pom.xml` cần:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Đây là fragment trong `<dependencies>` của Maven POM. Nếu project đã có `spring-boot-starter-test`, đừng thêm bản trùng. Spring Boot quản lý các phiên bản phụ thuộc để khớp Spring Security.

### 12.2. Test class hoàn chỉnh

Tạo file **`src/test/java/com/example/postauth/PostAuthApplicationTests.java`**:

~~~java
package com.example.postauth;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Assertions;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PostAuthApplicationTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    PostAuthApplication.DocumentService service;

    @ParameterizedTest
    @CsvSource({
        // username,password,path,expectedStatus
        "anonymous,none,/public/ping,200",
        "anonymous,none,/api/documents/A-1,401",
        "anonymous,none,/api/unlisted,401",

        "alice,demo123,/api/documents/A-1,200",
        "alice,demo123,/api/documents/B-1,403",
        "alice,demo123,/api/documents/X-9,404",
        "alice,demo123,/api/unlisted,403",

        "bob,demo456,/api/documents/B-1,200",
        "bob,demo456,/api/documents/A-1,403",
        "bob,demo456,/api/documents/X-9,404",

        "auditor,demo789,/api/documents/A-1,200",
        "auditor,demo789,/api/documents/B-1,200",
        "auditor,demo789,/api/documents/X-9,404",
        "auditor,demo789,/api/unlisted,403",

        "charlie,demo000,/api/documents/A-1,403",
        "charlie,demo000,/api/documents/B-1,403",
        "charlie,demo000,/api/documents/X-9,403"
    })
    void httpAuthorizationMatrix(
            String username, String password,
            String path, int expectedStatus
    ) throws Exception {
        MockHttpServletRequestBuilder request = get(path);
        if (!"anonymous".equals(username)) {
            request.with(httpBasic(username, password));
        }
        mvc.perform(request).andExpect(status().is(expectedStatus));
    }

    @Test
    void ownerReceivesDocumentJson() throws Exception {
        mvc.perform(get("/api/documents/A-1")
                .with(httpBasic("alice", "demo123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value("A-1"))
            .andExpect(jsonPath("$.owner").value("alice"))
            .andExpect(jsonPath("$.title").value("Plan A"));
    }

    @Test
    void nonOwnerCannotReceiveDocument() throws Exception {
        mvc.perform(get("/api/documents/B-1")
                .with(httpBasic("alice", "demo123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void auditorCanReadAcrossOwners() throws Exception {
        mvc.perform(get("/api/documents/B-1")
                .with(httpBasic("auditor", "demo789")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.owner").value("bob"));
    }

    @Test
    void wrongPasswordIsAuthenticationFailure() throws Exception {
        mvc.perform(get("/api/documents/A-1")
                .with(httpBasic("alice", "incorrect")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:read")
    void postDenyHappensAfterTargetMethodRan() {
        int before = service.getReadCount();

        assertThrows(
            AccessDeniedException.class,
            () -> service.read("B-1")
        );

        // Đã đọc B-1 nhưng không được trả cho caller.
        assertEquals(before + 1, service.getReadCount());
    }

    @Test
    @WithMockUser(username = "charlie", authorities = "ROLE_USER")
    void preDenyHappensBeforeTargetMethodRan() {
        int before = service.getReadCount();

        assertThrows(
            AccessDeniedException.class,
            () -> service.read("A-1")
        );

        // Thiếu document:read, target method không được chạy.
        assertEquals(before, service.getReadCount());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "document:read")
    void directlyCallingSpringBeanEnforcesPostAuthorize() {
        PostAuthApplication.Document doc = service.read("B-1");
        assertEquals("B-1", doc.getId());

        assertThrows(
            AccessDeniedException.class,
            () -> service.read("A-1")
        );
    }
}
~~~

**Một lưu ý về test:** import `org.junit.jupiter.api.Assertions` trong ví dụ không cần trực tiếp vì đã dùng static imports; có thể xóa để làm sạch IDE warning. Các ca kiểm thử có thể chạy độc lập theo cách Maven/JUnit thực thi thông thường; nếu bật **parallel test execution** và share cùng bean counter, cần đồng bộ/thiết kế test riêng để tránh kết quả không ổn định.

### 12.3. Vì sao có hai lớp test?

**MockMvc + `httpBasic`** kiểm toàn bộ luồng HTTP → Authentication → HTTP rule → method proxy → JSON/status. Các test 200/403/404 phân biệt owner, auditor, missing document và default deny.

**`@WithMockUser` + gọi thẳng Spring bean** kiểm phương thức độc lập với controller và cho phép đo `readCount`:

- Alice có `document:read` nhưng đọc B-1: counter **tăng 1**, sau đó `AccessDeniedException` → chứng minh hậu kiểm hoạt động sau khi target đã chạy.
- Charlie thiếu `document:read`: counter **không tăng** → chứng minh tiền kiểm chặn trước khi target chạy.
- Bob đọc B-1 được trả Document; đọc A-1 ném exception.

Điều kiện quan trọng là `service` phải được **inject từ Spring ApplicationContext**. Nếu tạo `new DocumentService()`, lời gọi không đi qua Spring AOP proxy và `@PostAuthorize` không có cơ hội kiểm; test đó không chứng minh an toàn.

### 12.4. Chạy test

~~~bash
# Linux/macOS:
./mvnw test

# Windows:
mvnw.cmd test
~~~

Kỳ vọng các ca đều pass trong project đúng dependencies và không có custom security/exception handler khác. **Không bịa log test**: kết quả thực tế, exit code và báo cáo JUnit/Maven mới xác nhận ứng dụng đang hoạt động.

## 13. Các tình huống ngoài ví dụ: API trả collection, nhiều role và dữ liệu phức tạp

### 13.1. Khi method trả List

`@PostAuthorize` đưa ra một quyết định cho **toàn bộ giá trị trả về**. Nếu muốn “danh sách chỉ gồm document của người gọi” thì có hai chiến lược:

1. Ưu tiên truy vấn dữ liệu với ràng buộc tenant/owner **ngay trong repository**, ví dụ điều kiện `owner_id = current_user_id`.
2. Với collection nhỏ và mục đích phù hợp, dùng `@PostFilter("filterObject.owner == authentication.name")` để loại những phần tử không đạt.

Không nên dùng `@PostAuthorize("returnObject.owner == ...")` trên `List<Document>` như thể list có property owner. Nếu muốn policy “caller chỉ được nhận cả list nếu mọi phần tử đều hợp lệ”, phải viết biểu thức/authorization bean phù hợp và test cả list rỗng, list hỗn hợp, null.

### 13.2. Khi method trả DTO thay vì entity

Nếu method trả `DocumentDto(id, owner, title)`, expression cần trỏ tới property **của DTO thực sự trả ra**, không phải entity đã biến mất trước khi tới hậu kiểm. Cần bảo đảm `owner` trong DTO đến từ dữ liệu server đáng tin, không lấy từ request mà client tự gửi.

Cũng cần đề phòng dữ liệu ngoài phạm vi quyền đã bị ghi log hoặc cache trong lúc ánh xạ DTO. Trả một DTO không tự biến hệ thống thành an toàn nếu trường quyền bị tính sai.

### 13.3. Trường owner lồng sâu

Ví dụ:

~~~java
@PostAuthorize(
    "returnObject != null and returnObject.project != null "
  + "and returnObject.project.tenantId == authentication.name"
)
public Document readInTenant(String id) {
    return repository.load(id);
}
~~~

Đây chỉ là **fragment**; cần model `project`/`tenantId` tương ứng. Không sử dụng `authentication.name` làm tenant ID trong sản phẩm nếu principal là username còn tenant là một khái niệm khác. Khi policy nhiều điều kiện, nên chuyển sang bean `@documentPolicy.canRead(authentication, returnObject)` để test bằng Java rõ ràng và kiểm soát null chặt chẽ.

### 13.4. Khi dùng role hierarchy

Nếu Spring Security được cấu hình `RoleHierarchy`, một biểu thức `hasRole(...)` trong `@PostAuthorize` có thể sử dụng các reachable authorities tương ứng khi expression handler áp dụng hierarchy. Nhưng **không tự suy ra** một role cao có quyền đọc mọi tài liệu: kết hợp owner, tenant và quyền audit theo chính sách thật.

### 13.5. Khi dùng Spring Security Reactive

Bài này dùng **Servlet/Spring MVC và Spring AOP**. Với WebFlux/Reactor, cách trả `Mono`/`Flux` và ngữ cảnh reactive khác, cần đọc tài liệu reactive method security để xử lý thời điểm subscription, publisher values và authorization. Không copy test MockMvc/Servlet rồi cho rằng đang kiểm reactive behavior.

## 14. Lỗi triển khai thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ viết `@PostAuthorize` nhưng không bật `@EnableMethodSecurity` | Annotation không được kiểm | Bật method security và test DENY |
| Coi `returnObject` là request body hoặc tham số đầu vào | SpEL không kiểm đúng object | Dùng đúng kiểu giá trị trả về |
| Dùng `returnObject.owner` khi method trả null | Có thể lỗi expression | Quyết định contract null/404 và guard |
| Dùng `returnObject.owner` khi method trả Optional/List | Sai cấu trúc return value | Dùng policy cho wrapper hoặc filtering |
| So sánh owner với ID do client tự khai báo là “tôi” | Dễ bị giả mạo | Dùng `authentication.name`/identity server-side |
| Chỉ dùng `@PostAuthorize` trên lệnh ghi | Side effect đã xảy ra trước DENY | Tiền kiểm + domain policy trước ghi |
| Tin `@Transactional` luôn rollback hậu kiểm DENY | Phụ thuộc advisor/transaction timing | Kiểm thiết kế transaction và test side effects |
| Đọc toàn bộ tenant rồi mới hậu kiểm | Rủi ro lộ dữ liệu/cache và tốn chi phí | Query theo scope, least privilege |
| Dùng `@PostAuthorize` thay `@PostFilter` cho list | Cả list bị DENY hoặc SpEL lỗi | Chọn cơ chế theo contract |
| Dùng `this.read(...)` trong cùng service | Có thể bỏ qua proxy | Gọi qua injected Spring bean |
| Tạo service bằng `new` | Không được Spring AOP bảo vệ | Dùng bean từ context |
| Đặt annotation trên method không interceptable | Policy không chạy | Kiểm proxy/interface/final/private |
| Trông chờ HTTP `authenticated()` đủ để bảo vệ document ID | Người dùng đọc dữ liệu người khác | Thêm owner/tenant checks |
| Không test anonymous/wrong password | Nhầm authentication với authorization | Thêm 401 tests |
| Không test tài liệu không thuộc caller | Không phát hiện IDOR | Thêm 403 negative tests |
| Nhầm 403 CSRF trên POST là do hậu kiểm | Debug sai nơi chặn | Tách CSRF và method security |
| Trả 404 cho không có ID, 403 cho ID có nhưng không thuộc user vô ý | Lộ sự tồn tại của resource | Thiết kế response theo threat model |
| Cho auditor quyền quá rộng | Đọc dữ liệu vượt mục đích | Cấp quyền audit có kiểm soát, log/audit |

### Checklist trước khi triển khai thực

1. Method có được gọi qua Spring-managed proxy và `@EnableMethodSecurity` có hiệu lực không?
2. `returnObject` là loại nào: POJO, DTO, null, Optional hay List?
3. Owner/tenant có dựa vào dữ liệu server đáng tin và identity thật không?
4. Có `@PreAuthorize` hoặc kiểm quyền sớm để giảm rủi ro load dữ liệu không cần thiết không?
5. Nếu target method có side effect, có chính sách **trước khi ghi** và kiểm trong transaction/domain không?
6. HTTP 401, method 403, CSRF 403 và domain 404 có được tách đúng trong test không?
7. Có test ALLOW của owner, DENY của non-owner, quyền auditor, null/not-found và default deny không?
8. Nếu hỗ trợ multi-tenant/list/search, truy vấn đã lọc theo phạm vi dữ liệu chưa?
9. Có tránh log dữ liệu nhạy cảm khi hậu kiểm từ chối không?
10. Nếu thay SpEL bằng custom bean hoặc annotation riêng, có test trực tiếp bean và integration test proxy không?

## 15. Tự kiểm tra kiến thức

**Câu 1.** `returnObject` trong `@PostAuthorize` là gì?  
**Đáp án:** Giá trị target method đã trả, đang được xét xem có thể đưa đến caller không.

**Câu 2.** `@PostAuthorize` chạy trước hay sau target method?  
**Đáp án:** Sau khi method trả kết quả bình thường.

**Câu 3.** Vì sao Alice có `document:read` vẫn bị 403 khi đọc B-1?  
**Đáp án:** `@PreAuthorize` cho phép gọi method nhưng `returnObject.owner` là Bob; Alice không có `document:audit` nên hậu kiểm DENY.

**Câu 4.** Auditor được đọc B-1 vì sao?  
**Đáp án:** Vì policy tường minh cho phép nhánh `hasAuthority('document:audit')`, không phải vì “auditor luôn là admin”.

**Câu 5.** Có nên gắn `@PostAuthorize` làm kiểm quyền duy nhất cho method chuyển tiền hoặc xóa bản ghi không?  
**Đáp án:** Không, vì thao tác đã có thể thực hiện trước khi hậu kiểm từ chối.

**Câu 6.** `@PostAuthorize("returnObject.owner == ...")` dùng được ngay khi method trả `Optional<Document>` không?  
**Đáp án:** Không nên: `returnObject` là wrapper Optional; cần policy nhận đúng kiểu hoặc đổi return contract.

**Câu 7.** Vì sao cần xử lý null riêng?  
**Đáp án:** Truy cập property của null có thể làm expression lỗi. Phải quy định ALLOW/DENY/not-found tường minh.

**Câu 8.** `@PostAuthorize` và `@PostFilter` khác gì khi method trả danh sách?  
**Đáp án:** PostAuthorize ra quyết định cho toàn giá trị trả về; PostFilter lọc từng phần tử trong collection.

**Câu 9.** Khi Alice bị DENY sau khi target đã đọc B-1, dữ liệu B-1 có chắc chưa từng vào memory/cache/log không?  
**Đáp án:** Không. Hậu kiểm ngăn trả kết quả qua proxy, không xóa mọi side effect đã xảy ra.

**Câu 10.** Test `readCount` chứng minh điều gì?  
**Đáp án:** Khi bị hậu kiểm từ chối, target method đã chạy và counter tăng; khi bị tiền kiểm từ chối, counter không tăng.

**Câu 11.** Method không được gọi qua Spring AOP proxy có được `@PostAuthorize` bảo vệ không?  
**Đáp án:** Không nên coi là được bảo vệ. Phải test bean thực, tránh self-invocation và object tự `new`.

**Câu 12.** Vì sao nên có thêm `@PreAuthorize("hasAuthority('document:read')")`?  
**Đáp án:** Để từ chối người thiếu quyền nghiệp vụ trước khi tải object, thay vì bắt buộc thực hiện đọc rồi mới kiểm.

**Câu 13.** `@PostAuthorize` trả trực tiếp JSON thông báo Forbidden không?  
**Đáp án:** Không. Nó ra quyết định ở proxy; cơ chế xử lý ngoại lệ/HTTP chịu trách nhiệm tạo response theo cấu hình.

**Câu 14.** Hậu kiểm có tự xử lý được nhánh target method ném 404 không?  
**Đáp án:** Khi không có kết quả trả bình thường, không có `returnObject` tương ứng để đánh giá; phải bảo vệ các nhánh lookup/lỗi theo policy riêng.

**Câu 15.** Thêm `@PostAuthorize` đã đủ để chống IDOR/BOLA trong hệ thống nhiều tenant chưa?  
**Đáp án:** Chưa. Cần kiểm tenant/ACL/ownership, lọc truy vấn, hạn chế field, xử lý race và response không rò rỉ.

**Ghi nhớ:** **`@PostAuthorize` kiểm đối tượng đã được method trả về** qua biến SpEL **`returnObject`**, rất hữu ích cho bài toán owner trên **thao tác đọc**. Kết hợp tiền kiểm để hạn chế truy cập sớm, không dựa vào hậu kiểm làm bảo vệ duy nhất cho ghi dữ liệu, và luôn kiểm thử **được phép đúng / từ chối đúng / không tìm thấy đúng**.

## Tài liệu chính thức

- Spring Security 6.5 — Method Security, phần **Authorization Method Results with `@PostAuthorize`** và sơ đồ các interceptor: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 — API `PostAuthorize`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/prepost/PostAuthorize.html
- Spring Security 6.5 — API `PostAuthorizeAuthorizationManager`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/method/PostAuthorizeAuthorizationManager.html
- Spring Security 6.5 — `AuthorizationManagerAfterMethodInterceptor` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/method/AuthorizationManagerAfterMethodInterceptor.html
- Spring Security 6.5 — Testing HTTP Basic with MockMvc: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html
- Spring Security 6.5 — Spring MVC test with method security: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/
