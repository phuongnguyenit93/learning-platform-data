# Recovery page origin — Origin của trang khôi phục tài khoản

## 1. Origin là một phần của ranh giới tin cậy

Trang khôi phục nhận dữ liệu có thể dẫn tới đặt lại mật khẩu, thay đổi MFA hoặc đăng ký lại phương thức xác thực. Vì vậy, quyết định đặt trang ở đâu liên quan trực tiếp tới những mã JavaScript, ứng dụng và dịch vụ có thể tác động tới quá trình khôi phục.

Một trang có đúng logo và giao diện chưa chứng minh nó thuộc hệ thống. HTTPS bảo vệ kết nối tới hostname đang truy cập, nhưng một hostname giả cũng có thể có chứng chỉ hợp lệ. Người dùng cần tới đúng địa chỉ chính thức; hệ thống cần bảo đảm cả liên kết được phát hành lẫn nơi nhận dữ liệu đều thuộc ranh giới đã chọn.

Có ba địa chỉ cần phân biệt trong thiết kế:

| Thành phần | Câu hỏi cần trả lời |
| --- | --- |
| Origin của trang | HTML và mã chạy trong trình duyệt được cung cấp từ đâu? |
| Origin của API | Token, mật khẩu mới và thao tác xác nhận được gửi tới đâu? |
| Đích điều hướng sau recovery | Người dùng sẽ được chuyển tới địa chỉ nào khi hoàn thành? |

Ba thành phần có thể cùng origin hoặc khác nhau theo kiến trúc. Việc cho phép một đích không tự động cho phép hai đích còn lại. Một URL hợp lệ để quay về trang đăng nhập không mặc nhiên là nơi được nhận token recovery.

## 2. Origin gồm những gì?

Đối với URL HTTP(S) thông thường, origin được xác định bởi scheme, host và port. Path, query và fragment không tạo ra origin mới. Cách phân chia này được mô tả trong [RFC 6454 về Web Origin](https://www.rfc-editor.org/rfc/rfc6454.html).

Lấy `https://accounts.example.invalid/recovery/start` làm địa chỉ chính thức trong ví dụ:

| URL so sánh | Cùng origin? | Giải thích |
| --- | --- | --- |
| `https://accounts.example.invalid/login` | Có | Chỉ khác path |
| `https://accounts.example.invalid/recovery/start?step=2` | Có | Query không đổi origin |
| `https://accounts.example.invalid:443/recovery/start` | Có | 443 là port mặc định của HTTPS |
| `http://accounts.example.invalid/recovery/start` | Không | Khác scheme |
| `https://accounts.example.invalid:8443/recovery/start` | Không | Khác port hiệu lực |
| `https://help.example.invalid/recovery/start` | Không | Khác host |
| `https://accounts.example.invalid.attacker.invalid/recovery/start` | Không | Host thuộc địa chỉ khác |

Các domain `.invalid` trong bài chỉ dùng minh họa, không phải endpoint hoạt động.

Một hệ quả quan trọng: đặt recovery ở `/secure/recovery` không tách nó khỏi `/blog` trên cùng origin. Tên thư mục nghe an toàn không tạo thêm một lớp cách ly của trình duyệt.

### Same-origin và same-site phục vụ những ranh giới khác nhau

Hai subdomain có thể khác origin nhưng vẫn cùng site. Với HTTP(S), khái niệm site xét scheme và miền đăng ký được; port không phân tách site như origin. Đây là sự khác biệt được nêu trong [HTML Standard về origin và site](https://html.spec.whatwg.org/multipage/browsers.html#sites).

Vì vậy, một trang trên subdomain tiếp thị không được xem là đồng nhất với trang recovery chỉ vì cùng công ty quản lý. Quyền thực tế phải xét theo origin và các cơ chế liên quan, không suy từ sự giống nhau của tên miền.

## 3. Chọn nơi đặt trang recovery

Mục tiêu là thu hẹp những thành phần có khả năng thực thi mã hoặc thay đổi nội dung trên trang khôi phục. Việc chọn riêng một hostname chỉ có giá trị khi quyền triển khai, nội dung và cấu hình của hostname đó cũng được quản lý phù hợp.

| Phương án | Điểm thuận lợi | Điều phải kiểm soát |
| --- | --- | --- |
| Cùng origin với ứng dụng chính | Gọi API tương đối và tích hợp phiên đơn giản | Mã trên origin ứng dụng có thể ảnh hưởng tới recovery nếu bị khai thác |
| Subdomain chuyên dụng, như `accounts.example.invalid` | Có thể tách ứng dụng, cookie và quyền triển khai | Vẫn phải xét quan hệ same-site và rủi ro từ subdomain lân cận |
| Domain đăng ký riêng cho định danh | Có thể tách thêm ranh giới site | Tăng yêu cầu quản lý domain, nhận diện địa chỉ và tích hợp giữa các hệ thống |

Không có phương án duy nhất phù hợp cho mọi sản phẩm. Với ứng dụng nhỏ được quản lý chặt, dùng cùng origin có thể hợp lý. Với nền tảng có nội dung người dùng, nhiều nhóm triển khai hoặc nhiều tenant, tách trang định danh thường giúp thể hiện ranh giới rõ hơn, nhưng không tự sửa các lỗi phân quyền.

Những nội dung cần đặc biệt cân nhắc khi dùng chung origin với recovery gồm trang HTML do khách hàng tải lên, trình xem tài liệu có thể thực thi script, ứng dụng cũ ít được bảo trì và plugin do bên ngoài quản lý. Nếu một thành phần như vậy có lỗ hổng cho phép chạy script trên cùng origin, path recovery không tạo ra hàng rào ngăn cách riêng.

Ngay cả khi file script được tải từ một domain khác, script được trang đưa vào thực thi vẫn có thể tương tác với trang theo quyền của ngữ cảnh đó. Do đó, lựa chọn origin cần đi cùng quyết định mã nào được phép chạy trên trang recovery.

## 4. Phát hành liên kết từ cấu hình tin cậy

Origin chính thức cần có nguồn cấu hình được kiểm soát phía server. Không lấy trực tiếp hostname từ request yêu cầu quên mật khẩu để dựng liên kết gửi email. OWASP cảnh báo việc dựa vào header `Host` có thể dẫn tới Host Header Injection; URL reset nên dùng địa chỉ cố định hoặc danh sách domain tin cậy. [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).

Ví dụ cấu hình thiết kế, không phải một schema bắt buộc:

```yaml
recovery:
  publicOrigin: https://accounts.example.invalid
  entryPath: /recovery/start
  completionPath: /login
```

Đoạn JavaScript sau minh họa việc tạo URL trong thành phần phát hành liên kết phía server:

```javascript
const RECOVERY_ORIGIN = "https://accounts.example.invalid";

function buildRecoveryLink(opaqueToken) {
  const link = new URL("/recovery/start", RECOVERY_ORIGIN);
  link.searchParams.set("token", opaqueToken);
  return link.href;
}
```

Đoạn mã dùng API URL để phân tích địa chỉ và mã hóa tham số, thay vì ghép token thẳng vào chuỗi URL. API này được định nghĩa trong [WHATWG URL Standard](https://url.spec.whatwg.org/#api). Ví dụ chỉ minh họa nguồn origin và cách dựng link; nó không bao gồm sinh, lưu, xác minh hay thu hồi token. URL kết quả vẫn chứa bí mật và không được đưa nguyên vẹn vào log.

Trong mô hình reverse proxy, backend có thể nhìn thấy host hoặc scheme nội bộ. Cấu hình public origin giúp tránh vô tình gửi link tới hostname nội bộ hoặc dùng HTTP. Nếu hệ thống thực sự cần thông tin chuyển tiếp, chỉ tin dữ liệu do proxy được xác định là tin cậy cung cấp và đối chiếu với cấu hình domain được phép; không tin mọi `X-Forwarded-Host` do client gửi.

Với hệ thống đa tenant, ánh xạ từ tenant sang recovery origin phải nằm trong cấu hình đã xác minh. Một trường `tenantDomain` ở body request không phải bằng chứng người gửi kiểm soát domain đó. Khi không tìm được ánh xạ hợp lệ, hệ thống không tự dùng domain do client gợi ý làm phương án dự phòng.

## 5. So sánh địa chỉ bằng thành phần URL

Kiểm tra origin không nên dựa trên việc chuỗi chứa tên thương hiệu hoặc bắt đầu bằng một đoạn quen thuộc. Ví dụ:

```text
https://accounts.example.invalid.attacker.invalid/recovery
https://accounts.example.invalid@attacker.invalid/recovery
```

Ở URL thứ nhất, host có phần đuôi khác. Ở URL thứ hai, phần đứng trước `@` là user information; host thực sự là `attacker.invalid`. Một phép tìm chuỗi `accounts.example.invalid` có thể chấp nhận cả hai.

Một chính sách cho recovery nên định nghĩa rõ scheme HTTPS, origin chính xác và các path được phục vụ. Việc phân tích và chuẩn hóa dùng thư viện URL phù hợp với môi trường; sau đó so sánh với danh sách nhỏ các giá trị tin cậy. Không dùng `endsWith("example.invalid")` như toàn bộ quy tắc xác thực domain.

Nếu một URL được dùng làm đích quay về, kiểm tra cùng origin vẫn chưa đủ: một path trên origin chính thức có thể là endpoint chuyển hướng tiếp. Chọn đích cố định hoặc ánh xạ một mã nội bộ như `LOGIN` sang đường dẫn đã biết thường dễ kiểm soát hơn nhận URL tùy ý.

Một đoạn JavaScript tự kiểm tra `window.location.origin` trên trang chính thức chỉ hỗ trợ logic giao diện. Nó không ngăn kẻ giả mạo dựng một website khác rồi xóa đoạn kiểm tra đó. Server vẫn phải kiểm soát nơi phát hành và tiếp nhận credential; người dùng vẫn cần nhận diện đúng hostname.

## 6. Giữ trang và API trong ranh giới đã chọn

Một phương án dễ diễn giải là phục vụ cả trang và API recovery dưới origin chuyên dụng, ví dụ:

```text
GET  https://accounts.example.invalid/recovery/start
POST https://accounts.example.invalid/recovery/confirm
```

Frontend có thể gọi endpoint tương đối `/recovery/confirm`. Hạ tầng phía sau có thể là nhiều service, nhưng trình duyệt vẫn tương tác với public origin đã xác định. Routing nội bộ không nên biến một tham số từ client thành đích upstream tùy ý.

Nếu frontend và API khác origin, cần cấu hình tích hợp rõ ràng: origin frontend nào được dùng, request nào mang credential và cơ chế nào cho phép thực hiện hành động. CORS là giao thức để server cho phép chia sẻ response giữa các origin trong trình duyệt; nó không xác minh quyền khôi phục một tài khoản. [Fetch Standard về CORS](https://fetch.spec.whatwg.org/#http-cors-protocol).

Không phản chiếu mọi header `Origin` vào `Access-Control-Allow-Origin` chỉ để frontend hết lỗi. Không đưa token vào URL của một API bên ngoài do tham số trên trang quyết định. Việc trình duyệt không cho script đọc response cũng không chứng minh request chưa tới server.

### Phiên recovery và cookie

Nếu dùng cookie cho phiên recovery, có thể chọn cookie host-only với thuộc tính phù hợp. Ví dụ sau chỉ dùng giá trị giả:

```http
Set-Cookie: __Host-recovery=DEMO_SESSION_NOT_VALID; Secure; HttpOnly; Path=/; SameSite=Lax
```

Tiền tố `__Host-` yêu cầu `Secure`, `Path=/` và không có `Domain`, giúp giới hạn cookie vào host đã đặt. Cookie vẫn không được cách ly theo port. `HttpOnly` hạn chế đọc cookie bằng JavaScript, không ngăn script gửi request bằng phiên đó. [Đặc tả HTTP Cookies](https://httpwg.org/http-extensions/draft-ietf-httpbis-rfc6265bis.html).

Giá trị `SameSite` cần phù hợp luồng đi vào từ email và điều hướng hợp lệ. Không mặc định rằng đặt `Strict` luôn giữ nguyên trải nghiệm; người dùng mở link từ ngoài site có thể chưa gửi cookie có sẵn. Phiên recovery cũng cần quyền hạn hẹp, không tự trở thành phiên đăng nhập đầy đủ chỉ vì trình duyệt đã có cookie.

### Origin của request và chống CSRF

Với hành động thay đổi trạng thái, server cần cơ chế chống CSRF phù hợp, như token CSRF gắn phiên kết hợp kiểm tra nguồn request. Header `Origin` và Fetch Metadata là tín hiệu hữu ích trong ngữ cảnh trình duyệt; chúng không thay thế bằng chứng người dùng đã vượt qua xác minh recovery. Không dựa riêng vào `SameSite` khi subdomain lân cận có thể không đáng tin cậy. [OWASP CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).

Mở trang bằng GET không nên trực tiếp đổi mật khẩu, xóa MFA hay đăng ký phương thức xác thực mới. Các bước đó cần hành động xác nhận và trạng thái xác minh hợp lệ phía server. Yêu cầu thiếu tín hiệu nguồn cần có chính sách xử lý rõ cho endpoint liên quan, thay vì tự xem là đáng tin.

## 7. Bảo vệ ngữ cảnh hiển thị của trang chính thức

Trang recovery có thể bị đặt trong iframe của website khác để đánh lừa thao tác. Form cũng có thể bị hướng tới một đích ngoài dự kiến nếu trang bị thay đổi. CSP cung cấp các chỉ thị kiểm soát việc nhúng trang và đích submit form. [Content Security Policy Level 3](https://www.w3.org/TR/CSP3/).

Ví dụ response header cho một trang tự chứa, chỉ dùng tài nguyên cùng origin:

```http
Content-Security-Policy: default-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'
```

Trong ví dụ, `frame-ancestors 'none'` cấm nhúng trang; `form-action 'self'` giới hạn nơi gửi form; `connect-src 'self'` giới hạn kết nối do các API chịu chỉ thị này quản lý. `frame-ancestors` phải được gửi qua HTTP header, không có hiệu lực khi chỉ đặt trong thẻ meta.

Đây là chính sách minh họa cho kiến trúc nói trên. Nếu ứng dụng cần API khác origin hoặc script nội tuyến, phải thiết kế nguồn và cơ chế cho phép tương ứng. Mở rộng bằng wildcard chỉ để tránh lỗi sẽ làm yếu ranh giới đã chọn. CSP cũng không sửa lỗi phân quyền ở API hoặc khiến một origin đã bị chiếm quyền trở nên đáng tin.

## 8. Ví dụ thiết kế cho nền tảng khôi phục tài khoản

Giả sử một nền tảng có ba khu vực:

```text
app.example.invalid          Ứng dụng chính
accounts.example.invalid     Đăng nhập và khôi phục
uploads.example.invalid      Nội dung do người dùng cung cấp
```

Đây là cách phân bổ minh họa, không phải xác nhận ba subdomain đã được cách ly đầy đủ.

Một luồng recovery có thể diễn ra như sau:

1. Người dùng yêu cầu khôi phục từ ứng dụng; server xác định tài khoản và tạo yêu cầu theo chính sách chống lạm dụng.
2. Thành phần gửi email dựng link từ public origin `https://accounts.example.invalid`, không dùng host do người yêu cầu cung cấp.
3. Trình duyệt mở trang trên origin đó. Trang không cần chạy script từ khu vực uploads hoặc công cụ hỗ trợ bên ngoài để xác minh token.
4. Các bước xác nhận gửi tới API recovery đã chọn. Server kiểm tra token, trạng thái yêu cầu, quyền hạn của phiên và chính sách chống CSRF tương ứng.
5. Sau hoàn thành, hệ thống vô hiệu quyền recovery phù hợp và đưa người dùng tới đích đăng nhập đã định trước. Không chuyển tiếp token recovery sang ứng dụng bằng URL quay về.

Nếu `uploads.example.invalid` gặp sự cố, origin khác giúp tránh việc xem nó như cùng một ngữ cảnh trang với accounts. Tuy nhiên, request từ uploads vẫn cần được xem xét theo chính sách server; quan hệ same-site không đủ để cấp quyền thay đổi mật khẩu. Nếu accounts dùng cookie có `Domain=example.invalid`, phạm vi cookie cũng cần được xem xét lại thay vì suy rằng tên subdomain đã giải quyết toàn bộ việc tách phiên.

Trong trường hợp mất MFA hoặc passkey, origin đúng chỉ bảo vệ một phần đường tương tác. Chính sách chứng minh danh tính, quyền đăng ký phương thức mới và xử lý session cũ vẫn phải do server thực thi. Giao diện đang ở đúng hostname không phải bằng chứng rằng người thao tác là chủ tài khoản.

## 9. Những nhầm lẫn thường gặp

| Nhầm lẫn | Hệ quả đối với recovery |
| --- | --- |
| Đổi path là tách origin | Mã không đáng tin trên cùng origin vẫn có thể ảnh hưởng trang |
| Cùng domain công ty là cùng mức tin cậy | Subdomain do tenant hoặc bên ngoài vận hành có thể có rủi ro khác |
| HTTPS chứng minh website chính thức | Người dùng vẫn có thể đang ở hostname giả |
| CORS cho phép thì được đổi mật khẩu | API vẫn phải xác minh quyền recovery và trạng thái hợp lệ |
| Cookie host-only cách ly mọi thành phần origin | Cookie không được giới hạn theo port |
| Header `Origin` đúng là đã xác minh danh tính | Nguồn request và quyền sở hữu tài khoản là hai điều kiện riêng |
| Trang chính thức được phép redirect tùy ý | Credential hoặc người dùng có thể bị đưa ra khỏi ranh giới đã chọn |

Origin của trang recovery cần được xác định từ cấu hình tin cậy và duy trì qua toàn bộ luồng: liên kết ban đầu, mã chạy trên trang, nơi nhận dữ liệu và đích điều hướng cuối. Ranh giới đó giúp giảm các thành phần có thể tiếp cận quá trình khôi phục, còn quyết định cho phép thay đổi tài khoản luôn cần bằng chứng và kiểm soát phía server.
