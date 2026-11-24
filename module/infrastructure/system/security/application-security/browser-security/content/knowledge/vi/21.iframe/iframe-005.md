# Điều hướng trong iframe: browsing context, sandbox và ranh giới bảo mật

## 1. Điều hướng trong iframe là gì?

Một **iframe** tạo ra một browsing context lồng nhau bên trong trang hiện tại. Trình duyệt tải một tài liệu vào context đó và có thể điều hướng context tới tài liệu khác mà không cần thay trang cha. Đây là cách phổ biến để nhúng video, bản đồ, trang thanh toán, widget, tài liệu hoặc một ứng dụng con.

Ví dụ:

~~~html
<iframe
  id="report-frame"
  src="https://reports.example.test/weekly"
  title="Báo cáo tuần"
></iframe>
~~~

Khi người dùng bấm một liên kết bên trong iframe, gửi form hoặc JavaScript thay đổi location của frame, browser điều hướng **browsing context của iframe**. Tùy đích được chọn, thao tác có thể ở lại trong frame, điều hướng frame cha, điều hướng tab trên cùng hoặc mở một context mới.

Điều hướng trong iframe có ý nghĩa bảo mật vì một tài liệu được nhúng có thể cố gắng:

- Điều hướng chính iframe sang trang khác.
- Điều hướng trang cha hoặc top-level tab.
- Mở popup hoặc tab mới.
- Gửi form tới một đích khác.
- Tạo luồng chuyển hướng khiến người dùng nhầm trang cha với trang con.
- Lợi dụng window.opener để tác động trang đã mở nó.

Các cơ chế quan trọng gồm target browsing context, Same-Origin Policy (SOP), thuộc tính sandbox, user activation, CSP và kiểm tra thông điệp giữa frame. Không có một thuộc tính đơn lẻ giải quyết tất cả rủi ro.

Bài học thuộc chương **Iframe** của module **SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY**. Nội dung tập trung vào cách browser định tuyến điều hướng giữa các browsing context, quyền của iframe sandbox, ranh giới same-origin/cross-origin và các biện pháp giới hạn điều hướng trong ứng dụng web.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích browsing context và cách iframe tạo context con.
2. Phân biệt target _self, _parent, _top, _blank và tên context.
3. Giải thích SOP giới hạn việc đọc nội dung frame nhưng không cấm mọi điều hướng.
4. Hiểu sandbox và các token điều khiển top navigation, popup, form, script.
5. Phân biệt allow-top-navigation với allow-top-navigation-by-user-activation.
6. Nhận diện rủi ro window.opener, reverse tabnabbing và cách dùng noopener.
7. Dùng postMessage an toàn khi hai frame cần trao đổi dữ liệu cross-origin.
8. Phân biệt frame-src, frame-ancestors và form-action trong CSP.
9. Kiểm thử hành vi điều hướng bằng DevTools trong môi trường được kiểm soát.

## 2. Browsing context và cây frame

Browser tổ chức các trang đang mở thành những **browsing context**. Một tab thường là top-level browsing context; mỗi iframe tạo một nested browsing context nằm bên trong một context khác.

Ví dụ cấu trúc:

~~~text
Tab / top-level context: portal.example.test
  └── iframe: dashboard.example.test
        └── iframe: charts.example.test
~~~

Mỗi context có tài liệu, URL, lịch sử điều hướng và quan hệ với context cha. Điều hướng một iframe thường thay tài liệu bên trong frame đó, không thay tài liệu của tab cha.

### 2.1. Các đối tượng window liên quan

Trong tài liệu chạy bên trong iframe:

- `window` hoặc `self` đại diện window của chính frame hiện tại.
- `parent` đại diện window của context cha trực tiếp.
- `top` đại diện top-level browsing context trong cây frame.
- `frames` cung cấp truy cập tới các browsing context con theo các giới hạn bảo mật của browser.

Ví dụ:

~~~js
console.log(window === self);  // true trong window hiện tại
console.log(window === parent); // true nếu tài liệu không nằm trong iframe
console.log(window === top);    // true nếu đây là top-level document
~~~

Các tham chiếu window có thể tồn tại giữa origin khác nhau, nhưng SOP giới hạn những thuộc tính và dữ liệu có thể đọc. Việc có một tham chiếu tới window không có nghĩa có quyền đọc DOM của window đó.

### 2.2. Iframe điều hướng độc lập với trang cha

Khi iframe được điều hướng, browser tải tài liệu mới vào context con. Trang cha vẫn giữ document của nó, trừ khi thao tác được nhắm tới _parent hoặc _top.

Điều hướng frame có thể được khởi tạo bởi:

- Liên kết có target chỉ định browsing context.
- Form có target.
- JavaScript gán location của context được phép điều hướng.
- Browser UI hoặc thao tác người dùng.
- Server redirect trong quá trình tải tài liệu.

Cần phân biệt **ai khởi tạo điều hướng**, **context nào là đích** và **sandbox/CSP nào đang áp dụng**.

## 3. Target browsing context: _self, _parent, _top, _blank

HTML dùng thuộc tính `target` trên liên kết và form để chọn browsing context nhận kết quả.

| Target | Context đích | Hành vi |
| --- | --- | --- |
| `_self` | Context hiện tại | Điều hướng ngay frame hoặc tab đang chứa phần tử. |
| `_parent` | Context cha trực tiếp | Điều hướng parent; nếu không có parent riêng thì tương đương _self. |
| `_top` | Top-level context | Điều hướng tab/window trên cùng. |
| `_blank` | Auxiliary/new browsing context | Mở context mới, thường là tab hoặc cửa sổ mới tùy browser. |
| Tên cụ thể | Context có tên tương ứng | Tái sử dụng context có tên nếu browser tìm thấy và cho phép. |

Ví dụ:

~~~html
<a href="/details" target="_self">Mở trong frame này</a>
<a href="/portal-home" target="_parent">Mở ở parent</a>
<a href="/home" target="_top">Mở ở tab trên cùng</a>
<a href="https://docs.example.test" target="_blank" rel="noopener">
  Mở tài liệu ở tab mới
</a>
~~~

Target quyết định **đích điều hướng**; nó không tự chứng minh URL là đáng tin hoặc user có quyền truy cập.

### 3.1. _self: điều hướng frame hiện tại

`_self` là lựa chọn mặc định nếu không có target khác. Liên kết trong iframe thường thay nội dung iframe:

~~~html
<a href="/next-step">Tiếp tục</a>
~~~

Nếu liên kết này nằm trong iframe, URL mới sẽ được tải trong iframe đó, trừ khi có target hoặc cơ chế khác chỉ định context khác.

### 3.2. _parent: điều hướng context cha

`_parent` yêu cầu browser điều hướng parent trực tiếp. Nếu iframe được lồng nhiều tầng, parent có thể vẫn là một iframe khác, không phải tab trên cùng.

Ví dụ:

~~~html
<a href="/summary" target="_parent">Mở trang tổng kết ở parent</a>
~~~

Nếu parent cross-origin, frame con vẫn có thể yêu cầu browser điều hướng context theo quy tắc cho phép, dù không được đọc DOM của parent. Sandbox có thể hạn chế thao tác này.

### 3.3. _top: điều hướng tab trên cùng

`_top` nhắm tới top-level browsing context:

~~~html
<a href="https://login.example.test" target="_top">Tiếp tục đăng nhập</a>
~~~

Một frame có thể bị giới hạn khi cố điều hướng top-level. Với sandbox, browser thường chặn top navigation trừ khi iframe được cấp token phù hợp hoặc có user activation theo token được cấp.

Không cấp quyền top navigation rộng chỉ vì một liên kết trong widget cần mở trang mới. Có thể dùng _blank hoặc điều hướng do parent kiểm soát theo thiết kế.

### 3.4. _blank: mở context mới

`_blank` thường mở tab hoặc cửa sổ mới. Cần cân nhắc quan hệ opener giữa context mới và trang mở nó.

~~~html
<a href="https://docs.example.test" target="_blank" rel="noopener">
  Tài liệu
</a>
~~~

`rel="noopener"` bảo đảm context mới không nhận tham chiếu window.opener tới trang mở nó trong các trường hợp áp dụng. Browser hiện đại thường mặc định noopener cho liên kết target="_blank", nhưng khai báo tường minh giúp ý định rõ và hỗ trợ đọc code/review.

`rel="noreferrer"` còn yêu cầu không gửi Referer trong điều kiện áp dụng và bao hàm hành vi noopener. Chỉ dùng khi chính sách privacy/referrer yêu cầu; mất Referer có thể ảnh hưởng analytics hoặc luồng tích hợp.

### 3.5. Tên browsing context

Một tên target tùy chỉnh có thể điều hướng context đã được đặt tên:

~~~html
<iframe name="help-panel" title="Trợ giúp"></iframe>
<a href="/help/article" target="help-panel">Mở trợ giúp</a>
~~~

Tên context có thể giúp nhiều liên kết dùng chung một frame. Nhưng không nên chọn tên quá chung hoặc dựa vào tên do nội dung không tin cậy đặt ra mà không hiểu quy tắc chọn browsing context. Các tên bắt đầu bằng dấu gạch dưới có ý nghĩa đặc biệt như _self và _top.

## 4. Điều hướng bằng JavaScript

JavaScript có thể yêu cầu browser điều hướng context hiện tại hoặc một context khác mà script có quyền điều khiển.

Điều hướng frame hiện tại:

~~~js
window.location.href = "/next";
~~~

Điều hướng context cha:

~~~js
window.parent.location.href = "/portal";
~~~

Điều hướng top-level:

~~~js
window.top.location.href = "https://login.example.test";
~~~

Những phép gán này là yêu cầu điều hướng. Browser vẫn áp dụng sandbox, user activation, popup policy, SOP và các quy tắc khác.

### 4.1. Có thể điều hướng cross-origin nhưng không thể tự do đọc

SOP thường ngăn script từ child origin đọc DOM hoặc thuộc tính nhạy cảm của parent cross-origin. Tuy vậy, một số thao tác điều hướng qua Location được cho phép theo mô hình browser.

Ví dụ, child có thể yêu cầu điều hướng parent trong một số điều kiện; nhưng không thể tùy ý đọc nội dung trang parent hoặc kiểm tra toàn bộ location của parent. Đừng suy ra “đọc bị chặn” đồng nghĩa “điều hướng bị chặn”.

### 4.2. Kiểm soát URL trước khi điều hướng

Không dùng dữ liệu URL không tin cậy làm đích điều hướng mà không parse và kiểm tra. Ví dụ an toàn hơn cho redirect nội bộ:

~~~js
function getInternalDestination(value) {
  const url = new URL(value, window.location.origin);

  if (url.origin !== window.location.origin) {
    throw new TypeError("Chỉ cho phép đích cùng origin");
  }

  if (url.protocol !== "https:" && url.protocol !== "http:") {
    throw new TypeError("Scheme không được phép");
  }

  return url.pathname + url.search + url.hash;
}

const destination = getInternalDestination(
  new URLSearchParams(location.search).get("next") || "/"
);

window.location.assign(destination);
~~~

Ví dụ này minh họa allowlist cùng origin. Hệ thống thực tế cần xử lý path chuẩn hóa, redirect chain, môi trường HTTPS và các quy tắc route cụ thể. Nếu chỉ cần điều hướng theo lựa chọn nghiệp vụ, tốt hơn dùng ID/enum được allowlist rồi ánh xạ sang URL cố định.

## 5. Same-Origin Policy và điều hướng cross-origin

Origin gồm scheme, host và port. Hai tài liệu cùng origin có thể được phép truy cập DOM theo SOP, tùy các điều kiện khác. Tài liệu khác origin bị hạn chế đọc dữ liệu của nhau.

Với iframe:

- Parent có thể truy cập một số thuộc tính của iframe element trong DOM của chính parent, ví dụ thay src.
- Parent không được tự do đọc document bên trong frame cross-origin.
- Child cross-origin không được tự do đọc DOM hoặc state của parent.
- Một số thao tác điều hướng vẫn được browser cho phép và có thể bị sandbox hạn chế.
- Giao tiếp dữ liệu có chủ đích nên dùng postMessage với kiểm tra origin/source.

Ví dụ parent thay URL iframe:

~~~js
const frame = document.querySelector("#report-frame");
frame.src = "https://reports.example.test/monthly";
~~~

Parent có thể sửa thuộc tính src trên phần tử iframe của chính mình. Điều này yêu cầu browser điều hướng context con, nhưng không cấp cho parent quyền đọc nội dung cross-origin mới.

### 5.1. Không dùng document.domain để “mở” quyền giữa subdomain

Cơ chế document.domain cũ từng được dùng để nới ranh giới giữa một số subdomain. Nó có nhiều hạn chế, làm suy yếu mô hình origin và đã bị deprecated trong các browser hiện đại. Thiết kế mới nên dùng postMessage với xác thực nguồn và API có cấu trúc thay vì cố chia sẻ DOM giữa subdomain.

### 5.2. Cross-origin navigation không phải cross-origin DOM access

Hãy tách ba khả năng:

1. **Load:** browser có thể tải URL vào frame hay không?
2. **Navigate:** script/user có thể điều hướng browsing context hay không?
3. **Read:** script có thể đọc document/response của context kia hay không?

CSP frame-src, sandbox, SOP và frame-ancestors tác động ở các điểm khác nhau. Đừng gộp chúng thành một khái niệm “cross-origin bị chặn”.

## 6. Sandbox của iframe

Thuộc tính `sandbox` bật một tập hạn chế cho tài liệu được nhúng:

~~~html
<iframe
  src="https://widgets.example.test/view"
  title="Widget"
  sandbox
></iframe>
~~~

Khi sandbox không có token mở quyền, browser áp dụng các hạn chế như:

- Chặn script trong frame.
- Đặt tài liệu vào opaque origin trong các điều kiện sandbox.
- Chặn form submission.
- Hạn chế popup và top-level navigation.
- Hạn chế một số plugin, download và các khả năng khác theo HTML sandbox model.

Sandbox được thiết kế theo hướng **mặc định hạn chế, mở từng quyền khi cần**.

### 6.1. Mở script có chọn lọc

Nếu widget cần JavaScript:

~~~html
<iframe
  src="https://widgets.example.test/view"
  title="Widget"
  sandbox="allow-scripts"
></iframe>
~~~

allow-scripts cho phép script chạy trong frame. Nó không tự cho phép frame đọc DOM parent cross-origin hoặc bỏ các hạn chế sandbox khác.

Chỉ thêm token cần thiết sau khi đã hiểu widget cần quyền nào. Một trang có script vẫn có thể điều hướng chính frame, xử lý dữ liệu và gửi request theo các quyền khác mà browser cho phép; sandbox không phải một network firewall.

### 6.2. allow-same-origin

allow-same-origin giữ origin thực của tài liệu thay vì làm tài liệu có opaque origin do sandbox. Điều này có thể cần cho cookie/storage hoặc tương tác cùng origin trong một số ứng dụng, nhưng nó làm thay đổi đáng kể ranh giới bảo mật.

Đặc biệt, với iframe same-origin do cùng ứng dụng kiểm soát, kết hợp:

~~~html
<iframe sandbox="allow-scripts allow-same-origin" src="/untrusted-widget"></iframe>
~~~

có thể làm sandbox mất phần lớn ý nghĩa. Script trong child same-origin có thể truy cập parent DOM và trong một số thiết kế loại bỏ thuộc tính sandbox trên iframe element rồi điều hướng/reload để thoát các hạn chế.

Không dùng kết hợp này cho nội dung không tin cậy same-origin. Nếu cần chạy script không tin cậy, cân nhắc phục vụ nội dung từ origin riêng biệt và chỉ cấp các token tối thiểu.

### 6.3. Top navigation trong sandbox

Mặc định, sandbox hạn chế tài liệu con điều hướng top-level context. Các token liên quan:

| Token | Ý nghĩa |
| --- | --- |
| allow-top-navigation | Cho phép frame điều hướng top-level context mà không yêu cầu user activation; quyền rộng. |
| allow-top-navigation-by-user-activation | Chỉ cho phép top navigation khi thao tác được kích hoạt bởi user activation theo quy tắc browser. |
| allow-top-navigation-to-custom-protocols | Cho phép một số điều hướng tới custom protocol theo quy tắc HTML; cần đánh giá riêng. |

Ví dụ cấp quyền khi có thao tác người dùng:

~~~html
<iframe
  src="https://checkout.example.test"
  title="Thanh toán"
  sandbox="allow-scripts allow-forms allow-top-navigation-by-user-activation"
></iframe>
~~~

Token allow-top-navigation-by-user-activation giảm khả năng frame tự ý thay trang cha khi không có tương tác người dùng phù hợp. Tuy vậy, nó không xác minh người dùng hiểu nội dung đích hoặc hành động là hợp lệ; UI và nghiệp vụ vẫn cần xác nhận.

Không cấp allow-top-navigation trừ khi có yêu cầu rõ ràng và đã đánh giá tác động.

### 6.4. Popup từ sandboxed iframe

Một iframe sandbox có thể bị chặn mở popup. Token allow-popups cho phép tạo auxiliary browsing context:

~~~html
<iframe
  src="https://widgets.example.test"
  title="Widget"
  sandbox="allow-scripts allow-popups"
></iframe>
~~~

Popup thường kế thừa sandbox restrictions của frame mở nó. Token allow-popups-to-escape-sandbox cho phép popup được tạo ra không kế thừa sandbox flags trong các trường hợp được quy định:

~~~html
<iframe
  src="https://checkout.example.test"
  title="Thanh toán"
  sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox"
></iframe>
~~~

Đây là quyền đáng kể: popup có thể hoạt động với ít hạn chế hơn. Chỉ dùng khi popup cần chạy như một trang độc lập và đích mở ra được tin cậy.

### 6.5. Form submission

Sandbox mặc định có thể chặn form submission của tài liệu con. Token:

~~~html
<iframe sandbox="allow-forms" src="https://forms.example.test"></iframe>
~~~

cho phép gửi form từ frame. Nó không thay CSRF protection, server-side validation hoặc authorization. Nếu form thực hiện thay đổi trạng thái bằng cookie session, backend vẫn cần kiểm tra CSRF theo threat model.

## 7. User activation và điều hướng top-level

Browser phân biệt thao tác được khởi tạo trực tiếp bởi người dùng với thao tác tự động từ script. User activation là trạng thái tạm thời được tạo bởi những hành động như click, tap hoặc key interaction được browser công nhận.

Ngay cả khi iframe không có sandbox, một số browser cũng hạn chế top-level navigation tự động do subframe khác origin khởi tạo nếu không có user activation. Chi tiết có thể khác theo browser và phiên bản; xem đây là lớp kiểm soát bổ sung của browser, không phải hợp đồng bảo mật thay cho sandbox hoặc policy của ứng dụng.

Điều này quan trọng với:

- Popup/window.open.
- Top-level navigation từ sandboxed frame.
- Clipboard, fullscreen và một số API nhạy cảm khác.
- Các thao tác có thể gây gián đoạn hoặc chiếm quyền điều khiển trang.

### 7.1. User activation không phải quyền vĩnh viễn

Một click có thể cấp transient user activation trong thời gian giới hạn. Một số API tiêu thụ activation; các tác vụ async hoặc chuỗi callback dài có thể làm mất điều kiện cần thiết.

Không giả định chỉ cần người dùng click một lần là mọi thao tác mở popup hoặc top navigation về sau đều được phép. Kiểm thử trên browser mục tiêu và thiết kế luồng thao tác rõ ràng.

### 7.2. Yêu cầu điều hướng do script tạo ra

Một frame có thể gọi:

~~~js
window.top.location.assign("https://destination.example.test");
~~~

Nhưng nếu sandbox không cấp token cho phép top navigation, browser có thể từ chối và ghi thông báo Console. Nếu token yêu cầu user activation, thao tác cần xảy ra trong ngữ cảnh activation hợp lệ.

Không dùng một nút giả hoặc giao diện gây nhầm lẫn để lợi dụng user activation. Clickjacking có thể khiến user activation phát sinh trên giao diện họ không hiểu; kết hợp frame-ancestors, xác nhận thao tác và UI rõ ràng.

## 8. Popup, opener và reverse tabnabbing

Khi một trang mở context mới, context mới có thể có tham chiếu `window.opener` tới trang mở nó, tùy target và chính sách. Nếu trang mới không đáng tin, nó có thể cố điều hướng trang opener tới một URL giả mạo.

Ví dụ mở tab:

~~~html
<a href="https://external.example.test" target="_blank">
  Mở trang ngoài
</a>
~~~

Cách phòng vệ rõ ràng:

~~~html
<a
  href="https://external.example.test"
  target="_blank"
  rel="noopener noreferrer"
>
  Mở trang ngoài
</a>
~~~

noopener loại bỏ quan hệ opener; noreferrer đồng thời hạn chế Referer. Browser hiện đại thường áp dụng noopener mặc định cho target="_blank" trên anchor/area, nhưng vẫn nên hiểu và khai báo tường minh khi cần tương thích hoặc review.

Nếu cần trao đổi với popup do ứng dụng sở hữu, dùng postMessage có targetOrigin chính xác và kiểm tra event.origin/event.source ở phía nhận. Không bỏ noopener chỉ để tiện giao tiếp nếu có thể thiết kế một channel an toàn khác.

### 8.1. window.open và feature noopener

Có thể dùng:

~~~js
window.open(
  "https://docs.example.test",
  "_blank",
  "noopener,noreferrer"
);
~~~

Kiểm tra hành vi return value và browser support theo yêu cầu ứng dụng. Khi cần nhận kết quả từ cửa sổ mới, cân nhắc postMessage hoặc một flow callback được xác thực thay vì để trang ngoài có quyền điều khiển opener.

## 9. postMessage: giao tiếp giữa các frame khác origin

Khi parent và child khác origin, SOP ngăn truy cập DOM trực tiếp. API `postMessage` cho phép trao đổi message có cấu trúc qua ranh giới origin.

Parent gửi:

~~~js
const frame = document.querySelector("#payment-frame");

frame.contentWindow.postMessage(
  { type: "init", locale: "vi" },
  "https://checkout.example.test"
);
~~~

Child nhận:

~~~js
window.addEventListener("message", (event) => {
  if (event.origin !== "https://portal.example.test") return;
  if (event.source !== window.parent) return;

  if (event.data?.type === "init") {
    initializeCheckout(event.data.locale);
  }
});
~~~

### 9.1. Luôn kiểm tra origin và source

Phía nhận cần:

- So sánh event.origin với origin chính xác đã cấu hình.
- Kiểm tra event.source nếu chỉ chấp nhận parent hoặc một frame cụ thể.
- Kiểm tra schema, kiểu dữ liệu, độ dài và giá trị của event.data.
- Chỉ thực hiện những hành động đã allowlist.
- Không dùng wildcard targetOrigin khi biết chính xác origin đích.

Không kiểm tra origin bằng includes hoặc hậu tố chuỗi. Các giá trị như portal.example.test.attacker.test không được coi là portal.example.test.

### 9.2. Tránh gửi dữ liệu nhạy cảm không cần thiết

postMessage là kênh giao tiếp, không tự mã hóa hay phân quyền dữ liệu nghiệp vụ. Chỉ gửi dữ liệu mà phía nhận được phép biết. Không gửi session ID, access token hoặc secret chỉ để đồng bộ UI.

Nếu child được điều hướng sang origin khác, message listener có thể nhận message từ context hiện tại theo vòng đời browsing context. Hãy xác minh origin/source và trạng thái phiên trước khi xử lý các message nhạy cảm.

## 10. CSP liên quan tới điều hướng và iframe

CSP có nhiều directive gần nhau nhưng kiểm soát các hướng khác nhau:

| Directive | Vai trò |
| --- | --- |
| frame-src | Parent kiểm soát nguồn URL được tải vào frame. |
| frame-ancestors | Child kiểm soát những ancestor được phép nhúng child. |
| form-action | Kiểm soát nơi form của document được gửi tới. |
| default-src | Fallback cho một số fetch directive; không thay frame-ancestors. |
| navigate-to | Từng được mô tả trong CSP nhưng không có hỗ trợ browser đủ rộng để dựa vào trong triển khai thực tế. |

Ví dụ parent chỉ cho phép tải frame từ checkout:

~~~http
Content-Security-Policy: default-src 'self'; frame-src https://checkout.example.test; object-src 'none'; base-uri 'none'
~~~

Child chỉ cho phép portal nhúng nó:

~~~http
Content-Security-Policy: frame-ancestors https://portal.example.test
~~~

Nếu form trong document chỉ được gửi tới cùng origin hoặc endpoint thanh toán:

~~~http
Content-Security-Policy: form-action 'self' https://checkout.example.test
~~~

### 10.1. frame-src không giới hạn điều hướng mọi loại context

frame-src kiểm soát URL dùng để tải nested browsing context của document hiện tại. Nó không phải allowlist chung cho mọi navigation của tab, link hoặc popup.

Ví dụ link:

~~~html
<a href="https://news.example.test" target="_top">Tin tức</a>
~~~

không được kiểm soát đơn giản bằng cách thêm news.example.test vào frame-src. Với top-level navigation, cần thiết kế URL allowlist ở ứng dụng, sandbox/user activation nếu là frame sandboxed và các biện pháp phù hợp khác.

### 10.2. form-action không thay CSRF protection

form-action giới hạn đích gửi form từ document. Nó không chứng minh request có ý định người dùng, không kiểm tra quyền nghiệp vụ và không thay CSRF token. Server vẫn phải xác thực request và kiểm tra dữ liệu.

## 11. Referrer policy khi iframe điều hướng

Khi frame tải một URL, browser có thể gửi Referer theo Referrer-Policy hiện hành của document khởi tạo hoặc thuộc tính referrerpolicy liên quan. Điều này ảnh hưởng dữ liệu URL nguồn được gửi cho destination.

Ví dụ:

~~~html
<iframe
  src="https://reports.example.test"
  title="Báo cáo"
  referrerpolicy="strict-origin"
></iframe>
~~~

strict-origin chỉ gửi origin trong các trường hợp chính sách cho phép, thay vì toàn bộ path/query. Một policy khác như no-referrer có thể loại bỏ Referer.

Referer có thể chứa thông tin đường dẫn hoặc query nhạy cảm nếu ứng dụng thiết kế URL không cẩn thận. Tránh đặt token bí mật trong URL; dùng Referrer-Policy như lớp giảm rò rỉ metadata.

Referrer-Policy không quyết định URL nào được phép tải và không thay SOP, CSP hoặc sandbox.

## 12. Điều hướng, cookie và session trong iframe

Điều hướng iframe tới một origin khác có thể thay đổi site context, cookie được gửi và cách browser xử lý storage. Các chính sách cookie hiện đại, đặc biệt SameSite và third-party cookie restrictions, có thể ảnh hưởng tích hợp nhúng.

Những điểm cần nhớ:

- Cookie SameSite=Strict thường không được gửi trong cross-site context.
- SameSite=Lax thường không gửi cookie trong iframe cross-site; quy tắc điều hướng top-level khác với nested frame.
- SameSite=None yêu cầu Secure trong browser hiện đại và vẫn chịu chính sách chặn third-party cookie.
- Cookie partitioning/storage access policy có thể làm tích hợp iframe khác nhau theo browser.
- Điều hướng frame sang origin mới có thể tạo request với cookie và storage context khác.

Không giả định iframe luôn có session giống tab top-level. Với thanh toán/SSO/widget, thiết kế luồng xác thực theo browser support và chính sách cookie hiện tại; không dùng redirect hoặc navigation để cố né bảo vệ third-party cookie.

## 13. Điều hướng và clickjacking

Một frame độc hại có thể cố điều hướng parent hoặc mở trang khác để gây nhầm lẫn. Ngược lại, parent có thể nhúng trang nhạy cảm và phủ giao diện giả lên đó.

Các lớp liên quan:

- frame-ancestors hoặc X-Frame-Options trên trang cần bảo vệ để kiểm soát ai được nhúng.
- sandbox trên iframe để hạn chế quyền của child.
- allow-top-navigation-by-user-activation khi thật sự cần top navigation có user activation.
- noopener để ngăn context mới điều khiển opener.
- Xác nhận giao dịch, re-authentication và CSRF defense cho hành động nhạy cảm.
- UI cho người dùng biết họ đang ở ứng dụng nào và đích điều hướng là gì.

Không coi việc browser yêu cầu user activation là đủ để chống clickjacking. User có thể bị lừa click lên một frame bị che; chính sách framing và xác nhận nghiệp vụ vẫn cần thiết.

## 14. Điều hướng tới URL do người dùng kiểm soát

Một số ứng dụng nhận query parameter như `next`, `returnUrl` hoặc `continue` để quyết định đích sau đăng nhập. Nếu đưa giá trị này vào iframe navigation hoặc top navigation mà không kiểm tra, có thể tạo open redirect hoặc điều hướng người dùng tới trang giả mạo.

### 14.1. Dùng route key thay URL tự do

Ưu tiên:

~~~js
const destinations = {
  dashboard: "/dashboard",
  settings: "/settings",
  help: "/help"
};

const key = new URLSearchParams(location.search).get("next");
const destination = destinations[key] ?? "/dashboard";

window.location.assign(destination);
~~~

Đây là allowlist theo khóa nghiệp vụ. Người dùng chỉ chọn một đích đã được ứng dụng định nghĩa.

### 14.2. Nếu cần URL, parse rồi allowlist

~~~js
function validateReturnUrl(value) {
  const url = new URL(value, location.origin);
  const allowedOrigins = new Set([
    location.origin,
    "https://portal.example.test"
  ]);

  if (!allowedOrigins.has(url.origin)) {
    throw new TypeError("Return URL không được phép");
  }

  if (url.username || url.password) {
    throw new TypeError("Không cho phép userinfo trong URL");
  }

  return url.href;
}
~~~

Kiểm tra origin chính xác thay vì so prefix. Nếu redirect qua một endpoint nội bộ khác, endpoint đó cũng phải kiểm tra redirect chain và không phản chiếu URL tùy ý.

### 14.3. URL hợp lệ vẫn có thể là trang giả mạo

Allowlist chỉ xác minh đích thuộc origin được cho phép. Nó không chứng minh nội dung trên origin đó đang an toàn hoặc người dùng hiểu hành động. Hãy xác định owner của từng origin, bảo vệ subdomain và tránh allowlist các tenant host không cùng mức tin cậy.

## 15. Lỗi triển khai thường gặp

1. **Dùng target=_top mà không đánh giá sandbox:** browser có thể chặn thao tác hoặc quyền top navigation quá rộng có thể bị cấp.
2. **Cấp allow-top-navigation cho mọi iframe:** child có thể điều hướng tab cha mà không cần user activation.
3. **Nhầm parent với top:** trong nested frame, _parent chỉ là context cha trực tiếp; _top là context trên cùng.
4. **Cho rằng SOP chặn điều hướng cross-origin:** SOP chủ yếu giới hạn đọc; một số thao tác navigation vẫn được phép.
5. **Cho rằng frame-src kiểm soát link/popup:** directive này kiểm soát nested frame fetch, không phải mọi navigation.
6. **Dùng target=_blank không hiểu opener:** context mới có thể tác động opener nếu quan hệ này tồn tại.
7. **Dùng sandbox="allow-scripts allow-same-origin" cho nội dung không tin cậy cùng origin:** có thể làm mất lợi ích sandbox.
8. **Mở allow-popups-to-escape-sandbox tùy tiện:** popup có thể không kế thừa hạn chế của frame.
9. **Dùng postMessage với targetOrigin="*" khi biết origin đích:** message có thể đến context không mong muốn sau navigation.
10. **Không kiểm tra event.origin/event.source:** message giả mạo có thể kích hoạt hành động.
11. **Dùng URL query trực tiếp làm returnUrl:** có thể tạo open redirect hoặc điều hướng lừa đảo.
12. **Dựa vào user activation để xác nhận ý định:** clickjacking có thể đánh lừa thao tác.
13. **Tin rằng iframe luôn có cookie/session như top-level tab:** SameSite và third-party cookie policy có thể thay đổi hành vi.
14. **Dùng form-action thay CSRF token:** CSP không xác thực ý định hay quyền nghiệp vụ.
15. **Không kiểm tra referrer leak:** URL có token hoặc dữ liệu nhạy cảm có thể bị gửi trong Referer.

## 16. Thực hành A — Quan sát target trong iframe

Tạo trang parent và một iframe local:

~~~html
<iframe
  src="/frame-child.html"
  name="demo-frame"
  title="Frame thử nghiệm"
></iframe>

<a href="/inside.html" target="demo-frame">Điều hướng frame</a>
<a href="/parent.html" target="_parent">Điều hướng parent</a>
<a href="/top.html" target="_top">Điều hướng top</a>
<a href="/new.html" target="_blank" rel="noopener">Mở tab mới</a>
~~~

Mở DevTools → Network và quan sát context nào tải document mới. Thử từng target trên trang demo do bạn kiểm soát.

**Mục tiêu:** xác định đích điều hướng theo browsing context, không suy đoán từ URL.

## 17. Thực hành B — So sánh sandbox top navigation

Trên child page, tạo nút:

~~~html
<button id="go-top">Mở trang top-level</button>
<script>
  document.querySelector("#go-top").addEventListener("click", () => {
    window.top.location.assign("/top-demo.html");
  });
</script>
~~~

Nhúng child với sandbox không có token top navigation:

~~~html
<iframe src="/child.html" sandbox="allow-scripts"></iframe>
~~~

Quan sát Console khi bấm nút. Sau đó thử:

~~~html
<iframe
  src="/child.html"
  sandbox="allow-scripts allow-top-navigation-by-user-activation"
></iframe>
~~~

So sánh thao tác click với điều hướng tự động khi tải trang. Không thêm allow-top-navigation trừ khi có yêu cầu đã được đánh giá.

## 18. Thực hành C — Kiểm tra opener và noopener

Tạo liên kết target blank tới trang test do bạn kiểm soát:

~~~html
<a href="/popup-test.html" target="_blank">Mở cửa sổ test</a>
~~~

Trong popup, kiểm tra:

~~~js
console.log(window.opener);
~~~

Sau đó thêm rel="noopener" vào liên kết và thử lại trên browser mục tiêu. Quan sát opener không còn được cung cấp theo hành vi noopener.

Chỉ thực hiện với trang local/test; không dùng trang ngoài để thử điều hướng opener.

## 19. Thực hành D — postMessage với origin allowlist

Tạo parent ở portal.example.test và child ở checkout.example.test. Parent gửi message:

~~~js
frame.contentWindow.postMessage(
  { type: "ping", requestId: "demo-1" },
  "https://checkout.example.test"
);
~~~

Child kiểm tra:

~~~js
window.addEventListener("message", (event) => {
  if (event.origin !== "https://portal.example.test") return;
  if (event.source !== window.parent) return;
  if (event.data?.type !== "ping") return;

  event.source.postMessage(
    { type: "pong", requestId: event.data.requestId },
    event.origin
  );
});
~~~

Thử message từ một origin khác và xác minh child bỏ qua. Kiểm tra Network/Console và không gửi secret trong message.

## 20. Checklist review điều hướng iframe

- [ ] Xác định browsing context hiện tại, parent trực tiếp và top-level context.
- [ ] Review mọi target: _self, _parent, _top, _blank và tên custom.
- [ ] Không cấp top navigation rộng nếu chỉ cần mở link trong frame hoặc popup.
- [ ] Dùng sandbox mặc định hạn chế và chỉ thêm token cần thiết.
- [ ] Phân biệt allow-top-navigation với allow-top-navigation-by-user-activation.
- [ ] Đánh giá allow-popups và allow-popups-to-escape-sandbox.
- [ ] Tránh allow-scripts + allow-same-origin cho nội dung không tin cậy same-origin.
- [ ] Kiểm soát URL redirect/returnUrl bằng route key hoặc URL parser và allowlist origin.
- [ ] Dùng rel=noopener cho liên kết mở context mới khi không cần opener.
- [ ] Chỉ dùng noreferrer khi cần giảm gửi Referer và hiểu tác động.
- [ ] Kiểm tra SOP: phân biệt load, navigate và read.
- [ ] Dùng postMessage với targetOrigin chính xác.
- [ ] Kiểm tra event.origin, event.source và schema của event.data.
- [ ] Dùng frame-src để giới hạn child mà parent tải.
- [ ] Dùng frame-ancestors để giới hạn parent được phép nhúng child.
- [ ] Dùng form-action cho đích gửi form; vẫn kiểm tra CSRF ở server.
- [ ] Không dựa vào navigate-to như một lớp kiểm soát tương thích rộng.
- [ ] Cấu hình Referrer-Policy và tránh secret trong URL.
- [ ] Đánh giá SameSite, third-party cookie và storage behavior trong iframe.
- [ ] Kiểm thử top navigation, popup, form, redirect và nested frame trên browser mục tiêu.
- [ ] Theo dõi Console, Network và response headers trong DevTools.

## 21. Những ngộ nhận thường gặp

| Nhận định | Đánh giá | Giải thích |
| --- | --- | --- |
| “SOP ngăn mọi navigation cross-origin.” | **Sai** | SOP giới hạn đọc; browser vẫn cho phép một số điều hướng. |
| “_parent luôn là tab trên cùng.” | **Sai** | _parent là context cha trực tiếp; _top mới là top-level. |
| “_blank luôn an toàn với opener.” | **Chưa đủ** | Browser hiện đại thường mặc định noopener cho anchor target blank; khai báo rõ và kiểm tra luồng popup. |
| “frame-src kiểm soát mọi liên kết rời khỏi iframe.” | **Sai** | frame-src kiểm soát nguồn nested frame, không phải mọi top-level navigation. |
| “frame-ancestors giới hạn frame mà trang hiện tại tải.” | **Sai** | Nó giới hạn ancestor được phép nhúng trang hiện tại. |
| “allow-scripts luôn an toàn nếu child ở origin khác.” | **Sai** | Script vẫn có thể dùng quyền được cấp, gửi request và tương tác theo sandbox còn lại. |
| “allow-same-origin chỉ là tên gọi khác của SOP.” | **Sai** | Token này ảnh hưởng origin sandbox của child và có thể làm thay đổi mạnh ranh giới. |
| “allow-top-navigation-by-user-activation xác nhận user hiểu đích.” | **Sai** | Nó chỉ xét user activation theo browser, không xác minh ý định. |
| “Sandbox thay CSP và CSRF.” | **Sai** | Các cơ chế bảo vệ những lớp khác nhau. |
| “postMessage tự xác thực sender.” | **Sai** | Receiver phải kiểm tra origin, source và dữ liệu. |
| “CORS cần thiết chỉ để hiển thị ảnh/frame.” | **Sai** | CORS chủ yếu kiểm soát quyền đọc response; embedding còn chịu CSP và chính sách riêng. |
| “form-action chống CSRF.” | **Sai** | Nó giới hạn đích form, không xác minh request hoặc quyền nghiệp vụ. |
| “Iframe luôn có cookie như tab top-level.” | **Sai** | SameSite và third-party cookie policy có thể thay đổi việc gửi cookie. |

## 22. Tổng kết

Điều hướng trong iframe là việc browser chuyển tài liệu của một browsing context lồng nhau tới URL hoặc context đích. target quyết định frame hiện tại, parent, top-level hay context mới; sandbox có thể giới hạn top navigation, popup và form; SOP hạn chế đọc dữ liệu cross-origin nhưng không cấm mọi điều hướng.

Ba nguyên tắc cần nhớ:

1. **Chọn đúng context và giới hạn quyền:** hiểu _self, _parent, _top, _blank; dùng sandbox và chỉ cấp top navigation/popup khi thật sự cần.
2. **Giữ ranh giới origin:** không nhầm navigation với DOM access; dùng postMessage có targetOrigin, origin và source validation.
3. **Kết hợp policy theo vai trò:** frame-src giới hạn frame mà parent tải, frame-ancestors giới hạn ai được nhúng child, form-action giới hạn đích form; server vẫn cần CSRF, authentication và authorization.

Khi review một iframe, hãy hỏi: **điều hướng được khởi tạo từ đâu, context nào là đích, sandbox đang cấp token nào, URL có được allowlist, context mới có opener không, và parent/child có trao đổi message với kiểm tra origin/source không?** Trả lời rõ các câu hỏi này giúp giữ điều hướng iframe trong phạm vi chức năng mà ứng dụng thực sự cần.
