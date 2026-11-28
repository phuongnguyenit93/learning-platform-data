# Đối soát hạn mức và chi phí khi có nhiều instance hoặc nhiều khách hàng

Trong module **SPRING_CLOUD_SERVICE_BROKER**, một service broker có thể phục vụ nhiều tenant, mỗi tenant có nhiều service instance và mỗi instance có thể chạy trên một hoặc nhiều hạ tầng phía sau. Khi số lượng instance tăng, broker phải trả lời được ba câu hỏi: khách hàng còn được phép tạo bao nhiêu tài nguyên, tài nguyên thực tế đang tiêu thụ bao nhiêu và chi phí nào thuộc về từng khách hàng.

Ba câu hỏi này liên quan nhưng không đồng nhất. Hạn mức (quota) là chính sách giới hạn; usage là mức sử dụng được đo; cost là giá trị tiền tệ được tính từ usage, giá và quy tắc phân bổ. Một instance có thể được cấp phát nhưng chưa có traffic, vẫn chiếm tài nguyên và phát sinh chi phí nền. Ngược lại, một tài nguyên dùng chung có thể phục vụ nhiều tenant nên không thể gán toàn bộ hóa đơn provider cho một instance duy nhất.

Open Service Broker API (OSB API) chuẩn hóa vòng đời service instance và binding, nhưng không định nghĩa một hệ thống quota hoặc billing thống nhất cho mọi provider. Broker cần tích hợp với cloud provider, Kubernetes, hệ thống metering và billing của sản phẩm để xây dựng mô hình attribution và reconciliation. Bài học này trình bày cách tổ chức dữ liệu, kiểm soát quota đồng thời, phân bổ chi phí dùng chung và đối soát số liệu giữa broker với hạ tầng.

## 1. Phân biệt quota, capacity, usage và cost

Bước đầu tiên là dùng đúng khái niệm. Nếu hệ thống dùng chung một trường "đã sử dụng" cho cả quota, tài nguyên provider và billing, số liệu sẽ khó giải thích và dễ dẫn đến quyết định sai.

| Khái niệm | Câu hỏi trả lời | Ví dụ |
|---|---|---|
| **Quota** | Tenant được phép sử dụng tối đa bao nhiêu? | Tối đa 10 PostgreSQL instance hoặc 2 TB storage |
| **Provider capacity** | Hạ tầng hiện có thể cấp thêm bao nhiêu? | Cluster còn 40 CPU core allocatable |
| **Allocated resource** | Broker đã đặt trước hoặc cấp phát bao nhiêu? | Instance được cấu hình 4 vCPU và 100 GB storage |
| **Measured usage** | Tài nguyên thực tế đã tiêu thụ bao nhiêu trong một khoảng thời gian? | CPU trung bình 1,2 core, storage thực tế 75 GB |
| **Billable usage** | Phần usage nào được tính tiền theo hợp đồng? | 100 GB storage-month, 500 GB data transfer |
| **Cost** | Giá trị tiền tệ được tính ra là bao nhiêu? | 35 USD cho kỳ tháng |
| **Price** | Đơn giá hoặc bảng giá nào được áp dụng? | 0,12 USD/GB-month |

Quota thường được kiểm tra trước khi provision hoặc update. Capacity phản ánh giới hạn vật lý hoặc giới hạn tài khoản ở provider. Usage được thu thập từ metrics hoặc billing export. Cost được tính bằng cách áp dụng price, discount, commitment, currency và quy tắc phân bổ.

Không nên dùng quota như số liệu billing. Ví dụ, tenant có quota 500 GB storage nhưng chỉ cấp phát 200 GB; hóa đơn có thể tính theo 200 GB allocated hoặc theo dung lượng thực tế, tùy sản phẩm. Quy tắc này phải được công bố trong chính sách thương mại, không suy ra từ quota.

## 2. Xác định phạm vi attribution trong mô hình nhiều tenant

Broker cần xác định chính xác tài nguyên thuộc khách hàng nào. Một mô hình phổ biến có cấu trúc:

~~~text
Platform
└── Organization / Account
    └── Tenant
        ├── Service Instance A
        │   ├── Provider Resource A1
        │   └── Binding A1, A2
        └── Service Instance B
            └── Provider Resource B1
~~~

Tùy platform, tenant có thể tương ứng với organization, space, project, subscription, account hoặc namespace. Broker nên có một tenant identifier nội bộ ổn định và một adapter ánh xạ context platform sang tenant đó.

Ví dụ:

| Nguồn platform | Context có thể nhận | Khóa attribution nội bộ |
|---|---|---|
| Cloud Foundry | organization GUID, space GUID | tenant_id, organization_id, space_id |
| Kubernetes integration | cluster, namespace, tenant annotation | tenant_id, cluster_id, namespace |
| Cloud account | account, project hoặc subscription ID | tenant_id, provider_account_id |

Không lấy tenant ID từ parameters do người dùng tự gửi rồi tin cậy trực tiếp. Broker phải xác thực platform client, xác định caller và kiểm tra context theo tích hợp. Nếu caller có thể sửa tenant ID tùy ý, quota có thể bị vượt hoặc chi phí bị gán sang khách hàng khác.

Cũng cần phân biệt owner của service instance với consumer của binding. Một instance có thể thuộc tenant A nhưng được bind cho nhiều workload. Nếu sản phẩm tính phí theo instance owner, toàn bộ chi phí instance thuộc tenant A. Nếu tính phí theo consumer hoặc namespace, cần có quy tắc phân bổ riêng cho từng binding hoặc workload.

## 3. Thiết kế khóa liên kết từ broker đến provider

Provider thường không biết service instance ID của OSB. Broker cần lưu mapping giữa định danh OSB và tài nguyên thật tại hạ tầng.

Một mapping có thể gồm:

| Trường | Ý nghĩa |
|---|---|
| **instance_id** | ID service instance do platform cung cấp |
| **tenant_id** | Tenant nội bộ sở hữu instance |
| **service_id** | Service offering trong catalog |
| **plan_id** | Plan được chọn |
| **provider_name** | Nhà cung cấp hoặc loại hạ tầng |
| **provider_account_id** | Account/project/subscription chứa tài nguyên |
| **provider_resource_id** | ID tài nguyên thực tế tại provider |
| **external_resource_key** | Tên/label ổn định dùng để tra cứu và reconciliation |
| **cluster_id / namespace** | Phạm vi Kubernetes nếu có |
| **lifecycle_state** | Trạng thái provision/update/deprovision |
| **created_at / deleted_at** | Mốc vòng đời để đối soát |

Nên áp dụng một external resource key ổn định, chẳng hạn tên có chứa instance ID đã được mã hóa hoặc rút gọn theo quy tắc đặt tên provider. Có thể thêm tags hoặc labels vào tài nguyên:

~~~json
{
  "managed_by": "spring-cloud-service-broker",
  "broker_instance_id": "instance-7f3a",
  "tenant_ref": "tenant-42",
  "service_id": "service-postgresql",
  "plan_id": "plan-standard",
  "environment": "production"
}
~~~

Các tag/label trên là ví dụ. Không đưa email, tên người dùng, secret hoặc dữ liệu cá nhân vào metadata provider nếu không cần thiết. Tenant reference nên là định danh nội bộ không nhạy cảm và được kiểm soát quyền đọc.

Tags giúp tìm và đối chiếu resource, nhưng không thay thế database mapping hoặc authorization. Một người có quyền sửa tag ở provider không được phép tự đổi tenant owner trong broker chỉ bằng cách sửa label.

## 4. Thiết kế quota theo nhiều chiều

Quota hiếm khi chỉ là một con số. Một tenant có thể bị giới hạn theo số instance, dung lượng, CPU, RAM, số binding hoặc chi phí theo kỳ.

Ví dụ quota:

| Dimension | Quota tenant | Đơn vị |
|---|---:|---|
| PostgreSQL instances | 10 | instance |
| Redis instances | 20 | instance |
| Storage | 2.000 | GB |
| Allocated vCPU | 64 | vCPU |
| Allocated memory | 256 | GB |
| Active bindings | 100 | binding |
| Monthly spending limit | 1.500 | USD/tháng |

Quota có thể được áp dụng ở nhiều scope:

- **Tenant scope:** tổng tài nguyên của khách hàng.
- **Service scope:** giới hạn riêng cho PostgreSQL, Redis hoặc RabbitMQ.
- **Plan scope:** giới hạn số lượng instance của plan enterprise.
- **Region/cluster scope:** giới hạn capacity ở một vùng hoặc cluster.
- **Account scope:** giới hạn do cloud provider áp dụng.
- **Binding scope:** giới hạn số consumer được bind vào một instance.

Một tenant có thể còn quota storage nhưng cluster đã hết capacity. Ngược lại, cluster còn capacity nhưng tenant đã đạt spending limit. Vì vậy provision phải kiểm tra cả policy tenant lẫn capacity của provider.

### 4.1. Hard quota, soft quota và spending limit

| Chính sách | Hành vi | Trường hợp dùng |
|---|---|---|
| Hard quota | Từ chối khi vượt giới hạn | Số instance, storage tối đa, CPU allocation |
| Soft quota | Cảnh báo hoặc yêu cầu approval khi gần/vượt ngưỡng | Dung lượng tăng trưởng, số binding |
| Spending limit | Ngăn hoặc yêu cầu duyệt khi dự báo/chi phí đạt mức | Ngân sách tháng của tenant |
| Burst allowance | Cho phép vượt ngưỡng trong thời gian hoặc phạm vi giới hạn | Workload có tải đột biến |

Không nên tự động deprovision tài nguyên đang chạy chỉ vì usage vượt quota nếu hợp đồng sản phẩm không cho phép. Thông thường, quota ngăn tạo mới hoặc tăng tài nguyên; việc xử lý instance hiện hữu cần chính sách riêng, cảnh báo và quy trình thay đổi được kiểm soát.

## 5. Kiểm tra quota an toàn khi có request đồng thời

Một lỗi phổ biến là kiểm tra quota bằng hai thao tác riêng:

~~~text
Request A: đọc usage = 8, quota = 10
Request B: đọc usage = 8, quota = 10
Request A: provision 2 instance
Request B: provision 2 instance
Kết quả: usage = 12, vượt quota
~~~

Đây là race condition. Broker cần reservation và cập nhật nguyên tử trong database.

Một mô hình đơn giản:

- **committed_usage:** tài nguyên đã được provision và đang tính vào quota.
- **reserved_usage:** quota đã giữ chỗ cho operation đang thực hiện.
- **quota_limit:** giới hạn hiện hành.

Điều kiện chấp nhận:

\[
committed\_usage + reserved\_usage + requested\_amount
\leq quota\_limit
\]

Ví dụ, tenant có quota 10 instance, đã có 8 instance active và 1 reservation đang provision. Request tạo thêm 1 instance có thể được chấp nhận; request tạo thêm 2 instance phải bị từ chối.

Một câu lệnh cập nhật có điều kiện có thể bảo vệ quota:

~~~sql
UPDATE tenant_quota
SET reserved_instances = reserved_instances + :requested
WHERE tenant_id = :tenant_id
  AND committed_instances + reserved_instances + :requested
      <= instance_limit;
~~~

Ứng dụng kiểm tra số hàng được cập nhật. Nếu không có hàng nào được cập nhật, quota không đủ hoặc bản ghi đã thay đổi đồng thời. Với nhiều dimension, cần reserve tất cả dimension trong cùng transaction hoặc có cơ chế rollback reservation khi một dimension thất bại.

### 5.1. Reservation lifecycle

~~~mermaid
stateDiagram-v2
    [*] --> RESERVED
    RESERVED --> COMMITTED
    RESERVED --> RELEASED
    COMMITTED --> RELEASE_PENDING
    RELEASE_PENDING --> RELEASED
    COMMITTED --> ADJUSTED
    RELEASED --> [*]
~~~

- Khi provision được chấp nhận, broker tạo reservation.
- Khi provider cấp phát thành công và instance được xác nhận, chuyển reservation thành committed usage.
- Khi provision thất bại hoàn toàn, giải phóng reservation.
- Khi update tăng tài nguyên, reserve phần chênh lệch trước khi gọi provider.
- Khi update giảm tài nguyên, chỉ giảm committed usage sau khi provider xác nhận thay đổi.
- Khi deprovision thành công, giải phóng committed usage theo quy tắc đo lường và billing.

Không giải phóng quota chỉ vì worker timeout. Timeout không chứng minh provider chưa tạo tài nguyên. Trước khi release reservation, cần kiểm tra operation và provider state để tránh cấp quota cho một tài nguyên đã tồn tại nhưng broker chưa kịp ghi nhận.

## 6. Quota cho provision, update, binding và deprovision

Mỗi thao tác vòng đời có cách tác động quota khác nhau.

| OSB operation | Tác động quota thường gặp |
|---|---|
| Provision | Reserve instance count, storage, CPU/RAM hoặc dự toán chi phí |
| Update tăng plan/resource | Reserve phần tăng thêm trước khi provider thay đổi |
| Update giảm resource | Chỉ giảm committed usage sau khi provider xác nhận |
| Bind | Tăng binding count hoặc connection entitlement nếu sản phẩm giới hạn |
| Unbind | Giảm binding count sau khi quyền truy cập đã được thu hồi |
| Deprovision | Giải phóng quota sau khi resource được xác nhận đã xóa/giải phóng |

Không phải mọi binding đều tiêu thụ một đơn vị tài nguyên provider. Tuy vậy, sản phẩm có thể đặt quota số binding để giới hạn số consumer, credential hoặc connection policy. Hãy tách quota nghiệp vụ khỏi quota vật lý.

Với async operation, reservation phải gắn với operation ID và có thời hạn/lease. Một reconciler cần phát hiện reservation bị kẹt khi worker chết, nhưng chỉ release sau khi xác minh provider state và operation state.

## 7. Đo usage: allocated khác actual consumption

Một instance có thể được tính quota theo tài nguyên được cấp phát, trong khi billing có thể dựa trên tài nguyên thực tế hoặc một mô hình kết hợp.

Ví dụ Kubernetes:

- Pod có request CPU 2 core và memory 4 GiB.
- Metrics ghi nhận CPU trung bình 0,7 core và memory working set 2,1 GiB.
- Quota cluster có thể tính theo requests.
- Billing sản phẩm có thể tính theo allocation, actual usage hoặc plan cố định.

Không dùng một con số duy nhất cho cả quota và cost. Lưu riêng allocated, measured và billable usage để có thể giải thích vì sao số liệu khác nhau.

Các loại usage phổ biến:

| Resource | Allocation metric | Actual/billable metric có thể dùng |
|---|---|---|
| CPU | vCPU hoặc CPU request | CPU core-second/core-hour |
| Memory | Memory request/limit | GB-hour hoặc GB-second |
| Storage | Dung lượng provision | GB-month hoặc dung lượng trung bình |
| Database | Instance tier, storage, IOPS | Instance-hour, storage-month, I/O |
| Network | Băng thông cam kết | GB egress hoặc request count |
| Object storage | Capacity tier | GB-month, operation count, retrieval |
| Binding | Số binding active | Credential/license hoặc connection entitlement |

Định nghĩa rõ đơn vị, thời gian lấy mẫu và cách tổng hợp. Ví dụ CPU core-hour phải xác định lấy CPU request, CPU usage hay CPU allocation. Nếu thay đổi định nghĩa mà không version hóa, khách hàng sẽ không thể so sánh hóa đơn giữa các kỳ.

## 8. Thu thập usage từ Kubernetes

Khi broker cấp phát tài nguyên trên Kubernetes, usage và quota có thể được lấy từ nhiều nguồn:

- Kubernetes API: object, requests, limits, PVC size, namespace và trạng thái workload.
- ResourceQuota: tổng mức request/limit hoặc object count trong namespace.
- Metrics API hoặc metrics pipeline: CPU, memory và network usage theo thời gian.
- Storage metrics: dung lượng volume đã cấp và dung lượng đã dùng, tùy storage driver.
- Cloud provider billing: chi phí node, disk, load balancer, network và dịch vụ managed.

Ví dụ một ResourceQuota:

~~~yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: tenant-payments
  namespace: payments
spec:
  hard:
    requests.cpu: "16"
    requests.memory: 64Gi
    limits.cpu: "32"
    limits.memory: 128Gi
    persistentvolumeclaims: "20"
    requests.storage: 1Ti
~~~

ResourceQuota là cơ chế giới hạn của Kubernetes trong namespace. Nó không tự cung cấp hóa đơn chính xác cho từng service instance. Broker vẫn cần mapping từ OSB instance ID sang namespace, workload, PVC và cloud resource liên quan.

Nên gắn labels nhất quán vào các object do broker tạo, ví dụ tenant ID, instance ID, service ID và plan ID. Một controller hoặc collector có thể tổng hợp metrics theo labels. Nếu nhiều instance cùng chạy trong một namespace, cần phân biệt resource theo instance label thay vì gán toàn bộ namespace usage cho một instance.

### 8.1. CPU và memory

CPU usage có thể biến động theo thời gian. Memory có thể được đo bằng working set, RSS hoặc mức request/limit. Các metric này có ý nghĩa khác nhau. Nếu billing theo allocation, dùng request/plan entitlement; nếu billing theo actual usage, định nghĩa cách lấy mẫu, percentile hoặc average.

Đối với CPU, tổng core-hour trong kỳ có thể tính:

\[
CPU\ core\ hours = \sum_i CPU_i \times \Delta t_i
\]

Trong đó CPU_i là số core được tính phí trong khoảng thời gian \(\Delta t_i\) tính theo giờ. Đối với memory, có thể tích phân GB theo thời gian tương tự. Cần thống nhất xử lý pod restart, missing samples và khoảng thời gian workload chưa sẵn sàng.

### 8.2. Storage

PVC request thường biểu diễn dung lượng provision, còn metrics storage có thể biểu diễn dung lượng đã dùng. Provider có thể tính phí theo volume size đã cấp phát, ngay cả khi filesystem chưa sử dụng hết.

Broker cần biết sản phẩm tính quota và billing theo:
- Dung lượng PVC provision.
- Dung lượng thực tế đã sử dụng.
- Dung lượng trung bình trong kỳ.
- Tier hoặc loại disk.
- Snapshot và backup storage riêng.

Không thay thế số liệu provider invoice bằng metrics filesystem nếu nhà cung cấp tính tiền theo volume allocation.

## 9. Thu thập usage và cost từ cloud provider

Cloud provider thường cung cấp billing export, cost and usage report hoặc API usage theo account/project/subscription. Dữ liệu có thể đến trễ, được điều chỉnh hoặc phân loại theo SKU, region, resource ID và tag.

Broker nên lưu provider resource ID và tags để nối dòng chi phí về instance. Một pipeline điển hình:

1. Nhận billing export theo lịch hoặc stream.
2. Chuẩn hóa provider account, resource ID, SKU, region, currency và usage unit.
3. Ánh xạ resource về service instance bằng provider mapping hoặc tags.
4. Áp dụng quy tắc direct/shared/unallocated.
5. Tính cost theo price version, discount và currency policy.
6. Ghi cost allocation ledger.
7. Đối soát tổng allocation với tổng chi phí provider.
8. Đưa sai lệch vào hàng đợi điều tra.

Không giả định billing export đến ngay khi tài nguyên được tạo hoặc xóa. Có thể có độ trễ, dòng chi phí điều chỉnh và credit được ghi ở kỳ sau. Do đó, usage metrics phục vụ vận hành gần thời gian thực, còn provider billing thường là nguồn tài chính có độ trễ và cần reconciliation.

## 10. Phân bổ chi phí trực tiếp và chi phí dùng chung

Một số chi phí có thể gắn trực tiếp với resource ID, ví dụ một managed database hoặc disk riêng. Một số chi phí dùng chung khó gắn trực tiếp, ví dụ Kubernetes control plane, node pool, NAT gateway, load balancer, logging pipeline hoặc monitoring platform.

### 10.1. Direct cost

Nếu provider invoice có resource ID tương ứng một service instance, broker có thể gán trực tiếp chi phí đó cho tenant sở hữu instance. Cần kiểm tra resource mapping và khoảng thời gian resource tồn tại.

### 10.2. Shared cost

Với chi phí dùng chung, cần có allocation policy được công bố và nhất quán. Một số phương pháp:

| Phương pháp | Cách phân bổ | Khi phù hợp |
|---|---|---|
| Theo usage đo được | Tỷ lệ CPU, memory, storage hoặc network usage | Có metrics đủ tin cậy |
| Theo allocation | Tỷ lệ request CPU, memory hoặc capacity đã đặt | Sản phẩm tính phí theo entitlement |
| Theo số instance | Chia đều theo số instance active | Các instance có quy mô tương đương |
| Theo trọng số plan | Mỗi plan có weight hoặc share cố định | Không có metrics chi tiết hoặc cần đơn giản |
| Theo tenant baseline | Mỗi tenant chịu một phần nền, phần còn lại theo usage | Có chi phí cố định và biến đổi |
| Unallocated/shared overhead | Giữ ở cost center nền tảng | Chưa có cơ sở phân bổ công bằng |

Ví dụ, chi phí node pool shared trong tháng là 1.000 USD. Nếu policy phân bổ theo CPU core-hour và tenant A chiếm 40% tổng usage, tenant A được phân bổ 400 USD. Nếu có 100 USD control-plane fee cố định được giữ ở platform overhead, chỉ 900 USD được chia theo usage. Quy tắc phải được ghi lại để khách hàng hiểu vì sao phần chi phí của họ thay đổi.

### 10.3. Không phân bổ trùng

Một dòng invoice provider chỉ được phân bổ một lần hoặc được chia thành các phần có tổng bằng dòng gốc. Nếu resource có tag instance ID nhưng đồng thời được đưa vào pool shared, không được tính cả direct cost lẫn shared allocation.

Mỗi allocation record nên tham chiếu đến source cost line và allocation policy version. Có thể dùng tổng kiểm tra:

\[
\sum tenant\_allocated\_cost + platform\_unallocated
= provider\_source\_cost
\]

Nếu có currency conversion hoặc rounding, cần định nghĩa tolerance và cách xử lý phần dư do làm tròn.

## 11. Tính cost theo thời gian và giá

Cost thường được tính từ usage nhân với unit price, nhưng giá có thể thay đổi theo thời điểm, region, plan, tier, discount hoặc hợp đồng.

Một công thức đơn giản:

\[
Cost = BillableUsage \times UnitPrice
\]

Ví dụ, storage được tính theo GB-month. Nếu một instance dùng 100 GB trong nửa tháng và 200 GB trong nửa tháng, usage theo GB-month có thể được tính theo thời gian:

\[
100 \times 0.5 + 200 \times 0.5 = 150\ GB\text{-}month
\]

Với đơn giá 0,10 USD/GB-month, chi phí storage là 15 USD trước thuế và discount.

Để tính chính xác, cần lưu:

- Thời điểm bắt đầu/kết thúc resource.
- Múi giờ và ranh giới kỳ billing.
- Đơn vị usage và cách quy đổi.
- Price version có hiệu lực tại thời điểm usage.
- Currency, discount, credit và tax treatment.
- Quy tắc rounding và precision.

Dùng kiểu decimal có độ chính xác phù hợp cho tiền tệ, không dùng floating point nhị phân để cộng trừ hóa đơn. Lưu đơn giá và cost theo decimal scale đã định nghĩa. Không làm tròn từng sample quá sớm; nên tổng hợp ở độ chính xác cần thiết rồi làm tròn theo chính sách billing.

### 11.1. Giá trong catalog không phải ledger tài chính

OSB catalog có thể công bố metadata chi phí để platform hiển thị giá tham khảo. Tuy nhiên metadata catalog không thay thế price book hoặc billing ledger. Hệ thống tính tiền phải dùng nguồn giá có version, thời gian hiệu lực và quy tắc thương mại rõ ràng.

Nếu catalog hiển thị giá theo tháng nhưng billing tính theo giờ, phải giải thích rõ quy đổi. Nếu plan có mức phí cố định cộng usage, phải tách recurring charge và metered charge để tránh cộng trùng.

## 12. Data model cho quota, usage và cost allocation

Một thiết kế có thể tách các bảng:

| Entity | Nội dung chính | Mục đích |
|---|---|---|
| tenant | tenant ID, trạng thái, billing account | Chủ sở hữu |
| tenant_quota | dimension, limit, committed, reserved | Kiểm soát hạn mức |
| service_instance | instance ID, tenant, service, plan, provider mapping | Registry tài nguyên |
| quota_reservation | operation ID, dimension, amount, state | Giữ chỗ quota |
| usage_sample | resource, metric, value, unit, interval | Dữ liệu metering |
| provider_cost_line | invoice/export line, resource ID, amount, currency | Chi phí nguồn |
| price_version | SKU, unit price, currency, effective interval | Nguồn giá |
| cost_allocation | cost line, tenant/instance, allocated amount, policy version | Phân bổ |
| reconciliation_run | kỳ, nguồn, thời gian chạy, kết quả | Theo dõi đối soát |
| reconciliation_issue | loại sai lệch, amount, owner, trạng thái | Điều tra sai lệch |

Ví dụ usage record:

~~~json
{
  "event_id": "usage-2026-11-27-00017",
  "tenant_id": "tenant-42",
  "instance_id": "instance-7f3a",
  "provider_resource_id": "db-resource-991",
  "metric": "storage_allocated",
  "value": 100,
  "unit": "GB",
  "period_start": "2026-11-27T00:00:00Z",
  "period_end": "2026-11-28T00:00:00Z",
  "source": "provider-meter"
}
~~~

Usage record cần có event ID hoặc khóa idempotency để collector gửi lại không làm tăng tổng usage hai lần. Cần phân biệt sample thay thế (correction) với sample bổ sung. Nếu provider sửa dữ liệu cũ, lưu adjustment có liên kết tới record gốc thay vì âm thầm ghi đè mà mất audit trail.

## 13. Pipeline metering và cost allocation

Một kiến trúc tham khảo:

~~~mermaid
flowchart TD
    A["OSB lifecycle events"] --> B["Instance / Tenant Registry"]
    C["Kubernetes metrics"] --> D["Usage Collector"]
    E["Cloud billing export"] --> F["Cost Importer"]
    B --> D
    B --> F
    D --> G["Normalized Usage Ledger"]
    F --> H["Provider Cost Ledger"]
    G --> I["Pricing and Allocation Engine"]
    H --> I
    I --> J["Tenant Cost Ledger"]
    J --> K["Reconciliation"]
    K --> L["Billing / Chargeback"]
    K --> M["Discrepancy Queue"]
~~~

Các thành phần có trách nhiệm riêng:

- **Instance registry:** mapping tenant, service instance và provider resource.
- **Usage collector:** lấy metrics hoặc usage report, chuẩn hóa unit và time window.
- **Cost importer:** nạp provider billing lines và adjustment.
- **Pricing engine:** áp dụng price book, discount và currency.
- **Allocation engine:** gán direct cost hoặc phân bổ shared cost.
- **Reconciliation:** so sánh source totals, usage-derived cost và tenant allocation.
- **Billing/chargeback:** xuất dữ liệu đã đối soát cho hệ thống thương mại.

Nên lưu ledger theo kiểu append-only hoặc có audit history. Điều chỉnh dữ liệu cũ bằng adjustment record có version, source và lý do để có thể giải thích hóa đơn sau này.

## 14. Đối soát quota và usage

Quota reconciliation kiểm tra số liệu broker đang giữ có khớp với resource inventory thực tế hay không.

Ví dụ:

| Nguồn | Instance count |
|---|---:|
| Broker registry | 25 |
| Provider inventory sau khi lọc tag | 24 |
| Chênh lệch | 1 |

Có thể xảy ra các tình huống:

- Broker ghi instance PROVISIONING nhưng provider chưa tạo resource.
- Provider tạo resource thành công nhưng broker chưa ghi mapping.
- Instance đã deprovision ở provider nhưng broker còn ACTIVE.
- Resource bị xóa thủ công ngoài broker.
- Tag/label bị mất khiến collector không nhận diện được tenant.
- Một operation bị retry tạo tài nguyên ngoài dự kiến.

Reconciliation nên so sánh theo external resource key, provider resource ID, tenant tag và thời gian. Không tự động xóa resource "không biết chủ" nếu chưa xác minh; có thể đó là tài nguyên của một hệ thống khác hoặc tag bị thiếu.

Quy trình xử lý sai lệch:

1. Phát hiện chênh lệch và tạo issue có ID.
2. Thu thập nguồn dữ liệu, thời điểm và resource mapping.
3. Phân loại là missing in broker, orphan at provider, stale state, duplicate hoặc tag mismatch.
4. Xác minh operation gần nhất và trạng thái provider.
5. Chọn hành động repair an toàn: cập nhật mapping, retry lifecycle, đánh dấu manual review hoặc cleanup đã được duyệt.
6. Ghi audit và chạy reconciliation lại để xác nhận.

## 15. Đối soát chi phí với provider invoice

Đối soát cost cần so sánh tổng chi phí provider với tổng phần đã phân bổ và phần overhead/unallocated.

Ví dụ:

| Hạng mục | Số tiền |
|---|---:|
| Provider invoice cho cluster | 10.000 USD |
| Direct cost gán cho instance | 6.200 USD |
| Shared cost phân bổ cho tenants | 3.000 USD |
| Platform overhead chưa phân bổ | 500 USD |
| Chênh lệch cần điều tra | 300 USD |

Chênh lệch có thể đến từ:

- Billing export đến trễ hoặc có adjustment.
- Resource chưa được mapping.
- Currency conversion hoặc rounding.
- Credit, discount, tax hoặc committed-use discount.
- Resource bị xóa giữa kỳ nhưng invoice tính trọn giờ/ngày.
- Shared cost chưa có allocation policy.
- Dòng phí network hoặc support không có resource ID cụ thể.

Không ép tổng allocation bằng invoice bằng cách phân bổ phần chênh lệch tùy tiện. Hãy ghi discrepancy, xác định nguyên nhân và dùng một cost center tạm thời nếu policy cho phép. Khi có dữ liệu điều chỉnh, tạo adjustment có audit.

## 16. Spring Cloud: tổ chức quota và cost services

Trong Spring Cloud Service Broker, không nên nhúng logic quota, provider billing và phân bổ cost vào handler HTTP. Tách các use case để có thể kiểm thử độc lập:

| Thành phần | Trách nhiệm |
|---|---|
| TenantContextResolver | Xác định tenant từ authenticated platform context |
| QuotaService | Kiểm tra và reserve quota |
| ReservationRepository | Lưu reservation có transaction/unique key |
| LifecycleCoordinator | Điều phối provision/update/deprovision |
| ProviderAdapter | Tạo, đọc, cập nhật và xóa tài nguyên |
| ResourceInventoryService | Đồng bộ mapping provider resource |
| UsageCollector | Thu thập và chuẩn hóa usage |
| CostImporter | Nạp billing export/provider cost |
| PricingService | Tính billable amount theo price version |
| CostAllocationService | Phân bổ direct/shared cost |
| ReconciliationService | Đối soát quota, inventory, usage và invoice |

Một flow provision có thể thực hiện:

~~~java
@Transactional
public ProvisionReservation reserveProvision(ProvisionCommand command) {
    TenantId tenantId = tenantContextResolver.requireTenant(command.context());

    quotaService.reserve(
        tenantId,
        command.planId(),
        command.requestedResources(),
        command.operationId()
    );

    return reservationRepository.create(
        tenantId,
        command.instanceId(),
        command.operationId(),
        command.requestedResources()
    );
}
~~~

Đây là pseudocode về trách nhiệm, không phải chữ ký API cố định của Spring Cloud Open Service Broker. Transaction phải bao phủ cập nhật quota và reservation trong cùng database. Provider call nên diễn ra ngoài transaction dài; khi provider thành công, application service chuyển reservation thành committed usage trong transaction mới.

Nếu transaction quota và reservation nằm ở hai database khác nhau, cần workflow có compensation/outbox thay vì giả định có distributed transaction tự động.

### 16.1. Commit và release reservation

Pseudocode:

~~~java
@Transactional
public void commitReservation(String operationId, ProviderResource resource) {
    ProvisionReservation reservation =
        reservationRepository.requireByOperationId(operationId);

    if (reservation.isCommitted()) {
        return;
    }

    resourceInventoryRepository.saveMapping(
        reservation.instanceId(),
        resource.providerId(),
        resource.externalKey()
    );

    quotaService.commit(reservation);
    reservationRepository.markCommitted(operationId);
}
~~~

Các hàm commit cần idempotent và được bảo vệ bởi unique constraint/state transition. Nếu worker retry sau khi commit thành công, lần chạy tiếp theo không được tăng committed usage thêm lần nữa.

### 16.2. Thu thập usage bất đồng bộ

Usage collector thường chạy theo lịch hoặc nhận event. Có thể lưu watermark cho từng nguồn để biết đã import đến thời điểm nào. Mỗi sample có event ID hoặc source key để chống nạp trùng.

Không để request provision phải chờ provider billing export. Provision chỉ cần kiểm tra quota/capacity và reservation. Billing reconciliation chạy theo chu kỳ riêng và có thể cập nhật adjustment sau đó.

## 17. Bảo mật và tính toàn vẹn dữ liệu attribution

Quota và cost ảnh hưởng trực tiếp đến quyền sử dụng và hóa đơn. Sai tenant attribution có thể khiến khách hàng bị tính tiền của người khác hoặc vượt giới hạn.

Các nguyên tắc:

- Xác định tenant từ authenticated platform context và registry.
- Không tin tags/labels do workload có thể tự sửa nếu không được kiểm soát.
- Bảo vệ API đọc usage, cost và quota theo tenant scope.
- Không cho tenant sửa provider resource ID hoặc owner mapping.
- Ghi audit cho thay đổi quota, price, allocation policy và manual adjustment.
- Version hóa price book và allocation policy.
- Đồng bộ thời gian, timezone và period boundary.
- Kiểm soát quyền truy cập billing export và provider account credentials.
- Mã hóa dữ liệu tài chính và giới hạn retention theo yêu cầu sản phẩm.
- Không log secret hoặc dữ liệu cá nhân trong metering event.

Một tenant chỉ được xem cost ledger và usage của chính tenant đó, trừ các vai trò vận hành được phân quyền riêng. Dashboard quản trị có thể xem tổng hợp nhưng cần audit và phân quyền theo chức năng.

## 18. Kiểm thử quota, usage và cost reconciliation

Kiểm thử cần bao phủ đồng thời, retry, provider drift và billing adjustments.

| Nhóm kiểm thử | Trường hợp | Kết quả mong đợi |
|---|---|---|
| Quota boundary | Request đúng bằng quota | Được chấp nhận nếu policy cho phép |
| Quota exceeded | Request vượt quota một đơn vị | Bị từ chối |
| Concurrent reservation | Hai request cùng reserve phần quota còn lại | Không vượt giới hạn |
| Provision failure | Provider thất bại sau reservation | Reservation được release sau khi xác minh |
| Timeout ambiguity | Provider tạo resource nhưng broker timeout | Reconciliation tìm resource, không cấp trùng |
| Update increase | Tăng storage/CPU | Reserve delta trước side effect |
| Update decrease | Giảm resource | Giảm committed sau provider success |
| Deprovision | Resource đã absent | Quota release idempotent |
| Duplicate usage event | Collector gửi lại cùng event | Ledger không cộng hai lần |
| Late billing adjustment | Provider sửa dòng chi phí kỳ trước | Tạo adjustment có liên kết |
| Shared allocation | Phân bổ shared cost theo usage | Tổng allocation khớp source cost trong tolerance |
| Unallocated resource | Provider resource không có mapping | Tạo discrepancy, không gán tenant tùy tiện |
| Tenant isolation | Tenant A truy vấn cost của B | Bị từ chối |
| Price version | Usage qua thời điểm đổi giá | Áp đúng price có hiệu lực từng thời đoạn |

Nên có test với database và provider adapter giả lập failure window: provider success nhưng broker chưa commit, worker chạy lặp, queue giao event trùng và billing export đến trễ. Test cần kiểm tra ledger cuối cùng, không chỉ response HTTP.

## 19. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Dùng quota làm số liệu billing | Hóa đơn không phản ánh quy tắc thương mại | Tách quota, usage và cost |
| Dùng namespace làm tenant mà không kiểm tra ownership | Gán nhầm tài nguyên giữa khách hàng | Context resolver và tenant registry |
| Chỉ kiểm tra quota bằng SELECT | Race condition vượt quota | Reservation và atomic update |
| Release reservation khi timeout | Provider có thể đã tạo tài nguyên | Reconcile provider trước khi release |
| Dùng metrics Kubernetes thay provider invoice | Bỏ sót disk, network, control plane hoặc discount | Đối soát với billing export |
| Phân bổ shared cost theo tỷ lệ không có policy | Hóa đơn khó giải thích | Version hóa allocation policy |
| Gán toàn bộ cost shared cho một instance | Sai chargeback | Phân bổ hoặc giữ overhead riêng |
| Không deduplicate usage event | Usage/cost bị cộng trùng | Event ID và unique constraint |
| Ghi đè dữ liệu billing cũ | Mất audit trail | Adjustment record có nguồn |
| Dùng floating point cho tiền | Sai số làm tròn | Decimal và rounding policy |
| Không lưu price version | Không giải thích được hóa đơn cũ | Effective-dated price book |
| Tự động xóa resource orphan | Có thể xóa nhầm tài nguyên | Discrepancy workflow và xác minh ownership |

## 20. Checklist triển khai cho môi trường nhiều tenant

Trước khi phát hành broker cho nhiều khách hàng, hãy xác nhận:

- [ ] Tenant ID được xác định từ platform context đã xác thực.
- [ ] Mỗi OSB instance được map tới provider resource ID và external key ổn định.
- [ ] Provider resource có tags/labels cần thiết cho inventory và cost attribution.
- [ ] Tags/labels không được xem là nguồn xác thực duy nhất.
- [ ] Quota được chia theo dimension và scope rõ ràng.
- [ ] Capacity provider được kiểm tra riêng với quota tenant.
- [ ] Provision và update dùng reservation nguyên tử, chống race condition.
- [ ] Reservation gắn với operation ID và có recovery khi worker chết.
- [ ] Commit/release quota idempotent.
- [ ] Allocated, measured và billable usage được lưu riêng.
- [ ] Usage event có deduplication key và unit/time window rõ ràng.
- [ ] Provider billing export được nhập và chuẩn hóa theo source ID.
- [ ] Direct cost và shared cost có allocation policy version.
- [ ] Tổng cost allocation được đối chiếu với provider source cost.
- [ ] Discrepancy được lưu, phân loại và xử lý có audit.
- [ ] Price book có currency, effective time, discount và rounding policy.
- [ ] Cost/usage/quota API có tenant isolation.
- [ ] Có test concurrent quota, provider timeout, duplicate event và late billing adjustment.

Đối soát hạn mức và chi phí trong môi trường nhiều instance đòi hỏi broker giữ được mối liên hệ từ tenant đến OSB instance, provider resource, usage sample và dòng chi phí. Quota cần được reserve nguyên tử trước khi cấp phát; usage cần có nguồn, đơn vị và khoảng thời gian; cost cần có price version và allocation policy; reconciliation cần phát hiện sai lệch mà không tự sửa mù quáng. Khi các lớp này được tách rõ và tích hợp qua Spring services, repository, worker và provider adapters, service broker có thể mở rộng nhiều tenant mà vẫn kiểm soát được capacity, chargeback và tính minh bạch tài chính.
