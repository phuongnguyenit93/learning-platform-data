# Lấy token qua request thật để kiểm tra vòng đời phát và gửi lại

Các helper `csrf()` và `csrf().useInvalidToken()` rất hữu ích khi kiểm tra riêng bộ lọc CSRF trong MockMvc. Nhưng chúng tạo token ngay trong test, nên không chứng minh ứng dụng có phát token đúng cách, browser có giữ cookie/session, hay client có gửi lại token đã nhận từ server hay không.

Để kiểm tra **vòng đời token thực tế**, cần thực hiện ít nhất hai request có liên hệ với nhau: request đầu lấy token và cookie/session; request sau gửi lại đúng token trong cùng ngữ cảnh. Bài học này hướng dẫn cách làm với session repository và cookie repository, dùng HTTP client có cookie jar, kiểm thử cả nhánh hợp lệ lẫn thiếu/sai token, và xác minh token cũ sau login/logout hoặc khi đổi phiên.

## 1. Vòng đời CSRF cần kiểm chứng

Một luồng CSRF thực tế thường có các bước:

1. Client truy cập trang hoặc endpoint bootstrap để server tạo/tải CSRF token.
2. Server trả token trong HTML, JSON hoặc cookie; đồng thời có thể phát cookie session.
3. Client lưu cookie và token theo đúng phạm vi phiên/origin.
4. Client gửi request thay đổi trạng thái cùng cookie/session và token qua form parameter hoặc header.
5. Server tải token dự kiến từ repository, giải quyết giá trị request theo request handler rồi so sánh.
6. Test xác minh request hợp lệ được xử lý, request thiếu/sai token bị từ chối và không tạo tác dụng phụ.

Điểm quan trọng là **request lấy token và request gửi lại token phải dùng cùng cookie jar/session**. Nếu lấy token ở session A rồi gửi cùng cookie của session B, test không còn kiểm tra luồng hợp lệ.

| Phần cần kiểm tra | Câu hỏi |
| --- | --- |
| Token bootstrap | Server có thực sự tạo và trả token không? |
| Repository | Token được lưu trong session hay cookie? |
| Cookie | Browser/client có nhận và gửi lại đúng cookie không? |
| Request handler | Token gửi bằng parameter/header có đúng định dạng được chấp nhận không? |
| Session lifecycle | Token còn hợp lệ sau login, logout, session rotation hoặc hết hạn không? |
| Kết quả nghiệp vụ | Request bị từ chối có tránh được tác dụng phụ không? |

## 2. Tạo endpoint bootstrap cho session repository

Với `HttpSessionCsrfTokenRepository`, token được lưu trong HTTP session. Một endpoint bootstrap có thể trả token cho client dưới dạng JSON:

~~~java
@RestController
class CsrfBootstrapController {

    @GetMapping("/csrf")
    ResponseEntity<CsrfToken> csrf(CsrfToken csrfToken) {
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(csrfToken);
    }
}
~~~

Endpoint này trả về các thuộc tính của `CsrfToken` như `token`, `parameterName` và `headerName`. Khi response được serialize và thuộc tính token được truy cập, deferred token có thể được materialize và lưu trong session. Client cần giữ cookie session do response phát ra.

Một số lưu ý khi cung cấp token:

- Chỉ tạo endpoint bootstrap nếu kiến trúc client cần endpoint riêng; form server-rendered có thể render token trực tiếp.
- Không cache response token: dùng `Cache-Control: no-store` để tránh proxy/browser cache nhầm token giữa các phiên.
- Giữ endpoint cùng origin với ứng dụng nếu có thể; nếu khác origin, cấu hình CORS và credential một cách tường minh.
- CSRF token không phải access token hay mật khẩu, nhưng vẫn nên tránh ghi token vào log, analytics hoặc cache dùng chung.
- Endpoint bootstrap không tự xác thực người dùng. Nếu trang cần đăng nhập, client vẫn phải thực hiện login theo cơ chế ứng dụng.

Ví dụ HTML form có thể render token:

~~~html
<form method="post" action="/profile">
  <input type="text" name="displayName" value="Lan">
  <input type="hidden" name="_csrf" value="token-do-server-render">
  <button type="submit">Lưu</button>
</form>
~~~

Với template engine tích hợp Spring Security, token có thể được thêm tự động khi dùng form action phù hợp. Hãy kiểm tra HTML đã render để tránh thêm hai hidden field CSRF.

## 3. Client browser lấy token rồi gửi lại

Với client JavaScript cùng origin, browser tự quản lý cookie theo chính sách cookie của response. Một luồng bootstrap JSON có thể như sau:

~~~javascript
async function loadCsrfToken() {
  const response = await fetch('/csrf', {
    method: 'GET',
    credentials: 'same-origin',
    cache: 'no-store'
  });
  if (!response.ok) {
    throw new Error('Không lấy được CSRF token: ' + response.status);
  }
  return await response.json();
}

async function updateProfile() {
  const csrf = await loadCsrfToken();
  const headers = {
    'Content-Type': 'application/json',
    [csrf.headerName]: csrf.token
  };

  const response = await fetch('/profile', {
    method: 'POST',
    credentials: 'same-origin',
    headers: headers,
    body: JSON.stringify({ displayName: 'Lan' })
  });

  if (!response.ok) {
    throw new Error('Không cập nhật được hồ sơ: ' + response.status);
  }
}
~~~

Đoạn mã giả định endpoint trả JSON có các thuộc tính `headerName` và `token`, ứng dụng cùng origin dùng cookie session và request handler chấp nhận token được render. Browser giữ session cookie từ lần GET và gửi lại ở POST nhờ `credentials: 'same-origin'`.

Nếu ứng dụng dùng form HTML, browser gửi hidden parameter cùng cookie session khi submit. Nếu dùng SPA với `CookieCsrfTokenRepository`, client thường đọc cookie CSRF rồi gửi giá trị trong header; cần tuân theo request handler được cấu hình, đặc biệt khi có XOR/BREACH protection.

## 4. Kiểm thử HTTP thật với RestAssured và cookie jar

MockMvc chạy qua servlet filter nhưng không kiểm tra đầy đủ hành vi cookie của browser/container như domain, Path, SameSite, Secure, CORS hoặc TLS. Để kiểm tra request HTTP tới server đang chạy, có thể dùng Spring Boot random port cùng RestAssured.

Dependency test thường dùng:

~~~groovy
testImplementation 'io.rest-assured:rest-assured'
testImplementation 'org.springframework.boot:spring-boot-starter-test'
~~~

Ví dụ sau giả định:

- Ứng dụng Servlet chạy với `HttpSessionCsrfTokenRepository`.
- `GET /csrf` trả JSON chứa `token` và `parameterName`.
- `POST /profile` yêu cầu đăng nhập bằng HTTP Basic, CSRF và trả `204` khi cập nhật thành công.
- Test environment có user `lan` với mật khẩu test và quyền phù hợp.

~~~java
import io.restassured.filter.cookie.CookieFilter;
import io.restassured.response.Response;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static io.restassured.RestAssured.given;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class CsrfRealHttpLifecycleTest {

    @LocalServerPort
    int port;

    @Test
    void obtainsTokenAndReusesItWithSameSession() {
        CookieFilter cookieJar = new CookieFilter();

        Response bootstrap = given()
            .baseUri("http://localhost")
            .port(port)
            .filter(cookieJar)
            .auth().preemptive().basic("lan", "test-password")
            .get("/csrf");

        bootstrap.then().statusCode(200);
        String token = bootstrap.jsonPath().getString("token");
        String parameterName =
            bootstrap.jsonPath().getString("parameterName");

        // Cùng cookie jar: giữ session cookie nhận được từ GET /csrf.
        given()
            .baseUri("http://localhost")
            .port(port)
            .filter(cookieJar)
            .auth().preemptive().basic("lan", "test-password")
            .contentType("application/x-www-form-urlencoded")
            .formParam("displayName", "Lan")
            .formParam(parameterName, token)
            .post("/profile")
            .then()
            .statusCode(204);
    }
}
~~~

`CookieFilter` hoạt động như cookie jar: nó thu cookie từ response bootstrap và gửi lại ở request tiếp theo. Với session repository, cookie jar giữ session ID để server tải đúng token đã lưu. HTTP Basic được gửi ở cả hai request vì Basic authentication không tự duy trì trạng thái đăng nhập trong session.

Trong dự án thực, không hard-code mật khẩu người dùng thật vào test. Tạo user test riêng, lấy thông tin từ cấu hình test an toàn hoặc dùng cơ chế đăng nhập của ứng dụng. Nếu dùng form login, chính request POST login cũng có thể cần CSRF token; hãy bootstrap token trước login và lấy token mới sau khi login nếu authentication strategy đã xóa token cũ.

## 5. Thử token thiếu, sai và hợp lệ trong cùng cookie jar

Sau khi nhận token từ `GET /csrf`, có thể kiểm tra ba nhánh trên cùng phiên:

Đoạn dưới đây là phần tiếp nối bên trong cùng test method `obtainsTokenAndReusesItWithSameSession()` ở mục trước; các biến `port`, `cookieJar`, `parameterName` và `token` đã được tạo từ bootstrap response.

~~~java
// Không gửi token: bị từ chối.
given()
    .baseUri("http://localhost")
    .port(port)
    .filter(cookieJar)
    .auth().preemptive().basic("lan", "test-password")
    .contentType("application/x-www-form-urlencoded")
    .formParam("displayName", "Lan")
    .post("/profile")
    .then()
    .statusCode(403);

// Có parameter nhưng token sai: bị từ chối.
given()
    .baseUri("http://localhost")
    .port(port)
    .filter(cookieJar)
    .auth().preemptive().basic("lan", "test-password")
    .contentType("application/x-www-form-urlencoded")
    .formParam("displayName", "Lan")
    .formParam(parameterName, "not-the-issued-token")
    .post("/profile")
    .then()
    .statusCode(403);

// Token vừa lấy từ server: được chấp nhận.
given()
    .baseUri("http://localhost")
    .port(port)
    .filter(cookieJar)
    .auth().preemptive().basic("lan", "test-password")
    .contentType("application/x-www-form-urlencoded")
    .formParam("displayName", "Lan")
    .formParam(parameterName, token)
    .post("/profile")
    .then()
    .statusCode(204);
~~~

Ba request dùng cùng URL, method, user, body và cookie jar; chỉ khác token. Status `403` là kỳ vọng của cấu hình ví dụ, nhưng ứng dụng có thể tùy chỉnh `AccessDeniedHandler`. Nên kiểm tra thêm dữ liệu profile không đổi sau hai request bị từ chối và chỉ thay đổi sau request hợp lệ.

Nếu endpoint trả `302`, `401` hoặc `400`, đừng lập tức đổi kỳ vọng thành công. Kiểm tra cookie jar có giữ session không, authentication có hợp lệ không, tên parameter có đúng không, token có bị serialize/mask theo handler không và body có hợp lệ không.

## 6. Cookie repository: nhận cookie CSRF rồi gửi header

Với SPA, ứng dụng có thể dùng `CookieCsrfTokenRepository`. Một endpoint bootstrap có thể chỉ cần buộc token được tạo để repository phát cookie:

~~~java
@RestController
class CsrfCookieBootstrapController {

    @GetMapping("/csrf")
    ResponseEntity<Void> csrf(CsrfToken csrfToken) {
        csrfToken.getToken(); // Materialize deferred token và phát cookie.
        return ResponseEntity.noContent()
            .cacheControl(CacheControl.noStore())
            .build();
    }
}
~~~

Đoạn này giả định repository là cookie-based. Browser nhận `Set-Cookie: XSRF-TOKEN=...`; JavaScript đọc cookie (nếu `HttpOnly=false`) và gửi giá trị vào header theo tên cấu hình, thường là `X-XSRF-TOKEN`.

Ví dụ test HTTP với RestAssured:

~~~java
@Test
void cookieTokenIsReusedInHeader() {
    CookieFilter cookieJar = new CookieFilter();

    Response bootstrap = given()
        .baseUri("http://localhost")
        .port(port)
        .filter(cookieJar)
        .auth().preemptive().basic("lan", "test-password")
        .get("/csrf");

    bootstrap.then().statusCode(204);
    String csrfCookie = bootstrap.getCookie("XSRF-TOKEN");
    assertNotNull(csrfCookie);

    given()
        .baseUri("http://localhost")
        .port(port)
        .filter(cookieJar)
        .auth().preemptive().basic("lan", "test-password")
        .header("X-XSRF-TOKEN", csrfCookie)
        .contentType("application/json")
        .body("{\"displayName\":\"Lan\"}")
        .post("/profile")
        .then()
        .statusCode(204);
}
~~~

Ví dụ này giả định ứng dụng đã cấu hình SPA request handler để chấp nhận raw token từ cookie trong header. Với handler XOR mặc định, giá trị cookie raw có thể không giống giá trị masked được render vào request attribute; không nên mặc định copy cookie vào header là luôn hợp lệ. Hãy dùng đúng handler và phiên bản Spring Security của ứng dụng.

Thêm các ca âm tính:

| Cookie CSRF | Header | Kỳ vọng |
| --- | --- | --- |
| Có | Thiếu | Bị từ chối nếu handler yêu cầu header/parameter. |
| Có | Sai | Bị từ chối. |
| Thiếu | Có token | Bị từ chối nếu repository không có token dự kiến để so khớp. |
| Có | Khớp token theo handler | Qua CSRF và tiếp tục xử lý. |

Khi test bằng cookie jar, xác nhận cookie có đúng Path/Domain và được gửi lại. Nếu cookie có cờ Secure, client phải dùng HTTPS để gửi; một test HTTP localhost có thể không tái hiện chính sách cookie của môi trường production.

## 7. Kiểm tra session khác nhau và token cũ

Token cần gắn với đúng ngữ cảnh repository. Với session repository, test nên tạo hai cookie jar riêng:

1. Jar A gọi bootstrap, nhận session A và token A.
2. Jar B gọi bootstrap, nhận session B và token B.
3. Jar B gửi token A: kỳ vọng bị từ chối.
4. Jar B gửi token B: kỳ vọng được chấp nhận.

Với cookie repository, thực hiện tương tự bằng hai cookie jar riêng và kiểm tra header/cookie của từng jar. Không dùng cookie từ jar A với token của jar B.

### Sau login

Spring Security có thể đổi session ID để chống session fixation và xóa CSRF token cũ khi authentication thành công. Vì vậy:

- Nếu bootstrap token trước login, đừng giả định token đó vẫn dùng được sau login.
- Giữ cookie jar qua response login để nhận session cookie mới.
- Gọi lại endpoint bootstrap sau login để lấy token mới.
- Gửi token mới với session hiện tại.

Nếu form login yêu cầu CSRF, request login ban đầu cũng cần token hợp lệ. Luồng test có thể là GET form/bootstrap, POST login với token và cookie ban đầu, sau đó GET bootstrap lần nữa và gửi token mới cho thao tác nghiệp vụ.

### Sau logout

Logout handling thường xóa token hiện tại. Sau logout, client không nên tiếp tục dùng token/session cũ. Kiểm thử cần xác minh:

- Logout request được gửi với CSRF token nếu endpoint logout yêu cầu.
- Response logout xóa/đổi cookie theo cấu hình.
- Request sau logout không còn được xác thực.
- Khi đăng nhập lại, client lấy token mới và không tái sử dụng token cũ.

Status login/logout tùy entry point và success handler; mục tiêu là xác minh vòng đời cookie/token, không ép mọi ứng dụng trả cùng một mã.

## 8. Kiểm tra HTML form thật thay vì chỉ JSON bootstrap

Nếu ứng dụng dùng server-rendered form, hãy gọi trang edit bằng HTTP thật và kiểm tra hidden field được render:

~~~java
Response page = given()
    .baseUri("http://localhost")
    .port(port)
    .filter(cookieJar)
    .auth().preemptive().basic("lan", "test-password")
    .get("/profile/edit");

page.then().statusCode(200);
String html = page.getBody().asString();
assertTrue(html.contains("name=\"_csrf\""));
~~~

Assertion chuỗi chỉ phù hợp khi tên parameter và template đã biết. Với test giao diện, nên dùng HTML parser hoặc browser automation để đọc giá trị hidden input thay vì regex mong manh. Sau đó submit form với cookie jar và giá trị token lấy từ chính trang vừa tải.

Không dùng token cố định trong fixture HTML. Token thay đổi theo session và có thể được masking; fixture tĩnh sẽ không mô phỏng vòng đời token thật.

## 9. Những gì MockMvc không chứng minh được

| MockMvc có thể kiểm tra | Cần HTTP server/browser thật để kiểm tra |
| --- | --- |
| `CsrfFilter` chấp nhận/từ chối request | Cookie được browser lưu và gửi theo Domain/Path |
| Request parameter/header đúng với repository/handler | Cờ Secure, SameSite, HttpOnly trong trình duyệt |
| Dùng `MockHttpSession` giữa các request test | Session cookie thực và session fixation qua container |
| Controller/service có chạy hay không | CORS preflight, credential mode và origin |
| Response status/body trong MVC test | HTTPS/TLS, reverse proxy và cookie behavior ngoài container |

MockMvc vẫn rất hữu ích cho test nhanh và chính xác ở tầng filter/controller. Dùng test HTTP thật cho các yêu cầu liên quan tới cookie jar, browser, CORS, TLS hoặc quá trình login/logout qua container.

## 10. Đối chiếu với WebFlux và WebTestClient

Reactive dùng `ServerWebExchange`, `ServerCsrfTokenRepository` và `WebTestClient`. Mutator `csrf()` của WebTestClient phù hợp để test filter; muốn kiểm tra token được phát và gửi lại qua HTTP thật, phải giữ cookie/session giữa các exchange như với Servlet.

Một luồng kiểm thử ở mức khái niệm:

1. Dùng WebTestClient kết nối server đang chạy và gọi GET bootstrap.
2. Đọc token JSON hoặc cookie từ response.
3. Lưu cookie `SESSION`/cookie CSRF theo cấu hình WebFlux.
4. Gửi POST với đúng cookie và header/parameter token.
5. Gửi lại request thiếu/sai token và xác minh bị từ chối.

Tên cookie session có thể thay đổi theo cấu hình. Không giả định WebFlux dùng `JSESSIONID` hoặc repository Servlet; phải kiểm tra `WebSessionServerCsrfTokenRepository`, cookie repository Reactive và request handler của ứng dụng.

## 11. Checklist kiểm thử vòng đời token

- [ ] Bootstrap request thực sự tới server và nhận token hoặc cookie CSRF.
- [ ] Response bootstrap có `Cache-Control: no-store`.
- [ ] Cookie jar giữ cookie session/CSRF từ response đầu.
- [ ] Request tiếp theo gửi token từ chính response đó.
- [ ] Token hợp lệ được chấp nhận và thao tác nghiệp vụ xảy ra đúng.
- [ ] Request thiếu token bị từ chối.
- [ ] Request có token sai bị từ chối.
- [ ] Hai session/cookie jar không dùng chéo token.
- [ ] Sau login/session rotation, client lấy token mới nếu token cũ bị xóa.
- [ ] Sau logout, cookie/session/token cũ không còn được sử dụng.
- [ ] Với SPA cookie repository, raw/masked token và request handler khớp nhau.
- [ ] Kiểm tra cookie attributes và CORS trong browser khi đó là yêu cầu triển khai.

## Bài tập thực hành

Một ứng dụng dùng `HttpSessionCsrfTokenRepository`, HTTP Basic và endpoint `POST /profile`. Hãy viết test HTTP thật:

1. Gọi GET `/csrf`, lưu token và cookie session bằng cookie jar.
2. Gửi POST `/profile` thiếu token: bị từ chối.
3. Gửi POST `/profile` với token sai: bị từ chối.
4. Gửi POST `/profile` với token nhận từ bootstrap và cùng cookie jar: thành công.
5. Tạo cookie jar thứ hai, dùng token jar thứ nhất: bị từ chối.

Sau đó chuyển sang `CookieCsrfTokenRepository` cho SPA: gọi bootstrap để nhận cookie `XSRF-TOKEN`, đọc token, gửi header `X-XSRF-TOKEN`, rồi thử header sai/thiếu. Giải thích vì sao test cần request handler phù hợp khi ứng dụng bật XOR/BREACH protection.

## Ghi nhớ

Muốn kiểm tra vòng đời CSRF thực tế, hãy **lấy token qua request thật rồi gửi lại bằng chính cookie jar/session đã nhận token**. Session repository gắn token với session phía server; cookie repository phát token qua cookie và thường cần client gửi lại trong header. Kiểm tra cả nhánh hợp lệ, thiếu, sai, đổi phiên, login/logout và cookie attributes. `csrf()` trong MockMvc/WebTestClient vẫn hữu ích cho filter test, nhưng không thay thế kiểm thử HTTP/browser về quá trình phát, lưu và gửi lại token.
