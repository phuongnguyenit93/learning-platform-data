# Khóa account trong Leaver lifecycle của IAM

> **Chương: Leaver lifecycle.** Khi nhân viên, nhà thầu hoặc một chủ thể không còn đủ điều kiện truy cập, quy trình **Leaver** phải ngăn việc tiếp tục sử dụng các tài khoản có liên quan. **Khóa account** là một nhóm hành động kiểm soát truy cập tại hệ thống đích, không đơn thuần là đổi trạng thái danh tính trong cơ sở dữ liệu IAM. Việc khóa hiệu quả cần kết hợp nguồn sự kiện đáng tin cậy, thời điểm hiệu lực, IdP/SSO, SCIM, chính sách phân quyền, phiên, token, thông tin xác thực và bước xác minh trạng thái thực tế.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **account lock, disable, suspend, deprovision, delete** và **revoke session/token/credential** trong vòng đời danh tính.
2. Xác định sự kiện Leaver, thời điểm khóa và tập tài khoản thuộc cùng một identity mà quy trình cần xử lý.
3. Thiết kế luồng khóa từ HR hoặc nguồn hợp đồng đến IdP, ứng dụng SaaS, hệ thống nội bộ và tài khoản đặc quyền.
4. Giải thích vì sao **khóa đăng nhập SSO** chưa chắc loại bỏ ngay các phiên, token hoặc khóa truy cập đã cấp.
5. Thiết lập retry, đối soát, chống kích hoạt lại bởi sự kiện cũ và kiểm toán kết quả thu hồi.
6. Xử lý ngoại lệ an toàn cho bàn giao nghiệp vụ, tài khoản dịch vụ, break-glass và khôi phục truy cập hợp lệ.

## 1. Khóa account nghĩa là gì?

Trong IAM (**Identity and Access Management — quản lý danh tính và truy cập**), account là bản ghi người dùng hoặc chủ thể tại một hệ thống cụ thể, chẳng hạn IdP, email, Git, CRM, VPN, cloud hay ứng dụng nhân sự. Một identity nghiệp vụ có thể liên kết với nhiều account. **Leaver** là giai đoạn kết thúc quan hệ sử dụng khiến những quyền không còn được phép phải bị thu hồi.

**Khóa account** trong ngữ cảnh Leaver là việc thực hiện các biện pháp để **tài khoản không còn có thể tạo hoặc duy trì truy cập trái chính sách** kể từ thời điểm hiệu lực. Tùy khả năng hệ thống đích, biện pháp có thể là vô hiệu hóa account, ngừng xác thực, gỡ membership, loại bỏ đặc quyền, rút phiên hoặc vô hiệu hóa credential.

Trước khi triển khai, cần phân biệt thuật ngữ bởi các sản phẩm có thể dùng từ **lock** cho nhiều hành vi:

| Thao tác | Ý nghĩa thông thường | Giới hạn cần kiểm tra |
| --- | --- | --- |
| **Lock account** | Chặn một kiểu đăng nhập, có thể do sai mật khẩu hoặc do quản trị viên khóa. | Có thể chỉ tạm thời; API token, SSO hoặc phiên cũ vẫn hoạt động tùy ứng dụng. |
| **Disable / deactivate** | Đánh dấu tài khoản không hoạt động, ngăn các hình thức truy cập được sản phẩm kiểm soát. | Hành vi với phiên, token và API key tùy sản phẩm. |
| **Suspend** | Tạm đình chỉ truy cập, có thể phục hồi khi có quyết định hợp lệ. | Có thể khác disable về xử lý dữ liệu, license và phiên. |
| **Deprovision** | Gỡ tài khoản khỏi phạm vi quản lý hoặc thu hồi các liên kết/quyền theo quy trình cấp phát. | Không nhất thiết xóa hoàn toàn bản ghi ở ứng dụng đích. |
| **Delete** | Xóa tài khoản/bản ghi hoặc yêu cầu xóa theo chức năng hệ thống. | Có thể ảnh hưởng ownership, bằng chứng, dữ liệu nghiệp vụ và khả năng khôi phục. |
| **Revoke sessions/tokens** | Chấm dứt hoặc vô hiệu hóa chứng cứ truy cập đã phát hành. | Token tự chứa có thể chỉ hết hiệu lực theo hạn hoặc cơ chế kiểm tra riêng. |
| **Revoke credentials** | Hủy khóa, chứng chỉ, mật khẩu, API key hay phương thức đăng nhập liên quan. | Phải xác định credential thuộc ai, có đang được hệ thống khác dùng chung không. |

**Không lấy tên API làm bằng chứng đã khóa an toàn.** Một endpoint có tên “lock” có thể chỉ vô hiệu hóa đăng nhập bằng mật khẩu, trong khi hệ thống vẫn chấp nhận API token hoặc phiên đã đăng nhập. Thiết kế cần mô tả **hành vi bảo mật được mong đợi và cách kiểm tra nó** tại từng hệ thống.

### Khóa danh tính, khóa account và thu hồi quyền

Ba lớp có liên quan nhưng không đồng nhất:

1. **Identity lifecycle state:** IAM ghi nhận một người đã rời tổ chức, ví dụ **TERMINATED** theo nguồn HR. Đây là quyết định quản trị danh tính.
2. **Account state:** IdP, Git, CRM, VPN hoặc cloud account phải chuyển sang trạng thái không còn cho phép những truy cập đã bị chấm dứt.
3. **Effective access:** phiên, token, nhóm lồng nhau, quyền cục bộ, credential và các đường truy cập trực tiếp phải thực sự không còn mang lại quyền trái chính sách.

Một tài khoản có thể được đánh dấu “disabled” nhưng phiên cũ vẫn còn hiệu lực. Ngược lại, chỉ gỡ một role có thể làm mất quyền dữ liệu mà chưa ngăn được đăng nhập. **Mục tiêu cuối là trạng thái truy cập thực tế**, không phải một trường trạng thái được cập nhật thành công.

## 2. Khi nào cần khóa account?

Leaver phải được kích hoạt bởi một sự kiện đáng tin cậy, có **chủ thể, nguồn, thời điểm hiệu lực và phạm vi rõ ràng**.

| Sự kiện | Nguồn có thể có thẩm quyền | Điều IAM phải làm |
| --- | --- | --- |
| Nhân viên nghỉ việc theo lịch | HRIS/HCM | Lập lịch thu hồi tại thời điểm có hiệu lực; xác minh lịch không bị thay thế. |
| Kết thúc hợp đồng nhà thầu | Hệ thống hợp đồng, sponsor/owner được ủy quyền | Chấm dứt account và quyền theo thời hạn; không phụ thuộc vào việc sponsor nhớ thông báo. |
| Nghỉ việc có hiệu lực ngay | HR hoặc người có thẩm quyền theo quy trình khẩn cấp | Ưu tiên chặn truy cập và kiểm tra toàn bộ đường truy cập đang hoạt động. |
| Quyết định đình chỉ truy cập tạm thời | Security/HR theo quy trình được phê duyệt | Dùng trạng thái tạm thời đúng phạm vi; giữ bằng chứng và điều kiện mở lại. |
| Chấm dứt quan hệ đối tác | Chủ sở hữu hợp đồng/tổ chức đối tác | Xác định những identity và account thuộc quan hệ đó. |
| Workload hoặc dịch vụ ngừng hoạt động | Service registry, owner kỹ thuật, hệ thống triển khai | Thu hồi service identity, credential, role và trust relationship theo vòng đời máy. |

Không nên dựa vào **email thông báo nghỉ việc** làm nguồn duy nhất nếu chưa có cơ chế xác minh người gửi và thời điểm hiệu lực. Các trường cần thiết gồm định danh ổn định, loại quan hệ, trạng thái mới, mốc hiệu lực, mã sự kiện, phiên bản dữ liệu nguồn và correlation ID.

### Mốc thời gian quan trọng

- **Thông báo:** lúc HR ghi nhận hoặc công bố sự kiện Leaver.
- **Hiệu lực:** lúc quan hệ/quyền truy cập phải kết thúc theo chính sách.
- **Bắt đầu thực thi:** lúc workflow khóa được khởi chạy.
- **Hoàn thành ở từng đích:** lúc account, quyền, phiên và credential được xử lý tại một hệ thống.
- **Xác minh:** lúc hệ thống đọc lại và chứng minh trạng thái đích đáp ứng điều kiện thu hồi.

Không nhầm **thời điểm nhận webhook** với **thời điểm hiệu lực**. Nếu Leaver có hiệu lực trước khi hệ thống nhận sự kiện, IAM cần xử lý theo độ ưu tiên và ghi nhận độ trễ. Nếu đã biết một Leaver trong tương lai, có thể chuẩn bị danh sách đích và kiểm tra dữ liệu trước, nhưng phải đảm bảo mốc khóa phù hợp chính sách.

### Múi giờ, ngày hiệu lực và giới hạn quyền

Ví dụ, nguồn HR ghi **2026-12-01T17:00:00+07:00**. Scheduler chạy ở UTC cần xử lý đúng thời điểm tuyệt đối, đồng thời giữ múi giờ nghiệp vụ để đối chiếu. Một ngày lịch không có giờ hoặc timezone phải được diễn giải bằng quy tắc được phê duyệt, không mặc định 00:00 UTC.

Nếu hợp đồng kết thúc ngay trước một ca đêm, quy tắc thời gian phải đủ chính xác để tránh cả khóa sớm gây gián đoạn hợp lệ lẫn khóa muộn tạo quyền tồn dư.

## 3. Xác định tất cả tài khoản cần khóa

Trước hoặc ngay khi Leaver có hiệu lực, IAM cần liên kết **một identity nguồn với mọi account và đường truy cập thực tế**. Chỉ lấy danh sách nhóm từ IdP thường chưa đủ.

~~~mermaid
flowchart TD
    HR["Nguồn HR/hợp đồng<br/>Leaver có hiệu lực"] --> IAM["Identity IAM<br/>ID ổn định + mapping"]
    IAM --> IDP["IdP User<br/>SSO và nhóm"]
    IAM --> SAAS["SaaS account<br/>CRM, Git, email"]
    IAM --> LOCAL["Tài khoản cục bộ<br/>VPN, máy chủ, DB"]
    IAM --> PRIV["Đặc quyền/PAM<br/>admin role và session"]
    IAM --> KEY["Credential trực tiếp<br/>API key, SSH key, cert"]
    IDP --> AUD["Đối soát trạng thái và quyền"]
    SAAS --> AUD
    LOCAL --> AUD
    PRIV --> AUD
    KEY --> AUD
~~~

### Kiểm kê theo nguồn và danh tính ổn định

Mỗi account nên có:

| Thuộc tính | Ví dụ minh họa | Mục đích |
| --- | --- | --- |
| Identity IAM | ID-8F31 | Liên kết mọi account của một chủ thể nghiệp vụ. |
| Source key | HRIS-A:EMP-2041 | Xác minh đúng người khi nhận Leaver. |
| Target system | Corporate IdP, Git, CRM | Xác định nơi phải thực thi. |
| Local account ID | idp-u728, git-u310 | Tác động đúng tài khoản trong namespace đích. |
| Account type | Workforce, admin, local, service | Chọn cách vô hiệu hóa phù hợp. |
| Effective entitlements | Role, group, policy, scope | Biết quyền cần thu hồi và đường truy cập còn lại. |
| Credential/session references | ID khóa, session handle khi có | Truy vết kênh cần rút quyền riêng. |
| Owner và trạng thái thực tế | Resource owner, ENABLED | Chuyển lỗi đúng người xử lý và đối soát. |

**Email và display name không phải khóa duy nhất đáng tin cậy**: email có thể đổi hoặc được tái cấp cho người khác. Khi mapping chưa rõ, cần điều tra có kiểm soát để tránh khóa nhầm người, đồng thời giảm rủi ro trong những đường truy cập đã xác minh là thuộc subject cần thu hồi.

### Những account dễ bị bỏ sót

1. Tài khoản nội bộ không đăng nhập qua SSO, kể cả tài khoản ứng dụng được tạo thủ công.
2. Tài khoản quản trị riêng mà một người dùng ngoài account làm việc thường ngày.
3. Quyền truy cập cloud theo IAM role/group, nhóm lồng nhau hoặc trust relationship.
4. Khóa API cá nhân, SSH key, chứng chỉ client, PAT của công cụ mã nguồn và token tự cấp.
5. Credential được lưu trong công cụ tự động hóa hoặc trên thiết bị đã được giao.
6. Phiên VPN, ứng dụng web, công cụ quản trị hoặc thiết bị vẫn còn phiên hợp lệ.
7. Tài khoản trong ứng dụng chưa tích hợp SCIM, có quy trình thu hồi thủ công.
8. Quyền xem dữ liệu theo quan hệ quản lý, nhóm dự án hoặc thuộc tính ABAC đã lỗi thời.

Nếu một account có thể phục vụ **nhiều chủ thể hoặc một dịch vụ dùng chung**, không được xóa hoặc khóa tùy tiện gây ngừng hoạt động hệ thống. Cần xác định người sử dụng, owner, phạm vi quyền và phương án **chuyển ownership hoặc xoay vòng credential** để loại bỏ quyền của người rời đi.

## 4. Quy trình khóa account từ đầu đến cuối

Một quy trình Leaver có thể gồm bảy giai đoạn liên kết:

### Giai đoạn 1 — Tiếp nhận và xác minh Leaver

Kiểm tra nguồn có thẩm quyền, identity nguồn, trạng thái, ngày hiệu lực, phiên bản và quyền của tác nhân gửi sự kiện. Nếu cùng mã sự kiện được gửi lại, workflow phải idempotent. Nếu sự kiện có xung đột hoặc định danh mơ hồ, chuyển xử lý theo mức rủi ro thay vì tự khóa một tài khoản có tên tương tự.

### Giai đoạn 2 — Xác định tập account và quyền

Nối identity IAM với local account ID của từng đích, nhận diện các đường truy cập không qua IdP và phân loại ưu tiên: đặc quyền, dữ liệu nhạy cảm, VPN/cloud, ứng dụng nghiệp vụ, kênh phục vụ onboarding hoặc dịch vụ máy.

Nếu doanh nghiệp đã chuẩn bị Leaver trước ngày hiệu lực, có thể kiểm kê các đích từ trước để giảm thời gian xử lý nhưng vẫn phải **đọc trạng thái mới nhất** ở thời điểm khóa.

### Giai đoạn 3 — Chặn truy cập theo hiệu lực

Tại mốc được phép, vô hiệu hóa hoặc suspend khả năng đăng nhập ở IdP và các hệ thống đích. Đồng thời áp dụng các chính sách deny/thu hồi role cần thiết tại những đường truy cập trực tiếp nếu hệ thống hỗ trợ. Với tình huống rủi ro cao, có thể cần phối hợp IAM, Security, chủ sở hữu hệ thống và quy trình phản ứng sự cố.

Việc khóa phải đảm bảo **không tái kích hoạt bởi job Joiner/Mover cũ**. Quy trình Leaver có hiệu lực phải được ưu tiên trong vòng đời danh tính; scheduler, connector và retry phải xem trạng thái hiện hành trước khi ghi.

### Giai đoạn 4 — Chấm dứt phiên và credential

Kiểm tra khả năng thu hồi refresh token, session, access token, API key, SSH key, chứng chỉ, phiên VPN và thông tin xác thực cục bộ. Có thể cần thao tác riêng ở IdP, ứng dụng, thiết bị hoặc hệ thống quản lý secrets.

Đặc biệt, **token bearer tự chứa còn hạn** có thể tiếp tục được ứng dụng chấp nhận cho tới khi hết hạn nếu ứng dụng không kiểm tra danh sách thu hồi hoặc trạng thái phiên tại điểm sử dụng. Phải xác định cơ chế kiểm soát thực tế, thời hạn token và biện pháp giảm thiểu phù hợp.

### Giai đoạn 5 — Gỡ quyền và xử lý tài nguyên liên quan

Thu hồi vai trò, group membership, ACL, đặc quyền, quyền dự án và các liên kết truy cập khác. Xác định các tài sản do account sở hữu, chẳng hạn repository, lịch chạy, mailbox nghiệp vụ, báo cáo, ticket, license, automation và khóa tích hợp, rồi bàn giao theo chính sách.

**Không mở lại account của người đã rời đi để nhân viên khác tiếp tục làm việc.** Việc bàn giao dữ liệu hoặc nhiệm vụ cần sử dụng cơ chế quản trị, tài khoản hợp lệ của người tiếp nhận và bằng chứng phê duyệt phù hợp.

### Giai đoạn 6 — Đọc lại và đối soát trạng thái đích

Từng hệ thống cần trả về hoặc được truy vấn để xác định:

- Account được xác định đúng local ID và trạng thái đăng nhập không còn hợp lệ.
- Vai trò/nhóm/quyền liên quan đã được gỡ hoặc vô hiệu hóa đúng phạm vi.
- Session, token và credential được xử lý theo khả năng đích; phần chưa thể rút ngay có hạn hết hiệu lực và kiểm soát bù.
- Quyền ở hệ thống trực tiếp, account quản trị và dữ liệu thuộc phạm vi Leaver không còn đường truy cập ngoài chính sách.
- Các thay đổi có kết quả **VERIFIED**, **FAILED**, **PENDING** hoặc **EXCEPTION** rõ ràng; không chỉ ghi “request sent”.

### Giai đoạn 7 — Kiểm toán và xử lý phần còn lại

Ghi lại từng hành động, người hoặc hệ thống thực thi, thời điểm, kết quả, nguyên nhân thất bại và owner xử lý. Những đích chưa đạt phải được retry hoặc chuyển xử lý thủ công theo quy trình; không công bố hoàn tất thu hồi toàn bộ khi còn đường truy cập chưa được kiểm chứng.

~~~mermaid
flowchart TD
    A["HR / nguồn có thẩm quyền<br/>Leaver effectiveAt"] --> B["Validate identity, version<br/>và phạm vi account"]
    B --> C["Chặn xác thực/đăng nhập<br/>tại IdP và account đích"]
    C --> D["Thu hồi nhóm, đặc quyền,<br/>session, token, credential"]
    D --> E["Readback từng hệ thống<br/>desired vs observed"]
    E --> F{"Tất cả đích bắt buộc<br/>đã xác minh?"}
    F -->|Có| G["LEAVER_ACCESS_REVOKED<br/>lưu bằng chứng"]
    F -->|Không| H["PARTIAL_FAILURE<br/>cảnh báo, retry/owner"]
    H --> E
~~~

*Sơ đồ minh họa. Tùy khả năng API và yêu cầu xử lý sự cố, các hành động khóa, thu hồi token và gỡ quyền có thể chạy song song hoặc theo thứ tự khác; luôn ưu tiên ngăn truy cập có rủi ro và kiểm chứng kết quả.*

## 5. IdP, SSO, SCIM và giới hạn khi khóa account

### IdP và SSO

IdP (**Identity Provider**) thường đảm nhiệm xác thực và cung cấp dịch vụ đăng nhập liên thông. **SSO (Single Sign-On)** cho phép người dùng truy cập nhiều ứng dụng được liên kết qua một cơ chế đăng nhập tin cậy, thường dùng OIDC hoặc SAML.

Khi IdP User bị vô hiệu hóa, các yêu cầu **đăng nhập mới qua IdP** có thể bị ngăn theo chính sách. Tuy nhiên:

- Ứng dụng có thể còn phiên cục bộ đã hình thành trước đó.
- Access token đã cấp có thể còn hạn và không liên hệ lại IdP ở mọi yêu cầu.
- Ứng dụng có thể cho đăng nhập trực tiếp bằng mật khẩu riêng hoặc API key.
- Một số hệ thống duy trì cookie, session hoặc cache quyền độc lập với IdP.

Vì vậy, **khóa IdP là bước quan trọng nhưng chưa đủ** để chứng minh Leaver đã mất mọi quyền truy cập.

### SCIM và account ứng dụng

**SCIM (System for Cross-domain Identity Management)** thường được dùng để tạo, cập nhật, vô hiệu hóa User/Group tại service provider. Ví dụ, nếu đích hỗ trợ cập nhật thuộc tính **active**, provisioning engine có thể gửi yêu cầu đổi **active** từ **true** sang **false**.

Ví dụ payload cập nhật dạng SCIM PatchOp (minh họa, đích phải hỗ trợ phương thức và schema tương ứng):

~~~http
PATCH /scim/v2/Users/target-user-42 HTTP/1.1
Content-Type: application/scim+json
Authorization: Bearer [REDACTED]

{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:PatchOp"
  ],
  "Operations": [
    {
      "op": "replace",
      "path": "active",
      "value": false
    }
  ]
}
~~~

**Lưu ý:** Đây chỉ là ví dụ cách thể hiện yêu cầu; không áp dụng nguyên dạng cho mọi sản phẩm. SCIM dùng để quản lý tài khoản/nhóm và **không bảo đảm** tự thu hồi toàn bộ session, access token, key hay entitlement cục bộ. Trước khi đánh dấu thành công, cần kiểm tra phản hồi và đọc lại trạng thái theo hợp đồng của từng ứng dụng.

### Quyền RBAC/ABAC vẫn cần được kiểm soát

| Thành phần | Vai trò trong Leaver | Điều cần xác minh |
| --- | --- | --- |
| **IdP** | Chặn xác thực mới, quản lý group và các session được IdP kiểm soát. | Account đã vô hiệu hóa; cơ chế session/token áp dụng ra sao. |
| **SSO / OIDC / SAML** | Liên kết đăng nhập vào ứng dụng. | Phiên ứng dụng tạo từ lần SSO cũ có còn sử dụng được không. |
| **SCIM/API provisioning** | Chuyển account/nhóm ở đích sang trạng thái phù hợp. | Đích đã áp dụng thay đổi, không có lỗi một phần hoặc quyền cục bộ. |
| **RBAC** | Gỡ role và các quyền gắn với vai trò. | Quyền kế thừa từ nhóm khác hoặc role trực tiếp có còn không. |
| **ABAC** | Từ chối thao tác theo thuộc tính, ví dụ trạng thái làm việc. | Ứng dụng dùng thuộc tính đủ mới, nguồn đáng tin và kiểm tra tại điểm sử dụng. |
| **PAM** | Rút quyền đặc quyền và phiên quản trị. | Không còn phiên JIT/admin hoặc credential đặc quyền sử dụng được. |
| **Audit/monitoring** | Chứng minh trạng thái thực tế sau thu hồi. | Log đầy đủ và cảnh báo các đích chưa đạt. |

**RBAC/ABAC không tự thay thế khóa account.** Một User có thể đã mất vai trò nghiệp vụ nhưng vẫn đăng nhập và sử dụng chức năng khác; ngược lại, một account bị disable có thể còn token cũ trong một ứng dụng không kiểm tra trạng thái người dùng. Thiết kế cần kết hợp các lớp theo mức rủi ro.

## 6. Điều phối, idempotency và chống tái kích hoạt

Quy trình Leaver thường trải qua nhiều hệ thống, không có giao dịch nguyên tử duy nhất. Một số lệnh sẽ timeout, lỗi tạm thời hoặc trả kết quả không rõ ràng. Để tránh **quyền truy cập tồn dư**, cần tổ chức workflow có trạng thái và đối soát.

### Mô hình trạng thái gợi ý

| Trạng thái nội bộ | Ý nghĩa | Hành động tiếp theo |
| --- | --- | --- |
| **LEAVER_SCHEDULED** | Đã có sự kiện kết thúc trong tương lai. | Chuẩn bị inventory, chờ mốc hợp lệ và theo dõi cập nhật. |
| **LEAVER_EFFECTIVE** | Nguồn xác nhận kết thúc đã có hiệu lực. | Khởi chạy kiểm soát thu hồi theo ưu tiên. |
| **BLOCKING_ACCESS** | Đang chặn đăng nhập và quyền tại các hệ thống. | Theo dõi kết quả theo đích. |
| **REVOKING_CREDENTIALS** | Đang rút phiên, token, khóa và các đường truy cập. | Đối soát từng nguồn phát hành và nơi sử dụng. |
| **VERIFYING** | Đọc lại trạng thái quyền thực tế. | Đánh giá tiêu chí hoàn thành. |
| **PARTIAL_FAILURE** | Một hoặc nhiều đích chưa chứng minh đã thu hồi. | Cảnh báo, retry, owner, kiểm soát bù. |
| **REVOKED_VERIFIED** | Các điều kiện bắt buộc đã được kiểm chứng. | Bàn giao, lưu hồ sơ, rà soát ngoại lệ. |
| **EXCEPTION_TRACKED** | Một vấn đề không thể xử lý ngay nhưng có kiểm soát riêng. | Theo dõi hạn, rủi ro, biện pháp bù và người chịu trách nhiệm. |

Đây là **mô hình thiết kế minh họa**, không phải trạng thái chuẩn của SCIM hay IdP. Không chuyển toàn bộ workflow sang trạng thái hoàn tất chỉ vì một API trả mã thành công.

### Pseudocode xử lý Leaver

~~~text
processLeaver(event):
    assert sourceIsAuthorized(event.source)
    assert event.subjectKey has stableNamespace

    identity = resolveIdentity(event.subjectKey)
    if identity is ambiguous:
        openHighPriorityReview(event)
        return REVIEW_REQUIRED

    latest = loadCurrentAuthoritativeState(identity)
    if event.version is stale relative to latest:
        return SUPERSEDED
    if currentTime < latest.leaverEffectiveAt:
        scheduleWithVersionGuard(identity, latest)
        return SCHEDULED

    desired = computeLeaverAccessState(identity, latest)
    preventStaleJoinerMoverReactivation(identity, latest.version)

    targets = discoverAccountsAndCredentials(identity)
    for each target in targets:
        result = blockAndRevokeIdempotently(target, desired)
        recordTargetResult(identity, target, result)

    verified = readBackEffectiveAccess(targets)
    recordAudit(identity, latest, verified)

    if verified.allMandatoryTargetsPass:
        return REVOKED_VERIFIED
    alertOwnersAndReconcile(verified.failures)
    return PARTIAL_FAILURE
~~~

Đoạn mã minh họa các yêu cầu nghiệp vụ. Khi xây dựng sản phẩm thật cần kiểm tra quyền của caller, concurrency, transaction, giới hạn retry, timeout, thiết kế API và xử lý trường hợp không thể kiểm tra hoàn toàn trạng thái token.

### Tại sao cần version và idempotency?

Giả sử:

1. HR gửi **Joiner**, IAM bắt đầu tạo Git User nhưng API timeout.
2. HR gửi **Leaver** có hiệu lực; IAM khóa IdP và Git User.
3. Một worker retry job Joiner cũ và bất ngờ bật lại Git User.

Lỗi nằm ở việc retry **không kiểm tra trạng thái nguồn hiện hành**. Cách khắc phục:

- Mỗi job mang identityId, source/version và loại thao tác.
- Mọi lệnh cấp/bật quyền phải kiểm tra Leaver đã có hiệu lực hay chưa.
- Dùng cập nhật có điều kiện hoặc cơ chế khóa đồng thời để ngăn job cũ ghi đè.
- Khi timeout, đọc lại đích trước khi thử lại; thao tác khóa lặp phải an toàn.
- Hệ thống reconciliation kiểm tra desired state là **không còn truy cập** và tiếp tục phát hiện quyền được mở lại ngoài ý muốn.

**Không chỉ dựa vào thứ tự nhận webhook** vì mạng và hàng đợi có thể làm sự kiện đến trễ hoặc sai thứ tự. Cần dùng version hoặc thời điểm hiệu lực đáng tin cậy từ nguồn.

## 7. Xử lý phiên, token và credential còn hiệu lực

Một trong những nhầm lẫn quan trọng nhất là cho rằng đổi trạng thái User tại IdP sẽ hủy ngay toàn bộ khả năng truy cập đã tồn tại.

### Access token và refresh token

- **Refresh token** thường cho phép lấy token mới. Nếu hệ thống hỗ trợ, việc thu hồi nó giúp chặn gia hạn phiên, nhưng không mặc nhiên hủy access token đã phát hành.
- **Access token tự chứa** có thể được ứng dụng kiểm tra chữ ký và thời hạn mà không gọi lại IdP. Nếu không có cơ chế kiểm tra trạng thái/denylist hoặc token binding phù hợp, token này có thể còn hiệu lực tới thời điểm hết hạn.
- **Token opaque** có thể được kiểm tra qua hệ thống introspection tùy kiến trúc, giúp áp dụng trạng thái thu hồi tại điểm sử dụng nếu triển khai đúng.
- **Session cookie** tại ứng dụng hoặc gateway có thể độc lập với token gốc và cần cơ chế logout/revoke riêng.

Không có một lệnh tổng quát “revoke all” hoạt động giống nhau trên mọi IdP và SaaS. Quy trình cần lập tài liệu chính xác về token lifetime, nơi xác minh token, cách rút session và khoảng tồn dư tối đa được chính sách chấp nhận.

### Credential truy cập trực tiếp

Ngay cả khi SSO bị khóa, các đường sau có thể tồn tại:

| Credential/đường truy cập | Ví dụ | Phương án xử lý |
| --- | --- | --- |
| **Personal API token (PAT)** | Token Git, automation cá nhân. | Thu hồi token của người rời đi, xác minh job liên quan có chủ mới. |
| **API key** | Khóa gọi dịch vụ từ script của nhân viên. | Xác định owner, thu hồi/rotate và xử lý các tích hợp phụ thuộc. |
| **SSH key** | Khóa truy cập máy chủ, repository. | Gỡ authorized key và quyền gắn với tài khoản, kiểm tra đường truy cập khác. |
| **Client certificate** | Chứng chỉ dùng với VPN hoặc mTLS. | Thu hồi/loại khỏi trust khi cần; xác minh sản phẩm đích đánh giá hiệu lực thu hồi. |
| **Local password** | Tài khoản database/app không tích hợp SSO. | Disable account hoặc đổi credential theo chính sách và kiểm chứng. |
| **Privileged session** | Phiên quản trị PAM/JIT. | Kết thúc phiên và thu hồi quyền nâng cao; lưu bằng chứng thích hợp. |

Việc rút credential **dùng chung** cần kế hoạch thay thế, vì thu hồi ngẫu nhiên có thể khiến ứng dụng quan trọng ngừng hoạt động. Tuy nhiên, duy trì credential dùng chung mà người nghỉ việc vẫn biết cũng là rủi ro; cần chuyển sang owner, credential riêng và xoay vòng có kiểm soát.

## 8. Quyền tối thiểu, bàn giao dữ liệu và tài khoản đặc biệt

### Bàn giao nghiệp vụ không phải lý do giữ account của Leaver

Trước khi người dùng rời đi, tổ chức có thể cần chuyển:

- Ownership repository, lịch chạy CI/CD, project hoặc hệ thống trực.
- Ticket, hồ sơ khách hàng, công việc đang phê duyệt, lịch và dữ liệu nghiệp vụ.
- Vai trò owner của ứng dụng, nhóm, tài khoản dịch vụ hoặc kho secrets.
- Thông tin liên hệ nghiệp vụ, hợp đồng, tài liệu và hồ sơ cần lưu theo chính sách.

**Người tiếp nhận phải dùng danh tính của chính mình** và chỉ nhận quyền cần thiết. Không dùng mật khẩu hoặc tài khoản của Leaver để tiếp tục xử lý thay họ; cách làm đó phá hỏng truy vết và có thể duy trì đường truy cập không hợp lệ.

### Service account và workload identity

Không nên tự động khóa mọi service account do một nhân viên tạo nếu chúng vẫn phục vụ hệ thống hợp lệ. Thay vào đó:

1. Kiểm kê service account/workload do người rời đi tạo, quản lý hoặc nắm giữ credential.
2. Xác nhận owner và mục đích hiện tại của từng identity máy.
3. Chuyển owner, điều chỉnh quyền theo công việc, thu hồi credential cá nhân liên quan và rotate bí mật bị người rời đi biết.
4. Loại bỏ service account không còn workload hoặc hợp đồng hợp lệ.
5. Xác minh ứng dụng vẫn chạy với identity và quyền phù hợp, không dựa vào account cá nhân đã nghỉ việc.

### Tài khoản quản trị và break-glass

User có thể có một account thường ngày và một account quản trị riêng. Cả hai cần được liên kết với cùng người và xử lý trong Leaver. Hãy kiểm tra cả membership cloud admin, PAM/JIT role, session quản trị và quyền ứng dụng không qua SSO.

**Break-glass account** phải được quản lý bằng chính sách đặc biệt, owner rõ ràng và kiểm toán. Nếu người rời đi từng biết credential hoặc có quyền quản lý tài khoản khẩn cấp, cần áp dụng biện pháp thu hồi/rotate và chuyển quyền quản trị phù hợp, thay vì xóa tùy tiện tài khoản khẩn cấp đang phục vụ khả năng ứng cứu.

### Xóa account hay chỉ disable?

Khóa quyền nên được tách khỏi quyết định **xóa dữ liệu**. Nhiều hệ thống cần giữ mã tham chiếu, log, hồ sơ kế toán, quyền sở hữu tài sản hoặc bằng chứng kiểm toán sau khi người dùng không còn đăng nhập.

Quy trình có thể chia:

1. **Ngừng truy cập đúng mốc** bằng các phương án chặn, revoke và xác minh.
2. **Bàn giao/retention** theo nhu cầu nghiệp vụ, pháp lý và bảo vệ dữ liệu.
3. **Xóa/anonymize** theo chính sách riêng khi đến hạn hoặc có căn cứ, có kiểm soát ảnh hưởng tới hệ thống phụ thuộc.

Disable một account có thể là bước thu hồi tức thời phù hợp hơn delete; tuy nhiên chính sách và đặc tính từng sản phẩm quyết định lựa chọn cuối cùng.

## 9. Các tình huống lỗi thường gặp

### Tình huống 1 — IdP bị khóa, CRM vẫn còn phiên

HR phát Leaver hiệu lực 17:00. IdP vô hiệu hóa User lúc 17:01 nhưng CRM vẫn chấp nhận cookie phiên được phát lúc 16:30.

**Vấn đề:** Điều kiện khóa ở IdP chưa ảnh hưởng tới phiên CRM đã tồn tại.

**Xử lý:** Xác định cơ chế chấm dứt session tại CRM, kiểm tra token lifetime và khả năng kiểm tra trạng thái User ở mỗi request. Bật biện pháp thu hồi/deny phù hợp, ghi nhận khoảng thời gian tồn dư và xác minh bằng cơ chế được phép. Không công bố “khóa toàn bộ” chỉ vì IdP trả thành công.

### Tình huống 2 — SCIM báo thành công nhưng account cục bộ còn hoạt động

Ứng dụng nhận yêu cầu active=false qua SCIM nhưng vẫn có một local admin account liên kết với cùng người.

**Vấn đề:** Phạm vi provisioning không bao phủ tài khoản quản trị cục bộ.

**Xử lý:** Duy trì inventory account ngoài luồng, gắn owner và local user ID; disable hoặc revoke local admin riêng, xác minh credential và session. Cảnh báo nếu inventory không đầy đủ.

### Tình huống 3 — API khóa thất bại giữa chừng

IdP và Git thành công nhưng CRM trả lỗi timeout. Lần chạy retry có nguy cơ gọi lại toàn bộ quy trình.

**Vấn đề:** Trạng thái một phần chưa được đối soát.

**Xử lý:** Ghi kết quả riêng từng đích; trước retry, đọc trạng thái CRM để xác định lệnh trước đã áp dụng chưa. Chỉ thao tác phần còn thiếu, tránh tạo/xóa nhầm dữ liệu. Giữ trạng thái **PARTIAL_FAILURE** cho tới khi xác minh.

### Tình huống 4 — Retry Joiner làm bật lại account

Một job Joiner cũ tạo account sau khi HR đã phát Leaver.

**Vấn đề:** Job không xét version/sự kiện hiệu lực hiện hành.

**Xử lý:** Mọi thao tác cấp quyền phải đọc desired lifecycle state mới nhất; Leaver có hiệu lực chặn kích hoạt. Dùng CAS/transaction và reconciliation để phát hiện, khắc phục đường truy cập mở lại.

### Tình huống 5 — Tài khoản dùng chung trên máy chủ

Nhân viên nghỉ việc từng biết mật khẩu của một service account dùng cho backup.

**Vấn đề:** Khóa account nhân viên không thay đổi credential của service account.

**Xử lý:** Chuyển owner, xoay vòng secret trong quy trình có kiểm soát, xác minh backup hoạt động bằng credential mới và gỡ đường truy cập của nhân viên đã nghỉ việc. Ưu tiên phân tách identity máy và dùng credential ngắn hạn khi nền tảng hỗ trợ.

### Tình huống 6 — Kết thúc hợp đồng nhưng thiếu thời điểm

Nguồn nhà thầu chỉ gửi ngày kết thúc mà không có timezone. Một connector hiểu là đầu ngày UTC, ứng dụng khác hiểu cuối ngày địa phương.

**Vấn đề:** Hệ thống có hai thời điểm khóa khác nhau, gây gián đoạn hoặc tồn dư.

**Xử lý:** Quy định cách chuyển ngày thành timestamp có timezone từ nguồn/chính sách, lưu thời điểm tuyệt đối và kiểm tra mốc thực thi của mọi hệ thống.

### Tình huống 7 — Bàn giao công việc chưa hoàn tất

Quản lý yêu cầu giữ account của nhân viên nghỉ việc thêm ba ngày để lấy tài liệu.

**Vấn đề:** Quyền truy cập của Leaver vượt thời điểm có hiệu lực, tăng rủi ro.

**Xử lý:** Khóa account theo chính sách và chuyển tài liệu qua quy trình quản trị có phê duyệt, truy vết người tiếp nhận. Nếu có ngoại lệ thực sự, phải có cơ sở thẩm quyền, phạm vi nhỏ, hạn rõ ràng, giám sát và đánh giá rủi ro; không kéo dài ngầm mọi quyền.

## 10. Kiểm toán, chỉ số và tiêu chí hoàn thành

### Những sự kiện cần ghi lại

Một hồ sơ offboarding có thể chứa:

| Dữ liệu | Ví dụ | Vai trò kiểm toán |
| --- | --- | --- |
| Identity và khóa nguồn | ID-8F31, HRIS-A:EMP-2041 | Xác định đúng chủ thể. |
| Loại, mã và phiên bản sự kiện | LEAVER, event-9021, version 43 | Chứng minh căn cứ và thứ tự nghiệp vụ. |
| Thời điểm hiệu lực | 2026-12-01T17:00:00+07:00 | Xác định hạn phải thu hồi. |
| Hệ thống và account đích | CRM:crm-u310, Git:git-u205 | Cho biết phạm vi đã xử lý. |
| Hành động | DISABLE_ACCOUNT, REVOKE_TOKEN, REMOVE_ROLE | Phân biệt lệnh khóa, rút session và gỡ quyền. |
| Trạng thái sau readback | VERIFIED, PENDING, FAILED, EXCEPTION | Chứng minh quyền thực tế ở đích. |
| Thời gian thực thi/xác minh | executedAt, verifiedAt | Đo thời gian truy cập tồn dư. |
| Người/đơn vị chịu trách nhiệm | Workflow actor, owner, reviewer | Quy trách nhiệm xử lý sai lệch. |
| Correlation ID | revoke-2041-v43 | Liên kết log xuyên nhiều dịch vụ. |

Ví dụ log khái niệm:

~~~json
{
  "eventType": "LEAVER_ACCESS_REVOCATION",
  "identityId": "ID-8F31",
  "sourceKey": "HRIS-A:EMP-2041",
  "sourceVersion": 43,
  "effectiveAt": "2026-12-01T17:00:00+07:00",
  "state": "PARTIAL_FAILURE",
  "targetResults": [
    {
      "target": "CORPORATE_IDP",
      "accountId": "idp-u728",
      "status": "VERIFIED"
    },
    {
      "target": "GIT",
      "accountId": "git-u205",
      "status": "VERIFIED"
    },
    {
      "target": "CRM",
      "accountId": "crm-u310",
      "status": "PENDING_RETRY"
    }
  ],
  "correlationId": "revoke-2041-v43"
}
~~~

Đây là schema minh họa, không phải một chuẩn event bắt buộc. Không ghi mật khẩu, access token đầy đủ, private key hay dữ liệu cá nhân không cần thiết vào log. Nhật ký cần được bảo vệ quyền đọc, tính toàn vẹn và thời hạn lưu giữ.

### Các chỉ số vận hành

| Chỉ số | Câu hỏi nó giúp trả lời |
| --- | --- |
| **Time to block** | Từ thời điểm Leaver có hiệu lực đến lúc các điểm xác thực quan trọng bị chặn là bao lâu? |
| **Time to verify revocation** | Mất bao lâu để các đích bắt buộc xác minh không còn truy cập? |
| **Residual access count** | Bao nhiêu đường truy cập còn hiệu lực sau thời điểm thu hồi? |
| **Partial failure rate** | Tỷ lệ offboarding có connector/tài khoản chưa xử lý xong? |
| **Orphan account count** | Có bao nhiêu account không có identity/owner hoặc còn hoạt động sau Leaver? |
| **Stale reactivation attempts** | Có bao nhiêu job Joiner/Mover cũ cố mở lại quyền đã thu hồi? |
| **Credential rotation backlog** | Bao nhiêu credential mà Leaver từng biết chưa được thay đổi theo chính sách? |
| **Exception overdue count** | Bao nhiêu ngoại lệ thu hồi đã quá hạn? |

Tổ chức nên đặt tiêu chí thời gian dựa trên mức độ nhạy cảm và rủi ro từng hệ thống. Không có một SLA cố định phù hợp cho mọi loại account hoặc trường hợp Leaver.

### Tiêu chí hoàn thành khóa account

Một Leaver chỉ nên được xem là đã **thu hồi truy cập theo phạm vi được xác minh** khi:

1. Danh tính nguồn, thời điểm có hiệu lực và mọi account được xử lý đều được đối sánh đáng tin cậy.
2. Các kênh đăng nhập mới và quyền cần thu hồi đã bị ngăn ở các hệ thống bắt buộc.
3. Phiên, token, API key, credential cục bộ và quyền đặc quyền được xử lý hoặc ghi rõ giới hạn kỹ thuật và kiểm soát bù có owner.
4. Trạng thái account, nhóm và quyền được đọc lại từ hệ thống đích, đối chiếu với trạng thái **desired: no unauthorized access**.
5. Không có job cũ hoặc workflow khác được phép tự mở lại quyền trái trạng thái Leaver hiện hành.
6. Lỗi một phần và ngoại lệ có trạng thái, người xử lý, cảnh báo và hạn giải quyết; không bị che bởi trạng thái thành công tổng.
7. Bằng chứng đã được lưu và dữ liệu nghiệp vụ/kiểm toán được bàn giao, giữ hoặc xóa đúng chính sách riêng.

Không nên gắn nhãn **VERIFIED** cho một đường truy cập mà hệ thống không cung cấp cơ chế kiểm tra. Khi đó cần mô tả bằng chứng gián tiếp, giới hạn xác minh và rủi ro còn lại.

## 11. Bài tập tự kiểm tra

**Câu 1.** Một nhân viên đã bị disable tại IdP nhưng ứng dụng SaaS vẫn chấp nhận session cookie cũ. Có thể nói Leaver đã hoàn tất không?

*Gợi ý:* Chưa. Cần xác minh cơ chế kết thúc phiên tại SaaS, quyền cục bộ và token còn hạn; đưa sai lệch vào workflow và kiểm tra kết quả.

**Câu 2.** Vì sao không nên xóa ngay mọi account khi nhận Leaver?

*Gợi ý:* Phải ưu tiên ngừng quyền truy cập, đồng thời giữ dữ liệu nghiệp vụ, tài sản, log và bằng chứng theo chính sách; xóa là một quyết định riêng có thể ảnh hưởng hệ thống phụ thuộc.

**Câu 3.** SCIM trả trạng thái cập nhật active=false thành công. Điều đó có chứng minh các PAT và phiên cũ đã vô hiệu không?

*Gợi ý:* Không mặc định. SCIM quản lý account/nhóm; cách revoke token, session và credential phụ thuộc vào ứng dụng.

**Câu 4.** Người nghỉ việc từng dùng chung một khóa API với job sản xuất. Nên xử lý thế nào?

*Gợi ý:* Xác định owner và các workload phụ thuộc; rotate/thu hồi credential có kiểm soát, chuyển quyền về identity máy phù hợp và xác minh hệ thống vẫn hoạt động.

**Câu 5.** HR phát Leaver trong lúc retry của Joiner chưa xong. Có thể để retry tiếp tục tạo account nếu nó mang event ID cũ?

*Gợi ý:* Không. Retry phải kiểm tra lifecycle state và phiên bản mới nhất; Leaver có hiệu lực chặn việc mở lại quyền.

**Câu 6.** Khóa tài khoản CRM thành công nhưng chưa truy vấn được trạng thái Git. Có nên báo trạng thái toàn bộ offboarding là VERIFIED?

*Gợi ý:* Không. Ghi trạng thái riêng cho Git là PENDING/UNVERIFIED, cảnh báo, retry và giữ bằng chứng về phạm vi thực sự đã xác minh.

**Câu 7.** Account admin riêng của nhân viên có phải xử lý khi họ rời công ty, ngay cả khi account thường đã bị khóa?

*Gợi ý:* Có. Cần kiểm kê và thu hồi mọi account gắn với cùng người, gồm đặc quyền, PAM/JIT, phiên, khóa và đường truy cập không qua SSO.

## Ghi nhớ

- **Khóa account** trong Leaver là kiểm soát để người rời tổ chức không còn truy cập trái chính sách; **disable, lock, suspend, delete, revoke token và revoke credential** có hành vi khác nhau.
- **Nguồn Leaver đáng tin, định danh ổn định và thời điểm hiệu lực rõ ràng** là nền tảng để khóa đúng người, đúng lúc.
- **IdP/SSO** giúp chặn đăng nhập liên thông; **SCIM/connector** giúp cập nhật User và nhóm ở đích; **RBAC/ABAC/PAM** kiểm soát quyền. Không lớp nào đơn lẻ đảm bảo mọi đường truy cập đã hết hiệu lực.
- Phải xét **session, access token, refresh token, khóa API, SSH key, tài khoản cục bộ và account đặc quyền**, kể cả những đường không đi qua IdP.
- **Idempotency, kiểm tra version/sự kiện mới nhất và reconciliation** ngăn retry Joiner/Mover cũ mở lại quyền sau Leaver.
- Chỉ ghi nhận thu hồi hoàn tất ở phạm vi đã **đọc lại và xác minh trạng thái thực tế**, kèm bằng chứng, owner xử lý lỗi một phần và kiểm soát quyền tồn dư.
