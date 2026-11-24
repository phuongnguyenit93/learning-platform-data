# Xác thực Origin trong luồng khôi phục tài khoản (Origin validation)

## 1. Vì sao API recovery cần biết request bắt nguồn từ đâu?

Một trang khôi phục có thể sử dụng cookie để giữ phiên giới hạn sau khi người dùng chứng minh quyền nhận email hoặc hoàn thành một bước xác minh. Khi trình duyệt gửi cookie tự động, một website khác có thể tìm cách khiến trình duyệt gửi request tới dịch vụ recovery.

Ví dụ minh họa:

```http
POST /recovery/change-password HTTP/1.1
Host: accounts.example.test
Origin: https://untrusted.example.test
Cookie: __Host-Recovery=DEMO_SESSION_NOT_VALID
Content-Type: application/x-www-form-urlencoded

newPassword=DEMO_PASSWORD_NOT_REAL
```

Cookie hợp lệ, nếu có, chỉ cho biết request đang mang một phiên. Nó chưa chứng minh request xuất phát từ giao diện được dịch vụ tin cậy.

**Origin validation** là kiểm tra phía máy chủ đối với nguồn tạo request. Trong một thiết kế cùng origin, nguồn phải khớp origin công khai của dịch vụ. Nếu frontend và API khác origin, nguồn phải thuộc tập origin được cấp phép rõ ràng cho endpoint đó.

Đây là một lớp phòng vệ CSRF. Nó không thay thế xác thực người dùng, kiểm tra recovery token, phạm vi phiên, yêu cầu bằng chứng bổ sung hoặc tính nguyên tử khi tiêu thụ token.

## 2. Origin là scheme, host và port

Với các URL HTTP(S) thông thường, origin được xác định bởi bộ ba:

```text
(scheme, host, effective port)
```

Đường dẫn, query và fragment không thuộc origin. Quy tắc so sánh và chuẩn hóa cần được thực hiện nhất quán bằng thành phần xử lý URL/origin phù hợp, bao gồm cổng mặc định. [Nguồn: RFC 6454, mục 4–6](https://www.rfc-editor.org/rfc/rfc6454.html#section-4).

Giả sử origin được phép là `https://accounts.example.test`:

| Giá trị nguồn | Kết quả theo chính sách minh họa | Lý do |
| --- | --- | --- |
| `https://accounts.example.test` | Chấp nhận nguồn | Khớp bộ ba đã cấu hình |
| `https://accounts.example.test:443` | Cùng origin sau chuẩn hóa hợp lệ | Cổng HTTPS mặc định |
| `http://accounts.example.test` | Từ chối | Khác scheme |
| `https://accounts.example.test:8443` | Từ chối | Khác port |
| `https://help.example.test` | Từ chối nếu chưa được cấp phép | Host khác |
| `https://accounts.example.test.untrusted.test` | Từ chối | Là host khác hoàn toàn |
| `https://untrusted.test@accounts.example.test` | Từ chối header dạng này | Có userinfo, không phải biểu diễn Origin mà chính sách chấp nhận |
| `https://accounts.example.test/recovery` | Từ chối khi nằm trong Origin | Origin không phải URL trang có path |
| `null` | Không xác lập nguồn tin cậy | Không phải origin HTTPS được phép |

Bảng không yêu cầu tự viết một parser. Nó chỉ ra các thuộc tính mà thành phần parsing và chính sách cần bảo toàn. Đừng đưa mọi chuỗi qua một URL parser rồi mặc nhiên chấp nhận chỉ vì parser tìm được host mong muốn; đầu vào còn phải đúng dạng header mà ứng dụng hỗ trợ.

## 3. Origin header có ích gì và không chứng minh điều gì?

Header `Origin` mô tả origin gây ra request và không mang path như `Referer`. Trình duyệt kiểm soát header này; mã JavaScript thông thường không được tự đặt nó như một header tùy ý. Tuy vậy, sự hiện diện và giá trị của nó phụ thuộc ngữ cảnh request. [Nguồn: MDN — Origin header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Origin).

Thuộc tính này hữu ích trong mô hình CSRF: website tấn công không thể đơn giản yêu cầu trình duyệt thay origin nguồn bằng origin của dịch vụ recovery.

Nhưng một HTTP client ngoài trình duyệt có thể tự gửi:

```http
Origin: https://accounts.example.test
```

Vì thế, header khớp không chứng minh:

- Người gọi là chủ tài khoản.
- Recovery token còn hạn hoặc chưa dùng.
- Bằng chứng MFA đã được xác minh.
- Request có đúng mục đích giao dịch.
- Trình duyệt không bị XSS trên một origin được tin cậy.

Kết quả “nguồn được phép” chỉ cho request đi tiếp tới các kiểm tra còn lại. Nó không được trực tiếp cấp quyền đặt mật khẩu, xóa yếu tố xác thực hoặc tạo session đăng nhập.

## 4. Xác định nguồn và đích từ hai miền tin cậy khác nhau

Cần phân biệt:

- **Nguồn request:** lấy từ Origin hoặc, trong chính sách dự phòng có định nghĩa, origin trích từ Referer.
- **Đích công khai và danh sách nguồn được phép:** lấy từ cấu hình server hoặc mapping đã được kiểm soát.

Ví dụ:

```text
publicRecoveryOrigin:
    https://accounts.example.test

allowedBrowserMutationOrigins:
    https://accounts.example.test
```

Không tạo danh sách được phép bằng cách sao chép chính header Origin đang cần kiểm tra. Không lấy một tham số `trustedOrigin` trong body hoặc query làm cấu hình.

Đối với hệ thống nhiều tenant, host đầu vào chỉ được dùng để tìm trong mapping tenant/domain đã được đăng ký và xác minh. Biết một host bất kỳ hoặc gửi đúng header Host không tự tạo ra một tenant đáng tin.

OWASP lưu ý rằng ứng dụng sau reverse proxy có thể nhìn thấy host nội bộ thay vì đích công khai. Một giá trị public origin được cấu hình phía server giúp giữ rõ ranh giới tin cậy. [Nguồn: OWASP CSRF Prevention — Identifying the Target Origin](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html#identifying-the-target-origin).

## 5. Reverse proxy và forwarded header

Một đường đi thực tế có thể là:

```text
Trình duyệt
  -> https://accounts.example.test
  -> CDN hoặc reverse proxy
  -> http://recovery-service:8080
```

Nếu so sánh Origin của trình duyệt với `http://recovery-service:8080`, request hợp lệ bị từ chối. Cách sửa là xác định đúng cấu hình origin công khai, không tắt kiểm tra.

Khi cần dùng `Forwarded`, `X-Forwarded-Host` hoặc `X-Forwarded-Proto`, chỉ tin chúng qua ranh giới proxy đã cấu hình:

1. Ứng dụng nhận kết nối qua các proxy được xác định.
2. Proxy loại bỏ hoặc ghi đè giá trị forwarded do client gửi.
3. Quy tắc chọn giá trị trong chuỗi nhiều hop được định nghĩa rõ.
4. Đường truy cập trực tiếp vào backend không được dùng để bỏ qua ranh giới này.
5. Đích sau khi dựng lại vẫn thuộc tập host/scheme được dịch vụ chấp nhận.

Các quy tắc này là điều kiện triển khai của ví dụ, không phải bằng chứng xác thực caller. Forwarded header mô tả đường tới dịch vụ; nó không thay thế Origin hoặc Referer để xác định nguồn trang.

Không phản xạ một host chưa kiểm soát vào reset URL, redirect hoặc thông báo lỗi trong quá trình xử lý origin mismatch.

## 6. Thiếu Origin và Origin: null phải là hai trạng thái rõ ràng

Không phải mọi request đều có một Origin cụ thể. Một GET điều hướng có thể không mang header; một số ngữ cảnh tạo giá trị `null`.

`Origin: null` có thể xuất hiện do opaque origin, iframe sandbox hoặc chuỗi redirect và các quy tắc bảo vệ riêng tư. Nó không đồng nghĩa “cùng origin”, cũng không tự chứng minh request là độc hại. [Nguồn: MDN — Origin, Description](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Origin#description).

Một chính sách minh họa cho endpoint thay đổi qua trình duyệt:

| Trạng thái đầu vào | Cách xử lý |
| --- | --- |
| Origin cụ thể, hợp lệ và được phép | Đi tiếp; vẫn phải kiểm tra CSRF token và quyền |
| Origin cụ thể nhưng không được phép | Từ chối; không dùng Referer để đảo kết quả |
| Origin hỏng hoặc nhiều giá trị ngoài định dạng hỗ trợ | Từ chối |
| Không có Origin nhưng có Referer hợp lệ | Nếu chính sách cho phép, trích origin và so sánh chính xác |
| Không có cả hai nguồn đáng tin | Từ chối hoặc dùng một cơ chế chống CSRF thay thế đã được cấu hình rõ |
| Origin là `null` | Không allowlist `null`; áp dụng chính sách nguồn không xác định đã định nghĩa |

Ứng dụng có thể chọn chỉ hỗ trợ đúng một serialized origin cho endpoint recovery và từ chối header lặp hoặc danh sách nhiều giá trị. Đây là chính sách đầu vào của ứng dụng; không nên để các tầng proxy và framework tự chọn các giá trị khác nhau trong cùng một request.

### Dự phòng bằng Referer

Khi Origin thực sự vắng mặt và chính sách cho phép Referer fallback:

- Parse Referer như một URL tuyệt đối phù hợp.
- Trích scheme, host và port để so sánh.
- Không kiểm tra bằng `contains`, `startsWith` hoặc chỉ tên miền.
- Không ghi toàn bộ Referer vào log vì path hoặc query có thể chứa dữ liệu nhạy cảm.

Một Origin không được phép phải bị từ chối ngay. Không viết logic “Origin sai nhưng Referer đúng thì cho qua”.

## 7. Tương tác quan trọng với Referrer-Policy

Trang recovery thường muốn giảm rò rỉ URL bằng `Referrer-Policy: no-referrer`. Cần xem chính sách này cùng cách gửi form, không cấu hình chúng độc lập rồi giả định mọi request hợp lệ vẫn có Origin cụ thể.

Đối với một số request không dùng GET/HEAD và không ở chế độ CORS, bao gồm việc gửi HTML form, `no-referrer` có thể khiến Origin trở thành `null`, đồng thời Referer bị bỏ. Một fetch mặc định dùng chế độ CORS có cách xử lý khác, kể cả khi URL đích cùng origin. [Nguồn: MDN — Referrer-Policy, Effect on the Origin header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referrer-Policy#effect_on_the_origin_header), [WHATWG Fetch — Append a request Origin header](https://fetch.spec.whatwg.org/#append-a-request-origin-header).

Có hai kiểu chính sách có thể thiết kế rõ:

### Kiểu A: bắt buộc xác lập được nguồn

Endpoint chỉ nhận request có nguồn đáng tin từ Origin, hoặc Referer fallback nếu được cấu hình; đồng thời yêu cầu CSRF token phù hợp. Nếu gửi form theo cách làm cả hai nguồn không còn dùng được, client cần dùng một đường gửi được hỗ trợ hoặc thiết kế trang cần được điều chỉnh.

Không nới lỏng toàn bộ endpoint khi gặp trường hợp tương thích. Cũng không chuyển token recovery sang query để né kiểm tra.

### Kiểu B: có đường dự phòng bằng CSRF token

Với một endpoint HTML form cụ thể, dịch vụ có thể cho phép trường hợp nguồn không xác định nếu **một cơ chế chống CSRF độc lập đủ mạnh** thành công, chẳng hạn synchronizer token gắn với pre-session phía server.

Ở đường dự phòng này:

- Việc cho phép dựa trên CSRF token đã xác minh, không dựa trên chuỗi `null`.
- Token chống CSRF phải không đoán được, gắn với đúng phiên/ngữ cảnh và không bị lộ qua URL hoặc log.
- Origin cụ thể không được phép, header hỏng hoặc dữ liệu mâu thuẫn vẫn bị từ chối.
- Session, mục đích recovery và bằng chứng bổ sung vẫn được kiểm tra.
- Phạm vi ngoại lệ được định nghĩa theo endpoint; không mở một công tắc “thiếu Origin thì bỏ qua mọi kiểm tra”.

`null` có thể do cả ngữ cảnh hợp lệ lẫn ngữ cảnh kẻ tấn công tạo ra. Server không thể phân biệt chúng chỉ từ giá trị header. Chính vì vậy, đường dự phòng phải có cơ chế bảo vệ riêng chứ không chỉ có lời giải thích về trình duyệt.

## 8. Mã giả cho chính sách bắt buộc nguồn tin cậy

Mã giả sau chọn kiểu A ở trên. Nó không mô tả mọi biến thể triển khai và không tự cung cấp parser:

```text
validateBrowserRecoveryMutation(request, routePolicy):
    yêu cầu endpoint không thay đổi nghiệp vụ bằng GET hoặc HEAD
    allowed = routePolicy.allowedCanonicalOrigins

    originValues = đọc toàn bộ giá trị header Origin

    nếu có nhiều giá trị ngoài định dạng được hỗ trợ:
        từ chối SOURCE_NOT_ACCEPTED

    nếu có Origin:
        nếu Origin là null:
            từ chối SOURCE_UNAVAILABLE

        source = parseSupportedSerializedOrigin(Origin)
        nếu parse thất bại hoặc source không thuộc allowed:
            từ chối SOURCE_NOT_ACCEPTED

    ngược lại:
        nếu không cho phép Referer fallback:
            từ chối SOURCE_UNAVAILABLE

        source = extractOriginFromValidReferer(request)
        nếu không xác lập được source hoặc source không thuộc allowed:
            từ chối SOURCE_NOT_ACCEPTED

    kiểm tra CSRF token gắn với đúng phiên biểu mẫu
    kiểm tra recovery session, mục đích, hạn dùng và bằng chứng
    kiểm tra điều kiện trạng thái hiện tại
    chỉ sau đó thực hiện chuyển trạng thái nghiệp vụ
```

Thành phần `parseSupportedSerializedOrigin` cần có hợp đồng cụ thể: giới hạn kích thước, hỗ trợ đúng scheme, xử lý host và cổng nhất quán, từ chối userinfo, path, query, fragment và dữ liệu thừa không hợp lệ. Không áp dụng một chuỗi decode tùy ý để “cứu” đầu vào bất thường.

Không đánh dấu token đã dùng, tăng bộ đếm nhập sai bằng chứng hoặc xóa yếu tố xác thực trước khi request qua các cổng bảo vệ cần thiết. Có thể ghi nhận từ chối theo một bộ đếm an ninh riêng mà không biến nó thành khóa tài khoản nạn nhân.

## 9. Same-origin, same-site và CORS là các khái niệm khác nhau

### Same-site chưa đủ để chấp nhận origin

`https://accounts.example.test` và `https://community.example.test` là hai origin khác nhau, dù có thể được trình duyệt phân loại cùng site. Một subdomain bị chiếm quyền hoặc cho người dùng đăng nội dung không nên tự được quyền gửi hành động recovery.

Vì vậy, không thay allowlist chính xác bằng wildcard cho toàn bộ subdomain. Cookie SameSite và thông tin same-site không khẳng định mọi ứng dụng cùng miền đăng ký đều đáng tin.

`Sec-Fetch-Site` phân biệt các giá trị như same-origin, same-site, cross-site và none. Nó có thể hỗ trợ một lớp quyết định sớm, nhưng cần chính sách rõ cho client không gửi header và cho frontend được phép khác origin. [Nguồn: MDN — Sec-Fetch-Site](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Sec-Fetch-Site).

### CORS không đồng nghĩa request chưa từng tới server

CORS điều khiển cách trình duyệt chia sẻ response cho mã phía client; một số request cần preflight, trong khi HTML form và các request đơn giản có thể được gửi mà không có bước này. Vì vậy, không dựa vào việc trang tấn công “không đọc được response” để kết luận hành động không xảy ra. [Nguồn: MDN — CORS Guide](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS).

Nếu frontend được phép là `https://app.example.test`, còn API là `https://accounts.example.test`, cần cấu hình rõ quyền CORS, credential và allowlist nguồn cho đúng endpoint. Không phản xạ mọi Origin và bật credential cùng lúc.

OPTIONS preflight không được thực hiện hành động recovery. Request POST thực tế vẫn phải qua các kiểm tra của nó.

## 10. Không làm hỏng bước mở liên kết từ email

Người dùng có thể điều hướng từ webmail, trình duyệt nhúng hoặc ứng dụng khác tới liên kết recovery. Một GET đầu vào không cần chứng minh nó được sinh từ trang recovery đã tải trước đó, vì người dùng chưa hề ở trang ấy.

Thiết kế cần tách:

1. **Tiếp nhận và trình bày:** GET nhận liên kết, tạo trạng thái tạm có giới hạn nếu cần, hiển thị trang hoặc chuyển sang URL sạch.
2. **Thực hiện quyền:** POST xác nhận hoặc thay đổi, được bảo vệ theo chính sách nguồn, CSRF và quyền giao dịch.

Không thêm origin của mọi nhà cung cấp email vào allowlist hành động chỉ để cho phép người dùng mở thư. GET đầu vào phải an toàn ngay cả khi bộ quét liên kết hoặc trang khác kích hoạt.

Tương tự, callback của một giao thức xác minh qua nhà cung cấp ngoài cần thiết kế riêng với các ràng buộc của giao thức. Không biến một ngoại lệ callback thành miễn kiểm tra nguồn cho mọi endpoint đặt lại mật khẩu hoặc MFA.

## 11. Native app và client ngoài trình duyệt

Một ứng dụng mobile hoặc tác vụ máy chủ có thể không gửi Origin. Không nên giải quyết bằng quy tắc:

```text
nếu không có Origin hoặc User-Agent trông giống mobile:
    bỏ qua kiểm tra và thực hiện recovery
```

Kẻ gửi request tự chọn User-Agent. Không có Origin cũng không chứng minh request không đến từ trình duyệt.

Nếu có API dành cho client ngoài trình duyệt, cần một contract riêng về xác thực, khả năng tự động đính kèm credential, quyền theo giao dịch và chống dùng lại. Có thể dùng endpoint hoặc chính sách rõ ràng khác với browser flow, nhưng không được cho một request cookie-based tự nhận mình là native để thoát bảo vệ CSRF.

Origin validation chủ yếu hỗ trợ mô hình an ninh của trình duyệt. Nó không phải cơ chế chống giả mạo mọi HTTP client trên Internet.

## 12. Phản hồi từ chối, quan sát và giới hạn còn lại

Khi nguồn không được chấp nhận, có thể trả 403 với thông điệp chung và mã hỗ trợ ngẫu nhiên. Không trả danh sách origin nội bộ, recovery token, email hoặc lý do xác minh tài khoản sâu hơn.

Một bản ghi vận hành tối giản có thể chứa:

```json
{
  "event": "recovery_request_rejected",
  "route": "CHANGE_PASSWORD",
  "reason": "SOURCE_NOT_ACCEPTED",
  "sourceClass": "UNTRUSTED",
  "requestId": "DEMO_REQUEST_ID"
}
```

Các giá trị phân loại do server tạo từ enum. Không ghi raw Referer, toàn bộ URL hoặc header tùy ý vào log chỉ để tìm origin mismatch. Nếu cần quan sát nguồn cụ thể, phải có giới hạn và chính sách giảm thiểu dữ liệu phù hợp.

Ba giới hạn cuối cùng cần giữ rõ:

- XSS trên origin được phép có thể tạo request mang Origin hợp lệ; vẫn cần phòng vệ XSS và giảm mã bên thứ ba trên trang recovery.
- Request từ nguồn đúng vẫn có thể chứa token sai, phiên hết hạn hoặc thao tác ngoài quyền; backend phải kiểm tra tất cả.
- Chính sách tương thích cho header thiếu/null phải được thiết kế trước; không sửa sự cố bằng một nhánh cho phép mặc định.

Một nguồn request đáng tin là một điều kiện để tiếp tục xử lý, không phải kết luận rằng người dùng đã được quyền khôi phục tài khoản.
