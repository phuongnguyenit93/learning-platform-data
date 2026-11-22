# Tách authorization service và consent service theo tenant

## 1. Bối cảnh và mục tiêu

Trong chương **Đa tenant** của module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, bài học này hướng dẫn tách dữ liệu OAuth authorization và quyết định consent theo từng tenant khi triển khai Spring Authorization Server trên một host hoặc một cụm dịch vụ dùng chung.

Module này học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot. Với hệ thống multi-tenant, cùng một ứng dụng có thể phục vụ nhiều tổ chức, mỗi tổ chức có issuer, client, người dùng, token và chính sách consent riêng.

Giả sử nền tảng có hai khách hàng:

- Tenant A dùng issuer `https://login.example.com/tenant-a`.
- Tenant B dùng issuer `https://login.example.com/tenant-b`.
- Cả hai có client tên `billing-portal` và principal `alice`.
- Tenant A cấp scope `invoice.read`; Tenant B cấp scope `payment.approve`.

Nếu hai tenant cùng ghi vào một kho authorization/consent mà truy vấn không gắn tenant, hệ thống có thể trả nhầm authorization, chấp nhận consent của tenant khác hoặc revoke nhầm token. Việc client_id hoặc username trùng nhau không phải điều bất thường; điều bắt buộc là dữ liệu của hai tenant phải có ranh giới lưu trữ và truy vấn rõ ràng.

Sau bài này, bạn có thể:

1. Phân biệt `OAuth2AuthorizationService` với `OAuth2AuthorizationConsentService`.
2. Chọn tenant dựa trên issuer đã được Authorization Server xác định.
3. Dùng `AuthorizationServerContextHolder` để định tuyến service theo issuer.
4. Tạo component registry và delegating service cho từng tenant.
5. Cấu hình `JdbcOAuth2AuthorizationService` và `JdbcOAuth2AuthorizationConsentService` với dữ liệu riêng.
6. Bảo đảm `RegisteredClientRepository` được định tuyến cùng tenant.
7. Chọn mô hình database-per-tenant, schema-per-tenant hoặc shared-table.
8. Kiểm thử truy cập chéo tenant, token lookup, consent lookup, revocation và xử lý song song.

## 2. Phân biệt authorization và consent

Hai service có liên quan trong authorization flow nhưng lưu hai loại trạng thái khác nhau.

### 2.1. OAuth2AuthorizationService

`OAuth2AuthorizationService` là nơi lưu và truy vấn một OAuth authorization đã được tạo. Một `OAuth2Authorization` có thể chứa:

- ID nội bộ của authorization.
- ID của RegisteredClient.
- Principal name của resource owner hoặc client.
- Authorization grant type.
- Các scope đã được chấp thuận trong authorization đó.
- Authorization Code, Access Token, Refresh Token, ID Token và metadata tương ứng tùy grant.
- Attributes của authorization request và principal.

Service này được dùng trong nhiều protocol flow như xử lý authorization grant, client authentication, introspection, token revocation và các thao tác liên quan.

Ví dụ: Alice hoàn tất Authorization Code Flow cho client Billing Portal. Authorization Server lưu authorization cùng Access Token và có thể cả Refresh Token. Khi client đổi Refresh Token, introspection hoặc revoke token, server tra cứu trạng thái này qua `OAuth2AuthorizationService`.

### 2.2. OAuth2AuthorizationConsentService

`OAuth2AuthorizationConsentService` quản lý quyết định consent của resource owner dành cho một RegisteredClient. Một `OAuth2AuthorizationConsent` gồm:

- `registeredClientId`: ID nội bộ của client đã đăng ký.
- `principalName`: principal của người dùng.
- `authorities`: tập quyền mà người dùng đã đồng ý, thường biểu diễn scope, claim hoặc permission.

Consent trả lời câu hỏi: **người dùng đã cho client này quyền gì?** Nó không phải token và không chứa trạng thái hoạt động/hết hạn của Access Token.

Ví dụ: Alice đồng ý cho Billing Portal đọc hóa đơn. Consent có thể lưu authority `SCOPE_invoice.read`. Ở lần đăng nhập sau, Authorization Server dùng consent để xác định có cần hiển thị lại màn hình đồng ý hay không.

### 2.3. Bảng so sánh

| Khía cạnh | OAuth2AuthorizationService | OAuth2AuthorizationConsentService |
| --- | --- | --- |
| Đối tượng | Một lần cấp quyền/authorization | Quyết định consent của user đối với client |
| Dữ liệu chính | Grant, token, principal, scope đã cấp, attributes | Registered client, principal, authorities đã đồng ý |
| Dùng ở đâu | Authorization grant, token, introspection, revocation | Authorization request và consent page |
| Khóa tra cứu điển hình | ID hoặc token | registeredClientId + principalName |
| Có chứa token không? | Có thể chứa token và metadata token | Không |
| Vòng đời | Theo grant/token và policy revoke/expire | Theo quyết định consent, có thể tồn tại qua nhiều lần cấp token |
| Tách tenant | Phải truy vấn authorization trong đúng issuer | Phải truy vấn consent trong đúng issuer |

Không dùng consent làm bằng chứng rằng Access Token vẫn active. Cũng không xóa consent chỉ vì một Access Token hết hạn.

## 3. Vì sao phải tách hai service theo tenant?

Trong Spring Authorization Server, các service này mặc định không có tham số `tenantId` trong các method interface. Ví dụ:

~~~java
public interface OAuth2AuthorizationService {
    void save(OAuth2Authorization authorization);
    void remove(OAuth2Authorization authorization);
    OAuth2Authorization findById(String id);
    OAuth2Authorization findByToken(String token, OAuth2TokenType tokenType);
}

public interface OAuth2AuthorizationConsentService {
    void save(OAuth2AuthorizationConsent authorizationConsent);
    void remove(OAuth2AuthorizationConsent authorizationConsent);
    OAuth2AuthorizationConsent findById(
            String registeredClientId, String principalName);
}
~~~

Nếu chỉ tạo một bean JDBC toàn cục, các thao tác có thể đọc/ghi vào cùng một kho. Khi client ID, principal name hoặc token identifier không mang tenant namespace, việc tra cứu có nguy cơ trả dữ liệu thuộc tổ chức khác.

Một composite service giải quyết vấn đề này bằng cách:

1. Xác định issuer của request hiện tại.
2. Tìm implementation service được đăng ký cho issuer đó.
3. Chuyển tiếp method tới implementation tương ứng.
4. Từ chối request nếu không có issuer hoặc issuer chưa được đăng ký.

~~~mermaid
flowchart TD
    R["HTTP request tới Authorization Server"] --> I["Xác định issuer đã được tin cậy"]
    I --> C["AuthorizationServerContextHolder"]
    C --> D{"Chọn service theo issuer"}
    D -->|Tenant A| A["AuthorizationService A"]
    D -->|Tenant A| AC["ConsentService A"]
    D -->|Tenant B| B["AuthorizationService B"]
    D -->|Tenant B| BC["ConsentService B"]
    A --> DA["Database / schema A"]
    AC --> DA
    B --> DB["Database / schema B"]
    BC --> DB
    D -->|Không có hoặc không hợp lệ| X["Fail closed"]
~~~

Authorization và consent phải cùng được định tuyến theo tenant. Nếu authorization được ghi vào database A nhưng consent lại đọc từ database B, luồng đăng nhập có thể trả kết quả sai hoặc thất bại.

## 4. Xác định tenant từ issuer

Spring Authorization Server hỗ trợ nhiều issuer trên cùng một host bằng cách dùng path component trong issuer identifier. Ví dụ:

| Tenant | Issuer | Metadata OIDC |
| --- | --- | --- |
| A | `https://login.example.com/tenant-a` | `https://login.example.com/tenant-a/.well-known/openid-configuration` |
| B | `https://login.example.com/tenant-b` | `https://login.example.com/tenant-b/.well-known/openid-configuration` |

Các endpoint protocol của mỗi tenant được xây dựng từ issuer tương ứng, chẳng hạn authorization endpoint, token endpoint, JWKS URI, revocation endpoint và introspection endpoint.

### 4.1. Bật multiple issuers

Hỗ trợ nhiều issuer trên cùng host bị tắt mặc định. Có thể bật bằng `AuthorizationServerSettings`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;

@Configuration(proxyBeanMethods = false)
class AuthorizationServerSettingsConfiguration {

    @Bean
    AuthorizationServerSettings authorizationServerSettings() {
        return AuthorizationServerSettings.builder()
                .multipleIssuersAllowed(true)
                .build();
    }
}
~~~

Trong cấu hình multi-issuer, không đặt issuer cố định bằng `issuer("https://login.example.com")` vì cấu hình đó ép server về một issuer cụ thể. Issuer phải được phân giải theo request và tenant đã được đăng ký.

### 4.2. AuthorizationServerContextHolder

Trong quá trình xử lý request, `AuthorizationServerContextHolder` cung cấp `AuthorizationServerContext` hiện tại. Context này có issuer mà Authorization Server đã xác định:

~~~java
AuthorizationServerContext context =
        AuthorizationServerContextHolder.getContext();

String issuer = context != null ? context.getIssuer() : null;
~~~

Issuer này là khóa định tuyến cho composite service. Service không cần nhận tenant từ một tham số tùy ý của caller; nó lấy issuer từ context protocol hiện tại.

### 4.3. Không tin tenant selector từ request

Không coi các giá trị sau là bằng chứng người gọi thuộc tenant:

- Header `X-Tenant-ID` do client tự gửi.
- Query parameter `tenant`.
- Cookie tenant chưa được xác minh.
- Host header tùy ý khi proxy/ingress chưa được cấu hình tin cậy.
- Một đoạn path chỉ được so khớp bằng `contains` hoặc `endsWith`.

Tenant cần được xác định từ issuer/host/path đã được cấu hình và kiểm soát. Nếu dùng forwarded headers, chỉ tin header do reverse proxy tin cậy ghi đè. Không để client bên ngoài tự giả mạo `X-Forwarded-Host` hoặc `X-Forwarded-Prefix`.

### 4.4. So khớp issuer chính xác

Ví dụ chính thức minh họa registry theo issuer và có thể kiểm tra suffix tenant. Trong hệ thống có tenant name gần nhau như `tenant-a` và `a`, suffix matching dễ gây mơ hồ. Bài này dùng full issuer URI làm key và tra cứu chính xác:

`https://login.example.com/tenant-a` chỉ ánh xạ tới đúng entry đó.

Không chuẩn hóa URI theo cách làm thay đổi issuer. Scheme, host, port và path phải nhất quán với issuer đã công bố trong discovery và token `iss` claim.

## 5. Thiết kế TenantPerIssuerComponentRegistry

Registry quản lý implementation cụ thể theo issuer. Mỗi issuer có thể đăng ký nhiều component type, ví dụ RegisteredClientRepository, OAuth2AuthorizationService và OAuth2AuthorizationConsentService.

~~~java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.security.oauth2.server.authorization.context.AuthorizationServerContext;
import org.springframework.security.oauth2.server.authorization.context.AuthorizationServerContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.util.Assert;
import org.springframework.util.StringUtils;

@Component
public final class TenantPerIssuerComponentRegistry {

    private final ConcurrentMap<String, ConcurrentMap<Class<?>, Object>> registry =
            new ConcurrentHashMap<>();

    public <T> void register(String issuer, Class<T> componentType, T component) {
        Assert.hasText(issuer, "issuer cannot be empty");
        Assert.notNull(componentType, "componentType cannot be null");
        Assert.notNull(component, "component cannot be null");

        ConcurrentMap<Class<?>, Object> components =
                this.registry.computeIfAbsent(issuer, key -> new ConcurrentHashMap<>());

        Object previous = components.putIfAbsent(componentType, component);
        Assert.state(previous == null,
                () -> "Component already registered for issuer " + issuer
                        + " and type " + componentType.getName());
    }

    public <T> T getRequired(Class<T> componentType) {
        AuthorizationServerContext context =
                AuthorizationServerContextHolder.getContext();

        Assert.state(context != null && StringUtils.hasText(context.getIssuer()),
                "AuthorizationServerContext with issuer is required");

        Map<Class<?>, Object> components = this.registry.get(context.getIssuer());
        Assert.state(components != null,
                () -> "Unknown issuer: " + context.getIssuer());

        Object component = components.get(componentType);
        Assert.state(component != null,
                () -> "Component " + componentType.getName()
                        + " is not registered for issuer " + context.getIssuer());

        return componentType.cast(component);
    }
}
~~~

Registry này có ba đặc điểm:

1. Key là issuer đầy đủ, không phải tenant label do caller gửi.
2. Mỗi loại component có một implementation riêng cho từng issuer.
3. Thiếu context, issuer hoặc component đều gây lỗi; không fallback sang tenant mặc định.

`putIfAbsent` ngăn cấu hình bị ghi đè âm thầm. Khi cần cập nhật tenant, thực hiện quy trình quản trị có kiểm soát, không thay bean đang phục vụ request một cách tùy tiện.

### 5.1. Khai báo issuer constants

~~~java
final class TenantIssuers {
    static final String TENANT_A = "https://login.example.com/tenant-a";
    static final String TENANT_B = "https://login.example.com/tenant-b";

    private TenantIssuers() {
    }
}
~~~

Issuer constants cần trùng với giá trị public issuer mà discovery và token phát ra. Trong môi trường thật, có thể nạp danh sách issuer từ tenant catalog đã được quản trị; validate uniqueness trước khi đăng ký component.

## 6. Tạo delegating OAuth2AuthorizationService

Delegating service chỉ làm nhiệm vụ chọn implementation đúng tenant. Nó không tự truy cập database và không thay đổi semantics của OAuth2Authorization.

~~~java
import org.springframework.security.oauth2.server.authorization.OAuth2Authorization;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.OAuth2TokenType;

public final class TenantAwareOAuth2AuthorizationService
        implements OAuth2AuthorizationService {

    private final TenantPerIssuerComponentRegistry componentRegistry;

    public TenantAwareOAuth2AuthorizationService(
            TenantPerIssuerComponentRegistry componentRegistry) {
        this.componentRegistry = componentRegistry;
    }

    private OAuth2AuthorizationService delegate() {
        return this.componentRegistry.getRequired(OAuth2AuthorizationService.class);
    }

    @Override
    public void save(OAuth2Authorization authorization) {
        delegate().save(authorization);
    }

    @Override
    public void remove(OAuth2Authorization authorization) {
        delegate().remove(authorization);
    }

    @Override
    public OAuth2Authorization findById(String id) {
        return delegate().findById(id);
    }

    @Override
    public OAuth2Authorization findByToken(String token, OAuth2TokenType tokenType) {
        return delegate().findByToken(token, tokenType);
    }
}
~~~

Mọi method đều gọi `delegate()` trong context hiện tại. Đặc biệt, `findByToken` phải truy vấn kho của issuer hiện tại; không tìm lần lượt qua tất cả tenant vì cách đó vừa làm lộ sự tồn tại token vừa tạo đường truy cập chéo tenant.

### 6.1. Tại sao findByToken cần tenant isolation?

Các endpoint introspection, revocation và grant processing có thể tìm authorization bằng token. Nếu một token thuộc Tenant A được gửi tới issuer Tenant B, service của B phải không tìm thấy token đó. Không được thử database A như fallback.

Kết quả đúng khi token thuộc tenant khác là không có authorization trong tenant hiện tại; endpoint trả protocol response tương ứng theo loại endpoint.

## 7. Tạo delegating OAuth2AuthorizationConsentService

Consent service cũng định tuyến theo issuer hiện tại:

~~~java
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationConsent;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationConsentService;

public final class TenantAwareOAuth2AuthorizationConsentService
        implements OAuth2AuthorizationConsentService {

    private final TenantPerIssuerComponentRegistry componentRegistry;

    public TenantAwareOAuth2AuthorizationConsentService(
            TenantPerIssuerComponentRegistry componentRegistry) {
        this.componentRegistry = componentRegistry;
    }

    private OAuth2AuthorizationConsentService delegate() {
        return this.componentRegistry.getRequired(
                OAuth2AuthorizationConsentService.class);
    }

    @Override
    public void save(OAuth2AuthorizationConsent authorizationConsent) {
        delegate().save(authorizationConsent);
    }

    @Override
    public void remove(OAuth2AuthorizationConsent authorizationConsent) {
        delegate().remove(authorizationConsent);
    }

    @Override
    public OAuth2AuthorizationConsent findById(
            String registeredClientId, String principalName) {
        return delegate().findById(registeredClientId, principalName);
    }
}
~~~

Consent lookup có hai tham số là RegisteredClient ID và principal name. Cả hai có thể trùng giữa hai tenant. Tenant boundary nằm ở implementation được chọn trước khi thực hiện lookup, không nằm trong việc hy vọng các giá trị ID là duy nhất trên toàn hệ thống.

### 7.1. Vì sao không chỉ thêm tenant vào principalName?

Có thể tạo principal name có namespace như `tenant-a:alice`, nhưng đây chỉ là một lớp namespacing. Nó không thay thế định tuyến tenant cho authorization store:

- Authorization service vẫn phải cô lập token và grant.
- RegisteredClient ID vẫn có thể trùng giữa các kho.
- Revocation và introspection vẫn phải giới hạn trong issuer.
- Principal naming có thể thay đổi theo identity provider.

Giữ tenant isolation ở tầng persistence/service; dùng principal namespace như một biện pháp bổ sung nếu identity model yêu cầu.

## 8. Định tuyến RegisteredClientRepository cùng tenant

`JdbcOAuth2AuthorizationService` và `JdbcOAuth2AuthorizationConsentService` nhận `RegisteredClientRepository` để tra cứu client khi đọc/ghi dữ liệu. Vì vậy, nếu authorization/consent service đã tách theo tenant nhưng repository vẫn là global repository, dữ liệu có thể bị ghép với RegisteredClient thuộc tenant khác.

Tạo delegating repository:

~~~java
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;

public final class TenantAwareRegisteredClientRepository
        implements RegisteredClientRepository {

    private final TenantPerIssuerComponentRegistry componentRegistry;

    public TenantAwareRegisteredClientRepository(
            TenantPerIssuerComponentRegistry componentRegistry) {
        this.componentRegistry = componentRegistry;
    }

    private RegisteredClientRepository delegate() {
        return this.componentRegistry.getRequired(RegisteredClientRepository.class);
    }

    @Override
    public void save(RegisteredClient registeredClient) {
        delegate().save(registeredClient);
    }

    @Override
    public RegisteredClient findById(String id) {
        return delegate().findById(id);
    }

    @Override
    public RegisteredClient findByClientId(String clientId) {
        return delegate().findByClientId(clientId);
    }
}
~~~

Đây là dependency quan trọng: khi một JDBC authorization service deserialize authorization, repository được truyền vào phải truy vấn RegisteredClient trong cùng tenant context.

Trong hệ thống đầy đủ, các component khác cũng cần tenant-aware implementation nếu dữ liệu của chúng phụ thuộc issuer, đặc biệt `JWKSource<SecurityContext>`. Bài này tập trung vào authorization và consent service nhưng không được triển khai hai service đó trong khi để key hoặc client repository rơi về tenant mặc định.

## 9. Cấu hình JDBC service riêng cho từng tenant

Spring Authorization Server cung cấp:

- `JdbcOAuth2AuthorizationService` để lưu authorization bằng JDBC.
- `JdbcOAuth2AuthorizationConsentService` để lưu consent bằng JDBC.
- `JdbcRegisteredClientRepository` để lưu RegisteredClient bằng JDBC.

Các implementation này dùng `JdbcOperations` và là lựa chọn persistence phù hợp cho production khi đã cấu hình schema, transaction và database riêng theo yêu cầu. Hai interface authorization/consent là optional trong cấu hình server và mặc định dùng implementation in-memory; `InMemoryOAuth2AuthorizationService` và `InMemoryOAuth2AuthorizationConsentService` chỉ phù hợp development/test, không dùng làm persistence production hoặc multi-node.

### 9.1. Cấu hình RegisteredClientRepository

Ví dụ dưới đây giả định ứng dụng đã có hai DataSource được cấu hình với qualifier riêng:

~~~java
import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.server.authorization.client.JdbcRegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;

@Configuration(proxyBeanMethods = false)
class TenantRegisteredClientRepositoryConfiguration {

    @Bean
    RegisteredClientRepository registeredClientRepository(
            @Qualifier("tenantADataSource") DataSource tenantADataSource,
            @Qualifier("tenantBDataSource") DataSource tenantBDataSource,
            TenantPerIssuerComponentRegistry registry) {

        registry.register(TenantIssuers.TENANT_A,
                RegisteredClientRepository.class,
                new JdbcRegisteredClientRepository(new JdbcTemplate(tenantADataSource)));

        registry.register(TenantIssuers.TENANT_B,
                RegisteredClientRepository.class,
                new JdbcRegisteredClientRepository(new JdbcTemplate(tenantBDataSource)));

        return new TenantAwareRegisteredClientRepository(registry);
    }
}
~~~

### 9.2. Cấu hình OAuth2AuthorizationService

~~~java
import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.server.authorization.JdbcOAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;

@Configuration(proxyBeanMethods = false)
class TenantAuthorizationServiceConfiguration {

    @Bean
    OAuth2AuthorizationService authorizationService(
            @Qualifier("tenantADataSource") DataSource tenantADataSource,
            @Qualifier("tenantBDataSource") DataSource tenantBDataSource,
            RegisteredClientRepository registeredClientRepository,
            TenantPerIssuerComponentRegistry registry) {

        registry.register(TenantIssuers.TENANT_A,
                OAuth2AuthorizationService.class,
                new JdbcOAuth2AuthorizationService(
                        new JdbcTemplate(tenantADataSource), registeredClientRepository));

        registry.register(TenantIssuers.TENANT_B,
                OAuth2AuthorizationService.class,
                new JdbcOAuth2AuthorizationService(
                        new JdbcTemplate(tenantBDataSource), registeredClientRepository));

        return new TenantAwareOAuth2AuthorizationService(registry);
    }
}
~~~

### 9.3. Cấu hình OAuth2AuthorizationConsentService

~~~java
import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.server.authorization.JdbcOAuth2AuthorizationConsentService;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationConsentService;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;

@Configuration(proxyBeanMethods = false)
class TenantConsentServiceConfiguration {

    @Bean
    OAuth2AuthorizationConsentService authorizationConsentService(
            @Qualifier("tenantADataSource") DataSource tenantADataSource,
            @Qualifier("tenantBDataSource") DataSource tenantBDataSource,
            RegisteredClientRepository registeredClientRepository,
            TenantPerIssuerComponentRegistry registry) {

        registry.register(TenantIssuers.TENANT_A,
                OAuth2AuthorizationConsentService.class,
                new JdbcOAuth2AuthorizationConsentService(
                        new JdbcTemplate(tenantADataSource), registeredClientRepository));

        registry.register(TenantIssuers.TENANT_B,
                OAuth2AuthorizationConsentService.class,
                new JdbcOAuth2AuthorizationConsentService(
                        new JdbcTemplate(tenantBDataSource), registeredClientRepository));

        return new TenantAwareOAuth2AuthorizationConsentService(registry);
    }
}
~~~

Các bean trên cùng dùng registry và cùng bộ DataSource theo tenant. Việc gọi `registry.register` trong quá trình khởi tạo bean chỉ đăng ký implementation cụ thể; bean trả về cho Spring là composite service.

### 9.4. Cấu hình Authorization Server sử dụng composite service

Đưa các composite service và repository vào `OAuth2AuthorizationServerConfigurer`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationConsentService;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
class AuthorizationServerSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(
            HttpSecurity http,
            RegisteredClientRepository registeredClientRepository,
            OAuth2AuthorizationService authorizationService,
            OAuth2AuthorizationConsentService authorizationConsentService)
            throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
                OAuth2AuthorizationServerConfigurer.authorizationServer();

        http.securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
            .with(authorizationServerConfigurer, authorizationServer ->
                authorizationServer
                    .registeredClientRepository(registeredClientRepository)
                    .authorizationService(authorizationService)
                    .authorizationConsentService(authorizationConsentService)
            );

        return http.build();
    }
}
~~~

Đây là phần cấu hình minh họa cho Authorization Server endpoints. Ứng dụng thực tế còn cần JWKSource, authentication chain, user store, issuer configuration và các endpoint policy tương ứng. Đảm bảo không có bean khác ghi đè các service multi-tenant này.

## 10. Schema và DataSource cho mỗi tenant

Mỗi tenant cần có schema tương ứng cho RegisteredClient, authorization và consent. Spring Authorization Server cung cấp SQL schema scripts trong artifact:

| Bảng | Script |
| --- | --- |
| Registered clients | `oauth2-registered-client-schema.sql` |
| Authorizations/tokens | `oauth2-authorization-schema.sql` |
| Consents | `oauth2-authorization-consent-schema.sql` |

Các script được cung cấp trong package resource của Spring Authorization Server. Ví dụ đường dẫn resource:

~~~text
org/springframework/security/oauth2/server/authorization/client/oauth2-registered-client-schema.sql
org/springframework/security/oauth2/server/authorization/oauth2-authorization-schema.sql
org/springframework/security/oauth2/server/authorization/oauth2-authorization-consent-schema.sql
~~~

Chạy migration cho từng tenant database/schema trước khi tenant được đưa vào phục vụ.

### 10.1. Database-per-tenant

Mỗi tenant có DataSource/database riêng:

| Tenant | RegisteredClient | Authorization | Consent |
| --- | --- | --- | --- |
| A | DB A | DB A | DB A |
| B | DB B | DB B | DB B |

Ưu điểm:

- Ranh giới dữ liệu rõ.
- Có thể backup/restore, mã hóa, retention và phân quyền database riêng.
- Query JDBC mặc định không cần thêm tenant predicate.
- Lỗi query thiếu tenant filter không thể tự động đọc database khác nếu credentials tách biệt.

Đổi lại, số lượng connection pool, migration và database resource tăng theo tenant. Cần giới hạn pool tổng và quản lý vòng đời DataSource.

### 10.2. Schema-per-tenant

Các tenant có thể dùng cùng database instance nhưng mỗi tenant một schema. Mỗi JDBC service phải dùng connection/DataSource được cố định đúng schema. Không thay đổi schema trên pooled connection rồi quên reset trước khi trả connection về pool.

Nếu chọn cách set schema theo transaction/session, cần kiểm thử connection reuse và reset-on-return. Với PostgreSQL, có thể dùng transaction-local setting hoặc DataSource wrapper gắn schema cố định; không dựa vào một biến session tồn tại xuyên các request.

### 10.3. Shared tables với tenant_id

Một database/schema chung có thể thêm cột `tenant_id` vào từng bảng. Nhưng các JDBC implementation mặc định của Spring Authorization Server không tự động thêm tenant predicate vào mọi câu SQL chỉ vì schema có cột đó.

Nếu dùng shared tables:

- Viết custom repository/service hoặc JDBC implementation có tenant predicate trong mọi thao tác.
- Đưa tenant_id vào khóa chính/unique constraint/index khi cần.
- Đảm bảo `findById`, `findByToken`, `remove` và consent `findById` đều lọc tenant.
- Cân nhắc database Row-Level Security như một lớp bảo vệ bổ sung.
- Kiểm thử quyền database và connection pool để tenant context không rò sang request khác.

Không thêm cột tenant_id rồi tiếp tục dùng nguyên `JdbcOAuth2AuthorizationService` và giả định dữ liệu đã tự tách.

### 10.4. Chọn mô hình lưu trữ

| Tiêu chí | Database-per-tenant | Schema-per-tenant | Shared tables |
| --- | --- | --- | --- |
| Cách ly dữ liệu | Mạnh, ở cấp database | Mạnh nếu schema routing đúng | Phụ thuộc query filter/RLS |
| Chi phí vận hành | Cao hơn | Trung bình | Thấp hơn |
| JDBC service mặc định | Dùng được với DataSource riêng | Dùng được với schema DataSource riêng | Thường cần custom SQL/service |
| Backup/restore riêng tenant | Thuận tiện | Khả thi theo schema | Phức tạp hơn |
| Scale số tenant lớn | Cần quản lý nhiều DB/pool | Cần quản lý schema/pool | Dễ tập trung nhưng cần bảo đảm isolation |

Chọn mô hình dựa trên yêu cầu compliance, số tenant, mức độ cách ly, vận hành và khả năng mở rộng. Không có một chiến lược duy nhất phù hợp mọi nền tảng.

## 11. Luồng authorization và consent khi đã tách tenant

Ví dụ Alice đăng nhập vào Tenant A:

~~~mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant AS as Authorization Server
    participant C as AuthorizationServerContext
    participant CS as Consent Service A
    participant AU as Authorization Service A
    B->>AS: GET /tenant-a/oauth2/authorize
    AS->>C: Resolve issuer tenant-a
    AS->>CS: findById(clientA, alice)
    CS-->>AS: Consent A hoặc null
    alt Cần user consent
        AS-->>B: Hiển thị consent screen
        B->>AS: User approves scopes
        AS->>CS: save(consent A)
    end
    AS->>AU: save(authorization A)
    AU-->>AS: Persisted
    AS-->>B: Redirect với authorization code
~~~

Khi cùng Alice đăng nhập vào Tenant B, context issuer là Tenant B. Composite service chuyển sang Consent Service B và Authorization Service B. Consent A không được dùng để bỏ qua consent screen ở B.

### 11.1. Consent và authorization không nhất thiết được ghi cùng thời điểm

Consent là quyết định người dùng; authorization là một lần cấp quyền/token. Chúng có vòng đời khác nhau. Khi người dùng đồng ý, consent service lưu authorities; khi grant hoàn tất, authorization service lưu authorization và token.

Thiết kế transaction cần xét hai service dùng cùng tenant DataSource và transaction manager. Nếu chúng ở hai database khác nhau hoặc có transaction manager riêng, không mặc định có một transaction ACID bao trùm cả hai. Xác định hành vi khi một thao tác thành công còn thao tác kia thất bại; dùng retry/idempotency hoặc quy trình bù trừ nếu nghiệp vụ yêu cầu.

### 11.2. Client Credentials

Với `client_credentials`, authorization có thể được tạo cho chính client mà không có user consent. Tuy vậy, OAuth2Authorization vẫn phải được lưu trong tenant của issuer để introspection/revocation/token lookup không vượt tenant.

## 12. Tenant identity trong principal và RegisteredClient

Trong `OAuth2AuthorizationConsent`, khóa lookup là `registeredClientId` và `principalName`. Trong `OAuth2Authorization`, dữ liệu gồm `registeredClientId` và `principalName` cùng token state.

Một tenant có thể có:

- client ID `billing-portal`.
- internal RegisteredClient ID `client-001`.
- principal `alice`.

Tenant khác có thể dùng cùng ba giá trị. Nếu database-per-tenant, giá trị này không xung đột. Nếu shared table, tenant_id phải tham gia vào mọi khóa và truy vấn liên quan.

Đối với OIDC subject, tránh dùng email làm định danh duy nhất nếu email có thể đổi hoặc trùng. Nên dùng subject ổn định trong issuer/tenant, và coi cặp `(iss, sub)` là định danh có namespace khi cần đối chiếu ngoài tenant store.

Không cho phép cùng một consent record của tenant A được tái sử dụng cho tenant B chỉ vì principalName và clientId hiển thị giống nhau.

## 13. JWKSource và các component liên quan

Mặc dù bài học tập trung vào authorization/consent service, một Authorization Server multi-tenant thường cần tách thêm:

- `RegisteredClientRepository`.
- `JWKSource<SecurityContext>`.
- `AuthorizationServerSettings`/issuer resolution.
- User/identity store nếu danh tính user khác nhau theo tenant.
- Cache, consent UI và audit context.

Nếu hai tenant dùng chung signing key mà policy yêu cầu khóa độc lập, token của một tenant có thể bị xác minh ở tenant kia nếu Resource Server không kiểm tra issuer và key policy đúng. Thông thường, mỗi issuer có key set riêng và discovery trả `jwks_uri` tương ứng.

JWKSource có thể dùng cùng registry pattern: lấy JWKSet theo issuer rồi trả các key được JWKSelector yêu cầu. Không trả JWKSet của tenant mặc định khi không xác định được issuer.

### 13.1. Resource Server cũng phải kiểm tra issuer

Tách database trong Authorization Server chưa đủ nếu Resource Server chấp nhận token mà không kiểm tra `iss`. Resource Server cần:

- Xác minh chữ ký theo key set tin cậy của issuer.
- Kiểm tra issuer chính xác.
- Kiểm tra audience/resource.
- Áp dụng scope/authority policy theo tenant.
- Không dùng tenant ID từ request body thay cho token claims đã xác minh.

## 14. Transaction, cache và xử lý đồng thời

### 14.1. Transaction manager

Nếu mỗi tenant có DataSource riêng, các thao tác JDBC của tenant phải dùng transaction manager gắn với DataSource đó. Nếu ứng dụng dùng routing DataSource, tenant routing phải được xác lập trước khi transaction lấy connection và giữ ổn định trong suốt transaction.

Không đổi tenant context giữa một transaction đang chạy. Không để connection được lấy cho tenant A rồi tái sử dụng để truy vấn tenant B.

### 14.2. Cache key phải bao gồm tenant

Nếu cache RegisteredClient, consent, authorization hoặc token lookup, cache key phải có issuer/tenant:

~~~text
issuer + registeredClientId
issuer + registeredClientId + principalName
issuer + tokenFingerprint
~~~

Không dùng `principalName`, `clientId` hoặc token fingerprint làm key toàn cục nếu cache có thể trả dữ liệu authorization nhạy cảm. Khi tenant revoke/disable client, invalidation phải giới hạn đúng tenant và đồng bộ trên các node.

### 14.3. Thread và async task

`AuthorizationServerContextHolder` cung cấp context cho request đang được xử lý. Không giả định context này tự truyền sang mọi executor, message listener hoặc background scheduler.

Với công việc nền như cleanup expired authorizations, export consent hoặc revoke batch:

1. Truyền issuer/tenant đã được xác thực như một tham số công việc.
2. Kiểm tra tenant có trong registry/allowlist.
3. Mở transaction và chọn service/DataSource theo tenant đó.
4. Dọn context sau khi hoàn tất.
5. Không dùng tenant của request trước trong thread pool.

## 15. Vận hành tenant lifecycle

### 15.1. Provision tenant

Quy trình tạo tenant cần:

1. Xác minh tenant identity, domain và issuer duy nhất.
2. Tạo database/schema và credentials phù hợp.
3. Chạy migrations cho registered client, authorization và consent.
4. Khởi tạo RegisteredClientRepository, authorization service và consent service.
5. Đăng ký component vào registry bằng issuer chính xác.
6. Cấu hình JWKSource và key material của tenant.
7. Kiểm tra discovery metadata và protocol endpoints.
8. Chạy smoke test xác nhận không đọc được dữ liệu tenant khác.
9. Chỉ sau đó mới đưa issuer vào load balancer/tenant catalog công khai.

### 15.2. Tenant bị tạm ngưng

Khi tenant bị suspend, không chỉ chặn trang web. Cần xác định policy cho authorization request, token endpoint, introspection, revocation, consent management và các background job. Không xóa database hoặc key chỉ vì tenant tạm ngưng.

### 15.3. Offboarding và xóa dữ liệu

Khi tenant chấm dứt:

- Ngừng phát hành authorization mới.
- Revoke/expire token theo hợp đồng và retention policy.
- Xử lý consent, authorization, RegisteredClient và signing key theo quy trình.
- Giữ audit record trong thời hạn bắt buộc.
- Backup/export theo yêu cầu pháp lý.
- Gỡ component khỏi registry sau khi request đang chạy đã drain.
- Xác nhận tenant không còn xuất hiện trong discovery/catalog.

Không xóa registry entry trước khi xử lý các request/transaction đang chạy; cũng không xóa dữ liệu tenant khác trong một batch cleanup.

## 16. Kiểm thử tenant isolation

Kiểm thử cần chứng minh dữ liệu không đi qua tenant boundary, kể cả khi client ID, principal name hoặc token-like identifiers có giá trị trùng nhau.

### 16.1. Unit test cho registry

Kiểm tra:

- Issuer A trả component A.
- Issuer B trả component B.
- Issuer chưa đăng ký bị từ chối.
- Context không có issuer bị từ chối.
- Hai issuer có suffix gần giống nhau không bị ánh xạ nhầm.
- Không thể đăng ký hai implementation cùng component type cho cùng issuer một cách âm thầm.

### 16.2. Integration test cho authorization service

Chuẩn bị hai database/schema độc lập và cùng tạo:

- RegisteredClient ID giống nhau.
- Client ID giống nhau.
- Principal name giống nhau.
- Scope hoặc token state khác nhau.

Sau đó xác minh:

1. Save authorization trong Tenant A chỉ xuất hiện ở A.
2. findById ở B không trả authorization của A.
3. findByToken ở B không tìm thấy token của A.
4. remove/revoke ở A không làm thay đổi authorization B.
5. Token introspection tại issuer B không chấp nhận token A.

### 16.3. Integration test cho consent service

1. Save consent A với `SCOPE_invoice.read`.
2. Save consent B với `SCOPE_payment.approve`.
3. Cùng registeredClientId/principalName nhưng query A chỉ trả authorities A.
4. Query B chỉ trả authorities B.
5. Remove consent A không xóa consent B.
6. Authorization request ở B không được bỏ qua consent screen chỉ vì user đã consent ở A.

### 16.4. Test song song và connection pool

Chạy request Tenant A và B đồng thời, dùng chung application instance và connection pool infrastructure. Lặp lại nhiều lần để phát hiện:

- ThreadLocal context không được dọn.
- Routing DataSource giữ tenant cũ.
- Transaction mở connection trước khi tenant được xác định.
- Cache key thiếu issuer.
- Background job lấy nhầm context.

## 17. Ma trận kiểm thử

| # | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| 1 | Request issuer A | Dùng service A |
| 2 | Request issuer B | Dùng service B |
| 3 | Issuer chưa đăng ký | Fail closed |
| 4 | Thiếu AuthorizationServerContext | Fail closed |
| 5 | Tenant label chỉ có suffix trùng | Không ánh xạ nhầm vì issuer exact match |
| 6 | Save authorization A | Chỉ lưu tại A |
| 7 | findById authorization A trong B | Không tìm thấy |
| 8 | findByToken token A trong B | Không tìm thấy |
| 9 | Remove authorization A | Không ảnh hưởng B |
| 10 | Introspection token A tại issuer B | Không active/không tìm thấy |
| 11 | Revocation token A tại issuer B | Không thay đổi authorization A |
| 12 | Save consent A | Chỉ lưu tại A |
| 13 | Consent lookup cùng client/principal ở B | Không trả consent A |
| 14 | Remove consent A | Không xóa consent B |
| 15 | Hai tenant trùng clientId | Repository trả đúng client của issuer |
| 16 | Hai tenant trùng principalName | Consent vẫn tách biệt |
| 17 | JdbcAuthorizationService deserialize | Dùng RegisteredClientRepository cùng tenant |
| 18 | Consent service deserialize/lookup | Dùng repository và database đúng tenant |
| 19 | Request song song A/B | Không rò tenant context |
| 20 | Reuse connection sau request A | Request B không đọc schema A |
| 21 | Cache authorization | Cache key có issuer |
| 22 | Cache consent | Cache key có issuer + client + principal |
| 23 | Background cleanup | Tenant được truyền và xác minh tường minh |
| 24 | Tenant đang suspend | Request xử lý theo policy suspend |
| 25 | Provision tenant mới | Chỉ active sau khi migrations/components/smoke test hoàn tất |
| 26 | Remove tenant component | Request đang chạy được drain; tenant khác vẫn hoạt động |
| 27 | Issuer trong token không khớp endpoint | Resource Server từ chối |
| 28 | JWKSource không có tenant context | Không trả key của tenant mặc định |
| 29 | Rollback migration một tenant | Không ảnh hưởng schema/database tenant khác |
| 30 | Restore backup tenant A | Không ghi đè dữ liệu tenant B |

## 18. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Consent tenant B xuất hiện ở A | Consent service global hoặc routing sai | Kiểm tra issuer context và registry |
| Token tenant A được introspect tại B | Authorization lookup xuyên tenant | Đảm bảo findByToken chỉ dùng service của issuer hiện tại |
| Authorization deserialize lỗi | RegisteredClientRepository không đúng tenant | Dùng tenant-aware repository |
| Unknown issuer nhưng request vẫn chạy | Có fallback tenant mặc định | Bỏ fallback và fail closed |
| Tenant name gần giống bị chọn nhầm | Dùng suffix/substring matching | Dùng exact canonical issuer key |
| Consent không được lưu sau approval | Consent service trỏ sai DataSource hoặc migration thiếu | Kiểm tra bean routing, schema và transaction |
| Request song song trả nhầm dữ liệu | Context/connection/cache bị rò | Kiểm tra lifecycle context, transaction và cache key |
| Token chữ ký hợp lệ nhưng issuer sai | Resource Server không validate iss đúng | Cấu hình issuer-specific validation |
| Tenant mới trả lỗi bảng không tồn tại | Chưa chạy migrations | Chạy schema migrations trước khi publish tenant |
| Xóa tenant làm ảnh hưởng tenant khác | Shared DB cleanup thiếu tenant predicate | Kiểm tra migration/cleanup và RLS |

## 19. Checklist triển khai production

1. **Issuer:** mỗi tenant có issuer canonical và duy nhất.
2. **Resolution:** tenant được xác định từ issuer đã tin cậy, không từ header/query tự khai.
3. **Multiple issuers:** bật `multipleIssuersAllowed(true)` và không ép issuer cố định.
4. **Registry:** map exact issuer tới implementation; unknown issuer phải fail closed.
5. **Authorization:** `OAuth2AuthorizationService` riêng cho từng tenant.
6. **Consent:** `OAuth2AuthorizationConsentService` riêng cho từng tenant.
7. **Registered client:** repository cũng phải tenant-aware.
8. **JWK:** key set và signing key đúng tenant.
9. **Persistence:** chọn DB/schema/shared-table có tenant filter rõ ràng.
10. **Schema:** migrations chạy độc lập và có version theo tenant.
11. **Transactions:** transaction manager và DataSource routing nhất quán.
12. **Cache:** mọi cache key có issuer/tenant.
13. **Async:** job nền nhận tenant tường minh, không dựa vào request ThreadLocal.
14. **Resource Server:** validate iss, aud, signature và scope theo tenant.
15. **Tests:** có negative tests truy cập chéo tenant và concurrency tests.
16. **Operations:** có provisioning, suspension, offboarding, backup và restore riêng tenant.
17. **Observability:** log issuer/tenant identifier an toàn; không log token, consent payload nhạy cảm hoặc secret.

## 20. Bài tập và câu hỏi tự đánh giá

**Bài tập A — Phân biệt hai service.** Một người dùng thu hồi consent nhưng Access Token cũ vẫn còn hạn. Mô tả service nào lưu consent, service nào lưu authorization/token và hệ thống cần làm gì nếu muốn token cũ ngừng active.

**Bài tập B — Composite service.** Viết registry ánh xạ issuer A/B và triển khai delegating OAuth2AuthorizationService cho bốn method save, remove, findById, findByToken.

**Bài tập C — Consent isolation.** Tạo hai tenant có cùng principalName và registeredClientId. Viết integration test chứng minh consent authorities không được dùng chéo tenant.

**Bài tập D — Storage design.** So sánh database-per-tenant, schema-per-tenant và shared-table có tenant_id. Giải thích vì sao JDBC service mặc định không tự lọc tenant_id.

**Bài tập E — Context spoofing.** Một client gửi `X-Tenant-ID: tenant-b` trong khi issuer request là tenant-a. Xây dựng threat model và giải thích vì sao header đó không được quyết định service routing.

**Bài tập F — Async cleanup.** Một scheduled job dọn authorization hết hạn cho nhiều tenant. Thiết kế cách truyền issuer, mở transaction, chọn service và bảo đảm không tái sử dụng tenant context cũ.

**Bài tập G — Full integration.** Cấu hình `multipleIssuersAllowed(true)`, hai DataSource, ba delegating components và JWKSource. Kiểm thử authorization code flow cho cả hai issuer.

**Câu hỏi ôn tập:**

1. `OAuth2Authorization` lưu những dữ liệu nào?
2. `OAuth2AuthorizationConsent` lưu quyết định gì?
3. Vì sao consent không đồng nghĩa token còn active?
4. Tại sao các service interface không cần tham số tenantId?
5. `AuthorizationServerContextHolder` cung cấp thông tin gì?
6. Vì sao nên dùng full issuer làm key thay vì suffix?
7. Khi không tìm thấy tenant trong registry, server phải xử lý thế nào?
8. Vì sao RegisteredClientRepository phải tách cùng authorization service?
9. Vì sao consent service cũng phải được định tuyến theo issuer?
10. Database-per-tenant và schema-per-tenant khác nhau thế nào?
11. Shared-table cần thay đổi gì trong JDBC query?
12. Cache key cần chứa những thành phần nào?
13. Background job cần truyền tenant ra sao?
14. Resource Server cần kiểm tra issuer thế nào?
15. Viết những test nào để phát hiện token/consent bị truy cập chéo tenant?

## 21. Tài liệu tham khảo

- [Spring Authorization Server 1.5.8 — How-to: Implement Multitenancy](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-multitenancy.html)
- [Spring Authorization Server 1.5.8 — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Authorization Server 1.5.8 — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
- [OAuth2AuthorizationService API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/OAuth2AuthorizationService.html)
- [OAuth2AuthorizationConsentService API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/OAuth2AuthorizationConsentService.html)
- [RegisteredClientRepository API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/client/RegisteredClientRepository.html)
- [Spring Security — Multi Tenant Security Cheat Sheet (OWASP)](https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html)
- [PostgreSQL — Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)

**Ghi nhớ:** `OAuth2AuthorizationService` lưu trạng thái grant/token; `OAuth2AuthorizationConsentService` lưu quyết định người dùng đã đồng ý cho client. Trong multi-tenant Authorization Server, cả hai phải được định tuyến theo issuer của request hiện tại. Dùng `AuthorizationServerContextHolder` và registry ánh xạ full issuer tới implementation riêng; unknown issuer hoặc thiếu context phải fail closed. Đồng thời, `RegisteredClientRepository`, JWKSource, DataSource, transaction và cache cũng phải tuân theo cùng tenant boundary. Kiểm thử bằng hai tenant có client ID và principal name trùng nhau để chứng minh authorization, consent, introspection và revocation không truy cập chéo tenant.
