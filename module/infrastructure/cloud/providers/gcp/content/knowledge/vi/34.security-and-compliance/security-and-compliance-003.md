# Security Health Analytics và cấu hình sai trên cloud

## 1. Vì sao cấu hình sai trở thành rủi ro bảo mật

Một hệ thống Google Cloud có thể dùng đúng dịch vụ, chạy ổn định và vẫn để lộ dữ liệu hoặc quyền quản trị vì một cấu hình nhỏ bị đặt quá rộng. Ví dụ: một Cloud Storage bucket cho phép `allUsers` đọc dữ liệu, một firewall rule mở SSH từ `0.0.0.0/0`, một Cloud SQL instance có IP công khai và danh sách mạng được phép quá rộng, hoặc một service account được cấp quyền `Owner` dù chỉ cần đọc một vài tài nguyên.

Những lỗi này thường không nằm trong mã nguồn ứng dụng. Chúng xuất hiện ở lớp cấu hình tài nguyên, IAM, mạng, lưu trữ, cơ sở dữ liệu, Kubernetes và chính sách của tổ chức. Khi số lượng project tăng lên, việc kiểm tra thủ công từng màn hình không còn đáng tin cậy: cấu hình có thể thay đổi sau một lần triển khai, một thao tác trên Console hoặc một thay đổi quyền của nhóm vận hành.

Trong module `CLOUD_PROVIDERS_GCP`, người học cần nhìn bảo mật như một phần của vòng đời hạ tầng: tổ chức và project xác định phạm vi quản trị; IAM quyết định ai được làm gì; VPC kiểm soát đường đi của lưu lượng; Compute Engine, GKE, Cloud Run, Storage và cơ sở dữ liệu mang dữ liệu và workload; pipeline triển khai phải giữ các giới hạn đó sau mỗi lần phát hành. Security Health Analytics hỗ trợ phát hiện các cấu hình cloud phổ biến có thể làm suy yếu những lớp bảo vệ này.

## 2. Security Health Analytics là gì?

**Security Health Analytics (SHA)** là dịch vụ phát hiện cấu hình sai được quản lý trong **Security Command Center (SCC)**. Dịch vụ quét các tài nguyên được hỗ trợ, áp dụng các detector có sẵn và tạo **finding** khi phát hiện một cấu hình có rủi ro. Finding giúp đội ngũ bảo mật và vận hành biết tài nguyên nào bị ảnh hưởng, vấn đề thuộc loại nào và nên kiểm tra hoặc khắc phục điều gì.

Ví dụ, detector có thể phát hiện các tình huống như:

- Bucket hoặc dataset có quyền truy cập công khai.
- Firewall rule cho phép kết nối quản trị từ dải IP quá rộng.
- Cloud SQL instance để lộ IP công khai hoặc có thiết lập bảo vệ chưa phù hợp.
- IAM binding cấp quyền quá rộng cho người dùng, nhóm hoặc service account.
- Khóa mã hóa, cấu hình sao lưu, audit logging hoặc chính sách tổ chức chưa đáp ứng yêu cầu bảo mật.
- GKE cluster thiếu một số thiết lập bảo vệ được detector hỗ trợ.

SHA giúp **phát hiện và mô tả vấn đề**. Dịch vụ không tự thay đổi firewall, thu hồi quyền IAM, chuyển database sang private IP hay sửa Terraform thay cho đội ngũ vận hành. Việc khắc phục vẫn cần được đánh giá tác động, thực hiện qua quy trình thay đổi phù hợp và xác minh sau khi triển khai.

### SHA nằm ở đâu trong hệ sinh thái bảo mật?

| Thành phần | Vai trò chính | Câu hỏi được trả lời |
|---|---|---|
| Cloud Asset Inventory | Ghi nhận tài nguyên và một phần metadata cấu hình được hỗ trợ | Tổ chức đang có những tài nguyên nào và chúng thuộc phạm vi nào? |
| Security Health Analytics | Chạy detector trên các loại tài nguyên được hỗ trợ | Cấu hình nào có dấu hiệu không an toàn? |
| Security Command Center Findings | Tập trung kết quả phát hiện và thông tin liên quan | Vấn đề nào đang tồn tại, ảnh hưởng tài nguyên nào và có mức độ nào? |
| IAM, Organization Policy, VPC và cấu hình dịch vụ | Áp dụng quyền và giới hạn bảo vệ | Làm thế nào để sửa vấn đề và ngăn cấu hình tương tự tái xuất hiện? |
| Terraform và CI/CD | Quản lý cấu hình hạ tầng qua mã nguồn và quy trình phát hành | Làm thế nào để kiểm tra thay đổi trước khi áp dụng? |

Luồng tổng quát:

~~~mermaid
flowchart LR
    A[Organization / Folder / Project] --> B[Cloud Asset Inventory và metadata tài nguyên]
    B --> C[Security Health Analytics detectors]
    C --> D[Findings trong Security Command Center]
    D --> E[Phân loại, ưu tiên và giao người phụ trách]
    E --> F[Khắc phục bằng Console, gcloud hoặc Terraform]
    F --> G[Quét lại và xác minh finding]
    G --> H[Organization Policy và kiểm tra CI/CD]
~~~

SHA chỉ kiểm tra **một tập con** các loại tài nguyên và thuộc tính mà dịch vụ hỗ trợ. Một dịch vụ Google Cloud có thể có nhiều thiết lập nhưng không phải tất cả đều được SHA kiểm tra. Vì vậy, không nên hiểu việc không có finding là bằng chứng rằng mọi tài nguyên đều an toàn.

## 3. Detector, finding và phạm vi phát hiện

Detector là quy tắc kiểm tra cho một loại cấu hình hoặc tài nguyên. Mỗi detector tạo ra một loại finding tương ứng khi phát hiện điều kiện không đạt. Các detector được nhóm theo những miền như IAM, firewall, network, Compute Engine, container, database, storage, KMS, logging, monitoring, API key và Organization Policy.

Một số ví dụ về phạm vi kiểm tra thường gặp:

| Miền tài nguyên | Cấu hình cần chú ý | Rủi ro có thể phát sinh |
|---|---|---|
| Cloud Storage và BigQuery | Quyền truy cập công khai, ACL hoặc IAM quá rộng, mã hóa | Lộ dữ liệu, truy cập trái phép hoặc không đáp ứng yêu cầu bảo vệ dữ liệu |
| VPC và Compute Engine | Firewall mở rộng, VM có đường truy cập công khai, thiết lập bảo vệ máy ảo | Bề mặt tấn công lớn, dò quét hoặc truy cập trái phép vào máy chủ |
| Cloud SQL | IP công khai, cấu hình TLS, backup và database flags | Lộ dịch vụ cơ sở dữ liệu, mất dữ liệu hoặc giảm khả năng bảo vệ kết nối |
| IAM và service account | Quyền cơ bản quá rộng, tài khoản dịch vụ hoặc khóa do người dùng quản lý | Leo thang đặc quyền, lạm dụng danh tính hoặc khó kiểm soát vòng đời thông tin xác thực |
| GKE | Thiết lập private cluster, Workload Identity, node và nâng cấp | Truy cập trái phép vào control plane hoặc quyền workload vượt nhu cầu |
| Cloud KMS | Chính sách truy cập, xoay vòng khóa và phân tách nhiệm vụ | Khóa bị lạm dụng hoặc không đáp ứng yêu cầu quản lý vòng đời khóa |
| Cloud Logging và Monitoring | Audit log, log sink, alert policy | Thiếu bằng chứng điều tra hoặc không phát hiện thay đổi nhạy cảm kịp thời |

Danh sách trên minh họa các miền cấu hình; detector cụ thể, loại tài nguyên được hỗ trợ và trạng thái bật mặc định phụ thuộc phiên bản dịch vụ và tier SCC. Hãy tra cứu danh mục detector hiện hành trước khi thiết kế tiêu chí kiểm soát cho một hệ thống.

### Đọc một finding như thế nào?

Khi mở finding trong SCC, hãy kiểm tra tối thiểu các thông tin sau:

1. **Category và source:** tên loại vấn đề và dịch vụ tạo ra finding. Đây là điểm bắt đầu để tra cứu detector và hướng dẫn khắc phục.
2. **Severity:** mức độ nghiêm trọng do dịch vụ gán. Severity là tín hiệu ưu tiên, không tự động thay thế đánh giá rủi ro của tổ chức.
3. **State:** finding đang `ACTIVE` hay `INACTIVE`.
4. **Affected resource:** tên đầy đủ, project và loại tài nguyên bị ảnh hưởng.
5. **Event time và thông tin phát hiện:** thời điểm ghi nhận, thuộc tính cấu hình liên quan và mô tả lý do detector tạo finding.
6. **Recommendation:** gợi ý xử lý. Cần đối chiếu với kiến trúc và yêu cầu nghiệp vụ trước khi thay đổi tài nguyên.

Không ưu tiên chỉ dựa trên severity. Một finding mức Medium trên bucket chứa dữ liệu nhạy cảm và đang công khai có thể cần xử lý trước một finding mức High trên tài nguyên thử nghiệm không thể truy cập từ bên ngoài. Khi phân loại, kết hợp severity với khả năng tiếp cận từ Internet, độ nhạy dữ liệu, quyền mà danh tính có thể đạt được, môi trường production, đường tấn công và tác động nếu thay đổi cấu hình.

## 4. Điều kiện sử dụng và cách bật dịch vụ

Khả năng sử dụng SHA phụ thuộc **Security Command Center tier, phạm vi kích hoạt và lịch sử chuyển đổi tier** của tổ chức. Không nên chỉ nhìn tên tier rồi kết luận mọi detector đều có sẵn. Tài liệu Google Cloud hiện mô tả những trường hợp khác nhau giữa Standard, Standard-legacy và Premium; một số tổ chức mới kích hoạt Premium hoặc đã chuyển tier cần dùng **Compliance Manager** để quét cấu hình sai. Ngược lại, tài liệu kích hoạt SCC Standard cũng mô tả SHA được tự động bật trong luồng kích hoạt Standard. Vì vậy, hãy kiểm tra trạng thái thực tế trong Settings và lịch sử migration của tổ chức.

Quy trình kiểm tra trên Google Cloud Console:

1. Mở **Security Command Center** và chọn đúng organization hoặc project.
2. Vào **Settings** và mở phần quản lý dịch vụ.
3. Tìm **Security Health Analytics**; kiểm tra dịch vụ có khả dụng và đang bật ở phạm vi cần bảo vệ hay không.
4. Trong **Service enablement**, chọn organization, folder hoặc project và đặt trạng thái `Enable`, `Disable` hoặc `Inherit` theo mô hình quản trị.
5. Mở tab **Modules** để xem detector nào đang bật. Bật các detector phù hợp với yêu cầu bảo mật và phạm vi tài nguyên.
6. Vào **Findings** để xác nhận kết quả sau khi quá trình onboarding và scan hoàn tất.

Nếu SHA không khả dụng trong cấu hình SCC hiện tại, kiểm tra hướng dẫn **Compliance Manager** và framework phù hợp thay vì giả định rằng việc bật một công tắc sẽ cung cấp đầy đủ detector. Với một số tier và tổ chức được chuyển đổi từ cấu hình cũ, tập detector hoặc cách hiển thị finding có thể khác nhau.

### Quyền IAM cần thiết

Quyền phụ thuộc thao tác và phạm vi tổ chức, folder hoặc project. Một số predefined role thường gặp gồm:

- `roles/securitycenter.settingsEditor`: quản lý thiết lập và bật/tắt detector khi được cấp đúng phạm vi.
- `roles/securitycenter.findingsViewer`: xem và lọc findings.
- `roles/securitycenter.settingsAdmin`: quản trị thiết lập SCC rộng hơn.
- Các role quản lý mute configuration hoặc findings chỉ nên cấp cho người thực sự cần thực hiện thao tác đó.

Áp dụng least privilege: người xử lý finding không nhất thiết cần quyền quản trị toàn bộ SCC hoặc quyền sửa mọi tài nguyên. Nếu người dùng xem được finding nhưng không sửa được bucket, firewall hay database, hãy yêu cầu chủ sở hữu tài nguyên thực hiện thay đổi qua quy trình được phê duyệt.

### Cách SHA quét tài nguyên và thời gian xuất hiện finding

SHA có ba kiểu scan:

- **Batch scan:** detector chạy theo lịch trên các organization hoặc project đã tham gia.
- **Real-time scan:** với Google Cloud và detector hỗ trợ, thay đổi cấu hình tài nguyên có thể kích hoạt scan sau khi thay đổi được ghi nhận.
- **Mixed-mode:** một detector hỗ trợ real-time nhưng không phải mọi loại tài nguyên của detector đó đều được cập nhật theo thời gian thực; một số trường hợp vẫn chờ batch scan.

Theo tài liệu SHA hiện hành, batch scan thường chạy hằng ngày ở Premium và Enterprise (tier Enterprise đã được đánh dấu deprecated), còn Standard và Standard-legacy có lịch quét mỗi 48 giờ. Lần scan đầu có thể bắt đầu sau khoảng một giờ ở Premium/Enterprise và mất đến 12 giờ để hoàn tất; với Standard, độ trễ ban đầu có thể lên đến khoảng 72 giờ. Đây là mục tiêu vận hành của lịch quét, không phải cam kết SLA. Thời gian thực tế còn phụ thuộc số lượng project, tài nguyên, quá trình onboarding và detector.

Do đó, ngay sau khi bật dịch vụ hoặc sửa tài nguyên, không nên dùng một lần truy vấn findings để kết luận toàn bộ môi trường đã được quét. Kiểm tra thời gian scan, trạng thái onboarding và chế độ scan của detector liên quan. Khi cần xác nhận khẩn cấp, hãy kiểm tra trực tiếp cấu hình tài nguyên qua Console, gcloud hoặc API.

## 5. Những cấu hình sai phổ biến và hướng khắc phục

### 5.1. Cloud Storage bucket có thể truy cập công khai

Một bucket chứa dữ liệu nội bộ nhưng được cấp quyền cho `allUsers` hoặc `allAuthenticatedUsers` có thể làm dữ liệu bị đọc ngoài dự kiến. Quyền công khai có thể đến từ IAM policy hoặc ACL cũ; chỉ kiểm tra một trong hai nơi có thể bỏ sót đường truy cập.

Hướng xử lý:

1. Xác định bucket, dữ liệu bên trong và ứng dụng đang phụ thuộc vào quyền hiện tại.
2. Kiểm tra IAM policy, ACL và mục đích truy cập. Nếu dữ liệu phải riêng tư, loại bỏ principal công khai.
3. Bật **Public access prevention** và **Uniform bucket-level access** khi phù hợp với thiết kế.
4. Kiểm tra lại quyền của service account và ứng dụng để tránh làm gián đoạn workload hợp lệ.
5. Nếu bucket được công khai có chủ đích để phân phối nội dung, ghi nhận chủ sở hữu, dữ liệu được phép công khai và phương án phân phối đã được duyệt.

Ví dụ Terraform cho bucket riêng tư:

~~~hcl
resource "google_storage_bucket" "private_data" {
  name                        = var.bucket_name
  location                    = "ASIA-SOUTHEAST1"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }
}
~~~

Hai lệnh sau minh họa cách áp dụng hai thiết lập trên bằng gcloud Storage:

~~~bash
gcloud storage buckets update gs://BUCKET_NAME --public-access-prevention
gcloud storage buckets update gs://BUCKET_NAME --uniform-bucket-level-access
~~~

Thay `BUCKET_NAME` bằng bucket thực tế. Trước khi áp dụng, kiểm tra ứng dụng có đang phụ thuộc vào ACL hoặc quyền truy cập công khai hay không.

### 5.2. Firewall mở SSH hoặc RDP ra Internet

Một ingress rule cho TCP 22 hoặc 3389 với source range `0.0.0.0/0` cho phép mọi địa chỉ IPv4 thử kết nối đến các VM khớp target của rule. Điều này làm tăng nguy cơ dò mật khẩu, khai thác lỗ hổng dịch vụ quản trị và tạo thêm điểm vào hệ thống.

Hướng xử lý:

- Xác định VM, tag hoặc service account đang khớp rule và kiểm tra có rule khác cũng cho phép cùng cổng hay không.
- Xóa rule không còn cần thiết. Nếu vẫn cần quản trị, giới hạn source range vào dải VPN hoặc mạng quản trị đã kiểm soát.
- Cân nhắc dùng Identity-Aware Proxy (IAP) cho TCP forwarding thay vì mở cổng quản trị trực tiếp ra Internet.
- Chỉ cho phép đúng protocol, port và nhóm VM cần thiết; tránh dùng target quá rộng.
- Kiểm tra cả firewall rule cấp VPC và các chính sách firewall phân cấp nếu tổ chức sử dụng chúng.

Không sửa source range một cách máy móc: cần chắc chắn dải IP thay thế thực sự thuộc mạng tin cậy và có đường định tuyến phù hợp.

### 5.3. Cloud SQL có IP công khai hoặc kết nối quá rộng

IP công khai không tự động đồng nghĩa database đã bị xâm nhập, nhưng nó làm tăng bề mặt tiếp cận. Rủi ro tăng cao khi authorized networks chứa dải IP rộng, TLS không được yêu cầu hoặc cấu hình backup chưa đáp ứng mục tiêu phục hồi.

Hướng xử lý:

- Xác minh ứng dụng và công cụ vận hành đang kết nối database từ đâu.
- Ưu tiên private IP hoặc phương án kết nối riêng phù hợp với kiến trúc; dùng Cloud SQL Auth Proxy hoặc connector khi thích hợp.
- Nếu phải giữ public IP, giới hạn authorized networks đến địa chỉ nguồn cố định và cần thiết.
- Yêu cầu TLS, rà soát tài khoản database và IAM, kiểm tra backup, retention và khả năng phục hồi.
- Thử kết nối từ ứng dụng sau thay đổi trước khi kết luận database đã được bảo vệ.

### 5.4. IAM cấp quyền quá rộng

Các role cơ bản như `roles/owner` và `roles/editor` có phạm vi quyền lớn. Cấp những role này cho người dùng, nhóm hoặc service account chỉ để giải quyết một thao tác nhỏ sẽ làm tăng tác động nếu danh tính bị lộ hoặc sử dụng sai mục đích. Principal công khai như `allUsers` và `allAuthenticatedUsers` cũng cần được rà soát kỹ.

Hướng xử lý:

1. Xác định principal, resource, role và lý do cấp quyền.
2. Thay role cơ bản bằng predefined role hẹp hơn hoặc custom role khi thật sự cần.
3. Ưu tiên cấp quyền qua Google Group có chủ sở hữu và quy trình rà soát thành viên.
4. Dùng IAM Conditions khi cần giới hạn quyền theo thuộc tính hoặc ngữ cảnh được hỗ trợ.
5. Tách danh tính con người khỏi workload; dùng service account riêng cho ứng dụng và chỉ cấp quyền cần thiết.
6. Kiểm tra lại quyền kế thừa từ organization và folder, vì một binding ở cấp cao có thể tác động đến nhiều project.

### 5.5. Khóa service account do người dùng quản lý

Khóa JSON dài hạn có thể bị sao chép ra khỏi môi trường Google Cloud và khó kiểm soát vòng đời. Nếu ứng dụng chạy trên Google Cloud, ưu tiên danh tính gắn với workload hoặc cơ chế xác thực không cần lưu khóa dài hạn. Với workload trên GKE, xem xét Workload Identity; với hệ thống bên ngoài, dùng cơ chế liên kết danh tính phù hợp nếu kiến trúc hỗ trợ.

Khi phát hiện khóa không còn cần thiết, xác định workload đang dùng khóa trước khi thu hồi. Sau đó chuyển ứng dụng sang cơ chế xác thực mới, thu hồi khóa cũ, kiểm tra log sử dụng và đưa quy trình xoay vòng vào vận hành.

### 5.6. GKE cluster thiếu cấu hình bảo vệ

Một số detector có thể kiểm tra các thiết lập như private cluster, Workload Identity, Shielded GKE Nodes, auto-repair hoặc auto-upgrade. Mức hỗ trợ cụ thể tùy loại cluster và detector.

Trước khi thay đổi, kiểm tra phiên bản GKE, cách workload lấy credential, quyền truy cập control plane, luồng CI/CD và yêu cầu kết nối của nhóm vận hành. Bật private endpoint hoặc thay đổi authorized networks mà không chuẩn bị đường truy cập quản trị có thể làm pipeline hoặc đội vận hành mất kết nối. Thực hiện theo từng cluster, có kế hoạch rollback và xác minh workload sau triển khai.

### 5.7. Thiếu audit logging và cảnh báo

Nếu audit log cho thao tác nhạy cảm không được thu thập hoặc log sink không chuyển dữ liệu đến nơi lưu trữ phù hợp, đội ngũ có thể không đủ bằng chứng để điều tra. Nếu không có alert policy cho thay đổi quan trọng, một cấu hình sai có thể tồn tại lâu trước khi được phát hiện.

Rà soát Data Access audit logs theo yêu cầu dữ liệu và chi phí, cấu hình log sink, thời gian lưu giữ, quyền truy cập log và cảnh báo cho các thay đổi IAM, firewall, bucket, database hoặc chính sách tổ chức. Bật logging mà không có người nhận cảnh báo và quy trình phản hồi vẫn để lại khoảng trống vận hành.

## 6. Quy trình xử lý finding từ lúc phát hiện đến khi đóng

Một quy trình nhất quán giúp tránh hai lỗi thường gặp: bỏ qua finding vì có quá nhiều cảnh báo, hoặc sửa nhanh một cấu hình mà không hiểu tác động đến ứng dụng.

### Bước 1: Xác nhận phạm vi và mức độ ảnh hưởng

Mở finding, xác định category, severity, state, resource name, project, thời điểm phát hiện và mô tả cấu hình. Kiểm tra tài nguyên có nằm trong production không, dữ liệu có nhạy cảm không, có thể truy cập từ Internet không và danh tính nào có thể khai thác quyền liên quan.

### Bước 2: Xác minh cấu hình hiện tại

Đối chiếu finding với cấu hình trực tiếp trong Google Cloud Console, gcloud hoặc API. Xem xét thời điểm scan và các thay đổi gần đây. Nếu finding cũ nhưng tài nguyên đã được sửa, xác minh trực tiếp trước khi mở một thay đổi mới. Nếu finding chưa xuất hiện nhưng có bằng chứng cấu hình đang mở, xử lý theo quy trình sự cố phù hợp thay vì chờ detector.

### Bước 3: Tìm chủ sở hữu và nguồn cấu hình

Tìm nhóm sở hữu workload và xác định cấu hình được quản lý ở đâu: Terraform, pipeline, cấu hình ứng dụng hay thao tác thủ công. Nếu chỉ sửa trực tiếp trên Console trong khi Terraform vẫn giữ giá trị cũ, lần chạy pipeline tiếp theo có thể đưa cấu hình sai trở lại.

### Bước 4: Chọn biện pháp khắc phục

Ưu tiên sửa nguyên nhân gốc bằng thay đổi nhỏ nhất đáp ứng yêu cầu bảo mật. Đánh giá ảnh hưởng đến ứng dụng, kết nối, dữ liệu và quy trình vận hành. Với rủi ro đang phơi bày dữ liệu hoặc quyền quản trị, phối hợp chủ sở hữu để giảm phơi nhiễm sớm, đồng thời ghi lại bằng chứng và kế hoạch hoàn thiện.

### Bước 5: Triển khai và xác minh

Đưa thay đổi vào mã nguồn hạ tầng khi có thể; review plan, kiểm tra môi trường đích và áp dụng qua pipeline đã được phê duyệt. Sau triển khai, kiểm tra lại cấu hình thực tế và thực hiện smoke test cho workload. Với thay đổi IAM hoặc mạng, kiểm tra cả quyền và đường kết nối cần thiết.

### Bước 6: Chờ scan và kiểm tra trạng thái

Khi SHA scan và xác nhận cấu hình không còn vi phạm, dịch vụ thường tự chuyển finding sang `INACTIVE`. Thời gian chuyển trạng thái phụ thuộc chế độ và lịch scan của detector. `INACTIVE` là tín hiệu finding không còn được phát hiện trong lần scan tương ứng; vẫn nên xác minh cấu hình thực tế nếu vấn đề có ảnh hưởng lớn.

**Mute không phải remediation.** Mute chỉ giúp giảm nhiễu khi finding được chấp nhận hoặc cần loại khỏi luồng xử lý hiển thị. Nó không sửa tài nguyên và không ngăn cấu hình gây rủi ro. Nếu finding được mute vì ngoại lệ nghiệp vụ, ghi rõ lý do, chủ sở hữu, phạm vi, người phê duyệt và thời điểm rà soát lại.

Lưu ý thêm: việc tắt detector cũng có thể làm findings do detector đó tạo ra chuyển sang `INACTIVE`. Vì vậy, không được xem mọi finding `INACTIVE` là bằng chứng tài nguyên đã được sửa; cần kiểm tra xem detector có bị tắt hoặc tier có thay đổi hay không.

## 7. Ngăn cấu hình sai quay trở lại

SHA tạo vòng phản hồi phát hiện, nhưng phòng ngừa phải được đặt trong cách tổ chức quản lý hạ tầng:

- **Organization Policy:** đặt guardrail ở cấp organization hoặc folder cho những yêu cầu bắt buộc, chẳng hạn ngăn public access vào Storage, giới hạn external IP hoặc kiểm soát vị trí tài nguyên khi phù hợp. Kiểm tra constraint hiện hành và ngoại lệ trước khi áp dụng ở phạm vi lớn.
- **IAM theo least privilege:** dùng nhóm có chủ sở hữu, role hẹp, service account riêng cho workload và rà soát quyền kế thừa định kỳ.
- **VPC và phân vùng mạng:** quản lý firewall theo nhóm workload, giới hạn ingress, dùng private connectivity khi phù hợp và kiểm tra các đường truy cập quản trị.
- **Infrastructure as Code:** lưu cấu hình chuẩn trong Terraform hoặc công cụ IaC đang dùng. Thay đổi trên Console cần được đồng bộ về mã nguồn để tránh drift.
- **CI/CD và policy as code:** kiểm tra plan trước khi apply; chặn cấu hình vi phạm chính sách quan trọng; yêu cầu review với thay đổi IAM, network, storage và database có rủi ro cao.
- **Logging và vận hành:** gửi finding đến nhóm chịu trách nhiệm, đặt thời hạn xử lý theo mức độ rủi ro, theo dõi tuổi finding và kiểm tra lại các ngoại lệ đã mute.
- **Quản lý chi phí:** chọn tier SCC và phạm vi kích hoạt theo yêu cầu bảo mật, hiểu mô hình tính phí của dịch vụ liên quan và tránh bật dịch vụ tích hợp ngoài nhu cầu.

Một kiểm soát chỉ bền vững khi có đủ ba phần: quy tắc rõ ràng, cơ chế phát hiện và người chịu trách nhiệm xử lý. Dashboard có nhiều finding đã đóng nhưng cùng lỗi liên tục tái xuất hiện cho thấy guardrail hoặc quy trình phát hành chưa giải quyết được nguyên nhân gốc.

## 8. Tình huống thực hành: xử lý bucket dữ liệu bị công khai

Một nhóm phân tích tạo bucket `customer-export-prod` để lưu file xuất dữ liệu. Một thay đổi IAM vô tình thêm `allUsers` với quyền đọc. SHA tạo finding cho bucket có quyền truy cập công khai.

**Phân tích:**

1. Mở finding và xác nhận đúng bucket, project production, category, severity và thời điểm phát hiện.
2. Kiểm tra IAM policy và ACL để biết quyền công khai được cấp ở đâu. Xác định loại dữ liệu trong bucket và kiểm tra log truy cập nếu có dấu hiệu đã bị đọc ngoài dự kiến.
3. Liên hệ nhóm sở hữu dữ liệu để xác định ứng dụng nào đang dùng bucket. Nếu không có yêu cầu công khai, loại bỏ principal công khai và bật Public access prevention cùng Uniform bucket-level access.
4. Sửa Terraform để lưu cấu hình an toàn vào mã nguồn. Tạo pull request, xem plan và kiểm tra các workload đọc dữ liệu bằng service account có tiếp tục hoạt động không.
5. Triển khai thay đổi, xác minh quyền truy cập từ danh tính hợp lệ và thử truy cập không xác thực để chắc chắn dữ liệu không còn công khai.
6. Theo dõi lần scan kế tiếp để xác nhận finding chuyển sang `INACTIVE`. Nếu trạng thái chưa đổi, kiểm tra scan latency, detector và cấu hình thực tế.
7. Bổ sung Organization Policy hoặc kiểm tra CI để ngăn bucket tương tự được tạo với quyền công khai trong tương lai.

**Kết quả mong đợi:** dữ liệu chỉ được truy cập bởi danh tính được cấp quyền; cấu hình an toàn được lưu trong IaC; finding được xác minh sau scan; nhóm sở hữu và cách ngăn tái diễn đã được ghi nhận.

## 9. Giới hạn và những điều không nên suy luận từ SHA

- Không có finding không đồng nghĩa không có lỗ hổng, mã độc, secret bị lộ hoặc đường tấn công. SHA tập trung vào các cấu hình mà detector hỗ trợ.
- Một detector có thể chỉ quét một số resource type hoặc một số thuộc tính của dịch vụ. Kiểm tra danh mục hỗ trợ thay vì suy rộng từ tên dịch vụ.
- Real-time scan không áp dụng cho mọi detector và mọi tài nguyên. Một số finding chỉ được cập nhật sau batch scan.
- Finding có thể cũ hơn trạng thái cấu hình hiện tại. Luôn đối chiếu thời điểm scan và kiểm tra trực tiếp tài nguyên khi cần.
- Severity là tín hiệu kỹ thuật; ưu tiên xử lý phải tính đến dữ liệu, khả năng tiếp cận, môi trường, tác động và bối cảnh kinh doanh.
- Compliance mapping hỗ trợ đánh giá một tập kiểm soát. Nó không tự chứng nhận toàn bộ hệ thống đáp ứng tiêu chuẩn hoặc yêu cầu pháp lý.
- Việc tắt detector, mute finding hoặc thay đổi SCC tier có thể ảnh hưởng cách findings được hiển thị và trạng thái của chúng. Không dùng các thao tác đó để thay thế việc khắc phục cấu hình.

## 10. Kiểm tra mức độ hiểu bài

1. Một finding báo bucket có quyền công khai. Trước khi bật Public access prevention, bạn cần xác minh những gì để tránh làm gián đoạn ứng dụng?
2. Vì sao một finding `ACTIVE` ngay sau khi sửa firewall chưa chắc có nghĩa thay đổi thất bại?
3. Khi một finding chuyển sang `INACTIVE`, những nguyên nhân nào ngoài việc cấu hình đã được sửa có thể giải thích trạng thái đó?
4. Một project có Cloud SQL public IP nhưng chỉ cho phép một dải IP quản trị cố định. Bạn sẽ đánh giá rủi ro và đề xuất kiến trúc kết nối như thế nào?
5. Vì sao sửa trực tiếp trên Console mà không cập nhật Terraform có thể khiến cấu hình sai quay trở lại?
6. Nếu SHA không khả dụng trong tier hoặc lịch sử kích hoạt của tổ chức, bạn cần kiểm tra giải pháp nào để tiếp tục đánh giá cấu hình và tuân thủ?

## Tài liệu tham khảo

- [Overview of Security Health Analytics](https://docs.cloud.google.com/security-command-center/docs/concepts-security-health-analytics)
- [Configure Security Command Center services](https://docs.cloud.google.com/security-command-center/docs/how-to-configure-security-command-center)
- [Use Security Health Analytics](https://docs.cloud.google.com/security-command-center/docs/how-to-use-security-health-analytics)
- [Remediate Security Health Analytics findings](https://docs.cloud.google.com/security-command-center/docs/how-to-remediate-security-health-analytics-findings)
- [Review and manage findings](https://docs.cloud.google.com/security-command-center/docs/review-manage-findings)
- [Security Command Center service tiers](https://docs.cloud.google.com/security-command-center/docs/service-tiers)
- [Compliance Manager overview](https://docs.cloud.google.com/security-command-center/docs/compliance-manager-overview)
