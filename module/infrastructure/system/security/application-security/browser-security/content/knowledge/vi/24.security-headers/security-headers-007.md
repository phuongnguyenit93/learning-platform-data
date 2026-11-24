# Cross-Origin-Opener-Policy: cô lập cửa sổ và kiểm soát quan hệ opener

Một trang web có thể mở trang khác bằng liên kết hoặc `window.open()`. Trình duyệt thường giữ quan hệ giữa hai cửa sổ thông qua `window.opener` và tham chiếu mà `window.open()` trả về. Quan hệ này hữu ích cho luồng đăng nhập, thanh toán và các popup tích hợp, nhưng cũng tạo ra bề mặt tấn công: trang bên ngoài có thể tương tác với cửa sổ mở nó trong phạm vi trình duyệt cho phép, khai thác cross-site leaks hoặc làm thay đổi hành vi của tab gốc.

Cross-Origin-Opener-Policy (COOP) là HTTP response header cho phép tài liệu top-level kiểm soát việc nó có chia sẻ Browsing Context Group (BCG) với tài liệu khác hay không. Khi hai tài liệu không được phép ở cùng nhóm, trình duyệt có thể tách chúng sang các nhóm khác nhau và cắt các tham chiếu opener giữa chúng.

Bài học này giải thích các giá trị COOP, tác động đến popup và OAuth, cách triển khai Report-Only, cũng như mối liên hệ với Cross-Origin-Embedder-Policy (COEP) khi ứng dụng cần cross-origin isolation.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích Browsing Context Group và vai trò của COOP.
- Phân biệt `unsafe-none`, `same-origin`, `same-origin-allow-popups` và `noopener-allow-popups`.
- Dự đoán khi nào điều hướng hoặc `window.open()` giữ hay cắt quan hệ opener.
- Nhận biết tác động của COOP đến `window.opener`, `WindowProxy` và `postMessage`.
- Chọn cấu hình phù hợp cho ứng dụng thông thường, popup OAuth và ứng dụng cần cross-origin isolation.
- Kết hợp COOP với COEP và kiểm tra `crossOriginIsolated`.
- Dùng `Cross-Origin-Opener-Policy-Report-Only` để phát hiện tích hợp có thể bị ảnh hưởng.
- Kiểm thử header trên các luồng điều hướng, popup, redirect và callback thực tế.

## 1. Browsing Context Group là gì?

### 1.1 Browsing context

Mỗi tab, cửa sổ popup hoặc iframe là một browsing context. Nó có Window, Document và lịch sử điều hướng riêng. Khi một trang mở popup, hai browsing context có thể giữ quan hệ với nhau thông qua opener.

~~~text
Tab ứng dụng A
  |
  +-- window.open()
        |
        +-- Popup B

Quan hệ thông thường:
A có thể giữ WindowProxy của B
B có thể có window.opener trỏ về A
~~~

Quan hệ này có ích khi popup cần gửi kết quả về trang mở nó. Tuy nhiên, nếu popup là trang bên ngoài, ứng dụng cần xem xét những thao tác mà hai cửa sổ có thể thực hiện.

### 1.2 Browsing Context Group

Browsing Context Group (BCG) là nhóm các browsing context có thể chia sẻ một số quan hệ và cơ chế tương tác theo mô hình của trình duyệt. Các cửa sổ trong cùng nhóm có thể giữ các tham chiếu opener theo quy tắc nền tảng.

COOP cho phép một tài liệu top-level yêu cầu trình duyệt đặt nó vào BCG mới khi chính sách của nó không tương thích với tài liệu mở nó hoặc tài liệu mà nó điều hướng đến. Khi việc tách nhóm xảy ra:

- Quan hệ opener giữa hai browsing context có thể bị cắt.
- Tham chiếu WindowProxy mà cửa sổ mở giữ có thể biểu hiện như đã đóng.
- `window.opener` trong tài liệu được mở có thể là `null`.
- Hai tài liệu không còn giao tiếp qua quan hệ cửa sổ đó như trước.

COOP giúp giảm các cuộc tấn công dựa trên khả năng quan sát hoặc tương tác giữa cửa sổ, bao gồm một số XS-Leaks. Trình duyệt cũng có thể dùng việc tách BCG để cải thiện process isolation, nhưng không nên xem BCG như cam kết rằng mỗi nhóm luôn chạy trong một tiến trình hệ điều hành riêng.

### 1.3 COOP áp dụng cho tài liệu top-level

COOP là chính sách của tài liệu top-level. Một iframe không thể tự dùng COOP để tách nó khỏi trang cha theo cách tương tự một tab top-level. Với iframe, cần xem xét các cơ chế như:

- Same-Origin Policy để giới hạn truy cập DOM.
- `sandbox` để hạn chế hành vi của tài liệu con.
- CSP `frame-src` để giới hạn nguồn iframe mà trang cha tải.
- CSP `frame-ancestors` để giới hạn trang nào được nhúng tài liệu.
- Permissions Policy để giới hạn tính năng trình duyệt được cấp cho iframe.

Đừng dùng COOP như thay thế cho các chính sách quản lý iframe.

## 2. COOP kiểm soát điều gì?

COOP là HTTP response header:

~~~http
Cross-Origin-Opener-Policy: same-origin
~~~

Trình duyệt đọc chính sách từ response của tài liệu top-level và quyết định tài liệu có thể chia sẻ BCG với opener hoặc tài liệu được mở hay không.

COOP đặc biệt quan trọng khi:

- Một website khác mở trang của bạn bằng `window.open()`.
- Trang của bạn mở popup đăng nhập hoặc thanh toán.
- Popup điều hướng qua nhiều origin rồi quay lại callback của ứng dụng.
- Ứng dụng cần tính năng yêu cầu `crossOriginIsolated`, ví dụ `SharedArrayBuffer`.
- Các trang có mức độ tin cậy khác nhau nhưng đang cùng origin và có quan hệ cửa sổ.

COOP không quyết định mọi loại truy cập giữa các origin. SOP vẫn kiểm soát việc đọc DOM và nhiều thuộc tính của cửa sổ khác origin. COOP bổ sung một lớp cô lập ở cấp quan hệ browsing context.

## 3. Các giá trị COOP

COOP có bốn giá trị thường gặp trong tài liệu triển khai hiện đại. Chọn giá trị theo yêu cầu tương tác giữa trang và popup.

| Giá trị | Hành vi chính | Trường hợp sử dụng |
|---|---|---|
| `unsafe-none` | Cho phép chia sẻ BCG theo hành vi mặc định nếu chính sách phía kia tương thích | Mặc định khi không chủ động bật cô lập |
| `same-origin` | Chỉ giữ trong BCG với tài liệu cùng origin có chính sách khớp | Cô lập mạnh cho ứng dụng top-level; thường cần cho cross-origin isolation |
| `same-origin-allow-popups` | Gần giống `same-origin`, nhưng cho phép giữ quan hệ với popup có `unsafe-none` trong trường hợp được quy định | Ứng dụng cần mở popup OAuth/thanh toán cross-origin và giữ tham chiếu |
| `noopener-allow-popups` | Cắt quan hệ với opener của chính tài liệu, đồng thời vẫn có thể mở popup `unsafe-none` theo quy tắc của nó | Cô lập trang khỏi trang đã mở nó, nhưng vẫn cần mở popup tích hợp |

Các quy tắc COOP xét chính sách của cả tài liệu mở và tài liệu được mở. Chỉ nhìn header của một phía là chưa đủ để dự đoán quan hệ cuối cùng.

### 3.1 unsafe-none

`unsafe-none` là giá trị mặc định khi tài liệu không chủ động đặt COOP. Nó cho phép tài liệu chia sẻ BCG với tài liệu khác theo quy tắc mặc định của trình duyệt.

~~~http
Cross-Origin-Opener-Policy: unsafe-none
~~~

Trong thực tế, thường không cần gửi header này vì nó là hành vi mặc định. Khai báo tường minh có thể hữu ích trong lab để so sánh chính sách.

Với `unsafe-none`, trang có thể giữ quan hệ opener với cửa sổ cross-origin nếu phía còn lại và quy tắc điều hướng cho phép. Điều đó giúp tương thích với nhiều tích hợp cũ, nhưng cũng giữ lại một số bề mặt XS-Leaks và tương tác cross-window.

Không dùng `unsafe-none` như lựa chọn bảo mật chỉ vì nó làm popup hoạt động. Hãy xác định popup có thật sự cần quan hệ opener hay không.

### 3.2 same-origin

`same-origin` yêu cầu tài liệu chỉ chia sẻ BCG với tài liệu cùng origin có chính sách COOP tương thích.

~~~http
Cross-Origin-Opener-Policy: same-origin
~~~

Khi một trang khác origin mở tài liệu này, trình duyệt thường đặt tài liệu vào BCG mới và cắt quan hệ opener. Tương tự, nếu trang này mở một popup khác origin, tham chiếu đến popup có thể bị tách theo quy tắc COOP.

Đây là lựa chọn thường cần khi ứng dụng muốn thiết lập cross-origin isolation cùng COEP. Nó phù hợp với ứng dụng cần giảm tương tác với cửa sổ cross-origin, nhưng có thể phá vỡ luồng popup vốn dựa vào `window.opener` hoặc WindowProxy trả về từ `window.open()`.

Trước khi triển khai, hãy kiểm tra:

- Đăng nhập OAuth hoặc OpenID Connect bằng popup.
- Popup thanh toán của nhà cung cấp.
- Liên kết mở trang hỗ trợ hoặc tài liệu.
- Luồng callback cần gọi `postMessage` về trang mở.
- Các trang nội bộ cùng origin có quan hệ cửa sổ với nhau.

### 3.3 same-origin-allow-popups

`same-origin-allow-popups` tương tự `same-origin`, nhưng nới lỏng quy tắc cho popup có chính sách `unsafe-none` được mở bằng `window.open()`.

~~~http
Cross-Origin-Opener-Policy: same-origin-allow-popups
~~~

Giá trị này được thiết kế cho ứng dụng cần mức cô lập cao hơn nhưng vẫn cần mở một popup cross-origin không chủ động dùng COOP, chẳng hạn trang đăng nhập OAuth hoặc trang thanh toán.

~~~text
Ứng dụng của bạn
  COOP: same-origin-allow-popups
        |
        | window.open()
        v
Nhà cung cấp OAuth
  COOP: unsafe-none hoặc không khai báo COOP

Trong trường hợp tương thích:
Ứng dụng vẫn giữ được tham chiếu popup
và có thể nhận kết quả theo giao thức đã thiết kế.
~~~

Giá trị này không có nghĩa mọi popup đều được giữ quan hệ. Nếu popup hoặc một trang trong chuỗi điều hướng của nó gửi COOP không tương thích, trình duyệt có thể tách BCG và cắt quan hệ opener.

Đặc biệt, hãy kiểm thử callback route sau khi nhà cung cấp đăng nhập điều hướng quay lại. Nếu callback của chính ứng dụng gửi `COOP: same-origin`, nó có thể làm thay đổi quan hệ cửa sổ mà luồng OAuth đang cần.

### 3.4 noopener-allow-popups

`noopener-allow-popups` là giá trị bổ sung cho trường hợp tài liệu muốn cắt quan hệ với opener của nó nhưng vẫn cần mở một số popup.

~~~http
Cross-Origin-Opener-Policy: noopener-allow-popups
~~~

Chính sách này thường làm tài liệu được cô lập khỏi opener, kể cả khi opener cùng origin. Với điều hướng giữa hai tài liệu cùng origin có cùng chính sách, quy tắc ghép BCG vẫn có ngoại lệ. Nó có thể phù hợp khi một ứng dụng cần ngăn trang đã mở nó truy cập ngược vào cửa sổ, nhưng vẫn muốn mở popup bên ngoài có `unsafe-none`.

Cần hiểu hai hướng khác nhau:

- Tài liệu nhận `noopener-allow-popups` không giữ quan hệ opener với trang đã mở nó.
- Tài liệu đó vẫn có thể mở một popup `unsafe-none` và giữ tham chiếu theo quy tắc COOP.

Giá trị này mới hơn và mức hỗ trợ trình duyệt có thể khác. Hãy kiểm tra Browser Compatibility Data và thử trên đúng trình duyệt mục tiêu trước khi dùng làm yêu cầu nền tảng.

Nó cũng không tạo ranh giới bảo mật hoàn chỉnh giữa hai ứng dụng cùng origin. Các ứng dụng cùng origin vẫn có thể chia sẻ cookie, storage, service worker, endpoint và các kênh khác. Nếu cần cô lập ứng dụng có mức tin cậy khác nhau, ưu tiên tách origin và kiểm soát tài nguyên ở máy chủ.

## 4. Điều hướng và window.open có quy tắc khác nhau

COOP không chỉ so sánh giá trị header của trang hiện tại. Kết quả còn phụ thuộc cách browsing context mới được tạo.

### 4.1 Khi điều hướng giữa hai tài liệu

Với điều hướng, hai tài liệu có thể ở cùng BCG khi:

- Cả hai đều dùng `unsafe-none`; hoặc
- Hai tài liệu cùng origin và có cùng chính sách COOP phù hợp.

Nếu chính sách không khớp, trình duyệt có thể tạo BCG mới. Điều này thường làm mất quan hệ opener trước đó.

### 4.2 Khi dùng window.open()

Với `window.open()`, quy tắc có ngoại lệ để hỗ trợ popup:

- Popup có `noopener-allow-popups` được mở trong BCG mới.
- Popup `unsafe-none` có thể ở cùng BCG khi opener dùng `same-origin-allow-popups` hoặc `noopener-allow-popups`.
- Nếu hai tài liệu có chính sách khớp và cùng origin theo quy tắc tương ứng, chúng có thể ở cùng BCG.
- Các trường hợp khác thường dẫn đến BCG mới.

Bảng dưới đây tóm tắt kết quả phổ biến theo quy tắc `window.open()` trong HTML Standard. “Cùng” nghĩa là có thể ở cùng BCG; “Mới” nghĩa là được mở trong BCG mới.

| COOP của opener ↓ / COOP của popup → | `unsafe-none` | `same-origin-allow-popups` | `same-origin` | `noopener-allow-popups` |
|---|---|---|---|---|
| `unsafe-none` | Cùng | Mới | Mới | Mới |
| `same-origin-allow-popups` | Cùng | Cùng nếu cùng origin | Mới | Mới |
| `same-origin` | Mới | Mới | Cùng nếu cùng origin | Mới |
| `noopener-allow-popups` | Cùng | Mới | Mới | Mới |

Đây là bảng khái quát để học quy tắc, không thay thế việc kiểm thử toàn bộ chuỗi redirect và response header của ứng dụng thực tế.

## 5. COOP ảnh hưởng đến opener và WindowProxy

### 5.1 window.opener có thể trở thành null

Nếu COOP khiến tài liệu được mở vào BCG mới, quan hệ opener có thể bị cắt. Trong tài liệu popup:

~~~js
if (window.opener === null) {
  console.log("Không có quan hệ opener");
}
~~~

Không nên xem `window.opener` khác null là bằng chứng popup đáng tin. Cần kiểm tra origin và giao thức message ngay cả khi opener còn tồn tại.

### 5.2 Tham chiếu trả về từ window.open có thể biểu hiện như đã đóng

Ví dụ:

~~~js
const popup = window.open(
  "https://login.example.test/authorize",
  "login-popup"
);

if (popup) {
  console.log("Popup handle:", popup);
}
~~~

Nếu COOP tạo BCG mới, tham chiếu mà opener giữ có thể có `closed === true` theo hành vi được định nghĩa cho WindowProxy bị tách. Điều này không nhất thiết có nghĩa người dùng đã đóng cửa sổ popup.

Vì vậy, không dùng `popup.closed` như tín hiệu duy nhất để xác định đăng nhập thất bại hoặc popup đã đóng bởi người dùng. Luồng ứng dụng cần có cơ chế hoàn tất riêng, chẳng hạn redirect về callback, polling trạng thái phía máy chủ hoặc một giao thức message được kiểm tra.

### 5.3 postMessage không thể vượt qua việc cắt quan hệ

`postMessage` yêu cầu có tham chiếu đến browsing context nhận. Nếu COOP đã cắt tham chiếu opener hoặc tách popup khỏi nhóm ban đầu, ứng dụng có thể không còn handle hợp lệ để gửi thông điệp như trước.

Ngay cả khi handle còn dùng được, vẫn cần:

- Dùng `targetOrigin` chính xác.
- Kiểm tra `event.origin`.
- Kiểm tra `event.source` với cửa sổ mong đợi.
- Xác thực schema và phiên bản message.
- Xác nhận trạng thái nghiệp vụ từ máy chủ.

COOP không thay thế kiểm tra an toàn của `postMessage`.

## 6. COOP và các cuộc tấn công cross-origin

### 6.1 XS-Leaks

XS-Leaks là nhóm kỹ thuật suy luận thông tin cross-site thông qua những khác biệt có thể quan sát được, chẳng hạn trạng thái điều hướng, thời gian tải, hành vi cửa sổ hoặc phản hồi tài nguyên.

Nếu website của bạn được mở trong popup bởi một website khác, quan hệ cửa sổ còn tồn tại có thể cung cấp một số tín hiệu cho bên mở. COOP có thể tách browsing context và hạn chế khả năng quan sát đó.

COOP không chặn mọi XS-Leak. Các kênh khác như timing, cache, request behavior, URL, tài nguyên nhúng hoặc side channel vẫn cần được đánh giá.

### 6.2 Reverse tabnabbing

Reverse tabnabbing là tình huống trang được mở dùng `window.opener` để điều hướng tab gốc đến một trang giả mạo.

Ví dụ nguy cơ:

~~~js
if (window.opener) {
  window.opener.location = "https://lookalike.example.test/login";
}
~~~

COOP có thể cắt quan hệ opener khi chính sách không tương thích. Tuy nhiên, với liên kết mở tab mới, hãy dùng `rel="noopener"` khi không cần opener:

~~~html
<a
  href="https://external.example.test"
  target="_blank"
  rel="noopener">
  Mở trang ngoài
</a>
~~~

`noopener` và COOP có phạm vi khác nhau:

- `noopener` áp dụng tại điểm mở liên kết hoặc cửa sổ.
- COOP là response policy của tài liệu top-level và ảnh hưởng cách trình duyệt nhóm các browsing context.

Không cần bật COOP chỉ để giải quyết reverse tabnabbing ở một liên kết. Hãy chọn cơ chế phù hợp với mục tiêu bảo vệ.

### 6.3 COOP không thay thế SOP

SOP giới hạn việc đọc DOM và dữ liệu giữa các origin. COOP quyết định các tài liệu top-level có chia sẻ BCG và quan hệ opener hay không.

Một ứng dụng có thể bị SOP hạn chế nhưng vẫn còn quan hệ opener; COOP có thể cắt quan hệ đó. Ngược lại, COOP không biến một trang cùng origin thành ứng dụng có quyền hạn tách biệt hoàn toàn.

## 7. COOP và cross-origin isolation

Một số API nhạy cảm về bảo mật và hiệu năng, chẳng hạn `SharedArrayBuffer`, yêu cầu tài liệu ở trạng thái cross-origin isolated trong các trình duyệt hiện đại.

Để đạt trạng thái này, cấu hình phổ biến gồm:

~~~http
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
~~~

Hoặc trong môi trường phù hợp:

~~~http
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: credentialless
~~~

### 7.1 Vai trò của COOP

`COOP: same-origin` cô lập tài liệu top-level khỏi các browsing context cross-origin thông qua BCG. Đây là nửa bảo vệ liên quan đến opener.

### 7.2 Vai trò của COEP

COEP kiểm soát việc tài liệu tải tài nguyên cross-origin. Với `require-corp`, tài nguyên cross-origin cần được tải qua CORS hoặc có CORP phù hợp. Với `credentialless`, một số request no-CORS được gửi mà không kèm credentials theo cơ chế của trình duyệt.

COEP có thể làm hỏng việc tải ảnh, font, script, worker hoặc iframe của bên thứ ba nếu máy chủ tài nguyên chưa cấp quyền phù hợp. Cần rà soát các tài nguyên đang dùng trước khi thực thi.

### 7.3 Kiểm tra crossOriginIsolated

Sau khi triển khai header, kiểm tra runtime:

~~~js
if (window.crossOriginIsolated) {
  const shared = new SharedArrayBuffer(1024);
  console.log("Cross-origin isolation is active", shared);
} else {
  console.log("Cross-origin isolation is not active");
}
~~~

`crossOriginIsolated` là tín hiệu runtime cho biết tài liệu hiện tại có đạt trạng thái cô lập cần thiết hay không. Không suy ra trạng thái này chỉ từ việc thấy header trong cấu hình; hãy kiểm tra response thực tế và thuộc tính runtime.

Ngoài COOP và COEP, còn cần xem xét hỗ trợ trình duyệt, Permissions Policy `cross-origin-isolated` và các điều kiện nền tảng khác.

### 7.4 same-origin-allow-popups có thay thế same-origin không?

Không nên mặc định như vậy. `same-origin-allow-popups` giúp giữ một số popup `unsafe-none`, nhưng cấu hình cross-origin isolation phổ biến yêu cầu `COOP: same-origin` cùng COEP tương thích. Nếu ứng dụng cần `SharedArrayBuffer`, kiểm tra `crossOriginIsolated` và tài liệu trình duyệt mục tiêu thay vì đổi giá trị COOP theo suy đoán.

## 8. COOP không phải ranh giới phân quyền ứng dụng

COOP giúp cô lập browsing context và cắt quan hệ opener. Nó không thay thế các biện pháp bảo vệ khác:

- Không thay thế xác thực và phân quyền ở máy chủ.
- Không ngăn XSS trong chính tài liệu.
- Không ngăn CSRF đối với endpoint có cookie hợp lệ.
- Không tự tách cookie hoặc localStorage giữa hai ứng dụng cùng origin.
- Không ngăn mọi giao tiếp qua BroadcastChannel, service worker hoặc request cùng origin.
- Không đảm bảo các ứng dụng cùng origin chạy ở tiến trình hệ điều hành riêng.
- Không thay thế CSP, Permissions Policy hoặc kiểm soát tải tài nguyên.

Nếu hai ứng dụng có mức độ tin cậy khác nhau, ví dụ ứng dụng chat do người dùng tạo nội dung và ứng dụng quản lý mật khẩu, cách ly bằng origin riêng thường là lựa chọn vững chắc hơn. COOP có thể bổ sung bảo vệ cho quan hệ cửa sổ, nhưng không thay thế thiết kế origin.

## 9. COOP Report-Only và Reporting API

Triển khai COOP có thể làm hỏng popup, OAuth, thanh toán hoặc luồng mở cửa sổ. Trước khi thực thi, có thể dùng `Cross-Origin-Opener-Policy-Report-Only` để quan sát các tình huống không tương thích.

Ví dụ cấu hình:

~~~http
Reporting-Endpoints: coop="https://app.example.test/reports/coop"
Cross-Origin-Opener-Policy-Report-Only: same-origin; report-to="coop"
~~~

Header Report-Only cho trình duyệt biết chính sách dự kiến để tạo báo cáo, nhưng không thực thi việc tách BCG theo chính sách đó.

Khi đọc báo cáo:

- Xác định route hoặc tài liệu liên quan.
- Kiểm tra opener và popup đang dùng COOP gì.
- Theo dõi redirect chain, đặc biệt luồng OAuth.
- Xác định tích hợp nào thật sự cần giữ WindowProxy hoặc `window.opener`.
- Phân biệt vi phạm do luồng hợp lệ với luồng không cần thiết.
- Không ghi hoặc lưu dữ liệu báo cáo nhạy cảm vượt quá nhu cầu điều tra.

Reporting API và mức hỗ trợ báo cáo có thể khác giữa trình duyệt. Không dùng việc không nhận báo cáo làm bằng chứng rằng chính sách chắc chắn không gây tác động.

Sau khi xử lý các tích hợp hợp lệ, chuyển sang `Cross-Origin-Opener-Policy` để thực thi.

## 10. Triển khai COOP ở máy chủ

COOP là response header, nên cần được cấu hình ở tầng thực sự trả response HTML. Có thể cấu hình tại ứng dụng, web server, reverse proxy hoặc CDN.

Ví dụ header cho một ứng dụng muốn cô lập cửa sổ cross-origin:

~~~http
Cross-Origin-Opener-Policy: same-origin
~~~

Ví dụ Nginx:

~~~nginx
add_header Cross-Origin-Opener-Policy "same-origin" always;
~~~

Tùy framework và kiến trúc, có thể dùng middleware hoặc cấu hình tương đương. Hãy bảo đảm header được trả về trên mọi response top-level liên quan, bao gồm trang callback, trang đăng nhập và route được phục vụ qua CDN.

### 10.1 Cấu hình theo nhóm ứng dụng

Không phải route nào cũng có cùng yêu cầu. Ví dụ:

| Nhóm route | Yêu cầu | Cách xem xét COOP |
|---|---|---|
| Ứng dụng chính | Cô lập khỏi opener cross-origin | Cân nhắc `same-origin` |
| Trang mở popup OAuth | Cần giữ popup `unsafe-none` | Cân nhắc `same-origin-allow-popups` nếu tương thích |
| Trang callback OAuth | Cần trao đổi kết quả với opener | Phải kiểm tra chính sách callback và chuỗi điều hướng |
| Trang tài liệu độc lập | Không cần opener | Cân nhắc `same-origin` hoặc `noopener-allow-popups` theo mục tiêu |
| Trang tích hợp cũ | Phụ thuộc popup cross-origin | Dùng Report-Only để đánh giá trước |

Không áp dụng cùng một header cho tất cả route mà không kiểm tra luồng nghiệp vụ. Một header đặt ở CDN có thể vô tình áp dụng cho cả callback route và làm popup không thể hoàn tất.

### 10.2 Kiểm tra response thực tế

Dùng DevTools Network hoặc công cụ HTTP để kiểm tra:

~~~bash
curl -I https://app.example.test/
~~~

Tìm header:

~~~http
Cross-Origin-Opener-Policy: same-origin
~~~

Kiểm tra cả response sau redirect. Header trên trang đầu tiên không đảm bảo response callback cuối cùng cũng có chính sách mong muốn.

## 11. Quy trình triển khai an toàn

Một quy trình triển khai có thể thực hiện theo các bước:

1. Liệt kê tất cả luồng `window.open()`, liên kết `target="_blank"` và popup tích hợp.
2. Xác định luồng nào cần `window.opener`, WindowProxy hoặc `postMessage`.
3. Kiểm tra COOP hiện tại trên opener, popup và callback.
4. Bật `Cross-Origin-Opener-Policy-Report-Only` với chính sách dự kiến.
5. Thu thập báo cáo và kiểm thử thủ công các luồng quan trọng.
6. Chọn giá trị COOP phù hợp cho từng nhóm route.
7. Thực thi header và xác minh response sau redirect.
8. Kiểm tra `window.opener`, `popup.closed`, message handshake và kết quả nghiệp vụ.
9. Nếu cần cross-origin isolation, cấu hình COEP và kiểm tra toàn bộ tài nguyên cross-origin.
10. Theo dõi lỗi sau phát hành và giữ phương án quay lại chính sách trước đó nếu tích hợp hợp lệ bị ảnh hưởng.

Không bật `same-origin` trên toàn bộ ứng dụng trước khi hiểu luồng popup và callback. Một thay đổi nhỏ ở response header có thể làm gián đoạn đăng nhập hoặc thanh toán dù nội dung trang vẫn tải bình thường.

## 12. Kiểm thử COOP trong trình duyệt

### 12.1 Kiểm tra opener cơ bản

Tạo hai trang lab ở hai origin khác nhau. Trang A mở trang B bằng `window.open()`. Trong trang B, kiểm tra:

~~~js
console.log(window.opener);
~~~

Thay đổi COOP của trang A và B, sau đó quan sát khi nào opener còn tồn tại và khi nào bị cắt.

### 12.2 Kiểm tra WindowProxy trả về

Trong trang A:

~~~js
const popup = window.open(
  "https://b.example.test/popup",
  "coop-lab"
);

setTimeout(() => {
  console.log({
    hasHandle: popup !== null,
    appearsClosed: popup ? popup.closed : null
  });
}, 1000);
~~~

Thử các chính sách khác nhau trên cả A và B. Ghi lại trường hợp `popup.closed` phản ánh việc tham chiếu bị tách dù popup vẫn đang mở.

### 12.3 Kiểm tra redirect chain

Dựng một luồng lab:

~~~text
Trang ứng dụng A
    |
    | window.open()
    v
Nhà cung cấp B
    |
    | redirect
    v
Callback C trên ứng dụng A
~~~

Thử COOP ở A, B và C. Quan sát thời điểm quan hệ opener bị cắt. Điều này đặc biệt quan trọng với OAuth, vì callback có thể có header khác trang ban đầu.

### 12.4 Kiểm tra postMessage

Nếu popup còn tham chiếu, thử gửi message với origin chính xác. Xác minh bên nhận kiểm tra:

- `event.origin`.
- `event.source`.
- `type` và `version`.
- ID của yêu cầu đang chờ.
- Trạng thái giao dịch đã được máy chủ xác nhận.

Nếu COOP đã cắt quan hệ opener, hãy ghi nhận rằng giao thức hiện tại phụ thuộc vào quan hệ cửa sổ và cần kiến trúc thay thế.

### 12.5 Kiểm tra cross-origin isolation

Thiết lập:

~~~http
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
~~~

Sau đó kiểm tra:

~~~js
console.log(window.crossOriginIsolated);
~~~

Nếu giá trị là `false`, kiểm tra header thực tế, tài nguyên cross-origin, CORS/CORP, COEP và Permissions Policy. Không chỉ kiểm tra header COOP.

## 13. Các lỗi triển khai thường gặp

### 13.1 Bật same-origin nhưng không kiểm thử OAuth

Popup đăng nhập có thể bị tách BCG. Trang mở mất handle hoặc không nhận được message callback. Kiểm thử toàn bộ redirect chain trước khi thực thi.

### 13.2 Nghĩ same-origin-allow-popups giữ mọi popup

Giá trị này chỉ nới lỏng một số trường hợp, đặc biệt popup `unsafe-none`. Popup có COOP không tương thích vẫn có thể bị tách.

### 13.3 Coi noopener-allow-popups là ranh giới giữa hai ứng dụng cùng origin

Nó cắt quan hệ opener, nhưng không tách cookie, storage, service worker hoặc các request cùng origin. Cần tách origin nếu yêu cầu là cô lập ứng dụng.

### 13.4 Chỉ cấu hình COOP ở trang chính

Callback route, trang đăng nhập hoặc response sau redirect có thể dùng header khác và làm thay đổi BCG. Kiểm tra mọi response top-level trong luồng.

### 13.5 Dùng popup.closed để xác định người dùng đã đóng popup

COOP có thể khiến WindowProxy biểu hiện như đã đóng khi quan hệ bị cắt. Cần trạng thái nghiệp vụ riêng và callback có kiểm tra.

### 13.6 Nghĩ COOP một mình bật cross-origin isolation

Cross-origin isolation thường cần COOP `same-origin` cùng COEP tương thích và các điều kiện bổ sung. Kiểm tra `crossOriginIsolated`.

### 13.7 Cho rằng COOP ngăn XSS hoặc CSRF

COOP không làm sạch dữ liệu, không chặn script độc hại trong trang và không xác thực request. Dùng các cơ chế phòng vệ tương ứng như output encoding, Trusted Types, CSP, CSRF token, SameSite cookie và authorization phía máy chủ.

### 13.8 Không dùng Report-Only

Thực thi ngay có thể làm hỏng popup hoặc SSO. Dùng Report-Only và thử nghiệm luồng thật trước khi chuyển sang enforcement.

## 14. Bài thực hành

Thực hiện trên các trang lab do bạn kiểm soát. Không dùng tài khoản hoặc luồng thanh toán thật.

### Bài 1: So sánh các giá trị COOP

Tạo hai origin lab A và B. Cho A mở B bằng `window.open()`. Thử các tổ hợp `unsafe-none`, `same-origin` và `same-origin-allow-popups`. Ghi lại:

- `window.opener` trong B.
- Giá trị `popup.closed` ở A.
- Khả năng gửi `postMessage`.
- Trường hợp hai trang ở cùng hoặc khác BCG theo hành vi trình duyệt.

### Bài 2: Kiểm thử same-origin-allow-popups

Cho trang A dùng `same-origin-allow-popups` và mở trang B `unsafe-none`. Kiểm tra handle popup và message handshake. Sau đó thêm COOP không tương thích vào B và quan sát sự thay đổi.

### Bài 3: Mô phỏng OAuth redirect

Tạo ba trang lab: opener, provider và callback. Provider redirect về callback. Thử thay đổi COOP trên callback và ghi nhận thời điểm quan hệ opener bị cắt. Đề xuất cách hoàn tất luồng mà không dựa vào handle nếu chính sách yêu cầu tách BCG.

### Bài 4: Report-Only

Thiết lập `Cross-Origin-Opener-Policy-Report-Only: same-origin` và Reporting API endpoint. Mở các popup lab, kiểm tra báo cáo và xác định tích hợp nào sẽ bị ảnh hưởng khi chuyển sang enforcement.

### Bài 5: Cross-origin isolation

Thiết lập COOP `same-origin` và COEP `require-corp`. Kiểm tra `crossOriginIsolated`, sau đó thêm tài nguyên cross-origin chưa có CORS/CORP và quan sát lỗi. Sửa response tài nguyên để đáp ứng chính sách.

## 15. Checklist review Cross-Origin-Opener-Policy

- [ ] Đã xác định các route top-level cần COOP.
- [ ] Đã liệt kê popup, OAuth, thanh toán và các luồng cần opener.
- [ ] Đã hiểu tác động của từng giá trị COOP.
- [ ] Không mặc định `same-origin` tương thích với mọi popup.
- [ ] Chỉ dùng `same-origin-allow-popups` khi cần giữ popup `unsafe-none` và đã kiểm thử.
- [ ] Đã đánh giá hỗ trợ trình duyệt cho `noopener-allow-popups`.
- [ ] Đã kiểm tra response header trên trang chính, redirect và callback.
- [ ] Đã kiểm thử `window.opener`, WindowProxy và `popup.closed`.
- [ ] `postMessage` vẫn kiểm tra origin, source và schema.
- [ ] Đã dùng Report-Only trước khi enforcement nếu có tích hợp hiện hữu.
- [ ] Nếu cần cross-origin isolation, COEP được cấu hình cùng COOP.
- [ ] Đã kiểm tra `window.crossOriginIsolated` trong runtime.
- [ ] Không coi COOP là cơ chế phân quyền hoặc ranh giới giữa ứng dụng cùng origin.
- [ ] Đã xác minh cấu hình trên các trình duyệt mục tiêu.

## 16. Câu hỏi tự kiểm tra

**1. COOP là gì?**

COOP là HTTP response header cho phép tài liệu top-level kiểm soát việc chia sẻ Browsing Context Group với các tài liệu khác và ảnh hưởng đến quan hệ opener.

**2. Browsing Context Group có vai trò gì?**

Nó nhóm các browsing context có thể chia sẻ một số quan hệ cửa sổ. COOP có thể yêu cầu trình duyệt tách tài liệu sang nhóm mới.

**3. Giá trị mặc định của COOP là gì?**

`unsafe-none`, tức tài liệu không chủ động yêu cầu cô lập bằng COOP.

**4. same-origin có tác động gì đến popup cross-origin?**

Nó thường làm popup cross-origin được mở trong BCG mới, cắt quan hệ opener và khiến tham chiếu WindowProxy phía mở không còn hoạt động như trước.

**5. Khi nào dùng same-origin-allow-popups?**

Khi ứng dụng cần cô lập hơn nhưng vẫn cần mở popup `unsafe-none`, ví dụ một số luồng OAuth hoặc thanh toán cần giữ tham chiếu.

**6. noopener-allow-popups khác same-origin-allow-popups thế nào?**

`noopener-allow-popups` cắt quan hệ giữa tài liệu hiện tại và opener của nó, kể cả khi cùng origin; nó vẫn có thể mở popup `unsafe-none` theo quy tắc riêng.

**7. COOP có ngăn XSS không?**

Không. COOP kiểm soát quan hệ browsing context; XSS cần output encoding, API DOM an toàn, Trusted Types và CSP phù hợp.

**8. Vì sao popup.closed có thể gây hiểu nhầm?**

Khi COOP tách BCG, tham chiếu WindowProxy có thể biểu hiện như đã đóng dù cửa sổ popup vẫn đang hiển thị.

**9. COOP có đủ để bật SharedArrayBuffer không?**

Không. Thông thường cần COOP `same-origin`, COEP tương thích và các điều kiện cross-origin isolation khác. Kiểm tra `crossOriginIsolated`.

**10. Report-Only có chặn việc chia sẻ BCG không?**

Không. Nó chỉ báo cáo các tình huống không tương thích theo chính sách dự kiến; enforcement mới áp dụng việc tách nhóm.

## Ghi nhớ

COOP kiểm soát quan hệ giữa các tài liệu top-level thông qua Browsing Context Group. `same-origin` tăng mức cô lập nhưng có thể làm hỏng popup cross-origin; `same-origin-allow-popups` hỗ trợ một số popup `unsafe-none`; `noopener-allow-popups` cắt quan hệ với opener của chính tài liệu. Hãy kiểm tra toàn bộ luồng popup và redirect, dùng Report-Only trước khi enforcement, và kết hợp COOP với COEP khi ứng dụng cần cross-origin isolation.

## Tài liệu tham khảo

- [MDN: Cross-Origin-Opener-Policy (COOP) header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cross-Origin-Opener-Policy)
- [HTML Standard: Cross-origin opener policies](https://html.spec.whatwg.org/multipage/browsers.html#the-coop-headers)
- [web.dev: Making your website cross-origin isolated](https://web.dev/articles/coop-coep)
