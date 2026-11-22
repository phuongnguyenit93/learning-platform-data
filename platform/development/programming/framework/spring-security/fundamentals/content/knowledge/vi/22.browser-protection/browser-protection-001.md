# Security headers và phạm vi giảm thiểu rủi ro

## 1. Security headers là gì và vì sao không thể chỉ dựa vào HTTPS?

Một ứng dụng có thể đã dùng **HTTPS**, xác thực bằng Spring Security, phân quyền endpoint và kiểm tra CSRF, nhưng trình duyệt vẫn cần biết phải xử lý **nội dung phản hồi** như thế nào. Chẳng hạn:
- Trang có được đưa vào **iframe** của website khác không?
- File có được diễn giải thành JavaScript dù server khai báo MIME type khác không?
- Script, style, ảnh hoặc kết nối đến **origin** nào được phép?
- Browser có được gửi **Referer** chứa đường dẫn trang trước đó sang một site khác không?
- Trang có được sử dụng camera, microphone hoặc geolocation không?
- Tài liệu nhạy cảm có được lưu trong cache của browser không?
- Trình duyệt có cần ép các lượt kết nối tương lai đến domain dùng HTTPS không?

Những quyết định này có thể được truyền tới trình duyệt bằng **HTTP response security headers**. Ví dụ:

~~~http
HTTP/1.1 200 OK
Content-Type: text/html; charset=UTF-8
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Content-Security-Policy: default-src 'self'; object-src 'none'; frame-ancestors 'none'
Referrer-Policy: no-referrer
Permissions-Policy: camera=(), microphone=(), geolocation=()
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
~~~

Đây là **ví dụ minh họa cho một response**, không phải danh sách header có sẵn trong mọi ứng dụng. Một số header được Spring Security bổ sung mặc định; một số cần chủ động cấu hình; một số chỉ có tác dụng trong những điều kiện nhất định.

**Nguyên tắc quan trọng:** security headers là **lớp giảm thiểu rủi ro và defense-in-depth**, không phải cơ chế chữa mọi lỗ hổng. Một header tốt không thay thế Authentication, Authorization, CSRF protection, output encoding, input validation, quản lý dependency, kiểm tra quyền với từng bản ghi hoặc cấu hình TLS.

### Mục tiêu học tập

Sau bài này, bạn có thể:
1. Giải thích **security headers là response headers** và vai trò của browser.
2. Phân biệt chính xác **header mặc định của Spring Security 6.x** và **header cần bật thêm**.
3. Nêu rủi ro mà từng header giảm thiểu cùng những rủi ro **nó không giải quyết**.
4. Thiết kế Content-Security-Policy (CSP) tương thích với HTML, JavaScript và các dịch vụ thực tế.
5. Hiểu HSTS, clickjacking, MIME sniffing, cache, Referrer-Policy, Permissions-Policy và các isolation headers.
6. Chạy ví dụ Spring Boot 3.x / Spring Security 6.x / Java 17+ thêm CSP và kiểm tra header qua curl/MockMvc.
7. Phân biệt security headers với cookie flags, CORS, CSRF và xác thực Bearer.
8. Rà soát reverse proxy/CDN, redirect, lỗi 401/403/500, static resources và chính sách trình duyệt.

> Phạm vi kỹ thuật: ví dụ dùng **Spring MVC/Servlet** và API cấu hình Spring Security **6.x**. Spring WebFlux dùng SecurityWebFilterChain và ServerHttpSecurity, không sao chép nguyên HttpSecurity của Servlet.

## 2. Ai phát header và ai thực thi?

Một HTTP response có thể đi qua nhiều thành phần:

~~~text
Browser
   ^
   | HTTP response + security headers
   |
Reverse proxy / CDN / API gateway
   ^
   | Response từ Spring Boot
   |
Spring Security FilterChainProxy / HeaderWriterFilter
   ^
   | Security headers được thêm/chỉnh theo cấu hình
   |
Spring MVC Controller / static resource / error handler
~~~

**Spring Security** có thể ghi các header liên quan vào response. **Reverse proxy hoặc CDN** có thể bổ sung, sửa, xóa hay ghi đè những header đó. **Browser** quyết định cách áp dụng: chặn iframe, áp CSP, không sniff MIME, không gửi Referrer theo policy hoặc chuyển HTTP thành HTTPS theo HSTS.

Do đó, cần kiểm tra response **thực sự tới browser**, không chỉ đọc code Java:
- Header có được gửi ở **HTML, CSS/JS, API và response lỗi** cần thiết không?
- Header có đúng trên **HTTPS** sau reverse proxy không?
- Có header bị viết hai lần với policy mâu thuẫn không?
- Header có được áp dụng bởi browser mục tiêu không?
- CSP có gây lỗi thực tế cho script/style hợp lệ không?

Không phải mọi HTTP client đều hiểu hoặc thực thi mọi security header. **curl** có thể hiển thị header nhưng không thực thi CSP hay cấm iframe. Vì vậy kiểm thử nên kết hợp HTTP-level assertions và browser DevTools/E2E.

### 2.1. Response header khác request header

Trong ví dụ, browser gửi:

~~~http
GET / HTTP/1.1
Host: app.example.com
Accept: text/html
Cookie: JSESSIONID=...
~~~

Server trả:

~~~http
HTTP/1.1 200 OK
Content-Security-Policy: default-src 'self'; script-src 'self'
X-Frame-Options: DENY
~~~

**Content-Security-Policy và X-Frame-Options là response headers.** Chúng không phải credential, cũng không phải request header để client tự khai “tôi an toàn”. Một attacker gửi header tên X-Frame-Options trong request không làm server tự tin request đó được xác thực.

## 3. Những header mặc định của Spring Security 6.x

Spring Security cung cấp mặc định một tập security response headers cho **response đi qua Spring Security filter chain**. Theo tài liệu Spring Security 6.x, danh sách thường có:

~~~http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
X-Content-Type-Options: nosniff
Strict-Transport-Security: max-age=31536000 ; includeSubDomains
X-Frame-Options: DENY
X-XSS-Protection: 0
~~~

**Ngoại lệ quan trọng:** Spring Security chỉ ghi **Strict-Transport-Security** cho **request được nhận diện là HTTPS/secure**, không viết HSTS như trên cho mọi response HTTP ở localhost. Dấu cách/định dạng thực tế của giá trị header có thể khác một chút giữa version/server, nên test ý nghĩa cấu hình thay vì so sánh một string không liên quan.

Bảng tóm tắt:

| Header mặc định | Mục tiêu giảm thiểu | Điều không thể suy ra |
| --- | --- | --- |
| Cache-Control, Pragma, Expires | Hạn chế cache các phản hồi nhạy cảm | Không thể coi là biện pháp xóa dữ liệu khỏi mọi thiết bị/cache đã có |
| X-Content-Type-Options: nosniff | Giảm rủi ro browser đoán sai MIME, nhất là script/style | Không tự sửa Content-Type sai hoặc chống mọi XSS |
| Strict-Transport-Security | Giúp browser nhớ phải dùng HTTPS cho host sau khi nhận chính sách hợp lệ | Không tự cài TLS hoặc loại mọi rủi ro ở kết nối HTTP ban đầu |
| X-Frame-Options: DENY | Ngăn trang bị nhúng trong frame theo cơ chế browser hỗ trợ | Không ngăn mọi clickjacking nếu các luồng khác còn lỗi |
| X-XSS-Protection: 0 | Tắt XSS filter cũ không còn được tin cậy trên browser hiện đại | **Không phải bật bộ lọc chống XSS** |

**Không có mặc định:** Spring Security không tự quyết định một **CSP** phù hợp cho tất cả website; **Referrer-Policy** và **Permissions-Policy** cũng cần cấu hình khi ứng dụng muốn dùng. Các chính sách này phụ thuộc cấu trúc trang, script/CDN, tính năng và threat model cụ thể.

### 3.1. Đừng vô hiệu mọi header để sửa một tính năng

Fragment sau là **anti-pattern**, không nên đưa vào production chỉ để làm một trang hiển thị được:

~~~java
http.headers(headers -> headers.disable());
~~~

Lệnh này tắt **toàn bộ** phần header writers của Spring Security trong chain tương ứng. Khi một header riêng cần thay đổi, hãy cấu hình **header đó** hoặc một nhóm URL cụ thể; không cần bỏ tất cả phòng vệ mặc định.

### 3.2. permitAll khác web.ignoring

Đối với static assets công khai:

~~~java
.requestMatchers("/assets/**").permitAll()
~~~

thường thích hợp hơn loại hẳn **/assets/** khỏi Spring Security bằng **web.ignoring()**. Với **permitAll**, request vẫn đi qua filter chain, do đó security headers của chain vẫn có thể được áp dụng. Với ignoring, Spring Security filter chain không chạy trên URL đó, nên **HeaderWriterFilter không thể tự bổ sung header cho response bị bỏ qua**.

Nếu dùng CDN/static hosting ngoài Spring Boot, phải chủ động cấu hình các security headers tương ứng tại nơi thật sự phục vụ nội dung. Không giả định Java config ảnh hưởng đến response của CDN độc lập.

## 4. Cache-Control: tránh lưu lại dữ liệu nhạy cảm

Các response chứa thông tin sau thường không nên bị browser/shared cache giữ lại:
- Trang tài khoản, sao kê, thông tin liên hệ cá nhân.
- API chứa dữ liệu người dùng, báo cáo nội bộ, quyền quản trị.
- Response có thông tin nhạy cảm theo session.
- Nội dung mà người đã logout không nên dễ dàng xem lại bằng một cơ chế cache.

Spring Security dùng các header cache-control mặc định:

~~~http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
~~~

**no-store** là chỉ thị yêu cầu cache không lưu response; **no-cache** nghĩa là không dùng lại nội dung chưa revalidate, **không có nghĩa “không lưu”**. Header Pragma và Expires thường giúp tương thích với client/cache cũ. Phạm vi tuân thủ còn tùy browser, proxy, cache và phiên bản phần mềm.

### 4.1. Header không thay thế logout và xóa dữ liệu

Cache-Control không bảo đảm dữ liệu đã tải xuống trước đó sẽ bị xóa khỏi:
- Bộ nhớ đang mở của browser tab.
- File người dùng đã download/screenshot.
- LocalStorage hoặc IndexedDB do ứng dụng tự ghi.
- Bộ nhớ/ổ đĩa hoặc bản backup của bên thứ ba.
- Các cache hoặc service worker ứng dụng tự quản lý không tuân theo giả định đơn giản.

Để logout đúng, vẫn phải làm mất hiệu lực session/token khi phù hợp, xóa dữ liệu client theo thiết kế và kiểm thử không có dữ liệu nhạy cảm bị giữ ngoài ý muốn.

### 4.2. Static CSS/JS thường cần cache khác với HTML nhạy cảm

Cache-Control mặc định của Spring Security tương đối thận trọng. Nhưng một bundle JavaScript có tên chứa hash nội dung, ví dụ **app.a1b2c3.js**, có thể được cache lâu để tăng hiệu năng.

Có thể thiết kế:
- **HTML có dữ liệu cá nhân:** cache-control no-store.
- **API nhạy cảm:** no-store.
- **CSS/JS đã version hóa:** cache dài hoặc immutable nếu nguồn phát và quy trình deploy thích hợp.
- **Ảnh công khai:** cache theo nhu cầu, không dùng chính sách như tệp private.

Spring MVC resource handlers, reverse proxy hoặc CDN có thể đặt cache policy cho asset. **Đừng tắt global cache-control của Spring Security chỉ vì muốn cache vài file CSS.** Với đường dẫn có dữ liệu riêng tư, ưu tiên chính sách thận trọng.

## 5. X-Content-Type-Options: nosniff

Header:

~~~http
X-Content-Type-Options: nosniff
~~~

giúp giảm rủi ro **MIME sniffing**: browser không nên tự đoán hoặc diễn giải một số tài nguyên, đặc biệt script và stylesheet, trái với MIME type server đã khai báo.

Ví dụ rủi ro: một file upload chứa nội dung có thể bị diễn giải như JavaScript nếu được phục vụ với loại nội dung không chính xác và browser sniff. Việc ép browser dựa vào MIME type giúp giảm kiểu tấn công này.

### Những điều cần hiểu đúng

- **nosniff không tự đặt Content-Type đúng**. Backend vẫn phải trả **text/javascript** (hoặc MIME JavaScript phù hợp) cho script, **text/css** cho stylesheet, **application/json** cho API JSON…
- Browser có thể chặn load script/style nếu MIME không phù hợp, khiến UI trông “hỏng” sau khi bật header. Cách sửa đúng là **sửa Content-Type**, không phải tùy tiện tắt nosniff.
- Header này không bảo vệ mọi trường hợp upload nguy hiểm. Upload cần **kiểm tra loại file**, nơi lưu, quyền truy cập, cách đặt Content-Disposition, domain riêng khi cần và chống thực thi nội dung không tin cậy.
- Không dùng file upload do user kiểm soát như một script cùng origin có quyền đầy đủ.

### X-Content-Type-Options khác Content-Type

~~~http
Content-Type: text/css
X-Content-Type-Options: nosniff
~~~

**Content-Type** nói tài nguyên thuộc loại gì; **nosniff** yêu cầu browser hạn chế tự suy diễn khác khai báo. Hai header bổ sung nhau.

## 6. X-Frame-Options và clickjacking

**Clickjacking** là việc một trang không đáng tin cố đặt giao diện thật của ứng dụng mục tiêu vào iframe/layer rồi đánh lừa người dùng bấm vào nút hoặc thao tác không chủ ý. Browser có thể vẫn gửi cookie phiên cho ứng dụng bị nhúng theo điều kiện cookie policy, khiến hành động nguy hiểm hơn.

Spring Security mặc định thường gửi:

~~~http
X-Frame-Options: DENY
~~~

Một số lựa chọn:
- **DENY:** không cho trang được nhúng trong frame, kể cả bởi cùng origin.
- **SAMEORIGIN:** cho phép frame theo điều kiện cùng origin của cơ chế header.
- **ALLOW-FROM:** cú pháp cũ, không được các browser hiện đại hỗ trợ đáng tin cậy; không nên chọn làm giải pháp allowlist origin hiện đại.

**Nếu app có nhu cầu nhúng một trang vào iframe hợp lệ**, không mở toàn bộ hệ thống chỉ để hỗ trợ một trang:
1. Xác định **trang con nào được nhúng** và **origin nào được phép nhúng**.
2. Cân nhắc dùng CSP directive **frame-ancestors** trên response của trang được nhúng.
3. Điều chỉnh X-Frame-Options tương thích với thiết kế; không để default DENY và policy nhúng hợp lệ mâu thuẫn trong browser đang triển khai.
4. Kiểm thử clickjacking, các path nhạy cảm và support browser.

### 6.1. CSP frame-ancestors thường linh hoạt hơn

Ví dụ:

~~~http
Content-Security-Policy: frame-ancestors 'self' https://portal.example.org
~~~

Directive này khai báo **những origin nào được phép nhúng response hiện tại**. Nó **không** đồng nghĩa với **frame-src**, là directive kiểm soát **những frame mà trang hiện tại được phép tải**. Hai hướng kiểm soát khác nhau.

Đối với trang không bao giờ cần nhúng:

~~~http
Content-Security-Policy: frame-ancestors 'none'
X-Frame-Options: DENY
~~~

Cặp header này giúp bảo vệ trong các môi trường browser hỗ trợ tương ứng. Không được suy ra rằng clickjacking đã được loại bỏ khỏi tất cả UI tương tác nếu ứng dụng còn các rủi ro về quyền, CSRF, UX hoặc browser đặc thù.

**Lưu ý kỹ thuật:** CSP **frame-ancestors** được áp dụng qua response header; không thể mong đặt directive đó trong thẻ HTML meta để tạo hiệu quả tương đương.

## 7. HSTS: buộc các lần kết nối tiếp theo dùng HTTPS

**HTTP Strict Transport Security (HSTS)** cho browser biết rằng một host phải được truy cập bằng HTTPS trong một khoảng thời gian.

Ví dụ:

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

Ý nghĩa:
- **max-age=31536000:** browser ghi nhớ chính sách trong khoảng một năm.
- **includeSubDomains:** áp dụng phạm vi cả các subdomain tương ứng.
- **preload:** dấu hiệu hỗ trợ quy trình đăng ký HSTS preload list, không đồng nghĩa chỉ cần thêm chữ preload là browser tự đưa domain vào danh sách preload.

### 7.1. Spring Security chỉ thêm HSTS khi request được coi là HTTPS

HSTS chỉ có hiệu lực từ response được nhận **qua kết nối HTTPS đáng tin cậy**. Theo mặc định, Spring Security không gửi HSTS khi xử lý request HTTP thường ở localhost.

~~~text
Browser --HTTP--> Server
    Không thể coi một HSTS header trong HTTP là chính sách đáng tin

Browser --HTTPS--> Server
    Server có thể gửi HSTS
    Browser nhớ chính sách cho các lần truy cập sau
~~~

Vì vậy, thử:

~~~bash
curl -i http://localhost:8080/
~~~

và không thấy **Strict-Transport-Security** là **bình thường** trong demo dùng HTTP. Đây không phải bằng chứng HSTS đã bị tắt.

### 7.2. HSTS không thay thế TLS và redirect HTTPS

HSTS **không tự cài đặt HTTPS/TLS**, không tạo chứng chỉ, không chặn mọi lỗi cấu hình proxy. Bạn vẫn cần:
- Cấp chứng chỉ TLS hợp lệ và bảo trì quy trình gia hạn.
- Chuyển hướng HTTP sang HTTPS theo chính sách.
- Bảo vệ traffic giữa proxy và backend phù hợp.
- Hạn chế nội dung hỗn hợp (mixed content).
- Tránh phát cookie hoặc credential qua HTTP.
- Kiểm tra ứng dụng trên HTTPS thực.

Nếu browser chưa từng nhận chính sách HSTS hợp lệ và domain chưa có trong preload list, **lần HTTP đầu tiên** vẫn có thể là bề mặt rủi ro trước khi redirect. HSTS preload có thể giảm trường hợp này, nhưng là quyết định dài hạn có điều kiện và quy trình đăng ký riêng.

### 7.3. Nguy cơ từ includeSubDomains và preload

Không bật **includeSubDomains** hoặc **preload** chỉ vì công cụ chấm điểm khuyến khích:
- Cần bảo đảm **mọi subdomain thuộc phạm vi** đều hỗ trợ HTTPS, kể cả host cũ, dịch vụ nội bộ hoặc subdomain ít dùng.
- Sai cấu hình HSTS có max-age lớn có thể khiến browser không truy cập được một host chỉ hỗ trợ HTTP cho đến khi chính sách hết hạn hoặc được xử lý đúng cách.
- Preload ảnh hưởng rộng và khó đảo ngược ngay; cần kiểm tra điều kiện và ownership toàn bộ DNS/HTTPS.
- Nên rollout thận trọng theo giai đoạn thay vì áp chính sách một năm trên hạ tầng chưa được kiểm toán.

### 7.4. Reverse proxy có thể làm sai request.isSecure()

Kiến trúc phổ biến:

~~~text
Browser -- HTTPS --> Load Balancer / Reverse Proxy
                            |
                            | HTTP nội bộ
                            v
                      Spring Boot
~~~

Nếu Spring Boot không nhận diện đúng **scheme gốc HTTPS** qua thông tin proxy đã được tin cậy, Spring Security có thể cho rằng request là HTTP và **không thêm HSTS**, dù browser truy cập HTTPS.

Spring Boot có thể được cấu hình hỗ trợ forwarded headers, ví dụ thuộc tính **server.forward-headers-strategy** theo môi trường. Phải bảo đảm proxy **loại bỏ/ghi đè forwarded headers không đáng tin từ Internet**, thay vì để client tự giả mạo X-Forwarded-Proto.

**Kiểm header ở cổng công khai sau proxy**, không chỉ HTTP localhost nội bộ. HSTS cũng có thể được thêm ở edge; hãy quyết định thành phần nào là owner để tránh policy trùng hoặc không nhất quán.

## 8. Content Security Policy (CSP): lớp giảm thiểu content injection

**Content-Security-Policy** là một trong những header chủ động mạnh nhất để giảm tác hại của **XSS/content injection** và kiểm soát nguồn tải tài nguyên của trang.

Ví dụ:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
~~~

Mục tiêu là thông báo cho browser:
- Script chỉ lấy từ origin của trang theo policy.
- CSS chỉ lấy từ origin của trang.
- Không tải nội dung bằng object/embed kiểu cũ.
- Hạn chế tài nguyên mặc định khác.
- Không cho trang bị nhúng trong frame.

**Spring Security không tự sinh CSP mặc định**, vì policy phù hợp phụ thuộc chính xác cách trang sử dụng JS/CSS, hình ảnh, CDN, API và các third-party integrations.

### 8.1. CSP không phải bộ lọc sửa nội dung XSS

CSP là **defense-in-depth**, không phải cách duy nhất để ngăn injection:
- Vẫn phải **escape HTML, JavaScript, URL, CSS theo đúng output context**.
- Không render HTML do user kiểm soát mà không sanitize/encode.
- Tránh DOM XSS như đưa dữ liệu không tin vào **innerHTML**, **eval** hoặc dynamic script execution.
- Dùng template engine/framework có cơ chế escaping an toàn và review các API bypass.
- Không dùng CSP để thay authorization hoặc CSRF.

Nếu attacker tìm được một cách script execution vẫn nằm trong policy được phép (ví dụ qua một nguồn script tin cậy có thể bị lạm dụng), CSP vẫn có thể bị vượt qua. Chính sách có **'unsafe-inline'** hoặc **'unsafe-eval'** thường làm suy yếu mục tiêu giảm XSS.

### 8.2. Những directive thường gặp

| Directive | Kiểm soát | Lưu ý thực tế |
| --- | --- | --- |
| **default-src** | Fallback cho nhiều fetch directives chưa khai báo | Không kiểm soát được mọi nhóm chỉ bằng một directive |
| **script-src** | Nguồn script và một số kiểu thực thi script | Ưu tiên external script được kiểm soát, nonce/hash khi cần |
| **style-src** | Nguồn stylesheet/style | CSS inline có thể bị chặn; cần thiết kế policy theo UI |
| **img-src** | Nguồn hình ảnh | Cân nhắc data: nếu ứng dụng thực sự cần |
| **connect-src** | URL mà fetch/XHR/WebSocket/EventSource… của trang được phép kết nối | **Không thay CORS của server đích** |
| **font-src** | Nguồn web font | CDN fonts có thể cần origin cụ thể |
| **object-src** | Plugin/object/embed | Với phần lớn trang hiện đại, dùng **'none'** |
| **base-uri** | Giới hạn HTML base URL | Giảm rủi ro redirect tài nguyên qua base tag không tin cậy |
| **form-action** | Đích được phép submit form | Hữu ích cho đăng nhập/đăng ký/thanh toán |
| **frame-ancestors** | Origin được phép nhúng trang hiện tại | Khác frame-src; không có fallback từ default-src |
| **frame-src** | Frame mà trang hiện tại được phép nhúng | Không dùng nó thay frame-ancestors |
| **upgrade-insecure-requests** | Gợi ý nâng các URL HTTP tài nguyên thành HTTPS | Cần thử với hạ tầng hỗ trợ HTTPS |

**'self'** liên quan origin của trang chứ không phải “cùng công ty” hoặc “mọi subdomain”. **'none'** chặn mọi nguồn trong directive đó. Một policy quá lỏng với wildcard cũng có thể còn nhiều đường injection; một policy quá chặt có thể làm giao diện ngừng hoạt động.

### 8.3. CSP nên xuất hiện trên HTML document

CSP trả trong response HTML là chính sách mà browser dùng để giới hạn việc tải/thực thi của **tài liệu HTML đó**. Một header CSP trên API JSON response **không tự khóa script đang chạy trong document ở origin khác**.

Với trang chính của SPA, cần xem policy do **HTML entrypoint** thực sự nhận được từ CDN/server, kể cả khi API JSON được trả bởi Spring Boot khác origin.

### 8.4. Các hạn chế với inline script, inline style

Xét HTML:

~~~html
<button onclick="save()">Lưu</button>
<script>
  function save() { console.log("saved"); }
</script>
~~~

Dưới policy:

~~~text
script-src 'self'
~~~

browser hiện đại sẽ chặn nhiều dạng script inline và event handler inline ở trên. Đây là **hành vi bảo vệ có chủ đích**, không nhất thiết là lỗi Spring Security.

Thay bằng external script và DOM API:

~~~html
<button id="save">Lưu</button>
<script src="/assets/app.js" defer></script>
~~~

~~~javascript
document.getElementById("save")
    .addEventListener("click", function () {
        console.log("saved");
    });
~~~

Một số framework yêu cầu inline bootstrap hoặc dynamic styles. Khi đó, thiết kế **nonce hoặc hash** theo request/policy và cơ chế render, thay vì mặc định thêm **'unsafe-inline'** cho toàn bộ trang.

**Nonce phải đủ entropy và thay đổi theo response cần bảo vệ**, không phải một string cố định hard-coded trong source. Token CSP nonce **khác CSRF token**; không dùng một giá trị thay cho cả hai cơ chế.

### 8.5. Thử CSP bằng Report-Only trước khi enforce

Trong quá trình rollout:

~~~http
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; object-src 'none'
~~~

Browser có thể **ghi nhận/report vi phạm nhưng không áp chặn theo policy report-only**. Sau khi xem log/DevTools, cập nhật nguồn tài nguyên hợp lệ, loại unsafe-inline và kiểm thử đầy đủ, chuyển sang:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'
~~~

**Report-Only và enforce là hai response headers khác nhau.** Chỉ set Report-Only không có nghĩa browser đã chặn script nguy hiểm. Khi thu thập violation reports, cần hạn chế dữ liệu nhạy cảm và lượng log; report có thể bị nhiễu, không phải lúc nào cũng đầy đủ hoặc là bằng chứng tấn công thành công.

### 8.6. CSP cần được kiểm thử cùng sản phẩm

Các thành phần dễ bị ảnh hưởng:
- CDN script/style, web fonts, image proxies.
- Inline code được SSR hoặc template engine sinh.
- Tool analytics, tag manager, payment widget và chat support.
- WebSocket/API URL ngoài origin qua connect-src.
- WASM và code evaluation tùy công nghệ.
- iframe tích hợp và payment provider.
- Dev tooling/hot reload ở môi trường development.

Không copy policy của ứng dụng khác vào production rồi chấm pass chỉ vì response có header. **Chính sách phải được rút ra từ asset graph và tập origin thật**, đồng thời thu hẹp các quyền không cần thiết.

## 9. Referrer-Policy: giảm rò rỉ thông tin trong Referer

Browser có thể gửi request header **Referer** cho biết trang trước đó khi điều hướng hoặc tải tài nguyên. URL của trang trước đôi khi chứa thông tin nhạy cảm ở path/query, ví dụ một mã truy cập thiết kế kém.

Response header:

~~~http
Referrer-Policy: no-referrer
~~~

có thể yêu cầu browser không gửi Referer cho các request liên quan theo policy đó.

Các lựa chọn phổ biến:
- **no-referrer:** không gửi Referer.
- **same-origin:** chỉ gửi Referer khi đích cùng origin theo quy định.
- **strict-origin-when-cross-origin:** thường gửi URL đầy đủ trong trường hợp cùng origin, giảm xuống origin cho cross-origin an toàn và không tiết lộ qua một số đường downgrade.
- **origin:** gửi origin thay vì URL đầy đủ theo ngữ cảnh.

Chọn chính sách tùy yêu cầu analytics, referral, sản phẩm và mức nhạy cảm. **Spring Security không tự thêm Referrer-Policy theo mặc định**, cần thiết lập nếu ứng dụng muốn chính sách cụ thể.

**Giới hạn:** header không xóa dữ liệu đã lộ trước đó, không loại rò rỉ thông tin từ URL được trực tiếp gửi đi và không đảm bảo mọi client đều tuân thủ. Thiết kế an toàn hơn vẫn là **không nhét access token, session ID hay bí mật vào URL query/path**.

### Referrer-Policy không phải CORS

CORS quyết định khả năng đọc cross-origin response từ browser script. Referrer-Policy quyết định thông tin nguồn điều hướng/request được tiết lộ trong Referer. Hai mục tiêu và vùng ảnh hưởng khác nhau.

## 10. Permissions-Policy: kiểm soát quyền sử dụng browser features

Response header:

~~~http
Permissions-Policy: camera=(), microphone=(), geolocation=()
~~~

có thể giới hạn việc một document và một số embedded contexts được sử dụng những browser features như camera, microphone và geolocation, theo chính sách và mức hỗ trợ của browser.

Ý nghĩa của **()** trong ví dụ là không cho các origin sử dụng feature tương ứng trong phạm vi policy. Có thể dùng danh sách origin được phép cho các trường hợp cụ thể.

**Header này không thay thế sự đồng ý của người dùng**: ngay cả khi feature được policy cho phép, browser vẫn có thể yêu cầu quyền user và áp các điều kiện khác. Ngược lại, nếu policy chặn feature, việc user đã từng bấm Allow không tự khiến trang vượt qua restriction.

Spring Security 6.x có DSL hỗ trợ **permissionsPolicy(...)**, nhưng **không tự biết ứng dụng cần camera/microphone/geolocation nào**, nên ứng dụng phải chọn chính sách. Browser support có thể khác nhau giữa các directive; kiểm thử trên những browser mục tiêu.

## 11. Cross-Origin-Opener/Embedder/Resource Policy (COOP/COEP/CORP)

Ngoài nhóm header cơ bản, có những header phục vụ **cross-origin isolation** và hạn chế cách các resource được nhúng hoặc chia sẻ:

| Header | Mục tiêu chính | Rủi ro khi áp dụng đại trà |
| --- | --- | --- |
| **Cross-Origin-Opener-Policy (COOP)** | Kiểm soát quan hệ browsing context của trang với tài liệu khác origin, giảm một số rủi ro tương tác window/opener | Có thể ảnh hưởng login popup, payment popup, tích hợp bên ngoài |
| **Cross-Origin-Embedder-Policy (COEP)** | Yêu cầu điều kiện nhúng resource từ origin khác theo policy như require-corp/credentialless | Có thể làm hỏng tài nguyên bên thứ ba chưa gửi CORS/CORP phù hợp |
| **Cross-Origin-Resource-Policy (CORP)** | Cho phép resource producer giới hạn việc nhúng resource theo ngữ cảnh cross-origin/cross-site với một số request | Có thể chặn CDN/tài nguyên đang chia sẻ hợp lệ |

Một số ví dụ minh họa header:

~~~http
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
Cross-Origin-Resource-Policy: same-origin
~~~

**Không coi bộ ba trên là mặc định phải bật cho mọi site.** Cross-origin isolation có thể cần khi dùng API browser đặc biệt, nhưng yêu cầu phối hợp toàn bộ tài nguyên và luồng popup/frame. Nếu hệ thống cần OIDC popup hoặc widget của bên thứ ba, COOP/COEP không tương thích có thể làm hỏng chức năng.

Các header này **khác CORS**: CORS là cơ chế browser cho script đọc cross-origin response khi server cho phép; CORP/COEP/COOP có thêm những ràng buộc đối với cách tài nguyên và browsing contexts tương tác. Spring Security có hỗ trợ các cấu hình tương ứng, nhưng chỉ bật theo threat model và compatibility testing.

## 12. Các header không phải giải pháp hiện đại được khuyến nghị

### 12.1. X-XSS-Protection: 0 không có nghĩa bật “chống XSS”

Header mặc định:

~~~http
X-XSS-Protection: 0
~~~

thể hiện việc **vô hiệu hóa một bộ lọc XSS cũ** trên browser còn hỗ trợ nó. Các bộ lọc kiểu này đã bị loại bỏ hoặc deprecated ở nhiều browser và có thể gây vấn đề bảo mật/ngữ nghĩa khi cố bật lại.

Cách xử lý XSS hiện đại là:
- Output encoding đúng ngữ cảnh.
- Loại bỏ HTML/JavaScript injection và DOM XSS sinks.
- CSP chặt khi tương thích.
- Sanitization khi thật sự cần render nội dung user-supplied.
- Giảm phụ thuộc script bên ngoài và cập nhật thư viện.

Không dùng **X-XSS-Protection: 1** như lời khẳng định bảo vệ XSS tốt hơn policy mặc định.

### 12.2. HPKP (HTTP Public Key Pinning) không nên triển khai mới

HPKP từng cho phép ghim public key ở browser, nhưng bị browser bỏ hỗ trợ và có nguy cơ gây mất khả năng truy cập site nếu quản lý khóa sai. Spring Security 6.x vẫn có các tài liệu/API lịch sử liên quan, nhưng **không nên dùng HPKP làm tiêu chuẩn hardening mới**.

Với HTTPS, ưu tiên quản lý chứng chỉ, HSTS phù hợp, Certificate Transparency/bảo vệ hạ tầng khi cần và quy trình key rotation được kiểm soát.

### 12.3. X-Frame-Options và CSP không thể sửa backend authorization

Cấm iframe không ngăn người dùng có session cố ý gửi request POST trái quyền; CSP mạnh không khiến API báo cáo tự hiểu role. Authentication và Authorization vẫn được quyết định bởi backend/security policy. Đây là ranh giới quan trọng khi đánh giá hiệu quả security headers.

## 13. Spring Boot 3.x + Spring Security 6.x: demo hoàn chỉnh

Demo có:
- **GET /**: trang HTML, tải CSS/JS từ chính origin.
- **GET /assets/site.css** và **GET /assets/app.js**: static resources được phép.
- **GET /api/public**: API JSON công khai.
- **GET /api/private**: yêu cầu HTTP Basic với tài khoản thử nghiệm.
- Security headers mặc định của Spring Security.
- **CSP do ứng dụng chủ động cấu hình**, không cho inline scripts, không cho frame.
- **Referrer-Policy: no-referrer**.
- **Permissions-Policy** chặn camera/microphone/geolocation.

Chúng ta chủ động **không bật COOP/COEP/CORP đại trà** vì không có nhu cầu cross-origin isolation trong demo. Không đổi HSTS mặc định: trên localhost HTTP, HSTS không được phát.

### 13.1. Tạo dự án

Dùng Spring Initializr:
- **Java 17+**, **Spring Boot 3.x**, **Gradle**.
- Group **com.example**, artifact **demo**, package **com.example.demo**.
- Dependencies **Spring Web** và **Spring Security**.

Tạo các file:

~~~text
src/main/java/com/example/demo/SecurityHeadersDemoApplication.java
src/main/resources/static/assets/site.css
src/main/resources/static/assets/app.js
~~~

Sử dụng file Gradle wrapper và dependencies do Spring Initializr sinh. Nếu khởi tạo artifact bằng tên khác, đảm bảo **package** và **đường dẫn file** trong code trùng nhau.

### 13.2. Toàn bộ Java backend

Đặt toàn bộ code dưới đây vào **src/main/java/com/example/demo/SecurityHeadersDemoApplication.java**:

~~~java
package com.example.demo;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.header.writers.ReferrerPolicyHeaderWriter.ReferrerPolicy;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SecurityHeadersDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityHeadersDemoApplication.class, args);
    }
}

@Configuration
@EnableWebSecurity
class SecurityHeadersConfiguration {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                        "/", "/assets/**", "/api/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/private")
                    .authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .headers(headers -> headers
                // Giữ header defaults, chỉ bổ sung policy theo app.
                .contentSecurityPolicy(csp -> csp
                    .policyDirectives(
                        "default-src 'self'; " +
                        "script-src 'self'; " +
                        "style-src 'self'; " +
                        "img-src 'self'; " +
                        "connect-src 'self'; " +
                        "object-src 'none'; " +
                        "base-uri 'self'; " +
                        "form-action 'self'; " +
                        "frame-ancestors 'none'"))
                .referrerPolicy(referrer -> referrer
                    .policy(ReferrerPolicy.NO_REFERRER))
                .permissionsPolicy(permissions -> permissions
                    .policy("camera=(), microphone=(), " +
                            "geolocation=()")))
            .build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password("{noop}demo123")
                .roles("USER")
                .build());
    }
}

@RestController
class DemoController {

    @GetMapping(value = "/", produces = MediaType.TEXT_HTML_VALUE)
    String page() {
        return """
            <!doctype html>
            <html lang="vi">
            <head>
              <meta charset="UTF-8">
              <meta name="viewport"
                    content="width=device-width, initial-scale=1">
              <title>Security Headers Demo</title>
              <link rel="stylesheet" href="/assets/site.css">
              <script defer src="/assets/app.js"></script>
            </head>
            <body>
              <main>
                <h1>Security headers đang được áp dụng</h1>
                <p>JavaScript và CSS tải từ cùng origin.</p>
                <button id="load">Đọc API công khai</button>
                <pre id="result">Nhấn nút để tải dữ liệu.</pre>
              </main>
            </body>
            </html>
            """;
    }

    @GetMapping("/api/public")
    Map<String, String> publicData() {
        return Map.of("message", "public-data");
    }

    @GetMapping("/api/private")
    Map<String, String> privateData(Authentication auth) {
        return Map.of(
            "username", auth.getName(),
            "message", "authenticated-data");
    }
}
~~~

**Giải thích code:**

1. Class public **SecurityHeadersDemoApplication** khớp tên file; hai class còn lại là package-private trong cùng package được Spring component scan.
2. **@EnableWebSecurity** và SecurityFilterChain bật Spring Security Servlet. Endpoint public **permitAll** vẫn đi qua filter chain; endpoint private cần xác thực.
3. **httpBasic** chỉ dùng chứng minh server vẫn kiểm tra danh tính bên cạnh security headers; **{noop}demo123** chỉ dành cho học cục bộ, tuyệt đối không dùng để lưu mật khẩu production.
4. **headers(...)** không dùng **defaultsDisabled()** hay **disable()**, vì vậy các header mặc định vẫn được giữ và các chính sách mới được bổ sung.
5. **CSP** chỉ cho phép JS/CSS/ảnh và kết nối cùng origin; external JS/CSS trong demo phù hợp policy. Không có inline event handler hay inline script.
6. **X-Frame-Options: DENY** mặc định và **frame-ancestors 'none'** đều chống nhúng trang. Không bật nhúng từ bên thứ ba.
7. **ReferrerPolicy.NO_REFERRER** yêu cầu browser không tiết lộ Referer theo policy.
8. **Permissions-Policy** giới hạn ba feature không cần cho demo.
9. **HSTS** vẫn được quản lý theo mặc định và chỉ xuất hiện nếu request được đánh dấu HTTPS/secure; local HTTP 8080 không có HSTS.
10. Không tắt **CSRF** vì không cần tạo POST/PUT/DELETE nghiệp vụ. Nếu thêm các request thay đổi trạng thái, phải thiết kế CSRF theo credential/browser threat model.

### 13.3. CSS trong static/assets/site.css

Tạo file **src/main/resources/static/assets/site.css**:

~~~css
body {
    margin: 0;
    padding: 32px;
    background: #f4f6fa;
    color: #263244;
    font-family: Arial, sans-serif;
}
main {
    background: white;
    padding: 24px;
    max-width: 560px;
    margin: auto;
    border-radius: 12px;
    box-shadow: 0 4px 18px rgba(0,0,0,0.08);
}
button {
    padding: 10px 16px;
    cursor: pointer;
}
pre {
    white-space: pre-wrap;
    background: #eef1f5;
    padding: 12px;
}
~~~

Với Spring Boot MVC static serving mặc định, đường dẫn file **static/assets/site.css** được phục vụ tại URL **/assets/site.css** (không thêm /static vào URL).

### 13.4. JavaScript trong static/assets/app.js

Tạo file **src/main/resources/static/assets/app.js**:

~~~javascript
"use strict";

const button = document.getElementById("load");
const result = document.getElementById("result");

button.addEventListener("click", async function () {
    try {
        const response = await fetch("/api/public");
        if (!response.ok) {
            throw new Error("HTTP " + response.status);
        }
        const data = await response.json();
        result.textContent = data.message;
    } catch (error) {
        result.textContent = "Lỗi: " + error.message;
    }
});
~~~

**textContent** giúp hiển thị text mà không phân tích dữ liệu API như HTML. Điều này phù hợp nguyên tắc chống DOM XSS; đừng đổi thành **innerHTML** chỉ để tiện chèn nội dung không tin cậy.

Không có inline JavaScript nên CSP **script-src 'self'** vẫn cho phép tải file app.js. Nếu thay script bằng inline JS, DevTools có thể báo CSP violation.

### 13.5. Chạy ứng dụng

Trong thư mục gốc project Gradle:

~~~bash
./gradlew bootRun
~~~

Trên Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Mặc định có thể truy cập **http://localhost:8080** nếu không đổi server.port.

Mở browser ở **http://localhost:8080**:
1. Trang HTML hiển thị.
2. CSS được tải từ /assets/site.css.
3. JS được tải từ /assets/app.js.
4. Nhấn nút **Đọc API công khai**: script fetch tới /api/public và hiển thị **public-data**.
5. Mở DevTools > Network > chọn request document **/**, kiểm tra tab **Response Headers**.
6. Mở DevTools > Console, kiểm tra không có CSP violation từ code mẫu.

**Đây là hành vi dự kiến từ source code**, không phải kết quả đã chạy ứng dụng trong môi trường của bạn.

## 14. Kiểm thử security headers bằng curl

### 14.1. Kiểm header trên trang HTML

~~~bash
curl -i http://localhost:8080/
~~~

Theo config, response **HTTP 200** và thường có:
- **X-Content-Type-Options: nosniff**.
- **X-Frame-Options: DENY**.
- **X-XSS-Protection: 0**.
- **Cache-Control** chứa **no-store**.
- **Content-Security-Policy** chứa **script-src 'self'** và **frame-ancestors 'none'**.
- **Referrer-Policy: no-referrer**.
- **Permissions-Policy** có **camera=(), microphone=(), geolocation=()**.
- Không có **Strict-Transport-Security** trên HTTP localhost theo behavior mặc định.

Dù có nhiều header, curl sẽ vẫn in HTML. **curl không thực thi CSP hoặc chống nhúng iframe**; chỉ browser mới áp những rule tương ứng.

### 14.2. Kiểm static assets được bảo vệ bằng header

~~~bash
curl -i http://localhost:8080/assets/app.js
curl -i http://localhost:8080/assets/site.css
~~~

Dự kiến cả hai trả **200**. Vì đường /assets/** dùng **permitAll** thay vì ignoring, Spring Security header writers vẫn chạy. Với cấu hình này, response asset có thể có security headers tương tự, dù tác dụng của từng header phụ thuộc tài nguyên/bối cảnh. Cần bảo đảm Content-Type của JS/CSS đúng để không bị **nosniff** chặn khi browser tải.

### 14.3. CORS/authorization không thể thay bằng headers

~~~bash
# Chưa xác thực:
curl -i http://localhost:8080/api/private

# Có Basic credentials demo:
curl -i -u reader:demo123 \
  http://localhost:8080/api/private
~~~

Kỳ vọng:
- Không có credentials: **HTTP 401**, endpoint không công khai dữ liệu.
- Có credentials hợp lệ: **HTTP 200**, JSON chứa username reader.

Đây là kiểm tra **Authentication**, độc lập với CSP/XFO/nosniff. Việc response 401 có header không có nghĩa người chưa đăng nhập được quyền gọi API.

### 14.4. HSTS phải được thử đúng môi trường HTTPS

Để kiểm HSTS thật, cần deploy qua **HTTPS có chứng chỉ tin cậy** rồi:

~~~bash
curl -I https://your-real-test-host.example/
~~~

URL trên là **địa chỉ mẫu phải thay bằng host kiểm thử thật**, không phải một site hoạt động sẵn. Đừng dùng **curl -k** để tuyên bố triển khai TLS an toàn, vì -k bỏ xác minh certificate. Khi dùng HEAD, cần lưu ý server/gateway có thể xử lý khác GET; có thể dùng **curl -i** cho GET nếu cần chắc chắn.

HSTS chỉ được browser ghi nhớ sau khi nhận response HTTPS hợp lệ, hoặc từ preload list. Nếu ở sau proxy, xác nhận request public HTTPS được backend/gateway nhận đúng scheme và policy có ở response cuối.

### 14.5. CSP Report-Only không giống CSP enforce

Nếu muốn triển khai theo giai đoạn, có thể cấu hình chỉ report:

~~~java
.headers(headers -> headers
    .contentSecurityPolicy(csp -> csp
        .policyDirectives(
            "default-src 'self'; script-src 'self'; object-src 'none'")
        .reportOnly()))
~~~

Đây là **fragment cấu hình** thay thế phần CSP enforce tương ứng, không phải chương trình độc lập. Với reportOnly, response dùng **Content-Security-Policy-Report-Only**; nếu chưa có CSP enforce khác thì browser không chặn nguồn chỉ vi phạm policy report-only này.

Khi đã khắc phục hết vi phạm hợp lệ, chuyển sang policy enforce và xác minh lại. Không coi dashboard có vài violation reports là bằng chứng không có XSS.

## 15. Kiểm thử tự động bằng Spring Security Test + MockMvc

Viết test cho **header hiện diện**, **header được cấu hình đúng**, **behavior theo HTTP/HTTPS** và **authorization vẫn hoạt động**.

Thêm dependencies trong **build.gradle** nếu chưa có:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Đây là fragment Gradle Groovy DSL; Spring Initializr thường đã thêm starter-test, nên tránh khai báo trùng.

Tạo file **src/test/java/com/example/demo/SecurityHeadersDemoApplicationTest.java**:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityHeadersDemoApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicPageKeepsDefaultsAndAddsSelectedHeaders()
            throws Exception {
        mvc.perform(get("/"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "X-Content-Type-Options", "nosniff"))
            .andExpect(header().string(
                "X-Frame-Options", "DENY"))
            .andExpect(header().string(
                "X-XSS-Protection", "0"))
            .andExpect(header().string(
                "Cache-Control", containsString("no-store")))
            .andExpect(header().string(
                "Content-Security-Policy",
                containsString("script-src 'self'")))
            .andExpect(header().string(
                "Referrer-Policy", "no-referrer"))
            .andExpect(header().string(
                "Permissions-Policy",
                containsString("geolocation=()")));
    }

    @Test
    void httpRequestDoesNotReceiveHstsByDefault()
            throws Exception {
        mvc.perform(get("/"))
            .andExpect(status().isOk())
            .andExpect(header().doesNotExist(
                "Strict-Transport-Security"));
    }

    @Test
    void simulatedHttpsRequestReceivesHsts()
            throws Exception {
        mvc.perform(get("/").secure(true))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Strict-Transport-Security",
                containsString("max-age=31536000")));
    }

    @Test
    void anonymousIsStillDeniedPrivateApi()
            throws Exception {
        mvc.perform(get("/api/private"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                "X-Frame-Options", "DENY"));
    }

    @Test
    void validHttpBasicAuthenticatesPrivateApi()
            throws Exception {
        mvc.perform(get("/api/private")
                .with(httpBasic("reader", "demo123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("reader"));
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Windows:

~~~powershell
.\gradlew.bat test
~~~

**Vì sao test HSTS dùng .secure(true)?** MockMvc không tạo kết nối TLS thật; **secure(true)** mô phỏng request được Servlet coi là secure, giúp kiểm header writer. Test này **không thay thế** kiểm chứng hạ tầng HTTPS, certificate và forwarded headers sau load balancer.

**Vì sao chỉ test header chưa đủ?** MockMvc có thể khẳng định CSP string đúng, nhưng không chạy browser để thử script inline bị chặn, iframe clickjacking hay permission prompts. Cần thêm browser DevTools/Playwright/Selenium test khi product phụ thuộc các hành vi đó.

### 15.1. Bảng expected results của demo

| Kiểm thử | Kết quả dự kiến | Ý nghĩa |
| --- | --- | --- |
| GET / trên HTTP | 200 + CSP, nosniff, DENY | Header config được áp dụng |
| GET / trên HTTP | Không có HSTS | Phù hợp quy tắc HTTPS-only |
| GET / với MockMvc secure(true) | HSTS có max-age | Header writer phản ứng với secure request |
| GET /assets/app.js | 200 + Content-Type script phù hợp | Asset đi qua chain và không bị nosniff chặn |
| GET /api/private thiếu credentials | 401 | Headers không thay thế Authentication |
| GET /api/private với Basic hợp lệ | 200 | Authentication policy hoạt động |
| Mở trang trên browser | JS/CSS cùng origin chạy, inline script bị chặn nếu thử thêm | CSP có tác dụng tại browser |
| Nhúng / vào iframe website khác | Browser được kỳ vọng chặn | XFO/CSP frame-ancestors giảm clickjacking |

Các trạng thái trên là **kỳ vọng theo cấu hình ví dụ**, không phải log Gradle hay browser được thu thập trong tài liệu này.

## 16. Khi nào header không xuất hiện hoặc không có tác dụng?

### 16.1. Response không đi qua Spring Security filter chain

Nếu một URL bị **web.ignoring**, static host riêng, gateway riêng hoặc CDN khác phục vụ, **HeaderWriterFilter của ứng dụng Spring Boot không trực tiếp sửa được response đó**. Bạn phải kiểm policy ở nơi trả response thật.

Dù **permitAll** cho phép URL công khai, Spring Security filter chain vẫn chạy, vì vậy có cơ hội ghi headers. **Bỏ qua security chain để tối ưu CSS** có thể vô tình bỏ luôn security headers.

### 16.2. SecurityFilterChain được chọn khác dự tính

Khi có nhiều chains:
- Một chain match /api/**.
- Một chain match /admin/**.
- Một chain default cho tài nguyên khác.

Header configuration áp dụng theo **chain xử lý request**, không phải một danh sách global bất biến. Nếu một endpoint không có CSP hoặc cache-control đúng, hãy kiểm **securityMatcher**, thứ tự chain và filter thực tế. Không đặt header trong chain A rồi mặc định nó sẽ xuất hiện ở chain B.

### 16.3. Lỗi xảy ra ở proxy trước khi request tới Spring

Các response 301, 302, 404, 429, 500, 502 hoặc 503 có thể được tạo ở:
- Reverse proxy, load balancer hoặc API gateway.
- CDN/cache edge.
- Container/servlet error handling.
- Spring Boot app và Spring Security.

Nếu response được sinh **trước khi đi vào Spring**, HeaderWriterFilter không thể thêm header. Cần cấu hình edge/server phù hợp, đặc biệt với HSTS trên public HTTPS host và CSP của HTML do CDN serve.

### 16.4. Header bị ghi đè hoặc bị trùng

Một site có thể cấu hình CSP ở Spring Security, nginx và CDN cùng lúc. **Nhiều policy CSP có thể được browser áp dụng đồng thời**, làm trang bị giới hạn chặt hơn dự kiến. Trái lại, một proxy có thể ghi đè CSP bằng giá trị lỏng hơn mà đội ứng dụng không biết.

HSTS, cache-control và các policy khác cũng có thể không nhất quán giữa các lớp. Nên chỉ định **owner** cho từng header và kiểm response thực tế sau mọi middleware.

### 16.5. Security header vẫn cần vá lỗ hổng framework

Ngay cả khi code dùng đúng cấu hình, phiên bản framework cũ có thể có lỗi làm header không được ghi trong một số tình huống. Ví dụ, các bản Spring Security 6.5 trước bản vá **6.5.9** bị ảnh hưởng bởi một advisory năm 2026 liên quan HTTP headers không được ghi trong một số trường hợp. Điều này nhắc rằng **cấu hình đúng và cập nhật phiên bản đều quan trọng**.

Với sản phẩm thực, theo dõi **Spring Security Advisories**, BOM của Spring Boot và kiểm thử regression header trên phiên bản đang triển khai. Đừng cho rằng một file README hoặc cấu hình từ nhiều năm trước bảo đảm hành vi của môi trường hiện tại.

## 17. Security headers và các cơ chế an ninh khác

| Cơ chế | Nó giải quyết điều gì? | Nó không phải |
| --- | --- | --- |
| **Security response headers** | Giảm một số rủi ro cách browser xử lý response | Authentication/Authorization |
| **HTTPS/TLS** | Bảo vệ đường truyền và xác thực server theo PKI | CSP hay chặn clickjacking |
| **HSTS** | Giúp browser ưu tiên HTTPS cho host về sau | Chứng chỉ TLS hoặc quy trình vá lỗ hổng |
| **CSP** | Giới hạn nguồn/thực thi script và tài nguyên | Output encoding hoặc quyền API |
| **CORS** | Cho phép script của origin khác đọc response theo policy | Kiểm tra ai được phép truy cập dữ liệu |
| **CSRF protection** | Chống request thay đổi trạng thái giả mạo có credential tự gửi | X-Frame-Options hoặc CORS |
| **SameSite / HttpOnly / Secure cookies** | Ràng buộc việc gửi/đọc cookie trong browser | Thay thế CSRF hoặc user login |
| **AuthorizationManager / method security** | Quyết định principal được gọi endpoint/thao tác nào | CSP, HSTS hay cache-control |
| **Input validation / output encoding** | Giảm injection và xử lý dữ liệu không tin cậy | Tự có chỉ nhờ đặt Content-Security-Policy |
| **Cập nhật dependencies** | Vá lỗi framework/thư viện | Header tự phát hiện và vá CVE |

### 17.1. CORS header không giống CSP connect-src

CORS trả lời: **server đích** có cho script ở origin A đọc response của mình hay không?  
CSP **connect-src** trả lời: **document nguồn** có cho script của trang kết nối đến URL B hay không?

Một fetch cross-origin có thể bị chặn bởi CSP connect-src ngay từ phía document; nếu connect-src cho phép, browser vẫn có thể chặn đọc response vì server đích không chấp nhận CORS. Cả hai đều không thay thế Authentication.

### 17.2. CSP frame-ancestors không thay CSRF token

Chống iframe giúp giảm một kiểu clickjacking, nhưng không thể ngăn một website khác gửi simple form request trong mọi điều kiện. **POST thay đổi trạng thái dùng session cookie** vẫn cần CSRF protection theo threat model, kể cả khi X-Frame-Options: DENY.

### 17.3. Header không cấp quyền

Ví dụ API trả:

~~~http
HTTP/1.1 403 Forbidden
Content-Security-Policy: default-src 'self'
X-Content-Type-Options: nosniff
~~~

HTTP 403 vẫn có nghĩa request bị từ chối theo cơ chế tương ứng. CSP không “chuyển” người dùng thành admin hoặc cho phép client vượt qua HasAuthority. Security headers là bảo vệ response; authorization là quyết định access ở server.

## 18. Lộ trình hardening một ứng dụng web thực tế

### Bước 1: Xác định loại nội dung và nguồn phát

Liệt kê:
- HTML server-rendered, SPA index.html.
- API JSON và HTML error pages.
- CSS/JS/images/font assets, file upload/download.
- CDN, reverse proxy, gateway và static host.
- Endpoint login/logout/admin, giao diện thanh toán và trang chứa dữ liệu riêng.

Không tự giả định toàn bộ response đến từ một SecurityFilterChain duy nhất.

### Bước 2: Kiểm tra header mặc định đã thực sự hiện diện

Trên **cổng public của staging**:
- GET trang HTML.
- GET endpoint protected sau khi đăng nhập.
- GET không đăng nhập dẫn tới 401/302.
- GET tài nguyên tĩnh và trang lỗi.
- HTTPS response kiểm HSTS.
- Không kiểm HSTS trên plain HTTP như một yêu cầu phải có.

Dùng **curl -i** và browser DevTools Network. Đối với header bị thiếu, điều tra security chain, static hosting và gateway trước khi sửa code.

### Bước 3: Thiết kế CSP theo asset graph

Thu thập tất cả script/style/connect/frame endpoints hợp lệ. Bắt đầu bằng policy report-only ở staging nếu cần, xem violation reports rồi thu hẹp dần. Đừng thêm **'unsafe-inline'** hoặc wildcard tràn lan chỉ để không thấy lỗi.

Nếu có inline scripts bắt buộc, dùng **nonce/hash có quản lý đúng**, không hard-code nonce cố định. Tránh chèn thông tin bí mật vào CSP logs/reports.

### Bước 4: Chốt Referrer-Policy và Permissions-Policy

Chọn Referrer-Policy theo yêu cầu privacy và analytics; với dashboard nhạy cảm có thể ưu tiên **no-referrer**. Chặn các browser features mà ứng dụng không sử dụng. Kiểm browser support và embedding use cases.

### Bước 5: Kiểm HTTPS và HSTS sau proxy

Xác minh public host, TLS certificate, redirect HTTPS, forwarded headers đáng tin cậy, includeSubDomains/preload và phạm vi domain. Rollout HSTS thận trọng; không bật preload khi chưa kiểm toán mọi subdomain.

### Bước 6: Test browser thực và HTTP-level assertions

Tối thiểu:
- CSP chặn inline script thử nghiệm mà không phá script hợp lệ.
- Iframe embedding bị chặn theo policy.
- Content-Type đúng và nosniff không làm hỏng asset.
- Referrer và browser features tuân policy.
- HSTS có trên public HTTPS.
- 401/403/500 không vô tình thiếu security headers cần thiết.
- Authentication, Authorization, CSRF vẫn được kiểm tra đúng.

### Bước 7: Theo dõi phiên bản và regressions

Giữ dependency Spring Security/Spring Boot ở bản đã vá. Mỗi thay đổi gateway/CDN hoặc migration nhiều SecurityFilterChain cần test lại response headers, đặc biệt CSP/Cache-Control/HSTS. Các báo cáo scanner chỉ là nguồn tín hiệu; cần xác minh bằng hành vi trình duyệt.

## 19. Bảng lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| HTTP localhost không có Strict-Transport-Security | HSTS chỉ thêm cho secure request | Test HTTPS thực hoặc MockMvc secure(true) |
| HTTPS ngoài Internet có HSTS nhưng backend không có | Gateway/CDN là nơi phát HSTS | Xác nhận owner và response cuối |
| HTTPS ngoài Internet thiếu HSTS | Proxy chưa truyền/được tin scheme gốc hoặc header bị xóa | Kiểm forwarded headers, edge config và header writer |
| CSS/JS bị browser từ chối sau khi bật nosniff | Content-Type sai | Sửa MIME thay vì tắt nosniff |
| CSP làm button không chạy | Code dùng onclick/inline script | Chuyển sang external JS và addEventListener; nonce/hash nếu cần |
| CDN assets bị CSP chặn | CDN origin chưa nằm trong allowlist phù hợp | Review asset graph, thêm nguồn tin cậy tối thiểu |
| CSP Report-Only có violation nhưng JS vẫn chạy | Report-only không enforce | Sử dụng enforce sau khi QA |
| CSP nằm trong API JSON nhưng SPA vẫn chạy script ngoài | CSP của API không quản lý document frontend ở host khác | Đặt CSP trên HTML entrypoint thực |
| Đã đặt frame-src 'none' nhưng site vẫn bị nhúng | frame-src kiểm frame con, không kiểm ai nhúng trang | Dùng frame-ancestors trên response của trang bị nhúng |
| XFO DENY làm widget iframe hợp lệ bị chặn | Chính sách chống nhúng quá chặt | Thiết kế allowlist frame-ancestors và điều chỉnh XFO phù hợp |
| Không thấy security headers trên static CSS | Tệp được CDN serve hoặc web.ignoring bỏ qua chain | Cấu hình tại nơi serve; ưu tiên permitAll cho assets trong app |
| Cache-Control chặn cache ảnh công khai | Mặc định tối ưu bảo mật, không phân loại asset | Tùy biến cache đúng URL, tránh tắt global headers |
| Dữ liệu vẫn còn sau logout | Browser tab, client storage hoặc cache riêng | Kết hợp logout/session invalidation và cache/client-storage policy |
| Spring trả header khác với gateway | Cấu hình ở nhiều lớp hoặc ghi đè | Xác định owner, chuẩn hóa, test response public |
| Permissions-Policy gây lỗi camera | Feature bị chặn theo chủ đích | Chỉ allow camera nơi thật sự cần, review browser support |
| COOP làm hỏng login popup | Cross-origin isolation xung đột luồng popup | Đánh giá policy theo kiến trúc, không copy mẫu cứng |
| JWT API vẫn bị truy cập trái quyền dù có CSP | CSP không phải authorization | Sửa Authentication/Authorization, ownership và scope |
| Dùng X-XSS-Protection: 1 để chống XSS | Cơ chế cũ không đáng tin | Output encoding + CSP hợp lý |
| Script bên thứ ba có CSP allowlist mà vẫn nguy hiểm | Đối tác bị xâm nhập hoặc script có quyền cùng origin | Giảm trust, theo dõi supply chain, SRI khi phù hợp |
| Header xuất hiện trên 200 nhưng mất ở 500 | Error được tạo ở gateway/container hoặc chain khác | Kiểm error pipeline, proxy/edge headers |
| Scanner báo thiếu CSP trên API JSON | CSP chủ yếu áp cho document đã tải | Xét endpoint/content type và threat model, không sửa máy móc |

## 20. Câu hỏi tự đánh giá

1. Security headers là **request headers** hay **response headers**? Bên nào thường thực thi chính sách?
2. Những header nào Spring Security 6.x thêm mặc định? HSTS có xuất hiện trên plain HTTP không?
3. **X-XSS-Protection: 0** có phải bật bộ lọc chống XSS mới không?
4. **nosniff** khác **Content-Type** thế nào? Vì sao CSS sai MIME có thể bị chặn?
5. **X-Frame-Options: DENY** giảm rủi ro gì? Khác gì với CSP **frame-ancestors**?
6. Nếu trang muốn được nhúng bởi portal cùng công ty nhưng khác origin, cần xét policy nào?
7. Vì sao **Cache-Control: no-cache** không đồng nghĩa “không lưu” và **no-store** thích hợp hơn cho nội dung nhạy cảm?
8. **HSTS includeSubDomains** và **preload** có thể gây rủi ro vận hành nào?
9. Nếu browser kết nối HTTPS với load balancer nhưng backend nhận HTTP, cần xác minh điều gì để HSTS được gửi đúng?
10. Vì sao Spring Security không áp một CSP mặc định cho mọi trang?
11. Chính sách **script-src 'self'** sẽ xử lý inline onclick và external /assets/app.js ra sao?
12. **Content-Security-Policy-Report-Only** khác header CSP enforce ở điều gì?
13. **frame-src** có dùng để chặn người khác nhúng trang mình không? Vì sao?
14. **Referrer-Policy: no-referrer** giảm rủi ro thông tin nào?
15. **Permissions-Policy** có thay user permission prompts của browser không?
16. Khi nào **COOP/COEP/CORP** cần thử đặc biệt kỹ vì nguy cơ làm hỏng tích hợp?
17. Vì sao **permitAll** thường thích hợp hơn **web.ignoring** đối với tài nguyên tĩnh có nhu cầu security headers?
18. Nếu HTML entrypoint do CDN serve còn API do Spring serve, CSP nên được kiểm tại đâu?
19. Vì sao header đầy đủ vẫn không thay được CSRF, Authentication, Authorization và kiểm quyền trên từng tài nguyên?
20. Với MockMvc, secure(true) chứng minh được điều gì và chưa chứng minh được điều gì về TLS production?

**Ghi nhớ:** Security headers giúp **trình duyệt giảm bề mặt tấn công khi xử lý response**, nhưng không biến một ứng dụng thiếu phân quyền hoặc chứa XSS thành an toàn. **Spring Security 6.x có bộ header mặc định** (cache-control, nosniff, XFO, HSTS trên HTTPS, X-XSS-Protection: 0); **CSP/Referrer-Policy/Permissions-Policy** cần thiết kế theo ứng dụng. Luôn kiểm header ở response thực sau proxy/CDN, test browser và giữ các lớp xác thực, phân quyền, CSRF, output encoding và TLS hoạt động đồng thời.

## 21. Tài liệu tham khảo chính thức

- Spring Security 6.5 — Security HTTP Response Headers (Servlet): https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/headers.html
- Spring Security 6.5 — Security HTTP Response Headers (features, defaults và phạm vi): https://docs.spring.io/spring-security/reference/6.5/features/exploits/headers.html
- Spring Security 6.5 — HTTP/HTTPS and Proxy Configuration: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/http.html
- Spring Boot — Running Behind a Front-end Proxy: https://docs.spring.io/spring-boot/reference/how-to/webserver.html
- MDN — HTTP Headers Reference: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers
- MDN — Content Security Policy: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP
- MDN — Strict-Transport-Security: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Strict-Transport-Security
- MDN — X-Frame-Options: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Frame-Options
- MDN — X-Content-Type-Options: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Content-Type-Options
- MDN — Referrer-Policy: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referrer-Policy
- MDN — Permissions-Policy: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Permissions-Policy
- OWASP — HTTP Security Response Headers Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html
- Spring Security Advisory, March 2026 — Under Some Conditions HTTP Headers Are Not Written (CVE-2026-22732): https://spring.io/security/cve-2026-22732/
