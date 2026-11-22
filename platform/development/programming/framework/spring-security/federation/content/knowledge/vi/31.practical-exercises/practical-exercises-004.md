# Tích hợp hai IdP với định danh ổn định và cách ly dữ liệu tenant

> **Chủ đề:** Spring Security – federation. **Mạch kiến thức:** Thực hành tổng hợp. Bài lab hướng dẫn tích hợp hai OpenID Connect Identity Provider (IdP/OP) vào một Spring Boot 3.x / Spring Security 6.x Servlet app sử dụng Java 17+, ánh xạ danh tính bằng **`(issuer, subject)`**, và bảo vệ dữ liệu nhiều tenant bằng **authorization ở service** cùng **truy vấn SQL có tenant_id**. Có cấu hình IdP mẫu, Maven project, Java code, SQL schema, MockMvc tests, chương trình Java 17 độc lập, runbook, ma trận negative tests và mở rộng sang SAML2/Resource Server.

## 1. Mục tiêu và mô hình

Ứng dụng `portal` phục vụ hai tenant độc lập:

- **North:** OIDC issuer `http://localhost:8180/realms/north`; Spring `registrationId=north`; client `portal-north`.
- **South:** OIDC issuer `http://localhost:8180/realms/south`; Spring `registrationId=south`; client `portal-south`.
- North và South có accounts/grants/notes riêng. Một user ở North **không có quyền mặc định** đọc tài liệu South.
- Hai user ở hai IdP **có thể cùng email, cùng username, cùng chuỗi `sub`**: chúng vẫn là hai danh tính khác nhau.
- `tenantId` trong URL là **resource selector không đáng tin**; app phải xác minh server-side từ authenticated principal và approved tenant membership.
- Bài lab chọn **một IdP ↔ một tenant** để các ca kiểm thử rõ ràng. Production có thể cho một IdP phục vụ nhiều tenants, hoặc một tenant tin nhiều IdPs, nhưng phải có allowlist issuer/tenant và business grants độc lập.

**Tiêu chí PASS:** North authenticated và đã được cấp `NOTE_READ` trên North đọc `GET /api/tenants/north/notes/1` được 200; chính user đó gọi `/api/tenants/south/notes/1` bị 403; South làm ngược lại; unknown issuer/sub/tenant bị deny; account bị disable vẫn bị deny dù app session còn. Không được có output nào chứa nội dung tài liệu tenant khác.

### 1.1. IdP không đồng nghĩa với tenant hay account

| Trường | Nơi phát sinh | Ví dụ | Ý nghĩa |
| --- | --- | --- | --- |
| `iss` | OIDC ID Token đã verify | `.../realms/north` | Namespace/trust boundary của OP |
| `sub` | OP đã verify | `same-sub` | User ID duy nhất **trong issuer** |
| `registrationId` | Spring ClientRegistration | `north` | Internal config key, không mặc định bằng `iss` |
| `client_id` | OP/client registry | `portal-north` | OAuth client ID, không phải account ID |
| `account_id` | DB ứng dụng | `acct-n` | Stable local account identifier |
| `tenant_id` | Business data model | `north` | Phạm vi quyền và dữ liệu |
| `permission` | Approved business policy | `NOTE_READ` | Quyền cụ thể, không từ email |
| `note_id` | Tenant data | `1` | Chỉ có nghĩa khi kết hợp tenant |
| `JSESSIONID`/`SESSION` | RP session | Opaque cookie | Local session, không phải IdP SSO session |

OIDC Core `5.7` xác định **cặp `iss + sub`** là định danh RP có thể tin về tính duy nhất/ổn định; **không** dùng `email`, `preferred_username` hoặc tên làm primary key. `sub` có thể trùng giữa các issuers. `email_verified=true` cũng không tự cho phép merge account hai IdPs. Với **pairwise subject**, cùng user tại một OP có thể có `sub` khác khi client/sector identifier đổi; account migration cần proof/approval, không tự link bằng email.

### 1.2. Sơ đồ luồng

```text
            Browser (two separate profiles)
                       |
             Spring Security RP
           oauth2Login north / south
                       |
            +----------+----------+
            |                     |
            v                     v
       OP North               OP South
   iss=.../north           iss=.../south
   client portal-north     client portal-south
            |                     |
            +----------+----------+
                       |
       Verified OidcUser ID Token (iss, sub)
                       |
            federated_identity
       PK (issuer, subject) -> account_id
                       |
          app_account.active AND
          tenant_membership.active AND
          permission = NOTE_READ
                       |
         @PreAuthorize tenant policy
                       |
         SELECT ... FROM tenant_note
         WHERE tenant_id=? AND note_id=?
                       |
                only authorized data
```

**Bốn security invariants:** (1) verified IdP authentication trước khi đọc claims; (2) unique `(iss,sub)`→local account; (3) active membership/permission cho **tenant cụ thể**; (4) **tenant-bound SQL** trên mọi data path. Không cái nào có thể thay thế ba cái còn lại.

## 2. Threat model: điều gì cần chặn?

1. **Account collision:** Attacker dùng IdP South, nhưng email hoặc `sub` trùng với North; app dùng email/sub đơn độc và cấp quyền North.
2. **Tenant ID tampering/IDOR:** North user sửa `/tenants/north/notes/1` thành `/tenants/south/notes/1`, hoặc đoán note IDs.
3. **Unsigned/untrusted token:** Backend đọc Base64 JWT `iss`/`groups` trước khi verify signature và tự cấp quyền.
4. **Dynamic JWK SSRF:** Code tạo `JwtDecoder` từ `iss` URL không có allowlist, attacker trỏ đến OP do mình vận hành.
5. **Group mapping confusion:** North và South đều phát `groups=["admin"]`, app map mọi `admin` thành global `ROLE_ADMIN`.
6. **Stale access:** User đã rời tổ chức, IdP account disabled nhưng RP session/JWT, local grant hoặc cache quyền cũ còn hoạt động.
7. **Cache bleed:** cache dùng key `note:1`, có thể trả dữ liệu North cho South.
8. **Unscoped SQL:** service check quyền đúng nhưng repository chạy `SELECT body WHERE note_id=?`, khiến dữ liệu tenant khác lọt vào kết quả.
9. **Browser/session mix-up:** Hai tabs cùng browser profile login hai IdPs, session state/cookies bị ghi đè; nếu app bỏ state/nonce check để “sửa” thì tạo login CSRF.
10. **Issuer migration/auto-link:** OP đổi issuer/client sector, `sub` mới xuất hiện; app tự gắn account cũ bằng email.
11. **SAML mixed federation:** Assertion từ IdP A được accept trong registration B hoặc NameID transient được dùng làm stable key.
12. **API access token confusion:** App dùng OIDC ID Token thay OAuth access token, hoặc Resource Server tin JWT issuer/audience sai.

**Quy tắc:** HTTP request header `X-Tenant`, `X-User`, `?sub=...` và raw JWT claims đều **không là authentication evidence**. Tenant path là input cần authorization, không phải grant. Không chọn IdP/public key theo hostname attacker nhập.

## 3. Setup hai issuers trong môi trường lab

### 3.1. Khởi động một Keycloak, hai realms

Keycloak có thể dùng **hai realms** để tạo **hai OIDC issuer namespaces logic** trên cùng một server. Đây không phải hai deployment vật lý độc lập; để test outage/HA độc lập cần hai Keycloak instances riêng.

```bash
docker run --rm --name keycloak-two-idp \
  -p 127.0.0.1:8180:8080 \
  -e KC_BOOTSTRAP_ADMIN_USERNAME=admin \
  -e KC_BOOTSTRAP_ADMIN_PASSWORD=change-me-local-only \
  quay.io/keycloak/keycloak:26.8.2 start-dev
```

**Chỉ chạy HTTP/dev credentials trên localhost**, không expose production. Image tag minh họa theo tài liệu Keycloak tại thời điểm xây lab; có thể dùng một version được tổ chức phê duyệt và kiểm release notes. Nếu Windows PowerShell, viết command một dòng hoặc dùng cú pháp continuation đúng shell.

Mở `http://localhost:8180/admin/`, tạo hai realms `north` và `south`, không dùng realm `master` cho ứng dụng.

Tại **north**:

- Tạo OIDC confidential client `portal-north` với Standard Flow/Authorization Code; bật client authentication.
- Valid Redirect URI exact: `http://localhost:8080/login/oauth2/code/north`.
- Tạo test user, thiết lập password và enabled. Lưu client secret vào biến môi trường `NORTH_CLIENT_SECRET`.

Tại **south**:

- Tạo client `portal-south`, Valid Redirect URI exact `http://localhost:8080/login/oauth2/code/south`.
- Tạo test user riêng; có thể dùng cùng email với North để thử collision. Lưu secret vào `SOUTH_CLIENT_SECRET`.

Kiểm hai discovery URLs:

```text
http://localhost:8180/realms/north/.well-known/openid-configuration
http://localhost:8180/realms/south/.well-known/openid-configuration
```

Mỗi JSON `issuer` phải bằng đúng URI đã cấu hình, kể cả scheme, host, port và path. Đừng đoán issuer từ email domain hoặc bỏ dấu slash tùy tiện. Chỉ dùng `http://localhost` trong lab; production dùng HTTPS, trusted OP discovery, TLS/PKIX, client secrets trong secret manager.

### 3.2. Giữ hai browser profiles

Dùng **Profile N** login North và **Profile S** login South. Một Spring web session thông thường giữ một current `Authentication`; login provider thứ hai trong cùng browser profile có thể thay principal/session, nên hai tabs không phải phép kiểm độc lập hai users. Sau khi kiểm happy path, mới thêm test concurrent tabs/state.

## 4. Project Java 17/Spring Boot

Cấu trúc file:

```text
federation-two-idp-lab/
  pom.xml
  src/main/resources/
    application.yml
    schema.sql
    data.sql
  src/main/java/com/example/federationlab/
    FederationLabApplication.java
    WebSecurityConfiguration.java
    TenantGuard.java
    TenantNoteService.java
    TenantNoteController.java
  src/test/java/com/example/federationlab/
    TenantIsolationMvcTest.java
```

**Maven `pom.xml`** (Java 17, Spring Boot 3.5.x; version pin là ví dụ, không phải khuyến nghị “latest”):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.7</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>federation-two-idp-lab</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <properties><java.version>17</java.version></properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-oauth2-client</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
      <groupId>com.h2database</groupId>
      <artifactId>h2</artifactId>
      <scope>runtime</scope>
    </dependency>
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
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
```

### 4.1. `application.yml`

```yaml
server:
  port: 8080
  # Only local direct HTTP lab. Use TLS/Secure cookies in prod.
  forward-headers-strategy: none
  servlet:
    session:
      cookie:
        secure: false
        http-only: true
        same-site: lax

spring:
  application:
    name: federation-two-idp-lab
  datasource:
    url: jdbc:h2:mem:federation;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  sql:
    init:
      mode: always
  security:
    oauth2:
      client:
        registration:
          north:
            provider: north-op
            client-id: portal-north
            client-secret: "${NORTH_CLIENT_SECRET}"
            authorization-grant-type: authorization_code
            scope: openid,profile,email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
          south:
            provider: south-op
            client-id: portal-south
            client-secret: "${SOUTH_CLIENT_SECRET}"
            authorization-grant-type: authorization_code
            scope: openid,profile,email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          north-op:
            issuer-uri: http://localhost:8180/realms/north
          south-op:
            issuer-uri: http://localhost:8180/realms/south
```

- `spring.security.oauth2.client.registration.north`/`south` là keys nội bộ. `provider.<id>.issuer-uri` mới là exact issuer của OP.
- Spring Security dựa vào ClientRegistration, OAuth2 Authorization Code flow, state/nonce/PKCE theo cấu hình, token exchange, OIDC ID Token/JWKS/issuer/audience validation. Không tự base64-decode JWT rồi tin claims.
- `client-secret` dùng environment placeholders; không hardcode secret hay để vào Git/Google Sheet. Các `scope` `profile/email` chỉ có ý nghĩa nếu app cần; có thể giảm theo principle of least data.
- `secure:false` và HTTP chỉ dùng localhost. Production HTTPS, `Secure=true`, trusted reverse proxy forwarding và shared session store nếu multi-pod.
- Boot có thể thực hiện OIDC discovery ngay khi tạo ClientRegistration; **start Keycloak trước app/tests** hoặc cấu hình test-only ClientRegistrationRepository stub phù hợp.
- H2 memory data mất sau mỗi restart; production dùng PostgreSQL, migration tool và approved provisioning.

### 4.2. `schema.sql` — stable identity, membership và tenant data

```sql
CREATE TABLE app_account (
    account_id VARCHAR(64) PRIMARY KEY,
    active BOOLEAN NOT NULL
);

CREATE TABLE federated_identity (
    issuer VARCHAR(255) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    account_id VARCHAR(64) NOT NULL,
    active BOOLEAN NOT NULL,
    PRIMARY KEY (issuer, subject),
    FOREIGN KEY (account_id) REFERENCES app_account(account_id)
);

CREATE INDEX idx_identity_account
    ON federated_identity(account_id);

CREATE TABLE tenant_membership (
    account_id VARCHAR(64) NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    permission VARCHAR(64) NOT NULL,
    active BOOLEAN NOT NULL,
    PRIMARY KEY (account_id, tenant_id, permission),
    FOREIGN KEY (account_id) REFERENCES app_account(account_id)
);

CREATE TABLE tenant_note (
    tenant_id VARCHAR(64) NOT NULL,
    note_id BIGINT NOT NULL,
    body VARCHAR(4000) NOT NULL,
    PRIMARY KEY (tenant_id, note_id)
);
```

**Vì sao hai primary keys kết hợp?**

- `PRIMARY KEY (issuer, subject)`: một `sub` thuộc hai issuers khác nhau không bị merge, trong khi cùng `(iss,sub)` không thể trỏ đến hai local accounts khi import đồng thời.
- `PRIMARY KEY (tenant_id, note_id)`: North/South đều có `note_id=1` mà không va chạm; mọi query resource cần tenant.
- `account_id` tách khỏi email, `sub` và display name, cho phép chuyển contact email/subject migration theo quy trình kiểm soát.
- `tenant_membership` thể hiện local approved permission. Identity login thành công **không** tự cấp membership. Trong production thêm owner, expiry, grant source, audit, SoD, indexes/constraints và tenant lifecycle.

### 4.3. `data.sql` — cố tình có collision

```sql
INSERT INTO app_account(account_id, active)
VALUES ('acct-n', TRUE), ('acct-s', TRUE);

-- Test fixtures; do not pretend Keycloak emits same-sub.
INSERT INTO federated_identity
  (issuer, subject, account_id, active)
VALUES
  ('http://localhost:8180/realms/north', 'same-sub', 'acct-n', TRUE),
  ('http://localhost:8180/realms/south', 'same-sub', 'acct-s', TRUE);

INSERT INTO tenant_membership
  (account_id, tenant_id, permission, active)
VALUES
  ('acct-n', 'north', 'NOTE_READ', TRUE),
  ('acct-s', 'south', 'NOTE_READ', TRUE);

INSERT INTO tenant_note(tenant_id, note_id, body)
VALUES
  ('north', 1, 'NORTH_ONLY'),
  ('south', 1, 'SOUTH_ONLY');
```

**Chú ý:** `same-sub` chỉ là **synthetic subject fixture** để MockMvc/Java test account collision. Real Keycloak users thường có `sub` dạng UUID khác. Khi login browser thật, app sẽ trả 403 trên note cho tới khi identity được administrator/owner xác minh và bind vào một local account có membership. Đây là **deny by default**, không phải bug cần bypass.

## 5. Java Spring Security authentication và tenant policy

### 5.1. `FederationLabApplication.java`

```java
package com.example.federationlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FederationLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(FederationLabApplication.class, args);
    }
}
```

### 5.2. `WebSecurityConfiguration.java`

```java
package com.example.federationlab;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class WebSecurityConfiguration {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
```

`authenticated()` chỉ là xác thực, **không tự kiểm tenant**. `@EnableMethodSecurity` cho phép `@PreAuthorize` bảo vệ business method trước query. Hai client registrations làm hai start URLs có thể dùng `/oauth2/authorization/north` và `/oauth2/authorization/south`. Callback mặc định tương ứng `/login/oauth2/code/north` và `/login/oauth2/code/south`.

### 5.3. `TenantGuard.java` — kiểm verified issuer, subject và grant

```java
package com.example.federationlab;

import java.util.Map;
import java.util.Objects;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.stereotype.Component;

@Component("tenantGuard")
public class TenantGuard {

    private static final Map<String, String> TENANT_ISSUERS =
        Map.of(
            "north", "http://localhost:8180/realms/north",
            "south", "http://localhost:8180/realms/south"
        );

    private final JdbcTemplate jdbc;

    public TenantGuard(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public boolean canRead(Authentication authentication,
                           String tenantId) {
        if (authentication == null
                || !authentication.isAuthenticated()
                || !(authentication.getPrincipal() instanceof OidcUser user)) {
            return false;
        }

        String allowedIssuer = TENANT_ISSUERS.get(tenantId);
        if (allowedIssuer == null) {
            return false; // unknown tenant
        }

        String issuer = user.getIdToken().getClaimAsString("iss");
        String subject = user.getIdToken().getSubject();

        if (!Objects.equals(allowedIssuer, issuer)
                || subject == null || subject.isBlank()) {
            return false;
        }

        Integer count = jdbc.queryForObject(
            """
            SELECT COUNT(*)
              FROM federated_identity fi
              JOIN app_account a
                ON a.account_id = fi.account_id
              JOIN tenant_membership tm
                ON tm.account_id = a.account_id
             WHERE fi.issuer = ?
               AND fi.subject = ?
               AND fi.active = TRUE
               AND a.active = TRUE
               AND tm.tenant_id = ?
               AND tm.permission = 'NOTE_READ'
               AND tm.active = TRUE
            """,
            Integer.class, issuer, subject, tenantId
        );

        return count != null && count > 0;
    }
}
```

**Đọc code theo trust boundaries:**

1. `OidcUser` được Spring OAuth2 Login tạo sau khi verified ID Token và OIDC flow; không dùng raw HTTP headers/query làm principal.
2. Cặp `issuer+subject` resolve đúng identity. `getClaimAsString("iss")`/`getSubject()` đọc từ `OidcIdToken`, không từ URL `/tenants/south`.
3. `TENANT_ISSUERS` là allowlist **của lab**, không là luật cho mọi kiến trúc. Nếu một tenant tin nhiều IdPs, dùng mapping approved issuer set và independent membership.
4. `fi.active`, `a.active` và `tm.active` phải cùng TRUE. Thay đổi membership trong DB có hiệu lực trên request mới, kể cả local session chưa logout (trừ khi production thêm authorization cache chưa invalidate).
5. `permission='NOTE_READ'` không cho quyền `NOTE_WRITE` hay `ADMIN`. Đừng map raw `groups=["admin"]` từ mọi IdPs thành global admin.
6. `JdbcTemplate` có binding parameters; không nối `subject`/`tenantId` vào SQL.
7. Với API routes, một user có thể đã logged in nhưng nhận `403`; đó là **business authorization deny**, khác OIDC authentication failure.
8. Các test `oidcLogin()` tạo principal giả trong MockMvc; đó là policy testing, không phải kiểm cryptographic token validation.
9. Dịch vụ dùng `@PreAuthorize` phải được gọi qua Spring-managed bean/AOP proxy; tránh self-invocation làm mất enforcement.
10. App production thường cần check permission ở action time từ authoritative DB/cache version, không chỉ cached `GrantedAuthorities` lúc login.

### 5.4. `TenantNoteService.java` — truy vấn có tenant

```java
package com.example.federationlab;

import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class TenantNoteService {

    private final JdbcTemplate jdbc;

    public TenantNoteService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @PreAuthorize("@tenantGuard.canRead(authentication, #p0)")
    public String readNote(String tenantId, long noteId) {

        List<String> rows = jdbc.query(
            """
            SELECT body
              FROM tenant_note
             WHERE tenant_id = ?
               AND note_id = ?
            """,
            (rs, rowNum) -> rs.getString("body"),
            tenantId, noteId
        );

        if (rows.isEmpty()) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Note not found");
        }
        return rows.get(0);
    }
}
```

**Defense in depth:** `@PreAuthorize` kiểm quyền **trước** method body; SQL `WHERE tenant_id=? AND note_id=?` bảo đảm query cũng bị giới hạn tenant. **Sai:** `SELECT body FROM tenant_note WHERE note_id=?` vì IDs có thể trùng giữa tenants và một code path khác có thể bypass controller guard.

### 5.5. `TenantNoteController.java`

```java
package com.example.federationlab;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class TenantNoteController {

    private final TenantNoteService service;

    public TenantNoteController(TenantNoteService service) {
        this.service = service;
    }

    @GetMapping("/")
    public Map<String, String> home() {
        return Map.of(
            "northLogin", "/oauth2/authorization/north",
            "southLogin", "/oauth2/authorization/south"
        );
    }

    // Lab-only authenticated endpoint for manual onboarding.
    @GetMapping("/me")
    public Map<String, String> me(
            @AuthenticationPrincipal OidcUser user) {
        return Map.of(
            "issuer", user.getIdToken().getClaimAsString("iss"),
            "subject", user.getIdToken().getSubject()
        );
    }

    @GetMapping("/api/tenants/{tenantId}/notes/{noteId}")
    public Map<String, Object> read(
            @PathVariable String tenantId,
            @PathVariable long noteId) {
        return Map.of(
            "tenant", tenantId,
            "id", noteId,
            "body", service.readNote(tenantId, noteId)
        );
    }
}
```

`/me` giúp user đã login xem **định danh của chính mình** để admin có thể duyệt onboarding trong lab. `iss/sub` là identifiers có yêu cầu bảo vệ privacy; production bỏ hoặc giới hạn endpoint, không log toàn bộ user identity. `service.readNote` được gọi qua Spring bean nên method-security AOP hoạt động.

## 6. Chạy lab và onboarding identity thực

Trước khi chạy Maven, mở Keycloak, xác minh `/.well-known/openid-configuration` cho hai realms và cấp secrets riêng qua environment. Dùng Java 17 + Maven:

```bash
mvn -version
mvn test
mvn spring-boot:run
```

Trình tự trong browser:

1. Profile N: `http://localhost:8080/oauth2/authorization/north` → Keycloak North login → Spring callback.
2. Profile S: `http://localhost:8080/oauth2/authorization/south` → Keycloak South login → Spring callback.
3. Mở `http://localhost:8080/me` ở từng profile; xác nhận hai `issuer` khác nhau và lấy `sub` của test users trong phòng lab (không ghi vào shared logs).
4. Do `data.sql` chỉ có `same-sub`, user thật từ Keycloak ban đầu có thể login OIDC thành công nhưng `/api/tenants/north/notes/1` vẫn trả `403`. Đây là **deny by default**.
5. Chỉ sau business owner approval, admin sửa hai giá trị `subject` seed (giữ nguyên `issuer`/`accountId`) thành subject thực và restart app H2. Ví dụ:

```sql
-- Lab-only: values must come from verified login and approval.
UPDATE federated_identity
   SET subject = 'VERIFIED_NORTH_SUB'
 WHERE issuer = 'http://localhost:8180/realms/north'
   AND account_id = 'acct-n';

UPDATE federated_identity
   SET subject = 'VERIFIED_SOUTH_SUB'
 WHERE issuer = 'http://localhost:8180/realms/south'
   AND account_id = 'acct-s';
```

Với H2 RAM, cách đơn giản là sửa `data.sql` tương ứng rồi restart; nếu chạy `UPDATE` trực tiếp qua DB admin tool trong lab thì phải bảo vệ tool, vì không có H2 console public trong cấu hình trên. **Không tạo self-service endpoint `POST /grant?tenant=south`**: browser không được tự cấp membership. Production dùng provisioning/SCIM/invite flow đã được duyệt, transactions/uniqueness/audit và authoritative HR/partner identity source.

Kết quả dự kiến sau provisioning:

| Browser | Request | Kết quả |
| --- | --- | --- |
| Profile N | `GET /api/tenants/north/notes/1` | 200, `NORTH_ONLY` |
| Profile N | `GET /api/tenants/south/notes/1` | **403**, không có `SOUTH_ONLY` |
| Profile S | `GET /api/tenants/south/notes/1` | 200, `SOUTH_ONLY` |
| Profile S | `GET /api/tenants/north/notes/1` | **403**, không có `NORTH_ONLY` |
| Chưa login | GET protected resource | Redirect login (web flow) hoặc error tùy entry point |
| Đã login nhưng account chưa map | GET tenant note | **403** (đúng) |

**Cần phân biệt:** “OIDC login success” chỉ bảo đảm Spring nhận identity, không bảo đảm user có business grant. Một user chưa được onboard mà nhận 403 **không phải** lý do tắt tenant guard.

## 7. MockMvc kiểm quyền chéo tenant

`oidcLogin()` trong `spring-security-test` chèn OIDC principal giả vào MockMvc request, kiểm phần **authorization sau authentication**. Nó không trao đổi authorization code, không verify JWT signature thật, không kiểm PKCE/nonce/HTTPS. Muốn kiểm handshake, dùng Keycloak và signed-token E2E.

File `src/test/java/com/example/federationlab/TenantIsolationMvcTest.java`:

```java
package com.example.federationlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.RequestPostProcessor;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class TenantIsolationMvcTest {

    @Autowired
    MockMvc mvc;

    static RequestPostProcessor id(String issuer, String subject) {
        return oidcLogin().idToken(token -> token
            .claim("iss", issuer)
            .claim("sub", subject));
    }

    @Test
    void northAllowedButSouthForbidden() throws Exception {
        mvc.perform(get("/api/tenants/north/notes/1")
                .with(id("http://localhost:8180/realms/north",
                         "same-sub")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.body").value("NORTH_ONLY"));

        mvc.perform(get("/api/tenants/south/notes/1")
                .with(id("http://localhost:8180/realms/north",
                         "same-sub")))
            .andExpect(status().isForbidden());
    }

    @Test
    void southAllowedButNorthForbidden() throws Exception {
        mvc.perform(get("/api/tenants/south/notes/1")
                .with(id("http://localhost:8180/realms/south",
                         "same-sub")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.body").value("SOUTH_ONLY"));

        mvc.perform(get("/api/tenants/north/notes/1")
                .with(id("http://localhost:8180/realms/south",
                         "same-sub")))
            .andExpect(status().isForbidden());
    }

    @Test
    void unknownIssuerSubjectTenantAreDenied() throws Exception {
        mvc.perform(get("/api/tenants/north/notes/1")
                .with(id("http://localhost:8180/realms/attacker",
                         "same-sub")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/tenants/north/notes/1")
                .with(id("http://localhost:8180/realms/north",
                         "not-linked")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/tenants/east/notes/1")
                .with(id("http://localhost:8180/realms/north",
                         "same-sub")))
            .andExpect(status().isForbidden());
    }
}
```

**Test chuẩn xác chứng minh:** Cùng `sub=same-sub` không gộp account; North không đọc South; South không đọc North; unknown issuer/sub/tenant bị deny; API data body đúng. Nếu Spring OIDC discovery lúc startup yêu cầu OP thật, **chạy Keycloak trước `mvn test`** hoặc cấu hình một test-only ClientRegistrationRepository stub để unit tests không phụ thuộc OP; tuyệt đối không biến MockMvc thành bằng chứng cryptographic validation.

**Caveat:** Để kiểm revocation trong app, thêm test chỉnh `app_account.active=false`/`tenant_membership.active=false` trong một transaction test rồi request lại qua MockMvc, sau đó rollback fixture. Không chỉ assert `role` có trong OIDC claim; quyền effective phải đến từ DB.

## 8. Java 17 độc lập — mô phỏng quyết định tenant

Chạy không cần Spring/Keycloak/DB; mô hình giả định **issuer/subject đã được provider verify trước khi gọi**. Tuyệt đối không lấy chúng trực tiếp từ HTTP query trong production.

File `TwoIssuerTenantIsolationDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

public final class TwoIssuerTenantIsolationDemo {

    static final String NORTH = "https://idp.example.org/north";
    static final String SOUTH = "https://idp.example.org/south";

    record Key(String issuer, String subject) { }
    record Account(String id, String email, boolean active) { }

    enum Verdict {
        ALLOW, DENY_TENANT, DENY_ISSUER, DENY_IDENTITY,
        DENY_INACTIVE, DENY_MEMBERSHIP, DENY_PERMISSION
    }

    final Map<Key, Account> identities = new HashMap<>();
    final Map<String, Set<String>> grants = new HashMap<>();
    final Map<String, String> tenantIssuer =
        Map.of("north", NORTH, "south", SOUTH);

    void bind(String issuer, String sub, Account account) {
        identities.put(new Key(issuer, sub), account);
    }

    void grant(String account, String tenant, String permission) {
        grants.put(account, Set.of(tenant, permission));
    }

    Verdict read(String issuer, String sub,
                 String tenant, String permission) {

        String expected = tenantIssuer.get(tenant);
        if (expected == null) return Verdict.DENY_TENANT;
        if (!expected.equals(issuer)) return Verdict.DENY_ISSUER;

        Account account = identities.get(new Key(issuer, sub));
        if (account == null) return Verdict.DENY_IDENTITY;
        if (!account.active()) return Verdict.DENY_INACTIVE;

        Set<String> grant = grants.get(account.id());
        if (grant == null || !grant.contains(tenant)) {
            return Verdict.DENY_MEMBERSHIP;
        }
        if (!grant.contains(permission)) {
            return Verdict.DENY_PERMISSION;
        }
        return Verdict.ALLOW;
    }

    public static void main(String[] args) {
        var app = new TwoIssuerTenantIsolationDemo();

        app.bind(NORTH, "same-sub",
            new Account("acct-n", "same@example.org", true));
        app.bind(SOUTH, "same-sub",
            new Account("acct-s", "same@example.org", true));

        app.grant("acct-n", "north", "NOTE_READ");
        app.grant("acct-s", "south", "NOTE_READ");

        System.out.println("northOwn=" +
            app.read(NORTH, "same-sub", "north", "NOTE_READ"));

        System.out.println("southOwn=" +
            app.read(SOUTH, "same-sub", "south", "NOTE_READ"));

        System.out.println("northToSouth=" +
            app.read(NORTH, "same-sub", "south", "NOTE_READ"));

        System.out.println("southToNorth=" +
            app.read(SOUTH, "same-sub", "north", "NOTE_READ"));

        System.out.println("unknownTenant=" +
            app.read(NORTH, "same-sub", "east", "NOTE_READ"));

        System.out.println("unlinked=" +
            app.read(NORTH, "other-sub", "north", "NOTE_READ"));

        System.out.println("wrongPermission=" +
            app.read(NORTH, "same-sub", "north", "NOTE_WRITE"));

        Account n = app.identities.get(new Key(NORTH, "same-sub"));
        Account s = app.identities.get(new Key(SOUTH, "same-sub"));
        System.out.println("differentAccounts=" +
            !n.id().equals(s.id()));
        System.out.println("sameEmail=" +
            n.email().equals(s.email()));

        app.bind(NORTH, "same-sub",
            new Account("acct-n", "same@example.org", false));

        System.out.println("disabledNorth=" +
            app.read(NORTH, "same-sub", "north", "NOTE_READ"));

        System.out.println("southUnaffected=" +
            app.read(SOUTH, "same-sub", "south", "NOTE_READ"));
    }
}
```

Biên dịch/chạy bằng JDK 17+:

```bash
javac --release 17 TwoIssuerTenantIsolationDemo.java
java TwoIssuerTenantIsolationDemo
```

**Stdout chính xác:**

```text
northOwn=ALLOW
southOwn=ALLOW
northToSouth=DENY_ISSUER
southToNorth=DENY_ISSUER
unknownTenant=DENY_TENANT
unlinked=DENY_IDENTITY
wrongPermission=DENY_PERMISSION
differentAccounts=true
sameEmail=true
disabledNorth=DENY_INACTIVE
southUnaffected=ALLOW
```

Chương trình chỉ so composite key và grants giả lập; không verify JWT, signature, SAML, browser session, TLS, role database hay concurrency. Nó không dùng `email` làm identity key dù hai accounts có email bằng nhau; `differentAccounts=true` là minh chứng. Không được đưa input `issuer`/`sub` từ client không xác thực vào hàm `read` rồi coi `ALLOW` là proof of login.

## 9. Luồng kiểm thử trình duyệt từ đầu đến cuối

| Bước | Profile N | Profile S | Kết quả cần ghi |
| --- | --- | --- | --- |
| 1 | `GET /oauth2/authorization/north` | — | Redirect tới đúng issuer North |
| 2 | — | `GET /oauth2/authorization/south` | Redirect tới đúng issuer South |
| 3 | Login/MFA tại North | Login/MFA tại South | OP xác thực độc lập |
| 4 | `/login/oauth2/code/north` | `/login/oauth2/code/south` | Spring verify state/nonce/token |
| 5 | `GET /me` | `GET /me` | Hai issuer khác; không auto-link email |
| 6 | Sau approved onboarding, GET North note | GET South note | 200, đúng body |
| 7 | GET South note | GET North note | **403** ở cả hai hướng |
| 8 | Thay email tại OP, giữ sub | Tương tự | Không đổi internal account |
| 9 | Revoke membership, giữ session | Đăng nhập không đổi | North deny, South không bị ảnh hưởng |

Một browser session thường chỉ chứa một current Authentication; **để test hai users đồng thời dùng profiles/containers tách biệt**. Nếu cố tình login North rồi South trong cùng profile, cần xem session replacement và `state` correlation đúng, không suy “tenant isolation fail” chỉ từ account hiển thị bị thay.

## 10. Data-layer và IDOR: điều kiện truy vấn không được bỏ

**Sai:**

```java
jdbc.queryForObject(
    "SELECT body FROM tenant_note WHERE note_id = ?",
    String.class, noteId);
```

**Đúng:**

```java
jdbc.query(
    "SELECT body FROM tenant_note WHERE tenant_id = ? AND note_id = ?",
    (rs, n) -> rs.getString("body"),
    verifiedAuthorizedTenantId, noteId);
```

`verifiedAuthorizedTenantId` không phải raw path/query value; trong `TenantNoteService`, method argument đã được `TenantGuard` kiểm bằng Spring Method Security. Với list/search/exports/batch/async/WebSocket/caches/files:

- Mọi query SQL, full-text search, aggregate, count, pagination và export đều có tenant scope.
- Cache keys phải mang tenant identity, chẳng hạn `tenant:north:note:1`; chỉ `note:1` gây nguy cơ cross-tenant cache bleed.
- Background jobs cần tenant context đã xác minh, không nhận tenant từ message queue không tin.
- Resource ownership/permission phải kiểm ở **service layer**; UI ẩn nút không phải authorization.
- CDN/object storage links ngắn hạn chỉ được cấp sau kiểm tenant/permission.
- Database backup/log/APM và error responses không được lộ body, record count hoặc group membership tenant khác.

**PostgreSQL RLS (tùy chọn defense-in-depth):**

```sql
ALTER TABLE tenant_note ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_note FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_scope
    ON tenant_note
    FOR SELECT
    USING (tenant_id = current_setting('app.current_tenant', true));
```

Đây là **SQL fragment** cho production design, không phải H2 script. Nếu dùng pooled connections, `app.current_tenant` phải được đặt từ **authorized tenant** với `SET LOCAL` hoặc transaction-local `set_config(...,true)`, không để session variable của request trước rò sang request sau. DB role superuser/`BYPASSRLS` vẫn có thể bypass; không dùng role đó cho ứng dụng. RLS không thay OIDC issuer validation, local grants hay service authorization. Test RLS với database role/connection pool thật trước triển khai.

## 11. Mở rộng sang hai IdPs khác giao thức: OIDC và SAML2

Bài lab chọn hai OIDC issuers nhưng logic identity/tenant áp dụng được khi **North dùng OIDC, South dùng SAML2**.

Sau OIDC flow đã verify:

```text
protocol=OIDC
providerId=validated ID Token iss
subjectId=validated ID Token sub
identityKey=(OIDC, iss, sub)
```

Sau SAML `saml2Login()` đã kiểm chữ ký và conditions:

```text
protocol=SAML2
providerId=trusted IdP EntityID / Issuer
subjectId=approved stable NameID or asserted stable attribute
qualifierScope=NameID Format + NameQualifier/SPNameQualifier as needed
identityKey=(SAML2, issuer, qualifierScope, stableSubject)
```

**SAML caveats:**

- `transient NameID` không ổn định qua các login; `emailAddress NameID` có thể đổi/tái dùng. Cần contract persistent NameID hoặc stable attribute được IdP bảo đảm và RP verified.
- RelyingPartyRegistration.`registrationId` không phải IdP EntityID, cũng không tự bằng tenant.
- Phải kiểm SAML XML Signature bằng trusted IdP verification credentials; kiểm `AudienceRestriction`, `Destination`, `Recipient`, `InResponseTo`, `NotBefore/NotOnOrAfter` và replay trước khi map user.
- Hai SAML IdPs phát cùng `groups=Admins` không cho phép mapping tự động thành global admin.
- Không tự lấy signing certificate từ untrusted SAMLResponse `KeyInfo` rồi tin nó.
- SP signing/decryption credentials khác IdP signing cert, metadata signer/TLS cert có trust riêng.
- Nếu RP có nhiều SAML registrations và unsolicited IdP-initiated SSO không có `InResponseTo`, phải thiết kế route/issuer/audience resolution không mơ hồ hoặc từ chối flow đó.

Khi đưa nhiều protocols vào cùng identity table, thêm `protocol`/provider namespace vào UNIQUE key nếu cần. **Account linking giữa OIDC/SAML chỉ qua verified re-authentication/approval**; không dựa email giống nhau. Linking identities không tự union mọi tenant permissions.

## 12. API Resource Server đa issuer là trường hợp khác

Lab web dùng `oauth2Login()` và Spring HttpSession. Nếu API nhận Bearer access tokens từ hai Authorization Servers thì cấu hình **`oauth2ResourceServer`** và issuer-specific JWT validation, không lấy OIDC ID Token của RP thay access token.

Spring Security Servlet hỗ trợ resolver từ danh sách issuers tin cậy (fragment cho SecurityFilterChain API riêng, thêm dependency Resource Server):

```java
var resolver =
    org.springframework.security.oauth2.server.resource.authentication
        .JwtIssuerAuthenticationManagerResolver
        .fromTrustedIssuers(
            "https://op-north.example.org/issuer",
            "https://op-south.example.org/issuer"
        );

http.authorizeHttpRequests(auth ->
        auth.anyRequest().authenticated())
    .oauth2ResourceServer(resource ->
        resource.authenticationManagerResolver(resolver));
```

- Không tạo decoder từ `iss` tùy ý trong unverified token, để tránh SSRF/attacker-selected keys.
- Ngoài issuer/signature/expiry, kiểm **audience API**, permitted algorithms/scopes và business tenant membership. Trusted issuer **không tự cho quyền mọi tenant**.
- Tách `SecurityFilterChain` cho browser OAuth2 Login và API bearer token nếu sử dụng song song, tránh login callback bị API chain bắt nhầm.
- Spring `jwt()` MockMvc postprocessor kiểm policy với mock principal; không xác minh chữ ký thật. Dùng signed JWT fixtures/real authorization servers cho crypto/issuer/audience tests.

## 13. Session và vòng đời account

- **Joiner:** IdP xác thực identity, business owner/HR xác nhận user và grant; thêm binding `(issuer,sub)`→accountId có approval/audit, chỉ cấp minimum membership.
- **Mover:** thu hồi old tenant grants, cấp tenant mới sau review; không giữ quyền cũ qua cached group/role.
- **Leaver:** disable authoritative account/membership, revoke Spring sessions/refresh tokens theo policy, bảo đảm API action-time deny. JWT đã phát có `exp` riêng; disable IdP không tự thu hồi mọi JWT.
- **Local logout:** xóa RP session; OP North/South SSO cookies có lifecycle độc lập. OIDC RP-initiated/back-channel logout chỉ hoạt động khi provider/protocol được hỗ trợ và triển khai đúng.
- **Issuer/client migration:** Pairwise `sub`/issuer thay đổi là migration danh tính, không phải “email đổi”; phải có verified linkage ceremony, audit và uniqueness locks.
- **Session multiple pods:** OAuth2 authorization request/state phải có session continuity (Spring Session/shared state/sticky policy phù hợp). Callback tới pod khác không được bỏ `state` để tránh invalid state.
- **Role cache:** Nếu `GrantedAuthority` snapshot lúc login, business grants stale có thể sống qua session. Bài lab query active membership mỗi request; production cache phải có invalidation/version và SLA.
- **Cookie:** Production `Secure; HttpOnly`, appropriate `SameSite`, restricted Domain/Path. OIDC top-level GET callback thường làm việc với Lax; cross-site POST mode cần đánh giá riêng.
- **Forwarded headers:** Reverse proxy phải strip/overwrite `Forwarded`/`X-Forwarded-*` để Spring tạo exact public redirect URI, không tin Host do browser cung cấp.

## 14. Ma trận kiểm thử bảo mật

| Test | Fixture/action | Kết quả |
| --- | --- | --- |
| North own resource | North issuer/sub + NOTE_READ North | **200 NORTH_ONLY** |
| South own resource | South issuer/sub + NOTE_READ South | **200 SOUTH_ONLY** |
| North to South path | Login North, swap tenant path | **403** |
| South to North path | Login South, swap path | **403** |
| Same `sub` different issuer | `same-sub` in North & South | Two separate accounts |
| Same email | Duplicate email across OPs | No auto account linking |
| Unknown issuer | Third realm ID Token/mock | Reject at OP validation/tenant guard |
| Unknown subject | Approved issuer, unmapped sub | 403 |
| Unknown tenant | `/tenants/east` | 403/404 policy |
| Disable local account | `active=false`, session still exists | Next request denies |
| Revoke membership | `tm.active=false` | Next request denies |
| Note ID collision | Both tenants have note `1` | No data mix |
| SQL without tenant | `WHERE note_id=?` | Security regression catches |
| Cache key without tenant | `note:1` only | Reject/fix cache design |
| Raw group `admin` | Claim exists, no approved grant | No admin |
| Duplicate email with verified flag | Both OPs `email_verified` | No merge |
| Forged `X-User`/`X-Tenant` | Attacker headers | No effect |
| Altered `state` | OAuth callback tampering | Auth failure |
| Bad PKCE verifier | Authorization/token mismatch | Token endpoint reject |
| Unknown JWK `kid` | Untrusted signing key | Token rejected |
| Wrong `iss` | Signed token from third realm | Reject |
| Wrong `aud` | Token for other client/API | Reject |
| Expired ID Token | `exp` past | Reject |
| OIDC issuer migration | New issuer/sub | Approved migration only |
| Pairwise subject rotated | Sector/client changes | No silent email link |
| Concurrent two tabs | North and South callbacks overlap | Valid state or safe failure |
| OIDC OP outage | North token endpoint down | No fallback to South identity |
| Session cookie missing | Callback session lost | Safe correlation failure |
| SAML wrong issuer | Valid signature, wrong IdP registration | Reject |
| SAML wrong audience | Signed assertion for other SP | Reject |
| SAML transient NameID | Subject changes each login | No accidental account merge |
| API unknown issuer | JWT `iss` attacker URL | Reject, no arbitrary JWKS fetch |
| API wrong audience | Valid signature for different API | Reject |
| Multi-pod stale grants | One pod retains old cache | Fail regression until converged |
| RLS pooled connection leak | Previous tenant context remains | Reject/fix transaction scope |
| Export/search cross-tenant | Unscoped bulk data endpoint | No leaked records |
| Sensitive logs | Raw token/cookie/SAMLResponse in TRACE | QA fail, redact |

**Chú ý test fixtures:** `MockMvc oidcLogin()` giả claims không có cryptographic signature. Signed-token E2E negative tests phải dùng OP/JWK test keys; sửa SAML assertion sau khi ký chỉ làm chữ ký invalid, không chứng minh audience validator. Tách rõ **policy tests** và **protocol/trust tests**.

## 15. Runbook xử lý lỗi thường gặp

### 15.1. North login thành công nhưng note trả 403

1. `/me` xác nhận `iss` chính xác North, `sub` thực từ OP.
2. Kiểm `federated_identity` có exact (issuer,sub) mapping active không; `data.sql` synthetic `same-sub` có thể chưa được thay.
3. Kiểm `app_account.active` và `tenant_membership` grant `NOTE_READ` North.
4. Kiểm `@EnableMethodSecurity`, `TenantGuard`, transaction/read replica stale.
5. Không “sửa” bằng cách bỏ guard hoặc auto-grant tenant từ email.

### 15.2. South user nhìn thấy data North

Đây là **security incident**. Cô lập endpoint theo quy trình, xác định ảnh hưởng, kiểm identity key có mất issuer không, SQL có thiếu tenant predicate không, caches/search/export có dùng tenant scope không, và method security có self-invocation bypass không. Bổ sung negative regression tests, đánh giá privacy/disclosure theo policy.

### 15.3. OIDC callback báo `invalid_state` hoặc redirect loop

Kiểm cookie Domain/Path/SameSite/Secure, session store (đặc biệt hai pods), browser tabs, reverse proxy public HTTPS host/port và authorization request repository. Không bỏ `state`/nonce/PKCE. Token exchange là **back-channel server-to-server**, không hiện trong browser Network panel; cần Spring/OP logs đã sanitize.

### 15.4. Hai users cùng email bị nhập một account

Kiểm code `findByEmail`, unique constraints, JIT provisioning, group role mapper. Chuyển thành `(iss,sub)`, migration được duyệt và audited; không tự nối bằng `email_verified`. Nếu đã lộ dữ liệu, xử lý security/privacy incident.

### 15.5. Đổi issuer hoặc signing key

Kiểm OP discovery `issuer`, JWKS `kid`, client registration, allowlist, key rotation timeline. Không import JWK từ URL attacker gửi. Với client/issuer migration, dùng approved identity mapping và planned rollover; không tự đổi `account_id` theo email.

### 15.6. User đã nghỉ nhưng session còn quyền

Tắt account/membership ở authoritative layer, invalidate session/refresh tokens theo SLA, kiểm database status/authorization cache và API bearer JWT expiry. Test request với session cũ phải deny ở mọi pods; chỉ tắt IdP login mới chưa đủ.

## 16. Tránh các anti-patterns

| Sai | Rủi ro | Đúng |
| --- | --- | --- |
| `users.email PRIMARY KEY` | Email đổi/trùng/reused | Local account ID + federated (iss,sub) |
| `Map<sub,account>` | Collision across OPs | Composite key |
| Tin `X-Tenant` từ browser | Tenant impersonation | Validated principal + approved membership |
| Decode JWT rồi nhận `groups` | Claim forgery | Verify ID Token/access token first |
| JWK URL từ arbitrary JWT `iss` | SSRF/trust bypass | Trusted issuer allowlist |
| Auto-map `admin` all issuers | Cross-tenant privilege escalation | Issuer-specific mapping + local policy |
| `authenticated()` là đủ | IDOR | Service/resource authorization |
| `SELECT WHERE note_id=?` | Data leak | `WHERE tenant_id=? AND note_id=?` |
| Cache `note:1` | Tenant data bleed | Tenant-scoped cache key |
| Auto-link cùng email | Account takeover | Verified linking ceremony |
| Tắt `state` khi session lỗi | Login CSRF | Fix session/cookies |
| Dùng ID Token cho API | Wrong audience/semantics | OAuth access token + Resource Server |
| Tắt CSRF toàn ứng dụng | Browser CSRF | Correct protocol-specific handling |
| Self-invocation bypass `@PreAuthorize` | Authorization skipped | Spring proxy service calls |
| Log raw tokens/HAR | Credential/PII leak | Sanitized audit events |
| Tin mọi SAML `KeyInfo` | Untrusted signer | Approved IdP metadata/cert |
| Reuse one browser profile for two users | Session overwriting | Separate profiles |
| Chờ token expiry cho leaver rủi ro cao | Stale privilege window | Active revoke/action-time checks |

## 17. Quan sát và bằng chứng QA

Sự kiện log (các giá trị chỉ minh họa):

```json
{
  "event": "TENANT_AUTHZ_DECISION",
  "utc": "2030-02-03T10:15:30Z",
  "trustedIssuerId": "north-op",
  "accountRef": "pseudonymous-account",
  "requestedTenant": "south",
  "permission": "NOTE_READ",
  "decision": "DENY",
  "reason": "ISSUER_NOT_ALLOWED_FOR_TENANT",
  "requestId": "server-generated-id"
}
```

Không log raw `sub`/email nếu không cần, access/ID tokens, authorization code, `state`/nonce, cookies, secrets, SAMLResponse, private signing keys hoặc full SQL params. Metrics labels chỉ dùng known registration/tenant values, không attacker-controlled identifiers. Để chốt QA cần cả **positive tests** (đúng tenant 200) lẫn **negative tests** (sai tenant 403/no data), readback config/runtime, IdP signed token E2E và data-scoping test; không chỉ nhìn login page thành công.

## 18. Câu hỏi tự kiểm tra và đáp án

**1.** North/South có `sub=123`, dùng `sub` làm global unique key được không?

**Đáp án:** Không. `sub` chỉ unique trong issuer; phải dùng `(iss,sub)`.

**2.** Hai OP có cùng email, `email_verified=true`, tự merge được không?

**Đáp án:** Không. Linking cần proof/approval riêng, không dùng email.

**3.** OIDC login thành công có tự cấp `NOTE_READ` North không?

**Đáp án:** Không. Business grant ở local membership/authoritative store phải được duyệt.

**4.** North user có thể đổi URL sang South vì controller chỉ yêu cầu `authenticated()`?

**Đáp án:** Có nguy cơ nếu chỉ dùng `authenticated()`; lab dùng `@PreAuthorize` và tenant-scoped SQL để deny.

**5.** Vì sao note PK gồm `tenant_id,note_id`?

**Đáp án:** Cùng note ID có thể tồn tại ở nhiều tenants; key và query phải có tenant.

**6.** MockMvc `oidcLogin()` chứng minh signature/PKCE/JWKS validation chưa?

**Đáp án:** Chưa, vì nó mock principal; cần real OP/signed-token E2E.

**7.** User email đổi nhưng `iss/sub` giữ nguyên, nên đổi local account ID không?

**Đáp án:** Không. Cập nhật display/contact data theo policy, giữ mapping stable.

**8.** Một IdP pairwise `sub` đổi khi đổi client sector; dùng email để “khôi phục” mapping?

**Đáp án:** Không. Dùng verified/approved migration linking.

**9.** JWT access token `iss` từ tenant thứ ba; có thể dùng URL đó tải JWKS để test không?

**Đáp án:** Không. Chỉ trusted issuer allowlist, tránh SSRF và untrusted signing keys.

**10.** Tắt user tại OP có tự invalidate Spring HttpSession và mọi JWTs không?

**Đáp án:** Không. Cần policy revoke sessions/tokens và authoritative access-time checks.

**11.** Một cache chỉ key theo note ID có nguy hiểm không?

**Đáp án:** Có. Dữ liệu North/South `note_id=1` có thể bị trộn. Cache phải gắn tenant và authorization context.

**12.** Khi thêm SAML2, stable subject nào có thể dùng?

**Đáp án:** Chỉ persistent NameID/approved stable attribute từ verified assertion, scoped IdP EntityID và qualifiers; không dùng transient NameID/email tùy tiện.

## 19. Checklist nghiệm thu

- [ ] Hai OP/realms có **issuer khác nhau**, client IDs/secrets/redirect URIs/JWKS được quản trị độc lập.
- [ ] Browser login đúng `/oauth2/authorization/north` hoặc `/south`, callback vào đúng `/login/oauth2/code/{registrationId}`.
- [ ] ID Token signature/issuer/audience/expiry/nonce và authorization transaction `state`/PKCE được verify.
- [ ] Identity table có `PRIMARY KEY (issuer, subject)` và accounts dùng immutable local ID.
- [ ] Không dùng email, display name, raw groups, URL tenant hay HTTP header làm security principal/grant.
- [ ] Unknown identity/tenant/issuer deny by default; JIT provisioning không tự tạo privileged membership.
- [ ] Membership/permission/active status gắn tenant, có owner/approval và offboarding.
- [ ] `@EnableMethodSecurity` hoạt động và service `@PreAuthorize` thực sự được gọi qua proxy.
- [ ] SQL query của note/list/export/search có tenant bound, không chỉ `note_id`.
- [ ] Synthetic tests có cùng sub/email và same note ID across North/South.
- [ ] North own 200, North→South 403; South own 200, South→North 403.
- [ ] Unknown issuer/subject/tenant, disabled account/grant, guessed resource IDs bị deny.
- [ ] Browser profiles độc lập; session fixation/state/cookie behavior được kiểm.
- [ ] Token/refresh-token/session lifecycle và IdP logout khác local RP logout được hiểu.
- [ ] Production HTTPS, Secure/HttpOnly/SameSite, trusted forwarded headers, secret manager, network controls.
- [ ] App nhiều pods có shared session/correlation storage và cache invalidation.
- [ ] API Resource Server (nếu có) validate trusted issuer, JWK signature, audience, scopes và local tenant permissions.
- [ ] SAML adapter (nếu có) verify signature/issuer/audience/recipient/time và stable NameID contract.
- [ ] Account linking và issuer migration có approval/audit, không tự link bằng email.
- [ ] Logs/HAR/metrics không chứa bearer artifacts, secrets, raw SAMLResponse hoặc PII không cần thiết.
- [ ] Negative tests chạy sau mỗi IdP config change, key rotation, Spring Security upgrade và schema migration.
- [ ] Kết luận PASS dựa trên **authentication đúng IdP + mapping đúng account + authorized tenant + truy vấn scoped data**, không chỉ login 200.

**Kết luận:** Tích hợp hai IdP không dừng ở hai mục `ClientRegistration`. Nền tảng an toàn là **trusted issuer verification**, **định danh composite `(iss,sub)`**, **local approved tenant grants**, và **tenant-scoped data access**. Bài lab cố ý dùng `same-sub` và `note_id=1` ở cả hai phía để phát hiện account collision và IDOR. Chỉ được coi bài thực hành thành công khi cả negative cross-tenant cases **bị từ chối**, kể cả khi browser đã đăng nhập SSO hợp lệ.

## 20. Tài liệu chính thức

1. [OpenID Connect Core – Claim Stability and Uniqueness](https://openid.net/specs/openid-connect-core-1_0.html#ClaimStability): cặp `iss/sub`, pairwise subject.
2. [OpenID Connect Discovery](https://openid.net/specs/openid-connect-discovery-1_0.html): issuer, endpoints và JWKS.
3. [Spring Security – OAuth2 Login Core](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): multiple ClientRegistrations and provider mapping.
4. [Spring Security – OAuth2 Login Advanced](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): Authorization Code login and callbacks.
5. [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity` và `@PreAuthorize`.
6. [Spring Security – OAuth2 Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): `oidcLogin()` test double.
7. [Spring Security – Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html): trusted issuer resolver.
8. [Spring Security – Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT signature and claims.
9. [Keycloak – Docker Getting Started](https://www.keycloak.org/getting-started/getting-started-docker): start-dev và realms.
10. [Spring Boot – SQL Database Initialization](https://docs.spring.io/spring-boot/reference/data/sql.html): schema.sql/data.sql.
11. [Spring Security – Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html).
12. [RFC 9700 – OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700).
13. [RFC 7636 – PKCE](https://www.rfc-editor.org/rfc/rfc7636).
14. [OASIS SAML2 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf).
15. [OWASP – Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).
16. [OWASP – Insecure Direct Object Reference Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html).
17. [OWASP – Multi Tenant Security](https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html).
18. [PostgreSQL – Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html).
