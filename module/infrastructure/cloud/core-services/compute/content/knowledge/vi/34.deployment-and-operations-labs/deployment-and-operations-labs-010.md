# Thu hồi tài nguyên thực hành và kiểm tra chi phí còn phát sinh

Sau một bài thực hành cloud, việc dừng máy ảo hoặc xóa ứng dụng chưa chắc đã kết thúc chi phí. Ổ đĩa, snapshot, địa chỉ IP tĩnh, NAT gateway, load balancer, database, backup, log, registry, cluster và tài nguyên mạng có thể tiếp tục tồn tại sau khi workload chính đã dừng. Một số cam kết sử dụng, license hoặc gói hỗ trợ còn tính phí theo hợp đồng dù tài nguyên đã bị xóa.

**Thu hồi tài nguyên thực hành** là quy trình xác định đúng phạm vi lab, dừng các nguồn tạo tải, xóa tài nguyên theo quan hệ phụ thuộc và xác minh phần còn lại. **Kiểm tra chi phí còn phát sinh** là bước đối chiếu inventory sau cleanup với báo cáo billing, usage và các cam kết tính phí để phát hiện khoản phí tiếp tục tăng.

Mục tiêu của bài thực hành là kết thúc một môi trường lab có kiểm soát, giữ lại dữ liệu cần thiết theo yêu cầu, tránh xóa nhầm tài nguyên dùng chung và xác nhận được những khoản chi phí nào đã dừng, khoản nào còn chờ dữ liệu billing cập nhật hoặc vẫn tiếp tục theo hợp đồng.

## 1. Vì sao xóa workload chưa chắc đã dừng chi phí?

Một môi trường thực hành thường gồm nhiều tài nguyên được tạo bởi các lớp khác nhau: ứng dụng, compute, storage, network, identity và dịch vụ quản lý. Xóa thành phần hiển thị đầu tiên có thể để lại tài nguyên độc lập hoặc tài nguyên được tạo tự động.

Ví dụ, xóa một VM có thể không xóa ổ đĩa dữ liệu nếu chính sách giữ lại disk được bật. Xóa Kubernetes cluster có thể không xóa persistent volume, snapshot, địa chỉ IP hoặc load balancer được tạo bởi controller. Dừng database có thể giảm phí compute nhưng storage và backup vẫn được tính. Tắt autoscaling không xóa những node đã được cấp phát.

Các nhóm chi phí thường còn tồn tại:

| Nhóm | Tài nguyên có thể còn lại | Vì sao vẫn phát sinh chi phí |
|---|---|---|
| Compute | VM đã stop/deallocate, node pool, dedicated host, GPU instance | Một số loại tài nguyên vẫn tính phí khi dừng; host hoặc reservation có thể tính theo thời hạn |
| Storage | Persistent disk, block volume, snapshot, backup, object version | Tính phí theo dung lượng lưu, số bản sao hoặc thời gian giữ |
| Network | NAT gateway, load balancer, public IP, VPN gateway, private endpoint | Có phí theo giờ, capacity, địa chỉ hoặc lưu lượng |
| Database | Instance đã dừng, storage, read replica, backup tự động | Storage, backup hoặc standby có thể tiếp tục được tính |
| Container | Cluster, node, persistent volume, registry image | Cluster control plane, node, volume và dung lượng image có vòng đời riêng |
| Observability | Log, metric, trace, dashboard, alert, log archive | Dữ liệu đã thu thập tiếp tục được lưu theo retention |
| Data transfer | Egress, cross-region replication, CDN, NAT processing | Lưu lượng đã phát sinh được ghi nhận sau đó; replication có thể tiếp tục chạy |
| Serverless và event | Scheduler, trigger, queue, workflow, subscription | Sự kiện mới tiếp tục kích hoạt workload hoặc tạo lượt gọi |
| Cam kết và license | Savings plan, reserved capacity, committed use, marketplace subscription, support plan | Nghĩa vụ hợp đồng hoặc license không tự kết thúc khi xóa workload |

Do đó, cần xem cleanup là một quy trình theo vòng đời tài nguyên và billing, không chỉ là lệnh xóa ứng dụng.

## 2. Xác định đúng phạm vi lab trước khi thu hồi

Trước khi xóa, lập danh sách tài nguyên thuộc đúng lần thực hành. Tên resource, tag/label và project/resource group giúp phân biệt lab với môi trường dùng chung.

Một bộ metadata hữu ích:

| Trường | Ví dụ | Mục đích |
|---|---|---|
| Environment | lab | Nhận diện môi trường |
| LabId | compute-lab-2026-11-22 | Gom tài nguyên của một lần thực hành |
| Owner | learner-team-a | Xác định người chịu trách nhiệm |
| ExpiresAt | 2026-11-23T18:00:00Z | Thời điểm cần rà soát/thu hồi |
| CostCenter | training | Phân bổ chi phí |
| KeepUntil | 2026-12-01 | Đánh dấu dữ liệu cần giữ tới hạn |

Nên gắn tag/label ngay khi tạo tài nguyên. Nếu một dịch vụ không hỗ trợ tag, ghi ID và quan hệ của nó trong manifest lab. Không nên suy ra quyền sở hữu chỉ từ tên gần giống; cần đối chiếu project, subscription, account, region, owner và thời điểm tạo.

Ví dụ manifest tài nguyên của một lab:

~~~yaml
lab:
  id: compute-lab-2026-11-22
  environment: lab
  owner: learner-team-a
  expiresAt: "2026-11-23T18:00:00Z"
  resources:
    - provider: cloud-a
      type: virtual-machine
      id: vm-compute-demo
      region: region-1
    - provider: cloud-a
      type: persistent-disk
      id: disk-compute-demo
      region: region-1
    - provider: cloud-a
      type: public-ip
      id: ip-compute-demo
      region: region-1
  retainedData:
    - id: lab-results
      keepUntil: "2026-12-01"
~~~

Đây là manifest minh họa để theo dõi, không phải schema lệnh của một nhà cung cấp. Manifest thực tế cần lưu ID chính xác và trạng thái thu hồi của từng tài nguyên.

### 2.1. Kiểm tra quyền và chủ sở hữu

Trước khi thao tác, xác nhận:

- Đang ở đúng cloud account, project hoặc subscription.
- Đúng region/zone và đúng môi trường lab.
- Tài nguyên mang tag/label của lab hoặc có trong manifest.
- Tài nguyên không được chia sẻ với bài thực hành khác, nhóm khác hoặc dịch vụ production.
- Đã xác định ai có quyền phê duyệt xóa dữ liệu và tài nguyên dùng chung.
- Có quyền đọc billing và inventory đủ để kiểm tra kết quả.

Nếu không xác định được quyền sở hữu hoặc quan hệ phụ thuộc, đưa tài nguyên vào danh sách cần xác minh thay vì xóa theo phỏng đoán.

## 3. Lập inventory và dependency graph

Một cleanup tốt bắt đầu bằng inventory đầy đủ. Hãy tìm tài nguyên theo tag/label, project/resource group, thời điểm tạo, quan hệ attachment và dịch vụ đã triển khai.

Cần kiểm tra ít nhất:

- VM, instance group, autoscaling group, node pool, GPU và máy chuyên dụng.
- Container cluster, service, task, job, persistent volume và volume attachment.
- Disk, snapshot, machine image, backup và object storage.
- Database, replica, cache, queue, topic và workflow.
- Load balancer, NAT gateway, public IP, VPN, firewall attachment, private endpoint và DNS.
- Registry, artifact, log group, metric, trace và backup archive.
- Scheduler, event rule, trigger, subscription và serverless deployment.
- Secret, certificate, service account và role sau khi workload đã ngừng.

Biểu diễn quan hệ phụ thuộc trước khi xóa:

~~~mermaid
flowchart TD
    A["Scheduler / event trigger"] --> B["Application / container service"]
    B --> C["Compute node / VM"]
    B --> D["Load balancer"]
    C --> E["Persistent disk"]
    C --> F["Network interface"]
    D --> G["Public IP"]
    C --> H["NAT / route"]
    B --> I["Database"]
    B --> J["Object storage"]
    B --> K["Queue"]
    I --> L["Backup / snapshot"]
    J --> M["Versioned objects"]
~~~

Thứ tự thu hồi cần tính tới dependency. Ví dụ, dừng trigger trước để không tạo thêm job; dừng workload trước khi xóa database hoặc queue; xóa service gắn load balancer trước khi xóa load balancer; kiểm tra volume và snapshot trước khi xóa cluster.

Inventory sau cleanup phải được chạy lại. Không nên chỉ dựa vào danh sách đã tạo ban đầu vì controller hoặc dịch vụ managed có thể tạo thêm tài nguyên trong quá trình thực hành.

## 4. Quy trình thu hồi an toàn theo thứ tự

Có thể dùng quy trình sau cho một lab thông thường:

### Bước 1: Đóng băng hoạt động tạo tài nguyên

- Dừng pipeline hoặc script tự động có thể tái tạo lab.
- Tắt scheduler, cron, event trigger và autoscaling policy tạo workload mới.
- Ngừng gửi traffic hoặc message vào môi trường.
- Đánh dấu lab ở trạng thái cleanup để người khác không tiếp tục sử dụng.
- Ghi lại số lượng job, replica, instance và message đang xử lý.

Nếu chỉ xóa VM trong khi autoscaling hoặc deployment controller vẫn hoạt động, controller có thể tạo VM mới. Nếu queue còn message và consumer vẫn hoạt động, workload có thể tiếp tục phát sinh chi phí.

### Bước 2: Lưu dữ liệu cần giữ

Xác định dữ liệu cần giữ theo yêu cầu bài học hoặc nhóm:

- Kết quả thực hành, log điều tra hoặc báo cáo.
- Database dump hoặc snapshot cần cho lần học tiếp theo.
- File đầu vào/đầu ra có thời hạn lưu.
- Manifest, cấu hình và metadata cần tái lập lab.

Kiểm tra bản sao lưu có thể đọc/khôi phục trước khi xóa nguồn nếu dữ liệu quan trọng. Ghi rõ owner, vị trí, encryption, retention và ngày hết hạn. Không tạo snapshot vô thời hạn chỉ để "phòng khi cần"; snapshot cũng có chi phí lưu trữ.

### Bước 3: Dừng và xóa workload

- Dừng ứng dụng, service, task, job và worker.
- Hủy job còn chờ hoặc đang chạy nếu được phép.
- Giảm replica về 0 hoặc xóa workload controller.
- Xác nhận không còn trigger, scheduler hoặc autoscaling tạo bản thay thế.
- Kiểm tra queue, workflow và subscription để ngăn sự kiện tiếp tục kích hoạt.

Với Kubernetes, xóa Deployment không đồng nghĩa mọi PersistentVolume hoặc tài nguyên cloud được tạo bởi controller sẽ bị xóa. Kiểm tra PVC, PV, reclaim policy, Service type LoadBalancer và tài nguyên do CSI/CNI tạo ra.

### Bước 4: Thu hồi compute và network

Sau khi workload dừng, thu hồi VM, node pool, cluster hoặc compute environment theo đúng dependency. Tiếp theo kiểm tra:

- Load balancer và target group/backend pool.
- Public/static IP không còn gắn với tài nguyên.
- NAT gateway, VPN gateway và private endpoint.
- Network interface, route, peering hoặc attachment riêng của lab.
- DNS record và zone được tạo riêng cho lab.

Không phải mọi thành phần mạng đều có phí theo giờ; tuy nhiên chúng có thể tạo phí cố định, phí xử lý dữ liệu hoặc phí truy vấn. Dùng bảng giá và báo cáo billing của dịch vụ cụ thể để xác nhận.

### Bước 5: Xử lý storage, backup và registry

Kiểm tra disk đã detach, snapshot, image, backup, object version, multipart upload chưa hoàn tất và artifact/image cũ. Xác định rõ dữ liệu nào phải xóa, dữ liệu nào phải giữ theo retention.

Các điểm dễ bỏ sót:

- Disk bị detach vẫn có thể tính phí dung lượng.
- Snapshot tăng dần vẫn lưu các block cần thiết và có thể tiếp tục tính phí.
- Object version hoặc delete marker có thể khiến dữ liệu cũ vẫn tồn tại.
- Lifecycle policy có thể chưa tới ngày xóa.
- Container registry vẫn lưu image dù cluster đã bị xóa.
- Backup tự động của database có retention riêng.

### Bước 6: Thu hồi identity và cấu hình phụ trợ

Sau khi workload không còn cần quyền, rà soát service account, role, access key, certificate, secret, policy và tài khoản test. Thu hồi credential không còn dùng và xóa secret theo chính sách.

Giữ lại audit log, manifest và bằng chứng cleanup theo thời hạn cần thiết. Không xóa role hoặc secret dùng chung chỉ vì tên có chứa từ lab.

### Bước 7: Kiểm tra tài nguyên còn sót

Chạy lại inventory ở tất cả region/zone liên quan. So sánh với manifest và phân loại mỗi mục:

- Deleted: đã xóa và API xác nhận.
- Retained: được giữ lại có owner và ngày hết hạn.
- Pending: yêu cầu xóa đang xử lý hoặc chờ thiết bị offline.
- Failed: xóa lỗi, có nguyên nhân và người xử lý.
- Shared: tài nguyên dùng chung được giữ lại và có owner rõ ràng.

Không đánh dấu lab hoàn tất khi còn resource ở trạng thái không rõ.

## 5. Những khoản phí dễ phát sinh sau khi lab kết thúc

### 5.1. Compute và cam kết sử dụng

Dừng instance có thể dừng phần phí compute theo cách tính của dịch vụ, nhưng không nhất thiết dừng phí disk, IP hoặc license. Một số tài nguyên như dedicated host hoặc reservation có thể được tính theo thời hạn ngay cả khi không có workload chạy trên đó.

Savings plan, reserved instance hoặc committed use discount là cam kết tài chính hoặc mức sử dụng đã mua. Xóa VM không tự hủy cam kết. Cần xem điều khoản, ngày kết thúc và khả năng chuyển assignment theo chính sách của nhà cung cấp.

### 5.2. Storage, snapshot và backup

Storage thường tiếp tục tính theo dung lượng và thời gian lưu. Kiểm tra cả primary disk, snapshot, backup, object version và dữ liệu lưu trong registry.

Với database, có thể tồn tại backup tự động sau khi instance bị xóa. Một số dịch vụ giữ backup cuối cùng theo lựa chọn khi xóa. Cần đọc lựa chọn retention/delete final backup trước khi xác nhận thao tác.

### 5.3. Network và data transfer

NAT gateway, load balancer, VPN gateway, public IP hoặc private endpoint có thể có phí cố định hoặc phí xử lý. Egress và cross-region transfer có thể xuất hiện trên hóa đơn sau khi lưu lượng đã kết thúc.

Xóa route hoặc firewall rule không tự xóa gateway. Xóa service không nhất thiết xóa IP tĩnh được cấp riêng. Kiểm tra attachment và resource ID cụ thể.

### 5.4. Observability và dữ liệu lưu trữ

Log, metric, trace và archive có thể tiếp tục tính phí theo dung lượng và retention. Dashboard hoặc alert rule có thể miễn phí ở một số gói, nhưng dữ liệu mà chúng tham chiếu vẫn có thể bị tính phí.

Kiểm tra log group, log bucket, workspace, archive, audit trail và export sang storage. Giữ lại dữ liệu bắt buộc, đặt retention phù hợp và xóa phần lab đã hết hạn.

### 5.5. Dịch vụ managed, serverless và event

Một số dịch vụ tính phí theo request hoặc thời gian chạy, số lượng workflow, message, query hoặc dung lượng. Nếu trigger vẫn hoạt động, workload có thể tiếp tục được gọi sau khi lab tưởng như đã kết thúc.

Kiểm tra event source mapping, subscription, scheduled job, webhook, queue redrive và workflow đang chờ. Đảm bảo không còn producer gửi sự kiện hoặc consumer chạy nền ngoài ý muốn.

### 5.6. License, marketplace và support

Phần mềm marketplace có thể tính theo giờ, theo instance, theo người dùng hoặc theo hợp đồng. Xóa VM không phải lúc nào cũng kết thúc subscription hoặc license. Gói hỗ trợ cloud thường áp dụng ở cấp account/organization và có thể tiếp tục tính phí khi không còn lab.

Rà soát billing account, marketplace subscriptions, support plan và cam kết hợp đồng. Chỉ người có thẩm quyền billing mới có thể xác nhận hoặc thay đổi những nghĩa vụ này.

## 6. Ví dụ thực hành: thu hồi lab trên Kubernetes

Giả sử lab tạo một namespace có Deployment API, Service kiểu LoadBalancer, PVC, Secret và một số tài nguyên cloud do controller tạo.

Đầu tiên, xác định đúng namespace và workload:

~~~bash
kubectl get all -n compute-lab
kubectl get pvc,pv -n compute-lab
kubectl get svc -n compute-lab
kubectl get events -n compute-lab --sort-by=.metadata.creationTimestamp
~~~

Lưu log hoặc kết quả thực hành cần thiết. Sau đó ngừng controller tạo workload mới, xóa CronJob/Job không còn cần và giảm Deployment về 0 hoặc xóa workload theo hướng dẫn lab.

~~~bash
kubectl get cronjobs,jobs -n compute-lab
kubectl get deployments,statefulsets -n compute-lab
kubectl scale deployment --all --replicas=0 -n compute-lab
~~~

Sau khi xác nhận ứng dụng đã dừng, kiểm tra Service và volume:

~~~bash
kubectl get svc,pvc -n compute-lab
kubectl get pv
kubectl describe pv PV_NAME
~~~

Service type LoadBalancer có thể tạo load balancer và IP ở cloud. Xóa Service sau khi đã xác nhận đúng lab và ghi lại resource ID liên quan:

~~~bash
kubectl delete service LAB_SERVICE -n compute-lab
~~~

PVC/PV cần được xử lý theo reclaim policy. Với policy Retain, xóa PVC có thể để PV và disk cloud tồn tại. Với policy Delete, controller có thể xóa storage bên dưới khi điều kiện phù hợp; vẫn cần kiểm tra inventory cloud sau đó.

Khi đã lưu hoặc xóa dữ liệu theo yêu cầu, xóa namespace lab:

~~~bash
kubectl delete namespace compute-lab
~~~

Cuối cùng, kiểm tra cluster, node pool, disk, snapshot, load balancer, public IP, NAT và log trên cloud provider. Nếu cluster được dùng chung, không xóa cluster chỉ vì namespace lab đã kết thúc.

## 7. Ví dụ lệnh kiểm tra tài nguyên theo cloud

Các lệnh dưới đây minh họa cách inventory và kiểm tra; cần thay tên project, account, subscription, region và tag theo môi trường thực tế. Chạy lệnh đọc trước, xem kết quả, rồi mới dùng lệnh xóa đúng resource ID đã xác minh.

### 7.1. AWS

Liệt kê EC2 instance theo tag lab:

~~~bash
aws ec2 describe-instances \
  --filters "Name=tag:Environment,Values=lab" \
  --query "Reservations[].Instances[].[InstanceId,State.Name,Placement.AvailabilityZone]"
~~~

Kiểm tra EBS volume đang available, thường là volume đã detach:

~~~bash
aws ec2 describe-volumes \
  --filters Name=status,Values=available \
  --query "Volumes[].[VolumeId,Size,AvailabilityZone,Tags]"
~~~

Kiểm tra Elastic IP và NAT gateway:

~~~bash
aws ec2 describe-addresses
aws ec2 describe-nat-gateways --filter Name=state,Values=available,pending,deleting
~~~

Sau khi xác minh ID và quan hệ phụ thuộc, có thể terminate instance hoặc xóa volume cụ thể. Ví dụ cú pháp minh họa:

~~~bash
aws ec2 terminate-instances --instance-ids i-0123456789abcdef0
aws ec2 delete-volume --volume-id vol-0123456789abcdef0
~~~

Terminate instance có thể giữ lại EBS volume tùy thuộc cấu hình delete-on-termination. Kiểm tra volume sau khi instance đã kết thúc. Với NAT gateway, cần xóa gateway và xử lý Elastic IP theo trạng thái và quy trình của dịch vụ.

Cost Explorer có thể dùng để xem chi phí theo dịch vụ và thời gian nếu đã được bật và có quyền:

~~~bash
aws ce get-cost-and-usage \
  --time-period Start=2026-11-01,End=2026-12-01 \
  --granularity DAILY \
  --metrics UnblendedCost \
  --group-by Type=DIMENSION,Key=SERVICE
~~~

Ngày kết thúc của khoảng thời gian là exclusive. Dữ liệu billing có độ trễ, vì vậy kết quả ngay sau cleanup chưa chắc phản ánh toàn bộ usage mới nhất.

### 7.2. Azure

Liệt kê tài nguyên trong resource group lab và lọc theo tag:

~~~bash
az resource list \
  --resource-group rg-compute-lab \
  --query "[].{name:name,type:type,location:location,id:id}" \
  --output table
~~~

Xem VM trong resource group:

~~~bash
az vm list \
  --resource-group rg-compute-lab \
  --show-details \
  --output table
~~~

Nếu resource group được tạo riêng cho một lab và đã xác minh không chứa tài nguyên dùng chung, có thể xóa cả nhóm bằng thao tác có chủ đích:

~~~bash
az group delete --name rg-compute-lab --yes
~~~

Xóa resource group là thao tác diện rộng. Trước khi chạy, kiểm tra danh sách resource trong nhóm, backup, disk, public IP và dữ liệu cần giữ. Với resource group dùng chung, xóa từng resource đã xác minh thay vì xóa toàn nhóm.

VM deallocate chỉ giải phóng compute theo cách tính của VM; disk, IP, backup hoặc resource khác có thể còn. Kiểm tra Cost Management theo subscription/resource group/service và chọn khoảng thời gian phù hợp để xác minh chi phí.

### 7.3. Google Cloud

Liệt kê VM theo label:

~~~bash
gcloud compute instances list \
  --filter="labels.environment=lab" \
  --format="table(name,zone,status,labels)"
~~~

Liệt kê disk:

~~~bash
gcloud compute disks list \
  --format="table(name,zone,status,sizeGb)"
~~~

Xem các tài nguyên trong project bằng Cloud Asset Inventory nếu API và quyền đã được bật:

~~~bash
gcloud asset search-all-resources \
  --scope=projects/PROJECT_ID \
  --query="labels.environment=lab"
~~~

Sau khi xác minh zone và ID, có thể xóa VM cụ thể:

~~~bash
gcloud compute instances delete LAB_VM \
  --zone=ZONE
~~~

Kiểm tra disk sau khi VM bị xóa vì disk có thể được giữ lại theo cấu hình auto-delete. Xem Cloud Billing Reports hoặc billing export để đối chiếu chi phí theo project, service, SKU và ngày. Billing export sang BigQuery hữu ích khi cần phân tích chi tiết theo label hoặc resource.

Các lệnh trên là ví dụ theo dịch vụ phổ biến. Mỗi cloud có thêm tài nguyên managed và khác biệt về retention; không nên coi một lệnh list VM là inventory hoàn chỉnh.

## 8. Kiểm tra billing sau khi thu hồi

Kiểm tra billing theo hai góc nhìn: tài nguyên còn tồn tại và usage đã được ghi nhận. Hai góc nhìn này bổ sung cho nhau.

### 8.1. Đối chiếu inventory và billing

Lập bảng kiểm tra sau cleanup:

| Nhóm | Inventory sau cleanup | Billing/usage cần kiểm tra |
|---|---|---|
| VM/compute | Không còn instance lab đang chạy | Instance hours, vCPU/GPU hours, dedicated host |
| Disk/snapshot | Không còn disk/snapshot ngoài danh sách giữ lại | GB-month, snapshot storage, backup storage |
| Network | Không còn NAT/LB/IP/VPN lab ngoài dự kiến | Gateway hours, IP hours, data processing, egress |
| Database | Không còn instance/replica lab | DB instance hours, storage, backup, I/O |
| Kubernetes | Không còn cluster/node pool lab nếu lab riêng | Cluster fee, node compute, volume và load balancer |
| Object/registry | Đã xóa dữ liệu hết hạn, giữ đúng dữ liệu cần thiết | Storage bytes, request, replication, registry storage |
| Observability | Retention đã đặt hoặc dữ liệu lab đã xóa | Log ingestion, archive, metric/trace storage |
| Event/serverless | Trigger, scheduler và workflow đã dừng | Invocation, message, workflow transition |
| Commitment/license | Đã kiểm tra hợp đồng và subscription | Phí cam kết, license, support plan |

Nếu inventory sạch nhưng billing còn tăng, kiểm tra độ trễ billing, tài nguyên tính phí theo usage đã phát sinh, cam kết sử dụng, license và dịch vụ cấp account. Nếu billing giảm nhưng inventory còn resource, resource đó có thể miễn phí hoặc chưa được sử dụng; vẫn cần quyết định giữ hay xóa theo chính sách.

### 8.2. Chọn khoảng thời gian so sánh

So sánh chi phí theo ngày hoặc giờ trước và sau cleanup, dùng cùng timezone và cùng loại metric. Nên:

1. Ghi mốc thời gian bắt đầu cleanup.
2. Chụp số liệu usage/cost trước khi xóa.
3. Ghi lại thời điểm resource thực sự chuyển sang trạng thái deleted.
4. Đợi báo cáo billing cập nhật theo chu kỳ của nhà cung cấp.
5. So sánh theo service, SKU, region, project/resource group và tag/label.
6. Điều tra dòng chi phí không giảm hoặc tiếp tục tăng.

Không kết luận ngay rằng cleanup thất bại chỉ vì hóa đơn chưa giảm trong vài phút. Billing thường được tổng hợp theo chu kỳ và có thể ghi nhận muộn. Ngược lại, cũng không kết luận đã hết phí chỉ vì dashboard một ngày chưa có dữ liệu.

### 8.3. Phân biệt chi phí tồn đọng và chi phí tiếp tục phát sinh

- **Chi phí tồn đọng:** usage đã xảy ra trước khi xóa nhưng được ghi nhận hoặc lập hóa đơn sau đó.
- **Chi phí tiếp tục phát sinh:** tài nguyên còn tồn tại, trigger còn hoạt động, dữ liệu còn được lưu hoặc cam kết vẫn tính phí.
- **Điều chỉnh billing:** credit, refund, tax, discount hoặc điều chỉnh hóa đơn làm số tiền thay đổi mà không phản ánh resource mới.
- **Chi phí chia sẻ:** tài nguyên cấp account/organization hoặc network dùng chung không thể quy toàn bộ cho một lab.

Dùng usage date và service/SKU để phân biệt khoản phát sinh trước hay sau thời điểm cleanup. Với tài nguyên dùng chung, cần dựa trên cost allocation/tag hoặc quy tắc phân bổ của tổ chức.

## 9. Thiết lập guardrail để lab tự kết thúc

Có thể giảm tài nguyên bị bỏ quên bằng cách thiết kế vòng đời ngay từ lúc tạo lab:

- Bắt buộc tag/label owner, lab ID, environment, cost center và expiry.
- Tạo lab trong project, subscription hoặc resource group riêng khi phù hợp.
- Dùng budget hoặc alert theo lab/project và ngưỡng chi phí.
- Thiết lập TTL cho môi trường tạm thời qua automation đã được kiểm thử.
- Dùng IaC để biết resource nào thuộc stack và có thể destroy có kiểm soát.
- Lưu manifest resource ID và output của deployment.
- Đặt retention mặc định cho log, snapshot và object tạm.
- Giới hạn quota và quyền tạo tài nguyên đắt tiền như GPU, NAT, public IP và database lớn.
- Dùng policy phát hiện resource không có owner hoặc quá hạn.
- Có quy trình ngoại lệ khi lab cần giữ tài nguyên lâu hơn expiry.

TTL không nên xóa dữ liệu hoặc tài nguyên dùng chung mà chưa có xác nhận owner. Automation cleanup cần có dry-run, allowlist/denylist, audit log, giới hạn phạm vi và khả năng dừng khi gặp resource không xác định.

## 10. Bài thực hành: cleanup một môi trường compute lab

Giả sử bạn tạo lab gồm một VM chạy API, một disk dữ liệu, một static public IP, một load balancer, một database nhỏ, một bucket lưu kết quả và log workspace.

Thực hiện theo các bước sau:

### 10.1. Ghi nhận trạng thái trước cleanup

- Ghi account/project/subscription và region.
- Ghi LabId, owner, thời gian bắt đầu và resource ID.
- Xuất danh sách VM, disk, IP, load balancer, database, bucket và log workspace.
- Ghi dung lượng storage, số snapshot, số object version và trạng thái backup.
- Ghi usage/cost baseline theo service/SKU trong khoảng thời gian xác định.
- Đánh dấu dữ liệu cần giữ và ngày hết hạn.

### 10.2. Ngừng workload

- Dừng traffic vào API.
- Tắt scheduler và trigger có thể tạo request.
- Dừng ứng dụng và worker.
- Kiểm tra database không còn kết nối ghi từ workload.
- Ghi log cuối và kết quả cần giữ.

### 10.3. Thu hồi tài nguyên theo dependency

- Xóa service hoặc workload gắn với load balancer.
- Xóa load balancer và target/backend attachment của lab.
- Thu hồi VM sau khi xác nhận dữ liệu trên disk đã được xử lý.
- Kiểm tra disk còn detached và xóa nếu không cần giữ.
- Giải phóng static IP nếu không còn gắn tài nguyên.
- Xóa database sau khi backup hoặc export được xác minh.
- Xóa object hết hạn, version cũ và log theo retention.
- Xóa NAT/VPN hoặc network component được tạo riêng cho lab.
- Thu hồi role, key và secret chỉ dùng cho lab.

### 10.4. Kiểm tra sau cleanup

Chạy inventory lại và xác nhận mỗi resource trong manifest là Deleted, Retained hoặc Pending có lý do. Kiểm tra không còn VM, disk, IP, LB, database, snapshot, trigger hay log retention ngoài dự kiến.

Đợi billing cập nhật rồi so sánh cost theo service/SKU. Nếu còn phí, xác định đó là usage tồn đọng, storage còn lại, network resource, license, commitment hay chi phí chia sẻ. Ghi người xử lý và ngày kiểm tra tiếp theo cho mọi khoản chưa giải quyết.

## 11. Mẫu biên bản cleanup

Mẫu sau giúp lưu bằng chứng và bàn giao:

~~~yaml
cleanup:
  labId: compute-lab-2026-11-22
  owner: learner-team-a
  completedAt: "2026-11-22T17:30:00Z"
  scope:
    account: training-account
    project: compute-training
    region: region-1
  resources:
    deleted:
      - vm-compute-demo
      - lb-compute-demo
      - ip-compute-demo
    retained:
      - id: lab-results-bucket
        reason: "Giữ kết quả tới ngày hết hạn"
        expiresAt: "2026-12-01"
    pending:
      - id: snapshot-demo-01
        reason: "Đang xác minh yêu cầu lưu giữ"
  billing:
    baselineCaptured: true
    lastReviewedAt: "2026-11-22"
    status: pending_provider_data
    remainingItems:
      - "Storage của snapshot đang chờ quyết định"
      - "Usage compute trước cleanup có thể được ghi nhận muộn"
  evidence:
    inventoryExport: cleanup-inventory.csv
    billingExport: lab-cost-review.csv
    operator: learner-team-a
~~~

Không đưa credential, access key hoặc thông tin thanh toán nhạy cảm vào biên bản. Lưu file bằng chứng ở vị trí có quyền truy cập phù hợp và retention rõ ràng.

## 12. Xử lý các tình huống thường gặp

| Tình huống | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| VM đã xóa nhưng phí storage còn | Disk hoặc snapshot được giữ lại | Liệt kê disk detached, snapshot, image và backup |
| Cluster đã xóa nhưng load balancer còn | Controller tạo resource cloud độc lập | Tìm theo tag, cluster ID, service annotation hoặc manifest |
| Instance đã stop nhưng compute cost chưa bằng 0 | Loại instance hoặc cam kết vẫn tính phí | Kiểm tra pricing model, host, reservation và commitment |
| Không tìm thấy resource trong region hiện tại | Resource nằm ở region khác hoặc global scope | Quét toàn bộ region và tài nguyên global có liên quan |
| Billing còn tăng sau cleanup | Billing delay, egress, storage hoặc trigger còn hoạt động | Đối chiếu usage date, SKU, resource ID và event source |
| Resource không có tag | Tạo thủ công hoặc tag propagation không đầy đủ | Đối chiếu ID, owner, audit log và thời điểm tạo |
| Xóa namespace nhưng disk còn | PV reclaim policy là Retain | Kiểm tra PV, volume attachment và disk cloud |
| Bucket đã xóa object nhưng storage chưa giảm | Versioning, delete marker hoặc retention lock | Kiểm tra object version, lifecycle và retention policy |
| Không xóa được public IP | IP còn gắn với NIC, LB hoặc NAT | Gỡ dependency theo thứ tự rồi release IP |
| Chi phí cam kết còn sau khi xóa hết lab | Reservation, savings plan hoặc contract | Rà soát billing agreement và ngày hết hạn |

Nếu khoản phí không xác định được resource ID, nhóm vận hành billing hoặc cloud administrator có thể cần truy vấn usage export chi tiết và đối chiếu account-level commitment. Ghi lại SKU, usage date, region và billing scope để việc điều tra có thể tiếp tục.

## 13. Checklist kết thúc lab

- [ ] Đã xác nhận đúng account/project/subscription, region, owner và LabId.
- [ ] Đã dừng pipeline, scheduler, trigger, autoscaling và producer tạo workload mới.
- [ ] Đã lưu hoặc xóa dữ liệu theo yêu cầu; backup cần thiết đã được kiểm tra.
- [ ] Đã dừng service, job, task, worker và workload.
- [ ] Đã thu hồi VM, node, cluster hoặc compute environment của lab.
- [ ] Đã kiểm tra disk, volume, snapshot, image, backup và object version.
- [ ] Đã thu hồi load balancer, NAT, public IP, VPN và network resource không còn dùng.
- [ ] Đã kiểm tra database, cache, queue, registry và event subscription.
- [ ] Đã rà soát log, metric, trace, archive và retention.
- [ ] Đã thu hồi secret, key, role và credential chỉ dùng cho lab.
- [ ] Đã kiểm tra reservation, commitment, marketplace license và support plan.
- [ ] Đã chạy inventory lại ở mọi region và phân loại Deleted/Retained/Pending.
- [ ] Đã so sánh billing theo usage date, service, SKU và tag/label sau độ trễ cập nhật.
- [ ] Mọi khoản phí còn lại có nguyên nhân, owner và thời điểm kiểm tra tiếp theo.
- [ ] Đã lưu biên bản cleanup và bằng chứng inventory/billing theo chính sách.

Một lab chỉ được xem là đã thu hồi về mặt vận hành khi workload đã dừng, tài nguyên ngoài phạm vi giữ lại đã được xử lý và inventory sau cleanup có thể giải thích đầy đủ. Việc kiểm tra billing cần thêm thời gian để dữ liệu usage cập nhật và phải xem cả phí storage, network, backup, license cùng cam kết sử dụng. Ghi nhận rõ khoản phí tồn đọng và khoản phí còn tiếp tục giúp tránh nhầm lẫn giữa hóa đơn đến muộn với tài nguyên vẫn đang tiêu tiền.
