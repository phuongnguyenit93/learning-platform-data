# CSP test

Kiểm thử Content Security Policy (CSP) là quá trình xác minh trình duyệt thực sự áp dụng đúng chính sách mà ứng dụng dự định triển khai. Một header CSP nhìn có vẻ chặt chẽ chưa đủ để kết luận ứng dụng an toàn. Cần kiểm tra policy trên response thực tế, xác nhận tài nguyên hợp lệ vẫn hoạt động, thử các hành vi phải bị chặn và đánh giá những đường đi có thể làm CSP mất tác dụng.

Trong phạm vi bảo mật trình duyệt, CSP là một lớp phòng vệ quan trọng trước Cross-Site Scripting (XSS), tải tài nguyên ngoài ý muốn, nhúng trang trái phép và một số hành vi điều hướng hoặc gửi biểu mẫu. CSP hoạt động cùng Same-Origin Policy, CORS, cookie, Trusted Types và các cơ chế cách ly khác. Nó không thay thế việc encode đầu ra, xử lý đầu vào, kiểm soát quyền truy cập hay phòng chống CSRF.

Mục tiêu của CSP test là trả lời được bốn câu hỏi: policy nào đang có hiệu lực, tài nguyên nào được phép, hành vi nào bị chặn và liệu kẻ tấn công có thể lợi dụng một nguồn được cho phép để thực thi mã hay không.

## CSP được áp dụng ở đâu?

Trình duyệt nhận CSP chủ yếu qua response header `Content-Security-Policy`. Ứng dụng có thể gửi header này từ web server, reverse proxy, CDN hoặc framework. CSP cũng có thể được khai báo bằng thẻ `meta` trong HTML, nhưng cách này có giới hạn và không thay thế được response header trong triển khai bảo mật đầy đủ.

Ví dụ policy cơ bản:

~~~http
Content-Security-Policy: default-src 'self'; object-src 'none'; base-uri 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; form-action 'self'
~~~

Policy này giới hạn nhiều nhóm tài nguyên về cùng origin, cấm plugin object, giới hạn nguồn của phần tử `base`, không cho trang bị nhúng trong frame, và chỉ cho biểu mẫu gửi về cùng origin. Đây là ví dụ để bắt đầu kiểm thử; policy thực tế phải dựa trên tài nguyên mà ứng dụng thật sự cần.

### Những điểm cần nhớ khi đọc policy

- Các directive như `script-src`, `style-src`, `img-src`, `connect-src`, `font-src`, `media-src`, `object-src` và một số directive tải tài nguyên khác có thể kế thừa fallback từ `default-src` khi không được khai báo riêng.
- `base-uri`, `form-action` và `frame-ancestors` không dùng `default-src` làm fallback. Nếu cần kiểm soát các hành vi này, phải khai báo riêng.
- `frame-src` kiểm soát frame mà trang hiện tại tải; `frame-ancestors` kiểm soát website nào được phép nhúng trang hiện tại. Hai directive giải quyết hai hướng khác nhau.
- `Content-Security-Policy` thực thi chính sách. `Content-Security-Policy-Report-Only` chỉ báo cáo vi phạm của policy đó mà không chặn theo policy Report-Only.
- Nhiều CSP header hoặc nhiều policy được áp dụng đồng thời. Trình duyệt thực thi tất cả policy; policy bổ sung có thể làm giới hạn chặt hơn, không dùng header sau để nới lỏng header trước.

Khi có nhiều lớp hạ tầng cùng thêm header, một policy hợp lệ ở ứng dụng có thể bị policy từ proxy hoặc CDN siết thêm. Ngược lại, một trang HTML có thể nhận header khác với trang lỗi hoặc response sau redirect. CSP test phải xem response mà browser thực sự nhận ở từng luồng quan trọng.

## Xác định phạm vi kiểm thử

Trước khi thử, lập danh sách các loại trang và luồng ứng dụng: trang đăng nhập, dashboard, trang có nội dung do người dùng tạo, trang thanh toán, trang nhúng iframe, trang dùng worker, trang tải file và trang có tích hợp bên thứ ba. Mỗi loại có thể cần policy khác nhau.

Ghi nhận các tài nguyên hợp lệ mà ứng dụng cần tải:

- Script và style nội bộ, script inline có nonce hoặc hash.
- Ảnh, font, media và tài nguyên từ CDN.
- Kết nối `fetch`, XHR, WebSocket và EventSource.
- iframe, worker, manifest và object nếu ứng dụng còn sử dụng.
- Nơi nhận biểu mẫu và các trang được phép nhúng ứng dụng.

Ghi nhận các môi trường cần kiểm thử: development, staging, production-like, browser mục tiêu và phiên bản browser. Tránh thử payload hoặc thay đổi policy trực tiếp trên hệ thống production nếu chưa có kế hoạch và quyền kiểm thử. Dùng dữ liệu giả, tài khoản thử nghiệm và origin do nhóm quản lý.

## Kiểm tra CSP trên response thực tế

Mở DevTools, chọn tab Network và tải lại trang. Chọn request loại Document rồi xem phần Response Headers. Xác nhận:

1. Response có `Content-Security-Policy` hoặc `Content-Security-Policy-Report-Only` đúng như thiết kế.
2. Các directive quan trọng xuất hiện và không bị ghi đè bởi cấu hình ở reverse proxy hoặc CDN.
3. Không có header CSP thứ hai ngoài dự kiến.
4. Trang lỗi, trang đăng nhập, trang redirect và các route đặc biệt cũng có policy phù hợp.
5. Header được gửi trong response HTML thực tế; việc cấu hình trong file hoặc ở một route khác không chứng minh browser đã nhận policy.

Có thể kiểm tra nhanh response bằng `curl`:

~~~bash
curl -sS -D - -o /dev/null https://app.example.test/
~~~

Lệnh này hiển thị response headers của một GET request và bỏ phần body. Cần kiểm tra đúng hostname, đường dẫn và trạng thái đăng nhập của luồng đang đánh giá; response của `HEAD`, request chưa đăng nhập hoặc một route khác có thể mang header khác.

Nếu ứng dụng khai báo CSP bằng `<meta http-equiv="Content-Security-Policy">`, kiểm tra vị trí thẻ trong HTML và các giới hạn của cơ chế meta. Một số directive, trong đó có `frame-ancestors`, không có tác dụng khi khai báo qua meta; `Content-Security-Policy-Report-Only` cũng không thể được bật bằng meta. Với chính sách bảo mật quan trọng, nên cấu hình qua HTTP response header.

## Kiểm thử hành vi được phép và bị chặn

Một CSP test tốt cần cả kiểm thử dương tính và âm tính. Kiểm thử dương tính chứng minh chức năng hợp lệ vẫn chạy; kiểm thử âm tính chứng minh browser chặn đúng hành vi nằm ngoài policy.

| Nhóm kiểm thử | Hành vi hợp lệ cần chạy | Hành vi cần bị chặn |
|---|---|---|
| Script | Script cùng origin hoặc script có nonce/hash hợp lệ | Inline script không được cấp nonce/hash, `eval` khi không được cho phép, script từ host ngoài danh sách |
| Style | Stylesheet hợp lệ và style được cấp phép | Inline style hoặc stylesheet từ nguồn không được phép |
| Image và media | Ảnh, font và media từ nguồn đã duyệt | Tài nguyên từ host không được phép hoặc scheme không mong muốn |
| Kết nối | API, WebSocket và EventSource đã khai báo | `fetch` hoặc kết nối đến origin ngoài `connect-src` |
| Frame | Frame từ nguồn được phép tải nếu cần | Website không được phép nhúng trang khi `frame-ancestors` giới hạn |
| Form | Form gửi đến endpoint hợp lệ | Form submit đến origin không được phép |
| Base URL | Thẻ `base` hợp lệ nếu ứng dụng cần | Thẻ `base` do nội dung không tin cậy chèn vào |
| Worker và object | Worker hợp lệ theo thiết kế | Worker hoặc object từ nguồn ngoài policy |

Không chỉ quan sát Console có thông báo vi phạm. Hãy xác nhận hành vi thực tế: script bị chặn không được thực thi, request bị giới hạn không hoàn thành, frame không thể nhúng và form không gửi đến đích ngoài policy. Console là bằng chứng hữu ích nhưng cần kết hợp với trạng thái trang, Network và sự kiện kiểm thử.

## Kiểm thử script, nonce và hash

Script là trọng tâm của CSP khi phòng chống XSS. Một policy dựa trên nonce hoặc hash thường an toàn hơn một allowlist host rộng hoặc `'unsafe-inline'`.

### Kiểm thử nonce

Nonce là giá trị ngẫu nhiên do server tạo cho một response HTML. Cùng một nonce phải xuất hiện trong CSP header và trên các thẻ script được phép chạy inline. Nonce cần đủ ngẫu nhiên, khó đoán và được tạo lại cho mỗi response HTML được sinh mới.

Ví dụ tạo nonce trong Node.js:

~~~javascript
import { randomBytes } from 'node:crypto';

function renderPage(req, res) {
  const nonce = randomBytes(16).toString('base64');

  res.setHeader(
    'Content-Security-Policy',
    `default-src 'self'; script-src 'self' 'nonce-${nonce}'; object-src 'none'; base-uri 'self'`
  );
  res.setHeader('Cache-Control', 'no-store');

  res.render('page', { nonce });
}
~~~

Thẻ script hợp lệ trong template có thể dùng nonce được truyền vào:

~~~html
<script nonce="{{nonce}}">
  window.appBootstrapped = true;
</script>
<script>
  window.untrustedInlineCodeRan = true;
</script>
~~~

Trong template engine thật, phải dùng cú pháp escape an toàn và đưa nonce từ cùng response vào header lẫn markup. Đoạn script thứ nhất được phép chạy; script thứ hai không có nonce nên phải bị chặn nếu không có nguồn cho phép khác.

Các kiểm tra cần thực hiện:

- Nonce trong header trùng với nonce của script hợp lệ trong HTML response.
- Script inline không có nonce hoặc hash hợp lệ bị chặn.
- Nonce không phải chuỗi cố định được hard-code hoặc tái sử dụng giữa các response HTML được sinh mới.
- Cache không phục vụ HTML chứa nonce cũ trong khi header hoặc nội dung đã thay đổi. Nếu có caching, phải thiết kế cách tạo và phân phối nonce nhất quán cho từng response.
- Không cấp nonce cho script có nội dung hoặc nguồn do người dùng kiểm soát.

Nonce không phải bí mật có thể bảo vệ ứng dụng sau khi mã JavaScript tùy ý đã chạy. Mục đích của nonce là cho phép browser phân biệt các script được server chủ động cấp phép với inline script không được cấp phép trong quá trình phân tích tài liệu.

### Kiểm thử hash

Hash-source cho phép một đoạn inline script cụ thể chạy khi nội dung của nó khớp hash trong policy. Chỉ cần thay đổi khoảng trắng hoặc ký tự trong nội dung script là hash có thể không còn khớp. Vì vậy, cần kiểm tra hash được tạo từ đúng byte của nội dung cuối cùng mà server gửi.

Ví dụ về dạng directive:

~~~http
Content-Security-Policy: script-src 'self' 'sha256-BASE64_HASH_OF_SCRIPT'; object-src 'none'; base-uri 'self'
~~~

Không dùng chuỗi placeholder này trong production. Build pipeline cần tính hash từ nội dung script chính xác và cập nhật policy tương ứng. Nếu ứng dụng dùng script ngoài có Subresource Integrity, kiểm tra cả `integrity` và CSP hash-source theo quy tắc của browser mục tiêu.

### Kiểm thử các từ khóa làm yếu policy

Tìm và đánh giá kỹ các giá trị:

- `'unsafe-inline'` có thể cho phép inline script hoặc style không được nonce/hash bảo vệ. Với `script-src` có nonce-source hoặc hash-source, browser hiện đại thường bỏ qua `'unsafe-inline'`; từ khóa này vẫn có thể làm yếu fallback cho browser cũ và gây hiểu nhầm khi policy thay đổi.
- `'unsafe-eval'` cho phép các cơ chế thực thi chuỗi như `eval()` hoặc `new Function()` trong ngữ cảnh bị áp dụng.
- Wildcard host, scheme rộng như `https:` hoặc CDN có nội dung do người khác kiểm soát có thể mở rộng bề mặt script.
- `data:` trong `script-src` có thể tạo thêm đường thực thi không mong muốn; không thêm chỉ để làm một tính năng chạy được.

Đừng xóa một từ khóa chỉ vì nó bị đánh dấu rủi ro trong công cụ phân tích. Xác định thư viện hoặc chức năng nào đang phụ thuộc vào nó, thay thế bằng cách triển khai an toàn hơn rồi kiểm thử lại.

## Kiểm thử script loader và strict-dynamic

Ứng dụng hiện đại có thể dùng một script loader để tải module hoặc script con. Khi policy sử dụng nonce/hash cùng `'strict-dynamic'`, browser hỗ trợ CSP3 có thể truyền sự tin cậy từ script được cấp nonce/hash sang script mà script đó tải động. Trong các browser hiểu `'strict-dynamic'`, host allowlist và scheme source trong cùng `script-src` có thể bị bỏ qua cho mục đích quyết định tải script theo cơ chế này.

Do đó, kiểm thử cần tập trung vào script loader:

1. Script loader được cấp nonce/hash có phải mã đáng tin và có được review không?
2. URL mà loader nhận có thể bị dữ liệu người dùng hoặc DOM điều khiển không?
3. Loader có allowlist rõ ràng cho tên module hoặc đường dẫn script không?
4. Loader có thể bị lợi dụng để tải script từ host do kẻ tấn công kiểm soát không?
5. Hành vi trên browser hỗ trợ và không hỗ trợ `'strict-dynamic'` có đúng với fallback đã thiết kế không?

Ví dụ rủi ro là một loader được cấp nonce nhưng nhận URL script trực tiếp từ query string rồi tạo thẻ `script`. CSP có thể tin loader và script con mà loader thêm vào. Vì vậy, nonce không tự động làm cho mọi script tải động an toàn; logic lựa chọn URL của loader phải được kiểm tra như một phần của ranh giới tin cậy.

## Kiểm tra các directive quan trọng

### `object-src` và `base-uri`

Với ứng dụng hiện đại, thường nên có `object-src 'none'` để chặn nội dung plugin/object không cần thiết. `base-uri 'self'` hoặc `base-uri 'none'` giới hạn nơi thẻ `base` có thể trỏ tới, giảm nguy cơ nội dung chèn thẻ base làm thay đổi cách phân giải URL tương đối.

Kiểm thử bằng một trang fixture có `<object>` hoặc `<embed>` từ nguồn ngoài và một thẻ `<base>` trỏ tới origin thử nghiệm. Xác nhận hành vi bị chặn hoặc không làm thay đổi URL theo policy. Không cần cài plugin nguy hiểm; chỉ xác minh browser áp dụng directive qua sự kiện và DOM.

### `frame-ancestors` và chống clickjacking

`frame-ancestors` xác định origin nào được phép nhúng document hiện tại. Ví dụ:

~~~http
Content-Security-Policy: frame-ancestors 'none'
~~~

Kiểm thử từ một trang thử nghiệm khác origin tạo iframe trỏ tới ứng dụng. Với `'none'`, browser phải chặn việc nhúng. Với `'self'`, chỉ trang cùng origin được phép làm ancestor theo policy. Nếu ứng dụng cần được nhúng bởi một cổng đối tác, khai báo chính xác origin đó và kiểm tra cả trường hợp lồng nhiều cấp frame.

`frame-ancestors` phải được gửi bằng HTTP response header; khai báo trong meta không có tác dụng. Kiểm tra sự tương thích với `X-Frame-Options` cũ nếu hệ thống vẫn gửi header này. CSP `frame-ancestors` là cơ chế hiện đại để điều khiển ancestor; không giả định header cũ có thể thay thế mọi trường hợp.

### `form-action` và `connect-src`

`form-action` giới hạn nơi form có thể submit. Thử submit form đến một origin ngoài danh sách và xác nhận browser chặn. Directive này hỗ trợ giảm rủi ro gửi dữ liệu ngoài ý muốn nhưng không thay thế CSRF token, SameSite cookie hoặc kiểm tra quyền ở server.

`connect-src` giới hạn các giao tiếp từ API như `fetch`, XHR, WebSocket, EventSource và Beacon theo quy tắc CSP. Kiểm thử từng endpoint cần thiết, đặc biệt khi ứng dụng có nhiều API, analytics, telemetry hoặc realtime service. Một endpoint bị chặn có thể làm ứng dụng mất chức năng dù script vẫn chạy.

### `frame-src`, `worker-src` và các nguồn tài nguyên khác

Kiểm tra iframe mà trang tải bằng `frame-src`, worker bằng `worker-src`, ảnh bằng `img-src`, font bằng `font-src`, media bằng `media-src` và stylesheet bằng `style-src`. Đừng giả định `default-src` bao phủ mọi directive; hãy kiểm tra fallback cụ thể và khai báo rõ directive có tác động bảo mật cao.

## Kiểm thử Report-Only và báo cáo vi phạm

`Content-Security-Policy-Report-Only` hữu ích khi thử policy mới mà chưa muốn chặn chức năng. Cần xác nhận:

- Header Report-Only xuất hiện trên response cần thử.
- Các thao tác vi phạm tạo sự kiện hoặc report theo browser hỗ trợ.
- Tài nguyên không bị chặn chỉ bởi policy Report-Only.
- Khi chuyển sang `Content-Security-Policy`, cùng vi phạm đó bị browser chặn.
- Endpoint report xử lý payload sai định dạng, batch lớn, dữ liệu trùng và report bị giả mạo.
- Báo cáo được giảm thiểu dữ liệu nhạy cảm và không tạo cảnh báo quá mức.

Ví dụ cấu hình dùng Reporting API mới và giữ `report-uri` cho browser cũ trong giai đoạn tương thích:

~~~http
Reporting-Endpoints: csp="https://reports.example.test/csp"
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; report-to csp; report-uri https://reports.example.test/csp
~~~

Đừng coi việc không nhận report là bằng chứng rằng không có vi phạm. Browser có thể không hỗ trợ loại report, report có thể bị trì hoãn hoặc mất khi thiết bị ngoại tuyến, và endpoint có thể từ chối request. Dùng DevTools và kiểm thử hành vi trực tiếp để xác nhận policy.

## Tự động hóa CSP test bằng Playwright

Có thể kiểm tra response header và hành vi của browser trong pipeline. Ví dụ dưới đây giả định ứng dụng có route fixture `/__test/csp-inline` trả về trang chứa một script có nonce hợp lệ và một inline script không có nonce. Route fixture chỉ nên tồn tại trong môi trường test.

~~~javascript
import { test, expect } from '@playwright/test';

test('serves the expected CSP header', async ({ request }) => {
  const response = await request.get('/__test/csp-inline');
  expect(response.ok()).toBeTruthy();

  const csp = response.headers()['content-security-policy'];
  expect(csp).toContain("object-src 'none'");
  expect(csp).toContain("base-uri 'self'");
  expect(csp).toContain('script-src');
  expect(csp).not.toContain("'unsafe-eval'");
});

test('allows a nonce script and blocks an unapproved inline script', async ({ page }) => {
  await page.addInitScript(() => {
    window.__cspEvents = [];
    document.addEventListener('securitypolicyviolation', (event) => {
      window.__cspEvents.push({
        directive: event.effectiveDirective,
        blockedURI: event.blockedURI,
        disposition: event.disposition
      });
    });
  });

  await page.goto('/__test/csp-inline');

  await expect.poll(async () => page.evaluate(() => window.allowedScriptRan === true))
    .toBe(true);

  const result = await page.evaluate(() => ({
    blockedScriptRan: window.blockedScriptRan === true,
    violations: window.__cspEvents
  }));

  expect(result.blockedScriptRan).toBe(false);
  expect(result.violations.some((item) =>
    item.directive === 'script-src' || item.directive === 'script-src-elem'
  )).toBe(true);
});
~~~

Đây là ví dụ khung; cần bổ sung kiểu global cho TypeScript và fixture tương ứng trong ứng dụng. Nếu browser không phát sự kiện trong thời gian mong đợi, kiểm tra Console, header và HTML thực tế trước khi kết luận. Không dùng `page.evaluate()` để chứng minh một script inline trong document bị CSP chặn hoặc được cho phép: lệnh evaluate của automation có thể đi qua giao diện điều khiển đặc quyền và không mô phỏng chính xác cách parser xử lý thẻ script.

Nên có thêm test cho nonce rotation, `frame-ancestors`, `form-action`, `connect-src`, `worker-src`, CSP trên route đăng nhập và trang lỗi. Chỉ kiểm tra chuỗi header không chứng minh toàn bộ hành vi browser.

## Các lỗi thường gặp khi kiểm thử

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ kiểm tra header mà không tải trang | Không biết script hoặc tài nguyên thực tế có bị chặn không | Kiểm tra response và runtime trong browser |
| Dùng `'unsafe-inline'` để sửa nhanh | Làm giảm khả năng chặn inline XSS | Chuyển sang nonce/hash và refactor script inline |
| Cho phép toàn bộ CDN hoặc `https:` | Có thể tin nhầm script không đáng tin trên host được cho phép | Giới hạn nguồn, dùng nonce/hash, kiểm tra script loader và SRI |
| Quên `base-uri` | Thẻ base bị chèn có thể đổi URL tương đối | Khai báo `base-uri 'self'` hoặc `'none'` |
| Quên `object-src` | Nội dung plugin/object có thể được tải nếu browser hỗ trợ | Khai báo `object-src 'none'` khi không cần |
| Nhầm `frame-src` với `frame-ancestors` | Kiểm soát sai hướng nhúng frame | Kiểm tra cả frame mà trang tải và ancestor nhúng trang |
| Chuyển Report-Only sang enforce quá sớm | Chức năng hợp lệ có thể bị chặn | Phân loại report, sửa policy và rollout theo giai đoạn |
| Tin rằng CSP thay thế encode đầu ra | XSS vẫn có thể xảy ra qua ngữ cảnh hoặc nguồn được phép | Kết hợp encoding, sanitization phù hợp và kiểm soát dữ liệu |
| Chỉ test một browser | Bỏ sót khác biệt hỗ trợ directive và report | Kiểm thử ma trận browser mục tiêu |

## Quy trình CSP test trước khi phát hành

1. Thu thập tài nguyên và luồng hợp lệ của ứng dụng, xác định origin bên thứ ba thực sự cần dùng.
2. Kiểm tra policy hiện tại, các header trùng lặp và vị trí thêm header ở ứng dụng, proxy hoặc CDN.
3. Đưa policy mới vào Report-Only trong staging hoặc nhóm người dùng thử nghiệm.
4. Phân tích report, đối chiếu với Network và mã nguồn; chỉ thêm nguồn khi có lý do chức năng rõ ràng.
5. Kiểm thử nonce/hash, script loader, `strict-dynamic` nếu dùng, các directive frame/form/connect và tài nguyên cần thiết.
6. Chạy kiểm thử âm tính với payload vô hại trong fixture để xác nhận hành vi bị chặn.
7. Chuyển policy sang enforce theo từng giai đoạn, theo dõi lỗi chức năng và có kế hoạch rollback.
8. Lưu policy đã phát hành, kết quả test, browser/version, route và ngoại lệ được chấp thuận để có thể so sánh ở lần cập nhật sau.

## Checklist CSP test

- [ ] Đã kiểm tra CSP trên response HTML thực tế của các route quan trọng.
- [ ] Đã kiểm tra policy từ ứng dụng, proxy, CDN và các header CSP trùng lặp.
- [ ] Đã xác minh các directive quan trọng và fallback của `default-src`.
- [ ] Đã kiểm thử tài nguyên hợp lệ tiếp tục hoạt động.
- [ ] Inline script không được cấp nonce/hash bị chặn.
- [ ] Nonce được tạo ngẫu nhiên, khớp header/markup và không bị cache sai.
- [ ] Hash được tính từ đúng nội dung script và cập nhật khi nội dung thay đổi.
- [ ] Đã rà soát `'unsafe-inline'`, `'unsafe-eval'`, wildcard và host allowlist rộng.
- [ ] Đã kiểm thử script loader và `strict-dynamic` nếu policy sử dụng.
- [ ] Đã kiểm thử `object-src`, `base-uri`, `frame-ancestors`, `form-action`, `connect-src` và worker nếu ứng dụng dùng.
- [ ] Report-Only được kiểm thử trước khi enforce và report endpoint xử lý an toàn.
- [ ] Đã kiểm thử trên các browser mục tiêu và route đặc biệt.
- [ ] Kết quả test có bằng chứng runtime, không chỉ có chuỗi header.

## Câu hỏi tự kiểm tra

1. Vì sao `frame-src` và `frame-ancestors` không thể thay thế cho nhau?
2. Khi nào `default-src` được dùng làm fallback, và directive nào cần khai báo riêng?
3. Nonce cần được tạo và gắn vào response như thế nào để CSP hoạt động đúng?
4. Vì sao một script loader được cấp nonce vẫn có thể tạo ra rủi ro nếu nhận URL từ dữ liệu không tin cậy?
5. CSP Report-Only khác policy enforce ở hành vi của browser ra sao?
6. Vì sao CSP test cần cả kiểm thử dương tính, âm tính và xác minh trên browser thực tế?

Một CSP chỉ có giá trị khi trình duyệt thực thi đúng policy trên những trang và luồng mà người dùng thực sự sử dụng. Hãy kiểm tra response header, nguồn script, hành vi runtime, các đường tải động và tác động đến chức năng. Sau khi phát hành, tiếp tục theo dõi report và chạy lại các kiểm thử quan trọng mỗi khi thay đổi template, dependency, CDN hoặc kiến trúc frontend.
