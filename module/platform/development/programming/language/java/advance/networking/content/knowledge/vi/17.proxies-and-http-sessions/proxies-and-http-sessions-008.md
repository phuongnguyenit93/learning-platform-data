# Domain, Path, Secure và thời hạn sống của cookie

## 1. Tại sao cần hiểu các thuộc tính cookie trong Java networking?

**HTTP vốn không lưu trạng thái phiên giữa các request.** Server có thể gán một mã nhận diện phiên qua response **Set-Cookie**; những request tiếp theo của client sẽ kèm **Cookie** nếu cookie còn hiệu lực và phù hợp các điều kiện gửi. Nhờ đó, server tra cứu phiên đã đăng nhập, giỏ hàng hoặc lựa chọn của người dùng.

Tuy nhiên, một cookie **không được gửi tới mọi URL**. Khi quyết định gửi, user agent (trình duyệt hoặc HTTP client có cookie store) xem xét **host/Domain**, **Path**, **Secure**, **thời hạn sống**, và các chính sách khác như **SameSite** hoặc cookie partitioning.

Bài này tập trung vào bốn yếu tố được nêu trong đề:

- **Domain:** cookie thuộc đúng host tạo nó hay có thể được gửi tới các subdomain?
- **Path:** đường dẫn request nào phù hợp để gửi cookie?
- **Secure:** cookie chỉ được gửi trên kênh HTTPS an toàn hay không?
- **Thời hạn sống:** cookie là session cookie hay persistent cookie; **Max-Age** và **Expires** tương tác thế nào?

Đồng thời giải thích cách sử dụng **java.net.CookieManager, HttpCookie, CookieStore, CookiePolicy** trong **Java 17+**, các điểm Java khác trình duyệt hiện đại, và ảnh hưởng của **proxy** trong phiên HTTP.

**Nguyên tắc an toàn:** cookie chứa session ID là một **bearer credential**. Ai có giá trị session hợp lệ có thể bị server xem là chủ phiên đó. Không lưu mật khẩu hay dữ liệu nhạy cảm thô trong cookie; dùng session ID ngẫu nhiên đủ mạnh, TLS, cookie attributes, kiểm tra quyền và vòng đời session phía server.

## 2. Phân biệt Set-Cookie và Cookie

Server phát hành hoặc cập nhật cookie bằng **response header** Set-Cookie:

~~~http
HTTP/1.1 200 OK
Set-Cookie: session=abc123; Path=/account; Secure; HttpOnly; SameSite=Lax; Max-Age=1800
Set-Cookie: theme=dark; Path=/; Secure; Max-Age=2592000
Content-Type: text/plain

Welcome
~~~

Ở request tiếp theo, nếu phù hợp, client chỉ gửi cặp **tên=giá trị** trong **request header** Cookie:

~~~http
GET /account/profile HTTP/1.1
Host: shop.example.test
Cookie: session=abc123; theme=dark
~~~

Lưu ý:

1. **Domain, Path, Secure, Max-Age, Expires, HttpOnly, SameSite** là **thuộc tính trong Set-Cookie** nhằm hướng dẫn user agent lưu/gửi cookie; chúng **không được gửi lại như các thuộc tính trong Cookie header** chuẩn.
2. Mỗi cookie được phát hành qua một **Set-Cookie field riêng**. Không ghép nhiều Set-Cookie fields thành một field phân cách bằng dấu phẩy; đặc biệt Expires chứa dấu phẩy của định dạng HTTP-date.
3. Nếu request không phù hợp hoặc cookie đã hết hạn, client không đưa cookie đó vào Cookie header.
4. Server phải tự kiểm tra giá trị session có tồn tại, còn hiệu lực và có quyền làm hành động được yêu cầu. **Việc client gửi Cookie không có nghĩa session chắc chắn hợp lệ.**
5. Cookie là metadata ở tầng HTTP. **TCP connection, TLS session, HTTP/2 stream, proxy connection** và application login session là những khái niệm khác nhau; tái sử dụng connection không làm thay đổi thời hạn cookie.

## 3. Domain: host-only và domain cookie

### 3.1. Không có Domain: host-only cookie

Giả sử response HTTPS của **shop.example.test** có:

~~~http
Set-Cookie: cart=A1; Path=/; Secure; HttpOnly; Max-Age=900
~~~

Không có Domain nghĩa là cookie **host-only**, gắn với **shop.example.test** đã phát hành. Trình duyệt theo RFC 6265 gửi nó tới **shop.example.test** (nếu các điều kiện khác thỏa), nhưng **không** gửi tới:

- **api.example.test**: một subdomain cùng parent nhưng khác host.
- **a.shop.example.test**: subdomain bên dưới host ban đầu, không trùng exact host.
- **other.test**: host hoàn toàn khác.

Đây là mặc định an toàn nên dùng khi các host khác không cần chia sẻ cookie. Cũng cần nhớ cookie thường **không bị cách ly theo port** theo mô hình trình duyệt: khác port trên cùng host không tự tạo ranh giới cookie mạnh; Path và Scheme cũng cần xét.

### 3.2. Có Domain: cho phép cùng domain và subdomain

Response từ **shop.example.test**:

~~~http
Set-Cookie: sharedSession=B2; Domain=example.test; Path=/; Secure; HttpOnly; Max-Age=900
~~~

Theo cơ chế cookie trên trình duyệt hiện đại, Domain=example.test làm cookie có phạm vi **example.test** và các subdomain như **shop.example.test**, **api.example.test**. Domain phải có quan hệ hợp lệ với host phát hành; một server ở shop.example.test **không thể hợp lệ yêu cầu Domain=other.test**.

Dạng cũ **Domain=.example.test** có dấu chấm đầu được các trình duyệt hiện đại xử lý tương tự Domain=example.test; dấu chấm đầu **không còn mở rộng phạm vi thêm** theo RFC 6265. Tuy nhiên, **java.net.CookieManager** của Java dựa trên semantics RFC 2965 cũ nên có thể xử lý leading dot khác; xem phần Java riêng bên dưới.

**Sai lầm:** Domain=example.test không cho phép cookie gửi tới **notexample.test** hay **example.test.attacker.invalid**. Đó không phải domain/subdomain hợp lệ chỉ vì có chuỗi con example.test.

### 3.3. Không cho client đặt cookie ở public suffix

Trình duyệt thường dùng **Public Suffix List** để ngăn một site phát hành cookie cho một suffix được nhiều chủ thể độc lập sử dụng, chẳng hạn **Domain=com** hay một public suffix như **co.uk**. Không nên cho phép một tenant đặt cookie cho toàn bộ suffix dùng chung.

Với multi-tenant service, wildcard DNS không đồng nghĩa mọi tenant được quyền chia sẻ session. Cookie Domain quá rộng có thể dẫn đến **cookie tossing, session fixation hoặc xung đột tên** giữa subdomains.

**Cách làm nên chọn:** nếu không cần cross-subdomain, bỏ hẳn Domain. Nếu thật sự cần chia sẻ giữa những subdomain do tổ chức quản lý, đặt Domain hẹp nhất có thể và có thiết kế chống session fixation.

### 3.4. Domain không phải cơ chế xác thực

Một request có Cookie phù hợp Domain chỉ chứng minh client **gửi một giá trị**. Nó không chứng minh nội dung cookie thuộc user nào hoặc user đã được cấp quyền.

Server vẫn phải tra cứu session, kiểm tra expiry/revocation, quyền truy cập và chống CSRF theo threat model. Với dịch vụ dùng chung nhiều subdomain, cần cẩn trọng khi một subdomain kém tin cậy có thể cố tình set cookie có Domain rộng hơn.

## 4. Path: đường dẫn nào khớp và tại sao không phải biên giới bảo mật

### 4.1. Cookie có Path cụ thể

Giả sử:

~~~http
Set-Cookie: accountSession=X1; Path=/account; Secure; HttpOnly; Max-Age=900
~~~

Theo **RFC 6265 path-match** của trình duyệt, cookie này phù hợp với:

| URL request path | Gửi cookie có Path=/account? | Giải thích |
| --- | --- | --- |
| **/account** | Có | Trùng chính xác |
| **/account/** | Có | Path là prefix và dấu tiếp theo là / |
| **/account/orders** | Có | Path con của /account |
| **/accounting** | **Không** | Sau /account là ký tự i, không phải / |
| **/accounts** | **Không** | Khác path segment |
| **/** | Không | Không thuộc nhánh /account |
| **/help** | Không | Không thuộc nhánh /account |

Thuật toán RFC 6265 không chỉ là kiểm tra **startsWith("/account")**: request path phải bằng cookie path, hoặc nếu cookie path kết thúc bằng / thì prefix phù hợp, hoặc ký tự tiếp theo sau prefix phải là **/**. Tình huống **/accounting** là bài test rất hữu ích để phát hiện implementation path-match quá rộng.

### 4.2. Bỏ Path thì mặc định là gì?

Nếu một response đến từ URL:

~~~text
https://shop.example.test/docs/guide/page.html
~~~

và Set-Cookie **không có Path**, trình duyệt theo RFC 6265 thường chọn thư mục chứa resource, tức **/docs/guide/** làm default-path. Không được luôn mặc định cookie Path=/.

Các ví dụ:

| URL phát hành | Default Path theo RFC 6265 |
| --- | --- |
| **https://x.example.test/** | / |
| **https://x.example.test/login** | / |
| **https://x.example.test/docs/page.html** | /docs/ |
| **https://x.example.test/docs/guide/page.html** | /docs/guide/ |

Nếu ứng dụng cần cookie trên mọi path của host, nên **đặt Path=/** rõ ràng. Nếu chỉ cần dưới /account, đặt Path=/account để hạn chế cookie được đính kèm ở những endpoint không liên quan.

### 4.3. Path không phải security boundary

**Path chỉ là cơ chế lựa chọn gửi cookie**, không phải cơ chế cách ly bảo mật như process/container/origin. Các trang cùng host nhưng đường dẫn khác có thể tương tác theo cách khiến Path không bảo vệ bí mật như một authentication mechanism.

Ví dụ code JavaScript chạy trên một path có thể gửi request tới path khác cùng origin; cookie thuộc path đích có thể được trình duyệt đính kèm khi request hợp lệ. Vì thế **Path=/admin không thay kiểm tra quyền admin trên server**.

Cookie tên giống nhau nhưng khác Path có thể cùng tồn tại. Khi cả hai cùng phù hợp request, Cookie header có thể mang nhiều cặp trùng tên; **không thiết kế logic authentication dựa vào thứ tự chuỗi Cookie header**. Tránh trùng tên và dùng quy tắc scope rõ.

### 4.4. Điểm khác biệt quan trọng với java.net.CookieManager

Tài liệu Java 17 nêu **CookieManager/HttpCookie** gắn với **RFC 2965** và những quy tắc lịch sử, **không phải trình duyệt RFC 6265 hoàn chỉnh**. Vì vậy các chi tiết Domain/path match có thể khác browser; ví dụ một số implementation Java dùng prefix path rộng hơn và không tái hiện đúng trường hợp **/accounting** của RFC 6265.

**Đừng lấy một kết quả của CookieManager Java để khẳng định trình duyệt sẽ gửi cookie y hệt.** Để kiểm thử hành vi browser, dùng browser test đúng chính sách hiện đại và các case path segment, domain/public suffix.

## 5. Secure: chỉ gửi cookie qua HTTPS có xác thực

### 5.1. Ý nghĩa chính xác

~~~http
Set-Cookie: session=RANDOM_ID; Path=/; Secure; HttpOnly; Max-Age=900
~~~

**Secure** yêu cầu client chỉ gửi cookie qua kênh an toàn theo chính sách user agent, thông thường là **HTTPS**. Với cùng host/path:

| Request | Cookie có Secure có được gửi? |
| --- | --- |
| **https://shop.example.test/account** | Có, nếu Domain/Path/TTL và các điều kiện khác phù hợp |
| **http://shop.example.test/account** | Không |
| **https://api.example.test/account** | Chỉ khi Domain cho phép api.example.test |
| **https://shop.example.test/other** | Chỉ khi Path phù hợp |

Trình duyệt có **ngoại lệ đặc biệt cho localhost** trong một số ngữ cảnh; không thiết kế bảo mật production dựa vào ngoại lệ này. Secure không có nghĩa **cookie được mã hóa khi nằm trên ổ đĩa client**, cũng không tự làm nội dung cookie bí mật đối với JavaScript.

### 5.2. Secure khác HttpOnly và SameSite

| Thuộc tính | Bảo vệ chính | Không bảo vệ được điều gì một mình |
| --- | --- | --- |
| **Secure** | Hạn chế gửi cookie qua HTTP plaintext | Không ngăn JavaScript đọc cookie nếu không có HttpOnly |
| **HttpOnly** | Ngăn JavaScript thông thường truy cập qua document.cookie | Không ngăn request HTTP hợp lệ tự gửi cookie; không chặn mọi XSS hậu quả |
| **SameSite=Lax/Strict** | Giảm một số trường hợp cookie tự gửi trong cross-site request | Không thay toàn bộ biện pháp chống CSRF và authorization |
| **Domain/Path** | Giới hạn nơi cookie được gửi | Không thay ranh giới bảo mật độc lập |
| **Max-Age/Expires** | Giới hạn thời gian cookie tồn tại ở client | Không tự vô hiệu hóa session server đã bị lộ |

Với **SameSite=None**, trình duyệt hiện đại yêu cầu **Secure**. Với session cookie của web app, chính sách phổ biến là **Secure; HttpOnly; SameSite=Lax hoặc Strict** theo luồng nghiệp vụ, cộng thời hạn sống ngắn và kiểm tra CSRF ở server khi cần.

**HttpOnly không phải cờ dành cho response body:** nó là thuộc tính của Set-Cookie. Khi JavaScript gửi fetch đến một endpoint phù hợp và credential policy cho phép, browser vẫn có thể kèm HttpOnly cookie trong HTTP request dù script không đọc được giá trị qua document.cookie.

### 5.3. Prefix tăng tính ràng buộc trong browser hỗ trợ

Các tên cookie có prefix hỗ trợ kiểm soát thêm:

~~~http
Set-Cookie: __Secure-session=A1; Path=/; Secure; HttpOnly; SameSite=Lax
Set-Cookie: __Host-session=B2; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

- **__Secure-**: cần được set từ secure origin và có Secure.
- **__Host-**: cần secure origin, có **Secure**, **Path=/** và **không có Domain**. Phù hợp khi cookie chỉ dành cho đúng host và không muốn subdomain khác set cookie cùng phạm vi.
- Các quy tắc prefix do **user agent hỗ trợ prefix** thực thi; **không giả định Java HttpCookie/CookieManager cũ tự kiểm tra toàn bộ prefix, SameSite và cookie partitioning** như browser đời mới.

Prefix là một lớp phòng thủ bổ sung. Backend vẫn phải xác minh session ID và chống session fixation.

## 6. Thời hạn sống: session, Max-Age, Expires và xóa cookie

### 6.1. Session cookie: không có Max-Age/Expires

~~~http
Set-Cookie: session=abc; Path=/; Secure; HttpOnly
~~~

Theo cookie model browser, đây là **session cookie**, thường bị loại khi phiên trình duyệt kết thúc. Tuy nhiên nhiều browser có **session restore**, có thể phục hồi cả session cookies sau khi mở lại. **Không giả định đóng tab/browser là thao tác logout bảo mật**; server cần expiration và revoke session riêng.

Trong Java HttpCookie, **getMaxAge() mặc định -1** biểu thị session-style cookie. CookieStore in-memory mặc định của CookieManager **không bền qua việc JVM kết thúc**, nhưng điều này khác cơ chế session-restore của browser.

### 6.2. Max-Age là thời hạn tương đối, đơn vị giây

~~~http
Set-Cookie: cart=abc; Path=/; Max-Age=1800; Secure
~~~

**Max-Age=1800** nghĩa là cookie có thời hạn tối đa 1.800 giây (30 phút) kể từ lúc được user agent nhận/xử lý theo policy. Không hiểu đây là milliseconds hoặc một timestamp Unix.

**Max-Age=0** hoặc một số âm theo RFC/browser tương đương hết hạn ngay, thường dùng để xóa cookie:

~~~http
Set-Cookie: cart=; Path=/; Max-Age=0; Secure
~~~

Với Java HttpCookie, **setMaxAge(0)** và **hasExpired()** giúp mô tả cùng ý nghĩa loại bỏ; giá trị âm -1 biểu thị session cookie khi xây đối tượng. Đừng suy diễn rằng một negative Max-Age trong cú pháp header có hiệu quả hoàn toàn giống mọi browser; cần kiểm tra user agent cụ thể.

### 6.3. Expires là thời điểm tuyệt đối

~~~http
Set-Cookie: cart=abc; Path=/; Expires=Wed, 21 Oct 2037 07:28:00 GMT; Secure
~~~

**Expires** là HTTP-date UTC/GMT. Cookie hết hiệu lực sau thời điểm đó theo đồng hồ/policy của client. Nếu server và client sai lệch thời gian, việc diễn giải ngày hết hạn có thể khó dự đoán; browser hiện đại có thể điều chỉnh clock skew dựa trên Date response header.

**Max-Age thường dễ quản lý hơn** khi muốn diễn đạt “tồn tại tối đa N giây”, nhưng backend cũng phải có TTL cho session tương ứng. Không dựa duy nhất vào cookie expiration để vô hiệu hóa token bị đánh cắp.

### 6.4. Nếu cùng có Max-Age và Expires?

~~~http
Set-Cookie: cart=abc; Path=/; Max-Age=3600; Expires=Wed, 21 Oct 2037 07:28:00 GMT; Secure
~~~

Theo RFC 6265, **Max-Age có quyền ưu tiên** so với Expires nếu cả hai hợp lệ. Trong ví dụ, thời hạn người học nên tính theo **3.600 giây** thay vì ngày năm 2037.

Điều này cũng giải thích tại sao một certificate TLS expiry, HTTP cache freshness, cookie Max-Age và session database TTL là **bốn giới hạn thời gian khác nhau**, không nên gom chúng thành “session timeout” chung.

### 6.5. Xóa đúng cookie phải khớp identity

Nếu cookie được lưu với **name=session**, **Domain=example.test** và **Path=/account**, một response xóa nên dùng lại **đúng tên, Domain và Path** của cookie đó:

~~~http
Set-Cookie: session=; Domain=example.test; Path=/account; Max-Age=0; Secure; HttpOnly
~~~

Nếu khi tạo **bỏ Domain** (host-only), khi xóa cũng thường bỏ Domain và gửi từ đúng host. Nếu cookie khác tên giống nhau nhưng Path khác, xóa Path=/ chưa chắc xóa cookie Path=/account. Cookie partitioned có thể cần xét partition key nữa; cần test với user agent thực tế.

**Logout an toàn có hai phần:** (1) đánh dấu session/token phía server hết hiệu lực hoặc revoke, (2) gửi Set-Cookie xóa giá trị phía client. Chỉ xóa cookie client không đủ nếu một bản sao token đã bị lộ vẫn còn hiệu lực trên server.

### 6.6. Absolute TTL và idle timeout

Ví dụ security policy yêu cầu session hết hiệu lực sau 30 phút **không hoạt động**, và không quá 8 giờ kể từ đăng nhập. Cookie Max-Age=1800 có thể hỗ trợ biểu diễn idle period nếu server chủ động refresh cookie, nhưng backend vẫn phải theo dõi:

- **Created-at** / thời điểm đăng nhập.
- **Last activity** / lần tương tác hợp lệ gần nhất.
- **Absolute expiration** / tuổi tối đa.
- **Revoked** / logout, đổi mật khẩu, security event.

Đừng tự kéo dài vô hạn session chỉ bằng cách liên tục gửi Set-Cookie Max-Age mới nếu chính sách có absolute expiration.

## 7. Ma trận Domain × Path × Secure × thời hạn

Giả sử HTTPS response từ **shop.example.test** phát hành các cookie sau:

~~~http
Set-Cookie: hostLogin=H; Path=/account; Secure; HttpOnly; Max-Age=900
Set-Cookie: shared=S; Domain=example.test; Path=/; Secure; Max-Age=3600
Set-Cookie: theme=dark; Path=/; Secure; Max-Age=86400
Set-Cookie: obsolete=; Path=/account; Max-Age=0
~~~

**Các kết quả dưới đây theo quy tắc cookie trình duyệt RFC 6265**, giả sử mọi cookie chưa hết hạn trừ obsolete, cùng-site/security policy không chặn thêm và domain phát hành hợp lệ:

| Request URL | Cookie phù hợp | Vì sao |
| --- | --- | --- |
| **https://shop.example.test/account/profile** | hostLogin, shared, theme | Trùng host, path /account, HTTPS, còn hạn |
| **https://shop.example.test/** | shared, theme | hostLogin chỉ có Path=/account |
| **https://shop.example.test/accounting** | shared, theme | /accounting **không** path-match /account theo RFC 6265 |
| **https://api.example.test/account/profile** | shared | shared có Domain=example.test; hai cookie kia host-only |
| **http://shop.example.test/account/profile** | Không cookie nào | Cả ba cookie còn sống đều Secure, không gửi qua HTTP |
| **https://unrelated.test/account/profile** | Không cookie nào | Khác domain |
| **https://shop.example.test/account/profile** sau khi cả ba TTL hết | Không cookie nào | Hết hạn |
| **https://shop.example.test/account/profile** ngay sau response | Không có obsolete | Max-Age=0 xóa ngay |

Điểm dễ nhầm: trong Java CookieManager nội bộ, **Path** có thể được xử lý theo RFC 2965 và **Domain** theo logic lịch sử, vì vậy không dùng bảng browser này làm expected output cứng của Java CookieManager. Phần demo dưới đây kiểm thử những trường hợp được Java runtime thực tế hỗ trợ và nêu rõ điều kiện.

### Đọc một dòng request đúng cách

Để quyết định gửi một cookie, client cần kiểm tra tuần tự:

1. **Cookie có hết hạn hoặc bị xóa không?** Nếu có, bỏ.
2. **Host có phù hợp host-only/Domain không?** Nếu không, bỏ.
3. **Request path có path-match Path không?** Nếu không, bỏ.
4. **Secure có yêu cầu HTTPS không?** Nếu yêu cầu mà request không an toàn, bỏ.
5. **SameSite/partitioning/browser policy** có cho request hiện tại mang cookie không? Nếu không, bỏ.
6. Nếu còn phù hợp, đặt **name=value** vào Cookie request header; **không** lặp các Set-Cookie attributes trong header đó.

Đây là mô hình tư duy, thứ tự kiểm tra nội bộ cụ thể có thể khác theo user agent và không bảo đảm mọi implementation có cùng chính sách.

## 8. Java 17: HttpCookie, CookieManager, CookieStore và CookiePolicy

### 8.1. Các thành phần và trách nhiệm

| API | Vai trò |
| --- | --- |
| **java.net.HttpCookie** | Đối tượng lưu name/value, Domain, Path, Secure, HttpOnly, Max-Age; parse Set-Cookie theo các định dạng Java hỗ trợ |
| **java.net.CookieManager** | Thực hiện CookieHandler.get/put, chọn cookie để gửi và chấp nhận cookie server phát hành |
| **java.net.CookieStore** | Nơi lưu các cookie được chấp nhận; implementation mặc định của CookieManager là in-memory |
| **java.net.CookiePolicy** | Quy tắc quyết định cookie nào được nhận, ví dụ ACCEPT_ORIGINAL_SERVER, ACCEPT_NONE, ACCEPT_ALL |
| **java.net.CookieHandler** | Trừu tượng hóa Cookie management, có thể dùng làm handler mặc định toàn JVM hoặc cấu hình riêng cho client |
| **java.net.http.HttpClient.Builder.cookieHandler(...)** | Gắn CookieHandler cho HttpClient để quản lý cookie HTTP tự động |

**CookieManager không phải web browser engine hiện đại.** API Java 17 có nguồn gốc Netscape/RFC 2109/RFC 2965 và không cam kết tái hiện mọi chính sách browser RFC 6265, SameSite, Partitioned, cookie prefixes hay Public Suffix List. Điều này đặc biệt quan trọng khi dùng Java HTTP client để test hệ thống web.

### 8.2. Tạo CookieManager có phạm vi riêng

~~~java
// Snippet Java 17: manager sống cùng một HttpClient.
CookieManager cookieManager =
        new CookieManager(null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);

HttpClient client = HttpClient.newBuilder()
        .cookieHandler(cookieManager)
        .build();
~~~

Ở đây **null CookieStore** yêu cầu Java dùng store in-memory mặc định; policy ACCEPT_ORIGINAL_SERVER chỉ nhận những cookie phù hợp origin theo quy tắc của implementation. Đây là hướng tốt cho client riêng biệt, tránh trạng thái cookie toàn JVM vô ý bị chia sẻ giữa các tác vụ.

**Không dùng ACCEPT_ALL cho dữ liệu không tin cậy chỉ để cookie “hoạt động”.** ACCEPT_ALL nới chính sách chấp nhận cookie. Nếu cần chính xác hơn, viết CookiePolicy/CookieStore tùy chỉnh và kiểm thử theo threat model.

### 8.3. Tránh cấu hình CookieHandler toàn JVM khi không cần

**CookieHandler.setDefault(manager)** thiết lập handler mặc định dùng chung trong JVM. Nó có thể ảnh hưởng đến code khác, tạo rủi ro trộn session giữa các thành phần hoặc test chạy song song. Nếu dùng **java.net.http.HttpClient**, nên cấu hình **cookieHandler(manager)** trên từng client/đối tượng lifetime thích hợp, không đặt global trừ khi kiến trúc yêu cầu.

### 8.4. Một khác biệt đáng lưu ý về Domain trong Java

Trong trình duyệt RFC 6265, **Domain=example.test** và **Domain=.example.test** có phạm vi như nhau. Nhưng **HttpCookie.domainMatches(...)** và **CookieManager** trong Java có logic RFC 2965 cũ; một số implementation có thể không chấp nhận **Domain=example.test** theo cách trình duyệt chấp nhận đối với source host **shop.example.test**. Trong **ví dụ Java đã kiểm thử**, dùng **Domain=.example.test** để minh họa chia sẻ cookie giữa subdomains theo implementation đó.

Đó là **quy ước của ví dụ Java**, không phải khuyến nghị server web luôn thêm dấu chấm trước Domain. Khi xây backend phục vụ browser, phát hành Domain theo chuẩn trình duyệt và thử trên browser thực; khi xây Java client, xác minh hành vi CookieManager của JDK đang chạy.

### 8.5. Không dùng CookieStore.getCookies để khẳng định header thực tế

**CookieStore.getCookies()** trả tập cookie trong store, **không đồng nghĩa** chúng đều được gửi tới một request cụ thể. Muốn xem Cookie headers dự kiến cho URI trong Java, dùng **CookieManager.get(requestURI, requestHeaders)**. Manager thực hiện thêm chọn lọc theo host/path/secure.

Ngược lại, **CookieManager.put(responseURI, responseHeaders)** mô phỏng/nhận response Set-Cookie và cập nhật store theo policy. Có thể dùng hai method này để kiểm thử offline mà không gửi request thật.

## 9. Ví dụ Java 17 chạy được: kiểm thử host, subdomain, path, Secure và tuổi cookie

Ví dụ **CookieScopeAudit.java** không dùng mạng và không yêu cầu server thật. Nó tạo **CookieManager + CookiePolicy.ACCEPT_ORIGINAL_SERVER**, giả lập nhận bốn Set-Cookie headers từ **https://shop.example.test/account/login**, rồi hỏi CookieManager cookie nào sẽ được chọn khi URI khác nhau.

Bốn cookie:

- **hostOnly=H; Path=/account; HttpOnly; Max-Age=120**: không có Domain, vì vậy dành cho host phát hành trong ví dụ Java; cố tình **không gắn Secure** để có thể quan sát khác biệt khi chuyển HTTP.
- **shared=W; Domain=.example.test; Path=/; Max-Age=120**: dùng leading dot cho Java CookieManager trong test này; trình duyệt hiện đại không yêu cầu dấu chấm đó.
- **secureOnly=S; Path=/account; Secure; HttpOnly; Max-Age=120**: cùng path nhưng chỉ được Java manager chọn cho HTTPS.
- **obsolete=x; Path=/account; Max-Age=0**: hết hạn ngay và không tồn tại trong cookie store cuối.

**Bảo mật:** việc có hostOnly cookie không Secure là **cấu hình thử nghiệm để minh họa**, không phải mẫu session cookie production. Với session/token thật, dùng **Secure, HttpOnly, SameSite phù hợp, HTTPS** và TTL theo chính sách. Các URI .test dùng để minh họa logic, **không có network request**.

### Tệp CookieScopeAudit.java

~~~java
import java.io.IOException;
import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.HttpCookie;
import java.net.URI;
import java.net.http.HttpClient;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

public class CookieScopeAudit {
    static void assertNames(
            CookieManager manager, String label,
            String url, String... expectedNames) throws IOException {
        Set<String> actual = new TreeSet<>();
        List<String> headers = manager.get(
                URI.create(url), Map.of())
                .getOrDefault("Cookie", List.of());

        for (String header : headers) {
            int equals = header.indexOf('=');
            if (equals > 0 && !header.startsWith("$")) {
                actual.add(header.substring(0, equals));
            }
        }

        Set<String> expected = new TreeSet<>(
                Arrays.asList(expectedNames));
        if (!actual.equals(expected)) {
            throw new AssertionError(
                    label + " expected=" + expected +
                    " actual=" + actual);
        }
        System.out.println(label + ": " +
                (actual.isEmpty() ? "(none)" :
                        String.join(",", actual)));
    }

    public static void main(String[] args) throws Exception {
        CookieManager manager = new CookieManager(
                null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);
        URI origin = URI.create(
                "https://shop.example.test/account/login");

        manager.put(origin, Map.of("Set-Cookie", List.of(
                "hostOnly=H; Path=/account; HttpOnly; Max-Age=120",
                "shared=W; Domain=.example.test; Path=/; Max-Age=120",
                "secureOnly=S; Path=/account; Secure; HttpOnly; Max-Age=120",
                "obsolete=x; Path=/account; Max-Age=0"
        )));

        assertNames(manager, "HTTPS /account",
                "https://shop.example.test/account/orders",
                "hostOnly", "secureOnly", "shared");
        assertNames(manager, "HTTP /account",
                "http://shop.example.test/account/orders",
                "hostOnly", "shared");
        assertNames(manager, "HTTPS /public",
                "https://shop.example.test/public",
                "shared");
        assertNames(manager, "HTTPS sibling",
                "https://api.example.test/",
                "shared");
        assertNames(manager, "HTTPS unrelated",
                "https://unrelated.test/", new String[0]);

        boolean obsoleteInStore = manager.getCookieStore().getCookies()
                .stream().anyMatch(c -> "obsolete".equals(c.getName()));
        if (obsoleteInStore) {
            throw new AssertionError("Max-Age=0 cookie persisted");
        }
        System.out.println(
                "Max-Age=0 stored: " + obsoleteInStore);

        HttpCookie session = HttpCookie.parse(
                "session=transient; Path=/").get(0);
        HttpCookie deleted = HttpCookie.parse(
                "deleted=x; Max-Age=0").get(0);
        System.out.println("Session Max-Age: " +
                session.getMaxAge());
        System.out.println("Max-Age=0 expired: " +
                deleted.hasExpired());

        HttpClient client = HttpClient.newBuilder()
                .cookieHandler(manager)
                .build();
        System.out.println(
                "HttpClient CookieHandler configured: " +
                client.cookieHandler().isPresent());
        System.out.println("No network request performed");
    }
}
~~~

### Biên dịch và chạy

Tạo tệp đúng tên **CookieScopeAudit.java**, sử dụng **JDK 17 hoặc mới hơn**:

~~~bash
javac --release 17 -encoding UTF-8 CookieScopeAudit.java
java CookieScopeAudit
~~~

**Stdout chính xác từ lần biên dịch --release 17 và chạy thành công trên OpenJDK 24.0.2:**

~~~text
HTTPS /account: hostOnly,secureOnly,shared
HTTP /account: hostOnly,shared
HTTPS /public: shared
HTTPS sibling: shared
HTTPS unrelated: (none)
Max-Age=0 stored: false
Session Max-Age: -1
Max-Age=0 expired: true
HttpClient CookieHandler configured: true
No network request performed
~~~

**Giải thích từng dòng:**

1. **HTTPS /account:** path đúng, Secure cho phép HTTPS, domain hợp lệ nên cả hostOnly, secureOnly và shared được chọn.
2. **HTTP /account:** secureOnly biến mất vì cookie Secure không được gửi cho HTTP; hostOnly và shared vẫn xuất hiện **chỉ vì ví dụ chủ động không gắn Secure cho chúng**.
3. **HTTPS /public:** hostOnly và secureOnly có Path=/account nên không được gửi; shared có Path=/ và domain phù hợp.
4. **HTTPS sibling:** chỉ cookie có Domain=.example.test được chọn cho **api.example.test**; cookie còn lại host-only shop.example.test.
5. **HTTPS unrelated:** không cookie nào có domain tương ứng unrelated.test.
6. **Max-Age=0 stored: false:** cookie obsolete không còn trong CookieStore cuối; mô phỏng hết hạn/xóa ngay.
7. **Session Max-Age: -1:** object HttpCookie mới không có Max-Age là session-style theo Java API.
8. **Max-Age=0 expired: true:** HttpCookie xác định thời hạn bằng 0 là hết hạn.
9. **HttpClient CookieHandler configured: true:** client được gắn manager, nhưng **không gửi request thật**.
10. **No network request performed:** toàn bộ URI ở trên chỉ dùng để kiểm tra selection logic.

**Tại sao assertNames không so sánh nguyên Cookie header?** Java CookieManager có thể đưa vào các thành phần kiểu RFC 2965 như **$Version, $Path, $Domain** và thứ tự cookie có thể không cố định. Hàm helper lấy tên cookie từ danh sách header values, sort bằng TreeSet, rồi so sánh tập tên dự kiến; **không biến thứ tự/format của một implementation thành tiêu chí học sai**.

**Đừng thay URL .test bằng một website thực rồi chạy test này với thông tin đăng nhập thật.** Chương trình không cần Internet, không trao đổi token, và chỉ chứng minh semantics của Java CookieManager ở môi trường test. Nó không kiểm chứng cookie browser SameSite, prefix, partitioning hay public-suffix policy.

## 10. Proxy, redirect và phiên HTTP: những chỗ cookie dễ bị sai

### 10.1. Proxy được chọn không có nghĩa cookie thuộc proxy

Giả sử ứng dụng gửi **https://shop.example.test/account** qua một HTTP forward proxy. Cookie scope vẫn phải gắn với **origin của request** mà client yêu cầu, **không gắn với hostname của proxy**.

~~~text
Java HttpClient
  |
  | Request URI = https://shop.example.test/account
  | Cookie selection: shop.example.test + /account + HTTPS + TTL
  v
HTTP proxy hoặc tunnel
  |
  v
Origin shop.example.test
~~~

CookieManager được cấp **request URI/response URI** tương ứng để quyết định cookie theo policy. Không tạo cookie Domain=proxy.corp.test chỉ vì socket TCP nối tới proxy đó.

### 10.2. TLS termination và Secure

Một reverse proxy/ingress có thể nhận **HTTPS** từ trình duyệt rồi chuyển request nội bộ tới backend bằng **HTTP**. Nếu backend suy luận sai từ kết nối nội bộ và phát hành session cookie **không có Secure**, cookie có thể bị gửi qua HTTP trong những request khác.

**Cách sửa:** cấu hình ứng dụng/server để phát hành cookie bảo mật theo **external HTTPS origin** và trust đúng proxy. Các forwarded headers như **Forwarded** hay **X-Forwarded-Proto** chỉ nên được chấp nhận từ **proxy đáng tin**, không tin giá trị do client Internet tùy ý gửi.

Không bỏ Secure chỉ vì backend nhận request HTTP sau TLS termination; bảo mật session nhìn từ user agent.

### 10.3. Proxy có thể sửa Set-Cookie hoặc thay host/path

Một gateway có thể rewrite **Domain**, **Path**, **Location** khi route nhiều backend. Nếu proxy đổi public URL từ **/app/** sang backend **/**, cookie **Path=/** hoặc **Path=/app** có thể làm kết quả gửi cookie khác với ý định.

Khi xảy ra “login thành công nhưng request sau mất session”, ghi lại:

- URL public trước/sau redirect.
- Response Set-Cookie thực sự client nhận (đã che token).
- Domain/Path/Secure/Max-Age/Expires của cookie.
- Host và scheme của request tiếp theo.
- Cookie request header có được gửi hay không (che token).
- Chính sách browser SameSite/third-party cookie hoặc Java CookieManager.

**Tránh log nguyên session ID.** Cookie là bearer credential; log đầy đủ có thể tạo điểm rò rỉ phiên.

### 10.4. Redirect và đổi hostname

Một flow đăng nhập có thể chuyển từ **login.example.test** sang **shop.example.test**:

- Cookie **host-only** từ login.example.test sẽ **không** tự đi theo sang shop.example.test.
- Cookie có Domain=example.test có thể dùng ở cả hai host nếu hợp lệ, nhưng tăng phạm vi chia sẻ và rủi ro session fixation.
- Cookie **Secure** yêu cầu đường an toàn; chuyển sang HTTP có thể khiến cookie không được gửi.
- Nếu redirect đổi path ra ngoài Path đã đặt, cookie sẽ không đi theo.
- **Max-Age** vẫn tính từ lần set cookie, không tự reset sau một HTTP redirect.

Giải pháp hợp lý có thể là luồng authentication trao đổi token/session qua server hoặc redirect bảo mật, **không phải luôn mở rộng Domain cho mọi subdomain**.

## 11. Những lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| **Bỏ Domain rồi nghĩ cookie gửi tới tất cả subdomain** | Sibling service không nhận session | Thiết kế host-only hoặc shared Domain có chủ đích |
| **Đặt Domain quá rộng** | Tăng khả năng cookie tossing/session fixation | Bỏ Domain khi có thể, dùng scope hẹp nhất |
| **Nhầm Domain với URL đầy đủ có port/path** | Cookie bị từ chối hoặc scope sai | Domain chỉ là DNS domain, không có scheme/port/path |
| **Path=/account được coi là match /accounting** | Gửi cookie nhiều hơn browser RFC cho phép | Test đúng RFC 6265 path segment |
| **Bỏ Path nhưng mặc định nó là /** | Cookie không đi tới URL khác thư mục | Hiểu default-path hoặc đặt Path rõ ràng |
| **Tin Path như ranh giới phân quyền** | Lộ dữ liệu vì server không kiểm tra quyền | Luôn kiểm tra authorization ở backend |
| **Thiếu Secure với session** | Cookie có thể đi qua HTTP | Phát hành Secure trên HTTPS, cấu hình TLS termination đúng |
| **Nhầm Secure với HttpOnly** | JS vẫn có thể đọc cookie không HttpOnly | Dùng cả Secure và HttpOnly nếu phù hợp |
| **Nhầm Max-Age là milliseconds** | Thời hạn cookie sai 1.000 lần | Max-Age là giây |
| **Có cả Max-Age và Expires rồi chọn Expires** | Thời hạn khác kỳ vọng | RFC 6265 ưu tiên Max-Age |
| **Xóa sai Domain/Path** | Cookie cũ vẫn được gửi | Xóa với đúng tên và scope ban đầu |
| **Logout chỉ xóa client cookie** | Token đã bị sao chép vẫn còn hiệu lực | Revoke/expire session phía server |
| **Dùng CookieManager nhưng quên gắn vào HttpClient** | HTTP client không tự lưu/gửi cookie | Builder.cookieHandler(manager) |
| **Dùng CookieStore.getCookies để kết luận cookie được gửi** | Không xét đường request cụ thể | Dùng CookieManager.get(requestURI, headers) |
| **Dùng Java CookieManager làm oracle browser SameSite** | Test cho kết luận sai về browser | Test browser với RFC6265/SameSite policy riêng |
| **Bật CookieHandler.setDefault cho test không cô lập** | Trộn phiên của các client khác | Manager riêng per HttpClient/test scope |
| **Kết nối qua proxy nên gán Domain bằng tên proxy** | Sai scope session | Luôn dựa trên origin URI |
| **Reverse proxy HTTPS nhưng backend quên Secure** | Cookie bảo mật bị phát hành thiếu | Chính sách cookie gắn external scheme đáng tin |
| **Log Cookie header nguyên văn** | Rò rỉ bearer session ID | Redact, chỉ log tên/scope và ID điều tra |
| **Không đặt server-side session TTL** | Cookie đã hết hạn nhưng token bị lộ vẫn dùng được | Có idle/absolute TTL và revocation ở server |

## 12. Bộ test nên có cho hệ thống thực

### Test scope theo host

1. Phát hành cookie không Domain từ **shop.example.test**.
2. Request **shop.example.test** có thể nhận cookie.
3. Request **api.example.test** không nhận host-only cookie.
4. Nếu có Domain=example.test, kiểm tra root và những subdomain được phép; request tới host độc lập **không** nhận.
5. Kiểm tra user agent từ chối Domain không thuộc quyền phát hành và public suffix.

### Test scope theo path

1. Path=/account phải match **/account**.
2. Phải match **/account/orders**.
3. **Không** match **/accounting** theo RFC6265 browser.
4. Bỏ Path từ URL **/docs/page.html** phải cho default-path **/docs/**.
5. Test cookies trùng tên khác Path, không dựa vào thứ tự trên wire.

### Test Secure và các cờ khác

1. Secure cookie từ HTTPS phải được gửi tới URI HTTPS hợp lệ.
2. Cùng URI host/path nhưng HTTP plaintext không nhận Secure cookie.
3. Session cookie HttpOnly không đọc được qua document.cookie của browser, nhưng được browser gửi trong HTTP request phù hợp.
4. SameSite/CSRF test có case cross-site request và luồng OAuth/redirect nếu ứng dụng dùng.
5. Nếu dùng prefix __Host-, xác minh cookie luôn có Secure, Path=/ và không có Domain.
6. Reverse proxy/TLS termination phải không làm mất Secure flag.

### Test thời hạn sống

1. Max-Age=2 hết hạn sau vài giây trong môi trường test có kiểm soát; tránh test sleep quá ngắn gây flakiness.
2. Max-Age=0 xóa ngay.
3. Cùng có Expires xa và Max-Age gần: browser ưu tiên Max-Age.
4. Xóa cookie sai Path không xóa bản đúng Path.
5. Logout phải revoke phiên backend.
6. Tắt/mở trình duyệt có thể gặp session restore; không lấy đóng browser làm cơ chế revoke chắc chắn.

### Test Java riêng

1. Dùng **CookieManager.get(uri, headers)** để kiểm tra selection thay vì chỉ xem getCookieStore().getCookies().
2. Test **Domain=.example.test** trong implementation JDK đang chạy và đối chiếu khác biệt browser Domain=example.test.
3. Test **Path=/account** so với **/accounting** bằng Java và browser riêng, không giả định kết quả giống nhau.
4. Test **CookiePolicy.ACCEPT_ORIGINAL_SERVER** so với policy tùy chỉnh nếu cần.
5. Test **HttpClient** được gắn cookieHandler, không trộn cookie manager giữa các tenant/user.
6. Test expire/replacement giữa nhiều Set-Cookie response và hành vi redirect qua các host khác nhau.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Cookie không có Domain phát hành từ shop.example.test có đi tới api.example.test không?  
**Trả lời:** Không trong browser RFC 6265: đó là host-only cookie, yêu cầu exact host.

**Câu 2.** Domain=example.test và Domain=.example.test có khác trong browser hiện đại không?  
**Trả lời:** Không về phạm vi: dấu chấm đầu bị bỏ qua theo RFC 6265. Nhưng Java CookieManager có thể xử lý khác vì nền tảng RFC 2965.

**Câu 3.** Domain=example.test có cho cookie gửi tới fakeexample.test không?  
**Trả lời:** Không. Cần domain-match hợp lệ, không chỉ chứa chuỗi con.

**Câu 4.** Path=/account có gửi tới /accounting trong browser theo RFC6265 không?  
**Trả lời:** Không, vì path segment không khớp; sau /account không phải dấu /.

**Câu 5.** Cookie không có Path từ /docs/page.html có mặc định Path=/ không?  
**Trả lời:** Không. Default-path thường là /docs/.

**Câu 6.** Cookie có Secure có thể gửi qua HTTP plaintext từ đúng host/path không?  
**Trả lời:** Không trong điều kiện thông thường; Secure hạn chế gửi qua kênh không an toàn. Browser có ngoại lệ localhost khi thử nghiệm.

**Câu 7.** Secure có ngăn JavaScript đọc cookie không?  
**Trả lời:** Không. HttpOnly mới chặn document.cookie thông thường, và nó không thay XSS defenses khác.

**Câu 8.** Cookie không có Max-Age và Expires là cookie gì?  
**Trả lời:** Session cookie theo browser model; nhưng session restore có thể giữ nó lâu hơn mong đợi, nên cần server-side TTL.

**Câu 9.** Max-Age=1800 tính theo gì?  
**Trả lời:** 1.800 giây = 30 phút, không phải milliseconds.

**Câu 10.** Cùng có Max-Age và Expires thì trình duyệt ưu tiên cái nào?  
**Trả lời:** Max-Age.

**Câu 11.** Logout chỉ set Max-Age=0 ở client có đủ vô hiệu hóa token đã bị lộ?  
**Trả lời:** Không. Server phải revoke/expire session/token tương ứng.

**Câu 12.** CookieManager Java mặc định lưu cookie bền qua JVM restart không?  
**Trả lời:** Không. Store mặc định là in-memory; nếu cần persistence phải chọn/triển khai CookieStore thích hợp.

**Câu 13.** CookieStore.getCookies() có cho biết cookie nào sẽ đi theo một URL cụ thể không?  
**Trả lời:** Không đầy đủ. Sử dụng CookieManager.get(requestURI, headers) để áp selection policy cho URI.

**Câu 14.** Tại sao một request qua proxy vẫn phải dùng Domain của origin thay vì proxy?  
**Trả lời:** Cookie thuộc HTTP origin được truy cập, không thuộc host cung cấp proxy transport.

**Câu 15.** Phát hành cookie Path=/admin có thay kiểm tra authorization cho /admin không?  
**Trả lời:** Không. Path không phải hàng rào bảo mật; backend phải xác minh session và quyền ở mỗi request.

## Kết luận

Bốn thuộc tính **Domain, Path, Secure, Max-Age/Expires** quyết định **cookie có được lưu và gửi trên một HTTP request hay không**. Domain điều khiển host/subdomain, Path điều khiển URL path, Secure giới hạn kênh truyền, còn Max-Age/Expires xác định thời hạn ở client. Chúng không thay **xác thực/ủy quyền, chống CSRF và session revocation ở server**.

Với Java 17, **CookieManager, CookieStore, HttpCookie và HttpClient.cookieHandler(...)** giúp quản lý cookie trong HTTP client. Nhưng Java CookieManager có nguồn gốc RFC 2965 và **không phải chuẩn đối chiếu đầy đủ cho browser RFC 6265/SameSite hiện đại**. Khi debug, phải biết mình kiểm thử **Java user agent** hay **web browser**, và kiểm tra Cookie header dự kiến cho **đúng origin URI**, ngay cả khi đi qua proxy hoặc reverse proxy.

### Tài liệu tham khảo

- [RFC 6265 — HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265): Domain, Path, host-only, Secure, Expires và Max-Age.
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): syntax, Domain/Path/Secure, HttpOnly, SameSite và cookie prefixes.
- [MDN — Using HTTP cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies): cookie lifecycle, security, browser policy.
- [MDN — Secure cookie configuration](https://developer.mozilla.org/en-US/docs/Web/Security/Practical_implementation_guides/Cookies): security defaults cho session cookies.
- [Java SE 17 — CookieManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/CookieManager.html): cookie handling, policies và RFC 2965.
- [Java SE 17 — HttpCookie](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpCookie.html): Domain, Path, Secure, HttpOnly và Max-Age API.
- [Java SE 17 — CookiePolicy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/CookiePolicy.html): ACCEPT_ORIGINAL_SERVER, ACCEPT_ALL, ACCEPT_NONE.
- [Java SE 17 — CookieStore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/CookieStore.html): lưu trữ và truy xuất cookie.
- [Java SE 17 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): cookieHandler(CookieHandler).
- [Oracle Java Tutorials — Default CookieManager](https://docs.oracle.com/javase/tutorial/networking/cookies/cookiemanager.html): in-memory store và phạm vi policy.
