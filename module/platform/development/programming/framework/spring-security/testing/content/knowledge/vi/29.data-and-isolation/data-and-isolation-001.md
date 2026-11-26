# Người dùng, vai trò, tenant và tài nguyên kiểm thử có định danh rõ ràng

> **Chương:** Dữ liệu và cô lập  
> **Module:** SPRING_SECURITY_TESTING — kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế bằng spring-security-test trên ứng dụng Servlet và Reactive.

## 1. Vì sao dữ liệu kiểm thử phải có định danh rõ ràng?

Một bài test bảo mật thường tạo ra nhiều đối tượng liên quan: người dùng, vai trò, tenant, tài nguyên và thông tin xác thực. Nếu tất cả test đều dùng username `user`, role `USER`, tenant mặc định và một bản ghi chung, rất khó biết vì sao request được chấp nhận hoặc bị từ chối. Test có thể pass do dữ liệu còn sót từ lần chạy trước, hoặc fail ngẫu nhiên khi chạy song song.

Trong ứng dụng đa tenant, việc định danh còn quan trọng hơn. Hai người dùng có thể cùng role nhưng thuộc tenant khác nhau; hai tài nguyên có thể cùng loại nhưng khác chủ sở hữu; một người dùng có thể được phép đọc dữ liệu trong tenant của mình nhưng không được truy cập dữ liệu của tenant khác. Nếu fixture không thể hiện các khác biệt này, test không chứng minh được ranh giới bảo mật.

Một bộ dữ liệu kiểm thử tốt cần trả lời rõ:

- **Ai đang gọi?** Subject/user ID nào, principal thuộc loại nào?
- **Người đó có quyền gì?** Role và authority cụ thể nào?
- **Người đó hoạt động trong tenant nào?** Tenant được xác định từ danh tính hoặc membership đã xác minh ra sao?
- **Tài nguyên nào đang được truy cập?** Resource ID, tenant sở hữu và owner ID là gì?
- **Test đang kiểm tra quan hệ nào?** Cùng tenant, khác tenant, cùng owner hay khác owner?

Trong module **SPRING_SECURITY_TESTING**, dữ liệu kiểm thử là một phần của bằng chứng xác thực và phân quyền. MockMvc và WebTestClient có thể tạo SecurityContext giả lập, nhưng test chỉ có ý nghĩa khi danh tính, quyền, tenant và tài nguyên được xác định đủ rõ để giải thích kết quả.

Sau bài học, bạn có thể:

1. Thiết kế fixture người dùng, role, tenant và resource với ID ổn định.
2. Phân biệt role, authority, tenant membership và quyền sở hữu tài nguyên.
3. Viết test positive và negative cho cùng tenant, khác tenant và khác owner.
4. Chọn đúng tiện ích Spring Security Test cho principal đơn giản, UserDetails hoặc JWT có claim tenant.
5. Cô lập dữ liệu giữa các test, tránh phụ thuộc thứ tự và rò rỉ trạng thái khi chạy song song.

## 2. Mô hình định danh cho một test bảo mật

Một fixture nên biểu diễn ít nhất bốn lớp dữ liệu:

| Lớp | Định danh ví dụ | Ý nghĩa bảo mật |
| --- | --- | --- |
| Người dùng | `user-alice` | Principal/subject đang gửi request |
| Vai trò và authority | `ROLE_TENANT_ADMIN`, `document:read` | Loại người dùng và hành động được phép |
| Tenant | `tenant-red` | Phạm vi dữ liệu người dùng đang hoạt động |
| Tài nguyên | `doc-red-001`, owner `user-bob` | Đối tượng được truy cập và quan hệ sở hữu |

Có thể bổ sung membership, client ID, organization, project hoặc account tùy mô hình sản phẩm. Điều quan trọng là các ID phải cho thấy quan hệ giữa chúng mà không cần suy đoán.

### 2.1. Role không đồng nghĩa tenant

Role mô tả nhóm quyền hoặc chức năng. Tenant mô tả phạm vi dữ liệu. Ví dụ:

- Alice có `ROLE_TENANT_ADMIN` trong `tenant-red`.
- Carol cũng có `ROLE_TENANT_ADMIN`, nhưng thuộc `tenant-blue`.
- Cả hai có thể quản trị tenant của mình; Alice không vì có cùng role mà quản trị được tenant của Carol.

Một test chỉ dùng `@WithMockUser(roles = "TENANT_ADMIN")` chưa đủ để kiểm tra cô lập tenant. Nó tạo authority `ROLE_TENANT_ADMIN`, nhưng không tự cung cấp tenant ID hay membership.

### 2.2. Authority không đồng nghĩa quyền sở hữu

Authority như `document:read` có thể cho phép thực hiện thao tác đọc nói chung. Server vẫn cần xác định người dùng được đọc **tài liệu cụ thể nào**.

Ví dụ policy:

- Tenant admin có thể đọc mọi tài liệu trong tenant của mình.
- Tenant member chỉ có thể đọc tài liệu do chính mình sở hữu.
- Không ai được đọc tài liệu thuộc tenant khác.

Khi test, cần tách trường hợp cùng tenant/khác owner với khác tenant. Nếu chỉ tạo một tài liệu duy nhất cho mỗi user, hai ranh giới này dễ bị kiểm tra lẫn lộn.

### 2.3. Tenant ID trong request không phải bằng chứng membership

Một request có thể chứa tenant trong path, query hoặc header:

~~~http
GET /api/tenants/tenant-blue/documents/doc-blue-001
X-Tenant-ID: tenant-blue
~~~

Giá trị do client gửi chỉ là dữ liệu yêu cầu. Server phải đối chiếu nó với tenant mà principal được phép truy cập hoặc membership đã được xác minh. Không lấy `X-Tenant-ID` làm bằng chứng duy nhất rằng người dùng thuộc tenant đó.

Với JWT, tenant có thể được đưa vào claim như `tenant_id` sau khi identity provider xác thực membership. Nếu một người dùng thuộc nhiều tenant, cần xác định rõ active tenant và kiểm tra membership trước khi dùng claim đó làm phạm vi truy vấn.

## 3. Thiết kế fixture có quan hệ rõ ràng

Giả sử ứng dụng quản lý tài liệu cho hai tenant. Policy của bài thực hành:

- `tenant-red` có Alice là admin và Bob là member.
- `tenant-blue` có Carol là admin.
- Admin được đọc mọi tài liệu trong tenant của mình.
- Member chỉ được đọc tài liệu mình sở hữu.
- Mọi người đều bị chặn khi truy cập tenant khác.

| Subject | Username | Tenant | Role | Authority |
| --- | --- | --- | --- | --- |
| `user-alice` | `alice` | `tenant-red` | `ROLE_TENANT_ADMIN` | `document:read` |
| `user-bob` | `bob` | `tenant-red` | `ROLE_TENANT_MEMBER` | `document:read` |
| `user-carol` | `carol` | `tenant-blue` | `ROLE_TENANT_ADMIN` | `document:read` |

Tài nguyên:

| Resource ID | Tenant sở hữu | Owner | Mục đích trong test |
| --- | --- | --- | --- |
| `doc-red-alice-001` | `tenant-red` | `user-alice` | Tài liệu của Alice |
| `doc-red-bob-001` | `tenant-red` | `user-bob` | Tài liệu khác owner nhưng cùng tenant |
| `doc-blue-carol-001` | `tenant-blue` | `user-carol` | Tài liệu ở tenant khác |

Với fixture này, test có thể chứng minh riêng:

- Alice đọc được tài liệu của chính mình.
- Alice (admin) đọc được tài liệu Bob trong cùng tenant.
- Bob (member) đọc được tài liệu của mình.
- Bob không đọc được tài liệu Alice nếu policy member giới hạn theo owner.
- Alice không đọc được tài liệu Carol vì khác tenant.
- Carol không đọc được tài liệu thuộc `tenant-red` dù có cùng role admin.

Nếu policy sản phẩm khác, hãy thay kỳ vọng tương ứng. Cấu trúc fixture vẫn nên giữ các quan hệ khác nhau để có thể kiểm tra từng quy tắc.

## 4. Đặt ID rõ ràng và ổn định

### 4.1. Dùng ID mô tả quan hệ

ID test nên ngắn, dễ đọc và ổn định:

~~~java
final class SecurityTestIds {

    static final String TENANT_RED = "tenant-red";
    static final String TENANT_BLUE = "tenant-blue";

    static final String ALICE_ID = "user-alice";
    static final String BOB_ID = "user-bob";
    static final String CAROL_ID = "user-carol";

    static final String ALICE_DOCUMENT = "doc-red-alice-001";
    static final String BOB_DOCUMENT = "doc-red-bob-001";
    static final String CAROL_DOCUMENT = "doc-blue-carol-001";

    private SecurityTestIds() {
    }
}
~~~

Tên ID giúp người đọc hiểu ngay tài nguyên thuộc tenant nào và ai sở hữu. Nếu cơ sở dữ liệu dùng UUID, test vẫn có thể dùng UUID cố định được đặt tên trong fixture; không cần tạo ID ngẫu nhiên khó tra cứu cho mọi lần chạy.

### 4.2. Dùng factory thay vì sao chép fixture tùy tiện

Có thể gom dữ liệu vào một test fixture factory:

~~~java
record TestUser(
    String subject,
    String username,
    String tenantId,
    String role,
    String authority
) {}

record TestDocument(
    String id,
    String tenantId,
    String ownerId
) {}

final class SecurityFixtures {

    static final TestUser ALICE = new TestUser(
        "user-alice", "alice", "tenant-red",
        "ROLE_TENANT_ADMIN", "document:read");

    static final TestUser BOB = new TestUser(
        "user-bob", "bob", "tenant-red",
        "ROLE_TENANT_MEMBER", "document:read");

    static final TestUser CAROL = new TestUser(
        "user-carol", "carol", "tenant-blue",
        "ROLE_TENANT_ADMIN", "document:read");

    static final TestDocument ALICE_DOCUMENT = new TestDocument(
        "doc-red-alice-001", "tenant-red", "user-alice");

    static final TestDocument BOB_DOCUMENT = new TestDocument(
        "doc-red-bob-001", "tenant-red", "user-bob");

    static final TestDocument CAROL_DOCUMENT = new TestDocument(
        "doc-blue-carol-001", "tenant-blue", "user-carol");

    private SecurityFixtures() {
    }
}
~~~

Factory giúp các test dùng cùng một mô hình định danh. Không nên để mỗi test tự tạo một Alice khác tenant hoặc một tài liệu có owner không nhất quán với tên ID.

### 4.3. Tránh fixture mặc định ngầm

Những pattern dễ gây test sai:

- Tạo một user mặc định trong `@BeforeAll` nhưng không thể hiện tenant/authority.
- Repository trả về tài liệu đầu tiên mà không quan tâm tenant.
- Dùng ID `1` cho nhiều loại tài nguyên hoặc tenant.
- Dùng cùng username cho nhiều principal không phân biệt subject.
- Gán admin cho mọi test để tránh xử lý authorization.
- Dựa vào dữ liệu được seed bởi một test khác.

Hãy để dữ liệu cần thiết xuất hiện rõ trong test hoặc factory mà test gọi. Người đọc phải biết principal và resource đang được kiểm tra mà không cần tìm một test chạy trước.

## 5. Phân biệt cách tạo SecurityContext theo loại principal

Spring Security Test có nhiều tiện ích. Chọn tiện ích phù hợp với cấu trúc danh tính của ứng dụng.

### 5.1. @WithMockUser cho role/authority đơn giản

Khi chỉ cần kiểm tra rule dựa trên role:

~~~java
@Test
@WithMockUser(username = "alice", roles = "TENANT_ADMIN")
void adminCanOpenAdminPage() throws Exception {
    mvc.perform(get("/admin"))
        .andExpect(status().isOk());
}
~~~

`roles = "TENANT_ADMIN"` tạo authority `ROLE_TENANT_ADMIN`. Nếu dùng `authorities`, cung cấp đúng chuỗi authority, ví dụ `document:read`; Spring không tự thêm prefix `ROLE_` cho giá trị authority.

`@WithMockUser` phù hợp với test role đơn giản. Nó không tự tạo custom principal, tenant claim, membership hay resource ownership. Không dùng annotation này một mình để chứng minh tenant isolation.

### 5.2. @WithUserDetails khi ứng dụng dùng UserDetailsService

Nếu ứng dụng nạp principal qua `UserDetailsService`, `@WithUserDetails("alice")` có thể tạo context bằng user fixture thực trong test context:

~~~java
@Test
@WithUserDetails("alice")
void authenticatedPrincipalComesFromUserDetailsService() throws Exception {
    mvc.perform(get("/api/profile"))
        .andExpect(status().isOk());
}
~~~

Cách này hữu ích khi custom `UserDetails` chứa user ID, tenant membership hoặc thuộc tính ứng dụng. Cần seed user `alice` trước khi test chạy và bảo đảm UserDetailsService lấy đúng bản ghi fixture. Nếu có nhiều user cùng username trong các tenant, username cần được định danh duy nhất hoặc lookup phải có tenant context đáng tin cậy.

### 5.3. JWT test khi tenant nằm trong claim

Với OAuth2 Resource Server, tenant có thể nằm trong claim JWT đã được xác thực. Spring Security Test cho phép tạo JWT giả lập để kiểm tra authorization mà không cần gọi identity provider:

~~~java
mvc.perform(get("/api/tenants/tenant-red/documents/doc-red-alice-001")
        .with(jwt()
            .jwt(token -> token
                .subject("user-alice")
                .claim("tenant_id", "tenant-red"))
            .authorities(
                new SimpleGrantedAuthority("ROLE_TENANT_ADMIN"),
                new SimpleGrantedAuthority("document:read"))))
    .andExpect(status().isOk());
~~~

Test này tạo JWT giả lập với subject, tenant claim và authority cụ thể. Nó không kiểm tra chữ ký JWT, issuer, audience hoặc quá trình cấp token thực tế; các phần đó cần test riêng cho decoder/resource server hoặc kiểm thử tích hợp phù hợp.

Đối với ứng dụng session-based có custom principal chứa tenant ID, dùng `@WithUserDetails` hoặc custom `@WithSecurityContext` để tạo principal đúng kiểu. Chọn cách tạo context giống mô hình xác thực của ứng dụng, tránh ép mọi loại principal thành `@WithMockUser`.

## 6. Kiểm tra tenant scope ở tầng truy vấn dữ liệu

Cô lập tenant cần được thực thi tại server và tầng truy cập dữ liệu. Một pattern quan trọng là truy vấn resource theo cả ID và tenant ID:

~~~java
interface DocumentRepository {
    Optional<Document> findByIdAndTenantId(
        String documentId,
        String tenantId
    );
}
~~~

Truy vấn có phạm vi tenant:

~~~sql
SELECT id, tenant_id, owner_id, title
FROM documents
WHERE id = :documentId
  AND tenant_id = :tenantId;
~~~

Nếu chỉ gọi `findById(documentId)` rồi kiểm tra tenant ở một lớp không nhất quán, một code path khác có thể quên kiểm tra và làm lộ dữ liệu. Có thể dùng repository method, database row-level security hoặc cơ chế tenant filter phù hợp, nhưng test phải chứng minh query thực tế luôn giới hạn đúng tenant.

### 6.1. Tenant từ principal, không lấy tùy tiện từ request

Một service có thể nhận tenant đã được xác minh từ security context:

~~~java
Document loadDocument(
        String authenticatedTenantId,
        String documentId) {
    return repository.findByIdAndTenantId(
            documentId, authenticatedTenantId)
        .orElseThrow(DocumentNotFoundException::new);
}
~~~

Nếu endpoint nhận tenant trong path, so sánh nó với tenant active đã được xác minh trước khi truy vấn. Nếu mismatch, trả kết quả theo chính sách đã thống nhất, thường là 403 hoặc 404 tùy mục tiêu tránh tiết lộ sự tồn tại của resource.

### 6.2. Tenant membership có thể nhiều hơn một

Một user có thể thuộc nhiều tenant. Khi đó, không nên coi `tenant_id` duy nhất trong profile là mô hình tổng quát. Ứng dụng có thể dùng:

- Claim active tenant do hệ thống xác thực cấp sau khi xác minh membership.
- Membership repository kiểm tra subject có thuộc tenant được yêu cầu không.
- Tenant selector được server xác thực trước khi đặt tenant context.

Test cần có trường hợp user thuộc tenant A và B, đang hoạt động trong A, rồi yêu cầu tài nguyên B. Kết quả phải theo policy active tenant và không được tự động mở rộng quyền chỉ vì user có membership ở nhiều nơi.

## 7. Ma trận test cho user, role, tenant và owner

Với fixture ở phần 3, một ma trận test có thể là:

| Principal | Tenant của resource | Owner | Policy | Kỳ vọng |
| --- | --- | --- | --- | --- |
| Alice, tenant admin | tenant-red | Alice | Admin đọc trong tenant | Cho phép |
| Alice, tenant admin | tenant-red | Bob | Admin đọc trong tenant | Cho phép |
| Bob, tenant member | tenant-red | Bob | Member đọc tài liệu của mình | Cho phép |
| Bob, tenant member | tenant-red | Alice | Khác owner | Từ chối |
| Alice, tenant admin | tenant-blue | Carol | Khác tenant | Từ chối |
| Carol, tenant admin | tenant-red | Alice | Khác tenant | Từ chối |
| Principal thiếu tenant claim | tenant-red | Alice | Không xác định tenant | Từ chối |
| Principal thiếu `document:read` | tenant-red | Chính mình | Thiếu authority | Từ chối |

Nên kiểm tra cả resource đơn lẻ và collection. Endpoint list/search/count/export thường có thể làm lộ dữ liệu cross-tenant dù endpoint detail đã được bảo vệ.

### 7.1. Các lớp từ chối cần tách riêng

Không gom mọi trường hợp thất bại thành một test 403:

- Chưa xác thực: thường 401 hoặc redirect theo entry point.
- Thiếu authority: thường 403.
- Tenant mismatch: 403 hoặc 404 theo chính sách.
- Resource không thuộc tenant: thường 404 nếu không muốn tiết lộ resource tồn tại.
- Resource cùng tenant nhưng khác owner: 403/404 theo policy owner.
- Thiếu tenant claim hoặc membership: từ chối trước khi truy vấn dữ liệu.
- Resource không tồn tại: 404.

Status cụ thể phụ thuộc hợp đồng API. Điều quan trọng là test xác nhận đúng nguyên nhân và không vô tình tiết lộ dữ liệu.

## 8. MockMvc: kiểm tra tenant và owner bằng JWT fixture

Ví dụ dưới đây giả định API có endpoint:

`GET /api/tenants/{tenantId}/documents/{documentId}`

Server lấy tenant active từ JWT claim đã được xác minh, kiểm tra path tenant và truy vấn tài liệu bằng cả document ID lẫn tenant ID. Policy: tenant admin đọc mọi tài liệu trong tenant; tenant member chỉ đọc tài liệu do mình sở hữu.

### 8.1. Tenant admin đọc tài liệu trong tenant của mình

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class TenantDocumentSecurityTests {

    @Autowired
    MockMvc mvc;

    @Test
    void tenantAdminCanReadDocumentInsideOwnTenant() throws Exception {
        mvc.perform(get(
                "/api/tenants/tenant-red/documents/doc-red-bob-001")
            .with(jwt()
                .jwt(token -> token
                    .subject("user-alice")
                    .claim("tenant_id", "tenant-red"))
                .authorities(
                    new SimpleGrantedAuthority("ROLE_TENANT_ADMIN"),
                    new SimpleGrantedAuthority("document:read"))))
            .andExpect(status().isOk());
    }
}
~~~

Alice đọc tài liệu của Bob vì policy cho tenant admin đọc trong cùng tenant. Nếu policy thực tế yêu cầu ownership ngay cả với admin, thay kỳ vọng và service rule cho phù hợp.

### 8.2. Tenant admin không đọc được tài liệu tenant khác

~~~java
@Test
void tenantAdminCannotReadAnotherTenantDocument() throws Exception {
    mvc.perform(get(
            "/api/tenants/tenant-blue/documents/doc-blue-carol-001")
        .with(jwt()
            .jwt(token -> token
                .subject("user-alice")
                .claim("tenant_id", "tenant-red"))
            .authorities(
                new SimpleGrantedAuthority("ROLE_TENANT_ADMIN"),
                new SimpleGrantedAuthority("document:read"))))
        .andExpect(status().isForbidden());
}
~~~

Test này kiểm tra cả path tenant và tenant claim. Nếu API chọn trả 404 để không tiết lộ tenant/resource, hãy assert 404 theo hợp đồng đó. Không chấp nhận response 200 hoặc dữ liệu của tenant-blue.

### 8.3. Member không đọc được tài liệu khác owner trong cùng tenant

~~~java
@Test
void tenantMemberCannotReadOtherUsersDocumentInSameTenant()
        throws Exception {
    mvc.perform(get(
            "/api/tenants/tenant-red/documents/doc-red-alice-001")
        .with(jwt()
            .jwt(token -> token
                .subject("user-bob")
                .claim("tenant_id", "tenant-red"))
            .authorities(
                new SimpleGrantedAuthority("ROLE_TENANT_MEMBER"),
                new SimpleGrantedAuthority("document:read"))))
        .andExpect(status().isForbidden());
}
~~~

Khác với test cross-tenant, trường hợp này cùng tenant nhưng khác owner. Tách riêng hai test giúp xác định policy tenant hay policy ownership đang được thực thi.

### 8.4. Thiếu tenant claim phải bị từ chối

~~~java
@Test
void principalWithoutTenantClaimCannotReadTenantResource()
        throws Exception {
    mvc.perform(get(
            "/api/tenants/tenant-red/documents/doc-red-alice-001")
        .with(jwt()
            .jwt(token -> token.subject("user-alice"))
            .authorities(
                new SimpleGrantedAuthority("ROLE_TENANT_ADMIN"),
                new SimpleGrantedAuthority("document:read"))))
        .andExpect(status().isForbidden());
}
~~~

Ứng dụng cần xác định hành vi khi claim tenant thiếu hoặc không hợp lệ. Không tự động dùng tenant mặc định hoặc lấy tenant từ path để bù vào claim bị thiếu.

### 8.5. Thiếu authority dù tenant đúng

~~~java
@Test
void correctTenantWithoutReadAuthorityIsDenied() throws Exception {
    mvc.perform(get(
            "/api/tenants/tenant-red/documents/doc-red-alice-001")
        .with(jwt()
            .jwt(token -> token
                .subject("user-alice")
                .claim("tenant_id", "tenant-red"))
            .authorities(
                new SimpleGrantedAuthority("ROLE_TENANT_ADMIN"))))
        .andExpect(status().isForbidden());
}
~~~

Test này chứng minh tenant membership không thay thế authority của hành động. Người dùng có tenant hợp lệ nhưng thiếu `document:read` vẫn phải bị từ chối.

## 9. WebTestClient: cùng fixture, kiểm tra trên Reactive

Với WebFlux, Spring Security Test cung cấp `mockJwt()` để tạo principal JWT giả lập. Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockJwt;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveTenantDocumentSecurityTests {

    @Autowired
    WebTestClient client;

    @Test
    void tenantAdminCanReadOwnTenantDocument() {
        client.mutateWith(mockJwt()
                .jwt(token -> token
                    .subject("user-alice")
                    .claim("tenant_id", "tenant-red"))
                .authorities(
                    new SimpleGrantedAuthority("ROLE_TENANT_ADMIN"),
                    new SimpleGrantedAuthority("document:read")))
            .get()
            .uri("/api/tenants/tenant-red/documents/doc-red-bob-001")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void tenantAdminCannotReadOtherTenantDocument() {
        client.mutateWith(mockJwt()
                .jwt(token -> token
                    .subject("user-alice")
                    .claim("tenant_id", "tenant-red"))
                .authorities(
                    new SimpleGrantedAuthority("ROLE_TENANT_ADMIN"),
                    new SimpleGrantedAuthority("document:read")))
            .get()
            .uri("/api/tenants/tenant-blue/documents/doc-blue-carol-001")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

Các test cần cùng fixture trong repository hoặc database test mà Servlet sử dụng. WebTestClient phải chạy qua `SecurityWebFilterChain`; nếu chỉ bind vào controller mà không gắn security config, kết quả không chứng minh được tenant authorization.

### 9.1. Reactive tenant context không nên dựa vào ThreadLocal

Trong ứng dụng Reactive, request có thể đổi thread trong quá trình xử lý. Một `ThreadLocal` dùng để lưu tenant có thể không theo request qua các operator hoặc có thể bị rò rỉ giữa luồng xử lý nếu quản lý sai.

Nếu ứng dụng dùng Reactor Context hoặc cơ chế tenant context reactive, test phải tạo request/security context theo cách framework hỗ trợ và xác minh tenant được truyền xuyên suốt pipeline. Không lấy kết quả test Servlet với ThreadLocal làm bằng chứng cho WebFlux.

## 10. Cô lập dữ liệu giữa các test

### 10.1. Mỗi test phải tự thiết lập fixture cần thiết

Một test không nên phụ thuộc vào test khác đã tạo Alice, tenant-red hoặc document. Có thể seed fixture trong `@BeforeEach`, dùng factory, repository test helper hoặc SQL script rõ ràng.

Trình tự thường dùng:

1. Xóa hoặc tạo namespace dữ liệu test riêng.
2. Tạo tenant và membership.
3. Tạo user/principal fixture.
4. Tạo resource cùng tenant/owner rõ ràng.
5. Thực hiện request qua security filter chain.
6. Assert status, body và dữ liệu không bị thay đổi ngoài ý muốn.
7. Dọn fixture sau test hoặc rollback theo cơ chế đã xác minh.

### 10.2. Transaction rollback không phải lúc nào cũng cô lập được request

`@Transactional` trên test có thể rollback dữ liệu được tạo trong cùng transaction. Nhưng request qua server, async processing, `REQUIRES_NEW`, worker thread hoặc kết nối riêng có thể chạy trong transaction khác. Với Reactive/R2DBC, transaction context cũng có cơ chế riêng và không nên suy luận từ test JDBC đồng bộ.

Hãy xác minh transaction boundary của ứng dụng. Nếu request không tham gia transaction test, dùng fixture namespace riêng và cleanup rõ ràng. Không cho rằng gắn `@Transactional` vào mọi test sẽ tự dọn mọi side effect.

### 10.3. Tránh chia sẻ mutable fixture

Không dùng cùng một entity mutable giữa nhiều test song song. Một test đổi tenant, role hoặc owner có thể làm test khác nhận dữ liệu sai.

Có thể dùng:

- Fixture bất biến (record/constant).
- ID riêng cho từng test khi test chạy song song.
- Database schema/container riêng hoặc namespace theo test run.
- Cleanup có điều kiện theo test namespace.
- Repository factory tạo bản ghi mới cho mỗi test.

Nếu ID ổn định dùng chung, bảo đảm mỗi test có transaction/cleanup/isolation đủ mạnh để không tranh chấp dữ liệu. Khi bật parallel execution, cần test riêng cơ chế cô lập đó.

### 10.4. Dọn SecurityContext và tenant context

Spring Security Test thường thiết lập và dọn SecurityContext theo lifecycle của test listener. Nếu tự set `SecurityContextHolder`, phải khôi phục hoặc clear context sau test. Với custom tenant context dựa trên ThreadLocal, luôn có cleanup trong `finally` hoặc filter lifecycle phù hợp.

Trong Reactive, dùng Reactor Context theo request thay vì lưu trạng thái toàn cục. Test nên gửi hai request với hai tenant khác nhau liên tiếp và song song để phát hiện context bị rò rỉ.

## 11. Kiểm tra list, search và aggregate, không chỉ detail endpoint

Một endpoint detail có thể đã dùng `findByIdAndTenantId`, nhưng endpoint list vẫn có thể truy vấn tất cả bản ghi:

~~~sql
-- Truy vấn thiếu tenant scope
SELECT id, tenant_id, owner_id, title
FROM documents
ORDER BY created_at DESC;
~~~

Truy vấn cần giới hạn tenant:

~~~sql
SELECT id, tenant_id, owner_id, title
FROM documents
WHERE tenant_id = :authenticatedTenantId
ORDER BY created_at DESC;
~~~

Hãy kiểm tra các bề mặt dữ liệu sau:

| Bề mặt | Rủi ro nếu thiếu tenant/owner scope |
| --- | --- |
| Detail | Đọc trực tiếp resource tenant khác |
| List/search | Trộn dữ liệu nhiều tenant |
| Count/summary | Rò rỉ số lượng hoặc hoạt động tenant khác |
| Export/download | Tải hàng loạt dữ liệu ngoài phạm vi |
| Update/delete | Sửa hoặc xóa tài nguyên tenant khác |
| Nested resource | Truy cập child resource qua parent ID không cùng tenant |
| Cache | Trả response của tenant trước cho tenant sau |
| Event/message | Phát sự kiện hoặc xử lý job sai tenant |

Đừng chỉ assert HTTP status. Với negative test, kiểm tra response body không chứa dữ liệu của tenant khác và database không có thay đổi ngoài ý muốn.

## 12. Chọn status code và tránh tiết lộ sự tồn tại của resource

Khi user tenant-red yêu cầu document thuộc tenant-blue, API có thể trả 403 hoặc 404:

- **403 Forbidden:** cho biết danh tính đã được xác định nhưng không được phép thực hiện hành động.
- **404 Not Found:** có thể dùng để không tiết lộ resource tồn tại ngoài phạm vi của caller.

Cả hai đều có thể là lựa chọn hợp lệ nếu áp dụng nhất quán và không tạo side channel rõ ràng. Ví dụ, nếu resource không tồn tại trả 404 nhưng resource của tenant khác trả 403, người gọi có thể suy ra ID nào đang tồn tại. Một số hệ thống cố ý trả cùng 404 cho cả hai trường hợp.

Test cần ghi rõ hợp đồng API và kiểm tra:

- Status code theo policy.
- Error code/message không tiết lộ tenant, owner hoặc nội dung.
- Response time không tạo khác biệt quá lớn nếu hệ thống có yêu cầu chống enumeration.
- Không có dữ liệu nhạy cảm trong response, log hoặc event.

Không đổi mọi lỗi thành 404 chỉ để che giấu; lựa chọn cần phù hợp UX, audit và hợp đồng API.

## 13. Những lỗi thiết kế fixture thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Mọi test dùng `@WithMockUser` cùng role | Không kiểm tra tenant/custom principal | Tạo JWT/UserDetails fixture có tenant |
| Tenant mặc định ngầm | Test không biết dữ liệu thuộc phạm vi nào | Gán tenant ID tường minh |
| Resource không có owner | Bỏ sót policy ownership | Gán owner ID cho fixture |
| User và tenant trùng lẫn với role | Khó phân biệt membership và authority | Lưu các thuộc tính thành trường riêng |
| Dùng request header làm tenant identity | Client có thể tự chọn phạm vi dữ liệu | Xác minh tenant qua principal/membership |
| Chỉ test detail endpoint | List/export/count có thể rò rỉ dữ liệu | Kiểm tra mọi bề mặt truy vấn |
| Dữ liệu seed dùng chung giữa test | Phụ thuộc thứ tự và fail ngẫu nhiên | Fixture độc lập và cleanup |
| Test chỉ assert status | Có thể trả sai tenant data trong body | Assert body, owner, tenant và side effects |
| Dùng ThreadLocal cho Reactive context | Tenant có thể rò rỉ giữa request | Dùng Reactor Context/cơ chế reactive phù hợp |

## 14. Ma trận kiểm thử đề xuất

| Mã | Principal | Resource | Điều kiện | Kỳ vọng |
| --- | --- | --- | --- | --- |
| DATA-01 | Alice, tenant-red admin | Alice, tenant-red | Cùng tenant, đúng role | Cho phép |
| DATA-02 | Alice, tenant-red admin | Bob, tenant-red | Cùng tenant, admin được đọc | Cho phép |
| DATA-03 | Bob, tenant-red member | Bob, tenant-red | Đúng owner | Cho phép |
| DATA-04 | Bob, tenant-red member | Alice, tenant-red | Khác owner | Từ chối |
| DATA-05 | Alice, tenant-red admin | Carol, tenant-blue | Khác tenant | Từ chối |
| DATA-06 | Carol, tenant-blue admin | Alice, tenant-red | Khác tenant, cùng role | Từ chối |
| DATA-07 | Alice, thiếu tenant claim | Alice, tenant-red | Tenant không xác định | Từ chối |
| DATA-08 | Alice, tenant-red | Alice, tenant-red | Thiếu document:read | Từ chối |
| DATA-09 | Alice, tenant-red | List tenant-red | Chỉ dữ liệu tenant-red | Không có bản ghi tenant khác |
| DATA-10 | Alice, tenant-red | Count/export | Chỉ dữ liệu tenant-red | Không rò rỉ số liệu/file |
| DATA-11 | User thuộc nhiều tenant | Resource tenant không active | Membership không đồng nghĩa active scope | Từ chối hoặc yêu cầu chọn tenant |
| DATA-12 | Hai request song song | Hai tenant khác nhau | Context không rò rỉ | Mỗi response đúng tenant |

Hãy chạy các ca negative với cả status và body/data assertion. Với các endpoint thay đổi trạng thái, kiểm tra database sau request để xác nhận tài nguyên tenant khác không bị cập nhật hoặc xóa.

## 15. Bài thực hành và tiêu chí hoàn thành

Xây dựng bộ fixture cho ứng dụng quản lý tài liệu có hai tenant:

- `tenant-red`: Alice là `ROLE_TENANT_ADMIN`, Bob là `ROLE_TENANT_MEMBER`.
- `tenant-blue`: Carol là `ROLE_TENANT_ADMIN`.
- Mỗi user có subject/user ID riêng.
- Tạo ba tài liệu: tài liệu Alice, tài liệu Bob trong `tenant-red`, tài liệu Carol trong `tenant-blue`.
- Authority đọc tài liệu là `document:read`.

Hãy thực hiện:

1. Tạo fixture factory với tenant ID, subject, role, authority, resource ID và owner ID tường minh.
2. Viết test `@WithMockUser` cho rule chỉ phụ thuộc role đơn giản; ghi rõ giới hạn khi principal cần tenant claim.
3. Viết MockMvc test dùng `jwt()` để giả lập subject và `tenant_id`.
4. Viết WebTestClient test dùng `mockJwt()` cho cùng các trường hợp tenant admin/member.
5. Kiểm tra Alice admin đọc tài liệu Bob trong cùng tenant; Bob member không đọc tài liệu Alice nếu policy giới hạn owner.
6. Kiểm tra Alice không đọc tài liệu Carol ở tenant khác dù cả hai cùng role admin.
7. Kiểm tra thiếu tenant claim, thiếu authority và tenant path mismatch.
8. Kiểm tra list/search/count/export chỉ trả dữ liệu trong tenant active.
9. Chạy test độc lập và song song; xác minh fixture/cleanup không phụ thuộc thứ tự.
10. Nếu ứng dụng Reactive, kiểm tra tenant context không rò rỉ giữa request.

**Tiêu chí hoàn thành:** mỗi test chỉ rõ principal, role/authority, tenant và resource/owner; positive và negative cases chứng minh được ranh giới cùng tenant, khác tenant và khác owner; dữ liệu test được tạo/dọn độc lập; MockMvc/WebTestClient chạy qua security chain thực tế.

**Điểm cần nhớ:** một role đúng không đủ để chứng minh quyền truy cập một tài nguyên. Test bảo mật đa tenant phải định danh rõ người dùng, quyền, tenant active, resource và owner, rồi kiểm tra các quan hệ đó ở cả endpoint đơn lẻ lẫn truy vấn dữ liệu tập hợp.
