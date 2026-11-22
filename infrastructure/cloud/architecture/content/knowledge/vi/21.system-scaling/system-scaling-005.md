# Phân vùng theo nghiệp vụ, khách hàng hoặc địa lý

Khi hệ thống tăng về số người dùng, số giao dịch và lượng dữ liệu, một database hoặc một nhóm máy chủ tập trung có thể trở thành giới hạn. Tăng cấu hình máy (scale up) chỉ giúp đến một ngưỡng nhất định; sau đó hệ thống cần phân phối dữ liệu và tải qua nhiều node, nhóm dịch vụ hoặc vùng triển khai. Một quyết định quan trọng là **chia hệ thống theo ranh giới nào**: theo nghiệp vụ, theo khách hàng/tenant hay theo địa lý.

Phân vùng theo nghiệp vụ giúp mỗi domain sở hữu dữ liệu và năng lực xử lý riêng. Phân vùng theo khách hàng cô lập dữ liệu và tải giữa các tenant, phù hợp với SaaS hoặc nền tảng phục vụ nhiều tổ chức. Phân vùng theo địa lý đưa dữ liệu và compute gần người dùng, hỗ trợ latency, khả năng phục hồi vùng và yêu cầu residency. Các cách này có thể kết hợp, nhưng mỗi lớp phân vùng thêm routing, vận hành, kiểm soát nhất quán và chi phí.

Không có một shard key hoặc topology tốt cho mọi workload. Quyết định cần xuất phát từ access pattern, quy mô tenant, ranh giới dữ liệu, yêu cầu giao dịch, luật dữ liệu, vị trí người dùng và khả năng vận hành. Một thiết kế tốt phải trả lời được: dữ liệu nào nằm ở đâu, request được định tuyến thế nào, khi một partition quá tải thì xử lý ra sao, và làm sao di chuyển dữ liệu mà không làm mất tính đúng đắn.

Bài học thuộc phần **Mở rộng hệ thống** trong học phần kiến trúc cloud. Trọng tâm là phân vùng theo nghiệp vụ, khách hàng hoặc địa lý để cân bằng khả năng mở rộng, độ tin cậy, bảo mật, hiệu năng, chi phí và vận hành theo tư duy Well-Architected.

Sau bài học, bạn có thể:

- Giải thích partitioning, sharding và khác biệt giữa phân vùng logic với phân vùng vật lý.
- Chọn phân vùng theo domain, tenant hoặc geography dựa trên workload và yêu cầu nghiệp vụ.
- Thiết kế shard key, partition map, routing và directory service.
- Nhận diện hotspot, skew, tenant lớn và giới hạn của hash/range partitioning.
- Thiết kế transaction, consistency, uniqueness và query liên partition.
- Lập kế hoạch rebalancing, migration, backup/restore và multi-region failover.
- Đánh giá data isolation, residency, observability, cost và khả năng vận hành.

## 1. Partitioning và sharding là gì?

Partitioning là cách chia một tập dữ liệu hoặc workload thành các phần nhỏ hơn theo một quy tắc. Mỗi phần gọi là partition. Partition có thể nằm trong cùng một database engine, được phân phối qua nhiều node hoặc nằm ở các cluster/region khác nhau.

Sharding thường chỉ việc phân phối dữ liệu qua nhiều database node hoặc shard độc lập. Mỗi shard lưu một phần dữ liệu và phục vụ một phần request. Trong thực tế, thuật ngữ partitioning và sharding đôi khi được dùng thay thế nhau; khi thiết kế cần nói rõ đó là partition logic trong một engine hay shard vật lý có failure domain và lifecycle riêng.

### Lợi ích

- **Scale out:** tăng năng lực bằng cách thêm node hoặc partition.
- **Giới hạn phạm vi tải:** query chỉ chạm partition cần thiết nếu key và query phù hợp.
- **Cô lập:** tenant hoặc domain có thể được cách ly về dữ liệu, quota và lỗi.
- **Locality:** đặt dữ liệu gần người dùng hoặc hệ thống phụ thuộc.
- **Lifecycle:** archive hoặc xóa dữ liệu theo vùng, tenant hay thời gian.
- **Failure containment:** sự cố một shard có thể giới hạn ảnh hưởng nếu routing và dependency được thiết kế đúng.

### Chi phí và rủi ro

- Query/join xuyên shard phức tạp hơn.
- Transaction nhiều partition khó đảm bảo atomicity.
- Routing, metadata và shard placement trở thành thành phần quan trọng.
- Rebalancing, backup, restore và migration phức tạp hơn.
- Phân bố dữ liệu lệch có thể làm một shard quá tải dù tổng cluster còn dư.
- Một partition map sai hoặc directory lỗi có thể ảnh hưởng diện rộng.

Sharding không phải bước mặc định khi hệ thống tăng tải. Trước khi chia, hãy kiểm tra index, query plan, connection pool, caching, read replica, vertical scaling và khả năng tách workload. Chỉ thêm shard khi có bằng chứng rằng chia tải/data sẽ giải quyết bottleneck cụ thể.

## 2. Chọn ranh giới phân vùng

Ba ranh giới chính giải quyết những vấn đề khác nhau:

| Ranh giới | Đơn vị được chia | Mục tiêu nổi bật | Thách thức chính |
| --- | --- | --- | --- |
| **Theo nghiệp vụ/domain** | Bounded context, service hoặc data product | Ownership, autonomy và scale riêng theo năng lực nghiệp vụ | Query liên domain, transaction và phối hợp dữ liệu |
| **Theo khách hàng/tenant** | Một tenant, nhóm tenant hoặc tenant partition | Isolation, noisy-neighbor control, scale theo khách hàng | Tenant skew, di chuyển tenant và shared-vs-dedicated tradeoff |
| **Theo địa lý** | Region, country, market hoặc locality | Latency, residency, regional resilience | Routing, replication, data sovereignty và cross-region consistency |

### 2.1. Phân vùng theo nghiệp vụ

Tách theo domain khi các nhóm nghiệp vụ có access pattern, lifecycle, SLO hoặc quyền sở hữu khác nhau. Ví dụ Booking, Payment, Catalog và Analytics có thể dùng datastore và scaling policy riêng.

Lợi ích:

- Mỗi domain tối ưu schema, index và capacity theo workload riêng.
- Lỗi hoặc tải đột biến của một domain ít ảnh hưởng domain khác nếu dependency được giới hạn.
- Team có thể triển khai và nâng cấp độc lập trong ranh giới contract.
- Dữ liệu không cần join liên tục có thể đặt gần service sở hữu.

Đánh đổi:

- Một use case liên domain cần API, event hoặc data platform để tổng hợp.
- Giao dịch xuyên domain thường phải dùng Saga hoặc workflow.
- Cần thống nhất identity, correlation, schema và policy bảo mật.
- Không nên tách một domain thành quá nhiều service/partition nhỏ nếu chưa có ownership và năng lực vận hành tương ứng.

Domain partitioning là ranh giới ownership trước tiên; nó không nhất thiết đồng nghĩa mỗi domain phải có một cluster riêng ngay từ đầu. Có thể bắt đầu bằng schema/database riêng trên hạ tầng chia sẻ rồi tách vật lý khi cần isolation hoặc scale.

### 2.2. Phân vùng theo khách hàng hoặc tenant

Trong nền tảng SaaS, nhiều khách hàng dùng chung một sản phẩm nhưng yêu cầu dữ liệu và tải có thể khác nhau. Có ba mô hình thường gặp:

| Mô hình | Cách lưu | Ưu điểm | Đánh đổi |
| --- | --- | --- | --- |
| Shared database, shared schema | Mọi tenant dùng chung bảng, có tenant key | Hiệu quả chi phí, vận hành tập trung | Cần row-level isolation, index và kiểm soát noisy neighbor |
| Shared database, schema per tenant | Schema riêng trong cùng engine/database | Ranh giới logic rõ hơn | Migration hàng loạt, nhiều schema/object và giới hạn engine |
| Database/shard per tenant hoặc tenant group | Tenant được gán vào database/cluster riêng | Isolation, backup/restore và placement linh hoạt | Chi phí, số connection, fleet operations và migration cao |

Không có mô hình nào phù hợp mọi tenant. Một hệ thống có thể bắt đầu shared schema cho đa số khách hàng, dùng shard theo nhóm tenant khi quy mô tăng và dành dedicated database cho khách hàng rất lớn hoặc có yêu cầu cách ly đặc biệt.

### 2.3. Phân vùng theo địa lý

Dữ liệu có thể được đặt theo country, market hoặc region phục vụ người dùng. Điều này hỗ trợ:

- Giảm network latency cho user và service cùng khu vực.
- Giữ dữ liệu trong ranh giới địa lý theo luật/hợp đồng khi có yêu cầu.
- Giới hạn ảnh hưởng khi một region gặp sự cố.
- Phân phối tải theo market và giờ cao điểm địa phương.

Nhưng multi-region không tự động đem lại consistency hoặc DR. Phải xác định region nào là writer, read replica phục vụ gì, failover quyền ghi thuộc ai, dữ liệu cross-region được truyền theo luật nào và conflict được giải quyết ra sao.

## 3. Có thể kết hợp nhiều chiều phân vùng

Một hệ thống lớn thường dùng nhiều chiều theo thứ tự rõ ràng. Ví dụ chọn region theo tenant residency, sau đó shard theo tenant ID trong region, còn domain Booking và Payment có datastore riêng.

~~~mermaid
flowchart TD
    REQ["Request"] --> AUTH["Resolve identity and tenant"]
    AUTH --> GEO["Select permitted region"]
    GEO --> DOMAIN["Route to business domain"]
    DOMAIN --> TENANT["Resolve tenant partition"]
    TENANT --> SHARD["Selected shard / database"]
~~~

Ví dụ topology:

~~~text
Platform
  Region A
    Booking domain
      Tenant shard group 1
      Tenant shard group 2
    Payment domain
      Payment shard group 1
  Region B
    Booking domain
      Tenant shard group 3
    Payment domain
      Payment shard group 2
~~~

Sơ đồ chỉ minh họa thứ bậc placement. Tránh tạo quá nhiều chiều phân vùng vì số tổ hợp tăng nhanh, kéo theo routing, metadata, deploy, monitoring và restore phức tạp. Mỗi chiều cần một lý do độc lập và owner rõ ràng.

## 4. Thiết kế shard key

Shard key quyết định bản ghi được đặt ở partition nào. Chọn key sai có thể tạo hotspot, phân bố lệch hoặc khiến phần lớn query phải truy cập nhiều shard.

Một shard key tốt thường:

- Có cardinality đủ lớn và phân bố tương đối đều theo tải thực.
- Có trong phần lớn query quan trọng để định tuyến trực tiếp.
- Ổn định trong vòng đời bản ghi.
- Không làm lộ dữ liệu nhạy cảm qua identifier.
- Phù hợp với transaction boundary và locality nghiệp vụ.
- Có thể hỗ trợ rebalancing hoặc directory mapping khi nhu cầu thay đổi.

### Các kiểu key

| Kiểu | Ví dụ | Ưu điểm | Rủi ro |
| --- | --- | --- | --- |
| Tenant ID | tenant_id | Cô lập truy vấn theo khách hàng | Một tenant rất lớn có thể thành hot shard |
| User/customer ID | customer_id | Phân phối theo người dùng | Query theo vùng/thời gian có thể fan-out |
| Geographic key | country/region | Đặt dữ liệu gần locality | Phân bố dân số/tải không đều; người dùng di chuyển |
| Hash key | hash(account_id) | Phân bố đều hơn khi input phân bố tốt | Query range khó; đổi shard count có thể remap nhiều key |
| Range key | date hoặc ID range | Range scan và lifecycle dễ | Key mới dồn vào partition cuối, tạo hotspot |
| Composite key | tenant_id + bucket | Tách tenant lớn thành nhiều bucket | Query cần fan-out hoặc thêm mapping |

### Hash partitioning

Hash key ánh xạ một ID qua hàm băm rồi xác định partition. Ví dụ về ý tưởng:

~~~text
partition = hash(tenant_id) mod N
~~~

Với N partition cố định, việc thay đổi N có thể khiến nhiều tenant chuyển shard. Hash partition phù hợp khi query chủ yếu theo key chính xác và cần phân bố tương đối đều. Consistent hashing hoặc virtual nodes có thể giảm lượng key phải chuyển khi thêm/bớt node, nhưng vẫn cần xử lý data migration và routing state.

### Range partitioning

Range partition chia theo khoảng key hoặc thời gian, ví dụ order ID, ngày tạo hay vùng ID. Nó hữu ích cho range query và archival, nhưng dữ liệu mới có thể dồn vào range hiện hành. Cần split partition, tạo bucket theo thời gian hoặc dùng chiến lược ghi phân tán để tránh hotspot.

### Composite key và bucket

Nếu một tenant quá lớn, partition chỉ theo tenant ID khiến toàn bộ tải dồn vào một shard. Có thể chia tenant thành nhiều bucket:

~~~text
bucket = hash(resource_id) mod B
partition = placement(tenant_id, bucket)
~~~

Điều này phân tán tải của một tenant nhưng truy vấn liệt kê toàn bộ dữ liệu tenant có thể cần đọc B bucket. Chọn B dựa trên access pattern và giới hạn fan-out, không chỉ dựa vào số shard hiện tại.

### Tránh key có cardinality thấp hoặc dễ skew

Các key như status (ACTIVE/INACTIVE), country với ít giá trị, hoặc ngày hiện tại có thể tạo partition mất cân bằng. Có thể kết hợp thêm hash suffix/bucket hoặc dùng key khác có phân bố phù hợp. Phải đo cả dung lượng lẫn request rate; dữ liệu cân bằng về số dòng chưa chắc cân bằng về tải.

## 5. Routing và partition directory

Sau khi xác định key, hệ thống phải tìm được partition đích. Có ba cách phổ biến:

1. **Deterministic routing:** client/service tính partition từ key và thuật toán đã thống nhất.
2. **Directory-based routing:** tra cứu tenant/key trong một metadata service để biết shard hiện tại.
3. **Proxy/router layer:** request đi qua proxy chuyên định tuyến và quản lý connection tới shard.

### Directory-based architecture

~~~mermaid
flowchart LR
    CLIENT["Application"] --> ROUTER["Shard router"]
    ROUTER --> DIR[("Partition directory")]
    DIR --> ROUTER
    ROUTER --> S1[("Shard A")]
    ROUTER --> S2[("Shard B")]
    ROUTER --> S3[("Shard C")]
    ADMIN["Placement controller"] --> DIR
    ADMIN --> MOVE["Migration workflow"]
    MOVE --> S1
    MOVE --> S2
~~~

Directory có thể lưu tenant → shard, region → cluster, virtual bucket → node và placement version. Nó trở thành dependency quan trọng, nên cần cache, HA, versioning, audit và quy trình cập nhật an toàn.

### Cache directory

Router có thể cache mapping để giảm latency. Nhưng mapping stale trong lúc di chuyển tenant có thể khiến ghi tới shard cũ. Cần:

- Placement version hoặc epoch.
- Cơ chế phát hiện stale route và refresh.
- Giai đoạn dual-read hoặc forwarding có giới hạn khi cutover.
- Fencing để chỉ shard sở hữu hiện hành được nhận ghi.
- Idempotent retry để request định tuyến lại không tạo duplicate.

Không cho client tùy ý chọn shard ID trong request. Routing phải dựa trên identity và directory do hệ thống kiểm soát.

## 6. Query theo phân vùng

Một query có shard key thường có thể route tới một partition (single-shard query). Query thiếu shard key có thể phải gửi tới nhiều partition (scatter-gather/fan-out), rồi tổng hợp kết quả.

### Single-shard query

Nếu request chứa tenant ID hoặc account ID và các bản ghi liên quan được đặt cùng shard, router có thể gửi thẳng đến shard đó. Đây là đường đi đơn giản và thường có latency ổn định hơn.

### Scatter-gather query

Ví dụ báo cáo tổng đơn hàng theo toàn nền tảng phải đọc nhiều shard, kết hợp kết quả và xử lý pagination/sort. Fan-out tăng với số shard và có thể bị chi phối bởi shard chậm nhất.

Các biện pháp:

- Giới hạn query fan-out và concurrency.
- Đặt timeout, partial result policy và cancellation.
- Dùng aggregate/read model/data platform cho báo cáo lặp lại.
- Phân trang theo cursor ổn định thay vì offset toàn cục tốn kém.
- Tránh query BI trực tiếp trên mọi OLTP shard.

### Cross-shard join

Join hai bảng cùng shard key có thể thực hiện tại shard. Join khác key hoặc khác domain cần lựa chọn:

- Denormalize dữ liệu vừa đủ cho query.
- Dùng application-level join có giới hạn và cache.
- Tạo read model/materialized view qua event.
- Đưa dữ liệu sang analytical platform.
- Thiết kế lại shard key nếu truy vấn đó là workload cốt lõi.

Không cố tạo một distributed join tùy ý trên mọi shard cho endpoint latency thấp.

## 7. Transaction và consistency xuyên partition

Khi các bản ghi của cùng transaction nằm trong một shard, local transaction có thể giữ semantics quen thuộc của database. Nếu transaction chạm nhiều shard, chi phí và độ phức tạp tăng đáng kể.

### Giữ transaction boundary cùng shard

Ví dụ booking và các dòng booking item thường được truy vấn/cập nhật cùng nhau. Nếu cùng shard key booking_id hoặc tenant_id, transaction có thể thực hiện cục bộ. Điều này là một tiêu chí khi chọn key.

### Cross-shard transaction

Có thể cần distributed transaction/2PC nếu engine và kiến trúc hỗ trợ, nhưng participant và failure handling sẽ phức tạp hơn. Thường có thể thiết kế lại nghiệp vụ theo Saga:

- Mỗi shard/service thực hiện local transaction.
- Phát event hoặc command với operation ID.
- Retry idempotent.
- Compensation khi không thể hoàn thành.
- Reconciliation cho kết quả không rõ.

Không tuyên bố atomicity toàn cục nếu hệ thống chỉ dùng event và retry. API phải thể hiện trạng thái PENDING/PROCESSING nếu workflow chưa hoàn tất.

### Uniqueness toàn cục

Unique constraint thông thường chỉ bảo vệ trong phạm vi database/shard. Nếu cần email hoặc external reference duy nhất trên toàn hệ thống:

- Dùng ID được sinh toàn cục và có collision risk được kiểm soát.
- Tạo registry/identity service có uniqueness boundary rõ.
- Định tuyến theo unique key nếu access pattern cho phép.
- Dùng reservation/claim service trước khi ghi các shard khác.

Không dựa vào kiểm tra read-then-write trên nhiều shard vì hai request đồng thời có thể cùng thấy chưa tồn tại.

## 8. Phân vùng tenant và noisy-neighbor isolation

Tenant có tải khác nhau. Một tenant enterprise có thể tạo nhiều request hoặc dữ liệu hơn hàng nghìn tenant nhỏ cộng lại. Nếu chỉ dùng shared shard với quota chung, tenant lớn có thể ảnh hưởng các tenant khác.

### Placement strategy theo tier

Một chiến lược kết hợp:

- Small tenants: shared shard group, phân bố bằng hash.
- Medium tenants: placement có kiểm soát theo capacity và workload.
- Large tenants: dedicated shard hoặc dedicated database khi lợi ích isolation xứng đáng chi phí.
- Regulated tenants: placement theo region/account và policy bảo mật riêng nếu cần.

### Quota và fairness

Đặt giới hạn theo tenant: request rate, concurrent jobs, storage, connection, queue depth và export size. Dùng rate limit/token bucket, workload queue và priority policy để tenant lớn không chiếm hết capacity.

Quota cần gắn với hợp đồng/SLO. Khi vượt ngưỡng, trả lỗi có thể retry phù hợp hoặc throttle; không âm thầm xếp hàng vô hạn khiến latency và chi phí tăng.

### Tenant migration

Chuyển một tenant từ shared shard sang dedicated shard cần:

1. Chọn tenant và xác định dung lượng/tải.
2. Tạo target và xác minh version/schema/index.
3. Snapshot hoặc initial copy.
4. Đồng bộ delta/CDC theo checkpoint.
5. Chuyển routing sang read target hoặc dual-read để validation.
6. Cutover writer với fencing/epoch và xử lý request đang chạy.
7. Reconcile counts/checksum/business invariants.
8. Giữ rollback window và xóa nguồn cũ theo policy.

Không chỉ đổi directory mapping rồi giả định dữ liệu đã chuyển xong.

## 9. Phân vùng địa lý và multi-region

Geo partitioning đặt tenant hoặc dữ liệu theo locality như country/market. Một tenant có thể được gán home region cố định hoặc dữ liệu có thể phân vùng theo đối tượng/địa điểm. Cần xác định trường hợp nào là bắt buộc.

### Home-region model

Mỗi tenant có một home region để ghi dữ liệu chuẩn. Người dùng có thể truy cập qua edge/API gateway, request được route về home region. Có thể dùng replica read ở nơi khác nếu nghiệp vụ chấp nhận lag.

Ưu điểm: writer ownership rõ và giảm conflict. Đánh đổi: user ở xa home region có latency cao; sự cố home region cần DR/failover có kiểm soát.

### Regional data residency

Khi luật hoặc hợp đồng yêu cầu dữ liệu lưu trong quốc gia/vùng cụ thể, phải xét:

- Primary data, backup, log, snapshot và export nằm ở đâu.
- Telemetry có chứa PII hoặc payload nhạy cảm không.
- Support access và control plane có truyền dữ liệu ra ngoài không.
- Cross-region replication có được phép không.
- Data deletion và retention được thực hiện ở mọi bản sao thế nào.

Không suy rằng region gần nhất luôn đáp ứng residency. Phải xác minh dịch vụ, region availability, backup behavior và hợp đồng.

### Active-passive và active-active

| Mô hình | Ghi dữ liệu | Ưu điểm | Rủi ro |
| --- | --- | --- | --- |
| Active-passive | Một region ghi, region dự phòng chờ | Writer ownership rõ, failover dễ suy luận hơn | Failover downtime, replication lag và failback |
| Active-active | Nhiều region có thể nhận ghi | Latency thấp và khả năng phục vụ khu vực | Conflict resolution, duplicate, ordering và consistency rất phức tạp |

Active-active chỉ phù hợp khi dữ liệu và nghiệp vụ có quy tắc conflict rõ, ví dụ partition theo chủ sở hữu hoặc operation có thể merge. Nếu cùng một số dư hoặc slot có thể được ghi đồng thời tại hai region, cần coordination hoặc single-writer rule.

### Regional failover

Runbook cần xác định:

- Khi nào tuyên bố region lỗi và ai có quyền failover.
- Xác định replica còn đủ mới theo RPO không.
- Fencing writer cũ để tránh split-brain.
- Cập nhật routing/directory/DNS.
- Xử lý request đang chạy và retry idempotent.
- Reconcile dữ liệu sau failover.
- Quy trình failback, không tự động chuyển writer về vùng cũ khi chưa kiểm tra.

## 10. Rebalancing và thay đổi topology

Khi thêm node, shard đầy hoặc tenant chuyển tier, cần phân phối lại dữ liệu. Đây là một trong những hoạt động rủi ro nhất của sharded system.

### Khi nào cần rebalancing?

- Một shard vượt dung lượng hoặc QPS mục tiêu.
- Tenant lớn gây hotspot.
- Thêm/bớt node do tăng trưởng hoặc sự cố.
- Thay đổi số virtual bucket hoặc placement policy.
- Di chuyển tenant sang region/dedicated shard.

### Các kỹ thuật

- **Consistent hashing/virtual nodes:** giảm số key phải remap khi thay đổi node membership.
- **Directory remapping:** đổi mapping có kiểm soát sau khi copy dữ liệu.
- **Split/merge partition:** chia range hoặc gộp partition nhỏ.
- **Online migration:** copy nền, CDC delta, cutover có fencing.
- **Tenant evacuation:** chuyển một tenant theo luồng riêng.

### Quy trình online migration gợi ý

~~~mermaid
flowchart TD
    A["Plan target capacity"] --> B["Create target partition"]
    B --> C["Initial snapshot copy"]
    C --> D["Stream ongoing changes"]
    D --> E["Validate counts, checksums, invariants"]
    E --> F{"Lag within threshold and validation pass?"}
    F -- "No" --> D
    F -- "Yes" --> G["Fence writes / short cutover"]
    G --> H["Switch placement version"]
    H --> I["Monitor target and reconcile"]
    I --> J["Retire old partition after rollback window"]
~~~

### Những gì cần bảo vệ

- Không để writer cũ và mới cùng nhận ghi không kiểm soát.
- Copy dữ liệu không bỏ sót update/delete xảy ra trong lúc copy.
- Checkpoint phải bền vững để migration có thể tiếp tục.
- Consumer và router xử lý stale mapping.
- Idempotency bảo vệ retry khi request chuyển shard.
- Có rollback plan và biết giới hạn rollback sau khi target nhận ghi mới.

## 11. Hotspot, skew và capacity planning

Một cluster có thể có tổng tài nguyên còn dư nhưng vẫn chậm nếu một shard nhận phần lớn traffic. Phân bố đều row count không đảm bảo đều request rate.

### Dấu hiệu

- Một partition có CPU/IO/connection cao hơn rõ rệt.
- P99 latency tăng theo một tenant/key group.
- Queue backlog và retry tập trung một shard.
- Storage growth lệch hoặc một range tăng rất nhanh.
- Router fan-out thường xuyên tới mọi shard.

### Biện pháp

- Chọn lại shard key hoặc thêm bucket cho tenant lớn.
- Tách tenant hot sang dedicated shard.
- Cache dữ liệu đọc nhiều nhưng không dùng cache làm nơi quyết định giao dịch.
- Throttle tenant hoặc workload gây nóng.
- Chia nhỏ partition/range và rebalancing.
- Tách analytical/reporting load khỏi OLTP shard.

### Tính dung lượng

Không chỉ tính storage:

~~~text
Shard demand =
  storage footprint
  + read/write QPS
  + active connections
  + CPU per query
  + IO/throughput
  + replication/backup overhead
  + growth and failover headroom
~~~

Capacity planning cần kiểm thử ở tải bình thường, peak, growth horizon và failure mode khi một shard/node/region mất. Nếu N shard đang chạy gần 100% capacity, mất một shard và dồn tải sang phần còn lại có thể làm toàn hệ thống sụp. Dự trữ headroom theo SLO và failure scenario.

## 12. Bảo mật, isolation và data governance

Phân vùng có thể tăng isolation nhưng chỉ khi mọi đường truy cập tuân thủ placement và authorization policy.

- Lấy tenant identity từ token/session đã xác thực, không tin tenant ID tự khai trong body.
- Router kiểm tra tenant → region/shard mapping từ directory được bảo vệ.
- Query layer bắt buộc thêm tenant scope hoặc dùng row-level security phù hợp.
- Database credential theo service/shard scope và least privilege.
- Dữ liệu cross-tenant không được xuất qua cache key, log, trace hoặc report.
- Encryption at rest/in transit và key policy phù hợp region.
- Backup, replica, snapshot, log và export tuân thủ cùng data classification/residency.
- Audit thay đổi placement, quyền và thao tác di chuyển dữ liệu.

Schema-per-tenant hoặc database-per-tenant không tự bảo đảm bảo mật nếu credential quản trị có quyền vào mọi tenant hoặc router không kiểm soát. Cần kiểm tra cả control plane lẫn data plane.

## 13. Observability và vận hành sharded systems

Một request có thể đi qua gateway, router, directory, service và shard. Observability cần theo dõi cả logical tenant, partition và physical node.

### Định danh xuyên suốt

Mỗi request/log/trace nên mang thông tin có kiểm soát:

- Request/correlation ID.
- Domain/service name.
- Tenant identifier được mask/hash theo policy.
- Region, shard ID và placement version.
- Query class hoặc operation name.
- Retry count, routing decision và error category.

Không đưa PII hoặc credential vào label metric có cardinality cao. Shard/tenant labels cần thiết kế để không làm monitoring backend quá tải.

### Metric quan trọng

| Metric | Mục tiêu |
| --- | --- |
| QPS/read/write theo shard | Phát hiện tải lệch |
| CPU, memory, IOPS, storage và connections | Theo dõi capacity |
| p50/p95/p99 theo tenant/shard/region | Nhìn thấy tail latency |
| Router cache hit và directory latency | Kiểm tra routing dependency |
| Fan-out count và scatter-gather duration | Phát hiện query không có shard key |
| Replication lag theo region/shard | Kiểm soát freshness và RPO |
| Rebalancing lag/bytes/errors | Quan sát migration |
| Failed/stale route và retry | Phát hiện mapping lỗi |
| Hot tenant/key và quota throttling | Kiểm soát noisy neighbor |
| Backup/restore status | Bảo đảm khả năng phục hồi |

### Runbook cần có

- Shard unavailable hoặc mất node.
- Directory/router stale hoặc không truy cập được.
- Tenant vượt quota hoặc gây hotspot.
- Rebalancing stuck hoặc validation mismatch.
- Cross-region lag hoặc failover.
- Tenant migration rollback.
- Restore một tenant/shard mà không ảnh hưởng tenant khác.

## 14. Backup, restore và disaster recovery theo partition

Backup trong hệ thống sharded có thêm yêu cầu phối hợp. Snapshot của từng shard ở các thời điểm khác nhau có thể không tạo thành một điểm phục hồi nhất quán trên toàn nghiệp vụ.

### Chính sách backup

- Xác định backup theo shard, tenant, region và toàn hệ thống.
- Ghi nhận timestamp, LSN/offset hoặc checkpoint cần thiết.
- Backup directory/placement metadata cùng version.
- Mã hóa và lưu backup theo residency policy.
- Kiểm tra khả năng restore độc lập tenant/shard và restore toàn cụm.
- Có runbook tái tạo router/credential/secret và network.

### Restore một tenant

Với shared shard, restore trực tiếp toàn shard có thể làm mất cập nhật của tenant khác. Các lựa chọn:

- Restore snapshot vào môi trường tạm rồi extract tenant rows theo point-in-time logic.
- Dùng logical backup/export theo tenant.
- Khôi phục shard mới rồi chuyển tenant qua directory sau khi validate.
- Dùng audit/event log để replay dữ liệu sau thời điểm snapshot nếu hỗ trợ.

Không phải engine nào cũng hỗ trợ tenant-level PITR; cần kiểm tra kỹ trước khi cam kết.

## 15. Những sai lầm thường gặp

**Chọn shard key chỉ theo số lượng dữ liệu.** Tải request và access pattern mới quyết định hotspot; row count cân bằng chưa đủ.

**Dùng tenant ID làm shard key mà không có chiến lược tenant lớn.** Một enterprise tenant có thể làm nóng một shard; cần bucket hoặc dedicated placement.

**Phân vùng theo region nhưng không xác định writer ownership.** Hai region có thể ghi xung đột hoặc tạo split-brain.

**Tin rằng hash partition giải quyết mọi query.** Query range và report liên shard vẫn phải fan-out; cần read model/warehouse.

**Đổi shard count mà không có migration plan.** Deterministic modulo remap có thể yêu cầu di chuyển phần lớn dữ liệu.

**Chỉ cập nhật directory sau khi copy một phần.** Request có thể đọc/ghi nhầm shard; cần checkpoint, fencing và cutover.

**Không có placement version.** Router cache stale có thể tiếp tục gửi ghi đến partition cũ.

**Cho phép cross-shard transaction tùy ý.** Latency và failure surface tăng; cân nhắc Saga và aggregate boundary.

**Cho báo cáo quét tất cả OLTP shard.** Fan-out query gây tải lớn; đưa workload vào data platform.

**Coi database-per-tenant là bảo mật đầy đủ.** Credential, backup, log và control plane vẫn có thể truy cập chéo.

**Không thử restore độc lập tenant.** Backup toàn cluster chưa chứng minh có thể phục hồi một khách hàng.

**Quên chi phí vận hành fleet.** Nhiều shard tăng backup, monitoring, patch, version drift, migration và support.

## 16. Ví dụ thiết kế: nền tảng SaaS đặt lịch nhiều quốc gia

**Bối cảnh giả định:** Một nền tảng phục vụ phòng khám ở nhiều quốc gia. Tenant nhỏ chia sẻ hạ tầng; một số chuỗi lớn có tải cao; một số khách hàng yêu cầu dữ liệu cư trú trong quốc gia của họ. Booking và Payment có workload, quyền sở hữu và SLO khác nhau. Dashboard toàn nền tảng cần tổng hợp dữ liệu theo ngày.

### Thiết kế phân vùng

1. Chọn region theo residency/home region của tenant.
2. Trong mỗi region, phân domain Booking và Payment để ownership, scale và access policy riêng.
3. Phân tenant nhỏ vào shared shard group bằng hash/virtual bucket.
4. Tenant lớn có placement riêng hoặc nhóm shard được dành capacity.
5. Router dùng directory tra tenant → region/domain/partition và placement version.
6. Data platform nhận event/CDC được phép để báo cáo liên miền; không fan-out truy vấn OLTP cho dashboard.

~~~mermaid
flowchart TD
    USER["User request"] --> GATE["API Gateway + authentication"]
    GATE --> DIR["Tenant placement directory"]
    DIR --> RA["Region A"]
    DIR --> RB["Region B"]
    subgraph A["Region A"]
        BA["Booking shard group"]
        PA["Payment shard group"]
    end
    subgraph B["Region B"]
        BB["Booking shard group"]
        PB["Payment shard group"]
    end
    RA --> A
    RB --> B
    BA --> EV["Governed events / CDC"]
    PA --> EV
    BB --> EV
    PB --> EV
    EV --> DP["Analytics data platform"]
~~~

### Các quyết định phải được kiểm chứng

- Shared shard có đáp ứng quota và isolation cho tenant nhỏ không?
- Tenant lớn có thể chuyển sang dedicated shard mà không downtime dài không?
- Directory outage ảnh hưởng gì; router có cache mapping và fencing không?
- Region failover có tuân thủ residency và RPO không?
- Payment và Booking có cần transaction cục bộ hay Saga khi phối hợp?
- Dashboard có thể báo cáo cross-region bằng dữ liệu đã được phép chuyển không?
- Restore một tenant có thể thực hiện mà không rollback tenant khác không?

## 17. Bài thực hành: thiết kế chiến lược phân vùng

**Tình huống:** Một SaaS phục vụ 10.000 doanh nghiệp ở ba khu vực. 9.700 tenant nhỏ, 250 tenant vừa và 50 tenant lớn. Một số tenant lớn tạo 35% tổng request. Khách hàng ở một số thị trường yêu cầu dữ liệu nằm tại region được chỉ định. Workload có đọc booking theo tenant và ngày, ghi booking theo ID, truy vấn báo cáo theo toàn tenant và tra cứu thanh toán. Đây là dữ liệu mô phỏng để luyện tập.

### Nhiệm vụ

1. **Chọn topology:** quyết định domain, tenant và geography partition theo thứ tự; phân biệt logic ownership với physical shard.
2. **Chọn shard key:** đề xuất key cho booking và payment; giải thích single-shard query, hot tenant, range scan và cross-shard reporting.
3. **Thiết kế placement directory:** xác định mapping, version, cache, HA, routing và quyền cập nhật.
4. **Lập tenant tiering:** tenant nhỏ/vừa/lớn dùng mô hình shared, shard group hay dedicated; định nghĩa tiêu chí di chuyển.
5. **Thiết kế consistency:** transaction boundary, global uniqueness, Saga, read model và event flow.
6. **Thiết kế geo:** home region, writer ownership, read replica, residency, DR/failover và failback.
7. **Lập migration plan:** chuyển một tenant hot sang shard riêng qua snapshot/CDC, validate, fencing và cutover.
8. **Thiết kế vận hành:** metric skew, QPS, latency, fan-out, directory, lag, backup và runbook.

### Ma trận kiểm thử

| Phép thử | Tình huống | Bằng chứng cần có |
| --- | --- | --- |
| Tenant isolation | Đổi tenant ID hoặc routing input giả mạo | Không đọc/ghi chéo dữ liệu |
| Hot tenant | Tenant lớn tăng tải nhiều lần | Quota/fairness hoạt động, tenant khác giữ SLO |
| Shard unavailable | Một database shard mất kết nối | Retry/fallback có giới hạn, ảnh hưởng được cô lập |
| Directory stale | Router giữ mapping cũ trong lúc migration | Placement version/fencing chặn ghi sai |
| Rebalance | Chuyển virtual bucket/shard | Counts/checksum/business invariant khớp |
| Cross-shard query | Báo cáo toàn tenant | Fan-out được giới hạn hoặc dùng read model |
| Region outage | Home region mất | RTO/RPO và writer fencing đạt kế hoạch |
| Replica lag | Read replica chậm | Query cần read-after-write quay về writer |
| Restore tenant | Một tenant cần phục hồi | Không làm mất dữ liệu tenant khác |
| Residency audit | Kiểm tra data/backup/log placement | Không có bản sao trái policy |
| Duplicate retry | Request được gửi lại qua routing change | Idempotency không tạo record trùng |
| Capacity failover | Một shard mất, tải chuyển sang phần còn lại | Headroom đủ hoặc admission control bảo vệ hệ thống |

### Deliverables

- Sơ đồ logical/physical partition topology.
- Shard key decision record và query routing matrix.
- Tenant tiering và placement policy.
- Directory API/data model cùng versioning strategy.
- Multi-region/residency/DR plan.
- Online migration/rebalancing runbook.
- Security/isolation matrix.
- Load, failure, restore, latency và cost validation report.

## 18. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi cho partitioning |
| --- | --- |
| **Operational Excellence** | Có placement inventory, routing version, migration runbook, capacity dashboard và owner cho shard không? |
| **Security** | Tenant isolation, region residency, IAM, backup/log access và audit placement có được kiểm soát? |
| **Reliability** | Shard/region failure, directory outage, stale route, backup/restore và rebalancing recovery đã được thử? |
| **Performance Efficiency** | Shard key phân bố theo QPS và storage? Query fan-out, hot key, connection và tail latency có được đo? |
| **Cost Optimization** | Shared/dedicated tradeoff, replication, backup, cross-region transfer và fleet overhead có hợp lý? |
| **Sustainability** | Có tránh over-sharding, dữ liệu nhân bản không cần thiết, node nhàn rỗi và rebalancing dư thừa không? |

## 19. Checklist trước khi đưa phân vùng vào production

- [ ] Bottleneck đã được đo và không thể giải quyết hợp lý chỉ bằng index, cache hoặc scale up.
- [ ] Ranh giới domain, tenant và geography có lý do nghiệp vụ rõ.
- [ ] Shard key phù hợp query, transaction boundary, cardinality và phân bố QPS.
- [ ] Hot tenant/key và data skew có chiến lược xử lý.
- [ ] Single-shard và fan-out query có policy, timeout và concurrency limit.
- [ ] Directory/router có HA, cache, version, audit và stale mapping handling.
- [ ] Tenant isolation, authentication, authorization và quota được kiểm thử.
- [ ] Transaction xuyên shard có thiết kế rõ; dùng Saga khi phù hợp.
- [ ] Global uniqueness có registry/claim strategy phù hợp.
- [ ] Home region, writer ownership, residency, replication và failover được xác định.
- [ ] Rebalancing/migration có snapshot, CDC, checkpoint, fencing, validation và rollback window.
- [ ] Backup/restore bao phủ cả shard data và placement metadata; có test restore từng tenant.
- [ ] Observability theo tenant/shard/region có cardinality kiểm soát và cảnh báo phù hợp.
- [ ] Capacity headroom được kiểm tra cả khi một shard/region mất.
- [ ] Cost tính cả replica, backup, network, router, directory, migration và fleet operations.
- [ ] Có ADR, runbook, owner và trigger xem lại khi tải/tenant/region thay đổi.

Phân vùng theo nghiệp vụ, khách hàng hoặc địa lý giúp hệ thống mở rộng và cô lập tải theo các ranh giới có ý nghĩa. Nhưng mỗi ranh giới bổ sung thêm routing, consistency, migration và vận hành. Hãy bắt đầu từ access pattern và ownership, chọn shard key phản ánh cả query lẫn phân bố tải, rồi thiết kế directory, isolation, failover và rebalancing như những năng lực cốt lõi. Một hệ thống sharded chỉ thực sự mở rộng tốt khi có thể phân phối dữ liệu **và** thay đổi placement an toàn, quan sát được và phục hồi được khi sự cố xảy ra.
