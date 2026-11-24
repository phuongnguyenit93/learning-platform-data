# Cross-origin window: Cửa sổ khác origin trong Same-Origin Policy

## 1. Bài toán: có tham chiếu đến cửa sổ khác thì có quyền gì?

Một ứng dụng tại `https://shop.example.com` mở cửa sổ thanh toán tại `https://pay.example.net`. Sau khi người dùng hoàn tất thanh toán, cửa sổ thanh toán cần thông báo kết quả cho ứng dụng cửa hàng. Ứng dụng cửa hàng có thể giữ tham chiếu tới cửa sổ thanh toán, nhưng **không được tự ý đọc nội dung tài khoản, biểu mẫu hay cookie** của cửa sổ đó.

Đây chính là bài toán của **cross-origin window** trong **Same-Origin Policy (SOP)**: trình duyệt cho phép một số tương tác giữa các cửa sổ có quan hệ với nhau, đồng thời giới hạn việc truy cập dữ liệu thuộc origin khác.

Trong mô hình bảo mật ứng dụng web, hiểu ranh giới này giúp:

- Chọn cách giao tiếp an toàn giữa trang cha và `iframe`, hoặc giữa cửa sổ chính và popup.
- Phân biệt quyền **giữ tham chiếu**, **điều hướng**, **gửi thông điệp** và **đọc DOM**.
- Tránh lỗ hổng rò rỉ thông tin qua `postMessage`, popup và mã JavaScript bên thứ ba.
- Kết hợp SOP với CORS, CSP, sandbox, các security headers và các biện pháp phòng vệ XSS, CSRF, clickjacking.

**Kết quả học tập:** sau bài này, bạn có thể dự đoán quyền truy cập của một cross-origin window, viết giao thức `postMessage` có kiểm tra nguồn gửi, xử lý `window.opener` và kiểm chứng bằng hai origin localhost.

## 2. Window, Document và WindowProxy

Mỗi tài liệu HTML đang hiển thị có một đối tượng `Document` (chứa DOM) và một đối tượng `Window` (môi trường toàn cục cho JavaScript). Khi có `iframe` hoặc popup, trình duyệt tạo thêm ngữ cảnh duyệt có thể chứa document với origin khác.

Các tham chiếu thường gặp:

| Biểu thức | Nghĩa | Ví dụ |
| --- | --- | --- |
| `window` | Cửa sổ của document hiện tại. | Script trong trang chủ. |
| `window.parent` | Cửa sổ của document cha; ở trang cấp cao nhất thường là chính nó. | Script trong `iframe` tham chiếu trang chứa nó. |
| `window.top` | Cửa sổ cấp cao nhất trong cây các frame. | Một frame lồng nhiều tầng tham chiếu tab chính. |
| `iframe.contentWindow` | Tham chiếu cửa sổ của iframe. | Trang cha giữ tham chiếu tới tài liệu nhúng. |
| `window.frames[index]` | Tham chiếu tới frame con theo chỉ số. | Trang cha liệt kê những frame trực tiếp. |
| `window.opener` | Tham chiếu cửa sổ đã mở popup, nếu quan hệ opener còn tồn tại. | Popup quay lại ứng dụng mở nó. |
| `window.open(...)` | Có thể mở ngữ cảnh duyệt mới và trả về tham chiếu. | Mở popup đăng nhập/thanh toán. |

Về mặt mô hình trình duyệt, nhiều tham chiếu chéo cửa sổ được biểu diễn bằng **`WindowProxy`**: một đối tượng đại diện cho cửa sổ khi document bên trong có thể thay đổi vì điều hướng. Điều quan trọng là **có tham chiếu `WindowProxy` không đồng nghĩa được truy cập toàn bộ `Window` hay `Document`**. Các phép đọc/ghi được trình duyệt kiểm tra quyền theo origin tại thời điểm sử dụng.

```text
Tab A: https://app.example.com             Popup B: https://pay.example.net
┌────────────────────────────┐             ┌────────────────────────────┐
│ Window A                   │ --open()--> │ Window B                   │
│ Document A + DOM A         │             │ Document B + DOM B         │
│ origin: app.example.com    │ <--opener-- │ origin: pay.example.net    │
│ tham chiếu đến Window B    │             │ tham chiếu đến Window A    │
└────────────────────────────┘             └────────────────────────────┘
         │                                           │
         └── SOP hạn chế đọc DOM chéo origin ─────────┘
                   postMessage vẫn dùng được
```

**Lưu ý:** mối quan hệ `parent`, `top`, `opener` là quan hệ giữa các ngữ cảnh duyệt, không phải bằng chứng hai tài liệu cùng origin hay cùng quyền đăng nhập.

## 3. Xác định cross-origin đúng cách

Với URL HTTP(S), **origin** gồm ba thành phần:

```text
origin = (scheme, host, port)

https://app.example.com:443/a   -> https://app.example.com
https://app.example.com:8443/a  -> https://app.example.com:8443
http://app.example.com/a        -> http://app.example.com
```

Chỉ cần khác **một** thành phần là cross-origin. Port `443` là mặc định của HTTPS và `80` là mặc định của HTTP; path, query và fragment không tham gia xác định origin.

Giả sử trang cha là `https://app.example.com/dashboard`:

| Tài liệu được mở/nhúng | Same-origin? | Hệ quả |
| --- | --- | --- |
| `https://app.example.com/help` | Có | Thường có thể truy cập DOM lẫn nhau nếu không bị chính sách khác hạn chế. |
| `https://api.example.com/docs` | Không | Khác host, dù cùng miền đăng ký. |
| `http://app.example.com/login` | Không | Khác scheme. |
| `https://app.example.com:8443/` | Không | Khác port. |
| `https://pay.example.net/` | Không | Khác host. |

Trong JavaScript, nên dùng API URL để so sánh origin cho những URL thông thường:

```javascript
const hostPage = new URL("https://app.example.com/dashboard");
const partner = new URL("https://pay.example.net/checkout");

console.log(hostPage.origin); // "https://app.example.com"
console.log(partner.origin);  // "https://pay.example.net"
console.log(hostPage.origin === partner.origin); // false
```

**Same-site khác same-origin.** `https://app.example.com` và `https://api.example.com` có thể được xem là cùng site theo mô hình *schemeful same-site* nhưng vẫn là hai origin. Thuộc tính cookie `SameSite` sử dụng khái niệm site; SOP giới hạn đọc DOM theo origin. Cookie còn có quy tắc Domain, Path, Secure, HttpOnly và không bị phân chia theo port như origin.

## 4. SOP cho phép và chặn những thao tác nào?

SOP giới hạn truy cập script từ một document sang document khác origin. Điều này **không có nghĩa mọi thuộc tính của cross-origin window đều bị chặn**: trình duyệt giữ một tập nhỏ các thao tác có thể dùng qua tham chiếu cửa sổ.

| Thao tác từ Window A đối với Window B khác origin | Hành vi phổ biến | Vì sao |
| --- | --- | --- |
| `otherWindow.document` | Bị chặn (thường ném `SecurityError`). | Không cho đọc/sửa DOM của document khác origin. |
| `otherWindow.localStorage` | Không được đọc dữ liệu của origin B. | Dữ liệu lưu trữ được bảo vệ theo origin và chính sách phân vùng. |
| `otherWindow.location.href` để **đọc** | Bị hạn chế. | Không tùy ý tiết lộ URL đầy đủ của B. |
| `otherWindow.location = "https://..."` để **điều hướng** | Có thể được phép trong một số quan hệ và điều kiện. | Điều hướng và đọc dữ liệu là hai quyền khác nhau; trình duyệt có giới hạn điều hướng chéo ngữ cảnh. |
| `otherWindow.postMessage(data, targetOrigin)` | Được phép khi có tham chiếu hợp lệ. | Kênh truyền dữ liệu liên document được thiết kế riêng. |
| `otherWindow.closed` | Có thể đọc trong tập thuộc tính được phép. | Hỗ trợ kiểm tra cửa sổ đã đóng. |
| `otherWindow.focus()` / `otherWindow.blur()` | Có API được phép nhưng hành vi có thể chịu giới hạn tương tác của trình duyệt. | Hỗ trợ quản lý giao diện, không cấp quyền đọc DOM. |
| `otherWindow.parent`, `top`, `frames` | Một số tham chiếu/thao tác hạn chế được cho phép. | Duy trì cấu trúc ngữ cảnh duyệt mà không tiết lộ DOM. |

**Không dùng bảng này làm danh sách API bất biến**: những hành vi ngoài tập tối thiểu còn phụ thuộc chuẩn trình duyệt, điều hướng, sandbox, chính sách popup và khả năng can thiệp của người dùng. Phải kiểm tra API cụ thể trên trình duyệt mục tiêu.

### 4.1 Đọc DOM của iframe khác origin

Trang cha tại `http://localhost:3000` chứa:

```html
<iframe id="child" src="http://localhost:4000/child.html"></iframe>
```

Sau khi iframe đã tải xong tài liệu ở port `4000`:

```javascript
const frame = document.querySelector("#child");

console.log(frame.contentWindow);   // Có tham chiếu WindowProxy
console.log(frame.contentDocument); // null với tài liệu cross-origin

try {
  console.log(frame.contentWindow.document.body.textContent);
} catch (error) {
  console.log(error.name); // thường là "SecurityError"
}
```

Hai trang cùng chạy ở `localhost` nhưng khác port nên khác origin. Chúng không thể truy cập DOM lẫn nhau chỉ vì có quan hệ cha/con.

### 4.2 Điều hướng không đồng nghĩa đọc được dữ liệu

Một số trường hợp cho phép cửa sổ A yêu cầu điều hướng cửa sổ B bằng gán `location`, kể cả khi không thể đọc `B.document` hoặc `B.location.href`. Quyền điều hướng phụ thuộc quan hệ cửa sổ và các hạn chế của trình duyệt (đặc biệt với điều hướng top-level từ iframe). Do đó:

- Không xem quyền điều hướng là quyền đọc thông tin.
- Không dựa vào việc “cửa sổ B đã từng ở origin đáng tin cậy” để đọc dữ liệu về sau.
- Luôn dùng `targetOrigin` chính xác khi gửi thông điệp, vì một popup/iframe có thể điều hướng sang trang khác sau khi được mở.

## 5. Giao tiếp đúng cách với window.postMessage

`postMessage` là kênh chính thức để hai document khác origin trao đổi thông điệp qua tham chiếu cửa sổ. Browser cho phép gửi thông điệp, nhưng ứng dụng phải tự thiết kế **giao thức tin cậy**:

1. Bên gửi chọn **`targetOrigin` cụ thể** để thông điệp chỉ được giao nếu tài liệu đích có origin phù hợp.
2. Bên nhận kiểm tra **`event.origin`** của bên gửi và **`event.source`** của cửa sổ gửi.
3. Bên nhận xác thực cấu trúc thông điệp, kiểu dữ liệu, loại yêu cầu và trạng thái nghiệp vụ.
4. Với yêu cầu và phản hồi, nên dùng **request ID / nonce** để ràng buộc phản hồi với một yêu cầu đang chờ.
5. Không coi thông điệp `postMessage` là bằng chứng người dùng đã đăng nhập hoặc được phép thực hiện hành động; quyền vẫn cần kiểm tra tại server.

`postMessage` truyền dữ liệu qua **structured clone algorithm**, thường có thể truyền object, array và một số kiểu dữ liệu chuyên biệt mà không cần `JSON.stringify`. Tuy nhiên ứng dụng vẫn phải xem payload là **dữ liệu không tin cậy**.

### 5.1 Ví dụ hoàn chỉnh với hai origin localhost

Trang cha: `http://localhost:3000/index.html`. Trang con: `http://localhost:4000/child.html`.

**Trang cha — `index.html`:**

```html
<!doctype html>
<html lang="vi">
<head><meta charset="utf-8"><title>Trang cha</title></head>
<body>
  <h1>Ứng dụng ở cổng 3000</h1>
  <p id="result">Đang chờ...</p>
  <iframe id="partner"
          title="Ứng dụng đối tác"
          src="http://localhost:4000/child.html"></iframe>
  <script>
    const partner = document.querySelector("#partner");
    const result = document.querySelector("#result");
    const partnerOrigin = "http://localhost:4000";
    const requestId = crypto.randomUUID();

    partner.addEventListener("load", () => {
      // Không đọc DOM của iframe; gửi thông điệp tới origin cụ thể.
      partner.contentWindow.postMessage(
        { type: "PING", requestId },
        partnerOrigin
      );
    });

    window.addEventListener("message", (event) => {
      if (event.origin !== partnerOrigin) return;
      if (event.source !== partner.contentWindow) return;

      const data = event.data;
      if (!data || typeof data !== "object") return;
      if (data.type !== "PONG" || data.requestId !== requestId) return;
      if (typeof data.message !== "string") return;

      // textContent hiển thị văn bản, không diễn giải HTML.
      result.textContent = data.message;
    });
  </script>
</body>
</html>
```

**Trang con — `child.html`:**

```html
<!doctype html>
<html lang="vi">
<head><meta charset="utf-8"><title>Trang con</title></head>
<body>
  <h2>Đối tác ở cổng 4000</h2>
  <script>
    const allowedParentOrigin = "http://localhost:3000";

    window.addEventListener("message", (event) => {
      if (event.origin !== allowedParentOrigin) return;
      if (event.source !== window.parent) return;

      const data = event.data;
      if (!data || typeof data !== "object") return;
      if (data.type !== "PING") return;
      if (typeof data.requestId !== "string") return;

      event.source.postMessage(
        {
          type: "PONG",
          requestId: data.requestId,
          message: "Phản hồi hợp lệ từ cửa sổ đối tác"
        },
        allowedParentOrigin
      );
    });
  </script>
</body>
</html>
```

Khi dùng HTTP server tĩnh để phục vụ đúng hai cổng, trang cha không đọc được DOM của iframe nhưng vẫn nhận được phản hồi `PONG` sau khi bộ kiểm tra origin, source và request ID thỏa điều kiện. `crypto.randomUUID()` hoạt động trên những trình duyệt hỗ trợ ở secure context; `localhost` thường được xem là ngữ cảnh đáng tin cậy cho mục đích phát triển.

**Lưu ý về thứ tự sự kiện:** trang con cài listener trong lúc tải, sau đó trang cha gửi `PING` khi iframe phát sự kiện `load`. Với tích hợp phức tạp, có thể thiết kế thêm thông điệp `READY` hoặc cơ chế xác nhận để tránh gửi trước khi đối tác đăng ký listener.

### 5.2 Những sai lầm nguy hiểm với postMessage

| Sai lầm | Nguy cơ | Cách sửa |
| --- | --- | --- |
| Gửi dữ liệu nhạy cảm bằng `postMessage(secret, "*")` | Một document khác có thể nhận dữ liệu nếu cửa sổ đích điều hướng. | Gửi tới `targetOrigin` cố định, chính xác. |
| Chỉ kiểm tra `event.data.type` | Mọi origin có tham chiếu tới cửa sổ có thể gửi payload giả mạo. | Kiểm tra `event.origin`, `event.source` và nội dung. |
| So sánh `event.origin.includes("example.com")` | Domain như `example.com.attacker.test` có thể vượt điều kiện. | So sánh chuỗi origin chuẩn hóa với allowlist cụ thể. |
| Chấp nhận `event.origin === "null"` như một đối tác xác định | Nhiều opaque origin khác nhau cùng có biểu diễn `"null"`. | Thiết kế giao thức riêng cho opaque origin; không coi `"null"` là danh tính đáng tin cậy. |
| Dùng `innerHTML = event.data.message` | Dữ liệu trong message có thể gây DOM XSS. | Dùng `textContent` khi chỉ cần văn bản; lọc nội dung HTML nếu thật sự cần. |
| Tin rằng `event.source` luôn đang ở origin của `event.origin` | Cửa sổ gửi có thể điều hướng sau khi thông điệp được phát. | Xác minh từng message; khi gửi lại dùng `targetOrigin` rõ ràng. |

**Chi tiết cần nhớ:** `event.origin` phản ánh origin của bên gửi **tại thời điểm bên gửi gọi `postMessage`**. Nếu cửa sổ đó điều hướng sau khi gửi, tham chiếu `event.source` có thể trỏ đến cửa sổ hiện đã hiển thị một document khác. Vì vậy cần kiểm tra lại ở từng tương tác, tránh lưu trạng thái “đã tin cậy vĩnh viễn”.

## 6. Popup, window.opener và nguy cơ thao túng điều hướng

Một popup mở bằng `window.open` đôi khi có thể truy cập `window.opener` để gửi thông điệp cho cửa sổ gốc:

```javascript
// Ví dụ bên cửa sổ chính (nên gọi trong sự kiện người dùng click).
const popup = window.open(
  "https://pay.example.net/start",
  "checkout",
  "width=520,height=680"
);

if (!popup) {
  console.log("Popup bị chặn hoặc không được mở.");
}
```

Nếu quan hệ opener tồn tại, trang popup khác origin có thể gửi thông điệp tới opener; trong những điều kiện nhất định, nó cũng có thể **điều hướng** cửa sổ gốc sang trang giả mạo, dù không đọc được DOM của cửa sổ đó. Đây là nền tảng của rủi ro *reverse tabnabbing*.

Với liên kết mở trang ngoài và không cần giao tiếp hai chiều, nên cắt quan hệ opener:

```html
<a href="https://external.example.net/"
   target="_blank"
   rel="noopener noreferrer">
  Mở trang bên ngoài
</a>
```

`noopener` ngăn cửa sổ mới nhận tham chiếu opener; `noreferrer` còn hạn chế gửi thông tin referrer. Các trình duyệt hiện đại thường đã áp dụng ngầm `noopener` cho nhiều liên kết `target="_blank"`, nhưng khai báo rõ vẫn dễ kiểm tra ý định bảo mật.

Với `window.open`, có thể yêu cầu:

```javascript
window.open("https://external.example.net/", "_blank", "noopener");
```

Trong chế độ này, chương trình không nên kỳ vọng có thể giữ tham chiếu popup dùng để `postMessage` như luồng có opener. Nếu nghiệp vụ **cần** trao đổi dữ liệu với popup (ví dụ đăng nhập), thiết kế giao thức chặt chẽ, chỉ cho phép origin đối tác đã cấu hình và cân nhắc dùng backend callback hoặc kênh trung gian đáng tin cậy. Popup có thể bị trình duyệt chặn nếu không gắn với thao tác trực tiếp của người dùng.

## 7. iframe sandbox và origin đặc biệt

Một `iframe` là một document riêng, nhưng **không phải mọi iframe đều được cách ly khỏi trang cha**. Nếu iframe dùng `srcdoc` mà không sandbox, document có thể kế thừa origin của trang chứa nó. Trang chứa HTML không tin cậy cần áp dụng sandbox thích hợp.

```html
<!-- Nội dung từ người dùng được cô lập; script không chạy. -->
<iframe
  title="Bản xem trước"
  sandbox=""
  srcdoc="<h1>Bản xem trước</h1>">
</iframe>
```

Nếu cần cho phép script trong nội dung nhúng nhưng vẫn muốn tách origin:

```html
<iframe
  title="Bản xem trước tương tác"
  sandbox="allow-scripts"
  src="https://widgets.example.net/preview">
</iframe>
```

Không có `allow-same-origin`, iframe sandbox được gán **opaque origin**. Nhiều opaque origin được serialize thành `"null"` khi truyền trong `MessageEvent.origin`; không nên đưa `"null"` vào allowlist như một đối tác xác định. Đối với popup/iframe sandbox, cần thiết kế chặt chẽ hướng truyền thông điệp và không gửi dữ liệu bí mật đến đích không thể xác định origin một cách an toàn.

Đặc biệt, **không kết hợp `allow-scripts` và `allow-same-origin` cho HTML không tin cậy được nhúng cùng origin với trang cha**: nội dung có thể lấy lại quyền đáng kể và làm mất tác dụng cách ly dự định.

Các origin khác cần chú ý:

- `about:blank` tạo từ một document thường kế thừa origin của document tạo nó.
- `iframe srcdoc` thường kế thừa origin của document nhúng nếu không bị sandbox cách ly.
- URL `data:` thường tạo tài liệu có opaque origin riêng.
- `blob:` thường gắn với origin của ngữ cảnh tạo blob URL, không mặc nhiên là opaque.

## 8. Các security headers tác động tới cửa sổ và tài liệu nhúng

SOP là mặc định. Ứng dụng có thể chủ động thu hẹp quan hệ cửa sổ và phạm vi nhúng bằng header:

| Cơ chế | Vai trò đối với cross-origin window |
| --- | --- |
| **`Content-Security-Policy: frame-ancestors`** | Xác định những origin nào được phép nhúng trang trong iframe; giúp chống clickjacking. |
| **`X-Frame-Options`** | Chính sách chống nhúng đời cũ, thường dùng `DENY` hoặc `SAMEORIGIN` cho tương thích. |
| **`Cross-Origin-Opener-Policy` (COOP)** | Điều khiển nhóm ngữ cảnh duyệt cấp cao nhất, có thể cắt quan hệ opener với cửa sổ khác origin. |
| **`Cross-Origin-Embedder-Policy` (COEP)** | Yêu cầu tài nguyên cross-origin được nhúng phải đáp ứng cơ chế phù hợp (CORS/CORP hoặc một chế độ được hỗ trợ). |
| **`Cross-Origin-Resource-Policy` (CORP)** | Cho phép tài nguyên giới hạn việc được tải ở các ngữ cảnh no-CORS cross-origin. |
| **`Content-Security-Policy: sandbox`** | Có thể áp đặt hạn chế sandbox cho document theo chính sách phản hồi. |

Trang tài khoản **không cần được nhúng** có thể sử dụng:

```http
Content-Security-Policy: frame-ancestors 'none'
X-Frame-Options: DENY
```

Chỉ thị `frame-ancestors` phải đặt trong **HTTP response header** của trang cần bảo vệ, không có hiệu lực khi viết trong `<meta http-equiv>`. Nếu cần nhúng trong một cổng thông tin tin cậy, hãy liệt kê các origin được phép thay vì dùng `'none'`.

### 8.1 COOP và quan hệ opener

Ví dụ:

```http
Cross-Origin-Opener-Policy: same-origin
```

Khi các điều kiện áp dụng được thỏa, COOP `same-origin` có thể đặt trang vào **browsing context group** khác với cửa sổ cross-origin, qua đó cắt quan hệ opener hoặc khiến tham chiếu popup từ phía mở không còn hoạt động như dự kiến. Đây là một lớp bảo vệ có chủ đích chống liên hệ không mong muốn giữa các cửa sổ.

Tuy nhiên, các luồng đăng nhập liên kết hoặc thanh toán bằng popup đôi khi phụ thuộc vào opener. Vì vậy **không áp dụng COOP một cách máy móc**: thử nghiệm toàn bộ luồng và chọn chính sách đáp ứng mô hình tin cậy. COOP kết hợp COEP phù hợp còn có thể tham gia tạo trạng thái *cross-origin isolated* cho một số API trình duyệt.

### 8.2 CSP và Trusted Types không thay thế SOP

Các biện pháp phòng vệ XSS như **CSP**, **Trusted Types** và thao tác DOM an toàn giúp giảm nguy cơ mã độc chạy ngay **trong origin được tin cậy**. Ví dụ:

```javascript
const message = new URLSearchParams(location.search).get("message") ?? "";

// Không dùng: document.querySelector("#notice").innerHTML = message;
document.querySelector("#notice").textContent = message;
```

Nếu một attacker khai thác XSS để mã chạy trong trang A, mã đó có quyền của origin A, bất kể trước đó SOP có bảo vệ A khỏi các trang cross-origin khác. Đây là lý do các lớp phòng vệ XSS cần được triển khai độc lập với ranh giới cửa sổ.

## 9. SOP, CORS và CSRF khác nhau ở đâu?

| Cơ chế | Câu hỏi mà cơ chế giải quyết | Điều không nên suy ra |
| --- | --- | --- |
| **SOP / cross-origin window** | Script ở trang A có thể đọc DOM và một số dữ liệu của trang B không? | Không ngăn mọi cách gửi request sang B. |
| **CORS** | Script ở origin A có được **đọc phản hồi** của request mạng tới origin B không? | Không phải xác thực hay phân quyền backend. |
| **Cookie SameSite** | Cookie có được gửi trong ngữ cảnh same-site/cross-site cụ thể không? | Không quyết định quyền đọc DOM giữa subdomain. |
| **CSRF token / kiểm tra request** | Một request thay đổi trạng thái có được phép với người dùng hiện tại và ngữ cảnh gửi không? | Không thể thay bằng việc “CORS đã chặn đọc response”. |
| **CSP / Trusted Types** | Mã/tài nguyên nào được chạy và dữ liệu có thể đi vào DOM sink nguy hiểm ra sao? | Không tự cấp quyền đọc DOM cross-origin. |

Ví dụ, một document cross-origin có thể gửi một biểu mẫu tới ứng dụng B; nếu cookie phiên của B được trình duyệt tự đính kèm và B không chống CSRF, thao tác đổi dữ liệu vẫn có thể xảy ra dù trang A không đọc được phản hồi. Ứng dụng nên dùng cookie `Secure`, `HttpOnly`, `SameSite` phù hợp, CSRF token hoặc kiểm tra `Origin`/`Referer` theo chính sách, và tuyệt đối kiểm tra quyền ở backend.

Tương tự, nếu ứng dụng B trả dữ liệu API với `Access-Control-Allow-Origin` hợp lệ, điều đó **không** cho phép script ở A đọc `B.document` qua `window.opener` hay `iframe.contentWindow`. CORS giải quyết quyền đọc phản hồi mạng, không mở rộng SOP cho DOM.

## 10. Thực hành kiểm chứng trong trình duyệt

Chuẩn bị hai trang HTML ở mục 5.1 và dùng hai HTTP server tĩnh chạy cổng `3000`, `4000`. Thử nghiệm nên được thực hiện trên `http://localhost` thay vì `file:`, vì chính sách origin cho `file:` có thể khác giữa các trình duyệt.

### Thí nghiệm A: SOP trên DOM

1. Truy cập `http://localhost:3000/index.html`, mở DevTools ở tab chứa trang cha.
2. Đợi iframe tại port `4000` tải xong.
3. Tại Console, kiểm tra `document.querySelector("#partner").contentWindow`: có tham chiếu cửa sổ.
4. Kiểm tra `document.querySelector("#partner").contentDocument`: kết quả dự kiến là `null` vì cross-origin.
5. Thử đọc `document.querySelector("#partner").contentWindow.document.body`: trình duyệt thường ném `SecurityError`.

**Giải thích:** khác port là khác origin; giữ tham chiếu không cấp quyền đọc DOM.

### Thí nghiệm B: postMessage có kiểm tra origin

1. Quan sát dòng “Phản hồi hợp lệ từ cửa sổ đối tác” xuất hiện trong phần tử `#result` của trang cha.
2. Trong code trang con, đổi `allowedParentOrigin` thành `http://localhost:9999` rồi tải lại: yêu cầu `PING` từ port `3000` không vượt qua điều kiện xác minh, nên không nhận `PONG`.
3. Khôi phục điều kiện; ở trang cha, đổi `partnerOrigin` thành `http://localhost:9999`: `targetOrigin` không khớp với tài liệu iframe, nên thông điệp không được giao như dự kiến.
4. Trong console, phân biệt thông báo lỗi truy cập DOM với hiện tượng `postMessage` không nhận phản hồi. Hai cơ chế hoạt động độc lập.

**Giải thích:** `targetOrigin` bảo vệ phía gửi; `event.origin`, `event.source`, request ID và xác minh payload bảo vệ phía nhận.

### Thí nghiệm C: sandbox

Thêm `sandbox="allow-scripts"` vào iframe của trang cha rồi tải lại. Script trong iframe được chạy, nhưng iframe nhận opaque origin vì thiếu `allow-same-origin`. Khi iframe gửi thông điệp về trang cha, `event.origin` có thể được serialize thành `"null"`, vì vậy bộ kiểm tra `event.origin === "http://localhost:4000"` ở trang cha từ chối phản hồi.

Đây là hành vi cách ly mong muốn. **Không sửa bộ kiểm tra thành chấp nhận mọi origin** chỉ để làm thử nghiệm chạy được. Nếu thiết kế thật sự cần dữ liệu từ nội dung sandbox có opaque origin, hãy thiết kế một kênh giao tiếp hạn chế, không truyền bí mật và đánh giá riêng mô hình tin cậy.

### Thí nghiệm D: popup và opener

Mở một liên kết `target="_blank" rel="noopener"` đến trang khác. Ở trang mới, kiểm tra `window.opener`: thường là `null`. So sánh với popup do `window.open` không có `noopener` tạo trong một tương tác của người dùng, rồi xem quan hệ opener có tồn tại không. Trình duyệt hoặc COOP có thể thay đổi kết quả.

### Câu hỏi tự kiểm tra

1. Có `iframe.contentWindow` nghĩa là được đọc `iframe.contentWindow.document` không? Vì sao?
2. Vì sao `https://a.example.com` và `https://b.example.com` là hai origin khác nhau, dù có thể cùng site?
3. Có thể dùng `postMessage` để gửi dữ liệu giữa popup và opener khi hai cửa sổ khác origin không? Các kiểm tra bắt buộc là gì?
4. Vì sao `event.origin === "null"` không đủ để xác định một iframe sandbox cụ thể?
5. Quyền điều hướng cửa sổ khác có khác với quyền đọc URL/DOM của cửa sổ đó không?
6. `Cross-Origin-Opener-Policy: same-origin` có thể tác động thế nào tới luồng đăng nhập popup?
7. Tại sao CORS cho phép đọc API vẫn không cho script đọc DOM của document khác origin?

## 11. Tổng kết

**Cross-origin window** là cửa sổ hoặc frame có document mang origin khác với document đang truy cập. Trình duyệt có thể cung cấp tham chiếu như `contentWindow`, `parent`, `top` hoặc `opener`, nhưng **Same-Origin Policy hạn chế đọc DOM và các dữ liệu riêng của cửa sổ khác origin**. Một số thao tác hẹp như gửi `postMessage`, kiểm tra trạng thái đóng hoặc điều hướng trong điều kiện cho phép vẫn có thể thực hiện.

Ứng dụng cần xác minh nguồn và nội dung của từng `message`, dùng `targetOrigin` chính xác, giới hạn quan hệ popup bằng `noopener` hoặc COOP khi phù hợp, dùng sandbox cho nội dung không tin cậy và `frame-ancestors` để giảm clickjacking. Đồng thời, SOP phải đi cùng CORS đúng phạm vi, xác thực/phân quyền và chống CSRF ở server, cùng CSP/Trusted Types và DOM API an toàn để phòng XSS. Bài học cốt lõi là **ranh giới của trình duyệt bảo vệ dữ liệu nhưng không thay thế thiết kế tin cậy ở cấp ứng dụng**.
