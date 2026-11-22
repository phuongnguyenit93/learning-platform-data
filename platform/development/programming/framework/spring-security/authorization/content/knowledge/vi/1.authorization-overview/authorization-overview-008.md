# Ranh giới giữa cơ chế Spring Security và chính sách nghiệp vụ

> **Bài học thuộc:** Spring Security - authorization → Bức tranh phân quyền.
>
> **Mục tiêu:** Sau bài này, bạn phân biệt được “Spring Security kiểm tra quyền bằng cơ chế nào?” với “nghiệp vụ quyết định ai được làm gì trên dữ liệu nào?”, đặt mỗi quyết định vào đúng tầng và kiểm chứng được rằng quyền ở URL hoặc role chung không vô tình mở quyền trên tài nguyên cụ thể.

## 1. Một yêu cầu, hai câu hỏi khác nhau

Giả sử ứng dụng quản lý tài liệu có API `PATCH /api/documents/42`. Người dùng Alice đăng nhập thành công và có quyền tổng quát `document:edit`. Alice có được sửa tài liệu 42 không?

**Chưa thể kết luận.** Quyền `document:edit` mới nói Alice có khả năng thực hiện loại thao tác “sửa tài liệu”; hệ thống còn phải biết tài liệu thuộc tổ chức nào, ai sở hữu, Alice có được ủy quyền trên tài liệu đó hay không và trạng thái tài liệu có cho phép thao tác này hay không.

Có ít nhất hai lớp quyết định:

1. **Cơ chế bảo mật (security mechanism):** nhận diện người gọi, lấy danh sách authority, chặn request hoặc method invocation theo luật đã cấu hình, báo lỗi từ chối truy cập và tích hợp các điểm kiểm tra.
2. **Chính sách phân quyền nghiệp vụ (business authorization policy):** xác định điều kiện cho phép *hành động cụ thể* trên *tài nguyên cụ thể* trong *bối cảnh cụ thể*: chủ sở hữu, tenant, quan hệ cộng tác, quyền phê duyệt, giai đoạn quy trình, quy tắc ngoại lệ được phê duyệt.

Spring Security cung cấp cả điểm thực thi và công cụ để tích hợp luật tùy biến (ví dụ `AuthorizationManager`, method security, `@PreAuthorize`). Điều đó **không** có nghĩa framework tự biết quy định “tài liệu đã duyệt thì chỉ bộ phận kiểm soát mới được mở khóa”. Luật đó phải được đội ứng dụng mô hình hóa rõ ràng.

Phân biệt thêm:

- **Authentication (xác thực):** “Người gọi là ai?”, bằng chứng đăng nhập/token có hợp lệ không.
- **Authorization (phân quyền):** “Người này có được thực hiện hành động này trên đối tượng này, trong bối cảnh này không?”.
- **Business invariant (bất biến nghiệp vụ):** “Thao tác có hợp lệ với trạng thái dữ liệu hay không, bất kể ai gọi?”. Ví dụ tổng tiền không được âm. Một điều kiện trạng thái có thể tham gia phân quyền nếu nó thay đổi *ai* được phép làm gì; nếu cấm tất cả mọi người như nhau thì thường thuộc kiểm tra nghiệp vụ chung.

## 2. Bản đồ trách nhiệm: tầng nào quyết định điều gì?

| Vấn đề | Spring Security / adapter bảo mật | Chính sách và dịch vụ nghiệp vụ |
| --- | --- | --- |
| Ai đang gọi? | Xác thực session, HTTP Basic, JWT hoặc cơ chế đã cấu hình; cung cấp `Authentication` | Chuyển danh tính tin cậy thành định danh actor/tenant của miền ứng dụng |
| Quyền tổng quát | Kiểm tra `hasAuthority`, `hasRole`, HTTP method, URL hoặc method | Xác định ý nghĩa `document:edit` trong bài toán tài liệu |
| Dữ liệu nào được truy cập? | Không tự biết bản ghi 42 thuộc ai | Nạp tài nguyên trong phạm vi tenant; kiểm tra owner, nhóm, ủy quyền, phạm vi dữ liệu |
| Ngữ cảnh nào được xét? | Cung cấp điểm gọi kiểm tra và dữ liệu bảo mật cần thiết | Xét trạng thái quy trình, quan hệ, tính hợp lệ thời điểm, quy tắc ngoại lệ |
| Khi từ chối? | Chặn bằng các cơ chế của Spring Security; điều phối lỗi bảo mật | Trả quyết định deny rõ ràng hoặc ném exception phù hợp với hợp đồng API |
| Ai kiểm soát thay đổi luật? | Cấu hình lớp chặn và đường đi tới luật | Product/domain owner xác nhận nội dung luật; đội phát triển lưu trong policy có kiểm thử |
| Chống lộ dữ liệu | Cấu hình đường truy cập, authentication/authorization ở biên | Giới hạn truy vấn, kiểm tra đối tượng trước khi tiết lộ, không lọc dữ liệu nhạy cảm chỉ ở UI |

**Nguyên tắc:** phần nào cần hiểu owner, tenant, quan hệ phê duyệt hoặc trạng thái thực thể thì phải được biểu diễn như luật nghiệp vụ; Spring Security có thể gọi luật đó tại một điểm thực thi thích hợp. “Dùng `@PreAuthorize`” là lựa chọn **cơ chế thực thi**, còn biểu thức hoặc service được gọi bên trong mới biểu diễn **nội dung chính sách**.

Một mô hình dễ dùng khi thiết kế là:

```text
Decision = Policy(actor, action, resource, context)
actor    = chủ thể đã xác thực và được ánh xạ sang danh tính miền ứng dụng
action   = hành động có nghĩa nghiệp vụ (view, edit, approve, refund, ...)
resource = đối tượng thật cần thao tác (Document #42, Order #81, ...)
context  = tenant, quan hệ, trạng thái, thời điểm và dữ kiện liên quan
```

Không nên giản lược quyết định trên tài nguyên thành duy nhất `Policy(role)` hoặc `Policy(URL)`.

## 3. Dòng chảy kiểm tra trong ứng dụng Servlet

```text
HTTP request
   |
   v
Spring Security filter chain
   |-- xác thực người gọi (nếu tuyến đó yêu cầu)
   |-- luật HTTP: chặn request không hợp lệ hoặc thiếu quyền khái quát
   v
Controller nhận request (chỉ dữ liệu đầu vào chưa tin cậy)
   |
   v
Application service / use case
   |-- lấy actor tin cậy từ security adapter
   |-- truy vấn dữ liệu trong phạm vi tenant hợp lệ
   |-- áp dụng domain authorization policy(actor, action, resource, context)
   |-- kiểm tra các bất biến nghiệp vụ khác
   v
Thực hiện nghiệp vụ / lưu dữ liệu / trả kết quả
```

Với Servlet, `AuthorizationFilter` dùng `AuthorizationManager` để kiểm tra request. Nếu từ chối, Spring Security có thể đưa ra `AccessDeniedException` và cơ chế xử lý exception chuyển thành phản hồi thích hợp với cách xác thực đã cấu hình. Method security thêm một điểm chặn tại lời gọi method của Spring-managed bean khi được bật.

Cả hai tầng đều có giá trị:

- **HTTP-level:** chặn sớm và có chi phí thấp các tuyến công khai/nội bộ, HTTP method, quyền rộng. Ví dụ người không có `document:edit` không thể đi vào endpoint sửa.
- **Method-level:** kiểm soát lời gọi use case/service kể cả khi logic được gọi từ nhiều endpoint; có thể gọi policy bean.
- **Domain/application-level:** kiểm tra sau khi biết thực thể thật và bối cảnh; dùng chung với tiến trình batch, message consumer hoặc các entry point không đi qua HTTP.

Các lớp có thể kết hợp, nhưng không được giả định chỉ bật `@EnableMethodSecurity` là tất cả service tự được bảo vệ: ứng dụng phải gắn luật lên method hoặc thiết lập advisor/manager phù hợp. Spring Boot Starter Security không tự bật method-level authorization.

## 4. Cấu hình HTTP là “cửa vào”, không phải luật sở hữu

Ví dụ dưới đây minh họa **một phần cấu hình** Spring Boot 3 / Spring Security 6 (Servlet). Ứng dụng phải tự cấu hình cơ chế xác thực thực tế và các bean cần thiết; đoạn này không phải ứng dụng độc lập chạy ngay.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
class SecurityConfig {

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/public/**").permitAll()
            .requestMatchers(HttpMethod.GET, "/api/documents/**")
                .hasAuthority("document:read")
            .requestMatchers(HttpMethod.PATCH, "/api/documents/**")
                .hasAuthority("document:edit")
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
```

Ý nghĩa:

- Luật trên HTTP method + URL là **điều kiện đầu vào**, ví dụ Alice cần `document:edit` để gửi PATCH.
- Luật đó **chưa xác định** Alice có được sửa tài liệu `42` không.
- `anyRequest().denyAll()` ngăn tuyến không khai báo vô tình được phép; chỉ cấp quyền công khai cho tuyến được thiết kế công khai.
- Trong cùng một `authorizeHttpRequests`, **thứ tự matcher quan trọng**: luật khớp đầu tiên được áp dụng. Không đặt `/api/**.authenticated()` trước luật cụ thể rồi kỳ vọng các luật sau được chạy.
- `hasRole("EDITOR")` thông thường kiểm tra authority với tiền tố `ROLE_`; `hasAuthority("document:edit")` kiểm tra authority đúng chuỗi. Cách ánh xạ role, scope JWT và permission phải được định nghĩa nhất quán, không suy đoán chỉ từ tên.
- Quyền HTTP không tự xử lý CSRF, cách xác thực hoặc token; với endpoint thay đổi trạng thái trên ứng dụng dùng session/cookie cần xem xét CSRF đúng kiến trúc. Không tắt CSRF chỉ để ví dụ PATCH chạy được.

Lỗi thiết kế thường gặp: mở `/api/documents/**` cho mọi user đã đăng nhập và cho rằng chỉ vì ID tài liệu khó đoán nên người khác không truy cập được. Đây là nguy cơ **Broken Object Level Authorization (BOLA/IDOR)**: attacker đổi `42` thành ID tài liệu khác và kiểm tra thiếu ở tầng dữ liệu sẽ cho phép vượt quyền.

## 5. Policy nghiệp vụ phải nhận đủ actor, action, resource và context

Giả sử quy tắc sửa tiêu đề tài liệu là:

1. Người gọi có permission `document:edit`.
2. Người gọi và tài liệu cùng tenant.
3. Người gọi là owner (hoặc người được chia sẻ quyền edit theo chính sách đã thống nhất).
4. Tài liệu còn ở trạng thái `DRAFT`; riêng thao tác mở khóa hoặc sửa bản đã duyệt là **use case khác** có quyền và quy trình riêng.

Nếu chỉ dùng `hasAuthority("document:edit")` thì các điều kiện 2–4 bị bỏ qua. Nếu chỉ so sánh owner thì lại bỏ qua permission và tenant. Phải xét tất cả điều kiện liên quan; trong trường hợp thiếu dữ liệu hoặc không kiểm chứng được quyền, hãy **từ chối theo mặc định**.

Đoạn Java 17+ dưới đây **chạy độc lập**, minh họa policy tối giản. Ví dụ cố ý chỉ cho owner sửa; quy tắc chia sẻ có thể mở rộng thành một quan hệ riêng, không nên thêm điều kiện “admin thì luôn được” theo suy đoán.

```java
import java.util.Set;

public class PolicyBoundaryDemo {

    record Actor(String userId, String tenantId, Set<String> permissions) {
        boolean hasPermission(String permission) {
            return permissions.contains(permission);
        }
    }

    record Document(String ownerId, String tenantId, String status) {}

    static boolean mayEdit(Actor actor, Document document) {
        return actor.hasPermission("document:edit")
            && actor.tenantId().equals(document.tenantId())
            && actor.userId().equals(document.ownerId())
            && "DRAFT".equals(document.status());
    }

    public static void main(String[] args) {
        Actor alice = new Actor(
            "alice", "shop-a", Set.of("document:edit"));

        System.out.println("own draft: " +
            mayEdit(alice, new Document("alice", "shop-a", "DRAFT")));
        System.out.println("other owner: " +
            mayEdit(alice, new Document("bob", "shop-a", "DRAFT")));
        System.out.println("other tenant: " +
            mayEdit(alice, new Document("alice", "shop-b", "DRAFT")));
        System.out.println("approved: " +
            mayEdit(alice, new Document("alice", "shop-a", "APPROVED")));
    }
}
```

Lưu thành `PolicyBoundaryDemo.java` rồi chạy:

```bash
javac PolicyBoundaryDemo.java
java PolicyBoundaryDemo
```

Kết quả chuẩn:

```text
own draft: true
other owner: false
other tenant: false
approved: false
```

Bài học chính: **cùng Alice, cùng authority, kết quả khác nhau vì tài nguyên và bối cảnh khác nhau**. Trên hệ thống thật, actor và tài liệu phải được lấy từ nguồn đáng tin; ví dụ độc lập này chỉ kiểm tra cách ra quyết định, không bao gồm xác thực, database hoặc HTTP.

## 6. Đặt policy ở đâu trong dự án thực tế?

Có hai cách phổ biến, có thể kết hợp khi giữ một nguồn sự thật cho luật.

### Cách A — Service nạp dữ liệu rồi gọi policy

Đây thường là lựa chọn rõ ràng khi cần dữ liệu thực thể, tenant, quan hệ giữa nhiều bản ghi và transaction.

```java
// Mã minh họa cấu trúc: các kiểu Document, Actor, repository,
// DocumentPolicy và exception do ứng dụng định nghĩa.
@Service
class DocumentService {
    private final DocumentRepository repository;
    private final DocumentPolicy policy;

    DocumentService(DocumentRepository repository, DocumentPolicy policy) {
        this.repository = repository;
        this.policy = policy;
    }

    @Transactional
    @PreAuthorize("hasAuthority('document:edit')")
    public void rename(UUID documentId, String title, Actor actor) {
        Document document = repository
            .findByIdAndTenantId(documentId, actor.tenantId())
            .orElseThrow(() -> new DocumentNotFoundException(documentId));

        if (!policy.mayRename(actor, document)) {
            throw new AccessDeniedException("Rename not allowed");
        }

        document.rename(title); // Document tự bảo vệ bất biến miền.
    }
}
```

Trong mẫu này:

- `@PreAuthorize` chặn sớm khi không có permission tổng quát.
- `findByIdAndTenantId` giới hạn truy vấn theo tenant **đã xác thực**, thay vì tải bất cứ bản ghi nào rồi vô tình trả dữ liệu cho tenant khác.
- `DocumentPolicy` là nơi diễn đạt điều kiện owner, cộng tác, trạng thái. Có thể kiểm thử độc lập mà không khởi động web server.
- `document.rename(...)` chịu trách nhiệm bất biến miền, như title hợp lệ hoặc chuyển trạng thái được cho phép. Không đặt mọi validation vào policy phân quyền.
- `@Transactional` giúp đọc, kiểm tra và cập nhật trong cùng transaction; với cạnh tranh cập nhật cần thêm optimistic/pessimistic locking tùy nghiệp vụ, vì transaction đơn thuần không tự giải quyết mọi race.
- Tham số `Actor` phải được **server** lấy từ danh tính đã xác thực/mapper đáng tin rồi truyền vào service; không nhận actor, user ID hay tenant ID như dữ liệu mà client tùy ý khai báo.

Đây là snippet tích hợp, **không phải file Java đứng riêng**: để biên dịch cần ứng dụng Spring và các class miền tương ứng. Import Spring điển hình bao gồm `@Service`, `@Transactional`, `@PreAuthorize` và `AccessDeniedException`.

### Cách B — Method security gọi bean policy

Khi điểm chặn thích hợp đã có đầy đủ dữ kiện và cần tái sử dụng luật tại nhiều method:

```java
@PreAuthorize("@documentAccess.canEdit(authentication, #documentId)")
public void editDocument(UUID documentId, EditCommand command) {
    // Xử lý sau khi authorization thành công.
}
```

Trong đó `documentAccess` là Spring bean do ứng dụng viết; nó ánh xạ `authentication` thành actor tin cậy, truy vấn/kiểm tra tài nguyên và trả boolean. Cần bật `@EnableMethodSecurity` để áp dụng annotation.

**Cân nhắc quan trọng:** Nếu bean policy đã truy vấn tài liệu rồi service lại truy vấn lần nữa, bạn có nguy cơ kiểm tra trên bản dữ liệu khác với bản được sửa (race/time-of-check-time-of-use), tăng I/O hoặc làm luật bị rải ở nhiều nơi. Có thể chọn service guard trong cùng transaction như Cách A, hoặc thiết kế pre-authorization có kiểm soát và nhất quán. Tránh ẩn các truy vấn nghiệp vụ phức tạp trong biểu thức SpEL dài khó test.

**Cảnh báo về proxy:** Method security trong Spring thường hoạt động qua AOP interceptor/proxy. Lời gọi nội bộ từ một method của bean tới method khác trên chính đối tượng đó (`this.method()`) có thể bỏ qua proxy và do đó không chạy `@PreAuthorize` trên method đích. Nếu tính toàn vẹn luật phụ thuộc vào lời gọi này, đưa guard vào service use case luôn được thực thi hoặc tổ chức lời gọi qua bean khác có proxy phù hợp. Đồng thời các job, consumer hay CLI không đi qua servlet filter vẫn phải được kiểm tra ở điểm use case thích hợp.

## 7. Định danh tin cậy: tuyệt đối không suy ra quyền từ dữ liệu client

Một request có thể mang `documentId`, `tenantId`, `ownerId` hoặc `role`. Đây là **đầu vào chưa tin cậy** cho đến khi được đối chiếu:

- `documentId` giúp tìm resource; tự nó không chứng minh quyền đối với resource.
- `ownerId` gửi trong JSON không quyết định ai là chủ sở hữu; lấy thông tin owner từ dữ liệu phía server.
- `tenantId` trên URL/header chỉ được dùng làm ngữ cảnh lựa chọn **sau khi** xác minh actor thực sự có quyền trên tenant đó. Với multi-tenant, chỉ kiểm tra owner ID mà bỏ tenant vẫn có thể rò chéo tổ chức.
- Role/authority phải đến từ nguồn xác thực/ủy quyền được xác minh (SecurityContext, token đã kiểm tra chữ ký/issuer/audience theo cấu hình, kho quyền server), không tin lời client tự khai “admin=true”.
- Với actor thực tế, tách `subjectId` ổn định khỏi tên hiển thị/email có thể đổi; nếu làm việc cho tổ chức thay mặt người khác, diễn đạt cả actor, represented organization và quyền ủy nhiệm thay vì bỏ mất ngữ cảnh.

Nhiều tổ chức chọn mapper như `AuthenticatedActorResolver` để chuyển `Authentication` thành `Actor` đúng miền ứng dụng. Domain policy sau đó chỉ nhận `Actor`; nhờ vậy logic không cần biết actor đến từ session, JWT, mTLS hay một security adapter khác.

## 8. Đừng đánh đồng ba loại quy tắc

Ví dụ tài liệu vừa được duyệt:

| Quy tắc | Bản chất | Nên kiểm tra ở đâu? |
| --- | --- | --- |
| Chỉ user có `document:edit` được gọi API sửa | Quyền chức năng tổng quát | HTTP và/hoặc method |
| Chỉ owner hoặc editor được phân công sửa tài liệu thuộc cùng tenant | Phân quyền theo tài nguyên | Application/domain policy |
| Tài liệu ở `APPROVED` không được sửa trực tiếp; chỉ workflow `revise` tạo bản mới | Bất biến/chính sách vòng đời nghiệp vụ | Domain service và entity invariant |
| Chỉ reviewer được approve bản `SUBMITTED`, và không được tự approve tài liệu của mình | Phân quyền phụ thuộc trạng thái, quan hệ và tách nhiệm vụ | Domain policy + domain invariant |

Khi một điều kiện trạng thái quyết định *người nào* được thao tác, nó là một phần của authorization policy; khi nó quyết định *thao tác vốn không hợp lệ* với mọi người, đó thường là invariant. Quy tắc có thể liên hệ nhau, nhưng cần diễn đạt rõ ràng để dùng đúng response code và kiểm thử đúng nguyên nhân thất bại.

Không dùng “ADMIN bypass tất cả” làm mặc định. Nếu có bypass khẩn cấp, chính sách cần quy định chính xác actor nào, phạm vi nào, lý do, thời hạn, bước phê duyệt và audit bắt buộc.

## 9. Từ chối truy cập và ý nghĩa của 401, 403, 404

Một số kết quả HTTP thường gặp trong REST API:

- **401 Unauthorized:** request cần xác thực nhưng chưa có credential hợp lệ theo cơ chế của API (dù tên là “Unauthorized”, ý nghĩa thường là chưa xác thực).
- **403 Forbidden:** danh tính đã được xác thực nhưng không được phép thực hiện hành động. `AccessDeniedException` thường được chuyển qua handler trong Spring Security; ứng dụng cần mapping rõ ràng nếu exception phát sinh từ domain/application service.
- **404 Not Found:** resource không tồn tại; trong hệ thống multi-tenant đôi khi dùng cùng phản hồi 404 cho “không tồn tại hoặc không nhìn thấy” để tránh tiết lộ sự hiện diện của tài nguyên. Đây là quyết định contract và chống lộ thông tin, không nên biến ngẫu nhiên tất cả deny thành 404.
- **409 Conflict / 422 theo contract:** thao tác trái trạng thái hoặc invariant nghiệp vụ, *nếu người gọi vốn có quyền thực hiện hành động*; không dùng response conflict thay cho lỗi thiếu quyền.

Spring Security có `AuthenticationEntryPoint` và `AccessDeniedHandler` để xử lý các nhánh lỗi bảo mật. Phản hồi thực tế phụ thuộc kiểu ứng dụng, cơ chế xác thực và exception handling đã cấu hình; không giả định mọi ứng dụng luôn trả cùng JSON/body.

Một thứ tự an toàn thường là: xác thực → xác định actor và phạm vi truy cập → tìm tài nguyên trong phạm vi hợp lệ → kiểm tra policy → kiểm tra invariant nghiệp vụ → cập nhật. Đừng trả nội dung, metadata nhạy cảm hoặc thông điệp chi tiết của tài nguyên trước khi kiểm tra quyền.

## 10. Kiểm soát quyền ngay cả khi truy vấn danh sách

Không chỉ endpoint `GET /documents/{id}` mới cần authorization; endpoint `GET /documents` có thể lộ **hàng trăm bản ghi** nếu chỉ kiểm tra `hasAuthority("document:read")` mà query bỏ điều kiện tenant/visibility.

Cách tiếp cận:

1. Ở biên, kiểm tra khả năng gọi chức năng đọc.
2. Xây predicate/truy vấn dựa trên actor đáng tin: tenant, owner, group membership, sharing rule.
3. Thực hiện lọc ở database khi có thể, có index thích hợp và tính nhất quán với policy kiểm tra một bản ghi.
4. Với API phân trang, lọc trước khi `LIMIT/OFFSET` để không đưa dữ liệu ngoài quyền vào kết quả hoặc làm sai paging/count.
5. Không tải toàn bộ dữ liệu nhạy cảm rồi lọc ở frontend; cũng không xem `@PostFilter` trên tập lớn là thay thế mặc định cho truy vấn an toàn.

Đối với update/delete, cân nhắc repository query có scope theo actor và dùng version check hoặc khóa khi điều kiện có thể thay đổi đồng thời. Chính sách cần thống nhất giữa xem danh sách, xem chi tiết, sửa và export; tránh cho phép export dữ liệu mà màn hình danh sách đã chặn.

## 11. Những lỗi thiết kế có thể dẫn đến vượt quyền

| Sai lầm | Hệ quả | Sửa bằng cách |
| --- | --- | --- |
| “Đã login thì xem được mọi ID” | IDOR/BOLA | Policy theo object + tenant + kiểm tra ở service/repository |
| “Role=MANAGER là toàn quyền” | Lộ dữ liệu ngoài tổ chức hoặc vượt workflow | Giới hạn permission, resource scope và ngoại lệ theo domain |
| Tin `ownerId`/`tenantId` từ body/header | Giả mạo chủ thể hoặc phạm vi | Actor từ nguồn tin cậy; đối chiếu tài nguyên server-side |
| Chỉ guard tại Controller | Batch job, event listener, service tái sử dụng có thể bypass | Guard tại use case/service và điểm vào bổ sung |
| Chỉ gắn `@PreAuthorize` ở method tự gọi nội bộ | AOP self-invocation có thể bỏ qua kiểm tra | Thiết kế lời gọi qua proxy phù hợp hoặc policy guard luôn được chạy |
| Luật nằm trong SpEL dài, controller, repository và UI với các biến thể khác nhau | Chính sách lệch nhau, khó audit | Một policy có tên, test rõ ràng, adapter mỏng |
| Check dữ liệu một lần rồi dùng bản mới không kiểm soát | Race/TOCTOU, thao tác sai trạng thái | Transaction, query scoped, version/locking phù hợp |
| Lọc kết quả sau khi đã trả hoặc ở browser | Rò thông tin, count/paging sai | Lọc từ truy vấn và kiểm soát từng operation |
| Dùng `permitAll` để né lỗi cấu hình | Endpoint quan trọng trở thành công khai | Xác định lý do lỗi, đặt matcher có chủ đích, deny theo mặc định |
| Xử lý mọi lỗi thành 403 | Che mất lỗi xác thực, dữ liệu không tồn tại hoặc validation | Phân loại authentication, authorization, resource và invariant |

Đặc biệt, `permitAll` chỉ cho phép request qua **bước authorization tương ứng**; nó không đồng nghĩa tắt mọi filter hoặc vô hiệu hóa các kiểm tra nghiệp vụ ở sau. Tương tự, endpoint được bảo vệ bởi URL matcher vẫn cần policy trên dữ liệu khi có tham số ID.

## 12. Tổ chức code để luật có thể thay đổi mà không phá cơ chế

Một cấu trúc tham khảo:

```text
security/
  SecurityConfig                 # endpoint guard, filter chain, method security
  AuthenticatedActorResolver    # Authentication -> Actor tin cậy
document/
  application/
    DocumentService             # load/scoping, policy check, transaction
  domain/
    Document
    DocumentPolicy              # canView, canRename, canApprove...
  persistence/
    DocumentRepository          # query theo tenant/visibility
```

Đây là sơ đồ trách nhiệm, không phải cấu trúc package bắt buộc.

Một policy tốt nên có các đặc điểm:

- Có tên thể hiện hành động: `canApproveInvoice` rõ hơn `checkPermission`.
- Đầu vào thể hiện đủ actor/action/resource/context, không đọc trực tiếp request toàn cục nếu không cần.
- Quyết định deny khi thiếu quan hệ hoặc dữ kiện bắt buộc; trường hợp “không tải được policy” không mặc nhiên allow.
- Tách chức năng thu thập dữ liệu và quyết định, nhất là khi muốn unit test thuần Java.
- Được các entry point gọi thống nhất; ownership của luật nằm ở miền nghiệp vụ.
- Ghi nhận audit phù hợp (ai, hành động, tài nguyên, kết quả, lý do ở mức an toàn); không ghi token, mật khẩu hoặc dữ liệu nhạy cảm vào log.
- Khi luật thay đổi, sửa test ma trận và contract trước hoặc cùng lúc với triển khai.

Spring Security không bị giới hạn ở role check: `AuthorizationManager` cho phép cắm chính sách tùy biến vào request/method authorization. Tuy nhiên đừng biến cơ chế framework thành nơi giữ toàn bộ trạng thái nghiệp vụ; policy vẫn nên có API và kiểm thử độc lập.

## 13. Bảng quyết định và chiến lược kiểm thử

Ví dụ với luật “owner có `document:edit` được sửa bản nháp cùng tenant”:

| Actor có permission | Cùng tenant | Là owner | Trạng thái | Kỳ vọng |
| --- | --- | --- | --- | --- |
| Có | Có | Có | DRAFT | ALLOW |
| Không | Có | Có | DRAFT | DENY |
| Có | Không | Có | DRAFT | DENY |
| Có | Có | Không | DRAFT | DENY |
| Có | Có | Có | APPROVED | DENY |
| Chưa xác thực | — | — | DRAFT | Bị chặn ở lớp xác thực trước khi vào policy |

Cần kiểm thử ít nhất ba nhóm:

1. **Unit test policy:** tất cả nhánh allow/deny, tenant chéo, owner khác, permission thiếu, trạng thái khác, dữ kiện null/thiếu (theo contract). Đây là nhóm có giá trị cao và chạy nhanh.
2. **Integration test method/service:** bật `@EnableMethodSecurity`, kiểm tra method guard thực sự áp dụng qua proxy, use case không bypass bằng alternate entry point, repository scoped đúng tenant, transaction/version xử lý race quan trọng.
3. **HTTP security test:** với MockMvc hoặc integration test tương ứng, kiểm tra anonymous/authenticated, HTTP method + URL, 401/403/404 theo contract, thứ tự matcher, request có/không có CSRF token khi áp dụng, và mapping principal/token sang Actor.

Lưu ý kiểm thử âm tính phải xác nhận **đúng nguyên nhân từ chối**. Ví dụ test “không được PATCH vì không phải owner” có thể vô tình nhận 403 do thiếu CSRF token; nếu chỉ assert HTTP 403 thì test chưa chứng minh policy owner hoạt động. Dùng fixture có credential/CSRF hợp lệ rồi chỉ thay owner/tenant/status, đồng thời xác nhận bản ghi không bị thay đổi.

Một bài tự đánh giá: “Người dùng có `document:edit`, là owner của tài liệu nhưng tài liệu nằm ở tenant mà người đó không còn là thành viên. Có được sửa không?” — **Không**; ownership đơn lẻ không thay thế kiểm tra phạm vi tổ chức. Tiếp theo: “API đọc tài liệu trả 404 thay vì 403 khi không thấy tài liệu của tenant khác; vậy có cần policy không?” — **Vẫn cần**; cách trình bày response không thay thế điều kiện giới hạn truy cập ở database/service.

## 14. Checklist khi thêm một use case mới

1. Mô tả hành động bằng ngôn ngữ miền nghiệp vụ: xem, chỉnh sửa, phê duyệt, hoàn tiền, phân công.
2. Xác định actor/tenant từ nguồn tin cậy, resource thật và mọi quan hệ cần truy vấn.
3. Viết câu cho phép chính xác: **ai**, **được làm gì**, **trên bản ghi nào**, **khi nào**, và **ngoại lệ nào**.
4. Chọn điểm chặn đầu vào bằng HTTP/method guard, rồi áp dụng domain policy tại nơi có dữ liệu đúng.
5. Tách điều kiện thiếu quyền khỏi điều kiện thao tác vô hiệu về nghiệp vụ; quy định lỗi trả về để không lộ thông tin.
6. Áp dụng cho cả list/detail/export/background operations và giao dịch đồng thời.
7. Lập ma trận allow/deny và kiểm thử đường âm tính có chủ đích trước khi công bố endpoint.

**Tư duy cốt lõi:** Spring Security đảm nhiệm hạ tầng xác thực, luồng kiểm tra và chặn truy cập; **ứng dụng phải quyết định nội dung quyền dựa trên người gọi, hành động, tài nguyên và ngữ cảnh nghiệp vụ**. Đặt các quyết định này vào một policy rõ ràng, thực thi ở mọi entry point và kiểm thử từng điều kiện, bạn sẽ tránh được phần lớn lỗi “đã có role nhưng vẫn truy cập sai tài nguyên”.

## Tài liệu đọc tiếp

- [Spring Security — Authorization (tổng quan)](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/index.html)
- [Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html)
- [Servlet Architecture — Handling Security Exceptions](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
