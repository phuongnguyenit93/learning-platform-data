# Snapshots, instant snapshots và lịch chụp đĩa trong Google Cloud

Một VM Compute Engine có thể chạy ứng dụng Java, lưu thư mục upload, chỉ mục tìm kiếm hoặc dữ liệu tạm trên Persistent Disk hoặc Hyperdisk. Nếu một bản cập nhật ứng dụng ghi hỏng dữ liệu, một quản trị viên xóa nhầm tệp hay cả zone gặp sự cố, đội vận hành cần **phục hồi trạng thái dữ liệu tại một thời điểm đã biết**. Compute Engine cung cấp nhiều cách bảo vệ dữ liệu đĩa, trong đó quan trọng là **standard snapshots**, **instant snapshots** và **snapshot schedules**.

Ba cơ chế này không tương đương nhau:

- **Standard snapshot** lưu bản chụp dữ liệu đĩa bên ngoài vị trí đĩa nguồn theo nơi lưu trữ đã chọn; phù hợp sao lưu dài hơn và phục hồi sau hỏng vùng/zone theo thiết kế.
- **Instant snapshot** tạo điểm phục hồi nhanh **ở cùng zone hoặc region với đĩa nguồn**; tối ưu cho khôi phục nhanh sau lỗi thao tác hay cập nhật phần mềm, nhưng không thay thế backup ngoài vị trí.
- **Snapshot schedule** là một **resource policy** chạy tự động theo giờ/ngày/tuần để tạo **standard snapshots**; **không tạo instant snapshots**.

Bài học thuộc chương **Lưu trữ khối và tệp** của mô-đun `CLOUD_PROVIDERS_GCP`. Trong quá trình học tổ chức project, IAM, VPC, Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ, cơ sở dữ liệu và tự động hóa phát hành, việc chọn giải pháp sao lưu phải gắn với **bảo vệ dữ liệu, tính sẵn sàng, khôi phục có kiểm chứng và kiểm soát chi phí**.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **đĩa nguồn**, **standard snapshot**, **archive snapshot**, **instant snapshot** và **snapshot schedule**.
2. Giải thích tính **incremental**, **crash consistency**, **application consistency** và khác biệt về RPO/RTO.
3. Chọn nơi lưu standard snapshot phù hợp với rủi ro zone/region, độ trễ phục hồi, chi phí và ràng buộc dữ liệu.
4. Tạo và phục hồi standard snapshot, instant snapshot bằng Google Cloud Console hoặc `gcloud`.
5. Tạo, gắn và kiểm tra snapshot schedule, cấu hình tần suất, retention và hành vi khi xóa đĩa nguồn.
6. Nhận biết các giới hạn quan trọng của instant snapshots: không dùng schedule, bị xóa cùng đĩa nguồn, chỉ truy cập trong vị trí nguồn.
7. Thiết kế bài thực hành phục hồi mà không ghi đè đĩa production, đồng thời xác nhận dữ liệu phục hồi đúng.
8. Giám sát snapshot failures, bảo vệ IAM/CMEK, lập chính sách vòng đời và dự báo chi phí.

## 1. Bài toán thực tế: phục hồi sau khi dữ liệu trên VM bị hỏng

Giả sử nhóm Commerce có ứng dụng Java `orders-worker` trên VM Compute Engine. VM có:

- Boot disk: hệ điều hành và cấu hình chạy dịch vụ.
- Data disk `orders-data`: dữ liệu xử lý và một số file nghiệp vụ.
- Cloud SQL: cơ sở dữ liệu giao dịch chính, được quản lý bằng cơ chế sao lưu riêng.
- Cloud Storage: lưu object dài hạn.

Trước một bản nâng cấp có nguy cơ thay đổi cấu trúc file, nhóm muốn một điểm phục hồi trong vài phút nếu nâng cấp thất bại. Đồng thời, nhóm cần bản sao dữ liệu **không bị mất khi zone của VM ngừng hoạt động**.

~~~mermaid
flowchart LR
    VM["Compute Engine VM<br/>orders-worker"]
    DISK["Persistent Disk<br/>orders-data"]
    INSTANT["Instant snapshot<br/>cùng zone với đĩa"]
    STANDARD["Standard snapshot<br/>nơi lưu do chính sách chọn"]
    RECOVER["Disk mới phục hồi<br/>gắn VM kiểm thử"]
    DR["Disk mới tại zone/region phù hợp<br/>theo khả năng khôi phục"]
    VM --> DISK
    DISK -->|"Trước khi nâng cấp"| INSTANT
    DISK -->|"Theo lịch / thủ công"| STANDARD
    INSTANT -->|"Khôi phục nhanh"| RECOVER
    STANDARD -->|"Phục hồi ngoài vị trí nguồn"| DR
~~~

**Thiết kế hợp lý là dùng nhiều lớp**: instant snapshot cho rollback nhanh tại chỗ, standard snapshot theo lịch cho lịch sử phục hồi và khả năng phục hồi rộng hơn. Nếu workload có dữ liệu nghiệp vụ quan trọng, còn cần cơ chế đảm bảo tính nhất quán ứng dụng, sao lưu database và kiểm thử restore.

## 2. Hiểu khái niệm snapshot và sự khác nhau giữa các loại

Snapshot lưu **trạng thái dữ liệu của một disk tại một thời điểm**; nó không phải là một VM đang chạy, cũng không chứa đầy đủ mọi tài nguyên hạ tầng liên quan đến VM.

| Tiêu chí | Standard snapshot | Instant snapshot | Archive snapshot |
| --- | --- | --- | --- |
| Mục đích nổi bật | Backup thường xuyên, phục hồi sau sự cố | Khôi phục đĩa nhanh tại chỗ | Lưu trữ ít truy cập trong thời gian dài |
| Vị trí dữ liệu | Lưu ngoài đĩa nguồn tại region/multi-region đã chọn | **Cùng zone hoặc region** với đĩa nguồn | Lưu ngoài đĩa nguồn |
| Bảo vệ khi xóa đĩa nguồn | **Vẫn tồn tại** | **Bị xóa cùng đĩa nguồn** | **Vẫn tồn tại** |
| Phục hồi khi mất toàn zone | Có thể, nếu vị trí lưu và quyền truy cập còn khả dụng | **Không** bảo đảm | Có thể, theo vị trí lưu và điều kiện phục hồi |
| Thời gian tạo đĩa phục hồi | Phù hợp backup/DR, thường chậm hơn instant | Tối ưu khôi phục nhanh | Thường chậm nhất |
| Tạo bằng snapshot schedule | **Có** | **Không** | **Không** |
| Tính nhất quán | Crash-consistent mặc định; có cách tạo application-consistent khi hỗ trợ | **Crash-consistent**, không hỗ trợ application-consistent theo cách của standard | Theo quy trình snapshot có hỗ trợ |
| Chi phí | Theo dung lượng dữ liệu lưu và các khoản liên quan | Theo cơ chế/lưu trữ instant snapshot | Giá lưu trữ có thể thấp hơn, cần đánh giá chi phí phục hồi |

Các tính năng và loại đĩa được hỗ trợ có thể thay đổi. Một số Hyperdisk không hỗ trợ instant snapshots; xem tài liệu **About instant snapshots** ở cuối bài trước khi chọn loại máy/đĩa.

### 2.1. Không nhầm với disk image hoặc backup ứng dụng

- **Custom image** thường phù hợp đóng gói boot disk hoặc golden image để tạo máy mới, không thay lịch backup dữ liệu thay đổi thường xuyên.
- **Disk clone** tạo bản sao đĩa phục vụ một số tác vụ nhân bản; không phải chiến lược backup off-site mặc định.
- **Database-native backup**, chẳng hạn các cơ chế backup/PITR của Cloud SQL hoặc dump/backup ứng dụng, bảo vệ mức logic và giao dịch mà snapshot khối không tự bảo đảm.
- **Cloud Storage Object Versioning** phục vụ phiên bản object; không phải snapshot của Persistent Disk.
- **Filestore snapshots/backups** là cơ chế riêng của dịch vụ file NFS, không dùng lệnh `gcloud compute snapshots` để thao tác trực tiếp lên Filestore.

## 3. Standard snapshots: bản sao tăng dần và khôi phục linh hoạt

Standard snapshots của Persistent Disk/Hyperdisk hỗ trợ cơ chế **incremental**: các lần chụp tiếp theo chủ yếu theo dõi những khối dữ liệu đã thay đổi kể từ điểm trước đó. Người dùng vẫn có thể phục hồi từ một snapshot hợp lệ như một điểm chụp độc lập ở mức trải nghiệm; Compute Engine xử lý chuỗi khối dữ liệu nền.

~~~mermaid
flowchart LR
    D["Disk đang thay đổi"]
    S1["Snapshot S1<br/>baseline"]
    S2["Snapshot S2<br/>các khối mới/đổi"]
    S3["Snapshot S3<br/>các khối mới/đổi"]
    R["Disk phục hồi<br/>trạng thái tại S3"]
    D --> S1 --> S2 --> S3
    S3 --> R
~~~

**Không tự suy ra rằng xóa S1 sẽ làm S2/S3 mất khả năng phục hồi.** Dịch vụ quản lý các khối dữ liệu chung để những snapshot còn hợp lệ vẫn khôi phục được. Tuy nhiên, khi xóa một snapshot, dung lượng tính phí không nhất thiết giảm bằng dung lượng hiển thị của riêng snapshot đó, vì các khối dữ liệu có thể vẫn được bản chụp khác tham chiếu.

### 3.1. Một snapshot mới có thể lấy khi VM đang chạy

Compute Engine cho phép tạo standard snapshot khi đĩa đang gắn với VM chạy. Tuy nhiên, việc chụp dữ liệu ở mức block **không có nghĩa ứng dụng đã ghi hết transaction trong memory** xuống disk. Với database, message queue hoặc file đang cập nhật, cần thiết kế nhất quán ứng dụng riêng.

### 3.2. Nơi lưu snapshot và phạm vi có thể dùng

Standard snapshots thường có **global scope theo mô hình mặc định**, nhưng dữ liệu được lưu ở **region hoặc multi-region** do cấu hình chọn. Hai ý này khác nhau:

- **Resource scope** mô tả cách nhận diện/tận dụng snapshot trong Compute Engine API.
- **Storage location** mô tả vị trí vật lý/logical nơi dữ liệu backup được lưu để đáp ứng residency, availability và chi phí.
- Tính năng **regionally scoped snapshots** có thể ở trạng thái Preview hoặc có giới hạn riêng; không áp dụng cú pháp đó cho mọi project khi chưa kiểm tra điều kiện.

Ví dụ: disk ở `asia-southeast1-b` được sao lưu vào một **multi-region** được tổ chức phê duyệt, để tránh phụ thuộc duy nhất vào region nguồn. Nếu chọn chỉ lưu standard snapshot trong **cùng một region** với disk, dữ liệu backup có mức dư thừa trong region đó, nhưng không nên coi đó là biện pháp chắc chắn chịu được **mất toàn region**.

### 3.3. Chọn location theo mục tiêu

| Mục tiêu | Quyết định |
| --- | --- |
| Phục hồi khi một zone mất | Snapshot phải độc lập với zone nguồn, restore vào zone khả dụng |
| Phục hồi khi region nguồn gián đoạn | Chọn snapshot storage location phù hợp đa vùng/ngoài region nguồn, kiểm tra quyền và target region |
| Dữ liệu phải ở khu vực được phê duyệt | Dùng location đáp ứng policy và ràng buộc residency |
| Tối ưu thời gian/chi phí truyền dữ liệu | Cân nhắc vị trí snapshot gần workload nhưng không đánh đổi sai mức bảo vệ |
| Phải chia sẻ snapshot giữa project | Phân quyền và kiểm tra restrictions của resource/snapshot scope |

**Kế hoạch DR thực tế** cần kiểm thử tạo disk, gắn VM và chạy ứng dụng tại **destination zone/region**, chứ không chỉ xác nhận snapshot tồn tại.

## 4. Instant snapshots: khôi phục nhanh nhưng không phải backup off-site

**Instant snapshot** là bản chụp dữ liệu đĩa tại chỗ, tối ưu cho việc tạo **một disk mới nhanh chóng** khi người vận hành muốn khôi phục trạng thái trước thay đổi.

~~~mermaid
flowchart TD
    D["Disk nguồn trong zone b"] --> I["Instant snapshot I1<br/>cũng ở zone b"]
    I --> N["Tạo disk phục hồi mới<br/>ở vị trí được hỗ trợ"]
    D -->|"Xóa disk nguồn"| X["Instant snapshot cũng bị xóa"]
    I -. "Không chuyển trực tiếp ra region khác" .-> DR["Cần standard snapshot nếu muốn off-site"]
~~~

Những giới hạn phải nhớ:

1. **Vị trí:** instant snapshot của zonal disk nằm trong cùng zone; của regional disk nằm trong cùng region. Không chọn location khác.
2. **Vòng đời:** xóa disk nguồn sẽ **xóa tất cả instant snapshots** của disk đó, kể cả khi disk bị xóa do xóa VM có auto-delete boot/data disk.
3. **Schedule:** không thể tạo instant snapshots bằng Compute Engine snapshot schedules.
4. **Consistency:** instant snapshot có **crash consistency**, không phải application consistency.
5. **Giới hạn tần suất/số lượng:** tại thời điểm tài liệu này được tham chiếu, tối đa một instant snapshot mỗi **30 giây** từ cùng disk và không quá **32 instant snapshots** mỗi disk.
6. **Hyperdisk:** không hỗ trợ cho mọi loại Hyperdisk; ví dụ Hyperdisk ML và Hyperdisk Throughput không hỗ trợ instant snapshot.
7. **Chuyển vùng hoặc giữ sau khi xóa disk:** tạo **standard snapshot từ instant snapshot** trước khi xóa nguồn.
8. **Boot recovery:** không tạo VM trực tiếp từ instant snapshot của boot disk; trước hết tạo **disk mới** từ instant snapshot rồi dùng disk đó cho VM.
9. **Move disk:** những instant snapshots còn tồn tại có thể ngăn di chuyển disk; đánh giá vòng đời trước khi thực hiện.

### 4.1. Khi nào chọn instant snapshot?

- Ngay trước khi nâng cấp phần mềm có thể thay đổi trạng thái file trên đĩa.
- Trước thao tác hệ thống có thể xóa nhầm dữ liệu.
- Khi cần điểm khôi phục nhanh cho workload trong một zone/region vẫn đang khả dụng.
- Khi chụp nhiều disks như một nhóm theo **consistency group** (nếu tính năng hỗ trợ) để phục hồi dữ liệu có mốc thời gian đồng bộ.

**Không dùng instant snapshots làm bản sao duy nhất cho dữ liệu quan trọng.** Nếu disk nguồn bị xóa hoặc zone/region gặp sự cố, instant snapshot không còn đáp ứng mục tiêu phục hồi.

### 4.2. Consistency group cho nhiều đĩa

Nếu ứng dụng có một disk chứa dữ liệu và một disk chứa transaction log, chụp riêng từng disk vào hai thời điểm khác nhau có thể tạo trạng thái không nhất quán. Compute Engine hỗ trợ tạo **consistency group of instant snapshots** từ một nhóm disk tương ứng trong những cấu hình được hỗ trợ.

Tính năng này giúp có mốc chụp đồng bộ **ở cấp đĩa**, nhưng **không tự bảo đảm dữ liệu giao dịch trong memory đã được ghi và hoàn tất logic ứng dụng**. Nếu mục tiêu là transaction-level consistency, cần cơ chế quiesce/app-native backup hoặc phương án backup nhất quán ứng dụng phù hợp.

## 5. Crash consistency và application consistency

**Crash-consistent snapshot** ghi nhận những khối dữ liệu hiện đã có trên storage như lúc máy bị mất điện. File system có thể journal/replay khi khởi động lại; database có thể cần recovery từ transaction logs. Nhưng dữ liệu chưa flush ra storage không được đưa vào snapshot.

**Application-consistent snapshot** cố gắng đảm bảo ứng dụng flush/ổn định trạng thái trước khi chụp, qua cơ chế guest-flush, VSS hoặc thao tác ứng dụng hỗ trợ.

| Cấp độ | Bảo đảm nổi bật | Giới hạn |
| --- | --- | --- |
| Crash-consistent | Điểm chụp của các khối trên disk | Không bảo đảm mọi transaction/app buffer đã ghi |
| File-system-consistent | File system được quiesce/flush theo cơ chế phù hợp | Chưa chắc database đã flush transaction logic |
| Application-consistent | Ứng dụng/database phối hợp tạo điểm backup nhất quán | Cần logic và kiểm chứng restore của ứng dụng |

### 5.1. Linux và Windows

- Trên **Linux**, Compute Engine hỗ trợ cơ chế tạo **application-consistent standard snapshots** thông qua guest-flush và các script/guest environment thích hợp. Trình tự có thể gồm pre-snapshot action, flush/quiesce, snapshot và post-snapshot action.
- Trên **Windows**, có thể dùng cơ chế **Volume Shadow Copy Service (VSS)** theo hướng dẫn của Google Cloud.
- Nếu snapshot cần ứng dụng phối hợp nhưng guest setup thiếu hoặc script lỗi, không nên coi bản chụp là một backup transaction-consistent.

**Không tự đưa lệnh `fsfreeze` vào cron rồi giả định đủ an toàn**; đóng băng file system sai cách có thể làm treo hoặc gián đoạn ứng dụng. Cần dùng đúng quy trình hỗ trợ, thời gian giới hạn và thử nghiệm phục hồi.

### 5.2. Mục tiêu nhất quán cho dữ liệu nghiệp vụ

Với `orders-worker`:

1. Tạm dừng nhận batch mới khi phù hợp và bảo đảm message queue không mất dữ liệu.
2. Flush những buffer quan trọng xuống disk hoặc tạo checkpoint theo khả năng ứng dụng.
3. Tạo standard snapshot hoặc backup ứng dụng theo quy trình đã thử.
4. Cho workload tiếp tục hoạt động; xác minh snapshot ở trạng thái hoàn tất.
5. Phục hồi thử sang disk/VM khác, chạy kiểm tra dữ liệu và logic nghiệp vụ.

Nếu giao dịch thật nằm trong **Cloud SQL**, hãy dùng **Cloud SQL backup/PITR** theo mục tiêu RPO/RTO; disk snapshot trên VM không thay thế backup nhất quán của cơ sở dữ liệu dịch vụ quản lý.

## 6. RPO và RTO giúp chọn đúng loại snapshot

- **RPO (Recovery Point Objective):** tối đa bao nhiêu thời gian dữ liệu có thể bị mất chấp nhận được.
- **RTO (Recovery Time Objective):** ứng dụng phải hoạt động lại trong bao lâu sau sự cố.

Ví dụ:

| Workload | RPO mục tiêu giả định | RTO mục tiêu giả định | Thiết kế gợi ý |
| --- | --- | --- | --- |
| Thư mục file tạm của batch VM | 24 giờ | 2 giờ | Daily standard snapshot |
| Dữ liệu phiên thử nghiệm trước rollout | Theo lần deploy | 15 phút | Instant snapshot trước nâng cấp + restore rehearsal |
| File tài liệu nghiệp vụ quan trọng | 4 giờ | 1 giờ | Hourly standard snapshot, backup app-consistent khi cần |
| Giao dịch thanh toán | Rất thấp | Rất thấp | Thiết kế database replication/PITR/backup riêng, không chỉ disk snapshot |

Các số trên là **giả định để lập kế hoạch**, không phải SLA cam kết của Google Cloud. RTO thực tế phụ thuộc dung lượng phục hồi, tốc độ tạo disk/VM, tính nhất quán, khả năng ứng dụng khởi động, networking/IAM và thời gian xác minh.

### 6.1. Công thức RPO theo lịch

Nếu daily snapshot chạy mỗi 24 giờ, một sự cố xảy ra ngay trước bản chụp kế tiếp có thể khiến mất **gần 24 giờ dữ liệu**, thậm chí hơn nếu lần chụp trước bị lỗi hoặc trì hoãn.

~~~text
Worst-case RPO dự kiến
  ≈ khoảng thời gian giữa hai bản snapshot thành công
  + độ trễ hoặc các lần snapshot bị lỗi chưa được xử lý
~~~

Giảm interval không đủ nếu backup thất bại mà không có alert, hoặc snapshot tạo xong nhưng không restore được.

## 7. Thực hành chuẩn bị: xác định disk và quyền trước khi chụp

Ví dụ lab dùng:

~~~text
Project: PROJECT_ID
Region: asia-southeast1
Zone: asia-southeast1-b
Disk: lab-orders-data
Standard snapshot: lab-orders-std-001
Instant snapshot: lab-orders-inst-001
Snapshot schedule: lab-orders-daily
Disk khôi phục: lab-orders-restore
~~~

**Các lệnh tạo disk/snapshot có thể phát sinh phí.** Chỉ thực hiện trong project lab đã được phê duyệt, có ngân sách, quyền IAM phù hợp và kế hoạch cleanup; không chạy trên production disk chứa dữ liệu chưa được phép thao tác.

~~~bash
# Chỉ đọc: xác định tài khoản và project trước khi thao tác
gcloud auth list
gcloud config get-value project

# Kiểm tra disk trong zone dự kiến
gcloud compute disks list --project=PROJECT_ID
gcloud compute disks describe lab-orders-data \
  --zone=asia-southeast1-b \
  --project=PROJECT_ID
~~~

Với disk dạng **regional**, những lệnh quản lý disk/snapshot liên quan phải sử dụng `--region` thay cho `--zone` theo API tương ứng. Không nhầm `asia-southeast1` (region) với `asia-southeast1-b` (zone).

### 7.1. IAM cần những quyền nào?

Cách cấp quyền tùy thao tác và phạm vi, nhưng thường liên quan:

- Tạo standard snapshot: quyền chụp disk và tạo snapshot (`compute.disks.createSnapshot`, `compute.snapshots.create` theo tác vụ).
- Tạo instant snapshot: `compute.instantSnapshots.create` và quyền dùng/đọc disk tương ứng.
- Khôi phục: `compute.disks.create` và quyền sử dụng snapshot nguồn (`compute.snapshots.useReadOnly` hoặc `compute.instantSnapshots.useReadOnly`), thêm quyền gắn disk nếu cần.
- Tạo/gắn snapshot schedule: quyền tạo/cập nhật **Compute Engine resource policy** và quyền gắn policy lên disk.
- Gắn disk vào VM: `compute.instances.attachDisk` và `compute.disks.use`.

Dùng vai trò IAM hẹp hoặc custom roles theo quy trình tổ chức. Quyền tạo/đọc snapshot là quyền nhạy cảm vì **snapshot có thể chứa dữ liệu cá nhân, secret hoặc thông tin ứng dụng**. Không cấp vai trò Owner toàn project chỉ để vận hành lịch sao lưu.

## 8. Tạo standard snapshot thủ công

### 8.1. Bằng Google Cloud Console

1. Chọn đúng project, vào **Compute Engine → Snapshots**.
2. Chọn **Create snapshot**, nhập tên và kiểu **Standard**.
3. Chọn **source disk** tương ứng và kiểm tra zone/region.
4. Chọn **storage location** phù hợp yêu cầu residency/DR.
5. Nếu cần application consistency, thực hiện quy trình guest-flush/VSS được tài liệu hỗ trợ trước/trong thao tác.
6. Tạo snapshot, chờ hoàn tất và kiểm tra metadata.

### 8.2. Bằng gcloud

~~~bash
gcloud compute snapshots create lab-orders-std-001 \
  --source-disk=lab-orders-data \
  --source-disk-zone=asia-southeast1-b \
  --snapshot-type=STANDARD \
  --storage-location=asia \
  --project=PROJECT_ID
~~~

Trong ví dụ, `asia` là **multi-region storage location**, khác với zone của disk. Chỉ chọn location được organization policy và yêu cầu quản trị dữ liệu cho phép; nếu không có mục tiêu đa vùng, có thể dùng storage location theo chính sách doanh nghiệp.

Kiểm tra:

~~~bash
gcloud compute snapshots list --project=PROJECT_ID

gcloud compute snapshots describe lab-orders-std-001 \
  --project=PROJECT_ID
~~~

Khi kiểm tra, chú ý trạng thái snapshot, nguồn disk, creation time, location, dung lượng và encryption. **Tạo lệnh thành công không thay thế việc xác minh snapshot đã sẵn sàng để khôi phục.**

### 8.3. Chu kỳ snapshot incremental và giới hạn

Khi nhiều standard snapshots được tạo từ cùng disk, dịch vụ thường chỉ cần lưu các khối mới/đổi. Không nên chạy nhiều snapshot cùng disk đồng thời, và cần tôn trọng giới hạn tần suất. Theo tài liệu Compute Engine, có giới hạn số lần tạo standard snapshot cho một disk trong một cửa sổ 60 phút; không biến lệnh snapshot thủ công thành vòng lặp dày đặc.

## 9. Tạo và phục hồi instant snapshot

### 9.1. Tạo instant snapshot của zonal disk

~~~bash
gcloud compute instant-snapshots create lab-orders-inst-001 \
  --source-disk=lab-orders-data \
  --zone=asia-southeast1-b \
  --project=PROJECT_ID
~~~

Kiểm tra:

~~~bash
gcloud compute instant-snapshots list --project=PROJECT_ID

gcloud compute instant-snapshots describe lab-orders-inst-001 \
  --zone=asia-southeast1-b \
  --project=PROJECT_ID
~~~

Instant snapshot **không có cờ chọn storage location khác**: vị trí của nó gắn với disk nguồn. Nếu disk là **regional disk**, dùng `--region=REGION` theo tài liệu thay vì `--zone`.

### 9.2. Khôi phục vào một disk mới

~~~bash
gcloud compute disks create lab-orders-from-instant \
  --zone=asia-southeast1-b \
  --source-instant-snapshot=lab-orders-inst-001 \
  --project=PROJECT_ID
~~~

Sau khi tạo disk, bạn có thể **gắn vào VM kiểm thử phù hợp** và mount/kiểm tra dữ liệu. Không ghi đè dữ liệu production. Nếu snapshot chứa file system đã mount theo UUID, cần tránh mount nhầm hai disks có cùng filesystem UUID hoặc logical volume identifiers trong cùng VM; có thể dùng VM tách biệt để xác minh.

### 9.3. Cần giữ instant snapshot sau khi xóa disk nguồn?

Bạn không thể chỉ “move” instant snapshot tới region khác. Trước khi xóa disk nguồn, tạo **standard snapshot từ instant snapshot**:

~~~bash
gcloud compute snapshots create lab-orders-inst-export \
  --source-instant-snapshot=lab-orders-inst-001 \
  --source-instant-snapshot-zone=asia-southeast1-b \
  --snapshot-type=STANDARD \
  --storage-location=asia \
  --project=PROJECT_ID
~~~

Kiểm tra standard snapshot mới **đã hoàn thành** trước khi xóa disk nguồn. Việc chuyển đổi này có giới hạn tần suất standard snapshot của disk và có thể phát sinh phí. Nếu disk nguồn đã bị xóa trước khi làm bước này, instant snapshot **không còn tồn tại để chuyển đổi**.

## 10. Phục hồi standard snapshot sang disk/VM mới

### 10.1. Phục hồi vào disk zonal

~~~bash
gcloud compute disks create lab-orders-restore \
  --zone=asia-southeast1-b \
  --source-snapshot=lab-orders-std-001 \
  --type=pd-balanced \
  --project=PROJECT_ID
~~~

Có thể chỉ định `--size` nếu cần, nhưng kích thước disk mới phải **không nhỏ hơn** disk nguồn gắn với snapshot. Chọn disk type hỗ trợ và zone còn tài nguyên/quota thích hợp.

### 10.2. Khôi phục tại zone/region khác

Với **standard snapshot có scope/location cho phép restore**, có thể tạo disk tại một zone khác, ví dụ:

~~~bash
gcloud compute disks create lab-orders-dr-restore \
  --zone=asia-southeast1-a \
  --source-snapshot=lab-orders-std-001 \
  --type=pd-balanced \
  --project=PROJECT_ID
~~~

Khả năng phục hồi đến một region khác còn phụ thuộc **snapshot scope, storage location, allowed access locations, Organization Policy, encryption key và mạng/ứng dụng của đích**. Đừng mặc định mọi tổ hợp region và snapshot đều được cho phép.

### 10.3. Gắn disk vào VM để kiểm tra

~~~bash
# Chỉ khi VM kiểm thử đã tồn tại và nằm cùng zone
gcloud compute instances attach-disk LAB_TEST_VM \
  --disk=lab-orders-restore \
  --zone=asia-southeast1-b \
  --project=PROJECT_ID
~~~

Bên trong VM, kiểm tra `lsblk`, file system, dữ liệu thực và ứng dụng; không mount một disk chứa bản sao dữ liệu nhạy cảm trên VM không được quản trị. Với **boot disk snapshot**, có thể tạo VM hoặc boot disk mới theo quy trình riêng; với **instant snapshot của boot disk**, phải tạo disk trước rồi dùng disk đó làm nguồn boot.

### 10.4. Kiểm chứng phục hồi

Một thử nghiệm restore chỉ đạt khi:

1. Disk mới tạo thành công từ snapshot và có kích thước/loại phù hợp.
2. File system mount được và có thể đọc dữ liệu.
3. Dữ liệu cần thiết tồn tại đúng thời điểm chụp.
4. Ứng dụng chạy và hoàn thành nghiệp vụ thử (ví dụ đọc file, khôi phục bản ghi).
5. Quyền IAM, encryption key, mạng và secret của môi trường khôi phục hoạt động.
6. Thời gian từ lúc bắt đầu sự cố giả lập đến lúc ứng dụng sẵn sàng được đo và so với **RTO**.

## 11. Snapshot schedule: tự động chụp standard snapshots

**Snapshot schedule** là một **regional resource policy** được gắn lên một hoặc nhiều Persistent Disk/Hyperdisk đủ điều kiện. Nó tạo **standard snapshots** theo một tần suất được khai báo: hourly, daily hoặc weekly.

~~~mermaid
flowchart LR
    POL["Resource policy<br/>daily-schedule"]
    D1["Disk orders-data<br/>zone b"]
    D2["Disk reports-data<br/>zone a"]
    S1["Standard snapshots<br/>theo lịch"]
    POL -. "Gắn cùng region" .-> D1
    POL -. "Có thể gắn khi phù hợp" .-> D2
    D1 --> S1
    D2 --> S1
~~~

Một schedule có thể dùng lại cho nhiều disks trong cùng region khi phù hợp điều kiện. Ngược lại, không nên mặc định một disk được gắn nhiều snapshot schedules đồng thời; hãy kiểm tra giới hạn của loại disk và cách quản lý resource policies.

### 11.1. Các thành phần của schedule

| Trường | Ý nghĩa | Giá trị minh họa |
| --- | --- | --- |
| Name | Tên policy | `lab-orders-daily` |
| Region | Vị trí resource policy, cùng region disk | `asia-southeast1` |
| Frequency | Mức lặp | Daily |
| Start time | Thời điểm bắt đầu **theo UTC** | `12:00` |
| Storage location | Nơi standard snapshot được lưu | `asia` |
| Max retention days | Số ngày giữ snapshot tự sinh (theo điều kiện) | 7 |
| On source disk delete | Cách xử lý snapshots khi disk nguồn bị xóa | `apply-retention-policy` |
| Snapshot labels | Metadata quản trị bản chụp | `env=lab`, `owner=commerce` |

**Thời gian chụp không phải SLA đúng phút 00.** Lịch có thể bắt đầu bất kỳ lúc nào trong **giờ được chỉ định**. UTC cũng khác múi giờ địa phương: phải tính quy đổi trong lịch vận hành và lưu ý DST khi nhóm theo múi giờ có đổi giờ mùa hè.

### 11.2. Tần suất là lựa chọn loại trừ nhau

Một schedule định nghĩa **một** hình thức frequency tại một thời điểm:

- **Hourly:** mỗi N giờ theo cú pháp được hỗ trợ.
- **Daily:** một lần mỗi ngày theo cửa sổ giờ UTC được chỉ định.
- **Weekly:** vào thứ hoặc các thứ định kỳ.

Không kết hợp `--hourly-schedule` và `--daily-schedule` trong cùng một lệnh. Với workload nhạy cảm cần nhiều lớp tần suất, hãy kiểm tra cách tổ chức nhiều disks/policies hoặc cơ chế backup khác; không giải quyết bằng việc gắn bừa nhiều schedules lên một disk.

## 12. Thực hành tạo và gắn daily snapshot schedule

### 12.1. Tạo resource policy

~~~bash
gcloud compute resource-policies create snapshot-schedule lab-orders-daily \
  --region=asia-southeast1 \
  --daily-schedule \
  --start-time=12:00 \
  --max-retention-days=7 \
  --on-source-disk-delete=apply-retention-policy \
  --storage-location=asia \
  --snapshot-labels=env=lab,team=commerce \
  --project=PROJECT_ID
~~~

Trong ví dụ:

- Schedule policy thuộc region `asia-southeast1` giống disk `lab-orders-data` ở zone `asia-southeast1-b`.
- Snapshot tự tạo là **standard snapshot**, được lưu vào multi-region `asia` theo cấu hình.
- Nếu muốn giữ snapshots chỉ 7 ngày, `--max-retention-days=7` xác định cửa sổ retention (còn có quy tắc giữ snapshot mới nhất).
- `--on-source-disk-delete=apply-retention-policy` quy định tiếp tục áp dụng retention khi disk nguồn bị xóa, thay vì giữ vĩnh viễn theo mặc định.
- Labels hỗ trợ truy vết các snapshots do schedule tạo.

### 12.2. Gắn policy vào disk

~~~bash
gcloud compute disks add-resource-policies lab-orders-data \
  --resource-policies=lab-orders-daily \
  --zone=asia-southeast1-b \
  --project=PROJECT_ID
~~~

Nếu là **regional disk**, sử dụng cờ `--region` theo lệnh tương ứng. Nếu disk có schedule khác, cần đánh giá và thay thế đúng quy trình thay vì tự chồng policy.

### 12.3. Đọc lại sau khi gắn

~~~bash
gcloud compute resource-policies describe lab-orders-daily \
  --region=asia-southeast1 \
  --project=PROJECT_ID

gcloud compute disks describe lab-orders-data \
  --zone=asia-southeast1-b \
  --project=PROJECT_ID

gcloud compute snapshots list \
  --project=PROJECT_ID
~~~

Trên disk, xem những **resourcePolicies** được gắn. Trên schedule, xác minh frequency, UTC time, retention, storage location và disk deletion policy. Sau khi có kỳ chụp thành công, kiểm tra snapshot tự tạo, thời điểm hoàn tất và khả năng khôi phục. **Lệnh tạo/gắn schedule thành công không chứng minh ngay đã có bản backup thành công.**

## 13. Retention và hành vi khi xóa đĩa nguồn

### 13.1. Không có retention sẽ giữ vô thời hạn

Nếu không thiết lập `--max-retention-days`, snapshot schedule có thể giữ các bản snapshot đã tạo **không giới hạn thời gian**, khiến chi phí storage tăng dần. Chính sách nên xác định rõ nhu cầu nghiệp vụ và thời gian lưu.

### 13.2. Retention không xóa mọi snapshot đúng ngày một cách tuyệt đối

Khi một snapshot vượt ngưỡng retention, Compute Engine thường **chỉ tự xóa nếu có snapshot mới hơn** của disk. Nếu không còn snapshot mới hơn, bản cuối cùng có thể được giữ lâu hơn thời hạn khai báo. Điều này giảm nguy cơ mất hết điểm phục hồi vì một schedule đã ngừng.

Ngoài ra:

- Retention của schedule chỉ tác động lên **snapshots tự tạo**, không xóa các snapshots **tạo thủ công**.
- Thay đổi retention không áp dụng hồi tố lên mọi snapshot cũ; các snapshot tạo sau thay đổi dùng chính sách mới theo quy tắc dịch vụ.
- Nếu delete schedule, snapshots trước đó có thể **được giữ vĩnh viễn** cho tới khi xóa bằng tay; schedule không còn quản lý retention của chúng.

### 13.3. Khi disk nguồn bị xóa

Có hai hành vi chính:

| Lựa chọn | Khi xóa source disk |
| --- | --- |
| `keep-auto-snapshots` | **Mặc định**: giữ những snapshots đã tự tạo, bất kể retention cũ, cho đến khi xóa thủ công |
| `apply-retention-policy` | Tiếp tục áp dụng retention đối với các snapshots do schedule tạo theo quy tắc dịch vụ |

**Đừng nhầm với instant snapshots:** instant snapshot **bị xóa cùng disk nguồn**, không có lựa chọn retention kiểu standard snapshot schedule.

### 13.4. Lịch chụp có phải SLA backup tuyệt đối?

Không. Một lịch có thể không tạo snapshot thành công vì quota, IAM, mã hóa, nguồn disk lỗi, giới hạn tần suất hoặc trạng thái dịch vụ. Do đó, **phải theo dõi bản snapshot thành công gần nhất** và cảnh báo nếu khoảng cách quá RPO.

## 14. Quản lý, thay thế và dọn snapshot schedule

### 14.1. Liệt kê schedule

~~~bash
gcloud compute resource-policies list \
  --project=PROJECT_ID

gcloud compute resource-policies describe lab-orders-daily \
  --region=asia-southeast1 \
  --project=PROJECT_ID
~~~

### 14.2. Cập nhật schedule

Có thể cập nhật một số trường như description, frequency, labels, deletion/retention policy thông qua:

~~~bash
gcloud compute resource-policies update snapshot-schedule lab-orders-daily \
  --region=asia-southeast1 \
  --daily-schedule \
  --start-time=13:00 \
  --max-retention-days=10 \
  --project=PROJECT_ID
~~~

**Thay đổi chỉ áp dụng cho những snapshot được tạo sau khi cập nhật**, không nhất thiết sửa retention của các bản cũ. Đừng thay giờ chụp vào thời gian cao điểm hoặc chỉ để giải quyết chi phí khi chưa hiểu số liệu.

### 14.3. Tháo lịch khỏi disk

~~~bash
gcloud compute disks remove-resource-policies lab-orders-data \
  --resource-policies=lab-orders-daily \
  --zone=asia-southeast1-b \
  --project=PROJECT_ID
~~~

Sau khi tháo, schedule không còn tự tạo snapshot cho disk đó. Những snapshot đã tạo vẫn cần được kiểm kê và xử lý vòng đời riêng.

### 14.4. Xóa resource policy

~~~bash
gcloud compute resource-policies delete lab-orders-daily \
  --region=asia-southeast1 \
  --project=PROJECT_ID
~~~

Chỉ thực hiện khi **không còn disk khác dùng chung schedule**. Có thể không xóa được nếu schedule vẫn đang gắn. Xóa schedule **không tự xóa** các snapshots trước đó; cần kiểm kê danh sách và retention/chi phí riêng.

## 15. Mã hóa, quyền và rủi ro truy cập snapshots

Một snapshot có thể chứa:

- Nội dung file, thông tin người dùng và tệp tạm.
- Cấu hình ứng dụng Java, secrets hoặc token vô tình lưu trên disk.
- Dữ liệu database nằm trên đĩa VM.
- Chỉ mục tìm kiếm và nội dung phục hồi nhạy cảm.

Vì vậy, **quyền tạo disk từ snapshot** có thể dẫn đến việc đọc dữ liệu mà ứng dụng gốc bảo vệ. Hạn chế IAM theo project, snapshot và nhóm vận hành phù hợp.

### 15.1. CMEK/CSEK

- Với **CMEK (Cloud KMS)**, có thể cần quyền dùng khóa cả khi tạo snapshot hoặc phục hồi; phải đảm bảo key còn khả dụng và được phép dùng tại destination.
- Với **CSEK**, ứng dụng/quản trị viên phải bảo quản khóa do khách hàng cung cấp; mất khóa có thể làm dữ liệu không phục hồi được.
- Với **snapshot schedules**, tài liệu Compute Engine nêu khả năng dùng **CMEK** kế thừa theo source disk, nhưng **không hỗ trợ schedules cho disk dùng CSEK** theo tính năng hiện hành.

**Không xóa/vô hiệu hóa Cloud KMS key một cách tùy tiện** khi snapshot còn được dùng cho DR. Kiểm tra KMS permissions, key location, rotation, trạng thái key version và audit theo quy trình Security.

### 15.2. Chia sẻ giữa project và hạn chế location

Standard snapshots có thể được chia sẻ/được sử dụng giữa các project theo IAM và cơ chế sản phẩm hỗ trợ. Tuy nhiên, việc copy/chia sẻ dữ liệu cần được phê duyệt, kiểm tra **Organization Policy**, VPC Service Controls (nếu liên quan) và data residency.

Nếu áp dụng regionally scoped snapshot ở Preview, phải kiểm tra **allowed access locations** và gcloud beta syntax tương ứng; không tự dùng `--source-snapshot=NAME` ở mọi region để suy ra tất cả đều có quyền restore.

## 16. Giám sát lịch chụp và kiểm tra restore định kỳ

Một lịch backup thành công không chỉ là “đã tạo schedule”, mà là một chuỗi kiểm soát:

~~~mermaid
flowchart TD
    A["Snapshot schedule đến giờ chạy"] --> B["Tạo standard snapshot"]
    B --> C{"Snapshot hoàn tất?"}
    C -->|Không| D["Alert, xem logs/quota/IAM/KMS, khắc phục"]
    C -->|Có| E["Ghi nhận thời điểm bản backup thành công gần nhất"]
    E --> F["Phục hồi thử vào disk/VM riêng"]
    F --> G{"Dữ liệu và ứng dụng kiểm tra đạt?"}
    G -->|Không| H["Điều tra consistency và quy trình restore"]
    G -->|Có| I["Đo RPO/RTO và xác nhận mục tiêu"]
    D --> A
    H --> A
    I --> A
~~~

### 16.1. Tín hiệu theo dõi

| Tín hiệu | Ý nghĩa | Hành động |
| --- | --- | --- |
| Snapshot gần nhất hoàn tất | Có điểm backup mới đúng lịch? | Cảnh báo nếu vượt RPO |
| Snapshot creation failures | Không có bản chụp đáng tin cậy | Kiểm tra quota, disk, KMS, IAM |
| Retention và số snapshot | Có bản quá hạn hoặc schedule bị xóa? | Rà soát chính sách và phí |
| Storage location | Backup có nằm tại nơi được duyệt? | So sánh DR/residency policy |
| Restore test | Có tạo disk/VM và đọc dữ liệu được không? | Lập diễn tập định kỳ |
| RTO đo được | Thời gian phục hồi thực so với mục tiêu | Tối ưu runbook/loại snapshot |
| Chi phí snapshot | Data storage, restore, egress | Billing Reports và budget |

### 16.2. Checklist diễn tập phục hồi

- [ ] Xác minh đúng project và loại snapshot, tránh chọn nhầm môi trường.
- [ ] Snapshot tồn tại và đã hoàn tất, source disk và timestamp phù hợp.
- [ ] Có quyền IAM và khóa mã hóa cần thiết.
- [ ] Chọn destination zone/region, disk type và dung lượng hỗ trợ.
- [ ] Tạo disk **mới**, không ghi đè disk production.
- [ ] Gắn disk vào VM kiểm thử được cấp phép; mount an toàn.
- [ ] Kiểm tra dữ liệu thực và chức năng Java/ứng dụng sau recovery.
- [ ] Ghi nhận thời gian phục hồi và lượng dữ liệu mất tối đa.
- [ ] Xóa disk/VM kiểm thử theo chính sách; giữ snapshot production.
- [ ] Ghi kết quả, owner và hành động cải tiến.

## 17. Chi phí: snapshots không miễn phí và không chỉ có một khoản

Chi phí có thể đến từ:

1. **Dung lượng snapshot được lưu**, tùy loại standard/instant/archive, location và dữ liệu đã thay đổi.
2. **Dữ liệu truyền qua region/location**, khi tạo hoặc restore phù hợp quy tắc tính phí.
3. **Disk mới** được tạo khi phục hồi và VM dùng để kiểm chứng.
4. **Cloud Logging, Monitoring**, công cụ bảo vệ dữ liệu, encryption/KMS theo cấu hình.
5. **Snapshots không còn được quản lý bởi schedule**, hoặc snapshots thủ công bị bỏ quên.
6. **Archive snapshot restore**, cần xem chi phí và thời gian khôi phục theo loại lưu trữ.

Không có mức giá cố định cho mọi region, snapshot type hoặc thời điểm. Dùng [Compute Engine disks and images pricing](https://cloud.google.com/compute/disks-image-pricing) và Cloud Billing Reports để dự báo trước khi tạo lab.

### 17.1. Vì sao incremental không đồng nghĩa ít chi phí trong mọi trường hợp?

Nếu disk thay đổi phần lớn dữ liệu mỗi ngày, chuỗi snapshot có thể lưu nhiều khối mới. Nếu retention quá dài, tổng dung lượng dữ liệu duy nhất được giữ tăng. Nếu mỗi lần build tạo dữ liệu tạm lớn trên data disk, backup có thể lưu cả những thay đổi không cần giữ.

**Cách giảm chi phí mà vẫn đáp ứng mục tiêu:**

- Chỉ snapshot disk cần bảo vệ; phân tách dữ liệu tạm.
- Đặt frequency theo RPO thực, không chọn hourly chỉ vì tiện.
- Thiết lập retention và source-disk deletion policy rõ ràng.
- Kiểm kê snapshots thủ công/auto, đặc biệt sau khi xóa schedule.
- Cân nhắc archive snapshot cho dữ liệu ít truy cập khi điều kiện phù hợp.
- Theo dõi location, egress và chi phí restore test, nhưng **không bỏ diễn tập khôi phục** để tiết kiệm.

### 17.2. Ví dụ hoạch định retention

Giả sử disk dữ liệu có 100 GiB và một phần thay đổi mỗi ngày. Nhóm muốn giữ daily snapshot 7 ngày và bản lưu hàng tháng trong 6 tháng. Không thể tính chi phí chỉ bằng **100 GiB × số snapshots**, vì incremental và dữ liệu khối trùng lặp, loại lưu trữ và retention policy làm thay đổi số GB bị tính phí.

Hãy đo **mức thay đổi thực tế** qua lịch sử, kiểm tra Billing Reports, rồi thiết kế chính sách backup dài hạn/ngoại lệ riêng. Một schedule daily không tự giải quyết mọi yêu cầu giữ monthly backups hoặc tuân thủ kiểm toán.

## 18. Xử lý lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Standard snapshot không tạo được | Disk sai tên/zone, quota/giới hạn tần suất, IAM/KMS | Disk describe, lỗi API, permissions và trạng thái |
| Snapshot có nhưng restore lỗi | Không đủ quyền, KMS key không khả dụng, region/scope không được phép | Snapshot location, IAM, CMEK/CSEK và policy |
| Tạo instant snapshot bị từ chối | Loại Hyperdisk không hỗ trợ, quá giới hạn số lượng/tần suất | Loại disk, 30 giây/32 bản, tình trạng API |
| Không thấy instant snapshot sau khi xóa VM | Boot/data disk bị auto-delete kéo theo instant snapshot | Kiểm tra lịch sử xóa disk, standard backup còn không |
| Instant snapshot không phục hồi ở region khác | Instant cùng vị trí nguồn | Tạo standard snapshot từ instant trước khi xóa nguồn |
| Không có snapshot tự tạo sau khi lập lịch | Chưa gắn resource policy, chưa tới cửa sổ UTC, job lỗi | Disk resourcePolicies, schedule describe, logs |
| Snapshot tự tạo không bị xóa đúng 7 ngày | Chưa có snapshot mới hơn hoặc deletion policy khác | Retention, lịch gần nhất, source-disk deletion option |
| Snapshot cũ được giữ vô hạn khi xóa schedule | Retention policy không còn quản lý snapshots cũ | Kiểm kê thủ công và áp dụng quy trình xóa |
| Data restore nhưng database không chạy | Snapshot crash-consistent, log/checkpoint hoặc KMS lỗi | Application-native recovery, tính nhất quán, test |
| Disk từ snapshot mount thất bại | File system/UUID/LVM, thiếu driver hoặc kích thước | Linux `lsblk`, filesystem tools, VM riêng |
| Bill tăng dù đã xóa disk | Standard snapshots còn giữ, instant/schedule/resources khác | Billing Reports, snapshots list, retention |
| RPO thực tế vượt mục tiêu | Snapshot job lỗi, schedule quá thưa, chưa alert | Backup monitoring và ứng dụng |

### 18.1. Quy trình debug theo thứ tự

~~~mermaid
flowchart TD
    A["Backup/restore không đạt"] --> B{"Loại snapshot nào?"}
    B -->|"Instant"| C["Kiểm tra disk nguồn còn, location, giới hạn, compatibility"]
    B -->|"Standard"| D["Kiểm tra status, storage location, IAM/KMS"]
    B -->|"Schedule"| E["Kiểm tra policy gắn disk, UTC, lần chạy, retention"]
    C --> F{"Snapshot còn và usable?"}
    D --> F
    E --> F
    F -->|Không| G["Đọc logs/metrics, sửa nguyên nhân, tạo backup mới khi phù hợp"]
    F -->|Có| H["Tạo disk mới để restore test"]
    H --> I{"App và dữ liệu có nhất quán?"}
    I -->|Không| J["Xem guest flush/app backup và runbook"]
    I -->|Có| K["Đo RTO, xác nhận backup đạt"]
~~~

## 19. Tình huống tổng hợp: giữ dữ liệu đơn hàng qua nâng cấp và sự cố zone

Nhóm Commerce có data disk của một VM ở `asia-southeast1-b`. Tuần này cần nâng cấp ứng dụng; đồng thời bảo đảm nếu zone không còn khả dụng thì có thể tái triển khai ở zone khác.

**Phương án:**

| Rủi ro | Cơ chế | Lý do |
| --- | --- | --- |
| Nâng cấp ứng dụng gây lỗi dữ liệu | **Instant snapshot trước deploy** | Phục hồi nhanh khi disk và zone còn |
| Xóa nhầm disk hoặc mất zone | **Standard snapshot lưu vị trí phù hợp** | Bản chụp không bị xóa cùng disk nguồn |
| Nhân viên quên backup thủ công | **Daily snapshot schedule** | Tự tạo standard snapshots theo lịch |
| Dữ liệu giao dịch không nhất quán | **Application quiesce/DB-native backup** | Snapshot khối không tự bảo đảm transaction consistency |
| Có snapshot nhưng không restore được | **Restore drill định kỳ** | Kiểm tra IAM, encryption, disk và ứng dụng |
| Phí storage vượt kế hoạch | **Retention + Billing budget** | Không giữ snapshot không cần thiết vô thời hạn |

### 19.1. Quy trình trước khi triển khai

1. Xác định bản sao dữ liệu cần giữ, owner, RPO/RTO và thời gian bảo trì.
2. Xác nhận standard snapshot schedule đang chạy và **bản snapshot gần nhất đã thành công**.
3. Nếu yêu cầu nhất quán ứng dụng, thực hiện checkpoint/quiesce trước khi backup theo quy trình được duyệt.
4. Tạo instant snapshot và ghi rõ snapshot name, source disk, zone, thời điểm.
5. Triển khai ứng dụng bằng CI/CD; giám sát health, latency và tính toàn vẹn dữ liệu.
6. Nếu rollback tại chỗ, tạo **disk mới từ instant snapshot** và khôi phục trên VM được quản lý.
7. Nếu disk nguồn/zone không còn, dùng **standard snapshot đã sẵn sàng** để tạo disk ở destination hợp lệ.
8. Sau khi xác nhận bản mới ổn định, rà soát instant snapshots không cần giữ; tránh xóa bản standard snapshot thuộc retention.
9. Ghi nhận số liệu, chi phí và kết quả diễn tập.

### 19.2. Ba nguyên tắc ra quyết định

**Nguyên tắc 1: Thời gian phục hồi và phạm vi chịu lỗi là hai trục riêng.** Instant snapshot có RTO tốt cho hỏng dữ liệu tại chỗ nhưng không đủ chống sự cố toàn zone.

**Nguyên tắc 2: Tự động hóa phải kèm kiểm chứng.** Một schedule có thể tồn tại nhiều tháng nhưng không tạo bản backup thành công do lỗi IAM/KMS/disk.

**Nguyên tắc 3: Có bản sao không bằng có dữ liệu dùng được.** Snapshot crash-consistent có thể cần file-system/database recovery; phải thử chức năng ứng dụng sau restore.

## 20. Bài tập tự kiểm tra

**Câu 1.** Instant snapshot và standard snapshot khác nhau chủ yếu ở đâu nếu VM cần phục hồi sau khi zone mất?

*Gợi ý:* Instant nằm cùng zone/region với source disk và không bảo vệ khỏi mất zone/region; standard snapshot được lưu ngoài đĩa nguồn tại location phù hợp và có khả năng phục hồi rộng hơn.

**Câu 2.** Xóa source disk sẽ xóa loại snapshot nào?

*Gợi ý:* Instant snapshots của disk đó bị xóa. Standard/archive snapshots độc lập với vòng đời source disk.

**Câu 3.** Snapshot schedule có tự tạo instant snapshots theo giờ không?

*Gợi ý:* Không. Compute Engine snapshot schedule tạo **standard snapshots**.

**Câu 4.** Daily schedule có `--max-retention-days=7` nhưng không có bản mới hơn. Snapshot cũ có chắc bị xóa ngay ngày thứ bảy?

*Gợi ý:* Không. Auto-deletion có thể đợi snapshot mới hơn của disk để tránh mất điểm phục hồi cuối cùng.

**Câu 5.** Tại sao application database trên disk có snapshot crash-consistent vẫn cần transaction recovery?

*Gợi ý:* Những transaction/buffer trong memory chưa ghi ra disk không được chụp; log và cơ chế recovery của database cần được sử dụng.

**Câu 6.** Snapshot schedule chạy `--start-time=12:00` có nghĩa chụp chính xác 12:00 giờ Việt Nam không?

*Gợi ý:* Không. Thời gian là **UTC** và schedule có thể bắt đầu trong cửa sổ giờ chỉ định; cần quy đổi theo múi giờ.

**Câu 7.** Bạn cần giữ instant snapshot sau khi xóa disk nguồn. Làm gì trước?

*Gợi ý:* Tạo **standard snapshot từ instant snapshot**, kiểm tra bản mới hoàn thành rồi mới xóa disk nguồn.

**Câu 8.** Lệnh `gcloud compute snapshots delete` có làm các standard snapshots khác của cùng disk không thể khôi phục?

*Gợi ý:* Không tự động. Compute Engine quản lý các khối chung của snapshots incremental; những snapshots còn hợp lệ vẫn có thể restore. Tuy nhiên không nên xóa bừa khi chưa kiểm tra retention.

**Câu 9.** Bản snapshot chứa dữ liệu người dùng có thể bị đọc bởi ai tạo disk từ nó không?

*Gợi ý:* Có thể. Cần giới hạn `compute.snapshots.useReadOnly` và các quyền tương đương, cùng CMEK/CSEK và audit.

**Câu 10.** Sau khi xóa snapshot schedule, những standard snapshots trước đó sẽ tự mất theo retention cũ không?

*Gợi ý:* Không mặc định; xóa policy có thể khiến các snapshots trước đó được giữ cho đến khi xóa thủ công.

**Câu 11.** Tại sao đồng thời dùng instant snapshot trước rollout và standard snapshot theo lịch lại hợp lý?

*Gợi ý:* Loại thứ nhất tối ưu phục hồi nhanh tại chỗ, loại thứ hai cung cấp lịch sử/off-site backup trước các sự cố rộng hơn.

**Câu 12.** Có snapshot đúng lịch nhưng hệ thống vẫn mất quá RPO. Có thể do đâu?

*Gợi ý:* Lần chụp bị lỗi/không hoàn tất, lịch quá thưa, độ trễ hoặc ứng dụng chưa ghi dữ liệu; cần monitoring và restore test.

**Câu 13.** Một team chọn archive snapshot cho điểm rollback cần phục hồi trong vài phút. Đây có phải lựa chọn mặc định tốt không?

*Gợi ý:* Không. Archive phù hợp lưu trữ ít truy cập, phục hồi thường chậm hơn; cần xét RTO.

## 21. Checklist trước khi đưa vào production

- [ ] Xác định source disks, zone/region, owner và dữ liệu cần bảo vệ.
- [ ] Xác định RPO, RTO và các kịch bản lỗi phải chịu: thao tác nhầm, xóa disk, mất zone, mất region.
- [ ] Dùng **instant snapshot** khi cần rollback nhanh nhưng không dùng làm bản backup duy nhất.
- [ ] Dùng **standard snapshots** lưu location phù hợp với DR và data residency.
- [ ] Chọn archive snapshot chỉ khi thời gian phục hồi dài hơn chấp nhận được.
- [ ] Kiểm tra tính nhất quán ứng dụng và phương án backup native cho database.
- [ ] Snapshot schedule là **regional resource policy**, có frequency và UTC start time đúng.
- [ ] Thiết lập retention, **on-source-disk-delete** và labels có owner.
- [ ] Kiểm tra những snapshots thủ công/được tạo trước khi thay đổi policy.
- [ ] Có quyền IAM tối thiểu và Cloud KMS keys cần thiết; không để mất khóa.
- [ ] Theo dõi snapshot thành công gần nhất, failure logs và chi phí.
- [ ] Định kỳ restore test vào disk/VM riêng và đo RPO/RTO thực tế.
- [ ] Kiểm tra snapshot tồn tại sau khi xóa disk hoặc schedule, tránh lãng phí.
- [ ] Có runbook và phê duyệt trước khi xóa snapshot/disk chứa dữ liệu thật.

## 22. Những điều cần nhớ

- **Standard snapshot** là bản sao đĩa incremental ngoài đĩa nguồn; dùng được cho backup/DR với storage location phù hợp.
- **Instant snapshot** cho phép phục hồi nhanh ở cùng zone/region, nhưng **bị xóa cùng source disk**.
- **Snapshot schedule chỉ tạo standard snapshots**, không phải instant hay archive snapshots.
- **Crash consistency khác application consistency**; database cần cơ chế quiesce/backup riêng khi yêu cầu.
- **Retention là chính sách có điều kiện**, không phải lời hứa snapshot sẽ bị xóa đúng phút; bản mới nhất có thể được giữ.
- **Xóa schedule không xóa snapshots cũ**, và default khi xóa disk là giữ auto standard snapshots trừ khi đổi policy.
- **Có snapshot chưa đủ**: phải khôi phục thử, kiểm tra dữ liệu và đo RPO/RTO.
- **Snapshots có chi phí và chứa dữ liệu nhạy cảm**: quản trị IAM, KMS, location, lifecycle và Billing.

Khi triển khai Compute Engine, GKE node disks, Cloud Run hoặc các dịch vụ khác trong mô-đun Google Cloud, hãy luôn hỏi: **“Nếu đĩa bị xóa hoặc zone không còn, điểm khôi phục gần nhất ở đâu, có tồn tại độc lập với nguồn không, ai có thể dùng và chúng ta đã từng restore thành công chưa?”** Đó mới là một kế hoạch bảo vệ dữ liệu có thể vận hành.

## Tài liệu tham khảo chính thức

- [About archive and standard disk snapshots](https://cloud.google.com/compute/docs/disks/snapshots)
- [Create archive and standard disk snapshots](https://cloud.google.com/compute/docs/disks/create-snapshots)
- [Best practices for disk snapshots](https://cloud.google.com/compute/docs/disks/snapshot-best-practices)
- [Restore from a standard snapshot](https://cloud.google.com/compute/docs/disks/restore-snapshot)
- [About instant snapshots](https://cloud.google.com/compute/docs/disks/instant-snapshots)
- [Create and manage instant snapshots](https://cloud.google.com/compute/docs/disks/create-instant-snapshots)
- [Restore disks from instant snapshots](https://cloud.google.com/compute/docs/disks/restore-instant-snapshot)
- [About snapshot schedules for disks](https://cloud.google.com/compute/docs/disks/about-snapshot-schedules)
- [Create snapshot schedules](https://cloud.google.com/compute/docs/disks/scheduled-snapshots)
- [Manage snapshot schedules](https://cloud.google.com/compute/docs/disks/manage-snapshot-schedules)
- [Compute Engine disks and images pricing](https://cloud.google.com/compute/disks-image-pricing)
- [gcloud compute snapshots create](https://cloud.google.com/sdk/gcloud/reference/compute/snapshots/create)
- [gcloud compute instant-snapshots create](https://cloud.google.com/sdk/gcloud/reference/compute/instant-snapshots/create)
- [gcloud compute resource-policies create snapshot-schedule](https://cloud.google.com/sdk/gcloud/reference/compute/resource-policies/create/snapshot-schedule)

