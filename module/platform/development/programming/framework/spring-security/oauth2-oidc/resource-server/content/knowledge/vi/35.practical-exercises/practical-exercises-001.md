# Bảo vệ API tra cứu dữ liệu bằng JWT từ một issuer tin cậy

Một API tra cứu dữ liệu thường cho phép client lọc, tìm kiếm, sắp xếp và phân trang kết quả. Khi dữ liệu được bảo vệ bằng OAuth 2.0, API cần xác minh access token trước khi chạy truy vấn, sau đó kiểm tra scope và quyền truy cập dữ liệu tương ứng.

Spring Security Resource Server hỗ trợ quy trình này bằng JWT:

1. Client lấy **access token** từ Authorization Server/Identity Provider đã được tin cậy.
2. Client gửi token trong header `Authorization: Bearer ...`.
3. Resource Server xác minh chữ ký JWT bằng public key được công bố qua JWKS.
4. Resource Server kiểm tra issuer, audience, thời hạn và các claim theo hợp đồng.
5. Spring Security tạo `Authentication` và ánh xạ scope thành authority.
6. Security filter chain kiểm tra authority trước khi controller xử lý request.
7. Service áp dụng quyền ở cấp dữ liệu, thực hiện truy vấn có tham số, giới hạn kết quả và trả DTO an toàn.

Trong bài thực hành này, ta xây dựng API tra cứu catalog tại `GET /api/catalog`. API chỉ chấp nhận access token từ một issuer tin cậy, có audience dành cho `catalog-api` và scope `catalog.read`. Với dữ liệu đa tenant, tenant được lấy từ claim đã xác minh trong token và luôn được đưa vào điều kiện truy vấn.

## 1. Kiến trúc và luồng xử lý

~~~mermaid
flowchart TD
    Client["Client / Web application"]
    IdP["Trusted Authorization Server"]
    RS["Spring Security Resource Server"]
    Decoder["JwtDecoder"]
    JWKS["Trusted JWKS endpoint"]
    Filter["BearerTokenAuthenticationFilter"]
    Authz["Scope authorization"]
    API["CatalogController"]
    Service["CatalogSearchService"]
    Repo["CatalogItemRepository"]
    DB[("Catalog database")]

    Client -->|"1. Request access token"| IdP
    IdP -->|"2. Signed access token"| Client
    Client -->|"3. Authorization: Bearer JWT"| RS
    RS --> Decoder
    Decoder -->|"Load / refresh public keys"| JWKS
    Decoder -->|"Signature + claims valid"| Filter
    Filter --> Authz
    Authz -->|"SCOPE_catalog.read"| API
    API --> Service
    Service --> Repo
    Repo --> DB
    DB -->|"Tenant-scoped page"| Repo
    Repo --> Service
    Service --> API
    API -->|"DTO + pagination metadata"| Client
~~~

Mỗi lớp có một trách nhiệm:

| Lớp | Trách nhiệm |
| --- | --- |
| Authorization Server | Xác thực client/user và phát access token có chữ ký |
| `JwtDecoder` | Xác minh chữ ký, issuer, timestamp và validator tùy chỉnh |
| `SecurityFilterChain` | Chặn request thiếu token hoặc thiếu authority |
| Controller | Nhận query parameters, lấy principal đã xác thực và gọi service |
| Service | Áp dụng quy tắc tra cứu, tenant/resource authorization, pagination và sorting |
| Repository | Tạo truy vấn có tham số đến database |
| Database | Lưu dữ liệu; không tự tin tenant ID do client gửi lên |

**Điều kiện quan trọng:** token phải là access token dành cho API. ID token trong OIDC chứng minh sự kiện đăng nhập cho client; nó không thay thế access token để gọi Resource Server.

## 2. Hợp đồng access token

Trước khi viết code, thống nhất token contract giữa Authorization Server và API.

Ví dụ payload JWT đã ký (chỉ minh họa claims):

~~~json
{
  "iss": "https://identity.example.test/realms/shop",
  "sub": "user-1842",
  "aud": ["catalog-api"],
  "iat": 1794700800,
  "nbf": 1794697200,
  "exp": 1794704400,
  "scope": "catalog.read",
  "tenant_id": "tenant-42"
}
~~~

| Claim/header | Ý nghĩa | Cách API sử dụng |
| --- | --- | --- |
| `iss` | Issuer đã phát hành token | So sánh chính xác với issuer cấu hình |
| `sub` | Subject/identity của caller | Principal name và audit attribution |
| `aud` | Resource/API nhận token | Bắt buộc chứa `catalog-api` |
| `iat` | Thời điểm phát hành | Có thể dùng trong policy bổ sung |
| `nbf` | Token bắt đầu có hiệu lực | Timestamp validation |
| `exp` | Thời điểm hết hạn | Từ chối token hết hạn |
| `scope` | Các quyền OAuth được cấp | Ánh xạ `catalog.read` thành `SCOPE_catalog.read` |
| `tenant_id` | Tenant được gắn với identity/token | Phạm vi dữ liệu khi API phục vụ nhiều tenant |
| JOSE `kid` | ID của signing key | Chọn public key tương ứng từ JWKS |

### 2.1. Chỉ tin claims sau khi JWT được xác minh

Payload JWT có thể đọc được mà không cần secret. Việc giải mã Base64URL không chứng minh token hợp lệ. Chỉ sử dụng `sub`, `scope`, `tenant_id` và các claim khác sau khi `JwtDecoder` đã:

- Xác minh chữ ký bằng public key từ JWKS URI tin cậy.
- Chỉ chấp nhận thuật toán ký được cấu hình.
- Kiểm tra issuer.
- Kiểm tra thời hạn và các timestamp liên quan.
- Kiểm tra audience dành cho API.

Không lấy tenant, user ID hoặc role từ query parameter/header tùy ý rồi dùng thay claim đã xác minh.

### 2.2. Access token và ID token

Hai loại token có mục đích khác nhau:

| Token | Đối tượng nhận | Mục đích |
| --- | --- | --- |
| ID token | OIDC client | Thông tin xác thực người dùng cho client |
| Access token | Resource Server/API | Cấp quyền truy cập resource |

Không chấp nhận ID token chỉ vì nó có chữ ký hợp lệ từ cùng issuer. Hãy yêu cầu audience của API và, nếu Authorization Server hỗ trợ, kiểm tra token profile/type (`typ`, `token_use` hoặc claim theo hợp đồng). Không suy diễn access-token profile chỉ từ tên claim `sub`.

## 3. Tạo project và dependencies

Ví dụ dùng Java 21, Spring Boot 3.x và Spring Security 6.x. Các API `SecurityFilterChain`, `oauth2ResourceServer().jwt()` và `JwtDecoder` cũng là nền tảng của các bản Spring Security mới hơn; hãy dùng dependency versions đồng bộ với Spring Boot đang triển khai.

Dependencies Maven tối thiểu:

~~~xml
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
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
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
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Resource Server starter cung cấp integration JWT/JWKS và OAuth2 bearer support. `spring-boot-starter-security` cung cấp filter chain, còn `spring-security-test` hỗ trợ test authorization.

Một cấu trúc package dễ theo dõi:

~~~text
com.example.catalog
├── config
│   └── SecurityConfig.java
├── catalog
│   ├── CatalogController.java
│   ├── CatalogSearchService.java
│   ├── CatalogItem.java
│   ├── CatalogItemRepository.java
│   ├── CatalogItemSpecifications.java
│   ├── CatalogItemResponse.java
│   └── CatalogSearchResponse.java
└── CatalogApplication.java
~~~

## 4. Cấu hình issuer và audience

Đặt issuer và audience ở externalized configuration. Không hardcode issuer theo môi trường hoặc để client gửi JWKS URI.

`application.yml`:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: catalog-api
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${OIDC_ISSUER_URI}
          # Có thể cấu hình jwk-set-uri trực tiếp nếu hạ tầng yêu cầu.
          # issuer-uri vẫn cần được giữ để kiểm tra claim iss.
  datasource:
    url: ${DB_URL:jdbc:postgresql://localhost:5432/catalog}
    username: ${DB_USERNAME:catalog}
    password: ${DB_PASSWORD}
  jpa:
    open-in-view: false
    hibernate:
      ddl-auto: validate

app:
  security:
    audience: ${API_AUDIENCE:catalog-api}
~~~

Ví dụ môi trường:

~~~text
OIDC_ISSUER_URI=https://identity.example.test/realms/shop
API_AUDIENCE=catalog-api
DB_URL=jdbc:postgresql://db.internal:5432/catalog
DB_USERNAME=catalog_api
DB_PASSWORD=<injected-secret>
~~~

`issuer-uri` phải trùng chính xác với claim `iss` trong token và metadata của issuer. Dấu slash cuối, scheme và path có thể làm issuer khác nhau.

### 4.1. Discovery metadata và JWKS

Spring Security dùng issuer để discovery metadata và tìm JWKS URI. Decoder tải public keys từ JWKS và có thể cache chúng. Không cần tải JWKS cho mỗi request nếu key phù hợp đã có trong cache.

Nếu muốn tránh discovery metadata chỉ để tìm JWKS, có thể cấu hình `jwk-set-uri` trực tiếp cùng `issuer-uri`. Khi đó issuer validation vẫn phải được giữ. Direct URI không bỏ qua chữ ký, key selection hoặc claim validation.

### 4.2. Kiểm tra cấu hình trước khi chạy

Xác nhận:

- Issuer URI thuộc IdP được quản trị và tin cậy.
- JWKS URI (nếu cấu hình trực tiếp) nằm trong trust boundary.
- Audience là identifier của API, không phải client ID tùy tiện.
- TLS certificate chain hợp lệ.
- API không lấy issuer/JWKS URL từ JWT chưa xác minh hoặc request parameter.
- Không đưa secret database hoặc client credential vào repository.

## 5. Cấu hình Spring Security Resource Server

Ta cần hai phần: decoder kiểm tra JWT và filter chain kiểm tra authority.

### 5.1. Properties cho security contract

~~~java
package com.example.catalog.config;

import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.security")
public record ApiSecurityProperties(
        @NotBlank String audience) {
}
~~~

Issuer được lấy từ `spring.security.oauth2.resourceserver.jwt.issuer-uri`; audience lấy từ `app.security.audience`.

### 5.2. Audience validator

Issuer validator mặc định không thay thế audience validation. API phải tự xác nhận token được phát hành cho đúng resource:

~~~java
package com.example.catalog.config;

import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

public final class AudienceValidator implements OAuth2TokenValidator<Jwt> {

    private final String requiredAudience;

    public AudienceValidator(String requiredAudience) {
        this.requiredAudience = requiredAudience;
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        if (jwt.getAudience().contains(requiredAudience)) {
            return OAuth2TokenValidatorResult.success();
        }

        OAuth2Error error = new OAuth2Error(
                "invalid_token",
                "Token is not intended for this API",
                null);
        return OAuth2TokenValidatorResult.failure(error);
    }
}
~~~

### 5.3. JwtDecoder với issuer, timestamp và audience

~~~java
package com.example.catalog.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
@EnableConfigurationProperties(ApiSecurityProperties.class)
public class JwtDecoderConfig {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}")
            String issuer,
            ApiSecurityProperties properties) {

        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withIssuerLocation(issuer).build();

        OAuth2TokenValidator<Jwt> defaultValidators =
                JwtValidators.createDefaultWithIssuer(issuer);
        OAuth2TokenValidator<Jwt> audienceValidator =
                new AudienceValidator(properties.audience());

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        defaultValidators,
                        audienceValidator,
                        new RequiredTenantClaimValidator()));

        return decoder;
    }
}
~~~

`JwtValidators.createDefaultWithIssuer` giữ issuer và timestamp validation mặc định. `DelegatingOAuth2TokenValidator` ghép các validator; không thay validator mặc định bằng audience validator đơn lẻ.

Validator tenant trong ví dụ áp dụng cho API đa tenant. Nếu API chỉ phục vụ một tenant hoặc lấy tenant từ một nguồn server-side khác, hãy điều chỉnh hợp đồng thay vì bắt buộc claim không cần thiết:

~~~java
package com.example.catalog.config;

import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

public final class RequiredTenantClaimValidator
        implements OAuth2TokenValidator<Jwt> {

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        String tenantId = jwt.getClaimAsString("tenant_id");
        if (tenantId != null && !tenantId.isBlank()) {
            return OAuth2TokenValidatorResult.success();
        }

        return OAuth2TokenValidatorResult.failure(new OAuth2Error(
                "invalid_token",
                "Required tenant claim is missing",
                null));
    }
}
~~~

Nếu dùng cấu hình `jwk-set-uri` trực tiếp, tạo decoder bằng `NimbusJwtDecoder.withJwkSetUri(jwksUri)` rồi gắn cùng validator issuer/time/audience. Không bỏ issuer validation khi chuyển từ discovery sang direct URI.

### 5.4. SecurityFilterChain và scope authorization

~~~java
package com.example.catalog.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/catalog", "/api/catalog/**")
                    .hasAuthority("SCOPE_catalog.read")
                .requestMatchers(HttpMethod.POST, "/api/catalog", "/api/catalog/**")
                    .hasAuthority("SCOPE_catalog.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(resourceServer -> resourceServer
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Chính sách trong ví dụ:

- Health endpoint được phép truy cập theo cấu hình vận hành.
- GET catalog yêu cầu `SCOPE_catalog.read`.
- POST catalog yêu cầu `SCOPE_catalog.write`.
- Route chưa được khai báo bị từ chối.
- Session không được tạo để lưu authentication giữa các request.

Chỉ disable CSRF khi API thực sự dùng bearer token trong Authorization header và không dùng browser cookie/session làm credential. Nếu ứng dụng cũng có form login/cookie authentication, cần thiết kế CSRF riêng thay vì disable toàn cục.

### 5.5. Scope được ánh xạ thành authority

Với claim:

~~~json
{
  "scope": "catalog.read catalog.export"
}
~~~

Spring Security mặc định tạo:

~~~text
SCOPE_catalog.read
SCOPE_catalog.export
~~~

Do đó `hasAuthority("SCOPE_catalog.read")` khớp với scope `catalog.read`. Không nhầm scope với role. Nếu issuer phát role trong claim `roles`, phải cấu hình converter riêng và xác định rõ allowlist/prefix; không tự coi mọi chuỗi trong `roles` là quyền hợp lệ.

### 5.6. Principal và claim tenant

`JwtAuthenticationToken` giữ JWT đã xác minh làm principal. Trong controller, có thể nhận `@AuthenticationPrincipal Jwt jwt`:

~~~java
String subject = jwt.getSubject();
String tenantId = jwt.getClaimAsString("tenant_id");
~~~

`sub` định danh subject trong phạm vi issuer; nếu có nhiều issuer, không giả định hai token có cùng `sub` là cùng một người dùng. Tenant claim chỉ được dùng sau khi decoder đã xác minh issuer, chữ ký và token contract.

## 6. Mô hình dữ liệu catalog và repository

Ví dụ dữ liệu có tenant, trạng thái hiển thị và các trường được phép trả về:

~~~java
package com.example.catalog.catalog;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(
    name = "catalog_item",
    indexes = {
        @Index(name = "idx_catalog_tenant_active", columnList = "tenant_id, active"),
        @Index(name = "idx_catalog_tenant_name", columnList = "tenant_id, name")
    })
public class CatalogItem {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(name = "tenant_id", nullable = false, length = 80)
    private String tenantId;

    @Column(nullable = false, length = 180)
    private String name;

    @Column(nullable = false, length = 60)
    private String category;

    @Column(length = 2000)
    private String description;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    @Column(nullable = false, length = 3)
    private String currency;

    @Column(nullable = false)
    private boolean active;

    @Column(nullable = false)
    private Instant createdAt;

    protected CatalogItem() {
    }

    public CatalogItem(
            String tenantId,
            String name,
            String category,
            String description,
            BigDecimal price,
            String currency,
            boolean active,
            Instant createdAt) {
        this.tenantId = tenantId;
        this.name = name;
        this.category = category;
        this.description = description;
        this.price = price;
        this.currency = currency;
        this.active = active;
        this.createdAt = createdAt;
    }

    public UUID getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getName() { return name; }
    public String getCategory() { return category; }
    public String getDescription() { return description; }
    public BigDecimal getPrice() { return price; }
    public String getCurrency() { return currency; }
    public boolean isActive() { return active; }
    public Instant getCreatedAt() { return createdAt; }
}
~~~

Entity có `tenantId` để database query giới hạn ngay từ đầu. Nếu hệ thống chỉ có một tenant, trường này có thể được thay bằng cấu trúc dữ liệu tương ứng; với multi-tenant, không được truy vấn toàn bộ bảng rồi lọc tenant trong Java.

Repository:

~~~java
package com.example.catalog.catalog;

import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

public interface CatalogItemRepository
        extends JpaRepository<CatalogItem, UUID>,
                JpaSpecificationExecutor<CatalogItem> {
}
~~~

`JpaSpecificationExecutor` cho phép ghép điều kiện tìm kiếm và tenant filter thành truy vấn SQL có tham số. Không nối trực tiếp query string của client vào JPQL/SQL.

### 6.1. Specification cho tìm kiếm

~~~java
package com.example.catalog.catalog;

import jakarta.persistence.criteria.Predicate;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import org.springframework.data.jpa.domain.Specification;

public final class CatalogItemSpecifications {

    private CatalogItemSpecifications() {
    }

    public static Specification<CatalogItem> search(
            String tenantId,
            String queryText,
            String category) {

        return (root, query, criteriaBuilder) -> {
            List<Predicate> predicates = new ArrayList<>();

            predicates.add(criteriaBuilder.equal(
                    root.get("tenantId"), tenantId));
            predicates.add(criteriaBuilder.isTrue(
                    root.get("active")));

            String pattern = "%"
                    + escapeLike(queryText.toLowerCase(Locale.ROOT))
                    + "%";
            predicates.add(criteriaBuilder.like(
                    criteriaBuilder.lower(root.get("name")),
                    pattern,
                    '\\'));

            if (category != null && !category.isBlank()) {
                predicates.add(criteriaBuilder.equal(
                        root.get("category"), category));
            }

            return criteriaBuilder.and(
                    predicates.toArray(Predicate[]::new));
        };
    }

    private static String escapeLike(String value) {
        return value
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_");
    }
}
~~~

Tenant predicate luôn được thêm vào cùng query. Người gọi không thể xóa điều kiện này bằng cách truyền một query parameter khác.

`escapeLike` coi ký tự `%` và `_` trong chuỗi tìm kiếm là ký tự literal, tránh để người dùng vô tình biến query thành wildcard rộng. `CriteriaBuilder.like` dùng ký tự escape tương ứng. Với database/collation khác nhau, kiểm tra behavior case-insensitive và escape syntax của hệ quản trị đang dùng.

### 6.2. Index theo query thực tế

Index cần được chọn theo workload:

- `(tenant_id, active)` hỗ trợ lọc tenant và trạng thái.
- `(tenant_id, name)` có thể hỗ trợ lookup/sort theo tên.
- Nếu tìm kiếm substring bằng `%term%`, B-tree thông thường có thể không tận dụng index hiệu quả; cân nhắc full-text/trigram index tùy database.
- Nếu sort theo `created_at` hoặc `price`, xem xét composite index có tenant prefix.

Không thêm index theo mọi field một cách máy móc. Đo query plan, selectivity và chi phí ghi dữ liệu.

## 7. Service tìm kiếm: tenant, pagination và sorting

Service là nơi áp dụng các giới hạn nghiệp vụ. Không để controller tự tạo SQL hoặc để repository nhận tên cột tùy ý từ client.

### 7.1. DTO response

~~~java
package com.example.catalog.catalog;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record CatalogItemResponse(
        UUID id,
        String name,
        String category,
        String description,
        BigDecimal price,
        String currency,
        Instant createdAt) {

    static CatalogItemResponse from(CatalogItem item) {
        return new CatalogItemResponse(
                item.getId(),
                item.getName(),
                item.getCategory(),
                item.getDescription(),
                item.getPrice(),
                item.getCurrency(),
                item.getCreatedAt());
    }
}
~~~

Không serialize JPA entity trực tiếp. DTO giúp kiểm soát field công khai và tránh vô tình trả internal flags, tenant metadata, relationships hoặc dữ liệu nhạy cảm.

Response phân trang:

~~~java
package com.example.catalog.catalog;

import java.util.List;

public record CatalogSearchResponse(
        List<CatalogItemResponse> items,
        int page,
        int size,
        long totalElements,
        int totalPages,
        boolean last) {
}
~~~

### 7.2. Search service

~~~java
package com.example.catalog.catalog;

import java.util.Map;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CatalogSearchService {

    private static final int MAX_PAGE_SIZE = 100;
    private static final int MAX_PAGE_INDEX = 10_000;

    private static final Map<String, String> SORT_FIELDS = Map.of(
            "name", "name",
            "price", "price",
            "createdAt", "createdAt");

    private final CatalogItemRepository repository;

    public CatalogSearchService(CatalogItemRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public CatalogSearchResponse search(
            String tenantId,
            String queryText,
            String category,
            int page,
            int size,
            String sortField,
            String direction) {

        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Tenant is required");
        }
        if (page < 0 || page > MAX_PAGE_INDEX) {
            throw new IllegalArgumentException("Page is out of range");
        }
        if (size < 1 || size > MAX_PAGE_SIZE) {
            throw new IllegalArgumentException("Page size is out of range");
        }
        if (queryText == null || queryText.trim().length() < 2
                || queryText.trim().length() > 100) {
            throw new IllegalArgumentException("Search text is out of range");
        }
        if (!"asc".equalsIgnoreCase(direction)
                && !"desc".equalsIgnoreCase(direction)) {
            throw new IllegalArgumentException("Unsupported sort direction");
        }

        String entityField =
                sortField == null ? null : SORT_FIELDS.get(sortField);
        if (entityField == null) {
            throw new IllegalArgumentException("Unsupported sort field");
        }

        Sort.Direction sortDirection =
                "desc".equalsIgnoreCase(direction)
                        ? Sort.Direction.DESC
                        : Sort.Direction.ASC;

        Pageable pageable = PageRequest.of(
                page,
                size,
                Sort.by(sortDirection, entityField)
                        .and(Sort.by(Sort.Direction.ASC, "id")));

        Page<CatalogItem> result = repository.findAll(
                CatalogItemSpecifications.search(
                        tenantId, queryText, category),
                pageable);

        return new CatalogSearchResponse(
                result.getContent().stream()
                        .map(CatalogItemResponse::from)
                        .toList(),
                result.getNumber(),
                result.getSize(),
                result.getTotalElements(),
                result.getTotalPages(),
                result.isLast());
    }
}
~~~

`SORT_FIELDS` là allowlist giữa tên sort public và thuộc tính entity. Không truyền trực tiếp `sort` từ URL vào `Sort.by(...)`; điều đó có thể làm lộ field nội bộ hoặc tạo query không mong muốn.

### 7.3. Vì sao tenant phải nằm trong SQL predicate?

Giả sử token của Alice thuộc tenant A. API phải truy vấn:

~~~sql
SELECT id, name, category, price
FROM catalog_item
WHERE tenant_id = :tenantId
  AND active = true
  AND lower(name) LIKE :pattern
ORDER BY name ASC
LIMIT :limit OFFSET :offset;
~~~

Giá trị `:tenantId` lấy từ claim `tenant_id` trong JWT đã xác minh. Không lấy từ `?tenantId=tenant-B`.

Nếu query lấy tất cả kết quả rồi lọc tenant trong Java, dữ liệu tenant khác đã đi qua tầng application, có thể bị lộ qua pagination count, memory, logs hoặc bug mapping. Tenant condition phải được áp dụng trong truy vấn dữ liệu ngay từ đầu.

## 8. Controller và kiểm tra query parameters

Controller nhận JWT đã xác minh bằng `@AuthenticationPrincipal`. Tenant lấy từ token; query parameters chỉ quyết định điều kiện tra cứu trong tenant đó.

~~~java
package com.example.catalog.catalog;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/catalog")
@Validated
public class CatalogController {

    private final CatalogSearchService searchService;

    public CatalogController(CatalogSearchService searchService) {
        this.searchService = searchService;
    }

    @GetMapping
    public CatalogSearchResponse search(
            @RequestParam("q")
            @NotBlank
            @Size(min = 2, max = 100)
            String q,

            @RequestParam(name = "category", required = false)
            @Size(max = 60)
            String category,

            @RequestParam(name = "page", defaultValue = "0")
            @Min(0)
            @Max(10_000)
            int page,

            @RequestParam(name = "size", defaultValue = "20")
            @Min(1)
            @Max(100)
            int size,

            @RequestParam(name = "sort", defaultValue = "name")
            @Pattern(regexp = "name|price|createdAt")
            String sort,

            @RequestParam(name = "direction", defaultValue = "asc")
            @Pattern(regexp = "(?i)asc|desc")
            String direction,

            @AuthenticationPrincipal Jwt jwt) {

        String tenantId = jwt.getClaimAsString("tenant_id");

        return searchService.search(
                tenantId,
                q.trim(),
                category,
                page,
                size,
                sort,
                direction);
    }
}
~~~

Các giới hạn được áp dụng:

- Query `q` bắt buộc, dài 2–100 ký tự.
- `category` tối đa 60 ký tự.
- `page` bắt đầu từ 0 và có giới hạn.
- `size` tối đa 100 bản ghi.
- `sort` chỉ nhận `name`, `price` hoặc `createdAt`.
- `direction` chỉ nhận `asc` hoặc `desc`.

`@Validated` bật method validation cho các constraint trên tham số controller. Service vẫn kiểm tra giới hạn quan trọng để bảo vệ khi được gọi từ một đường khác ngoài HTTP.

### 8.1. Vì sao không nhận tenant từ query parameter?

Không tạo endpoint kiểu:

~~~http
GET /api/catalog?q=keyboard&tenantId=tenant-B
~~~

Caller có thể đổi `tenantId` để thử đọc dữ liệu của tenant khác. Với API multi-tenant, tenant được xác định từ claim đã xác minh:

~~~java
String tenantId = jwt.getClaimAsString("tenant_id");
~~~

Nếu cần quản trị viên tra cứu nhiều tenant, đó phải là một use case riêng với scope/role và policy rõ ràng. Không thêm một query parameter tenant chung cho mọi caller.

### 8.2. Xử lý validation error

Query sai định dạng, vượt giới hạn hoặc sort không được hỗ trợ nên trả `400 Bad Request`. Có thể dùng `@RestControllerAdvice` để chuẩn hóa response:

~~~java
package com.example.catalog.catalog;

import jakarta.validation.ConstraintViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler({
        ConstraintViolationException.class,
        MethodArgumentTypeMismatchException.class,
        IllegalArgumentException.class
    })
    ResponseEntity<ProblemDetail> invalidSearchRequest(Exception exception) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "Search parameters are invalid");
        problem.setTitle("Invalid search request");
        return ResponseEntity.badRequest().body(problem);
    }
}
~~~

Trong ứng dụng dùng Spring Framework 6.1+, kiểm tra thêm `HandlerMethodValidationException` nếu controller method validation được xử lý theo exception này. Không trả stack trace, SQL hoặc chi tiết internal field cho caller.

`@RestControllerAdvice` xử lý lỗi trong MVC layer. Authentication failure và access denied xảy ra trong Spring Security filter chain, do `AuthenticationEntryPoint`/`AccessDeniedHandler` xử lý; không kỳ vọng controller advice bắt được chúng.

## 9. Gọi API và đọc response

Client gửi access token trong Authorization header:

~~~bash
curl --get "https://api.example.test/api/catalog" \
  --header "Authorization: Bearer $ACCESS_TOKEN" \
  --data-urlencode "q=mechanical keyboard" \
  --data-urlencode "category=peripherals" \
  --data-urlencode "page=0" \
  --data-urlencode "size=20" \
  --data-urlencode "sort=name" \
  --data-urlencode "direction=asc"
~~~

Ví dụ response thành công:

~~~json
{
  "items": [
    {
      "id": "f29f94d4-9c1d-4f64-8c45-0f59a6a9a401",
      "name": "Mechanical Keyboard K2",
      "category": "peripherals",
      "description": "Compact mechanical keyboard",
      "price": 89.90,
      "currency": "USD",
      "createdAt": "2026-10-10T08:30:00Z"
    }
  ],
  "page": 0,
  "size": 20,
  "totalElements": 1,
  "totalPages": 1,
  "last": true
}
~~~

Các response status thường gặp:

| Tình huống | HTTP status | Ý nghĩa |
| --- | --- | --- |
| Token hợp lệ, đủ scope, query hợp lệ | 200 | Trả trang kết quả; danh sách có thể rỗng |
| Không gửi bearer token | 401 | Chưa được xác thực |
| Token hết hạn/chữ ký sai/issuer hoặc audience sai | 401 | Token không hợp lệ |
| Token hợp lệ nhưng thiếu `catalog.read` | 403 | Đã xác thực nhưng không đủ quyền |
| Query sai, page/size vượt giới hạn, sort không cho phép | 400 | Request không hợp lệ |
| Lỗi database/dependency nội bộ | 5xx | Server không xử lý được request |

### 9.1. Không có kết quả vẫn là 200

Một tìm kiếm hợp lệ nhưng không có bản ghi phù hợp thường trả `200 OK` với `items: []` và metadata phân trang tương ứng. Không dùng `404` cho mọi trường hợp tìm kiếm rỗng; `404` phù hợp hơn khi client yêu cầu một resource cụ thể theo ID và resource đó không tồn tại hoặc không được phép hiển thị.

### 9.2. Pagination ổn định

Service thêm `id` làm sort phụ để thứ tự ổn định khi nhiều bản ghi có cùng tên/giá/thời điểm. Nếu chỉ sort theo field không unique, record có thể đổi vị trí giữa các trang khi dữ liệu thay đổi.

Offset pagination phù hợp với tập dữ liệu vừa phải. Với bảng rất lớn hoặc page sâu, `OFFSET` có thể tốn kém và dữ liệu thay đổi có thể gây bỏ sót/trùng record giữa các trang. Khi đó cân nhắc cursor/keyset pagination theo sort key ổn định, ví dụ `(created_at, id)`.

## 10. Kiểm thử bảo mật và data isolation

Không nên gom tất cả vào một test. Mỗi test nên chứng minh một boundary:

1. Decoder xác minh JWT và claims.
2. Filter chain yêu cầu đúng scope.
3. Controller kiểm tra query parameters.
4. Service/repository giới hạn dữ liệu theo tenant.
5. API không trả field ngoài DTO.

### 10.1. MockMvc test cho scope authorization

`spring-security-test` cung cấp request post processor `jwt()` để tạo mock JWT Authentication:

~~~java
package com.example.catalog.catalog;

import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.BDDMockito.given;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(CatalogController.class)
@Import(com.example.catalog.config.SecurityConfig.class)
class CatalogControllerSecurityTest {

    @Autowired
    MockMvc mvc;

    @MockBean
    CatalogSearchService searchService;

    @MockBean
    JwtDecoder jwtDecoder;

    @Test
    void allowsCatalogReadScope() throws Exception {
        given(searchService.search(
                eq("tenant-42"), eq("keyboard"), eq((String) null),
                eq(0), eq(20), eq("name"), eq("asc")))
            .willReturn(new CatalogSearchResponse(
                List.of(), 0, 20, 0, 0, true));

        mvc.perform(get("/api/catalog")
                .param("q", "keyboard")
                .with(jwt()
                    .jwt(token -> token
                        .subject("user-1842")
                        .claim("tenant_id", "tenant-42"))
                    .authorities(new SimpleGrantedAuthority(
                        "SCOPE_catalog.read"))))
            .andExpect(status().isOk());
    }

    @Test
    void rejectsRequestWithoutBearerAuthentication() throws Exception {
        mvc.perform(get("/api/catalog").param("q", "keyboard"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void rejectsAuthenticatedCallerWithoutReadScope() throws Exception {
        mvc.perform(get("/api/catalog")
                .param("q", "keyboard")
                .with(jwt()
                    .jwt(token -> token
                        .subject("user-1842")
                        .claim("tenant_id", "tenant-42"))
                    .authorities(new SimpleGrantedAuthority(
                        "SCOPE_profile.read"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void rejectsInvalidSearchParameters() throws Exception {
        mvc.perform(get("/api/catalog")
                .param("q", "x")
                .with(jwt().authorities(new SimpleGrantedAuthority(
                    "SCOPE_catalog.read"))))
            .andExpect(status().isBadRequest());
    }
}
~~~

Trong `@WebMvcTest`, cần mock `JwtDecoder` nếu slice test khởi tạo Resource Server filter chain và không có decoder bean trong context. Tên annotation mock phụ thuộc Spring Boot/Spring Framework version: các bản mới có thể dùng `@MockitoBean`; `@MockBean` được dùng trong nhiều dự án Boot 3.x.

`jwt()` tạo Authentication phục vụ test authorization. Nó **không** xác minh chữ ký JWT, không gọi JWKS, không chạy audience/issuer validators của decoder thật. Vì vậy không dùng test này để kết luận decoder đã được cấu hình đúng.

### 10.2. Unit test audience validator

~~~java
package com.example.catalog.config;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;

class AudienceValidatorTest {

    private final AudienceValidator validator =
            new AudienceValidator("catalog-api");

    @Test
    void acceptsTokenForCatalogApi() {
        Jwt jwt = Jwt.withTokenValue("test-token")
                .header("alg", "none")
                .audience(List.of("catalog-api"))
                .build();

        assertThat(validator.validate(jwt).hasErrors()).isFalse();
    }

    @Test
    void rejectsTokenForAnotherApi() {
        Jwt jwt = Jwt.withTokenValue("test-token")
                .header("alg", "none")
                .audience(List.of("billing-api"))
                .build();

        assertThat(validator.validate(jwt).hasErrors()).isTrue();
    }
}
~~~

Trong unit test validator, JWT object là input fixture cho logic claim; header `alg=none` không phải token được phép gửi vào API. Test decoder thật phải xác minh JWS signature.

### 10.3. DataJpaTest cho tenant isolation

Test repository phải chứng minh query của tenant A không trả record tenant B:

~~~java
package com.example.catalog.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;

@DataJpaTest
class CatalogItemTenantIsolationTest {

    @Autowired
    CatalogItemRepository repository;

    @Test
    void searchReturnsOnlyRowsFromTheAuthenticatedTenant() {
        repository.save(new CatalogItem(
                "tenant-A", "Keyboard A", "peripherals", null,
                new BigDecimal("80.00"), "USD", true, Instant.now()));
        repository.save(new CatalogItem(
                "tenant-B", "Keyboard B", "peripherals", null,
                new BigDecimal("90.00"), "USD", true, Instant.now()));

        Page<CatalogItem> result = repository.findAll(
                CatalogItemSpecifications.search(
                    "tenant-A", "keyboard", "peripherals"),
                PageRequest.of(0, 20));

        assertThat(result.getContent())
                .extracting(CatalogItem::getTenantId)
                .containsOnly("tenant-A");
        assertThat(result.getTotalElements()).isEqualTo(1);
    }
}
~~~

Đây là test data boundary. Nếu chỉ mock repository trong controller test, chưa có bằng chứng SQL/Specification thực sự thêm tenant predicate.

### 10.4. Integration test với JWT ký thật

Để kiểm tra signature, issuer, audience và filter chain cùng lúc, tạo RSA key pair riêng cho test:

1. Test encoder ký JWT bằng private key.
2. `JwtDecoder` xác minh bằng public key tương ứng hoặc JWKS test server.
3. JWT chứa issuer, audience, subject, scope, tenant và thời hạn hợp lệ.
4. Gửi token qua header `Authorization: Bearer ...` bằng MockMvc.
5. Gửi token sai chữ ký, sai audience, issuer khác và hết hạn; tất cả phải bị từ chối.

Ví dụ cấu hình decoder cục bộ trong test:

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
        .withPublicKey((RSAPublicKey) testKeyPair.getPublic())
        .build();

decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuer),
        new AudienceValidator("catalog-api"),
        new RequiredTenantClaimValidator()));
~~~

Encoder có thể dùng `NimbusJwtEncoder` với `ImmutableJWKSet` chứa public/private JWK test. Trong production, decoder nên lấy public key từ JWKS URI của issuer tin cậy; private key chỉ nằm ở test fixture/Authorization Server.

### 10.5. Ma trận test nên có

| Test case | JWT/Authentication | Query/data | Kết quả |
| --- | --- | --- | --- |
| Không có token | Không có | Hợp lệ | 401 |
| Chữ ký sai | Không hợp lệ | Hợp lệ | 401 |
| Issuer sai | Không hợp lệ | Hợp lệ | 401 |
| Audience khác API | Không hợp lệ | Hợp lệ | 401 |
| Token hết hạn | Không hợp lệ | Hợp lệ | 401 |
| Thiếu `tenant_id` trong multi-tenant profile | Contract không hợp lệ | Hợp lệ | 401 |
| JWT hợp lệ, thiếu `catalog.read` | Authenticated | Hợp lệ | 403 |
| JWT hợp lệ, đủ scope | Authenticated | Query hợp lệ | 200 |
| JWT hợp lệ, query quá dài | Authenticated | Không hợp lệ | 400 |
| JWT hợp lệ, sort không allowlist | Authenticated | Không hợp lệ | 400 |
| JWT tenant A | Authenticated | Có record A và B | Chỉ trả A |
| JWT hợp lệ, không có record khớp | Authenticated | Hợp lệ | 200 với danh sách rỗng |

## 11. Các lỗi bảo mật thường gặp

### 11.1. Chỉ decode JWT, không verify signature

Đọc payload bằng Base64URL rồi tin `sub`, `scope` hoặc `tenant_id` cho phép caller tự tạo claims. Dùng `JwtDecoder` và public key từ JWKS tin cậy.

### 11.2. Không kiểm tra audience

Một JWT từ cùng issuer có thể được phát hành cho API khác. Nếu chỉ kiểm tra issuer/signature, token dành cho `billing-api` có thể bị dùng nhầm ở `catalog-api`. Luôn kiểm tra audience theo resource server.

### 11.3. Dùng ID token để gọi API

ID token dành cho OIDC client, không phải access token cho API. Yêu cầu access token có audience và scope phù hợp.

### 11.4. Chỉ kiểm tra authenticated, không kiểm tra scope

`.authenticated()` chỉ nói caller đã xác thực. API tra cứu catalog cần authority cụ thể như `SCOPE_catalog.read`; nếu không, mọi token hợp lệ có thể đọc dữ liệu.

### 11.5. Tin tenant do client gửi

Query parameter `tenantId` hoặc header `X-Tenant-Id` có thể bị sửa. Lấy tenant từ claim đã xác minh hoặc server-side authorization context, rồi áp dụng trong query.

### 11.6. Lọc tenant sau khi tải dữ liệu

Lọc sau query có thể làm lộ total count, tốn memory và tạo đường rò dữ liệu. Tenant condition phải nằm trong SQL/Specification trước pagination.

### 11.7. Nối query string vào SQL

Không dùng:

~~~java
String sql = "select * from catalog_item where name like '%"
        + q + "%'";
~~~

Dùng JPA Criteria/parameter binding. Với sort, dùng allowlist tên field; bind parameter không thể thay thế identifier cột một cách an toàn.

### 11.8. Pagination không giới hạn

`size=1000000` hoặc page index cực lớn có thể tạo truy vấn tốn kém. Giới hạn page size, query length, sort fields và cân nhắc cursor pagination.

### 11.9. Trả JPA entity trực tiếp

Entity có thể chứa internal fields, relationship hoặc tenant metadata. Dùng DTO projection/response mapping để kiểm soát dữ liệu công khai.

### 11.10. Tắt CSRF cho API dùng cookie

CSRF disable chỉ phù hợp với API stateless dùng bearer token trong Authorization header và không dựa vào cookie/session. Nếu browser gửi cookie tự động, phải giữ CSRF protection hoặc tách security chain phù hợp.

### 11.11. Cấu hình sai issuer/JWKS

Không dùng issuer URL từ request, không tắt TLS validation và không lấy public key từ nguồn tùy ý. JWKS URI phải thuộc trust configuration do operator quản lý.

### 11.12. Ghi token vào log

Không log raw JWT, opaque token, Authorization header hoặc introspection request body. Ghi subject/issuer theo chính sách dữ liệu, correlation ID và error category cần thiết; redact credential ở tracing layer.

## 12. CORS, browser client và API documentation

CORS chỉ quyết định browser origin nào được phép gửi request và đọc response. CORS không thay thế JWT authentication hoặc scope authorization.

Nếu frontend chạy ở origin riêng, cấu hình allowlist cụ thể:

~~~java
package com.example.catalog.config;

import java.time.Duration;
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class CorsConfig {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration configuration = new CorsConfiguration();
        configuration.setAllowedOrigins(
                List.of("https://app.example.test"));
        configuration.setAllowedMethods(
                List.of("GET", "POST", "OPTIONS"));
        configuration.setAllowedHeaders(
                List.of("Authorization", "Content-Type"));
        configuration.setAllowCredentials(false);
        configuration.setMaxAge(Duration.ofMinutes(30));

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", configuration);
        return source;
    }
}
~~~

Bật CORS trong filter chain:

~~~java
return http
    .cors(Customizer.withDefaults())
    .csrf(csrf -> csrf.disable())
    // session management, authorization và resource server...
    .build();
~~~

Đặt đúng origin của frontend. Không dùng wildcard origin khi bật credentials. Ví dụ này không dùng cookie credentials; bearer token được gửi rõ ràng trong Authorization header. Nếu ứng dụng dùng cookie, cần đánh giá lại CSRF và CORS credentials.

Nếu API chỉ được gọi server-to-server hoặc không có browser frontend, có thể không cần CORS configuration.

### 12.1. Mô tả bearer authentication trong OpenAPI

Tài liệu API nên khai báo HTTP bearer scheme với format JWT để client biết cần gửi Authorization header:

~~~yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT

security:
  - bearerAuth: []
~~~

OpenAPI security scheme chỉ mô tả hợp đồng cho client/tooling. Nó không thay thế `SecurityFilterChain`, decoder hoặc authorization ở runtime.

## 13. Hiệu năng và vận hành

### 13.1. JWKS cache và key rotation

Resource Server tải public keys từ JWKS và thường cache JWK Set. Điều này giảm outbound call tới issuer. Khi key rotation:

- Issuer nên publish key mới trước khi bắt đầu ký token bằng key mới.
- Giữ key cũ trong overlap window đủ cho access token cũ hết hạn.
- Resource Server cần có khả năng refresh khi gặp `kid` mới.
- Không chấp nhận token có `kid` chưa tìm thấy hoặc chữ ký không xác minh được.

Không xóa key cache hoặc bỏ signature validation để xử lý outage. Token đã cache key có thể tiếp tục được xác minh theo cache policy, nhưng token hết hạn vẫn phải bị từ chối.

### 13.2. Token lifetime và audience

Access token nên có lifetime phù hợp với độ nhạy dữ liệu và trải nghiệm client. Token lifetime quá dài làm tăng thời gian token bị lộ có thể được dùng. Token quá ngắn làm tăng tần suất client phải lấy token và phụ thuộc Authorization Server.

Audience phải xác định resource server cụ thể. Nếu một token được phép gọi nhiều API, cân nhắc tách audience/scope theo resource và không cấp quyền rộng hơn nhu cầu.

### 13.3. Query performance

API tra cứu có thể chịu tải lớn dù JWT validation rất nhanh. Theo dõi:

- Database query duration và slow query count.
- Page size, page depth và số lượng rows trả về.
- Query plan và index hit.
- Số lượng concurrent search.
- Cache hit ratio nếu có query cache.

Nếu dùng cache kết quả tìm kiếm, key cache phải bao gồm tenant và các tiêu chí authorization liên quan. Ví dụ, cache theo `q` mà bỏ `tenant_id` có thể trả kết quả của tenant A cho tenant B. Không cache kết quả có quyền khác nhau dưới cùng một cache key.

### 13.4. Rate limit và giới hạn truy vấn

JWT xác thực danh tính và scope, nhưng không tự giới hạn tốc độ gọi API. Với endpoint tìm kiếm:

- Giới hạn request rate theo client/user/tenant phù hợp.
- Giới hạn độ dài query và page size.
- Giới hạn sort fields và filter combinations.
- Cân nhắc rate limit riêng cho export/full-text query nặng.
- Có timeout cho database query và downstream calls.

Rate limit phải được thực hiện bằng gateway/filter phù hợp và không được xem là thay thế authorization.

### 13.5. Quan sát authentication và search

Các chỉ số hữu ích:

| Chỉ số | Dùng để |
| --- | --- |
| Authentication success/failure | Theo dõi token acceptance |
| 401 theo error category | Phát hiện signature/issuer/audience/expiry failures |
| 403 theo authority | Phát hiện thiếu scope hoặc policy mismatch |
| JWKS fetch/cache metrics | Theo dõi issuer key dependency |
| Search latency p50/p95/p99 | Đo hiệu năng API |
| Database query count/duration | Tìm bottleneck truy vấn |
| Page size distribution | Phát hiện truy vấn quá lớn |
| Tenant-scoped result count | Theo dõi workload mà không ghi dữ liệu nhạy cảm |

Không dùng JWT hoặc tenant/user ID làm metric label có cardinality cao. Không log raw token. Nếu audit cần subject/tenant, tuân theo chính sách bảo vệ dữ liệu và retention.

### 13.6. Readiness và liveness

Liveness nên kiểm tra process nội bộ, không gọi issuer/JWKS cho mỗi probe. Readiness cần phản ánh ứng dụng có thể nhận traffic theo contract. Một instance có JWKS cache hợp lệ có thể vẫn xác minh JWT khi JWKS endpoint tạm thời offline; instance mới chưa tải key có thể chưa xác minh được token.

Nếu dùng Actuator, chỉ expose health endpoints cần thiết và không công khai chi tiết nội bộ/secret. Dependency health có thể được hiển thị riêng với trạng thái ứng dụng.

## 14. Các quyết định thiết kế cho API tra cứu dữ liệu

### 14.1. Scope không thay thế quyền ở cấp bản ghi

`catalog.read` cho phép caller sử dụng chức năng đọc catalog. Nó không nhất thiết cho phép caller đọc mọi catalog item trong hệ thống. Tenant filter, ownership và visibility policy vẫn cần ở service/query.

Nếu một item có ACL riêng, ghép điều kiện ACL với tenant predicate trong cùng truy vấn hoặc kiểm tra policy ở domain service trước khi trả kết quả.

### 14.2. Phân biệt role và scope

Scope thường mô tả hành động API client được phép thực hiện; role có thể mô tả chức năng người dùng trong domain. Ví dụ:

| Claim/authority | Ý nghĩa |
| --- | --- |
| `SCOPE_catalog.read` | Cho phép gọi API đọc catalog |
| `SCOPE_catalog.export` | Cho phép dùng chức năng export nếu API có |
| `ROLE_CATALOG_ADMIN` | Vai trò quản trị catalog theo policy ứng dụng |

Không tự tạo `ROLE_ADMIN` từ một claim string tùy ý. Chỉ map role từ claim đã thống nhất với issuer và allowlist của ứng dụng.

### 14.3. Multi-issuer

Nếu API chỉ tin một issuer, cấu hình một issuer rõ ràng. Nếu phải hỗ trợ nhiều issuer, cần allowlist issuer, decoder/JWKS và claim mapping theo từng issuer. Không chọn JWKS URI dựa trên `iss` chưa xác minh hoặc chấp nhận mọi issuer có chữ ký hợp lệ.

Subject phải được hiểu trong namespace issuer. Khóa identity có thể cần cặp `(iss, sub)` thay vì chỉ `sub`.

### 14.4. Tenant claim và dữ liệu downstream

Tenant claim là context đã được issuer xác minh, nhưng không tự chứng minh mọi resource trong tenant đều được user đọc. Service vẫn phải kiểm tra business policy, trạng thái tài khoản và quyền trên từng loại dữ liệu.

Nếu dùng database row-level security, đặt tenant context an toàn trong transaction/session DB và bảo đảm connection pool không làm rò context giữa request. Luôn giữ predicate ở application/query layer như defense in depth.

### 14.5. Cache và tenant isolation

Nếu thêm `@Cacheable`, cache key phải chứa ít nhất tenant, query đã chuẩn hóa, category, page, size, sort/direction và policy version nếu policy thay đổi kết quả.

Không dùng cache key chỉ là `q`. Không chia sẻ cache entry giữa hai principal nếu response có thể khác theo quyền của principal.

## 15. Checklist hoàn thiện bài thực hành

### Issuer và JWT

- [ ] Issuer URI trỏ tới Authorization Server được tin cậy.
- [ ] Decoder xác minh chữ ký bằng public key từ JWKS.
- [ ] Chỉ chấp nhận thuật toán đã cấu hình.
- [ ] Kiểm tra issuer và timestamp mặc định.
- [ ] Kiểm tra audience dành cho `catalog-api`.
- [ ] Kiểm tra token profile/access token theo contract.
- [ ] Có test key rotation/unknown `kid` và token hết hạn.

### Authorization

- [ ] GET catalog yêu cầu `SCOPE_catalog.read`.
- [ ] Endpoint chưa khai báo bị từ chối.
- [ ] Scope được ánh xạ đúng prefix.
- [ ] Không nhầm ID token với access token.
- [ ] Phân biệt 401 và 403.

### Search và dữ liệu

- [ ] Query bắt buộc có độ dài giới hạn.
- [ ] Page size/page index có giới hạn.
- [ ] Sort field nằm trong allowlist.
- [ ] Truy vấn dùng parameter binding/Criteria API.
- [ ] Tenant lấy từ claim đã xác minh.
- [ ] Tenant predicate nằm trong database query.
- [ ] DTO chỉ trả field được phép.
- [ ] Cache key, nếu có, bao gồm tenant và policy context.

### Test và vận hành

- [ ] MockMvc test không token, thiếu scope và query không hợp lệ.
- [ ] Unit test audience/tenant validator.
- [ ] DataJpaTest chứng minh tenant isolation.
- [ ] Integration test dùng JWT ký thật qua decoder.
- [ ] Không dùng `jwt()` để kết luận signature/JWKS đã được kiểm tra.
- [ ] CORS allowlist đúng nếu có browser client.
- [ ] Timeout, metrics và log redaction được cấu hình.
- [ ] Liveness không tạo restart loop khi IdP offline.

---

## Kết luận

Để bảo vệ API tra cứu dữ liệu, cần kết hợp xác minh JWT ở Spring Security với authorization theo scope và kiểm soát truy vấn ở tầng dữ liệu. `JwtDecoder` xác minh chữ ký, issuer, timestamp và audience của access token từ issuer tin cậy; filter chain yêu cầu `SCOPE_catalog.read`; controller nhận principal đã xác minh; service/repository giới hạn tenant, lọc và phân trang bằng truy vấn có tham số.

Không dừng ở việc request có token hợp lệ. API phải bảo đảm token dành cho đúng audience, caller có scope phù hợp, tenant không thể bị sửa từ query parameter, sort/page không tạo truy vấn tùy ý và response chỉ chứa field được phép. Test nên tách authorization, decoder signature validation và tenant isolation để chứng minh từng ranh giới hoạt động đúng.

## Tài liệu tham khảo

1. [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
2. [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
3. [Spring Security — Testing OAuth 2.0 Resource Servers with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html)
4. [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
5. [Spring Data JPA — Specifications](https://docs.spring.io/spring-data/jpa/reference/jpa/specifications.html)
6. [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html)
7. [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519.html)
8. [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html)
