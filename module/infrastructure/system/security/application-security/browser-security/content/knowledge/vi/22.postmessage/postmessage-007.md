# Window reference: tham chiếu cửa sổ và ranh giới giao tiếp giữa các browsing context

Trong trình duyệt, JavaScript có thể giữ tham chiếu đến cửa sổ hiện tại, cửa sổ cha, cửa sổ mở bằng popup hoặc tài liệu đang nằm trong iframe. Những tham chiếu này thường được dùng để điều hướng, kiểm tra trạng thái cửa sổ và trao đổi dữ liệu qua `postMessage`.

Tuy nhiên, một tham chiếu đến cửa sổ không đồng nghĩa với quyền đọc toàn bộ tài liệu của cửa sổ đó. Same-Origin Policy (SOP) giới hạn những thuộc tính và thao tác mà một trang có thể truy cập khi cửa sổ đích ở origin khác. Cần hiểu loại tham chiếu mà trình duyệt trả về, vòng đời của nó khi điều hướng, và cách kết hợp nó với kiểm tra origin khi nhận thông điệp.

Bài học này tập trung vào `Window`, `WindowProxy`, các thuộc tính `parent`, `top`, `opener`, `frames`, `contentWindow` và giá trị trả về của `window.open()`. Đây là nền tảng để thiết kế giao tiếp an toàn giữa trang cha, iframe và popup.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt browsing context, đối tượng Window và WindowProxy.
- Lấy tham chiếu đến cửa sổ cha, cửa sổ trên cùng, iframe và popup.
- Giải thích vì sao tham chiếu cửa sổ khác origin vẫn tồn tại nhưng không cho phép đọc DOM tùy ý.
- Hiểu tham chiếu WindowProxy thay đổi hành vi thế nào khi tài liệu điều hướng.
- Dùng `event.source` kết hợp `event.origin` để xác minh nguồn gửi `postMessage`.
- Ngăn reverse tabnabbing bằng `noopener` và hiểu vai trò của COOP.
- Quản lý vòng đời popup/iframe, trạng thái đóng và lỗi điều hướng.
- Kiểm thử các trường hợp cùng origin, khác origin và opaque origin.

## 1. Browsing context, Window và WindowProxy

### 1.1 Browsing context là gì?

Browsing context là môi trường trình duyệt dùng để hiển thị một tài liệu. Tab chính, popup và mỗi iframe đều có browsing context riêng. Một browsing context có thể điều hướng qua nhiều tài liệu trong suốt vòng đời của nó.

Ví dụ:

~~~text
Tab trình duyệt
  |
  +-- Trang ứng dụng (top-level browsing context)
        |
        +-- Iframe tài liệu (nested browsing context)
        |
        +-- Iframe thanh toán (nested browsing context)

Popup được mở từ trang ứng dụng
  |
  +-- Cửa sổ báo cáo (top-level browsing context riêng)
~~~

Mỗi browsing context có một cửa sổ và một tài liệu hiện tại. Khi browsing context điều hướng, tài liệu hiện tại có thể bị thay thế bằng tài liệu mới.

### 1.2 Window là đối tượng của môi trường trang

Trong JavaScript chạy trong tài liệu, `window` là đối tượng toàn cục của môi trường đó. Nó cung cấp các API như `document`, `location`, `history`, `postMessage()` và các sự kiện của cửa sổ.

Ví dụ:

~~~js
console.log(window.document === document);
console.log(window.location.href);
~~~

`window` đại diện cho môi trường cửa sổ hiện tại từ góc nhìn của tài liệu đang chạy. Tuy nhiên, khi một trang giữ tham chiếu đến cửa sổ khác, đối tượng mà nó quan sát được thường là `WindowProxy`.

### 1.3 WindowProxy là lớp đại diện cho browsing context

`WindowProxy` là đối tượng proxy mà trình duyệt dùng để đại diện cho browsing context. Nó chuyển tiếp thao tác đến Window của tài liệu hiện đang được hiển thị trong browsing context đó, theo các quy tắc truy cập của nền tảng.

Điểm quan trọng:

- Trang cha có thể giữ `iframe.contentWindow` để tham chiếu browsing context của iframe.
- Trang mở popup có thể nhận một tham chiếu WindowProxy từ `window.open()` nếu popup được tạo theo cách giữ quan hệ opener.
- Khi tài liệu trong browsing context điều hướng, tham chiếu WindowProxy thường vẫn đại diện cho browsing context đó và trỏ đến Window của tài liệu hiện tại.
- Quyền truy cập vào thuộc tính của cửa sổ đích vẫn chịu SOP và các cơ chế cô lập khác.

Vì vậy, đừng coi một tham chiếu WindowProxy như bản sao cố định của một đối tượng Window hoặc như quyền truy cập trực tiếp vào toàn bộ DOM.

## 2. Những cách lấy Window reference

Trình duyệt cung cấp nhiều thuộc tính và API để lấy tham chiếu đến browsing context khác nhau.

| API hoặc thuộc tính | Tham chiếu đến | Trường hợp thường dùng |
|---|---|---|
| `window` hoặc `self` | Cửa sổ hiện tại | Dùng API của môi trường hiện tại |
| `window.parent` | Cửa sổ cha của tài liệu hiện tại | Iframe liên hệ trang chứa nó |
| `window.top` | Cửa sổ top-level ở trên cùng | Nhận diện quan hệ lồng nhau hoặc yêu cầu điều hướng có kiểm soát |
| `window.opener` | Cửa sổ đã mở popup hiện tại | Popup trao đổi với trang đã mở nó |
| `window.frames` | Tập hợp các frame con của cửa sổ | Duyệt các browsing context con |
| `iframe.contentWindow` | Cửa sổ của iframe cụ thể | Trang cha giao tiếp với một iframe xác định |
| `window.open()` | Cửa sổ được mở nếu quan hệ được giữ | Trang mở popup và lưu tham chiếu |

### 2.1 window, self và globalThis

Trong môi trường Window của trình duyệt, `window` và `self` thường tham chiếu cùng môi trường cửa sổ. `globalThis` là cách truy cập global object theo chuẩn JavaScript và cũng trỏ đến global object của môi trường trang.

~~~js
console.log(window === self);
console.log(self === globalThis);
~~~

Trong code dùng chung giữa trình duyệt và các môi trường khác, `globalThis` có thể giúp tránh giả định rằng môi trường luôn là Window. Tuy nhiên, để thao tác với browsing context, các thuộc tính như `parent`, `top` và `opener` thuộc API Window.

### 2.2 window.parent và window.top

`window.parent` trả về cửa sổ cha của tài liệu hiện tại. Nếu tài liệu không nằm trong iframe, `parent` chính là cửa sổ hiện tại.

`window.top` trả về cửa sổ top-level trong cây browsing context. Một iframe lồng trong iframe khác vẫn có thể tham chiếu top-level context thông qua `top`, nhưng việc truy cập dữ liệu của nó vẫn chịu SOP.

Ví dụ:

~~~js
const isEmbedded = window.self !== window.top;

if (isEmbedded) {
  console.log("Tài liệu đang chạy bên trong một frame");
}
~~~

Phép so sánh trên có thể cho biết tài liệu có đang ở trong frame hay không trong các trường hợp thông thường. Nó không xác thực danh tính trang cha và không phải biện pháp chống clickjacking. Để ngăn website khác nhúng trang, dùng CSP `frame-ancestors` hoặc X-Frame-Options phù hợp.

Không đọc dữ liệu từ `parent.document` hoặc `top.document` nếu chưa xác định quan hệ origin và quyền truy cập. Khi khác origin, thao tác đọc DOM sẽ bị SOP chặn.

### 2.3 window.opener

`window.opener` là tham chiếu đến cửa sổ đã mở cửa sổ hiện tại bằng một thao tác như `window.open()` hoặc liên kết có target thích hợp.

Ví dụ đơn giản:

~~~js
// Trang cha
const reportWindow = window.open(
  "https://reports.example.test/view",
  "report-window"
);
~~~

Trong popup:

~~~js
if (window.opener) {
  console.log("Popup được mở từ một cửa sổ khác");
}
~~~

`opener` có thể là `null` nếu popup được mở với `noopener`, nếu quan hệ opener bị cắt bởi chính sách cô lập hoặc nếu không có cửa sổ mở nó. Không giả định popup luôn có opener.

### 2.4 iframe.contentWindow

Trang cha có thể lấy tham chiếu đến browsing context của một iframe cụ thể:

~~~html
<iframe
  id="help-frame"
  src="https://help.example.test/embed"
  title="Trợ giúp">
</iframe>
~~~

~~~js
const frame = document.querySelector("#help-frame");
const childWindow = frame.contentWindow;
~~~

`contentWindow` trả về WindowProxy của browsing context trong iframe. Tham chiếu này hữu ích khi gửi `postMessage` hoặc xác nhận `event.source` đến từ đúng iframe.

Nó không đồng nghĩa với quyền đọc `frame.contentWindow.document`. Nếu iframe khác origin hoặc bị sandbox thành opaque origin, việc đọc DOM có thể bị SOP chặn.

### 2.5 window.frames và chỉ số frame

`window.frames` cung cấp tập hợp các browsing context con của cửa sổ. Có thể truy cập frame theo chỉ số hoặc tên trong một số trường hợp:

~~~js
const firstFrame = window.frames[0];
console.log(window.frames.length);
~~~

Trong ứng dụng thực tế, ưu tiên truy vấn phần tử iframe bằng selector và lấy `contentWindow` thay vì dựa vào thứ tự frame. Thứ tự có thể thay đổi khi giao diện thêm, xóa hoặc sắp xếp iframe.

Tên frame cũng không phải danh tính bảo mật. Một trang có thể thay đổi cấu trúc frame hoặc điều hướng browsing context; hãy kiểm tra origin và source khi nhận thông điệp.

## 3. Window reference không đồng nghĩa với quyền truy cập DOM

### 3.1 Same-Origin Policy giới hạn thao tác cross-origin

Giả sử trang cha ở:

`https://app.example.test`

và iframe ở:

`https://docs.example.test`

Hai URL khác hostname nên khác origin. Trang cha có thể giữ `iframe.contentWindow`, nhưng không được đọc tùy ý:

~~~js
const frame = document.querySelector("#docs-frame");

// Tham chiếu cửa sổ có thể lấy được.
const childWindow = frame.contentWindow;

// Đọc DOM khác origin sẽ bị SOP chặn.
console.log(childWindow.document.body.textContent);
~~~

Thao tác đọc DOM có thể ném SecurityError. Đây là hành vi bảo vệ của trình duyệt, không phải lỗi cú pháp JavaScript.

### 3.2 Một số thao tác cross-origin được cho phép

Trình duyệt cho phép một tập thao tác hạn chế giữa các WindowProxy khác origin. Các ví dụ quan trọng:

- Gửi thông điệp bằng `postMessage()`.
- Kiểm tra một số trạng thái như `closed`.
- Gọi một số thao tác cửa sổ như `focus()` hoặc `blur()` trong giới hạn của trình duyệt.
- Đóng cửa sổ bằng `close()` khi điều kiện cho phép.
- Điều hướng một số cửa sổ bằng cách gán vào `location`, chịu các quy tắc bảo vệ riêng.

Không nên dựa vào danh sách này như hợp đồng đầy đủ cho mọi trình duyệt và mọi loại browsing context. Quyền truy cập cụ thể được định nghĩa bởi nền tảng web và có thể khác theo sandbox, COOP và trạng thái cửa sổ.

### 3.3 location là trường hợp đặc biệt

Với một cửa sổ khác origin, trang có thể được phép điều hướng nó bằng cách gán location trong một số ngữ cảnh:

~~~js
childWindow.location = "https://app.example.test/next";
~~~

Nhưng việc đọc URL hiện tại của cửa sổ khác origin thường bị chặn:

~~~js
console.log(childWindow.location.href); // Có thể ném SecurityError
~~~

Đây là lý do SOP không nên được mô tả đơn giản là “không thể làm gì với cửa sổ khác origin”. Trình duyệt cho phép một số hành động có chủ đích, trong khi hạn chế việc đọc dữ liệu.

Điều hướng một cửa sổ khác origin cũng có thể gây tác động bảo mật. Đừng để dữ liệu không tin cậy quyết định URL điều hướng của popup hoặc trang cha.

## 4. WindowProxy tồn tại qua điều hướng như thế nào?

Một browsing context có thể tải nhiều tài liệu trong suốt vòng đời của nó. Ví dụ, iframe ban đầu tải trang A, sau đó điều hướng sang trang B. Tham chiếu WindowProxy lấy từ `contentWindow` thường vẫn đại diện cho browsing context của iframe đó.

~~~js
const frame = document.querySelector("#child-frame");
const childWindow = frame.contentWindow;

// Sau đó iframe điều hướng sang một tài liệu khác.
frame.src = "https://next.example.test/page";

// childWindow vẫn là tham chiếu đến browsing context của iframe.
~~~

Điều này có hai hệ quả:

1. Tham chiếu không tự chứng minh tài liệu hiện tại vẫn là trang ban đầu.
2. Một thông điệp gửi sau khi iframe điều hướng có thể đến tài liệu mới nếu target origin không được giới hạn đúng.

Nếu gửi dữ liệu nhạy cảm, dùng `targetOrigin` chính xác:

~~~js
childWindow.postMessage(
  { type: "SESSION_READY" },
  "https://docs.example.test"
);
~~~

Nếu iframe đã điều hướng sang origin khác, trình duyệt không gửi thông điệp đến tài liệu mới vì origin đích không còn khớp.

Không dùng `"*"` cho dữ liệu nhạy cảm chỉ vì WindowProxy đã được lấy từ một iframe mà ứng dụng tin cậy lúc ban đầu.

## 5. Dùng Window reference với postMessage

`postMessage` là cơ chế chuẩn để trao đổi dữ liệu giữa các browsing context khi SOP ngăn truy cập trực tiếp vào DOM.

### 5.1 Trang cha gửi thông điệp đến iframe

~~~js
const frame = document.querySelector("#payment-frame");
const paymentWindow = frame.contentWindow;
const PAYMENT_ORIGIN = "https://pay.example.test";

paymentWindow.postMessage(
  {
    type: "INITIALIZE",
    version: 1,
    requestId: "checkout-42"
  },
  PAYMENT_ORIGIN
);
~~~

Tham số target origin là một lớp bảo vệ quan trọng. Trình duyệt chỉ chuyển thông điệp nếu origin của tài liệu nhận tại thời điểm giao thông điệp phù hợp với giá trị này.

### 5.2 Iframe xác minh cửa sổ cha

Trong tài liệu con:

~~~js
const PARENT_ORIGIN = "https://app.example.test";

window.addEventListener("message", event => {
  if (event.origin !== PARENT_ORIGIN) return;
  if (event.source !== window.parent) return;

  const message = event.data;

  if (
    !message ||
    typeof message !== "object" ||
    message.type !== "INITIALIZE" ||
    message.version !== 1 ||
    typeof message.requestId !== "string"
  ) {
    return;
  }

  initializePayment(message.requestId);
});
~~~

`event.source` là tham chiếu đến cửa sổ đã gửi thông điệp trong trường hợp thông điệp đến từ một Window. So sánh với `window.parent` giúp xác nhận thông điệp đến từ browsing context cha dự kiến.

`event.origin` cho biết origin của bên gửi tại thời điểm gửi thông điệp. Cần kiểm tra origin chính xác, bao gồm scheme, hostname và port.

### 5.3 Trang cha xác minh iframe cụ thể

Trong trang cha:

~~~js
const frame = document.querySelector("#payment-frame");
const PAYMENT_ORIGIN = "https://pay.example.test";

window.addEventListener("message", event => {
  if (event.origin !== PAYMENT_ORIGIN) return;
  if (event.source !== frame.contentWindow) return;

  const message = event.data;

  if (
    !message ||
    typeof message !== "object" ||
    message.type !== "PAYMENT_COMPLETE" ||
    message.version !== 1 ||
    typeof message.transactionId !== "string"
  ) {
    return;
  }

  markPaymentComplete(message.transactionId);
});
~~~

Chỉ kiểm tra origin có thể chưa đủ nếu trang có nhiều iframe cùng origin. So sánh `event.source` với `contentWindow` của iframe cụ thể giúp phân biệt browsing context gửi thông điệp.

Dù vậy, source và origin không thay thế xác thực nghiệp vụ. Ví dụ, trang cha vẫn cần kiểm tra trạng thái giao dịch từ máy chủ trước khi đánh dấu đơn hàng đã thanh toán. Không tin một thông điệp từ iframe như bằng chứng duy nhất cho hành động có giá trị.

## 6. Phân biệt origin, source và targetOrigin

Ba khái niệm này giải quyết ba câu hỏi khác nhau:

| Giá trị | Câu hỏi | Cách dùng |
|---|---|---|
| `event.origin` | Thông điệp được gửi từ origin nào? | So sánh với origin dự kiến |
| `event.source` | Browsing context nào gửi thông điệp? | So sánh với WindowProxy đã biết |
| `targetOrigin` | Origin nào được phép nhận thông điệp? | Truyền origin đích chính xác khi gửi |

Ví dụ:

~~~js
const expectedOrigin = "https://widget.example.test";
const expectedWindow = frame.contentWindow;

window.addEventListener("message", event => {
  if (event.origin !== expectedOrigin) return;
  if (event.source !== expectedWindow) return;

  processWidgetMessage(event.data);
});
~~~

Không dùng `event.origin` như một chuỗi chứa tên miền. So sánh origin chính xác:

~~~js
// Không an toàn: so khớp chuỗi con.
if (event.origin.includes("example.test")) {
  processWidgetMessage(event.data);
}
~~~

Điều kiện trên có thể chấp nhận origin giả có hostname khác nhưng chứa chuỗi mong muốn ở phần khác. Hãy dùng giá trị origin cố định hoặc allowlist origin đã phân tích.

## 7. Popup và reverse tabnabbing

### 7.1 Popup có thể giữ tham chiếu opener

Khi trang A mở trang B bằng `window.open()` mà không dùng `noopener`, trang B có thể nhận tham chiếu đến A qua `window.opener`.

~~~js
// Trang A
const popup = window.open(
  "https://external.example.test",
  "_blank"
);
~~~

Trang B có thể dùng `window.opener` để truy cập một số khả năng hạn chế của cửa sổ mở nó. Dù khác origin, một số thao tác điều hướng vẫn có thể được cho phép.

### 7.2 Reverse tabnabbing

Reverse tabnabbing xảy ra khi trang được mở dùng quan hệ opener để điều hướng tab gốc đến một trang giả mạo. Trang mở có thể không hề biết tab của mình đã bị thay đổi.

Ví dụ minh họa nguy cơ trong trang popup:

~~~js
if (window.opener) {
  window.opener.location = "https://lookalike.example.test/login";
}
~~~

SOP có thể ngăn popup đọc DOM của trang cha, nhưng không nên giả định nó chặn mọi hành động điều hướng được cho phép. Vì vậy, nếu không cần opener, hãy cắt quan hệ này ngay khi mở cửa sổ.

### 7.3 Dùng rel=noopener cho liên kết mở tab mới

~~~html
<a
  href="https://external.example.test"
  target="_blank"
  rel="noopener">
  Mở trang bên ngoài
</a>
~~~

`noopener` ngăn trang đích nhận tham chiếu opener. Các trình duyệt hiện đại cũng áp dụng hành vi noopener mặc định trong nhiều trường hợp với `target="_blank"`, nhưng khai báo tường minh vẫn giúp thể hiện ý định và hỗ trợ các môi trường cũ hơn.

Nếu không muốn gửi cả referrer, có thể dùng:

~~~html
<a
  href="https://external.example.test"
  target="_blank"
  rel="noopener noreferrer">
  Mở trang bên ngoài
</a>
~~~

`noreferrer` cũng làm mất referrer và có tác dụng như noopener.

### 7.4 Dùng noopener với window.open

~~~js
const popup = window.open(
  "https://external.example.test",
  "_blank",
  "noopener"
);
~~~

Khi dùng tính năng noopener, giá trị trả về của `window.open()` có thể là `null` dù cửa sổ đã được mở thành công. Không dùng việc giá trị trả về là null để kết luận chắc chắn popup bị chặn.

Nếu ứng dụng cần tham chiếu popup để trao đổi dữ liệu, hãy cân nhắc kiến trúc giao tiếp trước khi bỏ noopener. Chỉ giữ opener khi có nhu cầu rõ ràng, xác minh origin/source, giới hạn thông điệp và đánh giá khả năng điều hướng. Không mở opener chỉ để tiện gọi một hàm.

## 8. COOP và việc cắt quan hệ giữa các cửa sổ

Cross-Origin-Opener-Policy (COOP) là response header giúp kiểm soát việc tài liệu top-level chia sẻ browsing context group với cửa sổ khác. Nó có thể cô lập trang khỏi các cửa sổ cross-origin và làm thay đổi quan hệ opener.

Một số giá trị thường gặp:

| Giá trị | Ý nghĩa khái quát |
|---|---|
| `unsafe-none` | Hành vi mặc định phổ biến, cho phép nhóm browsing context được chia sẻ theo quy tắc nền tảng |
| `same-origin` | Cô lập tài liệu top-level khỏi các tài liệu khác origin trong browsing context group |
| `same-origin-allow-popups` | Cho phép tài liệu cùng origin giữ quan hệ với một số popup có chính sách `unsafe-none`, hữu ích cho luồng popup như OAuth hoặc thanh toán |

Ví dụ:

~~~http
Cross-Origin-Opener-Policy: same-origin
~~~

COOP có thể khiến quan hệ opener giữa các trang bị cắt khi chúng không thỏa điều kiện cùng nhóm. Trong một số tình huống, tham chiếu popup mà trang mở giữ được có thể biểu hiện như đã đóng hoặc không còn truy cập được như trước.

Với `same-origin`, popup khác origin thường được đặt vào browsing context group khác và quan hệ opener bị cắt. `same-origin-allow-popups` được thiết kế để giữ một số quan hệ với popup không áp dụng COOP nghiêm ngặt, nhưng vẫn cần kiểm thử với nhà cung cấp và luồng điều hướng thực tế.

COOP thường được dùng cùng các header bảo mật khác để tạo môi trường cô lập mạnh hơn. Tuy nhiên, cần kiểm thử luồng đăng nhập liên kết, popup thanh toán, OAuth và các tích hợp cần quay lại cửa sổ mở.

### 8.1 COOP khác noopener thế nào?

- `noopener` là lựa chọn tại thời điểm mở liên kết hoặc cửa sổ để ngăn quan hệ opener cho lần mở đó.
- COOP là chính sách response của tài liệu top-level, ảnh hưởng cách trình duyệt nhóm các browsing context.
- Cả hai có thể làm mất khả năng truy cập opener, nhưng phạm vi và tác động đến ứng dụng khác nhau.

Không dùng COOP như một cách sửa nhanh mà chưa kiểm tra luồng popup. Ngược lại, nếu ứng dụng không cần quan hệ opener, hãy dùng noopener ở điểm mở cửa sổ và đánh giá COOP ở cấp ứng dụng.

## 9. Window reference có thể bị đóng hoặc mất hiệu lực

Một cửa sổ có thể bị người dùng đóng, ứng dụng đóng hoặc trình duyệt tách khỏi quan hệ ban đầu. Trước khi gửi thông điệp hoặc thao tác, có thể kiểm tra trạng thái:

~~~js
if (popup && !popup.closed) {
  popup.postMessage(
    { type: "PING" },
    "https://reports.example.test"
  );
}
~~~

Một số lưu ý:

- `window.open()` có thể trả `null` nếu popup bị chặn hoặc nếu dùng noopener.
- `closed` cho biết browsing context đã đóng theo góc nhìn của tham chiếu.
- Gọi `close()` chỉ thành công trong những trường hợp được trình duyệt cho phép, thường là cửa sổ do script mở.
- Popup có thể điều hướng sang tài liệu khác trong cùng browsing context.
- Iframe có thể được thay src hoặc bị gỡ khỏi DOM.
- COOP có thể cắt quan hệ giữa các browsing context.

Không dùng trạng thái `closed` để xác thực danh tính hoặc quyền. Nó chỉ hữu ích để tránh thao tác trên cửa sổ đã đóng.

## 10. Sự kiện load không chứng minh tài liệu đáng tin

Iframe phát sự kiện `load` khi tài liệu được tải hoặc điều hướng hoàn tất theo cách trình duyệt báo. Tuy nhiên, sự kiện này không chứng minh tài liệu đến từ origin dự kiến, không chứng minh ứng dụng con đã sẵn sàng xử lý giao thức và không chứng minh nội dung là an toàn.

Ví dụ:

~~~js
const frame = document.querySelector("#widget-frame");

frame.addEventListener("load", () => {
  console.log("Iframe vừa tải hoặc điều hướng");
});
~~~

Nếu cần biết ứng dụng con đã khởi tạo xong, hãy thiết kế handshake bằng `postMessage`:

1. Trang con gửi `READY` sau khi hoàn tất khởi tạo.
2. Trang cha kiểm tra `event.origin` và `event.source`.
3. Trang cha xác minh phiên bản giao thức và các trường bắt buộc.
4. Hai bên mới bắt đầu trao đổi thông điệp nghiệp vụ.

Không coi `load` hoặc việc iframe có tồn tại là bằng chứng xác thực. Nếu iframe điều hướng nhiều lần, mỗi lần cần tuân theo quy trình xác minh phù hợp.

## 11. Opaque origin và Window reference

Một số tài liệu có opaque origin, ví dụ iframe sandbox không có `allow-same-origin`. Origin của tài liệu như vậy thường được biểu diễn trong MessageEvent bằng chuỗi `"null"`.

Không coi `event.origin === "null"` là xác thực người gửi. Nhiều tài liệu opaque origin khác nhau có thể có giá trị origin này.

Nếu ứng dụng cần giao tiếp với iframe opaque origin:

- So sánh `event.source` với đúng `iframe.contentWindow` đã tạo.
- Dùng schema thông điệp hẹp, kiểm tra mọi trường.
- Không gửi bí mật nếu không có cơ chế xác thực bổ sung.
- Có thể dùng capability ngẫu nhiên, khó đoán, thời hạn ngắn và giới hạn hành động.
- Tránh cấp cho iframe quyền hoặc dữ liệu vượt quá chức năng cần thiết.

Khi có thể, dùng một origin riêng ổn định cho nội dung con. Điều đó giúp xác minh origin rõ ràng hơn và dễ giới hạn nguồn qua CSP.

## 12. Các lỗi thường gặp khi dùng Window reference

### 12.1 Nghĩ rằng lấy được reference là đọc được DOM

`iframe.contentWindow` có thể lấy được ngay cả khi iframe khác origin. Điều đó không cấp quyền đọc `document` hoặc DOM con.

### 12.2 Chỉ kiểm tra event.source

Một browsing context có thể điều hướng sau khi tham chiếu được lưu. Hãy kiểm tra cả `event.source` và `event.origin`, đồng thời dùng targetOrigin chính xác khi gửi dữ liệu.

### 12.3 Chỉ kiểm tra event.origin

Một trang có thể có nhiều iframe cùng origin. So sánh source với `contentWindow` của iframe cụ thể giúp xác nhận đúng browsing context.

### 12.4 Dùng targetOrigin là dấu sao

Nếu iframe hoặc popup điều hướng trước khi thông điệp được gửi, dữ liệu có thể đến tài liệu khác. Dùng origin đích chính xác khi có thể.

### 12.5 Tin window.opener từ trang bên ngoài

Trang được mở có thể dùng opener để điều hướng cửa sổ gốc. Dùng noopener khi không cần quan hệ opener.

### 12.6 Dùng tên hoặc chỉ số frame như danh tính

Tên frame và thứ tự trong `window.frames` có thể thay đổi. Dùng tham chiếu từ phần tử iframe cụ thể và kiểm tra origin.

### 12.7 Dựa vào load để xác nhận ứng dụng con sẵn sàng

Sự kiện load không xác thực origin hoặc giao thức. Dùng handshake postMessage có xác minh.

### 12.8 Xem window reference như token quyền

Tham chiếu cửa sổ chỉ định browsing context. Nó không tự cấp quyền nghiệp vụ như xem đơn hàng, xác nhận thanh toán hoặc thay đổi tài khoản. Máy chủ vẫn phải xác thực và kiểm tra quyền cho hành động nhạy cảm.

## 13. Ví dụ hoàn chỉnh: giao tiếp với một iframe xác định

Trang cha có iframe:

~~~html
<iframe
  id="support-frame"
  src="https://support.example.test/embed"
  title="Trợ giúp">
</iframe>
~~~

Mã trang cha:

~~~js
const frame = document.querySelector("#support-frame");
const SUPPORT_ORIGIN = "https://support.example.test";
const PROTOCOL_VERSION = 1;

function sendInit() {
  const childWindow = frame.contentWindow;

  if (!childWindow) {
    throw new Error("Iframe browsing context is unavailable");
  }

  childWindow.postMessage(
    {
      type: "INIT",
      version: PROTOCOL_VERSION
    },
    SUPPORT_ORIGIN
  );
}

window.addEventListener("message", event => {
  if (event.origin !== SUPPORT_ORIGIN) return;
  if (event.source !== frame.contentWindow) return;

  const data = event.data;

  if (
    !data ||
    typeof data !== "object" ||
    data.version !== PROTOCOL_VERSION
  ) {
    return;
  }

  if (data.type === "READY") {
    enableSupportActions();
    return;
  }

  if (
    data.type === "OPEN_TICKET" &&
    typeof data.ticketId === "string"
  ) {
    showTicketReference(data.ticketId);
  }
});

frame.addEventListener("load", () => {
  // Load chỉ báo rằng frame vừa điều hướng/tải.
  // Handshake READY mới xác nhận giao thức ứng dụng đã sẵn sàng.
  sendInit();
});
~~~

Trong iframe:

~~~js
const PARENT_ORIGIN = "https://app.example.test";
const PROTOCOL_VERSION = 1;

window.addEventListener("message", event => {
  if (event.origin !== PARENT_ORIGIN) return;
  if (event.source !== window.parent) return;

  const data = event.data;

  if (
    !data ||
    typeof data !== "object" ||
    data.type !== "INIT" ||
    data.version !== PROTOCOL_VERSION
  ) {
    return;
  }

  window.parent.postMessage(
    {
      type: "READY",
      version: PROTOCOL_VERSION
    },
    PARENT_ORIGIN
  );
});
~~~

Ví dụ này minh họa:

- Trang cha giữ tham chiếu đến đúng iframe.
- Hai bên dùng origin cụ thể làm targetOrigin.
- Bên nhận kiểm tra origin và source.
- Dữ liệu được kiểm tra type và version trước khi xử lý.
- Sự kiện load chỉ kích hoạt việc gửi INIT; thông điệp READY là handshake ở tầng ứng dụng.

Trong sản phẩm thực tế, cần xử lý việc iframe tải lại, timeout, nhiều lần READY và trạng thái kết nối. Hành động nhạy cảm như xác nhận thanh toán hoặc cấp quyền phải được kiểm tra lại ở máy chủ.

## 14. Kiểm thử Window reference trong DevTools

### 14.1 Kiểm tra các loại reference

Trong Console, thử:

~~~js
({
  self: window.self === window,
  parentIsSelf: window.parent === window,
  topIsSelf: window.top === window,
  openerExists: window.opener !== null,
  frameCount: window.frames.length
});
~~~

Ghi lại kết quả khi trang chạy trong tab chính, iframe và popup.

### 14.2 Kiểm tra cross-origin access

Tạo một iframe ở origin khác. Thử lấy `contentWindow`, sau đó thử đọc `contentDocument` hoặc `document`. Quan sát việc lấy reference thành công và thao tác đọc DOM bị chặn.

### 14.3 Kiểm tra WindowProxy sau điều hướng

Lưu `iframe.contentWindow` vào biến, thay đổi `iframe.src` và kiểm tra lại so sánh tham chiếu. Quan sát rằng tham chiếu đại diện cho browsing context, trong khi tài liệu hiện tại đã thay đổi.

### 14.4 Kiểm tra postMessage

Gửi thông điệp từ đúng iframe và từ một iframe khác cùng origin. Xác nhận kiểm tra origin đơn lẻ có thể không phân biệt hai frame, còn so sánh `event.source` giúp nhận diện browsing context dự kiến.

### 14.5 Kiểm tra noopener

Mở một liên kết lab với `target="_blank"` và `rel="noopener"`. Trong trang đích, kiểm tra `window.opener`. Giá trị cần là `null` khi quan hệ opener đã bị cắt.

Không thử reverse tabnabbing trên website thật. Chỉ dùng trang lab do bạn kiểm soát.

## 15. Bài thực hành

Thực hiện với các trang lab do bạn kiểm soát, không dùng thông tin đăng nhập hoặc dữ liệu thật.

### Bài 1: Bản đồ browsing context

Tạo trang cha có hai iframe và một popup. In ra các giá trị `parent`, `top`, `opener`, `frames.length` và `contentWindow`. Vẽ sơ đồ browsing context và ghi lại reference nào trỏ đến đâu.

### Bài 2: So sánh cùng origin và khác origin

Đặt trang cha và iframe lần lượt cùng origin rồi khác origin. Kiểm tra việc lấy reference, đọc DOM và gửi postMessage. Ghi lại thao tác nào được phép và thao tác nào bị SOP chặn.

### Bài 3: Điều hướng trong khi giữ reference

Lưu `iframe.contentWindow`, điều hướng iframe sang một trang lab khác và gửi thông điệp với targetOrigin ban đầu. Xác nhận thông điệp không được chuyển đến tài liệu mới nếu origin không còn khớp.

### Bài 4: Phòng chống reverse tabnabbing

Mở trang lab bằng liên kết target blank có và không có noopener. Quan sát `window.opener` trong trang đích. Giải thích vì sao SOP không nên được coi là biện pháp thay thế noopener.

### Bài 5: Kiểm tra source và origin

Tạo hai iframe cùng origin. Gửi thông điệp từ cả hai đến trang cha. Chỉ chấp nhận thông điệp từ iframe được chỉ định bằng cách kiểm tra cả `event.origin` và `event.source`.

### Bài 6: Kiểm tra COOP

Dựng hai trang lab với các response header COOP khác nhau. Mở popup từ trang chính và quan sát quan hệ opener cùng trạng thái tham chiếu. Ghi lại tác động đến luồng ứng dụng cần popup.

## 16. Checklist review Window reference

- [ ] Đã xác định browsing context mà mỗi reference đại diện.
- [ ] Không nhầm WindowProxy với quyền đọc toàn bộ Window hoặc Document.
- [ ] Đã hiểu giới hạn SOP khi cửa sổ khác origin.
- [ ] Không dùng tên frame hoặc chỉ số frame làm danh tính bảo mật.
- [ ] Với postMessage, đã kiểm tra event.origin và event.source.
- [ ] Khi gửi thông điệp, dùng targetOrigin chính xác nếu biết origin đích.
- [ ] Không gửi dữ liệu nhạy cảm bằng targetOrigin là dấu sao.
- [ ] Đã xem xét khả năng browsing context điều hướng sau khi reference được lưu.
- [ ] Đã kiểm tra popup có thể bị chặn, đóng hoặc bị cắt quan hệ opener.
- [ ] Liên kết mở tab mới dùng noopener khi không cần opener.
- [ ] Đã đánh giá COOP và ảnh hưởng đến popup/SSO.
- [ ] Không dùng load event làm bằng chứng xác thực tài liệu con.
- [ ] Không coi Window reference là quyền nghiệp vụ.
- [ ] Hành động nhạy cảm vẫn được xác thực và phân quyền ở máy chủ.

## 17. Câu hỏi tự kiểm tra

**1. Browsing context là gì?**

Đó là môi trường trình duyệt hiển thị một tài liệu, ví dụ tab chính, popup hoặc iframe.

**2. WindowProxy dùng để làm gì?**

Nó đại diện cho browsing context và chuyển tiếp thao tác đến Window của tài liệu hiện tại theo các quy tắc truy cập của trình duyệt.

**3. Vì sao có thể lấy iframe.contentWindow nhưng không đọc được contentWindow.document?**

Vì việc lấy tham chiếu browsing context được cho phép, còn đọc DOM của tài liệu khác origin bị SOP hạn chế.

**4. window.parent và window.top khác nhau thế nào?**

parent là cửa sổ cha trực tiếp; top là cửa sổ top-level ở trên cùng của cây browsing context.

**5. event.source và event.origin khác nhau thế nào?**

source chỉ browsing context gửi thông điệp; origin cho biết origin của tài liệu gửi tại thời điểm gửi.

**6. Vì sao cần targetOrigin chính xác?**

Để trình duyệt chỉ chuyển thông điệp đến tài liệu có origin dự kiến, kể cả khi browsing context đã điều hướng.

**7. Reverse tabnabbing là gì?**

Là tình huống trang được mở dùng quan hệ opener để điều hướng tab gốc đến trang giả mạo.

**8. noopener có tác dụng gì?**

Nó ngăn trang đích nhận tham chiếu opener, giảm nguy cơ trang đích điều hướng cửa sổ mở nó.

**9. COOP có thể ảnh hưởng popup như thế nào?**

COOP có thể tách các browsing context vào nhóm khác nhau và cắt quan hệ opener, làm thay đổi khả năng giao tiếp giữa popup và trang mở.

**10. Window reference có chứng minh người gửi được quyền thực hiện hành động nghiệp vụ không?**

Không. Reference chỉ nhận diện browsing context. Máy chủ vẫn phải xác thực người dùng và kiểm tra quyền đối với hành động nhạy cảm.

## Ghi nhớ

Window reference cho phép một trang nhận diện browsing context khác, nhưng quyền truy cập vào tài liệu vẫn do SOP, sandbox và chính sách cô lập quyết định. Với giao tiếp giữa iframe hoặc popup, hãy kết hợp tham chiếu source với kiểm tra origin và giao thức thông điệp. Nếu không cần quan hệ opener, hãy dùng noopener; với hành động nghiệp vụ, luôn xác thực và phân quyền ở máy chủ.
