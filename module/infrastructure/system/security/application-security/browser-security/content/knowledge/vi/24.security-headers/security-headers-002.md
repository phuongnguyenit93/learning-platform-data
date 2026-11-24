# Content-Security-Policy

> **Chương:** Security headers  
> **Chủ đề:** Content-Security-Policy  
> **Module:** SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly. Thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích Content-Security-Policy (CSP) kiểm soát tài nguyên và hành vi của document như thế nào.
2. Đọc và xây dựng policy theo directive, source expression và fallback.
3. Dùng nonce hoặc hash để cho phép script/style cần thiết mà không bật unsafe-inline.
4. Phân biệt script-src, connect-src, img-src, frame-src, frame-ancestors, base-uri và form-action.
5. Triển khai CSP theo giai đoạn Report-Only → sửa vi phạm → Enforce.
6. Đọc CSP violation report và xử lý các lỗi do cache, CDN, framework hoặc dependency.
7. Kết hợp CSP với output encoding, sanitization và Trusted Types để giảm rủi ro XSS.

## 1. CSP là gì và bảo vệ điều gì?

**Content-Security-Policy (CSP)** là một security policy do server gửi cho browser, thường qua HTTP response header. Browser áp dụng policy để quyết định tài nguyên nào document được tải, script nào được chạy, form được gửi tới đâu và document có thể bị nhúng trong frame từ origin nào.

Một policy cơ bản:

```http
Content-Security-Policy: default-src 'self'; object-src 'none'; base-uri 'self'
```

Policy trên dùng cùng origin làm nguồn mặc định cho nhiều loại tài nguyên, cấm plugin object và giới hạn URL cơ sở của document. Trong ứng dụng thực tế, nên khai báo rõ từng nhóm tài nguyên quan trọng thay vì dựa hoàn toàn vào default-src.

CSP giúp giảm khả năng khai thác XSS bằng cách giới hạn script có thể thực thi. Ví dụ, nếu kẻ tấn công chèn một thẻ script inline nhưng policy không cho phép inline script, browser có thể chặn script đó. CSP cũng có thể hạn chế nơi dữ liệu bị gửi tới hoặc ngăn trang bị nhúng bởi website khác.

Tuy nhiên, CSP là **lớp giảm thiểu tác động**, không phải cách thay thế việc sửa nguyên nhân XSS:

- CSP không làm dữ liệu đầu vào trở nên an toàn.
- CSP không tự encode HTML hoặc sanitize rich text.
- Một policy có unsafe-inline, nguồn script quá rộng hoặc JSONP/script endpoint không an toàn có thể mất phần lớn hiệu quả.
- Nếu attacker đã chạy được script trong origin, nhiều hành động vẫn có thể thực hiện thông qua quyền của trang.
- CSP không thay SameSite cookie, CSRF token, kiểm tra authorization hay các biện pháp bảo vệ server.

Mục tiêu triển khai là policy đủ chặt để hạn chế script không mong muốn nhưng vẫn cho phép những tài nguyên mà ứng dụng thực sự cần.

## 2. CSP được browser áp dụng như thế nào?

Server gửi header CSP trong response của document. Browser đọc policy trước khi xử lý nội dung trang và áp dụng các directive tương ứng trong suốt vòng đời document.

```http
HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8
Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-random-value'
```

Có hai cách phổ biến để gửi policy:

- `Content-Security-Policy`: policy được enforce. Hành vi vi phạm directive bị browser chặn theo quy tắc của CSP.
- `Content-Security-Policy-Report-Only`: browser ghi nhận và báo cáo vi phạm nhưng không chặn hành vi. Dùng để quan sát trước khi enforce.

Một response có thể gửi nhiều CSP header. Browser áp dụng đồng thời các policy; một policy bổ sung có thể làm giới hạn chặt hơn, không dùng header thứ hai để nới lỏng header thứ nhất.

### 2.1. Header và meta element

Ưu tiên HTTP response header:

```http
Content-Security-Policy: default-src 'self'; object-src 'none'
```

CSP cũng có thể được khai báo bằng meta element:

```html
<meta http-equiv="Content-Security-Policy"
      content="default-src 'self'; object-src 'none'">
```

Meta element có giới hạn: không hỗ trợ Report-Only; một số directive như frame-ancestors và sandbox không có hiệu lực qua meta; policy chỉ bắt đầu áp dụng sau khi browser gặp thẻ meta nên không bảo vệ phần nội dung đã được parse trước đó. Vì vậy, meta không thay thế response header cho policy bảo mật chính.

### 2.2. Nhiều policy cùng áp dụng

Giả sử server gửi:

```http
Content-Security-Policy: script-src 'self'
Content-Security-Policy: img-src 'self'
```

Browser áp dụng cả hai policy. Script phải thỏa policy thứ nhất và hình ảnh phải thỏa policy thứ hai. Đừng tách policy thành nhiều header với giả định header sau sẽ ghi đè header trước.

## 3. Cấu trúc một CSP policy

Một policy gồm các directive, phân cách bằng dấu chấm phẩy:

```http
Content-Security-Policy: default-src 'self'; script-src 'nonce-abc123'; img-src 'self' data:; object-src 'none'
```

Mỗi directive điều khiển một nhóm hành vi hoặc loại tài nguyên. Giá trị có thể là source expression như self, none, hostname, scheme, nonce hoặc hash.

### 3.1. Source expression thường gặp

| Source expression | Ý nghĩa |
|---|---|
| `'self'` | Origin của document hiện tại |
| `'none'` | Không cho phép nguồn nào trong directive đó |
| `https:` | Cho phép nguồn dùng HTTPS; phạm vi rất rộng |
| `https://cdn.example.test` | Cho phép origin cụ thể |
| `https://cdn.example.test/assets/` | Giới hạn theo host và path |
| `*.example.test` | Wildcard cho các subdomain phù hợp; không đồng nghĩa với domain gốc |
| `'nonce-<giá-trị>'` | Cho phép phần tử script/style có nonce khớp |
| `'sha256-<base64>'` | Cho phép nội dung inline có hash khớp |
| `'strict-dynamic'` | Mở rộng sự tin cậy từ script có nonce/hash sang script được nó nạp trong browser hỗ trợ |

Các keyword như self, none, unsafe-inline, unsafe-eval phải đặt trong dấu nháy đơn. Hostname và scheme không đặt trong dấu nháy.

Tránh dùng nguồn quá rộng như * , https: hoặc *.example.test nếu ứng dụng chỉ cần một vài endpoint. Một origin được allowlist có thể chứa script upload, JSONP, redirect hoặc endpoint do bên thứ ba kiểm soát; chỉ thêm domain sau khi hiểu nội dung và chức năng của nó.

### 3.2. default-src và fallback

`default-src` là fallback cho nhiều nhóm tài nguyên khi directive chuyên biệt tương ứng không được khai báo. Ví dụ:

```http
Content-Security-Policy: default-src 'self'
```

Nếu không có img-src, browser dùng default-src để quyết định nguồn ảnh. Nếu khai báo img-src, directive đó thay thế fallback cho ảnh.

Không phải mọi directive đều fallback về default-src. Những directive điều khiển chính sách riêng như base-uri, form-action, frame-ancestors và sandbox cần được khai báo rõ nếu ứng dụng cần bảo vệ chúng.

Một số directive chuyên biệt hơn:

- script-src-elem và script-src-attr lần lượt điều khiển script element và inline event handler; nếu không khai báo, chúng fallback theo script-src, rồi default-src.
- style-src-elem và style-src-attr tương tự cho style element và style attribute.
- worker-src có fallback riêng qua child-src, script-src, rồi default-src theo quy tắc CSP.

Khi debug, hãy xác định directive thực sự áp dụng cho sink thay vì chỉ nhìn default-src.

## 4. Những directive quan trọng

| Directive | Điều khiển | Ví dụ |
|---|---|---|
| default-src | Fallback nguồn cho nhiều loại tài nguyên | default-src 'self' |
| script-src | Nguồn script và các cách thực thi script | script-src 'self' |
| script-src-elem | Script element | script-src-elem 'self' |
| script-src-attr | Inline event handler | script-src-attr 'none' |
| style-src | Stylesheet và style inline theo fallback | style-src 'self' |
| img-src | Hình ảnh | img-src 'self' data: |
| font-src | Font | font-src 'self' https://fonts.example.test |
| connect-src | Fetch, XHR, WebSocket, EventSource, sendBeacon | connect-src 'self' https://api.example.test |
| media-src | Audio/video | media-src 'self' |
| object-src | Plugin object/embed | object-src 'none' |
| frame-src | Nguồn iframe mà trang hiện tại được phép tải | frame-src https://widget.example.test |
| frame-ancestors | Origin được phép nhúng trang hiện tại | frame-ancestors 'self' |
| base-uri | URL được dùng trong thẻ base | base-uri 'none' |
| form-action | Đích form submission | form-action 'self' |
| manifest-src | Web app manifest | manifest-src 'self' |
| worker-src | Worker, SharedWorker và ServiceWorker script URL | worker-src 'self' |
| upgrade-insecure-requests | Nâng request tài nguyên HTTP lên HTTPS | upgrade-insecure-requests |
| report-to | Reporting API endpoint group | report-to csp-endpoint |
| report-uri | Endpoint báo cáo CSP kiểu cũ | report-uri /csp-report |

### 4.1. script-src

`script-src` là directive trọng tâm khi giảm rủi ro XSS. Ví dụ:

```http
Content-Security-Policy: script-src 'self' https://static.example.test
```

Policy cho phép script từ cùng origin và host CDN cụ thể. Tuy vậy, nếu cùng origin có endpoint cho phép người dùng upload JavaScript hoặc có JSONP không an toàn, self vẫn có thể mở đường cho script injection.

Với ứng dụng hiện đại, ưu tiên nonce hoặc hash và tránh phụ thuộc hoàn toàn vào host allowlist. Không thêm unsafe-inline chỉ để làm cho một trang cũ chạy được; hãy xác định script inline nào hợp lệ rồi chuyển sang nonce/hash hoặc external file.

### 4.2. connect-src

`connect-src` kiểm soát những đích mà script có thể kết nối bằng Fetch/XHR, WebSocket, EventSource và sendBeacon. Ví dụ:

```http
Content-Security-Policy: connect-src 'self' https://api.example.test wss://socket.example.test
```

Nếu ứng dụng dùng API domain riêng, phải thêm đúng origin đó. Không thêm * chỉ để xử lý lỗi kết nối; kiểm tra URL thực tế trong Network và allowlist từng origin cần thiết.

### 4.3. frame-src và frame-ancestors

Hai directive này có hướng kiểm soát khác nhau:

- frame-src của parent giới hạn nguồn iframe mà parent được tải.
- frame-ancestors của document child giới hạn origin nào được phép nhúng document đó.

Ví dụ parent:

```http
Content-Security-Policy: frame-src https://widget.example.test
```

Ví dụ child:

```http
Content-Security-Policy: frame-ancestors https://app.example.test
```

frame-ancestors thay thế vai trò chống framing của X-Frame-Options trong các browser hỗ trợ CSP. Có thể dùng frame-ancestors 'none' để cấm nhúng hoặc 'self' để chỉ cho cùng origin nhúng. Directive này phải gửi qua HTTP header.

### 4.4. object-src, base-uri và form-action

Đây là các directive nhỏ nhưng thường có giá trị bảo vệ cao:

```http
Content-Security-Policy: object-src 'none'; base-uri 'none'; form-action 'self'
```

- object-src 'none' cấm plugin content qua object và embed.
- base-uri 'none' ngăn thẻ base bị chèn làm thay đổi cách phân giải URL tương đối.
- form-action 'self' giới hạn form gửi tới cùng origin; nếu sản phẩm có form hợp lệ gửi tới cổng thanh toán, thêm origin chính xác của cổng đó.

default-src 'none' không tự thay thế các directive này. Hãy khai báo chúng rõ ràng.

## 5. Nonce: cho phép script cụ thể theo từng response

Nonce là một giá trị ngẫu nhiên, khó đoán, được server tạo cho mỗi response. Server đặt cùng nonce trong CSP header và các script/style element hợp lệ.

Ví dụ header:

```http
Content-Security-Policy: script-src 'nonce-r4nd0mValue'; object-src 'none'; base-uri 'none'
```

Ví dụ HTML:

```html
<script nonce="r4nd0mValue">
  initializeApplication();
</script>
```

Browser cho phép script element có nonce khớp với giá trị trong policy. Một script inline được chèn mà không có nonce phù hợp sẽ bị chặn.

### 5.1. Yêu cầu đối với nonce

- Tạo bằng bộ sinh số ngẫu nhiên mật mã phía server, ví dụ 16–32 byte ngẫu nhiên rồi encode Base64.
- Tạo nonce mới cho mỗi response HTML; không dùng timestamp, counter, user ID hoặc chuỗi cố định.
- Chỉ gắn nonce vào các script/style element do ứng dụng kiểm soát.
- Không cho phép dữ liệu người dùng quyết định vị trí gắn nonce.
- Tránh cache HTML có nonce dùng chung giữa nhiều response hoặc nhiều người dùng.
- Không ghi nonce vào log/analytics nếu không có lý do vận hành rõ ràng.

Nonce không phải secret lâu dài; nó là token cho phép thực thi trong một response. Nếu attacker có thể đọc nonce của document và chèn markup tùy ý vào cùng document, CSP có thể bị vô hiệu hóa. Vì vậy vẫn phải sửa XSS và bảo vệ sink.

### 5.2. Cache và CDN

Nonce phải khớp giữa header và HTML. Nếu CDN cache header và body độc lập, hoặc ghép HTML từ nhiều fragment, nonce có thể không khớp hoặc bị tái sử dụng.

Các cách xử lý thường dùng:

- Render nonce tại edge/origin cho từng response và bảo đảm header/body được thay đồng bộ.
- Không cache shared HTML có nonce dùng chung; dùng cache policy phù hợp.
- Với nội dung script tĩnh, cân nhắc hash thay nonce nếu quy trình build/deploy kiểm soát được nội dung.
- Kiểm thử response sau CDN, reverse proxy và service worker, không chỉ response tại development server.

## 6. Hash: cho phép nội dung inline cố định

Hash phù hợp với inline script/style có nội dung ổn định. Server hoặc build pipeline tính SHA-256/SHA-384/SHA-512 từ nội dung inline theo quy tắc hash của CSP rồi khai báo trong policy.

Ví dụ:

```http
Content-Security-Policy: script-src 'sha256-BASE64_HASH_VALUE'
```

HTML:

```html
<script>
  initializeApplication();
</script>
```

Hash phải khớp nội dung chính xác. Thay đổi khoảng trắng, xuống dòng hoặc ký tự cũng làm hash khác.

### 6.1. Khi nào dùng nonce và khi nào dùng hash?

| Tiêu chí | Nonce | Hash |
|---|---|---|
| Nội dung script | Có thể thay đổi theo response | Phải ổn định |
| Cách cấp quyền | Gắn nonce vào element | Hash nội dung và đưa vào header |
| Phù hợp | SSR, script inline sinh theo request | Script inline tĩnh, build pipeline kiểm soát |
| Cache | Cần giữ header/body nonce đồng bộ | Dễ cache hơn nếu nội dung không đổi |
| Thay đổi nội dung | Không cần tính lại hash, nhưng cần nonce mới cho response | Phải cập nhật hash mỗi lần nội dung đổi |

Không dùng hash cho một đoạn script được render từ dữ liệu người dùng. Hash chỉ chứng minh nội dung khớp với một giá trị đã duyệt; nó không làm nội dung động trở nên an toàn.

### 6.2. Hash cho inline event handler

Mặc định, hash của script element không tự cho phép inline event handler như onclick. Có cơ chế unsafe-hashes trong CSP3 để áp dụng hash cho một số handler/style attribute, nhưng đây là lựa chọn chuyển tiếp cần đánh giá kỹ. Ưu tiên bỏ inline handler và dùng addEventListener.

## 7. strict-dynamic và chính sách script nghiêm ngặt

strict-dynamic cho phép browser CSP3 truyền sự tin cậy từ script được cho phép bằng nonce/hash sang các script mà nó nạp động. Ví dụ:

```http
Content-Security-Policy: script-src 'nonce-random-value' 'strict-dynamic'; object-src 'none'; base-uri 'none'
```

Với browser hỗ trợ CSP3, các host allowlist trong script-src có thể bị bỏ qua khi strict-dynamic cùng nonce/hash có hiệu lực. Điều này giúp giảm phụ thuộc vào danh sách domain rộng, nhưng đặt trách nhiệm lớn hơn lên script gốc được tin cậy.

Nếu script gốc nạp script dựa trên dữ liệu không tin cậy, attacker có thể lợi dụng loader đó. Vì vậy:

- Chỉ gắn nonce vào script loader do ứng dụng kiểm soát.
- Không nối URL người dùng vào script.src nếu chưa parse và allowlist.
- Kiểm tra mọi code path tải script động.
- Dùng CSP script-src cùng Trusted Types TrustedScriptURL khi phù hợp.
- Kiểm thử browser cũ không hỗ trợ strict-dynamic; các nguồn fallback cần được cấu hình có chủ đích.

## 8. Những keyword làm yếu CSP

| Keyword | Tác động | Khuyến nghị |
|---|---|---|
| unsafe-inline | Cho phép inline script/style theo phạm vi directive và có thể làm giảm mạnh bảo vệ XSS | Tránh; chuyển script sang nonce/hash hoặc file ngoài |
| unsafe-eval | Cho phép các API thực thi chuỗi như eval()/Function() trong phạm vi script policy | Loại bỏ nếu có thể; thay bằng logic không sinh code |
| wasm-unsafe-eval | Cho phép compile/instantiate WebAssembly từ nguồn text trong browser hỗ trợ | Chỉ bật nếu ứng dụng thực sự cần |
| unsafe-hashes | Cho phép hash được áp dụng cho inline event handler/style attribute trong trường hợp phù hợp | Chỉ cân nhắc như bước chuyển tiếp, ưu tiên bỏ handler |
| * hoặc https: | Cho phép nguồn rất rộng | Liệt kê origin/path cần thiết |

Không thêm các keyword này chỉ để làm mất lỗi Console. Hãy xác định chức năng nào cần chúng và liệu có thể refactor để bỏ đi hay không.

Trong browser hỗ trợ CSP3, nếu source list của directive có nonce-source hoặc hash-source, keyword unsafe-inline sẽ bị bỏ qua theo quy tắc CSP. Không nên dựa vào hành vi khác nhau giữa browser cũ và mới để dùng unsafe-inline làm fallback; hãy kiểm thử ma trận browser và giữ policy rõ ràng.

## 9. Report-Only và quy trình triển khai an toàn

Không nên bật một policy rất chặt trên production mà chưa biết ứng dụng thực sự tải gì. CSP có thể làm hỏng analytics, font, API, payment widget, script của editor hoặc luồng đăng nhập nếu thiếu nguồn hợp lệ.

Quy trình rollout:

1. **Inventory:** lập danh sách script, style, ảnh, font, API, iframe, form action và worker đang dùng.
2. **Baseline:** quan sát Network và Console trên các workflow quan trọng.
3. **Report-Only:** phát policy dự kiến qua Content-Security-Policy-Report-Only.
4. **Triage:** nhóm vi phạm theo directive, URL, route và browser; phân biệt tài nguyên hợp lệ với injection hoặc dependency không cần thiết.
5. **Refactor:** loại inline handler, eval, script loader động không an toàn và nguồn quá rộng.
6. **Enforce staging:** bật Content-Security-Policy trên staging, chạy test hồi quy.
7. **Canary production:** rollout cho một nhóm traffic hoặc route phù hợp, theo dõi lỗi và report.
8. **Enforce rộng:** chỉ mở rộng khi luồng quan trọng đã hoạt động và policy không có ngoại lệ rộng không cần thiết.

Report-Only không chặn hành vi vi phạm. Nó là công cụ quan sát, không phải lớp bảo vệ thay thế policy enforce.

## 10. CSP reporting

Có hai cơ chế báo cáo thường gặp:

- report-to dùng Reporting API và endpoint group được khai báo bằng HTTP response header Reporting-Endpoints.
- report-uri là cơ chế cũ hơn, vẫn hữu ích làm fallback trong một số browser.

Ví dụ:

```http
Reporting-Endpoints: csp-endpoint="https://reports.example.test/csp"
Content-Security-Policy-Report-Only: default-src 'self'; report-to csp-endpoint; report-uri /csp-report
```

Endpoint cần xử lý POST report an toàn:

- Giới hạn kích thước body và tốc độ nhận.
- Không phản chiếu report vào HTML hoặc dùng nội dung report làm lệnh.
- Không tin các field trong report như input xác thực.
- Lọc hoặc loại bỏ query string/token/định danh nhạy cảm trước khi lưu.
- Chống spam và giới hạn thời gian lưu trữ.
- Theo dõi tỷ lệ report theo route, directive, browser và phiên bản ứng dụng.

Report có thể chứa URL, line number, blocked URI hoặc dữ liệu từ môi trường browser. Không mặc định rằng report luôn sạch, đầy đủ hoặc không chứa dữ liệu nhạy cảm.

## 11. CSP và các cơ chế bảo vệ liên quan

CSP phát huy hiệu quả tốt nhất khi kết hợp với các lớp bảo vệ khác:

| Cơ chế | Vai trò | Quan hệ với CSP |
|---|---|---|
| Output encoding | Giữ dữ liệu ở đúng HTML/attribute/URL/JS context | Sửa nguyên nhân injection; CSP giảm khả năng script độc hại chạy |
| HTML sanitization | Giữ lại markup rich text theo allowlist | Dùng khi sản phẩm cần cho phép HTML; CSP không thay sanitizer |
| Trusted Types | Kiểm soát chuỗi đi vào DOM injection sink | Có thể bật qua CSP require-trusted-types-for 'script' |
| SameSite cookie/CSRF token | Giảm request giả mạo có credential | CSP không thay CSRF defense |
| frame-ancestors | Giới hạn website được phép nhúng document | Bảo vệ framing/clickjacking ở phía document được nhúng |
| CORS | Kiểm soát quyền đọc response cross-origin qua script | CORS không phải CSP và không quyết định script nào được tải |
| SRI | Kiểm tra integrity của tài nguyên script/style bên ngoài | CSP giới hạn nguồn; SRI kiểm tra nội dung tài nguyên cụ thể |

Một policy CSP nghiêm ngặt không làm cho innerHTML trở thành API an toàn. Nếu dữ liệu không tin cậy đi vào DOM, vẫn cần dùng textContent, sanitizer phù hợp hoặc Trusted Types policy đã được kiểm thử.

## 12. Mẫu policy tham khảo

Một ứng dụng web có SSR, API riêng và một widget bên ngoài có thể bắt đầu từ mẫu sau, sau đó điều chỉnh theo tài nguyên thực tế:

```http
Content-Security-Policy:
  default-src 'none';
  base-uri 'none';
  object-src 'none';
  script-src 'nonce-<NONCE_PER_RESPONSE>' 'strict-dynamic';
  script-src-attr 'none';
  style-src 'self' 'nonce-<NONCE_PER_RESPONSE>';
  img-src 'self' data:;
  font-src 'self';
  connect-src 'self' https://api.example.test;
  frame-src https://widget.example.test;
  frame-ancestors 'none';
  form-action 'self';
  upgrade-insecure-requests;
  report-to csp-endpoint;
  report-uri /csp-report
```

Đây là điểm bắt đầu để review, không phải policy có thể sao chép nguyên trạng cho mọi ứng dụng:

- Thay placeholder nonce bằng giá trị ngẫu nhiên được server tạo cho response hiện tại; cùng nonce phải xuất hiện trong script/style element hợp lệ.
- Chỉ giữ data: trong img-src nếu ứng dụng thực sự hiển thị ảnh data URL.
- Thay frame-ancestors 'none' nếu sản phẩm cần được nhúng; chỉ liệt kê origin parent đã xác minh.
- Thêm nguồn font, API, worker hoặc media đúng nhu cầu.
- strict-dynamic cần kiểm thử browser mục tiêu và script loader; nếu không có loader đáng tin, không thêm chỉ vì đây là keyword mới.
- upgrade-insecure-requests hữu ích khi ứng dụng đã sẵn sàng phục vụ tài nguyên HTTPS; nó không thay việc sửa URL HTTP trong dữ liệu hoặc cấu hình.

Không dùng một policy chung cho mọi route nếu các route có nhu cầu tài nguyên khác nhau. Có thể dùng policy theo nhóm ứng dụng, nhưng phải bảo đảm không có route nhạy cảm nhận policy yếu hơn ngoài dự kiến.

## 13. Thực hành: lab CSP với Node.js

Lab dùng Node.js built-in, không cần package ngoài. Server tạo nonce ngẫu nhiên cho mỗi response và cung cấp hai chế độ:

- `mode=report`: gửi `Content-Security-Policy-Report-Only`; inline handler vi phạm được báo cáo nhưng vẫn chạy.
- `mode=enforce`: gửi `Content-Security-Policy`; inline handler không có nonce/hash bị browser chặn.

Trang có một script hợp lệ mang nonce và một nút có inline event handler để kiểm tra khác biệt giữa hai chế độ.

### Bước 1 — Tạo file `csp-lab.cjs`

```js
const http = require('node:http');
const crypto = require('node:crypto');

function renderPage(nonce, mode) {
  return [
    '<!doctype html>',
    '<html lang="vi"><head><meta charset="utf-8">',
    '<meta name="viewport" content="width=device-width, initial-scale=1">',
    '<title>CSP lab</title></head><body>',
    '<h1>Content-Security-Policy lab</h1>',
    '<p id="mode">Mode: ' + mode + '</p>',
    '<p id="result">Chưa chạy handler</p>',
    '<button id="safe" type="button">Handler bằng addEventListener</button>',
    '<button id="inline" type="button"',
    ' onclick="document.getElementById(&quot;result&quot;).textContent=&quot;inline handler ran&quot;">',
    'Thử inline handler</button>',
    '<script nonce="' + nonce + '">',
    "document.querySelector('#safe').addEventListener('click', () => {",
    "  document.querySelector('#result').textContent = 'nonce script ran';",
    '});',
    '</script>',
    '</body></html>',
  ].join('\n');
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost:3000');

  if (req.method === 'POST' && url.pathname === '/csp-report') {
    let bytes = 0;
    let tooLarge = false;
    req.on('data', (chunk) => {
      bytes += chunk.length;
      if (bytes > 16384) tooLarge = true;
    });
    req.on('end', () => {
      if (tooLarge) {
        res.writeHead(413);
        return res.end();
      }
      // Lab chỉ log metadata, không ghi nguyên report body.
      console.log('CSP report received; bytes=' + bytes);
      res.writeHead(204);
      res.end();
    });
    return;
  }

  if (url.pathname !== '/') {
    res.writeHead(404);
    return res.end('Not found');
  }

  const mode = url.searchParams.get('mode') === 'enforce'
    ? 'enforce' : 'report';
  const nonce = crypto.randomBytes(18).toString('base64');
  const policy = [
    "default-src 'none'",
    "base-uri 'none'",
    "object-src 'none'",
    "script-src 'nonce-" + nonce + "'",
    "style-src 'self'",
    "img-src 'self' data:",
    "connect-src 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "report-to csp-endpoint",
    "report-uri /csp-report",
  ].join('; ');

  const headers = {
    'Content-Type': 'text/html; charset=utf-8',
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff',
    'Reporting-Endpoints': 'csp-endpoint="http://localhost:3000/csp-report"',
  };

  if (mode === 'enforce') {
    headers['Content-Security-Policy'] = policy;
  } else {
    headers['Content-Security-Policy-Report-Only'] = policy;
  }

  res.writeHead(200, headers);
  res.end(renderPage(nonce, mode));
});

server.listen(3000, 'localhost', () => {
  console.log('Report-Only: http://localhost:3000/?mode=report');
  console.log('Enforce:     http://localhost:3000/?mode=enforce');
});
```

### Bước 2 — Chạy lab

```sh
node csp-lab.cjs
```

Mở browser tại `http://localhost:3000/?mode=report`. Bật DevTools → Console và Network.

### Bước 3 — Kiểm tra Report-Only

1. Nhấn nút **Handler bằng addEventListener**. Nội dung phải đổi thành `nonce script ran`.
2. Nhấn nút **Thử inline handler**. Trong Report-Only, handler có thể chạy và nội dung đổi thành `inline handler ran`.
3. Mở Console để tìm CSP violation liên quan inline event handler.
4. Quan sát Network hoặc terminal để kiểm tra report được gửi tới `/csp-report` nếu browser hỗ trợ reporting path đang cấu hình.

Report-Only ghi nhận vi phạm nhưng không chặn, vì vậy inline handler chạy là hành vi dự kiến trong bước quan sát.

### Bước 4 — Kiểm tra Enforce

Mở `http://localhost:3000/?mode=enforce` và tải lại trang:

1. Nhấn **Handler bằng addEventListener**. Script có nonce phải chạy bình thường.
2. Nhấn **Thử inline handler**. Browser phải chặn event handler không có nonce/hash; nội dung vẫn là `Chưa chạy handler` nếu chưa nhấn nút an toàn.
3. Mở Console và xác minh CSP violation.
4. Mở Network → document response và kiểm tra `Content-Security-Policy` đang được gửi.

Nếu inline handler vẫn chạy, xác minh bạn đang mở đúng URL enforce, response không bị cache và browser thực sự nhận header enforce.

### Bước 5 — Thử sửa policy có kiểm soát

Trong môi trường lab, thử lần lượt:

- Xóa nonce khỏi script hợp lệ: script phải bị chặn.
- Thêm một script element inline không nonce: script phải bị chặn.
- Thêm `img-src 'none'` rồi thử tải ảnh: ảnh không được tải.
- Thay `frame-ancestors 'none'` bằng origin cụ thể trong response header: chỉ origin đó được phép nhúng document.
- Xóa `form-action 'self'` khỏi policy rồi so sánh hành vi form theo policy mặc định; sau đó khai báo lại directive rõ ràng.

Mỗi lần thay đổi chỉ nên kiểm tra một directive để xác định chính xác tác động.

## 14. Chẩn đoán lỗi CSP

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Script hợp lệ bị chặn | Thiếu nonce/hash hoặc source không nằm trong policy | Kiểm tra response header và script element thực tế |
| Script inline chạy dù đã có CSP | Policy có unsafe-inline, header không được gửi hoặc chỉ dùng Report-Only | Kiểm tra Network response và directive script-src |
| Event handler bị chặn | Inline onclick/onload không được cho phép | Dùng addEventListener |
| API call bị chặn | Thiếu origin trong connect-src | Xác minh endpoint trong Network rồi allowlist origin cụ thể |
| Ảnh/font không hiển thị | Thiếu img-src hoặc font-src | Thêm đúng nguồn cần thiết |
| Iframe không tải | Parent frame-src chặn hoặc child frame-ancestors từ chối parent | Kiểm tra header ở cả hai response |
| Form không gửi được | form-action không cho phép đích | Thêm origin đích hợp lệ |
| Nonce không khớp | CDN cache header/body riêng hoặc fragment dùng nonce khác | Tạo nonce theo response và đồng bộ header/body |
| Report-Only có nhiều vi phạm | Policy chưa khớp baseline hoặc có code path cũ | Nhóm theo route/directive, phân loại trước khi enforce |
| CSP chặn script bên thứ ba | Host không được allowlist hoặc strict-dynamic thay đổi cách đánh giá nguồn | Xác minh script có thật sự cần, kiểm tra loader và fallback browser |

### 14.1. Phân biệt vi phạm thật và nhiễu

Một CSP report không tự động chứng minh có tấn công. Vi phạm có thể đến từ:

- Code ứng dụng chưa migrate.
- Thư viện hoặc tag manager hợp lệ nhưng dùng inline script.
- Extension của browser hoặc tooling trong môi trường kiểm thử.
- Tài nguyên không còn được dùng nhưng vẫn có code cố tải.
- Payload tấn công thật sự.

Không allowlist mọi URL xuất hiện trong report. Trước tiên xác minh route, initiator, source code, owner của dependency và nhu cầu sản phẩm. Report từ browser cũng có thể thiếu thông tin hoặc bị giả mạo ở endpoint nhận báo cáo.

## 15. Checklist triển khai CSP

Trước khi bật enforce, xác minh:

- [ ] Đã kiểm kê script, style, image, font, API, worker, iframe và form action.
- [ ] Đã khai báo object-src 'none' và base-uri 'none' nếu ứng dụng không cần ngoại lệ.
- [ ] Đã khai báo frame-ancestors theo chính sách embedding.
- [ ] script-src không dựa vào unsafe-inline hoặc unsafe-eval nếu không có lý do được duyệt.
- [ ] Script inline hợp lệ dùng nonce ngẫu nhiên theo response hoặc hash nội dung cố định.
- [ ] Nonce header và HTML khớp, không bị tái sử dụng do cache.
- [ ] connect-src, img-src, font-src, frame-src và form-action chỉ chứa nguồn cần thiết.
- [ ] Đã thử Report-Only trên các workflow quan trọng.
- [ ] Đã phân loại report và sửa vi phạm do code/dependency.
- [ ] Enforce đã được kiểm thử trên staging và browser mục tiêu.
- [ ] Reporting endpoint giới hạn kích thước, tốc độ và không lưu dữ liệu nhạy cảm.
- [ ] CSP được gửi qua HTTP response header.
- [ ] Output encoding, sanitization và Trusted Types vẫn được áp dụng tại sink tương ứng.

## 16. Câu hỏi tự kiểm tra

**1.** CSP được browser nhận chủ yếu qua đâu?  
**Trả lời:** Qua HTTP response header Content-Security-Policy; meta element có giới hạn và không thay thế header chính.

**2.** Content-Security-Policy-Report-Only khác Content-Security-Policy thế nào?  
**Trả lời:** Report-Only ghi nhận vi phạm nhưng không chặn; header thường enforce policy.

**3.** default-src 'self' có thay thế base-uri và form-action không?  
**Trả lời:** Không. Đây là các directive cần khai báo riêng.

**4.** Nonce phải được tạo và sử dụng thế nào?  
**Trả lời:** Sinh bằng CSPRNG phía server cho từng response, đặt cùng giá trị trong header và script/style element được tin cậy, không tái sử dụng qua cache.

**5.** Khi nào hash phù hợp hơn nonce?  
**Trả lời:** Khi nội dung inline cố định và build/deploy pipeline có thể tính, cập nhật hash chính xác mỗi lần nội dung thay đổi.

**6.** frame-src khác frame-ancestors ở đâu?  
**Trả lời:** frame-src kiểm soát frame mà trang hiện tại tải; frame-ancestors kiểm soát ai được phép nhúng trang hiện tại.

**7.** Vì sao unsafe-inline làm CSP yếu đi?  
**Trả lời:** Nó cho phép inline script/style trong phạm vi directive, làm giảm khả năng chặn payload XSS dựa trên inline code.

**8.** connect-src kiểm soát những kết nối nào?  
**Trả lời:** Fetch/XHR, WebSocket, EventSource và sendBeacon cùng các kết nối script tương tự.

**9.** CSP có thay output encoding và Trusted Types không?  
**Trả lời:** Không. CSP hạn chế hành vi browser; output encoding và Trusted Types kiểm soát dữ liệu đi vào context/sink nguy hiểm.

**10.** Vì sao không nên thêm mọi domain xuất hiện trong CSP report vào allowlist?  
**Trả lời:** Report có thể đến từ dependency không cần thiết, extension, code cũ hoặc tấn công. Phải xác minh nhu cầu và nguồn trước khi tin cậy.

## Tổng kết

CSP là lớp kiểm soát ở browser giúp giới hạn script, tài nguyên, kết nối và quyền nhúng của document. Policy cần khai báo directive theo nhu cầu thực tế, ưu tiên nonce/hash cho script inline, giới hạn nguồn rõ ràng và tránh keyword làm yếu như unsafe-inline hoặc unsafe-eval. Triển khai qua Report-Only để tìm vi phạm, sửa code và dependency, rồi bật Enforce sau khi kiểm thử workflow. CSP không thay output encoding, sanitizer, Trusted Types hay CSRF defense; hiệu quả của nó phụ thuộc vào policy chặt và cách ứng dụng quản lý script được tin cậy.
