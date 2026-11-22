# Khôi phục sau xóa nhầm, khóa bị vô hiệu hóa và mã độc tống tiền

Khi một tập dữ liệu biến mất, ứng dụng không thể giải mã dữ liệu hoặc xuất hiện dấu hiệu mã độc tống tiền, phản ứng hấp tấp có thể khiến thiệt hại tăng lên. Khôi phục nhầm phiên bản sẽ ghi đè dữ liệu hợp lệ; bật lại khóa mã hóa đang bị lạm dụng có thể mở đường cho kẻ tấn công; khôi phục backup vào hệ thống còn bị kiểm soát có thể khiến bản phục hồi bị mã hóa hoặc xóa lần nữa.

Bài học này trình bày cách nhận diện sự cố, lựa chọn **điểm khôi phục đáng tin**, thực hiện khôi phục **có kiểm soát** và chứng minh dữ liệu cùng dịch vụ đã trở lại trạng thái an toàn trên Google Cloud. Ba tình huống thực hành là **xóa nhầm**, **khóa Cloud KMS/CMEK không thể sử dụng** và **ransomware**. Đó là ba lớp vấn đề khác nhau nên không thể áp dụng một lệnh restore chung.

Bài thuộc chương **Sao lưu và phục hồi thảm họa** của module **CLOUD_PROVIDERS_GCP**. Module này khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu; qua tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Bài tập sử dụng Cloud Storage, Cloud SQL, Cloud KMS và Backup and DR làm ví dụ nhưng nguyên tắc về bằng chứng, quyền, RTO/RPO và kiểm thử áp dụng cho nhiều workload khác.

> **Cảnh báo vận hành:** Các lệnh và cấu hình bên dưới chỉ là ví dụ, không được tự động chạy trên dữ liệu production. Chỉ người được ủy quyền mới có thể xác định ranh giới sự cố, chấp thuận thao tác ghi đè, đổi trạng thái khóa, thay IAM hoặc thực hiện cutover. Nếu nghi ngờ có xâm nhập, điều phối với nhóm Security Incident Response trước khi phục hồi.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt xóa nhầm, xóa cả bucket/instance, sửa hỏng dữ liệu, mất quyền giải mã và ransomware.
- Chọn đúng cơ chế khôi phục: Cloud Storage soft delete/versioning, Cloud SQL backup/PITR, snapshot, Backup and DR vault hoặc Backup for GKE.
- Nhận diện trạng thái `ENABLED`, `DISABLED`, `DESTROY_SCHEDULED` và `DESTROYED` của Cloud KMS key version.
- Phân biệt lỗi quyền IAM với khóa không thể dùng và biết thời điểm không nên tự ý bật lại khóa.
- Xây dựng trình tự containment → evidence → restore point → isolated recovery → verification → cutover.
- Đo RPO/RTO thực tế và phân biệt khả năng có bản backup với khả năng phục hồi dịch vụ.
- Thiết kế bảo vệ backup bằng IAM phân tách trách nhiệm, retention có cưỡng chế và diễn tập định kỳ.

## 1. Bắt đầu bằng phân loại sự cố

Những thông báo “không đọc được dữ liệu” nhìn giống nhau nhưng nguyên nhân có thể khác biệt lớn.

| Dấu hiệu | Khả năng nguyên nhân | Câu hỏi đầu tiên | Không nên làm ngay |
|---|---|---|---|
| Object không còn trong Cloud Storage | Xóa nhầm, lifecycle, ghi đè, mã độc | Soft delete, generation hoặc retention còn hiệu lực không? | Bulk restore toàn bucket không có bộ lọc |
| Cloud SQL không còn instance | Xóa nhầm instance hoặc project | Có retained/final backup và PITR window không? | Tạo instance mới trùng tên rồi giả định được khôi phục |
| Bản ghi database thay đổi sai | Bug, migration, thao tác SQL nhầm | Thời điểm thay đổi và cửa sổ PITR là gì? | Restore trực tiếp lên database đang chạy |
| GCS/Cloud SQL báo lỗi sử dụng CMEK | Key version bị disable, IAM/service agent bị thu hồi, EKM không sẵn sàng | Key state, quyền và audit log cho biết gì? | Tạo key mới rồi xóa key cũ |
| Nhiều object bị mã hóa/đổi tên đột ngột | Ransomware hoặc application bug | Có dấu hiệu account compromise, mass delete, exfiltration? | Chạy lại workload nghi nhiễm lên backup |
| Snapshot tồn tại nhưng không mount được | Không có key, khác region/quota, corrupt dữ liệu | Key dependency và restore target có hợp lệ không? | Xóa snapshot hoặc disk nguồn |

**Nhận dạng đúng là bước đầu tiên của recovery.** Trong sự cố bảo mật, hãy làm đồng thời incident response và disaster recovery nhưng giữ hai tuyến trách nhiệm rõ: Security kiểm soát bằng chứng và mối đe dọa; Recovery team kiểm soát tính đúng đắn của bản phục hồi.

### 1.1. Thứ tự ưu tiên

1. Bảo vệ con người, tài khoản và dữ liệu còn lành.
2. Ngăn hành vi tiếp tục xóa/mã hóa/ghi sai khi có căn cứ.
3. Giữ lại audit logs, dấu thời gian, resource ID và dữ liệu phục vụ điều tra.
4. Xác định bản sao lưu và các key version cần để đọc bản đó.
5. Phục hồi trong môi trường cách ly, soát tính toàn vẹn.
6. Chuyển traffic hoặc đổi endpoint khi được phê duyệt.
7. Theo dõi tái nhiễm, lỗi ứng dụng, sai lệch dữ liệu và tổng kết sự cố.

Không coi **restore thành công theo API** là **phục hồi nghiệp vụ thành công**. Người dùng chỉ được phục vụ lại khi những luồng nghiệp vụ trọng yếu vượt kiểm thử và nhóm chịu trách nhiệm chấp nhận rủi ro tồn đọng.

## 2. Một runbook thống nhất cho cả ba kịch bản

Mọi sự cố nên có một bộ trường chung để người trực có thể phối hợp:

~~~yaml
incident_id: INC-EXAMPLE-2026-001
severity: SEV-1
status: investigating
service: checkout-api
environment: production
detected_at_utc: "2026-11-19T08:00:00Z"
suspected_start_utc: "2026-11-19T07:40:00Z"
incident_commander: "Vai trò được phân công"
security_lead: "Vai trò được phân công"
recovery_lead: "Vai trò được phân công"
source_project: "PROJECT_ID"
affected_assets:
  - "Cloud SQL: orders-db"
  - "Cloud Storage: gs://BUCKET_NAME/orders/"
encryption_dependencies:
  - "projects/KEY_PROJECT/locations/LOCATION/keyRings/RING/cryptoKeys/KEY"
target_rpo_minutes: 15
target_rto_minutes: 120
candidate_recovery_point: "Chưa xác nhận"
approvals:
  destructive_restore: false
  key_state_change: false
  production_cutover: false
~~~

Đây là **mẫu ghi chép**, không phải file cấu hình dành cho API Google Cloud. Thay thông tin minh họa bằng ID sự cố thật trong hệ thống được kiểm soát quyền truy cập. Không ghi thông tin mật, secret hoặc dữ liệu người dùng vào báo cáo chia sẻ rộng.

### 2.1. Sơ đồ quyết định ban đầu

~~~mermaid
flowchart TD
    A["Phát hiện mất/không đọc được dữ liệu"] --> B["Cô lập hành động có nguy cơ, bảo toàn chứng cứ"]
    B --> C{"Dấu hiệu compromise hoặc ransomware?"}
    C -->|"Có"| D["Kích hoạt Security IR, thu hồi session/credential theo phê duyệt"]
    C -->|"Chưa"| E["Kiểm tra timeline và audit logs"]
    D --> E
    E --> F{"Lỗi đọc vì CMEK?"}
    F -->|"Có"| G["Kiểm tra IAM, key state và EKM"]
    F -->|"Không"| H{"Bị xóa/sửa hỏng?"}
    G --> I["Xác định key version có thể phục hồi"]
    H -->|"Có"| J["Tìm soft delete, backup, PITR, vault"]
    H -->|"Không"| K["Điều tra tiếp, chưa ghi đè"]
    I --> L["Chọn recovery point sạch và quyền hợp lệ"]
    J --> L
    L --> M["Restore trong môi trường cách ly"]
    M --> N{"Dữ liệu sạch và kiểm thử đạt?"}
    N -->|"Không"| L
    N -->|"Có"| O["Phê duyệt cutover và giám sát"]
~~~

### 2.2. Ai có quyền làm gì?

| Vai trò | Quyết định được đề xuất | Không tự ý thực hiện |
|---|---|---|
| Incident commander | Mức độ nghiêm trọng, thứ tự khôi phục, thông tin liên lạc | Không bỏ qua kiểm tra security |
| Security lead | Scope compromise, bảo toàn bằng chứng, containment, clean bill of health | Không tự xóa chứng cứ vì muốn dọn nhanh |
| Data owner/DBA | Recovery point, tính toàn vẹn, đối soát dữ liệu | Không restore đè khi chưa xác nhận phạm vi mất dữ liệu |
| KMS administrator | Phân tích key state, khôi phục/enabling theo phê duyệt | Không cấp quyền giải mã tràn lan |
| Recovery operator | Thực hiện restore vào target chỉ định | Không tự đổi production endpoint |
| Service owner/SRE | SLO, traffic cutover, rollback và giám sát | Không coi health check 200 là đủ |

Với các thay đổi có thể phá hủy dữ liệu, yêu cầu phê duyệt hai người hoặc change control của tổ chức. Không cấp `roles/owner` chỉ để chạy lệnh restore; quyền nên được cấp theo thao tác và thời hạn.

## 3. Chuẩn bị để có thể khôi phục

**Backup là một bản sao; recoverability là khả năng tìm, giải mã, tái tạo và xác minh bản sao đó trong thời gian yêu cầu.** Một backup có thể tồn tại nhưng không dùng được nếu quyền IAM, key version, region, network hoặc tài khoản backup đã bị xâm phạm.

Thiết kế các lớp bảo vệ:

| Lớp | Vai trò | Ví dụ Google Cloud |
|---|---|---|
| Khôi phục gần | Chống xóa/sửa nhầm trong vài ngày | Cloud Storage soft delete; Object Versioning |
| Khôi phục theo thời điểm | Chọn thời điểm trước khi lỗi ghi dữ liệu | Cloud SQL point-in-time recovery |
| Sao lưu độc lập và retention | Chống xóa backup khi production account bị chiếm | Backup and DR backup vault với enforced retention |
| Bảo vệ dữ liệu không đổi | Ngăn xóa/ghi đè trước thời hạn | Cloud Storage Bucket Lock/Object Retention Lock |
| Sao lưu cấu hình | Tái tạo hạ tầng và workload | Terraform/IaC, Git, Backup for GKE khi phù hợp |
| Quản lý khóa và danh tính | Giữ khả năng đọc dữ liệu backup | Cloud KMS, service agent IAM, break-glass access |
| Xác minh và diễn tập | Chứng minh restore thực sự hoạt động | Restore drill, checksum, query và transaction reconciliation |

Với dữ liệu quan trọng, cân nhắc nguyên tắc nhiều bản sao, khác vị trí/quyền quản trị và có một bản không thể xóa bởi quyền production thông thường. Không giả định các tính năng retention của một dịch vụ tự động bảo vệ các tài nguyên ở dịch vụ khác.

### 3.1. Backup vault và retention cưỡng chế

Backup and DR backup vault hỗ trợ **enforced retention**. Trong thời gian retention có hiệu lực, backup được bảo vệ khỏi xóa thủ công, kể cả bởi admin hoặc Google, theo phạm vi tính năng. Enforced retention cần được thiết kế từ trước; không cứu được bản backup đã bị xóa trước khi chính sách được áp dụng.

Lưu ý quan trọng:

- Quyền quản trị vault, quyền sao lưu, quyền restore và quyền sản xuất nên tách biệt.
- Khóa, service agent và project chứa backup phải được duy trì khả dụng; immutable backup không đồng nghĩa tự giải mã được backup.
- Một số cấu hình vault có thể bị ràng buộc bởi quyền, resource type, region, compliance và chi phí.
- Retention dài có thể làm tăng phí lưu trữ và không thể rút ngắn tùy ý khi đã khóa.
- Project liens có thể bổ trợ ngăn xóa project chứa vault; vẫn cần bảo vệ project và identity trước compromise.

**Không thử xóa backup để “xác nhận immutable” trên hệ thống thật.** Trong lab, dùng tài nguyên được tạo riêng và kiểm tra cấu hình/chính sách thay vì tạo sự cố phá hủy dữ liệu production.

## 4. Kịch bản A: khôi phục Cloud Storage sau xóa nhầm

### 4.1. Soft delete hoạt động thế nào?

Cloud Storage soft delete giữ lại object hoặc bucket bị xóa/ghi đè trong khoảng thời gian định trước. Với bucket hỗ trợ tính năng này, soft delete được bật mặc định, thời gian mặc định thường là **7 ngày**; có thể cấu hình **3–90 ngày**, hoặc tắt với retention bằng 0. Cấu hình của từng bucket có thể khác, vì vậy phải kiểm tra trước sự cố.

Object soft-deleted **không đọc trực tiếp** và không sửa được. Người có quyền khôi phục sẽ tạo ra một phiên bản live mới; bản soft-deleted gốc vẫn tồn tại đến khi hết retention. Khi khôi phục object trùng tên với phiên bản live, có nguy cơ ghi đè/đổi trạng thái bản đang hoạt động. **Kiểm tra tên, generation và điều kiện overwrite trước khi chạy lệnh.**

| Tính năng | Có thể giúp khôi phục gì? | Giới hạn cần nhớ |
|---|---|---|
| Soft delete | Object/bucket vừa bị xóa hoặc ghi đè trong retention | Hết hạn không thể khôi phục bằng tính năng này |
| Object Versioning | Phiên bản object cũ còn noncurrent | Không tự bảo vệ khi xóa cả bucket; version cũ có thể bị xóa |
| Bucket retention policy | Ngăn xóa/ghi đè object trước thời điểm retention | Không khôi phục dữ liệu đã bị xóa trước khi bật |
| Bucket Lock | Khóa retention policy ở cấp bucket | Khóa là thao tác không thể đảo ngược; có chi phí và ràng buộc |
| Object Retention Lock | Bảo vệ object riêng lẻ theo thời hạn | Không thay thế backup độc lập; cần thiết kế trước |

Google Cloud khuyến nghị **soft delete** làm lớp bảo vệ chính trước xóa nhầm/malicious delete của Cloud Storage. Object Versioning có thể bổ sung để truy cập các bản noncurrent, nhưng không thay thế khả năng khôi phục bucket bị xóa.

### 4.2. Điều tra object bị xóa

Trước tiên, xác nhận project/bucket và khoảng thời gian nghi bị xóa. Dùng lệnh **chỉ đọc**:

~~~bash
# Chạy bằng account đã được cấp quyền xem soft-deleted objects.
gcloud storage ls "gs://RECOVERY_LAB_BUCKET/**" --soft-deleted

# Tìm các generation đã bị xóa của một object cụ thể.
gcloud storage ls "gs://RECOVERY_LAB_BUCKET/orders/order-001.json" --soft-deleted
~~~

Kết quả cung cấp các generation để chọn đối tượng cần khôi phục. Đối chiếu thời gian xóa, nguồn tạo và audit log với timeline sự cố. Với nhiều object bị xóa, nên lập danh sách và checksum/metadata mong đợi trước khi bulk restore.

### 4.3. Khôi phục đúng generation

Sau khi Data owner chấp thuận và xác minh không gây ghi đè bản live quan trọng, có thể sử dụng:

~~~bash
# CHỈ VÍ DỤ TRONG BUCKET LAB RIÊNG, KHÔNG CHẠY TRÊN PROD.
gcloud storage restore \
  "gs://RECOVERY_LAB_BUCKET/orders/order-001.json#GENERATION_NUMBER"
~~~

Nếu live object trùng tên tồn tại, lệnh có thể không cho ghi đè theo tùy chọn CLI, hoặc người vận hành phải chọn hành vi overwrite rõ ràng. Không tự động thêm `--allow-overwrite`: trước tiên xem version hiện có và phương án khôi phục sang khu vực cách ly. Sau restore, so sánh checksum, content type, generation mới và quyền truy cập; object được khôi phục có thể trở thành storage class **Standard**, làm thay đổi chi phí.

Nếu xóa cả bucket, **khôi phục bucket trước**, rồi đến objects. Trên CLI/API, restore bucket chỉ trả lại **bucket rỗng**; cần chạy restore objects riêng. Google Cloud Console có luồng hỗ trợ chọn restore cả objects cùng bucket. Khôi phục có thể bị chặn nếu tên bucket đã được người khác sử dụng hoặc đã hết retention.

### 4.4. Khôi phục nhiều object và rủi ro bulk restore

Khi hàng nghìn object bị xóa trong một khoảng thời gian, Cloud Storage hỗ trợ bulk restore bất đồng bộ, lọc theo thời điểm xóa và pattern. Bước này có thể tốn thời gian và tiền, đồng thời cần xử lý các đối tượng đã được ghi lại sau khi bị xóa. Đừng sử dụng wildcard toàn bucket nếu chỉ một prefix bị ảnh hưởng.

Trình tự an toàn:

1. Xuất danh sách generation/object bị ảnh hưởng bằng lệnh chỉ đọc.
2. Chọn khoảng thời gian xảy ra xóa nhầm; loại object cố ý xóa theo lịch.
3. Phân nhóm prefix, xác nhận quyền sở hữu và ảnh hưởng ứng dụng.
4. Khôi phục thử một tập nhỏ vào môi trường cách ly hoặc theo quy trình không ghi đè.
5. Kiểm tra hash, nội dung, metadata và mapping object-key nghiệp vụ.
6. Phê duyệt bulk restore có bộ lọc, theo dõi long-running operation.
7. Đối soát số lượng thành công, thất bại, skip và dữ liệu live sau restore.

**Soft delete không đảo ngược được một transaction database sai.** Nếu object và bản ghi Cloud SQL cần nhất quán, phục hồi cả hai theo một recovery plan có mốc thời gian chung.

## 5. Kịch bản A mở rộng: Cloud SQL bị xóa hoặc dữ liệu bị sửa sai

Cloud SQL PostgreSQL có hai luồng chính:

- **Restore từ backup:** khôi phục dữ liệu tại thời điểm backup. Nếu chọn **instance đích đã tồn tại**, thao tác có thể **ghi đè toàn bộ dữ liệu hiện có** trên instance đó, gồm PITR logs của đích. Để giảm rủi ro, ưu tiên **instance mới** khi điều tra.
- **Point-in-time recovery (PITR):** tạo **instance mới** tại một thời điểm nằm trong PITR window. Không thể dùng PITR để khôi phục trực tiếp lên instance hiện có. PITR phải được cấu hình đúng từ trước và nhật ký còn trong cửa sổ giữ lại.

### 5.1. Điều tra trước khi quyết định restore

~~~bash
# Kiểm tra mô tả instance và xem có PITR được bật.
gcloud sql instances describe ORDERS_DB \
  --project=STAGING_PROJECT_ID

# Liệt kê backup với mô hình standard backup phù hợp.
gcloud sql backups list \
  --instance=ORDERS_DB \
  --project=STAGING_PROJECT_ID
~~~

Danh sách backup thực tế phụ thuộc **Standard** hay **Enhanced** backup và trạng thái instance. Với Enhanced backup, phải kiểm tra vault, backup plan, data source và quyền restore tương ứng. Tài liệu hiện hành phân biệt quy trình khôi phục của từng loại; không giả định mọi backup dùng cùng một lệnh.

Ví dụ khi đã xác định dữ liệu bị ghi sai lúc **10:00 UTC**, PITR window còn chứa **09:55 UTC**, có thể đề xuất khôi phục về **09:55** trên **instance mới**. Trước khi thực thi, xác nhận timestamp timezone và thời điểm bắt đầu ghi sai dựa vào audit/application logs, tránh chọn bản đã bị lỗi.

### 5.2. Khi instance bị xóa

Đối với Cloud SQL hiện nay, khả năng phục hồi sau xóa phụ thuộc cấu hình **retained backups**, **final backup**, **Enhanced backups** và **PITR logs**. Nếu có backup được giữ, có thể restore vào instance mới; nếu PITR của instance đã xóa được giữ, có thể phục hồi theo timestamp bằng API/CLI theo tài liệu.

Nếu instance bị xóa nhầm mà không có final backup, Google Cloud có cơ chế **liên hệ Customer Care trong vòng bốn ngày** để *yêu cầu* khôi phục instance trong một số điều kiện. Đây **không phải bảo đảm** dữ liệu luôn khôi phục được và tuyệt đối không thể thay thế backup retention chủ động. Mở support case sớm; lưu thời điểm xóa, project, instance ID và bằng chứng nhưng không tự tạo lại dữ liệu vào resource trùng tên.

Khi restore sang instance mới, IP, connection name, network, IAM, authorized networks và cấu hình DNS/secret của ứng dụng có thể khác. Hãy xác nhận từng phụ thuộc trước khi chuyển traffic.

### 5.3. Kiểm tra tính nhất quán sau restore

- Đối chiếu số lượng và tổng giá trị đơn hàng giữa log nghiệp vụ, bản backup và nguồn giao dịch ngoài.
- Kiểm tra schema migration/version và mã ứng dụng tương thích.
- Kiểm tra duplicate keys, foreign keys và state machine của đơn hàng.
- Kiểm tra outbox/event logs; replay có idempotency, tránh tạo giao dịch lần hai.
- Dùng read-only smoke queries trước khi cho phép ghi.
- Xác nhận dịch vụ đặt lại các secret/connection strings đúng instance phục hồi.

Với hệ thống có thanh toán, không tự động phát lại mọi message hoặc mọi request. Việc đối soát với hệ thống thanh toán bên ngoài có thể cần quyết định của business owner và kiểm soát chống double-charge.

## 6. Kịch bản B: khóa Cloud KMS/CMEK bị vô hiệu hóa

Một hệ thống có dữ liệu vẫn còn nguyên trong Cloud Storage, Cloud SQL hoặc snapshot nhưng không thể đọc do **customer-managed encryption key (CMEK)** không hoạt động. Khôi phục từ backup cũng có thể thất bại nếu bản backup dùng cùng key version không khả dụng.

### 6.1. Các trạng thái của Cloud KMS key version

| Trạng thái | Có thể dùng crypto operations? | Hướng xử lý |
|---|---|---|
| `ENABLED` | Có, nếu IAM/service agent cho phép | Điều tra lỗi quyền, region, service integration hoặc EKM |
| `DISABLED` | Không; key material vẫn được giữ | Có thể **enable** lại sau phê duyệt |
| `DESTROY_SCHEDULED` | Không; đang chờ hủy | Có thể **restore** trong thời gian chờ, sau đó **enable** |
| `DESTROYED` | Không; key material đã bị hủy | Thông thường **không thể phục hồi**; ngoại lệ kỹ thuật riêng cho key material đã import lại nguyên vẹn |
| `PENDING_GENERATION` / `PENDING_IMPORT` | Chưa dùng được | Chờ hoàn thành hoặc điều tra import/key creation |

Mặc định lịch chờ destroy của một key version thường là **30 ngày**, nhưng có thể được cấu hình hoặc bị chính sách tổ chức ràng buộc. Sau thời gian chờ, việc hủy khóa về nguyên tắc không thể đảo ngược. Ngoại lệ với key được import lại nguyên key material **không** áp dụng đại trà và không phải kế hoạch khôi phục tiêu chuẩn.

**Đổi primary key version không tự giúp giải mã dữ liệu cũ.** Dữ liệu đã mã hóa bằng version nào cần chính version đó để giải mã; rotation phục vụ mã hóa dữ liệu mới, không biến dữ liệu cũ sang key version mới.

### 6.2. Kiểm tra trước khi thay đổi khóa

~~~bash
# Chỉ đọc: xem trạng thái các key versions.
gcloud kms keys versions list \
  --key=DATA_KEY \
  --keyring=DATA_RING \
  --location=KMS_LOCATION \
  --project=KMS_PROJECT_ID

# Chỉ đọc: kiểm tra version cụ thể.
gcloud kms keys versions describe KEY_VERSION \
  --key=DATA_KEY \
  --keyring=DATA_RING \
  --location=KMS_LOCATION \
  --project=KMS_PROJECT_ID
~~~

Song song, kiểm tra:

1. Cloud Audit Logs: ai gọi `DisableCryptoKeyVersion`, `DestroyCryptoKeyVersion` hoặc sửa IAM, khi nào?
2. Key usage tracking và tài nguyên nào sử dụng key version; dữ liệu này có thể trễ hoặc chưa đầy đủ.
3. **Service agent** của dịch vụ lưu trữ có quyền `roles/cloudkms.cryptoKeyEncrypterDecrypter` trên key hay không.
4. KMS location có tương thích với resource và region phục hồi không.
5. Với Cloud EKM: external key manager có đang sẵn sàng, cho phép sử dụng key và còn key material không?
6. Có dấu hiệu unauthorized use, key compromise hoặc thay đổi security policy hay chỉ là thao tác vô tình?

Lỗi `PERMISSION_DENIED` không đồng nghĩa key version đang DISABLED. Việc một người dùng có quyền đọc Cloud Storage object cũng không có nghĩa họ cần trực tiếp được cấp quyền giải mã CMEK; thường **service agent** của dịch vụ thực hiện mã hóa/giải mã.

### 6.3. Trường hợp vô hiệu hóa nhầm, không có dấu hiệu tấn công

Khi Security và KMS owner xác nhận đây là thao tác vô tình, trạng thái `DISABLED` có thể được chuyển sang `ENABLED`:

~~~bash
# CHỈ chạy sau khi có approval và đã xác minh KEY_VERSION.
gcloud kms keys versions enable KEY_VERSION \
  --key=DATA_KEY \
  --keyring=DATA_RING \
  --location=KMS_LOCATION \
  --project=KMS_PROJECT_ID
~~~

Sau lệnh, kiểm tra state của version, audit log, quyền service agent và thử một thao tác **đọc** trên tài nguyên test được mã hóa bằng version đó. Không đồng loạt bật lại mọi version cũ nếu chỉ một version liên quan.

Nếu key version đang `DESTROY_SCHEDULED` và **chưa qua deadline**, quy trình là:

~~~bash
# CHỈ chạy sau khi Security/KMS owner phê duyệt.
gcloud kms keys versions restore KEY_VERSION \
  --key=DATA_KEY \
  --keyring=DATA_RING \
  --location=KMS_LOCATION \
  --project=KMS_PROJECT_ID

# Restore đưa version về DISABLED; cần enable riêng.
gcloud kms keys versions enable KEY_VERSION \
  --key=DATA_KEY \
  --keyring=DATA_RING \
  --location=KMS_LOCATION \
  --project=KMS_PROJECT_ID
~~~

Không nhầm `restore key version` với `restore object/backup`. Bước này chỉ khôi phục khả năng dùng key material, **không tự hoàn tác dữ liệu đã bị xóa hoặc mã hóa bởi malware**.

### 6.4. Nếu khóa bị vô hiệu hóa vì nghi ngờ bị lộ

Không tự động enable theo runbook sự cố vận hành. Security phải xác định:

- Khóa có thể bị sử dụng bởi danh tính của kẻ tấn công không?
- Kẻ tấn công còn quyền trên service agent, identity, KMS IAM hoặc dự án backup không?
- Có cần cô lập workload, xoay identity, chặn access, tạo key mới và re-encrypt dữ liệu không?
- Phải giữ lại audit trail, xác nhận các resource dùng phiên bản cũ đã được di chuyển an toàn trước khi disable/destroy?
- Khôi phục tạm thời có an toàn và phù hợp yêu cầu pháp lý không?

Với key **DESTROYED**, đừng khẳng định “backup sẽ cứu được”. Nếu backup còn mã hóa bằng đúng key material đã mất, nó có thể không đọc được. Recovery plan phải chứng minh cả bản sao lưu **và** đường giải mã độc lập tương ứng.

## 7. Kịch bản C: ransomware và tài khoản bị chiếm quyền

Ransomware trong môi trường cloud không nhất thiết chạy như một virus trên VM. Kẻ tấn công có thể lấy credential, gọi API xóa object, ghi nội dung bị mã hóa lên object cũ, tạo khóa/giữ quyền truy cập hoặc phá hủy backup. Có thể kèm **đánh cắp dữ liệu** trước khi mã hóa; chỉ khôi phục dữ liệu không xử lý được nguy cơ exfiltration.

### 7.1. Các bước xử lý bắt buộc

**Phát hiện và xác nhận**

- Xác nhận tín hiệu: object bị thay thế hàng loạt, delete spikes, ransomware note, service account bất thường, IAM policy thay đổi, KMS access lỗi hoặc audit log ngoài lịch.
- Đối chiếu Cloud Audit Logs, Security Command Center findings, Cloud Logging, ứng dụng và các nguồn giám sát độc lập.
- Ghi mốc phát hiện và mốc nghi tấn công bắt đầu bằng UTC; phân biệt “phát hiện lúc 10:00” với “dữ liệu đã bị sửa từ 09:20”.

**Containment có kiểm soát**

- Phối hợp Security đóng hoặc hạn chế các identity và phiên đăng nhập bị xâm phạm; áp dụng phân tách trách nhiệm.
- Ngăn workload nghi bị chiếm quyền tiếp tục ghi/xóa bằng biện pháp đã được phê duyệt, tránh hành động phá bằng chứng.
- Cô lập VM/Pod hoặc network cần thiết; chặn đường đi tiếp của attacker.
- Bảo vệ các backup còn nguyên, key material và project backup khỏi quyền production bị lộ.
- Giữ lại log và image/snapshot phục vụ điều tra theo chính sách của tổ chức; không đưa malware trở lại production.

**Eradication và recovery**

- Điều tra entry point, quyền bị lạm dụng, persistence và dữ liệu có nguy cơ bị truy cập.
- Vá nguyên nhân, xoay credential, thu hẹp IAM; dựng môi trường sạch từ IaC/image được tin cậy.
- Chọn recovery point **trước thời điểm nhiễm/ghi sai**, không chỉ bản backup mới nhất.
- Khôi phục vào vùng/nhánh phục hồi cách ly; chạy integrity checks và các bước đánh giá an toàn.
- Mở traffic theo canary hoặc từng nhóm người dùng khi Security + Data owner phê duyệt.
- Giám sát dấu hiệu tái nhiễm, retry, unusual writes và thay đổi bất thường của backup.

Google Cloud khuyến nghị khôi phục từ **healthy backups**, tái tạo hạ tầng từ CI/CD/IaC đáng tin, kiểm tra lỗ hổng đã bị loại bỏ và cập nhật quy trình giám sát sau sự cố.

### 7.2. Không phục hồi vào vùng vẫn bị attacker kiểm soát

Nếu project production đang bị chiếm quyền, backup restore vào cùng project và dùng cùng service account có thể bị xóa lần nữa. Khi có khả năng, hãy chọn **recovery project**, service identities, VPC và key permissions riêng, với đường nối phục hồi theo least privilege. Tăng quyền trong thời gian ngắn theo approval rồi thu hồi khi xong.

~~~mermaid
flowchart LR
    subgraph Bad["Vùng nghi bị xâm nhập"]
      W["Workload / identity nghi nhiễm"]
      D["Dữ liệu có nguy cơ bị thay đổi"]
    end
    subgraph Vault["Vùng backup được tách quyền"]
      B[("Backup vault / immutable objects")]
      K["Key / KMS authorization"]
    end
    subgraph Clean["Vùng phục hồi cách ly"]
      I["IaC + image đã kiểm chứng"]
      R["Restore vào target mới"]
      T["Malware scan + integrity + nghiệp vụ"]
    end
    W --> D
    B --> R
    K --> R
    I --> R
    R --> T
    T --> A{"Security và owner phê duyệt?"}
    A -->|"Có"| P["Cutover kiểm soát"]
    A -->|"Không"| R
~~~

Trong thực tế, sơ đồ network phải thể hiện project boundary, service agent, egress, private access, KMS, logging, DNS và quyền người vận hành. “Khác project” không tự động có nghĩa sạch nếu sử dụng chung identity đã bị xâm nhập.

### 7.3. Tìm clean recovery point

| Mốc | Ý nghĩa minh họa |
|---|---|
| 08:40 | Bản backup hoàn tất, chưa thấy dấu hiệu compromise |
| 09:10 | Lần đầu có IAM thay đổi bất thường |
| 09:25 | Xuất hiện mass object overwrite |
| 09:40 | Monitoring báo lỗi đọc dữ liệu |
| 09:55 | Security xác nhận sự cố |

Một bản backup tạo lúc **09:30** có thể đã chứa dữ liệu bị thay đổi dù gần hiện tại nhất. Trong ví dụ này, bản **08:40** là *ứng viên* tốt hơn, nhưng vẫn cần kiểm tra hashes, timeline và malware indicators. Nếu không xác minh được điểm an toàn, đừng kết luận “bản mới nhất là sạch”.

### 7.4. Immutable không đồng nghĩa đủ an toàn

Backup vault với enforced retention, Cloud Storage soft delete và Bucket Lock có thể bảo vệ trước hành động xóa. Tuy nhiên:

- Kẻ tấn công vẫn có thể thay đổi dữ liệu **trước lúc backup**.
- Credential phục hồi có thể bị xâm phạm nếu dùng chung với production.
- Thiếu key version hoặc KMS service agent IAM khiến backup có thể không giải mã được.
- Restore có thể tạo chi phí, egress và quota contention lớn.
- Một số hệ thống cần transaction reconciliation, replay event hoặc restore metadata/secret ở bước riêng.

Hãy kiểm tra quy trình restore định kỳ, bao gồm việc dựng target mới và xác nhận database/query/app health, thay vì chỉ kiểm tra ngày tạo backup.

## 8. Bảo vệ backup và khóa trước sự cố

### 8.1. Phân tách quyền quản trị

| Asset | Bảo vệ khuyến nghị |
|---|---|
| Project production | Workload runtime không có quyền xóa backup hoặc sửa retention |
| Backup project/vault | Nhóm riêng quản trị; có enforced retention phù hợp |
| KMS project | Quyền quản lý key tách khỏi quyền sử dụng; audit và approval |
| Restore identity | Tài khoản chuyên dụng hoặc temporary elevation; ghi audit |
| Cloud Storage retention | Cấu hình trước khi có sự cố, hạn chế người được thay đổi |
| IaC/artifact | Repository bảo vệ branch, ký artifact, giữ bản release đã kiểm thử |
| Log/evidence | Giới hạn quyền xóa log, thời hạn retention và nơi lưu phù hợp |

Với Cloud Storage **Bucket Lock**, khóa retention là quyết định không thể thu hồi; không áp dụng tùy tiện cho bucket tạm hoặc log ngắn hạn. Với Object Versioning, noncurrent versions vẫn có thể bị xóa theo policy; cần đặt lifecycle và soft delete theo mục tiêu recovery, không coi versioning là immutable backup.

### 8.2. Kiểm soát lifecycle và key destruction

- Bật cảnh báo cho các thay đổi IAM, backup plan, key version state, bucket soft delete policy và retention.
- Trước khi destroy key, kiểm tra key usage, backup retention, encryption dependency và khả năng re-encrypt.
- Ghi danh sách key/resource mapping: một backup có thể cần key tại project/region khác.
- Với Cloud EKM, phục hồi phụ thuộc cả key association tại Google Cloud lẫn availability/permission ở external key manager.
- Đừng đồng nhất retention với RPO: retention giữ các điểm phục hồi trong một khoảng thời gian, còn **RPO** là mức độ mất dữ liệu chấp nhận; chúng liên quan nhưng không giống nhau. Đặt backup frequency, WAL retention và retention policy tách biệt.
- Kiểm tra chi phí của versioning, soft delete, backup vault và khóa không còn hoạt động; retention dài tạo thêm chi phí lưu trữ.

### 8.3. Test backup bằng restore thật

Một báo cáo “backup success” chỉ cho biết tác vụ backup hoàn tất theo dịch vụ. Chưa chứng minh rằng:

- Có thể tìm được bản backup phù hợp.
- Service agent và người thực hiện có quyền restore.
- Key version cần thiết còn giải mã được.
- Region/location của restore target tương thích.
- Dữ liệu ứng dụng nhất quán với logs/message queues.
- SLO, RTO và RPO đạt theo nhu cầu kinh doanh.

Mỗi quý hoặc theo rủi ro, chạy restore drill trong môi trường cô lập; đánh giá cả đường phục hồi bị lỗi key, thiếu IAM và quota không đủ.

## 9. Ví dụ thực hành an toàn trong môi trường lab

**Không thử bằng cách xóa hoặc sửa dữ liệu production.** Sử dụng project/bucket test tách biệt, dữ liệu giả và ngân sách nhỏ; trước khi thao tác, xem cấu hình soft delete trên bucket lab.

### Bài 1 — Khôi phục một object giả lập bị xóa

1. Tạo bucket test đã bật soft delete theo hướng dẫn Cloud Storage trong project lab được cấp phép.
2. Upload một JSON giả, ghi nhận tên object, generation, checksum và thời điểm.
3. Người hướng dẫn được ủy quyền xóa **chính object test** để mô phỏng xóa nhầm.
4. Liệt kê phiên bản soft-deleted và chọn generation đúng.
5. Chạy `gcloud storage restore` cho generation sau khi kiểm tra không ghi đè object sống.
6. Đọc object đã phục hồi, so sánh checksum và kiểm tra metadata.
7. Ghi thời gian từ phát hiện đến lúc xác minh, phí sử dụng và IAM cần thiết.

Bài thực hành không yêu cầu malware thật hoặc tạo sự cố trên tài nguyên chung.

### Bài 2 — Phân tích state của một test key, không phá dữ liệu thật

1. Dùng một Cloud KMS key version riêng cho lab, mã hóa dữ liệu giả.
2. Đọc key state bằng `gcloud kms keys versions describe`.
3. Thảo luận về điều gì xảy ra nếu key bị `DISABLED` hoặc `DESTROY_SCHEDULED`.
4. Chỉ trong lab được phê duyệt, thao tác disable/enable hoặc schedule/restore với data test; không thực hành destroy hoàn tất.
5. Xác minh luồng state `DESTROY_SCHEDULED → DISABLED → ENABLED`, IAM và log.
6. Viết runbook riêng cho trường hợp security nghi ngờ key compromise; chỉ Security mới quyết định việc bật lại.

### Bài 3 — Tabletop ransomware, không chạy mã độc

Cho các nhóm bốn vai: Incident Commander, Security, Data owner và Recovery operator. Mỗi nhóm nhận timeline giả định cùng các bản backup có mốc trước/sau compromised time.

Yêu cầu:

- Chọn bước containment và evidence phù hợp.
- Liệt kê các identity, project, storage location và key dependencies cần kiểm tra.
- Chọn recovery point và giải thích vì sao nó **có thể sạch**.
- Đề xuất môi trường restore cách ly và bài kiểm tra trước cutover.
- Tính RPO/RTO từ timestamps; nêu chi phí và rủi ro dữ liệu mất.
- Trình bày quyết định “restore/đợi thêm” với lý do và người phê duyệt.

## 10. Đo RPO, RTO và chất lượng phục hồi

**RPO (Recovery Point Objective):** mức mất dữ liệu theo thời gian tối đa có thể chấp nhận. **RTO (Recovery Time Objective):** thời gian tối đa mong muốn để khôi phục dịch vụ sau sự cố, theo định nghĩa điểm bắt đầu/kết thúc rõ.

Ví dụ thời gian giả định:

| Mốc UTC | Sự kiện |
|---|---|
| 09:50 | Recovery point sạch gần nhất được xác minh |
| 10:00 | Sự cố ghi sai dữ liệu bắt đầu |
| 10:12 | Hệ thống phát hiện và kích hoạt incident |
| 11:20 | Ứng dụng phục hồi, kiểm tra nghiệp vụ và mở traffic thành công |

Với định nghĩa thời điểm ảnh hưởng là **10:00**, tổ chức mất tối đa khoảng **10 phút dữ liệu** nếu chỉ khôi phục tại 09:50; **RPO đạt thực tế ≈ 10 phút** trong ví dụ. Nếu tính RTO từ lúc sự cố **10:00** đến lúc phục vụ lại **11:20**, **RTO đạt thực tế ≈ 80 phút**. Đừng lấy thời điểm phát hiện 10:12 để rút RTO trừ khi tiêu chuẩn vận hành đã định nghĩa rõ mốc này.

~~~text
Actual data loss window = Incident time - Last verified clean recovery point
Actual service recovery  = Verified service restore time - Incident start time
~~~

Với ransomware, “last clean point” có thể sớm hơn nhiều so với backup mới nhất. Nếu không xác định được lúc attacker bắt đầu thay đổi dữ liệu, ghi **unknown** hoặc khoảng bất định thay vì công bố RPO chính xác giả tạo.

### 10.1. Kiểm thử sau restore theo lớp

| Lớp kiểm tra | Cách kiểm tra | Điều kiện pass |
|---|---|---|
| Backup artifact | Backup đúng nguồn, mốc và generation | Có bằng chứng, hash/metadata nhất quán |
| Giải mã | Key version/service agent hợp lệ | Đọc thử thành công, không tăng quyền quá mức |
| Cơ sở dữ liệu | Schema, rows, consistency, constraints | Không có corruption hoặc thiếu dữ liệu ngoài RPO đã chấp thuận |
| Ứng dụng | Health, smoke test, critical user journeys | SLI thành công theo ngưỡng định trước |
| Asynchronous events | Queue, outbox, retry/idempotency | Không tạo sự kiện trùng hoặc mất message không được chấp thuận |
| Security | Không còn IOC/persistence, IAM đã khôi phục | Security lead chấp thuận mở traffic |
| Operations | Logs, metrics, alerts, backup job mới | Đã sẵn sàng trực, giám sát và rollback |
| Business | Đối soát giao dịch, dữ liệu khách hàng | Data/business owner ký xác nhận |

Trên GKE, có thể dùng Backup for GKE để phục hồi Kubernetes resources vào target cluster, nhưng việc tạo lại resource chưa chắc khiến workload hoạt động ngay; scheduler, network, volumes, IAM và application readiness phải tự hội tụ. Với Compute Engine, tạo disk/VM mới từ snapshot còn khả dụng và kiểm tra dữ liệu trước khi chuyển workload; không giả định snapshot luôn chứa trạng thái nhất quán của database nếu không có application-aware quiescing.

## 11. Nhật ký và bằng chứng cần giữ

Tùy dịch vụ và chính sách, nguồn dữ liệu điều tra gồm:

- **Cloud Audit Logs:** thao tác xóa object/instance, đổi IAM, thay retention, KMS key version state.
- **Cloud Logging và Error Reporting:** lỗi ứng dụng, 403/permission failures, decrypt errors, retry spikes.
- **Security Command Center:** findings về cấu hình và hành vi bất thường nếu đã bật tính năng tương ứng.
- **Cloud Monitoring:** đột biến lỗi, throughput, CPU, số connection, latency và backup health.
- **Backup and DR / Cloud SQL backup reports:** backup plan, retention, bản phục hồi đã chọn, kết quả restore.
- **Access/activity logs của tổ chức:** identity provider, CI/CD, PAM/break-glass approvals.
- **Forensic evidence:** snapshot/disk image/log bảo toàn theo chain of custody khi cần điều tra bảo mật.

Có thể dùng Cloud Logging query làm bước khởi đầu, sau đó lọc theo resource type, project và time window của sự cố. Các loại log khác nhau có thể yêu cầu Data Access audit logging được bật trước, và có chi phí/lưu giữ riêng; **không giả định tất cả API call đều được ghi đầy đủ theo mặc định**.

### 11.1. Mẫu nhật ký phục hồi

~~~yaml
incident_id: INC-EXAMPLE-2026-001
resource: "Cloud Storage orders object"
root_cause: "accidental delete, chưa có bằng chứng compromise"
evidence:
  - "audit log event reference"
  - "generation list before restore"
recovery_point: "object generation đã được Data owner duyệt"
restore_target: "isolated lab prefix / approved destination"
approvals:
  - "Security: approved"
  - "Data owner: approved"
actual_rpo_minutes: 10
actual_rto_minutes: 80
validation:
  checksum: passed
  application_smoke: passed
  reconciliation: pending
next_review: "Ngày/giờ theo quy trình"
~~~

Đừng ghi `passed` nếu chưa thực sự thực hiện. Nếu còn đối soát pending, chỉ mở traffic theo điều kiện và mức rủi ro đã được phê duyệt.

## 12. Phối hợp DR với phục hồi khóa

Một thiết kế backup mã hóa có ít nhất ba phụ thuộc:

1. **Bản backup/ciphertext còn nguyên và nằm trong retention.**
2. **Key version đúng vẫn có thể dùng**, hoặc có cơ chế quản lý/import gốc đã được kiểm chứng.
3. **Đúng service agent và identity** có quyền tương tác với key và restore target.

Không thay đổi Cloud KMS IAM trong quá trình restore nếu chưa xác định đâu là quyền cần cho nguồn và đích. Với Cloud SQL cross-region restore và CMEK, có thể cần key **ở region đích** cho instance được tạo; đồng thời bản backup nguồn có thể vẫn phụ thuộc khả năng giải mã bằng key của nguồn. Kiểm tra hướng dẫn dịch vụ theo loại backup và region; không coi “đặt key mới” là lời giải cho mất key cũ.

### Bài tập phụ thuộc khóa

Giả sử backup Cloud SQL được tạo lúc 09:50, dùng một key version đang `DISABLED` và service agent vẫn còn quyền KMS. Nếu không có dấu hiệu tấn công, quy trình có thể là: xác nhận version → phê duyệt enable → kiểm tra đọc backup → tạo instance mới → restore → verify.

Nếu cùng key version đã `DESTROYED`, quy trình trên không còn là lựa chọn mặc định. Nếu backup được mã hóa bằng key khác và bản sao độc lập vẫn tồn tại, có thể đánh giá đường phục hồi khác; nếu không, người xử lý phải báo rõ giới hạn, không cam kết dữ liệu cứu được.

## 13. Xử lý các sai lầm phổ biến

| Sai lầm | Hậu quả | Hướng khắc phục |
|---|---|---|
| Restore ngay khi vừa thấy lỗi | Ghi đè dữ liệu tốt, làm hỏng chứng cứ | Phân loại sự cố, chọn restore target cách ly |
| Chọn backup mới nhất khi nghi ransomware | Có thể restore lại malware hoặc dữ liệu bị sửa | Xác minh clean point theo timeline và IOC |
| Đồng nhất soft delete với versioning | Thiếu protection cho xóa bucket | Kiểm tra soft delete/retention, versioning chỉ là lớp bổ sung |
| Không kiểm tra generation | Restore nhầm bản hoặc ghi đè object sống | Dùng generation cụ thể, kiểm tra hash và metadata |
| PITR “trả database về chỗ cũ” | Hiểu sai semantics, gây cutover lỗi | PITR Cloud SQL tạo instance mới; thiết kế routing/validation |
| Nghĩ có backup là chắc chắn phục hồi | Key material/IAM/quota/region có thể chặn | Diễn tập restore với đúng đường giải mã |
| Enable KMS key ngay khi có nghi ngờ compromise | Có thể cấp lại quyền đọc cho attacker | Security phê duyệt, thu hồi quyền xấu trước |
| Tạo key mới rồi xóa version cũ | Dữ liệu cũ không giải mã được | Giữ version cần thiết, re-encrypt có kiểm chứng |
| Cấp Owner để “restore cho nhanh” | Mở rộng blast radius và quyền tấn công | Least privilege, temporary elevation và audit |
| Đưa backup vào cùng identity bị lộ | Bản phục hồi tiếp tục bị phá | Tách project/quyền, vùng phục hồi sạch |
| Bỏ qua message/outbox reconciliation | Tạo trùng đơn hoặc mất sự kiện | Soát transaction, replay idempotent |
| Chỉ test availability, không test dữ liệu | API trả 200 dù dữ liệu sai | Test critical user journeys, hash và đối soát |
| Retention dài mà không tính giá | Chi phí backup tăng khó kiểm soát | Chính sách dữ liệu theo RPO/retention/compliance |
| Không lưu evidence, người phê duyệt | Khó điều tra và audit | Incident record, approvals, timestamps, links |

## 14. Checklist phòng ngừa và sẵn sàng khôi phục

**Trước sự cố**

- [ ] Có inventory data assets, backup location, owner và độ quan trọng.
- [ ] RPO/RTO được business owner phê duyệt, có phép đo và DR test định kỳ.
- [ ] Cloud Storage soft delete/retention và phiên bản dữ liệu được thiết kế đúng.
- [ ] Cloud SQL backup/PITR được bật rõ ràng, có chính sách giữ backup sau xóa khi cần.
- [ ] Backup and DR vault có quyền tách biệt và retention cưỡng chế nếu use case phù hợp.
- [ ] Key/resource/backup dependency mapping được cập nhật sau key rotation.
- [ ] Mọi backup quan trọng đã từng được restore thử trên target mới.
- [ ] Có audit logs, monitoring và cảnh báo xóa hàng loạt, sửa IAM/KMS/retention.
- [ ] Có recovery project, tài khoản break-glass và runbook được kiểm soát.
- [ ] Có quy trình bảo vệ bằng chứng và xử lý malware/exfiltration.

**Khi xảy ra sự cố**

- [ ] Kích hoạt incident commander và Security khi có dấu hiệu compromise.
- [ ] Xác định mốc bắt đầu, thời điểm phát hiện, tài nguyên và project bị ảnh hưởng.
- [ ] Bảo toàn logs, snapshots và bằng chứng theo chính sách.
- [ ] Xác minh backup/soft delete/PITR window **trước khi hết hạn**.
- [ ] Xác minh đúng key version, key state, IAM/service agent và region.
- [ ] Có phê duyệt trước khi restore đè, enable key hoặc đổi production endpoint.
- [ ] Khôi phục vào target cách ly và kiểm tra sạch/an toàn.
- [ ] Chạy integrity, business reconciliation và smoke test.
- [ ] Ghi actual RPO/RTO, chi phí và residual risk.
- [ ] Chỉ cutover theo phê duyệt; theo dõi dấu hiệu tái diễn.
- [ ] Cập nhật runbook, backup protection và threat detection sau postmortem.

## 15. Tự kiểm tra

1. Vì sao object nằm trong Cloud Storage bucket có Object Versioning vẫn có thể mất khi cả bucket bị xóa?
2. Khi restore soft-deleted object, vai trò của generation number là gì?
3. Khôi phục một bucket bị soft-delete bằng gcloud có tự khôi phục tất cả object trong đó không?
4. Khác biệt giữa restore Cloud SQL backup lên instance hiện có và PITR là gì?
5. Cloud KMS key version `DISABLED` khác `DESTROYED` ở đâu?
6. Key đang `DESTROY_SCHEDULED` cần thực hiện những bước gì để dùng lại?
7. Vì sao một backup tồn tại nhưng vẫn có thể không giải mã được?
8. Vì sao ransomware cần chọn bản backup sạch thay vì bản gần nhất?
9. Backup vault có enforced retention có loại bỏ nhu cầu phân quyền IAM và diễn tập khôi phục không?
10. Trong ví dụ 10:00 xảy ra sự cố, 09:50 là recovery point sạch, 11:20 dịch vụ hoạt động lại, actual RPO và RTO là bao nhiêu?
11. Khi khôi phục đơn hàng và outbox, điều gì có thể xảy ra nếu phát lại Pub/Sub message không có idempotency?
12. Khi nào phải ưu tiên Security phê duyệt trước khi enable lại CMEK?

**Gợi ý đáp án**

1. Versioning giữ các bản noncurrent trong bucket, không bảo vệ khỏi việc xóa toàn bucket; soft delete bucket/backup độc lập phù hợp hơn cho trường hợp này.
2. Generation định danh đúng bản object đã bị xóa; tránh khôi phục nhầm hoặc ảnh hưởng bản live mới.
3. Không. CLI/API restore bucket trả lại bucket; objects cần restore riêng. Console có luồng chọn restore objects.
4. Restore backup lên instance hiện có có thể ghi đè dữ liệu đích; PITR tạo instance mới tại timestamp trong recovery window.
5. DISABLED còn key material và có thể enable lại; DESTROYED đã mất key material và thông thường không thể phục hồi.
6. Restore version khi còn trong scheduled destruction window → version trở về DISABLED → enable sau khi có phê duyệt.
7. Có thể thiếu CMEK version, quyền KMS của service agent, EKM availability hoặc ràng buộc region.
8. Backup gần nhất có thể chứa dữ liệu đã bị sửa/mã hóa; cần xác minh điểm sạch trước thời điểm compromise.
9. Không. Vault giữ backup khỏi xóa trong retention nhưng không tự chứng minh backup sạch, IAM đúng hoặc key còn đọc được.
10. Theo mốc đầu sự cố 10:00, actual RPO khoảng 10 phút, actual RTO khoảng 80 phút.
11. Có thể nhân đôi xử lý, tạo hai giao dịch hoặc gửi thông báo/trừ tiền lặp; cần idempotency và reconciliation.
12. Khi có dấu hiệu credential compromise, exfiltration, thay IAM trái phép hoặc key đã bị disable để containment.

## Kết luận

Phục hồi hiệu quả không bắt đầu từ lệnh restore mà từ việc **xác định đúng nguyên nhân, bảo vệ những dữ liệu còn lành, chọn điểm khôi phục có thể giải mã và xác minh trạng thái sạch trước khi mở dịch vụ trở lại**. Xóa nhầm có thể xử lý bằng soft delete/versioning hoặc backup; Cloud KMS DISABLED có thể enable có kiểm soát nhưng DESTROYED có thể khiến dữ liệu không thể đọc; ransomware đòi hỏi điều tra và tái tạo môi trường sạch trước khi dùng bản backup. Dù sử dụng dịch vụ managed nào, tổ chức vẫn cần phân tách quyền, DR drills, RPO/RTO đo được và một người chịu trách nhiệm cho quyết định cutover.

## Tài liệu tham khảo

- [Google Cloud Storage — Soft delete overview](https://docs.cloud.google.com/storage/docs/soft-delete)
- [Google Cloud Storage — Use soft-deleted objects](https://docs.cloud.google.com/storage/docs/use-soft-deleted-objects)
- [Google Cloud Storage — Use soft-deleted buckets](https://docs.cloud.google.com/storage/docs/use-soft-deleted-buckets)
- [Google Cloud Storage — Object Versioning](https://docs.cloud.google.com/storage/docs/object-versioning)
- [Google Cloud Storage — Bucket Lock](https://docs.cloud.google.com/storage/docs/bucket-lock)
- [Google Cloud SQL PostgreSQL — Backup and recovery](https://docs.cloud.google.com/sql/docs/postgres/backup-recovery/backups)
- [Google Cloud SQL PostgreSQL — Restore an instance](https://docs.cloud.google.com/sql/docs/postgres/backup-recovery/restoring)
- [Google Cloud SQL PostgreSQL — Point-in-time recovery](https://docs.cloud.google.com/sql/docs/postgres/backup-recovery/pitr)
- [Google Cloud SQL PostgreSQL — Delete instances and recovery](https://docs.cloud.google.com/sql/docs/postgres/delete-instance)
- [Google Cloud KMS — Enable and disable key versions](https://docs.cloud.google.com/kms/docs/enable-disable)
- [Google Cloud KMS — Destroy and restore key versions](https://docs.cloud.google.com/kms/docs/destroy-restore)
- [Google Cloud KMS — Key version states](https://docs.cloud.google.com/kms/docs/key-states)
- [Google Cloud KMS — Customer-managed encryption keys](https://docs.cloud.google.com/kms/docs/cmek)
- [Backup and DR — Backup vault overview](https://docs.cloud.google.com/backup-disaster-recovery/docs/concepts/backup-vault)
- [Backup for GKE — Restore from backup](https://docs.cloud.google.com/kubernetes-engine/docs/add-on/backup-for-gke/how-to/restore)
- [Google Cloud Security — Mitigate ransomware attacks](https://docs.cloud.google.com/docs/security/mitigating-ransomware-attacks)

