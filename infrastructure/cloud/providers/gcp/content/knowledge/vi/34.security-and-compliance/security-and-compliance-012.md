# Ứng phó sự cố bảo mật và bảo toàn chứng cứ trên GCP

Khi phát hiện một tài khoản bị chiếm quyền, một máy ảo phát sinh lưu lượng bất thường hoặc dữ liệu có dấu hiệu bị truy cập trái phép, nhóm vận hành cần vừa hạn chế thiệt hại vừa giữ lại thông tin đủ tin cậy để xác định điều gì đã xảy ra. Trên Google Cloud, chứng cứ có thể nằm rải rác trong Cloud Audit Logs, Cloud Logging, Security Command Center, IAM, cấu hình tài nguyên, image container, snapshot đĩa và hệ thống nghiệp vụ.

Ứng phó sự cố bảo mật vì thế là một quy trình phối hợp giữa kỹ thuật, vận hành, quản trị rủi ro và pháp lý. Mỗi hành động như dừng VM, xóa Pod, thu hồi khóa, thay đổi IAM hoặc triển khai lại dịch vụ đều có thể làm thay đổi dấu vết. Nhóm xử lý cần xác định thứ tự hành động, ghi lại quyết định và bảo toàn bản chứng cứ có thể kiểm tra lại.

Bài học này trình bày cách chuẩn bị, phát hiện, phân loại, cô lập, thu thập và bảo quản chứng cứ trong môi trường Google Cloud, với ví dụ cho Compute Engine, GKE, Cloud Run, Cloud SQL, Cloud Storage và danh tính IAM.

## 1. Mục tiêu và nguyên tắc ứng phó

Một quy trình ứng phó sự cố cần đạt bốn mục tiêu:

1. **Bảo vệ con người, dịch vụ và dữ liệu.** Hạn chế truy cập trái phép, rò rỉ dữ liệu và ảnh hưởng đến khách hàng.
2. **Hiểu phạm vi và nguyên nhân.** Xác định tài khoản, project, workload, dữ liệu, khu vực và khoảng thời gian có liên quan.
3. **Bảo toàn chứng cứ.** Giữ dữ liệu gốc, metadata, dấu thời gian và lịch sử thao tác đủ để tái dựng diễn biến.
4. **Khôi phục có kiểm soát.** Loại bỏ nguyên nhân, khôi phục dịch vụ an toàn và theo dõi nguy cơ tái diễn.

Trong lúc xử lý, áp dụng các nguyên tắc sau:

- **Ưu tiên an toàn và giới hạn thiệt hại.** Nếu có hoạt động đánh cắp dữ liệu đang diễn ra, việc cô lập ngay có thể quan trọng hơn việc thu thập đầy đủ mọi dấu vết. Ghi lại lý do và thời điểm của quyết định đó.
- **Ghi nhận trước khi thay đổi.** Khi có thể, chụp lại trạng thái tài nguyên, IAM, mạng, tiến trình triển khai và log trước khi thực hiện thao tác làm thay đổi hệ thống.
- **Giữ bản gốc và làm việc trên bản sao.** Không chỉnh sửa, lọc ghi đè hoặc mở trực tiếp bản chứng cứ gốc bằng công cụ có thể thay đổi nội dung.
- **Dùng thời gian UTC nhất quán.** Ghi cả thời gian sự kiện, thời gian thu thập và múi giờ nguồn. Không mặc định mọi đồng hồ máy chủ đều đồng bộ chính xác.
- **Giới hạn người tiếp cận.** Chỉ nhóm được ủy quyền mới có quyền đọc chứng cứ, đặc biệt khi dữ liệu chứa thông tin cá nhân, bí mật kinh doanh hoặc thông tin xác thực.
- **Ghi lại mọi thao tác.** Người thực hiện, thời điểm, mục đích, lệnh hoặc thay đổi đã áp dụng và kết quả đều cần xuất hiện trong nhật ký xử lý.

Không phải mọi sự kiện cảnh báo đều là một sự cố đã xác nhận. Một phát hiện từ hệ thống giám sát cần được xác minh, nhưng nhóm cũng không nên trì hoãn cô lập khi có dấu hiệu xâm nhập đang tiếp diễn.

## 2. Chuẩn bị trước khi xảy ra sự cố

Khả năng bảo toàn chứng cứ phụ thuộc nhiều vào cấu hình được chuẩn bị từ trước. Nếu audit log chưa được bật, log đã hết thời hạn lưu giữ hoặc không có nơi tập trung log, nhóm có thể không khôi phục được toàn bộ diễn biến sau sự cố.

### Thiết lập trách nhiệm và kênh điều phối

Một kế hoạch ứng phó nên xác định trước:

- Incident commander chịu trách nhiệm điều phối và ưu tiên hành động.
- Nhóm Cloud/SRE quản lý project, mạng, VM, GKE, Cloud Run và cơ sở dữ liệu.
- Nhóm Security phân tích cảnh báo, danh tính, lỗ hổng và phạm vi xâm nhập.
- Nhóm pháp lý, quyền riêng tư hoặc tuân thủ đánh giá nghĩa vụ thông báo, bảo toàn hồ sơ và yêu cầu pháp lý.
- Chủ sở hữu ứng dụng xác định ảnh hưởng nghiệp vụ, tính toàn vẹn dữ liệu và điều kiện khôi phục.

Cần có danh sách liên lạc khẩn cấp, quyền truy cập break-glass được kiểm soát, quy trình phê duyệt khi cô lập production và một kênh trao đổi riêng không phụ thuộc vào hệ thống có thể đã bị xâm nhập.

### Bật và tập trung audit log

Cloud Audit Logs ghi nhận hoạt động quản trị và truy cập tài nguyên. Các nhóm log chính gồm:

| Loại log | Nội dung điển hình | Lưu ý |
|---|---|---|
| Admin Activity | Thay đổi cấu hình và thao tác quản trị | Được ghi tự động; không thể tắt |
| System Event | Sự kiện hệ thống do Google Cloud thực hiện | Hữu ích khi điều tra thay đổi do nền tảng khởi tạo |
| Policy Denied | Yêu cầu bị từ chối do chính sách | Giúp phát hiện hoạt động bị chặn hoặc dò quyền |
| Data Access | Đọc hoặc ghi dữ liệu, truy cập dịch vụ | Nhiều dịch vụ yêu cầu bật rõ ràng; có thể phát sinh chi phí log |

Log mặc định được lưu trong các log bucket của Cloud Logging với thời hạn khác nhau. Ví dụ, log thuộc bucket _Required có thời hạn lưu mặc định 400 ngày; bucket _Default thường có thời hạn mặc định 30 ngày. Cấu hình thực tế có thể đã được thay đổi. Hãy kiểm tra retention của từng bucket, phạm vi log được thu thập và yêu cầu lưu giữ của tổ chức.

Với môi trường quan trọng, nên:

- Bật Data Access audit logs cho dịch vụ và loại dữ liệu cần điều tra.
- Tập trung log ở project bảo mật hoặc project logging riêng, có IAM tách biệt với workload.
- Tạo log sink đến Cloud Storage hoặc BigQuery để phân tích và lưu giữ dài hạn.
- Bảo vệ quyền sửa sink, xóa log, thay đổi retention và cấp quyền đọc log.
- Kiểm tra log routing, exclusion filter và các project nằm ngoài phạm vi thu thập.
- Thử diễn tập truy vấn và xuất log để xác nhận dữ liệu thực sự có thể lấy được.

Log sink chỉ chuyển các log mới phù hợp với bộ lọc sau khi sink hoạt động; nó không tự động xuất ngược toàn bộ log lịch sử. Khi cần điều tra khoảng thời gian trước đó, hãy truy vấn và xuất log đã tồn tại trong Cloud Logging.

### Chuẩn bị kho chứng cứ

Tạo một project hoặc bucket chuyên dụng cho chứng cứ, với quyền truy cập tối thiểu và audit log riêng. Có thể tổ chức dữ liệu theo mã sự cố, project nguồn, loại tài nguyên và thời gian thu thập.

Nên chuẩn bị:

- Bucket lưu chứng cứ có mã hóa, retention phù hợp và quyền xóa được giới hạn.
- Quy trình tạo manifest chứa tên tệp, nguồn, thời gian thu thập, người thu thập và SHA-256.
- Tài khoản thu thập riêng, chỉ có quyền đọc dữ liệu cần thiết và ghi vào kho chứng cứ.
- Cơ chế sao lưu hoặc bản sao độc lập để giảm nguy cơ bị xóa cùng môi trường nguồn.
- Quy trình legal hold khi có yêu cầu pháp lý hoặc điều tra chính thức.

Cloud Storage Bucket Lock có thể khóa retention policy theo cách không thể đảo ngược sau khi xác nhận. Chỉ áp dụng khi thời hạn lưu giữ, quyền sở hữu và yêu cầu pháp lý đã được phê duyệt. Không bật khóa không thể đảo ngược một cách tùy tiện trong lúc xử lý sự cố.

### Duy trì trạng thái nền

Lưu lại danh mục project, folder, organization, tài khoản dịch vụ, tài nguyên trọng yếu, cấu hình mạng, chính sách IAM và các image đang triển khai. Cloud Asset Inventory có thể hỗ trợ xuất trạng thái tài nguyên và chính sách để so sánh với thời điểm sự cố.

Một baseline có dấu thời gian giúp trả lời các câu hỏi: tài nguyên nào mới xuất hiện, ai cấp quyền mới, firewall rule nào vừa thay đổi và workload nào vừa được triển khai.

## 3. Phát hiện, xác minh và phân loại sự cố

Nguồn phát hiện có thể là Security Command Center, Event Threat Detection, log cảnh báo, hệ thống EDR, phản ánh từ người dùng, nhà cung cấp dịch vụ hoặc phát hiện bất thường trong hóa đơn.

Một số tín hiệu cần điều tra:

- Service account sử dụng ở khu vực, thời điểm hoặc workload không thường thấy.
- Khóa service account mới được tạo hoặc sử dụng bất thường.
- Quyền IAM được cấp rộng, thay đổi role hoặc thêm thành viên lạ.
- VM có IP công khai, tiến trình hoặc kết nối mạng bất thường.
- Pod trong GKE chạy image lạ, có quyền đặc biệt hoặc truy cập metadata server trái phép.
- Cloud Run revision mới dùng image digest không được phê duyệt.
- Cloud Storage xuất hiện hoạt động đọc hàng loạt, thay đổi ACL hoặc xóa object.
- Cloud SQL có kết nối, truy vấn hoặc thao tác quản trị bất thường.
- Logging sink, retention, audit configuration hoặc Security Command Center bị thay đổi.

### Triage ban đầu

Ngay khi nhận cảnh báo, tạo một hồ sơ sự cố và ghi:

| Trường | Nội dung cần ghi |
|---|---|
| Incident ID | Mã định danh duy nhất |
| Thời điểm phát hiện | Thời gian UTC và nguồn phát hiện |
| Người báo cáo | Nhóm hoặc hệ thống gửi cảnh báo |
| Project và resource | Project ID, project number, resource name, region/zone |
| Principal liên quan | Email service account, người dùng hoặc danh tính liên kết |
| Dấu hiệu ban đầu | Log entry, finding ID, IP, image digest hoặc hành vi bất thường |
| Mức độ ảnh hưởng | Dịch vụ, dữ liệu, khách hàng và khu vực bị ảnh hưởng |
| Hành động đã thực hiện | Thời điểm, người thực hiện, lý do và kết quả |

Phân loại mức độ theo tác động và phạm vi, chẳng hạn:

- **Thấp:** hoạt động bất thường bị chặn, chưa có bằng chứng truy cập trái phép.
- **Trung bình:** một tài khoản hoặc workload có dấu hiệu bị xâm nhập nhưng phạm vi còn giới hạn.
- **Cao:** có khả năng truy cập trái phép vào dữ liệu nhạy cảm, quyền quản trị hoặc nhiều workload.
- **Nghiêm trọng:** exfiltration đang diễn ra, mã độc lan rộng, phá hoại dữ liệu hoặc ảnh hưởng lớn đến dịch vụ trọng yếu.

Mức độ có thể tăng hoặc giảm khi có chứng cứ mới. Không dùng riêng số lượng cảnh báo để quyết định mức độ; cần xem xét độ nhạy cảm dữ liệu, quyền của principal và khả năng lan rộng.

### Xây dựng dòng thời gian

Dòng thời gian nên kết hợp:

1. Sự kiện đầu tiên có dấu hiệu bất thường.
2. Hoạt động xác thực và thay đổi IAM.
3. Thay đổi cấu hình mạng hoặc tài nguyên.
4. Hoạt động của workload và dữ liệu.
5. Thời điểm phát hiện, cảnh báo và phản hồi.
6. Các hành động cô lập, thu thập, khôi phục.

Dùng timestamp trong log cùng metadata như principalEmail, callerIp, userAgent, resourceName, methodName và requestMetadata khi có. Các trường này có thể không xuất hiện trong mọi loại log hoặc mọi dịch vụ.

## 4. Trình tự ứng phó và quyết định cô lập

Một vòng đời ứng phó thường gồm chuẩn bị, phát hiện và phân tích, ngăn chặn, loại bỏ nguyên nhân, khôi phục và rút kinh nghiệm.

~~~mermaid
flowchart TD
    A[Alert or report] --> B[Create incident record]
    B --> C[Validate and assess impact]
    C --> D{Active harm or exfiltration?}
    D -->|Yes| E[Contain immediately and record actions]
    D -->|No| F[Capture volatile evidence first]
    E --> G[Preserve logs and resource state]
    F --> G
    G --> H[Scope identities, workloads and data]
    H --> I[Eradicate root cause]
    I --> J[Recover with verified configuration]
    J --> K[Monitor and close incident]
~~~

### Khi nào cần cô lập ngay?

Nếu có hành vi đánh cắp dữ liệu, phá hoại hoặc lan truyền mã độc đang diễn ra, nhóm cần ưu tiên ngăn chặn. Ví dụ: chặn đường truyền ra ngoài, thu hẹp firewall rule, cô lập VM khỏi mạng ứng dụng hoặc vô hiệu hóa một credential bị lộ.

Nếu tình huống cho phép, hãy thu thập nhanh thông tin có tính biến động trước khi cô lập: thời điểm, kết nối mạng, tiến trình, phiên đăng nhập, Pod/VM đang chạy và log gần nhất. Không trì hoãn ngăn chặn chỉ để thu thập đủ mọi thông tin.

### Cô lập theo lớp

| Lớp | Biện pháp có thể cân nhắc | Điều cần đánh giá |
|---|---|---|
| Danh tính | Vô hiệu hóa khóa, thu hẹp IAM, chặn principal hoặc credential | Có thể làm gián đoạn workload hợp lệ; token đã cấp có thể còn hiệu lực đến khi hết hạn |
| Mạng | Giới hạn ingress/egress, firewall policy, route hoặc quyền truy cập endpoint | Tránh làm mất đường quản trị và đường thu thập chứng cứ |
| Compute Engine | Cô lập NIC hoặc áp dụng rule mạng giới hạn | VM vẫn có thể tiếp tục ghi dữ liệu lên đĩa; dừng máy làm mất dữ liệu bộ nhớ |
| GKE | Cô lập workload hoặc namespace, giới hạn network policy và quyền service account | Xóa Pod hoặc drain node có thể làm mất dữ liệu tạm và trạng thái runtime |
| Cloud Run | Điều chỉnh traffic, rollback revision hoặc hạn chế quyền service identity | Lưu cấu hình revision, image digest và traffic trước khi thay đổi |
| Storage/Database | Thu hẹp quyền đọc/ghi, khóa tài khoản hoặc giới hạn kết nối | Có thể ảnh hưởng giao dịch đang chạy và khả năng khôi phục |

Không xóa VM, disk, Pod, revision, service account, khóa hoặc bucket chỉ để “dọn sạch” hệ thống. Xóa tài nguyên có thể phá hủy chứng cứ và làm mất khả năng xác định nguyên nhân. Nếu cần dừng một dịch vụ để bảo vệ dữ liệu, hãy ghi nhận trạng thái trước đó và lý do.

## 5. Thu thập Cloud Audit Logs và Cloud Logging

Cloud Audit Logs thường là nguồn quan trọng để xác định ai đã gọi API, thao tác gì và trên tài nguyên nào. Hãy bắt đầu với khoảng thời gian đủ rộng quanh sự kiện và mở rộng theo các principal hoặc resource liên quan.

Ví dụ truy vấn log trong một project theo thời gian:

~~~bash
gcloud logging read 'timestamp >= "2026-11-19T00:00:00Z" AND timestamp <= "2026-11-19T06:00:00Z"' \
  --project="PROJECT_ID" \
  --format=json > incident-audit-logs.json
~~~

Lọc theo principal trong payload của audit log:

~~~bash
gcloud logging read 'protoPayload.authenticationInfo.principalEmail="suspicious-sa@PROJECT_ID.iam.gserviceaccount.com" AND timestamp >= "2026-11-19T00:00:00Z"' \
  --project="PROJECT_ID" \
  --format=json > principal-activity.json
~~~

Truy vấn theo resource hoặc methodName khi đã biết dịch vụ và thao tác nghi vấn. Không giả định một bộ lọc duy nhất sẽ tìm thấy mọi dấu vết: mỗi dịch vụ có resource type, method name và cấu trúc payload riêng.

Sau khi xuất:

- Giữ nguyên tệp JSON ban đầu; không sửa trực tiếp để làm sạch dữ liệu.
- Ghi lại filter, project, khoảng thời gian, thời điểm chạy và danh tính người thu thập.
- Tính SHA-256 và ghi vào manifest.
- Nếu cần phân tích hoặc chuẩn hóa, tạo bản làm việc riêng.
- Kiểm tra số lượng bản ghi, lỗi truy vấn, giới hạn trang và khoảng thời gian đã truy xuất.

Ví dụ trên là thao tác đọc log và ghi ra tệp cục bộ. Với môi trường sản xuất, hãy dùng máy thu thập được kiểm soát, bảo vệ thư mục đầu ra và chuyển bản chứng cứ vào kho được phê duyệt. Không gửi log có dữ liệu cá nhân hoặc thông tin nhạy cảm lên kênh trao đổi không được phép.

### Các loại log cần kiểm tra

- **Cloud Audit Logs:** principal, API method, caller IP, user agent, resource và trạng thái.
- **VPC Flow Logs:** luồng mạng được ghi nhận theo cấu hình subnet; không phải packet capture đầy đủ.
- **Firewall Rules Logging:** kết nối khớp rule đã bật logging.
- **Cloud DNS logs:** truy vấn DNS nếu logging được bật.
- **Load Balancer logs:** request, status code, latency, backend và địa chỉ client theo cấu hình.
- **GKE audit/control-plane logs:** thao tác API Kubernetes và sự kiện control plane được cấu hình.
- **Ứng dụng và hệ điều hành:** authentication, process, package, endpoint, lỗi và hoạt động nghiệp vụ.

VPC Flow Logs và log load balancer có thể bị sampling hoặc giới hạn trường dữ liệu. Chúng hỗ trợ điều tra luồng hoạt động nhưng không thay thế packet capture hoặc log ứng dụng.

## 6. Bảo toàn chứng cứ theo loại tài nguyên

Chứng cứ có thể bao gồm log, cấu hình, metadata, snapshot, bản sao dữ liệu, image digest, finding và lịch sử triển khai. Mỗi loại cần cách thu thập riêng.

### IAM và danh tính dịch vụ

Thu thập chính sách IAM hiện tại, thông tin service account, metadata khóa, quyền ở cấp project và các log thay đổi liên quan.

~~~bash
gcloud projects get-iam-policy "PROJECT_ID" \
  --format=json > project-iam-policy.json

gcloud iam service-accounts keys list \
  --iam-account="SUSPICIOUS_SA@PROJECT_ID.iam.gserviceaccount.com" \
  --project="PROJECT_ID" \
  --format=json > service-account-key-metadata.json
~~~

Lệnh liệt kê khóa chỉ lấy metadata; không xuất private key. Ghi nhận key ID, trạng thái, thời điểm tạo và principal liên quan nếu thông tin có sẵn. Kiểm tra cả IAM policy inheritance ở organization và folder, service account impersonation, workload identity federation và quyền cấp qua nhóm.

Không tải khóa riêng xuống để “kiểm tra”. Không đưa secret payload, access token hoặc private key vào hồ sơ chứng cứ. Với Secret Manager, thu thập metadata version, IAM policy và audit log truy cập; tránh đọc giá trị bí mật nếu không có yêu cầu điều tra được phê duyệt.

### Cloud Asset Inventory

Cloud Asset Inventory hỗ trợ chụp trạng thái tài nguyên hoặc chính sách IAM tại thời điểm xác định. Ví dụ xuất tài nguyên của project đến bucket chứng cứ:

~~~bash
gcloud asset export \
  --project="PROJECT_ID" \
  --content-type=resource \
  --output-path="gs://EVIDENCE_BUCKET/INCIDENT_ID/assets.json" \
  --snapshot-time="2026-11-19T06:00:00Z"
~~~

Đảm bảo người thu thập có quyền đọc tài sản và ghi vào đích. Lưu lại snapshot time, project scope và loại nội dung đã xuất. Nếu cần lịch sử thay đổi, kết hợp snapshot với Cloud Audit Logs; một snapshot đơn lẻ không cho biết đầy đủ ai đã thay đổi tài nguyên.

### Compute Engine

Với VM nghi bị xâm nhập, thu thập:

- Instance metadata, zone, machine type, network interface, IP, tag và service account.
- Boot disk, attached disk, snapshot và cấu hình firewall liên quan.
- Serial port output, system log, OS Login hoặc metadata SSH khi có.
- Log từ agent bảo mật, hệ điều hành, ứng dụng và VPC Flow Logs.
- Image, startup script, metadata và lịch sử triển khai.

Ví dụ ghi lại metadata instance:

~~~bash
gcloud compute instances describe "VM_NAME" \
  --zone="ZONE" \
  --project="PROJECT_ID" \
  --format=json > instance-description.json
~~~

Có thể tạo snapshot của persistent disk để bảo toàn trạng thái đĩa tại một thời điểm:

~~~bash
gcloud compute disks snapshot "DISK_NAME" \
  --zone="ZONE" \
  --snapshot-names="INCIDENT_ID-DISK-SNAPSHOT" \
  --project="PROJECT_ID"
~~~

Snapshot trong khi VM đang chạy thường phản ánh trạng thái crash-consistent, không đảm bảo ứng dụng hoặc cơ sở dữ liệu đã flush dữ liệu theo cách nhất quán. Với database, ưu tiên backup hoặc quy trình quiesce phù hợp và ghi lại phương pháp thu thập. Không gắn trực tiếp disk gốc vào máy phân tích nếu thao tác mount có thể ghi lên disk; tạo bản sao làm việc và dùng chế độ chỉ đọc khi phù hợp.

Nếu cần dữ liệu bộ nhớ hoặc trạng thái tiến trình, snapshot disk không thay thế memory acquisition. Việc thu thập bộ nhớ trên cloud có thể bị giới hạn bởi nền tảng và cần công cụ, quyền hoặc hỗ trợ chuyên biệt. Ghi rõ giới hạn này trong báo cáo.

### Google Kubernetes Engine

Với GKE, chứng cứ quan trọng có thể biến mất khi Pod bị xóa hoặc node bị thay thế. Trước khi restart, drain hoặc redeploy, cân nhắc thu thập:

- Cluster, node pool, node, namespace, Pod, owner reference và trạng thái workload.
- Image name và digest, command/args, service account, security context.
- Deployment, StatefulSet, DaemonSet, Job, CronJob, Service, Ingress và NetworkPolicy.
- Kubernetes events, audit logs và control-plane logs.
- Node disk, container runtime logs và log ứng dụng.
- Quyền RBAC, Workload Identity mapping và cấu hình network.

Một số lệnh đọc trạng thái Kubernetes:

~~~bash
kubectl get pods -A -o wide
kubectl get events -A --sort-by=.metadata.creationTimestamp
kubectl get deployments,statefulsets,daemonsets,jobs,cronjobs -A -o yaml
kubectl get nodes -o wide
~~~

Các đầu ra YAML có thể chứa cấu hình nhạy cảm. Rà soát quyền lưu trữ và loại bỏ secret payload khỏi bản chia sẻ; bản gốc được bảo vệ theo quy trình chứng cứ. Không chạy lệnh xuất toàn bộ Kubernetes Secret chỉ để phục vụ điều tra. Nếu cần một secret cụ thể, phải có phê duyệt, ghi nhận lý do và giới hạn người tiếp cận.

Tránh xóa Pod hoặc drain node trước khi đã đánh giá nhu cầu thu thập trạng thái runtime. Khi cần cô lập, áp dụng biện pháp giới hạn mạng hoặc quyền phù hợp và ghi lại chính xác thay đổi đã thực hiện.

### Cloud Run

Đối với Cloud Run, lưu lại service, revision, traffic split, image digest, runtime service account, region, cấu hình mạng, biến môi trường và tham chiếu Secret Manager. Phân biệt giá trị cấu hình thông thường với secret reference; không đưa secret payload vào bản xuất.

Thu thập Cloud Audit Logs về thao tác deploy/update, Cloud Logging của revision, request log, log ứng dụng, thông tin Artifact Registry và provenance của image nếu có. Ghi nhận revision đang nhận traffic và revision trước đó. Một lần rollback có thể làm thay đổi traffic và trạng thái đang chạy, vì vậy cần ghi nhận cấu hình trước khi thao tác.

### Cloud SQL và cơ sở dữ liệu

Thu thập metadata instance, cấu hình network, authorized networks, private IP, IAM database authentication, tài khoản DB, backup, thời điểm PITR và log có sẵn. Kiểm tra Cloud Audit Logs, database engine logs, kết nối, truy vấn, export và hoạt động backup.

Nếu cần giữ dữ liệu, sử dụng backup hoặc clone theo quy trình được phê duyệt. Với hệ thống có giao dịch đang chạy, cân nhắc tính nhất quán và thời điểm snapshot. Không chạy truy vấn điều tra có thể làm thay đổi dữ liệu nghiệp vụ hoặc xóa dấu vết. Giữ bản backup gốc, phân tích trên bản sao và ghi rõ điểm khôi phục.

### Cloud Storage

Đối với bucket liên quan, ghi nhận bucket metadata, location, IAM policy, uniform bucket-level access, public access prevention, retention policy, object versioning và lifecycle rule. Thu thập Cloud Audit Logs Data Access nếu đã bật, cùng log truy cập từ hệ thống khác.

Không xóa object nghi vấn hoặc ghi đè object gốc. Nếu versioning được bật, bảo toàn generation liên quan. Nếu versioning chưa bật, object đã bị ghi đè hoặc xóa có thể không khôi phục được; cần ghi rõ giới hạn. Khi sao chép object sang bucket chứng cứ, giữ metadata cần thiết, generation, checksum và nguồn gốc. Bản sao không thay thế bản gốc và không chứng minh tự thân rằng dữ liệu chưa bị thay đổi trước thời điểm thu thập.

## 7. Bảo toàn tính toàn vẹn và chuỗi quản lý chứng cứ

Chứng cứ chỉ có giá trị khi có thể giải thích nguồn gốc, quá trình thu thập, ai đã tiếp cận và nội dung có bị thay đổi hay không.

### Tạo manifest và hash

Sau khi xuất một tệp chứng cứ, tính SHA-256. Trên Linux:

~~~bash
sha256sum incident-audit-logs.json
~~~

Trên Windows PowerShell:

~~~powershell
Get-FileHash .\incident-audit-logs.json -Algorithm SHA256
~~~

Ghi kết quả vào manifest riêng. Ví dụ:

| Trường | Ví dụ nội dung |
|---|---|
| Evidence ID | EV-0001 |
| File | incident-audit-logs.json |
| Nguồn | Cloud Logging, project payments-prod |
| Query/filter | Filter đầy đủ hoặc mã tham chiếu truy vấn |
| Khoảng thời gian | 2026-11-19T00:00:00Z đến 2026-11-19T06:00:00Z |
| Thời điểm thu thập | 2026-11-19T06:20:00Z |
| Người thu thập | analyst@example.com |
| SHA-256 | Hash của tệp đã thu thập |
| Lưu trữ | Bucket, object path và generation |
| Lịch sử bàn giao | Người giao, người nhận, thời điểm, mục đích |

Hash giúp phát hiện thay đổi sau khi tính hash; nó không chứng minh dữ liệu gốc là đầy đủ hoặc chính xác trước lúc thu thập. Vì vậy, cần lưu cả nguồn, cách truy vấn và bối cảnh.

### Chuỗi quản lý chứng cứ (chain of custody)

Mỗi lần chứng cứ được sao chép, chuyển giao, mở hoặc phân tích cần có bản ghi:

- Evidence ID và mô tả nội dung.
- Người thu thập, người bàn giao, người nhận và vai trò.
- Ngày giờ UTC và mục đích truy cập.
- Nơi lưu trữ, quyền truy cập và trạng thái niêm phong.
- Hash trước và sau khi chuyển giao nếu có sao chép.
- Công cụ, phiên bản công cụ và thao tác đã thực hiện.

Giữ bản gốc ở chế độ chỉ đọc hoặc cơ chế tương đương; phân tích trên bản sao. Nếu phải chuyển đổi định dạng, lọc dữ liệu hoặc giải nén, giữ nguyên bản gốc và lưu quy trình chuyển đổi.

### Kiểm soát kho lưu trữ

Kho chứng cứ cần có:

- IAM riêng, quyền đọc và ghi tách biệt, không cấp quyền xóa rộng.
- Mã hóa khi lưu trữ và truyền tải.
- Retention phù hợp, legal hold khi được yêu cầu.
- Audit log cho thao tác đọc, ghi, thay đổi IAM và xóa.
- Bản sao độc lập hoặc cơ chế bảo vệ khỏi tài khoản quản trị bị xâm nhập.
- Phân loại dữ liệu và thời hạn lưu giữ theo chính sách quyền riêng tư.

Không dùng bucket đang bị nghi ngờ xâm nhập làm kho chứng cứ duy nhất. Nếu tài khoản quản trị nguồn có thể bị chiếm quyền, hãy lưu bản sao trong project bảo mật với principal và ranh giới quản trị độc lập.

## 8. Security Command Center và điều tra phạm vi ảnh hưởng

Security Command Center (SCC) tổng hợp findings về cấu hình sai, lỗ hổng và mối đe dọa tùy theo tier, dịch vụ và cấu hình đã bật. Finding là đầu mối điều tra, không phải kết luận cuối cùng.

Khi xem một finding, ghi lại:

- Finding ID, category, severity, state và thời điểm phát hiện.
- Resource name, project, folder hoặc organization.
- Source, detector và mô tả kỹ thuật.
- Event time, create time, update time và các external URI nếu có.
- Trạng thái xử lý, người phụ trách và liên kết đến chứng cứ liên quan.

Đối chiếu finding với Cloud Audit Logs, Cloud Asset Inventory, log mạng, log ứng dụng và trạng thái tài nguyên. Một finding có thể đã được khắc phục hoặc bị đóng nhưng log lịch sử vẫn cần được bảo toàn. Không xóa finding chỉ để làm sạch dashboard trước khi đã ghi nhận dữ liệu cần thiết.

## 9. Loại bỏ nguyên nhân và khôi phục dịch vụ

Sau khi xác định phạm vi, nhóm cần loại bỏ đường xâm nhập và khôi phục từ trạng thái đáng tin cậy.

Các bước thường gồm:

1. Xác định principal, credential, workload, image hoặc cấu hình gây ra sự cố.
2. Thu hồi hoặc thay thế credential bị lộ; kiểm tra quyền impersonation và các khóa liên quan.
3. Gỡ bỏ quyền IAM không hợp lệ, tài nguyên lạ, firewall rule hoặc cơ chế truy cập trái phép.
4. Tạo lại workload từ image và artifact đã xác minh, không tái sử dụng image nghi bị cài mã độc.
5. Khôi phục dữ liệu từ backup đã kiểm tra tính toàn vẹn và thời điểm sạch.
6. Kiểm thử chức năng, quyền truy cập, luồng mạng, audit log và khả năng giám sát.
7. Mở traffic theo từng bước và theo dõi dấu hiệu tái xâm nhập.

Không chỉ đổi mật khẩu rồi đóng sự cố. Kẻ tấn công có thể đã tạo service account mới, thêm SSH key, thay đổi startup script, tạo workload ẩn hoặc thay đổi log sink. Cần kiểm tra persistence ở IAM, Compute Engine metadata, GKE RBAC, Cloud Run revision, Cloud Scheduler, Pub/Sub, Cloud Functions/Workflows, firewall, DNS và CI/CD.

Khi thu hồi service account key, lưu metadata và log trước nếu tình hình cho phép. Vô hiệu hóa key ngăn việc dùng key đó để tạo chữ ký mới, nhưng access token đã được phát hành có thể còn hiệu lực đến khi hết hạn. Cần đánh giá thêm IAM permission, session/token và các danh tính liên quan.

## 10. Ví dụ thực hành: nghi ngờ service account bị lộ khóa

Giả sử Security Command Center phát hiện một service account của project production được sử dụng từ địa chỉ IP lạ. Audit log cho thấy principal đó gọi API đọc dữ liệu và thay đổi IAM trong cùng khoảng thời gian.

Quy trình xử lý mẫu:

**Bước 1 — Mở hồ sơ và xác minh.** Ghi incident ID, thời gian UTC, project, service account email, IP, method name, resource và finding ID. Xác định quyền của service account ở project, folder và organization.

**Bước 2 — Bảo toàn dữ liệu ban đầu.** Xuất audit log trong khoảng thời gian rộng hơn sự kiện, lưu IAM policy hiện tại, danh sách key metadata, danh mục tài nguyên và trạng thái workload. Tính hash và ghi manifest.

**Bước 3 — Mở rộng phạm vi.** Tìm các thao tác tạo service account key, cấp role, impersonation, tạo VM, deploy revision, tạo bucket, thay đổi sink và truy cập dữ liệu. Kiểm tra các project khác mà principal có quyền.

**Bước 4 — Cô lập.** Nếu xác nhận key bị lộ, vô hiệu hóa key nghi vấn và thu hẹp quyền của principal. Nếu có dấu hiệu exfiltration đang diễn ra, áp dụng biện pháp chặn truy cập dữ liệu hoặc mạng phù hợp. Ghi lại thời điểm và tác động của từng hành động.

**Bước 5 — Loại bỏ persistence.** Kiểm tra key khác của service account, principal lạ được thêm vào IAM, quyền impersonation, workload mới, scheduled job và sink bất thường. Xóa hoặc vô hiệu hóa thành phần trái phép sau khi đã bảo toàn chứng cứ cần thiết và được phê duyệt.

**Bước 6 — Khôi phục và giám sát.** Tạo credential thay thế qua quy trình an toàn, cấp lại quyền tối thiểu, triển khai workload sạch và theo dõi audit log. Xác minh các consumer hợp lệ hoạt động bình thường trước khi đóng sự cố.

Kết luận không nên chỉ ghi “đã vô hiệu hóa key”. Báo cáo cần trả lời key được tạo khi nào, ai có thể truy cập, key được dùng ở đâu, dữ liệu nào có khả năng bị đọc hoặc thay đổi, quyền nào đã bị lạm dụng và còn đường truy cập nào chưa được loại bỏ.

## 11. Báo cáo sự cố và rút kinh nghiệm

Báo cáo cuối cùng cần đủ rõ để nhóm kỹ thuật, quản lý và bộ phận tuân thủ có thể hiểu cùng một diễn biến.

Một báo cáo thường có:

- Tóm tắt sự cố và mức độ ảnh hưởng.
- Phạm vi organization, folder, project, region, resource và dữ liệu.
- Dòng thời gian UTC từ dấu hiệu đầu tiên đến khi khôi phục.
- Principal, IP, API method, image digest và tài nguyên liên quan.
- Chứng cứ đã thu thập, Evidence ID, hash và vị trí lưu trữ.
- Hành động cô lập, thay đổi IAM, thu hồi credential và quyết định nghiệp vụ.
- Nguyên nhân gốc đã xác nhận và giả thuyết chưa xác nhận.
- Dữ liệu có thể đã bị truy cập, thay đổi, xóa hoặc rò rỉ.
- Trạng thái khôi phục, kiểm thử và giám sát sau khôi phục.
- Nghĩa vụ thông báo, legal hold và người phê duyệt nếu có.
- Công việc khắc phục, người chịu trách nhiệm và thời hạn.

Sau sự cố, cập nhật playbook, quyền break-glass, logging coverage, retention, cảnh báo, baseline tài nguyên và bài diễn tập. Kiểm tra lại xem có project nào không gửi log, Data Access audit logs nào chưa bật, sink nào có thể bị sửa bởi workload và tài khoản nào có quyền xóa chứng cứ.

## 12. Checklist ứng phó và bảo toàn chứng cứ

### Khi phát hiện

- [ ] Tạo incident ID và chỉ định incident commander.
- [ ] Ghi thời gian UTC, nguồn cảnh báo, project, resource và principal liên quan.
- [ ] Xác định mức độ ảnh hưởng đến dữ liệu, dịch vụ và khách hàng.
- [ ] Bảo đảm kênh điều phối và quyền truy cập khẩn cấp đáng tin cậy.

### Trước và trong khi cô lập

- [ ] Ghi nhận trạng thái IAM, mạng, workload và revision nếu có thể.
- [ ] Thu thập dữ liệu biến động cần thiết khi việc này không làm tăng thiệt hại.
- [ ] Ghi rõ hành động cô lập, người thực hiện, thời điểm và lý do.
- [ ] Tránh xóa tài nguyên, Pod, disk, revision, log hoặc credential trước khi đánh giá nhu cầu chứng cứ.

### Thu thập và bảo quản

- [ ] Xuất Cloud Audit Logs, application logs và log mạng liên quan.
- [ ] Lưu IAM policy, metadata khóa và trạng thái tài nguyên.
- [ ] Thu thập snapshot/backup phù hợp cho VM, GKE, Cloud SQL hoặc Storage.
- [ ] Tạo SHA-256 manifest cho từng tệp chứng cứ.
- [ ] Lưu bản gốc trong kho riêng, hạn chế quyền và có retention phù hợp.
- [ ] Ghi đầy đủ chain of custody và lịch sử truy cập.

### Khôi phục và đóng sự cố

- [ ] Loại bỏ persistence và thu hồi credential bị lộ.
- [ ] Khôi phục từ artifact hoặc backup đã xác minh.
- [ ] Kiểm tra IAM, mạng, dữ liệu, workload và logging sau khôi phục.
- [ ] Theo dõi dấu hiệu tái xâm nhập.
- [ ] Hoàn tất báo cáo, nghĩa vụ thông báo và các hành động phòng ngừa.

Ứng phó sự cố trên Google Cloud đòi hỏi cân bằng giữa tốc độ ngăn chặn và khả năng tái dựng sự kiện. Cloud Audit Logs, Cloud Logging, Security Command Center, Cloud Asset Inventory và snapshot tài nguyên cung cấp các mảnh chứng cứ khác nhau. Khi nhóm ghi lại mọi thay đổi, bảo vệ bản gốc, xác minh hash và duy trì chuỗi bàn giao, kết quả điều tra sẽ đáng tin cậy hơn và quá trình khôi phục có thể được kiểm soát tốt hơn.

