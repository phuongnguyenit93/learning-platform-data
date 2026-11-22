# Truyền token qua biểu mẫu, tiêu đề HTTP và yêu cầu bất đồng bộ trong Spring Security reactive

## 1. Mục tiêu và ngữ cảnh

Một ứng dụng **Spring WebFlux / Spring Security reactive** có giao diện HTML, đăng nhập bằng cookie phiên, các biểu mẫu POST và những thao tác `fetch()` gửi JSON. Khi trình duyệt có thể tự gắn cookie đăng nhập vào request, một trang web bên ngoài có nguy cơ lợi dụng điều đó để gửi hành động trái ý người dùng. **Cross-Site Request Forgery (CSRF)** là lớp tấn công mà CSRF token được thiết kế để giảm thiểu.

Bài học tập trung vào cách **lấy, truyền và kiểm tra CSRF token** khi dùng:

1. Biểu mẫu HTML, với hidden input.
2. HTTP header như `X-CSRF-TOKEN` trong `fetch()`/XMLHttpRequest.
3. Endpoint `GET /csrf` cấp token cho SPA hoặc client bất đồng bộ.
4. Repository token mặc định `WebSessionServerCsrfTokenRepository` và lựa chọn `CookieServerCsrfTokenRepository`.
5. Mặc định XOR masking/BREACH từ Spring Security 6.0, ảnh hưởng tới token trong cookie, form và header.

Bạn sẽ có ví dụ **Java 17+** dùng Spring Boot WebFlux để quan sát thành công HTTP 200, thất bại CSRF HTTP 403 và các lỗi sau khi phiên hết hạn. CSRF token **không phải** access token hay bằng chứng đã đăng nhập; authorization vẫn phải được kiểm tra riêng.

## 2. Vì sao phải mang token ngoài cookie?

Giả sử user đã đăng nhập vào `https://shop.example`, trình duyệt giữ một cookie phiên. Một website khác tạo form gửi POST tới `https://shop.example/account/change-email`. Tùy SameSite/cookie policy và bối cảnh, browser có thể tự gửi cookie. Nếu server chỉ tin rằng “đã có cookie là chính chủ cố ý gửi POST”, request giả mạo có thể qua.

Theo **synchronizer token pattern**, server lưu một **expected token** tương ứng với phiên; một trang được server hợp lệ render sẽ đưa cho client **submitted token** trong phần mà browser không tự gửi tương tự cookie, ví dụ field ẩn hoặc custom header. Khi client POST, `CsrfWebFilter` kiểm tra submitted token trước khi cho handler xử lý.

~~~text
Browser                         Spring WebFlux
   |                                   |
   | GET /demo                         |
   |---------------------------------->|
   |                                   | CsrfWebFilter + repository
   | HTML có token trong hidden/meta    |
   |<----------------------------------|
   |                                   |
   | POST form /form/save               |
   | Cookie session + field _csrf       |
   |---------------------------------->|
   |                                   | so với expected token
   |           200 / 403               |
   |<----------------------------------|
   |                                   |
   | POST fetch /api/notes             |
   | Cookie session + X-CSRF-TOKEN      |
   |---------------------------------->|
   |                                   | so với expected token
   |         JSON / 403                |
   |<----------------------------------|
~~~

Không thể chỉ **lưu token trong một cookie rồi tin chính cookie đó**. Trong mô hình double-submit/cookie repository, client cần **đọc** hoặc nhận token bằng kênh phù hợp và **gửi một bản sao trong header/parameter**, đồng thời server phải dùng đúng request handler và token format đã cấu hình.

### 2.1. Những HTTP method nào cần CSRF?

Mặc định Spring Security WebFlux kiểm tra CSRF ở phương thức **không an toàn**. Bảng thường gặp:

| Phương thức | CSRF mặc định | Cách sử dụng đúng |
| --- | --- | --- |
| `GET` | Không | Chỉ đọc; có thể dùng lấy token |
| `HEAD`, `OPTIONS`, `TRACE` | Không | Không làm thay đổi trạng thái |
| `POST` | **Có** | Đăng nhập, đăng xuất, ghi dữ liệu |
| `PUT`, `PATCH` | **Có** | Sửa dữ liệu |
| `DELETE` | **Có** | Xóa dữ liệu |

Đừng dùng GET để thực hiện xóa record, chuyển tiền hoặc logout thực sự. Nếu GET có side effect, attacker có thể lợi dụng URL vì default CSRF matcher không chặn safe methods. **Sửa lại HTTP semantics** thay vì đòi CsrfWebFilter tự đoán hành động nghiệp vụ.

### 2.2. CSRF khác 401/403 do authentication/authorization

| Request | Kết quả thường gặp | Cơ chế |
| --- | --- | --- |
| POST có cookie login nhưng **không có token** | **403 Forbidden** | `CsrfWebFilter` |
| POST token đúng nhưng user chưa đăng nhập, URL protected | Redirect login hoặc 401 | Authentication/authorization |
| POST token và user đúng nhưng thiếu role | **403** | Authorization |
| GET private không credentials | Redirect login hoặc 401 | Entry point |
| POST token, user và role đều hợp lệ | Controller xử lý | Business logic |

Một request có CSRF token hợp lệ **vẫn có thể bị từ chối vì không đủ quyền**. Một response 403 **không tự chứng minh CSRF thiếu**. Hãy tách log/test theo lỗi CSRF và lỗi role.

## 3. Các API WebFlux cần nhớ

| API | Chức năng |
| --- | --- |
| `CsrfWebFilter` | Filter reactive kiểm tra CSRF |
| `CsrfToken` | `getToken()`, `getHeaderName()`, `getParameterName()` |
| `ServerCsrfTokenRepository` | Sinh, lưu, tải expected token |
| `WebSessionServerCsrfTokenRepository` | Kho **mặc định**, lưu token ở WebSession |
| `CookieServerCsrfTokenRepository` | Kho token trong cookie; convention XSRF |
| `ServerCsrfTokenRequestHandler` | Expose/resolve submitted token |
| `XorServerCsrfTokenRequestAttributeHandler` | Mask token chống BREACH, mặc định từ 6.0 |
| `ServerCsrfTokenRequestAttributeHandler` | Request handler không XOR |
| `ServerWebExchange` | Thuộc tính request, cookie, header, response |
| `Mono<CsrfToken>` | Publisher lấy/expose CSRF token ở reactive chain |
| `ServerHttpSecurity.csrf(...)` | Cấu hình CSRF trên SecurityWebFilterChain |

Theo tài liệu chính thức, Spring Security 7.1 mặc định lưu expected CSRF token trong **WebSession** và `CsrfWebFilter` expose một `Mono<CsrfToken>` thông qua exchange attribute có key bằng tên class `CsrfToken.class.getName()`. Từ **Spring Security 6.0**, request handler mặc định là `XorServerCsrfTokenRequestAttributeHandler` để hạn chế nguy cơ nén phản hồi BREACH. Ở **5.8**, handler mặc định trước đây là `ServerCsrfTokenRequestAttributeHandler`.

### 3.1. Lấy token không block event loop

Trong một controller reactive nhận `ServerWebExchange exchange`:

~~~java
Mono<CsrfToken> csrfToken =
        exchange.getAttribute(CsrfToken.class.getName());

if (csrfToken == null) {
    return Mono.error(new IllegalStateException(
            "CSRF request attribute unavailable"));
}
return csrfToken.map(CsrfToken::getToken);
~~~

Đây là **mã minh họa đặt trong method có return `Mono<String>`**, chưa phải Java class độc lập. Không gọi `csrfToken.block()` hay `subscribe()` thủ công trong controller. Spring WebFlux sẽ subscribe khi bạn **return** publisher; khi cần token mới, repository có thể tạo/lưu token thông qua subscriber đó.

Phải phân biệt:

- `CsrfToken.class.getName()`: **exchange attribute key**, tên đầy đủ class reactive.
- `token.getParameterName()`: tên field HTML (thường `_csrf`).
- `token.getHeaderName()`: tên request header (thường `X-CSRF-TOKEN` với WebSession repo).
- `token.getToken()`: giá trị submitted token được handler expose, **không tự suy rằng nó giống raw cookie**.

### 3.2. Lazy token không phải lỗi

CSRF token được cung cấp qua `Mono<CsrfToken>` để chỉ tải/tạo khi thật sự cần. Một request GET không render form có thể không cần đụng tới repository. Nếu tạo publisher nhưng không return/subscription, endpoint có thể không thực sự phát token mới hoặc lưu expected token. Ngược lại, nếu ép subscribe token ở **mọi request** qua advice toàn cục, có thể làm tăng session churn.

## 4. Biểu mẫu HTML: gửi token bằng hidden input

Với form-urlencoded POST, biểu mẫu cuối cùng được gửi tới browser cần giống:

~~~html
<form method="post" action="/form/save">
  <label>
    Nội dung
    <input name="message" value="from-form">
  </label>
  <input type="hidden" name="_csrf" value="SERVER_RENDERED_TOKEN">
  <button type="submit">Lưu</button>
</form>
~~~

`SERVER_RENDERED_TOKEN` chỉ là minh họa; trong ứng dụng phải dùng giá trị thật từ `CsrfToken.getToken()` của chính request/phiên hiện tại. Nếu token parameter name được custom, dùng `getParameterName()` thay vì hard-code `_csrf`.

Trong Spring Security 6+/7+ với XOR mặc định, token trong form **có thể là giá trị masked**, khác raw expected token được lưu ở WebSession; đây là hành vi chủ động. Filter sẽ resolve/unmask nó trước khi so khớp.

### 4.1. Form do Thymeleaf render

Spring Security tích hợp với `RequestDataValueProcessor` để Thymeleaf có thể tự chèn hidden CSRF input khi render form POST, nếu token/model attribute được expose đúng cách:

~~~html
<form th:action="@{/form/save}" method="post">
  <input name="message" value="from-thymeleaf">
  <button type="submit">Lưu</button>
</form>
~~~

Đây là **fragment Thymeleaf**, yêu cầu Spring Boot Thymeleaf starter và view engine. Không nên suy rằng bất kỳ HTML từ `@RestController` hoặc template engine khác đều tự chèn input. Nếu view engine không tự xử lý `Mono<CsrfToken>`, tài liệu reactive hướng dẫn `@ControllerAdvice` để expose `CsrfToken` như model attribute cho view.

### 4.2. Form do JavaScript tạo

Có thể dùng DOM API thay vì nối string HTML:

~~~javascript
const form = document.querySelector("#edit-form");
const csrf = document.querySelector('meta[name="_csrf"]').content;
const hidden = document.createElement("input");
hidden.type = "hidden";
hidden.name = "_csrf";
hidden.value = csrf;
form.appendChild(hidden);
~~~

Snippet giả định HTML đã có `form#edit-form` và meta `_csrf` từ server. Khi field name không mặc định, truyền thêm `parameterName` từ server và dùng tên đó. Không đặt token trong query parameter hoặc đường dẫn URL.

## 5. HTTP header: gửi token khi submit JSON hoặc AJAX

Với `Content-Type: application/json`, mặc định Spring Security **không parse field `_csrf` trong JSON business body để kiểm tra CSRF** như một form parameter. Hãy truyền submitted token qua header được `getHeaderName()` cung cấp.

Server có thể render meta tags:

~~~html
<meta name="_csrf" content="SERVER_RENDERED_TOKEN">
<meta name="_csrf_header" content="X-CSRF-TOKEN">
~~~

JavaScript lấy meta và thêm header cho `fetch()`:

~~~javascript
const token = document.querySelector('meta[name="_csrf"]').content;
const header = document.querySelector('meta[name="_csrf_header"]').content;

async function createNote(message) {
  const response = await fetch("/api/notes", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      [header]: token
    },
    body: JSON.stringify({message})
  });
  if (!response.ok) {
    throw new Error("HTTP " + response.status);
  }
  return response.json();
}
~~~

**`credentials: "same-origin"` gửi cookie phiên cho request cùng origin**, nhưng **không tự chèn CSRF header**: dòng `[header]: token` mới làm việc đó. CSRF token không nằm trong `Authorization` thay cho JWT, không phải key để cấp quyền.

Một request khác từ tab/page cùng origin có thể dùng cùng submitted token nếu expected token trong WebSession chưa bị reset. XOR masking **không có nghĩa token phải dùng một lần cho từng POST**; nó mask giá trị được render để bảo vệ against BREACH, còn validation vẫn dựa vào expected token.

### 5.1. XMLHttpRequest

Với API cổ điển:

~~~javascript
const xhr = new XMLHttpRequest();
xhr.open("POST", "/api/notes");
xhr.setRequestHeader("Content-Type", "application/json");
xhr.setRequestHeader(header, token);
xhr.onload = () => console.log("status", xhr.status);
xhr.send(JSON.stringify({message: "xhr"}));
~~~

Đoạn này dùng các biến `header` và `token` đã được lấy từ trang. Với cross-origin, `withCredentials` và CORS policy cần được thiết kế riêng; không giả định custom header tự được phép qua CORS.

### 5.2. Dùng Angular, Axios, jQuery

Một số thư viện hỗ trợ quy ước **cookie `XSRF-TOKEN` → header `X-XSRF-TOKEN`**, nhưng server phải có repository và request handler tương thích **raw vs masked**. Không tuyên bố cứ bật một flag ở frontend là đủ; cần xem nơi token được lưu, cách mask khi expose và cách resolve khi submit.

Với các ứng dụng dùng WebSession repository mặc định, **render masked token vào meta hoặc trả từ GET /csrf** thường dễ giữ đúng mặc định hơn là bắt frontend đọc raw cookie.

## 6. Cấp token qua endpoint GET /csrf cho client bất đồng bộ

Nếu frontend là SPA, có thể lấy token bằng một endpoint GET trả JSON:

~~~json
{
  "headerName": "X-CSRF-TOKEN",
  "parameterName": "_csrf",
  "token": "TOKEN_FROM_SERVER"
}
~~~

**`TOKEN_FROM_SERVER` là ký hiệu minh họa.** Giá trị thật phải do server phát và liên kết với session/request thích hợp. Response nên có `Cache-Control: no-store`, không cho website ngoài origin đọc nó qua CORS quá rộng.

Workflow:

~~~text
Client đã đăng nhập:
GET /csrf + cookie session
  -> nhận token, headerName, parameterName
POST /api/notes + cookie session
  + headerName: token + JSON body
  -> CsrfWebFilter validate
  -> controller chỉ chạy nếu CSRF/auth/role phù hợp

Sau logout / login mới / session timeout:
GET /csrf hoặc reload trang
  -> dùng token mới với session mới
~~~

Một `GET /csrf` thành công **không tự xác thực client**. Nếu endpoint được bảo vệ bằng `authenticated()`, client phải có phiên đăng nhập trước khi lấy token. Nếu endpoint public, bạn cần đánh giá ai được phép đọc response và cách cookie được cấp.

Client bất đồng bộ có thể làm:

~~~javascript
async function loadCsrf() {
  const response = await fetch("/csrf", {
    method: "GET",
    credentials: "same-origin",
    cache: "no-store"
  });
  if (!response.ok) {
    throw new Error("Cannot load CSRF: " + response.status);
  }
  return response.json();
}

async function saveAsync(message) {
  const csrf = await loadCsrf();
  const response = await fetch("/api/notes", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      [csrf.headerName]: csrf.token
    },
    body: JSON.stringify({message})
  });
  if (!response.ok) {
    throw new Error("Cannot save: " + response.status);
  }
  return response.json();
}
~~~

Mã này lấy token mỗi khi POST để minh họa đơn giản. Trong ứng dụng thật có thể cache token **trong memory của page** và refresh khi login/logout hoặc session thay đổi. Không tự retry vô hạn chỉ vì status 403; có thể user thiếu role hoặc policy khác từ chối.

## 7. Repository và sự khác nhau giữa raw token với masked token

### 7.1. Mặc định WebSessionServerCsrfTokenRepository

Spring Security WebFlux mặc định lưu expected CSRF token ở `WebSession`, đồng thời `CsrfWebFilter` đưa `Mono<CsrfToken>` vào request. Với session login cookie, server tìm đúng expected token dựa vào WebSession của request.

Ưu điểm: token expected nằm phía server, không cần JavaScript đọc raw cookie CSRF. Khi token được render vào form/meta, Spring Security xử lý masking và xác minh theo cấu hình.

Hạn chế: khi session hết hạn hoặc bị invalidate, submitted token cũ không còn khớp. Cần lấy lại token đúng phiên trước khi POST mới.

### 7.2. CookieServerCsrfTokenRepository

Một SPA có thể cố tình dùng cookie CSRF tên `XSRF-TOKEN`, gửi bản sao bằng header `X-XSRF-TOKEN`. Đây là convention do `CookieServerCsrfTokenRepository` hỗ trợ:

~~~java
// Snippet trong method cấu hình SecurityWebFilterChain:
.csrf(csrf -> csrf
        .csrfTokenRepository(
                CookieServerCsrfTokenRepository.withHttpOnlyFalse()))
~~~

`withHttpOnlyFalse()` khiến **cookie CSRF** được JavaScript đọc trực tiếp. **Nó không có nghĩa cookie authentication/session mất HttpOnly**. Nếu không cần đọc cookie, có thể dùng constructor thường với HttpOnly hoặc giữ WebSession repository mặc định. Tăng khả năng đọc token từ JS cần đánh giá XSS/CORS/cookie policy.

Tên mặc định:

| Nơi đặt | Giá trị |
| --- | --- |
| Cookie | `XSRF-TOKEN` |
| Request header | `X-XSRF-TOKEN` |
| Form parameter | `_csrf` |

### 7.3. XOR masking: nguyên nhân phổ biến của 403 khi “cookie bằng header”

Từ Spring Security **6.0**, handler mặc định `XorServerCsrfTokenRequestAttributeHandler` mask token khi expose ở request và giải mask token được submit trong header/form. Giá trị cookie `XSRF-TOKEN` thường là **raw expected token**; nếu client đọc raw token từ cookie và sao chép nguyên sang header `X-XSRF-TOKEN`, handler XOR mặc định có thể không giải được, gây **403**.

Trong mẫu chính của bài này, ta **giữ XOR mặc định** và gửi token **từ exchange attribute/page/GET /csrf**, nên không phải đoán raw hay masked.

Nếu bắt buộc giữ mô hình đọc raw cookie, có thể cấu hình handler không XOR:

~~~java
// Phương án tùy chọn, không dùng trong demo chính.
.csrf(csrf -> csrf
        .csrfTokenRepository(
                CookieServerCsrfTokenRepository.withHttpOnlyFalse())
        .csrfTokenRequestHandler(
                new ServerCsrfTokenRequestAttributeHandler()))
~~~

**Đánh đổi bảo mật:** `ServerCsrfTokenRequestAttributeHandler` thay cho XOR **tắt lớp masking chống BREACH**. Không làm vậy theo phản xạ chỉ vì 403; hãy đánh giá threat model hoặc triển khai custom request handler kết hợp masked render với raw header resolver theo đúng API và test kỹ.

Không trộn `CookieCsrfTokenRepository` (Servlet) với `CookieServerCsrfTokenRepository` (reactive).

### 7.4. Cookie là điều kiện cần nhưng không đủ

Cookie `SESSION` giúp xác định người dùng trong session login. Cookie `XSRF-TOKEN` là một cách lưu CSRF state (nếu chọn cookie repo). Header `X-XSRF-TOKEN` hoặc `X-CSRF-TOKEN` là vị trí **client chủ động trình bày token**. Chỉ có hai cookie mà không gửi parameter/header phù hợp thì request unsafe thường vẫn bị 403.

## 8. Ví dụ hoàn chỉnh: form, fetch và /csrf trên Spring Boot WebFlux

Ta tạo ứng dụng **Spring Boot 4.1.2**, Java **17+**, Spring Reactive Web và Spring Security. Ứng dụng:

- `GET /` công khai.
- `GET /login` được Spring Security cung cấp mặc định.
- `GET /demo` sau login: HTML có hidden form token và meta token cho JS.
- `GET /csrf` sau login: JSON token cho client bất đồng bộ.
- `POST /form/save`: form-urlencoded, CSRF token trong hidden field.
- `POST /api/notes`: JSON, CSRF token trong HTTP header.

Chúng ta **không dùng cookie CSRF repository tùy chọn**, **không tắt XOR**, **không tắt CSRF**. Form login chỉ là cách tạo phiên browser để thực hành, không phải production identity service.

### 8.1. Cấu hình Maven

Tạo project từ [Spring Initializr](https://start.spring.io/) với Java 17+, Maven, group `com.example`, artifact `reactive-csrf-demo`; chọn **Spring Reactive Web** và **Spring Security**. File `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.1.2</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>reactive-csrf-demo</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
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

Để Boot BOM quản lý các phiên bản Spring Security, Framework, Reactor và Netty. Không thêm `spring-boot-starter-web`/Servlet vào project WebFlux.

### 8.2. Java source đầy đủ

Tạo file `src/main/java/com/example/csrfdemo/ReactiveCsrfDemoApplication.java`:

~~~java
package com.example.csrfdemo;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class ReactiveCsrfDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveCsrfDemoApplication.class, args);
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails learner = User.withUsername("learner")
                .password("{noop}learn123")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(learner);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
                .authorizeExchange(routes -> routes
                        .pathMatchers("/").permitAll()
                        .anyExchange().authenticated())
                .formLogin(Customizer.withDefaults())
                .httpBasic(basic -> basic.disable())
                // CSRF WebFlux mặc định vẫn bật.
                .build();
    }

    private static Mono<CsrfToken> requireCsrf(
            ServerWebExchange exchange) {
        Mono<CsrfToken> publisher =
                exchange.getAttribute(CsrfToken.class.getName());
        if (publisher == null) {
            return Mono.error(new IllegalStateException(
                    "CSRF attribute unavailable"));
        }
        return publisher;
    }

    public record NoteRequest(String message) { }

    @RestController
    static class DemoController {

        @GetMapping(value = "/", produces = MediaType.TEXT_HTML_VALUE)
        Mono<String> index() {
            return Mono.just("""
                <!doctype html>
                <html lang="vi">
                <head><meta charset="UTF-8"><title>CSRF demo</title></head>
                <body>
                  <h1>CSRF trong Spring WebFlux</h1>
                  <a href="/demo">Vào trang thử nghiệm</a>
                </body></html>
                """);
        }

        @GetMapping(value = "/demo",
                produces = MediaType.TEXT_HTML_VALUE)
        Mono<String> demo(ServerWebExchange exchange) {
            return requireCsrf(exchange).map(token -> {
                exchange.getResponse().getHeaders()
                        .setCacheControl("no-store");
                return """
                    <!doctype html>
                    <html lang="vi">
                    <head>
                      <meta charset="UTF-8">
                      <title>CSRF form and fetch</title>
                      <meta name="_csrf" content="%s">
                      <meta name="_csrf_header" content="%s">
                    </head>
                    <body>
                      <h1>Form &amp; async JSON</h1>
                      <form method="post" action="/form/save">
                        <input name="message" value="from-form">
                        <input type="hidden" name="%s" value="%s">
                        <button type="submit">Submit form</button>
                      </form>
                      <button id="send" type="button">
                        Submit fetch()
                      </button>
                      <pre id="result"></pre>

                      <script>
                        const token = document.querySelector(
                          'meta[name="_csrf"]').content;
                        const header = document.querySelector(
                          'meta[name="_csrf_header"]').content;
                        document.getElementById('send')
                          .addEventListener('click', async () => {
                            const output = document.getElementById('result');
                            try {
                              const response = await fetch('/api/notes', {
                                method: 'POST',
                                credentials: 'same-origin',
                                headers: {
                                  'Content-Type': 'application/json',
                                  [header]: token
                                },
                                body: JSON.stringify({
                                  message: 'from-fetch'
                                })
                              });
                              output.textContent = response.status + ' ' +
                                  await response.text();
                            } catch (error) {
                              output.textContent = 'Network/CORS error';
                            }
                          });
                      </script>
                    </body></html>
                    """.formatted(token.getToken(),
                            token.getHeaderName(),
                            token.getParameterName(),
                            token.getToken());
            });
        }

        @GetMapping(value = "/csrf",
                produces = MediaType.APPLICATION_JSON_VALUE)
        Mono<Map<String, String>> csrf(ServerWebExchange exchange) {
            exchange.getResponse().getHeaders()
                    .setCacheControl("no-store");
            return requireCsrf(exchange).map(token -> Map.of(
                    "headerName", token.getHeaderName(),
                    "parameterName", token.getParameterName(),
                    "token", token.getToken()));
        }

        @PostMapping(value = "/form/save",
                consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
                produces = MediaType.TEXT_PLAIN_VALUE)
        Mono<String> formSave(ServerWebExchange exchange) {
            return exchange.getFormData()
                    .map(form -> "FORM_OK:" +
                            form.getFirst("message"));
        }

        @PostMapping(value = "/api/notes",
                consumes = MediaType.APPLICATION_JSON_VALUE,
                produces = MediaType.APPLICATION_JSON_VALUE)
        Mono<Map<String, String>> apiNotes(
                @RequestBody NoteRequest input) {
            return Mono.just(Map.of(
                    "status", "API_OK",
                    "message", input.message()));
        }
    }
}
~~~

### 8.3. Giải thích code

- `@EnableWebFluxSecurity` + `SecurityWebFilterChain` dùng API reactive.
- `formLogin(withDefaults())` tạo trang login mặc định và nhận POST login với CSRF hợp lệ; `httpBasic(disable)` giúp trình duyệt không hiện native Basic dialog.
- `/` công khai; `/demo`, `/csrf` và hai POST được bảo vệ bằng `authenticated()`. CSRF là lớp kiểm tra **bổ sung**, không thay authorization.
- `requireCsrf(...)` lấy `Mono<CsrfToken>` từ exchange attribute, **return publisher**, không block.
- `GET /demo` subscribe token trong `map` và render hidden input bằng `getParameterName()/getToken()`, meta bằng `getToken()/getHeaderName()`.
- `POST /form/save` dùng `ServerWebExchange.getFormData()`. Trong WebFlux, `@RequestParam` chủ yếu mô tả query param, không giả định hoàn toàn như Spring MVC form body.
- `POST /api/notes` dùng `@RequestBody NoteRequest` để parse JSON bằng WebFlux codec; không đọc CSRF token từ JSON business body.
- `GET /csrf` expose token dưới dạng JSON phục vụ async client; response có `Cache-Control: no-store`.
- Demo chỉ trả lời bằng text/JSON để quan sát; không lưu database.
- `{noop}`/password trong source chỉ dành cho local. Production phải dùng password encoder mạnh, HTTPS, rate limiting, nguồn danh tính thật và cơ chế session/cookie phù hợp.
- Code dùng Java text blocks, cần Java 17+. Đường dẫn file và public class phải đúng package.

**Lưu ý về masking:** ngay cả khi token trong meta/hidden input khác string expected token trong server repository, vẫn dùng giá trị **được expose** để submit. Không tự cắt, giải mã hoặc thay bằng raw cookie.

### 8.4. Chạy demo

Trong thư mục chứa `pom.xml`:

~~~bash
./mvnw clean package
./mvnw spring-boot:run
~~~

Trên Windows dùng `.\mvnw.cmd clean package` và `.\mvnw.cmd spring-boot:run`; nếu không có Maven wrapper, dùng `mvn` với Maven phù hợp.

Truy cập `http://localhost:8080/`, bấm liên kết `/demo`, bạn sẽ được redirect tới `/login`. Đăng nhập bằng:

~~~text
Username: learner
Password: learn123
~~~

Sau login, mở `http://localhost:8080/demo` nếu chưa được redirect đến đó. Trang hiện hai cách gửi:

1. Bấm **Submit form**: browser POST form-urlencoded có hidden `_csrf`; mong đợi HTTP 200 và body `FORM_OK:from-form`.
2. Bấm **Submit fetch()**: JavaScript gửi JSON và header từ meta; pre sẽ hiện status 200 và một JSON có `"status":"API_OK"`.

Khi vừa login xong, **reload trang demo** để bảo đảm token vừa render thuộc phiên hiện tại. Một token lấy từ session trước login có thể đã được reset.

### 8.5. Thử thiếu token và token sai

Dùng DevTools Network để kiểm tra request `POST /api/notes`, xem **Request Headers** và cookie phiên. Khi xóa code thêm `[header]: token` rồi reload trang trong môi trường thử nghiệm, POST sẽ bị **403** và handler `apiNotes` không chạy. Tương tự nếu thay token bằng chuỗi sai.

Chỉ kiểm tra response HTTP status chưa đủ để kết luận controller đã chạy. Một test tốt cũng theo dõi business effect/log kiểm thử và phân biệt 403 CSRF với 403 thiếu role.

## 9. Thử bằng curl cùng cookie jar

`curl` không tự có browser session. Dùng `-c` và `-b` để giữ đúng cookie khi lấy và submit token. Thao tác token dưới đây yêu cầu bạn tự thay token **được server trả thực tế**, không lấy token minh họa.

### 9.1. Lấy form login và token của request đó

~~~bash
curl -i -c cookies.txt -b cookies.txt \
  http://localhost:8080/login
~~~

Xem HTML `GET /login` để lấy hidden input `_csrf` của form login mặc định. Đừng chỉ sao chép session cookie rồi bỏ token.

### 9.2. Đăng nhập bằng token trong form

~~~bash
curl -i -c cookies.txt -b cookies.txt \
  --data-urlencode "username=learner" \
  --data-urlencode "password=learn123" \
  --data-urlencode "_csrf=LOGIN_FORM_TOKEN" \
  http://localhost:8080/login
~~~

`LOGIN_FORM_TOKEN` phải được thay bằng hidden field lấy từ cùng cookie jar. Nếu login thành công, form-login flow thường trả **302 redirect**; đừng mong POST login trả JSON 200.

### 9.3. Lấy token mới sau khi login

~~~bash
curl -i -c cookies.txt -b cookies.txt \
  http://localhost:8080/csrf
~~~

Response body có các field `headerName`, `parameterName` và `token`. Token có thể đã thay so với trước login. Dùng **token mới** cho các request sau, không chia sẻ ra chat/log công khai.

### 9.4. POST JSON + CSRF header

~~~bash
curl -i -c cookies.txt -b cookies.txt \
  -H "Content-Type: application/json" \
  -H "X-CSRF-TOKEN: TOKEN_FROM_CSRF_RESPONSE" \
  -d '{"message":"from-curl-json"}' \
  http://localhost:8080/api/notes
~~~

Expected HTTP **200** và JSON có `"status":"API_OK"`, `"message":"from-curl-json"`. Thứ tự field trong JSON có thể khác vì `Map.of` không bảo đảm order serializer.

### 9.5. POST form-urlencoded + CSRF parameter

~~~bash
curl -i -c cookies.txt -b cookies.txt \
  --data-urlencode "message=from-curl-form" \
  --data-urlencode "_csrf=TOKEN_FROM_CSRF_RESPONSE" \
  http://localhost:8080/form/save
~~~

Expected HTTP **200** với body `FORM_OK:from-curl-form`. Nó tương đương với hidden input trong form.

### 9.6. POST không có token

~~~bash
curl -i -c cookies.txt -b cookies.txt \
  -H "Content-Type: application/json" \
  -d '{"message":"missing-token"}' \
  http://localhost:8080/api/notes
~~~

Expected HTTP **403 Forbidden** (CSRF failure), dù browser/curl đang có session đăng nhập. Body 403 phụ thuộc handler và version, không ép một chuỗi JSON mặc định.

Trên Windows PowerShell, dùng `curl.exe` nếu `curl` là alias; lệnh dùng dấu `\` nối dòng của Bash, nên trên PowerShell có thể gõ một dòng. File `cookies.txt` chứa cookie phiên, không upload hoặc commit Git.

## 10. Các tình huống bất đồng bộ, timeout và CORS

### 10.1. fetch không throw khi status 403

`fetch()` thường **resolve Promise cả khi HTTP 401/403/500**; `catch` chủ yếu thấy network/CORS failure. Vì vậy luôn kiểm tra `response.ok` hoặc `response.status`:

~~~javascript
const response = await fetch("/api/notes", {
  method: "POST",
  credentials: "same-origin",
  headers: {
    "Content-Type": "application/json",
    [csrfHeader]: csrfToken
  },
  body: JSON.stringify({message: "example"})
});

if (response.status === 401) {
  // Cần login; thực hiện UX đăng nhập.
} else if (response.status === 403) {
  // CSRF hoặc thiếu quyền, không đoán duy nhất một nguyên nhân.
} else if (!response.ok) {
  // Các lỗi ứng dụng khác.
}
~~~

Đây là snippet với `csrfHeader` và `csrfToken` đã được load trước đó, chưa phải chương trình JS độc lập.

### 10.2. Nhiều request đồng thời

Khi nhiều `fetch()` gửi POST song song trên **cùng WebSession**, chúng có thể dùng cùng submitted token. XOR masking không bắt buộc token chỉ dùng một lần. Nhưng nếu user logout hoặc phiên được invalidate giữa các request, một số request có thể bị 403; không nên retry mọi request POST vô hạn vì một tác vụ có side effect có thể đã xảy ra.

Nếu hệ thống cần “một lần gửi duy nhất”, đó là vấn đề **idempotency keys/transaction**, tách khỏi CSRF validation.

### 10.3. Login/logout làm token cũ không còn hợp lệ

Sau login, logout, session timeout, password change hoặc session rotation, expected token có thể bị xóa/đổi. Một SPA nên refetch `/csrf` hoặc reload page trước khi gửi unsafe request mới; không cache token từ trang login trước đó suốt thời gian dài.

**403 không phải lúc nào cũng là token hết hạn**: có thể user chưa có role phù hợp, một CORS/WAF policy khác từ chối, hoặc request handler đang mong masked token. Đừng tự refresh token và retry liên tục.

### 10.4. CORS preflight

Một cross-origin request với custom header `X-CSRF-TOKEN` có thể kích hoạt preflight `OPTIONS`. CSRF matcher mặc định không đòi token cho OPTIONS, nhưng **CORS** vẫn cần cho phép origin, method, header và việc gửi credentials. Không chọn `Access-Control-Allow-Origin: *` cho cookie credentials và không dùng “tắt CSRF” để sửa CORS.

Nếu SPA/backend khác origin và dùng cookie, còn cần thiết kế `SameSite`, `Secure`, CSRF token endpoint, credentialed CORS và trust boundary. CORS **không phải** thay thế CSRF.

### 10.5. Multipart upload

Nếu đặt token ở multipart form body, server có thể cần parse body trước khi quyết định CSRF, gây rủi ro tạo file tạm/tiêu thụ tài nguyên. Với uploader JavaScript, **ưu tiên gửi token bằng HTTP header** để check trước xử lý body sâu. Không đặt token trong query string để né multipart parser.

### 10.6. Server-to-server WebClient

`WebClient` gọi API bằng Bearer token từ server (không tự dùng cookie browser) thường có CSRF threat model khác. Nếu WebClient thật sự giữ **cookie session** và gọi một server yêu cầu CSRF, client vẫn phải nhận token và gửi đúng header/form. Không gửi token bừa vào API stateless chỉ vì “mọi POST đều cần”.

### 10.7. WebSocket/SSE

SSE GET thường chỉ đọc; WebSocket có vấn đề origin/cross-site handshake riêng. Không cho rằng `CsrfWebFilter` bảo vệ toàn bộ WebSocket messages vì nó bảo vệ POST. Nếu có kết nối nâng cấp hoặc SockJS, đọc đúng tài liệu cơ chế đó để kiểm tra origin và authenticated session.

## 11. Khắc phục lỗi thường gặp

| Dấu hiệu | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| POST form 403 | Thiếu hidden input, sai token hoặc session cookie | Xem DOM form, Request Payload, Cookies |
| POST fetch 403 nhưng form thành công | Quên header CSRF hoặc sai header name | DevTools Request Headers |
| GET /csrf không có token | Không subscribe `Mono<CsrfToken>` hoặc route bị chặn | Return publisher và kiểm tra authentication |
| Raw XSRF cookie gửi nguyên header vẫn 403 | XOR handler mong masked submitted token | Xem repo + `ServerCsrfTokenRequestHandler` |
| POST sau login bị 403 | Token cũ hoặc session được đổi | GET /csrf mới |
| POST sau timeout bị 403 | Token thuộc session đã hết hạn | Login lại và lấy token mới |
| Token browser A + cookie browser B bị 403 | Expected token theo session khác | Không dùng token khác session |
| POST thiếu token nhưng controller không log | Filter từ chối trước controller | Đúng hành vi; xem security debug logs |
| Preflight OPTIONS không qua | CORS chưa cho phép header/origin | Xem Access-Control-Allow-* |
| fetch không chạy catch dù 403 | HTTP response không reject Promise | Kiểm tra response.ok/status |
| AJAX trả HTML login thay JSON | Form-login redirect, session hết hạn | Kiểm tra 302/Location; tách browser/API |
| Dev/prod khác nhau | Cookie path/domain/SameSite, proxy, cluster | Kiểm tra response Set-Cookie và session store |
| GET thay đổi dữ liệu mà không bị CSRF check | GET safe mặc định | Sửa endpoint theo HTTP semantics |

### 11.1. Ghi log đúng mà không lộ bí mật

Có thể bật trong dev:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Log ứng dụng nên ghi request ID, route template, method, status và mã lý do `csrf_missing`/`csrf_invalid`, nhưng **không** ghi raw `_csrf`, `X-CSRF-TOKEN`, access token, password hoặc cookie session. Không đưa token vào URL, Referer hay query parameter nếu có lựa chọn form/header.

### 11.2. Không chữa lỗi 403 bằng csrf.disable()

Nếu một POST bị 403, hãy kiểm tra:

1. Request method có nằm trong CSRF matcher không?
2. Repository nào đang lưu expected token?
3. Token đã được expose/subscribe chưa?
4. Header/parameter name nào server đòi?
5. Giá trị client gửi là **masked** hay **raw**?
6. Cookie có thuộc cùng browser session không?
7. Login/logout có reset token hoặc session không?
8. Có security chain khác match URL không?
9. 403 thực sự từ CSRF hay từ authorization?
10. Cross-origin request có bị CORS preflight từ chối không?

Chỉ xem xét disable CSRF cho chain stateless Bearer **sau khi** chứng minh không dùng browser-automatically-sent credentials và có threat model phù hợp.

## 12. Kiểm thử tự động

Với WebFlux dùng `WebTestClient` và Spring Security test support để assert request POST không có CSRF sẽ thất bại và request POST với token phù hợp có thể tới controller.

Một test snippet:

~~~java
// Đoạn minh họa trong integration test đã có WebTestClient.
webTestClient.mutateWith(mockUser("learner"))
        .mutateWith(csrf())
        .post()
        .uri("/api/notes")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new ReactiveCsrfDemoApplication.NoteRequest("test"))
        .exchange()
        .expectStatus().isOk();
~~~

Đây không phải class test đầy đủ; cần `Spring Security test`, `WebTestClient`, `SecurityMockServerConfigurers.mockUser`/`csrf`, test runner tương thích, và bean app được load. Sau đó thử tương tự **không có `csrf()`** để mong đợi 403. Mock user không tự chứng minh browser thật dùng đúng cookie jar; kết hợp test E2E với hai browser profile.

### 12.1. Test matrix

| Test | Đầu vào | Mong đợi |
| --- | --- | --- |
| Public GET | `GET /` anonymous | 200 |
| Protected GET | `GET /demo` anonymous | Redirect login |
| Login đúng CSRF | POST login + cookie + hidden token | Thành công/redirect |
| Login thiếu CSRF | POST login không token | 403 |
| Form POST đúng | Cookie + `_csrf` hidden | 200, `FORM_OK:from-form` |
| Form POST sai | Token sai/thiếu | 403 |
| Fetch POST đúng | Cookie + `X-CSRF-TOKEN` | 200, JSON `API_OK` |
| Fetch POST thiếu header | Cookie có nhưng header không có | 403 |
| JSON body có key _csrf nhưng không header | POST JSON | Thường 403 |
| GET /csrf | Session hợp lệ | JSON token/headerName/parameterName |
| Token trước login sau login | Stale token | Có thể 403, cần refresh |
| Token của session A + cookie B | Khác session | 403 |
| Cookie repo raw + XOR mặc định | Raw header | Có thể 403, kiểm tra handler |
| CORS preflight | OPTIONS có custom header | CORS cho phép đúng chính sách |
| CSRF pass nhưng role thiếu | Logged in thiếu authority | 403 authorization |
| API stateless Bearer | JWT Authorization, không cookie | Threat model riêng |

**Khi kiểm thử response JSON**, so field thay vì byte order. Với `Map.of`, serializer có thể đổi thứ tự các key trong output.

## 13. Checklist production

1. Giữ CSRF cho các request cookie/form/session hoặc browser cached credentials.
2. Không dùng GET/HEAD làm thao tác gây thay đổi trạng thái.
3. Lấy token từ chính session đang authenticated, không dùng token của người khác/phiên khác.
4. Form dùng hidden `token.getParameterName()` và `token.getToken()`.
5. JSON/AJAX dùng header `token.getHeaderName()` và giá trị token được server expose.
6. Không chặn Reactor event loop bằng `block()` khi lấy token.
7. Phân biệt repository token lưu **ở đâu** với request handler cần token **dạng gì** (raw/masked).
8. Cookie `XSRF-TOKEN` chỉ mở HttpOnly khi JS thực sự phải đọc; giữ policy cookie auth riêng.
9. Sau login/logout/session reset, load token mới.
10. Đặt `Cache-Control: no-store` cho endpoint/page expose token khi phù hợp.
11. Không log CSRF token hoặc gửi trong URL/query string.
12. CORS, SameSite, Secure, HttpOnly và session store được thiết kế đúng topology.
13. Không coi CSRF token là chứng cứ authentication/authorization.
14. Có test cả browser HTML, fetch async, curl với cookie jar, session expiry và multipart.
15. Nếu nhiều instance, session storage dùng chung hoặc strategy phù hợp để expected token nhất quán.
16. Không tắt CSRF toàn hệ thống để sửa một lỗi 403.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao chỉ gửi cookie session không đủ để một POST được chấp nhận?

**Đáp án:** Browser có thể tự gắn cookie vào request giả mạo. Token cần được gửi chủ động trong form field/header do website hợp lệ cung cấp.

**Câu 2.** Vì sao `fetch()` gửi JSON có field `_csrf` trong business body vẫn có thể 403?

**Đáp án:** Reactive CSRF resolver mặc định đọc token ở form parameter hoặc HTTP header, không tùy ý parse key trong JSON body. Gửi đúng header.

**Câu 3.** `Mono<CsrfToken>` nằm ở đâu?

**Đáp án:** `ServerWebExchange` attribute theo `CsrfToken.class.getName()`. Controller compose/return publisher, không gọi `block()`.

**Câu 4.** Spring Security 7.1 mặc định lưu expected token ở đâu?

**Đáp án:** `WebSessionServerCsrfTokenRepository`, trong WebSession.

**Câu 5.** Vì sao token đọc từ cookie XSRF-TOKEN có thể không dùng trực tiếp làm header trên Spring Security 7?

**Đáp án:** Cookie có token raw nhưng request handler mặc định XOR có thể mong masked submitted token. Cần cấu hình repository và handler tương thích.

**Câu 6.** `CookieServerCsrfTokenRepository.withHttpOnlyFalse()` có tự làm session cookie mất HttpOnly không?

**Đáp án:** Không. Nó cấu hình cookie CSRF để JavaScript có thể đọc, không tự thay thuộc tính của cookie authentication/session.

**Câu 7.** Tại sao nên refresh token sau login/logout?

**Đáp án:** Session/expected token có thể thay đổi hoặc bị xóa; token cũ có thể không khớp ở POST tiếp theo.

**Câu 8.** `fetch()` có tự throw khi HTTP status 403?

**Đáp án:** Không. Kiểm tra `response.ok`/`response.status`; promise reject thường do network/CORS error.

**Câu 9.** Với file upload multipart có JavaScript, gửi token ở đâu để tránh parse body trước CSRF?

**Đáp án:** Ưu tiên HTTP header.

**Câu 10.** Bearer-only stateless API có phải luôn tắt CSRF?

**Đáp án:** Không có quy tắc “luôn”. Chỉ cân nhắc sau khi kiểm tra rằng browser không tự gửi credential và không tồn tại cookie-based path cần bảo vệ.

## 15. Tài liệu chính thức

- [Spring Security 7.1 — CSRF for WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html)
- [Spring Security — CsrfWebFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/CsrfWebFilter.html)
- [Spring Security — CsrfToken API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/CsrfToken.html)
- [Spring Security — WebSessionServerCsrfTokenRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/WebSessionServerCsrfTokenRepository.html)
- [Spring Security — CookieServerCsrfTokenRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/CookieServerCsrfTokenRepository.html)
- [Spring Security — XorServerCsrfTokenRequestAttributeHandler API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/XorServerCsrfTokenRequestAttributeHandler.html)
- [Spring Security — ServerCsrfTokenRequestAttributeHandler API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/ServerCsrfTokenRequestAttributeHandler.html)
- [Spring Security — WebFlux Configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — Reactive Login](https://docs.spring.io/spring-security/reference/reactive/authentication/passwords/form.html)
- [Spring Security — CSRF Concepts](https://docs.spring.io/spring-security/reference/features/exploits/csrf.html)
- [Spring Boot 4.1.2 release](https://spring.io/blog/2026/10/23/spring-boot-4-1-2-available-now/)
