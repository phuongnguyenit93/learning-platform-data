# Nguyên tắc tối thiểu hóa dữ liệu nhận dạng cá nhân trong claims

## 1. Vì sao cần tối thiểu hóa dữ liệu trong JWT?

JSON Web Token (JWT) là định dạng mang claims giữa các bên. Một claim có thể mô tả chủ thể, bên phát hành, đối tượng nhận, thời gian hiệu lực, phạm vi truy cập hoặc một thuộc tính riêng của ứng dụng.

Việc đưa thông tin vào JWT rất thuận tiện: resource server có thể đọc claims để xử lý request mà không cần gọi dịch vụ hồ sơ cho mọi thuộc tính. Tuy nhiên, mỗi claim được thêm vào cũng làm tăng lượng dữ liệu được phát tán cùng token.

Một access token có thể đi qua trình duyệt, ứng dụng di động, API gateway, reverse proxy, resource server, hệ thống ghi log, công cụ giám sát và nhiều dịch vụ nội bộ. Token có thể được lưu trong bộ nhớ, cache, trace hoặc bản sao phục vụ chẩn đoán. Nếu payload chứa email, số điện thoại, địa chỉ, ngày sinh hoặc thông tin nhạy cảm, tất cả các điểm có quyền đọc token đều có khả năng tiếp cận dữ liệu đó.

**Tối thiểu hóa dữ liệu trong claims** nghĩa là chỉ đưa vào token những thông tin cần thiết cho mục đích và bên nhận cụ thể, với mức chi tiết và thời gian tồn tại phù hợp.

Mục tiêu không chỉ là làm token ngắn hơn. Cách thiết kế này giúp giảm số hệ thống có thể tiếp cận dữ liệu cá nhân, giảm tác động nếu token bị rò rỉ, hạn chế khả năng liên kết hoạt động giữa dịch vụ, tránh phát tán hồ sơ không cần thiết và giảm dữ liệu lỗi thời.

## 2. JWT có chữ ký không đồng nghĩa với payload được giữ bí mật

### JWS ký dữ liệu, không mã hóa payload

JWT thường được biểu diễn bằng JWS Compact Serialization:

~~~text
BASE64URL(header).BASE64URL(payload).signature
~~~

Base64URL chỉ là cách mã hóa biểu diễn dữ liệu để truyền tải. Bất kỳ bên nào có token đều có thể decode header và payload mà không cần khóa ký. Chữ ký giúp phát hiện nội dung bị sửa và xác minh nguồn phát hành theo khóa tin cậy; nó không che giấu claims.

Ví dụ payload sau có thể đọc được khi token là JWS:

~~~json
{
  "sub": "user-42",
  "email": "an.nguyen@example.test",
  "phone_number": "+84901234567",
  "birthdate": "1990-04-12",
  "department": "Finance"
}
~~~

Không nên giả định những giá trị này bí mật chỉ vì JWT có chữ ký hợp lệ.

### JWE cung cấp mã hóa, nhưng không thay thế tối thiểu hóa

JWE bảo vệ tính bí mật của nội dung đối với những bên không có khóa giải mã. Tuy nhiên, bên nhận được phép giải mã vẫn đọc được claims; token vẫn có thể bị lưu trữ, sao chép hoặc chuyển tiếp; dữ liệu có thể xuất hiện trong log sau khi giải mã; và khóa giải mã bị lộ có thể làm lộ nội dung của token còn lưu.

Mã hóa là một lớp bảo vệ bổ sung khi cần, không phải lý do để đưa mọi dữ liệu hồ sơ vào token. Nguyên tắc tốt vẫn là không phát tán dữ liệu mà bên nhận không cần.

## 3. Xác định mục đích trước khi thêm claim

Trước khi thêm một claim, hãy trả lời bốn câu hỏi:

1. **Mục đích:** Claim này phục vụ xác thực, định tuyến, authorization hay hiển thị hồ sơ?
2. **Bên nhận:** Chính xác resource server hoặc client nào cần giá trị này?
3. **Mức cần thiết:** Bên nhận có thể hoàn thành tác vụ bằng một định danh ít tiết lộ hơn hoặc bằng API tra cứu không?
4. **Thời gian:** Giá trị cần tồn tại trong suốt thời hạn token hay chỉ cần tại một thời điểm xử lý?

Nếu một claim chỉ hữu ích cho giao diện người dùng, nó thường không cần nằm trong access token gửi đến nhiều API. Nếu resource server chỉ cần biết người gọi có quyền đọc hóa đơn, nó thường không cần biết họ tên, ngày sinh, địa chỉ nhà hoặc số điện thoại.

| Mục đích | Dữ liệu thường cần | Dữ liệu thường không cần |
| --- | --- | --- |
| Xác thực chủ thể | Issuer, subject identifier, audience, thời gian và loại token | Địa chỉ nhà, ngày sinh, số giấy tờ |
| Authorization tại API | Scope hoặc quyền cần cho resource cụ thể; định danh subject khi cần audit | Hồ sơ cá nhân đầy đủ, ảnh đại diện, số điện thoại |
| Hiển thị hồ sơ | Các thuộc tính giao diện thực sự cần và được cho phép | Toàn bộ hồ sơ được nhúng sẵn vào mọi access token |

Một token có thể phục vụ nhiều mục đích, nhưng khi đó cần xác định rõ audience và profile. Không nên gửi một access token có đầy đủ hồ sơ người dùng đến mọi resource server chỉ để tránh một lần gọi API.

## 4. Phân biệt claim giao thức với dữ liệu hồ sơ

Một số claims có vai trò trong giao thức và kiểm tra token; một số khác là dữ liệu nhận dạng cá nhân hoặc dữ liệu nghiệp vụ.

| Claim hoặc nhóm dữ liệu | Vai trò thường gặp | Cân nhắc quyền riêng tư |
| --- | --- | --- |
| `iss` | Nhận diện issuer | Thường cần để xác minh nguồn phát hành; có thể tiết lộ hệ thống định danh đang dùng |
| `aud` | Xác định bên nhận dự kiến | Giới hạn token theo resource/client cụ thể |
| `exp`, `nbf`, `iat` | Kiểm tra thời gian | Thường cần cho vòng đời token; timestamp có thể tiết lộ thời điểm hoạt động |
| `sub` | Định danh chủ thể trong phạm vi issuer | Có thể là dữ liệu cá nhân giả danh nếu có thể liên kết về một người |
| `jti` | Định danh token cụ thể | Có thể hỗ trợ truy vết; tránh dùng lại như định danh người dùng ổn định |
| `scope` | Phạm vi truy cập | Có thể tiết lộ vai trò, quan hệ hoặc loại nghiệp vụ mà người dùng tham gia |
| `roles`, `groups` | Quyền hoặc nhóm nghiệp vụ | Có thể tiết lộ chức vụ, đơn vị, quan hệ lao động hoặc đặc điểm nhạy cảm |
| `email`, `phone_number` | Thông tin liên hệ | Là dữ liệu cá nhân trực tiếp; chỉ đưa vào khi bên nhận thực sự cần |
| `name`, `given_name`, `family_name` | Tên nhận dạng | Có thể nhận diện trực tiếp; thường chỉ cần ở client hiển thị hồ sơ |
| `birthdate`, `address` | Thông tin cá nhân | Có thể có mức độ nhạy cảm cao trong nhiều bối cảnh; tránh phát tán rộng |
| Số định danh, mã nhân viên, mã khách hàng | Định danh trong hệ thống khác | Có thể cho phép liên kết dữ liệu giữa các hệ thống |
| Thông tin sức khỏe, sinh trắc học, tài chính | Dữ liệu nhạy cảm hoặc có rủi ro cao | Không nhúng vào access token thông thường |

Không phải mọi claim ngoài bảy registered claims cốt lõi đều là dữ liệu cá nhân; ngược lại, một claim có tên kỹ thuật hoặc được mã hóa vẫn có thể là dữ liệu cá nhân nếu có thể liên kết với một người.

## 5. Tối thiểu hóa claim `sub`

`sub` thường là định danh chủ thể. Nó không nhất thiết phải là email, số điện thoại, tên đăng nhập hoặc mã nhân viên có ý nghĩa bên ngoài.

### Dùng định danh opaque thay vì thông tin nhận dạng trực tiếp

Ví dụ không nên dùng:

~~~json
{
  "sub": "an.nguyen@example.test"
}
~~~

Ví dụ ít tiết lộ hơn:

~~~json
{
  "sub": "usr_7f2c91a84d"
}
~~~

Giá trị opaque không chứa thông tin nhận dạng trực tiếp trong chuỗi. Resource server có thể dùng nó làm khóa tra cứu trong hệ thống có thẩm quyền nếu được phép.

Tuy nhiên, một định danh opaque vẫn có thể là dữ liệu cá nhân giả danh nếu tổ chức có thể liên kết nó với một cá nhân. Không được coi việc thay email bằng ID ngẫu nhiên là đã ẩn danh hoàn toàn.

### Phạm vi duy nhất của `sub`

Trong JWT, ý nghĩa của subject cần được diễn giải trong ngữ cảnh issuer. Không nên giả định một giá trị subject là định danh toàn cầu độc lập với issuer.

Khi cần định danh subject giữa nhiều issuer, hãy sử dụng cặp issuer và subject đã xác minh hoặc một cơ chế ánh xạ được kiểm soát. Không dùng email làm khóa liên kết mặc định vì email có thể thay đổi, được tái cấp hoặc khác cách chuẩn hóa giữa hệ thống.

### Pairwise subject identifier trong OpenID Connect

OpenID Connect hỗ trợ public và pairwise subject identifier. Pairwise subject giúp một OpenID Provider cấp subject khác nhau cho các client hoặc sector khác nhau, giảm khả năng các bên phối hợp dùng subject để liên kết hoạt động của cùng một người dùng.

| Client/Sector | Subject nhận được |
| --- | --- |
| Ứng dụng cửa hàng | `sub = pairwise-a81f...` |
| Cổng hỗ trợ | `sub = pairwise-5d20...` |
| Ứng dụng nhân sự | `sub = pairwise-9c73...` |

Các giá trị trên chỉ là minh họa. Việc sử dụng pairwise subject cần được hỗ trợ và cấu hình ở OpenID Provider; ứng dụng không thể tự giả định mọi issuer đều cung cấp cơ chế này.

Pairwise identifier giảm liên kết trực tiếp giữa client, nhưng không tự bảo đảm ẩn danh. Nhà cung cấp định danh vẫn có thể ánh xạ các giá trị về cùng một tài khoản, và các thuộc tính khác trong token có thể làm lộ mối liên hệ.

### Không dùng hash email như định danh ẩn danh

Hash một email thông thường không tự làm dữ liệu trở nên vô danh. Email có không gian giá trị dễ đoán; kẻ tấn công có thể tạo danh sách email phổ biến, hash chúng rồi đối chiếu.

Nếu cần pseudonymous identifier, hãy ưu tiên ID ngẫu nhiên hoặc cơ chế ánh xạ có kiểm soát. Nếu dùng HMAC có khóa bí mật, cần quản lý vòng đời khóa, phạm vi liên kết và khả năng xoay vòng. Dù dùng cách nào, định danh vẫn có thể là dữ liệu cá nhân giả danh nếu có thể tái liên kết.

## 6. Tránh đưa toàn bộ hồ sơ người dùng vào JWT

Một anti-pattern thường gặp là nhúng một object hồ sơ lớn vào access token:

~~~json
{
  "sub": "user-42",
  "user": {
    "name": "An Nguyen",
    "email": "an.nguyen@example.test",
    "phone": "+84901234567",
    "birthdate": "1990-04-12",
    "address": {
      "street": "12 Example Street",
      "city": "Ho Chi Minh City"
    },
    "employee_id": "EMP-00192",
    "department": "Finance",
    "manager": "user-18"
  },
  "roles": ["analyst"]
}
~~~

Những vấn đề của thiết kế này:

- Mọi resource server nhận token đều có thể đọc hồ sơ, dù chỉ một API cần một thuộc tính.
- Thay đổi tên, email, số điện thoại hoặc đơn vị không cập nhật token đã phát hành.
- Token lớn hơn, tăng chi phí truyền tải, parse, log và lưu trữ.
- Nhiều bản sao của cùng dữ liệu cá nhân được tạo ra ở nhiều hệ thống.
- Việc xóa hoặc sửa dữ liệu ở hồ sơ gốc không xóa các bản sao trong token đã phát hành.
- Dữ liệu hồ sơ có thể vô tình được dùng cho quyết định authorization ngoài mục đích ban đầu.

### Thiết kế thay thế

Access token chỉ mang định danh và quyền tối thiểu cần thiết:

~~~json
{
  "iss": "https://identity.example.com/",
  "sub": "usr_7f2c91a84d",
  "aud": "https://api.example.com/invoices",
  "scope": "invoices.read",
  "iat": 1893452400,
  "exp": 1893452700
}
~~~

Khi giao diện cần tên hiển thị hoặc ảnh đại diện, client gọi endpoint hồ sơ/UserInfo phù hợp với quyền được cấp. Resource server hóa đơn chỉ nhận các claims cần để xác minh và xử lý nghiệp vụ hóa đơn.

## 7. Phân biệt ID Token và Access Token

OpenID Connect ID Token và OAuth access token có mục đích khác nhau:

- **ID Token** truyền thông tin xác thực về người dùng đến OpenID Connect client.
- **Access token** cho phép client truy cập resource server theo phạm vi được cấp.

Không nên dùng ID Token như access token hoặc gửi một access token giàu thông tin hồ sơ đến mọi API.

### ID Token

ID Token có các claims cốt lõi như `iss`, `sub`, `aud`, `exp` và `iat`. Các claims hồ sơ như `name`, `email`, `picture`, `phone_number` và `address` là dữ liệu tùy chọn theo yêu cầu và quyền được cấp.

Chỉ yêu cầu và phát hành những claims mà client cần. Nếu client chỉ cần xác định người dùng đã đăng nhập, không nhất thiết phải đưa email, số điện thoại và địa chỉ vào ID Token.

### UserInfo endpoint

OpenID Connect cung cấp UserInfo endpoint để client lấy claims về người dùng theo access token và quyền tương ứng. Cách này cho phép tách thông tin hồ sơ khỏi token dùng để gọi nhiều resource server.

Ví dụ:

1. Client nhận ID Token với subject và các claims xác thực cần thiết.
2. Client cần hiển thị tên người dùng và ảnh đại diện.
3. Client gọi UserInfo endpoint với quyền phù hợp.
4. OpenID Provider chỉ trả các claims được yêu cầu và được phép.

UserInfo không tự động làm mọi dữ liệu an toàn; client vẫn phải bảo vệ response, cache và log. Nhưng nó giúp giới hạn bên nhận và thời điểm truy cập dữ liệu hồ sơ.

## 8. Tối thiểu hóa claims trong access token

Access token thường được gửi đến resource server, vì vậy cần gắn claims với đúng tài nguyên và hành động.

### Audience restriction

Đặt `aud` cho resource server hoặc nhóm resource được dự kiến nhận token. Tránh một access token có audience quá rộng chỉ vì tiện sử dụng lại.

Nếu token dành cho API hóa đơn, API báo cáo không nên chấp nhận token đó chỉ vì cùng issuer phát hành. Audience restriction giúp giới hạn nơi token được sử dụng và giảm phát tán claims đến dịch vụ không liên quan.

### Scope hẹp

Chỉ cấp các scope cần thiết cho tác vụ:

~~~json
{
  "scope": "invoices.read"
}
~~~

Tránh cấp một chuỗi scope rộng như `admin`, `all` hoặc toàn bộ quyền của người dùng nếu client chỉ cần đọc một loại tài nguyên.

Scope cũng có thể tiết lộ thông tin về công việc hoặc quan hệ của chủ thể. Chỉ đưa những scope mà resource server cần kiểm tra; tránh nhúng toàn bộ danh sách permission chi tiết nếu có thể tra cứu policy hiện tại.

### Claims theo tài nguyên

Một API có thể cần `tenant_id` hoặc `client_id` để giới hạn phạm vi. Chỉ đưa chúng vào token khi cần cho quyết định tại resource server và định nghĩa rõ ý nghĩa, nguồn phát hành, kiểu dữ liệu và audience.

Không đưa toàn bộ danh sách tenant, project, customer hoặc tài nguyên người dùng có thể truy cập vào token nếu API chỉ xử lý một tenant/resource trong request hiện tại.

## 9. Dữ liệu không nên nhúng vào access token thông thường

Các nhóm dữ liệu dưới đây thường không cần thiết trong bearer access token:

| Nhóm dữ liệu | Ví dụ | Vì sao nên tránh |
| --- | --- | --- |
| Bí mật xác thực | Mật khẩu, password hash, OTP seed, recovery code | Token không phải kho bí mật; lộ token có thể làm lộ credential hoặc giúp chiếm tài khoản |
| Khóa và secret | Private key, API key, client secret, refresh token khác | Đây là credential có quyền riêng; không nhúng vào claims |
| Thông tin liên hệ | Email cá nhân, số điện thoại, địa chỉ nhà | Thường không cần cho authorization tại API |
| Định danh chính phủ | Số căn cước, hộ chiếu, mã số thuế cá nhân | Có thể gây hậu quả lớn khi rò rỉ hoặc bị liên kết |
| Dữ liệu sức khỏe | Chẩn đoán, hồ sơ điều trị, thông tin bảo hiểm sức khỏe | Có thể thuộc nhóm dữ liệu nhạy cảm và cần kiểm soát truy cập nghiêm ngặt |
| Sinh trắc học | Ảnh khuôn mặt gốc, mẫu vân tay, voiceprint | Không nên phát tán trong token; có rủi ro khó thay đổi khi bị lộ |
| Dữ liệu tài chính | Số tài khoản, số thẻ, số dư, lịch sử giao dịch | Không cần thiết cho đa số quyết định xác thực và có thể tạo rủi ro tài chính |
| Hồ sơ nhân sự | Lương, đánh giá, tình trạng hợp đồng, quan hệ quản lý | Dễ tiết lộ thông tin lao động ngoài mục đích |
| Vị trí chi tiết | Tọa độ liên tục, lịch sử di chuyển, địa chỉ thường trú | Có thể tiết lộ thói quen và vị trí cá nhân |
| Hồ sơ đầy đủ | Toàn bộ profile, danh sách quan hệ và lịch sử hoạt động | Phát tán quá mức và khó cập nhật/thu hồi bản sao |

Nếu một nghiệp vụ thật sự cần dữ liệu thuộc các nhóm này, hãy thiết kế một luồng truy cập riêng với xác thực, authorization, audit, retention và kiểm soát bên nhận phù hợp. Không dùng việc nhúng vào JWT làm đường tắt.

## 10. Claim tùy chỉnh cần có schema và giới hạn rõ ràng

Claims tùy chỉnh như `tenant_id`, `department`, `customer_tier` hoặc `risk_level` có thể hữu ích, nhưng cần định nghĩa mục đích, bên nhận, nguồn dữ liệu, kiểu dữ liệu, mức độ nhạy cảm, thời gian giá trị còn đúng và hành vi khi claim thiếu, sai kiểu hoặc lỗi thời.

Ví dụ, `department: "Finance"` có thể tiết lộ đơn vị làm việc. Nếu API chỉ cần quyết định người dùng có thể đọc invoice hay không, một scope cụ thể có thể đủ và tiết lộ ít hơn.

### Không đưa dữ liệu suy diễn nhạy cảm vào claims

Không nên nhúng thuộc tính suy diễn như xu hướng sức khỏe, quan điểm, mức độ rủi ro cá nhân, tình trạng tài chính hoặc đặc điểm nhạy cảm chỉ vì hệ thống có thể tính ra chúng.

Nếu một thuộc tính được dùng cho quyết định tự động, cần đánh giá mục đích, cơ sở xử lý, tính chính xác, khả năng giải thích, quyền truy cập và tác động đối với cá nhân. JWT chỉ là phương tiện truyền dữ liệu, không làm cho việc thu thập hoặc sử dụng thuộc tính đó trở nên hợp lệ.

## 11. Claims có thể lỗi thời và làm tăng rủi ro riêng tư

Claims trong JWT là snapshot tại thời điểm phát hành. Nếu thông tin hồ sơ thay đổi, token cũ vẫn giữ giá trị cũ cho đến khi hết hạn hoặc bị từ chối.

Ví dụ:

- Người dùng đổi email nhưng token cũ vẫn chứa email trước đó.
- Người dùng đổi số điện thoại nhưng nhiều API tiếp tục nhìn thấy số cũ.
- Người dùng chuyển phòng ban nhưng token cũ còn chứa đơn vị trước đó.
- Người dùng rút lại quyền xử lý dữ liệu cho một mục đích, nhưng token cũ vẫn mang claim liên quan.

Điều này có thể gây hiển thị sai thông tin, gửi dữ liệu đến sai địa chỉ liên hệ, quyết định nghiệp vụ dựa trên thuộc tính không còn đúng hoặc tiếp tục xử lý dữ liệu sau khi mục đích đã thay đổi.

Đối với dữ liệu thay đổi thường xuyên, hãy cân nhắc chỉ đưa định danh ổn định vào token và truy vấn dữ liệu hiện tại từ nguồn có thẩm quyền. Nếu vẫn cần claim snapshot, đặt thời hạn token và cơ chế invalidation phù hợp với độ mới dữ liệu yêu cầu.

## 12. Tối thiểu hóa cả metadata và khả năng liên kết

Không chỉ các claim như email hay số điện thoại mới có thể ảnh hưởng quyền riêng tư.

### Định danh ổn định

Một `sub` ổn định được gửi đến nhiều resource server có thể giúp các dịch vụ liên kết request của cùng một người dùng. Điều này có thể cần thiết cho audit hoặc authorization, nhưng phải có lý do và phạm vi rõ ràng.

### `jti` và dữ liệu quan sát

`jti` giúp định danh một token cụ thể và hỗ trợ denylist hoặc audit. Không nên dùng cùng một `jti` cho nhiều token hoặc dùng `jti` như mã định danh người dùng. Tránh ghi raw token vào log; nếu cần tương quan sự kiện, dùng định danh sự kiện riêng hoặc fingerprint có kiểm soát.

### Timestamp

`iat`, `auth_time` hoặc các claim thời gian khác có thể tiết lộ thời điểm đăng nhập hay hoạt động. Chỉ phát hành khi profile hoặc bên nhận cần chúng. Không thêm timestamp chi tiết cho mục đích phân tích nếu có thể thực hiện ở hệ thống analytics được kiểm soát riêng.

### Scope và role

Danh sách quyền có thể tiết lộ vai trò, quan hệ công việc hoặc loại dịch vụ mà người dùng sử dụng. Hãy giới hạn token theo audience và chỉ mang quyền cần thiết cho resource server.

## 13. Tối thiểu hóa dữ liệu trong toàn bộ vòng đời token

Việc giảm claims khi phát hành là chưa đủ nếu các hệ thống sau đó lưu và ghi log toàn bộ token.

| Giai đoạn | Rủi ro | Biện pháp |
| --- | --- | --- |
| Thu thập dữ liệu | Thu thập nhiều thuộc tính hơn mục đích cần | Xác định mục đích và trường dữ liệu trước khi thiết kế claims |
| Phát hành token | Nhúng cả profile hoặc dữ liệu nhạy cảm | Allowlist claims theo token profile và audience |
| Truyền token | Token đi qua nhiều hệ thống | Dùng HTTPS, audience hẹp và hạn chế bên nhận |
| Xác minh token | Nhiều dịch vụ có thể đọc payload | Chỉ cấp token cho resource server cần claims đó |
| Ghi log/trace | Token hoặc payload bị ghi nguyên vẹn | Redact Authorization header, cookie và token; không log raw JWT |
| Cache | Bản sao token/claims tồn tại lâu | Giới hạn cache, retention và quyền truy cập |
| Hỗ trợ/điều tra | Token xuất hiện trong ticket, screenshot hoặc bản dump | Dùng dữ liệu đã che/mã tham chiếu thay vì token thật |
| Hết hạn/thu hồi | Bản sao đã phát hành vẫn tồn tại | TTL ngắn phù hợp, thu hồi khi cần và chính sách xóa dữ liệu ở hệ thống lưu trữ |

Không nên ghi toàn bộ payload để debug. Nếu cần chẩn đoán, ghi các trường không nhạy cảm như loại token, issuer đã cấu hình, audience, kết quả validation và mã tương quan. Ngay cả các trường này cũng cần đánh giá khả năng liên kết và retention.

## 14. Dữ liệu tối thiểu hóa không có nghĩa là bỏ qua kiểm tra authorization

Giảm claims không đồng nghĩa resource server được phép suy đoán quyền. Nếu token không mang đủ thông tin để quyết định, resource server phải lấy dữ liệu từ nguồn có thẩm quyền hoặc từ chối request.

Ví dụ:

- Nếu token chỉ có `sub`, API không được tự suy ra người dùng là admin.
- Nếu API cần kiểm tra quyền phê duyệt hiện tại, hãy truy vấn policy hiện tại hoặc dùng claim quyền có thời hạn phù hợp.
- Nếu token có `tenant_id`, vẫn phải kiểm tra tenant đó có khớp với tài nguyên được truy cập.
- Nếu token không có claim tùy chọn, không tự gán giá trị mặc định có đặc quyền.

Tối thiểu hóa cần đi cùng mô hình authorization rõ ràng: claim nào được dùng, claim nào chỉ là thông tin tham khảo và dữ liệu nào phải được kiểm tra lại.

## 15. Ví dụ thiết kế trước và sau

### Trước: token mang quá nhiều dữ liệu

~~~json
{
  "iss": "https://identity.example.com/",
  "sub": "an.nguyen@example.test",
  "aud": ["https://api.example.com/orders", "https://api.example.com/hr"],
  "email": "an.nguyen@example.test",
  "phone_number": "+84901234567",
  "birthdate": "1990-04-12",
  "address": "12 Example Street, Ho Chi Minh City",
  "employee_id": "EMP-00192",
  "department": "Finance",
  "roles": ["employee", "approver", "report-admin"],
  "permissions": ["orders.read", "orders.write", "hr.read", "payroll.read"],
  "iat": 1893452400,
  "exp": 1893456000
}
~~~

Các vấn đề:

- Email được dùng làm định danh và xuất hiện ở nhiều nơi.
- Token chứa thông tin liên hệ và ngày sinh mà API đơn hàng không cần.
- Audience bao gồm nhiều API với mục đích khác nhau.
- Danh sách role/permission tiết lộ nhiều thông tin và có thể lỗi thời.
- Token có thể bị sao chép đến các thành phần không cần hồ sơ nhân sự.

### Sau: token riêng cho API đơn hàng

~~~json
{
  "iss": "https://identity.example.com/",
  "sub": "usr_7f2c91a84d",
  "aud": "https://api.example.com/orders",
  "scope": "orders.read",
  "iat": 1893452400,
  "exp": 1893452700
}
~~~

API đơn hàng nhận một định danh giả danh, audience cụ thể và scope cần thiết. Nếu cần tên người nhận hàng, địa chỉ giao hàng hoặc dữ liệu hồ sơ, API lấy chúng từ hệ thống nghiệp vụ có quyền truy cập phù hợp cho đơn hàng đó.

Token sau không tự động phù hợp với mọi hệ thống. Nếu API cần thêm claim như tenant hoặc client, chỉ thêm khi có lý do, schema và kiểm tra rõ ràng.

## 16. Quy trình đánh giá một claim trước khi phát hành

Với từng claim dự kiến đưa vào token:

1. Ghi mục đích sử dụng và bên nhận.
2. Xác định claim có được chuẩn giao thức yêu cầu hay chỉ là dữ liệu tiện lợi.
3. Phân loại dữ liệu: định danh trực tiếp, định danh giả danh, thông tin liên hệ, dữ liệu nhạy cảm, quyền hoặc metadata.
4. Đánh giá khả năng liên kết claim với các dữ liệu khác.
5. Xác định bên nhận có thể dùng một ID opaque hoặc lookup thay thế không.
6. Giới hạn audience và scope để không phát tán claim rộng hơn.
7. Đặt thời hạn phù hợp với độ mới của dữ liệu.
8. Xác định cách claim xuất hiện trong log, cache, trace và công cụ hỗ trợ.
9. Kiểm tra claim có cần thiết ở mọi request hay chỉ một luồng hiếm.
10. Ghi lại quyết định, người phê duyệt và thời điểm cần xem xét lại.

| Câu hỏi | Nếu câu trả lời là “không” |
| --- | --- |
| Bên nhận có thực sự cần claim này không? | Loại bỏ claim |
| Mục đích đã được xác định và hợp lệ chưa? | Không phát hành cho đến khi làm rõ |
| Có thể dùng định danh ít tiết lộ hơn không? | Thay bằng định danh opaque/pairwise phù hợp |
| Claim có giới hạn đúng audience không? | Tách token/profile hoặc thu hẹp audience |
| Claim có thể thay đổi trong thời hạn token không? | Rút ngắn TTL hoặc lấy dữ liệu hiện tại từ API |
| Claim có thể xuất hiện trong log/trace không? | Bổ sung redaction và kiểm thử |
| Bên nhận có schema và quy tắc xử lý rõ không? | Không phát hành claim tùy chỉnh cho đến khi có hợp đồng |

## 17. Kiểm thử quyền riêng tư của JWT

Kiểm thử nên xác nhận không chỉ chữ ký và claims hợp lệ mà cả việc token không chứa dữ liệu vượt quá mục đích.

| Trường hợp | Kỳ vọng | Mục tiêu |
| --- | --- | --- |
| Access token cho API đơn hàng | Chỉ có claims cần cho xác minh và xử lý đơn hàng | Claim allowlist |
| Token không cần email | Không phát hành claim `email` | Loại dữ liệu hồ sơ dư thừa |
| Token không cần số điện thoại/ngày sinh/địa chỉ | Các claim này không xuất hiện | PII minimization |
| Subject identifier gửi đến nhiều client | Dùng pairwise subject nếu issuer/profile hỗ trợ và yêu cầu riêng tư cần | Giảm liên kết |
| Dùng email làm `sub` | Bị phát hiện trong review/schema policy | Tránh định danh trực tiếp |
| Hash email được mô tả là anonymous ID | Review từ chối giả định ẩn danh | Tránh re-identification |
| Access token có audience quá rộng | Từ chối phát hành hoặc kiểm thử không đạt | Audience restriction |
| Token có scope không cần thiết | Từ chối hoặc loại scope dư thừa | Least privilege |
| Log ở CDN/proxy | Không chứa token hoặc PII; trường nhạy cảm được redact | Log privacy |
| Analytics/error reporting | Không thu thập URL hoặc payload chứa credential/PII | Telemetry privacy |
| Thông tin hồ sơ thay đổi | API đọc dữ liệu mới từ nguồn hiện tại hoặc token cũ hết hiệu lực theo TTL | Claim freshness |
| Người dùng rút lại quyền xử lý dữ liệu | Token/claim và cache liên quan được xử lý theo policy | Consent/state change |
| JWE được dùng | Bên nhận và dữ liệu bên trong vẫn được tối thiểu hóa | Không phụ thuộc mã hóa để overshare |
| Token hết hạn | Bản sao cache/log được xử lý theo retention policy | Data lifecycle |
| Claim tùy chỉnh sai kiểu hoặc ngoài schema | Verifier từ chối hoặc xử lý theo profile, không suy đoán | Schema validation |

## 18. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
| --- | --- |
| JWT đã ký thì payload bí mật | JWS payload thường đọc được bằng Base64URL decode |
| Chỉ email và số điện thoại mới là dữ liệu cá nhân | ID giả danh, subject, timestamp, role và tổ hợp metadata cũng có thể liên kết với cá nhân |
| Hash email là ẩn danh | Email dễ đoán; hash không khóa có thể bị dò và đối chiếu |
| JWE cho phép nhúng toàn bộ hồ sơ | Bên nhận giải mã vẫn đọc được; dữ liệu vẫn có thể bị lưu hoặc log |
| Mọi API đều nên nhận cùng một JWT | Audience và claims nên giới hạn theo resource/purpose |
| Nhúng profile giúp giảm số lần gọi API nên luôn tốt hơn | Đổi lại là phát tán, stale data, token lớn và nhiều bản sao |
| `sub` chỉ là mã kỹ thuật nên không phải dữ liệu cá nhân | Nếu có thể liên kết về người dùng, nó vẫn có thể là dữ liệu cá nhân giả danh |
| Claim đã phát hành sẽ tự cập nhật khi hồ sơ đổi | JWT giữ nguyên nội dung đã ký cho đến khi hết hạn hoặc bị từ chối |
| Ít claims hơn nghĩa là ít kiểm tra hơn | Resource server vẫn phải xác minh token và quyết định authorization đầy đủ |

## 19. Nguyên tắc cần ghi nhớ

1. Chỉ đưa vào JWT những claims cần cho mục đích và bên nhận cụ thể.
2. JWS cung cấp tính toàn vẹn, không mã hóa payload; Base64URL không phải mã hóa bí mật.
3. JWE bảo vệ nội dung khỏi bên không có khóa giải mã nhưng không thay thế tối thiểu hóa dữ liệu.
4. Dùng `sub` opaque hoặc pairwise khi phù hợp; không dùng email/số điện thoại làm subject mặc định.
5. Pseudonymization không đồng nghĩa anonymization; ID giả danh vẫn có thể là dữ liệu cá nhân.
6. Không nhúng toàn bộ hồ sơ người dùng, dữ liệu sức khỏe, sinh trắc học, tài chính, bí mật xác thực hoặc khóa riêng vào access token thông thường.
7. Phân biệt ID Token, Access Token và UserInfo; mỗi loại có bên nhận và mục đích riêng.
8. Giới hạn audience, scope và custom claims theo resource/purpose.
9. Dữ liệu thay đổi thường xuyên nên được lấy từ nguồn hiện tại thay vì snapshot dài hạn trong JWT.
10. Redact raw JWT và claims nhạy cảm khỏi log, trace, analytics và ticket hỗ trợ.
11. Xem xét cả khả năng liên kết từ `sub`, `jti`, timestamp, scope và tổ hợp metadata.
12. Đánh giá claim theo vòng đời: thu thập, phát hành, truyền tải, sử dụng, lưu trữ, hết hạn và xóa.

### Tài liệu chuẩn tham khảo

- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): cấu trúc JWT và registered claims.
- [RFC 7516 — JSON Web Encryption](https://www.rfc-editor.org/rfc/rfc7516): bảo vệ tính bí mật của nội dung JWE.
- [OpenID Connect Core 1.0, mục 5 và 8](https://openid.net/specs/openid-connect-core-1_0.html): standard claims, scopes, UserInfo và subject identifier.
- [RFC 7643 — SCIM Core Schema](https://www.rfc-editor.org/rfc/rfc7643): ví dụ về schema thuộc tính người dùng và phân loại dữ liệu.
- [GDPR, Điều 5(1)(c)](https://eur-lex.europa.eu/eli/reg/2016/679/oj): nguyên tắc data minimisation trong phạm vi áp dụng.
- [GDPR, Điều 25](https://eur-lex.europa.eu/eli/reg/2016/679/oj): data protection by design and by default trong phạm vi áp dụng.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): hạn chế ghi log dữ liệu nhạy cảm và credential.

**Kết luận:** JWT nên mang lượng thông tin tối thiểu để đúng bên nhận thực hiện đúng mục đích. Hãy ưu tiên định danh giả danh, audience hẹp và scope tối thiểu; lấy dữ liệu hồ sơ từ endpoint có kiểm soát khi thực sự cần. Chữ ký và mã hóa bảo vệ token theo những cách khác nhau, nhưng không thay thế trách nhiệm giảm dữ liệu cá nhân được phát tán trong toàn bộ vòng đời token.
