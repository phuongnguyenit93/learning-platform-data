# Phân quyền theo chủ sở hữu tài nguyên và phòng tránh IDOR

## 1. Vấn đề cốt lõi: được gọi API không đồng nghĩa được truy cập mọi tài nguyên

Trong Spring Security reactive/WebFlux, một request đã xác thực có thể vượt qua quy tắc `authenticated()` hoặc `hasRole("USER")` nhưng vẫn không có quyền đọc, sửa hay xóa một bản ghi cụ thể. Một lỗi phổ biến là controller nhận ID do client gửi, gọi `repository.findById(id)`, rồi trả dữ liệu mà không đối chiếu **chủ sở hữu** hoặc quyền chia sẻ hợp lệ.

**IDOR (Insecure Direct Object Reference)** xảy ra khi client thay ID tài nguyên và truy cập được dữ liệu hoặc thao tác của người khác do kiểm tra quyền ở cấp đối tượng còn thiếu. Trong OWASP API Security, tình huống tương ứng thường được gọi là **BOLA (Broken Object Level Authorization)**.

~~~text
GET /api/docs/doc-101 + xác thực Alice  ──► 200: tài liệu Alice
GET /api/docs/doc-102 + xác thực Alice  ──► 200: tài liệu Bob
                                           ↑ LỖ HỔNG IDOR
Ứng dụng chỉ hỏi "Alice đã đăng nhập/có ROLE_USER chưa?"
mà không hỏi "Alice có quyền trên doc-102 không?".
~~~

Nếu có phân quyền đúng, request thứ hai phải **không được đọc tài liệu của Bob**, dù Alice được phép gọi cùng loại endpoint để đọc tài liệu của chính mình. Theo chính sách sản phẩm, response có thể là 403 hoặc 404; trong bài này, ví dụ chọn 404 cho tài liệu người dùng không có quyền xem, nhằm hạn chế tiết lộ sự tồn tại của tài nguyên.

### Mục tiêu học tập

1. Phân biệt authentication, quyền truy cập URL và quyền trên đối tượng (object-level authorization).
2. Giải thích vì sao ID ngẫu nhiên, `hasRole` và `hasAuthority` riêng lẻ không đủ chống IDOR.
3. Lấy actor/tenant từ `SecurityContext` đáng tin cậy thay vì tin `ownerId`/`tenantId` từ path, query, header hay JSON.
4. Bảo vệ GET, LIST, SEARCH, PUT/PATCH/DELETE và tài nguyên con, kể cả khi người dùng đổi ID.
5. Áp điều kiện owner/tenant ngay trong truy vấn dữ liệu và cùng câu lệnh UPDATE để tránh TOCTOU.
6. Thiết kế luồng HTTP 401/403/404, scope support/admin và quyền chia sẻ.
7. Xây ví dụ Java 17+ Spring Boot WebFlux hoàn chỉnh có unit/integration tests bằng `WebTestClient`.

## 2. Ba tầng quyết định không được trộn lẫn

~~~text
HTTP GET /api/docs/doc-102
           │
           ▼
Spring Security: Authentication
  Alice đã xác minh password/token? ── Không ─► 401 / entry point
           │ Có
           ▼
HTTP Authorization (authorizeExchange)
  GET /api/docs/* có "doc:read"? ────── Không ─► 403
           │ Có
           ▼
DocumentService / Repository
  doc-102 thuộc cùng tenant?
  Alice là owner / có share grant / được override rõ ràng?
        │ Có                         │ Không
        ▼                             ▼
  DTO dữ liệu an toàn            404 hoặc 403
        │
       200
~~~

| Tầng | Câu hỏi | API thường gặp | Giới hạn |
| --- | --- | --- | --- |
| Authentication | Ai đang gửi request? | `ReactiveAuthenticationManager`, `Authentication`, `SecurityContext` | Không biết tài liệu thuộc ai |
| HTTP authorization | Người dùng được dùng chức năng này? | `authorizeExchange`, `hasRole`, `hasAuthority` | Không tự tra ownerId của từng record |
| Resource authorization | Người dùng có quyền trên đúng ID? | Service policy, repository predicates, ACL | Cần diễn đạt trên mọi đường truy cập dữ liệu |
| Database enforcement | Có thể lọc/ghi dữ liệu theo owner+tenant ngay tại DB? | Conditional SQL, RLS, reactive repositories | Cần actor/tenant đáng tin cậy |
| Response shaping | Trường nào được phép công khai? | DTO allowlist | Không thay thế việc kiểm quyền |

Ví dụ Alice và Bob cùng có `ROLE_USER` và `doc:read`. Nếu chỉ dùng `hasRole("USER")`, cả hai đều vượt qua HTTP rule; không có logic nào trong rule đó tự xác định `doc-102.ownerId == Bob.id`. Phải bổ sung kiểm tra resource-level.

### 2.1. Role, permission, owner và tenant

- **Role:** nhóm trách nhiệm, ví dụ `ROLE_USER`, `ROLE_SUPPORT`.
- **Permission:** quyền thao tác, ví dụ `doc:read`, `doc:write`, `doc:read:any`.
- **Owner:** định danh account sở hữu bản ghi.
- **Tenant:** ranh giới phân tách tổ chức/khách hàng trong ứng dụng đa tenant.
- **Share grant / ACL:** quyền được người sở hữu hoặc quản trị có thẩm quyền chia sẻ cho user khác, có scope hành động/thời hạn rõ ràng.

Quy tắc `hasAuthority("doc:read")` không tự động cho phép tất cả tài liệu. Ngay cả quyền `doc:read:any` cũng phải được giới hạn tenant, phạm vi tổ chức, mục đích sử dụng và audit theo policy, không suy ra toàn quyền trên hệ thống.

## 3. Các dạng IDOR/BOLA cần nhận diện

### 3.1. Path variable

~~~http
GET /api/docs/doc-102 HTTP/1.1
Authorization: Basic <credentials-của-Alice>
~~~

ID là dữ liệu do client chọn. Nếu controller trả `findById("doc-102")` không lọc owner/tenant thì tài liệu Bob bị lộ. Kiểm tra đã login trước đó không giải quyết vấn đề.

### 3.2. Query string và bộ lọc danh sách

~~~text
GET /api/docs?ownerId=u-200
GET /api/orders?customerId=999
GET /api/reports?tenantId=t-other
~~~

Khi endpoint mang nghĩa “của tôi”, chủ sở hữu phải suy ra từ identity server-side. Query param từ client chỉ là **yêu cầu lựa chọn**, không phải bằng chứng được quyền. Endpoint tìm kiếm/list cần áp ACL **trước khi** tính count, sort, pagination và stream dữ liệu; lọc ở frontend hay sau phân trang đều không đủ.

### 3.3. JSON body và mass assignment

~~~json
{
  "documentId": "doc-102",
  "ownerId": "u-100",
  "tenantId": "t-1",
  "title": "Change ownership"
}
~~~

Client có thể mạo danh owner/tenant nếu backend bind JSON trực tiếp vào entity và lưu lại toàn bộ trường. Với API sửa tiêu đề, DTO chỉ nên chứa các trường được phép sửa:

~~~java
public record RenameRequest(String title) {}
~~~

Quyền kiểm dựa trên identity và dữ liệu hiện tại trong repository, **không dựa vào ownerId mà client vừa tự khai báo**.

### 3.4. Upload, download, attachment, export, batch, GraphQL

- `GET /docs/{docId}/files/{fileId}` cần kiểm file thuộc đúng document mà user được phép xem; đừng chỉ kiểm fileId tồn tại.
- `GET /exports/{jobId}` cần kiểm chủ sở hữu job và object storage key, không chỉ giữ link khó đoán.
- `POST /docs/batch` cần kiểm từng ID trong batch, tránh “một ID được phép” làm hợp thức hóa cả danh sách.
- GraphQL resolver lấy `node(id)` cũng phải kiểm object-level, không chỉ authorize operation root.
- WebSocket/SSE và background jobs phải có policy phù hợp với thời điểm stream/đưa dữ liệu ra ngoài, không tự coi client đã qua HTTP authentication là quyền vĩnh viễn.

### 3.5. UUID không thay thế authorization

UUID/ULID không dễ đoán giúp giảm việc dò ID tuần tự, nhưng ID có thể lộ qua email, share link, log, referrer, API khác hoặc bug. Một attacker biết đúng UUID vẫn phải bị từ chối nếu không có quyền. Không dùng tính bí mật của ID làm kiểm soát truy cập duy nhất.

## 4. Lấy actor đáng tin từ SecurityContext reactive

Trong Spring WebFlux, bảo mật được truyền theo **Reactor Context** của subscription:

~~~java
Mono<Authentication> authenticatedActor =
    ReactiveSecurityContextHolder.getContext()
        .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()));
~~~

Ở đây:
- `ReactiveSecurityContextHolder.getContext()` trả `Mono<SecurityContext>`.
- `Authentication.getName()` có thể trả username, subject hoặc tên định danh theo cơ chế login.
- `Authentication.getPrincipal()` có thể là `UserDetails`, `Jwt` hay custom principal.
- `getAuthorities()` trả quyền đã cấp từ manager/identity provider đáng tin, không phải role mà client tùy ý gửi.

**Không** lấy `ownerId` từ `X-User-Id`, tham số `userId` hoặc JSON body rồi coi là identity. Trong ứng dụng lớn, nên có **immutable accountId** và **tenantId đã xác minh** trong principal/claim hoặc directory backend. Username/email/displayName có thể thay đổi, không nên mặc định làm khóa định danh bảo mật vĩnh viễn.

Trong dự án demo, Spring Security tạo `UserDetails` và backend ánh xạ username **đã xác thực** sang account ID/tenant từ store tin cậy. Mô hình này gọn để học; sản phẩm có multi-realm/username thay đổi nên dùng principal chứa immutable ID.

Không dùng `SecurityContextHolder` ThreadLocal kiểu Servlet rồi giả định đúng ở mọi nhánh reactive. Không gọi `block()` hoặc tự `subscribe()` để kiểm quyền trong WebFlux handler.

## 5. Policy cụ thể: Alice, Bob, Carol và Support

Thiết kế bộ dữ liệu demo:

| User | Account ID | Tenant | Authorities |
| --- | --- | --- | --- |
| Alice | `u-100` | `t-1` | `ROLE_USER`, `doc:read`, `doc:write` |
| Bob | `u-200` | `t-1` | `ROLE_USER`, `doc:read`, `doc:write` |
| Carol | `u-300` | `t-2` | `ROLE_USER`, `doc:read`, `doc:write` |
| Support | `u-900` | `t-1` | `ROLE_SUPPORT`, `doc:read`, `doc:read:any` |

Documents:

| ID | Tenant | Owner | Tiêu đề ban đầu |
| --- | --- | --- | --- |
| `doc-101` | `t-1` | Alice | Alice private plan |
| `doc-102` | `t-1` | Bob | Bob private plan |
| `doc-201` | `t-2` | Carol | Carol private plan |

Quy tắc:

- **GET theo ID:** có `doc:read` ở HTTP, document phải cùng tenant và (actor là owner **hoặc** actor được cấp `doc:read:any` trong tenant).
- **LIST:** cùng điều kiện đọc, lọc **từng tài liệu**; không trả mọi tài liệu rồi để client ẩn đi.
- **PUT đổi tiêu đề:** có `doc:write` ở HTTP, document phải cùng tenant **và chính actor là owner**. Support dù đọc rộng vẫn không có quyền viết.
- **Unknown ID / không có quyền xem:** cùng trả 404 theo policy của demo.
- **Anonymous:** 401 với HTTP Basic; user đã xác thực nhưng thiếu permission thao tác: 403.
- **Sai tenant:** bị từ chối kể cả user mang quyền support.

Ma trận kỳ vọng:

| Request | Kết quả |
| --- | --- |
| Alice GET `doc-101` | 200 |
| Alice GET `doc-102` | 404 |
| Bob GET `doc-102` | 200 |
| Alice GET `doc-201` | 404 |
| Support GET `doc-102` | 200 |
| Support GET `doc-201` | 404 |
| Alice PUT `doc-101` (CSRF hợp lệ) | 200 |
| Alice PUT `doc-102` (CSRF hợp lệ) | 404 |
| Support PUT `doc-102` (CSRF hợp lệ) | 403 |
| Anonymous GET `doc-101` | 401 |

Support override được giữ trong cùng tenant, không phải lối tắt để xem mọi khách hàng. Quyền này cần quy trình cấp quyền/audit thực tế nếu ứng dụng có dữ liệu riêng tư.

## 6. Phân quyền HTTP bằng `authorizeExchange`

Một cấu hình route-level điển hình:

~~~java
return http
    .authorizeExchange(exchanges -> exchanges
        .pathMatchers("/health").permitAll()
        .pathMatchers(HttpMethod.GET, "/api/docs", "/api/docs/*")
            .hasAuthority("doc:read")
        .pathMatchers(HttpMethod.PUT, "/api/docs/*")
            .hasAuthority("doc:write")
        .anyExchange().denyAll()
    )
    .httpBasic(Customizer.withDefaults())
    .build();
~~~

**Đây là đoạn trích**, chưa phải file Java độc lập. Project mục 8 có đủ dependency/import/bean.

Trong Spring Security:
1. Filter xác thực user và tạo `Authentication` đáng tin.
2. `AuthorizationWebFilter` áp các luật `authorizeExchange` theo thứ tự.
3. GET tài liệu yêu cầu `doc:read`, PUT yêu cầu `doc:write`.
4. Khi vượt qua tầng HTTP, **chưa** có bảo đảm ID là của user. Controller/service/repository bắt buộc kiểm resource ownership.
5. `anyExchange().denyAll()` giúp không tự cho phép route mới bị quên policy.

**Phân biệt:** `hasRole("USER")` mặc định kiểm `ROLE_USER`, `hasAuthority("doc:read")` kiểm đúng chuỗi `doc:read`. Cả hai chỉ kiểm authorities chung, không truy vấn bản ghi.

### 6.1. Có thể kiểm owner trực tiếp trong HTTP rule không?

Có. `ReactiveAuthorizationManager<AuthorizationContext>` được truyền cho `.access(...)` có thể dùng `Mono<Authentication>` và context của request, trong đó `AuthorizationContext.getVariables()` cung cấp biến URI matcher đã trích xuất.

Ví dụ **minh họa API, không nằm trong project runnable**:

~~~java
ReactiveAuthorizationManager<AuthorizationContext> ownerManager =
    (authentication, context) -> {
        Object rawId = context.getVariables().get("id");
        if (!(rawId instanceof String documentId)) {
            return Mono.just(new AuthorizationDecision(false));
        }

        return authentication
            .flatMap(auth ->
                trustedAccounts.findByUsername(auth.getName()))
            .flatMap(actor ->
                documentRepository.existsByIdAndTenantIdAndOwnerId(
                    documentId, actor.tenantId(), actor.id()))
            .map(AuthorizationDecision::new)
            .defaultIfEmpty(new AuthorizationDecision(false));
    };

// Ví dụ rule tương ứng:
.pathMatchers(HttpMethod.GET, "/api/docs/{id}")
    .access(ownerManager)
~~~

Các phương thức `trustedAccounts.findByUsername(...)` và `documentRepository.existsByIdAndTenantIdAndOwnerId(...)` là API **giả định do ứng dụng định nghĩa**. Đây là minh họa về contract reactive của Spring Security 6.3, trong đó `check(Mono<Authentication>, AuthorizationContext)` trả `Mono<AuthorizationDecision>`; không phải một ứng dụng độc lập.

**Cân nhắc khi làm thật:**
- Manager minh họa chỉ cho owner và **chưa** xét quyền Support; nếu áp nó vào demo sẽ đổi policy. Phải mở rộng theo grants/tenant được phê duyệt.
- Một access denial ở filter đối với user đã auth thường dẫn đến **403**, khác policy 404 ở resource service; phải thống nhất contract.
- Kiểm HTTP trước rồi dùng `findById`/`UPDATE ... WHERE id` phía sau vẫn có thể lộ dữ liệu khi service được gọi từ một nơi khác hoặc có race TOCTOU.
- Vì vậy, với thao tác dữ liệu, **predicate owner/tenant trong truy vấn và câu lệnh ghi** vẫn là hàng phòng vệ quan trọng nhất.

### 6.2. Reactive method security có giúp không?

Có thể dùng `@EnableReactiveMethodSecurity` và `@PreAuthorize`/custom authorizer trong business service để bảo vệ từ các ingress khác nhau (REST, GraphQL, message jobs). Nhưng `@PreAuthorize("hasAuthority('doc:read')")` vẫn chưa xét owner. Nếu gọi repository reactive trong authorizer, cần phương thức reactive phù hợp thay vì `block()` trong SpEL. Kiểm thử cả method security và repository constraints.

## 7. Bảo vệ dữ liệu ở bước truy vấn và bước cập nhật

### 7.1. Lấy tài liệu theo ID đơn thuần là chưa đủ

**Mẫu rủi ro:**

~~~java
Mono<Document> find(String id) {
    return repository.findById(id);
}
~~~

Nếu trả thẳng kết quả cho bất kỳ user đăng nhập nào, IDOR xảy ra.

**Mẫu truy vấn có scope:**

~~~java
Mono<Document> findOwned(
        String id, String tenantId, String ownerId) {

    return repository.findByIdAndTenantIdAndOwnerId(
        id, tenantId, ownerId);
}
~~~

Tên method repository ở ví dụ là **method do ứng dụng định nghĩa**, không phải API mặc định của mọi `ReactiveCrudRepository`. Ý nghĩa là database query lọc đồng thời theo ID, tenant và owner. Với chia sẻ dữ liệu, bổ sung ACL/grant hợp lệ thay vì bỏ luôn điều kiện tenant.

Với LIST/SEARCH, cần áp quyền trong SQL/search query **trước count/pagination**. Không đọc toàn bộ bảng rồi lọc ở Java (dễ lộ metadata, hiệu năng kém, sai số lượng trang).

### 7.2. Tránh TOCTOU: kiểm tra owner và ghi trong cùng operation

Một trình tự nguy hiểm:

~~~text
T1: SELECT doc-101 → owner Alice
T2: Backend chuyển owner từ Alice sang Bob
T3: UPDATE doc-101 SET title = ... chỉ dùng WHERE id = doc-101
    → Alice vẫn ghi đè được sau khi mất quyền.
~~~

Đây là race **time-of-check to time-of-use**. Câu lệnh cập nhật đúng cho tài liệu private nên ràng buộc owner+tenant ngay tại thời điểm ghi:

~~~sql
UPDATE documents
SET title = :newTitle,
    version = version + 1
WHERE id = :documentId
  AND tenant_id = :trustedTenantId
  AND owner_id = :trustedAccountId
  AND version = :expectedVersion;
~~~

- `rowsUpdated = 1`: thành công.
- `rowsUpdated = 0`: không tồn tại, không được phép hoặc version đã khác; ứng dụng chọn xử lý an toàn theo contract (404 / 409 / 412 khi có cách phân biệt phù hợp).
- Không làm UPDATE chỉ theo ID sau khi đã check owner ở một SELECT tách biệt.
- Với DELETE áp điều kiện tương tự. Với nested file/subresource, kiểm parent relationship.
- Với grant share đọc, đừng tự suy ra grant write.

Một câu lệnh SQL có predicate quyền, optimistic lock và transaction thích hợp có giá trị phòng vệ cao hơn phép check trong controller rồi ghi dữ liệu không ràng buộc.

### 7.3. 403 hay 404 khi không có quyền trên bản ghi?

- **403 Forbidden**: caller đã xác thực nhưng không được làm thao tác; thích hợp khi resource là thứ caller được biết tồn tại.
- **404 Not Found**: dùng cho cả tài nguyên không tồn tại và không được phép nhìn thấy, giảm khả năng dò xem ID nào hợp lệ.
- **401 Unauthorized**: chưa có authentication hợp lệ (với HTTP Basic demo).

Demo chọn 404 ở service để không tiết lộ tài liệu cá nhân, 403 ở filter cho permission thiếu. Cần đồng nhất thông điệp lỗi/header và tránh body tiết lộ “tài liệu thuộc về Bob”. 404 không loại bỏ hoàn toàn side-channel thời gian xử lý hoặc log, nên vẫn cần giám sát và hạn chế enumeration.

## 8. Dự án hoàn chỉnh Java 17+: bảo vệ GET/LIST/PUT tài liệu

Demo dùng **Spring Boot 3.3.13**, Gradle 8.x, Spring Security WebFlux và JDK 17+. Phiên bản được cố định để minh họa API, không phải khuyến nghị production với một phiên bản Boot đã hết hỗ trợ.

Bộ dữ liệu ở RAM để code độc lập, không phụ thuộc database; production dùng R2DBC, queries có owner+tenant và conditional update tương ứng.

### 8.1. Cấu trúc và Gradle

~~~text
webflux-idor-defense/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── IdorDefenseApplication.java
    │   ├── DemoStore.java
    │   ├── SecurityConfig.java
    │   └── DocumentController.java
    └── test/java/demo/
        └── OwnershipTests.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-idor-defense'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Không thêm `spring-boot-starter-web` trong ví dụ: Spring WebFlux dùng `ServerHttpSecurity`/`WebFilter` chứ không phải `HttpSecurity`/Servlet `Filter`.

### 8.2. Lớp khởi chạy

`src/main/java/demo/IdorDefenseApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class IdorDefenseApplication {

    public static void main(String[] args) {
        SpringApplication.run(IdorDefenseApplication.class, args);
    }
}
~~~

### 8.3. Store: account đáng tin và các operation đã lọc

`src/main/java/demo/DemoStore.java`:

~~~java
package demo;

import java.util.Comparator;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
class DemoStore {

    record Account(
        String id,
        String tenantId,
        String username,
        String passwordHash,
        Set<String> authorities
    ) {}

    // Entity lưu nội bộ, KHÔNG serialize trực tiếp ra HTTP.
    record StoredDocument(
        String id,
        String tenantId,
        String ownerId,
        String title,
        long version
    ) {}

    private final Map<String, Account> accountsByUsername;
    private final ConcurrentHashMap<String, StoredDocument> documents =
        new ConcurrentHashMap<>();

    DemoStore(PasswordEncoder encoder) {
        Account alice = new Account(
            "u-100", "t-1", "alice",
            encoder.encode("alice-pass"),
            Set.of("ROLE_USER", "doc:read", "doc:write")
        );
        Account bob = new Account(
            "u-200", "t-1", "bob",
            encoder.encode("bob-pass"),
            Set.of("ROLE_USER", "doc:read", "doc:write")
        );
        Account carol = new Account(
            "u-300", "t-2", "carol",
            encoder.encode("carol-pass"),
            Set.of("ROLE_USER", "doc:read", "doc:write")
        );
        Account support = new Account(
            "u-900", "t-1", "support",
            encoder.encode("support-pass"),
            Set.of("ROLE_SUPPORT", "doc:read", "doc:read:any")
        );

        accountsByUsername = Map.of(
            alice.username(), alice,
            bob.username(), bob,
            carol.username(), carol,
            support.username(), support
        );

        documents.put("doc-101", new StoredDocument(
            "doc-101", "t-1", "u-100", "Alice private plan", 1));
        documents.put("doc-102", new StoredDocument(
            "doc-102", "t-1", "u-200", "Bob private plan", 1));
        documents.put("doc-201", new StoredDocument(
            "doc-201", "t-2", "u-300", "Carol private plan", 1));
    }

    Mono<Account> findAccountByUsername(String username) {
        return Mono.justOrEmpty(accountsByUsername.get(username));
    }

    private boolean sameTenant(
            StoredDocument doc, Account caller) {
        return doc.tenantId().equals(caller.tenantId());
    }

    private boolean mayRead(
            StoredDocument doc, Account caller) {
        return sameTenant(doc, caller)
            && (doc.ownerId().equals(caller.id())
                || caller.authorities().contains("doc:read:any"));
    }

    private boolean mayWrite(
            StoredDocument doc, Account caller) {
        return sameTenant(doc, caller)
            && doc.ownerId().equals(caller.id());
    }

    Mono<StoredDocument> findReadable(
            String id, Account caller) {
        return Mono.justOrEmpty(documents.get(id))
            .filter(doc -> mayRead(doc, caller));
    }

    Flux<StoredDocument> listReadable(Account caller) {
        return Flux.fromIterable(documents.values())
            .filter(doc -> mayRead(doc, caller))
            .sort(Comparator.comparing(StoredDocument::id));
    }

    Mono<StoredDocument> renameOwned(
            String id, Account caller, String newTitle) {

        return Mono.defer(() -> {
            AtomicReference<StoredDocument> updated =
                new AtomicReference<>();

            // Atomic cho MỘT key trong Map JVM:
            // kiểm ownership và sửa nằm trong cùng computeIfPresent.
            documents.computeIfPresent(id, (key, original) -> {
                if (!mayWrite(original, caller)) {
                    return original;
                }

                StoredDocument changed = new StoredDocument(
                    original.id(), original.tenantId(),
                    original.ownerId(), newTitle, original.version() + 1);

                updated.set(changed);
                return changed;
            });

            return Mono.justOrEmpty(updated.get());
        });
    }
}
~~~

Phân tích:
- `Account.id` và `tenantId` được backend gán; client không được lựa chọn hay ghi đè.
- `findReadable` trả `Mono.empty()` khi document không tồn tại **hoặc** không đủ quyền; caller không biết lý do.
- `listReadable` áp cùng chính sách cho LIST. Trong production, phải chuyển predicate này thành SQL/search filter để tránh tải cả dataset.
- `mayRead` cho phép Support tenant t-1 đọc tài liệu Bob, nhưng không tài liệu Carol tenant t-2.
- `mayWrite` **không** cho phép Support cập nhật hộ; chỉ chủ sở hữu cùng tenant.
- `renameOwned` kiểm owner và update **nguyên tử trong `ConcurrentHashMap.computeIfPresent`** cho một key. Khi chuyển sang DB, dùng conditional UPDATE với row count, có thể thêm version/transaction.
- `AtomicReference` chỉ tồn tại cục bộ trong mỗi lần subscribe để đưa kết quả từ lambda map; không phải cache trạng thái chia sẻ request.
- `StoredDocument` là entity nội bộ có owner/tenant, không phải response DTO.

Store in-memory minh họa, không phải giải pháp production/cluster, không lưu trạng thái sau restart.

### 8.4. Spring Security: phân quyền thao tác qua URL

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    ReactiveUserDetailsService users(DemoStore store) {
        return username -> store.findAccountByUsername(username)
            .map(account -> User.withUsername(account.username())
                .password(account.passwordHash())
                .authorities(account.authorities().toArray(String[]::new))
                .build());
    }

    @Bean
    ReactiveAuthenticationManager authenticationManager(
            ReactiveUserDetailsService users, PasswordEncoder encoder) {

        UserDetailsRepositoryReactiveAuthenticationManager manager =
            new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    SecurityWebFilterChain security(
            ServerHttpSecurity http, ReactiveAuthenticationManager manager) {

        return http
            .authenticationManager(manager)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/health").permitAll()
                .pathMatchers(HttpMethod.GET,
                    "/api/docs", "/api/docs/*")
                    .hasAuthority("doc:read")
                .pathMatchers(HttpMethod.PUT, "/api/docs/*")
                    .hasAuthority("doc:write")
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            // CSRF GIỮ BẬT: PUT cần token hợp lệ.
            .build();
    }
}
~~~

- Password trong `DemoStore` được BCrypt hash, `UserDetailsRepositoryReactiveAuthenticationManager` xác minh raw password với `PasswordEncoder`.
- Authorities là tập do backend quản lý, không lấy role/permission trực tiếp từ request.
- `httpBasic` cho demo đơn giản, chỉ chạy local qua HTTP; production dùng HTTPS và giải pháp authentication phù hợp.
- GET yêu cầu `doc:read`, PUT yêu cầu `doc:write`; `anyExchange().denyAll()` chặn route khác.
- Bảo vệ CSRF vẫn mặc định bật, vì browser có thể tự gửi Basic/cookie credentials. Test PUT phải cung cấp CSRF token. Không tắt CSRF chỉ vì HTTP Basic khi chưa đánh giá rủi ro.
- HTTP authorization **không biết** ownerId trong database; `DemoStore` tiếp tục kiểm object-level.

### 8.5. Controller: không cho client ghi ownerId hoặc tenantId

`src/main/java/demo/DocumentController.java`:

~~~java
package demo;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
class DocumentController {

    public record DocumentView(
        String id, String title, long version) {}

    public record RenameRequest(String title) {}

    private final DemoStore store;

    DocumentController(DemoStore store) {
        this.store = store;
    }

    @GetMapping("/health")
    Mono<String> health() {
        return Mono.just("ok");
    }

    @GetMapping("/api/docs")
    Flux<DocumentView> list() {
        return currentAccount()
            .flatMapMany(store::listReadable)
            .map(this::toView);
    }

    @GetMapping("/api/docs/{id}")
    Mono<DocumentView> get(@PathVariable String id) {
        return currentAccount()
            .flatMap(actor -> store.findReadable(id, actor))
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(HttpStatus.NOT_FOUND)))
            .map(this::toView);
    }

    @PutMapping("/api/docs/{id}")
    Mono<DocumentView> rename(
            @PathVariable String id,
            @RequestBody Mono<RenameRequest> input) {

        return input
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(HttpStatus.BAD_REQUEST)))
            .flatMap(command -> {
                if (command.title() == null
                    || command.title().isBlank()
                    || command.title().length() > 100) {

                    return Mono.error(new ResponseStatusException(
                        HttpStatus.BAD_REQUEST, "Invalid title"));
                }

                return currentAccount()
                    .flatMap(actor -> store.renameOwned(
                        id, actor, command.title().trim()))
                    .switchIfEmpty(Mono.error(
                        new ResponseStatusException(HttpStatus.NOT_FOUND)))
                    .map(this::toView);
            });
    }

    private Mono<DemoStore.Account> currentAccount() {
        return ReactiveSecurityContextHolder.getContext()
            .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
            .flatMap(this::loadTrustedAccount)
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(HttpStatus.UNAUTHORIZED)));
    }

    private Mono<DemoStore.Account> loadTrustedAccount(
            Authentication authentication) {
        return store.findAccountByUsername(authentication.getName());
    }

    private DocumentView toView(DemoStore.StoredDocument doc) {
        return new DocumentView(
            doc.id(), doc.title(), doc.version());
    }
}
~~~

Bảo vệ quan trọng:
1. `id` trong URL chỉ dùng để xác định đối tượng muốn đọc/sửa, không phải bằng chứng quyền.
2. `currentAccount()` lấy authentication từ Reactor Context, ánh xạ sang account tin cậy. Không có tham số `ownerId`/`tenantId` trong controller.
3. GET/LIST/PUT gọi các operation đã ràng buộc owner/tenant ở `DemoStore`, không trả thẳng `findById`.
4. Request update chỉ có `title`; entity nội bộ không bị bind hàng loạt từ JSON. Kiểm input rỗng và dài trên 100 ký tự.
5. `DocumentView` chỉ có id, title và version; không trả ownerId/tenantId/passwordHash.
6. Không có quyền và không tồn tại dùng cùng `NOT_FOUND` ở object service.
7. Code giữ pipeline `Mono`/`Flux`, không gọi `block()` hay tự `subscribe()`.

Khi triển khai thật, code nên lấy immutable account ID trực tiếp từ identity đã xác minh (hoặc một trusted account directory theo realm) và truy vấn R2DBC có điều kiện. Controller không được là hàng bảo vệ duy nhất nếu service được gọi qua queue, scheduled job hoặc GraphQL.

## 9. Chạy với curl: thay ID không được đổi quyền

Từ thư mục dự án, cần JDK 17+ và Gradle tương thích:

~~~bash
gradle bootRun
~~~

Hoặc dùng `./gradlew bootRun` (Unix/macOS) / `gradlew.bat bootRun` (Windows) nếu có wrapper.

Trong bash/Git Bash:

~~~bash
# Anonymous: 401.
curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/api/docs/doc-101

# Alice sở hữu doc-101: 200.
curl -s -u alice:alice-pass \
  http://localhost:8080/api/docs/doc-101

# Alice đoán ID doc-102 của Bob: 404.
curl -s -u alice:alice-pass -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/api/docs/doc-102

# Bob đọc tài liệu Bob: 200.
curl -s -u bob:bob-pass \
  http://localhost:8080/api/docs/doc-102

# Support t-1 đọc tài liệu Bob: 200.
curl -s -u support:support-pass \
  http://localhost:8080/api/docs/doc-102

# Support t-1 không được đọc tài liệu Carol t-2: 404.
curl -s -u support:support-pass -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/api/docs/doc-201

# Alice chỉ liệt kê tài liệu trong phạm vi được phép.
curl -s -u alice:alice-pass \
  http://localhost:8080/api/docs
~~~

Response GET `doc-101` trước khi sửa:

~~~json
{
  "id": "doc-101",
  "title": "Alice private plan",
  "version": 1
}
~~~

Response LIST của Alice:

~~~json
[
  {
    "id": "doc-101",
    "title": "Alice private plan",
    "version": 1
  }
]
~~~

Cảnh báo: `curl -u` trong ví dụ chỉ phục vụ local; trên Internet bắt buộc HTTPS và bí mật không được lưu trong logs/scripts. Trên PowerShell dùng `curl.exe` và có thể thay `/dev/null` bằng `NUL`.

### 9.1. PUT không có CSRF có thể trả 403 trước khi kiểm owner

Một lệnh `curl -X PUT` không kèm token CSRF thường bị `CsrfWebFilter` từ chối vì demo giữ CSRF bật theo mặc định. Đây **không phải** bằng chứng object-level authorization đang đúng: cần gửi token hợp lệ trong test để request đi tới quyền chức năng và quyền sở hữu.

Không tự tắt CSRF toàn cục trong hệ thống browser dùng cookie/Basic credentials. Các ứng dụng Bearer token thuần với cơ chế gửi credential khác cần đánh giá rủi ro CSRF riêng. Mục tiếp theo dùng `WebTestClient.mutateWith(csrf())` trong test scope để mô phỏng token hợp lệ, không disable CSRF production.

## 10. Kiểm thử tích hợp với `WebTestClient`

`src/test/java/demo/OwnershipTests.java`:

~~~java
package demo;

import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class OwnershipTests {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void anonymousCannotReadProtectedDocument() {
        client.get().uri("/api/docs/doc-101")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void aliceCanReadOwnDocumentButNotInternalOwnerFields() {
        client.get().uri("/api/docs/doc-101")
            .headers(h -> h.setBasicAuth("alice", "alice-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo("doc-101")
            .jsonPath("$.ownerId").doesNotExist()
            .jsonPath("$.tenantId").doesNotExist();
    }

    @Test
    void aliceCannotReadBobsDocumentByChangingId() {
        client.get().uri("/api/docs/doc-102")
            .headers(h -> h.setBasicAuth("alice", "alice-pass"))
            .exchange()
            .expectStatus().isNotFound();

        client.get().uri("/api/docs/doc-102")
            .headers(h -> h.setBasicAuth("bob", "bob-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo("doc-102");
    }

    @Test
    void supportReadOverrideNeverCrossesTenant() {
        client.get().uri("/api/docs/doc-102")
            .headers(h -> h.setBasicAuth("support", "support-pass"))
            .exchange()
            .expectStatus().isOk();

        client.get().uri("/api/docs/doc-201")
            .headers(h -> h.setBasicAuth("support", "support-pass"))
            .exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void listContainsOnlyReadableDocuments() {
        client.get().uri("/api/docs")
            .headers(h -> h.setBasicAuth("alice", "alice-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$[0].id").isEqualTo("doc-101")
            .jsonPath("$[1]").doesNotExist();
    }

    @Test
    void ownerMayRenameWithValidCsrf() {
        client.mutateWith(csrf()).put().uri("/api/docs/doc-101")
            .headers(h -> h.setBasicAuth("alice", "alice-pass"))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("title", "Alice updated"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.title").isEqualTo("Alice updated");
    }

    @Test
    void aliceCannotRenameBobsDocumentEvenWithDocWrite() {
        client.mutateWith(csrf()).put().uri("/api/docs/doc-102")
            .headers(h -> h.setBasicAuth("alice", "alice-pass"))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("title", "Illegal takeover"))
            .exchange()
            .expectStatus().isNotFound();

        client.get().uri("/api/docs/doc-102")
            .headers(h -> h.setBasicAuth("bob", "bob-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.title").isEqualTo("Bob private plan");
    }

    @Test
    void supportCannotWriteBecausePermissionIsMissing() {
        client.mutateWith(csrf()).put().uri("/api/docs/doc-102")
            .headers(h -> h.setBasicAuth("support", "support-pass"))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("title", "Not allowed"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void missingCsrfCannotModifyDocument() {
        client.put().uri("/api/docs/doc-102")
            .headers(h -> h.setBasicAuth("bob", "bob-pass"))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("title", "No csrf"))
            .exchange()
            .expectStatus().isForbidden();

        client.get().uri("/api/docs/doc-102")
            .headers(h -> h.setBasicAuth("bob", "bob-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.title").isEqualTo("Bob private plan");
    }
}
~~~

Kiểm thử bao phủ **chín** tình huống: anonymous bị 401, owner được 200, ID chéo bị 404, Support override bị giới hạn tenant, danh sách được scope, PUT chính chủ 200, PUT tài liệu của Bob dù có `doc:write` vẫn 404, Support thiếu write 403, và PUT thiếu CSRF 403 mà không sửa dữ liệu.

**Quan trọng:** không chỉ assert HTTP status cho denied update; đọc lại tài liệu dưới tài khoản chủ sở hữu để xác nhận dữ liệu không bị đổi. Test sửa `doc-101` không ảnh hưởng assertion nội dung `doc-102` nên không phụ thuộc thứ tự các test ở điểm này. Với test database, nên cô lập fixture/transaction theo từng test.

Chạy:

~~~bash
gradle test
~~~

Hoặc wrapper tương ứng nếu có. Các test được thiết kế để chạy trên context WebFlux nhưng cần kiểm chứng kết quả thực tế bằng việc biên dịch/chạy trong môi trường project, không mặc định coi stdout Gradle là một chuỗi cố định.

## 11. Những trường hợp một lớp authorization dễ bỏ sót

### 11.1. List, search và phân trang

Nếu GET by ID đã kiểm owner nhưng `GET /api/docs?page=0` trả tất cả tài liệu, API vẫn có BOLA. Các điều kiện quyền phải nằm trong query dữ liệu **trước count, sort, limit, offset**. Cache kết quả đếm tổng hoặc facet/search filters cũng có thể tiết lộ sự tồn tại của tài liệu khác.

### 11.2. Nested object và file download

`GET /api/docs/{docId}/attachments/{fileId}` cần chắc chắn file thực sự thuộc docId được phép và cùng tenant. Một pre-signed URL object storage có TTL nhưng không tự kiểm owner khi cấp; chỉ phát URL sau khi đã authorize file, cân nhắc thời hạn, chia sẻ và revoke.

### 11.3. Multi-tenant và Support/Admin

`ROLE_ADMIN` trong tenant A không tự động có quyền trên tenant B. Không lấy tenant đang được chọn từ header do client tự gửi mà không kiểm membership/role trong tenant đó. Quyền support/override nên gắn scope tenant, action, expiry, purpose và audit.

### 11.4. Caching/CDN/ETag

Không đưa tài liệu riêng tư vào public CDN cache với cache key chỉ dựa vào URL. Cân nhắc `Cache-Control: private, no-store` cho dữ liệu nhạy cảm hoặc cache phân vùng theo principal/tenant/policy. Lưu ý 304/ETag, error body và CDN rules cũng có thể lộ dữ liệu/metadata.

### 11.5. Background jobs và thời gian thu hồi quyền

Một request có thể authorize export lúc 10:00, nhưng worker xuất file lúc 10:20 sau khi quyền đã bị thu hồi. Cần policy về thời điểm kiểm tra quyền, quyền ủy quyền có thời hạn, cancellation/audit. Đừng đẩy raw session cookie/password/token vào queue.

### 11.6. Dò quét ID và side-channel

Dùng 404 nhất quán để giảm lộ tồn tại resource nhưng vẫn cần:
- Rate limiting và cảnh báo nhiều ID không hợp lệ.
- Tránh thông báo “belongs to Bob” trong body/log public.
- Xem xét khác biệt độ trễ, headers, kích thước body và metadata.
- Kiểm biến thể URL encoded ID, alias, nested resource, sort/search và các API phụ.
- Không dùng rate limit hay ID random thay cho object-level authorization.

## 12. Sai lầm phổ biến và hướng sửa

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| `authenticated()` là điều kiện duy nhất | Mọi người đăng nhập đọc được mọi ID | Kiểm owner/tenant/grant từng object |
| Dùng `hasRole("USER")` nhưng không kiểm ID | Role chung không bảo vệ dữ liệu riêng | Thêm object-level authorization |
| Tin `ownerId`/`tenantId` trong JSON | Client mạo danh hoặc chuyển sở hữu | Lấy identity từ authentication tin cậy |
| Trả `findById(id)` trực tiếp | IDOR ở GET | Query có owner+tenant hoặc ACL |
| Check owner rồi `UPDATE WHERE id` | TOCTOU khi owner thay đổi | Conditional UPDATE với owner/tenant/version |
| Chỉ lọc danh sách ở frontend | Backend đã rò rỉ dữ liệu | Lọc tại database/service trước response |
| Chỉ che ID bằng UUID | Khi ID lộ vẫn bị khai thác | UUID chỉ hỗ trợ; luôn kiểm quyền |
| Giả định SUPPORT có quyền mọi tenant | Cross-tenant data leak | Scope rõ tenant và action, có audit |
| Kiểm owner ở controller mà service public bỏ qua | GraphQL/queue bypass | Bảo vệ service/repository |
| Deserialize JSON thành entity có owner | Mass assignment | DTO cho đúng các field được sửa |
| Trả entity với metadata nhạy cảm | Rò rỉ owner, tenant, state | Response DTO allowlist |
| 403/404 body phân biệt lý do bị từ chối | Lộ ID hợp lệ và owner | Error policy nhất quán |
| Dùng `block()` trong WebFlux authorizer | Chặn event loop | Pipeline reactive, R2DBC |
| Tự `subscribe()` để check quyền | Response có thể đi trước kết quả check | Compose với `flatMap` |
| Bỏ CSRF chỉ để PUT demo dễ chạy | Browser request giả mạo | Giữ CSRF theo mô hình credentials |
| Chỉ test khác tenant, không test 2 user cùng tenant | Bỏ sót horizontal IDOR | Test Alice ↔ Bob cùng ROLE_USER |
| Chỉ test response 404, không xem DB sau write | Có thể vẫn sửa dữ liệu | Assert dữ liệu không thay đổi |
| Cache tài liệu cá nhân không phân vùng user | Lộ cross-user từ CDN/cache | No-store/private hoặc policy-aware cache |

## 13. Câu hỏi kiểm tra

1. **IDOR là gì?** User có thể truy cập/thao tác trên object không thuộc quyền nhờ thay tham chiếu ID khi backend thiếu authorization object-level.
2. **BOLA khác gì?** Thuật ngữ OWASP nhấn mạnh broken authorization tại cấp object; IDOR là mẫu khai thác trực tiếp bằng ID.
3. **Alice có `doc:read` nên được đọc doc của Bob?** Không. Permission chức năng chưa đáp ứng điều kiện ownership/tenant.
4. **`hasRole("USER")` có tự tra ownerId không?** Không; nó kiểm authority role.
5. **Có thể dùng UUID thay authorization không?** Không. ID có thể bị lộ.
6. **Lấy ownerId/tenantId từ đâu?** Từ identity được xác minh và record backend, không tin client body/query/header.
7. **Vì sao phải lọc LIST ngay tại data source?** Tránh lộ record/count và tránh lọc sai sau pagination.
8. **Tại sao dùng conditional UPDATE?** Đảm bảo quyền tồn tại tại thời điểm ghi, tránh TOCTOU.
9. **`rowsUpdated=0` nghĩa gì?** Có thể bản ghi không tồn tại, không có quyền, hoặc version đổi; xử lý theo contract an toàn.
10. **Support tenant t-1 đọc doc của Carol tenant t-2 được không?** Không, dù có `doc:read:any` trong tenant t-1.
11. **READ permission có tự cho WRITE không?** Không; mỗi action cần policy riêng.
12. **403 hay 404 cho document không thuộc quyền?** Tùy policy; 404 thường giảm lộ sự tồn tại đối với private object.
13. **Vì sao test denied PUT phải đọc lại bản ghi?** Để chắc chắn thao tác không thực sự thay đổi dữ liệu.
14. **Đã có owner check ở HTTP filter thì có bỏ ở service được không?** Không nên: service có đường gọi khác và race giữa check với update.
15. **PUT thiếu CSRF trả 403 có chứng minh owner authorization đúng không?** Không; CSRF có thể chặn trước kiểm owner.
16. **Dùng `ReactiveSecurityContextHolder` ra sao?** Đọc `Mono<SecurityContext>` theo Reactor Context rồi lấy authentication để xác định actor.
17. **Một tài liệu được chia sẻ nên xét điều gì?** Active grant, grantee, action, tenant, expiry và trạng thái revoke.
18. **Owner chuyển giữa check và update có nguy cơ gì?** TOCTOU; áp quyền ngay trong UPDATE/transaction.
19. **Admin tenant A có mặc định toàn quyền tenant B?** Không; cần scope/ủy quyền.
20. **Tại sao không trả `StoredDocument` nguyên object?** Có thể lộ owner/tenant/metadata; dùng DTO được phép và vẫn kiểm quyền.

## 14. Checklist triển khai production

- [ ] Liệt kê tất cả API tham chiếu ID: GET, UPDATE, DELETE, LIST, SEARCH, export, file, batch, GraphQL, jobs.
- [ ] Xác định rõ owner, tenant và quyền share; phân biệt role chung với permission hành động.
- [ ] Actor ID/tenant phải đến từ nguồn đã xác minh, dùng immutable key theo realm.
- [ ] `authorizeExchange` yêu cầu quyền chức năng; route mới có default deny.
- [ ] Repository GET/LIST/SEARCH có predicates owner/tenant/ACL; lọc trước count/page.
- [ ] UPDATE/DELETE ràng buộc quyền trong cùng thao tác ghi hoặc transaction nhất quán.
- [ ] Có kiểm soát race, optimistic locking/version, đổi owner và revoke grants.
- [ ] DTO request không nhận owner/tenant trái phép; DTO response chỉ công bố field cần thiết.
- [ ] 401/403/404 được chuẩn hóa, không lộ sự tồn tại của dữ liệu nhạy cảm.
- [ ] Cross-tenant và support override có policy, scope, audit rõ ràng.
- [ ] Không dùng ID khó đoán, frontend hide button hoặc rate-limit làm quyền truy cập.
- [ ] Cache, pre-signed URLs, background jobs, WebSocket/SSE không bypass object policy.
- [ ] Test ít nhất hai account cùng role và cùng tenant, một account khác tenant.
- [ ] Test rejected write không đổi bản ghi; kiểm multipart/nested/list và alias.
- [ ] Không blocking database I/O hoặc detached `subscribe()` trong reactive authorization.
- [ ] Giữ CSRF khi dùng credentials tự đính kèm từ browser, bảo vệ cookie/token và dùng HTTPS.
- [ ] Theo dõi enumeration, xâm nhập ngang user và hoạt động support mà không log raw credentials.

## 15. Tài liệu tham khảo

- OWASP API Security Top 10 — API1:2023 Broken Object Level Authorization: https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
- OWASP — IDOR Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html
- OWASP — Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- Spring Security 6.3 — Reactive HTTP Authorization: https://docs.spring.io/spring-security/reference/6.3/reactive/authorization/authorize-http-requests.html
- Spring Security 6.3 API — `ReactiveAuthorizationManager`: https://docs.spring.io/spring-security/site/docs/6.3.x/api/org/springframework/security/authorization/ReactiveAuthorizationManager.html
- Spring Security API — `AuthorizationContext`: https://docs.spring.io/spring-security/site/docs/6.3.x/api/org/springframework/security/web/server/authorization/AuthorizationContext.html
- Spring Security — Reactive Method Security: https://docs.spring.io/spring-security/reference/6.3/reactive/authorization/method.html
- Spring Security — WebFlux Configuration: https://docs.spring.io/spring-security/reference/6.3/reactive/configuration/webflux.html

**Ghi nhớ:** ID trong URL chỉ định đối tượng muốn truy cập, **không phải giấy phép**. Chống IDOR/BOLA trong Spring Security reactive cần kết hợp **xác thực đáng tin + quyền theo HTTP method + kiểm owner/tenant/grant tại nơi đọc/ghi dữ liệu**, và kiểm thử đổi ID giữa các account có cùng role. Với PUT/PATCH/DELETE, bảo vệ owner ngay tại câu lệnh ghi để tránh TOCTOU.
