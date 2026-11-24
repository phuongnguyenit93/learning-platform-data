# External user trong quản lý vòng đời danh tính (IAM)

## 1. External user là ai và vì sao cần quản lý riêng?

Trong **Identity and Access Management (IAM)**, *external user* là **người dùng là con người** cần truy cập tài nguyên của một tổ chức nhưng không thuộc lực lượng nhân sự nội bộ do tổ chức đó trực tiếp quản lý. Họ có thể là nhân viên đối tác, nhà thầu, kiểm toán viên độc lập, chuyên gia triển khai, người được mời cộng tác hoặc khách hàng sử dụng dịch vụ.

Ví dụ: Công ty A cung cấp cổng quản lý đơn hàng cho Công ty B. Nhân viên B đăng nhập để xem đơn hàng của B trên hệ thống A. Với A, nhân viên đó là external user, dù họ là nhân viên nội bộ của B. Chính sách IAM của A phải kiểm soát **họ được làm gì trong tài nguyên của A**, kể cả khi B chịu trách nhiệm xác thực họ.

Điểm khó nằm ở ranh giới tổ chức:

- **Ai xác minh con người?** Có thể là IdP của đối tác, hệ thống Customer IAM (CIAM) hoặc chính tổ chức cung cấp ứng dụng.
- **Ai cấp và chịu trách nhiệm về quyền?** Chủ tài nguyên và người bảo trợ (*sponsor*) phía tổ chức cung cấp quyền.
- **Ai biết lúc nào người dùng rời đối tác hoặc hết hợp đồng?** Thường là phía đối tác, nên hệ thống nhận quyền phải có cơ chế đồng bộ, kiểm tra định kỳ và hết hạn tự động.
- **Ai thu hồi phiên và quyền trên các hệ thống đích?** Hệ thống IAM và các ứng dụng thực thi quyền trong phạm vi tổ chức cung cấp tài nguyên.

**External user không đồng nghĩa với external IdP.** External user là chủ thể truy cập; IdP là hệ thống xác thực và phát hành thông tin danh tính. Một external user có thể dùng IdP nội bộ của bên cung cấp (tài khoản khách) hoặc IdP của tổ chức mình (federation). Ngoài ra, external user khác với **service account/workload identity**: service account phục vụ tiến trình máy, tích hợp API hoặc tác vụ tự động, cần vòng đời và phương thức xác thực riêng.

### Các mô hình thường gặp

| Trường hợp | Danh tính và xác thực | Cấp quyền trong hệ thống đích | Rủi ro nổi bật |
|---|---|---|---|
| Nhân viên đối tác B2B | Đăng nhập qua IdP đối tác bằng SAML/OIDC hoặc qua tài khoản khách | Vai trò giới hạn theo tenant, dự án, hợp đồng | Quyền còn tồn tại sau khi nhân viên rời đối tác |
| Nhà thầu/đơn vị tư vấn | Tài khoản guest hoặc federation tùy mức độ tích hợp | Quyền theo công việc, thời hạn ngắn, có sponsor | Tài khoản không có người chịu trách nhiệm |
| Người dùng khách hàng B2C | CIAM, social login hoặc IdP thích hợp | Quyền gắn với chính tài khoản và dữ liệu khách hàng | Nhầm lẫn danh tính và truy cập dữ liệu khách hàng khác |
| Kiểm toán viên bên ngoài | Danh tính được xác minh và phê duyệt theo đợt | Chủ yếu quyền chỉ đọc, có ngày hết hạn | Tải dữ liệu quá phạm vi hoặc quyền không được gỡ |

**Nguyên tắc cốt lõi:** Việc xác thực thành công chỉ trả lời “người này là ai theo IdP”; hệ thống tài nguyên vẫn phải tự quyết định “người này được truy cập tài nguyên nào, với hành động nào, trong bao lâu”.

## 2. Những thành phần tạo nên một danh tính bên ngoài

Một thiết kế có thể mô hình hóa danh tính người dùng bên ngoài theo các thành phần tách biệt:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Identity source | Nơi khẳng định và quản lý danh tính gốc | IdP của Công ty B |
| Stable subject identifier | Khóa nhận diện ổn định trong phạm vi nguồn | Cặp (issuer, subject) của OIDC |
| Local principal / guest record | Bản ghi đại diện tại tổ chức A | Guest ID 3842, trạng thái active |
| Organization membership | Người này thuộc đối tác/tenant nào tại A | Tenant “B”, hợp đồng C-2026 |
| Authorization grants | Vai trò, điều kiện và phạm vi tài nguyên | Viewer của dự án P42 |
| Sponsor / owner | Người hoặc bộ phận chịu trách nhiệm duyệt quyền | Chủ dự án P42 phía A |
| Access validity | Thời gian, trạng thái, điều kiện duy trì quyền | Hết hạn 31/12/2026 |
| Audit evidence | Dấu vết cấp, dùng, đổi và thu hồi quyền | Ai duyệt, thay đổi gì, thời điểm nào |

### Không dùng email làm khóa danh tính duy nhất

Email là thuộc tính tiện cho liên lạc, nhưng có thể đổi, được tái sử dụng hoặc trùng theo từng tổ chức. Với OIDC, nên liên kết tài khoản với cặp **(iss, sub)** sau khi xác thực token đúng quy tắc. Với SAML, dùng định danh được thỏa thuận là ổn định trong một nguồn xác thực, chẳng hạn persistent NameID hoặc thuộc tính định danh bất biến đã được xác minh. Khi đổi IdP, liên kết sang danh tính mới phải có quy trình xác nhận có kiểm soát.

Không tự động ghép hai tài khoản chỉ vì email giống nhau, và không suy quyền từ đuôi email. Ví dụ, “@partner.example” có thể hỗ trợ kiểm tra thuộc tổ chức, nhưng **không chứng minh** một cá nhân được xem mọi dự án của đối tác.

### Sơ đồ luồng xác thực và phân quyền

~~~mermaid
flowchart LR
    U["External user"] --> APP["Ứng dụng / Service Provider"]
    APP <-->|"OIDC / SAML SSO"| IDP["IdP của đối tác"]
    IDP -->|"SCIM nếu được triển khai"| DIR["Guest directory / IAM của A"]
    DIR --> POLICY["RBAC / ABAC + tenant scope"]
    APP --> POLICY
    POLICY -->|"Cho phép hoặc từ chối"| R["Tài nguyên của A"]
    SP["Sponsor / chủ tài nguyên"] -->|"Phê duyệt và rà soát"| DIR
    AUD["Audit log"] <-->|"Sự kiện cấp quyền và truy cập"| APP
    DIR --> AUD
~~~

Sơ đồ thể hiện các luồng **khác nhau**. OIDC/SAML phục vụ đăng nhập và chứng thực; SCIM (nếu có) đồng bộ vòng đời bản ghi người dùng; RBAC/ABAC và tenant scope quyết định quyền truy cập. Không phải mọi tích hợp federation đều hỗ trợ SCIM.

## 3. Vòng đời Joiner–Mover–Leaver của external user

Với người dùng bên ngoài, Joiner–Mover–Leaver (JML) vẫn là mô hình nền tảng, nhưng tác nhân kích hoạt thường đến từ **hợp đồng, đối tác, dự án và người bảo trợ**, không chỉ từ hệ thống HR nội bộ.

~~~mermaid
stateDiagram-v2
    [*] --> Requested: Mời / yêu cầu truy cập
    Requested --> Active: Xác minh + phê duyệt + cấp quyền
    Requested --> Rejected: Không đáp ứng điều kiện
    Active --> Active: Mover / chỉnh phạm vi / rà soát
    Active --> Suspended: Sự cố, rủi ro hoặc cần xác minh lại
    Suspended --> Active: Được phê duyệt khôi phục
    Active --> Revoked: Hết hạn / rời đối tác / kết thúc hợp đồng
    Suspended --> Revoked: Đóng yêu cầu hoặc hết hạn
    Rejected --> [*]
    Revoked --> [*]
~~~

### 3.1. Joiner: tiếp nhận và cấp quyền ban đầu

Quy trình Joiner điển hình:

1. **Phát sinh yêu cầu hợp lệ.** Người bảo trợ chỉ rõ đối tác, lý do truy cập, ứng dụng, tài nguyên, vai trò và ngày hết hạn. Không chấp nhận yêu cầu “quyền admin toàn bộ” khi công việc chỉ cần xem báo cáo.
2. **Xác thực quan hệ và danh tính.** Kiểm tra đối tác có hợp đồng phù hợp, danh tính có được xác minh, lời mời có đến đúng người và người đó còn thuộc đơn vị được mời. Mức độ xác minh tỷ lệ với độ nhạy của tài nguyên.
3. **Phê duyệt có trách nhiệm.** Chủ tài nguyên hoặc người được ủy quyền phê duyệt theo chính sách. Các quyền nhạy cảm có thể cần phê duyệt bổ sung và điều kiện chặt hơn.
4. **Tạo hoặc liên kết bản ghi IAM.** Gắn định danh từ IdP với local principal/guest, tổ chức đối tác, sponsor, thời hạn, trạng thái và phạm vi dữ liệu. Tránh tạo tài khoản trùng không được quản lý.
5. **Cấp quyền tối thiểu.** Dùng nhóm/vai trò RBAC và điều kiện ABAC để giới hạn theo tenant, dự án, loại dữ liệu, thời gian hoặc thiết bị nếu phù hợp.
6. **Thiết lập truy cập an toàn.** Ưu tiên SSO/federation đáng tin cậy, MFA phù hợp (ưu tiên chống phishing ở vị trí nhạy cảm), thời hạn phiên hợp lý và giám sát đăng nhập bất thường.
7. **Ghi bằng chứng.** Lưu yêu cầu, người duyệt, quyền được cấp, phạm vi, hạn sử dụng và sự kiện tạo tài khoản.

Hai cách khởi tạo tài khoản thường dùng:

- **Pre-provisioning:** Tạo tài khoản trước khi đăng nhập, qua quy trình mời, API hoặc SCIM. Phù hợp khi cần xác nhận quyền trước, có danh sách người dùng và có nguồn đồng bộ đáng tin cậy.
- **Just-in-time (JIT) provisioning:** Tạo bản ghi khi người dùng lần đầu đăng nhập liên kết. Cần ràng buộc với tổ chức, lời mời/điều kiện chấp thuận và quyền tối thiểu; đăng nhập thành công không được tự động mang lại quyền vào dữ liệu nhạy cảm.

Ví dụ: Đối tác B cần truy cập dự án P42 để đối soát. Sau khi chủ dự án A duyệt, IAM tạo guest của người dùng B, gắn tenant=B, role=report_viewer, project=P42 và thời hạn đến hết hợp đồng. Người dùng đăng nhập qua IdP của B; ứng dụng chỉ cho phép đọc báo cáo thuộc P42.

### 3.2. Mover: thay đổi vai trò, phạm vi hoặc quan hệ

Mover xảy ra khi người dùng chuyển dự án, đổi nhiệm vụ, đổi đơn vị trong đối tác, thay đổi hợp đồng hoặc chuyển từ quyền chỉ đọc sang quyền thao tác. Các sự kiện này phải dẫn đến **đánh giá lại quyền**, thay vì cộng dồn quyền cũ và mới.

Quy trình an toàn:

1. Nhận tín hiệu thay đổi từ đối tác, sponsor, hợp đồng, IAM hoặc đợt access review.
2. So sánh quyền hiện tại với quyền cần cho nhiệm vụ mới, bao gồm tenant, nhóm, môi trường và dữ liệu.
3. Thu hồi quyền không còn phù hợp trước hoặc cùng lúc với việc cấp quyền mới; yêu cầu duyệt lại nếu nâng đặc quyền.
4. Cập nhật group/role/attribute ở IAM và các ứng dụng đích; kiểm tra đồng bộ và hiệu lực tại điểm phân quyền.
5. Ghi lại quyền trước/sau, nguyên nhân, người duyệt và kết quả áp dụng.

**Ví dụ:** Nhân viên B rời P42 và được chuyển sang P51. Nếu IAM chỉ thêm quyền P51 mà quên gỡ P42 thì người này giữ truy cập tồn dư (*residual access*). Thiết kế đúng phải gỡ quyền P42 và cấp P51 theo yêu cầu mới; nếu P51 thuộc tenant khác, phải có phê duyệt và cơ sở chia sẻ dữ liệu riêng.

### 3.3. Leaver: kết thúc và thu hồi quyền

Leaver được kích hoạt bởi nghỉ việc tại đối tác, kết thúc hợp đồng, hết thời hạn mời, sponsor rút quyền, tổ chức đối tác mất tư cách hoặc sự cố bảo mật.

Cần phân biệt **không đăng nhập được nữa** với **không còn quyền truy cập**. Một tài khoản bị vô hiệu hóa ở IdP đối tác có thể vẫn giữ phiên đang hoạt động tại ứng dụng, API token, group membership hoặc dữ liệu được chia sẻ ở hệ thống đích.

Thứ tự xử lý tham khảo:

1. Đánh dấu danh tính hoặc membership tại bên cung cấp tài nguyên là suspended/revoked ngay khi sự kiện thu hồi có hiệu lực; chặn quyết định cấp quyền mới.
2. Thu hồi group membership, role, policy binding, chia sẻ dữ liệu và quyền trong các ứng dụng downstream. Với quyền nhạy cảm, xác minh thực tế tại ứng dụng đích.
3. Hủy phiên/refresh token ở nơi có khả năng quản lý; thu hồi credential và API token do cá nhân này sở hữu, xử lý các bản sao khóa liên quan theo chính sách.
4. Chặn truy cập còn hiệu lực từ access token đã cấp bằng cơ chế phù hợp (token ngắn hạn, kiểm tra trạng thái tại resource server hoặc cơ chế thu hồi có hỗ trợ). Không mặc định việc khóa tài khoản làm JWT đã phát hành vô hiệu ngay lập tức.
5. Giữ lại hoặc xóa dữ liệu theo chính sách lưu trữ, pháp lý và quyền riêng tư; không xóa audit trail cần bảo toàn. Có thể vô hiệu hóa trước rồi xóa sau.
6. Đối soát danh sách tài khoản và quyền trên các hệ thống; ghi bằng chứng hoàn tất và phát hiện các lần đồng bộ lỗi.

Khi sự kiện từ đối tác đến chậm hoặc không có, hệ thống vẫn cần **ngày hết hạn bắt buộc**, cơ chế tái phê duyệt và kiểm tra tài khoản không có sponsor. Đây là hàng rào chống quyền tồn dư.

## 4. IdP, SSO, SCIM, RBAC và ABAC phối hợp ra sao?

| Cơ chế | Trả lời câu hỏi gì? | Dùng đúng trong external-user IAM |
|---|---|---|
| **IdP** (Identity Provider) | Ai xác thực người dùng? | Phát hành assertion/token về danh tính; thiết lập trust với ứng dụng nhận |
| **SSO qua OIDC/SAML** | Người dùng đăng nhập liên thông thế nào? | Xác thực qua IdP đã tin cậy; ứng dụng kiểm tra token/assertion và tạo phiên |
| **SCIM** | Tạo, cập nhật, vô hiệu hóa bản ghi người dùng/nhóm thế nào? | Đồng bộ lifecycle khi hai hệ thống có tích hợp, xử lý sai lệch và retry |
| **RBAC** | Vai trò nào có tập quyền nào? | Ví dụ partner_viewer, auditor_readonly, project_editor |
| **ABAC** | Điều kiện bổ sung nào phải đúng? | Tenant, project, hợp đồng còn hiệu lực, classification, thời gian |
| **PAM/JIT elevation** | Khi nào được nâng đặc quyền tạm thời? | Yêu cầu phê duyệt, phiên đặc quyền ngắn hạn, theo dõi và thu hồi |
| **Access review** | Quyền hiện tại còn cần thiết không? | Sponsor/chủ tài nguyên xác nhận theo chu kỳ và khi có thay đổi |

### Xác minh federation và ranh giới tin cậy

Khi nhận OIDC ID token, ứng dụng phải kiểm tra chữ ký, issuer (iss), audience (aud), thời hạn (exp), nonce/luồng đăng nhập khi áp dụng và các yêu cầu bảo mật khác theo cấu hình. Với SAML, phải xác minh chữ ký, issuer, audience, thời gian, recipient/destination và điều kiện của assertion. Không tin một trường “role” do IdP đối tác tự gửi, trừ khi nó đã được ánh xạ theo chính sách và hợp đồng tin cậy cụ thể.

Ngay cả sau khi xác thực đúng, ứng dụng cần kiểm tra bản ghi người dùng còn active, membership còn hiệu lực, sponsor/contract có đủ điều kiện và quyền có đúng tài nguyên yêu cầu. Các kiểm tra này phải được thực hiện tại điểm truy cập tài nguyên, không chỉ ở giao diện người dùng.

### SCIM giúp gì và không thay thế điều gì?

SCIM chuẩn hóa thao tác quản lý user/group giữa những hệ thống có triển khai. Ví dụ, một hệ thống provisioning có quyền phù hợp có thể gửi yêu cầu vô hiệu hóa user tại hệ thống đích:

~~~http
PATCH /scim/v2/Users/7e18b2 HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/scim+json

{
  "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
  "Operations": [
    {
      "op": "Replace",
      "path": "active",
      "value": false
    }
  ]
}
~~~

Đây là ví dụ minh họa chuẩn PATCH SCIM, không phải bằng chứng rằng mọi IdP hay ứng dụng đều hỗ trợ thao tác này. Hệ thống đồng bộ phải xác thực phía gửi, dùng quyền tối thiểu, xử lý lỗi/retry và đối soát trạng thái sau khi gọi. **SCIM không tự hủy các phiên ứng dụng**, không thay thế phê duyệt quyền và không bảo đảm tài nguyên downstream đã bị thu hồi nếu tích hợp lỗi.

### Phân quyền theo tenant và dự án

Ví dụ chính sách bằng mã giả:

~~~text
allow(request, principal, membership, grant):
    if principal.status != "active": deny
    if membership.status != "active": deny
    if current_time >= membership.expires_at: deny
    if membership.tenant_id != request.tenant_id: deny
    if grant.project_id != request.project_id: deny
    if request.action not in grant.allowed_actions: deny
    if request.data_classification exceeds grant.clearance: deny
    return allow
~~~

Một quyền “viewer” không nên có tác dụng trên mọi tenant. Trong hệ thống SaaS nhiều khách hàng, kiểm tra tenant tại backend là bắt buộc, kể cả khi front-end đã ẩn tài nguyên người dùng không được phép xem. Khi người dùng có nhiều membership, phải chọn ngữ cảnh truy cập rõ ràng và quyết định quyền trên membership tương ứng.

## 5. Một kịch bản thực tế: đối tác được mời vào cổng vận hành

Giả sử Công ty A quản lý cổng vận hành cho nhiều nhà cung cấp. Công ty B cần hai người tham gia dự án “Fulfillment 2026”:

| Thời điểm | Sự kiện | Xử lý IAM đúng | Bằng chứng cần có |
|---|---|---|---|
| Ngày 1 | B đề nghị hai tài khoản xem báo cáo | Sponsor A duyệt, liên kết danh tính từ IdP B, gán viewer cho dự án và hạn 90 ngày | Yêu cầu, danh tính, sponsor, role, scope, expiry |
| Ngày 10 | Một người cần xử lý đơn hàng | Đánh giá và phê duyệt thêm quyền editor trong đúng dự án; có thể cấp tạm thời | Ai nâng quyền, lý do, hạn và quyền trước/sau |
| Ngày 30 | Một người chuyển sang dự án khác | Xóa membership dự án cũ, xét quyền mới sau phê duyệt | Event mover và kết quả đồng bộ |
| Ngày 60 | B thông báo người còn lại nghỉ việc | Khóa access tại A, thu hồi session/grant, đối soát downstream | Thời điểm nhận sự kiện, disable, revoke, kiểm chứng |
| Ngày 90 | Hết thời hạn mời | Tự động hết quyền; chỉ gia hạn nếu sponsor xác nhận nhu cầu | Expiry/review và kết quả gia hạn hoặc thu hồi |

Trường hợp xấu: B đã khóa tài khoản ở IdP B, nhưng A chỉ xác thực người dùng tại thời điểm đăng nhập. Một phiên đã mở hoặc quyền lưu trong ứng dụng A vẫn có thể tồn tại. Vì vậy A cần quản lý phiên, thời hạn, trạng thái membership và cơ chế thu hồi tại chính các dịch vụ của mình.

## 6. Access review và bảo đảm không còn quyền truy cập tồn dư

**Access review** là hoạt động rà soát quyền hiện tại so với nhu cầu công việc. Đối với external user, ít nhất nên xác minh:

- Người dùng có còn làm việc với đối tác và còn được tài trợ bởi sponsor hợp lệ?
- Hợp đồng, dự án và mục đích xử lý dữ liệu có còn hiệu lực?
- Có quyền thừa, role đặc quyền hoặc membership vượt tenant/dự án không?
- Có tài khoản không đăng nhập lâu ngày, không có owner, hết hạn nhưng vẫn active không?
- Các ứng dụng downstream có phản ánh đúng trạng thái revoke không?
- Có external user đang sở hữu token, khóa API hoặc tích hợp tự động cần chuyển giao trách nhiệm không?

Tần suất review nên dựa trên độ nhạy và rủi ro: quyền đặc quyền/dữ liệu nhạy cảm được rà soát chặt hơn quyền thông thường. Ngoài review định kỳ, các sự kiện như đổi sponsor, chuyển dự án, sửa hợp đồng, nghỉ việc và phát hiện đăng nhập bất thường phải kích hoạt đánh giá ngay khi phù hợp.

**Tách ba khái niệm để tránh sai sót:**

1. **Authentication state:** IdP có chấp nhận đăng nhập không?
2. **Local access state:** Bản ghi và quyền của người dùng tại tài nguyên còn hiệu lực không?
3. **Active sessions/credentials:** Phiên, token, API key hoặc quyền chia sẻ đã phát hành có tiếp tục hoạt động không?

Kết thúc đầy đủ chỉ được khẳng định khi các lớp có liên quan đã được xử lý và kiểm chứng.

## 7. Bảo mật, quyền riêng tư và kiểm toán

### Các rủi ro thường gặp và kiểm soát tương ứng

| Rủi ro | Nguyên nhân | Kiểm soát gợi ý |
|---|---|---|
| Tài khoản mồ côi (*orphan account*) | Sponsor nghỉ việc hoặc hợp đồng hết hạn | Bắt buộc owner, hạn truy cập, tự động tạm khóa và rà soát |
| Quyền tồn dư (*privilege creep*) | Mover chỉ cộng thêm quyền | So sánh quyền trước/sau, loại quyền cũ, recertification |
| Nhầm tenant/cross-tenant access | Quyền kiểm tra theo role nhưng không kiểm tra phạm vi | Tenant isolation trong mọi truy vấn, policy ở backend |
| Chiếm tài khoản | MFA yếu, phishing hoặc lời mời bị chuyển tiếp | MFA mạnh, lời mời có hạn, kiểm tra rủi ro đăng nhập |
| Ghép nhầm danh tính | Dùng email làm định danh bất biến | Liên kết bằng định danh từ issuer tin cậy, quy trình account linking |
| Đối tác rời đi nhưng vẫn có phiên | Chỉ disable ở IdP hoặc đồng bộ chậm | Revoke session/token khi hỗ trợ, kiểm tra trạng thái resource server |
| Cấp quá quyền | Tin hoàn toàn nhóm/role do đối tác gửi | Role mapping do bên sở hữu tài nguyên kiểm soát, least privilege |
| Thiếu bằng chứng | Chỉ lưu log đăng nhập | Lưu cả tạo, duyệt, cấp, đổi, rà soát, thu hồi và đồng bộ lỗi |

Audit event hữu ích có thể lưu: mã người dùng nội bộ và external subject, issuer, tenant, resource, action, trạng thái trước/sau, thời điểm, người yêu cầu/người duyệt, nguồn sự kiện, correlation ID và kết quả áp dụng vào ứng dụng đích. Cần phân quyền truy cập audit log, bảo vệ tính toàn vẹn và tuân thủ thời hạn lưu trữ. Không ghi mật khẩu, token còn dùng được hoặc dữ liệu cá nhân không cần thiết vào log.

Với bên thứ ba, việc chuyển dữ liệu giữa tổ chức còn chịu yêu cầu của hợp đồng và luật bảo vệ dữ liệu tương ứng. IAM chỉ cấp quyền theo chính sách; tính hợp pháp của mục đích xử lý, thời hạn lưu và cơ chế chia sẻ dữ liệu vẫn cần được quản trị riêng.

### Chỉ số vận hành nên theo dõi

- **Thời gian thu hồi quyền:** Từ khi nhận sự kiện leaver đến khi các hệ thống đích xác nhận vô hiệu hóa.
- **Số external user quá hạn nhưng còn active.**
- **Số tài khoản không có sponsor/owner hợp lệ.**
- **Tỷ lệ quyền được rà soát đúng hạn**, tỷ lệ bị thu hồi sau review.
- **Số lỗi đồng bộ provisioning/deprovisioning** chưa được xử lý hoặc đối soát.
- **Số external user có quyền đặc quyền** và mức độ sử dụng quyền đó.

Đặt ngưỡng và SLA dựa trên rủi ro của hệ thống, thay vì mặc định một con số phù hợp cho mọi loại tài khoản.

## 8. Tình huống đặc biệt cần thiết kế rõ

**Đối tác đổi IdP hoặc đổi domain.** Không tự động chuyển tất cả quyền theo email mới. Cần thẩm định tổ chức, ánh xạ định danh có kiểm soát, kiểm tra tài khoản trùng và thu hồi trust cũ khi hoàn tất.

**Người dùng thuộc nhiều tổ chức.** Không gom tất cả quyền vào một role chung. Duy trì membership và scope theo từng tổ chức, chọn rõ tenant đang hoạt động và ghi tenant vào quyết định phân quyền/audit.

**Người dùng vừa là nhân viên nội bộ vừa có quan hệ đối tác.** Quyền và vai trò có thể cần tách theo ngữ cảnh công việc; tránh tự động kế thừa quyền nội bộ cho ngữ cảnh external hoặc ngược lại.

**Federation/SCIM bị lỗi hoặc đối tác không gửi sự kiện nghỉ việc.** Thiết lập kiểm tra sai lệch, retry có giới hạn, cảnh báo và cơ chế hết hạn/review độc lập. Với lỗi xác minh hoặc trạng thái nghi ngờ, chính sách truy cập tài nguyên nhạy cảm nên theo nguyên tắc từ chối mặc định.

**Người dùng ngoài cần thao tác tự động qua API.** Nếu công việc do chương trình thực hiện, hãy dùng workload identity/service account có owner, credential được quản lý và phạm vi quyền riêng. Không chia sẻ mật khẩu external user hoặc dùng tài khoản con người làm robot lâu dài.

## 9. Checklist thiết kế external-user lifecycle

Trước khi triển khai, đội IAM và chủ ứng dụng có thể kiểm tra:

1. Có phân loại external user, đối tác, tenant và mục đích truy cập rõ ràng.
2. Có người yêu cầu, sponsor, chủ tài nguyên và luồng phê duyệt xác định.
3. Có định danh ổn định, liên kết tài khoản an toàn và trust với IdP được thẩm định.
4. Có MFA/chính sách phiên theo rủi ro, xác minh token/assertion đầy đủ.
5. Có hạn truy cập, role tối thiểu và kiểm tra tenant/project tại backend.
6. Có quy trình xử lý Joiner, Mover, Leaver với nguồn sự kiện và trách nhiệm cụ thể.
7. Có cách thu hồi local account, group, phiên và quyền downstream; có đối soát kết quả.
8. Có lịch access review, xử lý tài khoản mồ côi và quyền đặc quyền.
9. Có audit log, cảnh báo lỗi đồng bộ và chỉ số đo thời gian thu hồi.
10. Có phương án khi federation/SCIM không khả dụng hoặc đối tác ngừng hợp tác.

## 10. Tự kiểm tra hiểu biết

**Câu 1:** Nhân viên đối tác đã bị khóa ở IdP nhưng vẫn đang sử dụng được ứng dụng của bạn. Có phải IAM đã hoàn tất Leaver?

**Đáp án:** Chưa. Cần kiểm tra phiên đang hoạt động, token còn hiệu lực, local membership, các grants và quyền ở hệ thống đích; thực hiện thu hồi và xác minh hiệu lực.

**Câu 2:** OIDC ID token chứa email đúng domain của đối tác. Có thể tự động gán role administrator không?

**Đáp án:** Không. Email/domain không phải bằng chứng cấp quyền. Phải xác minh token đúng issuer/audience, liên kết stable subject và áp dụng phê duyệt, role mapping, scope và chính sách của tổ chức sở hữu tài nguyên.

**Câu 3:** Khi chuyển external user từ dự án P42 sang P51, thao tác quan trọng nhất là gì?

**Đáp án:** Đánh giá quyền cần thiết ở P51, thu hồi quyền P42 không còn cần và chỉ cấp quyền mới sau khi đáp ứng điều kiện phê duyệt; kiểm tra hiệu lực tại ứng dụng.

**Câu 4:** Triển khai SCIM có loại bỏ nhu cầu access review không?

**Đáp án:** Không. SCIM đồng bộ bản ghi theo nguồn được cấu hình, nhưng có thể thiếu sự kiện, đồng bộ lỗi hoặc không phản ánh đúng nhu cầu quyền theo hợp đồng/dự án. Access review vẫn cần để phát hiện quyền tồn dư.

## Kết luận

External user là mắt xích quan trọng trong **quản lý vòng đời danh tính** của hệ thống IAM vì quyền truy cập vượt qua ranh giới quản trị giữa các tổ chức. Thiết kế hiệu quả cần phối hợp **IdP và SSO để xác thực**, **SCIM hoặc quy trình provisioning để đồng bộ**, **RBAC/ABAC để giới hạn quyền**, cùng **sponsor, hạn truy cập, access review và audit** để kiểm soát xuyên suốt Joiner–Mover–Leaver. Mục tiêu là mỗi người bên ngoài chỉ có đúng quyền cần cho quan hệ hợp tác hiện tại, và quyền đó được thu hồi có kiểm chứng ngay khi không còn lý do tồn tại.
