# Chuẩn theo môi trường (Environment-specific Security Standards)

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **chuẩn bảo mật theo môi trường** là gì; phân biệt chính sách (*policy*), chuẩn bắt buộc (*standard*), baseline, hướng dẫn và quy trình vận hành.
- Xây dựng mô hình **baseline chung + yêu cầu bổ sung theo rủi ro** cho development, test, staging, production, disaster recovery (DR) và môi trường tạm thời.
- Xác định những control phải giữ nguyên ở mọi môi trường, những control được điều chỉnh có lý do và những trường hợp không được hạ chuẩn chỉ vì tên môi trường là `dev` hoặc `test`.
- Chuyển yêu cầu thành **tiêu chí kiểm chứng**, kiểm tra được cấu hình, danh tính, mạng, dữ liệu, secret, logging, kiểm thử, backup và luồng triển khai thực tế.
- Xây dựng **chuỗi bằng chứng security assurance** từ phân tích rủi ro, security controls, kết quả kiểm thử đến đánh giá độc lập, audit, finding, khắc phục và retest.
- Quản lý ngoại lệ, thay đổi và drift để các chuẩn tiếp tục được đáp ứng khi ứng dụng và hạ tầng vận hành.

## 1. Vì sao cần chuẩn bảo mật theo môi trường?

Một hệ thống có thể tồn tại đồng thời trên laptop của Developer, môi trường tích hợp, staging, production và một khu vực dự phòng. Các môi trường khác nhau về dữ liệu, người dùng, quyền truy cập, độ phơi lộ mạng, khả năng ảnh hưởng đến dịch vụ thật và yêu cầu phục hồi. Dùng **một bản cấu hình bất biến cho mọi tình huống** có thể không phù hợp; nhưng coi môi trường thử nghiệm là nơi được tùy ý bỏ qua control cũng nguy hiểm.

**Chuẩn bảo mật theo môi trường** là tập các yêu cầu kỹ thuật và vận hành **bắt buộc trong phạm vi xác định**, dựa trên mục tiêu bảo mật, phân loại dữ liệu, độ nhạy cảm của tài sản và mức độ rủi ro của môi trường đó. Ví dụ, production thường cần quản lý thay đổi, bảo vệ dữ liệu khách hàng, giám sát và khôi phục chặt chẽ. Một môi trường development có thể sử dụng dữ liệu giả và giới hạn external ingress, nhưng vẫn phải bảo vệ secret, tài khoản quản trị, code và token CI vì đây có thể là **đường vào production**.

Trong module **SECURITY_SECURITY_ASSURANCE**, mục tiêu không chỉ là viết chuẩn mà còn xây dựng **cơ sở có bằng chứng** rằng các security controls được áp dụng và đạt yêu cầu trong từng môi trường, ở đúng phiên bản và thời điểm. Điều này nối việc phân tích rủi ro với yêu cầu, kiểm thử, audit, khắc phục phát hiện và security assurance liên tục trong phát triển lẫn vận hành.

### Thuật ngữ cần phân biệt

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Security policy** | Định hướng, nguyên tắc và yêu cầu quản trị cấp tổ chức | Dữ liệu nhạy cảm phải được bảo vệ ở mọi nơi lưu và truyền |
| **Security standard** | Điều kiện bắt buộc, đo/kiểm được cho đối tượng trong phạm vi | Workload production không được công bố database trực tiếp ra Internet |
| **Security baseline** | Bộ yêu cầu mặc định tối thiểu để bắt đầu triển khai/đánh giá | Tắt debug, quản lý secret, áp dụng quyền tối thiểu |
| **Environment profile / overlay** | Yêu cầu bổ sung, tăng cường hoặc điều chỉnh đã được phê duyệt cho một loại môi trường | Production cần giám sát cảnh báo và bằng chứng restore drill |
| **Guideline** | Khuyến nghị hoặc cách lựa chọn có thể linh hoạt | Gợi ý công cụ scan/configuration-as-code |
| **Procedure / runbook** | Các bước thao tác để thực hiện chuẩn và xử lý ngoại lệ | Quy trình rotate secret hoặc rollback |
| **Control implementation** | Cách công nghệ/quy trình thực thi yêu cầu | IAM role, Kubernetes policy, CI security gate |
| **Control evidence** | Hiện vật cho thấy control đã được cấu hình, thực thi và đánh giá | Config snapshot, log, test report, deployment digest |

**Chuẩn không đồng nghĩa một bộ checkboxes.** Nếu chuẩn viết “MFA cho tài khoản quản trị”, cần phân biệt bằng chứng về **quy định**, **cấu hình thật**, **tài khoản được bao phủ**, **kết quả kiểm thử** và **ngoại lệ còn mở**. Một bản ghi “compliant” trong bảng không thay thế những bằng chứng này.

## 2. Mô hình phân loại môi trường theo rủi ro

Các tên `dev`, `qa`, `uat`, `stage`, `preprod`, `prod`, `dr` chỉ là **nhãn quy ước**. Không phải mọi tổ chức phân tầng như nhau; cần gắn thông tin thực tế cho từng instance.

| Môi trường | Mục đích chính | Rủi ro thường cần chú ý | Bằng chứng đặc thù |
| --- | --- | --- | --- |
| **Local development** | Phát triển, gỡ lỗi, chạy test nhanh | Secret bị commit/lưu trên máy cá nhân, quyền cloud quá rộng, dữ liệu thật sao chép ra ngoài | Quyền truy cập dev, secret scanning, quy định dữ liệu test, cấu hình endpoint |
| **Shared development / integration** | Tích hợp nhiều dịch vụ và developer | Tài khoản dùng chung, mối tin cậy giữa dịch vụ, cấu hình thử vô tình công khai | Inventory service, IAM, ingress và test authorization |
| **QA / automated test** | Kiểm thử chức năng, hồi quy, bảo mật | Fixture không an toàn, lộ dữ liệu thật, test permission không phản ánh production | Test run, data classification, cleanup và security test coverage |
| **Staging / preproduction** | Kiểm chứng release và hạ tầng gần với production | Dùng dữ liệu/snapshot thật, route ngoài ý muốn, quyền deploy quá rộng, cấu hình khác production | So sánh config, approval, artifact digest, runtime tests |
| **Production** | Cung cấp dịch vụ và xử lý dữ liệu/khách hàng thật | Truy cập trái phép, gián đoạn, sai quyền, gian lận, lộ dữ liệu, thiếu phát hiện | Cấu hình thực, change/audit log, scanning, monitoring và recovery test |
| **DR / standby** | Phục hồi khi production bị gián đoạn | Bản sao dữ liệu thật ít được theo dõi, credential tồn đọng, failover không an toàn | Quyền truy cập, đồng bộ cấu hình, restore/failover drill, RPO/RTO |
| **Ephemeral / preview** | Môi trường tạm theo PR hoặc nhánh | Public URL, tài khoản tồn tại sau khi hết nhu cầu, secret, dữ liệu sót | TTL của môi trường, network restriction, cleanup và owner |

**Nguyên tắc then chốt: phân loại theo mức rủi ro cao nhất của dữ liệu, quyền và kết nối đang có, không chỉ theo nhãn.**

Ví dụ: staging dùng dữ liệu khách hàng thật, kết nối hệ thống thanh toán thật hoặc có token triển khai production cần các biện pháp tương xứng với khả năng tác động của nó. Không được tự suy luận “staging nên được miễn yêu cầu bảo vệ dữ liệu” chỉ vì mục đích thử nghiệm.

### Hồ sơ môi trường tối thiểu

Mỗi môi trường nên có một record xác minh được:

- `environment_id`, tên, trạng thái, môi trường cha hoặc cụm dịch vụ liên quan.
- Owner kỹ thuật, data owner, risk owner, người phê duyệt thay đổi.
- Tài sản, data classification, có/không có dữ liệu thật, mức nhạy cảm.
- Kết nối ingress/egress, mạng, IAM trust, quyền service account và liên kết với production.
- Baseline version, overlay version, ngoại lệ, ngày review, phạm vi giám sát.
- Artifact/deployment ID đang chạy, nơi lưu evidence và tiêu chí decommission.

Mục tiêu là phân loại được **trường hợp thực tế** thay vì đặt tên thư mục rồi coi môi trường đã được bảo vệ.

## 3. Thiết kế chuẩn theo phương pháp baseline chung + overlay

Một mô hình dễ quản trị là:

\[
\text{Yêu cầu hiệu lực}(e)=
\text{Baseline chung}
+\text{Overlay môi trường}(e)
+\text{Điều kiện rủi ro, dữ liệu, kết nối}(e)
\]

Dấu “+” ở đây mang nghĩa **tổng hợp quy tắc**, không phải phép cộng điểm số. Khi hai quy tắc xung đột, phải có thứ tự ưu tiên, trách nhiệm xử lý và hồ sơ phê duyệt; không mặc định overlay được xóa bỏ baseline.

~~~mermaid
flowchart TD
    P["Chính sách bảo mật của tổ chức"] --> B["Baseline bắt buộc chung"]
    R["Tài sản, dữ liệu, threat model và rủi ro"] --> O["Overlay theo môi trường và ngữ cảnh"]
    B --> E["Bộ yêu cầu hiệu lực cho environment ID"]
    O --> E
    E --> I["Triển khai IaC, ứng dụng, IAM, quy trình"]
    I --> T["Test và đối chiếu trạng thái runtime"]
    T --> V{"Có đủ bằng chứng đạt control?"}
    V -- "Có" --> A["Đánh giá, lưu evidence và review định kỳ"]
    V -- "Không" --> F["Finding / ngoại lệ / remediation"]
    F --> I
~~~

### Những control không nên bị “tắt vì là non-prod”

Trong nhiều tổ chức, các nguyên tắc sau là **mức tối thiểu chung**, điều chỉnh chi tiết theo rủi ro:

1. Không chứa secret, private key hoặc token thật trong source, artifact và log không được bảo vệ.
2. Xác thực và ủy quyền cho các chức năng cần bảo vệ; không coi “mạng nội bộ” là lý do tin tưởng tuyệt đối.
3. Quyền IAM/workload theo nhu cầu thực; cô lập môi trường và đường truy cập ngoài nhiệm vụ.
4. Không vô cớ sao chép dữ liệu nhạy cảm từ production sang test; bảo vệ dữ liệu thật nếu sử dụng có căn cứ.
5. Quản lý thay đổi và truy vết hành động quản trị ở mức phù hợp; không cho phép tài khoản dùng chung phá khả năng truy vết.
6. Quét/đánh giá lỗ hổng theo quy tắc đã duyệt cho source, dependency và các thành phần hạ tầng liên quan.
7. Có owner, inventory, thời hạn và cách xử lý sự cố hoặc finding cho tài sản đang hoạt động.
8. Quản lý quyền truy cập và môi trường tạm trong toàn vòng đời, kể cả khi ngừng sử dụng.

Việc giảm log, bỏ backup hoặc nới một control có thể phù hợp trong **một trường hợp đã chứng minh rủi ro thấp và không có yêu cầu bắt buộc trái ngược**; nhưng phải ghi rõ phạm vi, lý do và người phê duyệt. Không dùng một bảng “prod nghiêm, dev thoáng” làm quy tắc tuyệt đối.

### Ví dụ overlay theo môi trường

| Control | Baseline chung | Non-prod có dữ liệu giả, cô lập | Staging có dữ liệu thật | Production / DR |
| --- | --- | --- | --- | --- |
| **Identity / IAM** | Danh tính riêng, least privilege, thu hồi khi không còn dùng | Scope riêng, role dev/test, không có quyền production | Scope và kiểm soát truy cập tương xứng dữ liệu thật | Kiểm soát đặc quyền, review và audit đầy đủ theo chính sách |
| **Data protection** | Phân loại, bảo vệ truyền/lưu và giới hạn bản sao theo rủi ro | Dữ liệu tổng hợp/giả ưu tiên | Không dùng dữ liệu thật nếu không cần; nếu có cần kiểm soát tương xứng | Bảo vệ dữ liệu thật, key/secret và retention đã phê duyệt |
| **Network** | Chỉ mở kết nối cần thiết, quản trị được ingress/egress | Giới hạn truy cập giữa nhóm dự án | Không công bố ngoài ý muốn; tương đương ranh giới sản xuất nơi cần | Segmentation, network/IAM control đã kiểm chứng |
| **Audit & monitoring** | Ghi hoạt động bảo mật thiết yếu, không log secret | Giữ đủ để phát hiện và điều tra trong phạm vi | Bao phủ tương xứng dữ liệu thật và kiểm thử release | Theo dõi tập trung, cảnh báo, kiểm chứng pipeline và retention |
| **Change & release** | Mã/config có version, review theo risk | Cho phép triển khai nhanh nhưng vẫn truy vết | Kiểm soát version và giống production ở điểm thiết yếu | Phê duyệt và xác minh theo quy trình thay đổi |
| **Backup/restore** | Xác định nhu cầu theo giá trị dữ liệu và hoạt động | Có thể tái tạo từ code/fixture khi chấp nhận được | Khôi phục các trạng thái/data quan trọng theo chính sách | Backup/restore/failover với RTO/RPO đã thống nhất |
| **Security tests** | Test phù hợp rủi ro, có negative tests | Unit/integration và scan liên tục | End-to-end và rehearsal trên cấu hình gần thực | Xác minh runtime có kiểm soát, monitoring và retest findings |
| **Lifecycle** | Owner, retention, decommission | Tự xóa tài nguyên khi hết nhu cầu | Xử lý data snapshot/credentials sau rehearsal | Quy tắc lưu giữ, khôi phục và thu hồi quyền rõ ràng |

Đây là **ma trận minh họa**, không phải tiêu chuẩn bắt buộc chung cho mọi ngành. Bảng yêu cầu chính thức phải nêu **control ID, điều kiện, bằng chứng, mức ưu tiên, phạm vi và owner**.

## 4. Xác định yêu cầu theo tài sản và kết nối, không chỉ tên môi trường

Một hồ sơ môi trường cần xem ít nhất năm góc độ.

### 4.1. Mức nhạy cảm và nguồn gốc dữ liệu

- Test dùng dữ liệu tổng hợp hay dữ liệu lấy từ production?
- Có dữ liệu định danh, giao dịch, tài chính, sức khỏe hoặc dữ liệu mật không?
- Dữ liệu đã được **ẩn danh thực sự** hay chỉ thay mã định danh còn khả năng tái liên kết?
- Có bản sao ở log, cache, message queue, object storage, backup, search và hệ thống bên thứ ba?
- Ai có quyền trích xuất, sao chép, xóa và kiểm chứng retention của từng bản?

Việc che tên/cột hiển thị không mặc nhiên bảo đảm dữ liệu đã ẩn danh. Nếu dùng dữ liệu thật, cần xác định căn cứ, phạm vi, biện pháp bảo vệ, quyền truy cập và vòng đời theo chính sách áp dụng.

### 4.2. Quyền có thể tác động tới production

Một runner ở non-prod có thể có quyền ghi image registry dùng chung, sửa Kubernetes deployment hoặc truy cập khóa ký artifact. Khi đó **rủi ro của đường đặc quyền** gần với production, dù runner đang chạy trong một namespace tên `test`.

Cần lập sơ đồ:

- Repository/CI runner → artifact registry → production deployment.
- Service account ở staging → cloud account/bucket production.
- Admin IAM → môi trường khác thông qua role delegation.
- Secret manager, DNS, webhook, mạng và hệ thống quản lý chung.

### 4.3. Mức phơi lộ mạng

Kiểm tra thực tế các đường vào và ra: public endpoint, VPN, private ingress, service mesh, gRPC, queue consumer, webhook và outbound Internet. Một ingress private không đủ nếu mọi máy trong mạng công ty có thể truy cập bằng credential chia sẻ.

### 4.4. Mức quan trọng và tính sẵn sàng

Production không phải môi trường duy nhất đòi hỏi khôi phục. Một môi trường tích hợp trọng yếu chặn toàn bộ pipeline phát hành có thể cần backup, cấu hình có thể tái tạo, kế hoạch khôi phục và owner phù hợp. Với DR, chính **khả năng dùng được lúc xảy ra sự cố** là yêu cầu trọng tâm.

### 4.5. Nghĩa vụ và phụ thuộc khác

Tổ chức có thể có yêu cầu hợp đồng, phân vùng khu vực, phân loại hệ thống, tiêu chuẩn ngành hoặc quy tắc kiểm soát thay đổi áp dụng với từng dữ liệu/tài sản. Một chuẩn theo môi trường **không được tự tạo ngoại lệ cho nghĩa vụ bắt buộc** chỉ vì muốn triển khai nhanh.

## 5. Các security controls cần có tiêu chí đo được

### 5.1. Identity, tài khoản đặc quyền và bí mật

Một yêu cầu mơ hồ: “Tài khoản production phải an toàn.”

Một yêu cầu đánh giá được:

> **ENV-IAM-01:** Mỗi workload trên production sử dụng identity riêng, chỉ có quyền tới tài nguyên phục vụ nghiệp vụ; mọi quyền đọc bucket ngoài phạm vi phải bị từ chối trong phép kiểm tra đã phê duyệt.

Bằng chứng có thể gồm IAM policy **thực tế**, quyền hiệu lực, identity của deployment đang chạy, positive/negative access tests, hồ sơ cấp/thu hồi và người review. Chỉ đọc Terraform source chưa chứng minh quyền đã áp dụng.

Với người vận hành, cần làm rõ **quyền truy cập đặc biệt, xác thực mạnh, break-glass, thời hạn cấp quyền, log thao tác, separation of duties và review**. Cùng một nguyên tắc có thể áp dụng cho staging nếu môi trường đó có đường quản trị production.

### 5.2. Network, ingress và egress

Yêu cầu minh họa:

> **ENV-NET-01:** Database production không có listener trực tiếp phục vụ Internet; chỉ các danh tính/workload và luồng kết nối được phê duyệt có quyền truy cập.

Kiểm tra cần từ **điểm nhìn phù hợp**: route/cloud firewall, ingress/listener, network policy và thử kết nối được phép/không được phép với tài khoản kiểm thử. Không được suy từ việc “port scan từ một IP không thấy cổng” rằng mọi con đường đều bị chặn.

Ở preview environment, cần đặt giới hạn public URL, tài khoản quản trị, egress tới service thật và **thời điểm hủy tài nguyên**.

### 5.3. Application hardening

Yêu cầu có thể gồm giới hạn management endpoints, thông báo lỗi không lộ stack trace, xác thực token theo issuer/audience, ủy quyền cấp đối tượng, kiểm tra đầu vào, chống injection và cấu hình TLS phù hợp.

Một ứng dụng Spring Boot dùng profile `dev` không nên tự động tắt toàn bộ authorization. Các profile có thể thay đổi **mức logging, stub tích hợp hay cấu hình tài nguyên**, nhưng không nên phá vỡ giả định bảo mật cốt lõi được kiểm thử để rồi production là lần đầu logic quyền được bật.

### 5.4. Logging, detection và evidence retention

- Xác định **event bắt buộc**: thao tác quản trị, thay đổi quyền, thay đổi cấu hình, từ chối truy cập, truy xuất dữ liệu đặc biệt, sự kiện backup/restore.
- Kiểm soát **nội dung log** để không ghi password, secret, private key hoặc payload cá nhân không cần thiết.
- Bảo đảm **đường vận chuyển**: event nguồn → collector → storage → detection rule → alert owner.
- Định nghĩa retention của từng nhóm log theo chính sách được duyệt; không mặc định cùng một số ngày cho mọi môi trường.
- Theo dõi sự cố pipeline, độ trễ, mất nguồn log và quyền sửa/xóa.

Một agent hiển thị “Running” chưa chứng minh event đã tới collector. Cần phép test end-to-end và kiểm tra đúng **môi trường, event type và khoảng thời gian**.

### 5.5. Backup, recovery và DR

Nếu môi trường chứa dữ liệu không thể tái tạo hoặc phục vụ hoạt động trọng yếu, cần mục tiêu khôi phục được phê duyệt, phương thức backup, kiểm soát quyền, retention và **restore test**. Hai khái niệm:

- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa có thể mất, biểu diễn bằng khoảng thời gian mục tiêu.
- **RTO (Recovery Time Objective):** thời gian mục tiêu để khôi phục dịch vụ/chức năng được chỉ định.

DR phải có bằng chứng về **khả năng failover, tính toàn vẹn bản sao, kết nối, quyền truy cập, giám sát và đường failback**. “Replica xanh” không đủ chứng minh cả hệ thống DR hoạt động an toàn.

## 6. Cấu trúc một environment security standard có thể quản trị

Một hồ sơ chuẩn cần được version và tham chiếu từ tài sản môi trường, tránh quy định rải rác trong tài liệu không có owner.

### Bản mẫu yêu cầu chuẩn (minh họa, không phải cấu hình chạy)

~~~yaml
standard_id: SEC-ENV-001
version: 1
module: SECURITY_SECURITY_ASSURANCE
title: "Security baseline theo môi trường"
status: approved
owner: "<SECURITY_GOVERNANCE_OWNER>"
approved_by: "<AUTHORIZED_APPROVER>"
effective_at: "<ISO_8601_UTC>"
scope:
  environment_types: [development, qa, staging, production, dr]
  covered_assets: "<SERVICE_AND_PLATFORM_INVENTORY>"
  data_classes: "<CLASSIFICATION_CATALOG>"
baseline_controls:
  - control_id: ENV-BASE-01
    requirement: "Tài khoản và workload có quyền theo phạm vi cần thiết"
    evidence: ["<IAM_EFFECTIVE_POLICY>", "<NEGATIVE_ACCESS_TEST>"]
  - control_id: ENV-BASE-02
    requirement: "Bí mật không được lưu trong source hoặc log không được bảo vệ"
    evidence: ["<SECRET_SCAN>", "<CONFIG_AND_LOG_REVIEW>"]
  - control_id: ENV-BASE-03
    requirement: "Các điểm truy cập được quản lý và có owner"
    evidence: ["<INGRESS_INVENTORY>", "<RUNTIME_VALIDATION>"]
overlays:
  production:
    - control_id: ENV-PROD-01
      requirement: "Thay đổi production có approval và runtime verification"
      evidence: ["<CHANGE_ID>", "<DEPLOYMENT_ID>", "<RETEST>"]
    - control_id: ENV-PROD-02
      requirement: "Log sự kiện quản trị được kiểm tra end-to-end"
      evidence: ["<TEST_EVENT>", "<COLLECTOR_RECORD>", "<ALERT_TEST>"]
  dr:
    - control_id: ENV-DR-01
      requirement: "DR được kiểm tra khôi phục/failover theo mục tiêu đã duyệt"
      evidence: ["<DR_DRILL_REPORT>", "<RTO_RPO_RESULTS>"]
conditional_rules:
  - when: "Non-production environment contains real sensitive data"
    enforce: "Data controls equivalent to the approved sensitive-data baseline"
  - when: "Environment can deploy or administer production"
    enforce: "Production-path privileged access controls"
exception_policy:
  approval_ref: "<EXCEPTION_PROCEDURE>"
  maximum_validity: "<APPROVED_REVIEW_RULE>"
review_triggers:
  - "New environment or data classification change"
  - "IAM, ingress, CI/CD or trust-boundary change"
  - "Incident, critical finding or failed control validation"
~~~

Các field trong dấu `<...>` là placeholder. `status: approved` chỉ minh họa trạng thái tài liệu chuẩn, **không có nghĩa** hệ thống đã đạt control. Cần phân biệt phiên bản tài liệu chuẩn với **control implementation** và **bằng chứng đánh giá hiệu lực**.

### Ma trận control cần có chủ sở hữu

| Control ID | Đối tượng | Ai triển khai | Ai xác nhận/đánh giá | Kết luận cần chứng minh |
| --- | --- | --- | --- | --- |
| ENV-DATA-01 | Dữ liệu non-prod | Service Team + Data Owner | Security/Privacy theo cơ chế | Không có dữ liệu thật trái chính sách hoặc đã bảo vệ tương xứng |
| ENV-IAM-01 | Workload identity | Platform/Ops + Developer | IAM/Security reviewer | Quyền hiệu lực khớp nguyên tắc tối thiểu |
| ENV-NET-01 | Network/ingress | Ops/Platform | Security + owner | Luồng không được phép thực sự bị chặn |
| ENV-APP-01 | API và Spring Security | Developer | Tech Lead/AppSec | Truy cập trái quyền bị từ chối theo resource/action |
| ENV-CICD-01 | Pipeline và artifact | Dev/Platform | Security reviewer | Artifact triển khai được truy ra commit/build đã kiểm tra |
| ENV-DR-01 | DR và khôi phục | Ops/SRE | Service/Risk Owner | Đạt mục tiêu RTO/RPO trong bài tập có phạm vi |

Không phải mọi trường hợp phải có reviewer độc lập, nhưng với **rủi ro trọng yếu**, mô hình tổ chức cần xác định khi nào phải phân tách người triển khai và người xác nhận.

## 7. Từ chuẩn đến configuration-as-code và security tests

Một tiêu chuẩn được duyệt có thể được cụ thể hóa bằng IaC policy, admission policy, CI pipeline test, configuration scanner, công cụ kiểm tra IAM và kiểm thử ứng dụng. Cần giữ **liên kết phiên bản** giữa tài liệu chuẩn, mã rule và trạng thái môi trường.

~~~mermaid
flowchart LR
    A["Security standard + overlay"] --> B["Control IDs và tiêu chí nghiệm thu"]
    B --> C["IaC / Spring / IAM / CI policies"]
    C --> D["Static checks + tests"]
    D --> E["Artifact đã kiểm tra"]
    E --> F["Triển khai đúng environment"]
    F --> G["Runtime checks + logs"]
    G --> H["Evidence / audit / findings"]
    H --> B
~~~

**Không phải mọi yêu cầu có thể tự động hóa.** Việc xác nhận chủ sở hữu rủi ro, mức nhạy cảm dữ liệu, ràng buộc pháp lý hoặc chấp nhận ngoại lệ có thể cần review con người. Tự động hóa nên giúp tìm sai lệch và thu evidence, không tự thay người có thẩm quyền ra quyết định rủi ro.

### Ví dụ: Spring Boot profile không được hạ thấp baseline

Định nghĩa các mặc định an toàn trong `application.yml`:

~~~yaml
# application.yml - các mặc định chung cho mọi profile
server:
  error:
    include-message: never
    include-stacktrace: never

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: never
~~~

Trong `application-prod.yml` có thể bổ sung cấu hình production dành riêng cho ứng dụng, nhưng **không dựa vào profile để bật authorization lần đầu**. Phần kiểm tra quyền nên nằm trong SecurityFilterChain và tầng service theo yêu cầu nghiệp vụ, được kiểm thử ở cả non-prod và production-equivalent test.

Ví dụ kiểm tra profile sản xuất bằng một test có điều kiện:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("prod")
class ProductionProfileBaselineTest {
    @Autowired Environment environment;

    @Test
    void healthDetailsMustNotBePublic() {
        assertEquals("never",
            environment.getProperty("management.endpoint.health.show-details"));
    }

    @Test
    void stacktraceMustNotAppearInErrorResponses() {
        assertEquals("never",
            environment.getProperty("server.error.include-stacktrace"));
    }
}
~~~

Đây là **ví dụ Java với Spring Boot và JUnit** để kiểm tra một phần cấu hình đã resolve khi khởi động test context. Nó không chứng minh ingress production đang khóa cổng quản trị, không chứng minh mọi profile/instance đã cấu hình đúng, cũng không thay thế bài test HTTP quan sát phản hồi thật. Với một dự án cụ thể, `@SpringBootTest` cần đủ các dependency/configurations để ứng dụng khởi động.

**Lưu ý:** một profile tên `prod` không tạo ra ranh giới bảo mật. Profile có thể bị đặt sai, bị override bằng environment variable hoặc cấu hình bên ngoài; cần đối chiếu effective configuration **tại nơi đang chạy**.

### Những phép thử đáng có

| Test ID | Đối tượng | Phương pháp | Kết quả mong đợi |
| --- | --- | --- | --- |
| ENV-T01 | Ingress production | Đối chiếu actual routes và thử từ điểm mạng được cấp phép | Chỉ public routes được phê duyệt khả dụng |
| ENV-T02 | IAM staging | Dùng workload test và truy cập tài nguyên ngoài scope | Bị từ chối; không có quyền production ngoài quy định |
| ENV-T03 | Dữ liệu QA | Quét inventory/fixture và rà soát nguồn import | Không có dữ liệu thật trái phép; dữ liệu thử theo chính sách |
| ENV-T04 | API authorization | Thử role, tenant, resource và đường export | Request trái quyền không lấy được dữ liệu |
| ENV-T05 | Artifact promotion | So commit, build artifact digest và image đang chạy | Cùng artifact/nguồn đã kiểm tra theo chính sách |
| ENV-T06 | Logging production | Tạo event quản trị thử → collector → alert | Event đến đủ và có người nhận cảnh báo theo ngưỡng |
| ENV-T07 | DR | Restore/failover rehearsal với dữ liệu thử | Đạt điều kiện RTO/RPO và xác minh toàn vẹn |
| ENV-T08 | Preview cleanup | Kiểm tra môi trường hết hạn và tài nguyên liên quan | Không còn route/secret/permission ngoài vòng đời được duyệt |
| ENV-T09 | Configuration drift | Tạo sai lệch an toàn có kiểm soát hoặc mô phỏng | Có finding/alert và quy trình xử lý được kích hoạt |

Mỗi phép thử phải có **scope, actor, thời điểm, build/config revision, phương pháp, expected/actual và người review**. Test đạt ở staging không chứng minh production đạt nếu phiên bản hoặc control khác biệt.

## 8. Tách biệt môi trường và tính tương đương cần thiết

Có hai mục tiêu tưởng mâu thuẫn:

- **Isolation:** không để một lỗi, danh tính hoặc hoạt động test vô tình tác động tới production.
- **Parity:** staging/test phải đủ giống production ở những đặc tính liên quan để kết quả kiểm thử dự báo đúng hành vi production.

Thiết kế phù hợp là **cách ly dữ liệu, danh tính, quyền và vùng gây lỗi**, nhưng giữ sự tương đương ở những control cần kiểm chứng: code, cấu hình authorization, API routes, container image, network topology quan trọng và phương thức phát hành.

### Mô hình tốt cho promotion

1. Developer thay code và cập nhật requirement/test.
2. Pipeline tạo artifact có danh tính, chạy security tests, SAST/SCA/config checks theo policy.
3. Build được đưa vào môi trường integration/staging với **identity, dữ liệu và secret riêng**.
4. Staging kiểm tra security behavior và cấu hình có liên quan tới production.
5. Theo quy trình, artifact **đã kiểm chứng** được promote (không thay đổi nội dung ngoài dự kiến), kèm approval và change record.
6. Ops/SRE xác minh image digest, effective config và identity đang chạy ở production.
7. Security/owner review evidence liên kết với claim; drift hoặc finding tạo trigger đánh giá lại.

Không bắt buộc mọi công ty dùng cơ chế promote artifact giống nhau; điều cốt lõi là **truy vết nguồn của bản đã kiểm tra và bản thực chạy**. Rebuild không kiểm soát có thể kéo dependency mới hoặc cấu hình build khác, làm giá trị của bằng chứng staging giảm.

### Những anti-pattern điển hình

| Anti-pattern | Rủi ro | Cách khắc phục |
| --- | --- | --- |
| Staging và production dùng chung secret | Lộ non-prod thành quyền prod | Tách secret/identity, giới hạn scope và rotation |
| Staging có dữ liệu thật nhưng không có bảo vệ tương xứng | Lộ dữ liệu qua nhóm test/vendor | Masking hoặc dữ liệu giả; nếu phải giữ thật thì tăng baseline |
| CI runner test có quyền deploy production không kiểm soát | Đường leo thang từ code/test lên production | Phân tách quyền, approval, short-lived credentials |
| Production được build lại từ branch khác | Test không còn đại diện release | Bảo đảm provenance và đối chiếu digest |
| Feature flag khiến auth chỉ bật ở prod | Test non-prod không tìm ra lỗi logic quyền | Kiểm thử cấu hình tương đương cho security behavior |
| Chia sẻ database giữa các môi trường | Test có thể sửa dữ liệu thật; vượt ranh giới | Cô lập dữ liệu và quyền, hạn chế external connections |
| DR sao chép dữ liệu thật nhưng ít giám sát | Điểm yếu tồn tại ở nơi dự phòng | Áp dụng bảo vệ dữ liệu và thử kiểm soát định kỳ |

## 9. Evidence: chứng minh chuẩn được đáp ứng ở đúng môi trường

Một kết luận assurance cần xuất phát từ **claim đủ cụ thể**. Ví dụ:

> **CLAIM-ENV-01:** Đối với `report-service` production ở bản triển khai `D-123`, workload không thể đọc object storage ngoài bucket được cấp phép; đường truy cập ngoài phạm vi đã bị từ chối theo bài kiểm tra ngày được ghi nhận.

Để kiểm tra, người đánh giá cần liên kết:

| Mắt xích | Ví dụ |
| --- | --- |
| **Risk** | RISK-ENV-01: quyền cloud quá rộng làm lộ dữ liệu ngoài phạm vi |
| **Objective** | OBJ-CONF-01: giới hạn truy cập dữ liệu theo danh tính và mục đích |
| **Requirement** | REQ-ENV-01: workload production chỉ truy cập đúng bucket được phê duyệt |
| **Control** | CTRL-IAM-01: policy và identity theo service, quyền tối thiểu |
| **Test** | TEST-IAM-01: positive test bucket được phép và negative test bucket khác |
| **Evidence** | EV-IAM-01: policy runtime, test result, deployment ID, reviewer |
| **Finding** | FIND-IAM-01: role cũ còn quyền đọc bucket khác, nếu có |
| **Remediation** | Thu hẹp policy, triển khai, retest và đánh giá residual risk |

Nếu chỉ có Terraform diff dự định giới hạn quyền nhưng production còn giữ role cũ thì **chưa đủ để khẳng định claim đạt**. Đặc biệt, security assurance cần phân biệt ba cấp bằng chứng:

1. **Design evidence:** tiêu chuẩn, thiết kế, rule và PR.
2. **Implementation/test evidence:** code/config revision, security test report, pipeline result.
3. **Operational evidence:** effective permissions, runtime snapshot, logs, alert test, deployment proof và restore test.

### Hồ sơ đánh giá mẫu

Các giá trị trong dấu `<...>` chỉ là placeholder, **không phải kết quả audit thật**:

~~~yaml
assessment_id: ENV-ASSURANCE-001
standard_id: SEC-ENV-001
standard_version: 1
environment_id: "<ENVIRONMENT_ID>"
environment_type: production
service_id: report-service
asset_scope: "<ACCOUNT_CLUSTER_NAMESPACE_AND_RESOURCES>"
data_classification: "<CLASSIFICATION>"
claim_id: CLAIM-ENV-01
risk_id: RISK-ENV-01
requirement_id: REQ-ENV-01
control_id: CTRL-IAM-01
test_id: TEST-IAM-01
build_commit: "<GIT_COMMIT>"
artifact_digest: "<ARTIFACT_DIGEST>"
deployment_id: "<DEPLOYMENT_ID>"
policy_snapshot: "<ACTUAL_IAM_POLICY_REFERENCE>"
test_run: "<POSITIVE_NEGATIVE_TEST_REPORT>"
observed_at: "<ISO_8601_UTC>"
result: "<PASS_FAIL_INCONCLUSIVE>"
reviewer: "<AUTHORIZED_ASSESSOR>"
limitations: "<UNTESTED_ACCOUNTS_PATHS_OR_PERIODS>"
finding_refs: ["<FINDING_ID_IF_ANY>"]
exception_ref: "<APPROVED_EXCEPTION_IF_APPLICABLE>"
reassessment_trigger: "<CHANGE_OR_REVIEW_DATE>"
~~~

YAML trên là **chỉ mục bằng chứng**, không tự xác minh hệ thống. Hiện vật gốc phải truy xuất được với quyền phù hợp, có nguồn, thời gian, phương pháp, môi trường, phiên bản, kết quả và những giới hạn. Bằng chứng cần được bảo vệ khỏi sửa/xóa trái phép và quản lý retention theo chính sách.

### “Compliance” có ba trạng thái quan trọng

| Trạng thái | Ý nghĩa | Quy tắc báo cáo |
| --- | --- | --- |
| **PASS** | Có bằng chứng đủ rằng yêu cầu đã đạt trong phạm vi xác định | Nêu scope, môi trường, phiên bản, thời gian và kiểm tra |
| **FAIL** | Quan sát chỉ ra control không đáp ứng yêu cầu | Ghi finding, owner, mức rủi ro, sửa và retest |
| **INCONCLUSIVE** | Không đủ chứng cứ hoặc phạm vi thử chưa bao phủ claim | Không biến thiếu chứng cứ thành PASS; lên kế hoạch kiểm chứng |

Ngoài ba trạng thái này, tổ chức có thể dùng `NOT_APPLICABLE` theo tiêu chí rõ: chẳng hạn một control dành riêng cho thiết bị di động không có trong asset scope. Cần người duyệt lý do loại trừ. **“Chưa thử” không tự động là “không áp dụng”.**

## 10. Ngoại lệ, baseline deviation và thẩm quyền quyết định

Không phải mọi môi trường có thể đáp ứng ngay toàn bộ yêu cầu. Cần quy trình ngoại lệ đủ rõ:

- Control ID và **yêu cầu đang không đạt**; mô tả sai lệch được quan sát.
- Environment ID, hệ thống, dữ liệu, tài nguyên, người dùng bị ảnh hưởng.
- Lý do kỹ thuật/nghiệp vụ và rủi ro còn lại; có vi phạm nghĩa vụ bắt buộc hay không.
- Control bù trừ, cách đánh giá hiệu lực, giới hạn và bằng chứng.
- Người đề xuất, người phê duyệt **có thẩm quyền**, thời điểm, hạn hiệu lực và điều kiện xem xét lại.
- Kế hoạch sửa triệt để, owner, deadline, phép retest và tiêu chí đóng.

**Ngoại lệ được phê duyệt không có nghĩa control chuyển từ FAIL thành PASS.** Cần giữ trạng thái kỹ thuật và quyết định chấp nhận rủi ro ở hai trường riêng. Người tạo môi trường hoặc người sửa cấu hình không mặc nhiên có quyền tự duyệt ngoại lệ.

Một trường hợp đáng cảnh giác: “Để test nhanh, mở network policy staging ra Internet trong hai tuần”. Nếu staging chứa dữ liệu thật hoặc credential có đường tới production, reviewer cần đánh giá tác động và các lựa chọn an toàn khác trước khi phê duyệt. Không mặc nhiên chấp nhận chỉ vì “không phải prod”.

## 11. Chương trình đánh giá liên tục và drift detection

Security standard theo môi trường có thể trở nên lỗi thời khi tài sản và quyền thay đổi. Cần xác định **trigger đánh giá lại** và hoạt động giám sát.

| Trigger | Cần kiểm tra lại | Bằng chứng cần cập nhật |
| --- | --- | --- |
| Tạo môi trường mới hoặc preview | Owner, dữ liệu, ingress, IAM, thời hạn hủy | Inventory, baseline mapping, cleanup rule |
| Thêm dữ liệu thật vào non-prod | Phân loại, căn cứ, bảo vệ, retention và owner | Data inventory, approval, control/test |
| Thay IAM/service account | Quyền hiệu lực, tác động qua môi trường, tính truy vết | IAM snapshot, access tests, change log |
| Thay gateway/ingress/network | External exposure, route cũ, port, policy | Runtime route inventory, positive/negative tests |
| Nâng cấp Spring/dependency/container | Behavior control, lỗ hổng, cấu hình mặc định | SCA/SAST, regression, deployed version |
| Thay CI runner, registry, artifact | Trust boundary, nguồn gốc, quyền phát hành/deploy | Pipeline review, artifact provenance, digest |
| Mất log hoặc monitoring | Khả năng phát hiện, phạm vi sự kiện bị bỏ sót | Pipeline health, synthetic event/alert test |
| Lỗi backup/DR hoặc rehearsal | RPO/RTO, tính sẵn sàng và độ toàn vẹn | Restore/failover test, finding, retest |
| Sự cố, audit finding hoặc ngoại lệ hết hạn | Residual risk và độ hiệu lực của claim cũ | Incident report, remediation, approval và review |

### Kiểm tra drift thực tế

1. Đọc **desired state**: chuẩn đã phê duyệt, overlay, IaC, policy-as-code, manifest, pipeline.
2. Thu **actual state** ở cùng thời điểm/phạm vi: policy IAM thực tế, ingress, config, image digest, workload, log health.
3. So sánh theo **Control ID**, không chỉ theo văn bản; phân biệt thay đổi có phê duyệt với sai lệch ngoài quy trình.
4. Phân loại **FAIL / INCONCLUSIVE / ngoại lệ**, gán owner và mức ưu tiên theo rủi ro.
5. Khắc phục bằng thay đổi có kiểm soát; xác minh lại actual state và các test liên quan.
6. Lưu evidence trước/sau, reviewer, thời điểm và trigger kiểm chứng tiếp theo.

Không nên tự động ghi đè mọi drift không phân biệt: trong sự cố production có thể tồn tại thay đổi khẩn cấp đã được cấp quyền nhưng chưa cập nhật source. Quy trình cần ghi rõ mức độ tự động sửa, escalation, review hồi tố và tiêu chí không làm gián đoạn dịch vụ.

## 12. Phân vai trong áp dụng chuẩn theo môi trường

| Vai trò | Trách nhiệm | Không nên tự ý quyết định |
| --- | --- | --- |
| **Security Governance / GRC** | Xác định chuẩn, ngưỡng và cách chứng minh; quản lý phiên bản | Tuyên bố một môi trường đạt mà không xét bằng chứng |
| **Risk Owner / Data Owner** | Xác định tác động, phân loại dữ liệu và quyết định trong thẩm quyền | Dùng nhãn “test” để miễn trừ nghĩa vụ bảo vệ dữ liệu |
| **Developer / Tech Lead** | Hiện thực control ứng dụng, test, review, CI checks và thông tin dependency | Tắt authorization/secret protection để thuận tiện mà không review |
| **Ops / SRE / Platform** | Vận hành môi trường, IAM, network, secrets, backup, log, deployment và actual-state evidence | Tự chấp nhận mọi ngoại lệ bảo mật ngoài thẩm quyền |
| **Security / AppSec / SOC** | Hỗ trợ threat model, đánh giá control, khả năng phát hiện, ứng cứu | Chỉ dựa trên checklist mà không xem đường gây hại |
| **Assessor / Audit** | Kiểm chứng claim, evidence, ngoại lệ và finding trong phạm vi được giao | Dùng lời tự xác nhận của operator thay review cần độc lập |

Một tổ chức nhỏ có thể gộp nhiều vai trò ở một nhóm; khi đó vẫn cần mô tả **ai là Responsible, ai là Accountable, ai review và ai có thẩm quyền chấp nhận rủi ro**. Đừng dùng ma trận RACI để tránh trách nhiệm chung trong sự cố xuyên nhiều môi trường.

## 13. Case study: staging “nhẹ” trở thành đường vào production

### Bối cảnh

Một hệ thống quản lý khách hàng gồm API Java/Spring Boot chạy trên Kubernetes. Nhóm phát triển có staging dùng để chạy kiểm thử cuối trước release. Vì cần tái hiện lỗi hiếm, nhóm thử tải snapshot dữ liệu khách hàng thật vào staging. Staging có public ingress cho đối tác test và service account của CI runner cho phép push image vào registry dùng chung với production.

Một cuộc đánh giá phát hiện:

- Bảng chuẩn staging đang gắn nhãn `LOW` dù chứa dữ liệu thật.
- Một management endpoint chỉ giới hạn theo IP, không có bằng chứng về effective authentication.
- CI runner lưu token có phạm vi ghi vào nhiều image repo.
- Staging dùng chung một số secret với production.
- Security audit log staging không gửi đầy đủ event thay đổi IAM.
- Bộ test security chạy xanh nhưng dùng cấu hình auth khác production; chưa có phép kiểm tra chéo.

### Đánh giá theo mục tiêu bảo mật

| Risk/finding | Vì sao đáng quan tâm | Control và bằng chứng cần bổ sung |
| --- | --- | --- |
| **F-ENV-01: dữ liệu thật ở staging** | Có thể lộ dữ liệu khách hàng từ môi trường ít được quản trị | Data owner approval, phân loại, access test, retention, xử lý bản sao |
| **F-ENV-02: management endpoint** | Có thể tiết lộ cấu hình hoặc cho hành động đặc quyền | Actual ingress/auth, test từ mạng phù hợp, response kiểm chứng |
| **F-ENV-03: CI token quyền rộng** | Xâm nhập staging/pipeline có thể tác động artifact prod | Effective token permissions, tách identity, test deny, review workflow |
| **F-ENV-04: secret dùng chung** | Secret bị lộ ở non-prod có thể được dùng ở production | Inventory secret, rotation/revocation, isolation verification |
| **F-ENV-05: thiếu IAM audit event** | Không đủ khả năng truy vết thay đổi và điều tra | Synthetic event → collector → alert, coverage và owner |
| **F-ENV-06: test không tương đương** | CI pass không chứng minh behavior auth trong production | So cấu hình, test authorization với production-like profile, digest evidence |

### Phương án xử lý

**Bước 1 — Xác định phạm vi:** môi trường nào, các namespace, IAM, secrets, dữ liệu và bản sao nào bị ảnh hưởng. Không dựa vào tên “staging”.

**Bước 2 — Giảm tác động:** kiểm tra và hạn chế ingress/quyền theo quy trình; đánh giá khả năng đã lộ dữ liệu/secret, phối hợp xử lý hoặc xoay secret khi cần. Việc thay đổi production phải theo cơ chế điều phối và phê duyệt tương ứng.

**Bước 3 — Thiết kế baseline điều kiện:** nếu staging còn dữ liệu thật, áp dụng các control bảo vệ dữ liệu tương xứng. Nếu có thể, thay bằng dữ liệu tổng hợp hoặc dữ liệu đã xử lý giảm nhạy cảm phù hợp; thiết lập thời hạn xử lý snapshot.

**Bước 4 — Tách quyền:** giới hạn quyền CI runner theo service/artifact, tách secret production và staging, kiểm chứng credential cũ không còn có đường tới production.

**Bước 5 — Làm rõ tính tương đương:** test Spring Security với các profile liên quan; đối chiếu route, issuer/audience, role mappings, policies và artifact. Không đòi staging dùng chung secret hoặc database với production để có parity.

**Bước 6 — Retest:** kiểm thử truy cập endpoint admin, bucket và artifact trái quyền; phát event IAM thử tới collector; đối chiếu config đang chạy. Ghi nhận các phần còn chưa quan sát.

**Bước 7 — Kết luận:** cập nhật control status, finding và residual risk. Chủ sở hữu rủi ro được trao thẩm quyền quyết định phần ngoại lệ; assessor kiểm chứng kết quả trong phạm vi đã giao.

**Bài học:** chuẩn theo môi trường phải phản ánh **dữ liệu và khả năng tác động thực tế**. Non-prod có thể trở thành đường vào production hoặc nơi lưu dữ liệu nhạy cảm; một checklist “staging ít nghiêm” không đủ.

## 14. Bài tập thực hành

**Tình huống:** tổ chức có bốn môi trường cho cùng dịch vụ thanh toán:

- `dev`: dữ liệu tổng hợp, không public ingress; các Developer dùng một CI runner chung.
- `qa`: nhận dữ liệu giả nhưng webhook trỏ tới endpoint của đối tác thật; không có tài khoản riêng cho mỗi workload.
- `stage`: kiến trúc gần production, có snapshot dữ liệu thật đã giới hạn định danh; vẫn giữ một service account có quyền đọc production bucket.
- `prod`: dữ liệu khách hàng thật, ingress công khai; backup thành công nhưng chưa thực hành restore trong kỳ review.
- Một vùng `dr`: nhận replica dữ liệu thật, có policy mạng và logging cũ chưa được kiểm chứng.

Hãy trả lời:

1. Đối với mỗi môi trường, xác định **rủi ro nổi bật** và lý do nó không thể được đánh giá chỉ bằng nhãn.
2. Chọn **năm control baseline chung** và **ít nhất hai overlay có điều kiện**; nêu tiêu chí áp dụng.
3. Viết **bốn security requirements có thể kiểm tra**, gồm quyền IAM, outbound webhook, data isolation và DR restore.
4. Đề xuất tối thiểu **sáu hiện vật evidence**, phân biệt design, test và runtime.
5. Nếu cần giữ service account stage đọc production bucket trong hai tuần, ai quyết định? Ngoại lệ phải ghi gì và kiểm tra control bù trừ thế nào?
6. Xác định trigger đánh giá lại khi CI runner thay đổi, có dữ liệu thật mới, chuyển gateway hoặc thay replica DR.

### Gợi ý đáp án

| Phát hiện | Hướng xử lý và kiểm chứng |
| --- | --- |
| CI runner chung | Đánh giá quyền repository/registry/deploy, tách hoặc giới hạn identity; giữ CI audit trail |
| QA webhook tới đối tác thật | Ràng buộc egress/endpoint, dùng sandbox khi phù hợp; kiểm tra request không tạo hành động thật ngoài ý muốn |
| QA workload không có identity riêng | Thiết kế service account theo phạm vi, test quyền từ chối và cấp quyền đúng |
| Stage chứa snapshot dữ liệu thật | Data owner review, bảo vệ theo độ nhạy, xác minh ẩn danh nếu có và retention |
| Stage có quyền đọc production bucket | Ưu tiên tách quyền, dùng dữ liệu đã được cấp phép; nếu ngoại lệ thì ghi risk owner, thời hạn và biện pháp bù trừ |
| Prod chưa có restore test | Backup success không chứng minh khả năng phục hồi; làm restore drill có RPO/RTO đo được |
| DR có policy cũ | So yêu cầu bảo vệ production/DR với trạng thái DR, test log, IAM, failover và quyền truy cập |

Một câu trả lời tốt **không** chỉ liệt kê “prod dùng strict, dev dùng relaxed”. Nó phải xác định **tài sản, quyền, dữ liệu, đường gây hại, control, cách kiểm chứng và người chịu trách nhiệm**.

## 15. Sai lầm cần tránh

| Sai lầm | Vì sao nguy hiểm? | Cách làm phù hợp |
| --- | --- | --- |
| “Dev/test nên được phép tắt auth.” | Không còn test được bảo mật; môi trường có thể chứa secret hoặc đường đến prod | Giữ control lõi, dùng identity và fixture phù hợp |
| “Chỉ có production mới cần bảo vệ dữ liệu.” | Non-prod có thể chứa dữ liệu thật/bản sao và bên thứ ba | Phân loại theo dữ liệu thực và quyền, áp dụng overlay điều kiện |
| “Staging càng giống production thì càng nên dùng chung DB/secret.” | Chia sẻ bí mật và dữ liệu phá cô lập | Giữ parity hành vi nhưng tách identity, secret và dữ liệu |
| “Đã có policy Terraform thì quyền runtime luôn đúng.” | Drift, cấu hình ngoài pipeline hoặc deploy khác có thể tồn tại | So desired/actual state, thử quyền có kiểm soát |
| “Cùng Docker image nghĩa là cùng assurance.” | Config, IAM, ingress, dữ liệu và trust boundary có thể khác | Gắn evidence với môi trường và version |
| “Bảo mật chỉ xét scanner xanh.” | Scanner không tìm hết lỗi logic, quyền và nhánh ẩn | Threat modeling, negative tests, runtime review và audit |
| “Không có alert nghĩa là không có rủi ro.” | Pipeline có thể thiếu nguồn, mất event hoặc rule sai | Kiểm tra log end-to-end và health của telemetry |
| “DR là vùng phụ nên ít giám sát.” | Chứa bản sao dữ liệu thật; lỗi DR ảnh hưởng tới phục hồi và bảo mật | Control tương xứng dữ liệu, drill và kiểm tra định kỳ |
| “Ngoại lệ được duyệt nghĩa là control PASS.” | Quyết định chấp nhận rủi ro khác hiệu lực kỹ thuật | Giữ trạng thái FAIL/INCONCLUSIVE và hồ sơ ngoại lệ riêng |
| “Một lần compliance pass là đủ mãi mãi.” | Deployment, secret, quyền, data và network thay đổi | Drift detection, trigger review và retest |

## Ghi nhớ

- **Chuẩn theo môi trường** là bộ yêu cầu kiểm chứng được, xuất phát từ **baseline chung và overlay theo rủi ro**, không phải danh sách “dev lỏng / prod chặt” cố định.
- Việc phân loại phải xét **dữ liệu thật, quyền, kết nối, tính quan trọng và khả năng tác động tới production**, không dựa duy nhất vào nhãn môi trường.
- **Isolation và parity** cần được cân bằng: tách dữ liệu/secret/quyền nhưng giữ tương đương những hành vi và security controls cần kiểm thử.
- Mỗi control cần **ID, owner, tiêu chí nghiệm thu, bằng chứng design/test/runtime, reviewer, phạm vi và phiên bản**; thiếu evidence không tự động là PASS.
- Chuỗi assurance là **rủi ro → mục tiêu → yêu cầu → security control → test → evidence → finding → remediation/retest**.
- Ngoại lệ có thời hạn là **quyết định quản trị về residual risk**, không thay bằng chứng kỹ thuật hoặc hợp thức hóa một control không đạt.
- Security standards phải được **kiểm tra liên tục** khi có thay đổi ứng dụng, dữ liệu, IAM, ingress, CI/CD, bản triển khai, sự cố hoặc môi trường DR.
