# Reverse proxy, đường dẫn viết lại và dữ liệu forwarded đáng tin cậy

> **Module:** Spring Security – authorization  
> **Nhóm:** Ngữ cảnh request  
> **Trọng tâm:** Request đi qua reverse proxy/load balancer/gateway có thể bị thay đổi đường dẫn, scheme, host, port và địa chỉ IP. Phân quyền phải áp dụng cho **request mà Spring Security thực sự nhìn thấy**, trong khi `Forwarded` và `X-Forwarded-*` chỉ được sử dụng sau khi ranh giới tin cậy được kiểm soát.

## 1. Tình huống: URL bên ngoài khác URL mà Spring nhận được

Giả sử khách hàng gọi API:

~~~http
GET https://shop.example/portal/api/admin/users
~~~

Hạ tầng gồm một HTTPS reverse proxy đặt phía trước ứng dụng Spring Boot chạy HTTP trong mạng riêng:

~~~text
Client/browser
    |
    | GET https://shop.example/portal/api/admin/users
    v
Trusted edge proxy / ingress
    |  - kết thúc TLS
    |  - xác thực host và định tuyến
    |  - bỏ prefix public "/portal"
    |  - thay thế các Forwarded/X-Forwarded-* không đáng tin
    |
    | GET http://app:8080/api/admin/users
    | X-Forwarded-Host: shop.example
    | X-Forwarded-Proto: https
    | X-Forwarded-For: 198.51.100.42
    | X-Forwarded-Prefix: /portal   (nếu cần cho public links)
    v
Spring Boot / Spring Security
    |
    +--> SecurityFilterChain / RequestMatcher
    +--> Authentication / AuthorizationManager
    +--> Controller / Service
~~~

Trong ví dụ **cụ thể** này, proxy đã thực sự đổi path từ `/portal/api/admin/users` thành `/api/admin/users`. Nếu cấu hình authorization chỉ kiểm tra một matcher dựa trên **đường dẫn public** `/portal/api/admin/**` mà thành phần matcher đang nhận đường dẫn upstream `/api/admin/**`, rule admin có thể không khớp. Tệ hơn, một rule rộng `authenticated()` hoặc một `SecurityFilterChain` thiếu fallback có thể làm request được xử lý với chính sách yếu hơn dự kiến.

Ngược lại, ứng dụng cần biết URL công khai là `https://shop.example/portal/...` để tạo redirect và absolute URL đúng. Đó là lý do tồn tại các header `Forwarded`/`X-Forwarded-*`.

**Hai vấn đề phải giải quyết đồng thời nhưng riêng biệt:**

1. **Path/routing correctness:** matcher bảo vệ chính xác đường mà servlet/security nhận sau khi proxy rewrite và sau các wrapper/filter có hiệu lực.
2. **Metadata trust:** chỉ nhận host, protocol, port, client address và prefix public từ proxy đáng tin, **không tin header do client tự tạo**.

Thêm `X-Forwarded-Proto: https` không phải là một phép xác thực người dùng; đặt `X-Forwarded-Prefix: /portal` cũng không mặc nhiên thực hiện path rewrite trong reverse proxy.

## 2. Một HTTP request có nhiều “góc nhìn” về URL

Phân biệt các lớp dữ liệu:

| Thuộc tính | Ví dụ trong tình huống | Nguồn/ý nghĩa |
|---|---|---|
| Public URL | `https://shop.example/portal/api/admin/users` | URL mà client gọi |
| Public scheme | `https` | Kết nối client → edge proxy |
| Public host | `shop.example` | Tên miền được gateway chấp nhận |
| Public prefix | `/portal` | Prefix có thể bị gateway loại bỏ khi forward |
| Upstream URL | `http://app:8080/api/admin/users` | Kết nối edge → ứng dụng |
| Backend path | `/api/admin/users` | Đường mà container nhận ở ví dụ này |
| `contextPath` | Thường trống nếu app triển khai ở root | Context ứng dụng Servlet; có thể bị wrapper thay đổi theo forwarded-prefix |
| `servletPath` / `pathInfo` | Phụ thuộc servlet mapping | Các trường Servlet dùng cho routing/matcher |
| `requestURI` | Thường chứa path theo upstream request và context path | Không tự đồng nghĩa public URI |
| `getScheme()`, `getServerName()` | Có thể là `http`/`app` nếu chưa xử lý forwarded | Giá trị request hiện hành; có thể được wrapper/container xử lý |
| Client IP quan sát ở backend | Địa chỉ proxy | Không nhất thiết là IP client cuối |

Các getter của Servlet không phải luôn có một hình dạng duy nhất. Spring MVC và Spring Security có thể dùng các `RequestMatcher`/`HandlerMapping` khác nhau tùy phiên bản, servlet mapping và cấu hình. Đặc biệt, `getRequestURI()`, `getContextPath()`, `getServletPath()` và `getPathInfo()` không thể hoán đổi tùy ý.

**Quy tắc quan trọng:** Không viết phân quyền bằng cách phỏng đoán chuỗi từ public URL. Hãy đo/kiểm thử request **sau hạ tầng proxy và các filter/wrapper liên quan**, rồi cấu hình matcher theo semantics của API đang sử dụng. Cần tránh log các header chứa credentials hoặc tokens khi chẩn đoán.

## 3. Reverse proxy có thể thay đổi những gì?

Một proxy, API gateway hoặc ingress có thể:

- Kết thúc TLS tại edge, tiếp tục kết nối nội bộ bằng HTTP.
- Thay `Host` public bằng tên upstream/hostname nội bộ (hoặc giữ host tùy cấu hình).
- Thêm/bỏ/thay prefix đường dẫn.
- Rewrite `/public/api/**` thành `/api/**`, hoặc đổi phiên bản `/v2/**` thành path upstream khác.
- Thêm thông tin nguồn request qua `Forwarded`/`X-Forwarded-*`.
- Route nhiều host public đến một backend; hoặc route một host đến nhiều services.
- Giới hạn truy cập mạng, xác thực người gọi ở gateway, rate limit hoặc chuẩn hóa URL.
- Thêm request ID/hop ID cho tracing (không có nghĩa các giá trị này đã đáng tin).

### 3.1. Ba kiểu rewrite thường gặp

~~~text
A. Strip prefix:
  public:  /portal/api/orders/42
  backend: /api/orders/42

B. Giữ nguyên path:
  public:  /portal/api/orders/42
  backend: /portal/api/orders/42

C. Thay prefix:
  public:  /service-a/orders/42
  backend: /internal/v1/orders/42
~~~

Ba tình huống có **đường upstream khác nhau**, nên một `requestMatchers("/portal/api/**")` không thể được tuyên bố luôn đúng hoặc luôn sai khi chưa biết gateway rewrite thật sự như thế nào.

Mỗi deployment phải có **routing contract**: public host/path/method → upstream service/path/method, cách chuyển tiếp header, trust boundary và cơ chế xác minh. Contract này cần được kiểm thử từ bên ngoài gateway, không chỉ kiểm thử controller bằng MockMvc.

### 3.2. Rewrite có thể gây lỗi “quyền không khớp controller”

Giả sử controller mapping:

~~~java
@GetMapping("/api/admin/users")
public List<UserDto> users() {
    // ...
}
~~~

Và proxy strip `/portal`. Nếu rule HTTP viết:

~~~java
.requestMatchers("/portal/api/admin/**").hasRole("ADMIN")
.anyRequest().authenticated()
~~~

trong ngữ cảnh matcher đang so khớp path upstream `/api/admin/users`, rule admin không khớp, request rơi vào `authenticated()`. Một user thường đã login **có thể vượt HTTP authorization** để gọi controller nếu không có lớp bảo vệ chặt khác. Đây là ví dụ về **vertical privilege escalation** do sai giả định về đường dẫn.

**Cách sửa trong kiến trúc upstream nêu trên:** matcher phải bao phủ URL mà security thấy, ví dụ `/api/admin/**`, với test tích hợp chứng minh đúng chain/rule. Không chỉ đổi regex/pattern mà chưa kiểm tra forwarded-prefix wrapper hoặc servlet context có làm thay đổi cách path matcher đánh giá không.

## 4. Forwarded headers: để mô tả client-facing request

Hai họ header thường gặp:

1. **`Forwarded`**: header chuẩn hóa bởi RFC 7239, chứa các thành phần như `for=`, `proto=`, `host=`; có thể chứa nhiều phần tử cho nhiều hop.
2. **`X-Forwarded-*`**: các header de facto phổ biến do proxy/gateway sử dụng.

Ví dụ:

~~~http
Forwarded: for=198.51.100.42;proto=https;host=shop.example
~~~

Hoặc các header:

~~~http
X-Forwarded-For: 198.51.100.42
X-Forwarded-Proto: https
X-Forwarded-Host: shop.example
X-Forwarded-Port: 443
X-Forwarded-Prefix: /portal
~~~

| Header | Công dụng thường gặp | Không được suy ra |
|---|---|---|
| `Forwarded` | Mô tả host/proto/for của request qua proxy | Header này mặc nhiên đáng tin hoặc được ký |
| `X-Forwarded-For` | Mô tả địa chỉ nguồn và có thể nhiều hop | Phần tử đầu tiên chắc chắn là IP khách hàng thật |
| `X-Forwarded-Proto` | Scheme public, thường là `https` | Client thực sự đã dùng HTTPS nếu header do nó tự gửi |
| `X-Forwarded-Host` | Host public | Host đã nằm trong danh sách tên miền được phép |
| `X-Forwarded-Port` | Port public, ví dụ `443` | Port đủ chứng minh TLS an toàn |
| `X-Forwarded-Prefix` | Prefix URL công khai, hữu ích cho URL generation | Proxy đã rewrite path đúng hoặc matcher tự đổi theo header |
| `X-Real-IP` | Header do một số proxy sử dụng để truyền IP | Chuẩn chung do Spring tự động tin trong mọi cấu hình |

**Chúng chỉ là dữ liệu HTTP cho tới khi ranh giới tin cậy xác minh nguồn.** Request từ Internet có thể gửi bất kỳ header nào, kể cả `Forwarded`, `X-Forwarded-Host`, `X-Forwarded-For` và `X-Forwarded-Proto`.

### 4.1. Quan hệ giữa `X-Forwarded-Prefix` và đường dẫn được rewrite

Spring Framework có hỗ trợ `X-Forwarded-Prefix` cho các tình huống public prefix bị thay, bỏ hoặc thêm khi đi qua proxy. Ví dụ:

~~~text
Public:  https://shop.example/portal/api/orders/42
Backend: http://app:8080/api/orders/42
Proxy:   X-Forwarded-Prefix: /portal
~~~

Khi ứng dụng **chủ động xử lý header đáng tin này**, framework có thể dùng prefix public để tạo liên kết/redirect phù hợp. Nhưng **header không thay thế thao tác rewrite của reverse proxy**; nếu proxy đã gửi upstream path sai, thêm header không tự sửa controller mapping hay security policy.

Ngoài ra, những wrapper áp dụng prefix có thể thay đổi cách request được trình bày ở Servlet API. Do đó **đừng kết luận mọi RequestMatcher luôn thấy `/api/**` hoặc luôn thấy `/portal/api/**`** chỉ từ ví dụ bên ngoài. Hãy kiểm tra đúng framework version, container, đường đi filter và endpoint thật.

## 5. Ranh giới tin cậy: tại sao dữ liệu forwarded có thể nguy hiểm?

Giả sử một client gửi:

~~~http
GET /portal/api/admin/users HTTP/1.1
Host: shop.example
X-Forwarded-Host: evil.example
X-Forwarded-Proto: https
X-Forwarded-For: 127.0.0.1
~~~

Nếu reverse proxy **chuyển nguyên xi** các giá trị đó và application dùng chúng như sự thật:

- Ứng dụng có thể tạo link hoặc redirect với host `evil.example`.
- Kiểm tra “yêu cầu HTTPS” có thể bị hiểu sai nếu `proto=https` giả mạo.
- Rule IP allowlist có thể bị vượt nếu tin `127.0.0.1` do client tự khai.
- Audit log/rate limit có thể nhận diện sai khách hàng.
- Header tùy biến như `X-Authenticated-User` nếu bị ứng dụng xem như danh tính đã xác thực có thể tạo lỗ hổng nghiêm trọng.

**Một framework không thể tự biết header do proxy đáng tin thêm hay do client độc hại gửi.** Vì vậy trách nhiệm chính nằm ở **edge proxy tại điểm bắt đầu mạng đáng tin**.

### 5.1. Chính sách trust boundary tối thiểu

1. **Không cho Internet kết nối trực tiếp đến backend** trừ luồng được ủy quyền. Dùng firewall/security group/private network và khi phù hợp dùng mTLS giữa proxy và ứng dụng.
2. **Ở edge tin cậy, xóa/ghi đè toàn bộ forwarded headers client gửi**, bao gồm cả `Forwarded` chuẩn và các `X-Forwarded-*`. Chỉ ghi các giá trị mà proxy tự quan sát hoặc đã xác minh.
3. **Chỉ chấp nhận host public đã cấu hình**; không đưa nguyên vẹn host tùy ý từ client thành trusted forwarded host.
4. **Chỉ tin các hop được kiểm soát**: khi có nhiều proxy, định nghĩa rõ proxy nào được phép thêm, chuyển tiếp hoặc chuẩn hóa các hop trước.
5. **Giới hạn địa chỉ proxy đáng tin** ở container/ingress khi cơ chế xử lý forwarded phụ thuộc địa chỉ mạng.
6. **Trong app, chỉ bật forwarded-header handling sau khi có trust boundary đúng**. Một filter xử lý header không tự làm header an toàn.
7. **Không biến forwarded metadata thành danh tính**. Authentication phải dựa vào session/JWT/mTLS/IdP hoặc một cơ chế ủy quyền gateway được bảo vệ đầy đủ.

Một cách hiểu gọn:

~~~text
Internet (không tin header)
    |
    v
TRUST BOUNDARY tại edge
    - bỏ mọi Forwarded/X-Forwarded-* nhận từ bên ngoài
    - xác thực public host và TLS state
    - lấy client IP quan sát được hoặc qua chuỗi hop đáng tin
    - ghi header canonical cho backend
    |
    v
Private upstream (chỉ tin đúng proxy)
    |
    v
Spring app có forwarded-header handling phù hợp
~~~

**Chỉ xóa `Forwarded` mà giữ `X-Forwarded-*`, hoặc ngược lại, là chưa đủ**: library khác nhau có thể đọc họ header khác nhau. Phải xử lý cả hai tại trust boundary.

## 6. Header forwarding không phải authentication, authorization hay bằng chứng nội bộ

Có ba điều dễ nhầm:

**A. `X-Forwarded-For: 127.0.0.1` không chứng minh request đến từ localhost.** Client từ Internet có thể viết chuỗi đó nếu edge không sanitize. Nếu ứng dụng dùng một đoạn `request.getHeader("X-Forwarded-For")` rồi cấp role admin cho IP “nội bộ”, đây là lỗi thiết kế.

**B. `X-Forwarded-Proto: https` không chứng minh đường truyền client được bảo vệ khi header không đáng tin.** Nó chỉ hữu ích sau khi proxy đã xác minh TLS thực tế. App không thể thay TLS enforcement bằng một phép so chuỗi.

**C. `X-Forwarded-Host: admin.example` không chứng minh user có quyền trên tenant/admin host.** Host-based routing có thể là một phần kiến trúc, nhưng cần host allowlist đáng tin và authentication/authorization trên principal. Không map host client tự gửi thành quyền.

Với kiến trúc “gateway xác thực hộ backend”, đôi khi có header như `X-Authenticated-User` hoặc `X-User-Roles`. Đó không phải forwarded metadata chuẩn. Nếu ứng dụng chấp nhận chúng làm authentication, phải có **kết nối chỉ từ gateway đã xác thực**, header client bị strip, định dạng/identity được kiểm tra, audit và cơ chế chống bypass. Không có những điều kiện này, **đừng tin**.

## 7. Spring Boot xử lý forwarded headers thế nào?

Với Spring Boot 3.x Servlet, thuộc tính:

~~~properties
server.forward-headers-strategy=framework
~~~

lựa chọn cách framework xử lý forwarded headers. Các lựa chọn phổ biến:

| Giá trị | Ý nghĩa chung | Điều cần kiểm tra |
|---|---|---|
| `none` | Không dùng cơ chế xử lý forwarded header do Boot chọn | App/server không có xử lý khác đi kèm ngoài ý muốn |
| `native` | Dùng cơ chế native của web server/container | Ví dụ Tomcat `RemoteIpValve`; khả năng hỗ trợ các header/prefix tùy container |
| `framework` | Dùng cơ chế Spring Framework | Với Servlet là `ForwardedHeaderFilter`; với reactive là cơ chế khác |
 
**Không có một lựa chọn đúng cho tất cả deployment.** Chọn dựa vào phiên bản Boot, container, cấu hình proxy và mục tiêu của ứng dụng. Spring Boot có thể có default khác nhau tùy môi trường/cloud platform: **đừng dựa vào default không được xác minh** trong production.

Ví dụ dùng framework handling ở nơi **đã đảm bảo proxy an toàn**:

~~~properties
# application.properties: chỉ bật sau khi edge sanitize headers.
server.forward-headers-strategy=framework
~~~

Nếu dùng container native:

~~~properties
# Phù hợp khi container được cấu hình trust proxies đúng.
server.forward-headers-strategy=native
~~~

Nếu không ở sau trusted proxy hoặc muốn bỏ việc dùng forwarded headers:

~~~properties
server.forward-headers-strategy=none
~~~

**Không nên bật `native` đồng thời tự đăng ký thêm `ForwardedHeaderFilter` nếu không có lý do và test rõ ràng.** Double-processing/wrapping có thể làm URL, redirect hoặc trust model khó đoán. Chọn **một chiến lược** và xác minh kết quả ở request thật.

### 7.1. Dùng ForwardedHeaderFilter khi nào?

`ForwardedHeaderFilter` của Spring Framework xử lý các giá trị `Forwarded` hoặc `X-Forwarded-*` và wrap request/response để downstream component có góc nhìn phù hợp với client-facing URL. Tùy phiên bản, nó hỗ trợ xử lý host, port, scheme, redirect, prefix và các trường liên quan.

Nếu sử dụng filter do framework cấu hình, thứ tự của nó phải bảo đảm các thành phần cần dữ liệu đã được chuẩn hóa **nhìn thấy request sau wrapper**. Tài liệu Spring Framework yêu cầu filter được đặt trước những filter downstream liên quan; với một số cách đăng ký thủ công còn cần cân nhắc dispatcher type `ASYNC` và `ERROR`.

**Lưu ý version:** API chọn họ header chuẩn hay `X-Forwarded-*`, và cách xử lý `X-Forwarded-Prefix` đã có thay đổi ở các phiên bản Spring Framework mới. Đừng sao chép một constructor/setting từ phiên bản khác rồi cho rằng nó tồn tại trên dependency của bạn. Xem JavaDoc và tài liệu chính thức của version đang dùng.

### 7.2. `removeOnly`: xóa mà không tin

Khi không muốn áp dụng forwarded metadata nhưng cần loại bỏ chúng trước downstream logic, `ForwardedHeaderFilter` có chế độ `removeOnly`:

~~~java
ForwardedHeaderFilter filter = new ForwardedHeaderFilter();
filter.setRemoveOnly(true);
~~~

Đây là **snippet Servlet Spring Framework 6.x minh họa**, không phải chương trình JDK độc lập. Cách khởi tạo của phiên bản mới hơn có thể khác; ở đây chỉ nêu ngữ nghĩa `removeOnly`. Nó làm header bị loại khỏi view của request mà không coi header client gửi là host/proto thật.

Tuy nhiên, **removeOnly không thay thế việc edge strip headers** và không ngăn một proxy khác phía trước tin nhầm chúng. Không tạo nhiều filter cùng xử lý header mà không hiểu thứ tự.

## 8. Cấu hình proxy theo hợp đồng thay vì theo cảm tính

Một bản hợp đồng proxy minh họa:

~~~text
Tên công khai được phép:
    shop.example
Giao thức client:
    HTTPS; HTTP bên ngoài phải redirect ở gateway
Đường public:
    /portal/api/**
Đường upstream:
    /api/**
Proxy rewrite:
    strip /portal
Kết nối upstream:
    chỉ private network; backend không public
Forwarding:
    xóa Forwarded và tất cả X-Forwarded-* từ client
    đặt X-Forwarded-Host = host đã allowlist (shop.example)
    đặt X-Forwarded-Proto = scheme client proxy thực thấy
    đặt X-Forwarded-Port = 443
    đặt X-Forwarded-For = địa chỉ nguồn đã xác minh
    đặt X-Forwarded-Prefix = /portal nếu app cần tạo URL public
Fallback:
    host lạ/path lạ -> proxy không chuyển vào app nhạy cảm
Logging:
    ghi request ID và routing outcome, che credentials/tokens
~~~

Đây là **pseudoconfiguration để review kiến trúc**, không phải cú pháp Nginx/Envoy/Kubernetes có thể dán chạy. Với Nginx, trailing slash trong `proxy_pass`, `location`, `rewrite` và `real_ip` tạo khác biệt thực tế; với ingress controller còn có annotation và behavior riêng theo version. Luôn kiểm chứng cấu hình thực trong môi trường staging, không chỉ đối chiếu pseudocode.

**Điểm đặc biệt:** nếu edge giữ nguyên `Host` từ client và ghi `X-Forwarded-Host` bằng giá trị đó, nó chưa chắc đáng tin nếu không có bước **allowlist host**. Xóa spoofed header nhưng chấp nhận host bất kỳ vẫn có nguy cơ host-header poisoning.

## 9. Cấu hình authorization với đường upstream đã xác minh

Giả sử integration test xác nhận security matcher thấy `/api/admin/**` trên backend sau rewrite. Một cấu hình Servlet có thể viết:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class BackendAuthorizationConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("order:read")
                .requestMatchers(HttpMethod.GET, "/api/public/**")
                    .permitAll()
                .anyRequest().denyAll()
        );

        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

**Đây là class cấu hình trong dự án Spring Boot/Spring Security**, không phải chương trình Java độc lập. Giả định backend được triển khai ở context phù hợp, matcher thực sự nhận path theo contract đã kiểm thử, và authentication provider đã cấp `ROLE_ADMIN`/`order:read` đúng cách.

Quan trọng:

- `/api/admin/**` đặt trước rule rộng; chỉ principal có `ROLE_ADMIN` mặc định mới qua HTTP rule.
- `GET /api/orders/**` cần authority `order:read`, nhưng service vẫn kiểm tra owner/tenant của từng đơn hàng.
- Chỉ `GET /api/public/**` được công khai ở HTTP rule; POST không tự hưởng rule này.
- `anyRequest().denyAll()` đóng mọi URL chưa khai báo **trong chain đã chọn**.
- `httpBasic` chỉ minh họa authentication mechanism; production cần HTTPS, credential provider và chính sách CSRF/session theo client.
- **Không viết `/portal/api/admin/**` chỉ vì URL client có `/portal`** nếu matcher ở deployment đã kiểm thử dùng upstream `/api/admin/**`.
- Nếu dùng `ForwardedHeaderFilter` có prefix wrapper, test lại semantics `requestMatchers` với đúng container/framework; không cố suy luận bằng một chuỗi cố định từ ví dụ.

### 9.1. Phân biệt securityMatcher và requestMatchers

Nếu tách nhiều chain:

~~~java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated());
~~~

`securityMatcher` quyết định **cả chain có được chọn hay không**; `requestMatchers` chỉ quyết định rule **sau khi chain đã được chọn**.

Ví dụ `/internal/debug` không khớp `securityMatcher("/api/**")`, nên `anyRequest().authenticated()` bên trong chain API **không bảo vệ** `/internal/debug`. Nếu không có chain fallback phù hợp, request đó có thể nằm ngoài Spring Security filter chain. Hệ thống có proxy rewrite càng phải kiểm tra trường hợp này.

Cấu hình nhiều chain nên có fallback không giới hạn matcher đặt cuối:

~~~java
@Bean
@org.springframework.core.annotation.Order(99)
SecurityFilterChain fallback(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll());
    return http.build();
}
~~~

Snippet giả định nó nằm trong một configuration class và các chain chuyên biệt có `@Order` cao hơn về ưu tiên. Nếu ứng dụng có public URL ở fallback, hãy thêm allowlist hẹp có chủ đích và test. Không đặt catch-all `permitAll` trước chain admin.

## 10. Những hậu quả phụ ngoài RequestMatcher

Thông tin forwarded sai không chỉ làm route/security khó debug. Nó còn có thể ảnh hưởng đến:

### 10.1. Redirect và absolute URL

Spring có thể tạo URL tuyệt đối để redirect, reset password, email xác minh, link pagination hoặc OAuth/OIDC callback. Nếu `X-Forwarded-Host` bị giả mạo, ứng dụng có thể tạo link tới domain kẻ tấn công; đó là **host-header poisoning** và có thể trở thành lỗ hổng nghiêm trọng tùy luồng.

Phòng vệ: public host allowlist tại proxy; chọn cách xử lý forwarded đúng; không lấy host không tin để tạo link bảo mật. Các callback/redirect URI quan trọng nên được đăng ký/allowlist theo cấu hình, không ghép từ request host tùy ý.

### 10.2. HTTP/HTTPS, Secure Cookie và HSTS

Nếu TLS kết thúc tại gateway, backend nhận HTTP. Nếu nó không biết public request vốn là HTTPS, redirect và URL generation có thể tạo `http://...`, cookie attributes hoặc security policies có thể bị cấu hình sai.

Ngược lại, **header `X-Forwarded-Proto: https` do client tự nhập không phải bằng chứng có TLS**. Edge phải xác minh protocol thực tế. HSTS phải được gửi đúng cho client-facing HTTPS response theo kiến trúc. Thuộc tính `Secure`/`SameSite` của cookie và CSRF/session strategy cần được cấu hình và test với proxy, browser thật.

### 10.3. Rate limit, IP allowlist và audit

Nếu app lấy `X-Forwarded-For` trực tiếp rồi dùng IP đầu tiên:

~~~java
// Không dùng làm quyết định tin cậy:
String clientIp = request.getHeader("X-Forwarded-For");
~~~

kẻ tấn công có thể tự đặt header `X-Forwarded-For: 127.0.0.1` nếu edge không strip. Dù chuỗi có nhiều IP, giá trị đầu tiên không tự chứng minh nguồn thật. Cần dùng **trusted proxy chain**/container logic đã cấu hình với đúng dải IP proxy, hoặc lấy IP từ gateway đã bảo đảm tính toàn vẹn. Các kiểm soát nhạy cảm không nên chỉ dựa vào IP; ưu tiên authentication/authorization mạnh và rate limiting phù hợp ở edge.

### 10.4. Host-based routing và multi-tenancy

Một số ứng dụng dùng subdomain như `tenant-a.shop.example` và `tenant-b.shop.example` để chọn tenant. Nếu chọn tenant chỉ bằng `Host`/`X-Forwarded-Host` do client tự khai, yêu cầu có thể bị gán sai phạm vi.

Nên ràng buộc **host đã được allowlist, session/principal và tenant membership**, kiểm tra quyền trên resource. Host có thể hỗ trợ định tuyến, nhưng không tự mang bằng chứng user được phép với tenant.

## 11. Chuỗi nhiều proxy: X-Forwarded-For không đơn giản là một IP

Kiến trúc có thể là:

~~~text
Client
   |
   v
CDN
   |
   v
External load balancer
   |
   v
Ingress
   |
   v
Spring app
~~~

Nếu mỗi hop append vào `X-Forwarded-For`, có thể có nhiều địa chỉ ngăn bằng dấu phẩy. Phần tử đầu tiên có thể là dữ liệu client giả mạo **nếu edge đầu tiên đã không xóa giá trị inbound**.

Quy tắc triển khai:

1. Xác định hop nào là **edge trust boundary** đầu tiên.
2. Edge xóa/ghi đè header từ Internet; chỉ giữ giá trị IP nó tin từ transport hoặc từ proxy trước được xác thực.
3. Mỗi hop nội bộ chỉ nhận forwarded metadata từ các proxy đã cho phép.
4. Container/ingress phải biết dải **trusted proxies**; không cấu hình “trust all” trong production.
5. Với nhiều header `Forwarded` và `X-Forwarded-*` cùng tồn tại, chọn chính sách nhất quán về họ header ưu tiên và loại bỏ họ không sử dụng.
6. Test khi bỏ qua một proxy, thay IP hoặc gọi backend trực tiếp: cơ chế trust phải từ chối hoặc không tin header.

Nếu app có kết nối trực tiếp công khai, mọi quy tắc sanitize ở proxy có thể bị **bypass**. Vì vậy network isolation quan trọng ngang với cấu hình application.

## 12. Java 17 độc lập: mô phỏng trusted edge, rewrite và rule admin

Ví dụ này dùng **Java thuần**, mô phỏng đúng một kịch bản: edge đáng tin strip prefix `/portal`, **bỏ qua các forwarded headers giả của client** và đặt metadata từ thông tin nó đã xác minh. App bảo vệ `/api/admin/**` bằng điều kiện đăng nhập + role admin.

**Đây chỉ là mô phỏng**, không phải implementation của proxy/Spring Security. Các phép `startsWith` cố ý đơn giản để diễn tả đường đi; môi trường thật phải dùng gateway routing và `RequestMatcher`/authorization infrastructure được kiểm thử.

Lưu tệp `ProxyBoundaryDemo.java`:

~~~java
public class ProxyBoundaryDemo {
    record ClientRequest(
            String publicPath,
            String clientForwardedHost,
            String clientForwardedProto,
            String clientForwardedFor) {}

    record UpstreamRequest(
            String path,
            String forwardedHost,
            String forwardedProto,
            String forwardedFor) {}

    static UpstreamRequest trustedEdge(
            ClientRequest client, String observedRemoteIp) {
        if (!client.publicPath().startsWith("/portal/")) {
            throw new IllegalArgumentException("Unexpected external route");
        }
        String backendPath =
                client.publicPath().substring("/portal".length());
        return new UpstreamRequest(
                backendPath,
                "shop.example",
                "https",
                observedRemoteIp);
    }

    static boolean adminMatcher(String path) {
        return path.startsWith("/api/admin/");
    }

    static String adminAuthorization(
            String path, boolean authenticated, boolean admin) {
        if (!adminMatcher(path)) {
            return "NOT_ADMIN_RULE";
        }
        return authenticated && admin ? "ALLOW" : "DENY";
    }

    public static void main(String[] args) {
        ClientRequest client = new ClientRequest(
                "/portal/api/admin/users",
                "evil.example",
                "http",
                "127.0.0.1");

        UpstreamRequest upstream =
                trustedEdge(client, "198.51.100.42");

        System.out.println("external path: " + client.publicPath());
        System.out.println("backend path: " + upstream.path());
        System.out.println("wrong external matcher: "
                + upstream.path().startsWith("/portal/api/admin/"));
        System.out.println("correct backend matcher: "
                + adminMatcher(upstream.path()));
        System.out.println("client fake host: "
                + client.clientForwardedHost());
        System.out.println("trusted forwarded host: "
                + upstream.forwardedHost());
        System.out.println("trusted forwarded proto: "
                + upstream.forwardedProto());
        System.out.println("trusted forwarded for: "
                + upstream.forwardedFor());
        System.out.println("ordinary user: "
                + adminAuthorization(upstream.path(), true, false));
        System.out.println("admin user: "
                + adminAuthorization(upstream.path(), true, true));
        System.out.println("backend direct access: REJECT");
    }
}
~~~

Biên dịch bằng Java 17:

~~~bash
javac --release 17 ProxyBoundaryDemo.java
java ProxyBoundaryDemo
~~~

Kết quả đã được kiểm tra:

~~~text
external path: /portal/api/admin/users
backend path: /api/admin/users
wrong external matcher: false
correct backend matcher: true
client fake host: evil.example
trusted forwarded host: shop.example
trusted forwarded proto: https
trusted forwarded for: 198.51.100.42
ordinary user: DENY
admin user: ALLOW
backend direct access: REJECT
~~~

Giải thích:

- Dòng 1–2: cùng một request nhưng **public path** và **upstream path** khác nhau.
- Dòng 3–4: matcher dựa trên prefix public sai trong kịch bản upstream này; matcher dựa trên path mà backend thật nhận mới khớp.
- Dòng 5–8: client gửi `evil.example`, `http`, `127.0.0.1` nhưng edge không sử dụng các giá trị ấy; edge đặt host/protocol/IP từ nguồn đã xác minh.
- Dòng 9–10: một rule admin vẫn phải kiểm tra authentication và role; regex/path khớp không cấp quyền.
- Dòng cuối: backend direct access bị từ chối là **chính sách mạng giả định**, không phải tính năng tự sinh của Java hay Spring Security.

Giá trị `198.51.100.42` là địa chỉ mẫu phục vụ tài liệu; không gắn với một khách hàng thật.

## 13. Kiểm thử: phải qua cả proxy và Spring Security

Chỉ test `MockMvc` trong ứng dụng không đủ để chứng minh edge đã strip headers và rewrite path đúng. Cần tách **ba lớp test**:

1. **Unit/component test:** kiểm tra `RequestMatcher`, route/role rules, URL builder và parser ở application.
2. **Spring integration test:** qua Servlet filter chain, method security, authentication provider; kiểm tra matcher, handler và status.
3. **End-to-end qua gateway/staging:** gửi request từ bên ngoài trust boundary, cả header hợp lệ và header giả mạo, quan sát upstream path và response an toàn.

### 13.1. Ma trận bắt buộc cho path rewrite

| Client request | Upstream path kỳ vọng | Chính sách cần có |
|---|---|---|
| `GET /portal/api/admin/users` | `/api/admin/users` | Chỉ admin; user thường bị từ chối |
| `GET /portal/api/orders/42` | `/api/orders/42` | `order:read` + owner/tenant |
| `POST /portal/api/orders/42` | `/api/orders/42` | Policy POST riêng, không hưởng GET |
| `GET /portal/api/public/faq` | `/api/public/faq` | Public có chủ đích |
| `GET /portal/internal/debug` | `/internal/debug` hoặc gateway từ chối | Không được rơi vào API public |
| `GET /portal/api/admin/users/` | Theo rewrite thật | Không bypass vì slash cuối |
| `GET /portal//api/admin/users` | Theo firewall/proxy | Reject hoặc xử lý nhất quán |
| `GET /portal/api/%61dmin/users` | Theo decode/routing thực | Không bypass rule admin |
| Request không thuộc `/portal/**` | Không route vào backend nhạy cảm | Bị gateway hoặc fallback từ chối |

Đây là **bảng kỳ vọng cho kịch bản proxy strip `/portal`**. Nếu deployment chọn rewrite khác, hãy thay bảng theo contract thật rồi test. URL có encoded slash, semicolon hoặc dot segments không nên được tự động “thêm vào allowlist”; test phải xác nhận proxy và application có canonicalization nhất quán.

### 13.2. Ma trận header spoofing

| Test | Hành vi mong đợi |
|---|---|
| Client gửi `X-Forwarded-Host: evil.example` | App **không** dùng evil host làm URL public |
| Client gửi `Forwarded: host=evil.example;proto=https` | Edge xóa/ghi đè; không tin |
| Client gửi `X-Forwarded-Proto: https` khi thực tế không có TLS | Gateway không cho đánh lừa chính sách HTTPS |
| Client gửi `X-Forwarded-For: 127.0.0.1` | Không được vượt IP allowlist |
| Client gửi `X-Forwarded-Prefix: /admin` | Không được tự thay routing hoặc quyền |
| Client gửi cả `Forwarded` và `X-Forwarded-*` trái ngược | Có chính sách chuẩn hóa nhất quán, không phụ thuộc thứ tự mơ hồ |
| Client gọi trực tiếp IP:port backend | Bị network layer từ chối hoặc không tin header |
| Nhiều hop, một hop không đáng tin | Không dùng hop không tin để xác định identity/IP |
| Proxy tạo header đúng host/scheme/prefix | App tạo redirect/link public hợp lệ |
| Proxy gửi header thiếu/sai | Hành vi fail-safe, monitoring phát hiện, không mở rộng quyền |

**Đừng chỉ assert status `403` trên endpoint không tồn tại.** Một route không có controller có thể trả 404 dù request không được security chain bảo vệ. Test phải có endpoint thật và kiểm tra authorization/response body, hoặc xác minh `FilterChainProxy` chọn đúng chain.

### 13.3. MockMvc để kiểm tra rule ở backend

Giả sử app có endpoint thật `GET /api/admin/users` và `SecurityFilterChain` tương ứng, test Spring MVC có thể viết:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BackendSecurityTest {
    @Autowired
    MockMvc mvc;

    @Test
    void normalUserCannotReadAdminEndpoint() throws Exception {
        mvc.perform(get("/api/admin/users")
                .with(user("lan").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanPassHttpRule() throws Exception {
        mvc.perform(get("/api/admin/users")
                .with(user("admin").roles("ADMIN")))
            .andExpect(status().isOk());
    }
}
~~~

Đây là **test tích hợp trong dự án có Spring Security Test**, cần controller thật trả 200 và các dependency đúng. Nó kiểm tra rule trên backend path `/api/admin/users`, **chưa chứng minh proxy ngoài thực tế rewrite `/portal` và sanitize forwarded headers**. Phải thêm end-to-end qua edge cho phần đó.

Khi xây test cho `X-Forwarded-Prefix`, `X-Forwarded-Host`, `X-Forwarded-Proto`, cần xác minh filter/framework có thực sự được đăng ký trong MockMvc/test runtime. Gửi một header vào mock request **không tự tái hiện** việc gateway đã xác thực và ghi đè header.

## 14. Gỡ lỗi trong môi trường nhiều lớp proxy

Khi gặp 404, 401/403, redirect sai host hoặc browser cảnh báo cookie, hãy làm theo thứ tự:

1. **Xác định public URL:** scheme, host, path, method, port, query từ browser/client.
2. **Xem gateway route:** service/backend nào được chọn, có strip/rewrite prefix không? Tên host và thứ tự route có đúng?
3. **Xem trust boundary:** edge có xóa `Forwarded` và mọi `X-Forwarded-*` inbound không? Backend có chỉ nhận từ proxy đáng tin không?
4. **Xác minh upstream request:** path/method thực đến Servlet là gì? Có bị path normalization, decode, rewrite thêm không?
5. **Kiểm Servlet fields:** `requestURI`, `contextPath`, `servletPath`, `pathInfo` và `getScheme()/getServerName()/getServerPort()` sau xử lý filter.
6. **Kiểm forwarding mode:** `server.forward-headers-strategy` thực tế là `none`, `native` hay `framework`? Có filter native/trùng lặp không?
7. **Kiểm chain coverage:** securityMatcher chọn `SecurityFilterChain` nào? Có chain fallback cuối không?
8. **Kiểm rule order:** URL đã khớp rule rộng `permitAll`/`authenticated` trước role/admin rule chưa?
9. **Kiểm authentication:** principal, authorities và kết quả kiểm tra method/object policy có đúng không?
10. **Kiểm response URL/cookie:** `Location` redirect, host, scheme, prefix, `Set-Cookie` `Secure`/`SameSite` có khớp public request không?
11. **Kiểm bản ghi dữ liệu:** user đúng role nhưng khác tenant/owner phải bị từ chối.
12. **Chạy test âm tính:** spoof host/proto/IP/prefix, direct-backend access, đường dẫn encoding/trailing slash và request qua nhiều hops.

### Logging an toàn

Ở môi trường test/staging, có thể bật log Spring Security theo phạm vi hẹp:

~~~properties
logging.level.org.springframework.security.web.FilterChainProxy=DEBUG
logging.level.org.springframework.security.web.access.intercept=DEBUG
~~~

Mức log và thông điệp thực tế phụ thuộc phiên bản. Đừng log token, cookie phiên, thông tin đăng nhập, PII hoặc toàn bộ forwarded chain chứa dữ liệu nhạy cảm. Không dùng DEBUG/TRACE lâu dài trong production mà thiếu kiểm soát.

Cần phân biệt **404 do gateway** (không route), **404 do MVC** (không handler), **401/403 do Spring Security**, **403 do CSRF** và **403/404 do object policy**. Mỗi loại có nguyên nhân khác nhau.

## 15. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Dùng public path để viết matcher nhưng proxy đã strip prefix | Rule admin không khớp hoặc rơi vào rule yếu hơn | Test upstream path và matcher thực |
| Tin rằng `X-Forwarded-Prefix` tự thực hiện path rewrite | Controller/security routing không đúng | Cấu hình gateway rewrite và framework handling riêng |
| Chấp nhận forwarded headers của client | Host/proto/IP spoofing | Strip ở edge và set giá trị trusted |
| Chỉ strip `Forwarded`, bỏ qua `X-Forwarded-*` | Thư viện khác vẫn tin giá trị giả | Xử lý cả hai họ header |
| Cho phép gọi backend trực tiếp | Bypass trust boundary của gateway | Private network, firewall/mTLS |
| Đặt `X-Forwarded-For` đầu tiên làm IP thật | Bypass IP allowlist/rate limit | Trusted proxy chain, không tự parse tùy tiện |
| Tin `X-Forwarded-Host` để chọn tenant | Lộ dữ liệu cross-tenant | Host allowlist + principal/tenant policy |
| Cấu hình `framework` và `native` chồng chéo | Double processing/request URL sai | Một chiến lược có test |
| Bật forwarded handling không kiểm proxy | App tin dữ liệu giả | Chuẩn hóa edge trước, có thể dùng `removeOnly` khi không tin |
| Đặt `securityMatcher` quá hẹp, không fallback | Request ngoài chain không được Spring Security bảo vệ | Catch-all chain cuối với deny |
| Đặt matcher rộng `authenticated` trước admin | Người thường vượt HTTP rule | Rule đặc quyền lên trước, negative tests |
| Coi URL khớp là đã đủ phân quyền | IDOR/BOLA | Service check owner/tenant/resource |
| Tạo redirect từ Host không allowlist | Host-header poisoning | Canonical origin hoặc allowlist host |
| Chỉ test backend bằng MockMvc | Không phát hiện lỗi proxy rewrite/header spoof | Test end-to-end qua gateway |
| Xem 404 là chứng minh Spring chặn | Có thể URL không có controller | Test filter chain và endpoint thật |

## 16. Checklist trước khi triển khai

- [ ] Có sơ đồ **public URL → edge route → upstream URL → Spring matcher/controller** cho từng nhóm API nhạy cảm.
- [ ] Đã xác định proxy có **strip, giữ hay thay prefix**; không suy luận từ tên path.
- [ ] Đã test các Servlet fields và matcher với đúng container/framework phiên bản đang dùng.
- [ ] Edge **xóa/ghi đè cả `Forwarded` và `X-Forwarded-*`** inbound từ Internet.
- [ ] Public host được allowlist; TLS state và client IP được edge xác minh.
- [ ] Backend không được truy cập trực tiếp từ mạng không đáng tin; trusted proxy hops có cấu hình rõ.
- [ ] `server.forward-headers-strategy` được đặt có chủ đích và tránh double processing.
- [ ] `X-Forwarded-Prefix` chỉ dùng đúng nhu cầu; redirect/link public hoạt động, không làm hở route khác.
- [ ] `SecurityFilterChain` có coverage cho mọi request cần bảo vệ và có fallback phù hợp.
- [ ] Rule admin/permission không bị `authenticated`/`permitAll` rộng che trước.
- [ ] Có object policy cho tenant/owner, không dựa trên host/path/client-supplied ID đơn thuần.
- [ ] Redirect, OAuth callback, password reset links, Secure cookies, HSTS/HTTPS đã kiểm tra qua gateway.
- [ ] Test spoof host, protocol, client IP và prefix; test đường encoded/trailing slash và direct backend.
- [ ] Log/monitor có request ID và routing outcome nhưng không rò credential.
- [ ] Có test regression khi đổi ingress/controller context path hoặc nâng Spring Boot/Framework.

**Nguyên tắc tổng kết:** *Đúng đường dẫn ở backend, đúng danh tính ở Spring Security, đúng nguồn metadata ở trust boundary.* Ba điều này phải đúng cùng lúc mới tránh được lỗ hổng do reverse proxy và dữ liệu forwarded.

## 17. Tự kiểm tra kiến thức

**1. Proxy đổi `/portal/api/admin/users` thành `/api/admin/users`. Có được mặc định viết matcher `/portal/api/admin/**` ở backend không?**  
Không. Matcher phải khớp request mà Spring Security thực tế nhìn thấy sau rewrite và forwarded handling; cần kiểm chứng trong runtime.

**2. `X-Forwarded-Prefix: /portal` có tự rewrite HTTP request upstream không?**  
Không. Nó là metadata hỗ trợ xử lý public prefix; proxy phải có rule rewrite riêng.

**3. `X-Forwarded-For: 127.0.0.1` có chứng minh client đến từ localhost?**  
Không. Header có thể do client tự gửi nếu edge không sanitize.

**4. Vì sao phải strip cả `Forwarded` và `X-Forwarded-*`?**  
Vì các framework/container có thể đọc các họ header khác nhau; bỏ sót một họ vẫn cho phép spoof.

**5. `server.forward-headers-strategy=framework` có tự biến mọi forwarded headers thành đáng tin không?**  
Không. Nó bật xử lý ở app; trust boundary phải được áp dụng ở proxy/network trước đó.

**6. Khi nào chọn `native` thay vì `framework`?**  
Khi cơ chế container native đáp ứng đúng header/redirect/prefix requirements và trusted proxy configuration của deployment; test kết quả thực tế thay vì chọn theo thói quen.

**7. Vì sao `anyRequest().denyAll()` trong chain chỉ khớp `/api/**` không bảo vệ `/debug`?**  
Vì `/debug` không vào chain đó. Cần một chain khác hoặc fallback không giới hạn matcher.

**8. MockMvc test `GET /api/admin/users` trả 403 cho user thường có chứng minh gateway đã strip `Forwarded` không?**  
Không. Nó kiểm tra app HTTP rule; gateway sanitization cần test end-to-end qua proxy.

**9. Vì sao sai `X-Forwarded-Host` có thể nguy hiểm hơn lỗi link bị hỏng?**  
Vì host giả có thể đi vào redirect, password reset links, callback URL hoặc tenant routing, dẫn đến host-header poisoning và rò dữ liệu tùy hệ thống.

**10. Nếu URL ID hợp lệ, user có `ROLE_ADMIN`, có được đọc tài nguyên của mọi tenant không?**  
Không tự động. Cần policy business/tenant/owner và kiểm soát phạm vi quyền cụ thể.

## 18. Tài liệu chính thức

- Spring Security – **HTTP request security và forwarded headers**: https://docs.spring.io/spring-security/reference/features/exploits/http.html
- Spring Security – **Authorize HttpServletRequests / Security Matchers**: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security – **Java Configuration / Multiple HttpSecurity / fallback**: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Framework – **Servlet Filters / Forwarded Headers / ForwardedHeaderFilter**: https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html
- Spring Framework – **Path Matching in Spring MVC**: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/handlermapping-path.html
- Spring Boot 3.5 – **Running Behind a Front-end Proxy Server**: https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
- RFC 7239 – **Forwarded HTTP Extension**: https://www.rfc-editor.org/rfc/rfc7239
