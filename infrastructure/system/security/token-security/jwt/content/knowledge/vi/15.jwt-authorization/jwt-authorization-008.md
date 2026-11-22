# Phối hợp claims trong token với dữ liệu phân quyền cập nhật

## 1. Vì sao cần kết hợp token với dữ liệu quyền hiện hành?

JSON Web Token (JWT) thường mang những thông tin đã được issuer xác nhận tại thời điểm phát hành, chẳng hạn chủ thể, audience, scope, role, permission hoặc tenant context. Resource server có thể xác minh chữ ký và đọc claims để đưa ra quyết định mà không cần gọi lại issuer trong mọi request.

Tuy nhiên, trạng thái phân quyền của ứng dụng có thể thay đổi sau khi token được cấp:

- Người dùng vừa bị gỡ khỏi một tenant.
- Role phê duyệt vừa bị thu hồi.
- Một tài liệu vừa được chia sẻ cho người dùng khác hoặc share cũ vừa bị hủy.
- Hóa đơn vừa chuyển từ PENDING sang APPROVED.
- Người dùng vừa bị khóa hoặc phiên đăng nhập bị kết thúc.
- Hạn mức giao dịch hoặc chính sách rủi ro vừa thay đổi.

JWT cũ vẫn chứa claims đã ký trước đó. Nếu API chỉ dựa vào token, nó có thể dùng một ảnh chụp quyền không còn phản ánh trạng thái hiện hành. Ngược lại, nếu API chỉ đọc dữ liệu quyền hiện hành mà bỏ qua giới hạn được cấp trong token, một token vốn chỉ được cấp scope hẹp có thể bị mở rộng ngoài ý định ban đầu.

Vì vậy, hệ thống cần định nghĩa cách **phối hợp claims đã xác minh trong token với dữ liệu phân quyền cập nhật**. Câu hỏi không chỉ là “token có role gì?” mà còn là:

1. Claim nào được dùng làm bằng chứng về danh tính hoặc giới hạn quyền?
2. Dữ liệu nào là nguồn sự thật hiện hành?
3. Khi token và dữ liệu hiện hành khác nhau, quy tắc nào có quyền quyết định?
4. Dữ liệu quyền được cập nhật nhanh đến đâu và cache có thể cũ bao lâu?
5. Quyết định được kiểm tra tại thời điểm nào so với lúc thao tác tài nguyên?

Nguyên tắc cốt lõi:

> **Token cung cấp bằng chứng đã ký trong phạm vi và thời điểm phát hành; nguồn phân quyền hiện hành cung cấp trạng thái động. API phải kết hợp chúng theo một hợp đồng rõ ràng, có quy tắc khi dữ liệu thiếu, cũ hoặc mâu thuẫn.**

Bài này thuộc phạm vi Security chung của JSON Web Token (JWT), áp dụng cho API, resource server và hệ thống phân quyền phân tán. Nội dung không phụ thuộc một ngôn ngữ lập trình hoặc framework cụ thể.

## 2. Phân biệt claims trong JWT và dữ liệu phân quyền cập nhật

Hai nguồn dữ liệu có vòng đời và mức độ tin cậy khác nhau.

| Nguồn | Ví dụ | Đặc điểm |
| --- | --- | --- |
| **Claims trong JWT đã xác minh** | iss, sub, aud, exp, scope, roles, permissions, tenant_id | Được issuer ký; phản ánh thông tin tại thời điểm phát hành; không tự cập nhật khi trạng thái bên ngoài đổi. |
| **Dữ liệu danh tính hiện hành** | Trạng thái tài khoản, trạng thái phiên, loại principal | Có thể thay đổi sau khi token được cấp; thường lấy từ identity/session store hoặc dịch vụ có thẩm quyền. |
| **Dữ liệu membership** | Thành viên tenant, nhóm, phòng ban, trạng thái thành viên | Có thể được thêm, gỡ, tạm khóa hoặc thay đổi theo thời gian. |
| **Dữ liệu quyền hiện hành** | Role assignment, permission grant, delegation, ACL, policy version | Phản ánh quyền đang có hiệu lực theo nguồn quản trị quyền. |
| **Dữ liệu tài nguyên** | Owner, tenant, trạng thái hóa đơn, phân loại tài liệu | Thuộc dịch vụ sở hữu resource; phải được lấy từ nguồn dữ liệu có thẩm quyền. |
| **Ngữ cảnh request** | Action, thời gian, thiết bị, mức xác thực, risk signal | Thay đổi theo request; có thể ảnh hưởng quyết định chính sách. |

### 2.1. Claims trong token không phải bản ghi hiện hành

Ví dụ access token:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-514",
  "aud": "https://api.example.test/billing",
  "iat": 1900000000,
  "exp": 1900003600,
  "scope": "invoice:read invoice:approve",
  "tenant_id": "company-a",
  "roles": ["invoice_approver"],
  "permissions": ["invoice.read", "invoice.approve"],
  "authz_version": 12
}
~~~

Đây là payload minh họa sau khi giải mã, không phải JWT hoàn chỉnh có chữ ký thực. Các claim roles, permissions, tenant_id và authz_version là quy ước của hợp đồng ứng dụng ví dụ.

Token phản ánh rằng tại lúc phát hành, issuer đã cấp những scope, role và permission này trong tenant company-a. Nó không tự chứng minh rằng:

- User-514 vẫn còn là thành viên company-a.
- Role invoice_approver chưa bị thu hồi.
- Permission invoice.approve vẫn còn hiệu lực.
- Hóa đơn đang ở trạng thái cho phép duyệt.
- Phiên hoặc tài khoản chưa bị vô hiệu hóa.

Các dữ kiện này cần được kiểm tra từ nguồn hiện hành nếu chính sách yêu cầu.

### 2.2. Dữ liệu hiện hành không thay thế việc xác minh JWT

Một API không nên bỏ qua JWT rồi chỉ tìm user bằng một header hoặc ID client gửi. Dữ liệu hiện hành phải được gắn với principal đã được xác minh.

Ví dụ:

~~~text
Verified principal = (iss, sub)
    -> resolve internal account
    -> load current membership and permissions
    -> evaluate requested action on actual resource
~~~

Không được dùng dữ liệu quyền của user-999 nếu JWT đã xác minh đại diện user-514. Cặp issuer và subject là cơ sở để ánh xạ principal; các thuộc tính khác cần được lấy từ nguồn có thẩm quyền.

## 3. Xác định vai trò của từng nguồn trước khi kết hợp

Trước khi viết logic authorization, hãy phân loại claims và dữ liệu động theo vai trò.

### 3.1. Token làm bằng chứng danh tính và giới hạn API

Một thiết kế có thể giữ trong token:

- Issuer và subject.
- Audience và mục đích token.
- Thời hạn.
- Client hoặc actor nếu profile yêu cầu.
- Scope được cấp cho API.
- Tenant context hoặc permission snapshot nếu hợp đồng cần.
- Phiên bản hợp đồng hoặc phiên bản quyền.

Token giúp resource server biết request đến từ một principal đã được issuer xác nhận và quyền tối đa nào đã được cấp cho access token.

### 3.2. Nguồn hiện hành làm sự thật về trạng thái có thể thay đổi

Các dữ liệu sau thường nên được đọc từ nguồn hiện hành nếu cần phản ánh thay đổi nhanh:

- Tài khoản còn active hay đã disabled.
- Membership trong tenant còn hiệu lực hay đã revoked.
- Role/permission assignment mới nhất.
- Delegation hoặc share đã hết hạn/bị thu hồi.
- Resource owner, tenant và trạng thái nghiệp vụ.
- Policy version hoặc trạng thái rủi ro hiện tại.

### 3.3. Không có một quy tắc cố định cho mọi claim

Một số hệ thống dùng JWT chỉ để xác thực; quyền nghiệp vụ được tính hoàn toàn từ nguồn hiện hành. Hệ thống khác đưa permission vào token và dùng dữ liệu hiện hành để thu hẹp quyền. Cả hai cách có thể hợp lệ nếu hợp đồng nói rõ.

Điều không an toàn là để từng API tự đoán:

- API A coi roles trong token là nguồn sự thật.
- API B coi database role mới nhất là nguồn duy nhất.
- API C lấy hợp của hai tập quyền.
- API D bỏ qua permission claim khi dịch vụ quyền lỗi.

Các cách hiểu khác nhau có thể tạo ra kết quả phân quyền không nhất quán giữa các dịch vụ.

## 4. Mô hình phối hợp: token là giới hạn quyền, dữ liệu hiện hành thu hẹp thêm

Khi JWT chứa scope hoặc permission đã được cấp, một mô hình bảo thủ là coi chúng như **trần quyền của token**. Dữ liệu hiện hành có thể thu hẹp quyền đó, nhưng không tự mở rộng quyền vượt quá những gì token được cấp.

Ví dụ:

~~~text
Token permissions:
    invoice.read
    invoice.approve

Current permissions:
    invoice.read

Effective permissions:
    invoice.read
~~~

Permission invoice.approve đã bị thu hồi trong nguồn hiện hành nên request duyệt phải bị từ chối, dù claim cũ vẫn còn trong JWT.

Có thể biểu diễn:

\[
P_{\text{effective}} =
P_{\text{token}} \cap P_{\text{current}}
\]

Đây là mô hình phù hợp khi cả token và nguồn hiện hành đều là các giới hạn bắt buộc của quyền. Không phải mọi kiến trúc đều bắt buộc dùng phép giao; nếu token chỉ mang danh tính và không mang permission, nguồn hiện hành có thể là nơi quyết định quyền. Điều quan trọng là hợp đồng phải chọn một mô hình rõ ràng.

### 4.1. Bảng quyết định cho mô hình giới hạn

| Token snapshot | Quyền hiện hành | Quyết định ví dụ |
| --- | --- | --- |
| Có invoice.read | Có invoice.read | Có thể tiếp tục đánh giá resource policy. |
| Có invoice.approve | Không còn invoice.approve | DENY. |
| Không có invoice.export | Hiện tại có invoice.export | DENY hoặc yêu cầu cấp token mới theo hợp đồng. |
| Không có invoice.delete | Có invoice.delete | Không tự mở rộng token cũ. |
| Có invoice.update | Tài khoản bị disabled | DENY. |
| Có invoice.approve | Permission hiện hành còn nhưng hóa đơn đã PAID | DENY theo resource policy. |

### 4.2. Vì sao không nên lấy hợp (union) quyền?

Giả sử:

~~~text
Token permissions:   [invoice.read]
Current permissions: [invoice.read, invoice.delete]
~~~

Nếu API lấy hợp hai tập, token cũ có thể tự nhiên nhận invoice.delete dù token không được cấp quyền đó. Điều này biến dữ liệu hiện hành thành cơ chế nâng quyền mà không có một lần cấp token mới hoặc quyết định ủy quyền rõ ràng.

Phép hợp chỉ có thể được dùng nếu thiết kế chủ đích quy định token không mang quyền nghiệp vụ mà chỉ xác thực danh tính, và nguồn hiện hành là nguồn duy nhất cấp quyền. Khi đó cần thể hiện rõ điều này trong hợp đồng; không được vô tình dùng union giữa hai nguồn có ngữ nghĩa khác nhau.

### 4.3. Scope, role và permission có thể có vai trò khác nhau

Ví dụ:

- Scope giới hạn API action mà access token được phép yêu cầu.
- Role hiện hành mô tả trách nhiệm hiện tại của user trong tenant.
- Permission hiện hành được tính từ role, ACL hoặc policy.
- Resource policy kiểm tra owner, trạng thái và thuộc tính object.

Một quyết định có thể cần tất cả điều kiện:

~~~text
ALLOW khi:
    token có scope invoice:approve
    AND token permission snapshot có invoice.approve
    AND current membership active
    AND current permission có invoice.approve
    AND resource thuộc tenant được phép
    AND resource state = PENDING
    AND business policy cho phép principal duyệt
~~~

## 5. Khi token chỉ mang danh tính, quyền được tính hoàn toàn từ nguồn hiện hành

Không phải JWT nào cũng cần chứa roles hoặc permissions. Một mô hình khác là access token chỉ mang:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-514",
  "aud": "https://api.example.test/billing",
  "exp": 1900003600
}
~~~

Resource server xác minh token, ánh xạ principal rồi lấy membership, role, permission và resource policy từ nguồn có thẩm quyền.

### 5.1. Ưu điểm

- Giảm nguy cơ claims role/permission cũ trong token.
- Có thể thay đổi quyền mà không cần phát hành lại token chỉ vì thay role.
- Token nhỏ hơn và chứa ít dữ liệu phân quyền hơn.
- Quy tắc quyền có thể được tập trung trong policy service hoặc nguồn quyền dùng chung.

### 5.2. Giới hạn

- Mỗi request có thể cần truy vấn dịch vụ quyền hoặc cache.
- API phụ thuộc vào tính sẵn sàng và độ trễ của nguồn dữ liệu hiện hành.
- Cần bảo vệ tính nhất quán giữa các dịch vụ và vùng triển khai.
- Phải xác định cách xử lý khi dịch vụ quyền không khả dụng.

### 5.3. Không để scope bị mất ý nghĩa

Ngay cả khi permission nghiệp vụ được tính động, scope vẫn có thể giới hạn API capability. Nếu token chỉ có scope invoice:read, dữ liệu quyền hiện hành có invoice.approve không tự cho phép API thực hiện duyệt nếu hợp đồng yêu cầu scope tương ứng.

Ví dụ:

~~~text
JWT:
    aud = Billing API
    scope = invoice:read

Current authorization store:
    invoice.read
    invoice.approve

Request:
    invoice.approve

Decision:
    DENY because the access token was not granted the required API scope.
~~~

Nếu thiết kế không dùng scope làm giới hạn, phải mô tả rõ token chỉ xác thực danh tính và quyền API được xác định từ nguồn hiện hành. Không được để các API tự diễn giải khác nhau.

## 6. Nguồn sự thật và quyền sở hữu dữ liệu

Khi phối hợp nhiều nguồn, cần xác định ai là chủ sở hữu của từng loại dữ liệu. Một dịch vụ không nên tự suy ra hoặc ghi đè dữ liệu mà nó không có thẩm quyền.

| Dữ liệu | Nguồn có thẩm quyền thường gặp | Resource server cần làm gì? |
| --- | --- | --- |
| Danh tính subject và issuer | Identity Provider | Xác minh JWT và ánh xạ principal. |
| Trạng thái tài khoản | Identity/account service | Kiểm tra active/disabled nếu chính sách yêu cầu thu hồi nhanh. |
| Tenant membership | Membership service hoặc hệ thống quản trị tổ chức | Đọc membership hiện hành và tenant context. |
| Role assignment | Hệ thống quản trị quyền | Dùng role theo đúng tenant/domain và phiên bản. |
| Permission/ACL | Authorization store hoặc policy service | Đánh giá quyền hiện hành cho action. |
| Owner và resource state | Dịch vụ sở hữu dữ liệu | Tải object thực tế và kiểm tra thuộc tính. |
| Policy definition | Policy administration/source control có thẩm quyền | Dùng phiên bản policy được triển khai và hỗ trợ. |
| Risk/session state | Risk hoặc session service | Áp dụng theo yêu cầu của hành động. |

### 6.1. Một claim có thể có nhiều cách diễn giải

Claim roles có thể là:

- Role được cấp tại thời điểm phát hành token.
- Role toàn cục của user.
- Role trong một tenant.
- Role của client/service.
- Role chỉ có ý nghĩa trong một API.

Nếu hợp đồng không phân biệt, API có thể hiểu role administrator ở phạm vi toàn cục trong khi issuer chỉ định nghĩa nó trong tenant company-a.

Nên định nghĩa namespace, phạm vi và nguồn của role/permission. Khi nhiều issuer cùng phát hành token, không giả định cùng tên claim có cùng ngữ nghĩa.

### 6.2. Không dùng token làm nguồn sự thật cho dữ liệu tài nguyên

JWT có thể mang tenant_id hoặc resource_id như ngữ cảnh, nhưng owner, trạng thái, phân loại và quan hệ hiện tại phải được kiểm tra từ dịch vụ quản lý tài nguyên nếu chúng có thể thay đổi.

Ví dụ token có tenant_id = company-a không chứng minh hóa đơn INV-200 thuộc company-a. API cần tải hóa đơn và xác minh tenant thật.

## 7. Kiến trúc phối hợp: Policy Enforcement, Decision, Information và Administration

Một kiến trúc phân quyền có thể chia trách nhiệm thành các thành phần logic:

- **Policy Enforcement Point (PEP):** điểm thực thi kiểm tra và áp dụng quyết định trước khi cho request đi tiếp.
- **Policy Decision Point (PDP):** thành phần đánh giá chính sách và trả ALLOW/DENY hoặc kết quả có điều kiện.
- **Policy Information Point (PIP):** nguồn cung cấp thuộc tính và trạng thái như membership, owner, risk hoặc resource state.
- **Policy Administration Point (PAP):** nơi quản lý, phê duyệt và phát hành chính sách.

Các tên gọi này thường gặp trong mô hình kiểm soát truy cập theo chính sách, chẳng hạn kiến trúc ABAC. Chúng là vai trò logic; một hệ thống có thể triển khai chúng trong một dịch vụ hoặc nhiều thành phần.

~~~mermaid
flowchart LR
    R["API Request"] --> PEP["PEP: Enforcement"]
    PEP --> V["Xác minh JWT"]
    V --> PDP["PDP: Policy Decision"]
    PDP --> PIP["PIP: Current attributes"]
    PAP["PAP: Policy administration"] --> PDP
    PIP --> PDP
    PDP -->|ALLOW| PEP
    PDP -->|DENY| PEP
    PEP --> O["Thực thi hoặc từ chối"]
~~~

### 7.1. Trách nhiệm của PEP

PEP nằm trên đường request và bảo đảm:

- JWT được xác minh trước khi claims được dùng.
- Principal và action được xác định đúng.
- Request không thể bỏ qua bước authorization.
- Kết quả DENY không tạo side effect.
- Quyết định được áp dụng trước khi trả dữ liệu hoặc ghi thay đổi.

### 7.2. Trách nhiệm của PDP

PDP kết hợp:

- Claims đã xác minh từ token.
- Dữ liệu hiện hành từ PIP.
- Policy đang có hiệu lực từ PAP.
- Action, resource và context của request.

PDP cần trả quyết định rõ ràng, không để PEP tự đoán khi PDP trả lỗi hoặc thiếu dữ liệu.

### 7.3. Trách nhiệm của PIP

PIP cung cấp thuộc tính hiện hành, ví dụ:

~~~json
{
  "principal": {
    "id": "user-514",
    "account_status": "ACTIVE"
  },
  "membership": {
    "tenant_id": "company-a",
    "status": "ACTIVE",
    "roles": ["invoice_approver"],
    "authorization_version": 13
  },
  "resource": {
    "id": "INV-100",
    "tenant_id": "company-a",
    "state": "PENDING",
    "created_by": "user-999"
  }
}
~~~

Đây là dữ liệu minh họa đã lấy từ các nguồn hiện hành, không phải claims JWT. PDP cần biết nguồn nào có thẩm quyền cho từng thuộc tính và thời điểm dữ liệu được đọc.

### 7.4. Trách nhiệm của PAP

PAP quản lý policy và phiên bản:

- Ai được thay đổi chính sách?
- Thay đổi cần phê duyệt nào?
- Policy được triển khai đến PDP nào?
- Làm sao rollback nếu policy sai?
- API nào hỗ trợ phiên bản hiện tại?

Không để một client hoặc request runtime tự gửi policy rồi yêu cầu PDP áp dụng như một nguồn có thẩm quyền.

## 8. Quy tắc kết hợp claims và dữ liệu hiện hành

Một hợp đồng phân quyền nên định nghĩa rõ thứ tự và điều kiện.

### 8.1. Xác minh token trước

Trước khi đọc claims cho mục đích authorization, API phải xác minh:

- Chữ ký và thuật toán được cho phép.
- Issuer tin cậy.
- Audience dành cho API hiện tại.
- Thời gian exp, nbf và các điều kiện thời gian liên quan.
- Token đúng loại/profile.
- Claims bắt buộc đúng kiểu và schema.

Giải mã payload mà không xác minh chữ ký không tạo ra principal đáng tin.

### 8.2. Xác định principal và ngữ cảnh

Ánh xạ cặp (iss, sub) sang principal nội bộ. Xác định client/actor nếu request là service-to-service hoặc delegated. Tenant context phải theo hợp đồng và được đối chiếu với membership.

### 8.3. Đọc trạng thái hiện hành cần thiết

Không nhất thiết truy vấn mọi nguồn dữ liệu cho mọi request. Chỉ lấy các thuộc tính mà policy cần, nhưng phải có chủ sở hữu dữ liệu và yêu cầu freshness rõ:

- Tài khoản active?
- Membership còn hiệu lực?
- Permission hoặc role còn hiệu lực?
- Delegation/share có bị thu hồi?
- Resource có thuộc tenant và trạng thái hợp lệ?

### 8.4. Đánh giá theo action và resource

Không chỉ kiểm tra quyền chung của principal. PDP/PEP cần đánh giá action cụ thể trên object thực tế:

~~~text
Decision = Policy(
    verified_principal,
    token_constraints,
    current_authorization_state,
    action,
    resource,
    request_context
)
~~~

### 8.5. Áp dụng kết quả một cách nhất quán

Nếu quyết định là DENY, không trả dữ liệu và không tạo side effect. Nếu quyết định là ALLOW, thao tác vẫn cần tuân thủ các điều kiện về trạng thái, version và tính nhất quán ở thời điểm thực thi.

## 9. Mâu thuẫn giữa token và dữ liệu hiện hành

Mâu thuẫn là tình huống thường gặp và phải có quy tắc đã định nghĩa trước.

| Token | Dữ liệu hiện hành | Hành vi an toàn theo mô hình token-ceiling |
| --- | --- | --- |
| Role invoice_approver | Role đã bị gỡ | DENY; không tin role cũ. |
| Permission invoice.approve | Permission hiện hành không có | DENY. |
| Không có invoice.delete | Hiện tại có invoice.delete | Không mở rộng token cũ; yêu cầu cấp token mới nếu token permission là giới hạn. |
| Tenant company-a | Membership company-a đã revoked | DENY. |
| Account active tại lúc phát hành | Account hiện disabled | DENY. |
| Có scope invoice:read | Current permission không có invoice.read | DENY. |
| Có permission invoice.approve | Resource đã PAID | DENY theo resource policy. |
| authz_version = 12 | Current version = 13 | Từ chối token hoặc yêu cầu cấp lại theo hợp đồng. |

### 9.1. Token có nhiều quyền hơn trạng thái hiện tại

Đây là trường hợp cần ngăn quyền cũ tiếp tục được dùng. Nguồn hiện hành có thể thu hẹp quyền hoặc đánh dấu token không còn phù hợp.

### 9.2. Token có ít quyền hơn trạng thái hiện tại

Nếu token mang permission snapshot làm trần quyền, dữ liệu hiện hành không được tự mở rộng token. Client cần lấy token mới để nhận quyền mới đã được cấp.

Nếu token chỉ mang danh tính và quyền hoàn toàn do nguồn hiện hành quyết định, quyền mới có thể có hiệu lực ngay theo chính sách. Nhưng hợp đồng phải nói rõ token không phải nơi chứa giới hạn permission.

### 9.3. Nguồn dữ liệu mâu thuẫn với nhau

Ví dụ membership service báo ACTIVE nhưng authorization store báo membership đã revoked. Hệ thống phải xác định nguồn có thẩm quyền hoặc version mới hơn; không lấy giá trị thuận tiện hơn để cho phép.

Nếu không thể xác định trạng thái đúng, thao tác nhạy cảm nên bị từ chối hoặc tạm dừng cho đến khi có bằng chứng đáng tin cậy.

## 10. Versioning để phát hiện claims cũ

Một cách kết hợp token và dữ liệu hiện hành là đưa phiên bản quyền vào JWT, rồi so sánh với phiên bản hiện tại.

Token:

~~~json
{
  "sub": "user-514",
  "aud": "https://api.example.test/billing",
  "authz_version": 12,
  "exp": 1900003600
}
~~~

Nguồn quyền hiện hành:

~~~json
{
  "principal": "user-514",
  "tenant_id": "company-a",
  "authz_version": 13
}
~~~

Nếu hợp đồng yêu cầu version bằng nhau:

~~~text
token.authz_version != current.authz_version
    -> token snapshot không còn phù hợp
    -> từ chối hoặc yêu cầu cấp token mới
~~~

### 10.1. Phạm vi version

Version có thể được quản lý theo:

- User authorization version.
- Tenant membership version.
- Client/grant version.
- Session version.
- Resource ACL version.
- Policy version.

Không nhất thiết mọi hệ thống cần tất cả các version. Chọn phạm vi theo sự kiện nào phải làm token hoặc quyết định cũ mất hiệu lực.

### 10.2. Tăng version khi nào?

Hợp đồng cần liệt kê các thay đổi làm tăng version, ví dụ:

- Gỡ role hoặc permission.
- Thay đổi tenant membership.
- Khóa tài khoản.
- Thu hồi delegation.
- Thu hồi grant của client.
- Thay đổi chính sách làm thay đổi quyền đã tính.

Nếu một sự kiện bị bỏ sót, version có thể vẫn bằng nhau dù quyền thực tế đã đổi.

### 10.3. Version không thay thế resource policy

Authorization version bằng nhau không chứng minh user được truy cập mọi object. API vẫn phải kiểm tra owner, tenant, trạng thái, quan hệ và action cụ thể.

## 11. Cache dữ liệu phân quyền hiện hành

Truy vấn nguồn quyền ở mọi request có thể tốn chi phí. Cache giúp giảm tải, nhưng cũng có thể giữ lại quyền đã bị thu hồi.

### 11.1. Các loại dữ liệu có thể cache

- Membership theo principal và tenant.
- Role/permission assignment.
- Authorization version.
- Policy evaluation result.
- Resource relationship hoặc ACL.
- Trạng thái introspection/session.

Mỗi loại cache cần TTL, key, nguồn cập nhật và chính sách invalidation riêng.

### 11.2. Cache key phải chứa ngữ cảnh làm thay đổi quyết định

Ví dụ cache policy result:

~~~text
issuer
principal
tenant
action
resource_id
authorization_version
policy_version
relevant_context
~~~

Không cache kết quả ALLOW chỉ theo user ID nếu quyền còn phụ thuộc tenant, action hoặc resource. Quyết định cho user-514 đọc INV-100 không được dùng cho user-514 xóa INV-100 hoặc đọc INV-200.

### 11.3. TTL và cửa sổ stale authorization

Nếu cache permission có TTL 60 giây, quyền vừa bị thu hồi có thể vẫn được chấp nhận trong khoảng cache còn hiệu lực nếu invalidation chưa tới. Thời gian thực tế còn phụ thuộc replication, event delivery và cơ chế refresh.

Vì vậy, cần đặt SLO cho độ trễ cập nhật quyền:

~~~text
T0 = thời điểm thu hồi được commit
T1 = nguồn quyền cập nhật version
T2 = API nhận event hoặc đọc version mới
T3 = cache cũ bị vô hiệu
T4 = request tiếp theo bị từ chối

Revocation latency = T4 - T0
~~~

SLO phải được đo ở các API và vùng triển khai thực tế, không chỉ ở authorization service.

### 11.4. Cache âm và cache dương

- **Positive cache:** lưu kết quả ALLOW. Nếu stale, có thể cho phép quá lâu.
- **Negative cache:** lưu kết quả DENY. Nếu stale, có thể từ chối quyền mới được cấp.

Cả hai đều có ảnh hưởng tới tính đúng đắn. TTL có thể khác nhau theo rủi ro và loại dữ liệu. Không dùng một thời gian cache chung cho mọi quyết định.

### 11.5. Invalidation bằng sự kiện

Khi quyền đổi, nguồn quản trị có thể phát sự kiện:

~~~json
{
  "event_id": "evt-authorization-901",
  "event_type": "authorization.changed",
  "principal": "user-514",
  "tenant_id": "company-a",
  "authorization_version": 13,
  "occurred_at": "2030-03-17T09:10:00Z"
}
~~~

Đây là event nội bộ minh họa, không phải JWT claim hoặc định dạng chuẩn OAuth.

Consumer cần:

- Xác thực producer và tính toàn vẹn event.
- Xử lý idempotent khi event được gửi lại.
- Không áp dụng version cũ sau version mới.
- Có replay/recovery khi consumer mất kết nối.
- Có cơ chế đối chiếu snapshot nếu event bị bỏ lỡ.
- Đo thời gian event đến và cache được invalidated.

## 12. Freshness và consistency của dữ liệu quyền

Không phải mọi thuộc tính quyền đều cần mức nhất quán giống nhau.

| Dữ liệu | Ví dụ yêu cầu freshness | Lý do |
| --- | --- | --- |
| Trạng thái khóa tài khoản | Rất mới cho thao tác nhạy cảm | Người dùng bị khóa không nên tiếp tục thực hiện hành động quan trọng. |
| Tenant membership | Mới theo SLO thu hồi | Người đã rời tổ chức không nên tiếp tục truy cập dữ liệu tenant. |
| Permission phê duyệt giao dịch | Gần thời điểm thực thi | Thu hồi quyền có thể ảnh hưởng trực tiếp đến tài chính. |
| Quan hệ chia sẻ tài liệu | Theo độ nhạy dữ liệu | Share đã bị thu hồi không nên tồn tại quá lâu trong cache. |
| Nhãn phân loại tài liệu | Theo quy trình cập nhật dữ liệu | Policy có thể thay đổi khi resource được phân loại lại. |
| Role ít nhạy cảm cho nội dung công khai | Có thể chấp nhận cache dài hơn | Hậu quả của stale state thấp hơn. |

Các mức consistency có thể là:

- **Strong/linearizable read:** đọc trạng thái mới nhất theo bảo đảm của kho dữ liệu.
- **Read-after-write:** sau khi thay đổi được xác nhận, bên thực hiện có thể đọc thấy thay đổi.
- **Eventual consistency:** các bản sao cập nhật sau một khoảng thời gian.
- **Bounded staleness:** hệ thống chấp nhận dữ liệu cũ trong giới hạn được đo.

Chọn mức consistency dựa trên hậu quả của quyết định ALLOW sai. Không nên dùng eventual consistency không giới hạn cho quyền có yêu cầu thu hồi gần tức thì.

## 13. Fail-closed, fail-open và dữ liệu quyền không khả dụng

Khi nguồn hiện hành không truy cập được, API cần biết liệu nó có đủ bằng chứng để cho phép hay không.

### 13.1. Fail-closed

Không thực hiện hành động khi không thể xác minh điều kiện bắt buộc.

Phù hợp với:

- Duyệt giao dịch.
- Chuyển tiền hoặc hoàn tiền.
- Thay đổi quyền quản trị.
- Truy cập dữ liệu nhạy cảm.
- Thao tác phụ thuộc membership vừa có thể bị thu hồi.

Ưu điểm là giảm nguy cơ cấp quyền dựa trên trạng thái cũ. Giới hạn là có thể làm giảm availability khi dịch vụ quyền gặp sự cố.

### 13.2. Fail-open

Tiếp tục dùng dữ liệu cache hoặc token snapshot khi nguồn hiện hành không khả dụng.

Chỉ nên cân nhắc khi:

- Hành động có rủi ro thấp.
- Cache có giới hạn tuổi rõ ràng.
- Có thể chứng minh token và policy vẫn nằm trong thời hạn chấp nhận.
- Hệ thống có monitoring và cơ chế phục hồi.
- Chủ sở hữu nghiệp vụ chấp nhận rủi ro còn lại.

Không được biến lỗi timeout thành ALLOW mặc định.

### 13.3. Phân biệt DENY với INDETERMINATE

PDP có thể trả ba kết quả:

- **PERMIT/ALLOW:** đủ bằng chứng và policy cho phép.
- **DENY:** policy xác định request không được phép.
- **INDETERMINATE:** không thể đánh giá do thiếu dữ liệu, timeout, lỗi nguồn hoặc policy không khả dụng.

PEP phải có quy tắc rõ cho INDETERMINATE. Với thao tác nhạy cảm, thường từ chối hoặc trả lỗi tạm thời. Không được tự chuyển INDETERMINATE thành ALLOW.

## 14. Kiểm tra quyền tại thời điểm thực thi và tránh TOCTOU

Ngay cả khi API đọc quyền hiện hành ở đầu request, quyền hoặc resource state vẫn có thể thay đổi trước lúc thao tác được ghi.

Ví dụ:

1. 09:10:00.000, PDP xác nhận user còn invoice.approve.
2. 09:10:00.050, quản trị viên thu hồi permission.
3. 09:10:00.100, API ghi hóa đơn thành APPROVED dựa trên kết quả cũ.

Đây là lỗi **time-of-check to time-of-use (TOCTOU)**.

Với thao tác nhạy cảm:

- Kiểm tra quyền sát thời điểm ghi.
- Dùng transaction hoặc cơ chế đồng bộ phù hợp.
- Kiểm tra version của resource và authorization state nếu có.
- Dùng conditional update để chỉ ghi khi trạng thái còn hợp lệ.
- Nếu thao tác nhiều bước, xác định thời điểm phải đánh giá lại quyền.
- Ghi audit kết quả thực thi và dữ liệu quyết định.

Ví dụ điều kiện ghi:

~~~sql
UPDATE invoices
SET status = 'APPROVED',
    approved_by = :principal_id,
    version = version + 1
WHERE invoice_id = :invoice_id
  AND tenant_id = :authorized_tenant_id
  AND status = 'PENDING'
  AND version = :expected_resource_version;
~~~

Truy vấn minh họa kiểm tra tenant, trạng thái và resource version ở thời điểm ghi. Nó không tự thay thế kiểm tra permission của principal; hệ thống cần ràng buộc quyết định quyền với thao tác ghi theo mô hình consistency đã chọn.

## 15. Pseudocode: phối hợp JWT, quyền hiện hành và resource policy

Ví dụ sau dùng mô hình token-ceiling: scope và permission trong JWT giới hạn quyền tối đa của access token; membership, permission hiện hành và resource policy có thể thu hẹp thêm.

~~~text
function authorizeInvoice(request, action):
    verified = validateAccessToken(
        extractBearerToken(request.headers),
        trustedIssuer = "https://identity.example.test",
        expectedAudience = "https://api.example.test/billing",
        allowedAlgorithms = ["RS256"]
    )
    if verified.failed:
        return UNAUTHENTICATED

    claims = verified.claims
    if not matchesBillingTokenSchema(claims):
        return DENY_INVALID_TOKEN

    principal = resolvePrincipal(claims.iss, claims.sub)
    if principal is null:
        return DENY

    requiredScope = scopeFor(action)
    requiredPermission = permissionFor(action)
    if requiredScope not in parseExactScopes(claims.scope):
        return DENY
    if requiredPermission not in claims.permissions:
        return DENY

    current = authorizationStore.load(
        principal = principal,
        tenant = claims.tenant_id
    )
    if current.unavailable:
        return INDETERMINATE
    if not current.accountActive or not current.membershipActive:
        return DENY
    if claims.authz_version != current.authorizationVersion:
        return REQUIRE_NEW_TOKEN
    if requiredPermission not in current.permissions:
        return DENY

    invoice = invoiceStore.load(
        invoiceId = request.invoiceId,
        tenantId = claims.tenant_id
    )
    if invoice is null:
        return NOT_FOUND

    decision = policy.evaluate(
        principal = principal,
        action = action,
        resource = invoice,
        context = current
    )
    if decision != ALLOW:
        return DENY

    return ALLOW
~~~

Đây là pseudocode minh họa, không phải thư viện hoặc giao thức triển khai hoàn chỉnh. Hợp đồng phải xác định version mismatch trả lỗi nào, dữ liệu hiện hành được cache bao lâu, policy service lỗi được xử lý ra sao và thao tác ghi có cần đánh giá lại quyền trong transaction hay không.

Nếu hệ thống dùng JWT chỉ để xác thực, có thể bỏ bước kiểm tra permission snapshot và để nguồn hiện hành quyết định quyền. Khi đó không được giả vờ rằng token có một permission ceiling không tồn tại trong hợp đồng.

## 16. Audit: ghi lại dữ liệu nào tạo nên quyết định?

Khi phối hợp nhiều nguồn, audit nên đủ để trả lời vì sao request được ALLOW hoặc DENY.

Một bản ghi quyết định minh họa:

~~~json
{
  "decision_id": "dec-5501",
  "issuer": "https://identity.example.test",
  "subject": "user-514",
  "tenant_id": "company-a",
  "audience": "https://api.example.test/billing",
  "action": "invoice.approve",
  "resource_id": "INV-100",
  "token_authorization_version": 12,
  "current_authorization_version": 13,
  "policy_version": "billing-policy-7",
  "decision": "DENY",
  "reason": "AUTHORIZATION_VERSION_MISMATCH"
}
~~~

Đây là dữ liệu audit minh họa, không phải JWT. Không ghi nguyên bearer token hoặc refresh token. Chỉ ghi các claim và định danh cần thiết theo chính sách bảo vệ dữ liệu.

### 16.1. Những trường nên xem xét

- Issuer và subject đã được xác minh.
- Client hoặc actor nếu có delegation.
- Audience và loại token.
- Tenant context.
- Action và resource ID.
- Token version và current version.
- Policy version.
- Dữ liệu freshness hoặc source version cần thiết.
- Decision và reason code.
- Thời điểm và service/region thực hiện quyết định.

### 16.2. Không ghi quá mức

Audit không nên trở thành nơi lưu token hoặc dữ liệu cá nhân không cần thiết. Dùng định danh đã được kiểm soát, che thông tin nhạy cảm và giới hạn quyền truy cập log.

## 17. Những lỗi thường gặp

| Sai lầm | Rủi ro | Cách phòng tránh |
| --- | --- | --- |
| Coi role trong JWT là quyền hiện hành mãi mãi | Token cũ tiếp tục cấp quyền sau khi role bị gỡ. | Kiểm tra quyền hiện hành hoặc giới hạn tuổi snapshot. |
| Bỏ qua permission trong token khi dữ liệu hiện hành cấp thêm quyền | Quyền vượt quá grant ban đầu của token. | Xác định token-ceiling hoặc identity-only contract. |
| Lấy union của token và current permissions | Một nguồn có thể vô tình mở rộng quyền của nguồn còn lại. | Dùng quy tắc intersection khi cả hai là giới hạn; nếu quyền động là nguồn duy nhất, ghi rõ. |
| Dùng dữ liệu hiện hành nhưng không xác minh principal | Quyền của user khác có thể bị áp dụng nhầm. | Ánh xạ từ issuer và subject đã xác minh. |
| Không xác định source of truth | API khác nhau có kết quả ALLOW/DENY khác nhau. | Gán chủ sở hữu dữ liệu và ngữ nghĩa cho từng claim/attribute. |
| Cache ALLOW quá lâu | Quyền bị thu hồi nhưng API vẫn cho phép. | TTL, invalidation, version và SLO rõ ràng. |
| Cache theo user nhưng bỏ tenant/action/resource | Quyết định của một ngữ cảnh bị dùng cho ngữ cảnh khác. | Cache key chứa các thuộc tính làm thay đổi quyết định. |
| Không phân biệt DENY và INDETERMINATE | Timeout hoặc thiếu dữ liệu bị biến thành cho phép. | Định nghĩa kết quả PDP và xử lý lỗi tại PEP. |
| Tăng version không đầy đủ | Một số thay đổi quyền không làm token cũ mất hiệu lực. | Liệt kê mọi sự kiện làm tăng version. |
| Đọc current permission nhưng không kiểm tra resource | User có quyền chung vẫn truy cập object ngoài phạm vi. | Kết hợp resource policy và object-level authorization. |
| Kiểm tra quyền quá sớm rồi mới ghi | TOCTOU khi quyền hoặc trạng thái thay đổi. | Kiểm tra sát thời điểm thực thi và dùng conditional write. |
| Không audit phiên bản dữ liệu/policy | Khó giải thích vì sao request được cho phép. | Ghi version và reason code cần thiết. |

## 18. Kịch bản kiểm thử phối hợp token và dữ liệu hiện hành

Kiểm thử phải bao gồm trường hợp token và nguồn hiện hành nhất quán, mâu thuẫn, lỗi hoặc bị stale.

### 18.1. Kiểm thử token-ceiling

~~~text
Token có invoice.read
Current có invoice.read
    -> tiếp tục đánh giá resource policy

Token có invoice.approve
Current đã thu hồi invoice.approve
    -> DENY

Token không có invoice.delete
Current vừa cấp invoice.delete
    -> không tự mở rộng token cũ; yêu cầu token mới

Token có invoice.read
Current có invoice.read và invoice.delete
    -> chỉ invoice.read nằm trong token ceiling
~~~

### 18.2. Kiểm thử identity-only token

~~~text
JWT chỉ xác thực danh tính
Current permissions có invoice.read
    -> ALLOW nếu resource policy cũng cho phép

JWT chỉ xác thực danh tính
Current permissions không có invoice.approve
    -> DENY

JWT hợp lệ nhưng account hiện disabled
    -> DENY theo chính sách trạng thái hiện hành
~~~

### 18.3. Kiểm thử version và cache

- Token version bằng current version.
- Token version thấp hơn current version.
- Event version đến sai thứ tự.
- Cache chứa version cũ sau khi event được phát.
- Một region mất kết nối và bỏ lỡ event.
- Cache positive và negative có TTL khác nhau.
- Resource ACL thay đổi nhưng policy result cache chưa invalidated.

### 18.4. Kiểm thử dữ liệu thiếu và lỗi

- Membership service timeout.
- Authorization store trả dữ liệu không đầy đủ.
- Policy version không được API hỗ trợ.
- Claims bắt buộc sai kiểu hoặc thiếu.
- Hai nguồn dữ liệu đưa ra trạng thái mâu thuẫn.
- PDP trả INDETERMINATE.

Xác minh API không tự chuyển các trường hợp thiếu bằng chứng thành ALLOW.

### 18.5. Kiểm thử TOCTOU và audit

- Permission bị thu hồi giữa lúc kiểm tra và ghi.
- Resource chuyển trạng thái trước khi cập nhật.
- Owner hoặc tenant thay đổi khi request đang xử lý.
- Audit ghi đúng token version, current version và policy version.
- Request DENY không tạo side effect.

## 19. Checklist thiết kế

Trước khi phối hợp JWT với dữ liệu quyền hiện hành, hãy trả lời:

1. **Token semantics:** token chỉ xác thực danh tính hay còn mang scope/permission làm giới hạn quyền?
2. **Claim contract:** roles, permissions, tenant và version có kiểu, phạm vi và issuer rõ ràng không?
3. **Source of truth:** nguồn nào có thẩm quyền cho account, membership, role, permission, resource và policy?
4. **Combination rule:** token và dữ liệu hiện hành dùng intersection, identity-only lookup hay quy tắc khác?
5. **Conflict:** token rộng hơn hoặc hẹp hơn trạng thái hiện tại thì xử lý thế nào?
6. **Freshness:** dữ liệu nào cần đọc trực tiếp; dữ liệu nào được cache và tối đa cũ bao lâu?
7. **Versioning:** sự kiện nào làm tăng authorization/session/tenant/policy version?
8. **Architecture:** PEP, PDP, PIP và PAP nằm ở đâu; thành phần nào chịu trách nhiệm quyết định?
9. **Failure:** DENY và INDETERMINATE được xử lý ra sao khi dịch vụ quyền lỗi?
10. **Resource policy:** owner, tenant, relationship và trạng thái object có được kiểm tra không?
11. **Consistency:** quyết định quyền có nhất quán với thời điểm thao tác ghi không?
12. **Audit:** có thể tái dựng quyết định từ các version và reason code mà không lưu token không?
13. **Testing:** có test stale claims, quyền mới, quyền thu hồi, cache, event ordering, lỗi nguồn và TOCTOU không?

## 20. Ghi nhớ trọng tâm

- Claims trong JWT là dữ liệu đã ký tại thời điểm phát hành; chúng không tự cập nhật theo trạng thái quyền hiện hành.
- Nguồn dữ liệu hiện hành phải được gắn với principal từ token đã xác minh, không được tra quyền theo ID client tự gửi.
- Nếu token mang permission làm giới hạn, một mô hình bảo thủ là lấy giao giữa quyền trong token và quyền hiện hành; dữ liệu hiện hành không tự mở rộng token cũ.
- Nếu token chỉ mang danh tính, nguồn hiện hành có thể là nơi quyết định quyền, nhưng hợp đồng phải nói rõ.
- Cần xác định source of truth cho account, membership, role, permission, resource và policy.
- Version, cache và event invalidation giúp phát hiện trạng thái cũ nhưng phải có SLO freshness và cơ chế recovery.
- Khi không đủ dữ liệu để quyết định, phân biệt DENY với INDETERMINATE; không mặc định cho phép.
- Kiểm tra quyền phải gắn với action và resource, đồng thời đủ nhất quán với thời điểm thực thi.
- Audit nên ghi nguồn, version và lý do quyết định; không lưu bearer token.

**Tài liệu tham khảo kỹ thuật:** RFC 7519 (JSON Web Token); RFC 8725 (JWT Best Current Practices); NIST SP 800-162 (Guide to Attribute Based Access Control); NIST SP 800-207 (Zero Trust Architecture); NIST SP 800-53 (Security and Privacy Controls, các nhóm access control và audit). Các tài liệu này cung cấp nền tảng về token, thuộc tính và kiến trúc kiểm soát truy cập; quy tắc phối hợp claims và nguồn quyền hiện hành phải được từng ứng dụng định nghĩa thành hợp đồng có thể kiểm thử.
