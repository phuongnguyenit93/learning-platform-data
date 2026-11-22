# Phân giải tenant bằng cơ chế đáng tin cậy và kiểm tra host, path

## 1. Mục tiêu và phạm vi

Trong mô-đun **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, chúng ta học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng **Spring Security**, **Spring Authorization Server** và **Spring Boot**. Bài này tập trung vào bước đầu tiên của kiến trúc đa tenant: xác định tenant nào đang nhận request, xác minh host/path của request đó và truyền tenant context đến đúng thành phần xử lý.

Một Authorization Server phục vụ nhiều tổ chức có thể dùng các issuer khác nhau:

- Host riêng cho từng tenant: `https://acme.login.example.com`.
- Path riêng trên một host: `https://login.example.com/acme`.
- Kết hợp host và path: `https://acme.login.example.com/auth`.

Issuer là định danh bảo mật của Authorization Server. Nó xuất hiện trong discovery metadata, token claim `iss`, quá trình kiểm tra chữ ký và cấu hình client. Nếu request của tenant A bị định tuyến nhầm sang khóa ký, client repository hoặc authorization store của tenant B, ranh giới bảo mật đã bị phá vỡ.

Spring Authorization Server 1.5.8 hỗ trợ nhiều issuer trên cùng host thông qua issuer chứa path. Bài dùng API 1.5.8 làm mốc và mở rộng thành quy trình định tuyến host/path có allowlist. Khi triển khai nhánh khác, kiểm tra lại Javadoc và hướng dẫn multitenancy đúng version.

Sau bài này, bạn có thể:

1. Phân biệt tenant identifier, issuer và host/path routing key.
2. Chọn chiến lược phân giải tenant theo host, path hoặc kết hợp.
3. Bật nhiều issuer trong Spring Authorization Server.
4. Kiểm tra host, scheme, port và path theo cấu hình server.
5. Xử lý `Forwarded`/`X-Forwarded-*` qua proxy tin cậy.
6. Dùng `AuthorizationServerContext` để chọn component theo issuer hiện tại.
7. Cô lập client, authorization, consent và signing keys giữa các tenant.
8. Kiểm thử host spoofing, path traversal, issuer mismatch và cross-tenant access.

## 2. Tenant ID, host, path và issuer

### 2.1. Bốn khái niệm cần tách biệt

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Tenant ID | Khóa nội bộ xác định tổ chức | `tenant-acme` |
| Host | Tên máy chủ mà client truy cập | `login.example.com` |
| Path prefix | Đường dẫn đại diện tenant trên host | `/acme` |
| Issuer | Định danh URL chuẩn của Authorization Server | `https://login.example.com/acme` |

Tenant ID là khóa nội bộ. Host/path là dữ liệu định tuyến từ request. Issuer là định danh công khai phải ổn định và khớp với giá trị trong token/discovery. Không dùng trực tiếp một chuỗi host hoặc path tùy ý làm tenant ID, cũng không tự tạo issuer từ dữ liệu request chưa được kiểm tra.

### 2.2. Issuer là ranh giới bảo mật

Ví dụ hai tenant:

| Tenant | Issuer | Discovery |
| --- | --- | --- |
| Acme | `https://login.example.com/acme` | `https://login.example.com/acme/.well-known/openid-configuration` |
| Globex | `https://login.example.com/globex` | `https://login.example.com/globex/.well-known/openid-configuration` |

Metadata của Acme phải công bố issuer `https://login.example.com/acme`, và các endpoint được công bố phải nằm dưới base URL tương ứng. Token do Acme phát hành phải có `iss` khớp issuer của Acme. Một client đã cấu hình issuer Acme không được chấp nhận token issuer Globex chỉ vì hai tenant dùng cùng một domain.

OIDC yêu cầu client kiểm tra issuer chính xác với issuer đã được discovery/configuration tin cậy. Vì vậy, không xem issuer chỉ là URL dùng để hiển thị hoặc tạo link.

### 2.3. Không suy tenant từ một tín hiệu chưa xác thực

Các tín hiệu sau không tự chứng minh tenant:

- Query parameter như `?tenant=acme`.
- Header tùy ý như `X-Tenant-Id`.
- `Host`/`X-Forwarded-Host` do client gửi thẳng.
- Path chưa được chuẩn hóa hoặc chưa kiểm tra route.
- JWT `iss` chưa xác minh chữ ký và chưa kiểm tra issuer allowlist.
- `client_id` do request gửi lên trước khi client authentication thành công.

Một tín hiệu có thể được dùng để chọn route ban đầu, nhưng kết quả phải được đối chiếu với danh sách tenant/issuer đã provision. Việc chọn tenant không được tự tạo tenant mới hoặc tự tin cậy host chưa đăng ký.

## 3. Chọn chiến lược host/path

### 3.1. Host riêng cho từng tenant

Ví dụ:

```text
https://acme.login.example.com/oauth2/authorize
https://globex.login.example.com/oauth2/authorize
```

Ưu điểm:

- Host là ranh giới định tuyến rõ ràng.
- Có thể cấu hình DNS, TLS certificate, WAF và rate limit riêng.
- Dễ đưa từng tenant đến ingress hoặc backend riêng khi cần.

Điểm cần quản lý:

- Allowlist chính xác hostname và port.
- Wildcard DNS/certificate không có nghĩa mọi subdomain đều là tenant hợp lệ.
- Phải kiểm tra `Host`/authority trước khi tạo issuer.
- Các host alias cần ánh xạ về một issuer canonical đã cấu hình.

Không chấp nhận mọi subdomain của `login.example.com` bằng phép kiểm tra `endsWith("login.example.com")`. Chuỗi `evil-login.example.com` hoặc host có hậu tố gây nhầm lẫn có thể vượt qua một kiểm tra suffix viết sai. Dùng exact mapping hoặc kiểm tra ranh giới DNS label rõ ràng.

### 3.2. Path riêng trên cùng host

Ví dụ:

```text
https://login.example.com/acme/oauth2/authorize
https://login.example.com/globex/oauth2/authorize
```

Spring Authorization Server hỗ trợ kiểu nhiều issuer trên một host bằng issuer chứa path. Đây là chiến lược được hướng dẫn multitenancy chính thức sử dụng. Path tenant là một phần của issuer và base URL của protocol endpoints.

Khi dùng path:

- Prefix phải nằm trong route table.
- So khớp theo segment boundary, tránh `/acme` khớp nhầm `/acme-old`.
- Không giải mã URL nhiều lần.
- Từ chối path encoding bất thường, dot segment hoặc slash/backslash được mã hóa nếu routing layer không hỗ trợ chúng.
- Giữ nguyên issuer canonical đã provision.

### 3.3. Kết hợp host và path

Một số hệ thống cần host chung theo vùng và path riêng theo tenant:

```text
https://apac.login.example.com/acme
https://apac.login.example.com/globex
https://eu.login.example.com/contoso
```

Route key khi đó gồm scheme, hostname, port và path prefix. Nếu một tenant chuyển vùng hoặc đổi hostname, hãy quản lý alias và issuer migration có kế hoạch. Không để hai tenant có cùng route key.

### 3.4. Chọn chiến lược theo yêu cầu cách ly

| Tiêu chí | Host riêng | Path riêng |
| --- | --- | --- |
| DNS/TLS | Cần nhiều hostname hoặc wildcard có kiểm soát | Có thể dùng một hostname |
| WAF/rate limit | Có thể áp policy theo host | Thường áp theo path/tenant route |
| Issuer | Khác hostname | Khác path |
| Reverse proxy | Cần giữ host gốc đáng tin cậy | Cần giữ path prefix gốc |
| Cấu hình SAS | Issuer request-derived/tenant-aware | `multipleIssuersAllowed(true)` cho nhiều issuer cùng host |
| Vận hành | Quản lý DNS/certificate | Quản lý path routing và prefix |

Nếu cần cách ly cao hoặc custom domain của khách hàng, host riêng thường dễ gắn với TLS, ingress và policy mạng. Nếu muốn một endpoint tập trung, path riêng thường đơn giản hơn. Dù chọn cách nào, issuer và tenant component registry phải xác định duy nhất tenant.

## 4. Bật nhiều issuer trong Spring Authorization Server

### 4.1. Cấu hình multipleIssuersAllowed

Mặc định, nhiều issuer trên cùng host bị tắt. Với mô hình issuer có path, bật:

```java
@Configuration(proxyBeanMethods = false)
public class AuthorizationServerSettingsConfig {

    @Bean
    AuthorizationServerSettings authorizationServerSettings() {
        return AuthorizationServerSettings.builder()
                .multipleIssuersAllowed(true)
                .build();
    }
}
```

Trong mô hình nhiều issuer được phân giải từ request, không cố định một issuer duy nhất bằng `.issuer("https://login.example.com")`. Việc cấu hình issuer cố định sẽ đưa server về một issuer đơn và làm mất mục đích phân giải issuer theo request.

Nếu ứng dụng chỉ phục vụ một issuer, hãy cấu hình issuer cố định theo thiết kế single-tenant. Không bật nhiều issuer chỉ để né một lỗi cấu hình host.

Hướng dẫn chính thức của Spring mô tả cụ thể mô hình nhiều issuer trên cùng host bằng path component. Host-based routing là một lớp định tuyến ở ingress/tenant directory; không xem riêng cờ `multipleIssuersAllowed` là cơ chế allowlist hostname. Với host riêng cho từng tenant, vẫn phải kiểm tra host và xác nhận issuer request-derived đúng với issuer canonical đã đăng ký.

### 4.2. AuthorizationServerContext và issuer hiện tại

Spring Authorization Server cung cấp:

- `AuthorizationServerContext`: chứa `AuthorizationServerSettings` và issuer của request hiện tại.
- `AuthorizationServerContextHolder`: truy cập context trong quá trình xử lý request.

Trong cấu hình nhiều issuer, `AuthorizationServerContext.getIssuer()` có thể chứa path tenant. Ví dụ:

| Request endpoint | Issuer được phân giải |
| --- | --- |
| `https://login.example.com/acme/oauth2/token` | `https://login.example.com/acme` |
| `https://login.example.com/globex/oauth2/token` | `https://login.example.com/globex` |
| `https://login.example.com/auth/acme/oauth2/jwks` | `https://login.example.com/auth/acme` |

Đọc issuer trong thành phần được gọi trong request lifecycle:

```java
AuthorizationServerContext context =
        AuthorizationServerContextHolder.getContext();

if (context == null || context.getIssuer() == null) {
    throw new IllegalStateException(
            "Authorization Server issuer context is unavailable"
    );
}

String issuer = context.getIssuer();
```

Không cache issuer hiện tại vào field của singleton bean. `AuthorizationServerContextHolder` gắn context với request đang xử lý; giá trị tenant phải được đọc trong từng lời gọi, không lưu thành trạng thái dùng chung giữa các request.

### 4.3. Discovery phải phản ánh đúng tenant

Với path issuer `https://login.example.com/acme`, OIDC discovery:

```http
GET /acme/.well-known/openid-configuration HTTP/1.1
Host: login.example.com
```

Phần metadata quan trọng phải tương ứng:

```json
{
  "issuer": "https://login.example.com/acme",
  "authorization_endpoint": "https://login.example.com/acme/oauth2/authorize",
  "token_endpoint": "https://login.example.com/acme/oauth2/token",
  "jwks_uri": "https://login.example.com/acme/oauth2/jwks",
  "revocation_endpoint": "https://login.example.com/acme/oauth2/revoke",
  "introspection_endpoint": "https://login.example.com/acme/oauth2/introspect"
}
```

Đây là ví dụ rút gọn. Hãy kiểm tra toàn bộ metadata do server trả về, đặc biệt issuer, endpoint URLs và JWKS URI. Nếu discovery của Acme trả endpoint hoặc issuer của Globex, không cho client tiếp tục flow.

## 5. Ranh giới tin cậy của Host và forwarded headers

### 5.1. Host/authority là input có thể bị giả mạo

HTTP request mang authority/Host để server biết request nhắm đến hostname nào. Ứng dụng không nên tự động tin mọi giá trị Host để tạo absolute issuer hoặc URL redirect. Host chưa được đăng ký có thể dẫn đến:

- Issuer giả trong discovery.
- URL token/JWKS endpoint trỏ sang host của attacker.
- Cache poisoning khi cache key không bao gồm host.
- Password reset/consent link hoặc redirect dùng sai domain.
- Tenant confusion giữa hai host alias.

Thiết lập allowlist host ở ingress/reverse proxy và kiểm tra lại ở ứng dụng. Từ chối host không thuộc tenant directory; không dùng default tenant làm fallback cho host lạ.

### 5.2. Forwarded và X-Forwarded headers

Khi ứng dụng đứng sau load balancer hoặc reverse proxy, request nội bộ có thể nhìn thấy host, scheme, port và path khác với URL client đã truy cập. Proxy có thể chuyển thông tin gốc bằng:

- `Forwarded` theo RFC 7239;
- `X-Forwarded-Host`;
- `X-Forwarded-Proto`;
- `X-Forwarded-Port`;
- `X-Forwarded-Prefix`.

Chỉ sử dụng các header này khi proxy ở ranh giới tin cậy đã xóa giá trị do client gửi và ghi lại giá trị của chính nó. Spring Framework cảnh báo forwarded headers không được phép đi trực tiếp từ bên ngoài vào ứng dụng như dữ liệu tin cậy.

### 5.3. Cấu hình Spring Boot sau trusted proxy

Nếu hạ tầng đã có proxy tin cậy và proxy ghi đè forwarded headers, có thể cấu hình Spring Boot theo chiến lược phù hợp:

```yaml
server:
  forward-headers-strategy: framework
```

`FRAMEWORK` dùng `ForwardedHeaderFilter` trên servlet stack. `NATIVE` dùng hỗ trợ của web server. Chọn theo proxy/server thực tế và kiểm thử cách host, scheme, port, prefix được khôi phục. Không bật forwarded-header processing một cách mù quáng khi ứng dụng có thể nhận traffic trực tiếp từ Internet.

Nếu không thể tin forwarded headers, không dùng chúng để xác định issuer. Có thể cấu hình chế độ remove-only ở filter phù hợp hoặc để chiến lược forwarded headers ở `NONE`, đồng thời yêu cầu proxy route theo Host/URL đã được xác minh.

Với path tenancy, proxy nên giữ nguyên tenant prefix hoặc khôi phục prefix gốc bằng forwarded-prefix header chỉ do proxy tin cậy ghi. Nếu proxy chuyển `/acme/oauth2/token` thành `/oauth2/token`, resolver dựa trên `getRequestURI()` sẽ không còn thấy `/acme`; `AuthorizationServerContext` cũng phải nhìn thấy cùng issuer bên ngoài. Không tự nối `X-Forwarded-Prefix` chưa xác minh vào path hoặc issuer. Kiểm tra request sau proxy bằng integration test.

### 5.4. Ví dụ proxy boundary

```text
Internet client
    |
    | Host: attacker.example
    | X-Forwarded-Host: login.example.com
    v
Trusted ingress / reverse proxy
    |
    | validate public host against virtual-host allowlist
    | remove incoming Forwarded and X-Forwarded-* headers
    | set trusted Forwarded/X-Forwarded-* values
    v
Spring Boot Authorization Server
    |
    | forwarded-header strategy matches ingress contract
    | resolve canonical issuer
    v
Tenant directory / component registry
```

Không để một client bên ngoài tự chọn `X-Forwarded-Host` rồi làm ứng dụng phát hành token với issuer của tenant khác. Nếu backend có thể truy cập trực tiếp, giới hạn mạng để chỉ ingress được kết nối hoặc bảo đảm backend không tin forwarded headers từ đường truy cập trực tiếp.

## 6. Kiểm tra host/path bằng tenant directory

### 6.1. Dùng route table đã provision

Thay vì tự ghép issuer từ request, khai báo route đã được quản trị:

| Scheme | Host | Port | Path prefix | Tenant ID | Issuer canonical |
| --- | --- | --- | --- | --- | --- |
| `https` | `login.example.com` | `443` | `/acme` | `tenant-acme` | `https://login.example.com/acme` |
| `https` | `login.example.com` | `443` | `/globex` | `tenant-globex` | `https://login.example.com/globex` |
| `https` | `acme.login.example.com` | `443` | `/` | `tenant-acme` | `https://acme.login.example.com` |

Route table là allowlist. Mỗi route ánh xạ tới một tenant đã tồn tại và một issuer canonical. Không thêm route chỉ vì request lần đầu đến với host/path mới.

### 6.2. Mô hình route và resolver

Ví dụ dưới đây minh họa một resolver đơn giản. Nó giả định request đã đi qua cấu hình trusted proxy nếu có; phần path prefix được so khớp theo segment boundary:

Code dùng Java 17+ (record) và lược bỏ import cùng các exception/service riêng của ứng dụng. `pathPrefix` trong route table phải dùng cùng dạng path mà servlet container trả về qua `getRequestURI()`, bao gồm hoặc loại trừ context path một cách nhất quán. Nếu proxy rewrite path, route table phải khớp path sau rewrite hoặc một prefix gốc đã được khôi phục từ trusted proxy.

```java
public record TenantRoute(
        String tenantId,
        String scheme,
        String host,
        int port,
        String pathPrefix,
        String issuer) {
}
```

```java
public final class TenantRouteResolver {

    private final List<TenantRoute> routes;

    public TenantRouteResolver(List<TenantRoute> routes) {
        this.routes = List.copyOf(routes);
    }

    public TenantRoute resolve(HttpServletRequest request) {
        String scheme = request.getScheme().toLowerCase(Locale.ROOT);
        String host = normalizeHost(request.getServerName());
        int port = effectivePort(scheme, request.getServerPort());
        String path = request.getRequestURI();

        return this.routes.stream()
                .filter(route -> route.scheme().equals(scheme))
                .filter(route -> normalizeHost(route.host()).equals(host))
                .filter(route -> route.port() == port)
                .filter(route -> pathMatches(path, route.pathPrefix()))
                .max(Comparator.comparingInt(
                        route -> route.pathPrefix().length()
                ))
                .orElseThrow(() ->
                        new UnknownTenantException("No trusted tenant route"));
    }

    private static String normalizeHost(String host) {
        try {
            return IDN.toASCII(host, IDN.USE_STD3_ASCII_RULES)
                    .toLowerCase(Locale.ROOT);
        } catch (IllegalArgumentException ex) {
            throw new UnknownTenantException("Invalid request host", ex);
        }
    }

    private static int effectivePort(String scheme, int port) {
        if (port > 0) {
            return port;
        }
        return "https".equals(scheme) ? 443 : 80;
    }

    private static boolean pathMatches(String requestPath, String prefix) {
        if ("/".equals(prefix)) {
            return requestPath.startsWith("/");
        }
        String normalizedPrefix = prefix.endsWith("/")
                ? prefix.substring(0, prefix.length() - 1)
                : prefix;
        return requestPath.equals(normalizedPrefix)
                || requestPath.startsWith(normalizedPrefix + "/");
    }
}
```

`UnknownTenantException` là exception do ứng dụng định nghĩa. Resolver mẫu giả định route config đã được validate lúc khởi động: scheme chỉ là `https` trong production, host là DNS name hợp lệ, port là port chuẩn, path prefix bắt đầu bằng `/`, không chứa query/fragment hoặc dot segment, và issuer là URL canonical đã được quản trị.

Đối với host dạng IPv6 literal, cần một nhánh canonicalization riêng thay vì gọi `IDN.toASCII`. Nếu ứng dụng không hỗ trợ IPv6 host ở public edge, hãy từ chối route dạng đó một cách tường minh.

Resolver mẫu không tự loại bỏ dấu chấm cuối hostname. Production nên chọn một chính sách rõ ràng: từ chối host có trailing dot, hoặc canonicalize nó giống hệt lúc provision route. Không để hai dạng host này vô tình tạo ra hai issuer khác nhau.

### 6.3. Vì sao so khớp path theo segment boundary?

Nếu tenant prefix là `/acme`, kiểm tra `startsWith("/acme")` cũng nhận `/acme-old`. So khớp đúng phải là:

- Request path bằng `/acme`; hoặc
- Request path bắt đầu bằng `/acme/`.

Đối với prefix lồng nhau như `/region/acme` và `/region/acme/admin`, chọn route cụ thể nhất bằng longest-prefix match, đồng thời không cho phép hai route có cùng scheme/host/port/prefix.

### 6.4. Chuẩn hóa path một lần

Path có thể bị biến đổi bởi proxy, servlet container hoặc router. Các trường hợp cần xử lý nhất quán:

- `%2F`/`%5C` (encoded slash/backslash);
- `%2E` và dot segment `.`/`..`;
- double slash `//`;
- trailing slash;
- percent encoding nhiều lớp;
- path prefix được proxy loại bỏ hoặc thêm vào.

Không decode path nhiều lần hoặc tự viết hàm decode khác với container. Cấu hình ingress và servlet container để thống nhất dạng path; giữ `StrictHttpFirewall` mặc định trừ khi có lý do và đánh giá bảo mật rõ ràng. Nếu một path có nhiều biểu diễn có thể dẫn đến nhiều tenant, từ chối request thay vì cố đoán.

## 7. Nối tenant route với AuthorizationServerContext

### 7.1. Kiểm tra route và issuer là cùng tenant

Route resolver xác nhận request phù hợp một route đã provision. Spring Authorization Server phân giải issuer trong `AuthorizationServerContext`. Trong request xử lý protocol, hãy kiểm tra hai kết quả khớp:

```java
public TenantRoute requireCurrentTenant(
        HttpServletRequest request,
        TenantRouteResolver routeResolver) {

    TenantRoute route = routeResolver.resolve(request);
    AuthorizationServerContext context =
            AuthorizationServerContextHolder.getContext();

    if (context == null || context.getIssuer() == null) {
        throw new UnknownTenantException(
                "Authorization Server context is unavailable"
        );
    }

    if (!route.issuer().equals(context.getIssuer())) {
        throw new UnknownTenantException(
                "Request route and Authorization Server issuer do not match"
        );
    }
    return route;
}
```

Đây là bước defense-in-depth. Resolver không tự ghi đè `AuthorizationServerContextHolder`; context của Spring Authorization Server vẫn do filter/context infrastructure của framework quản lý. Nếu issuer được framework tạo ra khác route canonical, fail closed và sửa cấu hình proxy/path/issuer.

### 7.2. Component registry theo issuer chính xác

Spring Authorization Server yêu cầu một số component có khả năng phân giải theo tenant. Có thể dùng registry:

```java
public record TenantComponents(
        RegisteredClientRepository registeredClientRepository,
        OAuth2AuthorizationService authorizationService,
        OAuth2AuthorizationConsentService authorizationConsentService,
        JWKSource<SecurityContext> jwkSource) {
}
```

```java
public final class TenantComponentRegistry {

    private final ConcurrentMap<String, TenantComponents> tenants =
            new ConcurrentHashMap<>();

    public void register(String issuer, TenantComponents components) {
        Assert.hasText(issuer, "issuer cannot be empty");
        Assert.notNull(components, "components cannot be null");
        TenantComponents previous = this.tenants.putIfAbsent(issuer, components);
        Assert.state(previous == null, "Issuer is already registered");
    }

    public TenantComponents requireCurrent() {
        AuthorizationServerContext context =
                AuthorizationServerContextHolder.getContext();
        Assert.state(context != null && StringUtils.hasText(context.getIssuer()),
                "Authorization Server issuer context is unavailable");

        TenantComponents components = this.tenants.get(context.getIssuer());
        Assert.state(components != null,
                "No components registered for the requested issuer");
        return components;
    }
}
```

Registry này tra cứu bằng exact issuer string đã đăng ký. Tránh mẫu `issuer.endsWith(tenantId)` nếu tenant ID có thể trùng hậu tố hoặc issuer path có prefix tương tự. Việc đăng ký tenant phải diễn ra trong provisioning flow có kiểm soát; request không được tự thêm entry vào registry.

Nếu một hostname alias được chấp nhận, hãy canonicalize alias tại trusted ingress trước khi request vào Authorization Server. Nếu ứng dụng vẫn nhận alias như một host riêng, issuer request-derived có thể khác issuer canonical; khi đó alias phải được provision và xử lý như issuer riêng, hoặc bị từ chối. Không âm thầm map một issuer bên ngoài sang issuer khác.

### 7.3. Delegating component

Một `RegisteredClientRepository` tổng hợp có thể chuyển tiếp đến repository của issuer hiện tại:

```java
public final class TenantAwareRegisteredClientRepository
        implements RegisteredClientRepository {

    private final TenantComponentRegistry registry;

    public TenantAwareRegisteredClientRepository(TenantComponentRegistry registry) {
        this.registry = registry;
    }

    @Override
    public void save(RegisteredClient registeredClient) {
        registry.requireCurrent()
                .registeredClientRepository()
                .save(registeredClient);
    }

    @Override
    public RegisteredClient findById(String id) {
        return registry.requireCurrent()
                .registeredClientRepository()
                .findById(id);
    }

    @Override
    public RegisteredClient findByClientId(String clientId) {
        return registry.requireCurrent()
                .registeredClientRepository()
                .findByClientId(clientId);
    }
}
```

Các delegating service khác theo cùng nguyên tắc:

- `OAuth2AuthorizationService`: delegate `save`, `remove`, `findById`, `findByToken`.
- `OAuth2AuthorizationConsentService`: delegate `save`, `remove`, `findById`.
- `JWKSource<SecurityContext>`: lấy JWK source của issuer hiện tại rồi gọi `get(selector, context)`.

Các wrapper trên dành cho request protocol có `AuthorizationServerContext`. Provisioning/admin control plane chạy ngoài request không có context này; nó nên gọi trực tiếp component cụ thể của tenant đã được quản trị, không gọi delegating wrapper rồi giả định có tenant mặc định.

Ví dụ JWK source tổng hợp:

```java
public final class TenantAwareJwkSource
        implements JWKSource<SecurityContext> {

    private final TenantComponentRegistry registry;

    public TenantAwareJwkSource(TenantComponentRegistry registry) {
        this.registry = registry;
    }

    @Override
    public List<JWK> get(
            JWKSelector selector,
            SecurityContext securityContext) throws KeySourceException {
        JWKSource<SecurityContext> tenantJwkSource =
                registry.requireCurrent().jwkSource();
        return tenantJwkSource.get(selector, securityContext);
    }
}
```

Không để một component tự suy tenant bằng cách tìm client ID trong tất cả tenant repositories. Mọi thao tác phải bắt đầu từ issuer đã được phân giải cho request hiện tại.

## 8. Cô lập dữ liệu và khóa theo tenant

### 8.1. Các component cần được tenant-aware

Hướng dẫn chính thức của Spring Authorization Server xác định bốn component cốt lõi cần hỗ trợ multitenancy:

| Component | Dữ liệu cần cô lập |
| --- | --- |
| `RegisteredClientRepository` | Client ID, secret, grant, scope, redirect URI, auth method |
| `OAuth2AuthorizationService` | Authorization code, access/refresh token, ID Token, trạng thái token |
| `OAuth2AuthorizationConsentService` | Consent của resource owner theo client và principal |
| `JWKSource<SecurityContext>` | Signing key, verification key, key rotation và JWKS công khai |

Ngoài ra, ứng dụng thường cần tenant-aware:

- User directory/`UserDetailsService`;
- policy service, consent policy và claim mapper;
- audit log và event publisher;
- rate limit/quota;
- cache và distributed lock;
- key management/KMS alias;
- email, branding và custom login/consent page.

### 8.2. Cô lập database

Có ba lựa chọn phổ biến:

| Mô hình | Cách hoạt động | Đánh giá |
| --- | --- | --- |
| Database riêng | Mỗi tenant có database/cluster riêng | Cách ly mạnh, chi phí vận hành cao |
| Schema riêng | Mỗi tenant có schema riêng trong cùng database | Cách ly tốt nếu quyền DB và migration được quản lý |
| Shared schema + tenant key | Bảng chung có `tenant_id` | Tiết kiệm, cần bảo đảm mọi query/unique key đều có tenant |

Hướng dẫn Spring minh họa các repository JDBC riêng theo issuer và `DataSource` riêng. Đây là cách rõ ràng để giảm nguy cơ query nhầm tenant. Nếu dùng shared schema, không chỉ thêm `tenant_id` vào entity: phải áp dụng tenant predicate ở mọi câu query, unique constraint và foreign key liên quan.

### 8.3. Cô lập client và authorization

Client ID không nhất thiết unique toàn hệ thống nếu repository được cô lập theo tenant. Tuy nhiên, trong một repository chung, unique key phải bao gồm tenant hoặc client ID phải được namespace rõ ràng. Khi lookup, phải dùng tenant context trước khi tra client.

Authorization record phải luôn tham chiếu client thuộc cùng tenant. Không cho phép authorization của Acme tham chiếu `registered_client_id` chỉ tồn tại trong repository của Globex. Consent lookup cũng phải bao gồm client/tenant context; cùng một `principalName` ở hai tenant là hai danh tính trong hai security domain khác nhau.

### 8.4. Cô lập JWK và signing key

Mỗi issuer nên có bộ signing keys và JWKS riêng, hoặc một key management design có ranh giới tenant được kiểm chứng. Với JWT:

- Acme ký bằng key Acme.
- Globex ký bằng key Globex.
- JWKS của Acme chỉ công bố public keys Acme.
- Token `iss` Acme phải xác minh bằng issuer/key configuration Acme.

Không dùng chung private signing key giữa tenant chỉ để đơn giản hóa cấu hình. Nếu một tenant bị lộ key, phạm vi ảnh hưởng không được lan sang tenant khác. Key rotation cần được thực hiện riêng hoặc có policy đồng bộ được kiểm soát.

## 9. Tenant context trong ứng dụng và các tác vụ nền

### 9.1. Context theo request

Trong HTTP protocol flow, `AuthorizationServerContextHolder` cung cấp issuer của request hiện tại. Hãy đọc context trong từng lời gọi service/repository và delegate ngay tới component của tenant.

Không lưu `TenantComponents` hiện tại vào singleton field hoặc mutable static variable. Các request đồng thời có thể thuộc tenant khác nhau; một biến dùng chung có thể khiến request của Acme ghi dữ liệu vào database Globex.

### 9.2. Async, scheduler và message consumer

`AuthorizationServerContextHolder` gắn với request lifecycle và không tự động trở thành tenant context cho mọi tác vụ async/background. Nếu công việc được đưa vào queue hoặc scheduler:

- Ghi tenant ID/issuer đã xác minh vào message metadata.
- Khi consumer xử lý, tra tenant từ registry allowlist.
- Xác thực message producer và quyền truy cập tenant.
- Thiết lập context riêng cho tác vụ theo cơ chế được ứng dụng quản lý.
- Xóa context trong `finally` sau khi hoàn thành.

Không serialize một object `AuthorizationServerContext` từ HTTP request rồi dùng lại ở background. Chỉ truyền identifier ổn định và xác minh lại quyền truy cập khi consumer nhận message.

### 9.3. Cache phải có tenant trong key

Các cache dễ gây rò dữ liệu nếu key chỉ chứa client ID, user ID hoặc token hash. Dùng key có tenant/issuer:

```text
tenant-acme:registered-client:client-123
tenant-globex:registered-client:client-123
tenant-acme:user-profile:user-100
tenant-globex:user-profile:user-100
```

Áp dụng tương tự cho cache authorization, consent, JWKS, discovery metadata, rate limit và distributed lock. Khi tenant bị xóa hoặc key rotation, invalidate đúng namespace.

## 10. Thêm tenant động và quản lý vòng đời

### 10.1. Provision tenant qua control plane

Tenant động cần một quy trình quản trị độc lập với protocol request:

1. Xác minh tổ chức/domain và quyền của quản trị viên.
2. Cấp tenant ID nội bộ duy nhất.
3. Đăng ký hostname/path prefix và issuer canonical.
4. Kiểm tra DNS, TLS certificate và ingress route.
5. Tạo DataSource/schema và chạy migration.
6. Tạo `RegisteredClientRepository`, `OAuth2AuthorizationService`, consent service và JWK source.
7. Đăng ký component theo issuer vào registry.
8. Chạy health check/discovery check trước khi đánh dấu tenant active.

Không tạo database, key pair hoặc issuer mới ngay trong request đầu tiên đến một hostname chưa biết. Cách đó biến public routing thành provisioning API không được kiểm soát.

### 10.2. Registry thread-safe và lifecycle

Dùng cấu trúc thread-safe như `ConcurrentHashMap` cho registry. Việc thêm tenant cần kiểm tra issuer chưa tồn tại, route key chưa bị tenant khác chiếm và tất cả component đã sẵn sàng trước khi công bố tenant active.

Khi ngừng tenant:

- Chuyển trạng thái sang disabled để từ chối request mới.
- Revoke hoặc xử lý token theo chính sách hợp đồng.
- Giữ dữ liệu audit/retention theo yêu cầu.
- Gỡ route và discovery sau khi hoàn tất chuyển tiếp.
- Đóng DataSource/key resources khi không còn request đang sử dụng.

Không xóa tenant khỏi registry ngay khi bắt đầu deprovision nếu vẫn còn request đang chạy. Cần lifecycle/graceful shutdown rõ ràng.

### 10.3. Alias và đổi issuer

Issuer là định danh ổn định. Đổi domain hoặc path có thể ảnh hưởng client discovery cache, issuer validation, token `iss`, redirect URI và JWKS. Nếu cần di chuyển:

- Công bố kế hoạch issuer migration.
- Duy trì alias/redirect chỉ khi giao thức và security policy cho phép.
- Phát hành token mới với issuer mới sau khi client đã cấu hình.
- Không xác minh token bằng issuer cũ chỉ vì domain redirect sang domain mới.
- Giữ key/authorization history theo chính sách và thời hạn token.

Không âm thầm thay issuer canonical trong route registry nếu database và token cũ vẫn còn issuer trước đó.

## 11. Kiểm thử và troubleshooting

### 11.1. Ma trận kiểm thử

| ID | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| TENANT-01 | Request tới host Acme đã đăng ký | Resolve tenant Acme |
| TENANT-02 | Request tới host chưa đăng ký | Từ chối; không fallback tenant mặc định |
| TENANT-03 | Host có chữ hoa/thường khác nhau | Canonicalize theo policy và map đúng host |
| TENANT-04 | Host có hậu tố gây nhầm như `evil-login.example.com` | Không khớp allowlist `login.example.com` |
| TENANT-05 | Host có trailing dot | Xử lý theo canonicalization đã cấu hình; không tạo issuer mới |
| TENANT-06 | Host Unicode/IDN | Chuyển về ASCII IDN theo policy hoặc từ chối |
| TENANT-07 | Host có port không được đăng ký | Từ chối |
| TENANT-08 | Request dùng HTTP khi tenant chỉ cho HTTPS | Từ chối hoặc redirect ở edge theo policy; không phát hành issuer HTTP |
| TENANT-09 | Request path `/acme/oauth2/token` | Resolve Acme |
| TENANT-10 | Request path `/acme-old/oauth2/token` | Không resolve thành Acme |
| TENANT-11 | Path tenant bị thiếu | Từ chối |
| TENANT-12 | Path chứa `..` hoặc encoded slash | Bị firewall/route policy từ chối |
| TENANT-13 | Path có double slash hoặc encoding nhiều lớp | Từ chối nếu không nằm trong canonical route |
| TENANT-14 | Host và path thuộc hai tenant khác nhau | Không khớp route; từ chối |
| TENANT-15 | Client gửi `X-Forwarded-Host` giả trực tiếp | Header bị proxy xóa hoặc không được tin cậy |
| TENANT-16 | Trusted proxy ghi forwarded host đã xác minh | Request dùng đúng external host canonical |
| TENANT-17 | Proxy không xóa forwarded header từ client | Security test phát hiện cấu hình không an toàn |
| TENANT-18 | `multipleIssuersAllowed` chưa bật cho path issuers | Discovery/endpoint test phát hiện issuer path không được xử lý |
| TENANT-19 | Cấu hình issuer cố định trong mode nhiều issuer | Configuration policy test từ chối cấu hình single-issuer này |
| TENANT-20 | Discovery của Acme | Metadata `issuer` và endpoint URLs đều thuộc Acme |
| TENANT-21 | Discovery của Globex | Không trả endpoint/issuer của Acme |
| TENANT-22 | `AuthorizationServerContextHolder` không có context | Component registry fail closed |
| TENANT-23 | Issuer context không nằm trong registry | Request bị từ chối |
| TENANT-24 | Route resolver và AuthorizationServerContext có issuer khác nhau | Request bị từ chối |
| TENANT-25 | Hai tenant có cùng client ID | Lookup trả client đúng tenant |
| TENANT-26 | Acme dùng authorization ID của Globex | Không tìm thấy record ngoài tenant |
| TENANT-27 | Consent cùng principalName nhưng khác tenant | Consent không bị chia sẻ |
| TENANT-28 | JWKS Acme được truy cập | Chỉ trả public key của Acme |
| TENANT-29 | JWT Acme được xác minh bằng key Globex | Xác minh thất bại |
| TENANT-30 | Cache key giữa hai tenant có cùng user ID | Không trả dữ liệu chéo tenant |
| TENANT-31 | Async consumer xử lý message Acme | Context Acme được xác minh và dọn sau xử lý |
| TENANT-32 | Tenant bị disable | Request mới bị từ chối; request đang chạy được xử lý theo lifecycle |
| TENANT-33 | Hai request đồng thời thuộc Acme và Globex | Không chia sẻ component/context giữa request |
| TENANT-34 | Rolling deployment có registry tenant khác nhau | Readiness check ngăn node cấu hình thiếu tenant nhận traffic |
| TENANT-35 | Issuer migration | Client/token cũ và mới được xử lý theo kế hoạch migration |

### 11.2. Kiểm thử discovery và issuer

Với mỗi tenant, test:

1. Gọi discovery URL.
2. Đọc `issuer` trong metadata.
3. So sánh exact string với issuer canonical trong tenant directory.
4. Kiểm tra `authorization_endpoint`, `token_endpoint`, `jwks_uri`, revocation và introspection URLs.
5. Thực hiện một flow cấp token.
6. Decode token để kiểm tra `iss`, sau đó xác minh chữ ký bằng JWKS của chính issuer.
7. Thử xác minh token bằng tenant khác và xác nhận thất bại.

Không chỉ kiểm tra HTTP 200 của discovery. Metadata có thể trả thành công nhưng chứa issuer/endpoint sai tenant.

### 11.3. Troubleshooting

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Discovery không xuất hiện dưới path tenant | `multipleIssuersAllowed` chưa bật hoặc path prefix không đúng | Kiểm tra `AuthorizationServerSettings` và ingress rewrite |
| Issuer luôn là một URL cố định | Đã gọi `.issuer(...)` trong mode multi-issuer | Bỏ issuer cố định và kiểm tra context request |
| Issuer chứa host nội bộ | Forwarded headers chưa được xử lý đúng | Cấu hình trusted proxy và forward-header strategy |
| Issuer bị attacker điều khiển | Proxy không xóa forwarded headers hoặc host chưa allowlist | Sửa trust boundary, từ chối host lạ |
| Route `/acme` nhận `/acme-old` | So khớp path bằng `startsWith` không có segment boundary | Dùng exact/prefix boundary |
| Không tìm thấy repository theo issuer | Registry chưa đăng ký issuer canonical hoặc context chưa có | Kiểm tra provisioning và request lifecycle |
| Client Acme không tìm thấy | Client được lưu ở repository tenant khác | Kiểm tra tenant routing và DataSource |
| Authorization lookup trả dữ liệu sai tenant | Service dùng shared store nhưng thiếu tenant predicate | Sửa delegating service/query và unique key |
| JWKS trả key của tenant khác | JWK source không dùng issuer context | Delegate JWK source theo exact issuer |
| Token signature hợp lệ nhưng `iss` sai | Validator chỉ kiểm tra chữ ký/key, chưa ràng buộc issuer | Kiểm tra issuer exact và decoder configuration |
| Lỗi chỉ xuất hiện sau proxy | Host/path/port bị rewrite khác với route table | So sánh external URL và request sau proxy |
| Tenant mới chưa hoạt động trên một node | Registry provisioning không đồng bộ | Dùng readiness check và đồng bộ component trước traffic |
| Request async mất tenant context | Thread-local/request context không được truyền | Truyền tenant ID đã xác minh trong message và resolve lại |

## 12. Checklist production và tài liệu đối chiếu

### 12.1. Checklist trước production

- [ ] Tenant ID, route key và issuer canonical là các giá trị riêng biệt.
- [ ] Mọi host/path đều được đăng ký trước trong tenant directory.
- [ ] Host được so khớp chính xác; không dùng wildcard/suffix không có ranh giới DNS.
- [ ] Scheme/port được kiểm tra và issuer production dùng HTTPS.
- [ ] Path prefix được so khớp theo segment boundary.
- [ ] Path encoding, dot segment, slash/backslash và duplicate slash được xử lý nhất quán.
- [ ] `Forwarded`/`X-Forwarded-*` chỉ được tin khi proxy đã xóa header từ client và ghi lại giá trị.
- [ ] Backend không có đường truy cập trực tiếp bỏ qua trust boundary của ingress.
- [ ] `multipleIssuersAllowed(true)` được bật khi cần nhiều issuer trên cùng host.
- [ ] Không cấu hình `.issuer(...)` cố định trong mode request-derived multi-issuer.
- [ ] Discovery metadata khớp exact issuer và endpoint URLs của tenant.
- [ ] `AuthorizationServerContextHolder` được dùng trong request scope; không cache tenant vào singleton field.
- [ ] Registry lookup dùng exact issuer key và fail closed khi không có component.
- [ ] `RegisteredClientRepository`, authorization service, consent service và JWK source đều tenant-aware.
- [ ] Database/schema, cache, rate limit, audit và user directory được cô lập theo tenant.
- [ ] Signing keys và JWKS được cô lập; có quy trình rotation riêng.
- [ ] Async/background job nhận tenant ID đã xác minh và dọn context sau xử lý.
- [ ] Có test host spoofing, path traversal, issuer mismatch, cross-tenant data access và concurrent requests.
- [ ] Có quy trình provision, disable, delete và migrate issuer.
- [ ] Tất cả instance trong cluster có tenant registry/configuration nhất quán.

### Bản đồ ghi nhớ

```text
Incoming HTTP request
       |
       v
Trusted ingress / proxy
  - validate public host
  - strip untrusted forwarded headers
  - set trusted external scheme/host/prefix
       |
       v
TenantRouteResolver
  - scheme + host + port
  - path prefix boundary
  - exact route allowlist
       |
       v
Canonical tenant route
  tenantId + canonical issuer
       |
       +-------------------------------+
       |                               |
       v                               v
AuthorizationServerContext       Tenant route check
  current issuer                    exact issuer match
       |                               |
       +---------------+---------------+
                       |
                       v
             TenantComponentRegistry
                       |
        +--------------+---------------+
        |              |               |
        v              v               v
 RegisteredClient  Authorization    Consent
 Repository         Service         Service
                       |
                       v
                 Tenant JWKSource
                       |
                       v
             tenant-scoped protocol flow
```

**Điểm cần nhớ:** Tenant được chọn từ route đã provision và issuer canonical, không từ header/query tùy ý. Spring Authorization Server 1.5.8 hỗ trợ nhiều issuer trên cùng host bằng `multipleIssuersAllowed(true)` và issuer có path. Sau khi request được phân giải, mọi repository, authorization service, consent service và JWK source phải delegate theo exact issuer hiện tại. Host/path, forwarded headers, discovery metadata, cache và dữ liệu phải giữ cùng một ranh giới tenant.

## Tài liệu chuẩn để đối chiếu

- [Spring Authorization Server 1.5.8 — How-to: Implement Multitenancy](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-multitenancy.html): issuer theo path, `multipleIssuersAllowed`, `AuthorizationServerContextHolder`, component registry và các component tenant-aware.
- [Spring Authorization Server 1.5.8 — AuthorizationServerSettings API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/AuthorizationServerSettings.html): issuer và `isMultipleIssuersAllowed`.
- [Spring Authorization Server 1.5.8 — AuthorizationServerContext API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/context/AuthorizationServerContext.html): issuer được phân giải từ request hiện tại.
- [Spring Authorization Server 1.5.8 — AuthorizationServerContextHolder API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/context/AuthorizationServerContextHolder.html): truy cập request-scoped Authorization Server context.
- [Spring Boot — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/how-to/webserver.html): cấu hình `server.forward-headers-strategy`, NATIVE và FRAMEWORK.
- [Spring Framework — Forwarded Headers and ForwardedHeaderFilter](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html): xử lý `Forwarded`/`X-Forwarded-*` và security considerations.
- [Spring Security — HttpFirewall](https://docs.spring.io/spring-security/reference/servlet/exploits/firewall.html): strict firewall, path matching và request hardening.
- [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239.html): semantics của HTTP `Forwarded` header.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414.html): issuer và metadata endpoint.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): issuer identifier và validation của ID Token/UserInfo.
