# PII trong token

## 1. Token có thể mang cả quyền truy cập lẫn thông tin về con người

Trong IAM, token thường được dùng để biểu diễn kết quả xác thực hoặc quyền truy cập. Tuy nhiên, các claims bên trong token cũng có thể tiết lộ thông tin về người dùng: họ tên, email, số điện thoại, mã nhân viên, đơn vị công tác hoặc nhóm mà người đó tham gia.

Trong bài này, **PII — Personally Identifiable Information** được hiểu theo góc nhìn thiết kế kỹ thuật: thông tin có thể nhận diện một cá nhân hoặc liên kết với cá nhân khi kết hợp dữ liệu khác. Không chỉ những trường có tên rõ ràng như `email` mới đáng quan tâm. Một `sub` ổn định, định danh phiên hoặc mã thiết bị cũng có thể giúp nối các hoạt động về cùng một người.

Khi token đồng thời là bearer credential, việc làm lộ token có hai loại tác động. Bên nhận ngoài dự kiến có thể đọc thông tin được chứa trong token, và trong điều kiện token còn dùng được, có thể sử dụng nó để gọi tài nguyên. Giảm PII không làm bearer token trở thành dữ liệu được phép công khai.

Ví dụ, một API xem báo cáo chỉ cần biết chủ thể, phạm vi truy cập và tenant. Nếu access token còn chứa địa chỉ nhà và số định danh cá nhân, mỗi lần gọi API lại mang theo dữ liệu không phục vụ quyết định truy cập đó. Gateway, tracing và hệ thống xử lý lỗi có thể tiếp tục tạo thêm các bản sao ngoài dự kiến.

## 2. Nhận diện những claims có rủi ro riêng tư

### 2.1. Dữ liệu trực tiếp và dữ liệu có thể liên kết

| Nhóm dữ liệu | Ví dụ trong claims | Rủi ro cần xem xét |
|---|---|---|
| Định danh trực tiếp | Họ tên, email, số điện thoại, số định danh cá nhân | Nhận diện và liên hệ với một người |
| Định danh nội bộ | `sub`, mã nhân viên, mã khách hàng | Liên kết token với hồ sơ hoặc các lần truy cập |
| Thông tin tổ chức | Phòng ban, chức danh, đơn vị, người quản lý | Suy ra vị trí và quan hệ trong tổ chức |
| Thuộc tính nhân khẩu hoặc hồ sơ | Ngày sinh, địa chỉ, thông tin sức khỏe | Tiết lộ dữ liệu không liên quan tới API nhận token |
| Nhóm và quyền | `groups`, `roles`, `entitlements` | Suy ra trách nhiệm công việc hoặc quan hệ nhạy cảm |
| Thông tin phiên và thiết bị | Session ID, mã thiết bị, địa chỉ IP | Liên kết hành vi hoặc bối cảnh sử dụng |
| Metadata thời gian và token | Thời điểm xác thực, thời điểm phát hành, `jti` | Hỗ trợ nối sự kiện và nhận biết mẫu hoạt động |

Không phải mọi giá trị trong các nhóm trên đều có mức nhạy cảm như nhau. Cần đánh giá bên nhận có biết gì thêm, dữ liệu được kết hợp với nguồn nào và ai có khả năng truy cập token. Một mã nội bộ khó hiểu vẫn có thể nhận diện người dùng khi hệ thống nhận có bảng ánh xạ tương ứng.

Tên nhóm cũng có thể tiết lộ nhiều hơn quyền thao tác. Chẳng hạn, một group mang tên dự án chưa công bố hoặc chương trình hỗ trợ nhân viên có thể bộc lộ thông tin tổ chức hoặc cá nhân. Vì vậy, không nên phát hành toàn bộ membership directory vào mọi token chỉ để ứng dụng tự chọn phần cần dùng.

### 2.2. Những dữ liệu không nên biến thành claims tiện dụng

Không đưa mật khẩu, OTP, mã khôi phục, khóa bí mật hoặc refresh token vào claims của một token khác. Nếu ứng dụng cần thực hiện một thao tác thay mặt người dùng, phải dùng cơ chế ủy quyền phù hợp thay vì nhét thông tin xác thực gốc vào payload.

Trường `email_verified` chỉ diễn tả kết quả theo ngữ nghĩa của nhà cung cấp. Nó không biến email thành khóa nhận diện bất biến hoặc tự chứng minh người dùng đã được xác minh danh tính ở mọi mức bảo đảm. Tương tự, một claim tự đặt tên `trusted_user` không có ý nghĩa bảo mật nếu chưa xác định ai phát hành và điều kiện nào tạo ra giá trị đó.

## 3. Ký, mã hóa và che giấu cấu trúc là các thuộc tính khác nhau

### 3.1. JWT được ký thường vẫn đọc được payload

JWT là một định dạng biểu diễn claims; bản thân việc sử dụng JWT không bảo đảm tính bí mật. Với JWT được bảo vệ bằng JWS nhưng không mã hóa, payload thường được mã hóa dạng base64url và bên có token có thể giải mã biểu diễn đó để đọc JSON. Không cần khóa ký để đọc phần payload này.

Chữ ký hoặc MAC hỗ trợ kiểm tra tính toàn vẹn và nguồn phát hành theo cơ chế đang dùng. Chúng không ngăn bên đã nhận token đọc claims. Việc một chuỗi token dài và khó nhìn bằng mắt không phải một biện pháp bảo vệ PII.

Giải mã biểu diễn payload cũng không đồng nghĩa xác minh token. Một JSON đọc được có thể là dữ liệu do kẻ khác tạo. Hệ thống chỉ được tin claims sau khi hoàn thành kiểm tra mật mã, issuer, audience, thời hạn, loại token và những điều kiện của protocol hoặc profile tương ứng.

### 3.2. So sánh các hình thức thường gặp

| Hình thức | Bên cầm token có thể đọc claims như thế nào? | Giới hạn cần nhớ |
|---|---|---|
| JWT ký, không mã hóa | Thường có thể đọc payload trực tiếp sau khi giải mã base64url | Chữ ký không cung cấp tính bí mật |
| JWT mã hóa bằng JWE | Cần khả năng giải mã phù hợp để đọc plaintext | Bên giải mã hợp lệ vẫn thấy dữ liệu; plaintext có thể tiếp tục bị ghi log |
| Opaque hoặc reference token | Không có payload claims công khai để client tự giải mã theo dạng JWT | Chuỗi token vẫn là credential; backend hoặc introspection vẫn có thể trả dữ liệu quá mức |
| Kênh truyền dùng TLS | Bảo vệ dữ liệu trên từng kết nối được bảo vệ | Không ngăn ứng dụng, proxy kết thúc TLS hoặc log đọc dữ liệu sau khi nhận |

JWE không phải lý do để đưa mọi thông tin vào token. Cần quản lý bên nhận, khóa giải mã và cách bảo vệ dữ liệu sau giải mã. Nếu một hệ thống không cần ngày sinh, việc mã hóa ngày sinh rồi vẫn cấp quyền giải mã cho hệ thống đó chưa giải quyết việc chia sẻ dư thừa.

RFC 7519 nêu vấn đề thông tin nhạy cảm trong JWT và mô tả các biện pháp bảo vệ; việc không đưa thông tin nhạy cảm không cần thiết vào JWT là cách trực tiếp để giảm rủi ro riêng tư. [RFC 7519, mục 12 — Privacy Considerations](https://www.rfc-editor.org/rfc/rfc7519.html#section-12).

## 4. Phân biệt mục đích của từng loại token

### 4.1. ID token

Trong OIDC, ID token giúp client xác minh kết quả xác thực và nhận claims theo contract với OpenID Provider. Nó không phải một hồ sơ người dùng được phép chuyển tiếp cho mọi API. Một ứng dụng có thể cần tên hiển thị để cá nhân hóa giao diện, trong khi API nghiệp vụ phía sau không cần trường đó.

Các claims được nhận từ ID token cũng cần được sử dụng đúng phạm vi. Khi liên kết danh tính, phải xem chủ thể trong phạm vi issuer đã xác minh. Không trộn tài khoản từ các issuer khác nhau chỉ vì chúng có cùng một chuỗi `sub` hoặc email giống nhau.

### 4.2. Access token

Access token phục vụ truy cập tài nguyên. Bên phát hành cần quyết định thông tin nào resource server cần để xác thực token và đánh giá quyền. Thông tin hồ sơ chỉ nên được đưa vào khi có mục đích cụ thể tại resource server đó.

Client không nên phụ thuộc tùy tiện vào việc giải mã access token để lấy tên hoặc email cho giao diện. Token có thể là opaque, được mã hóa hoặc thay đổi contract theo hệ thống đích. Nếu chức năng cần thông tin hồ sơ, sử dụng nguồn và cơ chế được thiết kế cho mục đích đó với quyền phù hợp.

Scope thể hiện phạm vi ủy quyền theo contract, nhưng không tự định nghĩa đầy đủ danh sách claims được phép phát hành. Cấu hình phát hành claims vẫn cần được kiểm soát riêng. API cũng phải kiểm tra quyền trên đúng tài nguyên và tenant, không chỉ kiểm tra token có một scope chung.

### 4.3. Refresh token

Refresh token được client gửi tới authorization server theo luồng tương ứng để xin token mới. Không gửi nó tới các API nghiệp vụ hoặc ghi vào sự kiện phân tích. Dù refresh token có hay không có cấu trúc tự đọc được, vẫn phải bảo vệ nó như một credential theo mô hình hệ thống.

Một thiết kế không cần giải mã refresh token để xây hồ sơ người dùng. Nếu nhà cung cấp có cấu trúc nội bộ cho loại token này, client không nên tự coi cấu trúc đó là API dữ liệu được hỗ trợ.

## 5. Thiết kế claims theo bên nhận và quyết định cần thực hiện

### 5.1. Đặt câu hỏi cho từng claim

Trước khi thêm claim, cần xác định:

1. Bên nhận cụ thể nào cần claim và để thực hiện quyết định gì?
2. Có thể dùng một thuộc tính ít chi tiết hơn hoặc tra cứu theo nhu cầu không?
3. Ai ngoài bên nhận chính có thể thấy token trên đường đi và khi vận hành?
4. Giá trị cần mới tới mức nào, và điều gì xảy ra khi nó thay đổi?
5. Claim là yêu cầu của protocol, profile hay chỉ là cấu hình tùy chọn?

Giảm dữ liệu tùy chọn không có nghĩa là xóa các trường bảo mật mà profile yêu cầu. Chẳng hạn, không được bỏ kiểm tra audience hoặc thời hạn chỉ để làm token ngắn hơn. Một định danh chủ thể có thể cần cho kiểm soát quyền dù vẫn có giá trị liên kết hành vi và phải được bảo vệ.

### 5.2. Ví dụ payload quá rộng

JSON dưới đây là dữ liệu giả để phân tích thiết kế, không phải token có thể sử dụng. Các trường như `home_address` chỉ là ví dụ claims do hệ thống tự định nghĩa.

```json
{
  "iss": "https://auth.example.test",
  "sub": "employee-1042",
  "aud": "https://reports-api.example.test",
  "name": "Nguoi Dung Demo",
  "email": "demo-user@example.test",
  "phone_number": "+000-DEMO-ONLY",
  "birthdate": "1990-01-01",
  "home_address": "Dia chi gia lap",
  "department": "internal-project-team",
  "groups": ["reports-readers", "private-project-members"],
  "scope": "reports:read",
  "iat": 1800000000,
  "exp": 1800000300
}
```

Giả sử reports API chỉ cần xác định chủ thể và kiểm tra quyền đọc báo cáo trong phạm vi được phép. Khi đó, ngày sinh, địa chỉ nhà và số điện thoại không hỗ trợ quyết định này. Danh sách mọi nhóm còn tiết lộ thông tin không liên quan tới tài nguyên báo cáo.

Một payload được thu hẹp cho tình huống đó có thể như sau:

```json
{
  "iss": "https://auth.example.test",
  "sub": "subject-for-reports-82",
  "aud": "https://reports-api.example.test",
  "client_id": "report-portal",
  "scope": "reports:read",
  "iat": 1800000000,
  "exp": 1800000300,
  "jti": "token-demo-719"
}
```

Đây chỉ là minh họa payload, không bao gồm header, chữ ký hoặc toàn bộ xử lý token. Các mốc thời gian giả định chỉ phục vụ ví dụ. Việc dùng một profile cụ thể phải tuân thủ đầy đủ yêu cầu của profile đó.

`sub` trong ví dụ vẫn có thể liên kết hoạt động về cùng chủ thể. Đổi một mã nhân viên thành mã khó đọc không biến dữ liệu thành vô danh. Nếu dùng định danh theo phạm vi bên nhận, cần có cơ chế phát hành và ánh xạ được thiết kế rõ ràng; không để mỗi dịch vụ tùy ý tự đổi khóa rồi làm sai liên kết tài khoản.

`jti` là định danh token, không phải bằng chứng người gọi giữ khóa riêng hoặc tự động ngăn replay. Tương tự, audience restriction giúp resource server từ chối token không dành cho mình nhưng không mã hóa các claims hoặc ngăn mọi thành phần đã nhận token đọc payload.

### 5.3. Tra cứu theo nhu cầu cũng cần tối thiểu hóa

Nếu API thỉnh thoảng cần một thuộc tính bổ sung, có thể cân nhắc truy vấn nguồn có thẩm quyền qua cơ chế được bảo vệ. Cách này có thể giảm việc đưa thuộc tính đó vào mọi token, nhưng tạo thêm yêu cầu về phân quyền truy vấn, độ sẵn sàng, độ trễ và cache.

Không thay một token nhiều PII bằng một endpoint cho phép mọi dịch vụ đọc toàn bộ hồ sơ. Với opaque token, introspection response cũng cần giới hạn dữ liệu theo quyền và nhu cầu của resource server. Nếu response đó được ghi nguyên vẹn vào log, dữ liệu vẫn bị nhân bản dù client không tự đọc được token.

RFC 9068 mô tả các lựa chọn bảo vệ dữ liệu nhạy cảm trong JWT access token, bao gồm mã hóa, bỏ claims nhạy cảm hoặc dùng opaque access token thay cho profile JWT. Lựa chọn cần phù hợp ranh giới tin cậy của hệ thống. [RFC 9068, mục 6 — Privacy Considerations](https://www.rfc-editor.org/rfc/rfc9068.html#section-6).

## 6. Những đường rò rỉ thường bị bỏ sót

### 6.1. URL, log và công cụ hỗ trợ

Đưa bearer token vào URL có thể làm token xuất hiện trong lịch sử trình duyệt, access log hoặc công cụ xử lý URL. Trong luồng gọi API dùng bearer token, nên dùng phương thức truyền được protocol hỗ trợ phù hợp, thường là `Authorization` header qua TLS, thay vì đặt token trong query string. Header cũng cần được loại khỏi log và báo cáo lỗi; chỉ đổi vị trí truyền không đủ nếu middleware ghi mọi header.

RFC 6750 chỉ rõ rủi ro khi bearer token xuất hiện trong URL và khuyến nghị tránh đưa bearer token vào URL trang. [RFC 6750, mục 5.3 — Summary of Recommendations](https://www.rfc-editor.org/rfc/rfc6750.html#section-5.3).

Không dán token thật vào website giải mã công khai, ticket, chat nhóm, ảnh chụp màn hình hoặc tài liệu minh họa. Nếu cần đọc cấu trúc, dùng dữ liệu giả hoặc công cụ nội bộ phù hợp. Một công cụ chỉ hiển thị payload vẫn có thể là nơi tiếp nhận toàn bộ credential nếu người dùng gửi nguyên token lên đó.

### 6.2. Gateway và dịch vụ phía sau

Một luồng có thể đi qua trình duyệt, backend, gateway, API và dịch vụ phụ thuộc. Cần xác định thành phần nào nhận token gốc, thành phần nào kết thúc TLS, thành phần nào có thể ghi log và token nào thực sự dành cho dịch vụ phụ thuộc.

Không mặc định chuyển tiếp cùng một token qua mọi chặng. Nếu API phía sau cần token khác với audience hoặc phạm vi khác, phải dùng cơ chế được hệ thống hỗ trợ để có credential phù hợp. Sao chép claims tùy ý từ một token sang header nội bộ không tự duy trì được tính xác thực của claims.

Không gửi toàn bộ token tới hệ thống analytics chỉ để liên kết request. Có thể dùng correlation ID riêng và các trường sự kiện đã được lựa chọn. Nếu dùng tham chiếu token hoặc định danh giả để điều tra, cần đánh giá khả năng liên kết và bảo vệ dữ liệu đó theo mục đích sử dụng.

### 6.3. Trình duyệt và cache

Token được gửi tới trình duyệt nằm trong phạm vi quan sát của client và các thành phần có quyền truy cập phù hợp tại đó. Việc chọn nơi lưu cần xem xét mô hình đe dọa của ứng dụng, bao gồm script, extension, XSS, session và CSRF theo kiến trúc đang dùng. Không có một vị trí lưu duy nhất tự giải quyết mọi rủi ro PII.

Nếu một mô hình backend giữ token phía máy chủ, cần bảo vệ phiên kết nối trình duyệt với backend và giới hạn dữ liệu trả về. Việc chuyển token khỏi JavaScript không có tác dụng giảm chia sẻ nếu backend vẫn đưa toàn bộ claims vào một API hồ sơ công khai cho client.

## 7. Thời hạn token không phải thời hạn tồn tại của mọi bản sao PII

### 7.1. Hết hạn sử dụng không làm payload tự biến mất

`exp` giới hạn thời gian chấp nhận token theo quy tắc xác minh. Nó không xóa token khỏi file log, cache, backup hoặc ảnh chụp đã được tạo. Một JWT ký không mã hóa dù hết hạn vẫn có thể được đọc để thấy email hay dữ liệu cá nhân trong payload.

Vì vậy, thời gian sống ngắn có thể giảm cửa sổ lạm dụng credential nhưng không thay thế việc giảm claims và kiểm soát lưu giữ. Không nên giữ toàn bộ token trong log rồi dựa vào `exp` để cho rằng thông tin bên trong đã hết rủi ro riêng tư.

### 7.2. Claims có thể trở nên lỗi thời

Email, chức danh, nhóm và quyền có thể thay đổi sau khi token được phát hành. Token tự chứa dữ liệu thường biểu diễn một snapshot tại thời điểm phát hành, trừ khi hệ thống có thêm bước kiểm tra trạng thái hiện hành.

Khi thu hồi quyền hoặc cập nhật hồ sơ, cần hiểu token cũ còn được chấp nhận tới khi nào và các bên nhận đã cache thông tin gì. Cơ chế có thể bao gồm thời hạn phù hợp, kiểm tra trạng thái trực tuyến, thu hồi theo khả năng của nền tảng hoặc xác minh lại quyết định quyền. Không mặc định sửa hồ sơ trong directory đã thay đổi mọi token đang lưu hành.

Khi bỏ một claim khỏi cấu hình phát hành, token mới có thể không còn trường đó, nhưng token cũ và bản sao đã lưu vẫn cần được xử lý theo vòng đời tương ứng. Rotation khóa cũng không tự xóa những bản plaintext đã được đọc hoặc ghi lại trước đó.

## 8. Quy trình kiểm soát và xử lý khi phát hiện chia sẻ quá mức

Một quy trình thiết kế có thể bắt đầu từ việc kiểm kê từng loại token, bên phát hành, bên nhận và luồng truyền. Sau đó, lập danh sách claims theo mục đích, giữ các yêu cầu bảo mật của protocol và loại các trường tùy chọn không cần cho bên nhận.

Cần kiểm tra cả cấu hình thực tế: token mẫu bằng dữ liệu giả, log ở gateway, tracing, error reporter, introspection response và API trả thông tin hồ sơ. Chỉ xem cấu hình ở authorization server có thể bỏ sót việc một thành phần khác đang lưu nguyên token.

Khi phát hiện token thật bị lộ, đánh giá đồng thời khả năng sử dụng credential và dữ liệu đã bị tiết lộ. Tùy khả năng nền tảng, có thể cần vô hiệu hóa hoặc hạn chế token bị ảnh hưởng, xử lý phiên liên quan, sửa nguồn rò rỉ và kiểm tra các bản sao trong hệ thống vận hành. Quy trình xử lý bằng chứng cần giữ khả năng điều tra mà không tiếp tục phát tán nguyên token.

Nếu vấn đề là claims được chia sẻ quá rộng nhưng chưa có bằng chứng rò rỉ credential, vẫn cần điều chỉnh contract và xác định bên nhận đã lưu gì. Tránh thay đổi claims một cách thiếu phối hợp làm hỏng liên kết tài khoản hoặc quyết định quyền. Có thể chuyển đổi theo giai đoạn với mapping rõ ràng và xác minh bên nhận không còn phụ thuộc vào trường bị loại bỏ.

## 9. Tự kiểm tra cách hiểu

**Token đã được ký có giấu email trong payload không?**

Không nếu token chỉ được ký mà không mã hóa. Chữ ký bảo vệ tính toàn vẹn theo cơ chế dùng, còn bên có token vẫn có thể đọc payload thông thường của JWT ký.

**Token không chứa tên hoặc email có còn rủi ro riêng tư không?**

Có. `sub`, thông tin nhóm, thiết bị hoặc định danh phiên có thể liên kết hoạt động với một người khi kết hợp dữ liệu khác. Token còn có thể là credential cần được bảo vệ khỏi sử dụng trái phép.

**JWT đã hết hạn có thể được giữ công khai để debug không?**

Không nên. Hết hạn không xóa thông tin trong payload hoặc bảo đảm token không còn giá trị trong mọi cấu hình lỗi. Dùng dữ liệu giả và sự kiện debug đã loại thông tin không cần thiết.

**Opaque token có tự bảo đảm hệ thống không chia sẻ PII quá mức không?**

Không. Nó hạn chế khả năng tự đọc claims từ chuỗi token, nhưng introspection, API hồ sơ, backend và log vẫn có thể tiết lộ dữ liệu dư. Cần kiểm soát toàn bộ luồng dữ liệu và bên nhận.

**Một thiết kế token phù hợp với quyền riêng tư cần đạt điều gì?**

Token cung cấp đủ thông tin cho mục đích xác thực hoặc truy cập đã xác định, có bên nhận và vòng đời rõ ràng, đồng thời giảm claims không cần thiết. Mọi thành phần nhận token vẫn phải bảo vệ credential, xác minh đúng protocol và hạn chế dữ liệu được lưu hoặc chuyển tiếp.
