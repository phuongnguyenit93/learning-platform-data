# Scheme, host, port: ba thành phần xác định origin của trang web

## 1. Tại sao phải phân biệt scheme, host và port?

Khi mở một trang web, trình duyệt cần trả lời một câu hỏi nền tảng: **mã JavaScript trong trang này được phép đọc và can thiệp vào tài nguyên của trang nào?** Đối với URL HTTP(S) thông thường, khái niệm **origin** là một trong những căn cứ chính để đưa ra quyết định đó.

Một origin gồm chính xác ba thành phần:

> **Origin = (scheme, host, port)**

Ví dụ, URL `https://shop.example.test:8443/products?id=10` có origin:

- **Scheme:** `https`
- **Host:** `shop.example.test`
- **Port:** `8443`

Path `/products`, query `?id=10` và fragment (nếu có) không tham gia định danh origin.

Bài này thuộc chương **Origin** của module **SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY**. Mục tiêu là nắm chính xác cách trình duyệt tách, chuẩn hóa và so sánh ba thành phần trên, từ đó hiểu Same-Origin Policy (SOP), CORS và các ranh giới liên quan đến cookie, iframe, JavaScript và API. Đây là kiến thức nền cho phòng vệ XSS, CSRF, clickjacking, CSP, Trusted Types và security headers: mọi cơ chế cần được áp dụng vào đúng ranh giới.

Sau khi học, bạn cần làm được những việc sau:

1. Phân tích một URL và chỉ ra scheme, host, port, path, query, fragment.
2. Xác định **same-origin** hay **cross-origin** giữa hai URL, kể cả trường hợp cổng mặc định hoặc host đã chuẩn hóa.
3. Phân biệt origin với site, domain, phạm vi cookie và quyền truy cập ở máy chủ.
4. Giải thích vì sao khác origin ảnh hưởng đến quyền đọc DOM và response nhưng không nhất thiết ngăn gửi request.
5. Tự kiểm chứng kết quả bằng `URL.origin`, DevTools và hai máy chủ chạy ở các cổng khác nhau.

## 2. Cấu trúc URL và vị trí của origin

Xét URL:

~~~text
https://alice:secret@portal.example.test:8443/admin/report?year=2026#summary
|---| |------------| |-----------------| |--| |-----------| |-------| |-----|
scheme    userinfo          host          port     path          query   fragment
~~~

Phân tách rõ:

| Thành phần | Giá trị ví dụ | Có thuộc origin? | Ý nghĩa |
| --- | --- | --- | --- |
| Scheme | `https` | **Có** | Giao thức hoặc lược đồ URL được sử dụng. |
| Username/password trong URL | `alice:secret` | **Không** | Dữ liệu userinfo theo cú pháp URL; không nên đặt thông tin bí mật trong URL. |
| Host | `portal.example.test` | **Có** | Tên host hoặc địa chỉ IP của đích. |
| Port | `8443` | **Có** | Cổng mà URL tham chiếu đến. |
| Path | `/admin/report` | Không | Vị trí tài nguyên trong origin. |
| Query | `year=2026` | Không | Tham số URL. |
| Fragment | `summary` | Không | Định danh một phần trong tài liệu, không gửi như một phần của HTTP request thông thường. |

Ví dụ từ JavaScript:

~~~js
const u = new URL(
  "https://portal.example.test:8443/admin/report?year=2026#summary"
);

console.log(u.protocol); // "https:"
console.log(u.hostname); // "portal.example.test"
console.log(u.port);     // "8443"
console.log(u.host);     // "portal.example.test:8443"
console.log(u.origin);   // "https://portal.example.test:8443"
console.log(u.pathname); // "/admin/report"
console.log(u.search);   // "?year=2026"
console.log(u.hash);     // "#summary"
~~~

**Lưu ý cách đặt tên trong URL API:**

- `hostname` biểu diễn host **không kèm cổng**.
- `host` của đối tượng `URL` chứa host và **cổng không mặc định nếu có**.
- `origin` là biểu diễn origin đã chuẩn hóa, thường có dạng `scheme://host[:port]`.
- `protocol` trả kèm dấu hai chấm, chẳng hạn `"https:"`. Khi diễn giải scheme bằng chữ, ta thường viết `https`.

Không nên phân tích URL bảo mật bằng cách tự `split("://")` hoặc cắt chuỗi theo dấu `:`. URL còn có userinfo, IPv6, dấu chấm cuối, ký tự Unicode và quy tắc chuẩn hóa; hãy dùng bộ phân tích URL chuẩn.

### 2.1. Origin không phải URL đầy đủ

Hai URL sau **cùng origin** dù dẫn đến tài nguyên khác nhau:

~~~text
https://portal.example.test/users/1?tab=profile#contact
https://portal.example.test/admin/settings?mode=advanced
~~~

Các đường dẫn `/users/1` và `/admin/settings` **không** tạo biên an toàn riêng trong trình duyệt. Nếu cùng origin, JavaScript thường có thể tương tác với tài nguyên cùng origin theo các chính sách áp dụng; máy chủ vẫn phải kiểm tra ai được xem hồ sơ, ai được sửa cấu hình quản trị.

Đường dẫn và cấu hình frontend không thay thế cơ chế **authorization**. Cookie có `Path=/admin` cũng không tự tạo một origin hoặc vùng JavaScript được cách ly riêng.

## 3. Scheme: phần đầu tiên của ranh giới

**Scheme** đứng trước dấu `:` trong URL, ví dụ `http:` và `https:`. Khi so sánh origin của URL web thông thường, **khác scheme là khác origin**, ngay cả khi host và cổng có vẻ liên quan.

| URL A | URL B | Kết quả |
| --- | --- | --- |
| `http://shop.example.test` | `https://shop.example.test` | **Cross-origin** vì khác scheme. |
| `https://shop.example.test/items` | `https://shop.example.test/login` | **Same-origin** vì scheme, host và port đều tương đương. |
| `https://shop.example.test:443` | `http://shop.example.test:443` | **Cross-origin** dù cùng cổng số `443`. |

`http` và `https` là hai scheme khác nhau; `https` có bảo vệ vận chuyển qua TLS, còn `http` thông thường thì không. Chuyển sang HTTPS thay đổi ranh giới origin của URL nếu trước đó ứng dụng chạy trên HTTP. Một số hành vi nhạy cảm còn yêu cầu **secure context**, được đánh giá theo quy tắc riêng; không nên suy rằng cứ “same-origin” là đủ quyền dùng camera hoặc micro.

Trình duyệt có thể **chặn mixed content** khi trang HTTPS yêu cầu một số tài nguyên HTTP. Đây là chính sách bổ sung, không phải quy tắc định nghĩa origin. Ngay cả khi một request bị chặn vì mixed content, hai URL vẫn được phân biệt origin qua scheme của chúng.

### 3.1. Chữ hoa/thường của scheme

URL parser chuẩn hóa scheme của URL web về chữ thường:

~~~js
new URL("HTTPS://shop.example.test/cart").origin
// "https://shop.example.test"
~~~

Do đó `HTTPS://shop.example.test` và `https://shop.example.test` có cùng origin sau khi được phân tích chuẩn. Đừng so sánh origin bằng chuỗi URL thô trước khi chuẩn hóa.

### 3.2. Scheme ngoài HTTP(S)

Quy tắc bộ ba thường được dạy cho **HTTP(S)**. Không nên máy móc áp dụng phép tách ba phần cho mọi loại URL:

- `data:` thường có **opaque origin**, không phải origin được xác định từ một host.
- `blob:` tạo trong một origin HTTP(S) thường mang origin của môi trường đã tạo blob URL.
- `about:blank` có thể kế thừa origin từ ngữ cảnh tạo ra nó; không thể xác định đầy đủ chỉ bằng nhìn chuỗi `about:blank`.
- `file:` có cách xử lý origin phụ thuộc trình duyệt và ngữ cảnh; không dùng như mô hình chuẩn cho thử nghiệm web có các quyền bảo mật.

Các trường hợp này sẽ được phân tích cụ thể ở mục 7.

## 4. Host: danh tính tên đích, không phải địa chỉ máy vật lý

**Host** trong URL web có thể là:

- Tên miền, ví dụ `app.example.test`.
- Địa chỉ IPv4, ví dụ `127.0.0.1`.
- Địa chỉ IPv6 đặt trong dấu ngoặc vuông theo cú pháp URL, ví dụ `[::1]`.

Host là thành phần nhận diện origin sau khi URL được phân tích. **Hai tên host trỏ đến cùng một máy chủ hoặc cùng một địa chỉ IP không mặc nhiên cùng origin.**

Ví dụ:

| URL | Quan hệ với `https://app.example.test` | Lý do |
| --- | --- | --- |
| `https://app.example.test/v1` | Same-origin | Chỉ thay path. |
| `https://api.example.test` | Cross-origin | Khác hostname. |
| `https://example.test` | Cross-origin | Bỏ subdomain cũng là khác host. |
| `https://APP.EXAMPLE.TEST` | Same-origin | Host DNS được chuẩn hóa về chữ thường. |
| `https://app.example.test.` | Cross-origin trong mô hình URL chuẩn | Dấu chấm cuối có thể được giữ trong biểu diễn host; không lấy việc DNS phân giải cùng chỗ làm căn cứ so origin. |

### 4.1. Subdomain không thừa hưởng quyền origin

`https://store.example.test` và `https://admin.example.test` là **hai origin khác nhau**, dù thuộc cùng tổ chức. JavaScript ở trang `store` không có quyền đọc DOM của tài liệu `admin` chỉ vì hai host cùng hậu tố `example.test`.

Ngược lại, một ứng dụng cũ ở `https://app.example.test/legacy` và trang mới ở `https://app.example.test/secure` vẫn cùng origin: **path không phải biên cách ly cho JavaScript**. Nếu nội dung có mức tin cậy khác nhau phải chạy độc lập, cần cân nhắc origin riêng kèm cơ chế trao đổi dữ liệu và xác thực thích hợp.

### 4.2. Host được chuẩn hóa

URL parser chuẩn hóa một số dạng biểu diễn của host:

- Tên host DNS được chuyển về chữ thường.
- Tên miền quốc tế hóa có thể được chuyển về dạng ASCII tương ứng (IDNA/Punycode).
- Địa chỉ IP có quy tắc phân tích và chuẩn hóa riêng.
- Cổng mặc định của scheme được loại bỏ khỏi biểu diễn URL chuẩn, dù cổng vẫn là thành phần logic của origin.

Ví dụ:

~~~js
const a = new URL("https://APP.EXAMPLE.TEST:443/catalog");
console.log(a.hostname); // "app.example.test"
console.log(a.port);     // "" vì 443 là cổng mặc định của HTTPS
console.log(a.origin);   // "https://app.example.test"
~~~

Đừng lấy việc hai tên miền phân giải về cùng địa chỉ IP làm phép so origin. Nếu dựa vào DNS hoặc hậu tố chuỗi để cấp quyền, ứng dụng có thể chấp nhận nhầm host của kẻ tấn công, chẳng hạn `app.example.test.attacker.test`.

### 4.3. Localhost và địa chỉ loopback

Các URL dưới đây **không tự động cùng origin**:

~~~text
http://localhost:3000
http://127.0.0.1:3000
http://[::1]:3000
~~~

Chúng có host khác nhau dù trong nhiều môi trường đều trỏ đến máy cục bộ. Đây là lỗi thử nghiệm thường gặp khi một ứng dụng được mở bằng `localhost` nhưng API hoặc cookie được cấu hình cho `127.0.0.1`. Kết quả CORS, cookie và quyền đọc có thể khác kỳ vọng.

## 5. Port: thành phần hay bị bỏ qua

**Port** là số cổng sau host trong URL, ví dụ `:3000`, `:8080`, `:8443`. Hai URL có **cùng scheme, cùng host, khác port** thì **cross-origin**.

~~~text
http://localhost:3000     → origin A
http://localhost:4000     → origin B
~~~

Dù cả hai chạy trên cùng máy, một trang ở cổng 3000 không tự được quyền đọc DOM hoặc phản hồi API từ cổng 4000.

### 5.1. Cổng mặc định và cổng được viết tường minh

Đối với scheme web thông dụng:

| Scheme | Cổng mặc định |
| --- | ---: |
| `http` | `80` |
| `https` | `443` |

Vì vậy, các cặp sau có cùng origin:

~~~text
http://app.example.test        == http://app.example.test:80
https://app.example.test       == https://app.example.test:443
~~~

Nhưng những cặp sau **khác origin**:

~~~text
https://app.example.test       != https://app.example.test:8443
http://app.example.test:443    != https://app.example.test:443
~~~

Trong JavaScript, thuộc tính `URL.port` trả chuỗi rỗng khi cổng không ghi rõ **hoặc** khi cổng ghi đúng mặc định và đã được chuẩn hóa:

~~~js
console.log(new URL("https://app.example.test").port);     // ""
console.log(new URL("https://app.example.test:443").port); // ""
console.log(new URL("https://app.example.test:8443").port); // "8443"
~~~

Giá trị rỗng của `URL.port` **không** có nghĩa “không tồn tại cổng”; origin vẫn có cổng hiệu lực `443` đối với HTTPS và `80` đối với HTTP.

### 5.2. Port trong origin khác với port của cookie

Cookie không được giới hạn theo cổng giống SOP. Một cookie phù hợp với host có thể được gửi tới các dịch vụ ở những cổng khác nhau của **cùng host**, tùy các thuộc tính cookie, scheme, ngữ cảnh và chính sách trình duyệt. Ví dụ, việc hai ứng dụng cùng chạy ở `localhost` nhưng khác port **không** làm cookie được tách theo port.

Điều này dễ gây nhầm: **storage và DOM theo origin** thường tách giữa cổng 3000 và 4000; **cookie** xét host/domain/path và các thuộc tính liên quan, không dùng port làm ranh giới độc lập.

## 6. Quy tắc quyết định same-origin chính xác

Đối với hai URL HTTP(S) đã được phân tích theo URL Standard:

> **Same-origin nếu và chỉ nếu scheme tương đương, host tương đương và port hiệu lực tương đương.**

Có thể mô tả:

~~~text
origin(A) == origin(B)
    ⇔ scheme(A) == scheme(B)
      AND host(A) == host(B)
      AND effectivePort(A) == effectivePort(B)
~~~

Port hiệu lực nghĩa là cổng tường minh, hoặc cổng mặc định của scheme khi URL không có cổng tường minh.

Lấy `https://shop.example.test` làm URL gốc:

| URL so sánh | Same-origin? | Thành phần quyết định |
| --- | --- | --- |
| `https://shop.example.test` | **Có** | Cùng bộ ba. |
| `https://shop.example.test/products/7` | **Có** | Path không tính. |
| `https://shop.example.test/?q=a#top` | **Có** | Query và fragment không tính. |
| `HTTPS://SHOP.EXAMPLE.TEST` | **Có** | Scheme và host được chuẩn hóa về chữ thường. |
| `https://shop.example.test:443` | **Có** | Cổng 443 là cổng mặc định của HTTPS. |
| `https://shop.example.test:444` | Không | Khác cổng. |
| `http://shop.example.test` | Không | Khác scheme. |
| `http://shop.example.test:443` | Không | Khác scheme, dù cùng số cổng 443. |
| `https://api.example.test` | Không | Khác host/subdomain. |
| `https://example.test` | Không | Khác host. |
| `https://shop.example.test.evil.test` | Không | Khác host; hậu tố tên dài không có nghĩa tin cậy. |
| `https://shop.example.test.` | Không | Host chuẩn của URL có dấu chấm cuối khác host không có dấu chấm cuối. |

### Sơ đồ ba câu hỏi

~~~mermaid
flowchart TD
    A["Hai URL HTTP(S) đã được parse"] --> B{"Scheme giống nhau?"}
    B -- "Không" --> X["Cross-origin"]
    B -- "Có" --> C{"Host đã chuẩn hóa giống nhau?"}
    C -- "Không" --> X
    C -- "Có" --> D{"Port hiệu lực giống nhau?"}
    D -- "Không" --> X
    D -- "Có" --> E["Same-origin"]
~~~

Đây là **phép so nguồn gốc của URL**, chưa phải kết luận một request có được xác thực, được cấp quyền, được gửi cookie hay được phép nhúng hay không.

### 6.1. Vì sao không dùng so sánh chuỗi tự viết?

Các cách kiểm tra sau đều dễ sai:

~~~js
// Sai: kiểm tra hậu tố có thể chấp nhận app.example.test.attacker.test.
candidateHost.includes("example.test");

// Sai: so URL đầy đủ khiến path/query khác nhau bị coi là khác origin.
urlA === urlB;

// Sai: bỏ port khiến localhost:3000 và localhost:4000 bị coi là cùng origin.
new URL(urlA).hostname === new URL(urlB).hostname;
~~~

Nếu cần xác định **quan hệ origin của hai URL HTTP(S) thông thường** trong môi trường JavaScript, dùng bộ phân tích URL:

~~~js
function sameHttpOrigin(left, right) {
  const a = new URL(left);
  const b = new URL(right);

  if (!["http:", "https:"].includes(a.protocol)) return false;
  if (!["http:", "https:"].includes(b.protocol)) return false;
  return a.origin === b.origin;
}

console.log(
  sameHttpOrigin(
    "https://SHOP.example.test:443/a",
    "https://shop.example.test/b"
  )
); // true

console.log(
  sameHttpOrigin(
    "http://localhost:3000",
    "http://localhost:4000"
  )
); // false
~~~

**Giới hạn:** Hàm minh họa chỉ dành cho URL HTTP(S) thông thường. Nó không mô hình hóa đầy đủ việc origin có thể là **opaque origin** với danh tính nội bộ riêng, hoặc ngữ cảnh tạo tài liệu `about:blank`, `sandbox`. Khi kiểm tra thông điệp cross-origin, sử dụng `event.origin` và đối tượng `event.source` theo ngữ cảnh, không thay bằng hàm so chuỗi URL tùy ý.

## 7. Khi origin không phải bộ ba thông thường

Khái niệm **opaque origin** rất quan trọng: có những tài liệu có origin đặc biệt, không tương đương với bất kỳ bộ ba `(scheme, host, port)` web thông thường nào.

| Nguồn tài liệu | Hành vi origin tiêu biểu | Cảnh báo |
| --- | --- | --- |
| Trang HTTP(S) thông thường | Tuple origin theo scheme, host, port | Có thể so bằng bộ ba đã chuẩn hóa. |
| `data:text/html,...` | Thường là opaque origin | Không tự nhận quyền của trang đã nhúng nó. |
| `iframe sandbox` không có `allow-same-origin` | Thường bị đưa vào opaque origin | Dù URL trông như URL cùng host, tài liệu vẫn có thể bị cách ly. |
| `about:blank` được tạo bởi trang | Có thể kế thừa origin của ngữ cảnh tạo ra nó | Phải xét cách tạo và ngữ cảnh tài liệu. |
| `blob:` tạo từ ngữ cảnh HTTP(S) | Thường gắn với origin của ngữ cảnh tạo blob URL | Không coi `blob:` đơn thuần là một host mới. |
| `file:` | Có quy tắc phụ thuộc trình duyệt | Không dựa vào đó để thiết kế chính sách web production. |

Khi một opaque origin cần được **serialize** thành chuỗi để hiển thị trong một số API, kết quả có thể là `"null"`. Điều đó **không** có nghĩa tất cả các tài liệu hiện ra chuỗi `"null"` có chung origin hay chung quyền. Opaque origin khác nhau vẫn có thể không cùng origin.

Ví dụ, một iframe sandbox:

~~~html
<iframe
  src="https://widget.example.test/preview"
  sandbox="allow-scripts"
  title="Xem trước"
></iframe>
~~~

Vì không có `allow-same-origin`, tài liệu iframe bị giới hạn origin theo cơ chế sandbox. Nếu iframe cần giao tiếp với trang cha, hãy dùng `postMessage` và kiểm tra nghiêm ngặt nguồn thông điệp; không chấp nhận bừa tất cả message với `event.origin === "null"`.

**Không nên cố “nới” origin bằng `document.domain`.** Cơ chế này đã lỗi thời, có tác động phụ về bảo mật và không hoạt động như một giải pháp tổng quát cho các API hoặc mô hình cách ly hiện đại. Thiết kế mới nên dùng origin rõ ràng và giao thức trao đổi giữa các context.

## 8. Bộ ba origin tác động thế nào đến Same-Origin Policy?

**Same-Origin Policy (SOP)** là tập hợp quy tắc trình duyệt giới hạn tương tác giữa các origin. Nó đặc biệt quan trọng với **quyền đọc dữ liệu** và **quyền truy cập DOM**, nhưng không đồng nghĩa việc “cross-origin không thể gửi bất kỳ request nào”.

Giả sử có:

~~~text
Trang A: https://app.example.test/
Trang B: https://api.example.test/data
Trang C: https://app.example.test:8443/
~~~

Cả B và C đều cross-origin so với A: B khác host; C khác port.

| Hành động của JavaScript/trình duyệt từ A | Cùng origin | Khác origin |
| --- | --- | --- |
| Đọc DOM của iframe | Thường được nếu không có hạn chế bổ sung | Thường bị SOP chặn. |
| Truy cập `localStorage` | Theo origin của tài liệu, trong những giới hạn chính sách hiện hành | Không mặc nhiên dùng chung. |
| Gửi request qua `fetch` | Bình thường; vẫn chịu CSP, network, auth | Có thể gửi; quyền **đọc response** thường chịu CORS. |
| Gửi biểu mẫu HTML đến URL khác | Có thể | Thường cũng có thể; CSRF là mối lo riêng. |
| Tải hình ảnh, stylesheet hoặc script từ URL khác | Thường có | Thường có theo các quy tắc tải/nhúng tương ứng. |
| Đọc response JSON bằng JavaScript | Có thể nếu endpoint cho phép và request thành công | Cần CORS cho quyền đọc trong trường hợp thông thường. |

Một URL cùng origin chỉ giải quyết **quan hệ nguồn gốc của tài liệu**. Quyền xem dữ liệu khách hàng, quyền cập nhật sản phẩm hay quyền quản trị phải được **máy chủ xác nhận** qua authentication và authorization.

### 8.1. Vì sao tải script bên ngoài lại cần đặc biệt cẩn thận?

~~~html
<script src="https://cdn.vendor.test/widget.js"></script>
~~~

Dù `cdn.vendor.test` khác origin, mã JavaScript được tải qua `<script src>` thông thường **chạy với quyền của trang nhúng**, không tự ở trong một origin sandbox của CDN. Do đó script bên thứ ba có thể tạo rủi ro XSS hoặc chuỗi cung ứng bên trong origin tin cậy của ứng dụng.

Biện pháp đúng tùy ngữ cảnh: chỉ cấp nguồn script cần thiết qua CSP `script-src`, cân nhắc SRI cho tài nguyên tĩnh và tách nội dung ít tin cậy sang iframe khác origin/sandbox. Trusted Types giúp kiểm soát một số sink DOM nguy hiểm, nhưng không biến script bên thứ ba thành ứng dụng cách ly.

### 8.2. Vì sao các đường dẫn khác nhau không tạo ranh giới mới?

~~~text
https://app.example.test/user
https://app.example.test/admin
~~~

Hai trang cùng origin. Không nên dựa vào ý tưởng “mã ở /user không thể chạm /admin”. Chỉ chặn hiển thị nút quản trị, đặt prefix path hoặc giới hạn cookie bằng `Path` đều không phải cách thay thế bảo vệ quyền ở máy chủ.

## 9. Origin trong CORS và giao tiếp API

CORS (**Cross-Origin Resource Sharing**) cho phép máy chủ quyết định origin nào được trình duyệt cho phép JavaScript **đọc response cross-origin**.

Ví dụ ứng dụng frontend ở `https://app.example.test` đọc API `https://api.example.test`:

~~~http
GET /v1/profile HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
~~~

Header `Origin` mang **origin của bên khởi tạo request** trong những ngữ cảnh áp dụng, không chứa path, query hay fragment. Một giá trị Origin hợp lệ kiểu HTTP(S) có dạng `https://app.example.test` hoặc `https://app.example.test:8443` nếu dùng cổng khác mặc định.

Máy chủ API có thể cho phép origin cụ thể:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Access-Control-Allow-Origin: https://app.example.test
Vary: Origin
~~~

Nếu dùng cookie hoặc các credentials cần thiết trong một request CORS, máy chủ thường cần các header thích hợp:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Khi JavaScript gửi credentials cross-origin, mã có thể dùng:

~~~js
fetch("https://api.example.test/v1/profile", {
  credentials: "include"
});
~~~

Một số quy tắc quan trọng:

1. Nếu cho phép CORS kèm credentials, không sử dụng `Access-Control-Allow-Origin: *` cho response đó. Cần chỉ định origin được phép và thiết lập `Access-Control-Allow-Credentials: true` tương ứng.
2. Với allowlist động, so sánh **origin đầy đủ và đã chuẩn hóa**, gồm scheme/host/port. Tránh so bằng hậu tố chuỗi hoặc tự động phản chiếu mọi giá trị `Origin`.
3. `Vary: Origin` là tín hiệu hữu ích cho cache khi nội dung/header response thay đổi theo origin được phép.
4. Một số request phải **preflight** bằng `OPTIONS`; request đơn giản hoặc biểu mẫu HTML thông thường có thể được gửi mà không cần preflight.
5. Header `Origin` có thể vắng mặt hoặc có giá trị `null` trong những ngữ cảnh nhất định. Máy chủ không nên tin `null` là một danh tính origin đáng tin cậy.
6. `curl` và những client ngoài trình duyệt không chịu SOP/CORS như JavaScript trên trang web. Không nên lấy CORS làm xác thực hoặc kiểm soát truy cập dữ liệu trên máy chủ.

**Điểm mấu chốt:** Lỗi CORS ở Console thường có nghĩa JavaScript bị từ chối **đọc** response; request có thể đã được gửi và xử lý. Chức năng thay đổi trạng thái cần bảo vệ CSRF, xác thực và phân quyền ngay tại backend.

### 9.1. CORS khác với CSP `connect-src`

- **CORS:** API phản hồi cho trình duyệt biết origin nào được quyền đọc response theo giao thức CORS.
- **CSP `connect-src`:** trang ứng dụng giới hạn nguồn kết nối mà JavaScript của trang được phép tạo bằng một số API, như `fetch`/XHR/WebSocket.

Ví dụ chính sách frontend chỉ cho phép kết nối đến API của mình:

~~~http
Content-Security-Policy: default-src 'self'; connect-src 'self' https://api.example.test
~~~

Header này do **ứng dụng frontend** đặt để giới hạn kết nối; phía API vẫn cần CORS hợp lệ và kiểm tra quyền. Hai chính sách bổ trợ nhau ở hai phía của ranh giới.

## 10. Origin, site và cookie: ba khái niệm không được trộn

**Origin** xét scheme + host + port. **Site** trong mô hình *schemeful same-site* chủ yếu xét scheme và registrable domain (theo Public Suffix List). Các subdomain có thể **khác origin nhưng cùng site**.

| Hai URL | Quan hệ origin | Quan hệ site |
| --- | --- | --- |
| `https://app.example.test` và `https://api.example.test` | Cross-origin | Same-site |
| `https://app.example.test` và `https://app.example.test:8443` | Cross-origin | Same-site |
| `https://app.example.test` và `http://app.example.test` | Cross-origin | Cross-site theo mô hình schemeful |
| `https://app.example.test` và `https://other.test` | Cross-origin | Cross-site |

Điểm này ảnh hưởng trực tiếp đến bảo mật cookie:

- **`SameSite`** quyết định gửi cookie theo ngữ cảnh same-site/cross-site và một số quy tắc điều hướng/request, **không** phải phép so origin gồm port.
- **`Domain`** quyết định host nào có thể nhận cookie; cookie host-only không tự mở rộng sang mọi subdomain.
- **`Path`** giới hạn đường dẫn request gửi cookie, nhưng không phải ranh giới quyền JavaScript mạnh.
- **`Secure`** yêu cầu điều kiện truyền tải an toàn theo quy tắc browser; **`HttpOnly`** ngăn JavaScript đọc cookie qua `document.cookie`.
- Cookie không cách ly theo port; một số cơ chế lưu trữ như `localStorage` lại được cách ly theo origin, ngoài các quy tắc partitioning hiện đại.

Ví dụ cookie phiên với phạm vi host hẹp:

~~~http
Set-Cookie: __Host-session=opaque-value; Secure; HttpOnly; Path=/; SameSite=Lax
~~~

Prefix `__Host-` yêu cầu `Secure`, `Path=/` và không có thuộc tính `Domain` trong những trình duyệt hỗ trợ, giúp giảm rủi ro mở rộng phạm vi cookie sang subdomain khác. Tuy nhiên, cookie này **không** là giải pháp duy nhất chống CSRF; máy chủ phải thực hiện các kiểm tra cần thiết.

### 10.1. Sai lầm phổ biến với subdomain

Giả sử ứng dụng chính chạy tại `https://app.example.test` và một ứng dụng cũ, ít được kiểm soát chạy tại `https://legacy.example.test`. Hai trang **cross-origin** nhưng **same-site**. Nếu `legacy` bị XSS hoặc bị chiếm quyền, chỉ đặt `SameSite=Lax` hoặc `SameSite=Strict` có thể không ngăn một số yêu cầu same-site đến hệ thống đích.

Chống CSRF phải xét đúng luồng, token, nguồn request, phân quyền máy chủ và phạm vi cookie; **khác origin** không có nghĩa tự động **khác site**, và same-site không đồng nghĩa “đáng tin”.

## 11. Thực hành A: xác định origin bằng JavaScript

Mở DevTools → **Console** của một trang web và chạy:

~~~js
const examples = [
  "https://shop.example.test",
  "https://shop.example.test:443/cart",
  "https://shop.example.test:8443/cart",
  "HTTPS://SHOP.EXAMPLE.TEST/path",
  "http://shop.example.test:80",
  "http://shop.example.test:443",
  "https://api.example.test",
  "http://localhost:3000",
  "http://localhost:4000",
  "http://127.0.0.1:3000"
];

console.table(
  examples.map((input) => {
    const u = new URL(input);
    return {
      input,
      scheme: u.protocol,
      hostname: u.hostname,
      port: u.port || "(default)",
      origin: u.origin
    };
  })
);
~~~

Những kết luận cần tự nhìn thấy:

- `https://shop.example.test` và URL có `:443` cho **cùng** `origin`.
- URL HTTPS có `:8443` tạo **origin khác**.
- Host hoặc scheme viết hoa được chuẩn hóa.
- `http://shop.example.test:80` có origin **khác** HTTPS của cùng host.
- `localhost:3000` và `localhost:4000` khác origin, dù cùng hostname.
- `localhost` và `127.0.0.1` khác origin, dù thường đều chỉ máy cục bộ.

Dùng `new URL()` cũng cho biết chính xác port nào bị chuẩn hóa. Đừng suy cổng hiệu lực chỉ từ `u.port === ""`.

## 12. Thực hành B: quan sát hai origin trên cùng máy

Bài thử dưới đây dùng **hai máy chủ thử nghiệm do bạn kiểm soát**:

- **Frontend:** `http://localhost:3000`
- **API:** `http://localhost:4000`

Bạn có thể dùng công cụ phát triển web hiện có để chạy mỗi máy chủ. Cần cấu hình API có endpoint `GET /hello` trả JSON và **ban đầu không trả header CORS**. Để dễ quan sát, API nên ghi log khi nhận request.

### Bước 1 — Nhìn đúng bộ ba

Trong Console của trang frontend, chạy:

~~~js
console.log(location.origin); // "http://localhost:3000"
console.log(new URL("http://localhost:4000/hello").origin);
// "http://localhost:4000"
~~~

Hai origin khác nhau **chỉ vì port**.

### Bước 2 — Gửi request cross-origin

~~~js
fetch("http://localhost:4000/hello")
  .then((r) => r.json())
  .then(console.log)
  .catch((err) => console.error("Fetch thất bại:", err));
~~~

Quan sát trong **Network** và **Console**:

- Nếu API không có CORS header hợp lệ, JavaScript thường gặp lỗi liên quan CORS và không đọc được body của response.
- Tab Network hoặc log API có thể cho thấy request **đã được gửi và đã được xử lý**.
- Chặn đọc response không có nghĩa trình duyệt nhất thiết ngăn gửi toàn bộ request.

### Bước 3 — Cho phép đúng origin

Trên endpoint API, thêm response header:

~~~http
Access-Control-Allow-Origin: http://localhost:3000
Vary: Origin
~~~

Tải lại frontend rồi gọi `fetch`. Với response và chính sách khác không thay đổi, JavaScript có thể đọc JSON. Nếu đổi frontend sang `http://localhost:3001` mà API chỉ cho phép `:3000`, yêu cầu đọc response từ origin mới không được cấp quyền.

**Đừng vô tình hiểu sai:** Thí nghiệm này dùng request GET đơn giản và không cần cookie. Nếu thử thêm method/header gây preflight hoặc credentials, trình duyệt có thể có request `OPTIONS` và yêu cầu thêm các CORS header khác. Cần đọc từng request trong Network để xác định điều đã xảy ra.

### Bước 4 — Phân biệt quyền đọc và quyền nghiệp vụ

Giả sử API có endpoint cập nhật địa chỉ. Cấu hình CORS cho phép origin `:3000` **không** biến mọi người dùng từ frontend đó thành người có quyền sửa địa chỉ. Backend vẫn phải xác thực phiên, kiểm tra chủ sở hữu bản ghi, chống CSRF khi dùng cơ chế cookie phù hợp và kiểm tra dữ liệu nghiệp vụ. Những kiểm soát này hoạt động độc lập với phép so origin.

## 13. Thực hành C: iframe và ranh giới đọc DOM

Giả sử bạn kiểm soát hai trang HTML ở `http://localhost:3000` và `http://localhost:4000`. Trang ở cổng 3000 nhúng iframe ở cổng 4000:

~~~html
<iframe
  id="external"
  src="http://localhost:4000/"
  title="Trang thử nghiệm khác origin"
></iframe>
~~~

Trong Console của trang cha, sau khi iframe tải xong:

~~~js
const frame = document.querySelector("#external");

try {
  console.log(frame.contentWindow.document.title);
} catch (err) {
  console.log("Không đọc được DOM khác origin:", err.name);
}
~~~

Dự kiến trình duyệt từ chối truy cập trực tiếp vì iframe và trang cha khác **port**, tức khác origin. Kết quả cụ thể tùy browser và chính sách bổ sung.

Để giao tiếp có kiểm soát, sử dụng `postMessage`:

~~~js
frame.contentWindow.postMessage(
  { type: "ping" },
  "http://localhost:4000"
);
~~~

Phía iframe phải kiểm tra `event.origin`, `event.source` và dữ liệu trước khi xử lý; trang cha cũng phải làm tương tự khi nhận phản hồi. **Cấp kênh gửi message không đồng nghĩa cấp quyền đọc DOM cross-origin.**

Một iframe còn có thể chịu hạn chế `sandbox`, CSP `frame-ancestors` và các header liên quan đến cách ly. Ví dụ trang được nhúng có thể chặn nhúng từ mọi origin bằng:

~~~http
Content-Security-Policy: frame-ancestors 'none'
~~~

Đây là biện pháp giúp chống **clickjacking**, khác với phép so bộ ba origin của SOP. Nó kiểm soát **trang nào được nhúng**, còn SOP kiểm soát nhiều dạng **truy cập giữa các tài liệu**.

## 14. Checklist đọc origin khi review bảo mật

Dùng checklist dưới đây khi có một frontend mới, API mới, subdomain mới hoặc cổng phát triển mới:

- [ ] Xác định scheme, host và **cổng hiệu lực** của từng URL.
- [ ] Chuẩn hóa URL bằng bộ phân tích chuẩn; không so bằng hậu tố chuỗi domain.
- [ ] Phân biệt path/query/fragment với bộ ba origin; kiểm soát quyền nghiệp vụ ở máy chủ.
- [ ] Xác định quan hệ **same-origin**, **cross-origin**, sau đó mới đánh giá riêng **same-site/cross-site**.
- [ ] Với API cross-origin, cấu hình CORS trên allowlist origin đầy đủ; xác minh trường hợp credentials và preflight.
- [ ] Kiểm tra cookie theo host/domain/path, `Secure`, `HttpOnly` và `SameSite`; đừng coi port là biên cookie.
- [ ] Khi có iframe, kiểm tra SOP, `sandbox`, `postMessage`, CSP `frame-ancestors` và quyền nhúng.
- [ ] Với script ngoài, nhớ script `<script src>` thường có quyền của trang nhúng; cân nhắc CSP/SRI và tách origin theo độ tin cậy.
- [ ] Nếu gặp URL `data:`, `blob:`, `about:blank`, `file:` hoặc tài liệu sandbox, kiểm tra **ngữ cảnh origin** thay vì cố tách bộ ba.
- [ ] Trong DevTools, đối chiếu địa chỉ trang, `Origin` request header, CORS response headers và request thực tế đã đi tới server hay chưa.

### Những nhầm lẫn cần tránh

| Nhận định | Đúng hay sai? | Giải thích |
| --- | --- | --- |
| “Khác đường dẫn `/admin` thì khác origin.” | **Sai** | Path không thuộc bộ ba. |
| “`https://example.test` khác origin với `https://example.test:443`.” | **Sai** | `443` là cổng mặc định của HTTPS. |
| “`localhost:3000` và `localhost:4000` cùng máy nên cùng origin.” | **Sai** | Khác port. |
| “`http` và `https` của cùng host luôn cùng origin.” | **Sai** | Khác scheme. |
| “Hai subdomain cùng site luôn cùng origin.” | **Sai** | Host khác nhau, dù có thể same-site. |
| “Cookie và localStorage luôn cách ly giống nhau.” | **Sai** | Cookie không tách theo port như origin-based storage. |
| “CORS chặn mọi request cross-origin.” | **Sai** | CORS chủ yếu chi phối quyền JavaScript đọc response. |
| “Một API same-origin không cần kiểm tra phân quyền.” | **Sai** | Quyền nghiệp vụ thuộc máy chủ. |
| “Mọi origin được serialize thành `null` đều là một origin.” | **Sai** | Opaque origins có thể khác nhau dù cùng biểu diễn chuỗi. |

## 15. Kết nối với bảo mật ứng dụng web

Một cách đánh giá ngắn gọn cho từng luồng trong ứng dụng:

~~~mermaid
flowchart LR
    A["URL của trang / script / iframe"] --> B["Parse scheme + host + port"]
    B --> C["Xác định same-origin / cross-origin"]
    C --> D["SOP: DOM, storage, đọc response"]
    C --> E["CORS: API có cho JS đọc response?"]
    B --> F["So site + cookie policy"]
    D --> G["Server: xác thực, phân quyền, CSRF"]
    E --> G
    F --> G
    G --> H["Kết quả an toàn của thao tác"]
~~~

**Scheme, host, port xác định origin; origin là căn cứ của nhiều quy tắc cách ly trong trình duyệt, nhưng không tự cấp quyền nghiệp vụ.** Việc biết chính xác ba thành phần này giúp tránh lỗi cấu hình CORS, sai phạm vi cookie, nhầm lẫn port trong môi trường local, và thiết kế cách ly sai cho subdomain hoặc iframe.

Ở các chủ đề tiếp theo về XSS, CSRF và clickjacking, hãy luôn hỏi trước: **dữ liệu hoặc mã đang chạy ở origin nào, có thể đọc gì, có thể gửi gì, và kiểm tra cuối cùng đang được thực thi ở trình duyệt hay ở máy chủ?**
