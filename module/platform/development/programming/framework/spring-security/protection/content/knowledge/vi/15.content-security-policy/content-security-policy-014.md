# Kiểm thử hành vi thật trên trình duyệt ngoài việc kiểm tra chuỗi header

> **Chương:** Chính sách nội dung CSP  
> **Mô-đun:** `SPRING_SECURITY_HTTP_PROTECTION` — áp dụng các lớp phòng vệ HTTP và trình duyệt trong Spring Security, từ CSRF, CORS, security headers, CSP, HSTS đến HTTP firewall và bảo vệ session. Người học cấu hình cho Servlet lẫn Reactive, kiểm thử các kịch bản tấn công web và chẩn đoán xung đột bảo mật khi triển khai.

## 1. Header đúng chưa chứng minh browser bảo vệ đúng

Giả sử ứng dụng Spring Boot có integration test:

~~~java
mockMvc.perform(get("/dashboard"))
    .andExpect(header().string(
        "Content-Security-Policy",
        containsString("script-src 'self'")
    ));
~~~

Test PASS chứng minh server có trả một chuỗi chứa `script-src 'self'`. Nhưng nó **không chứng minh**:

- JavaScript ngoài cùng origin thực sự tải và chạy.
- Script inline không được cấp phép, event handler hoặc `eval` đã bị trình duyệt chặn.
- CSS, ảnh, font, kết nối API và biểu mẫu hợp lệ không bị chính sách làm hỏng.
- HTML cuối cùng qua reverse proxy/CDN có CSP giống response do Spring phát.
- Một CSP thực thi khác có đang giao với policy này hay không.
- Nonce/hash trong header có khớp **HTML mà browser thực sự nhận** hay không.
- Browser hỗ trợ directive cụ thể và thực thi ở phiên bản mục tiêu hay không.

**Content Security Policy (CSP) là chính sách được browser thực thi trong ngữ cảnh tài liệu.** Spring Security giúp phát header, còn hành vi của trình duyệt cần được kiểm tra riêng. Chỉ thấy một header cũng không chứng minh ứng dụng không có lỗ hổng XSS.

Mục tiêu của bài học:

1. Thiết kế một bộ kiểm thử có **hành vi hợp lệ** và **hành vi cần bị từ chối**.
2. Kết hợp MockMvc/WebTestClient, DevTools, `SecurityPolicyViolationEvent` và trình duyệt tự động.
3. Kiểm tra các nhóm `script-src`, `style-src`, `img-src`, `connect-src`, `form-action`, `base-uri` và những trường hợp nonce/hash.
4. Phân biệt Report-Only với CSP thực thi và với các lỗi CORS, CSRF, authentication, HTTP hoặc mạng.
5. Chẩn đoán khác biệt giữa Servlet, WebFlux, origin, CDN, cache và trình duyệt thật.

## 2. Ba tầng bằng chứng cần kết hợp

Một bộ test chất lượng cần trả lời ba câu hỏi khác nhau:

| Tầng | Điều được kiểm tra | Công cụ điển hình | Giới hạn |
|---|---|---|---|
| **A. Response server** | Route HTML có đúng header CSP? | MockMvc, WebTestClient, HTTP client | Không chạy JS/CSS hoặc chứng minh browser chặn |
| **B. Hành vi browser** | Mã chạy/bị chặn, request được thử gửi, giao diện thay đổi | DevTools, Playwright/Selenium | Chưa chứng minh toàn bộ nghiệp vụ và server an toàn |
| **C. Chức năng end-to-end** | Đăng nhập, API, form, upload, checkout hoạt động sau khi bật CSP? | Browser E2E và log backend | Không phủ mọi biến thể tấn công |

~~~mermaid
flowchart TD
    A[Xác định hành vi được phép và bị cấm] --> B[Kiểm tra header HTML]
    B --> C[Chạy browser]
    C --> D[Đo hiệu ứng DOM và network]
    D --> E[Đọc CSP violation, Console, status]
    E --> F{Bằng chứng khớp kỳ vọng?}
    F -- Không --> G[Phân biệt CSP, CORS, CSRF, auth, cache, lỗi mạng]
    G --> B
    F -- Có --> H[Kiểm tra nghiệp vụ và browser mục tiêu]
~~~

Một phép thử vững chắc có **ít nhất hai dấu hiệu**. Ví dụ khối script không tạo hiệu ứng trên DOM **và** có violation `script-src` với `disposition: "enforce"`. Chỉ thấy script không chạy có thể là do HTTP 404 hoặc JavaScript lỗi cú pháp.

Ngược lại, trang “chạy bình thường” không chứng minh CSP đang chặn nguồn nguy hiểm; có thể ứng dụng đang dùng `Content-Security-Policy-Report-Only` hoặc `'unsafe-inline'`.

## 3. Lập ma trận kỳ vọng trước khi chạy browser

Chọn một policy minh họa cho trang kiểm thử ở `http://localhost:8080`:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'self'; script-src-attr 'none'; style-src 'self'; style-src-attr 'none'; img-src 'self'; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'
~~~

Policy này cố ý dùng JavaScript/CSS từ file cùng origin, không cho inline script/handler, không cho ảnh hoặc API ngoài origin và không dùng object/embed.

| Ca | Thử gì? | Theo CSP phải thế nào? | Bằng chứng nên lấy |
|---|---|---|---|
| S1 | JS `/js/csp-lab.js` | Cho phép | Script cập nhật DOM |
| S2 | `<script>` inline không nonce/hash | Chặn | Không tạo hiệu ứng + violation |
| S3 | `onclick` inline | Chặn | Click không chạy handler + violation |
| C1 | CSS file `/css/csp-lab.css` | Cho phép | Computed style đúng |
| C2 | `<style>` inline | Chặn | Computed style giữ giá trị đối chứng + violation |
| I1 | Ảnh cùng origin | Cho phép | `naturalWidth > 0` và HTTP thành công |
| I2 | Ảnh ngoài `img-src` | Chặn | Violation `img-src`, không chỉ ảnh trống |
| N1 | `fetch("/csp-lab/ping")` | Cho phép | Response hợp lệ + DOM đổi |
| N2 | `fetch` tới host ngoài `connect-src` | Chặn | Violation `connect-src` |
| F1 | Form cùng origin | Được phép về mặt CSP | HTTP gửi thành công nếu CSRF/auth phù hợp |
| F2 | Form khác origin | Chặn | Violation `form-action` và không submit ngoài |

Khi mở rộng test, thêm tình huống cho nonce, hash, WebSocket, `base-uri`, `frame-src`/`frame-ancestors`, Report-Only và cache. Đừng đưa mọi hành vi vào một test duy nhất vì sẽ khó xác định nguyên nhân khi thất bại.

## 4. Trang lab có cả phép thử dương tính và âm tính

Ví dụ HTML dùng trong môi trường **có quyền kiểm soát**:

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>CSP Browser Lab</title>
  <link rel="stylesheet" href="/css/csp-lab.css">

  <!-- Khối CSS cố tình vi phạm style-src -->
  <style>.inline-style-target { color: rgb(220, 38, 38); }</style>
</head>
<body>
  <h1>Kiểm thử CSP</h1>
  <p id="external-status">chưa chạy</p>
  <p class="inline-style-target">Màu chữ đối chứng</p>

  <button id="inline-button" type="button"
          onclick="document.documentElement.dataset.inlineHandler='executed'">
    Inline handler
  </button>

  <button id="same-origin-fetch" type="button">Fetch nội bộ</button>
  <button id="outside-fetch" type="button">Fetch ngoài danh sách</button>

  <img id="allowed-image" src="/images/csp-ok.svg" alt="Ảnh hợp lệ">
  <img id="blocked-image"
       src="https://outside.example.invalid/pixel.png"
       alt="Ảnh ngoài allowlist">

  <script src="/js/csp-lab.js" defer></script>

  <!-- Script không nonce/hash, phải bị chặn trong policy thực thi -->
  <script>
    document.documentElement.dataset.inlineScript = "executed";
  </script>
</body>
</html>
~~~

Tệp CSS mẫu:

~~~css
/* /css/csp-lab.css */
.inline-style-target { color: rgb(0, 0, 0); }
~~~

Ảnh hợp lệ mà demo cần phục vụ tại `/images/csp-ok.svg`:

~~~xml
<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24">
  <rect width="24" height="24" fill="navy"/>
</svg>
~~~

JavaScript đáng tin từ `/js/csp-lab.js`:

~~~javascript
document.getElementById("external-status").textContent = "external ok";

document.getElementById("same-origin-fetch")
  .addEventListener("click", async () => {
    try {
      const response = await fetch("/csp-lab/ping");
      document.documentElement.dataset.sameOriginFetch =
        response.ok ? "ok" : "http-error";
    } catch (error) {
      document.documentElement.dataset.sameOriginFetch = "failed";
    }
  });

document.getElementById("outside-fetch")
  .addEventListener("click", async () => {
    try {
      await fetch("https://outside.example.invalid/collect");
      document.documentElement.dataset.outsideFetch = "completed";
    } catch (error) {
      document.documentElement.dataset.outsideFetch = "failed";
    }
  });
~~~

Địa chỉ `outside.example.invalid` là host mô phỏng không có dịch vụ thật, giúp tránh gửi dữ liệu đến hệ thống ngoài. Vì host này có thể thất bại do DNS ngay cả khi CSP cho phép, **không dùng riêng việc request thất bại làm bằng chứng CSP**. Cần có violation tương ứng. Với ca kiểm tra request được phép, dùng một endpoint thực sự do đội phát triển kiểm soát.

**Giải thích các đối chứng:** script ngoài được phép cập nhật `#external-status`; script inline bị chặn không được đặt `dataset.inlineScript`; click inline handler không được đặt `dataset.inlineHandler`. CSS ngoài đặt màu đen, còn khối CSS inline cố định đặt màu đỏ; nếu inline bị chặn, computed style giữ màu đen. Ảnh hợp lệ chỉ được coi là positive control khi đã phục vụ đúng file và trả HTTP thành công.

## 5. Cấu hình Spring Security Servlet cho trang lab

Ví dụ Spring MVC/Servlet. Nếu dự án đã có authorization hoặc nhiều security chain, cần hợp nhất quy tắc này theo kiến trúc thật, không tạo một chain thứ hai cạnh tranh:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class CspLabServletSecurity {

    public static final String POLICY =
        "default-src 'none'; " +
        "script-src 'self'; " +
        "script-src-attr 'none'; " +
        "style-src 'self'; " +
        "style-src-attr 'none'; " +
        "img-src 'self'; " +
        "font-src 'self'; " +
        "connect-src 'self'; " +
        "object-src 'none'; " +
        "base-uri 'none'; " +
        "form-action 'self'; " +
        "frame-ancestors 'none'";

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(
                "/csp-lab",
                "/csp-lab/ping",
                "/js/csp-lab.js",
                "/css/csp-lab.css",
                "/images/csp-ok.svg"
            ).permitAll()
            .anyRequest().authenticated()
        );

        http.headers(headers -> headers
            .contentSecurityPolicy(csp -> csp
                .policyDirectives(POLICY)
            )
        );

        // Không tắt CSRF, CORS, HSTS hoặc session protection để thử CSP.
        return http.build();
    }
}
~~~

Controller cho HTML và endpoint ping:

~~~java
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ResponseBody;

@Controller
public class CspLabController {

    @GetMapping("/csp-lab")
    public String page() {
        return "csp-lab"; // templates/csp-lab.html
    }

    @GetMapping("/csp-lab/ping")
    @ResponseBody
    public String ping() {
        return "pong";
    }
}
~~~

Chỉ những response đi qua security chain tương ứng mới nhận header từ cấu hình đó. Header CSP trên `/csp-lab/ping` (JSON hoặc text) **không tự đặt chính sách cho HTML**; phải xác minh riêng response của `GET /csp-lab`.

## 6. Cấu hình Spring Security Reactive/WebFlux

Với Reactive/WebFlux, dùng `ServerHttpSecurity` và `SecurityWebFilterChain`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class CspLabReactiveSecurity {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        String policy =
            "default-src 'none'; " +
            "script-src 'self'; " +
            "script-src-attr 'none'; " +
            "style-src 'self'; " +
            "style-src-attr 'none'; " +
            "img-src 'self'; " +
            "font-src 'self'; " +
            "connect-src 'self'; " +
            "object-src 'none'; " +
            "base-uri 'none'; " +
            "form-action 'self'; " +
            "frame-ancestors 'none'";

        http.authorizeExchange(exchanges -> exchanges
            .pathMatchers(
                "/csp-lab",
                "/csp-lab/ping",
                "/js/csp-lab.js",
                "/css/csp-lab.css",
                "/images/csp-ok.svg"
            ).permitAll()
            .anyExchange().authenticated()
        );

        http.headers(headers -> headers
            .contentSecurityPolicy(csp -> csp
                .policyDirectives(policy)
            )
        );
        return http.build();
    }
}
~~~

Trang HTML và endpoint ping tương ứng được phục vụ bằng controller/view Reactive trong ứng dụng. Ý nghĩa CSP **không thay đổi** giữa Servlet và WebFlux vì browser thực thi chính sách. Nếu frontend HTML do CDN cung cấp còn WebFlux chỉ trả JSON/SSE, CSP phải xuất **trên HTML từ CDN**, không chỉ trên API.

## 7. MockMvc/WebTestClient: xác minh header đúng phạm vi

Servlet:

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(get("/csp-lab"))
    .andExpect(status().isOk())
    .andExpect(header().string(
        "Content-Security-Policy",
        containsString("script-src-attr 'none'")
    ))
    .andExpect(header().string(
        "Content-Security-Policy",
        containsString("connect-src 'self'")
    ));
~~~

WebFlux:

~~~java
webTestClient.get()
    .uri("/csp-lab")
    .exchange()
    .expectStatus().isOk()
    .expectHeader()
    .valueMatches(
        "Content-Security-Policy",
        ".*script-src 'self'.*"
    );
~~~

Hai test này chỉ xác minh **giá trị header**. Chúng chưa chạy engine CSS, chưa thực thi JavaScript và chưa chứng minh browser từ chối request ngoài allowlist. Khi route cần đăng nhập, test phải tạo authentication hợp lệ để kiểm tra đúng response HTML, thay vì chỉ nhận 302/401/403.

Nên dùng test server để phát hiện sai tên header, thiếu directive, policy biến đổi ngoài dự kiến hoặc cấu hình nhầm chain. Sau đó dùng browser để xác minh **hành vi** và **tác động nghiệp vụ**.

## 8. Quan sát thủ công bằng DevTools

Trong môi trường lab:

1. Mở trang `/csp-lab` bằng browser cần hỗ trợ và bật DevTools.
2. Ở **Network**, chọn request loại **Document**. Đọc đầy đủ `Content-Security-Policy` và `Content-Security-Policy-Report-Only`. Không nhầm CSP trên script/API với CSP của trang HTML.
3. Xem `csp-lab.js`, `csp-lab.css` và `csp-ok.svg` có thật sự tải thành công không.
4. Kiểm tra `#external-status`: file JavaScript được phép phải đổi nội dung thành `external ok`.
5. Kiểm tra thuộc tính `document.documentElement.dataset.inlineScript`: không được có giá trị `executed`.
6. Bấm nút inline handler: `dataset.inlineHandler` phải tiếp tục không có giá trị.
7. Ở **Computed Styles**, xem màu của `.inline-style-target`. Chính sách mẫu chặn khối style inline nên màu được khai báo trong tệp CSS ngoài được áp dụng.
8. Bấm hai nút fetch; đối chiếu Network và Console, phân biệt request nội bộ được phép với host ngoài không được phép.
9. Ghi lại browser/version, directive thực sự gây violation và trạng thái `report`/`enforce`.

Một thông báo có thể trông như:

~~~text
Refused to execute inline script because it violates
the following Content Security Policy directive: "script-src 'self'".
~~~

Tuy nhiên, **chuỗi Console không phải giao diện ổn định giữa trình duyệt**. Câu chữ và định dạng thay đổi theo Chromium, Firefox, WebKit hoặc phiên bản. Với test tự động, nên dựa vào hiệu ứng DOM/network và dữ liệu vi phạm có cấu trúc.

### Những suy luận thiếu bằng chứng

- **“Script không chạy, vậy CSP đã chặn.”** Script có thể không chạy vì HTTP 404, JavaScript syntax error, MIME sai hoặc lỗi import.
- **“Trang không bị lỗi, vậy CSP chặt.”** Trang có thể đang dùng Report-Only hoặc policy cho phép cả code đáng tin lẫn code bị chèn.
- **“Có lỗi Failed to fetch, vậy connect-src đã chặn.”** CORS, DNS, TLS, proxy hoặc server có thể là nguyên nhân.
- **“Không có Console warning, vậy không có vi phạm.”** Listener/logging, browser support và cách filter Console có thể khác nhau.

Đó là lý do phép thử cần **đối chứng dương tính, đối chứng âm tính và tín hiệu vi phạm**, không chỉ một quan sát.

## 9. SecurityPolicyViolationEvent: đọc vi phạm dưới dạng dữ liệu

Browser có thể phát sự kiện `securitypolicyviolation` khi một chính sách CSP được đánh giá là bị vi phạm. Listener minh họa:

~~~javascript
document.addEventListener("securitypolicyviolation", event => {
  console.log({
    effectiveDirective: event.effectiveDirective,
    violatedDirective: event.violatedDirective,
    blockedURI: event.blockedURI,
    disposition: event.disposition,
    originalPolicy: event.originalPolicy,
    sourceFile: event.sourceFile,
    lineNumber: event.lineNumber
  });
});
~~~

| Trường | Cung cấp thông tin gì? | Lưu ý khi test |
|---|---|---|
| `effectiveDirective` | Directive thực tế quyết định kiểm tra | Hữu ích khi có `script-src-elem`/`-attr` hoặc fallback |
| `violatedDirective` | Directive được browser báo vi phạm | Có thể khác dạng chuẩn hóa giữa browser |
| `blockedURI` | Đích hoặc kiểu nội dung bị chặn | Không giả định có toàn URL, query hay dữ liệu nhạy cảm |
| `disposition` | `"enforce"` hoặc `"report"` | Phân biệt thực thi và quan sát |
| `originalPolicy` | Chuỗi policy đã tạo vi phạm | Quan trọng nếu response có nhiều CSP |
| `sourceFile`, `lineNumber` | Vị trí nguồn browser cung cấp | Có thể không có hoặc không chính xác |
| `sample` | Mẫu nội dung trong những trường hợp có reporting sample | Có thể rỗng; hạn chế thu dữ liệu nhạy cảm |

**Thời điểm gắn listener rất quan trọng.** Nếu listener được thêm trong file JavaScript `defer`, browser có thể đã gặp khối script inline bị chặn trước đó; sự kiện sớm có thể bị bỏ lỡ. Với ca thử thủ công, đưa listener vào một script ngoài hợp lệ chạy sớm. Với automation, có thể dùng `page.addInitScript` để cài thiết bị đo trước khi trang chạy.

Việc Playwright cài listener bằng browser instrumentation **không chứng minh script instrumentation được CSP cấp phép như script của trang**. Nó chỉ giúp test thu sự kiện; các ca chứng minh source list phải dùng script thực sự tải theo đường ứng dụng.

Ngoài ra, hỗ trợ các trường, tần suất và loại sự kiện có thể khác nhau theo browser/phiên bản. Không yêu cầu một số lượng cố định nếu trang tạo nhiều violation đồng thời.

## 10. Playwright: tự động kiểm thử hành vi script

Playwright có thể điều khiển các browser thật và kiểm tra DOM/network. Ví dụ dùng JavaScript với `@playwright/test`; backend vẫn là Spring Boot Java. Các đoạn sau là **mẫu bài học**, không phải lệnh cần chạy trong STEP 4.

### 10.1. Gắn listener từ trước khi trang tải

~~~javascript
import { test, expect } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    window.__cspEvents = [];

    document.addEventListener("securitypolicyviolation", event => {
      window.__cspEvents.push({
        effectiveDirective: event.effectiveDirective,
        blockedURI: event.blockedURI,
        disposition: event.disposition,
        originalPolicy: event.originalPolicy
      });
    });
  });
});
~~~

`window.__cspEvents` là dữ liệu test được chuẩn bị cho document, **không phải API sản phẩm**. Nếu trang có iframe, route nhiều document hoặc client navigation, cần xác định đúng document và thời điểm sự kiện được thu.

### 10.2. Script ngoài hoạt động, script inline bị chặn

~~~javascript
test("script ngoài chạy, script inline không nonce bị chặn", async ({ page }) => {
  const response = await page.goto("http://localhost:8080/csp-lab");
  expect(response).not.toBeNull();
  expect(response.status()).toBe(200);

  const policy = response.headers()["content-security-policy"];
  expect(policy).toContain("script-src 'self'");

  await expect(page.locator("#external-status")).toHaveText("external ok");

  const inlineExecuted = await page.evaluate(
    () => document.documentElement.dataset.inlineScript
  );
  expect(inlineExecuted).toBeUndefined();

  const violations = await page.evaluate(() => window.__cspEvents);
  expect(violations.some(v =>
    v.effectiveDirective.startsWith("script-src") &&
    v.disposition === "enforce"
  )).toBe(true);
});
~~~

Đây là tổ hợp **positive control + negative control + violation event**. Nó mạnh hơn kiểm tra một mình chuỗi header hoặc chỉ kiểm tra biến không được đặt.

### 10.3. Inline event handler bị chặn

~~~javascript
test("inline onclick bị từ chối", async ({ page }) => {
  await page.goto("http://localhost:8080/csp-lab");

  await page.locator("#inline-button").click();

  const handlerRan = await page.evaluate(
    () => document.documentElement.dataset.inlineHandler
  );
  expect(handlerRan).toBeUndefined();

  const violations = await page.evaluate(() => window.__cspEvents);
  expect(violations.some(v =>
    ["script-src-attr", "script-src"].includes(v.effectiveDirective) &&
    v.disposition === "enforce"
  )).toBe(true);
});
~~~

Ở browser hỗ trợ CSP Level 3, `script-src-attr` điều khiển event handler. Khi directive đó không được hỗ trợ hoặc không có, `script-src` có thể quyết định hành vi theo fallback. Vì vậy test cho phép hai tên directive khi điều tra nhiều browser; bài test bảo mật vẫn đòi hỏi handler **không chạy**.

### 10.4. Fetch được phép và fetch ngoài allowlist

~~~javascript
test("connect-src cho nội bộ và chặn nguồn ngoài", async ({ page }) => {
  await page.goto("http://localhost:8080/csp-lab");

  await page.locator("#same-origin-fetch").click();
  await expect.poll(() => page.evaluate(
    () => document.documentElement.dataset.sameOriginFetch
  )).toBe("ok");

  await page.locator("#outside-fetch").click();
  await expect.poll(() => page.evaluate(
    () => document.documentElement.dataset.outsideFetch
  )).toBe("failed");

  const violations = await page.evaluate(() => window.__cspEvents);
  expect(violations.some(v =>
    v.effectiveDirective === "connect-src" &&
    v.disposition === "enforce"
  )).toBe(true);
});
~~~

Lưu ý: `outsideFetch === "failed"` **không đủ** để khẳng định CSP hoạt động. Host minh họa không có DNS hợp lệ, nên cần violation `connect-src` với `disposition: "enforce"` như test trên.

### 10.5. CSS và ảnh hợp lệ

~~~javascript
test("CSS ngoài và ảnh cùng origin hoạt động", async ({ page }) => {
  await page.goto("http://localhost:8080/csp-lab");

  const color = await page.locator(".inline-style-target")
    .evaluate(element => getComputedStyle(element).color);
  expect(color).toBe("rgb(0, 0, 0)");

  const width = await page.locator("#allowed-image")
    .evaluate(image => image.naturalWidth);
  expect(width).toBeGreaterThan(0);

  const violations = await page.evaluate(() => window.__cspEvents);
  expect(violations.some(v =>
    v.effectiveDirective.startsWith("style-src") &&
    v.disposition === "enforce"
  )).toBe(true);
});
~~~

Màu đen được đặt trong **tệp CSS ngoài**, còn khối inline đặt màu đỏ. Vì vậy computed style cho thấy sự khác biệt khi inline CSS bị chặn. Fixture phải ổn định: nếu stylesheet ngoài bị 404 hoặc một CSS khác ghi đè, test cần điều chỉnh trước khi kết luận.

Tương tự, `naturalWidth > 0` chỉ có ý nghĩa khi file `/images/csp-ok.svg` tồn tại và browser tải thành công. Một `img` trống do 404 không chứng minh `img-src` chặn; muốn kiểm tra ảnh ngoài allowlist, phải xem violation `img-src` riêng.

## 11. Report-Only phải có bài test với kỳ vọng khác enforcement

Đổi header của trang lab sang:

~~~http
Content-Security-Policy-Report-Only: default-src 'none'; script-src 'self'; script-src-attr 'none'; style-src 'self'; img-src 'self'; connect-src 'self'; object-src 'none'; report-uri /_csp/report
~~~

Nếu **không có CSP thực thi khác**:

- Khối script inline có thể chạy dù candidate policy báo vi phạm.
- `onclick` inline có thể chạy và tạo violation `disposition: "report"`.
- Tài nguyên ngoài allowlist có thể được thử tải, dù candidate policy báo vi phạm.
- Browser có thể gửi report bất đồng bộ đến collector, nhưng không bảo đảm mỗi violation tạo đúng một POST.

Ví dụ test trên một môi trường lab riêng, giả định `localhost:8081` chỉ phát CSP Report-Only:

~~~javascript
test("Report-Only ghi nhận nhưng không chặn script", async ({ page }) => {
  const response = await page.goto("http://localhost:8081/csp-lab");

  const reportOnly = response.headers()[
    "content-security-policy-report-only"
  ];
  expect(reportOnly).toContain("script-src 'self'");

  const executed = await page.evaluate(
    () => document.documentElement.dataset.inlineScript
  );
  expect(executed).toBe("executed");

  const events = await page.evaluate(() => window.__cspEvents);
  expect(events.some(v =>
    v.effectiveDirective.startsWith("script-src") &&
    v.disposition === "report"
  )).toBe(true);
});
~~~

`localhost:8081` là một **cấu hình server test riêng phải chuẩn bị trước**, không được Playwright tự tạo. Nếu trang có thêm một CSP thực thi chặn inline, test kỳ vọng script chạy sẽ không đúng; đó là vấn đề môi trường/đường header, không phải lỗi của cơ chế Report-Only.

**Không nên dùng số HTTP POST gửi về collector làm điều kiện bắt buộc cho từng vi phạm.** Reporting có thể bị gộp, giới hạn, gửi muộn hoặc không hỗ trợ ở một browser. Nên test browser theo hành vi và sự kiện; test collector theo integration riêng, rồi có một smoke test reporting end-to-end ở browser mục tiêu khi phù hợp.

## 12. Nonce: kiểm thử sự khớp trong cùng response và tính mới

Test chỉ có:

~~~http
Content-Security-Policy: script-src 'self' 'nonce-REQUEST_VALUE'
~~~

không chứng minh nonce đang hoạt động an toàn. Cần kiểm tra:

1. Nonce thật được sinh ngẫu nhiên mạnh, mới cho **mỗi response HTML cần nonce**.
2. CSP header và thẻ `<script>`/`<style>` tin cậy có **cùng nonce** trong response ấy.
3. Script với nonce khớp chạy, script không có nonce hoặc nonce sai bị chặn.
4. Hai request HTML độc lập có nonce khác nhau với xác suất rất cao.
5. Proxy/cache không dùng lại một HTML có nonce cũ hoặc thay header mà không thay body.

Ví dụ Playwright giả định có route `/csp-nonce-lab` sinh nonce động:

~~~javascript
test("header và HTML cùng nonce; response sau có nonce mới", async ({ page }) => {
  const first = await page.goto("http://localhost:8080/csp-nonce-lab");
  const policyA = first.headers()["content-security-policy"];
  const htmlA = await first.text();

  const matchA = /'nonce-([A-Za-z0-9+/=_-]+)'/.exec(policyA);
  expect(matchA).not.toBeNull();
  const nonceA = matchA[1];
  expect(htmlA).toContain('nonce="' + nonceA + '"');

  // Reload phải thực sự lấy HTTP response mới; kiểm soát cache của route.
  const second = await page.reload();
  const policyB = second.headers()["content-security-policy"];
  const htmlB = await second.text();
  const matchB = /'nonce-([A-Za-z0-9+/=_-]+)'/.exec(policyB);
  expect(matchB).not.toBeNull();

  const nonceB = matchB[1];
  expect(htmlB).toContain('nonce="' + nonceB + '"');
  expect(nonceB).not.toBe(nonceA);
});
~~~

Đây là test **quan hệ header–HTML**; cần thêm test script có nonce **thực sự chạy**, script không nonce bị chặn. Hai CSP thực thi khác nhau có thể khiến script nonce khớp một policy vẫn bị policy còn lại chặn.

**Lưu ý đặc thù DOM:** một số browser che giá trị nonce khi gọi `element.getAttribute("nonce")`; thuộc tính IDL `element.nonce` có thể cho giá trị phù hợp. So sánh với HTML **nguyên response** như trên giúp tránh nhầm với cách trình duyệt biểu diễn thuộc tính.

Với HTML động chứa nonce, nên kiểm soát shared cache. Hai request độc lập không nên nhận lại nguyên một HTML đã cache với nonce cũ; việc quay lại trang bằng *back-forward cache* có thể khôi phục document hiện có chứ không chứng minh server đã gửi response mới.

## 13. Hash: nội dung thực tế phải khớp từng ký tự

Với script cố định:

~~~html
<script>window.appReady = true;</script>
~~~

server có thể khai báo CSP hash:

~~~http
Content-Security-Policy: script-src 'self' 'sha256-ACTUAL_BASE64_DIGEST'
~~~

`ACTUAL_BASE64_DIGEST` là **placeholder**, phải được thay bằng digest Base64 thật của chuỗi `window.appReady = true;`. Hash không gồm thẻ mở/đóng, không phải dạng hex. Khi template formatter, minifier, CDN hoặc build tool thêm whitespace hay đổi code, digest có thể không còn khớp.

| Phép thử | Kết quả cần xác minh trên browser |
|---|---|
| Script inline có nội dung đúng hash | Chạy nếu không có policy khác chặn |
| Nội dung thay đổi mà policy chưa đổi hash | Bị chặn nếu không có cách cho phép khác |
| Hash đặt trong `script-src` nhưng có `script-src-elem` riêng | Phải xem directive thực sự kiểm soát script |
| Hash của `<script>` nhưng `onclick` không được cấp phép | Handler vẫn bị chặn |
| CDN thay nội dung script inline sau build | Có thể gây lỗi CSP trên đường public |

Một server-side integration test có thể băm lại nội dung trong **HTML đã render** và đối chiếu CSP. Nhưng browser test vẫn cần xác minh script thực thi trong ca đúng hash và bị chặn trong ca lệch hash. Chỉ thấy `'sha256-'` trong header không đủ.

## 14. Test đúng loại tài nguyên và directive thực sự có hiệu lực

CSP kiểm soát nhiều nhóm tài nguyên và hành vi khác nhau. Không suy ra từ tên host rằng mọi request đều dùng cùng một directive:

| Hành vi | Directive CSP cần xem | Dấu hiệu browser phù hợp |
|---|---|---|
| `<script src>` | `script-src-elem` → `script-src` → `default-src` | Script chạy/bị từ chối |
| `<script>` inline | `script-src-elem` → `script-src` | Inline code có/không có hiệu ứng |
| `onclick`/`onerror` | `script-src-attr` → `script-src` | Handler chạy/bị từ chối |
| Stylesheet/`<style>` | `style-src-elem` → `style-src` | Computed style |
| `style="..."` | `style-src-attr` → `style-src` | Style attribute có/không hiệu lực |
| `<img>` và CSS background image | `img-src` → `default-src` | Ảnh hiển thị, violation phù hợp |
| Font `@font-face` | `font-src` → `default-src` | Font thực sự tải và được sử dụng |
| `fetch`/XHR | `connect-src` → `default-src` | Violation kết nối + Network |
| WebSocket/SSE/Beacon | `connect-src` → `default-src` | Browser cho/không cho kết nối |
| HTML form submit | `form-action` | Submit đến đích hợp lệ/không hợp lệ |
| `<base href>` | `base-uri` | `document.baseURI` và URL tương đối |
| Iframe tải bởi trang | `frame-src` và fallback tương ứng | Frame xuất hiện/bị chặn |
| Trang bị website khác nhúng | `frame-ancestors` | Trang cha được/không được nhúng |

Lưu ý: `base-uri`, `form-action` và `frame-ancestors` **không tự fallback từ `default-src`**. Vì thế test chỉ kiểm tra `default-src 'none'` không chứng minh các hành vi này bị giới hạn.

### 14.1. WebSocket và SSE

Ví dụ JavaScript:

~~~javascript
const ws = new WebSocket("wss://events.example.net/live");
const events = new EventSource("https://api.example.net/events");
~~~

Hai kết nối thuộc phạm vi `connect-src`. Khi chúng **không** nằm trong allowlist, test nên kiểm tra violation. Khi đã được CSP cho phép, browser vẫn có thể không kết nối do proxy không hỗ trợ WebSocket upgrade, WSS/TLS, CORS của SSE, authentication hoặc server từ chối Origin.

**CSP ở frontend không thay thế kiểm tra Origin trên WebSocket server.** Một website khác không chịu CSP của ứng dụng bạn. Nếu thử cross-site WebSocket hijacking trong lab, kiểm tra quyết định từ server riêng biệt với CSP của trang đang phát kết nối.

### 14.2. Font và canvas

Một CDN font đã được `font-src` cho phép vẫn có thể bị **CORS** chặn. Ảnh cross-origin đã được `img-src` cho phép và hiển thị trên trang vẫn có thể khiến canvas bị *tainted* nếu JavaScript cố đọc pixel mà ảnh không được tải theo chế độ CORS phù hợp.

Test nên tách:

1. CSP cho phép URL tài nguyên hay không.
2. Browser có tải được response HTTP đúng định dạng hay không.
3. CORS/khả năng đọc dữ liệu có được phép hay không.
4. Giao diện/nghiệp vụ đã dùng tài nguyên thành công hay chưa.

## 15. Test form-action và base-uri trên những trang riêng

Hai directive này đặc biệt dễ bị bỏ qua vì chúng không có fallback từ `default-src`.

### 15.1. Form submit

Trang demo:

~~~html
<form id="internal-form" action="/csp-lab/submit" method="post">
  <input name="memo" value="demo">
  <button type="submit">Gửi nội bộ</button>
</form>

<form id="outside-form"
      action="https://outside.example.invalid/submit"
      method="post">
  <input name="memo" value="demo">
  <button type="submit">Gửi ngoài origin</button>
</form>
~~~

Với `form-action 'self'`, browser không được phép submit tới host ngoài allowlist. Kết quả cần được chứng minh bằng **violation `form-action`**, không phải riêng việc browser không điều hướng do host test không tồn tại.

Một nút `<button formaction="...">` có thể thay đích submit so với `action` của form. Nếu sản phẩm dùng thuộc tính này, phải thử cả đích thực sự được chọn.

**CSP không phải CSRF protection.** Một POST cùng origin có thể được CSP cho phép nhưng Spring Security trả HTTP 403 vì thiếu CSRF token. Với test nghiệp vụ hợp lệ, chuẩn bị token và authentication phù hợp, không tắt CSRF toàn ứng dụng chỉ để làm test xanh.

### 15.2. Base URI

Một trang test có:

~~~html
<head>
  <base href="https://outside.example.invalid/assets/">
</head>
<body>
  <a id="relative-link" href="help">Trợ giúp</a>
</body>
~~~

Với `base-uri 'none'`, browser không được dùng base URL của thẻ này. Test nên đọc `document.baseURI`, địa chỉ đã phân giải của liên kết và violation `base-uri`. Không chỉ kiểm tra thẻ `<base>` có mặt trong DOM: CSP có thể từ chối việc **áp dụng** base URL nhưng không xóa phần tử.

Để thử nhất quán, dùng tài liệu chỉ có một thẻ `<base>` cần kiểm tra. Nếu đã có một thẻ base trước đó, việc thêm thẻ khác về sau có thể không ảnh hưởng URL do quy tắc thứ tự của HTML.

## 16. frame-src và frame-ancestors là hai hướng kiểm thử khác nhau

~~~text
Trang A --<iframe src=B>--> Trang B
    frame-src của A kiểm soát A tải B.
    frame-ancestors của B kiểm soát ai được phép nhúng B.
~~~

Nếu trang B trả:

~~~http
Content-Security-Policy: frame-ancestors 'none'
~~~

hãy tạo trang A ở một origin thử nghiệm được kiểm soát và thử nhúng B. Kết quả mong đợi: browser từ chối hiển thị B trong frame theo `frame-ancestors`.

**Thiết kế đối chứng:** nếu trang A đồng thời có `frame-src 'none'`, chính A đã ngăn việc tải iframe trước khi chính sách của B được đánh giá đầy đủ. Muốn đánh giá `frame-ancestors` của B, trang A phải có policy cho phép thử nhúng.

`frame-ancestors` phải được kiểm thử bằng **CSP thực thi**. Không suy rằng việc không thấy report trong Report-Only chứng minh bảo vệ chống clickjacking có hiệu lực.

## 17. Phân biệt CSP với lỗi mạng và các cơ chế Spring Security khác

| Triệu chứng | Dấu hiệu CSP | Những nguyên nhân khác cần kiểm tra |
|---|---|---|
| `fetch` thất bại | `connect-src` violation có `enforce` | CORS, DNS, TLS, server 401/403/500 |
| WebSocket không mở | `connect-src` violation | Upgrade proxy, WSS, Origin, authentication |
| Form POST thất bại | `form-action` violation | CSRF token, quyền, route, server |
| JS không chạy | `script-src` hoặc `script-src-elem` violation | MIME sai, 404, module import lỗi, syntax error |
| Handler không chạy | `script-src-attr` violation | Click không xảy ra, code có lỗi |
| CSS không áp dụng | `style-src` violation | CSS selector, specificity, 404 |
| Font không hiện | `font-src` violation | CORS font, thiếu glyph, file lỗi |
| Ảnh không hiện | `img-src` violation | CDN 404, URL ký hết hạn, file hỏng |
| Iframe trắng | `frame-src`/`frame-ancestors` violation | `X-Frame-Options`, iframe sandbox, HTTP error |
| HTTPS page tải HTTP | Có thể có policy CSP liên quan | Browser chặn mixed content độc lập |

Một vài cơ chế cùng tác động. Ví dụ CSP của HTML có `connect-src 'self'` không cho API bên ngoài, nên dù API CORS đã cấu hình đúng thì browser vẫn không kết nối. Ngược lại, thêm API vào `connect-src` không tự sửa header CORS của API.

Đối với response HTML qua reverse proxy TLS, hãy phân biệt origin công khai của browser với địa chỉ upstream nội bộ. `'self'` được browser xét theo origin của tài liệu đang mở, không phải theo tên container Spring trong mạng nội bộ.

**Không tắt CORS, CSRF, HSTS, cookie/session protection hoặc HTTP firewall để giải quyết một thất bại của bài test CSP.** Cần xác định nguyên nhân thật, sau đó sửa đúng lớp.

## 18. Test qua proxy/CDN: vì sao origin PASS nhưng public FAIL?

Spring Security có thể trả:

~~~http
Content-Security-Policy: script-src 'self' 'nonce-ONE_RESPONSE_NONCE'
~~~

trong khi proxy thêm:

~~~http
Content-Security-Policy: script-src 'self'
~~~

Nếu browser nhận **hai CSP thực thi**, script inline có nonce hợp lệ với policy thứ nhất vẫn có thể bị policy thứ hai chặn. Một test MockMvc chỉ thấy CSP ở Spring sẽ không phát hiện trường hợp này.

| Điểm đo | Phương pháp | Điều cần xác minh |
|---|---|---|
| **Origin** | MockMvc, WebTestClient hoặc HTTP tới upstream trong staging | Header do Spring sinh |
| **Public path** | Playwright, DevTools, HTTP client qua proxy/CDN | Tất cả CSP cuối cùng và body HTML được phục vụ |
| **Cache hit** | GET lặp có kiểm soát, theo dõi cache metadata | HTML và header cùng version, không tái dùng nonce trái thiết kế |
| **Cache miss** | Request qua edge với cache đã kiểm soát | Kết quả nhất quán với origin |
| **Trang lỗi** | 404/500, login, redirect | Trang HTML đích vẫn có bảo vệ phù hợp |

### Hai lỗi cache nonce thường gặp

1. **CDN phát lại toàn bộ header và body** có nonce cũ: script có thể vẫn chạy, nhưng nonce không còn mới cho từng response được phục vụ.
2. **CDN trả body cũ nhưng proxy thay header nonce mới**: thẻ script có nonce cũ không khớp CSP, nên bị từ chối.

Kiểm tra bằng hai **HTTP request HTML mới thật sự**, không dùng việc quay lại trang từ *back-forward cache* rồi suy ra server đã phục vụ response mới.

### ETag và 304

Khi browser nhận `304 Not Modified`, nó có thể kết hợp metadata của response với nội dung đã cache theo quy tắc HTTP. Đừng chỉ đọc response 304 không body rồi kết luận nonce/hash khớp hay không. Cần xác định **HTML thực được browser sử dụng**, policy cuối cùng và cache version.

Với HTML cá nhân hóa có nonce, cân nhắc tránh shared cache bằng cache policy phù hợp (ví dụ `Cache-Control: no-store` khi hệ thống yêu cầu). Với HTML tĩnh và script ngoài hoặc CSP hash cho code cố định, cache thường đơn giản hơn.

### Multiple policies và Report-Only

~~~http
Content-Security-Policy: script-src 'self' https://static.example.net
Content-Security-Policy: script-src 'self'
Content-Security-Policy-Report-Only: script-src 'none'
~~~

Script từ CDN có thể bị chính sách thực thi thứ hai chặn dù chính sách thứ nhất cho. Policy Report-Only chỉ ghi nhận theo phạm vi hỗ trợ. Khi test, cần ghi toàn bộ header và `disposition`, không chỉ lấy một giá trị và giả định “header cuối cùng ghi đè header trước”.

## 19. Tổ chức test CI và giảm trường hợp giả

Nên tách các lớp thử nghiệm theo thời điểm và chi phí:

| Loại test | Khi nào chạy | Điểm quan trọng |
|---|---|---|
| Header unit/integration | Mỗi thay đổi security config | Route HTML, header type, directive |
| Browser smoke | Mỗi frontend build | JS/CSS/ảnh hợp lệ hoạt động, inline bị chặn |
| Browser CSP matrix | Trước rollout chính sách | Các directive và nhiều trình duyệt |
| Nonce/hash contract | Khi đổi SSR/template/build/cache | Header–body cùng response; nonce mới; hash đúng |
| Proxy/CDN integration | Trên staging trước production | CSP cuối cùng, 200/302/404/304, cache |
| Luồng nghiệp vụ E2E | Trước/sau enforcement | Login, checkout, upload, API, SSO |

Playwright có thể cấu hình các engine Chromium, Firefox, WebKit cho những browser mà sản phẩm hỗ trợ. Tuy nhiên, **độ hỗ trợ của CSP Level 3, Reporting API và chi tiết sự kiện có thể khác nhau**. Không giả định một test PASS trên Chromium đại diện mọi browser.

Để giảm flaky test:

- Dùng fixture tài nguyên và endpoint do nhóm phát triển quản lý; không phụ thuộc CDN công khai để kiểm tra positive control.
- Không assert nguyên văn chuỗi Console hoặc thứ tự các sự kiện violation khi trang tải song song.
- Không dùng sleep cố định thay cho việc chờ trạng thái DOM, request hoặc sự kiện.
- Không yêu cầu collector nhận đúng một POST với mỗi violation vì báo cáo có thể gửi bất đồng bộ hoặc bị gộp.
- Thiết lập test data và quyền truy cập phù hợp; không dùng tài khoản sản xuất hoặc dữ liệu nhạy cảm thật.
- Test nonce phải kiểm soát cache và đọc đúng HTTP response mới.
- Đặt tên test theo bằng chứng thật, ví dụ `blocksUnapprovedInlineScript`, không đặt `preventsEveryXss`.
- Khi test frame/cross-origin/WebSocket, dùng môi trường test nhiều origin có cấu hình rõ ràng.

## 20. Chẩn đoán test sai và điều chỉnh đúng nguyên nhân

| Kết quả quan sát | Nguy cơ kết luận sai | Cách kiểm chứng lại |
|---|---|---|
| Header chứa `script-src 'self'` | Tưởng inline chắc chắn bị chặn | Đo DOM và violation thực thi |
| Script không chạy | Tưởng CSP đã bảo vệ | Kiểm tra request JS, 404, syntax, MIME và Console |
| Fetch ngoài thất bại | Tưởng do `connect-src` | Kiểm tra `effectiveDirective` và `disposition` |
| Ảnh ngoài không hiển thị | Tưởng do `img-src` | Kiểm tra CSP event và Network |
| Listener không nhận event | Tưởng không có vi phạm | Đăng ký sớm; kiểm tra browser support |
| Report-Only báo vi phạm | Tưởng đã chặn | Test hiệu ứng và enforced CSP riêng |
| CSP collector không nhận POST | Tưởng policy không hoạt động | Kiểm tra collector, báo cáo async, browser support |
| Nonce đúng với một header | Tưởng script chắc chắn chạy | Kiểm tra CSP thứ hai và thực thi browser |
| Back navigation giữ nonce cũ | Tưởng CDN dùng lại nonce | Phân biệt bfcache với HTTP reload |
| CSS inline không làm đổi giao diện | Tưởng style bị chặn | Dùng computed style đối chứng và violation |
| Form cùng origin trả 403 | Tưởng `form-action` chặn | Kiểm tra CSRF/authorization ở server |
| Origin test PASS, public FAIL | Tưởng Spring code sai | Kiểm tra proxy, CDN, cache và error page |
| Trên một browser PASS | Tưởng đã đủ hỗ trợ | Thử browser mục tiêu khác |
| Nhiều report từ URL lạ | Tưởng cần thêm domain vào CSP | Xác minh tính năng, extension và độ tin cậy nguồn |

### Quy trình debug bốn bước

1. **Xác định hành vi:** mã không chạy, request thất bại, trang không hiển thị hay luồng nghiệp vụ lỗi?
2. **Đọc nguyên nhân có cấu trúc:** `effectiveDirective`, `disposition`, status HTTP, lỗi Console và network.
3. **Chọn đối chứng:** cùng loại tài nguyên ở nguồn được cấp phép có hoạt động không?
4. **Theo đường response:** HTML, security chain, proxy, cache, trình duyệt và phiên bản policy nào tạo kết quả?

Chỉ sau đó quyết định sửa code, CSP source list, cấu hình API hay hạ tầng. Đặc biệt không tự động thêm domain xuất hiện trong violation vào allowlist.

## 21. Mẫu báo cáo kết quả kiểm thử bảo mật

Để kiểm tra có thể review, báo cáo nên ghi rõ môi trường và bằng chứng:

| Trường | Ví dụ |
|---|---|
| Route | `GET /csp-lab` |
| Môi trường | Staging qua reverse proxy |
| Browser | Chromium bản CI đã cấu hình |
| CSP thực thi | `script-src 'self'; script-src-attr 'none'` |
| Report-Only | Không hoặc phiên bản candidate riêng |
| Đối chứng dương tính | JS cùng origin đặt `external-status = external ok` |
| Đối chứng âm tính | Script inline không đặt `dataset.inlineScript` |
| CSP violation | `script-src-elem`/`script-src`, `disposition: "enforce"` |
| Kết quả API nội bộ | GET ping HTTP 200, giao diện đổi trạng thái |
| Kết luận | PASS cho **các hành vi đã định nghĩa**, không bảo đảm chống mọi XSS |

Nếu FAIL, ghi thêm header CSP cuối cùng, URL route, browser/version, resource/network status, chính sách nào đã chặn và khác biệt giữa origin/public path. Không log token, cookie, thông tin cá nhân hoặc toàn bộ query string không cần thiết.

**Một browser test PASS không chứng minh toàn bộ hệ thống an toàn:** JavaScript được cấp phép vẫn có thể chứa DOM XSS, endpoint cùng origin có thể thiếu authorization, và các kênh khác (ảnh, form, iframe) có thể cần directive riêng. CSP phải được kết hợp với kiểm tra code, escape/sanitize HTML, CORS, CSRF, HSTS, HTTP firewall và session protection.

## 22. Bài thực hành tổng hợp

**Bối cảnh:** Một dashboard Spring Boot có test header CSP PASS, nhưng production đôi lúc chặn script và đôi lúc không. Hãy dùng trình duyệt thật để tìm nguyên nhân và chứng minh chính sách.

1. Dựng `/csp-lab` với script ngoài, script inline, handler inline, CSS ngoài/inline, ảnh hợp lệ và nút fetch.
2. Cấu hình CSP thực thi qua Spring Security **Servlet**, rồi tạo cấu hình tương đương bằng **WebFlux**. Không tắt CSRF/CORS/session.
3. Viết MockMvc/WebTestClient kiểm tra header của route HTML và giải thích test header chưa đủ.
4. Mở DevTools, ghi lại hiệu ứng của từng loại tài nguyên và violation tương ứng.
5. Dùng Playwright tự động xác nhận script ngoài chạy, inline script/handler bị chặn, fetch nội bộ thành công và fetch ngoài allowlist tạo violation.
6. Tạo môi trường Report-Only riêng; so sánh `disposition: "report"` với `"enforce"` và kết quả script inline.
7. Thêm trang nonce động; đọc header và HTML của **cùng response** và kiểm tra hai HTTP response độc lập có nonce khác nhau.
8. Tạo script inline cố định với CSP hash; sửa whitespace mà chưa cập nhật hash để tạo ca âm tính.
9. Thử `form-action`/`base-uri` trên trang riêng. Phân biệt form submit bị CSP chặn với POST trả 403 do CSRF.
10. Thử iframe hoặc WebSocket nếu hệ thống có tính năng liên quan; kiểm tra cả chính sách browser và quyết định của server.
11. Chạy đường public qua proxy/CDN test, tạo tình huống hai CSP thực thi hoặc cache body/header nonce không đồng bộ và xác định vì sao origin test không phát hiện.
12. Tạo bảng báo cáo với browser, header thực nhận, hành vi, sự kiện CSP và kết quả E2E của các chức năng quan trọng.

### Câu hỏi tự đánh giá

1. Vì sao assertion `containsString("script-src 'self'")` chưa chứng minh script inline bị chặn?
2. Một script không chạy có thể do những lỗi nào ngoài CSP?
3. Vì sao test cần cả script cùng origin chạy và script inline không được phép bị từ chối?
4. `SecurityPolicyViolationEvent` có những trường nào giúp phân biệt enforcing với Report-Only?
5. Vì sao listener đăng ký muộn có thể bỏ lỡ vi phạm lúc parser xử lý HTML?
6. Vì sao một host không tồn tại không phải đối chứng đủ mạnh cho `connect-src`?
7. Khi `script-src-attr` vắng hoặc không được browser hỗ trợ, directive nào có thể đóng vai trò fallback?
8. Vì sao khi test nonce phải so sánh header và body của **cùng HTTP response**?
9. Back/forward cache có khác HTTP cache hit như thế nào trong bài test nonce?
10. Hash của script inline có thể mất khớp sau build/minify vì nguyên nhân gì?
11. `form-action` có thay thế CSRF token không? Vì sao?
12. `frame-src` và `frame-ancestors` kiểm soát hai hướng nhúng khác nhau như thế nào?
13. Vì sao không bắt buộc collector phải nhận đúng một report cho mỗi vi phạm?
14. Khi origin PASS nhưng browser qua CDN FAIL, cần kiểm tra những tầng nào?
15. Một CSP thực thi thứ hai có thể từ chối script được policy thứ nhất cho phép không?
16. Vì sao test trên một browser không đủ để kết luận CSP Level 3 hoạt động trên mọi browser?

## 23. Ghi nhớ

**Kiểm tra chuỗi CSP header là cần thiết, nhưng không đủ.** Một bài kiểm thử CSP đáng tin phải chứng minh **tài nguyên hợp lệ hoạt động, hành vi không được cấp phép bị browser từ chối và chính sách thật sự nằm trên response HTML**. Hãy kết hợp MockMvc/WebTestClient với DevTools, `SecurityPolicyViolationEvent`, Playwright và kiểm thử nghiệp vụ. Violation có `disposition: "report"` chỉ cho biết quan sát; test enforcement phải xác nhận hành vi bị chặn thật.

Khi dùng nonce/hash, kiểm tra **header và HTML của cùng response**, sau đó xác minh hành vi browser. Khi có reverse proxy/CDN hoặc nhiều CSP, hãy test **đường public cuối cùng** và cache, không chỉ cấu hình Spring. Phân biệt CSP với CORS, CSRF, authentication, DNS, HTTPS/HSTS và lỗi HTTP. Trong `SPRING_SECURITY_HTTP_PROTECTION`, CSP là lớp giảm thiểu rủi ro cần đi cùng xử lý HTML an toàn, HTTP firewall và bảo vệ session, không phải bằng chứng rằng mọi kiểu XSS đều đã bị loại trừ.
