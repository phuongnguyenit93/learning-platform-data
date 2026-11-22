# Đánh giá chi phí vận hành khi thêm một công nghệ lưu trữ

Một hệ thống quản lý đơn hàng đang dùng MongoDB làm nơi lưu dữ liệu nghiệp vụ. Nhóm phát triển nhận thấy chức năng tìm kiếm đơn theo nhiều trường trở nên chậm khi dữ liệu tăng. Một người đề xuất thêm một search engine; người khác muốn đưa Redis vào cache. Một kỹ sư nhận xét: “Giá một node không đáng kể.” Nhưng người trực hệ thống hỏi: “Ai cập nhật dữ liệu, xử lý index lệch, vá lỗi bảo mật, khôi phục sau sự cố và chịu trách nhiệm khi hai database trả kết quả khác nhau?”

Đó là câu hỏi cốt lõi của bài học: **thêm một công nghệ lưu trữ không chỉ thêm máy chủ, mà còn thêm một vòng đời vận hành, tích hợp và rủi ro**. Một database có thể giúp truy vấn nhanh hơn, nhưng cũng có thể làm hệ thống phức tạp hơn, tăng chi phí kỹ sư, kéo dài thời gian phục hồi và khiến dữ liệu phân kỳ nếu không thiết kế đúng.

Bài học thuộc chương **Tích hợp và kiến trúc** của module **Database No SQL**. Ta sẽ xây dựng cách đánh giá **Total Cost of Ownership (TCO)**, phân biệt chi phí trực tiếp với chi phí ẩn, mô hình hóa chi phí tích hợp và đồng bộ, xác định trách nhiệm vận hành, so sánh managed với self-hosted, tính một ví dụ ba năm, xây ma trận quyết định và kế hoạch pilot/rollback. Ví dụ có MongoDB, Redis, Cassandra, Elasticsearch/OpenSearch, graph và vector store, nhưng tư duy áp dụng cho phần lớn hệ lưu trữ chuyên biệt.

**Mục tiêu:** sau bài này, bạn có thể bảo vệ một quyết định “nên thêm”, “chưa nên thêm” hoặc “nên tối ưu công nghệ hiện tại” bằng **workload, SLO, tính đúng dữ liệu, chi phí tăng thêm, năng lực đội ngũ và bằng chứng kiểm thử**, thay vì chỉ dựa trên sức hấp dẫn của công nghệ.

## 1. Một database mới là một hệ thống cần chịu trách nhiệm

Kiến trúc ban đầu:

~~~text
Order API
    |
    v
MongoDB (source of truth)
~~~

Sau khi thêm search engine:

~~~mermaid
flowchart LR
    A["Order API"] --> M["MongoDB - nguồn chính"]
    M --> O["Outbox / CDC"]
    O --> S["Search index"]
    Q["Search API"] --> S
~~~

Lợi ích có thể có:

- Full-text search, phân tích từ khóa hoặc relevance ranking tốt hơn.
- Tách một số truy vấn đọc nặng khỏi cơ sở dữ liệu giao dịch.
- Cải thiện p95/p99 của tính năng tìm kiếm.
- Dễ xây facets, filter, autocomplete hoặc phân tích chuyên biệt.

Những trách nhiệm mới:

- Cụm tìm kiếm và replica, shard, index, storage.
- Pipeline đưa dữ liệu từ MongoDB sang search.
- Backfill và reindex khi thêm/sửa mapping.
- Xử lý UPDATE/DELETE đến trễ, thiếu hoặc trùng.
- Theo dõi indexing lag, cảnh báo và incident.
- Backup, restore/rebuild và quyền truy cập.
- Nâng cấp phiên bản, driver, connector và chứng chỉ.
- Dọn dữ liệu, bảo mật, audit, compliance.

**Không tính được những phần này thì chưa tính được chi phí sở hữu giải pháp.**

## 2. Xác định vấn đề thật trước khi chọn công nghệ

Không bắt đầu từ câu hỏi “nên dùng Redis hay Elasticsearch?”, mà bắt đầu từ:

1. Endpoint nào đang chậm, lỗi hoặc không hỗ trợ chức năng?
2. Dữ liệu hiện có bao nhiêu, tăng ra sao và giữ bao lâu?
3. Quy mô **đọc/ghi**, peak và phân bố tải giữa các tenant là gì?
4. Đã xem query plan, index, partition key và slow-query logs chưa?
5. Query cần search full-text thật hay chỉ filter theo vài trường?
6. Có chấp nhận dữ liệu trễ vài giây, hay yêu cầu read-your-writes?
7. Tính năng mới tạo ra giá trị nghiệp vụ cụ thể nào?
8. Phương án tối ưu engine hiện tại là gì?

Ví dụ:

~~~text
GET /orders/{id}:
  p99 45 ms, đạt SLO.

GET /orders/search:
  p99 2.400 ms, chưa đạt SLO.

Tìm kiếm chiếm:
  8% tổng requests.

Query chủ lực:
  tenantId + status + createdAt.
~~~

Chưa thể kết luận cần một search cluster. Một **compound index**, query rewrite, cursor pagination hoặc read model đơn giản trong MongoDB có thể đủ. Nếu workload cần tiếng Việt full-text, relevance ranking và nhiều facets phức tạp, search engine chuyên biệt lại có thể có lợi thế thực chất.

## 3. Chốt tiêu chí thành công trước khi chạy PoC

Một đề xuất nên có các tiêu chí đo được:

| Lĩnh vực | Ví dụ mục tiêu |
|---|---|
| Latency | Search p99 dưới 250 ms ở workload đại diện |
| Throughput | Chịu peak dự báo với headroom |
| Freshness | 99,9% thay đổi xuất hiện trong index dưới 5 giây |
| Correctness | Không hồi sinh record đã DELETE do event cũ |
| Security | Tenant isolation, dữ liệu nhạy cảm được hạn chế |
| Availability | Search lỗi không làm CreateOrder lỗi theo thiết kế |
| Recovery | RTO/RPO đáp ứng sản phẩm |
| Cost | Incremental TCO 36 tháng trong ngân sách |
| Operations | Có owner, on-call, runbook và restore drill |
| Exit | Có thể tắt hoặc thay engine mà vẫn giữ nguồn dữ liệu |

Các con số ở đây minh họa cách đặt tiêu chí, không phải khuyến nghị chung.

**Đạt latency nhưng làm dữ liệu xóa xuất hiện trở lại là thất bại về tính đúng**, không phải một tối ưu đã hoàn thành.

## 4. Total Cost of Ownership (TCO)

TCO là tổng chi phí trong suốt vòng đời của một công nghệ, không chỉ hóa đơn mua/thuê.

\[
\begin{aligned}
\operatorname{TCO}(T)={}&C_{\text{setup}}
+\sum_{t=1}^{T}\big(
C_{\text{infrastructure},t}
+C_{\text{people},t}\\
&+C_{\text{licensing},t}
+C_{\text{integration},t}
+C_{\text{risk},t}\big)
+C_{\text{exit}}
\end{aligned}
\]

Trong đó:

- **Setup:** thiết kế, PoC, xây pipeline, backfill, cấu hình.
- **Infrastructure:** compute, memory, disk, network, backup, replicas.
- **People:** triển khai, vận hành, on-call, nâng cấp, đào tạo.
- **License/support:** phí dịch vụ, enterprise features/support nếu có.
- **Integration:** connector, CDC, outbox, migration, consistency handling.
- **Risk:** rủi ro downtime và sai dữ liệu được lượng hóa bằng phương pháp phù hợp; tránh đếm trùng chi phí sự cố đã có.
- **Exit:** chuyển hệ, export dữ liệu, tắt pipeline, gỡ code và xóa dữ liệu.

Không phải mọi khoản đều là **chi tiền mặt**. Thời gian của kỹ sư nội bộ có thể là phân bổ nguồn lực hoặc chi phí cơ hội. Nên báo cáo rõ loại chi phí để tránh đếm đôi.

## 5. So sánh **chi phí tăng thêm**, không so chi phí tuyệt đối

Giả sử cả hai phương án đều phải giữ MongoDB:

~~~text
Phương án A:
  MongoDB + tối ưu index/query.

Phương án B:
  MongoDB + search engine riêng + CDC.
~~~

Khi đó:

\[
\Delta\mathrm{TCO} =
\mathrm{TCO}_{B}-\mathrm{TCO}_{A}
\]

Nếu MongoDB hiện tốn 5.000 USD/tháng ở cả hai phương án thì không nên quy toàn bộ 5.000 USD thành chi phí riêng của B.

Ngược lại, B có thể làm **MongoDB tốn thêm** vì change streams, outbox writes, backup hoặc backfill; khoản tăng thêm đó phải được tính vào B.

**So sánh đúng là so hai kiến trúc hoàn chỉnh phục vụ cùng yêu cầu**, bao gồm công việc cần làm dù không thêm công nghệ.

## 6. Chi phí một lần và chi phí định kỳ

| Hạng mục | Loại | Ví dụ |
|---|---|---|
| Khảo sát, PoC, benchmark | Ban đầu | Kiểm tra workload đại diện |
| Thiết kế data model/index | Ban đầu + thay đổi | Routing key, mapping, query |
| Viết connector/outbox | Ban đầu + bảo trì | Source → projection |
| Backfill/migration | Ban đầu, có thể lặp | Chuyển lịch sử dữ liệu |
| Security review và IaC | Ban đầu + duy trì | IAM, mTLS, secrets |
| Compute/storage/network | Định kỳ | Cluster, disk, traffic |
| Backup/restore drill | Định kỳ | Snapshot, recovery |
| Quan sát/alerts | Định kỳ | Metrics, logs, tracing |
| Nâng cấp/vá lỗi | Định kỳ | Version, CVEs, drivers |
| On-call và sự cố | Định kỳ | Thời gian trực, investigation |
| Reindex/reconciliation | Định kỳ hoặc phát sinh | Sửa lệch, rebuild |
| Decommission/exit | Cuối vòng đời | Xóa dữ liệu, gỡ phụ thuộc |

PoC chạy được vài ngày không chứng minh chi phí bảo trì sẽ thấp trong ba năm.

## 7. Những khoản hạ tầng thường bị quên

Khi lập dự toán cho một NoSQL engine mới, nên xem:

- CPU và RAM thực tế khi peak.
- SSD/HDD, IOPS, throughput và giới hạn volume.
- Secondary indexes, metadata, WAL/log, temporary files.
- Replication factor, multi-zone standby.
- Snapshots/backup retention và dung lượng nhân bản.
- Disk headroom cho failover, rolling upgrade, compaction.
- Network cross-zone, cross-region, egress, private endpoints.
- Load balancers/proxies/gateways.
- Log, metrics, tracing và thời gian retention.
- KMS, secret management và support/license.
- Môi trường integration, staging và disaster recovery.

Giá một node demo thường chưa có **nhiều replica, backup, high availability và quy mô dữ liệu thật**. Số node cần dùng cũng không chỉ phụ thuộc dung lượng mà còn phụ thuộc CPU, I/O và khả năng phân tán traffic.

## 8. Replicas tăng durability, không tự tăng write throughput

Giả sử:

~~~text
Logical data: 100 GB.
Replication factor: 3.
~~~

Kích thước dữ liệu nhân bản ở mức khởi đầu là:

\[
100\times 3=300\ \mathrm{GB}
\]

Chưa bao gồm indexes, transaction logs, storage overhead, snapshots hoặc temporary files.

Ba replicas không có nghĩa write throughput gấp ba; nhiều hệ vẫn phải đi qua primary/leader hoặc phối hợp writes giữa replicas.

Ngoài dung lượng, replication tạo:

- Replication network traffic.
- CPU kiểm tra/apply thay đổi.
- Disk writes bổ sung.
- Replica lag và repair.
- Thời gian failover và rebalancing.

Một thiết kế phục vụ ba availability zones còn có thể phải chịu thêm network/cross-zone cost tùy môi trường và hợp đồng.

## 9. Headroom để hệ còn hoạt động khi lỗi

Một cluster luôn sử dụng 95% disk/CPU có thể gặp sự cố ngay khi:

- Một node hoặc zone hỏng.
- Cần thêm replica mới.
- Compaction hoặc reindex tạm tăng disk.
- Traffic tăng bất thường.
- Phải rolling upgrade.
- Backfill diễn ra cùng lúc live updates.

**Headroom là một yêu cầu khả dụng**, không chỉ là chi phí lãng phí.

Phân biệt hai cách đặt ngân sách:

~~~text
Headroom multiplier 1,30:
  required = used × 1,30

Target utilization tối đa 70%:
  required = used / 0,70
~~~

Hai công thức **không tương đương**. Với 300 GB cần chứa, cách thứ nhất cho 390 GB; cách thứ hai cho khoảng 428,6 GB.

Phải dùng định nghĩa nhất quán khi thẩm định.

## 10. Ví dụ tính capacity theo dữ liệu thật

Giả sử workload (chỉ minh họa):

~~~text
3.000.000 sự kiện/ngày.
0,8 KB dữ liệu logic/event.
Retention 30 ngày.
Index/metadata overhead 60%.
Replication factor = 3.
Headroom multiplier = 1,30.
~~~

Tính theo quy ước GB thập phân và bỏ qua compression:

\[
3\,000\,000\times0{,}8\ \mathrm{KB}=2{,}4\ \mathrm{GB/ngày}
\]

\[
D_{\text{logical}}=2{,}4\times30=72\ \mathrm{GB}
\]

\[
D_{\text{with replicas}}=72\times1{,}6\times3=345{,}6\ \mathrm{GB}
\]

\[
D_{\text{planned}}=345{,}6\times1{,}30=449{,}28\ \mathrm{GB}
\]

Con số này là **ước lượng để lập kế hoạch**, chưa đủ để chọn máy production. Cần đo compression, data distribution, indexes, segments, merge/compaction, I/O và tải truy vấn bằng dữ liệu mẫu thực.

Nếu yêu cầu **disk utilization tối đa 70%**, nên dùng khoảng \(345{,}6/0{,}7\approx493{,}7\) GB thay vì 449,28 GB, và vẫn cần xét các overhead khác.

## 11. Storage growth theo thời gian

Nếu dữ liệu tăng theo tỷ lệ \(g\) mỗi tháng:

\[
D_m=D_0(1+g)^m
\]

Đây là một mô hình giả định, không phải dự báo bảo đảm.

Hai trường hợp khác nhau:

**Dữ liệu giữ vĩnh viễn:**

~~~text
Orders primary store.
Dung lượng tích lũy qua nhiều năm.
~~~

**Dữ liệu có retention rolling:**

~~~text
Search events chỉ giữ 30 ngày.
Dung lượng chủ yếu phụ thuộc lượng event của 30 ngày gần nhất.
~~~

Chi phí snapshot, data archive và restore cũng phụ thuộc retention. Cần xây forecast cho **records, bytes, query QPS, write QPS**, không chỉ tổng records.

## 12. Write amplification khi thêm read model

Một business write có thể thành nhiều thao tác:

~~~text
1. CreateOrder vào MongoDB.
2. Ghi outbox event.
3. Relay đọc event.
4. Gửi đến broker/connector.
5. Ghi index.
6. Replicas index sao chép.
~~~

Như vậy chi phí tăng không chỉ ở query engine mới mà còn ở source, network và pipeline.

\[
\mathrm{WriteAmplification}=
\frac{\text{physical write work}}{\text{logical business writes}}
\]

Physical work có thể đo bằng bytes, disk operations hoặc CPU. **Phải thống nhất đơn vị** khi so sánh.

Read amplification cũng quan trọng: một search call có thể lấy IDs rồi đọc MongoDB để xác minh trạng thái/authorization; tổng số I/O cao hơn so với chỉ search query.

## 13. Network và cross-region costs

Một bản ghi 1 KB có thể di chuyển qua:

~~~text
MongoDB -> CDC -> Broker -> Search primary -> Search replicas
                                  |
                                  -> Snapshot/backup
~~~

Đối với multi-region, có thêm traffic qua vùng, data transfer và backup copies.

Lập **traffic matrix**:

| Nguồn | Đích | Khối lượng | Loại traffic |
|---|---|---|---|
| Source DB | CDC/relay | GB/tháng ước lượng | Change data |
| Relay | Index | GB/tháng ước lượng | Ingest |
| Index primary | Replicas | GB/tháng ước lượng | Replication |
| Index | Backup | GB/tháng ước lượng | Snapshots |
| App | Index | GB/tháng ước lượng | Queries/results |

Đơn giá theo GB có thể thay đổi theo nhà cung cấp, region, loại kết nối và hợp đồng. Dùng **giá/billing hiện hành đã xác minh**, không tự giả định mọi network traffic đều miễn phí.

## 14. Managed và self-hosted: chuyển trách nhiệm, không xóa trách nhiệm

| Tiêu chí | Managed service | Self-hosted |
|---|---|---|
| Khởi tạo | Thường nhanh hơn | Cần automation |
| Giá compute | Có thể kèm premium | Máy chủ có thể rẻ hơn |
| Patching | Nhà cung cấp quản lý một phần | Đội chịu trách nhiệm nhiều hơn |
| Backup/restore | Có tính năng sẵn, vẫn phải thử | Tự thiết kế/vận hành |
| Observability | Có metrics nền tảng | Tự tích hợp phần lớn |
| Customization | Có thể hạn chế | Linh hoạt, nhiều gánh nặng |
| Incident support | Theo gói và SLA thực tế | Chủ yếu đội nội bộ |
| Lock-in | API, cấu hình, pricing | Kiến thức và hạ tầng riêng |

Không thể kết luận managed luôn rẻ hơn hoặc self-hosted luôn rẻ hơn. Phải so **hạ tầng + support + bảo mật + nhân lực + thời gian khôi phục**.

Managed database vẫn không biết business invariant, shard key đúng, code retry hay query nào cần nhất quán. Các trách nhiệm ấy vẫn thuộc về đội xây ứng dụng.

## 15. Chi phí nhân sự và chi phí cơ hội

Một hệ mới cần người:

- Thiết kế schema, partition/index.
- Xây CDC/outbox và các consumers.
- Lập hạ tầng, IAM, TLS, backup.
- Điều chỉnh throughput/query.
- Trực sự cố và kiểm tra độ trễ.
- Vá lỗi, nâng cấp, restore drill.
- Đối soát dữ liệu, xử lý DELETE.
- Hỗ trợ team phát triển sử dụng đúng semantics.

Mô hình đơn giản:

\[
C_{\text{labor}}=
H_{\text{setup}}\times R
+H_{\text{monthly}}\times R\times M
\]

với \(H\) là giờ, \(R\) là fully loaded rate đã thống nhất, \(M\) là số tháng.

Không cộng **lương full-time toàn bộ** rồi cộng thêm **giờ của chính nhân viên đó** nếu hai khoản đo cùng một nguồn lực.

Chi phí cơ hội có thể là tính năng bị trì hoãn, các công việc reliability không được làm hoặc thời gian từ product idea đến production kéo dài.

## 16. On-call và bus factor

Một công nghệ chỉ có một kỹ sư biết debug có thể trở thành rủi ro:

~~~text
Search index lag 25 phút.
Người viết connector đang nghỉ phép.
On-call không biết cách replay event.
Customer support bắt đầu nhận khiếu nại.
~~~

Đặt câu hỏi:

1. Ai là **primary và secondary on-call**?
2. Ai có quyền truy cập production?
3. Có runbook cho backlog, disk full, node fail, restore không?
4. Có escalation/vendor support phù hợp?
5. Có khả năng tạm disable search/fallback không?
6. Đã diễn tập với người **không phải tác giả ban đầu** chưa?

**Thời gian chờ/đào tạo/trực** có chi phí ngay cả trong tháng không có incident.

## 17. Mỗi công nghệ có kỹ năng vận hành riêng

| Engine/loại kho | Những kiến thức cần có |
|---|---|
| Redis | Eviction, persistence, Cluster, hot keys, memory pressure |
| MongoDB | Index, transactions, sharding, replica sets, change streams |
| Cassandra | Partition key, compaction, repair, tombstone, consistency |
| Search engine | Mappings, shards, relevancy, reindex, segments |
| Graph database | Traversal, edge cardinality, query planning |
| Vector database | ANN indexes, recall, embeddings, reindex |
| Object store | Versioning, lifecycle, retention, conditional operations |

Tổng chi phí không chỉ là số chuyên gia phải tuyển mà còn là **tài liệu nội bộ, code review, CI compatibility, diagnostic tooling và support burden** cho các nhóm khác.

Một công nghệ có thể hoàn hảo về performance nhưng chưa phù hợp khi tổ chức không thể đảm bảo vận hành an toàn.

## 18. Data ownership phải rõ trước khi đồng bộ

Kiến trúc:

~~~text
MongoDB orders
Search index orders_search
Redis cache order_summary
~~~

Contract nên là:

~~~text
MongoDB = authoritative source của order status.
Search = projection có thể rebuild.
Redis = cache theo chính sách TTL/invalidation.
~~~

Nếu mỗi service có thể ghi thẳng dữ liệu nghiệp vụ vào cả ba nơi, sẽ khó trả lời:

- Bản nào đúng khi values khác nhau?
- Khi rebuild index, nguồn nào được ưu tiên?
- UPDATE và DELETE được phát từ đâu?
- Có cần transaction trên nhiều hệ không?
- Ai chịu trách nhiệm điều tra discrepancy?

**Một source of truth rõ ràng giảm chi phí đồng bộ** nhưng không tự loại bỏ nhu cầu retry, ordering và data reconciliation.

## 19. Chi phí kết nối nhiều hệ có thể tăng nhanh

Với \(N\) hệ có thể đồng bộ hai chiều tùy ý, số cặp tiềm năng:

\[
\frac{N(N-1)}{2}
\]

Ví dụ 4 hệ có 6 cặp; 5 hệ có 10 cặp. Đây **không phải số connector bắt buộc**, chỉ cho thấy độ phức tạp tiềm năng nếu tích hợp điểm–điểm.

Thường ưu tiên đường có hướng:

~~~mermaid
flowchart LR
    DB["Source of truth"] --> CDC["Outbox / CDC"]
    CDC --> BUS["Relay / Event stream"]
    BUS --> S["Search"]
    BUS --> C["Cache projection"]
    BUS --> A["Analytics"]
~~~

Nhưng mỗi consumer vẫn cần idempotency, versioning, checkpoints, monitoring và xử lý failure.

## 20. Dual-write: rẻ lúc demo, tốn kém khi có lỗi

Ví dụ Java không an toàn đầy đủ:

~~~java
void updateOrder(Order order) {
    mongoRepository.save(order);
    searchRepository.index(order);
}
~~~

Lịch lỗi:

~~~text
MongoDB commit, search timeout.
MongoDB commit, process crash trước index.
Search update v11 đến trước v10.
Search ghi xong nhưng response mất, client retry.
MongoDB rollback còn search đã có dữ liệu.
~~~

Hai lời gọi trong một method **không phải một distributed transaction**.

Nếu search là read model, nên ưu tiên giao thức **có thể replay, tái tạo và đối soát từ nguồn**, chẳng hạn outbox/CDC có consumer idempotent.

## 21. Outbox/CDC giúp tăng reliability nhưng có chi phí

Pattern:

~~~text
DB atomic unit:
  update order
  append outbox event(OrderUpdated, eventId, revision)
COMMIT

Relay:
  read outbox and publish

Consumer:
  apply to index with version guard
  save checkpoint
~~~

Chi phí bổ sung:

- Lưu outbox/change log, write amplification.
- Poller, change stream connector hoặc broker.
- Retry queues, dead-letter handling.
- Consumer deployment/monitoring.
- Event schema evolution.
- Rebuild/reindex và recovery.

Relay có thể gửi event trùng. **Outbox không bảo đảm exactly-once event delivery toàn hệ**; consumer cần xử lý lặp.

Một hệ pipeline tin cậy thường nhiều thành phần hơn một phương án ghi trực tiếp, nhưng tổng chi phí **sự cố và dữ liệu lệch** có thể thấp hơn.

## 22. Event ordering, delete và anti-resurrection

Ví dụ:

~~~text
Source order-101:
  rev 11 = PAID
  rev 12 = DELETED

Consumer xử lý:
  DELETE rev 12
  rồi UPDATE rev 11 đến muộn.
~~~

Nếu consumer chỉ DELETE rồi UPSERT, bản ghi đã xóa có thể **hồi sinh** trong search index.

Projection cần version/tombstone:

~~~text
incomingRevision < currentProjectionRevision
  -> IGNORE_STALE

incomingRevision mới hơn theo contract
  -> apply conditionally
~~~

**So version và apply phải có tính nguyên tử hoặc giao thức tương đương**. Khi DELETE, nếu xóa luôn metadata revision, consumer cần một high-watermark riêng để chặn event cũ.

Chi phí chống bản cũ, xử lý dữ liệu trùng và reconciliation phải được đưa vào bản kế hoạch tích hợp.

## 23. Consistency và độ trễ đồng bộ là một hợp đồng sản phẩm

Ví dụ:

~~~text
10:00:00 MongoDB nhận order mới.
10:00:00 API trả thành công.
10:00:03 Search index mới thấy order.
~~~

Trong 3 giây, tìm kiếm có thể không trả order vừa tạo.

Các câu hỏi:

- Giao diện có cho phép **eventual search** không?
- User cần read-your-writes sau khi tạo hay chỉ sau vài giây?
- Trạng thái thanh toán/tồn kho được phép stale không?
- Khi thu hồi quyền, hệ search có còn trả data nhạy cảm?
- Có cần đọc lại authoritative source để validate kết quả?

Nếu phải verify mỗi search result ở source, chi phí query/network tăng. Nếu không verify, cần guard phù hợp để search projection không trở thành lỗ hổng authorization.

**Không được chỉ đo query latency mà bỏ qua staleness và correctness.**

## 24. Deletion lifecycle tăng theo số nơi có dữ liệu

Một yêu cầu xóa có thể cần tác động:

~~~text
Primary store
Search index
Redis cache
Analytics read model
Object attachments
Backups/snapshots
Offline clients nếu có
~~~

Cần:

1. Xác định scope: hide, soft delete, purge hay erasure.
2. Ghi nhận delete operation và version.
3. Phát DELETE event đáng tin.
4. Consumer xử lý idempotent, không hồi sinh bằng UPDATE cũ.
5. Theo dõi deletion propagation lag.
6. Xác minh data access bị thu hồi đúng.
7. Thực hiện retention/purge theo policy tại từng store.

Copy dữ liệu sang thêm một index có thể làm **data governance khó hơn**. Nên **index ít field nhất đủ cho query**, tránh mang PII không cần thiết vào hệ mới.

## 25. Backup và khả năng khôi phục

Hỏi:

- Hệ mới là nguồn dữ liệu duy nhất hay có thể rebuild?
- Nếu rebuild mất 12 giờ, business có chấp nhận không?
- Có cần snapshot để phục hồi nhanh hơn?
- Snapshot chứa data nhạy cảm và giữ trong bao lâu?
- Có thử restore độc lập với tác giả hệ thống chưa?
- Connector có thể replay những events sau snapshot không?
- Reindex sau restore có xác minh DELETE/version không?

**Rebuildable không đồng nghĩa đáp ứng RTO**. Khả năng tái tạo logic trong một ngày không giúp ích nếu search chỉ được phép gián đoạn một giờ.

## 26. RPO/RTO và disaster recovery

- **RPO:** mức thay đổi/dữ liệu tối đa chấp nhận mất sau sự cố.
- **RTO:** thời gian mục tiêu để dịch vụ được phục hồi.

Ví dụ:

~~~text
MongoDB primary orders:
  RPO nghiêm ngặt, RTO 30 phút.

Search read model:
  có thể rebuild từ source và log
  RTO mục tiêu 4 giờ.
~~~

Để đạt RTO search 4 giờ có thể cần snapshot, parallel reindex, headroom và event log retention đủ dài.

Nếu business chấp nhận search temporarily unavailable và có source fallback, chi phí DR có thể giảm. Nhưng đường fallback phải được load test, không chỉ mô tả trong sơ đồ.

## 27. Availability của dependency mới

Một request bắt buộc cả MongoDB và search phải hoạt động sẽ có failure modes của cả hai.

Nếu **giả định độc lập** và mỗi hệ đạt 99,9% availability:

\[
A_{\text{joint}}=0{,}999\times0{,}999=0{,}998001
\]

tức khoảng **99,8001%** cho đường bắt buộc cả hai theo mô hình đơn giản.

Đây không phải dự báo production: failures có thể tương quan, có retries/fallback và các SLA không độc lập.

Bài học là **không đặt dependency phụ lên critical write path nếu nghiệp vụ không yêu cầu**:

~~~text
CreateOrder:
  commit source -> return success
  index async
~~~

Thiết kế này bảo vệ critical path tốt hơn nhưng phải chấp nhận và quản lý indexing lag.

## 28. Blast radius và fallback

Redis down có thể khiến tất cả cache misses quay về MongoDB, làm source quá tải. Search index down có thể khiến API retry vô hạn, giữ hết threads/connections.

Cần:

- Timeout và deadline propagation.
- Bounded retries, backoff, jitter.
- Circuit breakers và bulkhead isolation.
- Rate limiting/load shedding.
- Cache stampede prevention.
- Degraded mode/fallback.
- Queue/backpressure để tránh CDC overload source.

Thêm công nghệ mà không có failure isolation có thể **làm một sự cố phụ lan sang hệ nghiệp vụ chính**.

## 29. Observability cho đường dữ liệu mới

| Metric | Câu hỏi |
|---|---|
| Search p95/p99 | Có đạt mục tiêu UX? |
| Indexing lag p99 | Dữ liệu chậm bao lâu? |
| Change log/outbox backlog | Có bị kẹt và mất khả năng bắt kịp? |
| Dead-letter count | Event nào bị lỗi? |
| Source/index version mismatch | Dữ liệu có lệch? |
| Delete propagation lag | Có xóa đúng? |
| Heap/CPU/IO/disk watermark | Cluster sắp bão hòa? |
| Cache hit/miss ratio | Cache có tạo lợi ích? |
| Fallback rate | Phụ thuộc mới có không ổn định? |
| Replica health/recovery time | Failover/rebuild có đáp ứng SLO? |
| Cost per indexed event/query | Hiệu quả kinh tế có duy trì? |

Không tạo một metric label cho từng orderId nếu cardinality quá lớn. Dùng tracing/logs được kiểm soát, sampling hoặc aggregated metrics.

**Thêm alert còn kéo theo công việc tuning để tránh alert fatigue** và xây runbooks để người trực biết cách xử lý.

## 30. Kiểm thử tích hợp phải bao phủ lịch lỗi

Một số trường hợp:

~~~text
Primary DB commit, index lỗi.
Event v12 đến trước v11.
DELETE đến trước UPDATE cũ.
Consumer crash sau apply trước checkpoint.
Snapshot restore nhưng thiếu change log.
Reindex đang chạy, live writes vẫn tiếp tục.
One node down khi peak traffic.
Network partition giữa source và index.
~~~

Cần test:

- Contract và schema versions.
- Idempotency, ordering, conflict handling.
- Failure injection.
- Backfill/reindex và partial success.
- Restore drills.
- Load/soak tests.
- Authorization/deletion propagation.

Đội không nên kết luận “ổn định” chỉ vì các happy-path integration tests đều xanh.

## 31. Reconciliation là công việc vận hành thật

Index có thể lệch source do event missing, mapping mismatch, consumer crash hoặc out-of-order updates.

Một reconciliation job:

~~~text
Chọn tập order IDs/versions từ source.
Đọc IDs/versions trong search.
So missing, stale, extra records.
Reindex/correct có idempotency.
Ghi metrics và audit.
~~~

Nếu source và index không có chung version/identity, rất khó chứng minh record nào cần sửa.

Reconciliation có thể tạo tải lớn cho source, nên phải có **partition/range, throttling và checkpoint**. Nếu không thể phục hồi tự động sau vài ngày pipeline lỗi, chi phí support và incident có thể vượt chi phí node rất xa.

## 32. Backfill và reindex là giai đoạn tốn tài nguyên

Giả sử cần index 200 triệu orders trước khi tính năng mới go-live.

Quy trình:

1. Chọn source snapshot/change cursor.
2. Scan theo phân vùng có rate limit.
3. Transform sang schema index.
4. Bulk write với kiểm tra partial failures.
5. Catch-up những thay đổi sau snapshot.
6. Verify records/versions, nhất là DELETE.
7. Canary và cutover traffic.
8. Giữ đường rollback nếu fail.

Không được để backfill gây quá tải nguồn đang phục vụ giao dịch.

Khi mapping index thay đổi, có thể phải xây **index mới song song index cũ**, cần thêm storage và compute tạm. Chi phí này dễ bị bỏ quên khi chỉ đo steady-state ingestion.

## 33. Nâng cấp và dependency management

Một Java service dùng nhiều hệ có thể cần:

~~~text
Java runtime
MongoDB driver
Search Java client
CDC connector
Broker client
Search engine server version
TLS/auth libraries
~~~

Nâng cấp một thành phần có thể ảnh hưởng mapping, serialization, query DSL, wire protocol, certificates, snapshots và consumer schema.

Nên tính:

- Compatibility tests trong CI.
- Staging gần production.
- Rolling upgrade/rollback.
- Release monitoring.
- CVE patch windows.
- Maintenance và version support.

Một technology không được bảo trì đúng hạn có **security risk**; trì hoãn nâng cấp không làm chi phí biến mất.

## 34. Security và data minimization

Mỗi store mới có endpoints, IAM, credentials, encryption và audit riêng.

Một order document có thể chứa:

~~~json
{
  "orderId": "order-101",
  "tenantId": "shop-a",
  "status": "PAID",
  "shippingAddress": "...",
  "phone": "...",
  "internalNote": "..."
}
~~~

Nếu index chỉ phục vụ tìm theo ID, status và thời gian, không cần copy toàn bộ fields nhạy cảm:

~~~json
{
  "orderId": "order-101",
  "tenantId": "shop-a",
  "status": "PAID",
  "createdAt": "2026-11-14T09:00:00Z"
}
~~~

Data minimization giảm **lưu trữ, network, exposure khi incident và công việc deletion**.

Không để hệ search phục vụ kết quả của tenant khác chỉ vì query thiếu tenant filter. Quyền truy cập phải được kiểm chứng bằng nguồn/policy đáng tin.

## 35. Compliance và dữ liệu có nhiều bản

Một hệ đã đáp ứng encryption/audit trong MongoDB không có nghĩa search cluster mới tự thừa hưởng các control đó.

Kiểm tra:

- Phân loại dữ liệu và data residency.
- Encryption at rest/in transit.
- RBAC/ACL theo tenant.
- Secret rotation và privilege minimization.
- Audit logs, export controls.
- Retention, backups và data erasure.
- Subprocessor/vendor contract nếu có.
- Quy trình sự cố bảo mật.

**Số bản sao dữ liệu nhạy cảm tăng có thể tăng chi phí quản trị**, ngay cả khi kích thước dữ liệu không đáng kể.

## 36. Cost attribution và báo cáo hàng tháng

Ở nơi platform hỗ trợ cost tags:

~~~yaml
application: orders
environment: production
component: search-index
owner: order-platform
costCenter: commerce
~~~

Theo dõi:

- Compute vs storage vs network vs backup.
- Chi phí per query/per indexed event.
- Tăng trưởng dữ liệu.
- Tải idle so với peak.
- Khoản phát sinh khi reindex/restore.
- Anomalies và budget alerts.
- Chi phí phục vụ một tenant/workload, nếu đo hợp lý.

Không lấy hóa đơn toàn tài khoản chia bình quân để kết luận một engine rẻ; cần phân bổ incremental costs có căn cứ.

## 37. Ví dụ TCO ba năm: phương án A và B

Các con số tiếp theo là **giả định giáo dục**, không phải báo giá của bất kỳ cloud provider nào.

**Phương án A:** tối ưu MongoDB (indexes, pagination, read model nhỏ trong cùng engine).

**Phương án B:** giữ MongoDB và thêm search cluster riêng cùng outbox/CDC, monitoring, HA, backup, on-call.

Khung so sánh: 36 tháng, fully loaded engineering rate giả định 50 USD/giờ.

### Chi phí ban đầu của B

| Hạng mục | Giờ | Giá/giờ | Chi phí |
|---|---:|---:|---:|
| Khảo sát, kiến trúc, PoC | 100 | 50 USD | 5.000 USD |
| Outbox/CDC và integration | 240 | 50 USD | 12.000 USD |
| Security, DR, runbook | 80 | 50 USD | 4.000 USD |
| Migration/backfill | 120 | 50 USD | 6.000 USD |
| **Tổng** | **540** | | **27.000 USD** |

### Chi phí định kỳ của B

| Hạng mục | USD/tháng |
|---|---:|
| Compute/storage | 1.600 |
| Backup/network | 400 |
| Observability/license/support | 300 |
| Ops: 28 giờ × 50 USD | 1.400 |
| Incident work kỳ vọng: 6 giờ × 50 USD | 300 |
| **Tổng** | **4.000** |

\[
\mathrm{TCO}_{B,\text{base}}
=27\,000+36\times4\,000=171\,000\ \mathrm{USD}
\]

Nếu dùng **15% scenario reserve** trên base (chỉ là dự phòng ngân sách, chưa phải chi phí đã phát sinh):

\[
171\,000\times1{,}15=196\,650\ \mathrm{USD}
\]

Phương án A giả định:

~~~text
Setup: 8.000 USD.
Monthly incremental cost: 1.700 USD.
~~~

\[
\mathrm{TCO}_{A}=8\,000+36\times1\,700
=69\,200\ \mathrm{USD}
\]

Chênh lệch giữa B có scenario reserve và A base:

\[
196\,650-69\,200=127\,450\ \mathrm{USD}
\]

**127.450 USD chưa tự là “đắt” hay “rẻ”**. Nó là mức chi phí tăng thêm giả định để so với giá trị, rủi ro và lợi ích của hai phương án, cần ghi rõ rằng A chưa áp cùng một reserve.

Không tiếp tục cộng một khoản “incident work” thứ hai nếu 300 USD/tháng đã đại diện cho cùng chi phí; risk reserve cần phạm vi rõ để tránh double count.

## 38. Giá trị nghiệp vụ và break-even

Giả sử B có thể tạo thêm **210.000 USD giá trị** so với A trong ba năm, theo một giả thuyết chưa được xác thực.

\[
\operatorname{NetBenefit}_{B-A}
\approx210\,000-127\,450
=82\,550\ \mathrm{USD}
\]

Điều này chỉ có ý nghĩa nếu:

- Giá trị là **incremental so với A**, không phải toàn bộ doanh thu tính năng search.
- Dữ liệu được xác minh bằng experiment/usage/cost avoidance.
- Không double count conversion gains và productivity gains.
- Đã xét risk của downtime/data issues.
- Growth/pricing và thời gian phát sinh lợi ích được tính hợp lý.

Break-even nên được diễn đạt thành **ngưỡng đo được**, ví dụ tăng conversion bao nhiêu phần trăm hoặc bao nhiêu query workload thì B có lợi hơn A.

Nếu B chỉ có lời trong kịch bản quá lạc quan, quyết định nên được xem xét lại hoặc pilot để giảm độ bất định.

## 39. Chiết khấu dòng tiền và NPV

Với quyết định kéo dài nhiều năm, có thể dùng:

\[
\operatorname{NPV}
=-C_0+\sum_{t=1}^{T}
\frac{B_t-C_t}{(1+r)^t}
\]

Trong đó \(C_0\) là setup cost, \(B_t\) là lợi ích tăng thêm kỳ \(t\), \(C_t\) là chi phí kỳ \(t\), \(r\) là tỷ lệ chiết khấu **cùng đơn vị kỳ**.

Nếu dùng tháng, cần chuyển tỷ lệ năm thành tỷ lệ tháng theo quy tắc tài chính nhất quán.

Không nên coi NPV chính xác tới đồng cuối cùng nếu assumptions về adoption, cloud pricing, staffing và growth còn rất thiếu chắc chắn.

## 40. Phân tích độ nhạy và ba kịch bản

| Biến | Kịch bản tốt | Cơ sở | Xấu |
|---|---|---|---|
| Data growth | Chậm | Theo forecast | Gấp đôi |
| Index overhead | Thấp | Theo benchmark | Tăng mạnh |
| Ops hours | Ít | Bình thường | Nhiều incident |
| Reindex frequency | Hiếm | Định kỳ | Liên tục |
| Business adoption | Cao | Dự kiến | Thấp |
| Query SLO | Có headroom | Vừa đạt | Không đạt |

Cần xác định biến nào ảnh hưởng TCO nhiều nhất và **dùng PoC để giảm bất định đó**.

Ví dụ nếu index size chiếm phần lớn chi phí, ưu tiên benchmark với dữ liệu thật và mapping thực. Nếu chi phí con người là yếu tố chính, cần thử vận hành và kiểm tra năng lực on-call.

## 41. Rủi ro downtime và sai dữ liệu

Một mô hình lượng hóa đơn giản:

\[
\operatorname{ExpectedLoss}
=\sum_i P_i\times I_i
\]

với \(P_i\) là xác suất sự cố loại \(i\), \(I_i\) là mức thiệt hại.

Những rủi ro:

- Search down làm giảm conversion.
- Index stale hiển thị trạng thái order sai.
- DELETE không propagate gây lộ dữ liệu.
- Backfill làm chậm CreateOrder.
- Vendor outage hoặc pricing changes.
- Không thể restore trong RTO.

Xác suất có thể thiếu dữ liệu và chỉ là giả định. Những yêu cầu như **không lộ dữ liệu tenant khác** là hard constraints, không thể “bù” bằng điểm hiệu năng hoặc expected loss nhỏ.

## 42. Hard gates trước weighted scoring

Phân loại tiêu chí:

**Hard gates:**

- Data residency/compliance.
- Authorization/tenant isolation.
- Recovery tối thiểu.
- Business correctness.
- Security support và ownership bắt buộc.

**Optimization criteria:**

- Latency, throughput.
- Developer ergonomics.
- Features.
- TCO và portability.

Một công nghệ có p99 xuất sắc nhưng không đáp ứng data residency **không đủ điều kiện**, dù tổng điểm đánh giá cao.

## 43. Ma trận quyết định có trọng số

Sau khi vượt hard gates:

| Tiêu chí | Trọng số ví dụ | A: tối ưu hiện tại | B: kho mới |
|---|---:|---:|---:|
| Query SLO | 25% | 3/5 | 5/5 |
| Tính năng chuyên biệt | 20% | 2/5 | 5/5 |
| Incremental TCO | 20% | 5/5 | 2/5 |
| Ops readiness | 15% | 5/5 | 2/5 |
| Recovery/consistency | 10% | 4/5 | 3/5 |
| Exit/portability | 10% | 4/5 | 2/5 |

Điểm và trọng số chỉ minh họa. Chúng giúp làm rõ đánh đổi, không thay benchmark và risk review.

Nếu một mục Ops readiness thấp, có thể cải thiện bằng tuyển người hoặc đào tạo; **chi phí cải thiện đó phải có trong TCO**.

## 44. So sánh ít nhất hai phương án thay thế

Các lựa chọn điển hình:

1. Tối ưu query/index/partition của engine hiện tại.
2. Tạo read model trong cùng loại database.
3. Thêm cache với TTL/invalidation.
4. Thêm search/index chuyên biệt.
5. Đổi schema/shard key và query design.
6. Dùng managed feature hoặc managed specialized service.
7. Điều chỉnh UX, filter scope hoặc precomputation.

Phải benchmark trên **cùng dataset/workload** và yêu cầu tính đúng. Không so cấu hình B được tuning kỹ với A chưa có index cần thiết.

## 45. Khi nào Redis cache có giá trị?

Redis phù hợp khi:

- Tải read lặp lại cao, cache hit ratio có ý nghĩa.
- Data dễ cache và chấp nhận TTL/staleness.
- Có fallback kiểm soát khi Redis down.
- Cache không được dùng làm authoritative state cho nghiệp vụ cần consistency mạnh.

Chi phí ẩn:

- Cache invalidation.
- Cache cold start.
- Eviction và hot keys.
- Memory headroom.
- Cache stampede khi TTL hết.
- Network request bổ sung.
- Data duplication và encryption/ACL.

Nếu chỉ cache một query hiếm, chi phí vận hành có thể lớn hơn tiết kiệm tài nguyên.

## 46. Khi nào search engine chuyên biệt có giá trị?

Thường phù hợp nếu:

- Cần full-text, ranking, stemming, facets, autocomplete.
- Nhiều dạng truy vấn khó đạt SLO trên source giao dịch.
- Product value từ search đã được chứng minh.
- Chấp nhận một read model eventual hoặc có consistency workaround hợp lý.

Chi phí đặc thù:

- Index mappings, shard/replica sizing.
- Search relevancy testing.
- Index rebuild và shadow aliases.
- CDC, ordering, DELETE handling.
- Heap/disk pressure, segment merges.
- Query client/DSL lock-in.

Nếu query chủ yếu theo **tenantId + status + createdAt**, một compound index trong MongoDB có thể là phương án rẻ và dễ vận hành hơn.

## 47. Khi nào Cassandra/wide-column store phù hợp?

Một workload có rất nhiều time-series events, writes lớn và truy vấn theo partition key định trước có thể phù hợp với Cassandra.

Tuy nhiên chi phí vận hành gồm:

- Data modeling theo query.
- Partition/bucket design.
- Repair, compaction, tombstones.
- Consistency level và LWT semantics.
- Multi-datacenter replication.
- Query limitations, data duplication.
- On-call skills riêng.

Không nên thêm Cassandra chỉ vì “ghi nhanh” nếu workload thực tế nhỏ hoặc thường xuyên cần ad-hoc joins/truy vấn không theo partition key.

## 48. Graph và vector stores cũng có TCO riêng

Graph store:

- Edge/node synchronization.
- Traversal planning và high-degree nodes.
- Relationship deletion/uniqueness.
- Capacity và query diagnostics.

Vector store:

- Embedding generation/inference cost.
- Re-embedding khi model thay đổi.
- ANN recall/latency tradeoff.
- Index lifecycle và rebuild.
- Metadata filters/tenant isolation.
- Xóa dữ liệu cá nhân/embeddings.

**Chi phí model inference hoặc graph materialization có thể vượt storage invoice**. Phải đánh giá trọn pipeline, không chỉ giá một GB trong engine.

## 49. TCO của sự phức tạp tổ chức

Một tổ chức có thể dùng:

~~~text
MongoDB cho orders.
Redis cho cache.
Cassandra cho events.
Search engine cho search.
Vector store cho recommendations.
Graph store cho relations.
~~~

Từng lựa chọn có thể hợp lý, nhưng tập hợp đó tạo:

- Nhiều IAM/security models.
- Nhiều backup và restore playbooks.
- Nhiều libraries/drivers.
- Nhiều lộ trình nâng cấp.
- Nhiều connectors và change schemas.
- Nhiều chi phí billing/vendor support.

Đây là **technology sprawl**. Không phải lúc nào ít công nghệ cũng tốt hơn, nhưng một công nghệ chỉ phục vụ một nhu cầu nhỏ phải tạo giá trị đủ lớn để bù phần tăng phức tạp của tổ chức.

## 50. Architecture Decision Record (ADR)

Một ADR có thể có cấu trúc:

~~~markdown
# ADR-012: Thêm kho tìm kiếm cho orders

## Bối cảnh
- Query problems và baseline p99
- Data volume, retention và forecast
- Business requirement

## Phương án
- A: tối ưu MongoDB
- B: MongoDB + Search
- C: Redis cache/read model

## Hard constraints
- Tenant isolation, privacy, RTO/RPO
- Freshness, correctness, authorization

## Bằng chứng
- Query plan, benchmark, PoC
- Backfill/rebuild và failure tests
- Incremental 36-month TCO

## Quyết định
- Chọn phương án và lý do
- Các phương án bị loại và lý do

## Hệ quả và trách nhiệm
- Source of truth, on-call, SLO
- CDC, deletes, reconciliation
- Rollback/exit, review date
~~~

ADR không phải quảng cáo công nghệ mà là **tài liệu ghi các assumptions, bằng chứng và đánh đổi đã được chấp nhận**.

## 51. Proof of Concept phải đo nhiều hơn tốc độ một query

Một PoC hữu ích nên đo:

1. Query p50/p95/p99 với data shape thật.
2. Throughput ở peak và tăng trưởng dự báo.
3. Ingest/index lag cho create/update/delete.
4. Physical index size, CPU, RAM, I/O, network.
5. Backfill và reindex time.
6. Failover khi mất node.
7. Consumer restart/redelivery/out-of-order.
8. Restore/rebuild theo RTO.
9. Cost per indexed event và per query.
10. Khả năng on-call tự xử lý sự cố giả lập.

PoC chạy một giờ không đủ để đo GC/compaction, rolling upgrade, long retention hoặc chi phí khi cluster bị mất node. Cần thử **soak test** khi các rủi ro đó có ý nghĩa.

## 52. Pilot và rollout có kiểm soát

~~~mermaid
flowchart TD
    A["Đo baseline và yêu cầu"] --> B["PoC dữ liệu đại diện"]
    B --> C["TCO + Ops/Security review"]
    C --> D["Shadow indexing"]
    D --> E["Reconciliation + fault tests"]
    E --> F["Canary một phần read traffic"]
    F --> G["So SLO, cost, correctness"]
    G --> H{"Đạt gates?"}
    H -->|"Có"| I["Tăng dần traffic"]
    H -->|"Không"| J["Rollback / redesign"]
~~~

Trong **shadow indexing**, hệ mới nhận dữ liệu nhưng chưa quyết định kết quả hiển thị cho user. Có thể so records, revisions, DELETE propagation và latency với source.

Chỉ tăng traffic khi đã xác minh correctness và recovery, không chỉ dựa trên query p99.

## 53. Rollback không chỉ là một feature flag

Đưa read traffic về đường cũ có thể cần feature flag, nhưng sau rollback còn:

- Outbox/CDC events đang phát.
- Ingestion jobs và backfill.
- Nodes/volumes/snapshots đang bị tính tiền.
- Credentials và network policies.
- Monitoring/alerts/on-call.
- Dữ liệu index cần purge theo policy.
- Source indexes hoặc schema mới.

Kế hoạch rollback:

1. Switch traffic an toàn về source/fallback.
2. Pause pipeline có kiểm soát.
3. Verify primary business paths không bị ảnh hưởng.
4. Giữ điều tra nếu cần, hoặc chuẩn bị decommission.
5. Xóa data/secrets theo quy trình.
6. Xác nhận dừng chi phí.

Không xóa một cluster chỉ vì tưởng nó là cache khi chưa xác minh nó không chứa dữ liệu authoritative.

## 54. Exit plan nên tồn tại từ ngày đầu

Một công nghệ có thể cần bị bỏ vì giá tăng, team thiếu năng lực, workload không đạt dự báo hoặc vendor thay support.

Exit plan nên chỉ rõ:

- Source authoritative còn đầy đủ để rebuild.
- Có export/backup và khả năng chuyển.
- API dùng business abstraction vừa đủ.
- Có thể chạy hai read models song song để so.
- Có cutover, rollback và verification.
- Có delete/retention/credential revocation.
- Có thể gỡ connector và ngừng billing.

**Lock-in không chỉ đến từ vendor**. Query DSL, data model, team skills và pipeline riêng cũng tạo chi phí thay đổi.

## 55. Trừu tượng hóa đúng mức để giảm exit cost

Một generic interface:

~~~java
interface Database {
    Object execute(String arbitraryQuery);
}
~~~

có thể che giấu những khác biệt thật sự về transactions, consistency, routing và query semantics.

Tốt hơn là biểu diễn mục tiêu nghiệp vụ:

~~~java
public interface OrderSearch {
    SearchPage searchOrders(
        OrderSearchCriteria criteria,
        SearchCursor cursor
    );
}

public interface OrderRepository {
    Order findAuthoritativeById(
        TenantId tenantId,
        OrderId orderId
    );
}
~~~

Hai interfaces tách rõ **read model search** với **nguồn dữ liệu giao dịch**. Nếu đổi search engine, adapter mới có thể giữ business API, còn contract về freshness/consistency phải được kiểm tra lại.

## 56. Dữ liệu và tài liệu cần mang vào design review

| Đầu vào | Nguồn | Người xác nhận |
|---|---|---|
| Workload QPS/peak | Production metrics | Backend |
| Query shapes/plans | Slow queries/explain | DBA |
| Dataset/retention | Data profiling | Data owner |
| Index bytes/CPU | Benchmark | Platform |
| Cloud pricing | Billing/báo giá hợp lệ | FinOps |
| Setup/ops hours | Task estimates/on-call | Engineering lead |
| Security gates | Threat model/review | Security |
| DR/RPO/RTO | Recovery tests | SRE |
| Value assumptions | Product experiment | Product |
| Exit/decommission | ADR/runbook | Architecture |

Mỗi giả định nên có **đơn vị, nguồn, mức tin cậy, owner và ngày xem lại**. Không dùng giá không rõ region hay benchmark trên laptop làm dữ liệu chốt chi phí production.

## 57. Khi nào nên **chưa** thêm công nghệ?

- Chưa đo baseline và query plan của hệ hiện tại.
- Lợi ích chỉ đến từ một demo nhỏ.
- Không có owner/on-call.
- Chưa rõ data authority và DELETE path.
- Không có cách rebuild trong RTO.
- Security/data residency chưa đạt.
- TCO tăng mạnh trong khi business value chưa chứng minh.
- PoC không có failure/restore test.
- Có lựa chọn tối ưu hệ hiện tại rẻ hơn rõ rệt.

**“Chưa thêm” là một quyết định có thể rất đúng**, nhất là khi đặt được trigger xem xét lại, ví dụ QPS đạt ngưỡng hoặc product chính thức cần một dạng tìm kiếm hiện engine không đáp ứng.

## 58. Khi nào nên chấp nhận chi phí thêm?

- Workload có nhu cầu chuyên biệt và đã có benchmark.
- Lợi ích nghiệp vụ tăng thêm đo được.
- Hệ hiện tại không đạt SLO sau tối ưu hợp lý.
- Có source of truth, replay/rebuild, consistency contract.
- Security và DR đạt hard requirements.
- Có người vận hành và on-call.
- Incremental TCO và scenarios ở mức chấp nhận được.
- Có pilot, rollback và exit plan.

Quyết định tốt không tối ưu **số database ít nhất** hay **query nhanh nhất**, mà tối ưu toàn bộ hệ thống theo mục tiêu, ràng buộc và năng lực thực tế.

## 59. Những hiểu nhầm phổ biến

| Hiểu nhầm | Vì sao sai | Cách suy luận đúng |
|---|---|---|
| “Một node 100 USD/tháng là đủ” | Thiếu HA, backup, network, staging | Production topology TCO |
| “Open-source thì miễn phí” | Ops, support, patching vẫn tốn | License + infrastructure + people |
| “Managed không cần SRE” | App, query, data semantics vẫn do đội chịu trách nhiệm | Shared responsibility |
| “Replicas tăng throughput ghi gấp bội” | Ghi vẫn cần coordination/primary tùy engine | Benchmark read/write riêng |
| “Payload bytes bằng storage cần dùng” | Index/replica/log/overhead/headroom | Capacity model và test |
| “PoC một query nhanh là đủ” | Thiếu real data, failures, recovery | Representative PoC |
| “Dual-write Java method là atomic” | Hai commits độc lập | Outbox/transaction boundary |
| “Event bus không giao trùng” | Retry/redelivery xảy ra | Idempotent consumers |
| “Search có thể rebuild nên không cần DR” | Rebuild có thể lâu hơn RTO | Test recovery time |
| “DELETE source là search đã xóa” | Lag, missed events, stale writes | Tombstones/version guards |
| “Cloud bill là toàn bộ TCO” | On-call, development, security, migration | Incremental lifecycle costs |
| “Toàn bộ MongoDB cost thuộc search project” | MongoDB vẫn có ở baseline | Differential TCO |
| “Redis luôn giảm chi phí” | Invalidation và fallback có thể đắt | Hit ratio, stampede risk |
| “Có data copy thì có nhiều source of truth” | Phụ thuộc quyền ghi | Explicit authority/projections |
| “Giảm p99 là đủ” | Có thể tăng data corruption/cost | SLO + correctness + TCO |
| “Không có incident, on-call cost bằng 0” | Training/drills và readiness vẫn có giá | Recurring ops cost |
| “Giá hiện tại nhân 36 là dự báo chính xác” | Growth/pricing/risk thay đổi | Sensitivity/scenarios |
| “Hai hệ 99,9%, API chắc vẫn 99,9%” | Nếu cần cả hai, failure paths tăng | Dependency model |
| “Tối ưu source DB là không làm gì” | Vẫn có chi phí phát triển | Tính chi phí A |
| “Có feature flag tức có rollback hoàn chỉnh” | Pipeline, data, secrets, billing còn | Full rollback plan |
| “ADR chỉ cần ghi lựa chọn” | Không biết assumptions và alternatives | Evidence và decision triggers |
| “Lock-in chỉ là vendor” | Query DSL, schema, team skills cũng ràng buộc | Exit/portability |
| “Điểm tổng cao có thể bù vi phạm bảo mật” | Hard gate không được đánh đổi | Chặn trước scoring |

## 60. Bài tập thực hành

### Bài tập 1 — Chẩn đoán trước khi thêm database

Search API p99 là 2,4 giây nhưng 92% endpoint khác đạt SLO. Nêu năm phép đo/kiểm tra cần làm trước khi kết luận phải thêm search engine.

### Bài tập 2 — Incremental cost

MongoDB hiện tốn 5.000 USD/tháng ở mọi phương án. A tối ưu index thêm 700 USD/tháng. B thêm search 2.500 USD/tháng và làm MongoDB tăng thêm 300 USD/tháng. Tính chênh lệch chi phí định kỳ B–A và giải thích vì sao không phân bổ nguyên 5.000 USD riêng cho B.

### Bài tập 3 — TCO

Setup 200 giờ × 60 USD/giờ; infra 1.000 USD/tháng; ops 20 giờ/tháng × 60 USD/giờ; 24 tháng. Tính TCO và phân biệt cash cost với allocated engineering capacity.

### Bài tập 4 — Capacity model

2 triệu events/ngày, 1 KB/event, retention 45 ngày, index overhead 50%, replication factor 3, headroom multiplier 1,25. Ước lượng dung lượng theo GB thập phân và liệt kê overhead chưa tính.

### Bài tập 5 — Headroom

Dung lượng sau replica/index overhead là 600 GB. Tính capacity theo cách nhân 1,3 và theo target disk utilization 70%. Giải thích sự khác nhau.

### Bài tập 6 — Tính đúng và search freshness

Product yêu cầu tìm thấy order mới trong một giây, nhưng CDC lag p99 là 5 giây. Đề xuất các lựa chọn và chi phí của từng lựa chọn.

### Bài tập 7 — Out-of-order DELETE

Source đã xóa order-101 ở rev12, consumer nhận Delete rev12 rồi Update rev11. Thiết kế guard ngăn resurrection và nêu chỗ lưu revision metadata.

### Bài tập 8 — Transactional outbox

Service ghi MongoDB rồi crash trước index. Thiết kế outbox/CDC, relay retries, idempotent consumer và dashboard backlog; nêu các thành phần tạo thêm cost.

### Bài tập 9 — Backfill 200 triệu records

Thiết kế snapshot cursor, rate limit, live event catch-up, reconciliation, canary và rollback mà không làm CreateOrder vượt SLO.

### Bài tập 10 — Cache hit ratio

Một API có 100.000 reads/phút; cache hit ratio dự kiến 85%. Ước tính số source reads tránh được trong mô hình lý tưởng và nêu những điều có thể làm kết quả thấp hơn.

### Bài tập 11 — Redis down

Khi Redis mất kết nối, tất cả requests fallback MongoDB. Thiết kế circuit breaker, TTL jitter, coalescing và load shedding để ngăn outage lan rộng.

### Bài tập 12 — Managed vs self-hosted

Managed tốn 2.000 USD/tháng, tiết kiệm 30 giờ vận hành; self-hosted tốn 1.100 USD/tháng và yêu cầu thêm 30 giờ ở 60 USD/giờ. So đơn giản và nêu rủi ro ngoài chi phí.

### Bài tập 13 — On-call readiness

Team backend muốn thêm Cassandra, team platform chưa biết Cassandra. Viết kế hoạch đào tạo, support, repair drills, runbook và go-live gate.

### Bài tập 14 — RTO

Search index rebuild mất 10 giờ, SLO business chỉ cho unavailable 2 giờ. Đề xuất snapshot/restore, parallel rebuild hoặc degraded mode, kèm cost.

### Bài tập 15 — Availability

Hai dependencies có giả định độc lập 99,9% và đều bắt buộc trong một request. Tính mô hình joint availability và giải thích giới hạn giả định.

### Bài tập 16 — Security

Một team muốn index toàn bộ order document gồm điện thoại và địa chỉ. Thiết kế data minimization, tenant isolation, encryption, access audit và deletion policy.

### Bài tập 17 — Network costs

Vẽ traffic matrix của source, CDC, broker, search primary, replicas, backup và app clients. Phân biệt dữ liệu logic và traffic vật lý.

### Bài tập 18 — Chi phí cơ hội

Ba engineers dành sáu tuần tích hợp search thay vì xây feature tăng doanh thu. Viết cách trình bày opportunity cost không double count lương.

### Bài tập 19 — Sensitivity analysis

Lập ba scenarios về storage/index overhead, growth, incidents và adoption; chỉ ra biến gây thay đổi TCO lớn nhất và phép thử cần thiết.

### Bài tập 20 — ADR

Viết ADR so MongoDB indexes, Redis cache và search engine mới; bao gồm hard gates, workload, incremental TCO, risks, decision, owner, review date và exit.

### Bài tập 21 — Vector store

Nhóm đề xuất vector DB cho recommendations nhưng chưa đo recall/latency, embedding cost hoặc re-embedding. Lập PoC và cost model.

### Bài tập 22 — Reindex

Search mapping mới cần tạo index song song trong khi disk chỉ đủ cho index cũ. Thiết kế temporary capacity, backfill, version check, cutover và cleanup.

### Bài tập 23 — Tenant fairness

Một tenant tạo 70% indexing writes. Thiết kế rate limits, resource isolation, budget attribution và cách bảo vệ tenant nhỏ.

### Bài tập 24 — Reconciliation

Source có 1 triệu records, index thiếu 500 và còn 30 records đã DELETE. Thiết kế đối soát, idempotent repair và cách giới hạn tải lên source.

### Bài tập 25 — Rollback

Sau ba tháng, search engine không đạt yêu cầu. Viết kế hoạch đưa traffic về MongoDB, dừng pipeline, xóa dữ liệu, thu hồi secrets, tắt billing và cập nhật ADR.

### Bài tập 26 — Business value

Incremental TCO của B thêm 120.000 USD trong ba năm; product dự đoán tạo 180.000 USD giá trị. Bạn sẽ yêu cầu bằng chứng gì trước khi quyết định?

### Bài tập 27 — Fault injection

Tạo test plan cho source outage, CDC crash, out-of-order DELETE, search disk full, reindex giữa live traffic và backup restore. Nêu invariants, metrics và rollback triggers.

### Bài tập 28 — Design review tổng hợp

Hệ đang dùng MongoDB, Redis và object store; đội muốn thêm search cluster cùng một broker chỉ để phục vụ 5% read traffic. Hãy xây đề xuất gồm:

1. Baseline và alternatives.
2. Data model/source authority.
3. Query SLO, freshness, security.
4. Integration/CDC/outbox/inbox.
5. Capacity, replication, network, backup.
6. TCO 36 tháng với ba scenarios.
7. Business benefit và hard constraints.
8. On-call, runbook, restore drill.
9. PoC/pilot/canary/rollback gates.
10. Exit plan và ngày đánh giá lại.

Không được trả lời chỉ bằng **giá thuê search nodes**: yếu tố khó nằm ở **dữ liệu đi vào/ra công nghệ mới, khả năng phục hồi và người chịu trách nhiệm khi có sự cố**.

---

**Kết luận:** Thêm một công nghệ lưu trữ trong kiến trúc NoSQL là quyết định **sản phẩm, kỹ thuật và vận hành**, không chỉ là quyết định chọn engine có benchmark tốt. Phải so **incremental TCO** giữa các phương án trên cùng workload và SLO, tính đủ **setup, replication, index/storage overhead, network, nhân sự/on-call, bảo mật, CDC/outbox, migration/reindex, backup/DR, rủi ro và exit**. Mỗi bản sao dữ liệu mới cần xác định rõ **source of truth, freshness, idempotency, quyền truy cập, delete propagation và reconciliation**. Một quyết định đáng tin có **bằng chứng từ workload, hard gates, ADR, TCO nhiều kịch bản, pilot, runbook, rollback và ngày review lại**. Công nghệ mới chỉ đáng thêm khi **giá trị đo được của nó vượt chi phí tăng thêm**, rủi ro được kiểm soát và đội ngũ thật sự có thể vận hành, khôi phục nó an toàn trong suốt vòng đời.
