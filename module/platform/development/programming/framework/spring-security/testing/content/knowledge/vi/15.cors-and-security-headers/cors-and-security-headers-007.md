# Giới hạn của MockMvc hoặc WebTestClient so với thực thi chính sách trong trình duyệt

> **Chương:** CORS và header bảo vệ  
> **Module:** SPRING_SECURITY_TESTING — kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` trên ứng dụng Servlet và Reactive.

## 1. Vì sao HTTP test thành công chưa chứng minh browser chấp thuận CORS?

Bạn viết test MockMvc gửi `Origin: https://app.example.vn`, nhận `200 OK` và thấy `Access-Control-Allow-Origin` đúng. Hoặc WebTestClient gọi API và xác nhận toàn bộ response header. Những test đó rất cần thiết, nhưng chúng **không chứng minh JavaScript trong trình duyệt có thể đọc phản hồi**.

CORS có hai phần liên quan nhưng khác nhau:

1. **Phía server:** Spring xử lý request CORS, kiểm tra origin, method và header; nếu hợp lệ thì phát các response header `Access-Control-Allow-*`.
2. **Phía trình duyệt:** browser thực thi Same-Origin Policy và CORS. Nó tự gửi preflight khi cần, kiểm tra response header, quyết định có gửi request thật hay không và có cho JavaScript đọc response hay không.

MockMvc và WebTestClient có thể chạy bộ lọc CORS của ứng dụng. Chúng giúp kiểm tra **quyết định của server** và các header được phát. Nhưng chúng không phải browser engine, không áp dụng Same-Origin Policy lên mã kiểm thử, không tự chặn việc test code đọc body khi thiếu CORS header và không mô phỏng đầy đủ chính sách cookie của trình duyệt.

Vì vậy, kiểm thử Spring Security nên kết hợp nhiều lớp:

- **MockMvc** cho ứng dụng Servlet: kiểm tra CORS filter, security filter chain, status và response header.
- **WebTestClient** cho ứng dụng Reactive: kiểm tra CORS WebFilter/security chain và response header.
- **Browser end-to-end test:** kiểm tra hành vi thật của Fetch/XHR, preflight tự động, khả năng JavaScript đọc response và cookie theo chính sách browser.
- **Kiểm thử qua gateway/proxy:** khi hệ thống có thành phần đứng trước Spring và có thể thay đổi response header.

Bài này giúp bạn biết từng loại test chứng minh điều gì, chọn công cụ phù hợp và tránh kết luận quá mức từ một HTTP client không thực thi CORS như trình duyệt.

## 2. CORS server-side và browser enforcement

Giả sử frontend tại `https://app.example.vn` gọi API tại `https://api.example.vn`. Đây là hai origin khác nhau vì host khác nhau.

~~~mermaid
flowchart TD
    A["Frontend JavaScript gọi API khác origin"] --> B["Browser tạo request / preflight"]
    B --> C["HTTP request tới Spring"]
    C --> D["Spring CORS filter / processor"]
    D --> E["Authentication, authorization, CSRF"]
    E --> F["Response HTTP + CORS headers"]
    F --> G["Browser kiểm tra CORS response"]
    G -->|Được phép| H["JavaScript đọc response"]
    G -->|Không được phép| I["Fetch/XHR báo lỗi CORS"]
~~~

Sơ đồ mô tả luồng khái quát. Với preflight hợp lệ, CORS filter có thể trả lời ngay mà không chạy authentication/controller. Với actual request, request tiếp tục qua các filter bảo mật trước khi tạo response. Browser sau đó vẫn phải kiểm tra response header.

### 2.1. Phía server chịu trách nhiệm gì?

Spring CORS processor có thể:

- Đọc `Origin` và kiểm tra allowlist.
- Với preflight, đọc `Access-Control-Request-Method` và `Access-Control-Request-Headers`.
- Từ chối origin, method hoặc header không hợp lệ.
- Trả `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`, `Access-Control-Allow-Credentials` và các header liên quan.
- Cho actual request hợp lệ tiếp tục qua authentication, authorization, CSRF và controller.

MockMvc/WebTestClient có thể xác minh những hành vi này **nếu test đã gắn đúng filter chain của ứng dụng**.

### 2.2. Trình duyệt chịu trách nhiệm gì?

Browser:

- Quyết định một request có cần preflight theo phương thức, header và content type hay không.
- Tự phát OPTIONS preflight khi cần.
- Kiểm tra response của preflight để quyết định có gửi actual request không.
- Kiểm tra response của actual request để quyết định có chia sẻ dữ liệu với JavaScript không.
- Quản lý cookie theo Domain, Path, Secure, SameSite, thời hạn và chính sách quyền riêng tư.
- Áp dụng giới hạn credentialed CORS, wildcard và response header được expose.

Một HTTP client thông thường có thể gửi bất kỳ header nào và đọc body bất kể CORS. Đó là hành vi đúng của client ngoài browser; CORS không phải cơ chế xác thực người gọi ở phía server.

## 3. MockMvc chứng minh được gì?

### 3.1. Những gì MockMvc kiểm tra tốt

MockMvc mô phỏng request/response Servlet trong môi trường test và có thể chạy qua DispatcherServlet cùng các filter được đăng ký. Khi dùng `@SpringBootTest` và `@AutoConfigureMockMvc` mặc định, bạn có thể kiểm tra:

- `CorsFilter` hoặc CORS tích hợp trong Spring Security có được áp dụng không.
- Preflight hợp lệ được xử lý trước authentication.
- Origin/method/requested header bị cấm có bị từ chối không.
- Actual response có `Access-Control-Allow-Origin` và các header phù hợp không.
- Actual request vẫn chịu authentication, authorization và CSRF.
- `@WithMockUser`, `jwt()`, `oauth2Login()`, `oidcLogin()` tạo security context giả lập có tác động như mong đợi tới endpoint.

Ví dụ:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class CorsServerTests {

    @Autowired
    MockMvc mvc;

    @Test
    void preflightChoOriginHopLe() throws Exception {
        mvc.perform(options("/api/profile")
                .header(HttpHeaders.ORIGIN, "https://app.example.vn")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://app.example.vn"));
    }
}
~~~

Test này chứng minh server đã xử lý request OPTIONS theo CORS policy và phát header mong đợi. Nó **không chứng minh browser thật đã tự tạo preflight**, cũng không chứng minh JavaScript có thể đọc response.

### 3.2. Những gì MockMvc không mô phỏng

MockMvc không chạy browser engine. Nó không:

- Thực thi Same-Origin Policy đối với JavaScript.
- Tự quyết định preflight như Fetch/XHR; test phải tự tạo request OPTIONS với các header preflight.
- Chặn việc test code đọc response body vì thiếu `Access-Control-Allow-Origin`.
- Áp dụng cookie policy của Chrome/Firefox/WebKit như SameSite, third-party cookie, partitioning hoặc tracking prevention.
- Mô phỏng đầy đủ TLS, DNS, socket, reverse proxy, CDN và network routing.
- Chứng minh browser cache kết quả preflight như dự kiến.
- Xác minh hành vi redirect, browser extension, service worker hoặc CSP trong toàn ứng dụng.

MockMvc cũng không tự đảm bảo filter đã được thêm vào test. Nếu dùng `MockMvcBuilders.standaloneSetup(...)` mà không gắn filter/security config, bạn có thể chỉ test controller. Với mục tiêu kiểm chứng filter chain, hãy dùng application context hoặc chủ động cấu hình đầy đủ filter.

## 4. WebTestClient chứng minh được gì?

### 4.1. Những gì WebTestClient kiểm tra tốt

WebTestClient là HTTP testing client cho ứng dụng Reactive và cũng có thể dùng với một số ứng dụng MVC. Khi được gắn vào application context cùng Spring Security, nó kiểm tra được:

- CORS WebFilter hoặc CORS trong `SecurityWebFilterChain`.
- Preflight OPTIONS và actual request.
- Response header, status và body.
- Authentication/authorization giả lập bằng tiện ích Spring Security Test, ví dụ `mockUser()` hoặc `mockJwt()`.
- Hành vi khi origin/method/header bị từ chối.

Ví dụ:

~~~java
@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveCorsServerTests {

    @Autowired
    WebTestClient client;

    @Test
    void preflightChoOriginHopLe() {
        client.options().uri("/api/profile")
            .header(HttpHeaders.ORIGIN, "https://app.example.vn")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://app.example.vn");
    }
}
~~~

Nếu dùng client tự dựng, hãy xác định kiểu binding:

- `bindToController(...)`: tập trung vào controller/handler đã khai báo; không mặc nhiên có đầy đủ filter chain ứng dụng.
- `bindToApplicationContext(...)`: có thể gắn các thành phần WebFlux trong application context; phải xác minh security config/filter đã được áp dụng.
- `bindToServer()`: gửi HTTP tới server đang chạy; kiểm tra network/server response thực tế, nhưng client vẫn không thực thi CORS như browser.

### 4.2. Những gì WebTestClient không mô phỏng

Dù dùng `bindToServer()` và gửi request qua socket thật, WebTestClient vẫn là HTTP client, không phải browser. Nó không tự:

- Chặn response body vì CORS policy.
- Tự thực hiện toàn bộ thuật toán preflight của Fetch.
- Áp dụng chính sách SameSite, third-party cookie hoặc browser privacy controls.
- Kiểm tra JavaScript có đọc được response header tùy biến hay không.
- Thực hiện browser navigation, redirect, service worker hoặc CSP như trình duyệt.

Điều này cũng đúng với `curl`, Postman và các HTTP client khác: chúng giúp xem phản hồi server, không chứng minh CORS đã được browser chấp thuận.

## 5. So sánh nhanh các lớp kiểm thử

| Công cụ | Chạy Spring CORS/filter? | Browser tự preflight? | Browser chặn JS đọc response? | Cookie browser policy? |
| --- | --- | --- | --- | --- |
| MockMvc qua application context | Có, nếu filter được gắn | Không | Không | Không |
| WebTestClient bindToController | Chỉ handler được bind; phụ thuộc cấu hình | Không | Không | Không |
| WebTestClient bindToApplicationContext | Có nếu context/filter chain được áp dụng | Không | Không | Không |
| WebTestClient bindToServer | Có, tại server thực | Không | Không | Không |
| curl/Postman | Server xử lý nếu gửi tới server | Không | Không | Không theo browser policy |
| Playwright/Selenium trên browser | Có, qua HTTP server thật | Có | Có | Có, theo browser/engine |

**Lựa chọn đúng:** MockMvc/WebTestClient xác minh logic phía Spring; browser E2E xác minh trải nghiệm thật của frontend và browser. Hai lớp bổ sung cho nhau.

## 6. Thiết kế test matrix cho CORS

| Tình huống | Test Spring (MockMvc/WebTestClient) | Test browser |
| --- | --- | --- |
| Origin được phép | Kiểm tra status và ACAO đúng | Fetch resolve và JavaScript đọc được body |
| Origin bị cấm, request cần preflight | OPTIONS bị từ chối, không ACAO | Browser gửi OPTIONS, không gửi actual request, fetch reject |
| Origin bị cấm, simple request | CORS processor xử lý actual request theo policy | Browser có thể gửi request nhưng không cho JS đọc response |
| Method bị cấm | Preflight bị từ chối | Browser không gửi actual method sau preflight fail |
| Header bị cấm | Preflight bị từ chối | Browser không gửi actual request sau preflight fail |
| Credentialed request | Kiểm tra ACAO cụ thể và ACAC true | Browser gửi cookie nếu cookie policy cho phép |
| Exposed response header | Kiểm tra Expose-Headers | JavaScript đọc được header đã expose |
| Authentication thiếu | Kiểm tra 401/redirect và CORS header | JavaScript đọc response lỗi nếu CORS header hợp lệ |
| CSRF thiếu | Actual request bị chặn theo CSRF policy | Browser request thực tế bị từ chối |
| Preflight cache | Kiểm tra Max-Age/Vary | Kiểm tra hành vi browser khi lặp request, có lưu ý giới hạn cache của browser |

### 6.1. Positive test phải chứng minh được cả hai tầng

Ở tầng Spring, kiểm tra:

- Origin được phép và header ACAO đúng.
- Method và requested headers được chấp thuận.
- Credential policy hợp lệ nếu cần.
- Actual response có các header mà frontend cần đọc.

Ở tầng browser, kiểm tra:

- Fetch/XHR hoàn tất mà không ném lỗi CORS.
- JavaScript đọc được status/body.
- Các response header cần dùng được expose.
- Cookie/session thực sự được gửi nếu test yêu cầu credential.

### 6.2. Negative test cần phân biệt hai loại từ chối

**Preflight bị từ chối:** Browser gửi OPTIONS, nhận phản hồi không đáp ứng CORS, nên không gửi actual request. Đây là điều có thể quan sát bằng event request của Playwright.

**Actual response không được chia sẻ:** Với một số simple request, browser có thể gửi request thật rồi mới từ chối cho JavaScript đọc response. Không được kết luận rằng request không tới server chỉ vì Fetch reject.

## 7. Browser E2E với Playwright

Browser E2E kiểm tra CORS theo hành vi thật của browser engine. Ví dụ dưới đây dùng Playwright Test với ba origin:

- Frontend được phép: `https://app.example.test`.
- Frontend không được phép: `https://blocked.example.test`.
- API: `https://api.example.test`.

Các host này cần được ánh xạ tới ứng dụng test hoặc môi trường dev; frontend phải được phục vụ từ đúng origin để browser áp dụng CORS. Ví dụ dùng endpoint GET có custom header nhằm buộc preflight. Endpoint test không nên thay đổi dữ liệu.

### 7.1. Origin hợp lệ: browser tự preflight và JavaScript đọc response

~~~typescript
import { test, expect } from "@playwright/test";

test("browser cho phep origin hop le va doc duoc response", async ({ page }) => {
  await page.goto("https://app.example.test");

  const result = await page.evaluate(async () => {
    const response = await fetch(
      "https://api.example.test/api/cors-probe",
      {
        method: "GET",
        headers: { "X-Client-Probe": "browser-test" },
        credentials: "include"
      }
    );

    return {
      status: response.status,
      body: await response.json(),
      requestId: response.headers.get("X-Request-ID")
    };
  });

  expect(result.status).toBe(200);
  expect(result.body.ok).toBe(true);
  expect(result.requestId).toBeTruthy();
});
~~~

Ở đây, `X-Client-Probe` không phải CORS-safelisted request header nên browser tự gửi preflight. Nếu API cho phép origin, method và header, preflight thành công rồi actual GET được gửi. `credentials: "include"` yêu cầu browser sử dụng credential phù hợp; cookie chỉ thực sự được gửi nếu đã đăng nhập và cookie policy cho phép. `X-Request-ID` chỉ đọc được từ JavaScript nếu server expose header đó.

### 7.2. Origin bị cấm: preflight thất bại và actual request không được gửi

~~~typescript
import { test, expect } from "@playwright/test";

test("browser khong gui actual request sau preflight bi tu choi", async ({ page }) => {
  const apiRequests: string[] = [];

  page.on("request", request => {
    if (request.url().startsWith("https://api.example.test/api/cors-probe")) {
      apiRequests.push(request.method());
    }
  });

  await page.goto("https://blocked.example.test");

  const outcome = await page.evaluate(async () => {
    try {
      await fetch("https://api.example.test/api/cors-probe", {
        method: "GET",
        headers: { "X-Client-Probe": "browser-test" }
      });
      return "resolved";
    } catch (error) {
      return "rejected";
    }
  });

  expect(outcome).toBe("rejected");
  expect(apiRequests).toContain("OPTIONS");
  expect(apiRequests).not.toContain("GET");
});
~~~

Test này chứng minh hành vi browser cho request cần preflight: OPTIONS được gửi; do preflight không được chấp thuận, GET không được gửi. Nếu test dùng một simple GET không có header ngoài safelist, browser có thể gửi GET trước rồi chỉ chặn JavaScript đọc response. Khi đó kỳ vọng “không có GET” là sai.

### 7.3. Simple request từ origin bị cấm: server vẫn có thể nhận request

~~~typescript
import { test, expect } from "@playwright/test";

test("simple request co the toi server du browser khong cho JS doc", async ({ page }) => {
  await page.goto("https://blocked.example.test");

  const outcome = await page.evaluate(async () => {
    try {
      const response = await fetch(
        "https://api.example.test/api/public-probe"
      );
      return "readable:" + response.status;
    } catch (error) {
      return "cors-rejected";
    }
  });

  expect(outcome).toBe("cors-rejected");
});
~~~

GET này không thêm header tùy biến và có thể không cần preflight. Browser có thể gửi request thật đến server nhưng từ chối chia sẻ response cho JavaScript vì ACAO không hợp lệ. Vì vậy:

- Fetch reject không chứng minh server chưa xử lý request.
- Không dùng thao tác thay đổi dữ liệu qua simple request rồi cho rằng CORS sẽ ngăn request đó.
- Endpoint thay đổi trạng thái phải được bảo vệ bằng xác thực, phân quyền, CSRF và thiết kế HTTP đúng ngữ nghĩa.

### 7.4. Giới hạn của browser test

Browser test xác minh behavior của một browser engine và môi trường cụ thể. Nó không tự chứng minh mọi browser, mọi cấu hình privacy hoặc mọi mạng production giống nhau. Nên chạy các ca trọng yếu trên những browser engine mà sản phẩm hỗ trợ (ví dụ Chromium, Firefox, WebKit), nhất là khi dùng cookie cross-site.

Không cố định kỳ vọng về số lần preflight trong các test phụ thuộc cache: browser có thể cache preflight theo `Access-Control-Max-Age` nhưng áp dụng giới hạn riêng. Tạo browser context mới hoặc dùng endpoint/header riêng để giảm ảnh hưởng của cache khi cần kiểm tra hành vi lần đầu.

## 8. Cookie và credential: chỉ browser test mới kiểm tra được đầy đủ

MockMvc có thể gắn `MockHttpSession` hoặc cookie giả vào request. WebTestClient có thể gửi cookie bằng API client. Cả hai đều kiểm tra server nhận cookie và xử lý session ra sao, nhưng không áp dụng đầy đủ chính sách trình duyệt.

Browser kiểm tra các điều kiện:

- Frontend dùng `credentials: "include"` (Fetch) hoặc `withCredentials = true` (XHR).
- Server trả `Access-Control-Allow-Origin` cụ thể, không dùng wildcard khi credential mode là include.
- Server trả `Access-Control-Allow-Credentials: true`.
- Cookie khớp Domain, Path, Secure, SameSite và thời hạn.
- Browser có cho phép third-party cookie trong ngữ cảnh test không.
- CSRF token được cung cấp và gửi theo cơ chế ứng dụng.

Ví dụ test server có thể xác nhận header:

~~~java
mvc.perform(get("/api/profile")
        .header(HttpHeaders.ORIGIN, "https://app.example.vn")
        .session(existingSession))
    .andExpect(status().isOk())
    .andExpect(header().string(
        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
        "https://app.example.vn"))
    .andExpect(header().string(
        HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true"));
~~~

Test này kiểm tra server xử lý session đã gắn vào request. Nó không chứng minh browser sẽ gửi cookie session trong ngữ cảnh cross-site. Cần browser E2E sau khi thực hiện login bằng cùng browser context, rồi gọi API với credential mode phù hợp.

Không dùng `@WithMockUser` để tuyên bố đã kiểm tra cookie. Annotation đó tạo security context giả lập; nó không tạo quy trình Set-Cookie, lưu cookie và gửi cookie của trình duyệt.

## 9. Các giới hạn khác ngoài CORS

### 9.1. Redirect và preflight

Redirect trong chuỗi preflight/actual có thể có khác biệt theo browser và cấu hình server. Nếu API hoặc proxy redirect HTTP sang HTTPS, thay đổi host hoặc chuyển endpoint, hãy kiểm tra bằng browser test qua URL production-like. MockMvc có thể xác nhận redirect status/location ở server nhưng không xác minh browser theo đuổi redirect và áp dụng CORS trên toàn chuỗi như thế nào.

### 9.2. Cache và Vary

MockMvc/WebTestClient có thể kiểm tra `Access-Control-Max-Age` và `Vary` được phát. Chúng không chứng minh browser cache preflight giống nhau giữa các engine, cũng không mô phỏng CDN/proxy cache. Cần kiểm tra response qua gateway và browser test lặp request trong context phù hợp.

### 9.3. HTTPS, proxy và origin thực tế

Test MockMvc không có TLS handshake. WebTestClient `bindToServer()` có thể kết nối HTTP/HTTPS tới server nhưng vẫn không phải browser. Nếu production dùng TLS termination ở gateway, forwarded headers, cookie Secure hoặc origin rewrite, cần kiểm tra qua gateway với browser thật.

### 9.4. CSP, service worker và các chính sách browser khác

Một trang có thể gặp lỗi do Content Security Policy (`connect-src`), service worker, mixed content hoặc browser privacy controls dù CORS server đã đúng. MockMvc/WebTestClient không thực thi những chính sách này. Browser DevTools và E2E test giúp phân biệt lỗi CORS với lỗi của các cơ chế browser khác.

## 10. Chiến lược kiểm thử theo tầng

| Tầng | Công cụ | Nên kiểm tra | Không nên kết luận |
| --- | --- | --- | --- |
| Unit/configuration | Test `CorsConfiguration` hoặc policy helper | Allowlist, method, headers, credential flags | Filter chain đã được tích hợp đúng |
| Servlet integration | MockMvc + application context | CORS filter, SecurityFilterChain, status/header, authn/authz/CSRF | Browser chấp thuận CORS hoặc cookie được gửi |
| Reactive integration | WebTestClient + WebFlux context | CORS WebFilter/security chain, status/header, security context | Browser chấp thuận CORS hoặc cookie được gửi |
| Browser E2E | Playwright/Selenium | Preflight tự động, Fetch/XHR, JS response access, cookie behavior | Mọi browser/production network đều giống hệt |
| Environment E2E | Browser qua gateway/CDN | Header cuối tuyến, proxy, TLS, cache, redirect | Các cấu hình môi trường khác đã được kiểm tra |

Một pipeline có thể chia thành:

1. Chạy test MockMvc/WebTestClient nhanh ở mỗi thay đổi backend.
2. Chạy browser E2E cho các luồng CORS quan trọng trong CI.
3. Chạy browser matrix trên các engine hỗ trợ theo lịch hoặc trước release.
4. Kiểm tra thêm qua gateway/staging khi thay đổi proxy, TLS, cookie hoặc CDN.

Không cần đưa toàn bộ ma trận browser vào mọi test đơn vị; chọn các kịch bản rủi ro cao để giữ pipeline ổn định và có tín hiệu rõ.

## 11. Chẩn đoán lỗi từ góc nhìn đúng tầng

| Hiện tượng | Kiểm tra phía Spring | Kiểm tra phía browser |
| --- | --- | --- |
| MockMvc pass nhưng Fetch lỗi CORS | Test có gắn đúng filter không? ACAO có khớp origin thật? | Network: preflight/actual response và Console |
| WebTestClient pass nhưng actual request không gửi | Allow-Methods/Headers có đúng? | Preflight response có đáp ứng toàn bộ yêu cầu không? |
| Server trả 200, Fetch reject | Response có ACAO? Có redirect? | CORS, CSP, mixed content, redirect |
| Cookie không có trong request | Session/cookie server có được tạo không? | credentials include, SameSite, Secure, Domain, third-party policy |
| JavaScript không đọc được X-Request-ID | Server có phát header? | Expose-Headers có liệt kê header? |
| Simple GET origin lạ vẫn xuất hiện ở access log | CORS actual request response có bị chặn chia sẻ? | Browser có thể đã gửi GET rồi chặn response |
| OPTIONS trả 401 | CORS filter có chạy trước authentication? | Xem preflight response và security log |
| Test qua app nhưng staging lỗi | App response có header đúng? | Gateway/CDN/TLS/cache có sửa response không? |

Luôn ghi nhận ba dữ liệu riêng: **request browser đã gửi**, **response server đã trả**, và **dữ liệu JavaScript được phép đọc**. Chúng không đồng nghĩa với nhau.

## 12. Bài thực hành và tiêu chí hoàn thành

Một hệ thống có frontend `https://app.example.test`, frontend thứ hai không được phép `https://blocked.example.test` và API `https://api.example.test`. API cho phép origin thứ nhất gửi GET kèm `X-Client-Probe`, đồng thời trả `X-Request-ID` cho frontend đọc.

Hãy thực hiện:

1. Viết MockMvc test cho preflight hợp lệ, preflight từ origin bị cấm và actual response. Xác nhận CORS filter thật được chạy.
2. Viết WebTestClient tương đương nếu API dùng WebFlux; xác nhận security web filter chain được gắn vào client.
3. Viết Playwright test từ frontend hợp lệ, gửi Fetch có custom header để browser tự preflight và kiểm tra JavaScript đọc được body cùng `X-Request-ID`.
4. Viết Playwright test từ origin bị cấm, gửi request cần preflight; xác nhận OPTIONS có mặt và actual request không được gửi.
5. Viết thêm một simple GET từ origin bị cấm; xác nhận Fetch reject nhưng hiểu rằng request thật có thể đã tới server.
6. Nếu dùng session cookie, đăng nhập trong browser context, gọi API với `credentials: "include"` và kiểm tra cookie thực sự được gửi trong điều kiện browser hỗ trợ.
7. Chạy test qua gateway/staging nếu có proxy hoặc TLS termination ảnh hưởng CORS.

**Tiêu chí hoàn thành:** bạn có thể giải thích chính xác MockMvc/WebTestClient chứng minh quyết định CORS ở phía Spring, còn browser E2E chứng minh browser thực thi CORS và cho JavaScript đọc response. Bạn biết khi nào preflight thất bại làm actual request không được gửi, khi nào simple request có thể đã tới server, và vì sao kiểm thử cookie/browser cần một tầng riêng.

**Điểm cần nhớ:** Đừng dùng kết quả `200 OK` của HTTP test client để kết luận CORS đã hoạt động trong trình duyệt. Hãy kiểm tra server filter chain bằng MockMvc/WebTestClient và kiểm tra browser enforcement bằng E2E trên browser engine thật.
