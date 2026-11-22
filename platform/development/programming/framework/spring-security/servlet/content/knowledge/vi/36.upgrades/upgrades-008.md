# Thay đổi CSRF token tải trì hoãn, che token và tích hợp SPA trong Spring Security Servlet

## 1. Bối cảnh nâng cấp: Spring Security 6 và các lỗi 403 khó hiểu

Khi chuyển ứng dụng **Spring Security Servlet** từ dòng 5.x lên **Spring Security 6.x** (thường với Spring Boot 3 và Jakarta Servlet), nhiều hệ thống gặp hiện tượng: GET trang web vẫn thành công nhưng POST bị 403, cookie CSRF không xuất hiện ở GET đầu tiên, hoặc SPA đã gửi header `X-XSRF-TOKEN` nhưng server vẫn báo token không hợp lệ.

Đây không có nghĩa Spring Security đã bỏ bảo vệ CSRF. Hai thay đổi quan trọng cần hiểu là:

1. **Deferred CSRF token**: tải hoặc tạo token **khi cần**, thay vì luôn truy cập repository ngay khi request đến.
2. **CSRF token masking chống BREACH**: token trình bày trong HTML/request attribute có thể được **che bằng giá trị ngẫu nhiên**. Giá trị này khác với **raw token** lưu trong repository hay cookie của SPA.

Một SPA đọc token từ cookie `XSRF-TOKEN` và gửi nó trong header `X-XSRF-TOKEN` thường gửi **raw token**, không phải masked token. Nếu server cấu hình handler chỉ chờ masked form value, raw header có thể bị xử lý sai và POST bị từ chối. Mặt khác, chỉ tắt bảo vệ CSRF để “hết 403” sẽ bỏ một hàng rào quan trọng khi browser dùng **session cookie** hoặc credentials được tự động gửi.

**Mục tiêu bài học:** giải thích ý nghĩa của deferred loading và XOR masking, chọn repository/request handler đúng cho SPA, giữ tương thích server-rendered form, xử lý vòng đời token khi login/logout và viết bài kiểm thử HTTP thực sự gửi cookie/header. Ví dụ dành cho **Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring MVC/Servlet**; các URL và tên API là ví dụ học tập. Hãy kiểm version khi áp dụng vào ứng dụng thực tế.

## 2. CSRF là gì, và khi nào ứng dụng thực sự cần bảo vệ?

CSRF (Cross-Site Request Forgery) xảy ra khi trang độc hại khiến trình duyệt của người dùng gửi một request không mong muốn tới ứng dụng mà browser đang có credentials tự gửi, thường là cookie xác thực. Nếu server chỉ nhìn cookie phiên rồi chấp nhận thay đổi trạng thái, kẻ tấn công có thể lợi dụng quyền của nạn nhân mà không biết mật khẩu.

Ví dụ request hợp lệ với hệ thống dùng session:

~~~http
POST /api/preferences HTTP/1.1
Host: app.example.test
Cookie: JSESSIONID=<session-cookie>; XSRF-TOKEN=<raw-csrf-token>
Content-Type: application/json
X-XSRF-TOKEN: <raw-csrf-token>

{"theme":"dark"}
~~~

Các giá trị trong dấu ngoặc nhọn là **ký hiệu minh họa**, không phải secret thật. Cookie xác thực `JSESSIONID` do browser gửi tự động. Cookie CSRF `XSRF-TOKEN` cũng có thể được gửi tự động; chính việc SPA **đọc token rồi đặt header** theo hợp đồng server tạo ra tín hiệu bổ sung giúp phân biệt request có nguồn gốc hợp lệ.

**Cookie CSRF token tồn tại thôi chưa đủ**: nếu server chỉ kiểm một cookie mà browser luôn tự gửi, tác dụng chống CSRF suy giảm. Phải so sánh expected token với **submitted token độc lập** ở form parameter hoặc request header, theo cơ chế framework.

### CSRF không phải XSS, CORS hay authorization

- **CSRF**: request do browser tự mang credentials nhưng không được người dùng chủ động ủy quyền cho hành động đó.
- **XSS**: JavaScript độc hại chạy trong cùng origin; nếu SPA có thể đọc CSRF cookie thì XSS cũng có thể đọc và gửi request. CSRF token không thay thế phòng XSS.
- **CORS**: giới hạn quyền truy cập cross-origin qua trình duyệt. CORS không tự thay thế CSRF token, đặc biệt với simple requests hoặc sai cấu hình origin.
- **Authorization**: kiểm ai được phép làm gì. Có CSRF token hợp lệ không đồng nghĩa user được phép thay tài khoản của người khác.
- **SameSite cookie**: giảm một số tình huống cookie được gửi cross-site, nhưng không phải cơ chế thay thế đầy đủ cho CSRF defense trong mọi kiến trúc.

Một API thực sự **stateless, chỉ nhận Bearer token do client chủ động đính Authorization header và không nhận credentials tự động** có threat model khác. Nhưng **JWT trong cookie** hoặc HTTP Basic tự gửi bởi browser vẫn có nguy cơ CSRF; không lấy chữ “REST”/“JWT” làm lý do tắt CSRF toàn cục.

## 3. Phân biệt raw token, masked token và submitted token

| Khái niệm | Nơi tồn tại | Cách sử dụng |
| --- | --- | --- |
| **Expected/raw token** | `CsrfTokenRepository` (session hoặc cookie) | Giá trị gốc server dùng để đối chiếu |
| **Masked token** | Attribute như `_csrf.token` khi render HTML | Được biến đổi bằng random mask để giảm nguy cơ BREACH; form gửi lại giá trị này |
| **Submitted token** | Request header hoặc form parameter | `CsrfTokenRequestHandler` resolve/giải mã rồi đưa cho `CsrfFilter` so sánh |

Giả sử raw token trong repository là `T`. Lần render form thứ nhất, XOR handler xuất `M1`; lần render tiếp theo xuất `M2`. Cả `M1` và `M2` có thể đại diện **cùng raw token T**, không nhất thiết nghĩa là repository đã rotate token. Đây là trạng thái hợp lệ khi mỗi render có một random mask khác.

Trong SPA dùng `CookieCsrfTokenRepository`, cookie thường chứa **`T`**. JavaScript gửi header `X-XSRF-TOKEN: T`. Server phải nhận ra header này là **plain/raw**, không tự áp phép giải mã XOR vốn dành cho masked form token.

**BREACH masking không phải encryption hay chữ ký token.** Nó thay biểu diễn token trên response nhằm giảm một dạng compression side channel, không thay thế kiểm ngẫu nhiên, entropy, comparison, TLS, cookie security hay CSRF policy.

### Vì sao token trong hidden HTML input có thể thay đổi mỗi GET?

`XorCsrfTokenRequestAttributeHandler` dùng mask ngẫu nhiên để tránh raw CSRF token xuất hiện ổn định trong những response nén chứa dữ liệu attacker có thể ảnh hưởng. Mã token hidden có thể khác giữa hai lần render trong cùng session dù giá trị token gốc không đổi.

Đừng so sánh raw cookie token với giá trị hidden form đã masked rồi kết luận cookie bị hỏng. Đừng gửi masked HTML token trong header mà một custom SPA handler đang chờ raw cookie token. Đường resolve phải nhất quán với cách sinh giá trị.

## 4. Deferred CSRF token: trì hoãn việc tải

**`CsrfTokenRepository`** chịu trách nhiệm `generateToken`, `saveToken` và `loadToken`. Spring Security 6 sử dụng cơ chế deferred token thông qua supplier để tránh việc tải/tạo token ở những request không cần dùng.

Luồng GET khái niệm:

~~~text
GET /api/public
     │
     ▼
SecurityFilterChain → CsrfFilter
     │
     ├─ Lấy deferred CSRF supplier
     ├─ CsrfTokenRequestHandler.handle(...) thiết lập request attribute
     ├─ Controller trả JSON không dùng _csrf
     └─ Không cần validate CSRF vì GET là safe method
                   │
                   ▼
      Có thể KHÔNG gọi repository để load/generate
      Và có thể KHÔNG có Set-Cookie: XSRF-TOKEN
~~~

Luồng POST cần CSRF:

~~~text
POST /api/update
     │
     ▼
CsrfFilter xác định unsafe method
     │
     ├─ Load/generate expected token từ repository
     ├─ Handler resolve submitted token từ header/form
     ├─ So sánh hai giá trị
     │
     ├─ Khớp → tiếp tục authorization/controller
     └─ Thiếu/sai → AccessDeniedHandler → HTTP 403
~~~

Spring Security có matcher mặc định thường bảo vệ các method không thuộc nhóm safe như GET, HEAD, OPTIONS, TRACE. **GET phải thật sự không có side effect**; nếu developer dùng GET để chuyển tiền hoặc thay quyền, CSRF matcher không thể tự sửa thiết kế sai đó.

### 4.1. Lợi ích và tác động nâng cấp

Deferred loading có thể giảm thao tác trên session store/repository khi người dùng chỉ xem nội dung, đặc biệt với traffic GET lớn. Tuy nhiên nếu frontend **cần cookie token ngay trong GET bootstrap**, server phải chủ động materialize token. Nếu không, SPA mở trang rồi POST ngay có thể thiếu cookie.

Điều này giải thích vì sao một trang có form server-rendered nhận token bình thường (template truy cập `_csrf.token` làm load), còn một endpoint JSON GET không dùng token có thể không gửi `Set-Cookie`.

Không thể hứa “mọi GET luôn lazy”: view rendering, cấu hình handler, CSRF token endpoint hoặc việc gọi supplier `get()` có thể kích hoạt load. Đo request thực tế thay vì suy luận từ URL.

### 4.2. Ví dụ Java 17 thuần về lazy loading

Ví dụ file `DeferredTokenDemo.java` **chạy với JDK 17+, không cần Spring**. Nó minh họa supplier lười tải, **không phải implementation bảo mật CSRF thực tế**.

~~~java
import java.util.function.Supplier;

public class DeferredTokenDemo {
    static final class LazyToken implements Supplier<String> {
        private String cached;
        private int loads;

        @Override
        public String get() {
            if (cached == null) {
                cached = "example-raw-token";
                loads++;
            }
            return cached;
        }

        int loadCount() {
            return loads;
        }
    }

    public static void main(String[] args) {
        LazyToken token = new LazyToken();

        System.out.println("before=" + token.loadCount());
        System.out.println("first=" + token.get());
        System.out.println("after=" + token.loadCount());
        System.out.println("second=" + token.get());
        System.out.println("loads=" + token.loadCount());
    }
}
~~~

Chạy:

~~~bash
javac DeferredTokenDemo.java
java DeferredTokenDemo
~~~

Stdout **chính xác**:

~~~text
before=0
first=example-raw-token
after=1
second=example-raw-token
loads=1
~~~

Cách cache của supplier thật trong Spring Security phụ thuộc request/repository lifecycle; ví dụ chỉ dùng để giải thích từ “deferred”, không dùng nó để tạo token hoặc quyết định quyền.

## 5. XorCsrfTokenRequestAttributeHandler: token che chống BREACH

**BREACH** là một loại tấn công side channel khai thác biến thiên kích thước response bị nén khi một secret ổn định được đưa vào output và attacker có thể điều khiển một phần nội dung phản chiếu. CSRF token xuất nguyên văn liên tục trong HTML form là một ví dụ rủi ro dưới các điều kiện thích hợp.

Spring Security Servlet sử dụng `XorCsrfTokenRequestAttributeHandler` để xuất **masked representation** qua request attribute khi render, sau đó resolve lại giá trị do form submit để so sánh raw token. Ví dụ template nhận:

~~~html
<form action="/profile" method="post">
  <input type="hidden"
         name="_csrf"
         value="masked-value-produced-by-server">
  <button type="submit">Save</button>
</form>
~~~

Đây là ví dụ HTML giản lược; giá trị masked là **ký hiệu**, không phải giá trị format thật. Không tự viết thuật toán XOR/encode trên frontend; giao cho handler của Spring Security.

Vì mask mới có thể được tạo mỗi lần render, giá trị `_csrf.token` có thể thay đổi dù repository raw token giữ nguyên. Ngược lại, khi login/logout xóa raw token, chính giá trị expected token thay đổi và một form cũ có thể không còn hợp lệ.

### 5.1. Thay cả ứng dụng bằng plain handler có an toàn không?

`CsrfTokenRequestAttributeHandler` plain có thể nhận raw token trong header, nhưng nếu dùng nó thay XOR handler **trên mọi response server-rendered**, HTML form có thể không còn lợi ích BREACH masking. Một cách tích hợp SPA tốt là giữ XOR cho attribute/form và chỉ dùng plain resolver đối với **raw header** từ SPA.

Chú ý: trong thiết kế dưới đây, **header `X-XSRF-TOKEN` luôn được xem là raw**. Nếu client lấy masked hidden form token và chuyển nguyên sang header này, request có thể thất bại. Form truyền masked qua parameter `_csrf`; SPA truyền raw qua header.

## 6. Repository: Session CSRF và Cookie CSRF khác nhau

| Tiêu chí | `HttpSessionCsrfTokenRepository` | `CookieCsrfTokenRepository` |
| --- | --- | --- |
| Lưu expected token | HTTP session do server quản lý | Cookie do browser giữ và gửi |
| Tích hợp thường gặp | MVC server-rendered form và session login | SPA cần đọc raw token từ cookie |
| Cần JS đọc token? | Không nhất thiết; view dùng attribute | Thường có; dùng `withHttpOnlyFalse()` khi cần |
| Phụ thuộc session store | Có | Token cookie riêng có lifecycle khác; authentication vẫn có thể dùng session |
| Rủi ro cần đánh giá | Session persistence, expiry, fixation, multi-node | XSS, cookie injection, Domain/Path/SameSite/Secure, trusted subdomains |
| Cách gửi submitted token | Hidden form parameter/header theo handler | Header raw của SPA hoặc form value theo handler |

`CookieCsrfTokenRepository` mặc định thường dùng cookie tên **`XSRF-TOKEN`**, header **`X-XSRF-TOKEN`** và form parameter **`_csrf`**; xem lại nếu application đã custom names. CSRF cookie **không phải session authentication cookie**. Có token không chứng minh user đã đăng nhập.

`CookieCsrfTokenRepository.withHttpOnlyFalse()` đặt cookie để JavaScript đọc được. Đây là **tradeoff có chủ đích** cho SPA. Không áp dụng nó cho session cookie; cookie xác thực vẫn nên có `HttpOnly` và `Secure`, flags/path/same-site theo kiến trúc thực tế.

### Cookie chưa có vì token bị trì hoãn

Với deferred loading, GET public không truy cập token có thể không tạo cookie. SPA cần một request bootstrap tạo token. Pattern mẫu tại mục 7 gọi `csrfToken.get()` trong custom handler để materialize supplier khi request đi qua, làm cookie sẵn sàng trước mutation.

Đổi lại, cách này có thể tải token ngay trong cả GET không cần CSRF form — **không còn tối ưu lazy trên toàn bộ chain**. Đây là lựa chọn tradeoff hợp lý cho same-origin SPA; muốn giữ lazy ở đa số GET, có thể bootstrap token tại một endpoint hạn chế và test kỹ cơ chế repository/attribute ở phiên bản đang dùng.

## 7. Cấu hình Spring Security 6 cho SPA dùng session cookie

Ví dụ sau chạy trong **dự án Spring Boot 3.x với Java 17+, Spring Web MVC và Spring Security 6.x**. Các class được biên dịch/chạy qua Gradle hoặc Maven có dependency, **không phải** các file JDK độc lập.

### 7.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Các ví dụ đặt trong:

~~~text
src/main/java/com/example/demo/
  DemoApplication.java
  security/SpaCsrfTokenRequestHandler.java
  security/SecurityConfig.java
  web/DemoApiController.java
src/test/java/com/example/demo/
  SpaCsrfIntegrationTest.java
~~~

### 7.2. Handler vừa hỗ trợ XOR form vừa hỗ trợ raw SPA header

File `SpaCsrfTokenRequestHandler.java` trong package `com.example.demo.security`:

~~~java
package com.example.demo.security;

import java.util.function.Supplier;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.CsrfTokenRequestAttributeHandler;
import org.springframework.security.web.csrf.CsrfTokenRequestHandler;
import org.springframework.security.web.csrf.XorCsrfTokenRequestAttributeHandler;
import org.springframework.util.StringUtils;

public final class SpaCsrfTokenRequestHandler
        implements CsrfTokenRequestHandler {

    private final CsrfTokenRequestHandler plain =
        new CsrfTokenRequestAttributeHandler();

    private final CsrfTokenRequestHandler xor =
        new XorCsrfTokenRequestAttributeHandler();

    @Override
    public void handle(HttpServletRequest request,
                       HttpServletResponse response,
                       Supplier<CsrfToken> csrfToken) {
        // Token render trong HTML attribute vẫn được XOR mask.
        xor.handle(request, response, csrfToken);

        // Buộc token tải/generate để SPA có raw cookie.
        csrfToken.get();
    }

    @Override
    public String resolveCsrfTokenValue(HttpServletRequest request,
                                        CsrfToken csrfToken) {
        String value = request.getHeader(
            csrfToken.getHeaderName());

        // Header SPA mang raw token. Form parameter mang masked.
        return (StringUtils.hasText(value) ? plain : xor)
            .resolveCsrfTokenValue(request, csrfToken);
    }
}
~~~

Đây là lớp triển khai thực sự của `CsrfTokenRequestHandler` theo API Spring Security 6. **Không tự thêm `CsrfFilter` thứ hai**. Logic:

1. `xor.handle(...)` thiết lập request attribute phù hợp cho server-rendered forms; giá trị trình bày được che.
2. `csrfToken.get()` ép supplier load/generate token cần thiết và có thể khiến repository ghi `Set-Cookie: XSRF-TOKEN=...` nếu chưa có.
3. Nếu request mang header không rỗng mang tên theo `csrfToken.getHeaderName()`, handler dùng plain resolver. Token mà client gửi **phải là raw value** trong cookie.
4. Nếu không có header, handler dùng XOR resolver để nhận masked form parameter.
5. `CsrfFilter` tiếp tục so sánh expected/submitted token. Đường code không “cho qua vì có header”, không tắt kiểm tra CSRF.

**Điểm giới hạn:** nếu một thư viện frontend lấy masked form token và đưa vào header `X-XSRF-TOKEN`, handler trên coi nó là raw và có thể từ chối. Giao thức SPA phải nhất quán: **cookie raw → header raw**, SSR form masked → parameter masked.

### 7.3. SecurityFilterChain

File `SecurityConfig.java` trong package `com.example.demo.security`:

~~~java
package com.example.demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/bootstrap")
                    .permitAll()
                .requestMatchers("/api/preferences").authenticated()
                .anyRequest().permitAll())
            .formLogin(Customizer.withDefaults())
            .csrf(csrf -> csrf
                .csrfTokenRepository(
                    CookieCsrfTokenRepository.withHttpOnlyFalse())
                .csrfTokenRequestHandler(
                    new SpaCsrfTokenRequestHandler()));

        return http.build();
    }
}
~~~

**Lưu ý:** `anyRequest().permitAll()` chỉ để dễ học trong demo nhỏ, **không phải chính sách production**. Phải bảo vệ các API thực bằng role/authority/tenant/resource authorization và giới hạn các route. Form login dùng cookie phiên nên CSRF được giữ bật. CSRF token không chứng minh caller đã đăng nhập.

Nếu browser dùng một cookie session khác, cần xác định rõ `Secure`, `HttpOnly`, `SameSite`, session fixation protection, logout lifecycle và cookie path/context path. Không cấu hình `withHttpOnlyFalse()` cho session cookie.

### 7.4. Application class

File `DemoApplication.java` trong package `com.example.demo`:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 7.5. Controller thử nghiệm

File `DemoApiController.java` trong package `com.example.demo.web`:

~~~java
package com.example.demo.web;

import java.util.Map;
import java.util.Set;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class DemoApiController {
    public record PreferenceInput(String theme) {}

    @GetMapping("/api/bootstrap")
    public Map<String, String> bootstrap() {
        return Map.of("status", "ready");
    }

    @PostMapping("/api/preferences")
    public Map<String, String> save(
            @RequestBody PreferenceInput input) {
        if (input == null
            || !Set.of("dark", "light").contains(input.theme())) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Unsupported theme");
        }
        // Demo chỉ echo theme; không ghi database.
        return Map.of("theme", input.theme());
    }
}
~~~

`GET /api/bootstrap` là safe GET giúp browser kích hoạt handler. `POST /api/preferences` phải đáp ứng cả **CSRF validation** lẫn `authenticated()`, sau đó mới tới controller. Test Java ở mục 10 dùng mock authenticated user để không phụ thuộc tài khoản hay mật khẩu thật.

## 8. SPA JavaScript: đúng trình tự GET cookie, POST header

Ví dụ này dành cho **SPA và backend cùng origin**, không dùng cross-origin. SPA trước tiên GET bootstrap để server phát cookie token. Sau đó JavaScript đọc `XSRF-TOKEN` và gắn raw token vào header `X-XSRF-TOKEN` của request POST.

~~~javascript
function readCookie(name) {
  const prefix = name + "=";
  const pair = document.cookie
    .split("; ")
    .find(item => item.startsWith(prefix));

  return pair
    ? decodeURIComponent(pair.slice(prefix.length))
    : null;
}

async function getCsrfToken() {
  const response = await fetch("/api/bootstrap", {
    method: "GET",
    credentials: "same-origin",
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error("CSRF bootstrap failed");
  }

  const rawToken = readCookie("XSRF-TOKEN");
  if (!rawToken) {
    throw new Error("Missing XSRF-TOKEN cookie");
  }
  return rawToken;
}

async function saveTheme() {
  const csrf = await getCsrfToken();
  const response = await fetch("/api/preferences", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-XSRF-TOKEN": csrf
    },
    body: JSON.stringify({ theme: "dark" })
  });

  if (!response.ok) {
    throw new Error("HTTP " + response.status);
  }
  return response.json();
}
~~~

**Client không đưa token vào URL/query**, không gửi token đến third-party endpoint và không log giá trị token. Browser gửi cookies theo chính sách origin/credentials; raw CSRF header xuất hiện do script tự thêm.

Có CSRF token không tự đồng nghĩa user đã đăng nhập. Khi chưa đăng nhập, POST có token hợp lệ vẫn có thể nhận 302 redirect tới trang login hoặc 401 (tùy entry point). Đừng nhầm đó với 403 do CSRF.

### 8.1. Sau login/logout phải làm gì?

Spring Security có các thành phần như `CsrfAuthenticationStrategy` và `CsrfLogoutHandler` để xóa CSRF token cũ trong những luồng xác thực/logout phù hợp. Với deferred token, token mới không nhất thiết xuất hiện ngay cùng response. Vì thế SPA cần:

1. Login với token hợp lệ theo policy.
2. Sau khi authentication hoàn tất, **GET bootstrap mới**.
3. Đọc cookie mới và dùng token mới cho POST/PUT/PATCH/DELETE.
4. Sau logout, xóa bản cache raw token ở frontend và bootstrap lại trước một mutation tiếp theo.

**Không dùng mã token trước login (T1) sau khi login nếu server đã xóa/rotate sang T2.** Nhiều tab có thể gặp stale token khi một tab khác đăng nhập, đổi session hoặc logout. Nếu nhận 403, frontend phải phân biệt CSRF failure với permission denied; không retry mutation không idempotent vô hạn.

### 8.2. Vì sao same-origin khác cross-origin?

Nếu SPA ở `https://app.example.test` còn API ở `https://api.example.test`, đây là cross-origin. Một cookie host-only từ `api.example.test` **không thể đọc bằng `document.cookie` tại `app.example.test`** chỉ vì dùng `credentials: "include"`.

Cần thiết kế lại giao thức bootstrap, cookie Domain/Path/Secure/SameSite, CORS allowlist chính xác, credentials policy và threat model. Không bật `Access-Control-Allow-Origin: *` cùng credentials. Nếu phải cấp token cho frontend qua API riêng, đảm bảo endpoint có origin/authorization controls phù hợp, response không bị cache công khai, và JS không ghi token vào analytics/log.

Với cross-site thật, `SameSite=None; Secure` và browser third-party cookie policies có thể ảnh hưởng khả năng gửi cookie. Đây không phải chỉ là sửa một header: phải test trong browser qua proxy/HTTPS thực tế.

## 9. Form SSR vẫn dùng XOR masked token

Một ứng dụng có cả Thymeleaf/JSP và SPA nên hỗ trợ **hai cách trình bày** mà không tắt masking toàn cục.

Ví dụ Thymeleaf form:

~~~html
<form th:action="@{/profile}" method="post">
  <input type="hidden"
         th:name="${_csrf.parameterName}"
         th:value="${_csrf.token}">
  <button type="submit">Save</button>
</form>
~~~

`${_csrf.token}` được template engine đọc từ request attribute và có thể là **masked representation** do XOR handler cung cấp. Khi POST, form gửi parameter `_csrf`, handler chọn XOR resolver để giải token. Một số tích hợp Spring/Thymeleaf có thể tự tạo hidden CSRF field; ví dụ viết tường minh để minh họa.

**Không lấy chuỗi từ hidden form rồi gửi làm raw `X-XSRF-TOKEN` header.** Trong mẫu request handler ở mục 7, chỉ đường form parameter được XOR resolve; header luôn được coi raw.

Với ứng dụng **SSR-only** không cần JS đọc cookie, lựa chọn đơn giản thường là giữ session repository + XOR handler mặc định. Không cần cấu hình `CookieCsrfTokenRepository.withHttpOnlyFalse()` chỉ vì đang dùng Spring Security 6.

## 10. Kiểm thử MockMvc qua HTTP cookie/header thật

`spring-security-test` có helper `.with(csrf())` rất tiện cho unit/authorization tests. Nhưng test chỉ dùng helper có thể pass dù SPA thực tế không lấy được cookie hoặc raw header đi sai handler. Nên viết test:

**GET bootstrap → kiểm cookie → POST kèm chính cookie + raw header**.

File `SpaCsrfIntegrationTest.java` trong package `com.example.demo`:

~~~java
package com.example.demo;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class SpaCsrfIntegrationTest {

    @Autowired
    MockMvc mvc;

    private Cookie bootstrapCookie() throws Exception {
        MvcResult result = mvc.perform(get("/api/bootstrap"))
            .andExpect(status().isOk())
            .andReturn();

        Cookie cookie = result.getResponse()
            .getCookie("XSRF-TOKEN");
        assertNotNull(cookie);
        return cookie;
    }

    @Test
    void bootstrapIssuesCsrfCookie() throws Exception {
        bootstrapCookie();
    }

    @Test
    void cookieAloneDoesNotSatisfyCsrf() throws Exception {
        Cookie token = bootstrapCookie();

        mvc.perform(post("/api/preferences")
                .with(user("alice"))
                .cookie(token)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"theme\":\"dark\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void rawCookieHeaderIsAccepted() throws Exception {
        Cookie token = bootstrapCookie();

        mvc.perform(post("/api/preferences")
                .with(user("alice"))
                .cookie(token)
                .header("X-XSRF-TOKEN", token.getValue())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"theme\":\"dark\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.theme").value("dark"));
    }

    @Test
    void invalidHeaderIsRejected() throws Exception {
        Cookie token = bootstrapCookie();

        mvc.perform(post("/api/preferences")
                .with(user("alice"))
                .cookie(token)
                .header("X-XSRF-TOKEN", "invalid-value")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"theme\":\"dark\"}"))
            .andExpect(status().isForbidden());
    }
}
~~~

**Ý nghĩa từng test:**

- `bootstrapIssuesCsrfCookie`: GET public không dùng token vẫn phát cookie vì custom SPA handler gọi deferred supplier `get()`.
- `cookieAloneDoesNotSatisfyCsrf`: browser chỉ gửi cookie nhưng thiếu submitted header → 403.
- `rawCookieHeaderIsAccepted`: request đi qua filter chain, repository cookie, raw-header resolver; CSRF hợp lệ và mock authenticated principal có quyền vào endpoint.
- `invalidHeaderIsRejected`: cookie đúng mà header sai → 403.
- `.with(user("alice"))` chỉ dựng user trong test; **không kiểm xác thực password/login thật**. Với Spring Boot test và SecurityFilterChain, nó giúp tập trung vào CSRF.
- Các test trên chưa chứng minh rotation sau login/logout, CORS hay cookie behavior qua browser/proxy thực; cần bổ sung integration tests theo môi trường.

Lệnh chạy trong dự án có Gradle wrapper:

~~~bash
./gradlew test --tests com.example.demo.SpaCsrfIntegrationTest
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test --tests com.example.demo.SpaCsrfIntegrationTest
~~~

**Không giả lập stdout Gradle hay tuyên bố test đã chạy** khi không có môi trường dự án được thiết lập. Phải chạy thực tế để xác minh Spring Security version/dependencies, filter chain, cookie path và app context.

### 10.1. Ma trận kiểm thử mở rộng

| Trường hợp | Kỳ vọng |
| --- | --- |
| GET/bootstrap khi chưa có cookie | Nhận `XSRF-TOKEN` khi handler materialize |
| POST chỉ có cookie | 403 |
| POST có raw header đúng với cookie | Qua CSRF, tiếp tục authentication/authorization |
| POST có header sai hoặc không có cookie | 403 |
| Form SSR với masked `_csrf` | Qua CSRF nếu repository/session phù hợp |
| Đưa masked form token vào header raw | Bị từ chối theo handler mẫu |
| POST token cũ sau login | Có thể 403 khi token bị xóa/rotate |
| Bootstrap lại sau login | Có token mới cho mutation kế tiếp |
| Logout POST không gửi token | 403 trong cấu hình bảo vệ logout |
| User thiếu authority nhưng token hợp lệ | 403 authorization, không phải CSRF |
| GET có side effect nghiệp vụ | Phải sửa thiết kế; mặc định safe method không kiểm CSRF |
| Cross-origin SPA thiếu cookie visibility | Bootstrap/header handshake không hoạt động |
| Cookie/path qua reverse proxy khác local | Kiểm cùng path, HTTPS, SameSite, context path |
| Trình duyệt mở hai tab và một tab logout | Tab kia cần xử lý stale token an toàn |

Đừng chỉ assert status 403 rồi kết luận CSRF đúng. Request có thể bị 403 vì thiếu quyền, sai tenant, CORS hoặc policy business. Cần xác định **filter/handler nào** từ logs an toàn, không log raw CSRF token.

## 11. Migration pitfalls: lựa chọn đúng thay vì tắt CSRF

### 11.1. Đổi toàn app sang plain handler?

Một số hướng dẫn cũ chuyển sang `CsrfTokenRequestAttributeHandler` plain hoặc tùy chỉnh `setCsrfRequestAttributeName(null)` để ép tải token sớm. Đây **không phải phương án mặc định** cho mọi SPA: plain handler ở server-rendered HTML có thể mất BREACH masking; setter liên quan request attribute/lazy behavior không tự giải quyết sự khác nhau giữa raw header và masked form.

Nên phân tách:
- Raw cookie/header của SPA dùng plain resolver.
- Masked form value dùng XOR resolver.
- Token được bootstrap khi browser cần, với cân nhắc hiệu năng.

### 11.2. Có nên gọi csrf.disable()?

**Không** chỉ vì POST sau nâng cấp trả 403. Trong session/cookie-based SPA, tắt CSRF có thể tạo lỗ hổng. Nếu app thực sự thuần stateless Bearer header, có thể xây SecurityFilterChain/API matcher riêng phù hợp threat model, nhưng cần chứng minh không còn credentials tự động gửi qua cookie/Basic hoặc các route browser side effect.

Dùng đúng matcher cho một số endpoint công khai hay không cần bảo vệ khi có cơ sở, không dùng `csrf.disable()` toàn cục như workaround thiếu điều tra.

### 11.3. Không thêm CsrfFilter trùng

Spring Security tự lắp CsrfFilter khi cấu hình `http.csrf(...)`. Thêm thêm một filter thủ công trong servlet container hoặc custom chain có thể khiến CSRF check chạy hai lần hoặc không đúng lifecycle. Ưu tiên chọn repository/handler/matcher qua API chính thức.

### 11.4. Cookie/domain và subdomain

Nếu cookie `XSRF-TOKEN` bị đọc bởi script không đáng tin hoặc có thể bị ghi giả bởi subdomain bị chiếm, mô hình bảo vệ bị ảnh hưởng. Tránh đặt cookie Domain quá rộng, cân nhắc host-only cookie, Secure flags và kiểm CORS allowlist. Một số kiến trúc cần bổ sung Origin/Referer validation hoặc token-binding policy phù hợp; không tự cho rằng double-submit cookie mặc định bảo vệ mọi vấn đề cookie injection.

### 11.5. Khi POST đầu tiên sau login vẫn 403

Hãy kiểm:

1. Login success có xóa token cũ qua CSRF authentication strategy không?
2. Frontend đã bootstrap lại sau khi login/redirect chưa?
3. Browser có nhận Set-Cookie mới và dùng đúng Path/Domain/SameSite/Secure không?
4. Request POST có mang cả cookie và raw header mới không?
5. Handler có đang chọn plain cho header, không cố XOR decode không?
6. Có nhiều security filter chains áp khác nhau cho GET và POST không?
7. 403 đến từ CSRF hay authorization?

Trả lời các câu trên an toàn hơn việc thêm một dòng tắt CSRF.

## 12. Bảng chẩn đoán lỗi thực tế

| Triệu chứng | Nguyên nhân có thể | Hướng giải quyết |
| --- | --- | --- |
| GET 200 nhưng không có CSRF cookie | Token chưa được materialize do lazy | Bootstrap/force supplier get; kiểm repository |
| Cookie có token nhưng header raw bị từ chối | XOR handler xử lý raw như masked | Dùng SPA request handler plain-header |
| Form SSR trước đây OK nay POST 403 | Server thay XOR/plain không nhất quán | Giữ form masked và XOR resolve |
| Hidden `_csrf.token` khác mỗi lần GET | Mask ngẫu nhiên; raw có thể không đổi | Không so chuỗi masked như raw |
| Login thành công rồi mutation đầu tiên 403 | Token cũ bị invalidated | GET bootstrap mới rồi gửi token mới |
| Logout 403 | Thiếu hoặc stale CSRF ở logout POST | Gửi token hợp lệ trước logout |
| SPA subdomain không đọc token | Cookie host-only khác origin | Thiết kế lại bootstrap/cookie/CORS |
| Postman OK, browser fail | Browser cookies, CORS, SameSite, CSRF khác | Quan sát request ở browser có kiểm soát |
| Header `X-XSRF-TOKEN` bị chặn | CORS preflight/proxy không cho header | Chỉnh allowlist hẹp, kiểm request thật |
| Token trong cookie nhưng mất trên POST | Path/Domain/SameSite/Secure/credentials không đúng | Kiểm Set-Cookie/Cookie qua HTTPS/proxy |
| Có cookie/header đúng nhưng 403 | Thiếu quyền, session expired hoặc filter khác | Tách CSRF vs authentication/authorization |
| Custom handler làm mọi GET tốn tài nguyên | `csrfToken.get()` buộc load | Dùng bootstrap hẹp hoặc đánh giá session store |
| Tab A logout, tab B POST 403 | Session/token đã đổi hoặc bị thu hồi | Bootstrap lại, xử lý stale an toàn |
| Test dùng `with(csrf())` đều xanh | Không kiểm cookie-header handshake | Viết GET cookie → POST raw header tests |
| API dùng JWT-cookie và tắt CSRF | Nhầm stateless token với cookie tự gửi | Đánh giá lại CSRF threat model |
| Form HTML lộ raw token qua response nén | Đã thay toàn handler sang plain | Xem xét bật lại XOR masking |
| Một node OK, node khác 403 | Session persistence/cookie routing khác | Kiểm cluster session store, proxy, sticky-session |

### Quan sát an toàn

Không đưa `Authorization`, `JSESSIONID`, `XSRF-TOKEN`, `X-XSRF-TOKEN` hoặc full `CsrfToken` object vào logs/traces. Thay vào đó có thể ghi loại lỗi `csrf.missing`/`csrf.invalid`, route template, HTTP method, status, correlation ID và chain/handler đã được chọn. Giới hạn thông tin lỗi public; không trả expected token hay raw submitted token cho client.

Một 403 từ `CsrfFilter` và 403 do thiếu authority có cách chữa hoàn toàn khác. Đừng dùng HTTP status đơn lẻ để ra quyết định retry.

## 13. Checklist nâng cấp production

- [ ] Xác nhận đúng Spring Boot/Security/Framework version và Servlet thay vì WebFlux.
- [ ] Lập bản đồ những request có credentials tự động (session cookie, JWT cookie, browser Basic) và những unsafe methods.
- [ ] Biết khi nào deferred token tải, khi nào GET chỉ trả nội dung mà không tạo cookie.
- [ ] Hiểu raw expected token khác masked token dùng để render SSR.
- [ ] Giữ XOR masking cho HTML form cần BREACH defense.
- [ ] Với same-origin SPA, đảm bảo `XSRF-TOKEN` cookie phát hành qua bootstrap và `X-XSRF-TOKEN` header mang **raw** cookie value.
- [ ] Dùng `CookieCsrfTokenRepository.withHttpOnlyFalse()` chỉ khi JavaScript phải đọc CSRF cookie.
- [ ] Không làm session auth cookie mất HttpOnly; cấu hình Secure/SameSite/Domain/Path phù hợp.
- [ ] Custom request handler chọn plain cho raw header và XOR cho masked form parameter; không bỏ so sánh token.
- [ ] Token mới được bootstrap sau login/logout/rotation; tab cũ không retry mutation nguy hiểm vô hạn.
- [ ] Không dùng token trong URL/query hay log, không phản chiếu secret vào error response.
- [ ] Không tắt CSRF toàn cục chỉ vì dùng SPA hoặc JWT.
- [ ] Kiểm cả authentication/authorization, CSRF, CORS và object-level permissions.
- [ ] Có MockMvc test cookie-only fail, raw header pass, header sai fail, form masked pass và token rotation.
- [ ] Kiểm browser qua HTTPS/reverse proxy, session cluster, cookie flags, CORS, nhiều tab và cache.
- [ ] Có kế hoạch rollout/rollback theo phiên bản và đo tác động nếu materialize token trên mọi GET.

**Kết luận:** Spring Security Servlet 6.x tách việc **tải token trì hoãn**, **biểu diễn token đã che chống BREACH** và **giải token người dùng gửi về**. Form SSR thường gửi masked `_csrf`, còn SPA dùng cookie phải gửi **raw `XSRF-TOKEN` trong header `X-XSRF-TOKEN`** theo request handler phù hợp. Để nâng cấp an toàn, hãy kiểm cả repository, handler, vòng đời login/logout và HTTP cookie/header thực tế; đừng loại bỏ CSRF defense chỉ để “hết lỗi 403”.
