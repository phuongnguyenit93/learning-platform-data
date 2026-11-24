# Browser security boundary

Trình duyệt là một môi trường thực thi phức tạp, nơi nhiều website, iframe, script, worker và tiện ích có thể cùng hoạt động trong một phiên sử dụng. Mỗi thành phần có thể đến từ một nguồn khác nhau và mang mức độ tin cậy khác nhau. Browser security boundary là tập hợp các ranh giới mà trình duyệt và ứng dụng dùng để giới hạn việc đọc dữ liệu, thực thi mã, gửi thông tin, truy cập thiết bị và tương tác giữa các tài liệu.

Hiểu đúng các ranh giới này giúp thiết kế ứng dụng web an toàn. Một origin có thể được bảo vệ bởi Same-Origin Policy (SOP), nhưng cookie lại có phạm vi domain và path riêng. CORS có thể cho phép JavaScript đọc response cross-origin, nhưng không thay thế xác thực, phân quyền hoặc phòng vệ CSRF. Iframe sandbox có thể tạo môi trường cách ly, nhưng quyền được cấp qua token và cấu hình origin vẫn quyết định khả năng tương tác. CSP giới hạn hành vi nội dung, còn process sandbox và site isolation bảo vệ ở các lớp kiến trúc khác.

Bài học thuộc module <code>SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY</code>, tập trung vào ranh giới giữa trình duyệt, origin, cookie và ứng dụng web; từ đó hiểu SOP, CORS, các cơ chế cách ly và cách phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types và security headers.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt browser process, renderer process, site, origin, browsing context và storage boundary.
- Giải thích vai trò của Same-Origin Policy, CORS và các kênh giao tiếp cross-origin.
- Xác định phạm vi thực tế của cookie, storage, service worker và partitioning.
- Đánh giá iframe sandbox, postMessage, COOP, COEP, CORP và Permissions Policy.
- Phân tích cách XSS, CSRF và clickjacking tác động lên các ranh giới bảo mật.
- Xây dựng threat model và ma trận kiểm thử cho ứng dụng có nhiều origin, iframe, API và nội dung bên thứ ba.

## 1. Mô hình kiến trúc bảo mật của trình duyệt

Trình duyệt vừa là ứng dụng hiển thị nội dung vừa là môi trường thực thi mã không đáng tin cậy. Một trang web có thể tải JavaScript, hình ảnh, font, iframe và dữ liệu từ nhiều server. Mỗi script có thể tác động tới DOM trong phạm vi quyền được cấp, gửi request và sử dụng một số API của browser.

Các trình duyệt hiện đại thường dùng kiến trúc đa tiến trình. Chi tiết phân chia tiến trình khác nhau giữa sản phẩm và phiên bản, nhưng có thể hình dung các thành phần phổ biến:

| Thành phần | Vai trò khái quát | Ranh giới cần hiểu |
|---|---|---|
| Browser process | Quản lý cửa sổ, tab, điều hướng, quyền và điều phối các thành phần | Là lớp đặc quyền cao; lỗi ở đây có thể ảnh hưởng toàn browser |
| Renderer process | Phân tích HTML/CSS, chạy JavaScript và dựng trang | Chạy nội dung web không đáng tin cậy; thường bị giới hạn bằng sandbox |
| Network service/process | Xử lý kết nối, tải tài nguyên và các chính sách mạng liên quan | Kiểm soát request, response và nhiều quy tắc web security |
| GPU process | Hỗ trợ kết xuất đồ họa | Có ranh giới tiến trình riêng tùy browser |
| Utility processes | Xử lý tác vụ như giải mã media hoặc dịch vụ nền | Giới hạn tác động khi một thành phần gặp lỗi |
| Extension processes/contexts | Chạy tiện ích và API mở rộng | Có thể có quyền cao hơn trang web thông thường |

Đây là mô hình khái niệm. Không nên giả định mọi browser luôn có đúng số tiến trình hoặc phân chia công việc giống nhau. Một số browser có thể dùng chung renderer cho nhiều tài liệu cùng site, tách renderer theo site hoặc áp dụng chiến lược khác tùy tài nguyên và cấu hình.

### Renderer không phải vùng tin cậy

HTML và JavaScript từ website phải được xem là đầu vào không đáng tin cậy, kể cả khi website thuộc tổ chức của bạn. Renderer xử lý nội dung này trong phạm vi quyền được browser cấp. Sandbox của renderer giúp hạn chế truy cập hệ điều hành và tài nguyên đặc quyền nếu mã web bị khai thác.

Process sandbox và Same-Origin Policy giải quyết hai lớp khác nhau:

- Process sandbox giới hạn khả năng của tiến trình đối với hệ điều hành và các tài nguyên bên ngoài.
- SOP giới hạn việc một tài liệu hoặc script truy cập dữ liệu của origin khác.
- Site isolation là chiến lược kiến trúc tách nội dung từ các site khác nhau vào những tiến trình riêng khi browser hỗ trợ và áp dụng.
- CSP giới hạn hành vi mà nội dung trong một tài liệu được phép thực hiện.

Một trang bị XSS vẫn có thể chạy mã trong origin của ứng dụng và đọc dữ liệu mà origin đó được phép truy cập. Renderer sandbox không tự ngăn script độc hại đọc DOM hoặc dữ liệu cùng origin. Do đó, cần kết hợp phòng vệ XSS với các ranh giới khác.

### Site isolation

Site isolation là cơ chế kiến trúc giúp giảm khả năng nội dung từ các site khác nhau cùng chia sẻ vùng thực thi có thể truy cập lẫn nhau. Trong các browser hỗ trợ, cross-site iframe hoặc tab có thể được đặt vào renderer process khác. Điều này giúp giảm tác động của một số lỗi renderer và hạn chế rò rỉ dữ liệu qua các kênh bộ nhớ.

Site isolation là chi tiết triển khai của browser, không phải API mà ứng dụng có thể dùng thay SOP. Không dựa vào việc hai site đang nằm ở hai process để cấp quyền hoặc kết luận dữ liệu được cách ly đầy đủ. Ứng dụng vẫn phải dùng SOP, CORS, CSP, sandbox và xác thực phù hợp.

## 2. Origin, site và browsing context

### Origin là ranh giới của SOP

Với URL web thông thường, origin gồm ba thành phần:

1. Scheme, ví dụ <code>https</code>.
2. Host, ví dụ <code>app.example.test</code>.
3. Port hiệu lực, ví dụ <code>443</code> hoặc <code>8443</code>.

Hai URL cùng origin khi scheme, host và port sau chuẩn hóa tương ứng. Path, query và fragment không tham gia phép so sánh.

| URL A | URL B | Quan hệ |
|---|---|---|
| <code>https://app.example.test/a</code> | <code>https://app.example.test/b</code> | Cùng origin |
| <code>https://app.example.test</code> | <code>http://app.example.test</code> | Khác origin |
| <code>https://app.example.test</code> | <code>https://admin.example.test</code> | Khác origin |
| <code>https://app.example.test</code> | <code>https://app.example.test:8443</code> | Khác origin |
| <code>https://app.example.test</code> | <code>https://app.example.test:443</code> | Cùng origin sau chuẩn hóa port mặc định |

Dùng URL API để phân tích URL thay vì tách chuỗi bằng regex hoặc so sánh chuỗi con:

~~~js
const url = new URL("https://app.example.test:443/account?id=7");

console.log(url.origin);   // https://app.example.test
console.log(url.protocol); // https:
console.log(url.hostname); // app.example.test
console.log(url.port);     // rỗng vì là port mặc định
~~~

Một số tài liệu có opaque origin, chẳng hạn tài liệu sandbox không có <code>allow-same-origin</code> hoặc tài liệu <code>data:</code>. Khi tuần tự hóa, opaque origin thường hiển thị là <code>null</code>. Không dùng chuỗi <code>null</code> làm một mục allowlist tin cậy vì nhiều opaque origin khác nhau có thể cùng được biểu diễn như vậy.

### Site và schemeful site

Site thường được browser dùng trong các chính sách như SameSite cookie và một số cơ chế chống theo dõi. Schemeful site xét scheme cùng registrable domain theo Public Suffix List. Vì vậy:

- <code>https://app.example.test</code> và <code>https://admin.example.test</code> khác origin nhưng thường cùng site.
- <code>https://app.example.test</code> và <code>http://app.example.test</code> khác origin và khác schemeful site.
- <code>https://example.test</code> và <code>https://example.test.attacker.invalid</code> khác host và khác site.

Không dùng từ “cùng domain” thay cho “cùng origin” hoặc “cùng site”. Ba khái niệm này phục vụ các mục đích khác nhau.

### Browsing context và quan hệ cửa sổ

Browsing context là môi trường chứa một tài liệu đang được hiển thị hoặc chạy, ví dụ tab, iframe hoặc popup. Một tài liệu có thể có quan hệ với tài liệu khác qua:

- Trang cha và iframe con.
- Cửa sổ mở bằng <code>window.open()</code> và cửa sổ opener.
- Các tab hoặc cửa sổ có cùng origin.
- Worker được tạo bởi tài liệu.
- Service worker điều khiển một tập URL trong scope của nó.

SOP kiểm soát các thao tác giữa các cửa sổ. Ví dụ, cửa sổ có thể giữ tham chiếu tới <code>window.opener</code>, nhưng việc đọc DOM của cửa sổ khác origin bị giới hạn. Một số thuộc tính điều hướng hoặc đóng cửa sổ có hành vi riêng; không suy luận rằng có tham chiếu Window nghĩa là có quyền đọc nội dung.

## 3. Same-Origin Policy và CORS

### SOP bảo vệ dữ liệu như thế nào?

SOP giới hạn việc một script từ origin này đọc hoặc thao tác dữ liệu của origin khác. Các vùng thường được bảo vệ gồm:

- DOM của tài liệu khác origin.
- <code>localStorage</code> và nhiều API lưu trữ gắn với origin.
- Một số thuộc tính của Window và iframe.
- Kết quả response mạng mà JavaScript muốn đọc.
- Tài nguyên hoặc API có chính sách cross-origin riêng.

SOP không chặn tất cả request cross-origin. Một trang có thể gửi form, tải image, điều hướng hoặc thực hiện một số request tới origin khác. Việc gửi request và việc đọc response là hai quyền khác nhau.

### CORS mở quyền đọc response có kiểm soát

CORS là cơ chế server dùng HTTP response header để cho browser biết origin nào được phép đọc response cross-origin từ JavaScript.

Ví dụ:

~~~http
Access-Control-Allow-Origin: https://portal.example.test
Vary: Origin
~~~

Nếu request có credentials, server cần cấu hình cụ thể và đáp ứng quy tắc credentials:

~~~http
Access-Control-Allow-Origin: https://portal.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Wildcard <code>*</code> không hợp lệ khi response cần được expose với credentials. CORS không xác thực người dùng, không phân quyền thao tác và không thay thế CSRF protection.

| Cơ chế | Vai trò | Điều không nên suy luận |
|---|---|---|
| SOP | Hạn chế script đọc dữ liệu cross-origin | Không có nghĩa mọi request cross-origin bị chặn |
| CORS | Cho phép một origin đọc response theo header của server | Không chứng minh người dùng đã đăng nhập hoặc được phép thao tác |
| CSRF token | Xác minh request nhạy cảm có bằng chứng chống giả mạo | Không thay thế authorization phía server |
| SameSite cookie | Giới hạn một số cách cookie được gửi trong ngữ cảnh cross-site | Không phải cơ chế phân quyền đầy đủ |

### Preflight và request đơn giản

Với một số request cross-origin, browser gửi preflight <code>OPTIONS</code> để hỏi server có cho phép method và header dự kiến không. Nếu preflight thất bại, browser không gửi request chính theo luồng đó.

Request đơn giản có thể được gửi mà không cần preflight. Dù JavaScript không đọc được response vì CORS, server vẫn có thể đã nhận request. Vì vậy, endpoint có tác dụng phụ vẫn cần xác thực, authorization, CSRF protection và kiểm tra dữ liệu ở server.

## 4. Cookie có ranh giới riêng

Cookie không tuân theo cùng quy tắc với origin. Phạm vi cookie phụ thuộc domain/host, path, Secure, HttpOnly, SameSite, thời hạn và một số thuộc tính khác.

### Host-only và Domain cookie

Cookie không có thuộc tính Domain thường là host-only và chỉ được gửi tới host đã đặt cookie. Cookie có <code>Domain=example.test</code> có thể được gửi tới domain đó và các subdomain phù hợp.

Cookie không bị cô lập theo port. Hai ứng dụng trên hai port khác nhau của cùng host có thể nhận cùng cookie nếu các thuộc tính domain/path và ngữ cảnh request phù hợp. Vì vậy, không dùng port khác nhau như một biện pháp cô lập cookie.

### Các thuộc tính quan trọng

| Thuộc tính | Tác dụng | Giới hạn |
|---|---|---|
| <code>Secure</code> | Chỉ gửi cookie qua kết nối an toàn theo quy tắc browser | Không tự ngăn XSS đọc cookie nếu cookie không có HttpOnly |
| <code>HttpOnly</code> | Không cho JavaScript đọc cookie qua <code>document.cookie</code> | Browser vẫn có thể gửi cookie trong request |
| <code>SameSite=Strict</code> | Giới hạn cookie trong ngữ cảnh same-site chặt hơn | Có thể ảnh hưởng luồng điều hướng từ site khác |
| <code>SameSite=Lax</code> | Cho phép một số điều hướng top-level an toàn theo quy tắc browser | Không thay thế CSRF token cho mọi request |
| <code>SameSite=None; Secure</code> | Cho phép cookie trong một số ngữ cảnh cross-site nếu các điều kiện khác đáp ứng | Chính sách chặn cookie bên thứ ba vẫn có thể ảnh hưởng |
| <code>Domain</code> | Mở rộng phạm vi cookie tới domain/subdomain phù hợp | Tăng phạm vi host có thể nhận cookie |
| <code>Path</code> | Giới hạn request path gửi cookie | Không phải ranh giới bảo mật đáng tin cậy giữa ứng dụng |

Ví dụ cookie phiên:

~~~http
Set-Cookie: __Host-session=opaque-value; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Prefix <code>__Host-</code> yêu cầu cookie phải có Secure, Path=/ và không có Domain theo quy tắc hỗ trợ của browser. Điều này giúp cookie gắn với host đặt cookie và tránh bị subdomain đặt cookie cùng tên theo cách thông thường. Prefix này không thay thế kiểm soát phiên ở server.

### SameSite và CSRF

CSRF xảy ra khi browser tự gửi thông tin xác thực (thường là cookie) trong một request mà người dùng không chủ ý thực hiện. SameSite giúp giảm một số request cross-site mang cookie, nhưng ứng dụng vẫn cần bảo vệ các thao tác thay đổi trạng thái.

Với endpoint nhạy cảm:

- Dùng CSRF token phù hợp với kiến trúc ứng dụng.
- Kiểm tra Origin hoặc Referer khi có thể và theo chính sách rõ ràng.
- Không dùng GET để thực hiện thao tác thay đổi trạng thái.
- Xác minh authorization trên server cho từng thao tác.
- Cấu hình SameSite phù hợp với luồng đăng nhập, SSO và điều hướng.

Không coi CORS là biện pháp chống CSRF. Một form cross-site có thể gửi request dù script của trang gửi không đọc được response.

## 5. Storage và partitioning

Storage trong browser có nhiều phạm vi khác nhau. Không phải mọi loại dữ liệu đều dùng chung một khóa hoặc một boundary.

| Cơ chế | Phạm vi khái quát | Điểm cần lưu ý |
|---|---|---|
| <code>localStorage</code> | Origin | Khác scheme, host hoặc port tạo vùng riêng |
| <code>sessionStorage</code> | Origin và top-level browsing context | Các tab có thể có session storage riêng |
| IndexedDB | Origin, có thể chịu partitioning theo browser | Dữ liệu third-party có thể bị phân vùng hoặc hạn chế |
| Cache Storage | Origin và storage context | Cần kiểm tra partitioning và lifecycle |
| Service worker | Origin và scope path | Worker chỉ điều khiển URL phù hợp với scope và quyền |
| Cookie | Host/domain, path và thuộc tính cookie | Không theo port; SameSite xét ngữ cảnh site |
| HTTP cache | Theo cache key và chính sách browser | Có thể chịu cache partitioning và Vary |

### Third-party storage partitioning

Khi một trang nhúng nội dung từ domain khác, browser có thể phân vùng storage của bên thứ ba theo top-level site hoặc áp dụng hạn chế riêng tư. Điều này giúp giảm khả năng theo dõi người dùng qua nhiều website.

Ví dụ, cùng một widget ở <code>https://widget.example.test</code> được nhúng trong hai top-level site khác nhau có thể không nhìn thấy cùng một vùng storage. Hành vi cụ thể phụ thuộc browser, phiên bản và cơ chế lưu trữ.

Nếu ứng dụng dựa vào đăng nhập trong iframe hoặc chia sẻ trạng thái qua nhiều site, cần kiểm thử trên các browser thực tế. Thiết kế fallback an toàn như điều hướng top-level hoặc luồng đăng nhập do người dùng khởi tạo thay vì giả định third-party storage luôn có sẵn.

### Service worker

Service worker là script nền gắn với origin và scope. Nó có thể nhận sự kiện fetch cho các URL nằm trong phạm vi điều khiển, quản lý cache và hỗ trợ offline. Nó không có quyền đọc tùy ý dữ liệu của origin khác.

Các điểm cần kiểm tra:

- Đăng ký service worker trong secure context.
- Scope không vượt ngoài phạm vi được phép.
- Cache không chứa response nhạy cảm sau logout hoặc thay đổi tài khoản.
- Update và activation không giữ logic cũ ngoài dự kiến.
- Không tin dữ liệu từ cache như bằng chứng rằng người dùng vẫn được authorization.
- Xóa hoặc làm mới dữ liệu phù hợp khi logout và khi thay đổi quyền.

Service worker có thể phục vụ response từ cache; server vẫn phải kiểm tra authorization cho request cần bảo vệ khi có mạng. Không để dữ liệu tài khoản cũ bị lộ khi browser dùng chung profile.

## 6. Iframe, sandbox và giao tiếp giữa origin

Iframe tạo một browsing context riêng. Mặc định, tài liệu iframe vẫn có origin theo URL của nó. Nếu khác origin với trang cha, SOP hạn chế việc đọc DOM và dữ liệu.

### Sandbox

Thuộc tính <code>sandbox</code> áp dụng các hạn chế cho nội dung iframe. Có thể cấp lại một số quyền bằng token:

~~~html
<iframe
  src="https://preview.example.test/document"
  sandbox="allow-scripts"
  title="Isolated preview">
</iframe>
~~~

Không có <code>allow-same-origin</code>, tài liệu sandbox thường nhận opaque origin. Một số token phổ biến:

| Token | Quyền được cấp |
|---|---|
| <code>allow-scripts</code> | Cho phép script trong iframe chạy |
| <code>allow-same-origin</code> | Giữ origin thực của tài liệu thay vì chuyển thành opaque origin |
| <code>allow-forms</code> | Cho phép submit form |
| <code>allow-popups</code> | Cho phép mở popup |
| <code>allow-downloads</code> | Cho phép một số thao tác download |
| <code>allow-top-navigation</code> | Cho phép điều hướng top-level theo phạm vi token |

Cần cấp quyền tối thiểu. Kết hợp <code>allow-scripts</code> và <code>allow-same-origin</code> cho nội dung không tin cậy cùng origin với trang cha có thể làm giảm đáng kể tác dụng sandbox; nội dung có thể tìm cách bỏ thuộc tính sandbox trong một số cấu hình. Với preview file hoặc HTML do người dùng cung cấp, nên dùng origin riêng biệt và sandbox chặt.

### postMessage

Khi cần giao tiếp cross-origin, dùng <code>window.postMessage()</code> thay cho truy cập DOM trực tiếp. Bên gửi nên chỉ định target origin cụ thể:

~~~js
const frame = document.querySelector("#trusted-frame");

frame.contentWindow.postMessage(
  { type: "REQUEST_STATUS", requestId: "test-001" },
  "https://portal.example.test"
);
~~~

Bên nhận cần xác minh origin, source và schema:

~~~js
const expectedOrigin = "https://app.example.test";
const expectedSource = window.parent;

window.addEventListener("message", (event) => {
  if (event.origin !== expectedOrigin) return;
  if (event.source !== expectedSource) return;

  const data = event.data;
  if (!data || typeof data !== "object" || Array.isArray(data)) return;
  if (data.type !== "SET_THEME") return;
  if (data.theme !== "light" && data.theme !== "dark") return;

  applyTheme(data.theme);
});
~~~

Không tin message chỉ vì origin hợp lệ. Một origin có thể chứa nhiều trang hoặc cửa sổ; cần xác minh source và dữ liệu. Không dùng message làm bằng chứng authorization cho thao tác nhạy cảm ở server.

Với opaque origin, <code>event.origin</code> có thể là <code>null</code>. Không dùng riêng giá trị này làm allowlist. Nếu giao thức cần trao đổi với nội dung opaque origin, phải thiết kế kênh capability có phạm vi, vòng đời và dữ liệu tối thiểu rõ ràng.

## 7. Các security header tạo boundary

Security headers bổ sung quy tắc mà browser áp dụng khi tải và hiển thị nội dung. Chúng không thay thế xác thực hoặc phân quyền ở server.

### Content-Security-Policy

CSP giới hạn nguồn tài nguyên và hành động được phép:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-random-per-response'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
~~~

Các directive quan trọng:

- <code>default-src</code>: nguồn mặc định cho nhiều nhóm tài nguyên.
- <code>script-src</code>, <code>style-src</code>: nguồn script và style.
- <code>object-src 'none'</code>: chặn plugin object không cần thiết.
- <code>base-uri</code>: giới hạn URL base.
- <code>frame-ancestors</code>: giới hạn origin được phép nhúng tài liệu.
- <code>connect-src</code>: giới hạn các kết nối do script khởi tạo.

Nonce phải được sinh ngẫu nhiên cho mỗi response và gắn chính xác vào script/style được phép. Không tái sử dụng nonce tĩnh hoặc đưa nonce vào nơi có thể bị attacker đọc và sử dụng.

### X-Frame-Options và frame-ancestors

Clickjacking xảy ra khi kẻ tấn công nhúng trang hợp lệ vào một frame được bố trí để lừa người dùng thao tác. CSP <code>frame-ancestors</code> là cơ chế hiện đại để chỉ định ai được phép nhúng tài liệu. <code>X-Frame-Options</code> vẫn có ích cho một số browser cũ:

~~~http
Content-Security-Policy: frame-ancestors 'self'
X-Frame-Options: SAMEORIGIN
~~~

Không đặt header mâu thuẫn giữa các route. Nếu ứng dụng cần được nhúng bởi một đối tác, chỉ cho phép origin chính xác đã được xác minh.

### COOP, COEP và CORP

Các header này kiểm soát quan hệ giữa browsing context và việc tải tài nguyên cross-origin:

| Header | Vai trò |
|---|---|
| <code>Cross-Origin-Opener-Policy (COOP)</code> | Kiểm soát quan hệ opener và việc tài liệu có chia sẻ browsing context group với cửa sổ khác hay không |
| <code>Cross-Origin-Embedder-Policy (COEP)</code> | Yêu cầu tài nguyên cross-origin được cấp phép theo cơ chế phù hợp trước khi nhúng |
| <code>Cross-Origin-Resource-Policy (CORP)</code> | Cho phép hoặc hạn chế tài liệu khác origin/site tải tài nguyên trong một số ngữ cảnh no-cors |

Một cấu hình thường gặp để bật cross-origin isolation khi ứng dụng đáp ứng đủ yêu cầu:

~~~http
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
~~~

COEP có thể làm các tài nguyên cross-origin bị chặn nếu chúng không đáp ứng CORS hoặc CORP phù hợp. Cần kiểm tra CDN, font, image, worker và các thư viện bên thứ ba trước khi rollout.

COOP/COEP có thể tạo môi trường cross-origin isolated trong browser hỗ trợ khi các điều kiện liên quan được đáp ứng. Không coi việc gửi hai header là bằng chứng đầy đủ; xác minh <code>window.crossOriginIsolated</code> và các tính năng mà ứng dụng cần.

### Permissions Policy

Permissions Policy giới hạn việc tài liệu và iframe sử dụng một số tính năng mạnh như camera, microphone, geolocation hoặc fullscreen. Ví dụ:

~~~http
Permissions-Policy: camera=(), microphone=(), geolocation=(self)
~~~

Cấu hình header và thuộc tính <code>allow</code> của iframe cần nhất quán với yêu cầu sản phẩm. Permissions Policy giới hạn khả năng sử dụng API trong ngữ cảnh tài liệu; nó không thay thế hộp thoại xin quyền của browser hoặc quyết định của hệ điều hành.

### Referrer-Policy và X-Content-Type-Options

<code>Referrer-Policy</code> giới hạn thông tin referrer được gửi khi điều hướng hoặc tải tài nguyên. <code>X-Content-Type-Options: nosniff</code> yêu cầu browser tuân theo MIME type trong các ngữ cảnh được quy định, giúp giảm rủi ro diễn giải nội dung sai loại.

~~~http
Referrer-Policy: strict-origin-when-cross-origin
X-Content-Type-Options: nosniff
~~~

Các header này hỗ trợ bảo vệ dữ liệu và ngăn một số kiểu MIME confusion. Chúng không thay thế việc đặt Content-Type chính xác và xử lý upload an toàn.

## 8. XSS, CSRF và clickjacking qua góc nhìn boundary

### XSS vượt qua ranh giới tin cậy trong origin

Khi XSS xảy ra, script độc hại có thể chạy trong origin của ứng dụng. Từ góc nhìn SOP, script đó có thể có quyền tương tự script hợp lệ của trang. Nó có thể đọc DOM, gọi API bằng phiên hiện tại, truy cập storage trong phạm vi được phép hoặc gửi dữ liệu ra ngoài nếu CSP cho phép.

Các biện pháp giảm thiểu:

- Encode output theo đúng HTML/attribute/URL/JavaScript context.
- Tránh chèn chuỗi không tin cậy qua <code>innerHTML</code>.
- Dùng DOM API an toàn và Trusted Types khi phù hợp.
- Dùng CSP nonce/hash và loại bỏ inline script không cần thiết.
- Đặt cookie phiên là HttpOnly, Secure và SameSite phù hợp.
- Không lưu token dài hạn trong storage có thể bị JavaScript đọc nếu kiến trúc có lựa chọn an toàn hơn.
- Kiểm tra authorization phía server cho mọi request.

HttpOnly có thể ngăn script đọc trực tiếp giá trị cookie nhưng không ngăn XSS gửi request bằng cookie đó hoặc thao tác UI trong phiên người dùng. Vì vậy, cookie an toàn là một lớp bảo vệ, không phải cách khắc phục XSS.

### CSRF khai thác cách browser gửi cookie

CSRF lợi dụng việc browser tự động đính kèm cookie phù hợp vào request. SOP có thể ngăn trang tấn công đọc response nhưng không nhất thiết ngăn request tới server. Phòng vệ cần thực hiện ở server và trong thiết kế request:

- CSRF token cho thao tác thay đổi trạng thái.
- Kiểm tra Origin/Referer theo chính sách.
- SameSite cookie phù hợp.
- Không dùng GET cho hành động thay đổi dữ liệu.
- Xác thực và authorization ở server.

### Clickjacking khai thác giao diện được nhúng

Clickjacking sử dụng iframe để đặt giao diện thật dưới lớp nội dung đánh lừa. Cần giới hạn bên được phép nhúng bằng <code>frame-ancestors</code> hoặc X-Frame-Options tương thích. Với các luồng nhúng hợp lệ, xác minh origin cha và các thao tác nhạy cảm; không dựa vào một kiểm tra JavaScript phía client duy nhất để quyết định quyền.

## 9. Secure context, TLS và nguồn gốc đáng tin cậy

Nhiều API web mạnh chỉ hoạt động trong secure context. HTTPS giúp bảo vệ tính bí mật và toàn vẹn của dữ liệu khi truyền, đồng thời tạo điều kiện cho browser cấp các quyền và API như service worker trong môi trường thông thường.

Secure context không có nghĩa website tự động đáng tin cậy. Một trang HTTPS vẫn có thể chứa XSS, cấu hình CSP sai hoặc gọi API trái phép. TLS xác minh kết nối tới host theo chứng chỉ; nó không chứng minh nội dung ứng dụng là an toàn.

Các điểm cần kiểm tra:

- Chứng chỉ hợp lệ, hostname khớp và chuỗi tin cậy được xác minh.
- HTTP được chuyển hướng sang HTTPS theo thiết kế.
- HSTS được cấu hình phù hợp để giảm nguy cơ downgrade.
- Không có mixed content chủ động hoặc request nhạy cảm qua HTTP.
- Cookie phiên có Secure.
- Redirect không đưa dữ liệu nhạy cảm sang origin ngoài dự kiến.
- API chỉ chấp nhận giao thức và host hợp lệ.

Không bỏ qua lỗi chứng chỉ trong production hoặc dùng tùy chọn ignore certificate error trong kiểm thử bảo mật thông thường. Nếu cần kiểm tra lỗi TLS, tạo ca riêng và ghi rõ mục tiêu.

## 10. Extension và nội dung bên thứ ba

Extension có thể có quyền đọc hoặc sửa trang, truy cập tab, request hoặc dữ liệu theo quyền người dùng cấp. Extension không cùng mô hình quyền với script website. Một trang web không nên tin extension chỉ vì nó chạy trong browser; extension độc hại hoặc bị xâm phạm có thể trở thành một phần của threat model.

Nội dung bên thứ ba như analytics, chat widget, payment iframe và tag manager cũng có thể thay đổi ranh giới tin cậy. Mỗi tích hợp cần được đánh giá:

- Ai sở hữu script hoặc iframe?
- Script chạy trong origin của ứng dụng hay origin riêng?
- Dữ liệu nào được gửi cho nhà cung cấp?
- Script có quyền truy cập DOM hoặc storage không?
- Cần CORS, CSP, SRI, sandbox hoặc postMessage không?
- Cách cập nhật và thu hồi tích hợp khi có sự cố?

Ưu tiên nhúng nội dung không tin cậy qua origin riêng và sandbox khi phù hợp. Với script chạy trực tiếp trong origin ứng dụng, cần đánh giá kỹ vì script thường có quyền lớn trong tài liệu đó.

## 11. Xây dựng threat model cho browser boundary

Threat model cần xác định tài sản, chủ thể, ranh giới, luồng dữ liệu và tác động nếu một ranh giới bị vượt qua.

### Tài sản cần bảo vệ

- Cookie phiên và thông tin xác thực.
- Dữ liệu tài khoản, hồ sơ và giao dịch.
- DOM và state của ứng dụng.
- Access token, CSRF token và dữ liệu API.
- Nội dung người dùng tải lên hoặc nội dung preview.
- Dữ liệu trong localStorage, IndexedDB và Cache Storage.
- Quyền camera, microphone, clipboard và geolocation.
- Thông tin nhạy cảm được gửi qua postMessage hoặc iframe.

### Chủ thể và mức tin cậy

| Chủ thể | Mức tin cậy mặc định | Rủi ro |
|---|---|---|
| Browser engine | Hạ tầng thực thi của người dùng | Lỗi browser, phiên bản cũ, cấu hình riêng tư |
| Ứng dụng chính | Được tổ chức kiểm soát nhưng có thể có lỗi | XSS, logic authorization sai |
| API backend | Thành phần tin cậy theo kiến trúc | Kiểm tra quyền và dữ liệu không đầy đủ |
| Third-party script | Chỉ tin trong phạm vi đã duyệt | Supply-chain compromise, thu thập dữ liệu |
| Iframe bên ngoài | Origin riêng, dữ liệu không tin cậy | Message giả mạo, navigation, clickjacking |
| Extension | Quyền do người dùng hoặc tổ chức cấp | Can thiệp DOM và request |
| Người dùng | Có thể bị lừa hoặc thao tác nhầm | CSRF, clickjacking, phishing |

### Sơ đồ ranh giới tham khảo

~~~mermaid
flowchart TB
    subgraph Browser["Browser"]
        subgraph Main["Ứng dụng chính - origin A"]
            UI["DOM và JavaScript"]
            Store["Cookie / Storage"]
            SW["Service worker"]
        end
        subgraph Frame["Iframe - origin B"]
            Widget["Nội dung bên thứ ba"]
        end
        Ext["Extension context"]
        Sandbox["Renderer sandbox / process boundary"]
    end
    API["Backend API"]
    Third["Third-party service"]
    UI --> Store
    UI -->|Fetch / CORS| API
    UI -->|postMessage có kiểm tra| Widget
    Widget -->|Message được xác minh| UI
    UI -->|Request theo CSP| Third
    Ext -. "Quyền extension" .-> UI
    Main -. "Được browser cách ly" .-> Sandbox
~~~

Sơ đồ thể hiện các vùng logic để phân tích. Browser có thể tổ chức process và storage khác nhau; không suy luận từ sơ đồ rằng mỗi vùng luôn tương ứng một process riêng.

### Câu hỏi khi lập threat model

1. Dữ liệu nào có thể được đọc nếu script chạy trong origin chính?
2. Origin nào có thể gửi request tới API và origin nào được đọc response?
3. Cookie có được gửi trong iframe hoặc điều hướng cross-site không?
4. Third-party script có chạy trong origin chính hay origin riêng?
5. Iframe có token sandbox tối thiểu và giao thức postMessage được xác minh không?
6. Nội dung upload/preview có thể thực thi script hoặc truy cập cookie không?
7. CSRF token, Origin check và authorization được thực hiện ở đâu?
8. Browser cũ hoặc browser chặn third-party storage sẽ ảnh hưởng luồng nào?
9. Khi một boundary thất bại, dữ liệu và chức năng nào có thể bị ảnh hưởng?

## 12. Ma trận kiểm thử browser security boundary

Dùng ma trận dưới đây để kiểm tra các ranh giới trong một ứng dụng có frontend, API, iframe và nội dung bên thứ ba:

| ID | Boundary | Tình huống | Kết quả mong đợi |
|---|---|---|---|
| BSB-01 | Origin | Khác scheme, host hoặc port | SOP xem là origin khác |
| BSB-02 | SOP | Trang khác origin đọc DOM riêng tư | Bị chặn |
| BSB-03 | CORS | Origin được allowlist đọc API | Chỉ response được phép mới được expose |
| BSB-04 | CORS | Origin lạ gọi API có tác dụng phụ | Server vẫn yêu cầu xác thực, authorization và CSRF protection |
| BSB-05 | Cookie | Host-only cookie gửi tới subdomain khác | Không được gửi tới host khác |
| BSB-06 | Cookie | Cookie Domain | Chỉ gửi tới domain/subdomain phù hợp |
| BSB-07 | Cookie | Cookie HttpOnly | JavaScript không đọc được cookie |
| BSB-08 | SameSite | Request cross-site | Cookie được gửi theo thuộc tính và chính sách browser |
| BSB-09 | Storage | localStorage khác origin | Không đọc được vùng storage của origin kia |
| BSB-10 | Storage | Third-party iframe | Kiểm tra partitioning và hạn chế của browser |
| BSB-11 | Sandbox | Iframe opaque origin | Không truy cập DOM trực tiếp |
| BSB-12 | postMessage | Origin hoặc source không tin cậy | Listener từ chối |
| BSB-13 | CSP | Inline script không có nonce/hash | Bị chặn theo policy enforce |
| BSB-14 | Clickjacking | Origin lạ nhúng trang | Bị chặn theo frame-ancestors |
| BSB-15 | COOP/COEP | Bật cross-origin isolation | Tài nguyên và opener tuân theo policy |
| BSB-16 | Permissions Policy | Iframe yêu cầu quyền không được cấp | API bị giới hạn |
| BSB-17 | Service worker | Scope ngoài phạm vi dự kiến | Registration hoặc kiểm soát bị giới hạn |
| BSB-18 | Secure context | HTTP gọi API chỉ dành cho secure context | Tính năng không được cấp như trên HTTPS |
| BSB-19 | Extension | Extension can thiệp DOM | Phân biệt với script của ứng dụng |
| BSB-20 | Process isolation | Nội dung cross-site | Không dựa vào process như authorization boundary |

Với mỗi ca, ghi browser/engine/version, URL nguồn và đích, trạng thái cookie, policy header, thao tác, kết quả kỳ vọng, kết quả thực tế và bằng chứng. Chạy trên profile sạch và ghi nhận cấu hình quyền riêng tư khi test storage hoặc cookie bên thứ ba.

## 13. Thực hành

Tạo lab với các origin do bạn kiểm soát:

- <code>https://app.example.test</code>: ứng dụng chính chứa marker riêng tư.
- <code>https://api.example.test</code>: API có CORS allowlist.
- <code>https://portal.example.test</code>: client được phép đọc một response.
- <code>https://attacker.test</code>: trang kiểm thử không tin cậy.
- <code>https://preview.example.test</code>: iframe sandbox chứa nội dung giả lập.

Dùng dữ liệu tổng hợp. Không sử dụng cookie, token hoặc tài khoản production.

### Phần A: Origin và SOP

Đặt marker trong DOM và localStorage của ứng dụng chính. Từ <code>attacker.test</code>, mở ứng dụng trong iframe và thử đọc marker. Xác nhận thao tác bị browser chặn. Lặp lại từ cùng origin để xác nhận fixture hoạt động.

Thử đổi scheme hoặc port để quan sát origin thay đổi. Ghi lại URL đầy đủ và kết quả.

### Phần B: CORS và CSRF

Cấu hình API chỉ cho <code>portal.example.test</code> đọc response. Xác nhận origin được allowlist đọc được response và origin không được allowlist không đọc được response.

Tạo một endpoint thay đổi trạng thái giả lập. Gửi request từ trang khác site và quan sát server. Xác nhận server yêu cầu CSRF token hoặc kiểm tra Origin theo thiết kế. Không kết luận rằng CORS đã chặn request chỉ vì JavaScript không đọc được response.

### Phần C: Cookie và storage

Đặt cookie host-only, cookie Domain và cookie HttpOnly trong lab. Quan sát request tới từng host. Thử đọc cookie qua <code>document.cookie</code> để xác nhận HttpOnly. Tạo marker localStorage ở origin chính và kiểm tra origin khác không đọc được.

Lặp lại trong iframe cross-site và profile có chính sách chặn third-party cookie nếu browser hỗ trợ. Ghi rõ khác biệt.

### Phần D: Iframe, CSP và clickjacking

Nhúng trang preview với sandbox chỉ cấp <code>allow-scripts</code>. Thử truy cập DOM từ trang cha và kiểm tra opaque origin. Gửi postMessage từ origin hợp lệ và origin không hợp lệ; listener chỉ xử lý đúng message.

Đặt <code>frame-ancestors 'self'</code> cho ứng dụng chính và thử nhúng từ <code>attacker.test</code>. Xác nhận nội dung bị chặn. Tạo một inline script không có nonce để xác minh CSP enforce.

### Phần E: Threat model

Vẽ sơ đồ các origin, cookie, storage, iframe và API. Đánh dấu nơi có thể đọc dữ liệu, nơi có thể gửi request và nơi cần authorization. Chọn ba rủi ro có tác động cao nhất và đề xuất biện pháp kiểm soát tương ứng.

Hoàn thiện bảng kết quả với các cột: ID, browser, origin nguồn/đích, boundary, hành động, kỳ vọng, thực tế, bằng chứng và kết luận. Xóa dữ liệu giả lập sau khi hoàn tất.

## 14. Ghi nhớ

- Browser security boundary gồm nhiều lớp: process sandbox, site isolation, origin, browsing context, cookie, storage và API permission.
- Process isolation là cơ chế triển khai của browser; không thay thế SOP hoặc authorization.
- Origin gồm scheme, host và port; site phục vụ các chính sách khác như SameSite.
- SOP giới hạn đọc dữ liệu cross-origin nhưng không chặn mọi request.
- CORS cho phép đọc response theo chính sách server; không thay thế xác thực, phân quyền hoặc CSRF protection.
- Cookie không được cô lập theo port; Domain, Path, Secure, HttpOnly và SameSite có vai trò khác nhau.
- Storage có thể được partition theo top-level site; cần kiểm thử browser và ngữ cảnh nhúng thực tế.
- Iframe sandbox cần quyền tối thiểu; postMessage phải kiểm tra origin, source và schema.
- CSP, Trusted Types, COOP, COEP, CORP, Permissions Policy và frame-ancestors kiểm soát các khía cạnh khác nhau của boundary.
- XSS có thể chạy trong quyền của origin bị ảnh hưởng; CSRF khai thác cách browser gửi cookie; clickjacking khai thác việc nhúng giao diện.
- HTTPS và secure context tạo điều kiện cho nhiều cơ chế bảo vệ nhưng không chứng minh ứng dụng an toàn.
- Threat model phải xác định tài sản, chủ thể, luồng dữ liệu, boundary và tác động nếu boundary bị vượt qua.
