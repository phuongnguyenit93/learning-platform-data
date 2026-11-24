# Navigation policy: kiểm soát điều hướng trong trình duyệt

## 1. Vì sao điều hướng là một vấn đề bảo mật?

Điều hướng (*navigation*) là hành động khiến một ngữ cảnh duyệt mở hoặc chuyển sang một tài liệu khác. Người dùng có thể nhấp liên kết, gửi biểu mẫu, mở popup hoặc nhập URL; JavaScript cũng có thể yêu cầu trình duyệt chuyển trang qua `location.assign()`, `window.open()` hay các API liên quan. Máy chủ còn có thể trả về redirect HTTP để đưa trình duyệt tới URL tiếp theo.

Điều hướng là hoạt động bình thường của web, nhưng cũng tạo ra những rủi ro bảo mật:

- Một iframe không tin cậy có thể cố điều hướng tab chính sang trang giả mạo.
- Một liên kết bên ngoài có thể mở tab mới và thao túng trang đã mở nó nếu quan hệ `window.opener` còn tồn tại.
- Một endpoint redirect nhận URL tùy ý có thể trở thành **open redirect**, hỗ trợ phishing hoặc làm hỏng luồng OAuth.
- Biểu mẫu từ site khác có thể gửi request mang cookie phiên, tạo nguy cơ CSRF.
- Điều hướng HTTPS sang HTTP có thể làm giảm bảo vệ truyền tải nếu không có chính sách phù hợp.
- Trang có thể làm lộ URL nội bộ hoặc token qua header `Referer` khi điều hướng sang origin khác.

**Navigation policy** là tập hợp quy tắc của trình duyệt và ứng dụng quyết định ai có thể điều hướng ngữ cảnh nào, đích đến nào được chấp nhận, và thông tin nào được gửi kèm trong quá trình điều hướng. Chính sách này liên quan trực tiếp đến ranh giới origin, iframe, popup, sandbox, CSP, Referrer-Policy, HSTS và phòng vệ CSRF.

Sau bài học, bạn có thể phân biệt các loại điều hướng, hiểu quyền điều hướng giữa các cửa sổ, cấu hình sandbox và response headers phù hợp, cũng như kiểm tra những lỗ hổng redirect thường gặp.

## 2. Các loại điều hướng và ngữ cảnh đích

Trình duyệt có nhiều loại điều hướng. Cần xác định **ai khởi tạo**, **ngữ cảnh nào sẽ chuyển trang** và **đích đến là gì** trước khi đánh giá quyền.

| Cách điều hướng | Ví dụ | Ngữ cảnh thường được điều hướng |
| --- | --- | --- |
| Người dùng nhấp liên kết | `<a href="/profile">Hồ sơ</a>` | Frame chứa liên kết hoặc frame được chỉ định bởi `target`. |
| Gửi form | `<form action="/orders" method="post">` | Frame chứa form hoặc frame được chỉ định bởi `target`. |
| JavaScript điều hướng | `location.assign("/login")` | Document/cửa sổ hiện tại. |
| Mở popup/tab | `window.open("https://pay.example.net")` | Ngữ cảnh duyệt mới nếu trình duyệt cho phép. |
| HTTP redirect | Server trả `301`, `302`, `303`, `307` hoặc `308` với header `Location`. | Ngữ cảnh đang chờ phản hồi được chuyển tới URL mới. |
| Meta refresh | `<meta http-equiv="refresh" content="5;url=/next">` | Document hiện tại sau thời gian được khai báo. |
| Điều hướng frame cha/top | `window.top.location = "/home"` | Frame cấp cao nhất nếu quyền và chính sách cho phép. |

### 2.1 Top-level và nested browsing context

- **Top-level browsing context** là tab hoặc cửa sổ chính mà người dùng nhìn thấy.
- **Nested browsing context** thường là iframe được nhúng bên trong một document khác.
- Một trang có thể chứa nhiều iframe, mỗi iframe có document và origin riêng.
- Popup do `window.open()` tạo ra là một ngữ cảnh duyệt cấp cao nhất mới.

Sơ đồ:

```text
Tab chính (top-level)
┌──────────────────────────────────────────────┐
│ https://app.example.com                      │
│                                              │
│  iframe A: https://widget.example.net        │
│    └─ iframe A1: https://content.example.org │
│                                              │
│  iframe B: https://help.example.com          │
└──────────────────────────────────────────────┘
       │
       └── window.open() ──> Popup thanh toán
                             https://pay.example.net
```

Điều hướng một iframe không nhất thiết điều hướng tab chính. Ngược lại, điều hướng top-level có thể thay thế toàn bộ ứng dụng mà người dùng đang xem. Vì vậy, khả năng một frame điều hướng **chính nó** và khả năng frame điều hướng **ancestor/top-level** phải được đánh giá riêng.

## 3. Điều hướng khác origin và giới hạn của SOP

Same-Origin Policy chủ yếu giới hạn việc script đọc hoặc thao tác dữ liệu thuộc document khác origin. Nó không cấm mọi hoạt động điều hướng cross-origin.

Ví dụ, một trang có thể mở website đối tác:

```html
<a href="https://docs.example.net/" target="_blank" rel="noopener">
  Mở tài liệu đối tác
</a>
```

JavaScript cũng có thể yêu cầu điều hướng:

```javascript
// Điều hướng document hiện tại.
window.location.assign("https://docs.example.net/");

// Thay entry hiện tại trong session history.
window.location.replace("https://docs.example.net/");
```

Hai phương thức trên có ý nghĩa khác nhau đối với lịch sử:

- `location.assign(url)` điều hướng tới URL mới và thường tạo một entry mới trong session history; nút Back có thể quay lại trang trước.
- `location.replace(url)` thay thế entry hiện tại; người dùng thường không quay lại trang vừa bị thay bằng nút Back.
- `location.href = url` có hành vi điều hướng tương tự `assign()`.

**Quyền điều hướng không phải quyền đọc.** Một script có thể được phép yêu cầu cửa sổ khác điều hướng trong điều kiện nhất định nhưng vẫn không được đọc DOM hoặc URL đầy đủ của cửa sổ đó. Trình duyệt có thể áp dụng giới hạn bổ sung với frame cross-origin, popup, sandbox và điều hướng top-level.

### 3.1 Same-document navigation

Không phải mọi thay đổi URL đều tải document mới:

```javascript
// Thay đổi fragment: thường chỉ chuyển vị trí trong cùng document.
location.hash = "#security";

// Thay đổi URL của History API nhưng không tải document mới.
history.pushState({ tab: "settings" }, "", "/settings");
```

`history.pushState()` và `history.replaceState()` thay đổi session history của document hiện tại, với yêu cầu URL tuân thủ giới hạn same-origin của History API. Chúng không phải cách để đọc hoặc điều hướng một document cross-origin tùy ý.

## 4. Điều hướng từ iframe: sandbox và quyền top-navigation

Iframe thường được dùng để nhúng quảng cáo, widget, tài liệu hoặc nội dung do đối tác cung cấp. Nếu nội dung không tin cậy có thể điều hướng tab chính, nó có thể thay giao diện ứng dụng bằng một trang giả mạo. Thuộc tính `sandbox` giúp thu hẹp quyền của nội dung nhúng.

### 4.1 Sandbox mặc định

```html
<iframe
  title="Bản xem trước không tin cậy"
  sandbox=""
  srcdoc="<h2>Nội dung xem trước</h2>">
</iframe>
```

Với `sandbox=""`, trình duyệt áp dụng nhiều hạn chế, bao gồm chặn script, form submission, popup và top-level navigation theo các sandboxing flags tương ứng. Nội dung nhúng còn nhận opaque origin khi không được cấp `allow-same-origin`.

Có thể cấp một số quyền bằng token:

| Token | Quyền được mở | Cân nhắc bảo mật |
| --- | --- | --- |
| `allow-scripts` | Cho phép script trong frame chạy. | Script vẫn bị ràng buộc bởi những hạn chế sandbox còn lại. |
| `allow-forms` | Cho phép gửi biểu mẫu từ frame. | Xem xét đích form, CSRF và dữ liệu gửi đi. |
| `allow-same-origin` | Giữ origin thực thay vì ép về opaque origin. | Có thể làm suy yếu cách ly; đặc biệt nguy hiểm khi kết hợp với script trên nội dung cùng origin. |
| `allow-popups` | Cho phép frame mở popup. | Popup có thể tạo bề mặt phishing hoặc opener. |
| `allow-popups-to-escape-sandbox` | Popup được mở có thể không kế thừa sandbox flags của frame. | Chỉ cấp khi luồng popup thật sự cần. |
| `allow-top-navigation` | Cho phép frame điều hướng top-level. | Quyền mạnh; frame có thể thay thế trang người dùng đang xem. |
| `allow-top-navigation-by-user-activation` | Cho phép top-level navigation khi có transient user activation phù hợp. | Hạn chế điều hướng tự động không có tương tác người dùng. |
| `allow-downloads` | Cho phép một số thao tác tải xuống. | Có thể bị giới hạn thêm bởi chính sách trình duyệt và thao tác người dùng. |

Ví dụ cho phép script chạy nhưng vẫn chặn quyền điều hướng top-level:

```html
<iframe
  title="Widget tương tác"
  sandbox="allow-scripts"
  src="https://widget.example.net/">
</iframe>
```

Nếu widget cần mở popup sau khi người dùng nhấp nút, có thể cân nhắc `allow-popups`. Không thêm `allow-top-navigation` chỉ để sửa lỗi điều hướng khi chưa hiểu luồng cần thiết.

### 4.2 Điều hướng top-level có user activation

Một frame có thể cần đưa người dùng tới trang xác thực hoặc trang thanh toán. Token `allow-top-navigation-by-user-activation` cho phép top-level navigation khi frame có transient user activation hợp lệ, ví dụ được kích hoạt bởi thao tác click trực tiếp.

```html
<iframe
  title="Cổng xác thực"
  sandbox="allow-forms allow-scripts allow-top-navigation-by-user-activation"
  src="https://login.example.net/">
</iframe>
```

Không nên xem mọi sự kiện JavaScript là user activation. Trình duyệt quản lý trạng thái tương tác người dùng; activation có thể hết hạn hoặc bị tiêu thụ bởi một API khác. Tự gọi điều hướng từ timer, promise hoặc sự kiện tổng hợp không nhất thiết đáp ứng điều kiện.

### 4.3 CSP sandbox

Server cũng có thể áp dụng hạn chế sandbox cho document bằng response header:

```http
Content-Security-Policy: sandbox allow-forms allow-scripts
```

Chính sách này áp dụng sandbox flags cho document theo CSP. Token được cấp cần đúng nhu cầu; không dùng nó như một cách thay thế cho kiểm tra quyền và xác thực ở server.

## 5. Popup, target và window.opener

Popup thường được dùng trong đăng nhập, thanh toán và tích hợp đối tác. Khi một trang mở trang khác, mối quan hệ `opener` có thể cho phép trang mới tham chiếu tới cửa sổ mở nó.

```javascript
// Nên được gọi trực tiếp từ một thao tác người dùng như click.
const popup = window.open(
  "https://pay.example.net/checkout",
  "checkout",
  "width=520,height=700"
);

if (!popup) {
  // Trình duyệt có thể chặn popup.
  console.log("Không mở được cửa sổ thanh toán.");
}
```

Nếu opener còn tồn tại, trang popup khác origin vẫn có thể có một số khả năng với cửa sổ cha, trong đó có nguy cơ điều hướng cửa sổ cha. Đây là nền tảng của *reverse tabnabbing*.

### 5.1 Dùng noopener khi không cần giao tiếp ngược

Với liên kết ngoài:

```html
<a
  href="https://external.example.net/"
  target="_blank"
  rel="noopener noreferrer">
  Mở trang bên ngoài
</a>
```

- `noopener` ngăn trang mới nhận tham chiếu `window.opener`.
- `noreferrer` ngăn gửi thông tin referrer và đồng thời có hiệu lực như `noopener`.

Các trình duyệt hiện đại thường áp dụng hành vi `noopener` mặc định cho nhiều liên kết `target="_blank"`, nhưng khai báo tường minh giúp thể hiện ý định và tương thích với môi trường cũ.

Nếu luồng popup cần gửi kết quả về trang mở nó, không thể tùy tiện bật `noopener` rồi vẫn giả định `window.opener` còn dùng được. Hãy thiết kế một cơ chế trả kết quả khác hoặc một giao thức `postMessage` có xác minh origin, source và request ID.

### 5.2 Popup và user activation

Trình duyệt thường yêu cầu `window.open()` được gọi trong ngữ cảnh tương tác trực tiếp của người dùng:

```javascript
document.querySelector("#pay").addEventListener("click", () => {
  // Mở ngay trong click handler.
  const popup = window.open(
    "https://pay.example.net/start",
    "_blank",
    "noopener"
  );
  if (!popup) console.log("Popup có thể đã bị chặn.");
});
```

Gọi `window.open()` sau một khoảng chờ, timer hoặc chuỗi xử lý bất đồng bộ có thể mất transient user activation và bị popup blocker chặn. Hành vi chính xác phụ thuộc trình duyệt và cài đặt người dùng.

## 6. Form navigation, CSRF và chính sách đích đến

Form là một cơ chế điều hướng và gửi request quan trọng:

```html
<form action="https://api.example.com/profile" method="post">
  <input name="displayName" value="Nguyen">
  <button type="submit">Lưu</button>
</form>
```

Khi submit, trình duyệt tạo request tới `action`. Nếu đích là origin khác, request vẫn có thể được gửi; SOP/CORS chủ yếu liên quan đến việc script có được đọc phản hồi hay không. Cookie phiên có thể được gửi tùy domain, SameSite, credentials và chính sách trình duyệt.

Vì vậy, một website độc hại có thể tìm cách khiến trình duyệt người dùng đã đăng nhập gửi form tới ứng dụng khác. Nếu endpoint thay đổi trạng thái mà không có biện pháp chống CSRF, hành động trái ý có thể xảy ra dù trang khởi tạo không đọc được response.

### 6.1 CSP form-action

Chỉ thị `form-action` giới hạn nơi form của document được phép gửi:

```http
Content-Security-Policy: form-action 'self'
```

Nếu ứng dụng cần submit tới cổng thanh toán bên ngoài, khai báo origin đích cụ thể:

```http
Content-Security-Policy: form-action 'self' https://pay.example.net
```

`form-action` không phải chỉ thị điều khiển mọi dạng điều hướng; nó tập trung vào đích gửi form. Cần kết hợp với CSRF token, kiểm tra quyền backend và thiết kế endpoint đúng phương thức.

### 6.2 Không thay đổi trạng thái bằng GET

Một liên kết hoặc điều hướng GET có thể được kích hoạt bởi người dùng, iframe, crawler hoặc cơ chế tự động. Không dùng GET để xóa dữ liệu, chuyển tiền, đổi email hay thực hiện thao tác nhạy cảm.

Các thao tác thay đổi trạng thái cần phương thức phù hợp (thường POST/PUT/PATCH/DELETE qua API), xác thực quyền, CSRF protection và kiểm tra dữ liệu phía server. Phương thức HTTP một mình không ngăn CSRF.

## 7. Redirect và open redirect

Điều hướng có thể đi qua nhiều bước. Server thường trả redirect:

```http
HTTP/1.1 302 Found
Location: https://login.example.com/
```

Các mã redirect phổ biến:

| Mã | Ý nghĩa khái quát | Phương thức sau redirect |
| --- | --- | --- |
| `301` | Chuyển hướng vĩnh viễn. | Trình duyệt/client có thể chuyển POST thành GET theo hành vi lịch sử; không dựa vào việc giữ nguyên method. |
| `302` | Chuyển hướng tạm thời. | Nhiều client có thể chuyển POST thành GET. |
| `303` | Chuyển sang tài nguyên khác để lấy kết quả. | Theo sau bằng GET (hoặc HEAD tương ứng). |
| `307` | Chuyển hướng tạm thời, giữ nguyên method và body. | Giữ method/body. |
| `308` | Chuyển hướng vĩnh viễn, giữ nguyên method và body. | Giữ method/body. |

### 7.1 Open redirect là gì?

Một endpoint có thể được thiết kế như:

```text
https://app.example.com/redirect?next=https://trusted.example.net/
```

Nếu server lấy tham số `next` rồi chuyển hướng tới bất kỳ URL nào, attacker có thể gửi một liên kết có hostname đáng tin cậy nhưng cuối cùng đưa nạn nhân tới trang giả mạo:

```text
https://app.example.com/redirect?next=https://attacker.example/phishing
```

Người dùng có thể tin tưởng hostname ban đầu và không nhận ra bước chuyển hướng tiếp theo. Open redirect còn có thể phá luồng đăng nhập, làm lộ authorization code/token qua callback sai hoặc hỗ trợ chuỗi phishing.

### 7.2 Cách xử lý redirect an toàn

Ưu tiên các lựa chọn:

1. Dùng **mã định danh đích** thay cho URL tùy ý, ví dụ `next=dashboard` hoặc `next=orders`.
2. Nếu phải nhận URL, parse bằng thư viện URL chuẩn, kiểm tra scheme/host/port và đối chiếu allowlist chính xác.
3. Chỉ cho phép path tương đối đã chuẩn hóa nếu nghiệp vụ chỉ cần điều hướng nội bộ; xử lý cẩn thận dấu gạch chéo kép, dấu backslash, encoding và URL dạng protocol-relative.
4. Không kiểm tra hostname bằng `includes()` hoặc regex hậu tố thiếu ranh giới.
5. Với OAuth/OIDC, so sánh `redirect_uri` chính xác với URI đã đăng ký; dùng `state` và PKCE theo luồng phù hợp.

Ví dụ kiểm tra URL đích ở server-side (mã minh họa Node.js):

```javascript
const allowedOrigins = new Set([
  "https://app.example.com",
  "https://pay.example.net"
]);

function safeRedirectTarget(input) {
  try {
    const target = new URL(input, "https://app.example.com");

    if (target.protocol !== "https:") return null;
    if (!allowedOrigins.has(target.origin)) return null;
    return target.href;
  } catch {
    return null;
  }
}
```

Ví dụ này chỉ phù hợp khi ứng dụng thực sự cần một danh sách origin đích. Nếu chỉ cần chuyển tới các trang trong ứng dụng, cách an toàn và đơn giản hơn là ánh xạ mã đích sang route cố định, không nhận URL tùy ý từ request.

### 7.3 Redirect không phải CORS

HTTP redirect có thể được trình duyệt thực hiện như một phần của navigation. CORS không phải allowlist chung cho nơi tab được phép điều hướng. CORS kiểm soát việc script đọc phản hồi cross-origin trong các API như `fetch`/XHR; nó không ngăn người dùng nhấp liên kết hoặc ngăn browser theo redirect điều hướng.

## 8. Referrer-Policy: kiểm soát thông tin gửi khi điều hướng

Khi trang A điều hướng hoặc tải tài nguyên từ trang B, trình duyệt có thể gửi header `Referer` để cho B biết URL nguồn. URL nguồn đôi khi chứa query hoặc path nhạy cảm, chẳng hạn token reset mật khẩu, mã định danh nội bộ hoặc thông tin tìm kiếm.

Có thể thiết lập response header:

```http
Referrer-Policy: strict-origin-when-cross-origin
```

Ý nghĩa khái quát của một số giá trị:

| Giá trị | Hành vi |
| --- | --- |
| `no-referrer` | Không gửi referrer. |
| `same-origin` | Chỉ gửi referrer khi request cùng origin. |
| `origin` | Chỉ gửi origin, không gửi path/query. |
| `strict-origin` | Gửi origin; không gửi khi chuyển từ HTTPS xuống HTTP. |
| `origin-when-cross-origin` | Cùng origin gửi URL đầy đủ; cross-origin chỉ gửi origin. |
| `strict-origin-when-cross-origin` | Cùng origin gửi URL đầy đủ; cross-origin gửi origin; không gửi khi downgrade HTTPS→HTTP. |
| `no-referrer-when-downgrade` | Gửi URL nguồn trừ khi chuyển từ HTTPS xuống HTTP; đây là giá trị cũ, ít bảo vệ path hơn. |

Có thể đặt chính sách cho từng liên kết:

```html
<a href="https://external.example.net/" rel="noreferrer">
  Mở website bên ngoài mà không gửi referrer
</a>
```

Không dùng URL chứa bí mật làm nơi lưu token chỉ vì đã cấu hình Referrer-Policy. URL vẫn có thể xuất hiện trong lịch sử, log server, ảnh chụp màn hình hoặc hệ thống phân tích. Tránh đặt bí mật trong query/fragment nếu có thể; dùng token ngắn hạn, một lần và gửi qua kênh phù hợp.

## 9. HTTPS, HSTS và điều hướng an toàn

Điều hướng từ HTTPS xuống HTTP làm mất bảo vệ mã hóa và xác thực máy chủ. **HTTP Strict Transport Security (HSTS)** cho phép website yêu cầu trình duyệt tự nâng cấp các lần truy cập HTTP trong tương lai thành HTTPS:

```http
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

- `max-age` khai báo thời gian (giây) trình duyệt ghi nhớ chính sách.
- `includeSubDomains` mở rộng chính sách tới các subdomain phù hợp; chỉ bật khi mọi subdomain đều hỗ trợ HTTPS.
- `preload` là cơ chế đăng ký domain vào danh sách preload của trình duyệt; không chỉ thêm token vào header là tự động được preload.

HSTS thường được trình duyệt chấp nhận từ phản hồi HTTPS an toàn. Nó giúp chống downgrade và một số kiểu SSL stripping sau khi trình duyệt đã biết chính sách; lần truy cập HTTP đầu tiên vẫn có thể gặp rủi ro nếu domain chưa được preload hoặc chưa có trạng thái HSTS lưu trước đó.

Đừng nhầm HSTS với CSP `upgrade-insecure-requests`: chúng có mục tiêu và phạm vi khác nhau. HSTS là chính sách transport cho host; CSP directive giúp nâng cấp URL tài nguyên không an toàn được khai báo trong document. Cả hai không thay thế việc triển khai HTTPS đúng trên server.

## 10. CSP và những chính sách thường bị nhầm

Một số header điều khiển những khía cạnh khác nhau của navigation:

| Header/chỉ thị | Kiểm soát | Không kiểm soát toàn bộ |
| --- | --- | --- |
| CSP `form-action` | Đích gửi form. | Link click, mọi lệnh gán location hay mọi redirect. |
| CSP `frame-ancestors` | Ai được phép nhúng document hiện tại. | Document hiện tại được phép điều hướng tới đâu. |
| CSP `sandbox` | Quyền của document, bao gồm các giới hạn điều hướng theo sandbox flags. | Thay thế xác thực/ủy quyền của ứng dụng. |
| `Referrer-Policy` | Lượng thông tin referrer gửi đi. | URL đích được phép hay không. |
| `Strict-Transport-Security` | Yêu cầu dùng HTTPS cho host theo chính sách đã lưu. | Allowlist redirect hoặc quyền frame. |
| `Cross-Origin-Opener-Policy` | Quan hệ opener/browsing context group. | Quyền gửi mọi request hoặc quyền đọc DOM theo SOP. |

### 10.1 Cẩn trọng với CSP navigate-to

Chỉ thị `navigate-to` từng được đề xuất để giới hạn URL mà document có thể điều hướng tới. Tuy nhiên, mức hỗ trợ trình duyệt không đủ đồng đều để dựa vào nó như lớp kiểm soát chính trong sản phẩm. **Không coi `default-src` hoặc `navigate-to` là allowlist navigation phổ quát**; dùng các cơ chế được hỗ trợ cho từng luồng như sandbox, `form-action`, `frame-ancestors`, kiểm tra URL ở server và thiết kế route an toàn.

## 11. Checklist thiết kế và kiểm thử navigation policy

Khi xây dựng một ứng dụng có liên kết, iframe, popup hoặc redirect, hãy rà soát:

1. **Đích điều hướng:** URL đến từ code cố định, cấu hình tin cậy hay input người dùng? Có cho phép scheme nguy hiểm hoặc hostname ngoài allowlist không?
2. **Ngữ cảnh đích:** điều hướng self, iframe, parent hay top-level? Frame có thật sự cần quyền điều hướng ancestor không?
3. **User activation:** popup/top navigation có gắn với thao tác người dùng hợp lệ không?
4. **Sandbox:** iframe không tin cậy đã bị giới hạn script, form, popup và top navigation theo nhu cầu tối thiểu chưa?
5. **Opener:** tab mới có cần tham chiếu opener không? Nếu không, dùng `noopener`/`noreferrer`.
6. **Form và CSRF:** form có thể gửi tới origin nào? Server có CSRF token và xác thực quyền không? GET có vô tình thay đổi trạng thái không?
7. **Redirect:** server có open redirect không? Callback OAuth có so khớp chính xác không?
8. **Referrer:** URL nguồn có thể chứa token hoặc dữ liệu nhạy cảm? Đã đặt Referrer-Policy phù hợp chưa?
9. **Transport:** mọi trang nhạy cảm có HTTPS? HSTS có được bật khi toàn bộ host/subdomain đã sẵn sàng không?
10. **Nhúng trang:** trang nhạy cảm có cần iframe không? Đã cấu hình `frame-ancestors` chưa?

### Thực hành trên trình duyệt

**Bài A — quan sát top navigation trong sandbox**

Tạo một trang cha và iframe:

```html
<iframe
  title="Iframe thử nghiệm"
  sandbox="allow-scripts"
  srcdoc="
    <button id='go'>Đi tới trang ngoài</button>
    <script>
      document.querySelector('#go').addEventListener('click', () => {
        top.location.href = 'https://example.com/';
      });
    </script>
  ">
</iframe>
```

Thử nhấp nút. Vì iframe không có `allow-top-navigation` hoặc `allow-top-navigation-by-user-activation`, trình duyệt sẽ chặn nỗ lực điều hướng top-level theo sandbox flags. Sau đó thêm `allow-top-navigation-by-user-activation` và thử lại. Quan sát Console để đọc thông báo vi phạm sandbox.

**Bài B — so sánh noopener**

Tạo hai liên kết mở tab mới, một liên kết có `rel="noopener"` và một liên kết không có. Trên trang đích, chạy:

```javascript
console.log(window.opener);
```

Quan sát sự khác nhau, đồng thời lưu ý trình duyệt hiện đại có thể mặc định `noopener` cho `target="_blank"`. Có thể thử `window.open` trong click handler để so sánh, nhưng không dùng một trang thật của bên thứ ba để kiểm tra thao tác điều hướng.

**Bài C — phát hiện open redirect**

Trong môi trường lab, tạo endpoint nhận tham số `next` và quan sát hành vi khi nhập:

- `/orders`
- `https://attacker.example/phishing`
- `//attacker.example/phishing`
- `javascript:alert(1)`

Không triển khai endpoint phản chiếu URL tùy ý trên hệ thống thật. Sửa thiết kế để ánh xạ giá trị cho phép sang route cố định hoặc dùng allowlist URL đã parse; kiểm tra cả scheme, host và port.

**Bài D — kiểm tra Referrer-Policy**

Đặt trang nguồn có path/query giả lập dữ liệu nhạy cảm, điều hướng sang một server khác origin do bạn kiểm soát và quan sát request header `Referer` trong Network. Thử `no-referrer` và `strict-origin-when-cross-origin` để thấy lượng thông tin thay đổi.

## 12. Tổng kết

**Navigation policy** quyết định ngữ cảnh nào có thể điều hướng, những đích đến nào được chấp nhận và thông tin nào được gửi trong quá trình chuyển trang. SOP không cấm mọi điều hướng cross-origin; sandbox giới hạn khả năng iframe điều hướng top-level; user activation và popup policy giúp ngăn các hành động tự động gây bất ngờ; `noopener` giảm rủi ro từ opener; `form-action`, CSRF protection và kiểm tra redirect bảo vệ những luồng gửi dữ liệu; Referrer-Policy và HSTS bảo vệ thông tin nguồn và transport.

Không có một header duy nhất kiểm soát mọi navigation. Hãy xác định đúng loại điều hướng rồi áp dụng chính sách phù hợp ở cả trình duyệt lẫn server. Đặc biệt, backend phải xác thực và phân quyền hành động nhạy cảm, kiểm tra redirect đích và chống CSRF; các cơ chế phía trình duyệt bổ sung lớp bảo vệ cho người dùng và document.
