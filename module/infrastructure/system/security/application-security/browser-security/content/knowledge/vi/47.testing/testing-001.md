# Browser security test

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Xây dựng chiến lược kiểm thử bảo mật cho ứng dụng chạy trong browser dựa trên threat model và ranh giới tin cậy.
- Phân biệt kiểm thử unit, integration, browser automation và kiểm thử thủ công trên browser thật.
- Thiết kế test case cho Same-Origin Policy, CORS, cookie, CSRF, XSS, CSP, Trusted Types và clickjacking.
- Kiểm tra storage partitioning, service worker, cache, Referrer-Policy, MIME type, download và các security headers.
- Dùng Playwright để xác minh hành vi thực tế của browser thay vì chỉ kiểm tra cấu hình server.
- Tạo test fixture nhiều origin, HTTPS và tài khoản riêng biệt để kiểm thử cross-site có thể lặp lại.
- Đưa browser security test vào CI, xử lý khác biệt giữa browser engine và báo cáo kết quả có bằng chứng.

## 1. Vì sao cần browser security test?

Một ứng dụng có thể vượt qua unit test và API test nhưng vẫn có lỗ hổng khi chạy trong browser. Browser thực thi nhiều chính sách ở phía client: Same-Origin Policy (SOP), CORS, cookie SameSite, CSP, mixed content, MIME handling, storage partitioning, sandbox iframe, navigation và download policy. Hành vi cuối cùng còn phụ thuộc browser engine, phiên bản, cấu hình privacy và ngữ cảnh top-level site.

Ví dụ, backend có thể trả response đúng nhưng browser không cho JavaScript đọc vì CORS. Cookie có thể tồn tại ở server nhưng browser không gửi vì `SameSite`, `Secure`, third-party cookie restriction hoặc partition key. Một response có `Content-Type` sai có thể bị browser xử lý khác với dự kiến. Một trang có `frame-ancestors` đúng có thể bị cấu hình CDN ghi đè. Chỉ kiểm tra header trong source code không chứng minh browser nhận và thực thi policy đó.

Browser security test xác minh các thuộc tính bảo mật tại đúng điểm người dùng tương tác: document, frame, request, response, cookie, storage, navigation và script execution. Test cần trả lời được câu hỏi: “Một trang hoặc script không đáng tin có thể đọc, thay đổi hoặc kích hoạt hành động nào trong ngữ cảnh browser này?”.

Mục tiêu không phải tạo thật nhiều test case rời rạc. Hãy xác định các tài sản cần bảo vệ, các origin và frame tham gia, dữ liệu có thể đi qua ranh giới nào, sau đó viết test chứng minh ranh giới đó được browser thực thi.

## 2. Bắt đầu từ threat model và security invariant

Trước khi viết test, mô tả tài sản, attacker capability và điều kiện cần đúng.

| Tài sản | Ranh giới cần kiểm tra | Security invariant mẫu |
| --- | --- | --- |
| Session cookie | Browser ↔ application origin | Cookie xác thực có `Secure`, `HttpOnly`, `SameSite` phù hợp và chỉ được gửi trong ngữ cảnh dự kiến. |
| Dữ liệu API cá nhân | Origin A ↔ origin B | Origin không được phép không đọc được response qua browser. |
| Thao tác thay đổi dữ liệu | Cross-site form/navigation ↔ application | Request không có CSRF proof hợp lệ không làm thay đổi trạng thái. |
| Nội dung người dùng | Data ↔ HTML/JavaScript parser | Payload không tin cậy hiển thị như dữ liệu và không thực thi script. |
| Trang tài khoản | Document ↔ iframe không tin cậy | Trang không được nhúng trong frame ngoài allowlist. |
| Access token và URL | Document ↔ navigation/referrer/telemetry | Credential không xuất hiện trong referrer, log hoặc telemetry. |
| Response riêng tư | Browser cache/CDN/service worker | Dữ liệu của user A không được phục vụ lại cho user B. |
| File upload/download | Client ↔ parser/browser | MIME type và nội dung được kiểm tra; file không tin cậy không chạy trong origin ứng dụng. |
| Extension bridge | Page ↔ content script/service worker | Page không thể dùng message giả để gọi API extension đặc quyền. |

Một security invariant nên mô tả hành vi có thể quan sát và kết quả mong đợi. Ví dụ “CORS an toàn” quá chung. Một invariant tốt hơn là “JavaScript tại `https://attacker.test` không đọc được body của `/api/private` trên `https://api.example.test` khi server không cấp CORS cho attacker origin”.

### 2.1. Phân loại attacker

Browser test nên nêu rõ attacker đang có khả năng nào:

- Người dùng truy cập một website độc hại trong tab khác.
- Trang bên thứ ba được nhúng trong iframe.
- Script cùng origin bị XSS hoặc dependency bị xâm nhập.
- Người dùng upload file có nội dung không tin cậy.
- Extension có quyền đọc trang hoặc tương tác với tab.
- Một client gửi HTTP request trực tiếp, không chịu các giới hạn của browser.

Không trộn các mô hình này. CORS bảo vệ khả năng JavaScript đọc response cross-origin, nhưng không ngăn client ngoài browser gọi endpoint. CSRF kiểm tra request được gửi bằng credential của browser, nhưng không thay authorization. Isolated world của extension không làm DOM trở nên đáng tin.

## 3. Các tầng kiểm thử

Nên phối hợp nhiều tầng vì mỗi tầng bắt được một nhóm lỗi khác nhau.

| Tầng | Kiểm tra gì | Ví dụ |
| --- | --- | --- |
| Unit test | Hàm tạo policy, parser, URL allowlist và schema validation. | Hàm từ chối `javascript:` URL hoặc cấu hình cookie thiếu `Secure`. |
| Server integration test | Middleware, response header, CSRF validation, authorization và cache policy. | API trả `Cache-Control: no-store` và từ chối request thiếu CSRF token. |
| Browser automation | Browser thực thi SOP/CORS, cookie, CSP, iframe, navigation, storage và download. | Page từ origin khác không đọc được response; iframe bị chặn bởi `frame-ancestors`. |
| Cross-browser test | Khác biệt giữa Chromium, Firefox và WebKit/Safari. | SameSite, third-party storage, partitioning và permission behavior. |
| Manual security test | Luồng phức tạp, cấu hình privacy, extension, permission prompt và UI thực tế. | Kiểm tra Storage Access API prompt hoặc extension content script trên browser mục tiêu. |
| Production monitoring | Policy drift và lỗi sau deploy. | CSP reports, CORS failure rate, cookie blocked metrics và browser error telemetry. |

Unit test có thể chứng minh hàm tạo header trả chuỗi đúng, nhưng không chứng minh CDN không ghi đè header hoặc browser thực sự chặn iframe. Browser automation cần xác minh hành vi từ trang đã tải qua HTTP/HTTPS thật trong môi trường test.

## 4. Dựng môi trường test nhiều origin

Các test cross-origin cần ít nhất hai origin khác nhau. Để kiểm tra SameSite, third-party cookie và storage partitioning, cần phân biệt thêm same-site với cross-site.

Ví dụ sơ đồ hostname dành cho môi trường local/staging:

```text
https://app.example.test       Ứng dụng chính
https://api.example.test       API: khác origin nhưng cùng site với app
https://attacker.test          Trang không tin cậy: khác site
https://widget.vendor.test     Iframe/widget bên thứ ba
https://cdn.example.test       Tài nguyên tĩnh/CDN giả lập
```

`app.example.test` và `api.example.test` khác origin vì host khác nhau, nhưng thường cùng schemeful site vì cùng scheme và registrable domain `example.test`. `attacker.test` là site khác. Cần dùng HTTPS với certificate test hợp lệ để kiểm tra `Secure` cookie, `SameSite=None`, mixed content và các API yêu cầu secure context.

Không dựa vào `localhost` cho mọi bài test cross-site. `localhost` có quy tắc secure-context đặc biệt và không đại diện đầy đủ cho cookie/site behavior trên domain production. Dùng DNS/hosts entry dành riêng cho test, certificate có SAN phù hợp và không trỏ hostname thử nghiệm đến production.

### 4.1. Cô lập trạng thái giữa test

Mỗi test nên có browser context riêng hoặc storage state được tạo có chủ đích. Không dùng chung session giữa các test không liên quan. Khi test đổi tài khoản, cần chứng minh dữ liệu A không còn xuất hiện trong session B.

Các nguyên tắc:

- Tạo context mới cho test độc lập.
- Tạo user/tenant fixture riêng và xóa dữ liệu test sau khi hoàn tất.
- Không dùng cookie, token hoặc dữ liệu cá nhân production.
- Đặt thời gian hết hạn và cleanup cho signed URL, file và job test.
- Tắt hoặc kiểm soát service worker khi test không liên quan; bật rõ ràng khi test service worker.
- Cố định browser version trong CI, đồng thời có lịch chạy trên browser stable mới.

## 5. Thiết lập Playwright cho browser security test

Playwright cho phép chạy test trên Chromium, Firefox và WebKit. Mỗi project có thể dùng browser engine và cấu hình riêng. Tên engine không đồng nghĩa với mọi browser branding/version; cần kiểm thử trên browser mà sản phẩm hỗ trợ khi có khác biệt về privacy hoặc policy.

Ví dụ `playwright.config.ts`:

```ts
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/browser-security",
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: true,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "html" : "list",
  use: {
    baseURL: "https://app.example.test",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off"
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } }
  ]
});
```

Trong CI, cài browser dependencies và tin cậy certificate của test CA theo cách quản trị của môi trường. Không bật `ignoreHTTPSErrors: true` cho toàn bộ security suite vì thao tác đó che lỗi certificate. Nếu một test cần certificate lỗi để kiểm tra cảnh báo, hãy cô lập cấu hình đó trong test riêng.

Trace, screenshot và video có thể chứa URL, cookie, form value và nội dung cá nhân. Chỉ bật artifact cần thiết, dùng tài khoản test, giới hạn quyền truy cập và retention; không đính kèm artifact thô vào ticket công khai.

### 5.1. Browser context và API request

Playwright `browser.newContext()` tạo môi trường browser cô lập về cookie/storage. `page.request` hoặc `context.request` có thể chia sẻ cookie jar với context theo cách Playwright quy định, nhưng APIRequestContext không mô phỏng đầy đủ chính sách bảo mật của JavaScript trong browser. Khi kiểm tra SOP/CORS, phải thực hiện `fetch()` từ `page.evaluate()` trong trang có origin phù hợp.

Không dùng `request.get()` để kết luận CORS đã được browser thực thi. API request trực tiếp không bị giới hạn bởi CORS theo cùng cách JavaScript trong document.

## 6. Kiểm thử Same-Origin Policy và CORS

### 6.1. Kiểm thử SOP

SOP giới hạn việc một document đọc dữ liệu từ document/origin khác. Một test nên chứng minh trang attacker không thể đọc nội dung của cửa sổ app cross-origin.

Ví dụ Playwright:

```ts
import { test, expect } from "@playwright/test";

test("cross-origin page cannot read the app document", async ({ page }) => {
  await page.goto("https://attacker.test/blank");

  const result = await page.evaluate(() => new Promise<string>((resolve) => {
    const frame = document.createElement("iframe");
    frame.onload = () => {
      try {
        resolve(frame.contentWindow!.document.body.textContent ?? "");
      } catch (error) {
        resolve(error instanceof DOMException ? error.name : "unexpected-error");
      }
    };
    frame.src = "https://app.example.test/private";
    document.body.append(frame);
  }));

  expect(result).toBe("SecurityError");
});
```

Test dùng iframe để tránh phụ thuộc popup blocker. Fixture app phải tải được trong frame; nếu app chủ động chặn framing bằng CSP, hãy kiểm tra SOP bằng fixture document riêng không có `frame-ancestors` để tách hai policy. Kết quả cần thể hiện attacker không đọc được DOM cross-origin; việc điều hướng đến trang khác hoặc gửi request không đồng nghĩa được phép đọc response.

### 6.2. CORS deny test

Khi server không cấp CORS cho origin attacker, JavaScript fetch mặc định ở mode `cors` phải bị reject khi cố đọc response. Request vẫn có thể đến server; CORS không phải firewall.

```ts
test("untrusted origin cannot read private API response", async ({ page }) => {
  await page.goto("https://attacker.test/blank");

  const outcome = await page.evaluate(async () => {
    try {
      const response = await fetch("https://api.example.test/private");
      await response.text();
      return "readable";
    } catch (error) {
      return error instanceof TypeError ? "cors-blocked" : "other-error";
    }
  });

  expect(outcome).toBe("cors-blocked");
});
```

Đảm bảo endpoint test không trả `Access-Control-Allow-Origin: https://attacker.test`. Không dùng `mode: "no-cors"` trong test này vì response opaque không kiểm tra được body và sẽ kiểm tra một hành vi khác.

### 6.3. CORS allow test và credentialed CORS

Khi origin được allowlist, browser có thể cho JavaScript đọc response. Với credentialed CORS, server phải trả origin cụ thể, `Access-Control-Allow-Credentials: true` và header/method cần thiết; wildcard origin không dùng được.

```ts
test("approved origin can read credentialed API response", async ({ page, context }) => {
  await context.addCookies([{
    name: "api_session",
    value: "test-session-only",
    url: "https://api.example.test",
    httpOnly: true,
    secure: true,
    sameSite: "Lax"
  }]);

  await page.goto("https://app.example.test/test-harness");

  const result = await page.evaluate(async () => {
    const response = await fetch("https://api.example.test/private", {
      credentials: "include"
    });
    return {
      status: response.status,
      body: await response.json()
    };
  });

  expect(result.status).toBe(200);
  expect(result.body).toMatchObject({ owner: "test-user" });
});
```

Fixture server cho API phải trả `Access-Control-Allow-Origin: https://app.example.test`, `Access-Control-Allow-Credentials: true` và `Vary: Origin`. Hai host `app.example.test` và `api.example.test` khác origin nhưng cùng site, nên ví dụ này giảm phụ thuộc vào third-party cookie blocking. Test phải dùng dữ liệu giả.

### 6.4. Preflight

Kiểm tra cả `OPTIONS` preflight và request thực tế. Một test có thể theo dõi request:

```ts
test("preflight permits only the expected method and headers", async ({ page }) => {
  const methods: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/report")) methods.push(request.method());
  });

  await page.goto("https://app.example.test/test-harness");
  await page.evaluate(async () => {
    await fetch("https://api.example.test/api/report", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Report-Mode": "test"
      },
      body: JSON.stringify({ sample: true })
    });
  });

  expect(methods).toContain("OPTIONS");
  expect(methods).toContain("POST");
});
```

Test này giả định API cho phép `POST` và header `X-Report-Mode` từ app origin. Thêm test âm tính cho method/header không được phép; xác nhận browser không gửi actual request sau khi preflight thất bại. Cấu hình server phải giới hạn origin, method và header, không phản chiếu mọi giá trị request.

## 7. Kiểm thử cookie và session

Cookie test cần xác minh cả thuộc tính do server phát hành lẫn hành vi browser gửi cookie trong từng ngữ cảnh.

### 7.1. Thuộc tính cookie

Ví dụ sau đăng nhập vào fixture và kiểm tra cookie session:

```ts
test("session cookie has required security attributes", async ({ page, context }) => {
  await page.goto("https://app.example.test/login");
  await page.getByLabel("Username").fill("browser-test-user");
  await page.getByLabel("Password").fill("test-password");
  await page.getByRole("button", { name: "Sign in" }).click();

  const cookies = await context.cookies("https://app.example.test");
  const session = cookies.find((cookie) => cookie.name === "__Host-session");

  expect(session).toBeDefined();
  expect(session?.httpOnly).toBe(true);
  expect(session?.secure).toBe(true);
  expect(session?.sameSite).toBe("Lax");

  const visibleToPage = await page.evaluate(() => document.cookie);
  expect(visibleToPage).not.toContain("__Host-session=");
});
```

`context.cookies()` dùng để kiểm tra metadata cookie trong test; không log giá trị cookie ra report. Giá trị `SameSite` cần khớp thiết kế của luồng login/SSO. Nếu dùng `SameSite=None`, cookie phải `Secure`, nhưng browser vẫn có thể hạn chế third-party cookie theo policy.

### 7.2. SameSite và cross-site navigation

Kiểm tra cookie trong các ngữ cảnh:

- Request same-origin từ app đến API.
- Request cross-origin nhưng same-site giữa hai subdomain HTTPS.
- Form POST hoặc Fetch cross-site từ `attacker.test`.
- Top-level GET navigation từ site khác.
- Iframe third-party.

Không kết luận chỉ từ `document.cookie`: cookie `HttpOnly` không xuất hiện ở đây nhưng browser vẫn có thể gửi cookie. Dùng Network panel hoặc endpoint test chỉ ghi nhận boolean “cookie received” thay vì log giá trị.

### 7.3. Session rotation và logout

Test đăng nhập cần xác minh session ID được rotate sau authentication hoặc privilege change theo thiết kế. Logout phải thu hồi session phía server, hết hạn cookie và khiến request tiếp theo bị từ chối. Kiểm tra cả tab khác và Back/Forward restore.

Không chỉ assert rằng cookie bị xóa ở browser. Một cookie cũ có thể được sao chép hoặc request đã có thể được gửi; server phải từ chối session đã revoke.

## 8. Kiểm thử CSRF

CSRF test cần mô phỏng một site khác khiến browser gửi request có credential đến ứng dụng. Chọn endpoint test có side effect giả, ví dụ thay đổi một preference của test user.

Các lớp cần kiểm tra:

- Token CSRF khó đoán, ràng buộc với session và được xác minh server-side.
- `Origin`/`Referer` validation cho các request thay đổi trạng thái khi phù hợp.
- Fetch Metadata như `Sec-Fetch-Site` có thể bổ sung tín hiệu phòng vệ.
- Cookie `SameSite` giảm một số request cross-site nhưng không thay thế token và authorization.
- GET không thực hiện thao tác thay đổi trạng thái.
- CORS không phải CSRF protection; form cross-site vẫn có thể gửi một số request dù attacker không đọc được response.

Ví dụ test khái quát: đăng nhập một test user với cookie `SameSite=None; Secure` để bảo đảm browser có thể gửi cookie trong lab cross-site, mở trang `attacker.test` có form POST đến endpoint đổi preference, rồi xác nhận server từ chối do thiếu CSRF proof và trạng thái không đổi. Việc cố ý dùng `SameSite=None` trong fixture giúp kiểm tra lớp token/Origin độc lập; production cookie có thể dùng policy chặt hơn.

```ts
test("cross-site form cannot change account preference", async ({ page, context }) => {
  await context.addCookies([{
    name: "csrf-lab-session",
    value: "test-session-only",
    url: "https://app.example.test",
    secure: true,
    httpOnly: true,
    sameSite: "None"
  }]);

  await page.goto("https://attacker.test/csrf-form");
  await page.getByRole("button", { name: "Submit test form" }).click();

  await expect(page).toHaveURL(/csrf-rejected/);
  await expect(page.getByText("Request rejected")).toBeVisible();
});
```

Fixture `csrf-form` gửi form POST đến app endpoint. Server phải trả trang từ chối và không thay đổi state. Kiểm tra trạng thái bằng một request test có authorization hoặc bằng database assertion ở integration test. Không dùng thao tác thanh toán, xóa dữ liệu hay thay đổi tài khoản thật làm CSRF fixture.

## 9. Kiểm thử XSS và DOM injection

Browser test nên kiểm tra kết quả render, không chỉ kiểm tra sanitizer function. Payload test dùng sentinel vô hại để phát hiện script có thực thi hay không.

Ví dụ:

```ts
test("user content is rendered as text, not executable HTML", async ({ page }) => {
  await page.addInitScript(() => {
    (window as any).__xssExecuted = false;
  });

  await page.goto("https://app.example.test/comments");
  const payload = '<img src="/missing" onerror="window.__xssExecuted=true">';

  await page.getByLabel("Comment").fill(payload);
  await page.getByRole("button", { name: "Post comment" }).click();

  const comment = page.locator("[data-testid='comment']").last();
  await expect(comment).toHaveText(payload);
  await expect(comment.locator("img")).toHaveCount(0);
  expect(await page.evaluate(() => (window as any).__xssExecuted)).toBe(false);
});
```

Test này giả định ứng dụng hiển thị comment dưới dạng text. Nếu nghiệp vụ hỗ trợ rich text, hãy định nghĩa allowlist HTML rõ ràng và kiểm tra các element/attribute được phép; không chỉ assert rằng mọi HTML đều bị loại bỏ.

Các sink cần rà soát:

- `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`.
- `eval`, `new Function`, string-based timer và dynamic script URL.
- URL trong `href`, `src`, `action`, CSS và navigation.
- Template render, Markdown renderer, SVG và nội dung từ third-party API.

Test cần bao gồm cả reflected, stored và DOM-based XSS theo luồng dữ liệu thực tế. Browser automation không chứng minh không có XSS ở mọi input; kết hợp static analysis, code review, sanitizer tests và security regression tests.

## 10. Kiểm thử CSP và Trusted Types

### 10.1. CSP enforcement

Tạo endpoint test trả HTML có inline script không có nonce, trong khi response có CSP không cho inline script. Dùng `addInitScript` để đặt sentinel và lắng nghe `securitypolicyviolation` trước khi trang chạy.

```ts
test("CSP blocks an inline script without an approved nonce", async ({ page }) => {
  await page.addInitScript(() => {
    (window as any).__inlineRan = false;
    (window as any).__cspViolation = false;
    document.addEventListener("securitypolicyviolation", () => {
      (window as any).__cspViolation = true;
    });
  });

  await page.goto("https://app.example.test/security/csp-inline-fixture");

  expect(await page.evaluate(() => (window as any).__inlineRan)).toBe(false);
  expect(await page.evaluate(() => (window as any).__cspViolation)).toBe(true);
});
```

Fixture cần có inline script đặt `window.__inlineRan = true` và header CSP không cho phép script đó. Không dùng `unsafe-inline` trong fixture. Nếu kiểm thử nonce, xác minh nonce được tạo mới cho response và chỉ script được cấp nonce mới chạy.

### 10.2. Report-Only và enforcing policy

`Content-Security-Policy-Report-Only` dùng để quan sát violation mà chưa chặn nội dung. Test cần phân biệt report-only với policy enforcing. Khi rollout, xác minh report đến đúng endpoint, không chứa dữ liệu nhạy cảm ngoài mức cần thiết và không bị spam bởi tài nguyên không liên quan.

### 10.3. Trusted Types

Trusted Types giúp bảo vệ một số DOM injection sink trong browser hỗ trợ. Với policy `require-trusted-types-for 'script'`, các sink như `innerHTML` yêu cầu TrustedHTML thay vì chuỗi tùy ý. Đây là lớp giảm rủi ro DOM XSS, không thay thế sanitizer và safe DOM APIs.

Ví dụ test chỉ chạy trên engine có hỗ trợ Trusted Types:

```ts
test("Trusted Types rejects a raw string at an HTML injection sink", async ({ page, browserName }) => {
  test.skip(browserName !== "chromium", "Trusted Types support is checked in Chromium project");
  await page.goto("https://app.example.test/security/trusted-types-fixture");

  const result = await page.evaluate(() => {
    try {
      document.body.innerHTML = "<p>untrusted</p>";
      return "accepted";
    } catch (error) {
      return error instanceof TypeError ? "rejected" : "other-error";
    }
  });

  expect(result).toBe("rejected");
});
```

Không đánh dấu test Trusted Types là pass trên browser không hỗ trợ chỉ vì test được skip. Báo cáo riêng “unsupported/skipped” và duy trì test tương đương cho safe DOM handling ở mọi browser mục tiêu.

## 11. Kiểm thử clickjacking và iframe policy

Trang nhạy cảm có thể đặt `Content-Security-Policy: frame-ancestors 'none'` hoặc allowlist ancestor cụ thể. Test cần thử nhúng trang từ origin không được phép và xác nhận nội dung nhạy cảm không hiển thị trong frame.

Ví dụ test:

```ts
test("account page cannot be framed by an untrusted site", async ({ page }) => {
  await page.goto("https://attacker.test/frame-lab");

  const protectedFrame = page.frameLocator("iframe#target");
  await expect(protectedFrame.locator("[data-testid='account-balance']")).toHaveCount(0);
});
```

Fixture `frame-lab` nhúng `https://app.example.test/account` trong iframe. Response app cần trả CSP `frame-ancestors 'none'` hoặc policy không cho phép attacker origin. Nếu app chủ động render trang lỗi trong iframe, test phải xác nhận dữ liệu tài khoản không có trong document đó.

Test bổ sung:

- Origin được allowlist có thể nhúng nếu sản phẩm yêu cầu.
- Origin ngoài allowlist bị chặn.
- Redirect đến trang nhạy cảm không làm mất frame policy.
- `X-Frame-Options` legacy không mâu thuẫn ngoài dự kiến với CSP `frame-ancestors`.
- Nút hành động nhạy cảm không bị overlay hoặc UI giả trong luồng app.

Không chỉ kiểm tra header string. Hãy xác nhận browser thực sự không render protected content trong frame không được phép.

## 12. Kiểm thử postMessage và opener isolation

`postMessage` là API hợp lệ để giao tiếp giữa các browsing context, nhưng message có thể bị giả mạo hoặc gửi đến sai origin nếu code dùng wildcard.

Test nên xác minh:

- Receiver kiểm tra `event.origin` và `event.source`.
- Payload được validate theo schema, kiểu, độ dài và message type allowlist.
- Message từ origin không được phép không kích hoạt thao tác.
- Không gửi token hoặc dữ liệu bí mật đến `targetOrigin: "*"`.
- Popup/opener behavior phù hợp với COOP và `noopener`.
- Khi opener bị tách, ứng dụng có fallback an toàn thay vì dựa vào `window.opener` luôn tồn tại.

Ví dụ test bridge: mở app và một popup test, gửi message hợp lệ từ origin được phép rồi gửi message cùng schema từ `attacker.test`; chỉ message từ origin/source đúng mới được xử lý. Đừng dùng string field như `source: "trusted-app"` làm bằng chứng xác thực vì attacker có thể tự tạo cùng giá trị.

## 13. Kiểm thử storage partitioning và third-party state

Storage partitioning làm cùng một third-party origin có thể nhận storage khác nhau tùy top-level site. Test cần dùng một browser context và hai top-level site khác nhau, sau đó nhúng cùng widget origin.

```text
Top-level site A: https://shop.example.test
  └── iframe https://widget.vendor.test

Top-level site B: https://news.other.test
  └── iframe https://widget.vendor.test
```

Test ghi marker không nhạy cảm vào storage của iframe khi ở site A rồi mở site B và kiểm tra marker có xuất hiện hay không. Kết quả mong đợi phụ thuộc API, browser engine/version và privacy settings: browser có thể partition storage hoặc chặn API trong third-party context. Không áp một kỳ vọng giống nhau cho mọi browser nếu tiêu chuẩn hỗ trợ không quy định như vậy.

Ghi nhận:

- Browser/version và privacy setting.
- Top-level site, iframe origin và storage API được thử.
- API có sẵn, bị chặn hay được partition.
- Cookie thường và cookie CHIPS (`Partitioned`) có hành vi ra sao.
- `document.hasStorageAccess()`/`requestStorageAccess()` có được hỗ trợ và yêu cầu user activation/prompt thế nào.

Không dùng dữ liệu tài khoản thật. Với test partitioning, một marker ngẫu nhiên vô hại là đủ. Không tự động cấp quyền Storage Access API để làm test pass; cần kiểm tra cả trường hợp user từ chối.

## 14. Kiểm thử cache, service worker và logout

Response nhạy cảm cần policy HTTP phù hợp và không được service worker tự ghi vào Cache Storage nếu ứng dụng không cho phép.

Test case quan trọng:

1. API cá nhân trả `Cache-Control: no-store`.
2. CDN test không cache endpoint có session.
3. Service worker không gọi `cache.put()` cho `/api/private/*`.
4. User A logout, user B đăng nhập cùng browser profile, dữ liệu A không xuất hiện.
5. Back/Forward restore không hiển thị dữ liệu cũ sau khi session đã revoke.
6. Response `304` chỉ được trả sau khi server xác thực session và quyền hiện tại.
7. Offline mode không phục vụ dữ liệu cá nhân ngoài policy đã phê duyệt.

Ví dụ kiểm tra response header:

```ts
test("private API response is not stored by HTTP caches", async ({ page }) => {
  const responsePromise = page.waitForResponse((item) =>
    item.url().includes("/api/private/profile")
  );
  await page.goto("https://app.example.test/account");
  const response = await responsePromise;

  expect(response.headers()["cache-control"]).toContain("no-store");
});
```

Test này chỉ xác minh header từ response mà page nhận. Cần test riêng CDN cache status và Cache Storage của service worker. Browser cache và BFCache là hai cơ chế khác nhau; kiểm tra logout/back navigation bằng hành vi hiển thị và session revalidation, không chỉ dựa vào `Cache-Control`.

## 15. Kiểm thử Referrer-Policy và URL leak

Tạo URL callback giả có marker trong query và fragment. Không dùng token thật.

Với `Referrer-Policy: no-referrer`, request từ trang nguồn không nên có `Referer`. Với `strict-origin-when-cross-origin`, cross-origin request cùng mức bảo mật chỉ nhận origin, không nhận path/query. Fragment vốn không được đưa vào `Referer`, nhưng JavaScript vẫn có thể đọc `location.hash`.

Test nên xác minh:

- Response header policy đúng ở document thực tế.
- Cross-origin navigation/subresource request gửi đúng lượng referrer.
- `document.referrer` ở trang đích phù hợp với policy.
- Analytics/error tracking không thu thập `location.href`, query hoặc fragment nhạy cảm.
- Callback làm sạch URL sau khi xử lý và không ghi token vào console.

Không kết luận URL an toàn chỉ vì `Referer` không chứa fragment. Browser history, script cùng origin, telemetry và server log của request URL vẫn có thể chứa dữ liệu.

## 16. Kiểm thử MIME type, upload và download

MIME test cần kiểm tra header và byte nội dung. Header `Content-Type` do client gửi khi upload không phải bằng chứng định dạng file.

Các case nên có:

- JSON API trả `application/json` và `X-Content-Type-Options: nosniff`.
- Script/style có MIME type phù hợp; response sai type bị browser chặn trong ngữ cảnh có `nosniff`.
- Upload file giả MIME type bị server từ chối sau khi kiểm tra signature/parser.
- HTML/SVG do người dùng upload không chạy trong origin ứng dụng.
- Download nhạy cảm dùng `Content-Disposition: attachment` và cache policy phù hợp.
- Tên file không gây header injection hoặc path traversal.
- Archive upload có giới hạn byte giải nén, số entry, độ sâu và thời gian.

Browser automation có thể xác nhận response headers, download event và kết quả render. Kiểm tra archive bomb, parser crash và malware scan cần integration test riêng trong worker/container cô lập với fixture giới hạn; không tạo file có thể làm cạn tài nguyên trong CI thông thường.

## 17. Kiểm thử WebSocket và browser extension

### 17.1. WebSocket

Test WebSocket nên xác minh:

- Handshake chỉ dùng `wss://` trong production.
- Server kiểm tra `Origin` theo allowlist.
- Session được xác thực khi handshake và quyền được kiểm tra cho từng channel/action.
- Message schema, kích thước, tần suất và close code được xử lý đúng.
- Reconnect/backoff không tạo vòng lặp request hoặc gửi lặp hành động.
- Token không bị ghi vào URL, console hoặc log.

Handshake thành công không chứng minh message tiếp theo hợp lệ. Dùng fixture server và message test không chứa dữ liệu thật.

### 17.2. Browser extension

Nếu sản phẩm có extension, kiểm thử riêng:

- Content script chỉ chạy trên match pattern được cấp.
- Isolated world tách global nhưng DOM vẫn được coi là input không tin cậy.
- `postMessage`/CustomEvent giả không gọi privileged API.
- Service worker xác minh `sender.id`, URL, tab và frame.
- Message schema hẹp, không có action tùy ý.
- Host permissions và optional permissions theo least privilege.
- Extension không đưa secret vào DOM, bundle hoặc web-accessible resource.

Extension test thường cần persistent browser context và cách nạp extension riêng theo browser; không giả định cùng một cấu hình Playwright chạy được trên Chromium, Firefox và WebKit. Bổ sung kiểm thử thủ công trên browser phân phối extension.

## 18. Ma trận browser và môi trường

Không phải mọi browser đều triển khai privacy feature cùng thời điểm hoặc cùng cách. Hãy xác định ma trận hỗ trợ của sản phẩm và ghi rõ test nào bắt buộc, test nào phụ thuộc feature.

| Nhóm | Chromium | Firefox | WebKit/Safari | Ghi chú |
| --- | --- | --- | --- | --- |
| SOP/CORS | Bắt buộc | Bắt buộc | Bắt buộc | Test các origin thực, không dùng API request trực tiếp để thay browser fetch. |
| Cookie Secure/HttpOnly/SameSite | Bắt buộc | Bắt buộc | Bắt buộc | Có thể khác về privacy/tracking protection và third-party context. |
| CSP | Bắt buộc | Bắt buộc | Bắt buộc | Kiểm tra enforcement và report-only. |
| Trusted Types | Feature-specific | Feature-specific | Feature-specific | Chỉ assert trên engine/version có hỗ trợ; theo dõi support matrix. |
| Storage partitioning | Theo browser policy/version | Theo browser policy/version | Theo browser policy/version | Ghi nhận API bị partition hay block. |
| CHIPS | Feature-specific | Feature-specific | Feature-specific | Kiểm tra support thực tế; không coi là cookie third-party toàn cục. |
| BFCache | Bắt buộc | Bắt buộc | Bắt buộc | Test pageshow/restore và trạng thái sau logout. |
| Download behavior | Bắt buộc | Bắt buộc | Bắt buộc | Tên file, prompt và auto-download policy có thể khác. |
| Extension | Chromium-based theo sản phẩm | Theo sản phẩm | Theo sản phẩm | Cần test theo manifest/API và kênh phân phối cụ thể. |

Trong CI, dùng browser version cố định để giảm flaky test. Ngoài CI, chạy smoke suite trên phiên bản stable mới trước release. Với feature privacy thay đổi theo browser, lưu kết quả theo browser/version và cập nhật expected behavior dựa trên tài liệu chính thức cùng yêu cầu sản phẩm.

## 19. Tổ chức test suite và CI

Chia suite theo thời gian chạy và mức độ phụ thuộc môi trường:

| Suite | Nội dung | Khi chạy |
| --- | --- | --- |
| Fast security smoke | Security headers, CORS deny/allow, cookie flags, CSP basic, XSS render. | Mỗi pull request. |
| Browser integration | CSRF form, frame policy, referrer, cache/logout, MIME/download. | Pull request quan trọng hoặc nightly. |
| Cross-browser | Chromium, Firefox, WebKit với test cốt lõi. | Nightly và trước release. |
| Privacy/partition | Third-party cookie, CHIPS, Storage Access API, partitioned storage. | Nightly hoặc browser compatibility cycle. |
| Manual/controlled | Permission prompt, extension, privacy setting, certificate và UX. | Trước release hoặc khi thay đổi policy. |

Nguyên tắc CI:

- Dùng test domain riêng và HTTPS certificate tin cậy.
- Không gọi production API hoặc dùng production credentials.
- Mỗi test tạo state độc lập; cleanup user, cookie, file và job.
- Không chạy test song song nếu chúng chia sẻ cùng tài khoản hoặc resource mutable.
- Retry chỉ để xử lý flaky infrastructure, không dùng retry để che security failure.
- Giữ trace/screenshot có giới hạn; sanitize trước khi lưu hoặc chia sẻ.
- Lưu browser/version, commit, build ID và test fixture version trong report.
- Phân biệt `passed`, `failed`, `skipped` và `unsupported`; không coi skipped là passed.
- Test failure do browser policy phải có log giải thích và link đến expected behavior.

## 20. Tránh false positive và flaky security test

Security test dễ flaky nếu phụ thuộc thời gian, prompt, mạng hoặc trạng thái profile. Một số cách giảm nhiễu:

- Chờ điều kiện cụ thể bằng locator/response/event thay vì `waitForTimeout()` cố định.
- Dùng fixture server điều khiển được response header và latency.
- Dùng test account riêng cho từng worker.
- Xác định chính xác cookie domain, path, SameSite và Secure.
- Không dựa vào một thông báo Console có nội dung thay đổi giữa browser version nếu có thể kiểm tra hành vi thực tế.
- Với CORS, assert cả promise result và server request log để phân biệt browser block với network failure.
- Với CSP, kiểm tra script sentinel không chạy và violation event/report có xuất hiện.
- Với iframe, assert protected content không hiển thị; đừng chỉ assert header có mặt.
- Với storage partitioning, xác định trước feature support và chấp nhận kết quả “blocked” khác “partitioned”.
- Với download, chờ download event và kiểm tra filename/status; không giả định file đã được lưu chỉ vì click handler chạy.

Một test fail vì fixture server không hoạt động không phải bằng chứng ứng dụng có lỗ hổng. Report cần phân biệt product failure, environment failure và unsupported feature.

## 21. Báo cáo kết quả kiểm thử

Mỗi finding nên có:

- Tên security invariant.
- Browser engine/version, OS và cấu hình liên quan.
- Build/commit và môi trường.
- Preconditions và test account/tenant fixture.
- Bước tái hiện tối thiểu.
- Kết quả mong đợi và thực tế.
- Bằng chứng đã làm sạch: status/header, console category, request ID, assertion output.
- Severity/impact và phạm vi ảnh hưởng.
- Browser/version khác đã thử và kết quả.
- Hướng khắc phục cùng regression test cần thêm.

Không đưa cookie, Authorization header, token, password, signed URL, dữ liệu cá nhân hoặc response body nhạy cảm vào report. Trace, HAR, screenshot và video cần được xử lý như artifact có thể chứa credential. Dùng marker test và request ID thay vì giá trị thật.

## 22. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ kiểm tra header bằng unit test | Không biết browser/CDN có thực thi policy đúng không. | Thêm browser test qua HTTPS và xác nhận hành vi thực tế. |
| Dùng APIRequestContext để kết luận CORS | Bỏ qua enforcement của JavaScript trong browser. | Dùng `fetch()` từ page có origin cụ thể. |
| Chỉ test một browser | Bỏ sót khác biệt cookie, privacy, storage và navigation. | Chạy matrix browser engine/version theo mức hỗ trợ. |
| Dùng `localhost` cho mọi cross-site test | Không mô phỏng đầy đủ site và cookie behavior. | Dùng test domains riêng, HTTPS và certificate tin cậy. |
| Test CSRF với cookie Lax rồi nghĩ token đã được kiểm tra | Browser có thể không gửi cookie nên request thất bại vì auth, không phải CSRF defense. | Dùng fixture có thể gửi cookie cross-site để kiểm tra token/Origin độc lập. |
| Chỉ kiểm tra CSP header string | Header có thể bị ghi đè hoặc browser không thực thi như kỳ vọng. | Assert script bị chặn và violation được ghi nhận. |
| Coi test skipped là pass | Không biết feature chưa được kiểm tra trên engine đó. | Báo skipped/unsupported riêng và duy trì fallback test. |
| Chạy chung session giữa các test | Test có thể phụ thuộc thứ tự và che lỗi cross-account. | Context độc lập và fixture account riêng. |
| Lưu trace/HAR không kiểm soát | Lộ cookie, token hoặc dữ liệu cá nhân trong CI artifact. | Dùng dữ liệu giả, hạn chế artifact, sanitize và retention ngắn. |
| Retry mọi security test | Lỗ hổng/flaky behavior bị che bởi lần chạy sau. | Điều tra nguyên nhân; retry chỉ cho lỗi hạ tầng đã phân loại. |

## 23. Bài thực hành

Tạo một staging lab với các host `app.example.test`, `api.example.test`, `attacker.test` và `widget.vendor.test`. Dùng HTTPS, hai test account và dữ liệu giả.

1. Cấu hình Playwright chạy Chromium, Firefox và WebKit với browser version cố định.
2. Viết test chứng minh trang attacker không đọc được document cross-origin và API response không có CORS allowlist.
3. Viết test credentialed CORS cho app/API khác origin nhưng cùng site; kiểm tra preflight method/header.
4. Đăng nhập test user, xác minh session cookie có thuộc tính bảo mật và không đọc được qua `document.cookie`.
5. Gửi cross-site form POST từ attacker origin và xác nhận CSRF token/Origin validation từ chối, state không đổi.
6. Gửi payload XSS vô hại vào comment; xác nhận nội dung hiển thị như text và sentinel không chạy.
7. Kiểm tra CSP chặn inline script không có nonce; kiểm tra Trusted Types trên engine hỗ trợ.
8. Nhúng trang tài khoản trong iframe attacker và xác nhận browser không hiển thị protected content.
9. Kiểm tra referrer policy, response `no-store`, logout/account switching và Back/Forward restore.
10. Kiểm tra storage partitioning/CHIPS trong third-party iframe; ghi nhận rõ browser block hay partition state.
11. Kiểm tra MIME `nosniff`, upload giả MIME, download attachment và file không tin cậy.
12. Xuất report/trace đã làm sạch, ghi browser/version, bằng chứng, skipped test và các khác biệt cần xử lý.

Hoàn thành bài thực hành khi mỗi security invariant có ít nhất một test browser hoặc một test có giải thích rõ vì sao phải kiểm tra thủ công; các test chạy độc lập, có thể lặp lại, không dùng dữ liệu production và chứng minh được browser thực thi đúng ranh giới bảo mật.
