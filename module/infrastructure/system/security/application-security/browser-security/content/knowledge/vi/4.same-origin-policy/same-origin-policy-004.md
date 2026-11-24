# Request và read khác nhau

> **Thông điệp cốt lõi:** Trong bảo mật trình duyệt, **gửi được HTTP request** và **đọc được HTTP response bằng JavaScript** là hai quyền khác nhau. Một request có thể đã đến server, thậm chí đã thay đổi dữ liệu, dù script gọi request chỉ nhận lỗi CORS và không đọc được response. Ngược lại, một số request bị chặn **trước khi gửi request chính**, chẳng hạn khi preflight CORS thất bại.

Bài học thuộc chương **Same-origin policy** trong module **Browser Security** (`SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY`). Đây là nền tảng để phân tích ranh giới bảo mật giữa browser, origin, cookie và ứng dụng web, đồng thời hiểu đúng vai trò của CORS, cách ly tài nguyên và các biện pháp chống XSS, CSRF, clickjacking bằng CSP, Trusted Types và security headers.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

1. Phân biệt **khả năng khởi tạo/gửi request**, **khả năng nhúng tài nguyên** và **khả năng đọc response**.
2. Giải thích tại sao SOP có thể từ chối quyền đọc nhưng server vẫn nhận hoặc xử lý request.
3. Phân biệt request CORS được gửi trực tiếp với **preflight `OPTIONS`**, `fetch(..., {mode: 'no-cors'})` và response **opaque**.
4. Chỉ rõ ranh giới của cookie, `credentials`, `SameSite`, CORS và cơ chế phòng chống CSRF.
5. Quan sát chính xác request, status, response headers và lỗi CORS bằng Developer Tools.
6. Chọn phòng vệ phù hợp cho server và browser, tránh coi CORS là cơ chế xác thực/phân quyền.

## 2. Một ví dụ nhỏ để hiểu đúng câu hỏi

Giả sử bạn đang mở trang:

```text
https://shop.example.com
```

JavaScript trên trang này gọi:

```js
await fetch('https://api.example.net/cart');
```

Hai URL có **origin khác nhau**. Nếu API không cho phép origin của shop đọc response qua CORS, đoạn `fetch()` trên có thể báo lỗi. Nhưng từ lỗi đó **không thể suy ra** server chưa nhận request.

```mermaid
sequenceDiagram
    participant JS as JavaScript tại shop.example.com
    participant B as Browser
    participant API as API tại api.example.net
    JS->>B: fetch("https://api.example.net/cart")
    B->>API: GET /cart + Origin: https://shop.example.com
    API->>API: Xử lý request
    API-->>B: 200 OK + JSON (không có header CORS phù hợp)
    B--xJS: Chặn quyền đọc response; fetch bị reject
    Note over B,API: API đã nhận request dù script không đọc được body
```

Để diễn đạt chính xác cần tách **ba sự kiện**:

| Sự kiện | Câu hỏi cần kiểm chứng | Nơi có bằng chứng |
| --- | --- | --- |
| **Request được gửi** | Browser có thực hiện kết nối và chuyển request tới API không? | DevTools Network, request headers, log máy chủ |
| **Server xử lý request** | API có nhận, xác thực và thực hiện hành động không? | Log ứng dụng, database, dữ liệu trạng thái server |
| **Script đọc response** | JavaScript có lấy được status, headers và body theo các Web API không? | Console, kết quả `fetch()`/`XMLHttpRequest`, CORS response headers |

SOP/CORS tập trung vào các quyền của **mã chạy trong browser**. Máy chủ vẫn có nghĩa vụ xác thực, phân quyền và kiểm soát những thao tác mà nó nhận.

## 3. Same-Origin Policy bảo vệ quyền đọc như thế nào?

**Origin** thường được xác định bởi bộ ba **scheme + host + port**. Đường dẫn, query string và fragment không thuộc bộ ba này.

Nếu trang gốc là `https://app.example.com:443/dashboard`:

| Tài nguyên | Cùng origin? | Lý do |
| --- | :---: | --- |
| `https://app.example.com/settings` | Có | Cùng scheme, host và port mặc định HTTPS |
| `https://api.example.com/orders` | Không | Khác host |
| `https://app.example.com:8443/data` | Không | Khác port |
| `http://app.example.com/login` | Không | Khác scheme |
| `https://evil.example.net/` | Không | Khác host |

**Same-Origin Policy (SOP)** hạn chế việc một origin truy cập trực tiếp những nội dung được bảo vệ của origin khác: ví dụ đọc DOM trong iframe, truy cập một số vùng lưu trữ và đọc response từ `fetch()`/XHR. SOP không phải là tường lửa ngăn mọi kết nối HTTP đến origin khác.

### Ba loại khả năng thường bị nhầm lẫn

- **Gửi (request/write):** khởi tạo yêu cầu qua liên kết, form, tải tài nguyên hoặc một số lệnh JavaScript. Tùy loại request và chính sách trình duyệt, yêu cầu có thể được gửi tới origin khác.
- **Nhúng (embed):** tải và hiển thị tài nguyên như ảnh, iframe hoặc stylesheet trong một trang. Tài nguyên có thể xuất hiện trên giao diện trong khi script vẫn không đọc được dữ liệu nội bộ.
- **Đọc (read):** cho JavaScript truy cập nội dung response, DOM, pixel ảnh hoặc dữ liệu riêng theo các API được hỗ trợ. Đây là quyền thường bị hạn chế bởi SOP nếu khác origin.

Chính sách dành cho mỗi loại tài nguyên **không giống nhau**. Một trang được phép hiển thị ảnh xuyên origin không đương nhiên có quyền đọc pixel của ảnh qua canvas. Một trang có thể điều hướng sang website khác nhưng không thể dùng script từ trang cũ đọc DOM riêng của website mới.

## 4. Bảng quyền theo từng cơ chế gửi hoặc nhúng

| Cơ chế | Request sang origin khác có thể xảy ra? | JavaScript của trang nguồn đọc được response? | Lưu ý |
| --- | --- | --- | --- |
| `<a href="...">` / điều hướng | Có, theo chính sách điều hướng | Không thể tự do đọc DOM của tài liệu origin đích | Người dùng vẫn có thể nhìn thấy trang được mở |
| `<form action="..." method="POST">` | Có, dưới các điều kiện browser/cookie liên quan | Không mặc nhiên đọc được response xuyên origin | Là lý do CSRF có thể xảy ra dù không bật CORS |
| `<img src="...">` | Thường có thể tải ảnh | Không mặc nhiên đọc pixel bằng canvas; canvas có thể bị **taint** | `crossorigin` + CORS hợp lệ có thể thay đổi quyền xử lý canvas |
| `<iframe src="...">` | Có thể tải/hiển thị nếu chính sách framing cho phép | Không đọc DOM xuyên origin theo SOP | `frame-ancestors`, `X-Frame-Options` có thể chặn nhúng |
| `<script src="...">` cổ điển | Có thể tải script ngoài theo các chính sách | Script tải về **chạy trong origin của trang nhúng**, có quyền của trang đó | Đặc biệt nhạy cảm; chọn nguồn tin cậy, CSP/SRI khi phù hợp |
| `fetch(url)` với CORS mặc định | Request có thể được gửi; đôi khi phải preflight | **Chỉ** được đọc nếu kiểm tra CORS thành công | Thiếu header CORS có thể khiến Promise bị reject sau khi API đã xử lý |
| `fetch(url, {mode: 'no-cors'})` | Có thể gửi một tập request bị giới hạn | Thường nhận **opaque response**, không đọc body/headers/status thực | `no-cors` không phải cách tắt CORS để lấy JSON |
| Backend HTTP client / `curl` | Có thể gửi nếu mạng và server đích cho phép | Không chịu SOP/CORS của browser | Vẫn chịu xác thực, phân quyền, mạng và kiểm soát server |

Từ “có thể” trong bảng có chủ đích: CSP, mixed content, cookie policy, CORS preflight, CORP/COEP, cơ chế chặn theo dõi, TLS, DNS và nhiều điều kiện khác có thể ngăn một yêu cầu cụ thể. Hãy kiểm chứng thực tế thay vì suy luận từ tên API.

### Ví dụ: tải ảnh khác origin nhưng canvas bị hạn chế

```html
<img id="photo" src="https://images.example.net/photo.png" alt="Ảnh minh họa">
```

Ảnh có thể được hiển thị. Tuy nhiên nếu vẽ ảnh khác origin không được CORS cho phép lên canvas rồi thử đọc pixel, trình duyệt có thể ném `SecurityError`:

```js
const img = document.querySelector('#photo');
const canvas = document.createElement('canvas');
const ctx = canvas.getContext('2d');

img.addEventListener('load', () => {
  canvas.width = img.naturalWidth;
  canvas.height = img.naturalHeight;
  ctx.drawImage(img, 0, 0);

  try {
    console.log(ctx.getImageData(0, 0, 1, 1).data);
  } catch (error) {
    console.log(error.name); // Thường là SecurityError.
  }
});
```

Ví dụ này nói về **quyền đọc pixel**, không phải khả năng tải ảnh. Trình duyệt cũng có các ngoại lệ và hạn chế riêng cho tainted canvas; không nên dùng việc ảnh hiển thị được làm căn cứ rằng dữ liệu ảnh đã được cấp quyền đọc qua JavaScript.

## 5. `fetch()`: gửi request không đồng nghĩa đọc response

Theo mặc định, `fetch()` trong browser sử dụng `mode: 'cors'` cho request mạng thông thường. Với URL khác origin, browser tuân theo quy trình CORS.

### 5.1. Request được gửi trực tiếp rồi bị chặn đọc

Giả sử script ở `https://app.example.com` chạy:

```js
try {
  const response = await fetch('https://api.example.net/public-data');
  console.log(await response.json());
} catch (error) {
  console.error('Không đọc được response:', error);
}
```

Với một `GET` thỏa điều kiện **CORS-safelisted request** (thường gọi là *simple request*), browser không cần preflight. API vẫn có thể nhận `GET`, chạy nghiệp vụ và trả `200 OK`. Nếu response thiếu header cho phép origin hoặc cấu hình CORS sai, browser không chuyển response đó cho script.

Điều này giải thích tình huống tưởng như mâu thuẫn:

```text
Network / server log: GET /public-data → 200 OK
Console / JavaScript: TypeError: Failed to fetch (do CORS)
```

Câu chữ lỗi tùy trình duyệt. Việc DevTools hiển thị một response **không có nghĩa** script có quyền đọc response đó. DevTools là công cụ chẩn đoán có đặc quyền khác với mã web thông thường.

### 5.2. CORS header mở quyền đọc có điều kiện

Nếu API chủ đích cho phép origin của ứng dụng đọc dữ liệu, server có thể trả:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin
Content-Type: application/json
Cache-Control: no-store

{"items":[1,2,3]}
```

Lúc này browser có thể cho script tại `https://app.example.com` đọc response, với điều kiện không còn lỗi CORS hoặc chính sách khác. `Vary: Origin` quan trọng khi server phản hồi khác nhau theo `Origin` và response đi qua cache chia sẻ.

**Không nên** lấy trực tiếp mọi giá trị `Origin` từ request rồi phản chiếu vào `Access-Control-Allow-Origin` nếu API có dữ liệu riêng tư. Cần xác định allowlist origin rõ ràng và áp dụng xác thực/phân quyền độc lập.

### 5.3. Preflight có thể chặn request chính **trước khi gửi**

Khi script định gửi `POST` với `Content-Type: application/json` qua CORS:

```js
await fetch('https://api.example.net/account/update', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ displayName: 'An' }),
});
```

Browser thường gửi yêu cầu **preflight `OPTIONS`** để hỏi API có cho phép method và headers dự định hay không:

```http
OPTIONS /account/update HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type
```

Để cho phép request chính, server cần phản hồi preflight hợp lệ, ví dụ:

```http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: POST
Access-Control-Allow-Headers: Content-Type
Vary: Origin
```

Sau khi preflight thành công, browser mới gửi `POST` chính. Với trường hợp đơn giản **không credentials**, response của request chính vẫn cần cho phép origin đọc. Nếu preflight thất bại, trình duyệt **không gửi request chính**; server có thể chỉ nhìn thấy `OPTIONS`.

```mermaid
sequenceDiagram
    participant JS as JavaScript
    participant B as Browser
    participant API as API
    JS->>B: POST JSON xuyên origin
    B->>API: OPTIONS + Access-Control-Request-Method: POST
    alt Preflight hợp lệ
        API-->>B: 204 + Access-Control-Allow-*
        B->>API: POST /account/update
        API-->>B: Response POST
        B-->>JS: Chỉ đọc nếu response thỏa CORS
    else Preflight không hợp lệ
        API-->>B: 405 hoặc thiếu CORS headers cần thiết
        B--xJS: Lỗi CORS; không gửi POST
    end
```

Preflight không được xem là hệ thống phân quyền. Một HTTP client ngoài browser vẫn có thể gửi thẳng `POST`. Một ứng dụng khác cũng có thể tạo request với hình thức khác; API vẫn cần tự kiểm tra danh tính, quyền và chống CSRF nếu thích hợp.

### 5.4. `no-cors` không phải cách vượt CORS

Ví dụ:

```js
const response = await fetch('https://api.example.net/data', {
  mode: 'no-cors',
});

console.log(response.type);   // "opaque" trong trường hợp cross-origin điển hình.
console.log(response.status); // 0, không phải HTTP status thật.
console.log(response.ok);     // false.
```

Một **opaque response** che status thật, headers và body đối với JavaScript. Request có thể đến server, nhưng API này **không cho script đọc JSON**. Chế độ `no-cors` còn hạn chế method và các header mà script được phép thiết lập. Tùy môi trường còn có opaque-redirect và những loại response khác; ví dụ trên nói về response xuyên origin thông thường ở chế độ `no-cors`.

Nếu ứng dụng cần dữ liệu API, giải pháp là **cấu hình CORS đúng ở API** hoặc thiết kế backend hợp lệ để server ứng dụng gọi API và trả dữ liệu đã được phép cho client. Đừng dùng proxy mở nhận URL tùy ý, vì nó có thể tạo lỗ hổng SSRF.

### 5.5. Request có thể bị chặn ở nhiều thời điểm

| Điểm xảy ra | Ví dụ | Request chính đã đến server? |
| --- | --- | --- |
| Trước mạng | CSP `connect-src` từ chối URL; mixed content bị chặn | Thường **chưa** |
| Tại preflight | `OPTIONS` không được phép hoặc không có CORS headers cần thiết | `OPTIONS` có thể đã đến; request chính **chưa** |
| Sau response request chính | `GET` simple thành công ở server nhưng thiếu `Access-Control-Allow-Origin` | **Có thể đã** đến và được xử lý |
| Khi đọc dữ liệu từ API | Header CORS đúng nhưng API trả `401`/`403` | Request đã đến; server từ chối quyền hoặc xác thực |
| Do mạng | DNS/TLS/kết nối thất bại | Phải kiểm tra log/Network; không thể kết luận chỉ từ một lỗi JavaScript |

Phân biệt **lỗi bảo mật trình duyệt**, **lỗi HTTP nghiệp vụ** và **lỗi kết nối** giúp chẩn đoán chính xác và không sửa nhầm bằng cách nới lỏng CORS.

## 6. Cookie, credentials và khái niệm `site`

SOP/CORS xét **origin**, còn thuộc tính cookie `SameSite` xét **site**. Hai subdomain có thể cùng site nhưng khác origin:

```text
Trang:  https://app.example.com
API:    https://api.example.com
Origin: KHÁC vì host khác nhau
Site:   THƯỜNG CÙNG vì cùng scheme https và registrable domain example.com
```

Đối với cookie, browser còn xét `Domain`/host, `Path`, `Secure`, `SameSite`, chính sách cookie bên thứ ba và các cơ chế phân vùng lưu trữ khi áp dụng. **CORS thành công không có nghĩa cookie mặc nhiên được gửi**.

### 6.1. `fetch()` và credentials

Mặc định `fetch()` dùng `credentials: 'same-origin'`, do đó với một `fetch` xuyên origin thông thường, browser không tự đính kèm cookie do web API này quản lý theo cách như request cùng origin.

```js
// Browser script tại https://app.example.com
await fetch('https://api.example.com/profile', {
  credentials: 'include',
});
```

Khi dùng `credentials: 'include'`, browser vẫn chỉ gửi cookie **nếu cookie phù hợp chính sách**. Nếu JavaScript cần đọc response có credentials qua CORS, server phải gửi:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
```

Không dùng `Access-Control-Allow-Origin: *` cho response CORS có credentials. Việc cho phép đọc response vẫn **không cấp quyền tài khoản**: server phải xác thực session/token và phân quyền dữ liệu.

### 6.2. Vì sao lỗi CORS không bảo vệ được khỏi CSRF?

Một **form HTML** trên website khác có thể gửi request tới ứng dụng đang có phiên đăng nhập. Nếu cookie được đính kèm theo chính sách và server không kiểm tra ý định của request, hành động nhạy cảm có thể bị thực hiện **dù trang gây ra request không thể đọc response**.

```html
<!-- Minh họa tình huống rủi ro CSRF, không triển khai với dữ liệu thật. -->
<form action="https://bank.example.com/settings/email" method="POST">
  <input type="hidden" name="email" value="attacker@example.net">
  <button type="submit">Gửi yêu cầu</button>
</form>
```

Khả năng tấn công thực tế phụ thuộc cookie `SameSite`, phương thức, thao tác cụ thể và các phòng vệ tại endpoint. Ví dụ minh họa **cách request được tạo**, không khẳng định một ngân hàng hay website thật có lỗ hổng đó.

Các biện pháp bảo vệ **tại server** cần phối hợp:

1. **CSRF token** được kiểm tra đúng với phiên và các thao tác thay đổi trạng thái; hoặc cơ chế tương đương được thiết kế đúng cho kiến trúc.
2. Cookie phiên có `Secure`, `HttpOnly` và `SameSite=Lax` hoặc `Strict` khi phù hợp. Chỉ dùng `SameSite=None; Secure` cho nhu cầu xuyên site hợp lệ.
3. Kiểm tra `Origin`/`Referer` và/hoặc **Fetch Metadata** (`Sec-Fetch-Site`, `Sec-Fetch-Mode`,...) theo chính sách rõ ràng, có xử lý trường hợp header vắng mặt.
4. Không thay đổi trạng thái qua `GET`; áp dụng xác thực, phân quyền và xác nhận lại cho hành động rủi ro cao.

Lưu ý: `SameSite` là ranh giới **site**, vì vậy một subdomain cùng site nhưng không đáng tin cậy vẫn có thể gây rủi ro CSRF nếu server chỉ dựa vào thuộc tính này. Hơn nữa, `HttpOnly` ngăn JavaScript đọc trực tiếp cookie nhưng không ngăn mọi thao tác do script độc hại thực hiện trong phiên đã xác thực.

## 7. Những ranh giới liên quan: XSS, iframe và rò rỉ gián tiếp

Phân biệt request và read giúp tránh cấu hình nhầm cơ chế bảo vệ. Tuy nhiên SOP không thể bảo vệ ứng dụng khỏi mọi sai sót phía browser.

### 7.1. XSS biến mã tấn công thành mã cùng origin

Nếu attacker đưa script thực thi vào một trang qua lỗ hổng **Cross-Site Scripting (XSS)**, script đó có thể chạy **ngay trong origin của trang bị lỗi**. Khi ấy SOP không giúp tách script độc hại khỏi nhiều dữ liệu và API mà origin này vốn được phép truy cập.

```js
const message = new URLSearchParams(location.search).get('message') ?? '';

// Rủi ro: dữ liệu nhập được xử lý như HTML.
document.querySelector('#message').innerHTML = message;

// An toàn khi chỉ cần hiển thị văn bản:
document.querySelector('#message').textContent = message;
```

Cần tránh DOM sink nguy hiểm, encode đầu ra theo ngữ cảnh và sanitize HTML nếu thực sự cần hiển thị rich text. **CSP** giới hạn nguồn script/tài nguyên và một số hành vi; **Trusted Types** có thể siết các DOM sink nguy hiểm tại browser hỗ trợ. Hai cơ chế này là lớp phòng vệ bổ sung, không thay cho xử lý dữ liệu đúng.

### 7.2. Iframe: hiển thị có thể được, nhưng DOM không được đọc

Một trang có thể thử nhúng website khác:

```html
<iframe src="https://account.example.net" title="Trang tài khoản"></iframe>
```

Nếu được phép nhúng, iframe có thể hiển thị trên màn hình. Nhưng JavaScript ở trang cha không mặc nhiên được đọc DOM của iframe khác origin. Nếu có nhu cầu giao tiếp hợp lệ giữa hai frame, dùng `postMessage()` và **kiểm tra `event.origin`**, cấu trúc thông điệp; phía gửi phải chọn `targetOrigin` cụ thể thay vì dùng `*` cho dữ liệu nhạy cảm.

Để ngăn **clickjacking** đối với trang nhạy cảm không được nhúng, server có thể trả:

```http
Content-Security-Policy: frame-ancestors 'none'
X-Frame-Options: DENY
```

Browser thi hành chính sách framing. `frame-ancestors` phải nằm trong **HTTP response header**, không dùng thẻ `<meta>` để thay thế.

### 7.3. Không đọc được body vẫn có thể quan sát tín hiệu khác

Một trang bên ngoài đôi khi có thể quan sát sự kiện tải, thời gian phản hồi, thay đổi điều hướng hoặc đặc điểm hiển thị mà không đọc trực tiếp response. Nhóm rủi ro này thường được gọi là **cross-site leaks (XS-Leaks)**. SOP nhằm hạn chế nhiều quyền đọc trực tiếp nhưng không bảo đảm tuyệt đối chống mọi suy luận gián tiếp.

Server nên tránh endpoint trả tín hiệu khác biệt dễ quan sát cho dữ liệu nhạy cảm, hạn chế việc nhúng không cần thiết, áp dụng `Cross-Origin-Resource-Policy` (CORP), `Cross-Origin-Opener-Policy` (COOP), `Cross-Origin-Embedder-Policy` (COEP) khi đúng mô hình đe dọa và kiểm tra xác thực/phân quyền. Những header này có vai trò khác nhau; **CORP/COEP không thay thế CORS** nếu JavaScript cần đọc response qua `fetch()`.

## 8. Thực hành: ba kết quả khác nhau cho cùng một API

Bài thực hành chạy **chỉ trên localhost**, với **Node.js 18 trở lên**, không cần cài thư viện. Mục đích là đối chiếu ba tình huống:

1. **GET hoặc POST đơn giản:** request đến API, response bị browser chặn đọc khi API không có CORS.
2. **POST JSON cần preflight:** browser gửi `OPTIONS`, không gửi `POST` khi preflight thất bại.
3. **`no-cors` GET:** request đến API nhưng JavaScript nhận **opaque response**.

Hai origin của thí nghiệm:

```text
http://localhost:3000  -> trang demo (browser đang mở)
http://localhost:3001  -> API (khác origin vì khác port)
```

### 8.1. Tạo `api.mjs`

Tạo file sau trong **thư mục thực hành riêng**, bên ngoài nội dung bài học:

```js
import { createServer } from 'node:http';

let counter = 0;
const allowRead = false; // Vòng 2: đổi thành true rồi khởi động lại API.
const allowedOrigin = 'http://localhost:3000';

createServer((req, res) => {
  console.log('[API]', req.method, req.url, 'Origin:', req.headers.origin ?? '(none)');
  res.setHeader('Cache-Control', 'no-store');
  res.setHeader('Content-Type', 'application/json; charset=utf-8');

  // Cố ý không hỗ trợ preflight để nhìn thấy OPTIONS thất bại.
  if (req.method === 'OPTIONS') {
    res.writeHead(405).end(JSON.stringify({ error: 'Preflight is disabled' }));
    return;
  }

  // Khi bật, chỉ cho phép trang demo đọc response; không bật CORS toàn cục.
  if (allowRead && req.headers.origin === allowedOrigin) {
    res.setHeader('Access-Control-Allow-Origin', allowedOrigin);
    res.setHeader('Vary', 'Origin');
  }

  if (req.method === 'GET' && req.url === '/state') {
    res.writeHead(200).end(JSON.stringify({ counter }));
    return;
  }

  if (req.method === 'POST' && req.url === '/increment') {
    // Chỉ là bộ đếm trong RAM cho demo; KHÔNG triển khai kiểu này vào production.
    counter += 1;
    console.log('Counter tăng lên:', counter);
    res.writeHead(200).end(JSON.stringify({ counter }));
    return;
  }

  res.writeHead(404).end(JSON.stringify({ error: 'Not found' }));
}).listen(3001, () => console.log('API: http://localhost:3001'));
```

API cung cấp `GET /state` để xem bộ đếm và `POST /increment` để tăng bộ đếm. Endpoint không sử dụng session và không có dữ liệu nhạy cảm: đây là mô hình tối giản để chứng minh request có thể gây tác dụng phụ dù không đọc được response, **không phải ví dụ một CSRF hoàn chỉnh**.

### 8.2. Tạo `app.mjs`

```js
import { createServer } from 'node:http';

const page = `<!doctype html>
<html lang="vi">
<head><meta charset="utf-8"><title>Request vs Read</title></head>
<body>
  <h1>Request vs Read: localhost:3000 → localhost:3001</h1>
  <p>Mở DevTools (F12) → Console và Network trước khi bấm.</p>
  <button id="get">1. GET /state (CORS mặc định)</button>
  <button id="post">2. POST form-urlencoded (simple request)</button>
  <button id="json">3. POST JSON (preflight)</button>
  <button id="opaque">4. GET no-cors (opaque)</button>
  <pre id="log"></pre>
  <script>
    const api = 'http://localhost:3001';
    const log = (text) => {
      document.querySelector('#log').textContent += text + '\\n';
    };

    async function probe(name, path, options) {
      try {
        const response = await fetch(api + path, options);
        if (response.type === 'opaque') {
          log(name + ': opaque, status=' + response.status + ', body bị ẩn');
          return;
        }
        log(name + ': HTTP ' + response.status + ', ' + await response.text());
      } catch (error) {
        log(name + ': ' + error.name + ' - ' + error.message);
      }
    }

    document.querySelector('#get').onclick = () =>
      probe('GET', '/state');
    document.querySelector('#post').onclick = () =>
      probe('POST form', '/increment', {
        method: 'POST',
        body: new URLSearchParams({ value: '1' }),
      });
    document.querySelector('#json').onclick = () =>
      probe('POST JSON', '/increment', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value: 1 }),
      });
    document.querySelector('#opaque').onclick = () =>
      probe('GET no-cors', '/state', { mode: 'no-cors' });
  </script>
</body>
</html>`;

createServer((_req, res) => {
  res.writeHead(200, {
    'Content-Type': 'text/html; charset=utf-8',
    'Cache-Control': 'no-store',
  });
  res.end(page);
}).listen(3000, () => console.log('App: http://localhost:3000'));
```

Mở **hai terminal** tại thư mục demo:

```bash
node api.mjs
```

```bash
node app.mjs
```

Mở `http://localhost:3000`. Trước tiên để `allowRead = false`. Mở DevTools, chọn **Network** (có thể bật *Preserve log*) và **Console**, rồi bấm từng nút.

### 8.3. Dự đoán và đối chiếu kết quả

| Thao tác trên trang | Terminal API | JavaScript trong trang | Bộ đếm |
| --- | --- | --- | --- |
| **1. GET** | Nhận `GET /state` | `fetch` bị reject vì response thiếu CORS | Không đổi |
| **2. POST form-urlencoded** | Nhận `POST /increment` | `fetch` bị reject vì không đọc được response | **Tăng 1** |
| **3. POST JSON** | Nhận `OPTIONS /increment`, trả 405 | `fetch` bị reject trước khi gửi `POST` | **Không tăng** |
| **4. GET no-cors** | Nhận `GET /state` | Promise thường resolve với `response.type === 'opaque'`, `status === 0` | Không đổi |

Để kiểm tra trạng thái thực của server, mở **tab mới** tới `http://localhost:3001/state`. Browser điều hướng trực tiếp và **hiển thị JSON cho người dùng**, nhưng script đang chạy ở tab `3000` vẫn không có quyền đọc JSON đó qua CORS. Đây là hai ngữ cảnh khác nhau: hiển thị qua điều hướng và đọc qua JavaScript.

Nếu bạn không thấy `OPTIONS` riêng trong Network, thử bật tùy chọn hiện request preflight của DevTools. Một số trình duyệt hiển thị hoặc nhóm request preflight khác nhau. Terminal API là nguồn quan sát bổ sung.

### 8.4. Bật quyền đọc bằng CORS

Dừng API, đổi `allowRead` thành `true`, chạy lại `node api.mjs`, tải lại `http://localhost:3000`.

- Nút **GET** giờ có thể đọc JSON nhờ `Access-Control-Allow-Origin: http://localhost:3000`.
- Nút **POST form-urlencoded** có thể đọc response JSON sau khi server tăng bộ đếm.
- Nút **POST JSON** vẫn thất bại, vì ví dụ **cố ý** trả 405 cho preflight. Chỉ thêm `Access-Control-Allow-Origin` trên response POST chưa đủ để thông qua preflight.
- Nút **no-cors** vẫn trả response opaque: script đã chủ động chọn chế độ không đọc response.

Kiểm tra trong **Network → request → Headers**:

```http
Origin: http://localhost:3000
```

và khi `allowRead = true`:

```http
Access-Control-Allow-Origin: http://localhost:3000
```

Hãy so sánh thông báo Console với log terminal và giá trị `/state`. Bài thực hành này cho thấy rõ **điểm xảy ra thay đổi trạng thái**, **điểm browser chặn đọc** và **điểm browser chặn gửi request chính**.

### 8.5. Giới hạn thực hành và cách diễn giải

- Demo chỉ chạy trên localhost, không có người dùng thật, cookies hay quyền truy cập. Không dùng endpoint `/increment` như thiết kế production.
- Request `fetch` ở đây không gửi cookie xuyên origin theo mặc định. Nếu thử phiên/cookie thật, cần đánh giá riêng `credentials`, `SameSite`, domain, CORS có credentials và CSRF.
- Lỗi CORS và câu chữ do browser hiển thị có thể khác; giữ nguyên cấu hình và dựa trên **Network + server log + trạng thái server** để kết luận.
- Một API có thể được gọi bởi công cụ HTTP ngoài browser dù CORS bị chặn. Vì vậy không dùng CORS làm biện pháp bảo vệ API khỏi client tùy ý.

## 9. Mô hình phân tích khi gặp lỗi thực tế

Khi frontend báo `CORS error`, hãy đi theo trình tự:

1. **Xác định hai origin**: so sánh scheme, host, port của tài liệu và API. Đừng nhầm “cùng site” với “cùng origin”.
2. **Xem request đã đi đến đâu**: Network có `OPTIONS`? Có request chính? Log server có nhận không? Có reverse proxy/CDN can thiệp không?
3. **Đọc headers liên quan**: request `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers`; response `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers` và `Access-Control-Allow-Credentials` khi cần.
4. **Kiểm tra credentials**: frontend có dùng cookie không? `fetch` dùng `credentials` gì? Cookie có thuộc phạm vi và được phép gửi không?
5. **Đánh giá hành động server**: endpoint đã ghi dữ liệu chưa, có đòi xác thực/phân quyền và CSRF token không? Không thử lại thao tác không idempotent vô hạn vì tưởng request đã thất bại.
6. **Chỉ sửa đúng nguyên nhân**: cấu hình CORS theo allowlist origin khi có nhu cầu đọc hợp lệ; xử lý `OPTIONS` nếu cần; giữ nguyên các kiểm tra nghiệp vụ và chính sách bảo mật phù hợp.

### Tình huống kiểm tra nhanh

| Triệu chứng | Nguyên nhân khả dĩ | Cần xác minh |
| --- | --- | --- |
| Network có `GET 200`, Console báo CORS | API thiếu CORS response header hợp lệ | `Origin` và `Access-Control-Allow-Origin` |
| Network chỉ có `OPTIONS`, không có `POST` | Preflight thất bại | Response `OPTIONS`, method/header được cho phép |
| `fetch(..., {mode:'no-cors'})` có `status=0` | Opaque response | `response.type`, không dùng `status=0` để suy luận HTTP status |
| CORS hợp lệ nhưng API trả `403` | Server đã từ chối quyền | Log auth và authorization; không tùy tiện nới CORS |
| POST báo lỗi CORS nhưng dữ liệu đã đổi | Request chính đã xử lý trước khi quyền đọc bị chặn | Log, database, idempotency/CSRF |
| Server-to-server call thành công nhưng browser call thất bại | Chỉ browser bị SOP/CORS ràng buộc | Nguồn request, preflight và headers CORS |

## 10. Câu hỏi tự đánh giá

**Câu 1.** Browser script gọi `GET` sang API khác origin. API đã trả `200 OK`, nhưng Console báo lỗi CORS. API có chắc chưa nhận request không?

**Đáp án:** Không. Với request không cần preflight, API có thể nhận và trả response trước khi browser chặn script đọc. Kiểm tra Network và server log.

**Câu 2.** Browser gửi `OPTIONS`, API trả 405 và không thấy `POST`. Có thể kết luận `POST` đã thay đổi dữ liệu không?

**Đáp án:** Trong luồng preflight cụ thể này, browser chưa gửi **request POST chính**. Nhưng cần kiểm tra log và các luồng khác trước khi kết luận về trạng thái tổng thể.

**Câu 3.** Vì sao `mode: 'no-cors'` không giúp frontend lấy JSON?

**Đáp án:** Response xuyên origin trong trường hợp này bị lọc thành **opaque**, không cung cấp status thật, headers hoặc body cho JavaScript.

**Câu 4.** Website lạ không đọc được response của endpoint đổi email. Điều đó có đủ chống CSRF không?

**Đáp án:** Không. Request vẫn có thể được gửi và xử lý nếu cookie/phiên thỏa điều kiện. Server phải kiểm tra ý định (ví dụ CSRF token), xác thực, phân quyền và cookie policy thích hợp.

**Câu 5.** Tại sao ảnh tải được nhưng `getImageData()` lại bị `SecurityError`?

**Đáp án:** Quyền tải/hiển thị ảnh khác với quyền đọc pixel từ canvas. Ảnh cross-origin chưa đáp ứng cơ chế CORS phù hợp có thể làm canvas bị taint.

**Câu 6.** `https://app.example.com` và `https://api.example.com` có thể cùng site nhưng khác origin không? Điều này ảnh hưởng gì?

**Đáp án:** Có. Browser áp dụng CORS theo **origin** khi script cần đọc API; thuộc tính cookie `SameSite` dựa trên **site**, kết hợp các điều kiện cookie khác.

**Câu 7.** CORS cho phép origin `https://app.example.com` đọc dữ liệu của API. API có được bỏ kiểm tra quyền người dùng không?

**Đáp án:** Không. CORS không định danh người dùng hay phân quyền tài nguyên; các kiểm tra đó là trách nhiệm của server.

## Tài liệu tham khảo

- MDN — [Same-origin policy](https://developer.mozilla.org/en-US/docs/Web/Security/Same-origin_policy).
- MDN — [Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS) và [Using the Fetch API](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch).
- MDN — [Request: mode](https://developer.mozilla.org/en-US/docs/Web/API/Request/mode) và [Response: type](https://developer.mozilla.org/en-US/docs/Web/API/Response/type).
- MDN — [Using HTTP cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies), [Content Security Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP).
- OWASP Cheat Sheet Series — [Cross-Site Request Forgery Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html), [Cross Site Scripting Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html), [Clickjacking Defense](https://cheatsheetseries.owasp.org/cheatsheets/Clickjacking_Defense_Cheat_Sheet.html).
