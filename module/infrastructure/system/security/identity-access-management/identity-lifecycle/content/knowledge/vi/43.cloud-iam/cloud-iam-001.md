# Cloud identity

**Chương:** Cloud IAM  
**Chủ đề:** Cloud identity  
**Phạm vi:** Quản lý vòng đời danh tính trong hệ thống Identity and Access Management (IAM), đặc biệt là các danh tính truy cập hạ tầng, nền tảng và ứng dụng trên đám mây.

## 1. Cloud identity là gì?

**Cloud identity** là danh tính số được một hệ thống tin cậy dùng để nhận biết và quản lý một chủ thể có thể truy cập tài nguyên đám mây. Chủ thể đó có thể là nhân viên, cộng tác viên, đối tác, người quản trị hoặc một workload như ứng dụng, máy ảo, container, pipeline CI/CD. Một danh tính được nhận diện qua định danh ổn định và các thuộc tính; hệ thống xác thực danh tính trước khi đánh giá quyền truy cập tương ứng.

Ví dụ, nhân viên đăng nhập vào bảng điều khiển cloud bằng tài khoản công ty; dịch vụ chạy trên Kubernetes gọi API lưu trữ thông qua workload identity; hệ thống CI/CD được cấp quyền triển khai phiên bản mới. Ba tình huống đều liên quan đến cloud identity nhưng **cách xác thực, cấp quyền và kết thúc vòng đời khác nhau**.

Trong module quản lý vòng đời danh tính (Identity Lifecycle), cloud identity cần được nhìn xuyên suốt quá trình **Joiner – Mover – Leaver (JML)**:

- **Joiner:** Xác minh người hoặc workload mới, thiết lập danh tính, cấp quyền ban đầu có căn cứ.
- **Mover:** Cập nhật nhóm, vai trò và quyền khi thay đổi bộ phận, dự án, chức trách hoặc môi trường.
- **Leaver:** Vô hiệu hóa danh tính không còn hợp lệ, thu hồi quyền, phiên đăng nhập và khóa truy cập phù hợp, kiểm tra quyền truy cập tồn dư.

Cloud identity không chỉ là một tài khoản đăng nhập. Một con người có thể được biểu diễn bằng tài khoản tại **Identity Provider (IdP)**, danh tính được liên kết trong nhiều cloud tenant/account, quyền thành viên nhóm và các phiên truy cập tạm thời. Vì vậy, tắt một tài khoản ở một vị trí chưa chắc đã xóa hết khả năng truy cập.

Sau bài này, người học có thể giải thích ranh giới giữa danh tính, xác thực và phân quyền; mô tả kết nối IdP–SSO–SCIM với cloud IAM; thiết kế luồng JML cho người dùng và workload; phát hiện quyền tồn dư; xác định bằng chứng kiểm toán cần giữ lại.

## 2. Các khái niệm phải phân biệt

| Khái niệm | Ý nghĩa | Ví dụ trong môi trường cloud |
| --- | --- | --- |
| **Identity (danh tính)** | Bản ghi đại diện cho một chủ thể; có định danh và thuộc tính | Nhân viên có mã nội bộ, tài khoản dịch vụ của ứng dụng |
| **Principal (chủ thể thực thi)** | Thực thể mà hệ thống đánh giá quyền trong một yêu cầu | User, role session, service account, workload principal |
| **Account (tài khoản)** | Bản ghi tại IdP, ứng dụng hoặc cloud provider | Tài khoản Entra ID, cloud-local user |
| **Credential (yếu tố chứng thực)** | Bằng chứng dùng để xác thực hoặc đổi lấy phiên truy cập | Passkey, MFA, private key, token ngắn hạn |
| **Authentication (xác thực)** | Kiểm tra chủ thể đang yêu cầu có đủ bằng chứng danh tính | Đăng nhập SSO kèm MFA |
| **Authorization (ủy quyền/phân quyền)** | Quyết định chủ thể được phép làm gì trên tài nguyên nào | Đọc bucket, triển khai ứng dụng, quản trị billing |
| **Entitlement (quyền được cấp)** | Đơn vị quyền hoặc khả năng truy cập đã gắn cho danh tính | Thành viên nhóm, role binding, quyền trên project |
| **Federation (liên kết danh tính)** | Cho phép hệ thống tin cậy danh tính đã xác thực bởi hệ thống khác | IdP doanh nghiệp cấp SAML assertion cho AWS |
| **Session (phiên truy cập)** | Trạng thái/tài liệu xác thực có hiệu lực trong khoảng thời gian nhất định | Cloud console session, STS temporary credentials |
| **Identity lifecycle (vòng đời danh tính)** | Quy trình hình thành, thay đổi, đình chỉ và kết thúc danh tính | JML, access review, thu hồi quyền khi nghỉ việc |

**Phân biệt quan trọng:** Identity giải quyết câu hỏi “ai hoặc cái gì?”, authentication giải quyết “đã chứng minh được danh tính chưa?”, authorization giải quyết “được làm hành động này trên tài nguyên này không?”. Một người đăng nhập thành công vẫn có thể bị từ chối thao tác nếu thiếu quyền cloud IAM.

### 2.1. Ba lớp có thể tồn tại đồng thời

1. **Nguồn dữ liệu gốc (source of truth):** Hệ thống nhân sự (HRIS) cho nhân viên; hệ thống quản lý đối tác cho cộng tác viên; kho khai báo workload, CMDB hoặc nền tảng phát hành cho danh tính máy. Nguồn gốc quyết định khi nào danh tính hợp lệ và ai sở hữu nó.
2. **Kho danh tính và IdP:** Lưu chủ thể, nhóm, thuộc tính, phương thức xác thực; đưa ra kết quả đăng nhập hoặc token cho các hệ thống tin cậy.
3. **Cloud IAM và ứng dụng đích:** Ánh xạ chủ thể/nhóm/thuộc tính sang role, policy, permission. Một số dịch vụ có tài khoản và quyền nội bộ cần được đồng bộ, kiểm tra riêng.

Không nên đồng nhất tài khoản tại IdP với tài khoản cloud-local: cloud provider có thể có chủ thể gốc, tài khoản khẩn cấp, service account hoặc role session tồn tại độc lập với nhân viên trên IdP. Các loại này cần được kiểm kê và có quy trình sở hữu.

## 3. Kiến trúc cloud identity trong doanh nghiệp

~~~mermaid
flowchart TD
    HR["HRIS / hệ thống nhân sự<br/>Trạng thái, bộ phận, mã định danh"] --> LC["Identity lifecycle / IGA<br/>JML, phê duyệt, đối soát"]
    LC --> IDP["IdP / Directory<br/>Tài khoản, nhóm, MFA, chính sách đăng nhập"]
    LC --> PROV["Provisioning / SCIM hoặc API<br/>Tạo, cập nhật, vô hiệu hóa"]
    IDP -->|"SSO: SAML / OIDC"| FED["Cloud federation / trust"]
    FED --> IAM["Cloud IAM<br/>Role, policy, scope, điều kiện"]
    PROV --> APP["Ứng dụng SaaS / tài khoản đích"]
    IAM --> RESOURCE["Tài nguyên: compute, storage, database, API"]
    REG["Workload registry / CI-CD<br/>Owner, môi trường, mục đích"] --> WI["Workload identity / federation<br/>Token hoặc credential ngắn hạn"]
    WI --> IAM
    IDP -.-> AUD["Log / SIEM / kiểm toán"]
    PROV -.-> AUD
    IAM -.-> AUD
    LC -.-> AUD
~~~

Sơ đồ mô tả các mối liên kết logic; sản phẩm thực tế có thể gộp nhiều thành phần. Ví dụ một nền tảng IGA có thể tự thực hiện provisioning, hoặc cloud provider có thể cung cấp cả thư mục danh tính và công cụ phân quyền.

Luồng truy cập người dùng thường diễn ra như sau:

1. HRIS xác nhận nhân viên đang hoạt động và chức trách hiện hành.
2. Hệ thống JML/IGA tạo hoặc cập nhật hồ sơ trong IdP, tính toán nhóm và yêu cầu phê duyệt quyền đặc biệt.
3. Người dùng xác thực tại IdP; IdP áp chính sách MFA, thiết bị, rủi ro đăng nhập nếu được cấu hình.
4. Thông qua federation/SSO, cloud tin cậy kết quả xác thực theo cấu hình trust; sau đó ánh xạ danh tính sang principal, role hoặc session.
5. Cloud IAM kiểm tra quyền theo chính sách và phạm vi tài nguyên tại thời điểm yêu cầu.
6. Hệ thống tập trung ghi nhận sự kiện đăng nhập, cấp/sửa/thu hồi quyền và hoạt động nhạy cảm để phục vụ đối soát và điều tra.

**Điểm kiểm soát:** Xác thực tập trung giúp quản lý đăng nhập; **phân quyền và thu hồi tại hệ thống đích vẫn phải được kiểm tra**. Nếu nhân viên nghỉ việc nhưng còn một access key độc lập, role binding trực tiếp hoặc session chưa hết hạn, SSO không tự động xử lý hết các đường truy cập đó.

## 4. Xác thực, SSO và liên kết danh tính trên cloud

### 4.1. SAML, OpenID Connect và OAuth 2.0

| Cơ chế | Vai trò phù hợp | Đầu ra thường gặp | Điểm cần kiểm soát |
| --- | --- | --- | --- |
| **SAML 2.0** | Federation/SSO, nhất là ứng dụng doanh nghiệp và cloud console | SAML assertion chứa subject, thời gian hiệu lực, audience, thuộc tính | Chữ ký, issuer, audience, thời hạn, ánh xạ role, cấu hình trust |
| **OpenID Connect (OIDC)** | Đăng nhập hiện đại trên web/mobile; federation | ID token, thường là JWT, mô tả sự kiện xác thực | issuer, audience, chữ ký, expiry, nonce/state theo luồng, subject |
| **OAuth 2.0** | Ủy quyền để client nhận quyền gọi API | Access token có phạm vi/scope hoặc quyền được cấp | Đúng đối tượng nhận token, scope, hạn dùng, bảo vệ token |

OIDC xây dựng trên OAuth 2.0 nhưng **ID token và access token có mục đích khác nhau**. ID token là thông tin xác thực dành cho client đúng audience; access token là phương tiện gọi resource server. Không dùng ID token thay cho access token khi một API yêu cầu access token.

Ví dụ, hệ thống kỹ thuật mở cloud console qua SAML SSO; pipeline triển khai có thể sử dụng OIDC token do CI/CD phát hành để đổi lấy quyền cloud tạm thời. Cả hai đều dùng mô hình tin cậy, nhưng pipeline là **workload** và cần hạn chế theo repository, nhánh, môi trường và vai trò được phép.

### 4.2. Ranh giới trust và phiên truy cập

Khi cấu hình federation, cần xác định:

- **Ai được tin cậy:** IdP/issuer, khóa ký và cơ chế xoay khóa, tenant hoặc tổ chức nguồn.
- **Token có dành cho hệ thống này không:** Audience, recipient, thời gian hiệu lực và các điều kiện của giao thức.
- **Chủ thể được ánh xạ ra sao:** Định danh ổn định, role/nhóm, thuộc tính được tin cậy; tránh nối danh tính chỉ bằng email có thể đổi hoặc tái sử dụng.
- **Phiên dùng được bao lâu:** Thời gian sống của phiên và credential, cách hủy phiên khi có sự cố, quy trình thu hồi đối với token đã phát hành.

Việc khóa tài khoản IdP thường ngăn **lần đăng nhập tiếp theo**, nhưng không bảo đảm mọi token hoặc session đã cấp đều mất hiệu lực ngay lập tức. Hành vi này phụ thuộc giao thức, cloud provider, cách cache và khả năng thu hồi session/token của dịch vụ. Quy trình Leaver phải có bước xác minh thực tế.

Đối với danh tính có quyền cao, ưu tiên **MFA chống lừa đảo qua phishing** (ví dụ passkey hoặc khóa bảo mật theo chính sách tổ chức), áp dụng điều kiện đăng nhập và cấp quyền quản trị trong thời gian cần thiết.

## 5. Cấp quyền: Cloud IAM, RBAC và ABAC

Cloud IAM là lớp ra quyết định truy cập tài nguyên. Một bản ghi danh tính tồn tại không đồng nghĩa với việc chủ thể có quyền. Quyền thường được tính từ **principal + action + resource + context**, sau đó bị giới hạn bởi chính sách cấp tổ chức, ranh giới quyền, deny rule hoặc điều kiện khác nếu nền tảng có hỗ trợ.

**Role-Based Access Control (RBAC)** gom quyền thành vai trò: ví dụ nhóm kỹ sư phát triển được đọc log của môi trường dev; người trực vận hành được triển khai tại một project cụ thể. **Attribute-Based Access Control (ABAC)** đánh giá thuộc tính của chủ thể, tài nguyên và ngữ cảnh: ví dụ chỉ cho phép đọc tài nguyên có nhãn dự án trùng với dự án được giao, nếu nền tảng cung cấp cơ chế tương ứng.

| Chiều kiểm soát | Mô hình yếu | Mô hình nên hướng tới |
| --- | --- | --- |
| Phạm vi | Quyền quản trị trên toàn tổ chức | Quyền theo account/project/subscription/resource cần dùng |
| Gắn quyền | Cấp trực tiếp từng người, khó truy vết | Nhóm/vai trò chuẩn, có owner và chính sách phê duyệt |
| Thời hạn | Quyền đặc biệt tồn tại vô hạn | Quyền tạm thời, hết hạn và rà soát định kỳ |
| Điều kiện | Dựa riêng trên tài khoản | Kết hợp xác thực mạnh, ngữ cảnh, thuộc tính phù hợp |
| Thu hồi | Xóa tài khoản là coi như hoàn tất | So sánh quyền mong muốn với quyền thực tế tại mọi hệ thống liên quan |

Một nguyên tắc là **least privilege**: cấp tập quyền tối thiểu để làm việc, trên phạm vi tối thiểu và thời gian tối thiểu. Tuy vậy, trong thực tế phải cân bằng khả năng vận hành: không tự động cấp mọi quyền theo thuộc tính HR nếu quyền đó thuộc nhóm nhạy cảm hoặc cần sự chấp thuận độc lập.

### 5.1. Ví dụ chính sách theo ngữ cảnh

Đây là **giả mã minh họa**, không phải cú pháp được mọi cloud provider chấp nhận:

~~~yaml
principal:
  type: workforce
  employmentStatus: active
  team: platform
resource:
  environment: dev
  project: platform-learning
request:
  action: logs.read
decision:
  permit_when:
    - principal.employmentStatus == active
    - principal.team == platform
    - resource.environment == dev
    - resource.project == platform-learning
~~~

Khi nhân viên chuyển đội, điều kiện phụ thuộc thuộc tính có thể thay đổi quyết định truy cập. Tuy nhiên, **role binding hoặc grant cũ gắn trực tiếp vẫn phải được phát hiện và thu hồi**; ABAC không tự loại bỏ mọi đặc quyền tồn dư.

### 5.2. Danh tính có đặc quyền

Tài khoản quản trị, break-glass, chủ tài khoản gốc hoặc danh tính có quyền thay đổi IAM cần chính sách riêng: chủ sở hữu được xác định, phương thức xác thực mạnh, kênh truy cập độc lập khi IdP gặp sự cố, cảnh báo sử dụng, kiểm tra định kỳ và lưu dấu kiểm toán. Quyền khẩn cấp cần được bảo vệ nhưng vẫn có thể hoạt động khi xảy ra sự cố liên kết danh tính.

## 6. Joiner–Mover–Leaver cho danh tính cloud

Nguồn kích hoạt JML nên là sự kiện có thẩm quyền (như xác nhận nhân sự vào làm, thay đổi chức danh hoặc ngày kết thúc hợp đồng). Một yêu cầu thủ công không có trạng thái phê duyệt và owner rõ ràng dễ tạo tài khoản mồ côi.

| Giai đoạn | Điều kiện kích hoạt | Thao tác cần thực hiện | Bằng chứng hoàn tất |
| --- | --- | --- | --- |
| **Joiner** | Có mã nhân viên/đối tác đã xác minh, ngày hiệu lực, owner | Tạo identity tại IdP; gán nhóm theo vai trò; provision tài khoản đích cần thiết; cấp role cloud đã phê duyệt | Identity liên kết đúng; đăng nhập hợp lệ; quyền thực tế khớp baseline |
| **Mover** | Chuyển đội, dự án, vị trí, môi trường hoặc mức nhạy cảm | Tính lại quyền mong muốn; thu hồi quyền thuộc vai trò cũ; cấp quyền vai trò mới theo chính sách/phê duyệt; kiểm tra tài khoản phụ | Chênh lệch quyền cũ và mới được xử lý; owner/phạm vi cập nhật |
| **Leaver** | Nghỉ việc, hết hạn hợp đồng, mất tư cách sử dụng | Chặn đăng nhập; vô hiệu hóa account đích; thu hồi grants/role bindings, session hoặc key có thể thu hồi; xử lý tài khoản ủy quyền, token, nhóm, guest | Danh tính không thể truy cập theo các đường đã xác định; có log và xác nhận từ đích |

### 6.1. Joiner: tạo đúng danh tính ngay từ đầu

Thông tin nên có: định danh bất biến từ hệ thống nguồn, trạng thái hoạt động, loại nhân sự, đơn vị, vai trò, người quản lý, ngày bắt đầu/kết thúc nếu có. Email hoặc tên hiển thị thường là **thuộc tính có thể thay đổi**, không nên là khóa duy nhất để đồng nhất danh tính xuyên hệ thống.

Ví dụ, hệ thống tiếp nhận nhân viên mới có mã nguồn **EMP-1042**; IdP tạo user ID ổn định rồi gắn với mã đó. Bộ phận nhân sự thay email người dùng sau khi đổi tên; liên kết tài khoản cloud vẫn dựa vào định danh đã ghép đúng, tránh tạo tài khoản thứ hai.

Provisioning phải theo **ngày hiệu lực** và chính sách: có thể chuẩn bị danh tính trước ngày nhận việc nhưng chỉ kích hoạt quyền cần thiết đúng thời điểm; quyền sản xuất hoặc quản trị cần phê duyệt riêng.

### 6.2. Mover: thu hồi quyền cũ là bước bắt buộc

Khi nhân viên chuyển từ nhóm vận hành sản xuất sang nhóm phân tích, việc chỉ thêm nhóm mới sẽ để lại quyền vận hành cũ. Luồng đúng gồm:

1. Nhận sự kiện thay đổi và xác định thời điểm hiệu lực.
2. Tính **desired access** theo vai trò mới và ngoại lệ còn hiệu lực.
3. So sánh với **actual access** từ IdP, IAM và ứng dụng đích.
4. Thu hồi role, group, grant, quyền ủy quyền không còn lý do hợp lệ; cấp quyền mới sau khi thỏa điều kiện phê duyệt.
5. Kiểm tra lại trạng thái tại hệ thống đích; ghi nhận ngoại lệ ngắn hạn và ngày hết hạn.

Đối với thay đổi rủi ro cao, cần kiểm soát thứ tự cấp và thu hồi để tránh một khoảng thời gian người dùng giữ đồng thời hai nhóm quyền xung đột. Đây là yêu cầu **separation of duties (SoD)** bên cạnh least privilege.

### 6.3. Leaver: chặn truy cập và xử lý quyền tồn dư

Một quy trình Leaver có thể bao gồm các lớp thu hồi:

**Lớp danh tính:** Cập nhật trạng thái nguồn; khóa/disable ở IdP và các tài khoản cloud-local; xử lý tài khoản khách, tài khoản dự phòng gắn với cá nhân.

**Lớp quyền:** Xóa thành viên nhóm, role assignment, policy binding, quyền trực tiếp trong các cloud tenant/account/project và ứng dụng SaaS liên quan.

**Lớp credential/phiên:** Thu hồi hoặc vô hiệu hóa access key, personal access token, refresh token, phiên có cơ chế revoke; yêu cầu tái xác thực hoặc chờ hết hạn đối với cơ chế không hỗ trợ thu hồi tức thời; xoay credential dùng chung nếu người rời đi từng nắm giữ.

**Lớp sở hữu:** Chuyển giao resource, pipeline, khóa, service account và automation do người đó sở hữu cho owner hợp lệ trước khi ngừng các phụ thuộc cần thiết.

**Lớp kiểm chứng:** Đối soát cả nguồn danh tính lẫn hệ thống đích; thử xác nhận không còn quyền theo kịch bản được phép; lưu trạng thái hoàn tất và các trường hợp thất bại để xử lý tiếp.

**Lưu ý:** Một số hệ thống dùng “suspend/disable”, một số dùng “delete/deprovision”; không nên xóa dữ liệu cần bảo quản theo chính sách lưu trữ hoặc nghiệp vụ chỉ để hoàn tất thu hồi. Mục tiêu bảo mật là chặn truy cập và loại bỏ quyền không hợp lệ, đồng thời tuân thủ chính sách dữ liệu.

## 7. Provisioning: SCIM, API, JIT và đối soát

**System for Cross-domain Identity Management (SCIM)** là giao thức/đặc tả thường dùng để quản lý user, group và một số thuộc tính qua API. Hệ thống nguồn có thể yêu cầu tạo tài khoản, cập nhật thuộc tính/nhóm, hoặc đưa user sang trạng thái bất hoạt nếu hệ thống đích hỗ trợ.

SCIM và SSO giải quyết các phần khác nhau:

- **SSO/Federation:** Người dùng xác thực và được chấp nhận đăng nhập thông qua một quan hệ tin cậy.
- **SCIM/Provisioning:** Hệ thống đích nhận và cập nhật trạng thái tài khoản/nhóm.
- **Cloud IAM:** Hệ thống đích kiểm tra quyền thao tác đối với tài nguyên.

**Just-in-time (JIT) provisioning** có thể tạo account khi người dùng đăng nhập lần đầu. Điều đó không đồng nghĩa với **JIT privileged access** (cấp quyền đặc biệt có thời hạn), và cũng không thay thế được quy trình Leaver nếu tài khoản đã tồn tại nhưng người dùng không đăng nhập trở lại.

### 7.1. Mẫu vòng đời đồng bộ danh tính

~~~mermaid
sequenceDiagram
    participant H as HRIS / nguồn chuẩn
    participant L as Lifecycle / IGA
    participant I as IdP
    participant T as Cloud / SaaS
    H->>L: Joiner hoặc Mover hoặc Leaver
    L->>I: Tạo/cập nhật/disable identity
    L->>T: Provision hoặc thu hồi qua SCIM/API
    T-->>L: Kết quả thực thi
    L->>T: Đọc lại trạng thái và quyền thực tế
    T-->>L: User, groups, role bindings, trạng thái
    L->>L: So sánh desired và actual; ghi audit
    opt Có sai lệch hoặc lỗi tạm thời
        L->>T: Retry có kiểm soát / tạo sự kiện xử lý
    end
~~~

Các yêu cầu vận hành cần có:

1. **Định danh ổn định:** Ghép đúng người với tài khoản đích bằng mapping được quản lý; đề phòng email tái sử dụng, trùng tên, hợp nhất tài khoản.
2. **Idempotency:** Chạy lại yêu cầu không tạo user hoặc grant trùng; có khóa tương quan, phát hiện thao tác đã hoàn thành.
3. **Retry và xử lý lỗi:** Phân biệt lỗi tạm thời với quyền API sai, dữ liệu không hợp lệ và tài khoản bị xung đột; cảnh báo khi không thể deprovision đúng hạn.
4. **Reconciliation:** Định kỳ lấy actual access từ cloud thay vì chỉ tin rằng API đã trả thành công.
5. **Audit trail:** Ghi sự kiện nguồn, actor/service thực thi, phê duyệt, thay đổi trước/sau, thời điểm và kết quả kiểm chứng.
6. **Độ trễ:** Đặt ngưỡng xử lý hợp lý theo mức rủi ro; đối với người rời tổ chức hoặc sự cố tài khoản bị xâm nhập, ưu tiên chặn đăng nhập ngay rồi hoàn tất thu hồi các quyền đích.

Với dữ liệu nhân sự thiếu hoặc mâu thuẫn, hệ thống nên đưa yêu cầu vào trạng thái cần xử lý thay vì tự gắn quyền nhạy cảm. Sự kiện Leaver thất bại không thể được coi là hoàn thành chỉ vì request đã được gửi.

## 8. Danh tính workload, tài khoản dịch vụ và CI/CD

Không phải cloud identity nào cũng thuộc về con người. Một ứng dụng có thể đọc secret, một máy ảo có thể ghi log, một workload trên Kubernetes có thể gọi storage, hoặc CI/CD có thể triển khai bản phát hành. Những danh tính này cũng cần vòng đời, chủ sở hữu và giới hạn quyền.

| Loại danh tính | Cách xác thực thường gặp | Nguy cơ nổi bật | Cách quản trị |
| --- | --- | --- | --- |
| Workload gắn với môi trường cloud | Managed identity, instance/workload role, token do nền tảng cấp | Cấp role quá rộng; dùng chung giữa môi trường | Mỗi workload/môi trường có phạm vi riêng, token ngắn hạn |
| CI/CD ngoài cloud | OIDC federation hoặc token exchange | Trust policy cho phép repository/nhánh bất kỳ | Giới hạn issuer, audience, repository, nhánh, môi trường |
| Service account truyền thống | Key/secret tĩnh nếu không có lựa chọn khác | Key bị lộ, tồn tại nhiều năm, không rõ owner | Kho secret, rotation, hạn dùng, giám sát và loại bỏ key không cần thiết |
| Tài khoản máy do người tạo | Có thể bị gắn với tài khoản cá nhân | Người nghỉ việc nhưng job còn chạy hoặc ngược lại | Tách ownership theo dịch vụ; có kế hoạch bàn giao và vô hiệu hóa |

**Ưu tiên credential ngắn hạn và federation/managed identity** khi nền tảng hỗ trợ. Ví dụ, pipeline nhận OIDC token có hạn ngắn, chứng minh nguồn chạy hợp lệ rồi đổi lấy credential cloud tạm thời đúng một deployment role. Pipeline không cần lưu access key có tuổi thọ dài trong biến môi trường.

Các thuộc tính quản trị bắt buộc của workload nên gồm: ID, hệ thống sở hữu, owner chính/phụ, mục đích, môi trường, quyền cần dùng, nơi triển khai, thời điểm tạo, ngày rà soát/hết hạn và liên kết với kho mã/CI/CD khi có.

**JML cho workload** có thể hiểu tương tự:

- **Joiner:** Tạo identity qua Infrastructure as Code hoặc workflow phê duyệt; chỉ định owner và role nhỏ nhất; bật log.
- **Mover:** Khi đổi môi trường, thay ứng dụng hoặc thay owner, tính lại trust/policy; thu hồi key và role không còn cần.
- **Leaver:** Khi xóa workload/pipeline, thu hồi trust, role binding và secret liên quan; kiểm tra không còn API call hợp lệ từ identity đó.

Hãy tránh liên kết quyền runtime của ứng dụng trực tiếp với tài khoản cá nhân người phát triển. Một nhân viên rời công ty không được làm dừng workload quan trọng vì không có người tiếp nhận, và một workload không được giữ đường truy cập của nhân viên đã nghỉ.

## 9. Áp dụng trên những hệ sinh thái cloud phổ biến

Mỗi nhà cung cấp có cách đặt tên khác nhau, nhưng vẫn có hai câu hỏi chung: **chủ thể được chứng minh là ai** và **quyền nào được phép thực thi tại tài nguyên nào**.

| Hệ sinh thái | Thành phần nhận dạng/xác thực điển hình | Thành phần quyền truy cập cloud điển hình | Danh tính máy được ưu tiên khi phù hợp |
| --- | --- | --- | --- |
| **AWS** | IdP bên ngoài kết nối AWS IAM Identity Center, hoặc cơ chế federation khác | AWS IAM role, policy, AWS STS temporary credentials, quyền theo account/resource | IAM role cho compute/workload; OIDC federation cho CI/CD |
| **Microsoft Azure** | Microsoft Entra ID, federation/SSO, MFA và chính sách đăng nhập | Azure RBAC role assignment theo management group/subscription/resource group/resource; phân quyền riêng trong dịch vụ | Managed identities, workload identity federation |
| **Google Cloud** | Google Cloud Identity hoặc Google Workspace và liên kết IdP bên ngoài | Google Cloud IAM principals, roles, policy bindings theo organization/folder/project/resource | Service account kết hợp Workload Identity Federation hoặc cơ chế identity của nền tảng |

Bảng chỉ đưa ví dụ kiến trúc; khả năng chi tiết tùy dịch vụ, phiên bản và cấu hình. Không được giả định người dùng “đã là admin ở IdP” thì tự động có quyền admin trên mọi cloud account/project.

### 9.1. Mô hình đa cloud

Tổ chức sử dụng nhiều cloud nên thiết lập định danh nhân sự chung và một quy trình JML thống nhất, nhưng **kiểm kê quyền thực tế riêng từng đích**. Một người có thể đồng thời sở hữu nhóm IdP, Azure RBAC assignment, AWS IAM role trust/permission set và Google Cloud IAM binding. Thu hồi ở một nơi không chứng minh các nơi khác đã sạch quyền.

Các role tương đương giữa nhà cung cấp hiếm khi trùng phạm vi tuyệt đối. Khi di chuyển workload hoặc nhân viên, cần rà soát lại chính sách theo tài nguyên và action cụ thể thay vì sao chép danh xưng role.

## 10. Tình huống xuyên suốt: nhân viên đổi vai trò rồi nghỉ việc

Giả sử **Mai** gia nhập đội phát triển nền tảng; hồ sơ HR có mã bất biến **EMP-1042**. Công ty có IdP trung tâm và ba môi trường cloud: dev, staging, production.

**Bước 1 – Joiner.** HR phát sự kiện nhận việc; workflow tạo tài khoản IdP, gán nhóm phát triển, yêu cầu xác thực mạnh và cấp role đọc log, triển khai dev. Mai được đăng nhập SSO và chọn quyền tương ứng; không được quản trị production. Hệ thống lưu dấu: sự kiện HR, ID chủ thể, ai phê duyệt, role nào được gắn và kết quả đọc lại quyền.

**Bước 2 – Mover.** Mai chuyển sang đội phân tích dữ liệu. Chính sách mới cho phép đọc dữ liệu đã được phân loại trên project phân tích; quyền triển khai dev từ vai trò trước không còn cần. Workflow xóa nhóm/role cũ, thêm role mới, kiểm tra các grant đã gắn trực tiếp và xác nhận quyền production vẫn không tồn tại.

**Bước 3 – Leaver.** HR xác nhận ngày nghỉ; tài khoản IdP bị disable đúng thời điểm. Cloud IAM được đối soát để thu hồi role binding còn lại, API key cá nhân nếu có, tài khoản khách và session có thể hủy. Nếu Mai từng là owner của pipeline thì chuyển owner và thay credential theo quy trình. Kiểm tra tại các cloud đích cho thấy không còn đường truy cập hợp lệ.

Ví dụ một sự kiện phát hiện sai lệch quyền (dữ liệu giả định):

~~~json
{
  "eventType": "identity_access_reconciliation",
  "identityId": "EMP-1042",
  "lifecycleState": "moved",
  "resourceScope": "cloud-dev/project-platform",
  "desiredRoles": [],
  "actualRoles": ["developer-deploy"],
  "decision": "revoke_stale_role",
  "approvalReference": "MOVE-2048",
  "verificationState": "pending",
  "timestamp": "2026-11-23T07:00:00Z"
}
~~~

Sự kiện này **chưa phải bằng chứng đã thu hồi**: trạng thái verificationState còn pending. Chỉ khi thao tác đích thành công và đọc lại không còn role cũ thì mới cập nhật verified; nếu thất bại cần cảnh báo và tiếp tục xử lý.

### 10.1. Mô hình desired access và actual access

~~~text
desired = policy(identity.currentStatus, role, team, scope, approvals)
actual  = discoverEffectiveAccess(identity, allRelevantTargets)

stale   = actual - desired
missing = desired - actual

for entitlement in stale:
    revoke(entitlement)

for entitlement in missing:
    grant_only_if_authorized(entitlement)

verify_against_targets()
record_approval_changes_outcomes_and_exceptions()
~~~

Đây là mô hình khái niệm: quyền thực tế có thể kế thừa qua nhóm, nested group, role assumption, resource policy hoặc rule điều kiện. Vì vậy hàm discoverEffectiveAccess phải xét các đường cấp quyền liên quan; phép trừ đơn giản chỉ đúng khi dữ liệu đã được chuẩn hóa cùng phạm vi và ngữ nghĩa.

## 11. Rủi ro thường gặp và cách phát hiện

| Rủi ro | Dấu hiệu | Kiểm soát hoặc hành động |
| --- | --- | --- |
| **Orphan identity** | Tài khoản có quyền nhưng không tìm thấy owner hoặc hồ sơ nguồn hợp lệ | Đối soát identity ID với HR/registry, chỉ định owner, đình chỉ và điều tra theo quy trình |
| **Privilege accumulation** | Người chuyển vai trò vẫn giữ nhóm và quyền cũ | So sánh desired/actual, thu hồi ở hệ thống đích, review định kỳ |
| **Long-lived credentials** | Access key hoặc secret tồn tại lâu, không có ngày xoay | Chuyển sang workload federation/managed identity; đặt hạn dùng và rotation |
| **Federation misconfiguration** | Trust nhận token từ issuer, audience hoặc subject quá rộng | Ràng buộc chính xác issuer/audience/claims; kiểm tra chữ ký và điều kiện cấp role |
| **Tài khoản shadow/local** | Có user cloud-local ngoài IdP, không nằm trong JML | Inventory chủ thể từ cloud, gắn owner, quản lý riêng emergency account |
| **Provisioning drift** | IdP đã disable nhưng account SaaS/cloud vẫn active | Theo dõi lỗi SCIM/API; reconciliation; xác minh thu hồi trực tiếp |
| **Group/role quá rộng** | Thành viên một nhóm dùng chung được cấp quyền admin hàng loạt | Role theo chức năng và phạm vi; approval/PIM/JIT cho quyền nhạy cảm |
| **Thiếu log kiểm toán** | Chỉ thấy yêu cầu “revoke” mà không thấy kết quả | Lưu sự kiện nguồn, lệnh thay đổi, kết quả đích, người phê duyệt, thời điểm |

Các chỉ số vận hành hữu ích:

- **Thời gian thu hồi quyền:** Khoảng từ thời điểm Leaver có hiệu lực đến khi xác minh xong quyền liên quan (ví dụ đo P95 theo nhóm rủi ro).
- **Số danh tính mồ côi:** Principal có quyền nhưng không có nguồn hợp lệ hoặc owner được xác nhận.
- **Tỷ lệ lệch quyền:** Danh tính có actual access khác desired access sau kỳ đối soát.
- **Tài khoản/credential đặc quyền chưa rà soát:** Bao gồm quyền trực tiếp, key tĩnh, break-glass và danh tính workload.
- **Tỷ lệ hoàn tất theo bằng chứng:** Sự kiện JML có kết quả đọc lại tại đích, thay vì chỉ có log request.

Các chỉ số cần được phân chia theo người dùng, tài khoản đặc quyền và workload; một ngưỡng giống nhau có thể che giấu rủi ro lớn ở nhóm nhạy cảm.

## 12. Checklist thiết kế và vận hành Cloud identity

Khi triển khai hoặc đánh giá hệ thống cloud identity, hãy tự đối chiếu các điểm sau:

1. **Nguồn gốc và chủ sở hữu:** Mỗi người/workload có mã định danh ổn định, nguồn thẩm quyền và owner rõ ràng.
2. **Phân tách trách nhiệm:** IdP xác thực, chính sách IAM cấp quyền, IGA/lifecycle điều phối các thay đổi và kiểm chứng.
3. **Federation bảo mật:** Token/assertion được kiểm tra issuer, audience, chữ ký, thời hạn và điều kiện trust thích hợp.
4. **Ít quyền nhất:** Role/policy được giới hạn theo hành động, tài nguyên, môi trường; quyền cao cần phê duyệt, có thời hạn khi khả thi.
5. **Đồng bộ có kiểm chứng:** SCIM/API/JIT có quy tắc ghép identity, idempotency, retry, xử lý lỗi và đối soát actual access.
6. **Mover và Leaver đầy đủ:** Xóa quyền cũ, xử lý cả tài khoản cloud-local, service account do người đó sở hữu, credential và session theo khả năng nền tảng.
7. **Workload identity riêng:** Không nhúng access key dài hạn khi có thể dùng federation/managed identity; mỗi workload có owner và vòng đời.
8. **Khả năng kiểm toán:** Có log JML, phê duyệt, role binding, đăng nhập, token/credential quan trọng và xác nhận sau thu hồi.
9. **Rà soát định kỳ:** Phát hiện quyền trực tiếp, danh tính mồ côi, guest quá hạn, nhóm không còn owner và drift đa cloud.
10. **Phương án khẩn cấp:** Có cách xử lý IdP/federation bị gián đoạn, tài khoản đặc quyền bị xâm nhập và lỗi deprovision mà vẫn giữ nguyên bằng chứng.

## 13. Tổng kết khái niệm

Cloud identity là lớp biểu diễn các chủ thể trên hạ tầng và dịch vụ đám mây; cloud IAM dùng danh tính đã xác thực cùng policy/ngữ cảnh để quyết định quyền. **IdP và SSO** hợp nhất trải nghiệm xác thực; **SCIM/API** đồng bộ trạng thái tài khoản; **RBAC/ABAC** tổ chức quyền; **JML và đối soát** bảo đảm các quyền thay đổi theo tư cách thực tế của con người hoặc workload.

Một hệ thống quản lý vòng đời danh tính chỉ được xem là thực thi đầy đủ khi sự kiện Joiner, Mover hay Leaver đã dẫn tới **trạng thái quyền đúng tại các cloud target**, được xác minh và có bằng chứng kiểm toán. Đặc biệt, cần chủ động tìm và loại bỏ **quyền truy cập tồn dư** sau thay đổi vai trò, chấm dứt hợp đồng hoặc kết thúc workload.
