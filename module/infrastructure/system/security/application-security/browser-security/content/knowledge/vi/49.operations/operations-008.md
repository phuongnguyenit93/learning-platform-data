# Browser compatibility

Browser compatibility trong vận hành bảo mật là quá trình bảo đảm ứng dụng giữ được các thuộc tính an toàn trên những trình duyệt, phiên bản, hệ điều hành và môi trường nhúng mà người dùng thực tế sử dụng. Một header bảo mật được cấu hình đúng trên server chưa chắc tạo ra cùng hành vi trên mọi browser. Một API có thể chưa được hỗ trợ, được hỗ trợ một phần, bị tắt bởi cài đặt riêng tư hoặc hoạt động khác trong WebView và trình duyệt doanh nghiệp.

Vì vậy, vận hành cần biết tính năng bảo mật nào được hỗ trợ ở từng nhóm client, kiểm thử hành vi trên browser thực tế, chọn fallback có giới hạn và theo dõi thay đổi sau mỗi lần nâng cấp. Mục tiêu là giữ mức bảo vệ nhất quán mà không làm hỏng luồng sử dụng hợp lệ.

Trong module này, browser compatibility liên quan trực tiếp đến Same-Origin Policy, CORS, cookie, CSP, Trusted Types, security headers, service worker, Reporting API và các cơ chế cách ly. Những cơ chế này nằm ở nhiều tầng khác nhau: một số được browser thực thi, một số cần server cấu hình, một số là API JavaScript. Không thể dùng một phép kiểm tra chung để kết luận tất cả đều hoạt động.

## Vì sao tương thích trình duyệt là vấn đề vận hành bảo mật?

Sự khác nhau giữa browser có thể ảnh hưởng đến bảo mật theo nhiều cách:

- **Không hỗ trợ API:** ứng dụng dựa vào một API bảo vệ DOM hoặc lưu trữ nhưng browser cũ không có API đó.
- **Hỗ trợ khác nhau:** cùng một header hoặc directive có thể có mức hỗ trợ khác nhau giữa phiên bản và engine.
- **Khác biệt mặc định:** cookie, quyền riêng tư, chặn theo dõi, third-party storage và chính sách tải tài nguyên có thể khác theo browser hoặc cài đặt người dùng.
- **Môi trường nhúng:** WebView, browser trong ứng dụng, kiosk và thiết bị doanh nghiệp có thể dùng engine hoặc phiên bản cũ hơn browser độc lập.
- **Thay đổi theo phiên bản:** một lần cập nhật browser có thể thay đổi cách xử lý cookie, CSP, popup, storage, certificate hoặc request cross-origin.
- **Cấu hình theo tổ chức:** extension, enterprise policy, proxy TLS inspection và phần mềm bảo mật endpoint có thể ảnh hưởng hành vi mà nhóm phát triển không thấy trên máy cá nhân.

Không nên chỉ hỏi “trang có mở được không?”. Cần hỏi thêm: policy có được thực thi không, dữ liệu nào được gửi, cookie nào được đính kèm, script nào được phép chạy, trang có bị nhúng trái phép hay không và fallback có vô tình làm giảm bảo vệ không.

## Xây dựng ma trận browser hỗ trợ

Ma trận tương thích là tài liệu vận hành ghi lại client nào được hỗ trợ, mức độ ưu tiên và các kiểm soát bảo mật đã được xác minh. Ma trận nên dựa trên dữ liệu sử dụng thực tế, yêu cầu nghiệp vụ và mức độ rủi ro của ứng dụng.

Một ma trận khởi đầu có thể gồm:

| Nhóm client | Ví dụ | Cách kiểm thử |
|---|---|---|
| Chromium desktop | Chrome, Edge và các bản Chromium được tổ chức cho phép | Kiểm thử trên phiên bản ổn định hiện tại và phiên bản thấp nhất còn hỗ trợ |
| Firefox desktop | Firefox Release và ESR nếu tổ chức sử dụng | Kiểm tra CSP, cookie, CORS, storage và hành vi popup |
| Safari trên macOS | Safari trên các phiên bản macOS được hỗ trợ | Kiểm tra cookie, Intelligent Tracking Prevention, storage và WebKit behavior |
| Mobile browser | Chrome Android, Firefox Android, Safari iOS | Kiểm tra viewport, cookie, điều hướng, permission và lifecycle nền |
| WebView hoặc in-app browser | Android WebView, WKWebView và browser nhúng trong ứng dụng | Xác định engine/version, cấu hình host app và bridge native |
| Browser doanh nghiệp | Browser được quản lý bằng policy hoặc chạy trên VDI/kiosk | Kiểm tra enterprise policy, proxy, extension và chu kỳ cập nhật |

Không cần hỗ trợ mọi browser hoặc mọi phiên bản. Cần công bố rõ phiên bản tối thiểu, nhóm client được hỗ trợ, thời gian chuyển tiếp và cách xử lý khi người dùng dùng client ngoài phạm vi. Với ứng dụng quản trị hoặc dữ liệu nhạy cảm, có thể yêu cầu browser có các tính năng bảo mật nhất định và từ chối luồng nhạy cảm nếu không đáp ứng.

Ma trận nên ghi ít nhất các thông tin sau:

- Tên browser, engine, phiên bản và hệ điều hành.
- Thiết bị desktop/mobile, chế độ thường/private và loại môi trường nhúng.
- Tính năng bảo mật được hỗ trợ, được kiểm thử hoặc còn hạn chế.
- Các test case bắt buộc và kết quả gần nhất.
- Rủi ro đã biết, fallback đang dùng và người chịu trách nhiệm.
- Ngày kiểm tra, thời điểm hết hạn kết quả và sự kiện cần kiểm tra lại.

Phiên bản browser tự động cập nhật có thể khiến ma trận lỗi thời nhanh. Hãy gắn kết quả với phiên bản cụ thể và kiểm tra lại khi browser có bản cập nhật lớn, khi thay đổi security header hoặc khi telemetry cho thấy một nhóm client bắt đầu thất bại.

## Phân biệt phát hiện tính năng và xác minh bảo mật

Feature detection cho biết một API hoặc thuộc tính có tồn tại, nhưng không chứng minh browser thực thi đúng toàn bộ hành vi bảo mật cần thiết. User agent sniffing dựa trên chuỗi tên browser dễ sai vì chuỗi có thể bị thay đổi, rút gọn hoặc giống nhau giữa nhiều browser.

Ưu tiên phát hiện khả năng trực tiếp:

~~~javascript
const browserCapabilities = {
  secureContext: window.isSecureContext === true,
  serviceWorker: 'serviceWorker' in navigator,
  trustedTypes: 'trustedTypes' in window,
  reportingObserver: 'ReportingObserver' in window,
  credentialManagement: 'credentials' in navigator,
  crossOriginIsolated: window.crossOriginIsolated === true
};

console.info('Browser capability summary', browserCapabilities);
~~~

Đây là ví dụ kiểm kê khả năng ở client. Không nên gửi nguyên chuỗi user agent hoặc một fingerprint chi tiết lên server nếu không có nhu cầu rõ ràng. Nếu cần telemetry, chỉ thu các cờ tính năng và phiên bản ở mức tối thiểu cần thiết, có thông báo và thời hạn lưu phù hợp.

Với security headers, cần kiểm tra response và hành vi browser thay vì chỉ kiểm tra API JavaScript. Ví dụ, `frame-ancestors` được browser áp dụng khi nhận response; việc kiểm tra `window` có thuộc tính nào đó không chứng minh header đã được gửi. Tương tự, SameSite cookie cần kiểm tra qua request thực tế, và CORS cần xác minh cả preflight lẫn response.

Một quy trình kiểm tra có ba lớp:

1. **Kiểm tra cấu hình:** xác nhận server gửi header, cookie attribute và policy đúng.
2. **Kiểm tra hành vi:** xác nhận browser cho phép hoặc chặn đúng thao tác trong fixture thử nghiệm.
3. **Kiểm tra vận hành:** xác nhận luồng thực tế hoạt động trên phiên bản và thiết bị nằm trong ma trận hỗ trợ.

## Tương thích CSP và các cơ chế chống XSS

CSP được gửi qua response header và được browser thực thi. Khả năng hỗ trợ directive, nonce, hash, `strict-dynamic`, báo cáo và các tính năng CSP mới có thể khác giữa các engine hoặc phiên bản. Khi triển khai policy, không nên giả định mọi client hiểu cùng một tập directive.

Các bước vận hành nên thực hiện:

- Dùng `Content-Security-Policy-Report-Only` để quan sát policy mới trên nhóm browser mục tiêu trước khi enforce.
- Kiểm tra CSP enforce trên từng nhóm client; xác nhận script hợp lệ vẫn chạy và script không được cấp phép bị chặn.
- Ưu tiên nonce hoặc hash cho inline script cần thiết; không thêm `'unsafe-inline'` hoặc `'unsafe-eval'` chỉ để làm browser cũ chạy được.
- Kiểm tra `frame-ancestors`, `base-uri`, `object-src`, `form-action`, `connect-src`, `worker-src` và các directive ứng dụng đang dùng.
- Giữ phương án tương thích có giới hạn cho client cũ, nhưng phải đánh giá rõ mức bảo vệ bị thiếu.

`X-Frame-Options` có thể được duy trì như lớp tương thích cho browser cũ trong các trường hợp đơn giản như `DENY` hoặc `SAMEORIGIN`, đồng thời dùng CSP `frame-ancestors` cho browser hỗ trợ. Tuy nhiên, X-Frame-Options không biểu đạt được danh sách nhiều ancestor origin linh hoạt. Nếu ứng dụng cần được nhúng bởi nhiều đối tác, không được mở rộng chính sách cho tất cả chỉ để hỗ trợ một browser cũ; hãy xác định luồng nhúng có thể hỗ trợ và rủi ro còn lại.

Trusted Types là một cơ chế giảm nguy cơ DOM XSS bằng cách kiểm soát dữ liệu đi vào một số sink nguy hiểm. Mức hỗ trợ của Trusted Types không đồng đều ở mọi browser. Feature detection như `'trustedTypes' in window` chỉ cho biết API hiện diện. Cần kiểm thử CSP directive `require-trusted-types-for 'script'`, policy được tạo và các sink thực tế. Nếu browser không hỗ trợ, ứng dụng vẫn phải dùng text API, sanitizer phù hợp, kiểm soát template và tránh gán dữ liệu không tin cậy vào `innerHTML` hoặc sink tương tự. Polyfill không thể biến một browser không có enforcement gốc thành một ranh giới bảo mật tương đương.

### Ví dụ kiểm tra fallback chống frame

Nếu ứng dụng không cho phép nhúng ở bất kỳ origin nào, có thể cấu hình cả CSP và header tương thích:

~~~http
Content-Security-Policy: frame-ancestors 'none'
X-Frame-Options: DENY
~~~

Kiểm thử bằng một trang fixture khác origin tạo iframe trỏ đến ứng dụng. Xác nhận browser chặn frame và ứng dụng không phụ thuộc vào việc JavaScript phát hiện mình đang nằm trong frame để tự bảo vệ. Header phải được gửi trên response của trang cần bảo vệ, kể cả các route nhạy cảm.

## Tương thích cookie, SameSite và quyền riêng tư

Cookie là một khu vực có khác biệt đáng kể giữa browser, chế độ riêng tư và chính sách chặn third-party cookies. Cần kiểm tra attribute được server phát ra và xem cookie thực sự được gửi trong các request cần thiết.

Các thuộc tính nên được khai báo rõ:

~~~http
Set-Cookie: session=opaque-value; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

- `Secure` giới hạn cookie gửi qua kết nối bảo mật.
- `HttpOnly` ngăn JavaScript truy cập cookie qua `document.cookie`; nó không ngăn browser gửi cookie trong request phù hợp.
- `SameSite` kiểm soát việc gửi cookie trong các ngữ cảnh same-site và cross-site. `Strict`, `Lax` và `None` có hành vi khác nhau.
- `SameSite=None` cần đi cùng `Secure` trong các browser hiện đại hỗ trợ quy tắc này.
- `Path` và `Domain` xác định phạm vi cookie; không đặt Domain rộng hơn nhu cầu.

Kiểm thử cookie cần bao gồm đăng nhập, điều hướng top-level, form POST cross-site, iframe cross-site, popup OAuth, logout và chế độ private browsing. Một luồng đăng nhập có thể chạy trên browser này nhưng thất bại trên browser khác do third-party cookie bị chặn hoặc storage bị phân vùng. Không giải quyết lỗi bằng cách bỏ `Secure`, bỏ `HttpOnly` hoặc nới `SameSite` rộng mà không đánh giá CSRF và luồng xác thực.

Một số browser triển khai partitioned storage hoặc cookie partitioning theo chính sách riêng tư. Nếu ứng dụng dùng cookie `Partitioned` (CHIPS) hoặc nhúng nội dung bên thứ ba, phải kiểm tra hỗ trợ, attribute và hành vi trong từng browser mục tiêu. Không giả định cookie third-party sẽ hoạt động chỉ vì browser chấp nhận header `Set-Cookie`.

Nếu tính năng phụ thuộc third-party cookie, hãy cân nhắc kiến trúc first-party, redirect có kiểm soát, backend-for-frontend hoặc Storage Access API khi phù hợp. Storage Access API có yêu cầu tương tác người dùng và điều kiện theo browser; nó không phải cách bật quyền truy cập cookie cross-site vô điều kiện.

## CORS, Fetch Metadata và request cross-origin

CORS là cơ chế browser kiểm soát việc JavaScript đọc response cross-origin. Nó không phải cơ chế xác thực người dùng và không thay thế kiểm tra quyền ở server. Browser có thể gửi request đơn giản trước khi quyết định có cho JavaScript đọc response hay không; do đó server vẫn phải bảo vệ các thao tác thay đổi dữ liệu trước CSRF.

Khi vận hành CORS, kiểm tra:

- `Access-Control-Allow-Origin` chỉ phản hồi origin đã được cho phép; không phản chiếu mọi giá trị `Origin`.
- Khi dùng credentials, không dùng wildcard `*` cho `Access-Control-Allow-Origin`; phải trả origin cụ thể và `Access-Control-Allow-Credentials: true` khi thật sự cần.
- `Vary: Origin` được cấu hình phù hợp nếu response thay đổi theo origin, tránh cache dùng nhầm response giữa các origin.
- Preflight `OPTIONS` cho phép đúng method và header cần thiết; không mở rộng quá mức.
- Cookie và credentials hoạt động đúng với `SameSite`, third-party cookie policy và cấu hình fetch của browser.
- Lỗi CORS không làm lộ dữ liệu qua endpoint phụ hoặc thông điệp lỗi chi tiết.

Fetch Metadata như `Sec-Fetch-Site`, `Sec-Fetch-Mode`, `Sec-Fetch-Dest` và `Sec-Fetch-User` có thể giúp server phân biệt một số ngữ cảnh request do browser gửi. Mức hỗ trợ và cách gửi header cần được kiểm tra theo client. Nếu header vắng mặt, server vẫn phải có CSRF token, SameSite cookie, kiểm tra Origin/Referer phù hợp và xác thực quyền theo yêu cầu của endpoint.

Không dùng việc browser chặn response CORS làm bằng chứng rằng request không thể gây tác động. Test phải kiểm tra cả side effect ở server, không chỉ kết quả `fetch()` trong JavaScript.

## COOP, COEP, CORP và cross-origin isolation

Các header cách ly cross-origin ảnh hưởng đến quan hệ giữa browsing context, cách tải tài nguyên và khả năng dùng một số API nhạy cảm.

| Cơ chế | Mục đích | Điểm tương thích cần kiểm tra |
|---|---|---|
| COOP (`Cross-Origin-Opener-Policy`) | Tách browsing context group để giảm liên kết giữa cửa sổ có origin khác nhau | Popup OAuth, `window.opener`, đăng nhập qua cửa sổ mới và luồng thanh toán |
| COEP (`Cross-Origin-Embedder-Policy`) | Yêu cầu tài nguyên cross-origin được cấp phép rõ để document có thể đạt cross-origin isolation | Script, ảnh, worker, iframe và tài nguyên bên thứ ba |
| CORP (`Cross-Origin-Resource-Policy`) | Cho phép chủ tài nguyên chỉ định ngữ cảnh cross-origin nào có thể tải tài nguyên theo cơ chế CORP | Tài nguyên public, tài nguyên cùng site và CDN |
| `crossOriginIsolated` | Cho biết document hiện tại có đạt điều kiện cross-origin isolation hay không | Kiểm tra runtime cùng với header COOP/COEP và dependency |

Không bật COOP/COEP trên toàn site mà không thử các luồng popup và tài nguyên bên thứ ba. Một thay đổi có thể làm `window.opener` bị tách, khiến callback OAuth cũ không hoạt động hoặc làm browser chặn script/worker từ CDN thiếu header phù hợp.

Nếu ứng dụng cần API yêu cầu cross-origin isolation, hãy kiểm tra `window.crossOriginIsolated` trên browser mục tiêu và xác minh response headers trên document thực tế. Nếu không đạt điều kiện, ứng dụng phải có luồng thay thế phù hợp hoặc từ chối riêng chức năng phụ thuộc API đó. Không giả định chỉ kiểm tra sự tồn tại của API là đủ.

## Service worker và storage compatibility

Service worker yêu cầu secure context và có khác biệt về hỗ trợ, lifecycle, quota, eviction và hành vi khi browser ở chế độ tiết kiệm pin hoặc chạy nền. Browser có thể dừng worker khi không hoạt động; dữ liệu trong Cache Storage hoặc IndexedDB có thể bị xóa khi thiết bị thiếu dung lượng hoặc người dùng xóa dữ liệu site.

Kiểm thử trên các browser mục tiêu:

- `navigator.serviceWorker` có tồn tại và registration có thành công trên HTTPS.
- Scope, script MIME type, redirect và `Service-Worker-Allowed` có đúng không.
- Worker có activate, nhận fetch event và kiểm soát page theo đúng lifecycle không.
- Cache Storage và IndexedDB có được dùng đúng quota và xử lý trường hợp dữ liệu bị xóa không.
- Offline fallback không làm sai response API hoặc lộ dữ liệu session cũ.
- Cập nhật worker có tương thích với page cũ và browser có cache script theo cách dự kiến không.
- Push, Background Sync và notification được kiểm tra riêng vì hỗ trợ và quyền có thể khác theo browser, hệ điều hành và thiết bị.

Không coi cache offline là nơi lưu trữ bền vững hoặc kho bí mật. Với dữ liệu quan trọng, server vẫn là nguồn dữ liệu chính; ứng dụng cần xử lý rõ khi cache bị eviction, storage bị từ chối hoặc browser khôi phục từ profile mới.

## Reporting API và khả năng quan sát

Reporting API, `Reporting-Endpoints` và `ReportingObserver` có mức hỗ trợ khác nhau theo browser và phiên bản. Một endpoint không nhận report không chứng minh rằng không có vi phạm. Report có thể không được browser hỗ trợ, bị trì hoãn, bị mất khi offline hoặc bị loại bởi chính sách riêng tư.

Vận hành nên:

- Kiểm tra report endpoint trên từng browser mục tiêu và xác nhận content type, batch, schema.
- Dùng `ReportingObserver` với feature detection khi cần quan sát ở client; không để ứng dụng lỗi khi API không tồn tại.
- Duy trì kiểm tra trực tiếp bằng DevTools và automated tests; không phụ thuộc report làm bằng chứng duy nhất.
- Giảm thiểu URL, query string, source sample và dữ liệu người dùng trước khi lưu report.
- Theo dõi tỷ lệ report theo browser/version để nhận biết thay đổi hành vi sau update.

Nếu browser cũ không hỗ trợ cơ chế báo cáo mới, có thể cần cơ chế telemetry khác hoặc kiểm thử chủ động. Không hạ thấp CSP enforce chỉ vì một nhóm client không gửi được report.

## Progressive enhancement và fallback an toàn

Progressive enhancement là cách thiết kế để chức năng cơ bản vẫn hoạt động khi một API tùy chọn không có, trong khi tính năng nâng cao chỉ bật khi browser đáp ứng điều kiện. Với bảo mật, cần phân biệt rõ tính năng tiện ích và kiểm soát bắt buộc.

| Loại khả năng | Cách xử lý khi không được hỗ trợ |
|---|---|
| Tính năng giao diện không nhạy cảm | Dùng phương án giao diện đơn giản hơn hoặc thông báo giới hạn |
| API lưu offline | Chuyển sang network-only hoặc hiển thị trạng thái không hỗ trợ; không lưu dữ liệu nhạy cảm bằng cơ chế thay thế yếu hơn |
| ReportingObserver | Bỏ telemetry phía client hoặc dùng report endpoint/monitoring khác nếu browser hỗ trợ |
| Trusted Types enforcement | Giữ quy tắc coding an toàn, sanitizer và kiểm soát sink; không giả vờ rằng polyfill cung cấp enforcement tương đương |
| Cross-origin isolation | Tắt riêng chức năng phụ thuộc nếu không có isolation; giữ luồng ứng dụng an toàn còn lại |
| CSP directive quan trọng | Dùng lớp bảo vệ tương thích đã được kiểm chứng hoặc không cho phép luồng nhạy cảm trên client đó |
| Secure context hoặc WebAuthn | Không hạ xuống luồng xác thực yếu hơn mà không có đánh giá rủi ro và chính sách xác thực riêng |

Một fallback an toàn phải được thiết kế có chủ đích. Nếu thiếu cơ chế bảo vệ quan trọng, có thể từ chối chức năng nhạy cảm, yêu cầu browser được hỗ trợ hoặc chuyển người dùng sang một luồng đã được bảo vệ ở server. Không âm thầm chuyển sang `http`, bỏ cookie attribute, cho phép mọi origin hoặc bật `'unsafe-inline'` để tương thích.

Polyfill có thể bổ sung API tiện ích, nhưng không thể tự tạo ra một cơ chế bảo mật mà browser không thực thi. Ví dụ, một thư viện JavaScript không thể thay thế enforcement của CSP hoặc làm cho Trusted Types được browser kiểm tra ở mọi sink nếu browser không hỗ trợ cơ chế đó.

## Kiểm thử tương thích trong CI và trước phát hành

Tự động hóa giúp phát hiện hồi quy nhanh, nhưng một browser engine không đại diện cho mọi browser cùng tên hoặc cùng nền tảng. Playwright hỗ trợ chạy trên Chromium, Firefox và WebKit; WebKit trong Playwright là build WebKit do Playwright cung cấp, không phải phép thử thay thế hoàn toàn cho Safari thật trên macOS/iOS. Các luồng quan trọng cần kiểm tra thêm trên browser và thiết bị thực tế.

Ví dụ kiểm kê capability trong Playwright:

~~~javascript
import { test, expect } from '@playwright/test';

test('records security-related browser capabilities', async ({ page }, testInfo) => {
  await page.goto('/compatibility-check');

  const capabilities = await page.evaluate(() => ({
    secureContext: window.isSecureContext,
    serviceWorker: 'serviceWorker' in navigator,
    trustedTypes: 'trustedTypes' in window,
    reportingObserver: 'ReportingObserver' in window,
    crossOriginIsolated: window.crossOriginIsolated === true
  }));

  console.info({
    project: testInfo.project.name,
    capabilities
  });

  expect(capabilities.secureContext).toBe(true);
});
~~~

Ví dụ chỉ thu thập capability và khẳng định secure context cho route kiểm thử. Không nên đặt kỳ vọng mọi browser phải có tất cả API nếu ma trận hỗ trợ cho phép một số tính năng là tùy chọn. Thay vào đó, ánh xạ từng capability vào yêu cầu của chức năng và test hành vi tương ứng.

Các lớp test nên gồm:

1. **Static/configuration test:** kiểm tra response headers, `Set-Cookie`, CSP directive, CORS allowlist và cấu hình endpoint.
2. **Browser behavior test:** thử script bị CSP chặn, iframe bị từ chối, cookie được gửi theo ngữ cảnh, CORS không cho đọc response và service worker chỉ kiểm soát scope hợp lệ.
3. **Cross-browser test:** chạy test trên Chromium, Firefox và WebKit; bổ sung Safari thật, mobile browser và WebView nếu nằm trong phạm vi hỗ trợ.
4. **Regression test:** chạy lại sau khi cập nhật browser baseline, framework, CDN, proxy, cookie policy hoặc security headers.
5. **Manual exploratory test:** dùng DevTools trên browser thật để kiểm tra popup, redirect, permission prompt, private mode, extension và luồng đăng nhập phức tạp.

Không chỉ kiểm tra test pass. Lưu lại browser/version, hệ điều hành, test case, kết quả và lỗi console/network có liên quan để so sánh qua các đợt phát hành.

## Triển khai thay đổi tương thích an toàn

Khi cần thay đổi một security header hoặc API, hãy triển khai theo từng bước:

1. Xác định chức năng và nhóm client bị ảnh hưởng; kiểm tra dữ liệu sử dụng thực tế.
2. Xác minh yêu cầu hỗ trợ và khác biệt giữa các browser bằng tài liệu tương thích và test trên phiên bản mục tiêu.
3. Tạo test fixture tái hiện hành vi mong muốn và hành vi phải bị chặn.
4. Triển khai ở staging hoặc một nhóm client nhỏ; dùng Report-Only nếu cơ chế hỗ trợ chế độ quan sát.
5. Theo dõi lỗi theo browser/version, route và chức năng; phân biệt lỗi cấu hình với client ngoài phạm vi hỗ trợ.
6. Điều chỉnh fallback trong giới hạn an toàn và xác nhận các kiểm soát server-side vẫn được giữ.
7. Mở rộng rollout, lưu phiên bản cấu hình và chuẩn bị cách rollback nếu chức năng quan trọng bị ảnh hưởng.
8. Đặt ngày xem xét lại cho fallback cũ; loại bỏ chúng khi nhóm client không còn cần hỗ trợ.

Không nên giữ mã tương thích cũ vô thời hạn. Fallback có thể trở thành đường đi yếu nhất nếu không được theo dõi. Mỗi ngoại lệ cần có lý do, phạm vi, chủ sở hữu và thời hạn đánh giá.

## Giám sát sau phát hành

Vận hành cần theo dõi cả chỉ số kỹ thuật và trải nghiệm người dùng:

- Tỷ lệ đăng nhập thành công, lỗi callback OAuth và lỗi xác thực theo browser/version.
- Tỷ lệ request bị chặn bởi CSP, CORS hoặc policy tài nguyên.
- Lỗi service worker registration, update, offline fallback và cache miss.
- Lỗi storage, quota, permission prompt và API không hỗ trợ.
- Report CSP, deprecation và intervention khi browser gửi được.
- Lỗi JavaScript, lỗi mạng và các route có tỷ lệ thất bại tăng sau một bản cập nhật browser.

Khi phân tích, dùng thông tin browser ở mức tối thiểu cần thiết. User agent có thể bị rút gọn hoặc giả mạo; không dùng nó làm bằng chứng xác thực. Nếu cần phân nhóm, kết hợp phiên bản ứng dụng, capability đã phát hiện và telemetry vận hành, đồng thời tuân thủ chính sách quyền riêng tư.

Đặt ngưỡng cảnh báo dựa trên baseline từng nhóm client. Một tỷ lệ lỗi tăng đột ngột trên Safari mobile sau khi đổi cookie có thể cần điều tra khác với lỗi CSP tăng trên Chromium sau khi cập nhật CDN. Khi có sự cố, so sánh response header, cookie, network trace và browser version trước/sau thay đổi.

## Checklist vận hành browser compatibility

- [ ] Có ma trận browser, phiên bản, hệ điều hành, mobile và WebView được hỗ trợ.
- [ ] Mỗi tính năng bảo mật quan trọng có test cấu hình và test hành vi thực tế.
- [ ] Không dựa vào user agent sniffing khi có thể dùng feature detection.
- [ ] CSP và Trusted Types được đánh giá theo khả năng enforcement thực tế.
- [ ] Có fallback chống frame phù hợp và không mở rộng ancestor ngoài nhu cầu.
- [ ] Cookie `Secure`, `HttpOnly`, `SameSite`, `Domain` và `Path` được kiểm tra trong các luồng thực tế.
- [ ] CORS, credentials, preflight và Fetch Metadata được kiểm tra trên các browser mục tiêu.
- [ ] COOP/COEP/CORP được thử cùng popup, OAuth, iframe và tài nguyên bên thứ ba.
- [ ] Service worker, Cache Storage, storage quota và offline behavior được kiểm thử.
- [ ] Reporting API không phải nguồn bằng chứng duy nhất về vi phạm.
- [ ] CI chạy trên nhiều engine và có kiểm thử browser thật cho luồng quan trọng.
- [ ] Fallback có chủ sở hữu, lý do, giới hạn và thời hạn xem xét.
- [ ] Có telemetry theo browser/version và quy trình rollback khi phát sinh hồi quy.

## Câu hỏi tự kiểm tra

1. Vì sao feature detection không đủ để chứng minh một security header được browser thực thi?
2. Tại sao không nên nới CSP hoặc cookie attribute chỉ để hỗ trợ browser cũ?
3. Khi third-party cookie bị chặn, những luồng nào cần được kiểm thử lại?
4. Vì sao CORS không thay thế CSRF protection ở server?
5. Playwright WebKit khác với kiểm thử Safari thật ở điểm nào?
6. Khi một browser không hỗ trợ Trusted Types enforcement, những lớp bảo vệ nào vẫn phải được duy trì?
7. Vì sao fallback tương thích cần có chủ sở hữu và thời hạn xem xét?

Browser compatibility là một phần của vận hành bảo mật liên tục. Hãy xác định rõ client được hỗ trợ, kiểm tra cấu hình và hành vi trên từng engine, giữ fallback trong giới hạn an toàn và theo dõi thay đổi sau phát hành. Khi browser hoặc nền tảng thay đổi, ma trận kiểm thử và quyết định hỗ trợ cần được cập nhật cùng với ứng dụng.
