# Frame embedding: kiểm soát website nào được phép nhúng trang bằng iframe

## 1. Frame embedding là gì?

**Frame embedding** là việc một trang web hiển thị tài liệu khác bên trong vùng nội dung của mình bằng các phần tử như iframe, frame hoặc object theo những cơ chế tương ứng của browser. Đây là chức năng hợp lệ của web: ứng dụng có thể nhúng bản đồ, video, trang thanh toán, dashboard hoặc một phần giao diện từ hệ thống khác.

Tuy nhiên, nếu một trang nhạy cảm cho phép website bất kỳ nhúng nó, kẻ tấn công có thể dùng giao diện của mình để đặt trang thật vào bên dưới một lớp nội dung đánh lừa. Người dùng tưởng đang nhấn một nút bình thường nhưng thực tế click hoặc thao tác chạm trúng nút trên trang được nhúng. Đây là nền tảng của **clickjacking** (UI redressing).

Ví dụ, một trang tài khoản có nút “Xác nhận” hoặc “Bật tính năng”. Nếu trang đó cho phép bị nhúng, một website khác có thể đặt iframe trong suốt hoặc căn chỉnh nó dưới một nút giả. Người dùng không nhận ra giao diện thật đang nhận thao tác.

**Frame embedding defense** kiểm soát ai có thể đặt trang của ứng dụng vào browsing context lồng nhau. Cơ chế hiện đại là CSP directive **frame-ancestors**; header **X-Frame-Options** là lớp tương thích cũ hơn. Cần cấu hình đúng response của trang cần được bảo vệ, đồng thời phân biệt nó với frame-src, vốn kiểm soát trang hiện tại được phép nhúng những frame nào.

Bài học thuộc chương **Clickjacking** của module **SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY**. Module phân tích ranh giới bảo mật giữa browser, origin, cookie và ứng dụng web, đồng thời thực hành phòng vệ XSS, CSRF và clickjacking bằng CSP, security headers và kiểm chứng hành vi thực tế. Bài này tập trung vào quyền được nhúng một trang, chuỗi ancestor lồng nhau, cách cho phép parent đáng tin và cách kiểm thử trong browser.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích frame embedding và cách nó tạo điều kiện cho clickjacking.
2. Phân biệt trang được nhúng (framed document) với trang cha (embedding document).
3. Cấu hình CSP frame-ancestors để chặn hoặc allowlist parent origin.
4. Phân biệt frame-ancestors với frame-src, child-src và default-src.
5. Hiểu vai trò, giới hạn và khả năng tương thích của X-Frame-Options.
6. Phân tích nested frame chain và lý do mọi ancestor phải được cho phép.
7. Dùng iframe sandbox và các thuộc tính liên quan để giảm quyền của nội dung được nhúng.
8. Lựa chọn chính sách cho trang công khai, trang đăng nhập, dashboard và luồng tích hợp.
9. Kiểm tra response header, DevTools Console và hành vi thực tế khi embedding.

## 2. Clickjacking hoạt động như thế nào?

Clickjacking là kỹ thuật đánh lừa người dùng tương tác với một giao diện khác với giao diện họ nghĩ mình đang thao tác. Kẻ tấn công không nhất thiết cần đọc nội dung trang đích. Chỉ cần browser tải trang đó vào iframe và người dùng thực hiện thao tác trên vùng bị che phủ hoặc căn chỉnh sai.

Một kịch bản khái quát:

1. Người dùng đang đăng nhập vào app.example.test.
2. attacker.test mở một trang có iframe trỏ tới app.example.test/settings.
3. Trang tấn công đặt một lớp giao diện giả phía trên iframe.
4. Người dùng bấm nút giả như “Xem video” hoặc “Nhận quà”.
5. Thao tác thực tế đi tới control trên trang tài khoản nằm bên dưới.
6. Nếu ứng dụng không có xác nhận hoặc kiểm tra bổ sung, hành động có thể được thực hiện bằng phiên đang đăng nhập.

Ví dụ minh họa cấu trúc embedding trong môi trường lab:

~~~html
<iframe
  src="https://app.example.test/settings"
  title="Trang được nhúng"
></iframe>
~~~

Đây chỉ là ví dụ cấu trúc frame. Phòng vệ cần được thực hiện ở response của app.example.test để browser biết trang đó không được phép bị nhúng bởi parent không tin cậy.

### 2.1. Vì sao SOP không chặn clickjacking?

Same-Origin Policy hạn chế một trang khác origin đọc DOM và dữ liệu của trang được nhúng. Nhưng SOP không mặc định cấm trang khác tạo iframe hoặc hiển thị trang cross-origin.

Vì vậy hai điều có thể cùng đúng:

- attacker.test không thể đọc nội dung DOM của app.example.test.
- browser vẫn có thể hiển thị app.example.test trong iframe và chuyển thao tác chuột/chạm tới vùng đó.

Clickjacking chủ yếu khai thác việc **trang có thể được hiển thị và nhận tương tác**, không đòi hỏi kẻ tấn công đọc response. Cần chính sách framing riêng như frame-ancestors hoặc X-Frame-Options.

### 2.2. Clickjacking không chỉ là iframe trong suốt

Các biến thể có thể dùng:

- Iframe trong suốt hoặc opacity rất thấp.
- Iframe được đặt lệch hoặc cắt một phần.
- Nội dung giả phủ lên control thật.
- Nhiều frame lồng nhau.
- Điều hướng hoặc cửa sổ popup để tạo luồng tương tác gây nhầm lẫn.
- Giao diện được tối ưu cho thao tác chạm trên thiết bị di động.

Do đó chỉ tìm một iframe có opacity bằng 0 không đủ để xác định hoặc phòng vệ clickjacking. Hãy giới hạn quyền framing ở browser và thiết kế xác nhận cho thao tác nhạy cảm.

## 3. Vai trò của embedding page và framed page

Cần phân biệt hai phía:

- **Embedding page / parent:** tài liệu chứa iframe và yêu cầu nhúng trang khác.
- **Framed page / child:** tài liệu được browser tải bên trong iframe.

Ví dụ:

~~~html
<!-- Trang parent: portal.example.test -->
<iframe src="https://billing.example.test/payment"></iframe>
~~~

Trong ví dụ, portal.example.test là parent; billing.example.test là framed page.

Nếu billing.example.test muốn chỉ cho portal.example.test nhúng nó, header cần được gửi từ billing.example.test:

~~~http
Content-Security-Policy: frame-ancestors https://portal.example.test
~~~

Trang parent không thể tự tuyên bố thay cho child rằng child chỉ được nhúng bởi một số website. Quyết định cho phép hay từ chối embedding thuộc về response của framed page.

### 3.1. Quyền framing là chính sách của trang đích

Cấu hình CSP trên portal.example.test không thể thay thế frame-ancestors của billing.example.test. Nếu portal đặt frame-src để cho phép billing, điều đó chỉ nói portal được phép tải billing vào frame; nó không nói billing được phép xuất hiện bên trong portal.

Cần xem hai hướng độc lập:

1. Parent có được phép tải child không? Dùng frame-src ở parent.
2. Child có cho phép parent nhúng mình không? Dùng frame-ancestors ở child.

## 4. CSP frame-ancestors

**frame-ancestors** là CSP directive xác định những ancestor nào được phép nhúng tài liệu hiện tại. Nó kiểm tra các ancestor browsing context trong chuỗi frame, bao gồm parent trực tiếp và các ancestor ở phía trên.

Ví dụ chặn mọi framing:

~~~http
Content-Security-Policy: frame-ancestors 'none'
~~~

Chỉ cho phép cùng origin:

~~~http
Content-Security-Policy: frame-ancestors 'self'
~~~

Cho phép cùng origin và một portal cụ thể:

~~~http
Content-Security-Policy: frame-ancestors 'self' https://portal.example.test
~~~

Nếu ancestor không khớp source list, browser từ chối tải tài liệu vào frame và ghi nhận CSP violation. Khi truy cập URL trực tiếp ở top-level, không có ancestor cần kiểm tra nên frame-ancestors không chặn việc mở trang trực tiếp.

### 4.1. 'none': không cho bất kỳ trang nào nhúng

~~~http
Content-Security-Policy: frame-ancestors 'none'
~~~

Đây là lựa chọn mạnh cho trang tài khoản, quản trị hoặc trang không có nhu cầu tích hợp iframe. Nó ngăn cả same-origin parent nhúng trang.

Nếu một sản phẩm có widget cần được nhúng, không dùng none trên widget đó; thiết kế allowlist origin cụ thể.

### 4.2. 'self': chỉ cho phép cùng origin

~~~http
Content-Security-Policy: frame-ancestors 'self'
~~~

self dựa trên origin của framed document. Origin gồm scheme, host và port. Một subdomain khác thường không được coi là cùng origin, kể cả khi cùng registrable domain.

Ví dụ app.example.test và portal.example.test là hai origin khác nhau. Nếu portal cần nhúng app, chỉ self sẽ chặn việc đó.

### 4.3. Host source cụ thể

~~~http
Content-Security-Policy: frame-ancestors https://portal.example.test
~~~

Host source nên được khai báo rõ scheme, host và port nếu cần. Điều này giúp tránh vô tình cho phép nhiều origin hơn dự định.

Nếu portal có nhiều môi trường:

~~~http
Content-Security-Policy: frame-ancestors https://portal.example.test https://portal-staging.example.test
~~~

Chỉ đưa staging vào policy production khi thật sự cần. Tốt hơn là policy được cấu hình theo môi trường và không mang origin thử nghiệm sang production.

### 4.4. Wildcard và scheme source

Có thể dùng source expression rộng hơn theo cú pháp CSP, nhưng wildcard làm tăng phạm vi tin cậy. Ví dụ cho phép subdomain:

~~~http
Content-Security-Policy: frame-ancestors https://*.example.test
~~~

Hãy kiểm tra kỹ phạm vi subdomain, tenant host, hệ thống legacy và DNS. Một subdomain bị chiếm quyền có thể trở thành parent được phép nhúng trang nhạy cảm.

Không dùng wildcard chỉ để tránh lỗi tích hợp. Ưu tiên allowlist chính xác cho từng parent đã xác minh.

### 4.5. Không dùng 'unsafe-inline' hoặc nonce cho frame-ancestors

frame-ancestors là source list dành cho ancestor origin. Nó không nhận nonce/hash như script-src và không dùng unsafe-inline để cho phép parent. Hãy khai báo origin source phù hợp.

## 5. frame-ancestors không fallback về default-src

Đây là điểm dễ nhầm khi viết CSP.

**frame-ancestors không có fallback về default-src.** Nếu policy chỉ có:

~~~http
Content-Security-Policy: default-src 'self'
~~~

thì điều đó không tự giới hạn website nào được phép nhúng trang hiện tại.

Muốn cấm hoặc giới hạn embedding, phải khai báo rõ:

~~~http
Content-Security-Policy: default-src 'self'; frame-ancestors 'none'
~~~

Hoặc:

~~~http
Content-Security-Policy: default-src 'self'; frame-ancestors 'self' https://portal.example.test
~~~

Không suy luận frame-ancestors từ default-src, frame-src hoặc child-src. Chúng điều khiển các hướng khác nhau.

## 6. Phân biệt frame-ancestors, frame-src và child-src

Các directive có tên gần nhau nhưng giải quyết các câu hỏi khác nhau:

| Directive | Được cấu hình trên | Câu hỏi |
| --- | --- | --- |
| frame-ancestors | Framed page / child | Website nào được phép nhúng trang hiện tại? |
| frame-src | Embedding page / parent | Trang hiện tại được phép tải URL nào vào iframe/frame? |
| child-src | Parent, theo cơ chế fallback cũ | Nguồn nào được phép cho worker/frame trong các browser hỗ trợ; frame-src có thể ghi đè cho frame. |
| default-src | Document hiện tại | Fallback cho một số fetch directive, không áp dụng cho frame-ancestors. |

Ví dụ parent portal:

~~~http
Content-Security-Policy: default-src 'self'; frame-src https://billing.example.test
~~~

Portal được phép tải billing vào frame theo frame-src.

Ví dụ child billing:

~~~http
Content-Security-Policy: frame-ancestors https://portal.example.test
~~~

Billing cho phép portal nhúng nó.

Để tích hợp hoạt động, cả hai phía phải cho phép theo chính sách của mình. Parent có thể cho phép child nhưng child vẫn từ chối parent; ngược lại child có thể cho phép parent nhưng parent vẫn chặn URL child.

### 6.1. frame-src không bảo vệ child khỏi clickjacking

Nếu app.example.test chỉ cấu hình:

~~~http
Content-Security-Policy: frame-src 'self'
~~~

thì app chỉ giới hạn những frame mà chính app được phép tải. Điều đó không ngăn attacker.test nhúng app vào iframe của họ. Muốn bảo vệ app khỏi bị nhúng, cần frame-ancestors trên response của app.

### 6.2. child-src không thay frame-ancestors

child-src từng được dùng như fallback cho một số loại tài nguyên frame/worker. Nó không phải directive kiểm soát ancestor nào được phép chứa document hiện tại. Không dùng child-src thay cho frame-ancestors.

## 7. Nested frames: mọi ancestor đều phải được cho phép

Một framed page có thể nằm trong nhiều lớp iframe:

~~~text
top.example.test
  └── portal.example.test
        └── app.example.test
~~~

Nếu app.example.test khai báo:

~~~http
Content-Security-Policy: frame-ancestors https://portal.example.test
~~~

browser kiểm tra toàn bộ ancestor chain. top.example.test cũng là ancestor; nếu nó không khớp policy, việc nhúng có thể bị chặn dù parent trực tiếp là portal.example.test.

Nếu cả hai ancestor đều là parent hợp lệ:

~~~http
Content-Security-Policy: frame-ancestors https://portal.example.test https://top.example.test
~~~

thì mỗi ancestor trong chain phải khớp một source expression được phép.

Điểm quan trọng: frame-ancestors không chỉ kiểm tra parent trực tiếp. Nếu một hệ thống tích hợp qua nhiều lớp frame, cần liệt kê và kiểm thử cả chuỗi ancestor thật.

### 7.1. Không cho phép một ancestor lạ chỉ vì parent trực tiếp đáng tin

Giả sử portal.example.test là đối tác hợp lệ nhưng bị nhúng vào attacker.test. Nếu policy child chỉ kiểm tra portal, người ta có thể nghĩ portal đủ tin cậy. Browser kiểm tra cả ancestor chain để tránh việc một frame hợp lệ bị bọc bên trong một trang không được phép.

Nếu cần cho phép tích hợp nhiều tầng, hãy xác định chính xác mọi origin có thể xuất hiện trong chain và lý do chúng được tin cậy.

## 8. X-Frame-Options: lớp tương thích cũ

**X-Frame-Options (XFO)** là HTTP response header được dùng trước CSP frame-ancestors để kiểm soát việc trang có được nhúng vào frame hay không.

Hai giá trị phổ biến:

~~~http
X-Frame-Options: DENY
~~~

Chặn trang được hiển thị trong frame.

~~~http
X-Frame-Options: SAMEORIGIN
~~~

Chỉ cho phép framing từ cùng origin theo cách xử lý của browser hỗ trợ.

Một số hệ thống cũ từng dùng ALLOW-FROM, nhưng giá trị này đã lỗi thời và không được hỗ trợ nhất quán. Không dùng ALLOW-FROM để xây allowlist parent hiện đại.

### 8.1. DENY và SAMEORIGIN

| Giá trị | Hành vi |
| --- | --- |
| DENY | Không cho nhúng vào frame. |
| SAMEORIGIN | Cho phép framing khi ancestor đáp ứng quy tắc same-origin của browser. |
| ALLOW-FROM | Cũ/không tương thích rộng; không dùng cho thiết kế mới. |

Nếu trang không cần được nhúng, DENY là lựa chọn legacy rõ ràng. Nếu cần tích hợp same-origin, SAMEORIGIN có thể hỗ trợ browser cũ.

### 8.2. CSP frame-ancestors và XFO

CSP frame-ancestors là cơ chế hiện đại, hỗ trợ allowlist nhiều origin. XFO chỉ có các lựa chọn hạn chế và không biểu đạt được danh sách parent tùy ý.

Trong browser hiện đại, CSP frame-ancestors được ưu tiên khi có mặt và XFO không được dùng để ghi đè một policy frame-ancestors hợp lệ. Tuy nhiên, vẫn có thể gửi XFO để hỗ trợ browser cũ nếu giá trị không mâu thuẫn với CSP.

Ví dụ không nên kết hợp:

~~~http
Content-Security-Policy: frame-ancestors https://portal.example.test
X-Frame-Options: DENY
~~~

Browser hiện đại xử lý frame-ancestors theo CSP; browser cũ chỉ hiểu XFO có thể chặn portal. Kết quả là tích hợp không nhất quán. Nếu cần portal embedding và vẫn muốn hỗ trợ browser cũ, XFO SAMEORIGIN cũng không biểu đạt được portal cross-origin; cần quyết định rõ browser support và mức tương thích chấp nhận được.

### 8.3. Không dùng XFO ALLOW-FROM cho allowlist nhiều origin

ALLOW-FROM không phải phương án thay thế frame-ancestors. Browser có thể bỏ qua hoặc xử lý khác nhau. Với nhiều parent origin, dùng CSP frame-ancestors; xác định fallback cho browser cũ theo yêu cầu sản phẩm.

## 9. Header phải được gửi từ framed response

frame-ancestors và X-Frame-Options là response headers của **tài liệu cần bảo vệ**.

Ví dụ response từ app.example.test:

~~~http
HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8
Content-Security-Policy: frame-ancestors 'none'
X-Frame-Options: DENY
~~~

Nếu cấu hình header chỉ trên portal.example.test, nó không thay thế chính sách của app.example.test.

Cần bảo đảm header xuất hiện trên mọi response HTML nhạy cảm có thể được nhúng:

- Trang đăng nhập.
- Trang cài đặt tài khoản.
- Dashboard quản trị.
- Trang xác nhận giao dịch.
- Trang reset password hoặc thay đổi thông tin bảo mật.
- Error page có nội dung nhạy cảm.
- Các route trả HTML qua nhiều backend hoặc reverse proxy.

Một số route có thể được render bởi service khác hoặc đi qua redirect. Kiểm tra response cuối cùng chứa document được browser nhúng, không chỉ response đầu tiên trong chuỗi redirect.

## 10. Frame-ancestors phải dùng HTTP header

frame-ancestors không có hiệu lực khi khai báo bằng meta element:

~~~html
<meta
  http-equiv="Content-Security-Policy"
  content="frame-ancestors 'none'"
>
~~~

Browser không áp dụng frame-ancestors từ meta CSP. Hãy gửi qua HTTP response header:

~~~http
Content-Security-Policy: frame-ancestors 'none'
~~~

Đây là điểm khác với một số directive CSP khác có thể khai báo trong meta ở phạm vi hỗ trợ. Đối với frame-ancestors, cấu hình ở response header là bắt buộc.

## 11. Nhiều CSP policies và frame-ancestors

Một response có thể nhận nhiều CSP enforce policies. Browser áp dụng tất cả policy đang có hiệu lực; một ancestor phải được cho phép bởi từng policy liên quan.

Ví dụ:

~~~http
Content-Security-Policy: frame-ancestors 'self' https://portal.example.test
Content-Security-Policy: frame-ancestors 'self'
~~~

Portal cross-origin bị policy thứ hai chặn. Policy thứ hai không mở rộng quyền mà thu hẹp tập ancestor được phép.

Điều này thường xảy ra khi CSP được thêm ở cả ứng dụng, framework, reverse proxy hoặc CDN. Nếu portal hợp lệ vẫn bị chặn, kiểm tra tất cả response headers thay vì chỉ xem một header trong cấu hình source code.

### 11.1. Report-Only

CSP Report-Only có thể dùng để quan sát vi phạm của frame-ancestors mà không chặn embedding theo policy Report-Only đó:

~~~http
Content-Security-Policy-Report-Only: frame-ancestors 'self' https://portal.example.test
~~~

Report-Only không thay policy enforce hiện tại. Nếu trang chưa có policy enforce, Report-Only cũng không tự bảo vệ khỏi clickjacking. Dùng nó để quan sát trước khi triển khai enforcement, không xem nó là lớp phòng vệ đã bật.

## 12. Cho phép parent đáng tin: thiết kế allowlist

Nhiều sản phẩm cần được nhúng có kiểm soát, ví dụ:

- Widget thanh toán trong portal của doanh nghiệp.
- Dashboard được nhúng trong trang quản trị nội bộ.
- Ứng dụng đối tác có hợp đồng tích hợp.
- Trang đăng nhập hoặc nội dung SSO trong một luồng được thiết kế riêng.

Một allowlist nên dựa trên origin đã xác minh:

~~~http
Content-Security-Policy: frame-ancestors https://portal.example.test https://admin.example.test
~~~

Origin bao gồm scheme, host và port. Không chỉ kiểm tra tên miền cấp cao hoặc hậu tố chuỗi. Hai host sau là origin khác nhau:

~~~text
https://portal.example.test
https://portal.example.test.attacker.test
~~~

Không dùng wildcard rộng như *.example.test nếu mọi subdomain không cùng mức tin cậy. Nếu cho phép subdomain động, cần quản lý việc tạo, thu hồi và sở hữu subdomain như một phần của threat model.

### 12.1. Không xây allowlist bằng cách phản chiếu Origin tùy ý

Một anti-pattern là đọc header Origin từ request rồi đưa thẳng vào frame-ancestors response:

~~~text
Content-Security-Policy: frame-ancestors <Origin do client gửi>
~~~

Nếu không xác minh Origin bằng allowlist cố định phía server, attacker có thể tự chọn parent origin và làm chính sách cho phép họ. Hãy parse origin, so khớp với danh sách được cấu hình và chỉ trả policy tương ứng với cấu hình đã phê duyệt.

Nếu response thay đổi theo Origin, cần xem xét cache key và Vary để tránh CDN/proxy phục vụ policy của một origin cho origin khác. Cấu hình tĩnh theo route hoặc tenant thường dễ kiểm soát hơn.

### 12.2. Tách route cần embedding và route không cần embedding

Nếu chỉ widget cần nhúng, hãy cấp frame-ancestors allowlist cho route widget. Các route tài khoản hoặc quản trị khác có thể dùng frame-ancestors 'none'. Không mở quyền framing toàn ứng dụng chỉ vì một trang tích hợp cần iframe.

## 13. Iframe sandbox: giới hạn quyền của nội dung được nhúng

Thuộc tính sandbox trên iframe có thể áp đặt giới hạn bổ sung cho tài liệu con:

~~~html
<iframe
  src="https://widgets.example.test/report"
  title="Báo cáo"
  sandbox
></iframe>
~~~

Sandbox mặc định áp dụng một tập hạn chế như chặn script và giới hạn một số điều hướng/form theo quy tắc HTML. Có thể mở từng quyền bằng token trong thuộc tính sandbox khi thật sự cần.

Ví dụ:

~~~html
<iframe
  src="https://widgets.example.test/report"
  title="Báo cáo"
  sandbox="allow-scripts"
></iframe>
~~~

### 13.1. Chỉ cấp quyền cần thiết

Các token thường gặp:

| Token | Ý nghĩa khái quát |
| --- | --- |
| allow-scripts | Cho phép script trong frame chạy. |
| allow-forms | Cho phép gửi form. |
| allow-same-origin | Giữ origin thật của tài liệu thay vì sandbox opaque origin. |
| allow-popups | Cho phép mở popup theo quy tắc sandbox. |
| allow-downloads | Cho phép download trong các trường hợp được hỗ trợ. |
| allow-top-navigation | Cho phép điều hướng top-level; quyền rộng, cần thận trọng. |
| allow-top-navigation-by-user-activation | Cho phép top navigation khi có user activation theo quy tắc browser. |

Không thêm toàn bộ token chỉ để làm widget hoạt động. Bắt đầu với sandbox không có token rồi chỉ mở quyền đã chứng minh cần thiết.

### 13.2. allow-scripts kết hợp allow-same-origin

Với nội dung same-origin, kết hợp allow-scripts và allow-same-origin có thể làm giảm đáng kể lợi ích sandbox: script trong frame có thể có quyền cùng origin và trong một số tình huống truy cập parent để gỡ thuộc tính sandbox hoặc tương tác với document cha.

Không dùng cặp này một cách máy móc cho nội dung không tin cậy. Nếu cần script, cân nhắc phục vụ nội dung từ origin riêng và chỉ cấp quyền tối thiểu.

### 13.3. Sandbox không thay frame-ancestors

sandbox là chính sách của embedding page đối với frame con mà nó tạo. frame-ancestors là chính sách của framed page về ai được phép nhúng nó. Hai cơ chế bổ sung nhau nhưng không thay thế nhau.

## 14. Các thuộc tính iframe khác

Một số thuộc tính giúp kiểm soát cách frame hoạt động:

~~~html
<iframe
  src="https://widgets.example.test/report"
  title="Báo cáo"
  loading="lazy"
  referrerpolicy="strict-origin"
  sandbox="allow-scripts"
></iframe>
~~~

- title giúp công nghệ hỗ trợ tiếp cận mô tả frame.
- loading="lazy" trì hoãn tải frame ngoài vùng nhìn thấy; không phải security boundary.
- referrerpolicy kiểm soát thông tin referrer gửi khi tải frame; nó không quyết định ai được phép embed.
- allow có thể cấp quyền theo Permissions Policy như camera hoặc microphone cho frame; chỉ cấp khi cần.
- sandbox giới hạn một số khả năng của child document.

Không nhầm thuộc tính allow với frame-ancestors. allow quản lý quyền tính năng được cấp cho frame; frame-ancestors kiểm soát ancestor nào có thể nhúng framed document.

## 15. JavaScript frame-busting: vì sao không nên là lớp chính

Một số ứng dụng cũ dùng JavaScript để phát hiện mình đang ở trong iframe:

~~~js
if (window.top !== window.self) {
  window.top.location = window.self.location;
}
~~~

Cách này thường được gọi là frame-busting. Nó không phải biện pháp bảo vệ chính đáng tin cậy vì:

- Script có thể không chạy hoặc bị chặn trước khi thực thi.
- Sandbox có thể hạn chế top navigation.
- Cross-origin restrictions có thể làm hành vi không như mong đợi.
- Có thể có race condition hoặc logic bị vô hiệu hóa.
- Một số kỹ thuật UI redressing không phụ thuộc vào việc script frame-busting chạy đúng.

Hãy dùng frame-ancestors và X-Frame-Options. JavaScript detection chỉ có thể là lớp bổ sung trong một số ứng dụng legacy, không thay response security header.

## 16. Clickjacking và các lớp phòng vệ bổ sung

Frame-ancestors/XFO ngăn trang bị nhúng bởi parent không được phép. Nhưng nếu sản phẩm chủ động cho phép một portal nhúng trang nhạy cảm, vẫn cần đánh giá cách thao tác được xác nhận.

Các lớp bổ sung:

1. **Xác nhận hành động nhạy cảm:** yêu cầu user xác nhận nội dung cụ thể trước khi chuyển tiền, xóa dữ liệu hoặc thay đổi quyền.
2. **Re-authentication/step-up:** yêu cầu mật khẩu/MFA gần thời điểm thực hiện thao tác quan trọng.
3. **CSRF defense:** kiểm tra CSRF token và nguồn request cho thao tác thay đổi trạng thái; clickjacking và CSRF là hai vấn đề khác nhau, có thể cùng tồn tại.
4. **UI rõ ràng:** hiển thị tên tài khoản, số tiền, đích giao dịch và trạng thái trước khi xác nhận.
5. **Giảm quyền widget:** dùng sandbox và Permissions Policy cho nội dung nhúng.
6. **Không tin kích thước/opacity của frame:** CSS phía parent có thể thay đổi cách hiển thị; không dựa vào giao diện parent để xác định user đã nhìn thấy gì.

Nếu ứng dụng cho phép một parent origin tích hợp, cần bảo vệ cả parent đó và các ancestor có thể bọc nó. Allowlist origin không tự chứng minh nội dung hiển thị trong frame là đúng hoặc không bị parent thao túng.

## 17. Chọn policy theo loại trang

| Loại trang | Chính sách framing thường phù hợp | Lý do |
| --- | --- | --- |
| Tài khoản, hồ sơ cá nhân | frame-ancestors 'none' | Không cần tích hợp iframe; giảm clickjacking. |
| Quản trị nội bộ | 'none' hoặc parent nội bộ được xác minh | Giao diện có quyền nhạy cảm. |
| Widget công khai | Allowlist origin đối tác cụ thể | Cần hỗ trợ embedding có kiểm soát. |
| Trang thanh toán | Chỉ parent tích hợp đã phê duyệt | Cần giữ luồng nhúng rõ và giảm UI redressing. |
| Nội dung công khai chỉ đọc | Có thể cho phép framing theo yêu cầu sản phẩm | Vẫn cần đánh giá tracking, UI và quyền thao tác. |
| Trang login/SSO | Theo thiết kế IdP/SP và flow thực tế | Chặn quá chặt có thể làm hỏng luồng đăng nhập; mở rộng quá rộng làm tăng rủi ro. |

Không dùng một policy chung cho mọi route nếu nhu cầu embedding khác nhau. Đặc biệt, không mở frame-ancestors rộng trên toàn host chỉ vì một widget cần được nhúng.

## 18. Thực hành A — Kiểm tra frame-ancestors none

Tạo một trang test parent ở origin A và một framed page ở origin B do bạn kiểm soát. Trên response HTML của B, cấu hình:

~~~http
Content-Security-Policy: frame-ancestors 'none'
~~~

Parent A chứa:

~~~html
<iframe
  src="https://child.example.test/frame-demo"
  title="Frame demo"
></iframe>
~~~

Mở parent và quan sát:

1. Frame không hiển thị document theo policy.
2. DevTools Console ghi nhận vi phạm frame-ancestors.
3. Mở trực tiếp child URL ở tab top-level vẫn truy cập được nếu không có chính sách khác chặn.
4. Kiểm tra response của child có đúng CSP header hay không.

**Mục tiêu:** phân biệt chặn embedding với chặn truy cập trực tiếp.

## 19. Thực hành B — Allowlist parent origin

Trên framed page, thay policy bằng:

~~~http
Content-Security-Policy: frame-ancestors https://portal.example.test
~~~

Tạo parent trên đúng origin portal.example.test và một parent khác ở attacker.example.test hoặc origin test không được phép.

Kiểm tra:

- Parent được allowlist có thể nhúng child.
- Parent ngoài allowlist bị browser chặn.
- Thay scheme hoặc port của parent có thể làm origin không còn khớp.
- Nếu parent được đặt trong một top-level frame khác, ancestor chain cũng phải được cho phép.

Không dùng wildcard chỉ để làm tất cả test parent hoạt động.

## 20. Thực hành C — Phân biệt frame-src và frame-ancestors

Tạo parent có policy:

~~~http
Content-Security-Policy: frame-src https://child.example.test
~~~

Tạo child có policy:

~~~http
Content-Security-Policy: frame-ancestors https://portal.example.test
~~~

Kiểm tra các tình huống:

1. Parent portal cho phép child nhưng child không cho phép portal: frame bị chặn.
2. Child cho phép portal nhưng parent không cho phép child qua frame-src: frame bị chặn.
3. Cả hai policy cho phép: frame có thể tải nếu không có lỗi khác.

**Mục tiêu:** xác nhận hai directive bảo vệ hai hướng khác nhau.

## 21. Thực hành D — Kiểm tra X-Frame-Options và CSP

Trên response của child, thử:

~~~http
X-Frame-Options: DENY
~~~

Sau đó kiểm tra browser mục tiêu. Thử thêm CSP frame-ancestors và quan sát cách browser hiện đại ưu tiên CSP khi directive này có mặt.

Đối chiếu browser cũ hoặc browser không hỗ trợ frame-ancestors nếu tổ chức còn phải hỗ trợ. Không dựa vào ALLOW-FROM; nó không có hỗ trợ tương thích đủ rộng cho thiết kế mới.

Ghi lại:

- Response headers thực tế.
- Browser/version.
- Parent origin và ancestor chain.
- Console message.
- Kết quả frame tải hay bị chặn.

## 22. Checklist review frame embedding

- [ ] Xác định route nào thực sự cần được nhúng.
- [ ] Với trang không cần embedding, đặt CSP frame-ancestors 'none'.
- [ ] Với trang cần embedding, allowlist origin cụ thể đã được xác minh.
- [ ] Gửi frame-ancestors trong HTTP response header; không dùng meta element.
- [ ] Không giả định frame-ancestors fallback về default-src.
- [ ] Phân biệt frame-ancestors (ai nhúng trang này) với frame-src (trang này nhúng ai).
- [ ] Kiểm tra toàn bộ ancestor chain, không chỉ parent trực tiếp.
- [ ] Kiểm tra tất cả CSP headers; nhiều policy enforce được áp dụng đồng thời.
- [ ] Nếu dùng X-Frame-Options, chọn DENY hoặc SAMEORIGIN theo nhu cầu tương thích.
- [ ] Không dựa vào ALLOW-FROM cho allowlist nhiều origin.
- [ ] Đảm bảo CSP và XFO không tạo hành vi khác nhau ngoài dự kiến ở browser cũ.
- [ ] Cấu hình trên response của framed page và bao phủ mọi route nhạy cảm.
- [ ] Không phản chiếu Origin tùy ý vào frame-ancestors.
- [ ] Nếu policy thay đổi theo Origin, xem xét Vary và cache key.
- [ ] Tách widget cần nhúng khỏi trang tài khoản/quản trị không cần nhúng.
- [ ] Dùng iframe sandbox cho nội dung child ít tin cậy và chỉ cấp quyền tối thiểu.
- [ ] Cân nhắc rủi ro khi kết hợp allow-scripts và allow-same-origin.
- [ ] Dùng Permissions Policy/allow chỉ cho tính năng frame cần.
- [ ] Không dùng JavaScript frame-busting làm lớp bảo vệ chính.
- [ ] Bổ sung CSRF defense, xác nhận giao dịch và re-authentication cho hành động nhạy cảm.
- [ ] Kiểm thử với parent được phép, parent bị từ chối và nested frame chain.
- [ ] Kiểm tra DevTools Console và response headers trên browser mục tiêu.

## 23. Những ngộ nhận thường gặp

| Nhận định | Đánh giá | Giải thích |
| --- | --- | --- |
| “SOP ngăn website khác nhúng trang của tôi.” | **Sai** | SOP hạn chế đọc dữ liệu; framing vẫn có thể xảy ra. |
| “frame-src ngăn website khác nhúng trang hiện tại.” | **Sai** | frame-src kiểm soát frame mà document hiện tại tải; frame-ancestors kiểm soát ai nhúng document hiện tại. |
| “default-src 'none' tự cấm framing.” | **Sai** | frame-ancestors không fallback về default-src. |
| “Chỉ cần cho phép parent trực tiếp.” | **Sai** | Browser kiểm tra mọi ancestor trong frame chain. |
| “Có thể đặt frame-ancestors trong meta CSP.” | **Sai** | Directive này cần HTTP response header. |
| “X-Frame-Options ALLOW-FROM hỗ trợ mọi browser.” | **Sai** | Giá trị cũ và không tương thích rộng. |
| “CSP frame-ancestors và XFO luôn được cộng lại.” | **Sai** | Browser hiện đại ưu tiên frame-ancestors khi có mặt; browser cũ có thể chỉ hiểu XFO. |
| “Parent cấu hình frame-src là đủ để bảo vệ child.” | **Sai** | Child phải tự đặt frame-ancestors/XFO. |
| “Nếu iframe trong suốt bị chặn thì clickjacking đã được giải quyết hoàn toàn.” | **Sai** | Cần bảo vệ framing và thiết kế xác nhận hành động; có nhiều biến thể UI redressing. |
| “Sandbox thay thế frame-ancestors.” | **Sai** | Sandbox giới hạn quyền child; frame-ancestors giới hạn ancestor. |
| “JavaScript frame-busting đủ tin cậy.” | **Sai** | Có thể bị vô hiệu hóa hoặc không chạy; dùng response header. |
| “Cho phép một portal đồng nghĩa mọi ancestor phía trên đều an toàn.” | **Sai** | Toàn bộ chain phải khớp policy và nằm trong threat model. |
| “CSP chặn clickjacking thì không cần CSRF defense.” | **Sai** | Hai cơ chế xử lý threat khác nhau và có thể cùng cần. |

## 24. Tổng kết

Frame embedding là chức năng hữu ích nhưng có thể mở đường cho clickjacking nếu trang nhạy cảm bị website không tin cậy nhúng. CSP **frame-ancestors** là cơ chế hiện đại để quyết định ancestor nào được phép chứa trang hiện tại. **X-Frame-Options** bổ sung khả năng tương thích legacy với các lựa chọn DENY và SAMEORIGIN.

Ba nguyên tắc cần nhớ:

1. **Bảo vệ ở framed page:** gửi frame-ancestors trên response của trang cần bảo vệ; dùng 'none' nếu không cần embedding và allowlist origin chính xác nếu có tích hợp.
2. **Phân biệt hướng chính sách:** frame-ancestors trả lời ai được nhúng trang này; frame-src trả lời trang này được nhúng trang nào. Kiểm tra mọi ancestor trong chain.
3. **Kết hợp các lớp phù hợp:** XFO cho browser cũ, sandbox cho quyền của child, CSRF và xác nhận bổ sung cho hành động nhạy cảm. Không dựa vào frame-busting JavaScript làm lớp chính.

Khi review một iframe, hãy hỏi: **ai là parent trực tiếp, những ancestor nào nằm phía trên, response child cho phép origin nào, parent có cho phép tải child không, và thao tác nhạy cảm nào vẫn có thể bị đánh lừa trong giao diện được nhúng?** Trả lời rõ các câu hỏi này giúp kiểm soát embedding mà vẫn hỗ trợ những tích hợp thật sự cần thiết.
