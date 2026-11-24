# Thiết lập CSP

Content Security Policy (CSP) là cơ chế cho phép ứng dụng khai báo những nguồn nội dung và hành vi mà trình duyệt được phép tải hoặc thực thi. CSP giúp giảm nguy cơ XSS, hạn chế việc tải script ngoài dự kiến, kiểm soát nơi trang được nhúng và tạo thêm tín hiệu giám sát khi trình duyệt phát hiện vi phạm policy.

Bài thực hành này xây dựng CSP cho một ứng dụng quản lý tài khoản có HTML, JavaScript, CSS, API, ảnh, worker và một số nội dung nhúng. Bạn sẽ xác định tài nguyên cần thiết, triển khai policy ở chế độ Report-Only, phân tích báo cáo vi phạm, chuyển sang enforce bằng nonce, kiểm tra Trusted Types và xác minh hành vi trên trình duyệt.

CSP là một lớp phòng vệ bổ sung. Nó không thay thế output encoding, sanitizer, kiểm soát quyền ở server hoặc sửa lỗi injection. Một policy quá rộng, nonce bị lộ hoặc nguồn script được tin cậy có lỗ hổng vẫn có thể cho phép mã độc chạy.

## Mục tiêu

Sau bài thực hành, bạn có thể:

- Xác định các nguồn script, style, image, font, API, frame và worker của ứng dụng.
- Thiết kế CSP theo nguyên tắc chỉ cho phép những gì thực sự cần.
- Dùng `Content-Security-Policy-Report-Only` để quan sát trước khi enforce.
- Tạo nonce ngẫu nhiên theo từng response và áp dụng đúng vào script/style được phép.
- Phân biệt nonce, hash, allowlist host và các directive điều khiển inline code.
- Cấu hình báo cáo vi phạm, đọc `blocked-uri`, directive và document liên quan.
- Kết hợp CSP với Trusted Types và các security headers khác.
- Kiểm thử, triển khai theo giai đoạn và xử lý hồi quy sau khi bật policy.

## Bối cảnh bài lab

Ứng dụng mẫu chạy tại `https://app.example.test`. Trang tài khoản tải JavaScript và CSS cùng origin, gọi API tại `https://api.example.test`, hiển thị ảnh người dùng, dùng một Web Worker và có trang preview được nhúng trong iframe. Một số trang cũ còn có inline script hoặc event handler trong HTML.

Mục tiêu là chuyển ứng dụng sang policy có nguồn rõ ràng, loại bỏ inline handler, giới hạn frame và object, đồng thời thu thập report để phát hiện tài nguyên bị chặn. Dùng dữ liệu giả lập và môi trường QA. Không bật policy mới trên production khi chưa kiểm tra các luồng đăng nhập, thanh toán, upload, analytics và tích hợp bên thứ ba.

| Tài nguyên | Nguồn dự kiến | Directive cần xem xét |
|---|---|---|
| JavaScript chính | `app.example.test` | `script-src`, `script-src-elem`, `script-src-attr` |
| Inline bootstrap | Script có nonce riêng cho response | `script-src` |
| CSS | `app.example.test` | `style-src`, `style-src-elem`, `style-src-attr` |
| API | `api.example.test` | `connect-src` |
| Ảnh | Cùng origin và ảnh data URL nếu thật sự cần | `img-src` |
| Font | Cùng origin | `font-src` |
| Worker | Cùng origin | `worker-src` |
| Iframe | Không cho nhúng hoặc chỉ một origin được chỉ định | `frame-ancestors`, `frame-src` |
| Form | Chỉ gửi tới origin ứng dụng | `form-action` |
| Plugin/object | Không sử dụng | `object-src 'none'` |

Danh sách trên là giả định ban đầu. Hãy quan sát ứng dụng thực tế để bổ sung nguồn cần thiết và loại bỏ nguồn không còn sử dụng. Không thêm một host vào policy chỉ vì nó xuất hiện trong Console; cần xác minh chức năng và chủ sở hữu của host đó.

## CSP hoạt động như thế nào?

Server gửi CSP trong HTTP response header. Trình duyệt đọc policy và áp dụng khi xử lý tài liệu cùng tài nguyên liên quan. Một response có thể có nhiều policy; các policy enforce được áp dụng đồng thời, vì vậy thêm policy thứ hai thường làm giới hạn chặt hơn chứ không nới policy thứ nhất.

Header cơ bản:

```http
Content-Security-Policy: default-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
```

Các directive được ngăn cách bằng dấu chấm phẩy. Source expression có thể là keyword như `'self'`, `'none'`, nonce/hash, scheme hoặc host source. Keyword đặc biệt cần đặt trong dấu nháy đơn; host và scheme source không dùng dấu nháy.

### Enforce và Report-Only

Hai chế độ thường dùng:

- `Content-Security-Policy`: trình duyệt thực thi policy; tài nguyên hoặc hành vi vi phạm bị chặn theo directive.
- `Content-Security-Policy-Report-Only`: trình duyệt quan sát và gửi báo cáo vi phạm nhưng không chặn nội dung chỉ vì policy đó.

Có thể gửi một policy enforce và một policy Report-Only cùng lúc. Policy enforce bảo vệ hiện tại; policy Report-Only giúp thử nghiệm policy chặt hơn trước khi thay thế. Không dùng Report-Only như bằng chứng rằng ứng dụng đã được bảo vệ: nó chỉ ghi nhận vi phạm.

Ví dụ chạy policy mới ở chế độ quan sát:

```http
Content-Security-Policy-Report-Only: default-src 'self'; object-src 'none'; base-uri 'self'; script-src 'self' 'nonce-{RANDOM_NONCE}'; connect-src 'self' https://api.example.test; report-to csp; report-uri /csp-reports
```

Header này không chặn nội dung vi phạm. Tạo nonce mới cho mỗi response ngay cả trong giai đoạn Report-Only để dữ liệu thử nghiệm phản ánh đúng policy dự kiến. `Content-Security-Policy-Report-Only` cũng cần được gửi bằng HTTP response header; không thể triển khai bằng `<meta http-equiv>`.

### Directive và phạm vi áp dụng

| Directive | Kiểm soát | Ghi chú |
|---|---|---|
| `default-src` | Nguồn mặc định cho nhiều loại tài nguyên | Fallback cho directive không được khai báo; không thay thế mọi directive |
| `script-src` | Nguồn script và một số inline/eval behavior | Directive quan trọng để giảm XSS |
| `script-src-elem` | Phần tử script như `<script>` | Nếu có, ghi đè `script-src` cho script element |
| `script-src-attr` | Event handler dạng thuộc tính như `onclick` | Có thể đặt `'none'` để loại inline handler |
| `style-src` | Nguồn stylesheet và style inline | Cân nhắc nonce/hash cho style element |
| `style-src-elem` | Phần tử `<style>` và stylesheet | Có thể ghi đè fallback `style-src` |
| `style-src-attr` | Thuộc tính `style` | Có thể đặt `'none'` sau khi loại style attribute |
| `img-src` | Ảnh | `data:` chỉ nên cho phép khi cần |
| `font-src` | Font | Giới hạn host font |
| `connect-src` | Fetch, XHR, WebSocket, EventSource và một số kết nối script | Liệt kê API và endpoint telemetry cần thiết |
| `worker-src` | Worker, SharedWorker và Service Worker | Có fallback theo quy tắc CSP nếu không khai báo |
| `frame-src` | Nguồn iframe mà trang hiện tại được tải | Khác với `frame-ancestors` |
| `frame-ancestors` | Những site được phép nhúng trang hiện tại | Không được đặt bằng meta element; cần response header |
| `form-action` | Đích submit form | Không fallback từ `default-src` |
| `base-uri` | URL được phép dùng trong `<base>` | Giảm nguy cơ đổi base URL để chiếm đường dẫn tương đối |
| `object-src` | Plugin/object như `<object>` và `<embed>` | Thường đặt `'none'` |
| `manifest-src` | Web app manifest | Khai báo nếu ứng dụng dùng manifest |
| `media-src` | Audio/video | Chỉ cho phép nguồn cần thiết |
| `upgrade-insecure-requests` | Nâng request tài nguyên HTTP lên HTTPS | Hữu ích khi chuyển HTTPS; không thay thế sửa URL và HSTS |
| `block-all-mixed-content` | Chặn mixed content | Đã lỗi thời trong trình duyệt hiện đại; không nên dựa vào directive này |

Không phải directive nào cũng có fallback như `default-src`. Ví dụ `frame-ancestors`, `form-action` và `base-uri` cần được khai báo riêng khi cần kiểm soát. Kiểm tra CSP reference của browser mục tiêu nếu dùng directive mới.

## Thiết kế policy ban đầu

Với giả định của lab, policy khởi đầu có thể là:

```http
Content-Security-Policy: default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; script-src 'self' 'nonce-{RANDOM_NONCE}'; script-src-attr 'none'; style-src 'self' 'nonce-{RANDOM_NONCE}'; style-src-attr 'none'; img-src 'self' data:; font-src 'self'; connect-src 'self' https://api.example.test; worker-src 'self'; manifest-src 'self'; upgrade-insecure-requests
```

Đây là policy minh họa, không phải chuỗi có thể sao chép nguyên trạng vào production. `{RANDOM_NONCE}` phải được thay bằng nonce ngẫu nhiên mới cho từng response. `data:` trong `img-src` chỉ giữ lại nếu ứng dụng thực sự hiển thị ảnh data URL. Nếu trang cần được nhúng bởi portal, thay `frame-ancestors 'none'` bằng allowlist chính xác và kiểm thử toàn bộ ancestor chain.

Policy này cố ý không cho phép `unsafe-inline` hoặc `unsafe-eval`. Nếu ứng dụng hiện dùng inline event handler, `eval`, `new Function` hoặc inline style, hãy refactor hoặc thiết kế nonce/hash phù hợp thay vì mở rộng policy ngay lập tức.

### Tránh allowlist host quá rộng

Một policy như `script-src https:` cho phép tải script từ rất nhiều host HTTPS. Điều đó làm giảm hiệu quả của CSP. Allowlist host cũng cần đánh giá chất lượng nội dung: một host được tin cậy có thể chứa JSONP endpoint, nội dung người dùng tải lên hoặc thư viện có lỗ hổng.

Ưu tiên:

- Script cùng origin được kiểm soát.
- Nonce hoặc hash cho script inline cần thiết.
- Host bên thứ ba cụ thể, có chủ sở hữu và mục đích rõ ràng.
- SRI cho script/style tĩnh tải từ CDN khi phù hợp.
- Loại bỏ host không còn được dùng và tránh wildcard subdomain.

Không dùng `*`, `data:` hoặc `blob:` trong `script-src` trừ khi có yêu cầu được đánh giá rõ. Tránh `unsafe-inline` và `unsafe-eval` trong policy production.

## Triển khai nonce theo từng response

Nonce là giá trị ngẫu nhiên được tạo cho một response HTML. Server đặt nonce trong CSP header và gắn cùng giá trị vào những script/style element được phép thực thi. Trình duyệt chỉ chấp nhận element có nonce khớp với policy.

Nonce cần:

- Được tạo bằng bộ sinh số ngẫu nhiên mật mã.
- Đủ độ dài và không thể đoán.
- Thay đổi theo từng response HTML.
- Không được tái sử dụng cố định trong template, repository hoặc nhiều response.
- Được gửi qua header và HTML của cùng response.
- Không bị ghi vào log, analytics hoặc URL.

Ví dụ Node.js/Express:

```js
import crypto from "node:crypto";

app.get("/account", (req, res) => {
  const nonce = crypto.randomBytes(16).toString("base64");

  const csp = [
    "default-src 'self'",
    "base-uri 'self'",
    "object-src 'none'",
    "frame-ancestors 'none'",
    "form-action 'self'",
    `script-src 'self' 'nonce-${nonce}'`,
    "script-src-attr 'none'",
    `style-src 'self' 'nonce-${nonce}'`,
    "style-src-attr 'none'",
    "img-src 'self'",
    "font-src 'self'",
    "connect-src 'self' https://api.example.test",
    "worker-src 'self'",
    "upgrade-insecure-requests"
  ].join("; ");

  res.setHeader("Content-Security-Policy", csp);
  res.setHeader("Cache-Control", "no-store");
  res.render("account", { cspNonce: nonce });
});
```

Trong template, chỉ gắn nonce vào script/style tĩnh do ứng dụng kiểm soát:

```html
<script nonce="<%= cspNonce %>">
  window.accountPageReady = true;
</script>
<script nonce="<%= cspNonce %>" src="/assets/account.js"></script>
```

Ví dụ giả định template engine escape đúng thuộc tính HTML. Nonce là dữ liệu do server tạo, nhưng vẫn cần dùng cơ chế render an toàn. Không đưa nonce vào thuộc tính do người dùng kiểm soát hoặc nội dung có thể bị phản chiếu.

### Nonce và cache

Không cache HTML có nonce theo cách khiến nhiều người dùng nhận cùng một nonce. Nếu CDN hoặc reverse proxy cache response HTML, cần bảo đảm nonce được tạo và gắn đúng cho từng response, hoặc không cache HTML chứa nonce. Có thể cache asset tĩnh có version/hash riêng.

Không dùng nonce cố định trong file HTML tĩnh hoặc biến môi trường lâu dài. Nếu trang tĩnh không thể tạo nonce theo response, cân nhắc hash cho inline script tĩnh hoặc chuyển logic sang file JavaScript cùng origin.

## Dùng hash cho inline script/style tĩnh

Hash cho phép một đoạn inline code cụ thể được thực thi mà không cần nonce động. CSP hỗ trợ hash như `'sha256-...'`, `'sha384-...'` hoặc `'sha512-...'` tính từ nội dung chính xác của script/style.

Ví dụ policy:

```http
Content-Security-Policy: script-src 'self' 'sha256-BASE64_HASH_OF_EXACT_SCRIPT'; object-src 'none'; base-uri 'self'
```

Hash phải được tính trên đúng bytes/nội dung mà trình duyệt dùng để xác minh. Thay đổi khoảng trắng, ký tự xuống dòng hoặc code sẽ làm hash khác. Với script có `src`, SRI là cơ chế integrity của tài nguyên ngoài; CSP hash cho inline script có quy tắc riêng. Nếu dùng external script với hash trong CSP, cần tuân theo yêu cầu tương ứng của CSP và SRI, bao gồm `integrity`/`crossorigin` trong các trường hợp áp dụng.

Hash phù hợp với đoạn bootstrap nhỏ, ổn định. Nếu nội dung thay đổi theo request hoặc người dùng, nonce thường dễ quản lý hơn. Không hash một đoạn code có chứa dữ liệu người dùng hoặc secret.

## Loại bỏ inline handler và eval

Các event handler như `onclick`, `onerror` và `onload` là inline script attribute. Với `script-src-attr 'none'`, chúng bị chặn. Chuyển sang đăng ký event listener trong file JavaScript:

```html
<!-- Trước: inline handler -->
<button onclick="saveProfile()">Lưu</button>

<!-- Sau: chỉ dùng data attribute -->
<button id="save-profile" type="button">Lưu</button>
```

```js
document.querySelector("#save-profile")?.addEventListener("click", saveProfile);
```

Tương tự, thay `eval()` hoặc `new Function()` bằng parser hoặc logic rõ ràng. Nếu một thư viện cũ phụ thuộc eval, đánh giá nâng cấp hoặc thay thế thư viện. Không bật `'unsafe-eval'` chỉ để làm ứng dụng hết lỗi CSP mà chưa đánh giá tác động.

Inline style như `style="display:none"` cũng có thể bị chặn bởi `style-src-attr 'none'`. Chuyển sang class CSS và thay đổi class bằng DOM API:

```js
statusPanel.classList.toggle("is-hidden", shouldHide);
```

Nếu ứng dụng cần inline `<style>` tĩnh, có thể gắn nonce hoặc hash theo thiết kế. Tránh nonce cho từng thuộc tính `style`; ưu tiên stylesheet cùng origin và class.

## Kết hợp Trusted Types

Trusted Types giúp kiểm soát việc đưa chuỗi vào một số DOM sink nhạy cảm. Trong các trình duyệt hỗ trợ, CSP có thể yêu cầu Trusted Types cho script sink:

```http
Content-Security-Policy: require-trusted-types-for 'script'; trusted-types app-html
```

`require-trusted-types-for 'script'` yêu cầu các giá trị phù hợp cho những sink được bảo vệ. `trusted-types app-html` giới hạn tên policy được phép tạo. Trusted Types không tự làm sạch HTML; policy phải gọi sanitizer đã được kiểm thử.

Ví dụ minh họa policy dùng sanitizer được quản lý:

```js
const htmlPolicy = trustedTypes.createPolicy("app-html", {
  createHTML(input) {
    return DOMPurify.sanitize(input, {
      USE_PROFILES: { html: true }
    });
  }
});

preview.innerHTML = htmlPolicy.createHTML(untrustedMarkup);
```

Ví dụ giả định DOMPurify được cài đặt, cấu hình và cập nhật đúng. Không tạo policy trả nguyên `input` hoặc policy mặc định chấp nhận mọi chuỗi. Nếu không cần rich HTML, dùng `textContent` thay vì tạo TrustedHTML.

Trước khi enforce Trusted Types, kiểm kê DOM sink trong ứng dụng và dependency. Một framework hoặc thư viện có thể sử dụng sink nội bộ; cần kiểm tra phiên bản hỗ trợ Trusted Types hoặc tích hợp policy an toàn. Không tạo policy rộng chỉ để tương thích với thư viện cũ.

## Thu thập CSP violation report

Report giúp nhận diện tài nguyên bị chặn hoặc hành vi không phù hợp policy. Có thể cấu hình endpoint nhận báo cáo qua `report-to` và `Reporting-Endpoints`; `report-uri` vẫn hữu ích làm fallback cho một số browser.

Ví dụ response header:

```http
Reporting-Endpoints: csp="https://app.example.test/csp-reports"
Content-Security-Policy: default-src 'self'; object-src 'none'; base-uri 'self'; script-src 'self'; report-to csp; report-uri /csp-reports
```

`report-to csp` tham chiếu nhóm `csp` trong `Reporting-Endpoints`. `report-uri` là cơ chế cũ hơn nhưng vẫn có thể dùng làm fallback; hỗ trợ và định dạng report thay đổi theo trình duyệt. Kiểm tra browser mục tiêu và không giả định một endpoint sẽ nhận mọi định dạng.

### Dữ liệu trong report

Một báo cáo CSP có thể chứa:

- `document-uri`: tài liệu phát sinh vi phạm.
- `blocked-uri`: nguồn bị chặn; trình duyệt có thể rút gọn URL vì quyền riêng tư.
- `effective-directive`: directive thực tế áp dụng.
- `violated-directive`: directive bị vi phạm.
- `source-file`, `line-number`, `column-number`: vị trí liên quan nếu trình duyệt cung cấp.
- `disposition`: policy đang enforce hay report-only.
- `original-policy`: chuỗi policy áp dụng.
- `status-code`: status của tài liệu liên quan.

Không phải mọi browser đều gửi đủ trường. Một số report mới dùng định dạng Reporting API, trong khi `report-uri` có thể dùng định dạng CSP report cũ. Endpoint cần chấp nhận đúng các định dạng dự kiến và không giả định trường nào luôn tồn tại.

### Bảo vệ report endpoint

Report là dữ liệu do client gửi và có thể bị giả mạo hoặc gửi với số lượng lớn. Endpoint nhận report cần:

- Giới hạn kích thước body, số request và tốc độ theo nguồn phù hợp.
- Kiểm tra content type và schema; xử lý trường thiếu hoặc kiểu dữ liệu bất thường.
- Không render report bằng `innerHTML` hoặc đưa trực tiếp vào dashboard.
- Loại bỏ query string, fragment và thông tin nhạy cảm khỏi URL khi không cần.
- Không tin `document-uri`, `blocked-uri` hoặc `source-file` như bằng chứng xác thực.
- Có retention và quyền truy cập phù hợp; report có thể chứa hostname nội bộ hoặc dữ liệu URL.
- Nhóm các report lặp theo directive, host và policy version để giảm noise.

Không chặn người dùng hoặc kết luận có khai thác chỉ dựa trên một CSP report. Xác minh với release, request log và hành vi browser.

## Chuyển từ Report-Only sang enforce

Quy trình triển khai khuyến nghị:

1. **Inventory:** thu thập mọi nguồn script, style, image, font, API, worker, frame và form.
2. **Baseline:** xác định nguồn hợp lệ theo route và chức năng; phân biệt nguồn production với dev/test.
3. **Report-Only:** triển khai policy mục tiêu ở chế độ báo cáo trên môi trường QA hoặc nhóm người dùng giới hạn.
4. **Phân tích report:** xác minh từng host/directive, sửa ứng dụng hoặc loại nguồn không cần thiết.
5. **Refactor:** loại inline handler, eval, style attribute và các sink không an toàn.
6. **Enforce canary:** bật policy enforce cho một phần lưu lượng hoặc route có thể kiểm soát.
7. **Regression:** kiểm tra login, form, upload, API, iframe, worker, payment, analytics và luồng hỗ trợ.
8. **Expand:** mở rộng theo giai đoạn, theo dõi CSP report và lỗi frontend.
9. **Review:** loại bỏ ngoại lệ, cập nhật tài liệu và gán chủ sở hữu cho từng nguồn.

Không chuyển sang enforce chỉ vì số lượng report giảm. Cần xác minh chức năng hợp lệ không còn bị chặn và các report bất thường đã được xử lý. Report-Only không bảo vệ người dùng khỏi nội dung vi phạm trong giai đoạn quan sát.

## Kiểm thử bằng Chrome DevTools

### Kiểm tra response header

1. Mở ứng dụng lab và đăng nhập tài khoản giả lập.
2. Mở DevTools → Network, chọn request document chính.
3. Kiểm tra Response Headers có `Content-Security-Policy` hoặc `Content-Security-Policy-Report-Only` đúng môi trường.
4. Xác minh nonce trong header khớp với nonce trên script được phép.
5. Kiểm tra các response HTML khác như trang lỗi, trang đăng nhập và route SPA fallback.

Đừng chỉ kiểm tra một request asset. CSP của document chính điều khiển nhiều tài nguyên được tải bởi document đó; mỗi document/iframe có thể có policy riêng.

### Tạo vi phạm có kiểm soát

Trong trang lab, thử tải script từ origin không được cho phép:

```js
const script = document.createElement("script");
script.src = "https://untrusted.test/probe.js";
document.head.append(script);
```

Với policy enforce không cho phép host này, script phải bị chặn và Console hiển thị CSP violation. Với Report-Only, script vẫn có thể tải/chạy nhưng browser tạo report. Chỉ dùng URL thử nghiệm do bạn kiểm soát và không đưa mã độc vào lab.

Thử inline handler trong trang lab:

```html
<button onclick="console.log('inline handler')">Kiểm tra inline handler</button>
```

Nếu `script-src-attr 'none'` đang enforce, handler không được thực thi. Chuyển sang `addEventListener` để xác nhận cách triển khai hợp lệ.

### Kiểm tra directive theo chức năng

- `connect-src`: gọi API được cho phép và thử endpoint không nằm trong policy.
- `img-src`: tải ảnh cùng origin và ảnh từ host không được phép.
- `frame-src`: thử nhúng iframe được phép và không được phép.
- `frame-ancestors`: thử nhúng trang ứng dụng từ origin hợp lệ/không hợp lệ; kiểm tra response header của trang được nhúng.
- `form-action`: submit form tới origin được cho phép và một host lab không được phép.
- `worker-src`: khởi tạo worker từ nguồn được phép và không được phép.
- `base-uri`: thử thêm thẻ `<base>` tới host khác trong trang lab.
- `object-src`: xác nhận plugin/object không được tải khi policy là `'none'`.

`frame-ancestors` kiểm soát ai được nhúng trang hiện tại; `frame-src` kiểm soát trang hiện tại được tải iframe từ đâu. Hai directive không thay thế nhau. `frame-ancestors` không có hiệu lực khi khai báo qua `<meta http-equiv>`; cần gửi bằng HTTP response header.

Nếu phải hỗ trợ browser cũ không thực thi `frame-ancestors`, có thể cân nhắc `X-Frame-Options: DENY` hoặc `SAMEORIGIN` làm lớp tương thích. `X-Frame-Options` không biểu đạt được allowlist nhiều origin như `frame-ancestors`; tránh cấu hình hai header mâu thuẫn nhau.

## Kiểm thử bằng Playwright

Browser automation có thể xác minh header, lỗi Console và hành vi DOM. Ví dụ dưới đây là khung Playwright cho ứng dụng lab:

```js
import { test, expect } from "@playwright/test";

test("CSP chặn script từ origin không được phép", async ({ page }) => {
  const violations = [];
  page.on("console", (message) => {
    if (message.type() === "error" && /Content Security Policy/i.test(message.text())) {
      violations.push(message.text());
    }
  });

  const response = await page.goto("https://app.example.test/account");
  expect(response.headers()["content-security-policy"]).toContain("object-src 'none'");

  await page.evaluate(() => {
    const script = document.createElement("script");
    script.src = "https://untrusted.test/probe.js";
    document.head.append(script);
  });

  await expect.poll(() => violations.length).toBeGreaterThan(0);
});
```

Ví dụ cần được điều chỉnh theo cách ứng dụng ghi nhận report và browser engine. Không nên chỉ dựa vào nội dung Console vì thông điệp có thể thay đổi giữa phiên bản trình duyệt. Có thể kiểm tra thêm rằng một marker do script không được phép tạo ra không xuất hiện, đồng thời script hợp lệ vẫn hoạt động.

Chạy test cho cả policy enforce và Report-Only. Ở chế độ Report-Only, marker của script thử nghiệm có thể xuất hiện vì browser không chặn; test phải xác nhận report được tạo và ghi nhận đúng disposition. Ở chế độ enforce, marker không được xuất hiện.

## Ma trận kiểm thử CSP

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| CSP-01 | Script cùng origin được phép | Tải và thực thi thành công |
| CSP-02 | Script từ host không được phép | Bị chặn khi enforce; được report khi Report-Only |
| CSP-03 | Inline script không nonce/hash | Bị chặn khi policy không cho inline |
| CSP-04 | Inline script có nonce đúng | Được thực thi |
| CSP-05 | Nonce sai hoặc nonce cũ | Bị chặn |
| CSP-06 | Nonce thay đổi giữa hai response HTML | Mỗi response dùng nonce riêng |
| CSP-07 | Inline event handler | Bị chặn với `script-src-attr 'none'` |
| CSP-08 | `eval()` hoặc `new Function()` | Bị chặn khi không cho `unsafe-eval` |
| CSP-09 | CSS/inline style không được phép | Bị chặn theo style directive |
| CSP-10 | API nằm trong `connect-src` | Kết nối hoạt động |
| CSP-11 | API ngoài `connect-src` | Kết nối bị chặn |
| CSP-12 | Iframe không được phép | Bị chặn bởi `frame-src` hoặc `frame-ancestors` theo chiều kiểm tra |
| CSP-13 | Form submit tới host không được phép | Bị chặn bởi `form-action` |
| CSP-14 | Object/embed | Bị chặn với `object-src 'none'` |
| CSP-15 | DOM sink không có Trusted Types | Bị từ chối khi Trusted Types được enforce trên browser hỗ trợ |
| CSP-16 | Vi phạm được gửi tới report endpoint | Endpoint nhận đúng schema, giới hạn size và không render HTML |
| CSP-17 | Trang lỗi hoặc SPA fallback | Header policy vẫn có mặt và không làm hỏng luồng hợp lệ |
| CSP-18 | Service worker/worker | Tải đúng nguồn theo `worker-src` và policy liên quan |

Với mỗi ca, lưu route, browser/version, policy version, directive, disposition, kết quả tải/thực thi và report ID nếu có. Che URL chứa dữ liệu cá nhân hoặc token trong bằng chứng.

## Lỗi cấu hình thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| `default-src *` hoặc `script-src https:` | Cho phép quá nhiều nguồn script | Dùng allowlist cụ thể, nonce/hash và rà soát host |
| `unsafe-inline` trong script-src | Làm giảm khả năng CSP ngăn inline XSS | Loại inline handler, dùng nonce/hash |
| `unsafe-eval` | Cho phép eval và một số sink thực thi chuỗi | Nâng cấp/thay thư viện phụ thuộc eval |
| Nonce cố định | Attacker có thể tái sử dụng nếu biết nonce | Tạo nonce mật mã mới theo response |
| Nonce bị cache hoặc lộ | Nhiều client dùng chung nonce hoặc nonce bị rò rỉ | Kiểm soát cache, log và template |
| Chỉ khai báo `default-src` | Bỏ sót directive không fallback | Khai báo rõ `base-uri`, `form-action`, `frame-ancestors` và directive cần thiết |
| Dùng `frame-src` để chống clickjacking | Không giới hạn ai được nhúng trang hiện tại | Dùng `frame-ancestors` |
| Đặt `frame-ancestors` trong meta | Browser bỏ qua directive này trong meta policy | Gửi qua response header |
| Cho phép host CDN rộng | Script trên host được tin cậy có thể bị lợi dụng | Ghim phiên bản, SRI và nguồn hẹp |
| Report endpoint không giới hạn | Có thể bị spam hoặc gây quá tải | Rate limit, giới hạn body, validate schema |
| Chuyển enforce quá sớm | Chức năng hợp lệ bị chặn | Report-Only, phân tích và rollout theo giai đoạn |
| Chỉ kiểm tra trang chủ | Route khác hoặc error page không có policy | Kiểm tra toàn bộ document response và redirect |

## Checklist trước khi phát hành

- [ ] Inventory nguồn script, style, image, font, API, frame, form và worker.
- [ ] Có policy theo nhu cầu thực tế, không dùng wildcard rộng.
- [ ] Không còn inline handler hoặc `eval` ngoài ngoại lệ đã review.
- [ ] Nonce được tạo ngẫu nhiên cho từng response và không bị cache/lộ.
- [ ] Hash được tính từ nội dung chính xác và cập nhật khi code đổi.
- [ ] `object-src`, `base-uri`, `frame-ancestors` và `form-action` được khai báo phù hợp.
- [ ] `connect-src`, `worker-src` và các directive tài nguyên phản ánh đúng kiến trúc.
- [ ] Report-Only đã được quan sát và false positive đã được phân loại.
- [ ] Report endpoint giới hạn kích thước, rate, schema và quyền truy cập.
- [ ] Trusted Types policy hẹp và dùng sanitizer đã được kiểm thử nếu áp dụng.
- [ ] Header có mặt trên route, error response và SPA fallback cần thiết.
- [ ] Đã kiểm thử login, upload, payment, iframe, worker và các tích hợp bên thứ ba.
- [ ] Có canary, monitoring, rollback và người chịu trách nhiệm.

## Thực hành tổng hợp

Triển khai CSP cho `https://app.example.test` theo các yêu cầu:

1. JavaScript và CSS chính chỉ tải từ cùng origin.
2. Inline bootstrap script cần được cho phép bằng nonce ngẫu nhiên theo response.
3. Không cho inline event handler và `eval`.
4. API chỉ kết nối tới `https://api.example.test` cùng origin.
5. Không cho plugin/object; chỉ cho phép form submit về cùng origin.
6. Trang không được nhúng trong iframe của origin khác.
7. Worker chỉ tải từ cùng origin.
8. Bật báo cáo CSP và thử policy mới ở Report-Only trước khi enforce.

Thực hiện theo trình tự:

1. Lập inventory tài nguyên bằng Network và mã nguồn của ứng dụng lab.
2. Tạo policy Report-Only theo các yêu cầu trên.
3. Chạy các luồng đăng nhập, đọc hồ sơ, cập nhật hồ sơ, upload và preview.
4. Phân loại từng report; sửa code hoặc bổ sung nguồn hợp lệ có chủ sở hữu.
5. Loại inline handler, inline style và eval bằng refactor.
6. Triển khai nonce theo response, xác minh nonce header/HTML khớp và thay đổi qua từng response.
7. Thử các payload kiểm tra XSS an toàn và xác nhận script không được phép bị chặn.
8. Bật Trusted Types trong môi trường hỗ trợ, xử lý sink bằng policy hẹp hoặc API DOM an toàn.
9. Chuyển policy sang enforce ở QA/canary; chạy ma trận 18 ca kiểm thử.
10. Theo dõi report, lỗi frontend và chức năng hợp lệ; chuẩn bị rollback nếu có hồi quy.

Sản phẩm bàn giao gồm inventory tài nguyên, CSP Report-Only và enforce policy, cách tạo nonce, kết quả report, ma trận test, bằng chứng DevTools đã che dữ liệu nhạy cảm và kế hoạch rollout/rollback.

## Ghi nhớ

- CSP là policy do server gửi để giới hạn nguồn và hành vi nội dung trong trình duyệt.
- Report-Only chỉ quan sát; policy enforce mới chặn nội dung vi phạm.
- Nonce phải ngẫu nhiên, theo từng response và không được cache/lộ.
- Hash phù hợp với inline code tĩnh; mọi thay đổi nội dung cần tính lại hash.
- Loại inline handler và `eval`; ưu tiên file script cùng origin, nonce/hash và DOM API an toàn.
- `frame-ancestors` giới hạn ai được nhúng trang và phải gửi bằng HTTP header.
- Trusted Types cần policy hẹp và sanitizer; nó không tự làm sạch dữ liệu.
- CSP report là dữ liệu không tin cậy; cần giới hạn, validate và bảo vệ endpoint.
- Triển khai theo giai đoạn, kiểm thử luồng hợp lệ và chuẩn bị rollback.
