# Iframe allow attribute: ủy quyền có chọn lọc các tính năng trình duyệt

> **Chương:** Iframe  
> **Học phần:** SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

Thuộc tính `allow` của phần tử `<iframe>` khai báo **Permissions Policy container policy** cho nội dung được nhúng. Nó cho phép trang cha quyết định iframe cụ thể có thể sử dụng những tính năng trình duyệt nào, chẳng hạn geolocation, camera, microphone, fullscreen, autoplay hoặc payment. Nhờ vậy, ứng dụng có thể cấp một quyền cần thiết cho iframe đáng tin cậy, đồng thời tắt cùng tính năng ở những iframe khác.

`allow` không phải là lời cấp quyền tuyệt đối. Nó chỉ tạo ra một giới hạn hoặc ủy quyền cho browsing context con; chính sách `Permissions-Policy` trong response của trang cha vẫn đặt giới hạn phía trên. Browser còn áp dụng yêu cầu secure context, quyền do người dùng cấp, user activation và các quy tắc riêng của từng API. Nếu một ancestor đã tắt một tính năng, iframe không thể tự bật lại tính năng đó.

Bài này phân tích cú pháp `allow`, allowlist origin, cách nó kết hợp với HTTP header `Permissions-Policy`, hành vi khi iframe điều hướng, sự khác nhau giữa allow, sandbox và CSP, cùng cách kiểm chứng bằng DevTools và Node.js.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích `allow` là container policy dành cho iframe và thuộc Permissions Policy.
2. Viết allowlist cho origin của thuộc tính `src`, origin của trang cha và origin cụ thể.
3. Phân biệt cú pháp `allow` trong HTML với cú pháp structured header của `Permissions-Policy`.
4. Giải thích cách policy của trang cha giới hạn quyền mà iframe có thể nhận.
5. Phân biệt việc cho phép API trong policy với quyền người dùng cấp và điều kiện bảo mật của browser.
6. Hiểu ảnh hưởng của redirect/navigation sang origin khác đối với `'src'`.
7. Phân biệt `allow` với `sandbox`, `allowfullscreen`, CSP `frame-src`/`frame-ancestors` và CORS.
8. Thiết kế allowlist tối thiểu, tránh wildcard không cần thiết và xử lý browser không hỗ trợ.
9. Thực hành kiểm tra geolocation và fullscreen trong iframe trên localhost.

## 1. Iframe và các tính năng trình duyệt

### 1.1 Iframe tạo browsing context riêng

Phần tử `<iframe>` nhúng một tài liệu khác vào trang hiện tại. Tài liệu con có browsing context riêng và có thể thuộc cùng origin hoặc khác origin với trang cha.

Ví dụ:

~~~html
<iframe
  src="https://maps.example.net/embed"
  title="Bản đồ vị trí cửa hàng"
  width="640"
  height="360">
</iframe>
~~~

Nếu iframe thuộc origin khác, Same-Origin Policy giới hạn việc trang cha đọc DOM của nó và ngược lại. Tuy nhiên, nội dung iframe vẫn có thể cần một số tính năng trình duyệt, ví dụ:

- Bản đồ cần geolocation để xác định vị trí.
- Ứng dụng hội nghị cần camera và microphone.
- Trình phát video cần autoplay hoặc picture-in-picture.
- Ứng dụng trình chiếu cần fullscreen.
- Widget thanh toán cần Payment Request API trong browser hỗ trợ.
- Ứng dụng web cần USB, serial hoặc display capture trong những trường hợp đặc biệt.

Trang cha không nên mặc định rằng một iframe bên thứ ba cần mọi quyền. Hãy xác định tính năng nào thực sự cần cho từng nội dung nhúng.

### 1.2 Permissions Policy kiểm soát feature, không kiểm soát DOM

Permissions Policy cho biết một document hoặc browsing context có được phép sử dụng một tính năng được kiểm soát hay không. Nó không thay đổi Same-Origin Policy và không cấp quyền đọc DOM cross-origin.

Ví dụ, cho phép geolocation trong iframe không đồng nghĩa với việc trang cha có thể đọc DOM của iframe. Tương tự, CORS không cấp quyền camera hoặc fullscreen; mỗi cơ chế có mục tiêu riêng.

### 1.3 Hai nơi có thể khai báo policy

| Cơ chế | Phạm vi chính | Nơi khai báo |
|---|---|---|
| `Permissions-Policy` | Policy của document và giới hạn các browsing context con | HTTP response header |
| `allow` | Container policy cho một iframe cụ thể | Thuộc tính HTML trên `<iframe>` |

Header định nghĩa tập origin tối đa có thể được phép sử dụng feature. Thuộc tính `allow` chọn quyền cho iframe cụ thể trong phạm vi mà policy phía trên cho phép. Các ancestor cũng có thể đã giới hạn feature trước khi đến trang cha hiện tại.

## 2. Cú pháp của allow attribute

### 2.1 Cấu trúc tổng quát

Cú pháp trong HTML:

~~~html
<iframe
  src="https://maps.example.net/embed"
  allow="geolocation 'src'; fullscreen 'src'">
</iframe>
~~~

Cấu trúc gồm:

- Tên feature, ví dụ `geolocation` hoặc `fullscreen`.
- Allowlist cho feature đó.
- Nhiều directive được phân tách bằng dấu chấm phẩy.
- Nhiều origin trong cùng allowlist được phân tách bằng khoảng trắng.

Các tên feature thường gặp là `camera`, `microphone`, `geolocation`, `fullscreen`, `autoplay`, `payment`, `usb` và `display-capture`. Danh sách feature và mức hỗ trợ thay đổi theo browser; không phải browser nào cũng triển khai mọi directive.

### 2.2 Các giá trị allowlist

Trong `allow`, các giá trị đặc biệt thường dùng:

| Giá trị | Ý nghĩa |
|---|---|
| `'src'` | Origin của URL trong thuộc tính `src` của iframe |
| `'self'` | Origin của document cha hiện tại |
| `'none'` | Không cho phép origin nào |
| `*` | Cho phép mọi origin |
| `https://widget.example.net` | Chỉ cho phép origin cụ thể |

Các từ khóa `'src'`, `'self'` và `'none'` được đặt trong dấu nháy đơn. Origin cụ thể trong cú pháp HTML không đặt trong dấu nháy.

Giá trị `*` và `'none'` được dùng độc lập trong allowlist. `'self'` và `'src'` có thể kết hợp với một hoặc nhiều origin cụ thể.

### 2.3 Không ghi allowlist có nghĩa là 'src'

Nếu một feature được liệt kê nhưng không ghi allowlist, browser dùng `'src'` làm giá trị mặc định cho feature đó.

Hai cách sau tương đương:

~~~html
<iframe
  src="https://maps.example.net/embed"
  allow="geolocation">
</iframe>
~~~

~~~html
<iframe
  src="https://maps.example.net/embed"
  allow="geolocation 'src'">
</iframe>
~~~

Điều đó có nghĩa feature được cho phép trong iframe nếu document đang tải có cùng origin với URL trong `src`. Đây là cách ngắn gọn và thường phù hợp khi chỉ muốn cấp quyền cho đúng widget được nhúng.

Cần phân biệt trường hợp **feature không xuất hiện trong `allow`**. Khi không liệt kê, browser dùng default allowlist của feature theo Permissions Policy và policy được kế thừa. Default allowlist có thể là `self` hoặc `*` tùy feature. Vì vậy, không thể kết luận mọi feature đều bị tắt chỉ vì bỏ qua nó trong `allow`.

### 2.4 Ví dụ cho phép hoặc từ chối nhiều feature

Chỉ cho iframe có origin khớp `src` sử dụng geolocation và fullscreen; tắt camera/microphone:

~~~html
<iframe
  src="https://maps.example.net/embed"
  title="Bản đồ"
  allow="geolocation 'src'; fullscreen 'src'; camera 'none'; microphone 'none'">
</iframe>
~~~

Cho phép geolocation ở trang cha và một origin đối tác:

~~~html
<iframe
  src="https://maps.example.net/embed"
  allow="geolocation 'self' https://maps.example.net">
</iframe>
~~~

Tắt hoàn toàn các feature nhạy cảm trong iframe:

~~~html
<iframe
  src="https://widget.example.net"
  allow="camera 'none'; microphone 'none'; geolocation 'none'; fullscreen 'none'">
</iframe>
~~~

Không cấp mọi feature cho mọi origin nếu không có yêu cầu cụ thể:

~~~html
<!-- Phạm vi rất rộng; chỉ dùng khi có lý do rõ ràng. -->
<iframe src="https://widget.example.net" allow="camera *; microphone *">
</iframe>
~~~

Wildcard `*` làm tăng số origin có thể nhận quyền và khiến việc đánh giá bên nhận khó hơn. Với nội dung bên thứ ba, ưu tiên `'src'` hoặc origin cụ thể.

## 3. Origin trong allow attribute

### 3.1 Origin bao gồm scheme, host và port

Origin là tổ hợp scheme, host và port. Ví dụ:

- `https://maps.example.net`
- `https://maps.example.net:8443`
- `http://maps.example.net`

là các origin khác nhau nếu scheme hoặc port khác nhau. Path không thuộc origin: `https://maps.example.net/map` và `https://maps.example.net/embed` vẫn cùng origin.

Vì vậy, allowlist cần chỉ rõ origin đầy đủ. Đừng dùng tên miền gần đúng hoặc kiểm tra chuỗi suffix trong JavaScript để thay thế quy tắc origin của browser.

### 3.2 'src' gắn với URL ban đầu của iframe

Ví dụ:

~~~html
<iframe
  src="https://maps.example.net/embed"
  allow="geolocation 'src'">
</iframe>
~~~

`'src'` đại diện cho origin của URL được đặt trong thuộc tính `src`. Nếu iframe điều hướng sang một origin khác, policy không tự động được áp dụng cho origin mới đó.

Giả sử widget ban đầu tại `https://maps.example.net` chuyển sang `https://login.partner.example`. Nếu muốn cho origin điều hướng này sử dụng feature, cần liệt kê origin đó một cách có chủ đích:

~~~html
<iframe
  src="https://maps.example.net/embed"
  allow="geolocation 'src' https://login.partner.example">
</iframe>
~~~

Chỉ thêm origin đích nếu luồng điều hướng là một phần đã được kiểm soát của tích hợp. Không dùng wildcard để xử lý redirect chưa rõ nguồn.

### 3.3 'self' không có nghĩa là origin của iframe

Trong cú pháp `allow`, `'self'` tham chiếu đến origin của document cha. `'src'` tham chiếu origin của URL trong `src` của iframe.

Ví dụ trang cha tại `https://app.example.com` nhúng widget tại `https://maps.example.net`:

~~~html
<iframe
  src="https://maps.example.net/embed"
  allow="geolocation 'self'">
</iframe>
~~~

Allowlist `'self'` là origin của app, không phải maps. Widget khác origin sẽ không khớp allowlist này. Nếu mục tiêu là cấp quyền cho widget đúng theo URL nhúng, dùng `'src'`.

### 3.4 Nhiều origin cụ thể

Có thể cho phép nhiều origin:

~~~html
<iframe
  src="https://widget.example.net"
  allow="geolocation 'src' https://maps.partner.example https://login.partner.example">
</iframe>
~~~

Các origin trong cú pháp HTML không đặt trong dấu nháy. Nếu dùng wildcard subdomain, hãy kiểm tra hỗ trợ browser và nhớ wildcard subdomain không tự động bao gồm apex domain. Ví dụ `https://*.example.net` không đồng nghĩa với `https://example.net`.

## 4. Quan hệ giữa iframe allow và Permissions-Policy header

### 4.1 Header tạo giới hạn phía trên

Response của trang cha có thể gửi:

~~~http
Permissions-Policy: geolocation=(self "https://maps.example.net"), camera=(), microphone=(), fullscreen=(self "https://maps.example.net")
~~~

Cú pháp HTTP header khác cú pháp HTML `allow`:

- Header dùng `feature=(allowlist)`.
- Origin trong header được đặt trong dấu nháy kép.
- Allowlist rỗng được viết `()`.
- `self` trong header là token không đặt trong dấu nháy đơn.

Trong khi đó, HTML attribute dùng dạng:

~~~html
<iframe
  src="https://maps.example.net/embed"
  allow="geolocation; fullscreen; camera 'none'; microphone 'none'">
</iframe>
~~~

Không sao chép nguyên cú pháp header vào attribute hoặc ngược lại.

### 4.2 Iframe chỉ nhận quyền trong tập mà ancestor cho phép

Giả sử header của trang cha là:

~~~http
Permissions-Policy: geolocation=(self "https://maps.example.net"), camera=()
~~~

Trang cha cho phép geolocation ở chính nó và maps origin; camera bị tắt cho mọi browsing context con.

Nếu iframe là maps:

~~~html
<iframe
  src="https://maps.example.net/embed"
  allow="geolocation">
</iframe>
~~~

maps có thể nhận geolocation nếu các điều kiện khác đáp ứng. `allow="geolocation"` là shorthand cho allowlist `'src'`, phù hợp với origin trong `src`.

Nếu iframe cố bật camera:

~~~html
<iframe
  src="https://maps.example.net/embed"
  allow="camera *">
</iframe>
~~~

camera vẫn bị chặn vì header phía trên đã đặt `camera=()`. Child không thể nới lỏng giới hạn do parent/ancestor áp đặt.

### 4.3 Quyền bị tắt không thể bật lại ở descendant

Permissions Policy có tính chất một chiều khi một feature đã bị tắt ở ancestor:

~~~text
Top-level response
  Permissions-Policy: camera=()
          |
          v
Parent document
          |
          v
<iframe allow="camera *">
          |
          v
Camera vẫn bị chặn
~~~

Một child frame không thể tự cấp lại feature đã bị ancestor từ chối. Đây là nguyên tắc quan trọng khi xây dựng hệ thống nhiều lớp iframe hoặc nhúng widget của bên thứ ba.

### 4.4 Nếu header không khai báo feature thì sao?

Khi header không có directive cho một feature, khả năng delegate còn phụ thuộc default allowlist của feature và policy được kế thừa. `allow` có thể cấp feature cho origin được liệt kê nếu feature vẫn được bật trong parent document. Tuy nhiên, nếu feature đã bị chặn bởi ancestor hoặc default policy không cho phép origin đó, attribute không thể vượt qua giới hạn này.

Đừng giả định rằng việc không gửi header đồng nghĩa mọi feature được bật cho mọi iframe. Hãy kiểm tra default allowlist của từng feature trong tài liệu browser/spec và đặt header rõ ràng cho các feature nhạy cảm mà ứng dụng cần quản lý.

### 4.5 Phạm vi header của document con

Document con cũng có thể gửi Permissions-Policy header cho chính nó và các descendant của nó. Header đó tiếp tục thu hẹp quyền ở nhánh cây bên dưới; nó không thể mở lại feature mà ancestor đã tắt.

Nếu ứng dụng lồng nhiều iframe, hãy kiểm tra policy tại từng tầng. Quyền cần phải được cho phép xuyên suốt chuỗi ancestor và container policy.

## 5. allow không phải là lời cấp quyền của người dùng

### 5.1 Permissions Policy và Permissions API giải quyết hai điều khác nhau

Permissions Policy xác định feature có được phép sử dụng trong document/browsing context hay không. Permissions API và cơ chế permission của browser xác định người dùng đã cấp quyền cho website hoặc feature đó chưa.

Với camera, microphone và geolocation, việc policy cho phép iframe sử dụng API **không đồng nghĩa browser tự động cấp quyền**. Browser vẫn có thể hỏi người dùng, trả về trạng thái denied hoặc yêu cầu điều kiện khác.

Một feature có thể thất bại vì:

- Permissions Policy chặn feature.
- Người dùng đã từ chối quyền.
- Trang không ở secure context.
- Browser hoặc thiết bị không hỗ trợ API.
- Người dùng chưa thực hiện thao tác cần thiết.
- Hệ điều hành không cấp quyền cho browser.
- Quy tắc riêng của API không được đáp ứng.

### 5.2 Secure context

Các API nhạy cảm thường yêu cầu secure context. HTTPS là lựa chọn triển khai thông thường; localhost được browser xem là trustworthy trong nhiều tình huống phát triển, nên lab local có thể kiểm tra một số API mà không cần domain public.

Nếu iframe nhúng HTTP từ một host không được xem là secure context, thêm `allow="geolocation"` không thể biến nó thành secure context.

### 5.3 User activation

Một số API cần thao tác người dùng trực tiếp:

- Fullscreen thường cần transient user activation, ví dụ click nút.
- Autoplay có thể bị browser hạn chế theo chính sách trải nghiệm người dùng.
- Một số API thiết bị cần prompt hoặc gesture cụ thể.

Vì vậy, `allow="fullscreen"` không có nghĩa iframe được tự động bật fullscreen khi vừa tải.

### 5.4 Kiểm tra trạng thái permission

Có thể kiểm tra permission ở nơi API được hỗ trợ:

~~~js
async function inspectGeolocationPermission() {
  if (!navigator.permissions?.query) {
    return 'Permissions API không được hỗ trợ ở browser này.';
  }

  try {
    const result = await navigator.permissions.query({
      name: 'geolocation'
    });
    return result.state;
  } catch (error) {
    return error.name + ': ' + error.message;
  }
}
~~~

Kết quả `granted`, `prompt` hoặc `denied` phản ánh trạng thái permission mà browser báo. Nếu policy chặn feature, browser có thể báo `denied` hoặc từ chối API mà không hiện prompt. Không phải feature nào cũng có thể truy vấn qua Permissions API; hãy kiểm tra support theo API cụ thể.

## 6. Những feature thường được delegate

| Feature | API/khả năng liên quan | Điều cần lưu ý |
|---|---|---|
| `geolocation` | `navigator.geolocation` | Secure context và quyền người dùng |
| `camera` | `navigator.mediaDevices.getUserMedia()` với video | Permission, thiết bị và secure context |
| `microphone` | `navigator.mediaDevices.getUserMedia()` với audio | Permission, thiết bị và secure context |
| `fullscreen` | `Element.requestFullscreen()` | Thường cần user activation |
| `autoplay` | Tự động phát media | Còn phụ thuộc chính sách autoplay của browser |
| `picture-in-picture` | Picture-in-Picture API | Hỗ trợ và điều kiện theo browser |
| `payment` | Payment Request API | Hỗ trợ theo browser và phương thức thanh toán |
| `usb` | WebUSB | Secure context, hỗ trợ thiết bị và permission |
| `display-capture` | Screen Capture API | Yêu cầu user gesture/permission theo API |
| `clipboard-read` | Clipboard API | Permission và user activation theo browser |

Tên directive là identifier do Permissions Policy quy định. Không tự đặt tên feature theo tên JavaScript API. Kiểm tra danh sách directive và browser support trước khi triển khai.

## 7. allow, sandbox và các cơ chế iframe khác

### 7.1 allow và sandbox khác nhau

| Thuộc tính | Mục đích | Ví dụ |
|---|---|---|
| `allow` | Delegation/giới hạn các feature được kiểm soát bởi Permissions Policy | Cho phép geolocation trong một iframe |
| `sandbox` | Áp dụng hạn chế cho tài liệu nhúng như script, form, popup, navigation và origin | Nhúng nội dung không tin cậy với ít quyền hơn |
| `allowfullscreen` | Thuộc tính legacy cho khả năng fullscreen | Được thay dần bằng feature `fullscreen` trong `allow` |
| `referrerpolicy` | Kiểm soát Referrer header khi tải iframe | Giảm lộ URL nguồn |
| `loading` | Điều khiển lazy loading | Tải iframe khi gần viewport |

Ví dụ kết hợp:

~~~html
<iframe
  src="https://usercontent.example.net/view"
  title="Nội dung người dùng"
  sandbox="allow-scripts"
  allow="camera 'none'; microphone 'none'; geolocation 'none'; fullscreen 'none'"
  referrerpolicy="no-referrer"
  loading="lazy">
</iframe>
~~~

`sandbox` giới hạn khả năng của tài liệu theo các token được cấp. `allow` kiểm soát các policy-controlled feature. Cả hai có thể cùng áp dụng; cho phép một feature trong `allow` không gỡ bỏ hạn chế sandbox.

Đặc biệt thận trọng với tổ hợp `allow-scripts` và `allow-same-origin` khi nhúng nội dung cùng origin với trang cha. Với nội dung không tin cậy, tổ hợp này có thể làm suy yếu mục đích cô lập của sandbox.

### 7.2 allowfullscreen là legacy attribute

Trước đây, ứng dụng thường viết:

~~~html
<iframe src="https://video.example.net/embed" allowfullscreen></iframe>
~~~

Cách hiện đại là dùng Permissions Policy feature:

~~~html
<iframe
  src="https://video.example.net/embed"
  allow="fullscreen">
</iframe>
~~~

Khi `allow` có khai báo feature `fullscreen`, thuộc tính `allowfullscreen` không còn tác dụng đối với feature đó. Nếu chỉ dùng `allowfullscreen` cũ mà không khai báo fullscreen trong `allow`, cơ chế tương thích legacy có thể tạo allowlist rộng `*`. Vì vậy, `allow="fullscreen"` có phạm vi hẹp hơn theo origin `src` mặc định.

### 7.3 allow và CSP frame-src

CSP `frame-src` của trang cha kiểm soát những origin mà trang được phép tải trong iframe:

~~~http
Content-Security-Policy: frame-src 'self' https://maps.example.net
~~~

CSP `frame-ancestors` trong response của trang con kiểm soát những trang nào được phép nhúng nó:

~~~http
Content-Security-Policy: frame-ancestors 'self' https://portal.example.com
~~~

`allow` không thay thế hai directive này:

- CSP `frame-src` quyết định có được tải frame đó không.
- CSP `frame-ancestors` quyết định ai được nhúng tài liệu.
- Permissions Policy `allow` quyết định feature nào có thể được delegate cho iframe.

### 7.4 allow không phải CORS

CORS kiểm soát việc JavaScript ở origin khác có được đọc response hay không. `allow` kiểm soát feature trình duyệt được phép sử dụng trong iframe. Một iframe có thể được delegate geolocation nhưng vẫn không cho trang cha đọc DOM do SOP; một API fetch cross-origin vẫn cần CORS nếu script muốn đọc response.

## 8. Thiết kế allowlist an toàn

### 8.1 Chỉ cấp feature mà widget cần

Ví dụ widget bản đồ chỉ cần geolocation:

~~~html
<iframe
  src="https://maps.example.net/embed"
  title="Bản đồ"
  allow="geolocation">
</iframe>
~~~

Không cấp camera, microphone, USB hoặc clipboard nếu widget không sử dụng. Khi tích hợp một bên thứ ba, yêu cầu danh sách feature cụ thể và lý do nghiệp vụ.

### 8.2 Dùng header làm giới hạn tối đa

Ví dụ trang cha chỉ cho phép geolocation và fullscreen ở origin chính cùng widget bản đồ:

~~~http
Permissions-Policy: geolocation=(self "https://maps.example.net"), fullscreen=(self "https://maps.example.net"), camera=(), microphone=(), usb=()
~~~

Sau đó iframe chỉ nhận đúng feature cần:

~~~html
<iframe
  src="https://maps.example.net/embed"
  allow="geolocation; fullscreen">
</iframe>
~~~

Header giữ giới hạn tối đa ở cấp trang; attribute cho phép từng frame trong tập đó. Một iframe khác không khai báo hoặc bị giới hạn riêng sẽ không mặc nhiên nhận cùng quyền như widget bản đồ.

### 8.3 Tránh wildcard

Không dùng:

~~~html
<iframe src="https://widget.example.net" allow="camera *; microphone *">
</iframe>
~~~

trừ khi mọi origin có thể điều hướng/được phép trong browsing context thực sự cần feature và đã được đánh giá. Với camera/microphone, wildcard đặc biệt nhạy cảm.

Ưu tiên:

- `'src'` khi chỉ origin của URL nhúng cần feature.
- Origin cụ thể khi có luồng điều hướng đã biết.
- `'none'` khi muốn tắt feature trong iframe.
- Header allowlist tối thiểu cho những origin có thể nhận quyền.

### 8.4 Không xem iframe là ranh giới tin cậy tuyệt đối

Iframe cross-origin tạo ranh giới SOP cho DOM và nhiều API, nhưng nội dung bên trong vẫn có thể thực hiện hành động được delegate. Hãy xem xét:

- Nhà cung cấp và chủ sở hữu origin.
- Redirect và navigation trong iframe.
- Script/SDK được tải trong tài liệu con.
- Quyền thiết bị được delegate.
- Thông điệp postMessage giữa parent và child.
- Chính sách cookie và đăng nhập của bên thứ ba.
- CSP, sandbox và Permissions Policy ở các tầng.

Chỉ cấp quyền cho origin có lý do và có thể quản lý vòng đời tích hợp.

## 9. Kiểm thử và chẩn đoán

### 9.1 Kiểm tra trong DevTools

Mở DevTools của trang cha và kiểm tra:

1. Network → chọn response HTML của trang cha.
2. Xem header `Permissions-Policy`.
3. Elements → chọn iframe, kiểm tra `src` và `allow` thực tế sau khi framework render.
4. Console → tìm thông báo Permissions Policy violation.
5. Network → kiểm tra iframe có tải đúng origin hay bị redirect.
6. Application/Frames hoặc frame selector trong DevTools để chọn execution context của iframe.
7. Trong context iframe, kiểm tra API và thử feature sau thao tác người dùng.

Một số browser cung cấp thông tin policy qua API chẩn đoán riêng như `document.featurePolicy` (tên API legacy/khả năng hỗ trợ có thể khác). Không dựa vào API chẩn đoán không chuẩn hóa như một cơ chế bảo mật; response header, DOM và hành vi API thực tế là bằng chứng chính.

### 9.2 Phân biệt lỗi policy với lỗi permission

| Hiện tượng | Nguyên nhân có thể |
|---|---|
| API không tồn tại | Browser/thiết bị không hỗ trợ hoặc API không được expose trong context |
| Console báo Permissions Policy violation | Header ancestor hoặc iframe allowlist không cho phép feature |
| API trả NotAllowedError | Policy chặn, người dùng từ chối hoặc permission không được cấp; cần kiểm tra ngữ cảnh |
| Không hiện prompt | Feature bị policy chặn, permission đã bị từ chối, hoặc browser không yêu cầu prompt trong trường hợp đó |
| Geolocation lỗi trên HTTP | Trang không ở secure context |
| Fullscreen bị từ chối | Thiếu user activation, policy không cho phép hoặc browser không hỗ trợ |
| Widget redirect sang origin khác rồi mất quyền | Origin mới không nằm trong allowlist của iframe |
| allow có vẻ đúng nhưng feature vẫn bị chặn | Header ở ancestor đã chặn, feature không được hỗ trợ hoặc có giới hạn API khác |

Không kết luận mọi `NotAllowedError` đều là do `allow`. Kiểm tra header, origin thực tế, permission người dùng và console message.

## 10. Thực hành: delegate geolocation và fullscreen trên localhost

Bài lab tạo hai server HTTP local ở hai port khác nhau. Hai port tạo ra hai origin khác nhau, giúp kiểm tra delegation cross-origin. Browser thường xem localhost là secure context cho mục đích phát triển, nhưng geolocation vẫn cần người dùng cấp quyền và fullscreen cần thao tác click.

### 10.1 Tạo file `iframe-allow-lab.mjs`

~~~js
import { createServer } from 'node:http';

const parentHtml = [
  '<!doctype html>',
  '<html lang="vi">',
  '<head><meta charset="utf-8"><title>Iframe allow parent</title></head>',
  '<body>',
  '<h1>Parent: localhost:3000</h1>',
  '<p>Child chạy ở localhost:3001, khác origin do khác port.</p>',
  '<iframe',
  '  src="http://localhost:3001/child"',
  '  title="Permissions Policy demo"',
  '  width="700"',
  '  height="360"',
  '  allow="geolocation; fullscreen; camera \'none\'; microphone \'none\'">',
  '</iframe>',
  '</body></html>'
].join('\n');

const childHtml = [
  '<!doctype html>',
  '<html lang="vi">',
  '<head><meta charset="utf-8"><title>Iframe allow child</title></head>',
  '<body>',
  '<h2>Child: localhost:3001</h2>',
  '<p>Nhấn từng nút để kiểm tra feature được delegate.</p>',
  '<button id="geo" type="button">Thử geolocation</button>',
  '<button id="full" type="button">Thử fullscreen</button>',
  '<pre id="result">Chưa chạy.</pre>',
  '<script>',
  'const result = document.querySelector("#result");',
  'document.querySelector("#geo").addEventListener("click", () => {',
  '  if (!navigator.geolocation) {',
  '    result.textContent = "Geolocation API không khả dụng.";',
  '    return;',
  '  }',
  '  navigator.geolocation.getCurrentPosition(',
  '    () => { result.textContent = "Geolocation thành công; lab không hiển thị tọa độ."; },',
  '    error => { result.textContent = error.name + ": " + error.message; }',
  '  );',
  '});',
  'document.querySelector("#full").addEventListener("click", async () => {',
  '  try {',
  '    await document.documentElement.requestFullscreen();',
  '    result.textContent = "Fullscreen được kích hoạt.";',
  '  } catch (error) {',
  '    result.textContent = error.name + ": " + error.message;',
  '  }',
  '});',
  '</script>',
  '</body></html>'
].join('\n');

const parentServer = createServer((req, res) => {
  if (req.url !== '/') {
    res.writeHead(404);
    return res.end('Not found');
  }

  res.writeHead(200, {
    'Content-Type': 'text/html; charset=utf-8',
    'Cache-Control': 'no-store',
    'Permissions-Policy':
      'geolocation=(self "http://localhost:3001"), ' +
      'fullscreen=(self "http://localhost:3001"), ' +
      'camera=(), microphone=()'
  });
  res.end(parentHtml);
});

const childServer = createServer((req, res) => {
  if (req.url !== '/child') {
    res.writeHead(404);
    return res.end('Not found');
  }

  res.writeHead(200, {
    'Content-Type': 'text/html; charset=utf-8',
    'Cache-Control': 'no-store'
  });
  res.end(childHtml);
});

parentServer.listen(3000, 'localhost', () => {
  console.log('Parent: http://localhost:3000');
});

childServer.listen(3001, 'localhost', () => {
  console.log('Child:  http://localhost:3001/child');
});
~~~

### 10.2 Chạy lab

~~~bash
node iframe-allow-lab.mjs
~~~

Mở `http://localhost:3000`. Parent gửi header:

~~~http
Permissions-Policy: geolocation=(self "http://localhost:3001"), fullscreen=(self "http://localhost:3001"), camera=(), microphone=()
~~~

Iframe khai báo:

~~~html
allow="geolocation; fullscreen; camera 'none'; microphone 'none'"
~~~

Các điểm cần quan sát:

1. Child ở port 3001 là cross-origin với parent ở port 3000.
2. `geolocation` và `fullscreen` được delegate cho origin của iframe.
3. Nhấn nút geolocation. Browser có thể hiện prompt; chỉ cấp quyền nếu muốn thử. Lab không hiển thị tọa độ.
4. Nhấn nút fullscreen. Hành động được gọi từ click nên đáp ứng yêu cầu user activation thông thường.
5. Camera và microphone bị tắt ở header parent và trong allowlist của iframe; attribute con không thể bật lại.
6. Mở DevTools Console để xem lỗi policy hoặc lỗi permission nếu feature không hoạt động.

### 10.3 Thử thay đổi policy

Thử từng thay đổi, tải lại trang và so sánh:

**A. Từ chối geolocation ở iframe**

~~~html
<iframe
  src="http://localhost:3001/child"
  allow="geolocation 'none'; fullscreen">
</iframe>
~~~

Geolocation phải bị chặn trong child, dù header parent cho phép origin đó.

**B. Từ chối geolocation ở header**

~~~http
Permissions-Policy: geolocation=(), fullscreen=(self "http://localhost:3001"), camera=(), microphone=()
~~~

Ngay cả khi iframe vẫn có `allow="geolocation"`, geolocation không thể được bật lại.

**C. Thử origin không khớp**

Đổi iframe sang một origin khác hoặc để endpoint child redirect sang origin khác. Khi origin đích không nằm trong header allowlist/iframe allowlist phù hợp, feature sẽ không được kế thừa như trước.

**D. Thử bỏ allow attribute**

Xóa `allow` khỏi iframe rồi kiểm tra lại. Feature sẽ tuân theo default allowlist của feature và header/ancestor policy. Kết quả có thể khác nhau giữa các feature; không giả định tất cả đều bị chặn giống nhau.

Sau lab, dừng cả hai server. Không dùng wildcard hoặc cấp camera/microphone cho nội dung bên thứ ba chỉ để làm thử nghiệm.

## 11. Lỗi thường gặp

| Lỗi | Vì sao sai | Cách sửa |
|---|---|---|
| Nghĩ `allow="geolocation"` tự động cấp quyền người dùng | Attribute chỉ cho phép feature trong policy; browser vẫn áp dụng permission và secure context | Xử lý prompt, denied state và API error |
| Dùng `allow="geolocation 'self'"` cho widget khác origin | `'self'` là origin trang cha | Dùng `'src'` hoặc origin widget cụ thể |
| Nghĩ allow có thể ghi đè header | Header/ancestor tạo giới hạn phía trên | Mở đúng origin trong header rồi giới hạn từng iframe |
| Dùng cú pháp header trong HTML attribute | Hai cú pháp serialization khác nhau | Dùng `feature 'src'` trong HTML; `feature=(...)` trong header |
| Dùng wildcard cho mọi iframe | Mở rộng feature sang origin không cần thiết | Allowlist origin cụ thể |
| Không xét redirect | `'src'` chỉ đại diện origin của URL src | Liệt kê origin điều hướng đã biết hoặc giữ redirect trong cùng origin |
| Nhầm allow với sandbox | Một cái quản lý feature, một cái áp hạn chế browsing context | Thiết kế và kiểm thử cả hai độc lập |
| Nhầm frame-src với allow | CSP quyết định nguồn frame; allow quyết định feature | Khai báo cả CSP và Permissions Policy theo mục tiêu |
| Nhầm allow với CORS | CORS kiểm soát đọc response, không cấp feature | Xử lý CORS riêng cho request cross-origin |
| Nghĩ allowfullscreen và allow="fullscreen" giống hệt | Legacy allowfullscreen có semantics allowlist rộng hơn | Dùng allow="fullscreen" và kiểm tra browser mục tiêu |
| Dựa vào API featurePolicy như chuẩn bảo mật | API chẩn đoán có thể khác/legacy giữa browser | Kiểm tra response header và hành vi thực tế |
| Không kiểm tra browser support | Feature/directive có thể không được hỗ trợ | Test browser mục tiêu và xử lý graceful fallback |

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Thuộc tính `allow` của iframe kiểm soát điều gì?

**Đáp án:** Nó khai báo container Permissions Policy cho iframe, xác định feature nào được delegate cho browsing context con và origin nào được phép dùng feature.

**Câu 2.** `allow="geolocation"` tương đương với cú pháp nào?

**Đáp án:** `allow="geolocation 'src'"`. Khi allowlist bị bỏ qua sau tên feature, mặc định là origin của URL trong thuộc tính `src`.

**Câu 3.** Trong `allow`, `'self'` và `'src'` khác nhau thế nào?

**Đáp án:** `'self'` là origin của document cha; `'src'` là origin của URL trong thuộc tính src của iframe.

**Câu 4.** Vì sao `allow="camera *"` không bật camera nếu header cha đặt `camera=()`?

**Đáp án:** Header/ancestor đã tắt feature. Iframe không thể nới lỏng policy đã bị ancestor từ chối.

**Câu 5.** Cú pháp `Permissions-Policy` header khác `allow` HTML ở điểm nào?

**Đáp án:** Header dùng structured syntax như `geolocation=(self "https://maps.example")`; HTML attribute dùng cú pháp feature policy cũ như `geolocation 'src'`, origin cụ thể không đặt trong dấu nháy.

**Câu 6.** `allow="fullscreen"` có tự động làm iframe fullscreen khi tải trang không?

**Đáp án:** Không. Feature được phép trong policy nhưng requestFullscreen thường vẫn cần user activation và điều kiện browser.

**Câu 7.** Nếu iframe có `allow="geolocation 'src'"` rồi điều hướng sang origin khác, origin mới có tự động nhận quyền không?

**Đáp án:** Không. Cần liệt kê origin điều hướng đó trong allowlist nếu muốn delegate feature cho nó và header ancestor cũng phải cho phép.

**Câu 8.** `allow` khác `sandbox` như thế nào?

**Đáp án:** allow kiểm soát Permissions Policy feature; sandbox giới hạn khả năng của tài liệu nhúng như script, form, popup, navigation và origin. Chúng có thể cùng áp dụng.

**Câu 9.** `allow` có thay thế CSP `frame-src` hoặc `frame-ancestors` không?

**Đáp án:** Không. frame-src kiểm soát trang cha được tải iframe từ đâu; frame-ancestors kiểm soát ai được nhúng trang con; allow kiểm soát feature của iframe.

**Câu 10.** Vì sao một iframe được phép geolocation vẫn có thể nhận lỗi NotAllowedError?

**Đáp án:** Người dùng có thể từ chối quyền, trang không phải secure context, browser/thiết bị không hỗ trợ, feature bị ancestor policy chặn hoặc API có điều kiện riêng.

## 13. Checklist triển khai allow attribute

Trước khi nhúng iframe có sử dụng feature trình duyệt, hãy kiểm tra:

1. **Nhu cầu:** widget thực sự cần feature nào? Bỏ mọi quyền không cần.
2. **Origin:** xác định chính xác scheme, host và port của iframe.
3. **Allowlist:** dùng `'src'` hoặc origin cụ thể; tránh `*` nếu không có lý do rõ.
4. **Header:** đặt Permissions-Policy header làm giới hạn tối đa cho các feature nhạy cảm.
5. **Inheritance:** kiểm tra policy của mọi ancestor; child không thể bật lại feature đã bị tắt.
6. **Navigation:** đánh giá redirect và origin đích; `'src'` không tự bao gồm origin mới.
7. **User permission:** xử lý prompt, denied state và secure context; không coi allow là user consent.
8. **User activation:** kiểm tra gesture cần thiết cho fullscreen/autoplay và API liên quan.
9. **Sandbox:** thiết kế sandbox độc lập, đặc biệt với nội dung không tin cậy.
10. **CSP:** cấu hình frame-src và frame-ancestors theo nguồn được phép nhúng/tải.
11. **Browser support:** kiểm tra từng feature trên browser mục tiêu và graceful fallback.
12. **Quan sát:** kiểm tra response header, iframe attribute, console violation và API error.
13. **Bên thứ ba:** review nhà cung cấp, script, redirect, postMessage và quyền thiết bị trước khi delegate.
14. **Rà soát định kỳ:** bỏ origin/feature không còn dùng và kiểm tra các tích hợp mới.

**Ghi nhớ:** `allow` là cách cấp feature có chọn lọc cho từng iframe. Dùng `'src'` để giới hạn vào origin của URL nhúng, dùng origin cụ thể cho luồng đã biết, và phối hợp với Permissions-Policy header để giữ giới hạn tối đa. Browser vẫn cần áp dụng secure context, user permission và điều kiện riêng của API. `allow` không thay sandbox, CSP, SOP hay CORS.

## Tài liệu tham khảo

- [W3C — Permissions Policy](https://www.w3.org/TR/permissions-policy/)
- [MDN — Permissions Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Permissions_Policy)
- [MDN — HTMLIFrameElement.allow](https://developer.mozilla.org/en-US/docs/Web/API/HTMLIFrameElement/allow)
- [MDN — iframe element](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/iframe)
- [MDN — Permissions-Policy header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Permissions-Policy)
- [Chrome for Developers — Control browser features with Permissions Policy](https://developer.chrome.com/docs/privacy-security/permissions-policy)

