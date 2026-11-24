# Case study: Clickjacking trang quản trị

## 1. Bối cảnh

Một công ty vận hành cổng quản trị tại **https://admin.example.test**. Nhân viên quản trị đăng nhập để quản lý tài khoản, phân quyền và cấu hình hệ thống. Cổng này có một màn hình xác nhận thay đổi quyền với nút **Lưu thay đổi**. Người dùng thường mở trang quản trị trong cùng một browser profile với các trang web khác.

Một ngày, bộ phận hỗ trợ nhận được phản ánh rằng một quản trị viên đã vô tình xác nhận thay đổi quyền sau khi truy cập một trang quảng bá bên ngoài tại **https://promo.example.test**. Audit log cho thấy thao tác được thực hiện bằng session hợp lệ của quản trị viên. Không có bằng chứng cho thấy mật khẩu hoặc cookie bị đánh cắp.

Điều tra cho thấy trang quảng bá đã nhúng màn hình quản trị vào một iframe. Trang bên ngoài hiển thị lời mời nhận báo cáo, còn iframe gần như trong suốt và được căn vị trí để nút quản trị nằm ngay dưới vị trí người dùng được dụ bấm. Người dùng nhìn thấy nút trên trang quảng bá, nhưng browser nhận click tại nút trong iframe.

Đây là tình huống **clickjacking**, còn gọi là UI redressing: kẻ tấn công khiến người dùng tương tác với một giao diện thật nhưng bị che giấu hoặc trình bày sai ngữ cảnh. Mục tiêu của case study là lần theo cách sự cố xảy ra, đánh giá tác động, chọn biện pháp phòng vệ và xây dựng kiểm thử để ngăn tái diễn.

> Toàn bộ domain, tài khoản, dữ liệu và thao tác trong bài là giả lập. Các bước tái hiện chỉ thực hiện trong lab do nhóm kiểm soát, với trang quản trị mẫu và dữ liệu không có giá trị thật.

Sau bài học, bạn có thể:

- Giải thích vì sao Same-Origin Policy không tự ngăn clickjacking.
- Phân biệt clickjacking với CSRF, XSS và việc đánh cắp session.
- Đọc dấu hiệu iframe trong browser và request log.
- Đánh giá tác động của một click được thực hiện bằng session quản trị hợp lệ.
- Chọn CSP frame-ancestors và X-Frame-Options phù hợp.
- Kiểm tra header trên response thực tế và kiểm thử hành vi framing bằng browser.
- Lập kế hoạch containment, sửa lỗi, triển khai và theo dõi sau sự cố.

## 2. Kiến trúc và ranh giới tin cậy

Hệ thống trong tình huống gồm ba thành phần:

| Thành phần | Vai trò | Mức độ tin cậy |
| --- | --- | --- |
| **admin.example.test** | Cổng quản trị, chứa trang đổi quyền và session nhân viên | Tin cậy, có chức năng nhạy cảm |
| **promo.example.test** | Trang quảng bá bên ngoài, do bên thứ ba kiểm soát trong kịch bản | Không tin cậy |
| Browser của nhân viên | Giữ session, render cả trang quảng bá và iframe quản trị | Môi trường thực thi của người dùng |

Sơ đồ luồng khi chưa có biện pháp chống framing:

~~~mermaid
flowchart TD
    U["Nhân viên đang đăng nhập"] --> B["Browser"]
    B --> P["promo.example.test"]
    P --> I["iframe: admin.example.test"]
    I --> A["Trang xác nhận thay đổi quyền"]
    U --> C["Click tại vị trí lời mời trên trang quảng bá"]
    C --> I
    I --> R["Request cùng origin tới admin"]
    R --> S["Server xử lý bằng session hợp lệ"]
~~~

Điểm quan trọng là browser có thể hiển thị một tài liệu trong iframe mà không cho trang cha đọc nội dung của tài liệu đó. Same-Origin Policy giới hạn việc script ở origin quảng bá đọc DOM hoặc dữ liệu của origin quản trị; nó không mặc định cấm browser vẽ trang quản trị trong iframe và cũng không ngăn người dùng click vào nội dung đang hiển thị.

## 3. Diễn biến sự cố

### 3.1 Trước sự cố

Cổng quản trị cho phép một số trang được nhúng để phục vụ dashboard nội bộ. Trong quá trình phát triển, cấu hình frame protection không được áp dụng nhất quán cho các route quản trị. Trang xác nhận thay đổi quyền vẫn trả về HTML bình thường khi được tải trong iframe từ một origin khác.

Trang này có session cookie hợp lệ. Endpoint xử lý thao tác kiểm tra session và quyền quản trị ở server, nhưng UI không có lớp xác nhận bổ sung cho thao tác nhạy cảm. Việc xác thực request ở server là cần thiết, song không giải quyết được việc người dùng bị đánh lừa để chủ động click vào nút thật.

### 3.2 Chuỗi sự kiện

| Thời điểm | Sự kiện | Quan sát |
| --- | --- | --- |
| T0 | Quản trị viên đăng nhập cổng quản trị | Browser có session hợp lệ |
| T1 | Quản trị viên mở trang quảng bá | Trang ngoài được tải ở top-level |
| T2 | Trang quảng bá tải iframe tới trang quản trị | Browser gửi request tới admin trong ngữ cảnh frame |
| T3 | Iframe được căn dưới lời mời hiển thị | Người dùng không nhận biết nút quản trị thật |
| T4 | Người dùng click lời mời | Click đi vào nút trong iframe |
| T5 | Trang quản trị gửi request xác nhận | Server nhận request cùng session hợp lệ |
| T6 | Quyền được thay đổi | Audit log ghi nhận thao tác của tài khoản quản trị |
| T7 | Người dùng phản ánh | Nhóm vận hành mở điều tra |

### 3.3 Vì sao thao tác có thể thành công?

Browser đã tải trang quản trị trong iframe. Khi người dùng click đúng vị trí, sự kiện click được chuyển tới tài liệu đang nằm ở lớp trên cùng tại tọa độ đó. Nếu nút trong iframe thực hiện thao tác hợp lệ, trang quản trị có thể gửi request bằng session mà browser đang có.

Trang quảng bá không cần đọc DOM quản trị, không cần lấy cookie và không cần vượt qua CORS. Kịch bản dựa vào việc người dùng nhìn thấy một nội dung nhưng tương tác với nội dung khác.

## 4. Mô hình clickjacking

### 4.1 Lớp giao diện bị đánh tráo

Trang ngoài hiển thị một lời mời hoặc nút hấp dẫn. Một iframe được đặt phía trên hoặc phía dưới phần tử đó, có kích thước và vị trí được căn để vùng click trùng với nút thật trong trang quản trị. Iframe có thể được làm gần như trong suốt, khiến người dùng khó nhận ra giao diện bên dưới.

~~~text
+--------------------------------------------------+
| Trang quảng bá                                   |
|                                                  |
|             Nhận báo cáo miễn phí                |
|             [ XEM BÁO CÁO ]                      |
|                                                  |
|  Iframe quản trị trong suốt nằm cùng vị trí:     |
|  [ LƯU THAY ĐỔI QUYỀN ]                          |
+--------------------------------------------------+

Người dùng nhìn thấy: [ XEM BÁO CÁO ]
Browser nhận click: [ LƯU THAY ĐỔI QUYỀN ]
~~~

Các biến thể có thể dùng lớp phủ, căn chỉnh con trỏ, drag-and-drop hoặc nhiều bước click. Tuy nhiên, nguyên tắc chung vẫn là làm sai lệch mối quan hệ giữa ý định của người dùng và phần tử mà browser thực sự nhận tương tác.

### 4.2 Mô phỏng trong lab

Chỉ dùng hai host giả lập do nhóm kiểm soát, ví dụ **admin.example.test** và **promo.example.test**, cùng một trang quản trị mẫu không kết nối hệ thống thật. Trang mẫu chỉ ghi nhận trạng thái vào giao diện hoặc console, không thực hiện thay đổi tài khoản, quyền, thanh toán hay dữ liệu thật.

Trang quảng bá minh họa có thể chứa một iframe:

~~~html
<main class="promo">
  <h1>Nhận báo cáo mẫu</h1>
  <button class="visible-bait" type="button">Xem báo cáo</button>
  <iframe
    class="admin-preview"
    src="https://admin.example.test/lab/confirm"
    title="Trang quản trị mẫu">
  </iframe>
</main>
~~~

CSS trong lab có thể làm iframe gần như trong suốt và đặt lên trên vùng nút lời mời:

~~~css
.promo {
  position: relative;
  width: 720px;
  height: 420px;
}

.visible-bait {
  position: absolute;
  left: 260px;
  top: 180px;
  z-index: 1;
}

.admin-preview {
  position: absolute;
  left: 0;
  top: 0;
  width: 720px;
  height: 420px;
  opacity: 0.01;
  border: 0;
  z-index: 2;
}
~~~

Vị trí nút trong trang lab quản trị phải được bố trí có chủ đích để kiểm tra sự trùng tọa độ. Không sử dụng đoạn mô phỏng này để nhúng trang quản trị thật hoặc dụ người dùng ngoài lab. Khi hoàn tất bài kiểm tra, bật frame protection và xác minh browser từ chối tải trang quản trị trong iframe.

### 4.3 Quan sát trong DevTools

Mở tab Network và chọn request tài liệu quản trị được tải trong iframe. Kiểm tra:

- Request URL và host đích.
- Request được khởi tạo với ngữ cảnh frame hay top-level navigation.
- Request headers như **Sec-Fetch-Dest** và **Sec-Fetch-Site** nếu browser gửi.
- Response headers có CSP và X-Frame-Options hay không.
- Console có thông báo browser chặn việc hiển thị trong frame hay không.

Với một request điều hướng iframe cross-site, **Sec-Fetch-Dest** thường có giá trị **iframe** và **Sec-Fetch-Site** có thể là **cross-site**. Nếu hai host thuộc cùng site theo quy tắc schemeful same-site, giá trị có thể là **same-site**. Không xem các header này là bằng chứng duy nhất vì browser support, redirect, proxy và cấu trúc frame có thể làm thay đổi quan sát.

## 5. Phân biệt clickjacking với các lỗi bảo mật khác

| Cơ chế | Điều attacker cần | Điều bị lạm dụng | Kiểm soát chính |
| --- | --- | --- | --- |
| Clickjacking | Làm người dùng click hoặc kéo thả vào giao diện bị che | Cách browser hiển thị và nhận tương tác trong frame | CSP frame-ancestors, X-Frame-Options |
| CSRF | Khiến browser gửi request ngoài ý muốn tới ứng dụng | Cookie/session tự động được gửi trong request | CSRF token, SameSite, kiểm tra Origin/Fetch Metadata |
| XSS | Đưa script không tin cậy vào execution context của ứng dụng | Khả năng thực thi script cùng origin | Output encoding, sanitizer, Trusted Types, CSP |
| Session theft | Lấy hoặc sử dụng credential/session trái phép | Credential hoặc token | HttpOnly, Secure, rotation, session protection |

Các cơ chế có thể kết hợp. Một trang bị XSS có thể tạo giao diện lừa click bên trong ứng dụng; một trang clickjacking có thể dụ người dùng kích hoạt một hành động nhạy cảm. Tuy vậy, clickjacking không đòi hỏi attacker đọc cookie hoặc chạy JavaScript trong origin quản trị.

### 5.1 Same-Origin Policy và CORS không chặn việc hiển thị iframe

Same-Origin Policy ngăn script của trang quảng bá đọc nội dung DOM của trang quản trị vì hai origin khác nhau. CORS điều khiển việc JavaScript đọc response từ một số request cross-origin. Cả hai không phải cơ chế quyết định trang quản trị có được phép hiển thị bên trong frame của trang khác hay không.

Quyền nhúng được kiểm soát bằng CSP **frame-ancestors** và, để tương thích với browser cũ, X-Frame-Options. Không dùng CORS để thay thế các header này.

### 5.2 CSRF token không tự chặn clickjacking

CSRF token giúp server xác minh request có token hợp lệ gắn với session hoặc biểu mẫu. Trong clickjacking, browser tải trang quản trị thật vào iframe; token có thể đã nằm trong form hoặc DOM của trang đó. Người dùng bị dụ click nút thật và browser gửi form hợp lệ. Trang cha không cần đọc token.

CSRF defense vẫn cần thiết vì request giả mạo có thể xảy ra theo những đường khác. Nhưng muốn ngăn trang quản trị bị nhúng, cần chính sách chống framing.

### 5.3 SameSite cookie có thể giảm một số kịch bản nhưng không thay thế frame protection

Cookie **SameSite=Lax** hoặc **SameSite=Strict** thường không được gửi trong điều hướng iframe cross-site theo quy tắc SameSite. Điều này có thể khiến một số kịch bản clickjacking cross-site không còn session đăng nhập trong frame. Tuy nhiên:

- Một subdomain khác có thể là same-site nhưng vẫn là cross-origin.
- Cookie **SameSite=None; Secure** có thể được gửi trong ngữ cảnh cross-site nếu browser policy cho phép.
- Chính sách chặn third-party cookie thay đổi theo browser và cấu hình người dùng.
- Một trang có thể đã có trạng thái xác thực khác hoặc luồng nhạy cảm không dựa hoàn toàn vào cookie.

Vì vậy, hãy cấu hình frame protection trực tiếp cho trang nhạy cảm. SameSite là một lớp kiểm soát cookie và CSRF, không phải allowlist/denylist framing.

## 6. Đánh giá tác động trong case study

### 6.1 Tác động kỹ thuật

Trong tình huống, thao tác quản trị được thực hiện qua giao diện thật và endpoint hợp lệ. Server kiểm tra session và role, vì vậy request vượt qua xác thực. Lỗ hổng nằm ở việc người dùng không biết mình đang tương tác với trang quản trị được nhúng.

Những tác động có thể xảy ra tùy chức năng bị đặt dưới lớp phủ:

- Thay đổi quyền người dùng hoặc cấu hình truy cập.
- Tạo, thu hồi hoặc thay đổi credential nếu UI cho phép thao tác đó.
- Phê duyệt giao dịch, yêu cầu hoặc thay đổi nghiệp vụ.
- Thay đổi cấu hình bảo mật hoặc tắt một kiểm soát.
- Tiết lộ thông tin qua thao tác export hoặc điều hướng tới trang nhạy cảm.

Clickjacking không tự cấp quyền cao hơn session hiện tại. Attacker có thể khiến nạn nhân thực hiện những hành động mà chính nạn nhân được phép thực hiện trong giao diện bị nhúng.

### 6.2 Tác động nghiệp vụ

Một thao tác đổi quyền có thể dẫn đến tài khoản khác được cấp quyền ngoài dự kiến. Nhóm vận hành cần kiểm tra:

1. Ai thực hiện thao tác theo audit log?
2. Tài khoản đó có đang đăng nhập tại thời điểm truy cập trang quảng bá không?
3. Quyền nào được thay đổi, trên đối tượng nào và vào thời điểm nào?
4. Có thao tác tiếp theo nào được thực hiện bằng quyền mới không?
5. Có người dùng khác truy cập cùng trang quảng bá hoặc nội dung nhúng không?
6. Có thể khôi phục cấu hình về trạng thái trước sự cố bằng quy trình được phê duyệt không?

Không kết luận rằng tài khoản quản trị bị chiếm đoạt chỉ từ một request hợp lệ. Cần phân biệt thao tác bị lừa thực hiện với credential bị đánh cắp, đồng thời kiểm tra audit trail để xác định có hoạt động trái phép khác hay không.

### 6.3 Mức độ ưu tiên

Đối với trang quản trị có quyền thay đổi tài khoản hoặc cấu hình bảo mật, khả năng nhúng từ origin không tin cậy thường cần được xử lý ở mức cao. Mức độ cuối cùng phụ thuộc vào:

- Các route có thể bị nhúng và thao tác nhạy cảm nằm trên đó.
- Điều kiện để nạn nhân có session hợp lệ.
- Khả năng tiếp cận người dùng và mức tương tác cần thiết.
- Bằng chứng thao tác đã xảy ra và hậu quả thực tế.
- Việc attacker có thể kiểm soát một origin cùng site hoặc một origin đã được allowlist hay không.

## 7. Điều tra và bảo toàn bằng chứng

### 7.1 Thu thập bằng chứng

| Nguồn | Dữ liệu cần ghi | Lưu ý |
| --- | --- | --- |
| Browser Network | URL, thời điểm, request destination, response headers | Redact cookie và token |
| Browser Console | Thông báo frame bị chặn hoặc lỗi tải | Ghi browser/version |
| Access log | Route, method, status, request ID, Fetch Metadata nếu có | Không ghi raw credential |
| Audit log | Actor, action, target, before/after, timestamp | Kiểm tra tính toàn vẹn |
| Deployment config | CSP, X-Frame-Options, middleware và route scope | Gắn với release ID |
| User report | Trang đã mở, thao tác đã thấy, thời điểm | Không yêu cầu người dùng gửi mật khẩu hoặc session |

### 7.2 Dấu hiệu cần tương quan

- Request tới trang quản trị có **Sec-Fetch-Dest: iframe**.
- **Sec-Fetch-Site** thể hiện ngữ cảnh cross-site hoặc same-site.
- Header **Referer** có thể cho biết trang cha nếu referrer policy cho phép.
- Một state-changing request xuất hiện ngay sau khi tài liệu quản trị được tải trong frame.
- Audit log ghi nhận thao tác nhạy cảm trong session của người đã mở trang quảng bá.

Các dấu hiệu trên chỉ hỗ trợ điều tra. Referrer có thể bị rút gọn hoặc không được gửi; Fetch Metadata có thể không có ở một số client; request điều khiển thao tác bên trong frame có thể mang **Sec-Fetch-Site: same-origin** vì nó phát sinh từ chính tài liệu quản trị. Hãy ghép nhiều nguồn theo request ID và thời gian.

### 7.3 Bảo vệ dữ liệu điều tra

- Không lưu raw Cookie, Set-Cookie, Authorization hoặc token trong ticket.
- Redact query string và dữ liệu cá nhân trong HAR, screenshot, video và DOM snapshot.
- Lưu audit event và log gốc trong kho có phân quyền theo quy trình.
- Ghi lại hash hoặc ID tham chiếu của bằng chứng khi cần xác minh tính toàn vẹn.
- Hạn chế quyền xem bằng chứng và ghi nhận người truy cập.

## 8. Phân tích nguyên nhân gốc

### 8.1 Lỗ hổng cấu hình

Trang quản trị không có CSP **frame-ancestors** hoặc X-Frame-Options phù hợp. Một số route có header, nhưng route xác nhận thay đổi quyền lại thiếu do middleware chỉ được gắn ở một nhóm controller.

### 8.2 Lỗ hổng trong thiết kế

Ứng dụng có chức năng nhúng dashboard nhưng chưa phân loại route nào được phép nhúng. Cấu hình cho trang dashboard vô tình được xem như chính sách chung của cả khu vực quản trị. Không có danh sách origin đối tác được review và không có tiêu chí kiểm thử framing trong release checklist.

### 8.3 Lỗ hổng trong kiểm thử

Kiểm thử trước release chỉ xác minh trang hoạt động khi mở trực tiếp. Nhóm QA chưa thử mở trang quản trị từ một origin khác bằng iframe, chưa kiểm tra response headers trên mọi route và chưa kiểm tra các browser được hỗ trợ.

### 8.4 Lỗ hổng trong vận hành

Log chưa ghi Fetch Metadata hoặc request correlation đủ để xác định tài liệu được tải trong frame. Audit log có actor và action nhưng chưa liên kết rõ với request ID, khiến việc đối chiếu mất thêm thời gian.

### 8.5 Chuỗi nguyên nhân

~~~mermaid
flowchart TD
    A["Route quản trị thiếu frame policy"] --> B["Browser cho phép hiển thị trong iframe"]
    B --> C["Trang ngoài phủ giao diện và đánh tráo ý định click"]
    C --> D["Quản trị viên click nút thật"]
    D --> E["Request hợp lệ mang session của quản trị viên"]
    E --> F["Thay đổi trạng thái quản trị"]
    G["Thiếu test framing và audit correlation"] --> H["Phát hiện và điều tra chậm hơn"]
~~~

## 9. Phương án khắc phục

### 9.1 Chặn framing cho khu vực quản trị

Với trang quản trị không có nhu cầu nhúng, dùng CSP **frame-ancestors 'none'**:

~~~http
Content-Security-Policy: frame-ancestors 'none'
X-Frame-Options: DENY
~~~

**frame-ancestors** quy định origin nào được phép làm ancestor của tài liệu. Giá trị **'none'** cấm mọi trang khác nhúng tài liệu đó, kể cả cùng origin. **X-Frame-Options: DENY** là lớp tương thích cho browser cũ hơn.

Nếu ứng dụng có CSP hiện hữu, thêm directive **frame-ancestors** vào policy đang dùng và kiểm tra response cuối cùng. Không ghi đè toàn bộ CSP hiện tại chỉ để thêm một directive, vì có thể vô tình loại bỏ các kiểm soát script, object, base URL hoặc resource khác.

### 9.2 Chỉ cho phép nhúng khi có yêu cầu nghiệp vụ rõ ràng

Nếu một trang dashboard thực sự cần được nhúng trong portal nội bộ, hãy khai báo danh sách origin cụ thể:

~~~http
Content-Security-Policy: frame-ancestors 'self' https://portal.example.test
~~~

Chỉ thêm origin đã được xác minh quyền sở hữu, mục đích và quy trình quản lý thay đổi. Không dùng wildcard rộng hoặc cho phép mọi subdomain nếu không có lý do kiến trúc. Browser kiểm tra toàn bộ ancestor chain; mọi ancestor phải thỏa policy.

X-Frame-Options chỉ hỗ trợ các lựa chọn hạn chế như **DENY** và **SAMEORIGIN** trong thực tế hiện đại; **ALLOW-FROM** đã lỗi thời và không phải cách tương thích để khai báo allowlist nhiều origin. Khi cần external allowlist, dựa vào CSP frame-ancestors và xác định rõ browser support. Không thêm **X-Frame-Options: SAMEORIGIN** như fallback nếu cần cho phép portal khác origin nhúng trang, vì browser cũ chỉ hiểu X-Frame-Options có thể chặn cả portal hợp lệ đó.

### 9.3 Hiểu đúng các directive

| Cơ chế | Điều khiển | Dùng cho case này |
| --- | --- | --- |
| CSP frame-ancestors | Ai được phép nhúng trang hiện tại | Có, là kiểm soát chính |
| X-Frame-Options | Hạn chế framing theo cơ chế cũ | Có, làm lớp tương thích |
| CSP frame-src | Trang hiện tại được tải frame từ đâu | Không thay thế frame-ancestors |
| CSP default-src | Fallback cho một số nhóm resource | Không tự áp dụng thay frame-ancestors |
| CORS | JavaScript có được đọc response cross-origin hay không | Không ngăn hiển thị iframe |
| SameSite cookie | Điều kiện gửi cookie theo site context | Lớp kiểm soát cookie bổ sung |

**frame-ancestors** phải được gửi trong HTTP response header. Đặt directive này trong thẻ meta không có tác dụng. Nó cũng không kế thừa từ **default-src**, vì vậy phải khai báo rõ ràng.

### 9.4 Áp dụng nhất quán cho route nhạy cảm

Phạm vi cần kiểm tra gồm:

- Trang đăng nhập và xác thực lại.
- Dashboard quản trị.
- Trang chi tiết tài khoản và phân quyền.
- Form xác nhận thay đổi cấu hình.
- Trang tạo hoặc thu hồi credential.
- Trang phê duyệt và giao dịch nhạy cảm.
- Error page hoặc trang HTML được trả về từ reverse proxy nếu có thể hiển thị thông tin nhạy cảm.

Đảm bảo header có mặt trên mọi response HTML liên quan, kể cả response lỗi. Kiểm tra middleware order, reverse proxy, CDN và framework có thể ghi đè hoặc loại bỏ header.

### 9.5 Tăng cường bảo vệ thao tác nhạy cảm

Frame protection là biện pháp trực tiếp cho clickjacking. Có thể bổ sung:

- Yêu cầu xác nhận lại cho thao tác có tác động lớn.
- Hiển thị rõ đối tượng và thay đổi trước khi xác nhận.
- Yêu cầu step-up authentication cho thay đổi quyền hoặc credential.
- Dùng transaction approval gắn với nội dung hành động khi nghiệp vụ yêu cầu.
- Ghi audit event gồm actor, action, target, before/after, request ID và thời điểm.
- Tách quyền quản trị theo least privilege và yêu cầu phê duyệt kép với hành động đặc biệt.

Các bước xác nhận trong cùng trang vẫn có thể bị nhúng và clickjacked. Chúng là lớp giảm tác động, không thay thế việc chặn framing. Với hành động đặc biệt quan trọng, cần cơ chế xác nhận gắn với nội dung giao dịch và có khả năng cho người dùng nhận biết rõ điều họ đang phê duyệt.

### 9.6 Không dựa vào frame-busting JavaScript

Các đoạn script kiểm tra **window.top** hoặc cố điều hướng trang ra khỏi frame có thể bị vô hiệu hóa bởi sandbox, browser behavior, script error hoặc cách nhúng phức tạp. Chúng cũng có thể tạo lỗi chức năng. Dùng header do browser thực thi làm kiểm soát chính; JavaScript frame-busting nếu còn tồn tại chỉ nên là lớp phụ đã được đánh giá.

## 10. Kế hoạch triển khai

### Giai đoạn 1: Containment

1. Xác định các route quản trị có thể thực hiện hành động nhạy cảm.
2. Áp dụng **frame-ancestors 'none'** cho các route không cần nhúng.
3. Bổ sung **X-Frame-Options: DENY** cho compatibility.
4. Kiểm tra header trên response thực tế qua CDN và reverse proxy.
5. Nếu cần thời gian để triển khai bản sửa hoàn chỉnh, tạm vô hiệu hóa chức năng nhạy cảm hoặc yêu cầu xác thực lại theo đánh giá rủi ro.

### Giai đoạn 2: Remediation

1. Chuẩn hóa middleware hoặc security header configuration dùng chung.
2. Lập danh sách route được phép nhúng và owner của từng ngoại lệ.
3. Xóa ngoại lệ không còn nhu cầu.
4. Bổ sung audit correlation và Fetch Metadata logging đã giảm dữ liệu.
5. Bổ sung kiểm thử framing vào pipeline và release checklist.

### Giai đoạn 3: Rollout và giám sát

1. Kiểm tra chức năng dashboard nội bộ có nhu cầu nhúng hợp lệ.
2. Chạy browser matrix trên các browser/version được hỗ trợ.
3. Triển khai theo môi trường và theo dõi lỗi tích hợp.
4. Theo dõi request iframe bất thường và các thao tác quản trị sau khi trang được tải.
5. Xác minh không có route quản trị mới nào thiếu policy.

## 11. Kiểm thử xác minh bản sửa

### 11.1 Kiểm tra header từ server

Dùng request tới route thực tế:

~~~bash
curl -sSI https://admin.example.test/admin/settings
~~~

Kết quả mong đợi có:

~~~http
Content-Security-Policy: frame-ancestors 'none'
X-Frame-Options: DENY
~~~

Lặp lại với các route nhạy cảm, trang đăng nhập, response lỗi và các hostname được phục vụ qua CDN. Curl chỉ xác minh header server trả về; nó không chứng minh browser đã chặn iframe đúng như mong đợi.

### 11.2 Kiểm tra bằng browser

Chuẩn bị hai trang lab:

- Trang quản trị mẫu tại **https://admin.example.test/lab/confirm**.
- Trang nhúng mẫu tại **https://promo.example.test/lab/frame-check**.

Trước khi bật header, xác nhận iframe có thể hiển thị trang quản trị mẫu. Sau khi bật **frame-ancestors 'none'**, tải lại trang nhúng và xác nhận nội dung quản trị không còn hiển thị trong frame. Kiểm tra Console và Network để thấy browser chặn việc hiển thị.

### 11.3 Kiểm thử tự động bằng Playwright

Ví dụ dưới đây giả định hai host lab đã được cấu hình trong môi trường test và trang quản trị có heading cố định:

~~~javascript
import { test, expect } from "@playwright/test";

test("admin page cannot be embedded by another origin", async ({ page, request }) => {
  const adminUrl = "https://admin.example.test/lab/confirm";
  const promoUrl = "https://promo.example.test/lab/frame-check";

  const response = await request.get(adminUrl);
  expect(response.ok()).toBeTruthy();

  const headers = response.headers();
  expect(headers["content-security-policy"]).toContain("frame-ancestors 'none'");
  expect(headers["x-frame-options"]).toBe("DENY");

  await page.goto(promoUrl);

  const adminFrame = page.frameLocator("#admin-frame");
  await expect(
    adminFrame.getByRole("heading", { name: "Xác nhận thay đổi quản trị" })
  ).toHaveCount(0);
});
~~~

Đây là ví dụ kiểm tra cho một cấu trúc lab cụ thể. Trong dự án thật, cần điều chỉnh selector, xử lý response header có nhiều policy và xác minh kết quả trên các browser được hỗ trợ. Một test chỉ đọc header không đủ; cần test browser để chứng minh hành vi framing.

### 11.4 Ma trận kiểm thử

| ID | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| CJ01 | Mở trực tiếp trang quản trị | Trang hoạt động bình thường |
| CJ02 | Nhúng trang quản trị từ origin bên ngoài | Browser chặn frame |
| CJ03 | Nhúng từ cùng origin khi policy là none | Browser chặn frame |
| CJ04 | Nhúng qua nhiều lớp ancestor | Bị chặn nếu có ancestor không được phép |
| CJ05 | Trang dashboard được allowlist rõ ràng | Chỉ origin được phép mới nhúng được |
| CJ06 | Route xác nhận thay đổi quyền | Có frame policy trên response |
| CJ07 | Trang đăng nhập và error page | Có policy nhất quán |
| CJ08 | Response qua CDN/reverse proxy | Header không bị mất hoặc ghi đè |
| CJ09 | Browser cũ trong support matrix | X-Frame-Options cung cấp fallback phù hợp |
| CJ10 | Hành động nhạy cảm | Audit log ghi actor, action, target và request ID |
| CJ11 | CSRF regression | CSRF token và kiểm tra request vẫn hoạt động |
| CJ12 | Chức năng dashboard hợp lệ | Luồng nhúng được phê duyệt vẫn hoạt động |

### 11.5 Kiểm tra negative và positive

- Negative test: origin không được phép không thể hiển thị trang quản trị trong iframe.
- Positive test: nhân viên vẫn truy cập trực tiếp trang quản trị bình thường.
- Positive test có điều kiện: dashboard được allowlist vẫn nhúng được nếu kiến trúc thật sự cần.
- Regression: các thao tác quản trị hợp lệ vẫn hoạt động và audit log không mất dữ liệu.
- Compatibility: kiểm tra CSP, X-Frame-Options và hành vi browser trong support matrix.

## 12. Các tình huống dễ cấu hình sai

| Cấu hình hoặc giả định sai | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chỉ cấu hình **frame-src** | Trang khác vẫn có thể nhúng trang quản trị | Dùng **frame-ancestors** trên response của trang quản trị |
| Nghĩ **default-src 'self'** tự chặn framing | Directive không được áp dụng thay cho frame-ancestors | Khai báo frame-ancestors rõ ràng |
| Đặt frame-ancestors trong meta tag | Browser không áp dụng chính sách này | Gửi bằng HTTP response header |
| Chỉ thêm header ở trang chủ | Route nhạy cảm khác vẫn có thể bị nhúng | Áp dụng ở middleware hoặc tầng response dùng chung |
| Dùng wildcard cho subdomain | Subdomain bị takeover hoặc không còn tin cậy có thể được phép nhúng | Allowlist origin tối thiểu |
| Chỉ dùng JavaScript frame-busting | Có thể bị bypass hoặc gây lỗi | Dùng CSP và X-Frame-Options |
| Coi CORS là biện pháp chống clickjacking | Trang vẫn có thể được hiển thị trong iframe | Phân biệt quyền đọc response với quyền framing |
| Coi SameSite là frame protection | Cùng-site cross-origin hoặc luồng khác vẫn có thể tồn tại | Dùng frame policy trực tiếp |
| Bật header nhưng không kiểm tra CDN | Header có thể bị loại bỏ hoặc ghi đè | Kiểm tra response tại edge và browser |
| Cho rằng CSRF token đủ bảo vệ | Người dùng có thể click form thật trong iframe | Bổ sung anti-framing |

## 13. Tiêu chí đóng incident

Incident chỉ nên được đóng khi các điều kiện sau được xác minh:

- Đã xác định route và thao tác có thể bị clickjack.
- Các route quản trị nhạy cảm trả về frame policy phù hợp.
- Browser từ chối framing từ origin không được phép.
- Không còn ngoại lệ allowlist không có owner hoặc mục đích rõ ràng.
- Kiểm thử trực tiếp, iframe, nested frame và browser matrix đã đạt.
- Các thao tác quản trị bị ảnh hưởng đã được đối chiếu với audit log.
- Quyền hoặc cấu hình bị thay đổi ngoài ý muốn đã được đánh giá và xử lý.
- Các session hoặc credential liên quan đã được xử lý nếu có bằng chứng cần thiết.
- Monitoring và regression test đã được đưa vào quy trình vận hành.

Nếu điều tra không tìm thấy bằng chứng thao tác trái phép, ghi rõ phạm vi và giới hạn dữ liệu log. Không suy diễn rằng không có log nghĩa là chắc chắn không có người dùng bị ảnh hưởng.

## 14. Bài học rút ra

Clickjacking khai thác sự khác biệt giữa giao diện mà người dùng nghĩ họ đang tương tác và tài liệu mà browser thực sự nhận click. Một trang có thể được nhúng dù script của trang cha không thể đọc DOM của nó. Do đó, Same-Origin Policy và CORS không thay thế cơ chế chống framing.

Với cổng quản trị, chính sách mặc định nên là không cho phép nhúng. CSP **frame-ancestors 'none'** là kiểm soát hiện đại để chặn mọi ancestor; X-Frame-Options **DENY** hỗ trợ browser cũ. Nếu có nhu cầu nhúng, chỉ allowlist origin đã được review và kiểm tra toàn bộ ancestor chain.

CSRF token, SameSite cookie, xác nhận thao tác và audit log vẫn có vai trò riêng. Chúng giúp giảm các rủi ro liên quan nhưng không giải quyết trực tiếp việc UI bị che trong iframe. Kiểm thử phải xác minh cả response header lẫn hành vi browser trên route thực tế, qua CDN và trong các browser được hỗ trợ.

## 15. Câu hỏi thảo luận

1. Vì sao Same-Origin Policy không ngăn trang quảng bá hiển thị cổng quản trị trong iframe?
2. Vì sao CORS không phải cơ chế chống clickjacking?
3. Trong kịch bản này, click của người dùng đi tới phần tử nào và request được thực hiện dưới session nào?
4. CSRF token có thể vẫn hợp lệ trong một thao tác bị clickjack như thế nào?
5. SameSite cookie giảm những trường hợp nào và vì sao không thay thế frame-ancestors?
6. Khác biệt giữa CSP frame-ancestors và frame-src là gì?
7. Vì sao frame-ancestors cần được gửi qua HTTP response header?
8. Khi nào dùng frame-ancestors 'self' và khi nào dùng 'none'?
9. Nếu một dashboard cần nhúng từ portal đối tác, làm thế nào để allowlist an toàn?
10. Vì sao X-Frame-Options ALLOW-FROM không phải lựa chọn allowlist hiện đại?
11. Những bằng chứng nào giúp phát hiện một trang quản trị đã được tải trong iframe?
12. Vì sao request thao tác bên trong iframe có thể mang Sec-Fetch-Site same-origin?
13. Làm thế nào để kiểm tra frame policy sau khi response đi qua CDN?
14. Vì sao một dialog xác nhận trong cùng trang vẫn có thể bị clickjacking?
15. Những tiêu chí nào cần đạt trước khi đóng incident?

## 16. Tài liệu tham khảo

- [MDN: CSP frame-ancestors](https://developer.mozilla.org/docs/Web/HTTP/Headers/Content-Security-Policy/frame-ancestors)
- [MDN: X-Frame-Options](https://developer.mozilla.org/docs/Web/HTTP/Headers/X-Frame-Options)
- [MDN: Clickjacking](https://developer.mozilla.org/docs/Web/Security/Attacks/Clickjacking)
- [OWASP: Clickjacking Defense Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Clickjacking_Defense_Cheat_Sheet.html)
- [W3C: Content Security Policy Level 3](https://www.w3.org/TR/CSP3/)
- [MDN: Same-Origin Policy](https://developer.mozilla.org/docs/Web/Security/Same-origin_policy)
- [MDN: Fetch Metadata Request Headers](https://developer.mozilla.org/docs/Glossary/Fetch_metadata_request_header)
- [MDN: SameSite cookies](https://developer.mozilla.org/docs/Web/HTTP/Headers/Set-Cookie#samesitesamesite-value)
- [OWASP: Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
