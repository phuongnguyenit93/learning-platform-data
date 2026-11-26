# Kiểm tra khả năng hỗ trợ header trên các trình duyệt mục tiêu

Trong chương **Nâng cấp và tương thích** của **SPRING_SECURITY_HTTP_PROTECTION**, cùng một response do Spring Security tạo ra có thể được Chrome, Edge, Firefox, Safari hoặc WebView xử lý theo những cách khác nhau. Một header xuất hiện trong tab Network **chưa chứng minh trình duyệt thực thi chính sách**: browser có thể không hiểu tên header, chỉ hỗ trợ một số directive, yêu cầu HTTPS, có cờ tính năng riêng hoặc bỏ qua header đã lỗi thời.

Với module bao quát CSRF, CORS, security headers, CSP, HSTS, HTTP firewall và bảo vệ session, kiểm tra tương thích là công việc liên kết **hợp đồng bảo mật tại server** với **hành vi thực tế trên browser**. Đội ngũ cần biết chính sách nào có thể dựa vào browser, chính sách nào phải được bảo đảm ở Spring Security và những khác biệt nào cần test trước khi nâng cấp thư viện, trình duyệt hoặc hạ tầng CDN/proxy/gateway.

Sau bài học, người học có thể:

1. Xây dựng danh sách trình duyệt/phiên bản/thiết bị mục tiêu, phân biệt browser engine, browser thương hiệu và WebView.
2. Tra cứu dữ liệu tương thích của **từng header và directive** từ MDN Browser Compatibility Data (BCD), biết cách đọc hỗ trợ một phần, bỏ hỗ trợ và yêu cầu HTTPS.
3. Thiết kế kiểm thử hành vi cho CSP, HSTS, X-Frame-Options, CORS, Clear-Site-Data, Referrer-Policy, cookie và các header mở rộng.
4. Kết hợp MockMvc/WebTestClient với Playwright và thiết bị thật để phân biệt **phát header**, **browser nhận header** và **browser thực thi**.
5. Chọn cơ chế fallback an toàn khi browser mục tiêu không hỗ trợ một kiểm soát, rồi theo dõi hồi quy sau nâng cấp.

## 1. “Hỗ trợ header” thực sự có nghĩa gì?

Một HTTP response có thể chứa:

~~~http
HTTP/2 200
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'
Strict-Transport-Security: max-age=31536000
X-Content-Type-Options: nosniff
~~~

Server đã **phát** những chuỗi này, nhưng cần tách ít nhất năm tầng kết quả:

| Tầng | Câu hỏi cần trả lời | Bằng chứng |
|---|---|---|
| **1. Tạo chính sách** | Spring Security có cấu hình đúng giá trị cần phát không? | Kiểm tra cấu hình, MockMvc/WebTestClient |
| **2. Chuyển tiếp** | CDN, reverse proxy, gateway có giữ nguyên header không? | Response của origin so với public URL |
| **3. Phân tích cú pháp** | Browser có nhận tên header và hiểu directive đang dùng không? | MDN BCD, ghi chú browser, cảnh báo console |
| **4. Thực thi** | Browser có thật sự ngăn hoặc thay đổi hành vi tương ứng không? | Kịch bản quan sát được trong browser |
| **5. Bền vững trong hệ thống** | Khi cache, chuyển tab, redirect, đăng xuất, đổi thiết bị, kết quả có còn đúng không? | E2E, profile sạch và thiết bị thực |

Ví dụ, nhận được `Content-Security-Policy` không bảo đảm browser hiểu một directive mới. Ngược lại, `Access-Control-Allow-Origin` có mặt trong response không có nghĩa JavaScript từ origin lạ đã đọc được dữ liệu; trình duyệt còn kiểm tra origin, credentials và các header liên quan.

**Phân biệt ba loại kết luận:**

- **Được hỗ trợ**: dữ liệu tương thích hoặc test chỉ ra browser có triển khai tính năng.
- **Được thực thi trong điều kiện thử**: thao tác thực tế có kết quả đúng với policy và môi trường.
- **Được bảo đảm an toàn**: kiến trúc vẫn bảo vệ tài sản kể cả khi browser không triển khai header. Kết luận cuối cần cả server-side authorization, CSRF, output encoding và session lifecycle đúng.

## 2. Xác định “trình duyệt mục tiêu” thay vì chỉ ghi Chrome/Firefox/Safari

Ma trận kiểm thử có ý nghĩa khi gắn với người dùng thật và chính sách hỗ trợ sản phẩm.

| Nhóm mục tiêu | Biến cần ghi | Vì sao ảnh hưởng kết quả |
|---|---|---|
| Desktop Chromium | Google Chrome, Microsoft Edge, phiên bản ổn định/ESR nếu có, Windows/macOS/Linux | Hai browser có thể cùng engine nhưng khác version, enterprise policy, profile và release channel |
| Desktop Firefox | Firefox stable, ESR nếu tổ chức hỗ trợ, hệ điều hành | Một số directive thử nghiệm hoặc reporting không có cùng mức hỗ trợ với Chromium |
| Desktop Safari | Phiên bản Safari gắn với macOS, máy và chính sách privacy | Cần kiểm tra bản Safari phát hành thực tế, không suy từ WebKit thử nghiệm |
| Mobile | Chrome Android, Firefox Android, Safari iOS, Samsung Internet nếu sản phẩm có người dùng | UI, bộ nhớ, cookie policy, tính năng privacy và phiên bản engine có thể khác desktop |
| Embedded browser | Android WebView, WKWebView, trình duyệt trong ứng dụng hoặc SSO webview | Cấu hình embedding app, cookie store và API platform ảnh hưởng hành vi |
| Browser legacy | Các phiên bản chưa thể nâng cấp trong doanh nghiệp, nếu có | Có thể thiếu CSP directive hiện đại, có bộ lọc XSS lỗi thời và khác mặc định TLS |

Mỗi dòng **hỗ trợ chính thức** nên ghi:

~~~yaml
# Ví dụ hồ sơ kiểm thử, cần thay bằng dữ liệu tổ chức thực.
id: desktop-chrome-stable
browser: Chrome
engine: Chromium
os: Windows
channel: stable
version_policy: latest-approved
priority: P0
features_to_check:
  - csp-script
  - hsts
  - frame-ancestors
  - clear-site-data-storage
  - samesite-cookie
owner: frontend-security
last_verified: "2026-11-26"
~~~

Không biến `latest-approved` thành một con số cố định không cập nhật. Khi test, log **version đầy đủ của binary thực tế**; khi một bản cập nhật browser xảy ra, gắn kết quả với version đó. Lưu ngày tra cứu tài liệu tương thích và danh sách feature flags/enterprise policies có thể thay đổi hành vi.

### 2.1. Engine, bản phát hành và thiết bị không hoàn toàn tương đương

- **Playwright `chromium`** kiểm thử engine do Playwright phân phối; có thể thêm project chạy browser branded `chrome` và `msedge` nếu cần.
- **Playwright `firefox`** dùng bản Firefox có patch phục vụ automation; không thay thế hoàn toàn việc thử Firefox bản phát hành thực.
- **Playwright `webkit`** chạy bản WebKit được Playwright tích hợp, **không đồng nhất với Safari chính thức**; tính năng Safari có thể ra mắt muộn hơn hoặc khác hành vi hệ điều hành.
- Chế độ **mobile emulation** thường mô phỏng viewport, input và một số thuộc tính thiết bị; nó không thay trình duyệt iOS/Android thực khi kiểm thử cookie, WebView, HSTS, storage hay policy của hệ điều hành.
- WebView trong ứng dụng có thể cấu hình navigation, cookie, permission, third-party cookies và phiên đăng nhập khác trình duyệt ngoài.

Vì vậy nên có **hai lớp ma trận**: automation xuyên engine để phát hiện regression nhanh; thiết bị/binary thật cho các luồng có rủi ro tương thích cao.

## 3. Tra cứu dữ liệu từ MDN BCD cho đúng từng directive

MDN thường gắn nhãn **Baseline / Limited availability**, biểu đồ browser và bảng tương thích. Dữ liệu gốc nằm trong dự án **MDN Browser Compatibility Data (BCD)**, chẳng hạn entry cho `Clear-Site-Data` hoặc từng CSP directive.

Ví dụ giản lược cấu trúc một support statement:

~~~json
{
  "__compat": {
    "support": {
      "chrome": {
        "version_added": "61"
      },
      "firefox": {
        "version_added": "63"
      },
      "safari": {
        "version_added": "17"
      }
    }
  }
}
~~~

Đây là **ví dụ trích rút dữ liệu về header Clear-Site-Data nói chung**, không phải lời hứa rằng **mọi directive của header** đều được thực thi đồng nhất. Những entry riêng cho `"cache"`, `"storage"`, `"executionContexts"`, `"prefetchCache"` có thể khác hẳn nhau.

Cách hiểu metadata:

| Trường BCD | Ý nghĩa | Cách sử dụng |
|---|---|---|
| `version_added` | Phiên bản bắt đầu hỗ trợ; `false` nghĩa là chưa hỗ trợ theo dữ liệu | So sánh với version trong support matrix |
| `version_removed` | Phiên bản đã bỏ tính năng | Quan trọng với header cũ như `X-XSS-Protection` |
| `partial_implementation` | Browser chỉ triển khai một phần hoặc có khác biệt đáng kể | Phải đọc note, tạo case test riêng |
| `flags` | Chỉ hoạt động khi bật cờ tính năng/chế độ đặc biệt | Không tính là hỗ trợ mặc định của người dùng |
| `notes` | Bug, giới hạn, điều kiện cụ thể của engine | Chuyển thành acceptance criteria có thể quan sát |
| `alternative_name` / `prefix` | Tên thay thế hoặc tiền tố lịch sử | Xác định có cần tương thích legacy hay không |

**Quy trình tra cứu nên làm:**

1. Lấy **tên header**, sau đó tra **directive/subfeature** chính xác. Ví dụ `Content-Security-Policy` → `frame-ancestors` hoặc `require-trusted-types-for`.
2. Xem trạng thái `experimental`, `deprecated` và note cho browser mục tiêu.
3. Ghi **ngày truy vấn** và nguồn MDN/BCD; không sao chép kết luận “mọi browser hỗ trợ” không có phiên bản.
4. Chuyển từng điểm chưa chắc chắn thành test trên **browser/binary đúng version**.
5. Khi version browser mục tiêu hoặc BCD thay đổi, chạy lại test liên quan; không coi bảng tương thích là snapshot vĩnh viễn.

Các nguồn phổ biến: [MDN Browser Compatibility Data](https://github.com/mdn/browser-compat-data), [MDN HTTP Headers](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers), [Can I use](https://caniuse.com/) và release notes của từng nhà cung cấp. Dữ liệu cộng đồng là đầu vào quyết định, còn **hành vi trên môi trường mục tiêu** mới xác nhận ứng dụng thực hoạt động đúng.

## 4. Ma trận ưu tiên cho các header thường dùng trong Spring Security

Bảng dưới đây mô tả **mức độ cần kiểm thử và kiểu khác biệt**, không thay cho bảng “phiên bản hỗ trợ” theo thời gian. Mỗi tổ chức phải gắn version cụ thể trước khi công nhận PASS.

| Header hoặc nhóm | Đánh giá triển khai hiện đại | Điều cần test trong browser | Cách giữ an toàn khi thiếu hỗ trợ |
|---|---|---|---|
| `Content-Security-Policy`: `script-src`, `object-src`, nonce/hash | Cơ chế phòng vệ chủ đạo được hỗ trợ rộng; **directive mới có thể khác** | Script inline/ngoài allowlist bị chặn; script hợp lệ vẫn chạy | Output encoding, sanitization và DOM APIs an toàn |
| CSP `frame-ancestors` | Hỗ trợ rộng trong browser hiện đại; phải test embed thực | Trang không bị nhúng bởi parent bị cấm | `X-Frame-Options` tương thích browser cũ, cùng server authorization |
| `X-Frame-Options` | Cơ chế clickjacking lâu đời; `ALLOW-FROM` đã lỗi thời | `DENY`/`SAMEORIGIN` trên iframe thật | CSP `frame-ancestors` và chiến lược UI/authorization |
| `Strict-Transport-Security` | Cơ chế phổ biến, phụ thuộc HTTPS và trạng thái đã ghi nhớ | HTTP navigation sau khi HSTS được học, preload nếu có | HTTPS redirect, TLS end-to-end và cookie `Secure` |
| `X-Content-Type-Options: nosniff` | Cơ chế phổ biến | Script/style MIME sai bị chặn | Trả Content-Type đúng, không phục vụ dữ liệu untrusted như script |
| `Referrer-Policy` | Hỗ trợ rộng; token/URL mode phải đúng | `Referer` thực khi điều hướng cross-origin | Không đặt secret/token trong query URL |
| `Cache-Control` | Cơ chế nền tảng của HTTP nhưng cache có nhiều tầng | `no-store` trên dữ liệu riêng; back/forward/cache đúng mục đích | Authorization server-side, CDN bypass dữ liệu xác thực |
| CORS `Access-Control-Allow-*` | Cơ chế browser phổ biến, nhiều điều kiện phối hợp | Preflight, credentials, origin, Vary, request thật | Luôn xác thực/ủy quyền/CSRF ở server |
| `Clear-Site-Data` | Header chính có thể được hỗ trợ; **directive khác nhau rõ** | Cookie/storage/cache được xóa đúng origin/site khi HTTPS | Invalidating session/revoking token và frontend cleanup |
| `X-XSS-Protection` | **Deprecated**; nhiều browser không còn bộ lọc tương ứng | Hiểu tại sao `0` có chủ đích; không phụ thuộc `mode=block` | CSP, output encoding và sanitization |
| `Permissions-Policy` | Nhiều directive còn giới hạn/khác biệt engine | Camera, geolocation, microphone hoặc API được định rõ có bị giới hạn không | Kiểm soát quyền ở browser/OS và xác minh nghiệp vụ ở server |
| `Cross-Origin-Opener-Policy` / `Cross-Origin-Embedder-Policy` / `Cross-Origin-Resource-Policy` | Phải kiểm tra riêng policy, browser và loại resource | Isolation, popup OAuth, cross-origin asset, iframe | Thiết kế tích hợp tài nguyên, CORS/CORP đúng policy |
| CSP `require-trusted-types-for` | Khả năng hỗ trợ đang thay đổi theo browser/version | DOM sinks từ chối string khi policy thực thi | Safe DOM sinks và sanitizer ở toàn bộ browser |

Đừng đánh đồng các thuộc tính cookie `SameSite`, `Secure`, `HttpOnly` với security response headers theo nghĩa API header writer. Chúng thuộc `Set-Cookie` và chịu quy tắc **chấp nhận/gửi cookie** của browser, vì vậy cần một nhóm test riêng.

## 5. Kiểm thử CSP: nhận header rồi phải quan sát script thật

CSP là ví dụ điển hình của việc **hỗ trợ tên header ≠ hỗ trợ mọi directive**. Một CSP cơ bản:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
~~~

Trong thử nghiệm, cần xác minh ít nhất:

1. Script bên ngoài thuộc cùng origin được phép tải và chạy.
2. Một script **inline không có nonce/hash** bị chặn bởi `script-src 'self'`.
3. Script có nonce hoặc hash đúng được cho phép theo policy đã xây dựng; nonce sai không được phép.
4. `frame-ancestors 'none'` chặn trang được nhúng trong iframe từ origin khác **và cùng origin** theo nội dung policy.
5. `Content-Security-Policy-Report-Only` báo vi phạm nhưng không thực thi chặn.
6. Đường HTML qua CDN/proxy không cache nonce của response riêng rồi tái sử dụng sai.

Ví dụ **fixture dành riêng cho test**, không đưa vào trang sản phẩm:

~~~html
<!doctype html>
<html lang="vi">
  <meta charset="utf-8">
  <body>
    <p id="inline-status">not-run</p>
    <script>
      document.getElementById("inline-status").textContent = "ran";
    </script>
  </body>
</html>
~~~

Fixture được phục vụ qua HTTPS tại `/compat/csp` với response header:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'
~~~

Nếu browser **thực thi** CSP này, đoạn script inline không được cấp phép không chạy và nội dung vẫn là `not-run`. Nếu chỉ dùng **Report-Only**, script có thể chạy và nội dung đổi thành `ran`; báo cáo không phải bằng chứng đã chặn.

Một số điểm cần ghi nhớ:

- `frame-ancestors` được áp dụng qua **HTTP response header**; không dựa vào thẻ `<meta http-equiv="Content-Security-Policy">` để kiểm soát framing.
- Một số directive mới không có hiệu lực trên browser/phiên bản cũ. Kịch bản test cần kiểm tra **mục tiêu cụ thể**, không chỉ “CSP có hiệu lực”.
- Nhiều CSP headers có thể tạo tập chính sách cùng được áp dụng, làm trang bị chặn ngoài ý muốn; so sánh response origin và public URL.
- CSP không thay thế việc encode văn bản, sanitize rich text hay sửa các DOM sink như `innerHTML`.

## 6. Clickjacking: so sánh `frame-ancestors` và `X-Frame-Options`

Hai cơ chế có thể cùng dùng để ngăn nhúng trang nhạy cảm:

~~~http
X-Frame-Options: DENY
Content-Security-Policy: frame-ancestors 'none'
~~~

Với yêu cầu “không trang nào được nhúng”, hai policy này thống nhất về mục tiêu. Với yêu cầu nhúng từ một portal được phép, cần thiết kế cẩn thận: một CSP cho phép portal nhưng `X-Frame-Options: DENY` có thể chặn trên browser cũ hoặc trong các ngữ cảnh không hỗ trợ quy tắc CSP như dự kiến.

Không sử dụng `X-Frame-Options: ALLOW-FROM` làm fallback hiện đại: đây là directive đã lỗi thời và nhiều browser bỏ qua. Kiểm thử phải dùng **trang cha thực tại một origin khác**, chứa:

~~~html
<iframe src="https://admin.example.test/compat/secret"
        title="Khung thử nghiệm clickjacking"></iframe>
~~~

Đo kỳ vọng bằng việc **nội dung bí mật có được render trong frame hay không**; status code của URL khi gọi trực tiếp không thể chứng minh protection chống framing. Với nested iframe, CSP `frame-ancestors` xét cả chuỗi ancestor, không chỉ parent gần nhất.

## 7. HSTS: cần trạng thái trình duyệt và HTTPS thật

HSTS không phải chỉ cần thấy một header:

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

Browser **chỉ tiếp nhận HSTS qua kết nối HTTPS hợp lệ**. Khi nhận, nó ghi nhớ rằng các lần truy cập sau tới hostname phải dùng HTTPS theo thời hạn; `includeSubDomains` mở rộng phạm vi nếu được chọn. HSTS không tự bảo vệ request đầu tiên của một domain chưa có chính sách ghi nhớ, trừ khi browser đã có **preload entry** phù hợp.

### 7.1. Hai kịch bản khác nhau

**Kịch bản A — Profile mới, chưa biết HSTS**

1. Tạo browser profile sạch, dùng domain test HTTPS có chứng chỉ hợp lệ.
2. Điều hướng lần đầu bằng URL HTTPS; xác nhận response có header HSTS đúng chính sách.
3. Kiểm tra browser lưu policy qua khả năng chẩn đoán hiện có; không đoán từ một response 200.

**Kịch bản B — Đã học HSTS**

1. Sử dụng profile đã truy cập HTTPS hợp lệ và nhận HSTS.
2. Thử điều hướng đến `http://host-test.example.test/path`.
3. Quan sát browser **nâng lên HTTPS trước khi thực hiện network HTTP** theo hành vi HSTS; phân biệt browser internal upgrade với response redirect `301/308` của server.
4. Nếu domain có preload, cần test trên browser đã biết danh sách preload tương ứng; không thể dùng profile sạch để xóa preload tích hợp.

Không sử dụng domain sản xuất thật để thử một `max-age` rất dài hoặc `includeSubDomains` tùy tiện: HSTS được lưu tại browser và có thể tác động các phiên thử nghiệm kế tiếp. Dùng subdomain test tách biệt, có chứng chỉ và quy trình khôi phục rõ ràng.

### 7.2. Lưu ý Spring Security sau proxy

Spring Security mặc định chỉ thêm HSTS khi request được nhận diện là secure. Nếu TLS kết thúc ở CDN/reverse proxy, backend nhận HTTP và không xử lý forwarded headers đúng, origin có thể không phát header. Kiểm chứng tại **URL công khai HTTPS** và xác định owner HSTS (edge hoặc Spring). Bản test MockMvc `secure(true)` chỉ kiểm tra quyết định của Spring trong request giả lập; không kiểm tra TLS thực ở edge.

## 8. CORS và cache: test browser, không chỉ `curl`

CORS là tập các quy tắc liên quan nhiều header. Ví dụ frontend `https://app.example.test` gọi API `https://api.example.test` có cookie:

~~~http
OPTIONS /api/orders HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Response preflight được phép:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET, POST
Access-Control-Allow-Headers: content-type,x-csrf-token
Access-Control-Allow-Credentials: true
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Browser phải kiểm tra request thật theo origin và credential; không thể cho credentialed CORS dùng wildcard `Access-Control-Allow-Origin: *`. Một response API HTTP 200 **không có nghĩa** JavaScript đã đọc được dữ liệu nếu browser chặn CORS. Ngoài ra, CORS không phải xác thực hoặc CSRF: client ngoài trình duyệt có thể gửi HTTP request mà không chịu chính sách đọc của browser.

Các test bắt buộc:

| Test | Điều kiện | Kết quả quan sát |
|---|---|---|
| Allowed origin, preflight | `Origin` được phép, method/header phù hợp | Browser gửi request thật, đọc response được nếu đã authenticated |
| Disallowed origin | Origin lạ | Browser không cấp quyền đọc, dù server có thể đã nhận request |
| Credentials | `fetch` có `credentials: 'include'` | CORS headers cụ thể, cookie theo SameSite và browser policy |
| Duplicate headers | Edge và Spring cùng phát `Access-Control-Allow-Origin` | Phát hiện browser từ chối vì hai giá trị trùng/mâu thuẫn |
| Vary/cache | Hai `Origin` hoặc preflight method khác nhau qua CDN | Shared cache không trả CORS policy sai origin |
| Authentication | Preflight không có cookie thông thường | `OPTIONS` hợp lệ được xử lý trước authentication, request thật vẫn phải kiểm soát quyền |

`curl -i -X OPTIONS` hữu ích để quan sát **response headers**, nhưng không mô phỏng browser enforcement. Test cross-origin phải chạy từ một trang có origin thực phù hợp, không chỉ thêm `Origin` bằng JavaScript trên cùng một tab rồi suy diễn.

## 9. `Clear-Site-Data`: kiểm tra từng directive và phạm vi xóa

Header sau logout:

~~~http
Clear-Site-Data: "cache", "cookies", "storage"
~~~

Chỉ có ý nghĩa khi browser hỗ trợ và ở ngữ cảnh an toàn phù hợp, thông thường là **HTTPS**. MDN BCD phân biệt hỗ trợ **header cơ bản** và **các directive mở rộng**. Không dựa vào trạng thái “widely available” của header để suy rằng `"executionContexts"`, `"clientHints"`, `"prefetchCache"` hoặc `"prerenderCache"` đã hoạt động ở mọi engine.

| Directive | Cần quan sát | Rủi ro kiểm thử |
|---|---|---|
| `"cache"` | Tài nguyên từ cache có bị bỏ theo hành vi browser mục tiêu | Có thể còn bộ nhớ đệm ở CDN/proxy; một số hành vi phụ thuộc reload/tab mới |
| `"cookies"` | Cookie trong phạm vi registered domain/subdomain được yêu cầu xóa | Có thể ảnh hưởng ứng dụng khác cùng domain |
| `"storage"` | LocalStorage, IndexedDB, Service Worker/storage thuộc origin được yêu cầu xóa | Mất bản nháp/ứng dụng offline; API khác origin không xóa storage SPA |
| `"executionContexts"` | Ngữ cảnh tài liệu khác của origin có reload/được vô hiệu hóa không | Hỗ trợ browser khác nhau; cần cơ chế đồng bộ tab riêng |
| `"clientHints"` | Trạng thái Client Hints đã ghi nhớ | Không khả dụng đồng đều giữa các engine |
| `"prefetchCache"`, `"prerenderCache"` | Kết quả speculative loading được bỏ theo phạm vi được đặc tả | Tính năng mới; chỉ kết luận sau khi kiểm tra browser mục tiêu |
| `"*"` | Các loại dữ liệu browser hiểu được yêu cầu xóa | Rộng hơn dự tính, hành vi một phần khác nhau giữa browser |

Kịch bản thực nghiệm an toàn:

1. Tạo **browser context riêng cho bài test** với origin thử nghiệm, không dùng dữ liệu thật.
2. Lưu dấu thử vào `localStorage`, một cookie thử và nếu cần IndexedDB, ghi nhận giá trị ban đầu.
3. Thực hiện logout có response `Clear-Site-Data` từ **cùng origin** cần xóa storage.
4. Kiểm tra response cuối cùng có header và đủ dấu nháy kép; sau đó reload/tab mới và đo dữ liệu nào còn tồn tại theo browser target.
5. Thử trong tab khác, browser khác, và theo từng directive; lưu “PASS/PARTIAL/UNSUPPORTED” thay vì chỉ ghi “header đã có”.
6. Kiểm tra session ở server đã invalidated hoặc refresh token được thu hồi theo kiến trúc, dù browser bỏ qua header.

**Quan trọng:** `"storage"` từ `https://api.example.test` không tự xóa `localStorage` của `https://app.example.test`. `"cookies"` có phạm vi rộng hơn, có thể ảnh hưởng nhiều subdomain cùng registered domain. Đây là lý do phải có kịch bản **negative impact** khi thử logout trên các ứng dụng cùng miền.

## 10. Cookie và header mới: mức hỗ trợ thay đổi theo platform

### 10.1. Cookie được browser chấp nhận hay bị bỏ?

Một response có thể gửi:

~~~http
Set-Cookie: session=example; Path=/; Secure; HttpOnly; SameSite=None
~~~

Nhưng browser có thể từ chối cookie nếu kết nối không an toàn, thiếu `Secure` khi dùng `SameSite=None`, domain/path không hợp lệ, hoặc chính sách chặn third-party cookies. Vì vậy test:

- **`Secure`:** cookie phiên được chấp nhận và chỉ gửi theo điều kiện HTTPS; localhost có ngoại lệ ở một số browser, không thay cho HTTPS thật.
- **`HttpOnly`:** script không đọc được qua `document.cookie`; trong DevTools/automation cookie vẫn có thể xuất hiện.
- **`SameSite=Lax/Strict/None`:** kiểm tra navigation cross-site, redirect login/SSO, POST cross-site và Fetch có credentials.
- **`Domain`, `Path`:** browser gửi cookie đúng phạm vi; đừng coi Path là cơ chế authorization.
- **Cookie prefix `__Host-` / `__Secure-`:** kiểm tra quy tắc prefix; browser không hỗ trợ prefix có thể đối xử như tên cookie thông thường.
- **`Partitioned` / CHIPS:** nếu triển khai, kiểm tra hỗ trợ trên từng browser, top-level site isolation và khả năng fallback khi không được phân vùng.

`Set-Cookie` là **forbidden response header name** đối với frontend JavaScript trong nhiều ngữ cảnh Fetch; `response.headers.get('set-cookie')` không phải cách đọc cookie session. Dùng cookie inspection của browser automation hoặc DevTools.

### 10.2. Permissions Policy và các tính năng hạn chế

Ví dụ:

~~~http
Permissions-Policy: camera=(), microphone=(), geolocation=()
~~~

Mục đích là giới hạn một số capability của trang và iframe. Tuy nhiên **hỗ trợ của header và từng directive không đồng đều**; một số API hoặc tham số có thể chỉ có trên Chromium hoặc mới được bổ sung ở browser khác. Test bằng **API thực** trong một trang fixture có quyền/điều kiện thiết bị phù hợp; không chỉ tìm chuỗi `Permissions-Policy`.

Chưa có hỗ trợ không đồng nghĩa API nguy hiểm được phép tùy ý: browser còn có permission prompts, OS policy và secure-context requirements. Các kiểm soát nghiệp vụ như “user có được tải file hoặc xem dữ liệu này không” phải nằm ở server.

### 10.3. COOP, COEP, CORP và isolation

Đối với ứng dụng dùng `SharedArrayBuffer` hoặc tính năng cần cross-origin isolation, có thể gặp:

~~~http
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
Cross-Origin-Resource-Policy: same-origin
~~~

Không áp dụng bộ ba này toàn cục chỉ để “tăng điểm security headers”. Nó có thể ảnh hưởng OAuth popup, iframe, video/image/font từ CDN, tài nguyên third-party. Test:

- `window.crossOriginIsolated` trên context thực khi policy và browser cho phép.
- Popup login hoặc payment còn dùng được; kiểm tra mối quan hệ `window.opener` nếu ứng dụng cần.
- Cross-origin resource được tải theo CORS/CORP đúng quy tắc.
- Khi dùng `COEP: credentialless` hoặc iframe `credentialless`, kiểm tra tính tương thích riêng, nhất là cookie và khả năng hiển thị ở browser target.

### 10.4. Trusted Types và các CSP directive mới

`Content-Security-Policy: require-trusted-types-for 'script'` giúp ngăn đưa raw string vào một số DOM XSS sinks ở browser hỗ trợ. Trạng thái hỗ trợ đã mở rộng theo thời gian, vì vậy **không dựa vào kết luận cũ “chỉ Chromium hỗ trợ” hoặc kết luận mới “mọi trình duyệt đều hỗ trợ”**. Tra BCD tại ngày phát hành và thử trên các version được hỗ trợ, kể cả browser cũ chưa cập nhật.

Test nên xác minh `innerHTML` nhận raw string bị chặn theo policy đang enforce, Trusted Type được tạo qua policy hợp lệ được xử lý như thiết kế. Với browser thiếu hỗ trợ, vẫn cần `textContent`, sanitizer và output encoding đúng ngữ cảnh.

## 11. Tạo response nhất quán từ Spring Security

Spring Security Servlet và Reactive đều hỗ trợ security response headers mặc định như `X-Content-Type-Options`, `X-Frame-Options`, `Cache-Control` và HSTS trên HTTPS. **CSP không có một policy mặc định an toàn cho mọi ứng dụng**, nên cần cấu hình theo nhu cầu.

### 11.1. Servlet: `HttpSecurity`

Ví dụ policy cố định cho **trang nội bộ không dùng inline script hoặc iframe**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ServletSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/compat/**").permitAll()
                .anyRequest().authenticated())
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp.policyDirectives(
                    "default-src 'self'; " +
                    "script-src 'self'; " +
                    "object-src 'none'; " +
                    "base-uri 'self'; " +
                    "frame-ancestors 'none'"
                ))
            );

        // Thêm cơ chế xác thực theo nhu cầu ứng dụng.
        return http.build();
    }
}
~~~

`/compat/**` trong ví dụ chỉ dành cho **fixture test không có dữ liệu nhạy cảm**. Không mở `permitAll` cho đường quản trị thật. Nếu sản phẩm cần inline script, iframe, CDN hoặc nonce theo request, sửa CSP theo chính sách riêng. Không dùng `headers.disable()` chỉ vì một browser không hỗ trợ một directive: lệnh đó sẽ bỏ cả các header mặc định khác.

### 11.2. Reactive: `ServerHttpSecurity`

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/login", "/compat/**").permitAll()
                .anyExchange().authenticated())
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp.policyDirectives(
                    "default-src 'self'; " +
                    "script-src 'self'; " +
                    "object-src 'none'; " +
                    "base-uri 'self'; " +
                    "frame-ancestors 'none'"
                ))
            )
            .build();
    }
}
~~~

Đây là cấu hình minh họa điểm tích hợp writer; các endpoint, cơ chế authentication, CSRF và session phải phù hợp ứng dụng. Khi test cross-browser, **header của Servlet và Reactive có thể giống nhau** nhưng điều kiện kỹ thuật khác nhau ở filter chain và gateway. Hãy xác minh chính xác response của deployment chứ không chỉ đọc code DSL.

## 12. Tầng kiểm thử 1: MockMvc và WebTestClient xác minh phía server

### 12.1. Servlet MockMvc

Với endpoint fixture `GET /compat/csp` thực sự tồn tại, `spring-security-test` và cấu hình Servlet ở trên:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ServletHeadersRegressionTest {

    @Autowired MockMvc mvc;

    @Test
    void secureResponseIncludesPolicy() throws Exception {
        mvc.perform(get("/compat/csp").secure(true))
            .andExpect(status().isOk())
            .andExpect(header().exists("Content-Security-Policy"))
            .andExpect(header().string("X-Content-Type-Options", "nosniff"))
            .andExpect(header().exists("Strict-Transport-Security"));
    }
}
~~~

`secure(true)` tạo request giả được xem là HTTPS, quan trọng với HSTS writer của Spring Security. Nếu Spring được cấu hình cố ý không phát HSTS hoặc một chain khác xử lý URL, thay assertion theo contract đó. **MockMvc không có engine của browser**, nên không thể kết luận CSP được thực thi.

### 12.2. Reactive WebTestClient

Với ứng dụng WebFlux có endpoint fixture tương ứng:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveHeadersRegressionTest {

    @Autowired WebTestClient client;

    @Test
    void responseHasContentTypeProtection() {
        client.get().uri("/compat/csp")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                "X-Content-Type-Options", "nosniff");
    }
}
~~~

Cấu hình trên sử dụng `@AutoConfigureWebTestClient` của **Spring Boot 3.x** với ứng dụng WebFlux. Ở Spring Boot 4.x, package auto-configuration có thể thay đổi so với 3.x: cần dùng API phù hợp dependency thật của dự án. Nếu không dùng autoconfiguration, có thể tạo `WebTestClient` bind vào application context hoặc HTTP server test. Đoạn minh họa ở đây trình bày **loại assertion** cần có, không kiểm chứng browser behavior.

Kiểm tra thêm response `401/403`, redirect, handler của tài nguyên tĩnh và error pages: không nên giả định mọi response đi qua cùng security chain hoặc qua origin Spring.

## 13. Tầng kiểm thử 2: Playwright theo nhiều engine

Playwright hỗ trợ `projects` để cùng test chạy trên Chromium, Firefox, WebKit và browser branded nếu có cài đặt. Ví dụ `playwright.config.ts`:

~~~typescript
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  use: {
    baseURL: "https://staging.example.test",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "firefox",
      use: { ...devices["Desktop Firefox"] },
    },
    {
      name: "webkit",
      use: { ...devices["Desktop Safari"] },
    },
  ],
});
~~~

`Desktop Safari` trong cấu hình Playwright chọn thiết lập thiết bị tương ứng **với engine WebKit của Playwright**; nó không chạy app Safari phát hành. Đối với browser branded, thêm project riêng với `channel: "chrome"` hoặc `"msedge"` khi hệ thống CI đã cài binary phù hợp.

### 13.1. Test CSP: hành vi thay vì chỉ kiểm header

Fixture `/compat/csp` ở mục 5 có trạng thái `not-run` và script inline cố đổi thành `ran`:

~~~typescript
import { test, expect } from "@playwright/test";

test("CSP từ chối script inline không có nonce", async ({ page }) => {
  const response = await page.goto("/compat/csp");
  expect(response?.status()).toBe(200);

  const csp = response?.headers()["content-security-policy"];
  expect(csp).toContain("script-src 'self'");

  // Assertion hành vi quan trọng hơn: script inline bị chặn thật.
  await expect(page.locator("#inline-status")).toHaveText("not-run");
});
~~~

Với fixture chỉ gửi `Content-Security-Policy-Report-Only`, test phải có expected khác: inline script vẫn được phép chạy; chỉ ghi nhận vi phạm. Có thể thu event console/report khi cần, nhưng **không coi việc có message là đủ** nếu ứng dụng mong CSP thực thi chặn.

### 13.2. Test header hiện diện độc lập với enforcement

~~~typescript
test("response public không làm mất các header cơ bản", async ({ page }) => {
  const response = await page.goto("/compat/csp");
  expect(response).not.toBeNull();
  const headers = response!.headers();

  expect(headers["x-content-type-options"]).toBe("nosniff");
  expect(headers["content-security-policy"]).toContain("object-src 'none'");
});
~~~

Phần này chỉ xác nhận header được **nhận qua network**. Các test fixture hành vi như CSP, clickjacking, CORS, HSTS, cookie và Clear-Site-Data vẫn cần chạy riêng.

### 13.3. Kiểm thử trên môi trường khác origin

Với CORS hoặc iframe, cần **hai hostname HTTPS thuộc origin khác nhau**, chẳng hạn:

~~~text
https://app.example.test       # Trang thử nghiệm browser
https://api.example.test       # API preflight và CORS
https://embed.example.test     # Parent iframe để test frame-ancestors
~~~

Trang tại `app.example.test` mới có thể gọi `fetch("https://api.example.test/...")` để quan sát browser CORS; trang `embed.example.test` mới thực hiện iframe test đúng ngữ cảnh. Không giả lập hai origin bằng hai path dưới cùng một hostname rồi kết luận cross-origin behavior.

## 14. Tầng kiểm thử 3: thiết bị thực, tình huống âm và môi trường sạch

| Trường hợp | Vì sao cần test thực | Expected |
|---|---|---|
| Safari iOS sau nâng cấp OS | Browser engine, cookie/privacy, storage và policy OS | Login, CSP, cookie và logout theo contract |
| Firefox ESR trong doanh nghiệp | Khoảng cách version với browser mới | Directive hiện có hoạt động; tính năng mới có fallback |
| Chrome/Edge profile có enterprise policy | Policy có thể khóa hoặc sửa behavior | Không bypass server-side authorization; trình bày hạn chế |
| Android WebView trong app | Host app có cấu hình cookie, navigation, permission | Flow login/OIDC và redirect không mất session |
| Profile sạch chưa có HSTS | HSTS cần được học/preload trước khi nâng cấp HTTP | HTTPS redirect đầu tiên và sau đó HSTS đúng |
| Browser đã có HSTS/cookie/cache | State cũ ảnh hưởng nâng cấp | Không login loop, không cache dữ liệu nhạy cảm |
| Browser không hỗ trợ `Clear-Site-Data` directive | Dữ liệu local có thể còn | Backend session/token đã vô hiệu, frontend tự dọn state cần thiết |
| CSP nâng từ report-only sang enforce | HTML/script hợp lệ có thể bị chặn | Ứng dụng dùng được, script vi phạm bị chặn |
| Trình duyệt khi mất mạng | Service Worker/PWA có thể trả dữ liệu cũ | Không sử dụng lại quyền truy cập hết hiệu lực; dữ liệu offline xử lý theo policy |

### 14.1. Điều kiện kết quả PASS phải cụ thể

Ví dụ:

~~~yaml
case_id: CSD-STORAGE-HTTPS
browser: Safari
os: macOS
browser_version: "<ghi bản phát hành thực>"
precondition: "Test profile sạch; localStorage có key thử"
response: 'Clear-Site-Data: "storage"'
observable: "Key thử biến mất sau logout/reload theo browser target"
server_assertion: "Phiên bảo vệ bị vô hiệu hóa"
result: PASS_OR_PARTIAL_OR_UNSUPPORTED
evidence: ["request ID", "header cuối", "before-after storage"]
verified_at: "<ngày thử thật>"
~~~

Đây là **mẫu biên bản test**, không phải kết luận Safari nào cũng đạt mọi directive. Tách `UNSUPPORTED` khỏi `FAIL` giúp biết cần fallback hay ứng dụng đã regression. Đối với bảo vệ tối quan trọng, thiếu hỗ trợ không được làm lộ dữ liệu hoặc cho truy cập trái phép.

## 15. Quy trình thực tế để duy trì browser compatibility matrix

### Bước 1 — Thu thập danh sách trình duyệt được hỗ trợ

Phối hợp với người sở hữu sản phẩm, hỗ trợ khách hàng và dữ liệu telemetry **đã ẩn danh/tổng hợp**. Ghi rõ phiên bản tối thiểu, hệ điều hành, WebView, các browser có chính sách doanh nghiệp và thời hạn hỗ trợ. Không đưa mọi bản browser tồn tại vào cùng một ma trận vô hạn.

### Bước 2 — Gán mức độ quan trọng cho từng header

Tạo nhóm:

- **P0 (bảo vệ quan trọng):** CSP cho ứng dụng nhiều script, HSTS cho HTTPS, chống clickjacking, session cookie, CORS/CSRF theo mô hình xác thực. Khi browser không hiểu một phần policy, phải có bảo vệ bổ sung phù hợp.
- **P1 (chức năng/tương thích):** Referrer-Policy, Clear-Site-Data, một số tùy chọn báo cáo hoặc phân vùng cookie nếu sản phẩm dùng.
- **P2 (mở rộng/đang thử nghiệm):** directive Permissions-Policy mới, speculative cache, isolation tùy tính năng.

Mức P0/P1/P2 **do đội ngũ quyết định theo threat model**, không phải nhãn chung áp dụng cho mọi ứng dụng.

### Bước 3 — Tra BCD và ghi chú khác biệt

Ghi link MDN/BCD, ngày, version browser, directive, note `partial_implementation`. Từ mỗi ghi chú tạo một test có hành vi quan sát được. Đối với CSP, tra từng directive chứ không chỉ `Content-Security-Policy`.

### Bước 4 — Kiểm chứng server và đường công khai

Chạy MockMvc/WebTestClient để đảm bảo Spring phát header theo chain. Sau đó kiểm tra URL public sau CDN/gateway:

~~~bash
# GET thật, in response header và bỏ body.
curl -sS -D - -o /dev/null https://staging.example.test/compat/csp

# Preflight CORS; đây chỉ là kiểm tra HTTP, không thay browser enforcement.
curl -sS -i -X OPTIONS https://api.example.test/api/check \
  -H 'Origin: https://app.example.test' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type,x-csrf-token'
~~~

Đối chiếu hostname public, redirect, cache response, `Vary`, HSTS và sự tồn tại **một** bộ CORS headers không mâu thuẫn. `curl` không tự áp dụng CORS, CSP, HSTS, cookie SameSite hoặc Clear-Site-Data như trình duyệt.

### Bước 5 — Chạy browser test trên đúng engine, version và state

Bắt đầu với browser automation đa engine, sau đó test browser branded, Firefox ESR, Safari iOS hoặc WebView nếu nằm trong support matrix. Dùng cả profile sạch và profile đã có cookie/cache/HSTS; chạy HTTPS và hai origin khi cần.

### Bước 6 — Phân loại PASS/PARTIAL/FAIL/UNSUPPORTED

| Kết quả | Nghĩa | Hành động |
|---|---|---|
| `PASS` | Browser thực hiện đúng hợp đồng trên phiên bản và điều kiện đã ghi | Giữ regression test |
| `PARTIAL` | Chỉ một phần directive/behavior đạt, thường có ghi chú BCD | Mở issue hoặc áp dụng fallback; test lại sau browser update |
| `FAIL` | Một browser dự kiến hỗ trợ nhưng hành vi không đúng contract | Phân biệt browser bug và lỗi response/hạ tầng/app; xử lý trước release nếu mức rủi ro cao |
| `UNSUPPORTED` | Browser không triển khai tính năng cần test | Không giả định được bảo vệ; áp dụng fallback phía frontend/server |
| `NOT_APPLICABLE` | Ứng dụng không dùng tính năng đó | Ghi lý do, không bắt buộc chạy |
| `BLOCKED` | Môi trường test thiếu certificate, test domain hoặc access | Sửa test infrastructure trước khi kết luận |

### Bước 7 — Theo dõi thay đổi sau phát hành

Khi Spring Security, browser, CDN hoặc gateway được nâng cấp, tái chạy nhóm test bị tác động. Với tính năng còn hạn chế, lên lịch kiểm tra lại định kỳ và khi có browser release note. Mỗi kết quả nên có commit/config version, browser binary version, URL môi trường và link trace đã lược bỏ dữ liệu nhạy cảm.

## 16. Chẩn đoán lỗi browser support thường gặp

| Triệu chứng | Khả năng cao | Cách kiểm chứng |
|---|---|---|
| Header hiển thị nhưng script vẫn chạy | CSP chỉ Report-Only, script được allow, directive chưa được hỗ trợ hoặc có nonce/hash hợp lệ | So sánh enforced CSP, policy nguồn, console và fixture script |
| CSP chỉ lỗi trên Safari | Directive/nguồn script khác, chính sách cookie/platform hoặc WebKit triển khai khác | Safari version thật, Web Inspector, response public và BCD entry |
| `frame-ancestors` không chặn iframe | Policy đặt trong meta, không có HTTP header hiệu lực, browser version cũ hoặc wrong response | Kiểm tra response iframe được tải và nguồn parent |
| HSTS thiếu ở browser | Chưa truy cập HTTPS hợp lệ, chưa học policy hoặc proxy không phát header | HTTPS response, profile state và proxy forwarding |
| CORS trả 200 nhưng Fetch thất bại | CORS headers không hợp lệ/duplicate, credentials mismatch, browser chặn cookie | Console, Network OPTIONS + actual, response headers và cookie jar |
| `Clear-Site-Data: "storage"` không xóa SPA | Response từ API khác origin, browser không hỗ trợ hoặc response thiếu secure context | Origin của response, BCD directive, browser storage trước/sau |
| Permissions Policy không chặn API | Directive/browser không hỗ trợ hoặc API/iframe chưa đáp ứng điều kiện fixture | BCD từng directive, JS thực nghiệm, permission prompt/OS policy |
| Cookie có trong `Set-Cookie` nhưng browser không gửi | `SameSite`/`Secure`/`Domain`/`Path`, third-party policy hoặc fetch credentials | Browser cookie store + network request thật |
| WebKit Playwright PASS nhưng iPhone FAIL | WebKit test khác Safari/iOS phát hành, browser/OS privacy và WebView behavior | Chạy thiết bị iOS thực với Safari version cụ thể |
| Scanner báo thiếu `X-XSS-Protection: 1` | Rule cũ không phản ánh deprecation | Đối chiếu MDN/OWASP, giữ `0` hoặc bỏ header theo policy, dùng CSP và output encoding |

Khi phân tích, **không kết luận dựa chỉ trên console warning**. Phải gắn warning với **header thực, browser version, đường đi request, ngữ cảnh test và hành vi được ghi nhận**. Cùng mã `403` có thể đến từ WAF, CSRF, authorization hoặc gateway; vì vậy log các tầng cần có request/trace ID.

## 17. Bài tập thực hành: chọn hỗ trợ thay vì đoán

**Bối cảnh:** một sản phẩm Spring Security phục vụ desktop Chrome/Edge/Firefox, Safari macOS, Safari iOS và Android WebView. Ứng dụng có SPA khác origin với API, đăng nhập session cookie, CSP cơ bản, iframe report ở portal nội bộ và logout phát `Clear-Site-Data: "cookies", "storage", "executionContexts"`. Nhóm phát triển muốn bổ sung `Permissions-Policy` và CSP Trusted Types.

**Yêu cầu:**

1. Thiết kế một bảng browser/version/device có đủ engine, OS, test environment và ngày xác minh.
2. Liệt kê tối thiểu **mười** kiểm thử quan sát được, bao gồm: CSP chặn inline script, nonce hợp lệ, clickjacking, HSTS đã học, CORS credentials, cookie SameSite, storage sau logout, đa tab, Permissions Policy và Trusted Types.
3. Xác định test nào có thể chạy bằng MockMvc/WebTestClient, test nào cần browser thật, test nào cần iOS/Android device.
4. Nếu `"executionContexts"` không được hỗ trợ trên một browser mục tiêu, giải thích cách bảo đảm phiên đã logout vẫn không được backend chấp nhận.
5. Nếu Playwright WebKit PASS nhưng Safari iOS FAIL, liệt kê chứng cứ cần thu trước khi sửa Spring Security.

**Gợi ý giải:**

- Tra MDN BCD theo **từng directive**, ghi support/partial/unsupported cho browser version mục tiêu; đừng suy từ tính năng mẹ.
- Dùng MockMvc/WebTestClient kiểm tra header writer, CSRF và invalidated session. Dùng Playwright chạy CSP, CORS, iframe, cookie và storage. Chạy Safari iOS, Android WebView **thật** cho các khác biệt liên quan hệ điều hành/host application.
- Khi thiếu `"executionContexts"`, frontend có thể đồng bộ trạng thái bằng `BroadcastChannel` hoặc `storage` event, nhưng **server phải hủy session hoặc thu hồi token**; browser thiếu directive không được trở thành bypass xác thực.
- Với iframe, chọn một hợp đồng nhất quán giữa `frame-ancestors` và `X-Frame-Options`. Nếu portal được phép embed, không gửi `DENY` mâu thuẫn với nhu cầu trên browser cần hỗ trợ.
- Với CSP Trusted Types và Permissions Policy, chỉ bật enforcement ở các feature/browser có test phù hợp; các browser không hỗ trợ vẫn phải có safe DOM sinks, sanitizer và server-side authorization.
- Khi có bug iOS, lưu response public, chính sách cookie, version Safari/iOS, hành vi iframe/redirect, console/browser inspection và request ID theo tầng. Điều chỉnh policy sau khi xác định nguyên nhân cụ thể.

## 18. Checklist áp dụng trước khi nâng cấp

| Câu hỏi | Tiêu chí đạt |
|---|---|
| Có danh sách browser thực sự được hỗ trợ? | Ghi brand, engine, version tối thiểu, OS, desktop/mobile/WebView và owner |
| Có nguồn tương thích đáng tin? | MDN/BCD và browser release notes được gắn link, ngày kiểm tra |
| Mỗi directive quan trọng có test hành vi? | CSP, frame, HSTS, CORS, cookie, logout được kiểm qua browser |
| Có phân biệt header hiện diện với enforcement? | MockMvc/WebTestClient và browser E2E là hai tầng riêng |
| Có test public URL qua CDN/gateway? | Security header, redirect và cache policy không bị thay sai |
| Có thử profile sạch và profile đang có state? | HSTS, cookie, cache, storage, logout hoạt động trong cả hai |
| Có thử thiết bị thật khi cần? | Safari iOS/WebView không chỉ được thay bằng viewport emulation |
| Browser không hỗ trợ có fallback không? | Authentication/authorization/CSRF và data handling vẫn an toàn |
| Có ghi nhận hỗ trợ một phần? | Báo cáo PASS/PARTIAL/FAIL/UNSUPPORTED/NOT_APPLICABLE |
| Có đường xử lý khi browser cập nhật? | Test liên quan chạy lại khi nâng browser/Spring/gateway, có trace và owner |

## Tài liệu tham khảo

- [MDN Browser Compatibility Data (BCD)](https://github.com/mdn/browser-compat-data) và [schema support statements](https://github.com/mdn/browser-compat-data/blob/main/schemas/compat-data-schema.md): cách đọc `version_added`, `version_removed`, ghi chú và hỗ trợ một phần.
- [MDN — HTTP headers](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers): trang tra cứu cú pháp và tương thích header.
- [MDN — Content Security Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP) và [frame-ancestors](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/frame-ancestors): CSP, script và chống clickjacking.
- [MDN — X-Frame-Options](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Frame-Options): chính sách nhúng frame và sự lỗi thời của `ALLOW-FROM`.
- [MDN — Strict-Transport-Security](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Strict-Transport-Security): cách browser học HSTS và preload.
- [MDN — CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS) và [CORS credentials error](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS/Errors/CORSNotSupportingCredentials): preflight, wildcard và credential.
- [MDN — Clear-Site-Data](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Clear-Site-Data) và [dữ liệu BCD của header](https://github.com/mdn/browser-compat-data/blob/main/http/headers/Clear-Site-Data.json): tương thích khác nhau giữa các directive.
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): thuộc tính cookie và các ràng buộc browser.
- [MDN — Permissions-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Permissions-Policy), [Cross-Origin-Embedder-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cross-Origin-Embedder-Policy) và [Trusted Types CSP directive](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/require-trusted-types-for): tính năng có mức hỗ trợ thay đổi.
- [MDN — X-XSS-Protection](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-XSS-Protection): cơ chế legacy đã deprecated.
- [Spring Security — Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/features/exploits/headers.html), [Servlet](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html), [Reactive](https://docs.spring.io/spring-security/reference/reactive/exploits/headers.html): mặc định và API cấu hình headers.
- [Playwright — Browsers](https://playwright.dev/docs/browsers) và [Projects](https://playwright.dev/docs/test-projects): đa engine, cấu hình projects và giới hạn WebKit/Firefox automation so với browser branded.

