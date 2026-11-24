# Wildcard targetOrigin: rủi ro và cách dùng postMessage an toàn

## 1. targetOrigin là gì?

API `window.postMessage()` cho phép hai browsing context trao đổi dữ liệu ngay cả khi chúng khác origin. Khi gửi message, bên gửi chỉ định **targetOrigin** để browser kiểm tra origin của tài liệu nhận trước khi giao message.

Ví dụ:

~~~js
const frame = document.querySelector("#widget-frame");

frame.contentWindow.postMessage(
  { type: "theme-change", theme: "dark" },
  "https://widget.example.test"
);
~~~

Tham số thứ hai là targetOrigin. Browser chỉ giao message nếu origin của tài liệu đang ở browsing context đích khớp với origin đã chỉ định tại thời điểm message được giao. Nếu không khớp, message bị loại bỏ.

Một số code dùng dấu wildcard:

~~~js
frame.contentWindow.postMessage(
  { type: "theme-change", theme: "dark" },
  "*"
);
~~~

Dấu `*` có nghĩa là **không giới hạn origin của tài liệu nhận trong browsing context đích**. Message có thể được giao cho tài liệu đang chiếm context đó, bất kể origin của nó là gì. Đây là rủi ro nếu context có thể bị điều hướng sang một trang không tin cậy trước khi message được giao.

Wildcard không phải broadcast tới mọi tab hoặc mọi iframe. Nó vẫn gửi tới một đối tượng Window/WindowProxy cụ thể; dấu * chỉ bỏ bước giới hạn origin của tài liệu hiện đang ở context đó.

Bài học thuộc chương **postMessage** của module **SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY**. Module nghiên cứu ranh giới bảo mật giữa browser, origin, cookie và ứng dụng web; bài này tập trung vào việc gửi message cross-origin, cách targetOrigin bảo vệ người nhận, rủi ro khi dùng wildcard, trường hợp opaque origin và cách xác thực message ở phía nhận.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vai trò của targetOrigin trong window.postMessage.
2. Phân biệt wildcard `*` với một origin cụ thể và hiểu thời điểm browser kiểm tra đích.
3. Mô tả rủi ro khi WindowProxy tồn tại qua điều hướng của iframe hoặc popup.
4. Viết targetOrigin chính xác theo scheme, host và port.
5. Phân biệt targetOrigin ở phía gửi với event.origin và event.source ở phía nhận.
6. Nhận diện trường hợp opaque origin khiến không thể chỉ định origin đích cụ thể.
7. Xây dựng giao thức handshake, kiểm tra schema và dùng MessageChannel phù hợp.
8. Biết khi nào wildcard có thể chấp nhận được và dữ liệu nào tuyệt đối không nên gửi qua nó.
9. Kiểm chứng hành vi bằng hai origin thử nghiệm và DevTools.

## 2. postMessage giải quyết vấn đề gì?

Same-Origin Policy (SOP) ngăn JavaScript của một origin tùy ý đọc DOM và dữ liệu của origin khác. Tuy vậy, ứng dụng thường cần tích hợp có chủ đích giữa parent và child, ví dụ:

- Portal nhúng widget báo cáo.
- Trang chủ giao tiếp với iframe thanh toán.
- Popup đăng nhập gửi kết quả về trang đã mở nó.
- Ứng dụng nhúng video hoặc bản đồ cần nhận cấu hình.
- Các micro-frontend chạy trên origin riêng.
- Trang host gửi ngôn ngữ hoặc theme cho nội dung được nhúng.

`postMessage` cung cấp một kênh gửi message qua ranh giới origin mà không cần cấp quyền đọc DOM trực tiếp.

Ví dụ parent gửi cấu hình cho child:

~~~js
const child = document.querySelector("#child-frame");

child.contentWindow.postMessage(
  {
    type: "initialize",
    locale: "vi",
    theme: "light"
  },
  "https://widget.example.test"
);
~~~

Child nhận:

~~~js
window.addEventListener("message", (event) => {
  if (event.origin !== "https://portal.example.test") return;
  if (event.source !== window.parent) return;

  if (event.data?.type === "initialize") {
    initializeWidget(event.data);
  }
});
~~~

Đây là hai lớp kiểm tra khác nhau:

- targetOrigin ở phía gửi giới hạn **tài liệu nhận**.
- event.origin và event.source ở phía nhận kiểm tra **nguồn gửi**.

Không có lớp nào tự thay thế lớp còn lại.

## 3. targetOrigin được browser kiểm tra lúc nào?

Khi gọi `postMessage`, browser tạo message và xếp việc giao message vào hàng đợi của browsing context đích. Khi message được xử lý, browser so origin hiện tại của tài liệu nhận với targetOrigin.

Nếu origin không khớp, message không được giao. Điều này đặc biệt quan trọng vì một iframe hoặc popup có thể điều hướng sau khi bên gửi đã lấy được tham chiếu tới nó.

Ví dụ trình tự:

1. Parent lấy `frame.contentWindow` khi iframe đang hiển thị widget.example.test.
2. Parent chuẩn bị gửi message.
3. Iframe điều hướng sang attacker.example.test.
4. Message được giao sau khi điều hướng hoàn tất.
5. Với targetOrigin `*`, tài liệu mới vẫn có thể nhận message.
6. Với targetOrigin `https://widget.example.test`, message không được giao cho tài liệu ở attacker.example.test.

Đây là lý do không nên dùng wildcard khi biết origin đích.

### 3.1. WindowProxy có thể tồn tại qua navigation

Thuộc tính `contentWindow` trả về tham chiếu đại diện cho browsing context của iframe. Trình duyệt dùng WindowProxy để đại diện window qua các lần điều hướng. Khi tài liệu bên trong thay đổi, tham chiếu WindowProxy mà parent giữ có thể vẫn đại diện cho cùng browsing context.

Do đó:

~~~js
const target = frame.contentWindow;
~~~

không có nghĩa tài liệu đang chiếm frame ở mọi thời điểm sau này vẫn là tài liệu ban đầu.

Cần hiểu riêng:

- **WindowProxy:** tham chiếu tới browsing context.
- **Document hiện tại:** tài liệu đang được tải trong context đó.
- **Origin hiện tại:** origin của tài liệu hiện đang chiếm context.
- **targetOrigin:** điều kiện browser dùng để quyết định có giao message cho tài liệu đó hay không.

### 3.2. Wildcard bỏ lớp kiểm tra người nhận

Nếu dùng:

~~~js
target.postMessage({ type: "session-ready" }, "*");
~~~

browser không kiểm tra origin của tài liệu nhận. Nếu context bị điều hướng sang một trang khác, trang đó có thể nhận dữ liệu khi message được giao.

Ngay cả khi message ban đầu chỉ dành cho widget hợp lệ, wildcard làm mất bảo đảm rằng đúng origin widget mới được nhận message.

## 4. Rủi ro bảo mật của wildcard targetOrigin

Có hai nhóm rủi ro chính: **lộ dữ liệu** và **sai lệch luồng điều khiển**.

### 4.1. Lộ dữ liệu

Nếu message chứa thông tin nhạy cảm, trang không mong muốn có thể nhận được:

- Access token, refresh token hoặc session identifier.
- Dữ liệu hồ sơ hoặc thông tin thanh toán.
- Nội dung báo cáo nội bộ.
- Mã xác nhận hoặc dữ liệu khôi phục tài khoản.
- Thông tin cấu hình riêng của user.
- Capability token dùng để gọi API hoặc thao tác tài nguyên.

Không gửi các giá trị này bằng wildcard.

### 4.2. Sai lệch luồng điều khiển

Message không chứa secret vẫn có thể gây hại nếu nó kích hoạt hành động. Ví dụ:

~~~js
target.postMessage(
  { type: "confirm-payment", orderId: "ORDER-123" },
  "*"
);
~~~

Nếu một tài liệu ngoài dự kiến nhận được message và có listener xử lý lệnh đó, ứng dụng có thể thực hiện hành động sai ngữ cảnh.

Các message như `delete-record`, `approve-transfer`, `connect-account` hoặc `change-role` cần xác thực người gửi/người nhận, schema, quyền và trạng thái nghiệp vụ. Không xem việc payload không có token là an toàn.

### 4.3. Message có thể bị gửi tới tài liệu cùng context nhưng khác origin

Wildcard không tạo thêm browsing context và không gửi tới toàn bộ cửa sổ. Nó cho phép giao tới tài liệu bất kỳ đang chiếm đúng context đích. Rủi ro xuất hiện khi context đó có thể điều hướng hoặc được thay thế bằng một tài liệu không còn thuộc origin mong đợi.

### 4.4. Origin cùng host vẫn là ranh giới tin cậy rộng

Ngay cả targetOrigin chính xác cũng chỉ giới hạn theo origin, gồm scheme, host và port; nó không giới hạn theo path. Nếu một origin chứa cả ứng dụng tin cậy và nội dung người dùng có thể kiểm soát, tài liệu không tin cậy trên cùng origin vẫn khớp targetOrigin.

Nếu cần cô lập tenant hoặc nội dung không tin cậy, dùng origin riêng hoặc một ranh giới kiến trúc phù hợp. Không dùng path để giả lập ranh giới origin.

## 5. Dùng targetOrigin chính xác

Nếu biết origin của tài liệu nhận, chỉ định chính xác:

~~~js
const frame = document.querySelector("#widget-frame");

frame.contentWindow.postMessage(
  { type: "resize", height: 420 },
  "https://widget.example.test"
);
~~~

Origin phải khớp scheme, host và port. Ví dụ các giá trị sau là những origin khác nhau:

~~~text
https://widget.example.test
http://widget.example.test
https://widget.example.test:8443
https://portal.example.test
~~~

Path không phải một phần của origin. targetOrigin không thể giới hạn tài liệu nhận vào riêng `/widget` hoặc `/checkout`.

### 5.1. Dùng URL parser thay vì nối chuỗi origin

Nếu URL đích được cấu hình trong ứng dụng:

~~~js
const widgetUrl = new URL(
  "https://widget.example.test/embed",
  window.location.href
);

const targetOrigin = widgetUrl.origin;

frame.contentWindow.postMessage(
  { type: "initialize", locale: "vi" },
  targetOrigin
);
~~~

`URL.origin` tạo origin chuẩn hóa, gồm scheme, host và port hiệu lực. Không dùng toàn bộ `location.href` làm targetOrigin vì giá trị đó chứa path, query và fragment.

### 5.2. Không xác minh bằng prefix hoặc suffix

Không viết:

~~~js
if (event.origin.includes("example.test")) {
  acceptMessage(event);
}
~~~

Hoặc:

~~~js
if (event.origin.endsWith("example.test")) {
  acceptMessage(event);
}
~~~

Các phép kiểm tra chuỗi này có thể chấp nhận host như `example.test.attacker.test` hoặc các tên miền có cấu trúc gây nhầm lẫn.

Hãy so sánh origin chính xác:

~~~js
const allowedOrigins = new Set([
  "https://portal.example.test",
  "https://admin.example.test"
]);

if (!allowedOrigins.has(event.origin)) {
  return;
}
~~~

## 6. targetOrigin mặc định và wildcard khác nhau

Cú pháp phổ biến:

~~~js
targetWindow.postMessage(message, targetOrigin);
~~~

Trong API hiện đại cũng có dạng options:

~~~js
targetWindow.postMessage(message, {
  targetOrigin: "https://widget.example.test"
});
~~~

Nếu bỏ tham số targetOrigin theo overload hỗ trợ, giá trị mặc định `/` biểu thị origin của caller. Dù vậy, code bảo mật nên truyền rõ origin đích để ý định dễ review và tránh phụ thuộc vào mặc định hoặc overload.

| Giá trị | Ý nghĩa |
| --- | --- |
| `https://widget.example.test` | Chỉ giao nếu tài liệu đích có origin chính xác này. |
| `*` | Không giới hạn origin của tài liệu đang chiếm context đích. |
| `/` | Origin mặc định cùng origin với caller theo overload hỗ trợ. |

Không nhầm dấu `/` với đường dẫn root của website. Nó là giá trị đặc biệt trong API postMessage.

## 7. targetOrigin và event.origin là hai chiều khác nhau

Tên gần giống nhau nhưng hai giá trị được dùng ở hai phía:

| Thuộc tính | Nằm ở đâu | Câu hỏi |
| --- | --- | --- |
| targetOrigin | Tham số của postMessage bên gửi | Tài liệu origin nào được phép nhận message này? |
| event.origin | MessageEvent bên nhận | Message được gửi từ origin nào? |
| event.source | MessageEvent bên nhận | Window/context nào đã gửi message? |
| event.data | MessageEvent bên nhận | Payload là gì? |

Ví dụ parent gửi cho child:

~~~js
childWindow.postMessage(
  { type: "ready" },
  "https://widget.example.test"
);
~~~

Child xác minh parent:

~~~js
window.addEventListener("message", (event) => {
  if (event.origin !== "https://portal.example.test") return;
  if (event.source !== window.parent) return;

  handleParentMessage(event.data);
});
~~~

targetOrigin ở parent không xác minh ai đã gửi message tới parent. Parent cũng cần listener kiểm tra event.origin và event.source khi nhận message ngược lại.

## 8. Kiểm tra event.origin và event.source ở phía nhận

Một listener an toàn cần xác minh ít nhất:

1. Origin gửi có nằm trong allowlist chính xác không?
2. Window/context gửi có phải đối tượng mong đợi không?
3. Message có đúng schema và loại lệnh được hỗ trợ không?
4. Giá trị có đúng kiểu, giới hạn độ dài và miền giá trị không?
5. Hành động có phù hợp với trạng thái hiện tại và quyền user không?

Ví dụ:

~~~js
const PORTAL_ORIGIN = "https://portal.example.test";

window.addEventListener("message", (event) => {
  if (event.origin !== PORTAL_ORIGIN) return;
  if (event.source !== window.parent) return;

  const data = event.data;

  if (
    data === null ||
    typeof data !== "object" ||
    Array.isArray(data) ||
    data.type !== "set-locale" ||
    typeof data.locale !== "string"
  ) {
    return;
  }

  const supportedLocales = new Set(["vi", "en"]);
  if (!supportedLocales.has(data.locale)) return;

  setLocale(data.locale);
});
~~~

Kiểm tra origin/source chỉ xác định kênh gửi theo mô hình browser. Nó không thay authentication, authorization hoặc validation nghiệp vụ. Một origin được allowlist vẫn có thể có XSS hoặc code bị xâm nhập.

### 8.1. event.origin phản ánh origin tại thời điểm gửi

event.origin biểu thị origin của context gửi khi message được phát đi. Nó không phải lời cam kết rằng context gửi vẫn đang ở origin đó tại thời điểm receiver xử lý event.

Nếu ứng dụng cần biết sender hiện tại có còn là tài liệu mong đợi, thiết kế giao thức phải cân nhắc navigation, handshake và trạng thái kết nối. Không dùng event.origin một mình để suy ra trạng thái hiện tại của sender.

### 8.2. event.source là WindowProxy, không phải định danh document bất biến

event.source giúp so sánh sender với parent, iframe hoặc popup cụ thể. Nhưng WindowProxy có thể đại diện context qua các lần điều hướng. Vì vậy event.source cần đi cùng event.origin, schema và trạng thái của giao thức.

Không chấp nhận message chỉ vì `event.source === window.parent` nếu bất kỳ tài liệu nào có thể điều hướng hoặc chiếm parent context.

## 9. Trường hợp đặc biệt: opaque origin

Một số tài liệu có **opaque origin** thay vì origin tuple thông thường. Ví dụ có thể gồm:

- Tài liệu dùng URL data:.
- Iframe sandbox không có token allow-same-origin.
- Một số tài liệu được tạo trong môi trường có origin bị làm opaque theo chuẩn browser.

Opaque origin không có bộ ba scheme/host/port có thể dùng để so khớp như origin thông thường. Khi được serialize trong event.origin, nó thường xuất hiện dưới dạng chuỗi `"null"`.

Không được xem `event.origin === "null"` là bằng chứng một sender đáng tin. Nhiều tài liệu opaque origin khác nhau có thể serialize thành cùng chuỗi này.

### 9.1. Vì sao đôi khi phải dùng wildcard?

Khi target browsing context có opaque origin, bên gửi không thể chỉ định một origin tuple cụ thể để khớp. Trong một số trường hợp, API yêu cầu dùng `*` để gửi message tới context đó.

Ví dụ iframe sandbox:

~~~html
<iframe
  id="isolated-frame"
  src="https://untrusted-widget.example.test"
  sandbox="allow-scripts"
  title="Widget cô lập"
></iframe>
~~~

Vì không có allow-same-origin, tài liệu con bị cấp opaque origin. Parent có thể cần:

~~~js
const frame = document.querySelector("#isolated-frame");

frame.contentWindow.postMessage(
  { type: "initialize", theme: "light" },
  "*"
);
~~~

Đây là ngoại lệ cần threat model rõ. Message chỉ nên chứa dữ liệu công khai, không nhạy cảm và không trao capability có thể dùng để truy cập tài nguyên.

### 9.2. Receiver vẫn phải xác minh sender

Ở phía iframe, origin của parent có thể là origin tuple thông thường:

~~~js
window.addEventListener("message", (event) => {
  if (event.origin !== "https://portal.example.test") return;
  if (event.source !== window.parent) return;

  if (event.data?.type === "initialize") {
    applyPublicConfiguration(event.data);
  }
});
~~~

Opaque origin của child không làm mất khả năng xác minh origin của parent. Tuy nhiên, parent gửi tới child bằng wildcard vẫn không có bảo đảm origin cụ thể của tài liệu nhận.

### 9.3. Không gửi secret vào opaque-origin frame qua wildcard

Nếu tài liệu nhận có opaque origin, targetOrigin cụ thể không thể đóng vai trò giới hạn người nhận. Nếu nội dung hoặc browsing context có thể bị thay thế, secret gửi qua wildcard có thể tới sai tài liệu.

Nếu cần gửi thông tin nhạy cảm, cân nhắc phục vụ ứng dụng nhận từ một origin riêng biệt, ổn định và có thể allowlist; thiết kế lại sandbox để đạt ranh giới phù hợp. Không nới sandbox chỉ để gửi token mà chưa đánh giá hậu quả.

## 10. Handshake trước khi trao đổi message

Một handshake giúp hai phía xác nhận giao thức và trạng thái kết nối trước khi trao đổi dữ liệu nghiệp vụ. Handshake không tự xác thực origin nếu dùng wildcard; nó cần kết hợp targetOrigin và kiểm tra origin/source.

Parent:

~~~js
const widgetOrigin = "https://widget.example.test";
const frame = document.querySelector("#widget-frame");

function sendInitialization() {
  frame.contentWindow.postMessage(
    {
      type: "host-init",
      version: 1,
      locale: "vi"
    },
    widgetOrigin
  );
}
~~~

Child:

~~~js
const hostOrigin = "https://portal.example.test";

window.addEventListener("message", (event) => {
  if (event.origin !== hostOrigin) return;
  if (event.source !== window.parent) return;

  if (
    event.data?.type === "host-init" &&
    event.data.version === 1
  ) {
    window.parent.postMessage(
      { type: "widget-ready", version: 1 },
      hostOrigin
    );
  }
});
~~~

Parent cũng cần listener kiểm tra event.origin, event.source và schema trước khi đánh dấu widget sẵn sàng.

### 10.1. Handshake không biến wildcard thành an toàn

Một thông điệp `hello` hoặc `ready` không chứng minh tài liệu nhận là đáng tin nếu parent gửi message đầu tiên bằng wildcard. Tài liệu khác chiếm cùng context vẫn có thể trả lời theo giao thức giả.

Handshake cần bắt đầu từ một origin có thể xác minh hoặc một cơ chế nhận diện độc lập đã được thiết kế. Không gửi secret trước khi xác minh người nhận.

### 10.2. Version và state machine

Với giao thức có nhiều bước, xác định trạng thái rõ:

- created
- waiting-for-ready
- initialized
- active
- closed

Chỉ chấp nhận message hợp lệ cho trạng thái hiện tại. Từ chối message lặp, sai thứ tự hoặc có version không hỗ trợ. Điều này giúp giảm lỗi logic và replay trong một số giao thức.

## 11. MessageChannel có thay targetOrigin không?

`MessageChannel` tạo hai MessagePort liên kết để hai phía trao đổi sau khi thiết lập kênh. Nó hữu ích khi cần một kênh riêng cho một widget hoặc một phiên làm việc.

Parent tạo channel:

~~~js
const channel = new MessageChannel();
const frame = document.querySelector("#widget-frame");
const widgetOrigin = "https://widget.example.test";

frame.contentWindow.postMessage(
  { type: "connect", version: 1 },
  widgetOrigin,
  [channel.port2]
);

channel.port1.onmessage = (event) => {
  handleWidgetMessage(event.data);
};
~~~

Child nhận port sau khi xác minh nguồn:

~~~js
window.addEventListener("message", (event) => {
  if (event.origin !== "https://portal.example.test") return;
  if (event.source !== window.parent) return;
  if (event.data?.type !== "connect") return;

  const port = event.ports[0];
  if (!port) return;

  port.postMessage({ type: "connected", version: 1 });
});
~~~

MessagePort có thể làm giao thức gọn hơn, nhưng **không tự xác thực người nhận trong bước bootstrap**. Nếu parent chuyển port tới iframe bằng targetOrigin `*`, tài liệu không mong muốn đang chiếm frame tại thời điểm giao có thể nhận port và dùng nó.

Dùng targetOrigin chính xác cho bước chuyển port khi có thể. Sau đó vẫn validate schema và quyền cho từng message.

## 12. Dùng wildcard khi nào có thể chấp nhận?

Wildcard có thể hợp lý khi ứng dụng chủ động chấp nhận rằng bất kỳ tài liệu nào đang chiếm browsing context đích đều được nhận một message không nhạy cảm, hoặc khi target là opaque origin và API không cho phép chỉ định origin cụ thể.

Một số điều kiện cần cân nhắc:

- Payload công khai, không chứa secret, dữ liệu cá nhân hoặc capability token.
- Message không trực tiếp kích hoạt hành động nhạy cảm.
- Ứng dụng không dựa vào danh tính tài liệu nhận để quyết định quyền.
- Receiver có kiểm tra sender origin/source và schema.
- Rủi ro navigation của browsing context đã được đánh giá.
- Có thể chấp nhận việc message bị một tài liệu khác trong context nhận.

Ví dụ dữ liệu giao diện công khai:

~~~js
frame.contentWindow.postMessage(
  { type: "display-hint", colorScheme: "light" },
  "*"
);
~~~

Ngay cả ví dụ này, nếu biết origin đích thì nên dùng origin cụ thể. Wildcard là lựa chọn có ý thức cho trường hợp giới hạn, không phải giá trị mặc định để code “chạy được”.

## 13. Khi nào tuyệt đối tránh wildcard?

Tránh `*` khi gửi:

- Access token, refresh token, session identifier hoặc cookie secret.
- Thông tin cá nhân, hồ sơ, dữ liệu tài chính hoặc dữ liệu nội bộ.
- Mã xác nhận, reset token hoặc one-time password.
- Capability token hoặc dữ liệu cấp quyền.
- Lệnh thay đổi trạng thái hoặc phê duyệt nghiệp vụ.
- Dữ liệu mà chỉ một origin đối tác cụ thể được phép biết.
- MessagePort hoặc handle cấp quyền mà người nhận không mong muốn có thể sử dụng.

Nếu target context có thể điều hướng, wildcard làm mất bảo vệ ở ranh giới người nhận. Hãy dùng exact targetOrigin hoặc thiết kế lại tích hợp để có origin đích ổn định.

## 14. Cùng origin nhưng nhiều ứng dụng hoặc tenant

Exact targetOrigin không giới hạn theo path. Ví dụ:

~~~text
https://app.example.test/dashboard
https://app.example.test/user-content
~~~

Cả hai đều có origin `https://app.example.test`. Nếu user-content chứa nội dung do người dùng kiểm soát hoặc script không đáng tin, một message gửi tới origin này có thể được tài liệu đó nhận.

Đây là lý do multi-tenant hoặc user-generated content đôi khi cần origin riêng, chẳng hạn:

~~~text
https://app.example.test
https://usercontent.example-cdn.test
~~~

Tách origin giúp browser áp dụng SOP và targetOrigin chính xác hơn. Tuy nhiên, cần quản lý cookie domain, CORS, CSP, DNS và luồng xác thực phù hợp với kiến trúc.

Không coi path khác nhau là ranh giới bảo mật giữa hai ứng dụng.

## 15. Dữ liệu postMessage và structured clone

postMessage dùng structured clone để sao chép nhiều loại dữ liệu giữa context. Payload có thể là object, array, string, number, boolean, Date, Map hoặc một số kiểu dữ liệu được hỗ trợ. Có thể chuyển transferable như ArrayBuffer, MessagePort.

Structured clone không có nghĩa payload đáng tin. Receiver vẫn phải kiểm tra:

- Kiểu dữ liệu cấp cao.
- Các field được phép.
- Độ dài string và kích thước array.
- Giá trị enum/ID có nằm trong tập hỗ trợ.
- Message có đúng trạng thái giao thức.
- Không có URL hoặc command tùy ý đi vào sink nhạy cảm.

Ví dụ schema kiểm tra đơn giản:

~~~js
function isResizeMessage(value) {
  return (
    value !== null &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    value.type === "resize" &&
    Number.isInteger(value.height) &&
    value.height >= 100 &&
    value.height <= 1200
  );
}
~~~

Sau đó:

~~~js
window.addEventListener("message", (event) => {
  if (event.origin !== "https://widget.example.test") return;
  if (event.source !== expectedFrame.contentWindow) return;
  if (!isResizeMessage(event.data)) return;

  resizeWidget(event.data.height);
});
~~~

Không đưa message data trực tiếp vào innerHTML, eval, script.src hoặc location mà không kiểm tra context và allowlist.

## 16. postMessage không phải CORS

postMessage và CORS đều liên quan giao tiếp cross-origin nhưng hoạt động khác nhau:

| Cơ chế | Mục tiêu |
| --- | --- |
| postMessage | Trao đổi message có chủ đích giữa browsing contexts/window. |
| CORS | Quyết định JavaScript có được phép đọc response cross-origin theo cơ chế fetch/CORS hay không. |
| SOP | Giới hạn truy cập dữ liệu giữa các origin. |
| CSP | Giới hạn nguồn và một số hành vi của tài liệu. |

Một iframe cross-origin có thể dùng postMessage mà không cần bật CORS chỉ để gửi message. Ngược lại, bật CORS cho API không tự tạo một giao thức message an toàn và không xác thực sender của postMessage.

Không dùng Access-Control-Allow-Origin để thay event.origin/source validation.

## 17. postMessage, sandbox và CSP

Một iframe sandboxed có thể có opaque origin nếu không cấp allow-same-origin. Điều đó ảnh hưởng targetOrigin và event.origin như phần trước.

CSP cũng có directive liên quan đến việc tải frame:

- frame-src: parent kiểm soát nguồn URL được tải vào iframe.
- frame-ancestors: child kiểm soát những ancestor được phép nhúng nó.

Các directive này kiểm soát việc nhúng/tải document; chúng không xác thực từng message postMessage.

Ví dụ:

~~~http
Content-Security-Policy: default-src 'self'; frame-src https://widget.example.test; object-src 'none'; base-uri 'none'
~~~

Child:

~~~http
Content-Security-Policy: frame-ancestors https://portal.example.test
~~~

Ngay cả khi CSP cho phép tích hợp, ứng dụng vẫn phải dùng targetOrigin và xác minh message.

## 18. Navigation race và vòng đời iframe/popup

Một vấn đề thường bị bỏ qua là target browsing context có thể thay đổi tài liệu trong khi ứng dụng đang chạy.

Các tình huống:

- Iframe tự điều hướng sau một sự kiện.
- Parent cập nhật src khi chuyển route.
- Popup điều hướng qua redirect.
- Người dùng đóng rồi mở lại cửa sổ.
- Frame bị thay bằng một trang lỗi hoặc trang đăng nhập.
- Một endpoint bị chuyển hướng tới origin khác.

Với popup mở tới website ngoài, dùng `rel="noopener"` hoặc tùy chọn `noopener` của `window.open()` nếu trang mở không cần giữ quan hệ opener. Khi đó popup không thể dùng `window.opener.postMessage()` để callback về trang mở. Nếu sản phẩm cần callback, hãy thiết kế một flow riêng có xác thực và target origin rõ ràng; chỉ giữ quan hệ opener khi popup thuộc tích hợp đã tin cậy và thực sự cần nó.

Nếu ứng dụng lưu tham chiếu WindowProxy lâu dài, hãy gắn trạng thái kết nối với vòng đời frame. Khi bắt đầu navigation mới, vô hiệu hóa session message cũ và thiết lập handshake mới sau khi tài liệu hợp lệ sẵn sàng.

Exact targetOrigin giúp browser loại bỏ message nếu origin đích không khớp tại lúc giao. Nhưng nếu tài liệu mới cùng origin, targetOrigin vẫn khớp; khi đó cần bảo đảm mọi tài liệu trên origin đó thuộc cùng ranh giới tin cậy hoặc tách origin.

## 19. Những lỗi triển khai thường gặp

1. **Dùng `*` vì tiện:** message có thể tới bất kỳ tài liệu nào đang chiếm context đích.
2. **Gửi token qua wildcard:** tạo đường lộ credential hoặc capability.
3. **Giữ WindowProxy rồi giả định document không đổi:** iframe/popup có thể điều hướng.
4. **Nhầm targetOrigin với event.origin:** một cái giới hạn người nhận, một cái cho biết origin người gửi.
5. **Chỉ kiểm tra event.source:** WindowProxy có thể tồn tại qua navigation.
6. **Chỉ kiểm tra event.origin bằng includes/endsWith:** dễ chấp nhận origin giả.
7. **Chấp nhận event.origin là null:** opaque origin không định danh duy nhất một tài liệu tin cậy.
8. **Dùng path trong targetOrigin:** origin không chứa path.
9. **Dùng location.href làm targetOrigin:** giá trị có path/query, không phải origin thuần.
10. **Cho rằng postMessage cần CORS:** hai cơ chế khác nhau.
11. **Cho rằng CORS cho phép message an toàn:** CORS không thay protocol validation.
12. **Dùng wildcard để gửi MessagePort:** người nhận ngoài dự kiến có thể nhận channel.
13. **Không validate event.data:** payload có thể sai kiểu, quá lớn hoặc không đúng trạng thái.
14. **Dùng message trực tiếp trong sink:** có thể tạo DOM XSS, open redirect hoặc hành động ngoài ý muốn.
15. **Tin handshake đơn giản:** hello/ready không xác thực người nhận nếu bước đầu dùng wildcard.
16. **Coi sandbox là đủ:** sandbox hạn chế quyền frame nhưng không tự xác thực message.
17. **Không reset trạng thái khi frame navigation:** message cũ có thể được xử lý trong phiên kết nối mới.
18. **Dùng chung origin cho app tin cậy và nội dung không tin cậy:** exact targetOrigin không phân biệt path.

## 20. Thực hành A — So sánh exact targetOrigin và wildcard

Tạo hai trang local trên hai origin thử nghiệm khác nhau, ví dụ portal.test và widget.test. Dùng iframe trong portal.

Gửi message với origin cụ thể:

~~~js
const frame = document.querySelector("#widget-frame");

frame.contentWindow.postMessage(
  { type: "demo", value: "public" },
  "https://widget.test"
);
~~~

Sau đó thay targetOrigin bằng `*` và quan sát event listener ở child.

Mục tiêu là xác nhận cả hai dạng đều gửi được khi widget đang ở origin phù hợp, nhưng exact targetOrigin giữ điều kiện origin ở thời điểm giao message.

## 21. Thực hành B — Quan sát navigation race trong môi trường local

Dùng hai trang thử nghiệm do bạn kiểm soát, không gửi dữ liệu nhạy cảm.

1. Tạo iframe ban đầu tải trang ở origin A.
2. Parent lấy frame.contentWindow.
3. Parent xếp một message công khai vào hàng đợi.
4. Điều hướng iframe sang origin B trước khi message được xử lý nếu môi trường test cho phép tạo timing đó.
5. So sánh kết quả với targetOrigin `*` và targetOrigin là origin A.
6. Quan sát listener nào nhận được message trong DevTools.

Kết quả mong đợi: wildcard không giới hạn origin tài liệu nhận; exact origin A khiến message bị loại nếu context đã ở origin B lúc browser kiểm tra đích.

Không dùng access token, cookie hoặc dữ liệu người dùng trong bài thực hành.

## 22. Thực hành C — Xác minh event.origin và event.source

Ở parent, listener chỉ chấp nhận widget đã cấu hình:

~~~js
const frame = document.querySelector("#widget-frame");
const widgetOrigin = "https://widget.test";

window.addEventListener("message", (event) => {
  if (event.origin !== widgetOrigin) return;
  if (event.source !== frame.contentWindow) return;

  if (
    event.data?.type === "status" &&
    typeof event.data.ready === "boolean"
  ) {
    console.log("Widget status:", event.data.ready);
  }
});
~~~

Thử gửi message từ một origin khác và từ một iframe khác. Xác minh listener bỏ qua cả hai. Thử thay payload sai schema và xác nhận không có hành động được thực hiện.

## 23. Thực hành D — Opaque origin và sandbox

Tạo iframe:

~~~html
<iframe
  id="sandboxed"
  src="https://widget.test/demo"
  sandbox="allow-scripts"
  title="Sandbox demo"
></iframe>
~~~

Do thiếu allow-same-origin, child có opaque origin. Parent thử gửi một cấu hình công khai bằng targetOrigin `*`. Ở phía child, kiểm tra event.origin của parent và event.source.

Ghi nhận:

- Parent cần wildcard vì không có origin tuple cụ thể để nhắm tới opaque child.
- Child vẫn có thể xác minh origin của parent.
- event.origin của chính child khi gửi ngược có thể serialize thành `"null"`.
- Không gửi secret hoặc capability token vào frame chỉ có opaque origin nếu không có một thiết kế nhận diện và trao quyền an toàn.

## 24. Checklist review wildcard targetOrigin

- [ ] Xác định browsing context đích là iframe, popup hay window khác.
- [ ] Dùng targetOrigin chính xác nếu biết origin của tài liệu nhận.
- [ ] So khớp đầy đủ scheme, host và port; không dùng prefix/suffix.
- [ ] Không đưa path, query hoặc fragment vào targetOrigin.
- [ ] Hiểu WindowProxy có thể tồn tại qua navigation.
- [ ] Đánh giá liệu iframe/popup có thể điều hướng trước lúc message được giao.
- [ ] Không gửi token, secret, dữ liệu cá nhân hoặc capability qua wildcard.
- [ ] Không dùng wildcard cho lệnh thay đổi trạng thái hoặc phê duyệt.
- [ ] Nếu cần wildcard do opaque origin, giới hạn payload ở dữ liệu công khai, ít quyền.
- [ ] Không coi event.origin là định danh duy nhất khi giá trị là "null".
- [ ] Receiver kiểm tra event.origin chính xác và event.source mong đợi.
- [ ] Validate schema, kiểu, độ dài, enum và trạng thái giao thức.
- [ ] Không dùng message data trực tiếp trong HTML, script, URL hoặc command sink.
- [ ] Dùng handshake có version và state machine cho giao thức nhiều bước.
- [ ] Dùng MessageChannel khi cần kênh riêng nhưng xác thực bước bootstrap trước.
- [ ] Reset trạng thái message khi frame/popup navigation hoặc đóng.
- [ ] Tách origin cho nội dung không tin cậy hoặc tenant có mức tin cậy khác nhau.
- [ ] Phân biệt postMessage với CORS, SOP và CSP.
- [ ] Kiểm thử navigation race với dữ liệu công khai trên origin test.
- [ ] Ghi nhận browser/version và kiểm tra Console/Network khi debug.

## 25. Những ngộ nhận thường gặp

| Nhận định | Đánh giá | Giải thích |
| --- | --- | --- |
| “`*` gửi message tới mọi tab.” | **Sai** | Nó bỏ giới hạn origin cho một WindowProxy cụ thể, không broadcast. |
| “Nếu đã giữ contentWindow thì người nhận không đổi.” | **Sai** | WindowProxy có thể đại diện browsing context qua navigation. |
| “targetOrigin `*` chỉ là cách viết ngắn của self.” | **Sai** | Wildcard không giới hạn origin tài liệu nhận. |
| “targetOrigin chính xác xác định cả path.” | **Sai** | Origin chỉ gồm scheme, host và port. |
| “event.origin và targetOrigin là một.” | **Sai** | Một giá trị kiểm tra người gửi, một giá trị giới hạn người nhận. |
| “event.source đủ xác thực sender.” | **Sai** | WindowProxy có thể tồn tại qua navigation; kiểm tra cả origin và protocol. |
| “event.origin là null thì sender vô danh nhưng có thể tin.” | **Sai** | Nhiều opaque origin serialize thành "null"; không phải danh tính đáng tin. |
| “Opaque origin có thể được nhắm bằng host source.” | **Sai** | Không có origin tuple cụ thể để khớp; có thể phải dùng wildcard. |
| “MessageChannel loại bỏ rủi ro wildcard.” | **Sai** | Port vẫn có thể được chuyển tới sai tài liệu ở bước bootstrap. |
| “postMessage cần CORS.” | **Sai** | postMessage là cơ chế message riêng giữa browsing contexts. |
| “CSP frame-src xác thực message.” | **Sai** | frame-src kiểm soát nguồn frame được tải, không xác thực payload. |
| “Handshake hello/ready luôn xác thực widget.” | **Sai** | Handshake phải có origin/source validation và bước gửi ban đầu an toàn. |
| “Message object được structured clone nên đáng tin.” | **Sai** | Structured clone chỉ sao chép dữ liệu; receiver vẫn phải validate. |
| “Origin chính xác luôn tách được tenant.” | **Sai** | Path không thuộc origin; tenant không tin cậy cần ranh giới riêng. |

## 26. Tổng kết

targetOrigin là lớp kiểm soát người nhận trong window.postMessage. Dùng origin chính xác giúp browser chỉ giao message nếu tài liệu đang chiếm browsing context đích có đúng scheme, host và port được chỉ định. Dùng `*` bỏ giới hạn đó; message có thể tới một tài liệu khác nếu iframe hoặc popup điều hướng trước khi message được giao.

Ba nguyên tắc cần nhớ:

1. **Ưu tiên exact targetOrigin:** dùng origin đã cấu hình hoặc URL.origin; không dùng wildcard chỉ để tránh lỗi tích hợp.
2. **Xác minh cả hai chiều:** bên gửi giới hạn người nhận bằng targetOrigin; bên nhận kiểm tra event.origin, event.source và schema. WindowProxy không đồng nghĩa document bất biến.
3. **Xử lý opaque origin có chủ đích:** wildcard đôi khi cần cho sandboxed/opaque target, nhưng chỉ gửi dữ liệu công khai, không nhạy cảm và không trao quyền. Nếu cần gửi secret, thiết kế origin đích ổn định có thể xác minh.

Khi review một lệnh postMessage, hãy hỏi: **context đích có thể điều hướng không, origin nào sẽ nhận message tại thời điểm giao, payload có secret hoặc cấp quyền không, receiver kiểm tra sender bằng gì, và wildcard có thật sự bắt buộc do opaque origin hay chỉ được dùng cho tiện?** Trả lời rõ các câu hỏi này giúp giữ giao tiếp giữa frame trong đúng ranh giới tin cậy.
