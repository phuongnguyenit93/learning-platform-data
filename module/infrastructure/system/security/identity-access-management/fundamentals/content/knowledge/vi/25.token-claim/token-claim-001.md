# Token là gì

## 1. Token trong quản lý danh tính và quyền truy cập

Trong IAM, **token** là một giá trị dữ liệu được một bên phát hành và được bên khác kiểm tra để phục vụ một mục đích bảo mật, chẳng hạn đại diện cho quyền gọi API hoặc truyền đạt kết quả xác thực. Token thường xuất hiện dưới dạng chuỗi mà phần mềm lưu giữ và gửi theo một giao thức xác định.

Một token chỉ có ý nghĩa trong hệ thống và quy tắc đã định nghĩa nó. Chuỗi có vẻ ngẫu nhiên, một đối tượng JSON hoặc một giá trị được Base64 hóa không tự trở thành bằng chứng đáng tin cậy. Bên nhận phải biết ai phát hành, token dành cho mình hay không, còn hiệu lực hay không và được phép sử dụng vào việc gì.

Ví dụ, một ứng dụng quản lý chi tiêu được cấp quyền đọc giao dịch của người dùng. Ứng dụng nhận access token để gọi API giao dịch theo quyền đã cấp. API không vì nhìn thấy token mà cho phép ứng dụng chuyển tiền, sửa hồ sơ hoặc đọc dữ liệu của mọi khách hàng.

Trong bài này, token được hiểu là dữ liệu bảo mật trong phần mềm. Thiết bị xác thực phần cứng đôi khi cũng được gọi là security token; mã OTP lại là một loại bằng chứng có cách sử dụng riêng. Khi thiết kế hệ thống, cần ghi rõ đang nói đến loại nào.

## 2. Vì sao hệ thống sử dụng token?

Nếu mọi API đều trực tiếp nhận mật khẩu người dùng, ứng dụng gọi API phải có khả năng tiếp cận một bí mật có phạm vi rất rộng. Việc kiểm soát ứng dụng nào được làm gì, trong bao lâu và với tài nguyên nào trở nên khó khăn.

Token giúp biểu diễn một quyền hoặc kết quả bảo mật cụ thể dưới dạng dữ liệu mà các bên đã thống nhất cách xử lý. Chẳng hạn, ứng dụng chi tiêu có thể được cấp quyền đọc giao dịch trong một khoảng thời gian, thay vì được trao quyền sử dụng mật khẩu người dùng cho mọi mục đích.

Đối với OAuth 2.0, access token là credential để truy cập tài nguyên được bảo vệ. Nó đại diện cho quyền đã được cấp cho client, với phạm vi và thời gian sử dụng; định dạng không bắt buộc phải là JWT. [RFC 6749, mục 1.4](https://www.rfc-editor.org/rfc/rfc6749.html#section-1.4)

Việc dùng token tạo điều kiện cho những quyết định thiết kế sau:

- Cấp quyền hẹp cho từng ứng dụng hoặc workload.
- Giới hạn bên nhận và thời gian sử dụng của một bằng chứng truy cập.
- Tách hệ thống phát hành quyền khỏi API thực thi nghiệp vụ.
- Theo dõi và thu hồi quyền theo vòng đời của tài khoản, client hoặc phiên.

Những lợi ích đó cần được triển khai bằng chính sách và cơ chế kiểm tra. Chỉ thay mật khẩu bằng một chuỗi tồn tại vĩnh viễn, dùng được ở mọi API, không tự tạo ra nguyên tắc ít quyền nhất.

## 3. Ai phát hành, ai giữ và ai kiểm tra token?

Trong một mô hình OAuth điển hình, có các vai trò:

| Vai trò | Trách nhiệm trong ví dụ ứng dụng chi tiêu |
| --- | --- |
| Resource owner | Người có quyền cho phép ứng dụng truy cập dữ liệu theo mô hình áp dụng |
| Client | Ứng dụng cần gọi API giao dịch |
| Authorization server | Kiểm tra điều kiện cấp quyền và phát hành access token |
| Resource server | API tiếp nhận token và thực thi kiểm soát truy cập |

Đây là các vai trò logic. Authorization server và resource server có thể nằm trong các dịch vụ khác nhau hoặc cùng một sản phẩm. Ứng dụng cũng có thể gọi API nhân danh chính nó, chẳng hạn một job đối soát định kỳ, thay vì luôn nhân danh người dùng đang đăng nhập.

Luồng dưới đây chỉ minh họa việc sử dụng access token sau một quy trình cấp quyền hợp lệ; không mô tả toàn bộ một OAuth grant:

```mermaid
sequenceDiagram
    participant C as Client
    participant A as Authorization server
    participant R as API tài nguyên
    C->>A: Yêu cầu token theo luồng được cho phép
    A-->>C: Access token với quyền có giới hạn
    C->>R: Request API kèm access token
    R->>R: Xác minh token và kiểm tra quyền nghiệp vụ
    R-->>C: Kết quả hoặc lỗi truy cập
```

Người giữ token không nhất thiết đồng nhất với chủ thể được token đại diện. Một ứng dụng có thể giữ token được cấp để truy cập tài nguyên của người dùng. Đây là lý do cần phân biệt người dùng, client và bên gọi thực tế khi thiết kế nhật ký kiểm toán.

## 4. Các loại token có mục đích khác nhau

Không nên thiết kế một tham số tên `token` rồi chấp nhận mọi loại dữ liệu bảo mật có cùng hình dạng.

| Loại | Mục đích chính | Bên nhận theo mục đích đó |
| --- | --- | --- |
| Access token | Trình bày quyền truy cập tài nguyên được bảo vệ | Resource server phù hợp |
| Refresh token | Xin access token mới theo chính sách cấp quyền | Authorization server |
| ID token trong OpenID Connect | Cung cấp thông tin về việc người dùng được xác thực | Client thực hiện đăng nhập |
| Token đặt lại mật khẩu | Cho phép hoàn tất một giao dịch khôi phục tài khoản | Dịch vụ khôi phục tài khoản |

Refresh token là một credential riêng, không dùng thay access token ở API nghiệp vụ; việc phát hành refresh token là tùy chọn. [RFC 6749, mục 1.5](https://www.rfc-editor.org/rfc/rfc6749.html#section-1.5)

Trong OpenID Connect, ID token chứa các claim liên quan đến việc xác thực người dùng và được biểu diễn bằng JWT. Vì ID token và access token có mục đích khác nhau, API không được mặc nhiên nhận ID token như credential truy cập của mình. [OpenID Connect Core, mục 2](https://openid.net/specs/openid-connect-core-1_0.html#IDToken)

Ví dụ, ứng dụng nhận ID token để xử lý kết quả đăng nhập và access token để gọi API giao dịch. Dù cả hai đều có thể trông như JWT, việc tráo chúng cho nhau vẫn có thể sai mục đích và sai audience.

Token khôi phục mật khẩu cũng không nên được dùng làm phiên đăng nhập thông thường. Thiết kế cho giao dịch khôi phục có thể yêu cầu dùng một lần, hết hạn nhanh và gắn với đúng tài khoản, khác với cách một access token được dùng cho nhiều request trong thời gian hiệu lực.

## 5. Token không đồng nghĩa với JWT

**JWT — JSON Web Token** là một cách biểu diễn claim. Các claim có thể được bảo vệ bằng chữ ký hoặc MAC qua JWS, và có thể được mã hóa qua JWE. Đọc được nội dung không chứng minh token đã được xác minh; ký và mã hóa phục vụ những mục tiêu khác nhau. [RFC 7519, mục 1 và 3](https://www.rfc-editor.org/rfc/rfc7519.html#section-1)

Hai cách biểu diễn thường gặp trong thiết kế access token là:

| Cách biểu diễn | Ví dụ khái niệm | Bên nhận tìm thông tin liên quan bằng cách nào? |
| --- | --- | --- |
| Opaque token | Một giá trị không có ý nghĩa để client tự diễn giải | Dùng cơ chế tra cứu hoặc xác minh đã thống nhất với bên phát hành |
| Token chứa dữ liệu có thể xác minh | JWT được bảo vệ phù hợp với profile sử dụng | Đọc dữ liệu và kiểm tra bằng thư viện, khóa và chính sách đã cấu hình |

Với opaque token, quyền có thể được lưu ở phía hệ thống phát hành và được API kiểm tra qua hạ tầng phù hợp. Với JWT, API có thể xác minh nhiều thông tin ngay tại chỗ nếu có khóa và cấu hình cần thiết. Những cách này vẫn cần thiết kế về thời hạn, trạng thái tài khoản và thu hồi quyền.

Client nên sử dụng access token theo hợp đồng giao thức, không tự suy đoán cấu trúc từ số dấu chấm hoặc tiền tố của chuỗi. Một thay đổi định dạng do authorization server thực hiện không nên làm client nghiệp vụ bắt đầu tự cấp hoặc tự diễn giải quyền.

Trong JWT dạng JWS thường gặp, payload được mã hóa biểu diễn bằng Base64url, không phải được giữ bí mật nhờ Base64url. Không đưa mật khẩu, khóa bí mật hoặc dữ liệu cá nhân không cần thiết vào payload chỉ vì nó đã có chữ ký.

## 6. Claim là thông tin gì bên trong mô hình token?

**Claim** là một phát biểu về một chủ thể hoặc ngữ cảnh, được biểu diễn bằng tên và giá trị. Ví dụ, bên phát hành có thể đưa ra phát biểu về chủ thể được đại diện, bên nhận dự kiến hoặc phạm vi truy cập.

Đoạn dữ liệu sau chỉ là ví dụ về thông tin logic, không phải một token hoàn chỉnh và không dùng được để xác thực:

```json
{
  "iss": "https://identity.example.test",
  "sub": "user-1842",
  "aud": "transactions-api",
  "scope": "transactions:read",
  "tenant_id": "company-a"
}
```

Trong ví dụ:

- `iss` nhận diện bên phát hành.
- `sub` nhận diện chủ thể trong phạm vi định danh tương ứng.
- `aud` chỉ bên nhận dự kiến.
- `scope` được tích hợp này dùng để biểu diễn phạm vi được cấp.
- `tenant_id` là claim do hệ thống ví dụ định nghĩa cho bối cảnh nhiều tenant.

Không phải mọi token đều phải có tất cả các trường trên. Tên claim, kiểu dữ liệu, ý nghĩa và trường bắt buộc phụ thuộc giao thức hoặc profile. Đặc biệt, `scope` và `tenant_id` trong ví dụ không phải các trường mà mọi JWT tự động sở hữu.

Đối với opaque token, client có thể không nhìn thấy các thông tin tương ứng trong chính chuỗi token. Điều đó không có nghĩa hệ thống không biết token đại diện cho ai hoặc được cấp quyền gì; thông tin có thể nằm trong bản ghi hoặc kết quả xác minh phía máy chủ.

## 7. Bearer token: giữ được token có thể đồng nghĩa sử dụng được quyền

Bearer token được sử dụng dựa trên việc bên gọi sở hữu token, không đòi hỏi chứng minh đang giữ một khóa mật mã riêng để sử dụng token đó. Vì vậy, bảo vệ token trong lưu trữ và truyền tải là yêu cầu thiết yếu. Cách gửi thông dụng cho HTTP là header `Authorization` với scheme `Bearer`. [RFC 6750, mục 1.2 và 2.1](https://www.rfc-editor.org/rfc/rfc6750.html#section-1.2)

Ví dụ request được truyền qua HTTPS tới API phù hợp:

```http
GET /v1/transactions HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN_PLACEHOLDER
Accept: application/json
```

`ACCESS_TOKEN_PLACEHOLDER` là chỗ giữ chỗ, không phải token thật. Từ `Bearer` biểu diễn cách sử dụng credential, không cho biết token là JWT hay opaque.

Nếu token thật bị lộ trong log hoặc ảnh chụp màn hình, người có được nó có thể thử gọi API trong phạm vi token được chấp nhận. Chữ ký hợp lệ không giúp phân biệt người giữ hợp pháp với người vừa đánh cắp một bearer token.

Một số thiết kế ràng buộc token với khóa của bên gửi và yêu cầu bằng chứng bổ sung. Khi đó cần triển khai đúng cơ chế tương ứng; chỉ thêm một claim chứa tên thiết bị không tự tạo ra khả năng chống dùng token bị đánh cắp.

## 8. Có token hợp lệ vẫn cần kiểm tra quyền nghiệp vụ

Một API an toàn cần xử lý hai nhóm câu hỏi liên tiếp:

1. Credential có được chấp nhận cho API và request này không?
2. Chủ thể được xác định có được thực hiện hành động trên đúng tài nguyên này không?

Ở nhóm thứ nhất, hệ thống kiểm tra cơ chế bảo vệ token, issuer, audience, thời gian và các yêu cầu của loại token. Nếu có ràng buộc bên gửi hoặc trạng thái thu hồi, hệ thống cũng phải thực thi chúng.

Ở nhóm thứ hai, hệ thống áp dụng scope, role, thuộc tính, tenant, quyền sở hữu dữ liệu và quy tắc nghiệp vụ. Một claim có giá trị hợp lệ về mặt cú pháp không thay thế quyết định phân quyền.

Ví dụ, token của người dùng A có `transactions:read`. Người dùng gọi:

```http
GET /v1/accounts/account-of-user-b/transactions HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN_OF_USER_A_PLACEHOLDER
```

API vẫn phải kiểm tra A có quyền trên tài khoản của B hay không. Nếu chỉ kiểm tra chữ ký và scope rồi trả dữ liệu, hệ thống đã bỏ qua quyền ở mức đối tượng.

Trong bối cảnh nhiều tenant, API cũng không được lấy `tenant_id` do người gọi tùy ý gửi trong header rồi coi nó có giá trị tương đương claim đã được xác minh. Việc chọn tenant cần được đối chiếu với danh tính và chính sách truy cập đáng tin cậy.

## 9. Token có vòng đời

Một token được quản lý từ khi cấp đến khi không còn được chấp nhận:

```text
Đáp ứng điều kiện cấp quyền
  -> phát hành token với mục đích và giới hạn
  -> client lưu giữ, sử dụng theo giao thức
  -> bên nhận kiểm tra ở các lần sử dụng
  -> hết hạn hoặc bị thu hồi theo chính sách
```

Hết hạn làm giới hạn thời gian sử dụng. Thu hồi xử lý tình huống cần dừng quyền trước hạn, chẳng hạn tài khoản bị khóa, client bị xâm nhập hoặc người dùng rút quyền đã cấp. Khả năng phản ứng nhanh hay chậm phụ thuộc thiết kế kiểm tra trạng thái, cache và cách phát hành token.

JWT có thể được kiểm tra chữ ký tại chỗ không có nghĩa toàn bộ hệ thống tự động không cần trạng thái. Nếu API chỉ kiểm tra chữ ký và thời gian, một thay đổi quyền ở máy chủ có thể chưa tác động ngay tới token đã phát hành. Hệ thống phải chọn cơ chế phù hợp với độ trễ thu hồi mà nghiệp vụ chấp nhận.

Khi token hết hạn, client phải đi qua quy trình được cho phép để xin token mới. Client không được chỉnh sửa trường thời gian trong một token rồi tiếp tục gửi nó. Việc có refresh token hay không và khả năng tiếp tục cấp quyền đều do chính sách của hệ thống quyết định.

Đăng xuất ở giao diện cũng cần được thiết kế rõ. Xóa dữ liệu phía ứng dụng không nhất thiết làm mọi bản sao access token đã phát hành mất hiệu lực ngay. Cần phân biệt kết thúc phiên người dùng, dừng cấp token mới và ngăn sử dụng token hiện có.

## 10. Bảo vệ token trong triển khai

Vì token có thể là credential, cách xử lý nó phải phù hợp với giá trị quyền mà nó mang theo:

| Tình huống | Cách xử lý cần thiết kế |
| --- | --- |
| Truyền giữa client và API | Dùng kênh bảo vệ và kiểm tra đúng máy chủ đích |
| Ghi log request | Che hoặc loại bỏ credential trước khi ghi log, trace và báo lỗi |
| Lưu ở ứng dụng | Chọn cơ chế theo loại client, khả năng bị đánh cắp và thời gian cần lưu |
| Đính kèm vào URL | Tránh làm token xuất hiện trong lịch sử, liên kết chia sẻ và log URL |
| Forward request sang dịch vụ khác | Chỉ chuyển credential khi thiết kế cho phép và đúng bên nhận |
| Token của workload | Quản lý quyền và vòng đời của danh tính máy, không coi là bí mật dùng chung vĩnh viễn |

Với trình duyệt, không có một vị trí lưu token phù hợp cho mọi mô hình. Thiết kế cần xét JavaScript có thể đọc gì, ảnh hưởng của XSS, cách cookie được gửi và yêu cầu chống CSRF. Với ứng dụng máy chủ hoặc native app, khả năng bảo vệ credential và vòng đời tiến trình lại khác.

Không gửi token thật cho công cụ giải mã trực tuyến để kiểm tra payload. Khi điều tra, dùng môi trường được kiểm soát, dữ liệu giả hoặc thông tin đã lược bỏ credential. Khả năng đọc một token không phải lý do để công khai nó.

## 11. Những hiểu nhầm cần tránh

| Hiểu nhầm | Cách hiểu phù hợp |
| --- | --- |
| Token luôn là JWT | Token là khái niệm rộng; JWT là một cách biểu diễn |
| Giải mã Base64 là đã xác minh token | Đọc được dữ liệu khác với xác minh tính toàn vẹn và độ tin cậy |
| Có chữ ký thì nội dung được giữ bí mật | Chữ ký không tự mã hóa payload |
| Token còn hạn thì được làm mọi việc | Cần đúng mục đích, bên nhận và quyền đối với tài nguyên |
| ID token và access token thay thế được cho nhau | Mỗi loại có bên nhận và quy tắc sử dụng riêng |
| Đổi mật khẩu luôn làm mọi token mất hiệu lực ngay | Hiệu quả phụ thuộc chính sách và cơ chế thu hồi đã triển khai |
| Token chỉ dành cho người dùng | Workload và ứng dụng cũng có thể nhận credential truy cập |

Khi đọc tài liệu của một hệ thống IAM, hãy xác định token đang phục vụ mục đích gì, ai phát hành, ai được nhận, cách xác minh, giới hạn quyền, thời hạn và cơ chế thu hồi. Những câu hỏi đó giúp nối khái niệm token với xác thực, SSO, vòng đời danh tính và nguyên tắc ít quyền nhất trong hệ thống thực tế.
