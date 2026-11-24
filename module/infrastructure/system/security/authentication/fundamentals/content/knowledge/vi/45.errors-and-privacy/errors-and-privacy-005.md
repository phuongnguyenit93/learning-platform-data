# Sensitive claim — Bảo vệ dữ liệu nhạy cảm trong claim xác thực và liên kết danh tính

> **Chương:** Error và privacy  
> **Chủ đề:** Sensitive claim  
> **Phạm vi:** Security Authentication Fundamentals — nhận diện và quản lý claim nhạy cảm trong token, assertion và API identity; giảm thiểu dữ liệu phát hành, giới hạn audience/purpose, bảo vệ tính bí mật, kiểm soát truy cập, lưu trữ, logging và vòng đời dữ liệu.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích claim là gì và phân biệt claim về danh tính, thuộc tính, ngữ cảnh, quyền và trạng thái xác thực.
2. Phân loại dữ liệu theo mức nhạy cảm và mục đích xử lý.
3. Giải thích vì sao payload của JWT ký số thông thường vẫn đọc được.
4. Phân biệt ID token, access token, UserInfo response và SAML assertion về mục đích, audience và dữ liệu.
5. Áp dụng data minimization, purpose limitation và least disclosure khi phát hành claim.
6. Thiết kế scope, audience, pairwise subject và claim release policy phù hợp.
7. Chọn giữa signed JWT, encrypted JWT và opaque token theo yêu cầu integrity/confidentiality.
8. Ngăn claim nhạy cảm rò rỉ qua browser, mobile storage, log, trace, cache và support tooling.
9. Quản lý claim freshness, revocation, retention và quyền truy cập dữ liệu.
10. Xây dựng threat model, kiểm thử và checklist bảo vệ sensitive claim.

## 1. Claim là gì trong hệ thống xác thực?

**Claim** là một phát biểu hoặc thuộc tính mà một bên có thẩm quyền cung cấp về một subject hoặc về ngữ cảnh xác thực. Trong hệ thống identity, claim thường được biểu diễn dưới dạng tên và giá trị, sau đó đưa vào token, assertion hoặc response.

Ví dụ:

- Subject identifier: định danh người dùng hoặc workload;
- Email và trạng thái email đã xác minh;
- Tên hiển thị, ngôn ngữ hoặc timezone;
- Tenant, organization hoặc department;
- Authentication time và authentication method;
- Mức assurance hoặc trạng thái MFA;
- Role, group hoặc permission;
- Ngày sinh, địa chỉ, số điện thoại;
- Thuộc tính tài chính, sức khỏe hoặc dữ liệu nhân sự.

Claim có thể đến từ account database, identity provider, HR system, customer profile, device registry hoặc policy engine. Việc một claim xuất hiện trong token không tự chứng minh rằng dữ liệu còn mới, đúng mục đích hoặc được phép chia sẻ với mọi recipient.

### Claim không đồng nghĩa với quyền

Một claim mô tả điều mà issuer tuyên bố. Authorization policy quyết định caller có được phép làm gì.

Ví dụ, claim department=finance không tự cấp quyền xem mọi hồ sơ tài chính. Resource server phải kiểm tra issuer, audience, subject, scope, policy và context trước khi quyết định.

### Nguồn gốc và độ tin cậy

Mỗi claim nên có nguồn gốc rõ:

- Ai phát hành claim?
- Dữ liệu được lấy từ hệ thống nào?
- Issuer đã xác minh thuộc tính bằng cách nào?
- Claim được cập nhật lần cuối khi nào?
- Claim được phát hành cho mục đích nào?
- Recipient nào được phép nhận?

Không nên biến dữ liệu do người dùng tự nhập thành claim đã được xác minh nếu chưa có quy trình xác minh phù hợp.

## 2. Sensitive claim là gì?

**Sensitive claim** là claim chứa hoặc tiết lộ dữ liệu cần được bảo vệ do có thể gây hại cho cá nhân, tổ chức hoặc hệ thống nếu bị lộ, bị sửa, bị liên kết sai mục đích hoặc được sử dụng ngoài phạm vi cho phép.

Mức nhạy cảm phụ thuộc vào nội dung, ngữ cảnh, khả năng liên kết với người thật và hậu quả khi bị sử dụng sai.

### Ví dụ theo nhóm dữ liệu

| Nhóm | Ví dụ | Rủi ro |
| --- | --- | --- |
| Định danh trực tiếp | Email, số điện thoại, mã nhân viên | Phishing, account enumeration, liên kết hoạt động giữa dịch vụ |
| Định danh chính thức | Số giấy tờ, mã định danh quốc gia | Mạo danh, gian lận, đánh cắp danh tính |
| Định vị/liên hệ | Địa chỉ nhà, vị trí chính xác | Theo dõi, xâm phạm riêng tư và an toàn cá nhân |
| Tài chính | Tài khoản ngân hàng, thu nhập, trạng thái thanh toán | Gian lận và phân biệt đối xử |
| Sức khỏe | Chẩn đoán, thuốc, bảo hiểm, dữ liệu sinh trắc học sức khỏe | Xâm phạm đời tư và hậu quả pháp lý/xã hội |
| Nhân sự | Lương, đánh giá, disciplinary status | Lạm dụng nội bộ và tổn hại nghề nghiệp |
| Bảo mật | MFA enrollment, recovery status, credential metadata | Hỗ trợ attacker vượt kiểm soát tài khoản |
| Hành vi/ngữ cảnh | Device fingerprint, vị trí, lịch sử đăng nhập | Theo dõi và profiling |
| Tổ chức | Tenant nội bộ, nhóm đặc quyền, cấu trúc hệ thống | Reconnaissance và privilege targeting |

Không phải mọi email hoặc tên đều có cùng mức nhạy cảm trong mọi hệ thống. Một email công khai có thể ít nhạy cảm hơn email cá nhân dùng làm định danh đăng nhập; một claim đơn lẻ có thể vô hại nhưng khi kết hợp nhiều claim lại tạo hồ sơ có độ nhạy cảm cao.

### Dữ liệu nhạy cảm theo tổ hợp

Các claim riêng lẻ có thể trở nên nhạy cảm khi kết hợp:

- Email + department + location có thể nhận diện nhân viên và nơi làm việc;
- Tenant + role + group có thể tiết lộ cấu trúc tổ chức;
- Authentication time + device + IP có thể tạo lịch sử hoạt động;
- Birth date + postal code có thể hỗ trợ xác minh danh tính;
- Health condition + employer có thể tiết lộ dữ liệu sức khỏe trong ngữ cảnh nghề nghiệp.

Phân loại phải xem xét cả dữ liệu kết hợp, không chỉ từng field riêng lẻ.

## 3. Phân loại claim và chính sách xử lý

Trước khi đưa claim vào token hoặc response, cần xác định mức độ nhạy cảm và mục đích sử dụng.

### Một mô hình phân loại tham khảo

| Mức | Đặc điểm | Cách xử lý |
| --- | --- | --- |
| Public | Có thể công khai và ít gây hại | Chỉ phát hành khi có nhu cầu |
| Internal | Dành cho hệ thống/tổ chức nội bộ | Giới hạn audience và logging |
| Confidential | Có thể nhận diện cá nhân hoặc tiết lộ thông tin nghiệp vụ | Data minimization, access control, retention |
| Restricted | Dữ liệu đặc biệt nhạy cảm hoặc có hậu quả lớn | Tránh phát hành rộng; cần purpose, approval và kiểm soát mạnh |

Đây là ví dụ taxonomy nội bộ. Tổ chức cần ánh xạ với chính sách phân loại dữ liệu và quy định áp dụng tại nơi hoạt động.

### Thuộc tính cần ghi cho mỗi claim

- Name và schema/type;
- Data owner và authoritative source;
- Classification;
- Purpose/legal basis hoặc policy basis phù hợp;
- Issuer và recipient/audience được phép;
- Thời điểm xác minh và freshness requirement;
- Retention và deletion rule;
- Có được đưa vào token hay chỉ trả qua API riêng;
- Có được log, cache, export hoặc dùng trong analytics không.

### Không phát hành chỉ vì claim sẵn có

Identity provider có thể biết nhiều thông tin về người dùng, nhưng client chỉ nên nhận phần cần cho transaction hiện tại. Việc dễ thêm claim vào token không phải lý do để phát hành.

## 4. Data minimization và purpose limitation

**Data minimization** là chỉ thu thập, sử dụng và chia sẻ dữ liệu cần thiết cho mục đích cụ thể. **Purpose limitation** yêu cầu dữ liệu được sử dụng trong phạm vi mục đích đã xác định và được phép.

### Câu hỏi trước khi phát hành claim

1. Client thực sự cần biết điều gì để hoàn thành chức năng?
2. Có thể dùng boolean hoặc kết quả quyết định thay cho dữ liệu gốc không?
3. Có thể dùng subject identifier riêng cho client thay email hoặc mã nhân viên không?
4. Claim cần trong mọi request hay chỉ tại một endpoint?
5. Có thể truy vấn dữ liệu qua API được bảo vệ thay vì đưa vào token không?
6. Recipient có được phép xử lý claim cho mục đích này không?
7. Claim sẽ tồn tại bao lâu trong token, log, cache và backup?

### Thay dữ liệu gốc bằng kết quả tối thiểu

Ví dụ, thay vì phát hành ngày sinh đầy đủ, service có thể cung cấp claim age_over_18=true nếu ứng dụng chỉ cần kiểm tra điều kiện tuổi. Thay vì đưa toàn bộ department và HR attributes, policy service có thể trả quyết định can_view_resource=true cho một transaction cụ thể.

Giải pháp thay thế cũng cần được đánh giá: boolean có thể tiết lộ một thuộc tính nhạy cảm; decision claim có thể bị replay hoặc dùng sai audience. Tối thiểu dữ liệu không có nghĩa dữ liệu không còn nhạy cảm.

### Không dùng token như profile database

Đưa toàn bộ profile vào mọi access token làm tăng:

- Kích thước header/request;
- Số nơi lưu dữ liệu cá nhân;
- Khả năng rò rỉ qua log và telemetry;
- Thời gian dữ liệu cũ còn được sử dụng;
- Khó khăn khi cập nhật hoặc thu hồi claim;
- Phạm vi ảnh hưởng nếu một token bị đánh cắp.

Token nên chứa thông tin tối thiểu cần cho validation và authorization của resource server.

## 5. JWT payload không được mã hóa mặc định

JWT là một định dạng biểu diễn claims. JWS ký hoặc MAC token để bảo vệ integrity/authenticity; chữ ký không che giấu nội dung payload.

Một compact signed JWT thường có ba phần:

`````````text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
`````````

Header và payload được Base64URL encode, không phải encrypt. Người có token thường có thể decode và đọc claim mà không cần signing key.

### Ví dụ payload

`````````json
{
  "iss": "https://id.example.com",
  "sub": "user-8391",
  "aud": "orders-api",
  "exp": 1795329900,
  "email": "person@example.com",
  "department": "finance",
  "employee_number": "E-10482"
}
`````````

Payload trên minh họa dữ liệu có thể đọc được. Nếu access token được gửi qua nhiều service, gateway, trace hoặc log, các claim này có thể xuất hiện ở nhiều nơi.

### Không nhầm encoding với encryption

- Base64URL: chuyển dữ liệu sang dạng ký tự URL-safe, không bảo mật;
- JWS: bảo vệ integrity và nguồn ký, không che nội dung;
- JWE: mã hóa nội dung theo recipient/key phù hợp, bảo vệ confidentiality;
- Opaque token: chuỗi không tự mô tả claim; resource server phải tra cứu/introspect.

Ngay cả JWE cũng cần bảo vệ header, key management, recipient và log. Encryption không thay thế authorization, expiry, audience validation hoặc data minimization.

## 6. ID token, access token và UserInfo

Không phải token nào cũng dành cho cùng recipient hoặc mục đích.

| Artifact | Recipient | Mục đích | Lưu ý dữ liệu |
| --- | --- | --- | --- |
| ID token | OIDC client | Chứng minh kết quả authentication và thông tin subject cho client | Chỉ chứa claim client cần; audience phải khớp client |
| Access token | Resource server/API | Cho phép truy cập resource theo scope/audience | Không dùng như profile tùy tiện; hạn chế claim |
| UserInfo response | OIDC client có access token phù hợp | Trả user claims qua endpoint được bảo vệ | Chỉ yêu cầu/nhận claim cần thiết |
| SAML assertion | Service provider | Mang authentication/attribute statement | Có chữ ký, điều kiện thời gian, audience; có thể cần encryption |
| Session cookie | Ứng dụng web | Tham chiếu session của ứng dụng | Nên là opaque identifier, không nhồi profile nhạy cảm |

### Không dùng ID token làm access token

ID token được phát hành cho OIDC client, không mặc nhiên được chấp nhận bởi API. Resource server cần kiểm tra access token theo profile và audience của chính nó.

### UserInfo

UserInfo cho phép client lấy user claims qua một endpoint được bảo vệ bằng access token. Client cần kiểm tra subject trong UserInfo khớp subject trong ID token theo OIDC requirements. Không nên yêu cầu scope rộng chỉ để lấy một claim không cần thiết.

### SAML assertion

Chữ ký SAML bảo vệ tính toàn vẹn và nguồn phát hành; nó không tự mã hóa nội dung. Nếu assertion chứa sensitive attributes, cần xem xét encrypted assertion, encrypted attributes, giới hạn recipient và cách xử lý XML/log.

## 7. Scope, audience và claim release

Scope và audience giúp giới hạn quyền/recipient, nhưng không tự động bảo đảm mọi claim trong token đều phù hợp.

### Scope

Scope thường biểu diễn quyền hoặc nhóm dữ liệu mà client yêu cầu. Ví dụ OIDC scopes:

- openid: yêu cầu OIDC authentication;
- profile: nhóm claim hồ sơ cơ bản;
- email: nhóm claim email;
- address: nhóm claim địa chỉ;
- phone: nhóm claim số điện thoại.

Scope không phải danh sách mọi field bắt buộc phải phát hành. Issuer vẫn phải áp dụng policy, consent, client registration và data minimization.

### Audience

Audience xác định recipient mà token được phát hành cho. Resource server phải kiểm tra audience. Không phát hành token có audience quá rộng hoặc dùng một access token cho nhiều API không liên quan nếu có thể cấp token riêng.

### Claim release policy

Policy có thể dựa trên:

- Client ID và client type;
- Audience/resource;
- Requested scope;
- User consent;
- Organization/tenant policy;
- Authentication assurance;
- Purpose của transaction;
- Data classification;
- Jurisdiction hoặc data residency;
- Risk signal.

Client mobile công khai, web client, backend confidential client và service-to-service client không nên mặc nhiên nhận cùng tập claim.

## 8. OIDC Claims Request và consent

OpenID Connect hỗ trợ yêu cầu claim qua cơ chế scope và claims parameter trong các profile phù hợp. Client có thể yêu cầu một số claim cho ID token hoặc UserInfo; authorization server quyết định phát hành theo policy và sự đồng ý cần thiết.

### Ví dụ claims request

`````````json
{
  "userinfo": {
    "email": {
      "essential": true
    },
    "email_verified": {
      "essential": true
    }
  },
  "id_token": {
    "auth_time": {
      "essential": true
    }
  }
}
`````````

Đây là ví dụ cấu trúc claims parameter. Client chỉ nên yêu cầu các claim cần cho flow. Cờ essential biểu đạt mức cần thiết trong request theo OIDC; nó không cấp quyền vượt policy hoặc buộc issuer tiết lộ dữ liệu trái quy định.

### Consent

Consent cần:

- Nêu rõ client/recipient;
- Nêu mục đích và loại dữ liệu;
- Không gộp các mục đích không liên quan;
- Có thể rút lại theo policy;
- Được ghi nhận và kiểm toán;
- Không được dùng để hợp thức hóa việc thu thập quá mức.

Consent không thay thế data minimization hoặc cơ sở xử lý hợp lệ khác. Trong môi trường enterprise, policy tổ chức có thể quản lý claim release mà không có màn hình consent cho từng claim; vẫn cần transparency và governance phù hợp.

### Consent fatigue

Nếu yêu cầu người dùng đồng ý với quá nhiều claim không cần thiết, họ có thể bấm chấp nhận mà không hiểu. Chỉ yêu cầu quyền khi có nhu cầu thực và giải thích rõ tác động.

## 9. Subject identifier và pairwise subject

Subject identifier có thể là dữ liệu nhạy cảm nếu nó cho phép liên kết hoạt động của cùng một người qua nhiều client.

### Public subject

Một subject ID ổn định toàn cục giúp hệ thống nội bộ liên kết account dễ dàng, nhưng nếu chia sẻ cho nhiều client, các client có thể đối chiếu dữ liệu và theo dõi người dùng qua dịch vụ.

### Pairwise subject

Pairwise subject identifier cung cấp định danh khác nhau cho từng sector/client group. Client A và client B không dễ biết hai subject có cùng đại diện cho một người hay không chỉ bằng cách so sánh sub.

### Lợi ích

- Giảm khả năng cross-service correlation;
- Hạn chế việc client chia sẻ identifier để ghép hồ sơ;
- Giảm lộ định danh nội bộ;
- Hỗ trợ privacy-by-design trong federation.

### Giới hạn

- Account linking giữa client cần flow được kiểm soát;
- Migration sector identifier có thể thay đổi subject;
- Issuer vẫn cần mapping nội bộ an toàn;
- Pairwise ID không ẩn các thuộc tính khác như email hoặc số điện thoại;
- Client vẫn có thể correlation qua dữ liệu phụ nếu claim release quá rộng.

Không dùng email làm subject mặc định nếu cần định danh ổn định và riêng tư. Email có thể thay đổi, tái cấp hoặc được chia sẻ; subject identifier cần có semantics rõ ràng.

## 10. Chọn signed JWT, encrypted JWT hay opaque token

Lựa chọn token format ảnh hưởng trực tiếp tới mức độ claim được tiết lộ và cách resource server truy cập dữ liệu.

### Signed JWT (JWS)

- Cho phép verifier kiểm tra chữ ký và claims mà không gọi issuer;
- Payload có thể đọc được bởi bên sở hữu token;
- Phù hợp khi resource server cần validation local và claim có thể chia sẻ với audience;
- Không phù hợp để chứa secret hoặc dữ liệu cần giữ kín chỉ vì token đã ký.

### Encrypted JWT (JWE)

- Mã hóa nội dung cho recipient/key được chỉ định;
- Có thể kết hợp signed-then-encrypted hoặc encrypted structure theo protocol;
- Quản lý key distribution, rotation, algorithm và decryption permission phức tạp hơn;
- Header và metadata vẫn có thể tiết lộ một số thông tin;
- Verifier cần xử lý lỗi decryption an toàn và không lộ plaintext trong log.

JWE chỉ nên được dùng khi recipient thực sự cần nhận claim bí mật và có khả năng quản lý key phù hợp. Không mã hóa token rồi phát hành cho quá nhiều recipient cùng giữ một decryption key rộng.

### Opaque token

Opaque token không tự chứa claims có thể đọc được. Resource server dùng introspection hoặc token service để lấy trạng thái/metadata.

Lợi ích:

- Claim không bị lộ chỉ bằng cách decode token;
- Issuer có thể trả đúng metadata theo resource;
- Dễ kiểm soát revoke và claim freshness tập trung hơn.

Giới hạn:

- Introspection response vẫn có thể chứa sensitive claims;
- Resource server phải bảo vệ response/cache;
- Token endpoint/introspection trở thành dependency;
- Opaque token không tự ngăn token theft hoặc misuse.

### Chọn theo dữ liệu và trust boundary

| Nhu cầu | Hướng lựa chọn |
| --- | --- |
| Claim không nhạy cảm, cần local validation | Signed JWT tối thiểu |
| Claim cần giữ kín với bên không phải recipient | JWE với key và recipient giới hạn |
| Claim thay đổi nhanh hoặc cần revoke gần thời gian thực | Opaque token/introspection hoặc policy API |
| API chỉ cần quyền cụ thể | Token scope/audience hẹp, không phát hành profile |
| Dữ liệu cá nhân lớn hoặc thường thay đổi | API riêng được bảo vệ thay vì nhồi token |

Không có token format nào thay thế data minimization. Dù dùng JWE, claim không cần thiết vẫn không nên được phát hành.

## 11. Claim mapping và federation

Trong federation, một issuer có thể ánh xạ thuộc tính từ directory/HR/customer database sang OIDC claim hoặc SAML attribute. Sai mapping có thể làm lộ dữ liệu hoặc cấp quyền sai.

### Rủi ro mapping

- Nhầm employee ID với subject ID;
- Ánh xạ group nội bộ thành role công khai;
- Phát hành department hoặc manager chain cho client không cần;
- Tin email chưa verified;
- Nhầm claim từ tenant A sang tenant B;
- Giữ claim cũ sau khi người dùng đổi team hoặc rời tổ chức;
- Map thuộc tính do user tự khai thành thuộc tính đã được issuer xác minh.

### Quy tắc

- Dùng schema registry hoặc contract có version;
- Xác định authoritative source cho từng claim;
- Kiểm tra type, format, cardinality và null semantics;
- Phân biệt verified/unverified;
- Namespace claim nội bộ và claim chuẩn rõ ràng;
- Không dùng display name hoặc email làm authorization key;
- Review mapping khi thêm client/tenant;
- Test trường hợp dữ liệu thiếu, stale và conflicting.

### SAML attributes

SAML attribute có thể chứa nhiều giá trị và tên attribute tùy cấu hình. SP chỉ nên yêu cầu/nhận attributes cần thiết. XML signature bảo vệ integrity nhưng không che nội dung; sensitive attribute có thể cần encrypted assertion hoặc encrypted attribute theo khả năng IdP/SP.

Không xử lý XML assertion bằng parser cho phép external entity hoặc DTD nguy hiểm. Bảo vệ chống XXE, signature wrapping và kiểm tra đúng node đã được ký trước khi đọc attribute.

## 12. Claim freshness, validity và revocation

Một claim đúng tại thời điểm phát hành có thể sai ở thời điểm sử dụng.

Ví dụ:

- Nhân viên đã rời tổ chức nhưng token vẫn chứa department/role cũ;
- Email vừa đổi nhưng token vẫn có email cũ;
- MFA enrollment bị reset nhưng token cũ vẫn tuyên bố assurance trước đó;
- Tenant membership bị thu hồi nhưng access token chưa hết hạn;
- Account bị disable nhưng resource server chỉ kiểm tra chữ ký.

### Các cách kiểm soát

- Giới hạn token lifetime;
- Dùng introspection hoặc policy lookup cho action nhạy cảm;
- Dùng version/epoch claim để invalidation theo account/session;
- Có denylist hoặc revocation event khi cần;
- Giới hạn cache TTL;
- Kiểm tra authentication time và assurance freshness;
- Phát hành claim theo snapshot semantics rõ ràng;
- Không dùng token cũ làm nguồn dữ liệu authoritative lâu dài.

### Claim không có freshness chung

Không phải mọi claim cần cập nhật cùng tần suất. Email có thể thay đổi ít hơn trạng thái account; role đặc quyền có thể cần kiểm tra gần thời gian thực; locale có thể chấp nhận stale lâu hơn.

Đặt freshness requirement theo claim và action, không chỉ theo toàn bộ token expiry.

### Token version và session version

Có thể dùng version/epoch để phát hiện token được phát hành trước một sự kiện quan trọng. Resource server cần biết phiên bản hiện tại qua cache hoặc state service. Cơ chế này vẫn cần xử lý cache propagation và failover.

## 13. Sensitive claim trong browser và mobile app

Token thường đi qua browser, mobile app, gateway, SDK và nhiều service. Mỗi nơi lưu hoặc xử lý token là một điểm có thể làm lộ claim.

### Browser

- Không đặt token hoặc claim nhạy cảm trong URL;
- Tránh lưu bearer token dài hạn trong localStorage nếu có lựa chọn an toàn hơn;
- Bảo vệ session cookie bằng Secure, HttpOnly và SameSite phù hợp;
- Giảm XSS vì script cùng origin có thể đọc DOM hoặc gọi API bằng quyền user;
- Không đưa token vào analytics, session replay hoặc error reporting;
- Không render claim chưa được escape;
- Dùng CSP và hạn chế third-party script trên trang nhạy cảm.

### Mobile

- Lưu token/secret trong Keychain hoặc Android Keystore-backed storage theo nền tảng;
- Không lưu token trong plain preferences, log hoặc clipboard;
- Không đưa claim nhạy cảm vào notification payload nếu màn hình khóa có thể hiển thị;
- Xóa transient claim sau logout/account switch;
- Hạn chế backup/export token;
- Kiểm tra deep link và app intent không làm lộ token;
- Không coi device storage là an toàn nếu thiết bị đã root/jailbreak hoặc app runtime bị compromise.

### UI và cache local

Không hiển thị sensitive claim trước khi session được xác minh. Khi người dùng logout hoặc chuyển account, xóa dữ liệu cache và view model thuộc account cũ để tránh dữ liệu còn hiện trong UI.

## 14. Logging, tracing và telemetry

Một nguồn rò rỉ phổ biến là log request/response hoặc trace chứa toàn bộ token.

### Không log

- Raw JWT, access token, refresh token, ID token;
- Authorization header hoặc cookie;
- Password, OTP, recovery code;
- Sensitive claim như địa chỉ, số giấy tờ, sức khỏe, tài chính;
- SAML assertion hoặc UserInfo response đầy đủ;
- Private key, secret hoặc decryption material;
- Query string chứa magic link hoặc authorization code.

### Log thay thế

- Subject reference nội bộ đã pseudonymize;
- Client ID và audience;
- Claim name hoặc classification, không nhất thiết value;
- Policy decision và reason code;
- Token ID/jti đã được xử lý phù hợp, không dùng raw bearer value;
- Request/correlation ID;
- Claim schema/version;
- Số lượng claim được phát hành;
- Issuer và recipient reference.

### Tracing

APM agent có thể tự động capture HTTP headers, body hoặc exception. Cần cấu hình redaction ở agent, gateway và collector. Redaction chỉ ở ứng dụng không đủ nếu reverse proxy hoặc service mesh đã ghi request trước đó.

### Metrics

Metrics label không nên chứa email, user ID trực tiếp, token ID hoặc claim value có cardinality cao. Dùng aggregation theo client, route, claim type hoặc classification.

## 15. Cache, CDN và response API

Sensitive claim có thể xuất hiện trong ID token, UserInfo, profile API, error response hoặc cache layer.

### Cache policy

- Dùng Cache-Control phù hợp với dữ liệu và principal;
- Tránh shared cache cho response phụ thuộc user nếu cache key không phân biệt user;
- Cân nhắc no-store cho response chứa sensitive claim;
- Xử lý Vary/Authorization và CDN cache key rõ ràng;
- Xóa cache khi logout/account switch;
- Có invalidation khi claim thay đổi hoặc bị thu hồi;
- Không để browser back-forward cache hiển thị dữ liệu nhạy cảm trong context không còn hợp lệ nếu threat model yêu cầu.

### API response

Không trả toàn bộ user profile chỉ vì client đã có access token. Endpoint nên:

- Trả đúng field cần thiết;
- Áp dụng field-level authorization nếu dữ liệu có mức nhạy cảm khác nhau;
- Kiểm tra audience, scope và purpose;
- Phân biệt null, unknown, not disclosed và not applicable;
- Không dùng empty string để che mọi trạng thái nếu client cần hiểu semantics;
- Tránh đưa dữ liệu nhạy cảm vào URL query.

### Error response

Không echo claim/token trong lỗi validation hoặc authorization. Error response chỉ nên chứa code ổn định, mô tả an toàn và request ID; reason chi tiết được giữ trong audit có kiểm soát.

## 16. Retention, deletion và data lifecycle

Claim có thể được sao chép vào token, cache, log, backup, export, data warehouse và support tool. Xóa ở nguồn không tự xóa mọi bản sao.

### Vòng đời dữ liệu

1. Thu thập từ authoritative source;
2. Xác minh và phân loại;
3. Phát hành cho recipient/purpose;
4. Sử dụng và cache trong thời gian cho phép;
5. Cập nhật, sửa hoặc thu hồi;
6. Hết hạn và xóa khỏi hệ thống hoạt động;
7. Xử lý backup/replica theo retention;
8. Lưu audit tối thiểu theo yêu cầu.

### Retention policy

Retention cần xác định:

- Mục đích và căn cứ lưu;
- Thời gian tồn tại ở token/cache/log/backup;
- Ai có quyền truy cập;
- Khi nào phải xóa hoặc pseudonymize;
- Cách xử lý legal hold hoặc nghĩa vụ lưu trữ;
- Cách xác minh xóa ở các bản sao.

Không giữ claim vô thời hạn chỉ vì storage rẻ hoặc có thể hữu ích trong tương lai. Không giữ log chứa sensitive claim chỉ để debug nếu có thể dùng reason code và reference.

### Token expiry không xóa dữ liệu đã sao chép

Khi JWT hết hạn, payload vẫn có thể còn trong log, trace, browser cache hoặc backup. Token expiry hạn chế khả năng sử dụng token; nó không phải cơ chế xóa dữ liệu.

## 17. Governance, consent và quyền truy cập nội bộ

Sensitive claim cần governance từ lúc schema được thiết kế tới khi client ngừng sử dụng.

### Claim owner

Mỗi claim cần owner chịu trách nhiệm:

- Định nghĩa và schema;
- Authoritative source;
- Classification và purpose;
- Recipient/client allowlist;
- Freshness và retention;
- Thay đổi version;
- Incident response khi claim bị lộ.

### Review claim release

Khi thêm claim mới vào token hoặc UserInfo:

1. Xác định chức năng cần claim;
2. Xác định recipient và purpose;
3. Đánh giá mức nhạy cảm và khả năng correlation;
4. Xem có thể dùng boolean/decision/opaque reference không;
5. Xác định expiry, cache và retention;
6. Đánh giá log/trace/CDN/mobile storage;
7. Kiểm thử client chỉ nhận claim đã phê duyệt;
8. Ghi nhận owner và ngày review.

### Quyền truy cập nội bộ

Không phải mọi operator hoặc developer đều cần đọc claim value. Dùng least privilege, just-in-time access, audit và masking. Support tooling nên hiển thị reference hoặc giá trị đã che khi không cần plaintext.

## 18. Threat model: rò rỉ và lạm dụng sensitive claim

| Rủi ro | Cách xảy ra | Kiểm soát |
| --- | --- | --- |
| **JWT disclosure** | Payload signed JWT bị decode | Không đặt sensitive data vào JWS payload |
| **Audience over-sharing** | Một token được dùng cho nhiều API | Audience hẹp và token riêng theo resource |
| **Scope over-request** | Client yêu cầu profile/email/address không cần | Claim release policy và consent |
| **Cross-service correlation** | Dùng subject ổn định toàn cục | Pairwise subject và giảm identifier trực tiếp |
| **Stale claim** | Role/email/account state thay đổi sau token issue | Short lifetime, introspection, versioning |
| **Claim forgery** | Verifier không kiểm tra issuer/signature | Allowlist issuer, algorithm và signature validation |
| **Claim confusion** | Nhầm ID token với access token | Validate token type, audience và profile |
| **Federation mapping error** | Map group/department sai thành role | Schema/version, authoritative source và review |
| **Log leakage** | APM ghi raw token/UserInfo | Redaction tại mọi lớp và test log |
| **Cache leakage** | Shared cache trả profile user khác | no-store/private, cache key đúng |
| **Mobile extraction** | Token/claim lưu plain storage | Platform secure storage và short lifetime |
| **Browser XSS** | Script đọc token/DOM | HttpOnly cookie, CSP, output encoding |
| **Over-retention** | Claim còn trong backup/log sau expiry | Lifecycle, retention và deletion verification |
| **Insider access** | Operator xem dữ liệu không cần thiết | Least privilege, masking, JIT và audit |
| **Purpose drift** | Client dùng claim cho mục đích khác | Contract, governance, recipient review |
| **Sensitive inference** | Kết hợp claim tưởng như vô hại | Classification theo tổ hợp và privacy review |
| **SAML assertion exposure** | XML assertion bị log hoặc lưu plaintext | Redaction, encryption khi cần, secure XML parser |
| **Consent fatigue** | User chấp nhận scope quá rộng | Yêu cầu đúng nhu cầu và giải thích rõ |

## 19. Tình huống thiết kế: chia sẻ claim nhân viên cho ứng dụng đặt hàng

Một identity provider nội bộ phát hành JWT cho ứng dụng đặt hàng. Token hiện chứa email, tên đầy đủ, số nhân viên, department, manager, địa chỉ văn phòng, nhóm nội bộ và trạng thái MFA. Ứng dụng chỉ cần xác định người dùng có phải nhân viên và có được phép tạo đơn hàng hay không.

### Thiết kế ban đầu có vấn đề

1. Token chứa nhiều thuộc tính HR không cần thiết;
2. JWT được ký nhưng payload vẫn đọc được;
3. Access token được gửi tới nhiều API với audience rộng;
4. Email và employee number cho phép correlation giữa các ứng dụng;
5. Department/group được dùng trực tiếp làm quyền;
6. Token sống lâu nên role cũ tiếp tục được chấp nhận;
7. API gateway ghi Authorization header vào trace;
8. Client cache UserInfo đầy đủ sau logout;
9. Không có owner cho claim mapping.

### Thiết kế lại

1. Xác định mục đích: ứng dụng chỉ cần employee eligibility và quyền tạo đơn hàng.
2. Dùng subject identifier pairwise hoặc opaque reference cho client.
3. Cấp access token audience riêng cho orders API.
4. Phát hành scope tối thiểu như orders:create thay vì toàn bộ HR group.
5. Dùng policy service để xác định quyền; không biến department thành quyền mặc định.
6. Nếu cần eligibility, trả claim boolean hoặc decision có expiry ngắn, không phát hành số nhân viên.
7. Dùng token lifetime phù hợp và kiểm tra policy mới nhất cho thao tác có rủi ro.
8. Redact Authorization header và claim value tại gateway/APM.
9. Cache profile theo principal riêng hoặc no-store; xóa dữ liệu account cũ khi logout.
10. Gán owner cho schema, source, purpose, recipient và retention.

### Kết quả mong đợi

- Client chỉ nhận dữ liệu cần thiết;
- Token không chứa HR profile;
- Resource server xác minh audience/scope;
- Quyền không phụ thuộc trực tiếp vào claim chưa được policy kiểm tra;
- Claim stale được giới hạn theo freshness;
- Log, trace và cache không tạo bản sao dữ liệu không cần thiết;
- Có thể audit lý do mỗi claim được phát hành.

## 20. Bộ kiểm thử chấp nhận

| Trường hợp | Cách thử | Kết quả kỳ vọng |
| --- | --- | --- |
| Claim classification | Kiểm tra schema claim mới | Có owner, source, purpose và classification |
| Sensitive combination | Kết hợp email, department và location | Privacy review đánh giá correlation risk |
| JWT payload visibility | Decode signed JWT test | Không có secret hoặc claim không cần thiết |
| JWS integrity | Sửa payload sau khi ký | Verifier từ chối signature |
| JWE confidentiality | Kiểm tra token ở recipient không có key | Không đọc được plaintext claim |
| Opaque token | Decode token reference | Không lộ claim; introspection cần authentication |
| ID token audience | Gửi ID token tới resource API | API từ chối token sai type/audience |
| Access token audience | Dùng token cho API khác | Resource server từ chối |
| UserInfo subject | UserInfo sub không khớp ID token sub | Client từ chối response |
| Scope minimization | Client chỉ cần email nhưng yêu cầu scope rộng | Policy không phát hành claim không cần |
| Claims parameter | Yêu cầu claim không được phép | Issuer áp dụng policy; không tiết lộ ngoài quyền |
| Essential claim | Yêu cầu essential claim bị policy từ chối | Flow xử lý lỗi theo protocol, không giả vờ đã cấp |
| Consent withdrawal | Thu hồi consent theo policy | Claim release tiếp theo bị giới hạn |
| Pairwise subject | Cùng user đăng nhập hai client sector khác | Subject khác nhau theo cấu hình |
| Pairwise correlation | So sánh token của client khác | Không dùng identifier trực tiếp ngoài ý muốn |
| Email verification | Claim email_verified=false | Không dùng email làm định danh đã xác minh |
| Claim source | Thay đổi source attribute | Mapping chỉ nhận authoritative source |
| Tenant isolation | Gửi claim tenant khác | Resource server từ chối cross-tenant access |
| Stale role | Thu hồi role sau khi token phát hành | Quyền hết hiệu lực theo freshness/revoke policy |
| Account disabled | Disable account rồi dùng token | Bị từ chối trong SLA đã định |
| MFA freshness | Dùng claim MFA cũ cho thao tác step-up | Yêu cầu xác thực lại khi quá freshness window |
| SAML signature | Sửa attribute trong assertion | Signature validation thất bại |
| SAML encryption | Kiểm tra assertion chứa sensitive attribute | Chỉ recipient được phép giải mã |
| XML parser | Gửi DTD/XXE payload | Parser từ chối, không truy cập external entity |
| Log redaction | Gửi token chứa marker claim | Marker không xuất hiện trong log/trace |
| Header redaction | Kiểm tra gateway/APM | Authorization và cookie không bị capture |
| Metrics cardinality | Kiểm tra metric label | Không chứa email/user ID/token value |
| Browser storage | Kiểm tra local/session storage | Không có token/claim nhạy cảm ngoài policy |
| Mobile storage | Kiểm tra app data/log/backup | Token được lưu trong platform-protected storage |
| Account switch | Đăng xuất user A, đăng nhập user B | Cache/view model của A không còn hiển thị |
| Cache isolation | Hai user gọi profile API | Không nhận response cache của nhau |
| Cache invalidation | Thay đổi claim rồi đọc lại | Cache hết hạn/invalidate theo SLA |
| API field minimization | Gọi profile endpoint | Chỉ field được phép được trả |
| Error response | Gây lỗi claim validation | Không echo token hoặc claim value |
| Retention expiry | Hết retention window | Dữ liệu hoạt động được xóa/pseudonymize |
| Backup lifecycle | Kiểm tra backup theo retention | Có lịch hết hạn/xóa và access control |
| Access review | Operator không có quyền xem claim | Bị từ chối hoặc chỉ thấy masked value |
| Claim release audit | Yêu cầu token từ client | Audit ghi claim policy/version và recipient |
| Purpose drift | Client dùng claim cho chức năng khác | Contract/policy ngăn mục đích không được phép |
| Data subject update | Người dùng sửa thuộc tính | Source, token và cache cập nhật theo freshness policy |

Kiểm thử phải bao gồm issuer, token endpoint, resource server, gateway, browser/mobile client, log collector và backup/cache. Kiểm tra riêng token payload là chưa đủ vì claim có thể rò ở các lớp trung gian.

## 21. Checklist bảo vệ Sensitive claim

- **Inventory:** Mọi claim có schema, owner, authoritative source và classification?
- **Purpose:** Có mục đích cụ thể và recipient được phép?
- **Minimization:** Có thể bỏ claim, dùng boolean/decision hoặc truy vấn API riêng?
- **JWT:** Đã nhớ rằng JWS payload có thể đọc được?
- **Token type:** ID token, access token, UserInfo và SAML assertion được dùng đúng recipient?
- **Audience:** Token có audience hẹp và được verifier kiểm tra?
- **Scope:** Client chỉ yêu cầu nhóm claim cần thiết?
- **Consent/policy:** Claim release được quyết định theo policy và transparency phù hợp?
- **Subject:** Có pairwise/opaque identifier khi cần giảm correlation?
- **Mapping:** Claim đến từ authoritative source, type và version rõ?
- **Freshness:** Role, account status, MFA và claim quan trọng có freshness requirement?
- **Confidentiality:** JWE/opaque token được chọn khi cần, với key/introspection được bảo vệ?
- **Browser:** Không có token/claim nhạy cảm trong URL, local storage, analytics hoặc DOM không cần thiết?
- **Mobile:** Token/claim được lưu và xóa theo platform lifecycle?
- **Logging:** Gateway, APM, trace và collector đều redaction?
- **Cache:** Không có shared cache leakage; TTL và invalidation theo risk?
- **Retention:** Có expiry/deletion cho token, cache, log, export và backup?
- **Internal access:** Least privilege, masking, JIT và audit?
- **Federation:** Issuer, audience, signature, SAML parser và claim mapping được xác minh?
- **Testing:** Có test disclosure, correlation, stale claim, cross-tenant, log leakage và deletion?

### Câu hỏi tự kiểm tra

1. Vì sao signed JWT vẫn có thể làm lộ sensitive claim?
2. Claim khác authorization permission ở điểm nào?
3. Vì sao access token và ID token không thể dùng thay nhau?
4. Khi nào nên dùng pairwise subject thay subject ổn định toàn cục?
5. Scope có tự động cho phép issuer phát hành mọi claim trong scope không?
6. JWE giải quyết confidentiality nhưng không thay thế kiểm soát nào?
7. Vì sao token expiry không xóa dữ liệu đã đi vào log và backup?
8. Khi nào opaque token/introspection phù hợp hơn JWT local validation?
9. Claim freshness cần được xác định theo dữ liệu hay theo toàn bộ token?
10. Vì sao department hoặc group không nên tự động trở thành authorization decision?
11. Những lớp nào ngoài ứng dụng có thể ghi raw token hoặc claim?
12. Làm thế nào giảm correlation giữa các client mà vẫn hỗ trợ account linking hợp lệ?

## Kết luận

**Sensitive claim phải được quản lý như dữ liệu có mục đích, nguồn gốc, recipient và vòng đời rõ ràng; việc đưa claim vào token không làm nó trở nên an toàn hoặc cần thiết.** Signed JWT bảo vệ integrity nhưng payload vẫn đọc được, nên issuer cần tối thiểu hóa claim, giới hạn audience/scope và phân biệt ID token với access token. Pairwise subject, claim release policy, consent phù hợp, JWE hoặc opaque token có thể giảm một số rủi ro nhưng không thay thế authorization, freshness, key management và data governance. Claim cần được bảo vệ xuyên suốt browser, mobile, gateway, log, cache, telemetry và backup; việc thu hồi hoặc hết hạn token không tự xóa các bản sao dữ liệu. Một thiết kế tốt xác định owner, source, purpose, classification, retention và test cho từng claim trước khi phát hành, rồi kiểm tra định kỳ rằng recipient chỉ nhận và giữ dữ liệu thực sự cần thiết.
