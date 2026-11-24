# Cross origin recovery calls

## 1. Vì sao recovery có lời gọi khác origin?

Một hệ thống có thể tách giao diện và API khôi phục:

```text
Giao diện: https://app.example.com
API:      https://recovery.example.com
```

JavaScript chạy ở giao diện gọi API trên host khác nên đây là **cross-origin call**. Kiến trúc này có thể hợp lệ, nhưng cần quyết định rõ origin nào được đọc response, credential nào được gửi và cách backend chống request giả mạo.

Ví dụ, sau khi người dùng xác minh một bước recovery, API có thể cấp cookie phiên giới hạn. Giao diện cần gọi API để lấy bước tiếp theo hoặc hoàn tất việc đặt lại mật khẩu. Nếu cấu hình quá rộng, một trang không tin cậy cũng có thể lợi dụng phiên này.

Mục tiêu không phải mở CORS cho request “hết lỗi”. Mục tiêu là cho đúng giao diện thực hiện đúng thao tác, với đúng ngữ cảnh recovery và các lớp kiểm tra tại server.

Các tên miền, endpoint và giá trị trong bài đều là minh họa.

## 2. Phân biệt origin, site và tài khoản

Origin gồm scheme, host và port. Trong ví dụ trên, hai host khác nhau nên khác origin. Với cùng HTTPS và miền đăng ký example.com, chúng có thể cùng site.

| Hai URL | Quan hệ minh họa |
| --- | --- |
| `https://app.example.com` và `https://recovery.example.com` | Khác origin, cùng site |
| `https://app.example.net` và `https://recovery.example.com` | Khác origin, khác site |
| `https://app.example.com` và `https://app.example.com:8443` | Khác origin do port |

Sự khác biệt này quan trọng vì CORS xét origin, còn SameSite của cookie xét ngữ cảnh site. “Cùng site” không tự cấp quyền đọc response của origin khác.

Tài khoản lại là một ràng buộc riêng. Một origin nằm trong danh sách cho phép không có nghĩa mọi tài khoản do client gửi đều được phép tác động. API vẫn phải lấy tài khoản và mục đích từ credential hoặc trạng thái recovery đã xác minh.

Tương tự, quyền gọi API để đặt lại mật khẩu không tự mở quyền gỡ MFA, đăng ký passkey hoặc thay thiết bị xác thực.

## 3. Ba quyết định không được đánh đồng

Một lời gọi recovery cần phân biệt:

| Quyết định | Câu hỏi |
| --- | --- |
| Chính sách trình duyệt và CORS | Mã ở origin này được gửi loại request cần preflight và đọc response đến mức nào? |
| Authentication và authorization | Request có credential hợp lệ, đúng account, purpose và trạng thái không? |
| Phòng vệ CSRF và nguồn request | Request dùng credential tự gửi có đáp ứng điều kiện chống giả mạo của endpoint không? |

CORS chủ yếu là giao thức cho phép chia sẻ response giữa các origin, cùng cơ chế preflight cho những loại request nhất định. Nó không xác minh chủ tài khoản. Xem [Fetch Standard về CORS protocol](https://fetch.spec.whatwg.org/#http-cors-protocol).

Một client ngoài trình duyệt có thể gọi API mà không bị trình duyệt thực thi CORS. Vì vậy, server không thể dùng danh sách origin như cơ chế authorization duy nhất.

Chiều ngược lại cũng quan trọng: một form cross-origin có thể tạo request không cần preflight. Nếu server đã thực hiện thay đổi, việc script bên ngoài không được đọc response không hoàn tác thay đổi đó.

## 4. Chọn cách mang credential trước khi cấu hình CORS

Có hai mô hình thường gặp:

| Mô hình | Đặc điểm cần xem xét |
| --- | --- |
| Phiên recovery dùng cookie | Trình duyệt tự gắn cookie khi đủ điều kiện; cần phòng vệ CSRF phù hợp |
| Token recovery do client chủ động gắn | Phải bảo vệ bí mật, giới hạn audience/purpose và tránh gửi nhầm đích |

Không suy ra rằng JWT luôn không cần chống CSRF. JWT đặt trong cookie tự gửi vẫn cần được đánh giá theo hành vi cookie. Một endpoint nhận bearer token nhưng có đường fallback sang cookie cũng không thể được coi là chỉ dùng bearer token.

Bài này dùng mô hình cookie recovery cho ví dụ chính. Cookie thuộc host API, không cần mở `Domain=.example.com` để JavaScript ở app đọc được.

```http
Set-Cookie: recovery_session=DEMO_NOT_VALID; Path=/api/recovery; Secure; HttpOnly; SameSite=Lax
```

Cookie này phù hợp với phạm vi URL API được minh họa; các route ngoài phạm vi đó cần được thiết kế riêng. Cookie Path không phải cơ chế phân quyền nghiệp vụ.

Với frontend và API khác origin, lời gọi fetch mặc định không gửi cookie như lời gọi cùng origin. Client cần chọn chế độ credential phù hợp. Theo [MDN về credentials trong Fetch](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch#including_credentials), `credentials: "include"` cho phép dùng credential trong lời gọi cross-origin, nhưng không vượt qua hạn chế SameSite hay chính sách cookie khác của trình duyệt.

Do đó, khi frontend thực sự khác site, cookie Lax hoặc Strict không được gửi trong cross-site fetch chỉ nhờ thêm `include`. Chuyển sang `SameSite=None; Secure` cũng không bảo đảm mọi trình duyệt cho phép cookie bên thứ ba. Đây là quyết định kiến trúc và chính sách cookie, không phải lý do bỏ kiểm tra CSRF.

## 5. Ví dụ một lời gọi từ frontend tin cậy

Giả sử:

- Giao diện chạy ở `https://app.example.com`.
- API chạy ở `https://recovery.example.com`.
- Người dùng đã có cookie recovery hợp lệ.
- Giao diện đã lấy token CSRF gắn với đúng phiên qua API được bảo vệ.
- Endpoint yêu cầu JSON và header token CSRF.

Đoạn mã minh họa:

```javascript
async function completePasswordRecovery(csrfToken, newPassword) {
  const response = await fetch(
    "https://recovery.example.com/api/recovery/password",
    {
      method: "POST",
      mode: "cors",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken
      },
      body: JSON.stringify({ newPassword })
    }
  );

  if (!response.ok) {
    throw new Error("Khong the hoan tat khoi phuc.");
  }

  return response.json();
}
```

Đích API là cấu hình tin cậy, không lấy trực tiếp từ query, fragment hoặc trường do trang ngoài quyết định. Không gắn token CSRF hay bearer token vào mọi URL qua một interceptor toàn cục thiếu giới hạn đích.

Token CSRF không phải password-reset token gửi qua email. Nó không thay quyền recovery; cookie và trạng thái server vẫn phải cho phép hành động tương ứng.

Không dùng `mode: "no-cors"` để sửa lỗi cấu hình. Chế độ đó hạn chế request và không cho ứng dụng đọc response theo cách cần thiết; nó không tạo quyền gọi API hay bỏ qua yêu cầu bảo mật.

## 6. Preflight cho phép kiểu lời gọi, không cấp quyền recovery

Với JSON và custom header trong ví dụ, trình duyệt thực hiện preflight khi cần và chưa có kết quả phù hợp trong bộ nhớ preflight:

```http
OPTIONS /api/recovery/password HTTP/1.1
Host: recovery.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
```

Response cho origin và contract được phép có thể là:

```http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: POST
Access-Control-Allow-Headers: Content-Type, X-CSRF-Token
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
```

Các header được liệt kê rõ cho endpoint này. Server không cần phản chiếu mọi method và header mà client đề nghị.

Preflight cross-origin không mang cookie phiên của request thực tế theo giao thức Fetch. Vì vậy, không yêu cầu nó phải có cookie recovery hoặc giá trị token CSRF như POST. Cũng không chạy logic recovery trong OPTIONS. Response preflight chỉ trả lời liệu trình duyệt có được tiếp tục kiểu lời gọi đó hay không.

POST sau đó vẫn phải kiểm tra nguồn theo policy, credential, CSRF token, tài khoản, purpose, thời hạn và trạng thái hiện hành.

Không giả định mỗi POST đều có một OPTIONS mới ngay trước nó: trình duyệt có thể dùng lại quyền preflight đã lưu. Nếu cần rút quyền của một origin, backend vẫn cần thực thi chính sách nguồn trên request thực tế, không chỉ sửa nhánh OPTIONS.

## 7. Response thực tế cũng cần chính sách đúng

Ví dụ response thành công:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin

{
  "status": "COMPLETED"
}
```

Với lời gọi có chế độ credential include, không dùng `Access-Control-Allow-Origin: *`. Response cần một origin cụ thể được cho phép và cấu hình credential tương ứng; xem [MDN về CORS với credential](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS#requests_with_credentials).

Một response chỉ mang một giá trị origin được chấp nhận, không phải danh sách nhiều URL phân cách bằng dấu phẩy. Khi hỗ trợ nhiều frontend, server chọn origin phù hợp từ allowlist đã xác minh.

Nếu giá trị header phụ thuộc `Origin` của request, dùng `Vary: Origin` và giữ các giá trị Vary cần thiết khác. [MDN về Access-Control-Allow-Origin và cache](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Origin#cors_and_caching) giải thích vai trò này.

`Vary` không thay chính sách không lưu dữ liệu recovery nhạy cảm. Response cá nhân hóa vẫn cần `no-store` và cấu hình trung gian phù hợp.

Các lỗi nghiệp vụ từ origin hợp lệ cũng cần được xử lý nhất quán. Nếu frontend được phép đọc kết quả lỗi trung tính, response lỗi có thể mang header CORS tương ứng mà vẫn trả status lỗi. Không biến mọi lỗi thành thành công chỉ để tránh console báo vấn đề.

Với origin không được tin cậy, không chia sẻ response nhạy cảm và phải chặn thao tác theo chính sách backend trước khi có thay đổi.

## 8. Thiết kế allowlist hẹp và rõ

Một allowlist minh họa:

```text
Recovery browser clients:
  https://app.example.com

Not automatically allowed:
  https://preview.example.com
  https://customer-content.example.com
  http://app.example.com
  https://app.example.com:8443
  null
```

Đó là lựa chọn của ví dụ, không phải danh sách áp dụng cho mọi hệ thống. Origin phát triển hoặc môi trường preview cần cấu hình riêng và không được vô tình có quyền đọc dữ liệu production.

Không chọn origin bằng kiểm tra chuỗi như:

```text
Origin contains "example.com"
Origin ends with an unvalidated suffix
Reflect any Origin that the client supplies
```

Server cần kiểm tra cú pháp serialized origin, loại trường hợp không hợp lệ và so khớp với cấu hình tin cậy. Header Origin không có đường dẫn để phân quyền theo trang con.

Cho phép một origin đồng nghĩa mã được chạy trong origin đó có thể tham gia những lời gọi được cấu hình. Không thể tin riêng trang `/recovery` trên một origin rồi coi các trang khác của cùng origin là một ranh giới bảo mật độc lập.

[OWASP về custom header và CORS](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html#custom-headers-and-cors) nhấn mạnh chỉ cho phép các origin thực sự kiểm soát. Một subdomain có nội dung người dùng, cấu hình CNAME không còn quản lý hoặc mã không tin cậy cần được xem xét như một nguồn rủi ro.

Không coi `Origin: null` là “không có nguồn nên an toàn”. Nếu cần một client đặc biệt, thiết kế contract xác thực riêng thay vì mở rộng quyền cho mọi ngữ cảnh origin mờ đục.

## 9. Cấp token CSRF cho frontend khác origin

Frontend ở app không thể đọc cookie HttpOnly của recovery, và cũng không cần làm vậy. Một mô hình là:

1. API tạo hoặc xác thực phiên recovery theo bằng chứng được chấp nhận.
2. Frontend gọi endpoint lấy context qua credential include.
3. API kiểm tra phiên, origin được phép và chỉ trả dữ liệu cần cho bước hiện tại.
4. Response JSON mang token CSRF gắn với phiên đó.
5. Frontend gửi token ở custom header khi thay đổi trạng thái.
6. API xác minh token cùng các điều kiện authorization trước khi thay đổi.

Endpoint lấy context không được trả bí mật recovery cho mọi origin. Nếu một origin không tin cậy được phép đọc token CSRF cùng cookie phiên, lớp token chống giả mạo có thể mất tác dụng đối với origin đó.

Trong mô hình này, token được lấy từ response JSON của origin tin cậy, không cần mở cookie phiên cho JavaScript. Cũng không cố dùng `Access-Control-Expose-Headers` để đọc `Set-Cookie`: header này không được cung cấp cho JavaScript theo cơ chế đó.

Token cần đi theo lifecycle của phiên. Khi phiên được thay hoặc quyền được nâng sau xác minh, ứng dụng phải quản lý lại token và ngữ cảnh theo thiết kế. Không tái sử dụng token của một attempt khác chỉ vì trình duyệt vẫn đang mở cùng trang.

Frontend chỉ gắn token vào các endpoint tin cậy đã định vị. Một URL đích do người ngoài tác động có thể khiến chính mã hợp lệ gửi bí mật sai nơi.

## 10. Xử lý phía server theo contract của endpoint

Pseudocode cho endpoint browser dùng cookie recovery:

```text
if request is a CORS preflight:
    validate requested origin, route, method and header names
    return the allowed CORS contract without changing recovery state
else:
    validate actual origin according to browser endpoint policy
    validate method and content type
    resolve the recovery session
    verify CSRF token bound to this context
    authorize account, tenant, purpose and current recovery step

    atomically perform the permitted action and consume one-use rights
    return a minimal response with CORS policy for the allowed origin
```

Một client ngoài trình duyệt không trở thành hợp lệ chỉ nhờ tự đặt header Origin đúng. Credential và quyền vẫn phải được xác minh độc lập.

Ngược lại, request thiếu Origin cũng không nên mặc nhiên được chấp nhận như một ngoại lệ rộng cho endpoint dùng cookie. Nếu cần hỗ trợ một loại client không gửi header đó, phải có chính sách fallback hoặc contract riêng rõ ràng.

Nếu dùng Fetch Metadata bổ sung, nhớ rằng frontend và API khác origin vẫn có thể cùng site. Một giá trị `same-site` không thay thế allowlist origin cụ thể.

Giữ rule đồng bộ giữa gateway và backend. Proxy không được tự thêm một header cho phép quá rộng sau khi backend đã từ chối. Backend cũng không được tin origin đích bên ngoài từ header forwarding tùy ý do client gửi.

## 11. Nhìn đúng các tình huống lỗi

| Hiện tượng | Điều có thể đang xảy ra | Cách hiểu đúng |
| --- | --- | --- |
| OPTIONS bị từ chối | Origin, method hoặc header chưa thuộc contract | Không tắt CSRF hay mở mọi origin để sửa |
| POST không có cookie | Credential mode, phạm vi cookie hoặc SameSite không phù hợp | CORS response header không tự tạo cookie hợp lệ |
| Frontend báo network/CORS error | Response không được chia sẻ hoặc kết nối lỗi | Không chắc thao tác chưa đến server |
| POST trả lỗi CSRF | Token thiếu, sai phiên hoặc sai lifecycle | Không bỏ kiểm tra chỉ vì origin được allowlist |
| Browser đọc được response | CORS contract được đáp ứng | Không chứng minh hành động đã được authorization đúng |
| Request chạy bằng công cụ ngoài browser nhưng lỗi ở web | Hai client chịu cơ chế khác nhau | Không dùng kết quả ngoài browser làm bằng chứng cấu hình CORS đúng |

Khi frontend không nhận được kết quả sau một thao tác dùng quyền một lần, không tự gửi lặp vô hạn. Thao tác có thể đã hoàn tất phía server. Có thể cần API tra cứu trạng thái được bảo vệ hoặc cơ chế idempotency được thiết kế riêng; khóa idempotency không thay credential.

Tách frontend và API tạo thêm ranh giới cần quản lý. Nếu không cần cross-origin, một kiến trúc cùng origin hoặc lớp backend phục vụ frontend có thể giảm số điều kiện trình duyệt phải phối hợp. Dù chọn kiến trúc nào, quyền recovery vẫn phải hẹp, có thời hạn và được kiểm tra tại server trước mỗi thay đổi nhạy cảm.
