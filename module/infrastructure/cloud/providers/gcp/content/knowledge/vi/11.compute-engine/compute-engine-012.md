# Live migration, maintenance policy và lịch bảo trì

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích vì sao **Compute Engine** cần bảo trì máy chủ vật lý và **live migration** giúp VM tiếp tục chạy khi bảo trì được lên kế hoạch.
2. Phân biệt **onHostMaintenance: MIGRATE/TERMINATE**, **automaticRestart**, **hostErrorTimeoutSeconds**, khả năng khôi phục **Local SSD**, cũng như khác biệt giữa bảo trì và sự cố phần cứng.
3. Xác định những loại VM **không hỗ trợ live migration**, đặc biệt là Spot/preemptible, GPU/TPU, bare metal và một số cấu hình máy chuyên dụng.
4. Kiểm tra và thay đổi **host maintenance policy** bằng gcloud trong điều kiện hợp lệ, đồng thời đọc thông báo **maintenance-event**, **upcoming-maintenance** và Cloud Audit Logs.
5. Hiểu giới hạn của **lịch bảo trì được thông báo trước** và **on-demand maintenance**; lập runbook giảm ảnh hưởng ứng dụng, kiểm chứng và phục hồi.
6. Thiết kế tính sẵn sàng cho Java API trên Compute Engine, managed instance groups (MIG), GKE và hệ thống dữ liệu; đánh giá monitoring, bảo mật, chi phí và SLO.

## 1. Bối cảnh: VM chạy trên hạ tầng phải được bảo trì

Một VM trên **Google Compute Engine** chạy trong một zone, được đặt trên host vật lý do Google Cloud quản lý. Trong vòng đời host, nền tảng có thể cần cập nhật hypervisor, vá bảo mật, thay thế linh kiện, sửa lỗi mạng hoặc bảo trì phần cứng. Các hoạt động này không đồng nghĩa ứng dụng của khách hàng phải ngừng hoạt động trong mọi trường hợp.

Ví dụ ứng dụng **Java/Spring Boot** phục vụ đơn hàng trên VM **orders-api-01**, gắn Persistent Disk và chạy trong mạng VPC riêng. Nếu máy chủ vật lý chứa VM cần bảo trì, có hai hướng chính:

- **Live migrate:** Google Cloud chuyển trạng thái VM đang chạy sang host khác trong **cùng zone**, với thời gian gián đoạn ngắn và không yêu cầu guest OS khởi động lại theo quy trình thông thường.
- **Terminate:** VM bị dừng trong sự kiện bảo trì; tùy cấu hình và loại máy, Compute Engine có thể **tự khởi động lại** sau đó.

Các hành vi được điều khiển bằng **host maintenance policy** và khả năng hỗ trợ của loại VM. Không phải cứ gọi máy là VM tiêu chuẩn thì luôn được chọn live migration; GPU, bare metal, Spot và một số máy chuyên dụng có yêu cầu khác nhau.

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học triển khai project, IAM, VPC, Compute Engine, GKE, Cloud Run, lưu trữ và database, đồng thời tự động phát hành và theo dõi độ tin cậy, chi phí. Hiểu host maintenance là một phần thiết kế vận hành: **tránh nhầm nền tảng cố gắng duy trì một VM với bảo đảm ứng dụng không bao giờ bị gián đoạn**.

### Một số thuật ngữ

| Khái niệm | Ý nghĩa | Không nên nhầm với |
|---|---|---|
| **Host maintenance event** | Hoạt động bảo trì host/hạ tầng nơi VM đang chạy | Deploy bản cập nhật ứng dụng hoặc OS patch trong guest |
| **Live migration** | Chuyển VM đang chạy sang host vật lý khác trong cùng zone | Chuyển workload từ on-premises sang cloud hoặc đổi zone |
| **Host error** | Sự cố host khiến VM không đáp ứng hoặc phải phục hồi | Bảo trì theo lịch luôn có thông báo |
| **Host maintenance policy** | Hành vi VM khi có host event/host error theo các field scheduling | Lịch tự động stop/start VM để tiết kiệm chi phí |
| **Upcoming maintenance notification** | Thông báo trước có cửa sổ thời gian với một số machine families | Lịch cố định có sẵn cho mọi VM |
| **On-demand host maintenance** | Chủ động bắt đầu **sự kiện bảo trì đã được thông báo** khi máy đủ điều kiện | Tùy ý ra lệnh Google Cloud bảo trì mọi VM bất kỳ lúc nào |
| **Application high availability (HA)** | Thiết kế nhiều instance/zone, health check, retry, failover | Chỉ bật live migration cho một VM |

## 2. Live migration diễn ra như thế nào?

Live migration chuyển **execution state** của một VM giữa hai host trong **cùng zone**. Mục tiêu là duy trì các thuộc tính VM, gồm **IP, metadata, network configuration, trạng thái ứng dụng và dữ liệu block storage** theo khả năng dịch vụ, thay vì dừng máy và boot lại từ đầu.

~~~mermaid
sequenceDiagram
    participant G as Google Cloud control plane
    participant S as Host nguồn
    participant T as Host đích cùng zone
    participant C as Client ứng dụng
    G->>S: Phát hiện bảo trì host
    G->>T: Chuẩn bị VM đích
    S->>T: Sao chép bộ nhớ, theo dõi trang thay đổi
    C->>S: Lưu lượng đang chạy
    Note over S,T: Chuyển tiếp phần state cuối, blackout ngắn
    S->>T: Chuyển quyền thực thi sang host đích
    C->>T: Tiếp tục truy cập VM với IP như trước
    G->>G: Ghi nhận sự kiện migrate
~~~

Quy trình ở mức khái quát:

1. **Source brownout:** VM vẫn chạy trên host nguồn; hệ thống sao chép phần lớn bộ nhớ sang host đích, tiếp tục theo dõi các memory pages thay đổi.
2. **Blackout:** tạm ngưng thực thi rất ngắn để đồng bộ trạng thái cuối và chuyển điều khiển sang host đích.
3. **Target brownout:** VM tiếp tục trên host đích; hệ thống hoàn tất các công việc hậu chuyển và phục hồi hiệu năng ổn định.

Thời gian gián đoạn thường **dưới một giây** đối với live migration thông thường, nhưng không phải bảo đảm tuyệt đối không packet loss, không tăng latency hay không có timeout. Workload có tần suất ghi bộ nhớ lớn, dependency nhạy cảm hoặc driver đặc thù có thể cảm nhận biến động hiệu năng trong lúc di chuyển.

### Những gì thường được giữ nguyên

- **VM name, resource identity, zone và địa chỉ IP**; không tự đổi project hay zone.
- **Guest OS và tiến trình ứng dụng** tiếp tục chạy; không cần boot lại theo trường hợp live migration thành công.
- **Persistent Disk** và network settings được duy trì theo mô hình lưu trữ/mạng hỗ trợ.
- **Local SSD** cũng có thể được live migrate cùng dữ liệu trên các dòng máy hỗ trợ, nhưng dữ liệu Local SSD vẫn có đặc tính tạm thời và rủi ro ở các loại host event không thể migrate.

### Những gì live migration không bảo đảm

- Không bảo vệ VM khỏi **zonal outage** hoặc lỗi mạng diện rộng.
- Không thay thế backup, cơ chế khôi phục database, replication, load balancing và kiểm thử lỗi ứng dụng.
- Không ngăn mọi **host failure**: nếu phần cứng đã hỏng hoàn toàn hoặc trạng thái không thể di chuyển, VM có thể bị dừng và phải phục hồi bằng restart.
- Không tự sửa phần mềm lỗi, memory leak, deadlock, schema migration hay hệ thống backend đang lỗi.
- Không chuyển VM từ **zone A sang zone B**, không thực hiện disaster recovery sang region khác.

**Kết luận:** live migration giảm gián đoạn từ **planned infrastructure maintenance**, trong khi **HA/SLO** phụ thuộc tổng thể kiến trúc ứng dụng.

## 3. Host maintenance policy: ba nhóm hành vi quan trọng

Các thiết lập này nằm trong trường **scheduling** của Compute Engine instance. Mặc định phụ thuộc machine type, provisioning model và khả năng hỗ trợ.

### 3.1. onHostMaintenance: MIGRATE hoặc TERMINATE

| Giá trị | Hành vi khi host cần maintenance | Khi nào phù hợp |
|---|---|---|
| **MIGRATE** | Compute Engine cố gắng chuyển VM đang chạy sang host mới trong cùng zone | VM hỗ trợ live migration, workload cần uptime cao và chấp nhận giảm hiệu năng ngắn |
| **TERMINATE** | Compute Engine dừng VM trong maintenance; tùy policy có thể tự restart sau đó | Loại máy không hỗ trợ migrate, hoặc workload được thiết kế chấp nhận dừng |

**MIGRATE** là mặc định của nhiều VM standard hỗ trợ tính năng này. **TERMINATE** là giá trị bắt buộc đối với các loại VM không hỗ trợ live migration; cũng là default/giá trị duy nhất với Spot và preemptible VM.

Không thể bật **MIGRATE** cho GPU VM hoặc bare metal chỉ bằng đổi cờ. Compute Engine kiểm tra cấu hình máy thực tế và có thể từ chối thiết lập không hợp lệ.

### 3.2. automaticRestart: khởi động lại sau lỗi do Compute Engine

Trường **automaticRestart** điều khiển việc Compute Engine tự khởi động lại VM tiêu chuẩn sau khi bị dừng do **host error** hoặc một **programmed stop** như bảo trì theo chính sách phù hợp.

- **true**: Compute Engine cố gắng khởi động lại sau khi bị dừng bởi nền tảng.
- **false**: không tự restart theo cơ chế này; đội vận hành phải có phương án xử lý.
- Không phải công tắc “VM sẽ luôn chạy”: khi người dùng chủ động stop VM, lỗi cả zone, chính sách capacity hoặc những điều kiện khác, hành vi không đồng nhất với restart sau host error.
- **Spot/preemptible VM không được tự restart** theo cơ chế automaticRestart này.

Ví dụ **TERMINATE + automaticRestart=true** không phải live migration: OS phải **boot lại**, service khởi tạo lại, in-memory state có thể mất, client connections cần reconnect và ứng dụng có downtime.

### 3.3. Host error timeout và Local SSD recovery timeout

Các tùy chọn nâng cao:

| Property trong API | Ý nghĩa | Lưu ý |
|---|---|---|
| **hostErrorTimeoutSeconds** | Thời gian tối đa chờ trước khi phục hồi VM khi phát hiện host không đáp ứng | Cân bằng phát hiện nhanh và nguy cơ phản ứng quá sớm; các giá trị hợp lệ theo loại máy/API |
| **localSsdRecoveryTimeout** | Thời gian tối đa cố gắng khôi phục dữ liệu Local SSD trong những trường hợp hỗ trợ, trước khi chọn hướng phục hồi khác | Không phải backup và không bảo đảm giữ được dữ liệu Local SSD |
| **gracefulShutdown** và thời gian chờ (khi hỗ trợ) | Cho workload có thêm thời gian hoàn thành một số tác vụ lúc shutdown | Không áp dụng như một lời hứa luôn có graceful shutdown cho mọi host maintenance/host error |

**Local SSD** phù hợp với cache/scratch; dữ liệu quan trọng cần được đưa vào **Persistent Disk, Cloud Storage, database/replication hoặc cơ chế bền vững khác**. Nếu GPU VM bị dừng vì host maintenance, dữ liệu trên Local SSD kèm theo có thể không thể khôi phục; cần checkpoint ra nơi bền vững trước.

## 4. Phân biệt host maintenance, host error và hành động chủ động

| Sự kiện | Nguyên nhân | Có live migration? | Cần chuẩn bị gì? |
|---|---|---|---|
| **Planned host maintenance** | Nâng cấp host, hypervisor, vá bảo mật, cơ sở hạ tầng | Có thể nếu VM hỗ trợ và policy=MIGRATE | Theo dõi thông báo, SLO và hiệu năng |
| **Emergent maintenance** | Lỗi host dự báo, phần cứng đang suy giảm cần can thiệp | Có thể tùy mức độ và VM | Thông báo có thể ngắn, sẵn sàng drain/khôi phục |
| **Sudden host failure** | Host hỏng hoàn toàn/không thể migrate | Có thể không | automaticRestart/HA, cảnh báo và runbook |
| **Manual VM stop** | Quản trị viên/pipeline chủ động stop | Không, đây không phải live migration | Thống nhất maintenance window của ứng dụng, checkpoint và restart |
| **Guest OS update/reboot** | OS patch hoặc application deployment | Không do live migration xử lý | Rolling update, backup và health check |
| **Zonal outage** | Sự cố vùng sẵn sàng | Không thể coi live migration là giải pháp | Multi-zone/multi-region architecture |
| **Spot/preemptible preemption** | Cơ chế thu hồi capacity của loại VM | Không | Checkpoint, retry job, thiết kế idempotent |

**Maintenance policy không phải instance schedule**: cấu hình để VM tự dừng lúc 22:00 mỗi ngày phục vụ tiết kiệm chi phí là bài toán scheduling resource khác, không phải đặt lịch bảo trì host vật lý.

## 5. Những VM nào không thể live migrate?

Danh sách hỗ trợ phụ thuộc machine series, cấu hình gắn thiết bị và thay đổi theo thời gian. Nguyên tắc quan trọng là **kiểm tra tài liệu maintenance experience của đúng machine type**, thay vì chỉ dựa tên họ VM.

| Nhóm | Khả năng live migration | Hành động vận hành |
|---|---|---|
| **VM standard phổ biến** (ví dụ N2, các loại E2) | Nhiều loại hỗ trợ live migration và mặc định MIGRATE | Xem chính sách thực tế bằng describe |
| **E2 VMs standard** | Chỉ hỗ trợ migrate trong host maintenance; không cho đổi tùy ý sang TERMINATE bằng cấu hình này | Không ép đổi policy chỉ vì muốn thử |
| **Spot / preemptible** | Không live migrate trong host maintenance | TERMINATE; checkpoint, tự khôi phục ở cấp workload |
| **GPU-attached VMs** | Không hỗ trợ live migration | TERMINATE; lưu checkpoint trước; lưu ý Local SSD |
| **TPU-attached instances** | Không hỗ trợ live migration theo đặc tính tương ứng | Chuẩn bị stop/restart và checkpoint mô hình |
| **Bare metal instances** | Không thể chuyển nguyên một host bare metal theo live migration VM | TERMINATE; lên lịch bảo trì và chuẩn bị downtime |
| **Cloud RDMA network interface** | Không hỗ trợ live migration | TERMINATE; phối hợp job HPC |
| **Z3 có trên 18.000 GiB Titanium SSD** | Không live migrate | TERMINATE, xem tài liệu dòng máy |
| **Z4D/Z4M có trên 42.000 GiB Titanium SSD** | Không live migrate | TERMINATE theo yêu cầu cấu hình |
| **Một số Confidential VM hoặc cấu hình chuyên dụng** | Phụ thuộc chip/cấu hình; có thể không hỗ trợ | Kiểm tra tài liệu chuyên biệt |

Khi biên soạn, tài liệu Google Cloud còn liệt kê các cấu hình chuyên dụng như **H4D, X4/X5, một số Z-series** với cách maintenance hoặc restart riêng. Danh sách này **không cố định**: kiểm tra trang **Host maintenance overview** và maintenance experience của dòng máy thực tại thời điểm triển khai.

**Cần phân biệt:** một máy có thể hỗ trợ **thông báo lịch bảo trì nâng cao** nhưng **không hỗ trợ live migration**. Ví dụ GPU VM có thông báo sớm nhằm giúp doanh nghiệp checkpoint, chứ không có nghĩa GPU workload được live migrate.

## 6. Thực hành gcloud: xem và thiết lập host maintenance policy

Ví dụ dùng:

| Biến | Giá trị minh họa |
|---|---|
| Project ID | **shop-dev-001** |
| Zone | **asia-southeast1-b** |
| VM hỗ trợ live migration | **orders-api-lab** |
| VM thử chính sách terminate | **batch-lab** |

Đây là tên **giả định**. Chỉ chạy trên project thử nghiệm được phép; việc tạo VM/disk và bật logging có thể phát sinh chi phí. Không chạy lệnh stop/reconfigure/maintenance trên production khi chưa có phê duyệt.

### 6.1. Kiểm tra trạng thái VM và loại máy

~~~bash
# Liệt kê VMs đúng project
gcloud compute instances list --project=shop-dev-001

# Xem cấu hình hiện hành của VM
gcloud compute instances describe orders-api-lab \
  --project=shop-dev-001 \
  --zone=asia-southeast1-b \
  --format="yaml(name,status,machineType,scheduling,disks,resourceStatus)"
~~~

Quan sát **scheduling.onHostMaintenance**, **scheduling.automaticRestart**, **scheduling.provisioningModel**, thông tin GPU/Local SSD và trạng thái VM trước khi quyết định thay đổi.

### 6.2. Xem riêng maintenance policy

~~~bash
gcloud compute instances describe orders-api-lab \
  --project=shop-dev-001 \
  --zone=asia-southeast1-b \
  --flatten=scheduling
~~~

Ví dụ output (giả định):

~~~yaml
scheduling:
  automaticRestart: true
  onHostMaintenance: MIGRATE
  preemptible: false
  provisioningModel: STANDARD
~~~

Điều này cho thấy VM được cấu hình **cố gắng live migrate trong host maintenance**. Nó không có nghĩa mọi lỗi host, lỗi zone hoặc lỗi Java application sẽ được loại bỏ.

### 6.3. Tạo VM có maintenance policy tường minh

Ví dụ minh họa thao tác tạo có phát sinh chi phí, chỉ dùng khi được phép:

~~~bash
gcloud compute instances create orders-api-lab \
  --project=shop-dev-001 \
  --zone=asia-southeast1-b \
  --machine-type=n2-standard-2 \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --maintenance-policy=MIGRATE \
  --restart-on-failure
~~~

Chọn **n2-standard-2** để minh họa một VM standard tương đối điển hình có khả năng live migration. Khi dùng thật, phải kiểm tra quota, cấu hình VPC/firewall/IAM/OS Login và chi phí; việc tạo VM **không tự triển khai Java API**.

### 6.4. Thay chính sách cho VM hiện có

Lệnh CLI theo tài liệu hiện hành:

~~~bash
# THAO TÁC CÓ ẢNH HƯỞNG: VM thử nghiệm phải được stop theo điều kiện CLI
gcloud compute instances set-scheduling batch-lab \
  --project=shop-dev-001 \
  --zone=asia-southeast1-b \
  --maintenance-policy=TERMINATE \
  --restart-on-failure
~~~

**Quan trọng:** CLI reference của **gcloud compute instances set-scheduling** nêu điều kiện gọi khi VM ở trạng thái **TERMINATED (đã dừng)**. Vì vậy ví dụ giả định **batch-lab đã được dừng an toàn** và các tác vụ đã checkpoint. Không tự chạy lệnh stop trên VM đang phục vụ khách hàng chỉ để thay policy.

Nếu VM/machine series không cho đổi **onHostMaintenance** (ví dụ E2 hoặc một số loại Spot/chuyên dụng), lệnh có thể bị từ chối. Với instance templates và MIG, chính sách nên được đặt ở **instance template** rồi rollout theo quy trình phù hợp, thay vì sửa tay từng managed instance.

### 6.5. Automatic restart độc lập với MIGRATE/TERMINATE

~~~bash
# Ví dụ tắt cơ chế auto restart cho VM lab đã dừng
gcloud compute instances set-scheduling batch-lab \
  --project=shop-dev-001 \
  --zone=asia-southeast1-b \
  --no-restart-on-failure
~~~

Có thể dùng **--restart-on-failure** để bật lại khi machine type hỗ trợ. Không sử dụng **--no-restart-on-failure** cho hệ thống cần tự phục hồi trừ khi có thay thế ở tầng workload; tắt restart có thể khiến VM nằm ở trạng thái dừng sau host event.

## 7. Lịch bảo trì: không phải mọi VM đều có thông báo trước

Compute Engine có thể phát **upcoming maintenance notifications** cho các machine families được hỗ trợ. Thông báo giúp nhóm vận hành biết **maintenance window** và đôi khi cho phép **chủ động bắt đầu bảo trì trong khoảng được phép**.

### 7.1. Những machine families có advanced maintenance notifications

Theo tài liệu Google Cloud khi biên soạn, tính năng notification nâng cao có trên nhiều dòng phù hợp, chẳng hạn **A/G-series GPU**, **TPU**, **C3/C3D/C4/C4A/C4D**, **C4N**, **H3/H4D**, **M-series**, **X-series**, **Z-series**. Danh sách và số ngày thông báo **khác nhau theo từng máy và cấu hình**.

Không nên nói rằng **mọi E2/N2 VM đều được thông báo trước 7 ngày**. Nhiều VM standard chủ yếu dựa vào live migration và chỉ có **maintenance-event** sát thời điểm. Các sự kiện **emergency/unscheduled** có thể được báo ít hơn dự kiến hoặc không có cửa sổ chuẩn.

### 7.2. Các trường upcomingMaintenance quan trọng

Ví dụ JSON minh họa một thông báo **có khả năng bắt đầu bảo trì thủ công**:

~~~json
{
  "canReschedule": true,
  "latestWindowStartTime": "2026-12-10T18:00:00Z",
  "machineType": "c4-highmem-192",
  "maintenanceStatus": "PENDING",
  "type": "SCHEDULED",
  "windowStartTime": "2026-12-10T18:00:00Z",
  "windowEndTime": "2026-12-10T22:00:00Z"
}
~~~

Thời điểm trên là **giả định** để học cách đọc dữ liệu, không phải lịch bảo trì thực của tài khoản.

| Trường | Cách hiểu |
|---|---|
| **maintenanceStatus: PENDING** | Có sự kiện đang chờ, chưa bắt đầu |
| **maintenanceStatus: ONGOING** | Bảo trì đang thực hiện |
| **canReschedule: true** | Dòng máy và thời điểm đó cho phép bắt đầu maintenance thủ công trong cửa sổ thông báo |
| **canReschedule: false** | Không thể chủ động thay đổi thời điểm, hoặc sự kiện đã diễn ra/loại máy không hỗ trợ |
| **windowStartTime** | Bắt đầu cửa sổ bảo trì dự kiến |
| **windowEndTime** | Kết thúc cửa sổ dự kiến |
| **latestWindowStartTime** | Thời điểm trễ nhất còn được chọn để bắt đầu bảo trì theo điều kiện hỗ trợ |
| **type: SCHEDULED** | Bảo trì được lên kế hoạch |
| **type: UNSCHEDULED** | Bảo trì khẩn/cấp bách; cách hiển thị thông tin có thể khác theo kênh |

Đọc **UTC timestamp** chính xác và chuyển theo múi giờ vận hành. Không coi **latestWindowStartTime** là “bảo trì sẽ diễn ra đúng giờ đó”; nó mô tả ranh giới lựa chọn của cơ chế reschedule/on-demand.

### 7.3. Không phải người dùng đặt được lịch bảo trì hạ tầng tùy ý

Với machine type có **on-demand maintenance**, bạn có thể **bắt đầu sớm** một sự kiện đã được thông báo trong khoảng cho phép. Nếu không chủ động, Compute Engine sẽ thực hiện khi đến thời điểm theo chính sách của nền tảng.

Không có nút chung “Google hãy bảo trì VM này vào thứ Tư hàng tuần” cho mọi VM. Việc chọn giờ tự động **restart ứng dụng**, **stop VM hàng đêm** hoặc **OS patch rollout** là các quy trình khác; chúng không điều khiển lịch bảo trì host vật lý của Google Cloud.

## 8. Ba cách xem thông báo maintenance

### 8.1. Qua gcloud/Compute Engine API

~~~bash
# Chỉ hiện thông tin nếu VM thuộc loại hỗ trợ và có upcoming event
gcloud compute instances describe orders-api-lab \
  --project=shop-dev-001 \
  --zone=asia-southeast1-b \
  --format="yaml(resourceStatus.upcomingMaintenance)"
~~~

Nếu trả về **null** hoặc không có trường này, có thể chưa có lịch được thông báo, hoặc VM không thuộc machine family hỗ trợ **upcomingMaintenance**. Không được suy ra host không bao giờ bảo trì.

### 8.2. Qua metadata server bên trong VM

**maintenance-event** là metadata key gần thời điểm bảo trì, dùng khi ứng dụng cần nhận tín hiệu:

~~~bash
# Chạy BÊN TRONG guest VM
curl -sS -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/maintenance-event"
~~~

Các giá trị thường gặp:

| Giá trị | Ý nghĩa |
|---|---|
| **NONE** | Không có sự kiện host maintenance gần kề đang được báo qua key |
| **MIGRATE_ON_HOST_MAINTENANCE** | VM đang/chuẩn bị live migrate |
| **TERMINATE_ON_HOST_MAINTENANCE** | VM sẽ bị dừng trong host maintenance |

Theo tài liệu Compute Engine, VM live migrate có thể nhận tín hiệu **khoảng 60 giây trước** sự kiện nếu ứng dụng đã **query chính key maintenance-event ít nhất một lần giữa các sự kiện**. Nếu chưa từng truy vấn key đó kể từ lần maintenance trước, Compute Engine có thể **bỏ qua 60 giây cảnh báo**. Với VM không live migrate như GPU, metadata thông báo terminate thường xuất hiện **khoảng 60 phút trước**; chi tiết phụ thuộc loại máy và tính chất sự kiện.

Có thể long-poll:

~~~bash
curl -sS -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/maintenance-event?wait_for_change=true"
~~~

**Chỉ là một lần chờ thay đổi**. Một daemon production cần vòng lặp quản lý **ETag**, timeout, retry/backoff và trạng thái idempotent, vì metadata server có thể tạm trả **HTTP 503** trong lúc bảo trì.

Với các máy hỗ trợ thông báo nâng cao, xem:

~~~bash
curl -sS -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/upcoming-maintenance?alt=json"
~~~

Nếu trả về **NONE** hoặc chưa có dữ liệu, tiếp tục kiểm tra định kỳ. **upcoming-maintenance** và **maintenance-event** là **hai key phục vụ hai nhu cầu**: lên kế hoạch sớm và phản ứng sát thời điểm.

### 8.3. Qua Cloud Logging và Cloud Audit Logs

Compute Engine phát **System Event audit logs** cho các sự kiện hạ tầng:

- **compute.instances.upcomingMaintenance**: thông báo trước, trạng thái PENDING/ONGOING hoặc kết thúc.
- **compute.instances.migrateOnHostMaintenance**: VM được live migrate vì host maintenance.
- **compute.instances.terminateOnHostMaintenance**: VM bị terminate khi host maintenance.
- **compute.instances.automaticRestart**: Compute Engine tự restart VM trong trường hợp được hỗ trợ.

Trong **Logs Explorer**, một bộ lọc minh họa:

~~~text
resource.type="gce_instance"
(
  "compute.instances.upcomingMaintenance"
  OR "compute.instances.migrateOnHostMaintenance"
  OR "compute.instances.terminateOnHostMaintenance"
  OR "compute.instances.automaticRestart"
)
~~~

Người xem logs cần quyền **Cloud Logging Logs Viewer** hoặc quyền tương đương; thông báo còn phụ thuộc loại máy và chính sách ghi log. Có thể tạo **log-based alert policy** khi sự kiện maintenance được phát, chuyển thông báo tới đội vận hành và ticket/runbook phù hợp.

Đối với incident, cần phân biệt **system events** với **VM guest logs**, **application logs** và **health checks**: system event nói nền tảng đã làm gì, còn application metrics cho biết người dùng bị ảnh hưởng ra sao.

## 9. Chủ động bắt đầu bảo trì khi loại máy hỗ trợ

Nếu VM có upcoming maintenance với:

- **canReschedule: true**,
- **maintenanceStatus: PENDING**,
- còn nằm trong khoảng thời gian được phép,

quản trị viên có thể chủ động thực hiện maintenance để giảm ảnh hưởng tới thời điểm bận nhất.

~~~bash
# THAO TÁC CÓ ẢNH HƯỞNG, chỉ dành cho VM đủ điều kiện đã được duyệt
gcloud compute instances perform-maintenance INSTANCE_NAME \
  --project=PROJECT_ID \
  --zone=ZONE
~~~

Khi chạy thành công, maintenance **bắt đầu ngay**, có thể dẫn đến live migration hoặc stop/restart theo policy và loại máy. Đây không phải một lệnh **dry-run**. Nếu không có thông báo cho phép thực hiện, dịch vụ có thể báo **There is no reschedulable upcoming maintenance**.

**Runbook trước khi bấm:**

1. Xác minh đúng **project/zone/VM**, machine type và policy.
2. Kiểm tra trạng thái **canReschedule/PENDING** và thời gian cửa sổ.
3. Cân bằng **SLO và nhu cầu kinh doanh**; lên lịch ngoài đỉnh traffic nếu ứng dụng nhạy cảm.
4. Thông báo các nhóm phụ thuộc và người trực.
5. Drain requests hoặc checkpoint dữ liệu **nếu workload yêu cầu**; xác minh backup/restore.
6. Chỉ chạy **perform-maintenance** khi đã có phê duyệt.
7. Theo dõi logs, trạng thái VM, health check, metrics trong/sau event.
8. Ghi lại kết quả, thời gian thực tế, lỗi ứng dụng và bài học.

### Phân biệt với mô phỏng maintenance event

Google Cloud còn cung cấp **simulate-maintenance-event** để thử luồng thay đổi metadata và phản ứng của ứng dụng trong môi trường kiểm thử:

~~~bash
# Ví dụ thử nghiệm có thể gây gián đoạn; chỉ trên VM lab
gcloud compute instances simulate-maintenance-event orders-api-lab \
  --project=shop-dev-001 \
  --zone=asia-southeast1-b \
  --with-extended-notifications=True
~~~

Mô phỏng này dùng để kiểm tra end-to-end sự kiện maintenance; **không phải** câu lệnh chỉ đọc. Khi mô phỏng cho VM không hỗ trợ migrate hoặc có chính sách terminate, nó có thể khiến VM dừng/khởi động lại. Không dùng trong production khi chưa có kế hoạch thay đổi và rollback.

## 10. Vận hành Java application qua maintenance

Giả sử **orders-api** chạy Java/Spring Boot trên Compute Engine, truy cập **Cloud SQL PostgreSQL**, lưu ảnh trên Cloud Storage và nhận traffic qua Application Load Balancer.

### 10.1. Điều gì có thể xảy ra trong live migration?

- **Latency tăng ngắn** trong pha chuyển state, làm một vài HTTP request phản hồi chậm hoặc timeout.
- **Kết nối TCP lâu dài/WebSocket** có thể bị ảnh hưởng nếu client timeout quá ngắn hoặc ứng dụng phụ thuộc latency bất thường.
- **Database connection pool** có thể ghi nhận lỗi tạm thời do network jitter; cần cơ chế reconnect thích hợp.
- **Java process** thường không restart trong live migration thành công, nhưng ứng dụng vẫn phải chịu lỗi nền tảng không đoán trước.

Không dùng live migration làm lý do để bỏ retry có kiểm soát, timeout hợp lý, circuit breaker và idempotency cho những giao dịch có side effect.

### 10.2. Cấu hình ứng dụng chịu gián đoạn ngắn

**Timeout hợp lý:** client và backend cần có deadline phù hợp với nhu cầu kinh doanh; timeout quá ngắn làm tăng lỗi khi brownout, quá dài tạo nghẽn hàng đợi.

**Retry an toàn:** chỉ retry thao tác **idempotent** hoặc dùng idempotency key với endpoint tạo đơn hàng/thanh toán. Retry không giới hạn có thể gây bão request sau bảo trì.

**Connection pool:** đặt validation, tối đa thời gian chờ và tái tạo connection khi gặp lỗi; không mặc định in-memory session còn hợp lệ sau VM terminate/restart.

**Readiness/health endpoint:** load balancer và managed instance group cần biết instance có thật sự phục vụ được traffic. Kết quả health check phải phản ánh năng lực ứng dụng, không chỉ ping hệ điều hành.

**Drain trước stop:** đối với VM có lịch bảo trì dẫn đến terminate, có thể chủ động rút instance khỏi traffic, hoàn tất job đang chạy và lưu checkpoint theo cửa sổ cho phép.

### 10.3. Thiết kế tối thiểu nhiều instance và nhiều zone

~~~mermaid
flowchart TB
    C["Client"] --> LB["Application Load Balancer"]
    LB --> M["Regional Managed Instance Group"]
    M --> Z1["VM A<br/>zone A"]
    M --> Z2["VM B<br/>zone B"]
    Z1 --> DB["Cloud SQL HA / database được bảo vệ"]
    Z2 --> DB
    OBS["Cloud Monitoring / Logging"] --> M
~~~

**Live migration** là tính năng ở mức **VM/host**. **Regional MIG** và load balancer tạo năng lực tiếp tục phục vụ khi một instance/zone bị ảnh hưởng, nếu capacity, health check và cấu hình mạng phù hợp. **Cloud SQL HA** cũng có cơ chế riêng; không suy rằng HA của VM tự làm database HA.

Với VM có state nội bộ cần giữ lâu dài, cân nhắc **stateful MIG** hoặc phương án lưu state ngoài VM. Stateless application dễ rolling replacement và failover hơn.

## 11. Bảo trì trong Managed Instance Groups (MIG)

MIG sử dụng **instance template** để định nghĩa VMs và có cơ chế tự sửa lỗi (**autohealing**) khi health check thất bại. Host maintenance policy của VM trong MIG không tự thay thế những tính năng đó.

| Lớp | Vai trò | Rủi ro cần quản trị |
|---|---|---|
| **VM host maintenance MIGRATE** | Giảm downtime của từng VM trong maintenance | Latency spike, ngoại lệ không migrate |
| **VM automaticRestart** | Thử phục hồi VM sau host error/maintenance terminate | Cần boot và app readiness; không phải zonal HA |
| **MIG autohealing** | Thay instance không khỏe theo health check | Health check quá nhạy có thể gây churn |
| **Rolling update** | Chủ động phát hành template/image mới | Có thể thay VM và tạo downtime nếu policy sai |
| **Regional MIG** | Phân bố VM nhiều zone | Capacity, quota, phân bổ không tự đảm bảo mọi zone luôn sẵn |
| **Load balancer** | Chuyển traffic tới backend healthy | Cần kiểm tra warmup/drain/session affinity |

Khi muốn thay maintenance policy của một fleet, nên:

1. Định nghĩa lựa chọn phù hợp trong **instance template** mới.
2. Thử với canary hoặc nhóm staging.
3. Đánh giá update policy, max surge/max unavailable và capacity.
4. Rollout theo batch có health check, giám sát 5xx/latency.
5. Không sửa tay nhiều VM do MIG quản lý rồi để template cũ ghi đè lần tái tạo.

**Chú ý:** rolling update do bạn chủ động thực hiện là hoạt động **khác** với live migration do Google Cloud bảo trì host.

## 12. GPU, Local SSD và workload HPC: chuẩn bị cho terminate

### 12.1. GPU VM cần checkpoint

GPU VM không hỗ trợ live migration trong host maintenance. Nếu train mô hình AI trên GPU:

~~~text
GPU job chạy → thông báo maintenance → checkpoint model/optimizer state
          → dừng job an toàn → host maintenance / VM terminate
          → VM sẵn sàng lại → nạp checkpoint → tiếp tục training
~~~

Kế hoạch bao gồm:

- **Định kỳ checkpoint** vào Cloud Storage hoặc ổ đĩa bền vững.
- Cơ chế khôi phục từ checkpoint và kiểm tra integrity/version.
- Graceful shutdown theo thời lượng thông báo được hỗ trợ, nhưng không dựa vào khả năng luôn có warning với host failure khẩn.
- Monitoring khi job bị preempted/terminated, retry và dữ liệu đầu ra chưa commit.

Đặc biệt đối với GPU VM, dữ liệu **Local SSD có thể không khôi phục được khi Compute Engine dừng VM vì host maintenance**. Không lưu checkpoint duy nhất trên Local SSD.

### 12.2. Bare metal và RDMA

Bare metal hoặc máy HPC có **Cloud RDMA** có thể cần terminate/restart trong maintenance. Chúng thường xử lý job dài, nhạy cảm topology và dữ liệu trên local storage:

- Lên lịch thời điểm ít tác động nếu **upcomingMaintenance** có **canReschedule**.
- Dùng scheduler/checkpoint phù hợp với Slurm/MPI hoặc ứng dụng HPC.
- Chấp nhận restart hoặc thay host theo đặc tính machine series; không coi restart là live migration.
- Kiểm tra lịch downtime, tốc độ restore và khả năng mất dữ liệu tạm.

### 12.3. Local SSD không phải Persistent Disk

| Thuộc tính | Local SSD | Persistent Disk / Hyperdisk |
|---|---|---|
| Vị trí dữ liệu | Gắn với hạ tầng cục bộ của host | Dịch vụ block storage được quản lý |
| Điển hình | Cache, scratch, intermediate data | Boot, application data, database disks |
| Live migration | Có thể di chuyển cùng VM khi dòng máy hỗ trợ | Dữ liệu được duy trì theo cơ chế dịch vụ |
| Host failure không migrate được | Có rủi ro mất dữ liệu; recovery không bảo đảm | Có tính bền vững cao hơn, vẫn cần backup và HA |
| Khôi phục | Có thể cần xây dựng lại cache/checkpoint | Snapshot, replication/backup tùy sản phẩm |

Không phải mọi loại Local SSD/cấu hình đều có cùng recovery behavior; các dòng **Z3/Z4** có ngưỡng Titanium SSD và phương án maintenance riêng.

## 13. Quan sát, SLO và kiểm thử

### 13.1. Các chỉ số nên đo

| Chỉ số | Mục đích |
|---|---|
| **VM uptime/restarts** | Phân biệt migrate không reboot với terminate/restart |
| **System Event audit logs** | Xác nhận loại host event và thời điểm |
| **HTTP 5xx rate, latency p95/p99** | Đo tác động thực tế tới người dùng |
| **Load balancer backend health** | Biết instance có bị coi unhealthy hay không |
| **CPU/memory, network throughput, disk I/O** | Phát hiện brownout và tải bất thường |
| **Database connection errors** | Xác định lỗi phụ thuộc phát sinh lúc migrate |
| **Queue lag, job checkpoint duration** | Đánh giá khả năng phục hồi tác vụ batch |
| **Time to recover / RTO / RPO** | Đo chất lượng phục hồi khi không migrate được |

### 13.2. Các test nên có

1. **Read-only preflight:** xác nhận machine type, policy, automaticRestart, logs.
2. **Metadata listener:** verify ứng dụng đọc key và xử lý NONE/MIGRATE/TERMINATE.
3. **Simulated maintenance trên lab:** đo error budget và latency.
4. **Host termination path:** thử shutdown/restart có kiểm soát cho workload có terminate policy, đo thời gian boot tới READY.
5. **Multi-instance failover:** chủ động loại một backend khỏi load balancer để xem traffic sang instance khác.
6. **Durability test:** restore backup/checkpoint sau gián đoạn; đảm bảo giao dịch quan trọng không mất.
7. **Alert routing:** xác nhận log-based alert tạo incident, đúng người nhận và ticket có đủ dữ kiện.

Khi thử nghiệm, ghi lại **thời điểm, request count, error rate, latency, VM state, audit events và kết quả rollback**. Chỉ nói “test thành công” khi có tiêu chí nghiệm thu cụ thể.

### 13.3. Log-based alert cho maintenance

Ví dụ ý tưởng bộ lọc Logs Explorer:

~~~text
resource.type="gce_instance"
(
  protoPayload.methodName="compute.instances.upcomingMaintenance"
  OR protoPayload.methodName="compute.instances.terminateOnHostMaintenance"
  OR protoPayload.methodName="compute.instances.migrateOnHostMaintenance"
)
~~~

Đối với audit log của sự kiện theo version/dạng log cụ thể, field có thể nằm ở **protoPayload.methodName**, **operation.producer** hoặc thông tin bổ sung; cần xác minh filter từ log mẫu trong project. Có thể bật alert trước production và kiểm tra sự kiện mẫu/tương thích trước khi tin cậy hoàn toàn.

## 14. Runbook cho một maintenance window

**Tình huống:** một VM đơn lẻ phục vụ dịch vụ Java, dòng máy hỗ trợ **upcomingMaintenance**, maintenanceStatus=PENDING và canReschedule=true.

### Giai đoạn A — Khi nhận thông báo

1. Lưu **project, zone, instance ID, machine type, onHostMaintenance, automaticRestart**.
2. Ghi **windowStartTime, windowEndTime, latestWindowStartTime** và chuyển sang múi giờ đội trực.
3. Đọc maintenance experience cho loại VM, xác định **MIGRATE** hay **TERMINATE** thực tế.
4. Kiểm tra backup/checkpoint, phiên bản ứng dụng, dashboard SLO, các bên liên quan.
5. Nếu production, lập change record với người quyết định và thời điểm bắt đầu có thể chấp nhận.

### Giai đoạn B — Trước khi bảo trì

1. Đảm bảo workload có **graceful handling** và thông báo cho đội ứng dụng.
2. Với terminate: drain traffic, checkpoint, ngừng nhận job dài, xác nhận restore plan.
3. Với migrate: tiếp tục phục vụ nếu workload phù hợp, nhưng tăng giám sát latency và connection errors.
4. Nếu hỗ trợ và phù hợp, bắt đầu maintenance sớm bằng **perform-maintenance**; nếu không thì theo dõi đến thời điểm do Compute Engine thực hiện.
5. Không đổi IAM, firewall hoặc thông số storage không liên quan chỉ vì đang có host event.

### Giai đoạn C — Trong sự kiện

1. Theo dõi System Event logs và metadata **MIGRATE_ON_HOST_MAINTENANCE** hoặc **TERMINATE_ON_HOST_MAINTENANCE**.
2. Kiểm tra VM state, load balancer health và business metrics.
3. Theo dõi exception, DB pool, queue consumer và thời gian khởi tạo lại nếu có restart.
4. Dùng escalation khi vượt error budget hoặc VM không phục hồi đúng kỳ vọng.

### Giai đoạn D — Sau sự kiện

1. Xác nhận VM và dịch vụ đã khỏe, endpoint phản hồi đúng.
2. Đối chiếu audit event và thời điểm người dùng quan sát lỗi.
3. Với GPU/HPC, xác nhận checkpoint được nạp lại, job tiếp tục từ điểm hợp lệ.
4. Ghi downtime thực tế, số lượng lỗi và bài học cho runbook.
5. Đóng ticket chỉ khi health, dữ liệu và SLO đủ tiêu chí.

## 15. Tình huống tổng hợp: thương mại điện tử và job phân tích

Doanh nghiệp **Hải An** chạy hệ thống bán hàng trên Google Cloud:

- **orders-api** Java trên **regional MIG** ba instance ở hai zone, sau Application Load Balancer.
- **Cloud SQL** lưu đơn hàng, có sao lưu và cấu hình HA theo yêu cầu.
- **image-processing** chạy GPU VM để xử lý batch hình ảnh, lưu dữ liệu đầu ra vào Cloud Storage.
- **Nightly-report** chạy Spot VM theo batch, có khả năng retry.

### 15.1. Lựa chọn policy

| Workload | Đặc điểm | Policy/chiến lược đề xuất | Vì sao |
|---|---|---|---|
| **orders-api** | Stateless API, nhạy latency | Standard VMs hỗ trợ **MIGRATE** + automaticRestart; regional MIG, health checks | Giảm gián đoạn host, có dự phòng khi instance/zone lỗi |
| **Cloud SQL** | Database managed | Dùng **HA/backup/failover của Cloud SQL**, không coi đó là host policy của VM khách hàng | Database là sản phẩm managed riêng |
| **image-processing GPU** | GPU, batch nhiều giờ | **TERMINATE**, checkpoint định kỳ + khôi phục job | GPU không live migrate; có thể nhận maintenance notice |
| **Nightly-report Spot** | Giá thấp, chấp nhận bị thu hồi | Spot với restart ở tầng scheduler/job, không dựa automaticRestart | Spot không có bảo đảm chạy liên tục |

### 15.2. Hai cảnh báo khác nhau

**Sự kiện 1:** orders-api VM live migrate. Backend health phần lớn giữ ổn định, p99 latency tăng vài giây nhưng không có restart. Cần đánh giá **error budget** thay vì mở incident nghiêm trọng chỉ vì thấy log migrate.

**Sự kiện 2:** GPU VM có PENDING maintenance. Hệ thống thông báo cho nhóm ML, xuất checkpoint trước window. Nếu có **canReschedule**, nhóm có thể chọn bắt đầu maintenance sau khi job hoàn tất một batch. Khi VM được restart, job đọc checkpoint từ Cloud Storage. Không kỳ vọng dữ liệu scratch chỉ có trên Local SSD còn nguyên.

### 15.3. Ma trận chấp nhận

| Điều kiện kiểm thử | Kỳ vọng |
|---|---|
| orders-api migrate trên lab | Không mất dữ liệu, có đo latency và error count |
| Một VM MIG bị dừng | API vẫn phục vụ qua backend khác theo SLO |
| Một zone bị lỗi | Hệ thống còn instance ở zone khác và đủ capacity |
| GPU VM nhận maintenance notice | Có checkpoint và runbook trước khi dừng |
| GPU VM restart | Job phục hồi từ durable checkpoint |
| Spot job bị preempt | Có retry/idempotency, không nhân đôi dữ liệu |
| Logs có migrate/terminate events | Alert/ticket phân loại chính xác |
| Theo dõi chi phí | Có số liệu theo workload và thời gian chạy, không hiểu nhầm policy là budget |

## 16. Những sai lầm thường gặp

**“Bật MIGRATE đồng nghĩa không bao giờ có downtime.”** Sai. Live migration thường giảm gián đoạn, nhưng host failure không migrate được, lỗi guest hoặc zonal outage vẫn có thể gây downtime.

**“Automatic restart là live migration.”** Sai. Restart khởi động lại guest OS và app; live migration chuyển VM đang chạy mà không phải khởi động lại trong trường hợp thành công.

**“Mọi VM được thông báo trước 7 ngày.”** Sai. **upcomingMaintenance** chỉ hỗ trợ trên một số machine families và loại maintenance; sự kiện khẩn có thể báo ngắn hoặc không có cảnh báo tiêu chuẩn.

**“GPU VM có upcomingMaintenance thì cũng live migrate được.”** Sai. GPU VM cần terminate và chuẩn bị checkpoint.

**“Spot VM có thể bật automaticRestart để tránh preemption.”** Sai. Spot/preemptible không có cơ chế automaticRestart tương tự standard VMs.

**“Local SSD luôn tồn tại sau host failure.”** Sai. Có một số đường live migration/recovery, nhưng Local SSD không phải lớp lưu trữ bền vững.

**“set-scheduling có thể đổi mọi policy trên mọi VM đang chạy.”** Sai. CLI hiện tại yêu cầu điều kiện trạng thái phù hợp, và nhiều loại VM có policy cố định không cho thay đổi.

**“Có live migration là khỏi cần regional MIG.”** Sai. Live migration diễn ra trong **cùng zone**; regional MIG/HA giúp giảm rủi ro ở cấp instance và zone.

**“Lịch bảo trì có thể cố định lúc nào cũng như giờ cron.”** Sai. Chỉ một số dòng máy hỗ trợ lên lịch/khởi động sớm trong **maintenance window có thông báo**.

**“Không thấy upcomingMaintenance tức là không có sự kiện.”** Sai. Có thể chưa được thông báo hoặc máy không hỗ trợ thông tin nâng cao; host event vẫn có thể xảy ra.

## 17. Bài tập thực hành

### Bài tập A — Đọc policy

Cho output:

~~~yaml
scheduling:
  onHostMaintenance: TERMINATE
  automaticRestart: true
  provisioningModel: STANDARD
~~~

**Câu hỏi:**

1. Đây có phải live migration không?
2. Sự khác nhau giữa **TERMINATE + automaticRestart=true** và **MIGRATE**?
3. Điều gì xảy ra với in-memory Java session/connection pool khi VM stop/restart?
4. Vì sao vẫn cần backend health và backup?

**Gợi ý:** (1) không; (2) VM dừng và có thể boot lại, khác chuyển trạng thái đang chạy; (3) in-memory state mất, cần reconnect; (4) host policy không thay application HA hay bảo vệ dữ liệu.

### Bài tập B — Chọn policy và kiến trúc

Có ba workload:

- API thanh toán Java trên VM tiêu chuẩn.
- Training job GPU kéo dài 8 giờ.
- ETL dùng Spot VM, có thể lặp lại.

Hãy chọn policy, cách xử lý maintenance, backup/checkpoint, nơi đặt state và cơ chế nhận cảnh báo phù hợp cho từng workload.

**Đáp án định hướng:** API dùng MIGRATE khi được hỗ trợ + MIG/multi-zone; GPU dùng TERMINATE + durable checkpoint và theo dõi window; Spot thiết kế preemption-tolerant và retry ở scheduler, không dựa vào restart tự động.

### Bài tập C — Diễn giải thông báo lịch

~~~json
{
  "canReschedule": false,
  "maintenanceStatus": "PENDING",
  "type": "SCHEDULED",
  "windowStartTime": "2026-12-10T18:00:00Z",
  "windowEndTime": "2026-12-10T22:00:00Z"
}
~~~

**Câu hỏi:**

1. Có thể chạy **perform-maintenance** để tùy ý dời lịch không?
2. Nên làm gì với workload không hỗ trợ live migration?
3. Những thời điểm trong JSON dùng múi giờ nào và cần thông báo cho ai?

**Gợi ý:** (1) không, canReschedule=false; (2) checkpoint, chuẩn bị terminate/restart theo window, bảo đảm HA; (3) timestamp UTC, chuyển sang múi giờ của đội trực và báo stakeholders.

### Bài tập D — Chẩn đoán sự cố

Một VM standard **MIGRATE + automaticRestart=true** xuất hiện log:

~~~text
compute.instances.migrateOnHostMaintenance
~~~

Ngay sau đó API có p99 latency tăng và một số timeout, nhưng không có OS boot mới. Hãy phân biệt lỗi **live migration brownout** với lỗi **backend quá tải**, đề xuất cách đối chiếu System Events, app logs, metrics, load balancer health và database connection pool.

**Định hướng:** đối chiếu timestamp, so sánh request pattern, CPU/memory/net, VM uptime, các lỗi dependency. Không coi một log migrate là chứng minh duy nhất cho mọi lỗi. Điều chỉnh timeout/retry có kiểm soát và kiểm thử simulated maintenance trên lab.

### Bài tập E — Thiết kế runbook bảo trì

Viết checklist cho GPU VM có thông báo **canReschedule=true, PENDING**, gồm:

1. Xác nhận đúng VM/project/zone và ngưỡng lưu dữ liệu.
2. Chụp checkpoint ra durable storage.
3. Đo thời gian dừng/khởi động/khôi phục thực tế.
4. Chọn thời điểm perform-maintenance được duyệt.
5. Giám sát, tiếp tục job, xác minh output và cập nhật incident record.

**Tiêu chí:** không dựa vào Local SSD làm nơi lưu checkpoint duy nhất; có kế hoạch rollback và owner.

## 18. Ghi nhớ và tài liệu tham khảo

**Sáu nguyên tắc chính:**

1. **Live migration** giúp nhiều VM tiếp tục chạy khi host được bảo trì, **trong cùng zone**, nhưng không thay thế kiến trúc HA.
2. **MIGRATE** và **TERMINATE** là hai lựa chọn về host maintenance; **automaticRestart** quyết định một phần hành vi sau khi bị dừng bởi nền tảng.
3. **GPU, Spot, bare metal và nhiều cấu hình chuyên dụng** không thể live migrate; bắt buộc đọc tài liệu machine series thực tế.
4. **maintenance-event** phù hợp để ứng dụng phản ứng sát sự kiện; **upcoming-maintenance** phục vụ lập kế hoạch sớm và chỉ có với loại máy được hỗ trợ.
5. **perform-maintenance** chỉ chủ động bắt đầu sự kiện đã thông báo khi **canReschedule=true/PENDING**; không phải lịch bảo trì tùy ý cho mọi VM.
6. Đo **SLO và dữ liệu thực**, chuẩn bị backup/checkpoint, nhiều instance/zone, logging, runbook và kế hoạch phục hồi.

**Tài liệu Google Cloud chính thức:**

1. [About host events](https://docs.cloud.google.com/compute/docs/instances/host-maintenance-overview) — maintenance, host error, MIGRATE/TERMINATE, restart và máy không hỗ trợ.
2. [Live migration process during maintenance events](https://docs.cloud.google.com/compute/docs/instances/live-migration-process) — các pha live migration, thời gian gián đoạn và Local SSD.
3. [Set the host maintenance policy for a compute instance](https://docs.cloud.google.com/compute/docs/instances/setting-vm-host-options) — scheduling fields và ví dụ gcloud.
4. [gcloud compute instances set-scheduling](https://docs.cloud.google.com/sdk/gcloud/reference/compute/instances/set-scheduling) — cú pháp và ràng buộc cập nhật policy.
5. [Monitor and plan for a host maintenance event](https://docs.cloud.google.com/compute/docs/instances/monitor-plan-host-maintenance-event) — upcomingMaintenance, logs và thời gian thông báo.
6. [Query metadata server for maintenance notices](https://docs.cloud.google.com/compute/docs/metadata/getting-live-migration-notice) — maintenance-event, 60 giây/60 phút và wait_for_change.
7. [Manually start a host maintenance event](https://docs.cloud.google.com/compute/docs/instances/trigger-host-maintenance-event) — perform-maintenance trong cửa sổ cho phép.
8. [Simulate a host maintenance event](https://docs.cloud.google.com/compute/docs/instances/simulating-host-maintenance) — kiểm thử và sự thay đổi metadata.
9. [Handle GPU host maintenance events](https://docs.cloud.google.com/compute/docs/gpus/gpu-host-maintenance) — GPU termination, checkpoint và Local SSD.
10. [About graceful shutdown](https://docs.cloud.google.com/compute/docs/instances/graceful-shutdown-overview) — khả năng và giới hạn.
