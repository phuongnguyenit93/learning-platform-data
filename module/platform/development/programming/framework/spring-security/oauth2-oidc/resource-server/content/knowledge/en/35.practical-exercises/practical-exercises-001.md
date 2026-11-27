# Securing a Data Lookup API with JWT from a Trusted Issuer

A data lookup API typically allows clients to filter, search, sort, and paginate results. When data is protected by OAuth 2.0, the API needs to verify the access token before running the query, and then check the corresponding scope and data access permissions.

Spring Security Resource Server supports this flow using JWT:

1. The client obtains an **access token** from a trusted Authorization Server/Identity Provider.
2. The client sends the token in the `Authorization: Bearer ...` header.
3. The Resource Server verifies the JWT signature using the public key published via JWKS.
4. The Resource Server checks the issuer, audience, expiration, and claims according to the contract.
5. Spring Security creates an `Authentication` and maps scopes to authorities.
6. The security filter chain checks authorities before the controller processes the request.
7. The service applies data-level authorization, executes parameterized queries, limits results, and returns safe DTOs.

In this practical exercise, we build a catalog lookup API at `GET /api/catalog`. The API only accepts access tokens from a trusted issuer, with an audience intended for `catalog-api` and the `catalog.read` scope. For multi-tenant data, the tenant is retrieved from a verified claim in the token and is always included in the query condition.

## 1. Architecture and Processing Flow

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

Each layer has one responsibility:

| Layer | Responsibility |
| --- | --- |
| Authorization Server | Authenticates the client/user and issues a signed access token |
| `JwtDecoder` | Verifies signature, issuer, timestamps, and custom validators |
| `SecurityFilterChain` | Blocks requests missing a token or missing authority |
| Controller | Receives query parameters, extracts the authenticated principal, and calls the service |
| Service | Applies lookup rules, tenant/resource authorization, pagination, and sorting |
| Repository | Builds parameterized queries to the database |
| Database | Stores data; never trusts a client-supplied tenant ID |

**Important condition:** the token must be an access token intended for the API. An ID token in OIDC proves the login event to the client; it does not replace an access token for calling a Resource Server.

## 2. Access Token Contract

Before writing code, agree on the token contract between the Authorization Server and the API.

Example of a signed JWT payload (claims shown for illustration only):

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

| Claim/header | Meaning | How the API uses it |
| --- | --- | --- |
| `iss` | Issuer that issued the token | Exact match against configured issuer |
| `sub` | Subject/identity of the caller | Principal name and audit attribution |
| `aud` | Resource/API receiving the token | Must contain `catalog-api` |
| `iat` | Issued-at timestamp | Can be used in additional policies |
| `nbf` | Time when the token becomes valid | Timestamp validation |
| `exp` | Expiration timestamp | Rejects expired tokens |
| `scope` | Granted OAuth permissions | Maps `catalog.read` to `SCOPE_catalog.read` |
| `tenant_id` | Tenant bound to the identity/token | Data scope when the API serves multiple tenants |
| JOSE `kid` | ID of the signing key | Selects the matching public key from JWKS |

### 2.1. Only Trust Claims After JWT Verification

A JWT payload can be read without a secret. Base64URL decoding does not prove a token is valid. Only use `sub`, `scope`, `tenant_id`, and other claims after `JwtDecoder` has:

- Verified the signature using the public key from a trusted JWKS URI.
- Accepted only the configured signing algorithms.
- Checked the issuer.
- Checked the expiration and related timestamps.
- Checked the audience intended for the API.

Do not take tenant, user ID, or roles from an arbitrary query parameter/header and use them in place of verified claims.

### 2.2. Access Token vs. ID Token

The two token types serve different purposes:

| Token | Intended recipient | Purpose |
| --- | --- | --- |
| ID token | OIDC client | User authentication information for the client |
| Access token | Resource Server/API | Grants permission to access resources |

Do not accept an ID token merely because it has a valid signature from the same issuer. Require the API's audience and, if supported by the Authorization Server, validate the token profile/type (`typ`, `token_use`, or claim per contract). Do not infer the access-token profile solely from the presence of the `sub` claim.

## 3. Project Setup and Dependencies

The examples use Java 21, Spring Boot 3.x, and Spring Security 6.x. The `SecurityFilterChain`, `oauth2ResourceServer().jwt()`, and `JwtDecoder` APIs are also the foundation in newer Spring Security versions; use dependency versions aligned with the Spring Boot version you are deploying.

Minimum Maven dependencies:

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

The Resource Server starter provides JWT/JWKS integration and OAuth2 bearer support. `spring-boot-starter-security` provides the filter chain, and `spring-security-test` supports testing authorization.

An easy-to-follow package structure:

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

## 4. Configuring Issuer and Audience

Place the issuer and audience in externalized configuration. Do not hardcode the issuer per environment or let the client send the JWKS URI.

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
          # jwk-set-uri can be configured directly if required by infrastructure.
          # issuer-uri must still be kept to validate the iss claim.
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

Environment example:

~~~text
OIDC_ISSUER_URI=https://identity.example.test/realms/shop
API_AUDIENCE=catalog-api
DB_URL=jdbc:postgresql://db.internal:5432/catalog
DB_USERNAME=catalog_api
DB_PASSWORD=<injected-secret>
~~~

`issuer-uri` must match the `iss` claim in the token and the issuer metadata exactly. A trailing slash, scheme, or path difference can make issuers mismatch.

### 4.1. Discovery Metadata and JWKS

Spring Security uses the issuer to discover metadata and locate the JWKS URI. The decoder fetches public keys from JWKS and can cache them. It does not need to fetch JWKS on every request if the matching key is already in the cache.

If you want to avoid discovery metadata solely for finding JWKS, you can configure `jwk-set-uri` directly alongside `issuer-uri`. In that case, issuer validation must still be kept. A direct URI does not skip signature verification, key selection, or claim validation.

### 4.2. Pre-Run Configuration Checklist

Verify that:

- The Issuer URI belongs to a managed, trusted IdP.
- The JWKS URI (if configured directly) is within the trust boundary.
- The audience is the API's identifier, not an arbitrary client ID.
- The TLS certificate chain is valid.
- The API does not take the issuer/JWKS URL from an unverified JWT or request parameter.
- Database secrets or client credentials are not committed to the repository.

## 5. Configuring Spring Security Resource Server

We need two parts: a decoder to validate the JWT and a filter chain to check authorities.

### 5.1. Properties for the Security Contract

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

The issuer is read from `spring.security.oauth2.resourceserver.jwt.issuer-uri`; the audience is read from `app.security.audience`.

### 5.2. Audience Validator

The default issuer validator does not replace audience validation. The API must verify that the token was issued for the intended resource:

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

### 5.3. JwtDecoder with Issuer, Timestamp, and Audience

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

`JwtValidators.createDefaultWithIssuer` preserves the default issuer and timestamp validation. `DelegatingOAuth2TokenValidator` composes validators together; do not replace the default validator with an audience validator alone.

The tenant validator in the example applies to multi-tenant APIs. If the API serves only a single tenant or obtains the tenant from another server-side source, adjust the contract rather than requiring an unnecessary claim:

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

If using direct `jwk-set-uri` configuration, create the decoder with `NimbusJwtDecoder.withJwkSetUri(jwksUri)` and attach the same issuer/time/audience validators. Do not drop issuer validation when switching from discovery to a direct URI.

### 5.4. SecurityFilterChain and Scope Authorization

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

Policy in the example:

- The health endpoint is permitted according to operational configuration.
- GET catalog requires `SCOPE_catalog.read`.
- POST catalog requires `SCOPE_catalog.write`.
- Undeclared routes are denied.
- No session is created to store authentication across requests.

Only disable CSRF when the API genuinely uses bearer tokens in the Authorization header and does not rely on browser cookies/sessions as credentials. If the application also has form login/cookie authentication, design CSRF protection separately instead of disabling it globally.

### 5.5. Mapping Scopes to Authorities

With the claim:

~~~json
{
  "scope": "catalog.read catalog.export"
}
~~~

Spring Security creates by default:

~~~text
SCOPE_catalog.read
SCOPE_catalog.export
~~~

Therefore `hasAuthority("SCOPE_catalog.read")` matches the `catalog.read` scope. Do not confuse scopes with roles. If the issuer issues roles in a `roles` claim, configure a dedicated converter and explicitly define an allowlist/prefix; do not automatically treat every string in `roles` as a valid permission.

### 5.6. Principal and Tenant Claim

`JwtAuthenticationToken` holds the verified JWT as its principal. In a controller, you can inject `@AuthenticationPrincipal Jwt jwt`:

~~~java
String subject = jwt.getSubject();
String tenantId = jwt.getClaimAsString("tenant_id");
~~~

`sub` identifies the subject within the scope of the issuer; if there are multiple issuers, do not assume two tokens with the same `sub` represent the same user. The tenant claim must only be used after the decoder has verified the issuer, signature, and token contract.

## 6. Catalog Data Model and Repository

The data model example includes tenant, visibility status, and fields allowed to be returned:

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

The entity includes `tenantId` so database queries restrict data right from the start. If the system only has a single tenant, this field can be replaced with the corresponding data structure; in a multi-tenant setup, never query the entire table and filter tenants in Java.

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

`JpaSpecificationExecutor` lets you compose search conditions and tenant filters into parameterized SQL queries. Never concatenate the client's query string directly into JPQL/SQL.

### 6.1. Search Specification

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

The tenant predicate is always added to the same query. The caller cannot remove this condition by passing another query parameter.

`escapeLike` treats `%` and `_` in the search string as literal characters, preventing users from accidentally turning the query into a broad wildcard. `CriteriaBuilder.like` uses the corresponding escape character. Across different databases/collations, verify the case-insensitive behavior and escape syntax of the DBMS in use.

### 6.2. Indexing Based on Actual Queries

Indexes should be chosen based on workload:

- `(tenant_id, active)` supports filtering by tenant and status.
- `(tenant_id, name)` can support name lookup/sorting.
- For substring search with `%term%`, a standard B-tree may not utilize the index effectively; consider full-text/trigram indexes depending on the database.
- When sorting by `created_at` or `price`, consider a composite index with a tenant prefix.

Do not blindly add indexes to every field. Measure query plans, selectivity, and write overhead.

## 7. Search Service: Tenant, Pagination, and Sorting

The service is where business limits are enforced. Do not let the controller construct SQL or let the repository accept arbitrary column names from the client.

### 7.1. Response DTOs

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

Do not serialize JPA entities directly. DTOs control which fields are exposed and prevent accidentally returning internal flags, tenant metadata, relationships, or sensitive data.

Paginated response:

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

### 7.2. Search Service

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

`SORT_FIELDS` is an allowlist mapping public sort names to entity properties. Do not pass `sort` directly from the URL into `Sort.by(...)`; doing so can expose internal fields or generate unintended queries.

### 7.3. Why Must the Tenant Be in the SQL Predicate?

Suppose Alice's token belongs to tenant A. The API must query:

~~~sql
SELECT id, name, category, price
FROM catalog_item
WHERE tenant_id = :tenantId
  AND active = true
  AND lower(name) LIKE :pattern
ORDER BY name ASC
LIMIT :limit OFFSET :offset;
~~~

The `:tenantId` value comes from the `tenant_id` claim in the verified JWT. It does not come from `?tenantId=tenant-B`.

If a query fetches all results and filters by tenant in Java, data from other tenants has already passed through the application layer and could leak via pagination counts, memory, logs, or mapping bugs. The tenant condition must be applied in the data query right from the start.

## 8. Controller and Query Parameter Validation

The controller receives the verified JWT via `@AuthenticationPrincipal`. The tenant is taken from the token; query parameters only determine the lookup conditions within that tenant.

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

Enforced constraints:

- Query `q` is required, 2–100 characters long.
- `category` is at most 60 characters.
- `page` starts at 0 and has an upper bound.
- `size` is at most 100 records.
- `sort` accepts only `name`, `price`, or `createdAt`.
- `direction` accepts only `asc` or `desc`.

`@Validated` enables method validation for constraints on controller parameters. The service still validates critical bounds to protect against calls coming from paths other than HTTP.

### 8.1. Why Not Accept the Tenant from a Query Parameter?

Do not create an endpoint like:

~~~http
GET /api/catalog?q=keyboard&tenantId=tenant-B
~~~

The caller could change `tenantId` to try reading another tenant's data. For a multi-tenant API, the tenant is determined from a verified claim:

~~~java
String tenantId = jwt.getClaimAsString("tenant_id");
~~~

If administrators need to look up across multiple tenants, that should be a separate use case with explicit scopes/roles and policies. Do not add a general tenant query parameter for all callers.

### 8.2. Handling Validation Errors

Malformed queries, out-of-range limits, or unsupported sorts should return `400 Bad Request`. You can use `@RestControllerAdvice` to standardize responses:

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

In applications using Spring Framework 6.1+, also check for `HandlerMethodValidationException` if controller method validation is handled through this exception. Do not return stack traces, SQL, or internal field details to the caller.

`@RestControllerAdvice` handles errors in the MVC layer. Authentication failures and access denied occur in the Spring Security filter chain and are handled by `AuthenticationEntryPoint`/`AccessDeniedHandler`; do not expect controller advice to catch them.

## 9. Calling the API and Reading the Response

The client sends the access token in the Authorization header:

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

Example successful response:

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

Common response statuses:

| Scenario | HTTP status | Meaning |
| --- | --- | --- |
| Valid token, sufficient scope, valid query | 200 | Returns a page of results; the list may be empty |
| No bearer token sent | 401 | Unauthenticated |
| Expired token/invalid signature/wrong issuer or audience | 401 | Invalid token |
| Valid token but missing `catalog.read` | 403 | Authenticated but insufficient permissions |
| Malformed query, out-of-range page/size, disallowed sort | 400 | Invalid request |
| Database/internal dependency error | 5xx | Server failed to process the request |

### 9.1. Empty Results Are Still 200

A valid search with no matching records typically returns `200 OK` with `items: []` and the corresponding pagination metadata. Do not return `404` for every empty search; `404` is more appropriate when the client requests a specific resource by ID and that resource does not exist or is not allowed to be visible.

### 9.2. Stable Pagination

The service adds `id` as a secondary sort so ordering remains stable when multiple records share the same name/price/timestamp. If you sort only by a non-unique field, records can shift positions across pages as data changes.

Offset pagination works well for moderate datasets. For very large tables or deep pages, `OFFSET` can be expensive and changing data can cause skipped or duplicated records across pages. In those cases, consider cursor/keyset pagination along a stable sort key, such as `(created_at, id)`.

## 10. Testing Security and Data Isolation

Do not lump everything into a single test. Each test should prove one boundary:

1. The decoder verifies the JWT and claims.
2. The filter chain requires the right scope.
3. The controller validates query parameters.
4. The service/repository restricts data by tenant.
5. The API does not return fields outside the DTO.

### 10.1. MockMvc Test for Scope Authorization

`spring-security-test` provides the `jwt()` request post-processor to create a mock JWT Authentication:

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

In `@WebMvcTest`, you need to mock `JwtDecoder` if the slice test initializes the Resource Server filter chain and there is no decoder bean in the context. The mock annotation name depends on the Spring Boot/Spring Framework version: newer versions may use `@MockitoBean`; `@MockBean` is used in many Boot 3.x projects.

`jwt()` creates an Authentication for authorization testing. It does **not** verify JWT signatures, call JWKS, or run the real decoder's audience/issuer validators. Therefore, do not use this test to conclude that the decoder is configured properly.

### 10.2. Audience Validator Unit Test

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

In the validator unit test, the `Jwt` object is a fixture input for claim logic; the `alg=none` header is not a token allowed to be sent to the API. A real decoder test must verify the JWS signature.

### 10.3. DataJpaTest for Tenant Isolation

Repository tests must prove that a query for tenant A does not return tenant B records:

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

This is a data boundary test. If you only mock the repository in a controller test, there is no proof that the SQL/Specification actually adds the tenant predicate.

### 10.4. Integration Test with Real Signed JWTs

To test signature, issuer, audience, and the filter chain together, generate a dedicated RSA key pair for testing:

1. A test encoder signs the JWT with the private key.
2. `JwtDecoder` verifies it with the corresponding public key or a test JWKS server.
3. The JWT contains valid issuer, audience, subject, scope, tenant, and timestamps.
4. Send the token via the `Authorization: Bearer ...` header using MockMvc.
5. Send tokens with an invalid signature, wrong audience, different issuer, and expired timestamp; all must be rejected.

Example local decoder configuration in tests:

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
        .withPublicKey((RSAPublicKey) testKeyPair.getPublic())
        .build();

decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuer),
        new AudienceValidator("catalog-api"),
        new RequiredTenantClaimValidator()));
~~~

The encoder can use `NimbusJwtEncoder` with an `ImmutableJWKSet` containing the test public/private JWK. In production, the decoder should fetch public keys from the trusted issuer's JWKS URI; the private key exists only in test fixtures or the Authorization Server.

### 10.5. Recommended Test Matrix

| Test case | JWT/Authentication | Query/data | Expected result |
| --- | --- | --- | --- |
| Missing token | None | Valid | 401 |
| Invalid signature | Invalid | Valid | 401 |
| Wrong issuer | Invalid | Valid | 401 |
| Audience for another API | Invalid | Valid | 401 |
| Expired token | Invalid | Valid | 401 |
| Missing `tenant_id` in multi-tenant profile | Invalid contract | Valid | 401 |
| Valid JWT, missing `catalog.read` | Authenticated | Valid | 403 |
| Valid JWT, sufficient scope | Authenticated | Valid query | 200 |
| Valid JWT, query too long | Authenticated | Invalid | 400 |
| Valid JWT, sort not in allowlist | Authenticated | Invalid | 400 |
| Tenant A JWT | Authenticated | Records for A and B exist | Returns only A |
| Valid JWT, no matching records | Authenticated | Valid | 200 with empty list |

## 11. Common Security Pitfalls

### 11.1. Decoding JWT Without Verifying Signature

Reading the payload via Base64URL and trusting `sub`, `scope`, or `tenant_id` lets callers forge claims. Use `JwtDecoder` and public keys from a trusted JWKS.

### 11.2. Skipping Audience Validation

A JWT from the same issuer may have been issued for another API. If you only check issuer/signature, a token intended for `billing-api` could be misused at `catalog-api`. Always check the audience per resource server.

### 11.3. Using an ID Token to Call an API

An ID token is for an OIDC client, not an access token for an API. Require an access token with the appropriate audience and scopes.

### 11.4. Checking Only `authenticated()` Without Scope

`.authenticated()` only states that the caller is authenticated. A catalog lookup API requires a specific authority such as `SCOPE_catalog.read`; otherwise, any valid token could read the data.

### 11.5. Trusting Client-Supplied Tenant

A `tenantId` query parameter or `X-Tenant-Id` header can be tampered with. Extract the tenant from a verified claim or server-side authorization context, then enforce it in the query.

### 11.6. Filtering Tenants After Loading Data

Filtering after the query can leak total counts, waste memory, and create data-leak paths. The tenant condition must be in the SQL/Specification before pagination.

### 11.7. Concatenating Query Strings into SQL

Do not do:

~~~java
String sql = "select * from catalog_item where name like '%"
        + q + "%'";
~~~

Use JPA Criteria/parameter binding. For sorting, use a field name allowlist; bind parameters cannot safely replace column identifiers.

### 11.8. Unbounded Pagination

`size=1000000` or an extremely large page index can cause expensive queries. Limit page size, query length, and sort fields, and consider cursor pagination.

### 11.9. Returning JPA Entities Directly

Entities can contain internal fields, relationships, or tenant metadata. Use DTO projections/response mapping to control exposed data.

### 11.10. Disabling CSRF for Cookie-Based APIs

Disabling CSRF is only appropriate for stateless APIs using bearer tokens in the Authorization header and not relying on cookies/sessions. If the browser automatically sends cookies, keep CSRF protection or split security filter chains appropriately.

### 11.11. Misconfiguring Issuer/JWKS

Do not take the issuer URL from the request, do not disable TLS validation, and do not fetch public keys from arbitrary sources. The JWKS URI must belong to operator-managed trust configuration.

### 11.12. Logging Tokens

Do not log raw JWTs, opaque tokens, Authorization headers, or introspection request bodies. Log subject/issuer per data policy, correlation IDs, and necessary error categories; redact credentials in the tracing layer.

## 12. CORS, Browser Clients, and API Documentation

CORS only governs which browser origins are allowed to send requests and read responses. CORS does not replace JWT authentication or scope authorization.

If the frontend runs on a separate origin, configure an explicit allowlist:

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

Enable CORS in the filter chain:

~~~java
return http
    .cors(Customizer.withDefaults())
    .csrf(csrf -> csrf.disable())
    // session management, authorization, and resource server...
    .build();
~~~

Set the exact frontend origin. Do not use a wildcard origin when credentials are enabled. This example does not use cookie credentials; the bearer token is sent explicitly in the Authorization header. If the application uses cookies, re-evaluate CSRF and CORS credentials.

If the API is only called server-to-server or has no browser frontend, CORS configuration may not be needed.

### 12.1. Describing Bearer Authentication in OpenAPI

API documentation should declare the HTTP bearer scheme with JWT format so clients know to send the Authorization header:

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

An OpenAPI security scheme only describes the contract for clients/tooling. It does not replace `SecurityFilterChain`, the decoder, or runtime authorization.

## 13. Performance and Operations

### 13.1. JWKS Caching and Key Rotation

The Resource Server fetches public keys from JWKS and typically caches the JWK Set. This reduces outbound calls to the issuer. During key rotation:

- The issuer should publish the new key before starting to sign tokens with it.
- Keep the old key during an overlap window long enough for old access tokens to expire.
- The Resource Server must be able to refresh when encountering a new `kid`.
- Do not accept tokens with an unfound `kid` or an unverifiable signature.

Do not clear the key cache or disable signature validation to handle an outage. Tokens whose keys are already cached can continue to be verified per cache policy, while expired tokens must still be rejected.

### 13.2. Token Lifetime and Audience

Access tokens should have a lifetime appropriate for data sensitivity and client experience. Overly long token lifetimes increase the window in which a leaked token can be used. Overly short lifetimes increase token acquisition frequency and Authorization Server dependency.

The audience must identify a specific resource server. If a token is permitted to call multiple APIs, consider splitting audiences/scopes per resource and never granting broader permissions than needed.

### 13.3. Query Performance

A lookup API can face heavy load even though JWT validation is very fast. Monitor:

- Database query duration and slow query count.
- Page size, page depth, and number of rows returned.
- Query plans and index hits.
- Concurrent search count.
- Cache hit ratio if using a query cache.

If caching search results, the cache key must include the tenant and relevant authorization criteria. For example, caching by `q` while omitting `tenant_id` could return tenant A's results to tenant B. Never cache results with different permissions under the same cache key.

### 13.4. Rate Limiting and Query Limits

JWT verifies identity and scope, but does not rate-limit API calls on its own. For search endpoints:

- Limit request rates per client/user/tenant appropriately.
- Limit query length and page size.
- Limit sort fields and filter combinations.
- Consider separate rate limits for heavy exports/full-text queries.
- Configure timeouts for database queries and downstream calls.

Rate limiting should be enforced by an appropriate gateway/filter and must not be treated as a replacement for authorization.

### 13.5. Authentication and Search Observability

Useful metrics:

| Metric | Used for |
| --- | --- |
| Authentication success/failure | Tracking token acceptance |
| 401 by error category | Detecting signature/issuer/audience/expiry failures |
| 403 by authority | Detecting missing scopes or policy mismatches |
| JWKS fetch/cache metrics | Monitoring issuer key dependency |
| Search latency p50/p95/p99 | Measuring API performance |
| Database query count/duration | Finding query bottlenecks |
| Page size distribution | Detecting overly large queries |
| Tenant-scoped result count | Tracking workload without logging sensitive data |

Do not use JWTs or tenant/user IDs as high-cardinality metric labels. Do not log raw tokens. If auditing requires subject/tenant, follow data protection and retention policies.

### 13.6. Readiness and Liveness

Liveness should check internal process health, not call the issuer/JWKS on every probe. Readiness should reflect whether the application can accept traffic according to its contract. An instance with a valid JWKS cache can still verify JWTs when the JWKS endpoint is temporarily offline; a fresh instance that has not loaded keys yet may not be able to verify tokens.

If using Actuator, expose only the necessary health endpoints and do not reveal internal details/secrets. Dependency health can be surfaced separately from application status.

## 14. Design Decisions for a Data Lookup API

### 14.1. Scope Does Not Replace Record-Level Permissions

`catalog.read` allows the caller to use the catalog read functionality. It does not necessarily allow the caller to read every catalog item in the system. Tenant filters, ownership, and visibility policies are still needed in the service/query.

If an item has its own ACL, combine the ACL condition with the tenant predicate in the same query or evaluate the policy in the domain service before returning results.

### 14.2. Distinguishing Roles and Scopes

Scopes typically describe actions an API client is allowed to perform; roles can describe a user's function within the domain. For example:

| Claim/authority | Meaning |
| --- | --- |
| `SCOPE_catalog.read` | Allows calling the catalog read API |
| `SCOPE_catalog.export` | Allows using export functionality if provided by the API |
| `ROLE_CATALOG_ADMIN` | Catalog administration role per application policy |

Do not fabricate `ROLE_ADMIN` from an arbitrary claim string. Only map roles from claims agreed upon with the issuer and the application's allowlist.

### 14.3. Multi-Issuer

If the API only trusts one issuer, configure a single explicit issuer. If multiple issuers must be supported, maintain an issuer allowlist, per-issuer decoders/JWKS, and per-issuer claim mappings. Do not choose a JWKS URI based on an unverified `iss` or accept any issuer with a valid signature.

Subjects must be interpreted within the issuer namespace. Identity keys may need the `(iss, sub)` pair rather than `sub` alone.

### 14.4. Tenant Claim and Downstream Data

The tenant claim is context verified by the issuer, but does not by itself prove every resource in the tenant is readable by the user. The service must still check business policies, account status, and permissions per data type.

If using database row-level security, set the tenant context safely within the DB transaction/session and ensure the connection pool does not leak context across requests. Always keep the predicate at the application/query layer as defense in depth.

### 14.5. Caching and Tenant Isolation

If adding `@Cacheable`, the cache key must include at least the tenant, normalized query, category, page, size, sort/direction, and policy version if policies alter results.

Do not use a cache key consisting only of `q`. Do not share cache entries between two principals if the response can differ based on principal permissions.

## 15. Practical Exercise Completion Checklist

### Issuer and JWT

- [ ] Issuer URI points to a trusted Authorization Server.
- [ ] Decoder verifies signatures using public keys from JWKS.
- [ ] Only configured algorithms are accepted.
- [ ] Default issuer and timestamp checks are enabled.
- [ ] Audience is validated for `catalog-api`.
- [ ] Token profile/access token is checked per contract.
- [ ] Tests cover key rotation/unknown `kid` and expired tokens.

### Authorization

- [ ] GET catalog requires `SCOPE_catalog.read`.
- [ ] Undeclared endpoints are denied.
- [ ] Scopes are mapped with the proper prefix.
- [ ] ID tokens are not confused with access tokens.
- [ ] 401 and 403 are properly distinguished.

### Search and Data

- [ ] Required query has a bounded length.
- [ ] Page size/page index are bounded.
- [ ] Sort fields are in an allowlist.
- [ ] Queries use parameter binding/Criteria API.
- [ ] Tenant is taken from a verified claim.
- [ ] Tenant predicate is included in the database query.
- [ ] DTOs return only allowed fields.
- [ ] Cache keys, if any, include tenant and policy context.

### Testing and Operations

- [ ] MockMvc tests cover missing token, missing scope, and invalid query.
- [ ] Unit tests cover audience/tenant validators.
- [ ] DataJpaTest proves tenant isolation.
- [ ] Integration tests pass real signed JWTs through the decoder.
- [ ] `jwt()` is not used to conclude signature/JWKS verification is working.
- [ ] CORS allowlist is accurate if there is a browser client.
- [ ] Timeouts, metrics, and log redaction are configured.
- [ ] Liveness does not cause restart loops when the IdP is offline.

---

## Conclusion

Securing a data lookup API requires combining JWT verification in Spring Security with scope-based authorization and query controls at the data layer. `JwtDecoder` verifies the signature, issuer, timestamps, and audience of access tokens from a trusted issuer; the filter chain requires `SCOPE_catalog.read`; the controller receives the verified principal; and the service/repository scopes by tenant, filters, and paginates using parameterized queries.

Do not stop at checking whether a request carries a valid token. The API must ensure the token is intended for the right audience, the caller has the appropriate scope, the tenant cannot be altered via query parameters, sorting/pagination cannot produce arbitrary queries, and responses contain only allowed fields. Tests should separate authorization, decoder signature validation, and tenant isolation to prove each boundary works properly.

## References

1. [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
2. [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
3. [Spring Security — Testing OAuth 2.0 Resource Servers with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html)
4. [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
5. [Spring Data JPA — Specifications](https://docs.spring.io/spring-data/jpa/reference/jpa/specifications.html)
6. [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html)
7. [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519.html)
8. [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html)
