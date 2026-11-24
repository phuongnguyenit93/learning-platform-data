# Data read isolation — cách Same-Origin Policy cô lập quyền đọc dữ liệu

> **Chương:** Same-origin policy  
> **Trọng tâm:** Phân biệt quyền **gửi yêu cầu**, **hiển thị tài nguyên** và **đọc nội dung dữ liệu** giữa những origin. Giải thích vì sao trình duyệt cần ranh giới này, cách nó hoạt động với DOM, Fetch/CORS, cookie, storage và canvas, cũng như cách kiểm chứng và bổ sung phòng vệ cho ứng dụng web.

## 1. Vì sao cần cô lập quyền đọc dữ liệu?

Hãy tưởng tượng người dùng đang đăng nhập tại `https://bank.example.com` và đồng thời mở `https://news.example.net`. Trang tin có thể chứa JavaScript hoàn toàn do bên thứ ba kiểm soát. Nếu đoạn mã đó tự do đọc DOM, phản hồi API hoặc thông tin phiên của trang ngân hàng, chỉ riêng hành động mở trang tin cũng có thể làm lộ dữ liệu tài chính.

Trình duyệt phải chạy nhiều website trong cùng một ứng dụng nhưng giữ **ranh giới tin cậy** giữa chúng. Một trong những cơ chế nền tảng là **Same-Origin Policy (SOP)**: script ở một origin thường bị hạn chế đọc tài liệu và dữ liệu được bảo vệ thuộc origin khác.

Trong chủ đề **Data read isolation**, từ khóa quan trọng nhất là **đọc**:

- Một trang có thể **gửi** một số request chéo origin, nhưng script có thể **không được đọc** nội dung response.
- Một trang có thể **hiển thị** iframe hoặc hình ảnh từ origin khác, nhưng script có thể **không được đọc** DOM của iframe hoặc pixel của hình ảnh khi vẽ lên canvas.
- Trình duyệt có thể **đính kèm cookie** vào request theo chính sách cookie, trong khi script của trang khác **không được đọc** giá trị cookie đó qua API JavaScript.

Vì thế, câu hỏi “Trang A có truy cập được trang B không?” chưa đủ chính xác. Cần hỏi: **A đang thực hiện hành động nào trên loại dữ liệu nào của B, và cơ chế nào kiểm soát hành động đó?**

## 2. Origin là ranh giới nào?

Với URL HTTP(S) thông thường, origin được xác định bởi bộ ba:

```text
origin = scheme + hostname + port
Ví dụ: https://app.example.com:443
```

Origin không bao gồm đường dẫn, query string hay fragment. Port mặc định của HTTPS là `443`, của HTTP là `80`.

| URL được so với `https://app.example.com/account` | Cùng origin? | Giải thích |
| --- | --- | --- |
| `https://app.example.com/orders` | Có | Cùng scheme, hostname, port hiệu lực |
| `https://app.example.com:443/orders` | Có | `:443` là cổng HTTPS mặc định |
| `http://app.example.com/account` | Không | Khác scheme |
| `https://api.example.com/account` | Không | Khác hostname |
| `https://app.example.com:8443/account` | Không | Khác port |
| `https://app.example.com/account?tab=history` | Có | Query không tham gia xác định origin |

**Site** không đồng nghĩa với **origin**. Trong mô hình *schemeful same-site*, `https://app.example.com` và `https://api.example.com` có thể cùng site (cùng scheme và tên miền có thể đăng ký `example.com`) nhưng **khác origin**. Cookie `SameSite` chủ yếu xét quan hệ site; SOP chủ yếu xét quan hệ origin. Một subdomain cùng site không đương nhiên được đọc DOM hoặc `localStorage` của subdomain còn lại.

Một số tài liệu có **opaque origin**, không thể biểu diễn bằng bộ ba thông thường. Ví dụ phổ biến là tài liệu trong `iframe sandbox` không có `allow-same-origin`. Opaque origin không được coi là cùng origin với trang cha chỉ vì nội dung được nhúng từ cùng host.

Các URL đặc biệt có quy tắc riêng: `about:blank` và `srcdoc` thường kế thừa origin từ ngữ cảnh tạo/nhúng trong những điều kiện thích hợp; `data:` thường tạo opaque origin; `blob:` thường gắn với origin của môi trường tạo ra nó. Không suy luận quyền đọc chỉ từ chuỗi URL trong thanh địa chỉ.

## 3. Quyền gửi, nhúng và đọc là ba việc khác nhau

| Hành động | Ví dụ | SOP và chính sách liên quan |
| --- | --- | --- |
| **Gửi request** | Form gửi `POST` hoặc `fetch` tới host khác | Một số request chéo origin được gửi; có thể cần preflight và chịu các hạn chế khác |
| **Đọc response trong script** | `fetch(...).then(r => r.json())` | Thường cần đáp ứng CORS nếu response khác origin |
| **Hiển thị tài nguyên** | `<img>`, `<iframe>`, `<script src>` | Nhiều loại tài nguyên có thể nhúng chéo origin, tùy chính sách riêng |
| **Đọc DOM iframe** | `iframe.contentWindow.document` | SOP chặn khi iframe khác origin |
| **Đọc pixel canvas** | `canvas.toDataURL()` sau khi vẽ ảnh khác origin | Canvas có thể bị *taint* nếu ảnh chưa được cho phép đọc chéo origin |
| **Đọc dữ liệu lưu trữ** | `localStorage`, IndexedDB, `document.cookie` | Ràng buộc origin, phạm vi cookie và các cơ chế phân vùng/bảo vệ tương ứng |

Ví dụ `https://shop.example.com` có thể chèn một hình ảnh từ `https://cdn.example.net/logo.png`. Việc hình ảnh xuất hiện trên màn hình **không chứng minh** JavaScript của trang shop có quyền đọc mọi byte của hình ảnh đó. Tương tự, một iframe có thể được hiển thị mà DOM bên trong vẫn bị SOP bảo vệ.

Về kiến trúc, SOP cần được hiểu là **chính sách truy cập dữ liệu cho các ngữ cảnh web**. Sandbox tiến trình và cách ly site hỗ trợ một lớp bảo vệ khác ở mức engine/OS. Không nên suy luận rằng vì hai trang đang chạy cùng hoặc khác tiến trình thì JavaScript được quyền vượt SOP.

## 4. DOM và Window: nhìn thấy iframe không có nghĩa đọc được nó

Giả sử trang `https://shop.example.com` nhúng trang `https://account.example.net`:

```html
<iframe
  id="account"
  src="https://account.example.net/profile"
  title="Tài khoản khách hàng"
></iframe>
```

JavaScript của trang cha có thể nhận đối tượng tham chiếu đến cửa sổ của iframe, nhưng không được tùy ý truy cập thuộc tính nhạy cảm:

```js
const frame = document.querySelector("#account");

try {
  console.log(frame.contentWindow.document.body.textContent);
} catch (error) {
  console.error(error.name); // Thường là SecurityError
}
```

**Giải thích:** `contentWindow` là một tham chiếu đến đối tượng cửa sổ; nó **không** cấp quyền đọc DOM khác origin. Trình duyệt chỉ cho phép một tập thao tác hạn chế với cửa sổ chéo origin, ví dụ sử dụng `postMessage` theo quy tắc của API. Đọc `window.location.href` của cửa sổ khác origin thường cũng bị hạn chế; một số thao tác điều hướng/ghi có quy tắc khác và còn phụ thuộc điều kiện điều hướng.

SOP cũng giới hạn chiều ngược lại: script trong iframe khác origin không thể tự đọc DOM của trang cha. Nếu iframe được gắn `sandbox`, các quyền còn có thể bị thu hẹp thêm, chẳng hạn không cho script chạy hoặc ép tài liệu vào opaque origin.

### Trao đổi dữ liệu có chủ đích bằng `postMessage`

Khi cần chia sẻ **một phần** dữ liệu giữa trang cha và iframe, hãy thiết kế giao thức thông điệp thay vì tìm cách “tắt SOP”:

```js
// Trong trang cha: https://shop.example.com
const frame = document.querySelector("#account");
const partnerOrigin = "https://account.example.net";

frame.addEventListener("load", () => {
  frame.contentWindow.postMessage(
    { type: "REQUEST_DISPLAY_NAME" },
    partnerOrigin
  );
});

window.addEventListener("message", (event) => {
  if (event.origin !== partnerOrigin) return;
  if (event.source !== frame.contentWindow) return;
  if (!event.data || event.data.type !== "DISPLAY_NAME") return;
  if (typeof event.data.value !== "string") return;

  document.querySelector("#display-name").textContent = event.data.value;
});
```

Ví dụ giả định tài liệu con thực sự dùng origin `https://account.example.net`; nó cần tự kiểm tra origin của trang cha và kiểm tra quyền trước khi trả dữ liệu. **Không dùng `targetOrigin: "*"` khi gửi dữ liệu nhạy cảm.** Cũng không kiểm tra origin bằng phép so sánh chuỗi hậu tố dễ nhầm như `endsWith("example.net")`, vì một host giả mạo có thể chứa chuỗi đó.

Với iframe mang opaque origin, `event.origin` có thể là `"null"`. Không coi mọi thông điệp đến từ `"null"` đều đáng tin: nhiều tài liệu không liên quan cũng có thể có opaque origin. Khi cần giao tiếp với iframe dạng này, phải thiết kế một cơ chế xác nhận nguồn/giao thức thích hợp với mức nhạy cảm của dữ liệu.

## 5. Fetch và CORS: request đã đi nhưng response vẫn có thể không đọc được

Giả sử trang `https://app.example.com` gọi API `https://api.example.com/private`:

```js
async function loadPrivateData() {
  const response = await fetch("https://api.example.com/private");
  return response.json();
}

loadPrivateData()
  .then(console.log)
  .catch((error) => console.error("Không được đọc response:", error));
```

Vì hai URL khác hostname, request là **cross-origin**. Theo CORS, API có thể cho phép script tại `app.example.com` đọc response bằng header:

```http
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin
```

Nếu response không có chính sách CORS cho phép và không thỏa những điều kiện áp dụng, Promise `fetch` có thể bị từ chối với lỗi kiểu `TypeError` và Console báo vi phạm CORS. Việc thất bại ở JavaScript **không đủ** để kết luận server chưa nhận request; phải xem bản ghi mạng và server.

### Bốn trường hợp cần phân biệt

| Trường hợp | Request được gửi? | Script đọc body được? |
| --- | --- | --- |
| `fetch` cùng origin, server trả response hợp lệ | Thông thường có | Có, nếu không bị giới hạn riêng |
| `fetch` khác origin, server cho phép CORS hợp lệ | Có, khi các kiểm tra liên quan thành công | Có |
| `fetch` khác origin, server không cho phép CORS | Tùy loại request: có thể đã gửi; preflight có thể chặn request thực | Không |
| `fetch` khác origin với `mode: "no-cors"` | Có thể được gửi trong giới hạn của chế độ này | Không đọc nội dung response opaque |

`mode: "no-cors"` **không phải** mẹo vô hiệu hóa CORS. Ví dụ:

```js
const response = await fetch("https://cdn.example.net/data.txt", {
  mode: "no-cors",
});

console.log(response.type);   // "opaque"
console.log(response.status); // 0, không thấy HTTP status thực
// Không thể dùng response này để đọc body thật.
```

Response opaque cố ý che trạng thái, header và body với JavaScript, dù trình duyệt đã tải tài nguyên phục vụ mục đích được phép. Khi dùng `no-cors`, phương thức và header có thể bị giới hạn; không thể tùy ý gửi mọi loại request như với CORS.

### Preflight không đồng nghĩa authorization

Một số request chéo origin phải có request `OPTIONS` kiểm tra trước (*preflight*), chẳng hạn khi dùng `Content-Type: application/json` với phương thức `POST`:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: POST
Access-Control-Allow-Headers: Content-Type
```

Máy chủ có thể từ chối preflight khiến request thực không được gửi. Nhưng preflight chỉ phục vụ kiểm tra chia sẻ tài nguyên của browser; nó **không thay thế** đăng nhập, kiểm tra quyền truy cập đối tượng hoặc kiểm soát thay đổi trạng thái tại server.

Với request có credentials, có thể cần `fetch(url, { credentials: "include" })`, header `Access-Control-Allow-Credentials: true` và giá trị `Access-Control-Allow-Origin` chỉ rõ origin được phép (không dùng `*`). Cookie vẫn phải đáp ứng điều kiện `SameSite`, `Secure` và chính sách browser. Server phải kiểm tra quyền trước khi trả dữ liệu, bất kể CORS cấu hình thế nào.

## 6. Cookie và web storage: cùng trang đăng nhập không có nghĩa cùng quyền đọc

### Cookie được gửi theo phạm vi cookie, không theo SOP của JavaScript

Cookie có những thuộc tính riêng như `Domain`, `Path`, `Secure`, `HttpOnly` và `SameSite`. Khác với origin, **cookie thông thường không phân biệt port**. Vì vậy, hai ứng dụng cùng host `localhost` ở cổng `8000` và `8001` là **hai origin khác nhau** nhưng có thể dùng chung một số cookie theo phạm vi host/path.

Ví dụ cookie phiên do server đặt:

```http
Set-Cookie: __Host-session=opaque-session-value; Path=/; Secure; HttpOnly; SameSite=Lax
```

- `HttpOnly` ngăn mã JavaScript đọc giá trị cookie qua `document.cookie`, kể cả script cùng origin; cookie vẫn có thể được trình duyệt đính kèm vào request phù hợp.
- `Secure` giới hạn cookie vào ngữ cảnh truyền tải an toàn; `SameSite` điều chỉnh một phần hành vi gửi cookie theo quan hệ **site**.
- Prefix `__Host-` đòi hỏi `Secure`, `Path=/`, không có `Domain` ở browser hỗ trợ, giúp thu hẹp khả năng host khác ghi đè cookie.

Đặt `SameSite=Lax` không tạo ra quyền đọc chéo origin và cũng không đảm bảo loại trừ mọi tình huống CSRF. Các subdomain cùng site có thể khác origin, nên server vẫn cần kiểm tra CSRF khi cần và xác thực quyền trên từng request nhạy cảm.

### `localStorage` và IndexedDB

Các API như `localStorage` và IndexedDB về cơ bản được tổ chức theo origin, nên script tại `https://shop.example.com` không được trực tiếp mở `localStorage` của `https://api.example.com`. Một số trình duyệt còn phân vùng lưu trữ theo top-level site, nhất là trong ngữ cảnh bên thứ ba, làm tăng hạn chế.

Không lưu bí mật nhạy cảm trong `localStorage` với giả định “SOP đã bảo vệ hoàn toàn”. Nếu ứng dụng bị **XSS**, script độc hại chạy **trong chính origin đó** thường có thể đọc dữ liệu mà script hợp lệ được đọc. `HttpOnly` cho cookie phiên giúp giảm khả năng lộ giá trị cookie qua JavaScript, nhưng XSS vẫn có thể gọi API cùng origin thay người dùng.

## 7. Hình ảnh hiển thị được nhưng canvas có thể không đọc được pixel

Một thẻ ảnh chéo origin thường có thể hiển thị:

```html
<img src="https://cdn.example.net/photo.png" alt="Ảnh sản phẩm">
```

Nhưng khi ảnh không có quyền đọc chéo origin được vẽ lên canvas, canvas trở thành **origin-unclean** (thường gọi là *tainted*):

```js
const img = new Image();
img.src = "https://cdn.example.net/photo.png";

img.onload = () => {
  const canvas = document.createElement("canvas");
  canvas.width = img.naturalWidth;
  canvas.height = img.naturalHeight;
  const context = canvas.getContext("2d");
  context.drawImage(img, 0, 0);

  try {
    console.log(canvas.toDataURL());
  } catch (error) {
    console.error(error.name); // Thường là "SecurityError"
  }
};
```

Điều này tránh việc trang lạ lấy trực tiếp pixel từ tài nguyên vốn chỉ được phép hiển thị. Nếu chủ sở hữu ảnh **muốn** cho phép đọc, trang có thể yêu cầu ảnh ở chế độ CORS bằng `img.crossOrigin = "anonymous"` **trước khi gán `src`**, và server ảnh cần trả header CORS phù hợp như `Access-Control-Allow-Origin`. Khi ảnh được tải CORS hợp lệ, canvas có thể vẫn ở trạng thái origin-clean.

Quy tắc đọc dữ liệu còn xuất hiện ở các API khác như video, âm thanh và một số cách xử lý media. Vì vậy, “trình duyệt tải được” không đồng nghĩa “JavaScript trích xuất được toàn bộ nội dung”.

## 8. Một ngoại lệ dễ hiểu nhầm: script từ CDN chạy với quyền của tài liệu nhúng nó

Giả sử website chèn:

```html
<script src="https://cdn.example.net/library.js"></script>
```

Script tải từ CDN **thực thi trong môi trường của tài liệu đang nhúng nó**, tức được trao quyền JavaScript của origin trang chủ theo mô hình script cổ điển. Đây không phải là một iframe chạy độc lập tại origin của CDN. Nếu nguồn script bị thay thế, mã độc có thể thao tác DOM hoặc gọi API với quyền của script trong trang chủ.

Hệ quả khi thiết kế:

1. Chỉ nhúng script đáng tin và kiểm soát phụ thuộc bên thứ ba.
2. Dùng **CSP** để giới hạn nguồn/cách thực thi script; cân nhắc **Subresource Integrity (SRI)** cho tài nguyên tĩnh có nội dung cố định khi phù hợp.
3. Tránh chèn HTML hoặc JavaScript từ dữ liệu chưa được kiểm soát; dùng encode theo ngữ cảnh, API DOM an toàn và **Trusted Types** ở môi trường hỗ trợ.
4. Với nội dung đối tác cần cách ly quyền thực thi, cân nhắc iframe khác origin với `sandbox` thích hợp.

SOP giúp cô lập dữ liệu **giữa origin**, nhưng không thể phân biệt script hợp lệ với script bị chèn độc hại khi cả hai cùng chạy dưới quyền của **một origin**. Đó là lý do phòng vệ XSS vẫn là một phần thiết yếu của bảo mật trình duyệt.

## 9. Data read isolation không đồng nghĩa bí mật tuyệt đối

SOP chặn những đường **đọc trực tiếp** phổ biến, nhưng một hệ thống vẫn có thể rò rỉ thông tin theo cách khác:

- **CSRF:** request làm thay đổi trạng thái có thể được gửi trong một số tình huống mà trang gửi không đọc được response. Server cần CSRF token hoặc biện pháp tương ứng, kiểm tra quyền và không dùng GET cho thao tác thay đổi trạng thái.
- **XS-Leaks (cross-site leaks):** một website có thể suy luận thông tin qua tín hiệu gián tiếp như thời gian, trạng thái tải hoặc hành vi điều hướng nếu ứng dụng để lộ khác biệt quan sát được. SOP không tự loại bỏ mọi kênh suy luận.
- **XSS:** mã độc chạy trong origin của nạn nhân có thể đọc dữ liệu mà chính ứng dụng nạn nhân được quyền đọc.
- **Cấu hình CORS quá rộng:** nếu API phản chiếu tùy tiện `Origin` và cho phép credentials mà không kiểm soát, JavaScript ở origin không tin cậy có thể nhận được dữ liệu riêng tư.
- **Ứng dụng cho phép chia sẻ dữ liệu quá rộng:** ví dụ `postMessage` không kiểm tra `event.origin` hoặc API trả dữ liệu nhạy cảm cho người dùng không có quyền.

Một số lớp phụ trợ:

| Cơ chế | Hỗ trợ ranh giới đọc dữ liệu ra sao? | Không thay thế cho |
| --- | --- | --- |
| **CORS** | Cho phép/chặn việc script đọc HTTP response khác origin theo chính sách server | Xác thực, phân quyền API |
| **CORP** (`Cross-Origin-Resource-Policy`) | Server giới hạn một số trường hợp nhúng tài nguyên ở chế độ `no-cors` từ origin/site khác | CORS hoặc kiểm tra quyền dữ liệu |
| **COEP** (`Cross-Origin-Embedder-Policy`) | Tài liệu yêu cầu các tài nguyên chéo origin được nhúng đáp ứng quy tắc phù hợp | SOP hoặc kiểm soát mọi nguồn dữ liệu |
| **COOP** (`Cross-Origin-Opener-Policy`) | Tách quan hệ browsing context giữa một số cửa sổ top-level | Authorization ở server |
| **CSP** (`Content-Security-Policy`) | Giảm các đường tải/thực thi mã nguy hiểm và có thể chặn bị nhúng bằng `frame-ancestors` | Escape output, sửa XSS tại nguồn |
| **`iframe sandbox`** | Thu hẹp quyền tài liệu nhúng, có thể cấp opaque origin | SOP, chính sách của server |
| **Site Isolation** | Cách ly nội dung site ở mức tiến trình khi được hỗ trợ để giảm rủi ro lỗi engine | Mô hình quyền JavaScript hoặc xác thực |

Browser thực thi các cơ chế này ở những thời điểm và phạm vi khác nhau; không nên bật một header chỉ vì tên gọi có chữ “cross-origin”. Phải hiểu tương tác và kiểm tra nguồn tài nguyên hợp lệ có còn hoạt động hay không.

## 10. Thí nghiệm thực tế: hai origin trên cùng máy

Thí nghiệm này phân biệt được **đọc DOM khác origin**, **gửi thông điệp có chủ đích**, **lỗi CORS** và **response opaque**, không cần trang web bên ngoài. Chỉ thực hiện với các tệp thử nghiệm do bạn kiểm soát.

### Bước 1. Chuẩn bị hai thư mục và hai server

Tạo hai thư mục `parent` và `child`. Chạy hai HTTP server tĩnh ở hai cửa sổ terminal; ví dụ nếu có Python:

```bash
python -m http.server 8000 --directory parent
```

```bash
python -m http.server 8001 --directory child
```

Cả hai đều dùng `localhost`, nhưng `http://localhost:8000` và `http://localhost:8001` là **hai origin khác nhau vì khác port**. Các server tĩnh mẫu thường không trả header CORS để cho phép origin khác đọc response.

### Bước 2. Tạo `child/child.html`

```html
<!doctype html>
<html lang="vi">
  <meta charset="utf-8">
  <title>Child ở port 8001</title>
  <body>
    <h1 id="secret">Nội dung riêng của child</h1>
    <button id="send">Gửi dữ liệu được chọn</button>
    <script>
      document.querySelector("#send").addEventListener("click", () => {
        parent.postMessage(
          { type: "CHILD_MESSAGE", value: "Xin chào từ child" },
          "http://localhost:8000"
        );
      });
    </script>
  </body>
</html>
```

### Bước 3. Tạo `parent/index.html`

```html
<!doctype html>
<html lang="vi">
  <meta charset="utf-8">
  <title>Parent ở port 8000</title>
  <body>
    <h1>Kiểm tra Data read isolation</h1>
    <iframe
      id="child"
      title="Nội dung ở origin thứ hai"
      src="http://localhost:8001/child.html"
    ></iframe>
    <script>
      const frame = document.querySelector("#child");

      frame.addEventListener("load", () => {
        try {
          console.log(frame.contentWindow.document.querySelector("#secret").textContent);
        } catch (error) {
          console.log("Đọc DOM bị chặn:", error.name);
        }
      });

      window.addEventListener("message", (event) => {
        if (event.origin !== "http://localhost:8001") return;
        if (event.source !== frame.contentWindow) return;
        if (!event.data || event.data.type !== "CHILD_MESSAGE") return;
        if (typeof event.data.value !== "string") return;
        console.log("Thông điệp hợp lệ:", event.data.value);
      });

      async function testFetch() {
        const url = "http://localhost:8001/child.html";
        try {
          const result = await fetch(url);
          console.log("Đọc response:", await result.text());
        } catch (error) {
          console.log("Không đọc được do CORS:", error.name);
        }

        const opaque = await fetch(url, { mode: "no-cors" });
        console.log("no-cors:", opaque.type, opaque.status);
      }

      testFetch();
    </script>
  </body>
</html>
```

### Bước 4. Quan sát DevTools

Mở `http://localhost:8000`, bật **Console** và **Network**, rồi nhấn nút trong iframe.

| Thao tác | Kết quả mong đợi | Lý do |
| --- | --- | --- |
| Parent đọc `#secret` trong iframe | Lỗi `SecurityError` hoặc thông báo chặn chéo origin | SOP ngăn đọc DOM khác origin |
| Child gửi `postMessage` bằng nút bấm | Parent nhận `CHILD_MESSAGE` hợp lệ | Giao tiếp được thiết kế có kiểm tra nguồn |
| Parent gọi `fetch(url)` ở port 8001 | JS không đọc được response vì CORS | Server tĩnh không gửi header cho phép origin 8000 |
| Parent gọi `fetch(url, { mode: "no-cors" })` | Log `opaque 0` | Request có thể tải tài nguyên nhưng response không đọc được |
| Network ghi nhận request tới port 8001 | Có thể thấy request và response dù Console báo CORS | Chặn quyền đọc không luôn đồng nghĩa chặn gửi |

**Kiểm soát biến:** nếu thay iframe sang `http://localhost:8000` và phục vụ cùng nội dung từ origin cha, truy cập DOM có thể được phép. Nếu thay header CORS ở server port 8001 để cho phép đúng origin `http://localhost:8000`, trường hợp `fetch` cũng thay đổi. Đây là **hai thay đổi chính sách khác nhau**.

Kết quả có thể thay đổi do extension, CSP, chính sách trình duyệt hoặc cấu hình server; hãy đối chiếu trực tiếp origin, response header và Console thay vì chỉ dựa vào một thông báo lỗi. Không cần tắt bảo vệ của browser để hoàn thành thí nghiệm.

## 11. Cách chẩn đoán khi ứng dụng gặp lỗi đọc dữ liệu

Khi gặp `SecurityError`, lỗi CORS hoặc dữ liệu không xuất hiện, hãy đi theo thứ tự:

1. **Ghi rõ hai URL và origin.** So scheme, hostname và port. Đừng dùng quan hệ cùng site để kết luận cùng origin.
2. **Xác định thao tác đang thất bại.** Là gửi request, đọc response, truy cập DOM iframe, đọc storage, đọc pixel canvas hay mở API nhạy cảm?
3. **Đối chiếu DevTools.** Network cho biết request/response/preflight; Console cho biết phần browser chặn; Elements cho thấy thuộc tính iframe; Application/Storage cho biết dữ liệu lưu trữ trong ngữ cảnh hiện tại.
4. **Kiểm tra phía sở hữu tài nguyên.** Response API có CORS đúng không? Tài liệu con có cấm nhúng qua `frame-ancestors` không? Ảnh có CORS nếu muốn đọc pixel không?
5. **Tách chính sách trình duyệt và quyền nghiệp vụ.** Một request `401`/`403` từ API có thể là từ chối xác thực/phân quyền; lỗi CORS là một tầng khác và đôi khi che mất nội dung lỗi của server.
6. **Chọn cơ chế trao đổi phù hợp.** Dùng `postMessage` cho tài liệu khác origin, CORS cho script đọc API chéo origin, hoặc proxy/backend khi kiến trúc yêu cầu — với kiểm tra quyền và bảo vệ dữ liệu đầy đủ.

Không “sửa” bằng cách bỏ `HttpOnly`, phản chiếu mọi origin trong CORS, dùng `mode: "no-cors"` để mong đọc body, hay gộp mọi chức năng dưới một origin mà không xét tác động nếu XSS xảy ra.

## 12. Bài toán thiết kế: dashboard và iframe đối tác

Một ứng dụng có dashboard tại `https://portal.example.com`, API tại `https://api.example.com` và iframe báo cáo đối tác tại `https://reports.partner.example`. Dashboard cần hiển thị tên người dùng và điểm tổng hợp, còn iframe chỉ cần mã báo cáo hiện hành.

**Thiết kế phù hợp với ranh giới đọc dữ liệu:**

- API yêu cầu xác thực, kiểm tra quyền với từng báo cáo và chỉ cho phép CORS từ những origin frontend thực sự cần. Việc API cùng site với dashboard không làm hai origin giống nhau.
- Dashboard chỉ chuyển **mã báo cáo được phép sử dụng** sang iframe qua `postMessage` với `targetOrigin` cụ thể; iframe tự xác thực quyền với server của mình, không nhận toàn bộ thông tin phiên của dashboard.
- Dashboard kiểm tra `event.origin`, `event.source` và định dạng thông điệp khi nhận phản hồi; dữ liệu hiển thị vào `textContent`, không dùng `innerHTML` với chuỗi chưa tin cậy.
- Cookie phiên của dashboard có `Secure`, `HttpOnly`, `SameSite` phù hợp; server vẫn có phòng vệ CSRF cho hành động thay đổi trạng thái.
- Trang đặt CSP để giới hạn nguồn script và nơi được phép nhúng iframe; nếu muốn ngăn bên khác nhúng dashboard, server dùng `frame-ancestors`. Có thể cân nhắc `iframe sandbox` cho nội dung đối tác, mở đúng quyền tối thiểu.

Nếu đối tác cần thêm dữ liệu, **mở rộng hợp đồng chia sẻ có kiểm soát** là cách thiết kế; không nên mở toàn bộ DOM, dữ liệu lưu trữ hay API chỉ để widget dễ tích hợp.

## 13. Tổng kết và câu hỏi tự kiểm tra

**Data read isolation** là một cách nhìn chính xác về Same-Origin Policy: browser cho phép web tương tác và nhúng tài nguyên chéo origin trong những trường hợp được thiết kế, đồng thời giữ giới hạn đọc dữ liệu giữa các origin. Những ranh giới này xuất hiện ở DOM, HTTP response, cookie/storage và nội dung media, với những cơ chế cho phép chia sẻ có chủ đích như CORS hoặc `postMessage`.

Tự kiểm tra khả năng suy luận:

1. Vì sao `http://localhost:8000` và `http://localhost:8001` có thể khác origin nhưng cookie vẫn có thể dùng chung?
2. Nếu một request chéo origin trả HTTP 200 trong Network nhưng `fetch` báo lỗi, ta cần kiểm tra điều gì trước?
3. Vì sao `fetch(..., { mode: "no-cors" })` không giúp JavaScript đọc JSON của API khác origin?
4. Vì sao `<img>` hiển thị bình thường nhưng `canvas.toDataURL()` có thể ném `SecurityError`?
5. Vì sao CSP/Trusted Types và CSRF protection vẫn cần thiết ngay cả khi trình duyệt thực thi SOP đúng?

Trả lời được các câu hỏi này sẽ giúp nhận diện chính xác **ranh giới dữ liệu bị vượt qua**, chọn cơ chế phòng vệ phù hợp và kiểm chứng trên trình duyệt thực trước khi đưa một ứng dụng web vào vận hành.
