# Xác minh deprovisioning trong vòng đời danh tính IAM

**Xác minh deprovisioning (deprovisioning verification)** là quá trình thu thập và đánh giá bằng chứng rằng tài khoản, quyền truy cập, phiên làm việc và credential cần thu hồi đã **thực sự mất hiệu lực tại những hệ thống đích liên quan**. Quá trình này diễn ra sau hoặc song song với các lệnh disable, remove group, revoke token, thu hồi chứng chỉ và đóng tài khoản. Mục tiêu là trả lời một câu hỏi cụ thể: **sau thời điểm phải thu hồi, chủ thể còn đường nào để thực hiện hành động đã bị cấm không?**

Bài thuộc chương **Account deprovisioning** của module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Trong quản lý vòng đời danh tính **Joiner–Mover–Leaver (JML)**, Joiner phải được cấp quyền đúng lúc, Mover cần gỡ quyền không còn hợp lệ khi chuyển vai trò và Leaver cần chấm dứt các đường truy cập theo chính sách. Việc xác minh liên kết nguồn danh tính/HRIS, **IdP**, **SSO**, **SCIM**, **RBAC/ABAC**, tài khoản dịch vụ, kiểm toán và mục tiêu giảm **quyền truy cập tồn dư**.

**Tình huống dẫn nhập:** An nghỉ việc lúc 17:00. Hệ thống IAM đã gửi lệnh khóa tài khoản IdP và ứng dụng SaaS trả HTTP 200 cho yêu cầu cập nhật. Tuy nhiên, An có thể còn một phiên ứng dụng đã đăng nhập từ buổi sáng, quyền xem tài liệu được chia sẻ trực tiếp, API key tạo trước đó và một tài khoản cục bộ không liên kết SSO. Báo cáo “đã gửi lệnh khóa” không chứng minh tất cả các đường này đã ngừng hoạt động. Cần xác minh kết quả ở từng điểm thực thi quyền.

## 1. Phân biệt thực thi và xác minh deprovisioning

| Trạng thái hoặc hành động | Khẳng định có thể rút ra | Điều chưa thể kết luận |
| --- | --- | --- |
| HRIS phát sự kiện Leaver/Mover | Nguồn nhân sự thông báo thay đổi có hiệu lực. | IdP hoặc SaaS đã thực sự gỡ quyền. |
| IAM đưa lệnh vào hàng đợi | Có công việc thu hồi được lập và chờ xử lý. | Connector đã liên hệ được hệ thống đích. |
| Connector nhận HTTP 200/204 | Endpoint đã phản hồi thành công theo hợp đồng API. | Mọi quyền hiệu lực, phiên và token đều không còn. |
| IdP đánh dấu account disabled | IdP áp trạng thái tài khoản mới theo chính sách. | Tất cả phiên SSO và phiên cục bộ SaaS đã kết thúc. |
| SCIM User được đặt active=false | Thuộc tính của user ở hệ thống đích đã thay đổi nếu readback xác nhận. | Ứng dụng chắc chắn chặn mọi API key, phiên hoặc tài khoản khác. |
| Nhóm/role đã bị gỡ | Một nguồn cấp quyền đã được loại bỏ. | Không còn direct grant, ACL, nhóm lồng hoặc quyền kế thừa. |
| Kiểm thử truy cập bị từ chối | Một đường truy cập/loại hành động cụ thể không còn được phép tại thời điểm thử. | Mọi đường truy cập khác cũng đã bị thu hồi. |
| Đối soát toàn bộ phạm vi bắt buộc đạt | Các điều kiện đã định nghĩa đều có bằng chứng phù hợp. | Dữ liệu đã sao chép offline trước đó tự biến mất. |

Một quy trình tốt tách rõ **requested**, **applied**, **verified** và **closed**. Việc đọc lại một cờ cấu hình và việc thử quyền truy cập có kiểm soát là những bằng chứng bổ trợ, không hoàn toàn thay thế cho nhau.

### Vì sao đây là vấn đề bảo mật quan trọng?

- **Quyền tồn dư (residual access):** người rời tổ chức hoặc chuyển bộ phận vẫn truy cập được dữ liệu cũ.
- **Privilege creep:** quyền bị tích lũy qua nhiều lần Mover vì quy trình chỉ cấp thêm mà không chứng minh quyền cũ đã mất.
- **Rủi ro kiểm toán:** hệ thống có báo cáo “đã hoàn tất” nhưng không có chứng cứ cho từng ứng dụng và entitlement.
- **Khoảng trống do eventual consistency:** lệnh thành công ở nguồn nhưng ứng dụng đích đồng bộ chậm hoặc lỗi.
- **Đường truy cập độc lập:** tài khoản cục bộ, personal access token, SSH key, API key và secret không chịu điều khiển trực tiếp của IdP.

**Định nghĩa hoàn tất cần theo phạm vi:** một tổ chức có thể chấp nhận các mức độ trễ khác nhau cho quyền đọc tài liệu chung và quyền duyệt thanh toán. Nhưng mỗi mức phải có **mốc hiệu lực, SLA, bằng chứng và cách xử lý vi phạm rõ ràng**.

## 2. Xác định đối tượng phải kiểm chứng

Trước khi thực thi kiểm tra, IAM cần lập **inventory các đường truy cập** của chủ thể và nguồn cấp quyền. Không thể xác minh một hệ thống chưa biết tồn tại hoặc một entitlement không được ghi nhận.

| Lớp cần kiểm chứng | Ví dụ | Bằng chứng có ý nghĩa |
| --- | --- | --- |
| **Nguồn danh tính** | HRIS, hồ sơ nhà thầu, sponsor. | Trạng thái hiện hành, thời điểm hiệu lực, event ID/revision đáng tin. |
| **Tài khoản đăng nhập tập trung** | IdP, AD/LDAP, directory. | Account bị disable theo chính sách; nhóm/role bị gỡ; trạng thái thực tế được đọc lại. |
| **SSO và phiên ứng dụng** | Session của IdP, session cookie của SaaS, SAML/OIDC login. | Phiên cũ đã bị chặn hoặc API không còn cho phép hành động sau mốc quy định. |
| **Access token và refresh token** | OAuth access token, refresh token, personal access token. | Thu hồi hoặc hết hạn theo cơ chế thực tế; resource server không nhận quyền cũ. |
| **SCIM/connector** | SaaS User, Group, membership, trạng thái active. | User/Group được đọc lại từ hệ thống đích; mapping đúng người. |
| **RBAC và ABAC** | Role, scope, department, tenant, project, classification. | Effective access tại tài nguyên và thuộc tính chính sách hiện hành. |
| **Quyền trực tiếp/kế thừa** | ACL folder, nhóm lồng, phân quyền theo owner, delegated approval. | Không còn đường grant trái chính sách tại điểm thực thi. |
| **Cloud và hệ thống kỹ thuật** | Cloud IAM, database role, VPN, SSH key, repository, CI/CD. | Principal/credential/quyền tương ứng đã bị thu hồi theo chính sách. |
| **Tài khoản dịch vụ và secret** | Quyền đọc vault, sửa trust policy, quản lý service account. | Người cũ không còn kiểm soát workload; secret có thể đã biết được đánh giá rotation. |
| **Thiết bị và dữ liệu offline** | Laptop công ty, hồ sơ đồng bộ, chứng chỉ thiết bị, file đã tải. | Thu hồi quyền truy cập và quy trình xử lý thiết bị/dữ liệu được xác nhận trong khả năng kỹ thuật. |

**Phạm vi phải có owner:** ai chịu trách nhiệm kiểm chứng ở hệ thống nào; hệ thống không có connector sẽ cần bằng chứng thủ công hoặc biện pháp bù trừ được phê duyệt. Không đánh dấu “không có lỗi” khi thực tế chưa thể đọc trạng thái.

### Không đồng nhất user identity với mọi tài khoản liên quan

Một nhân viên có thể sở hữu user account ở IdP, local account trong ứng dụng cũ, privileged account tách biệt, API key dùng cho script, tài khoản thử nghiệm và quyền quản trị service principal. Các định danh này phải được nối với **subject ID ổn định** và mapping hợp lệ. Email hoặc họ tên có thể đổi, trùng hoặc được tái sử dụng; không dùng chúng làm căn cứ duy nhất để xóa hay thu hồi.

## 3. Mục tiêu xác minh của Joiner, Mover và Leaver

| Sự kiện | Trạng thái mong muốn | Điều cần xác minh |
| --- | --- | --- |
| **Joiner chưa đến ngày hiệu lực** | Account có thể được chuẩn bị nhưng chưa có quyền nghiệp vụ không hợp lệ. | Pre-provisioned account không thể tự truy cập dữ liệu trước ngày hiệu lực. |
| **Mover sang vai trò mới** | Giữ quyền chung cần thiết, gỡ quyền vai trò cũ, chỉ cấp quyền mới đã duyệt. | Mọi nguồn grant cũ ngoài desired state đều mất hiệu lực; không có cửa sổ xung đột SoD. |
| **Leaver** | Chặn đăng nhập và các đường truy cập; deprovision account/entitlement theo chính sách. | Session, token, API key, local account và ACL không còn cấp quyền; hoàn tất thu hồi ở các đích bắt buộc. |
| **Hủy tuyển dụng** | Thu hồi mọi tài khoản và bootstrap credential đã chuẩn bị. | Không còn account pre-hire active, invitation hoặc temporary credential có thể sử dụng. |
| **Hết hợp đồng nhà thầu** | Thu hồi quyền theo ngày hết hạn và phạm vi sponsor. | Quyền dự án, chia sẻ, VPN và tài khoản SaaS không còn sau thời điểm hợp lệ. |
| **Ngừng workload** | Tắt danh tính kỹ thuật và credential của workload không còn cần. | Mọi role, trust, certificate, API key và job sử dụng identity đã được xử lý. |

Ở Mover, không nên xóa mọi quyền vì một số quyền cơ bản vẫn hợp lệ. Ở Leaver, không nên giữ account đăng nhập chỉ để giữ dữ liệu nghiệp vụ: có thể bàn giao ownership, lưu trữ tài liệu theo retention và **khóa quyền truy cập của người rời đi**.

## 4. Quy trình xác minh từ sự kiện đến kết luận

~~~mermaid
flowchart TD
    A["HRIS / nguồn có thẩm quyền: Mover hoặc Leaver"] --> B["Xác minh event, subject, effectiveAt, revision"]
    B --> C["Tính desired state và inventory đường truy cập"]
    C --> D["Phát lệnh thu hồi tại từng target"]
    D --> E["Đọc lại trạng thái account, nhóm, role, credential"]
    E --> F["Kiểm chứng effective access / session theo rủi ro"]
    F --> G{"Các điều kiện bắt buộc đạt?"}
    G -->|Đạt| H["Lưu evidence và đóng VERIFIED"]
    G -->|Sai lệch| I["Retry / escalation / kiểm soát bù trừ"]
    G -->|Không quan sát được| J["BLOCKED: thiếu khả năng xác minh"]
    I --> E
    J --> K["Owner xử lý, khắc phục và xác minh lại"]
    K --> E
~~~

Quy trình gồm chín bước chính:

1. **Xác minh sự kiện:** chỉ nhận thay đổi từ HRIS, sponsor hoặc nguồn được ủy quyền; đọc mốc hiệu lực, revision, loại chủ thể, phê duyệt và lý do.
2. **Xác định subject và đích:** lấy canonical subject ID; đối chiếu mapping của từng application account, quyền trực tiếp, nhóm lồng, vault, thiết bị và privileged identity.
3. **Tính desired access:** dựa trên trạng thái quan hệ hiện hành và RBAC/ABAC, xác định quyền nào phải gỡ và quyền nào được giữ theo ngoại lệ có hạn.
4. **Lập verification plan:** mỗi target/action có deadline, mức rủi ro, loại bằng chứng, người chịu trách nhiệm và tiêu chí PASS.
5. **Thực thi revoke/deactivate:** gọi IdP, SCIM, API đích, PAM, vault, CA hoặc ticket thủ công tùy loại tài nguyên.
6. **Đọc lại cấu hình:** kiểm tra trạng thái tài khoản/nhóm/ACL/certificate và mapping ở target. Không lấy kết quả từ request ban đầu làm bằng chứng duy nhất.
7. **Kiểm tra hiệu lực truy cập:** với các đường quan trọng, chứng minh phiên cũ hoặc quyền cũ không còn cho thực hiện hành động; thử trong phạm vi được phép và an toàn.
8. **Đối soát sai lệch:** phân biệt quyền còn hoạt động, trạng thái chưa đồng bộ, lỗi connector, nguồn cấp quyền khác và trường hợp không thể xác minh.
9. **Đóng hồ sơ dựa trên bằng chứng:** chỉ chốt khi các điều kiện bắt buộc đạt hoặc ngoại lệ chưa thể xử lý được phê duyệt và ghi trạng thái riêng theo chính sách.

**Nguyên tắc:** một tác vụ trả “success” là kết quả thực thi kỹ thuật; **VERIFIED** là kết quả kiểm chứng trạng thái và quyền theo hợp đồng riêng.

## 5. Trạng thái deprovisioning và điều kiện chuyển

~~~mermaid
flowchart LR
    P["PENDING"] --> R["REVOKE_IN_PROGRESS"]
    R --> A["APPLIED"]
    A --> V["VERIFICATION_IN_PROGRESS"]
    V --> D["VERIFIED"]
    R --> E["RETRYABLE_FAILURE"]
    E --> R
    V --> E
    V --> B["BLOCKED / EXCEPTION"]
    B --> V
    D --> C["CLOSED"]
~~~

| Trạng thái | Ý nghĩa | Không được làm |
| --- | --- | --- |
| **PENDING** | Đã ghi nhận sự kiện và kế hoạch, chưa thực thi. | Báo quyền đã thu hồi. |
| **REVOKE_IN_PROGRESS** | Đang xử lý các yêu cầu tại một hoặc nhiều đích. | Đồng nhất trạng thái chung với một target thành công. |
| **APPLIED** | Hệ thống đích đã nhận/xử lý lệnh theo API. | Bỏ qua readback hoặc phiên cũ. |
| **VERIFICATION_IN_PROGRESS** | Đang kiểm tra trạng thái và hiệu lực truy cập. | Đóng hồ sơ khi còn bằng chứng thiếu. |
| **VERIFIED** | Toàn bộ tiêu chí kiểm chứng bắt buộc đã đạt. | Tự giả định cả phạm vi ngoài inventory đã được xử lý. |
| **RETRYABLE_FAILURE** | Lỗi tạm: timeout, rate-limit, dịch vụ không sẵn sàng. | Retry mù theo cách có thể tạo lại quyền hoặc xóa nhầm. |
| **BLOCKED** | Thiếu mapping, không đủ quyền connector, sai lệch không thể tự giải quyết, hoặc không quan sát được. | Chuyển thành thành công chỉ vì đã mở ticket. |
| **EXCEPTION_APPROVED** | Sai lệch/độ trễ có căn cứ, hạn và kiểm soát bù trừ. | Coi ngoại lệ tương đương quyền đã thu hồi thực tế. |
| **CLOSED** | Hồ sơ đã hoàn tất theo chính sách đóng và evidence được lưu. | Xóa mất bằng chứng hoặc che dấu exception còn mở. |

Một hệ thống có thể chọn các tên state khác; điều bắt buộc là trạng thái phải phân biệt được **gửi lệnh, kết quả xác minh, lỗi chưa giải quyết và ngoại lệ chấp nhận có điều kiện**. Ngoại lệ còn hiệu lực phải có owner và thời điểm xem xét lại; không nên báo tổng thể “hoàn toàn thu hồi” nếu còn đường truy cập được cho phép tạm.

## 6. Hai nhóm bằng chứng: cấu hình và khả năng truy cập

### 6.1. Configuration readback

Đây là việc **đọc lại trạng thái thực** từ hệ thống đích:

- IdP trả account disabled và nhóm/role đã gỡ.
- SCIM User đã chuyển active=false hoặc nhóm không còn member.
- Vault không còn ACL cho người dùng; PAT/SSH key được revoke.
- Database không còn grant hoặc role không phù hợp.
- Gateway/PKI xác nhận chứng chỉ hoặc credential bị chặn.
- Ứng dụng ghi quyền đã hết hạn hoặc tài khoản cục bộ bị disable.

**Readback phải đủ mới** và gắn với đúng account ID. Dữ liệu đọc từ cache cũ hoặc từ bảng nội bộ của IAM không thể chứng minh hệ thống đích đã áp dụng nếu chúng chưa được đồng bộ.

### 6.2. Effective-access verification

Đây là kiểm tra rằng **quyết định truy cập** ở điểm thực thi đã thay đổi đúng:

- Yêu cầu đăng nhập mới của chủ thể đã Leaver bị từ chối.
- Request từ **phiên ứng dụng cũ** không còn thực hiện được hành động bảo vệ.
- Access token cũ, nếu còn hiệu lực mật mã, không thể dùng để thực thi quyền đã bị thu hồi theo mức bảo đảm/SLA yêu cầu.
- Tài khoản Mover không còn đọc hoặc xuất dữ liệu thuộc phạm vi vai trò cũ.
- Đường API trực tiếp không bypass kiểm tra chỉ vì menu UI đã ẩn.

Kiểm thử phải được **ủy quyền và không phá hoại**: sử dụng môi trường kiểm thử, tài nguyên giả lập, probe chỉ đọc hoặc công cụ kiểm tra quyền của nền tảng. Không sử dụng dữ liệu khách hàng thật hoặc tài khoản người nghỉ việc để thử các hành động có thể tạo giao dịch. Khi không thể thử trực tiếp, ghi rõ giới hạn và bổ sung evidence đáng tin khác; không đánh dấu PASS “theo suy đoán”.

### 6.3. Negative test và positive control

Một negative test chỉ có ý nghĩa nếu biết phương thức kiểm thử hoạt động. Ví dụ request tới API trả 404 vì sai đường dẫn chưa chứng minh role đã bị gỡ. Có thể dùng **positive control** trên principal thử nghiệm được phép để xác nhận endpoint vẫn hoạt động, sau đó dùng credential/đối tượng kiểm thử đã bị thu hồi để xác nhận bị từ chối theo đúng nguyên nhân. Kết quả phải được diễn giải theo mã lỗi, policy decision và log tương quan, tránh nhầm lỗi mạng với từ chối quyền.

## 7. Xác minh deprovisioning qua SCIM

SCIM 2.0 thường đồng bộ người dùng và nhóm giữa IAM và ứng dụng SaaS. Với Leaver, một connector có thể đặt thuộc tính **active=false**, cập nhật group hoặc gọi thao tác khác theo khả năng hệ thống đích.

Ví dụ request minh họa:

~~~http
PATCH /scim/v2/Users/4dc0b44f-8ad3-42d0-aa7f-c3796c67c801 HTTP/1.1
Host: saas.example.org
Authorization: Bearer <connector-token-placeholder>
Content-Type: application/scim+json

{
  "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
  "Operations": [
    {
      "op": "replace",
      "path": "active",
      "value": false
    }
  ]
}
~~~

Đây là **ví dụ yêu cầu**, không phải bằng chứng thành công. Phải kiểm tra target ID lấy từ mapping đáng tin, phản hồi API và **đọc lại** đúng tài nguyên User sau khi cập nhật.

~~~http
GET /scim/v2/Users/4dc0b44f-8ad3-42d0-aa7f-c3796c67c801 HTTP/1.1
Host: saas.example.org
Authorization: Bearer <connector-token-placeholder>
Accept: application/scim+json
~~~

Điều cần đánh giá:

1. **Đúng user đích:** không dựa vào email có thể bị đổi hoặc tái sử dụng; đối chiếu ID và liên kết với canonical subject.
2. **Thuộc tính active:** phản hồi thể hiện trạng thái đúng, trong thời gian cho phép.
3. **Group/role:** membership và quyền trực tiếp có còn hay không; active=false không luôn tự xóa group.
4. **Local login/session/token:** ứng dụng có chặn đường đăng nhập cục bộ và phiên cũ không; hành vi phụ thuộc sản phẩm.
5. **Phản hồi đồng bộ:** khi SaaS có xử lý bất đồng bộ, cần kiểm chứng sau khi quá trình áp dụng hoàn tất.
6. **Nguồn cấp ngoài SCIM:** API key, vai trò do admin cấp trực tiếp hoặc local account có thể không thuộc phạm vi SCIM.

**SCIM không phải giao thức quản lý phiên đăng nhập.** Một SCIM PATCH trả HTTP 204 có thể cho biết thay đổi đã được chấp nhận theo hợp đồng server, nhưng không đủ để khẳng định **mọi** phiên SSO, session cục bộ, API key hoặc đường chia sẻ tài nguyên đã bị thu hồi.

## 8. IdP, SSO, access token và refresh token

Khóa tài khoản IdP thường giúp ngăn **đăng nhập mới**, nhưng không phải tất cả phiên hiện tại đều lập tức mất hiệu lực.

| Thành phần | Tình huống tồn dư | Cách xử lý và xác minh |
| --- | --- | --- |
| **IdP session** | Người dùng đã có session SSO trước khi nghỉ việc. | Revoke/invalidate phiên theo khả năng IdP; thử yêu cầu đăng nhập mới và kiểm tra log. |
| **SaaS local session** | Ứng dụng tạo cookie riêng, không kiểm tra IdP sau login. | Gọi logout/session termination API nếu có; thử hành động từ phiên cũ có kiểm soát. |
| **OAuth refresh token** | Client còn khả năng lấy access token mới. | Revoke refresh token/grant theo provider; thử refresh bị từ chối. |
| **JWT access token tự chứa** | Token đã ký vẫn hợp lệ đến khi hết hạn nếu resource server chỉ kiểm chữ ký/thời hạn. | Token TTL phù hợp; trạng thái/authorization version, denylist, introspection hoặc kiểm tra quyền hiện hành khi cần thu hồi nhanh. |
| **Opaque access token** | Token vẫn được resource server chấp nhận khi hệ thống introspection chưa cập nhật. | Thu hồi theo token service và xác nhận resource server kiểm trạng thái mới. |
| **Personal access token/API key** | Credential ngoài phiên SSO, tồn tại độc lập. | Revoke từng key/grant ở ứng dụng đích; xác minh thử token bị từ chối hoặc metadata revoked. |
| **SAML assertion** | Assertion đã được dùng để tạo local session. | Không thể coi “assertion hết hạn” là bằng chứng local session đã chấm dứt. |

**OIDC và SAML** giúp trao đổi kết quả xác thực trong SSO; **OAuth 2.0** thường cấp token truy cập tới API. Các cơ chế logout như front-channel/back-channel hoặc session management có thể hỗ trợ, nhưng cần kiểm tra **ứng dụng đã triển khai và xử lý thực sự**. Không hứa “logout ngay trên mọi ứng dụng” khi chưa có đường kiểm chứng.

### Lưu ý về JWT

Một JWT còn hạn có chữ ký hợp lệ **không thể bị làm mất chữ ký từ xa**. Nếu API chỉ kiểm issuer, audience, chữ ký và hạn dùng mà không kiểm trạng thái quyền hiện hành, token chứa role cũ có thể còn sử dụng tới khi hết hạn. Vì vậy với tài nguyên nhạy cảm, cần có thiết kế thu hồi bổ sung, ví dụ:

- Kiểm tra account/entitlement hiện hành trên backend ở những hành động nhạy cảm.
- Dùng token thời hạn ngắn cùng refresh token có thể thu hồi.
- Dùng token introspection hoặc chính sách chặn theo token/session ID khi phù hợp.
- Áp phiên bản chính sách/quyền và từ chối token mang version cũ theo thiết kế.
- Đo **cửa sổ tồn dư tối đa** và kiểm thử ở gateway/resource server.

**Không lưu access token, refresh token thật trong bằng chứng kiểm toán**. Có thể dùng ID, metadata không nhạy cảm và log đã được bảo vệ để chứng minh trạng thái.

## 9. RBAC, ABAC, ACL và quyền cấp qua nhiều đường

Một quyền có thể được cấp từ nhiều nguồn. Vì vậy chỉ thu hồi **một nguồn** chưa chắc làm biến mất **effective permission**.

Ví dụ một nhân viên có quyền đọc báo cáo Sales qua:

1. Membership nhóm **Sales-Reader** tại IdP.
2. Role trực tiếp **Sales-Export** tại ứng dụng.
3. ACL chia sẻ tài liệu do trưởng nhóm tạo.
4. Thuộc tính **department=Sales** được dùng bởi chính sách ABAC.
5. Session đã lưu vai trò cũ trong cache.

Khi Mover sang Finance, phải kiểm tra từng đường không còn hợp lệ, đồng thời giữ quyền nhân viên cơ bản.

~~~text
actual_effective_access = union(
    idp_inherited_roles,
    nested_groups,
    application_direct_grants,
    object_acl_or_relationships,
    abac_decisions,
    active_session_or_token_permissions
)

revocation_verified =
    no_unapproved_path_remains_for(target_action, target_resource)
~~~

Hai công thức là **mô hình khái niệm**. Trong hệ thống thực, deny/allow precedence, chính sách kế thừa, condition và nguồn quyết định có thể phức tạp hơn phép hợp đơn giản. Cần đánh giá ở **Policy Enforcement Point** của backend hoặc resource server.

**Không kiểm chứng bằng cách chỉ ẩn menu.** Một API có thể cho phép truy cập nếu backend không kiểm tra tenant, quyền trên đối tượng cụ thể và trạng thái chính sách. Trường hợp này liên quan đến **Broken Object Level Authorization (BOLA/IDOR)**.

### Separation of Duties (SoD)

Khi nhân viên chuyển từ vị trí tạo yêu cầu sang vị trí phê duyệt, quyền cũ phải được gỡ trước khi quyền mới được mở nếu hai vai trò xung đột. Bằng chứng cần gồm thời điểm thu hồi quyền cũ, thời điểm cấp quyền mới, kết quả policy và các cửa sổ chồng lấn đã xử lý.

Một ngoại lệ bàn giao phải có **phạm vi tài nguyên, hành động, người phê duyệt, hạn dùng và cơ chế tự thu hồi**, đồng thời được đánh dấu riêng. Không ghi nhận “thu hồi hoàn toàn” khi ngoại lệ vẫn cho chủ thể thực hiện một phần hành động cũ.

## 10. Tài khoản dịch vụ, secret và quyền gián tiếp

Quyền truy cập tồn dư có thể đến từ một **service account** hoặc workload mà người chuyển vai trò/nghỉ việc từng quản trị. Ví dụ một kỹ sư có thể:

- Đọc client secret hoặc private key từ vault.
- Sửa pipeline CI/CD để dùng credential production.
- Thay trust policy của service principal.
- Cấp quyền vào Kubernetes namespace, cloud role hoặc repository có quyền deploy.
- Dùng token đã sao chép trước đó dù quyền đọc vault vừa bị gỡ.

Khi Leaver/Mover, cần xác minh:

1. Quyền **quản trị** danh tính dịch vụ của người cũ đã bị thu hồi.
2. Quyền **đọc/sửa secret** ở vault và repository đã được gỡ.
3. Credential dài hạn người đó từng có thể biết đã được **đánh giá rotation/revocation** theo rủi ro; gỡ quyền đọc hiện tại không thể thu hồi bản sao secret đã lộ.
4. Runtime service account vẫn hoạt động đúng chức năng nếu còn nhu cầu, có owner mới và quyền tối thiểu.
5. Service account không còn dùng được decommission theo vòng đời riêng: disable, revoke key/certificate, gỡ role, chấm dứt job và đối soát.

**Không xóa nhầm service account dùng chung chỉ vì một nhân viên nghỉ việc.** Xóa vội có thể làm ngừng hoạt động của hệ thống. Quy trình đúng là thu hồi quyền cá nhân, chuyển ownership, đánh giá secrets và chỉ deprovision danh tính workload khi workload thực sự ngừng sử dụng.

## 11. Xây dựng hợp đồng bằng chứng (verification evidence)

Mỗi target cần có **tiêu chí PASS riêng**. Một hồ sơ mẫu có thể lưu:

~~~yaml
verificationCaseId: deprov-2026-0421
subjectId: person-4821
eventType: LEAVER
eventRef: trusted-hris-event-2045
effectiveAt: "2026-11-23T10:00:00Z"
policyVersion: leaver-verification-v3
scope:
  - target: workforce-idp
    accountRef: idp-user-4821
    expected:
      accountEnabled: false
      affectedSessionsAllowed: false
    evidence:
      configReadback: PASSED
      sessionCheck: PASSED
      verifiedAt: "2026-11-23T10:00:12Z"
  - target: finance-saas
    accountRef: scim-user-94
    expected:
      accountActive: false
      oldTokenCanAccess: false
    evidence:
      configReadback: PASSED
      oldTokenCheck: PENDING
      lastCheckedAt: "2026-11-23T10:00:25Z"
ownerTeam: iam-operations
overallStatus: VERIFICATION_IN_PROGRESS
~~~

Đây là **YAML minh họa**, không phải schema của sản phẩm IAM cụ thể. Trạng thái tổng phải còn **VERIFICATION_IN_PROGRESS** vì kiểm tra token tại Finance SaaS chưa hoàn tất. Không được tự chuyển thành VERIFIED chỉ vì \`configReadback\` đã PASS.

Metadata thường cần có:

| Nhóm thông tin | Mục đích |
| --- | --- |
| Subject, event, source, revision | Xác định đúng người/sự kiện, tránh ghi đè bằng event cũ. |
| Mốc hiệu lực, thời điểm áp dụng, thời điểm xác minh | Đo độ trễ và kiểm chứng SLA. |
| Target ID, action, resource scope | Phân biệt quyền nào đã thu hồi ở hệ thống nào. |
| Policy version và tiêu chí PASS | Có thể giải thích vì sao chốt trạng thái. |
| Loại bằng chứng, nguồn và timestamp | Biết bằng chứng là readback, kiểm thử quyền hay xác nhận thủ công. |
| Request/correlation ID | Nối log HRIS, IAM, IdP, SCIM, SaaS và gateway. |
| Lỗi, retry, owner, exception expiry | Hành động tiếp theo với sai lệch hoặc blocker. |

**Không đưa mật khẩu, access token, refresh token, private key hay secret vào evidence.** Chỉ lưu định danh tham chiếu và metadata tối thiểu theo chính sách bảo vệ dữ liệu; giới hạn truy cập và thời gian giữ log.

## 12. Readback, consistency và xử lý sự kiện bất đồng bộ

Nhiều ứng dụng áp thay đổi theo cơ chế **eventual consistency**: SCIM báo thành công, nhưng bộ máy authorization hoặc các node ứng dụng chưa đồng bộ ngay. Việc xác minh cần thiết kế retry có kiểm soát:

1. Đọc lại trạng thái sau khi lệnh được chấp nhận.
2. Nếu chưa khớp, xác định lỗi **chưa áp dụng**, **đang đồng bộ** hay **có đường grant khác**.
3. Thử lại với backoff/jitter trong thời hạn cho phép; tôn trọng \`Retry-After\` khi có.
4. Nếu quyền nhạy cảm còn dùng được quá mốc cho phép, dùng **kiểm soát bù trừ** như chặn ở gateway/identity layer nếu được thiết kế và phê duyệt.
5. Escalate cho owner ứng dụng khi vượt SLA hoặc thiếu khả năng quan sát.
6. Tiếp tục lưu các lần readback và chỉ chốt VERIFIED khi điều kiện đạt.

### Tránh đảo ngược trạng thái do event cũ

Giả sử An đã Leaver, nhưng một sự kiện Mover cũ được gửi lại từ hàng đợi. Nếu consumer không kiểm tra revision và **trạng thái HR hiện hành**, nó có thể tạo lại account hoặc role. Quy trình cần:

- Event ID và version/revision từ nguồn có thẩm quyền.
- Idempotency key theo subject, target và loại thao tác.
- So sánh desired state hiện hành trước mọi update/retry.
- Chặn trạng thái cấp lại quyền trái Leaver hoặc trái mốc hiệu lực.
- Readback sau thao tác để nhận ra drift.

**Timeout không phải bằng chứng thất bại tuyệt đối.** Lệnh revoke có thể đã được áp dù phản hồi bị mất. Retry nên đọc trạng thái trước để tránh thao tác ngược hoặc gây ra lỗi không cần thiết.

## 13. Pseudocode: điều phối xác minh deprovisioning

Đoạn Java sau diễn đạt luồng logic, **không phải mã production-ready**. Connector cụ thể cần tự triển khai an toàn theo khả năng của IdP, SCIM, application và hệ thống quản lý phiên:

~~~java
// Pseudocode: event được nhận từ nguồn tin cậy, không phải request tự khai.
VerificationReport verifyDeprovisioning(TrustedLifecycleEvent event) {
    policy.assertTrustedEvent(event);

    WorkforceState current = hrRepository.currentState(event.subjectId());
    if (!policy.matchesCurrentLifecycle(event, current)) {
        return VerificationReport.blocked("stale_or_inconsistent_event");
    }

    DesiredAccess desired = accessPolicy.desiredAfterEvent(current, event);
    AccessInventory inventory = identityRegistry.resolveAllKnownTargets(
        event.subjectId()
    );

    VerificationReport report = new VerificationReport(event.id());

    for (AccessTarget target : inventory.targets()) {
        TargetVerificationPlan plan = policy.planFor(target, desired);

        try {
            // Đọc thực tế tại target, không dựa riêng vào kết quả revoke trước.
            AccountState account = connector(target).readAccount(target.accountId());
            Entitlements entitlements = connector(target).readEffectiveAccess(
                target.accountId()
            );
            CredentialState credentialState = connector(target)
                .readCredentialAndSessionState(target.accountId());

            boolean configMatches = plan.matchesExpectedConfiguration(
                account, entitlements, credentialState
            );

            // Probe chỉ đọc/được phép; nếu không hỗ trợ, trả NOT_OBSERVABLE,
            // không tự coi là PASS.
            AccessProbeResult probe = accessVerifier.verifyApprovedProbes(
                target, plan
            );

            if (configMatches && plan.acceptsProbeEvidence(probe)) {
                report.markVerified(target.id(), probe.evidenceRef());
            } else {
                report.markUnverified(target.id(), plan.explainMismatch(probe));
            }
        } catch (TransientConnectorFailure ex) {
            report.markRetryable(target.id(), ex.safeCode());
        } catch (MappingOrPolicyFailure ex) {
            report.markBlocked(target.id(), ex.safeCode());
        }
    }

    // Mọi đích bắt buộc phải đạt; missing coverage không phải PASS.
    if (report.allMandatoryTargetsVerified()
            && report.hasNoUnapprovedResidualAccess()) {
        report.markVerifiedAt(clock.now());
    }

    auditStore.persistWithoutSecrets(report);
    return report;
}
~~~

Các hợp đồng quan trọng:

- **Đọc trạng thái thực tế** tại đích, không chỉ kiểm tra bản ghi công việc trong IAM.
- **Xác định full coverage** của inventory; target không đọc được phải được báo thiếu bằng chứng.
- **Kiểm tra cả hiệu lực** khi quyền còn có thể tồn tại qua session/token/cache.
- **Không lẫn lỗi môi trường với access denied:** probe phải có khả năng giải thích kết quả.
- **Không tự chấp nhận ngoại lệ:** chỉ policy/phê duyệt có hiệu lực mới cho phép trạng thái exception và nó không được đánh đồng với VERIFIED.
- **Không ghi secret vào log**, bảo vệ các bằng chứng kiểm toán.

Trong sản phẩm thực tế, phép thử với credential cũ phải được tổ chức được phép và bảo đảm không tiết lộ bí mật hay thực hiện thao tác phá hoại.

## 14. Ma trận kiểm thử xác minh

| Tình huống | Quan sát kiểm tra | Kết quả kỳ vọng |
| --- | --- | --- |
| IdP đã disable account Leaver. | Thử login mới và readback user. | Login bị từ chối, trạng thái account đúng. |
| SCIM trả 204 nhưng User vẫn active. | GET lại SCIM User sau khoảng áp dụng. | Không báo VERIFIED; retry/escalation theo SLA. |
| SCIM active=false nhưng SaaS vẫn nhận session cũ. | Probe có kiểm soát với session đã tạo trước Leaver. | Deprovision chưa đạt điều kiện; xử lý session/app. |
| JWT còn hạn chứa role cũ. | Probe theo cơ chế test hợp lệ tới API bảo vệ. | Quyền cũ không thể dùng; nếu còn, đánh dấu sai lệch. |
| Người dùng đã gỡ khỏi IdP group nhưng còn direct grant. | Đọc effective roles và kiểm tra hành động. | Phải gỡ grant trực tiếp, chưa thể đóng. |
| Mover chuyển Finance, nhưng vẫn xem tài liệu Sales qua ACL. | Đánh giá ACL/resource authorization. | Không còn quyền Sales ngoài ngoại lệ đã duyệt. |
| Nhân viên nghỉ nhưng personal API token còn active. | Đọc danh sách token và kiểm tra trạng thái revoke. | Token bị thu hồi hoặc bị API từ chối. |
| Người dùng bị xóa quyền vault nhưng biết secret cũ. | Kiểm tra rotation/revocation của credential phù hợp. | Không còn đường sử dụng bí mật bị lộ theo mục tiêu xử lý. |
| Tài khoản SaaS không hỗ trợ API readback. | Xem phương án test thay thế và owner xác nhận. | Ghi rõ limitation; không tự PASS. |
| Probe nhận 503 do hệ thống đích down. | Phân tích mã lỗi/health check. | Kết quả inconclusive; không diễn giải là từ chối truy cập. |
| Event Mover cũ tới sau Leaver. | So revision và HR current state. | Không tái tạo account hoặc role đã thu hồi. |
| Connector timeout khi revoke token. | Đọc trạng thái token trước retry. | Không nhân đôi thao tác sai; theo dõi tới readback. |
| Một target bị lỗi nhưng tất cả target khác PASS. | Tổng hợp trạng thái theo target bắt buộc. | Tổng thể còn PARTIAL/BLOCKED, chưa CLOSED VERIFIED. |
| Account bị disable nhưng file offline đã tải vẫn còn. | Kiểm tra quy trình thiết bị/dữ liệu tương ứng. | Không tuyên bố dữ liệu offline bị xóa từ xa khi chưa có bằng chứng. |
| Dịch vụ còn chạy bằng service account do nhân viên cũ từng quản trị. | Kiểm tra owner, quyền quản trị, secrets và rotation. | Dịch vụ được bàn giao; quyền của nhân viên cũ bị gỡ. |

## 15. Ví dụ thực tế: Leaver với ba đường truy cập

**Bối cảnh:** Hương rời công ty lúc 17:00 ngày 23/11. Hương có tài khoản ở IdP, CRM SaaS và hệ thống tài liệu nội bộ; trước đây còn tạo một personal API token để truy vấn CRM.

### 15.1. Kế hoạch trước giờ hiệu lực

IAM đối chiếu chủ thể Hương với ID ổn định, xác nhận sự kiện Leaver từ HRIS, xác định các tài khoản liên kết, nhóm/role, token và quyền chia sẻ. Mỗi đích có owner, SLA, hành động và tiêu chí kiểm chứng riêng. Những hệ thống ngoài scope đã biết phải được liệt kê là **coverage gap** để xử lý.

### 15.2. Thao tác lúc 17:00

1. Disable account IdP, thu hồi các phiên và credential theo khả năng triển khai.
2. Connector SCIM đặt CRM User thành inactive, gỡ các nhóm/entitlement không còn hợp lệ.
3. Revoke personal API token trong CRM và chặn các đường API khác của Hương.
4. Hệ thống tài liệu gỡ group, direct ACL và chuyển ownership tài liệu cần giữ theo chính sách.
5. Đối soát local sessions của CRM/tài liệu, kiểm tra thiết bị/secret có liên quan nếu có.

### 15.3. Xác minh từng kết quả

| Đích | Trạng thái sau lần kiểm tra đầu | Hành động tiếp theo |
| --- | --- | --- |
| IdP | Account disabled, login mới bị từ chối. | Lưu evidence; đánh giá session còn tồn. |
| CRM SCIM | active=false theo readback. | Kiểm tra local session và API token. |
| CRM API token | Token vẫn có trạng thái active. | Revoke và kiểm tra lại trước khi đóng. |
| Hệ thống tài liệu | Nhóm đã gỡ, nhưng folder ACL trực tiếp còn. | Thu hồi ACL và kiểm tra lại quyền đọc. |

Tại thời điểm này, kết luận đúng là **chưa hoàn tất deprovisioning** dù IdP và SCIM đã thành công. Sau khi token bị revoke, ACL bị gỡ, phiên cũ bị chặn theo chính sách và các bước còn lại được đối soát, hồ sơ mới đạt điều kiện VERIFIED.

### 15.4. Trường hợp ứng dụng không thể thu hồi session ngay

Nếu CRM có session không hỗ trợ revoke lập tức, phải ghi rõ **cửa sổ còn hiệu lực**, mức rủi ro, thời điểm hết hạn dự kiến và phương án bù trừ như chặn tại gateway, hạn chế mạng hoặc kiểm tra quyền hiện hành. Không dùng cụm từ “đã vô hiệu hóa tức thì toàn bộ” khi kiến trúc không hỗ trợ. Tổ chức cần chọn SLA phù hợp và nâng cấp hệ thống nếu cửa sổ rủi ro không chấp nhận được.

## 16. Ví dụ Mover: giữ quyền cần thiết và gỡ quyền cũ

**Bối cảnh:** Nam chuyển từ Sales sang Finance. Mục tiêu không phải xóa toàn bộ danh tính hay đăng ký SSO lại, mà điều chỉnh **effective access**.

~~~text
KEEP    employee.email
KEEP    employee.portal.read
REVOKE  sales.crm.customer.read
REVOKE  sales.crm.export
REVOKE  sales.drive.shared-folder
REVOKE  sales-service-secret.read
GRANT   finance.invoice.approved.read (sau phê duyệt)
DENY    finance.payment.approve (không thuộc vai trò)
~~~

Xác minh cần quan sát:

- IdP/SCIM không còn nhóm Sales không hợp lệ.
- CRM không còn direct role, ACL hoặc session cho phép đọc/xuất dữ liệu Sales.
- Nam không còn quyền vault/CI/CD đối với dịch vụ cũ; credential đã biết được xử lý theo rủi ro.
- Quyền truy cập chung vẫn hoạt động, tránh thu hồi nhầm.
- Finance chỉ được cấp quyền đúng phê duyệt, không có cặp quyền xung đột SoD.
- Nếu được bàn giao dữ liệu Sales tạm thời, exception phải có phạm vi tài nguyên, thời hạn và bằng chứng tự thu hồi riêng.

**Một quyền cũ có thể đến từ nhiều đường.** Gỡ role Sales ở IdP không đủ khi ACL trực tiếp hoặc cache entitlement vẫn cho phép truy cập. Cần kiểm tra effective permission theo từng tài nguyên quan trọng.

## 17. Kiểm toán, SLA và chỉ số chứng minh hiệu quả

Mỗi sự kiện deprovisioning nên có chuỗi thời gian:

1. **effectiveAt:** mốc phải chấm dứt quyền theo nguồn nhân sự/chính sách.
2. **receivedAt:** lúc IAM nhận và xác minh sự kiện.
3. **requestedAt:** lúc phát yêu cầu thu hồi tới target.
4. **appliedAt:** lúc target xác nhận thao tác được áp dụng.
5. **verifiedAt:** lúc bằng chứng tại điểm thực thi đạt tiêu chí.
6. **closedAt:** lúc workflow được đóng sau khi xử lý mọi target/exception theo chính sách.

**Revocation latency** nên đo tới **verifiedAt** cho từng đích/loại quyền, không chỉ tới khi connector nhận HTTP 200. Chỉ số và log nên dùng UTC hoặc timezone rõ ràng để tránh nhầm mốc hiệu lực.

| Chỉ số | Cách hiểu | Điều cần cảnh giác |
| --- | --- | --- |
| **Verification completion rate** | Tỷ lệ hồ sơ có đầy đủ bằng chứng bắt buộc. | Không đếm ticket “đã mở” như hoàn tất. |
| **Revocation latency by target** | Thời gian từ effectiveAt đến verifiedAt. | Mỗi hệ thống có cơ chế và SLA khác nhau. |
| **Residual access count** | Số quyền cũ còn khả năng sử dụng hoặc chưa khớp desired state. | Tách quyền có ngoại lệ hợp lệ khỏi quyền sai phạm. |
| **Unverified target count** | Đích không đọc được trạng thái, thiếu coverage hoặc bằng chứng. | Không tự hiểu “không phát hiện” là “không tồn tại”. |
| **Retry / connector failure rate** | Tỷ lệ lỗi đồng bộ, quá hạn và escalation. | Mọi lần retry phải giữ idempotency. |
| **Orphaned account count** | Tài khoản không còn subject hoặc owner hợp lệ nhưng vẫn hoạt động. | Bao gồm local account và service account. |
| **Stale session/token exposure** | Cửa sổ phiên/token cũ còn được chấp nhận. | Cần đo ở resource server, không chỉ tại IdP. |
| **Exception aging** | Ngoại lệ còn mở hoặc quá hạn. | Quyền tạm phải thực sự tự thu hồi, không chỉ được nhắc hạn. |

**SLA không đồng nghĩa bảo đảm thu hồi tức thì.** Tài nguyên đặc biệt nhạy cảm có thể cần quyền bị chặn ở điểm thực thi gần thời gian thực; với hệ thống legacy, kiến trúc phải nêu rõ giới hạn và phương án giảm rủi ro.

### Bảo vệ audit và dữ liệu cá nhân

Chỉ lưu bằng chứng đủ phục vụ kiểm toán, có phân quyền truy cập, retention và chống chỉnh sửa trái phép. Tránh lưu dữ liệu giấy tờ danh tính, cookie phiên, OTP, token hoặc secret thật. Khi cần kiểm tra trạng thái token, sử dụng ID/metadata an toàn theo hợp đồng của hệ thống.

## 18. Những sai lầm thường gặp

| Sai lầm | Tác động | Cách sửa |
| --- | --- | --- |
| Báo hoàn tất ngay khi HR gửi Leaver. | Các ứng dụng đích chưa đổi quyền. | Quản lý tiến độ từng target và tiêu chí VERIFIED. |
| Tin mã SCIM HTTP 200/204 là đủ. | Local session hoặc direct grant còn sống. | Readback User/Group và kiểm tra hiệu lực truy cập theo rủi ro. |
| Chỉ disable account IdP. | API key, SaaS local login, session cũ vẫn dùng. | Inventory mọi đường truy cập và revoke tại từng đích. |
| Chỉ xóa role, bỏ qua ACL. | Truy cập qua shared folder/đối tượng vẫn còn. | Kiểm tra effective permission và nguồn cấp. |
| Không xét JWT đã phát. | Access token cũ được chấp nhận tới khi hết hạn. | Thiết kế TTL/revocation/current-policy check phù hợp. |
| Probe gặp 404/503 rồi kết luận bị từ chối. | Lỗi route hoặc outage bị nhầm với authorization deny. | Positive control, mã policy và log tương quan. |
| Không lưu mapping canonical ID → target ID. | Deprovision nhầm tài khoản. | Kiểm tra liên kết định danh ổn định. |
| Retry sự kiện cũ không kiểm revision. | Khôi phục account sau Leaver. | Tính desired state từ nguồn hiện hành, chống replay. |
| Đóng hồ sơ khi còn target “unknown”. | Không biết quyền đã thu hồi hay chưa. | BLOCKED/coverage gap với owner và kế hoạch xác minh. |
| Gỡ quyền vault nhưng không xét secret đã lộ. | Người cũ vẫn dùng secret sao chép. | Đánh giá rotate/revoke credential và phân quyền workload. |
| Xóa service account đang vận hành khi owner nghỉ. | Gián đoạn dịch vụ. | Chuyển owner, thu hồi quyền cá nhân, duy trì workload cần thiết. |
| Hứa dữ liệu offline bị xóa ngay sau disable. | Báo cáo vượt quá khả năng kỹ thuật. | Quản lý thiết bị/dữ liệu và nói rõ giới hạn thu hồi offline. |

## 19. Checklist đóng hồ sơ deprovisioning

Trước khi chuyển hồ sơ sang **CLOSED**, người phụ trách phải trả lời có bằng chứng cho các câu hỏi sau:

1. **Nguồn sự kiện** có hợp lệ, đúng subject ID và thời điểm hiệu lực không?
2. **Inventory** đã phủ các ứng dụng, đặc quyền, token, account cục bộ, ACL và đường truy cập có liên quan chưa?
3. **Desired state** đã xác định rõ quyền phải thu hồi và quyền còn hợp lệ (đặc biệt với Mover) chưa?
4. **Các lệnh thu hồi** đã được thực thi và ghi trạng thái theo từng hệ thống đích chưa?
5. **Readback** của account, group, role, credential và ACL có khớp kết quả mong muốn không?
6. **Session/token** và quyền API đã được đánh giá hiệu lực theo rủi ro/SLA chưa?
7. **Service account, vault, CI/CD** và credential mà người cũ từng kiểm soát đã được xem xét chưa?
8. **Sai lệch, lỗi retry, ngoại lệ** đều có owner, thời hạn và trạng thái riêng chưa?
9. **Audit** có đủ mốc thời gian, correlation ID, policy version và bằng chứng không chứa bí mật chưa?
10. **Kết luận** có giới hạn phạm vi rõ ràng, không tuyên bố rộng hơn những gì thực sự đã được kiểm chứng không?

Nếu một điều kiện bắt buộc chưa đạt, kết quả phải là **chưa VERIFIED/BLOCKED** hoặc trạng thái ngoại lệ được phê duyệt, thay vì “đóng cho đủ KPI”.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** Connector SCIM báo thành công và User có active=false. Có thể kết luận mọi quyền truy cập đã chấm dứt ngay không?

**Trả lời:** Không. Cần đọc lại các entitlement liên quan và đánh giá đường đăng nhập cục bộ, phiên, token, API key, ACL theo khả năng và chính sách của ứng dụng đích.

**Câu 2.** Sự khác nhau giữa trạng thái APPLIED và VERIFIED là gì?

**Trả lời:** APPLIED cho biết thao tác được target áp dụng theo hợp đồng kỹ thuật. VERIFIED đòi hỏi bằng chứng cấu hình và/hoặc hiệu lực quyền tại các điểm thực thi đúng tiêu chí kiểm chứng đã định nghĩa.

**Câu 3.** Vì sao dùng HTTP 503 từ API làm bằng chứng deprovisioning là sai?

**Trả lời:** HTTP 503 phản ánh dịch vụ không sẵn sàng, không chứng minh IAM authorization từ chối. Cần probe/positive control hoặc bằng chứng trạng thái phù hợp để kết luận.

**Câu 4.** Vì sao việc gỡ group tại IdP có thể không đủ để xóa quyền xem tài liệu?

**Trả lời:** Người dùng có thể còn direct ACL, nhóm lồng, link chia sẻ hoặc session/cache. Cần kiểm tra mọi đường cấp effective access tại tài nguyên.

**Câu 5.** Nhân viên nghỉ việc từng có quyền đọc secret của service account. Chỉ gỡ quyền vault hiện tại đã đủ chưa?

**Trả lời:** Chưa chắc. Nếu người đó từng xem hoặc sao chép secret, cần đánh giá rotation/revocation credential và các quyền điều khiển workload như CI/CD, trust policy, repository.

**Câu 6.** Tại sao một JWT access token bị lộ có thể còn sử dụng sau khi role đã gỡ?

**Trả lời:** JWT tự chứa có chữ ký hợp lệ có thể được resource server chấp nhận tới khi hết hạn nếu server không kiểm tra revocation hoặc quyền hiện hành. Kiến trúc cần cơ chế ngăn quyền cũ theo SLA yêu cầu.

**Câu 7.** Trong Mover, phải xóa tất cả account và role cũ của nhân viên không?

**Trả lời:** Không. Cần tính desired state theo vai trò mới, giữ baseline còn hợp lệ, thu hồi quyền cũ không phù hợp và tránh xung đột nhiệm vụ. Kiểm chứng đúng cả phần giữ và phần gỡ.

**Câu 8.** Khi một hệ thống SaaS không cho đọc lại quyền, có nên mặc định PASS vì connector đã gửi lệnh không?

**Trả lời:** Không. Ghi rõ thiếu khả năng quan sát, dùng phương án chứng minh thay thế có kiểm soát hoặc escalation theo chính sách; không chuyển kết quả chưa xác minh thành thành công.

---

**Ghi nhớ:** Xác minh deprovisioning là **chứng minh quyền đã mất hiệu lực**, không chỉ chứng minh đã gửi lệnh. Một kết quả đáng tin cần bao quát **đúng danh tính, đúng đích, đúng mốc thời gian, đúng entitlement, phiên/token và bằng chứng tại điểm thực thi**. Kết hợp HRIS, IdP/SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ và kiểm toán giúp IAM kiểm soát quyền truy cập tồn dư xuyên suốt **Joiner–Mover–Leaver**.
