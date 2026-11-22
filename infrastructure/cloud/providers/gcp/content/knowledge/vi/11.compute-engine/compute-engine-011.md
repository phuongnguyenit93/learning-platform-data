# Reservation và chiến lược bảo đảm năng lực VM trong Compute Engine

Một ứng dụng Java xử lý đơn hàng có thể chạy trên managed instance group (MIG) và tự tăng số VM vào giờ cao điểm. Tuy nhiên, khi MIG cần thêm VM, một **zone** có thể không đủ phần cứng cho machine type mong muốn. Điều này có thể xảy ra ngay cả khi project còn quota, ngân sách đầy đủ và IAM đã cho phép tạo máy. Với hệ thống production, đợt di chuyển dữ liệu lớn hoặc kế hoạch khôi phục thảm họa, thiếu capacity đúng thời điểm là một rủi ro vận hành đáng kể.

**Compute Engine reservation** giúp giữ trước một lượng năng lực VM có **đặc tính phần cứng xác định trong một zone cụ thể**. Năng lực đó có thể được VM phù hợp tiêu thụ ngay hoặc được giữ cho một đợt triển khai sau. Đổi lại, **reservation phát sinh phí cho capacity đã giữ, kể cả khi chưa được sử dụng**. Reservation vì thế là công cụ bảo đảm năng lực, không phải cơ chế giảm giá.

Bài học thuộc chương **Compute Engine** trong mô-đun `CLOUD_PROVIDERS_GCP`. Kiến thức về tổ chức project, IAM, VPC, Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu được vận dụng vào lập kế hoạch triển khai, tự động hóa phát hành, duy trì độ tin cậy và kiểm soát chi phí. Trọng tâm ở đây là chọn loại reservation thích hợp, dự báo số VM, kiểm chứng mức sử dụng và quản lý vòng đời năng lực đã giữ.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **quota**, **zonal capacity**, **reservation**, **committed use discount (CUD)** và **Spot VM**.
2. Hiểu vì sao reservation gắn với **zone** và yêu cầu VM có những thuộc tính phần cứng tương thích.
3. Chọn giữa **on-demand reservation**, **future reservation** và cơ chế tiêu thụ **automatic/specific**.
4. Dùng **shared reservation** cho nhiều project và xác định ai quản trị, ai bị tính phí.
5. Ước lượng capacity theo baseline, cao điểm, rolling update và khôi phục sự cố.
6. Dùng `gcloud` tạo, kiểm tra, tiêu thụ, điều chỉnh và dọn reservation trong lab.
7. Theo dõi `count`, `assuredCount`, `inUseCount` và chi phí capacity chưa dùng.
8. Kết hợp reservation với MIG, GKE và chiến lược đa zone mà không nhầm nó với HA.

## 1. Vì sao cần reservation khi đã có quota?

| Khái niệm | Câu hỏi mà nó trả lời | Ví dụ |
| --- | --- | --- |
| **Quota** | Project được phép sử dụng tối đa bao nhiêu tài nguyên? | Còn đủ quota CPU của dòng N2 trong region |
| **Zonal capacity** | Hạ tầng ở zone còn phần cứng tương ứng không? | Zone `asia-southeast1-b` có còn máy N2? |
| **Reservation** | Có phần capacity đã được giữ trước cho VM phù hợp không? | Giữ 6 VM `n2-standard-4` tại zone b |
| **CUD/commitment** | Có cam kết sử dụng hoặc chi tiêu để được giá ưu đãi không? | Cam kết tính giá theo thời hạn |
| **Provisioning model** | VM sử dụng capacity theo chế độ nào? | Standard khác Spot |

Có quota **không bảo đảm** zone đang còn máy. Ngược lại, tạo reservation cũng **cần quota phù hợp**; reservation không phải cơ chế vượt qua giới hạn tài nguyên.

~~~mermaid
flowchart TD
    A["Ứng dụng cần thêm VM"] --> B{"Đủ quota và quyền tạo?"}
    B -->|Không| C["Kiểm tra quota/IAM"]
    B -->|Có| D{"Có reservation phù hợp còn capacity?"}
    D -->|Có| E["VM tiêu thụ năng lực đã giữ"]
    D -->|Không| F{"Zone còn capacity thường?"}
    F -->|Có| G["Tạo VM theo năng lực khả dụng"]
    F -->|Không| H["Có thể gặp lỗi thiếu resources"]
    E --> I["Tiếp tục boot, nối mạng và kiểm tra ứng dụng"]
    G --> I
~~~

**Reservation không tự tạo VM.** Bạn vẫn phải cấu hình image, boot disk, VPC subnet, firewall, service account, startup script và cơ chế giám sát ứng dụng.

## 2. Reservation thực sự giữ cái gì?

Một reservation Compute Engine thường mô tả:

- **Zone**: nơi năng lực vật lý được giữ.
- **Machine type**: chẳng hạn `n2-standard-4`.
- **VM count**: số VM matching mà reservation được thiết kế để giữ.
- **Minimum CPU platform** nếu có chỉ định.
- **GPU type/count** và **Local SSD count/interface** nếu loại máy và reservation hỗ trợ.
- **Compact placement policy** hoặc thuộc tính bổ sung, nếu được dùng.

Reservation **không tự dự trữ** boot disk, Persistent Disk, network egress, external IP, Cloud Load Balancing, dữ liệu Cloud Storage hoặc Cloud SQL. Những thành phần đó có điều kiện cấp phát và chi phí độc lập.

### 2.1. Reservation là tài nguyên zonal

~~~text
Project: atlas-commerce-prod
Region: asia-southeast1
Zone: asia-southeast1-b
Reservation: orders-n2-reserved
Machine type: n2-standard-4
VM count: 6
~~~

Capacity ở `asia-southeast1-b` không tự chuyển sang `asia-southeast1-a`. Khi một zone gặp sự cố, có reservation tại zone đó **không bảo đảm toàn bộ dịch vụ vẫn hoạt động**. Hệ thống yêu cầu HA cần phân phối workload và dự trù capacity tại **các zone khác nhau** theo kịch bản phục hồi đã chọn.

### 2.2. Thuộc tính VM phải khớp

| Thuộc tính | Điều kiện thường cần thỏa | Lỗi dễ gặp |
| --- | --- | --- |
| Zone | VM và reservation cùng zone | Cùng region nhưng khác zone |
| Machine type | Trùng machine type | VM N2-2, reservation N2-4 |
| Minimum CPU platform | Khớp cấu hình, kể cả chế độ mặc định | Chỉ định platform khác |
| GPU | Đúng loại và số lượng khi có | Khác model/count |
| Local SSD | Đúng count/interface khi có | VM thêm SSD mà reservation không giữ |
| Reservation affinity | Automatic/specific đúng kiểu | Quên target specific reservation |
| Project | Owner hoặc consumer được phép | VM ngoài phạm vi shared reservation |
| Placement policy | Khớp khi reservation yêu cầu | Thiếu compact placement policy |

Cùng số vCPU hay cùng region **chưa đủ**. Khi không tiêu thụ được reservation, cần đối chiếu từng thuộc tính liên quan.

### 2.3. Không phải mọi loại máy đều hỗ trợ như nhau

Các dòng GPU, HPC, TPU, bare metal hoặc provisioning model đặc biệt có thể có hạn chế hoặc loại reservation khác. Ví dụ trong bài này dùng **Standard N2 VM** để minh họa on-demand reservation; không áp nguyên các lệnh cho mọi GPU hoặc Spot VM. Luôn kiểm tra [Choose a reservation type](https://cloud.google.com/compute/docs/instances/choose-reservation-type) trước khi chọn tài nguyên.

## 3. Các loại reservation nên biết

| Loại | Thời điểm có capacity | Đặc điểm | Khi phù hợp |
| --- | --- | --- | --- |
| **On-demand reservation** | Tạo ngay nếu zone còn năng lực, đáp ứng quota/điều kiện | Có thể giữ cho tới khi xóa; tính phí khi tồn tại | Mở rộng theo sự kiện, migrate hoặc DR |
| **Future reservation request** | Yêu cầu bắt đầu vào ngày/giờ dự kiến | Có quy trình chấp thuận, lock time và nghĩa vụ thanh toán riêng | Kế hoạch cần capacity trong tương lai |
| **Future reservation calendar mode** | Capacity theo lịch cho loại tài nguyên được hỗ trợ | Có giới hạn thời gian và mô hình cấp phát đặc biệt | Một số nhu cầu GPU/HPC |
| **Hình thức dài hạn theo thỏa thuận** | Theo thỏa thuận hoặc kế hoạch với Google Cloud | Điều kiện/giới hạn hợp đồng | Nhu cầu đặc thù quy mô lớn |

**Yêu cầu future reservation không đồng nghĩa được cấp capacity ngay.** Cần theo dõi trạng thái chấp thuận, thời điểm bắt đầu, capacity đã provision và quy định hủy/chỉnh sửa. Với on-demand, yêu cầu tạo có thể bị từ chối ngay nếu không đủ capacity tại zone.

### 3.1. Khi nào nên giữ trước capacity?

- Chiến dịch có lịch tăng tải và cần bảo đảm số VM bổ sung.
- Di chuyển hệ thống sang Compute Engine theo từng đợt.
- Cần chuẩn bị capacity để MIG scale hoặc triển khai bản mới có surge.
- Nhu cầu DR được đánh giá là quan trọng hơn chi phí giữ chỗ.
- Phải có một loại machine/GPU nhất định trong một cửa sổ thời gian.

### 3.2. Khi nào không nên reserve?

- Lab nhỏ có thể dùng nhiều machine type/zone hoặc dời lịch.
- Workload batch có thể retry, chờ hoặc chuyển vùng, phù hợp với Spot.
- Chưa biết số lượng VM, zone hay thời gian sử dụng.
- Mục đích duy nhất là **tiết kiệm đơn giá**: cần đánh giá CUD và sizing riêng.

Reservation bị bỏ quên sau lab vẫn có thể tiếp tục tính phí dù không có VM nào chạy.

## 4. Automatic consumption và specific consumption

### 4.1. Automatically consumed reservation

Một on-demand reservation mặc định thường cho phép các VM **matching** tiêu thụ tự động. Điều này có thể áp dụng cho cả **VM đã chạy** và VM mới tạo, miễn là đúng zone, thuộc tính, project và affinity.

~~~mermaid
flowchart LR
    R["Automatic reservation<br/>6 VM N2"]
    A["VM N2 matching đang chạy"]
    B["VM N2 matching mới tạo"]
    C["VM khác zone/machine"]
    A -->|"Có thể tiêu thụ"| R
    B -->|"Có thể tiêu thụ"| R
    C -. "Không matching" .-> X["Không tiêu thụ"]
~~~

**Rủi ro:** một VM không phải workload ưu tiên nhưng có cùng cấu hình có thể chiếm capacity mong muốn dành cho ứng dụng production. Nếu cần bảo đảm workload nào được dùng capacity, hãy cân nhắc **specific reservation**.

### 4.2. Specifically targeted reservation

Tạo reservation với `--require-specific-reservation` để chỉ các VM **chủ động target đúng reservation** mới tiêu thụ được capacity.

~~~bash
gcloud compute reservations create orders-reserved \
  --project=PROJECT_ID \
  --zone=asia-southeast1-b \
  --machine-type=n2-standard-4 \
  --vm-count=6 \
  --require-specific-reservation
~~~

Ví dụ VM tiêu thụ reservation cùng project:

~~~bash
gcloud compute instances create orders-01 \
  --project=PROJECT_ID \
  --zone=asia-southeast1-b \
  --machine-type=n2-standard-4 \
  --reservation-affinity=specific \
  --reservation=orders-reserved \
  --subnet=SUBNET_NAME \
  --no-address
~~~

**Hai lệnh tạo tài nguyên tính phí**; chỉ dùng trong project và subnet được cho phép. VM không có external IP cần phương án quản trị/egress riêng nếu ứng dụng yêu cầu.

Nếu reservation nằm ở owner project khác và đã được chia sẻ, tên tham chiếu có dạng:

~~~text
projects/OWNER_PROJECT_ID/reservations/RESERVATION_NAME
~~~

| Tiêu chí | Automatic | Specific |
| --- | --- | --- |
| VM phải chỉ tên reservation | Không, nếu khớp | Có |
| VM đang chạy có thể tiêu thụ | Có thể | Chủ yếu VM tạo theo cấu hình target |
| Tranh chấp giữa workload matching | Có thể xảy ra | Dễ cô lập theo ownership |
| Cấu hình MIG/VM | Ít thay đổi nếu matching | Cần template/affinity tương ứng |
| Xóa khi có consumers | Có quy tắc riêng | Phải giải quyết VMs đang tiêu thụ trước |

Không chỉnh affinity hoặc xóa reservation trong production khi chưa kiểm tra giới hạn và tác động đến VM.

## 5. Shared reservation giữa nhiều project

Một tổ chức có thể có `commerce-prod`, `commerce-batch` và một project quản lý capacity riêng `capacity-admin`. Nếu cả hai workload cần VM cấu hình giống nhau trong cùng zone, **shared reservation** giúp dùng chung capacity thay vì mỗi nhóm giữ nhiều VM trống.

~~~mermaid
flowchart TD
    O["Organization Atlas"]
    P["Owner: capacity-admin"]
    R["Shared reservation N2<br/>zone asia-southeast1-b"]
    A["Consumer: commerce-prod"]
    B["Consumer: commerce-batch"]
    O --> P --> R
    R -. "VM matching" .-> A
    R -. "VM matching" .-> B
~~~

Ví dụ:

~~~bash
gcloud compute reservations create shared-n2-capacity \
  --project=CAPACITY_OWNER_PROJECT \
  --zone=asia-southeast1-b \
  --machine-type=n2-standard-4 \
  --vm-count=12 \
  --share-setting=projects \
  --share-with=commerce-prod,commerce-batch
~~~

Các điều kiện quan trọng:

1. Owner project phải được phép tạo shared reservations theo Organization Policy `compute.sharedReservationsOwnerProjects`; danh sách được cho phép **rỗng theo mặc định**.
2. Consumer projects phải cùng organization với owner.
3. Không thêm owner vào `--share-with` vì owner vốn được phép tiêu thụ.
4. Owner cần quota cho lượng tài nguyên reserve; consumers cần quota cho các VM tạo trong project của họ.
5. Owner quản lý cấu hình reservation; consumer không mặc định được xem reservation đó từ project riêng.
6. Nên giới hạn số owner projects và có người phụ trách để dễ theo dõi utilization.

### 5.1. Ai bị tính phí?

- **Phần chưa sử dụng** của shared reservation thường tính cho **owner project**.
- **Phần đã được consumer tiêu thụ** được tính cho consumer project tương ứng theo quy tắc billing.
- Những ưu đãi CUD/giá riêng phụ thuộc điều kiện project hoặc billing account bị tính phí.
- Bản thân tính năng chia sẻ không có phụ phí tách biệt.

Ví dụ một reservation giữ 10 VM: production dùng 4, batch dùng 3, còn 3 trống. Theo mô hình đơn giản, phần capacity tương đương **4 + 3 VM** được phân bổ cho hai consumers; **3 VM trống** thuộc chi phí owner. Không cộng thêm một khoản compute trùng lặp cho các VM đã tiêu thụ capacity đó. Disk, mạng và dịch vụ phụ trợ vẫn được tính riêng.

## 6. Reservation có bảo đảm hệ thống luôn chạy không?

**Không.** Reservation giúp bảo đảm năng lực tạo/khởi chạy VM phù hợp, không tự giải quyết:

- Hỏng cả zone hoặc cả region.
- Lỗi guest OS, JVM, ứng dụng hoặc startup script.
- Lỗi IAM, VPC route, firewall, DNS.
- Database bị gián đoạn, dữ liệu không đồng bộ hoặc disk lỗi.
- Autoscaler chọn nhầm zone/cấu hình máy.
- Health check, load balancing, RTO/RPO hoặc kế hoạch rollback.

Ví dụ một API cần tối thiểu 8 VM, đang phân bố 4 tại zone A và 4 tại zone B. Nếu A ngừng phục vụ mà B cần gánh đủ 8, B phải có khả năng tạo **4 VM bổ sung**. Reservation ở A **không di chuyển** sang B.

~~~text
Bình thường: Zone A = 4 VM, Zone B = 4 VM, tổng 8
Khi zone A hỏng:
  Zone B hiện có 4 VM
  Zone B cần thêm 4 VM để đạt 8
  → Phải dự trù capacity tại B, không chỉ tại A.
~~~

Để bảo đảm độ tin cậy, kết hợp **regional MIG, load balancer, autoscaling, health checks, backup, replication, DR drills** và năng lực theo zone. Reservation chỉ là một thành phần.

## 7. Tính lượng VM cần dự trữ

Không nên lấy số VM đang chạy rồi chọn `--vm-count` bằng trực giác. Cần dựa vào:

| Dữ liệu | Câu hỏi |
| --- | --- |
| **Baseline** | Mỗi zone thường chạy bao nhiêu VM? |
| **Peak** | Đỉnh lưu lượng dự báo cần bao nhiêu VM? |
| **Scale-out** | Khi tăng tải, cần thêm mấy VM và nhanh đến mức nào? |
| **Rolling surge** | Deployment có tạo VM mới trước khi xóa VM cũ không? |
| **DR buffer** | Khi một zone hỏng, zone còn lại phải bổ sung bao nhiêu VM? |
| **Placement** | Có yêu cầu GPU, Local SSD, CPU platform, compact placement không? |
| **Thời gian** | Cần capacity trong vài ngày hay cho một kỳ đã định? |
| **Chi phí** | Bao nhiêu capacity trống được phê duyệt duy trì? |

### 7.1. Automatic reservation có thể được VM hiện hữu tiêu thụ

Giả sử VM N2 đang chạy ở zone B là 4 và khi peak cần 10 VM. Nếu bạn tạo **automatic reservation 10 VM**, có thể xảy ra:

~~~text
Reservation count                 = 10
VM matching đang chạy tiêu thụ    = 4
Slot đã reserve nhưng chưa dùng   = 6
Năng lực scale-out đã giữ         = 6
~~~

Vì vậy, **tạo reservation 6 VM không mặc nhiên có nghĩa có 6 VM bổ sung**: 4 VM hiện tại có thể tiêu thụ trước, để lại chỉ 2 slot. Luôn xem `inUseCount` thực tế.

### 7.2. Count, assuredCount và inUseCount

- `count`: số VM reservation được khai báo.
- `assuredCount`: capacity VM được xác nhận đã giữ trong zone.
- `inUseCount`: số VM đang tiêu thụ reservation.

~~~text
Utilization (%) = inUseCount / count × 100
Unused assured capacity = max(assuredCount - inUseCount, 0)

Ví dụ:
  count        = 10
  assuredCount = 10
  inUseCount   = 7
  utilization  = 70%
  còn trống    = 3 VM
~~~

Nếu `assuredCount < count`, phần capacity được xác nhận ít hơn lượng yêu cầu; phải điều tra, không dựa vào `count` để hứa rằng toàn bộ VM chắc chắn tạo được.

**Utilization thấp không nhất thiết sai**: DR buffer có thể cần trống có chủ đích. Hãy đánh giá phần capacity chưa dùng so với mục đích bảo vệ, không chỉ một tỷ lệ phần trăm.
## 8. Reservation và committed use discounts khác nhau

| Tiêu chí | Reservation | CUD/commitment |
| --- | --- | --- |
| Mục tiêu | **Giữ năng lực VM** đúng zone/cấu hình | **Giảm giá** đổi lại một cam kết sử dụng hoặc chi tiêu |
| Phạm vi | Zonal | Theo điều kiện từng loại cam kết |
| Chi phí khi không dùng | **Có**, capacity giữ vẫn tính phí | Nghĩa vụ theo cam kết vẫn tồn tại |
| Bảo đảm scale-out phần cứng? | Có phần năng lực đã giữ, khi tạo thành công | Không mặc định; ngoại trừ cơ chế gắn reservation được hỗ trợ |
| Có thể kết hợp không? | Có khi đáp ứng eligibility | Có, với quy tắc riêng |

Một reservation có thể hưởng CUD, sustained use discounts hoặc giá theo hợp đồng nếu thỏa điều kiện. Tuy nhiên **reservation không phải một khoản phí capacity được cộng đúp** vào chi phí compute VM đang sử dụng chính capacity đó.

Một số **resource-based commitments** yêu cầu/cho phép **attached reservations** và có hạn chế chỉnh sửa/xóa trong thời hạn cam kết, nhất là khi có GPU hoặc Local SSD. Không suy ra mọi commitment đều tự giữ phần cứng.

### 8.1. Tính chi phí bằng ví dụ giả định

Giả sử một reservation giữ 8 VM đồng cấu hình. Giá **giả định** của phần tài nguyên phù hợp là `0,10 USD/VM-giờ`, chưa có giảm giá, thuế hoặc chi phí đĩa/mạng.

| Mục | Giá trị giả định |
| --- | ---: |
| Capacity giữ chỗ | 8 VM |
| VM đang dùng reservation | 5 VM |
| Capacity chưa dùng | 3 VM |
| Chi phí capacity trong 24 giờ | `8 × 0,10 × 24 = 19,20 USD` |
| Phần tương đương 5 VM dùng | `5 × 0,10 × 24 = 12,00 USD` |
| Phần tương đương 3 VM trống | `3 × 0,10 × 24 = 7,20 USD` |

Không tính thêm 12 USD compute cho chính 5 VM đã tiêu thụ reservation như một khoản nhân đôi. Nhưng **Persistent Disk, network egress, IP, snapshot, logging và các tài nguyên khác** có thể bị tính phí độc lập.

**Các số trên chỉ để giải thích cơ chế**. Để dự báo thực tế, dùng giá Compute Engine theo machine type/region, các điều kiện CUD và Cloud Billing Reports.

## 9. Lab: tạo và tiêu thụ specific reservation

**Mục tiêu:** giữ hai N2 VM trong một zone, tạo một VM tiêu thụ reservation, kiểm tra count rồi dọn. Đây là **bài thực hành tạo tài nguyên tính phí**: chỉ chạy trong project được cấp phép, có budget và owner chịu trách nhiệm.

Điều kiện trước khi chạy:

- Compute Engine API đã bật, project có billing phù hợp.
- Tài khoản có quyền tạo/xem/xóa reservation, tạo/xóa VM; không cần cấp Owner rộng nếu có vai trò hẹp phù hợp.
- Đủ quota và capacity tại zone, loại máy được chọn hỗ trợ reservations.
- Có subnet VPC thực tế ở cùng region; thay placeholder `SUBNET_NAME`.
- Mọi VM và reservation ví dụ chưa trùng tài nguyên production; dữ liệu lab có thể xóa.

### Bước 1: kiểm tra môi trường

~~~bash
gcloud auth list
gcloud config get-value project
gcloud compute zones list

# Chỉ đọc reservations hiện hữu trong project
gcloud compute reservations list --project=PROJECT_ID
~~~

`gcloud compute zones list` cho biết zone có sẵn trong danh mục nhưng không chứng minh đủ **quota** hoặc **zonal capacity** cho yêu cầu mới.

### Bước 2: tạo reservation chỉ định

~~~bash
gcloud compute reservations create lab-n2-capacity \
  --project=PROJECT_ID \
  --zone=asia-southeast1-b \
  --machine-type=n2-standard-2 \
  --vm-count=2 \
  --require-specific-reservation
~~~

Từ khi reservation tạo thành công, phần capacity được giữ bắt đầu phát sinh phí. Nếu nhận lỗi thiếu capacity/quota, cần đọc thông báo và đánh giá zone, machine type, số lượng hoặc quy trình quota phù hợp, thay vì thử tạo lặp liên tục.

### Bước 3: xem cấu hình reservation

~~~bash
gcloud compute reservations describe lab-n2-capacity \
  --project=PROJECT_ID \
  --zone=asia-southeast1-b \
  --format=json
~~~

Những field cần tìm trong cấu trúc trả về:

~~~text
name: lab-n2-capacity
specificReservationRequired: true
specificReservation:
  count: 2
  assuredCount: ...
  inUseCount: ...
  instanceProperties:
    machineType: n2-standard-2
~~~

Đây là **danh sách field minh họa**, không phải bản sao JSON API. Khi chưa có VM tiêu thụ, `inUseCount` thường bằng 0. Kiểm tra `assuredCount` thay vì giả định luôn bằng `count`.

### Bước 4: tạo VM tiêu thụ reservation

~~~bash
gcloud compute instances create lab-reserved-vm-1 \
  --project=PROJECT_ID \
  --zone=asia-southeast1-b \
  --machine-type=n2-standard-2 \
  --reservation-affinity=specific \
  --reservation=lab-n2-capacity \
  --subnet=SUBNET_NAME \
  --no-address
~~~

VM có primary internal IP nhưng không external IPv4. Nếu muốn SSH vào VM, cần chuẩn bị phương thức quản trị được cho phép như IAP TCP forwarding hoặc VPN; reservation **không tự mở đường mạng**.

### Bước 5: kiểm tra VM thực sự tiêu thụ capacity

~~~bash
gcloud compute instances describe lab-reserved-vm-1 \
  --project=PROJECT_ID \
  --zone=asia-southeast1-b \
  --format="json(resourceStatus,reservationAffinity)"

gcloud compute reservations describe lab-n2-capacity \
  --project=PROJECT_ID \
  --zone=asia-southeast1-b \
  --format=json
~~~

Tìm `resourceStatus.reservationConsumptionInfo.consumedReservation` của VM nếu được trả về. So sánh với `specificReservation.inUseCount` của reservation. Sau khi VM RUNNING và tiêu thụ thành công, kỳ vọng:

~~~text
count        = 2
assuredCount = 2 (nếu cấp đủ)
inUseCount   = 1
unused       = 1
~~~

Đừng chỉ thấy VM trùng zone rồi kết luận nó đang tiêu thụ reservation; **đọc trường consumption** là bước kiểm chứng.

### Bước 6: thay đổi số lượng khi cần

~~~bash
gcloud compute reservations update lab-n2-capacity \
  --project=PROJECT_ID \
  --zone=asia-southeast1-b \
  --vm-count=3
~~~

**Đây là thao tác thay đổi chi phí.** Việc tăng capacity còn phụ thuộc quota/availability, còn giảm capacity phải tôn trọng VMs tiêu thụ và các ràng buộc commitment. Không cần tăng count thì **bỏ qua bước này**.

### Bước 7: dọn lab theo thứ tự

~~~bash
# Kiểm tra không có dữ liệu cần giữ trước khi xóa VM
gcloud compute instances delete lab-reserved-vm-1 \
  --project=PROJECT_ID \
  --zone=asia-southeast1-b

# Kiểm tra VM đã giải phóng capacity
gcloud compute reservations describe lab-n2-capacity \
  --project=PROJECT_ID \
  --zone=asia-southeast1-b

# Xóa reservation để ngừng giữ capacity
gcloud compute reservations delete lab-n2-capacity \
  --project=PROJECT_ID \
  --zone=asia-southeast1-b
~~~

Lệnh xóa **là thao tác thực tế, không có cơ chế undo đơn giản**. Với specific reservation, phải giải quyết VM đang tiêu thụ trước khi xóa. Sau đó kiểm tra boot disk, snapshot, external IP còn sót và chi phí billing được cập nhật trễ.

## 10. Reservation với managed instance groups

Một **MIG** có thể tạo VM từ instance template và tự mở rộng theo chỉ số vận hành. Reservation có thể bảo đảm capacity cho **những VM matching** được MIG tạo theo tính năng hỗ trợ.

~~~mermaid
flowchart TD
    LB["Application Load Balancer"] --> MIG["MIG orders-api"]
    AUTO["Autoscaler"] --> MIG
    MIG --> A["VM từ instance template"]
    MIG --> B["VM từ instance template"]
    RES["Reservation phù hợp ở zone"] -. "Capacity" .-> A
    RES -. "Capacity" .-> B
    HC["Health checks và Monitoring"] -. "Kiểm tra ứng dụng" .-> MIG
~~~

### 10.1. Các điều kiện phải đồng bộ

- **Instance template** phải dùng đúng machine type, CPU platform, GPU/Local SSD, reservation affinity và placement policy khi có.
- **Vị trí zone:** VM MIG tạo ở zone nào chỉ có thể sử dụng reservation ở **zone đó**.
- **Autoscaling:** reservation không tự điều khiển min/max replicas; autoscaler vẫn tính toán theo policy.
- **MIG autohealing:** kiểm tra VM và tiến trình ứng dụng; reservation không thay health check.
- **VM boot/image/disk/network:** những thành phần này không được reservation tự chuẩn bị.
- **Shared reservation:** người vận hành cần biết MIG từ project nào có quyền tiêu thụ capacity.

### 10.2. Rolling update cũng cần capacity

Khi thay instance template, MIG có thể tạo **surge VMs** trước khi xóa VM cũ. Nếu capacity chỉ đủ cho VM hiện hữu, rollout có thể kẹt dù workload không tăng lưu lượng.

~~~text
Nhu cầu capacity tối đa theo zone
  = VM đang chạy
  + VM thêm vì autoscaling
  + VM surge khi rolling update
  + dự phòng DR nếu kịch bản cần đồng thời
~~~

Không cộng tất cả số liệu máy móc nếu các kịch bản không thể xảy ra cùng lúc; hãy xem `maxSurge`, `maxUnavailable`, chính sách phân bố theo zone và lịch rollout của MIG.

## 11. GKE, Batch, Dataflow và các workload khác

Compute Engine reservations có thể được tiêu thụ bởi một số sản phẩm được hỗ trợ, như **GKE, Batch, Dataflow, Managed Service for Apache Spark và Vertex AI**, nhưng **mỗi sản phẩm có ràng buộc riêng** về machine family, affinity, provisioning và cách tính giá.

### 11.1. Với GKE

- **Kubernetes requests/limits** cho biết Pod cần bao nhiêu CPU/memory trên một node; không phải Compute Engine reservation.
- **Compute Engine reservation** giữ capacity **node VM** trong zone.
- **Node pool** phải dùng cấu hình node tương thích và cơ chế tiêu thụ reservation được GKE hỗ trợ.
- **GKE autoscaling** vẫn bị ảnh hưởng bởi quota, topology, taints/tolerations, IAM và khả năng cung cấp node.

Một reservation cho node không đồng nghĩa Pod được lên lịch thành công. Khi áp dụng cần kiểm tra chế độ cluster (Standard/Autopilot), machine series, node pool và tài liệu tính năng tương ứng.

### 11.2. Workload batch có cần reservation?

Nếu batch có thể dời lịch, retry, chuyển zone hoặc dùng Spot VM, reservation giữ capacity lâu có thể **không tối ưu chi phí**. Nếu job có **deadline cứng**, yêu cầu GPU/CPU đặc biệt hoặc phải xử lý khối lượng lớn trong một khoảng thời gian cố định, nên đánh giá reservation hoặc future reservation.

Với Dataflow/Vertex AI, không tự giả định mọi loại job đều được dùng reservation hay hưởng CUD giống VM tạo trực tiếp. Luôn đối chiếu **tích hợp, điều kiện và restrictions** hiện hành.

## 12. IAM, Organization Policy và trách nhiệm vận hành

| Nhóm | Trách nhiệm |
| --- | --- |
| **Organization admin** | Quy định project nào có thể tạo shared reservations bằng `compute.sharedReservationsOwnerProjects` |
| **Capacity owner** | Chọn zone/machine/count, chia sẻ consumer, theo dõi và cleanup |
| **Workload owner** | Cấu hình VM/MIG/template/GKE đúng reservation |
| **SRE** | Theo dõi scaling, utilization, failover và rollout |
| **FinOps** | Tối ưu unused capacity, chia sẻ chi phí/CUD, budget |
| **Security** | IAM tối thiểu và audit thao tác thay đổi reservations |

Chỉ cấp các Compute Engine IAM permissions cần thiết. Người chỉ đọc reservation không nhất thiết phải được quyền tạo/xóa; không nên dùng `roles/owner` làm cách cấp quyền nhanh.

### 12.1. IaC không làm mất rủi ro capacity

Terraform có resource `google_compute_reservation` khi tính năng được provider hỗ trợ. Với production:

1. Dùng `plan` để xem count, machine type, zone, owner project có thay đổi không.
2. Phân tách người duyệt thay đổi capacity với workload triển khai.
3. Không cho hai pipeline cùng chỉnh một reservation.
4. Hiểu tác động khi đổi thuộc tính yêu cầu tạo lại resource.
5. Không xóa specific reservation còn consumer hoặc attached reservation còn ràng buộc commitment.
6. Ghi owner, thời hạn review và kế hoạch rollback.

**Rollback cấu hình không khôi phục bảo đảm capacity** nếu reservation đã xóa và zone không còn phần cứng để đặt lại.

## 13. Theo dõi reservation và chi phí

Cloud Monitoring có reservation consumption metrics; Console và `gcloud compute reservations list/describe` cho phép xem cấu hình và số VM dùng capacity.

| Tín hiệu | Câu hỏi | Hành động |
| --- | --- | --- |
| `count` | Đã yêu cầu giữ bao nhiêu VM? | Đối chiếu capacity plan |
| `assuredCount` | Thực sự bảo đảm bao nhiêu? | Nếu thấp hơn count, điều tra |
| `inUseCount` | Đã sử dụng bao nhiêu? | So với số VM và kế hoạch scale |
| Unused capacity | Đang giữ trống bao nhiêu? | Phân biệt DR buffer và lãng phí |
| Creation/scaling errors | MIG/VM có tạo đúng như kế hoạch? | Đối chiếu quota, zone và affinity |
| Billing cost | Phần capacity unused tiêu bao nhiêu tiền? | Phân bổ owner/consumer và CUD |
| DR readiness | Zone dự phòng có năng lực cần thiết? | Diễn tập failover |

Tạo dashboard/alerts theo tài liệu [Monitor reservation consumption](https://cloud.google.com/compute/docs/instances/reservations-monitor). Tên metric/label cần lấy từ Metrics Explorer hiện hành thay vì tự đoán.

### 13.1. Ví dụ báo cáo SRE

~~~text
Reservation: orders-capacity-b
Zone: asia-southeast1-b
Machine type: n2-standard-4
Count: 10
Assured: 10
In use: 6
Unused: 4
Owner: Commerce Platform
Reason for unused: rolling surge 2 + DR buffer 2
Review: hàng tuần
~~~

Nếu 4 VM trống được duyệt làm DR buffer, không tự giảm capacity chỉ vì utilization bằng 60%. Ngược lại, nếu nhóm duy trì 20 VM nhiều tuần nhưng không có kịch bản cần quá 2 VM, hãy xem xét giảm count/xóa sau khi đánh giá tác động.

### 13.2. Alert cần thiết

- `assuredCount` thấp hơn `count` một khoảng thời gian đáng kể.
- `inUseCount` tiến sát `assuredCount` trước kế hoạch autoscale/rollout.
- Reservation lab còn tồn tại sau ngày hết hạn.
- VM creation failures hoặc MIG không đạt target size.
- Chi phí unused capacity vượt mức đã được owner phê duyệt.

Cloud Billing budget chỉ cảnh báo theo cấu hình; **không tự dừng** reservation hoặc tính phí của VM.

## 14. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| Tạo reservation báo thiếu capacity | Zone không đủ phần cứng matching | Giảm count hoặc chọn zone/type khác có chủ đích |
| Tạo reservation báo thiếu quota | Hạn mức project/region không đủ | Quotas & System Limits, quota request |
| VM tạo được nhưng `inUseCount` không tăng | VM dùng unreserved capacity | Kiểm tra `consumedReservation`, zone, affinity |
| Specific reservation không được dùng | Thiếu target hoặc tên reservation sai | `--reservation-affinity=specific` và `--reservation` |
| VM mismatch dù cùng CPU count | GPU/SSD/minCpuPlatform/machine type khác | So sánh đầy đủ thuộc tính |
| MIG không scale | Zone khác, surge, quota, template sai | Phân bố MIG, autoscaler, reservation |
| Shared reservation không tạo được | Owner chưa allowlisted bởi Organization Policy | `compute.sharedReservationsOwnerProjects` |
| Consumer không dùng được | Khác organization, thiếu share/quota hoặc mismatch | Share settings, quota, affinity |
| Reservation trống nhưng bill tăng | Capacity vẫn được tính phí | Billing Reports và count/inUse |
| Không xóa được specific reservation | VM còn tiêu thụ | Xem consumers, dừng/xử lý theo quy trình |
| VM vẫn chạy sau khi xóa automatic reservation | Xóa reservation không đồng nghĩa xóa VM | Kiểm tra VM và billing riêng |
| Có reservation mà DR không chạy | Capacity ở zone không đúng hoặc ứng dụng/dữ liệu lỗi | Kiểm tra HA, replication, IAM và DR drills |

~~~mermaid
flowchart TD
    A["VM không tạo hoặc không consume"] --> B{"assuredCount đủ?"}
    B -->|Không| C["Kiểm tra quota/capacity/reservation status"]
    B -->|Có| D{"Zone + CPU/GPU/SSD khớp?"}
    D -->|Không| E["Sửa thuộc tính VM/template"]
    D -->|Có| F{"Project và affinity hợp lệ?"}
    F -->|Không| G["Kiểm tra share và specific/automatic"]
    F -->|Có| H{"Slot trống và quota hợp lệ?"}
    H -->|Không| I["Xem count, inUse, autoscaler"]
    H -->|Có| J["Kiểm tra disk, image, IAM, VPC, lỗi provisioning"]
~~~
## 15. Vòng đời reservation và những giới hạn khi xóa

### 15.1. Automatic reservation

Khi xóa một **automatically consumed reservation**, các VM đang tiêu thụ có thể **tiếp tục chạy**; tuy nhiên, Google Cloud không tiếp tục giữ capacity đó cho những lần tạo hoặc khởi động VM trong tương lai. Chi phí compute của VM đang chạy vẫn tồn tại theo điều kiện giá thông thường.

### 15.2. Specific reservation

Một **specifically targeted reservation** không thể bị xóa khi đang có VM tiêu thụ. Phải xử lý consumers trước. Đối với VM đã **stop/suspend** nhưng cấu hình affinity trỏ đích danh reservation, việc restart/resume về sau có thể yêu cầu tạo lại reservation đúng tên, zone và thuộc tính. Vì vậy, không xóa reservation chỉ dựa vào việc ứng dụng hiện không có lưu lượng.

### 15.3. Local SSD và trạng thái VM

Một số tình huống dừng VM với **Local SSD giữ dữ liệu**, hoặc tắt VM trong guest OS thay vì thông qua Compute Engine control plane, có thể khiến capacity **tiếp tục được tính là đang tiêu thụ**. Không mặc định máy đang ở trạng thái STOPPED sẽ làm `inUseCount` giảm. Hãy đọc trạng thái thực tế và quy tắc của loại máy/Local SSD.

### 15.4. Future reservation hoặc reservation gắn commitment

Future reservation đã vào giai đoạn ràng buộc thanh toán, hoặc reservation gắn resource-based commitment, có thể có **hạn chế chỉnh sửa/xóa** nghiêm ngặt hơn. Các thao tác trong lab dành cho **on-demand reservation độc lập**; không áp dụng quy trình dọn đó cho hợp đồng/cam kết dài hạn khi chưa kiểm tra điều khoản và người có quyền phê duyệt.

### 15.5. Dọn reservation khác với dọn môi trường

Sau khi xóa reservation, hãy kiểm tra riêng:

- VM còn hoạt động hay không và các disk/snapshots đi kèm.
- Reserved external IP, Cloud NAT, load balancer, network egress.
- Instance templates, startup scripts và automation có thể tạo lại VM.
- Cloud Billing Reports sau khi có độ trễ cập nhật.
- Shared reservation owner/consumer và báo cáo phân bổ chi phí.

## 16. Tình huống tổng hợp: kỳ bán hàng lớn của Commerce

Công ty Atlas dùng `orders-api` trên một **regional MIG** phía sau Application Load Balancer. Backend truy cập Cloud SQL, Pub/Sub và Cloud Storage. Một chiến dịch giảm giá kéo dài ba ngày sẽ làm traffic tăng mạnh.

**Yêu cầu giả định:**

- Bình thường: 6 VM `n2-standard-4`.
- Cao điểm: 14 VM trong thời gian ngắn.
- Phải phục vụ khi mất một zone theo mục tiêu SLO cụ thể.
- CI/CD có thể rolling update nhưng cần giới hạn gián đoạn.
- Không muốn giữ nguyên năng lực đỉnh trong cả tháng.

### 16.1. Phân rã số VM theo zone

Giả sử nhóm sử dụng hai zone A và B:

| Hạng mục | Zone A | Zone B | Giải thích |
| --- | ---: | ---: | --- |
| VM baseline | 3 | 3 | Tổng 6 |
| VM khi peak bình thường | 7 | 7 | Tổng 14 |
| Scale-out từ baseline | +4 | +4 | Nếu cả hai zone hoạt động |
| Capacity khi mất một zone | Phải tính riêng | Phải tính riêng | Zone còn lại có cần gánh toàn bộ 14 VM? |
| Rolling update surge | Theo MIG | Theo MIG | Tạo VM mới trước khi xóa cũ |

**Bảng chưa phải đề xuất count cuối cùng**. Nếu business yêu cầu toàn bộ 14 VM có thể chạy tại B khi A mất, sizing B phải xét trường hợp đó. Nếu triển khai có thể tạm ngừng trong sự cố, không nhất thiết cộng peak DR và surge như hai sự kiện xảy ra đồng thời.

### 16.2. Lộ trình thiết kế có kiểm chứng

1. Xác định SLO, lượng traffic có thể chịu giảm, RTO/RPO và loại sự cố phải vượt qua (một zone hay region).
2. Dùng lịch sử CPU, memory, request latency, load test và số connections tới Cloud SQL để tính số VM thật sự cần.
3. Cấu hình regional MIG/instance template, chính sách autoscaling và phân bổ zone phù hợp.
4. Đánh giá reservation **tại mỗi zone sẽ tạo VM**, dùng machine type/affinity thống nhất với template.
5. Nếu lịch tăng tải biết trước và loại capacity khó mua vào phút cuối, đánh giá **future reservation request** thay cho giữ on-demand quá sớm.
6. Kiểm tra quota, khả năng tạo reservation, chi phí và giới hạn sản phẩm.
7. Chạy thử scale-out, rolling surge, failover; xác nhận `assuredCount`/`inUseCount` và backend health.
8. Theo dõi SLO, errors, p95 latency, Cloud SQL connection pool, Pub/Sub backlog và Cloud Billing.
9. Kết thúc chiến dịch: thu hẹp hoặc xóa on-demand reservation độc lập được phép, bảo đảm không còn consumers hoặc kế hoạch restart phụ thuộc.
10. Ghi nhận số liệu, quyết định, owner và các khoản capacity trống có chủ đích.

~~~mermaid
flowchart LR
    PLAN["Forecast + load test"] --> SIZE["Sizing theo zone/DR/surge"]
    SIZE --> RES["Tạo reservation phù hợp"]
    RES --> MIG["MIG dùng template matching"]
    MIG --> LB["Load balancer + health checks"]
    LB --> OBS["SLO + capacity metrics"]
    OBS --> COST["Budget + unused capacity review"]
    COST --> CLOSE["Điều chỉnh/xóa đúng lúc"]
~~~

**Reservation chỉ là một phần của chiến lược bảo đảm năng lực.** Độ tin cậy còn phụ thuộc Java runtime, database, load balancer, VPC/IAM, khả năng khôi phục dữ liệu và quy trình phản ứng khi một zone ngừng phục vụ.

## 17. Bài tập tự kiểm tra

**Câu 1.** Project còn nhiều quota nhưng VM N2 vẫn không tạo được vì zone thiếu capacity. Quota increase có bảo đảm VM mới được tạo không?

*Đáp án gợi ý:* Không. Quota và zonal capacity khác nhau. Reservation có thể giữ capacity trước nếu tạo thành công theo điều kiện và quota.

**Câu 2.** Tạo reservation 10 VM, hiện chỉ 4 VM đang tiêu thụ. Google Cloud tính phí phần capacity của 4 hay 10 VM?

*Đáp án gợi ý:* On-demand reservation tính phí capacity đã giữ dù có được dùng hay không, tương ứng 10 VM trong ví dụ. Compute của 4 VM đã tiêu thụ reservation không bị tính đúp riêng cho cùng capacity.

**Câu 3.** Reservation ở `asia-southeast1-b` có thể được VM tại `asia-southeast1-a` tiêu thụ vì cùng machine type không?

*Đáp án gợi ý:* Không. Zone phải khớp, cùng với những thuộc tính liên quan khác.

**Câu 4.** Đã có 5 VM matching đang chạy. Tạo automatic reservation 8 VM có chắc tạo được thêm 8 VM từ reservation không?

*Đáp án gợi ý:* Không. Các VM đang chạy có thể tự tiêu thụ 5 slot; `inUseCount` là số cần kiểm chứng.

**Câu 5.** Vì sao VM không sử dụng specifically targeted reservation dù zone và machine type khớp?

*Đáp án gợi ý:* Có thể thiếu `--reservation-affinity=specific` hoặc `--reservation` trỏ sai, khác CPU platform/GPU/Local SSD, không có quyền chia sẻ hoặc không còn slot trống.

**Câu 6.** Với shared reservation, owner project giữ 10 VM; hai consumers cùng dùng 7 VM. Ai thường chịu phí 3 slot chưa dùng?

*Đáp án gợi ý:* Owner project thường chịu phần unused capacity; phần đang dùng được phân bổ cho consumer tương ứng theo mô hình billing.

**Câu 7.** Mua CUD có tự giữ đủ N2 instances trong zone khi autoscaler mở rộng không?

*Đáp án gợi ý:* Không mặc định. CUD chủ yếu phục vụ giá/cam kết; reservation phục vụ capacity. Một số resource-based commitments có attached reservations với quy tắc riêng.

**Câu 8.** Regional MIG ở hai zone nhưng reservation chỉ có ở một zone. Có thể coi đã bảo đảm DR toàn bộ không?

*Đáp án gợi ý:* Không. Cần tính capacity tại zone sẽ tiếp nhận VM khi sự cố, kiểm tra distribution, autoscaling, data replication và diễn tập.

**Câu 9.** `count=12`, `assuredCount=10`, `inUseCount=7`. Có chắc còn 5 VM đã được bảo đảm không?

*Đáp án gợi ý:* Không. Chỉ có 3 slot trong phần assured capacity chưa dùng. Chênh lệch giữa `count` và `assuredCount` cần điều tra.

**Câu 10.** Xóa hết VM lab có tự kết thúc phí reservation không?

*Đáp án gợi ý:* Không. Reservation còn tồn tại thì tiếp tục giữ và tính phí capacity theo điều kiện, dù không có consumers.

**Câu 11.** Reservation đã tạo thành công có chứng minh `orders-api` đang healthy không?

*Đáp án gợi ý:* Không. Nó giữ capacity; VM image, disk, VPC/IAM, ứng dụng Java, Cloud SQL, health checks có thể vẫn lỗi.

**Câu 12.** Vì sao không đổi traffic mà vẫn thiếu capacity trong lúc phát hành bản mới?

*Đáp án gợi ý:* Rolling update có thể tạo surge VMs tạm thời, cần xét `maxSurge` và per-zone capacity.

**Câu 13.** Vì sao không nên xóa specifically targeted reservation khi VM đã stop nhưng có thể cần restart trong sự cố?

*Đáp án gợi ý:* VM có thể cần reservation với đúng tên/zone/thuộc tính để khởi động lại; xóa capacity trước có thể gây thất bại DR.

## 18. Checklist trước khi sử dụng trong production

- [ ] Đã xác định nhu cầu chính là **capacity assurance**, không chỉ giảm giá.
- [ ] Đã chọn reservation type theo thời điểm cần VM.
- [ ] Đã xác minh machine family, GPU/Local SSD và loại workload có hỗ trợ.
- [ ] Đã chọn zone cụ thể, kiểm tra quota và những resource không nằm trong reservation.
- [ ] Đã đối chiếu machine type, CPU platform, GPU, Local SSD, affinity, project/share scope.
- [ ] Đã chọn automatic hay specific và cấu hình MIG/template phù hợp.
- [ ] Với shared reservation: đã có Organization Policy allowlist, owner/consumer và cost owner.
- [ ] Đã tính baseline, peak, DR, rolling surge, nguy cơ xảy ra đồng thời.
- [ ] Đã xem `count`, `assuredCount`, `inUseCount` và kết quả VM consumption thực tế.
- [ ] Đã lập budget, dự báo unused capacity và đánh giá CUD độc lập.
- [ ] Đã kiểm thử scaling, rolling update, failover và VM restart theo kịch bản.
- [ ] Đã ghi owner, IaC/change process, ngày review và ngày dọn.
- [ ] Không xóa specific reservation còn consumer hoặc attached reservation bị ràng buộc.
- [ ] Đã kiểm tra Monitoring, logs, IAM, VPC, disk và sức khỏe ứng dụng.

## 19. Những điểm cần nhớ

- **Reservation giữ capacity theo zone/cấu hình**, không tạo VM và không thay thế SLO ứng dụng.
- **Quota không phải capacity**: quota đủ chưa chắc còn phần cứng trong zone.
- **Automatic** có thể được VM matching đang chạy tiêu thụ; **specific** cần VM chủ động target.
- **Shared reservation** giúp nhiều project dùng chung nhưng phải quản trị owner, IAM, quota, policy và chi phí.
- **CUD phục vụ mức giá**, reservation phục vụ khả năng cấp phát; cách kết hợp cần theo đúng điều kiện.
- **Capacity chưa dùng vẫn tính phí**, còn disk/network và các dịch vụ khác có hóa đơn riêng.
- **count, assuredCount và inUseCount** cho biết reservation được khai báo, được xác nhận và đang dùng bao nhiêu.
- **HA/DR cần multi-zone strategy, autoscaling, health checks và dữ liệu có thể khôi phục**, không chỉ một reservation lớn.
- **Vòng đời reservation là độc lập**: xóa VM không tự giải phóng reservation.

Khi thiết kế hệ thống Compute Engine, hãy hỏi: **“Cần bao nhiêu VM, loại nào, tại zone nào, vào thời điểm nào? Capacity đã thực sự được giữ chưa? Ai tiêu thụ, ai chịu phí và khi nào phải trả capacity về?”** Trả lời rõ những câu hỏi này biến reservation thành một quyết định độ tin cậy và chi phí có thể kiểm chứng.

## Tài liệu tham khảo chính thức

- [About reservations — Compute Engine](https://cloud.google.com/compute/docs/instances/reservations-overview)
- [Choose a reservation type](https://cloud.google.com/compute/docs/instances/choose-reservation-type)
- [Create a single-project reservation](https://cloud.google.com/compute/docs/instances/reservations-single-project)
- [Consume reservations](https://cloud.google.com/compute/docs/instances/reservations-consume)
- [Create shared reservations](https://cloud.google.com/compute/docs/instances/reservations-shared)
- [Best practices for shared reservations](https://cloud.google.com/compute/docs/instances/best-practices-shared-reservations)
- [View reservations and reservation consumption](https://cloud.google.com/compute/docs/instances/reservations-view)
- [Modify reservations](https://cloud.google.com/compute/docs/instances/reservations-modify)
- [Monitor reservations consumption](https://cloud.google.com/compute/docs/instances/reservations-monitor)
- [About future reservation requests](https://cloud.google.com/compute/docs/instances/future-reservations-overview)
- [Troubleshoot reservation creation](https://cloud.google.com/compute/docs/troubleshooting/troubleshooting-reservation-creation)
- [Troubleshoot reservation consumption](https://cloud.google.com/compute/docs/troubleshooting/troubleshooting-reservation-consumption)
- [gcloud compute reservations create](https://cloud.google.com/sdk/gcloud/reference/compute/reservations/create)
- [Compute Engine pricing](https://cloud.google.com/compute/all-pricing)



