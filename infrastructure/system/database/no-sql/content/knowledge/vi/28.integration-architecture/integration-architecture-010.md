# Cô lập truy vấn quản trị hoặc báo cáo khỏi tải giao dịch

Một ứng dụng thương mại điện tử dùng NoSQL để xử lý đặt hàng, giữ hàng và cập nhật trạng thái thanh toán. API giao dịch thường chỉ đọc vài bản ghi theo khóa và trả kết quả trong vài chục mili-giây. Đến cuối tháng, một nhân viên quản trị mở báo cáo “tất cả đơn hàng của 18 tháng qua”, kèm nhóm theo sản phẩm và trạng thái. Truy vấn báo cáo phải đọc hàng triệu bản ghi, giải mã nhiều dữ liệu, sắp xếp và kết hợp; từ đó API thanh toán bắt đầu timeout dù chưa có đột biến khách mua hàng.

Vấn đề này xuất hiện khi **truy vấn quản trị hoặc báo cáo (administrative/analytical workload)** chia sẻ nguồn tài nguyên quan trọng với **tải giao dịch trực tuyến (transactional/operational workload)**. Với NoSQL, một truy vấn quét rộng có thể chiếm read capacity, CPU, disk I/O, cache, connection pool, coordinator threads và băng thông sao chép. Vì vậy “đặt báo cáo ở endpoint khác” không đủ; cần **cô lập ở đúng tầng tài nguyên và đúng hợp đồng dữ liệu**.

Bài học thuộc chương **Tích hợp và kiến trúc** của module **Database No SQL**. Nội dung đi từ cách nhận diện workload, lựa chọn kiến trúc đọc/báo cáo, CDC và read model, ranh giới nhất quán và độ mới, phân quyền bảo mật, giới hạn tải, thiết kế trên một số họ NoSQL, đến cách đo kiểm chứng rằng báo cáo không phá SLO của giao dịch.

**Phạm vi ví dụ:** thông số lưu lượng, độ trễ, dung lượng, giá tiền và giới hạn minh họa trong bài **không phải cam kết sản phẩm**. Cơ chế read replica, change streams, export, scan, query consistency và workload management phụ thuộc engine, phiên bản, cấu hình, dịch vụ managed và topology. Cần đo và đọc tài liệu của chính hệ được triển khai.

## 1. Vì sao giao dịch và báo cáo có đặc tính xung đột?

Tải giao dịch điển hình:

- Nhiều request nhỏ, thường đọc/ghi một khóa, một aggregate hoặc vài partitions.
- Cần p95/p99 thấp và kết quả đủ mới để quyết định đúng nghiệp vụ.
- Phải bảo vệ invariant: một Order không được chuyển trạng thái tùy tiện; tồn kho không âm; một idempotency key không áp hai lần.
- Chạy liên tục, nhạy cảm với contention và tail latency.

Tải quản trị/báo cáo điển hình:

- Ít người dùng hơn, nhưng mỗi request có thể đọc rất nhiều dữ liệu.
- Cần lọc theo thời gian, nhóm, tổng hợp, tính thống kê, xuất CSV/Parquet.
- Thường chịu được độ trễ làm mới vài giây, phút hoặc giờ tùy mục đích.
- Có thể sử dụng snapshot hoặc materialized view, không nhất thiết đọc transaction source trực tiếp.
- Có các batch jobs chạy theo lịch và một số dashboard truy vấn lặp lại.

| Thuộc tính | Giao dịch trực tuyến | Quản trị/báo cáo |
|---|---|---|
| Truy cập dữ liệu | Point lookup, bounded range, conditional write | Scan/range rộng, join/aggregate |
| Độ trễ mong muốn | Thường thấp và có p99 SLO | Có thể vài giây hoặc job bất đồng bộ |
| Tính nhất quán | Theo invariant và operation | Thường cần snapshot/độ mới công bố |
| Kiểu tải | Nhiều call nhỏ | Ít call nhưng lượng công việc lớn |
| Khả năng dự đoán | Tương đối theo API contract | Dễ thay đổi theo filter/ad hoc query |
| Tác động quá tải | Ảnh hưởng checkout, quyền truy cập, giữ hàng | Báo cáo chậm hoặc trễ |
| Ưu tiên phục vụ | Thường là đường quan trọng | Có thể hoãn, chia lô hoặc degrade |
| Dữ liệu | Mô hình theo aggregate/write patterns | Mô hình theo phân tích/đọc nhiều chiều |

Không phải mọi endpoint “admin” đều nặng. Một admin tra Order theo ID vẫn là point read. Ngược lại, một endpoint người dùng “xuất lịch sử 5 năm” có thể là workload báo cáo. **Phân loại theo hành vi và hậu quả của truy vấn**, không chỉ theo vai trò người gọi.

## 2. Một báo cáo có thể gây nghẽn thế nào?

Giả sử NoSQL cluster có 12 nodes, một hot shard và các API nghiệp vụ. Một báo cáo thực hiện:

~~~text
Admin UI
  -> GET /admin/report?from=...
  -> scan toàn bộ orders
  -> group by status/product
  -> sort + export 2 GiB CSV
~~~

Nó có thể cạnh tranh với giao dịch trên:

1. **CPU:** giải mã, filter, aggregate, serialize kết quả.
2. **Disk I/O:** đọc dữ liệu lạnh, kích hoạt page faults, chèn ép background compaction.
3. **Memory/cache:** scan làm tràn những hot pages hữu ích cho point reads.
4. **Network:** truyền hàng triệu documents giữa nodes hoặc về app.
5. **Read capacity/quota:** một table hoặc partition bị throttling.
6. **Thread/connection pool:** báo cáo giữ connection lâu.
7. **Coordinator/shard leader:** fan-out tới nhiều partitions khiến node điều phối quá tải.
8. **Index:** query không được index hỗ trợ dẫn tới scan nhiều records.
9. **Replication:** một số cách đọc/backup/report có thể ảnh hưởng log retention, replica replay hoặc disk sharing.
10. **Chi phí cloud:** tăng read units, data transfer, storage projection và CPU.

Từ một báo cáo “chỉ đọc” vẫn có thể làm writes chậm: CPU/disk/cache là tài nguyên dùng chung; một số hệ còn cần coordinator/lock metadata/transaction snapshot phục vụ query. **Read-only không đồng nghĩa zero impact**.

## 3. Định nghĩa mục tiêu cô lập trước khi chọn công nghệ

Cần mô tả mục tiêu bằng hợp đồng có thể đo:

> Khi một hoặc nhiều báo cáo chạy đồng thời, API Checkout vẫn đạt p99 dưới ngưỡng SLO và tỉ lệ thành công đã định; các báo cáo có thể chậm hoặc bị xếp hàng, nhưng không được lấy hết tài nguyên của đường giao dịch.

Các câu hỏi:

- API/operations nào phải được ưu tiên tuyệt đối?
- Bao nhiêu báo cáo có thể chạy đồng thời?
- Dataset lớn đến đâu; tăng bao nhiêu mỗi ngày?
- Báo cáo cần độ mới 1 giây, 1 phút hay T+1 ngày?
- Báo cáo có cần snapshot nhất quán với transaction nhiều bản ghi?
- Kết quả dùng để quyết định trả tiền/kho hay chỉ hiển thị xu hướng?
- Mục tiêu p95/p99 của transaction được đo khi báo cáo chạy thế nào?
- Khi cluster lỗi một node/AZ, báo cáo có cần tiếp tục chạy không?
- Ai được quyền truy vấn, và có được xem dữ liệu nhạy cảm/đa tenant không?
- Có chấp nhận “report queued” hoặc file xuất sau khi job hoàn thành không?

**“Không làm ảnh hưởng tải giao dịch” là mục tiêu về phần tài nguyên và SLO, không chỉ là một sơ đồ hệ thống đẹp.**

## 4. Các mức cô lập khác nhau

Có thể cô lập ở nhiều tầng:

| Tầng | Cơ chế | Lợi ích | Giới hạn |
|---|---|---|---|
| API | Endpoint/worker pool riêng | Dễ quản trị concurrency và deadline | Vẫn chung DB |
| Truy vấn | Filter/index/limit/bounded scan | Giảm công việc trên mỗi request | Không loại bỏ chia sẻ nguồn |
| Connection | Pool riêng với quota | Báo cáo không giữ hết kết nối của giao dịch | DB CPU/I/O còn chung |
| Scheduling | Job queue/priority | Tránh báo cáo chồng chéo, hỗ trợ hoãn | Nếu nhiều job lớn vẫn nghẽn DB |
| Replica | Đọc từ secondary/read replica | Giảm một phần read work trên primary | Sao chép, storage, network vẫn có thể chia sẻ |
| Node/cluster | Analytical node/replica group/DC riêng | Cô lập phần CPU/disk/bộ nhớ tốt hơn | Replication lag, chi phí và failover |
| Dữ liệu | CDC → reporting store | Mô hình dữ liệu đúng truy vấn, tách read compute | Event pipeline, độ trễ, reconciliation |
| Warehouse/lake | Batch/stream load và columnar compute | Phân tích lớn, join, BI | Freshness và vận hành ETL |
| Tổ chức | RBAC, tenant quota, audit, cost attribution | Kiểm soát người dùng/truy vấn | Không thay cô lập vật lý |

Những tầng có thể kết hợp. Ví dụ **CDC sang warehouse** vẫn nên có giới hạn concurrent SQL jobs, quyền truy cập theo tenant và quota chi phí. Còn **read replica riêng** vẫn cần timeout và lag monitoring.

## 5. Kiến trúc ba đường đọc: command, operational query và analytics

Một sơ đồ tham khảo:

~~~mermaid
flowchart LR
    U["Ứng dụng khách"] --> A["API giao dịch"]
    A --> P["NoSQL source / write model"]
    P --> E["CDC / Outbox / Export"]
    E --> R["Reporting projection"]
    E --> W["Warehouse / Data lake"]
    M["Admin console"] --> Q["Admin API / Job queue"]
    Q --> R
    Q --> W
    Q -. "Point lookup có kiểm soát" .-> P
~~~

Ba đường:

1. **Command/write path** kiểm tra invariant và ghi tại nguồn có thẩm quyền.
2. **Operational query path** đọc theo access patterns hẹp để phục vụ thao tác trực tuyến.
3. **Reporting/analytics path** dùng một mô hình khác, có thể được cập nhật bất đồng bộ.

Điều quan trọng không phải “CQRS là bắt buộc”, mà là **mỗi đường có performance, freshness, consistency và quyền truy cập được định nghĩa rõ**. Không cần một warehouse cho vài thống kê đơn giản; cũng không nên dùng transaction cluster để phục vụ báo cáo ad hoc rất lớn mãi mãi.

## 6. Khi nào vẫn có thể đọc báo cáo trực tiếp từ nguồn?

Đọc từ primary/transaction source có thể chấp nhận nếu truy vấn **thực sự nhỏ và được kiểm soát**:

- Tra một record theo key để hỗ trợ khách hàng.
- Đọc một trang gần nhất của audit log theo index/partition.
- Đọc số thống kê nhỏ đã được pre-aggregate trong source.
- Thực hiện kiểm tra tức thời mà yêu cầu consistency không thể đáp ứng từ replica chậm.
- Tần suất thấp, bounded by partition/time, có deadline và quota.

Ví dụ một API quản trị:

~~~text
GET /admin/orders/O1001
  -> keyed lookup
  -> record-level authorization
  -> bounded response
~~~

Tương phản:

~~~text
GET /admin/orders?from=2024-01-01
  -> unrestricted collection/table scan
  -> group + sort hàng triệu documents
  -> synchronous CSV stream rất dài
~~~

Với trường hợp thứ hai, thay vì giữ HTTP request và connection quá lâu, nên chuyển sang **report job** hoặc **read model**. Nếu vẫn thực hiện tại nguồn vì yêu cầu đặc biệt, cần explicit exception, bounded range, giới hạn concurrency và có kế hoạch dừng trước khi ảnh hưởng SLO.

## 7. Dedicated read replica: lợi ích và những điểm dễ hiểu nhầm

Một replica đọc dành cho admin có thể giảm read requests trên primary:

~~~mermaid
flowchart LR
    T["Transaction API"] --> P["Primary / authoritative owner"]
    P --> S["Replica cho operational reads"]
    P --> R["Replica dành cho admin/report"]
    AD["Admin API"] --> R
~~~

Ưu điểm:

- Tách một phần CPU/read I/O của báo cáo khỏi primary.
- Có thể cấp tài nguyên/instance khác phù hợp truy vấn.
- Thay đổi read preference/routing theo application role.
- Hạn chế báo cáo chiếm pool kết nối của transaction service.

Nhưng không mặc nhiên cô lập hoàn toàn:

- Replica vẫn phải **nhận và áp thay đổi** từ nguồn.
- Báo cáo nặng có thể làm replica lag, tăng log retention hoặc backlog theo cơ chế hệ.
- Nếu replica và primary dùng cùng host/volume/network thì mức cô lập vật lý thấp.
- Read replica có thể stale; báo cáo phải chấp nhận đúng độ mới.
- Một số hệ có thể promote replica trong failover, khiến tải admin bất ngờ chạy cùng owner mới.
- Nếu replica hỏng, **không tự động fallback báo cáo sang primary** nếu mục tiêu là bảo vệ transaction SLO.
- Snapshot/long reads có thể có ảnh hưởng lên storage internals theo engine.

**Cần đo shared dependencies**, không chỉ nhìn “read preference = secondary”.

## 8. Dedicated analytics node, replica group hoặc data center

Nếu dữ liệu lớn và báo cáo thường xuyên, có thể dùng **node/replica group/cluster riêng cho analytics**. Chẳng hạn một NoSQL topology có replication tới data center phục vụ analytics, nơi báo cáo không chạy trên những nodes phục vụ low-latency transactions.

Một mô hình:

~~~text
DC-OLTP:
  nodes phục vụ API giao dịch
  commit/read policy ưu tiên correctness + latency

DC-REPORT:
  nodes lưu bản sao dành cho báo cáo
  separate connections / jobs / query quotas

Replication:
  tiến độ, độ trễ, failure behavior được đo
~~~

Mức cô lập cải thiện vì có CPU, memory, disk và pools riêng. Tuy nhiên:

- Chi phí storage tăng theo số bản sao.
- Cross-region/DC network, replication và log retention tăng.
- Đọc ở DC báo cáo có thể chưa thấy write vừa commit ở DC giao dịch.
- Một topology failover có thể chuyển trách nhiệm/owner giữa DCs; phải biết rõ.
- Nếu báo cáo cần join, group-by hay scan ad hoc nhiều chiều, một **bản sao cùng data model OLTP** có thể vẫn không phù hợp.
- Cần backup/restore, access control và lifecycle riêng cho DC báo cáo.

Cô lập node tốt là **cô lập tài nguyên**; tối ưu báo cáo tốt còn đòi **mô hình lưu trữ và chỉ mục phù hợp**.

## 9. CDC: tách dữ liệu sang hệ đọc khác

**Change Data Capture (CDC)** lấy thay đổi đã commit từ một nguồn theo cơ chế được hỗ trợ và chuyển chúng tới read model/warehouse/search.

~~~mermaid
flowchart LR
    P["NoSQL source"] --> C["CDC/Change stream"]
    C --> B["Event bus / Durable queue"]
    B --> X["Transform / Normalize"]
    X --> R["Reporting store"]
    X --> W["Data lake / Warehouse"]
    X --> S["Search index"]
~~~

Ưu điểm:

- Truy vấn báo cáo chạy trên **compute/storage khác**.
- Có thể tạo schema denormalized, indexes hoặc columnar layout theo báo cáo.
- Báo cáo không quét lại primary mỗi lần.
- Nhiều sản phẩm tiêu thụ cùng một change log với yêu cầu khác nhau.

Giới hạn:

- Replication/CDC có độ trễ và cần metric về **freshness**.
- Event redelivery/reorder có thể xảy ra.
- Dữ liệu được biến đổi và ghép từ nhiều collections cần contract.
- Thay schema source có thể làm consumer hỏng.
- Nếu log retention không đủ khi consumer lag, phải backfill.
- CDC capture, network hoặc source log vẫn tiêu tài nguyên của hệ gốc.

**CDC giảm phần đọc nặng ở nguồn, nhưng không hoàn toàn miễn phí với source.** Cần bố trí connectors phù hợp, checkpoint, backpressure và alert.

## 10. Transactional outbox khi báo cáo cần business events

Nếu nguồn ghi Order và đồng thời cần phát event `OrderConfirmed`, một mô hình **transactional outbox** có thể bảo đảm ý định phát event được ghi trong cùng transaction/atomic boundary phù hợp:

~~~text
Within source transaction:
  update Order O1001 -> CONFIRMED
  insert Outbox event E1001
commit

Relay:
  read outbox or CDC
  publish E1001 to broker
  mark/checkpoint published

Consumer:
  upsert reporting projection with idempotency
~~~

Vì relay có thể crash sau khi publish nhưng trước khi ghi nhận checkpoint, **message có thể được giao lặp**. Consumer phải idempotent:

~~~text
if eventId has already been applied:
    skip duplicate
else:
    apply projection update
    record eventId as processed atomically if possible
~~~

Lưu `eventId` ở một nơi khác với projection mà không có atomic boundary có thể tạo crash gap. Cần chọn cơ chế phù hợp: unique event key, transaction trong reporting store, idempotent upsert theo version hoặc reconciliation.

**Outbox không tự tạo exactly-once delivery**; mục tiêu thực tế thường là *at-least-once delivery + exactly-once business effect* nhờ idempotency trong phạm vi đã định.

## 11. Chụp dữ liệu ban đầu và CDC: không được mất đoạn chuyển tiếp

Một read model mới cần **backfill dữ liệu lịch sử** rồi tiếp nhận changes mới. Nếu làm sai thứ tự:

~~~text
T0: Bắt đầu scan toàn bộ orders.
T1: Order O42 được cập nhật.
T2: Scan chưa tới O42 hoặc đã đi qua O42.
T3: Bật CDC quá muộn.
~~~

Có thể bỏ sót update giữa snapshot và CDC.

Một workflow an toàn theo **giao thức cụ thể của engine**:

1. Xác định một mốc snapshot/checkpoint hoặc change-stream position hợp lệ.
2. Bảo đảm changes **sau mốc** có thể replay đầy đủ, giữ log đủ lâu.
3. Backfill dữ liệu snapshot với key/version.
4. Stream changes từ mốc phù hợp, áp dụng idempotent theo ordering/version.
5. Ghi lại tiến độ theo shard/partition/stream.
6. Đối soát counts và business IDs/digests giữa source và projection.
7. Chỉ mở báo cáo “đầy đủ” khi backfill + stream đã hội tụ tới watermark đã công bố.
8. Nếu mất log gap, thực hiện repair/re-snapshot thay vì giả vờ đồng bộ.

Không có một trình tự “chụp trước rồi nghe CDC” đúng cho mọi connector. Một số sản phẩm hỗ trợ snapshot+stream handoff nhất quán, số khác cần một quy trình riêng. **Phải giữ đúng ranh giới snapshot/CDC**, không chỉ cộng hai luồng dữ liệu lại.

## 12. CDC delivery: duplicate, order và delete

Một event minh họa:

~~~json
{
  "eventId": "order-O1001-version-9",
  "entityId": "O1001",
  "entityVersion": 9,
  "operation": "STATUS_CHANGED",
  "occurredAt": "2026-11-14T09:00:00Z",
  "payload": {
    "status": "CONFIRMED"
  }
}
~~~

Khi report consumer nhận events:

- **Duplicate:** cùng `eventId` được gửi lại sau retry; cần dedupe.
- **Out-of-order:** version 9 tới trước version 8; phải không ghi đè bằng snapshot cũ.
- **Delete/tombstone:** cần xóa/đánh dấu dữ liệu khỏi read model theo chính sách.
- **Schema evolution:** event phiên bản cũ/field mới cùng tồn tại.
- **Partial failure:** consumer apply vào một projection nhưng chưa checkpoint.
- **Poison event:** dữ liệu không hợp lệ cần DLQ/quarantine, không để toàn pipeline chết vô hạn.
- **Replay:** reprocessing phải an toàn và biết snapshot/offset.

Một chiến lược cho **full-state upsert events** là chỉ áp khi `incomingVersion > storedVersion`. Nhưng với **delta events**, bỏ version 8 rồi áp version 9 có thể sai vì còn thiếu effect 8. Phải phân biệt **snapshot-of-state** và **operation delta**.

## 13. Read model phục vụ báo cáo cần schema khác write model

Một nguồn NoSQL được thiết kế theo access pattern:

~~~json
{
  "orderId": "O1001",
  "customerId": "u42",
  "items": [
    {"sku": "SKU-A", "quantity": 2, "unitPrice": 120000},
    {"sku": "SKU-B", "quantity": 1, "unitPrice": 80000}
  ],
  "status": "CONFIRMED",
  "createdAt": "2026-11-14T09:00:00Z"
}
~~~

Truy vấn báo cáo “doanh thu theo ngày và SKU” phải lặp qua items nhiều Order. Một read model có thể tạo các facts:

~~~text
order_line_facts:
  orderId
  lineId
  sku
  dateUTC
  quantity
  amount
  statusAtAccountingCutoff
  tenantId
  version
~~~

Và materialized aggregate:

~~~text
daily_revenue_by_sku:
  dateUTC, tenantId, sku
  confirmedRevenue
  refundedRevenue
  netRevenue
  orderCount
  dataWatermark
~~~

Khi report data được materialize, dashboard không cần đọc hàng triệu Order documents để tính lại mỗi lần.

Cần định nghĩa nghĩa nghiệp vụ: `createdAt` hay `paidAt` quyết định ngày hạch toán? Hoàn tiền hôm sau giảm doanh thu ngày nào? Đơn đổi trạng thái có phải hiệu chỉnh aggregate? **Schema báo cáo không chỉ là copy dữ liệu; nó là một data contract.**

## 14. Materialized aggregation: hiệu quả nhưng phải chống double-count

Giả sử một Order `O1001` được CONFIRMED và event gửi tới consumer hai lần. Nếu handler làm:

~~~text
dailyRevenue += 320000
~~~

mỗi lần nhận, báo cáo bị nhân đôi.

Các hướng đúng tùy mô hình:

- Lưu event idempotency key và áp effect một lần.
- Dùng versioned state: đọc previous order contribution, tính delta từ trạng thái cũ sang mới rồi atomic update.
- Dùng immutable fact ledger và aggregate từ các facts đã dedup.
- Rebuild định kỳ từ authoritative facts để sửa drift.
- Với dữ liệu aggregate xấp xỉ, công bố semantics và sai số được phép.

Bài toán khó hơn khi Order đổi trạng thái:

~~~text
PENDING -> CONFIRMED -> REFUNDED
~~~

Không thể cứ cộng giá trị ở mỗi event như thể cả ba đều là doanh thu mới. Cần event semantics, version monotonic và quy tắc ghi nhận/hoàn tác đúng.

## 15. Warehouse hoặc data lake: khi truy vấn vượt mô hình OLTP

Nếu báo cáo cần join nhiều datasets lớn, group theo nhiều chiều, giữ dữ liệu nhiều năm, tính cohort/funnel/percentile, chạy BI ad hoc hoặc kết hợp data bên ngoài NoSQL, một **warehouse/analytical engine** hoặc **data lake với query engine** thường phù hợp hơn một bản replica cùng document layout của OLTP.

~~~mermaid
flowchart LR
    A["NoSQL transactional source"] --> C["CDC + incremental ETL"]
    A --> S["Snapshot / scheduled export"]
    C --> W["Warehouse tables"]
    S --> W
    W --> BI["BI dashboards"]
    W --> B["Scheduled heavy reports"]
    W --> Q["Data quality checks"]
~~~

Các tính chất mong muốn:

- Columnar storage, vectorized scan nếu workload được hưởng lợi.
- Partition pruning theo ngày, tenant, một số dimensions.
- Cấp compute riêng cho report jobs.
- Materialized views/aggregations khi engine hỗ trợ.
- Data lineage, governance, audit và retention.
- Khả năng tính lại báo cáo khi logic nghiệp vụ thay đổi.

Đổi lại cần chi phí pipeline, schema/versioning và kiểm soát độ mới. Báo cáo phân tích là một **projection**; nghiệp vụ đặt hàng và giữ hàng vẫn dựa vào **transactional source** có thẩm quyền.

## 16. Search index không phải kho phân tích đa dụng

Một search engine như OpenSearch/Elasticsearch hoặc sản phẩm tương tự có thể hữu ích cho full-text search, filters đa chiều, faceting và aggregation trên index được thiết kế phù hợp. Nhưng search index có refresh/indexing lag, chi phí index/reindex, shard fan-out, heap pressure và giới hạn hiệu quả với high-cardinality aggregations hoặc deep pagination.

Nếu search đang phục vụ khách hàng, **admin aggregation nặng cũng cần được cô lập khỏi search production** bằng query budgets, worker pool, index/cluster riêng hoặc warehouse. Chuyển báo cáo từ transaction DB sang một search cluster dùng chung không tự làm biến mất tranh chấp tài nguyên; nó chỉ chuyển điểm nghẽn.

## 17. Báo cáo lớn nên là job, không phải một HTTP request dài

Một endpoint xuất hàng triệu records không nên giữ HTTP connection/DB connection sống hàng giờ. Mô hình:

~~~mermaid
flowchart TD
    A["Admin nhấn Export"] --> B["POST /reports/jobs"]
    B --> C["Validate quyền và query scope"]
    C --> D["Persist job metadata / enqueue"]
    D --> E["Worker có quota riêng"]
    E --> F["Đọc reporting store theo batches"]
    F --> G["Ghi artifact vào object storage"]
    G --> H["Mark SUCCEEDED + checksum"]
    H --> I["GET status / download URL ngắn hạn"]
~~~

Ví dụ:

~~~http
POST /reports/jobs
Content-Type: application/json

{
  "type": "orders-by-sku",
  "tenantId": "t01",
  "from": "2026-10-01T00:00:00Z",
  "to": "2026-11-01T00:00:00Z",
  "format": "csv"
}
~~~

Trả sau khi **durable intent** đã được ghi nhận:

~~~json
{
  "jobId": "report-921",
  "status": "QUEUED",
  "requestedAt": "2026-11-14T10:00:00Z"
}
~~~

Không báo COMPLETED khi chưa ghi xong/kiểm tra file. Job queue cần quota, retention, cleanup artifacts và cơ chế retry/cancel an toàn.

### 17.1. Vòng đời report job

~~~text
QUEUED -> RUNNING -> SUCCEEDED
               \-> FAILED_RETRYABLE -> RETRYING
               \-> FAILED_FINAL
QUEUED/RUNNING -> CANCEL_REQUESTED -> CANCELLED
SUCCEEDED -> EXPIRED/DELETED theo retention
~~~

Cần đảm bảo: idempotency key khi user bấm nhiều lần; checkpoint batches; retries không tạo hai artifacts thành công trùng; giới hạn total runtime/queue wait/attempts; tenant concurrency quota; quyền download; dữ liệu có cutoff/watermark rõ.

Một report job **không phải transaction nghiệp vụ kéo dài**: nó đọc dữ liệu theo snapshot/cutoff và tạo artifact có metadata về thời điểm/nguồn.

## 18. Truy vấn admin phải được giới hạn ngay cả ở reporting store

Dù đã có cluster riêng, query tự do không giới hạn vẫn có thể khiến cả đội báo cáo không dùng được.

Các hạn mức thực tế:

- Bắt buộc `tenantId` và giới hạn range thời gian.
- Số rows/page và total result cap.
- Số buckets/shards mỗi query.
- Query duration và job deadline.
- Concurrency/queue depth theo tenant.
- Data scanned/bytes returned/cost budgets.
- Chỉ cho phép report templates đã thẩm định nếu có dữ liệu nhạy cảm.
- Query cancellation và orphan-job handling.
- Không cho regex/wildcard/high-cardinality group-by không giới hạn.
- Bounded export size và retention.

Giới hạn không chỉ tiết kiệm tiền: nó bảo vệ tính khả dụng của các report quan trọng khác.

## 19. Keyset pagination và streaming cho bảng admin

Một bảng quản trị hiển thị “100 đơn hàng mới nhất” không nên làm full scan rồi sort toàn bộ.

Một projection NoSQL minh họa:

~~~text
PK = TENANT#t01#ORDER_DAY#2026-11-14
SK = CREATED_AT#2026-11-14T10:00:00Z#ORDER#O1001
~~~

Hoặc dùng một reporting index phục vụ `(tenant,status,createdAt)`. Khi phân trang:

- Dùng continuation token/keyset của engine.
- Giữ filters và sort order ổn định.
- Thêm `orderId` để tie-break nếu timestamps giống nhau.
- Opaque cursor có TTL, tenant/user scope và query hash.
- Tránh offset/skip cực lớn nếu engine quét bỏ nhiều records.
- Quy định dữ liệu mới giữa các trang có thể xuất hiện không.
- Với nhiều buckets/shards, dùng cursor hợp nhất theo composite sort key.

Một báo cáo export dài có thể dùng **batch scan checkpoint**, nhưng trang UI không nên biến thành scan không giới hạn.

## 20. Index dành cho báo cáo cũng có giá ghi

Index theo `createdAt,status,sku` có thể đẩy nhanh report nhưng mỗi write vào source phải cập nhật index theo semantics engine. Trước khi thêm index tại transaction source:

1. Query có thật dùng index với predicate/selectivity tốt?
2. Index có làm write amplification trên hot partition tăng không?
3. Storage/index footprint có vượt budget?
4. Xây/rebuild index có ảnh hưởng CPU/I/O production?
5. Truy vấn có vẫn quét qua hàng trăm partitions?
6. Index updates có đồng bộ hay bất đồng bộ?
7. Có cần index trường dữ liệu nhạy cảm không?
8. Có thể đặt index **chỉ ở reporting store** không?

Nếu một index chỉ giúp một report hiếm nhưng tăng chi phí cho hàng triệu writes, **tách projection** có thể phù hợp hơn.

### 20.1. Filter sớm, project ít field

Ví dụ MongoDB aggregate trên reporting collection:

~~~javascript
db.reportingOrders.aggregate([
  {
    $match: {
      tenantId: "t01",
      createdAt: {
        $gte: ISODate("2026-11-01T00:00:00Z"),
        $lt: ISODate("2026-12-01T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: "$status",
      orderCount: { $sum: 1 },
      amount: { $sum: "$totalAmount" }
    }
  },
  { $sort: { orderCount: -1 } }
]);
~~~

Đây là **query shape**, không cam kết nhanh. Range vẫn có thể chứa hàng triệu documents. Cần index phù hợp, query plan/explain, bounded data range và reporting resources. Aggregation nhiều shards hoặc disk spill vẫn đắt dù kết quả chỉ vài dòng.

## 21. Admission control và quota theo nhiều lớp

~~~text
Admin Gateway
  -> RBAC + tenant scope
  -> Validate report query
  -> Per-user/tenant quota
  -> Job scheduler
  -> Bounded worker pool
  -> Reporting DB pool
  -> Server-side query timeout/scan cap nếu hỗ trợ
~~~

| Biện pháp | Bảo vệ | Không tự bảo vệ |
|---|---|---|
| Jobs/user | User bấm nhiều jobs | Một job cực nặng |
| Concurrent jobs | Nhiều jobs chạy song song | Một query fan-out rất rộng |
| Bytes-scanned quota | Read cost lớn | CPU regex/aggregate riêng |
| Query deadline | Giới hạn thời gian giữ tài nguyên | Work burst trước timeout |
| Pool cap | Connection exhaustion | CPU/disk chung |
| Tenant fairness | Tenant nóng chiếm hết quota | Tất cả tenants cùng quá tải |
| Job priority | Hoãn báo cáo khi bận | Database có thể không hỗ trợ priority native |
| Separate cluster | Cô lập compute/storage phần lớn | CDC/shared network/source log |

Không có nút “low priority” phổ quát cho mọi NoSQL. Nếu engine không có workload groups/priorities native, application vẫn có thể giới hạn jobs và rate, nhưng phải đo tác động thực.

## 22. Pool riêng và bulkheads: cô lập số connections

Một nguồn lỗi thường gặp:

~~~text
Max DB connections trong application: 100

100 admin scans cùng chiếm connections và giữ lâu
=> Checkout requests không còn connection
=> Checkout timeout trước khi chạm DB
~~~

Nếu report và transaction chung process, có thể tách:

~~~text
transactionPool:
  maxConnections: 80
  acquireTimeout: 30ms

adminPool:
  maxConnections: 8
  acquireTimeout: 100ms
  maxConcurrentReports: 4
~~~

Các giá trị chỉ minh họa. Tách pools tạo một **bulkhead**: admin không giữ hết connections của transaction. Nhưng nếu cả hai pools cùng trỏ vào primary, admin vẫn có thể chiếm disk/CPU/network. Vì vậy bulkhead hiệu quả cần **connection + query + resource ownership isolation**.

Nếu báo cáo chạy trên cluster khác, dùng pool và credentials khác; không mang write privileges của transaction app vào worker báo cáo.

## 23. Timeout và deadline cho toàn report job

Một report lớn có thể có các mốc:

- Deadline API POST để nhận lệnh: ví dụ dưới 1 giây.
- Queue waiting budget: ví dụ tối đa 10 phút.
- Job execution deadline: ví dụ 30 phút.
- Per-batch database read timeout: ví dụ 10 giây.
- Retry budget cho lỗi tạm thời.
- Artifact retention: ví dụ 7 ngày.

Những mốc này **khác nhau**. Khi POST trả 202, HTTP connection đóng không có nghĩa report job phải hủy. Một batch timeout có thể retry từ checkpoint trong **job deadline**; không nhất thiết chạy lại mọi dữ liệu.

~~~text
Report intent accepted durably
  -> QUEUED within queue budget
  -> RUNNING within job deadline
       -> Batch 1 with bounded read timeout
       -> Batch 2 with bounded read timeout
       -> ...
       -> finalize artifact + checksum
~~~

Báo cáo “chốt số tại 00:00” cần snapshot/cutoff contract; tăng timeout không khiến dữ liệu được cố định tại một mốc.

## 24. Freshness SLO: báo cáo được phép trễ bao lâu?

Khi tách khỏi nguồn, báo cáo có **độ trễ cập nhật**. Cần phân biệt:

- **Event time:** lúc sự kiện nghiệp vụ xảy ra.
- **Commit time:** lúc nguồn chấp nhận thay đổi theo commit semantics.
- **Ingestion time:** lúc CDC/connector nhận.
- **Applied time:** lúc projection áp dụng thay đổi.
- **Visible time:** lúc query thực tế thấy bản mới.
- **Watermark:** mức tiến độ đã xác minh với semantics về dữ liệu còn đến muộn.

Ví dụ nhãn dashboard:

~~~text
Orders report
Data current through: 2026-11-14 09:58 UTC
Report generated at:  2026-11-14 10:00 UTC
Observed lag:          approximately 2 minutes
~~~

Không nên hứa “real-time” nếu pipeline lag vài phút. Nhãn **“Dữ liệu cập nhật đến 09:58 UTC”** giúp user phân biệt status transaction mới nhất với snapshot báo cáo.

### 24.1. Mức độ mới tùy nghiệp vụ

| Truy vấn | Freshness ví dụ | Cách xử lý khi lag |
|---|---|---|
| Dashboard traffic | 5–15 phút | Hiển thị watermark/stale label |
| Sales trend trong ngày | 1–5 phút | Có thể dùng bản cũ kèm thông báo |
| Quyết toán ngày | Chốt kỳ + đối soát đầy đủ | Không báo “final” khi thiếu dữ liệu |
| Fraud event triage | Có thể yêu cầu gần thời gian thực | Dùng event processing/operational lookup phù hợp |
| Số lượng có thể bán | Cần authoritative revalidation | Không dùng warehouse để chốt giữ hàng |
| Admin GET Order theo ID | Có thể cần read-your-writes | Point lookup có kiểm soát ở nguồn |

Những mức thời gian chỉ là **ví dụ phân loại**, không phải mặc định. Hãy chọn theo hậu quả business nếu báo cáo bị cũ.

## 25. Watermark phải có phạm vi và semantics cụ thể

Một pipeline xử lý 20 partitions. Nếu 19 partitions đã tới 10:00 nhưng partition P7 mới tới 09:40, không thể công bố “dữ liệu đầy đủ đến 10:00” cho toàn hệ nếu P7 thuộc report.

Ví dụ metadata:

~~~json
{
  "dataset": "orders_reporting",
  "sourcePositions": {
    "partition-0": "offset-12000",
    "partition-1": "offset-11500",
    "partition-7": "offset-9900"
  },
  "completeThrough": "2026-11-14T09:40:00Z",
  "calculatedAt": "2026-11-14T10:00:00Z"
}
~~~

Watermark chỉ có nghĩa nếu pipeline biết **không còn dữ liệu hợp lệ trước mốc đó chưa được xử lý**, theo producer/ordering/late-event contract. Nếu partition idle, offset không thay đổi chưa chắc là bị lag; có thể cần heartbeats hoặc idle partition semantics.

**Max observed event timestamp không tự là complete-through watermark.** Event 10:00 đã tới không chứng minh event 09:50 ở nguồn khác cũng đã tới.

## 26. Snapshot consistency: một báo cáo có thể lệch giữa các nguồn

Ví dụ Order và Inventory thuộc hai stores:

~~~text
09:00:00  Order O42 -> CONFIRMED
09:00:01  StockPool giảm available
09:00:02  Reporting ETL đọc Order mới
09:00:03  Reporting ETL đọc StockPool cũ
~~~

Report hiển thị Order CONFIRMED nhưng Stock chưa giảm. Đó có thể là ảnh chụp **tạm lệch**, không nhất thiết dữ liệu nguồn bị hỏng.

Các mức lựa chọn:

1. **Best-effort eventual:** chấp nhận lệch ngắn, công bố độ mới.
2. **Consistent snapshot trong một datastore:** dùng read timestamp/snapshot engine hỗ trợ và xác định scope.
3. **Cross-source reconciliation:** dùng cutoff/watermark cho mỗi nguồn và quy tắc chốt.
4. **Business fact ledger:** tính từ dữ liệu đã commit theo accounting semantics.
5. **Finalized period:** chỉ công bố final khi đã đối soát và khóa kỳ.

Không tự gọi dữ liệu từ hai sources ở cùng wall-clock timestamp là một **global consistent snapshot**. Nếu không có transaction/snapshot chung, cần định nghĩa reconciliation protocol.

## 27. Đối soát dữ liệu báo cáo với nguồn

Một pipeline có thể “healthy” nhưng bỏ event hoặc nhân đôi do retry. Cần đối soát:

- Counts theo partition/ngày/tenant và status.
- Sum/checksum cho facts có stable IDs.
- Max applied version theo entity.
- Missing/duplicate events tại cùng cutoff.
- State transitions có hợp lệ không.
- Poison events/DLQ đã được xử lý chưa.
- Replay/backfill checkpoints có gap không.
- Watermark có phản ánh trạng thái thực tế không.
- Sai lệch amounts do refunds/currency/rounding có policy gì.

Ví dụ:

~~~text
Source confirmed IDs tại cutoff: {O1,O2,O3,O4}
Reporting confirmed IDs tại cutoff: {O1,O2,O4}

Missing in projection: {O3}
Unexpected in projection: {}
~~~

Phép đối soát chỉ có nghĩa khi hai bên dùng **cùng snapshot/cutoff và cùng định nghĩa doanh thu/trạng thái**. Source có O5 mới hơn cutoff mà reporting chưa nhận không phải data loss.

### 27.1. Reconciliation là một đường vận hành

Nên có khả năng:

1. Chọn time window/partition có sai lệch.
2. Truy vấn nguồn chuẩn theo batch có quota.
3. So event IDs, version/fingerprint.
4. Bổ sung hoặc sửa projection bằng **idempotent upsert**.
5. Ghi audit của hành động sửa.
6. Đánh dấu watermark hợp lệ sau khi hoàn tất.
7. Cảnh báo nếu drift vượt ngưỡng hay sửa lặp không hết.

Quá trình repair cũng không được chạy scan khổng lồ trên production trong giờ cao điểm; nó là một workload admin/maintenance cần được giới hạn như report.

## 28. Bảo mật: báo cáo có thể nhạy cảm hơn API đơn lẻ

Một API giao dịch trả Order của một user; report worker có thể đọc **toàn bộ Orders của nhiều tenants**, gồm địa chỉ, email, doanh thu hay dữ liệu thanh toán. Cô lập tài nguyên phải đi cùng **cô lập quyền**:

1. **Least privilege:** credentials báo cáo chỉ đọc reporting store, không ghi transaction source.
2. **RBAC/ABAC:** quyền admin/report theo role và phạm vi tenant/organization.
3. **Server-side tenant filtering:** không chỉ tin UI/caller filter.
4. **Field masking:** chỉ xuất các trường thật sự cần.
5. **PII minimization:** không copy fields nhạy cảm không cần sang warehouse.
6. **Audit:** ai chạy report, scope nào, có tải file không.
7. **Encryption:** data at rest/in transit, quản lý keys và retention.
8. **Signed URL có TTL:** ngăn file báo cáo sống mãi qua URL public.
9. **Deletion/legal retention:** source delete cần lan sang projections/exports đúng chính sách.
10. **Tenant isolation tests:** request không được tự đổi tenantId để xem dữ liệu khác.

Một kho báo cáo có quyền rộng và giữ nhiều file xuất lâu dài có thể trở thành **bề mặt rủi ro bảo mật lớn** nếu thiếu governance.

## 29. CSV/Excel export cần chống formula injection

Các báo cáo admin thường xuất CSV để mở trong Excel hoặc công cụ bảng tính. Nếu một trường do người dùng cung cấp bắt đầu bằng ký tự bị bảng tính hiểu là công thức (ví dụ dấu bằng, cộng, trừ hoặc at-sign tùy phần mềm), ứng dụng nhận file có thể thực thi các hàm không mong muốn.

Một quy trình an toàn:

- Xác định rõ đối tượng tiêu thụ file và cách họ mở.
- Escape hoặc chuyển các giá trị không tin cậy sang text theo quy tắc của exporter/consumer.
- Không coi việc quote trường CSV bằng dấu nháy kép là biện pháp bảo vệ công thức đầy đủ.
- Xử lý Unicode, newline, delimiter, null và encoding nhất quán.
- Có tests cho input bất thường và người dùng có quyền ghi giá trị text.
- Đưa file ra object storage với content type, filename và download policy rõ.
- Không chèn private access token/secret vào report artifact.

Cô lập báo cáo không chỉ là performance. Một pipeline mới tạo file có thể mang các rủi ro data exfiltration và spreadsheet injection khác với API transaction gốc.

## 30. Tenant isolation và noisy neighbor

Một tenant lớn có thể chạy nhiều report nặng làm chậm các tenants khác trên reporting store. Một sơ đồ quota:

~~~text
Global report concurrency = 12

Tenant A: max 2 concurrent jobs
Tenant B: max 2 concurrent jobs
Tenant C: max 4 concurrent jobs, quota riêng theo hợp đồng
Shared overflow pool: controlled and fair
~~~

Con số minh họa. Các cơ chế:

- Concurrency/rate quota theo tenant.
- Weighted fair queue hoặc priority lanes theo business.
- Tính bytes-scanned/compute-seconds/storage theo tenant.
- Giới hạn dataset range và report size.
- Quyền cancel và expiration.
- Khi một tenant thật sự rất lớn, cân nhắc compute group/warehouse riêng.
- Alert khi tenant làm tăng queue age hoặc p99 của toàn reporting store.

**Report cost attribution** giúp phân biệt báo cáo tốn tiền vì nhiều dữ liệu hợp lệ với báo cáo tốn vì không được index/pruning.

## 31. Khi hệ báo cáo hỏng, không đẩy tải nặng sang primary

Một anti-pattern:

~~~text
Report cluster unavailable
  -> Admin API automatically reroutes all reports to OLTP primary
  -> OLTP primary receives large scans
  -> Transaction API starts timing out
~~~

Mục tiêu cô lập có thể bị phá đúng lúc hệ lỗi. Fallback cần phân loại:

- **Point lookup thực sự quan trọng:** có thể fallback đến primary với bounded concurrency, keyed access và deadline.
- **Heavy analytical query:** trả trạng thái chờ/tạm ngừng, không tự chạy primary scan.
- **Đã có snapshot export:** có thể trả artifact cũ với timestamp rõ.
- **Pipeline lag:** hiển thị watermark và thông báo, hoặc không cho chốt số final.
- **Admin operational emergency:** cho phép lệnh truy vấn đặc biệt theo quyền và quota riêng, có audit.

Khi một AZ/region lỗi, replica serving report có thể được promote làm source chính tùy topology. Khi đó cần tự động **ngừng hoặc giảm mạnh reporting traffic** để bảo vệ transaction workload của owner mới.

## 32. Recovery và tái dựng báo cáo sau lỗi

Một reporting store có thể được coi là **projection có thể rebuild** nếu nguồn chuẩn và event log còn. Nhưng “có thể rebuild” không có nghĩa nhanh hoặc miễn phí.

Cần:

- Snapshot hoặc export điểm bắt đầu.
- CDC/outbox retention đủ lâu để replay sau snapshot.
- Schema/transform version lưu bền.
- Index mapping và partitioning definition.
- Retryable/idempotent backfill.
- Throttling để không làm source production nghẽn.
- Checkpoints per shard và DLQ/poison event handling.
- Watermark và data quality checks sau rebuild.
- Kế hoạch trả dashboard stale/unavailable trong RTO.
- Backup/restore riêng cho artifacts hoặc reports final theo quy định.

Nếu nguồn log chỉ giữ 24 giờ nhưng projection ngừng chạy 48 giờ, không thể tự giả định có thể replay mọi sự kiện. Phải **re-snapshot/reconcile** hoặc có nguồn lưu trữ durable khác.

## 33. Khi nào cần một “bản chụp báo cáo đã chốt”?

Một số báo cáo không được thay đổi sau khi gửi cho kế toán/đối tác, ví dụ tổng hợp doanh thu đã quyết toán. Dashboard realtime là **view tiến hóa**, còn report finalized cần:

- Cutoff period và time zone.
- Data source versions/watermarks.
- Business definition/rule version.
- Currency exchange/rounding assumptions nếu áp dụng.
- Tổng/chi tiết được đối soát.
- Artifact checksum và immutable report ID.
- Ai phê duyệt, lúc nào và theo phiên bản nào.
- Cơ chế sửa sai: phát hành bản điều chỉnh, không sửa âm thầm file đã ký/đã gửi.

Một query chạy lại tuần sau có thể cho kết quả khác vì refunds, late events hoặc logic thay đổi. Đó không nhất thiết là lỗi; vấn đề là **report contract phải phân biệt live recomputation với finalized snapshot**.

## 34. Mẫu data contract cho một dataset báo cáo

~~~yaml
dataset: orders_reporting_daily
owner: data-platform
sourceOfTruth: order-service
purpose: "Daily order and revenue reporting"
grain: "tenantId, dateUTC, sku"
freshness:
  healthyTargetMinutes: 5
  exposeWatermark: true
consistency:
  provisional: "eventual projection"
  final: "reconciled after period close"
delivery:
  mode: "snapshot + CDC"
  duplicateHandling: "idempotent by eventId/version"
  deleteHandling: "tombstones and retention policy"
security:
  tenantScoped: true
  maskPii: true
  access: "report-read-only role"
operations:
  backfill: "checkpointed and rate-limited"
  dlq: "manual/automatic reconciliation"
  maxConcurrentHeavyQueries: 4
validation:
  - "reconcile by source IDs and cutoff"
  - "freshness lag p95/p99"
  - "no measurable regression of OLTP p99"
~~~

Đây là **YAML minh họa cho kiến trúc**, không phải cấu hình sản phẩm. Mỗi trường cần có owner rõ. “Provisional eventual” không đủ cho một báo cáo quyết toán chốt kỳ nếu tổ chức cần con số cuối; data contract phải quy định finalization.

## 35. MongoDB: secondary/reporting node chưa phải sandbox tuyệt đối

Một hướng là định tuyến reads cho admin tới secondaries hoặc nodes dùng cho analytics theo cơ chế được MongoDB deployment hỗ trợ. Nhưng cần nhớ:

- **Read preference** quyết định đường đọc, không mặc nhiên bảo đảm snapshot nhất quán với primary.
- Replica có thể lag; Order mới commit có thể chưa hiện trên secondary.
- Scan nặng có thể làm secondary áp replication log chậm.
- Một số topology có thể định hướng nodes phục vụ báo cáo theo tags/priority/hidden configuration, với implications cho elections và read routing.
- Nếu replica report hỏng, không tự fallback heavy scans sang primary.
- Index/long-running query/snapshot có thể tương tác với storage engine.
- Với sharded cluster, report query không target shards có thể scatter-gather.

Ví dụ query trên **reporting collection**:

~~~javascript
db.reportingOrders.aggregate([
  {
    $match: {
      tenantId: "t01",
      createdAt: {
        $gte: ISODate("2026-11-01T00:00:00Z"),
        $lt: ISODate("2026-12-01T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: "$status",
      orderCount: { $sum: 1 }
    }
  }
]);
~~~

Đây là query shape; phải xem index, query plan, phạm vi dữ liệu, timeout và resources. Một read replica cùng data model OLTP có thể vẫn không lý tưởng cho aggregates phức tạp. CDC/change streams đưa sang reporting cluster/warehouse có thể tách compute tốt hơn, nhưng phải đo lag và log retention của pipeline.

## 36. Cassandra/ScyllaDB: analytics DC và consistency scope

Trong các hệ họ Cassandra, có thể bố trí một data center dành cho reporting **nếu replication strategy, driver routing và consistency level phù hợp**:

~~~text
DC-OLTP:
  low-latency reads/writes
  transaction-facing APIs

DC-REPORT:
  replicas được định tuyến cho admin
  bounded scans/jobs và query quotas
~~~

Câu hỏi chính:

1. RF theo DC và placement theo racks/AZ?
2. Driver admin có thật gửi tới DC-REPORT?
3. Write consistency `LOCAL_QUORUM` ở DC-OLTP đã bảo đảm gì ở DC-REPORT?
4. Scan/token-range trên report DC có làm coordinator chậm hoặc gây tombstone/compaction backlog?
5. Report có truy vấn đúng partition key, clustering order không?
6. Repair/anti-entropy/replication lag ảnh hưởng SLO ra sao?
7. Khi report DC lỗi, có giữ được quy tắc **không fallback scan lên OLTP**?
8. Có cần ETL sang một analytical engine cho join/group nhiều chiều không?

Ví dụ một query có partition key hợp lệ **nếu schema được thiết kế tương ứng**:

~~~sql
SELECT event_id, event_time, event_type
FROM events_by_tenant_day
WHERE tenant_id = 't01'
  AND day_bucket = '2026-11-14'
LIMIT 100;
~~~

Không dùng `ALLOW FILTERING`/full scan một cách vô giới hạn trên giao dịch chỉ vì “query trả ít rows” sau filtering.

## 37. DynamoDB: Scan/parallel scan và read capacity

Trong DynamoDB, `GetItem`/`Query` theo key phù hợp với operational lookups; `Scan` trên table lớn có thể tiêu read capacity và tạo throttling cho traffic giao dịch nếu cùng nguồn/capacity.

- Parallel Scan có thể tăng tốc export nhưng **cũng tăng áp lực đồng thời**.
- Read capacity/quota tồn tại theo nhiều phạm vi; không suy một con số cố định cho mọi table mode.
- GSI hỗ trợ query khác nhưng tăng index write/storage cost và có freshness semantics riêng.
- DynamoDB Streams/CDC hoặc export ra object storage có thể phục vụ data pipeline và warehouse tùy yêu cầu.
- Một read eventual chỉ phù hợp nếu report cho phép stale; không dùng số tồn kho eventual để quyết định cấp hàng cuối.

Một hướng cho heavy export:

~~~text
Admin request
  -> durable job
  -> exported snapshot/reporting copy
  -> bounded workers
  -> query/scan với checkpoint
  -> object-storage artifact
~~~

Nếu phải scan source để backfill, phải dùng **rate limit và stop condition theo OLTP health**. Không chạy parallel scan tối đa trên production chỉ vì muốn export nhanh.

## 38. Redis: quét toàn keyspace có thể tranh event loop

Redis phục vụ key lookups và counters tốt trong nhiều trường hợp, nhưng một report quét hàng triệu keys hoặc chạy command có độ phức tạp cao có thể ảnh hưởng event loop, memory và network.

Anti-pattern:

~~~text
KEYS *
GET every key synchronously
aggregate inside one HTTP request
~~~

`SCAN` cho phép iteration nhưng không tạo snapshot toàn keyspace, có thể có duplicates hoặc thay đổi trong lúc key churn theo semantics. Tổng work vẫn lớn; Redis Cluster còn phải xét slots/nodes, còn replicas có lag/failover constraints.

Nếu Redis chỉ là cache, không nên dùng nó làm nguồn cuối cho audit/financial report. Có thể materialize counters từ event log vào reporting store/warehouse, giữ Redis cho hot operational access.

## 39. Chọn reporting model theo loại NoSQL query

| Query | Mô hình thường phù hợp hơn |
|---|---|
| Count Orders theo ngày | Daily aggregates hoặc columnar facts |
| Filter documents đa chiều | Indexed reporting projection hoặc search index |
| Trend events theo thời gian | Time-partitioned analytical store |
| Hành trình khách hàng nhiều bước | Warehouse events hoặc graph analytics |
| Traversal graph rất rộng | Graph analytical job / data copy |
| Top-K product popularity | Materialized rankings |
| Audit trail immutable | Append-only audit store |
| Admin point lookup | Operational key read có quota |

Không ép mọi báo cáo vào cùng transactional model chỉ vì nguồn đã chọn document, graph hay key-value store. **Access pattern** và **freshness semantics** quyết định hệ phân tích phù hợp.

## 40. Shared dependencies vẫn là kênh ảnh hưởng ngược

Hai clusters khác nhau có thể vẫn chia sẻ:

- Message broker phục vụ CDC.
- Network egress/ingress và logging/storage services.
- Account-level quota hoặc KMS/control plane.
- Source oplog/change stream throughput/retention.
- Authentication/API gateway.
- Scheduler/worker nodes.
- Object storage policy/cost.

Ví dụ:

~~~text
OLTP -> CDC broker -> Reporting cluster

Reporting consumers chậm
  -> broker backlog tăng
  -> connector retries mạnh
  -> network/log retention pressure trên source
  -> OLTP p99 xấu đi
~~~

**Cô lập phải xét dependency graph.** Một reporting cluster riêng giúp giảm read CPU/disk, nhưng không bảo đảm không có ảnh hưởng gián tiếp qua log capture, network hoặc shared services.

## 41. CDC backpressure: bảo vệ nguồn mà không làm mất events

Khi reporting consumer bị lag:

1. Có durable queue và log retention đủ cho khoảng gián đoạn?
2. Connector có thể pause/resume mà không làm mất changes?
3. Throttle consumer có gây áp lực tăng lên source không?
4. Broker đầy thì hệ báo lỗi, dừng, drop hay backfill? Hậu quả?
5. Có alert oldest unprocessed event age và per-partition lag?
6. Replay sau outage có rate limit tránh retry storm?
7. DLQ/quarantine được theo dõi và xử lý?
8. Tại mức lag nào báo cáo chuyển sang trạng thái stale/unavailable?

Một hệ có thể chấp nhận dashboard chậm thêm 20 phút khi report store lỗi, nhưng không chấp nhận Order transactions chậm toàn hệ. **Không drop CDC events âm thầm rồi vẫn công bố kết quả đầy đủ**; nếu log mất gap, phải resnapshot/reconcile.

## 42. Priority lanes cho quản trị

~~~mermaid
flowchart TD
    A["Admin users / scheduled jobs"] --> B["AuthN/AuthZ + tenant scope"]
    B --> C["Query templates + cost limits"]
    C --> D["Fair queue / priorities"]
    D --> E["Bounded reporting workers"]
    E --> F["Reporting data store"]
    F --> G["CSV / BI / dashboard"]
    H["OLTP health"] --> D
    I["CDC freshness"] --> D
~~~

Hai loại ưu tiên:

- **Operational support lookup:** keyed query nhỏ, cần phản hồi nhanh.
- **Heavy BI/export:** background job có thể hoãn, giới hạn concurrency và chi phí.

Nếu workload report còn chia sẻ dependencies với OLTP, có thể dùng OLTP health metrics để giảm reporting concurrency. Cần cooldown/hysteresis để tránh scheduler tăng giảm quá nhanh và tạo thundering herd.

## 43. Decision matrix để chọn mức cô lập

| Phương án | Freshness | Cô lập OLTP | Phù hợp | Đổi lại |
|---|---|---|---|---|
| Query nhỏ trên primary | Theo read policy | Thấp | Admin keyed lookup | Rủi ro khi query phát triển |
| Read replica riêng | Có thể lag | Trung bình tùy shared resources | Reads theo schema gốc | Lag, replication/election |
| Analytics DC/group | Có thể lag | Cao hơn nếu nodes độc lập | Workload phù hợp data model | Replication/cost |
| CDC → reporting NoSQL | Eventual theo pipeline | Cao | Operational dashboards | Consumers, dedup, repair |
| Export → warehouse/lake | Batch/stream | Cao với compute riêng | BI/joins/history | ETL, storage, query cost |
| Materialized aggregate | Theo update contract | Cao cho query định hình | Top-K/sums/trends | Consistency, rebuild |
| Background report job | Tùy nguồn | Tùy nguồn nhưng tránh HTTP scan | Large exports | Queue, quotas, artifacts |

Một report dùng replica riêng vẫn nên có query limit; một warehouse vẫn cần dữ liệu đúng/cutoff; một operational admin lookup quan trọng có thể được phép đọc primary theo key nếu tổng chi phí thấp.

## 44. Mục tiêu cô lập cần được đo bằng p99 giao dịch

Một thiết kế báo cáo chỉ thành công khi nó không làm hỏng các SLO cần bảo vệ. Ví dụ một hệ đặt trước tiêu chí **giả định**:

~~~text
OLTP:
  Checkout p99 <= 350 ms
  Successful commits >= 99.9% trong chế độ healthy
  No oversell / no duplicate payment effect

Reporting:
  Interactive dashboard p95 <= 2 s
  Heavy export được đưa vào job queue
  Data freshness <= 5 min khi pipeline healthy
  Jobs có thể bị hoãn khi OLTP degraded

Isolation criterion:
  OLTP p99 và error rate khi có báo cáo
  không vượt ngưỡng đã được thống nhất.
~~~

**Không lấy một số p99 tức thời** làm bằng chứng. Cần so nhiều khoảng tải, cân nhắc noise, cache, node placement, background compaction, warm-up, auto scaling, các giờ cao điểm và loại queries.

Một phép đo hay là **regression ratio**:

\[
R_{\mathrm{p99}} =
\frac{p99_{\mathrm{OLTP,\ with\ reports}}}
{p99_{\mathrm{OLTP,\ without\ reports}}}.
\]

Nếu baseline là 200 ms và khi báo cáo chạy là 320 ms, ratio = 1,6. Dù vẫn dưới SLO 350 ms, mức tăng 60% có thể báo trước thiếu headroom cho peak traffic. Ngưỡng chấp nhận phải được quyết định theo business budget trước khi thử; không có một ratio mặc định đúng cho mọi hệ.

## 45. Benchmark cô lập: có và không có báo cáo

Dùng cùng dữ liệu, topology và khối lượng giao dịch trên test environment đủ giống production:

| Kịch bản | Transaction load | Reporting load | Điều cần quan sát |
|---|---|---|---|
| A — Baseline | 1× normal | Không | p50/p95/p99, throughput |
| B — Single report | 1× normal | 1 heavy report | Regression và resource sharing |
| C — Concurrent reports | 1× normal | 5–10 reports | Quota, queue, max fan-out |
| D — Peak traffic | 2× peak model | Không | Headroom thực của OLTP |
| E — Peak + reports | 2× peak model | 5 reports | Report throttling có bảo vệ OLTP? |
| F — Report store lag | 1× normal | CDC lag 15 phút | Staleness và fallback |
| G — Report store down | 1× normal | Reports unavailable | Không fallback scan primary |
| H — Rebuild/backfill | 1× normal | Replay/backfill | Source log/CDC pressure |
| I — Failover | 1× normal | Report node/replica mất | Routing/promotion/bulkhead |

Tất cả khối lượng là **mẫu thiết kế**, không phải bắt buộc mọi team chạy 2×. Cần thử đúng peak và fault conditions mà hệ có khả năng chịu.

### 45.1. Chỉ số phải thu đồng thời

- Transaction end-to-end p50/p95/p99 và success/error/deadline.
- DB per-key/per-node CPU, read IOPS, disk queue, memory/cache miss.
- Read/write throttling, queue wait và connection pool saturation.
- Replication/CDC log lag, oldest unprocessed event age.
- Report query duration, bytes scanned, number of partitions, fan-out.
- Report worker concurrency và queue length/age.
- Materialized projection freshness/watermark.
- Duplicate/missing events và reconciliation drift.
- Chi phí network, storage, consumed read capacity/compute time.
- Số người dùng/tenants bị ảnh hưởng và mức nghiêm trọng nghiệp vụ.

Nếu report chạy nhanh hơn nhưng checkout p99 tăng, đó có thể là tối ưu **nhầm đối tượng**. Nếu OLTP ổn nhưng report luôn không hoàn thành, quota có thể quá chặt hoặc kiến trúc chưa đủ năng lực báo cáo. Phải đạt **hai hợp đồng khác nhau**.

## 46. Thí nghiệm phân tách nguyên nhân nghẽn

Một lần benchmark cho thấy checkout p99 tăng sau khi admin mở dashboard. Chưa nên kết luận ngay do database CPU.

Tiến hành theo lớp:

1. Quan sát **HTTP traces**: checkout chậm ở auth, pool wait, DB execution hay response?
2. Xem **query plan** của report: scan bao nhiêu records và indexes?
3. Đo **node/shard**: đâu là hot owner, có skew không?
4. Đo **replica lag**: report có làm replica áp log chậm?
5. Đo **CDC broker**: backlog có tăng và source connector có retry không?
6. Đo **connection pools**: report và transaction có chia pool?
7. Tắt **report load có kiểm soát** trong test: p99 hồi phục không?
8. Thử **rate limit** report: p99 biến đổi theo report concurrency thế nào?
9. Chuyển report sang dedicated replica/store: shared resource nào còn?
10. Kiểm tra **correctness/freshness** sau thay đổi: report có thiếu dữ liệu không?

Nếu bottleneck là connection pool, bulkhead có thể giúp ngay. Nếu bottleneck là primary disk scan, pool riêng không đủ. Nếu bottleneck là cross-region CDC bandwidth, một reporting cluster mới trong region khác có thể còn tăng chi phí mạng. **Chẩn đoán theo bằng chứng trước khi đổi kiến trúc.**

## 47. Fault injection: cô lập phải tồn tại cả khi một nhánh hỏng

Kịch bản trong lab:

~~~text
T0: OLTP và reporting bình thường.
T1: Báo cáo bắt đầu scan/export lớn.
T2: Dừng reporting store / tạo replica lag có kiểm soát.
T3: Quan sát Admin API behavior.
T4: Kiểm tra OLTP p99 và accepted writes.
T5: Phục hồi reporting store.
T6: Replay CDC/backfill theo quota.
T7: Đối soát watermark và business IDs.
~~~

Tiêu chí:

- Admin heavy requests không được tự chuyển sang scan primary.
- Reporting workers dừng/retry có giới hạn, không tạo storm.
- OLTP connection pool không bị report jobs chiếm hết.
- Pipeline lag được công bố, không hiển thị “data current” giả.
- Không có mất event không thể phục hồi sau replay.
- Một query export thất bại có thể resume hoặc báo failed rõ.
- Mỗi tenant không đọc dữ liệu tenant khác trong tình huống failover.
- Khi repair/backfill chạy, OLTP vẫn trong SLO hoặc hệ có guard tạm hoãn repair.

**Chỉ tạo faults trên môi trường được phép thử**. Không kill production nodes hoặc làm mất kết nối thật chỉ để chứng minh một ý tưởng; phương án diễn tập production phải tuân theo quy trình quản trị rủi ro riêng.

## 48. Migration từ report chạy trực tiếp sang isolated reporting

Một hệ legacy thường có:

~~~text
Admin UI -> API -> Production NoSQL
                     (scan/group/sort)
~~~

Có thể chuyển từng bước:

1. **Inventory** các report endpoints: input, query plans, tần suất, users, cost, data sensitivity.
2. **Phân loại** report nào là keyed lookup nhỏ, report nào scan/ad hoc.
3. **Đặt SLO và freshness contracts** cho từng nhóm.
4. **Giảm rủi ro ngay** bằng limit, deadline, concurrency quota, pool riêng.
5. **Thiết kế reporting schema** theo access patterns, tránh copy schema nguồn một cách máy móc.
6. **Dựng CDC/outbox/export pipeline** có checkpoints, DLQ và observability.
7. **Backfill** lịch sử theo snapshot+CDC handoff; không bỏ gap.
8. **Đối soát** counts/IDs/amounts theo cutoff.
9. **Shadow reads**: chạy báo cáo trên hai nguồn và so kết quả mà chưa đổi user response.
10. **Canary rollout** cho một số tenants/reports.
11. **Đo OLTP p99 và report cost**, freshness và correctness dưới tải.
12. **Chặn đường heavy scans cũ** sau khi đủ bằng chứng.
13. **Diễn tập report-store outage**, bảo đảm không fallback hại OLTP.
14. **Cập nhật runbook**, phân quyền, data lineage, retention và audit.

**Shadow compare cần cùng cutoff**. Nếu source thay đổi liên tục và reporting lag 2 phút, so hai snapshots ở hai thời điểm rồi đánh dấu mọi khác biệt là lỗi sẽ tạo nhiều false alarms.

### 48.1. Rollback không phải chuyển lại full scan primary vô điều kiện

Nếu projection lỗi, rollback có thể là:

- Tạm ngưng báo cáo nặng và trả trạng thái unavailable/queued.
- Trả kết quả finalized cũ với watermark.
- Chỉ cho operational point lookup trên source với quota chặt.
- Tạm bật report template ít tốn tài nguyên.
- Repair/rebuild projection rồi phát hành lại.

Không nên định nghĩa “rollback” là “mọi report quay về primary production” vì nó làm mất mục tiêu cô lập khi cần nhất.

## 49. Capacity và chi phí: đọc tách có thể rẻ hơn tổng thể

Một hệ cô lập có thêm storage/compute nhưng có thể giảm:

- CPU/IOPS cần dự phòng trên primary để chịu report peaks.
- Tỉ lệ timeout và thời gian incident của checkout.
- Chi phí ops do report full scans/bulk exports.
- Tải write do những index chỉ phục vụ analytics trên source.
- Truy vấn lặp lại cùng một aggregate không được materialize.
- Chờ kết quả của người dùng/admin.

Một mô hình chi phí đơn giản:

\[
C_{\mathrm{total}} =
C_{\mathrm{OLTP}} +
C_{\mathrm{replication/CDC}} +
C_{\mathrm{report\ storage}} +
C_{\mathrm{report\ compute}} +
C_{\mathrm{network}} +
C_{\mathrm{operations}}.
\]

So với chi phí:

\[
C_{\mathrm{shared}} =
C_{\mathrm{larger\ OLTP\ cluster}} +
C_{\mathrm{report\ queries}} +
C_{\mathrm{incidents}} +
C_{\mathrm{maintenance}}.
\]

Không thể suy một bên luôn rẻ hơn khi chưa đo workload, storage growth, data egress và cost of downtime. **Đừng hy sinh correctness hoặc SLA giao dịch chỉ để tiết kiệm một reporting replica**; cũng không dựng warehouse đắt tiền cho hai point lookup báo cáo nhỏ.

### 49.1. Ước tính fan-out và read workload

Giả sử một report quét 5 triệu records, mỗi record 2 KiB logic:

\[
5.000.000 \times 2\ \mathrm{KiB}
\approx 9{,}54\ \mathrm{GiB}.
\]

Đây là payload logic trước compression/index overhead. Mười report như vậy mỗi giờ có thể tạo khối lượng đọc lớn dù mỗi report cuối cùng chỉ trả 100 dòng tổng hợp. Một materialized aggregate có thể giảm lượng đọc trên **đường dashboard**, nhưng ETL phải chi trả một lần để duy trì aggregate và xử lý mọi updates.

Không chuyển trực tiếp GiB payload thành số read capacity units hay chi phí cloud khi chưa biết rounding, item size, consistency mode và pricing cụ thể.

## 50. Runbook khi report làm chậm giao dịch

Giả sử cảnh báo:

~~~text
Checkout p99:        180 ms -> 900 ms
Order write timeout: 0.2% -> 5%
Admin scan requests: 2 -> 60 concurrent
OLTP CPU average:    40% -> 85%
Replica lag:         1s -> 90s
~~~

Quy trình:

1. **Xác nhận phạm vi:** endpoints/tenants/partitions nào chậm?
2. **Ưu tiên business safety:** không giảm write consistency, không bỏ idempotency.
3. **Dừng nhận report nặng mới:** pause queue hoặc giảm concurrency.
4. **Cancel/limit đang chạy** theo công cụ an toàn, xem partial artifacts.
5. **Không fallback** heavy scans sang primary/replicas đang làm nguồn giao dịch.
6. **Xem nguồn nghẽn:** query plans, shared pools, CPU, disk, IOPS, network.
7. **Đánh giá replication/CDC lag:** projection có còn phục vụ được không?
8. **Ghi trạng thái report:** stale/queued/degraded; thông báo đúng người dùng.
9. **Đối soát job outcomes:** không duplicate exports, không thiếu events.
10. **Khôi phục theo quota nhỏ**, nâng dần khi p99 giao dịch hồi phục.
11. **Postmortem:** bổ sung guardrails, dashboard và fault test.
12. **Thẩm định architecture change:** replica riêng, ETL/materialization nếu nguyên nhân tái diễn.

Một cách sửa vội “tăng CPU primary” có thể giúp tạm thời nhưng che thiết kế sai; cần phân biệt immediate mitigation và long-term isolation.

## 51. Những hiểu nhầm thường gặp

| Hiểu nhầm | Vì sao sai | Cách tiếp cận |
|---|---|---|
| “Query read-only không ảnh hưởng write” | Dùng CPU, I/O, cache, connections | Đo shared resources |
| “Admin endpoint khác là đã cô lập” | Có thể cùng DB/pool | Phân tách resource ownership |
| “Read replica không dùng tài nguyên primary” | Replication/log/network vẫn liên quan | Xem shared dependencies |
| “Replica luôn mới như primary” | Có thể lag | Freshness contract/watermark |
| “Report replica lỗi thì tự fallback primary” | Có thể phá transaction SLA | Fail/defer heavy reports |
| “Thêm index phục vụ report là miễn phí” | Write amplification/storage | Cost model/index plan |
| “Query trả 5 dòng thì rẻ” | Có thể scan hàng triệu docs | Explain/bytes scanned |
| “Scan trên warehouse luôn an toàn” | Có thể làm nghẽn report users khác | Quota/cost admission |
| “Có CDC thì exactly once” | Redelivery/reorder/crash gaps | Idempotent consumer |
| “Snapshot rồi bật CDC sau là không mất gap” | Có handoff window | Checkpoint/retention protocol |
| “Max timestamp là watermark đầy đủ” | Có partitions/late events | Proven complete-through semantics |
| “Báo cáo T+1 nào cũng đủ cho checkout” | Checkout cần quyết định authoritative | Revalidate at source |
| “Read model là source of truth thứ hai” | Projection có lag/diff | Source ownership rõ |
| “Một report đúng hôm nay sẽ giống khi chạy lại” | Refund/late event/rules thay đổi | Finalized snapshot và version |
| “Hai nguồn cùng timestamp là snapshot global” | Không có transaction chung | Cross-source reconciliation |
| “RBAC ở UI đủ bảo mật” | API có thể bị gọi trực tiếp | Server-side authorization |
| “CSV quote đã tránh mọi formula injection” | Spreadsheet còn diễn giải formula | Escape/export text policy |
| “Có dedicated cluster nghĩa không còn shared risk” | Broker/network/quota có thể chung | Dependency analysis |
| “Tăng timeout sẽ bảo vệ OLTP” | Truy vấn giữ resources lâu hơn | Rate/concurrency budget |
| “Tắt báo cáo khi lỗi thì dữ liệu tự đúng” | CDC backlog/gap vẫn phải xử lý | Replay/reconcile |
| “Bất kỳ DBA scan nào cũng cần warehouse” | Keyed admin lookup nhỏ có thể an toàn | Phân loại access pattern |
| “Báo cáo được phép sai vì eventual” | Provisional khác final accounting | Data contract/finalization |

## 52. Bài tập A — Chọn kiến trúc cho hệ bán hàng

Một hệ có:

~~~text
NoSQL Orders source:
  100.000 Orders mới mỗi ngày
  Transaction read/write p99 SLO: 300 ms

Admin:
  GET Order theo ID: 2.000 lần/ngày
  Dashboard theo status/SKU: 20.000 lần/ngày
  Export 18 tháng Orders: 15 lần/tháng
~~~

Hãy:

1. Phân loại ba loại read: operational, aggregate hay heavy export.
2. Đề xuất đường đọc cho từng loại, có thể dùng primary/replica/projection/warehouse.
3. Giải thích vì sao một read replica có thể chưa đủ cho export 18 tháng.
4. Chọn freshness SLO và mức consistency mỗi loại.
5. Thiết kế report job API với statuses/expiration.
6. Xác định data model daily aggregate và cách chống duplicate events.
7. Đặt quota query và tenant-level access control.
8. Giả sử report cluster down, hệ phản hồi thế nào mà không ảnh hưởng checkout?
9. Đề xuất 5 metrics chứng minh isolation.
10. Viết test scenario cho peak traffic + 10 concurrent exports.

## 53. Bài tập B — CDC và reconciliation

Nguồn Order có:

~~~text
O1: version=3 CONFIRMED
O2: version=2 PENDING
O3: version=5 REFUNDED
O4: version=1 CONFIRMED
~~~

Reporting projection sau replay:

~~~text
O1: version=3 CONFIRMED
O2: version=2 PENDING
O3: version=4 CONFIRMED
O4: missing
~~~

Hãy:

1. Phân loại O3 là stale và O4 là missing theo cutoff tương ứng.
2. Giải thích vì sao cần cùng snapshot/cutoff khi đối soát.
3. Nêu cách replay O3 version 5 và O4 version 1 idempotent.
4. Nếu một duplicate event O1 v3 tới, consumer xử lý thế nào?
5. Nếu một delta O3 v5 đến trước v4, có thể áp thẳng không?
6. Thiết kế checkpoint per stream và DLQ.
7. Đặt watermark có ý nghĩa cho report.
8. Cách backfill khi CDC retention không còn event O4?
9. Làm sao hạn chế backfill load trên production?
10. Nêu khi nào có thể đánh dấu report period FINALIZED.

## 54. Bài tập C — Báo cáo làm tăng p99

Trong lab, bạn thấy:

| Metric | Không report | Khi chạy report |
|---|---:|---:|
| Checkout p99 | 180 ms | 630 ms |
| OLTP CPU | 45% | 78% |
| Pool checkout p99 | 5 ms | 280 ms |
| Replica lag | 1 s | 70 s |
| Report concurrency | 0 | 32 |

Giả sử checkout SLO là 350 ms. Hãy:

1. Tính p99 regression ratio.
2. Phân biệt ảnh hưởng pool wait và DB execution.
3. Giải thích vì sao secondary lag có thể liên quan tới report.
4. Đề xuất immediate mitigation không giảm consistency checkout.
5. Tách pool có giải toàn bộ vấn đề không? Vì sao?
6. Nếu giảm report concurrency từ 32 xuống 4, cần quan sát gì?
7. Có nên auto fallback report sang primary nếu secondary down không?
8. Một reporting store tách biệt cải thiện resource isolation nào?
9. Shared dependencies nào vẫn cần đo?
10. Định nghĩa PASS/FAIL cho test peak + report sau migration.

## 55. Câu hỏi tự kiểm tra

1. OLTP và reporting khác nhau ở kiểu truy cập và SLO nào?
2. Vì sao report “chỉ đọc” vẫn có thể làm writes chậm?
3. Cô lập API và cô lập database resources khác nhau ở đâu?
4. Khi nào keyed admin lookup có thể đọc từ transaction source?
5. Vì sao một read replica không đồng nghĩa cô lập vật lý hoàn toàn?
6. Replication lag ảnh hưởng read freshness của report thế nào?
7. Analytics DC giải quyết gì mà read replica cùng node không giải?
8. Vì sao same OLTP schema không lý tưởng cho mọi group-by?
9. CDC có thể bỏ event trong snapshot handoff nếu làm sai thế nào?
10. Outbox giúp bảo vệ source change event ở ranh giới nào?
11. At-least-once delivery cần idempotency để tránh double-count ra sao?
12. Full-state event khác delta event khi đến out-of-order thế nào?
13. Materialized daily revenue phải xử lý refund như thế nào?
14. Khi nào warehouse/lake phù hợp hơn một document replica?
15. Search index có thể trở thành hot spot do admin report không?
16. Report job nên có những trạng thái/timeout/quotas gì?
17. Vì sao không giữ HTTP request export hàng giờ?
18. Keyset pagination có lợi gì so với offset lớn?
19. Query result nhỏ có chứng minh query work nhỏ không?
20. Vì sao thêm index lên source có thể làm write p99 xấu?
21. Bulkhead/pool riêng ngăn loại contention nào?
22. Trường hợp nào quota theo tenant chưa đủ bảo vệ một query nặng?
23. Watermark khác max observed timestamp ở đâu?
24. Làm sao biết một report có consistent snapshot giữa hai sources?
25. Khi nào dữ liệu được gọi FINAL thay vì provisional?
26. Đối soát projection cần cùng cutoff vì sao?
27. Nếu source log retention không đủ, cần recovery nào?
28. Vì sao report cluster outage không được mặc định fallback primary?
29. Có những shared dependencies nào giữa source và warehouse?
30. RBAC, field masking và tenant filtering phải được enforce ở đâu?
31. CSV export có nguy cơ formula injection như thế nào?
32. Cần đo những metric nào để chứng minh reporting không phá checkout p99?
33. RPO/RTO của report projection có được khác source transaction không?
34. Một benchmark report-heavy nên gồm những failure scenarios nào?
35. Vì sao nên rollout theo shadow compare và canary?

## 56. Tổng kết: cô lập tải, nhưng giữ một sự thật nghiệp vụ

**Cô lập truy vấn quản trị hoặc báo cáo khỏi tải giao dịch** không chỉ là chạy query trên một hostname khác. Nó đòi xác định đường giao dịch nào phải được bảo vệ, tài nguyên nào đang bị chia sẻ, báo cáo thực sự cần độ mới/nhất quán đến đâu, và hệ sẽ phản ứng thế nào khi reporting pipeline hoặc replica gặp lỗi.

Một trình tự thực hành:

~~~text
1. Liệt kê access patterns giao dịch và báo cáo.
2. Đặt p95/p99, availability và freshness contracts.
3. Giới hạn query/query pool/job trước khi tối ưu lớn.
4. Chọn keyed source read, replica, projection hoặc warehouse.
5. Nếu tách dữ liệu, xây CDC/outbox/snapshot handoff đúng.
6. Thiết kế report schema và idempotent aggregates.
7. Gắn watermark, cutoff và reconciliation.
8. Đặt quyền truy cập, tenant quotas và artifact retention.
9. Không fallback heavy reports sang transaction primary.
10. Benchmark peak OLTP + concurrent reports + failure modes.
11. Quan sát p99, read cost, lag, errors và business correctness.
12. Chỉ công bố finalized reports sau khi đủ đối soát.
~~~

Một hệ NoSQL vận hành tốt phải cho phép cả giao dịch và phân tích phát triển, nhưng không để một yêu cầu báo cáo chạy lâu phá việc giữ hàng, thanh toán hoặc tra cứu quan trọng. **Mục tiêu cuối cùng là giao dịch được bảo vệ bởi SLO và bất biến, còn báo cáo được phục vụ bằng dữ liệu có nguồn gốc, độ mới và độ chính xác được công bố rõ ràng — với tài nguyên và chi phí được kiểm soát.**







