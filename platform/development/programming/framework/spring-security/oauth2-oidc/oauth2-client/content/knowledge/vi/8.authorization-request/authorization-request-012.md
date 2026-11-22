# 8.12. Kiểm soát URL điều hướng sau đăng nhập và nguy cơ open redirect

Trong ứng dụng **Spring Security OAuth 2.0/OIDC Client**, người dùng thường không vào trang đăng nhập chỉ để đăng nhập. Họ muốn thực hiện một công việc cụ thể: xem đơn hàng, mở trang hồ sơ, truy cập báo cáo, hoặc theo một liên kết từ email. Khi xác thực hoàn tất, ứng dụng cần quyết định **đưa trình duyệt đến đâu**.

Việc điều hướng này dễ bị nhầm với `redirect_uri` của OAuth 2.0, nhưng hai khái niệm khác nhau:

- **OAuth redirect URI (callback URI):** địa chỉ trên ứng dụng mà Authorization Server/OpenID Provider (OP) trả **authorization code** và `state` về sau khi người dùng xác thực.
- **Post-login redirect (success destination):** địa chỉ ứng dụng đưa người dùng đến **sau khi đã nhận callback, xác minh kết quả đăng nhập và thiết lập phiên**.

Một ứng dụng có thể có callback cố định `/login/oauth2/code/company` nhưng đưa người dùng sau đăng nhập đến `/dashboard`, `/orders` hoặc trang đã yêu cầu trước đó.

**Nguy cơ open redirect** xuất hiện khi ứng dụng cho phép dữ liệu do người dùng hoặc bên thứ ba kiểm soát quyết định đích chuyển hướng mà không có chính sách kiểm tra phù hợp. Kẻ tấn công có thể lợi dụng tên miền uy tín của ứng dụng để chuyển người dùng sang trang giả mạo, và trong một số kiến trúc sai, còn có nguy cơ rò rỉ mã ủy quyền, token hoặc thông tin nhạy cảm.

Bài học tập trung vào cách kiểm soát đích chuyển hướng trong **Authorization Request và OAuth2 Login trên Spring Security Servlet**, sử dụng cơ chế sẵn có khi phù hợp và chỉ tùy biến khi có yêu cầu nghiệp vụ rõ ràng.

## 1. Hiểu ba bước điều hướng trong OAuth 2.0/OIDC Login

### 1.1. Luồng cơ bản

Giả sử ứng dụng Spring Boot có:

- Ứng dụng web (Relying Party): `https://portal.example.org`.
- OpenID Provider: `https://login.example.org`.
- Registration ID cục bộ: `company`.
- Trang nghiệp vụ người dùng muốn xem: `/orders`.

Một luồng hợp lệ:

```mermaid
sequenceDiagram
    autonumber
    participant B as Trình duyệt
    participant RP as Spring Boot RP
    participant OP as OpenID Provider

    B->>RP: GET /orders
    RP->>RP: Người dùng chưa đăng nhập; lưu requested URL
    RP-->>B: Redirect /login
    B->>RP: GET /login
    RP-->>B: Trang có liên kết /oauth2/authorization/company
    B->>RP: GET /oauth2/authorization/company
    RP->>RP: Tạo authorization request, state và PKCE
    RP-->>B: Redirect OP /authorize
    B->>OP: GET /authorize (client_id, redirect_uri, state, ...)
    OP->>B: Xác thực và chấp thuận nếu cần
    OP-->>B: Redirect callback?code=...&state=...
    B->>RP: GET /login/oauth2/code/company?code=...&state=...
    RP->>OP: Đổi code lấy token (sau kiểm tra state)
    OP-->>RP: Token response (OIDC có ID token)
    RP->>RP: Xác minh kết quả, tạo Authentication và session
    RP-->>B: Redirect /orders (success destination)
    B->>RP: GET /orders với session cookie
    RP-->>B: Trang đơn hàng
```

Trong đó có **ba bước đổi URL cần được phân biệt**:

| Bước | Địa chỉ minh họa | Ai quyết định? | Mục đích |
|---|---|---|---|
| Bắt đầu OAuth Login | `/oauth2/authorization/company` | Cấu hình filter, `registrationId` của Spring | Khởi tạo authorization request |
| OP trả kết quả | `/login/oauth2/code/company` | `ClientRegistration.redirectUri` và cấu hình OP | Nhận code, `state` rồi hoàn tất OAuth/OIDC |
| Sau đăng nhập thành công | `/orders` | Success handler/request cache/chính sách ứng dụng | Trả người dùng đến nơi cần truy cập |

**Không đưa URL tùy ý do browser cung cấp vào OAuth `redirect_uri` chỉ để chọn trang sau đăng nhập.** Callback cần là một endpoint đã đăng ký và được kiểm soát chặt; trang đích sau đăng nhập được quản lý riêng tại RP.

### 1.2. Vì sao ranh giới này quan trọng?

OAuth Authorization Server phải xác minh `redirect_uri` theo registration đã đăng ký. Nếu ứng dụng lấy đích bất kỳ từ query parameter rồi biến nó thành callback, có thể phá vỡ kiểm tra redirect URI và gây nguy cơ **authorization code leakage** nếu AS hoặc ứng dụng xử lý sai.

Ở chiều ngược lại, ngay cả khi OAuth callback hoàn toàn an toàn, một success handler kiểu:

```java
response.sendRedirect(request.getParameter("next"));
```

vẫn có thể biến RP thành **open redirect** nếu giá trị `next` đến từ nguồn không đáng tin.

Hai vấn đề cùng liên quan đến HTTP redirect, nhưng cần xử lý ở **hai điểm bảo mật khác nhau**.

## 2. Open redirect là gì?

**Open redirect** là trường hợp website cho phép người gọi đưa vào một URL đích và website tự chuyển hướng đến đích đó, bất kể nó có thuộc phạm vi được phép hay không.

Ví dụ ứng dụng có endpoint:

```text
GET https://portal.example.org/redirect?next=https://evil.example/phishing
```

Nếu ứng dụng trả:

```http
HTTP/1.1 302 Found
Location: https://evil.example/phishing
```

thì một đường dẫn trên `portal.example.org` đã được dùng để đưa người dùng sang website ngoài ý muốn. Đường dẫn ban đầu thuộc domain uy tín có thể bị dùng trong email, QR code, tin nhắn hoặc chiến dịch lừa đảo.

### 2.1. Kẻ tấn công có thể làm gì?

Tùy cách ứng dụng được xây dựng, open redirect có thể tạo ra:

1. **Phishing:** gửi link trông như bắt đầu từ portal doanh nghiệp, sau đó chuyển người dùng sang trang login giả.
2. **Lạm dụng miền uy tín:** dùng domain của RP làm một bước trung gian để vượt bộ lọc link đơn giản.
3. **Lệch khỏi luồng nghiệp vụ:** sau xác thực, người dùng bị đưa đến trang không do ứng dụng kiểm soát.
4. **Rò rỉ dữ liệu trong một số triển khai sai:** nếu ứng dụng đưa code, token hoặc dữ liệu bí mật vào URL và sau đó điều hướng ra ngoài, những thông tin ấy có thể bị lộ qua URL, log hoặc hành vi trình duyệt.
5. **Chuỗi tấn công OAuth:** endpoint open redirect nằm trong phạm vi URI được Authorization Server tin cậy có thể làm phức tạp hoặc phá vỡ ranh giới callback, nhất là khi có kiểm tra redirect URI lỏng lẻo.

Không phải open redirect nào cũng tự động làm lộ token. Tác động phụ thuộc vị trí redirect, cookie, chính sách trình duyệt và cách ứng dụng/AS xử lý OAuth. Tuy nhiên, đây vẫn là lỗi cần loại bỏ vì đích bên ngoài **không được người dùng và ứng dụng xác nhận một cách đáng tin**.

### 2.2. Dấu hiệu thường gặp trong code

Các mẫu dễ gây rủi ro:

```java
// Ví dụ cố ý không an toàn: không dùng trong ứng dụng thực tế
@GetMapping("/go")
public void go(@RequestParam String target,
               HttpServletResponse response) throws IOException {
    response.sendRedirect(target);
}
```

```java
// Ví dụ cố ý không an toàn: tùy chỉnh success handler thiếu kiểm soát
.oauth2Login(oauth2 -> oauth2
    .successHandler((request, response, authentication) -> {
        String next = request.getParameter("next");
        response.sendRedirect(next);
    }))
```

```java
// Ví dụ có thể nguy hiểm nếu value do người dùng kiểm soát
successHandler.setTargetUrlParameter("redirectTo");
successHandler.setUseReferer(true);
```

Hai API `setTargetUrlParameter(...)` và `setUseReferer(true)` không tự xác minh một địa chỉ bên ngoài có được phép làm đích đến của ứng dụng hay không. Khi bật các cơ chế chọn đích bằng input, cần thiết kế chính sách đích chặt chẽ.

## 3. Các nguồn đích redirect sau đăng nhập

Sau khi Spring Security xác thực thành công, ứng dụng có thể chọn URL theo các nguồn sau:

| Nguồn | Ví dụ | Đặc điểm |
|---|---|---|
| **Đường dẫn mặc định của ứng dụng** | `/dashboard` | Do server cấu hình; đơn giản và dễ kiểm soát |
| **Request đã được lưu** | Người dùng yêu cầu `/orders/42` trước login | Spring RequestCache/SavedRequest giúp quay lại mục đích ban đầu |
| **Lựa chọn nghiệp vụ có giới hạn** | `go=orders`, `go=profile` | Server ánh xạ mã lựa chọn thành đường dẫn cố định |
| **Query parameter chứa URL tự do** | `?next=https://...` | Không đáng tin nếu không có chính sách validate |
| **HTTP Referer** | Trang trước đó trong browser | Dễ thiếu, bị kiểm soát một phần hoặc không phản ánh đích được phép |
| **Thông tin sâu trong OAuth `state`** | Ý định quay về `/orders` sau login | Chỉ an toàn khi gắn với yêu cầu, kiểm tra toàn vẹn và giới hạn đích; `state` không tự validate URL |
| **Host/protocol từ reverse proxy header** | `Forwarded`, `X-Forwarded-Host` | Chỉ được tin khi proxy và trust boundary được cấu hình đúng |

Nên ưu tiên **URL nội bộ được xác định bởi server** hoặc **SavedRequest do cơ chế Spring Security quản lý**, tùy trải nghiệm. Nếu business thực sự cần đích do người dùng lựa chọn, nên nhận một **mã đích đã allowlist**, không chấp nhận một URL bất kỳ.

## 4. Spring Security chọn trang sau đăng nhập như thế nào?

### 4.1. Default success handling

Trong ứng dụng Servlet OAuth2 Login, Spring Security sử dụng cơ chế `AuthenticationSuccessHandler` sau khi xác thực thành công. Một thành phần thường được dùng là **`SavedRequestAwareAuthenticationSuccessHandler`**.

Nguyên tắc hoạt động:

1. Khi người dùng chưa xác thực truy cập trang được bảo vệ, request có thể được lưu bởi `RequestCache`.
2. Người dùng đi qua trang login và OAuth/OIDC flow.
3. Sau xác thực thành công, success handler có thể khôi phục đích từ saved request.
4. Nếu không có request đã lưu, ứng dụng sử dụng đích mặc định.

Ví dụ: truy cập `/orders` trước login thì sau login thường quay lại `/orders`; truy cập trực tiếp `/oauth2/authorization/company` khi không có saved request thì dùng đường dẫn fallback.

**RequestCache không phải kho chứa URL tùy ý để tin mù quáng.** Nên giữ hành vi của framework, không tự thay request cache bằng dữ liệu lấy trực tiếp từ query string, và kiểm soát các request/host/header đưa vào ứng dụng theo chính sách triển khai.

### 4.2. `defaultSuccessUrl`

Một cấu hình thường gặp:

```java
http.oauth2Login(oauth2 -> oauth2
    .loginPage("/login")
    .defaultSuccessUrl("/dashboard"));
```

Với biến thể một tham số, `/dashboard` là URL mặc định khi không có saved request phù hợp. Nếu người dùng yêu cầu trang được bảo vệ trước login, cơ chế saved request có thể vẫn được ưu tiên.

Nếu ứng dụng muốn **luôn** đưa mọi người về dashboard:

```java
http.oauth2Login(oauth2 -> oauth2
    .loginPage("/login")
    .defaultSuccessUrl("/dashboard", true));
```

Đối số `true` thể hiện lựa chọn **luôn sử dụng trang thành công mặc định**, kể cả đã có request trước đó. Đây là quyết định UX: phù hợp cổng thông tin chỉ có một điểm bắt đầu, nhưng không phù hợp nếu người dùng cần truy cập deep link sau đăng nhập.

### 4.3. Khai báo handler rõ ràng với SavedRequestAwareAuthenticationSuccessHandler

Ví dụ Spring Security Servlet:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.SavedRequestAwareAuthenticationSuccessHandler;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        var success = new SavedRequestAwareAuthenticationSuccessHandler();
        success.setDefaultTargetUrl("/dashboard");
        success.setAlwaysUseDefaultTargetUrl(false);

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error", "/css/**")
                .permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .loginPage("/login")
                .successHandler(success));

        return http.build();
    }
}
```

Các điểm cần hiểu:

- `setDefaultTargetUrl("/dashboard")` đặt fallback cố định do server quyết định.
- `setAlwaysUseDefaultTargetUrl(false)` cho phép logic saved request được cân nhắc.
- Không bật `targetUrlParameter` hoặc `useReferer` để tự động lấy URL bất kỳ từ browser.
- Đường dẫn `/login` và tài nguyên CSS phải được truy cập bởi người dùng chưa đăng nhập.

Không cần tự tạo handler này nếu cấu hình mặc định và `defaultSuccessUrl(...)` đã đáp ứng yêu cầu. Càng ít logic tự dựng URL, diện tích tấn công càng nhỏ.

## 5. Sử dụng SavedRequest để trở lại trang trước đăng nhập

### 5.1. Tình huống deep link

Một email nội bộ chứa link:

```text
https://portal.example.org/orders/742
```

Người dùng chưa đăng nhập. Ứng dụng cần:

1. Yêu cầu xác thực trước khi trả dữ liệu.
2. Giữ thông tin request được phép khôi phục thông qua RequestCache/session.
3. Cho người dùng hoàn thành OAuth2 Login.
4. Quay lại `/orders/742`.
5. **Kiểm tra quyền xem đơn hàng 742 sau xác thực**, thay vì giả định người đã đăng nhập có quyền đối với tài nguyên.

SavedRequest giúp bảo toàn **đích điều hướng**; nó không phải cơ chế phân quyền. Authorization tại controller/service/API vẫn là điều kiện bắt buộc.

### 5.2. Điều gì thường được lưu?

`HttpSessionRequestCache` có thể lưu thông tin về request ban đầu trong HTTP session, như URL và thông tin cần thiết cho request matching/replay theo cơ chế framework. `SavedRequestAwareAuthenticationSuccessHandler` sử dụng thông tin này để quyết định redirect.

Không biến SavedRequest thành nơi lưu những URL vốn đã không được kiểm soát. Trong một ứng dụng có nhiều domain/proxy, cần tránh host-header poisoning và xác định host/scheme hợp lệ ở tầng ingress. Nếu ứng dụng tự triển khai RequestCache, phải giữ ranh giới giữa input HTTP bên ngoài và đích redirect đáng tin.

### 5.3. Hành vi khi người dùng vào thẳng màn hình login

Nếu người dùng truy cập:

```text
GET https://portal.example.org/login
```

sau đó chọn login với OP, thường không có một request nghiệp vụ nào đã được lưu. Khi ấy fallback `/dashboard` hoặc `/` là lựa chọn hợp lý.

Nếu người dùng đăng nhập từ một đường dẫn trong email, không nhất thiết phải tạo thêm `?next=...`; RequestCache đã hỗ trợ nhiều trường hợp deep link của ứng dụng session-based.

### 5.4. Những giới hạn cần cân nhắc

- Session/request cache có thể bị mất do hết hạn phiên hoặc cấu hình cookie.
- Khi triển khai nhiều instance, trạng thái authorization request và saved request có thể cần session store dùng chung.
- Bắt đầu nhiều login flow trong nhiều tab có thể tạo các tình huống cạnh tranh state/request cần được framework và kiến trúc giải quyết.
- Request ban đầu chứa dữ liệu nhạy cảm trong query string cần được xử lý thận trọng về log và redirect.
- Những endpoint như `/logout`, callback OAuth hoặc API endpoint không nhất thiết là đích thích hợp sau login; ứng dụng có thể cần chính sách chọn đích riêng.

## 6. Ví dụ nguy hiểm: tham số next quyết định redirect

Giả sử một trang login hỗ trợ:

```text
/login?next=/orders
```

Một lập trình viên viết:

```java
String next = request.getParameter("next");
response.sendRedirect(next);
```

Kẻ tấn công có thể sửa URL:

```text
/login?next=https://attacker.example/fake-login
```

Nếu ứng dụng dùng input này tại success handler, trình duyệt có thể rời portal sau khi đăng nhập. Một số payload không cần chứa `https://` trực tiếp:

```text
//attacker.example/path
\attacker.example\path
/%2F%2Fattacker.example/path
https://portal.example.org.attacker.example/
https://portal.example.org@attacker.example/path
https:%2f%2fattacker.example/path
```

Các ví dụ trên cho thấy những cách biểu diễn URL dễ gây nhầm lẫn. **Không phải mọi payload đều hoạt động với mọi parser, container hoặc browser**; mục đích là giải thích vì sao kiểm tra chuỗi đơn giản dễ sai khi phần mềm qua nhiều tầng decoding/normalization.

### 6.1. Vì sao `startsWith` không đủ?

Ví dụ:

```java
// Ví dụ cố ý không an toàn
if (next.startsWith("https://portal.example.org")) {
    response.sendRedirect(next);
}
```

Điều kiện này có thể chấp nhận:

```text
https://portal.example.org.attacker.example/login
```

vì chuỗi bắt đầu bằng prefix giống host được tin. Nhưng **hostname thực tế là `portal.example.org.attacker.example`**, không phải `portal.example.org`.

Một kiểu sai khác:

```java
// Ví dụ cố ý không an toàn
if (next.startsWith("/")) {
    response.sendRedirect(next);
}
```

Chuỗi `//attacker.example/path` bắt đầu bằng `/`, nhưng trong ngữ cảnh URL nó có thể được hiểu là **network-path reference** đến host bên ngoài.

Kiểm tra URL an toàn không chỉ là kiểm tra prefix string. Nếu không có nhu cầu đích ngoài, cách tốt nhất là **đừng cho browser cung cấp URL tự do**.

### 6.2. Rủi ro khi tin HTTP Referer

`Referer` không phải nguồn xác thực ý định của người dùng. Nó có thể bị thiếu do chính sách privacy, có thể phản ánh một trang ngoài hệ thống, và trong một số tình huống có thể bị bên gọi kiểm soát.

Đặt `setUseReferer(true)` để chuyển hướng sau login mà không có kiểm tra đích có thể khiến người dùng rời ứng dụng đến nguồn không mong muốn. Nên dùng saved request hoặc fallback cố định thay vì coi Referer là danh sách đích tin cậy.

## 7. Thiết kế an toàn: dùng mã đích và allowlist phía server

Nếu giao diện thật sự cần chuyển sau login đến những trang khác nhau, hãy truyền **ý định nghiệp vụ** thay vì URL.

Thay vì:

```text
/login?next=https://any-domain.example/path
```

dùng một trong các mã được chấp nhận:

```text
/sign-in?go=orders
/sign-in?go=profile
/sign-in?go=dashboard
```

Backend ánh xạ các mã này đến **đường dẫn cố định do server định nghĩa**:

| Mã `go` | Đích do server quyết định |
|---|---|
| `orders` | `/orders` |
| `profile` | `/profile` |
| `dashboard` | `/dashboard` |
| Giá trị khác/thiếu | `/dashboard` |

Cách này làm thay đổi bài toán từ “parse và tin một URL do bên ngoài cung cấp” thành “chọn một mục trong danh sách server đã công bố”.

### 7.1. Controller ghi lại ý định trước khi bắt đầu OAuth

Ví dụ Spring MVC:

```java
import java.util.Map;

import jakarta.servlet.http.HttpSession;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@Controller
public class SignInController {

    private static final String LOGIN_GO = "LOGIN_GO";

    private static final Map<String, String> ALLOWED_GO = Map.of(
        "orders", "/orders",
        "profile", "/profile",
        "dashboard", "/dashboard"
    );

    @GetMapping("/sign-in")
    public String signIn(
            @RequestParam(required = false) String go,
            HttpSession session) {

        String selected =
            go != null && ALLOWED_GO.containsKey(go) ? go : "dashboard";
        session.setAttribute(LOGIN_GO, selected);

        return "sign-in";
    }
}
```

Điều kiện `go != null` xử lý trường hợp người dùng không chọn đích và tránh truyền `null` vào `Map.of().containsKey(...)`. Với người dùng chưa đăng nhập, route `/sign-in` phải được `permitAll()`.

### 7.2. Trang login chỉ chứa liên kết bắt đầu xác thực

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Đăng nhập</title>
</head>
<body>
<main>
    <h1>Đăng nhập hệ thống</h1>
    <a th:href="@{/oauth2/authorization/company}">
        Đăng nhập qua tài khoản công ty
    </a>
</main>
</body>
</html>
```

Trang HTML không giữ URL bên ngoài và không sửa `redirect_uri`. Khi người dùng nhấn nút, Spring Security tạo authorization request bình thường và gắn nó với state/session tương ứng.

### 7.3. Success handler ánh xạ mã đích thành đường dẫn cố định

```java
import java.io.IOException;
import java.util.Map;

import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;

import org.springframework.security.core.Authentication;
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;
import org.springframework.security.web.DefaultRedirectStrategy;
import org.springframework.security.web.RedirectStrategy;
import org.springframework.stereotype.Component;

@Component
public class SafeLoginSuccessHandler implements AuthenticationSuccessHandler {

    private static final String LOGIN_GO = "LOGIN_GO";

    private static final Map<String, String> ROUTES = Map.of(
        "orders", "/orders",
        "profile", "/profile",
        "dashboard", "/dashboard"
    );

    private final RedirectStrategy redirectStrategy = new DefaultRedirectStrategy();

    @Override
    public void onAuthenticationSuccess(
            HttpServletRequest request,
            HttpServletResponse response,
            Authentication authentication)
            throws IOException, ServletException {

        HttpSession session = request.getSession(false);
        String selected = null;

        if (session != null) {
            Object value = session.getAttribute(LOGIN_GO);
            if (value instanceof String go) {
                selected = go;
            }
            session.removeAttribute(LOGIN_GO);
        }

        String destination = selected == null
            ? "/dashboard"
            : ROUTES.getOrDefault(selected, "/dashboard");

        redirectStrategy.sendRedirect(request, response, destination);
    }
}
```

Đoạn code không lấy URL từ `request.getParameter("next")` sau callback. Nó chỉ chọn **một trong ba route được khai báo trong chương trình**, rồi xóa ý định đã dùng khỏi session để tránh ảnh hưởng lần đăng nhập tiếp theo.

Nếu ứng dụng cần lưu `go` theo từng authorization request hoặc có nhiều login tab đồng thời, cần liên kết ý định với từng `state` thay vì dùng một thuộc tính session chung có thể bị ghi đè. Điều này quan trọng với kiến trúc nhiều provider hoặc nhiều flow song song.

### 7.4. Gắn success handler vào OAuth2 Login

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(
            HttpSecurity http,
            SafeLoginSuccessHandler loginSuccessHandler) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/", "/sign-in", "/error", "/assets/**"
                ).permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .loginPage("/sign-in")
                .successHandler(loginSuccessHandler));

        return http.build();
    }
}
```

Với handler này, **mã `go` đã chọn có ưu tiên**, và request cache thông thường **không tự được sử dụng** theo cách của `SavedRequestAwareAuthenticationSuccessHandler`. Nếu muốn ưu tiên deep link đã lưu, cần xây rõ thứ tự ưu tiên và sử dụng RequestCache phù hợp. Không thay handler mặc định nếu mục tiêu chỉ là cho người dùng quay lại URL họ đã truy cập trước login.

Cũng cần xét vị trí lưu state khi Spring Security đổi session ID sau đăng nhập để chống session fixation; cơ chế session migration mặc định thường bảo toàn session attributes. Nếu ứng dụng tùy chỉnh session management, phải xác định dữ liệu ý định login được giữ và xóa đúng thời điểm.

### 7.5. Vì sao phương pháp mã đích an toàn hơn URL tự do?

- Kẻ tấn công không thể chọn một hostname ngoài allowlist chỉ bằng đổi query parameter.
- Các đường dẫn đích có thể được kiểm soát qua code review.
- Có thể ràng buộc mỗi mã với role hoặc điều kiện nghiệp vụ.
- Không có nhu cầu tự viết URL parser phức tạp.
- Dễ kiểm thử theo bảng các mã hợp lệ và một fallback cố định.

Lưu ý: việc điều hướng đến `/orders` **không cấp quyền**. Endpoint `/orders` vẫn cần xác thực và phân quyền như bình thường. Sau login, nếu một tài khoản không có quyền truy cập trang đó, ứng dụng nên trả `403` hoặc trang hướng dẫn phù hợp.

## 8. Nếu buộc phải hỗ trợ URL động, cần giới hạn thế nào?

Có sản phẩm cần giữ deep link thay đổi theo ID, ví dụ `/orders/742?tab=history`. Khi không thể dùng một tập route cố định, chính sách redirect cần nghiêm ngặt hơn.

**Ưu tiên theo thứ tự:**

1. **SavedRequest:** nếu người dùng thực sự vào deep link ở cùng ứng dụng trước login, để RequestCache xử lý.
2. **Mã đích và dữ liệu tham số tách biệt:** ví dụ `go=order&id=742`; server kiểm tra ID, xây route `/orders/742` bằng route builder của ứng dụng.
3. **Đường dẫn nội bộ được parse và kiểm soát:** nếu nhận một path, chấp nhận theo danh sách route pattern; không cho phép scheme, authority, backslash hoặc path vượt ra ngoài phạm vi.
4. **External URL đã allowlist chặt:** chỉ khi nghiệp vụ cần điều hướng đến ứng dụng khác có tên miền/cấu hình đã xác định.

### 8.1. Kiểm soát đích cùng origin

Chỉ nhận URL có dạng relative-path do ứng dụng phục vụ có thể giảm rủi ro. Nhưng các chuỗi như `//host`, backslash, dấu phân cách mã hóa, ký tự điều khiển hoặc URL qua nhiều lần decode có thể gây sai lệch giữa Java, servlet container, proxy và browser.

Vì vậy, không tự viết validator chỉ bằng:

```java
next.startsWith("/")
```

rồi cho mọi route đi qua. Nếu cần hỗ trợ path động, nên dùng bộ parser/cơ chế chuẩn hóa URL tin cậy và kiểm tra **sau khi canonicalize**, đồng thời đối chiếu với các route mẫu cụ thể; hoặc xây path từ ID đã được validate bằng controller/server.

Một lựa chọn server-side thường dễ kiểm soát hơn:

```text
Yêu cầu: /sign-in?go=order&id=742
Sau khi xác thực:
  go == order
  id là định danh theo định dạng cho phép
  tài khoản được phép xem order 742
  -> /orders/742
```

Ứng dụng không cần chấp nhận một URL string tùy ý, và business service vẫn kiểm tra authorization khi người dùng truy cập tài nguyên.

### 8.2. Nếu phải chuyển sang website ngoài

Đôi khi RP phục vụ cổng đăng nhập tập trung rồi chuyển người dùng đến một ứng dụng riêng. Trường hợp này cần một **danh sách đích server-side chính xác** và một giao thức tin cậy giữa các ứng dụng. Không cho phép một tham số `next` tự do chỉ vì hostname “có vẻ thuộc công ty”.

Ví dụ danh sách tĩnh:

```java
private static final Map<String, String> EXTERNAL_DESTINATIONS = Map.of(
    "hr", "https://hr.example.org/",
    "docs", "https://docs.example.org/"
);
```

Chỉ truyền `destination=hr` hoặc `destination=docs`, rồi server chọn URL cố định từ map. Không nhận URL arbitrary sau login.

Nếu bắt buộc kiểm tra URL do nguồn bên ngoài cung cấp, cần so sánh URI đã parse theo các thuộc tính:

- Scheme `https` (trừ ngoại lệ dev được quản lý).
- Host đúng hostname được đăng ký, sau canonicalization/IDNA xử lý nhất quán.
- Port đúng giá trị cho phép, không dùng một port tùy ý.
- Không có `userinfo` (`user@host`) gây nhầm chủ thể host.
- Path và query thuộc những mẫu đã được phép.
- Không có network-path reference, backslash, redirect chaining hoặc ký tự điều khiển.
- Không có khả năng redirect tiếp từ đích được allowlist sang miền không đáng tin, nếu chuỗi đó thuộc trách nhiệm hệ thống.

**Không so hostname bằng string prefix hay chỉ so suffix thiếu ranh giới nhãn DNS.** `example.org.attacker.test` không thuộc `example.org`, và ký tự `@` có thể khiến phần trông giống domain lại là userinfo chứ không phải host.

### 8.3. Deep link có token hay mã phiên riêng cần giao thức khác

Nếu ứng dụng cần chuyển người dùng sang một domain khác sau đăng nhập, không truyền ID token, access token hoặc refresh token qua query parameter `next`. Mỗi ứng dụng RP nên thực hiện đăng nhập OIDC theo registration của mình, hoặc dùng một giao thức handoff có ràng buộc bảo mật, thời hạn ngắn và người nhận xác định.

Không xem open redirect như một cơ chế SSO giữa các ứng dụng. SSO được hỗ trợ nhờ phiên OP và giao thức OIDC, không cần các RP chuyển tiếp token bí mật qua URL tùy ý.

## 9. Liên hệ với OAuth Authorization Request và redirect_uri

### 9.1. redirect_uri là callback đã đăng ký với AS

Trong Spring Boot:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
```

Thông thường:

```text
Registration ID: company
Redirect callback: https://portal.example.org/login/oauth2/code/company
Post-login destination: /dashboard (hoặc SavedRequest)
```

Mặc định `/oauth2/authorization/company` là **đường dẫn bắt đầu authorization request** trên ứng dụng Spring. Nó không phải callback.

Tham số `redirect_uri` mà RP gửi đến OP phải khớp URI đã đăng ký/chính sách của OP. Các cách dùng wildcard hoặc prefix matching lỏng lẻo tại AS làm tăng nguy cơ mã ủy quyền bị gửi sai nơi.

### 9.2. Không ghép next vào callback từ browser

Một pattern sai:

```java
// Ví dụ cố ý không an toàn
String next = request.getParameter("next");
authorizationRequest = OAuth2AuthorizationRequest
    .from(authorizationRequest)
    .redirectUri(next)
    .build();
```

Nếu `next` là URL ngoài hệ thống, ứng dụng đã thay đổi đích nhận code. Một Authorization Server tuân thủ quy tắc redirect URI có thể từ chối yêu cầu; nhưng ứng dụng không nên dựa vào AS để sửa một thiết kế định tuyến sai.

Cách đúng là giữ callback được cấu hình tin cậy, rồi xử lý ý định post-login **sau khi OAuth flow kết thúc**.

### 9.3. State không phải nơi tin cậy URL bất kỳ

Tham số `state` dùng để ràng buộc authorization response với yêu cầu mà client đã khởi tạo, hỗ trợ phòng chống CSRF và nhầm callback. Nó **không tự xác minh một URL post-login có an toàn hay không**.

Ví dụ sai về ý tưởng:

```text
state = "https://attacker.example/collect"
Sau callback: sendRedirect(state)
```

Một giá trị `state` ngẫu nhiên/không thể đoán và một tham số `next` tự do là hai thứ khác nhau. Nếu ứng dụng cần liên kết ý định redirect với flow, nên lưu một **khóa tham chiếu ngẫu nhiên hoặc mã đích đã allowlist** trong trạng thái server-side gắn với authorization request; sau callback chỉ dùng khi request đã được xác minh và giá trị đích đáp ứng chính sách.

Không bỏ kiểm tra `state` hoặc cho rằng có PKCE nên có thể dùng bất kỳ redirect target nào. PKCE giúp bảo vệ việc đổi authorization code, nhưng không phải bộ lọc URL.

### 9.4. Nonce và PKCE giải quyết những vấn đề khác

| Cơ chế | Chức năng | Có chống open redirect không? |
|---|---|---|
| `state` | Gắn authorization response với request ban đầu | Không tự validate URL |
| `nonce` trong OIDC | Ràng buộc ID token với yêu cầu xác thực | Không |
| PKCE | Ràng buộc authorization code exchange với verifier | Không |
| Đối chiếu `redirect_uri` | Ngăn AS phát code đến callback không hợp lệ | Bảo vệ biên callback, không kiểm soát success URL |
| Success redirect allowlist | Giới hạn đích sau login | **Có, cho phạm vi post-login** |
| Authorization tại endpoint nghiệp vụ | Xác định quyền truy cập tài nguyên | Không phải URL validator; vẫn bắt buộc |

Một hệ thống an toàn cần **đồng thời** giữ đầy đủ kiểm tra giao thức và kiểm soát success URL.

## 10. Reverse proxy, forwarded headers và Host header

### 10.1. Base URL có thể đến từ request

Trong triển khai thông thường:

```text
Browser -> https://portal.example.org
             |
             v
      Reverse proxy / Load balancer
             |
             v
        http://spring:8080
```

Spring Boot có thể dựa trên request/forwarded headers để xác định `{baseUrl}` và tạo callback URI. Nếu hạ tầng tin `Forwarded` hoặc `X-Forwarded-Host` từ nguồn không tin cậy, ứng dụng có thể sinh URL dựa trên **host do người gửi thao túng**.

Đây là rủi ro về trust boundary: phản hồi redirect hoặc URL sinh tự động có thể trỏ sai domain, kể cả khi mã của ứng dụng không trực tiếp đọc tham số `next`.

### 10.2. Cách thiết kế

- Đặt public origin hợp lệ trong cấu hình hạ tầng và đăng ký đúng redirect URI tại OP.
- Chỉ chấp nhận forwarded headers từ proxy/ingress tin cậy; chặn hoặc ghi đè headers do client Internet tự gửi.
- Cấu hình Spring Boot `server.forward-headers-strategy` phù hợp với kiến trúc, nhưng không xem việc bật property là đủ nếu proxy vẫn để lọt header giả.
- Giới hạn Host hợp lệ tại ingress và kiểm soát domain phục vụ RP.
- Ưu tiên relative target cho điều hướng nội bộ và không tự ghép absolute URL dựa trên Host tùy ý.

Ví dụ property trong một hạ tầng reverse proxy tin cậy:

```yaml
server:
  forward-headers-strategy: framework
```

Cấu hình này chỉ nên được dùng khi đường truyền header đã được kiểm soát. Mọi phiên bản Spring Boot/container có thể xử lý forwarded headers khác nhau; cần căn cứ vào triển khai thực tế để xác định đường đi của thông tin host/scheme.

## 11. Multi-provider và multi-tenant: hai lớp allowlist

Một trang login có thể hiển thị nhiều nhà cung cấp:

```text
/oauth2/authorization/company
/oauth2/authorization/partner
```

Phần `company`/`partner` là **registration ID**, không phải URL đích. Nếu người dùng có thể chọn provider từ tham số:

```text
/sign-in?provider=company&go=orders
```

ứng dụng cần kiểm soát **hai thứ riêng**:

1. `provider` chỉ được ánh xạ tới registration ID tồn tại và được chính sách cho phép.
2. `go` chỉ được ánh xạ tới post-login destination được cho phép.

Không xây:

```text
/oauth2/authorization/{untrusted-provider}
/login/oauth2/code/{untrusted-return-host}
/success?next={arbitrary-url}
```

từ input tự do rồi giả định Spring hoặc OP tự xác minh toàn bộ mục đích nghiệp vụ.

### 11.1. Tenant-specific destination

Ví dụ người dùng thuộc tenant A được quay về `/tenant/a/home`, còn tenant B về `/tenant/b/home`. Không cho phép browser tự chọn tenant rồi redirect tới bất kỳ vùng nào.

Có thể:

- Dựa trên thông tin tenant đã được xác minh sau OIDC Login (issuer/claim/ánh xạ tài khoản).
- Tra tenant mà user được phép truy cập trong dữ liệu nội bộ.
- Xây route với tenant ID đã kiểm tra, hoặc chọn từ bảng route do server quản lý.
- Giữ authorization tại mỗi endpoint; redirect không đồng nghĩa quyền.

Nếu cần nhiều OP, phải xác định issuer/registration đáng tin cho từng tenant, tránh lựa chọn issuer hoặc token endpoint trực tiếp từ URL user cung cấp.

## 12. Thứ tự ưu tiên redirect trong ứng dụng thực tế

Một sản phẩm có thể có nhiều “mong muốn đi tới đâu” cùng lúc:

- Deep link ban đầu đến `/orders/742`.
- Mã đích từ một nút login trên trang chủ.
- Trang dashboard mặc định.
- Điều kiện onboarding bắt buộc sau lần đăng nhập đầu tiên.

Nên chọn **quy tắc ưu tiên rõ ràng**.

Ví dụ:

1. Nếu tài khoản chưa hoàn tất onboarding, đưa về **đường dẫn onboarding cố định**.
2. Nếu có saved request hợp lệ đến một trang thuộc phạm vi ứng dụng, và user có thể truy cập, dùng saved request.
3. Nếu user đã chọn mã đích được allowlist trong flow hiện tại, ánh xạ mã đó thành route.
4. Nếu không có trường hợp nào, chuyển về `/dashboard`.

Thứ tự này là **ví dụ chính sách nghiệp vụ**, không phải hành vi mặc định bắt buộc của Spring Security. Ứng dụng cần thực hiện kiểm tra trước khi chuyển hướng và vẫn phải kiểm tra quyền ở trang nhận request.

Nếu muốn người dùng chọn mã đích **ưu tiên hơn** saved request, phải quyết định và triển khai thứ tự ngược lại một cách chủ động. Tránh để nhiều success handler, target URL parameter và saved request cùng cạnh tranh mà không biết cái nào thắng.

### 12.1. Vấn đề onboarding

Người dùng vừa đăng nhập OIDC, nhưng phải xác minh điều kiện ứng dụng trước khi xem tài nguyên. Ứng dụng có thể đưa họ về `/onboarding` ngay sau login.

Điều đó **không** làm OP xác thực mạnh hơn và cũng không tự cấp quyền. Trong security rules, endpoint nghiệp vụ vẫn phải kiểm tra trạng thái onboarding hoặc quyền truy cập phù hợp, tránh người dùng truy cập thẳng `/orders/742` để bỏ qua bước bắt buộc.

### 12.2. Vấn đề login thất bại

Không nhầm **failure URL** với **success destination**. Khi OP từ chối đăng nhập hoặc callback không hợp lệ, Spring có thể chuyển người dùng về `/login?error`. Error handler không nên chuyển sang một `next` bất kỳ do browser gửi.

Ví dụ:

```java
.oauth2Login(oauth2 -> oauth2
    .loginPage("/login")
    .defaultSuccessUrl("/dashboard")
    .failureUrl("/login?error"))
```

Trang lỗi nên hiển thị thông báo phù hợp, không phát tán authorization code, ID token, access token hoặc exception nội bộ vào query string.

## 13. Những tình huống lỗi thường gặp

### Tình huống A — User đến một trang nội bộ từ email

**Yêu cầu:** Người dùng mở `/documents/123` khi chưa đăng nhập; sau OIDC Login muốn quay về đúng tài liệu.

**Thiết kế phù hợp:** Bảo vệ `/documents/123` bằng security rules; dùng `SavedRequestAwareAuthenticationSuccessHandler`/RequestCache để giữ request ban đầu. Sau login, endpoint tài liệu tiếp tục kiểm tra user có quyền xem tài liệu 123.

Không cần tạo `?next=https://portal.example.org/documents/123` nếu cơ chế saved request đã đáp ứng.

### Tình huống B — Người dùng có thể gửi URL ngoài vào login

**Yêu cầu ban đầu:** `/login?next=/orders`.

**Lỗi:** Ứng dụng redirect trực tiếp đến `next` sau login, nên `next=https://attacker.example` cũng hoạt động.

**Thiết kế phù hợp:** Dùng mã `go=orders` và map phía server, hoặc chỉ cho phép route nội bộ sau khi parse/canonicalize và đối chiếu chính sách. Không dùng string prefix host/path đơn giản.

### Tình huống C — Host header bị thay đổi tại proxy

**Biểu hiện:** Redirect callback hoặc link absolute trong ứng dụng trỏ tới hostname không phải domain sản phẩm.

**Nguyên nhân có thể:** Reverse proxy chuyển tiếp `Host`/`X-Forwarded-Host` do client cung cấp hoặc ứng dụng suy ra `{baseUrl}` từ headers không được kiểm soát.

**Thiết kế phù hợp:** Cho phép danh sách host tại ingress, cấu hình forwarded headers từ proxy tin cậy và dùng callback URI đã đăng ký chính xác với OP.

### Tình huống D — Login success handler luôn đưa về dashboard

**Biểu hiện:** Mở `/orders/742` rồi đăng nhập nhưng lại về `/dashboard`.

**Nguyên nhân:** Có thể đã cấu hình `defaultSuccessUrl("/dashboard", true)` hoặc custom success handler bỏ qua SavedRequest.

**Thiết kế phù hợp:** Nếu muốn khôi phục deep link, dùng saved-request-aware handler hoặc chọn precedence rõ. Nếu sản phẩm chủ động muốn luôn đưa về dashboard, đó là lựa chọn UX hợp lệ và cần được mô tả đúng.

### Tình huống E — Thay đổi OAuth redirect_uri để giữ next

**Biểu hiện:** OP báo `invalid_redirect_uri` hoặc callback không được filter xử lý.

**Nguyên nhân:** Ứng dụng đưa `next`/path nghiệp vụ vào `redirect_uri`, trong khi OP chỉ đăng ký callback cố định.

**Thiết kế phù hợp:** Giữ callback ổn định `/login/oauth2/code/company`; lưu ý định trở về trong session/request cache hoặc flow state đáng tin và xử lý sau login.

### Tình huống F — Nhiều tab đăng nhập đồng thời

**Biểu hiện:** Một tab chọn `go=orders`, tab khác chọn `go=profile`; tab đầu đăng nhập nhưng lại về profile.

**Nguyên nhân:** Ý định redirect được lưu trong một session attribute duy nhất và bị flow thứ hai ghi đè.

**Thiết kế phù hợp:** Gắn ý định redirect với **từng authorization transaction** theo state/request key hoặc quy tắc riêng cho đa tab; không dùng một ô session chung nếu sản phẩm cần hỗ trợ nhiều flow song song.

### Tình huống G — API chỉ có bearer token nhưng bị redirect tới login HTML

**Biểu hiện:** Client gọi `/api/orders` nhận `302 /login` thay vì trạng thái 401.

**Nguyên nhân:** Filter chain của web login đang xử lý API stateless hoặc entry point chưa tách theo request type.

**Thiết kế phù hợp:** Phân tách filter chain cho API Resource Server và web RP. API trả 401/403 thích hợp, không mặc định dùng HTTP redirect của browser login cho tất cả client.

## 14. Bảo mật và vận hành sau khi sửa redirect policy

### 14.1. Không đưa token hoặc authorization code vào success URL

Một ứng dụng OIDC Login dạng server-side nên hoàn tất token exchange tại backend, xác minh ID token rồi tạo session cho browser. Success URL có thể là `/dashboard` hoặc deep link nội bộ, nhưng **không nên thêm**:

```text
/dashboard?access_token=<token>
/dashboard?id_token=<token>
/dashboard?code=<authorization-code>
```

Token/code trong query string có thể bị ghi ở access logs, browser history, analytics, proxy hoặc lộ qua cơ chế URL/referrer trong những điều kiện nhất định. Đối với browser session, giữ token trong backend và dùng cookie phiên có cấu hình bảo mật phù hợp khi kiến trúc cho phép.

### 14.2. Không coi thành công xác thực là đủ quyền truy cập

OIDC Login khẳng định danh tính, không tự cấp quyền vào mọi tài nguyên. Một URL được phép redirect đến vẫn có thể bị từ chối bởi authorization của ứng dụng.

Ví dụ Spring Security:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/", "/login", "/error").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated());
```

Nếu success handler chuyển một user không có role ADMIN đến `/admin`, Spring Security vẫn từ chối theo rule. Không bỏ qua authorization để “redirect thành công” sau OIDC.

### 14.3. Cookie/session và SavedRequest

Khi browser đi qua OP rồi quay về callback, ứng dụng cần tìm lại authorization request và session dữ liệu phù hợp. Cần xem:

- HTTPS, cookie `Secure` và `HttpOnly`.
- `SameSite` theo phương thức callback (GET hoặc POST) và chính sách browser.
- Session fixation protection, timeout và invalidation.
- Session store dùng chung khi có nhiều instance.
- Proxy scheme/host/path và cookie path đúng.
- Tình huống session hết hạn giữa login flow.

Không sửa bằng cách bỏ kiểm tra `state` hoặc tắt CSRF toàn ứng dụng. Những cơ chế bảo vệ khác nhau và cần được cấu hình theo mô hình browser/session thực tế.

### 14.4. Logging, telemetry và điều tra lỗi

Nên ghi các sự kiện hữu ích nhưng không có dữ liệu bí mật:

- Registration ID mà ứng dụng đang dùng.
- Outcome `success`/`failure` và mã lỗi đã được chuẩn hóa.
- Request correlation ID riêng cho flow, không dùng token làm correlation key.
- Mã đích được allowlist, chẳng hạn `orders` hoặc `dashboard`.
- URI path nội bộ sau khi đã được kiểm soát, nếu chính sách log cho phép.

Không log toàn bộ query string của OAuth callback, `Authorization` header, access token, refresh token, ID token hoặc client secret. Không tự động đưa giá trị `next` chưa được xác minh vào analytics/dashboard mà sau đó người vận hành có thể nhấn.

## 15. Một cấu hình Spring Boot định hướng an toàn

Ví dụ ứng dụng Spring MVC dùng một OP và muốn:

- Trang `/login` hiển thị nút SSO.
- Spring giữ callback mặc định.
- Trang đích fallback `/dashboard`.
- Khi người dùng đến từ deep link, sử dụng SavedRequest.
- Không cho browser tự chọn URL redirect ngoài.

### 15.1. Cấu hình đăng ký OIDC Client

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
```

Client secret chỉ tồn tại tại backend. OP phải đăng ký chính xác redirect URI tương ứng public origin của ứng dụng.

### 15.2. Cấu hình SecurityFilterChain

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/", "/login", "/error",
                    "/css/**", "/js/**"
                ).permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .loginPage("/login")
                .defaultSuccessUrl("/dashboard"));

        return http.build();
    }
}
```

Không có tham số target URL tùy ý. Success handler có thể dùng request trước đó nếu request được lưu, nếu không thì fallback `/dashboard`.

### 15.3. Trang login

Controller:

```java
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class LoginController {

    @GetMapping("/login")
    public String login() {
        return "login";
    }
}
```

Thymeleaf template:

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Đăng nhập</title>
</head>
<body>
<main>
    <h1>Đăng nhập bằng tài khoản công ty</h1>
    <a th:href="@{/oauth2/authorization/company}">
        Tiếp tục với SSO
    </a>
</main>
</body>
</html>
```

Liên kết chỉ đến initiation endpoint của Spring. Spring tạo và quản lý `state`, callback và token exchange; template không tạo hay tiếp nhận tham số `next` tự do.

### 15.4. Một kịch bản yêu cầu điển hình

```text
GET /reports/2026
-> chưa đăng nhập, Spring lưu request và chuyển /login
-> click /oauth2/authorization/company
-> OP /authorize rồi quay lại /login/oauth2/code/company
-> Spring xác thực, success handler xem SavedRequest
-> 302 Location: /reports/2026
-> GET /reports/2026 với session đã xác thực
-> ứng dụng tiếp tục kiểm tra quyền xem báo cáo
```

Nếu người dùng bắt đầu trực tiếp từ trang login và không có saved request, fallback `/dashboard` được sử dụng.

## 16. Bảng quyết định cho từng nhu cầu điều hướng

| Nhu cầu | Cách làm gợi ý | Rủi ro cần kiểm soát |
|---|---|---|
| Mọi người về một dashboard | `defaultSuccessUrl("/dashboard", true)` | Mất deep link trước login nếu sản phẩm cần |
| Quay lại trang bị chặn trước login | RequestCache + saved-request-aware success handler | Session, Host/proxy trust boundary, quyền truy cập sau login |
| Chọn giữa vài trang cố định | Mã `go` và map đích tại server | Session overwrite giữa nhiều flow; route authorization |
| Deep link có tham số ID | SavedRequest hoặc route builder từ ID được kiểm tra | Không dùng URL tùy ý; kiểm tra quyền với ID |
| Đưa user sang ứng dụng khác | Mã ứng dụng + allowlist absolute URI cố định; SSO ở đích | Chuyển miền ngoài, token leakage, redirect chaining |
| Đổi OAuth callback | `redirect-uri`, callback matcher và OP registration | Không biến callback thành post-login target |
| Nhiều OP/tenant | Mapping registration và đích từ cấu hình tin cậy | Issuer mix-up, chọn provider không được phép |
| Tách web và API | SecurityFilterChain phù hợp từng request | API không nên bị chuyển đến HTML login |
| Đăng nhập đồng thời nhiều tab | Ý định redirect gắn riêng với authorization transaction | Ghi đè dữ liệu trong session |
| Redirect sau onboarding/authorization | Success handler dựa trên trạng thái user đã xác minh | Không dùng redirect để thay thế endpoint authorization |

## 17. Nguyên tắc thực hành

Khi thiết kế redirect sau OAuth2/OIDC Login, nên tự trả lời các câu hỏi sau theo thứ tự:

1. **Đích này thuộc giai đoạn nào?** Authorization endpoint của OP, callback `redirect_uri`, hay success URL của RP?
2. **Ai kiểm soát đích?** Cấu hình server, SavedRequest, mã allowlist, hay query parameter do browser cung cấp?
3. **Có thể dùng một route nội bộ cố định không?** Nếu được, tránh xây URL từ user input.
4. **Có cần quay về deep link không?** Nếu có, ưu tiên RequestCache/SavedRequest để giữ mục đích ban đầu theo mô hình session.
5. **Nếu user chọn đích, có thể truyền mã lựa chọn không?** Dùng `go=orders` thay vì `next=https://...`.
6. **Nếu URL thực sự động, đã kiểm soát URI sau canonicalization chưa?** Kiểm tra scheme, authority, host, port, path, redirect chaining và mọi biến thể encoding liên quan.
7. **Callback OAuth có ổn định và được OP đăng ký chính xác không?** Không thay `redirect_uri` dựa trên đích sau login.
8. **Có giữ đúng `state`, PKCE, nonce và session không?** Các cơ chế này bảo vệ authentication flow, độc lập với URL allowlist.
9. **Có kiểm tra quyền tại trang đích không?** Authentication thành công không tự tạo quyền truy cập tài nguyên.
10. **Có khai báo rõ hành vi khi thiếu đích hoặc login thất bại không?** Fallback cố định, không redirect theo URL không đáng tin.

**Điểm cần ghi nhớ:** Trong Spring Security Servlet OAuth2/OIDC Client, **callback OAuth là một phần của giao thức**, còn **URL sau đăng nhập là quyết định điều hướng của ứng dụng**. Giữ callback cố định, tận dụng SavedRequest cho deep link, dùng đường dẫn hoặc mã đích được server kiểm soát, và không để tham số URL tùy ý quyết định HTTP redirect. Các bước đó giúp đáp ứng trải nghiệm người dùng mà không tạo open redirect.

## 18. Tài liệu tham khảo

- [Spring Security — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): cơ chế OAuth2/OIDC Login trên Servlet stack.
- [Spring Security — Advanced OAuth 2.0 Login Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): authorization endpoint, callback và cấu hình login.
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): `Authentication`, success handler, entry point.
- [Spring Security — RequestCache](https://docs.spring.io/spring-security/reference/servlet/architecture.html): vị trí các filter trong Servlet Security, gồm request caching và exception handling.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): authorization request, `redirect_uri` và các yêu cầu đối chiếu.
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636): PKCE trong Authorization Code Flow.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): khuyến nghị bảo vệ redirect URI, authorization code và các thành phần OAuth.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): OIDC Authorization Code Flow, `state`, `nonce` và ID Token.
- [OWASP — Unvalidated Redirects and Forwards Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html): rủi ro open redirect, allowlist và các ví dụ phòng tránh.
