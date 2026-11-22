# Claims bắt buộc theo hợp đồng và claims chỉ mang tính bổ sung

## 1. Vì sao phải phân biệt claim bắt buộc và claim bổ sung?

Một **JSON Web Token (JWT)** mang tập claims do bên phát hành (*issuer*) cung cấp. Consumer nhận token cần biết claim nào phải có để xác minh và xử lý token, claim nào có thể vắng mặt, và claim nào chỉ cung cấp thêm ngữ cảnh hoặc thông tin mô tả.

Nếu hai bên không thống nhất rõ, issuer có thể bỏ qua một claim mà API cần để phân quyền; ngược lại, API có thể từ chối token hợp lệ chỉ vì thiếu một trường không thực sự cần thiết. Nguy hiểm hơn, API có thể tự điền giá trị mặc định cho claim đặc quyền bị thiếu rồi vô tình cấp quyền.

Trong JWT, **không có một danh sách claim bắt buộc chung cho mọi ứng dụng**. RFC 7519 định nghĩa các registered claims như **iss**, **sub**, **aud**, **exp**, **nbf**, **iat**, **jti**, nhưng việc claim nào bắt buộc thuộc về hồ sơ token (*token profile*), giao thức và hợp đồng giữa issuer với consumer. Một hồ sơ OAuth JWT Access Token có thể quy định tập claim bắt buộc riêng; token dùng trong một hệ thống khác có thể có yêu cầu khác.

Vì vậy, mỗi loại token cần một hợp đồng mô tả:

- Claim nào bắt buộc phải xuất hiện trong mọi token thuộc hồ sơ?
- Claim nào tùy chọn và có thể vắng mặt?
- Claim nào chỉ bắt buộc trong một ngữ cảnh hoặc thao tác cụ thể?
- Nếu claim tùy chọn xuất hiện, kiểu và giá trị của nó phải được kiểm tra thế nào?
- Consumer xử lý ra sao khi claim bị thiếu, sai kiểu, không hợp lệ hoặc không được biết?

**Bắt buộc hay bổ sung là thuộc tính của hợp đồng token và cách sử dụng, không phải thuộc tính tự động suy ra từ tên claim.**

## 2. Các mức độ yêu cầu của claim

### 2.1. Required claim — claim bắt buộc

Claim bắt buộc phải hiện diện trong mọi token thuộc hồ sơ đang xét. Nếu thiếu, token không đáp ứng hợp đồng và consumer phải từ chối theo quy tắc xác minh.

Ví dụ, một hồ sơ access token nội bộ có thể quy định:

```json
{
  "iss": "https://identity.example.org",
  "sub": "user_42",
  "aud": "https://api.orders.example.org",
  "exp": 1893456900,
  "tenant_id": "tenant_17"
}
```

Trong hồ sơ giả định này, **iss**, **sub**, **aud**, **exp** và **tenant_id** đều bắt buộc. **tenant_id** là yêu cầu riêng của API đa tenant trong ví dụ, không phải registered claim bắt buộc cho mọi JWT.

Nếu token thiếu **tenant_id**, API không được tự lấy tenant từ query parameter, header do client gửi hoặc một giá trị mặc định rồi coi như claim đã hợp lệ. Nó phải từ chối yêu cầu cần ngữ cảnh tenant hoặc thực hiện một quy trình xác định ngữ cảnh khác đã được hợp đồng cho phép.

### 2.2. Optional claim — claim tùy chọn

Claim tùy chọn có thể xuất hiện hoặc vắng mặt mà token vẫn đáp ứng hồ sơ. Khi xuất hiện, claim vẫn phải đúng kiểu, đúng định dạng và được xử lý theo hợp đồng.

Ví dụ, **display_name** có thể được dùng để hiển thị lời chào:

```json
{
  "iss": "https://identity.example.org",
  "sub": "user_42",
  "aud": "https://api.orders.example.org",
  "exp": 1893456900,
  "display_name": "An Nguyen"
}
```

Nếu **display_name** không có, API có thể hiển thị tên dự phòng hoặc tra cứu hồ sơ người dùng. Nhưng nếu claim này xuất hiện dưới dạng số trong khi hợp đồng yêu cầu chuỗi, consumer vẫn phải xử lý theo quy tắc sai schema; không được mặc định rằng “optional” có nghĩa là có thể chứa bất kỳ kiểu dữ liệu nào.

### 2.3. Conditional claim — claim bắt buộc theo điều kiện

Một claim có thể chỉ bắt buộc khi token hoặc yêu cầu thuộc một ngữ cảnh nhất định. Điều kiện phải được mô tả rõ, tránh để từng API tự suy diễn.

Ví dụ:

- **tenant_id** bắt buộc đối với access token dành cho API đa tenant.
- **device_id** bắt buộc với token được ràng buộc với thiết bị.
- **transaction_id** bắt buộc đối với token chỉ dùng cho một giao dịch cụ thể.
- **delegated_by** bắt buộc khi token được phát hành theo cơ chế ủy quyền.

Điều kiện có thể phụ thuộc loại token, audience, phương thức xác thực, grant type hoặc nghiệp vụ. Consumer phải xác định đúng hồ sơ và ngữ cảnh trước khi áp dụng quy tắc conditional.

### 2.4. Bảng so sánh

| Mức | Có thể vắng mặt? | Khi xuất hiện | Khi thiếu |
| --- | --- | --- | --- |
| Required | Không | Phải hợp lệ theo schema và ngữ nghĩa | Từ chối token theo hồ sơ |
| Optional | Có | Vẫn phải kiểm tra kiểu và giá trị | Bỏ qua, dùng nguồn khác hoặc không cung cấp tính năng phụ thuộc claim |
| Conditional | Chỉ khi điều kiện không áp dụng | Phải hợp lệ khi điều kiện yêu cầu | Từ chối ngữ cảnh/token cần claim đó |

Không nhầm **optional claim** với **unknown claim**. Optional là claim đã biết và được hợp đồng cho phép nhưng không bắt buộc. Unknown là claim mà consumer chưa có định nghĩa hoặc không hỗ trợ. Chính sách cho hai trường hợp này có thể khác nhau.

## 3. Required không đồng nghĩa với registered

RFC 7519 đăng ký tên và định nghĩa cho một số claims phổ biến:

| Claim | Ý nghĩa | Có bắt buộc trong mọi JWT không? |
| --- | --- | --- |
| **iss** | Issuer | Không |
| **sub** | Subject | Không |
| **aud** | Audience | Không |
| **exp** | Expiration time | Không |
| **nbf** | Not before | Không |
| **iat** | Issued at | Không |
| **jti** | JWT ID | Không |

Các tên trên là registered claims, nhưng **registered không có nghĩa là required**. Một ứng dụng có thể quy định **iss**, **aud** và **exp** là bắt buộc để token được chấp nhận tại API của mình. Một hồ sơ khác có thể yêu cầu thêm **sub**, **client_id** hoặc claim riêng.

Ngược lại, custom claim cũng có thể là bắt buộc. Ví dụ, **tenant_id** không phải registered claim trong RFC 7519, nhưng có thể là trường bắt buộc của mọi access token dành cho một API đa tenant.

Vì thế, hãy tra đặc tả/hồ sơ cụ thể thay vì suy luận từ việc tên claim có nằm trong registry hay không. Với JWT access token theo OAuth, RFC 9068 định nghĩa một hồ sơ riêng và tập yêu cầu riêng; không được áp dụng nguyên xi cho mọi loại JWT.

## 4. Claim bổ sung có thể mang những loại thông tin nào?

Claim bổ sung có thể giúp consumer cải thiện trải nghiệm, chọn luồng xử lý hoặc nhận ngữ cảnh đã được issuer xác nhận. Một số nhóm thường gặp:

| Nhóm | Ví dụ | Cách sử dụng phù hợp |
| --- | --- | --- |
| Thông tin hiển thị | **display_name**, **locale**, **avatar_url** | Hiển thị giao diện hoặc chọn ngôn ngữ; không dùng làm định danh/phân quyền nếu không có hợp đồng riêng |
| Ngữ cảnh nghiệp vụ | **preferred_region**, **active_store** | Chọn mặc định hoặc ngữ cảnh; đối chiếu với dữ liệu thật khi quyết định truy cập |
| Metadata vận hành | **auth_time**, **session_id**, **correlation_id** | Phục vụ luồng xác thực, theo dõi hoặc kiểm soát phiên theo đặc tả |
| Phân loại bổ sung | **customer_tier**, **account_segment** | Cá nhân hóa hoặc chọn chính sách nếu nguồn phát hành và độ tươi phù hợp |
| Tùy chọn trải nghiệm | **timezone**, **theme** | Điều chỉnh giao diện; thường không có tác động bảo mật |

Tên và ngữ nghĩa các claim tùy biến phải được định nghĩa. Không mặc định **locale**, **timezone**, **customer_tier** hay **display_name** là tên chuẩn của JWT.

Một claim có thể chỉ mang tính thông tin ở một API nhưng lại có tác động bảo mật ở API khác. Ví dụ **customer_tier** có thể chỉ dùng để chọn giao diện ở cổng khách hàng, nhưng lại ảnh hưởng hạn mức mua hàng ở dịch vụ thanh toán. Nếu dùng claim cho quyết định có rủi ro, cần đưa nó vào hợp đồng bảo mật của consumer đó: xác định issuer, tính bắt buộc theo ngữ cảnh, nguồn sự thật, thời hạn và quy tắc kiểm tra.

## 5. Phân biệt claim bổ sung với dữ liệu mặc định

### 5.1. Absent, null, empty và default là bốn trạng thái khác nhau

Khi claim không có mặt, không được tự động xem nó tương đương với **null**, chuỗi rỗng, mảng rỗng hoặc giá trị mặc định.

| Trạng thái | Ví dụ | Ý nghĩa cần quy định |
| --- | --- | --- |
| Absent | Không có khóa **display_name** | Issuer không cung cấp claim |
| Null | **display_name** có giá trị JSON null | Claim có mặt với giá trị null |
| Empty string | **display_name** là chuỗi rỗng | Claim có mặt với chuỗi rỗng |
| Empty array | **roles** là mảng rỗng | Claim có mặt với danh sách rỗng |
| Default value | **locale** có giá trị **en** | Một giá trị cụ thể được phát hành theo quy ước mặc định |

Nếu **display_name** là optional nhưng chỉ cho phép chuỗi không rỗng khi hiện diện, token có chuỗi rỗng vẫn không hợp lệ. Nếu **roles** optional nhưng mảng rỗng có ý nghĩa “không có vai trò”, schema phải cho phép và consumer phải hiểu rõ ý nghĩa đó.

### 5.2. Không tự điền giá trị mặc định cho claim bảo mật

Giả sử API yêu cầu **tenant_id**, nhưng token không có claim này. Nếu API tự điền tenant mặc định như **tenant_public**, một token thiếu ngữ cảnh có thể truy cập nhầm dữ liệu. Tương tự, không mặc định **is_admin = true**, **verified = true** hoặc **roles = ["user"]** khi claim không xuất hiện.

Giá trị mặc định chỉ phù hợp cho dữ liệu không nhạy cảm khi hợp đồng quy định rõ. Với quyết định bảo mật, thiếu thông tin cần thiết phải dẫn tới từ chối hoặc một quy trình tra cứu/ủy quyền khác được định nghĩa trước.

## 6. Khi claim optional xuất hiện, vẫn phải kiểm tra

Optional chỉ nói rằng claim có thể vắng mặt. Nó không miễn kiểm tra:

1. **Tên claim:** phải khớp tên đã được định nghĩa, không tự ánh xạ tên gần giống.
2. **Kiểu JSON:** string phải là string, number phải là number, array phải có phần tử đúng kiểu.
3. **Ràng buộc giá trị:** độ dài, miền giá trị, enum, định dạng và giới hạn số lượng.
4. **Nguồn phát hành:** issuer phải được phép khẳng định thông tin đó.
5. **Ngữ cảnh tiêu thụ:** audience và loại token phải phù hợp.
6. **Độ tươi:** giá trị có thể đã lỗi thời trước khi token hết hạn.
7. **Mục đích sử dụng:** không biến một claim hiển thị thành bằng chứng cấp quyền nếu hợp đồng không cho phép.

Ví dụ, **display_name** là optional và có kiểu string. Token sau có claim hiện diện nhưng sai kiểu:

```json
{
  "iss": "https://identity.example.org",
  "sub": "user_42",
  "aud": "https://api.orders.example.org",
  "exp": 1893456900,
  "display_name": 42
}
```

Nếu schema yêu cầu **display_name** là string, token không đáp ứng schema. Không nên bỏ qua lỗi kiểu chỉ vì claim không bắt buộc. Hồ sơ có thể cho phép bỏ qua claim không hợp lệ không ảnh hưởng bảo mật, nhưng hành vi đó phải được mô tả tường minh; mặc định an toàn là từ chối token không phù hợp schema.

## 7. Xác định required/optional theo từng loại token

Một hệ thống có thể phát hành nhiều loại token cho các mục đích khác nhau. Không nên dùng một schema chung quá rộng rồi cho mọi consumer tự suy diễn.

Ví dụ:

| Loại token | Claims bắt buộc theo hồ sơ minh họa | Claims bổ sung |
| --- | --- | --- |
| Access token cho API đơn hàng | **iss**, **sub**, **aud**, **exp**, **tenant_id** | **scope**, **jti**, **locale**, **display_name** |
| Access token máy-gọi-máy | **iss**, **sub** đại diện client, **aud**, **exp**, **client_id** | **scope**, **jti**, metadata hệ thống |
| Token cho một giao dịch | **iss**, **sub**, **aud**, **exp**, **transaction_id** | **correlation_id**, mô tả giao dịch |
| Token hiển thị thông tin đăng nhập | Theo giao thức/hồ sơ định danh cụ thể | **name**, **locale**, ảnh đại diện nếu được phép |

Đây chỉ là ví dụ thiết kế, không phải danh sách chuẩn áp dụng chung. Đặc biệt, ID token trong OpenID Connect và access token có mục đích khác nhau; consumer phải dùng đúng hồ sơ và không tùy tiện chấp nhận ID token như access token cho API.

### 7.1. Required theo token và required theo thao tác

Cần phân biệt hai tầng:

- **Required trong token profile:** claim phải có trong mọi token thuộc profile.
- **Required cho thao tác:** claim phải có khi thực hiện một hành động cụ thể.

Ví dụ, **department_id** có thể optional trong access token vì không phải API nào cũng cần. Nhưng endpoint đọc dữ liệu nhân sự có thể yêu cầu **department_id** hoặc phải tra cứu quan hệ phòng ban hiện hành. Nếu claim không có, endpoint không được tự suy luận quyền; nó có thể tra cứu nguồn có thẩm quyền hoặc từ chối.

### 7.2. Claim optional không phải cơ chế mở rộng vô hạn

Một schema có thể cho phép thêm claims để hỗ trợ tiến hóa. Tuy nhiên, consumer chỉ nên sử dụng các tên mà nó hiểu và được phép tin. Claim lạ có thể bị bỏ qua theo chính sách tương thích, nhưng không được tự động đưa vào quyết định phân quyền.

Nếu một claim mở rộng trở thành thiết yếu cho API hoặc quyết định bảo mật, hãy cập nhật hợp đồng, schema và phiên bản tương thích. Không để một trường optional âm thầm trở thành bắt buộc trong code mà không có thay đổi hợp đồng.

## 8. Ví dụ: thiết kế hợp đồng cho API đa tenant

Giả sử API đơn hàng nhận access token. Hợp đồng quy định:

| Claim | Mức yêu cầu | Kiểu | Mục đích |
| --- | --- | --- | --- |
| **iss** | Required | String | Xác định issuer được tin cậy |
| **sub** | Required | String | Định danh chủ thể trong phạm vi issuer |
| **aud** | Required | String hoặc array of strings | Giới hạn API nhận token |
| **exp** | Required | NumericDate | Giới hạn thời gian chấp nhận |
| **tenant_id** | Required | String không rỗng | Ngữ cảnh tenant của token |
| **scope** | Optional theo profile; cần cho endpoint yêu cầu scope | String theo hợp đồng | Phạm vi thao tác được cấp |
| **jti** | Optional theo profile; required nếu áp dụng kiểm soát theo từng token | String | Nhận diện JWT để theo dõi/thu hồi |
| **display_name** | Optional | String không rỗng khi hiện diện | Hiển thị tên người dùng |
| **locale** | Optional | String theo tập locale được hỗ trợ | Chọn ngôn ngữ hiển thị |

Một token tối thiểu có thể là:

```json
{
  "iss": "https://identity.example.org",
  "sub": "user_42",
  "aud": "https://api.orders.example.org",
  "exp": 1893456900,
  "tenant_id": "tenant_17"
}
```

Token mở rộng có thể thêm các claims bổ sung:

```json
{
  "iss": "https://identity.example.org",
  "sub": "user_42",
  "aud": "https://api.orders.example.org",
  "exp": 1893456900,
  "tenant_id": "tenant_17",
  "scope": "orders:read orders:create",
  "jti": "jwt_7b21",
  "display_name": "An Nguyen",
  "locale": "vi-VN"
}
```

Nếu **display_name** vắng mặt, API vẫn có thể xử lý nghiệp vụ đơn hàng. Nếu **tenant_id** vắng mặt, token không đáp ứng profile. Nếu **scope** vắng mặt, endpoint cần scope phải từ chối hoặc thực hiện cách đánh giá quyền khác đã được hợp đồng quy định. Không tự xem việc thiếu scope là “không giới hạn”.

Nếu **jti** optional trong profile nhưng một endpoint yêu cầu kiểm tra thu hồi theo từng token, endpoint đó cần **jti** hoặc cơ chế định danh phiên khác. Điều kiện này phải được quy định trước để issuer biết cần phát hành thông tin gì.

## 9. Xử lý claim thiếu hoặc không hợp lệ

Một quy trình xử lý rõ ràng giúp các API không diễn giải thiếu dữ liệu theo những cách khác nhau:

| Trạng thái claim | Xử lý theo hợp đồng |
| --- | --- |
| Required bị thiếu | Từ chối token |
| Conditional bị thiếu khi điều kiện áp dụng | Từ chối ngữ cảnh hoặc yêu cầu |
| Optional bị thiếu | Tiếp tục nếu không phụ thuộc; nếu cần chức năng phụ, tra cứu hoặc bỏ chức năng đó |
| Optional có mặt nhưng sai kiểu | Từ chối schema hoặc xử lý theo chính sách lỗi đã công bố |
| Claim có giá trị ngoài miền cho phép | Từ chối hoặc không sử dụng claim theo quy tắc rõ ràng |
| Claim lạ không được consumer hiểu | Bỏ qua nếu profile cho phép; không dùng để cấp quyền |
| Claim cần thiết nhưng dữ liệu đã cũ | Tra cứu nguồn có thẩm quyền hoặc từ chối theo chính sách |

### 9.1. Fail closed với thông tin bảo mật

Nếu một quyết định cần **tenant_id**, **scope** hoặc một khẳng định quyền cụ thể mà consumer không thể xác minh, không mặc định cho phép. Tùy tình huống, API có thể:

- Từ chối vì token không hợp lệ hoặc không đáp ứng profile.
- Từ chối quyền truy cập vì chủ thể không chứng minh được quyền.
- Trả lỗi phụ thuộc dịch vụ nếu nguồn tra cứu bắt buộc tạm thời không khả dụng.
- Yêu cầu một luồng xác thực/ủy quyền khác đã được định nghĩa.

Phân biệt lỗi token, lỗi xác thực, lỗi phân quyền và lỗi dịch vụ giúp client xử lý đúng. Không phải mọi trường hợp đều nên trả cùng một mã lỗi.

### 9.2. Không log toàn bộ token

Khi claim bắt buộc bị thiếu hoặc sai kiểu, log nên ghi loại token, issuer đã được xác minh nếu có, tên claim lỗi, mã tương quan và kết quả xử lý. Tránh ghi toàn bộ JWT hoặc các claim chứa dữ liệu cá nhân, bí mật hay thông tin nhạy cảm.

## 10. Quản lý thay đổi hợp đồng

### 10.1. Thêm một optional claim

Thêm claim tùy chọn thường dễ tương thích hơn thêm claim bắt buộc, nhưng chỉ khi consumer cũ có chính sách xử lý unknown claims phù hợp. Nếu consumer dùng schema strict với **additionalProperties: false**, token mới có thể bị từ chối dù claim mới không bắt buộc.

Trước khi phát hành, xác nhận:

1. Consumer cũ có từ chối claim lạ không?
2. Claim mới có vô tình ảnh hưởng quyết định bảo mật không?
3. Kiểu dữ liệu và ngữ nghĩa đã được tài liệu hóa chưa?
4. Claim có thể bị lộ dữ liệu hoặc làm token quá lớn không?
5. Issuer và consumer có cần triển khai đồng bộ không?

### 10.2. Chuyển optional thành required

Đây là thay đổi có thể làm token cũ không còn hợp lệ. Cần:

1. Xác định phiên bản profile/schema mới.
2. Cập nhật issuer để luôn phát hành claim mới.
3. Cập nhật consumer và kiểm thử token cũ/mới.
4. Chờ token cũ hết hạn hoặc có kế hoạch thu hồi/chuyển đổi.
5. Chỉ áp dụng quy tắc required sau thời điểm tương thích đã công bố.

Không thay đổi âm thầm hợp đồng đang được nhiều consumer sử dụng.

### 10.3. Bỏ một claim optional

Consumer có thể đã sử dụng claim optional cho hiển thị hoặc tối ưu. Trước khi ngừng phát hành, kiểm tra các consumer có phụ thuộc vào claim hay không. Nếu claim đã trở thành điều kiện nghiệp vụ, phải chuyển dependency sang hợp đồng rõ ràng hoặc nguồn dữ liệu có thẩm quyền.

### 10.4. Phiên bản schema phải được chọn từ ngữ cảnh tin cậy

Nếu có nhiều schema song song, consumer cần biết profile áp dụng theo issuer, audience, loại token hoặc cấu hình đã đăng ký. Không để một trường version chưa được xác minh tự chọn schema lỏng hơn. Sau khi xác minh token, claim phiên bản vẫn phải nằm trong tập giá trị được chấp nhận cho issuer và audience đó.

## 11. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| Registered claim thì luôn bắt buộc | Registered chỉ nói tên đã được đăng ký; required do profile quy định |
| Custom claim luôn optional | Custom claim có thể required nếu hợp đồng ứng dụng yêu cầu |
| Optional claim có thể sai kiểu | Optional chỉ được phép vắng mặt; khi hiện diện vẫn phải đúng schema |
| Thiếu claim tương đương null | Absent, null, empty và default là các trạng thái khác nhau |
| Thiếu scope nghĩa là có toàn quyền | Thiếu thông tin quyền không được biến thành quyền không giới hạn |
| Claim hiển thị không bao giờ liên quan bảo mật | Consumer khác có thể dùng cùng claim cho quyết định nhạy cảm; phải xét theo từng hợp đồng |
| Claim lạ luôn phải từ chối token | Chính sách unknown claim phụ thuộc profile; nhưng không dùng claim lạ để cấp quyền |
| Có đủ required claims là token đáng tin | Vẫn cần xác minh chữ ký, issuer, audience, thời gian và ngữ nghĩa |

## 12. Tình huống tự kiểm tra

Một access token cho API đa tenant có các claim bắt buộc **iss**, **sub**, **aud**, **exp**, **tenant_id**. **display_name** và **locale** là optional. **scope** không bắt buộc với toàn profile, nhưng endpoint đọc đơn hàng quy định phải có **orders:read**.

Token nhận được có đủ các claim bắt buộc, có **locale = "vi-VN"**, nhưng không có **display_name** và không có **scope**.

**Câu hỏi 1:** Token có đáp ứng profile không?

**Trả lời:** Có thể có, nếu các claim bắt buộc đều hợp lệ và profile cho phép thiếu **scope**. **display_name** và **locale** là optional; việc thiếu **display_name** không làm token sai.

**Câu hỏi 2:** Có thể cho phép endpoint đọc đơn hàng không?

**Trả lời:** Không theo hợp đồng endpoint đã nêu. Endpoint yêu cầu **orders:read**, nhưng token không cung cấp scope đó và không có cơ chế đánh giá quyền thay thế được quy định. Token hợp lệ ở cấp profile không đồng nghĩa mọi thao tác đều được phép.

**Câu hỏi 3:** Nếu **display_name** xuất hiện với giá trị null, API có nên xem như vắng mặt không?

**Trả lời:** Chỉ khi schema/hợp đồng cho phép null hoặc định nghĩa rõ quy tắc quy đổi. Nếu schema yêu cầu chuỗi không rỗng khi claim hiện diện, null là sai kiểu và phải được xử lý như lỗi schema.

## 13. Ghi nhớ

Hãy định nghĩa required, optional và conditional cho từng loại token, từng issuer và từng audience. Required claims phải có và hợp lệ; optional claims có thể vắng mặt nhưng vẫn phải được kiểm tra khi xuất hiện; conditional claims phải tuân theo điều kiện đã công bố. Tách rõ yêu cầu của token profile với yêu cầu riêng của từng thao tác nghiệp vụ.

Claims bổ sung có thể cải thiện trải nghiệm hoặc cung cấp ngữ cảnh, nhưng không tự trở thành bằng chứng phân quyền. Khi một quyết định cần thông tin không có trong token, consumer phải tra cứu nguồn có thẩm quyền hoặc từ chối theo chính sách. **Không biến sự thiếu vắng của claim thành quyền mặc định.**

## Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): JWT Claims Set, registered claim names và quyền quy định claims theo ứng dụng.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): thực hành xác minh token, issuer, audience và tránh nhầm lẫn loại token.
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): hồ sơ access token JWT với các yêu cầu claim cụ thể.
- [RFC 8259 — The JavaScript Object Notation (JSON) Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259): kiểu dữ liệu JSON và biểu diễn object/array.
