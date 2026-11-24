# Zero Trust và identity

> **Chương:** Zero Trust IAM  
> **Chủ đề:** Zero Trust và identity  
> **Phạm vi học tập:** Quản lý vòng đời danh tính trong Identity and Access Management (IAM), từ xác minh và tạo tài khoản đến cấp, rà soát và thu hồi quyền theo mô hình **Joiner–Mover–Leaver (JML)**. Bài học kết nối IdP, SSO, SCIM, RBAC/ABAC, danh tính máy, kiểm toán và xử lý quyền truy cập tồn dư.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vì sao **danh tính là đầu vào trung tâm của quyết định truy cập Zero Trust** nhưng một lần đăng nhập thành công không đủ để tin cậy mọi hành động tiếp theo.
2. Phân biệt xác minh danh tính, xác thực, cấp phát tài khoản, phân quyền, thực thi chính sách và kiểm toán; chỉ ra vai trò của IdP, SSO, SCIM, ứng dụng và hệ thống quản lý vòng đời.
3. Thiết kế các quyết định truy cập phụ thuộc **chủ thể, tài nguyên, hành động và ngữ cảnh**, kết hợp RBAC và ABAC với nguyên tắc quyền tối thiểu.
4. Áp dụng Zero Trust vào các tình huống Joiner, Mover, Leaver và danh tính của workload/tài khoản dịch vụ.
5. Nhận diện và đo lường những khoảng trống như tài khoản mồ côi, token còn hiệu lực, quyền cũ sau chuyển bộ phận và tài khoản dịch vụ dùng bí mật dài hạn.

## 2. Zero Trust đặt ra câu hỏi gì với một danh tính?

Trong cách tiếp cận dựa trên ranh giới mạng, một hệ thống có thể xem người dùng trong VPN hoặc mạng nội bộ là tương đối đáng tin. **Zero Trust** loại bỏ sự tin cậy ngầm dựa trên vị trí mạng hoặc việc đã đăng nhập trước đó. Mỗi yêu cầu truy cập tài nguyên cần được đánh giá theo chính sách với các tín hiệu phù hợp.

Ba nguyên tắc triển khai thường dùng:

- **Xác minh rõ ràng:** sử dụng bằng chứng về danh tính, mức bảo đảm xác thực, trạng thái tài khoản, thiết bị, rủi ro và tài nguyên cần truy cập.
- **Cấp quyền tối thiểu:** cho phép đúng hành động trên đúng tài nguyên, trong khoảng thời gian cần thiết; phân tách những nhiệm vụ xung đột.
- **Giả định có thể bị xâm nhập:** một tài khoản, phiên hoặc thiết bị đã được xác thực vẫn có thể bị đánh cắp hoặc thay đổi rủi ro; hệ thống phải giới hạn phạm vi tác động và phát hiện bất thường.

Ví dụ, nhân viên An đăng nhập thành công qua SSO bằng MFA. Khi An mở ứng dụng tài chính, việc SSO xác nhận “đây là An” **không tự động** trả lời “An được xem hóa đơn của công ty B” hoặc “An được duyệt chuyển khoản”. API tài chính vẫn phải kiểm tra quyền hiện tại, tenant, mức nhạy cảm và ngữ cảnh của yêu cầu.

Một cách mô hình hóa quyết định:

**Decision = Policy(subject, resource, action, context)**

Trong đó:

| Thành phần | Câu hỏi phải trả lời | Ví dụ thuộc tính |
|---|---|---|
| **Subject – chủ thể** | Ai hoặc workload nào đang gọi? | ID ổn định, loại danh tính, trạng thái active, nhóm/vai trò, phương thức xác thực, người/nhóm chịu trách nhiệm |
| **Resource – tài nguyên** | Đang truy cập dữ liệu/dịch vụ nào? | Invoice ID, tenant, chủ sở hữu, phân loại dữ liệu, môi trường production |
| **Action – hành động** | Được phép thao tác gì? | read, create, approve, export, delete, assume-role |
| **Context – ngữ cảnh** | Yêu cầu đang diễn ra trong điều kiện nào? | Độ tin cậy thiết bị, thời điểm, rủi ro phiên, nguồn mạng, vị trí nếu hợp pháp và cần thiết, kết quả xác thực tăng cường |

**Điểm cốt lõi:** “Đã xác thực” là một tín hiệu cho phép *xem xét* quyền truy cập; nó không phải giấy phép truy cập mọi tài nguyên. Chính sách có thể trả về **allow**, **deny**, hoặc yêu cầu **step-up authentication** hay một quy trình phê duyệt bổ sung. Mặc định từ chối khi thiếu bằng chứng quan trọng.

## 3. Những khái niệm IAM cần phân biệt

| Khái niệm | Công việc chính | Không nên nhầm với |
|---|---|---|
| **Identity proofing** – xác minh danh tính | Xác nhận một người/chủ thể thực sự là đối tượng được khai báo, ở mức phù hợp với rủi ro | Đăng nhập hằng ngày |
| **Identity lifecycle** – vòng đời danh tính | Tạo, cập nhật, khóa, thu hồi và chấm dứt danh tính khi quan hệ/ vai trò thay đổi | Chỉ tạo user một lần |
| **Authentication (AuthN)** – xác thực | Kiểm tra bằng chứng rằng bên đang yêu cầu là chủ thể đã khai báo | Quyền đọc/sửa một tài nguyên |
| **Authorization (AuthZ)** – phân quyền | Quyết định hành động cụ thể có được phép với tài nguyên cụ thể hay không | Thành công của SSO |
| **Provisioning / deprovisioning** | Đồng bộ tài khoản, thuộc tính, nhóm và trạng thái tới ứng dụng đích | Kiểm tra quyền ngay khi API chạy |
| **Session/token management** | Phát hành, giới hạn, làm mới và chấm dứt phiên hoặc token | Việc hủy tài khoản trong cơ sở dữ liệu |
| **Access review / attestation** | Chủ sở hữu nghiệp vụ xác nhận quyền hiện tại còn hợp lý | Thay thế thực thi chính sách thời gian chạy |
| **Audit / monitoring** | Ghi nhận và phát hiện sự kiện truy cập, thay đổi quyền, sai lệch trạng thái | Cơ chế ngăn chặn truy cập trực tiếp |

Một tổ chức có thể có một **Identity Provider (IdP)** xác thực tập trung, **Single Sign-On (SSO)** cho nhiều ứng dụng, **SCIM** để cấp phát tài khoản, nhưng vẫn chưa đạt mục tiêu Zero Trust nếu mỗi API bỏ qua kiểm tra quyền tài nguyên, hoặc người rời công ty vẫn sử dụng được refresh token cũ.

### Luồng kiến trúc tham chiếu

~~~mermaid
flowchart LR
    HR["Nguồn nhân sự / hợp đồng"] -->|"Sự kiện Joiner–Mover–Leaver"| LC["Lifecycle orchestration"]
    LC -->|"Tạo, đổi, khóa danh tính"| IDP["IdP / Directory"]
    LC -->|"SCIM hoặc API provisioning"| APP["Tài khoản ứng dụng"]
    S["Người dùng / workload"] -->|"SSO hoặc token phù hợp"| PEP["Ứng dụng / API gateway / PEP"]
    PEP -->|"Subject + Resource + Action + Context"| PDP{"Policy decision / PDP"}
    IDP -->|"Trạng thái và thuộc tính đã tin cậy"| PDP
    CTX["Thiết bị, phiên, độ nhạy, rủi ro"] --> PDP
    PDP -->|"Allow / Deny / Step-up"| PEP
    PEP -->|"Chỉ khi được cho phép"| DATA["Tài nguyên"]
    LC --> LOG["Nhật ký / kiểm toán"]
    PEP --> LOG
    PDP --> LOG
~~~

**Đọc sơ đồ theo hai đường khác nhau:**

1. **Đường quản lý vòng đời (control plane):** nguồn nhân sự và quy trình phê duyệt tạo sự kiện; hệ thống IAM cập nhật danh tính, nhóm, trạng thái và tài khoản ở ứng dụng.
2. **Đường xử lý truy cập (data plane):** người dùng/workload gửi yêu cầu; **Policy Enforcement Point (PEP)** chặn yêu cầu và thi hành kết quả từ **Policy Decision Point (PDP)**. PDP sử dụng chính sách, thuộc tính và tín hiệu tin cậy. Trong mô hình NIST SP 800-207 còn có thành phần **Policy Administrator (PA)** hỗ trợ thiết lập hoặc chấm dứt đường kết nối theo quyết định chính sách; cách phân tách cụ thể phụ thuộc kiến trúc triển khai.

Sơ đồ chỉ mô tả trách nhiệm logic. PEP có thể nằm trong API, service mesh, proxy hoặc ứng dụng; nhiều tổ chức triển khai cả kiểm tra ở gateway và kiểm tra quyền đối tượng ngay trong dịch vụ. **Gateway xác thực token không thay thế kiểm tra quyền theo từng bản ghi/tenant tại backend.**

## 4. Mối quan hệ giữa IdP, SSO, SCIM và chính sách Zero Trust

### 4.1. IdP và SSO: xác thực tập trung, tín hiệu có giới hạn

IdP quản lý danh tính, phiên xác thực và các thuộc tính được cấu hình. Với **OpenID Connect (OIDC)**, ứng dụng có thể nhận ID token để biết về phiên xác thực; với **OAuth 2.0**, access token được cấp cho việc truy cập các API theo audience/scope; **SAML** thường truyền assertion cho đăng nhập liên kết. Chọn giao thức theo nhu cầu và mô hình tin cậy của ứng dụng.

Ở phía dịch vụ, cần xác thực **chữ ký hoặc cơ chế xác minh token, issuer, audience, thời hạn, các ràng buộc liên quan** và kiểm tra chính sách AuthZ. Không lấy tên người dùng hay vai trò do client tự gửi làm nguồn sự thật.

Ngay cả khi SSO đã hoàn tất, quyết định truy cập phải xem xét:

- **Trạng thái hiện tại:** tài khoản đang active, bị khóa, bị hạn chế hoặc đã chấm dứt?
- **Mức bảo đảm phiên:** người dùng vừa xác thực bằng phương thức nào, có cần MFA chống phishing/step-up cho hành động nhạy cảm?
- **Quyền và phạm vi:** vai trò có áp dụng cho tài nguyên và tenant hiện tại không?
- **Rủi ro thay đổi:** thiết bị mất tuân thủ, phiên có dấu hiệu bị chiếm quyền, tài khoản bị thu hồi hoặc nhiệm vụ đã chuyển?

**Lưu ý về token:** access token tự chứa (ví dụ JWT) đã phát hành có thể còn được chấp nhận đến khi hết hạn nếu dịch vụ chỉ xác minh chữ ký và thời gian. Việc khóa user ở IdP **không bảo đảm mọi token lập tức vô hiệu** ở tất cả hệ thống. Giảm khoảng hở bằng token có thời hạn phù hợp, thu hồi refresh token/phiên, kiểm tra trạng thái khi cần, introspection hoặc cơ chế truyền sự kiện thay đổi quyền nơi nền tảng hỗ trợ. Phải hiểu giới hạn thực tế của từng ứng dụng.

### 4.2. SCIM: đồng bộ vòng đời, không phải máy ra quyết định truy cập

**System for Cross-domain Identity Management (SCIM)** là giao thức/định dạng tiêu chuẩn hỗ trợ quản lý user và group giữa hệ thống nguồn và ứng dụng đích. Luồng thường gặp: hệ thống IAM tạo user, cập nhật thuộc tính bộ phận, thêm/xóa group, đặt tài khoản inactive khi nhân viên rời đi.

SCIM xử lý việc **đồng bộ tài khoản và thuộc tính**, còn cho phép một request API cụ thể là trách nhiệm của hệ thống thực thi chính sách. Đồng bộ có thể trễ hoặc thất bại; do đó sự kiện Leaver cần được giám sát đến khi các hệ thống đích xác nhận đã thu hồi, đồng thời ưu tiên những biện pháp chặn truy cập có hiệu lực nhanh tại đường xác thực/truy cập.

### 4.3. RBAC, ABAC và chính sách kết hợp

- **RBAC (Role-Based Access Control):** gán quyền theo vai trò như support_agent, finance_analyst, finance_approver. Dễ kiểm toán các nhóm nghiệp vụ lớn nhưng dễ tạo “role explosion” nếu biến mọi điều kiện chi tiết thành vai trò riêng.
- **ABAC (Attribute-Based Access Control):** quyết định dựa trên thuộc tính chủ thể, tài nguyên, hành động và ngữ cảnh như cùng tenant, dữ liệu thuộc vùng được phép, thiết bị đạt yêu cầu, giới hạn giờ hỗ trợ.
- **Kết hợp RBAC + ABAC:** vai trò định nghĩa năng lực cơ bản, thuộc tính giới hạn phạm vi từng yêu cầu. Khi cần kiểm soát quan hệ chủ sở hữu/thành viên cụ thể, có thể bổ sung kiểm tra quan hệ giữa subject và resource.

Ví dụ một chính sách **mô tả**, không phải cấu hình có thể triển khai trực tiếp:

~~~yaml
policy_id: finance.invoice.read
effect: allow
action: invoice.read
requires:
  subject.status: active
  subject.role: finance_analyst
  subject.tenant_id: same_as_resource_tenant
  device.compliant: true
  session.auth_strength: phishing_resistant_mfa
  request.risk_score_at_most: 30
default: deny
~~~

Dù người dùng thuộc vai trò finance_analyst, hệ thống vẫn từ chối hóa đơn của tenant khác hoặc thiết bị không đáp ứng yêu cầu. Trường “mức rủi ro 30” chỉ minh họa chính sách nội bộ; không có một ngưỡng phổ quát cho mọi tổ chức. Các hành động **approve_payment** hoặc **export_bulk** cần chính sách riêng và có thể thêm kiểm tra phân tách nhiệm vụ, phê duyệt hoặc xác thực tăng cường.

## 5. Zero Trust trong vòng đời Joiner–Mover–Leaver

Điểm gắn kết quan trọng là **quyết định truy cập hôm nay phải phản ánh vai trò và quan hệ hiện tại**, thay vì tin vào quyền đã được cấp trong quá khứ.

| Giai đoạn | Sự kiện khởi phát | Xử lý danh tính và quyền | Kiểm soát Zero Trust cần giữ |
|---|---|---|---|
| **Joiner** – gia nhập | Hồ sơ nhân sự/hợp đồng hợp lệ; quản lý xác nhận vai trò, ngày bắt đầu | Xác minh danh tính theo rủi ro; tạo danh tính duy nhất; đăng ký MFA; cấp nhóm/quyền chuẩn qua workflow/SCIM | Không cấp quyền nhạy cảm chỉ vì user tồn tại; kiểm tra vai trò, thiết bị, tenant và thời điểm hiệu lực khi truy cập |
| **Mover** – chuyển vai trò | Đổi nhóm, vị trí, dự án, mức trách nhiệm hoặc vùng dữ liệu | Tính lại quyền cần có; thu hồi quyền không còn phù hợp; phê duyệt quyền mới và xử lý ngoại lệ có hạn | Không mặc định cộng dồn quyền cũ và mới; buộc phiên/token/chính sách phản ánh thay đổi |
| **Leaver** – rời đi | Kết thúc hợp đồng, nghỉ việc, chấm dứt cộng tác hoặc sự kiện khẩn | Khóa danh tính, ngăn đăng nhập mới, thu hồi phiên/refresh token, gỡ nhóm, vô hiệu hóa tài khoản ứng dụng, thu hồi khóa và quyền được ủy quyền | Chặn truy cập còn tồn dư; xác nhận trạng thái trên từng ứng dụng, xử lý offline/đồng bộ lỗi, giữ log theo chính sách |

### 5.1. Joiner: chứng minh và gắn quyền với mục đích công việc

Một nhân viên mới của bộ phận hỗ trợ khách hàng cần quyền xem ticket được phân công. Workflow mẫu:

1. Nguồn nhân sự đáng tin cậy tạo sự kiện onboarding, liên kết một **subject ID ổn định** với người mới; hạn chế dựa vào email vì email có thể đổi hoặc tái sử dụng.
2. Hệ thống IAM xác minh/đối chiếu danh tính ở mức phù hợp, tạo user tại IdP, đăng ký phương thức xác thực mạnh và gắn người quản lý.
3. Quyền chuẩn được gán dựa trên thuộc tính được quản trị (phòng ban, vai trò, loại nhân sự, tenant). SCIM hoặc API đồng bộ tài khoản đến ứng dụng ticket.
4. Khi mở ticket, API vẫn kiểm tra nhân viên đang active, ticket thuộc tenant cho phép và người dùng có quan hệ phù hợp với ticket đó. Tồn tại tài khoản không đủ để vượt qua các kiểm tra này.
5. Quyền production admin, truy cập dữ liệu đặc biệt hoặc xuất hàng loạt được cấp theo yêu cầu riêng, có người phê duyệt, lý do và thời hạn.

### 5.2. Mover: giảm quyền cũ trước khi tạo quyền chồng chéo

Nhân viên Bình chuyển từ **Support** sang **Finance**. Nếu chỉ thêm nhóm Finance mà không xóa Support, Bình có thể giữ quyền xem dữ liệu khách hàng lẫn quyền duyệt giao dịch, dẫn tới quyền vượt nhu cầu và xung đột nhiệm vụ.

Quy trình hợp lý:

1. Nhận sự kiện chuyển vai trò có ngày hiệu lực và chủ sở hữu phê duyệt.
2. Tính **desired entitlements** cho vai trò mới từ nguồn thuộc tính đáng tin; so sánh với **actual entitlements** ở IdP và từng ứng dụng.
3. Xóa quyền không còn cần thiết, xử lý quyền đặc biệt bằng cơ chế thời hạn và phê duyệt; thiết kế thứ tự cắt/chuyển giao để không tạo khoảng gián đoạn nghiệp vụ không kiểm soát.
4. Cập nhật nhóm và thuộc tính, truyền sự kiện thay đổi quyền, xử lý các phiên/token có thể chứa claim vai trò cũ.
5. Rà soát sau thay đổi: xác nhận Bình không xem được ticket nhạy cảm trước đây và chỉ thực hiện hành động tài chính thuộc phạm vi được cấp.

**Bẫy phổ biến:** một access token cũ vẫn chứa claim Support; dịch vụ kiểm tra claim này đơn thuần có thể tiếp tục cho phép đến khi token hết hạn. Khi cần thu hồi nhanh, dịch vụ phải dùng trạng thái quyền hiện tại hoặc cơ chế vô hiệu hóa token/phiên phù hợp. Tránh đặt toàn bộ tính đúng của Mover lên đồng bộ SCIM vốn có thể chạy bất đồng bộ.

### 5.3. Leaver: đóng cả đường vào lẫn các quyền tồn dư

Khi người dùng nghỉ việc, chỉ đặt trạng thái inactive ở IdP là chưa đủ để chứng minh đã chặn toàn bộ truy cập:

- **Đăng nhập/phiên:** từ chối đăng nhập mới, kết thúc phiên IdP và phiên ứng dụng, thu hồi refresh token/ủy quyền phù hợp.
- **Tài khoản đích:** vô hiệu hóa/gỡ quyền qua SCIM/API, kiểm tra ứng dụng không tích hợp và tài khoản cục bộ.
- **Chứng thực khác:** thu hồi hoặc quay vòng API key, SSH key, PAT, secret, chứng chỉ hoặc token còn do người dùng sở hữu; chuyển quyền sở hữu automation đúng quy trình.
- **Quyền gián tiếp:** xóa nhóm, role, chia sẻ trực tiếp, delegation, quyền truy cập kho mã, cloud account, tài khoản break-glass không còn được ủy quyền.
- **Xác nhận và đối soát:** kiểm tra kết quả theo từng hệ thống, cảnh báo deprovision thất bại và theo dõi cho đến khi được xử lý.

**Tài khoản và dữ liệu không nhất thiết phải xóa ngay:** lịch sử audit, hồ sơ nghiệp vụ, sở hữu tài liệu và yêu cầu lưu trữ có thể cần được bảo toàn. Phân biệt rõ **chặn truy cập**, **thu hồi quyền**, **chuyển sở hữu** và **xóa dữ liệu** theo chính sách của tổ chức.

## 6. Ra quyết định và thực thi quyền truy cập theo từng yêu cầu

Giả sử ứng dụng có endpoint đọc hóa đơn:

~~~http
GET /api/invoices/inv-2048
Authorization: Bearer <access-token>
~~~

Backend thực hiện chuỗi kiểm tra:

1. Xác thực token hợp lệ cho **API này** (issuer, audience, thời hạn và ràng buộc liên quan).
2. Xác định subject ID; tra cứu trạng thái danh tính hiện tại khi mức rủi ro/kiến trúc yêu cầu.
3. Tải thuộc tính hóa đơn từ nguồn tin cậy, bao gồm tenant, mức nhạy cảm và quan hệ với người gọi. **Không tin tenant_id hoặc resource owner do client tùy ý khai báo.**
4. Kiểm tra hành động invoice.read, chính sách RBAC/ABAC và điều kiện phiên/thiết bị. Ghi nhận policy decision.
5. Chỉ trả dữ liệu khi được cho phép; nếu không, trả mã lỗi phù hợp, tránh tiết lộ chi tiết tài nguyên nhạy cảm.

Bảng quyết định ví dụ:

| Tình huống | Xác thực | Quyền/ngữ cảnh | Kết quả |
|---|---|---|---|
| An active, MFA mạnh, finance_analyst, đúng tenant, thiết bị hợp lệ | Hợp lệ | Đủ yêu cầu invoice.read | **Allow** |
| An đăng nhập hợp lệ nhưng hóa đơn thuộc tenant khác | Hợp lệ | Sai phạm vi tài nguyên | **Deny** |
| Bình vừa chuyển khỏi Support, token cũ còn claim Support | Token chưa hết hạn | Trạng thái quyền hiện tại không còn Support | **Deny** khi chính sách dùng trạng thái mới |
| Quản trị viên yêu cầu xuất dữ liệu lớn, phiên không đủ mức xác thực | Hợp lệ | Thiếu yêu cầu cho hành động nhạy cảm | **Step-up** hoặc **Deny**, theo chính sách |
| User đã nghỉ việc nhưng vẫn gửi request qua token còn hạn | Có thể hợp lệ về mặt chữ ký | Danh tính bị vô hiệu hóa | **Deny** nếu có cơ chế đánh giá trạng thái/thu hồi đủ nhanh |

**“Liên tục xác minh”** là khả năng đánh giá lại khi yêu cầu, rủi ro hoặc quyền thay đổi; không nhất thiết phải bắt người dùng nhập MFA ở mỗi API call. Có thể dùng phiên ngắn phù hợp, sự kiện thu hồi, xác thực tăng cường theo rủi ro, cache chính sách có thời hạn giới hạn và kiểm tra lại ở thao tác nhạy cảm. Cần thiết kế cả khi nguồn thuộc tính/PDP không khả dụng: xác định hành động nào phải **fail closed**, hành động nào có thể dùng quyết định đã cache theo hạn chặt chẽ; tuyệt đối tránh “PDP lỗi thì mặc định allow”.

### Chống lỗi phân quyền tại tầng đối tượng

Hai API có cùng vai trò user vẫn có thể yêu cầu quyết định khác nhau:

- GET /invoices/inv-2048: quyền đọc hóa đơn cụ thể.
- POST /invoices/inv-2048/approve: quyền duyệt hóa đơn cụ thể, có thể cần người duyệt khác người tạo.

Vì thế cần kiểm soát quyền ở cấp **hành động và tài nguyên thực tế**, phòng lỗi broken object-level authorization (BOLA/IDOR), thay vì chỉ kiểm tra “có role finance” ở cổng API.

## 7. Danh tính máy, tài khoản dịch vụ và quyền không gắn người

Zero Trust áp dụng cho **workload, service account, CI/CD pipeline, job nền và API client** như với người dùng, nhưng bằng chứng danh tính khác nhau. Service A gọi Service B không trở nên tin cậy chỉ vì chúng cùng VPC/Kubernetes cluster.

Mỗi workload nên có:

- **Danh tính riêng và chủ sở hữu rõ ràng:** tên, mục đích, môi trường, hệ thống chịu trách nhiệm, ngày rà soát; tránh dùng tài khoản chung của con người cho automation.
- **Chứng thực phù hợp:** ưu tiên workload identity/federation, token ngắn hạn hoặc mTLS/chứng chỉ được quản lý; giới hạn và luân chuyển secret tĩnh nếu chưa thể loại bỏ.
- **Quyền hẹp:** chỉ một nhóm API, audience, scope, tài nguyên và môi trường cần thiết; tách staging với production và hạn chế quyền ghi.
- **Vòng đời độc lập:** tự động ngừng/thu hồi khi dịch vụ ngừng chạy, dự án đóng hoặc chủ sở hữu thay đổi; kiểm tra các quyền tồn dư của bot và integration.
- **Quan sát được:** log service principal, workload source, quyền sử dụng và dấu hiệu lạm dụng; cảnh báo key cũ hoặc quyền chưa từng dùng.

Ví dụ: một job đối soát chỉ cần đọc hóa đơn của tenant được chỉ định. Nếu job có khóa quản trị toàn hệ thống lưu trong biến môi trường và không hết hạn, Zero Trust chưa được thực thi dù các nhân viên đều dùng MFA.

### Khi nào “mạng nội bộ” vẫn có ích?

Phân đoạn mạng, service mesh và mTLS làm giảm bề mặt tấn công và hỗ trợ xác thực workload, nhưng **không thay thế** chính sách quyền ở tầng nghiệp vụ. Kết hợp cả hai để hạn chế đường đi của kẻ tấn công khi một danh tính hoặc workload bị chiếm quyền.

## 8. Kiểm toán và các tín hiệu để phát hiện khoảng trống

Log cần cho phép tái dựng **ai hoặc dịch vụ nào**, **đã yêu cầu hành động gì**, **trên tài nguyên nào**, **dựa vào chính sách nào**, **vào thời điểm nào** và **kết quả ra sao**, đồng thời hạn chế thông tin cá nhân/bí mật được ghi nhận.

Các nhóm sự kiện quan trọng:

| Nhóm | Sự kiện nên ghi |
|---|---|
| Vòng đời | Joiner/Mover/Leaver; nguồn yêu cầu; người duyệt; ngày hiệu lực; cập nhật trạng thái |
| Provisioning | Tạo/sửa/khóa user; thêm/xóa group; ứng dụng đích xác nhận; lỗi và retry |
| Xác thực/phiên | MFA, đăng nhập bất thường, khóa tài khoản, cấp và thu hồi phiên/token phù hợp |
| Phân quyền | Quyết định allow/deny/step-up đối với hành động nhạy cảm; policy ID/version, lý do đủ mức để điều tra |
| Quyền đặc biệt | Elevation/JIT, phê duyệt, thời hạn hết quyền, quyền không sử dụng |
| Workload identity | Tạo/đổi credential, giả mạo hoặc sử dụng bất thường, thay đổi owner, thu hồi integration |

Ví dụ cấu trúc sự kiện kiểm toán **mang tính minh họa**:

~~~json
{
  "timestamp": "2026-11-23T07:15:00Z",
  "event_type": "access_decision",
  "subject_id": "usr-271",
  "resource_type": "invoice",
  "resource_id": "inv-2048",
  "action": "invoice.read",
  "decision": "deny",
  "reason_code": "TENANT_SCOPE_MISMATCH",
  "policy_id": "finance.invoice.read",
  "policy_version": "v12",
  "correlation_id": "req-8e91"
}
~~~

Không log access token, mật khẩu, secret hoặc toàn bộ tài liệu/hồ sơ nhạy cảm. Cần bảo vệ tính toàn vẹn, phân quyền người đọc log, đồng bộ thời gian và có thời hạn lưu trữ thích hợp.

Những chỉ số nên theo dõi theo SLA/rủi ro của tổ chức:

- **Thời gian thu hồi thực tế:** từ sự kiện Leaver/Mover đến khi truy cập bị chặn ở các hệ thống quan trọng; đo cả p95/p99 và trường hợp vượt SLA.
- **Độ lệch quyền:** chênh lệch giữa desired entitlements và actual entitlements; tài khoản mồ côi, quyền trực tiếp ngoài chuẩn, nhóm không chủ sở hữu.
- **Độ phủ:** tỷ lệ ứng dụng tích hợp SSO/provisioning, tỷ lệ quyền nhạy cảm có kiểm tra ở cấp API/tài nguyên, tỷ lệ tài khoản dịch vụ có owner.
- **Chất lượng rà soát:** số quyền bị thu hồi qua access review, ngoại lệ quá hạn, quyền đặc biệt không có ngày kết thúc.
- **Khả năng phát hiện:** số lần deny do quyền cũ, truy cập sau offboarding, credential dùng sau thu hồi, sự kiện thất bại đồng bộ chưa được xử lý.

Không đánh giá thành công chỉ bằng “100% nhân viên có SSO”. Mục tiêu phải gắn với **quyền thực tế**, thời gian chặn truy cập và khả năng chứng minh hệ thống đang thi hành đúng chính sách.

## 9. Sai lầm thường gặp và cách xử lý

| Sai lầm | Hệ quả | Kiểm soát phù hợp |
|---|---|---|
| “Có VPN hoặc SSO thì tin cậy” | Di chuyển ngang và truy cập quá phạm vi khi tài khoản bị chiếm | PEP/PDP kiểm tra action, resource, context; phân đoạn mạng |
| Chỉ kiểm tra role có trong JWT | Quyền vẫn còn sau Mover/Leaver đến lúc token hết hạn | Giới hạn token, cập nhật/thu hồi phiên, kiểm tra quyền hiện tại ở nơi nhạy cảm |
| Gắn thêm quyền khi chuyển bộ phận | Tích lũy quyền cũ, xung đột nhiệm vụ | Reconcile desired–actual, thu hồi role cũ, thời hạn quyền và access review |
| Cho phép tenant do client truyền quyết định phạm vi | BOLA/IDOR và lộ dữ liệu chéo tenant | Lấy thuộc tính tài nguyên từ backend tin cậy, kiểm tra object-level |
| SCIM báo lỗi nhưng workflow đánh dấu đã xong | Tài khoản còn sống ở ứng dụng đích | Retry có kiểm soát, theo dõi xác nhận, cảnh báo và đối soát định kỳ |
| Dùng một API key admin cho nhiều job | Không quy trách nhiệm, khó thu hồi, phạm vi lộ lớn | Danh tính workload riêng, đặc quyền hẹp, credential ngắn hạn |
| PDP không phản hồi thì cho qua | Mất lớp chặn trong thời điểm lỗi | Thiết kế fail closed cho tác vụ nhạy cảm, cache quyết định có hạn |
| Ghi token vào log để debug | Rò rỉ credential trong hệ thống log | Redact, dùng subject ID/correlation ID, giới hạn quyền xem log |

## 10. Gợi ý triển khai từng bước

1. **Kiểm kê danh tính và điểm ra quyết định:** người dùng, khách ngoài, service principal, ứng dụng, API, tài nguyên nhạy cảm, nơi có local account và secret dài hạn.
2. **Chuẩn hóa nguồn danh tính:** xác định hệ thống nguồn tin cậy cho trạng thái nhân sự, hợp đồng, vai trò và tenant; dùng ID ổn định và owner rõ ràng.
3. **Định nghĩa quyền theo nghiệp vụ:** lập danh mục action/resource, role nền tảng, thuộc tính ABAC, chính sách deny-by-default và quy tắc phân tách nhiệm vụ.
4. **Tự động hóa JML:** tích hợp IdP/SSO/SCIM hoặc API, quy trình phê duyệt và reconciliation; xử lý lỗi và thu hồi khẩn cấp bằng đường chặn phù hợp.
5. **Đưa kiểm tra quyền vào đường xử lý:** PEP tại gateway/dịch vụ, PDP/policy module, kiểm tra tenant và object-level, step-up cho hoạt động rủi ro.
6. **Bảo vệ phiên và workload:** cấu hình token lifetime, revoke, credential rotation, danh tính máy riêng và logging.
7. **Kiểm thử và đo lường:** mô phỏng chuyển vai trò, nghỉ việc, token cũ, thiết bị không tuân thủ, cross-tenant access và lỗi đồng bộ; giám sát thời gian thu hồi và độ lệch quyền.

### Checklist kiểm tra thiết kế

- [ ] Có nguồn xác thực trạng thái active/inactive và chủ sở hữu danh tính đáng tin cậy.
- [ ] Quyền được xác định trên **subject + action + resource + context**, có deny mặc định.
- [ ] Backend kiểm tra tenant và quyền ở cấp đối tượng, không tin thuộc tính tùy ý từ client.
- [ ] Joiner cấp quyền tối thiểu; Mover gỡ quyền cũ; Leaver chặn cả phiên và tài khoản đích.
- [ ] Có cách giảm rủi ro token/claim cũ khi trạng thái hoặc vai trò thay đổi.
- [ ] SCIM/provisioning có xác nhận kết quả, retry, cảnh báo và reconciliation.
- [ ] Workload/service account có owner, quyền hẹp và credential được quản lý theo vòng đời.
- [ ] Audit đủ đối soát sự kiện và quyết định mà không lưu credential nhạy cảm.
- [ ] Có kiểm thử deny/fail-closed, quyền chéo tenant và kịch bản mất kết nối đến thành phần chính sách.

## 11. Bài tập tình huống

**Bối cảnh:** Công ty dùng IdP và SSO để đăng nhập ứng dụng CRM, kế toán và kho dữ liệu. Nhân viên Chi chuyển từ Sales sang Finance lúc 09:00. SCIM cập nhật quyền kế toán lúc 09:02 nhưng CRM cập nhật chậm đến 10:00. Access token CRM được cấp lúc 08:55, hết hạn 10:55. Lúc 09:30, Chi vẫn truy vấn được danh sách khách hàng cũ trên API CRM.

**Câu hỏi:**

1. Vì sao SSO và SCIM vẫn chưa bảo vệ được yêu cầu lúc 09:30?
2. Phải sửa ở tầng vòng đời và tầng xử lý request như thế nào?
3. Nên ghi sự kiện nào để chứng minh quyền Sales đã bị thu hồi đầy đủ?

**Gợi ý đáp án:**

1. Quyền và token cũ còn hiệu lực ở ứng dụng đích; SSO chỉ xác thực, còn SCIM là luồng đồng bộ có độ trễ. API có thể đang dựa vào claim cũ hoặc tài khoản chưa cập nhật.
2. Cập nhật quyền đích có xác nhận và cơ chế chặn truy cập ngay khi vai trò đổi; tùy kiến trúc, thu hồi phiên/refresh token, rút ngắn tuổi token hoặc kiểm tra quyền hiện tại ở API. Kiểm tra từng tài nguyên và tenant theo chính sách mới; điều tra SCIM lỗi/chậm và đặt SLA cho đường thu hồi.
3. Ghi sự kiện Mover, thời gian hiệu lực, desired/actual role, lệnh và xác nhận thu hồi tại CRM, tình trạng phiên/token, các quyết định deny/allow sau 09:00 và kết quả kiểm thử quyền cũ.

**Mở rộng:** Nếu Chi từng tạo một API key cá nhân cho integration, quy trình Mover/Leaver phải tìm và xử lý key đó thế nào để không gián đoạn một workflow hợp lệ? Phân biệt thu hồi key cá nhân với chuyển workflow sang danh tính workload do nhóm sở hữu.

## 12. Thuật ngữ và nguồn đọc tiếp

| Từ khóa | Ghi nhớ |
|---|---|
| **Zero Trust Architecture (ZTA)** | Kiến trúc ra quyết định theo chính sách và tín hiệu, không tin cậy ngầm theo vị trí mạng |
| **IdP / Directory** | Nơi quản lý danh tính, bằng chứng đăng nhập, nhóm và thuộc tính |
| **SSO / OIDC / SAML** | Cơ chế đăng nhập liên kết; không thay thế kiểm tra quyền tài nguyên |
| **OAuth 2.0 access token** | Chứng thực được cấp cho truy cập API theo giới hạn phù hợp; phải xác minh và kiểm tra quyền |
| **SCIM** | Chuẩn hỗ trợ provision/deprovision và đồng bộ user/group |
| **RBAC / ABAC** | Phân quyền theo vai trò / thuộc tính |
| **PEP / PDP / PA** | Thành phần thực thi / ra quyết định / quản trị việc thiết lập đường truy cập trong kiến trúc chính sách |
| **JML** | Joiner, Mover, Leaver: vòng đời gắn với quan hệ và vai trò của chủ thể |
| **Residual access** | Quyền hoặc phiên tồn dư dù không còn nhu cầu/ủy quyền hợp lệ |

Tài liệu tham khảo để đào sâu khái niệm: **NIST SP 800-207 (Zero Trust Architecture)**; **NIST SP 800-63 (Digital Identity Guidelines)**; **RFC 7643/7644 (SCIM)**; các đặc tả **OpenID Connect Core**, **OAuth 2.0**, và hướng dẫn **OWASP API Security** về lỗi phân quyền ở mức đối tượng.

**Ý chính cần nhớ:** Zero Trust biến danh tính thành một phần của *quyết định truy cập có điều kiện và có thể thay đổi*. Một thiết kế IAM tốt phải đồng thời đảm bảo biết chủ thể là ai, chủ thể hiện được phép làm gì, cách thu hồi kịp thời khi vai trò thay đổi, và bằng chứng kiểm toán về kết quả thực thi.
