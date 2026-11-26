# Cookie, bộ nhớ phía client và thời gian sống của thông tin đăng nhập

## Mục tiêu bài học

Một ứng dụng web có thể nhận diện người dùng qua **cookie phiên**, **token** hoặc một cơ chế xác thực khác. Trình duyệt đồng thời cung cấp nhiều nơi lưu dữ liệu như **localStorage**, **sessionStorage**, **IndexedDB**, bộ nhớ JavaScript và Cache Storage. Chúng khác nhau về phạm vi, thời gian tồn tại và khả năng JavaScript truy cập. Chọn sai nơi lưu hoặc đánh đồng **thời hạn cookie** với **thời hạn xác thực** có thể dẫn đến tình huống người dùng tưởng đã đăng xuất nhưng credential vẫn còn giá trị, hoặc session hết hạn dù cookie vẫn xuất hiện trong DevTools.

Bài này thuộc chương **Nền tảng trình duyệt** trong module **SPRING_SECURITY_HTTP_PROTECTION**: áp dụng các lớp phòng vệ HTTP/trình duyệt bằng Spring Security, từ **CSRF, CORS, security headers, CSP, HSTS** đến HTTP firewall và bảo vệ session. Kiến thức được liên hệ với cả **Servlet** và **Reactive/WebFlux**.

Sau bài học, bạn có thể:

1. Phân biệt **cookie jar**, **localStorage**, **sessionStorage**, **IndexedDB**, bộ nhớ JavaScript và những giới hạn của chúng.
2. Giải thích quy trình **Set-Cookie → browser lưu → browser gửi Cookie → server xác thực session**.
3. Thiết kế đúng **Domain, Path, Secure, HttpOnly, SameSite, Max-Age, Expires**; hiểu cookie host-only, tiền tố **__Host-** và phân vùng cookie.
4. Phân biệt **session cookie**, **persistent cookie**, **idle timeout**, **absolute lifetime**, **token expiration**, **refresh token rotation** và remember-me.
5. Nhận diện rủi ro **CSRF, XSS, token replay, session fixation, session hijacking** khi lựa chọn cách lưu credential.
6. Thiết kế đăng xuất, thu hồi phiên, xóa dữ liệu client và kiểm tra tính nhất quán trên nhiều tab/thiết bị.
7. Áp dụng cấu hình và kiểm thử cơ bản trên Spring Security **Servlet** và **Reactive**, đồng thời chẩn đoán cookie còn nhưng user lại nhận 401/403.

## 1. Ba câu hỏi cần tách khi nói “người dùng còn đăng nhập không?”

Giả sử người dùng đăng nhập tại **https://app.example.com**, còn API sử dụng cookie phiên hoặc token tại **https://api.example.com**. Trong hệ thống phải phân biệt ba lớp:

1. **Trình duyệt còn giữ credential không?** Cookie có trong cookie jar? Token còn trong bộ nhớ/localStorage/IndexedDB?
2. **Trình duyệt hoặc ứng dụng có gửi credential ở request này không?** Phụ thuộc URL đích, cookie policy, fetch credentials mode, cách client thêm Authorization, HTTPS và ngữ cảnh site.
3. **Server còn chấp nhận credential đó không?** Session đã hết hạn hay bị thu hồi? Token có hết hạn, bị vô hiệu hóa, sai chữ ký hoặc thiếu quyền không?

Một người dùng có thể thấy cookie vẫn tồn tại trong DevTools nhưng **server trả 401** vì session phía server đã hết hạn. Ngược lại, một cookie đã bị xóa ở một tab **không chứng minh session id phía server đã được thu hồi**: nếu ai đó đã sao chép session id trước khi cookie bị xóa, mã phiên có thể còn dùng được cho đến khi server vô hiệu hóa.

~~~mermaid
flowchart TD
    A["Browser còn giữ credential?"] --> B{"Request có gửi credential?"}
    B -->|Không| C["Request không được xác thực bằng credential này"]
    B -->|Có| D{"Server còn chấp nhận credential?"}
    D -->|Không| E["401 / yêu cầu đăng nhập lại hoặc phản hồi phù hợp"]
    D -->|Có| F{"User được phân quyền?"}
    F -->|Không| G["403 hoặc từ chối truy cập"]
    F -->|Có| H["Thực thi theo quyền và điều kiện nghiệp vụ"]
~~~

Sơ đồ chỉ mô tả luồng kiểm tra điển hình. Một số endpoint công khai không cần credential, và mã HTTP cụ thể phụ thuộc cách ứng dụng xử lý.

### 1.1. Một sơ đồ session cookie phổ biến

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Trình duyệt
    participant S as Spring Security
    participant R as Session repository
    U->>B: Gửi thông tin đăng nhập
    B->>S: POST /login (credentials)
    S->>S: Xác thực, bảo vệ chống session fixation
    S->>R: Tạo/lưu phiên
    S-->>B: Set-Cookie: __Host-session=opaque; Secure; HttpOnly
    B->>B: Lưu cookie theo policy
    U->>B: Mở /account
    B->>S: GET /account + Cookie: __Host-session=opaque
    S->>R: Tìm phiên và kiểm tra trạng thái
    R-->>S: Session hợp lệ / hết hạn
    S-->>B: Trả dữ liệu hoặc từ chối
~~~

**Mã phiên** nên là giá trị khó đoán, không thể suy ra thông tin người dùng. Thông thường server nắm trạng thái xác thực và liên kết session ID với security context. Cookie được gửi đến server theo các quy tắc của browser, **không chứng minh request có chủ ý của người dùng** — đây là điểm liên hệ trực tiếp tới CSRF.

## 2. Cookie: dữ liệu có thể được trình duyệt tự gửi

Cookie là một cơ chế lưu dữ liệu nhỏ, được browser quản lý và lựa chọn gửi theo **URL đích cùng ngữ cảnh request**. Server thường đặt cookie qua **Set-Cookie response header**:

~~~http
HTTP/1.1 200 OK
Set-Cookie: __Host-session=opaque-id; Path=/; Secure; HttpOnly; SameSite=Lax
Content-Type: application/json
~~~

Request về sau có thể chứa:

~~~http
GET /account HTTP/1.1
Host: app.example.com
Cookie: __Host-session=opaque-id
~~~

**Set-Cookie** và **Cookie** là hai header khác nhau:

| Header | Hướng | Ý nghĩa |
| --- | --- | --- |
| **Set-Cookie** | Response từ server | Đề nghị browser thêm, cập nhật hoặc xóa cookie. |
| **Cookie** | Request từ browser | Gửi tên và giá trị những cookie đủ điều kiện gửi. |

Khi gửi Cookie request, browser **không gửi lại các thuộc tính** như HttpOnly, SameSite, Path hoặc Max-Age. Server cần tự hiểu cấu hình cookie và **kiểm tra mã phiên**, không suy ra cookie nào cũng hợp lệ chỉ vì xuất hiện trong header.

### 2.1. Host-only so với Domain cookie

Cookie không có Domain thường là **host-only**:

~~~http
Set-Cookie: session=abc; Path=/; Secure; HttpOnly
~~~

Nếu response từ **https://api.example.com** tạo cookie đó, cookie thường chỉ phù hợp với host **api.example.com**. Trang frontend **app.example.com** không tự được quyền đọc giá trị cookie HttpOnly của API.

Nếu server đặt:

~~~http
Set-Cookie: preference=dark; Domain=example.com; Path=/; Secure
~~~

cookie có thể được gửi đến **example.com**, **app.example.com**, **api.example.com** và những subdomain phù hợp khi các điều kiện khác được đáp ứng.

Lưu ý:

- Browser từ chối Domain không hợp lệ hoặc phạm vi public suffix theo quy tắc cookie; server không thể đặt cookie cho một miền hoàn toàn không liên quan.
- Domain rộng có thể mở bề mặt rủi ro từ **subdomain không đáng tin hoặc bị chiếm quyền**.
- **Port không tạo ranh giới cookie.** Cookie dành cho host localhost có thể khớp cả localhost:3000 lẫn localhost:8080 nếu các điều kiện khác phù hợp, mặc dù hai URL **cross-origin** vì port khác nhau.
- Domain và Path **không thay thế xác thực hoặc phân quyền**.

Đối với session nhạy cảm, nên ưu tiên **cookie host-only** nếu kiến trúc hỗ trợ.

### 2.2. Path, Secure và HttpOnly

| Thuộc tính | Tác dụng | Không tự bảo đảm |
| --- | --- | --- |
| **Path=/** | Cookie có thể khớp những đường dẫn phù hợp dưới gốc site. | Path không phải ranh giới bảo mật mạnh giữa các ứng dụng cùng host. |
| **Secure** | Browser chỉ gửi qua kênh được coi là an toàn theo chính sách cookie, chủ yếu HTTPS. | Không mã hóa cookie tại nơi lưu hay ngăn XSS/CSRF. |
| **HttpOnly** | JavaScript thông thường không đọc được cookie qua document.cookie. | Không cản browser gửi cookie, không ngăn CSRF. |

Ví dụ:

~~~http
Set-Cookie: __Host-session=opaque-id; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Một cookie **HttpOnly** vẫn có thể được browser tự thêm vào HTTP request khi mọi điều kiện phù hợp. Không cho script đọc session ID giúp giảm nguy cơ đánh cắp trực tiếp qua document.cookie, nhưng **script XSS chạy cùng origin** vẫn có thể kích hoạt request có session hiện tại. Đó là lý do HttpOnly không thay thế xử lý XSS và CSRF.

**Secure** phải đi cùng **HTTPS** trên môi trường triển khai thực tế. Nếu Spring Boot đặt sau reverse proxy HTTPS nhưng backend nhận HTTP nội bộ, cần cấu hình forwarded headers/proxy một cách đáng tin, không tin bừa Header X-Forwarded-Proto do client ngoài gửi.

### 2.3. SameSite: cookie gửi theo site, không theo origin

Theo **schemeful same-site** với tên miền thông thường, site dựa trên scheme và **registrable domain** (Public Suffix List). Hai URL **https://app.example.com** và **https://api.example.com** thường **same-site nhưng cross-origin**.

| SameSite | Hành vi chung | Giới hạn |
| --- | --- | --- |
| **Strict** | Cookie chỉ được gửi trong những ngữ cảnh same-site phù hợp. | Người dùng đi từ liên kết ngoài vào ứng dụng có thể không mang cookie trên điều hướng đầu. |
| **Lax** | Gửi trong same-site và một số điều hướng cấp cao nhất bằng method an toàn như GET từ site khác. | Không bảo đảm chặn mọi request nguy hiểm; không dùng GET cho thao tác thay đổi trạng thái. |
| **None; Secure** | Cho phép cookie trong ngữ cảnh cross-site theo điều kiện riêng. | Vẫn có thể bị chặn bởi chính sách third-party cookies và phân vùng. |

Cookie không khai báo SameSite thường được nhiều browser xử lý theo mặc định kiểu Lax, có thể có ngoại lệ tương thích riêng cho cookie mới tạo. **Không dựa vào mặc định để thiết kế phòng vệ CSRF**; nên khai báo thuộc tính rõ ràng và thử nghiệm.

Ví dụ **Lax** có thể cho browser gửi cookie khi người dùng bấm liên kết top-level GET từ một site bên ngoài. Vì vậy **GET /transfer** hoặc **GET /logout** có tác dụng phụ là thiết kế nguy hiểm.

### 2.4. Tiền tố __Host- và __Secure-

Browser hỗ trợ các tiền tố cookie giúp yêu cầu thêm thuộc tính khi cookie được chấp nhận:

~~~http
Set-Cookie: __Secure-pref=dark; Secure; Path=/
Set-Cookie: __Host-session=opaque-id; Secure; HttpOnly; Path=/; SameSite=Lax
~~~

- **__Secure-** yêu cầu cookie được đặt từ nguồn an toàn và có thuộc tính Secure.
- **__Host-** yêu cầu Secure, **Path=/** và **không có Domain**, nhằm gắn cookie với host hẹp hơn.

Tiền tố __Host- đặc biệt hữu ích cho cookie session nếu ứng dụng dùng toàn bộ đường dẫn của một host. Nhưng nó **không tự chống CSRF, XSS hoặc session hijacking** nếu thông tin xác thực bị lộ theo cách khác.

### 2.5. Cookie không có kích thước hoặc số lượng vô hạn

Cookie có giới hạn về kích thước, số lượng theo host/domain và chính sách riêng của browser. Nếu nhét quá nhiều dữ liệu vào cookie:

- Request sẽ mang header Cookie lớn, tăng chi phí truyền tải và nguy cơ bị server/proxy từ chối.
- Dữ liệu client có thể lỗi thời hoặc bị sửa nếu không có kiểm tra phù hợp.
- Dữ liệu nhạy cảm có thể lộ qua các bề mặt xử lý HTTP nếu không thiết kế cẩn thận.

Trong mô hình server session, **chỉ đặt mã phiên opaque trong cookie** thường dễ kiểm soát hơn lưu trực tiếp dữ liệu quyền hay hồ sơ trong cookie. Nếu dùng cookie chứa trạng thái/tokens, phải đánh giá chữ ký, mã hóa khi cần, giới hạn kích thước và thu hồi.

## 3. Bộ nhớ phía client: không phải nơi nào cũng tự gửi dữ liệu

Browser cung cấp nhiều API lưu dữ liệu. Khác cookie, **localStorage, sessionStorage và IndexedDB không tự được browser biến thành Cookie hoặc Authorization header**.

### 3.1. Bảng so sánh các lựa chọn chính

| Nơi lưu | Phạm vi điển hình | Thời gian tồn tại | JavaScript có đọc được? | Tự gắn vào HTTP request? |
| --- | --- | --- | --- | --- |
| **Cookie không HttpOnly** | Domain/host, Path, cookie policy | Session cookie hoặc có hạn dùng | Có, trong phạm vi và chính sách áp dụng | **Có thể**, khi URL và request phù hợp. |
| **Cookie HttpOnly** | Domain/host, Path, cookie policy | Session cookie hoặc có hạn dùng | **Không** qua document.cookie | **Có thể**, khi URL và request phù hợp. |
| **localStorage** | Theo origin, chịu storage partitioning/policy trong các ngữ cảnh đặc biệt | Thường qua nhiều lần tải trang và khởi động lại browser, cho đến khi bị xóa/evict | Có, từ script chạy trong origin đó | **Không**. |
| **sessionStorage** | Theo origin **và ngữ cảnh duyệt cấp cao nhất/tab** | Thường trong vòng đời page session, có thể qua reload/restore | Có, trong ngữ cảnh phù hợp | **Không**. |
| **IndexedDB** | Theo origin, có thể bị phân vùng/giới hạn theo chính sách | Thường bền qua reload; có quota, eviction, chính sách riêng | Có, qua API bất đồng bộ | **Không**. |
| **Bộ nhớ JavaScript** | Runtime của trang, worker hoặc module | Thường mất khi runtime bị hủy/reload; tùy kiến trúc SPA | Có, bởi mã có quyền trong runtime | **Không**. |
| **Cache Storage** | Origin/storage partition, service worker | Tồn tại đến khi bị xóa/evict, theo quota | Có, qua Cache API trong ngữ cảnh có quyền | **Không tự** gửi token như cookie. |

Từ **thường** rất quan trọng: trình duyệt có thể xóa dữ liệu do chế độ riêng tư, chính sách hạn ngạch, người dùng xóa site data, tính năng chống theo dõi hoặc trình duyệt dọn bộ nhớ. **Lưu cục bộ không phải cơ sở dữ liệu bền vững có bảo đảm tuyệt đối**.

### 3.2. localStorage: tồn tại qua reload nhưng dễ bị JavaScript cùng origin đọc

Ví dụ:

~~~javascript
localStorage.setItem("theme", "dark");

const theme = localStorage.getItem("theme");
console.log(theme);

localStorage.removeItem("theme");
~~~

localStorage phù hợp với **tùy chọn giao diện không nhạy cảm**. Nếu lưu access token ở đây:

~~~javascript
localStorage.setItem("accessToken", token);
~~~

mã JavaScript độc hại chạy trong **cùng origin** do XSS có thể đọc token từ localStorage và gửi ra ngoài. Browser không tự gửi token đó: chính ứng dụng phải đọc và gắn nó vào Authorization header.

**Không nên mặc định localStorage là nơi cất giữ an toàn cho credential dài hạn.** Trong ứng dụng có nguy cơ XSS, khả năng truy xuất trực tiếp bằng script là điểm cần đánh giá nghiêm túc.

### 3.3. sessionStorage: theo page session, không đồng nghĩa đăng xuất an toàn

Ví dụ:

~~~javascript
sessionStorage.setItem("draftOrder", JSON.stringify({
  productId: 42,
  quantity: 1
}));

const draft = JSON.parse(sessionStorage.getItem("draftOrder") ?? "null");
~~~

sessionStorage thường gắn với **origin và tab/page session**. Nó có thể tồn tại qua reload và một số cơ chế khôi phục tab; trong một số trường hợp, tab mới mở qua opener có thể nhận bản sao khởi tạo của sessionStorage trước khi tách biệt.

Không dựa vào “đóng tab sẽ hủy mọi phiên đăng nhập” khi credential là **server session hoặc refresh token còn hiệu lực**. Xóa một mục sessionStorage ở một tab không làm session phía server hết hạn.

### 3.4. IndexedDB: lưu dữ liệu ứng dụng, không tự thêm xác thực

IndexedDB phù hợp cho dữ liệu client có cấu trúc, kích thước lớn hơn localStorage và API bất đồng bộ. Một ứng dụng offline có thể cache biểu mẫu, bản nháp hoặc metadata ở IndexedDB.

Nhưng mã cùng origin có quyền JavaScript có thể truy cập dữ liệu trong IndexedDB. Nếu lưu thông tin nhạy cảm, cần có chính sách tối thiểu hóa, xóa theo lifecycle, xử lý XSS và đánh giá tác động khi thiết bị bị chia sẻ.

Không coi IndexedDB là kho bí mật chỉ vì API phức tạp hơn localStorage.

### 3.5. Bộ nhớ JavaScript: giảm độ bền, không loại trừ XSS

Ví dụ giữ access token trong biến:

~~~javascript
let accessToken = null;

function acceptToken(token) {
  accessToken = token;
}

async function loadProfile() {
  return fetch("/api/profile", {
    headers: {
      Authorization: "Bearer " + accessToken
    }
  });
}
~~~

Một token nằm trong bộ nhớ JavaScript thường mất khi tải lại trang, nhưng **mã độc chạy cùng origin vẫn có thể gọi API hoặc can thiệp vào luồng sử dụng token**. Bộ nhớ runtime giảm một số bề mặt lưu trữ lâu dài, **không tự bảo vệ trước XSS**.

### 3.6. Service worker, Cache Storage và dữ liệu sau đăng xuất

Service worker có thể quản lý tài nguyên và Cache Storage để hỗ trợ offline. Nếu ứng dụng cache phản hồi chứa dữ liệu cá nhân, nội dung đó có thể **còn trên thiết bị sau khi session server hết hạn** trừ khi ứng dụng có chính sách xóa/quản lý cache.

Dùng **Cache-Control: no-store** cho phản hồi nhạy cảm khi cần tránh lưu trong HTTP cache, nhưng vẫn phải quản lý chủ động những dữ liệu mà **chính mã ứng dụng** lưu vào IndexedDB hoặc Cache Storage. Không nên suy ra no-store tự động xóa mọi bản sao đã được ứng dụng lưu vào storage khác.

Cũng cần bảo đảm service worker không vô tình trả dữ liệu của user A cho user B trên thiết bị dùng chung do dùng cache key không phân biệt danh tính hoặc phiên.

## 4. Cookie và storage có ranh giới nguồn khác nhau

### 4.1. SOP và Web Storage

Với URL HTTP/HTTPS thông thường:

**Origin = scheme + host + port**

~~~text
https://app.example.com        → origin A
https://api.example.com        → origin B
https://app.example.com:8443   → origin C

A, B, C khác origin.
~~~

JavaScript ở origin A không tự đọc localStorage của B, dù hai host thường **same-site**. Hai cổng khác nhau trên cùng hostname cũng là origin khác nhau.

Cookie lại dựa trên **Domain/host, Path, Secure, SameSite**, không phân biệt port theo cách origin phân biệt. Đó là lý do cookie của localhost có thể áp dụng cho nhiều port, nhưng localStorage của **http://localhost:3000** và **http://localhost:8080** là hai vùng khác nhau.

### 4.2. CORS không mở quyền đọc localStorage của origin khác

Giả sử frontend ở app.example.com gọi API ở api.example.com:

~~~javascript
const response = await fetch("https://api.example.com/api/me", {
  credentials: "include"
});
~~~

Nếu API cấp quyền CORS phù hợp, JavaScript có thể đọc **response**. Điều này **không cấp quyền trực tiếp đọc localStorage/IndexedDB** thuộc origin api.example.com hoặc đọc DOM của một iframe cross-origin.

CORS là cơ chế chia sẻ **HTTP response** có kiểm soát, không phải “gộp” các origin thành một vùng lưu trữ.

### 4.3. Cookie third-party và partitioning

Một widget bên thứ ba nhúng trong website khác có thể chịu chính sách **third-party cookie blocking** hoặc cookie partitioning. Một số trình duyệt hỗ trợ cookie phân vùng bằng **Partitioned**:

~~~http
Set-Cookie: __Host-widget=opaque; Secure; HttpOnly; Path=/; SameSite=None; Partitioned
~~~

Trong ngữ cảnh phù hợp, cookie phân vùng theo top-level site thay vì một cookie third-party chia sẻ trên mọi site. Tính năng và chi tiết hỗ trợ khác nhau giữa browser; không được coi nó là cơ chế đảm bảo mọi iframe có cookie.

Khi ứng dụng cần tích hợp SSO/iframe cross-site, phải kiểm thử chính sách storage/cookie của browser mục tiêu. CORS và credentials: include **không tự vượt qua hạn chế third-party cookie**.

## 5. Thời hạn cookie: session cookie và persistent cookie

### 5.1. Session cookie không có nghĩa hết hạn khi đóng một cửa sổ

Cookie không có **Expires** hoặc **Max-Age** thường được xem là **session cookie của browser**:

~~~http
Set-Cookie: __Host-session=opaque-id; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Nó gắn với khái niệm browser session, nhưng nhiều trình duyệt hỗ trợ **khôi phục phiên/tab** sau khi khởi động lại. Do đó **không nên xem việc đóng một cửa sổ hoặc thoát browser là cơ chế đăng xuất đáng tin cậy**.

Muốn bảo đảm khả năng truy cập kết thúc theo chính sách, server phải có **idle timeout, absolute timeout hoặc thu hồi session** độc lập.

### 5.2. Persistent cookie: Expires và Max-Age

Ví dụ:

~~~http
Set-Cookie: rememberChoice=yes; Path=/; Secure; SameSite=Lax; Max-Age=604800
~~~

**Max-Age=604800** yêu cầu cookie có tuổi thọ khoảng bảy ngày, tính theo quy tắc cookie. Có thể dùng **Expires** để đưa ra thời điểm hết hạn tuyệt đối:

~~~http
Set-Cookie: preference=compact; Path=/; Secure; Expires=Wed, 09 Dec 2026 00:00:00 GMT
~~~

Nếu cả **Max-Age** và **Expires** đều có, **Max-Age có ưu tiên** trong những trình duyệt hỗ trợ chuẩn.

Cookie hết hạn không còn được browser chọn gửi. Nhưng cookie chưa hết hạn **không chứng minh session phía server còn sống**. Không nên đặt Max-Age bảy ngày rồi mặc nhiên xem session server cũng kéo dài bảy ngày.

### 5.3. Xóa cookie phải khớp tên và phạm vi

Để yêu cầu browser xóa một cookie, server có thể gửi:

~~~http
Set-Cookie: __Host-session=; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=0
~~~

Cần quan tâm **cookie name, Domain (nếu có), Path** để xóa đúng bản ghi. Nếu cookie từng được tạo với Path=/app nhưng khi xóa lại dùng Path=/, có thể bạn đã tạo/ghi đè một cookie khác thay vì xóa đúng cookie cũ.

Xóa cookie trong response chỉ ảnh hưởng cookie jar mà browser xử lý; **không tự thu hồi session đang có hiệu lực trên server**. Một phương án đăng xuất an toàn phải xử lý cả hai lớp.

### 5.4. Thời gian hệ thống và sai lệch đồng hồ

Header Expires dùng thời gian tuyệt đối nên có thể chịu ảnh hưởng từ sai lệch đồng hồ giữa client và server; browser có các quy tắc xử lý riêng. **Max-Age** thường dễ diễn giải hơn cho thời hạn tương đối.

Với token có trường thời gian như exp/nbf/iat, **server hoặc bên kiểm tra token phải áp dụng đồng hồ và độ lệch cho phép một cách được kiểm soát**. Không dựa vào thời gian do frontend tự khai để quyết định token có hợp lệ hay không.

## 6. Thời gian sống session phía server

Một session có thể được quản lý trong bộ nhớ server, HTTP session store, Redis hoặc giải pháp tập trung như **Spring Session**. Các giá trị quan trọng:

| Khái niệm | Diễn giải | Ví dụ |
| --- | --- | --- |
| **Idle timeout / max inactive interval** | Session hết hiệu lực sau một khoảng không hoạt động được ghi nhận theo chính sách server. | Không có hoạt động trong 20 phút thì session hết hạn. |
| **Absolute session lifetime** | Session không được kéo dài vượt quá tổng tuổi thọ từ lúc tạo/đăng nhập, dù có hoạt động liên tục. | Buộc xác thực lại sau 12 giờ. |
| **Sliding expiration** | Hoạt động hợp lệ có thể làm mới khoảng hết hạn tính theo inactivity. | Mỗi request phù hợp kéo dài idle deadline, nhưng không nhất thiết kéo dài absolute deadline. |
| **Session invalidation / revocation** | Server chủ động làm mất hiệu lực session. | Đăng xuất, đổi mật khẩu, quản trị viên kết thúc phiên. |
| **Session fixation protection** | Đổi hoặc tái tạo session ID khi xác thực thành công theo chiến lược bảo mật. | Session ID trước đăng nhập không được tái dùng theo cách nguy hiểm. |
| **Concurrent session control** | Giới hạn hoặc quản lý phiên đồng thời trên nhiều thiết bị/tab. | Thông báo các phiên đang hoạt động hoặc giới hạn số phiên. |

Những giá trị như **20 phút** hoặc **12 giờ** chỉ là ví dụ chính sách, không phải giá trị bắt buộc của Spring Security hay khuyến nghị cố định cho mọi sản phẩm.

### 6.1. Cookie còn nhưng session server hết hạn

Giả sử browser đang giữ:

~~~http
Cookie: __Host-session=abc123opaque
~~~

Nhưng session store đã xóa bản ghi abc123opaque do idle timeout. Server nhận request nhưng không khôi phục được security context; kết quả có thể là **401**, redirect đến trang login, hoặc phản hồi tương đương theo cấu hình ứng dụng.

Vì vậy chẩn đoán theo thứ tự:

1. Cookie có thực sự được gửi đến URL này không?
2. Session ID có còn trong repository không?
3. Session có hết hạn hoặc bị invalidated không?
4. Authentication có được khôi phục từ session không?
5. Authorization có cho phép endpoint không?

Đừng chỉ thấy Cookie header và kết luận “Spring Security hỏng đăng nhập”.

### 6.2. Sliding session và request nền

Nếu mỗi request hợp lệ đều gia hạn idle timeout, các request nền như polling, refresh dữ liệu hoặc heartbeat có thể **kéo dài session dù người dùng không tương tác**. Tùy mục tiêu bảo mật, đó có thể là hành vi không mong muốn.

Cần quyết định rõ:

- Những hoạt động nào đủ để coi người dùng còn hoạt động?
- Có **absolute lifetime** để buộc xác thực lại không?
- Một session hết hạn do idle có được tự khôi phục bằng remember-me không?
- Khi user khóa màn hình, đổi mật khẩu hoặc tài khoản bị vô hiệu hóa, cần thu hồi phiên nào?

Không phải mọi session store mặc định đều cung cấp sẵn absolute lifetime; muốn áp dụng cần có chính sách bổ sung phù hợp với kiến trúc.

### 6.3. Session trên nhiều server

Nếu ứng dụng chạy nhiều instance mà dùng session **chỉ ở bộ nhớ từng instance**, request có thể gặp tình huống phiên tồn tại ở máy A nhưng không có ở máy B. Điều này dễ bị nhầm với cookie hết hạn ngẫu nhiên.

Cần cân nhắc **shared session repository** (chẳng hạn Spring Session với Redis) hoặc chiến lược phù hợp với hệ thống. Việc dùng shared store không tự giải quyết CSRF, fixation, bảo vệ cookie hoặc quyền truy cập.

## 7. Access token, refresh token và remember-me

### 7.1. Access token có thời hạn kiểm chứng riêng

Một access token tự chứa như JWT có thể có các claim:

~~~json
{
  "sub": "user-42",
  "iss": "https://auth.example.com",
  "aud": "orders-api",
  "iat": 1790000000,
  "exp": 1790000900
}
~~~

Các con số chỉ minh họa định dạng timestamp. **exp** thường biểu thị thời điểm token không còn được chấp nhận; server phải kiểm tra chữ ký hoặc phương thức xác thực token, issuer, audience, exp và những điều kiện liên quan. Không tin chỉ vì frontend giải mã được payload JSON.

Nếu access token được lưu trong localStorage, browser **không tự** đưa nó vào HTTP request. Ứng dụng thường phải chủ động thêm:

~~~javascript
const token = getTokenFromApplication();

await fetch("https://api.example.com/api/me", {
  headers: {
    Authorization: "Bearer " + token
  }
});
~~~

**getTokenFromApplication()** là hàm minh họa của ứng dụng, không phải API browser. Sử dụng Bearer token có thể giảm một số kiểu CSRF nếu token chỉ được chủ động đính kèm bởi code hợp lệ, nhưng vẫn cần chống **XSS, đánh cắp token, replay, phân quyền sai**. Nếu refresh token nằm trong cookie tự gửi, endpoint refresh vẫn phải được đánh giá CSRF.

### 7.2. Refresh token cần vòng đời và cơ chế thu hồi

Refresh token thường cho phép nhận access token mới mà không buộc người dùng đăng nhập lại ngay. Vì có khả năng duy trì phiên lâu hơn access token, nó cần:

- Lưu trữ với rủi ro phù hợp kiến trúc; ưu tiên hạn chế khả năng JavaScript tiếp cận khi không cần thiết.
- **Rotation** hoặc cơ chế hạn chế reuse theo thiết kế nhà cung cấp xác thực.
- **Revocation** khi đăng xuất, đổi mật khẩu, tài khoản bị khóa hoặc phát hiện dấu hiệu rủi ro.
- Thời hạn **absolute** và/hoặc **idle** rõ ràng.
- Ràng buộc với client/session/scopes theo cơ chế xác thực sử dụng.
- Không đưa token vào URL query, log, analytics hoặc thông báo lỗi.

Đừng nhầm “JWT access token exp trong 15 phút” với “người dùng hết đăng nhập sau 15 phút”: nếu refresh token còn hợp lệ, ứng dụng có thể cấp access token mới theo chính sách.

### 7.3. Remember-me khác session cookie đơn thuần

Tính năng **remember-me** có thể cho phép ứng dụng nhận diện user sau khi session HTTP kết thúc. Nó thường là một credential có thời hạn riêng, ví dụ cookie lưu lâu hơn session.

Điều này tạo **hai lớp vòng đời**:

~~~text
HTTP session kết thúc
     ↓
Remember-me credential vẫn có thể còn hợp lệ
     ↓
Ứng dụng có thể tái xác thực theo chính sách remember-me
~~~

Vì vậy, nếu mục tiêu là “đăng xuất hoàn toàn”, cần kiểm tra **cả session hiện tại và remember-me credential**. Một số loại remember-me cookie có giá trị bị đánh cắp có thể bị phát lại nếu không được thu hồi/rotation đúng cách.

Trong Spring Security, cấu hình remember-me là **tính năng riêng**, không mặc định bật chỉ vì ứng dụng dùng session. Chỉ triển khai khi có yêu cầu rõ ràng, thời hạn phù hợp và cơ chế thu hồi/token repository đáp ứng nhu cầu bảo mật.

### 7.4. Không dùng refresh token hoặc remember-me để lách chính sách hết phiên

Nếu hệ thống yêu cầu tái xác thực người dùng khi làm việc nhạy cảm, không nên để luồng refresh/remember-me âm thầm khôi phục mọi quyền vô hạn. Có thể cần **step-up authentication** cho hành động rủi ro, giới hạn thời gian kể từ lần xác thực mạnh gần nhất và thu hồi các credential dài hạn khi có sự kiện bảo mật.

## 8. Chọn nơi lưu credential: đánh đổi bảo mật

Một câu hỏi phổ biến là: **nên lưu access token ở localStorage hay cookie HttpOnly?** Không có câu trả lời an toàn tuyệt đối nếu bỏ qua mô hình đe dọa và luồng xác thực thực tế.

### 8.1. Ma trận đánh đổi

| Phương án | Ưu điểm điển hình | Nguy cơ chính | Điều kiện bổ sung |
| --- | --- | --- | --- |
| **Session ID trong cookie HttpOnly, Secure** | JavaScript không trực tiếp đọc mã phiên; browser quản lý gửi cookie; server chủ động thu hồi session. | Cookie tự gửi có thể bị lợi dụng cho **CSRF**; nếu XSS tồn tại, mã độc vẫn có thể thực hiện request với phiên hiện tại. | CSRF token, SameSite, phân quyền, session fixation protection, TLS, CSP/XSS defense. |
| **Access token trong bộ nhớ JavaScript** | Không còn trên đĩa qua mỗi reload thông thường; ứng dụng kiểm soát khi thêm Authorization. | Script XSS cùng origin có thể dùng token hoặc thực hiện request; reload làm mất token nếu không có cơ chế khôi phục. | CSP/XSS defense, lifetime ngắn, luồng làm mới token được thiết kế an toàn. |
| **Access token trong localStorage** | Dễ triển khai, tồn tại qua reload và phiên browser. | Mã JavaScript cùng origin có thể đọc token; token có thể tồn tại lâu không chủ đích. | XSS defense nghiêm ngặt, hạn dùng và thu hồi rõ ràng, đánh giá chính sách lưu trữ. |
| **Access token trong sessionStorage** | Phạm vi theo page session hẹp hơn localStorage trong nhiều trường hợp. | Script XSS vẫn đọc được; khôi phục tab hoặc các luồng tạo tab khiến giả định “đóng tab là hết” không đáng tin tuyệt đối. | XSS defense, chính sách vòng đời và xóa dữ liệu. |
| **Refresh token trong cookie HttpOnly** | Hạn chế JavaScript đọc token làm mới trực tiếp. | Request tới endpoint refresh có thể mang cookie tự động; CSRF/refresh abuse và replay vẫn phải đánh giá. | Rotation/reuse detection/revocation, CSRF khi phù hợp, Secure, SameSite, path/host scope. |
| **Token hoặc khóa trong IndexedDB** | Tiện cho ứng dụng offline và dữ liệu có cấu trúc. | Mã JavaScript cùng origin thường có thể truy cập; dữ liệu bền qua reload. | XSS defense, chính sách xóa/eviction, giới hạn dữ liệu nhạy cảm. |

**Không có cơ chế nào thay thế xác thực và phân quyền ở server.** CORS không biến localStorage thành nơi an toàn, và HttpOnly không ngăn hoàn toàn hành động từ script bị chèn vào origin hợp lệ.

### 8.2. Đánh giá theo tình huống, không theo khẩu hiệu

Một hệ thống giao diện và API cùng origin, có session store và giao dịch nhạy cảm thường có thể dùng **session cookie HttpOnly**, kết hợp CSRF token. Một API được gọi bởi mobile app, background service hoặc frontend có OAuth2/OIDC có thể sử dụng Bearer tokens theo cơ chế thích hợp. Cùng một hệ thống có thể kết hợp session và token ở các khu vực khác nhau, nhưng phải có **ranh giới rõ ràng**.

Hãy hỏi:

1. Credential nào **browser tự gửi** khi website khác cố khởi tạo request?
2. Credential nào **mã JavaScript cùng origin có thể đọc**?
3. Nếu credential bị đánh cắp, có thể **thu hồi** không, hay phải chờ hết hạn?
4. Nếu người dùng đăng xuất, credential nào còn ở **tab khác, thiết bị khác, storage khác**?
5. Khi đổi mật khẩu hoặc khóa tài khoản, cơ chế nào thu hồi quyền ngay?
6. Khi phản hồi chứa dữ liệu nhạy cảm, cache/service worker có thể tiếp tục lưu dữ liệu không?

### 8.3. XSS và CSRF có mô hình khác nhau

~~~text
XSS:
  Mã độc chạy trong origin tin cậy
    → có thể đọc storage JavaScript cho phép
    → có thể gọi API theo quyền của trang

CSRF:
  Trang không đáng tin khởi tạo request sang ứng dụng khác
    → browser có thể tự gắn cookie/session
    → server phải xác minh tính hợp lệ của thao tác
~~~

- **CSP**, escaping đúng ngữ cảnh, xử lý dữ liệu đầu vào và kiểm soát dependency hỗ trợ giảm rủi ro XSS.
- **CSRF token**, SameSite, Origin/Fetch Metadata theo chính sách hỗ trợ giảm rủi ro CSRF.
- **Authentication/authorization** vẫn quyết định user và quyền ở mọi endpoint; không được suy ra từ vị trí lưu dữ liệu phía client.

Với **CSP frame-ancestors/X-Frame-Options**, server còn có thể hạn chế các trang nhạy cảm bị nhúng vào iframe. **HSTS** giúp browser dùng HTTPS trên host theo chính sách, nhưng không giải quyết thời hạn session hoặc thu hồi token.

## 9. Spring Security Servlet: session cookie và thời gian sống

Với Spring Boot 3.x, Spring Security 6.x trên **Spring MVC/Servlet**, có thể cấu hình cookie phiên và thời gian không hoạt động qua các thuộc tính servlet session.

### 9.1. Ví dụ application.yml cho Servlet

~~~yaml
server:
  servlet:
    session:
      timeout: 20m
      cookie:
        name: __Host-session
        path: /
        secure: true
        http-only: true
        same-site: lax
~~~

**Đọc đúng ý nghĩa:**

- **server.servlet.session.timeout** cấu hình thời gian không hoạt động của session theo cơ chế servlet/session manager đang sử dụng, không phải thời hạn tuyệt đối kể từ lúc login.
- **cookie.name** chọn tên cookie phiên do container/session integration quản lý.
- Tên **__Host-session** yêu cầu **Secure, Path=/** và không đặt Domain; nếu không đáp ứng, browser có thể từ chối cookie.
- **secure: true** phù hợp với production HTTPS; môi trường HTTP dev cần cấu hình riêng, không vì debug mà tắt Secure trên production.
- **http-only: true** ngăn mã JavaScript đọc cookie session; không ngăn browser gửi cookie.
- **same-site: lax** giảm gửi cookie trong nhiều ngữ cảnh cross-site; không thay thế CSRF token.

Nếu cấu hình Spring Session hoặc proxy riêng, cần xác minh **cookie thực tế trong response** và timeout thực tế của repository thay vì chỉ đọc file cấu hình. Thuộc tính servlet không nhất thiết điều khiển mọi session store/plugin tùy chỉnh.

### 9.2. SecurityFilterChain: giữ CSRF và bảo vệ login/logout

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ServletSessionSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**").permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .sessionManagement(session -> session
                        .sessionFixation(fixation -> fixation.changeSessionId()))
                .logout(logout -> logout
                        .invalidateHttpSession(true)
                        .deleteCookies("__Host-session"))
                // CSRF protection mặc định vẫn hoạt động.
                .build();
    }
}
~~~

Ví dụ cho ứng dụng có **form login**. Tùy phiên bản và servlet container, bảo vệ session fixation có thể đã là mặc định; cấu hình trên làm rõ ý định **đổi session ID sau khi xác thực**. Với cookie tên khác, chỉnh cấu hình xóa cookie tương ứng.

**Không coi logout handler xóa cookie là đủ cho mọi trường hợp.** Phải xác minh session đã được vô hiệu hóa tại server, cookie thực tế được xóa với **Path/Domain** phù hợp, remember-me token (nếu có) đã được thu hồi, và các credential khác cũng có quy trình thu hồi.

Nếu SPA gửi logout qua fetch cross-origin, cần bổ sung CORS phù hợp. Các request thay đổi trạng thái như POST /logout thường cần **CSRF token** khi CSRF đang bật. Không chuyển logout thành GET chỉ vì frontend muốn một liên kết.

### 9.3. Lưu phiên theo session store dùng chung

Một triển khai nhiều instance có thể dùng **Spring Session** với repository chung để tránh session chỉ tồn tại trên một instance. Nhưng cấu hình repository, expiration và cleanup cần phù hợp Redis/DB và deployment. Cần kiểm thử:

- Session hết hạn sau idle timeout thực tế.
- Yêu cầu sau logout không khôi phục session cũ.
- Rotation session ID sau login không để session ID cũ tiếp tục có quyền ngoài ý muốn.
- Nhiều instance trả cùng kết quả đối với cùng một session hợp lệ.
- Thu hồi session trên một instance được các instance khác quan sát theo chính sách.

Không suy ra cookie Max-Age tự đồng bộ với TTL của session store.

### 9.4. Cookie có Max-Age và phiên server có timeout khác nhau

Giả sử một cookie phiên tồn tại bảy ngày nhưng session store chỉ lưu 20 phút không hoạt động. Sau 25 phút không có hoạt động, cookie vẫn có thể xuất hiện trong browser nhưng server đã loại session.

Nếu muốn browser **xóa cookie đồng thời** với session theo một chính sách định trước, cần thiết kế rõ cách đặt cookie hạn dùng và bảo đảm server không chấp nhận token đã hết hiệu lực. Không thể luôn buộc browser xóa cookie chính xác vào đúng thời điểm server xóa session khi browser đang offline.

## 10. Spring Security Reactive/WebFlux: WebSession và cookie ID

WebFlux sử dụng **WebSession**, không phải HttpSession của Servlet. Có thể dùng **WebSessionIdResolver** và cookie builder để đặt tên và thuộc tính cookie ID.

### 10.1. Cấu hình SecurityWebFilterChain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class ReactiveSessionSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(auth -> auth
                        .pathMatchers("/public/**").permitAll()
                        .anyExchange().authenticated())
                .formLogin(Customizer.withDefaults())
                // CSRF protection mặc định vẫn hoạt động.
                .build();
    }
}
~~~

Ví dụ giữ CSRF và yêu cầu authentication trên endpoint không công khai. Form login/logout thực tế cần được thiết kế tương thích với frontend, SecurityWebFilterChain và quy trình token của ứng dụng.

### 10.2. Cấu hình cookie ID của WebSession

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.server.session.CookieWebSessionIdResolver;
import org.springframework.web.server.session.WebSessionIdResolver;

@Configuration
class ReactiveSessionCookieConfig {

    @Bean
    WebSessionIdResolver webSessionIdResolver() {
        CookieWebSessionIdResolver resolver =
                new CookieWebSessionIdResolver();

        resolver.setCookieName("__Host-session");
        resolver.addCookieInitializer(cookie -> cookie
                .path("/")
                .secure(true)
                .httpOnly(true)
                .sameSite("Lax"));
        return resolver;
    }
}
~~~

Đoạn code minh họa API WebFlux để đặt cookie session trên production HTTPS. Không đặt Domain khi dùng tiền tố **__Host-**. Trong hệ thống thực tế, nếu Spring Session reactive hoặc một SessionIdResolver tùy chỉnh đã được khai báo, cần tích hợp tại đúng điểm để tránh cấu hình bean trùng nhau.

### 10.3. WebSession idle timeout

WebFlux cho phép quản lý **thời gian không hoạt động** của WebSession. Ví dụ minh họa trong một handler có quyền thao tác trên session hiện tại:

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;
import org.springframework.web.server.ServerWebExchange;

Mono<Void> configureSessionIdleTimeout(ServerWebExchange exchange) {
    return exchange.getSession()
            .doOnNext(session ->
                    session.setMaxIdleTime(Duration.ofMinutes(20)))
            .then();
}
~~~

Đoạn trên là một **helper**, không phải lớp cấu hình session toàn ứng dụng. Nó phải được gọi tại điểm phù hợp trong luồng session đã được thiết kế, ví dụ khi khởi tạo hoặc cập nhật chính sách phiên. Không nên để mọi request công khai tự tạo session chỉ để chạy helper.

Phần mềm thực tế cũng cần kiểm tra timeout của **WebSessionStore hoặc Spring Session Reactive repository** nếu có, và việc server dọn phiên hết hạn. **Không áp dụng máy móc thuộc tính server.servlet.session.timeout cho WebFlux**: đó là cấu hình của servlet stack.

### 10.4. Logout trong Reactive

Logout của WebFlux phải dẫn tới **vô hiệu hóa trạng thái xác thực/session** theo cơ chế reactive tương ứng, xóa credential phía browser nếu áp dụng, và thu hồi remember-me/refresh token nếu tồn tại trong kiến trúc.

Cũng như Servlet, CSRF mặc định trong Spring Security WebFlux thường yêu cầu token cho các method làm thay đổi trạng thái. **Không dùng GET cho logout có tác dụng vô hiệu hóa phiên**. Khi test, kiểm tra rằng cookie cũ hoặc session ID cũ không tiếp tục truy cập được tài nguyên đã bảo vệ.

## 11. Luồng đăng xuất và thu hồi thông tin đăng nhập

Đăng xuất là một thao tác bảo mật, không đơn thuần chỉ thay đổi nút giao diện từ “Logout” thành “Login”.

### 11.1. Luồng đăng xuất có kiểm soát

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Browser
    participant S as Spring Security
    participant R as Session/Token store
    U->>B: Chọn đăng xuất
    B->>S: POST /logout + cookie + CSRF token hợp lệ
    S->>R: Invalidate session / revoke credential nếu áp dụng
    R-->>S: Đã xử lý theo repository
    S-->>B: Set-Cookie xóa cookie, response/logout redirect
    B->>B: Xóa state client thuộc trách nhiệm ứng dụng
    B-->>U: Hiển thị trạng thái đã đăng xuất
~~~

Những hành động cần cân nhắc:

1. **Vô hiệu hóa session server-side**, không chỉ xóa cookie client.
2. **Xóa cookie** với đúng tên/Path/Domain và các thuộc tính cần thiết.
3. **Thu hồi refresh token, remember-me token** hoặc session khác theo chính sách logout hiện hành.
4. **Xóa access token/đầu vào nhạy cảm** đang được frontend lưu trong bộ nhớ, localStorage hoặc sessionStorage, nếu chúng thuộc phạm vi phiên vừa đăng xuất.
5. **Xóa hoặc cô lập dữ liệu nhạy cảm** trong IndexedDB/Cache Storage/service worker theo thiết kế.
6. Xác định logout có áp dụng **tab hiện tại, mọi tab, thiết bị hiện tại hay mọi thiết bị**; đây là lựa chọn nghiệp vụ, không phải hành vi tự động của browser.
7. Cân nhắc **Cache-Control: no-store** cho response chứa dữ liệu riêng tư và cách bảo vệ trang khi người dùng bấm Back sau đăng xuất.

### 11.2. Xóa dữ liệu phía client không thu hồi token server

~~~javascript
localStorage.removeItem("accessToken");
sessionStorage.removeItem("draftPrivateData");
~~~

Các lệnh trên chỉ xóa dữ liệu trong phạm vi storage hiện tại. Chúng **không bảo đảm** token đã bị thu hồi tại issuer/API hoặc một bản sao token ở tab, thiết bị, storage hoặc client khác đã bị xóa.

Nếu access token là JWT tự chứa và API chỉ kiểm tra chữ ký cùng exp, server có thể tiếp tục chấp nhận nó cho đến khi hết hạn trừ khi có cơ chế **revocation/denylist**, thay đổi khóa, phiên ràng buộc hoặc cơ chế tương ứng.

### 11.3. Back button, browser cache và dữ liệu offline

Sau logout, người dùng bấm Back có thể thấy một trang trước đó do browser cache hoặc trạng thái tab cũ hiển thị. Điều này **không nhất thiết chứng minh session vẫn còn hợp lệ**. Cần thử request API mới tới tài nguyên bảo vệ: nếu server đã thu hồi session đúng, API không được cấp dữ liệu mới.

Với dữ liệu cực kỳ nhạy cảm, cần chính sách cache, trạng thái client và màn hình che dữ liệu sau logout phù hợp. Cân nhắc HTTP cache, bfcache, service worker và storage theo kiến trúc; không kỳ vọng một header duy nhất luôn xóa mọi nội dung đã được hiển thị trước đó.

### 11.4. Đăng xuất trên nhiều tab

Nếu user mở tab A và B cùng origin, sau logout ở tab A, tab B có thể vẫn hiển thị giao diện cũ trong bộ nhớ. Cần phát tín hiệu đồng bộ UI, ví dụ **BroadcastChannel** hoặc một cơ chế thông báo từ ứng dụng:

~~~javascript
// Ví dụ đơn giản cho các tab cùng origin.
const channel = new BroadcastChannel("auth-state");

function publishLoggedOut() {
  channel.postMessage({ type: "LOGGED_OUT" });
}

channel.addEventListener("message", (event) => {
  if (event.data?.type === "LOGGED_OUT") {
    // Xóa state nhạy cảm trong tab hiện tại, chuyển về login.
    clearSensitiveUiState();
  }
});
~~~

**clearSensitiveUiState()** là hàm của ứng dụng, không có sẵn trong browser. BroadcastChannel là **cơ chế đồng bộ giao diện**, không phải cơ chế thu hồi session. Vẫn phải vô hiệu hóa credential tại server và xử lý trường hợp tab bị treo, không nhận sự kiện hoặc offline.

## 12. Kiểm thử bằng DevTools và HTTP client

Để xác định đúng vì sao user vẫn đăng nhập hoặc đột ngột mất session, hãy quan sát **từng lớp** thay vì chỉ nhìn giao diện.

### 12.1. Kiểm tra cookie đã được lưu chưa

Trong **DevTools → Application/Storage → Cookies**:

- Xem cookie được lưu cho host nào.
- Xem **Domain, Path, Secure, HttpOnly, SameSite, Expires/Max-Age**.
- Kiểm tra cookie bị browser từ chối, bị chặn bởi third-party cookie policy hoặc bị phân vùng không.
- Kiểm tra cookie có đúng tên không, đặc biệt khi dùng **__Host-**.
- Phân biệt cookie có trong storage và cookie đã được gửi trong request cụ thể.

Lưu ý: DevTools có thể hiển thị nội dung cookie HttpOnly cho người đang sở hữu môi trường debug phù hợp, nhưng điều đó **không có nghĩa JavaScript bình thường đọc được cookie HttpOnly**.

### 12.2. Kiểm tra network sau login

Trong **DevTools → Network**, xem:

1. Response login có **Set-Cookie** không? Browser có cảnh báo Set-Cookie bị từ chối không?
2. API request tiếp theo có **Cookie header** không?
3. Với fetch cross-origin, frontend có **credentials: include** không?
4. CORS response có **Access-Control-Allow-Origin** cụ thể và **Access-Control-Allow-Credentials: true** khi cần không?
5. Request thực trả **401**, **403**, **302** về login hay lỗi CORS? Đừng đánh đồng chúng.
6. Nếu có OPTIONS preflight, có phải OPTIONS bị chặn trước POST không? Preflight thường không mang session cookie.
7. Nếu API vẫn nhận cookie nhưng báo session hết hạn, kiểm tra session repository, TTL, revocation, đồng hồ và sticky/shared sessions.

### 12.3. Phân biệt 401, 403 và lỗi CORS

| Triệu chứng | Khả năng cần xem | Hướng kiểm tra |
| --- | --- | --- |
| Browser giữ cookie nhưng request API không có Cookie. | URL không khớp Domain/Path, Secure/SameSite, credentials mode, third-party policy. | Network Cookies/Request Headers, URL đích và ngữ cảnh site. |
| Cookie có trong request nhưng server trả 401. | Session store đã hết hạn/không tìm thấy, credential không hợp lệ hoặc auth chain khác. | Session repository, max idle, logout/revocation, Spring Security logs. |
| Request có session và CSRF token nhưng trả 403. | Không đủ quyền hoặc token CSRF không đúng theo cấu hình. | Kiểm tra authorization, token repository và logs. |
| OPTIONS trả 401/403, POST không được gửi. | Preflight bị xử lý sau auth hoặc CORS policy từ chối. | Kiểm tra thứ tự CORS và allowed Origin/method/header. |
| POST 200 nhưng frontend báo CORS. | Response thực thiếu CORS header phù hợp. | Kiểm tra POST response và proxy, tránh retry giao dịch mù quáng. |
| Login thành công trên instance A, request sau 401 trên B. | Session chỉ lưu cục bộ hoặc repository không đồng nhất. | Session store chung, load balancer, TTL, replication. |
| Người dùng logout nhưng tab B còn thấy dữ liệu. | UI/cache chưa đồng bộ hoặc API chưa thu hồi session. | Gọi API mới, kiểm tra BroadcastChannel, HTTP cache và storage. |
| Người dùng đóng browser rồi mở lại vẫn đăng nhập. | Browser session restore hoặc remember-me/refresh token. | Cookie type, remember-me policy và server auth logs. |
| Token hết hạn nhưng frontend vẫn giữ chuỗi token. | Storage và tính hợp lệ token độc lập. | Kiểm tra exp, refresh, token validation và revocation. |
| Sau triển khai HTTPS, cookie biến mất. | Cookie Secure/Domain/Path/Host prefix sai hoặc proxy forwarded headers cấu hình thiếu. | DevTools Issues/Storage và response Set-Cookie thực. |

### 12.4. Kiểm thử lifecycle session

Trong môi trường kiểm thử:

1. **Đăng nhập**, ghi nhận tên cookie, thời hạn và session ID ở server logs an toàn (không in đầy đủ session ID bí mật).
2. **Gửi request GET** hợp lệ, xác nhận session được khôi phục.
3. **Để phiên không hoạt động** lâu hơn idle timeout đã cấu hình, gọi lại API; xác nhận server không chấp nhận session cũ.
4. **Đăng nhập lại** và kiểm tra việc đổi session ID theo chính sách chống session fixation.
5. **Đăng xuất** qua phương thức hợp lệ với CSRF token khi áp dụng; thử lại request dùng session cũ để bảo đảm bị từ chối.
6. **Đăng nhập trên hai thiết bị hoặc trình duyệt**; kiểm tra logout có áp dụng thiết bị hiện tại hay tất cả theo chính sách.
7. **Kiểm tra nhiều tab**, làm mới trang, browser restart/restore và dữ liệu lưu offline.
8. Nếu có remember-me hoặc refresh token, kiểm tra **hết hạn, rotation, reuse và revocation** theo hợp đồng hệ thống.

Dùng tài khoản test và dữ liệu có thể xóa; không ghi mã phiên/token thật vào báo cáo kiểm thử hoặc log chia sẻ rộng rãi.

### 12.5. curl chỉ giúp xem HTTP, không mô phỏng đầy đủ browser

Trong môi trường kiểm thử được phép:

~~~bash
curl -i "https://app.example.com/account"
~~~

Có thể sử dụng cookie jar của curl để mô phỏng một phần quá trình lưu/gửi cookie, nhưng **curl không thực thi đầy đủ SameSite, SOP/CORS, third-party cookie policy, page session hoặc UI tab** như browser.

Ví dụ kiểm tra preflight của một SPA khác origin:

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/orders" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
~~~

Để kiểm tra cookie thực sự được browser gửi, dùng **DevTools** thay vì chỉ dựa vào curl. Trên PowerShell, dùng **curl.exe** nếu cần tránh bí danh curl của PowerShell.

## 13. Bài tập tình huống

### Tình huống A — Cookie vẫn có nhưng user bị đăng xuất

Cookie session còn trong DevTools với Expires ngày mai; server-side idle timeout là 20 phút. Người dùng không hoạt động 30 phút và GET /account trả 401. Đây chắc chắn là lỗi browser?

**Đáp án:** Không. Cookie còn nhưng session phía server có thể đã hết idle timeout. Cookie lifetime và session validity độc lập. Kiểm tra session repository, timeout và auth logs.

### Tình huống B — localStorage tồn tại sau reload

SPA lưu access token trong localStorage. Sau refresh, ứng dụng vẫn đọc được token. Điều đó chứng minh token còn hợp lệ?

**Đáp án:** Không. localStorage bảo toàn chuỗi dữ liệu qua reload, nhưng API phải kiểm tra token expiration, chữ ký, issuer/audience, scopes và trạng thái revocation theo cơ chế sử dụng.

### Tình huống C — sessionStorage và nhiều tab

Ứng dụng cho rằng token trong sessionStorage chắc chắn bị xóa khi đóng một tab, nên không cần thu hồi ở server. Có an toàn không?

**Đáp án:** Không. Page session có thể được khôi phục tùy browser; một số luồng tab mới có thể nhận bản sao khởi tạo. Quan trọng hơn, bản sao token ở nơi khác có thể vẫn có hiệu lực. Thu hồi token cần cơ chế server/issuer khi chính sách yêu cầu.

### Tình huống D — HttpOnly có chống CSRF không?

Cookie session có Secure, HttpOnly và SameSite=Lax. Lập trình viên nói “JavaScript không đọc được cookie nên CSRF không thể xảy ra”. Đúng không?

**Đáp án:** Sai. Browser có thể tự gửi cookie HttpOnly. SameSite giảm rủi ro nhiều ngữ cảnh cross-site, nhưng không thay thế CSRF token và không chặn mọi request same-site từ subdomain không đáng tin.

### Tình huống E — Port khác nhưng cookie vẫn gửi

Frontend http://localhost:3000 gọi API http://localhost:8080. Một cookie host-only không Secure của localhost có thể được gửi sang port khác không? localStorage có được chia sẻ không?

**Đáp án:** Cookie không cô lập theo port nên có thể đủ điều kiện gửi theo các quy tắc khác, đặc biệt nếu fetch đặt credentials phù hợp. Nhưng hai URL khác origin, nên localStorage không tự chia sẻ giữa port 3000 và 8080; fetch khác origin còn chịu CORS.

### Tình huống F — Logout chỉ xóa cookie

Ứng dụng gửi Max-Age=0 cho cookie phiên rồi hiển thị “Đã đăng xuất”, nhưng session ID vẫn hợp lệ trong session store. Có an toàn không?

**Đáp án:** Chưa đủ. Cần invalidate session tại server. Nếu session ID đã bị sao chép trước đó, xóa cookie ở browser không ngăn dùng lại ID khi nó còn hiệu lực.

### Tình huống G — Xóa cookie sai Path

Cookie được tạo với Path=/app, nhưng logout gửi Max-Age=0 với Path=/. Có thể chắc chắn cookie cũ bị xóa không?

**Đáp án:** Không. Việc xóa cần khớp cookie name và phạm vi phù hợp, đặc biệt Path và Domain khi có. Kiểm tra Cookie Storage sau response logout.

### Tình huống H — Access token ngắn, refresh token dài

Access token hết hạn sau 15 phút nhưng refresh token vẫn còn hợp lệ nhiều ngày. Người dùng còn có thể được cấp quyền truy cập mà không đăng nhập lại không?

**Đáp án:** Có thể, nếu refresh flow cho phép cấp access token mới. Thời hạn đăng nhập thực tế phụ thuộc cả refresh token, rotation, revocation, absolute policy và yêu cầu tái xác thực.

### Tình huống I — Remember-me sau session timeout

Session HTTP hết hạn, nhưng browser vẫn có remember-me cookie và ứng dụng tự xác thực lại. Điều đó có mâu thuẫn với session timeout không?

**Đáp án:** Không. Remember-me là một cơ chế xác thực duy trì riêng với thời hạn riêng. Nếu không mong muốn tự đăng nhập lại, cần thay đổi chính sách remember-me, không chỉ giảm session idle timeout.

### Tình huống J — XSS đọc token

Một SPA lưu access token trong localStorage và có lỗ hổng XSS. HttpOnly trên cookie session của API có bảo vệ access token trong localStorage không?

**Đáp án:** Không. HttpOnly chỉ áp dụng cho cookie được đặt thuộc tính đó. JavaScript độc hại cùng origin có thể đọc localStorage; cần bảo vệ XSS, giới hạn credential và xử lý token lifecycle thích hợp.

### Tình huống K — Cookie session cùng site, khác origin

Frontend https://app.example.com gọi https://api.example.com qua fetch. API có cookie host-only HttpOnly SameSite=Strict, nhưng fetch không có credentials: include. Browser có nhất thiết gửi cookie API không?

**Đáp án:** Không. Hai host có thể cùng site nhưng khác origin; fetch mặc định credentials: same-origin không tự gửi cookie cho request cross-origin. Khi dùng include, cookie còn phải khớp Domain/Path/Secure/SameSite và CORS phải phù hợp để JavaScript đọc response.

### Tình huống L — Nhiều instance session

Ứng dụng chạy ba instance, session chỉ nằm trong bộ nhớ của từng instance. Người dùng bị 401 ngẫu nhiên sau khi load balancer chuyển request. Vấn đề có chắc là cookie Expires?

**Đáp án:** Không. Có thể do session repository không chia sẻ giữa instance. Cần kiểm tra routing, session store, TTL và chính sách multi-instance; cookie còn hợp lệ không bảo đảm instance mới có bản ghi session.

### Tình huống M — Sau logout vẫn thấy dữ liệu khi bấm Back

Người dùng đã logout, bấm Back thấy màn hình giao dịch cũ. Có kết luận server vẫn cho phép truy cập không?

**Đáp án:** Chưa thể. Browser có thể hiện trạng thái/cached page cũ. Phải gọi API bảo vệ mới bằng credential cũ để kiểm tra session đã bị thu hồi, đồng thời xử lý HTTP cache và UI state phù hợp.

### Tình huống N — Session luôn tồn tại vì polling

Ứng dụng poll API mỗi phút, server tính mỗi request là hoạt động và gia hạn idle timeout. Người dùng không tương tác trong nhiều giờ nhưng session không hết. Có trái với mục tiêu idle timeout theo tương tác người dùng không?

**Đáp án:** Có thể. Cần xác định loại request nào được tính là hoạt động, xem xét absolute lifetime hoặc cơ chế user-activity riêng và không để background polling vô tình giữ phiên vô thời hạn.

### Tình huống O — Refresh token trong cookie HttpOnly

Ứng dụng lưu refresh token trong cookie HttpOnly rồi bỏ qua kiểm tra CSRF cho endpoint /token/refresh vì JavaScript không đọc được cookie. An toàn chưa?

**Đáp án:** Chưa thể kết luận. Cookie vẫn có thể được browser tự gửi và endpoint refresh có tác dụng cấp credential mới. Cần đánh giá CSRF, cookie SameSite, Origin, token rotation, phạm vi cookie, kiểm soát response và chính sách cấp refresh/access token.

### Tình huống P — Server đã thu hồi session nhưng browser giữ cookie

Sau logout, browser còn cookie session nhưng server đã invalidate session id đúng cách. Request mới có cookie cũ có được truy cập tài nguyên riêng tư không?

**Đáp án:** Không được, nếu server kiểm tra session repository đúng và không có cơ chế tự xác thực lại khác như remember-me. Cookie chưa được xóa là vấn đề vệ sinh trạng thái và UX, nhưng server-side invalidation mới là ranh giới xác thực chính trong mô hình session.

## 14. Ghi nhớ

- **Credential đang được lưu**, **credential được gửi** và **credential được server chấp nhận** là ba trạng thái khác nhau; không suy ra một trạng thái từ trạng thái còn lại.
- **Cookie do browser tự chọn gửi** theo Domain/host, Path, Secure, SameSite, hạn dùng và credentials mode. **HttpOnly** ngăn JavaScript đọc trực tiếp cookie, không ngăn browser gửi cookie hay tự chống CSRF.
- **localStorage, sessionStorage, IndexedDB và bộ nhớ JavaScript không tự gắn giá trị thành Cookie/Authorization**. Script có quyền cùng origin thường truy cập được các vùng lưu đó; XSS là rủi ro quan trọng.
- **Cookie session không có Expires/Max-Age** vẫn có thể sống qua browser restore; **persistent cookie** có thời hạn lưu client nhưng không bảo đảm session server còn hiệu lực.
- **Idle timeout** là thời hạn theo không hoạt động; **absolute lifetime** là giới hạn tổng thời gian; **refresh token/remember-me** có thể duy trì xác thực sau khi HTTP session hoặc access token kết thúc.
- **Logout đầy đủ** cần xử lý server-side invalidation/revocation, xóa cookie đúng Path/Domain, dọn state client/cache và xác định chính sách đối với nhiều tab/thiết bị.
- **CORS** điều chỉnh khả năng JavaScript đọc response cross-origin; **CSRF token, authentication, authorization** vẫn bảo vệ hành động dùng cookie/session. CORS không cấp quyền và không làm cookie tự gửi.
- Trong **Spring Security Servlet**, cấu hình cookie/timeout qua servlet session và security filter chain; trong **WebFlux**, dùng **WebSession**, resolver cookie và security web filter chain phù hợp.
- Khi chẩn đoán, luôn xem **Set-Cookie response, Cookie request, storage, session repository, thời hạn/thu hồi token và log bảo mật** thay vì chỉ quan sát trạng thái giao diện.
