# Replication, consistency và định tuyến truy cập Bigtable

Một hệ thống bán lẻ thu thập lượt xem sản phẩm từ **Cloud Run** và sự kiện thiết bị từ **GKE**, lưu dữ liệu dạng chuỗi thời gian vào **Bigtable**. Khách hàng ở hai khu vực muốn đọc dữ liệu gần nơi mình truy cập, nhưng đội vận hành cũng cần trả lời: *nếu ghi một sự kiện ở cluster A rồi đọc ở cluster B ngay lập tức, có chắc thấy dữ liệu mới không? Nếu cluster A ngừng phục vụ, ứng dụng chuyển sang cluster nào và mất khả năng nhất quán gì?*

**Replication** tăng khả năng sẵn sàng và đưa bản sao dữ liệu gần ứng dụng hơn, nhưng không tự tạo giao dịch toàn cục như **Spanner**. Trong Bigtable, lựa chọn **application profile (app profile)** quyết định yêu cầu được định tuyến đến cluster nào, qua đó ảnh hưởng trực tiếp tới **consistency, failover, độ trễ và chi phí**.

Bài học thuộc chương **Bigtable và Memorystore**, mô-đun **CLOUD_PROVIDERS_GCP**. Nội dung tập trung vào **replication, consistency và định tuyến truy cập Bigtable**, kết nối với IAM, VPC, Compute Engine, GKE, Cloud Run, giám sát độ tin cậy và chi phí. *Memorystore là dịch vụ cache/in-memory riêng; không đóng vai trò đồng bộ hoặc đảm bảo consistency cho dữ liệu Bigtable.*

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả replication giữa các **clusters của cùng Bigtable instance** và lý do bản sao có thể chậm hơn nguồn.
2. Phân biệt **eventual consistency**, **read-your-writes** và trường hợp có thể đạt **strong consistency**.
3. Chọn app profile **single-cluster**, **multi-cluster/any-cluster**, **cluster group** hoặc **row-affinity**.
4. Giải thích vì sao **single-row transactions** cần routing riêng và không dùng cùng multi-cluster routing.
5. Thiết lập app profiles, kiểm tra cấu hình, lập kế hoạch failover thủ công/tự động bằng `gcloud`.
6. Theo dõi **replication latency, max delay, CPU, lỗi và automatic failovers**, đánh giá RPO/RTO theo mục tiêu hệ thống.
7. Thiết kế test và runbook cho ứng dụng đa vùng, tránh ghi xung đột và chi phí bất ngờ.

## 2. Bigtable replication hoạt động thế nào?

### 2.1. Instance, cluster, table và bản sao

**Bigtable instance** có một hoặc nhiều **clusters** nằm ở các zone/region được hỗ trợ. Các clusters trong một replicated instance chứa **bản sao của cùng các bảng**, nhưng mỗi cluster có tài nguyên phục vụ riêng. Tất cả clusters đều có thể phục vụ **đọc và ghi**; không mặc định có một primary duy nhất như một số cơ sở dữ liệu quan hệ.

~~~mermaid
flowchart LR
    A["Cloud Run / GKE khu vực A"] --> P["App profile"]
    P --> CA["Cluster A"]
    P --> CB["Cluster B"]
    CA <-->|"Replication bất đồng bộ"| CB
    CA --> DA["Bản sao các bảng"]
    CB --> DB["Bản sao các bảng"]
~~~

Một thao tác ghi được phục vụ bởi cluster đã chọn và sau đó được lan truyền tới các clusters khác. **Không có cam kết rằng mọi cluster đều nhận bản ghi ngay thời điểm write ở cluster đầu trả thành công**. Replication có thể chậm do khoảng cách mạng, tải ghi, CPU hoặc vấn đề tạm thời của từng cluster.

| Tính chất | Hệ quả thiết kế |
| --- | --- |
| Mỗi cluster có bản sao dữ liệu. | Dung lượng/chi phí của replicated instance tăng theo số clusters và vùng. |
| Mỗi cluster phục vụ request. | Có thể giảm độ trễ đọc khi client ở gần cluster. |
| Replication bất đồng bộ. | Đọc ở cluster khác ngay sau ghi có thể trả dữ liệu cũ. |
| Cluster nhận cả đọc và ghi. | Cần kiểm soát conflicting writes, đặc biệt với giao dịch một hàng. |
| App profile quyết định routing. | Cùng database nhưng hai ứng dụng dùng profiles khác nhau có semantics khác nhau. |

**Replication không phải backup bất biến.** Xóa dữ liệu nhầm hoặc ghi sai có thể được replicate sang các clusters. Nếu cần khôi phục từ sai sót, sử dụng **Bigtable backups** theo chính sách riêng; backup ở một cluster cũng có thể chưa chứa write từ cluster khác còn đang chờ đồng bộ.

### 2.2. Replication có tăng throughput không?

Đọc có thể được phân tán giữa các clusters, giúp giảm latency và tăng read capacity cho từng khu vực. Tuy nhiên **thêm cluster không mặc nhiên tăng write throughput**: mỗi cluster còn phải nhận và áp các writes được replicate, tiêu thụ CPU, lưu trữ và mạng. Khi lập capacity plan, tính cả **tải replication nền**, không chỉ QPS do client gửi trực tiếp. Xem [Replication and performance](https://cloud.google.com/bigtable/docs/replication-performance).

## 3. Ba mức consistency cần phân biệt

### 3.1. Eventual consistency

Nếu ứng dụng gửi write tới cluster A và read tới B trước khi replication bắt kịp, B có thể trả phiên bản cũ. Khi replication hoàn tất và không còn writes xung đột, các bản sao tiến tới cùng trạng thái.

~~~text
09:00:00.000  Write row k, status=READY tới cluster A → thành công
09:00:00.010  Read row k qua cluster B → có thể vẫn thấy status=PENDING
09:00:00.xxx  Replication hoàn tất
09:00:00.yyy  Read qua B → thấy READY
~~~

Thời điểm và độ trễ trên chỉ là minh họa; **không có SLA cố định vài mili giây cho mọi write hoặc mọi đường mạng**. Với dashboards, clickstream, IoT telemetry hay phân tích cho phép dữ liệu chậm, eventual consistency thường chấp nhận được.

### 3.2. Read-your-writes

Ứng dụng cần đọc được write vừa thực hiện có thể dùng **single-cluster routing** và bảo đảm **mọi writes/reads liên quan của workload cùng đi tới một cluster**. Lưu ý:

- Đây là bảo đảm đối với đường truy cập được định tuyến nhất quán; **một profile khác đọc từ cluster khác vẫn có thể stale**.
- Nếu hệ thống chuyển cluster khi failover, dữ liệu chưa replicate sẽ có thể chưa xuất hiện tại đích.
- Nếu muốn các ứng dụng **cùng nhìn một trạng thái mạnh nhất quán**, tất cả workload liên quan phải đọc/ghi qua **cùng một cluster** và không sử dụng clusters khác để phục vụ operations độc lập.

### 3.3. Strong consistency có điều kiện

Theo tài liệu Bigtable, để có **strong consistency trên replicated instance** cho một tập workload, dùng single-cluster routing cho tất cả app profiles tham gia và **chỉ phục vụ đọc/ghi từ một cluster chung**. Các clusters còn lại có thể làm standby cho failover hoặc những tác vụ có yêu cầu khác, nhưng nếu chúng cũng phục vụ reads/writes trực tiếp thì không thể suy ra strong consistency toàn hệ thống.

**Failover phá giả định này trong một khoảng thời gian:** khi chuyển sang cluster khác còn lag, ứng dụng có thể đọc stale cho tới khi replication bắt kịp. Vì vậy **HA và strong consistency xuyên failover không phải hai bảo đảm tự động có cùng lúc**. <https://cloud.google.com/bigtable/docs/replication-overview>

| Yêu cầu nghiệp vụ | Thiết kế đề xuất | Giới hạn |
| --- | --- | --- |
| Phân tích/sự kiện telemetry, stale chấp nhận được. | Multi-cluster routing, các clusters gần client. | Eventual consistency. |
| Một ứng dụng phải đọc đúng write vừa gửi. | Single-cluster routing, đọc/ghi cùng cluster. | Cần failover thủ công và chấp nhận thay đổi semantics khi failover. |
| Các ứng dụng phải thấy cùng trạng thái hiện tại. | Tất cả app profiles cùng cluster đang phục vụ. | Không cho ứng dụng khác ghi sang cluster thứ hai. |
| Vừa HA tự động vừa cố gắng giảm stale reads một hàng. | Multi-cluster + row-affinity. | **Cải thiện xác suất**, không bảo đảm read-your-writes tuyệt đối. |

## 4. Ghi xung đột, atomicity và giao dịch một hàng

### 4.1. Đơn vị nhất quán của Bigtable

Một **mutation trên một row** là atomic, kể cả sửa nhiều cells của row đó trong cùng operation. Bigtable **không cung cấp transaction ACID cập nhật nhiều rows một cách atomic** như Spanner. Các nghiệp vụ yêu cầu transaction đa bảng/đa hàng hoặc uniqueness toàn cục nên được thiết kế trên dịch vụ dữ liệu phù hợp.

Các operations như **read-modify-write** (increment/append) và **check-and-mutate** là dạng **single-row transactions**. Chúng có thể gây kết quả sai khi hai clusters độc lập cùng thay đổi một row/cell rồi mới đồng bộ.

### 4.2. Vì sao multi-cluster không cho phép transactional writes?

Giả sử row `ticket#123` đang có `sold=5` ở hai clusters:

~~~text
Cluster A: increment sold → 6
Cluster B: increment sold → 6   (chưa nhận write từ A)
Replication sau đó không thể suy ra phải là 7.
~~~

Để tránh xung đột kiểu này, Bigtable **chỉ cho phép bật single-row transactional writes trên app profile dùng single-cluster routing**. Có thể có nhiều profiles đơn-cluster, nhưng **không bật transactional writes cho nhiều profiles trỏ tới các clusters khác nhau nếu chúng có thể cập nhật xung đột cùng row**. Muốn đếm sự kiện cộng dồn, tìm hiểu **aggregate cells** khi phù hợp hoặc dùng một đường ghi duy nhất.

### 4.3. Conflict resolution không phải “write mới nhất trên đồng hồ client”

Một cell version trong Bigtable được xác định bởi bộ `(row key, column family, column qualifier, timestamp)`. Nếu **hai writes có cùng bộ bốn này** đến các clusters khác nhau, Bigtable dùng cơ chế **last-write-wins nội bộ dựa trên thời gian server** để giải quyết xung đột nhất quán sau replication. Điều đó **không phải** một transaction merge theo ý định nghiệp vụ, không chắc chọn write mà ứng dụng coi là “sự kiện mới hơn”. Nếu timestamps khác nhau, các versions có thể cùng tồn tại theo chính sách lưu/GC thay vì đơn giản ghi đè một giá trị. Xem [Writes and conflict resolution](https://cloud.google.com/bigtable/docs/writes).

Đối với một row có nhiều mutations đồng thời:

- Tránh để hai regions độc lập cùng quyết định thay đổi một trạng thái quan trọng.
- Chọn một **writer ownership** theo row key/tenant khi cần; thiết kế event ID, version hoặc idempotency.
- Không dựa vào đồng hồ của nhiều client khác nhau để giải quyết mọi xung đột nghiệp vụ.
- Nếu hệ thống yêu cầu transaction đa hàng hoặc invariants chặt, cân nhắc **Spanner/Cloud SQL**; Bigtable phù hợp truy cập key/row và throughput cao hơn là thay thế hệ thống giao dịch quan hệ.

## 5. App profiles và bốn kiểu định tuyến truy cập

**App profile** là cấu hình của một loại ứng dụng/workload trên Bigtable instance. Client chọn **app profile ID** khi kết nối; Bigtable áp **routing policy** và các tùy chọn phù hợp. Không cần tạo một instance khác chỉ để cho workload analytics dùng routing khác với workload online.

| Routing policy | Cách hoạt động | Consistency và failover |
| --- | --- | --- |
| **Single-cluster** | Gửi mọi request của profile tới một cluster chỉ định. | Read-your-writes khi reads/writes cùng cluster; **failover thủ công**. Có thể bật single-row transactions. |
| **Multi-cluster: any** | Định tuyến tới cluster gần/khả dụng theo cơ chế Bigtable. | **Failover tự động**, eventual consistency; không bật single-row transactions. |
| **Multi-cluster: cluster group** | Chỉ cho phép một tập clusters được chọn tham gia routing/failover. | Tương tự multi-cluster nhưng không tự gửi tới cluster nằm ngoài tập. |
| **Multi-cluster: row-affinity** | Gán các request **đúng một row key** tới một cluster nhất quán hơn. | Cải thiện read-your-writes trong điều kiện bình thường nhưng **không bảo đảm** khi failover, overload hoặc đổi cluster topology. |

### 5.1. Row-affinity không phải sticky session

Row-affinity dựa trên **row key**, không dựa trên một phiên HTTP của người dùng, IP client hay vị trí region cố định. Nó phù hợp các API chủ yếu gọi **single-row reads/mutations**, nhưng:

- Không áp dụng cho **row-range scan** hoặc nhiều rows trong một request.
- **Không có hiệu lực với Bigtable SQL `ExecuteQuery`**, kể cả SQL lọc chỉ một row.
- Routing có thể đổi khi failover, network lỗi, cluster quá tải hoặc danh sách clusters thay đổi.
- Dùng **cluster group** có thể tránh việc thêm một cluster mới làm thay đổi phép gán row keys ngoài dự tính.

Do đó không thiết kế thanh toán/tồn kho yêu cầu nhất quán tuyệt đối chỉ dựa trên row-affinity. Đọc [Routing options](https://cloud.google.com/bigtable/docs/routing).

### 5.2. Đừng mặc định tin app profile `default`

App profile `default` được tạo tự động nhưng routing mặc định phụ thuộc **số clusters khi instance được tạo**:

- Instance **ban đầu có một cluster**: profile `default` thường dùng **single-cluster** và cho phép single-row transactions.
- Instance **ban đầu có từ hai clusters**: profile `default` dùng **multi-cluster** và không cho phép single-row transactions.
- **Thêm cluster sau này không tự đổi routing của `default`**.

Để tránh thay đổi hành vi không mong muốn, nên tạo **app profile đặt tên theo workload** (`orders-consistent`, `telemetry-ha`, `analytics-low-priority`) thay vì dựa mãi vào `default`. Profile riêng cũng giúp theo dõi CPU/latency theo workload.

## 6. Chọn topology theo mục tiêu availability và consistency

### 6.1. Active–passive: ưu tiên tính nhất quán

~~~mermaid
flowchart LR
    APP["Ứng dụng giao dịch"] --> PROFILE["Single-cluster app profile"]
    PROFILE --> A["Cluster A: phục vụ"]
    A <-->|"Replication"| B["Cluster B: standby"]
    PROFILE -. "Đổi route-to khi cần" .-> B
~~~

Mọi requests cần consistency đi tới **A**, B nhận bản sao để dự phòng. Nếu A bị sự cố, vận hành chủ động chuyển app profile sang B sau khi đánh giá **replication lag và nguy cơ đọc dữ liệu cũ**. Chế độ này cho phép thiết kế single-row transactions qua cluster chủ, nhưng không tạo ra zero-RPO tự động.

### 6.2. Active–active: ưu tiên khả dụng và latency

~~~mermaid
flowchart LR
    APP_A["Ứng dụng khu vực A"] --> PA["HA app profile"]
    APP_B["Ứng dụng khu vực B"] --> PA
    PA --> A["Cluster A"]
    PA --> B["Cluster B"]
    A <-->|"Replication"| B
~~~

Multi-cluster routing hướng ứng dụng tới cluster phù hợp và **tự chuyển sang cluster khác** khi một cluster không phục vụ được. Đây là lựa chọn tốt cho event data/read-heavy workloads chấp nhận eventual consistency. Nếu **region chứa ứng dụng** cũng gặp outage, chỉ có thêm cluster Bigtable ở region khác **chưa đủ**: cần triển khai application/client ở ít nhất một vị trí khác và có cơ chế điều hướng traffic, health checks, quotas và IAM tương ứng.

### 6.3. Bảng chọn nhanh

| Nhu cầu | Cấu hình nên khảo sát đầu tiên | Điều đánh đổi |
| --- | --- | --- |
| API luôn đọc lại giá trị vừa ghi, một nguồn sự thật. | Single-cluster, thống nhất cluster cho mọi app profiles liên quan. | Manual failover và latency cho client ở xa. |
| Telemetry trên nhiều khu vực, stale vài giây chấp nhận được. | Multi-cluster any. | Eventual consistency, chi phí nhân bản. |
| Muốn dự phòng nhưng không muốn failover ngoài kiểm soát. | Single-cluster + standby replication. | Cần runbook, giám sát và quyết định thời điểm chuyển. |
| Analytics workload không được chiếm CPU của online cluster. | Multi-cluster cluster-group hoặc single-cluster chuyên dụng. | Kiểm soát load, vùng, giá và không tự đảm bảo consistency. |
| Mostly one-row operations, muốn ít stale hơn với HA tự động. | Multi-cluster + row-affinity. | Không bảo đảm read-your-writes khi routing thay đổi. |
| Bộ đếm chính xác toàn cục với cập nhật đồng thời đa vùng. | Thiết kế writer duy nhất hoặc DB transactional phù hợp. | Không dùng multi-cluster Bigtable RMW cho cùng cell. |

## 7. Thực hành `gcloud`: tạo và kiểm tra app profiles

Lệnh ví dụ dùng **Bash**, giả định instance đã có **hai clusters tồn tại**. Thay IDs bằng tài nguyên của project lab. Lệnh `create/update` **ghi cấu hình và có thể ảnh hưởng traffic**; không chạy trên production khi chưa có change approval. App profiles **không tự tạo replication**: muốn có nhiều clusters phải cấu hình clusters của instance riêng, theo tài liệu chính thức.

### 7.1. Preflight chỉ đọc

~~~bash
PROJECT_ID="retail-lab"
INSTANCE="events-bt"
CLUSTER_A="events-a"
CLUSTER_B="events-b"

# READ-ONLY: xác nhận principal và project.
gcloud auth list
gcloud config get-value project

# READ-ONLY: xác minh instance, clusters và app profiles.
gcloud bigtable instances describe "$INSTANCE" --project="$PROJECT_ID"
gcloud bigtable clusters list --instances="$INSTANCE" --project="$PROJECT_ID"
gcloud bigtable app-profiles list --instance="$INSTANCE" --project="$PROJECT_ID"
~~~

Kiểm tra zone/region của từng cluster, CPU/capacity, độ trễ giữa các vị trí và profiles đang có. Không đoán cluster ID chỉ từ vùng, vì cluster là tài nguyên có ID riêng do người quản trị tạo.

### 7.2. Tạo profile cho từng tình huống

~~~bash
# WRITE: đơn-cluster cho workload yêu cầu read-your-writes.
gcloud bigtable app-profiles create orders-consistent \
  --instance="$INSTANCE" --project="$PROJECT_ID" \
  --route-to="$CLUSTER_A" \
  --description="Read/write on cluster A"

# WRITE: HA tự động, có thể định tuyến vào mọi cluster của instance.
gcloud bigtable app-profiles create telemetry-ha \
  --instance="$INSTANCE" --project="$PROJECT_ID" \
  --route-any \
  --description="Automatic failover; eventual consistency"

# WRITE: chỉ chọn A/B, hỗ trợ row-affinity cho single-row operations.
gcloud bigtable app-profiles create telemetry-sticky \
  --instance="$INSTANCE" --project="$PROJECT_ID" \
  --route-any \
  --restrict-to="$CLUSTER_A,$CLUSTER_B" \
  --row-affinity \
  --description="Single-row routing with affinity"

# READ-ONLY: xác minh routing policy thực tế.
gcloud bigtable app-profiles describe telemetry-sticky \
  --instance="$INSTANCE" --project="$PROJECT_ID"
~~~

**Cấu hình transactional writes** chỉ dành cho profile single-cluster khi nghiệp vụ cần `ReadModifyWriteRow` hoặc `CheckAndMutateRow`, ví dụ tạo thêm profile chỉ định `--route-to="$CLUSTER_A" --transactional-writes`. Không ghép `--transactional-writes` với `--route-any` hoặc `--row-affinity`; kiểm tra các profiles khác có ghi cùng row ở cluster B không. Cấu hình `orders-consistent` ở ví dụ **chưa bật** transactional writes.

### 7.3. Java client chỉ định app profile

Ví dụ dùng `com.google.cloud:google-cloud-bigtable` với **Application Default Credentials (ADC)**, không nhúng JSON key. Code đọc một row theo Bigtable Java API:

~~~java
import com.google.cloud.bigtable.data.v2.BigtableDataClient;
import com.google.cloud.bigtable.data.v2.BigtableDataSettings;
import com.google.cloud.bigtable.data.v2.models.Row;

public class ReadEvent {
    public static void main(String[] args) throws Exception {
        BigtableDataSettings settings = BigtableDataSettings.newBuilder()
                .setProjectId("retail-lab")
                .setInstanceId("events-bt")
                .setAppProfileId("telemetry-ha")
                .build();

        try (BigtableDataClient client = BigtableDataClient.create(settings)) {
            Row row = client.readRow("events", "device#001#20261119");
            System.out.println(row == null ? "Not found" : "Found");
        }
    }
}
~~~

Ví dụ giả định bảng/row có thật và identity có quyền đọc. Với **Cloud Run/GKE production**, tạo **một BigtableDataClient dùng chung theo vòng đời process** thay vì tạo trong mỗi HTTP request; `close()` lúc shutdown, đặt deadlines/retries phù hợp. Nếu đổi từ `telemetry-ha` sang `orders-consistent`, hành vi routing/consistency thay đổi **dù SQL/row key không đổi**.

## 8. Failover và failback có kiểm soát

### 8.1. Tự động hay thủ công?

- **Multi-cluster routing:** Bigtable có thể tự đổi cluster khi cluster gần nhất không phục vụ được. Tốc độ failover phụ thuộc **request deadline** và tình trạng cluster; không bảo đảm mọi request đều không lỗi.
- **Single-cluster routing:** **không tự chuyển cluster**; người vận hành phải thay `route-to` khi quyết định failover.
- Cả hai có thể dẫn tới **reads cũ** sau chuyển cluster nếu replication chưa bắt kịp. Nếu nguồn tiếp tục nhận writes trong lúc split/failover, phải quản lý xung đột dữ liệu cẩn thận.

### 8.2. Runbook failover thủ công

1. **Đánh giá sự cố:** so sánh 5xx/timeouts, latency, CPU/hottest node, network và tình trạng cluster A. Không mặc định mọi p99 tăng đều phải chuyển cluster.
2. **Đánh giá dữ liệu:** đọc replication latency/max delay và nguy cơ stale ở cluster B; xác định nghiệp vụ có chấp nhận RPO tạm thời hay không.
3. **Kiểm tra capacity đích:** cluster B phải chịu được cả traffic chuyển đến và replication nền.
4. **Quyết định writes:** với transactional/conditional mutations, ngừng hoặc quản lý chặt đường ghi ở A, tránh viết xung đột trên hai clusters.
5. **Chuyển profile trong change window:**

   ~~~bash
   # WRITE: CHỈ chạy khi đã phê duyệt failover và xác nhận cluster B khỏe.
   gcloud bigtable app-profiles update orders-consistent \
     --instance="$INSTANCE" --project="$PROJECT_ID" \
     --route-to="$CLUSTER_B"
   ~~~

6. **Xác minh:** kiểm tra app profile, application success rate, p95/p99, lỗi, tính mới của dữ liệu, automatic failovers (nếu dùng profiles khác), latency và cost.
7. **Failback có kế hoạch:** khi A phục hồi, đánh giá replication đã bắt kịp, cân nhắc consistency token/canary, sau đó mới đổi profile về A; không ping-pong routing liên tục.

`--force` có thể bỏ qua một số cảnh báo nguy hiểm của CLI; **không thêm mặc định**. Đối với multi-cluster, failover tự động không phải lý do để tắt monitoring. Đọc [Manage failovers](https://cloud.google.com/bigtable/docs/managing-failovers).

## 9. Kiểm chứng replication đã bắt kịp

### 9.1. Dùng consistency token khi cần bảo đảm theo mốc

Nếu một batch writes phải được replicate sang mọi cluster trước khi downstream analytics/bản backup thực hiện:

1. Gửi và xác nhận batch writes vào Bigtable.
2. **GenerateConsistencyToken** cho **table** sau batch.
3. Gọi **CheckConsistency** với token và chế độ thích hợp (ví dụ `StandardReadRemoteWrites`).
4. Nếu kết quả `consistent=false`, chờ/retry có timeout và backoff; chỉ tiếp tục sau khi đạt điều kiện hoặc fail với thông báo rõ.

Token kiểm tra rằng **những writes hoàn tất trước lúc tạo token** đã đạt điều kiện replicate, **không khẳng định các writes gửi sau đó đều nhất quán**. Lần kiểm tra đầu có thể cần thời gian để xác nhận trên mọi cluster. Đây là **cơ chế barrier theo batch/bảng**, không nên sinh/poll một token mới cho **mọi HTTP request** chỉ để thay read-your-writes routing. Xem [GenerateConsistencyToken](https://cloud.google.com/bigtable/docs/reference/admin/rest/v2/projects.instances.tables/generateConsistencyToken) và [CheckConsistency](https://cloud.google.com/bigtable/docs/reference/admin/rest/v2/projects.instances.tables/checkConsistency).

### 9.2. Replication và backup

Backup của bảng trong một cluster phản ánh dữ liệu cluster đó khi snapshot được tạo, có thể **chưa gồm những writes từ cluster khác chưa kịp replicate**. Nếu cần backup nhất quán theo batch writes quan trọng, dùng consistency token/điều kiện được tài liệu Bigtable hỗ trợ và diễn tập restore. Replication **không thay thế backup khi xóa nhầm bảng, lỗi ứng dụng hay cấu hình garbage collection sai**. Xem [Bigtable backups](https://cloud.google.com/bigtable/docs/backups).

## 10. Monitoring: đo consistency, latency và failover

### 10.1. Tín hiệu cần xem cùng nhau

| Tín hiệu trong Bigtable/Cloud Monitoring | Cho biết gì? | Khi nào quan tâm? |
| --- | --- | --- |
| `bigtable.googleapis.com/table/replication/latency` | Phân phối **độ trễ replication** giữa nguồn và đích, tính bằng ms. | p50/p95/p99 tăng, đặc biệt trước failover hoặc backup. |
| `bigtable.googleapis.com/table/replication/max_delay` | **Upper bound** về độ trễ replicate theo metric được cung cấp, tính bằng giây. | Xem cửa sổ mà thông tin consistency/latency có thể chưa đầy đủ. |
| Read/write latency theo cluster/app profile | Độ trễ phục vụ request ở tầng Bigtable. | Phát hiện region xa, scan nặng, load imbalance. |
| CPU utilization, **hottest node CPU** | Capacity và hotspot của cluster/tablet. | Một số row-key ranges quá nóng dù CPU trung bình thấp. |
| Automatic failovers | Số request được Bigtable tự chuyển cluster. | Hiểu biến động routing và p99 trên multi-cluster. |
| System error rate, timeouts, request counts | Dịch vụ có xử lý ổn định không. | Cần chẩn đoán lỗi mạng/capacity trước khi đổi app profile. |
| Client-side p95/p99, retries, Google Cloud audit logs | Trải nghiệm người dùng và ai thay routing. | Điều tra incident, cấu hình sai hoặc rollout. |

**Chú ý phân biệt:** `replication/latency` là **độ trễ của các mutations được đo khi replicate**, không phải cam kết “mọi row trong bảng có độ cũ tối đa bằng p95”. `replication/max_delay` cũng không là SLA RPO bằng con số cố định cho mọi thời điểm. Monitoring metrics có sampling/độ trễ hiển thị; xem cửa sổ thời gian đủ dài. Tài liệu: [Bigtable metrics](https://cloud.google.com/bigtable/docs/metrics), [Monitor Bigtable](https://cloud.google.com/bigtable/docs/monitoring-instance).

### 10.2. Alert theo SLO, không theo một ngưỡng cho mọi bảng

Một ví dụ chính sách giả định cho ứng dụng telemetry:

~~~text
SLO: 99,9% reads thành công, p99 < 200 ms.
Consistency budget của báo cáo: chấp nhận stale tối đa 30 giây.

Warning:
  replication p99 tăng nhiều phút, read p99 vượt mục tiêu.
Incident:
  replication delay tiếp tục tăng + lỗi client tăng/cluster bất ổn.
Failover readiness:
  đo replication lag, CPU headroom, capacity và vị trí client.
~~~

Giá trị trên chỉ minh họa, **không phải giới hạn hay SLA Bigtable**. Đối với order state hoặc counters cần chính xác ngay, tránh đặt “30 giây là được” nếu chưa có quyết định nghiệp vụ. SLO đọc/ghi phải được đo cùng **ứng dụng**, vì client ở region bị outage cũng có thể không gọi được Bigtable dù cluster khác khỏe.

## 11. Tải, IAM, mạng và chi phí

### 11.1. Phân bổ năng lực từng cluster

Khi Bigtable có nhiều clusters:

- Mỗi cluster có **storage bản sao**, node/compute capacity và CPU dành cho **replication nền**.
- **Write throughput không được nhân theo số clusters**; dữ liệu ghi ở một cluster cũng phải được replicate sang những clusters khác.
- Khi failover, cluster đích nhận thêm **client traffic**, trong khi replication và hệ thống vẫn tiêu thụ tài nguyên.
- Multi-region routing có thể giảm latency gần khách, nhưng có **inter-region replication/network transfer charges** tùy đường dữ liệu và bảng giá; lần thêm cluster mới còn có chi phí copy dữ liệu ban đầu.
- **Drop row ranges** trên instance có replication có thể chậm và tốn CPU đáng kể; không dùng để xóa hàng loạt sát giờ cao điểm.

Nếu một cluster đang gần hết headroom trước sự cố, HA trên giấy có thể không đáp ứng SLO sau failover. Load-test cả **N-1 capacity** (mất một cluster), theo dõi node count, storage và autoscaling behavior theo edition/thiết lập hiện hành.

### 11.2. Tách danh tính và quyền

| Principal | Cần làm | Nguyên tắc |
| --- | --- | --- |
| Cloud Run runtime SA | Đọc/ghi rows qua app profile. | `roles/bigtable.user` hoặc quyền dữ liệu tối thiểu ở scope phù hợp; không cấp Admin mặc định. |
| GKE workload SA | Xử lý events Bigtable. | Workload Identity Federation for GKE và quyền Data API theo workload. |
| SRE/DBA | Tạo/chỉnh app profiles, clusters, failover. | Phân quyền quản trị riêng, phê duyệt và audit; **không trao quyền đổi route** cho mọi app runtime. |
| CI/deployer | Quản lý cấu hình theo IaC/release. | Quyền deploy/`iam.serviceAccounts.actAs` khi cần, tách với quyền đọc dữ liệu nhạy cảm. |
| Auditor | Xem cấu hình/metrics. | Monitoring/Bigtable Viewer theo tài nguyên. |

**App profile là cơ chế routing, không phải hàng rào phân quyền dữ liệu**. IAM/authorized views và kiểm soát quyền ứng dụng vẫn cần được thiết kế riêng. Với private workloads, kiểm tra **đường đến Google APIs**, DNS, Private Google Access/PSC và VPC Service Controls theo topology; Bigtable không phải PostgreSQL server mà ứng dụng kết nối qua một private DB IP đơn lẻ.

### 11.3. Chi phí nên tính theo kiến trúc hoàn chỉnh

~~~text
Chi phí ước lượng ≈
  compute/nodes của từng Bigtable cluster
  + storage bản sao ở từng cluster
  + network transfer/replication theo khu vực và lưu lượng
  + backup và bản sao khởi tạo khi thêm cluster
  + Cloud Run/GKE client compute + logging/monitoring
~~~

Không gộp tất cả thành “Bigtable nhân đôi phí” chỉ vì có hai clusters: compute, storage, transfer, lưu trữ bổ sung và vị trí vùng có đơn giá/phạm vi riêng. Tính **chi phí trên mỗi triệu sự kiện được xử lý đúng SLO**, kiểm tra [Bigtable pricing](https://cloud.google.com/bigtable/pricing).

## 12. Case study: đọc/ghi đa vùng và kịch bản failover

### 12.1. Bối cảnh

- `events-bt`: Bigtable instance có cluster A và B ở hai regions khác nhau.
- Cloud Run ở A phát `product.viewed`; GKE ở B tổng hợp clickstream.
- Website cần xem telemetry gần realtime; ứng dụng quản lý khuyến mãi có một **bộ đếm trạng thái quan trọng**.
- SLO telemetry cho phép eventual consistency, còn bộ đếm nghiệp vụ không chấp nhận mất increments.

**Thiết kế:**

| Luồng | App profile | Giải thích |
| --- | --- | --- |
| `product.viewed` ingestion và dashboard | `telemetry-ha`: multi-cluster any | HA tự động, latency thấp hơn theo khu vực, stale đọc có thể chấp nhận. |
| Lookup một row telemetry vừa ghi | `telemetry-sticky`: multi-cluster row-affinity | Giảm khả năng đọc stale, nhưng vẫn xử lý trường hợp stale khi failover. |
| Counter khuyến mãi cần single-row read-modify-write | `orders-consistent`: single-cluster A, bật transactions nếu cần | Không phân tán conditional mutations vào hai clusters. |
| Báo cáo chỉ chạy ở B | Profile riêng single-cluster B hoặc cluster group phù hợp | Tách tải/quan sát, chấp nhận dữ liệu chưa replicate đầy đủ theo SLA nội bộ. |

**Cảnh báo:** nếu counter yêu cầu giao dịch nhiều rows hoặc cập nhật đồng thời chính xác ở cả A và B, cân nhắc Spanner/Cloud SQL hoặc một thiết kế aggregate/writer-ownership phù hợp; không dựa vào replication để tự merge số gia.

### 12.2. Một sự cố giả định

Khi region A có lỗi:

1. `telemetry-ha` tự chuyển traffic tới B; một số reads có thể tạm thấy dữ liệu cũ.
2. `orders-consistent` vẫn trỏ A nên **bị lỗi/timeout**, vì single-cluster không failover tự động.
3. SRE kiểm tra replication lag, nguy cơ xung đột và quyết định chuyển profile transactions sang B khi đáp ứng runbook.
4. Đội ứng dụng đảm bảo client A có endpoint/compute thay thế; dashboard vẫn đo đủ p99, lỗi và replication delay.
5. Khi A phục hồi, **không** chuyển mọi writes về A ngay nếu chưa xác minh dữ liệu nhất quán và không còn hai writers tranh chấp.

**Bài học:** HA tự động cho telemetry và consistency chặt cho một luồng giao dịch có thể **cùng tồn tại trên một instance nhưng qua app profiles khác nhau**; điều này tạo sự khác biệt về runbook và RPO. Không nhầm “đọc được ở B” với “không mất khả năng quan sát dữ liệu mới nhất” sau sự cố.

## 13. Troubleshooting: nhìn đúng tầng

| Triệu chứng | Nguyên nhân có thể | Kiểm tra đầu tiên |
| --- | --- | --- |
| Write A thành công, read B thấy giá trị cũ | Eventual replication chưa hoàn tất. | App profile routing, replication latency/max delay, read path. |
| Read sau write trên cùng ứng dụng đôi khi stale | Profile multi-cluster, row-affinity không áp dụng hoặc có failover. | Loại request, app profile, route và automatic failover metrics. |
| `CheckAndMutateRow` bị từ chối | App profile multi-cluster hoặc chưa bật transactional writes. | `route-to`/`transactional-writes`, không bật tùy tiện trên nhiều clusters. |
| Counter bị thiếu increments | Conditional/RMW writes xung đột ở nhiều clusters. | Writer ownership, multiple profiles, transaction safety. |
| Chỉ thấy độ trễ cao tại region B | Network path xa, B CPU nóng, hotspot hoặc replication tải cao. | Client/server latency, hottest node CPU, read/write QPS. |
| Tăng clusters mà write throughput không tăng | Mỗi cluster còn phải replicate writes. | Replication CPU, node count, client QPS. |
| Failover tự động không xảy ra | Profile single-cluster hoặc cluster group không có đích khỏe. | Routing policy, allowed clusters, system errors. |
| Failover tự động rồi stale reads | Cluster mới chưa nhận hết writes của nguồn. | Replication lag, hướng traffic, SLO freshness. |
| SQL query qua row-affinity vẫn đọc cluster khác | Row-affinity **không áp dụng cho `ExecuteQuery`**. | API method, routing docs, app profile. |
| Sau thêm cluster, sticky routing đổi | Row-key-to-cluster assignment thay đổi. | Cluster membership, dùng `--restrict-to` khi cần. |
| Không đổi được app profile | Thiếu quyền quản trị hoặc policy cảnh báo xung đột. | IAM, CLI warnings, approval; không tự thêm `--force`. |
| Backup sau failover thiếu writes rất mới | Bản sao cluster backup chưa có writes chưa replicate. | Consistency token, backup timing, restore drill. |

**Quy trình ngắn:** xác nhận project/instance/cluster/app profile → xác định đường reads/writes → kiểm tra freshness và transaction type → đọc replication/server/client metrics → đánh giá failover, IAM/capacity → kiểm chứng bằng canary/consistency token khi phù hợp → chỉ đổi routing sau phê duyệt.

## 14. Bài tập

### Bài 1 — Eventual consistency

Ghi một row ở A rồi đọc ở B sau 20 ms nhưng vẫn thấy giá trị cũ. Đây có chắc là lỗi replication không? Cần xem metric nào trước khi kết luận sự cố?

### Bài 2 — Chọn app profile

Chọn profile cho: (a) telemetry dashboard chấp nhận stale; (b) API luôn đọc lại writes ngay trên cùng cluster; (c) scan báo cáo chỉ ở cluster B; (d) single-row counter dùng check-and-mutate. Nêu loại routing và nguyên tắc failover.

### Bài 3 — Tại sao tăng cluster không tăng write throughput?

Instance một cluster có 4 nodes; sau khi thêm cluster thứ hai, writes/s không tăng như kỳ vọng. Giải thích chi phí CPU replication và cách đo xem nút thắt ở đâu.

### Bài 4 — Row-affinity và SQL

Một profile `--route-any --row-affinity` được dùng để `ExecuteQuery` SQL lọc `WHERE row_key = ...`, nhưng read-your-writes vẫn không ổn định. Vì sao? Nếu chuyển sang `ReadRows` với đúng một row key thì đã có bảo đảm tuyệt đối chưa?

### Bài 5 — Single-row transaction

Hai regions cùng increment `sold=5` qua read-modify-write. Mỗi nơi tạo giá trị 6. Tại sao không thể suy ra 7 từ hai writes? Cấu hình nào bị Bigtable cấm và thiết kế nào an toàn hơn?

### Bài 6 — Failover thủ công

Cluster A gặp lỗi, profile `orders-consistent` trỏ tới A; B đang lag. Lập checklist quyết định failover, thay đổi `gcloud` cần thực hiện và bước xác minh sau thay đổi. Vì sao không được tuyên bố RPO bằng 0?

### Bài 7 — Default profile

Instance bắt đầu với một cluster, sau đó được thêm B. `default` có tự chuyển thành multi-cluster routing không? Một instance ban đầu có hai clusters thì khác gì? Làm sao tránh phụ thuộc vào sự khác biệt lịch sử này?

### Bài 8 — Consistency token và backup

Bạn cần tạo backup sau batch writes từ A và phải chắc chắn B đã nhận đủ writes trước mốc. Mô tả thứ tự generate/check consistency token, xử lý timeout và vì sao token không đảm bảo những writes đến **sau** mốc tạo token.

### Bài 9 — Kiến trúc và chi phí

Thiết kế hệ thống IoT có 100.000 devices gửi events, hai regions, latency đọc thấp và yêu cầu lưu bản sao dự phòng. Chọn routing, SLO freshness, metrics, capacity cho trường hợp mất một cluster và các khoản phí cần dự toán. Nếu có thêm giao dịch thanh toán đa hàng, nên đưa nó vào Bigtable không?

## 15. Checklist production và tài liệu chính thức

| Hạng mục | Tiêu chí kiểm chứng |
| --- | --- |
| **Replication** | Có đúng số clusters/regions, năng lực từng cluster và theo dõi latency giữa chúng. |
| **Consistency** | Mỗi luồng ghi/đọc có yêu cầu eventual, read-your-writes hoặc strong rõ ràng. |
| **Routing** | Profiles đặt tên theo workload; không dựa vào `default` ngoài chủ đích. |
| **Transactions** | Single-row transactional writes chỉ trên single-cluster profile; không ghi xung đột giữa clusters. |
| **Row-affinity** | Chỉ dùng đúng one-row operations; không xem là bảo đảm tuyệt đối hoặc cho SQL. |
| **Failover** | Biết profile nào tự đổi cluster, profile nào cần manual runbook; đã diễn tập failback. |
| **Monitoring** | Replication p95/p99/max delay, CPU/hottest node, auto failovers, errors, latency. |
| **Backups** | Có backup/restore drill, đánh giá replication lag và consistency tokens khi cần. |
| **IAM/network** | Runtime SA tối thiểu, quyền quản trị routing riêng, Google APIs egress hợp lệ. |
| **SLO/chi phí** | RTO/RPO/freshness hợp lý; đo N-1 capacity, storage, transfer và client cost. |

Nguồn tham khảo chính thức:

- [Bigtable — Replication overview](https://cloud.google.com/bigtable/docs/replication-overview)
- [Bigtable — Routing options](https://cloud.google.com/bigtable/docs/routing)
- [Bigtable — App profiles overview](https://cloud.google.com/bigtable/docs/app-profiles)
- [Bigtable — Configure app profiles](https://cloud.google.com/bigtable/docs/configuring-app-profiles)
- [Bigtable — Replication settings examples](https://cloud.google.com/bigtable/docs/replication-settings)
- [Bigtable — Replication and performance](https://cloud.google.com/bigtable/docs/replication-performance)
- [Bigtable — Writes and conflict resolution](https://cloud.google.com/bigtable/docs/writes)
- [Bigtable — Failovers](https://cloud.google.com/bigtable/docs/failovers)
- [Bigtable — Manage failovers](https://cloud.google.com/bigtable/docs/managing-failovers)
- [Bigtable — Metrics and monitoring](https://cloud.google.com/bigtable/docs/metrics)
- [Bigtable — Consistency token API](https://cloud.google.com/bigtable/docs/reference/admin/rest/v2/projects.instances.tables/generateConsistencyToken)
- [Bigtable — Backups](https://cloud.google.com/bigtable/docs/backups)
- [Bigtable Java client settings](https://cloud.google.com/java/docs/reference/google-cloud-bigtable/latest/com.google.cloud.bigtable.data.v2.BigtableDataSettings)
- [Bigtable pricing](https://cloud.google.com/bigtable/pricing)

**Ghi nhớ:** Bigtable replication lưu nhiều bản sao và tăng khả năng failover, nhưng **đồng bộ bất đồng bộ** nên khi đọc từ cluster khác có thể gặp stale data. **App profile** quyết định consistency và failover: single-cluster ưu tiên read-your-writes và cho phép single-row transactions, còn multi-cluster ưu tiên tự động chuyển cluster và chấp nhận eventual consistency. Row-affinity chỉ **giảm xác suất** đọc cũ cho thao tác một hàng. Vận hành đúng nghĩa là chọn routing theo nghiệp vụ, kiểm soát conflicting writes, đo replication lag, diễn tập failover và dự toán đầy đủ chi phí mỗi cluster.


