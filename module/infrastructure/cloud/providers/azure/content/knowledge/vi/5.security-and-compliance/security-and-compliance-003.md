# Bảo vệ workload và xử lý khuyến nghị bảo mật

Một ứng dụng chạy trên Azure có thể sử dụng virtual machine (VM), Azure App Service, Azure Kubernetes Service (AKS), Azure SQL Database, Storage Account, mạng ảo, Key Vault và nhiều dịch vụ khác. Mỗi thành phần có kiểu rủi ro riêng: VM có thể mở cổng quản trị ra Internet, storage có thể cho phép truy cập công khai không chủ ý, container có thể dùng image chứa lỗ hổng, còn danh tính ứng dụng có thể được cấp quyền rộng hơn nhu cầu.

Trong module **CLOUD_PROVIDERS_AZURE**, sau khi biết cách tổ chức subscription, resource group và triển khai kiến trúc ứng dụng, bạn cần biết cách **bảo vệ workload liên tục**: phát hiện cấu hình yếu, đánh giá khuyến nghị, ưu tiên sửa lỗi có ảnh hưởng lớn, triển khai thay đổi an toàn rồi xác minh hiệu quả. Microsoft Defender for Cloud là một công cụ trung tâm để quan sát trạng thái bảo mật và hỗ trợ công việc này.

Bài học thuộc chương **Bảo mật và tuân thủ**. Nội dung sử dụng ví dụ ứng dụng đặt hàng chạy trên Azure gồm web workload, VM vận hành, storage, cơ sở dữ liệu và danh tính ứng dụng. Các tên tài nguyên, nhóm và địa chỉ trong ví dụ đều mang tính minh họa.

## 1. Mục tiêu học tập

Sau khi hoàn thành, bạn có thể:

- Giải thích trách nhiệm bảo mật của khách hàng khi vận hành workload trên Azure.
- Phân biệt đánh giá tư thế bảo mật (security posture), khuyến nghị cấu hình (recommendation) và cảnh báo mối đe dọa (security alert).
- Xác định vai trò của Microsoft Defender for Cloud, Azure Policy, Azure Monitor, Microsoft Entra ID, Key Vault và các biện pháp bảo vệ mạng.
- Đọc một khuyến nghị: tài nguyên bị ảnh hưởng, nguyên nhân, mức độ quan trọng, điều kiện áp dụng và phương án khắc phục.
- Ưu tiên khuyến nghị dựa trên khả năng bị khai thác, mức độ lộ diện, mức độ quan trọng của workload và tác động của thay đổi.
- Thực hiện chu trình phát hiện → phân loại → sửa cấu hình → xác minh → theo dõi, bao gồm xử lý ngoại lệ có kiểm soát.
- Thực hành đánh giá VM, Storage Account và quyền của workload bằng Azure CLI và mô tả sửa cấu hình bằng Bicep.

## 2. Hiểu đối tượng cần bảo vệ

### 2.1. Mô hình trách nhiệm chia sẻ

Azure bảo vệ hạ tầng vật lý và một phần lớp nền của dịch vụ, nhưng khách hàng vẫn chịu trách nhiệm về dữ liệu, danh tính, phân quyền, cấu hình và cách sử dụng workload. Mức độ trách nhiệm đối với hệ điều hành và ứng dụng thay đổi theo loại dịch vụ.

| Kiểu triển khai | Ví dụ | Trách nhiệm điển hình của khách hàng |
|---|---|---|
| IaaS | Azure Virtual Machines | Cập nhật hệ điều hành khách, cấu hình mạng và firewall, bảo vệ ứng dụng, dữ liệu, tài khoản và credential |
| PaaS | Azure App Service, Azure SQL Database | Cấu hình dịch vụ, danh tính, truy cập mạng, ứng dụng, dữ liệu, backup và quyền truy cập |
| Container platform | AKS | Bảo vệ image, RBAC, secret, network policy, cấu hình workload, cập nhật thành phần theo phạm vi trách nhiệm |
| SaaS | Một dịch vụ ứng dụng được quản lý hoàn chỉnh | Danh tính, phân quyền, dữ liệu và cấu hình mà dịch vụ cho phép khách hàng điều khiển |

Không có một công cụ nào thay thế được việc thiết kế bảo mật ngay từ đầu. Defender for Cloud có thể phát hiện rủi ro và đưa ra đề xuất, nhưng mỗi workload vẫn cần quy tắc triển khai, quyền tối thiểu, backup, logging và quy trình ứng phó sự cố.

### 2.2. Tư thế bảo mật khác bảo vệ khi đang chạy

Có hai nhóm hoạt động bổ sung cho nhau:

- **Cloud Security Posture Management (CSPM):** kiểm tra cấu hình, chính sách và trạng thái tài nguyên. Ví dụ: máy ảo có mở cổng quản trị không, storage có bật truy cập công khai không, hệ thống có sử dụng mã hóa hay cấu hình an toàn theo khuyến nghị không.
- **Cloud Workload Protection (CWP):** theo dõi và phát hiện một số hành vi hoặc mối đe dọa liên quan đến workload đang hoạt động, tùy gói bảo vệ được bật. Ví dụ: hoạt động bất thường trên máy chủ, cảnh báo liên quan đến storage hoặc container.

Một khuyến nghị về cấu hình yếu chưa chắc có nghĩa hệ thống đã bị xâm nhập. Ngược lại, một cảnh báo nghi ngờ tấn công đòi hỏi quy trình điều tra và ứng phó, ngay cả khi các chỉ số cấu hình trước đó đều tốt.

### 2.3. Các lớp phòng vệ của kiến trúc ứng dụng

~~~mermaid
flowchart TD
    A[Người dùng và hệ thống tích hợp] --> B[Kiểm soát danh tính và truy cập]
    B --> C[Mạng, firewall và phân đoạn]
    C --> D[Workload: VM, App Service, AKS]
    D --> E[Dữ liệu: SQL, Storage, Key Vault]
    F[Defender for Cloud] -. Khuyến nghị và cảnh báo .-> B
    F -. Quan sát rủi ro .-> C
    F -. Quan sát rủi ro .-> D
    F -. Quan sát rủi ro .-> E
    G[Azure Policy và IaC] -. Kiểm soát cấu hình .-> C
    G -. Kiểm soát cấu hình .-> D
    H[Monitor và Activity Log] -. Theo dõi và điều tra .-> D
~~~

Một thiết kế phòng vệ nhiều lớp giúp hạn chế phạm vi ảnh hưởng khi một lớp bảo vệ thất bại:

1. **Danh tính:** MFA cho tài khoản người dùng phù hợp; Azure RBAC theo quyền tối thiểu; managed identity cho ứng dụng khi khả thi.
2. **Mạng:** giới hạn cổng, nguồn truy cập và đích; phân tách subnet; dùng private endpoint khi phù hợp.
3. **Compute và ứng dụng:** vá lỗ hổng, giảm bề mặt tấn công, quản lý cấu hình và dependency.
4. **Dữ liệu và secret:** quản lý quyền data plane, mã hóa, backup, thời hạn lưu giữ, hạn chế truy cập công khai.
5. **Giám sát và ứng phó:** thu thập log cần thiết, tạo cảnh báo, có người trực xử lý và định kỳ diễn tập khôi phục.

## 3. Các dịch vụ Azure dùng trong quy trình bảo vệ

| Dịch vụ hoặc khả năng | Công dụng | Điều cần nhớ |
|---|---|---|
| **Microsoft Defender for Cloud** | Tập trung đánh giá tư thế bảo mật, khuyến nghị và một số khả năng bảo vệ workload | Phạm vi và tính năng phụ thuộc gói, subscription, dịch vụ và cấu hình |
| **Defender CSPM** | Cung cấp khả năng quản lý tư thế bảo mật nâng cao theo phạm vi hỗ trợ | Có thể có chi phí; cần kiểm tra tính năng và cách tính phí thực tế |
| **Defender plans** | Bảo vệ phù hợp cho máy chủ, storage, cơ sở dữ liệu, container và các nhóm dịch vụ được hỗ trợ | Mỗi plan có phạm vi và yêu cầu triển khai riêng |
| **Azure Policy** | Đánh giá hoặc thực thi quy tắc cấu hình tại scope quản trị | Các hiệu ứng như audit, deny và modify không tương đương nhau |
| **Azure RBAC và Microsoft Entra ID** | Quản lý ai được xem, sửa, triển khai hoặc truy cập dữ liệu | Phân biệt management plane và data plane |
| **Azure Monitor và Activity Log** | Thu thập số liệu, log và sự kiện quản lý để xác minh hoặc điều tra | Muốn lưu log dài hạn thường cần cấu hình đích xuất và retention |
| **Azure Key Vault** | Bảo vệ secret, key và certificate | Cần quản lý quyền, mạng, vòng đời secret và giám sát truy cập |
| **Microsoft Sentinel hoặc hệ thống SIEM/SOAR** | Hỗ trợ phân tích, tương quan và xử lý sự kiện bảo mật | Chỉ sử dụng khi tổ chức có nhu cầu và đã cấu hình tích hợp |

Không phải mọi khuyến nghị đều yêu cầu mua thêm plan. Một số kiểm tra tư thế bảo mật có sẵn ở mức nền tảng; các khả năng phân tích nâng cao hoặc phát hiện runtime có thể cần gói trả phí, thành phần cài đặt, quyền hoặc kết nối bổ sung. Trước khi bật một plan cho nhiều subscription, hãy kiểm tra phạm vi được bảo vệ, dữ liệu thu thập, khu vực hỗ trợ, tác động vận hành và chi phí.

### 3.1. Secure score có ý nghĩa gì?

Defender for Cloud có thể hiển thị **secure score** để tóm tắt mức độ đáp ứng những security controls được tính điểm trong phạm vi đang đánh giá. Điểm số có thể giúp quan sát xu hướng và theo dõi kết quả xử lý khuyến nghị.

Tuy nhiên, secure score **không phải xác suất bị tấn công**, cũng không phải bằng chứng rằng workload tuân thủ mọi yêu cầu hay đã an toàn tuyệt đối. Hai subscription cùng điểm có thể có mức độ rủi ro nghiệp vụ khác nhau. Điểm có thể thay đổi khi tài nguyên, quy tắc đánh giá hoặc phạm vi bật tính năng thay đổi.

Hãy dùng secure score làm một tín hiệu cải tiến, đồng thời xem mức độ lộ diện của tài nguyên, đường tấn công có thể xảy ra, độ nhạy dữ liệu và vai trò của hệ thống.

### 3.2. Recommendation khác security alert

| Khía cạnh | Recommendation | Security alert |
|---|---|---|
| Nội dung | Cấu hình hoặc điều kiện chưa đáp ứng yêu cầu bảo mật | Dấu hiệu hoạt động đáng ngờ hoặc mối đe dọa đã được phát hiện |
| Ví dụ | Cổng quản trị VM có thể truy cập từ Internet | Phát hiện hành vi khả nghi liên quan đến VM |
| Hướng xử lý | Đánh giá, sửa cấu hình, vá lỗ hổng, giảm quyền hoặc ghi nhận ngoại lệ | Triage, xác minh, khoanh vùng, điều tra, ứng phó và phục hồi |
| Thời gian xử lý | Theo ưu tiên rủi ro và quy trình thay đổi | Theo mức độ nghiêm trọng, tính xác thực và quy trình ứng phó sự cố |
| Kết quả mong muốn | Tài nguyên đáp ứng trạng thái an toàn đã định | Mối đe dọa được xử lý, bằng chứng được bảo toàn và đường xâm nhập được khắc phục |

Không nên đánh dấu một security alert đã xử lý chỉ vì đã sửa recommendation có tên tương tự. Cần điều tra riêng những dấu hiệu xâm nhập và sự kiện đã xảy ra.

## 4. Chuẩn bị để nhìn thấy trạng thái bảo mật

Trước khi xử lý khuyến nghị, hãy bảo đảm hệ thống có phạm vi giám sát rõ ràng.

### 4.1. Xác định subscription, chủ sở hữu và tài nguyên

Trong doanh nghiệp có nhiều môi trường, có thể có các subscription riêng cho phát triển, kiểm thử và production. Hãy xác định:

- Subscription và resource group chứa workload.
- Các dịch vụ đang được dùng: VM, AKS, App Service, Storage, SQL, Key Vault, mạng.
- Resource có public endpoint, xử lý dữ liệu nhạy cảm hoặc giữ vai trò quan trọng với hoạt động kinh doanh.
- Người chịu trách nhiệm kỹ thuật và chủ sở hữu dữ liệu.
- Tag phân loại như **application**, **environment**, **owner**, **costCenter** hoặc **dataClassification** khi được tổ chức hỗ trợ.

Tag giúp quản trị nhưng không tự động được kế thừa từ resource group xuống mọi tài nguyên; cần quy trình hoặc Azure Policy phù hợp nếu muốn bảo đảm tính nhất quán.

### 4.2. Xác nhận quyền và gói bảo vệ

Trong Azure Portal, mở **Microsoft Defender for Cloud** và kiểm tra phạm vi subscription hoặc môi trường phù hợp. Tên mục và vị trí điều hướng có thể thay đổi theo phiên bản Portal.

Kiểm tra các điểm sau:

1. Danh tính đang dùng có quyền **đọc** đánh giá bảo mật trong phạm vi cần xem không.
2. Gói bảo vệ phù hợp đã được cấu hình cho các workload cần giám sát chưa.
3. Các agent, extension, integration hoặc kết nối cần thiết cho từng khả năng đã được triển khai theo tài liệu chưa.
4. Có thông báo thiếu coverage, dữ liệu chưa cập nhật hoặc tài nguyên ngoài phạm vi đánh giá không.
5. Đã thống nhất ai có quyền sửa resource, ai có quyền quản trị policy, ai có quyền xử lý cảnh báo và ngoại lệ chưa.

Dùng quyền tối thiểu. Người phân loại recommendation có thể chỉ cần quyền xem dữ liệu bảo mật; người sửa cấu hình cần quyền phù hợp với resource; việc tạo miễn trừ hoặc thay đổi chính sách phải theo quy trình ủy quyền.

### 4.3. Mở danh sách recommendations

Quy trình thao tác thường là:

1. Chọn đúng phạm vi subscription hoặc môi trường trong Defender for Cloud.
2. Mở mục **Recommendations**.
3. Lọc theo mức độ quan trọng, trạng thái, loại resource, subscription hoặc môi trường nếu giao diện hỗ trợ.
4. Mở một recommendation để đọc lý do, yêu cầu và danh sách affected resources.
5. Chọn một tài nguyên cụ thể, đối chiếu owner và đánh giá tác động trước khi sửa.
6. Ghi lại recommendation, resource ID, quyết định xử lý và bằng chứng xác minh.

Trạng thái hiển thị có thể gồm tài nguyên khỏe mạnh, chưa đáp ứng, không áp dụng hoặc được miễn trừ tùy loại đánh giá. Một khuyến nghị chưa xuất hiện không khẳng định cấu hình an toàn: có thể do phạm vi, plan, quyền, dữ liệu, độ trễ cập nhật hoặc điều kiện kiểm tra.

## 5. Cách đọc và phân tích một khuyến nghị bảo mật

Khuyến nghị cần được xem như một đầu việc có bằng chứng và chủ sở hữu, thay vì chỉ một dòng cần tích chọn.

### 5.1. Những trường cần đọc

| Câu hỏi | Cần thu thập |
|---|---|
| Vấn đề là gì? | Tên và mô tả recommendation; điều kiện kiểm tra; cấu hình chưa đáp ứng |
| Ảnh hưởng đến đâu? | Resource ID, loại tài nguyên, subscription, resource group, region và environment |
| Vì sao cần sửa? | Đường tấn công hoặc tác động có thể xảy ra; có public exposure hay không |
| Quan trọng đến mức nào? | Severity/priority do công cụ đưa ra; rủi ro nghiệp vụ của tài nguyên |
| Sửa bằng cách nào? | Hướng dẫn remediation, yêu cầu tiền đề, quyền cần thiết |
| Thay đổi có tác động gì? | Downtime, mất kết nối, thay đổi routing/DNS, chi phí, khả năng tương thích |
| Ai chịu trách nhiệm? | Chủ sở hữu workload, người thực hiện, người phê duyệt |
| Xác minh kết quả thế nào? | Trạng thái cấu hình, kiểm thử ứng dụng, recommendation được đánh giá lại |
| Khi nào xong? | Thời hạn, change ticket, bằng chứng và trạng thái theo dõi |

Đừng chỉ xem tên recommendation. Ví dụ, khuyến nghị “chặn public access” có thể hợp lý với storage chứa dữ liệu nội bộ, nhưng nếu ứng dụng cần một endpoint công khai được kiểm soát, cách sửa phải được thiết kế phù hợp với luồng truy cập và phân loại dữ liệu.

### 5.2. Severity và business impact

Một khuyến nghị có severity cao thường đáng chú ý, nhưng nên bổ sung bối cảnh thực tế:

- **Mức độ lộ diện:** tài nguyên có thể bị truy cập từ Internet hay chỉ nằm trong mạng riêng?
- **Khả năng bị khai thác:** vấn đề có tạo đường khai thác thực tế không; có điều kiện xác thực hoặc mạng ngăn chặn nào?
- **Độ quan trọng:** production thanh toán, hệ thống thử nghiệm hay môi trường sandbox?
- **Dữ liệu:** có dữ liệu cá nhân, thông tin giao dịch, bí mật hoặc bản sao dữ liệu nhạy cảm không?
- **Tác động lan truyền:** principal hoặc workload có quyền truy cập tài nguyên khác không?
- **Biện pháp hiện có:** firewall, private endpoint, RBAC, WAF, backup, giám sát.
- **Rủi ro thay đổi:** sửa ngay có gây gián đoạn nghiêm trọng hoặc mất khả năng quản trị không?

Ví dụ, một VM production mở SSH từ Internet có thể cần ưu tiên cao hơn một VM thử nghiệm đã cô lập dù hai VM có cùng kiểu recommendation. Ngược lại, một storage test chứa bản sao dữ liệu thật có thể vẫn thuộc nhóm ưu tiên cao.

### 5.3. Ma trận ưu tiên nội bộ

Đây là **ví dụ quy tắc của nhóm vận hành**, không phải công thức chấm điểm chính thức của Defender for Cloud.

| Mức ưu tiên | Điều kiện minh họa | Hướng xử lý |
|---|---|---|
| P0 – Khẩn cấp | Nguy cơ bị khai thác đang diễn ra, có dấu hiệu xâm nhập hoặc tài nguyên trọng yếu lộ diện nghiêm trọng | Kích hoạt quy trình ứng phó sự cố, khoanh vùng và xử lý ngay theo quyền hạn |
| P1 – Cao | Exposure rộng, ảnh hưởng production hoặc dữ liệu nhạy cảm; khả năng khai thác đáng kể | Gán owner và thay đổi trong thời hạn ưu tiên cao |
| P2 – Trung bình | Cấu hình yếu nhưng có biện pháp bù trừ, hoặc tác động giới hạn | Đưa vào kế hoạch cải tiến có thời hạn |
| P3 – Thấp | Nguy cơ thấp, tài nguyên ít quan trọng hoặc yêu cầu tối ưu dài hạn | Xếp backlog và tái đánh giá định kỳ |

Đặt SLA cụ thể theo chính sách của tổ chức. Không suy ra SLA tuyệt đối chỉ từ màu sắc của cảnh báo hay số điểm secure score.

## 6. Chu trình xử lý recommendation từ đầu đến cuối

~~~mermaid
flowchart TD
    A[Phát hiện khuyến nghị] --> B[Xác định scope và owner]
    B --> C[Kiểm tra exposure, mức độ quan trọng và bằng chứng]
    C --> D{Khuyến nghị áp dụng thực tế?}
    D -->|Có| E[Chọn thay đổi và đánh giá rủi ro]
    E --> F[Review, kiểm thử, triển khai]
    F --> G[Kiểm tra cấu hình và chức năng]
    G --> H{Defender đánh giá lại đạt?}
    H -->|Có| I[Đóng công việc và lưu bằng chứng]
    H -->|Chưa| J[Kiểm tra độ trễ, phạm vi hoặc lỗi còn lại]
    J --> E
    D -->|Chưa hoặc chưa thể sửa| K[Ghi nhận lý do, kiểm soát bù trừ và thời hạn]
    K --> L[Phê duyệt ngoại lệ theo quy trình]
    L --> M[Tái đánh giá định kỳ]
    M --> C
~~~

### Bước 1: Xác thực tín hiệu

Đọc recommendation và các affected resources, sau đó trực tiếp kiểm tra cấu hình ở nguồn quản lý tài nguyên. Đảm bảo tài nguyên đúng subscription, workload và môi trường. Phân biệt dữ liệu vừa mới cập nhật với trạng thái cũ hoặc đánh giá chưa hoàn thành.

### Bước 2: Phân loại rủi ro và gán owner

Gắn priority, người chịu trách nhiệm, thời hạn và change ticket. Với thay đổi liên quan mạng, danh tính, database hoặc storage production, mời các nhóm liên quan tham gia đánh giá.

### Bước 3: Chọn biện pháp khắc phục

Ưu tiên sửa nguyên nhân gốc thay vì chỉ ẩn cảnh báo. Các dạng remediation thường gặp:

- Sửa cấu hình bằng Azure Portal, Azure CLI hoặc SDK.
- Thay đổi Bicep/ARM template/Terraform để trạng thái an toàn được tái triển khai nhất quán.
- Thu hẹp NSG rule, khóa public endpoint, cấu hình private endpoint hoặc WAF theo kiến trúc.
- Cập nhật hệ điều hành, image, runtime và dependency.
- Thu hẹp Azure RBAC và quyền data plane.
- Bật logging, mã hóa hoặc cấu hình backup thích hợp.
- Kích hoạt gói bảo vệ hoặc thành phần cần thiết nếu recommendation yêu cầu và tổ chức đã phê duyệt.

### Bước 4: Đánh giá ảnh hưởng trước khi triển khai

Xác định người dùng, hệ thống tích hợp và pipeline đang phụ thuộc vào cấu hình cũ. Ví dụ:

- Khóa public network access của Storage Account có thể làm API hoặc batch job mất kết nối.
- Chặn cổng quản trị có thể khiến vận hành không còn đường vào VM; nên chuẩn bị Azure Bastion hoặc đường truy cập đã được kiểm soát.
- Thay secret hoặc quyền identity có thể làm ứng dụng lỗi xác thực.
- Vá VM có thể yêu cầu reboot và ảnh hưởng thời gian phục vụ.
- Bật log hoặc plan mới có thể phát sinh chi phí.

Hãy ghi rõ kiểm thử, rollback và thời gian bảo trì nếu cần.

### Bước 5: Thực hiện thay đổi có kiểm soát

Ưu tiên quy trình Infrastructure as Code (IaC), pull request và triển khai qua pipeline đã phân quyền. Nếu cần hotfix trực tiếp, hãy ghi lại thay đổi và đồng bộ cấu hình về IaC để tránh trạng thái thực tế lệch khỏi mã nguồn.

Đối với Bicep, có thể chạy **what-if** để xem dự kiến thay đổi trước khi áp dụng. Kết quả what-if hữu ích nhưng không thay thế kiểm thử phụ thuộc và chức năng của workload.

### Bước 6: Xác minh ở ba cấp

1. **Cấu hình:** thuộc tính tài nguyên thực tế đã đúng chưa?
2. **Chức năng và bảo vệ:** người dùng hợp lệ còn truy cập được; truy cập trái phép bị chặn; giám sát còn hoạt động?
3. **Đánh giá tập trung:** recommendation đã chuyển trạng thái sau khi Defender for Cloud đánh giá lại chưa?

Có thể có độ trễ giữa lúc sửa xong và lúc recommendation được cập nhật. Nếu trạng thái chưa thay đổi ngay, hãy kiểm tra vòng đánh giá, scope, điều kiện policy, gói bảo vệ và metadata liên quan trước khi kết luận thất bại.

### Bước 7: Lưu bằng chứng và tránh tái phát

Lưu resource ID, ticket, pull request hoặc deployment ID, thời điểm, thay đổi thực hiện, kết quả kiểm thử và trạng thái recommendation sau sửa. Nếu nguyên nhân do chuẩn cấu hình chưa được áp dụng đồng nhất, bổ sung Azure Policy hoặc guardrail ở pipeline phù hợp.

## 7. Tình huống A: VM mở cổng quản trị từ Internet

Giả sử resource group **rg-orders-prod** chứa VM quản trị chạy trong virtual network. Một Network Security Group (NSG) có inbound rule cho phép TCP/22 từ nguồn quá rộng. Khuyến nghị liên quan đến việc hạn chế cổng quản trị xuất hiện trong Defender for Cloud.

### 7.1. Xác định rủi ro

SSH là công cụ quản trị hợp lệ, nhưng mở từ Internet làm tăng bề mặt tấn công. Nếu VM chứa credential hoặc có quyền truy cập cơ sở dữ liệu, tác động có thể lan sang tài nguyên khác.

Trước khi sửa, kiểm tra:

- NSG rule áp dụng vào NIC, subnet hoặc cả hai?
- Public IP có gắn với VM hoặc một thiết bị chuyển tiếp không?
- Có Azure Bastion, VPN hoặc một phương thức quản trị được phê duyệt không?
- Nhóm vận hành có phụ thuộc vào đường SSH hiện tại?
- VM có phân quyền, cập nhật bảo mật và logging phù hợp chưa?

### 7.2. Kiểm tra cấu hình bằng Azure CLI

~~~bash
az login
az account set --subscription "<subscription-id>"

# Xem inbound/outbound rules của NSG được chỉ định
az network nsg rule list \
  --resource-group rg-orders-prod \
  --nsg-name "<nsg-name>" \
  --output table

# Xem những role assignment trực tiếp hoặc kế thừa tại resource group
az role assignment list \
  --scope "/subscriptions/<subscription-id>/resourceGroups/rg-orders-prod" \
  --include-inherited \
  --output table
~~~

Thay các placeholder bằng giá trị thực. Danh sách NSG rule chỉ là một phần của đường đi mạng; cần xem cả cấu hình NIC, subnet, route, firewall trung gian và cách truy cập thật của VM.

### 7.3. Chọn phương án an toàn

Tùy kiến trúc có thể:

1. Loại bỏ inbound rule không còn cần thiết.
2. Giới hạn nguồn SSH/RDP vào mạng quản trị được phê duyệt.
3. Sử dụng Azure Bastion hoặc kết nối mạng riêng để tránh mở trực tiếp cổng quản trị qua public IP.
4. Xem xét Just-In-Time VM access khi có tính năng hỗ trợ, gói phù hợp và quy trình vận hành cho phép.
5. Giảm quyền của danh tính trên VM và kiểm tra OS patching, EDR/antimalware theo yêu cầu.

Không chặn toàn bộ đường quản trị trước khi xác nhận có phương án truy cập thay thế. Thử kết nối bằng đường được phê duyệt, thử truy cập không hợp lệ, rồi xác minh recommendation được đánh giá lại.

## 8. Tình huống B: Storage Account có cấu hình truy cập chưa an toàn

Ứng dụng Orders lưu hóa đơn và tài liệu nội bộ trong Azure Blob Storage. Security recommendation có thể liên quan đến truy cập blob công khai, HTTPS, quyền truy cập dữ liệu hoặc kết nối mạng.

### 8.1. Phân biệt ba lớp bảo vệ

- **Transport:** yêu cầu HTTPS/TLS phù hợp để tránh gửi dữ liệu qua kết nối không được bảo vệ.
- **Anonymous access:** quản lý khả năng truy cập blob công khai không cần xác thực. Thiết lập này khác với việc có hoặc không có public network endpoint.
- **Network exposure:** giới hạn đường truy cập tới storage account thông qua firewall, private endpoint hoặc cấu hình mạng được hỗ trợ.

Chặn anonymous blob access không tự động biến storage account thành private endpoint. Ngược lại, giới hạn network access không thay thế quyền data plane của Azure RBAC.

### 8.2. Kiểm tra thuộc tính hiện tại

~~~bash
az storage account show \
  --resource-group rg-orders-prod \
  --name "<storage-account-name>" \
  --query "{name:name,httpsOnly:enableHttpsTrafficOnly,minimumTls:minimumTlsVersion,allowBlobPublicAccess:allowBlobPublicAccess,publicNetworkAccess:publicNetworkAccess}" \
  --output json
~~~

Không đưa secret, storage key hoặc chuỗi kết nối vào log, ticket hay tài liệu. Kết quả ở đây chỉ dùng để kiểm tra cấu hình quản lý.

### 8.3. Khắc phục bằng Bicep

Ví dụ khai báo một Storage Account mới hoặc quản lý bằng IaC theo thiết kế an toàn. Đây là **mẫu cấu hình minh họa**, chưa phải cấu hình hoàn chỉnh cho mọi hệ thống production:

~~~bicep
@description('Tên storage account hợp lệ và duy nhất')
param storageAccountName string

@description('Region của tài nguyên')
param location string = resourceGroup().location

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
  }
  tags: {
    application: 'orders'
    environment: 'prod'
  }
}

output storageAccountId string = storage.id
~~~

Lưu mã trên vào **storage-secure.bicep** sau khi rà soát cấu hình đầy đủ của storage account hiện có. Nếu dùng template để cập nhật tài nguyên đang chạy, phải bảo đảm template mô tả đúng trạng thái mong muốn của toàn bộ resource; không dùng mẫu ngắn này để vô tình đặt lại thuộc tính đang vận hành.

~~~bash
# Xem trước thay đổi dự kiến ở scope resource group
az deployment group what-if \
  --resource-group rg-orders-prod \
  --template-file storage-secure.bicep \
  --parameters storageAccountName="<storage-account-name>"

# Chỉ chạy sau khi đã review what-if và tác động hệ thống
az deployment group create \
  --name security-storage-hardening \
  --resource-group rg-orders-prod \
  --template-file storage-secure.bicep \
  --parameters storageAccountName="<storage-account-name>"
~~~

Nếu cần chặn public network access, phải thiết kế private endpoint, DNS, mạng của ứng dụng, pipeline và công cụ quản trị trước. Không thêm tùy chọn chặn mạng vào production mà chưa xác minh luồng kết nối hợp lệ.

Sau thay đổi, kiểm tra thuộc tính thực tế bằng CLI, thử API đọc/ghi theo quyền được cấp và kiểm tra rằng truy cập không được phép đã bị chặn.

## 9. Tình huống C: workload container hoặc cơ sở dữ liệu

### 9.1. Container và AKS

Một khuyến nghị có thể liên quan đến image chứa lỗ hổng, container chạy với quyền quá rộng, kết nối mạng hoặc cấu hình Kubernetes chưa phù hợp.

Quy trình thực hiện:

1. Xác định image digest, phiên bản runtime và workload bị ảnh hưởng.
2. Xác nhận lỗ hổng nằm trong package có thể tiếp cận trong đường chạy thực tế hay không.
3. Cập nhật base image hoặc dependency đã được vá; build lại image.
4. Quét lại image và chạy kiểm thử chức năng trước khi rollout.
5. Triển khai theo chiến lược giảm rủi ro; theo dõi health, error rate và khả năng rollback.
6. Giới hạn quyền của pod, service account và đường mạng theo nhu cầu.
7. Xác minh khuyến nghị và kết quả quét lại.

Không nên xem việc tắt một pod bị phát hiện có vấn đề là đủ nếu image không an toàn vẫn còn trong registry hoặc pipeline triển khai lại image đó.

### 9.2. Azure SQL Database

Các khuyến nghị có thể liên quan đến quyền, cấu hình mạng, kiểm tra lỗ hổng, mã hóa, audit và phát hiện mối đe dọa theo khả năng của dịch vụ.

Khi xử lý:

- Xem xét ai và dịch vụ nào thực sự cần kết nối tới database.
- Thu hẹp firewall rule và dùng kết nối riêng khi kiến trúc phù hợp.
- Dùng danh tính ứng dụng được cấp đúng quyền thay vì thông tin xác thực quản trị dùng chung.
- Đánh giá phương thức sao lưu, phục hồi và retention.
- Bật audit/log hoặc plan bảo vệ cần thiết theo chính sách.
- Kiểm tra ứng dụng và kết nối sau khi thay đổi.

Không tự giả định mọi tùy chọn của một loại SQL deployment cũng tồn tại ở loại khác. Azure SQL Database, SQL Managed Instance và SQL Server chạy trên VM có trách nhiệm vận hành khác nhau.

### 9.3. Key Vault và secret

Khi khuyến nghị liên quan đến Key Vault, cần xem xét:

- Principal nào được phép đọc hoặc quản lý secret/key?
- Key Vault có public network access hay network firewall theo kiến trúc được phê duyệt không?
- Workload có dùng managed identity và cơ chế truy cập ít quyền không?
- Secret có chu kỳ xoay vòng và quy trình thu hồi không?
- Soft delete, purge protection, logging và cảnh báo có đáp ứng chính sách tổ chức không?

Khắc phục một cảnh báo “quá nhiều quyền” không chỉ là tắt public access. Phải kiểm tra cả quyền trên management plane và data plane của Key Vault, cũng như tác động tới ứng dụng dùng secret.

## 10. Quản lý ngoại lệ khi chưa thể sửa ngay

Không phải mọi recommendation đều có thể sửa ngay. Có thể workload phụ thuộc vào giao thức cũ, không hỗ trợ thay đổi trong kỳ vận hành hiện tại, hoặc recommendation chưa thực sự áp dụng do cơ chế kiểm soát bù trừ.

Tuy vậy, **ngoại lệ bảo mật** phải được xem là quyết định có trách nhiệm, không phải cách làm biến mất một hàng trong dashboard.

Một hồ sơ ngoại lệ nên có:

| Thông tin | Mục đích |
|---|---|
| Recommendation và resource ID | Xác định chính xác vấn đề và phạm vi |
| Lý do chưa sửa hoặc không áp dụng | Giải thích căn cứ kỹ thuật và nghiệp vụ |
| Rủi ro còn lại | Đánh giá exposure và hậu quả sau kiểm soát bù trừ |
| Biện pháp bù trừ | Giảm xác suất hoặc tác động trong thời gian chờ |
| Chủ sở hữu và người phê duyệt | Xác định trách nhiệm |
| Thời hạn và ngày đánh giá lại | Tránh ngoại lệ tồn tại vô hạn |
| Bằng chứng kiểm tra | Hỗ trợ kiểm toán và quyết định tiếp tục |

Nếu Defender for Cloud hỗ trợ exemption hoặc governance rule cho loại đánh giá đang dùng, chỉ áp dụng sau khi được phê duyệt và đúng phạm vi. Việc đánh dấu miễn trừ có thể thay đổi cách hiển thị hoặc tính điểm, **không tự làm cho cấu hình an toàn hơn**.

Ví dụ: một dịch vụ legacy buộc phải duy trì cổng quản trị trong một khoảng thời gian. Ngoại lệ cần nêu rõ nguồn IP được phép, thời gian còn hiệu lực, giám sát bổ sung, lịch chuyển sang kênh quản trị riêng và người phê duyệt.

## 11. Khi nhận được security alert thay vì recommendation

Một alert có thể cho biết hành vi bất thường hoặc nguy cơ đang diễn ra. Khi đó, quy trình thường bắt đầu bằng **triage và ứng phó sự cố**, không chỉ bằng thay đổi cấu hình.

1. Ghi lại thời điểm, subscription, tài nguyên, thông tin cảnh báo và bằng chứng gốc.
2. Xác minh alert có liên quan đến hoạt động hợp lệ (maintenance, kiểm thử được phê duyệt) hay có dấu hiệu tấn công.
3. Nếu nguy cơ đáng kể, kích hoạt kênh ứng phó và người chịu trách nhiệm.
4. Khoanh vùng theo runbook: ví dụ hạn chế truy cập hoặc cô lập workload, nhưng cân nhắc yêu cầu giữ bằng chứng và tính liên tục dịch vụ.
5. Xem log, timeline, principal, network connection và các tài nguyên liên quan.
6. Khắc phục nguyên nhân gốc: thu hồi credential, vá lỗ hổng, sửa role assignment, điều chỉnh firewall hoặc redeploy image sạch khi cần.
7. Kiểm thử phục hồi, giám sát tái diễn, ghi nhận bài học và cập nhật biện pháp phòng ngừa.

Không xóa VM, dữ liệu hay log chỉ để làm cảnh báo biến mất. Việc xóa hoặc khởi tạo lại hệ thống có thể phá hủy bằng chứng cần thiết cho điều tra; lựa chọn phải tuân theo quy trình ứng phó sự cố của tổ chức.

## 12. Tổ chức thực hiện ở quy mô nhiều subscription

Với một tổ chức có các môi trường **dev**, **staging** và **production**, một dashboard đơn lẻ chưa đủ để điều phối công việc. Hãy thiết kế vòng phản hồi giữa bảo mật và đội triển khai:

~~~mermaid
flowchart LR
    A[Defender for Cloud và Policy] --> B[Nhóm bảo mật: phân loại]
    B --> C[Owner của workload]
    C --> D[Thay đổi IaC và kiểm thử]
    D --> E[Pipeline triển khai]
    E --> F[Kiểm tra bảo mật và chức năng]
    F --> A
    B --> G[Ngoại lệ được phê duyệt]
    G --> H[Rà soát ngày hết hạn]
    H --> B
~~~

Có thể chuẩn hóa một bản ghi công việc:

~~~yaml
recommendation: "<recommendation-id-or-name>"
resourceId: "/subscriptions/<subscription-id>/resourceGroups/rg-orders-prod/providers/<namespace>/<type>/<name>"
environment: "prod"
application: "orders"
owner: "team-orders"
priority: "P1"
risk: "Publicly exposed management endpoint"
decision: "Remediate"
changeReference: "<ticket-or-pull-request>"
verification:
  configuration: "pending"
  applicationHealth: "pending"
  defenderReassessment: "pending"
dueDate: "<yyyy-mm-dd>"
~~~

Đây là **mẫu YAML của phiếu theo dõi**, không phải cú pháp API của Defender for Cloud. Các giá trị minh họa cần được thay bằng dữ liệu thực tế, tuyệt đối không điền credential hoặc dữ liệu nhạy cảm vào phiếu công khai.

Một số thực hành hỗ trợ vận hành:

- Định danh owner cho mỗi resource group và nhóm workload.
- Theo dõi backlog theo severity, exposure, thời gian tồn tại và environment.
- Có lịch rà soát các khuyến nghị mới và các ngoại lệ sắp hết hạn.
- Tạo các Azure Policy phù hợp để ngăn lỗi cấu hình tái diễn.
- Đảm bảo thay đổi từ Portal được phản ánh lại trong IaC hoặc tài liệu cấu hình chuẩn.
- Kết hợp dữ liệu từ Defender for Cloud với thay đổi Azure Activity Log và tín hiệu vận hành từ Azure Monitor.
- Đo việc giảm rủi ro thực tế: số public endpoint không cần thiết, số role quá quyền, thời gian khắc phục lỗ hổng quan trọng và tỷ lệ resource được bảo vệ.

## 13. Những nhầm lẫn thường gặp

1. **“Secure score cao nghĩa là không thể bị tấn công.”** Điểm số chỉ tóm tắt một phần trạng thái theo những kiểm tra đang áp dụng.
2. **“Recommendation là bằng chứng bị xâm nhập.”** Recommendation thường mô tả cấu hình hoặc điều kiện rủi ro; alert và điều tra mới giúp đánh giá hành vi đe dọa.
3. **“Bật Defender for Cloud là đủ.”** Vẫn cần coverage đúng, quyền, logging, vá lỗ hổng, thiết kế mạng và quy trình phản ứng.
4. **“Chỉ cần nhấn Fix là xong.”** Sửa cấu hình có thể làm mất kết nối hoặc gây lỗi nghiệp vụ; phải xem tác động, kiểm thử và xác minh.
5. **“Đã sửa thuộc tính thì dashboard phải cập nhật ngay.”** Có thể cần thời gian để hệ thống đánh giá lại.
6. **“Exempt nghĩa là đã an toàn.”** Ngoại lệ là chấp nhận hoặc xử lý rủi ro có thời hạn, cần người phê duyệt và biện pháp bù trừ.
7. **“Chặn anonymous blob access tương đương chặn public endpoint.”** Đây là hai cơ chế khác nhau.
8. **“Sửa trực tiếp trên Portal sẽ tồn tại mãi.”** Triển khai IaC tiếp theo có thể ghi đè; phải đồng bộ nguồn cấu hình.
9. **“Mọi plan áp dụng cho mọi workload.”** Mỗi plan và tính năng có phạm vi, điều kiện, khả năng bảo vệ và chi phí khác nhau.
10. **“Không còn thấy cảnh báo nghĩa là đã xử lý sự cố.”** Cần xác minh nguyên nhân gốc, tài nguyên liên quan và bằng chứng điều tra.

## 14. Bài tập thực hành

### Bài tập 1: Phân loại khuyến nghị

Giả sử Defender for Cloud ghi nhận:

- VM production mở cổng SSH tới Internet từ nguồn rộng.
- Storage Account của ứng dụng nội bộ cho phép anonymous blob access.
- Một container image staging có lỗ hổng trong dependency.
- Một danh tính ứng dụng có role Contributor trên subscription, dù chỉ cần đọc một Storage Account.

Hãy ghi owner, mức độ ưu tiên, cách xác minh, phương án remediation và tác động khi sửa. Giải thích lý do vì sao mức ưu tiên có thể khác severity của recommendation.

### Bài tập 2: Lập kế hoạch sửa storage

Sử dụng một resource group thử nghiệm. Đọc cấu hình storage account bằng Azure CLI; xác định HTTPS, TLS, public blob access và network exposure. Viết Bicep mô tả cấu hình mong muốn, xem **what-if**, kiểm tra ảnh hưởng tới ứng dụng, rồi triển khai chỉ sau khi có thể xác minh đường truy cập hợp lệ.

### Bài tập 3: Xử lý ngoại lệ

Một hệ thống legacy chưa thể chuyển sang private endpoint trong quý hiện tại. Hãy viết hồ sơ ngoại lệ gồm rủi ro còn lại, kiểm soát bù trừ, owner, người phê duyệt, ngày hết hạn và điều kiện chấm dứt ngoại lệ.

### Bài tập 4: Phân biệt khuyến nghị và cảnh báo

Cùng một VM xuất hiện recommendation mở cổng quản trị và alert nghi ngờ hành vi đăng nhập bất thường. Hãy mô tả hai luồng xử lý song song: thay đổi cấu hình để giảm exposure và điều tra sự kiện để xác định có xâm nhập hay không.

### Câu hỏi tự kiểm tra

1. Vì sao không nên xếp backlog chỉ theo secure score?
2. Khi nào một recommendation có thể chưa xuất hiện dù workload vẫn có rủi ro?
3. Tại sao cần kiểm tra chức năng ứng dụng sau khi khóa public network access?
4. Một exemption cần những trường tối thiểu nào?
5. Sự khác biệt giữa remediation, mitigation và incident response là gì?

## 15. Tài liệu tham khảo

- [Microsoft Defender for Cloud overview](https://learn.microsoft.com/azure/defender-for-cloud/defender-for-cloud-introduction)
- [Review security recommendations in Microsoft Defender for Cloud](https://learn.microsoft.com/azure/defender-for-cloud/review-security-recommendations)
- [Microsoft Defender for Cloud secure score](https://learn.microsoft.com/azure/defender-for-cloud/secure-score-security-controls)
- [Microsoft Defender for Servers](https://learn.microsoft.com/azure/defender-for-cloud/defender-for-servers-introduction)
- [Microsoft Defender for Storage](https://learn.microsoft.com/azure/defender-for-cloud/defender-for-storage-introduction)
- [Microsoft Defender for Containers](https://learn.microsoft.com/azure/defender-for-cloud/defender-for-containers-introduction)
- [Azure Policy overview](https://learn.microsoft.com/azure/governance/policy/overview)
- [Azure Well-Architected Framework: Security](https://learn.microsoft.com/azure/well-architected/security/overview)

