# Production debugging

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Xây dựng quy trình điều tra lỗi trên website production bằng browser DevTools mà không làm lộ dữ liệu người dùng.
- Thu thập thông tin tái hiện gồm browser/version, URL đã làm sạch, thời điểm, request ID và điều kiện mạng.
- Dùng Network, Console, Issues, Security, Application, Sources và Performance để khoanh vùng lỗi.
- Phân tích lỗi CORS, preflight, cookie, CSP, mixed content, service worker, cache và storage.
- Dùng source map, error monitoring và HAR đúng cách mà không công khai source hoặc credential.
- Phân biệt lỗi client, lỗi backend, lỗi CDN/proxy và lỗi do trạng thái browser.
- Lập báo cáo sự cố có bằng chứng đủ để xử lý nhưng không chứa token, cookie hoặc dữ liệu cá nhân không cần thiết.

## 1. Production debugging là gì?

Production debugging là quá trình điều tra hành vi không đúng trên môi trường người dùng thật hoặc môi trường gần với production. Lỗi có thể chỉ xảy ra với một browser version, một thiết bị, một tài khoản, một vùng địa lý, một trạng thái cache, một service worker cũ hoặc một điều kiện mạng cụ thể. Vì vậy, việc tái hiện chính xác và thu thập bằng chứng có kiểm soát quan trọng hơn việc thử thay đổi ngẫu nhiên trên trang đang chạy.

Trong ứng dụng web, DevTools giúp quan sát request/response, JavaScript exception, DOM, storage, cookie, certificate, security headers và hiệu năng. Tuy nhiên, DevTools hiển thị cả dữ liệu nhạy cảm mà browser đang xử lý. Network request có thể chứa session cookie, bearer token, thông tin cá nhân hoặc payload nghiệp vụ; Application panel có thể hiển thị cookie và storage; heap snapshot có thể giữ chuỗi bí mật trong bộ nhớ.

Một quy trình production debugging tốt cần đồng thời đạt ba mục tiêu:

1. Xác định lỗi xảy ra ở đâu và trong điều kiện nào.
2. Thu thập bằng chứng đủ để đội phát triển hoặc vận hành kiểm tra lại.
3. Giảm nguy cơ làm thay đổi trạng thái người dùng hoặc sao chép dữ liệu nhạy cảm ra khỏi môi trường được kiểm soát.

DevTools là công cụ quan sát và thử nghiệm cục bộ. Nó không thay thế log server, distributed tracing, metrics, alerting, RUM (Real User Monitoring) hoặc quy trình incident response.

## 2. Bắt đầu bằng phạm vi và thông tin tái hiện

Trước khi mở rộng điều tra, hãy mô tả hành vi lỗi theo một mẫu thống nhất. Tránh ghi nguyên URL chứa token, query nhạy cảm hoặc dữ liệu cá nhân vào ticket.

Thông tin hữu ích gồm:

- Thời điểm xảy ra lỗi và múi giờ.
- Môi trường, hostname và route đã loại bỏ dữ liệu nhạy cảm.
- Browser, phiên bản, hệ điều hành và loại thiết bị.
- Người dùng có gặp lỗi ở mọi lần thử hay chỉ một lần; có tái hiện được trên tài khoản thử nghiệm không.
- Hành động ngay trước khi lỗi xuất hiện.
- Kết quả mong đợi và kết quả thực tế.
- Request/correlation ID do hệ thống cấp, nếu có.
- Trạng thái mạng, VPN/proxy, tab mới/cũ, cache và service worker khi có liên quan.
- Phạm vi ảnh hưởng: một người, một tenant, một browser, một vùng hay toàn bộ người dùng.

Ví dụ báo cáo ban đầu:

```text
Thời điểm: 2026-11-22 09:15 UTC
Browser: Chromium-based browser, version đã ghi nhận trong ticket
Route: /account/overview (đã loại bỏ query riêng tư)
Hành động: mở trang sau khi đăng nhập
Kết quả: API /api/account trả 401, giao diện chuyển về trang đăng nhập
Tần suất: tái hiện 3/3 lần trong profile thử nghiệm
Request ID: req-7f31-demo
Phạm vi: một tenant thử nghiệm
```

Đây là dữ liệu minh họa. Khi ghi nhận thực tế, không đưa username, email, session ID, cookie, token hoặc body nghiệp vụ vào ví dụ công khai.

### 2.1. Phân biệt lỗi người dùng và lỗi hệ thống

Một lần tải thất bại có thể do:

- JavaScript exception hoặc lỗi logic phía client.
- Request không được gửi vì code không chạy, bị abort hoặc bị chặn bởi browser.
- DNS, TLS, proxy, mạng di động hoặc timeout.
- Backend trả status lỗi hoặc dữ liệu không đúng schema.
- CORS/preflight, CSP, Permissions Policy hoặc mixed content chặn thao tác.
- Cookie không được gửi do Domain, Path, Secure, SameSite, partitioning hoặc browser privacy policy.
- Cache, service worker hoặc BFCache cung cấp trạng thái cũ.
- Extension, privacy tool hoặc cấu hình browser thay đổi hành vi.

Không kết luận “backend lỗi” chỉ từ một dòng `Failed to fetch`. Cần xác định request có xuất hiện trong Network hay không, browser có chặn request trước khi gửi không và server có ghi nhận request ID tương ứng không.

## 3. Quy trình điều tra an toàn

Một trình tự thực tế:

1. Xác nhận phạm vi ảnh hưởng và chọn tài khoản/test data phù hợp.
2. Ghi browser/version, route đã làm sạch, thời điểm và request ID.
3. Mở DevTools trước khi tái hiện; bật Preserve log khi lỗi xảy ra qua redirect hoặc navigation.
4. Tái hiện một lần có kiểm soát và ghi lại request đầu tiên thất bại, không tạo vòng lặp tải hoặc gửi lặp thao tác ghi dữ liệu.
5. Đối chiếu Console, Network, Issues và các header liên quan.
6. Kiểm tra trạng thái cookie/storage/service worker/cache nếu giả thuyết liên quan.
7. Đối chiếu request ID với log backend, gateway và CDN.
8. Tạo bản tái hiện tối thiểu bằng tài khoản test hoặc staging.
9. Ghi kết luận, bằng chứng đã làm sạch, giả thuyết đã loại trừ và bước tiếp theo.

Trong production, ưu tiên thao tác chỉ đọc. Tránh gửi lại form thanh toán, tạo đơn, xóa dữ liệu, đổi quyền, refresh token hoặc thực hiện thao tác có side effect chỉ để xem lỗi. Nếu cần tái hiện hành động ghi dữ liệu, dùng tài khoản và resource thử nghiệm được cho phép.

## 4. Network panel: điều tra request và response

Network panel thường là điểm bắt đầu hữu ích nhất vì nó cho biết browser đã gửi gì, nhận gì và request nào bị chặn.

### 4.1. Cấu hình quan sát

Các tùy chọn thường dùng:

| Tùy chọn | Tác dụng | Lưu ý |
| --- | --- | --- |
| Preserve log | Giữ request qua navigation/redirect. | Có thể giữ cả request nhạy cảm lâu hơn trong DevTools. Tắt và xóa log khi kết thúc. |
| Disable cache | Bỏ qua browser HTTP cache khi DevTools đang mở trong điều kiện được hỗ trợ. | Làm thay đổi hành vi đang điều tra; chỉ bật để so sánh, không coi là trạng thái production mặc định. |
| Throttling | Mô phỏng mạng chậm hoặc offline. | Dùng để kiểm tra khả năng tái hiện, không đại diện chính xác mạng người dùng. |
| Filter | Lọc Fetch/XHR, Doc, JS, CSS, Img, WS hoặc request theo từ khóa. | Không chia sẻ filter/query có chứa dữ liệu nhạy cảm. |
| Initiator | Cho biết script, document hoặc call stack khởi tạo request. | Hữu ích để tìm code gọi API hoặc tải tài nguyên. |
| Timing | Hiển thị queueing, DNS, connect, TLS, request/response và download. | So sánh nhiều request để tìm bottleneck. |

Đừng bật `Disable cache` ngay từ đầu nếu nghi ngờ lỗi chỉ xảy ra do cache. Hãy quan sát trạng thái ban đầu trước, sau đó thử một lần với cache disabled để so sánh.

### 4.2. Đọc request/response

Với request lỗi, kiểm tra theo thứ tự:

- Request URL: đúng host/path/method chưa; loại bỏ query nhạy cảm khi ghi báo cáo.
- Status: 2xx, 3xx, 4xx, 5xx hay `(failed)`.
- Request headers: `Origin`, `Accept`, `Content-Type`, `Authorization`, `Cookie` và header tùy chỉnh có cần thiết không. Không copy giá trị bí mật.
- Response headers: `Content-Type`, `Cache-Control`, `Set-Cookie`, CORS headers, CSP và request ID.
- Payload/response: schema, error code, field bị thiếu hoặc định dạng bất thường; không xuất payload chứa dữ liệu cá nhân.
- Initiator: file, dòng hoặc stack đã tạo request.
- Timing/Size: request chậm ở DNS, TLS, server processing hay download.

Một request `200` không đảm bảo thao tác nghiệp vụ thành công; response có thể chứa lỗi trong JSON hoặc dữ liệu không hợp lệ. Ngược lại, `304` là phản hồi cache validation bình thường, không phải lỗi server. Hãy đọc status, header và body theo hợp đồng API.

### 4.3. Phân biệt request bị browser chặn với lỗi server

Nếu request không xuất hiện trong Network, có thể code chưa gọi, bị exception trước đó, bị chặn bởi policy hoặc request được xử lý ở service worker. Nếu Network hiển thị `(blocked:csp)`, `blocked by client`, CORS error hoặc mixed-content warning, cần kiểm tra lý do chặn cụ thể.

Nếu request xuất hiện và có status HTTP, browser đã nhận được response từ một tầng nào đó; tầng đó có thể là service worker, cache, CDN, proxy hoặc origin server. Dùng response header như `Age`, `Via`, `X-Cache` hoặc request ID nếu hạ tầng cung cấp để đối chiếu. Không giả định mọi response đều đến từ application server.

## 5. Console và lỗi JavaScript

Console giúp xác định exception, rejected Promise, warning của browser và thông báo policy. Khi điều tra:

- Giữ stack trace đầy đủ, file và line number.
- Phân biệt exception đầu tiên với lỗi phát sinh dây chuyền sau đó.
- Kiểm tra unhandled Promise rejection và lỗi async.
- Tìm CSP violation, CORS, cookie deprecation/blocking, mixed content và lỗi service worker.
- Ghi lại browser version vì thông báo và hành vi có thể thay đổi giữa phiên bản.

Ví dụ lỗi:

```text
Uncaught TypeError: Cannot read properties of undefined (reading 'id')
    at renderAccount (account.js:84:19)
    at loadAccount (account.js:42:7)
```

Stack trace chỉ ra nơi exception xuất hiện; cần truy ngược dữ liệu đầu vào và request đã tạo trạng thái đó. Đừng sửa bằng cách thêm optional chaining ở mọi nơi mà chưa hiểu vì sao dữ liệu thiếu.

### 5.1. Source maps

Production JavaScript thường được bundle/minify. Source map ánh xạ vị trí trong bundle về source gốc để stack trace dễ đọc hơn.

Có hai cách triển khai phổ biến:

- Public source map: file `.map` được triển khai và browser có thể tải xuống. Cách này tiện cho debugging nhưng có thể tiết lộ source, tên module, cấu trúc nội bộ và comment.
- Private source map: build artifact được upload riêng đến error monitoring/observability service; file map không được phục vụ công khai cùng website. Đây thường là lựa chọn phù hợp cho ứng dụng có source nội bộ.

Source map không phải cơ chế bảo mật cho secret. Không đưa API key, token, private config hoặc dữ liệu người dùng vào source gốc rồi hy vọng không ai xem được map. Secret không được đóng gói vào client bundle ngay từ đầu.

Khi source map không khớp:

1. Xác nhận release/build ID trong error event.
2. Xác nhận source map thuộc đúng bundle hash đang chạy.
3. Kiểm tra pipeline upload map đã hoàn tất trước khi event được xử lý.
4. Kiểm tra URL asset, release name và debug ID theo công cụ đang dùng.
5. Không thay source map của release khác để ép stack trace hiển thị.

### 5.2. Không chạy code tùy ý trong Console production

Console có thể thực thi JavaScript trong ngữ cảnh trang đang mở. Code chạy ở đây có thể đọc DOM, gọi API bằng session hiện tại hoặc thay đổi dữ liệu. Không paste snippet từ ticket, chat hoặc website lạ vào Console. Chỉ chạy lệnh đã được review, hiểu rõ tác dụng và được phép trên môi trường đó.

Không dùng Console để trích xuất cookie, token hoặc dữ liệu cá nhân nhằm gửi cho người khác. Với cookie `HttpOnly`, JavaScript trang không đọc được qua `document.cookie`, nhưng DevTools hoặc công cụ debug có thể hiển thị thông tin tương ứng; coi mọi bản sao là dữ liệu nhạy cảm.

## 6. Issues và Security panels

### 6.1. Issues panel

Issues panel tổng hợp một số vấn đề browser phát hiện, ví dụ cookie bị chặn hoặc sắp thay đổi hành vi, CORS, deprecation, mixed content hay vấn đề về policy. Mỗi issue thường cung cấp mô tả, request/document liên quan và gợi ý khắc phục.

Khi xử lý issue:

- Xác định URL và resource liên quan.
- Đọc chi tiết lý do browser nêu, không chỉ dựa vào biểu tượng warning.
- Kiểm tra response header và request context.
- Phân biệt warning tương thích với lỗi chặn thực tế.
- Kiểm thử trên browser/version mà sản phẩm hỗ trợ.

### 6.2. Security panel

Security panel trong Chromium-based DevTools giúp xem thông tin bảo mật của trang và origin, chẳng hạn certificate/TLS, nguồn không an toàn hoặc nội dung mixed. Giao diện cụ thể tùy browser.

Khi trang báo “Not secure” hoặc có mixed content:

1. Kiểm tra certificate có hợp lệ, đúng hostname và còn hạn không.
2. Kiểm tra chain, issuer và thời gian hệ thống nếu có lỗi TLS.
3. Xác định tài nguyên HTTP được tải từ document HTTPS.
4. Kiểm tra redirect từ HTTPS xuống HTTP.
5. Sửa URL tài nguyên và cấu hình HTTPS ở server/CDN; không bỏ cảnh báo certificate ở client như cách khắc phục.

Một trang HTTPS có thể vẫn có vấn đề nếu script, iframe hoặc API được tải qua HTTP. Browser có thể tự nâng cấp hoặc chặn mixed content tùy loại tài nguyên; không dựa vào hành vi tự động này.

## 7. Debug CORS và preflight

Khi JavaScript gọi API cross-origin, kiểm tra request trong Network và tìm request `OPTIONS` nếu có preflight.

Preflight thường xảy ra khi request không phải “simple request” theo quy tắc CORS, ví dụ dùng method/headers không nằm trong nhóm được cho phép hoặc có content type không safelisted. Browser gửi `OPTIONS` để hỏi server có cho phép origin, method và header dự kiến không.

Ví dụ request preflight:

```http
OPTIONS /api/report HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization, content-type
```

Response cần phù hợp với request:

```http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: POST, OPTIONS
Access-Control-Allow-Headers: Authorization, Content-Type
Vary: Origin
```

Nếu request dùng credentials, server cần trả origin cụ thể và `Access-Control-Allow-Credentials: true`; wildcard `Access-Control-Allow-Origin: *` không hợp lệ với credentialed CORS response. Browser cũng áp dụng quy tắc cookie riêng, nên CORS đúng chưa chắc cookie sẽ được gửi.

Checklist điều tra:

- Request có được gửi không, hay preflight bị chặn?
- `Origin` có đúng scheme/host/port không?
- `Access-Control-Allow-Origin` có khớp chính xác origin được phép không?
- Method và mọi request header có nằm trong allowlist không?
- Nếu dùng credentials, có `Access-Control-Allow-Credentials: true` và origin cụ thể không?
- Response có `Vary: Origin` khi origin được phản chiếu theo allowlist không?
- CDN có cache preflight/response theo key phù hợp không?
- Server có xử lý `OPTIONS` trước authentication middleware theo kiến trúc không?

Không khắc phục CORS bằng cách bật `Access-Control-Allow-Origin: *` cho mọi route hoặc dùng `mode: "no-cors"`. Hãy xác định client nào cần đọc response và cấp quyền tối thiểu.

## 8. Debug cookie và session

Cookie có thể không được gửi dù JavaScript gọi đúng endpoint. Trong Network, kiểm tra phần Cookies hoặc blocked reason của request nếu browser hiển thị.

Các thuộc tính cần rà soát:

| Thuộc tính | Câu hỏi khi debug |
| --- | --- |
| Domain/host-only | Cookie có thuộc host request hay chỉ host khác? Có khai báo Domain quá rộng không? |
| Path | Request path có khớp cookie Path không? |
| Secure | Request có HTTPS không? |
| SameSite | Điều hướng/request đang same-site hay cross-site? Cookie `Lax`, `Strict` hay `None` có phù hợp không? |
| HttpOnly | Cookie có được JavaScript đọc hay chỉ được browser gửi? Không cần bỏ HttpOnly để debug. |
| Expiration | Cookie đã hết hạn hoặc bị session cleanup chưa? |
| Partitioned | Cookie có gắn partition key và đang ở đúng top-level site không? |
| Browser privacy settings | Third-party cookie hoặc storage access có bị hạn chế không? |

Đừng sửa bằng cách bỏ `Secure`, `HttpOnly` hoặc đặt `SameSite=None` đại trà. Xác định chính xác request context và policy cần có. Khi dùng `SameSite=None`, cookie cần `Secure`; browser vẫn có thể hạn chế third-party cookie theo chính sách riêng tư.

Khi kiểm tra session lỗi:

1. Xác nhận request có cookie/session hay không mà không copy giá trị.
2. Đối chiếu session ID hoặc request ID qua hệ thống log được bảo vệ.
3. Kiểm tra cookie domain/path/SameSite/partitioning và thời điểm hết hạn.
4. Kiểm tra backend có revoke session, rotate session ID hoặc từ chối do CSRF/risk policy không.
5. Kiểm tra tab khác có đang dùng session cũ hay không.

## 9. Debug CSP và security headers

CSP violation thường xuất hiện trong Console và có thể được gửi đến endpoint report nếu policy cấu hình báo cáo. Hãy tìm directive bị vi phạm, resource URL và initiator.

Ví dụ:

```http
Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-random-per-response'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
```

Khi script bị chặn:

- Xác định script là first-party, third-party, inline hay dynamic.
- Kiểm tra directive cụ thể (`script-src`, `script-src-elem`, `script-src-attr` nếu được áp dụng).
- Kiểm tra nonce có được tạo mới cho response và khớp thuộc tính script không.
- Kiểm tra hash có khớp chính xác nội dung inline không.
- Kiểm tra CDN/proxy có làm thay đổi header hoặc HTML không.
- Nếu đang rollout, so sánh `Content-Security-Policy-Report-Only` với enforcing policy.

Không thêm `'unsafe-inline'` hoặc `*` chỉ để làm lỗi biến mất. Nếu policy mới chặn một tính năng hợp lệ, tìm nguồn script/endpoint cụ thể rồi cập nhật allowlist có chủ đích.

### 9.1. Các header liên quan khác

Khi điều tra browser security, có thể cần xem:

- `Strict-Transport-Security`: browser có ghi nhớ yêu cầu HTTPS cho host không.
- `X-Content-Type-Options: nosniff`: response script/style có MIME type phù hợp không.
- `Cross-Origin-Opener-Policy` (COOP): browsing context có bị tách khỏi opener không.
- `Cross-Origin-Embedder-Policy` (COEP): tài nguyên cross-origin có đáp ứng yêu cầu embed không.
- `Cross-Origin-Resource-Policy` (CORP): resource có cho phép context cross-origin tải không.
- `Permissions-Policy`: feature như camera, microphone hoặc geolocation có bị giới hạn không.
- `Referrer-Policy`: request có gửi lượng referrer dự kiến không.
- `frame-ancestors` trong CSP hoặc `X-Frame-Options`: trang có bị chặn khi nhúng iframe không.

Một request bị chặn bởi CORP/COEP có thể không phải lỗi CORS. Đọc thông báo Console và header tương ứng để xác định cơ chế đang áp dụng.

## 10. Debug service worker, Cache Storage và offline

Service worker có thể thay đổi response mà trang nhận được. Nếu Network cho thấy response không giống origin server, kiểm tra service worker trước khi kết luận backend trả sai.

Trong Application panel:

- Xem service worker registration, scope, trạng thái activated/waiting và script URL.
- Kiểm tra Cache Storage và tên cache.
- Xem Local Storage, IndexedDB và cookie theo origin/partition khi browser hỗ trợ hiển thị.
- Thử bypass service worker để so sánh một lần có kiểm soát.
- Kiểm tra update lifecycle: worker mới có đang waiting vì tab cũ vẫn mở không.

Nếu lỗi chỉ xuất hiện sau deploy:

1. Ghi nhận build/version của HTML, JS bundle và service worker.
2. Kiểm tra HTML mới có tham chiếu asset hash cũ hoặc ngược lại không.
3. Kiểm tra cache version và cleanup trong `activate`.
4. Kiểm tra worker cũ có đang phục vụ response từ Cache Storage không.
5. So sánh với một profile test mới hoặc bypass worker; không xóa storage người dùng thật chỉ để thử.

Không nhấn “Clear site data” trên profile người dùng thật khi chưa hiểu tác động. Thao tác này có thể xóa session, dữ liệu offline, IndexedDB và dữ liệu chưa đồng bộ. Dùng profile test hoặc staging để xác nhận giả thuyết.

## 11. Debug browser storage và privacy behavior

Application/Storage panel có thể giúp kiểm tra cookie, localStorage, sessionStorage, IndexedDB, Cache Storage và service worker. Khi so sánh hành vi, ghi rõ top-level site, frame origin và browser profile vì storage partitioning có thể làm cùng third-party origin nhận vùng dữ liệu khác nhau.

Nếu iframe không thấy session hoặc storage:

- Xác định iframe là same-origin, same-site hay cross-site với trang cha.
- Kiểm tra cookie SameSite, third-party cookie policy và partitioned cookie.
- Kiểm tra Storage Access API nếu ứng dụng có use case hợp lệ cần unpartitioned state.
- Kiểm tra storage key/partition được browser hiển thị nếu có.
- Kiểm tra API có bị chặn trong third-party context không.
- Thử top-level navigation đến origin nhúng để phân biệt first-party state và third-party partition.

Không giả định localStorage của iframe giống localStorage khi origin đó được mở trực tiếp ở top-level. Không dùng dữ liệu người dùng thật để kiểm tra partitioning nếu có thể tạo fixture test.

## 12. Performance và memory trong production

Performance panel giúp xác định long task, layout/recalculate style, scripting, rendering, network và các hoạt động tốn thời gian. Memory panel có thể chụp heap snapshot hoặc theo dõi allocation.

Khi điều tra chậm:

- Xác định thao tác người dùng cụ thể và thời gian bắt đầu/kết thúc.
- Phân biệt thời gian chờ network với thời gian main thread bị block.
- Tìm long task, layout thrashing, repeated DOM updates và event handler chạy quá nhiều.
- So sánh cold load với warm load và cache enabled/disabled.
- Kiểm tra bundle size, lazy loading, font/image và third-party script.
- Dùng Performance trace có thời lượng ngắn và tái hiện trên tài khoản thử nghiệm.

Heap snapshot có thể chứa token, nội dung form, email, dữ liệu hồ sơ hoặc response API trong JavaScript heap. Không tải snapshot từ production lên ticket hoặc gửi qua chat công khai. Nếu cần phân tích sâu, dùng tài khoản test và lưu artifact trong hệ thống nội bộ có kiểm soát truy cập.

### 12.1. Long task và UI freeze

Nếu UI đứng nhưng request đã hoàn tất, kiểm tra main thread. Một callback đồng bộ lớn, parse JSON lớn, render hàng nghìn node hoặc xử lý ảnh có thể làm trang không phản hồi.

Không kết luận do CPU server chỉ vì người dùng thấy spinner lâu. So sánh request timing với Performance trace. Nếu network nhanh nhưng main thread bận, tối ưu code phía client; nếu request chờ lâu ở server, đối chiếu trace backend.

## 13. Debug WebSocket và kết nối thời gian thực

Với WebSocket, kiểm tra request handshake và trạng thái `101 Switching Protocols`, sau đó xem Frames/Messages nếu DevTools hỗ trợ.

Các điểm cần rà soát:

- URL `wss://` hay `ws://`; production nên dùng TLS.
- Header `Origin` và allowlist origin ở server.
- Cookie/session có được gửi trong handshake theo policy không.
- Server có xác thực và authorize channel/topic sau handshake không.
- Ping/pong, close code, reconnect và backoff có hợp lý không.
- Message schema, kích thước và rate limit có được kiểm tra không.
- Token có bị ghi vào query string hoặc log không.

Handshake thành công không chứng minh mọi message đều hợp lệ. Server vẫn phải kiểm tra quyền cho từng channel và hành động. Khi chia sẻ log, loại bỏ nội dung message chứa dữ liệu cá nhân hoặc credential.

## 14. HAR, screenshot và bằng chứng debug

HAR (HTTP Archive) có thể ghi request/response headers, URL, timing và đôi khi body. Nó hữu ích để chuyển một lỗi Network cho nhóm khác, nhưng có thể chứa cookie, authorization header, query token, form body và dữ liệu cá nhân.

Trước khi chia sẻ HAR:

1. Dùng tài khoản test và tái hiện tối thiểu nếu có thể.
2. Chỉ ghi lại khoảng thời gian và request cần thiết.
3. Xóa `Cookie`, `Set-Cookie`, `Authorization`, API key, signed URL và token khỏi URL/header/body.
4. Xóa email, số điện thoại, ID hồ sơ, dữ liệu thanh toán và nội dung form không cần thiết.
5. Kiểm tra redirect chain và response body, không chỉ phần header.
6. Mở file HAR đã làm sạch như văn bản và tìm lại các chuỗi bí mật phổ biến trước khi gửi.
7. Chia sẻ qua hệ thống nội bộ có quyền truy cập và retention phù hợp.

Tùy chọn “sanitized HAR” của DevTools có thể loại bỏ một số header nhạy cảm, nhưng không đảm bảo xóa mọi secret trong query string, payload hoặc response body. Luôn kiểm tra thủ công bản xuất trước khi chia sẻ.

Screenshot cũng có thể hiển thị URL, tên người dùng, email, cookie panel hoặc nội dung trang. Crop vùng không cần thiết và che dữ liệu trước khi gửi. Không coi việc ẩn một phần trên ảnh gốc là xóa dữ liệu nếu file gốc vẫn được đính kèm.

## 15. Source maps và observability trong production

Debugging không nên phụ thuộc vào việc người vận hành phải mở từng tab người dùng. Hệ thống production nên có telemetry phù hợp:

- Error monitoring thu stack trace, release/build ID và browser metadata.
- RUM ghi thời gian tải, web vitals, lỗi resource và hành vi tổng hợp.
- Distributed tracing nối request ID giữa browser, gateway và backend.
- Structured logs ghi event code, status, duration và principal/tenant identifier đã được kiểm soát.
- Metrics cho tỷ lệ lỗi, latency, timeout, CORS/CSP violation và browser breakdown.
- Alert dựa trên ngưỡng và xu hướng, không chỉ một exception đơn lẻ.

Thiết kế telemetry theo data minimization:

- Không thu thập token, cookie, password, payment data hoặc nội dung form.
- Không gửi toàn bộ `location.href`; chuẩn hóa route và loại query/fragment.
- Không ghi request/response body mặc định; chỉ thu field đã allowlist và được phép.
- Pseudonymize user/tenant identifier khi có thể; kiểm soát quyền truy cập và retention.
- Không bật session replay trên trang nhạy cảm nếu chưa có masking/consent và đánh giá phù hợp.
- Kiểm tra SDK bên thứ ba không tự thu thập URL, input hoặc DOM nhạy cảm.

Source map nên được liên kết với release chính xác và lưu trong hệ thống observability có kiểm soát. Không public source map chỉ để stack trace dễ đọc nếu source nội bộ không nên công khai.

## 16. Một số tình huống production thường gặp

| Triệu chứng | Bằng chứng cần xem | Hướng điều tra |
| --- | --- | --- |
| Trang trắng sau deploy | Console exception, document/JS status, release ID, source map. | Asset hash, bundle mismatch, lỗi runtime và cache HTML. |
| API trả 401 sau thời gian idle | Cookie blocked reason, request headers, session expiry và backend request ID. | Session timeout, cookie expiry, refresh flow, tab stale hoặc clock skew. |
| API cross-origin thất bại | OPTIONS preflight, `Origin`, CORS response headers và Console. | Allowlist origin/method/header, credentials và CDN cache key. |
| Login redirect lặp | Redirect chain, cookie, `state`, callback URL đã làm sạch và server logs. | Cookie không được gửi, callback mismatch, session rotation hoặc redirect URI. |
| Script bị chặn | CSP violation, initiator, nonce/hash và response CSP. | Script nguồn mới, inline code hoặc policy deploy không đồng bộ. |
| Iframe không đọc được session | Top-level site, frame origin, cookie SameSite/Partitioned và storage access. | Third-party cookie restriction, partitioning hoặc permission. |
| Nội dung cũ sau deploy | `Age`, cache status, service worker version, Cache Storage. | CDN/browser cache, stale HTML hoặc worker cũ. |
| Trang chậm nhưng API nhanh | Performance trace, long task, layout và main-thread activity. | JS parse/render, DOM lớn, third-party script hoặc memory pressure. |
| Download không bắt đầu | Response status, Content-Disposition, MIME, blocked download và Console. | Authorization, browser download policy, header hoặc popup/user activation. |
| WebSocket đóng liên tục | Handshake, close code, timing, network changes và server logs. | TLS, origin/auth, proxy timeout, reconnect hoặc server capacity. |

## 17. Những lỗi thường gặp khi debug production

| Lỗi | Hậu quả | Cách làm tốt hơn |
| --- | --- | --- |
| Copy nguyên HAR vào ticket | Lộ cookie, token, query và dữ liệu người dùng. | Dùng tài khoản test, sanitize rồi kiểm tra lại toàn bộ file. |
| Dùng Disable cache ngay từ đầu | Che mất lỗi do cache hoặc service worker. | Quan sát trạng thái gốc trước, sau đó so sánh có/không cache. |
| Clear site data trên profile thật | Mất session và dữ liệu offline/chưa đồng bộ. | Dùng profile test hoặc staging; chỉ xóa khi hiểu tác động và được phép. |
| Chạy snippet lạ trong Console | Code có thể thao tác bằng session người dùng hiện tại. | Review code, giới hạn scope và chỉ chạy trong môi trường được phép. |
| Thử lại thao tác ghi dữ liệu nhiều lần | Tạo đơn, thanh toán hoặc thay đổi dữ liệu trùng lặp. | Dùng test fixture/idempotency key và chỉ tái hiện có kiểm soát. |
| Kết luận từ một status hoặc một log | Bỏ qua cache, proxy, service worker hoặc browser policy. | Kết hợp Network, Console, request ID và backend trace. |
| Public source map để debug nhanh | Tiết lộ cấu trúc source và comment nội bộ. | Upload map riêng theo release vào observability. |
| Tắt CSP/CORS/SameSite để hết lỗi | Tạo lỗ hổng bảo mật hoặc che nguyên nhân. | Xác định directive/attribute cụ thể và sửa cấu hình tối thiểu. |
| Thu thập quá nhiều telemetry | Tăng rủi ro quyền riêng tư và lộ dữ liệu. | Data minimization, allowlist, masking và retention. |
| Dùng remote debugging không kiểm soát | Có thể mở quyền truy cập dữ liệu và điều khiển browser profile. | Chỉ dùng trong môi trường test, giới hạn local access và tắt sau phiên. |

## 18. Checklist kết thúc phiên debug

Trước khi đóng DevTools hoặc gửi kết quả:

- Đã xác định browser/version, thời điểm, route và request ID chưa?
- Đã phân biệt request bị browser chặn với response lỗi từ server chưa?
- Đã đối chiếu Network, Console và log backend/CDN chưa?
- Đã kiểm tra cookie, CORS, CSP, cache hoặc service worker khi có dấu hiệu liên quan chưa?
- Đã ghi rõ bước tái hiện bằng tài khoản/test data chưa?
- HAR, screenshot, console log và trace đã được kiểm tra dữ liệu nhạy cảm chưa?
- Có bật Preserve log, Disable cache, throttling hoặc breakpoint làm thay đổi hành vi không? Đã ghi nhận và khôi phục trạng thái phù hợp chưa?
- Có thay đổi dữ liệu hoặc trạng thái production trong quá trình thử không? Nếu có, đã ghi lại và xử lý theo quy trình chưa?
- Đã tắt capture và đóng tab/profile debug không cần thiết chưa?
- Kết luận có phân biệt rõ bằng chứng, giả thuyết và phần chưa xác minh không?

## 19. Bài thực hành

Tạo một ứng dụng staging có trang đăng nhập, API cùng origin, API cross-origin, iframe và service worker. Dùng hai tài khoản thử nghiệm và dữ liệu giả.

1. Mở DevTools trước khi tải trang, bật Preserve log và tái hiện một redirect login.
2. Phân tích request API thành công và một request trả 401; đối chiếu cookie blocked reason và request ID.
3. Tạo lỗi CORS có kiểm soát; kiểm tra preflight và sửa allowlist origin/method/header tối thiểu.
4. Tạo một CSP violation trong staging; tìm directive, initiator và nonce/hash cần thiết.
5. Cập nhật service worker nhưng giữ tab cũ mở; quan sát waiting/activated và response từ Cache Storage.
6. Dùng Performance panel để ghi một thao tác chậm; phân biệt thời gian network với long task trên main thread.
7. Tạo source map cho build staging và liên kết với release ID trong error monitoring.
8. Xuất HAR, loại bỏ cookie/token/query/body nhạy cảm và kiểm tra lại trước khi lưu vào ticket thử nghiệm.
9. Viết báo cáo gồm điều kiện tái hiện, bằng chứng, nguyên nhân đã xác nhận, giả thuyết còn lại và đề xuất sửa.
10. Kết thúc phiên bằng cách tắt capture, xóa dữ liệu debug không cần thiết và khôi phục cài đặt DevTools đã thay đổi.

Hoàn thành bài thực hành khi bạn có thể tái hiện một lỗi browser, xác định request hoặc policy gây ra lỗi, đối chiếu được bằng chứng client với log server, và chia sẻ báo cáo đã làm sạch mà không để lộ credential hay dữ liệu người dùng.
