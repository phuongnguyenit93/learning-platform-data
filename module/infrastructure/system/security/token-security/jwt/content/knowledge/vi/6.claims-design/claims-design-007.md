# Ngăn bên yêu cầu tự gán claims đặc quyền

## 1. Vấn đề: token được ký vẫn có thể chứa quyền sai

Một JSON Web Token (JWT) thường mang những khẳng định (*claims*) do bên phát hành (*issuer*) tạo ra. Chữ ký số giúp bên nhận phát hiện token bị sửa sau khi ký và xác minh token được tạo bằng khóa tương ứng. Tuy nhiên, chữ ký **không chứng minh nội dung claim là đúng về mặt nghiệp vụ**.

Giả sử một client gửi yêu cầu cấp token với dữ liệu:

```json
{
  "username": "user_42",
  "role": "admin",
  "permissions": ["orders:read", "orders:delete"],
  "tenant_id": "tenant_99"
}
```

Nếu dịch vụ phát hành token sao chép nguyên các trường từ request vào payload rồi ký, token sẽ có chữ ký hợp lệ nhưng chứa các quyền do chính bên yêu cầu tự khai báo. Kẻ tấn công không cần phá thuật toán ký; họ chỉ cần khiến issuer ký một khẳng định mà issuer không có thẩm quyền xác nhận.

Đây là lỗi **ranh giới tin cậy** trong quá trình phát hành token. Bên yêu cầu có thể đề nghị một phạm vi truy cập hoặc chọn ngữ cảnh, nhưng không được tự quyết định vai trò, quyền, trạng thái xác minh hay đặc quyền mà issuer đưa vào token.

Nguyên tắc quan trọng:

> **Client có thể gửi yêu cầu; issuer phải tự xác định những claims nào được phép phát hành.**

## 2. Những claim nào cần được bảo vệ?

Không phải mọi claim đều có cùng mức rủi ro. Cần nhận diện các claim có thể làm thay đổi danh tính, phạm vi dữ liệu hoặc quyết định phân quyền:

| Nhóm | Ví dụ | Rủi ro nếu client tự gán |
| --- | --- | --- |
| Vai trò và đặc quyền | role, roles, is_admin, is_superuser | Tự nâng quyền quản trị |
| Quyền thao tác | permissions, scope, entitlements | Gọi chức năng hoặc thao tác vượt quá quyền được cấp |
| Phạm vi dữ liệu | tenant_id, organization_id, account_id | Truy cập chéo tenant/tổ chức/tài khoản |
| Trạng thái tin cậy | email_verified, phone_verified, mfa, acr, amr | Bỏ qua bước xác minh hoặc mức xác thực bắt buộc |
| Danh tính và nguồn | sub, iss, aud, client_id | Giả mạo chủ thể, issuer hoặc đối tượng nhận token |
| Ủy quyền và đại diện | act, may_act, delegated_by hoặc claim tương đương theo profile | Giả mạo quan hệ đại diện hay quyền hành động thay người khác |

Tên claim cụ thể và ý nghĩa phụ thuộc giao thức/hồ sơ token. Không phải mọi tên trong bảng đều là registered claim của RFC 7519. Điểm chung là consumer có thể dùng chúng để đưa ra quyết định bảo mật, vì vậy nguồn phát hành và quy tắc tạo giá trị phải được kiểm soát.

Một claim hiển thị như display_name thường ít nhạy cảm hơn, nhưng vẫn không nên được dùng làm định danh hoặc bằng chứng quyền. Một claim tùy biến có thể trở thành claim đặc quyền ngay khi API dùng nó trong quyết định truy cập.

## 3. Ranh giới tin cậy giữa request, issuer và resource server

### 3.1. Bên yêu cầu chỉ cung cấp dữ liệu đầu vào

Các giá trị đến từ request, query parameter, header, cookie, form, client metadata hoặc user-editable profile đều phải được coi là dữ liệu do bên yêu cầu kiểm soát cho đến khi được xác minh độc lập.

Ví dụ:

- role=admin trong request đăng ký không chứng minh người dùng là admin.
- email_verified=true do client gửi không chứng minh email đã được xác minh.
- tenant_id=tenant_99 trong header không chứng minh người dùng là thành viên tenant đó.
- scope=orders:delete trong yêu cầu cấp token không chứng minh quyền xóa đã được cấp.

### 3.2. Issuer là nơi quyết định claim được phát hành

Issuer phải xác thực chủ thể, kiểm tra grant/consent và chính sách cấp quyền, tra cứu dữ liệu có thẩm quyền, sau đó tự tạo Claims Set. Issuer chịu trách nhiệm về những khẳng định mình ký.

### 3.3. Resource server xác minh token và áp dụng chính sách

API nhận token chỉ tin claims sau khi xác minh đúng cơ chế mật mã, issuer, audience, thời gian, loại token và profile. Sau đó API vẫn phải kiểm tra quyền trên hành động và tài nguyên cụ thể.

```text
Bên yêu cầu
    |
    | Gửi thông tin xác thực + yêu cầu quyền/ngữ cảnh
    v
Authorization Server / Token Issuer
    |
    +--> Xác thực chủ thể và client
    +--> Kiểm tra grant, consent, membership, policy
    +--> Tự chọn claims từ nguồn có thẩm quyền
    +--> Ký token bằng khóa được kiểm soát
    |
    v
JWT có claims do issuer quyết định
    |
    v
Resource Server
    |
    +--> Xác minh chữ ký, iss, aud, exp, loại token
    +--> Kiểm tra claims và chính sách trên tài nguyên
    |
    v
Cho phép hoặc từ chối
```

Không chuyển trách nhiệm quyết định quyền của issuer sang client. Cũng không coi việc issuer ký thành công là lý do để resource server bỏ qua kiểm tra audience, loại token hoặc quyền trên tài nguyên.

## 4. Lỗi phổ biến: sao chép request vào Claims Set

### 4.1. Mass assignment khi phát hành token

Một lỗi thiết kế nguy hiểm là dùng toàn bộ request body làm nguồn tạo payload:

```json
{
  "sub": "user_42",
  "role": "admin",
  "is_admin": true,
  "scope": "orders:read orders:delete",
  "tenant_id": "tenant_99"
}
```

Nếu issuer tự động đưa mọi thuộc tính vào token, client có thể thêm các trường không nằm trong giao diện chính thức hoặc lợi dụng thuộc tính bị bỏ sót trong allowlist. Đây là dạng **mass assignment**: dữ liệu đầu vào được gán hàng loạt vào đối tượng có thuộc tính nhạy cảm.

Không nên tạo Claims Set bằng cách merge trực tiếp:

```text
claims = trusted_claims + request_body
```

hoặc:

```text
claims.update(client_supplied_claims)
```

vì các trường từ request có thể ghi đè sub, role, scope, tenant_id hoặc claim khác. Cách an toàn là tạo một đối tượng claims mới từ danh sách trường được phép, lấy từng giá trị từ nguồn phù hợp và không đưa nguyên request vào payload.

### 4.2. Chỉ chặn một vài tên nhạy cảm là chưa đủ

Một blacklist như “không nhận role và is_admin” có thể bỏ sót roles, permissions, privilege_level, access_level hoặc claim tùy biến mà API đang tin cậy.

Ưu tiên **allowlist theo từng loại token**:

- Xác định trước claim nào được phép xuất hiện.
- Với từng claim, chỉ rõ nguồn tạo giá trị và kiểu dữ liệu.
- Claim nào client được phép đề nghị, claim nào chỉ issuer được tạo.
- Từ chối hoặc bỏ qua trường không được hỗ trợ theo chính sách đã công bố.
- Không để tên claim tùy ý từ request trở thành một phần của token.

Allowlist phải bao gồm cả các tên tùy biến và namespace claim mà hệ thống chấp nhận. Không dựa vào việc tên claim có vẻ lạ hay không để quyết định độ tin cậy.

## 5. Requested scope không phải granted scope

### 5.1. Yêu cầu phạm vi chỉ là đề nghị

Trong OAuth 2.0, client có thể yêu cầu một tập scope khi xin access token. Scope được yêu cầu thể hiện **mong muốn của client**, không phải bằng chứng client có quyền nhận tất cả scope đó.

Ví dụ client yêu cầu:

```text
scope=orders:read orders:create orders:delete
```

Authorization server phải kiểm tra client, chủ thể, loại grant, resource/audience, consent và chính sách. Kết quả có thể là:

```text
granted_scope = orders:read orders:create
```

Token chỉ được chứa các scope thực sự được cấp. Không sao chép nguyên chuỗi scope do client yêu cầu thành claim scope trong access token.

### 5.2. Cách xác định tập scope được cấp

Một mô hình khái quát:

```text
requested_scopes
       |
       v
Kiểm tra client và loại grant
       |
       v
Xác định quyền chủ thể và consent
       |
       v
Áp dụng policy theo resource/audience
       |
       v
granted_scopes = phần được phép theo tất cả điều kiện
       |
       v
Phát hành access token với granted_scopes
```

Tập quyền được cấp phải bị giới hạn bởi chính sách của issuer. Nếu client yêu cầu scope không được phép, authorization server xử lý theo giao thức và chính sách tương ứng: từ chối yêu cầu hoặc cấp tập con được phép khi profile cho phép. Không có quy tắc rằng mọi scope client yêu cầu đều phải được cấp.

### 5.3. Resource server vẫn kiểm tra scope

Resource server cần xác minh token được phát hành cho chính resource đó và scope có bao phủ hành động đang yêu cầu. Có scope=orders:read không đồng nghĩa được đọc mọi đơn hàng; quyền trên từng đơn hàng còn phụ thuộc tenant, chủ sở hữu, trạng thái và policy.

## 6. Không tin tenant hoặc tổ chức do client tự chọn

Một client có thể cần chọn tenant đang làm việc. Việc gửi tenant_id có thể hợp lệ như **một yêu cầu chọn ngữ cảnh**, nhưng issuer phải xác minh người dùng có quyền sử dụng tenant đó trước khi đưa tenant vào token.

Ví dụ request:

```json
{
  "requested_tenant": "tenant_17"
}
```

Issuer cần kiểm tra:

1. Chủ thể đã được xác thực và định danh từ phiên/grant đáng tin cậy.
2. tenant_17 tồn tại và thuộc phạm vi mà issuer quản lý.
3. Chủ thể hiện là thành viên hoặc được ủy quyền truy cập tenant đó.
4. Client/audience được phép sử dụng ngữ cảnh tenant này.
5. Các điều kiện bổ sung như trạng thái tenant, trạng thái tài khoản hoặc chính sách tổ chức.

Chỉ sau khi các kiểm tra đạt, issuer mới có thể phát hành claim:

```json
{
  "sub": "user_42",
  "aud": "https://api.orders.example.org",
  "tenant_id": "tenant_17",
  "scope": "orders:read"
}
```

API vẫn phải đối chiếu tenant trong token với tenant của tài nguyên. Không tin tenant_id do client gửi lại trong URL hoặc header để thay thế ngữ cảnh đã xác minh. Nếu API hỗ trợ chuyển tenant, đó phải là một thao tác có kiểm soát và có thể yêu cầu cấp token/ngữ cảnh mới.

## 7. Phân biệt profile người dùng với thuộc tính phân quyền

Nhiều hệ thống cho phép người dùng sửa tên hiển thị, ảnh đại diện, mô tả, ngôn ngữ hoặc một số metadata. Các trường này có thể hữu ích cho giao diện, nhưng không nên tự động trở thành nguồn cấp quyền.

Ví dụ một hồ sơ có:

```json
{
  "display_name": "An",
  "department": "Finance",
  "job_title": "Administrator",
  "custom_metadata": {
    "role": "admin"
  }
}
```

Nếu người dùng tự chỉnh sửa job_title hoặc custom_metadata.role, API không được suy ra người đó có quyền quản trị. Thuộc tính phân quyền phải được lấy từ nguồn có thẩm quyền riêng, chẳng hạn hệ thống quản lý vai trò, quan hệ tổ chức hoặc policy service.

Một số nguyên tắc:

- Tách dữ liệu người dùng tự khai báo khỏi dữ liệu do tổ chức quản trị.
- Không tự động map mọi custom metadata vào JWT claims.
- Không sử dụng tên hiển thị, email hoặc chức danh làm bằng chứng đặc quyền.
- Claim xác minh như email_verified chỉ do quy trình xác minh có thẩm quyền phát hành.
- Nếu một thuộc tính hồ sơ được dùng cho phân quyền, phải có quy trình quản trị, nguồn xác nhận, lịch sử thay đổi và kiểm tra quyền chỉnh sửa.

## 8. Tạo claims từ nguồn có thẩm quyền

Issuer nên xây dựng Claims Set theo từng bước, thay vì nhận một payload hoàn chỉnh từ bên yêu cầu:

### Bước 1 — Xác thực client và chủ thể

Xác định client nào đang yêu cầu token, grant nào được sử dụng và chủ thể nào đã được xác thực. Không nhận sub do client tùy ý gửi làm danh tính đã xác minh.

Trong luồng máy-gọi-máy, chủ thể có thể là client hoặc workload. Trong luồng có người dùng, subject cần được liên kết với kết quả xác thực người dùng và quy tắc ủy quyền. Không mặc định sub luôn là một con người.

### Bước 2 — Xác định resource và audience

Token phải được phát hành cho resource server dự kiến. Audience lấy từ resource được đăng ký hoặc xác định theo quy tắc đáng tin cậy của authorization server; không để client tự ghi một chuỗi aud tùy ý rồi issuer ký mà không kiểm tra.

### Bước 3 — Đánh giá quyền được yêu cầu

So sánh requested scopes với quyền của client, chủ thể, grant, consent và chính sách. Kết quả là tập quyền thực sự được cấp. Nếu không có căn cứ cấp một quyền, quyền đó không xuất hiện trong token.

### Bước 4 — Lấy thuộc tính từ nguồn có thẩm quyền

Ví dụ:

| Claim dự kiến | Nguồn giá trị phù hợp |
| --- | --- |
| sub | Danh tính đã được xác thực/định danh trong issuer |
| iss | Cấu hình issuer |
| aud | Resource đã được xác định và cho phép |
| exp, iat | Chính sách thời hạn và đồng hồ của issuer |
| scope | Kết quả đánh giá quyền/grant/consent |
| roles | Hệ thống quản lý vai trò có thẩm quyền |
| tenant_id | Kết quả xác minh membership và ngữ cảnh tenant |
| email_verified | Kết quả từ quy trình xác minh email |
| acr, amr | Kết quả xác thực theo giao thức và mức bảo đảm thực tế |

### Bước 5 — Tạo Claims Set theo allowlist

Chỉ thêm các claim đã được định nghĩa cho token profile. Kiểm tra kiểu, miền giá trị, kích thước và quan hệ giữa các claim. Không đưa các trường không biết hoặc trường đặc quyền do client gửi vào payload.

### Bước 6 — Ký bằng khóa thuộc issuer

Ký token bằng khóa riêng được quản lý an toàn. Khóa ký chỉ nên nằm trong ranh giới kiểm soát của issuer hoặc dịch vụ ký được ủy quyền. Không để client cung cấp khóa, thuật toán tùy ý hoặc tham số chọn khóa không được tin cậy.

## 9. Ví dụ luồng phát hành an toàn

Một client đã xác thực gửi yêu cầu cấp token:

```json
{
  "requested_scope": "orders:read orders:delete",
  "requested_tenant": "tenant_17"
}
```

Issuer thực hiện:

1. Xác minh client và grant hiện tại.
2. Lấy chủ thể từ ngữ cảnh xác thực đã được xác minh.
3. Kiểm tra chủ thể có membership hợp lệ trong tenant_17.
4. Kiểm tra client và chủ thể có thể nhận orders:read hay không.
5. Kiểm tra orders:delete có được cấp cho grant/resource này không.
6. Chọn tập scope được cấp, ví dụ chỉ orders:read.
7. Tạo Claims Set từ dữ liệu đáng tin cậy.

Kết quả minh họa:

```json
{
  "iss": "https://identity.example.org",
  "sub": "user_42",
  "aud": "https://api.orders.example.org",
  "iat": 1893456000,
  "exp": 1893456900,
  "tenant_id": "tenant_17",
  "scope": "orders:read"
}
```

Client không thể ép issuer đưa orders:delete vào token chỉ bằng cách yêu cầu nó. Nếu membership bị thu hồi hoặc quyền thay đổi, issuer cần áp dụng chính sách cập nhật/thu hồi phù hợp; claims đã ký không tự thay đổi theo dữ liệu nguồn.

## 10. Token exchange và claims từ một token khác

Trong kiến trúc nhiều dịch vụ, một dịch vụ có thể nhận token rồi yêu cầu đổi sang token khác cho một audience hoặc mục đích mới. Không được sao chép mù quáng claims của token đầu vào sang token mới.

Với token exchange hoặc delegation:

- Xác minh token đầu vào theo issuer, audience, chữ ký, thời gian, loại token và profile được chấp nhận.
- Xác định bên yêu cầu đổi token có quyền thực hiện hành động đó hay không.
- Giới hạn audience và scope của token mới theo quyền đã được cấp và chính sách delegation.
- Giữ rõ danh tính chủ thể và actor nếu giao thức/profile hỗ trợ; không gộp nhầm người dùng với dịch vụ đang hành động thay họ.
- Chỉ chuyển tiếp những claims cần thiết và được phép phát hành cho token đích.
- Không giữ lại claim đặc quyền của token đầu vào nếu token mới có mục đích hoặc audience khác.

RFC 8693 định nghĩa OAuth 2.0 Token Exchange. Các quan hệ actor/subject và delegation cần được diễn giải theo đặc tả, không tự thiết kế bằng cách sao chép tùy ý role, scope hay tenant_id.

## 11. Kiểm tra ở resource server

Issuer là nơi quyết định claim được phát hành, nhưng resource server vẫn cần xác minh độc lập:

1. Chỉ chấp nhận thuật toán và loại token đã cấu hình; không tin lựa chọn thuật toán do header tự đề xuất.
2. Chọn khóa từ nguồn tin cậy gắn với issuer đã cấu hình; không tải khóa từ URL tùy ý do token chỉ định.
3. Xác minh chữ ký hoặc cơ chế bảo vệ tương ứng trước khi dùng claims.
4. Kiểm tra iss, aud, thời hạn, loại token và các ràng buộc profile.
5. Kiểm tra kiểu và ngữ nghĩa của claims đặc quyền.
6. Áp dụng authorization trên endpoint và tài nguyên cụ thể.

Không dùng payload chỉ mới Base64URL decode làm dữ liệu đã xác thực. Không chấp nhận ID token hoặc token cho một API khác như access token chỉ vì chữ ký có vẻ hợp lệ. RFC 8725 khuyến nghị ràng buộc issuer/audience, kiểm tra thuật toán và phân biệt các loại JWT để tránh token confusion.

## 12. Các lớp phòng thủ khi phát hành claims

| Lớp | Biện pháp | Mục tiêu |
| --- | --- | --- |
| Đầu vào | Schema/allowlist request, từ chối trường đặc quyền không được hỗ trợ | Không để client điều khiển trực tiếp Claims Set |
| Danh tính | Xác thực client và subject từ nguồn tin cậy | Không giả mạo sub hoặc client |
| Ủy quyền | Đánh giá grant, consent, role, membership và policy | Chỉ cấp quyền có căn cứ |
| Tạo token | Claims allowlist theo profile, không mass assignment | Không đưa dữ liệu tùy ý vào payload |
| Ký token | Quản lý khóa, thuật toán và quyền ký | Bảo vệ nguồn phát hành |
| Tiêu thụ token | Xác minh issuer, audience, loại token, thời gian và chữ ký | Không tin token sai nguồn/sai mục đích |
| Phân quyền | Kiểm tra quyền trên tài nguyên và trạng thái hiện hành khi cần | Ngăn truy cập vượt phạm vi |
| Giám sát | Audit quyết định cấp quyền và thay đổi entitlement | Phát hiện cấp quyền bất thường |

### 12.1. Chính sách với trường client gửi thêm

Có hai cách xử lý phổ biến:

- **Reject unknown/reserved fields:** từ chối yêu cầu nếu client gửi role, is_admin, permissions hoặc trường không được API cấp token hỗ trợ. Cách này làm lỗi dễ phát hiện.
- **Ignore non-supported fields:** bỏ qua trường không được hỗ trợ, nhưng phải bảo đảm chúng không được merge vào token và không ảnh hưởng quyết định. Cần cân nhắc việc im lặng bỏ qua có che giấu lỗi client hay không.

Với API cấp token, từ chối rõ các trường đặc quyền do client tự gửi thường giúp phát hiện sớm hành vi bất thường. Dù chọn chính sách nào, issuer tuyệt đối không đưa các trường đó vào Claims Set nếu chưa tự xác minh nguồn và quyền phát hành.

### 12.2. Không cho user tự sửa metadata dùng để phân quyền

Nếu hệ thống hỗ trợ custom attributes, hãy phân biệt:

- User-editable attributes: tên hiển thị, ngôn ngữ, tùy chọn giao diện.
- Admin-managed attributes: phòng ban, trạng thái nhân viên, phân loại tổ chức.
- Authorization attributes: vai trò, quyền, entitlement, membership.

Những nhóm này có quyền chỉnh sửa và nguồn sự thật khác nhau. Chỉ các quy trình quản trị được ủy quyền mới được thay đổi thuộc tính có ảnh hưởng tới phân quyền.

## 13. Kiểm thử chống tự gán claims đặc quyền

Nên có các ca kiểm thử cụ thể ở cả issuer và resource server:

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Client gửi role=admin trong request cấp token | Từ chối trường không hỗ trợ hoặc bỏ qua; không đưa vào token |
| Client gửi is_admin=true | Không làm thay đổi quyền được cấp |
| Client yêu cầu scope vượt quyền | Từ chối hoặc chỉ cấp tập con được phép theo profile |
| Client gửi tenant_id mà chủ thể không thuộc tenant | Từ chối yêu cầu chọn tenant |
| Client gửi sub của người khác | Issuer không dùng giá trị đó làm chủ thể đã xác thực |
| User sửa custom metadata thành role=admin | Không thay đổi entitlement/role có thẩm quyền |
| Token đầu vào chứa claim đặc quyền từ issuer không được tin | Từ chối token đầu vào hoặc không chấp nhận claim |
| Token hợp lệ về chữ ký nhưng sai audience | Resource server từ chối |
| Token có claim đặc quyền sai kiểu hoặc sai profile | Từ chối theo schema/profile |
| Token có scope hợp lệ nhưng truy cập tài nguyên tenant khác | Từ chối theo authorization trên tài nguyên |
| Client gửi trường lạ nhằm ghi đè claim issuer | Không có trường nào được ghi đè trong Claims Set |

Kiểm thử nên xác minh cả payload thực tế của token được phát hành, không chỉ HTTP response. Một response báo thành công không chứng minh token không chứa claim đặc quyền ngoài dự kiến.

## 14. Audit và xử lý khi phát hiện cấp sai claim

Issuer nên ghi lại sự kiện phát hành token ở mức đủ để điều tra:

- Client, subject và issuer liên quan.
- Audience/resource và loại grant.
- Tập scope/entitlement thực sự được cấp.
- Quyết định policy và phiên bản cấu hình áp dụng.
- Mã tương quan, thời điểm và định danh token như jti nếu được sử dụng.

Không ghi toàn bộ token hoặc bí mật ký vào log. Khi phát hiện issuer đã ký claims đặc quyền sai:

1. Ngăn phát hành token sai tiếp tục xảy ra bằng cách sửa quy tắc tạo claims hoặc thu hồi luồng cấp quyền.
2. Xác định phạm vi token đã phát hành, issuer, audience, client, subject và thời gian ảnh hưởng.
3. Thu hồi token/phiên hoặc vô hiệu hóa quyền theo cơ chế hệ thống hỗ trợ; chỉ chờ exp nếu rủi ro cho phép.
4. Kiểm tra audit log để xác định yêu cầu nào đã được chấp nhận dựa trên claim sai.
5. Khắc phục dữ liệu entitlement nguồn và kiểm thử lại các ranh giới tin cậy.
6. Đánh giá việc xoay khóa nếu khóa ký bị lộ hoặc bị sử dụng trái phép; lỗi logic cấp claim không tự động có nghĩa khóa đã bị xâm phạm.

## 15. Tình huống tự kiểm tra

Một người dùng bình thường đăng nhập thành công. Client gửi yêu cầu cấp access token:

```json
{
  "requested_scope": "orders:read",
  "role": "admin",
  "is_admin": true,
  "tenant_id": "tenant_99"
}
```

Hệ thống xác thực cho biết người dùng chỉ là nhân viên đọc đơn hàng của tenant_17, không thuộc tenant_99 và không có quyền quản trị.

**Câu hỏi 1:** Issuer có được ký nguyên các trường client gửi vì request đã được xác thực không?

**Trả lời:** Không. Xác thực request chỉ xác nhận ai gửi yêu cầu; nó không chứng minh các khẳng định đặc quyền trong body là đúng. Issuer phải lấy subject, vai trò và membership từ nguồn có thẩm quyền.

**Câu hỏi 2:** Claims Set nên chứa gì?

**Trả lời:** Issuer có thể phát hành sub của người dùng đã xác thực, aud của API hợp lệ, tenant_id=tenant_17 sau khi kiểm tra membership, và scope orders:read nếu grant/policy cho phép. Các trường role=admin, is_admin=true và tenant_99 do client gửi không được chấp nhận làm quyền hoặc ngữ cảnh đã xác minh.

**Câu hỏi 3:** Nếu token mới được ký đúng bằng khóa của issuer, resource server có thể tin is_admin=true không?

**Trả lời:** Chỉ khi issuer có hợp đồng và quy trình có thẩm quyền để phát hành claim đó, và resource server đã xác minh đúng issuer, audience, token profile. Chữ ký tự nó không chứng minh issuer đã tạo claim từ nguồn đúng; trách nhiệm bảo đảm điều đó nằm ở quy trình phát hành.

## 16. Ghi nhớ

Không để bên yêu cầu tự gán claims đặc quyền. Client có thể yêu cầu scope hoặc chọn tenant, nhưng issuer phải xác minh quyền và tự tạo giá trị claims từ danh tính, grant, consent, membership và policy có thẩm quyền. Dùng allowlist theo token profile, tránh mass assignment, tách metadata người dùng khỏi thuộc tính phân quyền và giới hạn claims được chuyển tiếp giữa các token.

Resource server phải xác minh đúng issuer, audience, loại token, chữ ký và thời hạn trước khi sử dụng claims; sau đó vẫn kiểm tra quyền trên tài nguyên cụ thể. **Token được ký đúng chỉ đáng tin khi quy trình phát hành cũng đáng tin.**

## Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): cấu trúc JWT và JWT Claims Set.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): thực hành xác minh thuật toán, issuer, audience và phân biệt loại token.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): authorization request, scope và quyền quyết định của authorization server.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): trao đổi token và ngữ cảnh subject/actor.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): hồ sơ JWT access token trong OAuth 2.0.
