# MessageEvent origin: xác minh nguồn gửi thông điệp cross-origin

## 1. Vì sao cần kiểm tra MessageEvent.origin?

Các trang web thường phải trao đổi dữ liệu giữa những browsing context khác nhau: trang chính với iframe thanh toán, cửa sổ đăng nhập bật bằng `window.open()`, widget của đối tác hoặc các frame trong một ứng dụng nhiều origin. Trình duyệt cung cấp `window.postMessage()` để những context này gửi thông điệp cho nhau mà không cần nới lỏng Same-Origin Policy.

Khi nhận thông điệp, listener nhận một đối tượng `MessageEvent`. Thuộc tính **`event.origin`** cho biết origin của context gửi tại thời điểm thông điệp được gửi. Ứng dụng dùng thông tin này để quyết định có tin nguồn gửi hay không.

Nếu nhận mọi thông điệp mà không kiểm tra origin, một trang không đáng tin có thể gửi dữ liệu giả, kích hoạt thao tác hoặc làm thay đổi trạng thái giao diện. Ví dụ, attacker có thể mở một cửa sổ tới ứng dụng rồi gửi message giả với nội dung “đã thanh toán”, hoặc nhúng trang ứng dụng vào iframe và cố gửi lệnh tới trang cha.

`event.origin` là tín hiệu quan trọng, nhưng không phải bằng chứng duy nhất. Ứng dụng thường cần kiểm tra cả `event.source`, xác thực cấu trúc `event.data`, kiểm tra trạng thái phiên giao tiếp và phân quyền hành động ở server.

Trong module bảo mật trình duyệt, `MessageEvent.origin` gắn trực tiếp với origin, SOP, iframe, popup, clickjacking, XSS và các ranh giới giữa ứng dụng với widget bên ngoài. Bài học này tập trung vào việc xác minh đúng nguồn trước khi xử lý dữ liệu nhận được.

Sau bài học, bạn có thể:

- Giải thích `event.origin`, `event.source`, `event.data` và `event.ports`.
- Kiểm tra origin theo scheme, host và port một cách chính xác.
- Kết hợp kiểm tra origin với định danh cửa sổ/iframe mong đợi.
- Xử lý origin opaque có giá trị chuỗi `"null"`.
- Xác minh schema và loại message trước khi thực hiện hành động.
- Dùng `targetOrigin` chính xác khi gửi và thiết kế kênh `MessageChannel` an toàn.
- Kiểm thử message giả mạo và navigation trong DevTools.

## 2. postMessage và MessageEvent hoạt động thế nào?

Một cửa sổ có thể gửi thông điệp tới cửa sổ khác bằng `postMessage()`:

```javascript
// Trang gửi
const targetWindow = window.opener;

targetWindow.postMessage(
  { type: "HELLO", version: 1 },
  "https://app.example.com"
);
```

Trang nhận đăng ký listener:

```javascript
window.addEventListener("message", event => {
  console.log(event.origin);
  console.log(event.source);
  console.log(event.data);
});
```

Khi message đến, browser tạo một `MessageEvent`. Với `window.postMessage()`, những thuộc tính quan trọng gồm:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `origin` | Origin của context gửi tại thời điểm gọi `postMessage()`, được serialize thành chuỗi. |
| `source` | Tham chiếu tới context gửi, thường là `WindowProxy` với window messaging. |
| `data` | Dữ liệu được gửi, chuyển qua structured clone algorithm. |
| `ports` | Danh sách `MessagePort` được chuyển kèm message, nếu có. |
| `lastEventId` | ID của message trong một số loại message event như Server-Sent Events; thường không phải dữ liệu cần dùng cho window `postMessage()`. |

Không nhầm `event.origin` với URL của trang nhận. `event.origin` mô tả bên gửi, còn `location.origin` mô tả origin của trang hiện tại.

## 3. Origin gồm những thành phần nào?

Origin được xác định bởi ba thành phần:

- Scheme: ví dụ `https` hoặc `http`.
- Host: tên miền hoặc địa chỉ host.
- Port: cổng hiệu lực của kết nối.

Ví dụ:

| Origin | Có giống `https://app.example.com` không? | Lý do |
| --- | --- | --- |
| `https://app.example.com` | Có | Cùng scheme, host và port hiệu lực. |
| `http://app.example.com` | Không | Scheme khác. |
| `https://api.example.com` | Không | Host khác. |
| `https://app.example.com:8443` | Không | Port khác. |
| `https://app.example.com.attacker.test` | Không | Host thực tế khác. |

Port mặc định thường được chuẩn hóa khi serialize origin: HTTPS dùng port 443 và HTTP dùng port 80. Vì vậy, giá trị `event.origin` thường không có phần `:443` hoặc `:80` khi đó là port mặc định.

Hãy so sánh với origin chuẩn đã cấu hình:

```javascript
const TRUSTED_ORIGIN = "https://app.example.com";

window.addEventListener("message", event => {
  if (event.origin !== TRUSTED_ORIGIN) {
    return;
  }

  // Chỉ xử lý tiếp sau khi origin khớp chính xác.
});
```

So sánh chuỗi chính xác tránh những lỗi như `includes("example.com")` hoặc `endsWith("example.com")`, vốn có thể chấp nhận hostname giả mạo như `app.example.com.attacker.test` hoặc `notexample.com`.

### 3.1 Origin khác site

Origin và site là hai khái niệm khác nhau. `https://portal.example.com` và `https://app.example.com` khác origin vì hostname khác, dù có thể cùng site. `event.origin` cần được so sánh theo origin đầy đủ; không dùng khái niệm same-site để thay allowlist origin.

### 3.2 Không tự dựng origin bằng phép nối chuỗi

Không lấy riêng hostname từ dữ liệu message rồi tự ghép thành origin được tin cậy. Hãy so sánh `event.origin` với allowlist origin cố định. Nếu cần xây dựng allowlist động từ cấu hình, parse URL ở bước cấu hình, kiểm tra scheme/host/port rồi lưu lại dạng origin chuẩn.

## 4. Kiểm tra origin trước khi đọc và xử lý data

Ví dụ một iframe widget được phép gửi thông điệp tới trang cha:

```javascript
const WIDGET_ORIGIN = "https://widget.example";
const widgetFrame = document.querySelector("#payment-widget");

window.addEventListener("message", event => {
  if (event.origin !== WIDGET_ORIGIN) {
    return;
  }

  if (event.source !== widgetFrame.contentWindow) {
    return;
  }

  // Tiếp tục xác minh event.data trước khi xử lý.
});
```

Hai điều kiện có vai trò khác nhau:

1. `event.origin` xác minh origin của document gửi message.
2. `event.source` xác minh message đến từ đúng browsing context mà ứng dụng mong đợi.

Chỉ kiểm tra origin có thể chưa đủ nếu nhiều cửa sổ cùng origin được phép gửi message. Chỉ kiểm tra source cũng chưa đủ vì cùng một `WindowProxy` có thể điều hướng sang document khác origin.

### 4.1 Vì sao event.source quan trọng?

Giả sử ứng dụng có hai iframe cùng tải nội dung từ `https://widget.example`. Cả hai đều có origin hợp lệ, nhưng chỉ một iframe được phép điều khiển luồng thanh toán hiện tại. Kiểm tra `event.origin` xác nhận cả hai đến từ host tin cậy; kiểm tra `event.source === expectedFrame.contentWindow` giới hạn message vào đúng iframe.

`event.source` với window messaging thường là `WindowProxy`, đại diện cho browsing context. Tham chiếu này có thể tồn tại qua navigation của cửa sổ. Do đó, luôn kết hợp source identity với kiểm tra origin tại mỗi message.

### 4.2 Kiểm tra cả hai trước side effect

Không cập nhật trạng thái thanh toán, quyền người dùng, phiên đăng nhập hoặc dữ liệu nhạy cảm trước khi hoàn tất kiểm tra nguồn và dữ liệu. Một listener nên đi theo thứ tự:

1. Kiểm tra origin chính xác.
2. Kiểm tra source context mong đợi.
3. Kiểm tra kiểu và schema của `event.data`.
4. Kiểm tra trạng thái giao thức hiện tại, ví dụ nonce hoặc request ID.
5. Kiểm tra quyền nghiệp vụ phía server nếu hành động có tác động tới dữ liệu.
6. Chỉ sau đó mới cập nhật giao diện hoặc thực hiện hành động.

`postMessage` không phải cơ chế chống CSRF. Nếu thao tác phía server dùng cookie authentication, endpoint thay đổi trạng thái vẫn cần CSRF token hoặc biện pháp chống CSRF phù hợp, cùng authorization. Việc message đến từ origin được phép chỉ xác minh nguồn của thông điệp trong giao thức browser; nó không tự chứng minh người dùng đã đồng ý với hành động nghiệp vụ.

## 5. Origin opaque và giá trị "null"

Không phải mọi document đều có origin dạng scheme/host/port thông thường. Một số context có **opaque origin**, ví dụ tài liệu `data:` hoặc iframe sandbox không có quyền `allow-same-origin`.

Trong một số trường hợp đó, `event.origin` được serialize thành chuỗi:

```text
null
```

Đây là chuỗi `"null"`, không phải JavaScript `null`. Nó không xác định một website cụ thể và nhiều document opaque origin khác nhau có thể có cùng biểu diễn `"null"`.

Không viết logic:

```javascript
// Sai: chấp nhận mọi message có opaque origin.
if (event.origin === "null") {
  processMessage(event.data);
}
```

Điều kiện này không xác minh được bên gửi cụ thể. Nếu ứng dụng nhận message từ một iframe opaque-origin vì yêu cầu sandbox, cần một thiết kế capability riêng, chỉ cấp dữ liệu tối thiểu và không gửi bí mật chỉ dựa trên chuỗi `"null"`.

### 5.1 Sandbox iframe

Ví dụ:

```html
<iframe
  src="https://untrusted.example/content"
  sandbox="allow-scripts">
</iframe>
```

Không có `allow-same-origin`, nội dung iframe được đặt trong opaque origin. Message từ frame này có thể có `event.origin === "null"`. Thêm `allow-same-origin` sẽ thay đổi mô hình origin của nội dung được nhúng; không thêm cờ này chỉ để làm kiểm tra origin đơn giản hơn.

Nếu buộc phải giao tiếp với frame opaque-origin, hãy:

- Xác định frame bằng `event.source` nếu có thể.
- Dùng handshake có nonce ngẫu nhiên, một lần và thời hạn ngắn.
- Không gửi token đăng nhập, cookie hoặc dữ liệu bí mật qua `targetOrigin: "*"`.
- Chỉ cấp một `MessagePort` với tập hành động hẹp sau khi xác minh bước khởi tạo.
- Xem mọi dữ liệu từ frame là input không tin cậy và kiểm tra schema.

Opaque origin không nên được xem như một origin allowlist chung.

## 6. targetOrigin khi gửi message

`postMessage()` có tham số `targetOrigin` để giới hạn document đích được nhận message:

```javascript
otherWindow.postMessage(
  { type: "ACCOUNT_READY", version: 1 },
  "https://portal.example.com"
);
```

Browser chỉ chuyển message nếu origin của document đích khớp `targetOrigin` tại thời điểm giao message. Nếu cửa sổ đích đã điều hướng sang origin khác, message sẽ không được gửi tới document mới.

Không dùng wildcard khi gửi dữ liệu nhạy cảm:

```javascript
// Rủi ro: message có thể được nhận bởi document khác origin
// nếu browsing context điều hướng trước khi message được giao.
otherWindow.postMessage(
  { type: "SESSION_TOKEN", token: secretToken },
  "*"
);
```

Ưu tiên origin chính xác:

```javascript
otherWindow.postMessage(
  { type: "WIDGET_INIT", requestId: "req-123" },
  "https://widget.example"
);
```

`targetOrigin` bảo vệ phía gửi khỏi việc gửi nhầm dữ liệu tới document đã điều hướng sang origin khác. `event.origin` bảo vệ phía nhận khỏi việc xử lý message đến từ origin không được tin. Hai kiểm tra bổ sung cho nhau.

### 6.1 Khi nào cần wildcard?

`targetOrigin: "*"` đôi khi được dùng khi đích có opaque origin vì origin đó không thể được chỉ định bằng một origin tuple thông thường. Đây là trường hợp cần thiết kế riêng: không gửi bí mật, xác minh source context, dùng handshake capability và chỉ gửi dữ liệu tối thiểu. Đừng dùng wildcard chỉ vì chưa biết origin của cửa sổ đích.

## 7. Kiểm tra schema của event.data

Ngay cả khi origin và source hợp lệ, dữ liệu message vẫn có thể sai định dạng hoặc chứa giá trị ngoài dự kiến. Origin xác minh nơi gửi, không xác minh ý nghĩa hoặc tính hợp lệ của payload.

Ví dụ message được ứng dụng mong đợi:

```javascript
{
  type: "PAYMENT_STATUS",
  version: 1,
  requestId: "req-123",
  status: "completed"
}
```

Có thể kiểm tra rõ ràng:

```javascript
function isPaymentStatusMessage(data) {
  if (data === null || typeof data !== "object" || Array.isArray(data)) {
    return false;
  }

  return data.type === "PAYMENT_STATUS"
    && data.version === 1
    && typeof data.requestId === "string"
    && data.requestId.length > 0
    && data.requestId.length <= 100
    && (data.status === "completed" || data.status === "failed");
}
```

Listener:

```javascript
const WIDGET_ORIGIN = "https://widget.example";
const widgetFrame = document.querySelector("#payment-widget");

window.addEventListener("message", event => {
  if (event.origin !== WIDGET_ORIGIN) return;
  if (event.source !== widgetFrame.contentWindow) return;
  if (!isPaymentStatusMessage(event.data)) return;

  updatePaymentStatus(event.data.status);
});
```

Đây là ví dụ kiểm tra schema ở client. Với thanh toán thực tế, không được coi message `"completed"` là bằng chứng cuối cùng rằng giao dịch đã thanh toán. Server phải xác minh trạng thái giao dịch từ nguồn có thẩm quyền; message chỉ nên dùng để đồng bộ giao diện.

### 7.1 Chỉ nhận message type đã định nghĩa

Tránh nhận mọi object rồi gọi một hàm hoặc property tùy ý:

```javascript
// Không an toàn: message điều khiển tên hành động tùy ý.
window.addEventListener("message", event => {
  handlers[event.data.action](event.data.payload);
});
```

Dùng allowlist loại message và dispatch tường minh:

```javascript
const handlers = {
  "WIDGET_READY": handleWidgetReady,
  "PAYMENT_STATUS": handlePaymentStatus
};

window.addEventListener("message", event => {
  if (event.origin !== "https://widget.example") return;
  if (event.source !== widgetFrame.contentWindow) return;

  const data = event.data;
  if (!data || typeof data !== "object" || Array.isArray(data)) return;
  if (typeof data.type !== "string") return;

  const handler = handlers[data.type];
  if (!handler) return;
  if (!isValidMessage(data)) return;

  handler(data);
});
```

Trong triển khai thực tế, `isValidMessage()` cần xác thực schema riêng cho từng `type`, giới hạn kích thước chuỗi/mảng và từ chối field không cần thiết nếu giao thức yêu cầu schema chặt.

### 7.2 Structured clone không phải kiểm tra bảo mật

`postMessage()` truyền dữ liệu qua structured clone algorithm. Nó hỗ trợ nhiều kiểu dữ liệu như `object`, `array`, `Date`, `Map`, `Set`, `ArrayBuffer` và một số kiểu có cấu trúc khác. Hàm, DOM node và một số object đặc biệt không thể clone theo cách thông thường.

Structured clone giúp chuyển dữ liệu giữa context mà không chia sẻ trực tiếp object reference thông thường, nhưng không đảm bảo dữ liệu đúng nghiệp vụ. Hãy kiểm tra type, range, length, enum và trạng thái giao thức như với bất kỳ input nào.

## 8. Ví dụ hoàn chỉnh: trang cha và iframe widget

Giả sử:

- Trang cha: `https://shop.example.com`.
- Widget: `https://widget.example.net`.
- Trang cha chỉ chấp nhận message từ iframe widget đã tạo.

HTML:

```html
<iframe
  id="payment-widget"
  src="https://widget.example.net/checkout"
  title="Payment widget">
</iframe>
```

JavaScript phía trang cha:

```javascript
const WIDGET_ORIGIN = "https://widget.example.net";
const frame = document.querySelector("#payment-widget");

function isReadyMessage(data) {
  return data !== null
    && typeof data === "object"
    && !Array.isArray(data)
    && data.type === "WIDGET_READY"
    && data.version === 1;
}

function isStatusMessage(data) {
  return data !== null
    && typeof data === "object"
    && !Array.isArray(data)
    && data.type === "PAYMENT_STATUS"
    && data.version === 1
    && typeof data.requestId === "string"
    && data.requestId.length <= 100
    && ["completed", "failed"].includes(data.status);
}

window.addEventListener("message", event => {
  if (event.origin !== WIDGET_ORIGIN) return;
  if (event.source !== frame.contentWindow) return;

  if (isReadyMessage(event.data)) {
    frame.contentWindow.postMessage(
      { type: "PARENT_INIT", version: 1 },
      WIDGET_ORIGIN
    );
    return;
  }

  if (isStatusMessage(event.data)) {
    // Chỉ cập nhật trạng thái hiển thị.
    // Server vẫn là nguồn xác nhận giao dịch cuối cùng.
    showPaymentStatus(event.data.status);
  }
});
```

Phía widget:

```javascript
const PARENT_ORIGIN = "https://shop.example.com";

window.parent.postMessage(
  { type: "WIDGET_READY", version: 1 },
  PARENT_ORIGIN
);

window.addEventListener("message", event => {
  if (event.origin !== PARENT_ORIGIN) return;
  if (event.source !== window.parent) return;

  if (
    event.data
    && event.data.type === "PARENT_INIT"
    && event.data.version === 1
  ) {
    initializeWidget();
  }
});
```

Ví dụ này kiểm tra origin và source ở cả hai phía, đồng thời dùng `targetOrigin` cụ thể. Trong sản phẩm thật, cần bổ sung request ID/nonce để ghép message với đúng phiên checkout và xác minh giao dịch ở backend.

## 9. Navigation và thời điểm event.origin được xác định

Một chi tiết quan trọng: `event.origin` phản ánh origin của bên gửi **tại thời điểm gọi `postMessage()`**. Nó không phải lời cam kết rằng cửa sổ gửi vẫn đang ở origin đó khi message được xử lý.

Ví dụ:

1. Một cửa sổ ở `https://trusted.example` gọi `postMessage()`.
2. Ngay sau đó, cửa sổ đó điều hướng sang một trang khác.
3. Message đã được gửi có thể vẫn tới nơi nhận; `event.origin` mô tả origin tại thời điểm gửi.

Vì `event.source` là tham chiếu browsing context, không phải snapshot bất biến của document, hãy kiểm tra origin trên từng message. Nếu ứng dụng cần ràng buộc message với một phiên cụ thể, dùng nonce hoặc request ID khó đoán, có thời hạn và chỉ dùng một lần.

### 9.1 Không tin message chỉ vì popup ban đầu là trusted

`window.open()` trả về một tham chiếu tới browsing context. Popup có thể điều hướng sau khi được mở. Do đó, không chỉ kiểm tra rằng message đến từ `window.opener` hoặc popup đã lưu; vẫn phải kiểm tra `event.origin` chính xác và schema.

Tương tự, iframe `contentWindow` có thể giữ identity qua navigation. `event.source === iframe.contentWindow` là điều kiện hữu ích nhưng cần kết hợp origin.

## 10. MessageChannel và chuyển quyền giao tiếp

Với giao tiếp hai chiều có nhiều message, có thể tạo `MessageChannel` rồi chuyển một `MessagePort` sang frame đã xác minh. Port tạo ra một kênh riêng, giúp không phải để mọi module nghe chung `window` message event.

Ví dụ phía trang cha:

```javascript
const WIDGET_ORIGIN = "https://widget.example.net";
const frame = document.querySelector("#payment-widget");
const channel = new MessageChannel();

channel.port1.addEventListener("message", event => {
  const data = event.data;
  if (!isWidgetEvent(data)) return;
  handleWidgetEvent(data);
});

channel.port1.start();

frame.addEventListener("load", () => {
  frame.contentWindow.postMessage(
    { type: "CONNECT", version: 1 },
    WIDGET_ORIGIN,
    [channel.port2]
  );
});
```

Phía widget nhận port được chuyển:

```javascript
window.addEventListener("message", event => {
  if (event.origin !== "https://shop.example.com") return;
  if (event.source !== window.parent) return;
  if (!isConnectMessage(event.data)) return;

  const port = event.ports[0];
  if (!port) return;

  port.addEventListener("message", handleParentCommand);
  port.start();
  port.postMessage({ type: "CONNECTED", version: 1 });
});
```

Đây là phác thảo giao thức; cần xử lý việc iframe tải lại và cấp port mới, đóng port cũ, timeout handshake, xác thực schema và tránh cấp nhiều kênh ngoài ý muốn. `MessagePort` là capability: ai giữ port có thể gửi message qua kênh đó. Chỉ chuyển port sau khi đã xác minh origin, source và handshake.

`MessageChannel` không tự xác thực bên gửi và cũng không thay schema validation. Sau khi port đã được cấp, mọi message trên port vẫn là input cần kiểm tra.

## 11. Những lỗi bảo mật thường gặp

| Lỗi | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| Không kiểm tra `event.origin` | Trang không tin cậy có thể gửi message giả. | So sánh origin chính xác với allowlist. |
| Chỉ kiểm tra hostname bằng `includes()` | Có thể chấp nhận hostname giả mạo hoặc scheme/port không mong muốn. | So sánh origin đầy đủ. |
| Chấp nhận `"null"` như origin tin cậy | Nhiều opaque origin khác nhau cùng serialize thành chuỗi này. | Thiết kế capability riêng, kiểm tra source và giới hạn dữ liệu. |
| Chỉ kiểm tra origin | Nhiều cửa sổ cùng origin có thể gửi message. | Kiểm tra thêm `event.source`. |
| Chỉ kiểm tra source | Browsing context có thể điều hướng sang document khác origin. | Kiểm tra cả `event.origin` trên mỗi message. |
| Gửi secret với `targetOrigin: "*"` | Cửa sổ đích có thể điều hướng trước khi message được giao. | Dùng target origin chính xác; không gửi secret tới opaque context. |
| Tin mọi `event.data` từ origin hợp lệ | Payload có thể sai schema hoặc vượt giới hạn. | Kiểm tra type, schema, length, enum và state. |
| Dùng message xác nhận thanh toán | Client có thể giả mạo trạng thái hoặc widget có lỗi. | Server xác minh giao dịch từ nguồn có thẩm quyền. |
| Dùng message type tùy ý để gọi handler | Attacker có thể chọn hành động ngoài dự kiến. | Allowlist type và dispatch tường minh. |
| Không xử lý navigation/reload | Message cũ hoặc port cũ có thể gắn với phiên mới. | Dùng nonce, request ID, timeout và lifecycle rõ ràng. |
| Tin MessageChannel là an toàn mặc định | Port là capability có thể bị chuyển nhầm hoặc lộ. | Chỉ chuyển sau handshake và kiểm tra mọi payload. |

## 12. Kiểm thử MessageEvent origin

Thực hiện trong môi trường lab do bạn kiểm soát, với hai origin riêng biệt:

- Trang cha: `http://localhost:3000`.
- Trang widget thử nghiệm: `http://localhost:4000`.
- Trang không tin cậy: `http://localhost:5000`.

Hai cổng khác nhau tạo ra origin khác nhau, dù có thể cùng site. Mục tiêu là quan sát giá trị `event.origin`, `event.source` và việc listener từ chối message không mong đợi.

### 12.1 Đăng ký listener có kiểm tra

Trên trang cha:

```javascript
const expectedOrigin = "http://localhost:4000";
const frame = document.querySelector("#widget");

window.addEventListener("message", event => {
  console.log({
    origin: event.origin,
    sourceMatches: event.source === frame.contentWindow,
    data: event.data
  });

  if (event.origin !== expectedOrigin) return;
  if (event.source !== frame.contentWindow) return;
  if (!event.data || event.data.type !== "LAB_READY") return;

  console.log("Accepted widget message");
});
```

### 12.2 Gửi message từ widget hợp lệ

Trên trang widget:

```javascript
window.parent.postMessage(
  { type: "LAB_READY", version: 1 },
  "http://localhost:3000"
);
```

Trang cha phải ghi nhận đúng origin và source, sau đó mới chấp nhận message theo schema.

### 12.3 Gửi message từ origin khác

Trên trang không tin cậy:

```javascript
window.parent.postMessage(
  { type: "LAB_READY", version: 1 },
  "http://localhost:3000"
);
```

Trang cha có thể nhận event, nhưng `event.origin` là `http://localhost:5000` và phải bỏ qua. Việc browser cho phép gửi message không có nghĩa listener phải tin nó.

### 12.4 Thử sai targetOrigin

Từ widget, gửi message với target origin không khớp:

```javascript
window.parent.postMessage(
  { type: "SHOULD_NOT_ARRIVE" },
  "https://wrong.example"
);
```

Message không được chuyển tới document đích nếu origin của đích không khớp target origin tại thời điểm giao.

### 12.5 Quan sát trong DevTools

1. Mở DevTools → Console ở trang cha.
2. Ghi log `event.origin`, `event.source` và `event.data`.
3. Gửi message lần lượt từ widget và trang không tin cậy.
4. Xác nhận message từ origin khác bị bỏ qua.
5. Thử reload hoặc điều hướng iframe và quan sát source/origin.
6. Gửi payload sai schema và xác nhận không có side effect.

Không dùng log chứa access token, session ID hoặc dữ liệu cá nhân thật.

## 13. Quy trình thiết kế message protocol an toàn

1. **Liệt kê context:** xác định trang cha, iframe, popup, worker hoặc service nào cần trao đổi.
2. **Định nghĩa origin:** ghi rõ scheme, host và port của từng bên; không dùng wildcard domain.
3. **Xác định source:** lưu tham chiếu iframe/popup dự kiến và so sánh `event.source`.
4. **Định nghĩa message schema:** mỗi message có `type`, `version`, request ID và các field cần thiết.
5. **Giới hạn quyền:** chỉ cho phép các action cần thiết; không để message tùy ý gọi API hoặc handler.
6. **Chọn targetOrigin:** gửi tới origin chính xác, tránh `*` cho dữ liệu nhạy cảm.
7. **Xử lý lifecycle:** có handshake, timeout, nonce và cách thu hồi port khi frame reload/navigation.
8. **Kiểm tra server:** mọi hành động có tác động nghiệp vụ vẫn phải được authentication/authorization ở backend.
9. **Kiểm thử negative cases:** sai origin, sai source, `"null"`, payload sai schema, message lặp và navigation.

## 14. Checklist bảo mật

- [ ] Listener kiểm tra `event.origin` bằng so sánh chính xác.
- [ ] Listener kiểm tra `event.source` là đúng iframe/popup mong đợi.
- [ ] Không chấp nhận chuỗi `"null"` như một origin allowlist chung.
- [ ] Mỗi message có `type` và schema đã định nghĩa.
- [ ] Giới hạn độ dài chuỗi, kích thước mảng và số lượng message.
- [ ] Không thực thi chuỗi từ message bằng `eval`, `Function` hoặc HTML sink.
- [ ] Message trạng thái thanh toán/quyền được xác minh ở server.
- [ ] Sender dùng `targetOrigin` cụ thể khi có thể.
- [ ] Không gửi secret bằng wildcard target origin.
- [ ] Handshake có nonce/request ID khi cần ràng buộc phiên.
- [ ] `MessagePort` chỉ được chuyển sau khi xác minh bên nhận.
- [ ] Đã thử message từ origin lạ và trường hợp iframe/popup điều hướng.
- [ ] Log không chứa token hoặc dữ liệu nhạy cảm.

## 15. Câu hỏi tự kiểm tra

1. `event.origin` mô tả origin của bên gửi hay bên nhận?
2. Vì sao cần kiểm tra `event.source` ngoài `event.origin`?
3. `event.origin` được xác định tại thời điểm nào?
4. Origin khác site như thế nào? Vì sao không dùng same-site để thay allowlist origin?
5. Vì sao giá trị `"null"` không đại diện cho một origin cụ thể?
6. `targetOrigin` bảo vệ phía gửi ra sao?
7. Vì sao origin hợp lệ không chứng minh `event.data` đúng schema?
8. Structured clone có làm payload trở nên đáng tin không?
9. `MessageChannel` tạo capability gì và cần xác minh trước khi chuyển port ra sao?
10. Vì sao message `"PAYMENT_STATUS: completed"` không đủ để xác nhận giao dịch ở backend?

## 16. Tổng kết

`MessageEvent.origin` cho biết origin của context gửi message tại thời điểm gọi `postMessage()`. Hãy so sánh chính xác scheme, host và port với allowlist, đồng thời kiểm tra `event.source` để xác nhận đúng iframe hoặc popup. Không chấp nhận chuỗi `"null"` như một origin tin cậy chung vì nó có thể đại diện cho nhiều opaque origins.

Sau khi xác minh nguồn, tiếp tục kiểm tra schema, message type, request ID và trạng thái giao thức trước khi thực hiện side effect. Sender cần đặt `targetOrigin` cụ thể để tránh gửi dữ liệu tới document đã điều hướng sang origin khác. `MessageChannel` có thể tạo kênh riêng nhưng port là capability cần cấp có kiểm soát. Với thao tác nhạy cảm, server vẫn là nơi xác thực và phân quyền cuối cùng. Kiểm thử cả trường hợp đúng và sai origin/source, payload không hợp lệ, opaque origin và navigation để giữ an toàn cho ranh giới giao tiếp giữa các browsing context.
