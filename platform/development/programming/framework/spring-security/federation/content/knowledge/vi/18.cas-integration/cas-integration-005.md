# Đối chiếu service URL khi xác minh ticket CAS và khi triển khai sau reverse proxy

> **Bối cảnh:** Spring Security – federation · **Nhóm:** Tích hợp CAS. Tài liệu dành cho ứng dụng Spring Security dùng **CAS protocol** để đăng nhập tập trung, đặc biệt khi ứng dụng ở sau Nginx, Ingress, API Gateway, Load Balancer hoặc TLS-terminating reverse proxy. Trọng tâm là **cùng một định danh service URL phải được dùng khi CAS Server cấp Service Ticket và khi backend kiểm chứng ticket**, trong khi browser nhìn thấy URL công khai còn servlet container có thể thấy URL nội bộ. Đoạn cấu hình Spring áp dụng theo hướng Spring Boot 3.x / Spring Security 6.x Servlet, cần kiểm tra phiên bản; ví dụ Java 17 chạy độc lập để học nguyên lý.

## 1. Vấn đề: CAS phát ticket cho URL công khai, service lại xác minh bằng URL nội bộ

Một portal có public callback:

```text
https://portal.example.org/app/login/cas
```

Nhưng hệ thống thực tế:

```text
Browser HTTPS :443
      |
      v
Nginx / Kubernetes Ingress
  public /app/login/cas
      |
      | proxy HTTP, rewrite /app -> /
      v
Spring Boot pod
  http://portal-service:8080/login/cas
```

Người dùng bắt đầu CAS login với:

```text
GET https://sso.example.org/cas/login
    ?service=https%3A%2F%2Fportal.example.org%2Fapp%2Flogin%2Fcas
```

CAS Server cấp `ST-...` **cho đúng service URL công khai ấy** và đưa browser quay về:

```text
https://portal.example.org/app/login/cas?ticket=ST-example
```

Nếu backend Spring Boot lại gửi CAS validation:

```text
GET https://sso.example.org/cas/serviceValidate
    ?ticket=ST-example
    &service=http%3A%2F%2Fportal-service%3A8080%2Flogin%2Fcas
```

thì **service khi cấp ticket và service khi kiểm chứng không khớp**. CAS từ chối, thường ở dạng `INVALID_SERVICE`; một ST đã trải qua validation attempt bị **consume**, vì vậy việc sửa URL rồi retry chính `ST-example` không phải cách khắc phục. Phải cấu hình service URL nhất quán và bắt đầu **luồng login mới để nhận ST mới**.

Đây là một trong những nguyên nhân phổ biến của “CAS login loop”, “ticket not recognized”, “sau deploy Ingress thì SSO fail” hoặc “chỉ lỗi tại môi trường production”.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nêu định nghĩa **CAS service identifier** và phân biệt URL callback công khai với URL backend nội bộ.
2. Đối chiếu chính xác giá trị `service` ở **/login** và **/serviceValidate** (hoặc `/p3/serviceValidate`).
3. Hiểu quy tắc **ST chỉ dùng cho service đã phát hành và một lần kiểm chứng**, kể cả khi validation fail.
4. Phân biệt **CAS registered service regex/allowlist** với **ticket-bound service comparison**; không nới xác minh ticket chỉ để sửa deployment.
5. Cấu hình `ServiceProperties.setService(...)`, `CasAuthenticationFilter` và `CasAuthenticationEntryPoint` của Spring Security theo một **public canonical URL**.
6. Quản trị `Forwarded`, `X-Forwarded-Proto`, `X-Forwarded-Host`, `X-Forwarded-Port` và `X-Forwarded-Prefix` an toàn qua reverse proxy.
7. Debug lỗi `INVALID_SERVICE` mà không log raw tickets, TGC, cookie/session hoặc PII.
8. Viết test so sánh external/internal URL, prefix rewrite, port/query encoding, host-header spoofing, multi-node/multi-tenant và replay.
9. Sử dụng ví dụ Java 17 minh họa service binding và ticket consume.

## 2. CAS Service Ticket ràng buộc service identifier như thế nào?

Trong CAS protocol truyền thống:

- CAS **Service Ticket (ST)** là một opaque bearer credential ngắn hạn, thường có prefix `ST-`.
- User/browser xin đăng nhập bằng cách truy cập `CAS /login?service=<service-identifier>`.
- CAS Server kiểm tra service đã đăng ký, xác thực user (hoặc tái dùng TGT/TGC), rồi phát ST **chỉ dành cho service identifier đó**.
- Browser chuyển ST qua query `ticket` khi điều hướng về service URL.
- CAS service backend phải gọi `CAS /serviceValidate?service=<same-service-identifier>&ticket=<ST>`.
- CAS xác minh ST và ràng buộc với `service`, rồi trả `authenticationSuccess` hoặc `authenticationFailure`.
- Một ST **chỉ hợp lệ cho một lần thử validation**; CAS phải invalidate sau lần thử, bất kể thành công hay thất bại.

### 2.1. Quy tắc từ CAS Protocol Specification

CAS 2.0 `/serviceValidate` yêu cầu:

| Tham số | Bắt buộc? | Vai trò |
| --- | --- | --- |
| `service` | Có | **Định danh service mà ST được phát cho** |
| `ticket` | Có | ST cần kiểm chứng |
| `renew` | Không | Yêu cầu ST xuất phát từ primary credentials theo semantics CAS |
| `pgtUrl` | Không | Chỉ dùng nếu có CAS proxy authentication đúng profile |

CAS có lỗi `INVALID_SERVICE` khi ticket hợp lệ nhưng service được cung cấp khi validation **không khớp** service mà ticket được gắn lúc phát hành. CAS Protocol cũng yêu cầu invalidation ticket sau lần validation đó. Với ticket không tồn tại, hết hạn hoặc đã consume, có thể nhận `INVALID_TICKET`.

**Không cố tìm cách retry cùng ST** sau `INVALID_SERVICE`, vì retry có thể chuyển thành `INVALID_TICKET`. Sửa service config, bắt đầu login lại để lấy ST mới rồi kiểm thử.

### 2.2. “Đúng service” không phải chỉ đúng hostname

Ví dụ với service ban đầu:

```text
https://portal.example.org/app/login/cas
```

Những giá trị sau **không nên mặc định coi là tương đương** trong giao dịch CAS:

| Validation `service` | Khác gì? |
| --- | --- |
| `http://portal.example.org/app/login/cas` | Scheme HTTP thay HTTPS |
| `https://portal.example.org:8443/app/login/cas` | Port khác |
| `https://portal.example.org/login/cas` | Thiếu public path prefix `/app` |
| `https://portal-service:8080/login/cas` | Host nội bộ và port khác |
| `https://portal.example.org/app/login/cas/` | Trailing slash khác |
| `https://portal.example.org/app/LOGIN/cas` | Path case khác |
| `https://portal.example.org/app/login/cas?lang=vi` | Query bổ sung |
| `https://another.example.org/app/login/cas` | Host/service khác |

Các URI có thể tương đương ở **một số** lớp HTTP hoặc được CAS server tùy biến chuẩn hóa theo policy, nhưng không được **dựa vào sự tương đương đó để vượt service ticket binding**. Cách ổn định nhất là phát và xác minh bằng **cùng một giá trị canonical đã định nghĩa**, kiểm chứng bằng test trên **CAS Server đang deploy**.

**Phân biệt hai mức so sánh:**

1. **Registered-service matching:** CAS Server quyết định service URL có được phép yêu cầu login, thường bằng regex/literal service definition do admin cấu hình.
2. **Ticket-to-service binding:** Khi validate một ST cụ thể, CAS kiểm tra ST có được phát cho **service identifier tương ứng** không. Regex của service registry được dùng để phê duyệt service, **không tự làm ST cho /app-a có thể dùng tại /app-b**.

Một registry rule rộng không phải lời giải cho `INVALID_SERVICE`; thậm chí có thể mở đường chuyển hướng/ticket issuance tới host không được phép.

### 2.3. URL encoding và phép so sánh

Tham số `service` ở `/login` và `/serviceValidate` là **giá trị URL phải được encode khi đưa vào query**:

```text
Service identity (unencoded):
https://portal.example.org/app/login/cas

HTTP query parameter:
service=https%3A%2F%2Fportal.example.org%2Fapp%2Flogin%2Fcas
```

CAS server giải mã query để nhận service identifier. **Đừng so hai chuỗi query raw chỉ vì percent-encoding khác nhau**; so identity đã được parse đúng hoặc kiểm tra logging an toàn của component đã chuẩn hóa. Nhưng cũng không tự động “bỏ query, bỏ path, bỏ port” để làm hai identity khớp: đó có thể làm hỏng ràng buộc bảo mật.

Tránh **double encoding**:

```text
Một lần (đúng với query-parameter encoding):
https%3A%2F%2Fportal.example.org%2Fapp%2Flogin%2Fcas

Hai lần (thường sai):
https%253A%252F%252Fportal.example.org%252Fapp%252Flogin%252Fcas
```

Tùy HTTP client, bạn nên truyền **giá trị URI gốc** cho builder encode query, không vừa encode thủ công rồi để builder encode lần hai. Kiểm thử request CAS nhận được cuối cùng, không chỉ cấu hình YAML.

### 2.4. Query parameters trong callback

Nếu service callback vốn cần một query parameter cố định như `/login/cas?tenant=corp`, thì query ấy là **một phần của service identity theo chính sách**. Browser return URL có thể được CAS Server bổ sung `ticket=ST-...`; khi validate, service thường cần sử dụng identity **ban đầu chưa có ticket** chứ không sao chép toàn bộ callback query chứa `ticket` vào `service`.

Đừng làm:

```text
Issue:
service=https://portal.example.org/app/login/cas

Validate sai:
service=https://portal.example.org/app/login/cas?ticket=ST-...
```

Một số CAS clients/servers có quy tắc xử lý query parameters và service matching cụ thể. Kiểm tra implementation thực, nhất là khi ứng dụng tự dựng URL. Tránh đưa query động không cần thiết như timestamps, nonce tự phát, debug flags hoặc tracking parameters vào service identity; dùng request cache/state được kiểm soát cho URL protected ban đầu.

## 3. Sơ đồ đầy đủ qua reverse proxy

```text
Browser                   Reverse Proxy / Ingress        Spring Boot Pod       CAS
   | HTTPS portal.example.org/app/login/cas             |                 |
   |---------------------------->|                     |                 |
   |                             | HTTP portal:8080    |                 |
   |                             | /login/cas          |                 |
   |                             |-------------------->|                 |
   |                             |                     |                  |
   | 302 đến CAS /login?service=https://portal.example.org/app/login/cas |
   |<----------------------------|<--------------------|                 |
   |------------------------------------------------------------------->|
   |             CAS xác thực, cấp ST cho PUBLIC service URL           |
   |<-------------------------------------------------------------------|
   | 302 tới https://portal.example.org/app/login/cas?ticket=ST-...    |
   |---------------------------->|                     |                 |
   |                             | GET /login/cas      |                 |
   |                             |-------------------->|                 |
   |                             |                     |                 |
   |                             |  Backend CAS /serviceValidate?      |
   |                             |   service=PUBLIC URL&ticket=ST-...  |
   |                             |                     |--------------->|
   |                             |                     |<---------------|
   |                             |             authenticationSuccess    |
   |             Spring tạo local SecurityContext/session              |
   |<----------------------------|<--------------------|                 |
```

**Chú ý:** Ngay cả khi CAS validation đi từ pod qua mạng nội bộ tới CAS Server, **giá trị tham số `service` vẫn là public callback URL**, không phải địa chỉ nội bộ pod và không phải URL backend của CAS Server.

### 3.1. Ba địa chỉ không thể thay nhau

| Thành phần | Ví dụ | Công dụng |
| --- | --- | --- |
| **CAS Server base URL** | `https://sso.example.org/cas` | Nơi CAS service gọi `/serviceValidate` và browser được redirect tới `/login` |
| **Public CAS service URL** | `https://portal.example.org/app/login/cas` | Định danh service để CAS phát và validate ST |
| **Internal upstream URL** | `http://portal-service:8080/login/cas` | Nơi proxy gửi request đến Spring servlet |

Sai lầm thường gặp: đưa CAS Server base URL vào `ServiceProperties.setService`, hoặc đưa internal upstream vào tham số `service` khi validate ST.

### 3.2. Browser và backend kiểm tra ở hai phía

Browser nhìn được redirect `Location` và callback URL có `ticket`; backend Spring Security gọi CAS `/serviceValidate` qua **server-to-server backchannel**. DevTools browser có thể **không** hiển thị request validation bởi nó do backend thực hiện.

Để debug, cần hai loại quan sát không lộ secrets:

- Frontchannel: public CAS login redirect + callback path trên browser, nhưng **che `ticket`**.
- Backchannel: CAS validation result/`service` identity ở dạng normalized diagnostic, không log raw ticket hoặc full query.

## 4. Các nguồn sai khác do reverse proxy

### 4.1. TLS termination làm scheme đổi

```text
Browser: https://portal.example.org
    |
TLS terminated by Nginx/Ingress
    |
Backend: http://portal-service:8080
```

Nếu Spring tự lấy `HttpServletRequest.getScheme()` ở backend mà không xử lý trusted forwarded headers, nó có thể tạo `http://...` trong service URL hoặc redirects. CAS đã cấp ST cho `https://...` nên validation mismatch.

**Cách sửa:** ưu tiên cấu hình **canonical public service URL cố định** cho `ServiceProperties`. Đồng thời cấu hình forwarded-header handling an toàn cho redirects/absolute URLs nếu framework cần tạo đường dẫn khác. Không giả mạo HTTPS bằng cách thay CAS validator thành “bỏ scheme”.

### 4.2. Proxy thay Host

Nhiều reverse proxies gửi upstream với Host nội bộ:

```text
Public Host: portal.example.org
Upstream Host: portal-service
```

Nếu lấy host từ request phía servlet, service URL thành `portal-service`. Ngược lại, nếu proxy sao chép nguyên Host từ browser mà không kiểm tra allowlist, attacker có thể thao túng link/redirect và `service`.

**Giải pháp:** proxy có server_name/host routing cụ thể, chỉ chấp nhận các Host đã cho phép, strip/overwrite forwarded headers và gửi host công khai **đã xác minh**. Ứng dụng nên dùng public URI từ config quản trị, không coi mọi `Host`/`X-Forwarded-Host` là danh tính dịch vụ đáng tin.

### 4.3. Path prefix và rewrite

Ví dụ bên ngoài công khai `/app/login/cas` nhưng upstream servlet path là `/login/cas`:

```text
Public:  https://portal.example.org/app/login/cas
Ingress: rewrite /app -> /
Backend: http://portal-service:8080/login/cas
```

Nếu service URL thiếu `/app` khi validate sẽ mismatch. Nếu cả application context path và `X-Forwarded-Prefix` đều thêm `/app` có thể tạo **/app/app/login/cas**.

Phải chọn đúng **một** chiến lược path:

- App thực sự chạy với `server.servlet.context-path=/app` và ingress giữ prefix; hoặc
- Proxy rewrite bỏ prefix, app chạy root context, trong khi **canonical public service URL** vẫn có `/app`.

Đừng kết hợp cả hai một cách tình cờ. Test cả `Location` redirect, URL CAS nhận và callback mà filter thực sự bắt.

### 4.4. Port mismatch

`https://portal.example.org/app/login/cas` và `https://portal.example.org:443/app/login/cas` có thể tương đương ở một số URI/HTTP contexts nhưng không nên giả định CAS service matching chuẩn hóa giống nhau theo mọi release.

**Chiến lược đơn giản:** dùng một canonical URL cố định, không tự chuyển đổi port tùy request. Khi ghi service registry và các probes, dùng cùng representation; nếu có custom port như 8443, khai báo rõ ở mọi bên.

### 4.5. Context path, servlet mapping và filter URL

`CasAuthenticationFilter` thường xử lý URL `/login/cas` trong service app. Với proxy rewrite, browser vào `/app/login/cas` nhưng servlet filter có thể thấy path `/login/cas`. Điều đó **không mâu thuẫn** nếu cấu hình đúng:

- CAS `service` công khai: `https://portal.example.org/app/login/cas`.
- CAS filter local process URL: `/login/cas`.
- Proxy chuyển `/app/login/cas` tới `/login/cas`.
- `ServiceProperties.service` vẫn bằng **public** URL.

Không đổi `CasAuthenticationFilter.filterProcessesUrl` sang public full URL; matcher filter sử dụng local servlet request path, không một URL đầy đủ. Chỉ đổi local path khi app routing thực sự yêu cầu.

## 5. Giải pháp ưu tiên: một public canonical service URL từ cấu hình

Với một ứng dụng CAS service có callback cố định, cách ổn định nhất là **chỉ định giá trị service URL duy nhất** trong config kiểm soát bởi vận hành:

```yaml
# application.yml: custom application properties, KHÔNG phải
# auto-config mặc định của Spring Security CAS.
cas-client:
  server-base-url: "https://sso.example.org/cas"
  public-service-url: "https://portal.example.org/app/login/cas"

# Chỉ bật forwarded header parsing khi ingress/proxy thật sự
# loại bỏ/sinh lại headers và có boundary đáng tin.
server:
  forward-headers-strategy: framework
```

Hai khóa `cas-client.*` là **custom properties** của ứng dụng: muốn dùng phải bind vào bean hoặc đọc qua configuration class. Đừng tưởng Spring Boot tự cấu hình CAS login bằng các khóa này.

### 5.1. ServiceProperties cố định theo external URL

Tạo `CasPublicServiceConfiguration.java`:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.cas.ServiceProperties;

@ConfigurationProperties(prefix = "cas-client")
record CasClientSettings(
        String serverBaseUrl,
        String publicServiceUrl) {}

@Configuration
@EnableConfigurationProperties(CasClientSettings.class)
public class CasPublicServiceConfiguration {

    @Bean
    ServiceProperties serviceProperties(CasClientSettings settings) {
        String publicServiceUrl = settings.publicServiceUrl();

        // Việc kiểm tra URI chặt hơn nên làm khi bootstrap:
        if (!publicServiceUrl.startsWith("https://")) {
            throw new IllegalArgumentException(
                    "CAS public service URL must be HTTPS");
        }

        ServiceProperties service = new ServiceProperties();
        service.setService(publicServiceUrl);
        service.setSendRenew(false);
        return service;
    }
}
```

Đây là **class cấu hình Spring Boot 3.x**, không phải chương trình chạy riêng bằng `javac`. Cần `spring-security-cas` tương thích, auto-bind configuration properties, Spring Boot/Security beans và các thành phần CAS client còn lại. Spring Boot sẽ bind `server-base-url` và `public-service-url` sang record fields tương ứng khi cấu hình đúng.

**Lưu ý bảo mật:** `startsWith("https://")` chỉ là kiểm tra sơ bộ trong ví dụ, **không thay URI parser/hostname allowlist/không có userinfo/port policy**. Trong ứng dụng thật, validate bằng `URI` và một danh sách callback cho phép theo môi trường. Giá trị phải đến từ cấu hình được quản lý, không từ query `service` của browser.

Điểm quan trọng nhất ở đây là `ServiceProperties.setService("https://portal.example.org/app/login/cas")`. Thành phần này được `CasAuthenticationEntryPoint` sử dụng khi redirect tới CAS, và được `CasAuthenticationFilter`/provider sử dụng khi xác minh ST trong flow CAS service ticket thông thường.

### 5.2. CAS Server URL khác ServiceProperties.service

Trong configuration class khác, CAS login entry point dùng **CAS Server base URL**:

```java
import org.springframework.security.cas.ServiceProperties;
import org.springframework.security.cas.web.CasAuthenticationEntryPoint;

// Fragment, cần beans đã khai báo từ Spring.
CasAuthenticationEntryPoint entryPoint =
        new CasAuthenticationEntryPoint();

entryPoint.setLoginUrl("https://sso.example.org/cas/login");
entryPoint.setServiceProperties(serviceProperties);
```

Trong fragment, biến `serviceProperties` là instance bean ở mục trước. Entry point sẽ tạo redirect CAS login với query `service=PUBLIC_URL`. Không ghi internal upstream URL và không gửi ST đi validate qua browser.

### 5.3. CasAuthenticationFilter và callback matcher

`CasAuthenticationFilter` thường nghe local `/login/cas`:

```java
import org.springframework.security.cas.web.CasAuthenticationFilter;

// Fragment: authenticationManager là Spring AuthenticationManager
// đã gắn CasAuthenticationProvider tương thích.
CasAuthenticationFilter filter = new CasAuthenticationFilter();
filter.setFilterProcessesUrl("/login/cas");
filter.setAuthenticationManager(authenticationManager);
```

**Tách hai chuỗi:** `filterProcessesUrl=/login/cas` là **local servlet route**, trong khi `serviceProperties.service=https://portal.example.org/app/login/cas` là **external CAS callback identifier**.

Nếu app có `server.servlet.context-path=/app` và ingress không rewrite, matcher local vẫn theo logic servlet context path; phải kiểm tra framework thực nhận `servletPath`. Không tự đưa `/app/app/login/cas` vào service URL.

### 5.4. CasAuthenticationProvider và TicketValidator

Spring Security dùng `CasAuthenticationProvider` kết hợp một CAS client `TicketValidator`. Ví dụ fragment:

```java
import org.apereo.cas.client.validation.Cas20ServiceTicketValidator;
import org.springframework.security.cas.ServiceProperties;
import org.springframework.security.cas.authentication.CasAuthenticationProvider;

// Fragment: userDetailsService và serviceProperties là beans đã
// được cấu hình trong ứng dụng, không phải code runnable độc lập.
Cas20ServiceTicketValidator validator =
        new Cas20ServiceTicketValidator("https://sso.example.org/cas");

CasAuthenticationProvider provider = new CasAuthenticationProvider();
provider.setServiceProperties(serviceProperties);
provider.setTicketValidator(validator);
provider.setKey("portal-cas-provider-v1");

// Còn cần authenticationUserDetailsService / user-authority mapping
// theo API Spring Security của release hiện dùng.
```

`Cas20ServiceTicketValidator` biết CAS server base URL để gọi `/serviceValidate`. `CasAuthenticationProvider` phải nhận đúng `ServiceProperties`, validator và cách lấy/mapping user details/authorities. Chỉ kiểm tra username sau CAS success, không dùng raw ticket query hay arbitrary browser data để tạo principal.

**Không nhầm:** nếu một trong entry point/filter/provider sử dụng service URL khác với phần còn lại, lỗi vẫn có thể xảy ra dù bean ServiceProperties nhìn qua “đúng”.

### 5.5. Một sơ đồ Spring Security dễ nhớ

```text
Unauthorized GET /orders
       |
       v
CasAuthenticationEntryPoint
       |
       +--> CAS /login?service=PUBLIC_CALLBACK
                |
                v
        Browser CAS login / existing SSO
                |
                v
        GET PUBLIC_CALLBACK?ticket=ST-...
                |
         Reverse proxy rewrite
                |
                v
        CasAuthenticationFilter at local /login/cas
                |
                v
        AuthenticationManager
                |
                v
        CasAuthenticationProvider
                |
                v
        Cas20ServiceTicketValidator
                |
                +--> backend HTTPS CAS /serviceValidate
                    ?service=THE_SAME_PUBLIC_CALLBACK
                    &ticket=ST-...
                |
                v
        CAS authenticationSuccess -> principal
                |
                v
        Spring SecurityContext + local session
```

Đây là **CAS protocol**, không dùng `saml2Login()` để xử lý ST. CAS native service ticket khác SAML Assertion/Response. Ngoài ra “reverse proxy” ở chủ đề này là proxy HTTP đứng trước app, **không phải CAS Proxy Ticket (PT/PGT)**; `Cas20ProxyTicketValidator` và `pgtUrl` là chủ đề ủy quyền backend riêng.

## 6. Forwarded headers: tính đúng URL mà không tin attacker

### 6.1. Những header thường gặp

| Header | Mục đích thường gặp | Rủi ro nếu tin header do client tự gửi |
| --- | --- | --- |
| `Forwarded: proto=https;host=portal.example.org` | RFC 7239 ghi nhận scheme/host ban đầu | Attacker giả host/protocol |
| `X-Forwarded-Proto: https` | HTTPS public khi upstream HTTP | Spoof scheme, tạo URL sai |
| `X-Forwarded-Host: portal.example.org` | Host external | Host-header injection/open redirect/service confusion |
| `X-Forwarded-Port: 443` | Port external | Port mismatch và redirect bất thường |
| `X-Forwarded-Prefix: /app` | Public path được proxy rewrite | Prefix injection/double prefix |
| `X-Forwarded-For` | Client IP chain | IP spoof/rate-limit bypass nếu trust sai |

**Rule quan trọng:** chỉ xử lý forwarded headers do **trusted proxy** tạo ra. Proxy ở ranh giới Internet phải **xóa bản sao do client gửi**, sau đó **thiết lập giá trị đúng từ ingress routing đã được kiểm soát**. Spring Framework docs nhấn mạnh không thể tự biết header được proxy thêm hay attacker tự đưa; phải thiết lập trust boundary tại edge.

### 6.2. Một mẫu proxy Nginx minh họa

Đoạn sau giả định Nginx là **ingress duy nhất** cho host cụ thể `portal.example.org`; TLS được cấu hình ở Nginx và backend chỉ nhận traffic nội bộ từ proxy. Đây là **fragment topology**, không phải cấu hình Nginx đầy đủ để copy vào Internet; cần server block TLS, certificate, logging và host rejection rõ ràng.

```nginx
# Nằm trong server block đã giới hạn server_name portal.example.org
# và listen 443 ssl. Không cho traffic internet bypass proxy.
location /app/ {
    # Dấu "/" cuối khiến prefix /app/ được thay bằng "/".
    # Public /app/login/cas -> upstream /login/cas.
    proxy_pass http://portal-service:8080/;

    # Header external được đặt cố định/đã xác minh theo vhost.
    proxy_set_header Host portal.example.org;
    proxy_set_header X-Forwarded-Host portal.example.org;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Port 443;
    proxy_set_header X-Forwarded-Prefix /app;

    # Không proxy raw Forwarded/Host do client tự tạo như trust source.
    # Edge security còn cần strip incoming forwarded variants.
}
```

**Điều cần kiểm thử riêng:** Nginx config khác có `proxy_pass http://portal-service:8080;` (không dấu slash cuối) sẽ có semantics rewrite khác; Kubernetes ingress-nginx dùng regex/rewrite-target annotations thay vì cấu hình này. Kiểm tra **actual upstream path** bằng routing test. Một snippet không thay ingress ownership, TLS termination, header sanitation hoặc host allowlisting.

**Không đủ** chỉ đặt `X-Forwarded-Host` bằng `$http_host` do browser gửi rồi bật Spring trust. Nếu edge cho Host lạ/Forwarded spoofed, app có thể phát redirect/ticket service URL sang host do attacker điều khiển.

### 6.3. Spring Boot xử lý forwarded headers

Trong Spring Boot (Servlet):

```yaml
server:
  forward-headers-strategy: framework
```

`FRAMEWORK` sử dụng Spring framework-level forwarded header support như `ForwardedHeaderFilter` theo environment; `NATIVE` cho container-level handling; `NONE` bỏ qua. Lựa chọn tùy runtime/ingress. **Không đồng thời cài nhiều bộ rewrite** để cùng chỉnh request URL hai lần; hãy thử cả redirect URLs và callback matching.

**Tuy nhiên:** bật `server.forward-headers-strategy=framework` chỉ nên làm khi ingress đã loại bỏ header giả và đặt header thật. Nó **không tự tạo trust boundary**, không tự kiểm tra CAS service identity và không tự bảo đảm metadata/cookie session an toàn.

Trong nhiều trường hợp một `ServiceProperties.service` **cố định và đúng public URL** giải quyết CAS binding dễ hơn việc dựng URL động từ request. Forwarded headers vẫn quan trọng cho redirects/cookie Path/Secure, nhưng bạn không nên để CAS service identifier bị thay đổi dựa trên input Host của browser.

### 6.4. ForwardedHeaderFilter và thứ tự filter

Nếu tự cấu hình `ForwardedHeaderFilter`, phải đảm bảo thứ tự trước các components cần đọc URL đã sửa, và không lặp với Boot auto-config `server.forward-headers-strategy`. Spring Framework docs cũng có `removeOnly` mode để **loại header không tin** mà không sử dụng chúng.

Việc đặt Filter sai thứ tự có thể khiến:

- CAS entry point xây redirect bằng URI cũ;
- CAS provider validate bằng URI khác;
- Application absolute links mang internal hostname;
- Callback được route đến sai context path.

Kiểm tra behavior ở **runtime**, không chỉ code config: cùng một request khi qua proxy phải nhìn thấy external scheme/host/prefix đã xác minh theo một cách nhất quán.

### 6.5. X-Forwarded-Prefix cần cẩn trọng

Một số ingress strip `/app` trước upstream rồi thêm `X-Forwarded-Prefix: /app`. Nếu app lại có context-path `/app`, Spring có thể sinh absolute URL với prefix kép. Nếu ingress không strip prefix mà app vẫn tự thêm forwarded prefix, cũng có nguy cơ sai.

**Quyết định trước:** external path, upstream path, servlet context path, forwarded prefix handling và `ServiceProperties.service`. Vẽ bảng mapping rồi test, không sửa theo cảm giác.

## 7. Bảng contract URL trước khi triển khai

Với topology ví dụ, một bảng contract rõ ràng nên có:

| Trường | Giá trị chuẩn |
| --- | --- |
| Browser external origin | `https://portal.example.org` |
| Public CAS service callback | `https://portal.example.org/app/login/cas` |
| CAS Server login URL | `https://sso.example.org/cas/login` |
| CAS Server validation URL | `https://sso.example.org/cas/serviceValidate` |
| Backend listener | `http://portal-service:8080` |
| Browser public callback path | `/app/login/cas` |
| Backend servlet callback path | `/login/cas` |
| Proxy rewrite | `/app/` → `/` |
| Spring Security filterProcessesUrl | `/login/cas` |
| Spring ServiceProperties.service | `https://portal.example.org/app/login/cas` |
| CAS registered service | Chỉ cho phép public callback này hoặc pattern hẹp tương đương |
| Validation request service value | **Giống hệt** `ServiceProperties.service` |
| IdP/CAS trusted TLS connection | Backend → `https://sso.example.org/cas` có xác minh CA/hostname |

Bảng contract này là tài liệu vận hành quan trọng. Khi đổi domain, prefix hoặc port, phải cập nhật đồng bộ **service registry của CAS**, **ServiceProperties của client**, **ingress route** và **tests**. Không thay chỉ một nơi.

### 7.1. Mẫu khác: ứng dụng có context path thực

Nếu app được cấu hình:

```yaml
server:
  servlet:
    context-path: /app
```

và ingress chuyển tiếp nguyên `/app/login/cas` (không rewrite), callback public vẫn `https://portal.example.org/app/login/cas` nhưng local routing/context path khác mẫu trên. Không đồng thời strip `/app` và để app đòi `context-path=/app` trừ khi có rule chủ động phục hồi path; callback có thể 404 trước khi tới `CasAuthenticationFilter`.

## 8. CAS registered service matching không phải ticket validation matching

Apereo CAS service registry có thể dùng `serviceId` regex, literal hoặc strategy khác để xác định **ứng dụng được phép**:

```text
Registered service (admin-defined):
  https://portal.example.org/app/login/cas

Ticket issued for:
  https://portal.example.org/app/login/cas

Validation service:
  https://portal.example.org/app/login/cas
```

Ở một số CAS versions, service registry dùng **full regex matching** với anchors mặc định; quản trị viên có thể định nghĩa literal match. Nhưng **matching registry** và **binding của ST cụ thể** là hai kiểm tra riêng.

### 8.1. Ví dụ cấu hình registry minh họa

```json
{
  "@class": "org.apereo.cas.services.CasRegisteredService",
  "serviceId": "https://portal[.]example[.]org/app/login/cas",
  "name": "Portal CAS Client",
  "id": 1201
}
```

Đây là **ý tưởng JSON cho một Apereo CAS registered service**, không cam kết schema đủ cho CAS release hiện có hoặc các service policies khác. Cách encode regex, matchingStrategy, evaluationOrder, access strategy và service registry backend phụ thuộc phiên bản. Nếu lựa chọn **literal matching strategy**, có thể cấu hình literal URI thay regex; hãy kiểm tra docs phiên bản deploy.

Đừng mở:

```text
https://.*
http[s]?://.*
.*login/cas.*
```

Một rule quá rộng có thể cho attacker đăng ký/đưa browser đến một URL ngoài phạm vi hợp đồng hoặc nhận ticket không mong muốn. Cấu hình CAS server càng rộng, rủi ro open redirect/service enrollment/credential flow càng lớn.

### 8.2. Vì sao không sửa CAS ServiceMatchingStrategy để “bỏ host”?

CAS Server hiện đại có cơ chế tùy biến service matching; tuy nhiên việc viết strategy coi mọi scheme/host/path là tương đương để sửa lỗi proxy làm suy yếu mục tiêu **ST chỉ dành cho service được cấp**. Một ST bị lộ từ service A có thể bị chấp nhận ở service B nếu matcher quá rộng.

**Sửa upstream contract** trước: ServiceProperties, Ingress, registry và callback URL. Nếu có nhu cầu thật về alias URLs hoặc migration domain, thiết kế **danh sách alias đã duyệt**, thời hạn, mapping rõ, kiểm thử tách tenant và đánh giá an toàn; không bỏ host trong mọi trường hợp.

### 8.3. CAS proxy server vs HTTP reverse proxy

Tên có thể gây nhầm:

- **HTTP reverse proxy:** Nginx/Ingress đứng trước Portal, làm TLS termination, path rewrite và forwarded headers. Đó là chủ đề bài này.
- **CAS proxy authentication:** PGT/PT, `/proxy`, `/proxyValidate`, `pgtUrl` cho delegated backend calls. Đó là tính năng **protocol khác**.

Không dùng `Cas20ProxyTicketValidator` chỉ vì ứng dụng ở sau Nginx. Một CAS service ticket login truyền thống vẫn dùng `Cas20ServiceTicketValidator` hoặc validator CAS 3.0 phù hợp attributes, không tự chuyển sang proxy tickets.

## 9. HTTP transcripts: đúng và sai

### 9.1. Luồng đúng

```http
# Frontchannel: Browser → CAS Server
GET /cas/login?service=https%3A%2F%2Fportal.example.org%2Fapp%2Flogin%2Fcas HTTP/1.1
Host: sso.example.org

# CAS Server → Browser (vé ví dụ, không phải ST thật)
HTTP/1.1 302 Found
Location: https://portal.example.org/app/login/cas?ticket=ST-DEMO

# Browser → Proxy → Portal callback
GET /app/login/cas?ticket=ST-DEMO HTTP/1.1
Host: portal.example.org

# Backend Portal → CAS Server, qua HTTPS
GET /cas/serviceValidate?service=https%3A%2F%2Fportal.example.org%2Fapp%2Flogin%2Fcas&ticket=ST-DEMO HTTP/1.1
Host: sso.example.org
```

CAS Server trả `authenticationSuccess`, sau đó Spring tạo local authenticated session. Nếu ứng dụng cần trả user về `/dashboard`, dùng saved request/safe redirect (không cần đưa protected original path làm service identifier).

### 9.2. Luồng sai do internal URL

```http
# Backend dùng host/proto/path nội bộ, khác ST binding:
GET /cas/serviceValidate?service=http%3A%2F%2Fportal-service%3A8080%2Flogin%2Fcas&ticket=ST-DEMO HTTP/1.1
Host: sso.example.org
```

CAS có thể trả:

```xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationFailure code="INVALID_SERVICE">
    Service mismatch
  </cas:authenticationFailure>
</cas:serviceResponse>
```

XML chỉ là **ví dụ mô phỏng**, không thể dùng để tự giả mạo CAS response. Không log full exception vì các CAS servers có thể đưa ticket hoặc service chi tiết vào mô tả lỗi.

### 9.3. Sau INVALID_SERVICE, làm gì?

1. Xác định service URL **đã phát ST**: từ CAS entry-point config hoặc CAS audit đã redacted; không lưu ST.
2. Xác định service URL **client dùng khi validate**: từ `ServiceProperties`/provider hoặc telemetry nội bộ đã làm sạch.
3. So sánh scheme, host, port, path, prefix, query và URL encoding.
4. Sửa **cấu hình** ở client/proxy/registry, không sửa ticket.
5. Bắt đầu **login transaction mới**; không replay ST cũ.
6. Chạy test cả đúng/sai service, expired ST và multi-node callback.

Không bật validation “trust all tickets”, bỏ `service` param, hoặc nhờ CAS accept mọi host để giữ tỷ lệ đăng nhập.

## 10. Java 17: mô phỏng service-binding và reverse-proxy mismatch

Chương trình sau chạy bằng **JDK 17+ thuần**, không có Spring/CAS dependency. Nó mô phỏng CAS Server phát ST với một `serviceUrl` và kiểm chứng bằng **exact identity match**. Mỗi validation attempt **consume ticket trước khi so sánh**. Bài test cho thấy dùng internal URL sẽ bị reject; retry ST ấy bằng public URL cũng fail; chỉ một **ST mới** với đúng public URL mới thành công.

**Đây không phải CAS Server thật:** ticket strings là giá trị giả, không đủ entropy/TTL; không có password, MFA, CAS TGT/TGC, HTTPS, XML validation hay session. Chỉ mô phỏng quan hệ service identity và one-time ticket.

Lưu file `CasServiceUrlContractDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

public class CasServiceUrlContractDemo {

    private static final String PUBLIC_SERVICE =
            "https://portal.example.org/app/login/cas";
    private static final String INTERNAL_SERVICE =
            "http://portal-service:8080/login/cas";

    record Ticket(String serviceUrl, String username) {}

    static class MockCasServer {
        private final Map<String, Ticket> tickets = new HashMap<>();
        private int nextId = 1;

        String issue(String serviceUrl, String username) {
            String id = "ST-" + nextId++;
            tickets.put(id, new Ticket(serviceUrl, username));
            return id;
        }

        String validate(String ticketId, String serviceUrl) {
            // CAS service tickets are one-attempt credentials.
            Ticket issued = tickets.remove(ticketId);
            if (issued == null || !issued.serviceUrl().equals(serviceUrl)) {
                return "REJECT";
            }
            return "AUTH:" + issued.username();
        }
    }

    static boolean allowedPublicCallback(String candidate) {
        // Simulates a configured allowlist, NOT parsing proxy headers.
        return Set.of(PUBLIC_SERVICE).contains(candidate);
    }

    public static void main(String[] args) {
        MockCasServer cas = new MockCasServer();

        System.out.println("Public callback: " + PUBLIC_SERVICE);
        System.out.println("Internal equals public: "
                + PUBLIC_SERVICE.equals(INTERNAL_SERVICE));

        String first = cas.issue(PUBLIC_SERVICE, "alice");
        System.out.println("Wrong internal validation: "
                + cas.validate(first, INTERNAL_SERVICE));
        System.out.println("Retry same ticket: "
                + cas.validate(first, PUBLIC_SERVICE));

        String second = cas.issue(PUBLIC_SERVICE, "alice");
        System.out.println("Canonical public approved: "
                + allowedPublicCallback(PUBLIC_SERVICE));
        System.out.println("Correct validation: "
                + cas.validate(second, PUBLIC_SERVICE));
        System.out.println("Replay after success: "
                + cas.validate(second, PUBLIC_SERVICE));

        String spoofed = "https://evil.example/app/login/cas";
        System.out.println("Spoofed forwarded host approved: "
                + allowedPublicCallback(spoofed));

        String reports = "https://reports.example.org/login/cas";
        String third = cas.issue(PUBLIC_SERVICE, "alice");
        System.out.println("Other service validation: "
                + cas.validate(third, reports));
    }
}
```

Biên dịch và chạy:

```bash
javac CasServiceUrlContractDemo.java
java CasServiceUrlContractDemo
```

Stdout **chính xác**:

```text
Public callback: https://portal.example.org/app/login/cas
Internal equals public: false
Wrong internal validation: REJECT
Retry same ticket: REJECT
Canonical public approved: true
Correct validation: AUTH:alice
Replay after success: REJECT
Spoofed forwarded host approved: false
Other service validation: REJECT
```

### 10.1. Giải thích từng kết quả

- `Public callback` là external service identity đã chốt.
- `Internal equals public=false`: upstream HTTP/host/path không thể dùng thay external URL.
- `Wrong internal validation=REJECT`: CAS ST được phát cho URL public không được nhận với service nội bộ.
- `Retry same ticket=REJECT`: một validation attempt sai đã consume ST; sửa URL mà replay ticket không giúp.
- `Canonical public approved=true`: public URL nằm trong allowlist cố định của ứng dụng demo.
- `Correct validation=AUTH:alice`: ST **mới** cho public URL được validate với đúng cùng identity.
- `Replay after success=REJECT`: ST đã dùng không thể xác thực lần nữa.
- `Spoofed forwarded host approved=false`: hostname ngoài allowlist không được chọn làm service identity.
- `Other service validation=REJECT`: ST của Portal không được xác minh như ticket cho Reports.

### 10.2. Ranh giới của ví dụ

`MockCasServer.issue` chấp nhận mọi URL và username vì đây là mô hình lớp học; CAS thật phải có **registered service allowlist**, authentication handlers và session TGT/TGC. `allowedPublicCallback` chỉ minh họa allowlist, không phải cách parse/verify `Forwarded` headers trong môi trường thật. `HashMap` không an toàn cho CAS cluster và chưa có TTL/secure random; production cần ticket registry với atomic consume và timeouts.

Không sao chép hàm `validate` làm CAS client production: client đúng phải gọi trusted CAS Server `/serviceValidate` qua HTTPS, xử lý `authenticationFailure` XML và chỉ sau success mới tạo `Authentication`/local session.

## 11. Kiểm thử contract trong Spring Security

### 11.1. Ba kiểm tra chính

Một integration test CAS service URL sau proxy nên xác nhận đồng thời:

**A. Issue:** browser được 302 tới CAS Server `/login`; tham số `service` sau URL-decode đúng bằng `https://portal.example.org/app/login/cas`.

**B. Callback routing:** khi browser truy cập `https://portal.example.org/app/login/cas?ticket=...`, proxy đưa request tới local `CasAuthenticationFilter` ở `/login/cas`, không bị 404/403/redirect loop.

**C. Validate:** backend gọi CAS `/serviceValidate` (hoặc `/p3/serviceValidate`) với tham số `service` **đúng identity A** và ST tương ứng; CAS trả result đúng. Không cần browser trực tiếp thấy backchannel request.

### 11.2. MockWebServer/WireMock hoặc CAS test server

Có thể cấu hình một **CAS test server** để capture:

```text
GET /cas/login?...service=PUBLIC_CALLBACK...
GET /cas/serviceValidate?...service=PUBLIC_CALLBACK&ticket=TEST_ST...
```

Chỉ dùng `TEST_ST` hoặc fixture giả; không lưu tickets thật. Nếu dùng mock CAS validation response, phân biệt **unit test request construction** với **security integration test**: mock trả success không chứng minh CAS Server thật đã enforce ticket service binding, one-time consume, trusted transport và service registry rules.

Với integration test thật, dùng Apereo CAS test deployment cùng service definitions tương thích, kiểm tra:

1. CAS cấp ST cho public callback.
2. Backend xác minh với đúng service → success.
3. ST dành cho public callback bị validate bằng internal URL → `INVALID_SERVICE`.
4. Retry ST đã thất bại → `INVALID_TICKET` hoặc reject tương đương.
5. ST dành cho Portal đem validate với Reports URL → reject.
6. Unknown external service URL → CAS registry reject.
7. Mọi request có forwarded headers giả → không thể điều khiển public callback identity.

### 11.3. Test proxy headers có kiểm soát

| Request scenario | Expected public callback behavior |
| --- | --- |
| HTTPS public, proxy strip /app | App dùng đúng `https://portal.example.org/app/login/cas` |
| TLS terminates, backend HTTP | Không xuất hiện `http://portal-service:8080` trong `service` |
| `X-Forwarded-Proto=https` từ trusted proxy | Absolute URLs đúng sau sanitation |
| Client tự gửi `X-Forwarded-Host=evil.example` | Edge strip/overwrite, không đổi CAS service |
| Client tự gửi `Forwarded: host=evil.example;proto=http` | Edge strip hoặc overwrite, không đổi CAS service |
| Client tự gửi `X-Forwarded-Prefix=/evil` | Không làm callback thành `/evil/login/cas` |
| Host header không trong allowed vhost | Ingress reject, không phát CAS redirect |
| Proxy thiếu `X-Forwarded-Prefix` trong topology cần prefix | Test phát hiện mất `/app`; sửa routing |
| App context-path=/app cùng ingress rewrite /app | Test phát hiện 404/double prefix |
| Thay `proxy_pass` có/không trailing slash | Test capture actual upstream path |
| Default port 443 so với `:443` trong URL | Test expected canonical representation |
| Callback có query `lang=vi` | So đúng service identity nếu query là phần hợp đồng |
| Query bị double URL-encode | Test phát hiện CAS nhận service identity sai |
| Nhiều pods có service URL config khác nhau | Test fail, không coi IdP outage |

### 11.4. Các assertions cần chạy liên tục trong CI

- CAS redirect `service` là **HTTPS public callback**, không phải internal host.
- Callback `ticket` không xuất hiện trong `service` gửi tới validator (trừ khi có profile/URI identity được thiết kế khác và xác thực).
- `ServiceProperties.service` là same string ở các CAS components và tất cả pods.
- Local `CasAuthenticationFilter.filterProcessesUrl` match đúng callback path sau proxy rewrite.
- CAS Server service registry không cho phép wildcard host trái security policy.
- Sai service, expired ticket, reused ticket đều **không tạo Spring Authentication**.
- Khi CAS Server không reachable/TLS sai, app fail closed.
- Session chỉ được tạo sau ticket validation success, không từ prefix `ST-` hoặc browser query username.
- Callback success chuyển tới URL sạch không giữ raw ST.
- Logs/APM/WAF/nginx không thu raw `ticket`, CAS session TGC/cookies hoặc nguyên validation URL.

## 12. Troubleshooting: phân biệt mismatch với các lỗi khác

| Triệu chứng | Lỗi/thành phần nghi ngờ | Kiểm tra |
| --- | --- | --- |
| CAS báo `INVALID_SERVICE` ngay ở lần validate đầu | Issue service khác validation service | So sánh scheme/host/port/path/query, không retry ST |
| Sau sửa URL, retry cùng ST thành `INVALID_TICKET` | ST đã bị consume ở lần đầu | Bắt đầu CAS login mới |
| Redirect CAS quay về `http://internal:8080/...` | EntryPoint/serviceProperties/proxy headers sai | Dùng external canonical service URL |
| CAS redirect đúng public URL nhưng Spring callback 404 | Ingress rewrite/path local filter sai | Map public `/app/login/cas` tới local `/login/cas` |
| Callback bị xử lý như protected route và redirect CAS lại | Filter order/matcher không bắt `/login/cas` | Kiểm tra SecurityFilterChain và callback matcher |
| Validation gửi `service` thiếu `/app` | X-Forwarded-Prefix hoặc ServiceProperties sai | Khai báo fixed public URL và kiểm tra rewrite |
| Validation gửi scheme HTTP | TLS termination và forwarded handling sai | Config trusted forward headers/public URL |
| Validation gửi `:8080` hoặc upstream host | Sinh URL từ servlet request nội bộ | Dùng canonical public service identity |
| Validation gửi `:443` không đồng nhất | Canonical port representation khác | Thống nhất một value, test theo CAS release |
| Host bị thay bởi query/header từ client | Untrusted forwarded/Host | Edge strip/allowlist; không lấy user input làm service |
| CAS login bị registry reject trước khi cấp ST | Service URL chưa đăng ký/regex không match | Cập nhật approved registered service definition hẹp |
| `/serviceValidate` trả HTTP 200 nhưng không login | XML `authenticationFailure` | Parse CAS response protocol, không chỉ HTTP status |
| `renew=true` làm CAS yêu cầu lại password | Policy yêu cầu fresh primary credentials | Đối chiếu `ServiceProperties.sendRenew` và CAS policy |
| ST đã hết hạn | Browser/network latency, stale callback | Login mới, không kéo dài TTL vô hạn |
| CAS TGC không được gửi | Cookie domain/SameSite/Secure/path | Kiểm tra CAS origin cookie, không liên quan service URL binding |
| User login thành công nhưng request sau lại anonymous | App local session/cookie/proxy affinity | Kiểm tra Spring Session/HttpSession, SecurityContext |
| Node A success, node B INVALID_SERVICE | Pod config drift public-service-url | Readiness/version/config consistency |
| Validation TLS fail | Trust store, certificate/hostname hoặc network | Không disable hostname verification |
| CAS client dùng CAS proxy ticket validator vì có Nginx | Nhầm reverse proxy với CAS PT/PGT | Dùng ST validator phù hợp protocol |
| Proxy rewrites URL sau deploy Ingress | public-service-url/registry chưa cập nhật | Coordinated change + regression test |

### 12.1. Trình tự điều tra không làm rò ticket

1. **Loại lỗi:** registry reject trước issue ST, `INVALID_SERVICE` sau issue, `INVALID_TICKET`, callback 404, CAS backend TLS lỗi hay local session lỗi?
2. **Đo external callback:** kiểm tra cấu hình `ServiceProperties.service` và request `/cas/login` với `service` được redacted đúng; không copy `ticket`.
3. **Đo validation service:** lưu chỉ service ID đã allowlist và fingerprint/normalized URL thuộc config, không lưu ST hoặc full query.
4. **So khớp:** external scheme/host/port/prefix/path/trailing slash/query; kiểm tra ingress rewrite trên request thật.
5. **Xác định pod:** so desired/applied config và version service URL trên mỗi node; không dùng login success một pod làm kết luận toàn cluster.
6. **Sửa tầng sai:** config Spring, ingress routing, CAS registered service hoặc forwarded trust boundary.
7. **Login mới:** ST cũ đã consume; không replay.
8. **Test security:** wrong-service/attacker-host/expired/replayed tickets reject, TLS và logging kiểm tra.

**Không nên** log `request.getQueryString()` ở callback hoặc cả URL validation, vì có `ticket=ST-...`. Nếu cần audit, tạo event ID nội bộ và log reason code như `CAS_INVALID_SERVICE` cùng registration/service ID cho phép.

## 13. Bảo vệ service URL khỏi Host/Forwarded injection

Một ứng dụng dựng service URL bằng:

```java
// ANTI-PATTERN minh họa: host/proto do client truyền có thể bị giả.
// String service = request.getHeader("X-Forwarded-Proto")
//         + "://" + request.getHeader("X-Forwarded-Host")
//         + "/app/login/cas";
```

có thể bị attacker lợi dụng nếu proxy không strip headers. Khi ứng dụng redirect sang CAS với `service=attacker.example`, CAS có thể redirect browser tới host không được phép nếu registry cũng quá rộng, gây open redirect/ticket exposure.

Phòng vệ theo lớp:

1. Ingress **chỉ phục vụ allowed Host** và reject host không thuộc vhost.
2. Strip tất cả incoming `Forwarded` và `X-Forwarded-*` từ client trước khi thêm trusted values; đừng chỉ overwrite một header nhưng để header standard còn sống.
3. Backend chỉ nhận traffic từ trusted proxy/service mesh; không expose pod/NodePort trực tiếp ra Internet.
4. Spring Boot chỉ parse forwarded headers theo framework/container **sau khi** proxy sanitation.
5. `ServiceProperties.service` lấy từ **static allowlisted config** hoặc mapping allowlist theo tenant, không từ arbitrary browser Host/URL.
6. CAS Server registry chỉ cho phép service callbacks đúng domain, path, scheme; không broad regex.
7. Test một request từ client với forged forwarded headers và kiểm tra `service` vẫn đúng.

### 13.1. TLS hostname/trust và CAS validation backchannel

Proxy cho Portal có TLS termination không có nghĩa **backend → CAS Server** được bỏ TLS. CAS ticket validation phải kết nối `https://sso.example.org/cas/serviceValidate` với certificate chain/hostname validation hợp lệ và timeout. **Không** dùng `trustAll` HTTP client hoặc tắt SSL verification để giải login loop.

Lưu ý CAS service ID công khai không phải chứng cứ identity của CAS Server: CAS Server origin phải là URL đã quản trị và được validate qua HTTPS. Nếu attacker đổi destination của `TicketValidator` sang server giả, họ có thể giả `authenticationSuccess`. Service URL correctness và CAS Server trust phải **đúng cùng lúc**.

### 13.2. Tránh lộ ST qua logs/analytics

ST xuất hiện trên callback query:

```text
https://portal.example.org/app/login/cas?ticket=ST-...
```

Đây là bearer credential. Cần:

- Không log raw query string tại reverse proxy, ingress, servlet request logger hoặc APM spans.
- Không đưa ticket vào third-party analytics/Referer khi render callback.
- Dùng `Referrer-Policy: no-referrer` theo chính sách và redirect sang URL sạch sau validation.
- Không dán ST thật vào ticket hỗ trợ, chat hay issue tracker.
- Rate-limit/alert trên lỗi validation, không ghi nguyên CAS XML response chứa PII vào log.
- Xoay session ID sau login, quản lý cookie Secure/HttpOnly/SameSite phù hợp.
- Áp dụng CSRF cho state-changing requests của local web app; CAS login validation không thay CSRF/authorization.

## 14. Multi-node, blue/green và multi-tenant service URLs

### 14.1. Multi-pod: cùng một public service URL

Một service chạy ở 3 pods:

```text
portal-v1-pod-a:8080
portal-v1-pod-b:8080
portal-v2-pod-c:8080
        |
    Ingress /app/
        |
https://portal.example.org/app/login/cas
```

**Cả ba pods phải dùng cùng `ServiceProperties.service`** nếu chúng cùng nhận callback thuộc một public service identity. Không lấy `podName`, `nodeIP` hoặc runtime `server.port` làm service ID. Một callback từ browser có thể vào pod khác với pod đã khởi tạo CAS login.

CAS Server chỉ thấy một public registered service. Local Spring Security session/request cache cần Redis/shared session hoặc affinity theo yêu cầu ứng dụng; đó là bài toán **khác** ticket-to-service binding.

### 14.2. Blue/green migration domain hoặc prefix

Giả sử phiên bản mới chuyển callback từ:

```text
OLD https://portal.example.org/app/login/cas
NEW https://portal.example.org/workspace/login/cas
```

Cần điều phối:

1. CAS registry phê duyệt cả old/new service IDs trong **cửa sổ migration có hạn** (nếu chính sách cho phép).
2. Ingress tiếp nhận old và new callbacks trong thời gian in-flight, route về client config tương ứng.
3. Spring client old phải **validate ST old bằng old service**; client new **validate ST new bằng new service**. Không đổi mọi pods sang new trước khi các redirects old hoàn tất.
4. Đảm bảo session/request state và authentication path phù hợp, không nhận ST của old ở new mà bỏ binding.
5. Khi traffic old đã hết và tests xong, retire old registry/routing/config.
6. Nếu một service URL được ghi trong request cache/state, không để app tin value do browser tự chọn.

Nếu đang sử dụng một `ServiceProperties` fixed cho mỗi deployment, blue/green có thể yêu cầu **hai deployments/filters** hoặc thiết kế chuyên biệt cho multiple approved service IDs; không cố “autodetect” bằng Host header chưa được trust.

### 14.3. Multi-tenant và nhiều external hosts

Ví dụ:

```text
Tenant A: https://a.example.org/login/cas
Tenant B: https://b.example.org/login/cas
```

Một bean `ServiceProperties.setService` cố định chỉ đại diện **một** service callback. Nếu một Spring deployment thật sự phải phục vụ nhiều external identities, cần mô hình:

- Mapping tenant → approved public service URL được quản trị.
- Registration/routing context tin cậy để chọn service cho login và validation.
- Đối chiếu service URL của ticket với đúng tenant/client; không chọn tenant chỉ bằng raw Host/`ticket`/username.
- Có thể cần filter/provider hoặc `AuthenticationDetailsSource`/validator customization phù hợp Spring Security CAS release và CAS client semantics.
- Test ticket A không login service B, kể cả khi hai tenants cùng CAS Server.
- Không dùng `setAuthenticateAllArtifacts(true)` như một nút magic giải quyết multi-tenant service URL; đọc đúng contract của dynamic service authentication và bảo đảm origin/tenant binding.

Spring Security tài liệu có `ServiceAuthenticationDetailsSource` cho trường hợp xác thực tickets ở nhiều URLs, đặc biệt **stateless CAS proxy ticket** flows. Tính linh hoạt này **không** có nghĩa có thể nhận arbitrary service identity từ browser; phải ràng buộc với allowlist và CAS service ticket semantics.

### 14.4. Tính nhất quán trên CAS cluster

CAS Server cluster phải có ticket registry chia sẻ/atomic để ST phát ở node A được consume một lần ở node B. Từng node CAS phải dùng cùng service registry và service matching policy; một node broad regex hoặc normalize URL khác có thể tạo hành vi không nhất quán.

Một số CAS Servers hỗ trợ custom `ServiceMatchingStrategy`, nhưng thay semantics phải được phê duyệt và test cross-app/cross-tenant; không dùng làm workaround cho proxy URL bug.

## 15. Các tình huống test âm tính quan trọng

| Tình huống | Kết quả mong đợi |
| --- | --- |
| ST phát cho public `https://.../app/login/cas`, validate cùng URL | PASS (nếu các điều kiện khác hợp lệ) |
| ST phát cho public URL, validate bằng internal HTTP URL | **INVALID_SERVICE/reject** |
| ST phát cho public URL, validate URL thiếu `/app` | Reject |
| ST phát cho public URL, validate URL host khác | Reject |
| ST phát cho public URL, validate port 8443 thay 443 | Reject theo policy |
| ST phát cho Portal, validate ở Reports | Reject |
| ST validation mismatch, sau đó retry same ticket với đúng service | Reject do ST consumed |
| ST validation success, replay ticket | Reject |
| ST hết hạn | Reject, login mới |
| Ticket `ST-fake` chưa bao giờ phát hành | Reject |
| CAS backend TLS hostname mismatch | Reject/fail closed |
| Service ID chưa registered | CAS không cấp ST/không cho dùng |
| Registry match rule quá rộng | Security review/test FAIL |
| Browser tự gửi `X-Forwarded-Host=evil.example` | Không thay `ServiceProperties.service`/redirect |
| Browser tự gửi `Forwarded: host=evil.example` | Edge strip, không có effect |
| Browser tự gửi `X-Forwarded-Prefix=/evil` | Edge strip, không có effect |
| Proxy prefix duplicate `/app/app` | Integration routing test phải fail |
| Proxy context mismatch khiến callback 404 | Không tự relax ticket validation |
| CAS /serviceValidate HTTP 200 với `authenticationFailure` XML | Không tạo Authentication |
| CAS validation endpoint outage | Fail closed, không tự trust ticket |
| Browser callback có `ticket` đi vào access logs | Privacy/security test FAIL |
| Một pod dùng `http://portal-service`, pod khác dùng public URL | Config drift test FAIL |
| Một tenant đổi host, ticket tenant cũ sang host tenant mới | Reject, cần migration đúng |
| `renew` bật ở một bên nhưng validator/issuer policy khác | Diagnose/reject, không làm lỏng service binding |
| Nhiều CAS nodes đều accept replay cùng ST | CAS ticket registry test FAIL |

**Không chỉ kiểm tra “user thấy trang dashboard”**: phải thu các request của CAS test backend, kiểm tra issuer service identity và assert ticket replay/wrong-service reject.

## 16. Checklist triển khai

- [ ] Xác định **một public canonical callback URL** cho từng CAS service: scheme, host, port, prefix, path và query cố định (nếu có).
- [ ] `CasAuthenticationEntryPoint` gửi chính URL này trong `/login?service=...`.
- [ ] `CasAuthenticationFilter` bắt đúng **local callback path** sau proxy rewrite.
- [ ] `CasAuthenticationProvider`/`TicketValidator` validate ST với cùng service ID được dùng khi issue.
- [ ] `ServiceProperties.service` không dùng internal upstream host, không bị tính động từ untrusted browser headers.
- [ ] CAS registered service registry cho phép đúng HTTPS callback với matching strategy hẹp.
- [ ] Proxy đã strip/overwrite incoming `Forwarded` và `X-Forwarded-*`; reject unknown Host.
- [ ] Spring `server.forward-headers-strategy` được chọn đúng và không bị double rewrite.
- [ ] Prefix/context path đã kiểm tra trong thực tế; không có `/app/app` hoặc thiếu `/app`.
- [ ] Không nhầm TLS termination ở proxy với backend-to-CAS HTTPS trust.
- [ ] ST chỉ một validation attempt, service-bound, short TTL; mismatch/replay đều reject.
- [ ] CAS XML validation failure không tạo Authentication dù HTTP status 200.
- [ ] Không retry ST đã bị `INVALID_SERVICE` bằng service mới.
- [ ] Không log ST/query raw/cookies/validation XML chứa PII ở proxy, servlet và APM.
- [ ] Spring Security session ID rotation, session cookie và authorization được kiểm tra.
- [ ] Mọi pods có cùng public service URL/registry contract; có drift alert.
- [ ] Khi blue/green đổi domain/prefix, giữ old/new flows tách và có sunset plan.
- [ ] Multi-tenant service URLs được allowlist theo tenant; không choose-from-Host tùy ý.
- [ ] Test đúng/sai service, double encoding, port/case/trailing slash, forged forwarded header, SLO và cookie/session side effects.
- [ ] Runbook xử lý `INVALID_SERVICE` dùng event IDs/reason codes, không yêu cầu raw ST.

## 17. Câu hỏi ôn tập

**Câu 1.** CAS phát ST cho `https://portal.example.org/app/login/cas`. Backend chạy `http://portal-service:8080/login/cas`. Khi validate phải gửi `service` bằng URL nào?  
**Đáp án:** Public callback URL **đã dùng khi issue ST**, không phải upstream URL.

**Câu 2.** Sau `INVALID_SERVICE`, sửa `service` rồi retry cùng ST được không?  
**Đáp án:** Không. CAS protocol yêu cầu consume ST sau một validation attempt. Bắt đầu login mới.

**Câu 3.** CAS service registry có regex cho cả portal và reports, vậy ST Portal dùng ở Reports được không?  
**Đáp án:** Không. Registry cho phép ứng dụng request tickets; ticket vẫn phải ràng buộc với **service identifier khi phát**.

**Câu 4.** `CasAuthenticationFilter.filterProcessesUrl` có nên là full URL `https://portal.example.org/app/login/cas` không?  
**Đáp án:** Không. Filter matcher thường là **local servlet path** như `/login/cas`; `ServiceProperties.service` mới là public URL.

**Câu 5.** Có nên bật `server.forward-headers-strategy=framework` mà không kiểm tra Nginx strip headers?  
**Đáp án:** Không. Forwarded headers có thể bị client spoof; cần trusted proxy sanitation và host allowlist.

**Câu 6.** Vì sao dấu slash cuối và port 443 có thể gây lỗi?  
**Đáp án:** Vì service identity phải match theo quy tắc CAS đang chạy; không tự giả định mọi chuỗi URL đều được chuẩn hóa giống nhau.

**Câu 7.** CAS login redirect đúng URL mà callback trả 404, lỗi ở đâu?  
**Đáp án:** Có thể proxy rewrite/path context hoặc `CasAuthenticationFilter` matcher sai. Không phải lý do bỏ service binding.

**Câu 8.** `/serviceValidate` HTTP 200 có đủ để tạo local session không?  
**Đáp án:** Không. XML có thể chứa `authenticationFailure`. Phải xác minh CAS protocol result.

**Câu 9.** HTTP reverse proxy và CAS Proxy Ticket là một không?  
**Đáp án:** Không. Nginx/Ingress là network proxy; CAS PGT/PT là cơ chế delegated authentication riêng.

**Câu 10.** Vì sao fixed `ServiceProperties.service` thường tốt hơn tự dùng Host/X-Forwarded-Host để dựng URL?  
**Đáp án:** Nó tránh drift/mismatch và giảm khả năng host-header injection. Vẫn phải quản trị proxy headers đúng cho redirects/cookies.

**Câu 11.** Blue/green đổi `/app/login/cas` thành `/workspace/login/cas` nên dùng một shared service ID luôn không?  
**Đáp án:** Không tự bỏ binding. Giữ old/new registered services/flows theo migration plan, mỗi ticket validate với identity đã phát.

**Câu 12.** Khi có nhiều tenants/hosts trong một app, chọn `service` từ bất kỳ HTTP Host được không?  
**Đáp án:** Không. Cần mapping tenant→approved public callback, request context tin cậy và kiểm thử cross-tenant.

**Câu 13.** CAS Server `/serviceValidate` gọi từ browser hay backend SP?  
**Đáp án:** Backend CAS client/service qua HTTPS server-to-server; browser chỉ mang ST qua frontchannel redirect.

**Câu 14.** Một ST validation fail do wrong-service có thể được “cứu” bằng cách kéo dài TTL?  
**Đáp án:** Không. TTL và service identity là hai điều kiện khác nhau; ST đã consume, và nới TTL không sửa mismatch.

## 18. Tài liệu tham khảo chuẩn

- [Apereo CAS — CAS Protocol Specification](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html): `service` tại `/login` và `/serviceValidate`, `INVALID_SERVICE`/`INVALID_TICKET`, ST một lần thử và service binding.
- [Apereo CAS — Ticket Validation](https://apereo.github.io/cas/development/authentication/CAS-Protocol-TicketValidation.html): service identifier matching và các extension; lưu ý tác động bảo mật khi tùy biến.
- [Apereo CAS — Configuring Service Matching Strategy](https://apereo.github.io/cas/development/services/Configuring-Service-Matching-Strategy.html): full regex/literal matching trong service registry, không đồng nhất với ticket binding.
- [Apereo CAS — Service Management](https://apereo.github.io/cas/development/services/): registered services và governance URL.
- [Spring Security — CAS Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html): `ServiceProperties`, `CasAuthenticationEntryPoint`, `CasAuthenticationFilter`, `CasAuthenticationProvider`, TicketValidator.
- [Spring Security 6.2.6 — CasAuthenticationFilter API](https://docs.spring.io/spring-security/site/docs/6.2.6/api/org/springframework/security/cas/web/CasAuthenticationFilter.html): filterProcessesUrl mặc định `/login/cas` và `ServiceProperties.getService()` trong ticket validation.
- [Spring Security — ServiceProperties API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/ServiceProperties.html): public service URL và các tùy chọn.
- [Spring Framework — ForwardedHeaderFilter](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html): xử lý `Forwarded`/`X-Forwarded-*` và cảnh báo trust boundary; removeOnly mode.
- [Spring Boot 3.0 — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/docs/3.0.x/reference/html/howto.html): `server.forward-headers-strategy`, `FRAMEWORK`/`NATIVE` và proxy HTTPS details.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): cấu hình forwarded strategy.
- [OWASP Unvalidated Redirects and Forwards Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html): host/redirect allowlist.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): cookie và session security.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): credentials trong logs và audit events.

**Ghi nhớ:** **CAS không xác minh ST theo tên pod hoặc upstream URL**. ST gắn với **service identity** mà CAS đã dùng lúc cấp vé; vì vậy `ServiceProperties.service`, CAS login `service`, CAS validation `service` và CAS registered-service contract phải thống nhất trên **URL callback công khai**. Reverse proxy có thể thay scheme/host/port/path bên trong mà không thay định danh này. Sửa sai lệch ở cấu hình public URL, ingress routing và trusted forwarding headers; **không nới ticket-to-service binding, không retry ticket đã consume và không tin Host/Forwarded từ client**.