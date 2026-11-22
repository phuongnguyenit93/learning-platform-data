# Tách quy trình phát hành, xác minh và quyết định phân quyền

## 1. Vì sao cần tách ba quy trình?

Khi tích hợp thư viện JWT vào một hệ thống, một lỗi thiết kế thường gặp là gom mọi thao tác vào một bước mang tên “xử lý JWT”. Ứng dụng nhận một chuỗi token, giải mã payload, kiểm tra chữ ký rồi dùng các claims để quyết định cho phép request. Cách nhìn này bỏ qua ba trách nhiệm bảo mật khác nhau:

1. **Phát hành (issuance):** quyết định có cấp credential hay không, cấp cho ai, dành cho resource nào, có quyền gì và trong bao lâu; sau đó tạo và ký token.
2. **Xác minh (verification):** kiểm tra credential nhận được có được phát hành bởi nguồn tin cậy, dành cho đúng bên nhận, đúng loại token và còn hiệu lực hay không.
3. **Quyết định phân quyền (authorization):** quyết định subject/client đã được xác minh có được thực hiện hành động cụ thể trên tài nguyên cụ thể trong ngữ cảnh hiện tại hay không.

Ba bước có liên hệ nhưng không thể thay thế nhau. Một token được ký hợp lệ chưa chắc được phát hành cho API đang nhận. Một access token hợp lệ chưa chắc có scope cần thiết. Một token có scope phù hợp cũng chưa chắc được phép truy cập một bản ghi thuộc tenant hoặc người dùng khác.

**Thư viện JWT giúp thực hiện thao tác mật mã và xử lý định dạng; ứng dụng và chính sách bảo mật vẫn chịu trách nhiệm quyết định cấp credential và quyền truy cập.**

Bài viết thuộc phạm vi **Security - JSON Web Token (JWT)** tổng quát, tập trung vào cách tổ chức và tích hợp các thành phần phát hành, xác minh và phân quyền, không phụ thuộc ngôn ngữ lập trình hay framework.

## 2. Ba trách nhiệm và ranh giới tin cậy

| Quy trình | Câu hỏi cần trả lời | Đầu vào chính | Kết quả |
| --- | --- | --- | --- |
| Phát hành | Có nên cấp token và token đại diện cho quyền nào? | Danh tính đã xác minh, client, grant, resource, consent và chính sách cấp quyền | JWT đã ký hoặc token response |
| Xác minh | Token có đáng tin và được dùng đúng ngữ cảnh không? | Token nhận được, cấu hình issuer, audience, profile và khóa tin cậy | Principal/claims đã xác minh hoặc lỗi xác minh |
| Phân quyền | Chủ thể có được phép thực hiện hành động này không? | Principal đã xác minh, action, resource, context và policy | Allow hoặc deny |

Sơ đồ khái niệm:

~~~mermaid
flowchart LR
    subgraph AS["Authorization Server / Issuer"]
        A["Xác minh client, grant, subject"]
        B["Đánh giá chính sách cấp quyền"]
        C["Tạo claims và ký JWT"]
        A --> B --> C
    end
    C -->|"Access token"| T["Client"]
    T -->|"Bearer token"| V["Resource Server"]
    subgraph RS["Resource Server"]
        V --> D["Xác minh token"]
        D --> E["Tạo principal đã xác minh"]
        E --> F["Đánh giá policy trên action/resource"]
        F --> G["Cho phép hoặc từ chối"]
    end
~~~

Issuer giữ trách nhiệm phát hành credential. Resource server giữ trách nhiệm xác minh credential và áp dụng chính sách trên tài nguyên mà nó bảo vệ. Client chuyển token theo giao thức và bảo vệ token; client không tự quyết định rằng claims trong payload đã được tin cậy.

## 3. Quy trình phát hành token

### 3.1. Phát hành là một quyết định bảo mật

Thư viện ký JWT không biết người dùng đã đăng nhập hợp lệ hay chưa, client có được phép yêu cầu scope nào, resource nào đã chấp thuận hoặc tổ chức có chính sách cấp quyền gì. Nó chỉ có thể tạo chữ ký từ dữ liệu mà ứng dụng cung cấp.

Vì vậy, trước khi gọi chức năng tạo JWT, thành phần phát hành cần:

1. Xác minh danh tính hoặc client theo giao thức đang sử dụng.
2. Xác minh authorization grant và các điều kiện consent/chính sách có liên quan.
3. Xác định subject mà token đại diện.
4. Xác định client đã yêu cầu token.
5. Xác định audience/resource được phép nhận token.
6. Tính scope/permission từ chính sách có thẩm quyền.
7. Chọn loại token/profile và thời hạn phù hợp.
8. Tạo claims từ dữ liệu đã được xác minh, sau đó ký bằng khóa phát hành.

Không nhận nguyên trạng role, scope, tenant hoặc subject do client gửi lên rồi đưa vào token. Dữ liệu yêu cầu từ client chỉ là đầu vào cần đánh giá; quyền được cấp phải xuất phát từ chính sách và nguồn dữ liệu có thẩm quyền.

### 3.2. Tách quyết định cấp quyền khỏi thao tác ký

Một cấu trúc logic có thể gồm:

- **Grant evaluator:** xác định yêu cầu có đủ điều kiện cấp token không.
- **Claims builder:** tạo tập claims theo profile và kết quả chính sách.
- **Signing component:** chọn khóa/thuật toán đã cấu hình và ký nội dung.
- **Token response builder:** trả access token, token type, expires_in và scope theo giao thức.

Luồng này giúp không biến thư viện ký thành nơi tự suy luận quyền. Nếu chính sách từ chối yêu cầu, không được tạo token rồi hy vọng resource server sẽ từ chối sau đó.

### 3.3. Claims phải tuân theo hợp đồng

Với JWT access token, các claims phụ thuộc profile. Ví dụ, RFC 9068 quy định profile JWT Access Token với các claims cốt lõi như issuer, subject, audience, client_id, thời điểm phát hành, thời điểm hết hạn và token ID. Một hệ thống có thể có claims mở rộng như scope hoặc tenant, nhưng phải định nghĩa ngữ nghĩa và kiểu dữ liệu nhất quán.

Ví dụ payload minh họa:

~~~json
{
  "iss": "https://authorization.example.org",
  "sub": "account-42",
  "aud": "https://api.example.org/orders",
  "client_id": "shopping-client",
  "iat": 1893456000,
  "exp": 1893456900,
  "jti": "at-7f31",
  "scope": "orders:read"
}
~~~

Đây là Claims Set minh họa, không phải token đã ký. Issuer phải bảo đảm claims được tạo theo đúng profile, dữ liệu có thẩm quyền và thời hạn đã chọn.

### 3.4. Không để thư viện tự chọn chính sách khóa

Thành phần phát hành phải nhận khóa từ cấu hình hoặc hệ thống quản lý khóa được tin cậy. Không lấy secret từ request, không hardcode khóa trong source code và không dùng giá trị mặc định của thư viện trong production.

Với chữ ký bất đối xứng, private key chỉ nằm ở issuer hoặc thành phần ký được ủy quyền. Với HMAC, mọi bên giữ secret đều có khả năng ký; cần giới hạn số thành phần được cấp secret. Thuật toán được chọn từ allowlist của hệ thống, không phải từ dữ liệu không đáng tin do client cung cấp.

## 4. Quy trình xác minh token

### 4.1. Giải mã không phải xác minh

Nhiều thư viện cung cấp hàm decode/parse để tách header và payload. Thao tác này chỉ giúp đọc cấu trúc token; nó không chứng minh chữ ký hợp lệ, issuer đáng tin hoặc audience phù hợp.

Không sử dụng claims từ payload trước khi hoàn tất xác minh. Đặc biệt, không lấy sub, role, scope hoặc tenant từ một JWT chưa được xác minh để truy vấn dữ liệu nhạy cảm hay quyết định quyền.

### 4.2. Pipeline xác minh

Resource server cần một quy trình xác minh rõ ràng:

~~~mermaid
flowchart TD
    A["Nhận token"] --> B["Giới hạn kích thước và parse cấu trúc"]
    B --> C["Xác định loại token/profile được hỗ trợ"]
    C --> D["Chọn issuer và khóa từ cấu hình tin cậy"]
    D --> E["Áp dụng allowlist thuật toán"]
    E --> F["Xác minh chữ ký hoặc MAC"]
    F --> G["Kiểm tra issuer, audience và claims bắt buộc"]
    G --> H["Kiểm tra exp, nbf, iat và thời gian"]
    H --> I["Kiểm tra trạng thái/ sender constraint nếu yêu cầu"]
    I --> J["Tạo principal đã xác minh"]
    J --> K["Chuyển sang bước phân quyền"]
~~~

Thư viện có thể gộp một số bước thành một API xác minh cấp cao. Dù vậy, ứng dụng vẫn phải cấu hình đúng issuer, audience, thuật toán, profile, nguồn khóa và các điều kiện bổ sung. Một hàm trả về “valid” chỉ có ý nghĩa trong phạm vi cấu hình đã truyền cho nó.

### 4.3. Những kiểm tra cốt lõi

| Kiểm tra | Mục đích | Nếu bỏ qua |
| --- | --- | --- |
| Loại token/profile | Ngăn dùng nhầm ID token, access token hoặc assertion | Cross-token confusion |
| Allowlist thuật toán | Giới hạn thuật toán được phép | Có thể chấp nhận thuật toán không an toàn hoặc sai loại |
| Chữ ký/MAC | Xác minh tính toàn vẹn và khóa phát hành | Claims có thể bị sửa hoặc giả mạo |
| Issuer | Chỉ tin nguồn phát hành đã cấu hình | Chấp nhận token từ nguồn không tin cậy |
| Audience | Ràng buộc token với đúng API/resource | Token của API khác có thể bị dùng nhầm |
| Expiration và thời gian | Giới hạn cửa sổ chấp nhận | Token cũ có thể được sử dụng lâu hơn dự kiến |
| Claims bắt buộc | Bảo đảm token đáp ứng profile | Token thiếu ngữ nghĩa cần thiết vẫn được chấp nhận |
| Revocation/sender constraint | Áp dụng trạng thái và ràng buộc bổ sung khi cần | Khó xử lý token bị lộ hoặc proof bị phát lại |

### 4.4. Nguồn khóa phải được tin cậy

Với chữ ký bất đối xứng, resource server thường lấy public key từ JWKS hoặc kho khóa đã cấu hình. Issuer phải được xác định trước; không lấy URL từ header token rồi tự động tải khóa từ nơi bất kỳ. Header kid chỉ giúp chọn một khóa trong tập khóa tin cậy.

Với HMAC, verifier cần cùng secret với issuer. Điều đó đồng nghĩa verifier có khả năng tạo chữ ký. Nếu có nhiều resource server, hãy cân nhắc chữ ký bất đối xứng để verifier chỉ cần public key và không có quyền phát hành token.

### 4.5. Xác minh thành công tạo ra principal đã tin cậy

Sau khi toàn bộ kiểm tra đạt, resource server có thể tạo một principal hoặc security context chứa subject, client, issuer, audience, scope và claims cần thiết. Dữ liệu này được xem là đã xác minh trong phạm vi profile và chính sách cấu hình.

Principal không phải bản sao tùy tiện của toàn bộ payload. Chỉ đưa vào các trường cần thiết cho phân quyền và audit. Không truyền nguyên token qua các lớp nghiệp vụ nếu không có lý do rõ ràng.

## 5. Quy trình quyết định phân quyền

### 5.1. Token hợp lệ không có nghĩa mọi hành động đều được phép

Xác minh trả lời câu hỏi credential có đáng tin trong ngữ cảnh API hay không. Phân quyền trả lời câu hỏi principal có được phép thực hiện hành động cụ thể trên tài nguyên cụ thể hay không.

Ví dụ, một access token có:

~~~json
{
  "sub": "account-42",
  "aud": "orders-api",
  "scope": "orders:read"
}
~~~

Token có thể hợp lệ với orders API và có scope đọc đơn hàng. Nhưng request đọc đơn hàng của account khác vẫn có thể bị từ chối vì principal không sở hữu tài nguyên hoặc không thuộc tenant được phép.

### 5.2. Phân quyền cần nhiều hơn claims trong token

Quyết định có thể kết hợp:

- **Principal:** subject/client đã xác minh.
- **Action:** hành động như read, create, update, approve hoặc delete.
- **Resource:** bản ghi, đơn hàng, tài khoản, tenant hoặc đối tượng cụ thể.
- **Claims:** scope, role, tenant hoặc thuộc tính đã được phát hành theo hợp đồng.
- **Current state:** trạng thái tài khoản, quyền vừa bị thu hồi, trạng thái tài nguyên.
- **Context:** thời gian, mức xác thực, thiết bị hoặc điều kiện nghiệp vụ nếu policy yêu cầu.

Không nên giả định mọi quyền đều có thể đóng băng trong JWT. Quyền thay đổi thường xuyên hoặc cần thu hồi tức thì có thể phải được kiểm tra từ nguồn trạng thái hiện tại.

### 5.3. Scope, role và permission không đồng nghĩa

| Khái niệm | Vai trò thường gặp |
| --- | --- |
| Scope | Phạm vi quyền mà client được cấp trong OAuth token |
| Role | Nhóm trách nhiệm/quyền được gán cho subject trong một miền ứng dụng |
| Permission | Quyền cụ thể trên một hành động hoặc loại tài nguyên |
| Resource ownership | Quan hệ subject với tài nguyên, ví dụ chủ sở hữu hoặc thành viên tenant |

Tên và ngữ nghĩa của các giá trị này phải được định nghĩa trong hợp đồng. Không có quy tắc phổ quát rằng scope orders:read tự động tương đương role ADMIN hoặc quyền đọc mọi bản ghi.

### 5.4. Ví dụ quyết định

| Request | Token đã xác minh | Kiểm tra policy | Kết quả |
| --- | --- | --- | --- |
| Đọc đơn hàng thuộc account-42 | Audience đúng, scope orders:read | Subject là chủ sở hữu | Allow |
| Đọc đơn hàng thuộc account-99 | Audience đúng, scope orders:read | Subject không sở hữu, không có quyền chia sẻ | Deny |
| Xóa đơn hàng | Audience đúng, chỉ có orders:read | Thiếu permission orders:delete | Deny |
| Gọi API thanh toán bằng token audience orders-api | Chữ ký hợp lệ nhưng audience sai | Không tiếp tục policy nghiệp vụ | Reject token |
| Gọi API bằng token hết hạn | Không vượt qua verification | Không đánh giá policy | Reject token |

## 6. Hợp đồng giữa issuer và resource server

Việc tách thành phần chỉ hiệu quả khi issuer và resource server thống nhất một token contract.

Hợp đồng cần xác định:

1. Issuer Identifier và cách tin cậy metadata/JWKS.
2. Loại token/profile được phát hành.
3. Thuật toán và cách quản lý/luân chuyển khóa.
4. Audience/resource identifier.
5. Claims bắt buộc, kiểu dữ liệu và ngữ nghĩa.
6. Scope/permission được cấp và cách ánh xạ.
7. Thời hạn token, clock skew và thời điểm chấp nhận.
8. Cách xử lý revocation, introspection hoặc sender constraint nếu có.
9. Hành vi lỗi khi token sai, thiếu quyền hoặc dịch vụ trạng thái không sẵn sàng.

Không nên để từng API tự suy đoán ngữ nghĩa của claim tùy chỉnh. Ví dụ claim tenant có thể là tenant được subject chọn, tenant mà client được phép truy cập hoặc tenant của tài nguyên. Nếu không định nghĩa rõ, hai resource server có thể đưa ra quyết định trái ngược trên cùng một token.

## 7. Tổ chức các thư viện và thành phần tích hợp

Một ứng dụng có thể dùng cùng một thư viện JOSE/JWT cho nhiều thao tác, nhưng nên phân tách cấu hình và quyền sử dụng theo vai trò.

| Thành phần logic | Thao tác thư viện | Quyền/secret cần có |
| --- | --- | --- |
| Token issuer | Tạo header/claims, ký JWS hoặc mã hóa JWE | Private signing key hoặc HMAC secret; quyền phát hành |
| Token verifier | Parse và xác minh chữ ký, claims, profile | Public verification key hoặc HMAC secret; không cần quyền cấp token |
| Authorization evaluator | Đánh giá principal/action/resource/context | Policy và dữ liệu quyền; thường không cần signing key |
| Key provider | Cung cấp khóa đúng issuer, purpose và phiên bản | Quyền đọc khóa theo least privilege |
| Revocation/status provider | Tra cứu trạng thái hoặc introspection khi cần | Quyền truy cập nguồn trạng thái có thẩm quyền |

### 7.1. Không chia sẻ quyền ký cho mọi verifier

Nếu mọi resource server đều giữ private key hoặc HMAC secret có quyền ký, một API bị xâm nhập có thể tạo token giả cho các API khác cùng tin khóa đó.

Với mô hình nhiều verifier:

- Ưu tiên chữ ký bất đối xứng khi phù hợp.
- Private key chỉ ở issuer hoặc dịch vụ ký chuyên trách.
- Resource server chỉ giữ public key cần để xác minh.
- Tách khóa theo môi trường, issuer và miền tin cậy.
- Không cấp quyền gọi key-management service rộng hơn nhu cầu.

### 7.2. Tách cấu hình phát hành và xác minh

Issuer và verifier có các cấu hình khác nhau:

| Cấu hình phát hành | Cấu hình xác minh |
| --- | --- |
| Signing algorithm được phép | Verification algorithm allowlist |
| Signing key/private key | Trusted public keys hoặc HMAC secret |
| Issuer claim | Expected issuer |
| Audience được cấp | Expected audience |
| Claims builder và token lifetime | Required claims và time validation |
| Token type/profile được phát hành | Token type/profile được chấp nhận |

Không dùng một cấu hình mặc định chung cho mọi dịch vụ. Mỗi resource server cần audience và profile cụ thể.

### 7.3. Authorization evaluator không cần biết cách ký JWT

Thành phần phân quyền nên nhận principal đã xác minh và dữ liệu action/resource/context. Nó không cần private key, HMAC secret hoặc chức năng tạo JWT.

Thiết kế này giảm phạm vi ảnh hưởng nếu policy engine hoặc module nghiệp vụ bị xâm nhập. Đồng thời, nó giúp kiểm thử policy độc lập với thư viện JOSE.

## 8. Pseudocode cho ba bước độc lập

Ví dụ dưới đây là pseudocode trung lập, minh họa ranh giới trách nhiệm chứ không phải API của một thư viện cụ thể.

### 8.1. Phát hành

~~~text
grant = evaluate_grant(
    authenticated_subject,
    authenticated_client,
    requested_resource,
    requested_scope
)

if grant.denied:
    reject_token_request()

claims = build_access_token_claims(
    issuer = configured_issuer,
    subject = grant.subject,
    audience = grant.resource,
    client_id = grant.client_id,
    scope = grant.approved_scope,
    issued_at = now(),
    expires_at = grant.expiry,
    token_id = generate_unique_id()
)

token = jwt_sign(claims, configured_signing_key, allowed_algorithm)
return token_response(token, grant.expiry, grant.approved_scope)
~~~

Điểm quan trọng: grant evaluator quyết định quyền được cấp trước khi claims builder tạo token. Signing function không tự quyết định subject hoặc scope.

### 8.2. Xác minh

~~~text
verified = jwt_verify(
    token,
    trusted_keys_for_configured_issuer,
    allowed_algorithms,
    expected_issuer,
    expected_audience,
    required_token_profile
)

if not verified.valid:
    reject_as_invalid_credential()

principal = create_verified_principal(
    issuer = verified.issuer,
    subject = verified.subject,
    client = verified.client_id,
    scopes = verified.scopes,
    claims = selected_verified_claims
)
~~~

Các tham số cấu hình phải đến từ nguồn tin cậy. Không lấy expected issuer, audience hoặc allowlist thuật toán từ chính token đang được xác minh.

### 8.3. Phân quyền

~~~text
decision = authorization_policy.evaluate(
    principal = principal,
    action = request.action,
    resource = loaded_resource,
    context = current_security_context
)

if decision.allowed:
    execute_business_operation()
else:
    deny_access()
~~~

Resource cần được tải và kiểm tra theo cách không tạo side effect trái phép trước khi policy quyết định. Không tin resource ID hoặc tenant ID do client gửi mà chưa đối chiếu với dữ liệu có thẩm quyền.

## 9. Xử lý lỗi và phân biệt 401 với 403

Tách xác minh và phân quyền giúp phản hồi lỗi rõ ràng:

| Tình huống | Giai đoạn | Kết quả HTTP thường gặp |
| --- | --- | --- |
| Không có token trong endpoint yêu cầu xác thực | Authentication | 401 Unauthorized |
| Chữ ký sai, token hết hạn, issuer/audience sai hoặc sai loại | Verification | 401 Unauthorized |
| Token hợp lệ nhưng thiếu scope theo hợp đồng bearer | Authorization | 403 Forbidden, có thể dùng insufficient_scope |
| Token hợp lệ nhưng subject không có quyền trên tài nguyên | Authorization | 403 Forbidden hoặc phản hồi không tiết lộ sự tồn tại tài nguyên theo chính sách |
| Token hợp lệ nhưng trạng thái tài khoản đã bị khóa | Authorization/current-state policy | Từ chối theo chính sách; có thể yêu cầu xác thực lại |

Không trả thông tin chi tiết về khóa, cấu hình issuer nội bộ hoặc lý do nhạy cảm cho client không đáng tin. Log nội bộ có thể ghi mã lỗi, request ID và giai đoạn thất bại, nhưng không ghi token nguyên văn.

## 10. Các lỗi tích hợp thường gặp

1. **Decode rồi tin claims:** parse payload nhưng không xác minh chữ ký, issuer và audience.
2. **Để thư viện ký quyết định quyền:** đưa role/scope do request cung cấp thẳng vào token.
3. **Xác minh chữ ký rồi cho phép mọi thao tác:** nhầm token hợp lệ với quyền truy cập không giới hạn.
4. **Không kiểm tra audience:** token dành cho API khác được chấp nhận.
5. **Dùng chung secret HMAC cho nhiều dịch vụ:** mọi verifier có thể trở thành issuer nếu secret bị lộ.
6. **Dùng một validator cho mọi loại JWT:** ID token, access token và assertion bị nhầm lẫn.
7. **Lấy JWKS URL từ token:** để dữ liệu không tin cậy quyết định nguồn khóa.
8. **Không thống nhất claims contract:** cùng một claim bị hiểu khác nhau giữa các API.
9. **Dùng scope như quyền trên từng bản ghi:** bỏ qua ownership, tenant và trạng thái tài nguyên.
10. **Đóng băng mọi quyền trong token quá lâu:** thay đổi quyền không có hiệu lực cho đến khi token hết hạn.
11. **Authorization evaluator nhận raw token:** khiến logic nghiệp vụ tự decode hoặc xác minh không nhất quán.
12. **Trả lỗi chung cho mọi trường hợp:** khó phân biệt credential không hợp lệ với thiếu quyền và khó vận hành.
13. **Không có kiểm soát revocation khi cần:** token bị lộ hoặc quyền bị thu hồi vẫn có thể được chấp nhận đến exp.

## 11. Checklist tích hợp

### Phát hành

- [ ] Danh tính subject và client đã được xác minh trước khi cấp token.
- [ ] Grant evaluator kiểm tra resource, scope, consent và policy.
- [ ] Claims được tạo từ dữ liệu có thẩm quyền, không lấy nguyên trạng từ client.
- [ ] Issuer, audience, token type, thời gian và claims tuân theo profile.
- [ ] Signing algorithm và key đến từ cấu hình tin cậy.
- [ ] Chỉ issuer/dịch vụ ký được quyền giữ private key hoặc HMAC secret.

### Xác minh

- [ ] Không sử dụng claims trước khi xác minh token.
- [ ] Có giới hạn kích thước và kiểm tra cấu trúc token.
- [ ] Có allowlist thuật toán.
- [ ] Khóa được chọn từ issuer/JWKS/kho khóa tin cậy.
- [ ] Kiểm tra chữ ký/MAC, issuer, audience, token type và claims bắt buộc.
- [ ] Kiểm tra exp, nbf, iat và clock skew.
- [ ] Có kiểm tra trạng thái, revocation hoặc sender constraint nếu yêu cầu.
- [ ] Principal chỉ chứa claims đã xác minh và cần thiết.

### Phân quyền

- [ ] Policy nhận principal đã xác minh, action, resource và context.
- [ ] Scope/role/permission có ngữ nghĩa được định nghĩa rõ.
- [ ] Kiểm tra ownership, tenant và trạng thái tài nguyên.
- [ ] Quyền thay đổi nhanh được đối chiếu nguồn trạng thái hiện tại khi cần.
- [ ] Quyết định deny là mặc định khi policy hoặc dữ liệu quyền không xác định.
- [ ] Không đưa signing key vào authorization evaluator.

### Vận hành

- [ ] Issuer và verifier có cấu hình riêng.
- [ ] Có quy trình luân chuyển/thu hồi khóa.
- [ ] Có hợp đồng claims và audience được quản lý phiên bản.
- [ ] Có kiểm thử token sai chữ ký, sai issuer/audience, hết hạn, sai profile và thiếu quyền.
- [ ] Log phân biệt lỗi verification với authorization nhưng không ghi token.
- [ ] Có giám sát lỗi JWKS, revocation store và policy source.

## 12. Kết luận

Tích hợp JWT an toàn cần tách rõ **phát hành, xác minh và quyết định phân quyền**. Issuer xác minh grant và chính sách cấp quyền trước khi tạo claims và ký token. Resource server xác minh token theo issuer, audience, loại token, chữ ký và thời gian trước khi tạo principal đáng tin. Authorization evaluator dùng principal đó cùng action, resource, context và policy để quyết định cho phép hay từ chối.

Thư viện JWT cung cấp các thao tác JOSE/JWT; nó không tự biết ai được cấp quyền hoặc người dùng có được đọc một tài nguyên cụ thể hay không. Tách các trách nhiệm giúp giới hạn quyền của từng thành phần, giảm chia sẻ signing key, làm rõ hợp đồng giữa dịch vụ và kiểm thử từng lớp độc lập.

**Token hợp lệ là điều kiện để tiếp tục đánh giá quyền; nó không phải quyết định cho phép truy cập.**

## Tài liệu chuẩn để đọc tiếp

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): định dạng JWT và registered claims.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): ký và xác minh JWS.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): biểu diễn khóa và JWKS.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): thuật toán JOSE.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): xác minh JWT theo ngữ cảnh và chống nhầm lẫn token.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile JWT access token và quy tắc xác minh.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): vai trò authorization server, client, access token và resource server.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): cách trình bearer token và xử lý lỗi.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): tra cứu trạng thái token.
- [NIST SP 800-162 — Guide to Attribute Based Access Control (ABAC)](https://csrc.nist.gov/pubs/sp/800/162/upd2/final): mô hình quyết định quyền dựa trên subject, resource, action và environment attributes.
