# Clickjacking là gì

**Clickjacking** (còn gọi là **UI redressing**) là kiểu tấn công khiến người dùng tưởng rằng họ đang nhấn vào một thành phần giao diện, nhưng thao tác thực tế được gửi tới một thành phần khác bị che hoặc ngụy trang. Một cách phổ biến là attacker nhúng trang của ứng dụng mục tiêu vào một **iframe trong suốt**, đặt iframe chồng lên nút hoặc liên kết giả mà nạn nhân nhìn thấy. Khi người dùng click, browser chuyển sự kiện tới nội dung bên trong iframe.

Clickjacking khai thác sự tin cậy của người dùng vào giao diện và việc browser cho phép một trang được nhúng trong trang khác. Attacker không nhất thiết phải đọc DOM của iframe hoặc vượt qua Same-Origin Policy (SOP); họ chỉ cần khiến người dùng tương tác với giao diện thật đang được browser hiển thị. Hậu quả có thể là bật một tùy chọn, cấp quyền, đăng bài, thay đổi cài đặt hoặc xác nhận một hành động nhạy cảm.

Bài học thuộc chương **Clickjacking** trong module **Browser Security** (SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY). Nội dung đặt clickjacking trong ranh giới giữa browser, origin, cookie và ứng dụng web; phân biệt nó với CSRF/XSS, đồng thời giới thiệu các biện pháp chống nhúng như CSP `frame-ancestors` và `X-Frame-Options`.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích clickjacking và UI redressing bằng tình huống iframe bị che phủ.
2. Mô tả cách browser định tuyến thao tác chuột/chạm tới phần tử nằm trong iframe.
3. Phân biệt quyền đọc nội dung cross-origin theo SOP với khả năng nhúng và tương tác bằng giao diện.
4. Phân biệt clickjacking với CSRF và XSS, đồng thời nhận diện trường hợp các kiểu tấn công kết hợp.
5. Cấu hình CSP `frame-ancestors` và `X-Frame-Options` để kiểm soát ai được nhúng trang.
6. Phân biệt `frame-ancestors` với `frame-src`, `iframe sandbox` và các header bảo mật khác.
7. Giải thích vì sao JavaScript frame-busting, SameSite cookie và CSRF token không thay thế biện pháp chống framing.
8. Kiểm tra khả năng bị nhúng bằng DevTools và thực hành một lab an toàn trên localhost.

## 2. Cơ chế clickjacking

Giả sử người dùng đã đăng nhập vào `account.example.com`. Trang này có nút **Cho phép ứng dụng truy cập tài khoản**. Attacker tạo một trang có lời mời giả như “Nhấn để nhận quà”, rồi đặt iframe chứa trang tài khoản ở đúng vị trí nút giả. Iframe gần như trong suốt nên người dùng không nhận ra.

Khi nạn nhân nhấn vào nút nhìn thấy, tọa độ click rơi vào nút thật bên trong iframe. Browser thực hiện thao tác theo tài liệu của ứng dụng mục tiêu và cookie phiên có thể được gửi theo chính sách cookie hiện hành.

### 2.1. Luồng tấn công điển hình

~~~mermaid
sequenceDiagram
    actor V as Nạn nhân
    participant B as Browser
    participant A as Trang attacker
    participant T as Trang mục tiêu
    V->>B: Đăng nhập trang mục tiêu
    B->>T: GET /account
    T-->>B: Trang tài khoản + session cookie
    V->>B: Mở trang attacker
    B->>A: GET /bait
    A-->>B: HTML có iframe trong suốt phủ lên nút giả
    B->>T: Hiển thị trang mục tiêu bên trong iframe
    V->>B: Click nút giả mà họ nhìn thấy
    B->>T: Chuyển click tới nút thật trong iframe
    T->>T: Xử lý hành động trong phiên của nạn nhân
~~~

Điểm đáng chú ý: attacker có thể không biết nội dung bên trong iframe. Họ có thể căn vị trí iframe dựa trên kích thước giao diện đã quan sát hoặc dùng một hành động có vị trí ổn định. Browser vẫn xử lý click theo hit-testing và thứ tự lớp hiển thị.

### 2.2. Iframe trong suốt và lớp giao diện giả

Một trang thử nghiệm có thể dùng CSS như sau:

~~~css
.bait {
  position: absolute;
  z-index: 1;
}

.target-frame {
  position: absolute;
  z-index: 2;
  opacity: 0.01;
  pointer-events: auto;
}
~~~

`opacity: 0.01` làm iframe gần như không nhìn thấy nhưng vẫn nhận thao tác chuột. `z-index` đặt iframe ở lớp trên nút giả. `pointer-events: auto` cho phép iframe nhận pointer event. Trong một cuộc tấn công thực tế, attacker có thể điều chỉnh kích thước, vị trí, nội dung lời dụ và thời điểm hiển thị để tăng khả năng người dùng click đúng vùng mục tiêu.

Không phải mọi clickjacking đều dùng iframe trong suốt. UI redressing có thể dùng nhiều lớp giao diện, cửa sổ popup, nội dung giả, vùng kéo-thả hoặc giao diện cảm ứng.

## 3. Các dạng clickjacking thường gặp

| Dạng | Cách thực hiện | Ví dụ hậu quả |
| --- | --- | --- |
| **Classic iframe overlay** | Iframe của trang mục tiêu bị làm trong suốt và phủ lên nút giả | Người dùng vô tình bật một thiết lập |
| **Likejacking** | Nút “Like”, “Follow” hoặc tương tác mạng xã hội thật bị đặt dưới lời mời giả | Người dùng tương tác với nội dung mà họ không định chọn |
| **Cursorjacking** | Hiển thị hoặc dịch chuyển con trỏ giả để đánh lạc hướng vị trí click thật | Người dùng tưởng con trỏ nằm ở vị trí khác |
| **Drag-and-drop redressing** | Vùng kéo-thả thật bị phủ hoặc căn chỉnh với vùng giả | Người dùng kéo dữ liệu hoặc thả file vào mục tiêu khác |
| **Tapjacking trên thiết bị cảm ứng** | Giao diện bị căn chỉnh để cú chạm kích hoạt thành phần khác | Người dùng vô tình cấp quyền hoặc xác nhận |
| **Nested-frame UI redressing** | Nhiều lớp iframe được lồng để che giấu trang mục tiêu | Khó nhận biết trang nào thực sự nhận tương tác |

Các biến thể có thể kết hợp với phishing, social engineering, CSRF hoặc lạm dụng luồng cấp quyền. Tên gọi khác nhau nhưng nguyên tắc chung là **người dùng nhìn thấy một giao diện và tương tác với một giao diện khác**.

## 4. Điều kiện để clickjacking xảy ra

Một tình huống clickjacking thường cần nhiều điều kiện:

1. Trang mục tiêu cho phép một trang khác nhúng nó trong iframe hoặc một browsing context tương tự.
2. Người dùng có thể truy cập trang mục tiêu, thường đang có phiên đăng nhập hoặc trạng thái đã cấp quyền.
3. Attacker có thể tạo giao diện phủ/căn chỉnh để người dùng click hoặc chạm vào thành phần mục tiêu.
4. Hành động có thể thực hiện qua tương tác giao diện mà không có bước xác nhận độc lập đủ mạnh.

Không phải mọi trang được nhúng đều dễ bị khai thác. Nhưng nếu một trang nhạy cảm có thể được nhúng và các thao tác quan trọng chỉ cần một click, cần xem xét rủi ro nghiêm túc.

### 4.1. SOP không ngăn được clickjacking

Same-Origin Policy (SOP) giới hạn cách một tài liệu đọc hoặc thao tác dữ liệu của tài liệu khác origin. Ví dụ, trang `attacker.example` thường không thể đọc DOM bên trong iframe đang mở `account.example.com`.

Tuy nhiên, **SOP không mặc định cấm nhúng trang cross-origin**. Browser vẫn có thể tải và hiển thị trang mục tiêu trong iframe. Trang cha có thể không đọc được DOM của iframe nhưng vẫn đặt iframe vào layout, phủ các phần tử khác lên trên và khiến người dùng tương tác với nó.

Vì vậy:

- Không đọc được DOM cross-origin không có nghĩa trang không thể bị nhúng.
- CORS không phải cơ chế ngăn iframe được hiển thị.
- Chống clickjacking cần kiểm soát quyền framing của chính trang mục tiêu.

### 4.2. Cookie và trạng thái đăng nhập

Nếu trang mục tiêu dùng cookie phiên, browser có thể gửi cookie khi tải iframe hoặc thực hiện request bên trong iframe, tùy thuộc `SameSite`, `Secure`, chính sách third-party cookie và ngữ cảnh site. Một số browser chặn hoặc phân vùng third-party cookie, nhưng không nên dựa vào hành vi này làm biện pháp chống clickjacking.

Hai subdomain khác origin nhưng cùng site cũng cần được xem xét riêng. Chính sách SameSite có thể vẫn cho phép cookie trong một số ngữ cảnh same-site; do đó một trang cùng site nhưng kém tin cậy vẫn có thể tạo rủi ro framing nếu trang nhạy cảm cho phép nó nhúng.

## 5. Clickjacking khác CSRF và XSS như thế nào?

Ba nhóm tấn công có thể dẫn đến thay đổi trạng thái nhưng khai thác các điểm khác nhau:

| Tiêu chí | Clickjacking | CSRF | XSS |
| --- | --- | --- | --- |
| Điểm yếu chính | Người dùng bị đánh lừa về giao diện/thao tác | Server tin request mang cookie mà không xác minh ý định | Dữ liệu không tin cậy được thực thi như script |
| Vai trò người dùng | Thường bị dụ click/chạm/kéo-thả | Có thể không cần tương tác | Có thể chỉ cần mở trang có payload |
| Cách gửi hành động | Tương tác với UI thật bị che hoặc ngụy trang | Browser gửi request cross-site | Script chạy trong origin ứng dụng |
| SOP | Không cần đọc DOM cross-origin | Không ngăn mọi request gửi đi | Script chạy cùng origin có quyền đọc dữ liệu theo SOP |
| Phòng vệ chính | CSP `frame-ancestors`, X-Frame-Options | CSRF token, SameSite, Origin/Fetch Metadata | Safe DOM API, output encoding, CSP, Trusted Types |

### 5.1. CSRF token có thay chống clickjacking không?

Không. Trong clickjacking, người dùng có thể đang mở trang thật trong iframe. Trang thật đã render form và CSRF token hợp lệ; click của nạn nhân có thể gửi form cùng token đó. CSRF token chứng minh request thuộc luồng ứng dụng đã phát token, nhưng không chứng minh người dùng nhìn thấy đúng giao diện khi bấm.

Ngược lại, chống framing bằng `frame-ancestors` không thay CSRF token cho các request có thể được gửi từ form hoặc request cross-site khác.

### 5.2. XSS có thể kết hợp clickjacking

XSS có thể cho attacker thực thi script trong origin của ứng dụng, từ đó sửa giao diện hoặc điều khiển DOM trực tiếp. Clickjacking thường không cần XSS; nó lợi dụng trang mục tiêu có thể được nhúng và thao tác người dùng. Nếu một ứng dụng vừa có XSS vừa cho phép framing, mức độ rủi ro có thể tăng thêm.

## 6. Phòng vệ chính: CSP frame-ancestors

`Content-Security-Policy` có directive **`frame-ancestors`** để quy định những origin nào được phép nhúng tài liệu hiện tại trong iframe, frame, object hoặc embed theo các quy tắc CSP.

Ví dụ:

~~~http
Content-Security-Policy: frame-ancestors 'none'
~~~

Directive này cấm mọi trang khác nhúng tài liệu. Đây là lựa chọn phù hợp cho trang tài khoản, trang quản trị, trang cài đặt và các trang không có nhu cầu được nhúng.

### 6.1. Các chính sách phổ biến

| Chính sách | Ý nghĩa | Trường hợp dùng |
| --- | --- | --- |
| `frame-ancestors 'none'` | Không cho phép bất kỳ ancestor nào nhúng trang | Trang đăng nhập, tài khoản, quản trị, thanh toán |
| `frame-ancestors 'self'` | Chỉ cho phép tài liệu cùng origin nhúng trang | Ứng dụng cần iframe nội bộ |
| `frame-ancestors 'self' https://portal.example.com` | Cho phép cùng origin và origin portal cụ thể | Tích hợp với một portal được quản lý |
| `frame-ancestors https://portal.example.com https://admin.example.net` | Chỉ cho phép các origin liệt kê | Tích hợp cross-origin có kiểm soát |

Ví dụ cho phép một portal đối tác:

~~~http
Content-Security-Policy: frame-ancestors 'self' https://portal.example.com
~~~

Hãy khai báo chính xác scheme, host và port khi cần. Không dùng wildcard rộng như `https:` hoặc `*` chỉ để iframe hoạt động; điều đó có thể cho phép các trang không mong muốn nhúng ứng dụng.

### 6.2. Mọi ancestor trong chuỗi frame đều phải được phép

Nếu trang mục tiêu nằm trong nhiều lớp iframe, browser kiểm tra toàn bộ ancestor chain. Chỉ cần một ancestor không khớp chính sách, browser sẽ chặn việc hiển thị tài liệu trong frame.

Ví dụ:

~~~text
portal.example.com
  └── wrapper.partner.example
        └── app.example.com
~~~

Nếu CSP của `app.example.com` chỉ cho phép `portal.example.com` nhưng không cho phép `wrapper.partner.example`, việc nhúng có thể bị chặn. Khi thiết kế tích hợp, cần biết chính xác toàn bộ chuỗi trang cha.

### 6.3. frame-ancestors phải gửi bằng HTTP response header

Đặt directive trong thẻ meta không có hiệu lực:

~~~html
<!-- Không có tác dụng đối với frame-ancestors -->
<meta http-equiv="Content-Security-Policy" content="frame-ancestors 'none'">
~~~

Hãy cấu hình trên response HTTP của tài liệu cần bảo vệ:

~~~http
HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8
Content-Security-Policy: frame-ancestors 'none'
~~~

`frame-ancestors` không có fallback từ `default-src`. Nếu muốn cấm framing, phải khai báo directive này tường minh.

### 6.4. frame-ancestors và frame-src là hai chiều khác nhau

| Directive | Ai kiểm soát? | Câu hỏi được trả lời |
| --- | --- | --- |
| `frame-ancestors` | Trang đang được tải | Những trang nào được phép nhúng tôi? |
| `frame-src` | Trang đang nhúng iframe | Tôi được phép tải iframe từ những nguồn nào? |

Ví dụ:

~~~http
Content-Security-Policy: frame-src https://video.example.com; frame-ancestors 'none'
~~~

Trang có thể nhúng video từ `video.example.com`, nhưng bản thân trang không được nhúng vào iframe của trang khác. Chỉ cấu hình `frame-src` không bảo vệ trang khỏi clickjacking.

## 7. X-Frame-Options cho tương thích

`X-Frame-Options` là HTTP response header cũ dùng để hạn chế việc tài liệu được hiển thị trong frame:

~~~http
X-Frame-Options: DENY
~~~

Các giá trị phổ biến:

| Giá trị | Ý nghĩa |
| --- | --- |
| `DENY` | Không cho phép hiển thị tài liệu trong frame |
| `SAMEORIGIN` | Chỉ cho phép frame có cùng origin theo quy tắc browser |
| `ALLOW-FROM` | Cơ chế allowlist origin cũ, đã lỗi thời và không được hỗ trợ nhất quán |

### 7.1. Khi nào dùng DENY hoặc SAMEORIGIN?

- Dùng `DENY` nếu trang không cần được nhúng ở bất kỳ nơi nào.
- Dùng `SAMEORIGIN` nếu ứng dụng chỉ cần nhúng trang trong cùng origin.
- Nếu cần cho phép một hoặc nhiều origin đối tác, dùng CSP `frame-ancestors` với danh sách cụ thể; X-Frame-Options không cung cấp cơ chế allowlist đa origin tương đương.

### 7.2. Kết hợp CSP và X-Frame-Options

Trong browser hiện đại hỗ trợ CSP `frame-ancestors`, directive này có ưu tiên đối với quyết định framing; X-Frame-Options có thể bị bỏ qua khi `frame-ancestors` hiện diện. Có thể gửi cả hai để hỗ trợ browser cũ, nhưng cần bảo đảm chúng không mâu thuẫn.

Ví dụ trang không cho phép nhúng:

~~~http
Content-Security-Policy: frame-ancestors 'none'
X-Frame-Options: DENY
~~~

Ví dụ chỉ cho phép cùng origin:

~~~http
Content-Security-Policy: frame-ancestors 'self'
X-Frame-Options: SAMEORIGIN
~~~

Nếu CSP cho phép một portal cross-origin nhưng X-Frame-Options là `SAMEORIGIN`, browser cũ chỉ hiểu XFO có thể chặn portal đó. Hãy xác định rõ yêu cầu tương thích và kiểm thử trên browser thực tế.

Không dùng `ALLOW-FROM` làm giải pháp allowlist mới. Không đặt nhiều giá trị XFO khác nhau với kỳ vọng browser sẽ tự chọn chính sách chặt nhất.

## 8. Vì sao JavaScript frame-busting không đủ?

Một số ứng dụng cũ dùng JavaScript để phát hiện mình đang nằm trong iframe:

~~~js
if (window.top !== window.self) {
  window.top.location = window.self.location;
}
~~~

Cách này thường được gọi là **frame-busting**. Nó có thể hữu ích như một lớp phụ trong môi trường cũ, nhưng không nên là biện pháp bảo vệ chính vì:

- JavaScript có thể bị tắt hoặc không chạy trước khi người dùng tương tác.
- Trang cha có thể dùng thuộc tính `sandbox` hạn chế điều hướng top-level.
- Nested iframe và các tình huống điều hướng có thể làm logic frame-busting phức tạp.
- Attacker có thể lợi dụng timing, popup hoặc cách trình duyệt xử lý navigation.
- Một đoạn script lỗi hoặc bị CSP chặn có thể làm cơ chế không hoạt động.

**Hãy dùng HTTP response header CSP `frame-ancestors` hoặc X-Frame-Options.** Browser thực thi chính sách framing trước khi người dùng tương tác với nội dung được nhúng.

## 9. Các cơ chế khác có thay chống framing không?

| Cơ chế | Có thay `frame-ancestors` không? | Giải thích |
| --- | :---: | --- |
| SameSite cookie | Không | Giảm một số trường hợp cookie được gửi cross-site; không ngăn tài liệu được nhúng hoặc bị che |
| CSRF token | Không | Xác minh request gắn với session; clickjacking có thể khiến người dùng gửi form có token hợp lệ |
| CORS | Không | Kiểm soát quyền đọc response cross-origin và preflight; không quyết định trang có được hiển thị trong iframe |
| SOP | Không | Giới hạn đọc dữ liệu cross-origin, không mặc định cấm nhúng |
| `frame-src` | Không | Kiểm soát iframe mà trang mình tải |
| `iframe sandbox` | Không | Hạn chế khả năng của nội dung trong iframe do trang cha nhúng; không phải chính sách chống trang khác nhúng ứng dụng của bạn |
| CSP `frame-ancestors` | Có | Kiểm soát ancestor nào được phép nhúng tài liệu |
| X-Frame-Options | Có, theo khả năng cũ | Cơ chế header chống framing với DENY/SAMEORIGIN |

### 9.1. iframe sandbox có tác dụng gì?

Thuộc tính `sandbox` trên iframe do **trang nhúng** đặt để giới hạn nội dung được nhúng, ví dụ hạn chế script, form submission, popup hoặc điều hướng top-level nếu không cấp quyền tương ứng.

Nó hữu ích khi ứng dụng của bạn nhúng nội dung không tin cậy. Nhưng nếu ứng dụng của bạn là trang mục tiêu và attacker nhúng trang đó, attacker kiểm soát thuộc tính iframe ở trang cha. Vì vậy sandbox do attacker chọn không phải biện pháp bảo vệ mà ứng dụng mục tiêu có thể dựa vào.

## 10. Giảm tác động khi thao tác nhạy cảm

Chống framing bằng response header là lớp bảo vệ chính. Với hành động có hậu quả lớn, ứng dụng nên bổ sung kiểm soát để một click đơn lẻ khó tạo thay đổi ngoài ý muốn:

1. Yêu cầu xác thực lại hoặc step-up authentication trước hành động quan trọng.
2. Hiển thị rõ đối tượng, số tiền, quyền hoặc phạm vi sẽ được thay đổi.
3. Với giao dịch nhạy cảm, dùng kênh xác nhận độc lập có hiển thị chi tiết giao dịch; tránh chỉ hỏi “Bạn có chắc không?” trong cùng giao diện có thể bị che.
4. Tách các bước cấp quyền hoặc thay đổi bảo mật thành luồng có xác nhận rõ ràng.
5. Ghi nhận audit event và gửi thông báo cho người dùng sau thay đổi quan trọng.
6. Cung cấp khả năng thu hồi quyền hoặc hủy phiên khi phát hiện thao tác bất thường.

Một hộp thoại xác nhận thông thường trong cùng trang vẫn có thể bị clickjacking nếu trang đó được nhúng và hộp thoại có thể bị căn chỉnh/che phủ. Biện pháp step-up cần bảo đảm người dùng nhìn thấy và xác nhận đúng thông tin trong một ngữ cảnh đáng tin cậy.

Không dùng một nút xác nhận thứ hai như biện pháp duy nhất. Kết hợp framing policy, xác thực lại và xác nhận giao dịch theo rủi ro.

## 11. Cấu hình header chống clickjacking

### 11.1. Trang không cho phép nhúng

~~~http
Content-Security-Policy: frame-ancestors 'none'
X-Frame-Options: DENY
~~~

Đây là cấu hình phù hợp cho phần lớn trang tài khoản, quản trị, đăng nhập và thanh toán không có nhu cầu nhúng.

### 11.2. Trang chỉ được nhúng cùng origin

~~~http
Content-Security-Policy: frame-ancestors 'self'
X-Frame-Options: SAMEORIGIN
~~~

Chỉ dùng khi ứng dụng thực sự có luồng iframe nội bộ và mọi trang cùng origin đều thuộc cùng ranh giới tin cậy.

### 11.3. Trang được nhúng bởi portal đối tác

~~~http
Content-Security-Policy: frame-ancestors 'self' https://portal.example.com
~~~

Với cấu hình này, browser CSP3 cho phép ancestor thuộc origin được liệt kê. X-Frame-Options không có cú pháp tương đương để cho phép một origin cụ thể; không thêm `SAMEORIGIN` nếu cần browser cũ nhúng từ portal khác origin.

### 11.4. Cấu hình theo route

Một ứng dụng có thể có các nhu cầu khác nhau:

| Nhóm trang | Chính sách gợi ý |
| --- | --- |
| Đăng nhập / tài khoản / cài đặt bảo mật | `frame-ancestors 'none'` |
| Trang nội bộ được nhúng trong dashboard cùng origin | `frame-ancestors 'self'` |
| Widget dành cho portal đối tác | Allowlist chính xác portal trong `frame-ancestors` |
| Nội dung công khai được thiết kế để nhúng | Allowlist các parent cần thiết; kiểm tra dữ liệu và quyền riêng |

Tránh cấu hình một allowlist rộng cho toàn bộ ứng dụng nếu chỉ một vài route cần được nhúng. Đặt header theo response của từng trang hoặc nhóm route, nhưng giữ chính sách nhất quán cho các trang có cùng mức độ nhạy cảm.

## 12. Thực hành: kiểm chứng clickjacking trên localhost

Bài thực hành dùng **Node.js 18 trở lên**, không cần package ngoài. Lab tạo hai origin khác nhau bằng hai port:

- `http://localhost:3000`: trang giả lập lời mời nhận quà.
- `http://localhost:3001`: trang mục tiêu có nút demo.

Trang attacker đặt iframe gần như trong suốt lên nút lời mời. Khi iframe được phép nhúng, click vào lời mời sẽ thực sự bấm nút trong trang mục tiêu. Sau đó bật header chống framing và quan sát browser chặn iframe.

Lab chỉ ghi nhận một thao tác demo trong terminal; không dùng tài khoản, cookie hoặc hành động thật.

### 12.1. Tạo file `clickjacking-lab.mjs`

~~~js
import { createServer } from 'node:http';

const victimPage = `<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <title>Victim demo</title>
  <style>
    body { margin: 0; font: 16px sans-serif; }
    button { width: 260px; height: 90px; font-size: 18px; }
    p { padding: 12px; }
  </style>
</head>
<body>
  <button id="target">Xác nhận thao tác demo</button>
  <p id="status">Chưa có thao tác.</p>
  <script>
    document.querySelector('#target').addEventListener('click', async () => {
      document.querySelector('#status').textContent = 'Nút thật trong trang mục tiêu đã được click.';
      await fetch('/action', { method: 'POST' });
    });
  </script>
</body>
</html>`;

const attackerPage = `<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <title>Clickjacking demo</title>
  <style>
    body { font: 16px sans-serif; padding: 20px; }
    #stage { position: relative; width: 340px; height: 150px; margin-top: 20px; }
    #bait {
      position: absolute; left: 0; top: 0;
      width: 260px; height: 90px;
      z-index: 1; font-size: 18px;
      background: #f2d36b; border: 2px solid #8b6b00;
    }
    #target-frame {
      position: absolute; left: 0; top: 0;
      width: 260px; height: 90px;
      z-index: 2; opacity: 0.01;
      border: 0; pointer-events: auto;
    }
    .controls { display: flex; gap: 8px; flex-wrap: wrap; }
  </style>
</head>
<body>
  <h1>Nhận phần thưởng demo</h1>
  <p>Nhấn nút bên dưới để xem hiệu ứng.</p>
  <div class="controls">
    <button id="unprotected">Tải trang không có bảo vệ</button>
    <button id="protected">Tải trang có frame protection</button>
  </div>
  <div id="stage">
    <button id="bait">Nhấn để nhận quà</button>
    <iframe id="target-frame" title="Demo target page"
      src="http://localhost:3001/unprotected"></iframe>
  </div>
  <p>Trang iframe gần như trong suốt nằm trên nút giả. Mở DevTools để quan sát.</p>
  <script>
    const frame = document.querySelector('#target-frame');
    document.querySelector('#unprotected').addEventListener('click', () => {
      frame.src = 'http://localhost:3001/unprotected';
    });
    document.querySelector('#protected').addEventListener('click', () => {
      frame.src = 'http://localhost:3001/protected';
    });
    document.querySelector('#bait').addEventListener('click', () => {
      alert('Đây là nút giả của trang demo.');
    });
  </script>
</body>
</html>`;

createServer((req, res) => {
  const path = new URL(req.url, 'http://localhost:3001').pathname;

  if (path === '/unprotected' || path === '/protected') {
    const headers = {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-store',
    };

    if (path === '/protected') {
      headers['Content-Security-Policy'] = "frame-ancestors 'none'";
      headers['X-Frame-Options'] = 'DENY';
    }

    res.writeHead(200, headers);
    res.end(victimPage);
    return;
  }

  if (path === '/action' && req.method === 'POST') {
    console.log('[victim] Demo action received from iframe click.');
    res.writeHead(204, { 'Cache-Control': 'no-store' });
    res.end();
    return;
  }

  res.writeHead(404);
  res.end('Not found');
}).listen(3001, () => {
  console.log('Victim: http://localhost:3001');
});

createServer((req, res) => {
  if (req.url === '/') {
    res.writeHead(200, {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-store',
    });
    res.end(attackerPage);
    return;
  }
  res.writeHead(404);
  res.end('Not found');
}).listen(3000, () => {
  console.log('Attacker demo: http://localhost:3000');
});
~~~

### 12.2. Chạy lab

Chạy:

~~~bash
node clickjacking-lab.mjs
~~~

Mở `http://localhost:3000`:

1. Đảm bảo iframe đang tải `/unprotected`.
2. Di chuột và click vào nút vàng **Nhấn để nhận quà**.
3. Trang mục tiêu nằm trong iframe gần như trong suốt nhận click; terminal hiển thị log `[victim] Demo action received...`.
4. Trong DevTools → Elements, chọn iframe và tạm đổi `opacity` thành `1` để nhìn thấy nút thật nằm dưới nút giả.
5. Nhấn **Tải trang có frame protection**. Browser sẽ chặn trang mục tiêu được hiển thị trong iframe vì response có `frame-ancestors 'none'` và `X-Frame-Options: DENY`.
6. Mở DevTools → Console để xem thông báo vi phạm framing policy.

### 12.3. Vì sao hai port tạo ra hai origin?

`http://localhost:3000` và `http://localhost:3001` có scheme và hostname giống nhau nhưng port khác nhau, do đó là **hai origin khác nhau**. SOP không cho trang attacker đọc DOM của iframe mục tiêu, nhưng browser vẫn có thể hiển thị iframe nếu response không cấm framing.

Lab không cần CORS để hiển thị iframe và không dùng cookie xác thực. Mục tiêu là chứng minh việc nhúng và định tuyến click có thể xảy ra dù parent không đọc được nội dung cross-origin.

### 12.4. Thử các chính sách khác

Trong response `/protected`, thay `frame-ancestors 'none'` bằng:

~~~http
Content-Security-Policy: frame-ancestors 'self'
~~~

Vì attacker và victim dùng hai port khác nhau, iframe vẫn bị chặn. Nếu cả trang cha và trang con cùng origin, `'self'` mới cho phép.

Thử bỏ CSP và giữ:

~~~http
X-Frame-Options: DENY
~~~

để quan sát cơ chế tương thích XFO. Sau đó thử `SAMEORIGIN` và so sánh. Không dùng `ALLOW-FROM` cho cấu hình mới.

### 12.5. Giới hạn của lab

- Đây là mô phỏng giao diện, không có đăng nhập, cookie session hoặc giao dịch thật.
- Lab dùng HTTP localhost để dễ chạy; production nên dùng HTTPS.
- Hành vi console và thông báo chặn có thể khác giữa browser/version.
- Không đưa URL hoặc tài khoản của bên thứ ba vào lab; chỉ thử trên hai server local.

## 13. Checklist review chống clickjacking

Khi review ứng dụng web:

1. **Kiểm kê trang nhạy cảm:** login, tài khoản, quản trị, cài đặt, cấp quyền, thanh toán và xác nhận giao dịch.
2. **Kiểm tra response header:** có CSP `frame-ancestors` hoặc X-Frame-Options trên mọi trang cần bảo vệ không?
3. **Chọn policy chặt:** dùng `'none'` nếu không cần nhúng; `'self'` hoặc allowlist origin cụ thể khi có yêu cầu sản phẩm.
4. **Kiểm tra toàn bộ ancestor chain:** nếu cho phép portal, xác định mọi lớp iframe trung gian.
5. **Không dùng meta:** `frame-ancestors` phải được gửi bằng HTTP response header.
6. **Phân biệt directive:** `frame-src` kiểm soát iframe trang mình tải; `frame-ancestors` kiểm soát ai được nhúng mình.
7. **Đồng bộ XFO:** nếu dùng XFO cho browser cũ, bảo đảm không mâu thuẫn với CSP; tránh `ALLOW-FROM`.
8. **Không dựa vào frame-busting:** JavaScript detection chỉ là lớp phụ, không thay header.
9. **Kiểm tra cookie/site:** không coi SameSite hoặc third-party cookie blocking là chống framing.
10. **Bảo vệ hành động nhạy cảm:** xác thực lại, hiển thị chi tiết và xác nhận độc lập khi rủi ro yêu cầu.
11. **Kiểm thử nhiều browser:** mở trang từ origin không tin cậy, cùng origin, subdomain cùng site và nested iframe.
12. **Kiểm tra các response:** trang đăng nhập, lỗi, redirect và các route có nội dung nhạy cảm đều cần policy phù hợp.

## 14. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “SOP ngăn trang khác nhúng website của tôi.” | SOP giới hạn đọc dữ liệu cross-origin; framing cần được kiểm soát riêng. |
| “Không đọc được iframe nghĩa là không click được.” | Browser vẫn định tuyến click tới phần tử trong iframe dù parent không đọc được DOM. |
| “CORS chặn clickjacking.” | CORS không quyết định trang có được hiển thị trong iframe hay không. |
| “CSRF token ngăn mọi clickjacking.” | Trang thật trong iframe có thể đã chứa token hợp lệ; click của nạn nhân vẫn gửi form đó. |
| “SameSite cookie là đủ.” | SameSite giảm một số request cross-site nhưng không ngăn framing và không bao phủ mọi ngữ cảnh same-site. |
| “frame-src bảo vệ trang khỏi bị nhúng.” | `frame-src` kiểm soát iframe trang hiện tại tải; `frame-ancestors` kiểm soát ai được nhúng trang hiện tại. |
| “Có thể dùng meta CSP cho frame-ancestors.” | Directive này phải được gửi qua HTTP response header. |
| “JavaScript frame-busting là đủ.” | Script có thể bị tắt, sandbox hoặc timing làm vô hiệu; dùng CSP/XFO. |
| “Một hộp thoại xác nhận luôn ngăn clickjacking.” | Hộp thoại trong cùng trang cũng có thể bị căn chỉnh/che; thao tác nhạy cảm cần xác nhận độc lập phù hợp. |
| “iframe sandbox do attacker đặt bảo vệ trang mục tiêu.” | Sandbox là giới hạn do parent áp dụng cho nội dung nhúng; trang mục tiêu cần tự đặt frame policy bằng response header. |

## 15. Câu hỏi tự đánh giá

**Câu 1.** Clickjacking là gì và vì sao còn được gọi là UI redressing?

**Gợi ý trả lời:** Attacker làm người dùng tưởng đang tương tác với một thành phần giao diện nhưng browser thực sự gửi click tới thành phần khác bị che hoặc ngụy trang.

**Câu 2.** Vì sao SOP không ngăn được iframe overlay cross-origin?

**Gợi ý trả lời:** SOP hạn chế parent đọc DOM cross-origin, nhưng không mặc định cấm browser tải và hiển thị trang đó trong iframe hoặc chuyển click tới nội dung bên trong.

**Câu 3.** Header nào là biện pháp chính để cấm mọi trang nhúng một tài liệu?

**Gợi ý trả lời:** CSP `frame-ancestors 'none'`; có thể bổ sung `X-Frame-Options: DENY` cho tương thích browser cũ.

**Câu 4.** `frame-src` khác `frame-ancestors` thế nào?

**Gợi ý trả lời:** `frame-src` giới hạn nguồn iframe mà trang hiện tại tải; `frame-ancestors` giới hạn các trang cha được phép nhúng tài liệu hiện tại.

**Câu 5.** Vì sao CSRF token không thay thế frame protection?

**Gợi ý trả lời:** Người dùng có thể đang tương tác với form thật trong iframe; form đó đã có token hợp lệ. Clickjacking đánh lừa giao diện, còn token chỉ xác minh request gắn với session.

**Câu 6.** Khi nào nên dùng `frame-ancestors 'self'` thay vì `'none'`?

**Gợi ý trả lời:** Khi sản phẩm thực sự cần trang cùng origin nhúng tài liệu; nếu không có nhu cầu, `'none'` có bề mặt cho phép nhỏ hơn.

**Câu 7.** Vì sao không nên dựa riêng vào JavaScript frame-busting?

**Gợi ý trả lời:** Script có thể không chạy, bị sandbox hạn chế hoặc bị ảnh hưởng bởi timing/nested frame. Header CSP/XFO được browser thực thi trực tiếp trước khi người dùng tương tác.

## Tài liệu tham khảo

- W3C — [Content Security Policy Level 3: frame-ancestors](https://www.w3.org/TR/CSP3/#directive-frame-ancestors).
- MDN — [CSP: frame-ancestors](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/frame-ancestors), [X-Frame-Options](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Frame-Options).
- OWASP — [Clickjacking Defense Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Clickjacking_Defense_Cheat_Sheet.html).
- OWASP — [Clickjacking](https://owasp.org/www-community/attacks/Clickjacking).
- MDN — [Same-origin policy](https://developer.mozilla.org/en-US/docs/Web/Security/Same-origin_policy), [iframe sandbox](https://developer.mozilla.org/en-US/docs/Web/HTML/Element/iframe#sandbox).
