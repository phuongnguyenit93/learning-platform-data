# Phối hợp bảo vệ nhiều lớp mà không bỏ sót hoặc mâu thuẫn chính sách

## 1. Bài toán: một lớp cho phép vẫn có thể chưa đủ quyền

Trong hệ thống Spring Security, kiểm tra quyền ở HTTP, phương thức dịch vụ và tài nguyên không giải quyết cùng một câu hỏi. Một người đã đăng nhập có thể có quyền `document:read` nhưng không được xem tài liệu thuộc tenant khác; một controller có thể bảo vệ đúng URL nhưng tác vụ nền lại gọi cùng repository mà không qua bộ lọc HTTP; một phương thức đã được duyệt có thể trở nên không hợp lệ khi tài liệu đổi trạng thái trước lúc ghi.

**Bảo vệ nhiều lớp** là thiết kế các chốt kiểm tra để mọi đường tới hành động nhạy cảm đều đáp ứng chính sách chung. Các chốt có thể kiểm tra điều kiện khác nhau và cùng đóng góp vào quyết định cuối, không nhất thiết lặp mọi câu lệnh quyền.

Một luồng đơn giản:

```text
Request HTTP
  |
  v
Xác thực: ai đang gọi?
  |
  v
FilterChainProxy chọn SecurityFilterChain đầu tiên khớp
  |
  v
HTTP Authorization: được gọi hành động trên route này?
  |      Không -> DENY
  v
Method Security: có quyền chạy nghiệp vụ này?
  |      Không -> DENY
  v
Object Policy: có quyền với tài nguyên này, trong ngữ cảnh này?
  |      Không -> DENY
  v
Repository / transaction: truy vấn đúng tenant, ghi đúng trạng thái?
  |      Không -> DENY/ERROR
  v
THỰC THI + AUDIT

Đường không qua HTTP (job, consumer, internal call)
  -> Bắt đầu từ một ranh giới dịch vụ/đối tượng có cùng chính sách
```

Sơ đồ trên là **khái niệm**: tùy thiết kế, việc kiểm tra owner/tenant có thể nằm ngay trong truy vấn; một service có thể được gọi qua nhiều entrypoint; và transaction có thể bao quanh các kiểm tra nghiệp vụ. Điều bất biến là không đường truy cập nào được phép bỏ qua điều kiện bắt buộc.

### Ba dạng lỗi cần phân biệt

- **Bỏ sót lớp:** URL mới không khớp bất kỳ `SecurityFilterChain` nào, endpoint export không kiểm tra tenant, hoặc job viết trực tiếp xuống database.
- **Mâu thuẫn ý định chính sách:** controller cho phép “manager sửa mọi tài liệu”, nhưng service cho phép “chỉ owner sửa DRAFT”; hai nơi cùng tuyên bố định nghĩa quyền sửa mà không có quy tắc thống nhất.
- **Từ chối bổ sung đúng chính sách:** HTTP cho phép vì user có `document:update` nhưng service từ chối vì tài liệu đã APPROVED. Đây là kết quả đúng khi **cả permission và trạng thái** đều bắt buộc.

Mục tiêu bài học: biết chọn và phối hợp các lớp bảo vệ, tránh lỗi thứ tự matcher và filter chain, diễn đạt điều kiện bằng AND/OR đúng, bảo vệ các đường ngoài HTTP, xác minh bằng unit/integration test, và xử lý thay đổi/tranh chấp dữ liệu.

## 2. Bảng trách nhiệm của từng ranh giới

| Ranh giới | Điều nên kiểm tra | Công cụ/thành phần | Không nên mặc định |
| --- | --- | --- | --- |
| Identity | Danh tính đã xác thực, trạng thái tài khoản | `Authentication`, `SecurityContext`, authentication filters | Client gửi `userId`/`role` là thật |
| Chọn chuỗi lọc | Request thuộc chain nào? | `FilterChainProxy`, `SecurityFilterChain`, `@Order`, `securityMatcher` | Mọi chain đều chạy nối tiếp |
| HTTP authorization | Route, HTTP method, permission chức năng | `authorizeHttpRequests`, `requestMatchers`, `AuthorizationFilter` | Đúng URL nghĩa là có quyền với mọi ID |
| Method authorization | Có được gọi hành động nghiệp vụ? | `@EnableMethodSecurity`, `@PreAuthorize` | Annotation bảo vệ được mọi lời gọi trong cùng instance |
| Object policy | Có quyền trên đối tượng cụ thể? | Policy service, owner/tenant/state/sharing | Có role là đủ đọc mọi dữ liệu |
| Repository | Truy vấn có giới hạn đúng phạm vi? | Điều kiện SQL/JPA, row-level security nếu được triển khai đúng | Lọc phía giao diện đủ an toàn |
| Transaction/data invariants | Quyền và trạng thái còn đúng khi ghi? | Version, lock, constraint, conditional update | Kiểm tra trước là đủ chống mọi race |
| Non-HTTP | Job/consumer/RPC được thực thi dưới danh tính nào? | Service entrypoint, machine identity, policy | “Nội bộ” tự động đáng tin |
| Audit/operations | Vì sao được phép/từ chối, quyền đổi khi nào? | Event log, trace, review quyền | Log thay thế cho kiểm tra trước thao tác |

Một lớp có thể chặn sớm những yêu cầu rõ ràng không hợp lệ, giảm tải cho lớp dưới. Nhưng **quyền trên tài nguyên thực tế phải được bảo vệ tại nơi có đủ thông tin để quyết định**. Đặc biệt với các chức năng dùng chung giữa nhiều kênh, service hoặc lớp dữ liệu là ranh giới cần xác định cẩn thận.

## 3. Viết chính sách chung trước khi gắn annotation

Giả sử một ứng dụng quản lý tài liệu đa tenant với các trường: `id`, `tenantId`, `ownerId`, `status` và `version`. Danh tính phía server có `userId`, tenant đã được kiểm chứng và các authority có hiệu lực.

Đặt ra chính sách minh họa:

| Hành động | Permission | Điều kiện dữ liệu | Điều kiện trạng thái |
| --- | --- | --- | --- |
| Đọc tài liệu | `document:read` | Cùng tenant và là owner hoặc được chia sẻ hợp lệ | Theo quy tắc đọc |
| Sửa tài liệu | `document:update` | Cùng tenant và là owner | `DRAFT` |
| Duyệt tài liệu | `document:approve` | Cùng tenant, người duyệt khác người tạo | `PENDING` |
| Xóa tài liệu | `document:delete` | Cùng tenant và được giao quyền xóa đối tượng | Theo quy trình xóa |

Đây là **mô hình ví dụ**, không phải chính sách mặc định của Spring Security. Những nhánh chia sẻ, duyệt và xóa phải được định nghĩa đầy đủ nếu ứng dụng triển khai chúng.

### 3.1. Diễn đạt bằng các điều kiện tường minh

```text
canRead =
  authenticated
  AND hasAuthority(document:read)
  AND sameTenant
  AND (isOwner OR validReadShare)

canUpdate =
  authenticated
  AND hasAuthority(document:update)
  AND sameTenant
  AND isOwner
  AND (status == DRAFT)
```

Tại đây, `AND` là **đủ mọi điều kiện bắt buộc**, còn `OR` chỉ cho phép những **nhánh thay thế đã được nghiệp vụ phê duyệt**. Nếu viết sai dấu ngoặc thành:

```text
(hasAuthority(document:read) AND sameTenant AND isOwner)
OR validReadShare
```

thì người có share grant có thể vượt qua điều kiện permission và tenant, trừ khi đó thực sự là chính sách có chủ đích. Hãy viết chính sách đầy đủ thành câu, bảng và test để tránh sự nhầm lẫn khi chuyển sang biểu thức Java/SpEL.

### 3.2. Mặc định từ chối và các ngoại lệ

Người đã đăng nhập mà không có quyền cụ thể phải bị từ chối. Một thao tác mới chưa có rule không nên tự động được phép. Trạng thái không biết, owner không xác định, kết quả policy service không tin cậy cũng không được chuyển thành “đã cho phép”.

Điều này không có nghĩa mọi lỗi mạng đều trả HTTP 403; lỗi phụ thuộc có thể cần 5xx hoặc retry có giới hạn. **Hành động nhạy cảm không được tiến hành khi chưa xác minh được quyền**, bất kể mã HTTP nào biểu diễn lỗi.

### 3.3. Mâu thuẫn thực sự là gì?

Có hai kiểu phải xử lý:

1. **Một nơi dùng quyền tổng quát khác ý nghĩa:** HTTP yêu cầu `ROLE_EDITOR`, service yêu cầu `document:update`, nhưng không có mapping chuẩn xác giữa role và permission. Kết quả có thể sai lệch do cấu hình/đặc quyền.
2. **Hai nơi diễn đạt khác nhau về một quy tắc object:** controller kiểm tra “cùng tenant”, còn một service khác lại cho “mọi manager đọc mọi tenant”, không có mô hình ngoại lệ thống nhất.

Cách sửa là đưa quyền chức năng vào một catalog, nêu rõ mapping `role → authorities` và tập trung chính sách đối tượng ở thành phần có thể tái sử dụng; viết test cho mọi đường đi. Đừng giải quyết bằng cách xóa lớp từ chối mà chưa biết nó đang bảo vệ điều kiện gì.

## 4. Lớp HTTP: chọn SecurityFilterChain đúng trước khi xét requestMatchers

### 4.1. `securityMatcher` khác `requestMatchers`

Trong Spring Security Servlet, `FilterChainProxy` chọn **SecurityFilterChain đầu tiên khớp request** theo thứ tự ưu tiên. **Chỉ chain được chọn được chạy**; các chain khác không tự động áp dụng như những điều kiện bổ sung.

- `http.securityMatcher("/api/**")` xác định **phạm vi áp dụng của cả chain**.
- `http.authorizeHttpRequests(auth -> auth.requestMatchers(...))` xác định **quy tắc truy cập bên trong chain**.
- `anyRequest().denyAll()` chỉ xử lý những request **đã vào chain đó** nhưng chưa khớp quy tắc trước; không bảo vệ được URL nằm ngoài chain.

Sai sót rất thường gặp: có một chain duy nhất dùng `securityMatcher("/api/**")`, sau đó cho rằng `anyRequest().denyAll()` sẽ cấm cả `/admin/export`. Nếu không có chain khớp `/admin/export`, request đó có thể không được Spring Security bảo vệ.

### 4.2. Cấu hình hai chain có fallback

Đoạn sau là **mã Spring Boot Servlet tích hợp**, phù hợp phong cách cấu hình Spring Security 6 và không phải chương trình Java độc lập. Ứng dụng thực cần cấu hình cơ chế xác thực phù hợp (session, OAuth2 Resource Server, v.v.).

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class AuthorizationConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/documents/**")
                    .hasAuthority("document:read")
                .requestMatchers(HttpMethod.PATCH, "/api/documents/**")
                    .hasAuthority("document:update")
                .anyRequest().denyAll()
            );
        return http.build();
    }

    @Bean
    SecurityFilterChain fallbackSecurity(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/public/ping")
                .permitAll()
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
```

Đọc từng điểm:

1. API chain được xét trước nhờ `@Order(1)`, chỉ áp dụng cho `/api/**`.
2. Trong API chain, `GET /api/documents/101` yêu cầu `document:read`, còn `PATCH /api/documents/101` yêu cầu `document:update`. Những đường/method API khác bị từ chối.
3. Fallback không khai báo `securityMatcher` nên có phạm vi khớp các request còn lại. Chỉ đường GET được duyệt là công khai; phần khác bị từ chối.
4. Hai `anyRequest()` có phạm vi **khác nhau**. Chúng không chạy nối tiếp cho cùng request.
5. `@EnableMethodSecurity` bật cơ chế method security cho các phương thức/bean phù hợp; không tự động gắn quyền lên mọi method.
6. Code mẫu chưa cấu hình authentication, CSRF hay CORS. Phải cấu hình riêng theo kiến trúc; đặc biệt không tắt CSRF tùy tiện khi dùng cookie/session.

**Ghi nhớ:** nếu chain ưu tiên cao khớp `/**` thì chain API ưu tiên thấp hơn có thể không bao giờ được chọn. Một chain “có quyền admin” ở sau không sửa được chain quá rộng cho phép trước đó. Kiểm thử thứ tự chain bằng các request cụ thể.

### 4.3. Thứ tự các matcher trong cùng chain

Các rule của `authorizeHttpRequests` thường được đánh giá theo thứ tự khai báo để chọn rule đầu tiên khớp. Hãy đặt rule hẹp và nhạy cảm trước các rule bao quát.

```text
Nguy hiểm:
  /api/**            -> authenticated
  /api/admin/**      -> hasRole("ADMIN")  (có thể không được chọn)

Chặt chẽ:
  /api/admin/**      -> hasRole("ADMIN")
  /api/documents/**  -> quyền theo HTTP method
  anyRequest         -> denyAll
```

Không giả định rule của admin sẽ được kiểm tra “thêm lần nữa” sau khi một matcher rộng đã cho phép. Cũng không tự mặc định `authenticated()` đủ cho hành động nghiệp vụ chỉ dành cho một permission.

### 4.4. Các điểm HTTP dễ bỏ sót

Phải xem xét đầy đủ phương thức `GET/POST/PATCH/PUT/DELETE`, biến thể đường dẫn, tài nguyên tĩnh, endpoint tải tệp, actuator, login/logout, CORS preflight, gateway rewrite và đường lỗi. Không mở rộng `permitAll()` vô điều kiện cho mọi endpoint chỉ vì hệ thống có một số endpoint công khai.

Đối với nhiều chain, mỗi chain có thể có các filter và cách xác thực khác nhau. Tác dụng của `csrf()`, authentication filter, security headers và exception handler cần được kiểm tra trên **chain thực sự được chọn**.

## 5. Lớp service: giữ chính sách cho mọi đường gọi nghiệp vụ

HTTP là ranh giới đầu tiên nhưng service có thể được gọi bởi controller thứ hai, job nền, batch import hoặc thành phần xử lý sự kiện. Một service xử lý dữ liệu nhạy cảm nên có điểm kiểm tra rõ ràng.

### 5.1. Method security trong Spring

Cần bật method security với `@EnableMethodSecurity`. Với Spring AOP proxy thông dụng, một phương thức public được gọi qua Spring bean/proxy có thể được bảo vệ:

```java
@PreAuthorize("hasAuthority('document:update')")
public void updateDraft(long documentId, UpdateDocumentCommand command) {
    // Logic nghiệp vụ và quyền theo đối tượng.
}
```

Tuy nhiên, annotation này chỉ kiểm tra **quyền chức năng**. Nó không tự biết `documentId` thuộc tenant nào, ai sở hữu, đã phê duyệt chưa hoặc yêu cầu có bị khóa không.

Khi kết hợp các annotation method security, mỗi bộ kiểm tra có thể thực thi nối tiếp và tất cả điều kiện áp dụng cần được đáp ứng. Không nên lặp hai lần cùng `@PreAuthorize` trên một phương thức; với các điều kiện phức tạp, viết một biểu thức rõ hoặc ủy quyền tới một policy bean.

### 5.2. Service bảo vệ tài nguyên cụ thể

Mã sau là **ví dụ tích hợp**, cần các lớp miền/repository do dự án định nghĩa, không phải chương trình hoàn chỉnh.

```java
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentService {
    private final DocumentRepository repository;
    private final CurrentActor currentActor;

    public DocumentService(
            DocumentRepository repository, CurrentActor currentActor) {
        this.repository = repository;
        this.currentActor = currentActor;
    }

    @Transactional(readOnly = true)
    @PreAuthorize("hasAuthority('document:read')")
    public DocumentView read(long documentId) {
        var actor = currentActor.requireAuthenticated();

        var document = repository.findByIdAndTenantIdAndOwnerId(
            documentId, actor.tenantId(), actor.userId()
        ).orElseThrow(() -> new DocumentNotFoundException(documentId));

        return DocumentView.from(document);
    }

    @Transactional
    @PreAuthorize("hasAuthority('document:update')")
    public void updateDraft(
            long documentId, UpdateDocumentCommand command) {

        var actor = currentActor.requireAuthenticated();

        var document = repository.findByIdAndTenantIdAndOwnerId(
            documentId, actor.tenantId(), actor.userId()
        ).orElseThrow(() -> new DocumentNotFoundException(documentId));

        if (!document.isDraft()) {
            throw new AccessDeniedException("Update denied");
        }

        document.applyAllowedChanges(command);
        // Cần thiết kế thêm chống ghi dựa trên version cũ.
    }
}
```

Quyền được thực thi qua các lớp:

- **HTTP**: requester phải có `document:read` hoặc `document:update` để vào endpoint tương ứng.
- **Method**: cùng quyền chức năng được kiểm tra khi service được gọi từ một entrypoint khác, với điều kiện lời gọi đi qua cơ chế method security.
- **Data**: truy vấn chỉ lấy tài liệu khớp ID, tenant và owner. Trong mô hình có chia sẻ, policy truy vấn cần thêm các grant hợp lệ.
- **Workflow**: chỉ sửa được tài liệu DRAFT.
- **Transaction**: cần đảm bảo dữ liệu vẫn hợp lệ tại lúc ghi, xử lý update đồng thời.

Lưu ý mã trên chưa là giải pháp đầy đủ cho optimistic locking, hạn mức, kiểm toán hoặc quyền chia sẻ. Mục tiêu là cho thấy mỗi điều kiện được đặt tại nơi có dữ liệu đáng tin.

### 5.3. Tránh self-invocation và gọi ngoài proxy

Spring AOP proxy có thể bị đi vòng nếu một phương thức trên cùng object tự gọi phương thức được annotation bảo vệ:

```java
@Service
class BadApprovalService {
    void process() {
        approve(); // Gọi trực tiếp trong cùng instance.
    }

    @PreAuthorize("hasAuthority('document:approve')")
    public void approve() {
        // Thao tác nhạy cảm
    }
}
```

Khi lời gọi không qua proxy, annotation có thể không chạy. Cần thiết kế entrypoint được gọi qua Spring bean/proxy đúng cách, đặt policy vào nơi luôn được gọi, và giữ bất biến tại dữ liệu. Không dựa vào `@PreAuthorize` như một phép bảo vệ mặc định cho mọi lời gọi cùng instance.

Một lớp tự tạo bằng `new` ngoài Spring container cũng không tự nhận advice của method security. Với tác vụ nền, cần xác định danh tính thực thi hoặc quyền hệ thống thay vì giả định luôn có principal từ HTTP.

## 6. Lớp dữ liệu: chống IDOR/BOLA và sai phạm vi

### 6.1. Query phải giới hạn đúng object

Với một API nhận ID từ URL, check `document:read` và sau đó gọi `findById(id)` đơn thuần có thể để lộ tài liệu của người khác. Đây là dạng lỗi **IDOR/BOLA**.

```sql
-- Không đủ để chứng minh quyền đọc bản ghi:
SELECT * FROM documents WHERE id = :id;

-- Mô hình owner trong cùng tenant:
SELECT *
FROM documents
WHERE id = :id
  AND tenant_id = :tenantId
  AND owner_id = :userId;
```

Áp dụng phạm vi tương đương cho `list/search/pagination/download/export`; không lọc sau khi dữ liệu đã được trả ra cho client. Với mô hình chia sẻ, truy vấn phải diễn đạt nhánh owner hoặc share grant **mà vẫn giữ các điều kiện bất biến**.

### 6.2. TOCTOU: kiểm tra đúng nhưng ghi bằng dữ liệu cũ

Giả sử hai request cùng đọc document đang DRAFT. Request A duyệt tài liệu, request B vẫn giữ dữ liệu cũ và gọi update. Nếu lệnh ghi B không kiểm tra lại state/version, kết quả có thể vi phạm “đã duyệt thì không được sửa”.

Các biện pháp thường dùng:

- **Optimistic locking** bằng cột `version` và xử lý cập nhật xung đột.
- **Pessimistic lock** khi cần tuần tự hóa truy cập một số bản ghi.
- **Conditional UPDATE** kèm tenant, trạng thái và version ở mệnh đề `WHERE`; xác nhận số dòng thay đổi.
- Ràng buộc database cho các invariant có thể biểu diễn ở dữ liệu.

Ví dụ minh họa:

```sql
UPDATE documents
SET title = :newTitle, version = version + 1
WHERE id = :id
  AND tenant_id = :tenantId
  AND owner_id = :userId
  AND status = 'DRAFT'
  AND version = :expectedVersion;
```

Nếu số dòng cập nhật bằng 0, không tuyên bố đã sửa thành công. Phải xác định người dùng mất quyền, bản ghi đổi trạng thái hay phiên bản không còn đúng theo hợp đồng API; không retry vô hạn làm thay đổi ý định người dùng.

Một `@Transactional` không tự loại bỏ mọi race nếu mức cô lập hoặc điều kiện ghi không bảo đảm. Với side effect bên ngoài DB, cân nhắc idempotency/outbox nếu nghiệp vụ yêu cầu.

### 6.3. Tránh mass assignment

Nếu client gửi `tenantId`, `ownerId`, `approvedBy` hoặc `status`, đừng bind trực tiếp tất cả vào entity chỉ vì họ có quyền `document:update`. Dùng DTO có các trường được phép sửa và phương thức nghiệp vụ riêng cho việc chuyển trạng thái. Một người có quyền sửa nội dung chưa chắc có quyền thay chủ sở hữu hoặc tự duyệt.

## 7. Java 17 chạy độc lập: quyết định nhiều lớp bằng AND

Ví dụ nhỏ sau không phụ thuộc Spring. Nó cho thấy một request có thể được **HTTP cho phép** vì đúng authority nhưng **service từ chối** vì không phải owner, hoặc dữ liệu từ chối vì sai tenant.

Lưu file `LayeredAuthorizationDemo.java`:

```java
import java.util.Set;

public class LayeredAuthorizationDemo {
    enum Action { READ, UPDATE }
    enum Status { DRAFT, APPROVED }

    record Actor(long id, long tenantId, boolean active,
                 Set<String> authorities) {}

    record Document(long id, long tenantId, long ownerId,
                    Status status) {}

    static boolean httpAllowed(Actor actor, Action action) {
        if (actor == null || action == null || !actor.active()
                || actor.authorities() == null) {
            return false;
        }
        return switch (action) {
            case READ ->
                actor.authorities().contains("document:read");
            case UPDATE ->
                actor.authorities().contains("document:update");
        };
    }

    static boolean serviceAllowed(
            Actor actor, Action action, Document document) {
        if (actor == null || action == null || document == null) {
            return false;
        }
        boolean owner = actor.id() == document.ownerId();
        return switch (action) {
            case READ -> owner;
            case UPDATE ->
                owner && document.status() == Status.DRAFT;
        };
    }

    static boolean dataScopeAllowed(
            Actor actor, Document document) {
        return actor != null
            && document != null
            && actor.tenantId() == document.tenantId();
    }

    static boolean allowed(
            Actor actor, Action action, Document document) {
        return httpAllowed(actor, action)
            && serviceAllowed(actor, action, document)
            && dataScopeAllowed(actor, document);
    }

    static void show(String name, boolean result) {
        System.out.println(name + ": " + result);
    }

    public static void main(String[] args) {
        Actor alice = new Actor(
            10, 1, true,
            Set.of("document:read", "document:update")
        );
        Actor bob = new Actor(
            20, 1, true, Set.of("document:read")
        );
        Actor outsider = new Actor(
            30, 2, true, Set.of("document:read")
        );
        Actor inactive = new Actor(
            10, 1, false, Set.of("document:read")
        );

        Document draft = new Document(101, 1, 10, Status.DRAFT);
        Document approved = new Document(102, 1, 10, Status.APPROVED);
        Document outsiderDoc =
            new Document(103, 2, 30, Status.DRAFT);

        show("alice reads own",
            allowed(alice, Action.READ, draft));
        show("bob reads alice",
            allowed(bob, Action.READ, draft));
        show("other tenant reads alice",
            allowed(outsider, Action.READ, draft));
        show("alice edits draft",
            allowed(alice, Action.UPDATE, draft));
        show("alice edits approved",
            allowed(alice, Action.UPDATE, approved));
        show("bob edits draft",
            allowed(bob, Action.UPDATE, draft));
        show("inactive reads",
            allowed(inactive, Action.READ, draft));
        show("anonymous reads",
            allowed(null, Action.READ, draft));
        show("tenant two owner reads own",
            allowed(outsider, Action.READ, outsiderDoc));
        show("http allows bob read",
            httpAllowed(bob, Action.READ));
        show("service denies bob read",
            serviceAllowed(bob, Action.READ, draft));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac LayeredAuthorizationDemo.java
java LayeredAuthorizationDemo
```

Kết quả chuẩn:

```text
alice reads own: true
bob reads alice: false
other tenant reads alice: false
alice edits draft: true
alice edits approved: false
bob edits draft: false
inactive reads: false
anonymous reads: false
tenant two owner reads own: true
http allows bob read: true
service denies bob read: false
```

**Điểm đáng chú ý:** Bob có `document:read` nên được cho phép ở **lớp quyền chức năng**, nhưng không phải owner nên bị từ chối ở **lớp chính sách đối tượng**. Đây là kết quả nhất quán của một chính sách yêu cầu nhiều điều kiện, không phải lỗi vì hai lớp có kết quả khác nhau.

Chương trình này chỉ mô phỏng chính sách. Dữ liệu `Document` trong ứng dụng thật phải được tải từ server/repository đáng tin; không nhận các trường owner và tenant từ payload client rồi dùng làm căn cứ. Khi áp dụng vào DB, filter theo tenant cần diễn ra ngay trong truy vấn tương ứng.

## 8. Bảo vệ cả các đường ngoài HTTP

Một ứng dụng có thể có nhiều đường tới cùng hành động:

| Đường đi | Rủi ro khi chỉ có HTTP filter | Chốt cần thiết |
| --- | --- | --- |
| REST GET/PATCH/DELETE | URL/method chưa khai báo | Matcher và policy theo đối tượng |
| API tải file | URL download khác endpoint metadata | Quyền của file gắn với tài nguyên sở hữu |
| CSV/PDF export | Lọc đúng trên màn hình nhưng xuất toàn bộ DB | Query scope và kiểm tra quyền export |
| GraphQL resolver | Điểm vào khác REST | Quyền tại resolver/service/data |
| WebSocket message | Đã mở kết nối thì gửi mọi hành động | Kiểm tra từng message/action |
| Message consumer | Không qua `AuthorizationFilter` | Identity/service policy tại handler |
| `@Async` hoặc scheduled job | Không có cùng `SecurityContext` | Quyền máy/ủy quyền và context propagation rõ |
| RPC nội bộ | “Gọi từ bên trong” bị coi luôn đáng tin | Xác thực giữa dịch vụ và object policy |
| Admin script | Có thể ghi thẳng DB | Phạm vi DB, audit, quy trình vận hành |

Với Servlet, `SecurityContextHolder` thường dựa trên `ThreadLocal`. Không giả định rằng một tác vụ chạy trên luồng khác kế thừa principal; nếu phải truyền context, dùng cơ chế có kiểm soát và xác định thời hạn quyền. Một job chạy bằng service account cần permission tối thiểu cho nhiệm vụ đó.

Nếu hệ thống microservice phân quyền ở API gateway, dịch vụ phía sau vẫn phải tin cậy thông tin danh tính đúng cách và bảo vệ dữ liệu. Gateway không thể xác minh mọi owner/tenant/state nếu không có dữ liệu nghiệp vụ tương ứng; đồng thời các kênh nội bộ có thể đi vòng gateway.

## 9. Tránh mâu thuẫn bằng chính sách và quyền thống nhất

### 9.1. Catalog permission và mapping role

Ví dụ:

```text
ROLE_READER  -> document:read
ROLE_EDITOR  -> document:read, document:update
ROLE_APPROVER -> document:read, document:approve
```

Khi IdP gửi group/role, application mapper phải tạo ra `GrantedAuthority` đúng chuỗi. Trong quy ước Spring Security thông dụng, `hasRole("EDITOR")` kiểm tra authority `ROLE_EDITOR`; `hasAuthority("document:update")` so khớp đúng chuỗi `document:update`. Nếu các nơi dùng tên khác nhau mà không có bảng mapping, người dùng có thể bị deny không mong muốn hoặc được cấp nhầm quyền.

**Quyền có phạm vi** cũng phải được thể hiện rõ: editor của tenant A không tự động được sửa tài liệu tenant B. Authority chức năng chưa chứa đầy đủ quan hệ object, nên policy tenant/owner vẫn cần được đánh giá ở service/data.

### 9.2. Deny overrides không tự xuất hiện ở mọi nơi

Một thiết kế có thể quy định rằng deny bắt buộc (khác tenant, tài khoản khóa, trạng thái cấm) thắng một permit tổng quát. Nhưng Spring Security không tự lấy mọi kết quả ở mọi lớp rồi áp một bộ “deny overrides” toàn cục. Các authorization manager và cách kết hợp điều kiện là cấu hình cụ thể; request matchers thường **chọn** một rule, còn nhiều kiểm tra thuộc các ranh giới khác nhau có thể phải **cùng được thỏa**.

Nếu viết custom policy có nhiều nhánh, làm rõ khi nào dùng `AND` và khi nào dùng `OR`. Với trường hợp không đủ dữ liệu để đánh giá, không chuyển thành `ALLOW` theo suy đoán. Tách nhánh ngoại lệ (ví dụ temporary admin break-glass) thành chính sách được phê duyệt, có thời hạn và audit.

### 9.3. Nên chia logic đến đâu?

Giữ quy tắc URL/method ở HTTP; giữ quy tắc nhiệm vụ/đối tượng ở service hoặc policy bean; giữ phạm vi dữ liệu ở query. Khi một điều kiện object cần dùng từ nhiều nơi, viết thành policy có thể tái sử dụng, tránh sao chép khác nhau trong từng controller.

Với hành động nhạy cảm, điều kiện trạng thái có thể phải được bảo vệ bằng **câu lệnh ghi có điều kiện** dù đã kiểm tra ở policy. Đây là việc bảo vệ cùng một bất biến ở những thời điểm khác nhau, không phải viết thừa.

## 10. Kiểm thử có bằng chứng: lớp nào đã chặn?

### 10.1. Ma trận tối thiểu

| Ca thử | Lớp muốn chứng minh | Kỳ vọng |
| --- | --- | --- |
| User đủ permission, owner, đúng tenant, DRAFT | Toàn luồng | Cho phép thao tác hợp lệ |
| Thiếu permission | HTTP/method | Từ chối, không sửa DB |
| Có permission nhưng sai owner | Object/service | Từ chối, không trả dữ liệu |
| Có permission nhưng sai tenant | Repository/data | Từ chối, không lộ bản ghi |
| Có permission nhưng status APPROVED | Workflow/data | Không cho cập nhật |
| Chưa đăng nhập | Authentication | Không thực hiện thao tác bảo vệ |
| URL nằm ngoài `securityMatcher("/api/**")` | Chain selection | Fallback xử lý, không lọt qua |
| Hai chain cùng khớp | FilterChainProxy | Chọn đúng chain ưu tiên |
| Rule admin sau matcher quá rộng | HTTP rule order | Test phát hiện cấu hình mở quyền |
| Gọi service từ controller khác | Method security | Không bỏ qua quyền |
| Gọi nội bộ self-invocation | AOP boundary | Test phát hiện đường không qua proxy |
| Download/export | Object/data | Chỉ trả dữ liệu đúng phạm vi |
| Hai cập nhật đồng thời | Transaction/version | Không ghi dựa trên state cũ |
| Policy service lỗi | Fail closed | Không phát sinh side effect trái phép |

### 10.2. Unit test và integration test

- **Policy unit test:** cho actor, action và resource; kiểm tra điều kiện hợp lệ, thiếu dữ liệu, sai owner, sai tenant, quyền chia sẻ và chuyển trạng thái.
- **HTTP test bằng `MockMvc` và `spring-security-test`:** kiểm tra method/path/chain, principal, role prefix, response và tuyến mặc định từ chối.
- **Method security integration test:** gọi Spring bean qua proxy, xác nhận annotation thực thi; thêm ca gọi service từ điểm vào khác.
- **Repository test:** có ít nhất hai tenant và hai owner; query list/detail/export đều không trả bản ghi ngoài phạm vi.
- **Transaction/concurrency test:** dữ liệu thực hoặc DB test đủ giống sản xuất; kiểm tra version/conflict, không nhân đôi side effect.

Một đoạn gọi minh họa trong test có sẵn `mockMvc` và fixture:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// Trong phương thức @Test đã cấu hình MockMvc và fixture:
mockMvc.perform(patch("/api/documents/101")
        .with(user("alice").authorities(
            new SimpleGrantedAuthority("document:update")))
        .with(csrf())
        .contentType("application/json")
        .content("{\"title\":\"Updated\"}"))
    .andExpect(status().is2xxSuccessful());
```

Trong ví dụ, `SimpleGrantedAuthority` là `org.springframework.security.core.authority.SimpleGrantedAuthority`; response 2xx chỉ đúng nếu controller, fixture và trạng thái thật hợp lệ. Đây **không phải lớp Java độc lập**. Với POST/PATCH/DELETE, nếu CSRF bật, cần thêm token CSRF hợp lệ khi muốn test chính sách phân quyền; nếu không, 403 có thể chỉ do CSRF và không chứng minh rule owner/tenant đã chạy.

Ngoài mã HTTP, phải xác minh dữ liệu, số bản ghi, message/outbox và audit sau thao tác. Một test trả 403 mà dữ liệu đã bị cập nhật vẫn là thất bại bảo mật.

### 10.3. Chẩn đoán khi lớp này cho phép nhưng lớp kia từ chối

1. Xác nhận request đã khớp chain nào theo `securityMatcher` và `@Order`.
2. Xác nhận matcher nào trong `authorizeHttpRequests` được chọn.
3. Kiểm tra danh tính/authority thực của `Authentication`, gồm khác biệt `ROLE_` và tên permission.
4. Kiểm tra method security đã bật, lời gọi đi qua proxy và bean được Spring quản lý.
5. Kiểm tra tenant, owner, share grant, trạng thái và version của object từ dữ liệu server.
6. Kiểm tra điều kiện query/list/export, đừng chỉ dựa trên response của một endpoint.
7. Kiểm tra CSRF, authentication entry point, exception handler và token/session/cache.
8. Kiểm tra giao dịch có side effect hay không; dùng correlation ID để nối log.

Trong API, **401** thường biểu thị chưa xác thực, **403** thường biểu thị thiếu quyền (hoặc lỗi CSRF), **404** có thể được dùng để không lộ sự tồn tại của object, **409** có thể chỉ state/version conflict, còn lỗi hạ tầng có thể là **5xx**. Cần biết **lý do thật**; không dùng cùng một mã làm bằng chứng rằng mọi lớp đều hoạt động đúng.

## 11. Các lỗi phổ biến

| Lỗi | Hậu quả | Cách tránh |
| --- | --- | --- |
| Chỉ có chain cho `/api/**` | Đường ngoài API có thể không được bảo vệ | Chain fallback và test coverage |
| Chain ưu tiên cao match quá rộng | Chain sau không được chạy | Xác định matcher và thứ tự rõ |
| `authenticated()` đứng trước admin rule | User thường có thể qua route admin | Rule hẹp trước, default deny |
| Chỉ nhìn role/authority | Đổi ID để truy cập object khác | Tenant/owner/share/state policy |
| Gọi `findById(id)` rồi trả thẳng | IDOR/BOLA | Query có phạm vi |
| Gắn `@PreAuthorize` trên self-invocation | AOP không chạy | Ranh giới service/proxy đúng |
| Job gọi repository trực tiếp | Bỏ qua kiểm tra HTTP/service | Entry point bảo vệ ở nghiệp vụ |
| Hợp quyền bằng `OR` tùy tiện | Một nhánh yếu vượt điều kiện bắt buộc | AND/OR có ngoặc và test |
| Ghi sau khi check status cũ | TOCTOU và state corruption | Version/lock/conditional update |
| Test 403 nhưng quên CSRF | Chẩn đoán sai chính sách | Tách security/CSRF tests |
| Ánh xạ `ROLE_`/permission không nhất quán | Deny sai hoặc cấp quyền ngoài ý muốn | Catalog + mapping được review |
| Lỗi policy service thì cho qua | Lỗi hạ tầng tạo lỗ hổng | Fail closed |
| Lọc danh sách ở frontend | Có thể lộ toàn bộ dữ liệu | Enforce data scope ở server |

## 12. Bài tập thực hành

**Bài 1 — Vẽ bản đồ các điểm chặn.** Với một REST API đọc/sửa tài liệu, endpoint download và job export, hãy đánh dấu chỗ kiểm tra principal, permission, tenant, owner và trạng thái. Đạt khi không có đường nào đi tới dữ liệu nhạy cảm mà thiếu điều kiện bắt buộc.

**Bài 2 — Cấu hình hai chain.** Tạo API chain và fallback. Thử các request GET/PATCH/DELETE, endpoint public, URL chưa đăng ký và URL nằm ngoài `/api/**`. Cố tình đặt chain `/**` ưu tiên cao để xem test phát hiện lỗi.

**Bài 3 — Chạy Java 17.** Biên dịch `LayeredAuthorizationDemo.java`. Thêm một nhánh share grant cho READ mà không bỏ điều kiện tenant/authority. Viết các trường hợp owner đúng, sai owner, sai tenant, thiếu quyền và đã khóa.

**Bài 4 — Kiểm thử service.** Gắn `@PreAuthorize` trên service, bật method security; thử gọi qua Spring bean và qua self-invocation. Thiết kế lại để lời gọi nhạy cảm luôn qua ranh giới thực thi policy.

**Bài 5 — Tầng dữ liệu.** Viết truy vấn theo ID/tenant/owner, sau đó bổ sung optimistic locking hoặc UPDATE có `version`. Tạo hai request đồng thời, xác nhận không thể cập nhật tài liệu đã bị duyệt.

**Bài 6 — Kiểm thử hồi quy.** Khi thêm role mới có quyền đọc tài liệu chia sẻ, sửa ma trận quyền, mapper, policy, query và tests. Chạy lại các đường download/export/job để bảo đảm permission mới không làm lộ dữ liệu ngoài phạm vi.

## 13. Checklist trước khi triển khai

- [ ] Mỗi hành động nhạy cảm có chính sách actor/action/resource/context rõ.
- [ ] Mọi HTTP route được chain phù hợp bảo vệ; chain fallback đã kiểm tra.
- [ ] `securityMatcher`, `requestMatchers` và `@Order` có thứ tự đúng.
- [ ] Endpoint mới chưa khai báo bị từ chối mặc định.
- [ ] HTTP permission, role mapping và method permission thống nhất.
- [ ] Quy tắc object/tenant/owner/sharing được tái sử dụng ở nơi cần.
- [ ] Query list/detail/export/download giới hạn đúng tập dữ liệu.
- [ ] Không có lời gọi non-HTTP hoặc self-invocation bỏ qua policy.
- [ ] Trạng thái/phiên bản được kiểm tra tại lúc ghi, xử lý concurrency.
- [ ] DTO không cho client tự sửa tenant, owner, status hay trường nhạy cảm.
- [ ] Test gồm cả allow/deny, kiểm tra DB và side effect.
- [ ] Có log/audit nguyên nhân quyết định và quản lý thu hồi quyền.

## 14. Tự kiểm tra

1. **Hai `SecurityFilterChain` cùng match một request có chạy nối tiếp không?** Không; `FilterChainProxy` chọn chain phù hợp đầu tiên.
2. **`anyRequest().denyAll()` trong chain `/api/**` có chặn `/admin/export` không?** Không nếu request không vào chain; cần fallback hoặc cấu hình bao phủ.
3. **Có `document:read` nghĩa là được đọc ID của người khác?** Không; còn tenant/owner/share/state.
4. **HTTP cho phép nhưng object policy từ chối có phải mâu thuẫn?** Không nếu policy yêu cầu cả hai điều kiện.
5. **Vì sao self-invocation có nguy cơ?** Có thể không đi qua Spring AOP proxy nên annotation không chạy.
6. **Tại sao phải giới hạn truy vấn export?** HTTP chỉ quyết định có gọi endpoint, không tự lọc toàn bộ record.
7. **Vì sao version quan trọng khi cập nhật?** Để phát hiện trạng thái/dữ liệu đã đổi giữa kiểm tra và ghi.
8. **403 có đủ chứng minh object policy chặn đúng không?** Không; 403 có thể do CSRF hoặc matcher khác.
9. **Khi policy service lỗi, có thể tạm cho phép thao tác nhạy cảm?** Không; cần fail closed và trả lỗi phù hợp.
10. **Thêm endpoint mới phải làm gì?** Xem lại chính sách, chain coverage, method/object/data enforcement và tests.

**Ghi nhớ:** bảo vệ nhiều lớp hiệu quả không phải thêm nhiều annotation nhất. Hệ thống phải **bao phủ mọi đường truy cập**, **đặt từng điều kiện ở nơi đáng tin**, **diễn đạt rõ cách kết hợp quyết định**, và **kiểm thử rằng một đường được phép về mặt chức năng vẫn không thể vượt qua phạm vi đối tượng, trạng thái hay ràng buộc dữ liệu**.

### Tài liệu chính thức

- [Spring Security – Java Configuration và nhiều SecurityFilterChain](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Security – HTTP Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security – Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)