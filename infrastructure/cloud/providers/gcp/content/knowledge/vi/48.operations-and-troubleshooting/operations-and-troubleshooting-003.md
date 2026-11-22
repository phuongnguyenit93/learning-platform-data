# Xử lý quota exceeded, resource exhausted và thiếu capacity

Một hệ thống Java chạy trên Google Cloud có thể thất bại lúc tăng tải dù cấu hình và mã nguồn không thay đổi. Có lúc lệnh tạo VM trả `QUOTA_EXCEEDED`; có lúc quota CPU vẫn còn nhưng Compute Engine báo `ZONE_RESOURCE_POOL_EXHAUSTED`. Một Pod GKE ở trạng thái `Pending`, một request Cloud Run trả 429, hoặc ứng dụng Java ném `OutOfMemoryError` đều có thể bị gọi chung là “hết tài nguyên” — nhưng **nguyên nhân và biện pháp xử lý hoàn toàn khác nhau**.

Bài học này xây dựng phương pháp phân loại, điều tra và xử lý ba nhóm vấn đề: **quota exceeded** (vượt giới hạn sử dụng được cấp), **resource exhausted** (tài nguyên cần cho thao tác đã cạn hoặc không cấp phát được) và **capacity shortage** (thiếu năng lực vật lý hoặc năng lực xử lý ở lớp dịch vụ). Mục tiêu là khôi phục dịch vụ an toàn, tránh những thay đổi hoảng loạn làm mất dữ liệu hoặc phá vỡ độ tin cậy, rồi thiết kế giám sát và capacity planning để sự cố không lặp lại.

Bài thuộc chương **Vận hành và xử lý sự cố** của module **CLOUD_PROVIDERS_GCP**. Module khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua những tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Trong bài này, chúng ta áp dụng các kiến thức đó vào công việc SRE vận hành và xử lý sự cố thực tế.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **rate quota**, **allocation quota**, **concurrent quota**, **system limit**, **physical capacity** và **application resource exhaustion**.
- Đọc tín hiệu `429`, `403 QUOTA_EXCEEDED`, gRPC `RESOURCE_EXHAUSTED`, `503`, `ZONE_RESOURCE_POOL_EXHAUSTED` và `OOMKilled` mà không suy đoán chỉ từ mã lỗi.
- Xác định đúng service, project, region/zone, quota metric, limit, usage và request gây lỗi.
- Dùng Cloud Quotas, Cloud Monitoring, Cloud Logging, `gcloud` và `kubectl` để chẩn đoán bằng thao tác đọc.
- Xử lý những tình huống thường gặp ở Compute Engine, GKE, Cloud Run, Cloud SQL, Pub/Sub, BigQuery và Cloud Storage.
- Thiết kế retry có backoff/jitter, flow control, batching và idempotency cho Java/Spring.
- Lập yêu cầu tăng quota có số liệu, phân biệt tăng quota với đặt trước capacity.
- Xây cảnh báo, dự báo headroom và runbook GO/NO-GO cho tăng tải, triển khai và DR.
- Đánh giá ảnh hưởng chi phí, bảo mật và sự công bằng tài nguyên khi giảm thiểu sự cố.

## 1. Bốn khái niệm phải tách biệt

### 1.1 Quota: giới hạn quản trị được cấp

**Quota** định nghĩa lượng tài nguyên hoặc số thao tác mà một consumer được phép sử dụng trong phạm vi xác định. Google Cloud có nhiều loại:

| Loại quota | Ví dụ | Đặc điểm |
|---|---|---|
| **Allocation quota** | Tổng vCPU hoặc accelerator được phép cấp phát trong một region | Tài nguyên đang dùng chiếm quota cho tới khi được giải phóng theo quy tắc dịch vụ |
| **Rate quota** | Số API requests trên một phút, trong ngày hoặc một cửa sổ khác | Khả năng sử dụng hồi phục theo cửa sổ thời gian của service |
| **Concurrent quota** | Số operation hoặc request đồng thời | Chỉ giảm áp lực khi request/operation hoàn thành |
| **Per-user quota** | Request mỗi phút cho một caller/user được xác định | Có thể hết riêng một caller dù tổng project còn thấp |
| **System limit** | Giới hạn cố định của một tính năng/đối tượng | Thường không thể yêu cầu tăng như quota điều chỉnh được |

Quota được gắn với **phạm vi**: project, region, zone, service, machine family, consumer hoặc identity, tùy từng metric. Một request quota ở region A không tăng quota ở region B; quota của API X không tự chuyển cho API Y.

**Điều quan trọng:** quota lớn hơn không bảo đảm có phần cứng sẵn có và cũng không bảo đảm application có đủ CPU, RAM hay kết nối database để xử lý.

### 1.2 Physical capacity: khả năng cấp phát thực tế

Một zone có thể không còn đủ CPU, memory, GPU hoặc Local SSD cho một VM hoặc accelerator slice ở thời điểm tạo. Khi đó Compute Engine có thể trả lỗi như `ZONE_RESOURCE_POOL_EXHAUSTED`, `REGION_RESOURCE_POOL_EXHAUSTED` hoặc `POOL_CAPACITY_INSUFFICIENT` tùy request và API.

**Tăng quota sẽ không làm zone có thêm physical hardware ngay lập tức.** Phương án cần xem là zone khác, region khác, machine type tương đương, phân nhỏ workload hoặc reservation/provisioning model phù hợp.

### 1.3 Resource exhaustion bên trong workload

Dù quota và zone capacity còn đủ, tiến trình vẫn có thể cạn:

- Java heap hoặc native memory, dẫn tới `OutOfMemoryError` hoặc container `OOMKilled`.
- Thread pool / connection pool của HTTP/JDBC.
- Disk đầy, inode hết hoặc storage throughput/IOPS bị bão hòa.
- CPU bị throttling, request queue đầy, event loop tắc.
- Database chạm `max_connections`, lock contention hoặc storage limit.
- Pod không được lập lịch vì yêu cầu lớn hơn `allocatable` trên một node.

Đây là vấn đề capacity **ở workload và runtime**, không tự động được chữa bằng một nút “Increase quota” ở Cloud Console.

### 1.4 Service capacity và cấu hình tự giới hạn

Một service managed như Cloud Run có thể từ chối request khi không có instance sẵn sàng vì `max instances`, regional CPU/memory quota, thời gian startup lâu, service scaling chậm hoặc backend quá tải. GKE Cluster Autoscaler có thể bị chặn bởi node pool max size, Pod scheduling constraints, IP exhaustion hay Compute Engine capacity.

Vì vậy, điều tra cần trả lời **“giới hạn ở lớp nào?”** trước khi chọn hành động.

## 2. Ma trận nhận diện lỗi

| Tín hiệu | Ngữ cảnh thường gặp | Giả thuyết đầu tiên | Không được kết luận vội |
|---|---|---|---|
| HTTP `429 Too Many Requests` | API rate limiting, quota, Cloud Run không còn instance | Quá nhiều request hoặc không đủ serving capacity | “Chắc chắn cần tăng API quota” |
| HTTP `403 QUOTA_EXCEEDED` | Một số Compute Engine API | Vượt quota cấp phát | “IAM permission denied” |
| HTTP `403 RATE_LIMIT_EXCEEDED` | Compute Engine rate quota | Tần suất gọi API quá cao | “Phải tăng số vCPU” |
| gRPC `RESOURCE_EXHAUSTED` | Google APIs hoặc application gRPC | Quota, flow control hoặc resource limit | “Chắc chắn hết hardware ở zone” |
| `ZONE_RESOURCE_POOL_EXHAUSTED` | Tạo/start VM | Zone không đủ physical capacity | “Quota đang bằng 100%” |
| `REGION_RESOURCE_POOL_EXHAUSTED` | Yêu cầu Compute Engine trong region | Không đáp ứng được capacity ở các zone xét | “IAM/role bị thiếu” |
| `IP_SPACE_EXHAUSTED` | GKE/node provisioning | Dải IP không đủ | “CPU quota thấp” |
| Pod `Pending` / `FailedScheduling` | GKE | Không fit tài nguyên hoặc constraints | “Cluster Autoscaler bị hỏng” |
| `OOMKilled`, exit 137 | Container | Vượt memory limit hoặc OOM | “Regional memory quota đã hết” |
| HTTP `503` | Cloud Run, load balancer, upstream | Không phục vụ được request hoặc backend lỗi | “Chỉ cần retry vô hạn” |
| Database `too many connections` | Cloud SQL/PostgreSQL/MySQL | Cạn DB connections | “Cần tăng SQL instance quota” |
| BigQuery `resourcesExceeded` | Query execution | Memory/shuffle/CPU resource limits | “Cần tăng API requests quota” |

**Mã lỗi không phải toàn bộ chẩn đoán.** Đọc error message, service/API method, `reason`, `domain`, `quota_metric`, `quota_limit`, project, location, request ID và thời điểm. Một số sản phẩm có trường chi tiết khác nhau.

### Ví dụ log minh họa, không phải response chuẩn của mọi API

~~~json
{
  "severity": "ERROR",
  "service": "orders-worker",
  "operation": "create-compute-instance",
  "project_id": "demo-project",
  "location": "asia-southeast1-b",
  "api_error": "QUOTA_EXCEEDED",
  "resource_type": "compute.googleapis.com",
  "request_id": "example-request-id",
  "retryable": false,
  "message": "Requested operation exceeds a quota in the specified scope"
}
~~~

Giữ mã lỗi nguyên gốc từ provider. Các field `service`, `operation`, `retryable` ở ví dụ là **schema log ứng dụng tự thiết kế**, không bảo đảm do mọi Google API trả về.

## 3. Trong 10 phút đầu incident: giảm tác động trước khi tăng quota

Một sự cố capacity có thể mở rộng rất nhanh vì các client retry đồng loạt. Mục tiêu đầu tiên là **khống chế ảnh hưởng**, không phải lập tức yêu cầu quota tăng.

### Luồng xử lý

~~~mermaid
flowchart TD
  A[Alert / error / Pod Pending] --> B[Phân loại customer impact và phạm vi]
  B --> C{Lỗi ở lớp nào?}
  C -->|Quota rate hoặc concurrent| D[Rate limit, backoff, queue, giảm fan-out]
  C -->|Quota allocation| E[Kiểm tra usage, giải phóng unused resources an toàn]
  C -->|Zone capacity| F[Đổi zone/machine type hoặc dùng reservation]
  C -->|Workload exhausted| G[Tune memory/pool/requests, giảm traffic]
  C -->|Chưa rõ| H[Giữ nguyên thay đổi, thu logs/metrics]
  D --> I[Kiểm chứng SLO và backlog]
  E --> I
  F --> I
  G --> I
  H --> I
  I --> J{Đã ổn định?}
  J -->|Không| K[Escalate support / incident commander]
  J -->|Có| L[RCA, quota/capacity plan, alerts]
~~~

### Checklist triage ban đầu

1. **Xác định impact:** request bị lỗi, giao dịch thất bại, queue backlog, mất khả năng deploy hay chỉ có job thử nghiệm bị chặn?
2. **Xác định phạm vi:** project, billing account, service, region/zone, tenant/user, resource, API method.
3. **Ghi thời điểm và dấu vết:** log entry, request ID, operation ID, error details và deployment/change gần nhất.
4. **Đo usage/limit:** quota metric và limit đúng dimension, không chỉ nhìn tổng quota của project.
5. **Kiểm tra health:** CPU/memory, latency, queue age, DB connections, GKE events, node capacity.
6. **Áp dụng biện pháp an toàn:** giảm batch concurrency, tạm dừng job không quan trọng, bật backpressure hoặc điều chỉnh routing đã được phê duyệt.
7. **Escalate đúng nhóm:** Platform/Quota owner cho quota; SRE/Network cho capacity; DBA cho database; app team cho Java memory.
8. **Chỉ nâng quota hoặc thay kiến trúc** sau khi xác định giới hạn và tác động FinOps/bảo mật.

**Không dừng/xóa một VM production để “lấy lại slot” khi zone đang thiếu capacity**: Compute Engine có thể không thể tạo hoặc khởi động lại instance nếu không có reservation phù hợp.

## 4. Xem quota đúng nơi và đúng dimension

Trong Google Cloud Console:

1. Chọn đúng project/folder/organization.
2. Mở **IAM & Admin > Quotas & System Limits**.
3. Lọc theo Service, quota metric, location và tên limit.
4. Xem Value, Current usage, Current usage percentage, Unit và Scope.
5. Mở **usage chart** và so sánh với thời điểm lỗi.
6. Kiểm tra có quota adjustment pending hoặc override thấp hơn mặc định không.
7. Đối chiếu tài liệu service để biết có thể điều chỉnh hay là system limit.

**Cẩn thận:** với rate quota per-minute, cột Current usage có thể là trung bình của một cửa sổ quan sát; spike ngắn có thể gây lỗi 429 dù con số hiển thị chưa tới 100%. Với quota per-day, cách tính ngày có thể theo Pacific Time. Hãy đọc định nghĩa của metric và period.

### Bảng điều tra cần điền

| Trường | Ví dụ | Tại sao cần |
|---|---|---|
| Incident ID | INC-2026-XX | Theo dõi |
| Product/API | Compute Engine API | Chọn đúng bảng quota |
| Project | `project-prod` | Consumer quota |
| Location | `asia-southeast1` / zone | Phạm vi phân bổ |
| Quota metric | CPU family hoặc API request rate | Giới hạn đang nghi vấn |
| Limit | Giá trị đo từ Console | Không đoán default |
| Usage | Giá trị cùng scope/time window | Tính headroom |
| Error reason | `QUOTA_EXCEEDED` | Phân loại |
| Business impact | 20% deploy không thành công | Đánh giá severity |
| Owner | platform-oncall | Người xử lý |
| Evidence | Console chart, log, request ID | Audit/RCA |

### Phân biệt “quota còn” với “được cấp tài nguyên”

Giả sử quota region cho họ máy còn 40 vCPU, nhưng một yêu cầu 32 vCPU có thể thất bại do zone không đủ máy cùng cấu hình tại thời điểm đó. Đây là **capacity shortage**, không phải lý do tự động xin tăng quota từ 40 lên 80 vCPU.

Ngược lại, khi zone có capacity nhưng project đã dùng hết quota 40 vCPU, thử chuyển sang zone khác **trong cùng region** có thể vẫn bị chặn bởi cùng quota regional. Phải kiểm tra scope.

## 5. Các lệnh kiểm tra ban đầu không làm thay đổi tài nguyên

Các ví dụ sau nhằm **đọc trạng thái**. Thay `PROJECT_ID`, `REGION`, `ZONE`, `CLUSTER` và resource names trước khi chạy. Luôn xác nhận project/context để tránh điều tra nhầm môi trường.

### Project và Compute Engine quota

~~~bash
gcloud config get-value project
gcloud projects describe PROJECT_ID

gcloud compute regions describe REGION \
  --project=PROJECT_ID \
  --format="yaml(quotas)"

gcloud compute project-info describe \
  --project=PROJECT_ID \
  --format="yaml(quotas)"
~~~

Đây là cách xem **các quota Compute Engine được biểu diễn trong tài nguyên liên quan**, không phải bảng quota cho mọi Google Cloud product. Với các quota khác, dùng Cloud Quotas Console/API và tài liệu service cụ thể.

### VM, reservations và zone

~~~bash
gcloud compute instances list --project=PROJECT_ID

gcloud compute reservations list --project=PROJECT_ID

gcloud compute zones describe ZONE --project=PROJECT_ID
~~~

Lệnh `zones describe` không hứa hẹn trả số physical capacity hiện có. Nếu API báo thiếu tài nguyên, dùng reason details và hướng dẫn capacity error để lựa chọn phương án.

### Logs Explorer mẫu

~~~text
severity>=ERROR
(
  "QUOTA_EXCEEDED" OR
  "RATE_LIMIT_EXCEEDED" OR
  "RESOURCE_EXHAUSTED" OR
  "ZONE_RESOURCE_POOL_EXHAUSTED"
)
~~~

Đây là truy vấn tìm chuỗi để sàng lọc. Trong log thực, dùng resource labels, project, thời gian và structured fields của từng dịch vụ để tránh bỏ sót các lỗi có message khác.

### Nguyên tắc bằng chứng

Một ảnh chụp quota lúc 14:00 không chứng minh quota không bị chạm lúc 13:15. Mỗi quan sát phải ghi timestamp, scope, thời gian ghi log và request bị lỗi.

## 6. Theo dõi quota bằng Cloud Monitoring

Cloud Monitoring hỗ trợ nhiều metric quota. Có hai họ chính:

- **Consumer quotas:** các metric theo monitored resource `consumer_quota`, chẳng hạn `serviceruntime.googleapis.com/quota/exceeded`; dùng label `quota_metric` để phân biệt giới hạn.
- **Resource-specific quotas:** một số service xuất trực tiếp metric `usage`, `limit`, `exceeded` theo monitored resource riêng.

Ví dụ một filter trong Metrics Explorer hoặc Monitoring Query Language tương đương:

~~~text
metric.type="serviceruntime.googleapis.com/quota/exceeded"
resource.type="consumer_quota"
~~~

Chỉ nên triển khai alert sau khi xác nhận service thật sự phát metric tương ứng. Metric quota không được tất cả sản phẩm xuất cùng schema, cùng độ trễ hoặc cùng dimension.

### Dashboard quota tối thiểu

| Widget | Công dụng |
|---|---|
| Usage / limit (%) theo quota và region | Headroom |
| Quota exceeded events | Biết đã chạm giới hạn |
| Request rate, p95/p99 latency | Tác động người dùng |
| Retry rate / 429 / 503 | Phát hiện retry storm |
| Queue age và backlog | Đo áp lực dồn lại |
| CPU, memory, disk, connections | Tách quota với workload saturation |
| GKE Pending Pods / scale-up errors | Nút thắt của scheduler/autoscaler |
| Deploy/traffic change markers | Liên hệ tăng lỗi với thay đổi |

### Ngưỡng cảnh báo

Một ngưỡng 70–80% headroom usage hoặc dự báo chạm quota trong vài ngày có thể là **ngưỡng nội bộ khởi đầu**, không phải ngưỡng được Google Cloud bảo đảm. Một dịch vụ có spike theo giây cần burn-rate/short-window alert; một allocation quota ít biến động có thể dùng threshold dài hơn.

Tránh page on-call với một quota “90%” nhưng không có nguy cơ ảnh hưởng dịch vụ. Phân biệt **planning alert** với **incident alert**.

## 7. Compute Engine: phân biệt quota với hết capacity ở zone

### Case A: `QUOTA_EXCEEDED`

Biểu hiện: tạo VM hoặc tăng Managed Instance Group (MIG) không thành công; error nói rõ quota metric.

Điều tra:

1. Xác định family, region/zone, vCPU/GPU/Local SSD/external IP hoặc resource limit liên quan.
2. Kiểm tra usage/limit trong Cloud Quotas và Compute Engine.
3. Đối chiếu các VM/MIG, reservation và instance tạo gần đây.
4. Xem có resource không dùng nhưng vẫn chiếm quota hay không.
5. Quyết định giảm nhu cầu, giải phóng tài nguyên an toàn hoặc request adjustment.

Không xóa disk, snapshot hay VM khác để “giải phóng quota” nếu chưa biết quota nào bị chạm và dependency của tài nguyên đó.

### Case B: `ZONE_RESOURCE_POOL_EXHAUSTED`

Biểu hiện: quota còn nhưng zone không có đủ resource cho cấu hình.

Phương án:

- Đổi sang machine type khác đáp ứng workload.
- Chọn zone khác trong region, nếu data residency và HA design cho phép.
- Thử region khác theo chính sách dữ liệu.
- Chia workload thành instance nhỏ hơn nếu kiến trúc hỗ trợ.
- Sử dụng provisioning model tương thích như Spot/flex-start cho job chịu gián đoạn.
- Chuẩn bị **reservation** cho tài nguyên quan trọng nếu có thể.

**Không nên stop/start VM production đang chạy chỉ để thử**; khi stop, các tài nguyên phần cứng không còn được giữ chắc cho lần start tiếp theo nếu không có cơ chế reservation phù hợp.

### Capacity không đồng nghĩa mọi loại VM có sẵn

Một zone có thể đủ E2 nhưng thiếu A-series GPU, hoặc đủ vCPU nhưng thiếu cấu hình memory/local SSD. Kiểm tra toàn bộ machine type, accelerator, disk interface, topology và placement constraints.

## 8. Reservations, Spot và capacity planning

**Reservation** trong Compute Engine giúp đảm bảo khả năng dùng tài nguyên phù hợp khi đúng điều kiện được đáp ứng. Nó không phải giấy phép bỏ qua mọi quota, region/zone, billing hoặc IAM. Cấu hình reservation phải khớp các thuộc tính cần thiết của VM.

| Phương án | Khi dùng | Rủi ro/đánh đổi |
|---|---|---|
| On-demand | Workload thông thường | Có thể gặp capacity shortage |
| Reservation phù hợp | Workload phải tạo/khởi động theo kế hoạch | Phát sinh chi phí/commitment tùy loại |
| Spot | Batch/checkpointable, test, stateless jobs chịu gián đoạn | Có thể bị thu hồi |
| Flex-start, nếu hỗ trợ | Workload cho phép chờ để được cấp phát | Không có giờ bắt đầu cố định như reservation |
| Đổi machine type/zone | Có lựa chọn tương đương | Cần test memory, CPU arch, latency, compliance |
| Pre-provisioning/warm pool | Critical traffic và deployment | Chi phí idle |

### GPU/TPU

GPU/TPU có thể có **quota riêng theo accelerator family và location**, cộng với yêu cầu physical capacity và topology. TPU slice nhiều host có thể thất bại dù tổng quota chip đủ vì cấu hình liên kết hoặc capacity không phù hợp.

Không giải quyết tình huống TPU/GPU thiếu capacity bằng cách chỉ sửa một quota CPU chung. Xem các loại quota, capacity, reservation và hướng dẫn provisioning riêng của TPU/GPU.

## 9. GKE: Pod Pending có ít nhất năm nguyên nhân khác nhau

Một Pod ở trạng thái `Pending` không đồng nghĩa thiếu vCPU quota.

| Dấu hiệu / sự kiện | Lớp bị chặn | Cách xử lý phù hợp |
|---|---|---|
| `Insufficient cpu` / `Insufficient memory` | Scheduler không tìm thấy allocatable resource phù hợp | Đúng requests/limits, node size, autoscaling |
| `scale.up.error.quota.exceeded` | Compute Engine quota khi tạo node | Kiểm tra quota tương ứng |
| `scale.up.error.out.of.resources` | Zone không đủ physical capacity | Chọn zone/machine type khác |
| `scale.up.error.ip.space.exhausted` | Subnet/Pod IP không đủ | Mở rộng range theo quy trình GKE |
| `no.scale.up.mig.failing.predicate` | Node selectors/affinity/taints/tolerations | Sửa scheduling constraints đúng yêu cầu |
| Node pool đã đạt max size | Autoscaler không tăng thêm nodes | Review autoscaling limits và quota |
| Unbound PVC | Storage/PV binding | Kiểm tra CSI, storage class, zone/volume |
| Pod yêu cầu hơn một node có thể chứa | Không có node phù hợp dù scale thêm | Tách workload hoặc chọn node lớn hơn |

### Read-only triage trên GKE

~~~bash
kubectl config current-context
kubectl get pods -A --field-selector=status.phase=Pending
kubectl describe pod POD_NAME -n NAMESPACE
kubectl get events -A --sort-by=.metadata.creationTimestamp
kubectl get nodes -o wide
kubectl describe nodes
kubectl get hpa -A
~~~

Khi Cluster Autoscaler không tăng node:

- Xem lỗi trong GKE Console > Workloads / Notifications.
- Kiểm tra `scaleUp` và `noScaleUp` events trong Cloud Logging.
- Xem node pool min/max, Compute Engine quota và machine type.
- Xem GKE IP space và số address trống cho node/Pod.
- Xem node affinity, taints/tolerations, resource requests và PVC topology.

### Ví dụ tính capacity của Pod

Một node có 8 vCPU **không nhất thiết có đủ 8 vCPU allocatable** cho Pod vì kubelet, system components và reservation của node. Nếu Pod yêu cầu 8 CPU trên node 8-vCPU, nó có thể không fit. Dựa vào `kubectl describe node` (Capacity, Allocatable, Allocated resources), không chỉ tên machine type.

### Backoff khi quota lỗi

GKE Cluster Autoscaler có thể vào **backoff** sau một số lỗi scale-up như quota exhausted. Tăng quota xong không nhất thiết Pod lập tức chuyển sang Running; cần kiểm tra event/backoff, scheduling và hiệu lực của quota đã được cập nhật.

**Không giảm requests một cách tùy tiện** để ép Pod chạy nếu workload thực sự cần memory đó; đổi `requests` không làm ứng dụng bớt dùng RAM và có thể gây OOM hoặc noisy neighbor.

## 10. Cloud Run: 429 không phải lúc nào là API quota

Cloud Run có thể trả:

- **429 “no available instance”** khi request đến nhưng không có instance nhận được, do chạm max instances, startup chậm hoặc tăng tải quá nhanh.
- **503** trong các tình huống scaling, backend/container lỗi hoặc không còn serving capacity.
- Lỗi application 429 do chính Java service hoặc API gateway đặt rate limiting.
- Lỗi từ Google API downstream, dù Cloud Run request hiện tại vẫn có tài nguyên.

### Những giới hạn cần phân biệt

1. **Service-level max instances**: giới hạn tổng serving capacity theo cấu hình.
2. **Revision-level max instances**: giới hạn trên từng revision theo cấu hình tương ứng.
3. **Regional CPU/memory/GPU quotas**: tài nguyên được cấp cho các Cloud Run workloads trong region.
4. **Concurrency per instance**: số request có thể xử lý cùng lúc trên một instance.
5. **Request timeout và startup time**: thời gian chiếm instance/thread.
6. **Downstream capacity**: Cloud SQL connections, Pub/Sub throughput, external APIs.

Với Cloud Run, max instances có thể bị vượt tạm thời trong một số điều kiện scaling hoặc rollout. Vì thế, tính toán DB connection limit cần có **safety margin**, không lấy `max instances × pool size` làm một hard cap được bảo đảm tuyệt đối.

### Đọc cấu hình và logs

~~~bash
gcloud run services describe SERVICE \
  --region=REGION \
  --project=PROJECT_ID \
  --format=yaml

gcloud run revisions list \
  --service=SERVICE \
  --region=REGION \
  --project=PROJECT_ID
~~~

Trong Console/Monitoring, xem instance count, request concurrency, request latency, startup latency, CPU, memory và 429/503 theo revision. Đọc **request log message** để tách lỗi “no available instance” khỏi 429 do ứng dụng trả.

### Biện pháp

| Vấn đề | Hướng giải quyết |
|---|---|
| Max instances thấp so với peak | Review tăng service-level max, quota và cost |
| Startup lâu | Giảm startup work, image size, init I/O; min instances nếu SLO cần |
| Concurrency không phù hợp | Benchmark tối ưu request concurrency, CPU và DB pool |
| Ứng dụng hết memory | Profile heap/native memory, chỉnh memory limit và code |
| DB quá tải khi scale | Giới hạn connection pooling, queue và concurrency trước khi scale |
| Regional quota chưa đủ | Lập yêu cầu quota đúng metric và region |
| Burst lớn | Rate-limit upstream, queue và fail gracefully |

Đừng mặc định tăng max instances sẽ tốt hơn: nếu mỗi instance tạo 20 DB connections, nhân thêm instance có thể biến một sự cố Cloud Run thành sự cố database.

## 11. Cloud SQL: connection exhaustion, storage và hiệu năng

Ở database, các lỗi “resource exhausted” thường không phải quota hành chính của Cloud SQL API.

### `too many connections`

Nguyên nhân có thể:

- Quá nhiều Cloud Run/GKE replicas cùng mở pool JDBC.
- Pool bị leak hoặc không đóng connection.
- Slow queries giữ connection lâu.
- Batch hoặc admin clients mở connections liên tục.
- `max_connections` và memory của database không phù hợp workload.

Công thức ngân sách kết nối:

~~~text
Estimated DB connections
  ≈ number_of_active_app_instances × max_pool_size_per_instance
    + workers + admin + background connections
~~~

Ví dụ 120 instance × 15 connections = 1.800 connections, **chưa tính** worker/admin. Đây là phép tính giả định; số thực tế phải đo, và Cloud Run có thể tạm vượt max instances trong một số hoàn cảnh.

### PostgreSQL kiểm tra read-only

~~~sql
SHOW max_connections;

SELECT count(*) AS total_connections
FROM pg_stat_activity;

SELECT state, count(*) AS connections
FROM pg_stat_activity
GROUP BY state
ORDER BY connections DESC;
~~~

Không tùy tiện chạy `pg_terminate_backend` để “giải phóng slot”. Việc đó có thể hủy transaction, gây retry storm hoặc làm mất tiến độ một job.

### Storage/IOPS saturation

Khi database gần đầy storage hoặc I/O cao:

- Kiểm tra disk usage, growth, auto storage increase và hạn mức của instance.
- Xem slow queries, locks, replication lag và transaction logs.
- Xem backup/PITR/HA behavior theo engine và edition.
- Đánh giá nâng instance size/IOPS/connection cap theo runbook DBA.
- Xem index, vacuum/maintenance hoặc workload batching để giảm áp lực.

**Nâng Cloud SQL instance count quota không chữa việc một instance đã hết kết nối.** Chọn đúng lớp giới hạn.

## 12. Pub/Sub, BigQuery, Cloud Storage và API rate quotas

### Pub/Sub

Pub/Sub có thể trả `RESOURCE_EXHAUSTED` khi vượt quota throughput, request rate hoặc giới hạn khác tùy method/region.

Hướng xử lý:

- Kiểm tra publish/subscribe throughput và quota đúng region.
- Giảm producer concurrency bằng flow control.
- Tối ưu batching và kích thước message.
- Thiết kế subscriber parallelism phù hợp.
- Kiểm tra oldest unacked message age, retry/dead-letter, backpressure.
- Không tự tăng số publishers nếu quota throughput đã chạm.

Message processing có thể bị dồn; đánh giá RPO nghiệp vụ và thời gian xử lý backlog trước khi nâng quota.

### BigQuery

Phân biệt:

- Quota API jobs/query requests.
- Giới hạn đồng thời của jobs theo project/location.
- Query `resourcesExceeded` vì memory, shuffle hoặc execution engine.
- Slot capacity/reservations dành cho query compute.
- Storage quota và streaming ingestion limits.

Với query hết memory/shuffle, hãy:

1. Đọc query job execution details và plan.
2. Kiểm tra join lớn, `ORDER BY`, aggregation và skew.
3. Dùng partition/pruning, predicate pushdown và schema thích hợp.
4. Xem slots/concurrency và reservation capacity.
5. Chia query thành stages hoặc batch nếu hợp lý.

Không tự xem mọi lỗi `resourcesExceeded` là yêu cầu tăng BigQuery API quota.

### Cloud Storage

HTTP `429` hoặc `503` khi có burst/operation contention có thể yêu cầu:

- Retry với exponential backoff và jitter.
- Tăng request rate từ từ khi có traffic rất lớn.
- Tránh một object bị ghi/metadata cập nhật liên tục bởi nhiều worker.
- Batch hoặc điều chỉnh layout object nếu phù hợp.
- Kiểm tra bucket location, API method, operation costs và service limits.

Thao tác object phải hỗ trợ **idempotency/preconditions** nếu được retry; không overwrite dữ liệu production mù quáng.

### API khác

Secret Manager, Cloud Logging, Cloud Monitoring và IAM APIs cũng có rate/usage quotas. Một job đồng bộ hoặc autoscaler lỗi có thể nhân request đáng kể, vì vậy cần đo **số API calls thực tế mỗi nghiệp vụ**, không chỉ RPS của frontend.

## 13. Java runtime: heap exhaustion và thread/connection pools

Khi ứng dụng Java lỗi trong container, kiểm tra JVM và container trước khi tìm quota Google Cloud.

### Java memory không chỉ có heap

~~~text
Container memory
  = Java heap
    + metaspace + code cache
    + thread stacks + direct/off-heap buffers
    + native libraries + JVM overhead
    + các tiến trình sidecar hoặc khác trong container
~~~

Nếu container giới hạn 1 GiB, đặt `-Xmx1024m` có thể không còn khoảng trống cho native memory, dẫn đến OOMKill dù heap Java chưa ghi nhận `OutOfMemoryError`.

### Dấu hiệu cần quan sát

| Dấu hiệu | Giải thích khả dĩ | Kiểm tra |
|---|---|---|
| `java.lang.OutOfMemoryError: Java heap space` | Heap không chứa được object allocations | Heap usage, GC, dump theo chính sách |
| `OOMKilled` / exit 137 | Cgroup/container memory bị vượt | GKE Pod events, Cloud Run logs, memory metrics |
| `GC overhead limit exceeded` | JVM tiêu tốn thời gian cho GC nhưng giải phóng ít | GC logs, allocation profile |
| Thread count tăng liên tục | Thread leak hoặc blocking | Thread dump, executor metrics |
| HikariCP connection timeout | Pool thiếu/DB chậm hoặc leak | Active/idle/pending, DB sessions |
| HTTP 429 từ downstream | Quota/rate limiting hoặc backend capacity | HTTP headers, request IDs, Retry-After |
| `RESOURCE_EXHAUSTED` từ gRPC | Có thể quota hoặc flow control | gRPC status details, service metrics |

### Biện pháp Java

- Profile allocation và heap live set trước khi chỉ tăng memory.
- Chỉnh `-XX:MaxRAMPercentage` hoặc `-Xmx` theo container memory budget.
- Giới hạn worker threads, queue length và concurrent blocking calls.
- Đặt timeout ở HTTP/JDBC/gRPC; không cho request giữ resource vô hạn.
- Đảm bảo connection đóng bằng `try-with-resources` hoặc framework lifecycle.
- Dùng pagination/streaming cho dữ liệu lớn.
- Cài circuit breaker, bulkhead và backpressure.
- Có load test với peak/burst và failure injection trước khi tăng replica.

## 14. Retry đúng: khác nhau giữa lỗi tạm thời và hard limit

**Retry không làm một hệ thống có thêm quota hoặc capacity.** Nó chỉ hữu ích khi lỗi tạm thời và việc chờ có cơ hội thành công.

| Lỗi | Có retry? | Điều kiện |
|---|---|---|
| API 429 rate limit | Thường có | Tôn trọng `Retry-After`, exponential backoff + jitter |
| gRPC `RESOURCE_EXHAUSTED` | Phụ thuộc service | Kiểm tra semantics và quota details |
| 503 transient | Có thể | Timeout, budget, idempotency |
| Quota allocation đã hết | Không nên retry liên tục | Cần giải phóng quota hoặc được điều chỉnh |
| Zone capacity shortage | Chỉ bounded retry; thường cần phương án khác | Đổi zone/machine/reservation |
| IAM 403 permission denied | Không | Sửa danh tính/quyền |
| Validation 400 | Không | Sửa request |
| DB max connections | Hạn chế | Backpressure, pool/DB recovery trước |

### Exponential backoff với full jitter

Một công thức minh họa:

~~~text
baseDelay = 200 milliseconds
maxDelay  = 10 seconds
attempt   = 0, 1, 2, ...
ceiling   = min(maxDelay, baseDelay × 2^attempt)
sleep     = random_uniform(0, ceiling)
~~~

Ngoài giới hạn số lần retry, cần **deadline tổng** để không giữ thread của người dùng quá lâu. Nếu provider trả `Retry-After`, ưu tiên tuân thủ hướng dẫn tương ứng.

### Ví dụ Java 17 với HTTP GET idempotent

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

public class BoundedRetryExample {
    private static final int MAX_ATTEMPTS = 4;

    public static String getWithRetry(String endpoint)
            throws Exception {
        HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .build();

        HttpRequest request = HttpRequest.newBuilder(URI.create(endpoint))
            .timeout(Duration.ofSeconds(5))
            .GET()
            .build();

        for (int attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
            HttpResponse<String> response =
                client.send(request, HttpResponse.BodyHandlers.ofString());

            int status = response.statusCode();

            if (status >= 200 && status < 300) {
                return response.body();
            }

            if (status != 429 && status != 503) {
                throw new IllegalStateException(
                    "Non-retryable HTTP status " + status);
            }

            if (attempt == MAX_ATTEMPTS - 1) {
                throw new IllegalStateException(
                    "Retry budget exhausted, status " + status);
            }

            long maxBackoffMs = Math.min(10000L, 200L << attempt);
            long jitterMs = ThreadLocalRandom.current()
                .nextLong(maxBackoffMs + 1);

            // Demo: cần đọc và tôn trọng Retry-After, cùng deadline tổng,
            // trước khi dùng ở production.
            Thread.sleep(jitterMs);
        }

        throw new IllegalStateException("Unreachable");
    }
}
~~~

Đoạn code này là **mẫu giáo dục cho GET** và chưa xử lý `Retry-After`, I/O failures, circuit breaker, cancellation hoặc tổng request deadline. Đối với production, ưu tiên retry configuration có giới hạn của Google Cloud client libraries/framework theo tài liệu. Không sao chép nguyên code cho POST có side effects mà chưa có idempotency key hoặc phương án chống ghi trùng.

### Retry storm và amplification

Nếu một API request gọi ba dependency và mỗi dependency retry ba lần, tổng request downstream có thể tăng mạnh khi hệ thống đang khó khăn. Thiết kế retry budget ở **một lớp chủ đạo**, đặt timeouts và bulkheads; không đặt nhiều retry policies lồng nhau không kiểm soát.

## 15. Flow control, queue và graceful degradation

Khi quota/rate limit xuất hiện, điều chỉnh nhu cầu có thể khôi phục nhanh hơn yêu cầu tăng quota.

### Công cụ giảm áp lực

- **Client-side rate limiter:** giới hạn calls/second và concurrency.
- **Token bucket:** cho phép burst có kiểm soát nhưng giữ average rate.
- **Semaphore/bulkhead:** giới hạn số lời gọi đồng thời tới dependency.
- **Bounded queue:** có dung lượng hữu hạn, tránh OOM và làm rõ overload.
- **Circuit breaker:** tạm chặn calls đến dependency đang lỗi liên tục.
- **Batching:** giảm overhead trên mỗi request khi API hỗ trợ.
- **Caching:** tránh đọc nhiều lần cùng dữ liệu không đổi.
- **Async processing:** đưa công việc không bắt buộc realtime vào Pub/Sub/Cloud Tasks.
- **Priority shedding:** giữ giao dịch critical, trì hoãn job phụ trợ.

### Điều cần tránh

- Queue vô hạn gây tăng memory và latency.
- Retry không có jitter khiến tất cả client gọi lại cùng một lúc.
- Bỏ tất cả rate limits làm downstream sụp đổ.
- Tăng replicas vô hạn khi database hoặc API quota là nút thắt.
- Đánh dấu công việc thành công khi mới chỉ enqueue nhưng nghiệp vụ cần đảm bảo xử lý cuối cùng.

Nếu giảm tải bằng cách drop requests, phải có lỗi trả về rõ ràng, telemetry và thông báo cho caller. Với những giao dịch tiền tệ hoặc thay đổi trạng thái, cần idempotency, deduplication và đối soát.

## 16. Quy trình yêu cầu tăng quota có bằng chứng

Khi đã chứng minh chạm **quota điều chỉnh được**, làm theo quy trình:

1. Xác nhận quota metric, project, region/zone và unit.
2. Đo usage hiện tại, peak, tăng trưởng, retry amplification và mức headroom.
3. Chọn giá trị đề xuất hợp lý và trình bày business impact.
4. Xác nhận không phải system limit hoặc physical capacity shortage.
5. Đánh giá chi phí khi quota cao hơn cho phép mở rộng compute/service.
6. Xin quota adjustment trong **IAM & Admin > Quotas & System Limits**.
7. Theo dõi trạng thái request; nếu cần review, có thể cần Google Cloud support/account team.
8. Chỉ cập nhật runbook/rollout sau khi quota đã **được phê duyệt và có hiệu lực**.
9. Kiểm thử lại nhu cầu thực tế; không coi email chấp thuận là kiểm chứng đầy đủ.

### IAM cho quota

Theo tài liệu Cloud Quotas, vai trò `roles/servicemanagement.quotaViewer` hỗ trợ xem quota; `roles/servicemanagement.quotaAdmin` hỗ trợ đề nghị điều chỉnh. Quyền cụ thể cần xét ở project/folder/organization và theo API.

### Thông tin nên gửi trong request

~~~yaml
request_type: quota_adjustment
project_id: "PROJECT_ID"
product: "Compute Engine"
quota_metric: "EXACT_METRIC_FROM_CONSOLE"
location: "REGION"
current_limit: "READ_FROM_CONSOLE"
peak_usage: "READ_FROM_MONITORING"
requested_limit: "CALCULATED_AND_APPROVED_VALUE"
business_reason: "Planned production launch and tested peak load"
expected_start: "YYYY-MM-DD"
alternatives_considered:
  - "Tune requests and autoscaling"
  - "Other zone/machine family"
risk_owner: "platform-team"
cost_approval: "finops-owner"
status: "proposed"
~~~

Đây là mẫu ghi nhận trong ticket, **không phải request body chuẩn của Cloud Quotas API**. Không gửi screenshot/ticket chứa secret hoặc dữ liệu cá nhân.

### Tăng quota không tương đương thay đổi tức thời

Yêu cầu có thể được phê duyệt ngay, cần review hoặc từ chối. Một số system limit không thể tăng. Tránh lên kế hoạch go-live dựa vào lời hứa quota sẽ tăng trong một thời hạn chưa được xác nhận.

## 17. Capacity planning theo nhu cầu và failure scenarios

### Ví dụ API quota

Giả định một workload có:

- Peak 250 request/giây ở frontend.
- Trung bình 4 API calls tới một Google API cho mỗi request.
- Hệ số burst/maintenance/retry được phê duyệt là 1,2.

Suy ra lưu lượng dự kiến:

~~~text
250 requests/second × 4 calls/request = 1,000 calls/second
1,000 × 60 = 60,000 calls/minute
60,000 × 1.2 = 72,000 calls/minute
~~~

Con số 72.000/min là **ước lượng workload**, không phải quota có sẵn. Đối chiếu quota service, project, user và region, đồng thời đo burst ngắn hơn 1 phút nếu sản phẩm có cửa sổ rate riêng. Nếu API còn được dùng bởi batch/worker khác, phải cộng đúng những consumer cùng scope.

### Ví dụ quota CPU và dự phòng zone

Giả định một GKE node pool cần 12 node, mỗi node 8 vCPU, cộng headroom thêm 4 node:

~~~text
Planned nodes      = 12 + 4 = 16 nodes
Regional vCPUs     = 16 × 8 = 128 vCPUs
Additional overhead = other VM/MIG/node pools and reservations
~~~

128 vCPU chưa tính các quota khác hoặc khả năng VM sẽ thực sự được cấp trong zone. Nếu chịu lỗi một zone, cần kiểm tra liệu **các zone còn lại** có capacity và quota vùng đủ cho workload theo kịch bản failover; không chỉ dựa vào tổng trạng thái bình thường.

### Nhiều chiều cùng lúc

Thực tế một workload bị giới hạn bởi **chiều nhỏ nhất**:

~~~text
Effective capacity = min(
  compute allocation quota,
  physical available capacity,
  configured autoscaling ceiling,
  available Pod IPs,
  per-instance CPU/RAM capacity,
  downstream connection/API throughput
)
~~~

Đây là mô hình khái niệm: các đại lượng có đơn vị khác nhau, nên không lấy hàm `min` trực tiếp trên số thô. Phải đổi từng chiều về **request/second hoặc throughput thực tế** trước khi so sánh.

### Tránh overprovisioning vô mục tiêu

Headroom phục vụ HA/DR là cần thiết, nhưng quota rất cao có thể cho phép autoscaling vượt kỳ vọng và tạo chi phí lớn. Kết hợp:

- SLO/error budget.
- Load test, peak forecast.
- Quota request hợp lý.
- Rate limits và max instances cân bằng.
- Budget alerts và billing anomaly detection.
- Reservations cho capacity critical.
- Ownership và review định kỳ.

## 18. Playbook theo triệu chứng

### Playbook A: Google API trả 429

1. Xác định API/method, caller và quota scope.
2. Đọc `Retry-After`, error details và metric `quota/exceeded`.
3. So sánh spike request rate với quota và downstream health.
4. Tạm giảm fan-out/batch jobs không critical.
5. Bật backoff + jitter, cap concurrency và retry budget.
6. Nếu cần capacity dài hạn, yêu cầu tăng đúng quota.
7. Theo dõi 429 rate, backlog, p95 và business success.

### Playbook B: Compute Engine không tạo được VM

1. Đọc exact reason `QUOTA_EXCEEDED` hoặc `ZONE_RESOURCE_POOL_EXHAUSTED`.
2. Với quota, xem project/region/family và usage/limit.
3. Với capacity, kiểm tra alternative zone/machine type.
4. Không stop các VM đang chạy để thử.
5. Xem reservation và provisioning model cho workload critical.
6. Re-run một lần theo change được phê duyệt, ghi kết quả.

### Playbook C: GKE Pods Pending khi traffic tăng

1. Xem `kubectl describe pod`, Events và resource requests.
2. Xem node allocatable, affinity/taints/PVC.
3. Xem Cluster Autoscaler `scaleUp`/`noScaleUp` events.
4. Phân loại quota, zone capacity, IP exhaustion, node pool max hoặc scheduling constraint.
5. Chỉnh đúng lớp; tránh giảm memory request dưới mức workload cần.
6. Quan sát Pod Ready, p95, CPU/memory, node health, chi phí và scale-down.

### Playbook D: Cloud Run 429/503 khi burst

1. Xác minh lỗi do Cloud Run platform hay ứng dụng/downstream.
2. Xem revision, instance count, concurrency, startup và 429/503 logs.
3. Xem service/revision max instances, regional CPU/memory quota.
4. Kiểm tra Cloud SQL connection pool và external API quotas.
5. Điều chỉnh max/concurrency hoặc min instances **sau khi benchmark**.
6. Thực hiện canary và giám sát p95, DB load, billing.
7. Nếu capacity không thể tăng, trả graceful 429 hoặc queue requests theo nghiệp vụ.

### Playbook E: Cloud SQL `too many connections`

1. Xem pool metrics và DB connection count.
2. Đối chiếu số application replicas, workers, recent rollout.
3. Giảm/giới hạn concurrency hoặc pool size theo phương án an toàn.
4. Tìm connection leaks/slow transactions.
5. Đánh giá database instance sizing và connection management.
6. Kiểm tra các giao dịch bị timeout/retry có bị ghi trùng không.
7. Chạy load test sau khi thay đổi.

## 19. Thực hành: mô phỏng lỗi và xác minh cách xử lý

Lab này **không cố tình tạo quá tải** lên production hay Google Cloud APIs. Dùng sandbox, log/sự kiện có sẵn hoặc dữ liệu giả để luyện phân loại.

### Bài tập 1: phân loại năm error records

~~~json
[
  {
    "service": "Compute Engine",
    "reason": "QUOTA_EXCEEDED",
    "location": "region-a",
    "quota_usage_percent": 100
  },
  {
    "service": "Compute Engine",
    "reason": "ZONE_RESOURCE_POOL_EXHAUSTED",
    "location": "zone-b",
    "quota_usage_percent": 60
  },
  {
    "service": "GKE",
    "reason": "scale.up.error.ip.space.exhausted",
    "location": "cluster-c"
  },
  {
    "service": "Cloud Run",
    "http_status": 429,
    "message": "The request was aborted because there was no available instance"
  },
  {
    "service": "Java",
    "reason": "java.lang.OutOfMemoryError: Java heap space"
  }
]
~~~

Hãy ghi cho mỗi record: lớp lỗi, cần lấy thêm bằng chứng gì, ba biện pháp có thể thử và một hành động **không được làm**. Các records được tạo để luyện tập, không phản ánh metrics hay log hiện có của project nào.

### Bài tập 2: dựng dashboard

1. Chọn một service và một quota metric.
2. Tạo chart usage, limit và quota-exceeded events nếu service có metric hỗ trợ.
3. Thêm service request rate/latency, 429/503 và downstream saturation.
4. Đặt planning alert trước khi chạm quota; incident alert cho ảnh hưởng người dùng.
5. Kiểm thử notification channel trong phạm vi được phép.
6. Ghi runbook và owner cho mỗi alert.

### Bài tập 3: làm kế hoạch đón traffic tăng

Giả sử Orders API dự báo peak gấp đôi và Cloud SQL là shared dependency. Hãy tính:

- Requests/giây và các API calls phát sinh.
- Instance count và DB pool connections.
- Regional vCPU/memory quota, GKE Pod IP headroom nếu dùng GKE.
- Số node cần khi mất một zone.
- Chi phí nếu phải tăng min instances hoặc reservation.
- Ngưỡng p95/429/503 để dừng rollout.

### Tiêu chí lab PASS

- Phân loại đúng quota, physical capacity và application exhaustion.
- Không đề xuất tăng quota cho lỗi zone capacity.
- Dùng metric/log evidence có scope và timestamp.
- Có bounded retry/backpressure.
- Có owner, escalation, rollback và chi phí ước tính.
- Không có thao tác phá hủy hoặc gây quá tải tài nguyên thật.

## 20. Mẫu incident report và quyết định GO/NO-GO

~~~yaml
incident_id: "INC-EXAMPLE-2026-001"
service: "orders-api"
environment: "production"
project_id: "PROJECT_ID"
location: "REGION_OR_ZONE"
start_time_utc: "YYYY-MM-DDTHH:MM:SSZ"
impact:
  affected_transactions: "TO_BE_MEASURED"
  error_rate: "TO_BE_MEASURED"
evidence:
  error_reason: "QUOTA_EXCEEDED"
  quota_metric: "EXACT_METRIC_FROM_CONSOLE"
  quota_limit: "MEASURED_VALUE"
  quota_usage: "MEASURED_VALUE"
  request_id: "REDACTED"
classification: "quota_allocation"
mitigation:
  action: "PAUSE_NON_CRITICAL_JOB_AND_REVIEW_QUOTA"
  owner: "platform-oncall"
permanent_actions:
  - "Capacity forecast and approved quota adjustment"
  - "Quota headroom alert and load test"
validation:
  customer_errors_recovered: false
  backlog_draining: false
  quota_headroom_confirmed: false
decision: "NO-GO_UNTIL_VALIDATION"
approvers:
  - "incident-commander"
  - "service-owner"
~~~

Đây là **mẫu ticket/sổ sự cố**, không phải cấu hình GCP. Chỉ chuyển sang GO khi điều kiện hồi phục đã được kiểm chứng và chủ hệ thống/phụ trách thay đổi chấp thuận.

### Tình huống buộc dừng rollout

- Quota/capacity không đủ khi triển khai hoặc failover.
- 429/503 tăng, nhưng chưa rõ giới hạn nằm ở đâu.
- GKE vẫn có Pod Pending không dự đoán được.
- Cloud SQL connections chạm ngưỡng và latency tăng.
- Chưa có rollback hoặc rủi ro mất dữ liệu do retry/write duplication.
- Không có người nhận cảnh báo hoặc không có quyền xử lý sự cố.

## 21. Những lỗi xử lý sai thường gặp

| Hành động sai | Vì sao nguy hiểm | Hướng tốt hơn |
|---|---|---|
| Tăng quota CPU để chữa `ZONE_RESOURCE_POOL_EXHAUSTED` | Không tạo thêm hardware trong zone | Đổi zone/machine type, reservation |
| Retry liên tục mọi `RESOURCE_EXHAUSTED` | Retry storm, phí, giữ kết nối | Đọc error details, bounded backoff |
| Tắt rồi bật VM khi zone thiếu capacity | Có thể không khởi động lại được | Giữ VM đang chạy; đánh giá reservation |
| Tăng Cloud Run max instances mà không tính DB connections | Downstream quá tải | Tối ưu pool/rate/concurrency |
| Giảm GKE memory requests quá thấp | OOM, eviction, noisy neighbor | Đo working set và chọn node phù hợp |
| Xóa tài nguyên không rõ owner để lấy quota | Có thể mất dữ liệu/DR | Asset inventory, phê duyệt trước khi xóa |
| Coi quota usage 70% chắc chắn an toàn | Spike ngắn có thể chạm rate quota | Chart cửa sổ phù hợp, quota-exceeded metric |
| Coi Pod Pending luôn là vCPU quota | Có thể là IP, PVC hoặc taints | Đọc scheduler/autoscaler events |
| Tăng DB max_connections mà không tính RAM | Tăng áp lực memory và contention | Pool budget, scaling có benchmark |
| Bỏ `Retry-After` và gọi lại ngay | Tăng tải trong lúc throttling | Backoff + jitter + deadline |
| Chuyển region mà không kiểm tra residency/DR | Vi phạm chính sách, tăng latency/egress | Security approval và load test |
| Chỉ xem metrics mà không xét impact | Có thể page vô ích hoặc bỏ lỡ sự cố | Liên kết quota với SLO/business KPIs |

## 22. Checklist vận hành trước khi tăng tải hoặc go-live

- [ ] Dịch vụ có owner, project, region/zone và workload dependency map.
- [ ] Đã liệt kê các quota allocation/rate/concurrent quan trọng và system limits.
- [ ] Usage và limit có dashboard, cùng cửa sổ đo phù hợp.
- [ ] Có cảnh báo quota exceeded và headroom đối với nguồn rủi ro cao.
- [ ] API clients có bounded retry, exponential backoff, jitter, timeout và idempotency.
- [ ] Có rate limiter, bounded queue hoặc phương án graceful degradation.
- [ ] Cloud Run max instances, concurrency và regional CPU/memory quota được kiểm thử.
- [ ] GKE node requests/allocatable, Pod IP space, autoscaler/max nodes đã được kiểm chứng.
- [ ] Compute Engine/GPU/TPU có kế hoạch xử lý zone capacity shortage.
- [ ] Reservation/provisioning model đã được đánh giá cho workload critical.
- [ ] Cloud SQL pool budget, storage và saturation được theo dõi.
- [ ] BigQuery/Pub/Sub/Storage API quotas của job cao tải đã được xem xét.
- [ ] Có load test peak/burst/soak và failover capacity test.
- [ ] Có quy trình thay đổi quota, phê duyệt chi phí và lead time.
- [ ] Có on-call, escalation, runbook và rollback policy.
- [ ] Giới hạn/chi phí không bị nâng lên vô hạn chỉ để che lỗi ứng dụng.
- [ ] Sau khôi phục, error rate, backlog, p95 và dữ liệu đều được xác minh.

## Câu hỏi ôn tập

1. Quota allocation và rate quota khác nhau như thế nào? Vì sao phải kiểm tra location/scope?
2. Vì sao `ZONE_RESOURCE_POOL_EXHAUSTED` không thể chữa bằng cách tăng quota CPU?
3. Một Pod GKE `Pending` có thể do những nguyên nhân nào ngoài thiếu CPU quota?
4. Khi Cloud Run trả 429 “no available instance”, cần xem những cấu hình nào?
5. Quota CPU trong region đã còn đủ nhưng VM vẫn không tạo được: ba giả thuyết và hướng kiểm chứng?
6. Vì sao Java container có thể bị `OOMKilled` dù heap `-Xmx` thấp hơn memory limit?
7. Khi nào `RESOURCE_EXHAUSTED` nên retry và khi nào không?
8. Tại sao phải dùng full jitter và giới hạn retry tổng?
9. Khi tăng Cloud Run instances, tại sao cần tính budget database connections?
10. Monitoring metric `serviceruntime.googleapis.com/quota/exceeded` có ý nghĩa gì? Có phải mọi product đều có cùng metric không?
11. Reservation giúp gì cho capacity và có thể thay thế quota hay không?
12. Làm thế nào chứng minh một sự cố capacity đã được khắc phục chứ không chỉ tạm biến mất?

## Kết luận

**Quota exceeded**, **resource exhausted** và **capacity shortage** là ba nhóm triệu chứng dễ nhầm nhưng phải xử lý ở các tầng khác nhau. Quota là giới hạn quản trị theo scope và loại tài nguyên; capacity là nguồn lực vật lý hoặc khả năng serving thực tế; resource exhaustion có thể xảy ra ngay trong JVM, Pod, database hoặc một hàng đợi của ứng dụng.

Một runbook tốt bắt đầu từ **mã lỗi và error details**, xác định đúng project/region/service/metric, đối chiếu usage với limit, kiểm tra tình trạng workload và **đưa ra biện pháp giảm ảnh hưởng an toàn**. Với lỗi rate, áp dụng backoff/jitter, flow control và quota planning. Với Compute Engine thiếu capacity, chọn zone/machine type/reservation phù hợp. Với GKE và Cloud Run, phải xét scheduler, autoscaling, IP, instance ceilings, memory và downstream dependencies. Với Java/Cloud SQL, kiểm soát heap, thread pool và database connections thường quan trọng hơn tăng quota.

Để ngăn sự cố tái diễn, kết hợp Cloud Monitoring quota metrics, load test, SLO, capacity forecast, quy trình tăng quota có phê duyệt, kế hoạch HA/DR và FinOps. Mục tiêu không phải “không bao giờ nhận 429”, mà là **hệ thống có thể phát hiện, giảm thiểu và phục hồi khi giới hạn xuất hiện, mà không phá vỡ dữ liệu hoặc ngân sách**.

## Tài liệu tham khảo

- [Cloud Quotas: Overview](https://cloud.google.com/docs/quotas/overview)
- [Cloud Quotas: Troubleshoot quota errors](https://cloud.google.com/docs/quotas/troubleshoot)
- [Cloud Quotas: View and manage quotas](https://cloud.google.com/docs/quotas/view-manage)
- [Cloud Quotas: Request quota adjustments](https://cloud.google.com/docs/quotas/quotas-adjust)
- [Cloud Monitoring: Chart and monitor quota metrics](https://cloud.google.com/monitoring/alerts/using-quota-metrics)
- [Compute Engine: Troubleshoot resource availability errors](https://cloud.google.com/compute/docs/troubleshooting/troubleshooting-resource-availability)
- [Compute Engine: Troubleshoot quota errors](https://cloud.google.com/compute/docs/troubleshooting/troubleshooting-quota-errors)
- [Compute Engine: Resource reservations](https://cloud.google.com/compute/docs/instances/reservations-overview)
- [Compute Engine: Regions and zones](https://cloud.google.com/compute/docs/regions-zones)
- [GKE: Troubleshoot Cluster Autoscaler scale-up](https://cloud.google.com/kubernetes-engine/docs/troubleshooting/cluster-autoscaler-scale-up)
- [GKE: Troubleshoot deployed workloads](https://cloud.google.com/kubernetes-engine/docs/troubleshooting/deployed-workloads)
- [GKE: Node allocatable resources](https://cloud.google.com/kubernetes-engine/docs/concepts/plan-node-sizes)
- [Cloud Run: Troubleshoot service issues](https://cloud.google.com/run/docs/troubleshooting)
- [Cloud Run: Maximum instances limits](https://cloud.google.com/run/docs/configuring/max-instances-limits)
- [Cloud Run: Configure maximum instances](https://cloud.google.com/run/docs/configuring/max-instances)
- [Cloud Run: Instance autoscaling](https://cloud.google.com/run/docs/about-instance-autoscaling)
- [Cloud SQL PostgreSQL: Database connections](https://cloud.google.com/sql/docs/postgres/manage-connections)
- [Pub/Sub: Quotas and limits](https://cloud.google.com/pubsub/quotas)
- [BigQuery: Quotas and limits](https://cloud.google.com/bigquery/quotas)
- [BigQuery: Optimize query computation](https://cloud.google.com/bigquery/docs/best-practices-performance-compute)
- [Cloud Storage: Request rate and access distribution guidelines](https://cloud.google.com/storage/docs/request-rate)
- [Google SRE Workbook](https://sre.google/workbook/table-of-contents/)

