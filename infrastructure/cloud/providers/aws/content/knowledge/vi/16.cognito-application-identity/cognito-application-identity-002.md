# Thiết kế user attribute, group và app client

> **Chương:** Danh tính ứng dụng với Cognito  
> **Module:** CLOUD_PROVIDERS_AWS — khám phá AWS qua Region/AZ, IAM, VPC, tính toán, lưu trữ, cơ sở dữ liệu, tích hợp và serverless; rèn năng lực chọn dịch vụ, bảo mật, giám sát, phục hồi và quản trị chi phí.

## Mục tiêu học tập

Khi xây dựng một nền tảng học trực tuyến, cổng khách hàng hoặc ứng dụng SaaS, đăng nhập là một phần nhỏ của quản lý danh tính. Hệ thống cần biết **người dùng là ai**, thuộc nhóm nào, ứng dụng nào được xem/sửa dữ liệu hồ sơ và các API được phép thực hiện thao tác gì. Trong **Amazon Cognito User Pools**, ba đối tượng thiết kế chính là:

- **User attributes:** thông tin của mỗi tài khoản, gồm thuộc tính chuẩn, thuộc tính tự định nghĩa và các trường có ý nghĩa xác minh.
- **Groups:** tập người dùng có đặc điểm hoặc vai trò ứng dụng tương tự, xuất hiện trong token và có thể gắn IAM role cho tình huống tích hợp Identity Pool.
- **App clients:** cấu hình riêng cho ứng dụng mobile, SPA, web backend hoặc máy-máy; kiểm soát flow xác thực, OAuth scopes, callback URLs, token lifetimes và **quyền đọc/ghi thuộc tính**.

Bài học này phân biệt **authentication** (xác thực), **authorization** (cấp quyền) và **application data ownership** (quản trị dữ liệu nghiệp vụ), tránh cách triển khai nguy hiểm như dùng một thuộc tính do người dùng tự sửa để xác định quyền quản trị.

Sau bài, bạn có thể:

1. Thiết kế schema chuẩn và custom attributes theo nguyên tắc dữ liệu tối thiểu, có tính đến các lựa chọn khó sửa sau khi tạo user pool.
2. So sánh username, alias email/phone, `preferred_username`, `sub` và xác minh `email_verified`.
3. Xác định khi nào dùng group, ý nghĩa `Precedence`, các claim `cognito:groups` và `cognito:preferred_role`.
4. Tạo bản thiết kế app clients riêng cho SPA, mobile, web server và machine-to-machine, chọn public/confidential và OAuth flow đúng.
5. Tách quyền `ReadAttributes`/`WriteAttributes`, scopes, resource servers và quyền nghiệp vụ ở backend.
6. Đọc và xác minh ID/access tokens, xử lý federation/attribute mapping mà không tạo lỗ hổng phân quyền.
7. Kiểm tra user pool, groups và app clients bằng AWS CLI **chỉ đọc**, không trích xuất client secret hoặc dữ liệu cá nhân.
8. Lập kế hoạch bảo mật, vận hành, kiểm toán, giới hạn, chi phí và sự cố định danh.

## 1. Đặt User Pools vào kiến trúc ứng dụng

### 1.1. User Pool và Identity Pool khác nhau

**Amazon Cognito User Pool** là thư mục người dùng và nhà cung cấp danh tính (IdP) cho ứng dụng. Nó có thể quản lý đăng ký, đăng nhập, khôi phục tài khoản, xác thực đa yếu tố, liên kết với IdP doanh nghiệp/xã hội và phát hành token theo giao thức được hỗ trợ.

**Amazon Cognito Identity Pool** (Federated Identities) là thành phần tùy chọn để **đổi danh tính đã xác thực thành AWS credentials tạm thời** theo cấu hình IAM role và trust policy. Nhiều ứng dụng chỉ cần User Pool + backend API, **không cần Identity Pool**.

| Nhu cầu | Thành phần phù hợp | Lưu ý |
|---|---|---|
| Đăng ký và đăng nhập người dùng cuối | Cognito User Pool | Password/passkey/MFA/federation theo tính năng và cấu hình |
| Phát ID token và access token cho web/mobile | User Pool app client | Token phải được xác minh ở resource server |
| Phân quyền API `/courses`, `/reports` | Backend/API Gateway + scopes/groups/logic ứng dụng | Không coi group là thay thế hoàn toàn authorization |
| Cấp quyền truy cập trực tiếp AWS S3 bằng STS credentials | Identity Pool theo thiết kế phù hợp | Kiểm tra IAM role mappings và phạm vi tài nguyên |
| Phân quyền nhà phát triển vận hành Cognito | AWS IAM | IAM administration khác user authentication |
| Lưu quan hệ khóa học/đơn hàng/progress | RDS/DynamoDB hoặc data store ứng dụng | Không biến User Pool thành database nghiệp vụ |

### 1.2. Sơ đồ người dùng tới API

~~~mermaid
flowchart LR
    U[Học viên / Giáo viên] --> APP[Web SPA / Mobile / Server Web]
    APP --> CL[App client phù hợp]
    CL --> UP[(Cognito User Pool)]
    UP -->|ID token + access token| APP
    APP -->|Bearer access token| API[API Gateway / Backend]
    API --> AUTH[Verify JWT issuer, signature, token_use, app client + scope/group]
    AUTH --> DATA[(RDS / DynamoDB nghiệp vụ)]
    UP -. Groups / attributes .-> AUTH
    IDP[Google / OIDC / SAML IdP] --> UP
    IP[Identity Pool: tùy chọn] -. AWS temporary credentials .-> APP
    UP -. Identity token .-> IP
~~~

**Một user pool có thể có nhiều app clients**. Cùng một người dùng có thể đăng nhập vào website học viên và ứng dụng mobile dùng các client IDs khác nhau. Thuộc tính user **được lưu ở cấp user pool**, còn cách từng app client được xem/sửa thuộc tính có thể khác.

### 1.3. Xác thực khác cấp quyền

Ví dụ giáo viên `teacher-001` đăng nhập thành công và nhận access token. Điều này mới chứng minh danh tính/token theo những điều kiện đã kiểm tra. Để cho phép `POST /courses/123/grade`, backend còn phải xác minh:

1. Token hợp lệ, không hết hạn, đúng issuer và đúng mục đích.
2. Client/scopes/groups được phép thực hiện lớp thao tác tương ứng.
3. Người dùng thực sự được gán **giảng dạy khóa học 123** trong cơ sở dữ liệu nghiệp vụ.
4. Các chính sách về trạng thái khóa học, tenant và audit đều được thỏa mãn.

**`cognito:groups=["teachers"]` không tự có nghĩa giáo viên đó được sửa điểm của mọi học viên trên mọi khóa học.**

## 2. User attributes: phân loại trước khi thiết kế schema

### 2.1. Thuộc tính chuẩn và thuộc tính tùy chỉnh

Cognito hỗ trợ các **standard attributes** theo OIDC và các thuộc tính khác dành cho user directory, ví dụ:

| Attribute | Vai trò | Có dùng làm khóa nghiệp vụ chính? |
|---|---|---|
| `sub` | Định danh ổn định, duy nhất trong user pool | **Nên** dùng làm khóa danh tính nội bộ (kèm user pool/issuer khi đa pool) |
| `username` | Tên người dùng do cơ chế user pool quản lý | Không nên thay `sub` trong mọi mô hình đăng nhập |
| `email` | Địa chỉ email liên hệ/đăng nhập nếu cấu hình | **Không**; có thể đổi, cần xác minh |
| `email_verified` | Trạng thái xác minh email | Không phải vai trò/quyền ứng dụng |
| `phone_number` | Số điện thoại theo định dạng hỗ trợ | Không; có thể thay đổi và tái sử dụng ngoài đời thực |
| `phone_number_verified` | Trạng thái xác minh số điện thoại | Không cấp quyền nghiệp vụ |
| `preferred_username` | Tên hiển thị hoặc alias theo cấu hình | Không; có thể thay đổi |
| `given_name`, `family_name`, `name` | Thông tin hồ sơ hiển thị | Không |
| `locale`, `zoneinfo` | Ưu tiên ngôn ngữ/múi giờ | Không |
| `custom:tenantId` | Thuộc tính tự định nghĩa nếu cần một tenant hint | Chỉ dùng cho authorization khi nguồn ghi đáng tin và backend xác minh quan hệ |

**`sub`** là lựa chọn chính để liên kết hồ sơ với các bản ghi nghiệp vụ. Cognito phát hành định danh này với giá trị **không đổi trong cùng user pool**; đừng ép parse định dạng UUID cố định. Nếu kết hợp nhiều user pools, dùng khóa logic như **`(issuer, sub)`** thay vì giả định `sub` toàn cục.

### 2.2. Bốn câu hỏi cho mỗi attribute

Trước khi thêm một trường, ghi lại:

1. **Mục đích:** trường này cần cho sign-in, gửi thông báo, giao diện hay kiểm soát quyền?
2. **Nguồn dữ liệu đáng tin:** người dùng, bộ phận support, backend quản trị, hệ thống HR hay IdP ngoài?
3. **Ai đọc/ghi:** SPA, mobile, BFF, admin portal, background job?
4. **Vòng đời:** trường có đổi được không, cần đồng bộ, có dữ liệu nhạy cảm không, retention/xóa dữ liệu ra sao?

Một bảng thiết kế ví dụ:

| Dữ liệu | Lưu ở đâu | Nguồn ghi | Client được đọc? | Client được tự sửa? |
|---|---|---|---|---|
| `sub` | Cognito | Cognito cấp | Dùng làm identity key | Không |
| `email` | Cognito | Người dùng + xác minh | Có theo nhu cầu | Có theo quy trình xác minh |
| `given_name` | Cognito | Người dùng | Có | Có |
| `custom:tenantId` | Cognito hoặc data store nghiệp vụ | Backend quản trị đáng tin | Có thể, nếu cần hiển thị | **Không** |
| Vai trò giáo viên của lớp 123 | CSDL ứng dụng | Hệ thống nghiệp vụ | Qua API đã phân quyền | **Không** |
| Mật khẩu | Cognito auth flow | Người dùng qua giao thức an toàn | Không trả plaintext | Không qua profile update thường |
| Payment card / private medical records | Dịch vụ chuyên biệt theo quy định | Quy trình được duyệt | Không mặc định | Không lưu ở custom attribute |

### 2.3. Không dùng User Pool làm nơi lưu mọi dữ liệu

Custom attributes có giới hạn schema và kích thước, không phù hợp để chứa:

- Danh sách lớp học dài/thường xuyên thay đổi;
- Quan hệ nhiều-nhiều user–group–resource;
- Quyền chi tiết trên hàng nghìn đối tượng;
- Ảnh/biên bản/dữ liệu tuân thủ đặc biệt;
- Secret, token OAuth của hệ thống khác hoặc access keys.

Cognito nên giữ **identity profile tối thiểu** và những thuộc tính cần cho luồng xác thực, còn RDS/DynamoDB/S3 giữ dữ liệu nghiệp vụ với vòng đời/quyền riêng.

## 3. Username, sign-in aliases và xác minh liên hệ

### 3.1. Ba khái niệm thường bị nhầm

| Khái niệm | Giải thích | Có ổn định? |
|---|---|---|
| `sub` | ID định danh do Cognito cấp | Ổn định trong pool |
| `username` | Username nội bộ theo cấu hình user pool | Được Cognito quản lý, không coi như email mutable |
| `email` / `phone_number` | Thuộc tính liên hệ và có thể là sign-in identifier | Có thể thay đổi |
| `preferred_username` | Tên người dùng muốn hiển thị/alias nếu được bật | Có thể thay đổi |

Không tạo khóa ngoại ứng dụng theo `email`. Email có thể đổi, mất quyền sở hữu hoặc được người khác đăng ký về sau; nếu dùng làm khóa nghiệp vụ sẽ gây khó khăn trong việc hợp nhất/đổi email.

### 3.2. Username attributes và alias attributes

Tại thời điểm tạo user pool, bạn chọn chiến lược sign-in:

- **Username attributes:** cho phép dùng email, số điện thoại hoặc cả hai như username theo cấu hình.
- **Alias attributes:** giữ username ổn định, cho phép sign-in bằng một hoặc nhiều alias như email/phone/`preferred_username` sau khi đáp ứng điều kiện xác minh.

Hai mô hình có **semantics khác về tính duy nhất và xác minh**. Với username attributes, email/phone dùng để sign-up có ràng buộc duy nhất theo cấu hình. Với alias, email/phone có thể tồn tại ở nhiều profile trong các trạng thái khác nhau, nhưng **alias đã xác minh** chỉ thuộc một user để dùng sign-in ở thời điểm tương ứng.

**Ràng buộc quan trọng:** các tùy chọn sign-in identifiers, username case sensitivity và required standard attributes thuộc nhóm **không thể tùy tiện sửa sau khi tạo pool**. Nếu thiết kế sai, thường phải tạo user pool mới và lập kế hoạch migration.

### 3.3. Ví dụ chọn theo sản phẩm

| Sản phẩm | Lựa chọn khởi đầu | Tại sao? |
|---|---|---|
| Ứng dụng học viên phổ thông | Email làm sign-in identifier | Dễ sử dụng; cần email delivery/verification |
| Cổng nhân viên có mã định danh | Username + email alias | Mã nhân viên/username ổn định, email vẫn là đường đăng nhập |
| Mobile dùng phone OTP | Phone sign-in theo hỗ trợ | Cần SMS/chi phí/khả năng chống SIM swap |
| SaaS liên kết nhiều IdP | Federation + `sub`/identity linking | Không gán một người chỉ qua so email chưa xác minh |
| Marketplace cần đổi tên hiển thị | Dùng `preferred_username`/profile name | Tách tên hiển thị khỏi khóa định danh |

### 3.4. Email verified không tương đương quyền sở hữu tài khoản mãi mãi

`email_verified=true` chứng minh một quy trình kiểm tra email theo chính sách tại một thời điểm. Nó:

- Không chứng minh người dùng là giáo viên hay nhân viên hợp lệ.
- Không chứng minh cùng một người khi tài khoản email đã đổi chủ.
- Không được phép được client tự gán để vượt xác minh.
- Không thay thế MFA với thao tác rủi ro.

Khi cho phép đổi email hoặc phone, hãy cấu hình **verification before update** theo nhu cầu bảo mật. Với tài khoản liên quan thanh toán/admin, có thể cần xác thực lại trước thao tác nhạy cảm.

## 4. Custom attributes: loại dữ liệu, mutability và rủi ro thay schema

### 4.1. Quy tắc tạo custom attribute

Cognito cho phép thêm **custom attributes** vào user pool. Những điểm cần xác minh:

- Tên thuộc tính khi sử dụng trong code/token có tiền tố **`custom:`**, ví dụ `custom:tenantId`.
- Có các kiểu như String, Number, Boolean và DateTime theo API/hỗ trợ; dữ liệu được lưu/truyền như **chuỗi** khi ứng dụng thao tác với Cognito và trong ID token.
- Mỗi user pool có quota số custom attributes (AWS documentation hiện nêu tối đa 50); không dùng như nơi chứa mô hình schema thay đổi liên tục.
- Custom attribute **không thể đánh dấu required** cho người dùng theo cách required standard attributes.
- Sau khi thêm vào pool, custom attribute **không thể xóa, đổi tên, đổi kiểu, sửa mutability hoặc constraints**.
- Một custom attribute có thể **mutable** hoặc **immutable**; immutable chỉ được gán trong quá trình tạo user theo khả năng dịch vụ.
- Legacy developer attributes với tiền tố `dev:` không nên là lựa chọn mặc định cho thiết kế mới; AWS khuyến nghị cơ chế app client attribute permissions.

**Ví dụ JSON khai báo schema (chỉ minh họa phần fields):**

~~~json
{
  "Name": "tenantId",
  "AttributeDataType": "String",
  "DeveloperOnlyAttribute": false,
  "Mutable": false,
  "Required": false,
  "StringAttributeConstraints": {
    "MinLength": "1",
    "MaxLength": "64"
  }
}
~~~

Trong API khai báo schema, `Name` thường là **tên chưa có tiền tố** `custom:`. Khi đọc/ghi user attributes, dùng `custom:tenantId`. Giới hạn tên theo quy tắc AWS hiện hành; chọn tên đơn giản chỉ gồm ký tự ASCII, chữ, số, gạch dưới/gạch ngang theo regex được hỗ trợ.

### 4.2. Mutable hay immutable?

| Thiết kế | Ví dụ | Ưu điểm | Rủi ro |
|---|---|---|---|
| Mutable | `custom:uiTheme` | Người dùng đổi được khi client có WriteAttributes | Không phù hợp làm bằng chứng quyền |
| Immutable | `custom:registrationSource` | Ghi một lần lúc tạo account | Không sửa được khi dữ liệu đã sai |
| Mutable nhưng admin-only write | `custom:tenantId` nếu cần di chuyển tenant | Backend quản trị có thể sửa qua quy trình duyệt | Phải chặn user tự ghi từ **mọi app clients** |
| Không đưa vào Cognito | `courseMemberships` | Truy vấn/quản lý quyền nghiệp vụ linh hoạt | Cần API/data store riêng |

**Chọn immutable không tự bảo đảm tính đáng tin** nếu bạn cho phép người đăng ký tự chọn giá trị tại SignUp. Ví dụ `custom:isAdmin` immutable nhưng app client ghi được khi sign-up vẫn là thiết kế nguy hiểm: người dùng có thể tự gán `"true"` trong quá trình tạo profile. Quyền quản trị phải do luồng provisioning có thẩm quyền xác định.

### 4.3. Không thể dựa vào độ bất biến để bỏ qua migration

Giả sử sau một năm, cấu trúc `tenantId` chuyển từ UUID sang mã doanh nghiệp nhiều vùng. Vì không đổi được kiểu/constraints của custom attribute đã tạo, bạn có thể phải:

1. Tạo attribute mới như `custom:tenantKeyV2` nếu quota và thiết kế cho phép.
2. Viết chuyển đổi/bổ sung dữ liệu bằng API/IaC có quyền, không tự mở rộng cho client.
3. Cho các versions ứng dụng đọc cả trường cũ/mới trong cửa sổ migration.
4. Thay logic backend và audit.
5. Giữ trường cũ không dùng nữa vì **không thể xóa schema custom attribute**.

Vì vậy, chỉ thêm custom attribute khi có **lý do identity rõ ràng và data contract dài hạn**.

## 5. App client attribute permissions: đọc và ghi không giống OAuth scopes

### 5.1. Vì sao mỗi app client cần riêng quyền thuộc tính?

Một user pool có thể phục vụ ba ứng dụng:

~~~text
User Pool: school-users
├── App client: student-spa
│   ├── Read: sub, email, email_verified, given_name, custom:tenantId
│   └── Write: email, given_name (theo luồng xác minh)
├── App client: teacher-portal
│   ├── Read: hồ sơ cần hiển thị theo policy
│   └── Write: tên hiển thị, thông tin hỗ trợ
└── App client: admin-bff
    ├── Read: thuộc tính theo nhu cầu quản trị
    └── Write: quản trị theo backend access controls
~~~

Một app client **không tạo bản sao riêng** của user. Những thay đổi hồ sơ trong cùng pool có thể xuất hiện trong tokens/`GetUser` của app clients khác nếu quyền đọc/claims cho phép.

### 5.2. ReadAttributes và WriteAttributes

| Thuộc tính app client | Tác động | Rủi ro thiết kế |
|---|---|---|
| `ReadAttributes` | Quyền app client đọc profile attributes và những claim tương ứng trong ID token | Lộ thông tin quá mức hoặc đưa PII vào logs |
| `WriteAttributes` | App có thể thay đổi các thuộc tính được cho phép qua API người dùng thích hợp | Tự nâng quyền nếu cho ghi `custom:role`/`custom:tenantId` |
| `AllowedOAuthScopes` | Những OAuth scopes app được phép xin | Không thay thế Read/WriteAttributes |
| `ExplicitAuthFlows` | Cho phép những luồng Cognito API authentication cụ thể | Mở flow không cần thiết làm tăng bề mặt tấn công |
| `CallbackURLs`, `LogoutURLs` | Đường redirect trong OAuth/managed login | Redirect sai domain có thể gây lộ authorization code hoặc session |
| `GenerateSecret` / client secret | Xác thực confidential client theo chế độ hỗ trợ | Không được nhúng secret vào SPA/mobile |
| `AccessTokenValidity`, `IdTokenValidity`, `RefreshTokenValidity` | Thời hạn các tokens | Cân bằng trải nghiệm và cửa sổ rủi ro |

**Cảnh báo về giá trị mặc định:** với các API tạo app client, **bỏ qua `ReadAttributes`/`WriteAttributes` không có nghĩa là từ chối tất cả**. Tài liệu AWS mô tả mặc định cho phép tập thuộc tính chuẩn, và trong một số cấu hình cho phép truy cập nhiều thuộc tính hơn bạn dự tính. API `DescribeUserPoolClient` cũng có thể **không trả trường** khi đang dùng permissions mặc định. Vì vậy cần **cấu hình rõ ràng quyền tối thiểu**, và audit bằng cấu hình hiệu lực thay vì suy luận trường rỗng là an toàn.

### 5.3. Quy tắc đặc biệt cho thuộc tính quyết định quyền

Giả sử hệ thống có `custom:tenantId` và `custom:roleLevel`. Nếu app student cho phép:

~~~text
WriteAttributes = ["email", "custom:tenantId", "custom:roleLevel"]
~~~

thì người dùng có thể gọi API cập nhật profile với những giá trị do họ chọn, làm sai logic tenant/role **nếu backend tin các claims đó**.

Thiết kế an toàn hơn:

~~~text
Student SPA:
  ReadAttributes  = ["email", "email_verified", "given_name",
                     "custom:tenantId"]
  WriteAttributes = ["email", "given_name"]

Admin provisioning:
  Ghi tenant/role qua một API backend đã xác thực, phân quyền,
  validate source + audit và sử dụng IAM administrative APIs theo chính sách.
~~~

**Rà soát tất cả app clients trong cùng user pool**, không chỉ client đang dùng. Một client thử nghiệm bị bỏ quên có quyền write rộng có thể làm thay đổi thuộc tính mà client production dùng để ra quyết định.

### 5.4. Attribute read permission và ID token claims

Cognito có thể đưa các standard/custom attributes có quyền đọc vào **ID token** tùy flow, scopes và cấu hình; `GetUser` có thể trả profile theo quyền của app client. Không dùng `ID token` như một container để truyền toàn bộ hồ sơ, vì:

- Token đi qua client và có thể xuất hiện ở log nếu xử lý sai;
- Token có thời hạn, các thay đổi attribute/group sau đó không tự sửa token đã phát;
- PII trong JWT có thể bị đọc bởi bên giữ token dù payload được mã hóa? **JWT ký số thường không được mã hóa**, nên payload có thể giải mã base64url;
- Quyền đọc thuộc tính khác với quyền gọi API nghiệp vụ.

Khi cần dữ liệu hồ sơ đầy đủ, cân nhắc backend `/me` có authorization, chỉ trả dữ liệu cần cho UI.

## 6. Cognito groups: vai trò, membership và precedence

### 6.1. Group giải quyết nhu cầu nào?

Một nhóm là tập user pool users, ví dụ:

~~~text
students
teachers
content-reviewers
school-admins
support-agents
~~~

Mỗi user có thể thuộc **nhiều groups**. Group membership có thể xuất hiện trong claim `cognito:groups` của **access token** và **ID token**, tùy token type/cấu hình, và ứng dụng có thể sử dụng sau khi đã xác minh token.

~~~mermaid
flowchart LR
    U[User sub=abc] --> G1[Group students]
    U --> G2[Group teachers]
    G1 --> TOK[JWT cognito:groups]
    G2 --> TOK
    TOK --> API[Backend authz]
    API --> DB[(Course membership database)]
    DB --> DEC[Quyết định cho từng tài nguyên]
~~~

Group là cơ chế phân loại **mức rộng**. Không tạo một group cho mỗi hàng trong bảng điểm hoặc một group cho từng khóa học trong hệ thống lớn nếu authorization dựa vào hàng triệu quan hệ. Quan hệ chi tiết nên nằm ở dữ liệu nghiệp vụ và được backend kiểm tra.

### 6.2. Group name và authorization policy

Ví dụ:

| Group | Quyền rộng có thể đề xuất | Vẫn phải kiểm tra thêm |
|---|---|---|
| `students` | Xem khóa học đã đăng ký | Student có enrollment hợp lệ |
| `teachers` | Quản lý bài học lớp được giao | Teacher có assignment với course/tenant |
| `content-reviewers` | Duyệt nội dung trong phạm vi phân công | Nội dung và workflow state |
| `school-admins` | Quản trị một tenant cụ thể | Tenant ID, vai trò đang hiệu lực, audit |
| `support-agents` | Truy cập hỗ trợ theo ticket | Lý do truy cập, ticket scope, PII redaction |

Đừng chỉ kiểm tra `"school-admins" in cognito:groups` rồi cho phép sửa mọi tenant. Trong ứng dụng multi-tenant, nhóm cấp cao vẫn cần **tenant boundary** và xác minh quyền ở backend.

### 6.3. Precedence và preferred IAM role

Khi một user thuộc nhiều groups, các groups có thể có **`Precedence`** và `RoleArn` để phục vụ việc chọn IAM role liên quan đến **Identity Pool role mapping**:

- `Precedence=0` có độ ưu tiên cao nhất; số **nhỏ hơn** được ưu tiên hơn số lớn hơn.
- Group có precedence nhỏ nhất thường quyết định claim `cognito:preferred_role` trong **ID token** khi có role phù hợp.
- Nếu các groups cùng precedence và cùng role ARN, role đó có thể được chọn.
- Nếu cùng precedence nhưng **role ARN khác nhau**, `cognito:preferred_role` có thể không được đặt; identity pool có cơ chế `AmbiguousRoleResolution`/`CustomRoleArn` tương ứng.
- `cognito:roles` là các IAM roles gắn với nhóm, **không có nghĩa app backend tự được IAM cho phép**.
- Group **không hỗ trợ lồng nhau**; số groups chịu service quotas.

Ví dụ:

~~~text
User belongs to:
  students:    precedence=20, role=arn:...:role/StudentFilesRole
  teachers:    precedence=10, role=arn:...:role/TeacherFilesRole

Expected preferred role:
  TeacherFilesRole (theo priority 10)
~~~

**Không dùng group precedence như thứ tự quyền ứng dụng**. Precedence chủ yếu hỗ trợ lựa chọn IAM role khi sử dụng Cognito Identity Pools. Trong backend API, group membership có thể được xử lý bằng **policy logic riêng**, ví dụ deny-by-default, role hierarchy và tenant-scoped permissions.

### 6.4. Khi nào không gắn IAM role vào group?

Nếu mọi thao tác trên AWS resources đều đi qua **backend trên Lambda/EC2/ECS**, backend có **execution role riêng**, và end-user không cần gọi trực tiếp AWS APIs, thì bạn có thể chỉ dùng group để mô tả vai trò ứng dụng, **không cần gắn IAM role cho mỗi group**.

Chỉ khi ứng dụng cần cấp AWS temporary credentials trực tiếp qua **Identity Pool** mới xem xét `RoleArn`, role mapping, IAM trust policy, principal tags và resource permissions phù hợp. Đây là mô hình khác với cấp quyền REST API.

### 6.5. Quản lý membership là thao tác đặc quyền

**Không cho người dùng thông thường tự thêm mình vào nhóm admin.** Thao tác như `AdminAddUserToGroup` là API quản trị, phải được thực hiện bởi IAM principal/backend đã xác thực và ủy quyền theo nghiệp vụ.

Một workflow thêm giáo viên:

1. Nhà trường xác minh danh tính và hợp đồng.
2. Nhân sự quản trị xác nhận `sub`/user profile đúng.
3. Backend admin kiểm tra quyền người thao tác.
4. Admin API thêm group `teachers` và ghi audit.
5. Backend cập nhật assignment chi tiết tới từng course.
6. Người dùng đăng nhập/refresh token theo chính sách để nhận claims mới, sau đó backend vẫn đối chiếu dữ liệu quyền thật.

## 7. Thiết kế app clients theo loại ứng dụng

### 7.1. Public client và confidential client

| Loại | Ví dụ | Client secret? | OAuth flow thường đề xuất |
|---|---|---|---|
| **Public client** | SPA chạy trong browser | **Không** | Authorization Code + **PKCE** |
| **Public client** | iOS/Android app | **Không** | Authorization Code + PKCE, system browser |
| **Confidential client** | Server-rendered web app/BFF | Có thể có, giữ server-side | Authorization Code, xác thực client ở token endpoint |
| **Confidential client** | Machine-to-machine backend | **Có** | `client_credentials` + custom scopes |
| **Backend proxy/BFF** | SPA gọi BFF, BFF giữ session | BFF có thể dùng confidential client | Code flow, cookie HttpOnly/Secure/SameSite theo thiết kế |

**Client ID không phải secret**; nó được phép xuất hiện trong mã client. **Client secret là dữ liệu bí mật**, không nhúng vào bundle JS, mobile APK/IPA hay repository công khai.

### 7.2. Một User Pool, nhiều clients

Ví dụ:

~~~text
User Pool: school-users
├── student-spa (public)
│   ├── Code + PKCE
│   ├── Callback: https://learn.example.com/auth/callback
│   └── Scopes: openid email profile school-api/courses.read
├── teacher-web (confidential BFF)
│   ├── Code flow / server-side secret
│   ├── Callback: https://teacher.example.com/oauth/callback
│   └── Scopes: openid email school-api/grades.write
└── report-service (confidential M2M)
    ├── client_credentials
    └── Scope: school-api/reports.generate
~~~

Tách app clients giúp áp chính sách callback, token TTL, auth flows và attribute permissions phù hợp với từng ứng dụng. Nhưng **client tách biệt không tạo tenant isolation tuyệt đối** nếu cùng một user pool và API authorization thiếu ràng buộc nghiệp vụ.

### 7.3. Những settings nên quyết định khi thiết kế

| Setting | Quyết định thiết kế | Rủi ro nếu cấu hình sai |
|---|---|---|
| `ClientName` | Tên môi trường + ứng dụng + loại client | Khó phân biệt prod/dev |
| `GenerateSecret` | Chỉ dành cho confidential client theo flow | Secret lộ trong SPA/mobile hoặc M2M không được phép |
| `AllowedOAuthFlowsUserPoolClient` | Bật OAuth flow cho user pool client | OAuth config không hoạt động |
| `AllowedOAuthFlows` | `code`, `client_credentials` ... theo nhu cầu | Bật implicit flow không cần thiết |
| `AllowedOAuthScopes` | Tối thiểu cho app | Token xin scope rộng hoặc thiếu scope |
| `CallbackURLs` | Exact HTTPS redirect URIs | Open redirect/code leakage/invalid redirect |
| `LogoutURLs` | Exact post-logout paths | Điều hướng sai hoặc bị lợi dụng |
| `SupportedIdentityProviders` | Cognito và IdPs được phép | Cho sign-in từ IdP không dự kiến |
| `ReadAttributes` / `WriteAttributes` | Thông tin app được xem/sửa | Lộ PII hoặc privilege escalation |
| `ExplicitAuthFlows` | Các API authentication flows trực tiếp | Mở password-based flow không cần |
| Token validity và refresh rotation | Session duration, re-auth, revocation | Token sống quá lâu hoặc app refresh lỗi |
| `PreventUserExistenceErrors` | Hạn chế lộ thông tin user tồn tại | User enumeration qua lỗi đăng nhập |

Giá trị cụ thể, đơn vị TTL, giới hạn callback URLs và tính năng client-secret management được AWS cập nhật; kiểm tra API/tài liệu theo Region và product tier hiện hành.

### 7.4. Client secrets và rotation

Theo tài liệu AWS mới, app client confidential có thể có các cơ chế quản lý **client secret rotation**, bao gồm duy trì nhiều secrets trong một giai đoạn chuyển đổi hoặc tích hợp với Secrets Manager khi được hỗ trợ.

Đối với code vận hành:

1. Không hardcode client secret.
2. Nếu server cần secret, lưu trong **Secrets Manager** hoặc vault tổ chức.
3. Đọc/cache secret theo chính sách và có khả năng refresh sau rotation.
4. Rotate trên môi trường thử, xác nhận không gây lỗi token exchange rồi mới production.
5. Không coi việc “đổi `GenerateSecret`” trên app client đã tồn tại là thao tác đơn giản; loại public/confidential cần được thiết kế từ đầu.

**Phân biệt client secret rotation với refresh token rotation**: một bên là thông tin xác thực ứng dụng server, một bên là vòng đời token đăng nhập của người dùng.

## 8. OAuth 2.0/OIDC: app client chọn flow và scopes

### 8.1. Authorization Code + PKCE cho SPA/mobile

~~~mermaid
sequenceDiagram
    participant B as Browser / Mobile
    participant APP as App client
    participant C as Cognito managed login
    participant API as Backend API
    B->>APP: Người dùng chọn Đăng nhập
    APP->>APP: Tạo state, nonce, code_verifier + code_challenge
    APP->>C: /oauth2/authorize (code, PKCE, scopes, redirect_uri)
    C->>B: Đăng nhập + MFA / federated IdP
    C-->>APP: Redirect về callback có authorization code + state
    APP->>APP: Xác minh state
    APP->>C: /oauth2/token với code_verifier
    C-->>APP: ID + access + refresh tokens nếu được cấp
    APP->>API: Authorization Bearer access_token
    API->>API: Verify JWT + scope/group/resource permissions
~~~

Với SPA/mobile là **public client**, dùng `Authorization Code + PKCE` thay vì implicit grant. **PKCE không thay thế state và nonce**; nên sử dụng thư viện OIDC đáng tin để triển khai chống CSRF, token substitution và các điều kiện liên quan.

**Callback URLs** phải được đăng ký chính xác cho client. Sử dụng HTTPS cho môi trường thật, có ngoại lệ hợp lệ dành cho localhost trong phát triển theo quy tắc Cognito. Không dùng callback URL wildcard rộng hoặc redirect không được kiểm soát.

### 8.2. OAuth scopes khác group names

| Khái niệm | Ví dụ | Tác dụng |
|---|---|---|
| OIDC scope | `openid` | Xin đăng nhập theo OIDC/ID token |
| OIDC scope | `email`, `profile` | Xin các claim/profile tương ứng theo quyền |
| Cognito scope | `aws.cognito.signin.user.admin` | Cho phép self-service user pool operations theo quy tắc Cognito |
| Custom API scope | `school-api/courses.read` | Cho API kiểm tra có quyền đọc lớp thao tác đó |
| Custom API scope | `school-api/grades.write` | Cho API kiểm tra lớp thao tác ghi |
| Cognito group | `teachers` | Phân loại người dùng trong user pool |
| Business policy | “Giáo viên A được chấm lớp 123” | Kiểm tra tài nguyên cụ thể |

**`scope`** thường nằm trong **access token**. **`cognito:groups`** có thể nằm trong cả access và ID tokens, nhưng không phải OAuth scope. Resource server phải kiểm tra **signature/issuer/expiry/token_use/client/audience phù hợp**, rồi mới dùng scopes/groups như một phần của logic quyền.

### 8.3. Resource server và custom scopes

Trong Cognito, bạn có thể định nghĩa resource server identifier, ví dụ `school-api`, cùng scopes:

~~~text
Resource server identifier: school-api
Scope names:
  courses.read
  courses.write
  grades.read
  grades.write
  reports.generate

Token scope values:
  school-api/courses.read
  school-api/grades.write
~~~

Đây là **quyền theo API capability**, chưa phải quyền theo một dòng dữ liệu cụ thể. Ví dụ access token có `school-api/grades.write` chưa có nghĩa được sửa tất cả grade records; backend tiếp tục kiểm tra course assignment.

### 8.4. Machine-to-machine dùng client_credentials

Một service tự động tạo báo cáo có thể dùng **confidential app client** và `client_credentials` để xin **access token** với custom scopes. Không có người dùng tương tác và thông thường **không có ID token người dùng** trong luồng này.

Thiết kế an toàn:

- Client secret giữ tại server/vault, rotate theo quy trình.
- Chỉ cấp các custom scopes service cần.
- API phân biệt **machine principal** với human user.
- Log/audit theo client/service, không tự tạo giả user `admin`.
- Rate limits và quota phù hợp, không dùng một shared client secret cho mọi service độc lập.

### 8.5. Refresh token rotation và phiên đăng nhập

Cognito hỗ trợ **refresh token rotation**. Khi bật trên app client, mỗi lần refresh thành công có thể cấp refresh token mới theo cơ chế dịch vụ; app phải lưu/thu hồi token an toàn.

Quan trọng: một app client bật refresh token rotation **không thể tiếp tục dùng auth flow `REFRESH_TOKEN_AUTH`** như khi rotation tắt; cần dùng token endpoint `refresh_token` hoặc API `GetTokensFromRefreshToken` theo khả năng được hỗ trợ.

Nếu thiết bị mất refresh token hoặc refresh thất bại, app cần xử lý đăng nhập lại/thu hồi session, không giảm bảo mật bằng cách tăng thời gian sống token vô hạn.

## 9. ID token, access token, refresh token và group claims

### 9.1. Mục đích từng token

| Token | Đối tượng sử dụng | Chứa gì? | Dùng để gọi API nghiệp vụ? |
|---|---|---|---|
| **ID token** | OIDC client để biết người dùng đã xác thực | `sub`, `aud`, profile claims và `token_use=id` | **Không nên** dùng làm bearer authorization token của API |
| **Access token** | Resource server/API | `scope`, `client_id`, `sub`, `token_use=access` và claims phù hợp | **Có**, sau xác minh đầy đủ |
| **Refresh token** | Client/session để xin token mới | Opaque token theo cơ chế Cognito | Không đưa cho resource server/API nghiệp vụ |

JWT thông thường là **signed**, không mặc nhiên **encrypted**. Không đưa mật khẩu, token downstream, bí mật thanh toán hoặc thông tin cá nhân quá mức vào custom claims.

### 9.2. Ví dụ ID token payload giản lược

~~~json
{
  "iss": "https://cognito-idp.ap-southeast-1.amazonaws.com/ap-southeast-1_EXAMPLE",
  "sub": "cognito-sub-example",
  "aud": "example-public-client-id",
  "token_use": "id",
  "email": "learner@example.test",
  "email_verified": true,
  "custom:tenantId": "school-42",
  "cognito:groups": ["students"],
  "iat": 1795140000,
  "exp": 1795143600
}
~~~

**Giả lập, không phải token có chữ ký hợp lệ.** Claims trong thực tế phụ thuộc scope, app client attribute permissions, token customization, nhóm và cấu hình IdP. Không mặc định mọi custom attribute luôn xuất hiện trong ID token.

### 9.3. Ví dụ access token payload giản lược

~~~json
{
  "iss": "https://cognito-idp.ap-southeast-1.amazonaws.com/ap-southeast-1_EXAMPLE",
  "sub": "cognito-sub-example",
  "client_id": "example-public-client-id",
  "token_use": "access",
  "scope": "openid school-api/courses.read",
  "cognito:groups": ["students"],
  "iat": 1795140000,
  "exp": 1795143600
}
~~~

Ví dụ này không có `aud` vì Cognito access token thường dùng `client_id` để nhận diện app client. Với các phiên bản hỗ trợ **resource binding**, access token có thể chứa `aud` là URL của resource server. Do đó, API phải kiểm tra **audience/client_id theo đúng token type và cấu hình**.

### 9.4. Các bước xác minh JWT ở backend

~~~text
1. Lấy OIDC discovery/JWKS từ issuer của Cognito User Pool tin cậy.
2. Xác thực JWT signature bằng public key có kid phù hợp.
3. Xác thực iss đúng user pool định cấu hình.
4. Xác thực token_use=access cho API nghiệp vụ.
5. Xác thực client_id và/hoặc aud theo flow/resource binding.
6. Xác thực exp, nbf/iat khi phù hợp và clock skew hợp lý.
7. Kiểm tra scope của API và group claims nếu policy dùng.
8. Kiểm tra user/tenant/resource ownership ở backend.
9. Áp chính sách revocation/session nếu ứng dụng yêu cầu.
10. Audit các quyết định quan trọng, không log JWT nguyên văn.
~~~

Không chỉ `Base64 decode` JWT rồi tin claim; **chưa kiểm tra chữ ký thì payload do client tự tạo có thể giống hệt token thật**. Cần xử lý JWKS key rotation và cache key set hợp lý; nên dùng thư viện JWT/OIDC đã được bảo trì.

### 9.5. Quyền đổi group không làm token cũ biến mất tức thời

Khi một nhân sự bị loại khỏi group `school-admins`, token phát trước đó có thể tiếp tục mang `cognito:groups` cũ cho tới khi hết hạn hoặc chính sách session/revocation có hiệu lực theo thiết kế. Với quyền nhạy cảm:

- Đặt TTL vừa đủ ngắn cho access token.
- Có phương án token revocation/sessions theo sản phẩm.
- Backend có thể kiểm tra **trạng thái quyền hiện hành** từ database/cache kiểm soát khi cần phản ánh gần như tức thì.
- Không tin một JWT cũ vô hạn chỉ vì chữ ký hợp lệ.

## 10. Federation: attribute mapping và trust boundaries

### 10.1. User Pool có thể nhận IdP bên ngoài

Một user pool có thể liên kết những nguồn danh tính được hỗ trợ, ví dụ Google/OIDC/SAML. Khi người dùng đăng nhập qua IdP, Cognito có thể map attributes từ IdP sang user pool profile.

~~~mermaid
flowchart LR
    U[Người dùng] --> LOGIN[Cognito managed login]
    LOGIN --> IDP[External OIDC/SAML IdP]
    IDP -->|Claims đã xác thực| COG[(Cognito User Pool)]
    COG --> MAP[Attribute mappings]
    MAP --> ATTR[Standard/custom user attributes]
    COG --> APP[App client tokens]
    APP --> API[Backend authorization]
~~~

Một mapping như `email → email` hoặc `department → custom:department` có thể hoạt động, **nhưng phải xét nguồn tin cậy, quyền write và mutability**.

### 10.2. Quy tắc cho mapped attributes

- Thuộc tính đích cần **mutable** nếu IdP có thể cập nhật giá trị khi sign-in.
- **App client liên quan phải có WriteAttributes** cho thuộc tính đã mapping, nếu không sign-in có thể thất bại khi Cognito cần cập nhật.
- Mapping vào **immutable custom attribute** là một lỗi thiết kế phổ biến; AWS có thể từ chối quá trình login khi IdP gửi giá trị cần ghi.
- Không dùng claim IdP do bên ngoài tự cho phép người dùng sửa như một điều kiện cấp quyền quản trị.
- Với tenant/organization, xây **quy trình xác thực quan hệ từ phía backend/admin provisioning**; không dùng một `email domain` chưa được xác minh làm quyền cao.
- Thiết kế **account linking** để tránh duplicate users, account takeover hoặc hợp nhất sai chỉ vì hai profile có cùng email.

### 10.3. Ví dụ bảng mapping

| IdP claim | Cognito attribute | Mutable? | Có nên dùng làm authz? |
|---|---|---|---|
| `email` | `email` | Theo cấu hình | Chỉ như thông tin liên hệ, kiểm tra `email_verified` |
| `given_name` | `given_name` | Thường có | Không |
| `locale` | `locale` | Có | Không |
| `department` | `custom:department` | **Có** nếu map mỗi lần login | Chỉ sau kiểm chứng nguồn quản trị |
| `tenantId` do IdP kiểm soát | `custom:tenantId` | Có nếu cần sync | Chỉ nếu trust contract/quyền IdP rõ |
| `isSuperAdmin` từ profile do user tự sửa | **Không map thành quyền** | Không áp dụng | **Không** |

Federation là việc liên kết **identity**, không tự động chuyển mọi claim ngoài thành quyền nội bộ của ứng dụng.

## 11. Thiết kế đa ứng dụng và đa tenant

### 11.1. User Pool chung hay tách pool?

| Thiết kế | Ưu điểm | Rủi ro/đánh đổi |
|---|---|---|
| Một user pool cho nhiều app clients | Một profile, nhiều ứng dụng, chung xác thực | Phải quản lý quyền read/write chặt, mọi client nhìn cùng directory |
| Pool riêng theo môi trường dev/staging/prod | Cô lập dữ liệu thử và sản xuất | Quản lý nhiều configs, triển khai/chi phí |
| Pool riêng theo tenant lớn khi yêu cầu cô lập cao | Đường ranh giới cấu hình/danh tính rõ | Quota, user management, federation, vận hành phức tạp |
| Pool chung + tenant ID trong DB và policy backend | Mở rộng khi nhiều tenants nhỏ | Authorization theo tenant phải triển khai và kiểm thử nghiêm ngặt |

Không có một mô hình duy nhất tối ưu mọi SaaS. Cân nhắc compliance, user federation, email domain, data sovereignty, number of tenants, IAM scope và ngân sách.

### 11.2. Tách identity ID khỏi domain entity

Mô hình đơn giản trong database ứng dụng:

~~~sql
CREATE TABLE app_user (
    internal_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cognito_issuer VARCHAR(256) NOT NULL,
    cognito_sub VARCHAR(256) NOT NULL,
    display_name VARCHAR(200),
    UNIQUE (cognito_issuer, cognito_sub)
);

CREATE TABLE tenant_membership (
    user_id BIGINT NOT NULL REFERENCES app_user(internal_id),
    tenant_id VARCHAR(64) NOT NULL,
    role_code VARCHAR(64) NOT NULL,
    PRIMARY KEY (user_id, tenant_id, role_code)
);
~~~

Lược đồ mang tính minh họa; cú pháp SQL áp dụng tùy RDBMS và mô hình nghiệp vụ. **Đừng sử dụng email làm khóa** trong bảng `tenant_membership`. Khi user đổi email, quan hệ tenant không được tự thay đổi.

### 11.3. Ví dụ API phân quyền theo tenant

~~~text
POST /tenants/school-42/courses/123/grades

Backend:
  1. Verify access token (iss, signature, token_use, client_id/aud, exp).
  2. Kiểm tra scope grades.write nếu API dùng OAuth scopes.
  3. Lấy (issuer, sub) và ánh xạ sang internal app_user.
  4. Kiểm tra user là teacher/admin của tenant school-42.
  5. Kiểm tra course 123 thuộc school-42.
  6. Kiểm tra teacher được phân công chấm course 123.
  7. Thực hiện cập nhật + audit trong transaction.
~~~

Kể cả token có `cognito:groups=["teachers"]` và `custom:tenantId="school-42"`, bước 4–6 vẫn cần logic phía server. Một user có thể thuộc nhiều tenants; lưu một tenantId duy nhất trong Cognito thường không đủ mô hình.

## 12. Chính sách bảo mật khi tạo app client

### 12.1. Checklist theo từng loại app

| Kiểm soát | SPA/mobile | Server web/BFF | M2M |
|---|---|---|---|
| Client secret | Không | Có thể có, chỉ giữ server | Có |
| OAuth flow | Code + PKCE | Code flow, server session | client_credentials |
| Callback URLs | HTTPS exact, localhost cho dev khi phù hợp | HTTPS exact | Không dùng callback người dùng |
| Scopes | Ít nhất cho giao diện/API | Theo chức năng server | Custom API scopes tối thiểu |
| Read/WriteAttributes | Rõ, ít nhất | Rõ theo server nghiệp vụ | Thường không cần user profile |
| Refresh token | Lưu an toàn, rotate nếu phù hợp | Server-side/secure session | Không có user refresh token theo flow client_credentials |
| MFA | Theo rủi ro user | Theo rủi ro user/admin | Không áp dụng human MFA trực tiếp |
| Token validation | API kiểm tra độc lập | BFF/API kiểm tra | API kiểm tra client and scope |
| Logging | Không lưu tokens/PII | Redact headers/secret | Không ghi client secret |

### 12.2. MFA, sign-up và user enumeration

Để bảo vệ user directory, xem xét:

- MFA/passkey/password policy theo khả năng Cognito và mức rủi ro;
- cơ chế xác minh email/phone và recovery;
- CAPTCHA/bot detection, threat protection theo feature tier nếu phù hợp;
- `PreventUserExistenceErrors` và thông báo lỗi đăng nhập không tiết lộ tài khoản;
- giới hạn tốc độ đăng ký/thử mật khẩu;
- CloudTrail/metrics và cảnh báo admin operations;
- account lifecycle: disabled, deleted, archived, reactivated theo compliance.

**Không tự giả định Cognito MFA bảo vệ mọi thao tác nhạy cảm**. Thay đổi tài khoản ngân hàng, cấp quyền admin hoặc xuất dữ liệu có thể yêu cầu **step-up authentication** và audit bổ sung.

### 12.3. Secrets và token storage

- Client secret phải ở backend/Secrets Manager, không trong HTML hoặc JavaScript.
- Access token/ID token không được ghi ra analytics, URL query hoặc logs.
- Với browser, đánh giá BFF + HttpOnly/Secure/SameSite cookies hoặc cơ chế được OIDC SDK hỗ trợ; tránh lưu token dài hạn dễ bị XSS truy cập.
- Dùng TLS, Content Security Policy, security headers, CORS phù hợp.
- Xác minh callback URLs để chống code injection, redirect abuse và CSRF.
- Có kế hoạch logout, revoke và token TTL.
- Không dùng `client_id` như một bằng chứng bí mật xác định người gọi; public client IDs là thông tin công khai.

## 13. Thực hành 1 — Khám phá user pool bằng AWS CLI (chỉ đọc)

> Bài lab mặc định **không tạo user, group hoặc app client**, không phát token và không đọc mật khẩu/client secrets. Dùng AWS CLI v2, IAM profile **sandbox** với quyền đọc Cognito. Các ID đều là placeholder. Nếu tổ chức yêu cầu chống tiết lộ thông tin cấu hình, chỉ lưu kết quả trong môi trường được cấp quyền.

### 13.1. Xác minh account và Region

Ví dụ trên Bash/AWS CloudShell:

~~~bash
export AWS_PROFILE=aws-lab-dev
export AWS_DEFAULT_REGION=ap-southeast-1
REGION=ap-southeast-1

aws sts get-caller-identity --profile "$AWS_PROFILE"
~~~

Nếu dùng CloudShell đã có credentials mà không có profile `aws-lab-dev`, bỏ bước export và các tham số `--profile` liên quan. Không dùng production account chỉ để học.

### 13.2. Liệt kê user pools

~~~bash
aws cognito-idp list-user-pools \
  --max-results 20 \
  --region "$REGION" \
  --query 'UserPools[].{Id:Id,Name:Name,LastModifiedDate:LastModifiedDate}' \
  --output table
~~~

API này có pagination. Nếu kết quả hiển thị chỉ là trang đầu, dùng next token/paginator phù hợp của AWS CLI để tiếp tục; không suy luận account chỉ có 20 pools.

### 13.3. Đọc schema của pool

~~~bash
USER_POOL_ID=ap-southeast-1_EXAMPLE

aws cognito-idp describe-user-pool \
  --user-pool-id "$USER_POOL_ID" \
  --region "$REGION" \
  --query 'UserPool.{Id:Id,Name:Name,UsernameAttributes:UsernameAttributes,AliasAttributes:AliasAttributes,AutoVerifiedAttributes:AutoVerifiedAttributes,UsernameConfiguration:UsernameConfiguration,SchemaAttributes:SchemaAttributes}' \
  --output json
~~~

Quan sát:

- `Required` và `Mutable` của standard/custom attributes;
- `AttributeDataType` và `StringAttributeConstraints`;
- `UsernameAttributes` hay `AliasAttributes`;
- `AutoVerifiedAttributes` cho email/phone nếu có;
- custom attributes có tiền tố `custom:`;
- schema nào không thể dễ thay đổi sau tạo pool.

**Không chạy `list-users` hoặc `admin-get-user` để lấy dữ liệu cá nhân** nếu không có mục đích và quyền hợp lệ; lab chỉ cần schema, không cần danh sách học viên thật.

### 13.4. Liệt kê groups

~~~bash
aws cognito-idp list-groups \
  --user-pool-id "$USER_POOL_ID" \
  --region "$REGION" \
  --query 'Groups[].{Name:GroupName,Precedence:Precedence,RoleArn:RoleArn}' \
  --output table
~~~

Group names và IAM RoleArn có thể là **metadata nội bộ**; chỉ lưu trong tài liệu lab được cấp quyền. Không liệt kê thành viên thật hoặc gửi danh sách ra ngoài. Nếu group không có RoleArn, đó **không phải lỗi** khi chỉ dùng groups cho application roles.

### 13.5. Liệt kê app clients

~~~bash
aws cognito-idp list-user-pool-clients \
  --user-pool-id "$USER_POOL_ID" \
  --max-results 20 \
  --region "$REGION" \
  --query 'UserPoolClients[].{ClientName:ClientName,ClientId:ClientId}' \
  --output table
~~~

Ghi lại các client IDs **được phép quan sát**, so tên để biết SPA/mobile/admin/M2M đã được tách chưa.

### 13.6. Mô tả một app client mà không xuất ClientSecret

**Rất quan trọng:** API `DescribeUserPoolClient` có thể trả về **`ClientSecret`** đối với confidential app client. Vì vậy, **không chạy `--output json` toàn bộ response** và không dán log gốc. Chỉ truy vấn các fields không chứa secret:

~~~bash
CLIENT_ID=exampleclientid

aws cognito-idp describe-user-pool-client \
  --user-pool-id "$USER_POOL_ID" \
  --client-id "$CLIENT_ID" \
  --region "$REGION" \
  --query 'UserPoolClient.{Name:ClientName,Id:ClientId,AllowedOAuthFlows:AllowedOAuthFlows,AllowedOAuthScopes:AllowedOAuthScopes,CallbackURLs:CallbackURLs,LogoutURLs:LogoutURLs,ReadAttributes:ReadAttributes,WriteAttributes:WriteAttributes,ExplicitAuthFlows:ExplicitAuthFlows,AccessTokenValidity:AccessTokenValidity,IdTokenValidity:IdTokenValidity,RefreshTokenValidity:RefreshTokenValidity,RefreshTokenRotation:RefreshTokenRotation,TokenValidityUnits:TokenValidityUnits,PreventUserExistenceErrors:PreventUserExistenceErrors}' \
  --output json
~~~

**Diễn giải:**

- `ReadAttributes` hoặc `WriteAttributes` không hiển thị có thể nghĩa là app đang dùng **default permissions**, không phải “không có quyền”.
- Nếu thấy callback URL trỏ sang staging trong app client production, cần mở issue thay đổi sau review.
- `AllowedOAuthFlows` và `AllowedOAuthScopes` phải phản ánh client type và API thực sự cần.
- Nếu client là SPA và secret vẫn được cấu hình, cần đánh giá **nguy cơ lộ secret** và kế hoạch thay client.
- Nếu auth flow/token setting thiếu hoặc khác dự kiến, đọc tài liệu/version hiện hành và cấu hình thực trước khi kết luận.

### 13.7. Liệt kê resource servers và OAuth scopes

~~~bash
aws cognito-idp list-resource-servers \
  --user-pool-id "$USER_POOL_ID" \
  --max-results 20 \
  --region "$REGION" \
  --query 'ResourceServers[].{Name:Name,Identifier:Identifier,Scopes:Scopes}' \
  --output json
~~~

Đối chiếu custom scope identifiers với `AllowedOAuthScopes` của từng app client. Một scope có tồn tại ở resource server **không có nghĩa mọi client được phép xin** scope đó.

## 14. Thực hành 2 — Thiết kế JSON và thay đổi có kiểm soát

> Phần này chỉ là **ví dụ cấu hình để review**. Các lệnh tạo/sửa Cognito user pool, group và app client có thể ảnh hưởng trực tiếp tài khoản và đăng nhập người dùng. **Không thực thi trên production** khi chưa có approval, quyền IAM phù hợp, phương án rollback và dữ liệu thử. Không thể đảo ngược mọi thay đổi schema.

### 14.1. Mẫu thiết kế schema

Giả sử ứng dụng cần `custom:tenantId` để hiển thị tenant đang được quản lý. Một phần schema khi tạo pool:

~~~json
{
  "Schema": [
    {
      "Name": "tenantId",
      "AttributeDataType": "String",
      "DeveloperOnlyAttribute": false,
      "Mutable": false,
      "Required": false,
      "StringAttributeConstraints": {
        "MinLength": "1",
        "MaxLength": "64"
      }
    }
  ]
}
~~~

**Không dùng mẫu này như toàn bộ `CreateUserPool` request**; API còn yêu cầu/cho phép nhiều cấu hình khác. Nếu cần tenant membership thay đổi theo thời gian, một immutable `tenantId` có thể là lựa chọn sai; cân nhắc database nghiệp vụ hoặc mutable attribute chỉ admin-writable.

### 14.2. Mẫu group configuration

Ví dụ groups:

~~~json
[
  {"GroupName": "students", "Precedence": 30},
  {"GroupName": "teachers", "Precedence": 20},
  {"GroupName": "content-reviewers", "Precedence": 10},
  {"GroupName": "school-admins", "Precedence": 0}
]
~~~

Đây là **minh họa group precedence**, không phải đầu vào nguyên xi cho CLI. Các precedence này **không tự định nghĩa cấp quyền REST API**; phải có backend policy. Nếu không dùng Identity Pool, có thể **không cần đặt precedence**.

Lệnh có tác động, chỉ dành cho sandbox nếu được phép:

~~~bash
# CÓ TÁC ĐỘNG - không chạy trên pool dùng chung hoặc production
aws cognito-idp create-group \
  --user-pool-id ap-southeast-1_EXAMPLE \
  --group-name training-students \
  --description "Sandbox student group" \
  --precedence 30 \
  --region ap-southeast-1
~~~

Để dọn group thử nghiệm sau khi xác nhận không còn user/không dùng chung, có thể dùng `delete-group` theo quy trình được duyệt; **không xóa groups nghiệp vụ thật**.

### 14.3. App client cho SPA (JSON minh họa)

~~~json
{
  "UserPoolId": "ap-southeast-1_EXAMPLE",
  "ClientName": "training-student-spa",
  "GenerateSecret": false,
  "AllowedOAuthFlowsUserPoolClient": true,
  "AllowedOAuthFlows": ["code"],
  "AllowedOAuthScopes": [
    "openid",
    "email",
    "profile",
    "school-api/courses.read"
  ],
  "CallbackURLs": [
    "https://learn.example.com/auth/callback"
  ],
  "LogoutURLs": [
    "https://learn.example.com/"
  ],
  "SupportedIdentityProviders": ["COGNITO"],
  "ReadAttributes": [
    "email",
    "email_verified",
    "given_name",
    "custom:tenantId"
  ],
  "WriteAttributes": [
    "email",
    "given_name"
  ],
  "PreventUserExistenceErrors": "ENABLED"
}
~~~

Cần kiểm tra rằng resource server `school-api` và scope `courses.read` đã được tạo. Cấu hình `ReadAttributes`/`WriteAttributes` phải phù hợp required standard attributes, đăng ký user, federation và các ràng buộc AWS; **mẫu chỉ minh họa ý định**, không bảo đảm chấp nhận nguyên xi ở mọi pool/flow.

### 14.4. App client cho M2M (JSON minh họa)

~~~json
{
  "UserPoolId": "ap-southeast-1_EXAMPLE",
  "ClientName": "training-report-job",
  "GenerateSecret": true,
  "AllowedOAuthFlowsUserPoolClient": true,
  "AllowedOAuthFlows": ["client_credentials"],
  "AllowedOAuthScopes": ["school-api/reports.generate"],
  "SupportedIdentityProviders": ["COGNITO"]
}
~~~

M2M không có user login/ID token; không thiết lập OIDC `openid/email` như nếu có người dùng. Client secret phải được lưu ở backend vault và hỗ trợ rotation; không đưa request/response của lệnh tạo client vào CI log công khai vì có thể chứa `ClientSecret`.

### 14.5. Hợp đồng API sau khi tạo app clients

1. Xác minh SPA chỉ được redirect về callback được phép.
2. Xác minh Authorization Code + PKCE; không gửi client secret từ browser.
3. Xác minh access token chứa `school-api/courses.read` khi thực sự xin scope.
4. Xác minh access token không có `grades.write` nếu chưa được cấp.
5. Thử self-service update một attribute được phép như `given_name`.
6. Thử sửa `custom:tenantId` từ SPA phải bị từ chối.
7. Thử user không thuộc `teachers` gọi API chấm điểm phải bị backend từ chối.
8. Thử user thuộc `teachers` nhưng không được giao course cụ thể vẫn bị từ chối.
9. Thử key rotation/JWKS refresh và token expiration/revocation.
10. Log evidence mà **không ghi token, mật khẩu, email thật hoặc client secret**.

## 15. Vận hành, giám sát và chi phí

### 15.1. Vòng đời thay đổi

Một thay đổi user pool/app client ảnh hưởng nhiều ứng dụng:

~~~text
Design review
   ↓
Threat model + data classification
   ↓
Schema / groups / app-client policy as code
   ↓
Sandbox integration tests
   ↓
Staging with federated IdP and real-world auth flows
   ↓
Production rollout + monitoring
   ↓
Rollback/revoke plan và audit
~~~

Các thành phần **khó sửa** như sign-in identifiers và custom attribute schema phải được review kỹ trước khi tạo user pool. Các thay đổi client OAuth URLs/scopes/attribute permissions nên có migration plan cho ứng dụng đang chạy.

### 15.2. Những tín hiệu cần theo dõi

| Tín hiệu | Ý nghĩa | Cách xử lý |
|---|---|---|
| Sign-up/sign-in successes và failures | Trải nghiệm đăng nhập và lỗi cấu hình | Phân loại password, MFA, callback, IdP |
| Token endpoint errors | Lỗi code/PKCE/client secret/scope | Kiểm tra flow và client config |
| User existence probing | Nỗ lực enumeration | Rate limiting, generic errors, threat protection |
| MFA failure/lockout | Đăng nhập thất bại có rủi ro | Recovery workflow an toàn |
| Group membership changes | Có thể thay đổi quyền truy cập | Audit `AdminAddUserToGroup`/`AdminRemoveUserFromGroup` |
| App client config changes | Có thể thay OAuth scopes/callbacks/read-write | CloudTrail và config diff |
| IdP federation failures | Attribute mapping, issuer, metadata, write permission | Mapped attributes và login logs |
| Backend 401/403 | Token invalid hoặc quyền API/tenant bị từ chối | Phân biệt authn và authz, không ghi token |
| Token refresh failures | Session renewal/rotation hoặc client secret sai | SDK/rotation/revocation/expiry |
| Cognito/API costs | MAU, M2M token requests, features/tiers và SMS/email | Budgets, pricing calculator, quotas |

Cognito có **mô hình phí theo user pools/feature plans, monthly active users (MAU), M2M flows và những thành phần liên quan** tùy tài khoản/Region. Những dịch vụ như SNS/SMS, SES, Lambda triggers, CloudWatch logs và AWS WAF có thể phát sinh phí riêng. Không sử dụng một đơn giá cũ làm cơ sở chốt ngân sách; xem bảng giá Cognito hiện hành.

### 15.3. IAM quản trị và bảo vệ dữ liệu

- IAM principal dùng `cognito-idp:DescribeUserPool`/`ListGroups` khác với người dùng cuối trong pool.
- Giới hạn quyền tạo/xóa group, cập nhật client, quản lý liên kết IdP và thay user profile.
- Dùng IAM Identity Center/role tạm thời, không dùng access keys dài hạn nếu có phương án an toàn hơn.
- Không cấp `cognito-idp:*` trên mọi resources cho pipeline chỉ cần xem cấu hình.
- Rà soát CloudTrail cho những thao tác IAM/management; quản lý log retention/alert theo yêu cầu.
- Dữ liệu user attributes có thể là PII; hạn chế trích xuất `ListUsers` và lưu token payload.
- Thiết kế chính sách xóa tài khoản, đồng bộ/backup dữ liệu nghiệp vụ và quyền riêng tư theo quy định áp dụng.

## 16. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
|---|---|---|
| User đã sign-in nhưng backend 401 | Token signature/issuer/expiry/client không hợp lệ | JWKS, `iss`, `exp`, `token_use`, client IDs |
| API trả 403 dù token hợp lệ | Scope/group/tenant/resource permission thiếu | Backend authorization, không đổi token validation |
| SPA bị yêu cầu client secret | Đã tạo confidential client cho browser | Tạo public app client không có secret; migrate |
| OAuth redirect báo invalid `redirect_uri` | Callback URL không khớp config | So chính xác scheme/host/path và client ID |
| Code exchange báo `invalid_grant` | Code hết hạn, reused, PKCE/state mismatch | Authorization flow và code_verifier |
| Access token không có custom scope | App client chưa được cấp scope hoặc chưa xin scope | Resource server, `AllowedOAuthScopes` và request |
| ID token không có `custom:tenantId` | App client thiếu ReadAttributes hoặc user chưa có giá trị | Xem cấu hình/attribute mapping mà không log token thật |
| User có thể sửa tenant/role | WriteAttributes quá rộng ở một app client | Audit tất cả clients; loại quyền write, review logs |
| Gửi `email_verified=true` từ client bị từ chối | Không được tự sửa verification flag theo flow | Dùng verification/API admin có quyền phù hợp |
| Sửa `custom:tenantId` báo immutable | Attribute được tạo `Mutable=false` | Không thể đổi schema cũ; lập kế hoạch migration |
| Federation sign-in bị lỗi khi map attribute | Attribute không mutable hoặc app client không writable | IdP attribute mapping, WriteAttributes |
| Email sign-up báo `UsernameExistsException` | Sign-in identifier/uniqueness khác kỳ vọng | Xem `UsernameAttributes`/`AliasAttributes` |
| Username là email bị từ chối trong alias pool | Pool cấu hình email alias, username không được trùng định dạng email | Dùng username phù hợp hoặc thiết kế pool khác |
| Group membership mới chưa thấy trong token | JWT cũ, refresh/sign-in chưa phát claims mới | Token lifecycle, kiểm tra nguồn quyền hiện hành |
| `cognito:preferred_role` trống | Nhiều groups cùng precedence nhưng RoleArn khác | Rà soát group precedence/IAM role |
| Có group `teachers` nhưng vẫn không được sửa lớp | Backend kiểm tra assignment/course tenant | Không sửa group để vượt data ownership |
| `DescribeUserPoolClient` không trả Read/WriteAttributes | Đang dùng default permissions | Không coi là deny-all; audit defaults và cấu hình tối thiểu |
| M2M không nhận ID token | `client_credentials` không có user interaction | Dùng access token cho API và custom scopes |
| Refresh thất bại sau khi bật rotation | Client vẫn dùng `REFRESH_TOKEN_AUTH` | Chuyển sang token endpoint/GetTokensFromRefreshToken |
| Token payload hiển thị PII | Attribute permissions/claims rộng | Giảm ReadAttributes, tránh đưa PII vào tokens/logs |
| User bị khóa vì MFA/IdP | Chính sách an ninh, mapping hoặc account state | Recovery theo quy trình, không tắt MFA toàn pool |
| Quota hoặc chi phí bất thường | Nhiều clients/groups/MAUs/M2M tokens | Service Quotas, Cost Explorer, logs |

### 16.1. Runbook điều tra

~~~text
1. Xác minh AWS account, Region, user pool ID và client ID.
2. Xác định đang lỗi sign-up, login, token exchange, token validation hay API authorization.
3. So cấu hình sign-in identifiers, required/mutable attributes và client type.
4. Xem AllowedOAuthFlows, scopes, callbacks và auth flows.
5. Xem ReadAttributes/WriteAttributes thực tế và cả defaults.
6. Nếu federated, xem IdP mappings, mutability và verified claims.
7. Nếu group-based, xem membership, precedence và token freshness.
8. Phía API, kiểm tra iss/signature/aud-or-client_id/token_use/exp.
9. Kiểm tra tenant/resource ownership và audit log, không log JWT nguyên văn.
10. Sửa đúng lớp, chạy negative tests và rollout qua sandbox/staging.
~~~

## 17. Bài tập tình huống: nền tảng giáo dục nhiều vai trò

### 17.1. Yêu cầu

Một ứng dụng học trực tuyến có:

- **Student SPA** trên `learn.example.com` và mobile app.
- **Teacher portal** chạy qua một backend-for-frontend.
- **School admin** có quyền mời giáo viên và quản lý lớp thuộc trường của họ.
- **Report worker** backend gọi API báo cáo không có người dùng tương tác.
- Một người dùng có thể vừa là học viên, vừa là giáo viên.
- Một số giáo viên có thể thuộc hai trường khác nhau.
- CSDL RDS giữ quan hệ `teacher ↔ course ↔ tenant`; S3 giữ tài liệu riêng tư.

Không được cho user tự gán `school-admins` hoặc thay tenantId để xem dữ liệu trường khác.

### 17.2. Thiết kế được đề xuất

| Thành phần | Thiết kế | Vì sao |
|---|---|---|
| User Pool | Một pool cho ứng dụng người dùng, tách khỏi dev/staging | Danh tính thống nhất trong cùng môi trường |
| Stable identity | `(issuer, sub)` | Không đổi khi email/username hiển thị đổi |
| Standard attrs | `email`, `email_verified`, `given_name`, `family_name` | Chỉ dữ liệu cần thiết |
| Custom attrs | Ít nhất; có thể dùng `custom:registrationSource` hoặc tenant hint | Không biến token thành cơ sở dữ liệu quyền |
| Groups | `students`, `teachers`, `school-admins` | Vai trò cấp cao, không chứa mọi course |
| App clients | Student SPA public, mobile public, Teacher BFF confidential, Report M2M confidential | Tách token flows/scopes/secret handling |
| OAuth scopes | `courses.read`, `grades.write`, `reports.generate` | Cấp quyền capability ở API |
| Backend authorization | Kiểm tra membership trường/lớp từ RDS | Ngăn truy cập chéo tenant |
| Admin provisioning | API có IAM/log và workflow duyệt | Không để app tự add user vào group |
| Secure delivery | HTTPS, PKCE, MFA cho admin, token verification | Bảo vệ phiên đăng nhập |
| Monitoring | CloudTrail, auth metrics, API 401/403, permission changes | Audit, điều tra sự cố |
| Costs | Theo dõi MAUs, M2M, SMS/email, Lambda triggers | Không vượt ngân sách |

### 17.3. Các tình huống kiểm thử

1. Student chỉ có group `students` cố gọi `POST /grades` → **403**.
2. Teacher thuộc `teachers` cố sửa lớp không được phân công → **403**.
3. Admin trường A cố đổi user từ trường B → **403**.
4. SPA client cố gọi `UpdateUserAttributes` để đặt `custom:tenantId=school-B` → **bị từ chối**.
5. Teacher BFF lấy refresh token từ thiết bị khác không được phép → hệ thống thực hiện session/rotation/revocation policy.
6. M2M client cố gọi `grades.write` khi chỉ có `reports.generate` → **403**.
7. IdP ngoài gửi `custom:department` khác với bản cũ → sign-in thành công chỉ nếu attribute mutable và app client writable theo mapping.
8. User đổi email, các quan hệ khóa học theo `sub` vẫn giữ.
9. User bị loại khỏi nhóm admin; ứng dụng phải xử lý token cũ theo policy freshness/authorization.
10. Mật khẩu/client secret/refresh tokens không hiện trong logs, query strings hay console screenshots.

### 17.4. Câu hỏi tự kiểm tra

1. User Pool khác Identity Pool ở nhiệm vụ chính nào?
2. Vì sao `sub` thích hợp hơn email làm khóa người dùng?
3. Username attribute khác email alias ra sao?
4. Có đổi sign-in method từ username sang email trên một user pool đã tạo tùy ý được không?
5. Vì sao `custom:isAdmin` immutable nhưng người dùng được ghi lúc sign-up vẫn không an toàn?
6. Có thể xóa custom attribute đã tạo không? Hệ quả cho việc thiết kế schema?
7. `ReadAttributes` và `WriteAttributes` của app client khác `AllowedOAuthScopes` thế nào?
8. `DescribeUserPoolClient` không có `WriteAttributes` nghĩa là client không được ghi thuộc tính nào, đúng hay sai?
9. Nếu user thuộc `students` và `teachers`, token có group nào?
10. `Precedence=0` và `Precedence=20` cái nào được ưu tiên khi chọn IAM role?
11. Group precedence có thay được backend authorization theo course không?
12. SPA có thể giữ client secret an toàn trong bundle JavaScript không?
13. Với SPA/mobile, vì sao Authorization Code + PKCE thường tốt hơn implicit?
14. ID token và access token có cùng mục đích không?
15. API cần xác minh gì trước khi đọc `scope` và `cognito:groups`?
16. M2M `client_credentials` có ID token đại diện người dùng thật không?
17. App client thiếu write permission cho mapped IdP attribute gây hệ quả gì?
18. Vì sao một custom attribute chứa tenantId không thể thay database membership?
19. Refresh token rotation ảnh hưởng `REFRESH_TOKEN_AUTH` ra sao?
20. Những dữ liệu nào tuyệt đối không nên đưa vào token hoặc logs?

**Gợi ý đáp án cô đọng:**

1. User Pool xác thực/phát token; Identity Pool cấp AWS temporary credentials theo điều kiện.
2. `sub` ổn định trong pool, email có thể thay đổi.
3. Username attributes dùng email/phone làm username; alias bổ sung lựa chọn đăng nhập trên username cố định theo cấu hình.
4. Không; thường phải tạo pool mới và migration.
5. User có thể tự gán giá trị sai ngay lúc tạo account.
6. Không; cần thiết kế schema bền vững hoặc thêm trường mới và migration.
7. Attribute permissions kiểm soát profile read/write; OAuth scopes xác định yêu cầu truy cập API/OIDC.
8. Sai; có thể đang dùng quyền mặc định rộng.
9. Có thể chứa cả hai trong `cognito:groups`.
10. `0` có ưu tiên cao hơn.
11. Không; backend phải kiểm tra tenant/resource.
12. Không; public client không giữ secret tin cậy.
13. PKCE ràng buộc code với client đang giao dịch, giảm nguy cơ đánh cắp code.
14. Không; ID token cho client biết danh tính, access token cho resource server.
15. Signature, issuer, token_use, expiry, client ID/audience và các điều kiện theo API.
16. Không; đây là service principal.
17. Federation sign-in có thể lỗi khi cần cập nhật attribute.
18. Một user có thể có nhiều memberships, policies thay đổi liên tục.
19. Phải dùng cơ chế refresh tương thích thay vì `REFRESH_TOKEN_AUTH`.
20. Passwords, client secrets, access/refresh tokens, dữ liệu cá nhân không cần thiết.

## 18. Checklist trước khi đưa Cognito vào production

### User pool và attributes

- [ ] Đã chọn User Pool/Identity Pool theo đúng nhu cầu.
- [ ] Khóa định danh nội bộ dùng `sub` (kèm issuer khi nhiều pool), không dùng email.
- [ ] Sign-in identifiers, alias options, case-sensitivity và required attributes được duyệt **trước khi tạo pool**.
- [ ] Standard attributes tối thiểu, có kế hoạch email/phone verification và recovery.
- [ ] Custom attributes có tên, kiểu, mutability và constraints bền vững.
- [ ] Không sử dụng custom attribute để lưu secret hoặc danh sách quyền nghiệp vụ phức tạp.
- [ ] Không cho client tự ghi thuộc tính dùng để quyết định quyền.
- [ ] IdP attribute mappings có nguồn tin cậy, mutable và writable phù hợp.

### Groups và authorization

- [ ] Groups thể hiện vai trò tổng quát, không thay tenant/resource policies.
- [ ] Membership chỉ sửa qua administrative workflow có audit.
- [ ] Hiểu group precedence chỉ liên quan tới preferred role khi tích hợp IAM/Identity Pool.
- [ ] Group claims/token freshness được xử lý đúng khi đổi quyền.
- [ ] API kiểm tra scopes, groups và dữ liệu nghiệp vụ cùng nhau theo deny-by-default.
- [ ] Có negative tests cho cross-tenant, broken object-level authorization và self-escalation.

### App clients và tokens

- [ ] Tách app clients cho SPA/mobile/BFF/M2M theo loại ứng dụng.
- [ ] Public clients không chứa client secret; confidential client secrets ở vault.
- [ ] OAuth Code + PKCE cho public apps; callback/logout URLs cụ thể và hợp lệ.
- [ ] `ReadAttributes`/`WriteAttributes` và OAuth scopes tuân thủ least privilege, có rà soát defaults.
- [ ] API xác minh JWT signature/issuer/token_use/client/aud/exp, không chỉ decode payload.
- [ ] M2M chỉ dùng custom scopes cần thiết và bảo vệ client credentials.
- [ ] Token TTL/refresh rotation/revocation/MFA được thiết kế theo SLO và rủi ro.
- [ ] Không ghi token, client secret hoặc PII không cần thiết vào logs/analytics.

### Vận hành và chi phí

- [ ] Đã kiểm thử sign-up/login/reset/MFA/federation và IdP attribute mapping.
- [ ] CloudTrail/metrics có cảnh báo cho changes nhóm/app client và auth failures.
- [ ] IAM quản trị Cognito được giới hạn theo môi trường và quyền thực tế.
- [ ] Có phương án migration/rollback khi thay schema hoặc app client.
- [ ] Có quản trị retention/xóa dữ liệu người dùng theo quy định.
- [ ] Chi phí MAU/M2M/SMS/email/tính năng bảo mật được dự toán theo giá hiện hành.
- [ ] Có kế hoạch dọn user pools, clients và tài nguyên sandbox **mà không xóa dữ liệu thật**.

**Kết quả mong đợi:** Người học thiết kế được một Cognito User Pool với attributes có nguồn tin cậy, groups thể hiện vai trò ứng dụng, app clients có OAuth/attribute permissions phù hợp; đồng thời biết xác minh token và chặn các lỗi phân quyền vượt tenant, giữ an toàn dữ liệu cá nhân và vận hành trong giới hạn chi phí.

## Tài liệu AWS chính thức

- [What is Amazon Cognito?](https://docs.aws.amazon.com/cognito/latest/developerguide/what-is-amazon-cognito.html)
- [Working with user attributes](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-settings-attributes.html)
- [User pool sign-in with aliases and username attributes](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-settings-attributes.html#user-pool-settings-aliases)
- [Adding groups to a user pool](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-user-groups.html)
- [Using role-based access control with Cognito Identity Pools](https://docs.aws.amazon.com/cognito/latest/developerguide/role-based-access-control.html)
- [Application-specific settings with app clients](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-settings-client-apps.html)
- [Scopes, resource servers and M2M authorization](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-define-resource-servers.html)
- [Using tokens with user pools](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-tokens.html)
- [Verifying JSON web tokens](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-tokens-verifying-a-jwt.html)
- [Understanding ID tokens](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-the-id-token.html)
- [Understanding access tokens](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-the-access-token.html)
- [Refresh tokens and refresh token rotation](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-the-refresh-token.html)
- [Mapping IdP attributes to user pool profiles](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-specifying-attribute-mapping.html)
- [Updating user pool and app client configuration](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pool-updating.html)
- [Cognito user pools API reference](https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/Welcome.html)
- [Cognito pricing](https://aws.amazon.com/cognito/pricing/)
- [AWS Pricing Calculator](https://calculator.aws/)

> **Lưu ý áp dụng:** Tất cả user pool IDs, app client IDs, account IDs, domain names, role names, token JSON và dữ liệu trong bài đều giả định để học tập. Tính năng xác thực, client secret management, OAuth capabilities, service quotas, feature tiers và bảng giá AWS có thể thay đổi. Trước khi tạo hoặc sửa user pool/app client production, đối chiếu tài liệu AWS hiện hành, review bảo mật/PII, kiểm thử trên sandbox và triển khai theo quy trình phê duyệt.
