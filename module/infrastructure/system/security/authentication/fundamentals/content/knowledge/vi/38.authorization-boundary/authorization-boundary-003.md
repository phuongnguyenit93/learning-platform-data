# Identity claims

**Identity claims** là những khẳng định có cấu trúc về một chủ thể do một nguồn phát hành đưa ra trong một ngữ cảnh xác định. Claim có thể mô tả subject là ai, được nhận diện trong tenant nào, có thuộc tính nào đã được xác minh, hoặc đã trải qua phương thức xác thực nào. Ví dụ gồm subject identifier, email đã xác minh, tên hiển thị, tenant identifier, authentication time và authentication context.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, người học tìm hiểu xác thực danh tính từ credential, password, MFA, passkey và certificate đến token, session, federation và account recovery. Identity claims kết nối các phần này: sau khi một issuer xác thực hoặc nhận diện chủ thể, nó phát hành các claim để client hoặc resource server hiểu assertion đó trong phạm vi tin cậy đã thỏa thuận.

Điểm cốt lõi: **claim là lời khẳng định của issuer, không phải sự thật tự chứng minh và cũng không tự động là quyền truy cập**. Chữ ký số có thể chứng minh token không bị sửa và được ký bởi một khóa được tin cậy; nó không chứng minh mọi thuộc tính trong token luôn đúng, còn mới hoặc đủ để cấp quyền cho mọi tài nguyên. Ứng dụng phải xác minh issuer, subject, audience, thời hạn, ngữ cảnh và policy trước khi sử dụng claim.

## 1. Identity claim là gì?

Một claim là một cặp tên và giá trị hoặc một cấu trúc có kiểu, được gắn với một subject trong một miền tin cậy. Ví dụ, issuer có thể khẳng định subject có identifier là một chuỗi ổn định, email đã được xác minh, thuộc một tổ chức hoặc đã đăng nhập bằng một phương thức nhất định.

Claim thường xuất hiện trong:
- ID Token của OpenID Connect (OIDC).
- Access token do authorization server phát hành.
- SAML assertion.
- Token hoặc assertion nội bộ giữa các service.
- Hồ sơ directory được đồng bộ qua một giao thức provisioning.
- Thông điệp identity federation giữa các tổ chức.

Một claim chỉ có ý nghĩa khi consumer biết ai phát hành, phát hành cho ai, trong bối cảnh nào, theo schema nào và có thể tin issuer tới mức nào.

### 1.1. Ví dụ về các claim thường gặp

| Claim hoặc thuộc tính | Ý nghĩa | Lưu ý khi sử dụng |
| --- | --- | --- |
| **iss** | Issuer phát hành token/assertion. | Phải khớp chính xác issuer được cấu hình tin cậy. |
| **sub** | Subject identifier trong phạm vi issuer. | Thường là định danh chính để liên kết subject trong issuer đó; không mặc định toàn cầu duy nhất. |
| **aud** | Audience được phép nhận token. | Consumer phải xác minh mình nằm trong audience được phép. |
| **exp** | Thời điểm token hết hạn. | Không chấp nhận token sau expiry, trừ tolerance nhỏ được policy quy định. |
| **iat** | Thời điểm token được phát hành. | Hữu ích để đánh giá tuổi token và phát hiện thời gian bất hợp lý. |
| **nbf** | Thời điểm token bắt đầu có hiệu lực. | Token chưa tới thời điểm này chưa được chấp nhận. |
| **jti** | Identifier của token. | Có thể hỗ trợ audit hoặc replay detection nếu hệ thống duy trì trạng thái tương ứng. |
| **email** | Địa chỉ email được issuer cung cấp. | Email có thể thay đổi hoặc được tái cấp; không nên mặc định là khóa identity. |
| **email_verified** | Issuer khẳng định email đã được xác minh theo policy của họ. | Consumer cần hiểu semantics và mức tin cậy của issuer. |
| **name** | Tên hiển thị của subject. | Thuộc tính mô tả, không phải định danh ổn định. |
| **preferred_username** | Tên đăng nhập hoặc tên người dùng ưu tiên. | Có thể đổi, trùng hoặc chỉ duy nhất trong một miền. |
| **auth_time** | Thời điểm user được xác thực. | Dùng khi policy cần authentication freshness. |
| **acr** | Authentication Context Class Reference. | Chỉ hiểu được theo profile và mapping đã thỏa thuận với issuer. |
| **amr** | Authentication Methods References. | Mô tả phương thức theo vocabulary của issuer; không tự suy ra assurance nếu chưa có mapping. |
| **groups / roles** | Nhóm hoặc vai trò do issuer cung cấp. | Thường là claim mở rộng; cần kiểm tra scope, tenant, nguồn và độ mới. |

Không phải mọi token đều chứa mọi claim. Một số claim là chuẩn trong một profile; các claim khác là custom hoặc phụ thuộc nhà cung cấp. Consumer phải xác định schema và semantics theo hợp đồng, không suy đoán từ tên trường.

### 1.2. Claim, attribute, credential và permission

Các khái niệm liên quan nhưng không đồng nghĩa:

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| **Identity attribute** | Dữ liệu mô tả một subject trong hệ thống nguồn. | Ngày bắt đầu làm việc trong HR directory. |
| **Identity claim** | Assertion về subject được issuer phát hành cho một consumer/ngữ cảnh. | Issuer khẳng định subject thuộc tenant A. |
| **Credential/authenticator** | Bằng chứng được dùng để xác thực quyền kiểm soát. | Passkey, password, client certificate. |
| **Authentication result** | Kết quả của một lần xác thực. | Đăng nhập thành công bằng WebAuthn có user verification. |
| **Authorization permission** | Quyền thực hiện action trên resource theo policy. | Được phép đọc hồ sơ của chính mình. |
| **Session** | Trạng thái truy cập được tạo sau khi xác thực. | Phiên browser có cookie opaque. |

Directory có thể lưu thuộc tính chức vụ; issuer có thể phát hành claim về chức vụ đó; ứng dụng có thể ánh xạ claim vào policy. Nhưng việc một người có chức vụ “Manager” không tự động chứng minh họ được phép phê duyệt mọi yêu cầu.

## 2. Issuer, subject và audience tạo nên ngữ cảnh claim

Ba thành phần quan trọng nhất để hiểu một assertion là ai phát hành, assertion nói về ai và assertion dành cho ai.

### 2.1. Issuer

Issuer là hệ thống phát hành token hoặc assertion. Trong OIDC, issuer thường là một Identity Provider hoặc OpenID Provider. Trong SAML, assertion được phát hành bởi Identity Provider. Với service-to-service, issuer có thể là authorization server hoặc workload identity provider.

Consumer phải có cấu hình trust rõ:
- Issuer identifier chính xác.
- Cách lấy signing keys hoặc certificate đáng tin.
- Thuật toán chữ ký được phép.
- Audience và token type mong đợi.
- Claim schema, mapping và policy.
- Quy trình key rotation và xử lý issuer compromise.

Không chọn issuer dựa trên một URL tùy ý do browser, callback hoặc token không xác minh cung cấp. Nếu ứng dụng hỗ trợ nhiều issuer, phải xác định issuer dự kiến cho từng tenant hoặc transaction trước khi chấp nhận response.

### 2.2. Subject

Subject là thực thể mà claim nói tới. Trong OIDC, claim **sub** là subject identifier trong phạm vi issuer. Một cặp issuer và subject thường được dùng để xác định external identity:

    external_identity_key = (issuer, subject)

Không nên dùng riêng subject nếu hệ thống có nhiều issuer. Hai issuer khác nhau có thể cùng phát hành giá trị sub giống nhau cho hai người khác nhau.

Subject cũng không nhất thiết là con người. Nó có thể đại diện workload, service principal, thiết bị hoặc một thực thể khác tùy profile. Consumer cần biết loại principal đang xử lý trước khi áp dụng policy.

### 2.3. Audience

Audience xác định consumer được phép nhận hoặc sử dụng token. Một ID Token được phát hành cho OIDC client không phải access token để gửi tới API. Một access token dành cho API A không nên được API B chấp nhận chỉ vì chữ ký hợp lệ.

Ví dụ:
- ID Token có audience là client application.
- Access token có audience là resource server/API.
- Token nội bộ có audience là service cụ thể.

Audience validation ngăn token được phát hành trong một ngữ cảnh bị dùng ở ngữ cảnh khác. Không chấp nhận token chỉ vì issuer tin cậy và chữ ký đúng.

### 2.4. Issuer-subject không phải account nội bộ

Ứng dụng thường ánh xạ external identity vào account nội bộ bằng một bảng liên kết. Bảng đó cần giữ issuer, subject, internal account ID, tenant, trạng thái liên kết, thời điểm xác minh và nguồn approval.

Email hoặc username có thể được dùng để gợi ý tìm account trong một quy trình kiểm soát, nhưng không nên tự động liên kết chỉ vì chuỗi email giống nhau. Account linking phải chứng minh quyền kiểm soát account đích và tin cậy issuer.

## 3. Claims trong OpenID Connect

OIDC xây dựng trên OAuth 2.0 và cung cấp lớp identity cho client. ID Token là một JWT chứa claims về authentication event và subject. UserInfo Endpoint có thể cung cấp thêm claims theo access token và quyền được cấp.

### 3.1. ID Token và Access Token phục vụ mục đích khác nhau

| Token | Consumer chính | Mục đích |
| --- | --- | --- |
| **ID Token** | OIDC client/Relying Party. | Truyền assertion về authentication và subject cho client. |
| **Access Token** | Resource server/API. | Cấp quyền truy cập resource theo scope/audience/policy. |
| **Refresh Token** | OAuth client với authorization server. | Xin access token mới theo grant và policy. |

Không gửi ID Token tới API để thay access token. Không dùng Access Token như bằng chứng đăng nhập giao diện nếu token/profile không được thiết kế cho mục đích đó. Một JWT có chữ ký đúng vẫn có thể sai loại hoặc sai audience.

### 3.2. Standard claims và custom claims

OIDC định nghĩa các standard claims như name, given_name, family_name, preferred_username, email, email_verified, picture, locale và một số thuộc tính khác. Việc phát hành phụ thuộc scope, consent, claim request và policy của OP.

Custom claims có thể chứa tenant, employee number, groups hoặc entitlement. Cần:
- Namespace rõ để tránh đụng tên claim chuẩn.
- Kiểu dữ liệu và semantics được tài liệu hóa.
- Giới hạn kích thước và số lượng.
- Quy tắc phát hành theo client, tenant và scope.
- Quy trình versioning khi thay schema.
- Không đưa dữ liệu nhạy cảm vào token nếu consumer không cần.

### 3.3. Claim về email và username

Email và preferred username hữu ích để hiển thị hoặc liên hệ, nhưng thường không phải định danh bền vững. Email có thể đổi, domain có thể thay đổi, mailbox có thể được tái cấp cho nhân viên khác. Claim email_verified chỉ nói issuer đã xác minh email theo quy trình của họ tại thời điểm liên quan; consumer cần biết mức đảm bảo và thời điểm của quy trình đó.

Nếu email được dùng để tìm account, hãy dùng một luồng linking an toàn:
1. Xác minh token và issuer.
2. Xác định external subject bằng issuer-subject.
3. Yêu cầu người dùng chứng minh quyền kiểm soát account nội bộ hiện tại.
4. Kiểm tra tenant và policy.
5. Tạo liên kết có audit và thông báo.
6. Xử lý xung đột nếu email đã gắn với account khác.

### 3.4. Claim authentication context

Các claim như auth_time, acr và amr giúp client đánh giá lần xác thực. Chúng không thay thế việc xác minh ID Token và không tự mô tả đầy đủ threat model.

- **auth_time** cho biết thời điểm authentication theo issuer.
- **acr** mô tả class/context theo profile.
- **amr** liệt kê phương thức xác thực theo vocabulary của issuer.

Client cần mapping cụ thể. Không giả định mọi OP dùng cùng giá trị acr hoặc cùng tên amr; không xếp hạng một chuỗi theo chữ “high”, “strong” hoặc “mfa” nếu chưa có thỏa thuận.

## 4. Claims trong JWT và chữ ký số

JWT là định dạng biểu diễn claims. JWT có thể được ký (JWS), mã hóa (JWE), hoặc vừa ký vừa mã hóa. Trong luồng xác thực phổ biến, consumer thường nhận JWS và xác minh chữ ký trước khi tin payload.

### 4.1. Chữ ký bảo vệ điều gì?

Chữ ký số có thể chứng minh:
- Payload không bị thay đổi kể từ khi được ký.
- Token được ký bằng private key tương ứng với public key đã được consumer tin cậy.
- Token có thể được kiểm tra theo thuật toán và key được cấu hình.

Chữ ký không chứng minh:
- Issuer đã nhập dữ liệu đúng.
- Email vẫn thuộc chủ thể hiện tại.
- Role chưa bị thu hồi sau lúc token được phát hành.
- Token được gửi đúng API nếu consumer không kiểm tra audience.
- Token chưa bị replay.
- Subject không bị liên kết nhầm với account nội bộ.

Trust bắt đầu từ việc consumer tin đúng issuer và key. Nếu cấu hình JWKS hoặc trust anchor bị chiếm, chữ ký hợp lệ có thể xác nhận một assertion độc hại.

### 4.2. Các kiểm tra JWT cơ bản

Trước khi dùng claims, consumer cần:
1. Chọn issuer từ cấu hình tin cậy.
2. Lấy key từ JWKS/metadata của issuer đã xác minh.
3. Chỉ chấp nhận thuật toán chữ ký được policy cho phép.
4. Xác minh chữ ký bằng key phù hợp; xử lý kid như một key identifier, không phải URL hay lệnh.
5. So khớp issuer chính xác.
6. Kiểm tra audience và authorized party khi profile yêu cầu.
7. Kiểm tra exp, nbf, iat và clock tolerance.
8. Xác minh token type và mục đích sử dụng.
9. Với ID Token, kiểm tra nonce khi flow yêu cầu và ràng buộc với authentication transaction.
10. Kiểm tra claim bắt buộc, schema, tenant và policy trước khi sử dụng.

Không tự động tải key từ URL do header token cung cấp. Không cho client chọn thuật toán hoặc issuer tùy ý. Không dùng decode payload như thể đó là verify signature.

### 4.3. Key rotation và cache

Issuer có thể xoay signing key và công bố nhiều key trong JWKS. Consumer cần:
- Cache JWKS trong thời gian phù hợp.
- Refresh khi gặp kid chưa biết theo cách có giới hạn.
- Không thực hiện fetch không giới hạn theo mỗi token lỗi.
- Cho phép overlap key cũ/mới trong giai đoạn chuyển đổi theo policy.
- Xử lý key bị compromise bằng trust update/denylist và thu hồi token liên quan.
- Theo dõi issuer metadata và thay đổi trust configuration.

Không tiếp tục tin key đã bị thu hồi chỉ vì nó còn trong cache lâu. Với action nhạy cảm, cân nhắc trạng thái trust mới nhất.

### 4.4. Token type confusion

Một số hệ thống nhận nhiều loại JWT: ID Token, access token, logout token, client assertion hoặc token nội bộ. Nếu cùng một validator chấp nhận mọi token mà không phân biệt mục đích, token hợp lệ ở flow này có thể bị dùng nhầm ở flow khác.

Cần tách validator hoặc profile theo token type, issuer, audience, required claims và thuật toán. Kiểm tra claim typ khi profile sử dụng; không tự suy đoán loại token chỉ từ việc nó có ba phần phân cách bằng dấu chấm.

## 5. Claims trong SAML

SAML assertion là cấu trúc XML do Identity Provider phát hành cho Service Provider. Nó có thể chứa subject, conditions, authentication statement và attribute statement.

### 5.1. Các thành phần quan trọng

| Thành phần | Ý nghĩa | Kiểm tra cần có |
| --- | --- | --- |
| **Issuer** | IdP phát hành assertion. | Phải thuộc danh sách issuer được tin cậy. |
| **Subject / NameID** | Định danh subject theo format/profile. | Mapping ổn định và đúng tenant. |
| **Conditions** | Điều kiện thời gian và audience. | Kiểm tra NotBefore, NotOnOrAfter và AudienceRestriction. |
| **Recipient / Destination** | Endpoint nhận response/assertion. | Khớp endpoint đã cấu hình. |
| **InResponseTo** | Liên kết response với AuthnRequest. | Kiểm tra request correlation khi SP-initiated flow. |
| **AuthnStatement** | Thông tin authentication event. | Kiểm tra context và thời điểm theo policy. |
| **AttributeStatement** | Các thuộc tính/claims về subject. | Kiểm tra namespace, source và mapping. |
| **Signature** | Bằng chứng toàn vẹn và issuer signing key. | Xác minh đúng node/element được sử dụng. |

### 5.2. XML signature wrapping và parsing an toàn

SAML dùng XML Signature, vì vậy cách parse và xác định node đã ký rất quan trọng. Một lỗi phổ biến là thư viện xác minh một element nhưng ứng dụng lại đọc một element khác có cùng tên hoặc ID. Điều này có thể dẫn tới signature wrapping.

Sử dụng thư viện SAML đã được kiểm chứng, bật kiểm tra signature và schema phù hợp, ràng buộc ID duy nhất, xác định chính xác assertion đã ký và dùng đúng node đó cho authorization. Không tự viết XML signature validation hoặc tắt kiểm tra để “tương thích”.

### 5.3. NameID không phải lúc nào cũng là email

NameID có thể là persistent, transient, email-address hoặc format khác. Ý nghĩa và vòng đời phụ thuộc IdP/SP agreement. Không mặc định NameID là email hoặc giá trị bất biến giữa mọi service provider.

## 6. Claim mapping và federation boundary

Trong federation, một tổ chức phát hành claims theo schema của họ, còn consumer ánh xạ chúng vào mô hình nội bộ. Đây là một ranh giới tin cậy quan trọng.

Ví dụ:
- IdP phát hành claim department = Finance.
- Ứng dụng ánh xạ Finance thành nhóm nội bộ finance-readers.
- Policy cho nhóm đó quyền đọc một tập tài liệu.
- Một action khác như phê duyệt thanh toán vẫn yêu cầu role riêng và approval.

### 6.1. Mapping phải rõ và có phiên bản

Mỗi mapping cần định nghĩa:
- Issuer và tenant áp dụng.
- Claim name, type và allowed values.
- Nguồn dữ liệu và owner.
- Quy tắc normalize/case sensitivity.
- Giá trị thiếu, null, duplicate hoặc không hợp lệ được xử lý ra sao.
- Mapping sang group/role/entitlement nội bộ.
- Version, ngày hiệu lực và quy trình rollback.

Không dùng quy tắc “mọi claim có tên admin đều là admin”. Một IdP đối tác có thể phát hành group tên administrators với nghĩa khác. Chỉ mapping chính xác từ issuer và tenant đã tin cậy mới có thể tham gia policy.

### 6.2. Không để claim tự chọn tenant

Trong hệ thống multi-tenant, tenant context phải được ràng buộc với issuer, client, subject và request. Không tin tenant ID do browser tự gửi hoặc một claim custom không có mapping đã phê duyệt.

API cần kiểm tra:
- Token có audience là API đang gọi.
- Subject đã được liên kết với account trong tenant.
- Membership còn active.
- Resource thuộc tenant tương ứng.
- Claim/role có nguồn và scope phù hợp.
- Action được phép trên object cụ thể.

Một token có tenant = A không tự cấp quyền lên mọi object của tenant A; authorization vẫn cần resource-level check.

### 6.3. Group overage và claim quá lớn

Một user có thể thuộc hàng trăm hoặc hàng nghìn group. Đưa toàn bộ group vào token làm token lớn, tăng độ trễ và có thể vượt giới hạn header/cookie. Một số IdP dùng overage indicator hoặc endpoint riêng để truy vấn group membership.

Consumer cần:
- Hiểu semantics của overage indicator theo provider.
- Gọi endpoint bổ sung bằng token và audience phù hợp.
- Không coi thiếu group trong token là không có membership nếu provider báo overage.
- Cache membership có TTL và xử lý revoke.
- Giới hạn group được phát hành theo client/tenant và mục đích.

Không tự suy ra group membership từ display name hoặc dữ liệu client.

## 7. Identity claims không phải authorization decision

Authentication trả lời “principal nào đã được xác thực và bằng cách nào?”. Authorization trả lời “principal này có được phép thực hiện action trên resource cụ thể không?”.

Claims có thể là đầu vào của authorization, nhưng policy cần kết hợp:
- Subject và actor.
- Issuer và mức tin cậy của claim.
- Tenant, organization và resource ownership.
- Action và scope.
- Membership/role còn hiệu lực.
- Authentication assurance và freshness.
- Context của request.
- Approval hoặc business constraints.

Ví dụ, claim department = Finance không tự cấp quyền đọc mọi dữ liệu tài chính. Policy có thể yêu cầu user thuộc tenant đúng, role finance-reader còn active, resource thuộc phạm vi được giao và session đáp ứng assurance cần thiết.

### 7.1. Scope không đồng nghĩa role

OAuth scope thường mô tả quyền mà client được cấp đối với API/resource, chẳng hạn đọc hồ sơ hoặc ghi dữ liệu. Scope không nhất thiết mô tả chức danh hay vai trò của con người. Một client có scope đọc dữ liệu vẫn phải kiểm tra user/subject và object-level authorization nếu API hoạt động thay mặt người dùng.

### 7.2. Claims không thay thế kiểm tra trạng thái hiện tại

Một access token có thể chứa role admin tại thời điểm phát hành. Sau đó người dùng bị gỡ role, rời tenant hoặc account bị suspend. Nếu resource server chỉ kiểm chữ ký và expiry, claim cũ có thể tiếp tục được chấp nhận.

Các cách giảm stale authorization:
- Access token lifetime phù hợp.
- Introspection hoặc state lookup cho action nhạy cảm.
- Account/session version hoặc authorization epoch.
- Event-driven cache invalidation.
- Kiểm tra membership/resource ownership gần thời điểm sử dụng.
- Thu hồi grant/session khi có thay đổi lifecycle.

Không phải mọi API cần truy vấn directory ở mỗi request; mức nhất quán phải theo hậu quả của quyết định và khả năng revoke.

## 8. Freshness và nguồn gốc của claim

Claim có thể đúng lúc phát hành nhưng sai sau đó. Email thay đổi, nhân viên rời tổ chức, role bị thu hồi, tenant membership hết hạn hoặc thiết bị bị đánh dấu không compliant.

Mỗi claim quan trọng nên có semantics về:
- Nguồn phát hành và provenance.
- Thời điểm dữ liệu gốc được cập nhật.
- Thời điểm token/assertion được phát hành.
- Thời gian sống và cache policy.
- Sự kiện nào làm claim mất hiệu lực.
- Cách consumer nhận biết dữ liệu mới.

### 8.1. Token lifetime không phải attribute freshness

Token được phát hành một phút trước vẫn có thể chứa group membership được đồng bộ từ directory hôm qua. iat cho biết token được tạo khi nào, không nhất thiết cho biết dữ liệu nguồn được cập nhật khi nào.

Nếu cần freshness cho một thuộc tính, cần claim riêng hoặc truy vấn nguồn có thẩm quyền. Không suy ra dữ liệu vừa được xác minh chỉ từ token mới.

### 8.2. Authentication freshness và claim freshness

auth_time liên quan tới thời điểm xác thực người dùng; nó không nói rằng mọi profile attribute vừa được kiểm tra. Một người có thể xác thực bằng passkey ngay bây giờ nhưng claim department trong directory vẫn cũ.

Policy phải xác định freshness cần cho từng mục đích:
- Xác thực mới cho thay đổi recovery.
- Membership mới cho cấp quyền admin.
- Employment status mới cho tài nguyên nhân viên.
- Certificate status mới cho xác thực workload.
- Device posture mới cho export dữ liệu nhạy cảm.

## 9. Pairwise subject và bảo vệ quyền riêng tư

OIDC hỗ trợ pairwise subject identifier để cùng một người có thể có sub khác nhau ở các client/sector khác nhau. Điều này hạn chế việc các RP dễ dàng liên kết hoạt động của cùng một người qua nhiều dịch vụ.

### 9.1. Vì sao cần pairwise subject?

Nếu mọi ứng dụng nhận cùng một subject identifier toàn cục, các bên có thể đối chiếu dữ liệu và xây dựng hồ sơ sử dụng xuyên dịch vụ. Pairwise subject giảm khả năng liên kết trực tiếp này.

Tổ chức cần:
- Hiểu sector identifier và quy tắc tạo pairwise sub của OP.
- Giữ mapping nội bộ trong phạm vi kiểm soát và mục đích hợp lệ.
- Không giả định sub của hai client sẽ giống nhau.
- Có quy trình account linking/consent khi cần chia sẻ identity.
- Xem xét tác động khi đổi sector identifier hoặc chuyển client.

### 9.2. Data minimization

Chỉ phát hành claim mà client cần. Tránh đưa:
- Số định danh cá nhân không cần thiết.
- Ngày sinh hoặc địa chỉ chính xác nếu không có mục đích.
- Nhóm/role nội bộ cho client không cần biết.
- Dữ liệu sức khỏe, tài chính hoặc thuộc tính nhạy cảm.
- Thông tin thiết bị chi tiết có thể fingerprint người dùng.

Claims trong JWT có thể được lưu trong log, browser tooling, proxy hoặc telemetry. Không coi token là nơi chứa hồ sơ cá nhân đầy đủ.

### 9.3. Consent và purpose limitation

User consent có thể là một phần của việc chia sẻ claim, nhưng consent screen phải mô tả rõ client, publisher, dữ liệu và quyền. Với dữ liệu tổ chức hoặc xử lý dựa trên policy khác, không phải lúc nào consent cá nhân cũng là căn cứ duy nhất. Consumer phải tuân theo agreement, luật và policy áp dụng.

## 10. Bảo vệ claim trong token và log

Claims thường chứa dữ liệu có giá trị cao. Cần bảo vệ cả khi truyền, lưu và xử lý.

- Dùng TLS cho các endpoint token, userinfo, federation và API.
- Chỉ gửi token tới đúng audience.
- Tránh đặt token trong URL query string.
- Không log raw ID Token, access token, refresh token hoặc SAML assertion.
- Không lưu token trong nơi client-side dễ bị đọc nếu kiến trúc có lựa chọn an toàn hơn.
- Giới hạn claim payload và tránh secret trong custom claim.
- Mã hóa token nếu payload chứa dữ liệu cần confidentiality và profile hỗ trợ.
- Bảo vệ signing key trong HSM/KMS hoặc secret management phù hợp.
- Phân quyền và audit truy cập JWKS/signing configuration.
- Mask hoặc loại bỏ dữ liệu cá nhân trong telemetry.

JWS bảo vệ tính toàn vẹn nhưng payload thường có thể đọc được bởi người giữ token. Không đặt password, private key, recovery code hoặc dữ liệu bí mật vào JWT đã ký nhưng không mã hóa.

## 11. Threat model: lạm dụng identity claims

| Mối đe dọa | Cách xảy ra | Tác động | Kiểm soát |
| --- | --- | --- | --- |
| **Issuer confusion** | Chấp nhận token từ issuer không được cấu hình. | Attacker tự phát hành claim giả. | Issuer allowlist và exact match. |
| **Audience confusion** | API nhận ID Token hoặc access token dành cho service khác. | Token hợp lệ bị dùng sai ngữ cảnh. | Audience và token type validation. |
| **Subject collision** | Dùng sub mà không kèm issuer. | Liên kết nhầm hai người/identity. | Khóa external identity bằng issuer-subject. |
| **Claim injection** | Tin header/body/client field thay vì claim đã xác minh. | Attacker tự khai role, tenant hoặc email verified. | Chỉ đọc claims từ validated assertion; server-side mapping. |
| **Privilege escalation** | Ánh xạ group/role từ issuer không đúng hoặc quá rộng. | Cấp quyền admin ngoài ý muốn. | Issuer/tenant-scoped mapping, least privilege và approval. |
| **Stale claim** | Token chứa membership/role đã bị thu hồi. | Quyền cũ tiếp tục có hiệu lực. | TTL, introspection/state check, event invalidation. |
| **Token replay** | Token bị sao chép và dùng lại trong thời hạn. | Truy cập trái phép bằng bearer token. | Short lifetime, sender constraint, replay controls và revoke. |
| **Token type confusion** | Dùng ID Token làm access token hoặc ngược lại. | Bypass kiểm tra consumer/audience. | Validator/profile riêng và token type checks. |
| **SAML signature wrapping** | Ứng dụng đọc node khác với node đã ký. | Assertion không được xác minh được dùng để cấp quyền. | Thư viện SAML tin cậy, schema/ID checks và signed-node binding. |
| **Tenant confusion** | Claim tenant không được ràng buộc với resource. | Truy cập chéo tenant. | Tenant-scoped authorization và object-level checks. |
| **Privacy leakage** | Phát hành hoặc log quá nhiều claims. | Lộ thông tin cá nhân và liên kết hoạt động. | Data minimization, pairwise subject, retention và access control. |

## 12. Tình huống thực hành: claim role cũ sau khi nhân viên chuyển bộ phận

**Bối cảnh:** Nhân viên Lan chuyển từ Finance sang Operations. HR directory đã cập nhật department và hệ thống IAM đã gỡ Lan khỏi nhóm finance-approvers. Tuy nhiên, access token của Lan còn hiệu lực thêm 45 phút và vẫn chứa claim role finance-approver. Trong khoảng thời gian đó, Lan gọi API phê duyệt một giao dịch.

**Phân tích:**

1. Token có thể có chữ ký hợp lệ và chưa hết hạn.
2. Claim role phản ánh trạng thái lúc token được phát hành.
3. Việc gỡ membership trong directory không tự thay đổi payload token đã phát hành.
4. Nếu API chỉ kiểm chữ ký, audience và expiry, role cũ có thể được chấp nhận.
5. Authentication thành công không chứng minh quyền phê duyệt còn hiệu lực tại thời điểm request.

**Thiết kế lại:**

- Dùng token lifetime ngắn phù hợp với rủi ro.
- Phát event membership/role change để cập nhật authorization cache hoặc session version.
- Với giao dịch phê duyệt, kiểm tra membership và entitlement hiện tại từ nguồn có thẩm quyền hoặc introspection/state service.
- Ràng buộc quyền với tenant, account, action và resource cụ thể.
- Thu hồi session/grant nếu thay đổi là một phần của incident hoặc policy yêu cầu.
- Ghi audit decision, claim source/version và trạng thái membership đã kiểm tra.

**Bài tập:** Nếu Lan vừa xác thực lại bằng passkey sau khi chuyển bộ phận, claim role cũ trong access token có trở nên mới không? Không. auth_time mới chỉ nói lần xác thực mới; nó không tự làm mới dữ liệu role. Authorization phải lấy membership mới hoặc token mới được phát hành từ nguồn đã cập nhật.

## 13. Checklist thiết kế và sử dụng identity claims

- [ ] Xác định issuer, subject, audience và token/assertion type trước khi dùng claim.
- [ ] Dùng cặp issuer-subject cho external identity; không dùng email làm khóa bất biến.
- [ ] Phân biệt identity attribute, claim, credential, authentication result và permission.
- [ ] Tách ID Token, access token, refresh token và assertion theo consumer/mục đích.
- [ ] Xác minh chữ ký bằng key từ issuer tin cậy và thuật toán allowlist.
- [ ] Kiểm tra issuer, audience, expiry, not-before, issued-at và token type.
- [ ] Với OIDC, kiểm tra nonce và authentication context theo flow/policy.
- [ ] Với SAML, kiểm tra signature, conditions, audience, recipient, destination và request correlation.
- [ ] Dùng thư viện federation/JWT đã được kiểm chứng; tránh tự viết parser/validator.
- [ ] Version hóa claim schema và mapping; xử lý null, duplicate, overage và unknown values.
- [ ] Ràng buộc group/role mapping với issuer, tenant, client và nguồn có thẩm quyền.
- [ ] Không để claim tự chọn tenant hoặc tự cấp quyền trên mọi resource.
- [ ] Kiểm tra authorization riêng theo subject, actor, tenant, action và object.
- [ ] Đánh giá freshness của dữ liệu nguồn; token iat mới không có nghĩa attribute mới.
- [ ] Có cơ chế xử lý stale role/membership: TTL, introspection, version hoặc event invalidation.
- [ ] Dùng pairwise subject khi phù hợp và có quy trình linking được kiểm soát.
- [ ] Chỉ phát hành claims cần thiết; tránh dữ liệu nhạy cảm và token payload quá lớn.
- [ ] Không log raw token/assertion hoặc secret.
- [ ] Bảo vệ signing keys, JWKS configuration và trust metadata.
- [ ] Kiểm thử issuer confusion, audience confusion, claim injection, replay, stale claims và tenant boundary.

## 14. Câu hỏi tự kiểm tra

**1. Identity claim là gì?**  
Là assertion có cấu trúc do issuer phát hành về một subject trong một ngữ cảnh xác định, chẳng hạn subject ID, email verified, tenant hoặc authentication context.

**2. Chữ ký JWT hợp lệ chứng minh điều gì?**  
Nó chứng minh payload không bị sửa và được ký bằng key tương ứng với key consumer tin cậy. Nó không chứng minh claim luôn đúng, mới hoặc đủ để cấp quyền.

**3. Vì sao phải kiểm tra issuer và audience?**  
Issuer xác định nguồn assertion; audience xác định consumer được phép dùng token. Bỏ qua một trong hai có thể cho phép token từ nguồn hoặc mục đích khác bị chấp nhận.

**4. Có thể dùng email làm định danh account ổn định không?**  
Không nên mặc định. Email có thể đổi hoặc tái cấp; dùng issuer-subject hoặc internal account ID ổn định và linking có proof of control.

**5. ID Token và Access Token khác nhau thế nào?**  
ID Token truyền identity/authentication claims cho OIDC client; Access Token cấp quyền truy cập resource cho API theo audience/scope/policy.

**6. Claim role trong token còn hiệu lực sau khi user bị gỡ role không?**  
Có thể còn được chấp nhận tới khi token hết hạn nếu resource server không kiểm tra trạng thái mới. Cần TTL, introspection, version hoặc invalidation phù hợp.

**7. auth_time có chứng minh department vừa được cập nhật không?**  
Không. auth_time chỉ nói thời điểm authentication; freshness của thuộc tính department cần nguồn hoặc timestamp riêng.

**8. Vì sao cần issuer-subject pair?**  
Vì cùng một giá trị sub có thể xuất hiện ở nhiều issuer khác nhau; kết hợp cả hai giúp xác định external identity đúng miền tin cậy.

**9. Scope có đồng nghĩa với role của người dùng không?**  
Không. Scope thường mô tả quyền client được cấp trên API/resource; role là một thuộc tính authorization khác và cần mapping/policy rõ.

**10. Vì sao phải giảm số lượng claims?**  
Để hạn chế lộ dữ liệu cá nhân, token quá lớn, liên kết hoạt động xuyên dịch vụ và việc consumer nhận dữ liệu không cần thiết.

**Ghi nhớ:** Identity claims là assertion do issuer phát hành về một subject cho audience cụ thể. Hãy xác minh nguồn, chữ ký, audience, thời hạn và semantics; ánh xạ claims theo issuer/tenant có kiểm soát; đánh giá freshness; bảo vệ quyền riêng tư; và luôn thực hiện authorization riêng trên resource/action. Một claim đáng tin trong một flow không tự trở thành quyền phổ quát ở mọi nơi.
