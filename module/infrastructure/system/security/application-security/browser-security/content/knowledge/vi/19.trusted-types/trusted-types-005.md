# Default policy — kiểm soát các DOM sink cũ khi áp dụng Trusted Types

> **Chương:** Trusted Types  
> **Mục tiêu:** Hiểu default policy của Trusted Types, cách browser tự gọi policy này khi chuỗi thường đi vào injection sink được bảo vệ, vai trò của nó trong quá trình chuyển đổi ứng dụng cũ, cách xây dựng policy an toàn cho HTML/Script/ScriptURL, giới hạn của default policy và lộ trình chuyển sang policy tường minh theo từng thành phần.

## 1. Default policy giải quyết vấn đề gì?

Một ứng dụng lâu năm có thể có hàng trăm chỗ gán dữ liệu vào DOM:

```js
element.innerHTML = apiResponse.description;
container.insertAdjacentHTML("beforeend", comment);
script.src = pluginUrl;
```

Những dòng code này có thể tồn tại trong nhiều module, thư viện hoặc framework. Khi bật Trusted Types enforcement, browser yêu cầu các injection sink được bảo vệ nhận đúng loại Trusted Type thay vì một chuỗi JavaScript thông thường. Code cũ truyền string có thể bắt đầu ném `TypeError`.

**Default policy** là một policy đặc biệt có tên chính xác là `default`. Khi Trusted Types enforcement được bật và một string thường được truyền vào một sink được bảo vệ, browser có thể tự gọi callback tương ứng của default policy để chuyển đổi dữ liệu thành Trusted Type.

Ví dụ khái niệm:

```js
const defaultPolicy = trustedTypes.createPolicy("default", {
  createHTML(input) {
    return DOMPurify.sanitize(input, {
      RETURN_TRUSTED_TYPE: false,
    });
  },
});

// Với enforcement đang bật, default policy có thể được gọi ngầm
// khi string đi vào HTML injection sink được bảo vệ.
element.innerHTML = untrustedHtml;
```

Default policy có thể giúp ứng dụng cũ tiếp tục hoạt động trong khi đội phát triển kiểm kê và sửa từng sink. Tuy nhiên, nó cũng là **đường chuyển đổi ngầm có phạm vi rộng**. Nếu callback trả lại mọi input mà không kiểm tra, Trusted Types enforcement gần như mất ý nghĩa tại những sink đó.

## 2. Trusted Types hoạt động cùng CSP như thế nào?

Trusted Types thường được bật bằng hai directive CSP:

```http
Content-Security-Policy: require-trusted-types-for 'script'; trusted-types default app-html
```

- `require-trusted-types-for 'script'` yêu cầu các injection sink thuộc phạm vi hỗ trợ phải nhận Trusted Type phù hợp thay vì string thường.
- `trusted-types default app-html` giới hạn tên policy mà trang được phép tạo; ví dụ này cho phép policy `default` và `app-html`.

Nếu chỉ bật `require-trusted-types-for` mà không có default policy, code cũ truyền string vào sink được bảo vệ thường bị từ chối và browser ném `TypeError`.

Nếu có default policy được phép tạo và đã khởi tạo, browser có thể gọi callback thích hợp khi gặp string. Policy vẫn phải trả về giá trị hợp lệ để tạo Trusted Type; nếu callback ném lỗi hoặc không có callback tương ứng, thao tác không được tự động trở nên an toàn.

**CSP kiểm soát policy nào được tạo và yêu cầu Trusted Types tại sink.** Nó không tự viết sanitizer và không tự quyết định nội dung HTML nào được phép.

## 3. Default policy được gọi khi nào?

Default policy không phải middleware chạy cho mọi dữ liệu của ứng dụng. Nó được browser sử dụng trong những tình huống cụ thể:

1. Trang đang có Trusted Types enforcement.
2. Code truyền một giá trị string thông thường vào injection sink được Trusted Types bảo vệ.
3. Browser tìm thấy default policy có callback phù hợp với loại sink.
4. Callback chuyển đổi đầu vào thành giá trị được bọc thành Trusted Type.
5. Sink nhận Trusted Type đó và tiếp tục theo quy tắc của API.

Nếu code đã truyền một đối tượng `TrustedHTML` vào sink yêu cầu TrustedHTML, default policy không cần được gọi lại. Mục tiêu lâu dài là các module chủ động tạo Trusted Type bằng policy hẹp của mình, thay vì phụ thuộc vào chuyển đổi ngầm.

### Default policy không tự động làm sạch mọi chuỗi

Nếu ứng dụng chỉ tạo default policy với `createHTML`, điều đó không có nghĩa mọi loại sink đều được bảo vệ bằng cùng một callback. Các sink có thể yêu cầu loại khác:

| Loại Trusted Type | Vai trò |
| --- | --- |
| `TrustedHTML` | Dữ liệu được phép đi vào HTML injection sink |
| `TrustedScript` | Dữ liệu được phép đi vào một số sink diễn giải JavaScript |
| `TrustedScriptURL` | URL được phép dùng cho những sink tải script |

Không có một kiểu Trusted Type tổng quát thay cho mọi ngữ cảnh. Browser kiểm tra loại giá trị theo sink; một TrustedHTML không thể thay thế TrustedScriptURL.

## 4. Default policy không phải sanitizer mặc định

Tên `default` dễ gây hiểu lầm. Browser không cung cấp một thuật toán làm sạch HTML tích hợp chỉ vì policy mang tên này.

Ứng dụng tự định nghĩa callback:

```js
trustedTypes.createPolicy("default", {
  createHTML(input) {
    return input;
  },
});
```

Ví dụ trên trả lại nguyên chuỗi. Nó khiến mọi string đi qua callback HTML được bọc thành TrustedHTML mà không có bước kiểm soát nội dung. **Đây là cách cấu hình nguy hiểm** nếu input có thể chứa markup hoặc thuộc tính do attacker kiểm soát.

Default policy chỉ an toàn khi mỗi callback có quy tắc rõ ràng:

- HTML phải được sanitize bằng thư viện chuyên dụng và cấu hình theo sản phẩm.
- Script động nên bị từ chối trừ khi có một tập mã cố định đã được kiểm duyệt.
- Script URL phải được parse và kiểm tra allowlist chính xác.
- Callback không xử lý được ngữ cảnh thì phải fail closed bằng cách ném lỗi.

Không viết sanitizer HTML bằng regex, và không dùng một phép escape chuỗi chung cho HTML, JavaScript và URL.

## 5. Tạo default policy cho giai đoạn chuyển đổi

Một default policy dùng trong migration có thể cho phép một số HTML rich text đã được sanitize, đồng thời từ chối các loại script không có quy tắc an toàn:

```js
const defaultPolicy = trustedTypes.createPolicy("default", {
  createHTML(input) {
    return DOMPurify.sanitize(input, {
      USE_PROFILES: { html: true },
      RETURN_TRUSTED_TYPE: false,
    });
  },

  createScript() {
    throw new TypeError("Không cho phép tạo script từ chuỗi");
  },

  createScriptURL(input) {
    const url = new URL(input, location.origin);
    const allowedPaths = new Set([
      "/assets/app.js",
      "/assets/editor.js",
    ]);

    if (url.protocol !== "https:" || url.origin !== location.origin) {
      throw new TypeError("Script URL không được phép");
    }
    if (!allowedPaths.has(url.pathname) || url.search || url.hash || url.username || url.password) {
      throw new TypeError("Đường dẫn script không được phép");
    }

    return url.href;
  },
});
```

Đây là ví dụ minh họa. Trong production:

- Kiểm tra chính sách URL bằng origin và path đã parse; không dựa trên so khớp chuỗi tiền tố URL thô.
- Quyết định rõ có cần query string, port hoặc tên file cụ thể hay không.
- Thay danh sách asset minh họa bằng allowlist chính xác của ứng dụng; không cho phép mọi file dưới một thư mục nếu không cần.
- Chỉ dùng DOMPurify từ dependency được quản lý, cập nhật và cấu hình phù hợp.
- Không tạo default policy chỉ để làm mọi lỗi TypeError biến mất.

Trong callback `createHTML`, DOMPurify trả về string đã sanitize vì `RETURN_TRUSTED_TYPE: false`. Sau đó Trusted Types API bọc kết quả thành TrustedHTML. Nếu DOMPurify được cấu hình trả TrustedHTML ngay bên trong callback createHTML, việc lồng kiểu có thể không phù hợp với hợp đồng callback.

### Một phiên bản policy tối giản hơn

Nếu ứng dụng không cần hỗ trợ script URL string cũ, tốt hơn là chỉ định nghĩa callback HTML và để các loại script tiếp tục bị chặn:

```js
trustedTypes.createPolicy("default", {
  createHTML(input) {
    return DOMPurify.sanitize(input, {
      USE_PROFILES: { html: true },
      RETURN_TRUSTED_TYPE: false,
    });
  },
});
```

Không có callback `createScript` hoặc `createScriptURL` đồng nghĩa ứng dụng không có đường chuyển đổi ngầm cho những sink tương ứng. Những thao tác đó cần được sửa thành policy tường minh hoặc loại bỏ.

## 6. Vì sao default policy có phạm vi rủi ro lớn?

Default policy có thể được gọi từ nhiều nơi mà code không gọi trực tiếp `defaultPolicy.createHTML()`. Do đó, một callback quá rộng có thể che giấu hàng loạt đường dữ liệu không an toàn:

- Một module đưa comment người dùng vào `innerHTML`.
- Một thư viện cũ gán chuỗi vào `outerHTML`.
- Một plugin tạo script URL từ dữ liệu cấu hình.
- Một component không rõ nguồn gốc truyền chuỗi vào HTML sink.

Nếu default policy luôn trả về một Trusted Type cho mọi input, các lỗi kiến trúc vẫn tồn tại nhưng không còn bị enforcement phát hiện. Đây là lý do default policy nên được xem như **cầu nối migration có kiểm soát**, không phải mục tiêu cuối cùng.

Một policy HTML dùng sanitizer cũng không giải quyết các vấn đề sau:

- URL redirect hoặc điều hướng sai đích.
- Quyền truy cập và authorization ở server.
- Script URL trỏ tới tài nguyên độc hại nhưng hợp lệ theo allowlist quá rộng.
- DOM clobbering hoặc logic ứng dụng sai.
- XSS trong một context không thuộc callback HTML.

## 7. Default policy và policy tường minh khác nhau thế nào?

| Tiêu chí | Default policy | Named policy tường minh |
| --- | --- | --- |
| Tên | Phải là `default` | Tên do ứng dụng chọn, ví dụ `article-html` |
| Cách gọi | Browser có thể gọi ngầm khi string đi vào sink được bảo vệ | Code gọi `policy.createHTML()` hoặc API tương ứng |
| Phạm vi | Có thể ảnh hưởng nhiều module và thư viện cũ | Có thể giới hạn cho một thành phần hoặc nghiệp vụ |
| Mục đích phù hợp | Migration, quan sát và tương thích có thời hạn | Thiết kế lâu dài với ranh giới rõ ràng |
| Rủi ro | Dễ vô tình cho phép quá nhiều sink | Vẫn nguy hiểm nếu callback quá rộng, nhưng dễ rà soát hơn |

Ví dụ policy tường minh:

```js
const articleHtmlPolicy = trustedTypes.createPolicy("article-html", {
  createHTML(input) {
    return DOMPurify.sanitize(input, {
      USE_PROFILES: { html: true },
      RETURN_TRUSTED_TYPE: false,
    });
  },
});

const trustedArticle = articleHtmlPolicy.createHTML(articleBody);
document.querySelector("#article").innerHTML = trustedArticle;
```

Code thể hiện rõ module nào đang yêu cầu HTML đã sanitize. Khi audit, có thể tìm các chỗ gọi `articleHtmlPolicy.createHTML` và đánh giá đầu vào, callback cũng như sink tương ứng.

## 8. Policy factory và giới hạn tên policy bằng CSP

Directive `trusted-types` trong CSP xác định tên policy được phép tạo:

```http
Content-Security-Policy: require-trusted-types-for 'script'; trusted-types default article-html script-assets
```

Trong ví dụ, trang có thể tạo policy `default`, `article-html` và `script-assets`. Nếu code cố tạo policy tên khác, browser có thể từ chối việc tạo policy theo CSP.

Một số lưu ý:

- Tên policy là định danh, không phải bí mật.
- Tránh cho phép wildcard tên policy nếu không cần.
- Không dùng `allow-duplicates` trừ khi có lý do kiến trúc đã đánh giá; policy trùng tên làm khó kiểm soát ai tạo policy.
- Không để mỗi plugin tự tạo policy tùy ý.
- Duy trì danh sách policy tập trung, có owner và mục đích rõ ràng.

Ví dụ tạo policy cho URL script:

```js
const scriptAssetsPolicy = trustedTypes.createPolicy("script-assets", {
  createScriptURL(input) {
    const url = new URL(input, location.origin);
    const allowedPaths = new Set([
      "/assets/app.js",
      "/assets/editor.js",
    ]);

    if (url.origin !== location.origin || url.protocol !== "https:") {
      throw new TypeError("Origin script không hợp lệ");
    }
    if (!allowedPaths.has(url.pathname) || url.search || url.hash) {
      throw new TypeError("Script path không nằm trong allowlist");
    }
    return url.href;
  },
});

const script = document.createElement("script");
script.src = scriptAssetsPolicy.createScriptURL("/assets/app.js");
document.head.append(script);
```

Policy trên dùng allowlist chính xác theo path, origin và scheme. Trong ứng dụng thực, có thể cần port hoặc versioned asset path; hãy đưa chúng vào chính sách rõ ràng thay vì cho phép mọi URL dưới một host rộng.

## 9. Không tạo TrustedScript từ dữ liệu tùy ý

`TrustedScript` dành cho một số sink diễn giải chuỗi thành JavaScript. Việc bọc một chuỗi thành TrustedScript không làm code trong chuỗi an toàn.

Ví dụ nguy hiểm:

```js
trustedTypes.createPolicy("default", {
  createScript(input) {
    return input;
  },
});
```

Policy này cho phép string tùy ý đi vào đường thực thi script được bảo vệ. Thông thường, ứng dụng nên:

- Loại bỏ `eval`, `new Function` và timer dạng chuỗi.
- Dùng function/module được định nghĩa trong source code.
- Nếu một thư viện legacy thực sự cần script động, xác định chính xác tập code được phép và thay thế thư viện khi có thể.
- Không dùng sanitizer HTML để xử lý JavaScript.

Nếu không có nhu cầu hợp lệ cho TrustedScript, không định nghĩa `createScript` trong default policy. Để sink từ chối string sẽ giúp phát hiện code cần sửa.

## 10. createScriptURL cần allowlist nghiêm ngặt

`TrustedScriptURL` thường được dùng cho sink tải script như `script.src`. Nếu default policy chấp nhận mọi URL, bất kỳ code cũ nào có thể biến dữ liệu không tin cậy thành URL script được chấp nhận.

Không làm:

```js
trustedTypes.createPolicy("default", {
  createScriptURL(input) {
    return input;
  },
});
```

Một policy URL script phải:

1. Parse bằng `new URL(input, base)`.
2. Chỉ chấp nhận scheme phù hợp, thường là HTTPS.
3. So sánh origin chính xác với allowlist.
4. Kiểm tra path hoặc asset identifier theo danh sách đã được build/deploy kiểm soát.
5. Từ chối username/password, port, query hoặc fragment nếu không cần.
6. Không theo redirect tùy ý tới nguồn script ngoài chính sách.

Không nhầm TrustedScriptURL với URL thông thường của liên kết. Một đường dẫn có thể hợp lệ cho `a.href` nhưng không được phép làm nguồn JavaScript.

## 11. Default policy và HTML sanitizer

Khi legacy code dùng `innerHTML` để render rich text, default policy có thể gọi sanitizer:

```js
const defaultPolicy = trustedTypes.createPolicy("default", {
  createHTML(input) {
    return DOMPurify.sanitize(input, {
      USE_PROFILES: { html: true },
      RETURN_TRUSTED_TYPE: false,
    });
  },
});
```

Điều này chỉ phù hợp khi sản phẩm thực sự cần render HTML. Nếu chỉ cần hiển thị văn bản, sửa sink thành `textContent` sẽ đơn giản và ít rủi ro hơn.

Sanitizer phải được:

- Cập nhật định kỳ theo phiên bản và cảnh báo bảo mật.
- Cấu hình theo allowlist tag/attribute cần thiết.
- Kiểm thử với browser/parser thực tế.
- Sử dụng đúng output context.
- Bảo vệ khỏi việc code tiếp tục nối chuỗi hoặc sửa DOM sau sanitize theo cách làm mất hiệu lực bảo vệ.

Không tự thêm các tag, attribute hoặc URI scheme vào allowlist chỉ để làm nội dung hiển thị giống trước. Hãy xác định yêu cầu sản phẩm và rủi ro của từng khả năng.

## 12. Quan sát default policy trong giai đoạn migration

Default policy có thể giúp đội phát triển phát hiện nơi code cũ truyền string vào sink. Tuy nhiên, callback chỉ nhìn thấy những lần browser gọi policy; không phải mọi thao tác DOM đều được bao phủ và không phải mọi lỗ hổng XSS đều đi qua Trusted Types sink.

Trong migration, có thể ghi nhận:

- Loại callback được gọi: HTML, Script hay ScriptURL.
- Module/route và call stack ở mức cần thiết.
- Loại sink hoặc thành phần gọi nếu thông tin có sẵn.
- Số lần gọi theo build/phiên bản để theo dõi tiến độ.

Không log nguyên văn input nếu có thể chứa thông tin cá nhân, token hoặc nội dung nhạy cảm. Tránh đưa dữ liệu người dùng vào telemetry chỉ để debug.

Mục tiêu của quan sát là lập danh sách sink cần sửa, không phải chứng minh callback đang làm sạch mọi đầu vào.

## 13. Lộ trình chuyển từ default policy sang policy tường minh

Một lộ trình có thể chia thành các giai đoạn:

1. **Kiểm kê:** tìm `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, script URL và các API injection sink liên quan.
2. **Bật quan sát:** thử nghiệm Trusted Types bằng Report-Only nếu browser mục tiêu hỗ trợ, phân loại các đường vi phạm.
3. **Tạo default policy fail-closed:** chỉ hỗ trợ trường hợp HTML rich text có sanitizer; từ chối script/script URL chưa có quy tắc.
4. **Sửa sink đơn giản:** thay HTML sink bằng `textContent`, DOM API có cấu trúc hoặc template binding an toàn.
5. **Tạo named policy:** mỗi thành phần có policy rõ ràng, ví dụ `article-html` hoặc `script-assets`.
6. **Thu hẹp default policy:** loại bỏ callback đã không còn cần; theo dõi nơi vẫn gọi ngầm.
7. **Xóa default policy:** khi toàn bộ sink đã chuyển sang Trusted Type tường minh hoặc safe sink, bỏ policy `default` để string cũ bị từ chối.
8. **Enforce và regression test:** giữ CSP enforcement, kiểm tra các browser được hỗ trợ và theo dõi lỗi runtime.

Không giữ default policy vô thời hạn chỉ vì một thư viện chưa được sửa. Ghi rõ owner, thời hạn và tiêu chí xóa policy.

## 14. Report-Only, enforcement và browser support

Trusted Types thường được triển khai qua CSP:

```http
Content-Security-Policy-Report-Only: require-trusted-types-for 'script'; trusted-types default article-html
```

Report-Only giúp quan sát vi phạm mà không chặn theo policy đó. Khi chuyển sang:

```http
Content-Security-Policy: require-trusted-types-for 'script'; trusted-types default article-html
```

browser hỗ trợ sẽ thực thi yêu cầu Trusted Types cho các sink trong phạm vi.

Trusted Types enforcement được hỗ trợ chủ yếu trong Chromium-based browsers; mức hỗ trợ khác nhau giữa browser engine và phiên bản. Một polyfill có thể cung cấp một phần API để hỗ trợ phát triển hoặc kiểm thử, nhưng **không thể tự tạo enforcement ở native browser sink nếu browser không hỗ trợ cơ chế đó**.

Do đó:

- Xác định browser/version tối thiểu của sản phẩm.
- Dùng feature detection và fallback an toàn.
- Không dựa riêng vào polyfill như ranh giới bảo mật.
- Duy trì safe DOM API, sanitizer và CSP script policy cho browser chưa hỗ trợ.
- Kiểm tra Report-Only và enforcement trên browser thật trong ma trận hỗ trợ.

## 15. Các lỗi thường gặp với default policy

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Default policy trả lại input nguyên trạng | String không tin cậy được bọc thành Trusted Type | Sanitize HTML; từ chối Script/ScriptURL nếu chưa có quy tắc |
| Tạo policy tên default nhưng không giới hạn bằng CSP | Thành phần khác có thể tạo policy ngoài dự kiến | Dùng directive `trusted-types` với danh sách tên cụ thể |
| Cho phép mọi script URL | Dữ liệu có thể chọn nguồn script tùy ý | Parse URL và allowlist origin/path chính xác |
| Dùng createScript để sửa TypeError | Mở lại đường thực thi code động | Loại bỏ eval/Function/timer string hoặc dùng code cố định |
| Dùng sanitizer HTML cho mọi loại sink | Sai context, không bảo vệ URL/script/CSS | Tách callback theo Trusted Type và ngữ nghĩa sink |
| Giữ default policy mãi mãi | Che giấu các sink legacy, khó audit | Đặt thời hạn migration và chuyển sang named policy |
| Log toàn bộ input trong callback | Có thể lộ dữ liệu nhạy cảm | Log metadata và call site tối thiểu |
| Nghĩ polyfill tạo enforcement như browser | Sink native có thể vẫn nhận string | Kiểm tra hỗ trợ native, giữ safe API độc lập |
| Nghĩ Trusted Types chặn mọi XSS | XSS có thể đi qua sink khác hoặc logic ứng dụng | Kết hợp output encoding, CSP, authorization và kiểm thử |

## 16. Thực hành: quan sát default policy trong DevTools

Thực hiện trong ứng dụng lab do bạn kiểm soát, dùng dữ liệu thử nghiệm vô hại.

### Bước 1 — Bật Trusted Types enforcement

Server thử nghiệm trả:

```http
Content-Security-Policy: require-trusted-types-for 'script'; trusted-types default
```

Nếu browser hỗ trợ, thử gán string vào một HTML injection sink:

```js
document.querySelector("#preview").innerHTML = "<strong>Demo</strong>";
```

Khi chưa có default policy, browser có thể ném `TypeError` vì sink yêu cầu TrustedHTML.

### Bước 2 — Tạo default policy có sanitizer

```js
trustedTypes.createPolicy("default", {
  createHTML(input) {
    return DOMPurify.sanitize(input, {
      USE_PROFILES: { html: true },
      RETURN_TRUSTED_TYPE: false,
    });
  },
});
```

Lặp lại phép gán. Quan sát callback được gọi và nội dung được sanitize trước khi đưa vào sink.

### Bước 3 — Thử chuỗi thường ở script URL

Tạo một script element trong lab và thử gán một URL thử nghiệm. Nếu default policy không có `createScriptURL`, thao tác dùng string thường cần bị từ chối theo enforcement. Không thêm callback trả lại nguyên URL chỉ để làm thử nghiệm qua.

### Bước 4 — Chuyển sang named policy

Tạo policy `article-html` và gọi rõ `articleHtmlPolicy.createHTML(input)` tại component rich text. Sau đó bỏ phụ thuộc vào default policy cho luồng đó.

### Bước 5 — Theo dõi và loại bỏ default policy

Ghi nhận các callback còn được gọi trong luồng thử nghiệm, sửa từng sink và thử bỏ policy `default`. Những code cũ còn truyền string vào sink được bảo vệ phải bị phát hiện trong kiểm thử.

Không thực hiện thử nghiệm trên trang production có dữ liệu người dùng thật.

## 17. Checklist thiết kế default policy

- Chỉ tạo policy tên `default` khi có mục tiêu migration rõ ràng.
- Bật `require-trusted-types-for 'script'` và giới hạn tên policy bằng `trusted-types`.
- Không bao giờ trả lại input nguyên trạng chỉ để làm sink hết TypeError.
- Với HTML, dùng sanitizer được duy trì và cấu hình tối thiểu; ưu tiên text sink nếu không cần rich HTML.
- Với Script, mặc định từ chối chuỗi động; loại bỏ eval/Function/timer string.
- Với ScriptURL, parse URL và allowlist scheme, origin, path chính xác.
- Không dùng một callback hoặc sanitizer cho mọi ngữ cảnh.
- Ghi nhận vị trí sử dụng ở mức an toàn, tránh log nội dung nhạy cảm.
- Chuyển dần sang named policy hẹp theo component/nghiệp vụ.
- Đặt tiêu chí và thời hạn loại bỏ default policy.
- Kiểm thử CSP Report-Only, enforcement, browser support và fallback.
- Kết hợp Trusted Types với output encoding, CSP script-src, XSS prevention và server-side authorization.

## 18. Câu hỏi tự kiểm tra

1. Default policy có tên gì và browser gọi nó trong tình huống nào?
2. Vì sao default policy không phải sanitizer tích hợp sẵn?
3. Điều gì xảy ra khi enforcement bật nhưng không có default policy và code truyền string vào sink?
4. Vì sao callback createHTML nên dùng sanitizer thay vì trả lại input?
5. TrustedHTML, TrustedScript và TrustedScriptURL khác nhau như thế nào?
6. Vì sao default policy createScript nên từ chối nếu ứng dụng không có nhu cầu rõ ràng?
7. Vì sao createScriptURL cần allowlist origin và path chính xác?
8. CSP directive trusted-types kiểm soát điều gì?
9. Vì sao default policy nên là cầu nối migration có thời hạn?
10. Vì sao polyfill không thể thay thế native Trusted Types enforcement?

**Ghi nhớ:** Default policy là policy đặc biệt tên `default` mà browser có thể gọi ngầm khi string thường đi vào injection sink được Trusted Types bảo vệ. Nó giúp chuyển đổi code cũ, nhưng phạm vi rộng khiến callback quá dễ dãi có thể vô hiệu hóa mục tiêu enforcement. Hãy dùng sanitizer cho HTML thật sự cần, từ chối script động, allowlist chặt ScriptURL, quan sát các sink legacy và chuyển sang named policy tường minh. Mục tiêu cuối cùng là loại bỏ default policy khi ứng dụng không còn cần chuyển đổi ngầm.
