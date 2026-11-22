# Định danh ổn định, định danh theo cặp và khả năng liên kết người dùng

JWT thường mang claim `sub` để cho biết token đại diện cho chủ thể nào. Nếu mọi ứng dụng nhận cùng một định danh ổn định của người dùng, chúng có thể liên kết hoạt động của người đó qua nhiều dịch vụ, kể cả khi không có nhu cầu nghiệp vụ để chia sẻ danh tính. **Pairwise subject identifier** giảm khả năng liên kết trực tiếp này bằng cách cấp một định danh khác nhau cho từng nhóm client được xác định trước. Tuy vậy, đổi `sub` không tự động bảo vệ quyền riêng tư nếu token vẫn chứa email, số điện thoại, tên, mã khách hàng hoặc các thuộc tính có thể đối chiếu.

Bài này thuộc chương **Dữ liệu và riêng tư** của module **Security - JSON Web Token (JWT)**. Nội dung áp dụng cho thiết kế định danh và bảo vệ dữ liệu trong hệ thống JWT nói chung. Phần pairwise subject trình bày theo OpenID Connect (OIDC); JWT thuần không tự định nghĩa một cơ chế pairwise identifier.

## 1. Mục tiêu và nguyên tắc

Sau bài học, người đọc có thể:

1. Giải thích vai trò của `sub` và phạm vi duy nhất của định danh trong một issuer.
2. Phân biệt public subject identifier, pairwise subject identifier, session ID và token ID.
3. Mô tả cách OIDC dùng sector identifier để nhóm các client khi tạo pairwise subject.
4. Đánh giá khả năng liên kết người dùng qua nhiều issuer, client, tenant và dịch vụ.
5. Thiết kế định danh ổn định, opaque, không phụ thuộc email hoặc username.
6. Nhận diện các claim khác có thể làm lộ danh tính hoặc vô hiệu hóa lợi ích của pairwise subject.
7. Thiết kế account linking, migration, rotation và kiểm thử quyền riêng tư.

**Nguyên tắc:** định danh nên ổn định trong đúng phạm vi cần thiết, nhưng không được chia sẻ rộng hơn nhu cầu nghiệp vụ. Mỗi bên nhận chỉ nên có khả năng nhận diện và liên kết người dùng trong trust boundary được phép.

## 2. `sub` trong JWT đại diện cho điều gì?

Claim `sub` (Subject) xác định chủ thể mà JWT nói đến. Chủ thể có thể là người dùng, service account, workload hoặc một thực thể khác tùy token profile.

Theo RFC 7519:

- `sub` là một chuỗi phân biệt chữ hoa/chữ thường.
- Giá trị này được issuer định nghĩa.
- Nếu được sử dụng, giá trị phải duy nhất cục bộ trong phạm vi issuer hoặc duy nhất trên toàn cục.
- Trong hệ thống nhiều issuer, bên nhận thường kết hợp `iss` và `sub` để xác định chủ thể.

Vì vậy, định danh nên được hiểu là cặp:

~~~text
subject_key = (issuer, subject)
~~~

Không giả định `sub` là duy nhất trên toàn Internet hoặc giữa mọi identity provider. Hai issuer khác nhau có thể cùng phát hành `sub` bằng `user-123` cho hai người khác nhau.

Ví dụ:

~~~json
{
  "iss": "https://identity-a.example.test/",
  "sub": "user-123",
  "aud": "orders-api"
}
~~~

Và:

~~~json
{
  "iss": "https://identity-b.example.test/",
  "sub": "user-123",
  "aud": "orders-api"
}
~~~

Hai token trên không nhất thiết đại diện cho cùng một người. Resource server phải xác minh issuer và áp dụng đúng namespace định danh.

## 3. Định danh ổn định và định danh có thể thay đổi

Một định danh ổn định cho phép các hệ thống nhận biết cùng một chủ thể qua nhiều lần phát hành token. Định danh có thể thay đổi thường được dùng cho thông tin hồ sơ hoặc thông tin liên hệ.

| Giá trị | Tính ổn định | Có nên dùng làm `sub`? |
| --- | --- | --- |
| Email | Có thể đổi, có thể được cấp lại cho người khác | Không nên |
| Username | Có thể đổi, có thể tái sử dụng | Không nên |
| Số điện thoại | Có thể đổi hoặc được nhà mạng cấp lại | Không nên |
| Tên hiển thị | Có thể đổi và không duy nhất | Không |
| Mã nội bộ ngẫu nhiên, không tái sử dụng | Có thể ổn định | Có thể, nếu scope và quyền riêng tư phù hợp |
| Pairwise opaque identifier | Ổn định trong một sector | Phù hợp cho OIDC pairwise subject |
| Session ID | Chỉ ổn định trong một phiên | Không thay cho subject |
| JWT `jti` | Định danh một token | Không thay cho subject |

Email hoặc username có thể hữu ích cho giao diện và liên hệ, nhưng không nên là khóa định danh chính trong authorization, account linking hoặc dữ liệu lâu dài. Nếu người dùng đổi email, quyền sở hữu tài nguyên không nên bị chuyển sang một chủ thể khác.

### 3.1. Không tái sử dụng subject đã cấp

Một subject identifier đã được cấp cho một người không nên được tái sử dụng cho người khác sau khi tài khoản bị xóa. Nếu tái sử dụng, dữ liệu lịch sử, audit record, consent hoặc quyền truy cập có thể bị gắn nhầm sang chủ thể mới.

Với OIDC, `sub` được yêu cầu duy nhất và không được tái cấp cho một End-User khác trong phạm vi issuer. Hệ thống nên duy trì quy tắc này cả sau khi tài khoản bị đóng hoặc ẩn danh hóa.

## 4. Public subject identifier và khả năng liên kết

OIDC định nghĩa hai loại subject identifier phổ biến:

- **Public subject identifier:** cùng một người dùng có cùng `sub` khi đăng nhập vào các client của cùng OpenID Provider.
- **Pairwise subject identifier:** cùng một người dùng có subject khác nhau giữa các sector identifier.

### 4.1. Public subject

Ví dụ:

| Client | Subject nhận được |
| --- | --- |
| `calendar.example.test` | `u-8f31` |
| `drive.example.test` | `u-8f31` |
| `shop.example.test` | `u-8f31` |

Các client có thể nhận ra rằng ba tài khoản tương ứng cùng một người chỉ bằng cách so sánh `sub`, nếu chúng có thể trao đổi dữ liệu.

Public subject có thể phù hợp khi:

- Các client thuộc cùng một tổ chức và có nhu cầu nghiệp vụ rõ ràng để nhận diện cùng người dùng.
- Người dùng mong muốn một hồ sơ thống nhất giữa các dịch vụ.
- Chính sách và thông báo quyền riêng tư cho phép liên kết dữ liệu đó.

Rủi ro xuất hiện khi các bên độc lập có thể ghép dữ liệu mà người dùng không mong đợi.

### 4.2. Pairwise subject

Pairwise subject cấp một giá trị khác nhau cho từng sector:

| Sector / nhóm client | Subject nhận được |
| --- | --- |
| Sector A | `p-2b91` |
| Sector B | `p-7d04` |
| Sector C | `p-a631` |

Client trong cùng sector có thể nhận cùng subject để hỗ trợ trải nghiệm thống nhất trong một nhóm ứng dụng. Client ở sector khác không thể liên kết người dùng chỉ bằng cách so sánh `sub`.

Pairwise subject là một định danh giả danh (pseudonymous identifier), không phải dữ liệu ẩn danh. Identity Provider vẫn có thể ánh xạ các subject đó về cùng tài khoản nội bộ.

## 5. Sector identifier trong OpenID Connect

Trong OIDC, pairwise subject được tạo theo **Sector Identifier**. Sector xác định nhóm client được phép nhận cùng một pairwise subject của một End-User.

Theo OIDC Core, Sector Identifier thường được xác định từ host của các registered redirect URI. Khi client cần gom nhiều redirect URI hoặc nhiều host vào cùng một sector, có thể dùng `sector_identifier_uri` theo quy tắc của đặc tả.

Một `sector_identifier_uri` trỏ đến tài liệu JSON qua HTTPS, chứa danh sách redirect URI tương ứng. Khi sử dụng, host của URI này xác định Sector Identifier; OpenID Provider kiểm tra các URI đã đăng ký với danh sách trong tài liệu theo OIDC Core.

Ví dụ khái niệm:

~~~text
Client A:
  redirect_uri = https://app-a.example.test/callback

Client B:
  redirect_uri = https://app-b.example.test/callback

Nếu dùng host riêng làm sector:
  Sector A = app-a.example.test
  Sector B = app-b.example.test

Nếu hai client được cấu hình cùng sector_identifier_uri hợp lệ:
  Cả hai có thể thuộc cùng một sector theo policy OIDC.
~~~

### 5.1. Sector không đồng nghĩa tenant hoặc origin

Sector là khái niệm OIDC để xác định phạm vi pairwise subject. Nó không tự động đồng nghĩa:

- Tenant trong hệ thống SaaS.
- Origin của mọi API.
- Một tổ chức pháp lý.
- Một nhóm người dùng.
- Một permission boundary.

Tổ chức cần cấu hình sector theo mục đích chia sẻ danh tính. Không gom nhiều client vào cùng sector chỉ vì chúng dùng chung một identity provider hoặc cùng thuộc một sản phẩm.

### 5.2. Khi nào nên dùng chung sector?

Có thể dùng chung sector khi các client:

- Thuộc cùng một nhóm ứng dụng có lý do nghiệp vụ để nhận diện cùng người dùng.
- Có chủ thể kiểm soát và quản trị đáng tin cậy.
- Có chính sách chia sẻ dữ liệu và thông báo cho người dùng phù hợp.
- Có quy trình xử lý khi client rời nhóm hoặc chuyển quyền sở hữu.

Nếu hai ứng dụng độc lập, không có nhu cầu liên kết, nên dùng sector riêng để giảm khả năng tương quan.

## 6. Cách tạo pairwise identifier

OIDC yêu cầu OpenID Provider tạo pairwise subject ổn định theo End-User và Sector Identifier. Đặc tả quy định kết quả và cách nhóm client, nhưng không bắt buộc một thuật toán dẫn xuất duy nhất cho mọi provider.

Một triển khai cần bảo đảm pairwise identifier:

- Ổn định cho cùng End-User trong cùng sector theo vòng đời đã cam kết.
- Khác nhau giữa các sector, với xác suất va chạm không đáng kể.
- Không để client suy ra trực tiếp internal user ID hoặc email.
- Không thể đảo ngược bằng cách thử các giá trị phổ biến nếu không có bí mật hoặc bảng ánh xạ.
- Không bị tái sử dụng cho người dùng khác.
- Có thể được tìm lại nhất quán sau restart, backup/restore hoặc triển khai nhiều instance.

### 6.1. Mapping table

Một cách dễ kiểm soát là lưu ánh xạ:

~~~text
(internal_subject_id, sector_id) -> pairwise_subject_id
~~~

Ví dụ:

| Internal subject | Sector | Pairwise subject |
| --- | --- | --- |
| `acct-1007` | `sector-a` | `p-2b91` |
| `acct-1007` | `sector-b` | `p-7d04` |
| `acct-2044` | `sector-a` | `p-6c20` |

Ưu điểm:

- Dễ giữ định danh ổn định khi thay đổi thuật toán hoặc secret.
- Có thể kiểm tra unique constraint và tránh tái sử dụng.
- Hỗ trợ migration, account linking và audit.

Đổi lại, provider phải bảo vệ mapping store như dữ liệu định danh nhạy cảm vì nó có thể liên kết nhiều pseudonym về một người.

### 6.2. Dẫn xuất bằng keyed function

Một hệ thống có thể cân nhắc dẫn xuất pseudonym từ internal subject và sector bằng keyed cryptographic function:

~~~text
pairwise_subject =
    BASE64URL(HMAC-SHA-256(secret, internal_subject || separator || sector_id))
~~~

Đây chỉ là mô hình thiết kế minh họa, không phải thuật toán bắt buộc của OIDC. Nếu sử dụng:

- Secret phải được giữ bí mật và tách khỏi key ký JWT.
- Input phải có encoding và phân tách không mơ hồ.
- Có versioning cho secret/algorithm.
- Có kế hoạch khi secret bị rotate hoặc compromise.
- Bảo đảm kết quả đủ dài và không bị cắt ngắn gây collision.
- Không dùng plain hash của email, username hoặc user ID dễ đoán.

Keyed derivation có thể giảm nhu cầu lưu mapping trực tiếp, nhưng rotation secret có thể làm thay đổi mọi subject. Mapping table hoặc một lớp migration có thể cần thiết để giữ tương thích.

### 6.3. Không dùng hash email làm pairwise subject

Email có entropy thấp và thường xuất hiện trong nguồn dữ liệu khác. Nếu tạo `sub` bằng SHA-256(email), bên nhận có thể thử từ điển email phổ biến để tìm lại địa chỉ. Thêm salt công khai không loại bỏ hoàn toàn rủi ro đoán nếu đầu vào dễ dự đoán.

Pairwise identifier cần được tạo từ internal identifier không công khai và cơ chế bảo vệ phù hợp, hoặc từ mapping ngẫu nhiên do provider quản lý.

## 7. Đưa subject vào ID Token và UserInfo

Trong OIDC, ID Token chứa `sub` để client xác định End-User trong phạm vi issuer. UserInfo response cũng trả `sub` và phải khớp với subject trong ID Token theo quy tắc OIDC.

Ví dụ hai client ở hai sector khác nhau:

**Client thuộc sector A**

~~~json
{
  "iss": "https://id.example.test/",
  "aud": "client-a",
  "sub": "pairwise-2b91",
  "iat": 1794820000,
  "exp": 1794823600
}
~~~

**Client thuộc sector B**

~~~json
{
  "iss": "https://id.example.test/",
  "aud": "client-b",
  "sub": "pairwise-7d04",
  "iat": 1794820100,
  "exp": 1794823700
}
~~~

Issuer giống nhau nhưng `sub` khác nhau. Client A không nên có API để tự đổi `pairwise-2b91` thành `pairwise-7d04` nếu không có một quy trình account linking được cho phép.

Không tự giả định mọi JWT trong hệ thống đều phải dùng pairwise subject. Access token, ID Token, service token và token nội bộ có thể có token profile khác nhau. Hãy xác định rõ đối tượng nhận và mục đích sử dụng của từng token.

## 8. `sub` không phải `jti`, `sid` hay `client_id`

Các identifier trong JWT/OIDC có mục đích khác nhau:

| Giá trị | Định danh | Phạm vi điển hình |
| --- | --- | --- |
| `sub` | Chủ thể được token đại diện | Issuer và subject policy |
| `jti` | Một JWT cụ thể | Từng token; có thể dùng cho replay detection/denylist |
| `sid` | Một phiên đăng nhập OIDC | Session theo issuer và logout/session policy |
| `client_id` / `aud` | Client hoặc resource server nhận token | Client/resource context |
| `iss` | Bên phát hành token | Namespace của subject và trust |
| `sector identifier` | Nhóm client dùng chung pairwise subject | OIDC pairwise scope |

Không dùng `jti` làm định danh người dùng vì mỗi lần cấp token có thể tạo `jti` khác nhau. Không dùng `sid` làm định danh tài khoản lâu dài vì một người có thể có nhiều session. Không dùng `client_id` làm subject.

## 9. Khả năng liên kết người dùng (linkability)

Linkability là khả năng xác định hai bản ghi, sự kiện hoặc tài khoản ở các ngữ cảnh khác nhau thuộc cùng một chủ thể.

Liên kết có thể xảy ra:

- Giữa hai ứng dụng của cùng một identity provider.
- Giữa nhiều tenant trong một SaaS.
- Giữa token được phát hành ở các thời điểm khác nhau.
- Giữa dữ liệu đăng nhập và dữ liệu analytics.
- Giữa nhiều tổ chức thông qua dữ liệu được chia sẻ.
- Giữa các thiết bị hoặc session của cùng người dùng.

Linkability không phải lúc nào cũng xấu. Hệ thống có thể cần liên kết để cung cấp một tài khoản thống nhất, phát hiện gian lận hoặc đáp ứng yêu cầu audit. Rủi ro xuất hiện khi liên kết vượt quá mục đích, sự đồng ý hoặc quyền truy cập được phép.

### 9.1. Linkability trực tiếp

Hai bên nhìn thấy cùng một identifier ổn định, chẳng hạn public `sub` hoặc internal customer ID. Chỉ cần so sánh chuỗi là có thể nhận ra cùng chủ thể.

### 9.2. Linkability gián tiếp

Ngay cả khi `sub` khác nhau, các bên vẫn có thể ghép dữ liệu qua:

- Email hoặc số điện thoại.
- Tên, ngày sinh, địa chỉ hoặc thông tin hồ sơ hiếm.
- Mã khách hàng, mã nhân viên hoặc external account ID.
- Ảnh đại diện hoặc URL hồ sơ ổn định.
- Nhóm quyền hoặc thuộc tính tổ chức quá đặc thù.
- Dấu thời gian đăng nhập, hành vi và mẫu sử dụng.
- IP, device identifier hoặc browser fingerprint từ hệ thống khác.

Pairwise subject chỉ làm giảm một kênh liên kết trực tiếp. Nó không tạo ra anonymity và không ngăn các bên hợp tác ghép dữ liệu khác.

## 10. Các claim khác có thể làm lộ khả năng liên kết

Khi thiết kế token profile, cần đánh giá toàn bộ claims chứ không chỉ `sub`.

| Claim/dữ liệu | Rủi ro liên kết | Hướng giảm thiểu |
| --- | --- | --- |
| `email`, `email_verified` | Email thường là identifier chung giữa nhiều dịch vụ | Chỉ cấp khi client có scope và mục đích phù hợp; cân nhắc email relay/alias |
| `phone_number` | Số điện thoại thường được dùng trên nhiều nền tảng | Không cấp mặc định; giới hạn theo consent/scope |
| `name`, `preferred_username` | Có thể đối chiếu giữa các ứng dụng | Chỉ chia sẻ khi cần cho trải nghiệm |
| `birthdate`, `address` | Thuộc tính kết hợp có thể nhận diện cá nhân | Data minimization và giảm độ chi tiết |
| `employee_id`, `customer_id` | Mã ổn định có thể nối dữ liệu giữa hệ thống | Dùng identifier riêng theo audience/sector |
| `groups`, `roles`, `organization` | Có thể tiết lộ quan hệ nội bộ hoặc tổ chức | Chỉ phát hành quyền cần thiết cho resource |
| `sid` | Có thể liên kết hoạt động trong cùng session | Scope theo client/sector; không dùng như user ID |
| `jti` | Có thể liên kết cùng token trong log hoặc telemetry | Không tái sử dụng; hạn chế chia sẻ và log |
| `auth_time`, `acr`, `amr` | Tiết lộ thời điểm/cấp độ xác thực | Chỉ phát hành khi client cần |
| Custom claims | Có thể chứa mã nội bộ hoặc identifier khác | Review schema và privacy impact trước khi cấp |

Không nên đưa toàn bộ profile người dùng vào mọi access token. Resource server chỉ cần claims phục vụ authorization và nghiệp vụ cụ thể.

## 11. Data minimization trong JWT

JWT ký (JWS) thường chỉ bảo vệ tính toàn vẹn và nguồn gốc; payload Base64url không được mã hóa và có thể đọc bởi bên nắm token. Vì vậy, mọi claim được phát hành phải được xem là dữ liệu có thể bị đọc bởi client, resource server, proxy hoặc log có quyền truy cập token.

Một token tối giản có thể gồm:

~~~json
{
  "iss": "https://id.example.test/",
  "sub": "pairwise-2b91",
  "aud": "orders-api",
  "exp": 1794823600,
  "scope": "orders:read"
}
~~~

Không cần thêm email, ngày sinh, địa chỉ hoặc danh sách mọi nhóm quyền nếu API không sử dụng chúng.

Nếu cần giữ bí mật nội dung JWT trước người nắm token, có thể cân nhắc JWE hoặc opaque token/introspection theo threat model. Mã hóa không xóa khả năng liên kết ở các bên có quyền giải mã, và không thay thế việc giảm thiểu dữ liệu.

## 12. Chọn identifier theo audience và purpose

Một identifier nên được tạo cho phạm vi sử dụng cụ thể:

| Use case | Identifier phù hợp |
| --- | --- |
| OIDC client cần nhận diện End-User | Public hoặc pairwise `sub` theo policy |
| API cần phân biệt user trong issuer | Cặp `(iss, sub)` hoặc mapping nội bộ đã xác thực |
| Resource server cần định danh workload | Subject/service principal theo workload trust domain |
| Một token cụ thể cần chống replay | `jti` |
| Quản lý phiên đăng nhập | Session identifier riêng như `sid` theo profile |
| Analytics nhiều sản phẩm | Pseudonymous analytics ID riêng, có consent/purpose phù hợp |
| Data warehouse cần hợp nhất dữ liệu | Mapping qua controlled identity service, có quyền và audit |

Không phát hành một global user ID cho mọi client chỉ vì dễ join database. Nếu có nhu cầu hợp nhất dữ liệu, hãy thực hiện ở một dịch vụ trung gian được kiểm soát thay vì đưa global identifier vào mọi JWT.

## 13. Account linking giữa các pairwise subject

Người dùng có thể đăng nhập vào hai ứng dụng thuộc hai sector và nhận hai `sub` khác nhau. Nếu tổ chức có nhu cầu liên kết hai tài khoản, cần một quy trình có chủ đích.

Không nên:

- Cho client tự gửi hai subject rồi yêu cầu server hợp nhất.
- Ghép tài khoản chỉ vì email giống nhau.
- Dùng suy đoán dựa trên tên, số điện thoại hoặc ngày sinh.
- Cho một client đọc mapping subject của client khác.
- Tạo API tra cứu global user ID không có authorization và audit.

Quy trình account linking an toàn nên:

1. Xác thực người dùng với cả hai tài khoản hoặc dùng một phương thức xác minh đủ mạnh cho cả hai.
2. Thông báo rõ tài khoản/dịch vụ nào sẽ được liên kết và mục đích.
3. Yêu cầu xác nhận phù hợp, đặc biệt khi việc liên kết mở rộng quyền chia sẻ dữ liệu.
4. Lưu mapping trong identity service có kiểm soát truy cập.
5. Ghi audit event về ai, lúc nào, theo consent/purpose nào.
6. Có cách hủy liên kết và xử lý quyền/dữ liệu đã chia sẻ.

Email giống nhau có thể là tín hiệu hỗ trợ, nhưng không phải bằng chứng đủ mạnh để tự động hợp nhất tài khoản. Email có thể chưa được xác minh, được chia sẻ hoặc được cấp lại.

## 14. Cross-issuer identity linking

Hai issuer có thể phát hành subject khác nhau cho cùng một người. Không có quy tắc chung cho phép resource server tự suy ra hai subject đó tương đương.

Nếu cần federation hoặc account linking:

- Xác minh chữ ký, issuer, audience và token profile của từng issuer.
- Dùng quy trình liên kết được người dùng hoặc quản trị viên cho phép.
- Lưu mapping giữa issuer-subject pair trong một trust service.
- Không dùng raw `sub` làm khóa toàn cục.
- Xem xét assurance level, xác minh email và phương thức xác thực của từng issuer.
- Có quy trình khi issuer thay đổi subject hoặc chấm dứt dịch vụ.

Không tin một issuer chỉ vì tên miền gần giống issuer khác. Trust phải dựa trên cấu hình federation được quản trị.

## 15. Thay đổi sector, client và redirect URI

Thay đổi cấu hình sector có thể làm thay đổi pairwise subject mà client nhận được. Đây là thay đổi có tác động đến account mapping và dữ liệu lịch sử.

Trước khi thay đổi:

1. Kiểm kê client đang dùng sector cũ.
2. Xác định client nào cần tiếp tục chia sẻ subject.
3. Đánh giá việc chuyển host hoặc `sector_identifier_uri`.
4. Xác định account mapping có thể bị mất nếu subject thay đổi.
5. Thông báo cho client theo quy trình thay đổi tương thích.
6. Thiết kế migration có kiểm soát và thời gian chuyển tiếp.

Không tự ý gộp hoặc tách sector trong production mà không đánh giá tác động. Nếu client nhận subject mới, backend có thể coi đó là một người dùng mới và tạo tài khoản trùng.

## 16. Rotation và migration định danh

Pairwise subject thường cần ổn định lâu dài để client liên kết dữ liệu. Vì vậy, thay đổi thuật toán dẫn xuất, secret hoặc mapping store cần được quản lý như một migration dữ liệu định danh.

Các lựa chọn:

### 16.1. Giữ mapping cũ

Nếu dùng mapping table, giữ pairwise subject đã cấp và chỉ tạo mapping mới cho subject/sector mới. Đây thường là cách giảm gián đoạn cho client.

### 16.2. Versioned derivation

Nếu dùng keyed derivation, có thể lưu version của secret/algorithm và hỗ trợ kiểm tra mapping cũ trong thời gian chuyển tiếp. Không đổi secret một cách âm thầm rồi phát hành subject mới cho tất cả người dùng.

### 16.3. Forced re-linking

Nếu mapping cũ bị compromise hoặc không thể duy trì, có thể phải yêu cầu người dùng liên kết lại. Quy trình cần xác minh danh tính, thông báo và audit; không tự động gán tài khoản theo email.

### 16.4. Xử lý xóa tài khoản

Khi xóa tài khoản:

- Ngừng phát hành token mới cho chủ thể.
- Thu hồi session/grant theo policy.
- Xóa hoặc giữ mapping theo yêu cầu pháp lý và mục đích lưu trữ.
- Không tái sử dụng pairwise subject cũ cho người khác.
- Nếu cần giữ audit record, giảm thiểu hoặc pseudonymize theo policy.

## 17. Pairwise identifier và multi-tenant SaaS

Trong SaaS, một người có thể là thành viên của nhiều tenant. Một global `sub` dùng chung ở mọi tenant giúp vận hành đơn giản nhưng có thể làm các tenant liên kết hoạt động của cùng người dùng.

Có thể chọn:

- **Tenant-scoped subject:** mỗi tenant có identifier riêng.
- **Organization-scoped subject:** nhiều ứng dụng trong một tổ chức dùng chung identifier theo mục đích được duyệt.
- **Global subject:** chỉ dùng khi có lý do nghiệp vụ rõ ràng và quyền liên kết được công bố.

Đừng nhầm tenant-scoped identifier của SaaS với OIDC pairwise subject. Chúng có thể dùng ý tưởng tương tự nhưng cần định nghĩa namespace, lifecycle, issuer và API contract riêng.

Ví dụ một bảng định danh:

~~~text
issuer_id | tenant_id | internal_subject | external_subject
----------|-----------|------------------|----------------
idp-main  | tenant-a  | acct-1007        | ta-p-2b91
idp-main  | tenant-b  | acct-1007        | tb-p-7d04
idp-main  | tenant-c  | acct-1007        | tc-p-a631
~~~

Mapping này cần được bảo vệ chặt vì nó có thể nối các pseudonym khác nhau về cùng một internal subject.

## 18. Rủi ro khi dùng định danh ổn định trong analytics và logging

Đưa `sub` vào mọi log, trace và analytics event có thể tạo ra một kho dữ liệu liên kết hành vi người dùng xuyên dịch vụ.

Hãy phân biệt:

- Security audit cần một identifier để điều tra sự kiện.
- Product analytics cần đo hành vi trong một phạm vi sản phẩm.
- Billing cần định danh account/contract.
- Support cần tìm đúng tài khoản khi có yêu cầu.

Không nhất thiết các hệ thống này phải dùng cùng một identifier. Có thể tạo pseudonymous ID riêng theo purpose, quyền truy cập và retention.

Biện pháp:

- Chỉ log subject khi có mục đích và quyền truy cập rõ.
- Pseudonymize identifier cho analytics nếu không cần danh tính trực tiếp.
- Không dùng raw `sub`, email hoặc phone làm metric label.
- Giới hạn retention và quyền export.
- Audit việc tra cứu mapping giữa pairwise ID và internal account.
- Không đưa global ID vào telemetry gửi cho bên thứ ba nếu không cần.

Pseudonymization vẫn là xử lý dữ liệu có thể liên kết nếu tổ chức giữ mapping hoặc có thể tái nhận diện bằng dữ liệu khác. Không coi pseudonym là dữ liệu anonymous.

## 19. Kiểm thử privacy và linkability

Kiểm thử không chỉ xác nhận token hợp lệ; cần kiểm tra định danh có được cấp đúng phạm vi.

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Cùng người dùng, cùng issuer, cùng sector | Pairwise `sub` ổn định qua các lần đăng nhập theo policy. |
| Cùng người dùng, hai sector khác nhau | `sub` khác nhau. |
| Hai client cùng sector | Có cùng pairwise `sub` nếu OIDC configuration quy định như vậy. |
| Hai người dùng khác nhau trong cùng sector | `sub` khác nhau, không collision. |
| Cùng `sub` nhưng issuer khác nhau | Được xử lý như namespace khác nhau. |
| Người dùng đổi email | `sub` không đổi chỉ vì email đổi. |
| Tài khoản bị xóa rồi có người khác đăng ký lại email cũ | Subject cũ không được tái sử dụng cho người mới. |
| Token chứa pairwise `sub` nhưng kèm email/global ID | Privacy review phát hiện kênh linkability còn lại. |
| Client thử tra mapping sang sector khác | Bị từ chối nếu không có quyền linking. |
| Sector/redirect URI thay đổi | Migration được kiểm soát; không tạo tài khoản trùng âm thầm. |
| Secret dẫn xuất được rotate | Subject stability/migration tuân theo policy; không đổi ngoài dự kiến. |
| UserInfo trả `sub` khác ID Token | Bị phát hiện và xử lý theo OIDC validation. |

### 19.1. Kiểm thử linkability thực tế

Tạo hai bộ token cho cùng người dùng ở các client/sector khác nhau, sau đó kiểm tra:

- Chỉ dùng `iss` và `sub`, hai bên có thể liên kết hay không?
- Nếu bỏ `sub`, các claims còn lại có đủ nhận diện không?
- Có custom claim nào chứa cùng internal ID không?
- Có URL/avatar/device ID ổn định được chia sẻ không?
- Log hoặc analytics có một khóa join chung không?
- Client có thể gọi endpoint nào để tìm global account mapping?

Kết quả nên được đánh giá theo dữ liệu mà từng bên thực sự có thể truy cập, không chỉ theo payload JWT mẫu.

## 20. Những anti-pattern cần tránh

| Anti-pattern | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Dùng email làm `sub` | Email đổi được, có thể tái cấp và dễ liên kết | Dùng opaque immutable subject |
| Dùng global `sub` cho mọi client | Các client có thể so sánh và liên kết người dùng | Pairwise subject theo sector khi cần giảm linkability |
| Cho rằng pairwise `sub` tạo anonymity | Claims khác hoặc dữ liệu ngoài token vẫn có thể liên kết | Data minimization và privacy review toàn bộ luồng |
| Dùng plain hash(email) làm pairwise ID | Có thể bị dò từ điển | Random mapping hoặc keyed derivation an toàn |
| Dùng `jti` làm user identifier | Mỗi token có thể có ID khác nhau | Phân biệt token ID và subject ID |
| Dùng `sub` đơn lẻ qua nhiều issuer | Collision hoặc gán nhầm người dùng | Dùng `(iss, sub)` |
| Gộp sector tùy tiện | Nhiều client có thể liên kết người dùng ngoài mục đích | Quản trị sector theo trust boundary |
| Tự động account-link theo email | Chiếm đoạt hoặc hợp nhất nhầm tài khoản | Xác thực cả hai bên và yêu cầu xác nhận |
| Rotate subject âm thầm | Client tạo account trùng hoặc mất lịch sử | Migration và compatibility plan |
| Log global subject ở mọi hệ thống | Tạo đồ thị hành vi xuyên dịch vụ | Pseudonymous ID theo purpose và access control |
| Đưa nhiều profile claims vào mọi JWT | Tăng dữ liệu bị lộ và linkability | Phát hành tối thiểu theo audience/scope |

## 21. Checklist thiết kế định danh

**Subject semantics**

- [ ] Xác định chủ thể của từng token profile.
- [ ] Dùng `(iss, sub)` làm namespace nhận diện, không dùng `sub` đơn lẻ toàn cục.
- [ ] Subject ổn định và không phụ thuộc email/username có thể thay đổi.
- [ ] Không tái sử dụng subject đã cấp cho người khác.
- [ ] Phân biệt `sub`, `jti`, `sid`, `client_id` và tenant ID.

**Pairwise subject**

- [ ] Xác định rõ client nào thuộc cùng sector và vì sao.
- [ ] Dùng pairwise subject khi giảm liên kết giữa client là yêu cầu quyền riêng tư.
- [ ] Hiểu `sector_identifier_uri` và quy tắc sector theo OIDC Core.
- [ ] Pairwise ID ổn định trong sector và khác giữa các sector.
- [ ] Không dùng plain hash của email hoặc identifier dễ đoán.
- [ ] Mapping/derivation secret được bảo vệ và có migration plan.

**Data minimization và linking**

- [ ] Chỉ phát hành claims cần thiết cho audience/purpose.
- [ ] Đánh giá email, phone, name, organization, `sid` và custom claims như kênh liên kết.
- [ ] Account linking yêu cầu xác thực và quyền rõ ràng.
- [ ] Cross-issuer mapping nằm trong identity service được kiểm soát.
- [ ] Có cơ chế unlink, revoke và audit.

**Vận hành và privacy**

- [ ] Subject migration/sector change được kiểm thử.
- [ ] UserInfo `sub` khớp ID Token theo OIDC.
- [ ] Log/analytics dùng identifier theo purpose và retention.
- [ ] Mapping giữa pairwise ID và internal ID được bảo vệ.
- [ ] Có test xác nhận không link được qua các claims không cần thiết.

## 22. Tài liệu chuẩn tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): semantics của `sub`, `iss`, `aud` và các registered claims.
- [OpenID Connect Core 1.0 — Subject Identifier Types](https://openid.net/specs/openid-connect-core-1_0.html#SubjectIDTypes): public và pairwise subject identifiers.
- [OpenID Connect Core 1.0 — Sector Identifier](https://openid.net/specs/openid-connect-core-1_0.html#SectorIdentifier): sector identifier và `sector_identifier_uri`.
- [OpenID Connect Core 1.0 — ID Token](https://openid.net/specs/openid-connect-core-1_0.html#IDToken): yêu cầu và validation của ID Token.
- [OpenID Connect Core 1.0 — UserInfo](https://openid.net/specs/openid-connect-core-1_0.html#UserInfo): subject consistency giữa ID Token và UserInfo.
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638): thumbprint của public key; hữu ích khi thiết kế identifier/key reference nhưng không thay thế subject identifier.
- [NIST Privacy Framework](https://www.nist.gov/privacy-framework): quản trị rủi ro quyền riêng tư và dữ liệu có thể liên kết.

**Ghi nhớ:** `sub` là định danh trong namespace của issuer; hãy dùng `(iss, sub)` khi nhận diện chủ thể. Public subject giúp các client trong cùng issuer dễ liên kết; pairwise subject giới hạn liên kết trực tiếp theo sector. Pairwise không tạo anonymity nếu token còn email, phone, global ID hoặc thuộc tính có thể đối chiếu. Thiết kế tốt cần data minimization, account linking có kiểm soát và lifecycle không tái sử dụng định danh.
