# Cloud Identity và quản lý danh tính tổ chức trên Google Cloud

> **Chương:** Quản trị tổ chức  
> **Bài học:** Cloud Identity và quản lý danh tính tổ chức  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu; qua các tình huống triển khai, người học biết chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành, theo dõi độ tin cậy và chi phí. Để làm được điều đó trên quy mô doanh nghiệp, tổ chức phải quản lý **danh tính của người dùng và nhóm** trước khi bàn đến quyền quản trị tài nguyên.

**Cloud Identity** hỗ trợ quản lý tập trung danh tính tổ chức dưới miền doanh nghiệp, các nhóm, cơ chế đăng nhập và một số chính sách thiết bị/bảo mật tùy phiên bản và giấy phép. Cùng với **Google Cloud Identity and Access Management (IAM)**, Cloud Identity giúp trả lời hai câu hỏi khác nhau:

- **Bạn là ai?** Danh tính được xác thực, thuộc tổ chức hoặc nhóm nào, tài khoản có đang hoạt động không?
- **Bạn được làm gì trên tài nguyên nào?** IAM role, phạm vi resource, điều kiện và các chính sách liên quan quyết định quyền.

Bài viết tập trung vào mối quan hệ giữa Cloud Identity, Google Workspace, Google Cloud Organization, IAM và vòng đời danh tính. Ví dụ sử dụng miền và project giả định, không yêu cầu tạo người dùng hoặc thay đổi cấu hình sản xuất để hoàn thành bài.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **Cloud Identity**, **Google Workspace**, **Cloud IAM**, **Organization resource**, **Folder**, **Project** và **Google Groups**.
2. Mô tả cách miền đã xác minh và tài khoản tổ chức giúp thiết lập ranh giới quản trị Google Cloud.
3. Thiết kế vòng đời **joiner–mover–leaver**: tạo tài khoản, gán nhóm, thay đổi chức vụ, thu hồi quyền và xử lý tài khoản nghỉ việc.
4. Phân tách quyền quản trị danh tính trong **Google Admin console** với quyền quản lý tài nguyên trong **Google Cloud console**.
5. Áp dụng MFA/2-Step Verification, SSO, kiểm soát phiên, bảo vệ tài khoản đặc quyền và giám sát truy cập.
6. Phân biệt danh tính con người, **service account**, **Workload Identity Federation** và **Workforce Identity Federation**.
7. Xây dựng ma trận nhóm–vai trò–phạm vi cho nhiều project phát triển, vận hành và sản xuất.
8. Phát hiện sai sót phổ biến: dùng tài khoản cá nhân ngoài tổ chức, cấp quyền trực tiếp tràn lan, bỏ sót quyền kế thừa hoặc hiểu nhầm nhóm là một role.

## 2. Cloud Identity là gì?

Cloud Identity là dịch vụ quản lý danh tính và bảo mật cho tổ chức của Google. Tổ chức có thể sử dụng **tài khoản được quản lý theo miền** để cung cấp danh tính đăng nhập, tổ chức người dùng/nhóm và áp dụng chính sách quản lý phù hợp.

Cloud Identity có các phiên bản **Free** và **Premium**, với phạm vi tính năng, quản lý thiết bị, báo cáo và quyền lợi khác nhau. Việc một tính năng có được sử dụng hay không còn tùy loại giấy phép, cấu hình và chính sách hiện hành. Doanh nghiệp đã dùng **Google Workspace** có hệ thống danh tính/quản trị tương ứng; không nhất thiết phải tạo thêm một hệ danh tính tách biệt chỉ để sử dụng Google Cloud.

### 2.1. Phân biệt các thành phần

| Thành phần | Chịu trách nhiệm chính | Ví dụ | Không nên nhầm với |
|---|---|---|---|
| **Cloud Identity** | Quản lý tài khoản, nhóm, đăng nhập và chính sách danh tính của tổ chức | `engineer@example.com`, nhóm `gcp-ops@example.com` | Role cho phép sửa Compute Engine VM |
| **Google Workspace** | Bộ ứng dụng cộng tác và quản trị người dùng doanh nghiệp | Gmail, Drive, Calendar và quản trị tài khoản | Tự động có quyền Owner mọi project |
| **Google Admin console** | Giao diện quản trị danh tính, người dùng, nhóm, bảo mật và thiết bị theo quyền | `admin.google.com` | Google Cloud console quản lý VM/GKE |
| **Google Cloud IAM** | Cho phép hoặc hạn chế principal thực hiện permission trên resource | `roles/run.developer` tại project | Cơ chế xác thực mật khẩu/SSO |
| **Google Cloud Organization** | Nút gốc phân cấp tài nguyên cloud cho một tổ chức | `organizations/123456789012` | Organizational Unit của Cloud Identity |
| **Folder / Project** | Nhóm và cô lập tài nguyên cloud, làm scope của IAM/policy | `folders/…` và `projects/…` | Google Groups |
| **Google Group / Cloud Identity Group** | Tập hợp người dùng/nhóm để quản trị thành viên và cấp IAM theo nhóm | `gcp-platform@example.com` | Role; nhóm không tự mang permission khi chưa gán IAM |
| **Service account** | Danh tính cho workload chạy trên Google Cloud | `orders-api@project.iam.gserviceaccount.com` | Tài khoản nhân viên đăng nhập Console |

**Một tài khoản được quản lý không tự có quyền trên mọi tài nguyên Google Cloud.** Khả năng đăng nhập và quyền sử dụng API là hai bước riêng; quyền cuối cùng phụ thuộc vào IAM policy, quyền kế thừa và những kiểm soát khác.

### 2.2. Người dùng tổ chức và người dùng cá nhân

- **Managed Google Account:** tổ chức có thể quản trị vòng đời và chính sách thông qua hệ thống danh tính của mình; thường dùng địa chỉ email thuộc miền đã xác minh.
- **Personal Google Account:** tài khoản do cá nhân tự quản lý, có thể được mời vào dự án trong phạm vi chính sách nhưng doanh nghiệp không tự kiểm soát toàn bộ vòng đời đăng nhập của tài khoản đó.
- **Unmanaged account dùng miền doanh nghiệp:** có thể đã được cá nhân tạo trước khi doanh nghiệp xác minh miền. Việc xử lý trùng/đụng độ tài khoản cần quy trình chuyển đổi được hỗ trợ, trao đổi với người sử dụng và quản trị viên; không tự giả định mọi tài khoản sẽ chuyển thành managed account khi xác minh miền.

Đối với vận hành và kiểm toán, ưu tiên danh tính do tổ chức quản lý cho nhân viên và phân quyền theo nhóm; tài khoản bên ngoài phải được phê duyệt và có ngày rà soát.

## 3. Từ miền doanh nghiệp đến Google Cloud Organization

### 3.1. Vì sao phải xác minh miền?

Cloud Identity/Google Workspace sử dụng cơ chế **domain verification** để xác nhận tổ chức kiểm soát miền được khai báo, ví dụ `example.com`. Quản trị viên thường cần chứng minh quyền quản lý DNS bằng một bản ghi xác minh do Google cung cấp. Đây là bước chứng minh sở hữu miền; nó **không tự tạo VM, VPC, bucket hoặc quyền IAM cho từng nhân viên**.

Trình tự khái quát:

1. Đơn vị phụ trách xác nhận miền chính và người chịu trách nhiệm quản trị DNS.
2. Tạo/thiết lập tenant Cloud Identity hoặc Google Workspace được phê duyệt.
3. Thực hiện domain verification theo hướng dẫn chính thức.
4. Cấu hình danh tính quản trị, phương thức đăng nhập, chính sách bảo mật và nhóm.
5. Kiểm tra **Google Cloud Organization resource** liên quan trong Google Cloud và phân quyền quản trị cấp organization.
6. Tổ chức folder/project và chính sách quản trị trong phạm vi organization.

Sự xuất hiện và quyền nhìn thấy Organization resource phụ thuộc trạng thái thiết lập danh tính/tổ chức và IAM. Nếu không tìm thấy organization trong Console, cần kiểm tra điều kiện thiết lập, tài khoản đăng nhập và quyền xem; **đừng tự tạo thêm tenant** để xử lý vội.

### 3.2. Hai cây phân cấp khác nhau

~~~mermaid
flowchart LR
    subgraph I["Danh tính: Admin console"]
      D["Miền đã xác minh"] --> OU["Organizational Units<br/>cấu hình chính sách người dùng"]
      D --> U["Managed Users"]
      D --> G["Groups và Group Membership"]
    end
    subgraph C["Tài nguyên: Google Cloud"]
      O["Organization resource"] --> F["Folder: Engineering"]
      F --> PD["Project: development"]
      F --> PP["Project: production"]
      PP --> S["Cloud Run / GKE / Cloud SQL"]
    end
    G -. "Gán group làm IAM principal" .-> PD
    G -. "Gán role có scope phù hợp" .-> PP
~~~

**Organizational Unit (OU)** trong hệ quản trị danh tính dùng để áp chính sách cho tập người dùng/thiết bị theo khả năng sản phẩm. **Folder** trong Google Cloud Resource Manager dùng để tổ chức tài nguyên, áp IAM và Organization Policy theo phân cấp cloud. Cùng có khái niệm “đơn vị tổ chức” nhưng **không phải một cây đồng bộ tự động**.

Ví dụ: nhân viên thuộc OU `Engineering` trong Admin console không tự được quyền sửa dự án trong folder `Engineering` của Google Cloud. Muốn cấp quyền cloud, quản trị viên phải cấu hình đúng IAM binding hoặc chính sách ủy quyền được hỗ trợ.

### 3.3. Organization và dự án “No organization”

Các project có thể tồn tại ngoài một Organization resource tùy nguồn gốc và mô hình tài khoản. Khi doanh nghiệp đưa project vào organization, cần kiểm tra **người sở hữu tài nguyên, billing, IAM, Organization Policy, network, service account và quyền di chuyển project**. Không coi việc chuyển project như chỉ đổi tên một thư mục: chính sách kế thừa tại đích có thể làm hành vi vận hành thay đổi.

## 4. Ai quản trị danh tính, ai quản trị tài nguyên?

Google Admin console và Google Cloud console phục vụ hai miền quản trị. Người làm ở cả hai hệ thống có thể giữ nhiều vai trò, nhưng nên tách rõ trách nhiệm theo năng lực.

| Nhóm quản trị | Phạm vi | Nhiệm vụ tiêu biểu | Rủi ro nếu lạm quyền |
|---|---|---|---|
| **Cloud Identity / Workspace Super Admin** | Tenant danh tính, quyền quản trị cao nhất theo khả năng sản phẩm | Khôi phục tài khoản, quản lý admin role, cấu hình bảo mật, chính sách danh tính | Tài khoản bị chiếm có thể ảnh hưởng diện rộng đến danh tính |
| **Delegated user/group admin** | Tập người dùng/nhóm được ủy quyền | Onboarding, cập nhật nhóm, hỗ trợ vòng đời | Gán sai thành viên nhóm có IAM quyền cao |
| **Google Cloud Organization Admin** | Google Cloud organization và cấu trúc tài nguyên | Quản trị organization/folder và ủy quyền cloud theo vai trò cấp | Thay đổi tài nguyên/chính sách toàn tổ chức |
| **Security administrator** | Danh tính, chính sách cloud và giám sát theo nhiệm vụ | MFA, quản trị posture, audit, phân quyền đặc quyền | Xung đột kiểm soát nếu vừa phê duyệt vừa tự cấp quyền |
| **Project admin / workload owner** | Project hoặc tài nguyên được giao | Quản lý Compute Engine/GKE/Cloud Run và dịch vụ dữ liệu | Quyền quá rộng có thể ảnh hưởng production |
| **Auditor / FinOps** | Log, cấu hình, dữ liệu chi phí trong phạm vi cho phép | Rà IAM, thay đổi, chi phí và ngoại lệ | Xem dữ liệu nhạy cảm ngoài nhu cầu |

Một người được chỉ định **Super Admin** của Cloud Identity/Workspace có thể có các quyền khởi tạo quản trị Google Cloud theo thiết lập tổ chức; tuy nhiên **không được suy diễn quyền thực tế chỉ từ chức danh**. Phải đọc lại IAM policy và thử khả năng trên đúng Organization/Project. Ngược lại, `roles/resourcemanager.organizationAdmin` là role của Google Cloud IAM và **không thay thế toàn bộ quyền Super Admin** trong Admin console.

### 4.1. Phân tách nhiệm vụ

Quy trình tốt nên có ít nhất ba bước tách vai:

1. **Chủ dịch vụ yêu cầu** quyền theo trách nhiệm công việc.
2. **Quản trị danh tính** xác nhận người dùng hoạt động và thêm vào đúng group.
3. **Chủ resource hoặc security reviewer** phê duyệt IAM binding/group-to-role và kiểm tra quyền hiệu lực.

Tổ chức nhỏ có thể gộp một phần vai trò nhưng vẫn cần dấu vết phê duyệt, quyền tối thiểu và rà soát độc lập định kỳ cho nhóm đặc quyền.

## 5. Quản lý Google Groups và cấp quyền IAM theo nhóm

### 5.1. Vì sao ưu tiên nhóm?

Cấp quyền trực tiếp cho từng người sẽ tạo nhiều binding khó rà soát. Cấp quyền cho **Google Group** cho phép IAM policy ổn định khi nhân viên thay đổi; nhóm phụ trách danh tính cập nhật thành viên theo quy trình.

Ví dụ giả định:

| Group | Thành viên | IAM role dự kiến | Scope |
|---|---|---|---|
| `gcp-dev-readers@example.com` | Dev cần xem môi trường dev | `roles/viewer` (đánh giá mức quyền cụ thể) | Project development |
| `gcp-ops-logs@example.com` | SRE, hỗ trợ vận hành | `roles/logging.viewer` | Project production |
| `gcp-run-deployers@example.com` | CI/CD operators được ủy quyền | Role triển khai Cloud Run phù hợp | Project/Resource cần triển khai |
| `gcp-billing-auditors@example.com` | Tài chính/FinOps | Billing viewer/cost role phù hợp | Billing account được phụ trách |
| `gcp-security-review@example.com` | Kiểm toán nội bộ | Vai trò read-only phù hợp | Organization/folder/project theo nhiệm vụ |

Tên nhóm trên chỉ là **minh họa**. Một group có thể được gán nhiều role ở nhiều tài nguyên; đồng thời một người thuộc nhiều group. IAM lấy kết quả từ tất cả nguồn cấp quyền có liên quan, không xem group là “ngăn chứa” quyền độc quyền.

### 5.2. Quy trình quản trị group

1. **Định danh:** đặt tên thể hiện sản phẩm, môi trường và mức quyền; ghi owner chịu trách nhiệm.
2. **Xác định membership rule:** ai có thể vào nhóm, ai phê duyệt, thời hạn và điều kiện rời nhóm.
3. **Quản lý thành viên:** ưu tiên thay đổi membership qua quy trình IT/IAM; không chia sẻ account dùng chung.
4. **Gán role:** owner cloud gán group làm IAM principal ở scope thấp nhất đáp ứng nhu cầu.
5. **Kiểm tra:** xác minh thành viên, role, quyền kế thừa và khả năng truy cập thực tế.
6. **Rà soát:** kiểm tra nhóm bỏ quên, thành viên hết nhiệm vụ, nhóm lồng nhau và các đường cấp quyền không mong muốn.

**Điểm cần cẩn trọng:** group có owner được phép thêm thành viên sẽ trở thành một phần đường kiểm soát IAM. Nếu group đó giữ role nhạy cảm trên production, **quyền quản lý thành viên group cũng là quyền gián tiếp ảnh hưởng production** và cần được bảo vệ.

### 5.3. Minh họa allow policy

~~~yaml
# Minh họa đoạn binding, không dùng làm toàn bộ policy để ghi đè.
bindings:
  - role: roles/logging.viewer
    members:
      - group:gcp-ops-logs@example.com
version: 1
~~~

Khi nhóm được dùng làm principal, tài khoản `sre-a@example.com` phải là thành viên hợp lệ và không bị chính sách khác chặn để sử dụng các permission của role. **Group membership không tự động cấp role** nếu trong IAM chưa có binding.

Nếu cần quyền tạm thời, có thể xem xét **IAM Conditions** (ví dụ điều kiện thời gian) hoặc cơ chế **Privileged Access Manager** được tổ chức hỗ trợ; việc chọn giải pháp phụ thuộc yêu cầu phê duyệt, ghi log và rà soát.

## 6. Vòng đời danh tính: Joiner – Mover – Leaver

Danh tính phải thay đổi khi quan hệ lao động hoặc trách nhiệm công việc thay đổi. Quy trình vòng đời tốt có thể tự động hóa một phần từ hệ thống nhân sự/danh bạ, nhưng luôn cần xác minh dữ liệu nguồn.

### 6.1. Joiner: nhân viên gia nhập

**Kịch bản:** Minh gia nhập nhóm backend và chỉ cần xem log của project development.

- Nhân sự/IT xác nhận hợp đồng, tài khoản tổ chức và email quản lý.
- Quản trị viên tạo hoặc đồng bộ managed user `minh@example.com` trong Cloud Identity/Workspace.
- Áp chính sách đăng nhập, MFA/2SV, thiết bị và phục hồi tài khoản theo cấp rủi ro.
- Thêm Minh vào nhóm `gcp-dev-readers@example.com` hoặc nhóm quan sát log phù hợp.
- Owner cloud kiểm tra IAM binding của group ở project development; không cấp Owner vì người dùng cần đọc log.
- Người dùng thử truy cập đúng project, ghi nhận người cấp và thời điểm phê duyệt.

### 6.2. Mover: chuyển nhóm hoặc thay đổi trách nhiệm

**Kịch bản:** Minh chuyển từ development sang team SRE có nhiệm vụ hỗ trợ production.

- Loại khỏi nhóm phát triển nếu không còn cần quyền.
- Thêm vào nhóm `gcp-ops-logs@example.com` với quyền xem log production đã được duyệt.
- Nếu cần deploy, cấp thêm quyền cụ thể và điều kiện thời hạn phù hợp, không mặc định nâng toàn bộ quyền.
- Rà **binding IAM cấp trực tiếp**, nhóm lồng nhau và quyền được kế thừa từ folder/organization; không chỉ xem nhóm mới.
- Kiểm thử cả quyền cần có và quyền cần mất; lưu audit.

### 6.3. Leaver: nghỉ việc hoặc kết thúc hợp đồng

Khi nhân viên rời tổ chức, một quy trình minh họa:

1. Nhân sự phát tín hiệu thôi việc và thời điểm chấm dứt quyền.
2. IT/Identity team đình chỉ hoặc vô hiệu hóa tài khoản theo chính sách, thu hồi phiên/truy cập theo khả năng hệ thống.
3. Xóa membership các group, thu hồi các role IAM cấp trực tiếp và quyền tại hệ thống liên quan.
4. Kiểm tra token, khóa/credential cá nhân, quyền impersonation service account, ứng dụng bên thứ ba và CI/CD credentials mà người đó từng quản lý.
5. Bàn giao tài nguyên có owner là nhân viên, dữ liệu cần giữ và trách nhiệm quản trị; không xóa dữ liệu doanh nghiệp trái chính sách lưu giữ.
6. Xác minh không còn đăng nhập/truy cập và lưu dấu vết xử lý.

**Chỉ xóa membership là chưa đủ** nếu người dùng còn được cấp IAM trực tiếp, thuộc group khác hoặc sở hữu thông tin xác thực ứng dụng độc lập. Cần xem cả quyền trực tiếp lẫn gián tiếp.

### 6.4. Ma trận công việc và rủi ro

| Giai đoạn | Thao tác danh tính | Thao tác IAM cloud | Kết quả kiểm tra |
|---|---|---|---|
| **Joiner** | Tạo/sync user, bật chính sách MFA, thêm group | Group đã có role đúng project | Vào được chức năng được duyệt |
| **Mover** | Rời group cũ, vào group mới | Rà IAM cấp trực tiếp, folder/org inheritance | Quyền cũ bị rút, quyền mới chính xác |
| **Leaver** | Suspend/deactivate, thu hồi session theo khả năng | Thu hồi group/direct role, kiểm tra credentials | Không còn đường truy cập hợp lệ |
| **Định kỳ** | Rà active users, group owners, admin accounts | Review privileged roles, group-to-role, ngoại lệ | Danh sách quyền có owner và lý do |

## 7. Xác thực tập trung, SSO và MFA

### 7.1. Xác thực và ủy quyền là hai bước khác nhau

~~~mermaid
sequenceDiagram
    participant E as Nhân viên
    participant ID as Cloud Identity / SSO
    participant C as Google Cloud Console / API
    participant I as Google Cloud IAM
    participant R as Tài nguyên
    E->>ID: Đăng nhập + kiểm tra MFA
    ID-->>E: Danh tính/phiên được xác thực
    E->>C: Yêu cầu thao tác trên project
    C->>I: Kiểm tra principal, permission, resource
    I-->>C: Cho phép hoặc từ chối theo policy
    C->>R: Thực hiện nếu được phép
    R-->>E: Kết quả
~~~

SSO giúp người dùng đăng nhập một cách thống nhất; IAM quyết định **người dùng đã đăng nhập được làm gì** trên Google Cloud. Một người đăng nhập thành công không có nghĩa là có quyền tạo GKE cluster hoặc xem Cloud SQL production.

### 7.2. Single Sign-On (SSO)

Doanh nghiệp có sẵn nhà cung cấp danh tính (Identity Provider – **IdP**) như một hệ thống AD/Entra/Okta có thể cấu hình liên kết đăng nhập theo cơ chế được Cloud Identity/Workspace hỗ trợ (chẳng hạn **SAML SSO**). Trong mô hình này, tổ chức quản trị chính sách xác thực ở IdP và ánh xạ danh tính sang tài khoản Google được quản lý; phải chú ý định danh duy nhất, khóa tài khoản, thời gian phiên và đường đăng nhập dự phòng.

Khi triển khai:

- Xác định **nguồn danh tính gốc** (HRIS/directory/IdP) và nơi tạo/sửa/xóa người dùng.
- Đồng bộ dữ liệu người dùng/nhóm bằng phương thức được hỗ trợ; phân biệt **provisioning** với **authentication**.
- Kiểm tra trường ID, email alias, đổi họ tên, đổi phòng ban và tài khoản trùng.
- Thử đăng nhập khi IdP hoạt động, khi IdP mất kết nối và trong ca khôi phục.
- Lập phương án truy cập khẩn cấp theo chính sách, tránh phụ thuộc duy nhất vào một tài khoản.

**SSO không tự gán IAM role.** Một IdP xác thực thành công nhưng nhóm Google/IAM chưa được đồng bộ hoặc cấu hình đúng vẫn có thể nhận lỗi `PERMISSION_DENIED`.

### 7.3. MFA / Two-Step Verification (2SV)

MFA giảm nguy cơ kẻ tấn công dùng mật khẩu bị lộ để truy cập hệ thống. Doanh nghiệp nên ưu tiên phương thức chống giả mạo đăng nhập như **security keys** hoặc **passkeys** theo tính khả dụng và chính sách; kiểm soát enrollment, account recovery và phương án xử lý mất thiết bị.

Đối với tài khoản đặc quyền:

- Áp dụng chính sách xác thực mạnh, phục hồi tài khoản có kiểm soát và bảo vệ thiết bị quản trị.
- Hạn chế số **Super Admin** và người nắm vai trò cloud có phạm vi organization.
- Có ít nhất một quy trình **break-glass** được phê duyệt và kiểm thử định kỳ; tài khoản khẩn cấp cần bảo vệ và ghi nhận chặt chẽ.
- Theo dõi phiên đăng nhập đáng ngờ, thay đổi MFA, thay đổi admin/group và IAM policy.

Các tính năng như **context-aware access**, quản lý endpoint nâng cao hoặc điều kiện thiết bị có thể phụ thuộc giấy phép và loại ứng dụng; hãy kiểm tra trước khi viết yêu cầu bắt buộc cho mọi tài khoản Cloud Identity Free.

## 8. Danh tính con người và danh tính workload

Một hệ thống Google Cloud có API Java trên Cloud Run, pod trên GKE, VM Compute Engine, job đồng bộ dữ liệu và pipeline phát hành. Không nên dùng tài khoản nhân viên để tất cả những workload đó truy cập API.

| Loại danh tính | Dùng cho | Cách quản lý nên ưu tiên |
|---|---|---|
| **Managed user** | Nhân viên vào Google Cloud Console, Cloud Shell và công cụ hỗ trợ | Cloud Identity/Workspace, SSO/MFA, vòng đời nhân sự |
| **Group** | Tập hợp các managed users hoặc principal phù hợp để cấp IAM | Owner, quy tắc membership, review định kỳ |
| **Service account** | Workload trên Cloud Run, GKE, Compute Engine và automation | Service account riêng theo ứng dụng/môi trường; IAM tối thiểu |
| **Workload Identity Federation** | Workload bên ngoài Google Cloud (ví dụ CI bên ngoài hoặc cloud khác) cần truy cập Google Cloud | Liên kết danh tính ngắn hạn từ IdP được hỗ trợ, hạn chế khóa dài hạn |
| **Workforce Identity Federation** | Nhân sự/đối tác từ IdP ngoài Google truy cập tài nguyên Google Cloud theo policy federation | Thiết lập pool/provider và mapping IAM, chính sách tổ chức phù hợp |

Hai công nghệ federation có tên gần giống nhưng **đối tượng khác nhau**: *workload* cho máy/tác vụ; *workforce* cho người dùng. **Cloud Identity SSO** với managed Google Account lại là một cách khác để nhân viên đăng nhập; không nên vẽ tất cả thành một quy trình duy nhất.

### 8.1. Ví dụ workload trên Cloud Run

Giả sử API đặt hàng cần đọc object trong Cloud Storage và gửi sự kiện Pub/Sub:

~~~text
Nhân viên lập trình:
  developer@example.com
  → đăng nhập Google Cloud bằng managed account
  → được IAM role triển khai theo group/phạm vi cho phép

Cloud Run runtime:
  orders-api@project-id.iam.gserviceaccount.com
  → danh tính workload
  → chỉ có quyền đọc bucket cụ thể và publish topic cụ thể
~~~

Nhân viên có thể có quyền **triển khai phiên bản mới** nhưng không nhất thiết có quyền **đọc dữ liệu khách hàng**. Ngược lại, service account của API có permission dùng khi chạy nhưng **không nên được cấp Editor/Owner** trên toàn project.

Trên GKE, đánh giá cơ chế **Workload Identity Federation for GKE** để workload dùng danh tính phù hợp thay vì phát tán service account key. Trên Compute Engine, dùng service account đính kèm VM với scope/access controls phù hợp; trên Cloud Run, dùng service identity của dịch vụ. Nếu pipeline ngoài Google Cloud cần truy cập, ưu tiên Workload Identity Federation thay vì khóa JSON dài hạn khi đáp ứng yêu cầu.

## 9. Tình huống thực tế: quản trị danh tính cho công ty bán lẻ

**Bối cảnh:** công ty `RetailOne` quản lý miền `retailone.example` và triển khai hệ thống đặt hàng lên Google Cloud. Họ có ba môi trường:

- **Development:** nhóm lập trình thử API Java, Cloud Run, Cloud SQL không chứa dữ liệu thật.
- **Staging:** nhóm QA xác nhận bản phát hành và chạy test tích hợp.
- **Production:** Cloud Run Orders API, Cloud SQL dữ liệu khách hàng, Pub/Sub, Monitoring và budget riêng.

Một kiến trúc quản trị tham chiếu:

~~~mermaid
flowchart TD
    ID["Cloud Identity / Google Workspace: retailone.example"]
    ID --> USERS["Users: dev, qa, sre, finance"]
    ID --> GROUPS["Groups: gcp-dev, gcp-qa, gcp-sre, gcp-finops"]
    ORG["Google Cloud Organization"] --> ENG["Folder: Engineering"]
    ENG --> DEV["Project: retail-dev"]
    ENG --> STG["Project: retail-staging"]
    ENG --> PROD["Project: retail-prod"]
    ORG --> SHARED["Folder: Shared-services"]
    SHARED --> OBS["Project: central-monitoring"]
    GROUPS -. "IAM role tại project/folder phù hợp" .-> DEV
    GROUPS -. "Role phạm vi và quyền tối thiểu" .-> STG
    GROUPS -. "Read-only production và quyền được phê duyệt" .-> PROD
~~~

### 9.1. Thiết kế quyền theo nhóm

| Group giả định | Nhu cầu | Quyền minh họa | Điều kiện kiểm soát |
|---|---|---|---|
| `gcp-devs@retailone.example` | Phát triển API tại dev | Role cần thiết cho deploy/quan sát ở dev | Không mặc định có role ở prod |
| `gcp-qa@retailone.example` | Kiểm thử staging | Role xem và thực hiện tác vụ QA được duyệt | Tách khỏi quyền sửa database production |
| `gcp-sre-readers@retailone.example` | Theo dõi vận hành prod | `roles/logging.viewer`, `roles/monitoring.viewer` khi phù hợp | Không tự động được phép deploy/đọc dữ liệu gốc |
| `gcp-prod-deployers@retailone.example` | Thực hiện phát hành prod | Role triển khai Cloud Run và quyền liên quan được rà soát | Có quy trình phê duyệt, log và tách khỏi app runtime |
| `gcp-finops@retailone.example` | Báo cáo chi phí nhiều project | Billing/cost viewer đúng phạm vi | Không cần Owner project hoặc IAM admin |

**Vai trò triển khai Cloud Run** có thể cần nhiều permission, gồm quyền trên service, image và khả năng dùng service account runtime; vì thế không nên chỉ cấp một role theo tên rồi giả định pipeline sẽ hoạt động. Phải thử thao tác cụ thể trong sandbox, cấp các quyền bổ sung ở phạm vi hẹp.

### 9.2. Quy trình nhân viên chuyển sang vận hành production

Một developer `lan@retailone.example` chuyển làm SRE.

1. Chủ team cũ phê duyệt việc rút membership khỏi `gcp-devs` khi nhiệm vụ hoàn tất.
2. Chủ team mới yêu cầu thêm vào `gcp-sre-readers`; IT kiểm tra identity còn hoạt động và MFA theo policy.
3. Security/cloud owner xác nhận role trên production chỉ đủ **xem log/metric**, không trao quyền quản lý Cloud SQL.
4. Nếu cần triển khai emergency, yêu cầu quyền đặc biệt có hạn với log/phê duyệt; không đưa vĩnh viễn vào nhóm deploy vì một sự cố.
5. Trong kỳ rà soát, kiểm tra group membership, direct IAM bindings và quyền được kế thừa từ folder/organization.

### 9.3. Sự cố nghỉ việc nhưng tài khoản vẫn có quyền

Nhân viên cũ đã rời group `gcp-devs` nhưng audit phát hiện vẫn xuất hiện trong policy production. Nguyên nhân có thể:

- Được gán IAM **trực tiếp** tại project.
- Thuộc một **group khác** hoặc nested group.
- Có quyền do **folder/organization** kế thừa.
- Một service account key hoặc credential automation mà nhân viên trước đó quản lý vẫn tồn tại.
- Quy trình vô hiệu hóa tài khoản và thu hồi phiên chưa hoàn tất.

Cách xử lý là truy vết từng đường cấp quyền, thu hồi theo chính sách và xác minh kết quả. Không xóa bừa policy của project vì có thể ảnh hưởng service account đang vận hành Cloud Run hoặc GKE.

## 10. Quản trị project, IAM và Organization Policy

Cloud Identity giải quyết danh tính và nhóm. Google Cloud cần thêm lớp quản trị tài nguyên:

### 10.1. Cấu trúc organization / folder / project

- Dùng **organization** làm ranh giới quản trị cloud, gán đội sở hữu và bảo vệ role quyền cao.
- Dùng **folder** để phân nhóm sản phẩm/môi trường hoặc đơn vị doanh nghiệp có chung chính sách.
- Dùng **project** làm ranh giới vận hành, tài nguyên, quota, billing và IAM theo workload.
- Rà lại các **IAM bindings ở tổ tiên** vì role tại organization/folder có thể cấp permission cho mọi project con theo quy tắc kế thừa.

### 10.2. Organization Policy không phải IAM role

**Organization Policy Service** áp các ràng buộc cấu hình khi tạo/sửa hoặc dùng tài nguyên được hỗ trợ, ví dụ hạn chế một số cách chia sẻ hoặc cấu hình không phù hợp với yêu cầu doanh nghiệp. IAM xác định **ai được gọi một permission**; Organization Policy có thể làm một thao tác được IAM cho phép vẫn thất bại vì cấu hình vi phạm ràng buộc.

Ví dụ công ty muốn ngăn chia sẻ IAM cho danh tính ngoài danh sách/miền được phép. Có thể xem xét chính sách giới hạn principal được cấp quyền theo khả năng Google Cloud hiện hành; cần thử tác động đến đối tác, CI/CD federation và service account của Google trước khi áp dụng trên production. **Đừng tự đoán rằng xác minh miền đã tự bật chính sách chặn mọi danh tính bên ngoài.**

### 10.3. Phân quyền và quản lý billing

Một managed user có thể thuộc group vận hành GKE nhưng **không có quyền quản trị billing account**. Mô hình billing IAM là phạm vi riêng. Nên giao quyền xem chi phí và quản lý budget cho đúng nhóm FinOps/Tài chính; sử dụng cost attribution theo project/label như một phần quản trị, không vì nhu cầu báo cáo mà cấp Owner/Editor cho cả organization.

## 11. Công cụ và lệnh quan sát an toàn

Có thể tìm cấu hình danh tính và nhóm trong **Google Admin console** tại `https://admin.google.com/`, với quyền quản trị phù hợp. Quản lý project, IAM, tài nguyên và audit của Google Cloud tại **Google Cloud console** `https://console.cloud.google.com/`.

Nếu được cấp quyền, một số câu lệnh **chỉ đọc** trên Cloud Shell hoặc máy có Google Cloud CLI:

~~~bash
# Kiểm tra danh tính CLI đang hoạt động.
gcloud auth list

# Danh sách organization mà tài khoản hiện tại được phép xem.
gcloud organizations list

# Kiểm tra project mà bạn đã biết ID.
gcloud projects describe PROJECT_ID \
  --format="yaml(projectId,projectNumber,name,parent)"

# Quan sát IAM của project (không thay đổi quyền).
gcloud projects get-iam-policy PROJECT_ID \
  --format=json
~~~

Thay `PROJECT_ID` bằng định danh thật đã được phê duyệt. Dữ liệu chỉ phản ánh tài nguyên và policy bạn **có quyền xem**, không nhất thiết là toàn bộ phạm vi doanh nghiệp. Tài khoản có thể nhìn thấy user/group ở Admin console nhưng không đủ quyền chạy `gcloud organizations list` hoặc `get-iam-policy`.

Nếu có quyền đọc IAM organization, có thể dùng:

~~~bash
gcloud organizations get-iam-policy ORGANIZATION_ID --format=json
~~~

Kết quả là **allow policy ở scope organization**; để giải thích quyền hiệu lực của một người trên một VM/Cloud Run service, vẫn phải xét thêm các binding cấp dưới, group membership, điều kiện, deny và những chính sách liên quan.

### 11.1. Thực hành chỉ đọc

1. Xác định một project **sandbox** được phép sử dụng.
2. Kiểm tra `gcloud auth list` và `gcloud projects describe PROJECT_ID`.
3. Nếu nhìn được organization, ghi lại organization ID và các project thuộc phạm vi quản trị liên quan.
4. Quan sát IAM project: tìm một binding dạng `group:...` và role/scope tương ứng; không sửa binding.
5. Đối chiếu nhóm thuộc đơn vị nào, ai quản lý thành viên và vì sao nhóm cần role đó.
6. Kiểm tra riêng mục **Billing**, **Monitoring** và các dịch vụ Compute/GKE/Cloud Run để thấy cùng một danh tính có thể có quyền khác nhau trên từng hệ thống.
7. Ghi lại giới hạn quyền quan sát nếu Console hoặc CLI trả `PERMISSION_DENIED`.

Không cần tạo managed user thật, tạo project hoặc cấp IAM role để làm bài này.

## 12. Bảo mật danh tính và kiểm toán

Một chương trình quản lý danh tính tốt cần phát hiện sai cấu hình trước khi phát sinh sự cố.

| Rủi ro | Tín hiệu cần theo dõi | Cách giảm thiểu |
|---|---|---|
| Tài khoản admin bị chiếm | Đăng nhập lạ, thay đổi MFA/role, truy cập bất thường | MFA chống phishing, giám sát và quy trình incident response |
| Có nhiều Super Admin không kiểm soát | Danh sách tài khoản quản trị tăng, owner không rõ | Giới hạn số lượng, phân quyền delegated admin, review thường xuyên |
| Cấp IAM trực tiếp tràn lan | Nhiều `user:...` trong policy project/folder | Ưu tiên group-to-role, chuẩn hóa yêu cầu quyền |
| Nhóm production không có owner | Không rõ ai thêm thành viên/duyệt | Gán owner, giới hạn quyền quản lý membership, audit |
| Nghỉ việc nhưng quyền tồn tại | Active account hoặc credential cũ vẫn dùng | Joiner–mover–leaver, kiểm tra session/key và xác nhận leaver |
| Service account key lưu trong mã nguồn | Secret bị lộ, khó truy vết nguồn sử dụng | Dùng service identity và federation, quản trị secret/key chặt |
| Phạm vi IAM quá rộng | Role cấp ở organization cho nhu cầu một project | Hạ scope về project/resource và rà quyền kế thừa |
| Đồng bộ IdP/nhóm lỗi | Người mới không có quyền hoặc người chuyển nhóm còn quyền cũ | Giám sát đồng bộ, kiểm thử lifecycle, xử lý ngoại lệ |
| Nhầm OU với Cloud Folder | Người dùng tưởng đã được gán quyền khi đổi OU | Quy trình mapping IAM riêng có kiểm soát |

### 12.1. Nguồn audit cần phân biệt

- **Google Admin/Cloud Identity audit:** sự kiện liên quan danh tính, người dùng, nhóm, đăng nhập, thay đổi cấu hình quản trị, tùy mức hỗ trợ và giấy phép.
- **Cloud Audit Logs:** thay đổi tài nguyên Google Cloud, IAM policy, lệnh/API của dịch vụ theo loại log và cấu hình.
- **Cloud Logging / Monitoring:** log, metric và cảnh báo vận hành workload Compute Engine, GKE, Cloud Run, cơ sở dữ liệu và các thành phần khác.
- **Hệ thống ticket/HR/ITSM:** yêu cầu cấp quyền, phê duyệt, chuyển bộ phận và nghỉ việc.

Không nên kết luận “không có thay đổi nhóm” chỉ vì không thấy sự kiện trong **Cloud Audit Logs của project**; quản trị membership của Cloud Identity thuộc nguồn audit danh tính tương ứng.

### 12.2. Quyền xem audit cũng cần giới hạn

Báo cáo đăng nhập, membership, chi tiết principal, resource và nhật ký lỗi có thể chứa thông tin nhạy cảm. Chỉ cấp quyền đọc cho nhóm có nhiệm vụ, đặt retention phù hợp và không đăng token/mật khẩu hoặc bản xuất danh sách nhân viên lên repo công khai.

## 13. Xử lý sự cố thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra có kiểm soát |
|---|---|---|
| Nhân viên đăng nhập được nhưng không thấy project | Chưa có IAM, sai account, org/folder scope hoặc quyền xem | Kiểm tra Google account, project ID và binding group/role |
| Group trong Admin console đúng nhưng `PERMISSION_DENIED` | Chưa gán IAM, role thiếu permission, policy chặn hoặc cập nhật chưa đồng bộ | Đối chiếu effective access, permission, scope; thử lại theo propagation |
| Không thấy Organization resource | Thiết lập miền/org chưa sẵn sàng, dùng sai account hoặc thiếu quyền | Xác nhận tenant, domain verification và quyền view organization |
| Quản trị viên Cloud IAM không sửa được người dùng | Cloud IAM khác quyền Admin console | Xác định delegated admin/Super Admin được phê duyệt |
| Super Admin không thao tác được tài nguyên cloud như kỳ vọng | Phạm vi role và IAM policy không phù hợp, org policy hoặc kiểm soát khác chặn | Xem quyền hiệu lực trên tài nguyên, không suy từ chức danh |
| Người nghỉ việc vẫn xuất hiện trong IAM | Direct role, nhóm khác, policy kế thừa, cập nhật chưa hoàn tất | Rà tất cả đường grant và trạng thái tài khoản |
| Người đăng nhập bằng IdP lỗi | Liên kết SSO, định danh, chứng chỉ, đồng bộ hoặc policy xác thực | Xem IdP/Cloud Identity audit và cấu hình federation |
| CI/CD deploy lỗi sau khi đổi danh tính nhân viên | Pipeline từng phụ thuộc credential cá nhân hoặc service account thiếu role | Chuyển sang workload identity và quyền cụ thể cho automation |
| Không tạo được resource dù IAM role đúng | Organization Policy, API chưa bật, quota, billing hoặc ràng buộc mạng | Đọc lỗi dịch vụ, kiểm tra policy và trạng thái project |
| Không thấy log audit của nhóm | Tìm sai hệ thống hoặc thiếu quyền/retention | Tách nguồn Google Admin audit và Cloud Audit Logs |

**Phương pháp điều tra:** xác định **principal**, **resource**, **permission**, **phạm vi IAM**, **thời điểm**, **đường cấp quyền** và **chính sách bổ sung** trước khi đề xuất cấp quyền mới. Khi cần, dùng **Policy Troubleshooter for IAM** để kiểm tra nguyên nhân được phép/từ chối theo dữ liệu hiện có.

## 14. Bài tập thiết kế: doanh nghiệp đa môi trường

Một doanh nghiệp có miền `academy.example` và 60 nhân viên. Họ triển khai:

- `academy-dev`: Cloud Run API, Cloud Storage dùng dữ liệu thực hành.
- `academy-test`: GKE dùng thử nghiệm tích hợp.
- `academy-prod`: Cloud Run, Cloud SQL với dữ liệu thật.
- `academy-shared`: Logging/Monitoring, pipeline chung.
- Một billing account dùng chung nhưng **chỉ tài chính và FinOps được xem tổng chi phí toàn tài khoản**.

Có bốn nhóm người: **Developers**, **QA**, **SRE**, **Finance**. Một cộng tác viên bên ngoài chỉ hỗ trợ 30 ngày; một developer vừa chuyển sang SRE và một nhân viên tài chính chuẩn bị nghỉ.

Hãy trả lời:

1. Vì sao nên dùng managed Google Account/Cloud Identity hoặc Google Workspace cho nhân viên? Tài khoản cá nhân có bất lợi vận hành gì?
2. Thiết kế hai cây: **OU/user/group** trong danh tính và **Organization/folder/project** trong Google Cloud. Mục đích mỗi cây khác nhau ra sao?
3. Đề xuất tên nhóm và role/scope cho Developers, QA, SRE và Finance. Những quyền nào cần tránh cấp ở scope organization?
4. Người dùng đã là thành viên `gcp-sre@example.com` nhưng vẫn không xem được Cloud Run production. Bạn sẽ kiểm tra gì?
5. Quy trình chuyển nhóm cho developer sang SRE phải thu hồi những quyền nào? Vì sao xóa khỏi một group chưa đủ?
6. Cộng tác viên 30 ngày sẽ được bảo vệ như thế nào? Hãy cân nhắc account quản lý, federation theo mô hình phù hợp, quyền có hạn và chủ sở hữu phê duyệt.
7. Khi nhân viên Finance nghỉ việc, những nguồn nào cần kiểm tra ngoài Google Group?
8. Khi Cloud Run runtime cần đọc Cloud Storage, vì sao nên dùng service account riêng thay vì tài khoản SRE?
9. Phân biệt sự kiện quản trị membership nhóm với sự kiện thay đổi IAM binding trên project: mỗi sự kiện thường nằm ở nguồn audit nào?
10. Nêu ba tiêu chí chứng minh thiết kế đạt mục tiêu bảo mật và ba tiêu chí chứng minh không làm gián đoạn vận hành.

**Gợi ý đối chiếu:** Một mô hình tốt cấp quyền qua nhóm và role hẹp tại project phù hợp, có tài khoản/nhóm sở hữu rõ, MFA cho người dùng, dịch vụ chạy bằng service identity, theo dõi quyền kế thừa, kiểm tra ngoại lệ cộng tác viên và quy trình offboarding xác nhận đến cùng. Tài chính có quyền billing đúng phạm vi mà không cần quyền triển khai Cloud Run/GKE.

## 15. Checklist vận hành Cloud Identity trong tổ chức

- [ ] Miền doanh nghiệp đã được xác minh; có chủ sở hữu quản trị DNS và tenant.
- [ ] Có danh sách Super Admin/delegated admin, quy trình phê duyệt và khôi phục truy cập.
- [ ] Đã xác định Organization resource, owner và cấu trúc folder/project.
- [ ] Phân biệt OU danh tính với folder tài nguyên; không giả định tự đồng bộ.
- [ ] Nhân viên dùng danh tính tổ chức với MFA/SSO và chính sách phiên phù hợp.
- [ ] Có quy trình tạo/sync/đổi nhóm/ngừng dùng tài khoản theo nguồn HR/IT.
- [ ] Google Groups có owner, quy tắc membership, quy trình cấp/thu hồi và định kỳ rà soát.
- [ ] IAM role được gán vào nhóm ở scope thấp nhất hợp lý; đã rà direct grant và inherited grant.
- [ ] Dịch vụ Compute Engine, GKE, Cloud Run và CI/CD dùng danh tính workload riêng, hạn chế khóa dài hạn.
- [ ] Quyền billing/FinOps được tách khỏi quyền chỉnh tài nguyên sản xuất.
- [ ] Có audit cho danh tính và cloud policy; có người nhận cảnh báo thay đổi nhạy cảm.
- [ ] Đã kiểm thử joiner, mover, leaver, tài khoản ngoài tổ chức và đường khôi phục khẩn cấp.
- [ ] Có kế hoạch rà soát tính năng theo phiên bản Cloud Identity/Workspace và chính sách hiện hành.

## 16. Tài liệu tham khảo

Khi triển khai trong tổ chức thật, cần kiểm tra trạng thái tính năng, giấy phép, giới hạn và giao diện mới nhất trong tài liệu chính thức:

- [Cloud Identity overview](https://cloud.google.com/identity/docs/overview)
- [Cloud Identity documentation](https://cloud.google.com/identity/docs)
- [Cloud Identity editions](https://cloud.google.com/identity/pricing)
- [Google Cloud resource hierarchy](https://cloud.google.com/resource-manager/docs/cloud-platform-resource-hierarchy)
- [IAM overview](https://cloud.google.com/iam/docs/overview)
- [IAM best practices](https://cloud.google.com/iam/docs/using-iam-securely)
- [Workforce Identity Federation](https://cloud.google.com/iam/docs/workforce-identity-federation)
- [Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation)
- [Google Workspace Admin Help](https://support.google.com/a/)

**Điểm cần nhớ:** Cloud Identity quản lý **danh tính và vòng đời người dùng**, còn Google Cloud IAM quản lý **quyền trên tài nguyên**. Cầu nối quan trọng nhất thường là **nhóm được quản trị chặt chẽ và IAM binding đúng phạm vi**. Với SSO/MFA, phân tách người dùng và workload, quy trình joiner–mover–leaver và audit rõ ràng, tổ chức mới có nền tảng an toàn để triển khai Compute Engine, GKE, Cloud Run, dịch vụ dữ liệu và quản lý chi phí ở quy mô nhiều project.
