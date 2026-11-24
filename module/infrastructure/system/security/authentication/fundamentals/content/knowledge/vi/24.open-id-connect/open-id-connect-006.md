# Claims trong OpenID Connect

> **Chương:** OpenID Connect  
> **Phạm vi:** Module **SECURITY_AUTHENTICATION_FUNDAMENTALS** tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này tập trung vào claims trong OpenID Connect (OIDC): dữ liệu nào được IdP khẳng định về người dùng và sự kiện xác thực, claim xuất hiện ở ID token hay UserInfo, cách yêu cầu và xác minh claim, cùng cách sử dụng chúng an toàn trong ứng dụng.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích claim là gì và phân biệt claim với scope, role, permission và dữ liệu do client tự khai.
2. Phân biệt ID token, access token và UserInfo response; biết mỗi loại phục vụ mục đích nào.
3. Nhận diện các claim chuẩn như iss, sub, aud, exp, iat, nonce, auth_time, acr, amr, name, email và email_verified.
4. Yêu cầu claim qua scope hoặc claims request parameter và hiểu giới hạn của consent/policy.
5. Xác minh chữ ký, issuer, audience, thời hạn, nonce và subject binding trước khi tin claim.
6. Thiết kế identity mapping ổn định bằng issuer và subject, tránh liên kết tài khoản chỉ bằng email.
7. Giảm thiểu dữ liệu cá nhân, quản lý custom claims và tránh biến claim cũ thành quyền truy cập không còn hợp lệ.
8. Đọc và ánh xạ claims trong Java/Spring, đồng thời xây dựng ma trận kiểm thử OIDC.

## 2. Claim là gì?

Trong OpenID Connect, **claim** là một thông tin được một issuer đưa ra về một subject hoặc về ngữ cảnh xác thực. Claim có tên và giá trị; giá trị có thể là chuỗi, số, boolean, thời gian hoặc cấu trúc JSON tùy loại claim.

Ví dụ một Identity Provider có thể khẳng định:

- Subject có định danh ổn định là một giá trị cụ thể trong phạm vi issuer.
- Tên hiển thị của subject là An Nguyen.
- Email đã được issuer xác minh tại thời điểm phát hành.
- Người dùng đã xác thực vào một thời điểm nhất định.
- Phiên đăng nhập sử dụng một phương thức xác thực hoặc đạt một authentication context cụ thể.

Một claim là **lời khẳng định của issuer**. RP cần xác minh issuer và token/response trước khi sử dụng. Một trường JSON có tên email trong request body do browser gửi lên không trở thành OIDC claim chỉ vì nó có cùng tên.

Claims giúp RP hiểu danh tính và ngữ cảnh xác thực, nhưng không tự động quyết định mọi quyền truy cập. Ứng dụng vẫn phải áp dụng authorization, tenant membership, ownership và chính sách nghiệp vụ.

## 3. Claim, scope, role và permission khác nhau

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Claim** | Một thông tin được issuer khẳng định về subject hoặc authentication context | email_verified = true |
| **Scope** | Phạm vi dữ liệu hoặc quyền mà client yêu cầu theo giao thức | openid profile email |
| **Role** | Vai trò của principal trong tổ chức hoặc ứng dụng | HR_ADMIN |
| **Permission** | Quyền thực hiện action trên resource cụ thể | invoice:read trên INV-42 |
| **Client input** | Dữ liệu do client/browser tự gửi | displayName trong request body |
| **Authentication evidence** | Bằng chứng đã được verifier kiểm tra | passkey assertion hợp lệ |

Scope thường giúp yêu cầu một nhóm claims chuẩn. Ví dụ, scope profile yêu cầu nhóm thông tin hồ sơ cơ bản theo OIDC. Scope không có nghĩa mọi claim trong nhóm chắc chắn sẽ xuất hiện; việc phát hành còn phụ thuộc dữ liệu có sẵn, consent, policy và cấu hình IdP.

Role hoặc permission có thể được biểu diễn bằng custom claim trong một hệ thống, nhưng RP phải hiểu rõ issuer, semantics, freshness và nguồn dữ liệu của claim đó. Không nên coi một chuỗi role bất kỳ trong ID token là quyền quản trị nếu chưa có hợp đồng tin cậy rõ ràng.

## 4. Claims nằm ở đâu trong OIDC?

OIDC có ba thành phần cần phân biệt:

- **ID token:** JWT do OpenID Provider phát hành cho client để truyền đạt kết quả xác thực và các claims về subject/authentication event.
- **UserInfo endpoint:** endpoint được bảo vệ bằng access token, trả về claims về người dùng theo quyền và policy.
- **Access token:** credential dành cho resource server/API. Nó có thể là JWT hoặc opaque token; không mặc định là nơi RP lấy profile user và không được dùng thay ID token.

~~~mermaid
flowchart TD
    C["OIDC client / RP"] -->|"Authorization request + scopes / claims"| OP["OpenID Provider"]
    OP -->|"Authenticate user and apply policy"| OP
    OP -->|"ID token: subject + auth claims"| C
    OP -->|"Access token"| C
    C -->|"Access token"| UI["UserInfo endpoint"]
    UI -->|"User claims + sub"| C
    C -->|"Verify issuer, audience, signature, nonce and subject"| V["Trusted identity context"]
    V --> A["Application session and authorization"]
~~~

ID token và UserInfo có thể mang một phần claims giống nhau, nhưng RP phải xác minh mỗi nguồn theo đúng quy tắc. UserInfo response phải được lấy qua TLS từ endpoint của issuer đáng tin cậy và claim sub trong response phải khớp subject của ID token.

## 5. Các claim chuẩn trong ID token

Một ID token thường có các claim nền tảng:

| Claim | Ý nghĩa | Cách RP sử dụng |
|---|---|---|
| **iss** | Issuer phát hành token | So khớp chính xác issuer đã cấu hình |
| **sub** | Định danh subject trong phạm vi issuer | Dùng cùng iss làm khóa định danh federation |
| **aud** | Audience, thường chứa client ID của RP | Xác nhận token dành cho đúng client |
| **exp** | Thời điểm token hết hạn | Từ chối token sau thời điểm này, có clock skew nhỏ theo policy |
| **iat** | Thời điểm token được phát hành | Kiểm tra tính hợp lý và độ mới theo policy |
| **auth_time** | Thời điểm user thực sự xác thực gần nhất | Đánh giá freshness khi cần re-authentication |
| **nonce** | Giá trị ràng buộc token với authorization request | So khớp với nonce RP đã gửi |
| **acr** | Authentication Context Class Reference | Diễn giải mức/ngữ cảnh xác thực theo hợp đồng với IdP |
| **amr** | Authentication Methods References | Thông tin về phương thức xác thực được dùng |
| **azp** | Authorized party, thường là client được ủy quyền khi aud có nhiều giá trị | Kiểm tra theo quy tắc OIDC khi cần |
| **at_hash** | Hash của access token trong một số response flow | Xác minh quan hệ giữa ID token và access token khi áp dụng |
| **c_hash** | Hash của authorization code trong một số response flow | Xác minh quan hệ code/token khi áp dụng |

Các claim tùy chọn không nhất thiết xuất hiện trong mọi ID token. RP không nên yêu cầu một claim tùy chọn nếu use case không cần, và không nên suy diễn giá trị thiếu thành một kết quả xác thực cụ thể.

### Issuer và subject phải được dùng cùng nhau

Giá trị sub chỉ có ý nghĩa trong phạm vi issuer. Hai IdP khác nhau có thể phát hành cùng chuỗi sub cho hai người khác nhau. Khóa định danh federation nên là:

~~~text
federated_identity_key = (iss, sub)
~~~

Không dùng sub đơn lẻ trên nhiều issuer. Không mặc định email hoặc username là định danh bất biến.

## 6. Claims hồ sơ người dùng

OIDC định nghĩa các standard profile claims để client có thể yêu cầu thông tin người dùng. Một số ví dụ:

| Claim | Kiểu dữ liệu thường gặp | Ý nghĩa |
|---|---|---|
| name | string | Tên đầy đủ hoặc tên hiển thị |
| given_name | string | Tên |
| family_name | string | Họ |
| middle_name | string | Tên đệm |
| nickname | string | Biệt danh |
| preferred_username | string | Tên đăng nhập ưu tiên do issuer cung cấp |
| profile | string | URL hồ sơ |
| picture | string | URL ảnh đại diện |
| website | string | Website |
| gender | string | Thông tin giới tính nếu được cung cấp |
| birthdate | string | Ngày sinh theo quy ước OIDC |
| zoneinfo | string | Múi giờ |
| locale | string | Ngôn ngữ/khu vực ưu tiên |
| updated_at | number | Thời điểm thông tin hồ sơ được cập nhật |
| email | string | Địa chỉ email |
| email_verified | boolean | Issuer khẳng định email đã được xác minh |
| phone_number | string | Số điện thoại |
| phone_number_verified | boolean | Issuer khẳng định số điện thoại đã được xác minh |
| address | JSON object | Địa chỉ có cấu trúc |

Một số lưu ý:

- name, email và preferred_username có thể thay đổi; không dùng làm primary key.
- email_verified = true có nghĩa issuer đã xác minh email theo chính sách của họ tại thời điểm khẳng định. Nó không chứng minh email sẽ luôn thuộc quyền kiểm soát của cùng người đó trong tương lai.
- phone_number_verified cũng cần được hiểu trong ngữ cảnh thời điểm và chính sách xác minh của issuer.
- picture/profile là URL hoặc dữ liệu tham chiếu bên ngoài; không tự động tải và tin nội dung từ URL đó.
- birthdate, address, phone_number và các dữ liệu hồ sơ khác có thể nhạy cảm; chỉ yêu cầu nếu ứng dụng thực sự cần.

## 7. Scope chuẩn và claims được yêu cầu

OIDC Core định nghĩa các scope chuẩn để yêu cầu nhóm claims:

| Scope | Nhóm claims thường liên quan |
|---|---|
| openid | Bắt buộc để biến OAuth authorization request thành OIDC authentication request |
| profile | Các claims hồ sơ như name, family_name, given_name, picture, locale, updated_at |
| email | email và email_verified |
| address | address |
| phone | phone_number và phone_number_verified |

Scope yêu cầu một nhóm thông tin, không bảo đảm mọi claim sẽ có mặt. IdP có thể không có dữ liệu, user có thể không consent hoặc policy có thể hạn chế phát hành.

Ví dụ authorization request:

~~~http
GET /authorize?
  response_type=code&
  client_id=portal-web&
  redirect_uri=https%3A%2F%2Fportal.example.test%2Fcallback&
  scope=openid%20profile%20email&
  state=random-state&
  nonce=random-nonce
~~~

Trong Authorization Code Flow, RP nên dùng PKCE, state, nonce và redirect URI đăng ký chính xác. Ví dụ chỉ minh họa các tham số chính, không phải URL production hoàn chỉnh.

## 8. Claims Request Parameter

Ngoài scope, OIDC hỗ trợ **claims request parameter** để client yêu cầu các claim cụ thể và có thể chỉ rõ claim cần xuất hiện trong ID token hoặc UserInfo. Cơ chế này giúp yêu cầu dữ liệu chi tiết hơn so với nhóm scope.

Ví dụ minh họa:

~~~json
{
  "userinfo": {
    "email": {
      "essential": true
    },
    "name": null
  },
  "id_token": {
    "auth_time": {
      "essential": true
    },
    "acr": {
      "values": ["urn:example:loa:2"]
    }
  }
}
~~~

Ý nghĩa:

- Client yêu cầu email và đánh dấu essential để biểu đạt claim cần thiết cho use case.
- Client yêu cầu name trong UserInfo.
- Client yêu cầu auth_time trong ID token.
- Client yêu cầu một giá trị acr cụ thể theo profile đã thỏa thuận với IdP.

Đánh dấu essential không buộc IdP phải phát hành claim nếu không thể hoặc policy không cho phép. Authorization server có thể từ chối request hoặc xử lý theo chính sách; RP phải xử lý trường hợp claim không được trả về.

Claims request không phải cách bỏ qua consent. Client chỉ nên yêu cầu thông tin cần thiết và giải thích rõ mục đích sử dụng.

## 9. ID token và UserInfo: cùng subject, khác thời điểm và nguồn

ID token là một snapshot về subject và authentication event tại thời điểm phát hành. UserInfo endpoint có thể trả về profile claims hiện tại hoặc theo policy của IdP khi endpoint được gọi.

Ví dụ:

1. Người dùng đăng nhập lúc 09:00; ID token có email và auth_time.
2. Người dùng đổi email ở IdP lúc 10:00.
3. RP gọi UserInfo lúc 10:05 và nhận email mới.
4. ID token cũ vẫn chứa claim email tại thời điểm token được phát hành.

RP không nên giả định mọi claim trong ID token luôn đồng bộ với UserInfo hoặc directory tại mọi thời điểm.

### Kiểm tra UserInfo subject

Sau khi gọi UserInfo bằng access token:

- Xác minh kết nối TLS và endpoint thuộc issuer đã cấu hình.
- Gửi access token theo cách thức quy định, thông thường là Authorization Bearer header.
- Parse response theo schema/profile.
- So khớp claim sub trong UserInfo với sub trong ID token đã xác minh.
- Nếu subject không khớp, không hợp nhất hai response thành một identity context.

Không dùng access token của một issuer hoặc resource khác để gọi endpoint UserInfo tùy ý.

## 10. Authentication context: auth_time, acr và amr

Claims về authentication context giúp RP quyết định liệu phiên hiện tại có đáp ứng yêu cầu xác thực của một thao tác hay không.

### auth_time

auth_time biểu thị thời điểm người dùng thực sự xác thực. Nó hữu ích khi RP cần biết lần xác thực gần nhất đã quá cũ hay chưa.

Ví dụ, một ứng dụng có thể yêu cầu user xác thực trong vòng 5 phút trước khi đổi phương thức MFA. RP phải so sánh thời gian theo clock đáng tin và policy của mình; không chỉ dựa vào thời điểm token được phát hành iat.

### acr

acr mô tả Authentication Context Class. Giá trị cụ thể phụ thuộc profile và hợp đồng giữa RP với IdP. Một chuỗi như urn:example:loa:2 không tự động tương đương một AAL chuẩn hoặc một mức assurance chung trên mọi nhà cung cấp.

RP cần:

- Định nghĩa trước giá trị acr được chấp nhận.
- Xác nhận IdP thực sự bảo đảm semantics đó.
- Xử lý giá trị không biết hoặc thiếu theo policy.
- Dùng max_age hoặc yêu cầu xác thực phù hợp khi cần freshness.

### amr

amr là danh sách phương thức xác thực được dùng, theo semantics của issuer/profile. Ví dụ có thể có pwd, otp, sms, hwk hoặc phương thức khác theo quy ước tương ứng.

Không suy ra rằng hai phần tử trong amr chắc chắn là hai yếu tố độc lập, hoặc rằng một giá trị amr cụ thể chống phishing. RP phải có hợp đồng về ý nghĩa, cách IdP xác minh và assurance thực tế.

## 11. Yêu cầu xác thực mới bằng max_age và prompt

OIDC có các tham số giúp client yêu cầu tương tác hoặc xác thực gần đây:

- **max_age:** giới hạn thời gian tối đa kể từ lần user xác thực; nếu vượt quá, OP phải thực hiện xác thực lại theo quy tắc OIDC.
- **prompt=login:** yêu cầu OP hiển thị luồng xác thực thay vì âm thầm dùng phiên hiện tại, theo semantics của OP.
- **prompt=none:** yêu cầu xử lý không tương tác; nếu không thể hoàn thành, OP trả lỗi phù hợp thay vì hiển thị UI.
- **acr_values:** gợi ý hoặc yêu cầu authentication context theo profile/contract được hỗ trợ; cần hiểu semantics cụ thể của OP.

Ví dụ:

~~~text
scope=openid profile
max_age=300
prompt=login
~~~

max_age và auth_time có quan hệ trực tiếp: RP có thể kiểm tra thời điểm xác thực được IdP khẳng định. Không nhầm iat (thời điểm token phát hành) với auth_time (thời điểm user xác thực).

## 12. Xác minh claims trước khi tin

Claim trong ID token chỉ đáng tin sau khi RP xác minh token theo OIDC:

1. Lấy issuer từ cấu hình tin cậy hoặc discovery đã xác minh; không lấy issuer tùy tiện từ input không tin cậy.
2. Lấy signing keys từ JWKS endpoint thuộc issuer đã cấu hình, xử lý key rotation an toàn.
3. Xác minh chữ ký bằng thuật toán được cho phép và key phù hợp.
4. So khớp iss chính xác.
5. Kiểm tra aud chứa client ID của RP; kiểm tra azp khi quy tắc OIDC yêu cầu.
6. Kiểm tra exp, iat và các giới hạn thời gian.
7. So khớp nonce nếu request đã gửi nonce.
8. Kiểm tra token type/profile và các claim bắt buộc của ứng dụng.
9. Chỉ sau đó mới tạo authenticated principal và sử dụng profile claims.

Không chỉ Base64-decode payload rồi tin các giá trị. Không chấp nhận token vì nó có claim sub/email trông hợp lý.

### JWT claim không đồng nghĩa dữ liệu bí mật

JWT thường chỉ được ký, không mã hóa. Header và payload có thể được đọc bởi bên nhận token. Không đưa mật khẩu, private key, client secret, recovery code hoặc dữ liệu nhạy cảm không cần thiết vào ID token.

Nếu cần bảo vệ tính bí mật của claim, phải dùng cơ chế encryption/profile phù hợp và xác định rõ RP nào được phép giải mã. Chữ ký bảo vệ tính toàn vẹn và nguồn phát hành; nó không che nội dung.

## 13. Identity mapping và account linking

RP cần một khóa ổn định để nhận diện cùng một subject qua các lần đăng nhập:

~~~text
identity_key = issuer + subject

Example:
issuer  = https://identity.example.test
subject = 00u123example
~~~

Không dùng các trường sau làm khóa federation duy nhất:

- email: có thể đổi, tái sử dụng hoặc trùng giữa issuer.
- preferred_username: có thể đổi và không nhất thiết duy nhất.
- name: có thể trùng và không ổn định.
- phone_number: có thể thay đổi hoặc được cấp lại cho người khác.

Nếu hỗ trợ liên kết tài khoản local với IdP mới, yêu cầu user chứng minh kiểm soát tài khoản hiện tại và tài khoản liên kết theo quy trình có assurance phù hợp. Không tự động hợp nhất chỉ vì email giống nhau.

### Pairwise subject identifiers

OIDC cho phép subject identifier có tính chất public hoặc pairwise tùy cấu hình. Pairwise subject có thể khác nhau giữa các sector/client để giảm khả năng các RP liên kết hoạt động người dùng với nhau.

Hệ quả:

- Cùng một người có thể có sub khác nhau ở hai client/sector.
- RP không nên so sánh sub giữa hai client khác nhau để kết luận là cùng người.
- Nếu cần liên kết giữa các ứng dụng, dùng cơ chế account linking hoặc định danh tổ chức được phê duyệt, không tự suy đoán từ claim công khai.

## 14. Custom claims và namespace

IdP hoặc authorization server có thể phát hành custom claims để truyền thuộc tính tổ chức hoặc ngữ cảnh riêng, ví dụ:

~~~json
{
  "https://claims.example.test/tenant_id": "tenant-42",
  "https://claims.example.test/department": "finance",
  "https://claims.example.test/employee_type": "staff"
}
~~~

Nên dùng namespace ổn định để tránh xung đột tên với standard claims hoặc custom claims từ bên khác.

Trước khi dùng custom claim, cần xác định:

- Ai là nguồn dữ liệu có thẩm quyền?
- Claim được cập nhật và đồng bộ bao lâu một lần?
- Claim có thể thiếu, null hoặc có kiểu dữ liệu khác không?
- Claim có nhạy cảm hoặc chứa PII không?
- RP dùng claim để hiển thị, định tuyến hay ra quyết định authorization?
- Khi thuộc tính thay đổi, token cũ còn hiệu lực bao lâu?

Không đưa quyền admin rộng vào claim chỉ để đơn giản hóa code nếu role có thể thay đổi nhanh hoặc phụ thuộc resource. Với quyền nhạy cảm, cân nhắc tra cứu policy server-side hoặc token lifetime ngắn.

## 15. Aggregated và distributed claims

OIDC hỗ trợ mô hình claims nâng cao:

- **Aggregated claims:** claim được lấy từ một nguồn khác và được issuer đưa vào response dưới dạng dữ liệu đã được ký bởi nguồn đó, theo cấu trúc OIDC.
- **Distributed claims:** response chỉ ra endpoint và thông tin tham chiếu để client lấy claim từ nguồn bên ngoài.

Những mô hình này hữu ích khi profile tổng hợp thuộc tính từ nhiều nguồn, nhưng tạo thêm trust boundary:

- RP phải xác minh nguồn claim theo cấu trúc giao thức.
- Endpoint phân phối phải được tin cậy và bảo vệ.
- Access token dùng để lấy claim cần đúng audience/endpoint.
- Phải kiểm soát SSRF và không tùy tiện gọi URL claim do input không tin cậy cung cấp.
- Chỉ lấy claim cần thiết, giới hạn thời gian và xử lý lỗi nguồn dữ liệu.

Không biến URL trong response thành lệnh gọi HTTP tùy ý. Chỉ truy cập endpoint được xác thực và được policy cho phép.

## 16. Privacy và data minimization

Claims thường chứa dữ liệu cá nhân. Client nên yêu cầu và lưu tối thiểu:

1. Chỉ yêu cầu scope/claim cần cho chức năng cụ thể.
2. Không yêu cầu birthdate, address, phone hoặc profile đầy đủ chỉ để lấy email.
3. Giải thích mục đích và hiển thị consent rõ ràng.
4. Tránh lưu profile claims lâu hơn nhu cầu; đồng bộ lại khi cần.
5. Không ghi ID token/UserInfo đầy đủ vào log hoặc analytics.
6. Giới hạn quyền truy cập database chứa profile và audit dữ liệu nhạy cảm.
7. Xử lý xóa, sửa và retention theo chính sách quyền riêng tư áp dụng.
8. Không chia sẻ claims giữa tenant hoặc client nếu không có cơ sở và mục đích rõ ràng.

Một claim được IdP phát hành không có nghĩa RP được phép sử dụng cho mọi mục đích. Việc nhận dữ liệu và việc xử lý dữ liệu là hai trách nhiệm riêng.

## 17. Claim freshness và dữ liệu cũ

Claims trong ID token là snapshot tại thời điểm phát hành. Một số thuộc tính thay đổi chậm như tên; một số thuộc tính như role, employment status, tenant membership hoặc account disabled có thể thay đổi ngay sau đó.

Các chiến lược:

- Dùng ID token để thiết lập danh tính ban đầu, không dùng nó làm nguồn sự thật vô thời hạn.
- Với thuộc tính ít nhạy cảm, có thể cache theo thời hạn rõ ràng.
- Với quyền nhạy cảm, kiểm tra trạng thái/policy server-side.
- Dùng event/provisioning để cập nhật role, nhưng có đường revoke khẩn cấp khi đồng bộ trễ.
- Giới hạn local session lifetime hoặc yêu cầu re-authentication khi claim/authentication context đã cũ.
- Ghi nhận thời điểm đồng bộ và nguồn dữ liệu của custom claims.

Không coi claim email_verified hoặc group membership là trạng thái bất biến. Chính sách cần xác định mức stale tối đa chấp nhận được cho từng thuộc tính.

## 18. Java/Spring: đọc claims từ OIDC principal

Spring Security hỗ trợ OIDC Login và cung cấp OidcUser sau khi token được xác minh bởi framework. Ví dụ:

~~~java
@Service
class OidcProfileMapper {

    UserProfile map(OidcUser oidcUser) {
        String subject = oidcUser.getSubject();
        String issuer = oidcUser.getIdToken()
            .getIssuer()
            .toString();

        String email = oidcUser.getEmail();
        Boolean emailVerified = oidcUser.getEmailVerified();
        String displayName = oidcUser.getFullName();

        return new UserProfile(
            issuer,
            subject,
            email,
            Boolean.TRUE.equals(emailVerified),
            displayName
        );
    }
}
~~~

Đây là ví dụ khung; UserProfile do ứng dụng định nghĩa. Giá trị emailVerified có thể null/không được cung cấp; không được diễn giải thiếu claim thành true.

### Lưu định danh federation ổn định

~~~java
@Service
class FederatedAccountService {
    private final FederatedAccountRepository repository;

    FederatedAccountService(FederatedAccountRepository repository) {
        this.repository = repository;
    }

    Account resolve(OidcUser user) {
        String issuer = user.getIdToken()
            .getIssuer()
            .toString();
        String subject = user.getSubject();

        return repository.findByIssuerAndSubject(issuer, subject)
            .orElseThrow(UnknownFederatedIdentityException::new);
    }
}
~~~

Không tự động fallback sang tìm account theo email nếu cặp issuer/subject chưa tồn tại. Việc enrollment hoặc linking cần một flow riêng, xác minh quyền kiểm soát tài khoản hiện có và ghi audit.

### Đọc authentication context

~~~java
Instant authTime = oidcUser.getIdToken().getClaimAsInstant("auth_time");
String acr = oidcUser.getIdToken().getClaimAsString("acr");
List<String> amr = oidcUser.getIdToken().getClaimAsStringList("amr");
~~~

Các claim có thể không hiện diện hoặc có kiểu dữ liệu khác theo profile. Cần kiểm tra null, kiểm tra semantics theo hợp đồng IdP và không dùng tên acr/amr tùy ý để tuyên bố đạt một mức assurance chuẩn.

### UserInfo

~~~java
OidcUserInfo userInfo = oidcUser.getUserInfo();
if (userInfo != null) {
    String userInfoSubject = userInfo.getSubject();
    if (!oidcUser.getSubject().equals(userInfoSubject)) {
        throw new IllegalStateException("OIDC subject mismatch");
    }
}
~~~

Framework hỗ trợ gọi UserInfo theo cấu hình client. Ứng dụng vẫn cần xử lý trường hợp endpoint lỗi, response thiếu claim và subject mismatch; không hợp nhất dữ liệu nếu subject không khớp.

## 19. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Tin claim trước khi verify ID token | Attacker có thể giả issuer, subject hoặc role | Xác minh chữ ký, iss, aud, exp, nonce và profile |
| Dùng email làm primary key | Account linking sai khi email đổi/trùng/tái sử dụng | Dùng cặp issuer + subject |
| Dùng ID token để gọi API | Nhầm authentication token với access token | Dùng access token đúng audience |
| Coi scope profile bảo đảm mọi profile claim có mặt | Code lỗi khi claim thiếu | Xử lý optional claims và policy |
| Coi email_verified là vĩnh viễn | Tin email cũ hoặc email đã được tái cấp | Xem thời điểm, issuer policy và xác minh lại khi cần |
| Tin acr/amr mà không có hợp đồng | Đánh giá sai assurance/phishing resistance | Thống nhất semantics với IdP và kiểm thử |
| Dùng claim role cũ để cấp quyền mãi mãi | Quyền không bị thu hồi khi tổ chức thay đổi | Re-evaluate policy và giới hạn freshness |
| Không so khớp UserInfo sub | Trộn profile của subject khác | Bắt buộc subject match |
| Ghi toàn bộ token/UserInfo vào log | Rò rỉ PII và credential | Log metadata tối thiểu, redact token |
| Yêu cầu mọi claim dù không cần | Thu thập quá mức và tăng trách nhiệm privacy | Data minimization và consent |
| Gọi URL distributed claim tùy ý | Nguy cơ SSRF hoặc rò token | Chỉ gọi endpoint tin cậy, kiểm tra host/audience |
| Dùng pairwise sub như định danh toàn cục | Liên kết sai hoặc không nhận ra cùng subject | Tôn trọng sector boundary và flow linking riêng |

## 20. Ma trận kiểm thử OIDC claims

| Kiểm thử | Kết quả mong đợi |
|---|---|
| ID token có chữ ký không hợp lệ | RP từ chối |
| Issuer không nằm trong cấu hình tin cậy | RP từ chối |
| Audience không chứa client ID | RP từ chối |
| Nonce không khớp request | RP từ chối |
| ID token hết hạn | RP từ chối |
| Token thiếu claim tùy chọn name | Ứng dụng xử lý theo policy, không crash |
| email_verified thiếu hoặc null | Không tự coi email đã xác minh |
| email thay đổi giữa ID token và UserInfo | RP áp dụng quy tắc freshness; không đổi khóa định danh |
| UserInfo sub khác ID token sub | RP từ chối hợp nhất response |
| Cùng email từ hai issuer | Không tự động liên kết tài khoản |
| Cùng sub từ hai issuer | Tạo hai federation identity khác nhau |
| Pairwise sub khác giữa hai client | Không tự suy luận đó là hai người khác nhau hoặc cùng người |
| auth_time quá cũ cho thao tác nhạy cảm | Yêu cầu re-authentication/step-up |
| acr không nằm trong allowlist | Không coi là assurance đáp ứng |
| amr chứa giá trị không biết | Không tự suy ra mức MFA/phishing resistance |
| Custom claim role bị thay đổi | Quyền được kiểm tra theo nguồn/policy tin cậy |
| JWT payload bị sửa nhưng chữ ký không hợp lệ | RP từ chối |
| UserInfo endpoint lỗi | Không tạo claim giả hoặc bỏ qua xác minh |
| Distributed claim trỏ tới host không tin cậy | RP không gọi endpoint đó |
| ID token được gửi tới resource API | API từ chối token sai mục đích/audience |
| Claims request đánh dấu essential nhưng IdP không trả claim | Client xử lý lỗi/thiếu dữ liệu theo use case |
| Log trong quá trình callback | Không chứa ID token, access token hoặc PII không cần thiết |

Kiểm thử bằng issuer, client và user giả lập trong môi trường test. Không dùng ID token, email, số điện thoại hoặc profile claims thật của người dùng trong fixture công khai.

## 21. Tình huống phân tích

### Tình huống A: hai issuer có cùng email

Ứng dụng đã có local account cho an@example.test. Một IdP đối tác phát hành ID token có cùng email và email_verified=true. RP tự động liên kết hai tài khoản.

**Phân tích:** email không đủ để xác định cùng một subject qua hai issuer. RP phải dùng issuer + subject và yêu cầu một quy trình linking có xác minh quyền kiểm soát local account.

### Tình huống B: claim role cũ vẫn còn trong token

Một nhân viên bị gỡ khỏi nhóm Finance nhưng ID token cũ vẫn chứa custom claim department=finance và role=FINANCE_ADMIN.

**Phân tích:** claim là snapshot tại thời điểm phát hành. Với thao tác tài chính nhạy cảm, RP cần kiểm tra quyền hiện tại ở policy store hoặc dùng token/session lifetime ngắn và cơ chế revoke đồng bộ.

### Tình huống C: UserInfo subject không khớp

RP lấy access token của An nhưng UserInfo response trả về sub của Bình do cấu hình endpoint hoặc token mapping sai.

**Phân tích:** không hợp nhất claims. Từ chối response, ghi incident/configuration error và kiểm tra issuer, audience, token và endpoint.

### Tình huống D: RP hiểu sai acr

IdP phát hành acr với giá trị nội bộ có chữ high. RP tự coi đó là MFA chống phishing mà không có tài liệu semantics.

**Phân tích:** tên chuỗi không chứng minh assurance. RP và IdP phải thống nhất profile, phương thức, yêu cầu freshness và cách xác minh; nếu không, RP phải yêu cầu một context đã được định nghĩa hoặc từ chối thao tác.

### Tình huống E: ứng dụng yêu cầu quá nhiều profile data

Ứng dụng chỉ cần biết user có email liên hệ nhưng yêu cầu profile, address, phone và birthdate.

**Phân tích:** yêu cầu vượt mục đích. Giảm scope/claims về mức cần thiết, giải thích consent và tránh lưu dữ liệu không phục vụ chức năng.

## 22. Quy trình thiết kế và vận hành

Trước khi sử dụng claims trong ứng dụng, hãy xác định:

1. Claim nào cần cho đăng nhập, hồ sơ, định tuyến hoặc authorization?
2. Claim đến từ ID token, UserInfo hay nguồn custom nào?
3. Issuer và semantics của claim có được tài liệu hóa không?
4. RP xác minh chữ ký, issuer, audience, expiration, nonce và token profile ra sao?
5. UserInfo sub có được so khớp với ID token sub không?
6. Identity key có dùng cặp issuer + subject không?
7. Claim nào có thể thay đổi, và độ stale tối đa chấp nhận được là bao lâu?
8. Custom role/group claim có nguồn authoritative, version và revoke path không?
9. auth_time, acr, amr được diễn giải theo hợp đồng nào?
10. Scope và claims request có tối thiểu, consent có rõ ràng không?
11. PII có được hạn chế trong log, cache, database và analytics không?
12. Pairwise subject, account linking và distributed claims có được xử lý đúng trust boundary không?
13. Khi IdP hoặc UserInfo lỗi, ứng dụng có fallback an toàn không?
14. Có kiểm thử claim thiếu, sai kiểu, stale, sai issuer và subject mismatch không?

## 23. Ghi nhớ trọng tâm

- **Claim là lời khẳng định của issuer** về subject hoặc authentication context; chỉ tin sau khi xác minh nguồn và giao thức.
- **ID token, access token và UserInfo có mục đích khác nhau.** Không dùng ID token thay access token để gọi API.
- **Issuer + subject là định danh federation ổn định.** Email, tên và username có thể thay đổi hoặc trùng.
- **Scope yêu cầu nhóm claims, không bảo đảm mọi claim sẽ có mặt.** Consent, dữ liệu và policy của IdP vẫn quyết định.
- **auth_time, acr và amr cần semantics được thống nhất.** Không tự suy ra MFA hoặc phishing resistance từ một chuỗi claim.
- **UserInfo sub phải khớp ID token sub.** Không trộn dữ liệu của hai subject.
- **Claims có thể stale.** Role, group và trạng thái nhân sự nhạy cảm cần kiểm tra freshness hoặc policy server-side.
- **Custom claims phải có namespace, owner và vòng đời.** Không biến claim cũ thành quyền vĩnh viễn.
- **Data minimization là yêu cầu thiết kế.** Chỉ yêu cầu, lưu và chia sẻ dữ liệu cần cho mục đích đã xác định.

Claims là hợp đồng dữ liệu giữa OpenID Provider và Relying Party. Khi RP hiểu đúng nguồn, semantics, thời điểm và phạm vi của từng claim, ứng dụng có thể xây dựng identity context đáng tin cậy mà không nhầm dữ liệu hồ sơ với bằng chứng xác thực hoặc quyền truy cập.
