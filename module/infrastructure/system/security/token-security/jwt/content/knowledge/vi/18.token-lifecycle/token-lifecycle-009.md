# Thay đổi mật khẩu, khóa tài khoản hoặc đổi quyền khi token còn hạn

## 1. Vấn đề: JWT còn hạn vẫn có thể không còn được phép sử dụng

JSON Web Token (JWT) thường được dùng làm access token. Một JWT tự chứa có thể mang thông tin về chủ thể, audience, thời hạn và quyền tại thời điểm phát hành. Resource server có thể xác minh chữ ký và claims mà không cần hỏi authorization server ở mỗi request.

Đặc điểm đó giúp giảm độ trễ và phụ thuộc trạng thái, nhưng cũng tạo ra một giới hạn quan trọng: **JWT đã phát hành không tự thay đổi khi dữ liệu tài khoản ở máy chủ thay đổi**.

Ví dụ:

- Người dùng đổi mật khẩu nhưng access token cũ vẫn còn 20 phút mới đến `exp`.
- Quản trị viên khóa tài khoản nhưng token trên một thiết bị khác vẫn có chữ ký hợp lệ.
- Người dùng bị gỡ quyền `payments.approve`, nhưng access token đã phát hành vẫn chứa scope hoặc role cũ.

Nếu resource server chỉ kiểm tra chữ ký, `iss`, `aud` và `exp`, token có thể tiếp tục được chấp nhận cho đến khi hết hạn. Đây không phải lỗi của chữ ký JWT; đó là hệ quả của việc claims là bản chụp tại thời điểm phát hành.

Muốn trạng thái mới có hiệu lực trước khi token hết hạn, hệ thống phải có chính sách xác định sự kiện nào làm token cũ mất hiệu lực, phạm vi token bị ảnh hưởng và cách truyền trạng thái thay đổi tới mọi verifier.

## 2. JWT là bản chụp trạng thái tại thời điểm phát hành

Giả sử authorization server phát hành:

~~~json
{
  "iss": "https://identity.example.com/",
  "sub": "user-42",
  "aud": "https://api.example.com/payments",
  "iat": 1893452400,
  "exp": 1893456000,
  "jti": "access-7f3d9a",
  "scope": "payments.read payments.approve",
  "roles": ["approver"]
}
~~~

JWT này ghi nhận rằng tại thời điểm phát hành, chủ thể có các quyền được thể hiện trong token và token được cấp cho API thanh toán trong một khoảng thời gian nhất định.

Sau khi token được ký:

- Đổi mật khẩu không sửa được payload đã ký.
- Khóa tài khoản không tự thay đổi chữ ký hoặc `exp`.
- Gỡ role không tự xóa claim `roles`.
- Thu hồi phiên đăng nhập không tự làm JWT tự chứa biết rằng phiên đã bị thu hồi.

Issuer có thể phát hành token mới với claims mới, nhưng việc tạo token mới không tự động vô hiệu hóa token cũ. Verifier cần một cơ chế nhận biết trạng thái mới.

### Xác minh mật mã khác với xác minh trạng thái hiện tại

| Lớp kiểm tra | Câu hỏi |
| --- | --- |
| Chữ ký/MAC hoặc bảo vệ mật mã | Token có được phát hành bởi bên giữ khóa tin cậy và nội dung có bị sửa không? |
| Issuer, audience, token type | Token đến từ đúng nguồn, dành cho đúng nơi nhận và đúng mục đích không? |
| Thời gian (`nbf`, `exp`, chính sách `iat`) | Token đã có hiệu lực, chưa hết hạn và còn trong giới hạn tuổi không? |
| Trạng thái tài khoản/phiên | Tài khoản và phiên còn được phép hoạt động không? |
| Quyền hiện tại | Chủ thể vẫn có quyền thực hiện hành động cụ thể không? |

Một token có thể vượt qua các kiểm tra mật mã và thời gian nhưng vẫn phải bị từ chối vì tài khoản đã bị vô hiệu hóa hoặc quyền đã bị thu hồi.

## 3. Xác định chính sách theo từng sự kiện

Không phải mọi thay đổi tài khoản đều phải có cùng hành vi. Chính sách nên phân biệt thay đổi mật khẩu, khóa/vô hiệu hóa tài khoản và thay đổi quyền.

| Sự kiện | Rủi ro chính | Chính sách cần cân nhắc |
| --- | --- | --- |
| Người dùng tự đổi mật khẩu | Token trên thiết bị cũ hoặc phiên khác có thể vẫn được dùng | Giữ phiên hiện tại hay thu hồi các phiên khác; thu hồi refresh token theo chính sách |
| Quản trị viên đặt lại mật khẩu | Credential cũ có thể đã bị lộ hoặc không còn được kiểm soát | Thu hồi các phiên/refresh token hiện có và yêu cầu xác thực lại nếu chính sách yêu cầu |
| Phát hiện mật khẩu bị lộ hoặc tài khoản bị chiếm quyền | Kẻ tấn công có thể đang giữ access token và refresh token | Thu hồi khẩn cấp các phiên và credential liên quan; điều tra hoạt động bất thường |
| Khóa tài khoản tạm thời | Có thể chỉ cần chặn đăng nhập mới hoặc chặn toàn bộ hoạt động | Quy định rõ phiên hiện tại có tiếp tục được dùng hay không |
| Vô hiệu hóa tài khoản vĩnh viễn | Chủ thể không còn được phép truy cập tài nguyên | Từ chối mọi token thuộc chủ thể sau khi trạng thái vô hiệu hóa có hiệu lực |
| Gỡ quyền hoặc hạ vai trò | Token cũ có thể giữ quyền cao hơn | Thu hồi hoặc kiểm tra quyền hiện tại trước hành động nhạy cảm |
| Cấp thêm quyền | Token cũ chưa có quyền mới | Yêu cầu token mới hoặc đọc quyền hiện tại từ nguồn có thẩm quyền |

Chính sách cần được quyết định theo yêu cầu bảo mật và sản phẩm. Không nên ngầm hiểu rằng đổi mật khẩu luôn đăng xuất mọi thiết bị hoặc khóa tài khoản chỉ ảnh hưởng lần đăng nhập tiếp theo. Hành vi phải được mô tả rõ, nhất quán và kiểm thử được.

## 4. Khi người dùng thay đổi mật khẩu

### Đổi mật khẩu không tự làm access token cũ hết hạn

Giả sử người dùng đổi mật khẩu lúc 10:00. Access token đã phát hành lúc 09:50 và có `exp` lúc 10:30 vẫn chứa chữ ký và claims cũ. Nếu API chỉ kiểm tra chữ ký và `exp`, token đó có thể được chấp nhận sau 10:00.

Điều này đặc biệt quan trọng khi:

- Người dùng nghi ngờ mật khẩu cũ đã bị lộ.
- Người dùng đổi mật khẩu sau khi đăng nhập trên thiết bị công cộng.
- Quản trị viên đặt lại mật khẩu vì phát hiện hành vi đáng ngờ.
- Kẻ tấn công đã lấy được refresh token hoặc access token trước khi mật khẩu được đổi.

### Phân biệt đổi mật khẩu chủ động và đặt lại do sự cố

Một số hệ thống cho phép người dùng đổi mật khẩu trong phiên hiện tại nhưng giữ phiên trên thiết bị đó. Các phiên khác có thể bị thu hồi. Với trường hợp đặt lại mật khẩu do tài khoản bị xâm phạm, chính sách thường nghiêm ngặt hơn:

| Tình huống | Hành vi có thể chọn |
| --- | --- |
| Người dùng chủ động đổi mật khẩu và phiên hiện tại được tin cậy | Giữ phiên hiện tại, thu hồi các phiên khác hoặc yêu cầu đăng nhập lại tùy chính sách |
| Quản trị viên reset mật khẩu | Thu hồi refresh token và các phiên hiện tại; yêu cầu xác thực lại |
| Phát hiện credential bị xâm phạm | Thu hồi mọi phiên/refresh token, vô hiệu hóa access token còn hạn bằng cơ chế trạng thái và yêu cầu xác thực lại |
| Đổi mật khẩu theo yêu cầu định kỳ | Có thể chỉ cập nhật credential nếu chính sách không yêu cầu logout; cần thông báo rõ tác động lên phiên |

Đối với hệ thống nhạy cảm, nên có thao tác rõ ràng như “đăng xuất khỏi tất cả thiết bị” hoặc “thu hồi tất cả phiên”. Thao tác này cần tác động đến trạng thái phiên và refresh token, đồng thời có cách làm cho access token cũ bị từ chối trong thời gian chấp nhận được.

### Refresh token cũng cần được xử lý

Nếu chỉ chặn access token hiện tại nhưng refresh token vẫn còn hiệu lực, client có thể đổi refresh token đó lấy access token mới. Khi chính sách yêu cầu đăng xuất hoặc thu hồi sau đổi mật khẩu, cần xem xét:

- Thu hồi refresh token hoặc token family liên quan.
- Thu hồi các phiên đăng nhập theo chủ thể.
- Xoay vòng refresh token và phát hiện việc sử dụng lại token cũ nếu giao thức hỗ trợ.
- Từ chối cấp access token mới khi tài khoản đang bị khóa hoặc trạng thái credential không còn hợp lệ.

Thu hồi refresh token không tự thu hồi mọi access token đã phát hành. Cần kết hợp thời hạn access token ngắn hoặc cơ chế kiểm tra trạng thái, denylist hay introspection.

## 5. Khi tài khoản bị khóa hoặc vô hiệu hóa

Khóa tài khoản có thể mang nhiều ý nghĩa: tạm khóa do nhiều lần đăng nhập sai, khóa theo yêu cầu quản trị, đình chỉ do điều tra hoặc vô hiệu hóa vĩnh viễn. Hệ thống cần định nghĩa loại trạng thái và hành vi với token đang tồn tại.

### Vì sao token cũ vẫn có thể hoạt động?

Một access token có thể chỉ chứa `sub`, `aud`, `exp` và quyền đã cấp. Nếu resource server không kiểm tra trạng thái tài khoản, nó không biết rằng tài khoản vừa bị khóa.

Ví dụ:

1. Người dùng đăng nhập và nhận access token có thời hạn 30 phút.
2. Sau 5 phút, hệ thống phát hiện tài khoản bị xâm phạm và chuyển trạng thái sang disabled.
3. Access token vẫn có chữ ký hợp lệ và còn 25 phút.
4. API không kiểm tra trạng thái tài khoản nên vẫn chấp nhận token.

Để chặn token sau khi tài khoản bị vô hiệu hóa, trạng thái phải được kiểm tra tại điểm ra quyết định hoặc được phản ánh vào cơ chế thu hồi mà verifier có thể truy cập.

### Phân biệt khóa đăng nhập mới với khóa mọi truy cập

Chính sách “không cho đăng nhập mới” chỉ ngăn việc tạo phiên hoặc phát hành token mới. Nó không nhất thiết chặn access token đã cấp.

Chính sách “vô hiệu hóa tài khoản” thường cần chặn cả:

- Đăng nhập mới.
- Refresh token và cấp access token mới.
- Access token hiện có.
- Phiên hoặc credential khác thuộc chủ thể.

Nếu chỉ thực hiện hai bước đầu, token tự chứa cũ vẫn có thể hoạt động cho đến khi hết hạn hoặc bị verifier từ chối bằng cơ chế khác.

## 6. Khi quyền hoặc vai trò thay đổi

Access token thường mang snapshot quyền tại thời điểm phát hành, ví dụ `scope`, `roles`, `groups` hoặc claim riêng của ứng dụng.

Giả sử token chứa:

~~~json
{
  "sub": "user-42",
  "scope": "reports.read reports.export",
  "roles": ["analyst", "report-exporter"],
  "exp": 1893456000
}
~~~

Quản trị viên gỡ quyền `reports.export` lúc 10:00. Token cũ vẫn chứa quyền đó. Nếu API chỉ dựa trên scope/role trong JWT, người dùng có thể tiếp tục export báo cáo cho đến khi token hết hạn.

### Thu hồi quyền và cấp thêm quyền có hai hướng tác động

| Thay đổi | Rủi ro nếu dùng claims snapshot | Cách xử lý |
| --- | --- | --- |
| Gỡ quyền | Token cũ có thể tiếp tục cấp quyền đã bị gỡ | Kiểm tra quyền hiện tại, tăng authorization version hoặc thu hồi token cũ |
| Hạ role | Token cũ có thể giữ role cao | Kiểm tra trạng thái role mới trước hành động nhạy cảm |
| Chuyển tenant/phòng ban | Token cũ có thể còn định danh phạm vi cũ | Ràng buộc tenant/resource theo trạng thái hiện tại |
| Cấp thêm quyền | Token cũ chưa có quyền mới | Cấp token mới hoặc lấy quyền hiện tại từ nguồn có thẩm quyền |
| Tạm dừng quyền | Token cũ có thể không biết trạng thái tạm dừng | Kiểm tra policy hiện tại tại thời điểm thao tác |

Với quyền bị thu hồi, mục tiêu thường là ngăn quyền cũ được sử dụng càng sớm càng tốt. Với quyền mới được cấp, việc access token cũ chưa có quyền mới thường chỉ gây từ chối tạm thời; client có thể lấy token mới sau khi được phép.

### Không phải mọi quyền đều nên nằm hoàn toàn trong JWT

Claims trong JWT phù hợp với quyền tương đối ổn định và có thể chấp nhận độ trễ cập nhật. Với quyền có thể thay đổi thường xuyên hoặc thao tác có rủi ro cao, resource server nên tham chiếu authorization service hoặc dữ liệu quyền hiện tại.

Một mô hình kết hợp:

- JWT xác thực chủ thể và mang các quyền cơ bản.
- Resource server kiểm tra trạng thái tài khoản/phiên khi cần.
- Policy engine hoặc authorization service quyết định quyền nhạy cảm dựa trên dữ liệu hiện tại.
- Các thay đổi quyền phát sự kiện để vô hiệu hóa cache hoặc phiên bản quyền cũ.

## 7. Các cơ chế làm token cũ mất hiệu lực

Không có một cơ chế duy nhất phù hợp cho mọi kiến trúc. Những lựa chọn phổ biến gồm:

| Cơ chế | Cách hoạt động | Phạm vi thu hồi | Đặc điểm |
| --- | --- | --- | --- |
| Short-lived access token | Đặt `exp` gần hơn và chờ token tự hết hạn | Token theo thời hạn | Đơn giản, nhưng không thu hồi tức thời |
| Denylist theo `jti` | Lưu ID token bị thu hồi; verifier tra cứu khi nhận token | Một token cụ thể | Chính xác, cần trạng thái và lưu đủ lâu |
| Token/session version | Token mang version; verifier so với version hiện tại | Có thể là mọi token của tài khoản hoặc phiên | Thu hồi theo nhóm, cần kiểm tra trạng thái hiện tại |
| `tokens_valid_after` / cutoff theo `iat` | Từ chối token phát hành trước một mốc | Token trước mốc của chủ thể | Dễ hiểu, nhạy với độ chính xác thời gian |
| Introspection/status check | Verifier hỏi authorization server hoặc dịch vụ trạng thái | Theo trạng thái do server trả về | Trạng thái tập trung, tăng độ trễ/phụ thuộc mạng |
| Session store | Kiểm tra phiên còn active hay đã bị thu hồi | Một phiên hoặc nhóm phiên | Phù hợp khi cần logout/disable theo phiên |
| Authorization check hiện tại | Đọc role/permission mới trước hành động | Một quyền hoặc tài nguyên | Phù hợp với thay đổi quyền nhanh |
| Signing-key rotation | Ngừng tin khóa đã ký token | Mọi token ký bằng khóa đó | Phạm vi rộng, dành cho vòng đời khóa hoặc sự cố khẩn cấp |

Các cơ chế có thể kết hợp. Ví dụ, access token ngắn hạn cộng refresh token rotation giảm cửa sổ rủi ro; session version hoặc introspection giúp thu hồi sớm; denylist theo `jti` hỗ trợ thu hồi một token cụ thể.

## 8. Denylist theo `jti`: thu hồi một token cụ thể

Nếu JWT có claim `jti`, hệ thống có thể ghi nhận token bị thu hồi bằng định danh này. Khi verifier nhận token:

1. Xác minh chữ ký và các claims cơ bản.
2. Lấy `iss` và `jti` từ claims đã xác minh.
3. Tra cứu khóa `(iss, jti)` trong denylist.
4. Nếu có entry còn hiệu lực, từ chối token.
5. Nếu không có entry, tiếp tục kiểm tra trạng thái và quyền.

Ví dụ bản ghi:

~~~text
revoked_tokens:
    key: (issuer, jti)
    revoked_at: 1893452700
    expires_at: token_exp + maximum_verifier_leeway
~~~

Trong hệ thống đa issuer, dùng `(iss, jti)` giúp định danh token trong namespace của issuer đã xác minh. Không dùng `jti` lấy từ payload chưa xác minh làm khóa quyết định.

Entry denylist thường cần tồn tại ít nhất đến khi token không còn được chấp nhận, bao gồm leeway tối đa mà verifier áp dụng. Nếu xóa entry quá sớm, token đã thu hồi có thể được chấp nhận lại trong phần thời gian còn lại. Nếu token không có `exp`, cần chính sách thời hạn hoặc giới hạn chấp nhận khác.

Denylist cung cấp khả năng thu hồi một token cụ thể, nhưng verifier phải truy cập trạng thái dùng chung. Nếu kho denylist không khả dụng, chính sách phải xác định fail closed hay hành vi dự phòng nào được phép. Với hành động nhạy cảm, âm thầm bỏ qua denylist có thể làm vô hiệu hóa mục tiêu thu hồi.

## 9. Token version hoặc session version

Một cách thu hồi theo nhóm là gắn phiên bản vào trạng thái tài khoản hoặc phiên.

Ví dụ trạng thái phía máy chủ:

~~~json
{
  "user_id": "user-42",
  "account_status": "active",
  "token_version": 8
}
~~~

Token được phát hành mang claim riêng:

~~~json
{
  "sub": "user-42",
  "ver": 7,
  "iat": 1893452400,
  "exp": 1893456000
}
~~~

Verifier so sánh `ver` trong token với `token_version` hiện tại:

~~~text
token.ver == account.token_version
~~~

Nếu quản trị viên tăng version từ 7 lên 8 sau khi đổi mật khẩu hoặc thu hồi tất cả phiên, mọi token có version 7 bị từ chối khi verifier đọc được version mới.

| Loại version | Tác động |
| --- | --- |
| Account token version | Có thể vô hiệu hóa tất cả token của một chủ thể |
| Session version/identifier | Có thể vô hiệu hóa một phiên hoặc một nhóm token thuộc phiên |
| Authorization version | Có thể vô hiệu hóa token chứa snapshot quyền cũ |
| Credential version | Có thể liên kết với thay đổi mật khẩu hoặc credential theo chính sách |

Không nhất thiết phải dùng nhiều số version riêng. Hệ thống có thể dùng một version tổng thể hoặc các version theo mục đích, miễn là phạm vi và cách tăng version được định nghĩa rõ. Verifier vẫn phải đọc version hiện tại hoặc dùng cache có cơ chế invalidation; cache quá lâu làm token cũ tiếp tục được chấp nhận.

Claim version là claim riêng của ứng dụng, không phải registered claim chuẩn của JWT.

## 10. Thu hồi theo mốc `tokens_valid_after`

Một lựa chọn khác là lưu mốc thời gian mà từ đó token mới được phép sử dụng:

~~~text
account.tokens_valid_after = 1893452700
~~~

Verifier từ chối token nếu:

~~~text
token.iat < account.tokens_valid_after
~~~

Khi người dùng đổi mật khẩu hoặc bị khóa, hệ thống cập nhật mốc này. Những token được phát hành trước mốc sẽ bị từ chối sau khi verifier nhận được trạng thái mới.

Các giới hạn cần xử lý:

- `iat` là NumericDate có thể có độ chính xác đến giây; hai token phát hành gần nhau có thể có cùng timestamp.
- Nếu cutoff được đặt cùng giây với một token cần thu hồi, phép so sánh `<` có thể vẫn cho token đó đi qua.
- Đồng hồ issuer và verifier lệch có thể làm sai quyết định.
- Token thiếu `iat` không thể kiểm tra theo cơ chế này và phải được xử lý theo profile.
- Verifier cần lấy cutoff hiện tại hoặc dùng cache có giới hạn độ trễ.

Không nên giải quyết vấn đề độ phân giải bằng cách cộng/trừ tùy tiện một giây mà không đánh giá tác động đến token mới. Nếu cần thu hồi chính xác, token/session version thường dễ diễn đạt hơn.

## 11. Introspection và kiểm tra trạng thái tập trung

OAuth 2.0 Token Introspection được định nghĩa trong [RFC 7662](https://www.rfc-editor.org/rfc/rfc7662). Resource server gửi token đến authorization server hoặc introspection endpoint được tin cậy để hỏi token còn active hay không và nhận metadata liên quan.

Ví dụ response rút gọn:

~~~json
{
  "active": true,
  "scope": "payments.read",
  "client_id": "payments-client",
  "sub": "user-42",
  "iss": "https://identity.example.com/",
  "exp": 1893456000
}
~~~

Khi tài khoản bị khóa hoặc token bị thu hồi, authorization server có thể trả `active: false` theo chính sách và trạng thái hiện tại.

Ưu điểm:

- Có thể phản ánh trạng thái thu hồi tập trung.
- Có thể trả về scope/metadata hiện tại theo chính sách.
- Resource server không phải tự duy trì toàn bộ trạng thái token.

Đánh đổi:

- Tạo thêm request mạng và độ trễ cho đường xử lý.
- Authorization server/introspection endpoint trở thành dependency quan trọng.
- Cache kết quả introspection làm tăng độ trễ thu hồi.
- Cần bảo vệ endpoint, xác thực resource server và giới hạn quyền truy vấn.
- Khi endpoint lỗi, cần chính sách fail closed hoặc fallback rõ ràng.

Introspection không tự động xuất hiện chỉ vì token là JWT. Kiến trúc phải chủ động triển khai và resource server phải sử dụng kết quả introspection theo hợp đồng.

## 12. Kiểm tra trạng thái tài khoản và quyền hiện tại

Với các thao tác nhạy cảm, resource server có thể kiểm tra trạng thái tài khoản hoặc authorization service ngay trước khi thực hiện hành động.

~~~text
claims = verifyJwt(token)
account = accountDirectory.getCurrent(claims.sub)

if account.status != "active":
    reject("account is disabled")

if not authorizationService.isAllowed(
    subject = claims.sub,
    action = "payments.approve",
    resource = paymentId
):
    reject("permission no longer granted")

processApproval()
~~~

Đây là giả mã minh họa. Trong hệ thống thực tế, cần bảo đảm truy vấn trạng thái dùng nguồn dữ liệu có thẩm quyền, xử lý lỗi và tránh race condition giữa kiểm tra quyền với thời điểm ghi nhận hành động.

Một request có thể được xác minh lúc 10:00:00 nhưng quyền bị thu hồi lúc 10:00:01 trước khi thao tác thanh toán được commit. Nếu nghiệp vụ yêu cầu quyền còn hiệu lực tại thời điểm commit, chỉ kiểm tra lúc đầu request là chưa đủ. Với giao dịch quan trọng, có thể cần kiểm tra authorization trong cùng transaction hoặc sát thời điểm commit, dùng version trạng thái để phát hiện thay đổi đồng thời và ghi audit về quyết định đã sử dụng.

## 13. Access token và refresh token khi trạng thái thay đổi

Access token được gửi đến resource server để truy cập tài nguyên; refresh token được gửi đến authorization server để xin access token mới. Khi đổi mật khẩu, khóa tài khoản hoặc đổi quyền, cần xem xét cả hai loại credential.

| Sự kiện | Access token hiện có | Refresh token |
| --- | --- | --- |
| Đổi mật khẩu theo chính sách giữ phiên hiện tại | Có thể tiếp tục đến `exp` hoặc theo chính sách phiên | Có thể giữ phiên hiện tại, thu hồi các phiên khác |
| Reset mật khẩu bởi quản trị viên | Nên có cơ chế từ chối token cũ nếu reset do sự cố hoặc chính sách yêu cầu | Thu hồi các refresh token/phiên liên quan |
| Tài khoản bị khóa | Từ chối theo trạng thái tài khoản hoặc cơ chế thu hồi | Không cho refresh và thu hồi token còn hiệu lực |
| Gỡ quyền nhạy cảm | Kiểm tra quyền hiện tại hoặc thu hồi token chứa quyền cũ | Token mới phải được cấp theo quyền mới |
| Phát hiện tài khoản bị chiếm quyền | Thu hồi hoặc chặn token hiện tại trong thời gian ngắn nhất có thể | Thu hồi refresh token family và yêu cầu xác thực lại |

### Refresh token rotation và reuse detection

Khi hệ thống xoay vòng refresh token, mỗi lần sử dụng thành công sẽ cấp refresh token mới và vô hiệu hóa token cũ. Nếu token cũ bị dùng lại, authorization server có thể phát hiện dấu hiệu sao chép và thu hồi token family hoặc phiên liên quan theo chính sách.

Rotation giúp phát hiện một số trường hợp refresh token bị đánh cắp, nhưng không tự thu hồi access token đã phát hành trước đó. Access token vẫn cần expiration, introspection, denylist hoặc trạng thái phiên nếu cần thu hồi sớm.

## 14. Cache trạng thái và độ trễ thu hồi

Một cơ chế thu hồi chỉ có hiệu quả khi mọi verifier nhận được thay đổi trong khoảng thời gian chấp nhận được.

Giả sử account service tăng `token_version` từ 7 lên 8, nhưng resource server cache version trong 60 giây. Trong khoảng đó, token version 7 có thể vẫn được chấp nhận ở node chưa nhận invalidation.

Độ trễ thu hồi có thể đến từ:

- Cache TTL ở resource server.
- Độ trễ phát sự kiện và truyền sự kiện.
- Replication lag của database.
- Cache trung gian hoặc introspection response cache.
- Node offline rồi quay lại với trạng thái cũ.
- Request đang chạy trước thời điểm thu hồi.

| Mô hình | Đặc điểm | Đánh đổi |
| --- | --- | --- |
| Truy vấn trạng thái mỗi request | Nhận thay đổi nhanh nhất theo độ nhất quán của nguồn | Tăng latency và tải dependency |
| Cache ngắn hạn | Giảm tải, có giới hạn độ trễ rõ hơn | Token có thể còn được chấp nhận trong TTL |
| Event-driven invalidation | Chủ động xóa cache khi có thay đổi | Cần xử lý mất/đảo thứ tự sự kiện và node offline |
| Kết hợp cache + event + kiểm tra lại thao tác nhạy cảm | Cân bằng hiệu năng và mức bảo đảm | Phức tạp hơn, cần quan sát và kiểm thử |

Không nên nói “thu hồi tức thời” nếu kiến trúc còn cache hoặc replication bất đồng bộ. Hãy định nghĩa một mục tiêu có thể đo, ví dụ:

~~~text
Từ lúc khóa tài khoản được xác nhận
đến khi mọi resource server từ chối token cũ
<= 5 giây
~~~

Con số 5 giây chỉ là ví dụ. Hệ thống phải chọn mục tiêu theo mức độ nhạy cảm, khả năng hạ tầng và rủi ro chấp nhận được.

## 15. Khi nguồn trạng thái hoặc dịch vụ thu hồi không khả dụng

Nếu resource server không thể truy cập account service, introspection endpoint, session store hoặc denylist, nó không thể biết chắc token đã bị thu hồi hay chưa.

Các lựa chọn:

- **Fail closed:** từ chối thao tác cần kiểm tra trạng thái khi dependency không khả dụng. An toàn hơn nhưng giảm availability.
- **Fail open có giới hạn:** tiếp tục dùng trạng thái cache trong một khoảng ngắn được định nghĩa rõ. Tăng availability nhưng có thể chấp nhận token đã bị thu hồi trong khoảng đó.
- **Phân loại theo rủi ro:** cho phép đọc ít nhạy cảm bằng cache còn fresh, nhưng yêu cầu trạng thái trực tiếp cho thanh toán, thay đổi quyền hoặc dữ liệu nhạy cảm.

Không được âm thầm chuyển từ fail closed sang fail open khi có lỗi mạng. Hành vi dự phòng phải được thiết kế, ghi log, cảnh báo và kiểm thử trước.

Nếu hệ thống dùng cache trạng thái, cần đặt TTL theo mục tiêu độ trễ thu hồi, có event invalidation và cơ chế đồng bộ lại khi node kết nối trở lại, không dùng cache stale vô hạn và ghi nhận rõ quyết định dựa trên dữ liệu cache hay dữ liệu trực tiếp.

## 16. Signing-key rotation không phải cách thu hồi tài khoản thông thường

Đổi signing key có thể làm token ký bằng khóa cũ không còn xác minh được sau khi mọi verifier ngừng tin khóa đó, nhưng phạm vi ảnh hưởng rất rộng:

- Thu hồi token của nhiều người dùng cùng lúc.
- Có thể làm gián đoạn dịch vụ và các tích hợp đang hoạt động.
- Cache JWKS có thể khiến một số verifier vẫn tin khóa cũ trong một khoảng thời gian.
- Không phân biệt được tài khoản nào cần bị khóa hoặc quyền nào cần bị thu hồi.

Vì vậy, signing-key rotation phù hợp với vòng đời khóa hoặc ứng phó khi khóa ký bị xâm phạm, không phải cơ chế mặc định để xử lý một người dùng đổi mật khẩu hoặc mất một role. Với thay đổi ở phạm vi tài khoản/phiên/token, ưu tiên cơ chế có phạm vi tương ứng như session state, version, introspection hoặc denylist.

## 17. Quy trình xử lý thay đổi trạng thái tài khoản

Một luồng tổng quát có thể thực hiện như sau:

1. Xác thực và ghi nhận sự kiện thay đổi mật khẩu, trạng thái tài khoản hoặc quyền.
2. Cập nhật dữ liệu có thẩm quyền trong transaction.
3. Xác định phạm vi credential bị ảnh hưởng: một token, một phiên, mọi phiên của chủ thể hay chỉ quyền cụ thể.
4. Tăng token/session/authorization version hoặc ghi denylist/cập nhật trạng thái phiên theo chính sách.
5. Thu hồi refresh token và ngăn cấp token mới nếu tài khoản bị khóa hoặc credential bị xâm phạm.
6. Phát sự kiện invalidation đến các resource server/cache cần biết.
7. Với thao tác nhạy cảm, yêu cầu verifier kiểm tra trạng thái hiện tại hoặc introspection.
8. Ghi audit event, thời điểm hiệu lực và phạm vi thu hồi.
9. Xác nhận các verifier đã nhận thay đổi trong mục tiêu độ trễ đã định.
10. Thông báo cho người dùng về các phiên đã đăng xuất hoặc yêu cầu xác thực lại.

~~~mermaid
flowchart TD
    A[Thay đổi mật khẩu, trạng thái hoặc quyền] --> B[Cập nhật trạng thái có thẩm quyền]
    B --> C{Xác định phạm vi ảnh hưởng}
    C --> D[Thu hồi một token bằng jti]
    C --> E[Tăng session/account version]
    C --> F[Cập nhật account hoặc permission state]
    C --> G[Thu hồi refresh token và phiên]
    D --> H[Phát sự kiện invalidation]
    E --> H
    F --> H
    G --> H
    H --> I[Resource server cập nhật cache/trạng thái]
    I --> J[Request tiếp theo xác minh token và trạng thái]
    J --> K{Token, tài khoản và quyền còn hợp lệ?}
    K -- Không --> L[Từ chối]
    K -- Có --> M[Tiếp tục authorization và xử lý]
~~~

Sơ đồ mô tả một luồng khái quát. Không phải mọi sự kiện đều cần tất cả cơ chế. Gỡ một quyền có thể chỉ cần cập nhật authorization state; khóa tài khoản do bị chiếm quyền có thể cần thu hồi mọi phiên và refresh token.

## 18. Giả mã xác minh access token có kiểm tra trạng thái

Ví dụ dưới đây minh họa mô hình token version và trạng thái tài khoản:

~~~text
function authorizeRequest(rawToken, action, resource):
    claims = verifyJwtCryptographically(rawToken)

    if verification failed:
        reject("invalid token")

    if not issuerAudienceAndTimeChecksPass(claims):
        reject("token claims are invalid")

    if claims.sub is missing or claims.ver is missing:
        reject("required subject/version claim is missing")

    account = accountStateStore.getCurrent(claims.sub)

    if account is unavailable:
        rejectOrApplyExplicitFallbackPolicy("account state unavailable")

    if account.status != "active":
        reject("account is not active")

    if claims.ver != account.token_version:
        reject("token has been revoked")

    if not authorizationService.isAllowed(claims.sub, action, resource):
        reject("permission is no longer granted")

    accept()
~~~

Đây là giả mã, không phải API của thư viện cụ thể. Chỉ đọc `sub` và `ver` sau khi xác minh chữ ký và profile. `ver` là claim riêng do hệ thống định nghĩa, không phải claim chuẩn của JWT. Trạng thái tài khoản và quyền phải đến từ nguồn có thẩm quyền hoặc cache có giới hạn độ trễ rõ ràng. Không để lỗi truy vấn trạng thái tự động biến thành “được phép”.

Cần xác định cách xử lý request đang chạy khi trạng thái bị thu hồi giữa quá trình xác minh và commit.

## 19. Tình huống thực tế

### Tình huống A: Người dùng đổi mật khẩu sau khi đăng nhập trên máy công cộng

Người dùng đăng nhập trên máy công cộng và sau đó đổi mật khẩu từ thiết bị cá nhân. Nếu hệ thống chỉ đổi mật khẩu, JWT trên máy công cộng có thể vẫn còn hiệu lực và refresh token trên máy công cộng có thể tiếp tục cấp access token mới.

Chính sách phù hợp có thể là thu hồi tất cả phiên khác, thu hồi refresh token family và tăng account token version. Resource server kiểm tra version để từ chối access token cũ. Phiên trên thiết bị cá nhân có thể được giữ lại nếu người dùng xác nhận đây là phiên đáng tin cậy.

### Tình huống B: Quản trị viên khóa tài khoản nhân viên

Nhân viên rời tổ chức hoặc tài khoản bị đình chỉ. Việc chỉ chặn đăng nhập mới không đủ nếu access token cũ còn quyền truy cập API. Hệ thống cập nhật `account.status = disabled`, thu hồi refresh token và phát sự kiện đến các resource server. Các API kiểm tra trạng thái tài khoản hoặc token version trước khi thực hiện hành động nhạy cảm. Mục tiêu độ trễ thu hồi phải được đo và giám sát.

### Tình huống C: Gỡ quyền phê duyệt thanh toán

Người dùng vẫn được phép đọc báo cáo nhưng không còn quyền phê duyệt thanh toán. Nếu JWT cũ chứa `payments.approve`, API chỉ dựa trên scope cũ có thể cho phép phê duyệt.

Hệ thống cập nhật authorization policy và tăng authorization version. API kiểm tra version hoặc hỏi authorization service trước thao tác phê duyệt. Token cũ bị từ chối hoặc chỉ còn được dùng cho những hành động không bị thu hồi theo chính sách mới.

## 20. Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Cho rằng đổi mật khẩu tự làm JWT hết hạn | Token cũ vẫn được chấp nhận đến `exp` | Kết hợp thu hồi phiên/version/denylist hoặc trạng thái hiện tại |
| Chỉ thu hồi refresh token | Access token đã cấp vẫn có thể hoạt động | Kết hợp access-token revocation hoặc thời hạn ngắn |
| Chỉ chặn đăng nhập mới khi khóa tài khoản | Token cũ vẫn truy cập API | Kiểm tra account status hoặc thu hồi theo nhóm |
| Chỉ cập nhật role trong database | JWT cũ vẫn chứa role/scope trước đó | Kiểm tra quyền hiện tại hoặc authorization version |
| Coi `exp` là cơ chế thu hồi tức thời | Không thể phản ánh sự kiện trước thời điểm hết hạn | Dùng cơ chế trạng thái/thu hồi bổ sung |
| Dùng signing-key rotation để khóa một tài khoản | Ảnh hưởng mọi token dùng khóa đó | Dùng cơ chế thu hồi theo subject/session/token |
| Lưu denylist chỉ trong bộ nhớ một node | Token có thể được chấp nhận ở node khác | Dùng trạng thái chia sẻ và đồng bộ |
| Cache account/version quá lâu | Thu hồi có độ trễ vượt mục tiêu | Giảm TTL, event invalidation hoặc kiểm tra trực tiếp |
| Không thu hồi token family khi refresh token bị dùng lại | Kẻ tấn công có thể tiếp tục làm mới phiên | Áp dụng reuse detection và thu hồi theo chính sách |
| Fail open khi dịch vụ trạng thái lỗi mà không có quy định | Token đã thu hồi vẫn được chấp nhận | Định nghĩa fail behavior theo rủi ro |
| Không kiểm tra quyền tại thời điểm thao tác quan trọng | Quyền có thể bị thu hồi giữa request và commit | Kiểm tra lại trong transaction hoặc trước commit |
| Tuyên bố thu hồi tức thời nhưng có cache/event lag | Kỳ vọng vận hành không đúng thực tế | Định nghĩa và đo mục tiêu revocation latency |

## 21. Kịch bản kiểm thử

Nên kiểm thử cả sự kiện thay đổi trạng thái và hành vi của mọi resource server:

| Trường hợp | Kỳ vọng | Mục tiêu |
| --- | --- | --- |
| Token hợp lệ, tài khoản active, version khớp | Chấp nhận nếu quyền đạt | Luồng bình thường |
| Người dùng đổi mật khẩu, chính sách thu hồi mọi phiên | Access token cũ bị từ chối theo version/trạng thái | Password change revocation |
| Đổi mật khẩu nhưng giữ phiên hiện tại theo chính sách | Chỉ phiên được giữ tiếp tục hoạt động | Phạm vi thu hồi |
| Refresh token cũ được dùng sau khi bị thu hồi | Không cấp access token mới | Refresh revocation |
| Refresh token cũ bị dùng lại sau rotation | Phát hiện reuse và xử lý token family theo chính sách | Refresh reuse detection |
| Tài khoản chuyển sang disabled | Token cũ bị từ chối ở mọi verifier trong mục tiêu thời gian | Account disable |
| Tài khoản bị khóa tạm thời | Hành vi đúng với policy lock đã định nghĩa | Temporary lock |
| Role nhạy cảm bị gỡ | Hành động cần role đó bị từ chối dù token cũ còn hạn | Permission revocation |
| Quyền mới được cấp | Token cũ không tự có quyền mới; token mới hoặc policy hiện tại được dùng | Permission grant |
| `jti` nằm trong denylist | Token cụ thể bị từ chối | Per-token revocation |
| Token version cũ hơn version hiện tại | Từ chối | Version invalidation |
| `iat` trước `tokens_valid_after` | Từ chối theo cutoff policy | Time-based invalidation |
| Hai token có cùng giây `iat` quanh thời điểm cutoff | Hành vi được xác định rõ; không thu hồi nhầm token mới | Timestamp precision |
| Một node nhận event invalidation chậm | Đo và cảnh báo độ trễ; không vượt mục tiêu | Event propagation |
| Node offline rồi quay lại | Đồng bộ lại trạng thái trước khi xử lý request nhạy cảm | Stale node recovery |
| Introspection endpoint không khả dụng | Fail behavior đúng chính sách | Dependency failure |
| Denylist store không khả dụng | Không âm thầm bỏ qua kiểm tra thu hồi | Revocation store failure |
| Quyền bị thu hồi giữa lúc request đang chạy | Hành động nhạy cảm bị chặn theo chính sách commit-time | Authorization race |
| Token đã bị thu hồi nhưng `exp` còn xa | Từ chối vì trạng thái, không chờ hết hạn | Early revocation |

Nên kiểm thử trên nhiều node và nhiều vùng triển khai. Một bài test chỉ chạy ở một resource server không chứng minh rằng trạng thái thu hồi đã lan tới toàn bộ hệ thống.

## 22. Nguyên tắc cần ghi nhớ

1. JWT tự chứa là snapshot claims tại thời điểm phát hành; thay đổi mật khẩu, trạng thái tài khoản hoặc quyền không tự sửa token cũ.
2. Chữ ký hợp lệ và `exp` chưa đến không đồng nghĩa tài khoản hoặc quyền vẫn còn hợp lệ.
3. Phân biệt đổi mật khẩu chủ động, reset do quản trị viên, sự cố credential và thao tác khóa tài khoản.
4. Khi khóa tài khoản, phải quyết định rõ có chặn access token hiện có, refresh token và mọi phiên hay không.
5. Khi gỡ quyền, claims snapshot có thể còn quyền cũ; cần authorization state hiện tại hoặc cơ chế version/revocation.
6. Short-lived access token giảm cửa sổ rủi ro nhưng không thay thế thu hồi sớm.
7. Denylist theo `(iss, jti)` phù hợp với một token; token/session version phù hợp với thu hồi theo nhóm.
8. `tokens_valid_after` có thể thu hồi token cũ theo `iat`, nhưng cần xử lý độ phân giải timestamp và clock skew.
9. Introspection hoặc kiểm tra trạng thái tập trung có thể phản ánh thay đổi nhanh, đổi lại tăng latency và phụ thuộc dịch vụ.
10. Thu hồi refresh token không tự thu hồi access token đã phát hành.
11. Cache và event propagation tạo ra revocation latency; phải định nghĩa, đo và giám sát mục tiêu.
12. Signing-key rotation có phạm vi rộng, không nên dùng làm cách mặc định để xử lý một tài khoản hoặc một quyền.
13. Với thao tác nhạy cảm, kiểm tra quyền sát thời điểm thực hiện/commit để hạn chế race condition.
14. Không tuyên bố thu hồi tức thời nếu verifier vẫn có thể dùng trạng thái stale hoặc không kiểm tra trạng thái.

### Tài liệu chuẩn tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): claims, chữ ký và thời hạn của JWT.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): thực hành xác minh token và phân tách ngữ cảnh.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): endpoint và quy tắc thu hồi OAuth token.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): kiểm tra trạng thái token tại authorization server.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile JWT access token và các claim liên quan.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ refresh token, rotation và xử lý credential.

**Kết luận:** Thay đổi mật khẩu, khóa tài khoản hoặc gỡ quyền không tự làm JWT đã phát hành mất hiệu lực. Muốn trạng thái mới có hiệu lực với token còn hạn, hệ thống phải xác định phạm vi thu hồi và cung cấp cơ chế để verifier nhận biết thay đổi, chẳng hạn denylist, token/session version, introspection hoặc kiểm tra quyền hiện tại. Thời gian lan truyền trạng thái và hành vi khi dependency lỗi cần được định nghĩa, đo lường và kiểm thử.
