# Phân quyền ở mức HTTP, phương thức và từng đối tượng dữ liệu

## Mục tiêu học tập

Sau bài này, bạn có thể phân biệt ba nơi đặt chính sách phân quyền trong ứng dụng Spring Security trên Servlet stack; biết mỗi tầng quyết định điều gì, kết hợp chúng như thế nào và vì sao kiểm tra quyền truy cập một URL vẫn chưa đủ để bảo vệ một bản ghi cụ thể. Ví dụ xuyên suốt là API quản lý tài liệu: người dùng có quyền đọc/sửa tài liệu nói chung, nhưng chỉ được thao tác với tài liệu thuộc quyền sở hữu hoặc được chia sẻ cho mình.

## 1. Phân quyền kiểm tra điều gì?

**Authentication** xác định người gọi là ai; **authorization** xác định người gọi có được thực hiện một hành động lên một tài nguyên cụ thể hay không. Trong Spring Security, `Authentication` thường giữ danh tính (`principal`), trạng thái xác thực và các `GrantedAuthority` như `ROLE_ADMIN` hoặc `doc:read`. Một người đã đăng nhập chưa đương nhiên được phép truy cập mọi tài liệu.

Một quyết định phân quyền có thể phụ thuộc đồng thời vào:

- **Chủ thể**: người dùng hiện tại, vai trò, authority, tenant, nhóm.
- **Hành động**: đọc, tạo, sửa, xóa, phê duyệt.
- **Tài nguyên**: API, nghiệp vụ, tài liệu có `id=42` và chủ sở hữu `alice`.
- **Bối cảnh**: thời điểm, trạng thái tài liệu, quan hệ chia sẻ, quy định của tổ chức.

Ví dụ, `bob` có authority `doc:edit` nhưng tài liệu 42 thuộc `alice` và không cho phép người khác chỉnh sửa: yêu cầu đổi tên tài liệu 42 **phải bị từ chối**. Authority chỉ thể hiện quyền ở mức chức năng; quyền với từng đối tượng còn cần điều kiện riêng.

### Ba tầng nên phối hợp

| Tầng | Điểm kiểm soát | Ví dụ câu hỏi | Điểm mạnh | Giới hạn |
| --- | --- | --- | --- | --- |
| HTTP/request | `SecurityFilterChain` và `authorizeHttpRequests` | `PATCH /api/documents/42` có cần `doc:edit` không? | Chặn sớm theo URL, HTTP method và quyền tổng quát | Không tự biết ai sở hữu bản ghi 42 |
| Phương thức/nghiệp vụ | `@PreAuthorize`, `@PostAuthorize` trên Spring bean | Ai được gọi `DocumentService.rename(42, ...)`? | Bảo vệ nghiệp vụ cả khi gọi từ controller, message consumer hay thành phần khác | Cần bật method security và đi qua Spring AOP proxy |
| Từng đối tượng dữ liệu | Chính sách owner/tenant/ACL, query có ràng buộc | Bản ghi 42 có thuộc tenant và quyền của người này không? | Ngăn truy cập chéo dữ liệu, kể cả khi cùng một API | Phải kiểm tra theo dữ liệu đáng tin ở server, kể cả truy vấn danh sách |

Luồng điển hình: **request → xác thực → luật HTTP → controller → luật method → truy vấn/đánh giá quyền trên bản ghi → nghiệp vụ/response**. Một request hợp lệ phải qua *tất cả* các cổng áp dụng. Tách các tầng giúp dễ bảo trì; chúng bổ sung cho nhau chứ không thay thế nhau.

## 2. Phân quyền ở mức HTTP

Trong ứng dụng Spring MVC/Spring Boot dùng Spring Security 6.x, khai báo luật truy cập với `SecurityFilterChain` và `authorizeHttpRequests`. Ví dụ đầy đủ cho lớp cấu hình; cần dependency `spring-boot-starter-security` cùng nguồn người dùng/xác thực do ứng dụng cung cấp:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/actuator/health").permitAll()
            .requestMatchers(HttpMethod.GET, "/api/documents/**")
                .hasAuthority("doc:read")
            .requestMatchers(HttpMethod.POST, "/api/documents")
                .hasAuthority("doc:create")
            .requestMatchers(HttpMethod.PATCH, "/api/documents/**")
                .hasAuthority("doc:edit")
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().denyAll()
        );
        http.httpBasic(Customizer.withDefaults()); // Xác thực minh họa
        return http.build();
    }
}
```

**Đọc cấu hình:**

1. `/actuator/health` công khai. Với `GET /api/documents/42`, người gọi cần đúng authority `doc:read`; với `PATCH` cùng URL, cần `doc:edit`.
2. `hasRole("ADMIN")` theo quy ước thông thường kiểm tra authority `ROLE_ADMIN`. Còn `hasAuthority("doc:read")` kiểm tra **chuỗi chính xác** `doc:read`; không tự thêm tiền tố.
3. Luật `requestMatchers` được xét **theo thứ tự**, luật đầu tiên khớp sẽ quyết định ở tầng HTTP; đặt trường hợp cụ thể trước trường hợp bao quát. `anyRequest().denyAll()` từ chối endpoint chưa khai báo: mặc định đóng.
4. `@EnableMethodSecurity` trong ví dụ bật xử lý `@PreAuthorize`/`@PostAuthorize`; chỉ thêm starter Security chưa tự bật tính năng này.

`httpBasic` chỉ dùng để giúp minh họa lớp kiểm tra quyền, không quyết định mô hình xác thực của hệ thống. API production có thể dùng session hoặc OAuth2 Resource Server/JWT và phải cấu hình nguồn `Authentication`, ánh xạ authorities phù hợp. Nếu dùng HTTP Basic/cookie với request thay đổi dữ liệu, **CSRF vẫn là một kiểm soát riêng**: `PATCH` có thể bị 403 do thiếu CSRF token ngay cả khi có đủ authority. Không tắt CSRF chỉ để ví dụ chạy; chọn cấu hình theo loại ứng dụng và mối đe dọa thực tế.

**Điều HTTP không giải quyết:** cả `alice` và `bob` có `doc:read` đều được qua luật `GET /api/documents/42`, nhưng chỉ bản ghi và quy tắc chia sẻ mới quyết định `bob` có thực sự đọc được tài liệu 42 không. Không được xem việc khớp URL là bằng chứng sở hữu tài liệu.

## 3. Phân quyền ở mức phương thức

Method security bảo vệ điểm vào nghiệp vụ bằng Spring AOP. `@PreAuthorize` đánh giá biểu thức **trước** khi chạy method; `@PostAuthorize` đánh giá kết quả **sau** khi method trả về. Các biểu thức thường dùng:

| Biểu thức | Ý nghĩa |
| --- | --- |
| `hasAuthority('doc:read')` | Có đúng authority `doc:read` |
| `hasRole('ADMIN')` | Có role tương ứng `ROLE_ADMIN` theo tiền tố mặc định |
| `authentication.name` | Tên/định danh của người đã xác thực do cơ chế xác thực cung cấp |
| `#id` | Đối số method tên `id` (cần metadata tên tham số hoặc annotation `@P`) |
| `@documentAccess.canEdit(authentication, #id)` | Gọi bean kiểm tra chính sách truy cập đối tượng |
| `returnObject` | Giá trị trả về dùng trong `@PostAuthorize` |

Giả sử `Document` có getter `getOwnerUsername()`, `isShared()` và `setTitle(String)`; `DocumentRepository` có `findById(long)` trả về `Optional<Document>`. Đây là hai kiểu thuộc domain của ứng dụng, **không phải** class được Spring Security cung cấp. Mẫu dưới đây biểu diễn hai Spring bean với nghiệp vụ thực; để biên dịch cần khai báo hai kiểu domain/repository vừa nêu.

```java
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentAccess")
public class DocumentAccess {
    private final DocumentRepository documents;

    public DocumentAccess(DocumentRepository documents) {
        this.documents = documents;
    }

    public boolean canRead(Authentication actor, long id) {
        if (actor == null || !actor.isAuthenticated()) return false;
        return documents.findById(id)
            .map(doc -> doc.getOwnerUsername().equals(actor.getName())
                     || doc.isShared())
            .orElse(false);
    }

    public boolean canEdit(Authentication actor, long id) {
        if (actor == null || !actor.isAuthenticated()) return false;
        return documents.findById(id)
            .map(doc -> doc.getOwnerUsername().equals(actor.getName()))
            .orElse(false);
    }
}
```

```java
import java.util.NoSuchElementException;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentService {
    private final DocumentRepository documents;

    public DocumentService(DocumentRepository documents) {
        this.documents = documents;
    }

    @PreAuthorize(
        "hasAuthority('doc:read') and " +
        "@documentAccess.canRead(authentication, #id)"
    )
    public Document read(@P("id") long id) {
        return documents.findById(id)
            .orElseThrow(() -> new NoSuchElementException("Document not found"));
    }

    @Transactional
    @PreAuthorize(
        "hasAuthority('doc:edit') and " +
        "@documentAccess.canEdit(authentication, #id)"
    )
    public Document rename(@P("id") long id, String title) {
        Document document = documents.findById(id)
            .orElseThrow(() -> new NoSuchElementException("Document not found"));
        document.setTitle(title);
        return document;
    }
}
```

**Cơ chế:** gọi `DocumentService.read(42)` qua Spring proxy làm `@PreAuthorize` kiểm tra **cả** quyền `doc:read` và `documentAccess.canRead(...)`. Chỉ khi cả hai đúng, method mới đọc tài liệu. Annotation `@P("id")` khai báo tên tham số cho SpEL, tránh phụ thuộc cấu hình compiler; nếu dùng `#id` mà không có `@P`, cần biên dịch Java với `-parameters` để Spring Framework 6.1+ thấy tên tham số. Phần kiểm tra ownership diễn ra ở server dựa trên bản ghi thực, không tin `ownerId` do client gửi.

**Giới hạn AOP:** annotation có hiệu lực trên method của bean do Spring quản lý khi lời gọi đi qua proxy. Một lời gọi `this.rename(...)` từ method khác **trong cùng bean** thường bỏ qua interceptor; gọi bằng `new DocumentService(...)` cũng không có proxy. Đặt chính sách tại service boundary và viết test gọi bean thực từ Spring context; không chỉ gọi trực tiếp method trên object tự tạo.

`@PostAuthorize("returnObject.ownerUsername == authentication.name")` có thể phù hợp với thao tác **đọc**, vì nó đánh giá đối tượng trả về; không dùng nó làm cổng duy nhất cho thao tác ghi/xóa: side effect có thể xảy ra trước lúc bị từ chối. Với nghiệp vụ cập nhật, ưu tiên kiểm tra trước và bảo vệ phép ghi ở tầng dữ liệu.

## 4. Phân quyền đối với từng đối tượng dữ liệu

### 4.1. Vì sao phải kiểm tra ID thực tế?

Nếu API nhận `GET /api/documents/42`, client chỉ chọn **ID để yêu cầu**, không có quyền tự quyết định `owner`. Rủi ro **IDOR/BOLA** xuất hiện khi server chỉ kiểm tra `doc:read` rồi chạy `findById(42)` và trả dữ liệu cho bất kỳ ai biết ID. Việc đổi `42` thành `43` không được làm lộ dữ liệu người khác.

Ví dụ chính sách cho hệ thống một tenant:

| Người gọi | Authority | Tài liệu | Quyết định |
| --- | --- | --- | --- |
| Alice | `doc:read` | Tài liệu 42 do Alice sở hữu | Cho đọc |
| Bob | `doc:read` | Tài liệu 42 của Alice, chưa chia sẻ | Từ chối đọc |
| Bob | `doc:read` | Tài liệu 42 của Alice, đã chia sẻ đọc | Cho đọc |
| Bob | `doc:edit` | Tài liệu 42 của Alice, dù đã chia sẻ đọc | Từ chối sửa |
| Alice | `doc:edit` | Tài liệu 42 do Alice sở hữu | Cho sửa |
| Người chưa xác thực | Không có | Bất kỳ tài liệu riêng tư | Từ chối |

Đây là **chính sách ví dụ**, không phải mặc định của Spring Security. Hệ thống thật có thể dùng ACL (danh sách người được chia sẻ), role trong dự án, trạng thái tài liệu hoặc điều kiện tenant. Mọi điều kiện phải được thực thi ở phía server, ở mọi đường vào nghiệp vụ.

### 4.2. Đặt điều kiện ngay trong truy vấn khi phù hợp

Với dữ liệu riêng tư, truy vấn có ràng buộc sở hữu thường rõ hơn và giảm nguy cơ quên kiểm tra:

```java
// Ví dụ method của Spring Data JPA repository.
// Document có thuộc tính ownerUsername; tên field phải khớp entity thật.
Optional<Document> findByIdAndOwnerUsername(long id, String ownerUsername);
```

Trong service, lấy `ownerUsername` từ danh tính đã xác thực và dùng `findByIdAndOwnerUsername(id, actorName)`. Với tenant nhiều khách hàng, thêm `tenantId` vào cả điều kiện truy vấn và uniqueness/permission checks; một tên người dùng giống nhau ở hai tenant không được xem là cùng người sở hữu. Với các quyền phức tạp, thay điều kiện owner bằng query/policy kiểm tra ACL hay membership trên dữ liệu thật.

Đối với **ghi dữ liệu quan trọng**, chỉ kiểm tra owner trước rồi cập nhật sau có thể có khoảng đua (TOCTOU) nếu quyền/owner thay đổi giữa hai thao tác. Chọn transaction/locking phù hợp, hoặc câu lệnh cập nhật có điều kiện kiểu `UPDATE ... WHERE id = ? AND tenant_id = ? AND owner_id = ?`; kiểm tra số dòng cập nhật. Annotation ở service không tự làm thao tác DB trở nên nguyên tử.

Đối với **danh sách, tìm kiếm, phân trang, export**, phải áp filter quyền **trước khi phân trang/trả dữ liệu**, thường ngay trong truy vấn. Lấy tất cả rồi lọc bằng `@PostFilter` có thể lãng phí tài nguyên, làm sai tổng số/trang và lộ metadata ngoài ý muốn. Cả read-by-ID và list đều phải dùng cùng chính sách.

### 4.3. Khi nào dùng `hasPermission`?

Spring Security có biểu thức `hasPermission(target, 'read')` hoặc `hasPermission(id, 'Document', 'read')`, chuyển việc đánh giá vào `PermissionEvaluator` do ứng dụng tùy biến. Nó phù hợp khi nhiều service cùng sử dụng ACL/chính sách thống nhất. Tuy nhiên **không mặc nhiên suy ra quyền sở hữu chỉ vì gọi `hasPermission`**: phải cung cấp implementation, dữ liệu và phép ánh xạ quyền tương ứng. Với ví dụ nhỏ, bean `documentAccess` dễ đọc và dễ test hơn.

## 5. Phân biệt 401, 403, 404 và các lỗi khác

- **401 Unauthorized**: thường là chưa xác thực hợp lệ khi endpoint yêu cầu đăng nhập, đồng thời cơ chế xác thực chọn trả challenge 401.
- **403 Forbidden**: đã xác thực nhưng không đủ quyền, hoặc một lớp bảo vệ như CSRF từ chối. Không nên thấy 403 rồi kết luận ngay rằng sai role.
- **404 Not Found**: khi không có bản ghi; một API có thể chủ động dùng 404 cho dữ liệu ngoài phạm vi người gọi để tránh tiết lộ sự tồn tại, theo chính sách thống nhất của sản phẩm. Không dựa vào mã trạng thái để thay thế kiểm tra quyền.
- **500**: lỗi cấu hình/mapping ngoài dự kiến không nên biến thành 403 một cách âm thầm; cần log an toàn để điều tra.

Ở Servlet web request, Spring Security thường chuyển `AccessDeniedException` thành response từ chối qua cơ chế xử lý exception của filter chain. Với lời gọi service từ background job hay consumer không có HTTP request, ứng dụng phải tự xử lý exception/định nghĩa danh tính thực thi phù hợp.

## 6. Thiết kế kiểm thử theo cả ba tầng

Kiểm tra từng biên và các tương tác:

| Tình huống | Kỳ vọng | Tầng cần quan sát |
| --- | --- | --- |
| Khách chưa đăng nhập gọi endpoint riêng tư | Bị từ chối, thường 401 theo entry point | HTTP |
| Người có `doc:read` gọi `PATCH` cần `doc:edit` | 403 | HTTP |
| Người có `doc:edit` gọi trực tiếp service sửa tài liệu người khác | `AccessDeniedException`; dữ liệu không đổi | Method + object |
| Người có quyền đọc tài liệu 42 nhưng đổi ID sang tài liệu bí mật 43 | Không lấy được dữ liệu 43 | Object |
| Người ở tenant A biết ID tài liệu tenant B | Không thể đọc/sửa/đếm/tìm thấy qua API | Object/query |
| Chủ sở hữu sửa tài liệu của chính mình | Thành công, trạng thái được lưu | End-to-end |
| Query danh sách có 1000 tài liệu nhưng người gọi chỉ được xem 7 | Kết quả, phân trang và count chỉ phản ánh 7 tài liệu có quyền | Query |
| Method được gọi qua các entry point khác HTTP | Quy tắc nghiệp vụ vẫn hoạt động | Method |
| Request `PATCH` có authority nhưng thiếu CSRF token trong cấu hình cần CSRF | Bị chặn vì CSRF; không đổ lỗi cho authority | Web security |

Với HTTP, dùng `MockMvc` và `spring-security-test` (ví dụ `@WithMockUser`, `csrf()`) để xác minh 401/403 và matcher. Với object-level, dùng service bean thật cùng dữ liệu mẫu có owner/tenant khác nhau; mock toàn bộ service sẽ làm mất cơ hội kiểm tra annotation trên service đó. Trong test cập nhật, phải xác nhận **database không thay đổi** khi bị từ chối, không chỉ xác nhận status. Với query có phân trang, kiểm tra cả danh sách lẫn total/count.

## 7. Những sai lầm thường gặp

1. **Chỉ bảo vệ URL:** endpoint `/api/documents/{id}` có auth vẫn có thể trả dữ liệu người khác. Luôn xét owner/ACL/tenant theo ID thật.
2. **Nhầm role với authority:** `hasRole("ADMIN")` khác `hasAuthority("ADMIN")` nếu authority thực là `ROLE_ADMIN`. OAuth2 scope có thể được ánh xạ thành `SCOPE_xxx` theo cấu hình; đừng giả định token scope tự biến thành `doc:read`.
3. **Thứ tự matcher sai hoặc mở quá rộng:** luật `/api/**` được khai báo trước luật riêng có thể nuốt route phía sau. Xác định fallback rõ bằng `anyRequest()`.
4. **Quên `@EnableMethodSecurity`, tự gọi trong bean hoặc gọi object ngoài container:** annotation hiện diện trong code nhưng không được interceptor thực thi.
5. **Dùng `@PostAuthorize` cho ghi:** kiểm tra diễn ra sau side effect. Thay bằng kiểm tra trước và điều kiện ghi nguyên tử.
6. **Tin ID người sở hữu/tenant do client cung cấp:** identity và tenant phải đến từ nguồn đã xác thực/chứng thực, còn quyền được kiểm tra với dữ liệu server.
7. **Lọc quyền sau khi trả danh sách hoặc sau phân trang:** dễ lộ dữ liệu, sai count, tốn bộ nhớ. Đẩy điều kiện xuống query và nhất quán với endpoint đơn lẻ.
8. **Không xử lý race hoặc cache quyền cũ:** khi tài liệu chuyển owner/tenant hay thay ACL, quyền phải được cập nhật/kiểm tra tại thời điểm thích hợp; các thao tác ghi quan trọng cần bảo đảm tính nguyên tử.
9. **Xem mọi 403 là thiếu authority:** CSRF, policy ở method, policy ở object và rule HTTP đều có thể là nguyên nhân. Chẩn đoán theo tầng, không tắt bảo vệ theo cảm tính.

## 8. Quy trình áp dụng cho endpoint mới

1. Viết rõ quyết định mong muốn theo dạng **chủ thể – hành động – đối tượng – bối cảnh**; chọn mặc định từ chối.
2. Bảo vệ URL và HTTP method bằng rule tổng quát. Đặt matcher cụ thể trước matcher rộng.
3. Đặt kiểm tra quyền nghiệp vụ ở service boundary; bật method security và xác nhận lời gọi đi qua proxy.
4. Kiểm tra owner/ACL/tenant bằng bản ghi thật hoặc query có điều kiện; bảo vệ riêng các thao tác ghi và truy vấn danh sách.
5. Thiết kế status trả về, logging không lộ thông tin nhạy cảm và test các trường hợp trái quyền, đặc biệt **biết ID người khác**, thay đổi quyền khi đang xử lý và gọi service từ đường khác HTTP.

**Tự kiểm tra:** Nếu Alice và Bob đều có `doc:read`, URL `GET /api/documents/42` đã cho qua ở tầng HTTP, nhưng tài liệu 42 thuộc Alice và không chia sẻ, Bob có được xem không? **Không.** Rule HTTP chứng minh quyền đọc *loại tài nguyên*; bean policy hoặc query phải từ chối Bob vì thiếu quyền với *bản ghi cụ thể*.

## Tài liệu tham khảo

- Spring Security, *Authorize HttpServletRequests*: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security, *Method Security*: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security, *PermissionEvaluator API*: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/access/PermissionEvaluator.html
