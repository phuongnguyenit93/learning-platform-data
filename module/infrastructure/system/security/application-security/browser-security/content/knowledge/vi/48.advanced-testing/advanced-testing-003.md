# postMessage test: kiểm thử giao tiếp cross-origin an toàn

`window.postMessage()` cho phép các browsing context trao đổi dữ liệu kể cả khi chúng thuộc những origin khác nhau. Cơ chế này thường được dùng giữa trang cha và iframe, popup đăng nhập, widget thanh toán hoặc ứng dụng được nhúng. Vì message đi qua ranh giới origin, một handler thiếu kiểm tra có thể trở thành điểm vào cho XSS, rò rỉ dữ liệu hoặc hành động có đặc quyền ngoài ý muốn.

Kiểm thử `postMessage` phải xem xét cả phía gửi lẫn phía nhận. Sender cần giới hạn nơi nhận bằng `targetOrigin`. Receiver cần xác minh `event.origin`, `event.source` và schema của `event.data` trước khi xử lý. Các test nâng cao còn phải bao gồm điều hướng cửa sổ, iframe sandbox, origin opaque, MessageChannel, message lặp và hành động cần authorization phía server.

Bài học này trình bày phương pháp kiểm thử postMessage trong ứng dụng web, gắn với Same-Origin Policy, cookie, CSP, CSRF, COOP và DOM XSS.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích mô hình bảo mật của `postMessage` và `MessageEvent`.
- Phân biệt `targetOrigin`, `event.origin` và `event.source`.
- Xác thực origin bằng exact match, bao gồm scheme, host và port.
- Phát hiện lỗi wildcard, substring matching và bỏ qua source window.
- Thiết kế message schema có version, type, payload và request identifier.
- Kiểm thử dữ liệu sai kiểu, quá lớn, lặp hoặc đến sai trạng thái.
- Đánh giá navigation race, iframe sandbox và opaque origin.
- Kiểm thử MessageChannel, popup và COOP.
- Phân biệt origin validation với authorization và CSRF protection.
- Tạo test harness với hai origin khác nhau và tự động hóa các ca kiểm thử.
- Kiểm tra dữ liệu message đi vào DOM sink có thể gây XSS hay không.

## 1. postMessage và ranh giới origin

Same-Origin Policy (SOP) giới hạn việc một document đọc DOM, JavaScript state và dữ liệu của document khác origin. Một ứng dụng vẫn có thể cần giao tiếp cross-origin có chủ đích, ví dụ trang cha nhúng widget, popup đăng nhập gửi kết quả về opener hoặc iframe báo trạng thái thanh toán.

`postMessage` cho phép trao đổi dữ liệu có kiểm soát mà không cấp quyền đọc DOM trực tiếp giữa hai origin.

### 1.1 Origin gồm những thành phần nào?

Origin là bộ ba scheme, host và port. Hai URL chỉ cùng origin khi các thành phần này tương ứng theo quy tắc chuẩn hóa của browser.

| URL | Quan hệ với `https://app.example.test` |
|---|---|
| `https://app.example.test/account` | Cùng origin |
| `https://app.example.test:443/help` | Cùng origin vì 443 là port mặc định |
| `http://app.example.test` | Khác origin vì scheme khác |
| `https://admin.example.test` | Khác origin vì host khác |
| `https://app.example.test:8443` | Khác origin vì port khác |

Không nhầm origin với site. Hai subdomain có thể được xem là cùng site trong một số quy tắc cookie/SameSite nhưng vẫn là hai origin khác nhau khi xử lý postMessage.

### 1.2 Message không cấp quyền truy cập DOM

Receiver chỉ nhận payload mà sender gửi. Tuy nhiên, receiver có thể dùng payload đó để gọi API hoặc thực hiện hành động có đặc quyền. Nếu một iframe không đáng tin có thể gửi `{ type: "delete-account" }` và host thực hiện lệnh đó mà không kiểm tra, host có thể trở thành confused deputy.

Handler message vì vậy phải được review như một endpoint HTTP: xác thực nguồn, validate input, kiểm tra trạng thái và quyền nghiệp vụ.

## 2. Cách postMessage hoạt động

Sender có thể gửi object bằng:

~~~javascript
const frame = document.querySelector("#widget");

frame.contentWindow.postMessage(
  { type: "READY", version: 1 },
  "https://widget.example.test"
);
~~~

Tham số thứ hai là `targetOrigin`. Browser chỉ giao message khi origin hiện tại của cửa sổ nhận khớp origin được chỉ định. Nếu cửa sổ bị điều hướng sang origin khác trước lúc message được giao, message với targetOrigin cũ sẽ không được giao cho document mới.

Receiver đăng ký listener:

~~~javascript
window.addEventListener("message", (event) => {
  console.log(event.origin);
  console.log(event.source);
  console.log(event.data);
});
~~~

Ba thuộc tính cần phân biệt:

| Thành phần | Ý nghĩa | Phía sử dụng |
|---|---|---|
| `targetOrigin` | Origin được phép nhận message | Sender |
| `event.origin` | Origin của sender tại thời điểm gửi | Receiver |
| `event.source` | Browsing context đã gửi message | Receiver |

`targetOrigin` không xác thực sender. `event.origin` không xác nhận đó là đúng iframe mà ứng dụng đang quản lý. `event.source` nhận diện browsing context nhưng không thay thế việc kiểm tra origin hiện tại.

### 2.1 Origin và source theo thời điểm

`event.origin` phản ánh origin của sender tại thời điểm message được gửi. Nếu sender điều hướng sau đó, giá trị này không tự thay đổi.

`event.source` thường là tham chiếu `WindowProxy` đại diện cho browsing context và có thể tiếp tục tồn tại qua navigation. Vì vậy cần kiểm tra cả origin và source.

### 2.2 Structured clone không phải validation

`postMessage` dùng structured clone để truyền dữ liệu. Object, array, Date, Map, Set và một số kiểu nhị phân có thể được clone. Function và DOM node không thể được clone theo cách thông thường.

Structured clone chỉ xác định cách truyền dữ liệu. Nó không xác thực sender, không xác nhận schema và không chứng minh payload được phép trong nghiệp vụ.

### 2.3 Transferable objects

Một số object như `MessagePort` hoặc `ArrayBuffer` có thể được transfer thay vì clone:

~~~javascript
const channel = new MessageChannel();

frame.contentWindow.postMessage(
  { type: "CONNECT" },
  "https://widget.example.test",
  [channel.port2]
);

channel.port1.start();
~~~

Khi transfer, quyền sở hữu object được chuyển sang context nhận. Cần quản lý handshake, port và vòng đời kết nối.

## 3. Xác thực message ở receiver

Một handler nên thực hiện theo thứ tự:

1. Kiểm tra `event.origin` có trong allowlist chính xác.
2. Kiểm tra `event.source` có đúng browsing context dự kiến.
3. Kiểm tra message là object có cấu trúc phù hợp.
4. Kiểm tra type và version được hỗ trợ.
5. Validate payload theo schema riêng của type.
6. Kiểm tra trạng thái hiện tại cho phép hành động.
7. Kiểm tra quyền nghiệp vụ ở server nếu có thao tác nhạy cảm.
8. Chỉ sau đó mới xử lý payload.

Ví dụ:

~~~javascript
const trustedOrigin = "https://widget.example.test";
const widgetFrame = document.querySelector("#payment-widget");

window.addEventListener("message", (event) => {
  if (event.origin !== trustedOrigin) return;
  if (event.source !== widgetFrame.contentWindow) return;

  const message = event.data;

  if (
    message === null ||
    typeof message !== "object" ||
    Array.isArray(message)
  ) {
    return;
  }

  if (message.version !== 1 || message.type !== "PAYMENT_STATUS") {
    return;
  }

  if (
    message.payload === null ||
    typeof message.payload !== "object" ||
    typeof message.payload.status !== "string"
  ) {
    return;
  }

  const allowedStatuses = new Set(["pending", "completed", "failed"]);
  if (!allowedStatuses.has(message.payload.status)) return;

  handlePaymentStatus(message.payload.status);
});
~~~

Đây là ví dụ khung. Ứng dụng thực tế cần validate độ dài, identifier, enum và state transition đầy đủ. Không gọi API nhạy cảm chỉ vì message có type hợp lệ.

### 3.1 So khớp origin chính xác

Dùng origin string cố định hoặc allowlist:

~~~javascript
const allowedOrigins = new Set([
  "https://widget.example.test",
  "https://login.example.test"
]);

if (!allowedOrigins.has(event.origin)) {
  return;
}
~~~

Không dùng substring hoặc suffix matching:

~~~javascript
if (event.origin.includes("example.test")) {
  process(event.data);
}

if (event.origin.endsWith("example.test")) {
  process(event.data);
}
~~~

Các hostname như evil-example.test hoặc example.test.attacker.invalid có thể đánh lừa cách so khớp yếu. Không dùng regex tự viết để phân tích URL nếu có thể so sánh origin đã serialize với allowlist.

### 3.2 Scheme và port cũng là một phần của origin

Chỉ kiểm tra hostname có thể vô tình chấp nhận HTTP thay vì HTTPS hoặc port không được phép.

~~~javascript
const sender = new URL(event.origin);

if (
  sender.protocol === "https:" &&
  sender.hostname === "widget.example.test" &&
  sender.port === ""
) {
  // Origin đúng theo policy HTTPS và port mặc định.
}
~~~

Với allowlist nhỏ, exact match origin string thường đơn giản và ít lỗi hơn.

### 3.3 Kiểm tra event.source

Nếu host có hai iframe cùng origin, chỉ kiểm tra `event.origin` có thể chấp nhận message từ iframe không đúng chức năng.

~~~javascript
const paymentFrame = document.querySelector("#payment-frame");

window.addEventListener("message", (event) => {
  if (event.origin !== "https://pay.example.test") return;
  if (event.source !== paymentFrame.contentWindow) return;

  processPaymentMessage(event.data);
});
~~~

`event.source` đặc biệt hữu ích khi một origin phục vụ nhiều ứng dụng hoặc nhiều iframe có quyền khác nhau.

### 3.4 Không dựa vào isTrusted

`event.isTrusted` không thay thế việc kiểm tra origin, source và schema. Nó không chứng minh sender là một ứng dụng cụ thể hoặc message được phép kích hoạt hành động nghiệp vụ.

## 4. targetOrigin và wildcard

Một lỗi phổ biến là gửi dữ liệu nhạy cảm bằng wildcard:

~~~javascript
popup.postMessage(
  { type: "AUTH_RESULT", token: accessToken },
  "*"
);
~~~

Wildcard cho phép giao message bất kể origin hiện tại của cửa sổ đích. Nếu popup hoặc iframe bị điều hướng, dữ liệu có thể tới nhầm document.

Ưu tiên origin đích cụ thể:

~~~javascript
popup.postMessage(
  { type: "AUTH_RESULT", code: authorizationCode },
  "https://login.example.test"
);
~~~

Nếu origin không khớp, browser không giao message tới document đó. Không chuyển sang wildcard chỉ để khắc phục lỗi tích hợp; hãy kiểm tra URL và lifecycle của cửa sổ.

### 4.1 Trường hợp opaque origin

Iframe sandbox không có `allow-same-origin` có thể có opaque origin. Một số trường hợp gửi message tới opaque origin cần `targetOrigin` là `"*"` vì không có origin tuple để chỉ định.

Nếu thiết kế buộc phải dùng wildcard:

- Không gửi secret hoặc token có giá trị cao.
- Kiểm tra `event.source` là đúng iframe.
- Dùng handshake có giới hạn và chỉ chấp nhận một lần.
- Cấp `MessageChannel` khi phù hợp.
- Validate mọi message sau khi tạo channel.
- Giới hạn quyền của iframe bằng sandbox.

Wildcard không trở nên an toàn chỉ vì iframe có sandbox. Cần đánh giá nội dung iframe, khả năng navigation và cách cấp capability.

### 4.2 Không dựa vào mặc định khó hiểu

Các overload hiện đại của `postMessage` có thể nhận options object. Khi gửi dữ liệu cross-origin, khai báo rõ target origin thay vì dựa vào mặc định hoặc chuỗi cấu hình khó đọc.

## 5. Thiết kế message schema

Không gửi chuỗi tự do rồi suy đoán lệnh từ prefix. Dùng schema ổn định:

~~~json
{
  "version": 1,
  "type": "PAYMENT_STATUS",
  "requestId": "req-7f12",
  "payload": {
    "status": "completed",
    "transactionId": "txn-42"
  }
}
~~~

| Trường | Mục đích |
|---|---|
| `version` | Quản lý thay đổi giao thức |
| `type` | Xác định loại message được cho phép |
| `requestId` | Liên kết request và response |
| `payload` | Dữ liệu của message type |
| `sequence` | Kiểm soát thứ tự nếu cần |
| `timestamp` | Hỗ trợ chẩn đoán, không chứng minh tính mới |
| `nonce` | Dùng trong handshake hoặc chống replay theo thiết kế |

### 5.1 Allowlist type

~~~javascript
const allowedTypes = new Set([
  "READY",
  "RESIZE",
  "PAYMENT_STATUS",
  "CLOSE"
]);

if (!allowedTypes.has(message.type)) return;
~~~

Không gọi hàm động dựa trên dữ liệu sender như `window[message.action]()` hoặc `api[message.method](message.payload)` nếu không có allowlist và kiểm soát tham số chặt chẽ.

### 5.2 Validate riêng theo type

Mỗi message type cần quy định:

- Field bắt buộc và kiểu dữ liệu.
- Giá trị enum hợp lệ.
- Độ dài tối đa.
- Định dạng identifier.
- Field không được phép xuất hiện.
- Trạng thái ứng dụng được phép nhận message.

Ví dụ, RESIZE chỉ cần chiều cao dạng số trong khoảng hợp lý. PAYMENT_STATUS cần status trong enum và transaction identifier hợp lệ.

### 5.3 Chống replay và message lặp

Timestamp do sender gửi có thể sai hoặc bị giả mạo. Nếu cần chống replay, dùng nonce dùng một lần, sequence number gắn với session hoặc state server-side.

Với message gây tác động:

- Dùng requestId duy nhất.
- Theo dõi request đã xử lý.
- Thiết kế thao tác idempotent nếu có thể.
- Kiểm tra state transition.
- Xác minh quyền và trạng thái giao dịch ở server.
- Không xử lý lại command chỉ vì nhận message trùng.

## 6. Rủi ro bảo mật cần kiểm thử

### 6.1 Trust tất cả origin

~~~javascript
window.addEventListener("message", (event) => {
  updateAccount(event.data);
});
~~~

Handler này không kiểm tra sender, schema hoặc quyền. Trang không đáng tin có thể gửi dữ liệu khiến host thực hiện hành động.

### 6.2 So khớp origin bằng substring

~~~javascript
if (event.origin.indexOf("trusted.example") !== -1) {
  process(event.data);
}
~~~

Origin `https://trusted.example.attacker.invalid` có thể vượt qua kiểm tra substring. So sánh origin string chính xác.

### 6.3 Chỉ kiểm tra origin, bỏ qua source

Nếu nhiều iframe cùng origin, message từ context khác có thể bị hiểu nhầm là message từ widget được tin cậy. Lưu tham chiếu cửa sổ dự kiến và kiểm tra `event.source`.

### 6.4 Gửi secret bằng wildcard

Nếu cửa sổ đích điều hướng trước khi message được giao, wildcard có thể làm dữ liệu tới origin khác. Dùng targetOrigin cụ thể và giảm dữ liệu bí mật gửi qua message.

### 6.5 Xử lý message như lệnh có đặc quyền

Không để message trực tiếp xóa tài khoản, thay đổi email, xác nhận thanh toán, tạo API key hoặc truy cập dữ liệu tenant khác. Server vẫn phải kiểm tra session, CSRF protection khi áp dụng, authorization và business rules.

### 6.6 DOM XSS từ event.data

Dữ liệu message có thể chứa HTML do sender kiểm soát. Ví dụ nguy hiểm:

~~~javascript
window.addEventListener("message", (event) => {
  document.querySelector("#output").innerHTML = event.data.html;
});
~~~

Nếu payload chứa markup có thể thực thi, ứng dụng có thể tạo DOM XSS. Nếu chỉ cần hiển thị văn bản, dùng textContent:

~~~javascript
window.addEventListener("message", (event) => {
  document.querySelector("#output").textContent =
    String(event.data);
});
~~~

Nếu cần rich HTML, dùng sanitizer được duy trì tốt, allowlist rõ ràng và cân nhắc Trusted Types. Origin validation không làm payload HTML trở nên an toàn.

### 6.7 Prototype pollution và merge object

Không merge message object tùy ý vào state:

~~~javascript
Object.assign(appConfig, event.data);
~~~

Chọn field bằng allowlist, validate schema và tránh recursive merge không an toàn.

### 6.8 Confused deputy

Một iframe ít quyền có thể yêu cầu host gọi API bằng session của người dùng. Nếu host không xác minh ý định, state và quyền nghiệp vụ, host trở thành confused deputy. Giới hạn giao thức ở các thao tác cần thiết và kiểm tra authorization ở server.

## 7. Iframe sandbox và opaque origin

Ví dụ iframe:

~~~html
<iframe
  id="untrusted-widget"
  src="https://widget.example.test/embed"
  sandbox="allow-scripts">
</iframe>
~~~

Khi sandbox không có `allow-same-origin`, document có opaque origin và `event.origin` có thể là `"null"`.

### 7.1 Không tin cậy origin null

Giá trị null không nhận diện một website duy nhất. Nhiều opaque origin khác nhau có thể cùng serialize thành null.

Không dùng:

~~~javascript
if (event.origin === "null") {
  trustMessage(event.data);
}
~~~

Kiểm tra source window vẫn quan trọng, nhưng cũng cần đánh giá navigation và nội dung có thể chạy bên trong iframe.

### 7.2 Cấp quyền sandbox tối thiểu

| Token | Tác động |
|---|---|
| `allow-scripts` | Cho phép script trong iframe chạy |
| `allow-forms` | Cho phép submit form |
| `allow-popups` | Cho phép mở popup |
| `allow-same-origin` | Giữ origin thực thay vì opaque origin |
| `allow-top-navigation` | Cho phép điều hướng browsing context cấp cao theo phạm vi token |

Không thêm token chỉ để làm message hoạt động. Một số tổ hợp sandbox làm giảm đáng kể mức cách ly.

### 7.3 Test navigation

Một test nâng cao cần:

1. Tải iframe từ origin tin cậy.
2. Lưu tham chiếu `contentWindow`.
3. Gửi message hợp lệ.
4. Điều hướng iframe sang origin khác.
5. Gửi message sau navigation.
6. Xác nhận targetOrigin cũ không giao message tới document mới.
7. Xác nhận receiver từ chối message không đúng origin hoặc source.

`WindowProxy` có thể tiếp tục đại diện cho browsing context qua navigation. Không giả định tham chiếu source tự đổi; kiểm tra origin và trạng thái handshake.

## 8. MessageChannel

`MessageChannel` tạo hai `MessagePort` nối với nhau. Mỗi context nhận một port và giao tiếp qua kênh riêng.

Host gửi port cho iframe:

~~~javascript
const frame = document.querySelector("#widget");
const channel = new MessageChannel();

channel.port1.addEventListener("message", (event) => {
  handleWidgetMessage(event.data);
});

channel.port1.start();

frame.contentWindow.postMessage(
  { type: "INIT", version: 1 },
  "https://widget.example.test",
  [channel.port2]
);
~~~

Iframe nhận port:

~~~javascript
window.addEventListener("message", (event) => {
  if (event.origin !== "https://app.example.test") return;
  if (event.source !== window.parent) return;

  if (
    event.data === null ||
    typeof event.data !== "object" ||
    event.data.type !== "INIT" ||
    event.data.version !== 1
  ) {
    return;
  }

  const port = event.ports[0];
  if (!port) return;

  port.onmessage = (messageEvent) => {
    handleHostMessage(messageEvent.data);
  };

  port.start();
}, { once: true });
~~~

Đây là ví dụ khung. Cần kiểm tra số port, schema, handshake và lifecycle. Nếu INIT có thể đến lặp, từ chối port mới hoặc đóng channel cũ có kiểm soát.

### 8.1 Port không thay thế xác thực ban đầu

Sau khi transfer, message qua port không có cùng mô hình xác thực origin/source như window message ban đầu. Việc sở hữu port là một capability.

- Chỉ transfer port sau khi xác minh sender và trạng thái handshake.
- Giới hạn loại message được phép qua port.
- Đóng port khi iframe unload, navigation hoặc tích hợp kết thúc.
- Không xem port là quyền truy cập vô hạn vào mọi API của host.

### 8.2 Handshake và kết nối cũ

Handshake nên có state rõ ràng như idle, connecting, connected và closed. Chỉ chấp nhận INIT khi đang ở trạng thái phù hợp.

Có thể dùng nonce ngẫu nhiên một lần để liên kết request và response. Nonce cần được tạo bằng nguồn ngẫu nhiên mật mã khi dùng cho mục đích bảo mật; không dùng Math.random làm token bảo mật. Khi tạo kết nối mới, đóng port cũ và vô hiệu hóa request identifier của phiên trước.

## 9. Popup, opener và COOP

Popup thường được tạo bằng `window.open()`:

~~~javascript
const authWindow = window.open(
  "https://login.example.test/authorize",
  "auth",
  "popup,width=480,height=640"
);
~~~

Trang đăng nhập có thể gửi kết quả về opener:

~~~javascript
window.opener.postMessage(
  { type: "AUTH_COMPLETE", code: "temporary-code" },
  "https://app.example.test"
);
~~~

Host kiểm tra origin và source:

~~~javascript
window.addEventListener("message", (event) => {
  if (event.origin !== "https://login.example.test") return;
  if (event.source !== authWindow) return;

  if (
    event.data === null ||
    typeof event.data !== "object" ||
    event.data.type !== "AUTH_COMPLETE"
  ) {
    return;
  }

  completeLogin(event.data.code);
});
~~~

Cần validate code format, request correlation, thời hạn và state; việc xác thực cuối cùng phải hoàn tất ở server. Không coi message AUTH_COMPLETE là bằng chứng đăng nhập thành công.

### 9.1 COOP và noopener

`noopener` hoặc Cross-Origin-Opener-Policy (COOP) có thể cắt quan hệ opener hoặc thay đổi browsing context group. Popup có thể không truy cập được `window.opener` như dự kiến.

Test popup với response header COOP gần production. Không bỏ noopener hoặc nới COOP chỉ để sửa một luồng message chưa được thiết kế đúng.

### 9.2 Không truyền access token dài hạn

Ưu tiên authorization code dùng một lần, thời hạn ngắn và ràng buộc với state/PKCE theo giao thức đăng nhập. Host đổi code với server và xác minh callback state. Không gửi mật khẩu, refresh token hoặc access token dài hạn qua message nếu có thiết kế khác an toàn hơn.

## 10. postMessage, cookie, CSRF và SOP

`postMessage` không chia sẻ cookie trực tiếp. Cookie vẫn tuân theo domain, path, Secure, HttpOnly, SameSite và các quy tắc browser.

Tuy nhiên, message có thể khiến host gửi request tới server bằng session cookie của người dùng. Đây là lúc cần đánh giá CSRF và authorization.

### 10.1 Message không phải CSRF token

Origin được allowlist không chứng minh người dùng đã chủ ý thực hiện hành động. Nếu host dùng cookie session để gửi request thay mặt người dùng, server vẫn cần CSRF protection phù hợp.

Không thay CSRF token bằng `event.origin`. Origin validation ở message handler và CSRF validation ở server bảo vệ những ranh giới khác nhau.

### 10.2 SameSite không thay message validation

SameSite kiểm soát việc gửi cookie trong một số ngữ cảnh cross-site. Nó không xác thực sender postMessage. Hai subdomain cùng site vẫn có thể là origin khác nhau.

Vì vậy vẫn cần kiểm tra origin, source và schema ngay cả khi cookie có SameSite=Lax hoặc Strict.

### 10.3 SOP vẫn tồn tại

`postMessage` là API trao đổi dữ liệu có chủ đích. Nó không tắt SOP và không cho phép sender tự đọc DOM receiver. Mỗi phía nhận payload và tự quyết định có tin và xử lý nó không.

## 11. Test harness với hai origin

Kiểm thử cross-origin cần hai origin thật sự khác nhau. Khác port cũng tạo origin khác nhau.

Ví dụ local lab:

- Host app: `http://localhost:3000`.
- Widget: `http://localhost:4000`.
- Attacker simulation: `http://localhost:5000`.

Chỉ đổi path không tạo cross-origin nếu scheme, host và port vẫn giống nhau.

### 11.1 Host page

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <title>postMessage host lab</title>
</head>
<body>
  <iframe id="widget" src="http://localhost:4000/widget.html"></iframe>
  <pre id="log"></pre>
  <script src="/host.js"></script>
</body>
</html>
~~~

### 11.2 Receiver phía host

~~~javascript
const widget = document.querySelector("#widget");
const log = document.querySelector("#log");
const widgetOrigin = "http://localhost:4000";

function writeLog(message) {
  log.textContent += String(message) + "\n";
}

window.addEventListener("message", (event) => {
  if (event.origin !== widgetOrigin) {
    writeLog("Rejected: origin");
    return;
  }

  if (event.source !== widget.contentWindow) {
    writeLog("Rejected: source");
    return;
  }

  const message = event.data;

  if (
    message === null ||
    typeof message !== "object" ||
    Array.isArray(message)
  ) {
    writeLog("Rejected: shape");
    return;
  }

  if (message.version !== 1 || message.type !== "READY") {
    writeLog("Rejected: type or version");
    return;
  }

  writeLog("Accepted: widget ready");
});
~~~

### 11.3 Widget sender

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <title>Widget lab</title>
</head>
<body>
  <button id="send">Send READY</button>
  <script>
    document.querySelector("#send").addEventListener("click", () => {
      window.parent.postMessage(
        { version: 1, type: "READY" },
        "http://localhost:3000"
      );
    });
  </script>
</body>
</html>
~~~

### 11.4 Attacker simulation

Tạo trang ở origin thứ ba và gửi message giả:

~~~javascript
window.parent.postMessage(
  { version: 1, type: "READY" },
  "http://localhost:3000"
);
~~~

Mở host trong popup hoặc tạo iframe khác trỏ tới trang attacker. Xác nhận handler từ chối vì origin hoặc source không khớp. Một message bình thường từ origin không được tin cậy đã đủ để test origin validation; không cần payload XSS.

## 12. Ma trận kiểm thử bảo mật

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| PM-01 | Origin allowlist, source đúng, schema hợp lệ | Chấp nhận |
| PM-02 | Origin khác allowlist | Từ chối |
| PM-03 | Hostname gần giống domain tin cậy | Từ chối |
| PM-04 | Cùng hostname nhưng khác scheme | Từ chối nếu scheme không được phép |
| PM-05 | Cùng hostname nhưng khác port | Từ chối nếu port không được phép |
| PM-06 | Origin đúng nhưng source là iframe khác | Từ chối |
| PM-07 | Source đúng nhưng origin sau navigation không đúng | Từ chối |
| PM-08 | event.data là null, primitive hoặc array sai schema | Từ chối |
| PM-09 | Message type không biết | Từ chối |
| PM-10 | Version không hỗ trợ | Từ chối hoặc thương lượng rõ ràng |
| PM-11 | Payload vượt giới hạn | Từ chối có kiểm soát |
| PM-12 | Message lặp với cùng requestId | Không thực hiện lần hai |
| PM-13 | Message đến sai state | Từ chối |
| PM-14 | Sender gửi chuỗi HTML | Hiển thị như text, không thực thi |
| PM-15 | Iframe sandbox có origin opaque | Không tin cậy chỉ vì origin là null |
| PM-16 | MessageChannel nhận port ngoài handshake | Từ chối hoặc đóng port |
| PM-17 | Popup bị đóng trước callback | Xử lý timeout/close, không crash |
| PM-18 | Popup hoặc iframe điều hướng khi handshake | Hủy hoặc thiết lập lại an toàn |
| PM-19 | Message yêu cầu hành động nhạy cảm | Server vẫn kiểm tra quyền và CSRF |
| PM-20 | Message gửi liên tục | Rate limit hoặc giới hạn xử lý |

### 12.1 Test targetOrigin

Gửi message với targetOrigin đúng, sai và wildcard. Điều hướng cửa sổ đích tới origin thứ ba trước khi gửi. Xác nhận message có targetOrigin cũ không bị giao cho document mới.

### 12.2 Test event.origin và event.source độc lập

Tạo hai iframe cùng origin. Chỉ cho phép iframe thứ nhất. Gửi message từ iframe thứ hai. Origin check sẽ pass nhưng source check phải fail.

### 12.3 Test dữ liệu không hợp lệ

Gửi null, chuỗi, số, array, object thiếu type, type lạ, version cũ, payload sai kiểu, string quá dài, object lồng sâu và identifier sai định dạng.

Handler phải từ chối an toàn, không làm hỏng listener hoặc thay đổi state.

### 12.4 Test navigation race

Xác minh targetOrigin giới hạn nơi nhận, event.origin được kiểm tra, event.source khớp context dự kiến, handshake cũ bị vô hiệu hóa và port cũ được đóng sau navigation.

### 12.5 Test XSS sink

Gửi chuỗi HTML lab:

~~~text
<img src=x onerror=alert(1)>
~~~

Nếu giao diện chỉ cần hiển thị văn bản, chuỗi phải xuất hiện như text node. Không có event handler nào được thực thi. Dùng console và DOM inspector để xác nhận.

## 13. Tự động hóa với Playwright

Browser automation có thể tạo các origin local và xác nhận handler nhận hoặc từ chối message. Ví dụ skeleton:

~~~javascript
import { test, expect } from "@playwright/test";

test("accepts message from the expected widget", async ({ page }) => {
  await page.goto("http://localhost:3000");

  const frame = page.frameLocator("#widget");
  await frame.locator("#send").click();

  await expect(page.locator("#log")).toContainText(
    "Accepted: widget ready"
  );
});

test("rejects message from an untrusted origin", async ({ page }) => {
  await page.goto("http://localhost:3000");

  await page.evaluate(() => {
    const attacker = document.createElement("iframe");
    attacker.src = "http://localhost:5000/attacker.html";
    document.body.appendChild(attacker);
  });

  await expect(page.locator("#log")).toContainText(
    "Rejected: origin"
  );
});
~~~

Đây là skeleton minh họa. Fixture phải phục vụ ba origin local và bảo đảm trang attacker gửi message sau khi tải. Không dùng sleep cố định để đồng bộ; dùng event, locator hoặc điều kiện trạng thái.

### 13.1 Unit test và browser integration test

Unit test kiểm tra schema validator với object fixture. Browser integration test cần xác minh:

- Browser thực sự tạo MessageEvent.
- Origin được serialize đúng.
- event.source tham chiếu đúng browsing context.
- targetOrigin hoạt động khi navigation.
- Iframe sandbox và popup hoạt động theo policy.
- MessageChannel transfer port đúng thiết kế.

Unit test không thay thế kiểm thử phụ thuộc browser lifecycle.

### 13.2 Bằng chứng kiểm thử

Mỗi test nên lưu origin host/sender, loại browsing context, targetOrigin, event.origin, source expectation, message type/version, kết quả accept/reject, state trước/sau, browser/version và console error. Dùng fixture giả lập; không lưu token hoặc dữ liệu cá nhân.

## 14. CSP, frame policy, sandbox và COOP

`postMessage` là một phần của thiết kế tích hợp browser. Các cơ chế khác có thể ảnh hưởng việc nhúng hoặc quan hệ giữa cửa sổ.

- `frame-src` giới hạn nguồn mà trang hiện tại được phép nhúng.
- `frame-ancestors` giới hạn những origin nào được phép nhúng trang hiện tại.
- Iframe sandbox giới hạn script, form, popup, navigation và origin.
- COOP có thể tách browsing context group và ảnh hưởng opener.
- Trusted Types giúp hạn chế một số luồng dữ liệu vào HTML sink trong browser hỗ trợ.

Trusted Types không xác thực sender hoặc message schema. CSP cũng không thay thế origin validation. Khi test thất bại, kiểm tra response header thực tế trước khi thay đổi policy bảo vệ.

## 15. Quy trình điều tra khi test thất bại

Khi message không đến hoặc bị từ chối, kiểm tra theo thứ tự:

1. Hai browsing context đã tải xong chưa?
2. Scheme, hostname và port của mỗi URL là gì?
3. targetOrigin có khớp origin đích hiện tại không?
4. event.origin có đúng allowlist không?
5. event.source có phải đúng WindowProxy không?
6. Listener đã được đăng ký trước khi gửi chưa?
7. event.data có đúng schema và version không?
8. Iframe có sandbox hoặc opaque origin không?
9. Popup/opener có bị ảnh hưởng bởi COOP hoặc noopener không?
10. Handler có exception hoặc state transition không hợp lệ không?
11. MessagePort đã được transfer và start đúng cách chưa?
12. CSP có chặn iframe hoặc script cần thiết không?

Không khắc phục bằng cách bỏ origin check hoặc đổi targetOrigin thành wildcard. Tìm điều kiện sai trong URL, handshake hoặc lifecycle.

## 16. Lỗi triển khai thường gặp

### 16.1 Dùng wildcard cho mọi message

Wildcard có thể gửi message tới document không còn là origin dự kiến. Dùng targetOrigin cụ thể khi có thể.

### 16.2 Chỉ kiểm tra event.origin

Một origin có thể phục vụ nhiều iframe. Kiểm tra event.source để xác định đúng context.

### 16.3 Kiểm tra origin bằng substring

So khớp yếu có thể chấp nhận hostname do attacker kiểm soát. Dùng exact match.

### 16.4 Tin origin null

null là serialization của opaque origin, không phải danh tính duy nhất.

### 16.5 Parse message theo kiểu đoán

Dùng version, type, schema và allowlist để tránh xử lý nhầm command.

### 16.6 Dùng message thay authorization

Sender hợp lệ không đồng nghĩa người dùng được phép thực hiện mọi hành động. Server vẫn kiểm tra quyền và trạng thái.

### 16.7 Đưa message vào innerHTML

Structured clone không làm string an toàn cho HTML. Dùng textContent hoặc sanitizer/Trusted Types.

### 16.8 Không xử lý message lặp

Dùng requestId, idempotency và state transition cho hành động có tác động.

### 16.9 Không đóng MessagePort cũ

Đóng port khi session kết thúc, navigation hoặc handshake mới.

### 16.10 Test cùng origin

Khác path không tạo cross-origin. Dùng host hoặc port khác nhau và xác minh origin trong browser.

### 16.11 Chỉ gọi handler trực tiếp trong unit test

Unit test không kiểm tra targetOrigin, event.origin, event.source hoặc browser lifecycle. Cần integration test với cửa sổ và iframe thật.

### 16.12 Bỏ qua COOP và sandbox

Test local không có header production có thể pass trong khi production thất bại. Dùng cấu hình gần production.

## 17. Checklist review postMessage

- [ ] Sender khai báo targetOrigin cụ thể.
- [ ] Không gửi token hoặc dữ liệu nhạy cảm bằng wildcard.
- [ ] Receiver kiểm tra event.origin bằng exact allowlist.
- [ ] Receiver kiểm tra event.source với browsing context dự kiến.
- [ ] Không dùng substring, regex yếu hoặc hostname đơn lẻ để xác thực origin.
- [ ] Có schema message rõ ràng, version và allowlist type.
- [ ] Validate kiểu, độ dài và enum của payload.
- [ ] Có giới hạn kích thước và tần suất xử lý.
- [ ] Kiểm tra state trước khi thực hiện hành động.
- [ ] Message lặp không gây tác động hai lần.
- [ ] Không render dữ liệu bằng innerHTML hoặc thực thi sample.
- [ ] Message không thay thế authorization hoặc CSRF protection.
- [ ] Iframe sandbox chỉ cấp token tối thiểu.
- [ ] Origin opaque null không được xem là danh tính đáng tin.
- [ ] Navigation và handshake cũ được xử lý.
- [ ] MessageChannel chỉ được cấp sau handshake hợp lệ.
- [ ] Port được đóng khi kết nối kết thúc.
- [ ] Popup test có xét noopener và COOP.
- [ ] Có integration test với ít nhất hai origin thực sự khác nhau.
- [ ] Có test origin sai, source sai, schema sai và payload bất thường.
- [ ] Có test XSS sink và xác nhận output được render an toàn.
- [ ] Test dùng cấu hình gần production và ghi lại browser/version.

## 18. Bài thực hành

Thực hiện trong local lab hoặc môi trường do bạn kiểm soát.

### Bài 1: Xác minh origin

Chạy host ở port 3000 và widget ở port 4000. Gửi message từ widget tới host. Ghi nhận event.origin và xác nhận hai URL khác origin vì port khác nhau.

### Bài 2: So sánh targetOrigin

Gửi message với targetOrigin đúng, sai và wildcard. Điều hướng iframe trước khi gửi. Ghi nhận document nào nhận message.

### Bài 3: Phát hiện lỗi substring

Tạo origin giả lập có hostname chứa chuỗi của domain tin cậy nhưng không thuộc allowlist. Xác nhận exact match từ chối và test phát hiện substring matcher yếu.

### Bài 4: Kiểm tra event.source

Tạo hai iframe cùng origin. Chỉ đăng ký một iframe là trusted source. Gửi message từ iframe còn lại và xác nhận handler từ chối.

### Bài 5: Validate schema

Gửi message sai kiểu, thiếu field, type lạ, version cũ, payload quá dài và object lồng sâu. Xác nhận không có state mutation hoặc exception ngoài dự kiến.

### Bài 6: Kiểm tra navigation

Tải widget hợp lệ, bắt đầu handshake rồi điều hướng iframe sang origin khác. Xác nhận message cũ và port cũ không được dùng để thực hiện hành động mới.

### Bài 7: Iframe sandbox

So sánh iframe có và không có allow-same-origin. Quan sát event.origin. Xác nhận origin null không được chấp nhận như origin tin cậy.

### Bài 8: MessageChannel

Thiết lập channel sau handshake. Thử INIT lặp, transfer port không hợp lệ và gửi message sau khi đóng port. Xác nhận state machine từ chối trường hợp sai.

### Bài 9: DOM XSS

Gửi chuỗi HTML lab qua message và hiển thị trong host. So sánh innerHTML với textContent. Xác nhận cách hiển thị an toàn không tạo element thực thi.

### Bài 10: Authorization phía server

Gửi message yêu cầu cập nhật dữ liệu từ sender được allowlist nhưng không có quyền nghiệp vụ. Xác nhận server từ chối dù origin và source hợp lệ.

## 19. Câu hỏi tự kiểm tra

**1. postMessage cho phép điều gì?**

Nó cho phép browsing context trao đổi dữ liệu có chủ đích, kể cả khi khác origin, mà không cấp quyền đọc DOM trực tiếp qua SOP.

**2. targetOrigin khác event.origin như thế nào?**

targetOrigin giới hạn origin nhận ở phía gửi. event.origin cho biết origin sender tại thời điểm gửi ở phía nhận.

**3. Vì sao phải kiểm tra event.source?**

Để xác định message đến từ đúng iframe hoặc popup mà ứng dụng dự kiến, đặc biệt khi nhiều context cùng origin.

**4. Vì sao không dùng substring để kiểm tra origin?**

Hostname do attacker kiểm soát có thể chứa chuỗi hostname tin cậy. Exact match tránh nhầm lẫn này.

**5. Origin null có nghĩa gì?**

Nó thường biểu diễn opaque origin. Nhiều opaque origin khác nhau có thể cùng serialize thành null, nên không thể dùng giá trị này làm danh tính duy nhất.

**6. Structured clone có xác thực dữ liệu không?**

Không. Nó định nghĩa cách clone dữ liệu giữa context, không chứng minh nguồn gửi hoặc tính hợp lệ nghiệp vụ.

**7. MessageChannel có thay thế origin validation không?**

Không. Cần xác thực sender và handshake trước khi transfer port; sau đó vẫn validate message theo protocol.

**8. Vì sao postMessage không thay CSRF protection?**

Message có thể khiến host gửi request bằng cookie session. Server vẫn phải kiểm tra CSRF và authorization.

**9. Có thể kết luận XSS chỉ từ việc nhận HTML qua message không?**

Không. Cần xác định dữ liệu đi vào sink có thể thực thi. Nếu hiển thị bằng textContent, chuỗi HTML được hiển thị như văn bản.

**10. Test cross-origin cần điều kiện gì?**

Hai browsing context phải có origin khác nhau thực sự, khác scheme, host hoặc port. Chỉ đổi path không tạo cross-origin.

## Ghi nhớ

`postMessage` là kênh trao đổi dữ liệu qua ranh giới browsing context. Sender phải giới hạn nơi nhận bằng targetOrigin chính xác; receiver phải xác thực event.origin, event.source và schema trước khi xử lý. Origin đúng không tự cấp quyền nghiệp vụ. Dữ liệu message vẫn không đáng tin cậy và có thể tạo XSS nếu đưa vào DOM sink không an toàn. Kiểm thử nâng cao cần bao gồm navigation, iframe sandbox, origin opaque, popup/COOP, MessageChannel, replay, payload bất thường và authorization phía server. Dùng test harness với các origin khác nhau thật sự để xác minh hành vi browser.

## Tài liệu tham khảo

- [WHATWG HTML Standard: Web Messaging](https://html.spec.whatwg.org/multipage/web-messaging.html)
- [MDN: Window.postMessage()](https://developer.mozilla.org/en-US/docs/Web/API/Window/postMessage)
- [MDN: MessageEvent](https://developer.mozilla.org/en-US/docs/Web/API/MessageEvent)
- [MDN: MessageChannel](https://developer.mozilla.org/en-US/docs/Web/API/MessageChannel)
- [MDN: MessagePort](https://developer.mozilla.org/en-US/docs/Web/API/MessagePort)
- [MDN: HTMLIFrameElement sandbox](https://developer.mozilla.org/en-US/docs/Web/HTML/Element/iframe#sandbox)
- [MDN: Cross-Origin-Opener-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cross-Origin-Opener-Policy)
- [OWASP: HTML5 Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html)
- [Playwright: Frames](https://playwright.dev/docs/frames)
- [Playwright: Browser contexts](https://playwright.dev/docs/browser-contexts)
