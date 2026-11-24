# Permissions-Policy

> **Chương:** Security headers  
> **Học phần:** Application Security — Browser Security (`SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY`)

Một trang web có thể sử dụng camera, microphone, geolocation, fullscreen, clipboard, payment API và nhiều khả năng khác của browser. Các tính năng này hữu ích, nhưng một trang nhúng từ bên thứ ba không nhất thiết cần được sử dụng tất cả quyền đó. **Permissions-Policy** là HTTP response header giúp chủ sở hữu trang giới hạn những browser feature mà tài liệu và các frame con được phép sử dụng.

Ví dụ, một ứng dụng chỉ cần hiển thị nội dung có thể tắt camera, microphone và geolocation. Một trang họp trực tuyến có thể cho phép camera/microphone ở chính origin của nó và delegate hai quyền đó cho iframe của nhà cung cấp cuộc họp. Browser vẫn áp dụng permission của người dùng, secure context và các điều kiện riêng của API; header không tự cấp quyền truy cập thiết bị.

Permissions Policy là một lớp giảm bề mặt tấn công và kiểm soát quyền của nội dung nhúng. Nó không thay thế Same-Origin Policy, CORS, CSP, iframe sandbox, xác thực người dùng hay phân quyền server-side.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích Permissions Policy và lý do cần giới hạn browser feature.
2. Cấu hình HTTP header `Permissions-Policy` bằng allowlist rõ ràng.
3. Phân biệt cú pháp header với thuộc tính `allow` của iframe.
4. Hiểu default allowlist và cách policy được kế thừa qua frame lồng nhau.
5. Delegate camera, microphone, geolocation hoặc fullscreen cho đúng iframe.
6. Phân biệt policy của browser với permission prompt do người dùng quyết định.
7. Kết hợp Permissions Policy với CSP, sandbox, SOP và CORS.
8. Triển khai header trên server, kiểm tra response và xử lý lỗi tương thích.
9. Kiểm thử feature bị cho phép/từ chối trong môi trường lab.

## 2. Permissions Policy giải quyết vấn đề gì?

Browser cung cấp nhiều API có thể truy cập phần cứng, dữ liệu hoặc khả năng tương tác nhạy cảm. Ví dụ:

- Camera và microphone có thể thu âm thanh/hình ảnh.
- Geolocation có thể tiết lộ vị trí thiết bị.
- Clipboard có thể đọc hoặc ghi nội dung người dùng đang sao chép.
- Screen capture có thể chia sẻ nội dung màn hình.
- Payment API có thể khởi tạo luồng thanh toán.
- USB hoặc các API thiết bị có thể tương tác với phần cứng.
- Fullscreen có thể thay đổi cách nội dung chiếm toàn bộ màn hình.

Một trang có thể nhúng video, quảng cáo, widget chat, dashboard hoặc ứng dụng đối tác trong iframe. Nếu không giới hạn feature, frame có thể yêu cầu sử dụng các API mà tính năng đó không cần. Permissions Policy cho phép chủ sở hữu tài liệu đặt một **allowlist theo feature**, rồi quyết định có delegate một số feature cho frame cụ thể hay không.

Ví dụ response header:

```http
Permissions-Policy: camera=(), microphone=(), geolocation=()
```

Policy này từ chối ba feature trong tài liệu và các context con chịu sự kế thừa của policy. Nó không có nghĩa browser sẽ chặn mọi request mạng của trang hoặc vô hiệu hóa JavaScript nói chung.

## 3. Permissions Policy không phải permission của người dùng

Có hai lớp quyết định khác nhau:

1. **Permissions Policy:** website có được phép sử dụng feature trong context hiện tại hay không?
2. **User permission:** người dùng đã cấp quyền cho origin sử dụng feature hay chưa?

Để camera hoạt động, cả policy lẫn các điều kiện permission của browser/người dùng phải cho phép. Nếu Permissions Policy từ chối camera, việc người dùng đã từng cấp quyền cho origin cũng không làm policy bị bỏ qua. Ngược lại, policy cho phép camera không có nghĩa người dùng đã đồng ý bật camera.

Các API như camera, microphone và geolocation còn yêu cầu secure context trong các browser hiện đại. Browser có thể yêu cầu user activation, hiển thị permission prompt, áp dụng giới hạn theo thiết bị hoặc từ chối vì cài đặt riêng tư.

Vì vậy, không dùng Permissions Policy như bằng chứng rằng người dùng đã đồng ý. Ứng dụng vẫn cần giải thích mục đích, xin quyền đúng thời điểm, xử lý trường hợp bị từ chối và cung cấp lựa chọn tắt tính năng.

## 4. Cú pháp HTTP header `Permissions-Policy`

Header dùng tên feature và allowlist. Một số dạng thường gặp:

```http
Permissions-Policy: geolocation=(self), camera=(), microphone=(), fullscreen=(self)
```

| Cú pháp | Ý nghĩa |
| --- | --- |
| `feature=()` | Không cho phép origin nào sử dụng feature trong policy này |
| `feature=(self)` | Chỉ cho phép cùng origin với tài liệu áp dụng policy |
| `feature=(self "https://partner.example")` | Cho phép cùng origin và origin được liệt kê |
| `feature=*` | Cho phép mọi origin trong phạm vi policy, theo khả năng hỗ trợ của feature/browser |

Đây là cú pháp Structured Fields của header hiện đại. `self` trong header không đặt trong dấu nháy đơn; origin được đặt trong dấu nháy kép. Ví dụ `camera=(self "https://meet.example.com")`.

Không nhầm cú pháp này với CSP. Trong CSP, source thường viết như `'self'`; trong Permissions Policy header, giá trị là `self` không có dấu nháy đơn. Cũng không nhầm với cú pháp thuộc tính `allow` của iframe, nơi các từ khóa như `'self'`, `'src'` và `'none'` được viết theo cú pháp riêng.

`Feature-Policy` là tên header cũ/thử nghiệm trước đây. Với triển khai hiện đại, dùng `Permissions-Policy` và cú pháp hiện hành; nếu phải hỗ trợ browser cũ, kiểm tra compatibility theo browser matrix thay vì giả định header cũ và mới có thể thay thế nhau trong mọi môi trường.

## 5. Ý nghĩa của allowlist

Allowlist xác định origin nào được dùng feature trong một policy. Các lựa chọn quan trọng:

| Allowlist | Ý nghĩa | Khi sử dụng |
| --- | --- | --- |
| `()` | Không origin nào được phép | Feature không được ứng dụng sử dụng |
| `(self)` | Chỉ origin hiện tại | Ứng dụng tự dùng feature, không delegate rộng |
| `(self "https://widget.example")` | Origin hiện tại và một origin cụ thể | Widget đối tác đã được phê duyệt |
| `*` | Mọi origin | Chỉ cân nhắc khi feature thật sự cần cho mọi origin; thường quá rộng |

Origin là bộ ba scheme, host và port. `https://meet.example.com` khác `http://meet.example.com`, khác `https://meet.example.com:8443` và khác `https://sub.meet.example.com`. Hãy liệt kê origin chính xác, không dùng wildcard chỉ để tránh phải quản lý danh sách.

Nếu một feature không được khai báo, browser áp dụng **default allowlist** được định nghĩa cho feature đó. Giá trị mặc định có thể khác nhau: một số feature mặc định cho `self`, một số cho phép rộng hơn, một số bị tắt. Không giả định mọi feature đều mặc định an toàn như nhau; hãy kiểm tra default allowlist của từng feature và khai báo rõ những quyền nhạy cảm.

## 6. Các feature thường cần xem xét

Tên feature trong header thường là tên chuẩn hóa bằng chữ thường và dấu gạch nối. Danh sách hỗ trợ thay đổi theo browser và phiên bản.

| Feature | Khả năng được kiểm soát | Lý do cần đánh giá |
| --- | --- | --- |
| `camera` | Truy cập camera | Thu thập hình ảnh/video |
| `microphone` | Truy cập microphone | Thu thập âm thanh |
| `geolocation` | Truy cập vị trí | Dữ liệu vị trí nhạy cảm |
| `display-capture` | Chia sẻ màn hình | Có thể lộ nội dung màn hình |
| `fullscreen` | Chuyển nội dung sang fullscreen | Ảnh hưởng cách người dùng quan sát giao diện |
| `autoplay` | Tự động phát media | Trải nghiệm và quyền kiểm soát media |
| `clipboard-read` | Đọc clipboard | Có thể tiếp cận dữ liệu người dùng sao chép |
| `clipboard-write` | Ghi clipboard | Có thể thay nội dung người dùng định dán |
| `payment` | Payment API | Liên quan tới luồng thanh toán |
| `usb` | WebUSB | Truy cập thiết bị USB được hỗ trợ |
| `serial` | Web Serial | Giao tiếp thiết bị serial |
| `bluetooth` | Web Bluetooth | Khám phá/kết nối thiết bị Bluetooth |
| `accelerometer`, `gyroscope`, `magnetometer` | Sensor API | Dữ liệu chuyển động và môi trường |
| `publickey-credentials-get` | Truy xuất credential WebAuthn theo feature policy | Ảnh hưởng luồng xác thực trong frame |
| `screen-wake-lock` | Ngăn thiết bị ngủ theo API | Quyền giữ màn hình hoạt động |
| `web-share` | Chia sẻ qua hệ thống của thiết bị | Chuyển dữ liệu sang ứng dụng khác |

Không phải browser nào cũng hỗ trợ mọi feature; tên và hành vi có thể thay đổi theo tiêu chuẩn. Hãy xác minh feature cần dùng trên browser mục tiêu, và tránh thêm feature vào policy nếu ứng dụng không có nhu cầu thực tế.

## 7. Ví dụ: từ chối feature không sử dụng

Một ứng dụng nội bộ chỉ hiển thị dashboard và không cần camera, microphone, geolocation, USB hoặc payment API có thể bắt đầu bằng:

```http
Permissions-Policy: camera=(), microphone=(), geolocation=(), usb=(), payment=()
```

Đây là cấu hình từ chối các feature đã liệt kê. Nó giúp giảm khả năng một dependency hoặc frame vô tình sử dụng chúng. Tuy nhiên, đây không phải allowlist đầy đủ cho toàn bộ browser; cần xác định feature nào ứng dụng thực sự dùng và kiểm tra default allowlist của phần còn lại.

Nếu trang cần geolocation ở chính origin:

```http
Permissions-Policy: geolocation=(self), camera=(), microphone=()
```

Khi đó tài liệu cùng origin có thể yêu cầu geolocation, nhưng vẫn cần secure context và permission của người dùng. Frame cross-origin không tự được cấp geolocation chỉ vì parent được phép.

## 8. Thuộc tính `allow` của iframe

Response header đặt giới hạn cho tài liệu; thuộc tính `allow` trên iframe delegate feature cho một frame cụ thể trong phạm vi policy của parent.

Ví dụ:

```html
<iframe
  src="https://meet.example.com/room"
  allow="camera 'src'; microphone 'src'; fullscreen 'src'"
  title="Phòng họp trực tuyến"></iframe>
```

Ở đây, `'src'` là từ khóa của thuộc tính iframe, biểu thị origin của URL `src` được cho phép với feature tương ứng. Parent chỉ delegate camera, microphone và fullscreen cho frame đó, thay vì cho mọi frame trên trang.

Các từ khóa trong iframe `allow` có cú pháp khác với HTTP header:

```html
<iframe allow="geolocation 'self'; camera 'none'"></iframe>
```

Trong thuộc tính `allow`, các từ khóa đặc biệt thường được viết trong dấu nháy đơn. Trong HTTP header, dạng tương đương dùng `geolocation=(self); camera=()`.

Không dùng `allow` để thay thế header của parent. Nếu response header đã từ chối một feature, thuộc tính `allow` không thể tự mở lại quyền đó.

## 9. Kế thừa policy qua frame lồng nhau

Policy của frame con chịu giới hạn từ policy của tài liệu cha và container policy được đặt trên iframe. Response header của tài liệu con có thể tiếp tục giới hạn feature trong chính tài liệu đó. Một frame lồng sâu không thể tự cấp lại feature mà một ancestor đã từ chối.

Ví dụ:

```http
Permissions-Policy: camera=(self "https://meet.example.com")
```

Parent cho phép camera cho chính nó và origin cuộc họp. Nhưng để frame cuộc họp thực sự nhận quyền, parent còn cần delegate trên iframe:

```html
<iframe
  src="https://meet.example.com/room"
  allow="camera 'src'"
  title="Cuộc họp"></iframe>
```

Nếu `meet.example.com` tiếp tục nhúng một frame khác, quyền camera không tự động lan truyền vô hạn. Policy của frame trung gian và thuộc tính `allow` trên container tiếp theo tiếp tục quyết định quyền được delegate. Hãy kiểm tra từng bước trong ancestor chain.

## 10. Ví dụ đầy đủ: delegate camera và microphone cho nhà cung cấp họp

Giả sử ứng dụng `https://app.example.com` nhúng dịch vụ họp `https://meet.example.com`. Ứng dụng không muốn các widget khác truy cập camera/microphone.

Response header của trang parent:

```http
Permissions-Policy: camera=(self "https://meet.example.com"), microphone=(self "https://meet.example.com"), geolocation=(), usb=()
```

Iframe:

```html
<iframe
  src="https://meet.example.com/room/123"
  allow="camera 'src'; microphone 'src'; fullscreen 'src'"
  referrerpolicy="strict-origin-when-cross-origin"
  title="Cuộc họp với đối tác"></iframe>
```

Response của `meet.example.com` có thể tiếp tục giới hạn feature theo nhu cầu riêng của dịch vụ. Browser vẫn yêu cầu người dùng cấp quyền camera/microphone; nếu người dùng từ chối, API sẽ không hoạt động dù policy cho phép.

Nếu ứng dụng chỉ cần camera/microphone trong frame cuộc họp, có thể bỏ `self` khỏi header parent để chính parent không được dùng hai feature đó. Hãy chọn allowlist đúng với kiến trúc thực tế.

## 11. `src` và origin được delegate

Trong thuộc tính `allow`, từ khóa `'src'` giúp ràng buộc feature với origin của URL `src` của iframe. Cách này thuận tiện khi frame có URL ổn định và ứng dụng muốn cấp quyền cho chính dịch vụ đó.

Nếu dùng origin cụ thể thay cho `'src'`, cần đảm bảo nó khớp origin thực tế của frame:

```html
<iframe
  src="https://meet.example.com/room"
  allow="camera https://meet.example.com; microphone https://meet.example.com"
  title="Cuộc họp"></iframe>
```

Redirect hoặc thay đổi URL đích có thể làm origin thực tế khác dự kiến. Không tự động delegate cho một URL redirect chưa được kiểm soát. Hãy xác minh endpoint cuối cùng và giới hạn origin ở cả header parent lẫn iframe container.

## 12. Permissions Policy và permission prompt

Ví dụ JavaScript sử dụng geolocation:

```js
navigator.geolocation.getCurrentPosition(
  ({ coords }) => {
    console.log(coords.latitude, coords.longitude);
  },
  (error) => {
    console.error("Không lấy được vị trí", error.code, error.message);
  }
);
```

Lệnh gọi có thể thất bại vì nhiều lý do:

- Tài liệu không ở secure context.
- Permissions Policy không cho phép geolocation trong context hiện tại.
- Người dùng đã từ chối hoặc chưa cấp permission.
- Browser hoặc hệ điều hành không hỗ trợ/không bật dịch vụ vị trí.
- Request timeout hoặc thiết bị không xác định được vị trí.

Ứng dụng cần xử lý lỗi rõ ràng và không lặp lại prompt gây phiền. Không suy luận rằng `Permissions-Policy` cho phép feature đồng nghĩa API chắc chắn thành công.

Với camera/microphone, `navigator.mediaDevices.getUserMedia()` cũng chịu policy, secure context và user permission. Với clipboard, fullscreen hoặc payment, còn có thể có điều kiện user activation và yêu cầu riêng của API.

## 13. Phân biệt Permissions Policy với các cơ chế khác

| Cơ chế | Câu hỏi nó trả lời | Ví dụ |
| --- | --- | --- |
| Permissions Policy | Tài liệu/frame có được sử dụng browser feature này không? | `camera=()` |
| CSP `frame-src` | Trang cha được tải iframe từ nguồn nào? | `frame-src https://meet.example.com` |
| CSP `frame-ancestors` | Trang hiện tại được origin nào nhúng? | `frame-ancestors 'self'` |
| iframe `sandbox` | Frame được phép chạy script, submit form, mở popup hay điều hướng không? | `sandbox="allow-scripts"` |
| SOP | Script có được truy cập DOM/dữ liệu của origin khác không? | Chặn đọc `contentDocument` cross-origin |
| CORS | JavaScript có được đọc response cross-origin không? | `Access-Control-Allow-Origin` |
| User permission | Người dùng có cấp quyền cho feature không? | Cho phép camera trong browser prompt |
| Server authorization | Người dùng có quyền thực hiện hành động/dữ liệu không? | Kiểm tra quyền trên API |

Các lớp này bổ sung cho nhau. Permissions Policy không chặn việc tải iframe; CSP `frame-src` mới giới hạn nguồn frame. `sandbox` có thể hạn chế nhiều năng lực của frame nhưng không thay thế allowlist feature. CORS không phải cơ chế delegate camera hay geolocation.

## 14. Triển khai header trên server

Permissions Policy được gửi bằng HTTP response header. Không dùng `<meta http-equiv="Permissions-Policy">` như một cách thay thế.

Ví dụ Express:

```js
app.use((req, res, next) => {
  res.setHeader(
    "Permissions-Policy",
    "camera=(), microphone=(), geolocation=(), usb=(), payment=()"
  );
  next();
});
```

Ví dụ Nginx:

```nginx
add_header Permissions-Policy "camera=(), microphone=(), geolocation=(), usb=(), payment=()" always;
```

Đây là policy minh họa cho ứng dụng không cần các feature được liệt kê. Nếu một route cần camera hoặc geolocation, hãy tạo policy phù hợp với route đó và kiểm thử response. `always` giúp header được thêm vào nhiều loại response status theo cấu hình Nginx; cần xác minh không có location block khác ghi đè hoặc bỏ header.

Đặt header tại lớp có thể quản lý response HTML cuối cùng: ứng dụng, reverse proxy hoặc CDN. Kiểm tra Network để xác nhận header thật sự được gửi trên document response, không chỉ xem file cấu hình.

## 15. Feature mặc định và policy tường minh

Mỗi feature có default allowlist riêng trong định nghĩa Permissions Policy. Nếu một feature không được khai báo, browser dùng giá trị mặc định đó. Vì default có thể là `self`, `*` hoặc `none`, việc bỏ qua directive có thể tạo ra quyền khác với điều nhóm phát triển dự kiến.

Một số nguyên tắc:

- Với feature nhạy cảm, khai báo rõ `()` nếu ứng dụng không cần.
- Nếu chỉ ứng dụng chính cần feature, dùng `(self)`.
- Nếu cần delegate, liệt kê origin cụ thể và cấu hình iframe `allow` tương ứng.
- Tránh `*` trừ khi sản phẩm có yêu cầu thực sự cho mọi origin.
- Theo dõi feature mới được browser hỗ trợ và cập nhật policy theo threat model.

Không sao chép một danh sách feature dài từ ứng dụng khác mà không hiểu từng mục. Một số feature có thể chưa được browser hỗ trợ hoặc đã thay đổi tên/trạng thái; header không thay thế quá trình kiểm thử.

## 16. Nhiều frame và widget bên thứ ba

Một trang có thể nhúng nhiều widget với nhu cầu khác nhau:

| Frame | Nhu cầu | Cách delegate |
| --- | --- | --- |
| Video công khai | Autoplay hoặc fullscreen tùy trải nghiệm | Chỉ delegate feature cần thiết cho origin video |
| Bản đồ | Geolocation có thể không cần nếu chỉ hiển thị bản đồ tĩnh | Không cấp geolocation mặc định |
| Widget họp | Camera, microphone, fullscreen | Chỉ cho phép origin nhà cung cấp họp |
| Chat hỗ trợ | Thường không cần camera/microphone | Từ chối các feature không liên quan |
| Quảng cáo | Thường không cần feature thiết bị | Dùng allowlist tối thiểu hoặc từ chối |

Không dùng một iframe wrapper chung có `allow="camera; microphone; geolocation; ..."` cho mọi widget. Hãy cấu hình theo loại nội dung và origin cụ thể. Nếu widget được tải động, mapping origin → feature cần được kiểm soát bởi code/cấu hình đáng tin cậy; không lấy origin từ input người dùng rồi ghép thẳng vào policy.

## 17. Tương tác với iframe sandbox

`sandbox` và Permissions Policy giải quyết hai khía cạnh khác nhau:

- `sandbox` hạn chế năng lực của tài liệu trong frame như script, form, popup, download, top-level navigation và origin behavior.
- Permissions Policy giới hạn browser feature cụ thể như camera, microphone, geolocation, fullscreen hoặc clipboard.

Ví dụ:

```html
<iframe
  src="https://widget.example.net/embed"
  sandbox="allow-scripts"
  allow="fullscreen 'src'"
  title="Widget xem nội dung"></iframe>
```

Frame được phép chạy script và yêu cầu fullscreen theo policy, nhưng vẫn chịu các hạn chế sandbox khác. Nếu sandbox làm origin thành opaque hoặc chặn một hành vi cần thiết, không tự động thêm `allow-same-origin` hoặc các token khác. Xem lại mức tin cậy, origin và tính năng thực sự cần.

Một feature bị sandbox hoặc Permissions Policy từ chối sẽ không được mở lại chỉ bằng cách nới lớp còn lại. Hãy kiểm tra cả hai policy khi debug.

## 18. Những giới hạn và điều không nên giả định

Permissions Policy có một số giới hạn cần hiểu rõ:

- Không phải mọi browser đều hỗ trợ cùng danh sách feature hoặc cú pháp mới nhất.
- Header không tự cấp user permission và không bỏ qua secure context.
- Policy không kiểm soát mọi API web; chỉ các feature được chuẩn hóa và triển khai tương ứng.
- Policy không thay thế server-side authorization hoặc kiểm tra quyền trên API.
- Policy không ngăn frame gửi request mạng thông thường.
- Policy không thay thế CSP, SOP, CORS hoặc anti-clickjacking.
- Feature được phép trong parent không tự động có nghĩa mọi child được phép dùng; delegation và inheritance vẫn áp dụng.
- Một permission prompt không xuất hiện có thể do policy, browser setting, user decision hoặc điều kiện API khác.

Hãy xác minh trên browser/version thực tế. Không dựa vào một browser duy nhất nếu sản phẩm hỗ trợ nhiều nền tảng.

## 19. Kiểm tra và chẩn đoán

### 19.1 Kiểm tra response header

Trong DevTools → Network:

1. Chọn document response của trang top-level.
2. Tìm `Permissions-Policy` trong Response Headers.
3. Kiểm tra header có đúng route, đúng môi trường và đúng origin không.
4. Chọn request của iframe và xác nhận URL/origin cuối cùng sau redirect.
5. Kiểm tra thuộc tính `allow` của iframe trong Elements.
6. Đọc Console để tìm thông báo feature bị chặn bởi Permissions Policy.

Nếu header được thêm tại proxy/CDN, kiểm tra response cuối cùng sau tất cả lớp trung gian. Cấu hình ở source code không bảo đảm header tồn tại ở browser.

### 19.2 Kiểm tra feature trong code

Feature detection cho biết API có tồn tại, nhưng không chứng minh policy cho phép:

```js
const hasGeolocationApi = "geolocation" in navigator;
console.log({ hasGeolocationApi });
```

Ngay cả khi API tồn tại, lời gọi vẫn có thể bị policy hoặc user permission từ chối. Hãy thực hiện kiểm thử trong browser thật và xử lý lỗi API. Một số browser cung cấp API kiểm tra policy riêng, nhưng tên và mức hỗ trợ không đồng đều; không dựa vào một API kiểm tra không chuẩn để thay thế test hành vi.

### 19.3 Phân loại nguyên nhân

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Camera không mở | Header từ chối, iframe chưa delegate, user từ chối, không phải secure context | Kiểm tra response, `allow`, Console và permission browser |
| Parent dùng được nhưng iframe không dùng được | Header cho `self` nhưng chưa delegate qua iframe `allow` | Kiểm tra origin child và container policy |
| Iframe có `allow` nhưng vẫn bị chặn | Parent header từ chối hoặc ancestor policy giới hạn | Kiểm tra toàn bộ ancestor và response header |
| Feature hoạt động trên browser A nhưng không trên B | Khác biệt hỗ trợ feature/default allowlist | Kiểm tra browser/version và feature support |
| Geolocation không hiện prompt | Policy chặn, user đã từ chối, secure context hoặc browser setting | Kiểm tra Console, permission state và API error |
| Header cấu hình đúng nhưng không thấy ở browser | Proxy/CDN/location block ghi đè hoặc không gắn header | Kiểm tra Network response cuối cùng |

## 20. Triển khai theo giai đoạn

Một quy trình triển khai thực tế:

1. **Inventory:** liệt kê browser feature mà ứng dụng và từng iframe đang dùng.
2. **Owner:** xác định module/nhà cung cấp chịu trách nhiệm cho từng feature.
3. **Baseline:** kiểm tra default allowlist và browser matrix.
4. **Policy:** từ chối feature không cần; chỉ allow `self` hoặc origin cụ thể khi có nhu cầu.
5. **Delegation:** cấu hình `allow` riêng cho từng iframe.
6. **Test:** kiểm tra permission prompt, API success/failure, nested frame và user denial.
7. **Rollout:** phát hành header theo route/môi trường, theo dõi lỗi và phản hồi người dùng.
8. **Review:** rà soát định kỳ các origin được delegate và thu hồi quyền khi tích hợp kết thúc.

Không nên mở `*` hoặc cấp tất cả feature cho mọi iframe để sửa lỗi nhanh. Hãy xác định feature nào bị chặn, frame nào cần dùng và origin nào sở hữu frame đó.

## 21. Thực hành kiểm chứng trong môi trường lab

Chỉ sử dụng trang local hoặc domain thử nghiệm do bạn kiểm soát. Dùng thiết bị lab và dữ liệu giả; không yêu cầu camera/microphone hoặc vị trí của người khác.

### Bài thử A — Từ chối geolocation

1. Tạo trang HTTPS lab có nút gọi `navigator.geolocation.getCurrentPosition`.
2. Gửi response header `Permissions-Policy: geolocation=()`.
3. Tải lại và bấm nút.
4. Quan sát Console và error callback.
5. Đổi policy thành `geolocation=(self)` và thử lại với quyền browser được cấp trong môi trường lab.

**Kỳ vọng:** `()` từ chối feature theo policy; `(self)` cho phép origin hiện tại yêu cầu feature nhưng vẫn phụ thuộc user permission và secure context.

### Bài thử B — Parent delegate camera cho iframe

1. Chạy parent và child trên hai origin lab khác nhau.
2. Đặt header parent `camera=(self "https://child.lab.example.test")`.
3. Nhúng child với `allow="camera 'src'"`.
4. Trong child, gọi `navigator.mediaDevices.getUserMedia({ video: true })` với camera lab.
5. Bỏ thuộc tính `allow` rồi tải lại để so sánh.

**Kỳ vọng:** Feature chỉ có thể được dùng khi policy parent cho phép, container delegate đúng và người dùng cấp quyền. Không dùng camera thật nếu không cần; có thể chỉ quan sát lỗi policy trên browser test.

### Bài thử C — Header từ chối không thể được iframe mở lại

Đặt header parent `camera=()` rồi thêm `allow="camera 'src'"` vào iframe.

**Kỳ vọng:** Thuộc tính `allow` không thể nới policy đã từ chối ở parent. Ghi lại thông báo trong Console.

### Bài thử D — Nested iframe

Tạo parent → child → grandchild. Delegate feature cho child nhưng không delegate từ child tới grandchild. Quan sát API trong từng frame.

**Kỳ vọng:** Quyền không tự lan truyền qua mọi tầng; từng container/ancestor policy phải cho phép delegation.

### Bài thử E — Phân biệt policy và user permission

Cho phép geolocation trong policy, sau đó từ chối permission ở browser. Thử gọi API và quan sát lỗi. Sau đó cấp permission lại trong lab và thử lần nữa.

**Kỳ vọng:** Permissions Policy cho phép feature nhưng không thay quyết định của người dùng. API chỉ hoạt động khi các điều kiện khác cũng đáp ứng.

## 22. Các lỗi cấu hình thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng cú pháp CSP `'self'` trong header Permissions Policy | Header có thể không được parse như mong muốn | Dùng `self` trong `feature=(self)` |
| Nhầm cú pháp header với iframe `allow` | Delegate không hoạt động | Header dùng `camera=(self)`; iframe dùng `allow="camera 'src'"` |
| Chỉ cấu hình header parent | Frame cần quyền vẫn bị chặn | Delegate qua `allow` trên iframe cụ thể |
| Thêm `allow` nhưng parent đã đặt `camera=()` | Quyền không được mở lại | Sửa policy parent theo đúng nhu cầu và threat model |
| Dùng `*` cho mọi feature | Mở quyền quá rộng cho frame | Dùng `()`/`(self)` và origin allowlist cụ thể |
| Cho rằng policy cho phép đồng nghĩa user đã cấp quyền | API vẫn có thể bị từ chối | Xử lý permission prompt và lỗi API |
| Nhầm Permissions Policy với CORS | CORS không delegate camera/geolocation | Cấu hình đúng cơ chế cho đúng feature |
| Nghĩ `frame-src` kiểm soát feature của iframe | `frame-src` chỉ giới hạn nguồn frame được tải | Dùng Permissions Policy và `allow` |
| Tin default allowlist luôn là `self` | Một số feature có default khác | Kiểm tra từng feature và khai báo rõ |
| Không kiểm tra browser support | Policy có thể khác nhau giữa browser | Có browser matrix và test thực tế |
| Chỉ kiểm tra cấu hình server | Proxy/CDN có thể làm thay đổi response | Kiểm tra header cuối qua Network |

## 23. Checklist review Permissions Policy

- [ ] Đã liệt kê browser feature ứng dụng và iframe thực sự cần.
- [ ] Feature nhạy cảm không sử dụng được đặt thành `()` khi phù hợp.
- [ ] Feature chỉ dùng trong app được giới hạn bằng `(self)`.
- [ ] Origin bên thứ ba được allowlist chính xác, gồm scheme/host/port.
- [ ] Không dùng `*` nếu không có lý do nghiệp vụ rõ ràng.
- [ ] Đã kiểm tra default allowlist của feature không khai báo.
- [ ] Header được gửi qua HTTP response, không dựa vào meta tag.
- [ ] Thuộc tính `allow` chỉ delegate feature cần thiết cho iframe cụ thể.
- [ ] Đã phân biệt cú pháp header và cú pháp iframe `allow`.
- [ ] Đã kiểm tra nested iframe và policy inheritance.
- [ ] User permission, secure context và user activation được xử lý riêng.
- [ ] Đã phân biệt Permissions Policy với CSP, sandbox, SOP và CORS.
- [ ] Không coi policy là thay thế authorization phía server.
- [ ] Đã kiểm tra response cuối qua proxy/CDN và browser mục tiêu.
- [ ] Có test cho trạng thái được phép, bị từ chối và user denial.
- [ ] Origin được delegate được rà soát và thu hồi khi không còn cần.

## 24. Câu hỏi tự kiểm tra

1. Permissions Policy kiểm soát điều gì và khác permission prompt ra sao?
2. `camera=()` và `camera=(self)` khác nhau như thế nào?
3. Vì sao default allowlist của từng feature cần được kiểm tra?
4. Cú pháp `self` trong HTTP header khác `'self'` trong iframe `allow` như thế nào?
5. Thuộc tính iframe `allow` delegate quyền theo cách nào?
6. Vì sao `allow` không thể mở lại feature mà policy parent đã từ chối?
7. Khi nào nên dùng `'src'` trong thuộc tính iframe `allow`?
8. Permissions Policy khác CSP `frame-src` và `frame-ancestors` ra sao?
9. Vì sao một API có thể tồn tại nhưng lời gọi vẫn bị policy hoặc user permission từ chối?
10. Cần kiểm tra những gì khi feature hoạt động trong parent nhưng không hoạt động trong iframe?

## 25. Ghi nhớ

Permissions Policy giới hạn browser feature mà tài liệu và frame con được phép sử dụng. HTTP header đặt allowlist theo feature: `()` để từ chối, `(self)` để giới hạn cùng origin và danh sách origin cụ thể để delegate có kiểm soát. Thuộc tính `allow` trên iframe tiếp tục giới hạn/delegate feature cho frame đó; nó không thể mở lại quyền đã bị policy của parent từ chối.

Policy cho phép không đồng nghĩa người dùng đã cấp quyền. Secure context, permission prompt, user activation và điều kiện riêng của API vẫn áp dụng. Hãy cấp đúng feature cho đúng origin, kiểm tra từng tầng iframe và kết hợp Permissions Policy với CSP, sandbox, SOP, CORS cùng authorization server-side. **Mục tiêu là giảm quyền browser mà mỗi tài liệu được sử dụng xuống đúng mức tính năng thực sự cần.**
