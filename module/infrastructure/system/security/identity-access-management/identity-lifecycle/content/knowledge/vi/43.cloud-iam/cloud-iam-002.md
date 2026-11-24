# Cloud account

**Chương:** Cloud IAM  
**Bài học:** Cloud account  
**Phạm vi:** Tài khoản và ranh giới quản trị trong môi trường cloud, đặc biệt là cách tạo, sở hữu, phân quyền, chuyển giao, rà soát và chấm dứt quyền truy cập theo vòng đời danh tính **Joiner–Mover–Leaver (JML)**.

## 1. Cloud account là gì?

**Cloud account** là thuật ngữ có thể chỉ tài khoản đăng nhập của một người hoặc một đơn vị quản trị tài nguyên cloud, tùy ngữ cảnh. Khi thiết kế **Identity and Access Management (IAM)**, phải xác định chính xác đối tượng đang nói tới trước khi cấp hoặc thu hồi quyền:

1. **Tài khoản định danh (identity/user account):** Bản ghi đại diện cho người dùng tại Identity Provider (IdP), thư mục danh tính hoặc trong cloud, dùng để đăng nhập và liên kết với quyền truy cập.
2. **Tài khoản quản trị tài nguyên (cloud resource account):** Ranh giới logic chứa hoặc quản lý tài nguyên, chính sách, hạn mức và chi phí. Ví dụ: AWS account; những đơn vị có vai trò tương tự nhưng không đồng nhất là Azure subscription và Google Cloud project.
3. **Tài khoản máy (service/workload account):** Danh tính cho ứng dụng, pipeline hoặc workload, có thể được gắn quyền API mà không cần người dùng đăng nhập tương tác.
4. **Tài khoản sở hữu và thanh toán (organization/billing account):** Đối tượng gắn quản trị tổ chức, hợp đồng hoặc thanh toán; có thể có quan hệ với các đơn vị tài nguyên nhưng **không đồng nghĩa** với danh tính cá nhân.

Bài học tập trung vào **cloud resource account** như một ranh giới quản trị, sau đó nối với **vòng đời của các danh tính được quyền truy cập**. Việc tạo mới một AWS account hoặc Azure subscription **không tự động** tạo tài khoản định danh cho nhân viên; ngược lại, khi một nhân viên rời công ty, tổ chức thường chỉ cần thu hồi quyền của nhân viên đó khỏi các cloud account liên quan, không đóng mọi cloud account mà nhân viên từng truy cập.

### 1.1. Tại sao account boundary quan trọng?

Ranh giới account giúp tách môi trường dev/staging/production, nhóm sản phẩm, đơn vị kinh doanh, chủ sở hữu và phạm vi bảo mật. Sự tách biệt này làm giảm phạm vi tác động khi bị lộ quyền và giúp áp chính sách quản trị, hạn mức, giám sát, chi phí phù hợp.

Ví dụ, đội thanh toán và đội học tập cùng sử dụng cloud nhưng có tập dữ liệu nhạy cảm khác nhau. Tổ chức có thể cấp các đơn vị cloud riêng cho từng workload/môi trường. Người dùng được đăng nhập tập trung qua IdP, sau đó đảm nhận vai trò với phạm vi giới hạn tại đúng đơn vị được phân công.

**Phân biệt cốt lõi:** Cloud account xác định một phạm vi quản lý hoặc truy cập; **principal/identity** cho biết ai hoặc workload nào đang yêu cầu; **role/policy** quyết định principal được làm gì trên tài nguyên nào. Một account không tự mang ý nghĩa “mọi nhân viên đều được truy cập”.

## 2. So sánh mô hình account của AWS, Azure và Google Cloud

| Khía cạnh | AWS | Microsoft Azure | Google Cloud |
| --- | --- | --- | --- |
| Ranh giới quản trị tài nguyên tiêu biểu | **AWS account** | **Subscription**; resource group tổ chức tài nguyên trong subscription | **Project**; folder và organization tổ chức project |
| Cấu trúc quản trị cao hơn | AWS Organizations, Organizational Unit (OU) | Microsoft Entra tenant, management group | Organization, folder |
| Phạm vi quyền truy cập | IAM policy, role và resource policy; có thể bị giới hạn bởi cơ chế quản trị cấp tổ chức | Azure RBAC role assignment tại management group, subscription, resource group hoặc resource | Google Cloud IAM binding tại organization, folder, project hoặc tài nguyên hỗ trợ |
| Phân tách chi phí | Tài khoản và cơ chế billing hợp nhất, phân bổ theo dữ liệu chi phí | Subscription, billing scope và nhãn phân bổ chi phí | Project liên kết với Cloud Billing account, nhãn phân bổ chi phí |
| Cấp quyền người dùng tổ chức | IAM Identity Center hoặc cơ chế federation/role, tùy kiến trúc | Microsoft Entra ID kết hợp Azure RBAC | Google identity và/hoặc federation kết hợp Google Cloud IAM |
| Quyền đặc biệt cần chú ý | Root user của AWS account; role có quyền quản trị | Quyền cao trong tenant và Azure RBAC Owner/User Access Administrator | Organization Admin, Project Owner và các IAM role nhạy cảm khác |

Các khái niệm trên **tương đồng về mục đích quản trị**, nhưng không hoán đổi trực tiếp. Azure resource group không giống AWS account; Google Cloud Billing account không đồng nghĩa Google Cloud project. Chi tiết của kế thừa quyền, policy chặn quyền, giới hạn tổ chức và phân quyền dịch vụ cần kiểm tra theo nhà cung cấp.

### 2.1. Các ranh giới cần ghi nhớ

- **Organization/tenant:** Nơi quản trị danh tính tổ chức, chính sách cấp cao hoặc cấu trúc tài nguyên, tùy nhà cung cấp.
- **Account/subscription/project:** Đơn vị tài nguyên cần người sở hữu, vòng đời vận hành, kiểm soát quyền và giám sát riêng.
- **Resource group/folder/OU:** Cấu trúc gom nhóm để tổ chức, thừa kế chính sách hoặc áp quy tắc quản trị; ngữ nghĩa khác nhau giữa các hệ thống.
- **User, role, service account, workload principal:** Các danh tính hoặc vai trò có thể được đánh giá khi truy cập tài nguyên.
- **Billing account/scope:** Đơn vị tài chính có thể liên quan tới nhiều đơn vị tài nguyên; quyền truy cập tài chính và quyền truy cập tài nguyên cần kiểm soát riêng.

Trong tài liệu vận hành, nên dùng cụm từ chính xác như “AWS production account”, “Azure subscription của sản phẩm A”, “Google Cloud project staging”, tránh ghi chung “cloud account” khi đang phân công quyền hoặc đóng môi trường.

## 3. Quan hệ giữa cloud account và cloud identity

Giả sử có ba principal: kỹ sư phát triển, nhân viên kiểm toán và pipeline triển khai. Ba principal có thể cần truy cập cùng một AWS account, nhưng mỗi người hoặc workload phải nhận quyền khác nhau. Quan hệ truy cập không được suy ra từ việc cả ba đều thuộc chung công ty.

~~~mermaid
flowchart TD
    HR["HRIS / nguồn danh tính và trạng thái nhân sự"] --> IGA["Identity Lifecycle / IGA<br/>Joiner - Mover - Leaver"]
    IGA --> IDP["IdP / Directory<br/>User, group, MFA"]
    IGA --> PROV["Provisioning / API / SCIM<br/>Đồng bộ tài khoản đích"]
    IDP --> FED["SSO / Federation<br/>SAML hoặc OIDC"]
    FED --> AUTH["Cloud IAM<br/>Principal, role, policy"]
    WORK["Workload registry / CI-CD<br/>Owner, issuer, môi trường"] --> WF["Workload identity / federation"]
    WF --> AUTH
    PROV --> APP["Tài khoản đích hỗ trợ provisioning"]
    AUTH --> A["Account / Subscription / Project A<br/>Dev"]
    AUTH --> B["Account / Subscription / Project B<br/>Production"]
    A --> AUD["Audit logs / Security monitoring"]
    B --> AUD
    IGA --> AUD
~~~

Sơ đồ là mô hình logic, không tuyên bố mọi cloud đều có cùng cấu trúc hoặc hỗ trợ SCIM cho tất cả account. **SCIM** chủ yếu hỗ trợ quản lý user/group ở các hệ thống đích có tích hợp; việc **tạo AWS account, Azure subscription hoặc Google Cloud project** thường cần workflow và API provisioning tài nguyên riêng.

### 3.1. Ai xác thực, ai quyết định quyền?

Một luồng truy cập người dùng tiêu biểu:

1. Hệ thống nhân sự xác nhận người dùng đang có tư cách làm việc hợp lệ.
2. IGA/lifecycle đưa người dùng vào các nhóm phù hợp và ghi nhận quyền cần phê duyệt.
3. Người dùng đăng nhập IdP qua SSO; các chính sách xác thực như MFA, thiết bị hoặc rủi ro được áp dụng.
4. Hệ thống cloud tin cậy danh tính theo federation đã cấu hình và xác định principal/role/session tương ứng.
5. Cloud IAM đánh giá quyền thực tế trên account/subscription/project và tài nguyên đích theo chính sách của nền tảng.
6. Sự kiện đăng nhập, thay đổi quyền, thao tác quản trị và kết quả rà soát được ghi lại.

**SSO giải quyết đăng nhập**, còn quyền truy cập cloud được quản lý bằng role, policy, assignment hoặc binding. Nếu người dùng bị khóa ở IdP, những session/token đã tồn tại có thể vẫn hiệu lực trong một khoảng thời gian tùy nền tảng; cần cơ chế thu hồi hoặc kiểm tra hiệu lực riêng khi xử lý sự kiện khẩn cấp và Leaver.

### 3.2. Tài khoản nội bộ cloud và danh tính tập trung

Cloud có thể tồn tại những danh tính ngoài IdP: user nội bộ, root/owner đặc biệt, guest, service account, access key, role dành cho bên thứ ba hoặc danh tính khẩn cấp. Chúng không tự biến mất khi xóa một người khỏi directory.

Vì thế, quản lý cloud account phải có **inventory các đường truy cập**, bao gồm cả quyền gắn trực tiếp, quyền qua nhóm, role assumption, resource-based access, danh tính workload và cơ chế quyền cấp tổ chức. Một cuộc rà soát chỉ nhìn danh sách user trong IdP là chưa đủ.

## 4. Thiết kế cloud account trong tổ chức

Một account mới cần được coi như một tài nguyên có **owner và vòng đời rõ ràng**, không phải chỉ là thao tác cấp một “sandbox” vô danh.

| Thuộc tính quản trị | Nội dung cần quản lý | Giá trị ví dụ |
| --- | --- | --- |
| Định danh account | ID do nhà cung cấp cấp và loại đối tượng | AWS account ID, Azure subscription ID, GCP project ID |
| Phạm vi | Nhà cung cấp, tenant/organization, OU/folder/management group | Org chính, nhóm platform |
| Ownership | Owner nghiệp vụ, owner kỹ thuật, người thay thế | Product Lead, Platform Team |
| Môi trường | Dev, test, staging, production hoặc sandbox | production |
| Mục đích | Sản phẩm/dịch vụ, dữ liệu và ranh giới kinh doanh | payment-api |
| Độ nhạy dữ liệu | Phân loại dữ liệu, yêu cầu lưu trữ hoặc mã hóa | confidential |
| Phân bổ chi phí | Cost center, billing reference, giới hạn ngân sách | CC-PLATFORM-07 |
| Chính sách truy cập | Nhóm được phép, role chuẩn, cơ chế quyền cao | platform-operators, JIT admin |
| Trạng thái vòng đời | Requested, provisioning, active, retiring, closed | active |
| Bằng chứng kiểm soát | Thời điểm tạo, phê duyệt, baseline, log, kỳ rà soát | CHG-2401, audit record |

**Định danh được provider cấp** phải là khóa quản lý đáng tin cậy, vì tên và email gắn với account có thể thay đổi. Metadata như owner hoặc cost center cũng cần có lịch sử thay đổi.

### 4.1. Account strategy và ranh giới cô lập

Các cách tổ chức thường gặp:

- **Tách theo môi trường:** Production được bảo vệ bằng ranh giới và chính sách khác dev/test; rủi ro ở môi trường thử nghiệm ít ảnh hưởng sản xuất hơn.
- **Tách theo workload hoặc sản phẩm:** Mỗi dịch vụ trọng yếu có account/subscription/project được gắn owner; dễ kiểm kê tài nguyên và phân bổ chi phí.
- **Tách theo mức dữ liệu/tuân thủ:** Workload xử lý dữ liệu nhạy cảm nhận chính sách và quyền vận hành riêng.
- **Tách chức năng nền tảng:** Logging, security tooling, network hub hoặc các dịch vụ chung có ranh giới chuyên trách nếu kiến trúc yêu cầu.

Không có một số lượng account tối ưu cho mọi tổ chức. Quá ít ranh giới dễ mở rộng quyền và phạm vi sự cố; quá nhiều ranh giới thiếu quản trị tạo account mồ côi và phát sinh chi phí. Thiết kế cần đi cùng khả năng tự động hóa, kiểm kê và decommission.

### 4.2. Baseline khi tạo account

Mỗi account nên được áp chính sách nền tảng ngay khi cấp phát:

1. Đặt account vào đúng organizational hierarchy và nhóm chính sách quản trị.
2. Liên kết billing/cost center, thiết lập giám sát ngân sách và nhãn bắt buộc nếu được hỗ trợ.
3. Bật audit log, tập trung lưu trữ log có chính sách bảo vệ và thời hạn lưu.
4. Áp chính sách an toàn mặc định về IAM, vị trí triển khai, mã hóa, mạng và khóa nếu phù hợp.
5. Cấu hình group/role chuẩn để truy cập qua federation và tránh phân phát key tĩnh.
6. Thiết lập danh tính khẩn cấp và quyền quản trị đặc biệt theo quy trình được kiểm soát.
7. Đăng ký owner, inventory resource và thời điểm rà soát tiếp theo.

Không nên cho triển khai workload production trước khi baseline cần thiết đã được áp dụng và kiểm chứng.

## 5. Vòng đời của một cloud resource account

Vòng đời account tài nguyên và vòng đời người dùng liên quan nhưng **khác nhau**. Một account thường sống lâu hơn nhiệm kỳ của nhân viên. Mô hình trạng thái có thể triển khai như sau:

~~~mermaid
stateDiagram-v2
    [*] --> Requested
    Requested --> Provisioning: Được duyệt
    Requested --> Rejected: Từ chối
    Provisioning --> Active: Baseline và kiểm chứng PASS
    Provisioning --> Failed: Tạo hoặc kiểm chứng lỗi
    Failed --> Provisioning: Khắc phục / retry
    Active --> Restricted: Phát hiện rủi ro
    Restricted --> Active: Xử lý, xác minh
    Active --> Retiring: Đã duyệt dừng sử dụng
    Restricted --> Retiring: Chấm dứt
    Retiring --> Closed: Di trú dữ liệu / đóng quyền / kiểm chứng
    Rejected --> [*]
    Closed --> [*]
~~~

| Trạng thái | Điều kiện cần | Kiểm soát quan trọng |
| --- | --- | --- |
| Requested | Có yêu cầu, người phê duyệt và owner | Kiểm tra trùng account, phạm vi, ngân sách và phân loại dữ liệu |
| Provisioning | Yêu cầu hợp lệ đang được thực hiện | API và IaC có idempotency, log thao tác, baseline bảo mật |
| Active | Đã tạo và xác minh đủ điều kiện sử dụng | Quyền tối thiểu, rà soát, giám sát, ownership rõ |
| Restricted | Phát hiện rủi ro hoặc vi phạm cần hạn chế hoạt động | Chặn/giới hạn quyền theo mức độ; bảo tồn bằng chứng |
| Retiring | Được phê duyệt chấm dứt hoặc thay thế account | Lập danh sách tài nguyên, dependencies, dữ liệu, access path |
| Closed | Đã xử lý dữ liệu và quyền theo quy trình, có xác minh | Lưu bằng chứng đóng; bảo đảm không còn đường truy cập ngoài ý muốn |

Các tên trạng thái chỉ là mô hình quản trị nội bộ. Nhà cung cấp có quy trình đóng tài khoản, xóa subscription/project và thời gian khôi phục hoặc lưu giữ khác nhau. Không được coi việc “đánh dấu Closed trong CMDB” là bằng chứng nhà cung cấp đã hoàn tất thao tác tương ứng.

### 5.1. Account vending: cấp phát có kiểm soát

**Account vending** là luồng tự phục vụ có kiểm duyệt để tạo account/subscription/project theo tiêu chuẩn. Yêu cầu đầu vào có thể gồm tên workload, owner, mục đích, môi trường, loại dữ liệu, yêu cầu mạng, vùng, cost center và nhóm truy cập.

~~~mermaid
sequenceDiagram
    participant R as Người yêu cầu
    participant P as Portal / Workflow
    participant A as Người phê duyệt
    participant V as Account provisioning / IaC
    participant C as Cloud provider
    participant G as Governance / Inventory
    R->>P: Tạo yêu cầu + owner + môi trường
    P->>A: Duyệt ngân sách và quyền sở hữu
    A-->>P: Quyết định và điều kiện
    P->>V: Tạo theo mẫu đã duyệt
    V->>C: Tạo account / subscription / project
    C-->>V: ID và kết quả
    V->>C: Cấu hình IAM, logging, policy, billing
    V->>G: Đăng ký account, owner, baseline
    V->>C: Đọc lại cấu hình và quyền
    C-->>V: Trạng thái thực tế
    V-->>P: Kết quả PASS hoặc cần xử lý
~~~

Hệ thống phải xử lý được trường hợp tạo account thành công nhưng cấu hình baseline thất bại: trạng thái khi đó **chưa thể là Active**. Cần phát hiện tài nguyên tạo dở, khóa tương quan để tránh tạo trùng khi retry, và người chịu trách nhiệm xử lý.

### 5.2. Thay đổi account đang hoạt động

Khi account chuyển sản phẩm, team, tổ chức, môi trường hoặc mức dữ liệu, quy trình cập nhật ít nhất:

- Owner, cost center, policy hierarchy và người chịu trách nhiệm vận hành.
- Nhóm được truy cập và role assignment/binding thực tế.
- Trust với account khác, provider khác hoặc bên thứ ba.
- Tài khoản máy, pipeline, secret, hạ tầng mạng và khóa mã hóa liên quan.
- Yêu cầu giám sát, backup, lưu trữ và kiểm toán.

Nếu account được chuyển giao từ đội A sang đội B, quyền của đội A cần được thu hồi sau khi chuyển giao những phụ thuộc được phép giữ lại. Chỉ đổi nhãn owner mà không rà soát quyền là một lỗi quản trị thường gặp.

### 5.3. Chấm dứt account và xử lý tài nguyên

Account chứa workload có thể có database, bucket, DNS, khóa mã hóa, snapshot, log, secret, service account và kết nối mạng liên account. Trước khi đóng, phải xác nhận phạm vi dữ liệu cần lưu/di trú, thời hạn lưu giữ, trách nhiệm ứng dụng và đường truy cập vận hành.

Luồng khuyến nghị:

1. Phê duyệt nghỉ sử dụng và xác định account/tenant/project ID chính xác.
2. Khảo sát workload, tài nguyên, data dependency, network peering, trust, role và IAM binding.
3. Chuyển dữ liệu hoặc lưu giữ theo chính sách; cập nhật DNS, pipeline, monitoring và phụ thuộc liên vùng/liên account.
4. Chặn triển khai mới; thu hồi người dùng, workload credentials, cross-account access và quyền bên thứ ba.
5. Xác minh không còn traffic/chi phí hoặc sự phụ thuộc chưa được xử lý, theo mức độ kiểm soát có thể thực hiện.
6. Thực hiện thao tác đóng/xóa theo khả năng nhà cung cấp; ghi nhận trạng thái xác nhận và thời hạn có thể khôi phục nếu có.
7. Giữ log và bằng chứng kiểm toán ở vị trí không bị xóa cùng account theo chính sách tổ chức.

**Không xóa account một cách máy móc** khi có dữ liệu cần lưu, yêu cầu pháp lý hoặc ứng dụng chưa được chuyển giao. Chấm dứt vòng đời phải kết hợp kiểm soát quyền và bảo toàn dữ liệu cần thiết.

## 6. Joiner–Mover–Leaver đối với quyền truy cập cloud account

Mô hình JML được áp dụng cho **các danh tính có quyền truy cập account**, còn account tài nguyên có vòng đời ở phần trên. Hai luồng phải liên kết qua inventory và hồ sơ quyền:

| Giai đoạn | Sự kiện nguồn | Công việc trên account đích | Kết quả cần xác minh |
| --- | --- | --- | --- |
| **Joiner** | Nhân viên mới, đối tác được chấp thuận | Liên kết identity với nhóm/role; cấp phạm vi account đúng công việc và thời hạn | Người dùng chỉ có quyền cần thiết trên account được duyệt |
| **Mover** | Đổi team, chức vụ, dự án, môi trường | Thu hồi role và nhóm ở account cũ; cấp quyền account mới theo phê duyệt; rà soát access path trực tiếp | Không còn quyền cũ hoặc xung đột quyền chưa được chấp thuận |
| **Leaver** | Nghỉ việc, hết hợp đồng, tài khoản bị đình chỉ | Khóa IdP, thu hồi quyền IAM tại mọi account liên quan, xử lý key/token/session, guest, ownership | Không còn đường truy cập hợp lệ được xác định ở account đích |

### 6.1. Joiner: ghép đúng identity và đúng account

Một nhân viên mới cần được gắn **immutable identity ID** từ nguồn đáng tin cậy, thay vì dùng email làm khóa duy nhất. Email có thể thay đổi, và địa chỉ đã ngừng sử dụng có thể tái cấp.

Ví dụ, hồ sơ nhân sự có ID **EMP-2874**. Người dùng được tạo trên IdP và tham gia nhóm **data-readers** sau khi có phê duyệt; nhóm này chỉ ánh xạ đến role đọc tại **GCP project analytics-dev**. Không có lý do để cấp quyền Owner trên toàn organization.

Tại thời điểm cấp quyền, nên lưu identity ID, loại principal, account ID, resource scope, role, căn cứ phê duyệt, owner phê duyệt, thời điểm hiệu lực và ngày hết hạn nếu có. Những thông tin này tạo nền tảng cho rà soát và Leaver.

### 6.2. Mover: chấm dứt quyền thuộc vai trò cũ

Nhân viên chuyển từ vận hành payment-production sang phân tích dữ liệu. Quy trình đúng cần thực hiện đồng thời **tính quyền mới và thu hồi quyền cũ**:

1. Nhận sự kiện thay đổi từ HRIS hoặc nguồn được ủy quyền.
2. Tính quyền mong muốn cho role/team mới, bao gồm quyền được duyệt có thời hạn.
3. Truy vấn quyền thực tế ở các account đích: nhóm, role, policy, tài khoản local, resource policy, trust, key và session liên quan.
4. Thu hồi quyền quản trị payment-production và cấp quyền analytics đúng phạm vi.
5. Kiểm tra lại effective access; xử lý ngoại lệ và quyền xung đột theo nguyên tắc separation of duties.

Việc thêm nhóm mới mà giữ mọi quyền cũ gây **privilege accumulation**, đặc biệt nguy hiểm với những tài khoản quản trị production.

### 6.3. Leaver: kiểm soát mọi đường truy cập

Một thao tác “disable user ở IdP” thường chặn đăng nhập SSO mới nhưng chưa bảo đảm:

- Các access key hoặc credential độc lập đã bị vô hiệu hóa.
- Phiên truy cập/tạm quyền đã cấp bị hủy ngay, nếu nhà cung cấp hỗ trợ thu hồi.
- Quyền trực tiếp tại account, project, subscription hoặc tài nguyên đã được xóa.
- Guest account, tài khoản local, quyền bên thứ ba và role đặc biệt đã được rà soát.
- Pipeline và service account do người rời đi quản lý đã có owner mới và secret liên quan được thay đổi khi cần.

Leaver cần lấy account inventory để biết nhân viên hiện có quyền ở đâu; điều này quan trọng hơn việc kiểm tra danh sách những nơi nhân viên từng “đăng nhập gần đây”.

## 7. Cấp quyền bên trong và giữa các cloud account

### 7.1. Role-Based Access Control (RBAC)

RBAC đóng gói quyền theo chức trách, ví dụ **Developer**, **ReadOnlyAuditor**, **DeploymentOperator**, **BillingViewer**. Quyền phải giới hạn theo môi trường và đơn vị tài nguyên.

| Vai trò nghiệp vụ | Phạm vi minh họa | Quyền ví dụ | Điều kiện bổ sung |
| --- | --- | --- | --- |
| Developer | Project dev của nhóm | Đọc log, quản lý tài nguyên phát triển cần thiết | Không có quyền thay đổi IAM production |
| Deployment operator | Một account production đã xác định | Thực hiện deployment đã duyệt | Phiên ngắn hạn, có bằng chứng triển khai |
| Security auditor | Nhiều account theo phạm vi audit | Xem chính sách, cấu hình và log phù hợp | Quyền đọc, tránh thao tác ghi nếu không cần |
| Billing analyst | Billing scope/cost center được phân công | Xem phân bổ chi phí, ngân sách | Không suy ra quyền đọc dữ liệu ứng dụng |
| Account owner | Một account/subscription/project | Điều phối vận hành và phê duyệt quyền | Quyền kỹ thuật admin chỉ cấp khi thật sự cần |

**Owner nghiệp vụ** không nhất thiết cần role IAM cao nhất. Người chịu trách nhiệm chi phí, dữ liệu hoặc vòng đời account có thể quản trị quy trình thông qua phê duyệt trong khi đội platform thực thi thay đổi kỹ thuật.

### 7.2. Attribute-Based Access Control (ABAC)

ABAC có thể dùng thuộc tính principal, tài nguyên và ngữ cảnh để ra quyết định khi hệ thống hỗ trợ. Ví dụ, một chính sách cho phép nhóm phát triển thao tác trên resource có nhãn **environment=dev** và **team=learning** với điều kiện phù hợp.

~~~yaml
# Giả mã chính sách, không phải cú pháp IAM của nhà cung cấp cụ thể
principal:
  employmentStatus: active
  department: platform
resource:
  environment: dev
  owningTeam: platform
request:
  action: service.logs.read
policy:
  allowWhen:
    - principal.employmentStatus == active
    - principal.department == resource.owningTeam
    - resource.environment == dev
~~~

Thuộc tính ảnh hưởng quyền cần có nguồn đáng tin cậy và quy tắc cập nhật. Một nhãn do người dùng tự sửa có thể không phù hợp để làm điều kiện bảo mật. Hơn nữa, ABAC không tự thu hồi mọi role gắn trực tiếp; hệ thống JML vẫn phải đối soát.

### 7.3. Phân quyền và trust giữa account

Một workload ở account A có thể cần truy cập tài nguyên trong account B. Cách thiết lập cụ thể phụ thuộc nhà cung cấp và dịch vụ, thường có quan hệ trust/federation, role hoặc resource policy. Điều cần kiểm tra:

- **Ai được tin cậy:** Principal nguồn, nhà phát hành token (issuer), account/tenant nguồn, audience và điều kiện subject nếu phù hợp.
- **Được làm gì:** Action và resource cụ thể, tránh cấp quyền toàn cục.
- **Khi nào:** Thời hạn credential/session, môi trường được dùng và các điều kiện ngữ cảnh.
- **Ai phê duyệt và sở hữu:** Owner ở cả nguồn lẫn đích, ngày hết hạn nếu là tích hợp tạm thời.
- **Thu hồi ra sao:** Xóa trust và grant cả ở những đường phù hợp, thu hồi credential, kiểm chứng request không còn được cấp phép.

Ví dụ, pipeline CI/CD tại repository đã duyệt dùng OIDC federation để nhận quyền deploy vào một account staging. Trust nên giới hạn issuer/audience và claim của repository/nhánh/môi trường nếu nền tảng hỗ trợ, thay vì chấp nhận mọi token của một tổ chức CI/CD.

### 7.4. Quyền thực tế không chỉ đến từ một role

Trong hệ thống phức tạp, effective access có thể chịu ảnh hưởng của nhiều lớp: quyền qua nhóm, policy được gắn trực tiếp, resource policy, role assumption, quyền kế thừa, explicit deny, hạn chế cấp tổ chức và điều kiện đăng nhập. Một hệ thống không có quyền ở một lớp vẫn có thể được cấp qua đường khác; ngược lại, quyền được gắn chưa chắc có hiệu lực nếu bị policy cấp trên ngăn.

Vì thế, kiểm tra Leaver/Mover cần đánh giá **tập đường truy cập thực sự tồn tại**, không chỉ đếm số lượng role gắn với một user.

## 8. Service account và workload identity trong cloud account

Service account và workload principal được dùng cho ứng dụng, job, máy ảo, container, function, automation hoặc CI/CD. Những danh tính này phải được quản trị độc lập với tài khoản đăng nhập của người phát triển.

| Cách xác thực workload | Ví dụ áp dụng | Lưu ý quản trị |
| --- | --- | --- |
| Managed identity / instance role | Ứng dụng chạy trong cloud gọi API cloud | Giới hạn quyền theo workload và tài nguyên; kiểm tra owner khi workload đổi nhóm |
| Workload identity federation | Pipeline hoặc nền tảng bên ngoài trao đổi token lấy credential ngắn hạn | Ràng buộc trust với issuer, audience, subject và môi trường |
| Service account với token ngắn hạn | Job hoặc container được cấp token qua nền tảng | Quản lý gắn kết với workload; ghi log và quyền tối thiểu |
| Key/secret tĩnh khi bắt buộc | Tích hợp cũ chưa hỗ trợ federation | Lưu trong secret manager, rotation, giám sát và kế hoạch thay thế |

**Không dùng chung tài khoản người thật cho automation.** Nếu script triển khai chạy bằng user cá nhân, nghỉ việc có thể khiến pipeline ngừng hoạt động; tệ hơn, credential cũ có thể tiếp tục tồn tại ngoài quy trình Leaver.

Danh tính workload nên có: ID, account/project/subscription được phép truy cập, mục đích, owner chính/phụ, môi trường, code repository/pipeline liên quan, quyền, phương thức xác thực, hạn dùng và kỳ rà soát.

Vòng đời workload:

1. **Joiner:** Tạo danh tính qua workflow/IaC được duyệt; gắn owner, phạm vi, policy và log.
2. **Mover:** Khi service đổi account, nhóm hoặc môi trường, cập nhật role/trust, vô hiệu hóa credential cũ và kiểm chứng quyền thực tế.
3. **Leaver:** Khi service, pipeline hoặc tích hợp bị hủy, thu hồi danh tính/role/trust/secret và xác minh không còn API call hợp lệ.

## 9. Quyền quản trị cao, root và break-glass

Cloud account thường có những đường truy cập rất mạnh: root user, role Owner, global/privileged admin hoặc quyền thay đổi IAM. Đây là đối tượng kiểm soát đặc biệt:

- Ưu tiên quản trị theo phiên tạm thời, phê duyệt và just-in-time privileged access nếu nền tảng có cơ chế phù hợp.
- Dùng phương thức xác thực chống phishing cho danh tính người có quyền cao và bảo vệ thiết bị/trạm quản trị theo chính sách.
- Giới hạn phạm vi; không dùng quyền cao cho tác vụ thường ngày hoặc automation.
- Bảo vệ và kiểm tra danh tính root, tài khoản khẩn cấp và phương thức khôi phục; thiết lập cảnh báo khi sử dụng.
- Có đường xử lý sự cố khi IdP/federation không hoạt động, được kiểm thử có kiểm soát và có audit trail.
- Rà soát quyền có khả năng gán/sửa role: quyền quản lý IAM có thể gián tiếp dẫn tới nâng đặc quyền.

**Break-glass** là quyền truy cập khẩn cấp, nên được dùng trong tình huống đã định nghĩa và được ghi nhận đầy đủ. Để giảm rủi ro, không dùng tài khoản khẩn cấp làm đường truy cập vận hành thường xuyên.

## 10. Rà soát quyền và phát hiện truy cập tồn dư

Một hệ thống quản lý quyền tốt phải biết đồng thời:

- **Desired access:** Quyền được phép dựa trên trạng thái nhân sự, chức trách, owner, phê duyệt, mục đích và thời hạn.
- **Actual access:** Quyền đang cấu hình tại cloud account/tenant/project, bao gồm đường truy cập trực tiếp, kế thừa, qua nhóm, trust, service account và key.
- **Effective access:** Quyền thực tế được IAM cho phép sau khi xét các lớp policy và ngữ cảnh phù hợp.

~~~text
identity = resolveStableIdentityId(sourceEvent)
targets = discoverRelevantAccounts(identity)

for target in targets:
    desired = approvedAccess(identity, target)
    actual = queryGrantsGroupsRolesAndTrust(identity, target)
    stale = normalize(actual) - normalize(desired)

    for grant in stale:
        revokeWithAudit(grant)

    verifyEffectiveAccess(identity, target)
    recordResultOrEscalate(identity, target)
~~~

Đây là **giả mã quy trình**, không phải công thức tính được mọi loại effective access. Vì IAM có deny, quyền kế thừa và điều kiện khác nhau giữa nhà cung cấp, bước xác minh có thể cần truy vấn policy, mô phỏng quyền hoặc thực hiện thử nghiệm truy cập được cho phép.

### 10.1. Access review định kỳ

Một đợt review nên cung cấp cho owner đủ ngữ cảnh để quyết định:

| Trường | Mục đích |
| --- | --- |
| Principal ID và loại danh tính | Biết đây là nhân viên, guest, đối tác, service account hay workload |
| Account ID và phạm vi quyền | Xác định cloud và tài nguyên bị ảnh hưởng |
| Role/policy/binding cụ thể | Hiểu quyền có thể thực hiện |
| Nguồn cấp quyền | Group, assignment trực tiếp, federation, resource policy hoặc cơ chế khác |
| Lý do và người phê duyệt | Xác nhận nhu cầu nghiệp vụ còn hợp lệ |
| Lần sử dụng gần nhất nếu có | Một tín hiệu để xem xét, không phải bằng chứng duy nhất |
| Ngày bắt đầu, hết hạn, lần review cuối | Hỗ trợ xử lý quyền tồn tại quá lâu |
| Quyết định và bằng chứng thu hồi | Chứng minh thay đổi thực sự có hiệu lực |

Tần suất review nên căn cứ mức rủi ro. Quyền quản trị production, external access, tài khoản khẩn cấp và key tĩnh thường cần kiểm soát chặt hơn quyền đọc ở môi trường thử nghiệm.

### 10.2. Quy trình xử lý sai lệch

~~~mermaid
flowchart TD
    A["Nhận sự kiện JML hoặc lịch rà soát"] --> B["Truy vấn principal và account inventory"]
    B --> C["Tính desired / actual access"]
    C --> D{"Có grant không còn hợp lệ?"}
    D -->|Không| E["Lưu kết quả kiểm chứng"]
    D -->|Có| F["Thu hồi grant / trust / credential"]
    F --> G["Đọc lại trạng thái ở cloud target"]
    G --> H{"Quyền cũ đã hết hiệu lực?"}
    H -->|Có| E
    H -->|Không| I["Cảnh báo, ghi ngoại lệ có owner và thời hạn"]
    I --> G
~~~

Việc gửi API thu hồi thành công chưa đủ để ghi “hoàn tất” nếu chưa xác minh trạng thái đích. Khi một số phiên truy cập không thể thu hồi ngay, cần ghi rõ giới hạn, thời hạn hết hiệu lực dự kiến và biện pháp giảm rủi ro đã áp dụng.

## 11. Tình huống thực tế: chuyển nhóm rồi rời công ty

Một công ty vận hành ba đơn vị cloud:

| Đối tượng | Mục đích | Owner |
| --- | --- | --- |
| AWS account **prod-payments** | Dịch vụ thanh toán production | Payment Platform |
| Azure subscription **data-dev** | Hạ tầng phát triển phân tích dữ liệu | Data Platform |
| GCP project **audit-reporting** | Tập hợp dữ liệu log đã chọn cho báo cáo | Security Operations |

Nhân viên **An** (identity ID nội bộ **EMP-2874**) đang làm việc ở đội Payment Platform.

**Joiner:** HRIS kích hoạt hồ sơ của An; IdP tạo/đồng bộ danh tính. An được vào nhóm vận hành thanh toán và nhận role đọc log ở prod-payments. Việc can thiệp production yêu cầu phiên được duyệt có thời hạn. Hệ thống ghi nhận idempotent grant và kiểm tra account thực tế.

**Mover:** An chuyển sang Data Platform. Nhóm Data Platform duyệt quyền phù hợp tại data-dev. Workflow **thu hồi** quyền đọc log và quyền vận hành đã cấp ở prod-payments, xóa membership của nhóm Payment Platform, kiểm tra grant trực tiếp còn sót; sau đó cấp quyền mới ở data-dev. Account prod-payments vẫn tiếp tục vận hành với owner Payment Platform.

**Leaver:** HRIS thông báo An nghỉ việc. IdP disable danh tính, các cloud target thu hồi assignment/binding còn lại. Workflow rà soát session, key, guest account và ngoại lệ. Nếu An là owner khai báo của một pipeline, Data Platform chuyển ownership sang nhóm vận hành phù hợp và thay credential liên quan khi cần. Kiểm chứng cuối cùng không còn quyền truy cập cloud của An.

Ví dụ sự kiện audit từ hệ thống lifecycle (dữ liệu giả định):

~~~json
{
  "eventId": "JML-MOVE-0135",
  "identityId": "EMP-2874",
  "eventType": "mover",
  "source": "HRIS",
  "accountRef": "aws:prod-payments",
  "previousEntitlements": ["payments-log-reader"],
  "desiredEntitlements": [],
  "operation": "revoke",
  "status": "verification_pending",
  "approvedChange": "CHG-2401",
  "occurredAt": "2026-11-23T07:00:00Z"
}
~~~

Trạng thái **verification_pending** chỉ cho biết đã ghi nhận yêu cầu đang đợi xác minh. Khi quyền cũ đã thực sự bị thu hồi ở đích, hệ thống mới ghi kết quả verified cùng thời điểm và bằng chứng tương ứng.

### 11.1. Trường hợp account bị chuyển giao hoặc ngừng sử dụng

Sau một năm, công ty quyết định hợp nhất các workload dev và đóng subscription data-dev. Đây là **vòng đời của đơn vị tài nguyên**, độc lập với việc An đã nghỉ. Đội platform phải di chuyển các workload còn sống, kiểm kê secret và role, cập nhật billing, thu hồi trust, lưu các audit log cần thiết rồi thực hiện quy trình đóng subscription theo provider.

Ví dụ này minh họa hai luồng khác nhau nhưng liên kết dữ liệu: **JML của người dùng** và **lifecycle của account tài nguyên**. Account inventory và quyền thực tế ở đích là cầu nối để bảo đảm không còn truy cập tồn dư.

## 12. Các sự cố quản trị cloud account thường gặp

| Sự cố | Hậu quả có thể xảy ra | Kiểm soát thực tế |
| --- | --- | --- |
| **Shadow account** được tạo ngoài account vending | Không có owner, billing và chính sách nền tảng | Khám phá account định kỳ, kiểm soát tạo mới, đối soát inventory |
| **Tài khoản mồ côi** sau thay đổi tổ chức | Không ai nhận trách nhiệm cấp/thu hồi quyền hoặc chi phí | Bắt buộc owner chính/phụ, workflow chuyển giao |
| **Stale role** sau Mover | Nhân viên giữ quyền ở team/account cũ | JML truy vấn actual access và thu hồi có xác minh |
| **Cloud-local user** nằm ngoài SSO | Lỗ hổng khi disable IdP, khó audit | Hạn chế tài khoản local, quản lý inventory và quy trình Leaver |
| **Cross-account trust quá rộng** | Danh tính ngoài phạm vi nhận được quyền | Giới hạn principal, issuer/audience và ngữ cảnh |
| **Access key dài hạn hoặc dùng chung** | Credential còn hiệu lực sau nghỉ việc, dễ rò rỉ | Federation/managed identity, rotation, owner, expiry |
| **Role quá rộng ở account production** | Phạm vi ảnh hưởng lớn khi bị chiếm quyền | Least privilege, giới hạn scope và quyền cao có thời hạn |
| **Đóng account khi chưa di chuyển dữ liệu** | Mất dịch vụ, đứt tích hợp, rủi ro mất dữ liệu | Checklist dependency, migration và phê duyệt đóng |
| **Log chỉ nằm trong account sắp xóa** | Mất bằng chứng để điều tra và kiểm toán | Tập trung log độc lập với vòng đời account nguồn |
| **Sao chép role giữa cloud theo tên** | Áp quyền sai vì ngữ nghĩa và scope khác nhau | Đánh giá action/resource/provider cụ thể |

## 13. Kiểm toán, vận hành và chỉ số

Cloud account governance cần hai lớp bằng chứng:

**Bằng chứng quản trị account:** Ai yêu cầu và phê duyệt account; account ID; đơn vị sở hữu; vị trí trong tổ chức; baseline cấu hình; liên kết billing; trạng thái; lịch sử đổi owner và đóng account.

**Bằng chứng truy cập:** Ai hoặc workload nào được cấp quyền; nguồn quyền; thời điểm phê duyệt; giới hạn phạm vi/thời gian; đăng nhập hoặc sử dụng key; thay đổi IAM; sự kiện JML; kết quả thu hồi và xác minh.

Một số chỉ số phù hợp:

- **Tỷ lệ account có owner hợp lệ:** Account đang hoạt động có owner chính/phụ, cost center và kỳ rà soát xác định.
- **Tỷ lệ baseline compliance:** Account có đủ log, guardrail, phân loại và cấu hình bắt buộc.
- **Số account shadow/orphan:** Account chưa có nguồn tạo hợp lệ, owner hoặc lý do tồn tại.
- **Thời gian hoàn tất JML:** Từ hiệu lực sự kiện nguồn tới khi tất cả cloud target xác minh quyền tương ứng.
- **Tỷ lệ quyền tồn dư:** Grant còn tồn tại sau Mover/Leaver so với tập quyền phải thu hồi.
- **Số credential dài hạn chưa có owner/rotation:** Ưu tiên credential của tài khoản máy và privileged principal.
- **Tỷ lệ review hoàn tất có bằng chứng:** Quyết định review được đối chiếu bằng trạng thái thật tại đích.

Chỉ số nên được phân nhóm theo môi trường và độ nhạy cảm, bởi một stale admin grant ở production nghiêm trọng hơn một quyền đọc hạn chế ở sandbox.

### 13.1. Kiểm tra và xử lý sự cố

Khi nghi ngờ account bị chiếm quyền hoặc bị cấp quyền trái phép:

1. Xác định account/subscription/project ID, principal và thời điểm nghi vấn.
2. Bảo toàn log và dấu vết liên quan; truy vấn thay đổi IAM, trust, credential và API activity.
3. Chặn hoặc giới hạn các đường truy cập bị ảnh hưởng theo quy trình ứng cứu.
4. Rà soát cả principal người và workload, kể cả cross-account trust và quyền cấp qua resource policy.
5. Xác minh effective access sau thay đổi, ghi nhận phạm vi ảnh hưởng và theo dõi phục hồi dịch vụ.

Các bước trên là khung kiểm soát; hành động thực thi trên từng nhà cung cấp cần dựa vào công cụ, kiến trúc và quy trình ứng cứu đã được tổ chức phê duyệt.

## 14. Checklist thực hành

Khi được giao mở hoặc quản lý một cloud account, hãy kiểm tra:

1. **Đúng định nghĩa:** Đây là AWS account, Azure subscription, Google Cloud project hay tài khoản danh tính/user/service account?
2. **Đúng owner:** Có owner nghiệp vụ và kỹ thuật, môi trường, mục đích, cost center và thông tin liên hệ không?
3. **Đúng chính sách:** Đã áp guardrail, logging, giám sát, phân loại dữ liệu và yêu cầu mạng/mã hóa phù hợp chưa?
4. **Đúng đường đăng nhập:** Người dùng sử dụng IdP/SSO và xác thực mạnh khi cần; tài khoản local, break-glass được kiểm kê.
5. **Đúng quyền:** Role/ABAC giới hạn theo nguyên tắc ít quyền nhất; các quyền đặc biệt có phê duyệt và thời hạn khi phù hợp.
6. **Đúng workload identity:** Ứng dụng có principal riêng, owner và credential ngắn hạn/federation khi khả thi.
7. **Đúng JML:** Joiner cấp quyền theo nhiệm vụ; Mover thu hồi quyền cũ; Leaver kiểm tra toàn bộ account liên quan và đường truy cập tồn dư.
8. **Đúng đối soát:** Có thể đọc desired/actual access, kiểm tra quyền gắn trực tiếp, quyền qua nhóm, trust và credential.
9. **Đúng kiểm toán:** Lưu quyết định phê duyệt, thay đổi, kết quả thực thi, readback và ngoại lệ.
10. **Đúng kết thúc:** Khi account ngừng hoạt động, đã xử lý dependencies, dữ liệu, quyền, log và xác nhận provider trước khi đánh dấu Closed.

## 15. Câu hỏi tự kiểm tra

**1. Một người nghỉ việc, có nên đóng AWS account mà họ từng quản trị không?**  
Không. AWS account có thể đang chứa dịch vụ của doanh nghiệp; cần thu hồi quyền và credential của người rời đi, chuyển owner/quyền vận hành cần thiết. Chỉ đóng account khi workload và nghiệp vụ của chính account đó được chấm dứt theo quy trình riêng.

**2. Có SSO thì còn cần SCIM và cloud IAM không?**  
Có. SSO xử lý đăng nhập liên kết; SCIM hoặc provisioning API cập nhật account/user/group ở những hệ thống có hỗ trợ; cloud IAM quyết định quyền trên tài nguyên. Không cơ chế nào một mình đảm bảo deprovision mọi quyền và token tồn dư.

**3. Azure subscription có tương đương Google Cloud Billing account không?**  
Không. Subscription là đơn vị quản trị tài nguyên trong Azure; Google Cloud Billing account là đối tượng thanh toán có thể liên kết nhiều project. Khi so sánh ranh giới tài nguyên, Google Cloud project thường gần với vai trò tổ chức tài nguyên mà một subscription đảm nhiệm, nhưng các cơ chế vẫn khác nhau.

**4. Tại sao cần đối soát actual access sau sự kiện Mover?**  
Vì người dùng có thể còn quyền gắn trực tiếp, session, tài khoản local hoặc trust ngoài nhóm IdP đã thay đổi. Chỉ đọc nhóm mới trong IdP không chứng minh tất cả account đã thu hồi quyền cũ.

**5. Khi một pipeline ngừng hoạt động, ai chịu trách nhiệm thu hồi role và secret?**  
Owner workload cùng quy trình quản trị IAM/cloud account; không nên dựa vào tài khoản cá nhân của người từng viết pipeline. Cần xóa hoặc vô hiệu hóa trust, grant, credential và xác minh không còn đường truy cập hợp lệ.

## 16. Kết luận

**Cloud account** là một đơn vị quan trọng để tổ chức tài nguyên và ranh giới quản trị, còn **cloud identity** biểu diễn những chủ thể được phép yêu cầu truy cập. Doanh nghiệp phải quản lý cả **vòng đời account tài nguyên** (tạo, vận hành, chuyển giao, chấm dứt) lẫn **vòng đời quyền truy cập của con người và workload** theo Joiner–Mover–Leaver.

Để giảm quyền truy cập tồn dư, mọi thay đổi vai trò hoặc nghỉ việc phải được phản ánh tại đúng AWS account, Azure subscription, Google Cloud project và các hệ thống liên quan. Quy trình chỉ hoàn tất khi **quyền thực tế đã được xác minh**, các ngoại lệ có người chịu trách nhiệm và bằng chứng kiểm toán được bảo lưu.
