# Lấy token mới sau đăng nhập và đăng xuất

## Mục tiêu và bối cảnh

Trong chương **CSRF cho SPA và API** thuộc module **SPRING_SECURITY_HTTP_PROTECTION**, một ứng dụng một trang (SPA) dùng cookie đăng nhập phải xử lý **vòng đời CSRF token**, không chỉ lấy token khi giao diện mở lần đầu. Một POST có thể thành công trước đăng nhập nhưng nhận **403 Forbidden** ngay sau khi đăng nhập. Sau logout, token trong bộ nhớ JavaScript hoặc cookie **XSRF-TOKEN** cũng có thể không còn phù hợp với ngữ cảnh xác thực hiện tại.

Với Spring Security Servlet, **CsrfAuthenticationStrategy** và **CsrfLogoutHandler** giúp xóa CSRF token trước đó khi đăng nhập thành công hoặc đăng xuất. Đồng thời, cơ chế **deferred CSRF token** có thể trì hoãn việc tạo token mới cho tới request thực sự dùng token. SPA cần chủ động **lấy lại CSRF token sau ranh giới xác thực**, rồi mới gửi các thao tác thay đổi trạng thái.

Bài học tập trung vào sự chuyển đổi **anonymous → authenticated → anonymous** của SPA, ví dụ trên **Servlet (Spring MVC)** và **Reactive (WebFlux)**, cũng như tương tác với cookie, SameSite, CORS, security headers, CSP, HSTS, HTTP firewall và bảo vệ session.

Sau bài học, bạn có thể:

- Trình bày vai trò token **trước login**, **sau login**, **trước logout**, **sau logout**.
- Giải thích vì sao token cũ có thể bị xóa và token mới chưa được cấp ngay trong response login/logout.
- Xây dựng **GET /api/csrf** để lấy token gắn với cookie/session hiện tại, kể cả khi chưa đăng nhập.
- Thiết kế SPA tránh dùng token cũ, tránh race condition khi request bootstrap đến trễ và xử lý nhiều tab.
- Phân biệt vòng đời CSRF token của **HttpSessionCsrfTokenRepository** với **CookieCsrfTokenRepository**.
- Kiểm thử trước/sau đăng nhập và đăng xuất trên Servlet, WebFlux, trình duyệt và API gateway.

## 1. Tại sao token cũ có thể mất hiệu lực sau login/logout?

**Cross-Site Request Forgery (CSRF)** lợi dụng việc trình duyệt tự đính kèm thông tin xác thực (chẳng hạn **JSESSIONID** hoặc cookie JWT) vào những request không thực sự do người dùng chủ ý. Với thao tác không an toàn như POST/PUT/PATCH/DELETE, backend thường yêu cầu CSRF token được gửi chủ động trong một header hoặc form parameter.

Ví dụ SPA lấy token A lúc chưa đăng nhập:

~~~http
GET /api/csrf HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=anonymous-session
~~~

Phản hồi minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{"headerName":"X-CSRF-TOKEN","token":"token-A"}
~~~

Khi người dùng xác thực thành công, Spring Security có thể **xóa token A** ra khỏi repository. Nó cũng có thể đổi session ID để bảo vệ chống **session fixation**. Nếu frontend vẫn giữ A và đưa vào POST tiếp theo, server có thể từ chối:

~~~http
PATCH /api/profile HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=authenticated-session
X-CSRF-TOKEN: token-A
Content-Type: application/json

{"displayName":"Alice"}
~~~

Do đó, quy tắc xử lý cơ bản là:

> Sau khi backend **xác nhận** login hoặc logout thành công, frontend phải **bỏ trạng thái CSRF token cũ** và lấy token phù hợp với cookie/session mới trước thao tác ghi tiếp theo.

**Không bắt buộc mọi token có chuỗi khác nhau.** Chính sách xóa, tạo và xoay token phụ thuộc repository, strategy và custom authentication flow. Các nhãn A/B/C dưới đây dùng để phân biệt ngữ cảnh, không phải lời hứa mọi implementation luôn cấp giá trị khác nhau.

### 1.1. CSRF token không phải credential xác thực

| Thành phần | Mục đích | Ảnh hưởng của login/logout |
| --- | --- | --- |
| **JSESSIONID** | Định danh phiên, browser tự gửi cookie | Session có thể được đổi ID hoặc bị vô hiệu hóa |
| **Cookie JWT/AUTH_TOKEN** | Credential mà browser có thể tự gửi | Có thể được phát, thay hoặc xóa khi authentication đổi |
| **CSRF token lưu trong HttpSession** | Chứng minh request không an toàn thuộc luồng hợp lệ | Có thể bị xóa bởi authentication/logout strategy |
| **Cookie XSRF-TOKEN** | Cung cấp token cho JavaScript đọc và gắn header | Có thể bị xóa/hết hạn và được phát lại |
| **Authorization: Bearer** do JS tự gửi | Credential do frontend chủ động thêm | Không giống cookie auto-send; API Bearer-only có mô hình CSRF khác |
| **Bản sao CSRF token trong bộ nhớ SPA** | Giá trị frontend sử dụng cho request ghi | Không tự biết khi repository đã xóa token |

Token CSRF hợp lệ **không cấp quyền đăng nhập**. Sau logout, ứng dụng vẫn có thể nhận CSRF token cho một form anonymous; token ấy không cho phép truy cập API yêu cầu authentication.

## 2. Dòng thời gian chuẩn: trước login, sau login, trước logout, sau logout

~~~mermaid
sequenceDiagram
    autonumber
    participant SPA as Trình duyệt / SPA
    participant SEC as Spring Security
    participant API as API Controller
    SPA->>SEC: GET /api/csrf (anonymous cookie)
    SEC-->>SPA: Token A
    SPA->>SEC: POST /login + cookie + token A
    SEC->>SEC: Authentication thành công, có thể đổi session ID và xóa A
    SEC-->>SPA: Login success/redirect và cookie hiện hành
    SPA->>SEC: GET /api/csrf bằng cookie hiện hành
    SEC-->>SPA: Token B
    SPA->>SEC: POST /api/orders + cookie + token B
    SEC->>API: Kiểm tra CSRF, authentication và quyền
    API-->>SPA: Kết quả nghiệp vụ
    SPA->>SEC: POST /logout + cookie + token hiện hành
    SEC->>SEC: Logout và xóa token theo cấu hình
    SEC-->>SPA: Logout success/redirect
    SPA->>SEC: GET /api/csrf ở trạng thái anonymous mới
    SEC-->>SPA: Token C
~~~

Có hai thứ tự không được đảo ngược:

- **POST login dùng token trước login**, bởi POST login cũng có thể được CsrfFilter bảo vệ. **Chỉ sau login thành công** mới lấy token cho trạng thái authenticated.
- **POST logout dùng token còn hiệu lực của phiên đã đăng nhập**. **Chỉ sau logout thành công** mới xóa cache token và lấy token cho trạng thái anonymous.

Sai lầm phổ biến là xóa token client **trước khi gửi logout**, làm chính POST logout thiếu CSRF header rồi bị từ chối. Khi đó UI có thể hiển thị “đã đăng xuất” nhưng phiên backend vẫn còn đăng nhập.

### 2.1. Bảng quyết định theo thời điểm

| Sự kiện | Hành động của SPA | Điều cần xác minh |
| --- | --- | --- |
| Vừa mở SPA | GET /api/csrf lấy token A | Token được tạo trong đúng cookie/session |
| Người dùng bấm Login | Gửi POST login với A | Login endpoint có CSRF protection và cookie phù hợp |
| Login được xác nhận thành công | Invalidate A, GET /api/csrf lấy B | Session/cookie mới đã được browser áp dụng |
| POST/PATCH/DELETE của người dùng đã đăng nhập | Gửi token B | CSRF đúng, quyền đủ, input hợp lệ |
| Người dùng bấm Logout | Gửi POST logout với B | Logout thật sự được server xử lý |
| Logout được xác nhận thành công | Invalidate B, GET /api/csrf lấy C nếu còn cần | Ứng dụng đang anonymous, không phải session cũ |
| Login/logout thất bại | Không chuyển UI thành công giả | Kiểm tra trạng thái server/cookie, báo lỗi rõ |
| Session timeout | Không tự động lặp lại POST nguy hiểm | Xác định nguyên nhân 401/403, yêu cầu login hoặc bootstrap lại |

## 3. Spring Security Servlet: CsrfAuthenticationStrategy và CsrfLogoutHandler

### 3.1. Khi xác thực thành công

Với Servlet, **CsrfAuthenticationStrategy** có thể xóa CSRF token cũ khỏi **CsrfTokenRepository** trong luồng authentication thành công. Mục tiêu là không giữ nguyên token đã dùng ở một ranh giới tin cậy thấp hơn qua sự kiện chuyển đổi danh tính.

Với **HttpSessionCsrfTokenRepository**:

1. GET ban đầu tạo token A và có thể tạo session anonymous để lưu token.
2. POST login dùng A hợp lệ nên vượt bước kiểm tra CSRF.
3. Authentication strategy xóa A; session fixation protection có thể đổi ID.
4. GET /api/csrf sau login hiện thực hóa token mới trong ngữ cảnh session hiện tại.
5. Request ghi tiếp theo sử dụng giá trị mới, không dùng A.

Với **CookieCsrfTokenRepository**, thao tác xóa có thể biểu hiện bằng **Set-Cookie** làm hết hạn cookie XSRF-TOKEN. Do **deferred token**, cookie mới không nhất thiết xuất hiện trong cùng response login. SPA nên gọi GET bootstrap, chờ browser áp dụng cookie rồi **đọc lại cookie XSRF**.

**Đừng dựa vào một Set-Cookie cụ thể luôn có mặt** sau login; thứ tự filter, repository, handler và response strategy ảnh hưởng thời điểm phát token.

### 3.2. Session fixation protection không tự thay vai trò CSRF

Spring Security có thể đổi session ID khi đăng nhập để giảm nguy cơ **session fixation**. Phân biệt:

- **Session ID đổi:** browser cần dùng cookie phiên mới; các session attributes có thể được quản lý/migrate theo chính sách.
- **CSRF token bị xóa:** strategy loại token khỏi repository; GET bootstrap mới cần tạo/nạp token.
- **Cookie bị chặn:** Secure, SameSite, Domain/Path, Fetch credentials hoặc third-party cookie policy khiến GET và POST thuộc ngữ cảnh khác.
- **Principal/authority đổi:** request vẫn có thể bị 403 do thiếu quyền, dù token CSRF hợp lệ.

Vì vậy, 403 ngay sau login không tự chứng minh lỗi CSRF; cần xem exception và các cookie/headers thực tế.

### 3.3. Khi đăng xuất

**CsrfLogoutHandler** trong Servlet có thể xóa CSRF token khi logout. Đồng thời luồng logout có thể xóa **SecurityContext** và vô hiệu hóa HttpSession theo cấu hình.

Ví dụ cho hệ thống dùng cookie XSRF raw:

~~~http
POST /logout HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=current-session; XSRF-TOKEN=raw-B
X-XSRF-TOKEN: raw-B
~~~

Request này phải được kiểm tra với **token hiện hành trước logout**. Nếu logout thành công, không dùng lại raw-B cho một hành động khác, kể cả UI vẫn mở. Với HttpSessionCsrfTokenRepository mặc định, header có thể là **X-CSRF-TOKEN** và token có thể là XOR-masked; phải theo đúng request handler hiện có.

**Không thiết kế logout có side effect qua GET** chỉ để tránh yêu cầu CSRF. Logout CSRF có thể gây gián đoạn phiên hoặc rủi ro khác tùy nghiệp vụ.

### 3.4. Authentication/logout tự viết phải được kiểm tra riêng

Một hệ thống có thể dùng JSON login controller tùy chỉnh, OAuth/OIDC redirect, API gateway, Backend for Frontend (BFF), custom authentication filter hoặc JWT cookie. Những luồng này **không chắc** chạy qua cùng strategy/handler của formLogin chuẩn.

Cần xác minh cụ thể:

- Login có đi qua Spring Security authentication mechanism phù hợp hay chỉ tự phát JWT?
- Khi login, CsrfTokenRepository có được yêu cầu xóa token cũ không?
- Logout có thực sự gọi logout mechanism và hủy credential/session theo thiết kế?
- Có chain/API gateway nào đọc cookie rồi thay bằng header danh tính nội bộ không?
- SPA lấy token mới tại ranh giới browser-facing, không phải từ một hệ thống khác?

Hợp đồng quan trọng là **sau sự kiện xác thực đã hoàn tất**, frontend có cách lấy token hợp lệ cho trạng thái mới và request ghi kế tiếp vẫn qua CsrfFilter.

## 4. Deferred CSRF token: vì sao đăng nhập xong vẫn chưa có XSRF cookie?

Spring Security hiện đại hỗ trợ **deferred CSRF token**: repository có thể hoãn việc tải hoặc tạo token đến khi giá trị thực sự được truy cập.

Một GET bình thường tới **/dashboard** có thể không khiến token mới được hiện thực hóa, dù authentication thành công trước đó. Với cookie repository, browser có thể thấy cookie đăng nhập mới nhưng **chưa thấy XSRF-TOKEN cookie**.

Để cấp token đúng lúc:

1. SPA GET **/api/csrf** sau khi login/logout được xác nhận thành công.
2. Endpoint thực sự truy cập **CsrfToken.getToken()** trong Servlet hoặc subscribe **Mono<CsrfToken>** trong WebFlux.
3. Backend trả JSON token hoặc làm cookie repository phát XSRF cookie; response đặt **Cache-Control: no-store**.
4. Frontend đợi hoàn thành, rồi mới cho phép thao tác POST/PATCH/DELETE mới.

**Chỉ một response GET 200/204 không đảm bảo token đã được tạo** nếu không có code chạm tới token và repository có thể thực hiện deferred loading.

## 5. Servlet: GET /api/csrf trước và sau đăng nhập

Ví dụ sau dùng **Spring Boot 3, Spring Security 6**, form login và repository CSRF Servlet mặc định, thường lưu token trong HttpSession.

### 5.1. SecurityFilterChain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class WebSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .csrf(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                // Token cần được lấy cả khi chưa đăng nhập và sau logout.
                .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().permitAll()
            )
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults())
            .build();
    }
}
~~~

**permitAll** ở GET không tắt CSRF cho POST. Với formLogin mặc định, Spring Security thường nhận **POST /login** theo dạng form và redirect khi thành công/thất bại; cấu hình này **không tự tạo một JSON login API**. Nếu dùng nhiều SecurityFilterChain, xác minh GET token và POST cần token được xử lý bởi repository/request handler tương thích.

### 5.2. Endpoint trả JSON token

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CsrfBootstrapController {

    record CsrfPayload(String headerName, String token) {}

    @GetMapping("/api/csrf")
    ResponseEntity<CsrfPayload> csrf(HttpServletRequest request) {
        CsrfToken csrf = (CsrfToken) request.getAttribute(
            CsrfToken.class.getName());

        if (csrf == null) {
            throw new IllegalStateException("CSRF filter not configured");
        }

        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(new CsrfPayload(csrf.getHeaderName(), csrf.getToken()));
    }
}
~~~

**csrf.getToken()** kích hoạt deferred token. Khi repository lưu token vào HttpSession, request GET này có thể tạo session anonymous; đó là state phục vụ security, không phải dữ liệu nghiệp vụ bị thay đổi.

Frontend phải gửi **đúng token và headerName từ response mới nhất**. Trong Spring Security 6, token từ request attribute có thể là **XOR-masked token** để giảm nguy cơ BREACH trong response có nén; frontend không cần giải mã và không được tự thay nó bằng giá trị raw ở một nguồn khác.

### 5.3. CookieCsrfTokenRepository cho SPA đọc raw cookie

Nếu SPA cùng origin muốn đọc cookie **XSRF-TOKEN** rồi gửi **X-XSRF-TOKEN**, có thể thay riêng phần CSRF bằng biến thể:

~~~java
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;
import org.springframework.security.web.csrf.CsrfTokenRequestAttributeHandler;

// Biến thể riêng cho SPA chỉ dùng raw XSRF cookie/header:
.csrf(csrf -> csrf
    .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
    .csrfTokenRequestHandler(new CsrfTokenRequestAttributeHandler())
)
~~~

Đây là **mẫu raw token** phù hợp API JSON. Nếu ứng dụng đồng thời render form HTML có XOR-masked token, cần **SPA CSRF request handler kết hợp**: XOR cho token HTML/request attribute và plain cho header raw, thay vì áp dụng handler plain cho mọi trường hợp mà không đánh giá BREACH.

Cookie phiên **JSESSIONID** hoặc cookie JWT xác thực phải được quản lý **HttpOnly, Secure, SameSite** riêng. Chỉ XSRF cookie cần **HttpOnly=false** khi JavaScript thực sự phải đọc cookie. Nếu dùng endpoint JSON cho token, không bắt buộc mở quyền đọc XSRF cookie.

Sau login/logout, repository cookie có thể xóa XSRF cookie cũ. Gọi **GET /api/csrf**, sau đó đọc lại cookie thay vì dùng token đã cache trong state SPA.

### 5.4. Không đổi repository giữa GET và POST

| Triệu chứng | Nguyên nhân có thể |
| --- | --- |
| Token A dùng được trước login nhưng POST sau login 403 | Strategy xóa token A, frontend chưa lấy token mới |
| GET /api/csrf thành công, POST vẫn 403 | Cookie/session không khớp hoặc GET/POST qua hai chain có repository khác |
| Sau login không thấy XSRF-TOKEN cookie | Deferred token chưa được hiện thực hóa, cookie bị chặn, hoặc hệ thống dùng HttpSession repo |
| Token JSON thay đổi mỗi GET | Có thể chỉ là mask XOR thay đổi, không phải raw token đổi |
| XSRF cookie và header raw giống nhau nhưng POST 403 | Request handler đang đòi token masked |
| POST logout 403 | Thiếu/sai token hiện hành, sai chain hoặc browser không gửi cookie |

## 6. JavaScript: quản lý token theo thế hệ xác thực

Một SPA có thể mở nhiều component, nhiều request đồng thời. Để tránh một GET cũ ghi đè token mới sau login, nên quản lý CSRF token theo **epoch** (thế hệ xác thực).

### 6.1. Service bootstrap có kiểm tra epoch

~~~javascript
const csrfState = {
  epoch: 0,
  current: null, // { headerName, token }
  loading: null
};

function invalidateForAuthChange() {
  csrfState.epoch += 1;
  csrfState.current = null;
  csrfState.loading = null;
}

async function ensureCsrf() {
  if (csrfState.current) return csrfState.current;
  if (csrfState.loading) return csrfState.loading;

  const expectedEpoch = csrfState.epoch;
  const operation = (async () => {
    const response = await fetch("/api/csrf", {
      method: "GET",
      credentials: "same-origin",
      cache: "no-store"
    });

    if (!response.ok) {
      throw new Error("CSRF bootstrap failed: " + response.status);
    }

    const body = await response.json();
    if (typeof body.headerName !== "string" ||
        typeof body.token !== "string" ||
        !body.token) {
      throw new Error("Invalid CSRF response");
    }

    // Request khởi tạo trước login/logout không được ghi đè state mới.
    if (csrfState.epoch !== expectedEpoch) {
      throw new Error("Obsolete CSRF response");
    }

    csrfState.current = {
      headerName: body.headerName,
      token: body.token
    };
    return csrfState.current;
  })();

  csrfState.loading = operation;
  try {
    return await operation;
  } finally {
    if (csrfState.loading === operation) csrfState.loading = null;
  }
}

async function refreshAfterAuthChange() {
  invalidateForAuthChange();
  return ensureCsrf();
}
~~~

**Tình huống race:** GET token A bắt đầu khi anonymous, login thành công, GET token B bắt đầu, response A đến **sau** B. Nếu state nhận A cuối cùng, POST kế tiếp có thể 403. Epoch làm request cũ bị từ chối thay vì ghi đè token B.

### 6.2. Request ghi cần token đúng epoch

~~~javascript
async function savePreferences(preferences) {
  const startEpoch = csrfState.epoch;
  const csrf = await ensureCsrf();

  if (csrfState.epoch !== startEpoch) {
    throw new Error("Auth state changed while preparing request");
  }

  const response = await fetch("/api/preferences", {
    method: "PATCH",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      [csrf.headerName]: csrf.token
    },
    body: JSON.stringify(preferences)
  });

  if (response.status === 401) {
    throw new Error("Session missing or expired");
  }
  if (response.status === 403) {
    csrfState.current = null;
    throw new Error("Request denied: inspect CSRF and authorization");
  }
  if (!response.ok) {
    throw new Error("Update failed: " + response.status);
  }

  return response.status === 204 ? null : response.json();
}
~~~

Epoch giúp giảm rủi ro race phía client, **không thay backend kiểm tra session/CSRF/authorization**. Login hoặc logout vẫn có thể xảy ra ngay sau bước kiểm tra epoch; backend là lớp bảo vệ cuối cùng. Khi auth transition đang diễn ra, nên khóa các thao tác ghi mới ở API service/UI.

**Không retry POST/PATCH tự động khi 403**. Một response 403 có thể do thiếu quyền, và retry một thao tác có side effect cần chính sách an toàn riêng.

### 6.3. Sau login thành công

~~~javascript
// authenticateUser và các hàm UI dưới đây do ứng dụng triển khai.
async function onLogin(credentials) {
  setWriteActionsDisabled(true);
  try {
    await authenticateUser(credentials);
    // Chỉ gọi nếu backend đã xác nhận login thành công.
    await refreshAfterAuthChange();
    setAuthenticatedUi();
  } finally {
    setWriteActionsDisabled(false);
  }
}
~~~

**authenticateUser** phải gửi token trước login nếu POST login được CsrfFilter bảo vệ. Hàm này cần xác minh login **thực sự thành công**, không chỉ dựa vào status 200 của response cuối cùng sau redirect.

Với Spring Security **formLogin mặc định**, browser thường điều hướng qua redirect và SPA sẽ bootstrap lại từ đầu ở trang mới. Nếu xây dựng login API trả JSON/204, phải tùy biến authentication success/failure flow một cách rõ ràng; ví dụ client trên giả định hợp đồng ấy đã tồn tại.

### 6.4. Logout: chỉ xóa token cũ sau thành công

~~~javascript
// signOutUsingToken là adapter theo endpoint logout thực tế của dự án.
async function onLogout() {
  setWriteActionsDisabled(true);
  try {
    const csrf = await ensureCsrf();
    await signOutUsingToken({
      headerName: csrf.headerName,
      token: csrf.token
    });

    // Chỉ khi server xác nhận logout thành công.
    await refreshAfterAuthChange();
    setAnonymousUi();
  } finally {
    setWriteActionsDisabled(false);
  }
}
~~~

**signOutUsingToken** phải gửi **POST logout** cùng cookie hiện hành và CSRF token hiện hành; ứng dụng cần giải quyết chính sách redirect hay success handler của backend. Nếu logout thất bại, **không tuyên bố người dùng đã đăng xuất** chỉ bằng việc xóa token hoặc UI state.

## 7. Biến thể SPA dùng raw XSRF cookie sau auth transition

Với CookieCsrfTokenRepository, frontend có thể đọc **XSRF-TOKEN** từ document.cookie. Sau login/logout, quy trình làm mới là **GET token để backend cấp lại cookie, rồi đọc lại cookie mới**:

~~~javascript
function readCookie(name) {
  const prefix = encodeURIComponent(name) + "=";
  const item = document.cookie
    .split("; ")
    .find(part => part.startsWith(prefix));
  return item ? decodeURIComponent(item.slice(prefix.length)) : null;
}

async function refreshRawXsrfCookie() {
  const response = await fetch("/api/csrf", {
    method: "GET",
    credentials: "same-origin",
    cache: "no-store"
  });
  if (!response.ok) {
    throw new Error("Cannot refresh XSRF token");
  }

  const token = readCookie("XSRF-TOKEN");
  if (!token) {
    throw new Error("XSRF cookie missing after bootstrap");
  }
  return token;
}

async function postOrder(order) {
  const rawToken = readCookie("XSRF-TOKEN") ||
      await refreshRawXsrfCookie();

  return fetch("/api/orders", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-XSRF-TOKEN": rawToken
    },
    body: JSON.stringify(order)
  });
}
~~~

Sau khi login/logout thành công, frontend **phải chủ động gọi refreshRawXsrfCookie()** thay vì chỉ dùng cookie giá trị cũ hoặc token trong biến memory. XSRF cookie có thể bị hết hạn/xóa và được tạo lại tùy repo. Trên môi trường HTTPS production nên cấu hình **Secure, SameSite, Domain/Path** phù hợp; không bỏ HttpOnly trên **cookie xác thực**.

Nếu frontend lấy **token JSON từ XOR request attribute** thay vì raw cookie, header cần được xử lý theo **hợp đồng masked token**. Không trộn giá trị raw cookie với handler mong masked token, hoặc đưa masked JSON vào handler coi header là raw.

## 8. Reactive/WebFlux: cùng bài toán vòng đời, API khác

Spring Security WebFlux dùng **CsrfWebFilter**, **ServerHttpSecurity**, **ServerCsrfTokenRepository** và **ServerWebExchange**. Token có thể được gắn vào exchange dưới dạng **Mono<CsrfToken>** và chỉ được tạo khi pipeline subscribe.

### 8.1. SecurityWebFilterChain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Bean
SecurityWebFilterChain reactiveSecurity(ServerHttpSecurity http) {
    return http
        .csrf(Customizer.withDefaults())
        .authorizeExchange(auth -> auth
            .pathMatchers(HttpMethod.GET, "/api/csrf").permitAll()
            .pathMatchers("/api/**").authenticated()
            .anyExchange().permitAll()
        )
        .formLogin(Customizer.withDefaults())
        .logout(Customizer.withDefaults())
        .build();
}
~~~

**CsrfAuthenticationStrategy** và **CsrfLogoutHandler** là tên class liên quan Servlet; **không sử dụng trực tiếp các class Servlet ấy trong WebFlux**. Khi ứng dụng tự viết authentication/logout Reactive, cần kiểm thử thực tế xem token có bị xóa, tái cấp và lưu đúng repository không, thay vì mặc định suy luận từ Servlet.

### 8.2. Endpoint GET /api/csrf Reactive

~~~java
import java.util.Map;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
class ReactiveCsrfBootstrapController {

    @GetMapping("/api/csrf")
    Mono<ResponseEntity<Map<String, String>>> csrf(ServerWebExchange exchange) {
        Mono<CsrfToken> tokenMono =
            exchange.getAttribute(CsrfToken.class.getName());

        if (tokenMono == null) {
            return Mono.error(
                new IllegalStateException("CSRF not configured"));
        }

        return tokenMono.map(token -> ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(Map.of(
                "headerName", token.getHeaderName(),
                "token", token.getToken()
            )));
    }
}
~~~

**Không gọi block()** trong controller WebFlux. Sau login/logout Reactive, SPA gọi GET này với cookie/WebSession đang hoạt động để lấy token phù hợp.

### 8.3. CookieServerCsrfTokenRepository

~~~java
import org.springframework.security.web.server.csrf.CookieServerCsrfTokenRepository;
import org.springframework.security.web.server.csrf.ServerCsrfTokenRequestAttributeHandler;

// Biến thể riêng cho SPA Reactive gửi raw XSRF cookie trong header:
.csrf(csrf -> csrf
    .csrfTokenRepository(
        CookieServerCsrfTokenRepository.withHttpOnlyFalse())
    .csrfTokenRequestHandler(
        new ServerCsrfTokenRequestAttributeHandler())
)
~~~

Biến thể này dành cho raw token; ứng dụng có HTML với XOR-masked token cần request handler Reactive phù hợp. Không copy nguyên **HttpServletRequest** hay Servlet handler sang **ServerWebExchange**.

Sau authentication/logout trong WebFlux, kiểm tra **WebSession**, CSRF cookie, token repository và request handler để biết token nào hợp lệ; không chỉ kiểm tra một HTTP status.

## 9. Khác origin: GET token mới phải sử dụng cookie phiên mới

Giả sử SPA chạy tại **https://app.example.com** còn API tại **https://api.example.com**. Hai địa chỉ này **khác origin** dù có thể cùng site. Fetch mặc định dùng **credentials: "same-origin"**, nên khi gọi API khác origin, browser không tự gửi cookie như frontend có thể tưởng.

Với API xác thực bằng cookie, cả ba loại request đều cần hợp đồng credentials rõ ràng:

1. **Login/logout request**: cookie hiện hành phải được gửi hoặc response mới phải có thể được browser lưu tùy luồng.
2. **GET /api/csrf sau login/logout**: phải dùng cookie của **trạng thái xác thực mới nhất**.
3. **POST/PATCH/DELETE sau đó**: phải dùng cùng ngữ cảnh cookie với GET token và thêm header CSRF.

Ví dụ SPA lấy token sau login:

~~~javascript
const API = "https://api.example.com";

async function csrfFromCurrentApiSession() {
  const response = await fetch(API + "/api/csrf", {
    method: "GET",
    credentials: "include",
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error("Cannot get CSRF token: " + response.status);
  }
  return response.json();
}

async function createOrder(order) {
  const csrf = await csrfFromCurrentApiSession();

  return fetch(API + "/api/orders", {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      [csrf.headerName]: csrf.token
    },
    body: JSON.stringify(order)
  });
}
~~~

Ở đây mỗi POST đều lấy token để làm rõ tính đúng đắn; ứng dụng thực tế có thể cache token trong một epoch và dùng lại cho đến khi authentication state thay đổi. Dù cache hay không, **GET token và POST phải có cùng cookie/session hợp lệ**.

### 9.1. CORS Servlet mẫu

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration cors = new CorsConfiguration();
    cors.setAllowedOrigins(List.of("https://app.example.com"));
    cors.setAllowedMethods(List.of("GET", "POST", "PUT", "PATCH", "DELETE"));
    cors.setAllowedHeaders(List.of(
        "Content-Type", "X-CSRF-TOKEN", "X-XSRF-TOKEN"));
    cors.setAllowCredentials(true);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", cors);
    return source;
}
~~~

Với Servlet, gắn CORS vào HttpSecurity bằng **.cors(Customizer.withDefaults())**, cấu hình đường login/logout và preflight tương ứng với request thực tế. Với WebFlux, sử dụng các thành phần **Reactive CORS** thay vì class Servlet.

**CORS không tự làm cookie hợp lệ.** Browser còn xét **SameSite, Secure, Domain, Path, chính sách third-party cookies** và Fetch credentials. Khi SPA và API khác site, **SameSite=None; Secure** có thể cần thiết nếu kiến trúc cho phép, nhưng third-party cookie có thể vẫn bị chặn; cần xem xét BFF hoặc same-site deployment thay vì nới policy vô tội vạ.

**Không bật CORS credentials cho mọi origin.** Endpoint JSON trả CSRF token chỉ nên đọc được bởi các origin tin cậy. CORS wildcard hoặc phản chiếu Origin không kiểm soát có thể làm lộ token/ngữ cảnh xác thực.

### 9.2. Cookie host-only và XSRF token

Khi API **api.example.com** phát XSRF-TOKEN không có thuộc tính Domain, đó thường là **host-only cookie**. JavaScript tại **app.example.com** không đọc được cookie này qua document.cookie.

Do đó SPA khác origin thường nên nhận token qua **response JSON** từ GET /api/csrf với CORS allowlist. Không mở rộng **Domain=example.com** chỉ để đọc XSRF cookie: nhiều subdomain kém tin cậy có thể làm tăng rủi ro cookie injection.

Nếu response JSON cấp token được XOR-mask, frontend phải gửi đúng chuỗi JSON qua handler XOR tương ứng. Nếu backend thiết kế handler plain cho raw header, response JSON cũng phải cung cấp raw token. **Lấy token sau login/logout không chữa được sai hợp đồng raw/masked.**

## 10. Kiểm thử Servlet: token của session hiện tại

### 10.1. MockMvc kiểm tra GET token và POST cùng session

Giả sử ứng dụng có endpoint **POST /api/preferences** cho người dùng đã xác thực cập nhật dữ liệu, dùng **HttpSessionCsrfTokenRepository mặc định** và có dependency **spring-security-test**.

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.jayway.jsonpath.JsonPath;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfLoginLogoutBootstrapTests {

    @Autowired MockMvc mvc;

    @Test
    void tokenFromGetIsAcceptedWithinCurrentSession() throws Exception {
        MvcResult getResult = mvc.perform(get("/api/csrf"))
            .andExpect(status().isOk())
            .andReturn();

        String json = getResult.getResponse().getContentAsString();
        String headerName = JsonPath.read(json, "$.headerName");
        String token = JsonPath.read(json, "$.token");
        MockHttpSession session =
            (MockHttpSession) getResult.getRequest().getSession(false);

        if (session == null) {
            throw new AssertionError("Expected session-backed CSRF token");
        }

        mvc.perform(post("/api/preferences")
                .session(session)
                .with(user("alice"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"emailAlerts\":false}"))
            .andExpect(status().isForbidden());

        mvc.perform(post("/api/preferences")
                .session(session)
                .with(user("alice"))
                .header(headerName, token)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"emailAlerts\":false}"))
            .andExpect(status().is2xxSuccessful());
    }
}
~~~

Ví dụ phụ thuộc controller thật và quyền nghiệp vụ phù hợp; kỳ vọng 2xx chỉ đúng khi endpoint có tồn tại và dữ liệu hợp lệ. **user("alice")** là test helper mô phỏng principal, **không thực hiện login thực tế**, không chứng minh CsrfAuthenticationStrategy đã xóa token hoặc session fixation protection đã chạy. Cần kiểm thử integration với authentication mechanism thật cho mục tiêu chính của bài.

### 10.2. Integration test: login thật phải làm mới CSRF token

Trong môi trường được phép kiểm thử:

1. Tạo browser session anonymous và GET /api/csrf để lấy token A.
2. POST login với token A, cookie tương ứng và credentials test hợp lệ.
3. Xác minh login **thật sự thành công** bằng principal/endpoint kiểm tra session hoặc authentication success handler, không chỉ status 200 sau redirect.
4. Giữ **cookie hiện hành** được phát sau login, nhất là nếu session ID đã đổi.
5. Với cấu hình mặc định có xóa token, thử POST API bằng A: cần bị từ chối và dữ liệu **không thay đổi**.
6. GET /api/csrf trong phiên authenticated mới để lấy token B.
7. POST API với B, cookie authenticated và đủ quyền: phải vượt CSRF và được nghiệp vụ xử lý.
8. Thử token B với người dùng không có quyền ghi: CSRF đúng vẫn không đủ để vượt authorization.

**Không cần assertion cứng rằng chuỗi A khác chuỗi B trong mọi ứng dụng tùy biến.** Mục tiêu là xác minh tính hợp lệ/hết hiệu lực và hành vi bảo vệ trong chính cấu hình triển khai.

### 10.3. Integration test: logout thật, anonymous mới

1. Đăng nhập thành công rồi GET /api/csrf lấy token B.
2. POST logout có B và cookie phiên hiện hành; xác minh backend logout thật.
3. Gọi API protected sau logout: phải bị từ chối, kể cả khi một CSRF token anonymous hợp lệ được gửi.
4. GET /api/csrf tiếp sau logout để nhận token C cho trạng thái anonymous nếu cần.
5. POST một endpoint public nhưng cần CSRF bằng token C (nếu ứng dụng có route như vậy): token phải đi qua CsrfFilter; route protected vẫn cần authentication.
6. Đăng nhập lại bằng tài khoản khác rồi xác minh token/phiên được đồng bộ.
7. Kiểm tra **POST logout thiếu/sai CSRF token** có bị chặn trước khi phiên bị đăng xuất hay không.

Với formLogin/logout mặc định, response có thể **redirect (3xx)**. Nếu gọi qua Fetch, phải xử lý redirect và trạng thái xác thực thật; response cuối 200 có thể là HTML login page chứ không chứng minh login thành công.

### 10.4. Ma trận kết quả

| Kịch bản | Kỳ vọng bảo mật |
| --- | --- |
| GET /api/csrf khi anonymous và permitAll | Có thể lấy token A hợp lệ cho phiên hiện tại |
| POST login thiếu token khi được bảo vệ | Bị chặn, không đăng nhập |
| POST login với A hợp lệ và credentials đúng | Có thể xác thực; xác minh trạng thái server |
| POST API với A cũ ngay sau login | Bị từ chối nếu strategy xóa A; dữ liệu giữ nguyên |
| GET token sau login với cookie mới | Lấy được token hợp lệ cho authenticated session |
| POST với B và đủ quyền | Vượt CSRF và thao tác có thể được xử lý |
| POST logout thiếu token hiện hành | Bị chặn theo chính sách logout cookie-based |
| POST logout có token B hiện hành | Logout thành công nếu các điều kiện khác hợp lệ |
| GET token sau logout | Nhận token cho anonymous nếu cần thao tác ghi |
| POST API protected sau logout, dù CSRF token đúng | Vẫn bị chặn do chưa xác thực |
| Login thất bại | UI không chuyển sai sang authenticated |
| GET token/POST có cookie phiên khác nhau | Bị từ chối hoặc sai token; kiểm tra browser cookie |
| Token đúng nhưng thiếu role | Bị authorization từ chối, không phải lỗi CSRF |

Mã 401/403/3xx cụ thể phụ thuộc authentication entry point, request handler và success/failure handler. **Kiểm tra side effect trên dữ liệu** mới chứng minh request trái phép thực sự bị chặn.

## 11. WebTestClient và vòng đời token Reactive

Có thể dùng **spring-security-test** với WebFlux:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

// Đoạn thân test; webTestClient gắn Spring Security,
// POST /api/preferences có handler thật.
webTestClient.mutateWith(mockUser("alice"))
    .post().uri("/api/preferences")
    .bodyValue(Map.of("emailAlerts", false))
    .exchange()
    .expectStatus().isForbidden();

webTestClient.mutateWith(mockUser("alice")).mutateWith(csrf())
    .post().uri("/api/preferences")
    .bodyValue(Map.of("emailAlerts", false))
    .exchange()
    .expectStatus().is2xxSuccessful();
~~~

Đây là đoạn thân test, cần **java.util.Map**, WebTestClient và controller phù hợp. **mockUser()** và **csrf()** giúp xác minh CsrfWebFilter, **không mô phỏng toàn bộ authentication/logout Reactive**.

Với bài test đúng trọng tâm, hãy dùng client duy trì cookie/WebSession qua chuỗi: GET token A → authentication thật → GET token B → POST → logout thật → GET token C. Theo dõi token/cookie cùng session và việc Mono của endpoint bootstrap đã được subscribe. Nếu repository dùng cookie CSRF, kiểm tra raw header và handler; nếu dùng WebSession repository, giữ đúng WebSession giữa các bước.

## 12. Race condition, multi-tab và chuyển tài khoản

### 12.1. Một response GET cũ đến sau login

~~~text
T0: GET /api/csrf cho anonymous bắt đầu, chưa trả response
T1: Login thành công
T2: GET /api/csrf cho authenticated bắt đầu
T3: Response T2 chứa token B, SPA lưu B
T4: Response T0 chứa token A đến muộn
T5: SPA lỗi nếu ghi đè B bằng A
~~~

Cơ chế **epoch** ở phần 6 giúp loại response không còn thuộc trạng thái hiện tại. Có thể dùng thêm **AbortController** để hủy GET cũ tại client, nhưng vẫn phải kiểm tra epoch vì việc hủy network không tự bảo đảm backend đã ngừng xử lý mọi request.

### 12.2. Logout đồng thời với thao tác ghi

Một component có thể gửi POST cùng lúc component khác logout. Việc POST được xử lý trước hay sau logout tùy thứ tự request tới backend; JavaScript không thể bảo đảm tuyệt đối bằng một flag.

Phòng vệ thực tế:

- Tạm dừng các thao tác ghi mới khi login/logout bắt đầu.
- Kiểm tra token và auth epoch ngay trước lúc gửi request.
- Giữ kiểm tra session, CSRF và authorization ở server cho **mọi request**.
- Với nghiệp vụ nhạy cảm, áp dụng transaction/idempotency và thiết kế retry riêng.
- Không tự gửi lại thao tác ghi khi phiên thay đổi hoặc sau 403.

### 12.3. Nhiều tab dùng chung cookie nhưng không chung JavaScript state

Cookie của cùng origin có thể được dùng chung giữa các tab, trong khi biến lưu token trong memory của từng tab là riêng. Nếu tab A logout/login, tab B có thể tiếp tục giữ CSRF token của phiên cũ.

Có thể dùng tín hiệu **BroadcastChannel** để thông báo “trạng thái đăng nhập đã thay đổi” giữa các tab cùng origin, hoặc kiểm tra token/phiên khi tab focus lại. Không cần phát tán token bí mật qua BroadcastChannel chỉ để báo một sự kiện. Tín hiệu có thể bị bỏ lỡ, nên backend vẫn phải là nguồn xác thực cuối cùng.

Khi chuyển tài khoản A → B trong một SPA, xóa dữ liệu tài khoản cũ, token cũ và cache nhạy cảm, rồi GET token trong phiên mới. **CSRF token không thay thế kiểm soát phân quyền hoặc tách biệt dữ liệu giữa tài khoản.**

## 13. Chẩn đoán lỗi thường gặp

### “Login thành công nhưng POST đầu tiên 403, reload trang lại được”

Khả năng thường gặp là frontend còn giữ token từ trước login. Kiểm tra GET /api/csrf có được gọi **sau login thành công** không, cookie phiên đã cập nhật chưa, POST có gửi đúng headerName và token mới không. Xem lỗi **InvalidCsrfTokenException** hoặc **MissingCsrfTokenException** khi có log an toàn.

### “Sau login không thấy XSRF-TOKEN cookie”

Với **HttpSessionCsrfTokenRepository**, token có thể lưu trong session và cấp qua JSON, không có XSRF cookie. Với **CookieCsrfTokenRepository**, kiểm tra deferred loading, GET bootstrap có truy cập token không, cookie Secure/Domain/Path, cùng việc browser có chặn cookie không.

### “Logout POST trả 403 nhưng frontend đã hiện đã đăng xuất”

Có thể frontend xóa CSRF token **trước** khi gửi logout. Kiểm tra LogoutFilter, endpoint/method, cookie và token của phiên hiện hành. Không đánh dấu logout hoàn tất nếu backend chưa xác nhận; nếu logout không thành công, session vẫn có thể đang authenticated.

### “Logout xong GET /api/csrf tạo JSESSIONID mới”

Với repository dùng HttpSession, token anonymous có thể cần một session mới để lưu. **JSESSIONID mới không đồng nghĩa người dùng vẫn đăng nhập.** Xác minh SecurityContext/principal và quyền trên API protected.

### “Token sau login nhìn giống trước login”

Có thể so sánh nhầm masked representation với raw token, hoặc ứng dụng có custom lifecycle. XOR masking có thể đổi chuỗi dù raw token không đổi. Đừng chẩn đoán chỉ bằng độ dài/giá trị token; kiểm tra repository và hành vi request.

### “Token mới đúng, cookie đúng nhưng vẫn 401/403”

Kiểm tra authentication, quyền, audience/scope nếu có JWT, Spring Security chain phù hợp, cùng exception thực sự phát sinh. Token CSRF đúng không cấp quyền truy cập.

### “SPA khác origin chỉ lỗi sau login”

Kiểm tra **credentials: include** ở login, GET token và POST; **CORS** preflight, redirect và Set-Cookie, SameSite/Secure, Domain/Path và third-party cookies. Không chữa bằng cách bật Access-Control-Allow-Credentials cho Origin không giới hạn.

### “Dùng JWT Bearer rồi còn cần CSRF token sau login?”

API chỉ nhận **Authorization: Bearer** do client chủ động gắn, không chấp nhận cookie/browser-managed fallback, thường không có CSRF browser truyền thống trên các route đó. Nhưng **login/refresh/logout dùng cookie**, BFF hoặc session cookie ở gateway vẫn phải đánh giá CSRF riêng. Tính stateless của backend không phải tiêu chí duy nhất.

## 14. Các lớp bảo vệ HTTP vẫn cần duy trì

| Lớp bảo vệ | Tác dụng và giới hạn |
| --- | --- |
| **HttpOnly session cookie** | Giảm JavaScript đọc session ID; browser vẫn có thể tự gửi cookie |
| **Secure + HTTPS/HSTS** | Bảo vệ cookie/response qua kết nối an toàn, không chứng minh ý định request |
| **SameSite** | Hạn chế nhiều request cross-site; cùng site không phải lúc nào cũng đáng tin |
| **CORS allowlist** | Hạn chế origin JavaScript được đọc CSRF token JSON và dùng credentials; không thay token verification |
| **CSP + chống XSS** | Giảm nguy cơ script độc hại cùng origin có thể đọc XSRF token hoặc gọi API |
| **HTTP firewall** | Chặn một số request bất thường, không thay CsrfFilter |
| **Authentication + authorization** | Kiểm tra danh tính/quyền độc lập với CSRF token |
| **Session fixation protection** | Hạn chế lạm dụng session ID trước login; vẫn cần đồng bộ token CSRF |
| **Cache-Control: no-store** | Hạn chế cache chia sẻ response chứa token theo ngữ cảnh phiên |

Không đưa **CSRF token, JSESSIONID, JWT** vào URL, log, analytics hoặc lỗi trả về. Khi debug, ghi loại exception, route, kết quả xác thực và correlation ID, không ghi bí mật.

## 15. Bài tập thực hành

**Bài tập A — Trước/sau login:** Với formLogin và session CSRF mặc định, lấy token A anonymous, đăng nhập dùng A, thử token A ở POST API và token B sau GET bootstrap. Giải thích kết quả dựa vào repository và strategy.

**Bài tập B — Logout đúng thứ tự:** Đăng nhập và có B, gửi POST logout với B, xác minh server logout rồi lấy token C. Chứng minh C không cấp quyền gọi API protected khi anonymous.

**Bài tập C — Cookie repository:** Đổi sang CookieCsrfTokenRepository cho SPA cùng origin và handler raw. Quan sát XSRF cookie có bị xóa/tạo lại qua auth transition không và GET nào thực sự materialize token.

**Bài tập D — Race condition:** Cố ý làm chậm response GET token anonymous, login, lấy token authenticated rồi cho response cũ đến sau. Kiểm chứng epoch ngăn token cũ ghi đè.

**Bài tập E — Nhiều tab:** Mở hai tab, login/logout tab A và POST từ tab B; thiết kế tín hiệu auth changed và luồng lấy token mới.

**Bài tập F — Khác origin:** SPA tại app.example.com, API tại api.example.com, cookie session. So sánh GET bootstrap sau login khi có hoặc thiếu credentials include; xác minh CORS allowlist, preflight và cookie policy.

**Bài tập G — WebFlux:** Dùng SecurityWebFilterChain, endpoint Mono<CsrfToken> và POST API có CSRF. Kiểm thử vòng đời authentication/logout Reactive với WebSession/cookie thực và việc Mono được subscribe.

**Bài tập H — Login thất bại:** Thử sai mật khẩu, kiểm tra SPA không báo authenticated; kiểm tra session/CSRF state có thực sự thay đổi không trước khi cho phép hành động tiếp theo.

## 16. Nguyên tắc cần ghi nhớ

1. **Login/logout là ranh giới xác thực:** sau khi backend xác nhận thành công, frontend không được dùng mù quáng token cũ.
2. **POST login cần token trước login** và **POST logout cần token còn hiệu lực trước logout**, nếu endpoint dùng CSRF protection.
3. **CsrfAuthenticationStrategy và CsrfLogoutHandler** trong Servlet có thể xóa token cũ; **deferred loading** nghĩa là token mới có thể chỉ xuất hiện ở GET kế tiếp.
4. **GET /api/csrf** phải dùng đúng repository, cookie/phiên và request handler, hiện thực hóa token và không cache chia sẻ.
5. **Session ID và CSRF token có vòng đời khác nhau:** session ID có thể đổi do session fixation protection; token có thể bị xóa riêng.
6. **Raw XSRF cookie và XOR-masked token khác định dạng**, phải thống nhất frontend với request handler sau mỗi lần refresh.
7. **SPA khác origin cần credentials và CORS phù hợp** cho cả GET token lẫn thao tác ghi, nhưng CORS không thay thế CSRF.
8. **Đồng bộ trạng thái nhiều request và nhiều tab**, không để GET cũ ghi đè token mới hoặc retry POST nguy hiểm chỉ vì 403.
9. **WebFlux có API và cơ chế lifecycle riêng**, phải kiểm thử authentication/logout Reactive thực tế.
10. **CSRF token không thay thế chống XSS, xác thực, phân quyền, bảo vệ cookie và validation**; hãy kiểm thử cả trạng thái dữ liệu.

Một SPA Spring Security ổn định sẽ thực hiện đúng thứ tự tại mỗi ranh giới: **xác minh login/logout thành công với backend → đồng bộ cookie/session hiện hành → lấy token CSRF phù hợp với trạng thái mới → cho phép thao tác ghi tiếp theo**. Đó là cách tránh lỗi token hết hiệu lực và duy trì lớp phòng vệ HTTP nhất quán khi người dùng đăng nhập, đăng xuất hoặc chuyển tài khoản.


