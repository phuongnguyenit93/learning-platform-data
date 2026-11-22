# Chuyển hướng sau đăng nhập và giới hạn nguồn URL được tin cậy

Sau khi người dùng đăng nhập thành công, ứng dụng thường đưa họ đến dashboard hoặc trang đang xem trước khi bị yêu cầu xác thực. Đây là **post-login redirect**. Một tính năng nhỏ nhưng có thể biến thành **open redirect** nếu máy chủ lấy URL từ query parameter, cookie, header hoặc request chưa được kiểm tra rồi ghi thẳng vào HTTP `Location`.

Điều kiện an toàn không chỉ là “đăng nhập đã thành công”, mà còn là: **địa chỉ đích đến từ nguồn được phép, thuộc phạm vi URL đã phê duyệt, đúng phiên/ngữ cảnh và không làm mất các kiểm tra quyền tại resource**. Với Spring Security Servlet, các thành phần liên quan gồm `AuthenticationSuccessHandler`, `SavedRequestAwareAuthenticationSuccessHandler`, `RequestCache`, `defaultSuccessUrl` và `RedirectStrategy`.

Bài học tập trung vào **giới hạn nguồn URL đáng tin cậy khi chuyển hướng sau login**, vừa bảo vệ chống phishing/open redirect, vừa giữ được trải nghiệm deep link nội bộ khi có yêu cầu chính đáng. Ví dụ Java 17+ được tách rõ giữa chương trình chạy độc lập và cấu hình cần Spring Boot.

## 1. Vì sao ứng dụng cần chuyển hướng sau login?

Ví dụ người dùng chưa đăng nhập mở trang đơn hàng:

~~~http
GET /orders/123 HTTP/1.1
Host: shop.example.org
~~~

Một flow thông thường:

~~~text
Browser: GET /orders/123
          |
          v
Spring Security thấy chưa được xác thực
          |
          v
Lưu request ban đầu nếu RequestCache được bật
          |
          v
302 -> /login
          |
          v
POST /login, credentials được xác minh
          |
          v
AuthenticationSuccessHandler chọn đích
          |
          +--> /orders/123 (saved request hợp lệ)
          |
          +--> /dashboard (fallback an toàn)
          |
          v
Browser GET trang đích trong phiên đã đăng nhập
~~~

Đưa người dùng trở lại `/orders/123` giúp UX tốt, nhưng họ vẫn phải có quyền với đơn hàng đó. Đăng nhập thành công **không tự cấp phép** truy cập mọi đơn hàng, tenant hoặc vai trò.

Ba kiểu đích phổ biến:

| Tình huống | Cách chọn đích phù hợp | Cần bảo vệ |
| --- | --- | --- |
| Login bình thường | URL cố định như `/dashboard` | Đích cấu hình không đến từ client |
| Login sau khi yêu cầu trang protected | SavedRequest cùng session | Host/public origin, path, ngữ cảnh |
| Người dùng chọn khu vực sau login | Mã route như `destination=orders` | Mapping cố định, quyền truy cập |
| Portal cần nhảy sang đối tác | Mã đích allowlist | HTTPS, host/port/path và không gửi token |

Nhu cầu UX **không** đồng nghĩa phải cho phép một `returnUrl` tùy ý.

## 2. Open redirect: cách một URL chuyển hướng trở thành lỗ hổng

Một request do attacker tạo:

~~~text
https://shop.example.org/login?next=https://fake-login.example.net
~~~

Phản ví dụ Java:

~~~java
// Không an toàn: client có toàn quyền quyết định đích.
response.sendRedirect(request.getParameter("next"));
~~~

Sau khi login, server trả:

~~~http
HTTP/1.1 302 Found
Location: https://fake-login.example.net
~~~

Nạn nhân đã tương tác trên domain thật, nên dễ tin luồng điều hướng tiếp theo. Website giả có thể yêu cầu đăng nhập lại, thu thập OTP, dẫn dụ cài đặt phần mềm hoặc lợi dụng sự tin tưởng vào link bắt đầu bằng domain chính thức.

**Xác thực danh tính không làm đầu vào trở nên đáng tin.** Request parameter `next` có thể do chính attacker đính vào link gửi nạn nhân. Các tên `returnUrl`, `continue`, `redirect`, `target`, `callback` hoặc `destination` có rủi ro tương tự nếu được xử lý như một URL tùy ý.

Open redirect cũng có thể bị dùng làm mắt xích trong các luồng OAuth, phishing, redirect chaining và che giấu đích liên kết. Vì vậy cần kiểm soát **mọi nơi tạo HTTP redirect**, không riêng trang login.

## 3. Phân loại nguồn URL theo mức độ tin cậy

| Nguồn target | Đánh giá | Chính sách nên dùng |
| --- | --- | --- |
| Constant path ở backend | Tốt nếu code review | Ưu tiên |
| Server-side route key allowlist | Tốt nếu map chỉ do server quản lý | Giải pháp linh hoạt an toàn |
| SavedRequest được tạo trong session login | Có điều kiện | Kiểm đúng session và nguồn host/path |
| Query parameter `next` hoặc `returnUrl` | Không tin cậy | Không truyền thẳng vào redirect |
| Header `Referer` | Không tin cậy, có thể vắng mặt | Không làm nguồn redirect mặc định |
| Cookie/localStorage của browser | Client có thể sửa | Cần kiểm lại hoặc ký/ràng buộc context |
| Header `Host`, `Forwarded`, `X-Forwarded-Host` | Có thể giả nếu cấu hình proxy sai | Chỉ tin từ proxy được phép |
| Dữ liệu URL trong database | Tùy quyền tạo/sửa record | Vẫn cần allowlist đích |
| OAuth2/OIDC `redirect_uri` | Phải được client đăng ký/kiểm tại AS | Không nhập nhằng với post-login URL |

Không có quy tắc “đã lưu trong session thì chắc chắn an toàn”: nếu session lưu URL từ input không được kiểm, lần đọc lại cũng vẫn phải áp chính sách.

Các câu hỏi cần chốt trước khi triển khai:

1. Có cần target động không, hay một URL cố định là đủ?
2. Phạm vi cho phép là path nội bộ, một nhóm domain công ty hay cả partner?
3. Ai chọn target, bằng cơ chế nào và vào thời điểm nào?
4. Target có được gắn với login session, tenant và account không?
5. Nếu target không hợp lệ, fallback ở đâu?
6. Resource đích còn cần kiểm quyền nào sau khi login?

## 4. Spring Security quyết định URL sau login như thế nào?

Trong Spring Security Servlet, `AuthenticationSuccessHandler` được gọi sau khi xác thực thành công. Với form login, `SavedRequestAwareAuthenticationSuccessHandler` có thể đưa người dùng trở lại request đã bị chặn trước login.

Theo Javadoc Spring Security 6.x/7.x, thứ tự lựa chọn của handler này về cơ bản:

1. Nếu `alwaysUseDefaultTargetUrl=true`: dùng `defaultTargetUrl`, bỏ qua saved request.
2. Nếu đã cấu hình `targetUrlParameter` và request có tham số đích: dùng giá trị tham số, đồng thời không ưu tiên saved request.
3. Nếu `RequestCache` có `SavedRequest`: redirect về URL của request đó.
4. Nếu không có các điều kiện trên: dùng fallback của lớp cha, thường là `defaultTargetUrl`.

Sơ đồ:

~~~text
Authentication successful
           |
           v
alwaysUseDefaultTargetUrl == true ?
       yes --> defaultTargetUrl
       no
           |
           v
targetUrlParameter có giá trị ?
       yes --> giá trị param (phải được tin cậy!)
       no
           |
           v
SavedRequest trong RequestCache ?
       yes --> request URL ban đầu
       no
           |
           v
defaultTargetUrl
~~~

**Cẩn thận với `targetUrlParameter`:** nó cho phép một giá trị từ request ảnh hưởng trực tiếp tới target. Không cấu hình `setTargetUrlParameter("next")` nếu ứng dụng chưa có một validator/allowlist bao quanh phù hợp.

### Những API liên quan

- `SavedRequestAwareAuthenticationSuccessHandler`: dùng saved request khi thích hợp.
- `SimpleUrlAuthenticationSuccessHandler`: có logic URL mặc định/tham số/referer qua lớp cha.
- `AbstractAuthenticationTargetUrlRequestHandler`: cung cấp `setDefaultTargetUrl`, `setAlwaysUseDefaultTargetUrl`, `setTargetUrlParameter`, `setUseReferer`.
- `HttpSessionRequestCache`: thường lưu request ban đầu trong session.
- `RedirectStrategy`: chiến lược thực hiện redirect; không phải cơ chế tự xác thực danh sách URL bên ngoài.

Nếu dự án override handler hoặc request cache, hành vi thực tế có thể khác mặc định. Hãy đọc config đang chạy và test response `Location` thật.

## 5. Giải pháp ít rủi ro nhất: target nội bộ cố định

Nếu không cần quay về trang ban đầu, chọn một trang sau login được mã hóa cố định:

~~~java
@Bean
SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/login", "/error").permitAll()
                    .anyRequest().authenticated())
            .formLogin(form -> form
                    .defaultSuccessUrl("/dashboard", true))
            .build();
}
~~~

Đây là **mảnh cấu hình Spring Security Servlet**, cần `@Configuration`, các import Bean/HttpSecurity/SecurityFilterChain, main Spring Boot, các route thực và user store. Không thể chạy độc lập chỉ bằng javac.

`defaultSuccessUrl("/dashboard", true)` có hai ý nghĩa:

- `/dashboard` là path được chọn trong mã server.
- `true` đặt hành vi “**luôn dùng URL mặc định**”, kể cả khi đã có SavedRequest.

Ngược lại, `defaultSuccessUrl("/dashboard")` với cấu hình mặc định có thể tiếp tục ưu tiên saved request trước rồi mới fallback về dashboard. Điều này không phải một lỗ hổng tự thân, nhưng phải hiểu rõ nhu cầu sản phẩm và nguồn request.

Phương án cố định rất phù hợp cho hệ thống nhỏ, app nội bộ có ít khu vực hoặc các luồng đăng nhập có yêu cầu bảo mật cao. Đánh đổi là người dùng mất deep link sau login.

## 6. Giải pháp linh hoạt: dùng route key thay vì URL

OWASP khuyến nghị ưu tiên **mã đích/short name** rồi ánh xạ nó sang URL đã được server xét duyệt, thay vì cho client nhập URL tùy ý.

Ví dụ:

~~~text
Login form gửi: destination=orders
Server map:       orders -> /orders
Redirect:         /orders
~~~

Bảng allowlist:

| Route key | Path đã duyệt | Policy |
| --- | --- | --- |
| `dashboard` | `/dashboard` | Fallback |
| `orders` | `/orders` | Cần quyền xem orders |
| `profile` | `/account/profile` | User đã đăng nhập |
| `https://evil.example` | Không có mapping | Fallback |
| `//evil.example` | Không có mapping | Fallback |
| `/admin/users` | Không phải route key | Fallback |

### Chương trình Java 17+ độc lập: PostLoginRouteDemo.java

Chương trình sau chọn target từ bảng route cố định và mô phỏng một quyền ứng dụng. Nó không chạy HTTP hoặc Spring; nó minh họa nguyên tắc **client không bao giờ được cung cấp URL đích nguyên bản**.

~~~java
import java.util.Map;
import java.util.Set;

public class PostLoginRouteDemo {

    private static final String DEFAULT = "/dashboard";

    private static final Map<String, String> ROUTES = Map.of(
            "dashboard", "/dashboard",
            "orders", "/orders",
            "profile", "/account/profile");

    static String choose(String requestedRoute, Set<String> authorities) {
        String path = requestedRoute == null
                ? null
                : ROUTES.get(requestedRoute);

        if (path == null) {
            return DEFAULT;
        }

        if (path.equals("/orders")
                && !authorities.contains("ORDER_READ")) {
            return DEFAULT;
        }

        return path;
    }

    public static void main(String[] args) {
        Set<String> withOrders = Set.of("ORDER_READ");
        Set<String> withoutOrders = Set.of();

        System.out.println("Default = " + choose(null, withoutOrders));
        System.out.println("Known route = "
                + choose("orders", withOrders));
        System.out.println("Missing permission = "
                + choose("orders", withoutOrders));
        System.out.println("External URL = "
                + choose("https://evil.example", withOrders));
        System.out.println("Scheme-relative URL = "
                + choose("//evil.example", withOrders));
        System.out.println("Unknown route = "
                + choose("something-else", withOrders));
    }
}
~~~

Biên dịch/chạy với JDK 17 trở lên:

~~~bash
javac PostLoginRouteDemo.java
java PostLoginRouteDemo
~~~

Stdout chính xác:

~~~text
Default = /dashboard
Known route = /orders
Missing permission = /dashboard
External URL = /dashboard
Scheme-relative URL = /dashboard
Unknown route = /dashboard
~~~

Mã `orders` được dịch sang path cố định. Một URL attacker dù hợp lệ về cú pháp cũng không trùng key, nên về dashboard. Quyền `ORDER_READ` ở đây chỉ là minh họa: endpoint thực tế vẫn phải kiểm authorization và quyền trên từng đơn hàng.

**Không làm biến tướng mô hình allowlist** thành `"/" + requestedRoute` hoặc chấp nhận map có thể sửa bởi client. Khi đó dữ liệu không tin cậy lại được ghép vào URL.

## 7. Tích hợp route key với AuthenticationSuccessHandler

Trong Spring Security Servlet, có thể đưa route map vào một success handler tùy biến:

~~~java
@Bean
AuthenticationSuccessHandler approvedDestinationHandler() {
    Map<String, String> routes = Map.of(
            "dashboard", "/dashboard",
            "orders", "/orders",
            "profile", "/account/profile");

    return (request, response, authentication) -> {
        String key = request.getParameter("destination");
        String path = key == null
                ? "/dashboard"
                : routes.getOrDefault(key, "/dashboard");

        // Path là constant ở server, không phải URL do client gửi.
        response.sendRedirect(request.getContextPath() + path);
    };
}

@Bean
SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        AuthenticationSuccessHandler approvedDestinationHandler)
        throws Exception {

    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/login", "/error").permitAll()
                    .anyRequest().authenticated())
            .formLogin(form -> form
                    .successHandler(approvedDestinationHandler))
            .build();
}
~~~

Cần import `java.util.Map`, `org.springframework.context.annotation.Bean`, `org.springframework.security.web.authentication.AuthenticationSuccessHandler`, `org.springframework.security.config.annotation.web.builders.HttpSecurity`, `org.springframework.security.web.SecurityFilterChain`; đặt trong một class Spring configuration. Mảnh này cần form login, user store và các controller ứng dụng. Nó **không phải** Java main độc lập.

**Tính chất bảo vệ:**

- `destination` là dữ liệu client không tin; chỉ được dùng để tra trong map.
- `routes` do server xây, đích là path đã phê duyệt.
- `getContextPath()` hỗ trợ ứng dụng chạy dưới Servlet context path, còn phần path đến từ constant nội bộ.
- Đích không hợp lệ fallback `/dashboard`.
- Endpoint đích vẫn phải áp quyền; nếu có quyền khác nhau cho route, có thể chọn fallback dựa vào `Authentication.getAuthorities()` đã xác minh.

Dùng handler tùy biến như trên **thay** hành vi mặc định của SavedRequestAware handler. Nếu muốn giữ deep link và tránh request cache cũ tồn tại ngoài ý định, hãy thiết kế rõ lifecycle của RequestCache (dọn hoặc tiếp tục dùng theo đúng flow); không vô tình phối hợp hai cơ chế chọn target khác nhau.

### Không cấp quyền dựa trên route hoặc request parameter

Phản ví dụ:

~~~java
// Sai: client không có quyền tự khai mình là ADMIN.
String claimedRole = request.getParameter("role");
if ("ADMIN".equals(claimedRole)) {
    response.sendRedirect("/admin");
}
~~~

Kể cả khi chuyển đến `/admin`, server vẫn phải kiểm role/resource ở endpoint; tốt hơn là không chọn đích admin nếu `Authentication` chưa có quyền. Route target không phải nguồn quyết định role.

## 8. Giữ deep link bằng SavedRequest nhưng không tin Host giả

Nếu muốn đưa người dùng về URL đã cố truy cập trước login:

~~~text
GET /orders/123 (unauthenticated)
    -> lưu request trong session
    -> login
    -> redirect về /orders/123
~~~

Spring Security có thể hỗ trợ bằng RequestCache. Ví dụ DSL:

~~~java
http
    .authorizeHttpRequests(auth -> auth
            .requestMatchers("/login", "/error").permitAll()
            .anyRequest().authenticated())
    .formLogin(form -> form
            .defaultSuccessUrl("/dashboard"));
~~~

Khi có SavedRequest hợp lệ, handler thông thường ưu tiên saved request trước fallback. Tuy nhiên, request ban đầu có thể chịu ảnh hưởng từ **Host**, **scheme**, **port**, context path và proxy headers. Nếu web server/proxy tin các header giả từ Internet, URL tuyệt đối được lưu và tái dựng có thể chứa host ngoài phạm vi.

Ví dụ request đáng ngờ:

~~~http
GET /orders/123 HTTP/1.1
Host: attacker.example
X-Forwarded-Host: attacker.example
X-Forwarded-Proto: https
~~~

Điều kiện khai thác phụ thuộc reverse proxy/container/framework config. **Không khẳng định mọi SavedRequest mặc định đều bị open redirect**, nhưng phải xác minh nguồn thông tin tạo URL.

Chính sách nên kiểm:

1. Edge proxy chỉ tiếp nhận Host công khai nằm trong allowlist.
2. Proxy phải loại bỏ hoặc ghi đè `Forwarded`/`X-Forwarded-*` do client Internet gửi.
3. Backend chỉ tin forwarded headers từ kết nối proxy đã xác thực/cấu hình tin cậy.
4. Không để backend bị truy cập trực tiếp qua mạng ngoài bypass proxy.
5. Kiểm scheme HTTPS, port công khai và context path đúng sau SSL termination.
6. Giới hạn các request được lưu theo scope/method phù hợp; không giữ login/logout/callback hoặc URL chứa secret không cần thiết.
7. Xác thực user/tenant/resource sau redirect, không coi SavedRequest là quyền.

Nếu user mở nhiều tab hoặc đăng nhập bằng tài khoản khác, request cache có thể chứa target cũ. Cần xác định chiến lược cho multi-tab, session timeout và fallback.

## 9. URL nội bộ không đồng nghĩa chuỗi bắt đầu bằng dấu slash là an toàn

Khi sản phẩm bắt buộc hỗ trợ `returnUrl` là path động, bộ kiểm phải xử lý các dạng URL mà browser/proxy có thể diễn giải khác cách kiểm chuỗi của ứng dụng.

| Input | Rủi ro |
| --- | --- |
| `https://evil.example/path` | Redirect tuyệt đối ra domain khác |
| `//evil.example/path` | Scheme-relative URL, host là evil.example |
| `\\evil.example\path` | Backslash có thể được một số stack coi như separator |
| `/%2F%2Fevil.example` | Encoded slash đổi nghĩa khi decode |
| `/%252F%252Fevil.example` | Double decode qua nhiều tầng |
| `/../admin` | Path traversal/canonicalization |
| `https://shop.example.org.evil.net` | Prefix hostname đánh lừa |
| `https://shop.example.org@evil.net` | Userinfo trước dấu @, host thực evil.net |
| `http://shop.example.org` | Downgrade từ HTTPS |
| `javascript:...` hoặc `data:...` | Scheme không phù hợp cho redirect |
| Chuỗi có CR, LF hoặc control chars | Lỗi xử lý header/response splitting ở stack yếu |
| `/orders?redirect=https://evil.example` | Redirect chain qua endpoint nội bộ khác |

**Không** bảo vệ bằng `startsWith("https://shop.example.org")` hoặc `endsWith("example.org")`. Chúng bỏ qua hostname boundary, userinfo, port và canonicalization.

Nếu cho phép return path nội bộ:

1. Ưu tiên **route key** hoặc router allowlist cụ thể trước khi tự parse URL.
2. Nếu cần parse, dùng thư viện URL/URI được bảo trì phù hợp với redirect API và browser, không dùng regex một dòng.
3. Giới hạn kích thước; reject ký tự điều khiển, backslash và format mơ hồ.
4. Từ chối scheme/authority/userinfo, fragment không cần thiết và đường bắt đầu bằng hai dấu slash.
5. Canonicalize và decode đúng một lần theo một contract; không validate trước rồi decode lại sau.
6. Ngăn dot segments, double encoding và path vượt phạm vi route được phép.
7. Áp path allowlist và authorization theo user/tenant/resource.
8. Fallback an toàn khi kiểm không thành công; không cố “sửa” URL attacker rồi gửi tiếp.

`java.net.URI` giúp phân tích scheme/authority/path, nhưng **không đảm bảo mọi browser/proxy diễn giải chuỗi giống Java URI**. Đừng viết validator tùy hứng chỉ để tiết kiệm vài dòng code.

## 10. URL bên ngoài: host allowlist và canonical origin

Nếu ứng dụng phải redirect sang một website đối tác đã phê duyệt, hãy giữ bảng cấu hình do backend quản lý:

~~~text
destination=partnerPortal
    -> https://portal.partner.example/approved/home
~~~

Đó vẫn là một route key, chỉ khác target là một absolute HTTPS URL cố định. Nếu URL ngoài phải động theo nghiệp vụ, validator cần kiểm nhiều hơn:

| Thuộc tính | Chính sách |
| --- | --- |
| Scheme | Chỉ `https` trừ ngoại lệ được duyệt |
| Host | So khớp hostname canonical đầy đủ trong allowlist |
| Port | Chỉ port hiệu lực được duyệt; tránh arbitrary port |
| Userinfo | Từ chối |
| Path | Giới hạn path/prefix đã định nghĩa đúng ranh giới |
| Query | Chỉ cho parameters cần thiết, không chứa secrets |
| Fragment | Thường không cần trong flow server redirect |
| IDN/punycode | Canonicalization rõ để tránh host lookalike |
| Redirect chain | Endpoint bên ngoài có thể tiếp tục điều hướng; cân nhắc cảnh báo |
| Quyền/tenant | Không gửi target riêng tenant tới tenant khác |

Không dùng wildcard `*.example.org` nếu subdomain có thể thuộc người dùng, dịch vụ third-party hoặc không còn được quản lý. Một host “cùng tổ chức” không tự nhiên an toàn cho mọi dữ liệu đăng nhập.

**Redirect sang site đối tác không phải cách truyền phiên đăng nhập.** Không kèm session cookie, access token, OAuth authorization code, reset token hoặc API secret vào URL. Nếu cần federation, dùng OAuth2/OIDC/SAML flow với callback/redirect URI đăng ký chặt.

## 11. OAuth2/OIDC redirect_uri và post-login target khác nhau

Trong OAuth2 login có ít nhất hai bước:

~~~text
RP App -> Authorization Server
       -> Callback /login/oauth2/code/{registrationId}
       -> Xác thực và tạo Authentication
       -> Post-login redirect tới trang ứng dụng
~~~

- **OAuth2 `redirect_uri`**: callback từ authorization server về client; phải được đăng ký hoặc xác thực theo chính sách tại authorization server. Không biến nó thành giá trị tùy ý do browser đưa.
- **Post-login redirect**: website chọn trang người dùng xem sau khi callback đã xác thực xong, ví dụ dashboard hoặc saved request.

Nếu sử dụng Spring Security `oauth2Login()` và success handler tùy biến, handler đó vẫn phải chịu target allowlist. OAuth state/nonce giúp liên kết giao thức login/authorization, **không** có nghĩa bất kỳ `next` nào cũng an toàn.

Với SAML, `RelayState` thường liên quan correlation/state; không lấy giá trị untrusted làm URL điều hướng tùy ý sau xử lý SAMLResponse. Mọi thông điệp danh tính phải được xác minh trước khi thực hiện chuyển hướng nghiệp vụ.

## 12. SPA, deep link và browser storage

SPA thường muốn sau login quay về route đang mở:

~~~text
/checkout/confirm -> hiện login -> đăng nhập -> /checkout/confirm
~~~

Browser có thể lưu intended route trong sessionStorage, state của router hoặc tham số URL. Vì storage do browser kiểm soát, **nó không phải trust anchor**. Khi điều hướng frontend:

- Chỉ cho các route nội bộ có trong router allowlist.
- Không gọi `window.location = untrustedNextUrl`.
- Nếu route có order ID, validate identifier, encode path segment đúng cách và giữ path template cố định.
- Backend phải kiểm quyền với order/tenant ở API endpoint.
- Không đưa login token, authorization code hoặc secret vào URL route.
- Xóa state dự định sau khi dùng và xử lý multiple tabs có mục đích rõ.

Nếu yêu cầu deep link phức tạp và cần tin tưởng mạnh, server có thể cấp **flow ID ngẫu nhiên** rồi lưu intended path đã duyệt trong session/Redis với TTL và account/session binding. Browser gửi flow ID sau login, server truy hồi mục tiêu; flow ID không phải URL.

### Referer không phải chứng cứ cho target

Header `Referer` có thể bị ẩn bởi browser privacy policy, có thể đến từ website ngoài, hoặc bị giả bởi client không phải browser. Không dùng `setUseReferer(true)` làm nguồn redirect đích nếu thiếu kiểm soát. Bật tính năng đó mà không xét nguồn dẫn đến một kênh target không tin cậy khác.

## 13. Kiểm URL và kiểm quyền là hai bước khác nhau

Một URL có thể **nội bộ nhưng bị cấm đối với user**. Ví dụ sau login `user:lan` không có quyền admin, nhưng target trong session là `/admin/users`. Dù `/admin/users` thuộc same-origin, resource phải trả 403 hoặc ứng dụng chọn fallback.

Ngược lại, một user có ROLE_ADMIN không được phép redirect sang trang phishing. Có hai tầng:

1. **Redirect target allowlist**: nguồn target và URL có hợp lệ?
2. **Authorization**: user có quyền với endpoint, tenant, resource không?

Tình huống:

~~~text
Current principal: user:lan (tenant A)
Saved URL:         /tenants/B/invoices/123

Target policy: path có thể thuộc app
Resource policy: user không có quyền tenant B
Decision: từ chối/fallback theo sản phẩm, không cấp quyền B
~~~

Việc người dùng vừa login thành công không giải quyết được tenant isolation. Cần kiểm tại service/repository/query chứ không chỉ ở login success handler.

Nếu app có MFA/step-up nhiều giai đoạn, không redirect tới hành động nhạy cảm và coi “password hợp lệ” là đã hoàn thành mọi authentication factor.

## 14. Các vấn đề liên quan session, CSRF và reverse proxy

**SecurityContext:** chỉ sử dụng `Authentication` đã được provider xác thực; không cấp quyền từ query param, role claim tự khai hoặc route key. Redirect không thay thế authorization filter.

**Session fixation:** Spring Security có chiến lược bảo vệ phiên khi login; nếu lưu target trước login, cần quyết định request cache có còn phù hợp sau session rotation không. Tránh dùng một saved target thuộc flow/user cũ cho account mới.

**CSRF:** với form login/session cookie, áp dụng CSRF protection theo mô hình trình duyệt. Không lấy “POST /login thành công” làm lý do tự tắt CSRF ở mọi endpoint.

**Trusted forwarded headers:** SSL termination/proxy có thể làm backend thấy `http://internal:8080` trong khi public URL là `https://shop.example.org`. Cần cấu hình proxy header trust và public domain whitelist. Không dùng một header từ Internet để tự suy base URL cho redirect.

**Sensitive query:** Không đưa password, access token, session ID, password-reset token vào `Location`. Tránh log redirect target chứa secrets hoặc PII; dùng route ID và correlation ID cho audit nếu có thể.

**Redirect loop:** Không chọn endpoint đăng nhập, logout, callback hoặc recovery làm target mặc định; kiểm loop khi target lại trigger authentication entry point.

## 15. Kiểm thử Location thay vì chỉ kiểm 302

Một bộ test nên quan sát **response Location cuối cùng** của auth success. Chỉ assert status là 302 sẽ bỏ sót redirect ra ngoài.

| Trường hợp | Kỳ vọng |
| --- | --- |
| Login thường không có target | `/dashboard` |
| Destination=orders hợp lệ | `/orders` |
| Route key không biết | Fallback an toàn |
| Target `https://evil.example` | Không xuất hiện trong Location |
| Target `//evil.example` | Không xuất hiện trong Location |
| Backslash/encoded slash/double encoding | Reject/fallback |
| Host/Forwarded giả | Không redirect tới host attacker |
| Saved request hợp lệ từ cùng session | Quay lại path hợp lệ |
| Saved request từ session/tenant cũ | Không được dùng trái policy |
| User không có quyền admin | Không có quyền resource admin |
| URL hợp lệ nhưng resource thuộc tenant khác | 403/404 hoặc fallback theo policy |
| Auth failure | Không gọi success redirect |
| OAuth2/SAML callback | Không nhận next URL untrusted |
| URL có control chars | Không gây header injection |
| Scheme HTTP ở external target | Từ chối nếu chỉ cho HTTPS |
| SPA route chứa token trong query | Không phát tán token ra Location/log |
| Proxy deploy dưới context path | Redirect có path/host công khai đúng |

### Mảnh test MockMvc

Với Spring Boot Servlet có Spring Security Test và test user đã được cung cấp:

~~~java
var response = mockMvc.perform(
        post("/login")
                .param("username", "lan")
                .param("password", "correct-password")
                .param("destination", "https://evil.example")
                .with(csrf()))
        .andReturn()
        .getResponse();

assertEquals("/dashboard", response.getRedirectedUrl());
~~~

Đây là **mảnh test**, cần các static imports `post`, `csrf`, `assertEquals` và thiết lập MockMvc, Spring Security chain, login credentials hợp lệ. Nó kiểm cấu hình route-key handler đã trình bày; không chạy độc lập với javac.

Với context path khác, expected redirect có thể mang prefix. Với OAuth2/SAML, phải test flow callback thực tế; test form login không chứng minh mọi handler đều an toàn.

### Test thuộc tính không phải mã HTTP

- Verify `Location` bằng URL parser và exact host/path expected.
- Thử Host hoặc Forwarded headers bị giả ngay tại reverse proxy ở môi trường test.
- Kiểm quyền resource sau khi follow redirect.
- Kiểm saved request lifecycle, concurrent tabs và session timeout.
- Ghi test về login khi người dùng đổi account/tenant trong cùng browser.

## 16. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Luôn về dashboard thay vì deep link | `alwaysUseDefaultTargetUrl=true` | Quyết định UX; thay config nếu muốn saved request |
| Redirect tới domain lạ | `next`/Referer/Host/forwarded header untrusted | Chuyển route key và xử lý proxy trust |
| Target parameter bị bỏ qua | Handler ưu tiên default/saved request | Kiểm thứ tự handler và config thực tế |
| Deep link mất sau login | RequestCache tắt, session state mất | Xem RequestCache/session lifecycle |
| Login xong bị 403 | Target hợp lệ nhưng thiếu quyền | Kiểm resource authorization, không mở quyền |
| HTTPS bị chuyển về HTTP | Base URL/proxy scheme sai | Fix trusted forwarded headers |
| Redirect loop | Target cũng yêu cầu auth, cookie mất | Kiểm session, security matcher, target |
| Application chạy dưới context path bị 404 | Ghép path/context sai | Dùng context path từ Servlet, test public URL |
| Client thử encoded URL và bypass | Regex/decode nhiều lần | Chỉ route key hoặc dùng parser/allowlist chặt |
| Tenant khác nhận deep link | Saved state không xét tenant | Revalidate user/tenant/resource |
| Logout/OAuth callback bị redirect làm target | Không giới hạn route | Loại endpoint nhạy cảm khỏi allowlist |

Khi debug, log nguồn chọn target (default, saved request, route key), tên route đã được duyệt và quyết định allow/deny. Không ghi raw attacker URL chưa escape, session cookie hoặc query chứa token vào log không được bảo vệ.

## 17. Checklist thiết kế trước triển khai

1. Có thể dùng **một URL nội bộ cố định** sau login không?
2. Nếu cần nhiều trang, đã dùng **route key ánh xạ server-side** thay cho URL do client gửi?
3. Nếu dùng `SavedRequest`, đã kiểm session binding, nguồn scheme/host/port, request method và tenant/account chưa?
4. Có vô tình bật `targetUrlParameter` hoặc `setUseReferer(true)` mà không có allowlist không?
5. Nếu hỗ trợ returnUrl thật, có chống scheme-relative, userinfo, prefix-host, backslash, double encoding và scheme downgrade?
6. Có kiểm cả target policy và quyền truy cập resource?
7. Có chặn spoofed `Host`/`Forwarded` ở proxy và hạn chế backend bypass?
8. Có tránh gửi token/credential/secrets trong Location và audit log?
9. Có giữ CSRF/session fixation/step-up policy thích hợp?
10. Đã kiểm Location và resource access trên form login, OAuth2/SAML nếu dùng, với cả input hợp lệ và độc hại?

**Kết luận:** Chuyển hướng sau đăng nhập chỉ nên đến **URL thuộc chính sách tin cậy của server**. Ưu tiên URL cố định; nếu cần lựa chọn thì dùng route key; nếu cần deep link thì quản lý SavedRequest và xác thực nguồn host/session; nếu buộc có URL ngoài thì allowlist scheme/host/port/path. Spring Security giúp quản lý authentication và redirect flow, nhưng ứng dụng phải chịu trách nhiệm với mọi target được phép và các quyền tại trang đích.

### Tài liệu tham khảo

- Spring Security — Form Login (Servlet): https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html
- Spring Security 6.5 — SavedRequestAwareAuthenticationSuccessHandler: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/SavedRequestAwareAuthenticationSuccessHandler.html
- Spring Security — AbstractAuthenticationTargetUrlRequestHandler: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/AbstractAuthenticationTargetUrlRequestHandler.html
- Spring Security — RequestCache: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/savedrequest/RequestCache.html
- Spring Security — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- OWASP — Unvalidated Redirects and Forwards Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html
- CWE-601 — URL Redirection to Untrusted Site: https://cwe.mitre.org/data/definitions/601.html
