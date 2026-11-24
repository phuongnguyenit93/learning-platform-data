# Iframe security: bảo vệ ranh giới giữa trang cha và tài liệu được nhúng

Iframe cho phép một trang hiển thị tài liệu HTML khác bên trong vùng nội dung của mình. Cơ chế này hữu ích cho trình xem tài liệu, bản đồ, thanh toán, video và các ứng dụng tích hợp. Tuy nhiên, mỗi iframe tạo thêm một tài liệu có vòng đời, origin, quyền truy cập và chính sách bảo mật riêng. Nếu cấu hình thiếu chặt chẽ, nội dung nhúng có thể điều hướng trang cha, mở cửa sổ mới, gửi thông điệp sai mục đích hoặc làm lộ dữ liệu.

Bảo vệ iframe cần nhiều lớp phối hợp: Same-Origin Policy (SOP), thuộc tính `sandbox`, Permissions Policy qua thuộc tính `allow`, CSP `frame-src` và `frame-ancestors`, kiểm soát `postMessage`, cùng chính sách cookie và storage. Không có một thuộc tính đơn lẻ nào thay thế được toàn bộ các lớp này.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích iframe tạo ra tài liệu và ranh giới origin riêng như thế nào.
- Phân biệt quyền của trang cha với quyền của tài liệu con.
- Chọn các token `sandbox` tối thiểu cho từng trường hợp sử dụng.
- Dùng Permissions Policy để giới hạn camera, microphone, geolocation và các tính năng khác.
- Phân biệt CSP `frame-src` với `frame-ancestors` và X-Frame-Options.
- Trao đổi dữ liệu qua `postMessage` có kiểm tra origin, source và cấu trúc thông điệp.
- Đánh giá tác động của cookie, storage, referrer và clickjacking.
- Kiểm thử cấu hình iframe trong DevTools và xây dựng checklist review.

## 1. Iframe tạo ra một tài liệu lồng bên trong

Một iframe là phần tử nhúng một browsing context có tài liệu riêng. Ví dụ:

~~~html
<iframe
  src="https://docs.example.test/viewer"
  title="Trình xem tài liệu">
</iframe>
~~~

Trang chứa iframe được gọi là trang cha (parent hoặc embedding document). Tài liệu được tải trong iframe là tài liệu con (child hoặc embedded document).

Hai tài liệu có thể:

- Cùng origin, ví dụ cùng scheme, hostname và port.
- Khác origin, ví dụ một tài liệu từ `app.example.test` và một tài liệu từ `docs.example.test`.
- Có nguồn đặc biệt như `srcdoc`, `data:` hoặc tài liệu bị sandbox tạo thành opaque origin.

Iframe không phải một vùng HTML đơn giản nằm trong DOM của trang cha. Nó có document, window, JavaScript context và vòng đời điều hướng riêng. Trang cha có thể giữ tham chiếu đến phần tử iframe và `contentWindow`, nhưng quyền đọc hoặc sửa tài liệu con còn phụ thuộc chính sách cùng origin và sandbox.

### 1.1 Origin là gì?

Origin được xác định bởi bộ ba:

~~~text
scheme + hostname + port
~~~

Ví dụ:

| URL | So sánh với `https://app.example.test` |
|---|---|
| `https://app.example.test/home` | Cùng origin |
| `https://app.example.test:443/profile` | Cùng origin vì 443 là port mặc định của HTTPS |
| `http://app.example.test` | Khác origin vì scheme khác |
| `https://docs.example.test` | Khác origin vì hostname khác |
| `https://app.example.test:8443` | Khác origin vì port khác |

SOP giới hạn cách một tài liệu có thể đọc hoặc thao tác dữ liệu của tài liệu ở origin khác. Ví dụ, trang cha khác origin thường không thể đọc `iframe.contentDocument` hoặc truy cập các phần tử DOM bên trong. Trình duyệt vẫn cho phép một số thao tác được thiết kế rõ ràng như điều hướng iframe, nhúng tài liệu và gửi thông điệp qua `postMessage`.

SOP không có nghĩa hai tài liệu khác origin hoàn toàn không thể liên lạc. Nó giới hạn quyền truy cập trực tiếp; các API giao tiếp được thiết kế riêng vẫn có thể hoạt động.

### 1.2 Trang cha và tài liệu con có quyền khác nhau

| Hành động | Cùng origin, không sandbox | Khác origin, không sandbox |
|---|---|---|
| Trang cha đọc DOM con | Thường được phép | Bị SOP chặn |
| Trang cha giữ `contentWindow` | Được phép | Được phép |
| Trang cha điều hướng iframe | Được phép theo quy tắc điều hướng | Được phép theo quy tắc điều hướng |
| Tài liệu con gửi `postMessage` | Được phép | Được phép |
| Tài liệu con đọc DOM cha | Được phép theo quyền cùng origin | Bị SOP chặn |

Sandbox có thể thu hẹp quyền thêm nữa, kể cả khi hai tài liệu cùng origin. Vì vậy, khi review iframe, hãy xác định cả origin lẫn token sandbox đang bật.

## 2. Ranh giới bảo mật và mô hình đe dọa

Một iframe có thể đến từ máy chủ của chính tổ chức, một nhà cung cấp bên ngoài hoặc nội dung do người dùng tải lên. Mỗi nguồn có mức tin cậy khác nhau.

Một số mối đe dọa thường gặp:

- Nội dung con chạy JavaScript ngoài dự kiến và cố truy cập trang cha.
- Iframe điều hướng top-level page sang một trang giả mạo.
- Nội dung con mở popup hoặc gửi biểu mẫu mà người dùng không nhận biết.
- Iframe được cấp quyền camera, microphone, geolocation hoặc fullscreen quá rộng.
- Thông điệp `postMessage` giả mạo khiến trang cha thực hiện hành động nhạy cảm.
- Trang nhạy cảm bị nhúng trên website khác để thực hiện clickjacking.
- Dữ liệu đăng nhập hoặc trạng thái người dùng bị ảnh hưởng bởi chính sách cookie và storage của trình duyệt.
- URL iframe được lấy từ dữ liệu không tin cậy, cho phép tải nội dung ngoài danh sách được duyệt.

Cần phân biệt hai hướng kiểm soát:

1. Trang cha quyết định tài liệu nào được phép nhúng vào nó và quyền nào được cấp cho iframe.
2. Tài liệu con quyết định những trang cha nào được phép nhúng chính nó.

CSP `frame-src` của trang cha và CSP `frame-ancestors` của tài liệu con giải quyết hai câu hỏi khác nhau.

## 3. Dùng sandbox để giới hạn hành vi iframe

Thuộc tính `sandbox` áp dụng một tập hạn chế cho tài liệu được nhúng. Khi có `sandbox` mà không có token cho phép, trình duyệt áp dụng các hạn chế như:

- Không cho script trong tài liệu chạy.
- Đưa tài liệu vào một opaque origin, trừ khi có token `allow-same-origin`.
- Chặn gửi biểu mẫu.
- Hạn chế popup và điều hướng top-level.
- Hạn chế một số API, tương tác và tính năng khác.

Ví dụ khóa chặt:

~~~html
<iframe
  src="https://untrusted.example.test/widget"
  title="Widget bên ngoài"
  sandbox>
</iframe>
~~~

Cấu hình này phù hợp khi tài liệu chỉ cần hiển thị nội dung tĩnh. Nếu widget cần script hoặc biểu mẫu, hãy cấp đúng token cần thiết sau khi hiểu rõ tác động.

### 3.1 Token sandbox phổ biến

Sandbox bắt đầu ở trạng thái hạn chế. Mỗi token trong thuộc tính là một ngoại lệ cho một hành vi cụ thể.

| Token | Quyền được nới lỏng | Cân nhắc bảo mật |
|---|---|---|
| `allow-scripts` | Cho phép script trong tài liệu con chạy | Script có thể thao tác nội dung của chính tài liệu và gửi thông điệp |
| `allow-same-origin` | Giữ origin thật của tài liệu thay vì opaque origin | Có thể cho phép truy cập cookie/storage theo chính sách trình duyệt và quyền cùng origin |
| `allow-forms` | Cho phép gửi form | Kiểm tra đích gửi và hành động mà form có thể thực hiện |
| `allow-popups` | Cho phép mở popup hoặc tab mới | Popup có thể bị dùng để lừa người dùng |
| `allow-popups-to-escape-sandbox` | Popup mới không kế thừa sandbox của iframe | Chỉ bật khi popup cần chạy độc lập và đích đến đã được kiểm soát |
| `allow-top-navigation` | Cho phép điều hướng trang top-level | Có thể thay thế toàn bộ trang cha |
| `allow-top-navigation-by-user-activation` | Cho phép điều hướng top-level sau kích hoạt người dùng | Hạn chế hơn token điều hướng tổng quát |
| `allow-downloads` | Cho phép tải xuống | Cần đánh giá nội dung và hành vi tải file |
| `allow-modals` | Cho phép hộp thoại modal như alert/confirm/prompt | Có thể gây gián đoạn hoặc lừa người dùng |
| `allow-pointer-lock` | Cho phép pointer lock | Chỉ cấp cho ứng dụng thực sự cần điều khiển con trỏ |
| `allow-presentation` | Cho phép dùng Presentation API | Cấp theo nhu cầu trình chiếu |
| `allow-orientation-lock` | Cho phép khóa hướng màn hình | Chủ yếu liên quan ứng dụng toàn màn hình trên thiết bị phù hợp |
| `allow-storage-access-by-user-activation` | Cho phép yêu cầu Storage Access API sau kích hoạt người dùng | Không tự động bỏ qua mọi chính sách cookie bên thứ ba |

Các token và mức hỗ trợ có thể khác nhau theo phiên bản trình duyệt. Hãy kiểm tra tài liệu nền tảng mà sản phẩm hỗ trợ, đặc biệt với các token ít dùng.

### 3.2 Chọn token tối thiểu

Giả sử widget cần JavaScript để render và cần gửi form, nhưng không cần popup hay điều hướng trang cha:

~~~html
<iframe
  src="https://widget.example.test/embed"
  title="Widget"
  sandbox="allow-scripts allow-forms">
</iframe>
~~~

Chỉ thêm token khi có yêu cầu sản phẩm cụ thể. Nếu widget không cần form, bỏ `allow-forms`. Nếu không cần script, bỏ `allow-scripts`.

Không dùng một danh sách token rộng chỉ để tránh lỗi tích hợp. Khi thêm quyền, hãy ghi rõ tính năng nào cần quyền đó và kiểm thử hành vi liên quan.

### 3.3 Cẩn trọng với allow-scripts kết hợp allow-same-origin

Một cấu hình đặc biệt nguy hiểm là dùng đồng thời:

~~~html
<iframe
  src="/same-origin-widget"
  sandbox="allow-scripts allow-same-origin">
</iframe>
~~~

Nếu tài liệu con cùng origin với trang cha, `allow-scripts` cho phép mã con chạy và `allow-same-origin` giữ origin thật. Trong trường hợp này, script bên trong có thể truy cập DOM cha theo SOP, tìm phần tử iframe chứa nó, gỡ thuộc tính sandbox rồi điều hướng hoặc tải lại để thoát khỏi các hạn chế sandbox.

Vì vậy, không dùng kết hợp này cho nội dung cùng origin không hoàn toàn đáng tin. Nếu cần chạy nội dung không tin cậy, hãy đặt nội dung trên origin riêng và thiết kế giao tiếp qua `postMessage`. Nếu nội dung thực sự thuộc ứng dụng và được tin cậy, đánh giá xem có cần iframe sandbox hay không.

Đối với tài liệu khác origin, token `allow-same-origin` không làm nó trở thành cùng origin với trang cha; nó chỉ giữ origin của chính tài liệu con thay vì biến origin thành opaque. Tuy nhiên, việc cấp token vẫn có thể cho phép tài liệu dùng cookie hoặc storage của origin riêng theo các chính sách trình duyệt.

### 3.4 Sandbox không thay thế kiểm soát URL

Sandbox giới hạn hành vi của tài liệu sau khi được nhúng. Nó không phải allowlist URL và không thay thế CSP `frame-src`. Nếu URL iframe có thể bị người dùng điều khiển, ứng dụng vẫn cần xác minh scheme, origin và đường dẫn được phép trước khi gán vào `src`.

## 4. Permissions Policy qua thuộc tính allow

Thuộc tính `allow` của iframe dùng để áp dụng Permissions Policy cho tài liệu con. Nó có thể giới hạn việc dùng những tính năng như camera, microphone, geolocation, fullscreen, autoplay và một số API khác.

Ví dụ:

~~~html
<iframe
  src="https://meeting.example.test/room"
  title="Phòng họp"
  allow="camera 'self'; microphone 'self'; geolocation 'none'; fullscreen 'self'">
</iframe>
~~~

Trong ví dụ:

- Camera và microphone chỉ được cấp cho origin được chỉ định theo policy.
- Geolocation bị tắt trong iframe.
- Fullscreen được cho phép theo allowlist đã khai báo.

Cần phối hợp thuộc tính `allow` với header Permissions-Policy của trang cha. Header có thể đặt giới hạn tối đa; thuộc tính iframe không thể tự mở rộng vượt quá chính sách mà tài liệu cha cho phép.

Ví dụ header giới hạn camera và microphone:

~~~http
Permissions-Policy: camera=(self), microphone=(self), geolocation=()
~~~

Sau đó iframe có thể được cấp quyền cụ thể hơn trong giới hạn đó. Cú pháp và tên feature phụ thuộc phiên bản chuẩn và trình duyệt; kiểm tra danh sách feature mà sản phẩm thực sự sử dụng.

### 4.1 Sandbox và Permissions Policy khác nhau

| Cơ chế | Kiểm soát chính |
|---|---|
| `sandbox` | Khả năng chạy script, gửi form, mở popup, điều hướng và các hạn chế sandbox khác |
| `allow` | Quyền sử dụng các tính năng trình duyệt được Permissions Policy quản lý |
| CSP `frame-src` | Nguồn tài liệu mà trang cha được phép tải vào frame |
| CSP `frame-ancestors` | Những ancestor nào được phép nhúng tài liệu hiện tại |

Một iframe có thể được phép tải nhưng vẫn bị hạn chế camera. Ngược lại, việc cấp camera không có nghĩa nguồn iframe được phép tải. Hãy review từng lớp riêng.

## 5. CSP frame-src: trang cha được tải iframe từ đâu?

`frame-src` là fetch directive của CSP trên trang cha. Nó giới hạn nguồn tài liệu được tải vào các phần tử frame như `<iframe>` và `<frame>`.

Ví dụ chỉ cho phép iframe cùng origin và một nhà cung cấp cụ thể:

~~~http
Content-Security-Policy: default-src 'self'; frame-src 'self' https://video.example.test
~~~

Trang có thể tải iframe từ cùng origin hoặc `video.example.test`. Nguồn khác sẽ bị chặn theo chính sách.

Ví dụ HTML:

~~~html
<iframe
  src="https://video.example.test/embed/lesson-42"
  title="Video bài học"
  loading="lazy">
</iframe>
~~~

Nếu không khai báo `frame-src`, CSP có thể dùng `child-src` làm fallback, rồi đến `default-src`. Để người review nhìn thấy chủ đích rõ ràng, hãy khai báo `frame-src` tường minh khi ứng dụng có nội dung nhúng.

### 5.1 frame-src không phải frame-ancestors

- `frame-src`: trang này được phép tải những tài liệu nào vào frame?
- `frame-ancestors`: những trang nào được phép nhúng trang này?

Ví dụ:

~~~http
Content-Security-Policy: default-src 'self'; frame-src https://video.example.test; frame-ancestors 'self'
~~~

Trang cha chỉ tải iframe từ `video.example.test`, đồng thời chính trang đó chỉ được nhúng bởi các ancestor cùng origin.

Hai directive không thay thế nhau. `frame-src 'none'` không ngăn website khác nhúng chính trang hiện tại. `frame-ancestors 'none'` không ngăn trang hiện tại nhúng một iframe khác.

### 5.2 Không nhầm với child-src

`child-src` là directive cũ hơn từng kiểm soát một số ngữ cảnh worker và frame. Trong chính sách hiện đại, `frame-src` và `worker-src` có thể được khai báo riêng. Khi thiếu `frame-src`, trình duyệt có thể đi theo fallback chain của CSP.

Đừng dùng `child-src` làm cách thay thế mặc định nếu ứng dụng cần kiểm soát iframe rõ ràng. Hãy khai báo `frame-src` và `worker-src` theo nhu cầu thực tế.

## 6. frame-ancestors: ai được phép nhúng trang của bạn?

Nếu trang có chức năng nhạy cảm như tài khoản, thanh toán, quản trị hoặc xác nhận giao dịch, cần ngăn website không được phép nhúng trang vào iframe để thực hiện clickjacking.

CSP `frame-ancestors` kiểm soát các ancestor của tài liệu hiện tại:

~~~http
Content-Security-Policy: frame-ancestors 'none'
~~~

Cấu hình này cấm mọi trang nhúng tài liệu. Nếu chỉ cho phép nhúng trong cùng origin:

~~~http
Content-Security-Policy: frame-ancestors 'self'
~~~

Nếu cần một số đối tác cụ thể:

~~~http
Content-Security-Policy: frame-ancestors 'self' https://portal.partner.test
~~~

Trình duyệt kiểm tra toàn bộ chuỗi ancestor. Nếu một frame nằm trong nhiều lớp iframe, mọi ancestor phải phù hợp với chính sách. Chỉ kiểm tra frame cha trực tiếp là chưa đủ.

### 6.1 frame-ancestors không dùng default-src làm fallback

Nếu không khai báo `frame-ancestors`, `default-src` không tự động cấm nhúng. Vì vậy, hãy khai báo rõ directive này cho các trang cần bảo vệ khỏi framing.

### 6.2 Chỉ cấu hình bằng response header

`frame-ancestors` không được hỗ trợ trong thẻ meta `<meta http-equiv="Content-Security-Policy">`. Hãy gửi directive trong HTTP response header của tài liệu cần được bảo vệ.

Ví dụ:

~~~http
Content-Security-Policy: default-src 'self'; frame-ancestors 'self'
~~~

Header phải được trả về cho đúng tài liệu, bao gồm các route nhạy cảm và response liên quan. Kiểm tra Network để xác nhận response thực tế, không chỉ nhìn file cấu hình ở tầng ứng dụng.

## 7. X-Frame-Options và khả năng tương thích

X-Frame-Options (XFO) là response header cũ để hạn chế việc trang được nhúng.

Hai giá trị thường gặp:

~~~http
X-Frame-Options: DENY
~~~

Không cho phép trang được hiển thị trong frame.

~~~http
X-Frame-Options: SAMEORIGIN
~~~

Chỉ cho phép nhúng trong cùng origin theo cách xử lý của trình duyệt.

Giá trị `ALLOW-FROM` đã lỗi thời và không nên dùng cho cấu hình mới. Nếu cần danh sách nhiều đối tác, hãy dùng CSP `frame-ancestors`.

Một số hệ thống gửi cả XFO và CSP `frame-ancestors` để hỗ trợ trình duyệt cũ. Hai chính sách cần nhất quán. Trên các trình duyệt hiện đại hỗ trợ `frame-ancestors`, directive CSP là cơ chế linh hoạt hơn; hãy kiểm tra ma trận trình duyệt và hành vi thực tế khi gửi đồng thời.

Trên trình duyệt hỗ trợ `frame-ancestors`, directive CSP được ưu tiên và XFO bị bỏ qua khi cả hai cùng xuất hiện. XFO vẫn có thể làm fallback cho trình duyệt cũ không hiểu directive này; vì vậy, đừng cấu hình XFO rộng hơn chính sách `frame-ancestors`.

Ví dụ chính sách nghiêm ngặt:

~~~http
Content-Security-Policy: default-src 'self'; frame-ancestors 'none'
X-Frame-Options: DENY
~~~

Đối với ứng dụng cần nhúng trong cùng origin:

~~~http
Content-Security-Policy: frame-ancestors 'self'
X-Frame-Options: SAMEORIGIN
~~~

XFO và `frame-ancestors` là chính sách của tài liệu được nhúng. Chúng không quyết định trang đó có thể tải iframe từ host nào; việc đó thuộc `frame-src` của trang cha.

## 8. Giao tiếp an toàn bằng postMessage

Trang cha và iframe khác origin không thể đọc DOM của nhau trực tiếp do SOP. `window.postMessage` là API chuẩn để trao đổi dữ liệu có kiểm soát.

Ví dụ trang cha gửi thông điệp đến iframe:

~~~js
const frame = document.querySelector("#payment-frame");

frame.contentWindow.postMessage(
  {
    type: "INIT_CHECKOUT",
    version: 1,
    requestId: "req-42"
  },
  "https://pay.example.test"
);
~~~

Tham số `targetOrigin` cần là origin chính xác mà bạn mong đợi. Không dùng `*` nếu biết trước origin của tài liệu nhận.

### 8.1 Xác minh origin và source khi nhận

Trong trang cha:

~~~js
const paymentFrame = document.querySelector("#payment-frame");
const PAYMENT_ORIGIN = "https://pay.example.test";

window.addEventListener("message", event => {
  if (event.origin !== PAYMENT_ORIGIN) return;
  if (event.source !== paymentFrame.contentWindow) return;

  const message = event.data;

  if (
    !message ||
    typeof message !== "object" ||
    message.type !== "CHECKOUT_COMPLETE" ||
    message.version !== 1 ||
    typeof message.requestId !== "string"
  ) {
    return;
  }

  // Chỉ xử lý dữ liệu sau khi xác minh đúng giao thức.
  handleCheckoutComplete(message);
});
~~~

Cần kiểm tra cả:

- `event.origin`: origin của bên gửi.
- `event.source`: window cụ thể đang gửi.
- `event.data`: kiểu dữ liệu, schema, kích thước và giá trị hợp lệ.
- `type` và `version`: thông điệp có thuộc giao thức mà ứng dụng mong đợi không.

Không chỉ kiểm tra `event.origin` rồi thực hiện ngay hành động nhạy cảm. Một origin hợp lệ vẫn có thể gửi dữ liệu sai định dạng hoặc một thông điệp không đúng thời điểm.

### 8.2 Không dùng wildcard làm targetOrigin tùy tiện

Mẫu nguy hiểm:

~~~js
frame.contentWindow.postMessage(
  { type: "SEND_TOKEN", token: accessToken },
  "*"
);
~~~

Nếu iframe bị điều hướng sang tài liệu khác trước khi thông điệp được gửi, dữ liệu có thể đến một đích không còn được tin cậy. Khi biết origin, luôn dùng origin chính xác.

### 8.3 Xử lý iframe có opaque origin

Một iframe sandbox không có `allow-same-origin` thường có opaque origin. Trong sự kiện message, origin có thể được biểu diễn là chuỗi `"null"`. Không coi `"null"` là một danh tính đáng tin cậy, vì nhiều tài liệu opaque origin khác nhau có thể có biểu diễn này.

Một số trường hợp gửi thông điệp đến opaque origin không thể dùng target origin cụ thể và buộc phải dùng `*`. Nếu thiết kế cần trường hợp đó:

- Chỉ gửi dữ liệu không nhạy cảm.
- Kiểm tra `event.source` đúng iframe đã tạo.
- Dùng giao thức thông điệp hẹp và kiểm tra schema.
- Có thể dùng capability ngẫu nhiên, thời hạn ngắn và chỉ cấp đúng quyền cần thiết.
- Không dựa vào `event.origin === "null"` để xác thực người gửi.

Nếu có thể, dùng origin riêng ổn định cho nội dung con để giao tiếp có thể xác minh bằng origin chính xác.

### 8.4 Không biến postMessage thành lệnh thực thi

Không nhận một chuỗi từ iframe rồi đưa vào `eval`, `Function`, `innerHTML`, `outerHTML` hoặc một API điều hướng tùy ý. Hãy dùng giao thức dữ liệu có kiểu rõ ràng, ví dụ `RESIZE`, `CLOSE_DIALOG`, `CHECKOUT_COMPLETE`, và kiểm tra từng trường trước khi hành động.

## 9. Cookie, storage và đăng nhập trong iframe

Iframe có thể tải tài liệu cùng origin hoặc bên thứ ba. Cookie và storage chịu ảnh hưởng bởi origin, thuộc tính cookie và chính sách quyền riêng tư của trình duyệt.

Một số điểm cần hiểu:

- Cookie được gắn với domain/path và các thuộc tính như `Secure`, `HttpOnly`, `SameSite`.
- Cookie `SameSite=Lax` hoặc `Strict` có thể không được gửi trong một số ngữ cảnh iframe cross-site.
- Cookie `SameSite=None` cần `Secure`, nhưng trình duyệt vẫn có thể chặn hoặc phân vùng cookie bên thứ ba.
- Storage như localStorage thường gắn với origin và có thể chịu phân vùng theo top-level site trong các cơ chế bảo vệ quyền riêng tư.
- Sandbox tạo opaque origin có thể làm thay đổi khả năng truy cập cookie và storage của tài liệu con.
- `allow-same-origin` không tự bỏ qua chính sách cookie bên thứ ba của trình duyệt.

Không thiết kế xác thực dựa trên giả định rằng cookie bên thứ ba luôn được gửi. Nếu ứng dụng cần đăng nhập trong iframe, hãy kiểm thử các trình duyệt mục tiêu và cân nhắc luồng xác thực top-level, redirect có kiểm soát hoặc Storage Access API khi phù hợp.

Không nới lỏng `SameSite` hoặc cấp quyền storage chỉ để tránh lỗi tích hợp mà chưa đánh giá tác động bảo mật. Dữ liệu nhạy cảm không nên được truyền qua URL query string để bù cho cookie không hoạt động.

## 10. srcdoc và nội dung HTML nội tuyến

Thuộc tính `srcdoc` cho phép đặt nội dung HTML trực tiếp trong iframe:

~~~html
<iframe
  title="Bản xem trước"
  srcdoc="<p>Nội dung xem trước</p>">
</iframe>
~~~

Tài liệu `srcdoc` thường có quan hệ origin với trang cha nếu không bị sandbox làm opaque origin. Nếu nội dung được tạo từ dữ liệu người dùng, việc ghép chuỗi vào `srcdoc` có thể tạo DOM XSS trong browsing context.

Không làm như sau:

~~~js
frame.srcdoc = "<p>" + userProvidedText + "</p>";
~~~

Nếu chỉ cần hiển thị văn bản, hãy tạo text node hoặc gán `textContent` trong tài liệu con thay vì nội suy chuỗi HTML. Nếu tài liệu con bị sandbox thành opaque origin, hãy thiết kế việc render ngay bên trong tài liệu con thay vì giả định trang cha có thể truy cập DOM của nó. Nếu thật sự cần HTML rich text, dùng sanitizer đã được duy trì và sandbox nội dung.

Ví dụ với iframe sandbox:

~~~html
<iframe
  title="Bản xem trước không tin cậy"
  sandbox
  srcdoc="<p>Nội dung tĩnh đã được kiểm soát</p>">
</iframe>
~~~

`srcdoc` không tự tạo một origin cô lập. Hãy kiểm tra kết hợp với sandbox và tránh cấp token không cần thiết.

## 11. Referrer Policy và dữ liệu điều hướng

Khi iframe tải tài liệu, trình duyệt có thể gửi Referer theo Referrer Policy. URL trang cha có thể chứa thông tin không nên tiết lộ, như mã chiến dịch, định danh tài nguyên hoặc tham số nội bộ.

Có thể giới hạn referrer cho iframe:

~~~html
<iframe
  src="https://partner.example.test/embed"
  title="Nội dung đối tác"
  referrerpolicy="strict-origin">
</iframe>
~~~

Các giá trị thường gặp gồm `no-referrer`, `same-origin`, `strict-origin` và `strict-origin-when-cross-origin`. Chọn chính sách phù hợp với yêu cầu tích hợp và tránh đưa bí mật vào URL ngay từ đầu.

Thuộc tính `loading="lazy"` có thể trì hoãn tải iframe ngoài màn hình, giúp hiệu năng tốt hơn. Đây không phải biện pháp bảo mật và không thay thế CSP hoặc sandbox.

## 12. Clickjacking và bảo vệ trang khỏi bị nhúng

Clickjacking xảy ra khi kẻ tấn công đặt một trang thật trong iframe nhưng che phủ hoặc bố trí nó để người dùng bấm vào những vùng khác với điều họ nghĩ. Ví dụ, một nút xác nhận giao dịch có thể bị đặt dưới một lớp giao diện giả.

Đối với trang nhạy cảm, dùng:

~~~http
Content-Security-Policy: frame-ancestors 'none'
~~~

Nếu cần được nhúng bởi trang cùng origin:

~~~http
Content-Security-Policy: frame-ancestors 'self'
~~~

Nếu cần cho phép đối tác cụ thể, chỉ liệt kê origin đã xác minh. Hãy nhớ kiểm tra toàn bộ chuỗi ancestor và áp dụng header trên tất cả route nhạy cảm.

XFO có thể được dùng làm fallback cho trình duyệt cũ, nhưng CSP `frame-ancestors` là lựa chọn linh hoạt hơn.

### 12.1 Frame-busting bằng JavaScript không đủ

Một số trang cũ dùng đoạn mã phát hiện mình đang ở trong iframe rồi điều hướng top-level. Cách này không đáng tin cậy như header vì:

- Script có thể bị chặn hoặc không chạy.
- Sandbox có thể ngăn điều hướng top-level.
- Trình duyệt và cấu trúc nested frame có hành vi khác nhau.
- Kẻ tấn công có thể che nội dung hoặc tương tác trước khi mã chạy.

Dùng `frame-ancestors` hoặc XFO ở response thay cho việc dựa vào frame-busting script.

## 13. Cấu hình iframe an toàn theo từng tình huống

### 13.1 Nội dung bên ngoài chỉ để hiển thị

Nếu nhúng nội dung không tin cậy và không cần script:

~~~html
<iframe
  src="https://content.example.test/article"
  title="Bài viết bên ngoài"
  sandbox
  referrerpolicy="no-referrer"
  loading="lazy">
</iframe>
~~~

### 13.2 Widget cần script nhưng không cần quyền top-level

~~~html
<iframe
  src="https://widget.example.test/embed"
  title="Widget"
  sandbox="allow-scripts"
  referrerpolicy="strict-origin">
</iframe>
~~~

Chỉ thêm `allow-forms`, `allow-popups` hoặc token khác nếu yêu cầu sản phẩm đã được xác minh.

### 13.3 Video từ nhà cung cấp đã duyệt

~~~html
<iframe
  src="https://video.example.test/embed/lesson-42"
  title="Video bài học"
  loading="lazy"
  referrerpolicy="strict-origin"
  allow="fullscreen; picture-in-picture"
  sandbox="allow-scripts allow-same-origin allow-presentation">
</iframe>
~~~

Ví dụ này chỉ minh họa các nhóm quyền có thể cần cho trình phát. Token sandbox thực tế phải được kiểm thử với nhà cung cấp; nếu tài liệu con cùng origin với trang cha, cần tránh tổ hợp `allow-scripts allow-same-origin` như đã giải thích. Với nhà cung cấp khác origin, tổ hợp này không biến tài liệu con thành cùng origin với trang cha, nhưng vẫn cần đánh giá quyền script và origin của chính nó.

### 13.4 Ứng dụng cùng origin và được tin cậy

Nếu iframe là một phần của cùng ứng dụng và cần truy cập DOM cha, cân nhắc dùng component nội bộ thay cho iframe. Nếu vẫn cần iframe vì kiến trúc, xác định rõ quyền cùng origin và các thao tác mà tài liệu con có thể thực hiện. Không giả định sandbox tạo ra cô lập khi cấp các token đã loại bỏ những hạn chế cốt lõi.

## 14. Một baseline bảo mật để bắt đầu

Không có một cấu hình iframe phù hợp cho mọi ứng dụng. Baseline sau là điểm khởi đầu cho trang cha chỉ cần tải một số dịch vụ đã duyệt, không cần object/embed và không muốn cho trang khác nhúng nó:

~~~http
Content-Security-Policy: default-src 'self'; frame-src 'self' https://video.example.test; object-src 'none'; frame-ancestors 'none'; base-uri 'self'
Permissions-Policy: camera=(), microphone=(), geolocation=()
X-Frame-Options: DENY
Referrer-Policy: strict-origin-when-cross-origin
~~~

Khi dùng baseline:

- Thay `video.example.test` bằng host thực tế đã được duyệt.
- Nếu sản phẩm cần nhúng bởi portal cùng origin hoặc đối tác, thay `frame-ancestors` và XFO bằng chính sách nhất quán.
- Nếu iframe cần camera, microphone hoặc geolocation, cấp quyền tối thiểu bằng Permissions Policy và thuộc tính `allow`.
- Nếu trang cha không cần từ chối mọi ancestor, đừng sao chép `frame-ancestors 'none'` một cách máy móc.
- Bổ sung các CSP directive khác theo ứng dụng; ví dụ này không phải CSP hoàn chỉnh cho mọi tài nguyên.

## 15. Kiểm thử iframe trong DevTools

### 15.1 Kiểm tra response header

Mở DevTools, vào Network và tải lại trang. Chọn request loại Document của trang cha và tài liệu iframe. Kiểm tra:

- CSP `frame-src` của trang cha.
- CSP `frame-ancestors` của tài liệu con.
- X-Frame-Options.
- Permissions-Policy.
- Referrer-Policy.
- Cookie được gửi hoặc bị loại khỏi request.
- Redirect và URL cuối cùng của iframe.

### 15.2 Kiểm tra sandbox

Tạo iframe lab với `sandbox` trống, sau đó thêm từng token một. Quan sát:

- Script có chạy không.
- Form có gửi được không.
- Popup có mở không.
- Top-level navigation có bị chặn không.
- Tài liệu con có truy cập được origin và storage của nó không.
- Trang cha có đọc được DOM con không.

Không bật nhiều token cùng lúc ngay từ đầu. Thêm từng quyền sẽ giúp xác định token nào thực sự cần thiết.

### 15.3 Kiểm tra frame-src

Đặt CSP:

~~~http
Content-Security-Policy: default-src 'self'; frame-src 'self'
~~~

Thử tải iframe cùng origin và iframe từ origin khác. Xác nhận iframe ngoài allowlist bị chặn và Console ghi nhận vi phạm liên quan đến `frame-src`.

### 15.4 Kiểm tra frame-ancestors

Trên một trang lab được bảo vệ, trả về:

~~~http
Content-Security-Policy: frame-ancestors 'none'
~~~

Từ một trang lab khác, thử nhúng trang đó. Xác nhận trình duyệt chặn việc hiển thị trong frame. Sau đó thử `'self'` và một origin đối tác đã duyệt để hiểu khác biệt.

### 15.5 Kiểm tra postMessage

Gửi thông điệp hợp lệ và thông điệp sai origin, sai source, thiếu trường hoặc sai kiểu dữ liệu. Xác nhận ứng dụng chỉ xử lý thông điệp đúng giao thức và không thực hiện hành động nhạy cảm từ payload không hợp lệ.

## 16. Các lỗi triển khai thường gặp

### 16.1 Không đặt title cho iframe

Thiếu `title` làm người dùng công nghệ hỗ trợ khó hiểu nội dung iframe. Hãy đặt tên mô tả cho từng frame.

### 16.2 Dùng sandbox nhưng cấp quá nhiều token

Một sandbox có nhiều ngoại lệ có thể mất phần lớn tác dụng. Chỉ cấp quyền mà tính năng cần và ghi rõ lý do.

### 16.3 Nhầm frame-src với frame-ancestors

Một directive kiểm soát nội dung mà trang tải vào; directive kia kiểm soát ai được nhúng trang. Cần cấu hình cả hai theo nhu cầu.

### 16.4 Tin vào postMessage mà không kiểm tra origin

Thông điệp từ cửa sổ khác có thể đến listener. Luôn kiểm tra origin, source và schema.

### 16.5 Dùng targetOrigin là dấu sao

Dùng `*` có thể gửi dữ liệu đến tài liệu khác sau khi iframe bị điều hướng. Dùng origin chính xác khi biết đích.

### 16.6 Cho rằng khác origin là đủ cô lập mọi thứ

SOP hạn chế truy cập DOM trực tiếp nhưng không tự chặn mọi điều hướng, popup, form hoặc thông điệp. Dùng sandbox và chính sách bổ sung theo threat model.

### 16.7 Cho rằng frame-busting script bảo vệ clickjacking

JavaScript có thể bị chặn hoặc chạy quá muộn. Dùng CSP `frame-ancestors` và XFO.

### 16.8 Dùng cookie bên thứ ba như điều kiện bắt buộc

Trình duyệt có thể chặn hoặc phân vùng cookie bên thứ ba. Thiết kế luồng đăng nhập và tích hợp không dựa vào giả định mọi iframe đều nhận cookie.

### 16.9 Nhúng URL do người dùng tùy ý cung cấp

Nếu `src` được lấy từ dữ liệu không tin cậy, iframe có thể tải một website ngoài dự kiến. Dùng allowlist origin/path và CSP `frame-src`.

## 17. Bài thực hành

Thực hiện trên các trang lab do bạn kiểm soát. Không thử với tài khoản, dữ liệu hoặc trang thanh toán thật.

### Bài 1: Quan sát SOP

Tạo hai trang ở hai origin lab khác nhau. Nhúng trang thứ hai vào iframe. Thử đọc `contentDocument` từ trang cha và ghi nhận lỗi SOP. Sau đó gửi một thông điệp không nhạy cảm qua `postMessage` và kiểm tra listener.

### Bài 2: Tìm sandbox tối thiểu

Tạo trang con có nút JavaScript, form và liên kết mở popup. Bắt đầu với sandbox trống. Thêm `allow-scripts`, `allow-forms` và `allow-popups` từng bước, ghi lại thay đổi hành vi và lý do mỗi token cần thiết.

### Bài 3: Kiểm tra Permissions Policy

Tạo iframe thử nghiệm dùng geolocation hoặc camera trong môi trường có quyền phù hợp. Chặn feature bằng header Permissions-Policy, sau đó thử cấp lại qua thuộc tính `allow`. Quan sát quyền hiệu lực và lỗi trong Console.

### Bài 4: Kiểm tra CSP hai chiều

Trên trang cha, dùng `frame-src` để cho phép một host. Trên tài liệu con, dùng `frame-ancestors` để chỉ cho phép một parent. Thử thay đổi từng phía và giải thích vì sao một bên cho phép tải không có nghĩa bên còn lại cho phép nhúng.

### Bài 5: Kiểm thử postMessage

Xây dựng giao thức gồm `INIT`, `READY` và `COMPLETE`. Kiểm tra `event.origin`, `event.source`, version, request ID và kiểu dữ liệu. Gửi payload thiếu trường hoặc có type không hợp lệ và xác nhận bị bỏ qua.

### Bài 6: Mô phỏng clickjacking trong lab

Tạo một trang lab không chứa thông tin nhạy cảm, thử nhúng nó từ một origin khác. Thêm `frame-ancestors 'none'` và quan sát kết quả. Không tạo giao diện giả để lừa người dùng thật.

## 18. Checklist review Iframe security

- [ ] Đã xác định origin của trang cha và tài liệu con.
- [ ] URL iframe chỉ lấy từ nguồn đã được kiểm tra và allowlist.
- [ ] Có `title` mô tả cho iframe.
- [ ] Đã dùng `sandbox` nếu nội dung con cần bị giới hạn.
- [ ] Chỉ cấp các token sandbox thực sự cần thiết.
- [ ] Đã đánh giá rủi ro của tổ hợp `allow-scripts allow-same-origin`.
- [ ] Permissions Policy giới hạn các feature như camera, microphone và geolocation.
- [ ] CSP `frame-src` chỉ cho phép nguồn iframe cần thiết.
- [ ] Trang nhạy cảm có `frame-ancestors` phù hợp.
- [ ] X-Frame-Options được cấu hình nhất quán nếu cần hỗ trợ trình duyệt cũ.
- [ ] `postMessage` kiểm tra origin, source và schema.
- [ ] Không gửi dữ liệu nhạy cảm qua `postMessage` với targetOrigin là `*` khi có thể chỉ rõ origin.
- [ ] Cookie và storage đã được kiểm thử trên trình duyệt mục tiêu.
- [ ] Referrer Policy không làm lộ thông tin không cần thiết.
- [ ] Đã kiểm tra response header thực tế và toàn bộ ancestor chain.
- [ ] Có kiểm thử hồi quy cho sandbox, CSP, permissions và giao tiếp message.

## 19. Câu hỏi tự kiểm tra

**1. Iframe có phải chỉ là một phần DOM của trang cha không?**

Không. Nó tạo browsing context và tài liệu riêng với window, document và vòng đời điều hướng riêng.

**2. SOP kiểm soát điều gì khi iframe khác origin?**

SOP hạn chế việc đọc hoặc thao tác trực tiếp vào DOM và dữ liệu của tài liệu khác origin. Các API giao tiếp được thiết kế riêng như `postMessage` vẫn có thể hoạt động.

**3. Sandbox trống có tác dụng gì?**

Nó áp dụng các hạn chế mặc định cho tài liệu con, bao gồm hạn chế script, form, popup, điều hướng và tạo opaque origin.

**4. Vì sao cần tránh allow-scripts cùng allow-same-origin cho iframe cùng origin không tin cậy?**

Vì script con có thể truy cập DOM cha và có khả năng gỡ sandbox attribute khỏi phần tử iframe rồi tải lại tài liệu.

**5. frame-src và frame-ancestors khác nhau thế nào?**

`frame-src` giới hạn nguồn mà trang cha tải vào iframe. `frame-ancestors` giới hạn những trang được phép nhúng tài liệu hiện tại.

**6. Permissions Policy có thay thế sandbox không?**

Không. Permissions Policy giới hạn các tính năng trình duyệt; sandbox kiểm soát một tập hành vi và quyền của tài liệu nhúng.

**7. Vì sao phải kiểm tra event.source trong postMessage?**

Để xác nhận thông điệp đến từ đúng browsing context dự kiến, tránh nhận thông điệp từ một cửa sổ khác có cùng origin.

**8. Có thể tin event.origin bằng chuỗi null không?**

Không. Opaque origin thường được biểu diễn thành `"null"`; nhiều tài liệu opaque origin có thể có giá trị này. Cần thiết kế xác thực dựa trên source và giao thức phù hợp.

**9. frame-ancestors có dùng default-src làm fallback không?**

Không. Nếu cần giới hạn ai được nhúng trang, phải khai báo `frame-ancestors` tường minh.

**10. Vì sao X-Frame-Options vẫn có thể xuất hiện cùng frame-ancestors?**

XFO có thể làm fallback cho trình duyệt cũ. Khi dùng cả hai, giá trị cần nhất quán với chính sách CSP.

## Ghi nhớ

Iframe tạo một tài liệu có origin, quyền và vòng đời riêng. Hãy xác định rõ nguồn iframe, giới hạn hành vi bằng sandbox, cấp tính năng qua Permissions Policy, kiểm soát nguồn tải bằng `frame-src`, bảo vệ trang khỏi bị nhúng bằng `frame-ancestors`, và xác thực mọi thông điệp bằng `postMessage`. Cookie, storage và referrer cũng cần được kiểm thử trong trình duyệt thực tế.
