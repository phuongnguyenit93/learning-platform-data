# Rightsizing VM và loại bỏ tài nguyên nhàn rỗi

Một dự án Google Cloud có thể hoạt động ổn định nhưng vẫn lãng phí ngân sách: VM chạy 24/7 dù chỉ phục vụ báo cáo vài giờ mỗi tuần, máy ứng dụng được cấp quá nhiều vCPU và RAM, Persistent Disk đã tách khỏi máy nhưng vẫn bị tính phí, hay địa chỉ IP tĩnh không còn gắn với dịch vụ nào. Trong mô hình FinOps, việc phát hiện và xử lý những tài nguyên này được thực hiện liên tục, có bằng chứng và có người chịu trách nhiệm — không phải một chiến dịch xóa tài nguyên vô chủ vào cuối quý.

**Rightsizing** là điều chỉnh lượng tài nguyên được cấp để phù hợp nhu cầu thực tế mà vẫn đạt các mục tiêu hiệu năng, độ tin cậy và an toàn. **Idle resource cleanup** là xác minh, ngừng sử dụng hoặc loại bỏ tài nguyên không còn tạo giá trị. Trên Google Cloud, Compute Engine Recommender, Cloud Monitoring, Cloud Billing và công cụ quản lý tài nguyên giúp xác định ứng viên; quyết định thay đổi production vẫn cần được review theo ngữ cảnh ứng dụng.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt VM quá lớn, VM nhàn rỗi và tài nguyên không còn được sử dụng.
- Đọc machine type recommendations và idle VM recommendations trên Compute Engine.
- Kết hợp CPU, RAM, disk, network, lịch batch và SLO để đánh giá quyền thay đổi.
- Lập quy trình thay đổi kích thước VM có phê duyệt, rollback và kiểm chứng.
- Phát hiện Persistent Disk, custom image và static external IP nhàn rỗi.
- Hiểu khác biệt về chi phí khi stop, suspend, delete và snapshot.
- Ước tính savings thực tế bằng billing data thay vì chỉ nhìn giá niêm yết.
- Thiết lập ownership, nhãn, cảnh báo và automation để tránh lãng phí tái phát.
- Thiết kế một backlog tối ưu FinOps mà không ảnh hưởng workload quan trọng.

## 1. Rightsizing không đồng nghĩa chọn máy nhỏ nhất

Hệ thống có ba loại nhu cầu cần cân bằng:

- **Capacity đủ dùng**: phục vụ peak và tăng trưởng mà không vượt giới hạn CPU, memory, storage I/O hoặc network.
- **Availability và recovery**: duy trì headroom để xử lý failover, rollout và các tình huống bất thường.
- **Chi phí hợp lý**: không trả tiền cho vCPU, RAM hay tài nguyên khác không cần thiết.

Một VM chỉ dùng trung bình 8% CPU chưa chắc nên giảm mạnh kích thước. Nó có thể xử lý batch cuối tháng, giữ một dịch vụ standby hoặc dùng nhiều RAM dù CPU thấp. Ngược lại, một VM có CPU trung bình 45% nhưng thường xuyên bị memory pressure vẫn có thể cần đổi sang machine family phù hợp hơn.

### Phân biệt ba loại hành động

| Tình huống | Vấn đề | Hành động thường cân nhắc |
|---|---|---|
| Oversized VM | VM đang phục vụ việc thật nhưng vCPU/RAM dư đáng kể | Đổi machine type, điều chỉnh tài nguyên |
| Idle VM | VM gần như không xử lý công việc trong khoảng quan sát | Stop, lịch chạy hoặc loại bỏ sau xác minh |
| Unused resource | Disk, image, IP hoặc resource khác không còn được tham chiếu | Thu hồi, lưu bản sao cần thiết rồi delete |

Không chọn một hành động dựa trên một metric. Phân tích phải kết hợp loại workload, owner, vòng đời môi trường và ràng buộc vận hành.

## 2. Vòng lặp FinOps: Inform, Optimize, Operate

Một chương trình rightsizing cần thực hiện theo chu kỳ:

~~~text
Inventory + Labels + Billing
           |
           v
   Usage data / SLO / Recommender
           |
           v
       Triage ứng viên
           |
           v
 Owner xác nhận + Risk assessment
           |
           v
   Pilot / Change / Rollback plan
           |
           v
 Verify performance + Actual billing
           |
           v
   Review + Automation + Next cycle
~~~

**Inform** làm rõ ai đang sử dụng và đang trả chi phí cho resource. **Optimize** đánh giá và thực hiện thay đổi đúng ngữ cảnh. **Operate** chuyển bài học thành nhãn, chính sách, lịch review và kiểm soát liên tục.

Một báo cáo có 100 recommendations không đồng nghĩa 100 cơ hội tiết kiệm chắc chắn. Cần nhóm theo impact, mức độ tự tin, effort, dependency và mức rủi ro.

## 3. Dữ liệu cần thu thập trước khi resize

| Nhóm dữ liệu | Ví dụ | Lý do cần thiết |
|---|---|---|
| Tài nguyên | Project, zone, VM name, machine type, disks | Xác minh đúng đối tượng |
| Ownership | Team, service, environment, cost center | Ai được phê duyệt thay đổi |
| CPU | Trung bình, p95/p99, peak, spike | Tránh cấp thiếu CPU |
| RAM | Used/available, pressure, swap, OOM | Tránh lỗi do thiếu memory |
| Storage | Capacity, IOPS, throughput, latency | Machine type có thể ảnh hưởng thông lượng |
| Network | Throughput, packet rate, egress | Tránh nghẽn mạng khi giảm máy |
| Ứng dụng | Request throughput, latency, queue depth | Liên hệ với trải nghiệm người dùng |
| Vận hành | Batch window, backup, failover, maintenance | Không bỏ lỡ tác vụ không diễn ra thường xuyên |
| Chi phí | SKU thực trả, discounts, commitments, labels | Ước tính savings chính xác |
| Kiến trúc | MIG, autoscaling, instance template, HA | Chọn đúng nơi sửa cấu hình |

### CPU và RAM đo theo chu kỳ

Cloud Monitoring cung cấp CPU usage, disk và network metrics của Compute Engine. Với memory và process-level metrics, việc cài Ops Agent hoặc cơ chế telemetry thích hợp có thể cải thiện dữ liệu đánh giá.

Nên xem cả:

- Giờ làm việc và ngoài giờ.
- Ngày thường/cuối tuần.
- Batch hoặc backup theo lịch.
- Kỳ thanh toán, cao điểm mua sắm và các sự kiện mùa vụ.
- Sự cố hoặc failover có thể khiến một VM phải gánh tải nhiều hơn.

Không nên dùng một con số trung bình trên dashboard để quyết định ngay. Một service có p99 latency nhạy với CPU spike cần headroom dù mức sử dụng bình quân thấp.

## 4. Machine type recommendations của Compute Engine

Compute Engine Recommender đề xuất kích thước VM dựa trên CPU và memory metrics có sẵn. Theo tài liệu Google Cloud, cơ chế phổ biến sử dụng **8 ngày dữ liệu gần nhất**; các thống kê CPU thường dựa trên khoảng trung bình 60 giây nên có thể bỏ qua spike rất ngắn.

Recommender có thể gợi ý:

- Giảm vCPU khi mức sử dụng CPU thấp trong phần lớn thời gian.
- Giảm RAM khi memory không được dùng tới.
- Tăng vCPU hoặc RAM nếu VM thường xuyên bị thiếu tài nguyên.
- Chọn standard hoặc custom machine type phù hợp với ràng buộc của dòng máy.

Recommendation là **tín hiệu để đánh giá**, không phải mệnh lệnh áp dụng. Một số resource không hỗ trợ gợi ý; tài liệu cũng ghi nhận các giới hạn đối với VM có GPU/TPU, một số loại disk, memory-optimized machine families và VM do dịch vụ khác tạo.

### Xem recommendation trong Console

1. Chọn đúng project và mở Compute Engine → VM instances.
2. Xem cột Recommendations để tìm máy có gợi ý thay đổi.
3. Mở chi tiết để xem machine type đề xuất và savings dự kiến.
4. Đối chiếu với Cloud Monitoring, SLO và lịch tải.
5. Ghi nhận quyết định: accept, defer hoặc dismiss cùng lý do.

Một VM không có recommendation chưa chắc đã được tối ưu. Có thể thiếu dữ liệu, workload không hỗ trợ hoặc mức tiết kiệm dưới ngưỡng mà Recommender hiển thị.

### Xem gợi ý bằng gcloud

Lệnh chỉ đọc:

~~~bash
gcloud recommender recommendations list \
  --project=PROJECT_ID \
  --location=ZONE \
  --recommender=google.compute.instance.MachineTypeRecommender \
  --format=yaml
~~~

Cần quyền đọc recommendation tương ứng; việc xem gợi ý không cần quyền thay đổi VM. Đầu ra có mô tả, tác động ước tính và các operation được đề xuất. Kiểm tra tên resource và zone trong payload trước khi lập change ticket.

### Đánh giá độ tin cậy của gợi ý

| Câu hỏi | Nếu chưa rõ |
|---|---|
| Dữ liệu có bao phủ peak cuối tuần/tháng? | Kéo dài quan sát bằng telemetry khác |
| Agent có memory metric đầy đủ? | Bổ sung Ops Agent và benchmark |
| Có batch job chỉ chạy mỗi tháng? | Review scheduler và job history |
| VM là standby hay disaster recovery? | Giữ capacity theo RTO/RPO |
| Có giới hạn license hoặc CPU architecture? | Xác minh compatibility trước resize |
| Có yêu cầu throughput disk/network tối thiểu? | Kiểm tra tài liệu machine type |
| VM thuộc Managed Instance Group? | Chỉnh instance template/MIG, không chỉ một VM |

## 5. Một checklist đánh giá trước khi giảm machine type

Một change request tốt trả lời được các câu hỏi sau:

1. Đây là project và VM của môi trường nào?
2. Service owner và approver là ai?
3. Máy có phục vụ load balancer, database, job hoặc instance group không?
4. Dữ liệu peak/p95/p99 trong kỳ đại diện thế nào?
5. CPU/memory hiện tại và cấu hình target?
6. Các giới hạn storage, network bandwidth, disk count, license và architecture?
7. Cần dừng VM trong bao lâu, lịch thay đổi nào được phê duyệt?
8. Có snapshot/backup và thủ tục rollback đủ khả thi?
9. Các SLI nào phải giữ ổn định sau thay đổi?
10. Khi nào xem lại recommendation và chi phí thực trả?

**Không resize trực tiếp production bằng một click khi chưa xác định downtime và rollback.** Thao tác đổi machine type thường yêu cầu stop VM, thay đổi cấu hình rồi start; vì vậy có thể gây gián đoạn.

## 6. Ví dụ: rightsizing một VM ứng dụng Java

Giả sử VM phục vụ Spring Boot API có cấu hình:

| Thuộc tính | Trạng thái hiện tại | Quan sát |
|---|---|---|
| Machine type | 8 vCPU, 32 GiB RAM | Ví dụ giả định |
| CPU median | 11% | 3 tuần dữ liệu |
| CPU p95 | 32% | Không phải peak tuyệt đối |
| RAM p95 | 14 GiB | Có 1 đợt batch tăng lên 20 GiB |
| Disk read/write | Thấp | Không có I/O bottleneck |
| Network | Thấp | Có burst khi chạy export |
| Availability | 99,9% SLO | Chạy sau load balancer |

Một phương án là thử máy 4 vCPU, 24 GiB RAM (nếu machine family/zone cho phép cấu hình đó) thay vì giảm về 2 vCPU và 8 GiB. Cần benchmark tải, khả năng scale/failover và thời gian GC.

### Quy trình thay đổi có kiểm soát

**Bước 1 – Kiểm tra trước khi thay đổi**

~~~bash
gcloud compute instances describe VM_NAME \
  --project=PROJECT_ID \
  --zone=ZONE \
  --format="yaml(name,status,machineType,disks,networkInterfaces,labels)"
~~~

Lưu lại output có kiểm soát; không đưa thông tin nhạy cảm vào ticket công khai. Ghi nhận machine type cũ và dữ liệu monitoring.

**Bước 2 – Đánh giá khả năng backup và phục hồi**

Nếu VM lưu dữ liệu quan trọng, xác minh backup/snapshot phù hợp, application consistency và quyền restore. Không chỉ tạo snapshot ngẫu nhiên rồi coi đó là phương án rollback hoàn chỉnh.

**Bước 3 – Thực hiện trong maintenance window**

Sau khi có phê duyệt và kiểm tra ràng buộc machine type:

~~~bash
gcloud compute instances stop VM_NAME \
  --project=PROJECT_ID \
  --zone=ZONE

gcloud compute instances set-machine-type VM_NAME \
  --project=PROJECT_ID \
  --zone=ZONE \
  --machine-type=TARGET_MACHINE_TYPE

gcloud compute instances start VM_NAME \
  --project=PROJECT_ID \
  --zone=ZONE
~~~

Các lệnh trên **thay đổi trạng thái production**. Chúng chỉ là runbook minh họa, không được chạy tự động trong quy trình phân tích. VM có Local SSD, GPU, license đặc thù hoặc service management có thể cần bước khác.

**Bước 4 – Verify**

- VM đã RUNNING và health check đạt.
- Java service khởi động, kết nối database/secret hoạt động.
- CPU, RAM, GC, p95/p99 latency và error rate trong ngưỡng.
- Batch/scheduler và export còn chạy đúng.
- Không tăng timeout, retry hoặc queue backlog.
- Billing sau chu kỳ đủ dài phản ánh chi phí mới.

**Bước 5 – Rollback**

Nếu SLO/hiệu năng suy giảm, dừng máy theo quy trình rồi khôi phục machine type ban đầu. Phương án cần kiểm tra capacity/quota ở zone và thời gian hồi phục, không giả định đổi lại sẽ luôn tức thời.

### VM thuộc Managed Instance Group

Nếu workload nằm trong MIG, cấu hình machine type thường được quản lý qua instance template hoặc cơ chế cập nhật MIG, không thao tác thủ công trên một VM rồi mong thay đổi tồn tại sau recreate. Cần chỉnh nguồn cấu hình, kiểm soát rolling update/canary và đo sức chứa nhóm.

## 7. Idle VM recommendations

**Idle VM** là VM có chỉ số CPU và network rất thấp theo điều kiện của Recommender trong khoảng quan sát. Theo tài liệu hiện hành, mặc định idle VM Recommender quan sát **14 ngày**, có thể cấu hình từ 1 đến 14 ngày trong một số trường hợp.

Một VM bị coi idle không có nghĩa là vô chủ hoặc có thể xóa. Nó có thể:

- Là máy dự phòng failover.
- Chạy batch cuối tháng.
- Là bastion hoặc máy vận hành cần bật khi sự cố.
- Đóng vai trò build agent theo lịch không đều.
- Là môi trường thử nghiệm tạm giữ phục vụ một dự án.

### Xem idle VM recommendations

~~~bash
gcloud recommender recommendations list \
  --project=PROJECT_ID \
  --location=ZONE \
  --recommender=google.compute.instance.IdleResourceRecommender \
  --format=yaml
~~~

Cần quyền xem recommendation phù hợp trong project. Ghi lại tên VM, thời gian quan sát và owner, rồi đối chiếu job scheduler, audit logs, network traffic và kết quả phỏng vấn ứng dụng.

### Chọn hành động

| Tình huống | Quyết định khuyến nghị |
|---|---|
| VM dev chỉ dùng giờ hành chính | Stop/start theo lịch nếu không có dependency ngoài giờ |
| VM test đã hết dự án | Tag candidate, giữ quarantine rồi xóa sau phê duyệt |
| VM warm standby cho sự cố | Giữ lại và ghi rõ exception/DR purpose |
| VM chỉ chạy báo cáo cuối tháng | Chuyển sang execution theo lịch hoặc giữ capacity có lý do |
| VM production đang idle bất thường | Điều tra routing, workload hoặc deployment trước khi stop |
| VM quá lớn nhưng vẫn cần bật 24/7 | Rightsize thay vì stop |

## 8. Stop, suspend, delete khác nhau về chi phí và rủi ro

| Hành động | Ảnh hưởng | Điều cần lưu ý |
|---|---|---|
| Stop VM | Dừng CPU/runtime, giữ cấu hình và disk | Disk, snapshot và external IP còn có thể bị tính phí |
| Suspend VM | Giữ trạng thái memory theo khả năng hỗ trợ | Có thể phát sinh phí lưu trạng thái; không phải mọi VM hỗ trợ |
| Delete VM | Xóa instance resource | Disk auto-delete, Local SSD và IP có thể bị ảnh hưởng; cần backup và review |
| Schedule start/stop | Chỉ chạy trong khung cần thiết | Phải xét timezone, batch và on-call |
| Rightsize | Đổi vCPU/RAM/machine type | Có thể cần downtime và benchmark |

**Stop không đồng nghĩa hóa đơn bằng 0.** Persistent Disk, snapshot, reservation hoặc static external IP vẫn có thể tạo chi phí. Ngoài ra, quyền truy cập, external IP tạm và dữ liệu Local SSD cần được xem xét khi dừng.

### Quy trình stop an toàn

1. Xác nhận owner và môi trường.
2. Kiểm tra workloads, connection, background jobs và dependency.
3. Bảo đảm không phải VM trong MIG/managed system đang kỳ vọng được tự khởi động.
4. Lập thời gian stop và cửa sổ quan sát.
5. Có runbook start lại, kiểm tra readiness và DNS/IP.
6. Ghi nhận chi phí còn lại của disk/IP.
7. Không delete trước khi kết thúc thời gian quarantine.

Một VM đã dừng có thể giữ nguyên disk và cấu hình đủ để rollback nhanh hơn delete. Tuy nhiên, disk lâu không sử dụng tiếp tục làm tăng bill; sau thời gian retention cần quyết định archive/snapshot hoặc xóa theo policy.

## 9. Dọn tài nguyên không được dùng: disks, images và IPs

Compute Engine có nhóm Recommender khác để nhận diện một số loại idle resources: Persistent Disk, custom images và external IP addresses. Theo tài liệu Google Cloud, nhiều trường hợp được xem xét sau khoảng **15 ngày** không sử dụng/không gắn, nhưng điều kiện khác nhau theo loại tài nguyên.

| Resource | Dấu hiệu đáng kiểm tra | Rủi ro khi thu hồi |
|---|---|---|
| Persistent Disk | Disk chưa từng attach hoặc đã detach lâu | Có thể chứa dữ liệu, snapshot hoặc forensic evidence |
| Custom image | Không dùng tạo disk và không được template tham chiếu | Có thể là golden image dùng cho DR |
| Static external IP | Không gắn với resource | Có thể nằm trong DNS/partner allowlist |
| Snapshot | Cũ, trùng retention hoặc không owner | Có thể là điểm khôi phục duy nhất |
| VM image version | Không được deploy trong thời gian dài | Có thể phục vụ rollback hoặc compliance |
| Load balancer/resource phụ | Backend không còn sử dụng | Có thể là điểm entry dự phòng |

Không phải mọi loại trong bảng đều có Recommender chuyên biệt hoặc cùng ngưỡng. Với snapshots và các dịch vụ khác, cần inventory, policy hoặc billing analytics bổ sung.

### Xem idle disk recommendations

~~~bash
gcloud recommender recommendations list \
  --project=PROJECT_ID \
  --location=ZONE \
  --recommender=google.compute.disk.IdleResourceRecommender \
  --format=yaml
~~~

Với external IP cấp vùng:

~~~bash
gcloud recommender recommendations list \
  --project=PROJECT_ID \
  --location=REGION \
  --recommender=google.compute.address.IdleResourceRecommender \
  --format=yaml
~~~

Với custom images, location là global:

~~~bash
gcloud recommender recommendations list \
  --project=PROJECT_ID \
  --location=global \
  --recommender=google.compute.image.IdleResourceRecommender \
  --format=yaml
~~~

### Inventory bằng gcloud

~~~bash
gcloud compute disks list \
  --project=PROJECT_ID \
  --format="table(name,zone,status,sizeGb,users)"

gcloud compute addresses list \
  --project=PROJECT_ID \
  --format="table(name,region,status,address)"

gcloud compute images list \
  --project=PROJECT_ID \
  --no-standard-images \
  --format="table(name,creationTimestamp,status)"
~~~

Những lệnh trên chỉ đọc. Không dùng việc trường users trống làm bằng chứng đầy đủ để xóa disk; disk có thể đang giữ dữ liệu quan trọng hoặc dành cho phục hồi.

### Disk đã detach

Trước khi xóa disk đã detach:

1. Xác minh nó không nằm trong quy trình restore, GKE PV hoặc forensic investigation.
2. Kiểm tra nội dung, encryption và application ownership theo quy trình an toàn.
3. Nếu cần retention, tạo snapshot phù hợp và kiểm tra restore.
4. Ghi nhận snapshot ID, retention, owner và chính sách xóa.
5. Chỉ xóa disk khi được owner phê duyệt.

Snapshot có thể rẻ hơn disk nhưng không phải lúc nào cũng vậy; chi phí phụ thuộc loại disk, vị trí, kích thước thực lưu và chính sách lưu trữ.

### Static external IP không gắn

Địa chỉ không attached có thể vẫn nằm trong DNS, firewall allowlist hoặc cấu hình đối tác. Trước khi release:

- Kiểm tra Cloud DNS, record ngoài GCP và tài liệu đối tác.
- Xác minh không phục vụ DR/cutover.
- Kiểm tra có service nào được cấu hình hardcode IP.
- Cho owner thời gian xác nhận và quarantine.
- Ghi nhật ký thay đổi vì release IP có thể không lấy lại được.

## 10. Ước tính savings đúng cách

Cần phân biệt **potential savings** với **realized savings**.

Potential savings là ước tính từ recommendation hoặc mô hình. Realized savings là phần chi phí thực tế giảm sau khi thay đổi, đã xét workload, discount và chi phí phát sinh.

### Ví dụ giả định

Một VM có:

- Chi phí compute hiện tại: 300 USD/tháng.
- Machine type mới dự kiến: 190 USD/tháng.
- Chi phí thực hiện và kiểm thử: 200 USD một lần.
- Disk và network: giữ nguyên.

Tiết kiệm compute dự kiến mỗi tháng:

~~~text
300 - 190 = 110 USD/tháng
~~~

Trong 12 tháng, trước các biến số khác:

~~~text
110 × 12 - 200 = 1.120 USD
~~~

Các số này chỉ minh họa, không phải giá Compute Engine. Nếu VM đang được hưởng committed use discount hoặc sustained use discount, savings thực tế có thể khác. Nếu commitment vẫn phải trả, việc giảm VM không tự làm giảm phí cam kết.

### Công thức tài chính tham khảo

~~~text
Net realized savings
  = Chi phí baseline đã chuẩn hóa
  - Chi phí mới cùng phạm vi workload
  - Chi phí vận hành/tài nguyên phát sinh
  - Chi phí thay đổi phân bổ theo kỳ
~~~

Một biến động hóa đơn vì số request giảm không nên được ghi toàn bộ thành savings do rightsizing. Cần chuẩn hóa theo demand, ví dụ cost per request, cost per batch hoặc số giờ phục vụ.

### Billing export và nhãn

Cloud Billing export sang BigQuery cho phép phân tích theo project, service, SKU, labels, credits và thời gian. Dùng cost allocation labels để gắn resource vào team, cost center và environment. Với các bảng dữ liệu nhạy cảm về tài chính, hạn chế IAM và chỉ cấp quyền phân tích cần thiết.

Không so sánh thô hai tháng khác số ngày mà không quy đổi giờ hoặc lượng request. Sau khi stop VM, disk/IP có thể vẫn tính phí; giữ chúng trong baseline và actual comparison.

## 11. Quy trình FinOps vận hành hàng tuần

Một quy trình có thể bắt đầu đơn giản:

| Ngày/hoạt động | Người phụ trách | Đầu ra |
|---|---|---|
| Đầu tuần: thu thập recommendations | FinOps/Platform | Backlog ứng viên |
| Triage và gắn owner | Platform + app owners | Danh sách có risk/impact |
| Kiểm tra telemetry và dependency | SRE/App team | Quyết định accept/defer/dismiss |
| Review change plan | Change owner | Downtime, rollback và approver |
| Thực hiện theo lịch | Operations | Log thay đổi và verification |
| Cuối kỳ: đối chiếu billing | FinOps | Savings thực tế và lessons learned |

### Trạng thái một recommendation

- **New**: mới được phát hiện, chưa có owner.
- **Investigating**: đang kiểm tra metrics và dependency.
- **Approved**: có kế hoạch change và rollback.
- **Applied**: đã thay đổi resource.
- **Verified**: đạt SLO và chi phí phù hợp.
- **Deferred**: hoãn có lý do/điều kiện xem lại.
- **Rejected**: không phù hợp, có bằng chứng.
- **Exempt**: tài nguyên cần giữ vì standby, DR hoặc compliance.

Không chỉ đếm số recommendations đã đóng. KPI tốt hơn gồm số tiền thực tiết kiệm, mức SLO giữ ổn định, tỷ lệ ứng viên có owner, thời gian xử lý và tỷ lệ phát hiện sai.

## 12. Tự động hóa dọn tài nguyên nhưng có guardrails

Có thể dùng Cloud Scheduler, Cloud Functions/Cloud Run jobs, Pub/Sub và Workflows để phát hiện hoặc lên lịch xử lý tài nguyên. Tuy nhiên, tự động xóa resource dựa trên một metric thấp là rủi ro lớn.

Một thiết kế an toàn:

~~~text
Recommender + Cloud Asset Inventory
             |
             v
   Scheduled discovery job
             |
             v
   Labels + owner + exclusion rules
             |
             v
   Candidate report / ticket
             |
             v
   Owner approve + grace period
             |
             v
   Stop / snapshot / release (phê duyệt riêng)
             |
             v
   Verify + actual billing + audit
~~~

### Các guardrails nên có

- Dry-run mặc định, không tự execute các hành động phá hủy.
- Denylist/allowlist theo project, folder, environment và resource.
- Nhãn như owner, cost-center, environment, lifecycle, retention-until.
- Tôn trọng resource có deletion protection hoặc thuộc Managed Instance Group.
- Xác minh dependency và lịch batch dài hơn cửa sổ Recommender.
- Hai cấp phê duyệt cho database, disk chứa dữ liệu và production.
- Bản sao/restore đã thử trước khi delete dữ liệu quan trọng.
- Log thay đổi, rollback và escalation path.
- Giới hạn số resource thay đổi trong một lần chạy.
- Không tự gỡ nhãn hoặc quyền để vượt qua policy.

### Ví dụ policy

Một VM development chỉ được tự stop nếu:

- Có nhãn environment=dev.
- Owner đồng ý lịch chạy.
- Không có batch hoặc integration test trong khoảng stop.
- Không thuộc MIG/cluster bị điều phối tự động.
- Có script start lại và smoke test.
- Đã đo savings sau một vài chu kỳ.

Nếu bất kỳ điều kiện nào không chắc chắn, tạo ticket thay vì stop.

## 13. Tình huống thực tế: dọn môi trường thử nghiệm Java

Một nhóm phát triển Java/Spring đã tạo:

- 6 VM chạy integration tests.
- 3 Persistent Disk tách khỏi máy cũ.
- 2 static external IP không attached.
- 1 custom image cũ không còn trong instance template.
- 1 VM production standby có CPU thấp.

### Bước 1 — Thu thập và phân loại

FinOps lấy báo cáo idle VM và idle resources, gắn từng đối tượng với owner, repository, pipeline hoặc application. VM production standby được đánh dấu **exception** với lý do và RTO/RPO, không xóa theo CPU.

### Bước 2 — Kiểm tra usage

Logs cho thấy 6 VM test chỉ cần chạy 9:00–18:00 ngày làm việc, nhưng pipeline nightly có một test suite lúc 22:00. Nhóm điều chỉnh lịch test hoặc giữ một pool có thể khởi tạo theo demand, thay vì stop toàn bộ máy ngay 18:00.

### Bước 3 — Thử nghiệm thay đổi

Trong staging:

- Giảm machine type cho hai VM sau benchmark.
- Thiết lập lịch stop/start cho VM development được owner phê duyệt.
- Kiểm tra khả năng khởi động lại test harness.
- Tạo snapshot cho disk còn dữ liệu cần lưu.
- Xác minh external IP không nằm trong DNS hoặc allowlist.

### Bước 4 — Dọn tài nguyên

Sau thời gian quarantine và phê duyệt:

- Delete disk không còn cần giữ, chỉ sau khi đánh giá dữ liệu.
- Release IP không còn được dùng.
- Xóa custom image nếu không thuộc quy trình rollback/DR.
- Giữ nguyên VM standby và ghi rõ lý do exception.

### Bước 5 — Đo hiệu quả

Đối chiếu Cloud Billing trước/sau, loại trừ ảnh hưởng do số lượng test thay đổi. Đồng thời theo dõi test pass rate, thời gian startup, job duration và chi phí/CI run để tránh tiết kiệm chi phí hạ tầng nhưng làm giảm năng suất nhóm.

## 14. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Quyết định theo CPU trung bình một ngày | Bỏ lỡ peak hoặc batch | Quan sát nhiều chu kỳ và p95/p99 |
| Xem recommendation như lệnh bắt buộc | Có thể phá SLO | Review owner, workload và constraints |
| Stop VM rồi cho rằng không còn chi phí | Disk/IP/snapshot vẫn bị tính tiền | Theo dõi toàn bộ related resources |
| Delete idle disk không kiểm tra dữ liệu | Mất dữ liệu hoặc mất bản restore | Quarantine, snapshot, restore test |
| Xóa external IP không kiểm tra đối tác | DNS/allowlist bị hỏng | Dependency review trước release |
| Resize VM trong MIG trực tiếp | Cấu hình bị recreate hoặc không đồng bộ | Chỉnh instance template và rollout |
| Chọn máy nhỏ bỏ qua IOPS/network | Hiệu năng suy giảm | Kiểm tra limits machine type |
| Bỏ qua CUD và credits | Tính sai realized savings | Dùng Billing export và pricing thực |
| Dùng cùng rule cho dev và prod | Vô tình stop workload quan trọng | Policy theo environment và criticality |
| Tự động xóa theo thiếu owner label | Dữ liệu có thể mất | Missing owner phải là ticket, không phải lý do delete |
| Không thử rollback | Downtime kéo dài khi đổi kích thước | Runbook, capacity verification và smoke tests |
| Chỉ đếm số gợi ý đã áp dụng | Không biết giá trị tài chính thực | Đo savings, SLO và operation effort |

## 15. Checklist trước khi áp dụng production

### Discover và phân loại

- [ ] Đã xác nhận project, zone, resource ID và owner.
- [ ] Có chi phí baseline theo workload và môi trường.
- [ ] Đã xem machine type và idle resource recommendations.
- [ ] Có đủ CPU, RAM, disk/network và telemetry ứng dụng.
- [ ] Đã kiểm tra batch, backup, failover và peak dài hơn cửa sổ quan sát.
- [ ] Đã đánh dấu exceptions: DR, standby, licensed/special hardware.
- [ ] Đã loại trừ resource thuộc service được điều phối riêng.

### Change và rollback

- [ ] Target machine type phù hợp CPU/RAM/IOPS/network constraints.
- [ ] Có change ticket, approver, maintenance window và SLA.
- [ ] Có backup/restore strategy cho resource chứa dữ liệu.
- [ ] Có runbook stop/resize/start hoặc snapshot/delete.
- [ ] Có plan khôi phục machine type, service và network.
- [ ] Không có resource bị stop/delete chỉ dựa trên một metric.
- [ ] Đã kiểm tra health, SLO và business flow sau thay đổi.

### FinOps và vận hành liên tục

- [ ] Billing sau thay đổi được so với baseline đã chuẩn hóa.
- [ ] Phí disk, snapshot, external IP và commitments được tính đến.
- [ ] Labels owner/environment/cost center được áp dụng.
- [ ] Có review định kỳ, audit trail và exception policy.
- [ ] Automation có dry-run, approval và giới hạn blast radius.
- [ ] Savings được ghi nhận sau verification, không chỉ dự báo.
- [ ] Không làm content QA hoặc infrastructure deployment ngoài phạm vi bài học.

## Kết luận

Rightsizing VM và dọn tài nguyên nhàn rỗi là hoạt động FinOps dựa trên dữ liệu và trách nhiệm rõ ràng. Compute Engine Recommender giúp phát hiện VM có thể thay đổi kích thước, VM ít hoạt động, disk, image và IP có dấu hiệu không sử dụng. Nhưng một recommendation chỉ là điểm khởi đầu: nhóm phải kiểm tra workload, owner, memory, IOPS/network, peak, SLO và quy trình rollback trước khi thực hiện. Sau thay đổi, Cloud Billing và telemetry ứng dụng mới cho biết savings thực tế có bền vững hay không. Khi được tổ chức thành vòng lặp có guardrails, rightsizing sẽ giảm lãng phí mà vẫn bảo vệ độ tin cậy của dịch vụ trên GCP.

## Tài liệu tham khảo

- [Compute Engine: Machine type recommendations](https://docs.cloud.google.com/compute/docs/instances/apply-machine-type-recommendations-for-instances)
- [Compute Engine: Idle VM recommendations overview](https://docs.cloud.google.com/compute/docs/instances/idle-vm-recommendations-overview)
- [Compute Engine: View and apply idle VM recommendations](https://docs.cloud.google.com/compute/docs/instances/viewing-and-applying-idle-vm-recommendations)
- [Compute Engine: Idle resources recommendations](https://docs.cloud.google.com/compute/docs/viewing-and-applying-idle-resources-recommendations)
- [Compute Engine: Stop or restart instances](https://docs.cloud.google.com/compute/docs/instances/stop-start-instance)
- [Compute Engine: Change machine types](https://docs.cloud.google.com/compute/docs/instances/changing-machine-type-of-stopped-instance)
- [Compute Engine: Managed Instance Group rightsizing](https://docs.cloud.google.com/compute/docs/instance-groups/apply-machine-type-recommendations-managed-instance-groups)
- [Cloud Billing: Export billing data to BigQuery](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery)
- [Cloud Billing: Cost optimization](https://docs.cloud.google.com/billing/docs/how-to/cost-management)
- [Google Cloud Recommender documentation](https://docs.cloud.google.com/recommender/docs)
- [Cloud Monitoring documentation](https://docs.cloud.google.com/monitoring/docs)

