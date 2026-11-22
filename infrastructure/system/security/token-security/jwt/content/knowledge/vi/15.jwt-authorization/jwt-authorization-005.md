# Ràng buộc quyền với audience, tenant và tài nguyên đích

## 1. Một token phải đúng API, đúng tổ chức và đúng tài nguyên

Trong hệ thống dùng JSON Web Token (JWT) làm access token, một request chỉ nên được chấp nhận khi token được phát hành cho đúng API, chủ thể có quyền trong đúng ngữ cảnh tổ chức và hành động được phép trên đúng tài nguyên.

Ba câu hỏi này liên quan nhưng không thể thay thế cho nhau:

1. **Audience:** API hoặc resource server nào được phép nhận token?
2. **Tenant:** Chủ thể đang hoạt động trong tổ chức, workspace hoặc phạm vi dữ liệu nào?
3. **Tài nguyên đích:** Đối tượng cụ thể nào đang được đọc, sửa, duyệt, tải hoặc xóa?

Giả sử một nhân viên có access token hợp lệ:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-514",
  "aud": "https://api.example.test/billing",
  "exp": 1900003600,
  "scope": "invoice:read",
  "tenant_id": "company-a"
}
~~~

Đây là payload minh họa sau khi giải mã, không phải token hoàn chỉnh có chữ ký thực. Các claim **tenant_id** và **scope** theo hợp đồng ứng dụng ví dụ.

Token có audience dành cho Billing API, scope đọc hóa đơn và tenant company-a. Điều đó vẫn không có nghĩa nhân viên được đọc mọi hóa đơn trong company-a, càng không cho phép họ đọc hóa đơn thuộc company-b hoặc dùng token này ở một API khác.

Quy tắc cốt lõi:

> **Audience ràng buộc nơi token được sử dụng; tenant ràng buộc phạm vi tổ chức; chính sách tài nguyên quyết định đối tượng cụ thể mà chủ thể được phép thao tác.**

Bài này thuộc phạm vi Security chung của JSON Web Token (JWT), áp dụng cho API, resource server và hệ thống nhiều tổ chức. Các nguyên tắc không phụ thuộc ngôn ngữ lập trình hoặc framework cụ thể.

## 2. Phân biệt ba lớp ràng buộc

| Thành phần | Câu hỏi | Ví dụ | Nguồn ý nghĩa |
| --- | --- | --- | --- |
| **Audience (aud)** | Token dành cho API/resource server nào? | https://api.example.test/billing | Registered claim của JWT; giá trị do issuer và API thống nhất. |
| **Tenant context** | Quyền đang được áp dụng trong tổ chức nào? | company-a | Thường là custom claim hoặc ngữ cảnh được xác minh từ nguồn quyền. |
| **Target resource** | Chủ thể được thao tác trên object nào? | INV-100 | ID và thuộc tính tài nguyên từ nguồn dữ liệu đáng tin cậy, kết hợp chính sách. |

Ba lớp này bảo vệ các ranh giới khác nhau:

- Kiểm tra **audience** ngăn token dành cho API A bị dùng như token dành cho API B.
- Kiểm tra **tenant** ngăn quyền của một tổ chức bị áp dụng sang tổ chức khác.
- Kiểm tra **tài nguyên đích** ngăn người dùng hợp lệ truy cập object ngoài quyền, ngay cả khi object nằm trong cùng tenant.

Không thể thay thế một lớp bằng lớp khác. Token có audience đúng vẫn có thể sai tenant; tenant đúng vẫn có thể truy cập sai object; object ID hợp lệ không chứng minh token được cấp cho API đang nhận request.

## 3. Audience: token được cấp cho ai nhận?

### 3.1. Ý nghĩa của claim aud

Trong JWT, claim đăng ký **aud** (audience) xác định những bên nhận mà JWT hướng tới. Giá trị có thể là một chuỗi hoặc một mảng chuỗi theo cấu trúc JWT. Bên nhận phải xác định danh tính của chính mình và kiểm tra token có audience phù hợp.

Ví dụ token dành cho Billing API:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-514",
  "aud": "https://api.example.test/billing",
  "exp": 1900003600
}
~~~

Billing API được cấu hình với audience kỳ vọng:

~~~text
https://api.example.test/billing
~~~

API chỉ chấp nhận token nếu giá trị audience đáp ứng hợp đồng của chính API. Không được bỏ qua kiểm tra **aud** chỉ vì chữ ký hợp lệ hoặc issuer được tin cậy.

### 3.2. Một issuer có thể phát hành token cho nhiều API

Một hệ thống có nhiều resource server:

~~~text
Identity Provider
    |
    +---- token dành cho Billing API
    |
    +---- token dành cho Reporting API
    |
    +---- token dành cho Document API
~~~

Mỗi API nên có định danh audience riêng, ví dụ:

| Resource server | Audience ví dụ |
| --- | --- |
| Billing API | https://api.example.test/billing |
| Reporting API | https://api.example.test/reporting |
| Document API | https://api.example.test/documents |

Nếu client lấy token dành cho Billing API rồi gửi tới Document API, Document API phải từ chối do audience không phù hợp, dù issuer và chữ ký đều hợp lệ.

### 3.3. Audience dạng mảng

JWT cho phép **aud** là một chuỗi hoặc mảng các chuỗi. Ví dụ:

~~~json
{
  "aud": [
    "https://api.example.test/billing",
    "https://api.example.test/reporting"
  ]
}
~~~

API cần áp dụng chính sách audience đã công bố:

- Nếu hợp đồng yêu cầu một audience duy nhất, từ chối token có thêm audience ngoài dự kiến.
- Nếu hợp đồng cho phép nhiều audience, xác định rõ API nào được nhận và quyền nào có hiệu lực ở từng API.
- Không dùng việc một API xuất hiện trong mảng làm lý do bỏ qua các kiểm tra scope, tenant hoặc tài nguyên.

Trong nhiều kiến trúc, phát hành token riêng cho từng resource server giúp giới hạn phạm vi và giảm nguy cơ token bị dùng sai dịch vụ. Nếu một token được chấp nhận bởi nhiều audience, mọi bên nhận cần hiểu chính xác cùng một hợp đồng và giới hạn quyền.

### 3.4. Audience không phải client_id

**aud** trả lời câu hỏi token dành cho resource server nào. **client_id** (trong các profile hoặc hợp đồng có claim này) nhận diện ứng dụng khách liên quan đến việc xin hoặc sử dụng token. Hai giá trị có vai trò khác nhau:

~~~text
client_id = billing-portal
aud       = https://api.example.test/billing
sub       = user-514
~~~

- **client_id:** ứng dụng khách.
- **aud:** API nhận token.
- **sub:** chủ thể mà token đại diện theo issuer.

Không dùng client_id thay cho audience, và không giả định client_id là người dùng cuối.

### 3.5. ID token và access token không thể thay thế cho nhau

Trong OpenID Connect, ID token được phát hành để ứng dụng khách nhận thông tin xác thực người dùng; access token được dùng để truy cập resource server theo phạm vi được cấp. Một ID token có chữ ký hợp lệ không vì thế trở thành access token hợp lệ cho API.

API cần kiểm tra đúng loại token/profile, issuer, audience, thời gian và các yêu cầu claims. Không chấp nhận một token chỉ vì nó là JWT và có chữ ký đúng.

Với hệ thống áp dụng JWT Profile for OAuth 2.0 Access Tokens (RFC 9068), profile này định nghĩa cách biểu diễn access token, bao gồm dấu hiệu kiểu token và các claim liên quan. Hệ thống dùng profile khác phải theo hợp đồng của chính mình.

## 4. Audience trong OAuth và Resource Indicators

Trong OAuth 2.0, ứng dụng khách cần xin token dành cho một resource server cụ thể. **OAuth 2.0 Resource Indicators** (RFC 8707) định nghĩa tham số request **resource** để client chỉ ra tài nguyên mà token được dự kiến sử dụng.

Ví dụ yêu cầu cấp token có thể mang:

~~~http
POST /token HTTP/1.1
Host: identity.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&
resource=https%3A%2F%2Fapi.example.test%2Fbilling
~~~

Authorization server dùng thông tin resource theo chính sách để quyết định cấp token dành cho resource đó. Token được phát hành sau đó cần có audience phù hợp với resource server theo profile và hợp đồng được áp dụng.

Lưu ý:

- Tham số request **resource** theo RFC 8707 không phải một registered claim bắt buộc trong mọi JWT.
- Client yêu cầu một resource không có nghĩa authorization server phải chấp thuận; server phải xác minh client, grant, user, policy và quyền được cấp.
- Resource identifier cần ổn định và được quản lý; không lấy URL tùy ý từ client rồi tin rằng đó là API được phép.
- Resource server vẫn xác minh **aud** trên token nhận được.

Resource Indicators giúp ràng buộc token vào nơi sử dụng dự kiến, giảm tình huống một token rộng được dùng khắp hệ thống.

## 5. Tenant: quyền đang áp dụng trong tổ chức nào?

Audience xác định API nhận token, nhưng thường không đủ để giới hạn dữ liệu giữa các khách hàng của cùng API. Một Billing API có thể phục vụ hàng nghìn công ty; mỗi công ty là một tenant.

### 5.1. Tenant là ngữ cảnh phân quyền

Ví dụ:

~~~json
{
  "sub": "user-514",
  "aud": "https://api.example.test/billing",
  "tenant_id": "company-a",
  "scope": "invoice:read invoice:create"
}
~~~

Trong hợp đồng ứng dụng này, **tenant_id** xác định ngữ cảnh tổ chức mà các quyền liên quan được áp dụng. Đây là custom claim, không phải registered claim có ngữ nghĩa chung bắt buộc trong JWT.

API phải biết:

- Ai có thẩm quyền phát hành tenant_id?
- Tenant đó có thuộc membership hiện hành của principal không?
- Token có đại diện cho một tenant duy nhất hay nhiều tenant?
- Quyền nào được áp dụng trong tenant đó?
- Resource thực tế có thuộc tenant đã xác minh không?

Không dùng tenant_id từ token như một bằng chứng duy nhất nếu membership có thể thay đổi hoặc cần thu hồi nhanh. Tùy rủi ro, API có thể tra cứu membership hiện hành hoặc kiểm tra phiên bản quyền.

### 5.2. Một tenant trên mỗi access token

Một mô hình thường dễ kiểm tra là token chỉ mang một tenant context:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-514",
  "aud": "https://api.example.test/billing",
  "tenant_id": "company-a",
  "scope": "invoice:read",
  "exp": 1900003600
}
~~~

Khi người dùng chuyển sang company-b, ứng dụng lấy token có tenant context phù hợp theo quy trình cấp quyền. Resource server không tự đổi tenant chỉ vì client sửa URL.

Ưu điểm:

- Claims gọn và rõ ràng.
- Ít nhập nhằng khi kiểm tra tenant.
- Dễ giới hạn quyền và audit theo từng ngữ cảnh.
- Ít nguy cơ hợp nhất quyền từ nhiều tenant.

Giới hạn là client có thể cần xin token mới khi đổi tenant. Việc này cần được cân nhắc với trải nghiệm và chính sách cấp token.

### 5.3. Nhiều tenant trong một token

Một hệ thống có thể thiết kế custom claim cho nhiều tenant:

~~~json
{
  "tenant_permissions": {
    "company-a": ["invoice.read", "invoice.approve"],
    "company-b": ["invoice.read"]
  }
}
~~~

Đây không phải định dạng chuẩn JWT. Nếu chọn mô hình này, hợp đồng phải quy định:

- Cách chọn tenant đang hoạt động cho request.
- Cách đối chiếu tenant được chọn với resource thật.
- Cách biểu diễn role, scope và permission theo từng tenant.
- Giới hạn kích thước token và số tenant.
- Cách cập nhật hoặc thu hồi quyền của riêng một tenant.
- Hành vi khi claim thiếu, sai kiểu hoặc chứa tenant không được hỗ trợ.

Không gom permission của company-a và company-b thành một danh sách toàn cục:

~~~text
company-a: invoice.read, invoice.approve
company-b: invoice.read

Sai nếu gộp thành:
invoice.read, invoice.approve
~~~

Việc gộp làm mất ngữ cảnh, có thể cho phép duyệt hóa đơn company-b dù quyền duyệt chỉ được cấp ở company-a.

### 5.4. Tenant trong URL không phải tenant được cấp quyền

Request:

~~~http
GET /tenants/company-b/invoices/INV-200 HTTP/1.1
Authorization: Bearer <token-for-company-a>
~~~

Đường dẫn chỉ nói client muốn truy cập company-b. API phải xác minh principal có membership và quyền phù hợp ở company-b hay không. Nếu token chỉ dành cho company-a và hợp đồng không cho phép chuyển ngữ cảnh, request phải bị từ chối.

Tenant được chọn có thể đến từ path, header, query hoặc body. Vị trí truyền không làm nó đáng tin cậy. Server phải xác minh tenant đó dựa trên token và nguồn membership có thẩm quyền.

## 6. Tài nguyên đích: object cụ thể mà request muốn thao tác

Ngay cả khi audience và tenant đều đúng, API vẫn phải kiểm tra object cụ thể.

Ví dụ:

~~~text
Audience: Billing API
Tenant: company-a
Principal: user-514
Scope: invoice:read

INV-100: company-a, owner=user-514
INV-101: company-a, owner=user-999
INV-200: company-b, owner=user-514
~~~

Kết quả có thể là:

| Request | Audience | Tenant | Quyền trên object | Quyết định |
| --- | --- | --- | --- | --- |
| Đọc INV-100 | Đúng | Đúng | Là owner và các điều kiện khác đạt | **ALLOW** |
| Đọc INV-101 | Đúng | Đúng | Không phải owner, không có quyền chia sẻ/kiểm toán | **DENY** |
| Đọc INV-200 | Đúng | Không phù hợp | Object thuộc tenant khác | **DENY** |
| Gửi token Billing tới Document API | Sai | Không cần xét tiếp | Audience không dành cho API này | **Từ chối token** |

### 6.1. Resource phải được tải từ nguồn đáng tin cậy

ID trong URL, query hoặc body chỉ là khóa để tìm object:

~~~http
GET /invoices/INV-101
~~~

API cần tải bản ghi hóa đơn và đọc các thuộc tính như:

~~~text
invoice.id
invoice.tenant_id
invoice.owner_id
invoice.state
invoice.classification
invoice.created_by
~~~

Những thuộc tính này phải đến từ kho dữ liệu hoặc dịch vụ quản lý tài nguyên có thẩm quyền. Không tin các giá trị owner_id, tenant_id hoặc state do client gửi kèm để tự chứng minh quyền.

### 6.2. Quyền phụ thuộc hành động

Một principal có thể được phép đọc nhưng không được sửa hoặc duyệt:

| Action | Kiểm tra quyền ví dụ |
| --- | --- |
| invoice.read | Scope đọc và quan hệ owner/auditor trong tenant. |
| invoice.update | Permission sửa, owner hoặc quan hệ quản lý, trạng thái cho phép sửa. |
| invoice.approve | Permission duyệt, role hiện hành, giới hạn phê duyệt và điều kiện tách nhiệm vụ. |
| invoice.delete | Permission xóa, trạng thái, retention và quyền quản trị phù hợp. |

Không suy quyền từ tên role chung hoặc từ việc token có một scope gần giống. API cần ánh xạ action cụ thể vào chính sách.

### 6.3. Quyền phụ thuộc quan hệ

Không phải mọi quyền đều dựa trên owner. Một tài liệu có thể được chia sẻ cho người dùng hoặc nhóm. Chính sách cần xác minh quan hệ còn hiệu lực:

~~~text
ALLOW document.read nếu:
    principal là owner
    OR có direct share còn hiệu lực
    OR principal thuộc group được chia sẻ
    OR principal có vai trò kiểm toán trong tenant
~~~

Khi chia sẻ bị thu hồi, API phải nhận biết thay đổi theo yêu cầu thu hồi của hệ thống. Một claim role trong token không tự cập nhật theo quan hệ chia sẻ.

## 7. Ghép audience, tenant và tài nguyên thành một quyết định

Một quyết định truy cập có thể được mô tả:

~~~text
ALLOW khi:
    token hợp lệ
    AND expected_audience nằm trong token.aud
    AND token purpose/profile đúng cho API
    AND principal được xác định từ issuer + subject
    AND tenant context được phép và còn hiệu lực
    AND resource thuộc tenant context đã xác minh
    AND scope/permission cho phép action
    AND policy cho phép principal thao tác trên resource
    AND context nghiệp vụ phù hợp

Mọi điều kiện bắt buộc không đạt: DENY
~~~

Thứ tự có thể thay đổi theo cách triển khai, nhưng API không được thực thi hành động trước khi có đủ bằng chứng cho phép.

### 7.1. Sơ đồ quyết định

~~~mermaid
flowchart TD
    A["Request tới resource server"] --> B{"JWT hợp lệ và đúng loại token?"}
    B -- "Không" --> X["Từ chối xác thực"]
    B -- "Có" --> C{"aud dành cho API hiện tại?"}
    C -- "Không" --> X
    C -- "Có" --> D["Xác định principal và tenant context"]
    D --> E{"Principal được phép dùng tenant?"}
    E -- "Không" --> Y["DENY"]
    E -- "Có" --> F["Tải resource từ nguồn tin cậy"]
    F --> G{"Resource thuộc tenant đã xác minh?"}
    G -- "Không" --> Y
    G -- "Có" --> H{"Scope/permission cho phép action?"}
    H -- "Không" --> Y
    H -- "Có" --> I{"Object policy cho phép?"}
    I -- "Không" --> Y
    I -- "Có" --> J["Thực thi action"]
~~~

### 7.2. Vì sao phải kiểm tra audience trước khi dùng claims phân quyền?

Giả sử Reporting API nhận một token có:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-514",
  "aud": "https://api.example.test/billing",
  "scope": "invoice:read",
  "tenant_id": "company-a"
}
~~~

Reporting API không được đọc claim scope rồi quyết định rằng user có quyền đọc báo cáo. Token được cấp cho Billing API. Dù hai API cùng dùng issuer, subject và tenant, audience vẫn sai.

Kiểm tra audience sớm giúp tránh việc một dịch vụ sử dụng claims có ý nghĩa trong hợp đồng của dịch vụ khác.

## 8. Token substitution và confused deputy

### 8.1. Token substitution

Token substitution xảy ra khi một token hợp lệ cho một mục đích hoặc resource server bị dùng ở một nơi khác không được dự kiến.

Ví dụ:

~~~text
1. Client lấy access token dành cho Billing API.
2. Client gửi token đó tới Document API.
3. Document API chỉ kiểm tra chữ ký và exp.
4. Document API chấp nhận token dù aud không dành cho nó.
~~~

Đây là lỗi thiếu ràng buộc audience. Kẻ tấn công có thể tận dụng token có quyền ở dịch vụ này để thử truy cập dịch vụ khác.

Phòng tránh:

- Mỗi resource server xác minh audience của chính mình.
- Token có mục đích và profile rõ ràng.
- Không dùng ID token thay access token.
- Không dùng một khóa/issuer đáng tin làm lý do bỏ qua audience.
- Giới hạn scope/permission theo resource server.

### 8.2. Confused deputy

**Confused deputy** là tình huống một thành phần có quyền cao bị đánh lừa để dùng quyền của nó thay mặt một caller không đủ quyền.

Ví dụ, Billing API có quyền gọi Document API để tải chứng từ. Người dùng A chỉ được đọc hóa đơn của company-a nhưng gửi yêu cầu khiến Billing API tải chứng từ của company-b. Nếu Billing API dùng credential dịch vụ rộng của mình mà không kiểm tra quyền của người dùng trên tài liệu đích, Document API có thể thấy một service principal hợp lệ và trả dữ liệu.

Đường gọi nội bộ vẫn cần giữ ngữ cảnh ủy quyền:

- Kiểm tra quyền của caller trên tài nguyên trước khi gọi dịch vụ tiếp theo.
- Dùng token dành cho đúng downstream audience.
- Giới hạn quyền của token downstream theo hành động và tài nguyên cần thiết.
- Nếu dùng service identity, phân biệt quyền của service với quyền được ủy quyền từ caller.
- Không để dịch vụ có quyền rộng trở thành proxy vượt qua kiểm soát của người dùng.

### 8.3. Token forwarding và token exchange

Không nên chuyển nguyên access token của API A sang API B nếu token có audience chỉ dành cho API A. Một lựa chọn là yêu cầu authorization server cấp token mới dành cho API B, với quyền hẹp hơn theo luồng ủy quyền được thiết kế.

OAuth 2.0 Token Exchange (RFC 8693) mô tả cơ chế đổi token. Hệ thống có thể dùng token đầu vào đại diện cho subject/actor và yêu cầu token đầu ra dành cho resource server tiếp theo, theo chính sách của authorization server.

Ví dụ về mục tiêu:

~~~text
Incoming token:
    aud = Billing API
    scope = invoice:read invoice:approve

Downstream token:
    aud = Document API
    scope = document:read
    resource/tenant constraints = chỉ chứng từ cần xử lý
~~~

Đây là minh họa ý tưởng, không phải cú pháp request token exchange đầy đủ. Authorization server phải kiểm tra caller, subject, actor, audience/resource, grant và quyền được phép ủy quyền. Token mới không được tự động kế thừa mọi quyền rộng của token đầu vào.

## 9. Thiết kế claim và hợp đồng cho audience, tenant

Một hợp đồng token cho Billing API có thể định nghĩa:

~~~yaml
contract_id: billing-access/v1
token_purpose: access_token
trusted_issuer: https://identity.example.test
expected_audience: https://api.example.test/billing
allowed_algorithms:
  - RS256

claims:
  iss:
    type: string
    required: true
  sub:
    type: string
    required: true
  aud:
    type: string_or_array_of_strings
    required: true
    policy: billing_api_must_be_an_intended_recipient
  exp:
    type: numeric_date
    required: true
  tenant_id:
    type: string
    required: true
    meaning: selected_tenant_context
  scope:
    type: string
    format: space_delimited_exact_tokens
    required: true

authorization:
  tenant_membership_check: required
  resource_tenant_match: required
  object_level_policy: required
  missing_or_invalid_required_claim: deny
  unsupported_audience: reject_token
~~~

Đây là đặc tả ứng dụng minh họa, không phải schema chuẩn bắt buộc của JWT. Các trường tenant_id và phần authorization là quy ước của hệ thống ví dụ.

Hợp đồng nên quy định thêm:

- Audience là URI hay identifier dạng khác; cách chuẩn hóa và so khớp chính xác.
- API có chấp nhận nhiều audience không.
- Một token có thể mang một tenant hay nhiều tenant.
- Tenant context được chọn bởi ai và được xác minh bằng nguồn nào.
- Scope nào có hiệu lực cho audience này.
- Resource server có kiểm tra membership hiện hành không.
- Object policy cần thuộc tính và quan hệ nào.
- Hành vi khi thiếu claim, sai kiểu hoặc gặp issuer chưa hỗ trợ.

Không tự động chuẩn hóa URL audience bằng cách bỏ path, đổi scheme hoặc so khớp chuỗi con. Audience phải được so khớp theo định danh đã thống nhất. Ví dụ, https://api.example.test/billing không đồng nghĩa với https://api.example.test/documents.

## 10. Tránh nhầm lẫn giữa resource server và resource object

Từ “resource” thường được dùng ở hai mức:

1. **OAuth resource server / API resource:** nơi client dùng access token, ví dụ Billing API. Điều này liên quan đến audience và Resource Indicators.
2. **Business resource / object:** dữ liệu nghiệp vụ mà API quản lý, ví dụ hóa đơn INV-100, tài liệu DOC-200 hoặc tài khoản ACC-300.

Một audience có thể đại diện cho API quản lý hàng triệu object. Vì vậy, aud = Billing API không thể liệt kê mọi hóa đơn mà chủ thể được phép đọc.

Tương tự, một object ID không phải audience. aud = INV-100 thường không phải cách mô hình hóa quyền đối với object trong một API tổng quát. API cần audience cho resource server, sau đó áp dụng object-level authorization trên object được yêu cầu.

Ví dụ:

~~~text
aud = https://api.example.test/billing
tenant_id = company-a
request resource = invoice INV-100

API:
    xác minh aud
    xác minh tenant context
    tải INV-100
    kiểm tra INV-100 thuộc company-a
    kiểm tra user có invoice.read trên INV-100
~~~

Không gộp ba lớp thành một claim chung như resource_access = true nếu không có định nghĩa rõ phạm vi và ngữ nghĩa.

## 11. Các trường hợp API và kiến trúc thường gặp

### 11.1. Một API phục vụ nhiều tenant

Ví dụ Billing API dùng chung cho company-a và company-b:

~~~text
Audience: Billing API
Tenant: company-a
Object: INV-100 (company-a)
~~~

Audience giống nhau cho mọi tenant vì cùng resource server. Tenant mới là ranh giới tổ chức. API phải xác minh tenant membership và object tenant ở từng request.

### 11.2. Nhiều API cùng phục vụ một tenant

Một người dùng company-a có thể dùng Billing API và Document API:

~~~text
Billing token:
    aud = Billing API
    tenant_id = company-a
    scope = invoice:read

Document token:
    aud = Document API
    tenant_id = company-a
    scope = document:read
~~~

Tenant có thể giống nhau nhưng audience và scope khác nhau. Không gửi Billing token tới Document API.

### 11.3. Một tài nguyên được tham chiếu qua nhiều API

Một hóa đơn có thể được hiển thị ở Billing API và Reporting API. Điều đó không có nghĩa hai API phải dùng chung audience hoặc chính sách.

- Billing API có thể cho phép cập nhật và duyệt.
- Reporting API có thể chỉ cho phép đọc dữ liệu đã tổng hợp.
- Document API có thể cho phép tải chứng từ gắn với hóa đơn.

Mỗi API kiểm tra token dành cho chính mình và áp dụng policy riêng cho dữ liệu mà nó phục vụ. Nếu một thao tác đi qua nhiều dịch vụ, quyền được ủy quyền phải được giới hạn xuyên suốt chuỗi gọi.

### 11.4. Service-to-service

Một service principal có thể có quyền gọi Billing API để xử lý báo cáo. Token của service phải có audience phù hợp và scope hẹp. Nếu service đang thay mặt một user, kiến trúc phải phân biệt:

- Danh tính của service thực hiện lời gọi.
- Danh tính của user được ủy quyền.
- Hành động và tài nguyên được phép trong lần ủy quyền đó.

Không suy quyền của user từ quyền của service hoặc ngược lại. Service có thể có quyền kỹ thuật rộng hơn, nhưng không được dùng quyền đó để vượt qua chính sách của user khi thao tác được thực hiện thay mặt user.

## 12. Pseudocode: xác minh audience, tenant và tài nguyên

Ví dụ dưới đây mô tả một request đọc hóa đơn. Hàm validateAccessToken phải kiểm tra đầy đủ chữ ký, thuật toán, issuer, audience, thời gian và profile token.

~~~text
function readInvoice(request):
    token = extractBearerToken(request.headers.Authorization)

    verified = validateAccessToken(
        token,
        trustedIssuer = "https://identity.example.test",
        expectedAudience = "https://api.example.test/billing",
        allowedAlgorithms = ["RS256"],
        tokenPurpose = "access_token"
    )
    if verified.failed:
        return HTTP 401

    claims = verified.claims
    principal = resolvePrincipal(claims.iss, claims.sub)
    if principal is null:
        return HTTP 403

    tenant = resolveTenantContext(
        principal,
        claims.tenant_id,
        request.selectedTenant
    )
    if tenant is null:
        return HTTP 403

    membership = loadCurrentMembership(principal, tenant.id)
    if membership is null or not membership.active:
        return HTTP 403

    if not exactScopeContains(claims.scope, "invoice:read"):
        return HTTP 403

    invoice = loadInvoiceByIdAndTenant(
        request.path.invoiceId,
        tenant.id
    )
    if invoice is null:
        return HTTP 404

    if invoice.tenant_id != tenant.id:
        return HTTP 404

    decision = policy.evaluate(
        principal = principal,
        action = "invoice.read",
        resource = invoice,
        context = {
            tenant: tenant,
            membership: membership
        }
    )
    if decision != ALLOW:
        return HTTP 404

    return HTTP 200 with permittedInvoiceFields(invoice, principal)
~~~

Các điểm cần lưu ý:

- expectedAudience là định danh của Billing API, không phải tenant hoặc invoice ID.
- tenant_id được diễn giải theo hợp đồng custom claim và được đối chiếu với membership.
- loadInvoiceByIdAndTenant giới hạn truy vấn ngay từ nguồn dữ liệu.
- Chính sách vẫn đánh giá quan hệ của principal với object cụ thể.
- 404 được dùng trong ví dụ để che giấu object ngoài phạm vi; API có thể dùng 403 nếu hợp đồng yêu cầu.

## 13. Những lỗi thường gặp khi ràng buộc audience, tenant và resource

| Sai lầm | Rủi ro | Cách phòng tránh |
| --- | --- | --- |
| Không kiểm tra aud | Token dành cho API khác được chấp nhận. | Mỗi resource server xác minh audience của chính mình. |
| Chấp nhận mọi token cùng issuer | Token đúng issuer nhưng sai mục đích/audience vẫn lọt. | Kiểm tra issuer, audience, profile, thời gian và loại token. |
| Dùng client_id thay audience | Nhầm ứng dụng khách với API nhận token. | Xác định riêng client, subject và audience. |
| Dùng ID token làm access token | Token sai mục đích được dùng cho API. | Chỉ chấp nhận access token theo profile/hợp đồng. |
| Gộp nhiều tenant vào một danh sách permission | Quyền tenant A có thể lan sang tenant B. | Gắn mỗi quyền với tenant context. |
| Tin tenant_id từ URL hoặc body | Client tự chọn tenant không có quyền. | Xác minh tenant từ token và membership hiện hành. |
| Coi tenant đúng là đủ | Object khác owner hoặc bị hạn chế vẫn có thể bị truy cập. | Kiểm tra object-level policy. |
| Coi audience là resource object | Một token cho API bị hiểu nhầm là quyền trên mọi object. | Tách API audience và object authorization. |
| Forward token nguyên bản sang downstream API | Token có thể sai audience hoặc quyền quá rộng. | Dùng token dành cho downstream resource, cân nhắc token exchange/downscoping. |
| Dùng service credential thay quyền của user | Confused deputy khiến service dùng quyền rộng thay caller. | Giữ ngữ cảnh ủy quyền và kiểm tra quyền end-to-end. |
| So khớp audience bằng chuỗi con | Audience gần giống có thể bị chấp nhận nhầm. | So khớp chính xác theo định danh đã thống nhất. |
| Cho phép nhiều audience không có chính sách | Nhiều API nhận token với quyền/ý nghĩa khác nhau. | Giới hạn audience hoặc định nghĩa rõ quyền theo từng bên nhận. |

## 14. Kiểm thử ranh giới audience, tenant và tài nguyên

Một bộ kiểm thử nên xác minh từng lớp độc lập và các tổ hợp của chúng.

### 14.1. Kiểm thử audience

~~~text
Token aud = Billing API, gửi tới Billing API
    -> có thể tiếp tục kiểm tra các lớp quyền

Token aud = Billing API, gửi tới Document API
    -> từ chối token

Token aud thiếu
    -> từ chối nếu hợp đồng yêu cầu audience

Token aud là mảng có Billing API và API khác
    -> xử lý theo chính sách multi-audience đã công bố

ID token có chữ ký đúng nhưng không phải access token
    -> từ chối
~~~

### 14.2. Kiểm thử tenant

~~~text
Principal là member của company-a, token tenant company-a
    -> chỉ tiếp tục trong company-a

Principal không phải member của company-b
    -> request company-b bị từ chối

Client sửa URL từ company-a sang company-b
    -> không làm thay đổi tenant được phép

Membership company-a bị thu hồi sau khi token phát hành
    -> API xử lý theo cơ chế quyền hiện hành/thu hồi đã thiết kế

Token có nhiều tenant nhưng action chỉ được cấp ở một tenant
    -> không được áp dụng action sang tenant còn lại
~~~

### 14.3. Kiểm thử tài nguyên

~~~text
Đúng audience + đúng tenant + object thuộc owner
    -> ALLOW nếu các điều kiện khác đạt

Đúng audience + đúng tenant + object thuộc người khác
    -> DENY nếu không có quan hệ/quyền bổ sung

Đúng audience + sai tenant của object
    -> DENY

Đúng audience + đúng tenant + object ở trạng thái bị khóa
    -> DENY

Đúng audience + scope read + request action approve
    -> DENY
~~~

### 14.4. Kiểm thử chuỗi service-to-service

- Billing token không được dùng trực tiếp ở Document API.
- Token exchange chỉ cấp audience downstream đã được chấp thuận.
- Downstream token có scope hẹp hơn hoặc bằng quyền được ủy quyền.
- Service không dùng quyền kỹ thuật rộng để vượt quyền của user.
- Tenant và resource context được giữ hoặc xác minh lại ở từng service.
- Audit ghi nhận cả actor/service và subject được đại diện theo hợp đồng.

### 14.5. Kiểm thử cấu hình và lỗi

- API cấu hình nhầm expected audience phải làm token bị từ chối, không fallback sang chấp nhận mọi audience.
- Claim tenant thiếu hoặc sai kiểu phải xử lý theo hợp đồng, thường là deny.
- Membership service không khả dụng phải tuân theo chính sách fail-open/fail-closed đã định nghĩa.
- Cache không được trả quyết định ALLOW của tenant hoặc resource khác.
- Response không tiết lộ object ngoài phạm vi qua thông báo, metadata hoặc phân trang.

## 15. Checklist thiết kế

Trước khi đưa một API vào sử dụng, cần trả lời:

1. **Audience:** API có một audience định danh ổn định không? Có chấp nhận nhiều audience không?
2. **Token purpose:** API phân biệt access token với ID token hoặc token loại khác như thế nào?
3. **Issuer và thuật toán:** những issuer/thuật toán nào được tin cậy; khóa được lấy từ nguồn nào?
4. **Client và subject:** client nào xin token; token đại diện cho user hay service?
5. **Tenant:** token biểu diễn một tenant hay nhiều tenant? Nguồn membership và cách thu hồi là gì?
6. **Scope/permission:** quyền nào có hiệu lực cho audience này; có bị giới hạn theo tenant không?
7. **Resource:** object được tải từ nguồn nào; tenant, owner, relationship và state lấy từ đâu?
8. **Action:** read, update, approve, delete, export và download có chính sách riêng không?
9. **Downstream:** token có bị forward không? Nếu có, audience và quyền có được đổi/thu hẹp đúng cách?
10. **Service identity:** có phân biệt quyền của service với quyền của user được đại diện không?
11. **Cache và trạng thái:** quyết định quyền có phụ thuộc membership hoặc trạng thái hiện hành không?
12. **Audit:** có ghi nhận audience, subject, tenant, action, resource và kết quả cần thiết mà không log token không?
13. **Testing:** có kiểm thử token sai audience, tenant khác, object khác owner và chuỗi service-to-service không?

## 16. Ghi nhớ trọng tâm

- **Audience** xác định resource server dự kiến nhận token; mỗi API phải kiểm tra audience của chính mình.
- **Tenant** xác định ngữ cảnh tổ chức của quyền; nó thường là custom claim và phải được đối chiếu với membership cùng tài nguyên thực tế.
- **Tài nguyên đích** là object cụ thể; API phải tải object từ nguồn đáng tin cậy và kiểm tra quyền theo principal, action, resource và context.
- Đúng audience không có nghĩa đúng tenant; đúng tenant không có nghĩa có quyền trên mọi object.
- Không dùng client_id thay aud, không dùng ID token làm access token và không forward token sai audience sang downstream.
- Token exchange/downscoping có thể giúp cấp token cho API tiếp theo với phạm vi hẹp, nhưng authorization server vẫn phải kiểm tra quyền ủy quyền.
- Khi thiếu bằng chứng cho bất kỳ ràng buộc bắt buộc nào, mặc định từ chối và tránh tiết lộ dữ liệu ngoài phạm vi.

**Tài liệu tham khảo kỹ thuật:** RFC 7519 (JSON Web Token, claim aud); RFC 8725 (JWT Best Current Practices); RFC 9068 (JWT Profile for OAuth 2.0 Access Tokens); RFC 8707 (Resource Indicators for OAuth 2.0); RFC 8693 (OAuth 2.0 Token Exchange); OpenID Connect Core (ID Token và audience). Các chuẩn mô tả token, resource server và luồng ủy quyền; ranh giới tenant và chính sách object cụ thể vẫn do ứng dụng định nghĩa.
