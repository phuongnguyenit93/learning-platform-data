# Kiểm tra thông điệp postMessage an toàn giữa các browsing context

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích cách window.postMessage() trao đổi dữ liệu giữa cửa sổ, tab và iframe khác origin.
2. Xác minh cả event.origin và event.source trước khi xử lý message.
3. Kiểm tra cấu trúc, loại, kiểu dữ liệu, kích thước và trạng thái message theo protocol rõ ràng.
4. Gửi message với targetOrigin chính xác và hiểu rủi ro của wildcard *.
5. Xử lý opaque origin, navigation và handshake bằng MessageChannel.
6. Tránh DOM XSS, confused deputy và rò rỉ dữ liệu khi xử lý message.
7. Kiểm thử message flow bằng Chrome DevTools và xây dựng ma trận negative test.

> **Bối cảnh:** Module Browser Security phân tích ranh giới giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly. postMessage là API cho phép các browsing context trao đổi dữ liệu có chủ đích qua ranh giới origin. Cơ chế này hữu ích cho iframe, popup và tích hợp nhiều ứng dụng, nhưng mỗi message nhận được phải được xác minh như dữ liệu không tin cậy.

## 1. postMessage dùng để làm gì?

Same-Origin Policy (SOP) ngăn JavaScript của một origin tùy ý đọc DOM hoặc dữ liệu của origin khác. Tuy nhiên, ứng dụng đôi khi cần hai trang khác origin phối hợp:

- Trang thương mại nhúng widget thanh toán của đối tác.
- Cửa sổ đăng nhập popup cần thông báo kết quả cho trang mở nó.
- Một ứng dụng host nhúng dashboard ở origin riêng.
- Các micro-frontend chạy trên origin tách biệt cần trao đổi trạng thái giới hạn.

window.postMessage() cung cấp một kênh gửi message có chủ đích qua ranh giới đó:

```js
// Sender
targetWindow.postMessage(
  { type: "checkout:ready", version: 1 },
  "https://shop.example.test"
);
```

Trang nhận đăng ký message event:

```js
window.addEventListener("message", (event) => {
  console.log(event.origin);
  console.log(event.source);
  console.log(event.data);
});
```

Browser tạo MessageEvent với các thuộc tính quan trọng:

| Thuộc tính | Ý nghĩa | Cách dùng an toàn |
| --- | --- | --- |
| event.data | Dữ liệu message sau structured clone | Xem là input không tin cậy; validate schema và giá trị |
| event.origin | Serialized origin của sender tại thời điểm gọi postMessage | So sánh chính xác với allowlist |
| event.source | WindowProxy của browsing context gửi message | So sánh với cửa sổ/iframe đã dự kiến |
| event.ports | Các MessagePort được chuyển kèm | Chỉ nhận và dùng khi protocol có handshake rõ |

**Không xử lý event.data chỉ vì event có type message.** Một trang bất kỳ có thể cố gửi message tới cửa sổ của ứng dụng. Việc nhận message không đồng nghĩa sender đã được xác thực.

## 2. Hai lớp kiểm tra nguồn: origin và source

Khi nhận message, hãy xác minh đồng thời:

1. **Origin:** message có đến từ đúng scheme, host và port được tin cậy?
2. **Source:** message có đến từ đúng cửa sổ hoặc iframe mà ứng dụng đã chủ động mở/nhúng?

Ví dụ host nhúng một payment iframe:

```html
<iframe
  id="payment-frame"
  title="Payment"
  src="https://payments.partner.test/checkout">
</iframe>
```

```js
const paymentFrame = document.querySelector("#payment-frame");
const trustedPaymentOrigin = "https://payments.partner.test";

window.addEventListener("message", (event) => {
  if (event.origin !== trustedPaymentOrigin) return;
  if (event.source !== paymentFrame.contentWindow) return;

  // Chỉ sau hai kiểm tra nguồn mới xem xét event.data.
  handlePaymentMessage(event.data);
});
```

event.origin xác định origin của sender tại thời điểm message được gửi. event.source xác định browsing context gửi message. Kết hợp hai điều kiện giúp tránh nhận message từ một cửa sổ khác nhưng tình cờ có cùng origin.

### Vì sao không chỉ kiểm tra hostname?

Origin là bộ ba **scheme + host + port**. Các origin sau khác nhau:

```text
https://payments.partner.test
http://payments.partner.test
https://payments.partner.test:8443
https://admin.partner.test
```

Không dùng substring hoặc suffix:

```js
// SAI: host giả có thể chứa chuỗi tin cậy
if (event.origin.includes("partner.test")) {
  handleMessage(event.data);
}

// SAI: origin tấn công có thể kết thúc bằng chuỗi này
if (event.origin.endsWith("partner.test")) {
  handleMessage(event.data);
}
```

Hãy so sánh serialized origin chính xác:

```js
const trustedOrigins = new Set([
  "https://payments.partner.test",
  "https://portal.example.test"
]);

if (!trustedOrigins.has(event.origin)) return;
```

Không đưa wildcard, origin staging hoặc mọi subdomain vào allowlist chỉ để tránh lỗi tích hợp. Mỗi origin được tin cậy phải có chủ sở hữu và mục đích rõ ràng.

### postMessage khác CORS như thế nào?

Hai cơ chế đều liên quan đến giao tiếp cross-origin nhưng giải quyết vấn đề khác nhau:

| Cơ chế | Mục đích | Ai kiểm tra? |
| --- | --- | --- |
| SOP | Giới hạn script đọc dữ liệu/DOM cross-origin | Browser |
| CORS | Cho phép script đọc một số response cross-origin theo policy server | Browser dựa trên response header |
| postMessage | Cho phép hai browsing context trao đổi message có chủ đích | Ứng dụng gửi/nhận phải kiểm tra origin, source và payload |

CORS không xác thực message event và postMessage không cấp quyền đọc response fetch/XHR. Một ứng dụng có thể dùng cả hai, nhưng không thay thế lẫn nhau.

## 3. Kiểm tra event.source theo browsing context đã đăng ký

So sánh event.source giúp ràng buộc message với đúng cửa sổ:

### Iframe

```js
const frame = document.getElementById("reports-frame");

window.addEventListener("message", (event) => {
  if (event.origin !== "https://reports.example.test") return;
  if (event.source !== frame.contentWindow) return;

  // Kiểm tra message sau khi xác minh nguồn.
});
```

### Popup

```js
const popup = window.open(
  "https://login.identity.test/authorize",
  "login-popup",
  "popup,width=520,height=680"
);

window.addEventListener("message", (event) => {
  if (event.origin !== "https://login.identity.test") return;
  if (event.source !== popup) return;

  // Chỉ nhận kết quả từ popup mà ứng dụng đã mở.
});
```

Trong ứng dụng thật, phải xử lý trường hợp popup bị chặn, đóng hoặc tham chiếu không còn hợp lệ. Nếu ứng dụng dùng noopener, cửa sổ mở có thể không còn window.opener; khi đó không thiết kế protocol phụ thuộc vào opener.

### WindowProxy và navigation

event.source là tham chiếu tới browsing context (WindowProxy), không phải bằng chứng origin cố định cho mọi thời điểm. Một iframe hoặc popup có thể điều hướng sang tài liệu khác trong cùng browsing context. Vì vậy:

- Kiểm tra event.origin ở từng message.
- Kiểm tra event.source có đúng context đã đăng ký.
- Không giả định một lần kiểm tra origin trước đó áp dụng cho các message sau.
- Khi chủ động điều hướng frame/popup, cập nhật trạng thái protocol và chỉ chấp nhận message trong đúng giai đoạn.

event.origin phản ánh origin của sender khi message được gửi. Nếu cửa sổ đã điều hướng trước lúc message được giao, origin hiện tại của cửa sổ có thể khác giá trị event.origin; vẫn phải dùng origin trong event để xác định sender của message đó.

Không đọc thuộc tính của cửa sổ cross-origin để cố xác minh sender; SOP giới hạn việc đó. So sánh WindowProxy bằng event.source là phép kiểm tra identity của browsing context, còn event.origin xác định origin của message.

## 4. Validate message schema, không chỉ validate nguồn

Một origin đáng tin cậy vẫn có thể có bug, bị XSS hoặc gửi dữ liệu sai định dạng. Vì vậy, sau khi xác minh origin/source, cần kiểm tra payload.

Một protocol đơn giản có thể yêu cầu:

```json
{
  "type": "checkout:complete",
  "version": 1,
  "requestId": "req-123",
  "payload": {
    "orderId": "order-456",
    "status": "paid"
  }
}
```

Các bước kiểm tra nên bao gồm:

1. Dữ liệu phải có cấu trúc object đúng theo protocol.
2. type phải nằm trong allowlist message type.
3. version phải được hỗ trợ.
4. Các field bắt buộc phải tồn tại và có đúng kiểu.
5. String có giới hạn độ dài; array/object có giới hạn số phần tử và độ sâu phù hợp.
6. Enum chỉ nhận giá trị cho phép.
7. Không chấp nhận field lạ nếu protocol không cần mở rộng tự do.
8. Kiểm tra message có hợp lệ với trạng thái hiện tại của ứng dụng hay không.

### Ví dụ validator chặt

```js
const allowedStatuses = new Set(["paid", "failed", "cancelled"]);

function isRecord(value) {
  return value !== null &&
    typeof value === "object" &&
    !Array.isArray(value);
}

function validateCheckoutMessage(data) {
  if (!isRecord(data)) return null;

  const topKeys = Object.keys(data).sort();
  const expectedTopKeys = ["payload", "requestId", "type", "version"];
  if (topKeys.join("|") !== expectedTopKeys.join("|")) return null;

  if (data.type !== "checkout:complete") return null;
  if (data.version !== 1) return null;
  if (typeof data.requestId !== "string" || data.requestId.length > 80) {
    return null;
  }

  if (!isRecord(data.payload)) return null;
  const payloadKeys = Object.keys(data.payload).sort();
  if (payloadKeys.join("|") !== "orderId|status") return null;

  const { orderId, status } = data.payload;
  if (typeof orderId !== "string" || orderId.length < 1 || orderId.length > 64) {
    return null;
  }
  if (!allowedStatuses.has(status)) return null;

  return {
    requestId: data.requestId,
    orderId,
    status
  };
}
```

Validator trả về một object mới chứa đúng các giá trị đã kiểm tra. Code nghiệp vụ chỉ dùng kết quả này, không tiếp tục tin object tùy ý từ event.data.

Ví dụ trên dùng allowlist field chính xác để minh họa protocol nhỏ. Với protocol lớn, nên dùng schema validator được duy trì, định nghĩa rõ optional field, versioning, giới hạn kích thước và quy tắc tương thích.

### Kiểm tra trạng thái và request correlation

Một message checkout:complete không nên được chấp nhận ở bất kỳ thời điểm nào. Ứng dụng có thể yêu cầu:

- Đã gửi request checkout tương ứng.
- requestId khớp request đang chờ.
- orderId thuộc giao dịch đang xử lý.
- Message chưa được xử lý trước đó.
- Trạng thái đơn hàng được xác nhận ở backend trước khi ghi nhận thanh toán.

requestId giúp liên kết request/response và phát hiện message lặp, nhưng **không phải bí mật xác thực** nếu attacker có thể đọc hoặc dự đoán nó.

## 5. Gửi message với targetOrigin chính xác

Sender cũng phải hạn chế recipient. Tham số thứ hai của postMessage() là targetOrigin:

```js
const frame = document.querySelector("#payment-frame");

frame.contentWindow.postMessage(
  {
    type: "checkout:init",
    version: 1
  },
  "https://payments.partner.test"
);
```

Browser chỉ giao message nếu target browsing context vẫn ở origin được chỉ định khi giao. Nếu frame đã điều hướng sang origin khác, message không được gửi tới tài liệu mới.

### Không dùng wildcard cho dữ liệu nhạy cảm

```js
// RỦI RO: gửi message tới bất kỳ origin nào mà cửa sổ đích đang ở
popup.postMessage(
  { type: "auth:result", accessToken: token },
  "*"
);
```

Nếu popup điều hướng sang trang do attacker kiểm soát trước lúc message được gửi, dữ liệu có thể bị lộ. Với thông tin nhạy cảm, chỉ dùng exact target origin:

```js
popup.postMessage(
  { type: "auth:complete", code: authorizationCode },
  "https://login.identity.test"
);
```

Ngay cả với targetOrigin chính xác, không gửi access token hoặc credential nếu protocol có thể dùng authorization code ngắn hạn, một lần và được backend đổi qua kênh xác thực phù hợp. postMessage không tự mã hóa bí mật ở tầng ứng dụng và không thay authentication.

### Khi nào có thể dùng '*'

Có trường hợp recipient có opaque origin, ví dụ một số sandboxed iframe không có allow-same-origin, hoặc data: document. Browser không thể so khớp một origin thông thường cho các context này, nên việc gửi có thể cần targetOrigin "*" theo đặc tính API.

Nếu bắt buộc dùng wildcard:

- Không gửi credential, token hoặc dữ liệu bí mật.
- Xác minh event.source và protocol ở phía nhận.
- Dùng một kênh/port capability được chuyển sau khi thiết lập context đã xác minh nếu phù hợp.
- Giới hạn dữ liệu ở mức tối thiểu và thiết kế để message bị lộ không tạo quyền truy cập.

Không dùng wildcard như lựa chọn tiện lợi cho một iframe có origin bình thường.

## 6. Opaque origin và giá trị event.origin là "null"

Một số tài liệu có opaque origin, chẳng hạn:

- data: URL.
- Một số sandboxed iframe không cấp allow-same-origin.
- Các context có origin bị tạo thành opaque theo quy tắc của platform.

Message từ những context này có thể có:

```js
event.origin === "null"
```

"null" không phải một origin duy nhất. Nhiều opaque origin khác nhau có thể được serialize thành cùng chuỗi này. Vì vậy:

```js
// KHÔNG an toàn: chấp nhận mọi opaque origin
if (event.origin === "null") {
  handleMessage(event.data);
}
```

không xác minh được danh tính sender. Nếu ứng dụng bắt buộc giao tiếp với opaque-origin frame, cần thiết kế trust bằng một cơ chế khác:

1. Giữ tham chiếu chính xác tới iframe đã tạo và kiểm tra event.source.
2. Dùng handshake một lần với nonce ngẫu nhiên đủ mạnh, gắn với phiên/iframe cụ thể.
3. Chuyển một MessagePort riêng sau handshake và chỉ dùng port đó cho protocol đã định nghĩa.
4. Không gửi dữ liệu có giá trị nếu không thể xác thực context đủ mạnh.

Nonce handshake không biến chuỗi "null" thành origin đáng tin cậy. Nó chỉ có giá trị khi nonce được sinh, phân phối và gắn với browsing context theo cách không thể bị context khác đoán hoặc tái sử dụng.

## 7. Dùng MessageChannel cho kênh trao đổi riêng

MessageChannel tạo hai đầu MessagePort. Một port có thể được chuyển cho iframe qua postMessage() dưới dạng transferable, sau đó hai bên trao đổi trên port riêng:

```js
const frame = document.querySelector("#widget-frame");
const widgetOrigin = "https://widget.partner.test";
const channel = new MessageChannel();

channel.port1.onmessage = (event) => {
  const message = validateWidgetMessage(event.data);
  if (!message) return;
  handleWidgetMessage(message);
};

frame.contentWindow.postMessage(
  { type: "host:connect", version: 1 },
  widgetOrigin,
  [channel.port2]
);
```

Phía widget nhận port:

```js
window.addEventListener("message", function onConnect(event) {
  if (event.origin !== "https://shop.example.test") return;
  if (event.source !== window.parent) return;
  if (event.data?.type !== "host:connect") return;
  if (event.data?.version !== 1) return;
  if (event.ports.length !== 1) return;

  window.removeEventListener("message", onConnect);

  const port = event.ports[0];
  port.onmessage = (portEvent) => {
    const message = validateHostMessage(portEvent.data);
    if (!message) return;
    handleHostMessage(message);
  };
  port.start();
});
```

MessageChannel giảm việc lắng nghe message toàn cục sau khi kết nối và tạo một kênh riêng cho hai bên. Tuy nhiên, **port không tự xác thực sender**. Việc chuyển port phải chỉ xảy ra sau khi kiểm tra origin, source và handshake; dữ liệu qua port vẫn phải validate schema, trạng thái và quyền.

Đóng port khi không còn dùng:

```js
channel.port1.close();
```

## 8. Kiểm tra message trước khi tác động DOM

Một message có origin hợp lệ vẫn có thể chứa nội dung do người dùng kiểm soát. Không đưa dữ liệu đó thẳng vào HTML:

```js
// KHÔNG an toàn: message có thể chứa markup/script injection
window.addEventListener("message", (event) => {
  if (event.origin !== "https://widget.partner.test") return;
  document.querySelector("#result").innerHTML = event.data.html;
});
```

Nếu chỉ hiển thị text, dùng textContent:

```js
window.addEventListener("message", (event) => {
  if (event.origin !== "https://widget.partner.test") return;
  if (event.source !== widgetFrame.contentWindow) return;

  const message = validateWidgetMessage(event.data);
  if (!message) return;

  document.querySelector("#result").textContent = message.label;
});
```

Nếu sản phẩm thật sự cần nhận rich HTML, phải có schema và sanitizer phù hợp, cân nhắc Trusted Types và CSP. Origin allowlist không làm HTML từ sender trở thành an toàn.

### Không thực thi message như code

Không dùng:

```js
eval(event.data);
new Function(event.data)();
setTimeout(event.data, 0);
```

Message là dữ liệu. Hãy định nghĩa message type và ánh xạ mỗi type tới một hàm có sẵn:

```js
const handlers = {
  "widget:resize": handleResize,
  "widget:ready": handleReady,
  "widget:close": handleClose
};

function dispatchMessage(message) {
  const handler = handlers[message.type];
  if (!handler) return;
  handler(message);
}
```

Không dùng key do message cung cấp để truy cập tùy ý method trên object có quyền cao hoặc gọi API quản trị.

## 9. postMessage không thay xác thực, phân quyền hoặc CSRF

Kiểm tra event.origin trả lời câu hỏi **message đến từ origin nào**. Nó không trả lời:

- Người dùng hiện tại là ai?
- Người dùng có quyền thực hiện hành động này không?
- Đơn hàng hoặc tài nguyên có thuộc người dùng đó không?
- Giao dịch đã được backend xác nhận chưa?

Nếu widget gửi message payment:success, host không nên chỉ tin message đó rồi đánh dấu đơn hàng đã thanh toán. Backend phải xác minh trạng thái thanh toán qua webhook/API đã xác thực với nhà cung cấp.

### Confused deputy

Một trang host có thể có quyền cao hơn widget. Nếu host nhận message rồi thực hiện hành động thay widget, host có thể trở thành confused deputy:

```js
// Nguy hiểm: message tùy ý quyết định URL fetch với quyền của host
window.addEventListener("message", (event) => {
  if (event.origin !== widgetOrigin) return;
  fetch(event.data.url, { credentials: "include" });
});
```

Kẻ gửi có thể khiến host gửi request tới endpoint nội bộ hoặc endpoint nhạy cảm. Hãy thiết kế command allowlist:

```js
const allowedCommands = new Set([
  "profile:request-summary",
  "checkout:request-status"
]);

function handleWidgetCommand(message) {
  if (!allowedCommands.has(message.type)) return;

  switch (message.type) {
    case "profile:request-summary":
      return sendLimitedProfileSummary();
    case "checkout:request-status":
      return sendCurrentCheckoutStatus();
  }
}
```

Backend vẫn phải xác thực và phân quyền. Không biến host thành proxy tùy ý chỉ vì message đến từ một origin đã allowlist.

### Message không phải CSRF token

postMessage có thể phối hợp với luồng CSRF, nhưng bản thân message không chứng minh request backend là hợp lệ. Nếu thao tác tiếp theo dùng cookie session, backend vẫn cần CSRF defense phù hợp như token, Origin/Referer validation và kiểm tra quyền.

## 10. Protocol message nên có version và trạng thái

Một protocol ổn định cần xác định:

| Thành phần | Câu hỏi cần trả lời |
| --- | --- |
| type | Message đang yêu cầu hoặc thông báo điều gì? |
| version | Hai bên có hiểu cùng protocol không? |
| requestId | Message thuộc request nào? |
| payload | Dữ liệu nào được phép gửi? |
| State | Message có hợp lệ ở giai đoạn hiện tại không? |
| Timeout | Khi nào request hết hiệu lực? |
| Replay handling | Message lặp được xử lý ra sao? |

Ví dụ luồng:

```text
Host                         Widget
  |                              |
  |---- host:init, version 1 --->|
  |                              |
  |<--- widget:ready, version 1 -|
  |                              |
  |---- host:request, id 42 ---->|
  |                              |
  |<--- widget:response, id 42 --|
  |                              |
```

Host chỉ chấp nhận response có requestId đang chờ, đúng type/version và chưa hết timeout. Khi iframe reload hoặc điều hướng, hủy request cũ và thực hiện handshake mới.

### Giới hạn kích thước và tần suất

Không có một ngưỡng kích thước phù hợp cho mọi ứng dụng. Protocol nên giới hạn:

- Độ dài string.
- Số field và phần tử array.
- Độ sâu object.
- Tần suất message.
- Số request đang chờ.
- Thời gian xử lý tối đa.

Nếu nhận payload lớn, cân nhắc truyền dữ liệu qua API có xác thực hoặc transferable như ArrayBuffer khi phù hợp, thay vì message object khổng lồ. Structured clone không phải bộ lọc schema và không bảo đảm dữ liệu nghiệp vụ hợp lệ.

## 11. Ví dụ tích hợp: host và payment iframe

### Host page

```html
<iframe
  id="payment-frame"
  title="Payment"
  src="https://payments.partner.test/checkout">
</iframe>
<p id="payment-status" aria-live="polite"></p>
```

```js
const paymentFrame = document.getElementById("payment-frame");
const paymentOrigin = "https://payments.partner.test";
const statusNode = document.getElementById("payment-status");

function validatePaymentMessage(data) {
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    return null;
  }

  if (data.type !== "checkout:status") return null;
  if (data.version !== 1) return null;
  if (typeof data.orderId !== "string" || data.orderId.length > 64) {
    return null;
  }
  if (!["pending", "failed", "completed"].includes(data.status)) {
    return null;
  }

  return {
    orderId: data.orderId,
    status: data.status
  };
}

window.addEventListener("message", (event) => {
  if (event.origin !== paymentOrigin) return;
  if (event.source !== paymentFrame.contentWindow) return;

  const message = validatePaymentMessage(event.data);
  if (!message) return;

  if (message.orderId !== currentOrderId) return;

  // Chỉ hiển thị trạng thái; backend vẫn là nguồn xác nhận thanh toán.
  statusNode.textContent = "Trạng thái: " + message.status;
  refreshOrderStatusFromServer();
});
```

### Payment iframe

```js
const hostOrigin = "https://shop.example.test";

function reportStatus(orderId, status) {
  window.parent.postMessage(
    {
      type: "checkout:status",
      version: 1,
      orderId,
      status
    },
    hostOrigin
  );
}
```

Hai phía cần thống nhất origin thực tế, schema và lifecycle. Nếu host có nhiều môi trường, cấu hình origin theo deployment; không suy ra host origin từ dữ liệu message.

## 12. Kiểm thử bằng Chrome DevTools

Thực hiện trong ứng dụng local hoặc staging với hai origin do bạn kiểm soát. Dùng port khác nhau để tạo cross-origin trên localhost.

### Bước 1 — Quan sát message event

1. Mở host page và iframe trong browser.
2. DevTools → Console.
3. Thêm listener message ở host và log tạm event.origin, event.source, event.data.
4. Kích hoạt thao tác trong iframe để gửi message.
5. Xác nhận origin là origin của iframe và source bằng iframe.contentWindow.

Chỉ log payload giả lập, không log token, session hoặc thông tin thanh toán nhạy cảm.

### Bước 2 — Thử sai origin

1. Tạo một trang test ở origin khác.
2. Gửi message tới host với cùng type nhưng từ trang test.
3. Xác nhận host từ chối do event.origin không nằm trong allowlist.

### Bước 3 — Thử sai source

1. Mở thêm một iframe khác nhưng cùng origin với iframe tin cậy.
2. Gửi message từ iframe thứ hai.
3. Xác nhận kiểm tra event.source từ chối message vì không phải browsing context đã đăng ký.

### Bước 4 — Thử payload không hợp lệ

Thử lần lượt:

```js
[
  null,
  "checkout:complete",
  { type: "unknown", version: 1 },
  { type: "checkout:status", version: 99 },
  { type: "checkout:status", version: 1, orderId: 123, status: "paid" },
  { type: "checkout:status", version: 1, orderId: "x", status: "admin" }
]
```

Xác nhận validator từ chối từng payload sai kiểu, sai version, type hoặc enum.

### Bước 5 — Kiểm tra targetOrigin

1. Gửi message với targetOrigin chính xác.
2. Điều hướng iframe sang origin khác trong môi trường lab.
3. Gửi lại message; xác nhận browser không giao message cho tài liệu có origin không khớp targetOrigin.
4. Không dùng token thật để thử wildcard.

### Ma trận kiểm thử

| Ca kiểm thử | Điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| Sender hợp lệ | Origin đúng, source đúng, schema hợp lệ | Xử lý theo protocol |
| Origin sai | Host khác hoặc scheme/port khác | Bỏ qua |
| Source sai | Cùng origin nhưng iframe/popup khác | Bỏ qua |
| Origin null | Opaque origin không nằm trong protocol tin cậy | Từ chối mặc định |
| Type không cho phép | type không trong allowlist | Bỏ qua hoặc trả lỗi protocol |
| Version không hỗ trợ | Version khác | Từ chối có kiểm soát |
| Payload sai schema | Thiếu field hoặc sai kiểu | Không gọi nghiệp vụ |
| Message lặp | requestId đã xử lý | Không thực hiện lại side effect |
| Frame đã điều hướng | Origin mới không khớp | Message không được browser giao hoặc listener từ chối |
| Payload có HTML | String chứa markup | Không gán vào innerHTML; dùng textContent hoặc sanitizer |
| targetOrigin sai | Không khớp origin đích | Message không được giao |

## 13. Sai lầm thường gặp

| Sai lầm | Rủi ro | Cách sửa |
| --- | --- | --- |
| Chỉ kiểm tra event.data.type | Sender bất kỳ có thể giả message type | Kiểm tra origin và source trước |
| Chỉ kiểm tra event.origin | Một cửa sổ khác cùng origin có thể gửi message | Ràng buộc event.source với iframe/popup đã đăng ký |
| Dùng substring cho origin | Chấp nhận domain giả | Exact origin allowlist |
| Gửi token với targetOrigin * | Token có thể tới trang khác sau navigation | Dùng exact targetOrigin; giảm dữ liệu bí mật |
| Chấp nhận event.origin là null | Không xác định được opaque sender | Từ chối mặc định hoặc protocol riêng |
| Tin payload vì sender cùng origin | Sender có thể bị XSS hoặc bug | Validate schema, state và quyền |
| Gán message vào innerHTML | DOM XSS | textContent, DOM API hoặc sanitizer/TrustedHTML |
| Gọi eval trên message | Code injection | Message type allowlist và handler tĩnh |
| Dùng message để xác nhận thanh toán | Client có thể giả thông báo hoặc replay | Xác minh backend/provider |
| Cho message chọn URL fetch tùy ý | Confused deputy và request ngoài ý muốn | Command allowlist và endpoint cố định |
| Không kiểm tra requestId/state | Replay hoặc response cũ | Correlation ID, timeout và state machine |
| Tin MessagePort tự xác thực | Port chỉ là kênh, không phải danh tính | Xác minh handshake trước khi chuyển port |

## 14. Câu hỏi củng cố

**Câu 1.** Vì sao cần kiểm tra cả event.origin và event.source?

**Giải đáp:** Origin xác định nguồn theo scheme/host/port; source xác định đúng browsing context đã được ứng dụng mở hoặc nhúng. Kết hợp hai điều kiện tránh nhận message từ cửa sổ khác cùng origin.

**Câu 2.** event.origin có luôn là origin hiện tại của cửa sổ sender khi event được xử lý không?

**Giải đáp:** Không. Nó là origin của sender tại thời điểm gọi postMessage. Sender có thể đã điều hướng trước khi message được giao.

**Câu 3.** Có nên dùng targetOrigin * để gửi access token cho popup không?

**Giải đáp:** Không. Popup có thể điều hướng sang origin khác trước khi message được giao. Dùng exact targetOrigin và thiết kế để không phải gửi credential dài hạn.

**Câu 4.** event.origin là null có xác minh được sender không?

**Giải đáp:** Không. Nhiều opaque origin khác nhau có thể cùng serialize thành null. Từ chối mặc định hoặc thiết kế protocol riêng có ràng buộc context và capability.

**Câu 5.** MessageChannel có thay kiểm tra origin và schema không?

**Giải đáp:** Không. Cần xác minh origin/source trước khi chuyển port; message qua port vẫn cần schema, state và authorization checks.

**Câu 6.** Widget gửi payment:success; host có thể đánh dấu đơn đã thanh toán ngay không?

**Giải đáp:** Không. Message chỉ là tín hiệu UI. Backend phải xác minh trạng thái giao dịch với payment provider qua kênh xác thực.

## 15. Tổng kết

postMessage cho phép các browsing context trao đổi dữ liệu qua ranh giới origin, nhưng mọi message nhận được đều là input không tin cậy. Hãy xác minh **exact event.origin**, **event.source** của iframe/popup đã đăng ký, rồi kiểm tra type, version, schema, giới hạn dữ liệu và trạng thái protocol trước khi thực hiện hành động.

Ở chiều gửi, dùng targetOrigin chính xác và không gửi bí mật với wildcard. Opaque origin có thể xuất hiện dưới giá trị null; không coi nó là danh tính. MessageChannel tạo kênh riêng nhưng không tự xác thực peer. Cuối cùng, không biến message thành HTML hoặc code, không dùng nó thay authentication/authorization/CSRF, và luôn để backend xác nhận các hành động nhạy cảm như thanh toán.

## Tài liệu tham khảo

1. [WHATWG — HTML Standard: Web messaging](https://html.spec.whatwg.org/multipage/web-messaging.html): thuật toán postMessage, MessageEvent và MessageChannel.
2. [MDN — Window.postMessage()](https://developer.mozilla.org/en-US/docs/Web/API/Window/postMessage): gửi message giữa browsing context và targetOrigin.
3. [MDN — MessageEvent](https://developer.mozilla.org/en-US/docs/Web/API/MessageEvent): event.origin, event.source, data và ports.
4. [MDN — MessageChannel](https://developer.mozilla.org/en-US/docs/Web/API/MessageChannel): tạo cặp MessagePort để giao tiếp.
5. [OWASP — HTML5 Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html): kiểm tra origin và dữ liệu khi dùng postMessage.
6. [OWASP — DOM based XSS Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/DOM_based_XSS_Prevention_Cheat_Sheet.html): xử lý dữ liệu không tin cậy ở DOM sink.
