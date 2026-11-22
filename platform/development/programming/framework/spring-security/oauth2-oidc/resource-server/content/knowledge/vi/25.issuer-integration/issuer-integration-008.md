# Định danh người dùng theo issuer, subject và ánh xạ tài khoản nội bộ

Trong hệ thống **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Resource Server**, JWT access token hoặc kết quả opaque-token introspection giúp API xác nhận **chủ thể nào đã được Authorization Server chấp nhận**. Nhưng API bán hàng, thanh toán hoặc quản trị thường còn có một **định danh tài khoản nội bộ**: mã người dùng trong database, hồ sơ nhân viên, chủ đơn hàng, tenant membership và trạng thái khóa tài khoản. Những định danh này **không nhất thiết trùng `sub`, email hoặc username** mà nhà phát hành token cung cấp.

Ví dụ, Identity Server trả token có `sub = "00u84x2"`, còn Orders API lưu người dùng là `internal_user_id = "usr-0042"`. Nếu ứng dụng gọi trực tiếp `orderRepository.findByOwnerId(jwt.getSubject())`, nó có thể không tìm thấy đơn hàng; nguy hiểm hơn, nếu tích hợp nhiều nhà phát hành, **hai issuer có thể cấp cùng một `sub` nhưng đại diện cho hai người khác nhau**. Ở chiều ngược lại, **một người nội bộ có thể liên kết với nhiều danh tính bên ngoài** (đổi Identity Provider, tài khoản doanh nghiệp và tài khoản khách hàng, hoặc quá trình migration).

Bài học trình bày cách xác định **danh tính đáng tin bằng `(issuer, subject)`**, lưu ánh xạ sang account nội bộ, quyết định nơi thực hiện lookup trong Spring Security, tránh account takeover khi linking và kiểm thử những trường hợp nhầm lẫn danh tính giữa nhà phát hành/tenant.

> **Nguyên tắc quan trọng:** Định danh bên ngoài không phải khóa database nội bộ. Hãy chỉ tin `iss` và `sub` **sau khi access token đã được xác minh đúng issuer, signature/active, audience, thời hạn và profile**. Dùng cặp **`(iss, sub)`** làm khóa danh tính ngoài khi hợp đồng của nhà phát hành bảo đảm subject trong namespace issuer; ánh xạ nó tới **internal user ID bất biến**, còn quyền theo role/tenant/resource phải được đánh giá độc lập.

## 1. Ba vai trò trong luồng OAuth2/OIDC

Giả sử Shop Web gọi Orders API:

- **Identity Server (Authorization Server / OIDC Provider)**: xác thực người dùng, phát hành access token; có thể phát hành ID token dành cho OIDC Client.
- **Shop Web (OAuth2/OIDC Client)**: điều hướng đăng nhập hoặc xin quyền, lấy access token, gọi API theo grant/flow hợp lệ.
- **Orders API (Resource Server)**: xác minh access token và quyền truy cập tài nguyên.
- **User Management/Account DB**: quản lý internal user ID, trạng thái account, liên kết danh tính ngoài và membership.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant C as Shop Web / OAuth2 Client
    participant AS as Identity Server
    participant API as Orders API / Resource Server
    participant DB as Identity Link + Account DB

    U->>C: Mở trang đơn hàng
    C->>AS: OAuth2/OIDC authorization flow
    AS-->>C: Access token cho Orders API
    C->>API: Authorization: Bearer <access-token>
    API->>API: Verify JWT / introspect opaque
    API->>API: Xác nhận issuer, subject, audience
    API->>DB: Lookup theo (issuer, subject) nếu cần
    DB-->>API: internalUserId, enabled, memberships
    API->>API: Check scope + tenant/owner policy
    API-->>C: Dữ liệu được phép hoặc từ chối
~~~

Lưu ý: **OIDC Client** xử lý đăng nhập và ID token; **Resource Server** xác minh **OAuth2 access token** dành cho API. Một ID token thường có audience là Client ID và **không được dùng thay access token** ở Orders API chỉ vì có `sub` hoặc email.

### 1.1. Hai câu hỏi phải được tách

1. **“Danh tính ngoài này là ai?”** — Authorization Server xác nhận subject trong namespace issuer, qua token được API chấp nhận.
2. **“Danh tính ấy tương ứng với account nào và có quyền gì trong ứng dụng?”** — ánh xạ/authorization nội bộ trả lời, có thể bao gồm trạng thái account, tenant membership, owner/assignment.

Token hợp lệ có thể trả lời câu hỏi đầu tiên nhưng **không** tự trả lời câu hỏi thứ hai. Một user có thể đăng nhập đúng nhưng chưa được cấp tài khoản nội bộ hoặc đã bị quản trị viên khóa quyền truy cập Orders API.

## 2. Tìm hiểu `iss` và `sub`

### 2.1. `iss` — issuer

`iss` là định danh của bên phát hành token theo ngữ nghĩa JWT/OIDC profile. Ví dụ:

~~~text
https://identity.example.test/realms/shop
https://login.partner.example.test/tenant/acme
~~~

Đây là hai **namespace danh tính khác nhau**, ngay cả khi cả hai cùng phát một `sub`.

**Không suy ra issuer từ domain email hoặc hostname của request Client.** Issuer phải thuộc tập nguồn mà API **đã cấu hình tin**, và JWT phải được xác minh với issuer/khóa/audience phù hợp; với opaque token, kết quả introspection phải được ràng buộc với Authorization Server tin cậy theo hợp đồng.

### 2.2. `sub` — subject

`sub` là định danh chủ thể do issuer gán trong một token. Ví dụ:

~~~json
{
  "iss": "https://identity.example.test/realms/shop",
  "sub": "00u84x2",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
~~~

Trong kiến trúc người dùng thông thường, subject có thể đại diện user; trong các token khác, đặc biệt token của service/client credentials, nó có thể đại diện Client hoặc một chủ thể không phải người dùng cuối. **Không tự coi mọi access token có `sub` là user account có quyền sở hữu dữ liệu**.

### 2.3. Khóa danh tính ngoài là cặp `(iss, sub)`

| Issuer | Subject | Có thể là ai? |
| --- | --- | --- |
| `https://identity.example.test/realms/shop` | `00u84x2` | Alice trong Identity Server nội bộ |
| `https://login.partner.example.test/tenant/acme` | `00u84x2` | Carol trong IdP đối tác |
| `https://identity.example.test/realms/shop` | `00u84x3` | Bob trong cùng Identity Server |

Nếu database chỉ lưu:

~~~sql
SELECT internal_user_id
FROM external_identities
WHERE subject = '00u84x2';
~~~

thì hàng Alice và Carol có thể **đụng khóa hoặc ánh xạ sai người**. Truy vấn phải có issuer:

~~~sql
SELECT internal_user_id
FROM external_identities
WHERE issuer = :verifiedIssuer
  AND subject = :verifiedSubject;
~~~

**Phải dùng giá trị issuer đã được xác minh**, không phải một header `X-Issuer` do Client tự đặt. Với một issuer duy nhất đã cố định trong config, database vẫn nên lưu issuer để tránh rủi ro khi mở rộng multi-issuer/migration.

### 2.4. Pairwise subject trong OIDC

Một OIDC Provider có thể phát **pairwise subject identifiers**: cùng một user nhận các `sub` khác nhau ở những client/sector khác nhau nhằm hạn chế liên kết danh tính. Vì vậy:

~~~text
User thật: Alice
OIDC Client A nhận sub = pA-123
OIDC Client B nhận sub = pB-456
~~~

Không kết luận hai subject là cùng người hoặc khác người **chỉ từ cách chuỗi khác nhau**; phải căn cứ vào chính sách subject identifier và cơ chế liên kết danh tính được IdP hỗ trợ. API nên dùng định danh **mà Authorization Server cam kết trong access token dành cho API**, không tráo tùy tiện `sub` từ ID token của Client khác.

## 3. Phân biệt `sub`, email, username, client ID và tenant

| Dữ liệu | Chức năng | Có phù hợp làm khóa liên kết ngoài không? |
| --- | --- | --- |
| **`iss + sub`** | Định danh trong namespace issuer | **Thường có**, nếu issuer/profile bảo đảm ngữ nghĩa và ổn định |
| `email` | Thông tin liên hệ | **Không tự động**: thay đổi, tái sử dụng hoặc thiếu xác minh |
| `email_verified` | Cờ email đã được xác minh theo chính sách issuer | Không bảo đảm hai tài khoản cùng email là cùng chủ thể hoặc được phép link |
| `preferred_username` | Tên đăng nhập/hiển thị | Có thể đổi, trùng, tùy issuer |
| `name` | Tên hiển thị | Không phải khóa định danh |
| `client_id` | OAuth2 Client được cấp token | Không đồng nghĩa internal user |
| `azp` | Authorized party trong profile có claim này | Không phải user/tenant ID |
| `aud` | Resource Server/Client nào là đối tượng nhận token | Không phải namespace account hoặc owner |
| `tenant_id` / `org_id` (custom) | Tenant context/membership tùy AS | Không thay internal user ID và policy membership |
| **`internal_user_id`** | Khóa account do ứng dụng quản lý | **Có** cho bảng dữ liệu nghiệp vụ nội bộ |

Ví dụ hai user khác issuer có cùng email:

~~~json
{
  "iss": "https://identity.example.test/realms/shop",
  "sub": "alice-001",
  "email": "shared@example.test",
  "email_verified": true
}
~~~

~~~json
{
  "iss": "https://login.partner.example.test/tenant/acme",
  "sub": "carol-998",
  "email": "shared@example.test",
  "email_verified": true
}
~~~

**Không tự ghép hai danh tính này vào một account nội bộ**. Điều đó có thể dẫn tới **account takeover** nếu email được tái sử dụng, nhà phát hành áp dụng chuẩn xác minh khác nhau hoặc tài khoản ở một nguồn được quản lý bởi bên không đáng tin bằng nguồn còn lại.

### 3.1. `Authentication.getName()` không nhất thiết là email

Spring Security thường trả `sub` làm tên principal của JWT authentication mặc định. Không viết code giả định:

~~~java
String email = authentication.getName(); // Có thể thực tế là sub!
~~~

Nếu ứng dụng cần email, lấy từ một claim đã xác minh **theo hợp đồng** và dùng nó như dữ liệu liên hệ, không phải mặc nhiên làm khóa tra cứu owner.

### 3.2. Subject không có nghĩa “người dùng hiện đang login ở browser”

Trong **Client Credentials** flow, access token có thể đại diện một dịch vụ:

~~~json
{
  "iss": "https://identity.example.test/realms/shop",
  "sub": "nightly-sync-service",
  "client_id": "nightly-sync-service",
  "aud": ["orders-api"],
  "scope": "orders.sync"
}
~~~

Nếu API hỗ trợ service principal, phải có **service-account mapping và authority policy riêng**, không tự tạo internal human-user account hoặc gán mọi service cho một nhân viên.

## 4. Token được tin từ đâu?

Một string JSON chứa `iss` và `sub` **không tự là bằng chứng**; caller có thể tự tạo JWT payload.

~~~text
Bearer token chưa xác thực
  -> kiểm tra chữ ký/issuer/audience/time/type hoặc introspection
  -> verified token / OAuth2AuthenticatedPrincipal
  -> đọc iss + sub
  -> tìm identity link
  -> kiểm tra account/membership/permissions
~~~

### 4.1. Với JWT access token

Spring Security Resource Server thường dùng `JwtDecoder`/`NimbusJwtDecoder` để:

- Xác minh JWS bằng khóa tin cậy/JWKS theo cấu hình.
- Kiểm tra `iss` theo issuer đã cấu hình.
- Kiểm tra `exp` và `nbf` theo validator.
- Kiểm tra `aud` dành cho **Orders API**; không mặc định cho rằng mọi cấu hình issuer tự ràng buộc audience mà ứng dụng muốn.
- Kiểm tra token purpose/type/profile theo AS contract khi cần.

**Đừng tự Base64 decode JWT payload rồi đi query database trước khi Spring xác minh token.**

### 4.2. Với opaque access token

Opaque token thường không có claims mà Resource Server được phép decode local. Spring Security gọi `OpaqueTokenIntrospector`; AS xác nhận trạng thái `active` và trả metadata theo profile.

Ví dụ response minh họa:

~~~json
{
  "active": true,
  "iss": "https://identity.example.test/realms/shop",
  "sub": "00u84x2",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "client_id": "shop-web"
}
~~~

**RFC 7662 không bảo đảm mọi response đều chứa `iss` hoặc `sub`**. Nếu API cần tạo user identity link, AS phải cam kết những trường ấy **hoặc** endpoint/registration phải cho một ràng buộc issuer đáng tin và định danh subject được xác định rõ. Không tự đặt default `iss` hoặc `sub` để “sửa” một response thiếu metadata.

### 4.3. Tách `iss` trong JWT và introspection endpoint trust

JWT có claim `iss` cần được đối chiếu với issuer/JWKS trusted. Trong opaque flow, Resource Server trước hết tin **endpoint introspection, TLS và credential/resource restriction**; claim `iss` nếu AS trả có thể thêm một ràng buộc issuer. Không chấp nhận issuer khác chỉ vì một endpoint trả `active: true` nếu hợp đồng endpoint cho phép introspect nhiều realm mà API chưa giới hạn nguồn.

## 5. Một ví dụ ánh xạ hai cấp

Định nghĩa ba thực thể:

1. **External identity**: `(issuer, subject)` từ Identity Server.
2. **Internal account**: `internal_user_id` do ứng dụng tạo, là khóa bền vững trong bảng nghiệp vụ.
3. **Tenant membership**: account có quyền gì tại tenant nào; có thể thay đổi độc lập với định danh.

~~~mermaid
erDiagram
    INTERNAL_USERS ||--o{ EXTERNAL_IDENTITIES : "linked from"
    INTERNAL_USERS ||--o{ TENANT_MEMBERSHIPS : "belongs to"
    TENANTS ||--o{ TENANT_MEMBERSHIPS : "has members"
    TENANTS ||--o{ ORDERS : "owns"
    INTERNAL_USERS ||--o{ ORDERS : "customer or owner"

    INTERNAL_USERS {
        uuid id PK
        string status
        datetime created_at
    }
    EXTERNAL_IDENTITIES {
        long id PK
        string issuer
        string subject
        uuid internal_user_id FK
        datetime linked_at
    }
    TENANTS {
        uuid id PK
        string name
    }
    TENANT_MEMBERSHIPS {
        uuid user_id FK
        uuid tenant_id FK
        string role
        string status
    }
    ORDERS {
        uuid id PK
        uuid tenant_id FK
        uuid owner_user_id FK
        string status
    }
~~~

Ví dụ:

| External issuer | External subject | Internal user | Tenant |
| --- | --- | --- | --- |
| Internal IdP | `00u84x2` | `usr-0042` | tenant A |
| Partner IdP | `partner-alice-73` | `usr-0042` | tenant A, sau khi liên kết an toàn |
| Partner IdP | `00u84x2` | `usr-1290` | tenant B |

**Một account nội bộ có thể có nhiều external identities**; nhưng mỗi `(issuer, subject)` được liên kết với **tối đa một internal user** nếu thiết kế không hỗ trợ chuyển ownership trong một giao dịch quản trị riêng.

### 5.1. SQL schema minh họa

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE internal_users (
    id UUID PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE external_identities (
    id BIGSERIAL PRIMARY KEY,
    issuer VARCHAR(512) NOT NULL,
    subject VARCHAR(512) NOT NULL,
    internal_user_id UUID NOT NULL
        REFERENCES internal_users(id),
    linked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_external_identity
        UNIQUE (issuer, subject)
);

CREATE INDEX idx_external_identity_user
    ON external_identities(internal_user_id);

CREATE TABLE tenant_memberships (
    user_id UUID NOT NULL REFERENCES internal_users(id),
    tenant_id UUID NOT NULL,
    role_code VARCHAR(80) NOT NULL,
    status VARCHAR(20) NOT NULL,
    PRIMARY KEY (user_id, tenant_id, role_code)
);
~~~

**Unique constraint `(issuer, subject)` là một invariant dữ liệu**, không chỉ là tối ưu query. Nó giúp tránh hai account cùng nhận một danh tính ngoài do race condition khi linking.

### 5.2. Dữ liệu nghiệp vụ nên lưu internal user ID

Đơn hàng:

~~~sql
CREATE TABLE orders (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    owner_user_id UUID NOT NULL REFERENCES internal_users(id),
    status VARCHAR(32) NOT NULL
);
~~~

Không nên đưa `sub` hoặc email trực tiếp vào mọi bảng đơn hàng. Khi IdP đổi issuer hoặc user liên kết danh tính mới, **`owner_user_id` vẫn là khóa account nội bộ ổn định**, dữ liệu nghiệp vụ không phải migrate theo toàn bộ các claim bên ngoài.

### 5.3. Tách việc đổi email khỏi việc đổi identity

Email/phone/display name là **profile attributes**, có thể được cập nhật qua quy trình riêng. Một thay đổi email từ IdP không được tự động đổi `internal_user_id` hoặc chuyển quyền sở hữu đơn. Tương tự, một external identity mới có email giống user cũ **không được tự động kế thừa account đó**.

## 6. Quy tắc chuẩn hóa issuer và subject

Định danh issuer và subject nên được xử lý như **opaque identifiers theo contract**, không “làm đẹp” bằng những thao tác mất tính phân biệt.

Hai issuer:

~~~text
https://identity.example.test/realms/shop
https://identity.example.test/realms/shop/
~~~

có thể được coi là **hai giá trị khác** trong một hợp đồng issuer. Không tùy ý bỏ trailing slash, bỏ realm path, chuyển `https` thành `http`, gộp hostname hoặc so `contains("identity")`.

### 6.1. Không lower-case `sub` tùy ý

~~~text
sub = UserABC
sub = userabc
~~~

Nếu AS coi các giá trị khác nhau, một biến đổi lower-case có thể làm **đụng identity**. Tương tự, không tự trim/normalize Unicode hoặc giải mã các ký tự trong `sub` nếu hợp đồng không quy định. Lưu giá trị đã xác minh **đúng dạng**, với collation/unique index bảo đảm phân biệt theo quy tắc mong muốn.

### 6.2. Canonical issuer theo cấu hình tin cậy

Thường nên sử dụng **issuer canonical đã được AS công bố**, được đối chiếu bởi JWT validator, làm giá trị trong identity link. Nếu AS có aliases chính thức, xử lý mapping alias bằng một policy migration có kiểm soát, không đặt rule “mọi URL cùng host là cùng issuer”.

### 6.3. Không đưa raw token làm identity key

Access token có thể rotate, hết hạn hoặc được phát nhiều lần cho cùng subject. Không dùng toàn chuỗi JWT làm khóa user:

~~~text
Token X và token Y khác nhau
-> vẫn có thể cùng (iss, sub)
-> cùng internal user ID
~~~

Token là credential bí mật, không nên lưu trong bảng external identity hay đưa vào URL/log.

## 7. Hai chiến lược lookup trong Spring Security

Có hai lựa chọn chính:

| Chiến lược | Vị trí lookup | Hành vi | Khi phù hợp |
| --- | --- | --- | --- |
| **A. Lookup ở service** | Sau JWT authentication, tại endpoint cần account | Token có thể được xác thực trước; service chỉ cho phép nghiệp vụ sau khi tìm account | API có endpoint không cần local account, hỗ trợ onboarding hoặc service tokens |
| **B. Lookup trong authentication converter** | Sau JwtDecoder, trước khi tạo Authentication | Mọi request được authentication theo chain yêu cầu local account link/active | Mọi protected request bắt buộc có local user |
| **C. Lookup qua reactive converter** | Trong `Mono`/`Flux` của WebFlux | Như B nhưng non-blocking | WebFlux API bắt buộc link account trong authentication |

**Không có chiến lược nào đúng cho mọi hệ thống**. Điều quyết định là **invariant bảo mật**: phải có account nội bộ ngay khi xác thực token, hay chỉ khi sử dụng một chức năng cụ thể?

### 7.1. Tránh lookup từ controller theo một quy ước thiếu nhất quán

Sai:

~~~java
// Không nên lấy email làm khóa account một cách tự phát ở controller.
User user = userRepo.findByEmail(jwt.getClaimAsString("email"));
~~~

Nếu mỗi controller tự chọn claim khác nhau, hệ thống sẽ có **identity mapping không nhất quán**. Nên tập trung ánh xạ trong một `ExternalIdentityResolver` hoặc service riêng; mỗi endpoint dùng cùng contract `(iss, sub)`.

## 8. Cấu hình Spring Boot Resource Server xác minh JWT

Ví dụ dùng **Spring Boot 3 / Spring Security 6, Java 17+, Servlet/MVC**. Phần đầu tiên phải xác minh token chính xác.

### 8.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Chọn driver DB, migrations và dependency versions theo dự án. Code ví dụ dùng `JpaRepository` đồng bộ trong Servlet stack, **không copy trực tiếp lookup JPA sang Netty WebFlux event-loop**.

### 8.2. application.yml

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${OAUTH_ISSUER_URI}
          jwk-set-uri: ${OAUTH_JWKS_URI}

app:
  security:
    expected-audience: orders-api
~~~

Ví dụ:

~~~text
OAUTH_ISSUER_URI=https://identity.example.test/realms/shop
OAUTH_JWKS_URI=https://identity.example.test/realms/shop/protocol/openid-connect/certs
~~~

Đây là URI minh họa. Production phải dùng endpoint do AS công bố và cơ chế TLS/JWKS/algorithm hợp lệ.

### 8.3. `JwtDecoder` với issuer, thời gian và audience

Khi tự tạo decoder, giữ validation đầy đủ:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class VerifiedJwtConfiguration {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}")
            String issuer,
            @Value("${spring.security.oauth2.resourceserver.jwt.jwk-set-uri}")
            String jwksUri,
            @Value("${app.security.expected-audience}")
            String expectedAudience) {

        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withJwkSetUri(jwksUri).build();

        OAuth2TokenValidator<Jwt> defaultValidators =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
                jwt.getAudience().contains(expectedAudience)
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(
                            "invalid_token",
                            "Invalid audience for Orders API",
                            null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                    defaultValidators, audienceValidator));
        return decoder;
    }
}
~~~

`JwtValidators.createDefaultWithIssuer` áp dụng các validators mặc định phù hợp cùng issuer theo dòng Spring Security đang dùng; **audience** được ràng buộc thêm theo hợp đồng Orders API. Khi tùy chỉnh decoder, không vô tình bỏ issuer/time validation. Với ứng dụng multi-issuer cần cơ chế lựa chọn AuthenticationManager/decoder theo **allowlist issuer tin cậy** chứ không cho một token tự quyết định JWKS URI.

**Đây vẫn chưa phải toàn bộ hợp đồng token**. Một hệ thống có thể còn cần kiểm tra profile access-token/type, thuật toán được phép và các claims bắt buộc. Điều quan trọng là `(iss, sub)` chỉ được dùng sau lớp validation này.

### 8.4. `SecurityFilterChain`

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OrdersApiSecurity {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Đây là Bearer-header-only API; chỉ trong giả định **không sử dụng cookie/session ambient để xác thực request protected**, tắt CSRF cho chain này có thể phù hợp. Một web application dùng session/cookie vẫn cần CSRF protection. `securityMatcher("/api/**")` không bảo vệ những URL bên ngoài phạm vi đó nếu không có chain khác.

`hasAuthority("SCOPE_orders.read")` **không** thay identity lookup, account state, tenant membership hoặc object-level policy.

## 9. Spring Data JPA: ánh xạ `(iss, sub)` sang user nội bộ

### 9.1. Entity external identity

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

import java.util.UUID;

@Entity
@Table(
    name = "external_identities",
    uniqueConstraints = @UniqueConstraint(
        name = "uq_external_identity",
        columnNames = {"issuer", "subject"}),
    indexes = @Index(
        name = "idx_external_identity_user",
        columnList = "internal_user_id")
)
public class ExternalIdentity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 512)
    private String issuer;

    @Column(nullable = false, length = 512)
    private String subject;

    @Column(name = "internal_user_id", nullable = false)
    private UUID internalUserId;

    protected ExternalIdentity() {}

    public ExternalIdentity(
            String issuer, String subject, UUID internalUserId) {
        this.issuer = issuer;
        this.subject = subject;
        this.internalUserId = internalUserId;
    }

    public String getIssuer() { return issuer; }
    public String getSubject() { return subject; }
    public UUID getInternalUserId() { return internalUserId; }
}
~~~

Ví dụ cố ý chỉ lưu identity-link fields. Trong thực tế, cân nhắc account status, audit, created/updated timestamps, provider registration và quy trình migrate; tránh lưu raw JWT hoặc token secrets vào bảng này.

### 9.2. Repository có khóa ghép

~~~java
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ExternalIdentityRepository
        extends JpaRepository<ExternalIdentity, Long> {

    Optional<ExternalIdentity> findByIssuerAndSubject(
            String issuer, String subject);
}
~~~

Sử dụng:

~~~java
String verifiedIssuer = jwt.getIssuer().toString();
String verifiedSubject = jwt.getSubject();

ExternalIdentity identity = identities
    .findByIssuerAndSubject(verifiedIssuer, verifiedSubject)
    .orElseThrow(() -> new UnlinkedIdentityException());
~~~

`UnlinkedIdentityException` là exception nghiệp vụ minh họa do ứng dụng định nghĩa. **JWT đã được decoder xác minh trước khi đến service**, và issuer/subject phải được kiểm tra null/blank trước khi lookup nếu profile yêu cầu.

### 9.3. User account và trạng thái

Identity link không có nghĩa local user vẫn active:

~~~text
externalIdentity -> internalUserId
internalUsers[id].status = DISABLED
~~~

Nếu policy yêu cầu account enabled, phải kiểm tra. Một user có token hợp lệ từ AS nhưng bị khóa trong Orders API **không đương nhiên được tiếp tục truy cập API**. Mặt khác, nếu một số endpoint phục vụ onboarding thì cần định nghĩa riêng phạm vi các request có thể đi qua khi chưa liên kết account.

## 10. Chiến lược A: ánh xạ tại service khi nghiệp vụ cần

Đây thường là lựa chọn **ít ghép chặt hơn** với database: Resource Server xác thực JWT và scope; những service cần internal user ID mới resolve identity.

### 10.1. Service chuyên trách identity resolution

~~~java
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class InternalIdentityService {

    private final ExternalIdentityRepository links;
    private final InternalUserRepository users;

    public InternalIdentityService(
            ExternalIdentityRepository links,
            InternalUserRepository users) {
        this.links = links;
        this.users = users;
    }

    @Transactional(readOnly = true)
    public UUID requireEnabledUser(Jwt jwt) {
        if (jwt.getIssuer() == null
                || jwt.getSubject() == null
                || jwt.getSubject().isBlank()) {
            throw new ResponseStatusException(
                HttpStatus.FORBIDDEN, "Account not available");
        }

        var link = links.findByIssuerAndSubject(
                jwt.getIssuer().toString(),
                jwt.getSubject())
            .orElseThrow(() -> new ResponseStatusException(
                HttpStatus.FORBIDDEN, "Account not available"));

        var user = users.findById(link.getInternalUserId())
            .orElseThrow(() -> new ResponseStatusException(
                HttpStatus.FORBIDDEN, "Account not available"));

        if (!user.isEnabled()) {
            throw new ResponseStatusException(
                HttpStatus.FORBIDDEN, "Account not available");
        }

        return user.getId();
    }
}
~~~

`InternalUserRepository` và `InternalUser` là các thành phần ứng dụng cần triển khai theo schema `internal_users`; ví dụ giả định `isEnabled()` và `getId()` có sẵn. Dùng một thông báo công khai chung giúp tránh lộ vì sao account không được truy cập; log nội bộ có thể phân biệt unlinked/disabled theo policy.

### 10.2. Controller lấy JWT đã xác minh

~~~java
import java.util.Map;
import java.util.UUID;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/me")
class MeController {

    private final InternalIdentityService identities;

    MeController(InternalIdentityService identities) {
        this.identities = identities;
    }

    @GetMapping("/account")
    Map<String, String> account(@AuthenticationPrincipal Jwt jwt) {
        UUID id = identities.requireEnabledUser(jwt);
        return Map.of("internalUserId", id.toString());
    }
}
~~~

`@AuthenticationPrincipal Jwt` hoạt động khi principal của JWT Resource Server vẫn là `Jwt`. Nếu dùng opaque authentication hoặc đổi principal type, hãy điều chỉnh cách lấy principal theo contract, không cast mù.

### 10.3. Khi nào phương án A tốt?

- API có endpoint public/health hoặc resource cần token nhưng không cần local profile.
- Có onboarding cho danh tính vừa được IdP xác thực nhưng chưa có account.
- Có cả user token và service token; mỗi loại dùng policy riêng.
- Chỉ một số thao tác thực sự cần liên kết account, tránh database lookup ở mọi request.

Đổi lại, service cần được gọi ở **mọi nhánh nghiệp vụ sử dụng internal user ID**. Nên tập trung trong một lớp policy/service và có negative tests để không quên ở endpoint mới.

## 11. Chiến lược B: ánh xạ tại JWT authentication converter

Nếu **mọi protected request đều yêu cầu một local user đang enabled**, có thể từ chối ngay ở authentication converter sau khi JwtDecoder đã xác minh token.

### 11.1. `JwtAuthenticationToken` giữ JWT nhưng đổi `getName()`

Đây là điểm dễ gây nhầm:

~~~java
new JwtAuthenticationToken(jwt, authorities, internalUserId);
~~~

Nó vẫn giữ:

~~~text
Authentication.getPrincipal()   -> Jwt đã xác minh
Authentication.getName()        -> internalUserId
Authentication.getAuthorities() -> GrantedAuthorities đã được cấp
~~~

**Đổi `getName()` không tự biến `getPrincipal()` thành domain User**. Khi controller dùng `@AuthenticationPrincipal Jwt`, nó vẫn nhận JWT; nếu cần domain profile phải tra cứu hoặc thiết kế một authentication subtype có chủ đích.

### 11.2. Custom converter trong Servlet Resource Server

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.UUID;

import org.springframework.core.convert.converter.Converter;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtAuthenticationToken;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtGrantedAuthoritiesConverter;

public final class LocalAccountJwtConverter
        implements Converter<Jwt, AbstractAuthenticationToken> {

    private final ExternalIdentityRepository links;
    private final InternalUserRepository users;
    private final JwtGrantedAuthoritiesConverter scopes =
            new JwtGrantedAuthoritiesConverter();

    public LocalAccountJwtConverter(
            ExternalIdentityRepository links,
            InternalUserRepository users) {
        this.links = links;
        this.users = users;
    }

    @Override
    public AbstractAuthenticationToken convert(Jwt jwt) {
        if (jwt.getIssuer() == null
                || jwt.getSubject() == null
                || jwt.getSubject().isBlank()) {
            throw new BadCredentialsException(
                "Missing verified identity");
        }

        String issuer = jwt.getIssuer().toString();
        String subject = jwt.getSubject();

        var link = links.findByIssuerAndSubject(issuer, subject)
            .orElseThrow(() -> new BadCredentialsException(
                "No local account linked"));

        UUID userId = link.getInternalUserId();
        var user = users.findById(userId)
            .orElseThrow(() -> new BadCredentialsException(
                "Local account unavailable"));

        if (!user.isEnabled()) {
            throw new DisabledException(
                "Local account unavailable");
        }

        Collection<GrantedAuthority> scopeAuthorities =
                scopes.convert(jwt);
        List<GrantedAuthority> authorities =
                new ArrayList<>();
        if (scopeAuthorities != null) {
            authorities.addAll(scopeAuthorities);
        }

        // Không cấp ROLE_ADMIN mặc định chỉ vì có identity link.
        return new JwtAuthenticationToken(
                jwt, authorities, userId.toString());
    }
}
~~~

Trong ví dụ, `InternalUserRepository` là repository đồng bộ và converter chạy trong **Servlet/MVC**. Gọi repository tại đây làm authentication **phụ thuộc database ở mỗi request** nếu không có cache/policy khác. Điều này có thể hợp lý nếu tính “account enabled” là điều kiện không thể bỏ qua, nhưng cần tính latency, khả dụng, transaction boundaries và lỗi database.

Đoạn code **không tự ánh xạ role/tenant từ database**. Nếu cần role, phải có mapping allowlist và tenant scoping rõ, tránh nâng quyền vì chỉ có link hợp lệ.

### 11.3. Gắn converter vào SecurityFilterChain

~~~java
@Bean
SecurityFilterChain api(
        HttpSecurity http,
        ExternalIdentityRepository links,
        InternalUserRepository users) throws Exception {

    return http
        .securityMatcher("/api/**")
        .csrf(AbstractHttpConfigurer::disable)
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt -> jwt
            .jwtAuthenticationConverter(
                new LocalAccountJwtConverter(links, users))))
        .build();
}
~~~

Đây là **biến thể thay thế** cấu hình chain ở mục 8, không đăng ký hai chain có matcher trùng rồi nghĩ framework tự chọn converter tùy request. Trong production, tách HTTP methods/scopes đúng yêu cầu; snippet chỉ minh họa vị trí nối converter.

### 11.4. Không tìm thấy link: 401 hay 403?

Nếu một local account đang enabled là **điều kiện bắt buộc của authentication**, converter có thể ném `AuthenticationException` và request thường không có Authentication hợp lệ, dẫn đến **401** qua Bearer entry point.

Nếu token đã được xác thực nhưng một endpoint không cho account chưa liên kết thực hiện thao tác, API cũng có thể chọn **403** ở authorization/business layer. Khi có flow onboarding riêng, **đừng đặt converter bắt buộc link trên tất cả route** khiến caller chưa liên kết không thể truy cập endpoint onboarding. Đây là **quyết định hợp đồng**, không có một status duy nhất đúng cho mọi chính sách.

### 11.5. Dữ liệu user nội bộ không được làm thay token validation

Không tạo principal chỉ vì database tìm thấy `(iss, sub)` trong một token chưa xác minh. Converter ở trên nhận `Jwt` **sau JwtDecoder** trong pipeline Spring Security; không tự Base64 decode Authorization header.

## 12. Chiến lược C: WebFlux và tra cứu phản ứng

Trong **Spring WebFlux**, không được gọi JPA/JDBC blocking `findByIssuerAndSubject` ngay trên Netty event loop hay dùng `.block()` trong JWT converter. Sử dụng R2DBC/reactive repository và trả `Mono<AbstractAuthenticationToken>`.

### 12.1. Reactive repository

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Mono;

interface ReactiveExternalIdentityRepository
        extends ReactiveCrudRepository<ExternalIdentityRecord, Long> {

    Mono<ExternalIdentityRecord> findByIssuerAndSubject(
            String issuer, String subject);
}
~~~

`ExternalIdentityRecord` là entity R2DBC riêng của dự án, **không phải JPA entity ở mục 9**. Database driver/reactive repository phải thực sự không chặn.

### 12.2. Converter reactive

~~~java
import java.util.ArrayList;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtAuthenticationToken;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtGrantedAuthoritiesConverter;

import reactor.core.publisher.Mono;

final class ReactiveLocalIdentityConverter
        implements Converter<Jwt, Mono<AbstractAuthenticationToken>> {

    private final ReactiveExternalIdentityRepository links;
    private final JwtGrantedAuthoritiesConverter scopes =
            new JwtGrantedAuthoritiesConverter();

    ReactiveLocalIdentityConverter(
            ReactiveExternalIdentityRepository links) {
        this.links = links;
    }

    @Override
    public Mono<AbstractAuthenticationToken> convert(Jwt jwt) {
        if (jwt.getIssuer() == null || jwt.getSubject() == null) {
            return Mono.error(new BadCredentialsException(
                    "Missing verified issuer or subject"));
        }

        return links.findByIssuerAndSubject(
                jwt.getIssuer().toString(),
                jwt.getSubject())
            .switchIfEmpty(Mono.error(new BadCredentialsException(
                "Identity is not linked")))
            .map(link -> {
                // link.internalUserId() được lấy từ trusted DB.
                var authorities = new ArrayList<GrantedAuthority>();
                var tokenScopes = scopes.convert(jwt);
                if (tokenScopes != null) {
                    authorities.addAll(tokenScopes);
                }
                return (AbstractAuthenticationToken)
                    new JwtAuthenticationToken(
                        jwt,
                        authorities,
                        link.internalUserId().toString());
            });
    }
}
~~~

Ví dụ này **chưa kiểm tra trạng thái user enabled** để tập trung vào mapping; nếu enabled là điều kiện bắt buộc, phải thêm **reactive lookup + validation** trước khi trả Authentication và fail closed khi user disabled/DB lỗi.

### 12.3. Cấu hình WebFlux

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.web.server.SecurityWebFilterChain;
import reactor.core.publisher.Mono;

@Bean
SecurityWebFilterChain webfluxApi(
        ServerHttpSecurity http,
        Converter<Jwt, Mono<AbstractAuthenticationToken>> converter) {

    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyExchange().denyAll())
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt.jwtAuthenticationConverter(converter)))
        .build();
}
~~~

Đây là code cho **WebFlux**, cần cấu hình `ReactiveJwtDecoder` với issuer/audience và security policy; không trộn nó vào Servlet `HttpSecurity` chain. Khi dùng reactive context, lấy authentication qua `ReactiveSecurityContextHolder` hoặc argument resolver thay vì phụ thuộc một ThreadLocal mutable global.

**Không dùng `.block()` hoặc tự `.subscribe()` trong converter.** Chuỗi `Mono` phải được Spring Security subscribe và xử lý kết quả trước khi request tiếp tục. Nếu lookup thất bại, không tạo principal “guest/admin” mặc định.

## 13. Phân biệt identity linking và authorization theo tenant

Sau khi resolve:

~~~text
(iss, sub) -> internalUserId = usr-0042
~~~

chưa thể kết luận user đó được đọc mọi đơn hàng. Cần kiểm tra:

~~~text
JWT access token hợp lệ
AND aud = orders-api
AND SCOPE_orders.read
AND internalUserId đã được link
AND internalUser.enabled = true
AND internalUser là member active của tenant được yêu cầu
AND resource.tenantId thuộc tenant được phép
AND owner/assignment/role cho phép truy cập bản ghi
~~~

Ví dụ:

| Internal user | Tenant | Role | Quyền |
| --- | --- | --- | --- |
| `usr-0042` | tenant A | Order admin | Có thể quản lý order tại A theo policy |
| `usr-0042` | tenant B | Reader | Chỉ đọc theo policy tenant B |
| `usr-1290` | tenant B | Member | Không có quyền tenant A |

Không tạo một `ROLE_ORDER_ADMIN` **global** từ role ở tenant A rồi cho phép cập nhật tenant B. Scope và role cần được **gắn đúng ngữ cảnh**, còn quyền trên resource được kiểm tra tại domain service/repository.

### 13.1. Tenant selector từ request không phải bằng chứng quyền

~~~http
GET /api/tenants/tenant-B/orders/42
Authorization: Bearer <token-of-usr-0042>
X-Tenant-Id: tenant-B
~~~

`tenant-B` ở path/header là input do caller chọn. Phải tra membership active của `usr-0042` trong tenant B hoặc dùng trusted active-tenant claim đã được AS kiểm chứng. Không chỉ dựa vào việc header được gửi.

### 13.2. Query dữ liệu với internalUserId và tenant

~~~sql
SELECT *
FROM orders
WHERE id = :orderId
  AND tenant_id = :authorizedTenantId
  AND owner_user_id = :internalUserId;
~~~

Nếu Orders API hỗ trợ support staff, policy có thể cho thêm một nhánh assigned support **nhưng vẫn phải ràng buộc tenant**. Không query `findById(id)` rồi lấy dữ liệu của tenant khác trước khi kiểm tra.

### 13.3. Một người dùng có nhiều external identities

~~~text
Issuer internal + sub S1 -> internalUserId usr-0042
Issuer partner  + sub S2 -> internalUserId usr-0042
~~~

Hai danh tính này có thể liên kết vào **cùng account** nếu có một **quy trình account linking được ủy quyền**. Quyền nghiệp vụ được quản lý bằng internal user ID, không cần sao chép dữ liệu owner trong mọi đơn khi user dùng IdP thứ hai.

Điều này khác hoàn toàn việc tự tìm hai account cùng email và tự gộp mà không cần xác nhận.

## 14. Account linking an toàn: bước dễ tạo account takeover

Giả sử Alice đã có local account `usr-0042` qua IdP nội bộ. Alice muốn dùng IdP đối tác để đăng nhập. Nếu ứng dụng chỉ làm:

~~~text
newIdentity.email == existingUser.email
  -> tự link new (iss, sub) vào existingUser
~~~

thì attacker có thể tìm cách sở hữu một external identity trả cùng email, hoặc tận dụng một nguồn có cơ chế email verification yếu hơn. **Email match không được coi là bằng chứng sở hữu account nội bộ.**

### 14.1. Quy trình linking chủ động

Một flow an toàn hơn:

1. User **đã xác thực account hiện tại** bằng cơ chế đang tin cậy, hoặc thực hiện re-authentication cho thao tác nhạy cảm.
2. User chủ động yêu cầu **“Liên kết thêm nhà cung cấp đăng nhập”**; server tạo flow có `state`, PKCE/nonce tương ứng theo OAuth/OIDC Client profile.
3. User hoàn thành authentication tại IdP thứ hai.
4. Server/Client xác minh response theo OIDC/OAuth rules; xác định **issuer và subject mới đã được xác minh**.
5. Server kiểm tra `(iss, sub)` mới chưa thuộc user khác. Nếu đã link, **không tự chuyển ownership**.
6. Server ghi link mới vào **chính internal user ID của session đã được bảo vệ** bằng transaction/unique constraint; ghi audit.
7. Thông báo user, có thể yêu cầu xác nhận hoặc MFA/re-authentication tùy mức độ rủi ro.

**Đây là OAuth2/OIDC Client login/linking flow**, không phải Resource Server tự nhận một JWT tùy ý rồi tạo link. API làm Resource Server có thể cung cấp endpoint account management, nhưng phải giới hạn quyền và chỉ tin authentication đã được xác minh.

### 14.2. Nếu external identity đã link account khác

Phản hồi an toàn thường là **từ chối hoặc chuyển sang quy trình hỗ trợ được kiểm soát**, không tự gộp/hủy account:

~~~text
issuer=partner, sub=S2 -> usr-1290 đã tồn tại
User đang login usr-0042 muốn link S2
=> CONFLICT / manual review, không ghi đè link
~~~

Unique constraint trên `(issuer, subject)` bảo vệ cả race condition khi hai request linking đồng thời.

### 14.3. Đăng ký mới / Just-in-Time provisioning

Một số sản phẩm cần tự tạo account khi người dùng từ AS đáng tin đăng nhập lần đầu. Đây là **JIT provisioning**:

~~~text
Verified (iss, sub) không tìm thấy
  -> xem issuer/client/tenant và chính sách onboarding
  -> yêu cầu invitation / eligibility / consent nếu cần
  -> tạo internal_user mới, mặc định quyền tối thiểu
  -> ghi external_identity link trong transaction
~~~

**Không tự gán admin hoặc membership tenant chỉ vì token có email, domain email hay role string lạ.** Nếu AS có claims về organization/membership, hãy định nghĩa hợp đồng cấp quyền; nếu không, trạng thái mới nên là pending/inactive cho tới khi quy trình cấp quyền hoàn tất.

### 14.4. IdP user bị xóa và `sub` được tái sử dụng?

Hợp đồng của IdP cần quy định subject stability/non-reassignment. Nếu một IdP **tái sử dụng `sub`**, bảng identity link cũ có thể trỏ tới account của người trước. Khi tích hợp nhà phát hành, cần xác nhận thuộc tính **không tái sử dụng subject** theo profile. Nếu không được bảo đảm, phải có định danh/chứng cứ bổ sung và quy trình re-link/verification; không suy rằng mọi `sub` luôn bất biến vô điều kiện.

## 15. Migration nhà phát hành: không tự đổi issuer/subject

Một hệ thống chuyển từ:

~~~text
https://old-id.example.test/realms/shop
~~~

sang:

~~~text
https://new-id.example.test/realms/shop
~~~

không thể đơn giản replace text mọi `issuer` trong database và tin những subject cũ vẫn đại diện cùng người. Một số IdP có thể giữ subject; nhà phát hành khác có thể đổi subject hoàn toàn.

### 15.1. Quy trình migration có kiểm soát

1. Xác định old/new issuer và **tập subject** được bảo đảm tương ứng hay không.
2. Nhận mapping từ nguồn quản trị đáng tin, hoặc yêu cầu re-auth/account linking hợp lệ.
3. Tạo **external identity mới** trỏ tới internalUserId hiện tại, giữ history/audit theo policy.
4. Kiểm tra unique constraints, account conflicts, tenant memberships.
5. Cập nhật trust configuration cho issuer mới; không cho token issuer cũ ở production lâu hơn thời hạn chuyển đổi được phê duyệt.
6. Kiểm thử cả token old/new trong cửa sổ migration; bảo đảm issuer không tin bị từ chối.
7. Sau migration, retire liên kết/issuer cũ theo chính sách mà không phá owner IDs trong business DB.

**Không chỉ dựa email để chuyển mapping**. Nếu dùng email làm gợi ý reconciliation, quyết định cuối cần chứng cứ và kiểm soát ownership.

### 15.2. Trường hợp multi-issuer đồng thời

API có thể hỗ trợ hai issuers trusted trong giai đoạn chuyển đổi. Mỗi issuer cần ràng buộc **issuer → validator/JWKS/audience/profile**.

Trong Spring Security có thể sử dụng `JwtIssuerAuthenticationManagerResolver` hoặc một `AuthenticationManagerResolver<HttpServletRequest>` theo allowlist. Ý tưởng:

~~~java
// Pseudocode/phụ thuộc phiên bản: chỉ tin các issuer đã được đăng ký.
Set<String> trustedIssuers = Set.of(
    "https://old-id.example.test/realms/shop",
    "https://new-id.example.test/realms/shop");

// Resolver chọn AuthenticationManager cho issuer trong allowlist,
// không chấp nhận arbitrary issuer từ token.
~~~

**Không**:

~~~java
// SAI: lấy iss chưa xác thực rồi tự fetch JWKS tùy URL attacker chọn.
String jwksUri = unverifiedTokenIssuer + "/.well-known/jwks.json";
~~~

Một issuer sai có thể dẫn đến SSRF, chấp nhận khóa của attacker hoặc identity confusion nếu hệ thống tự tin mọi endpoint mà token khai báo. **Issuer phải được allowlist và token phải được verify theo đúng khóa/trust của issuer ấy**.

### 15.3. Multi-issuer + same subject phải không trộn account

Negative test:

~~~text
Issuer old + sub=123 -> internal usr-0042
Issuer new + sub=123 -> internal usr-1290
~~~

Nếu migration thực sự xác nhận cùng người, link cả hai vào một internal ID có kiểm soát. Nếu không, **không** được gộp chỉ vì subject string giống nhau.

## 16. Quyết định tạo quyền từ token hay local database

Sau khi xác định internal user ID, ứng dụng có thể có hai nguồn quyền:

| Quyền | Nguồn có thể tin cậy | Đặc điểm |
| --- | --- | --- |
| `SCOPE_orders.read` | Access token đã xác minh | Loại thao tác token được cấp; có thời hạn |
| `ROLE_ORDER_SUPPORT` | Token claim theo hợp đồng hoặc local role DB | Cần mapping allowlist/prefix |
| Tenant membership | Local membership DB hoặc custom claim được AS bảo đảm | Có thể thay đổi sau khi cấp token |
| Owner/assignment | Resource database | Gắn từng order |
| Account disabled | User management DB/IdP policy | Có thể cần thu hồi nhanh |
| Platform-wide support override | Quy trình admin đặc biệt, được audit | Không được cấp ngầm từ role string |

**Định danh không phải quyền.** Chỉ vì `(iss, sub)` có link hợp lệ không có nghĩa account có `ROLE_ADMIN` hoặc được đọc mọi tenant.

### 16.1. Mapping scope không tự tạo role

Spring Security `JwtGrantedAuthoritiesConverter` thường ánh xạ `scope`/`scp` thành authorities dạng `SCOPE_...`. Role custom có thể cần converter riêng.

~~~text
scope: orders.read orders.write
  -> SCOPE_orders.read
  -> SCOPE_orders.write
~~~

Role:

~~~text
ROLE_ORDER_SUPPORT
~~~

không tự xuất hiện nếu token không có claim/mapper theo hợp đồng. Đừng viết `hasRole("ORDER_SUPPORT")` rồi giả định scope `orders.read` sẽ match.

### 16.2. Tenant-specific role không là global authority

Alice có thể là manager ở tenant A nhưng chỉ viewer ở tenant B. Một `ROLE_MANAGER` global không chứa tenant context có thể làm lộ quyền cross-tenant. Chỉ cấp global authorities thực sự toàn cục, còn membership/tenant entitlements nên được đánh giá với **tenant và resource đang truy cập**.

## 17. Phân loại lỗi: token invalid, identity unlinked và thiếu quyền

| Tình huống | Bản chất | Phản hồi thường gặp |
| --- | --- | --- |
| Không có Bearer token | Chưa xác thực | 401, Bearer challenge |
| JWT sai chữ ký/issuer/audience/hết hạn | Token authentication thất bại | 401, có thể `invalid_token` |
| Opaque token inactive | Token authentication thất bại | 401 |
| Token hợp lệ nhưng chưa link local account | Chính sách linking/onboarding | 401 nếu link là điều kiện authentication; 403/luồng onboarding nếu kiểm tra ở app layer |
| Token hợp lệ, local account disabled | Chính sách account | 401/403 theo nơi enforcement, không được cấp quyền |
| Token hợp lệ, account có link, thiếu `orders.read` | Authorization | 403, có thể `insufficient_scope` |
| Scope đúng, account hợp lệ nhưng không thuộc tenant | Tenant policy | 403/404 theo disclosure policy |
| Scope đúng, thuộc tenant nhưng không sở hữu order | Resource policy | 403/404 theo contract |
| Identity DB unavailable khi lookup bắt buộc | Dependency failure | Fail closed; status theo error handling, không chạy nghiệp vụ |

**Không dùng 401/403/404 như phép phân biệt email có được đăng ký hay không cho user chưa xác minh**. Với account-sensitive endpoints, cân nhắc generic messages và rate limiting.

### 17.1. Đừng biến unlinked identity thành account admin

Sai:

~~~java
ExternalIdentity link = links
    .findByIssuerAndSubject(issuer, subject)
    .orElse(createDefaultAdminLink());
~~~

Đây là **fail open / privilege escalation**. Nếu không tìm thấy link, xử lý theo onboarding contract hoặc từ chối, không tự cấp quyền.

### 17.2. Database down khác với không tìm thấy link

~~~text
Lookup trả Optional.empty:
  -> không có external identity link trong DB hiện tại

Lookup ném timeout/connection exception:
  -> chưa đủ thông tin vì dependency lỗi
~~~

Cả hai không được gây unauthorized access khi linking là điều kiện bắt buộc. Nhưng audit/metrics phải phân biệt để điều tra sự cố, không biến toàn bộ timeout thành “user không tồn tại”.

## 18. Cache identity links và thu hồi quyền

Lookup `(iss, sub)` trên mọi request có chi phí; cache có thể giảm tải nhưng cũng tạo rủi ro **stale identity mapping hoặc status**.

| Vấn đề | Policy cần xác định |
| --- | --- |
| Cache key | Cặp `(issuer, subject)`, tách môi trường/tenant context khi cần |
| TTL | Giới hạn theo thời gian chấp nhận stale identity/status |
| Disabled account | Cache invalidation khi khóa user; không tiếp tục cấp quyền quá SLA |
| Identity link thay đổi | Invalidate link cũ/new link và tránh race |
| Role/membership | Cache tách khỏi identity hoặc version policy phù hợp |
| AS key/token revocation | Cache identity **không thay** xác minh token |
| Cache failure | Không tự cấp account/role khi cache và DB cùng unavailable |
| Lưu trữ | Bảo vệ PII/identifiers và không lưu raw access token không cần thiết |

### 18.1. Cache theo `sub` đơn lẻ là lỗi

~~~java
@Cacheable(cacheNames = "identity", key = "#subject")
InternalUser resolve(String issuer, String subject) { ... }
~~~

Nếu hai issuers có cùng subject, cache key có thể trùng và trả **user sai**. Một key đúng phải bao gồm **issuer canonical và subject**:

~~~java
@Cacheable(
    cacheNames = "identity",
    key = "{#issuer, #subject}")
InternalUser resolve(String issuer, String subject) { ... }
~~~

Đây là minh họa cho caching ở service; TTL/invalidation phải được cấu hình tại cache provider. Nếu account disabled, cache một `InternalUser` vô hạn có thể tiếp tục trả user enabled cũ.

### 18.2. Không cache Authentication vĩnh viễn

JWT signature, expiry, issuer, audience vẫn phải được kiểm tra theo security pipeline. Cache identity link **không** làm token hết hạn trở nên hợp lệ và không nên đồng nhất token X/Y với account chỉ bằng một cache entry thiếu issuer.

### 18.3. Time-of-check/time-of-use

Nếu converter xác nhận account enabled ở T1, còn tenant membership bị thu hồi ở T2 trước khi cập nhật đơn, những thao tác nhạy cảm có thể cần **kiểm tra quyền gần thời điểm ghi** hoặc transactional guard. Một identity link đúng tại đầu request không bảo đảm mọi quyền còn hiệu lực đến cuối workflow.

## 19. Kiểm thử identity mapping ở nhiều lớp

Phải phân biệt:

1. **Unit test resolver/repository mapping** — từ `(iss, sub)` tới internal user.
2. **Spring Security HTTP authorization test** — authentication và route policy khi đã có principal.
3. **JWT/opaque protocol integration test** — token thật sự được xác minh từ AS/JWKS/introspection.
4. **Account linking workflow test** — không gộp sai identity hoặc race tạo link.
5. **Tenant/resource policy test** — link đúng nhưng vẫn không được đọc bản ghi khác quyền.

### 19.1. Ma trận test cơ sở

| Case | Issuer | Subject | Trạng thái link | Kỳ vọng |
| --- | --- | --- | --- | --- |
| I01 | Internal | `alice-01` | Link tới `usr-0042` enabled | Resolve `usr-0042` |
| I02 | Partner | `alice-01` | Link tới `usr-1290` enabled | Resolve **`usr-1290`**, không trộn |
| I03 | Internal | `unknown` | Không có link | Unlinked/onboarding/deny theo policy |
| I04 | Internal | `alice-01` | User disabled | Không thực thi protected action |
| I05 | Internal | `alice-01` | Link nhưng user record bị xóa/sai FK | Fail closed và điều tra integrity |
| I06 | Partner | `partner-alice` | Link cùng `usr-0042` đã được xác nhận | Cùng internal ID |
| I07 | Untrusted issuer | `alice-01` | DB tình cờ có link | **Token từ issuer đó vẫn bị từ chối** |
| I08 | Internal | JWT token chữ ký sai nhưng `sub=alice-01` | DB có link | Decoder từ chối trước lookup/ủy quyền |
| I09 | Internal | JWT `aud=billing-api` | DB có link | Decoder/audience validator từ chối |
| I10 | Internal | Token hết hạn | DB có link | Không xác thực |
| I11 | Internal | User có cùng email với user partner | Hai subjects khác nhau | **Không auto-merge** |
| I12 | Internal | Cùng issuer+subject hai requests tạo link đồng thời | Race | Unique constraint giữ một owner |
| I13 | Internal | Alice có role tenant A | Request tenant B | Không dùng role A tại B |
| I14 | Internal | Client Credentials service token | Không có human-user link | Chính sách service riêng |

**I02, I07, I08 và I11 là các negative tests bảo vệ trust boundary**. Nếu chỉ test một issuer và một user luôn thành công, rất dễ bỏ sót lỗi cross-issuer/cross-account.

## 20. Unit test bằng JUnit và Mockito

Ví dụ một resolver độc lập:

~~~java
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class ExternalAccountResolver {

    private final ExternalIdentityRepository identities;

    public ExternalAccountResolver(
            ExternalIdentityRepository identities) {
        this.identities = identities;
    }

    public UUID resolve(String verifiedIssuer,
                        String verifiedSubject) {
        if (verifiedIssuer == null || verifiedIssuer.isBlank()
                || verifiedSubject == null
                || verifiedSubject.isBlank()) {
            throw new IllegalArgumentException(
                "Verified identity is missing");
        }
        return identities
            .findByIssuerAndSubject(
                verifiedIssuer, verifiedSubject)
            .map(ExternalIdentity::getInternalUserId)
            .orElseThrow(UnlinkedIdentityException::new);
    }
}
~~~

`UnlinkedIdentityException` là custom exception của dự án. Tên tham số `verifiedIssuer` nhấn mạnh **caller của resolver có trách nhiệm chỉ truyền identity đã được xác minh**. Một resolver public method nhận hai string **không tự xác minh JWT**, vì vậy hãy giữ nó trong service boundary được bảo vệ, không expose trực tiếp thành endpoint nhận issuer/subject tùy ý từ người dùng.

### 20.1. Test hai issuers cùng subject

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class ExternalAccountResolverTest {

    private static final String ISSUER_SHOP =
        "https://identity.example.test/realms/shop";
    private static final String ISSUER_PARTNER =
        "https://login.partner.example.test/tenant/acme";

    @Test
    void sameSubjectFromDifferentIssuersMapsToDifferentUsers() {
        var repo = mock(ExternalIdentityRepository.class);

        UUID shopUser =
            UUID.fromString("11111111-1111-1111-1111-111111111111");
        UUID partnerUser =
            UUID.fromString("22222222-2222-2222-2222-222222222222");

        when(repo.findByIssuerAndSubject(
                ISSUER_SHOP, "shared-sub"))
            .thenReturn(Optional.of(new ExternalIdentity(
                ISSUER_SHOP, "shared-sub", shopUser)));

        when(repo.findByIssuerAndSubject(
                ISSUER_PARTNER, "shared-sub"))
            .thenReturn(Optional.of(new ExternalIdentity(
                ISSUER_PARTNER, "shared-sub", partnerUser)));

        var resolver = new ExternalAccountResolver(repo);

        assertEquals(shopUser,
            resolver.resolve(ISSUER_SHOP, "shared-sub"));
        assertEquals(partnerUser,
            resolver.resolve(ISSUER_PARTNER, "shared-sub"));
    }
}
~~~

Test cho thấy **cùng `sub` không tạo ra cùng internal user** khi issuer khác. Nó chưa chứng minh JWT token đã ký hợp lệ; đó là trách nhiệm integration tests.

### 20.2. Missing identity không tạo user mặc định

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.*;
import java.util.Optional;

@Test
void missingLinkMustNotBecomeAnotherUser() {
    var repo = mock(ExternalIdentityRepository.class);
    when(repo.findByIssuerAndSubject(
            ISSUER_SHOP, "unknown"))
        .thenReturn(Optional.empty());

    var resolver = new ExternalAccountResolver(repo);

    assertThrows(UnlinkedIdentityException.class,
        () -> resolver.resolve(ISSUER_SHOP, "unknown"));
}
~~~

Đây là **phần thân test** dùng cùng class constants/imports như ví dụ trước. Khi test logic JIT provisioning, thay expectation theo policy provisioning nhưng **không auto-link vào user cũ dựa email**.

### 20.3. Test không normalize subject mù

~~~text
issuer=shop, sub=UserABC -> usr-0042
issuer=shop, sub=userabc -> usr-1290
~~~

Nếu hợp đồng issuer coi hai subject khác nhau, resolver và database index phải **bảo toàn khác biệt ấy**. Dùng những fixtures có dấu hoa/thường, Unicode hoặc trailing characters theo schema AS thực sự để phát hiện normalization sai.

## 21. Test Spring Security bằng MockMvc và JWT giả lập

`SecurityMockMvcRequestPostProcessors.jwt()` có thể đặt `JwtAuthenticationToken` vào request mà không phải gọi JWKS. Nó rất hữu ích để kiểm thử code **sau authentication**.

Ví dụ:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

mockMvc.perform(get("/api/orders/42")
        .with(jwt().jwt(token -> token
            .issuer("https://identity.example.test/realms/shop")
            .subject("alice-01")
            .claim("scope", "orders.read"))
            .authorities(new SimpleGrantedAuthority(
                "SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

Đây là **phần thân test** với controller/service/data fixture phù hợp, và là **happy path giả lập**. Nó không chứng minh:

- JwtDecoder xác minh JWS signature.
- Issuer hoặc audience thực sự bị kiểm tra.
- Custom `JwtAuthenticationConverter` được gọi trong pipeline.
- JWKS rotation hoạt động.

`jwt()` có thể bỏ qua converter/decoder bằng cách tạo Authentication trực tiếp. Vì vậy nếu mục tiêu là kiểm tra việc **lookup local identity ở converter**, phải unit test converter riêng và viết integration test với Authorization header chứa JWT thật.

### 21.1. Unit test converter với mock repositories

Một test tập trung:

~~~text
Input: Jwt verified object
iss=shop, sub=alice-01, scope=orders.read
ExternalIdentityRepository: (shop,alice-01) -> usr-0042
InternalUserRepository: usr-0042 enabled
Expected JwtAuthenticationToken.getName() = UUID usr-0042
Expected getPrincipal() instanceof Jwt
Expected authorities contains SCOPE_orders.read
~~~

Negative:

~~~text
unlinked subject -> AuthenticationException
disabled account -> AuthenticationException
DB timeout -> no authenticated principal / fail closed
issuer khác + sub giống -> lookup key khác, không lấy nhầm user
~~~

**Không mock JWT object chưa xác minh rồi suy ra việc mapping an toàn với token thật.** Trong unit test, `Jwt` là fixture để test code sau decoder; trong production, only authenticated pipeline được phép gọi converter.

## 22. Integration test bằng JWT ký thật và mock JWKS

Một test end-to-end nên:

1. Tạo cặp RSA/EC **chỉ cho môi trường test**; không tái sử dụng private key production.
2. Cấu hình mock JWKS endpoint công bố public key và `kid` theo test.
3. Dùng `JwtDecoder`/Resource Server thật với issuer/audience validators.
4. Phát JWT có chữ ký thật, claims đúng contract.
5. Gửi `Authorization: Bearer <signed-jwt>` tới HTTP endpoint qua MockMvc hoặc real HTTP client.
6. Kiểm tra converter/service sử dụng **`(iss, sub)` đã xác minh**, trả đúng internalUserId và resource data.
7. Tạo một token khác có **cùng sub nhưng issuer khác được allowlist** (ký bằng key tương ứng) và xác nhận mapping khác.
8. Tạo token với issuer untrusted, audience khác, signature sai hoặc hết hạn — phải bị **authentication từ chối trước business policy**.

### 22.1. Test chống lạm dụng claim `iss`

Đừng chỉ thay giá trị `iss` trong `Jwt` fixture. Một negative test có giá trị hơn:

~~~text
JWT tự khai báo iss = trusted-shop-issuer
Nhưng được ký bằng khóa attacker/issuer khác
-> JwtDecoder phải từ chối
-> ExternalAccountResolver không được coi JWT là chứng cứ account
~~~

Nếu API multi-issuer, kiểm tra route selection và allowlist: một issuer ngoài tập tin cậy **không thể làm API tự tải JWKS bất kỳ** dựa trên payload do caller kiểm soát.

### 22.2. Opaque introspection integration test

Mock Authorization Server trả:

~~~json
{
  "active": true,
  "iss": "https://identity.example.test/realms/shop",
  "sub": "alice-01",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
~~~

Resource Server phải dùng endpoint/credential trusted, parse đúng metadata, rồi ánh xạ sang internal ID. Negative cases:

- `active:false` → không xác thực.
- `active:true` nhưng audience khác → từ chối.
- Thiếu `iss` khi contract bắt buộc field đó → từ chối.
- `iss` thuộc issuer chưa được tin → từ chối.
- `sub` không có link → xử lý theo account policy.
- Endpoint timeout → không được fail open.

**Không tự coi `username` từ introspection là `sub`** nếu AS không định nghĩa tương đương. Account mapping yêu cầu subject ổn định và ràng buộc issuer.

## 23. Unit/integration test an toàn khi linking account

Một flow linking cần test cả success và conflict:

| Case | Account đang login | External identity mới | Kỳ vọng |
| --- | --- | --- | --- |
| L1 | usr-0042 | `(partner,S2)` chưa liên kết | Link mới sau flow xác minh đầy đủ |
| L2 | usr-0042 | `(partner,S2)` đã thuộc usr-1290 | Từ chối, không chuyển link |
| L3 | usr-0042 | Token mới không đúng issuer/audience/profile | Không tạo link |
| L4 | usr-0042 | Cùng email nhưng `(iss,sub)` khác | Không auto-link theo email |
| L5 | Không có authenticated current account | Request link vào usr-0042 | Không cho phép |
| L6 | Hai requests tạo cùng `(iss,sub)` | Race | Unique constraint giữ single owner |
| L7 | User account disabled | Cố thêm IdP | Từ chối theo policy account |
| L8 | External identity link bị revoke | Token cũ vẫn còn hạn | Quy tắc invalidation/revocation áp dụng |
| L9 | User chuyển issuer qua migration | New verified (iss,sub) | Giữ đúng internal ID sau mapping có kiểm soát |

### 23.1. Race condition phải test trên database thật

Unit tests có thể mô phỏng repository, nhưng **chỉ integration test transaction/unique index** mới chứng minh hai linking requests không cùng tạo hai owner cho một external identity. Khi bắt unique constraint violation, trả conflict an toàn và không ghi đè ID hiện hữu.

### 23.2. Tránh replay linking callback

OAuth2/OIDC linking callback phải kiểm tra `state`, PKCE/nonce theo flow, redirect URI, session người khởi tạo và ràng buộc một lần dùng. Không cho attacker gửi lại callback hoặc đổi account context giữa lúc bắt đầu và hoàn tất link để gắn identity vào user khác.

## 24. Multi-tenant và identity resolution

Một user nội bộ có thể thuộc nhiều tenants:

~~~text
(iss, sub) -> usr-0042
usr-0042 -> tenant A: MANAGER
usr-0042 -> tenant B: VIEWER
~~~

Internal identity mapping trả lời “**ai**”, tenant authorization trả lời “**được làm gì ở tổ chức nào**”.

Không viết:

~~~java
// SAI: chỉ vì user thuộc tenant A không có quyền tenant B.
if (userId != null) {
    return orderRepository.findById(orderId);
}
~~~

Thay vào đó, service cần xác định tenant context đã được xác minh, kiểm tra membership/role ở tenant đó và truy vấn:

~~~sql
SELECT *
FROM orders
WHERE id = :orderId
  AND tenant_id = :allowedTenant
  AND owner_user_id = :internalUserId;
~~~

Với support/manager, điều kiện owner có thể thay bằng policy assignment nhưng **tenant boundary vẫn giữ**. Test một token của usr-0042 dùng ở tenant A cố đọc order B; internal ID đúng **không làm quyền tenant B tự xuất hiện**.

### 24.1. Tenant trong JWT là custom claim theo hợp đồng

`tenant_id` không phải claim bắt buộc của OAuth2/OIDC access token. Nếu AS phát token với một active tenant, API có thể dùng claim ấy sau verification, nhưng vẫn cần kiểm tra tenant resource. Nếu user có nhiều memberships, có thể cần tra cứu động. Không dùng raw `X-Tenant-Id` làm bằng chứng membership.

### 24.2. Quyền thu hồi có thể nhanh hơn token expiry

Access token còn 20 phút nhưng user bị khóa hoặc rời tenant sau 1 phút. Nếu doanh nghiệp yêu cầu thu hồi gần tức thời, chỉ tin JWT và cache membership lâu có thể không đáp ứng. Cần TTL, revocation, lookup động hoặc token lifetime theo SLA, không tự tuyên bố mọi token còn hạn đều đủ quyền.

## 25. Vấn đề riêng của OIDC: ID token, UserInfo và external profile

### 25.1. Không dùng ID token làm credential cho Resource Server

OIDC ID token dành cho **OIDC Client** và thường có `aud` tương ứng Client ID. Orders API không được nhận ID token thay OAuth access token nếu `aud` không dành cho Orders API, dù ID token có chữ ký hợp lệ và `sub` trùng user.

### 25.2. UserInfo không tự là nguồn thay thế access-token authentication

OIDC Client có thể gọi UserInfo endpoint để lấy claims profile theo protocol. Resource Server **không mặc định gọi UserInfo cho mỗi request** để xác minh Bearer access token, vì:

- Access token phải được xác minh theo Resource Server contract.
- UserInfo cung cấp user claims theo OIDC scope/profile, không tự ràng buộc authorization trên Orders API.
- Kết quả UserInfo và subject trong ID token có những quy tắc đối chiếu riêng cho OIDC Client.
- Email/profile có thể thay đổi, không thay `(iss, sub)` làm identity key.

Nếu cần đồng bộ hồ sơ, hãy định nghĩa một workflow/profile sync đáng tin, có consent/privacy và không lấy profile attributes làm bằng chứng tự động để gộp accounts.

### 25.3. Subject của ID token và access token

Trong một OIDC deployment, `sub` có thể cùng thể hiện user, nhưng cấu trúc token và chính sách subject có thể khác theo Client, grant hoặc privacy profile. Resource Server chỉ được sử dụng **`sub` trong access token mà nó đã xác minh**, và cần contract từ AS về ngữ nghĩa claim. Không tự đọc `sub` từ một ID token khác trong browser để quyết định owner tài nguyên.

## 26. Bảo vệ thông tin cá nhân và audit

External identity link là dữ liệu nhạy cảm vì nối danh tính ngoài với account nội bộ. Một hệ thống vận hành nên:

- Chỉ cấp quyền đọc/sửa link cho service có trách nhiệm và admin được phép.
- Không lưu raw access token/refresh token chỉ để tra cứu identity.
- Tránh trả bảng `(issuer, subject, internalUserId)` công khai cho Client.
- Log audit thao tác link/unlink/migrate, người khởi tạo và kết quả, với dữ liệu tối thiểu.
- Có cơ chế xử lý account deletion, unlink, lịch sử giao dịch và yêu cầu pháp lý theo chính sách tổ chức.
- Không dùng `email` hay `sub` làm metric label có cardinality vô hạn.
- Phân biệt token data **chưa xác minh** với claims được trusted decoder trả về trước khi ghi security event.

### 26.1. Logout không tự xóa external identity

Logout session/OAuth Client hoặc thu hồi access token **không đồng nghĩa xóa account link**; account link là quan hệ lâu dài theo policy. Ngược lại, unlink một external identity không nhất thiết thu hồi mọi access token đã phát; nếu cần chặn ngay, API phải kiểm tra link hiện hành hoặc invalidate caches phù hợp.

### 26.2. Xóa link không được làm “chiếm lại” account khác

Sau unlink, nếu same external identity đăng nhập lại, không tự chọn user theo email hoặc user gần đây. Phải đi qua onboarding/linking xác minh mới; nếu unique key/reassignment policy đặc biệt, cần audit và quy trình quản trị rõ.

## 27. Những hiểu nhầm phổ biến

**“`sub` luôn duy nhất trên toàn Internet.”** Sai. Nó có ý nghĩa trong namespace issuer theo hợp đồng, vì vậy cần `(iss, sub)`.

**“Hai issuer dùng cùng sub là cùng người.”** Sai. Có thể là hai users hoàn toàn khác.

**“Hai external identities có cùng email thì luôn cùng người.”** Sai. Email mutable/reusable và phụ thuộc chính sách xác minh.

**“`email_verified: true` cho phép tự động ghép mọi account.”** Không. Nó không phải sự đồng ý hoặc bằng chứng sở hữu account ở một issuer khác.

**“`preferred_username` ổn định hơn sub.”** Không mặc định. Username thường có thể đổi hoặc trùng.

**“`Authentication.getName()` luôn là internal user ID.”** Không. JWT default thường dùng sub; chỉ khi converter mapping rõ mới thành internal ID.

**“Đổi name thì `getPrincipal()` trở thành domain User.”** Không với `JwtAuthenticationToken(jwt, authorities, name)`; principal vẫn là Jwt.

**“Tìm được link nghĩa là có quyền admin.”** Sai. Identity mapping và authorization là hai tầng khác nhau.

**“Một token ký đúng của Issuer A được dùng cho mọi API.”** Sai. Cần kiểm tra audience, purpose, time và các validators theo hợp đồng.

**“JWT có thể decode payload trước, verify chữ ký sau.”** Không được sử dụng claims chưa xác minh để cấp danh tính/quyền.

**“Opaque token lúc nào cũng có `iss`/`sub`.”** Không. Introspection response phụ thuộc AS contract.

**“Multi-issuer chỉ cần thêm issuer vào danh sách; có thể dùng chung mọi roles và keys.”** Không. Mỗi issuer cần trust/claim semantics/authority mapping phù hợp.

**“Đổi issuer URL chỉ việc replace text trong external_identities.”** Không. Phải xác minh mapping subject và ownership trong migration.

**“JWT còn hạn thì local account luôn enabled.”** Không. Account có thể bị khóa hoặc membership bị thu hồi sau khi token được cấp.

**“Cache theo subject là đủ.”** Không. Thiếu issuer gây identity collision; cache còn cần TTL/invalidation.

**“Một user có internal ID đúng là đọc được mọi tenant.”** Không. Tenant/owner/resource policy vẫn phải kiểm tra.

**“Client Credentials token cũng là human user vì có sub.”** Không mặc định. Cần service principal policy riêng.

**“MockMvc `jwt()` pass chứng minh signed JWT và decoder đúng.”** Không. `jwt()` thường tạo mock Authentication; cần signed JWT integration test.

**“JPA repository gọi trong reactive converter bằng `Mono.just` là non-blocking.”** Không. Blocking I/O vẫn block; dùng reactive driver hoặc cô lập legacy code theo chính sách.

## 28. Checklist thiết kế và tích hợp nhà phát hành

1. Authorization Server nào được tin? Issuer canonical và JWKS/introspection endpoint lấy từ đâu?
2. Access token có `iss`, `sub`, `aud`, thời hạn và token type/profile theo hợp đồng nào?
3. JwtDecoder/introspection đã xác minh token trước mọi lookup chưa?
4. Identity key có dùng **`(iss, sub)`** và unique constraint không?
5. Có tránh dùng email/username làm khóa account hoặc auto-merge không?
6. Subject có stable/non-reassignable theo profile nhà phát hành không?
7. IdP có pairwise subjects, multi-client hoặc account migration đặc thù không?
8. External identity table có FK tới internal user ID và audit linking không?
9. Một internal account có thể link nhiều identities; quy trình link/unlink có re-auth/consent phù hợp không?
10. Không tìm thấy link thì onboard, 401 hay 403? Có contract tường minh không?
11. Account disabled và membership revoked được phản ánh theo SLA nào?
12. Cần lookup ngay lúc authentication hay chỉ khi nghiệp vụ cần?
13. Servlet JPA lookup có latency/availability/cache policy không? WebFlux có non-blocking không?
14. Service/Client Credentials tokens có principal/permission policy riêng không?
15. Multi-issuer được allowlist và không fetch JWKS tùy ý từ claim chưa xác minh không?
16. Tenant-scoped roles và object-level authorization có độc lập identity link không?
17. Cache có key issuer+subject và invalidation khi link/status thay đổi không?
18. API có log raw Bearer token, email/subject hoặc linked identities quá mức không?
19. Test có same subject/different issuer, same email/different subjects, missing link, disabled user và migration conflict không?
20. Signed-JWT/introspection integration test có chứng minh decoder thực sự xác minh token không?

## 29. Bài tập tình huống

**Tình huống A.** IdP Shop cấp `iss=shop`, `sub=123`; IdP Partner cấp `iss=partner`, `sub=123`. Có được mặc định ánh xạ cả hai sang một internal user?

**Không.** `sub` chỉ có ý nghĩa trong namespace issuer. Cần hai external identity keys riêng, và chỉ được gắn cùng internal user sau một flow liên kết đã được xác minh.

**Tình huống B.** Alice thay email từ `alice@old.example` sang `alice@new.example` nhưng `(iss, sub)` không đổi. Có phải tạo account nội bộ mới?

**Không thông thường.** Internal identity link vẫn trỏ tới account cũ; email là profile attribute được cập nhật theo policy.

**Tình huống C.** Carol có cùng email đã verified với Alice ở một IdP khác. Hệ thống tự ghép Carol vào account Alice. Sai ở đâu?

**Account linking thiếu chứng cứ sở hữu account**, có thể tạo account takeover. Không auto-link chỉ bằng email, kể cả `email_verified`.

**Tình huống D.** Một JWT có `iss=trusted-shop` và `sub=alice` nhưng chữ ký sai. Database có identity link cho Alice. Có được tạo Authentication?

**Không.** Token phải qua decoder/JWS/validator. Identity link tồn tại không làm một JWT giả thành hợp lệ.

**Tình huống E.** Orders API đổi `JwtAuthenticationToken` name thành internal ID. Controller `@AuthenticationPrincipal Jwt jwt` có tự nhận `InternalUser` không?

**Không.** Principal vẫn là Jwt; chỉ `getName()` đổi. Muốn domain user, dùng service lookup hoặc authentication subtype được thiết kế riêng.

**Tình huống F.** JWT hợp lệ, account link có, nhưng local user disabled. Có được chấp nhận vì token chưa hết hạn?

**Không** nếu policy API yêu cầu local user active. Cần kiểm tra trạng thái và xử lý cache/revocation phù hợp.

**Tình huống G.** JWT hợp lệ, internal user `usr-0042` có role ADMIN tenant A nhưng đang yêu cầu order tenant B. Có quyền không?

**Không mặc định.** Account identity không mang theo role A sang B; cần tenant membership/resource policy đúng ngữ cảnh.

**Tình huống H.** Resource Server dùng opaque introspection và response chỉ có `active:true`, `scope`, `client_id`, không có `sub` hay issuer binding. Có thể dùng `client_id` làm user ID?

**Không.** `client_id` là OAuth Client identifier. Cần contract về subject và issuer trước khi tạo human user mapping; service tokens phải theo policy khác.

**Tình huống I.** Một developer bọc JPA repository trong `Mono.just(repository.findByIssuerAndSubject(...))` rồi gọi từ WebFlux JWT converter. Có non-blocking không?

**Không.** Repository blocking đã chạy trước khi Mono được tạo. Cần reactive repository hoặc giải pháp cô lập blocking I/O có kiểm soát.

**Tình huống J.** Trong migration, new issuer cấp một `sub` giống old issuer. Có thể tự thay issuer trong DB mà không verify người dùng?

**Không.** Subject giữa hai issuer không mặc nhiên cùng danh tính. Cần mapping được chứng thực hoặc account linking/re-auth, rồi thêm link mới một cách có kiểm soát.

**Tình huống K.** Unit test resolver pass cho `(iss,sub)`, nhưng production trả 401 do issuer claim không được phép. Unit test có sai không?

**Chưa chắc.** Unit test chỉ kiểm tra mapping; decoder/integration test phải xác nhận issuer/JWKS/audience hợp lệ trước resolver. Không nới validator để “cho resolver chạy”.

**Tình huống L.** Một user có hai access tokens với `scope` khác nhau nhưng cùng `(iss,sub)`. Có được dùng identity cache để tự cấp scope từ token cũ?

**Không.** Cả hai token có thể cùng internal user ID, nhưng **authorities của mỗi request phải đến từ token/policy hiện hành**, không lấy scope/role không đúng từ cache identity.

---

## Kết luận

Khi tích hợp nhà phát hành vào **Spring Security OAuth 2.0/OIDC Resource Server**, cách tiếp cận bền vững là xác minh access token **trước**, rồi sử dụng **issuer và subject đã được tin cậy** làm khóa liên kết **`(iss, sub)`** đến **internal user ID**. Không dùng email, username, Client ID hoặc raw token làm khóa người dùng nội bộ; hai issuer có thể cấp cùng subject, còn một internal user có thể được liên kết với nhiều external identities qua quy trình **account linking có kiểm soát**.

Trong Spring Security Servlet, có thể lookup tại **service** khi nghiệp vụ cần, hoặc tại **`JwtAuthenticationConverter`** nếu mọi protected request bắt buộc có account nội bộ. Với WebFlux, lookup phải nằm trong **`Mono`/`Flux` non-blocking**, không gọi `.block()` hay JPA đồng bộ trên event loop. Sau ánh xạ, `Authentication.getName()` có thể là internal ID trong khi principal vẫn là `Jwt`; **identity resolution không thay thế scope, role, tenant membership và resource-level authorization**.

Để tránh account takeover và cross-issuer confusion, hãy dùng **unique constraint `(issuer, subject)`, không auto-merge theo email, allowlist issuer/JWKS, kiểm soát migration/link/unlink, fail closed khi thiếu chứng cứ**, và kiểm thử nhiều tầng: mapping unit tests, account-linking concurrency, HTTP authorization cùng **signed-JWT hoặc introspection integration tests**. **Token hợp lệ chứng minh một external identity; chỉ policy nội bộ mới quyết định external identity ấy gắn với account nào và được phép làm gì.**
