# Bigtable instances, clusters và app profiles

> **Chương:** Bigtable và Memorystore  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Một nền tảng IoT nhận hàng trăm nghìn sự kiện cảm biến mỗi giây. API cần đọc giá trị mới nhất theo thiết bị với độ trễ thấp; một tác vụ phân tích quét dữ liệu lịch sử; hệ thống cũng cần tiếp tục phục vụ khi một vùng gặp sự cố. **Google Cloud Bigtable** phù hợp với dữ liệu dạng wide-column, khối lượng lớn, truy cập theo row key và dải row key. Nhưng triển khai Bigtable không dừng ở tạo bảng: phải hiểu **instance**, **cluster** và **app profile** để phân bổ tài nguyên và chọn đường đi của mỗi request.

Trong mô-đun **CLOUD_PROVIDERS_GCP**, bài này kết nối kiến thức project/IAM, vùng triển khai, Cloud Run/GKE, cơ sở dữ liệu, độ tin cậy và chi phí. Trọng tâm là cấu hình năng lực Bigtable; **Memorystore** được nhắc ở phần so sánh để tránh dùng cache như hệ thống lưu dữ liệu bền vững. Ví dụ sử dụng Bigtable **Enterprise edition** ở một project lab; tính năng phụ thuộc **Enterprise Plus** được đánh dấu riêng.

**Sau bài học, bạn có thể:**

1. Phân biệt instance (phạm vi dữ liệu), cluster (năng lực xử lý theo zone), node (compute) và app profile (đường định tuyến, workload settings).
2. Giải thích vì sao thêm cluster **không** tạo bảng mới, nhưng tạo bản sao dữ liệu và replication work.
3. Chọn **single-cluster** hoặc **multi-cluster routing**, đọc hiểu tính nhất quán, failover và single-row transactions.
4. Thiết kế app profiles riêng cho API online, batch analytics và tác vụ yêu cầu read-your-writes.
5. Tạo/kiểm tra instances, clusters và app profiles với `gcloud`; chọn app profile trong Java client.
6. Cấu hình autoscaling, ưu tiên request, Data Boost và cảnh báo CPU/storage/replication.
7. Lập kế hoạch chi phí, IAM, backup, failover và chứng minh đáp ứng SLO bằng bài lab.

## 1. Sơ đồ thành phần: dữ liệu thuộc instance, tài nguyên thuộc cluster

~~~mermaid
flowchart TB
  AP["Ứng dụng: API realtime"] -->|"app profile: api-ha"| ROUTER["Bigtable app profile\nmulti-cluster routing"]
  ETL["Ứng dụng: batch history"] -->|"app profile: batch-asia"| FIX["App profile\nsingle-cluster routing"]
  ROUTER --> A["Cluster events-asia\nZone asia-southeast1-b"]
  ROUTER --> B["Cluster events-dr\nZone asia-southeast1-c"]
  FIX --> A
  subgraph INST["Instance: bt-events-lab"]
    DATA["Tables: telemetry, device_metadata\nRow keys, column families, cells"]
    A <-->|"Replication, eventual consistency"| B
  end
  DATA -. "Dữ liệu thuộc instance;\nmỗi cluster có một bản sao" .-> A
  DATA -.-> B
  A --> N1["Nodes / autoscaling"]
  B --> N2["Nodes / autoscaling"]
~~~

Sơ đồ minh họa hai cluster cùng region nhưng khác zone. Để chịu **sự cố cả region**, cần cluster ở **region khác** và kế hoạch network/latency/residency riêng; hai zone trong một region không thay thế regional DR.

| Đối tượng | Phạm vi | Đặc trưng | Ví dụ |
| --- | --- | --- | --- |
| **Project** | Google Cloud | IAM, billing, API enablement | `LAB_PROJECT_ID` |
| **Bigtable instance** | Container dữ liệu | Chứa tables, clusters, app profiles; có edition/storage type | `bt-events-lab` |
| **Table** | Nằm trong instance | Row key, column families, cells/versions | `telemetry` |
| **Cluster** | Thuộc instance, ở **một zone** | Phục vụ đọc/ghi và replication, có số nodes và storage | `events-asia` |
| **Node** | Trong cluster | Năng lực tính toán/đọc/ghi, quản lý/compaction | 3 nodes minh họa |
| **App profile** | Thuộc instance | Routing, request priority, compute/isolation; được client chọn | `api-ha` |
| **Bigtable client** | Trong app | Gửi RPC với project, instance và app profile ID | Java Cloud Run |

**Quy tắc nền tảng:** Table thuộc **instance**, không thuộc riêng cluster. Khi có nhiều clusters, **mọi cluster lưu bản sao của mọi table trong instance**; không dùng cluster A chỉ để chứa table X còn cluster B chỉ chứa table Y. <https://docs.cloud.google.com/bigtable/docs/instances-clusters-nodes>

### 1.1. Không nhầm Bigtable với Memorystore

| Nhu cầu | Bigtable | Memorystore (Redis/Valkey) |
| --- | --- | --- |
| Dữ liệu khối lượng lớn, tồn tại lâu dài | Phù hợp | Không phải lựa chọn chính để lưu mọi dữ liệu lịch sử |
| Row-key lookup, scan dải key có tổ chức | Điểm mạnh | Chủ yếu key-value/cấu trúc in-memory |
| Cache hot keys, session, rate-limit state ngắn hạn | Có thể phục vụ nhưng không tối ưu như cache chuyên dụng | Thường phù hợp hơn |
| Replication/HA | Nhiều clusters theo app profile | Phụ thuộc sản phẩm, tier/topology |
| Giao dịch SQL nhiều bảng và JOIN | Không phải mô hình chính | Không phải cơ sở dữ liệu SQL |

Không chọn Bigtable cho một CRUD app nhỏ chỉ vì cần high availability; hãy đánh giá Firestore, Cloud SQL/AlloyDB hay cache theo access patterns và tổng chi phí.

## 2. Instance: phạm vi quản trị và quyết định khó đổi

Instance định nghĩa **phạm vi tables, app profiles và clusters**. ID instance là định danh ổn định mà clients sử dụng. Instance có thể có một hoặc nhiều clusters ở các locations được phép. Một số quyết định ban đầu ảnh hưởng lâu dài:

| Quyết định | Cần cân nhắc |
| --- | --- |
| **Edition** | Enterprise / Enterprise Plus, tính năng, SLA/giá tương ứng; hỗ trợ chuyển edition theo quy định |
| **Storage type** | SSD hay HDD, workload latency/throughput và giá; **không đổi SSD ↔ HDD trên instance hiện có** |
| **Cluster locations** | Độ trễ tới ứng dụng, failure domains, data residency, egress |
| **Node/autoscaling policy** | Peak capacity, headroom cho replication/failover, chi phí |
| **Table/GC policy** | Retention theo column family; áp dụng chung qua các clusters |
| **CMEK khi cần** | Encryption key, location, quyền KMS và khả năng khôi phục |

Bigtable không có khái niệm “mỗi cluster có một bộ bảng độc lập trong cùng instance”. Nếu cần **data isolation** thật sự giữa production và sandbox, cân nhắc **instances/projects riêng** thay vì chỉ tách app profiles.

### 2.1. Edition và lưu trữ

- **Enterprise** phù hợp phần lớn workloads Bigtable truyền thống.
- **Enterprise Plus** mở rộng một số tính năng/khả năng, như **in-memory tier** đang ở trạng thái **Preview** tại thời điểm tài liệu được đối chiếu. Không mặc nhiên đưa Preview vào yêu cầu production.
- **SSD** thường phù hợp latency thấp và workload nhiều read/write. **HDD** có trade-off chi phí/throughput và không tối ưu cho mọi random read.
- Một instance dùng cùng storage type cho toàn bộ clusters; **storage type được chọn khi tạo và không thể đổi**.

Nên xác minh edition, quota, vùng hỗ trợ và price calculator trước khi tạo cluster có phí.

## 3. Cluster, node và năng lực phục vụ

Cluster là nơi Bigtable phục vụ requests. Mỗi cluster nằm trong **một zone** và có ít nhất một node; khả năng đáp ứng phụ thuộc node count, I/O, row-key distribution, storage, kích thước row, tỷ lệ đọc/ghi và công việc replication.

**Thêm node không thêm một bản dữ liệu thứ hai:** node mở rộng năng lực xử lý và dung lượng phục vụ **trong một cluster**. **Thêm cluster** làm instance có thêm bản sao dữ liệu và thêm failure domain.

| Tác vụ | Cấp tác động |
| --- | --- |
| Tăng số nodes để hấp thụ QPS | Cluster |
| Đổi min/max autoscaling | Cluster |
| Thêm cluster khác zone | Instance + replication, ảnh hưởng toàn bộ bảng |
| Tạo table/column family | Instance; đồng bộ tới mọi clusters |
| Thay app profile route-to | App profile; thay đường request của ứng dụng dùng profile |
| Đổi row-key schema | Table + application; không giải quyết bằng việc tăng clusters đơn thuần |

### 3.1. Một cụm không có nghĩa một “máy lưu dữ liệu”

Bigtable lưu dữ liệu trên lớp storage phân tán, node phục vụ requests và làm công việc bảo trì. Khi cluster thiếu compute, có thể tăng latency/CPU, system errors hoặc scan chậm. Tăng số cluster để “nâng write throughput” **không đảm bảo** tăng tổng write throughput: mỗi write tới một cluster phải được **replicate sang các cluster còn lại**, tạo thêm công việc. <https://docs.cloud.google.com/bigtable/docs/replication-performance>

### 3.2. Sizing trước khi chọn nodes

| Chỉ số workload | Ảnh hưởng |
| --- | --- |
| Read/write requests per second và bytes/s | Compute/network |
| P95/P99 read latency | Sizing, hot tablets, row-key distribution |
| Batch scans và bulk import | Tài nguyên tranh chấp API online |
| Total compressed storage | Storage capacity và node budget của **mỗi** cluster |
| Replication input/output | CPU, network, freshness khi nhiều clusters |
| Số vùng và dữ liệu được phép đặt ở mỗi vùng | Compliance, latency và egress |
| Failover peak QPS | Cluster còn sống phải nhận thêm traffic |
| Garbage collection/change streams | Background CPU/storage chi phí |

Đừng copy một con số nodes từ demo sang production. Dùng benchmark tải thật và **Monitoring/Key Visualizer**.

## 4. App profile là “hợp đồng định tuyến” của client

**Application profile** là resource trong instance. Ứng dụng khi kết nối cung cấp **app profile ID**, Bigtable dùng nó để quyết định cluster routing và một số thuộc tính workload. App profile **không phải Kubernetes profile**, **không phải connection pool của JDBC**, và **không tạo IAM security boundary**.

### 4.1. Standard app profile

Một standard app profile có thể khai báo:

- **Single-cluster routing:** chỉ đưa requests tới một cluster xác định.
- **Multi-cluster routing:** chọn cluster sẵn sàng gần client; hỗ trợ tự failover trong phạm vi tập clusters.
- **Cluster group routing:** chỉ cho phép định tuyến trong subset clusters.
- **Row-affinity routing:** cố gắng đưa single-row operations của một row key tới cùng cluster.
- **Request priority:** `PRIORITY_HIGH`, `PRIORITY_MEDIUM` hoặc `PRIORITY_LOW`.
- **Single-row transactions:** chỉ cho phép với **single-cluster routing**, khi thực sự cần read-modify-write/check-and-mutate.

**Hợp đồng bắt buộc:** Nếu app muốn tăng counter bằng `ReadModifyWriteRow` hoặc cập nhật theo điều kiện bằng `CheckAndMutateRow`, hãy chọn **single-cluster app profile** và bật transactional writes. Dùng multi-cluster routing cho thao tác này có thể gây xung đột/data loss; Bigtable không cho bật transactional writes trên multi-cluster profile.

### 4.2. Default profile và custom profiles

Bigtable tạo app profile **`default`** lúc tạo instance:

- Nếu instance ban đầu có **một** cluster: `default` dùng **single-cluster**, cho phép single-row transactions.
- Nếu instance ban đầu có **từ hai clusters**: `default` dùng multi-cluster routing, không cho single-row transactions.
- **Thêm hoặc xóa cluster về sau không tự đổi route policy của `default`.**

Nếu client không chỉ định profile ID, nó sẽ dùng `default`. Vì vậy không nên dựa vào “đã thêm cluster thứ hai thì ứng dụng tự failover”: phải đọc profile đang dùng. **Tạo custom app profiles và truyền ID rõ ràng** cho từng workload sẽ dễ quan sát và đổi có kiểm soát hơn. <https://docs.cloud.google.com/bigtable/docs/app-profiles>

### 4.3. Ma trận các kiểu định tuyến

| Kiểu | Tính nhất quán | Failover | Single-row transaction? | Ví dụ |
| --- | --- | --- | --- | --- |
| **Single cluster** | Read-your-writes trong cùng cluster; yêu cầu không có conflicting writes ở cluster khác | **Manual** | **Có**, khi bật | Counter/conditional write |
| **Multi cluster / any** | **Eventual** giữa clusters | **Automatic** | **Không** | API đọc nhiều khu vực |
| **Multi / group** | Eventual | Auto trong cluster group | Không | Tách cluster chuyên dụng |
| **Multi + row affinity** | Tăng xác suất read-your-writes cho **single-row requests**, không cam kết | Auto; có thể đổi cluster | Không | Hot device state theo row key |
| **Data Boost** | Read-only analytical jobs, snapshot/consistency semantics theo sản phẩm | Single cluster | Không dành cho transactional writes | Quét lịch sử |

Row-affinity **không bảo đảm strong consistency**: failover, overload hoặc thay đổi cluster membership có thể chuyển row key sang cluster khác. Không dùng nó để bảo đảm tính chính xác của giao dịch tiền hoặc đặt hàng.

### 4.4. Tạo app profile không cấp quyền

Google Cloud IAM kiểm soát người được đọc/ghi Bigtable tables; profiles chủ yếu điều chỉnh routing, isolation và telemetry. Muốn read-only client, dùng `roles/bigtable.reader` hoặc quyền phù hợp trên table/authorized view; ghi dữ liệu cần `roles/bigtable.user` hay custom permissions. **Không coi app profile LOW priority là một lớp bảo vệ dữ liệu.**

## 5. Replication và tính nhất quán

Với một cluster, Bigtable cung cấp strong consistency cho thao tác vào cluster đó. Với nhiều clusters, Bigtable replicate dữ liệu **bất đồng bộ** giữa các clusters. **Mỗi cluster là primary** cho đọc và ghi; không có một cluster mặc định read-only.

~~~mermaid
sequenceDiagram
    participant A as API write via cluster A
    participant BA as Bigtable cluster A
    participant BB as Bigtable cluster B
    participant R as Reader via cluster B
    A->>BA: MutateRow(device-42, value=18)
    BA-->>A: Write OK
    R->>BB: Read device-42 ngay
    BB-->>R: Có thể thấy giá trị cũ
    BA-->>BB: Replication async
    R->>BB: Read sau khi đồng bộ
    BB-->>R: Thấy giá trị mới
~~~

**Mấu chốt:** Request ghi thành công tại A **không chứng minh B đã nhận dữ liệu**. Replication latency không có mốc thời gian cứng “chỉ cần sleep 1 giây”; có thể tăng khi cluster overload, khác region hoặc mạng gặp vấn đề. <https://docs.cloud.google.com/bigtable/docs/replication-overview>

### 5.1. Read-your-writes và single-cluster

Nếu cả read và write của một workload đều đi **cùng cluster** thông qua single-cluster app profile, workload có thể giữ read-your-writes. Nếu **mọi** ứng dụng dùng cùng cluster và không tạo concurrent writes ở cluster khác, một số thiết kế multi-cluster instance vẫn có strong consistency cho workload. Nhưng khi manual failover sang cluster B lúc replication chưa hoàn tất, đọc có thể **stale**.

### 5.2. Xung đột ghi nhiều cluster

Bigtable định danh mỗi cell theo `row key / column family / column qualifier / timestamp`. Khi hai clusters ghi cùng cell với cùng timestamp, Bigtable dùng cơ chế phân giải xung đột **last-write-wins nội bộ**. Các operations mang tính transaction (read-modify-write, conditional writes) chạy **độc lập** trên hai clusters có thể dẫn tới mất ý nghĩa nghiệp vụ.

Ví dụ counter tăng từ 7 lên 8 ở A và cũng tăng 7 lên 8 ở B. Replication không tự hiểu ý định “tăng hai lần để thành 9”. Nếu phù hợp loại dữ liệu, cân nhắc **aggregate cells/AddToCell** theo khả năng hỗ trợ để có merge semantics rõ ràng; nếu không, đưa mọi transactional writes của cùng row về **một** cluster.

### 5.3. Chọn loại consistency theo yêu cầu

| Yêu cầu | Thiết kế ưu tiên | Đánh đổi |
| --- | --- | --- |
| Giá trị thiết bị mới nhất phải thấy ngay sau ghi trong một region | Single-cluster profile | Không tự failover |
| Đọc dữ liệu replicated ở vùng gần khách hàng, chấp nhận vài giây trễ | Multi-cluster routing | Eventual consistency |
| HA tự chuyển khi cluster lỗi | Multi-cluster (any/group) | Có thể đọc cũ sau failover |
| Increments và conditional writes | Single-cluster + transactional writes | Tránh conflicting writes qua nhiều clusters |
| Batch analytics không gây CPU spikes cho API online | Data Boost profile hoặc dedicated cluster | Chi phí compute/storage và freshness constraints |

### 5.4. Failover không thay backup

Replication là **nhiều bản sao của dữ liệu đang hoạt động**, không phải backup bất biến: lỗi logic, xóa bảng, ghi nhầm hoặc GC policy sai có thể được replicate. Dùng **Bigtable backup/restore**, retention và drill riêng. Tùy cấu hình, regional replication còn có giới hạn residency/egress; phải được phê duyệt trước.

## 6. Lab topology và preflight

Ví dụ chung trong bài:

| Trường | Giá trị minh họa |
| --- | --- |
| Project | `LAB_PROJECT_ID` |
| Bigtable instance | `bt-events-lab` |
| Edition / storage | `ENTERPRISE` / `ssd` |
| Cluster A | `events-asia`, zone `asia-southeast1-b` |
| Cluster B | `events-dr`, zone `asia-southeast1-c` |
| Table | `telemetry` |
| App profile online | `api-ha` (multi-cluster) |
| App profile transaction | `counter-single` (single-cluster A) |
| App profile batch | `batch-asia` (single-cluster A, low priority) |

**Ghi nhớ về chi phí:** Bigtable nodes và dữ liệu mỗi cluster có phí **ngay cả khi chỉ thử nghiệm**, replication cũng tiêu thụ tài nguyên và có thể có network charges. Nên ưu tiên lab được quản trị viên cấp sẵn; nếu chỉ học lý thuyết, dùng **bài tập mô phỏng**, không tạo 2 clusters có phí chỉ để chạy theo hướng dẫn.

**Điều kiện:** project/billing và Bigtable APIs hợp lệ, `gcloud` đủ mới, có `roles/bigtable.admin` hoặc custom role cho thao tác quản trị; runtime apps dùng quyền nhỏ hơn. Cần kiểm tra quota theo zone và các giới hạn riêng của edition/node scale. Không cấp Project Owner/Editor cho một service account chỉ để đọc dữ liệu.

### 6.1. Lệnh preflight chỉ đọc

~~~bash
gcloud config get-value project
gcloud services list --enabled --project=LAB_PROJECT_ID

gcloud bigtable instances list --project=LAB_PROJECT_ID

# Nếu instance lab đã tồn tại:
gcloud bigtable instances describe bt-events-lab \
  --project=LAB_PROJECT_ID

gcloud bigtable clusters list \
  --instances=bt-events-lab \
  --project=LAB_PROJECT_ID

gcloud bigtable app-profiles list \
  --instance=bt-events-lab \
  --project=LAB_PROJECT_ID
~~~

Nếu instance chưa có, những lệnh phụ thuộc vào `bt-events-lab` có thể trả `NOT_FOUND`; đó là tín hiệu thiếu lab resource, không phải lý do tự tạo production instance.

## 7. Tạo instance/cluster — chỉ trong sandbox được phê duyệt

### 7.1. Tạo instance một cluster (có phí)

~~~bash
# THAY ĐỔI TÀI NGUYÊN, PHÁT SINH PHÍ
# Chỉ chạy nếu project LAB, quota, zone và ngân sách đã được phê duyệt.
gcloud bigtable instances create bt-events-lab \
  --display-name="Bigtable events lab" \
  --edition=ENTERPRISE \
  --cluster-storage-type=ssd \
  --cluster-config=id=events-asia,zone=asia-southeast1-b,nodes=3 \
  --project=LAB_PROJECT_ID
~~~

Đây là ví dụ dùng `--cluster-config` được khuyến nghị thay cho các cờ tạo cluster deprecated. Con số **3 nodes chỉ minh họa**, không phải mặc định/minimum cho mọi edition. Xem region/quota/giá chính xác trước khi chạy. Nếu instance ID đã tồn tại, **không tạo đè/xóa**.

### 7.2. Thêm cluster B để bật replication

~~~bash
# THAY ĐỔI INSTANCE, phát sinh compute/storage và replication
gcloud bigtable clusters create events-dr \
  --instance=bt-events-lab \
  --zone=asia-southeast1-c \
  --num-nodes=3 \
  --project=LAB_PROJECT_ID
~~~

Việc thêm cluster B sẽ replicate **tất cả tables** từ instance sang B. **Không tự chuyển routing policy của profile `default`** khi instance ban đầu được tạo với một cluster. Đợi replication/health đạt yêu cầu trước khi dùng B cho production traffic.

**Hai cluster hai zone cùng region không bảo vệ khi cả region mất.** Muốn regional DR, phải lựa chọn region thứ hai theo quy định dữ liệu và tính chi phí/độ trễ.

### 7.3. Xác minh sau thay đổi

~~~bash
gcloud bigtable instances describe bt-events-lab \
  --project=LAB_PROJECT_ID

gcloud bigtable clusters list \
  --instances=bt-events-lab \
  --project=LAB_PROJECT_ID
~~~

Đọc Console **Bigtable → Instances → Clusters** để xem zone, node count, autoscaling, status và storage. **Cluster READY không bảo đảm replication lag bằng 0 hoặc đủ capacity khi failover.**

## 8. Tạo ba standard app profiles cho ba workload

### 8.1. API online: multi-cluster và auto failover

~~~bash
# THAY ĐỔI: tạo profile để online requests có thể route tới A/B
gcloud bigtable app-profiles create api-ha \
  --instance=bt-events-lab \
  --route-any \
  --priority=PRIORITY_HIGH \
  --description="Online API; multi-cluster auto failover" \
  --project=LAB_PROJECT_ID
~~~

**Hiệu quả:** Requests có thể tới cluster gần client và tự failover khi cluster đó không sẵn sàng. **Đánh đổi:** consistency giữa clusters là eventual, không dùng single-row transactional writes trên profile này.

Nếu phải giới hạn failover chỉ trong A/B khi sau này thêm cluster C:

~~~bash
# Ví dụ tạo profile khác; chỉ định group có thể dùng cho auto failover
gcloud bigtable app-profiles create api-ab-only \
  --instance=bt-events-lab \
  --route-any \
  --restrict-to=events-asia,events-dr \
  --priority=PRIORITY_HIGH \
  --project=LAB_PROJECT_ID
~~~

Với `--restrict-to`, thêm cluster mới **không tự** thêm cluster đó vào routing group. Điều này hữu ích khi giữ cluster phân tích/DR riêng, nhưng cũng có thể khiến app không dùng cluster mới khi sự cố nếu operator quên cập nhật group.

### 8.2. Giao dịch một hàng: single-cluster

~~~bash
# THAY ĐỔI: cho phép CheckAndMutateRow / ReadModifyWriteRow
gcloud bigtable app-profiles create counter-single \
  --instance=bt-events-lab \
  --route-to=events-asia \
  --transactional-writes \
  --priority=PRIORITY_HIGH \
  --project=LAB_PROJECT_ID
~~~

**Không** thêm `--route-any`/`--restrict-to` vào lệnh này. Nếu các writers khác vẫn gửi conflicting transactional writes cùng hàng tới cluster B, consistency có thể hỏng dù profile A đã đúng.

### 8.3. Batch analytics: một cluster và ưu tiên thấp

~~~bash
# THAY ĐỔI: scan batch qua A, giảm cạnh tranh với high priority API
gcloud bigtable app-profiles create batch-asia \
  --instance=bt-events-lab \
  --route-to=events-asia \
  --priority=PRIORITY_LOW \
  --project=LAB_PROJECT_ID
~~~

Priority là gợi ý **scheduler** của Bigtable trong cluster; **không** tạo compute isolation tuyệt đối và không giới hạn quyền đọc. Đối với scans lớn, cân nhắc **Data Boost** để cách ly compute tốt hơn.

### 8.4. Kiểm chứng profiles

~~~bash
gcloud bigtable app-profiles list \
  --instance=bt-events-lab \
  --project=LAB_PROJECT_ID

gcloud bigtable app-profiles describe api-ha \
  --instance=bt-events-lab \
  --project=LAB_PROJECT_ID

gcloud bigtable app-profiles describe counter-single \
  --instance=bt-events-lab \
  --project=LAB_PROJECT_ID
~~~

Cần xác nhận *routing policy thực tế* và *client đã chọn profile ID đúng*. Lệnh tạo profile thành công không đảm bảo ứng dụng không còn dùng profile `default`.

## 9. Java client: chọn app profile ngay khi tạo client

Google Cloud Bigtable Java Data Client lấy credentials bằng **Application Default Credentials (ADC)**. Ứng dụng chạy trên Cloud Run/GKE/Compute Engine nên sử dụng runtime service account và IAM phù hợp, không lưu JSON key trong image/Git.

### 9.1. Đọc một hàng bằng profile được chỉ định

Ví dụ với thư viện `com.google.cloud:google-cloud-bigtable`, giả định table `telemetry` tồn tại và có row key `device#0042#20261119T0900Z`:

~~~java
import com.google.cloud.bigtable.data.v2.BigtableDataClient;
import com.google.cloud.bigtable.data.v2.BigtableDataSettings;
import com.google.cloud.bigtable.data.v2.models.Row;

public final class ReadTelemetry {
    public static void main(String[] args) throws Exception {
        String project = "LAB_PROJECT_ID";
        String instance = "bt-events-lab";
        String appProfile = "api-ha";

        BigtableDataSettings settings = BigtableDataSettings.newBuilder()
            .setProjectId(project)
            .setInstanceId(instance)
            .setAppProfileId(appProfile)
            .build();

        try (BigtableDataClient client = BigtableDataClient.create(settings)) {
            Row row = client.readRow(
                "telemetry", "device#0042#20261119T0900Z");
            if (row == null) {
                System.out.println("Row not found");
            } else {
                System.out.println("Row key: " + row.getKey().toStringUtf8());
            }
        }
    }
}
~~~

**Giải thích:**

- `setProjectId` xác định project chứa instance.
- `setInstanceId` xác định **instance**, không phải cluster ID.
- `setAppProfileId("api-ha")` gửi request theo chính sách multi-cluster/HA đã tạo.
- `client.readRow` trả dữ liệu của **một row** hoặc `null` nếu chưa có.
- Ví dụ chỉ in row key để tránh ghi cell values/PII vào logs.

Mã là chương trình nhỏ minh họa API, cần dependency/version tương thích với JDK và một table có dữ liệu thật. **Không chạy bài demo này để chứng minh read-your-writes tức thời trên `api-ha`**; multi-cluster profile có eventual consistency.

### 9.2. Vì sao không tạo BigtableDataClient mỗi request?

Tạo client/channel liên tục làm tăng TLS/network setup, số threads và latency. Trong Cloud Run/GKE nên tạo một client dùng lại theo vòng đời process; đóng khi shutdown. Nếu cần hai routing policies, tạo các clients/settings **riêng** cho `api-ha` và `counter-single`, rồi gửi đúng thao tác tới đúng client.

**Không** lấy cluster ID truyền vào `setInstanceId` để chuyển vùng; routing là trách nhiệm app profile.

### 9.3. Một ví dụ chọn profile sai

Đoạn code:

~~~java
BigtableDataSettings wrongSettings = BigtableDataSettings.newBuilder()
    .setProjectId("LAB_PROJECT_ID")
    .setInstanceId("bt-events-lab")
    .setAppProfileId("api-ha")
    .build();

// Không dùng cấu hình api-ha với read-modify-write/check-and-mutate
// khi profile này đang multi-cluster.
~~~

Không cần viết thêm lệnh mutate: lỗi nằm ở **quyết định routing** chứ không phải cú pháp mutation. Chuyển sang `counter-single` cho thao tác transaction, đồng thời bảo đảm không có transactional writes cạnh tranh tại cluster khác.

## 10. Autoscaling và capacity planning

Bigtable hỗ trợ **manual node allocation** hoặc **autoscaling** theo từng cluster. Autoscaling điều chỉnh nodes dựa trên CPU/storage targets, không dựa duy nhất vào HTTP request count.

| Tham số | Ý nghĩa | Cảnh báo |
| --- | --- | --- |
| `autoscaling-min-nodes` | Số nodes thấp nhất được giữ | Đủ xử lý baseline, replication và storage |
| `autoscaling-max-nodes` | Mức trần scaling | Phải đủ headroom khi traffic/failover tăng |
| `autoscaling-cpu-target` | CPU utilization mục tiêu, **10–80%** | Mục tiêu quá cao làm giảm headroom cho spikes |
| `autoscaling-storage-target` | Dung lượng mục tiêu GiB/node | Tùy SSD/HDD, giới hạn theo edition |
| `num-nodes` | Số nodes thủ công | Không đồng thời là chế độ autoscaling |

Bigtable autoscaler tăng nodes nhanh khi CPU vượt target, nhưng **không cam kết failover không ảnh hưởng latency** nếu cluster nhận traffic tăng đột ngột. Với Enterprise Plus, yếu tố **2× node scaling** có thể yêu cầu số min nodes chẵn; xác minh constraint của edition trước khi đặt giá trị. <https://docs.cloud.google.com/bigtable/docs/autoscaling>

### 10.1. Bật autoscaling cho cluster A

~~~bash
# THAY ĐỔI cluster, có tác động chi phí/capacity.
# Chỉ thực hiện trong project lab với budget rõ ràng.
gcloud bigtable clusters update events-asia \
  --instance=bt-events-lab \
  --autoscaling-min-nodes=2 \
  --autoscaling-max-nodes=8 \
  --autoscaling-cpu-target=60 \
  --project=LAB_PROJECT_ID
~~~

Cấu hình 2–8 và CPU 60% chỉ minh họa cho Enterprise; nếu edition/zone/feature có quy định khác, dùng giá trị hợp lệ theo CLI và tài liệu. Nếu storage pressure cao, autoscaler cũng cần giữ đủ nodes; đừng giảm min nodes đến mức vượt hard limit dung lượng.

### 10.2. Sizing cho kịch bản failover

Giả sử:

| Cluster | Tải thường | Năng lực đã dự trù | Khi A ngừng hoạt động |
| --- | --- | --- | --- |
| A | 60% của tổng traffic | 6 nodes | 0 traffic |
| B | 40% của tổng traffic | 4 nodes | Nhận thêm 60% traffic |
| B sau failover | 100% | Cần năng lực cao hơn, tùy workload | Có thể cần scale và tăng p95 |

Đây là **bài toán capacity**, không phải công thức “6 + 4 nodes = luôn đủ 100%”: phân phối row keys, loại reads/writes, overhead replication và storage cũng quyết định throughput. Với failover cần RTO rất ngắn, **provision headroom trước**, không chỉ kỳ vọng autoscaler kịp tăng nodes.

### 10.3. Replication tăng cả compute lẫn storage

Một instance có hai clusters có **hai bản sao dữ liệu**. Mỗi cluster có thể phải xử lý background replication/compaction ngoài traffic ứng dụng. Vì vậy:

- Thêm cluster có thể cải thiện **read latency/HA**, nhưng làm tăng chi phí lưu trữ/compute.
- Thêm cluster **không mặc định tăng write throughput tổng**.
- Mọi cluster phải có đủ nodes để chứa và replicate dữ liệu, ngay cả cluster không được app profile nào chọn làm primary endpoint.
- Chỉ số **CPU average thấp** không đảm bảo không có hotspot; kiểm tra CPU của **hottest node** và Key Visualizer.

## 11. Request priority, Data Boost và workload isolation

### 11.1. Request priorities

Standard app profile có mức `PRIORITY_HIGH` / `PRIORITY_MEDIUM` / `PRIORITY_LOW`. Với cluster có cả API và batch, có thể ưu tiên requests của API. Priority giúp scheduler phân biệt loại việc, **không phải hard rate limit, dedicated node pool hay IAM control**.

Ví dụ thay batch sang low priority:

~~~bash
# THAY ĐỔI profile, ảnh hưởng workload đang sử dụng
gcloud bigtable app-profiles update batch-asia \
  --instance=bt-events-lab \
  --priority=PRIORITY_LOW \
  --project=LAB_PROJECT_ID
~~~

Cần đo CPU, latency và throughput trước/sau. Nếu API và batch vẫn tranh chấp mạnh, định tuyến batch sang cluster khác hoặc dùng Data Boost.

### 11.2. Data Boost cho big scans

**Data Boost** cung cấp serverless compute cho **high-throughput read jobs**, thay vì dùng nodes của cluster để phục vụ scan lớn. Nó dùng **Data Boost app profile** với **single-cluster routing**, tách workload phân tích khỏi serving CPU. Không dùng Data Boost profile cho transactional writes hay API read/write thông thường.

~~~bash
# THAY ĐỔI: tạo Data Boost app profile theo điều kiện edition hỗ trợ
gcloud bigtable app-profiles create history-boost \
  --instance=bt-events-lab \
  --route-to=events-asia \
  --data-boost \
  --data-boost-compute-billing-owner=HOST_PAYS \
  --project=LAB_PROJECT_ID
~~~

**Cần kiểm tra feature availability, workload eligibility và phí Data Boost** trước khi chạy. Data Boost có semantics riêng về freshness/snapshot, không được dùng để kiểm tra giá trị “vừa ghi xong”. Lệnh chỉ tạo profile; client/job phải **chọn profile ID** để thực sự sử dụng compute riêng.

### 11.3. In-memory tier khác Memorystore

Ở một số cấu hình **Enterprise Plus (Preview)**, app profile có thể dùng **in-memory tier** để tăng tốc eligible point reads. Đây là tính năng **của Bigtable**, không phải Memorystore Redis/Valkey; có giới hạn feature, routing và chi phí khác, **chỉ single-cluster**. Không đưa tính năng Preview làm tiền đề bắt buộc của bài lab hoặc production.

## 12. Failover: tự động và thủ công

~~~mermaid
flowchart TD
  E["Cluster A gặp lỗi"] --> PROFILE{"App profile type?"}
  PROFILE -- "multi-cluster"| AUTO["Bigtable có thể auto reroute\nđến B trong group"]
  PROFILE -- "single-cluster"| MAN["Operator đánh giá lag/capacity\nrồi update profile route-to=B"]
  AUTO --> CHECK["Test request success, p95,\nreplication freshness, data correctness"]
  MAN --> CHECK
  CHECK --> Q{"Đáp ứng SLO/consistency?"}
  Q -- "Không" --> FIX["Điều chỉnh capacity, route,\nchặn ghi rủi ro, runbook"]
  Q -- "Có" --> HOLD["Theo dõi và ghi incident"]
~~~

### 12.1. Multi-cluster automatic failover

Với `api-ha`, khi một cluster không xử lý được request, Bigtable có thể chuyển sang cluster còn sẵn sàng theo policy. Tốc độ chuyển **phụ thuộc request deadline và hiện trạng**. Không mặc định **zero errors/zero stale reads**; ứng dụng vẫn cần retry phù hợp với tính idempotent, timeout và monitoring.

### 12.2. Single-cluster manual failover

Với profile `batch-asia`, operator có thể đổi route-to sau khi xác minh cluster B khỏe và đọc được dữ liệu phù hợp:

~~~bash
# THAY ĐỔI ĐƯỜNG TRAFFIC, chỉ làm trên app profile lab.
# Kiểm tra replication lag và data correctness trước.
gcloud bigtable app-profiles update batch-asia \
  --instance=bt-events-lab \
  --route-to=events-dr \
  --project=LAB_PROJECT_ID
~~~

Lệnh đổi định tuyến **không copy dữ liệu tức thì**, chỉ chuyển requests sang bản sao B có sẵn. Nó ảnh hưởng **tất cả clients dùng `batch-asia`**. Với profile cho single-row transactions, failover còn cần đảm bảo không tồn tại conflicting writes tại cluster cũ và xử lý các writes chưa replicate.

**Không dùng `--force` để bỏ qua warnings consistency chỉ vì thời gian sự cố gấp.** Runbook phải xác định chấp nhận mất freshness đến mức nào, cần chặn ghi hay không, và cách failback.

### 12.3. Đừng quên khả năng đọc cũ

Nếu replication lag 40 giây khi A mất, một client đọc B ngay có thể nhận state **chưa chứa các writes vừa được ack ở A**. Ứng dụng phải quyết định:

- Có chấp nhận **eventual consistency** như dữ liệu telemetry lịch sử không?
- Có bắt buộc dữ liệu chính xác ngay như hạn mức, thứ tự tài chính không?
- Có cần đặt app ở trạng thái read-only/degraded mode đến khi xác minh dữ liệu?
- Khi nào failback, và làm sao ngăn ghi hai nơi gây xung đột?

## 13. Bảo mật và trách nhiệm vận hành

### 13.1. Phân quyền Google Cloud IAM

| Vai trò | Quyền điển hình | Dùng cho |
| --- | --- | --- |
| `roles/bigtable.admin` | Quản lý instances, clusters, profiles, tables | Team hạ tầng, chỉ khi cần |
| `roles/bigtable.user` | Đọc/ghi dữ liệu theo phạm vi được cấp | Runtime ingestion/API |
| `roles/bigtable.reader` | Chỉ đọc dữ liệu | Reporting/sandbox readers |
| Roles tùy chỉnh/Authorized Views | Thu hẹp permissions và phạm vi dữ liệu | Đa ứng dụng/tenant khi phù hợp |

Cấp quyền ở resource scope nhỏ nhất được hỗ trợ; không dùng `roles/editor` hoặc service account JSON key dài hạn trong Cloud Run/GKE. **App profile không giới hạn ai được xem rows của table**; quyền dữ liệu vẫn do IAM và cơ chế bảo vệ chuyên dụng quyết định.

### 13.2. Network và vị trí dữ liệu

- Bigtable dùng endpoint Google APIs (TLS), kiểm tra DNS/egress/firewall và **Private Google Access/Private Service Connect** khi kiến trúc private network yêu cầu.
- Truy cập vào Bigtable thông qua API không tương đương database chạy ngay trong subnet của bạn; instance/cluster có locations riêng.
- Với multi-region clusters, dữ liệu của tables được replicate sang các locations đó; phải đánh giá **data residency** trước khi thêm cluster.
- Có thể dùng **CMEK** theo khả năng hỗ trợ, nhưng quản trị KMS key/IAM/rotation là một phần của DR.
- Audit Logs, service account impersonation và change approvals cần theo dõi thay đổi app profile routing/cluster placement.

### 13.3. Hướng bảo vệ dữ liệu

Replication chống sự cố cluster/region phù hợp nhưng **không thay backup**. Đối với xóa nhầm table, corruption do ứng dụng hoặc thay GC rule, cần Bigtable backups, retention, thử restore. Cũng phải có source-of-truth cho IAM, profiles, autoscaling config và các định nghĩa tables/column families.

**Không** thử xóa production cluster hoặc table để “xác minh failover”. Dùng tài nguyên lab, mô phỏng thay đổi route hoặc môi trường đã được phê duyệt fault-injection.

## 14. Quan sát, xử lý lỗi và chi phí

### 14.1. Chỉ số phải xem theo cluster và app profile

| Metrics | Câu hỏi vận hành |
| --- | --- |
| CPU average / **hottest node** | Cluster có hotspot, CPU distribution bất thường? |
| Node count và autoscaling recommendation | Có chạm max nodes khi traffic tăng không? |
| Storage utilization (%/bytes) mỗi cluster | Đủ headroom lưu/replicate dữ liệu? |
| Read/write latency p95/p99 | SLO có cải thiện khi đổi route/size không? |
| Rows read/written, read/write throughput | Tải thực sự đi về cluster nào? |
| System error rate | Có lỗi backend Bigtable hay client retries? |
| Replication latency **input/output** | Có thể đọc cũ bao lâu giữa clusters? |
| Automatic failover events | Có bất thường route giữa clusters không? |
| CPU/latency theo **app profile** | API và batch profile đang dùng bao nhiêu tài nguyên? |
| Data Boost SPU-seconds (nếu dùng) | Batch compute có chi phí/hiệu quả ra sao? |

Trong **Bigtable → System insights**, xem theo Instance, Tables, Application Profiles, Replication; với hotspot, dùng **Key Visualizer**. Storage metrics có thể trễ vì tính toán nén/compaction; đừng hiểu một thay đổi nhỏ chưa xuất hiện tức thì là mất dữ liệu.

### 14.2. Chẩn đoán thường gặp

| Triệu chứng | Khả năng nguyên nhân | Kiểm tra |
| --- | --- | --- |
| `NOT_FOUND` instance/table | Sai project/instance/table ID hoặc chưa có resource | `instances list`, table metadata, client settings |
| App bị lỗi read-modify-write | Multi-cluster profile không cho single-row transaction | Chọn `counter-single`, xem profile config |
| API trả dữ liệu cũ sau ghi | Đọc từ cluster khác trước khi replication xong | Routing, lag, same-cluster read |
| Add cluster nhưng app không auto failover | `default` vẫn single-cluster | App profile thực tế client đang dùng |
| Latency tăng khi failover | B thiếu capacity hoặc dữ liệu chưa nóng | Node headroom, autoscaling, p95/CPU |
| Lỗi resource exhausted | CPU/quota/storage hoặc hotspot | Metrics, Key Visualizer, quota và retry |
| Average CPU thấp, một số requests chậm | Row-key range quá nóng | Hottest node/Key Visualizer, schema |
| Batch scan làm API p99 tăng | Tất cả dùng cùng cluster resources | LOW priority, Data Boost hoặc cluster riêng |
| Storage không giảm ngay sau GC | Compaction/metrics có độ trễ | Xem GC policy, storage trend, không xóa bừa |
| `PERMISSION_DENIED` | Runtime SA thiếu IAM | Bigtable role đúng resource, ADC |
| Profile đổi nhưng app chưa đổi behavior | Client vẫn dùng `default` hoặc cached config | `setAppProfileId`, restart/client lifecycle |
| Chi phí tăng sau thêm cluster | Mỗi cluster có compute/storage copy | Billing theo clusters, replication/egress |

**Quy trình điều tra:** đúng project/instance → app profile thực tế → routing/cluster health → IAM/network → CPU/hottest node/storage → replication lag → row-key access pattern → cost.

### 14.3. Chi phí cần dự trù

Bigtable có các yếu tố tính phí tùy cấu hình và edition:

- **Cluster nodes** (hoặc compute capacity theo edition) theo thời gian.
- **Storage bytes** của mỗi bản sao cluster.
- **Network/data transfer**, nhất là clusters đa region và clients ở nơi xa.
- Backups/change streams, Data Boost SPUs và các tính năng nâng cao nếu dùng.
- Cloud Monitoring/Logging và workloads đọc/ghi trên Cloud Run/GKE/Dataflow.

Ước lượng minh họa: nếu instance từ 1 cluster 3 nodes mở rộng thành **2 clusters, mỗi cluster 3 nodes**, **compute provisioned tăng gấp đôi** trước khi tối ưu autoscaling; storage cũng cần thêm bản sao. Đây **không** phải dự toán hóa đơn chính xác, vì edition/pricing/time/region khác nhau. Dùng Cloud Billing Reports/Budgets/Calculator và số liệu thực.

## 15. Bài thực hành: quyết định routing cho nền tảng IoT

**Mục tiêu:** Thiết kế app profiles, tự giải thích consistency/failover và chứng minh bằng cấu hình/metrics. Ưu tiên **mô phỏng với dữ liệu/lệnh chỉ đọc** để không phát sinh phí nếu không có sandbox được cấp.

### 15.1. Phần A — Mô hình ban đầu

Giả sử hệ thống có:

- **API realtime**: cần lookup theo device ID, chấp nhận đọc trễ vài giây khi failover; SLO p95 được xác định riêng.
- **Counter hạn mức**: yêu cầu increment/conditional mutate an toàn cho một row.
- **Batch analytics**: quét dữ liệu hàng đêm, không được làm API tăng p95.
- **HA**: chịu được lỗi một zone trong cùng region; regional DR là yêu cầu tương lai.
- **Bảo mật:** Cloud Run runtime SA chỉ được đọc/ghi bảng cần thiết, reporting chỉ read.

**Nhiệm vụ:** Xác định số clusters, locations, app profiles, route policies và IAM. Dùng bảng:

| Workload | App profile | Route | Transactions | Lý do |
| --- | --- | --- | --- | --- |
| API realtime | `api-ha` | Multi / any A,B | Không | HA/nearest, eventual consistency chấp nhận |
| Counter | `counter-single` | Single A | Có | Read-modify-write an toàn khi không có concurrent write tại B |
| Batch | `batch-asia` hoặc Data Boost | Single A, LOW / read-only Data Boost | Không | Kiểm soát impact tới API |

### 15.2. Phần B — Preflight và thiết kế

1. Xác nhận gcloud project, Bigtable instance, cluster zones và hiện trạng `default` profile.
2. Nếu được cấp **lab đã cài instance**, đọc profiles hiện có bằng `gcloud bigtable app-profiles list`.
3. Vẽ data path của API và counter. Đánh dấu nơi nào có thể đọc stale khi failover.
4. Giải thích vì sao table `telemetry` tồn tại ở cả cluster A/B, không cần tạo bảng lần hai.
5. Tính sơ bộ node capacity khi A mất: B nhận thêm 60% traffic giả định, cần bao nhiêu headroom?
6. Thiết kế autoscaling min/max/CPU target **dựa trên metric giả định**, không chỉ theo số người dùng.
7. Viết change plan tạo profiles với lệnh mục 8 và chỉ apply khi owner phê duyệt.
8. Tạo bản ghi xác nhận runtime SA được IAM đúng phạm vi, client chọn `setAppProfileId` đúng.

### 15.3. Phần C — Failure scenario

- **Tình huống 1:** Ghi tại cluster A thành công, đọc ở B ngay không thấy value. **Đáp án:** replication eventual; single-cluster cho read-your-writes hoặc thiết kế chịu stale.
- **Tình huống 2:** Một team bật counter transaction trên multi-cluster profile. **Đáp án:** không được; chuyển single-cluster và không cho conflicting writes từ profile khác.
- **Tình huống 3:** Cluster A lỗi, `api-ha` tự failover nhưng `counter-single` bị lỗi. **Đáp án:** multi auto; single cần manual runbook, đánh giá lag/capacity và rủi ro transactional writes.
- **Tình huống 4:** Bốn profile đều dùng cùng cluster để scan; p99 API tăng. **Đáp án:** đo CPU/app profile rồi chọn LOW priority, Data Boost hoặc tách workloads.
- **Tình huống 5:** Mỗi cluster disk utilization đã cao, operator giảm nodes để giảm phí. **Đáp án:** cần kiểm tra storage hard limit; có thể làm writes thất bại toàn instance.

### 15.4. Kết quả nộp bài

| Bằng chứng | Tiêu chí đạt |
| --- | --- |
| Sơ đồ instances/clusters/profiles | Đúng ownership và replication |
| Routing policy từng workload | Nêu rõ auto/manual failover và consistency |
| Client configuration | Chỉ định `appProfileId` rõ ràng |
| Transaction behavior | Không gửi ReadModifyWriteRow qua multi-cluster |
| Autoscaling plan | CPU/storage targets, headroom failover |
| Metrics | Có CPU/hottest node, replication lag, p95, system errors |
| Bảo mật | IAM ít quyền nhất, không nhầm profile với access control |
| Chi phí | Mỗi cluster có compute/storage; có budget cảnh báo |
| DR | Backups/restore drill, data residency và manual/auto failover |

## 16. Câu hỏi ôn tập và đáp án định hướng

1. **Table thuộc cluster hay instance?** Thuộc **instance**; mọi cluster của instance đều chứa bản sao tables.
2. **Node khác cluster?** Node mở rộng compute trong một cluster; cluster là failure domain riêng theo zone.
3. **Thêm cluster thứ hai có tạo table mới không?** Không; Bigtable replicate toàn bộ tables.
4. **Mỗi cluster replicated có thể nhận write?** Có, tất cả là primary clusters.
5. **Multi-cluster profile cung cấp consistency gì?** Eventual giữa clusters, auto failover.
6. **Single-cluster profile có auto failover?** Không; operator cần manual failover.
7. **Read-your-writes được đảm bảo khi dùng row-affinity?** Không; chỉ tăng xác suất khi điều kiện phù hợp.
8. **Counter read-modify-write cần gì?** Single-cluster route và bật transactional writes; tránh conflicting writes trên cluster khác.
9. **App profile `default` tự chuyển multi khi thêm cluster?** Không.
10. **`--route-any` có đi cùng `--transactional-writes`?** Không.
11. **`--restrict-to=A,B` dùng để làm gì?** Chỉ cho auto routing/failover trong nhóm A và B.
12. **Priority LOW có chặn app đọc bảng nhạy cảm?** Không, IAM mới kiểm soát quyền dữ liệu.
13. **Vì sao thêm cluster không chắc tăng write throughput?** Replication tạo thêm CPU/network work cho mỗi cluster.
14. **Dùng Data Boost cho loại workload nào?** High-throughput read analytics có compute riêng; không dùng transactional writes.
15. **Bản mới nhất vừa ghi A luôn thấy ngay ở B?** Không, phải đợi replication hoàn tất.
16. **Thêm cluster khác region có rủi ro gì?** Latency, residency và network egress/chi phí tăng.
17. **Autoscaling max nodes quá nhỏ khi failover gây gì?** Receiver thiếu capacity, p95/error rate tăng.
18. **CPU average thấp nhưng hottest node cao nói lên điều gì?** Hot key range/tablet, cần xem Key Visualizer.
19. **Replication có thay backup không?** Không; xóa nhầm/schema/GC có thể lan sang mọi cluster.
20. **Java client chọn routing bằng gì?** `BigtableDataSettings.setAppProfileId(...)`.

## 17. Checklist production và tài liệu tham khảo

- [ ] Đã chọn Bigtable theo access pattern/scale, không dùng như cache hoặc SQL JOIN mặc định.
- [ ] Instance edition/SSD-HDD/location/CMEK được duyệt, có budget.
- [ ] Clusters đủ failure domains và capacity cho toàn bộ bảng/replication.
- [ ] App profiles theo workload; `default` không bị thay tùy tiện.
- [ ] Read/write yêu cầu consistency chọn single-cluster nếu cần.
- [ ] Multi-cluster auto failover đã test và chấp nhận eventual consistency.
- [ ] Single-row transactions chỉ bật trên single-cluster profiles, không có conflicting writers.
- [ ] Row affinity không bị dùng như bảo đảm strong consistency.
- [ ] Clients có `setAppProfileId`; không lẫn cluster ID với instance ID.
- [ ] Batch workload có priority/compute isolation hợp lý; Data Boost chỉ khi phù hợp.
- [ ] Autoscaling min/max CPU/storage target và failover headroom đã load test.
- [ ] CPU/hottest node, storage, p95/p99, replication latency và app profile usage được alert.
- [ ] IAM/runtime identities tối thiểu, encryption/audit và data residency được kiểm tra.
- [ ] Có backup/restore drill và runbook failover/failback.
- [ ] Chi phí multi-cluster/node/storage/network/backup/Data Boost được theo dõi.
- [ ] Không xóa instance/cluster/table chỉ vì kết thúc thử nghiệm nếu đang dùng chung.

**Tài liệu Google Cloud chính thức:**

- [Bigtable overview](https://docs.cloud.google.com/bigtable/docs/overview) — workload, consistency và bảo vệ dữ liệu.
- [Instances, clusters and nodes](https://docs.cloud.google.com/bigtable/docs/instances-clusters-nodes) — phân cấp instance/cluster/node, SSD/HDD.
- [Create an instance](https://docs.cloud.google.com/bigtable/docs/creating-instance) — instance, cluster, location/edition.
- [Modify an instance](https://docs.cloud.google.com/bigtable/docs/modifying-instance) — thêm cluster, chỉnh nodes/autoscaling.
- [Application profiles](https://docs.cloud.google.com/bigtable/docs/app-profiles) — default/custom, Standard, Data Boost.
- [Create and configure app profiles](https://docs.cloud.google.com/bigtable/docs/configuring-app-profiles) — routing, flags và priority.
- [Routing options](https://docs.cloud.google.com/bigtable/docs/routing) — single/multi/group/row-affinity, transactions.
- [Replication overview](https://docs.cloud.google.com/bigtable/docs/replication-overview) — eventual consistency, conflict resolution.
- [Replication configurations](https://docs.cloud.google.com/bigtable/docs/replication-settings) — HA, workload separation.
- [Managing failovers](https://docs.cloud.google.com/bigtable/docs/managing-failovers) — manual vs automatic.
- [Autoscaling](https://docs.cloud.google.com/bigtable/docs/autoscaling) — node targets và capacity.
- [Bigtable monitoring](https://docs.cloud.google.com/bigtable/docs/monitoring-instance) — cluster/app profile/replication metrics.
- [Data Boost overview](https://docs.cloud.google.com/bigtable/docs/data-boost-overview) — serverless compute cho analytics.
- [Bigtable client libraries](https://docs.cloud.google.com/bigtable/docs/reference/libraries) — ADC/Java BigtableDataClient.
- [gcloud app profiles create](https://docs.cloud.google.com/sdk/gcloud/reference/bigtable/app-profiles/create) — `--route-any`, `--route-to`.
- [gcloud instance create](https://docs.cloud.google.com/sdk/gcloud/reference/bigtable/instances/create) — `--cluster-config`.
- [Bigtable IAM roles](https://docs.cloud.google.com/iam/docs/roles-permissions/bigtable) — Reader/User/Admin.
- [Bigtable pricing](https://cloud.google.com/bigtable/pricing) — editions, nodes, storage và Data Boost.

**Ghi nhớ:** **Instance sở hữu dữ liệu; cluster cung cấp compute và bản sao theo zone; app profile quyết định route của request.** Một profile multi-cluster cải thiện availability nhưng cần chấp nhận eventual consistency; single-cluster giữ read-your-writes và hỗ trợ single-row transactions nhưng cần manual failover. Kết hợp profile, autoscaling, capacity headroom, IAM và backup để đạt độ tin cậy mà không mất kiểm soát chi phí.
