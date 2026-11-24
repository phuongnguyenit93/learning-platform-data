# Bảo vệ endpoint bằng method security

> **Chương:** Dự án thực hành  
> **Module:** SECURITY_TOKEN_SECURITY_FUNDAMENTALS  
> **Bối cảnh:** Nắm mô hình tin cậy và vòng đời token bảo mật; phân biệt JWT, opaque token, access token và refresh token trong xác thực, phân quyền và OAuth 2.0/OIDC; phát hành, kiểm tra claims, scope, audience, lưu trữ, thu hồi và phòng chống token bị đánh cắp hoặc phát lại.

## Mục tiêu dự án

Xây dựng một **Orders API** bằng Java và Spring Boot, dùng OAuth 2.0 Resource Server để xác thực access token JWT và Spring Method Security để bảo vệ từng thao tác nghiệp vụ.

Khi hoàn thành, ứng dụng có hai endpoint:

- `GET /api/orders/{orderId}`: chỉ principal có scope `orders.read` và thuộc đúng tenant mới đọc được đơn hàng.
- `POST /api/orders/{orderId}/cancel`: chỉ principal có scope `orders.cancel` và thuộc đúng tenant mới hủy được đơn hàng.

Dự án cần chứng minh được các trường hợp:

- Không có token: trả `401 Unauthorized`.
- Token không hợp lệ, sai issuer hoặc audience: bị từ chối ở bước xác thực.
- Token hợp lệ nhưng thiếu scope: trả `403 Forbidden`.
- Token có scope nhưng tenant không sở hữu đơn hàng: trả `403 Forbidden`.
- Token có đúng scope và tenant: thao tác được thực hiện.
- Service được gọi qua Spring proxy để method security thực sự chạy.

Dự án dùng JWT để minh họa. Với opaque access token, có thể thay JWT decoder bằng introspection và giữ nguyên các quy tắc method authorization ở service layer.

## 1. Kiến trúc và luồng xử lý

~~~mermaid
flowchart TD
    C["Client gửi Bearer access token"] --> F["Spring Security Filter Chain"]
    F --> V["JWT Decoder<br/>signature + issuer + audience + time"]
    V -->|Hợp lệ| A["JwtAuthenticationToken<br/>subject + tenant + authorities"]
    V -->|Không hợp lệ| X["401 Unauthorized"]
    A --> E["Orders Controller"]
    E --> M["OrderService Spring proxy"]
    M --> P["@PreAuthorize"]
    P --> S["Scope check"]
    P --> T["Tenant/object policy"]
    S -->|Thiếu scope| D["403 Forbidden"]
    T -->|Sai tenant| D
    S -->|Đạt| T
    T -->|Đạt| R["Repository + business logic"]
    R --> O["HTTP response"]
~~~

Các lớp có trách nhiệm riêng:

| Thành phần | Trách nhiệm |
|---|---|
| Authorization Server | Xác thực user/client và phát hành access token |
| JWT decoder | Xác minh chữ ký, issuer, audience và thời hạn |
| SecurityContext | Giữ principal và authorities đã được xác minh |
| Controller | Nhận HTTP request và gọi service |
| Method security | Kiểm tra scope và policy trước khi chạy nghiệp vụ |
| OrderAccessPolicy | So khớp tenant trong token với tenant của đơn hàng |
| Repository | Đọc và cập nhật dữ liệu |
| Test suite | Chứng minh allow/deny ở cả HTTP và method layer |

Method security là lớp authorization ở service. Nó không thay thế JWT validation, tenant membership hoặc kiểm tra trạng thái nghiệp vụ.

## 2. Yêu cầu môi trường

- Java 17 trở lên.
- Maven 3.9 trở lên.
- Spring Boot 3.x.
- Một Authorization Server/OIDC Provider có thể phát hành JWT access token và công bố JWKS.
- Một IDE hỗ trợ Java, hoặc terminal có Maven.

Các ví dụ dùng Spring Boot 3.5.0 và Spring Security do Spring Boot quản lý phiên bản. Nếu repository của bạn đã có version catalog hoặc parent POM riêng, hãy dùng phiên bản Spring Boot/Security được dự án hỗ trợ và giữ nguyên cấu hình tương đương.

## 3. Khởi tạo project và dependency

Tạo project Maven với cấu trúc:

~~~text
token-method-security-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/orders/
    │   │   ├── OrdersApplication.java
    │   │   ├── config/
    │   │   │   ├── SecurityConfig.java
    │   │   │   └── RequiredAudienceValidator.java
    │   │   ├── order/
    │   │   │   ├── OrderEntity.java
    │   │   │   ├── OrderRepository.java
    │   │   │   ├── OrderResponse.java
    │   │   │   ├── OrderService.java
    │   │   │   └── OrderController.java
    │   │   └── security/
    │   │       └── OrderAccessPolicy.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/com/example/orders/
            ├── OrderEndpointSecurityTest.java
            └── RequiredAudienceValidatorTest.java
~~~

Tạo `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>token-method-security-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

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
            <artifactId>spring-boot-starter-data-jpa</artifactId>
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
~~~

Tạo application class:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

## 4. Cấu hình issuer, audience và JWKS

Tạo `src/main/resources/application.yml`:

~~~yaml
spring:
  datasource:
    url: jdbc:h2:mem:orders;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE
    username: sa
    password:
    driver-class-name: org.h2.Driver

  jpa:
    hibernate:
      ddl-auto: create-drop
    open-in-view: false

  h2:
    console:
      enabled: false

security:
  jwt:
    issuer: https://auth.example.test/realms/orders-lab
    audience: orders-api
    jwk-set-uri: https://auth.example.test/realms/orders-lab/protocol/openid-connect/certs
~~~

Ba giá trị issuer, audience và JWKS URI là cấu hình mẫu. Khi chạy với Authorization Server thật, thay chúng bằng issuer và JWKS URI đã đăng ký, được xác minh từ cấu hình tin cậy. Không lấy JWKS URI từ claim hoặc header do request gửi lên.

- `issuer`: giá trị `iss` mà API chấp nhận.
- `audience`: identifier của Orders API.
- `jwk-set-uri`: endpoint chứa public keys để xác minh chữ ký JWT.

Không đưa client secret hoặc private key vào file cấu hình đã commit. Lab này dùng resource server xác minh access token; private signing key thuộc Authorization Server.

## 5. Bật Spring Method Security và kiểm tra JWT

Tạo `RequiredAudienceValidator.java`:

~~~java
package com.example.orders.config;

import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

public final class RequiredAudienceValidator
        implements OAuth2TokenValidator<Jwt> {

    private final String requiredAudience;

    public RequiredAudienceValidator(String requiredAudience) {
        this.requiredAudience = requiredAudience;
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        if (jwt.getAudience().contains(requiredAudience)) {
            return OAuth2TokenValidatorResult.success();
        }

        OAuth2Error error = new OAuth2Error(
            "invalid_token",
            "Required audience is missing",
            null
        );

        return OAuth2TokenValidatorResult.failure(error);
    }
}
~~~

Validator này yêu cầu audience của token chứa `orders-api`. Nó không tự xác minh chữ ký hoặc issuer; những kiểm tra đó được kết hợp trong decoder.

Tạo `SecurityConfig.java`:

~~~java
package com.example.orders.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(resourceServer -> resourceServer
                .jwt(jwt -> {
                    // Authorities từ scope sẽ được ánh xạ theo mặc định
                    // thành SCOPE_<scope-name>.
                })
            );

        return http.build();
    }

    @Bean
    JwtDecoder jwtDecoder(Environment environment) {
        String jwkSetUri =
            environment.getRequiredProperty("security.jwt.jwk-set-uri");
        String issuer =
            environment.getRequiredProperty("security.jwt.issuer");
        String audience =
            environment.getRequiredProperty("security.jwt.audience");

        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(jwkSetUri).build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audienceValidator =
            new RequiredAudienceValidator(audience);

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime,
                audienceValidator
            )
        );

        return decoder;
    }
}
~~~

`@EnableMethodSecurity` bật các interceptor cho `@PreAuthorize`, `@PostAuthorize` và các annotation method security khác. `JwtValidators.createDefaultWithIssuer` kiểm tra issuer và các validator thời gian mặc định; `RequiredAudienceValidator` bổ sung kiểm tra audience.

Cấu hình `STATELESS` phù hợp với API dùng bearer access token và không dựa vào session cookie. Nếu ứng dụng dùng cookie authentication hoặc browser session, cần đánh giá CSRF theo kiến trúc thực tế trước khi tắt bảo vệ CSRF.

Trong cấu hình trên, scope claim được Spring Resource Server ánh xạ thành authority có prefix `SCOPE_`. Ví dụ `orders.read` trở thành `SCOPE_orders.read`.

## 6. Tạo dữ liệu đơn hàng

Tạo `OrderEntity.java`:

~~~java
package com.example.orders.order;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "orders")
public class OrderEntity {

    @Id
    private String id;

    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Column(nullable = false)
    private String status;

    protected OrderEntity() {
    }

    public OrderEntity(String id, String tenantId, String status) {
        this.id = id;
        this.tenantId = tenantId;
        this.status = status;
    }

    public String getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getStatus() {
        return status;
    }

    public void cancel() {
        this.status = "CANCELLED";
    }
}
~~~

Tạo `OrderRepository.java`:

~~~java
package com.example.orders.order;

import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository
        extends JpaRepository<OrderEntity, String> {
}
~~~

Tạo response DTO `OrderResponse.java`:

~~~java
package com.example.orders.order;

public record OrderResponse(
    String id,
    String tenantId,
    String status
) {
    public static OrderResponse from(OrderEntity order) {
        return new OrderResponse(
            order.getId(),
            order.getTenantId(),
            order.getStatus()
        );
    }
}
~~~

Trong ứng dụng thực tế, không nhất thiết trả tenant ID ra response. DTO ở đây giữ field để bài lab dễ quan sát dữ liệu test; có thể bỏ field này nếu API contract không cần công khai tenant.

## 7. Viết tenant access policy

Tạo `OrderAccessPolicy.java`:

~~~java
package com.example.orders.security;

import java.util.Optional;

import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Component;

import com.example.orders.order.OrderRepository;

@Component("orderAccess")
public class OrderAccessPolicy {

    private final OrderRepository repository;

    public OrderAccessPolicy(OrderRepository repository) {
        this.repository = repository;
    }

    public boolean canAccess(
            Authentication authentication,
            String orderId
    ) {
        Optional<String> tenantId = verifiedTenant(authentication);

        if (tenantId.isEmpty()) {
            return false;
        }

        return repository.findById(orderId)
            .map(order -> order.getTenantId().equals(tenantId.get()))
            .orElse(false);
    }

    private Optional<String> verifiedTenant(
            Authentication authentication
    ) {
        if (!(authentication instanceof JwtAuthenticationToken jwtAuth)) {
            return Optional.empty();
        }

        String tenantId =
            jwtAuth.getToken().getClaimAsString("tenant_id");

        if (tenantId == null || tenantId.isBlank()) {
            return Optional.empty();
        }

        return Optional.of(tenantId);
    }
}
~~~

Policy chỉ đọc `tenant_id` từ `JwtAuthenticationToken` do resource server tạo sau khi token được xác minh. Nó không tin `X-Tenant-Id`, query parameter hoặc tenant ID trong request body.

Trong hệ thống nhiều tenant thật, cần xác minh membership và trạng thái tenant theo policy. Nếu user có thể thuộc nhiều tenant, claim phải thể hiện tenant context đã được chọn hợp lệ hoặc service phải tra membership server-side. Khi không thể xác minh tenant, policy trả `false` để từ chối.

Ví dụ này truy vấn tenant của order để minh họa. Với dữ liệu lớn, có thể tối ưu bằng repository query có tenant predicate và transaction phù hợp, miễn tenant ID vẫn đến từ Authentication đã xác minh.

## 8. Bảo vệ nghiệp vụ tại OrderService

Tạo `OrderService.java`:

~~~java
package com.example.orders.order;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.parameters.P;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
@Transactional(readOnly = true)
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize(
        "hasAuthority('SCOPE_orders.read') " +
        "and @orderAccess.canAccess(authentication, #orderId)"
    )
    public OrderResponse getOrder(
            @P("orderId") String orderId
    ) {
        OrderEntity order = repository.findById(orderId)
            .orElseThrow(() -> new ResponseStatusException(
                HttpStatus.NOT_FOUND,
                "Order not found"
            ));

        return OrderResponse.from(order);
    }

    @PreAuthorize(
        "hasAuthority('SCOPE_orders.cancel') " +
        "and @orderAccess.canAccess(authentication, #orderId)"
    )
    @Transactional
    public OrderResponse cancelOrder(
            @P("orderId") String orderId
    ) {
        OrderEntity order = repository.findById(orderId)
            .orElseThrow(() -> new ResponseStatusException(
                HttpStatus.NOT_FOUND,
                "Order not found"
            ));

        order.cancel();
        return OrderResponse.from(repository.save(order));
    }
}
~~~

Hai phương thức có hai điều kiện độc lập:

- `hasAuthority(...)` kiểm tra scope của access token.
- `@orderAccess.canAccess(...)` kiểm tra tenant của principal với tenant của order.

`@P("orderId")` giúp SpEL nhận diện tên tham số method ổn định. Có thể dùng compiler option `-parameters` theo quy ước của dự án, nhưng cần bảo đảm parameter name được giữ trong bytecode.

Method security hoạt động khi lời gọi đi qua Spring proxy. Controller sẽ inject `OrderService` từ Spring context nên lời gọi đi qua proxy. Không tự tạo service bằng `new` hoặc gọi method được bảo vệ qua self-invocation trong cùng bean.

## 9. Tạo REST controller

Tạo `OrderController.java`:

~~~java
package com.example.orders.order;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{orderId}")
    public OrderResponse getOrder(
            @PathVariable String orderId
    ) {
        return orderService.getOrder(orderId);
    }

    @PostMapping("/{orderId}/cancel")
    public OrderResponse cancelOrder(
            @PathVariable String orderId
    ) {
        return orderService.cancelOrder(orderId);
    }
}
~~~

Controller không tự đọc scope hoặc tenant header. Nó chuyển request tới service đã được bảo vệ bằng method security. Cách này giúp các caller khác như message consumer hoặc service nội bộ có thể dùng cùng policy nếu cũng gọi bean qua proxy và cung cấp Authentication phù hợp.

## 10. Viết kiểm thử endpoint security

Dùng `MockMvc` và Spring Security Test để tạo JWT Authentication giả trong request. Tạo `OrderEndpointSecurityTest.java`:

~~~java
package com.example.orders;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import com.example.orders.order.OrderEntity;
import com.example.orders.order.OrderRepository;

@SpringBootTest
@AutoConfigureMockMvc
class OrderEndpointSecurityTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    OrderRepository repository;

    @BeforeEach
    void seedOrders() {
        repository.deleteAll();
        repository.save(
            new OrderEntity("order-a1", "tenant-a", "NEW")
        );
        repository.save(
            new OrderEntity("order-b1", "tenant-b", "NEW")
        );
    }

    @Test
    void requestWithoutTokenIsUnauthorized() throws Exception {
        mvc.perform(get("/api/orders/order-a1"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void tenantACanReadOwnOrderWithReadScope() throws Exception {
        mvc.perform(get("/api/orders/order-a1")
                .with(jwt()
                    .jwt(token -> token
                        .subject("alice")
                        .claim("tenant_id", "tenant-a"))
                    .authorities(
                        new SimpleGrantedAuthority("SCOPE_orders.read")
                    )))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value("order-a1"))
            .andExpect(jsonPath("$.status").value("NEW"));
    }

    @Test
    void missingScopeIsForbidden() throws Exception {
        mvc.perform(get("/api/orders/order-a1")
                .with(jwt()
                    .jwt(token -> token
                        .subject("alice")
                        .claim("tenant_id", "tenant-a"))
                    .authorities(
                        new SimpleGrantedAuthority("SCOPE_profile.read")
                    )))
            .andExpect(status().isForbidden());
    }

    @Test
    void tenantACannotReadTenantBOrder() throws Exception {
        mvc.perform(get("/api/orders/order-b1")
                .with(jwt()
                    .jwt(token -> token
                        .subject("alice")
                        .claim("tenant_id", "tenant-a"))
                    .authorities(
                        new SimpleGrantedAuthority("SCOPE_orders.read")
                    )))
            .andExpect(status().isForbidden());
    }

    @Test
    void tenantACanCancelOwnOrderWithCancelScope() throws Exception {
        mvc.perform(post("/api/orders/order-a1/cancel")
                .with(jwt()
                    .jwt(token -> token
                        .subject("alice")
                        .claim("tenant_id", "tenant-a"))
                    .authorities(
                        new SimpleGrantedAuthority("SCOPE_orders.cancel")
                    )))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("CANCELLED"));
    }

    @Test
    void readScopeCannotCancelOrder() throws Exception {
        mvc.perform(post("/api/orders/order-a1/cancel")
                .with(jwt()
                    .jwt(token -> token
                        .subject("alice")
                        .claim("tenant_id", "tenant-a"))
                    .authorities(
                        new SimpleGrantedAuthority("SCOPE_orders.read")
                    )))
            .andExpect(status().isForbidden());
    }

    @Test
    void missingTenantClaimIsDenied() throws Exception {
        mvc.perform(get("/api/orders/order-a1")
                .with(jwt()
                    .jwt(token -> token.subject("alice"))
                    .authorities(
                        new SimpleGrantedAuthority("SCOPE_orders.read")
                    )))
            .andExpect(status().isForbidden());
    }
}
~~~

Các test trên xác nhận filter chain, controller và method security phối hợp đúng với Authentication được dựng cho test. Chúng không xác minh chữ ký JWT thật vì `jwt()` tạo Authentication giả và bỏ qua decoder/JWKS.

## 11. Kiểm thử audience validator

Tạo `RequiredAudienceValidatorTest.java`:

~~~java
package com.example.orders;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;

import com.example.orders.config.RequiredAudienceValidator;

class RequiredAudienceValidatorTest {

    private final RequiredAudienceValidator validator =
        new RequiredAudienceValidator("orders-api");

    private Jwt tokenWithAudience(List<String> audiences) {
        Instant now = Instant.now();

        return Jwt.withTokenValue("test-token")
            .header("alg", "RS256")
            .issuer("https://auth.example.test/realms/orders-lab")
            .subject("alice")
            .audience(audiences)
            .issuedAt(now)
            .expiresAt(now.plusSeconds(300))
            .build();
    }

    @Test
    void acceptsOrdersApiAudience() {
        var result = validator.validate(
            tokenWithAudience(List.of("orders-api"))
        );

        assertTrue(result.getErrors().isEmpty());
    }

    @Test
    void rejectsDifferentAudience() {
        var result = validator.validate(
            tokenWithAudience(List.of("inventory-api"))
        );

        assertFalse(result.getErrors().isEmpty());
    }

    @Test
    void acceptsOrdersApiInAudienceArray() {
        var result = validator.validate(
            tokenWithAudience(
                List.of("orders-api", "reporting-api")
            )
        );

        assertTrue(result.getErrors().isEmpty());
    }
}
~~~

Unit test này kiểm tra riêng audience validator. Để kiểm tra issuer, chữ ký và thời hạn, cần test decoder với JWT được ký bằng test key hoặc một Authorization Server test. Không dùng `jwt()` postprocessor để kết luận decoder đã xác minh token thật.

## 12. Chạy project và gọi API

Chạy test:

~~~bash
mvn test
~~~

Chạy ứng dụng:

~~~bash
mvn spring-boot:run
~~~

Để gọi API thật, cần có Authorization Server phù hợp với `issuer`, `audience` và JWKS URI trong cấu hình. Tạo access token có các claim tương đương:

~~~json
{
  "iss": "https://auth.example.test/realms/orders-lab",
  "sub": "alice",
  "aud": ["orders-api"],
  "scope": "orders.read orders.cancel",
  "tenant_id": "tenant-a",
  "exp": 1893456000
}
~~~

Đây là payload minh họa, không phải token có thể sử dụng. Token thật phải được Authorization Server ký và resource server xác minh.

Gọi endpoint bằng access token thật:

~~~bash
curl -i \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  http://localhost:8080/api/orders/order-a1
~~~

Hủy đơn hàng:

~~~bash
curl -i -X POST \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  http://localhost:8080/api/orders/order-a1/cancel
~~~

Không đưa token thật vào source code, shell history, ticket hoặc log chia sẻ. Nếu dùng terminal tương tác, hãy lấy token từ secret manager hoặc công cụ đăng nhập an toàn.

## 13. Bảng kết quả mong đợi

| Request | Token scope | Tenant claim | Order tenant | Kết quả |
|---|---|---|---|---|
| GET order-a1 | orders.read | tenant-a | tenant-a | 200 |
| GET order-b1 | orders.read | tenant-a | tenant-b | 403 |
| GET order-a1 | profile.read | tenant-a | tenant-a | 403 |
| GET order-a1 | orders.read | thiếu | tenant-a | 403 |
| POST cancel order-a1 | orders.cancel | tenant-a | tenant-a | 200 |
| POST cancel order-a1 | orders.read | tenant-a | tenant-a | 403 |
| GET order-a1 | Không có token | — | tenant-a | 401 |
| GET order-a1 | JWT sai issuer/audience/chữ ký | tenant-a | tenant-a | 401 |

Ở lab này, request sai tenant trả 403. API khác có thể chọn 404 để hạn chế tiết lộ resource có tồn tại; nếu chọn cách đó, hãy giữ hành vi nhất quán cho resource ngoài tenant và resource không tồn tại.

## 14. Những lỗi cần chủ động thử

### Chỉ bảo vệ controller

Nếu chỉ thêm kiểm tra ở controller, một message consumer hoặc service khác có thể gọi trực tiếp service và bỏ qua kiểm soát. Đặt `@PreAuthorize` ở service method giúp mọi lời gọi đi qua Spring proxy chịu cùng policy.

### Tự tạo service bằng new

Nếu test khởi tạo `new OrderService(repository)`, method security interceptor không chạy. Test phải inject Spring-managed bean hoặc đi qua HTTP endpoint như project này.

### Self-invocation

Một method trong cùng bean gọi `this.otherProtectedMethod()` có thể không đi qua proxy. Chuyển method được bảo vệ sang bean riêng hoặc tổ chức lời gọi qua Spring proxy.

### Tin tenant header

Thử gửi `X-Tenant-Id: tenant-b` trong khi JWT mang `tenant_id=tenant-a`. Policy của lab không đọc header nên request vẫn chỉ được đánh giá theo tenant claim đã xác minh.

### Bỏ audience validator

Tạm bỏ `RequiredAudienceValidator`, sau đó gửi token có issuer và chữ ký hợp lệ nhưng audience dành cho API khác. Test decoder phải phát hiện lỗi cấu hình này. Không để thay đổi thử nghiệm được đưa vào production.

### Nhầm role và scope

`SCOPE_orders.read` là authority được ánh xạ từ scope. `ROLE_ORDER_MANAGER` là authority theo convention role. Không dùng `hasRole('SCOPE_orders.read')` hoặc tự thêm `ROLE_` vào scope.

### Dùng ID token thay access token

ID token thường có audience là OIDC client. Orders API phải từ chối token không có audience `orders-api` và chỉ chấp nhận access token theo profile đã cấu hình.

## 15. Mở rộng dự án

Sau khi các test cơ bản chạy thành công, có thể mở rộng theo các hướng:

1. **Role claim:** thêm `roles: ["ORDER_MANAGER"]`, viết converter ánh xạ thành `ROLE_ORDER_MANAGER` và yêu cầu cả scope lẫn role cho thao tác hủy.
2. **Membership lookup:** kiểm tra user còn thuộc tenant trong database hoặc policy service thay vì chỉ dựa vào tenant claim snapshot.
3. **Opaque token:** thay JWT decoder bằng `OpaqueTokenIntrospector`, kiểm tra `active`, issuer, audience và scope từ introspection response.
4. **Token revocation:** thêm test khi access token hoặc session bị thu hồi; xác định cache TTL và SLA propagation.
5. **Token exchange:** để Orders Service lấy token mới dành cho Inventory API với audience `inventory-api` và scope `inventory.read`.
6. **Audit:** ghi event allow/deny với subject reference được pseudonymize; không ghi raw token hoặc Authorization header.
7. **Database isolation:** bổ sung tenant predicate hoặc PostgreSQL Row-Level Security để có lớp bảo vệ dữ liệu ở database.
8. **Concurrency:** chạy request tenant A và tenant B đồng thời để phát hiện rò rỉ SecurityContext hoặc tenant context.

Khi thêm role claim, hãy giữ semantics tách biệt: scope xác định capability của API; role thể hiện trách nhiệm nghiệp vụ; tenant và object policy xác định phạm vi dữ liệu.

## 16. Tiêu chí hoàn thành

- [ ] Ứng dụng khởi động và cấu hình Resource Server.
- [ ] JWT decoder xác minh chữ ký, issuer, audience và thời gian.
- [ ] `@EnableMethodSecurity` được bật.
- [ ] `GET` yêu cầu `SCOPE_orders.read`.
- [ ] `POST cancel` yêu cầu `SCOPE_orders.cancel`.
- [ ] Tenant policy đọc tenant từ Authentication đã xác minh.
- [ ] Tenant A không đọc hoặc hủy order thuộc tenant B.
- [ ] Test không token trả 401.
- [ ] Test thiếu scope hoặc sai tenant trả 403.
- [ ] Test hợp lệ trả dữ liệu hoặc cập nhật trạng thái đúng.
- [ ] Test ghi rõ `jwt()` postprocessor bỏ qua chữ ký/JWKS validation.
- [ ] Không log raw access token, refresh token hoặc secret.

## 17. Tổng kết

Dự án đã kết hợp xác thực JWT ở Spring Security Resource Server với authorization ở service layer bằng `@PreAuthorize`. JWT decoder kiểm tra chữ ký, issuer, audience và thời hạn; Spring ánh xạ scope thành authority; `OrderAccessPolicy` kiểm tra tenant; `OrderService` thực thi nghiệp vụ sau khi mọi điều kiện được đáp ứng.

Điểm quan trọng là method security phải chạy qua Spring proxy và kiểm tra quyền trên tài nguyên cụ thể. Một token có chữ ký hợp lệ hoặc có scope phù hợp vẫn không được đọc dữ liệu của tenant khác. Bộ test cần phân biệt rõ kiểm thử method authorization bằng JWT giả với kiểm thử decoder bằng JWT ký thật.

**Kết quả cần đạt:** endpoint chỉ thực hiện nghiệp vụ khi access token đến từ issuer tin cậy, dành cho đúng audience, còn hiệu lực, có scope cần thiết và principal được phép thao tác trên đúng tenant/resource.
