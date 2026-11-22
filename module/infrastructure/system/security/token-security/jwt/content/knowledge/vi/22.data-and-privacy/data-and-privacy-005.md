# Claims nhạy cảm và lựa chọn mã hóa hoặc tra cứu phía máy chủ

## 1. Không phải claim nào cũng nên nằm trong token

JWT thường được dùng để chuyển thông tin về issuer, subject, audience, thời gian, client, scope hoặc ngữ cảnh xác thực giữa các thành phần. Vì payload của một JWS thông thường chỉ được Base64URL-encode và ký, bất kỳ bên nào có token đều có thể đọc payload mà không cần khóa bí mật.

Điều này tạo ra một câu hỏi thiết kế quan trọng: **claim có thực sự cần được mang theo trong token không, và nếu cần thì ai được phép đọc nó?**

Các dữ liệu như email, số điện thoại, địa chỉ, mã khách hàng, tenant, thông tin tài chính, dữ liệu sức khỏe, nhóm nội bộ, quyền quản trị hoặc thuộc tính xác thực có thể nhạy cảm tùy ngữ cảnh. Nếu nhúng quá nhiều dữ liệu vào JWT, các thông tin đó có thể bị lộ khi token đi qua client, proxy, log, hệ thống quan sát, công cụ hỗ trợ hoặc kho lưu trữ.

Có ba hướng thiết kế thường gặp:

1. **Giảm thiểu claims:** chỉ đưa thông tin thực sự cần thiết vào token.
2. **Mã hóa token bằng JWE:** giữ payload không đọc được với các bên không có quyền giải mã.
3. **Dùng opaque/reference token và tra cứu phía máy chủ:** token chỉ là một định danh ngẫu nhiên; dữ liệu và trạng thái được giữ trong hệ thống có thẩm quyền.

Các hướng này có thể kết hợp. Mã hóa không thay thế việc giảm thiểu dữ liệu, còn tra cứu phía máy chủ không loại bỏ nhu cầu bảo vệ token như một bearer credential.

Nội dung thuộc module Security - JSON Web Token (JWT), chương Dữ liệu và riêng tư. Phạm vi áp dụng chung cho JWT, JOSE và OAuth, không phụ thuộc Java, Spring Security hay nền tảng cụ thể.

## 2. JWS không cung cấp tính bí mật cho payload

JWS Compact Serialization thường có ba phần:

~~~text
BASE64URL(protected-header)
.
BASE64URL(payload)
.
BASE64URL(signature)
~~~

Chữ ký bảo vệ tính toàn vẹn và giúp bên nhận xác minh dữ liệu được ký bằng khóa tương ứng. Base64URL không phải mã hóa bí mật. Người có token có thể decode header và payload.

Ví dụ:

~~~json
{
  "iss": "https://identity.example.org/",
  "sub": "user-123",
  "email": "person@example.org",
  "phone_number": "+84000000000",
  "tenant_id": "tenant-blue",
  "role": "finance-admin",
  "exp": 1893456900
}
~~~

Nếu đây là JWS, các giá trị trên có thể được đọc bởi client, proxy, gateway, người có được bản sao token hoặc hệ thống ghi lại token. Việc chữ ký hợp lệ không làm payload trở nên riêng tư.

### 2.1. TLS không làm payload JWS trở thành bí mật đầu cuối

TLS bảo vệ dữ liệu trên từng kết nối mạng. Tuy nhiên, token vẫn có thể xuất hiện ở các điểm kết thúc TLS hoặc sau khi giải mã tại proxy, gateway, client và ứng dụng. Token cũng có thể bị ghi vào log, lưu trong trình duyệt, crash report hoặc hệ thống tracing.

Do đó, TLS là yêu cầu nền tảng nhưng không tự giải quyết mọi đường rò rỉ dữ liệu sau khi kết nối kết thúc. Nếu một bên trung gian cần chuyển token nhưng không được phép đọc claims, JWE có thể bổ sung bảo vệ payload đầu cuối tới recipient.

### 2.2. Không nhầm chữ ký với mã hóa

| Cơ chế | Mục tiêu chính | Ai có thể đọc payload? |
| --- | --- | --- |
| JWS | Integrity và xác minh nguồn ký theo trust model | Bất kỳ ai có token |
| JWE | Confidentiality và integrity của ciphertext theo thuật toán mã hóa xác thực | Recipient có khóa giải mã phù hợp |
| JWS lồng trong JWE | Chữ ký issuer bên trong và mã hóa payload bên ngoài | Recipient giải mã mới đọc được JWS |
| Opaque/reference token | Không mang claims có thể đọc trực tiếp; phải tra cứu | Thành phần có quyền tra cứu trạng thái |

Một JWE có thể bảo vệ payload khỏi người chỉ có ciphertext. Tuy nhiên, việc ai tạo JWE và liệu người nhận có xác minh được issuer hay không còn phụ thuộc cách dùng khóa và việc có chữ ký bên trong.

## 3. Phân loại dữ liệu trước khi chọn cách biểu diễn

Không nên bắt đầu bằng câu hỏi “dùng JWE hay JWS?”. Hãy phân loại dữ liệu và xác định nhu cầu của từng bên nhận trước.

| Nhóm dữ liệu | Ví dụ | Câu hỏi cần đặt ra |
| --- | --- | --- |
| Định danh tối thiểu | sub dạng pairwise identifier, issuer | API có cần giá trị này để ánh xạ chủ thể không? |
| Thông tin liên hệ | Email, số điện thoại, địa chỉ | Có cần gửi qua mọi service hay chỉ một service hồ sơ? |
| Dữ liệu tài chính | Số tài khoản, thông tin thanh toán, hạn mức | Có nên chỉ tra cứu từ hệ thống tài chính có kiểm soát? |
| Dữ liệu sức khỏe hoặc dữ liệu đặc biệt nhạy cảm | Tình trạng, hồ sơ, thuộc tính sức khỏe | Có thực sự cần nằm trong credential được chuyển qua nhiều hệ thống? |
| Thuộc tính tổ chức | Tenant, phòng ban, nhóm, vai trò nội bộ | Có thể lấy từ policy hoặc directory phía máy chủ không? |
| Ngữ cảnh xác thực | ACR, AMR, auth_time | Có cần cho quyết định hiện tại và profile có định nghĩa semantics không? |
| Quyền truy cập | Scope, permission, entitlement | Có thể giới hạn ở quyền cần cho resource cụ thể không? |
| Trạng thái vòng đời | Session, grant, token family, trạng thái khóa | Có cần giá trị mới nhất từ kho trạng thái không? |

Một claim có thể không nhạy cảm trong hệ thống này nhưng trở nên nhạy cảm khi kết hợp với các claim khác. Ví dụ, tenant, department và role có thể tiết lộ cấu trúc tổ chức; một identifier ổn định có thể cho phép liên kết hoạt động giữa nhiều dịch vụ.

### 3.1. Áp dụng data minimization

Trước khi đưa claim vào token, hãy trả lời:

- Thành phần nhận có thực sự cần giá trị này không?
- Có thể dùng một identifier giả danh (pseudonymous identifier) thay cho dữ liệu trực tiếp không?
- Có thể tra cứu dữ liệu từ API có thẩm quyền khi cần không?
- Claim có thể được tính lại từ ngữ cảnh tin cậy không?
- Giá trị có thay đổi trong thời hạn token không?
- Token sẽ đi qua những client, proxy, service và hệ thống quan sát nào?
- Thời hạn lưu token và bản sao của nó là bao lâu?

Nếu một API chỉ cần biết subject có quyền đọc hóa đơn, có thể chỉ cần sub, aud và scope phù hợp. API đó thường không cần email, địa chỉ nhà, ngày sinh hoặc toàn bộ hồ sơ người dùng.

### 3.2. Ưu tiên identifier giả danh khi phù hợp

Thay vì đưa email hoặc số điện thoại vào token, có thể dùng subject identifier ổn định trong phạm vi issuer hoặc pairwise subject identifier theo từng client/sector nếu profile hỗ trợ.

Identifier giả danh vẫn có thể là dữ liệu có khả năng liên kết hoặc nhận diện khi kết hợp với dữ liệu khác. Không coi việc thay email bằng một chuỗi ID là đã ẩn danh hoàn toàn. Cần giới hạn mục đích, phạm vi chia sẻ và thời gian lưu.

## 4. Lựa chọn 1: JWS với claims tối thiểu

JWS phù hợp khi recipient được phép đọc claims và cần xác minh chúng mà không phải hỏi issuer ở mỗi request. Ví dụ, Resource Server nhận access token có issuer, subject, audience, thời hạn và scope.

Một payload tối thiểu hơn:

~~~json
{
  "iss": "https://identity.example.org/",
  "sub": "pairwise-user-7f29",
  "aud": "https://api.example.org/invoices",
  "scope": "invoice:read",
  "iat": 1893456000,
  "exp": 1893456900
}
~~~

API có thể dùng sub để ánh xạ sang hồ sơ nội bộ nếu cần. Email, địa chỉ, dữ liệu tài chính hoặc thông tin cá nhân khác không cần đi theo mọi request.

### 4.1. Ưu điểm

- Resource Server xác minh chữ ký và claims cục bộ.
- Không cần giải mã JWE hoặc tra cứu trạng thái cho mỗi claim.
- Token dễ quan sát và debug hơn trong môi trường được kiểm soát, miễn là không log token hoặc dữ liệu nhạy cảm.
- Claims có thể được chia sẻ giữa các thành phần cùng được phép đọc.
- Ít phụ thuộc vào khóa giải mã của recipient.

### 4.2. Giới hạn

- Payload không bí mật; ai có token đều có thể đọc.
- Token bị sao chép có thể bị replay trong thời hạn nếu không có cơ chế bổ sung.
- Claims có thể cũ so với dữ liệu hiện hành.
- Token có thể bị log hoặc lưu ngoài dự kiến.
- Không phù hợp để mang dữ liệu bí mật chỉ vì token đã được ký.

JWS với claims tối thiểu thường là lựa chọn đơn giản khi dữ liệu không cần giữ bí mật trước recipient hoặc các bên có thể nhìn thấy token, và khi thông tin trong token được giới hạn ở mức cần thiết.

## 5. Lựa chọn 2: JWE để bảo vệ tính bí mật

JWE (JSON Web Encryption) mã hóa nội dung để chỉ recipient có khóa phù hợp mới có thể đọc plaintext. JWE Compact Serialization thường có năm phần:

~~~text
BASE64URL(protected-header)
.
BASE64URL(encrypted-key)
.
BASE64URL(iv)
.
BASE64URL(ciphertext)
.
BASE64URL(authentication-tag)
~~~

JWE bảo vệ confidentiality của payload và, với chế độ mã hóa xác thực theo JWA, phát hiện việc ciphertext hoặc dữ liệu được bảo vệ bị sửa đổi.

Ví dụ minh họa payload sau khi giải mã:

~~~json
{
  "iss": "https://identity.example.org/",
  "sub": "user-123",
  "aud": "https://api.example.org/medical-records",
  "record_reference": "record-8a12",
  "exp": 1893456900
}
~~~

Nếu payload này được mã hóa cho API hồ sơ y tế, các proxy hoặc thành phần trung gian chỉ có ciphertext không thể đọc trực tiếp các claims bên trong, miễn là chúng không có khóa giải mã.

### 5.1. Header JWE vẫn có thể nhìn thấy

Trong Compact Serialization, protected header được Base64URL-encode và không được mã hóa như ciphertext. Metadata có thể lộ gồm:

- alg: thuật toán quản lý hoặc thỏa thuận khóa.
- enc: thuật toán mã hóa nội dung.
- kid: định danh khóa.
- typ và cty nếu có.
- zip nếu có sử dụng nén.

Do đó, JWE không che giấu toàn bộ metadata của token. Không đặt email, subject, tenant hoặc dữ liệu nhạy cảm vào protected header, unprotected header hoặc phần ngoài ciphertext.

Kích thước ciphertext, thời điểm phát hành và tần suất xuất hiện token cũng có thể tiết lộ một số thông tin về hoạt động. Mã hóa payload không tự xóa mọi side channel.

### 5.2. JWE không thay thế xác thực issuer

Đây là điểm cần chú ý khi dùng mã hóa khóa công khai:

- Nếu Authorization Server mã hóa cho public key của Resource Server, bất kỳ ai biết public key đó về nguyên tắc cũng có thể tạo ciphertext gửi tới recipient.
- Khả năng giải mã thành công không tự chứng minh ciphertext do Authorization Server tạo.
- AEAD bảo vệ tính toàn vẹn của ciphertext đối với khóa giải mã, nhưng với mô hình khóa chia sẻ, các bên cùng có khóa có thể tạo ciphertext hợp lệ.

Nếu recipient cần xác minh rõ token do issuer phát hành, hãy dùng chữ ký JWS bên trong JWE hoặc một cơ chế xác thực nguồn gửi được profile quy định.

### 5.3. JWE không ngăn replay

Kẻ tấn công có được toàn bộ JWE vẫn có thể gửi lại ciphertext tới recipient nếu không có cơ chế chống replay hoặc thu hồi. Mã hóa chỉ làm khó việc đọc nội dung; nó không chứng minh request hiện tại được gửi bởi client ban đầu.

Nếu cần chống replay, sử dụng jti/nonce và trạng thái theo profile, rotation, sender-constrained token hoặc cơ chế khác phù hợp. Không nhầm confidentiality với freshness hay proof-of-possession.

## 6. Nested JWT: ký bên trong, mã hóa bên ngoài

Khi vừa cần xác minh issuer vừa cần giữ payload bí mật trước trung gian, một cấu trúc phổ biến là **ký JWT trước rồi mã hóa JWS bên ngoài bằng JWE**:

~~~mermaid
flowchart TD
    A["Claims tối thiểu và cần thiết"] --> B["Tạo JWS bằng khóa ký issuer"]
    B --> C["JWS bảo vệ integrity và nguồn ký"]
    C --> D["Mã hóa JWS bằng JWE cho recipient"]
    D --> E["Truyền nested JWT"]
    E --> F["Recipient giải mã JWE"]
    F --> G["Nhận JWS bên trong"]
    G --> H["Xác minh chữ ký JWS và issuer"]
    H --> I["Kiểm tra claims, audience, thời gian và profile"]
~~~

Quy trình này tạo hai lớp:

1. **JWS bên trong:** recipient xác minh chữ ký và claims được issuer ký.
2. **JWE bên ngoài:** chỉ recipient có khóa giải mã mới đọc được JWS bên trong.

JOSE header của JWE có thể dùng **cty: JWT** để chỉ ra payload là một JWT lồng bên trong. Header và cấu trúc cụ thể phải tuân thủ JOSE serialization/profile được sử dụng.

### 6.1. Vì sao ký trước rồi mã hóa?

Ký trước rồi mã hóa giúp recipient vừa giải mã được nội dung vừa xác minh chữ ký issuer. Các bên trung gian không có khóa giải mã không đọc được claims hoặc chữ ký bên trong.

Nếu chỉ dùng JWE với public-key encryption, người gửi bất kỳ có public key recipient có thể tạo ciphertext. JWS bên trong cung cấp bằng chứng issuer đã ký nội dung.

### 6.2. Thứ tự xác minh

Recipient cần:

1. Parse JWE theo giới hạn kích thước và định dạng.
2. Kiểm tra alg, enc, kid và các header theo allowlist/profile.
3. Giải mã và xác minh authentication tag.
4. Nhận JWS bên trong sau khi authenticated decryption thành công.
5. Xác minh JWS bằng khóa ký thuộc issuer được tin cậy.
6. Kiểm tra issuer, audience, thời gian, token type và claims bắt buộc.
7. Kiểm tra revocation/binding nếu policy yêu cầu.

Không sử dụng plaintext trước khi JWE authentication tag hợp lệ. Không coi JWE bên ngoài hợp lệ là bằng chứng đủ để bỏ qua chữ ký issuer bên trong nếu profile yêu cầu xác thực nguồn phát hành.

### 6.3. Chi phí và vận hành

Nested JWT tăng kích thước token, độ trễ xử lý và số lượng khóa cần quản lý. Hệ thống phải vận hành cả khóa ký của issuer và khóa giải mã của recipient, bao gồm rotation, phân phối, thu hồi, backup và giám sát.

Chỉ dùng nested JWT khi có yêu cầu confidentiality thực sự giữa các thành phần. Nếu mọi bên nhận đều được phép đọc claims, JWS với payload tối thiểu có thể đơn giản hơn.

## 7. Lựa chọn 3: Opaque/reference token và tra cứu phía máy chủ

Một opaque/reference token là chuỗi ngẫu nhiên không chứa claims có ý nghĩa mà client hoặc Resource Server có thể tự diễn giải. Khi nhận token, Resource Server hoặc Authorization Server tra cứu trạng thái trong kho dữ liệu có thẩm quyền.

Ví dụ:

~~~text
rt_6pQ7mX2wN9sK4vF8...
~~~

Chuỗi trên chỉ là định danh bí mật. Dữ liệu thực tế được lưu phía máy chủ:

~~~yaml
tokenRecord:
  tokenId: record-8a12
  subjectReference: pairwise-user-7f29
  clientId: portal-client
  audience:
    - https://api.example.org/medical-records
  scopes:
    - records:read
  status: active
  expiresAt: 1893456900
~~~

Đây là cấu trúc minh họa, không phải schema chuẩn. Client không cần đọc các trường này; nó chỉ gửi reference token theo giao thức.

### 7.1. Ưu điểm về riêng tư và trạng thái

- Token không mang trực tiếp email, số điện thoại, role hoặc hồ sơ nhạy cảm.
- Dữ liệu chỉ được trả cho thành phần có quyền tra cứu.
- Có thể thu hồi token hoặc thay đổi trạng thái mà không cần chờ JWT hết hạn.
- Có thể cập nhật quyền, tenant hoặc trạng thái tài khoản theo dữ liệu hiện hành.
- Có thể ghi audit việc tra cứu và giới hạn trường được trả cho từng Resource Server.
- Giảm lượng claims phải phát tán qua client và hạ tầng trung gian.

### 7.2. Đánh đổi

- Resource Server cần truy cập kho trạng thái hoặc introspection service.
- Tăng độ trễ và phụ thuộc vào tính sẵn sàng của dịch vụ tra cứu.
- Kho trạng thái trở thành thành phần quan trọng cần bảo vệ, backup và scale.
- Cache có thể làm trạng thái thu hồi hoặc quyền mới cập nhật chậm.
- Cần thiết kế phân quyền để mỗi API chỉ nhận các trường cần thiết.

Opaque token không mặc nhiên an toàn nếu token entropy thấp, bị log hoặc được lưu ở client không an toàn. Vì vẫn là bearer credential, người sở hữu chuỗi token có thể sử dụng nó trong phạm vi được cấp nếu không có sender constraint.

## 8. Tra cứu phía máy chủ có thể dùng introspection

OAuth 2.0 Token Introspection (RFC 7662) định nghĩa cách Resource Server hỏi Authorization Server về trạng thái token. Phản hồi thường có **active** và có thể chứa scope, client, subject, audience, issuer, thời hạn hoặc metadata theo policy.

Ví dụ phản hồi minh họa:

~~~json
{
  "active": true,
  "iss": "https://identity.example.org/",
  "sub": "pairwise-user-7f29",
  "aud": "https://api.example.org/medical-records",
  "scope": "records:read",
  "exp": 1893456900
}
~~~

Resource Server cần xác thực với introspection endpoint, dùng TLS, kiểm tra nguồn phản hồi và chỉ yêu cầu những metadata cần thiết. Không gửi token tới endpoint không đáng tin cậy.

### 8.1. Trả ít dữ liệu nhất

Introspection response không cần trả toàn bộ hồ sơ người dùng. Ví dụ, API hóa đơn có thể chỉ cần:

- active.
- issuer và subject reference.
- audience.
- scope.
- exp.
- client identifier nếu policy cần.

Nếu API cần email hoặc địa chỉ, có thể gọi profile service có thẩm quyền theo quyền riêng thay vì mở rộng mọi introspection response.

### 8.2. Cache và độ trễ thu hồi

Cache kết quả active=true giúp giảm số lần gọi introspection nhưng tạo ra cửa sổ mà token đã bị thu hồi vẫn được chấp nhận cho tới khi cache hết hạn.

TTL cache phải phù hợp với yêu cầu revocation latency. Với dữ liệu hoặc thao tác nhạy cảm, có thể dùng TTL rất ngắn hoặc tra cứu trực tiếp. Không tuyên bố thu hồi tức thời nếu cache active có thể tồn tại lâu.

## 9. So sánh JWS, JWE và opaque/reference token

| Tiêu chí | JWS claims tối thiểu | JWE / nested JWT | Opaque/reference + lookup |
| --- | --- | --- | --- |
| Confidentiality của payload | Không | Có với recipient có khóa giải mã | Token không mang payload claims |
| Integrity/issuer authentication | JWS signature theo trust model | JWE integrity; thêm JWS bên trong để xác minh issuer | Dựa trên trạng thái/kênh và cơ chế tra cứu tin cậy |
| Xác minh cục bộ | Thường có | Recipient phải giải mã; nested còn verify chữ ký | Thường không, cần lookup/introspection |
| Thu hồi tức thời | Cần trạng thái bổ sung | Cần trạng thái bổ sung | Có thể cập nhật trạng thái tập trung |
| Độ trễ request | Thấp | Cao hơn do giải mã và có thể verify thêm chữ ký | Có lookup hoặc cache |
| Quản lý khóa | Khóa ký/xác minh | Khóa mã hóa/giải mã và có thể cả khóa ký | Khóa tạo token/verifier hoặc hạ tầng kho trạng thái |
| Dữ liệu lộ qua token | Claims trong payload | Header/metadata và một số đặc điểm ciphertext | Chủ yếu là chuỗi reference |
| Khả năng hoạt động khi kho trạng thái lỗi | Có thể tiếp tục xác minh cục bộ | Có thể giải mã cục bộ | Bị ảnh hưởng trực tiếp nếu không có cache/fallback |
| Phù hợp | Claims không bí mật, recipient được phép đọc | Cần bảo mật payload tới recipient cụ thể | Cần riêng tư, thu hồi và trạng thái tập trung |

Không có lựa chọn tối ưu cho mọi trường hợp. Nhiều hệ thống dùng Access Token JWS với claims tối thiểu và dùng opaque refresh token hoặc reference token cho credential cần kiểm soát vòng đời chặt.

## 10. Cây quyết định lựa chọn

~~~mermaid
flowchart TD
    A["Có cần dữ liệu này trong token không?"] --> B{"Không"}
    B --> C["Không đưa claim vào token"]
    A --> D{"Có"}
    D --> E{"Recipient có được phép đọc claim không?"}
    E --> F{"Có"}
    F --> G["Dùng JWS với claims tối thiểu"]
    E --> H{"Không"}
    H --> I{"Recipient cần tự xác minh issuer offline?"}
    I --> J{"Có"}
    J --> K["Cân nhắc nested JWS trong JWE"]
    I --> L{"Không"}
    L --> M["Cân nhắc opaque/reference token + lookup"]
    C --> N["Lấy dữ liệu qua API có thẩm quyền khi cần"]
    G --> O["Đánh giá log, storage, replay và lifetime"]
    K --> P["Quản lý khóa ký, khóa giải mã và rotation"]
    M --> Q["Quản lý availability, cache, revocation và access control"]
~~~

Các câu hỏi quyết định:

1. Dữ liệu có thực sự cần đi cùng mỗi request không?
2. Những thành phần nào có thể đọc token?
3. Recipient có cần xác minh issuer mà không gọi mạng không?
4. Trạng thái có cần thu hồi hoặc cập nhật gần thời gian thực không?
5. Hệ thống có thể vận hành an toàn khóa giải mã ở mọi recipient không?
6. Độ trễ và availability của introspection có chấp nhận được không?
7. Token có đi qua client hoặc môi trường không được tin cậy không?

Nếu claim chỉ cần ở một service, tra cứu phía máy chủ thường giảm phát tán dữ liệu. Nếu token phải đi qua nhiều bên trung gian nhưng chỉ một recipient được đọc payload và vẫn cần xác minh chữ ký issuer offline, nested JWS-in-JWE có thể phù hợp.

## 11. Quản lý khóa khi sử dụng JWE

JWE bổ sung một vòng đời khóa mã hóa bên cạnh khóa ký nếu hệ thống dùng nested JWT.

### 11.1. Phân biệt khóa ký và khóa giải mã

| Khóa | Mục đích | Ai thường giữ |
| --- | --- | --- |
| Private signing key | Ký JWS để chứng minh issuer phát hành | Issuer |
| Public verification key | Xác minh chữ ký JWS | Recipient/Resource Server |
| Public encryption key | Mã hóa JWE dành cho recipient | Issuer hoặc sender |
| Private decryption key | Giải mã JWE | Recipient |
| Shared symmetric key | Mã hóa/giải mã theo chế độ thỏa thuận khóa đối xứng | Các bên được cấp quyền |

Không dùng nhầm signing key làm encryption key nếu profile và thuật toán không cho phép. Key usage, key type, algorithm và recipient phải được ràng buộc rõ.

### 11.2. Rotation và nhiều recipient

Khi xoay khóa giải mã:

- Phát hành khóa mới và công bố/đăng ký theo kênh tin cậy.
- Issuer bắt đầu mã hóa cho khóa mới sau khi recipient sẵn sàng.
- Có thể giữ khóa cũ trong thời gian chuyển tiếp để giải mã token còn hạn.
- Ngừng nhận token dùng khóa cũ sau mốc đã định.
- Thu hồi khẩn cấp khi private key bị lộ.
- Theo dõi kid và tỷ lệ giải mã thất bại.

Không xóa khóa cũ trước khi xử lý token hợp lệ còn hiệu lực nếu kiến trúc cần giải mã chúng. Ngược lại, không giữ khóa cũ vô thời hạn chỉ vì muốn tương thích.

### 11.3. Giới hạn tác động khi khóa bị lộ

Khóa giải mã bị lộ có thể cho phép đọc các JWE được mã hóa bằng khóa đó mà attacker thu thập được. Phạm vi ảnh hưởng phụ thuộc thuật toán, cách phân phối khóa, thời gian lưu token và khả năng thu hồi.

Giảm rủi ro bằng cách:

- Tách khóa theo môi trường, recipient hoặc trust domain.
- Giới hạn quyền đọc private key.
- Dùng KMS/HSM hoặc cơ chế bảo vệ khóa phù hợp.
- Giới hạn thời hạn token.
- Có quy trình emergency rotation và đánh giá token đã bị thu thập.
- Không log plaintext hoặc private key trong quá trình xử lý lỗi.

## 12. Bảo vệ dữ liệu trong opaque/reference token store

Opaque token chuyển trọng tâm bảo vệ từ payload sang kho trạng thái:

- Sinh token bằng CSPRNG với entropy cao.
- Có thể lưu verifier/hash thay vì raw token.
- Namespace bản ghi theo issuer, client, grant hoặc token family.
- Mã hóa dữ liệu nhạy cảm trong database theo yêu cầu.
- Giới hạn quyền truy cập theo service và mục đích.
- Ghi audit việc đọc/thu hồi mà không ghi raw token.
- Đặt retention cho bản ghi hết hạn và bản ghi audit.
- Có backup, phục hồi và kiểm soát truy cập khẩn cấp.

Vì token ngẫu nhiên có entropy cao, hệ thống có thể lưu hash mật mã làm lookup key. Nếu dùng HMAC để tạo verifier, secret HMAC phải được quản lý riêng và có kế hoạch rotation. Không lưu raw bearer token trong log hoặc bảng vận hành chỉ để tiện debug.

### 12.1. Phân quyền trường dữ liệu trả về

Một kho trạng thái có thể chứa nhiều thuộc tính hơn bất kỳ API nào cần. Không trả toàn bộ record cho mọi Resource Server.

Ví dụ:

| API | Trường cần thiết |
| --- | --- |
| Invoice API | subject reference, tenant, invoice:read, exp, active |
| Profile API | subject reference, profile:read, exp, active |
| Medical Records API | subject reference, records:read, consent/status cần thiết, exp, active |

Mỗi API chỉ nhận các trường được policy cho phép. Profile service hoặc data service có thể trả dữ liệu chi tiết qua một API riêng với authorization tương ứng.

### 12.2. Failure mode khi lookup không khả dụng

Nếu API bắt buộc tra cứu trạng thái mà kho dữ liệu không khả dụng, nó không thể kết luận token còn active. Hệ thống phải định nghĩa fail-closed/fail-open theo rủi ro:

| Chính sách | Hành vi | Đánh đổi |
| --- | --- | --- |
| Fail closed | Từ chối khi không thể xác minh trạng thái bắt buộc | Tăng bảo vệ nhưng giảm availability |
| Fail open | Chấp nhận dựa trên dữ liệu cache hoặc điều kiện tối thiểu đã định | Có thể chấp nhận token đã thu hồi hoặc dữ liệu cũ |
| Bounded stale cache | Dùng trạng thái cache trong thời gian tối đa đã định | Cân bằng độ trễ và độ mới; có cửa sổ stale rõ ràng |

Không dùng fail-open ngầm. Nếu dùng stale cache, phải định nghĩa tuổi dữ liệu tối đa, cách invalidation và endpoint nào được phép dùng.

## 13. Token vẫn là dữ liệu nhạy cảm dù dùng JWE

Mã hóa payload không làm token trở thành dữ liệu vô hại:

- Bearer token vẫn có thể bị replay nếu attacker có ciphertext.
- JWE header và một số metadata vẫn hiển thị.
- Token có thể bị lộ qua URL, log, browser storage hoặc crash report.
- Recipient giải mã vẫn nhìn thấy toàn bộ payload.
- Token có thể bị liên kết qua giá trị lặp, thời điểm hoặc kích thước.
- Khóa giải mã bị compromise có thể làm lộ payload.

Vì vậy:

- Không ghi Authorization header hoặc raw token vào log.
- Không đưa token vào query string hoặc URL.
- Không gửi token tới analytics, error tracking hoặc bên thứ ba không cần thiết.
- Bảo vệ token tại client và server như credential có thể bị replay.
- Giới hạn lifetime và audience.
- Dùng sender constraint nếu threat model yêu cầu.
- Không trả plaintext claims trong error response.

## 14. Quyền riêng tư khi thiết kế claims

### 14.1. Tránh đưa dữ liệu trực tiếp nhận diện nếu không cần

Email, số điện thoại, tên, địa chỉ và ngày sinh thường không cần có trong mọi Access Token. Dùng subject identifier phù hợp hoặc tra cứu profile khi cần.

### 14.2. Hạn chế dữ liệu suy luận

Ngay cả khi từng claim có vẻ vô hại, kết hợp role, department, tenant, location, authentication method và thời điểm truy cập có thể tiết lộ cấu trúc tổ chức hoặc hành vi người dùng.

### 14.3. Pairwise subject và phạm vi liên kết

Nếu nhiều client không nên liên kết cùng một subject, pairwise subject identifier có thể giảm khả năng tương quan giữa các client theo OIDC. Tuy nhiên, issuer hoặc hệ thống có quyền truy cập mapping vẫn có thể liên kết các giá trị này; cần bảo vệ mapping.

### 14.4. Giới hạn thời gian và mục đích

Không lưu claims lâu hơn mục đích cần thiết. Token hết hạn không tự động xóa bản sao token hoặc log đã ghi trước đó. Cần có retention policy cho cache, database, backup, audit và hệ thống quan sát.

Các nghĩa vụ pháp lý về dữ liệu cá nhân phụ thuộc nơi hoạt động, loại dữ liệu và vai trò của tổ chức. Thiết kế kỹ thuật nên hỗ trợ phân loại dữ liệu, giới hạn mục đích, kiểm soát truy cập, retention và khả năng đáp ứng yêu cầu quyền riêng tư theo quy định áp dụng.

## 15. Ví dụ lựa chọn theo tình huống

| Tình huống | Lựa chọn có thể phù hợp | Lý do |
| --- | --- | --- |
| API đọc hóa đơn chỉ cần subject, audience và scope | JWS với claims tối thiểu | Recipient được phép đọc và có thể xác minh cục bộ |
| Token đi qua proxy không được đọc dữ liệu y tế | Nested JWS trong JWE tới API hồ sơ | Giữ payload bí mật trước trung gian và vẫn xác minh issuer |
| Quyền thay đổi thường xuyên, cần logout/revoke ngay | Opaque/reference token + lookup/introspection | Trạng thái active được quản lý tập trung |
| Nhiều service chỉ cần biết token active và scope | Introspection trả metadata tối thiểu | Không phát tán hồ sơ đầy đủ |
| Refresh token có rotation và reuse detection | Opaque refresh token với token-family store | Trạng thái vòng đời được cập nhật nguyên tử |
| JWT nội bộ chứa dữ liệu không cần chia sẻ cho mọi service | Claims tối thiểu hoặc JWE recipient-specific | Giảm người có thể đọc payload |
| Dữ liệu không cần thiết cho bước xác thực | Không đưa vào token; gọi data API khi cần | Giảm phát tán và thời gian lưu |

Đây là các mẫu thiết kế, không phải quy tắc bắt buộc cho mọi hệ thống. Cần xem xét trust boundary, latency, availability, key management và mức nhạy cảm của dữ liệu.

## 16. Mã giả chọn cách phân phối claims

~~~text
function designTokenRepresentation(dataRequirements, recipient, threatModel):
    requiredClaims = minimizeToClaimsNeededForCurrentPurpose(dataRequirements)

    if requiredClaims is empty:
        return NO_CLAIMS_IN_TOKEN

    if recipient is allowed to read all requiredClaims:
        if recipient needs local validation and claims are not confidential:
            return SIGNED_JWS(requiredClaims)

    if recipient needs local issuer verification
       and intermediaries must not read payload:
        return SIGN_THEN_ENCRYPT_JWE(requiredClaims, recipient)

    if current state, revocation, or privacy requires server-side control:
        return OPAQUE_REFERENCE_WITH_LOOKUP(requiredClaims)

    return REASSESS_DATA_REQUIREMENTS_AND_TRUST_BOUNDARIES
~~~

Quyết định thực tế có thể kết hợp nhiều mô hình. Ví dụ, Access Token JWS chỉ chứa claims tối thiểu, trong khi refresh token opaque và dữ liệu hồ sơ được tra cứu qua API riêng.

## 17. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách tránh |
| --- | --- | --- |
| Nghĩ Base64URL là mã hóa | Payload JWS bị đọc bởi người có token | Không đưa dữ liệu bí mật vào JWS |
| Đưa toàn bộ profile vào JWT | Phát tán dữ liệu qua client, proxy và log | Claims tối thiểu, lookup khi cần |
| Dùng JWE cho mọi token | Tăng độ phức tạp khóa và xử lý không cần thiết | Chọn theo confidentiality requirement |
| Coi JWE là bằng chứng issuer đã ký | Ciphertext có thể được tạo bởi bên có public key recipient | Nested JWS hoặc cơ chế xác thực nguồn gửi |
| Nghĩ JWE ngăn replay | Token ciphertext bị đánh cắp vẫn có thể được gửi lại | Replay store, nonce hoặc sender constraint |
| Đặt PII trong header JWE | Header vẫn hiển thị | Chỉ để metadata cần thiết trong header |
| Không xoay khóa giải mã | Khóa cũ tồn tại lâu và tăng tác động khi lộ | Rotation, retirement và emergency revoke |
| Chỉ bảo vệ token mà bỏ qua log | Token/claims bị lộ ở telemetry | Redact Authorization header và raw token |
| Opaque token entropy thấp | Credential có thể bị đoán | CSPRNG và entropy cao |
| Tra cứu trả toàn bộ record | API nhận dữ liệu vượt nhu cầu | Field-level authorization và minimization |
| Cache active quá lâu | Token đã thu hồi vẫn được chấp nhận | TTL theo revocation SLA và invalidation |
| Coi identifier giả danh là anonymous | Có thể liên kết hoạt động giữa dịch vụ | Quản lý mapping, mục đích và retention |
| Lưu claims lâu vô hạn | Dữ liệu tồn tại ngoài mục đích ban đầu | Retention cho token, cache, log và backup |

## 18. Ma trận kiểm thử dữ liệu và riêng tư

| Nhóm | Ca kiểm thử | Kết quả mong đợi |
| --- | --- | --- |
| JWS visibility | Decode payload JWS | Không có claim bí mật ngoài dự kiến |
| Data minimization | Bỏ email/địa chỉ không cần thiết | API vẫn hoạt động với subject reference |
| JWE confidentiality | Người không có private key đọc ciphertext | Không lấy được plaintext |
| JWE integrity | Sửa ciphertext hoặc authentication tag | Decryption thất bại |
| Issuer authenticity | JWE được tạo bởi bên khác dùng public key recipient | Không được tin là issuer nếu thiếu chữ ký/binding cần thiết |
| Nested JWT | JWE hợp lệ nhưng JWS bên trong sai chữ ký | Từ chối toàn bộ |
| Header exposure | Kiểm tra alg, enc, kid, typ, cty | Không có PII hoặc claim nhạy cảm trong header |
| Key rotation | Token mã hóa bằng khóa cũ trong thời gian chuyển tiếp | Xử lý đúng theo retirement policy |
| Key compromise | Khóa giải mã bị thu hồi | Không tiếp tục chấp nhận theo policy khẩn cấp |
| Opaque token | Token ngẫu nhiên sai hoặc không tồn tại | Không tra ra record active |
| Introspection | Token bị thu hồi nhưng cache active còn hạn | Hành vi khớp revocation SLA đã định |
| Field minimization | API chỉ được yêu cầu trường cần thiết | Không nhận profile hoặc dữ liệu ngoài quyền |
| Logging | Request chứa bearer token | Log không ghi raw token/Authorization header |
| Storage | Kiểm tra database/client storage | Credential và dữ liệu được bảo vệ theo policy |
| Retention | Token/cache/log hết hạn | Dữ liệu được xóa hoặc xử lý theo retention |
| Privacy | Kết hợp subject, tenant, role và telemetry | Có đánh giá khả năng liên kết và mục đích sử dụng |

## 19. Checklist triển khai

1. [ ] Phân loại claims theo mức nhạy cảm và mục đích xử lý.
2. [ ] Chỉ đưa claims thực sự cần thiết vào token.
3. [ ] Không coi Base64URL/JWS là mã hóa bí mật.
4. [ ] Chọn JWS khi recipient được phép đọc claims và cần xác minh cục bộ.
5. [ ] Chọn JWE khi cần confidentiality tới recipient; protected header không chứa dữ liệu nhạy cảm.
6. [ ] Dùng nested JWS trong JWE khi vừa cần xác minh chữ ký issuer vừa cần mã hóa payload.
7. [ ] Không coi JWE encryption bằng public key là bằng chứng issuer đã tạo token.
8. [ ] Dùng opaque/reference token và lookup khi cần kiểm soát trạng thái, thu hồi hoặc hạn chế phát tán claims.
9. [ ] Introspection chỉ trả metadata tối thiểu theo quyền của Resource Server.
10. [ ] Có policy cache và revocation latency rõ ràng.
11. [ ] Khóa ký và khóa giải mã có mục đích, quyền truy cập và vòng đời riêng.
12. [ ] Có key rotation, retirement và emergency revocation.
13. [ ] Không ghi raw token, Authorization header hoặc plaintext claims nhạy cảm vào log.
14. [ ] Bảo vệ token tại client, proxy, gateway, database, backup và telemetry.
15. [ ] Giới hạn audience, lifetime và recipient.
16. [ ] Đánh giá replay riêng; mã hóa không thay thế nonce, jti, rotation hoặc sender constraint.
17. [ ] Dùng identifier giả danh khi phù hợp và kiểm soát khả năng liên kết.
18. [ ] Có retention policy cho token, cache, log, audit và backup.
19. [ ] Có kiểm thử JWS visibility, JWE integrity/confidentiality, issuer authenticity, lookup, cache và privacy.

## 20. Tài liệu tiêu chuẩn liên quan

- **RFC 7519 — JSON Web Token (JWT):** cấu trúc JWT, claims và nested JWT.
- **RFC 7515 — JSON Web Signature (JWS):** bảo vệ tính toàn vẹn và xác minh chữ ký.
- **RFC 7516 — JSON Web Encryption (JWE):** mã hóa và authenticated encryption cho JOSE.
- **RFC 7518 — JSON Web Algorithms (JWA):** thuật toán quản lý khóa, mã hóa nội dung và chữ ký.
- **RFC 8725 — JSON Web Token Best Current Practices:** thực hành an toàn khi thiết kế và xác minh JWT.
- **RFC 7662 — OAuth 2.0 Token Introspection:** tra cứu trạng thái token phía Authorization Server.
- **RFC 7009 — OAuth 2.0 Token Revocation:** thu hồi token.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** profile Access Token dạng JWT.
- **OpenID Connect Core 1.0:** subject identifier, pairwise subject và quy tắc ID Token.

**Nguyên tắc ghi nhớ:** Đừng đưa dữ liệu vào token chỉ vì có thể ký hoặc mã hóa nó. Hãy giảm thiểu claims trước; dùng JWS khi recipient được phép đọc, JWE khi cần bảo vệ payload tới recipient cụ thể và cần xác minh nguồn ký thì dùng JWS lồng trong JWE. Khi cần trạng thái mới nhất, thu hồi hoặc giới hạn dữ liệu được chia sẻ, opaque/reference token cùng tra cứu phía máy chủ thường phù hợp hơn.
