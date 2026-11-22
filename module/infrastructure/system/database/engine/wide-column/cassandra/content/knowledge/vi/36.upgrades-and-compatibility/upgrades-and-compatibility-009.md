# Kiểm tra schema, topology metadata và trạng thái background task khi nâng cấp Apache Cassandra

## 1. Vấn đề: node đã khởi động không có nghĩa nâng cấp đã hoàn tất

Apache Cassandra là cơ sở dữ liệu phân tán theo mô hình **wide-column**: dữ liệu được định tuyến bằng **partition key**, nhân bản theo replication strategy và truy vấn qua coordinator với **consistency level** (CL). Ứng dụng Java dùng CQL và driver để đọc/ghi, trong khi các node liên tục flush memtable, compaction SSTable, repair, xử lý hints và streaming khi topology thay đổi.

Trong chương **Nâng cấp và tương thích** của module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**, một vấn đề vận hành cốt lõi là: sau khi nâng cấp một hoặc nhiều node, cluster có còn **đồng thuận về schema, đúng topology/replica placement và kiểm soát được công việc nền** hay không?

Một node có thể báo **`UN`** trong `nodetool status` nhưng vẫn gặp:

- Schema chưa lan truyền đồng đều, khiến một số coordinator không hiểu bảng/cột mới.
- Danh sách peers, rack, datacenter hoặc tokens không giống thiết kế, dẫn tới định tuyến và replication sai mong đợi.
- Repair/compaction/streaming quá tải, làm p99 đọc/ghi và timeout tăng.
- Driver Java kết nối được nhưng một số prepared statement, CQL type hoặc protocol feature hoạt động khác kỳ vọng.
- SSTable cũ vẫn tồn tại hoặc công việc chuyển định dạng chưa được thực hiện theo hướng dẫn phiên bản.

Do đó, quy tắc quan trọng là:

> **Nâng cấp đạt yêu cầu khi trạng thái dữ liệu, topology, tác vụ nền và ứng dụng được kiểm chứng**, không chỉ khi một process Cassandra chạy lại.

Bài cung cấp quy trình kiểm tra có bằng chứng; **không thay thế release notes hoặc upgrade guide của cặp phiên bản nguồn/đích cụ thể**. Các lệnh và bảng hệ thống có thể khác giữa Cassandra 3.x, 4.x, 5.x, các bản vá và bản phân phối riêng.

## 2. Ba lớp cần kiểm chứng

| Lớp | Câu hỏi chính | Nguồn bằng chứng thường dùng | Hậu quả nếu bỏ qua |
|---|---|---|---|
| **Schema** | Các node có cùng định nghĩa keyspace, table, type, index và schema version hợp lệ không? | `cqlsh DESCRIBE`, `system_schema`, `nodetool describecluster`, driver metadata | Query lỗi, prepared statement invalid, tính năng CQL không nhất quán |
| **Topology metadata** | Host ID, node address, token, DC/rack, RF và peers có đúng như sơ đồ không? | `nodetool status`, `nodetool gossipinfo`, `system.local`, `system.peers`/`system.peers_v2` | Replica placement sai, CL không đạt, DC routing lỗi |
| **Background task** | Compaction, flush, streaming, repair, hints hoặc các stage có đang nghẽn không? | `nodetool tpstats`, `compactionstats`, `netstats`, logs/JMX/metrics, repair tracking | Disk đầy, p99 tăng, timeout, mất khả năng phục vụ khi nâng cấp tiếp |

Ba lớp này **phụ thuộc lẫn nhau**. Ví dụ một node boot lại với rack sai có thể làm topology không ổn định; nếu lập tức chạy repair hoặc thêm node khác, streaming và compaction có thể làm sự cố lan rộng.

~~~mermaid
flowchart TD
    A["Bắt đầu change window"] --> B["Kiểm tra release/upgrade path"]
    B --> C["Lưu baseline schema + topology + task metrics"]
    C --> D["Canary / nâng cấp một node theo runbook"]
    D --> E["Schema agreement và CQL smoke test"]
    E --> F["Topology: host ID, token, DC/rack, peers"]
    F --> G["Background: compaction, repair, stream, queues"]
    G --> H{"Mọi gate đạt?"}
    H -->|Có| I["Ghi bằng chứng, chuyển node kế tiếp"]
    H -->|Không| J["Dừng rollout, điều tra và xử lý theo playbook"]
    J --> E
    I --> K["Kiểm tra toàn cluster và ứng dụng sau upgrade"]
~~~

Trong môi trường hỗ trợ rolling upgrade, **mỗi node là một chốt kiểm tra**, nhưng thứ tự và trạng thái mixed-version được phép phải lấy từ **hướng dẫn chính thức cho đường nâng cấp đang thực hiện**.

## 3. Trước khi đo: xác định rõ ma trận tương thích

### 3.1. Những thứ cần phiên bản cụ thể

Không thể xây dựng một quy trình chính xác bằng cách chỉ biết “đang chạy Cassandra”. Trước khi bắt đầu, cần ghi nhận:

1. **Phiên bản nguồn và đích chính xác**, bao gồm patch release và bản phân phối.
2. **Đường nâng cấp được hỗ trợ**; không mặc định có thể nhảy từ 3.x sang 5.x hoặc trộn các bản tùy ý.
3. **Thời gian mixed-version được hỗ trợ**, hành vi schema agreement và lệnh vận hành bị hạn chế trong giai đoạn đó.
4. **Java runtime/JDK được hỗ trợ** cho từng Cassandra release, cấu hình GC, kernel và storage.
5. **Java Driver version**, CQL protocol negotiation, authentication, TLS và policy kết nối.
6. **SSTable format và quá trình nâng cấp SSTable** nếu release yêu cầu.
7. **Snitch, partitioner, token allocation, topology**, network protocol và cách mapping DC/rack.
8. **Tính năng CQL/DDL được sử dụng**: UDT, collections, indexes, LWT, CDC, views, counters, v.v.
9. **Downgrade/rollback policy**: một số bước có thể khiến quay lại binary cũ không còn được hỗ trợ.
10. **Backup có thể phục hồi** và phương án thay node/khôi phục khi upgrade thất bại.

**Đừng dùng ngày phát hành hoặc số major version để suy ra compatibility.** Ví dụ “4.x và 5.x cùng nói CQL” không bảo đảm mọi kết hợp rolling upgrade hoặc mọi Java Driver feature đều được hỗ trợ.

### 3.2. Ví dụ bảng kiểm kê trước nâng cấp

| Thuộc tính | Node A | Node B | Node C | Kết quả kỳ vọng |
|---|---|---|---|---|
| Cassandra version | V cũ | V cũ | V cũ | Phiên bản nguồn như kế hoạch |
| Datacenter | dc1 | dc1 | dc1 | Phù hợp bản đồ topology |
| Rack | rack1 | rack2 | rack3 | Phân bố đúng failure domain |
| Host ID | H-A | H-B | H-C | **Duy nhất**, không bị đổi ngoài ý muốn |
| Token ownership | Theo ring baseline | Theo ring baseline | Theo ring baseline | Không thay bất thường |
| Schema | Version S | Version S | Version S | Đồng thuận trước change |
| Task trạng thái | Ổn định | Ổn định | Ổn định | Không có tác vụ nguy hiểm chưa xử lý |
| Backup | Đã kiểm thử | Đã kiểm thử | Đã kiểm thử | Có phương án phục hồi phù hợp |

Đây là **schema kiểm kê minh họa**, không phải trạng thái của một cluster thật. Với vnodes, mỗi node có nhiều tokens; cột “token ownership” phải chứa danh sách/hash/đường dẫn lưu bằng chứng tương ứng, không chỉ một token đầu tiên.

### 3.3. Không nâng cấp khi điều kiện nền chưa ổn

Trước khi đụng binary, xem có:

- Node down hoặc `UJ`/`UL`/`UM` chưa xử lý xong.
- Schema không thống nhất.
- Hints/repair/streaming chưa hoàn tất theo yêu cầu runbook.
- Disk gần đầy, compaction backlog tăng lâu hoặc lỗi commit log/I/O.
- p99, timeout, unavailable hoặc dropped messages đã vượt SLO.
- Backup mới nhất chưa có bằng chứng restore, hoặc snapshot thiếu token coverage.
- Đang đồng thời thực hiện topology change, bulk import, backfill hoặc schema migration lớn.

Nếu có, **dừng để giải quyết** hoặc nhận quyết định thay đổi đã được đánh giá rủi ro rõ ràng. Nâng cấp không phải cách mặc định chữa một cluster vốn đang quá tải.

## 4. Schema agreement: khái niệm và giới hạn

### 4.1. Schema là trạng thái được lan truyền giữa các node

Schema Cassandra gồm keyspace, replication settings, table, columns, primary key, types, indexes, views và những đối tượng khác tùy phiên bản. Các node cần **đồng thuận** về schema để định tuyến và giải thích CQL đúng.

Khi thay đổi DDL, Cassandra phân phối thông tin schema theo cơ chế của release. Trong một thời gian ngắn, các node có thể chưa cùng phiên bản schema; driver thường có cơ chế đợi/kiểm tra agreement cho các thay đổi DDL nhất định.

Cần phân biệt:

- **Schema agreement:** các node liên quan đang báo phiên bản schema phù hợp với nhau.
- **Schema correctness:** định nghĩa CQL đúng với kỳ vọng ứng dụng.
- **Data correctness:** dữ liệu logic trong bảng còn đầy đủ/chính xác.
- **Protocol compatibility:** Java Driver và coordinator thực thi CQL theo đường được hỗ trợ.

**Agreement là điều kiện cần, không đủ**: toàn cluster có thể cùng đồng thuận về một schema *sai* vừa được triển khai.

### 4.2. Kiểm tra từ cqlsh

~~~cql
-- Chạy trong cqlsh kết nối đến một node/cluster được xác minh.
DESCRIBE KEYSPACE telemetry;

-- Những bảng hệ thống thường được dùng trong Cassandra hiện đại:
SELECT keyspace_name, replication, durable_writes
FROM system_schema.keyspaces
WHERE keyspace_name = 'telemetry';

SELECT table_name
FROM system_schema.tables
WHERE keyspace_name = 'telemetry';
~~~

`DESCRIBE` là lệnh **cqlsh**, không phải statement CQL dùng nguyên văn qua Java Driver. Thao tác `SELECT` trên `system_schema` có thể cung cấp thông tin cấu trúc khi phiên bản triển khai hỗ trợ các bảng/cột tương ứng.

**Không dựa vào `SELECT *` trên system table để tạo parser cross-version**: các bảng metadata và cột có thể thay đổi. Khi so sánh upgrade, ghi lại DDL chuẩn hóa và chỉ những field phù hợp.

### 4.3. Kiểm tra qua nodetool

~~~bash
# Xác minh bản nodetool và các lệnh trên node.
nodetool version
nodetool help

# Một số phiên bản hiển thị cluster info và schema versions.
nodetool describecluster
~~~

Thông tin từ `describecluster` có thể giúp phát hiện **nhiều schema version** trong một cluster tại thời điểm chụp. Nhưng:

- Output thay đổi theo release.
- Một node/gossip view có thể tạm thời không thấy peer.
- Schema version bằng nhau không chứng minh truy vấn nghiệp vụ đúng.
- Một số node down không phản hồi hoặc chưa hoàn tất schema propagation.
- Khi đang mixed-version, cách so sánh/diễn giải phải theo upgrade guide cụ thể.

Nên **đo lặp qua thời gian và từ các node đáng tin** thay vì kết luận từ một snapshot.

### 4.4. Những gì phải so sánh trong DDL

| Thành phần | Điều cần kiểm tra trước/sau | Vì sao quan trọng |
|---|---|---|
| Keyspace RF và replication strategy | `NetworkTopologyStrategy`, RF theo DC | Quyết định vị trí/đủ replica cho CL |
| `durable_writes` | Giữ theo chính sách độ bền | Ảnh hưởng đường commit log |
| Table primary key | Partition key, clustering columns, order | Quyết định token và truy vấn |
| Column definitions | Tên, type, static/regular, UDT | Driver codec và dữ liệu |
| Table options | Compaction, compression, TTL, gc_grace_seconds | Read/write amplification, tombstone, storage |
| Index/view | Tồn tại, trạng thái rebuild/tính tương thích | Truy vấn phụ và background load |
| Functions/aggregates | Chỉ khi được sử dụng và phiên bản hỗ trợ | Runtime, Java/UDF feature có thể khác |
| Authentication/role metadata | Quyền SELECT/MODIFY và resource scope | Ngăn app mất quyền hoặc quyền bị mở rộng |

Không chỉ so tên table. Một bảng cùng tên nhưng đổi clustering key, type hay RF có thể tạo lỗi đọc/ghi hoặc làm tải replica khác trước.

## 5. Ví dụ schema chuẩn để smoke test

Giả sử ứng dụng ghi telemetry theo thiết bị/ngày:

~~~cql
CREATE KEYSPACE telemetry
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE telemetry.events_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    metric_value double,
    PRIMARY KEY ((device_id, event_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);
~~~

Đây là **schema minh họa cho lab**, không phải yêu cầu tạo lại keyspace có sẵn trong production. Sau nâng cấp, chạy các truy vấn **read-only hoặc test writes vào bảng test riêng** đã được phê duyệt.

~~~cql
-- Trong cqlsh, dùng CL phù hợp với RF và datacenter test.
CONSISTENCY LOCAL_QUORUM;

SELECT event_time, metric_value
FROM telemetry.events_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
LIMIT 20;
~~~

Kiểm tra:

- CQL có parse được không và output đúng type/row count kỳ vọng không?
- Có phân biệt được lỗi `UNAVAILABLE`, read timeout, auth hay unknown table không?
- `LOCAL_QUORUM` có thể đạt với số replica khỏe trong DC không?
- Driver có nhận đúng metadata, codec và prepared statement không?
- Query vẫn dùng đầy đủ partition key, tránh `ALLOW FILTERING` hay full scan chỉ để smoke test.

**Không tạo/ALTER/DROP bảng trong lúc mixed-version nếu upgrade guide đang cấm DDL**. Tạo schema test phải diễn ra ở lab hoặc phase đã được phê duyệt.

## 6. Topology metadata: không chỉ là ba chữ UN

### 6.1. Các thuộc tính cần ghi baseline

Trong cluster Cassandra, mỗi node có:

- **Host ID**: danh tính node ở lớp Cassandra.
- **Addresses/ports**: địa chỉ gossip/internode, CQL/native transport và có thể nhiều endpoint tùy version.
- **Datacenter và rack**: từ snitch/topology config, ảnh hưởng replica placement.
- **Tokens**: các vị trí trên token ring xác định phạm vi dữ liệu.
- **Node state**: up/down, joining/leaving/moving và các trạng thái chuyển đổi khác.
- **Release version, schema version**: một phần của thông tin cluster nhìn thấy.
- **Pending ranges/streams** trong một số thao tác topology, theo công cụ/version.

Thay đổi hoặc đánh giá sai một thuộc tính có thể làm đứt kết nối, sai replica placement hoặc khiến việc nâng cấp trở thành topology migration không chủ đích.

### 6.2. Các lệnh đọc trạng thái

~~~bash
# Node ring, token ownership, datacenter/rack và trạng thái.
nodetool status

# Cluster view và schema versions, nếu được hỗ trợ.
nodetool describecluster

# Chi tiết gossip endpoint và trạng thái nhìn từ node.
# Output có thể lớn, nhạy với phiên bản và cần đọc có chọn lọc.
nodetool gossipinfo

# Thông tin node hiện tại, heap/uptime và trạng thái chung.
nodetool info

# Trạng thái streaming trong chuyển topology.
nodetool netstats
~~~

Các lệnh trên thường cung cấp **góc nhìn cục bộ/JMX**. Không cho rằng node A thấy B `UN` nghĩa node C cũng có cùng view ngay thời điểm đó.

### 6.3. Đọc `nodetool status` đúng cách

Một số mã trạng thái thường gặp:

| Ký hiệu | Ý nghĩa vận hành khái quát | Cần làm |
|---|---|---|
| **`UN`** | Up và Normal | Cần kiểm tra tiếp schema, read/write, task; chưa đủ để kết luận khỏe |
| **`DN`** | Down và Normal (trạng thái cuối được thấy) | Điều tra node/network, không tự nâng cấp node khác tùy ý |
| **`UJ`** | Up và Joining | Bootstrap/chuyển dữ liệu có thể chưa xong |
| **`UL`** | Up và Leaving | Node đang rời cluster |
| **`UM`** | Up và Moving | Token movement có thể đang diễn ra |
| **`?`** hoặc trạng thái khác | Tùy version và output | Đối chiếu help/logs, không đoán |

`UN` nói rằng node đang ở trạng thái **Up/Normal theo view đó**; nó không đảm bảo mọi SSTable đã nâng định dạng, repair hoàn tất hay p99 khỏe. Một node `UJ` có thể đang dùng rất nhiều disk/network để nhận SSTable.

### 6.4. Phân biệt token ring và topology vật lý

Với `NetworkTopologyStrategy`, replica placement phụ thuộc token và datacenter/rack. Token có thể phân bổ giữa nhiều vnodes; do đó:

- Không lấy một token để đại diện toàn bộ node.
- Không dùng địa chỉ IP làm suy luận vị trí trên ring.
- Không nhầm **Owns** hiển thị trong `nodetool status` với dung lượng vật lý chính xác hoặc quyền sở hữu duy nhất; con số có thể phụ thuộc replication/keyspace.
- Không suy từ “ba node trong DC” rằng RF đã đúng hoặc cả ba replica khỏe.
- Không thay snitch/rack config giữa upgrade nếu không có kế hoạch topology migration riêng.

Nếu replication factor bị thay đổi ngoài ý muốn, điều kiện `LOCAL_QUORUM` và khả năng chịu lỗi có thể thay đổi, ngay cả khi query CQL không thay.

## 7. `system.local`, `system.peers` và `system.peers_v2`

### 7.1. Metadata từ một node

Trong các phiên bản hỗ trợ, có thể kiểm tra trên **node đang kết nối**:

~~~cql
SELECT cluster_name, data_center, rack,
       host_id, release_version, schema_version
FROM system.local;
~~~

`system.local` mô tả thông tin **local của node cung cấp kết quả**. Nếu cqlsh kết nối qua proxy/load balancer, phải xác định chính xác coordinator mà bạn đang hỏi để không nhầm kết quả với node mong muốn.

Đối với peers, bảng system phụ thuộc phiên bản:

~~~cql
-- Nhiều môi trường có system.peers:
SELECT peer, data_center, rack,
       host_id, release_version, schema_version
FROM system.peers;

-- Một số bản Cassandra 4.x trở lên có thêm system.peers_v2,
-- chứa thông tin endpoint/port chi tiết hơn.
-- Hãy xác minh bảng/cột thật qua DESCRIBE trước khi dùng.
~~~

**Không mặc định truy vấn `system.peers_v2` chạy được trên Cassandra 3.x.** Tài liệu/command của một phiên bản không phải hợp đồng cho mọi release.

### 7.2. Một số metadata là view, không phải chân lý toàn cluster

`system.peers` hoặc `system.peers_v2` phản ánh những peer mà **node đang được hỏi** biết. Khi gossip chưa ổn định, lỗi mạng hoặc node đang joining, các view có thể khác nhau.

Khi kiểm tra topology metadata:

1. Ghi **node nguồn của kết quả**.
2. So cùng danh sách host IDs, DC/rack, phiên bản và schema versions giữa những node được chọn.
3. Kiểm tra node thiếu/duplicated, địa chỉ/port sai hoặc metadata stale.
4. So với sơ đồ topology dự kiến từ change plan.
5. Dùng `nodetool status` và logs để xác nhận peer thực sự UP/Normal.
6. Không tự sửa trực tiếp các bảng `system.local`/`system.peers` bằng CQL.

**Tự update/delete system tables** có thể phá gossip, token/host ID metadata hoặc các giả định của Cassandra. Nếu metadata sai, phải theo runbook của đúng phiên bản về replace node, snitch/rack hoặc remediation được hỗ trợ.

### 7.3. Đối chiếu token và host ID

Các bước thực dụng:

- Chụp `nodetool status` từ trước upgrade.
- Lưu host ID, DC/rack và danh sách token/vnode (qua công cụ được release hỗ trợ).
- Sau mỗi node upgrade, xác minh host ID **không bị thay thế ngoài ý muốn**.
- Nếu node mới boot với host ID khác, dừng rollout và phân biệt **replace đúng quy trình** với **mất metadata do nhầm data directory**.
- Nếu token ownership/rack thay đổi, điều tra ngay trước khi chạy repair, streaming hoặc upgrade node tiếp theo.

Không giả định thay IP đồng nghĩa host ID mới, và cũng không giả định node cùng địa chỉ IP chắc chắn giữ nguyên danh tính Cassandra.

## 8. Background tasks: còn backlog thì chưa thể nói đã sẵn sàng

### 8.1. Tác vụ nền quan trọng khi nâng cấp

| Tác vụ | Mục đích | Vì sao ảnh hưởng upgrade |
|---|---|---|
| **Memtable flush** | Chuyển dữ liệu từ RAM thành SSTable | Có thể gây disk write; backlog làm tăng áp lực commit log |
| **Compaction** | Merge SSTables, xử lý phiên bản/tombstone theo quy tắc | Tăng CPU/I/O và dung lượng tạm, ảnh hưởng p99 |
| **Repair** | Đối chiếu replica anti-entropy | Tiêu thụ CPU/disk/network; có thể truyền dữ liệu qua streaming |
| **Streaming** | Chuyển SSTable khi bootstrap/rebuild/repair/topology changes | Cạnh tranh disk và network giữa node |
| **Hints / hinted handoff** | Gửi bù mutation cho replica vắng mặt | Có thể tăng load khi node lên lại sau upgrade |
| **SSTable format upgrade** | Viết lại/đọc lại format theo yêu cầu release | Là I/O-heavy, có thể cần nhiều dung lượng tạm |
| **Index/view build** | Tạo hoặc xây lại cấu trúc phụ | Chi phí storage/CPU và thay đổi hành vi query |
| **Commit log replay** | Phục hồi memtable state chưa flush khi startup | Tăng thời gian node khởi động, cần theo dõi lỗi |

Không có một lệnh `nodetool` duy nhất hiển thị đầy đủ và chính xác **mọi** tác vụ nền. Cần kết hợp nhiều nguồn, logs và metrics.

## 9. `nodetool tpstats`: executor đang bận và message có bị drop?

~~~bash
nodetool tpstats
~~~

Các trường thường gặp:

| Trường | Ý nghĩa | Cách đọc đúng |
|---|---|---|
| `Active` | Số task đang thực thi | Cao có thể bình thường nếu throughput tốt |
| `Pending` | Task đang chờ trong queue | Quan trọng là **xu hướng tăng lâu hay giảm** |
| `Completed` | Tổng task đã hoàn thành trong phạm vi counter | Cần tính delta theo thời gian |
| `Blocked`, `All time blocked` | Thông tin blocked theo executor/release | Không nhầm với số kết nối mạng đang đợi |
| Dropped messages | Message bị drop theo loại | Đếm delta và so error/timeout, không coi là số CQL thất bại 1:1 |

Ví dụ hai ảnh chụp cách nhau 60 giây:

~~~text
Time    ReadStage Pending    Completed    READ dropped
10:00            20            500000              4
10:01           620            509000             64

Completed delta: 9.000 tác vụ / 60 s = 150 task/s
Pending tăng:    600
Dropped tăng:     60 message
~~~

Các tên stage/counter minh họa; release mới có thể dùng tên khác. Có thể nói **queue và dropped messages đang tăng**, nhưng chưa thể khẳng định nguyên nhân là thiếu thread: disk stall, network, GC, query scan hoặc streaming đều có thể gây chờ.

Nếu `tpstats` cho thấy stage mutation/flush nghẽn sau node restart, cần kiểm tra commitlog, heap/disk và tốc độ ghi trước khi chuyển sang nâng cấp node kế tiếp.

## 10. `nodetool compactionstats`: backlog và dung lượng tạm

~~~bash
nodetool compactionstats
~~~

Trong nhiều phiên bản, lệnh hiển thị pending compactions và thông tin những tác vụ đang chạy, có thể gồm keyspace/table, bytes processed/total hoặc progress.

### 10.1. Những câu hỏi cần trả lời

- Pending tasks có **giảm khi node khỏe trở lại** hay tăng liên tục?
- Có compaction lớn đang chạy trên bảng hotspot?
- Disk free trên node có đủ cho **SSTable output** khi SSTable nguồn chưa được giải phóng không?
- Có compaction/sstable rewrite do upgrade hoặc repair cùng hoạt động?
- Read p99 và SSTables per read có xấu đi không?
- Có I/O error, file corruption hoặc failed compaction trong logs không?

Ví dụ **giả định**:

~~~text
10:00  pending compactions = 8
10:10  pending compactions = 50
10:20  pending compactions = 160
       disk free            = 13%
       read p99             = 900 ms
~~~

Đây là tín hiệu **không nên vội nâng cấp node tiếp theo**. Nhưng không được kết luận từ pending=160 rằng phải tăng compaction concurrency: nếu disk bão hòa, tăng thread có thể làm tình hình xấu thêm.

### 10.2. Lệnh đổi định dạng SSTable là một thao tác riêng

Một số đường nâng cấp yêu cầu hoặc khuyến nghị chạy **`nodetool upgradesstables`** sau khi tất cả node đã lên release đích và đáp ứng điều kiện của upgrade guide. Lệnh này có thể **viết lại SSTable**, tiêu tốn disk/CPU và dung lượng tạm.

~~~bash
# CHỈ XEM TRỢ GIÚP khi điều tra; không tự chạy trên production.
nodetool help upgradesstables

# Tránh chạy upgradesstables khi chưa có phê duyệt,
# tính toán headroom và hướng dẫn chính thức cho version pair.
~~~

**Khởi động binary mới thành công không có nghĩa mọi SSTable đã chuyển format.** Ngược lại, không phải mọi lần nâng cấp đều yêu cầu lập tức rewrite toàn bộ SSTable. Cần đọc tài liệu release và giữ khả năng rollback trước khi kích hoạt công việc không thể đảo ngược.

## 11. `nodetool netstats`: streaming và chuyển topology

~~~bash
nodetool netstats
~~~

Lệnh này có thể hiển thị các session **SSTable streaming** đang gửi/nhận, file/bytes transferred, peer và progress tùy phiên bản.

Phân biệt:

- **Streaming:** chuyển dữ liệu trong bootstrap, rebuild, replace, một số pha repair.
- **Replica messaging/CQL:** traffic từ coordinator đến replica cho request thường.
- **Gossip:** thông tin membership/trạng thái.
- **Driver-to-coordinator:** traffic từ ứng dụng Java.

`netstats` **không phải thống kê tất cả các loại traffic mạng**. Nếu không có stream, Cassandra vẫn có thể đang chịu tải CQL, gossip hoặc hints.

Ví dụ có hai ảnh chụp cùng một session:

~~~text
11:00:00 transferred = 120 GiB
11:02:00 transferred = 126 GiB

Average rate over 120 seconds
= 6 GiB / 120 s ≈ 51,2 MiB/s
~~~

Nếu session thay đổi hoặc tổng bytes được tính lại, không trừ số của hai phiên khác nhau. Tiến độ 95% cũng **không đồng nghĩa** còn đúng 5% thời gian; còn phụ thuộc file size, network và bước hoàn tất.

### 11.1. Khi node đang Joining

Nếu `nodetool status` báo `UJ`, node có thể chưa sở hữu dữ liệu đầy đủ để phục vụ trách nhiệm tương lai. Phải theo dõi `netstats`, logs và trạng thái node; không chỉ thấy process UP rồi đưa vào rollout tiếp.

### 11.2. Khi repair đang chạy

Một số pha repair không có streaming liên tục. `netstats` trống **không chứng minh repair đã hoàn tất**. Theo dõi repair status/logs và metrics phù hợp phiên bản, tránh suy từ một lệnh.

## 12. Hints, flush, commit log và repair: nguồn tải dễ bỏ sót

### 12.1. Hints sau node restart

Trong rolling upgrade, một node có thể vắng mặt tạm thời. Các replica/coordinator khác có thể lưu hints cho những mutation cần gửi bù khi node quay lại, nếu cấu hình và điều kiện cho phép.

Khi node được đưa trở lại:

- Hints delivery có thể tạo burst ghi/network.
- Node vừa restart có thể đồng thời replay commit log, flush/compaction.
- Nếu hệ thống còn read/write traffic cao, p99 có thể xấu hơn baseline.
- Hints **không thay thế repair** trong mọi trường hợp mất kết nối dài hoặc replica sai lệch.

Trước khi nâng cấp node kế tiếp, cần có bằng chứng cluster đã đủ khỏe và công việc nền đã trở lại mức chấp nhận; không mặc định “UP trở lại” đồng nghĩa đã nhận đủ mọi mutation.

### 12.2. Flush và commit log

Sau restart, commitlog replay có thể kéo dài. Cassandra dùng commit log để phục hồi mutation chưa flush thành SSTable khi log còn hợp lệ. Nếu disk chậm, flush/compaction backlog tăng và commitlog segments khó thu hồi.

Theo dõi:

- Startup/replay logs, node readiness và CQL health.
- Disk free ở **data** và **commitlog** volumes.
- Flush pending queues qua `tpstats`/metrics.
- Write latency, unavailable/timeout, I/O errors.
- SSTables count và compaction backlog.

Không xóa commit log/SSTable thủ công chỉ vì thấy disk sử dụng cao; chúng có thể chứa dữ liệu chưa an toàn.

### 12.3. Repair readiness

Trước nâng cấp, phải biết lịch và trạng thái repair. Repair giúp anti-entropy giữa các replica, nhưng có thể tạo I/O/network lớn.

Trong mixed-version:

- Không tự chạy full cluster repair hoặc thay cấu hình repair nếu upgrade guide hạn chế.
- Không kéo dài thời gian vắng mặt replica đến mức vi phạm policy repair/hints/tombstone mà không đánh giá rủi ro.
- Không cho rằng `LOCAL_QUORUM` đọc thành công chứng minh mọi replica đã đồng bộ.
- Nếu repair dang dở, ghi task/phase, owner và kế hoạch xử lý trước khi restart node.

### 12.4. Ghi nhận trạng thái các background jobs không có output đơn nhất

Một bảng checklist node trước khi tiếp tục:

| Task | Trạng thái xác nhận | Nguồn |
|---|---|---|
| Flush | Pending ổn/giảm | `tpstats`, metrics |
| Compaction | Không backlog nguy hiểm | `compactionstats`, disk telemetry |
| Streaming | Không session bất thường | `netstats` và logs |
| Repair | Không đang dở theo quy trình | Repair logs/metrics/management tools |
| Hints | Delivery không quá tải | Hints metrics/logs |
| Commitlog replay | Hoàn thành, không I/O error | Startup logs, readiness |
| Index/view build | Đã kết thúc hoặc được phép tiếp tục | Tool/logs theo version |
| SSTable format | Đúng phase và version policy | Upgrade guide, tooling |

**“Không thấy lỗi” không phải trạng thái kiểm chứng.** Ghi rõ nguồn bằng chứng và thời điểm, hoặc đánh dấu **UNKNOWN**.

## 13. Workflow nâng cấp có chốt kiểm tra từng pha

### 13.1. Pha A — Pre-upgrade baseline

Trước khi thực hiện thao tác có thể làm thay đổi dữ liệu hoặc metadata:

1. Xác minh supported upgrade path, rollback/downgrade và JVM/driver requirements.
2. Chụp schema: DDL, `system_schema`, schema versions và danh sách đối tượng.
3. Chụp topology: `nodetool status`, host IDs, tokens, DC/rack, RF, peers metadata.
4. Chụp background: `tpstats`, `compactionstats`, `netstats`, repair/hints/flush.
5. Chụp performance: QPS, read/write p50/p95/p99, errors, timeouts, disk/network/GC.
6. Xác minh backup/snapshot và quy trình khôi phục được thử gần đây.
7. Xác nhận cluster không có node down/topology change chưa kết thúc.
8. Ghi thời điểm UTC, người chịu trách nhiệm và giới hạn thay đổi.

### 13.2. Pha B — Canary/một node được nâng cấp

**Thao tác dừng/khởi động service, drain, thay binary và cấu hình phải do runbook của đúng cặp phiên bản quyết định**. Bài này không khẳng định một chuỗi lệnh shutdown áp dụng cho mọi release.

Sau khi node được đưa lên:

- Kiểm tra process/readiness và logs, không chỉ TCP port 9042 mở.
- Xác minh node đúng release, host ID, DC/rack, tokens và `UN`.
- Kiểm tra schema agreement và CQL smoke test.
- Kiểm tra driver vẫn nhận metadata và query/codec đúng.
- Kiểm tra `tpstats`/`compactionstats`/`netstats` và log lỗi.
- Xác nhận replica còn đủ cho CL thực tế của ứng dụng.
- Đánh giá các task cần chờ hoàn thành theo upgrade guide trước khi tiếp tục.

### 13.3. Pha C — Trong thời gian mixed-version

Khi cả node cũ và mới cùng chạy (nếu đường upgrade cho phép):

- **Giữ đúng giới hạn feature/DDL/protocol** theo release notes.
- Tránh schema changes không được phép hoặc không cần thiết.
- Không chạy bước nâng SSTable format, repair lớn hoặc rollback có nguy cơ phá tương thích nếu guide chưa cho phép.
- Không nâng nhiều node đồng thời vượt số lượng outage mà RF/CL có thể chịu.
- Theo dõi từng DC/rack để tránh làm mất quorum cùng lúc.
- Tăng cảnh giác với driver errors/retries và topology drift.
- Ghi phiên bản từng node để không nhầm trạng thái rollout “chưa xong” với lỗi.

### 13.4. Pha D — Post-upgrade toàn cluster

Sau khi tất cả node đã hoàn tất phiên bản đích:

1. Kiểm tra cluster membership, host IDs, tokens, DC/rack và RF không lệch kế hoạch.
2. Kiểm tra schema agreement và so DDL với baseline, có giải thích cho mọi thay đổi.
3. Chạy smoke test đọc/ghi **trên workload phù hợp** với quyền và an toàn dữ liệu.
4. Kiểm tra driver compatibility, prepared statement, LWT nếu ứng dụng dùng, counters và paging.
5. Kiểm tra `tpstats`, compaction, streaming, hints, repair và flush không bị nghẽn.
6. Chỉ chạy bước nâng SSTable format hoặc tính năng mới sau khi đáp ứng gate chính thức.
7. Theo dõi p50/p95/p99 và timeout đủ lâu để thấy tải thực.
8. Cập nhật tài liệu version, trạng thái backup, hình thái topology và rollback policy.

## 14. Java Driver 4.x: kiểm chứng metadata và một truy vấn

Đừng chỉ thử `cqlsh`; ứng dụng Java có thể dùng protocol negotiation, prepared statements, codec và authentication khác. Một đoạn test có mục tiêu là **kết nối đúng cluster, đọc metadata và thực thi query dựa trên partition key**.

~~~java
import com.datastax.oss.driver.api.core.CqlIdentifier;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.metadata.Metadata;
import com.datastax.oss.driver.api.core.metadata.Node;

import java.net.InetSocketAddress;
import java.time.LocalDate;
import java.util.UUID;

public final class UpgradeSmokeTest {
    public static void main(String[] args) {
        // Ví dụ dành cho LAB hoặc endpoint đã được phê duyệt.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress(
                    "10.50.0.11", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            Metadata metadata = session.getMetadata();
            if (!metadata.getKeyspace(
                    CqlIdentifier.fromCql("telemetry")).isPresent()) {
                throw new IllegalStateException(
                    "Expected keyspace telemetry was not found");
            }

            for (Node node : metadata.getNodes().values()) {
                System.out.println(
                    "nodeId=" + node.getHostId() +
                    " dc=" + node.getDatacenter() +
                    " rack=" + node.getRack());
            }

            PreparedStatement ps = session.prepare(
                "SELECT event_time, metric_value " +
                "FROM telemetry.events_by_device_day " +
                "WHERE device_id = ? AND event_day = ? LIMIT 10"
            );
            BoundStatement bound = ps.bind(
                    UUID.fromString(
                        "11111111-1111-1111-1111-111111111111"),
                    LocalDate.of(2026, 11, 21))
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM);

            Row first = session.execute(bound).one();
            System.out.println(
                "SELECT completed; firstRowPresent=" + (first != null));
        }
    }
}
~~~

Đây là ví dụ **Java Driver 4.x API**, không chứng minh cấu hình TLS/auth/driver phù hợp production. `node.getHostId()` và metadata snapshot phản ánh **view mà driver biết**, có thể trễ sau topology change; không được coi driver metadata là nguồn duy nhất xác định membership.

Lưu ý quan trọng:

- Nếu bảng test không có row khớp, `first == null` là hợp lệ; xác minh query đã thực thi, không tự ghi “dữ liệu bị mất”.
- `LOCAL_QUORUM` yêu cầu keyspace RF và số node khỏe phù hợp trong DC cục bộ.
- Contact point và local DC phải thuộc **cluster đích**, không nhầm giữa lab và production.
- Với ứng dụng thực, cần kiểm tra những query shape và codec thật sự sử dụng, không chỉ một `SELECT`.
- Nếu dùng async/paging, LWT, collections/UDT, cần smoke test riêng cho từng tính năng quan trọng.
- Mỗi version pair phải đối chiếu bảng **compatibility của Java Driver và Cassandra** do nhà phát hành cung cấp.

### 14.1. Điều cần phân biệt về schema agreement ở driver

Driver có thể theo dõi/kiểm tra schema agreement và refresh metadata. Nhưng:

- Một metadata snapshot cập nhật trễ không chắc server schema sai.
- Query thành công trên một coordinator không chứng minh mọi node đều cùng schema.
- Truy vấn DDL và keyspace metadata thay đổi trong lúc mixed-version có thể có ràng buộc riêng.
- Không dùng cơ chế retry DDL liên tục để “ép schema agreement” khi gossip/metadata chưa khỏe.

Nếu driver báo lỗi liên quan schema, cần chụp phiên bản driver, coordinator, statement template, schema versions và logs thay vì xóa cache/prepare indiscriminately.

## 15. Phân tích tình huống: schema agreement không đạt

**Tình huống:** Sau nâng cấp node B, `nodetool describecluster` còn báo hai schema versions, trong khi A/C vẫn xử lý request.

### Bước 1 — Ghi lại trạng thái thay vì thay DDL

Lưu timestamp UTC, version của A/B/C, `nodetool status`, các schema versions và logs của node B. Không chạy `ALTER TABLE` ngẫu nhiên để làm thay đổi hash/version.

### Bước 2 — Xác minh connectivity/gossip và node membership

Đảm bảo B đúng DC/rack, host ID, address và không ở `UJ` hoặc `DN`. Kiểm tra `gossipinfo` và network errors nếu có.

### Bước 3 — So DDL và metadata theo từng view

Kiểm tra `DESCRIBE KEYSPACE`, `system_schema` và metadata từ node cần thiết. Nếu chỉ một node chưa nhận schema mới, xác minh thời gian propagation và lỗi trong log; nếu DDL khác nhau thật, không tự chọn “phiên bản mới nhất” theo timestamp mà bỏ qua compatibility.

### Bước 4 — Kiểm tra hỗ trợ của version pair

Trong mixed-version, schema transport và các tính năng CQL được phép có thể bị giới hạn. Đối chiếu hướng dẫn chính thức, không ép dùng DDL mới nếu node cũ chưa hiểu.

### Bước 5 — Dừng rollout đến khi có bằng chứng

Chỉ nâng cấp node tiếp theo khi schema, topology, application smoke test và task queues đạt gate được phê duyệt. Nếu không khắc phục được, thực hiện phương án rollback/recovery **có xét compatibility của SSTable và metadata**, không đơn giản đổi binary về bản cũ.

## 16. Phân tích tình huống: node UN nhưng topology metadata khác baseline

**Tình huống:** Node B khởi động lại và báo `UN`. Tuy nhiên `data_center` hoặc `rack` của nó không giống baseline, hoặc một host ID mới xuất hiện.

Giả thuyết cần điều tra:

- Snitch/rack config vô tình thay đổi khi thay package.
- Tệp config bị reset hoặc mount sai.
- Data directory/system metadata không đúng, khiến node được xem như danh tính khác.
- Thao tác replace node chưa được thực hiện theo quy trình.
- Gossip view cũ hoặc peer metadata chưa cập nhật.
- Địa chỉ/port internode khác bản cũ, dẫn tới trạng thái kết nối không ổn.

Quy trình an toàn:

1. **Dừng upgrade node tiếp theo.**
2. So file cấu hình/manifest từ change plan với thông số đang chạy bằng công cụ đã phê duyệt; worker của bài này chỉ nêu phương pháp, không cần sửa cấu hình thực.
3. Chụp `nodetool status`, `gossipinfo`, `system.local` và peers view.
4. Xác nhận host ID, DC/rack, tokens/placement và nguyên nhân drift.
5. Không “sửa” system tables bằng CQL để ép host ID hoặc token.
6. Dùng runbook **restore đúng identity/replace node** của phiên bản nếu cần.
7. Xác minh RF/CL, dữ liệu và streaming/repair sau khi khôi phục membership.

**Một node có tên/IP giống cũ nhưng host ID hoặc tokens khác** có thể tạo nguy cơ dữ liệu/replication lớn hơn một kết nối client đơn giản thất bại.

## 17. Phân tích tình huống: compaction và streaming kéo dài sau upgrade

**Tình huống:** Upgrade node A đã hoàn tất theo process status. Nhưng sau 30 phút, compaction pending từ 5 lên 140, `netstats` cho thấy receiving stream lớn, write p99 tăng và disk free giảm.

### Điều tra theo thứ tự

1. **Tìm nguồn streaming:** node có đang joining/rebuild/repair/replace không? Stream có đúng kế hoạch upgrade không?
2. **Đo compaction:** `compactionstats` cho biết active tasks có tiến triển hay backlog tăng không?
3. **Đo disk I/O:** await/p99, free bytes, write throughput, throttle và I/O errors.
4. **Đo executor:** `tpstats`, pending/dropped messages trên read/mutation/flush stages.
5. **Đo ứng dụng:** p95/p99, timeout/unavailable, driver retries và in-flight requests.
6. **Kiểm tra log/version:** công việc viết lại SSTable có được upgrade guide yêu cầu không, hay là tác vụ độc lập?
7. **Ra quyết định pause:** không nâng node tiếp theo nếu stop conditions bị vi phạm; cân nhắc giảm workload không thiết yếu theo runbook.

### Không làm gì?

- Không tự xóa SSTable cũ hoặc commit log để “giải phóng disk”.
- Không tự tăng compaction concurrency nếu storage đã bão hòa.
- Không hạ write/read CL để che timeout mà không đánh giá correctness.
- Không dừng streaming/repair bằng thao tác tùy ý nếu đang phục hồi replica.
- Không chạy `upgradesstables` thêm chỉ vì phát hiện SSTable cũ mà chưa có headroom và upgrade policy.

**UN + background backlog lớn = chưa đủ bằng chứng sẵn sàng tiếp tục rollout.**

## 18. Dashboard và gate đo lường

### 18.1. Baseline mẫu minh họa

| Metric | Baseline trước upgrade | Gate theo dõi minh họa |
|---|---:|---|
| API read p99 | 80 ms | Không vượt SLO đã phê duyệt |
| API write p99 | 35 ms | Không vượt SLO đã phê duyệt |
| Timeout rate | 0,05% | Không tăng vượt error budget |
| Worst-node data disk free | 38% | Không giảm dưới ngưỡng an toàn thực tế |
| Compaction pending | 5–15 | Xu hướng không tăng vô hạn |
| Stage pending/dropped | Ổn định | Không có tăng bất thường kéo dài |
| Streaming sessions | Không có ngoài lịch | Các task có owner, tiến độ và lý do |
| Schema versions | Đồng thuận | Theo gate phiên bản và trạng thái node |
| Host IDs/DC/rack | Đúng baseline | Không có drift không giải thích được |

**Các số liệu là giả định để minh họa cách lập gate**, không phải ngưỡng Cassandra mặc định. Trong thực tế, tài liệu change phải định nghĩa khoảng quan sát và số mẫu đủ để quyết định.

### 18.2. Phân biệt snapshot và xu hướng

`nodetool tpstats` và `compactionstats` tại một thời điểm có thể che spike vừa xảy ra. Cần:

- Thu ít nhất vài snapshot theo thời gian, cùng node và cùng version.
- Tính delta của counters (ví dụ Completed, Dropped), không xem giá trị tuyệt đối là throughput.
- Ghi reset do node restart trước khi tính delta; counter có thể về 0.
- So metric có **cùng scope và đơn vị**, không trừ p99 của coordinator cho p99 của driver để suy ra network latency.
- Không tính p99 toàn cluster bằng trung bình các p99 từng node; cần gộp histogram/phân bố phù hợp.
- So đồng thời p99 **và** timeout/error; request chậm đã timeout có thể biến khỏi histogram thành công.

### 18.3. Ví dụ phiếu kết quả sau mỗi node

~~~text
CHANGE ID:
Node/host ID:
Expected DC/rack/tokens:
Source version -> target version:
Upgrade guide/path reference:
Timestamp UTC:

Schema:
  describecluster schema versions:
  keyspace/table/UDT smoke check:
  DDL diff explained? PASS/FAIL/UNKNOWN

Topology:
  nodetool status:
  host ID preserved? PASS/FAIL/UNKNOWN
  DC/rack/tokens match baseline? PASS/FAIL/UNKNOWN
  peer metadata consistent? PASS/FAIL/UNKNOWN

Background:
  tpstats active/pending/dropped trend:
  compactionstats pending/progress:
  netstats sessions/owner:
  repair/flush/hints/replay status:

Application:
  Java Driver version/protocol tested:
  read/write p99:
  timeout/unavailable:
  prepared statement/UDT/LWT/paging tests:

Decision:
  GO / HOLD / ROLLBACK-PLAN
  Approver / evidence links:
~~~

Có thể ghi **UNKNOWN** nếu chưa đủ bằng chứng. Không tự đổi thành PASS chỉ vì node có vẻ hoạt động.

## 19. Những sai lầm thường gặp

| Nhận định/hành động | Vì sao sai | Cách làm phù hợp |
|---|---|---|
| “Node UN nghĩa là upgrade hoàn thành.” | Không xác minh schema, task, driver hoặc data | Dùng đủ ba lớp gate |
| “describecluster chỉ có một schema version nên schema đúng.” | Tất cả node có thể đồng thuận về schema sai | So DDL/invariant với baseline |
| “system.peers là topology chân lý toàn cluster.” | Là view local, có thể stale | So nhiều node, status và change plan |
| “Host ID đổi sau restart là bình thường.” | Có thể là sai data dir/replace ngoài ý muốn | Dừng rollout, điều tra identity |
| “dc/rack không quan trọng nếu mọi node UP.” | Replication placement phụ thuộc topology | So snitch, DC/rack và RF |
| “Đọc dữ liệu OK nghĩa là mọi replica đồng bộ.” | CL có thể cho phép một số replica chậm | Đánh giá repair/replica health |
| “netstats trống nghĩa là hết traffic mạng.” | CQL/gossip/hints không phải SSTable streaming | Dùng network và driver metrics |
| “repair xong khi netstats trống.” | Repair có các pha không stream | Dùng repair status/logs |
| “pending compaction cao thì tăng threads.” | Disk đã bão hòa có thể xấu hơn | Kiểm tra I/O, headroom và tiến độ |
| “Nâng cấp SSTable format ngay sau node đầu tiên.” | Có thể phá rolling compatibility/rollback | Theo guide của version pair |
| “Mọi driver nói CQL đều dùng được với mọi release.” | Protocol/feature/codec hỗ trợ khác nhau | Kiểm thử đúng driver/version matrix |
| “Tắt kiểm tra schema để giảm lỗi.” | Che vấn đề, không sửa schema propagation | Điều tra gossip/metadata và DDL |
| “Có backup nhưng chưa restore vẫn đủ.” | Backup có thể thiếu file hoặc không tương thích | Diễn tập restore vào cluster cô lập |
| “Trung bình p99 node là p99 cluster.” | Percentile không có tính cộng | Gộp histogram đúng cách |
| “Thay binary về version cũ luôn rollback được.” | SSTable/metadata có thể đã đổi | Theo rollback policy và backup |

## 20. Bài tập và tình huống có đáp án

### Câu 1 — Schema version

Sau khi nâng node B, `nodetool describecluster` báo hai schema versions. Có thể lập tức nâng C vì B đã `UN` không?

**Đáp án:** Không. Cần xác minh schema agreement, gossip, version compatibility và DDL diff; node `UN` không giải quyết sự không thống nhất schema.

### Câu 2 — Host ID

Node khởi động lại sau nâng cấp với IP cũ nhưng host ID khác trước. Đây chỉ là thay đổi thẩm mỹ?

**Đáp án:** Không. Có thể là node mới/replace không đúng, sai data directory hoặc metadata. Cần dừng rollout, xác minh token/identity và runbook hỗ trợ trước khi tiến hành.

### Câu 3 — Đọc `system.local`

Bạn kết nối CQL vào node A và đọc `system.local`. Có thể coi kết quả là thông tin local của node B đang được nâng không?

**Đáp án:** Không, trừ khi xác nhận truy vấn thực sự được thực thi trên B. `system.local` gắn với node cung cấp dữ liệu; cần biết endpoint/coordinator.

### Câu 4 — Bản 3.x và `peers_v2`

Một runbook viết cho 4.x yêu cầu truy vấn `system.peers_v2` trên cluster 3.x. Có bảo đảm bảng tồn tại không?

**Đáp án:** Không. Metadata schema thay đổi theo phiên bản; kiểm tra tài liệu và bảng có thật trên source release, dùng phương án phù hợp.

### Câu 5 — Completed counter

`ReadStage Completed` tăng từ 1.000.000 lên 1.012.000 trong 60 giây. Tốc độ công việc hoàn thành khoảng bao nhiêu?

**Đáp án:** `12.000/60 = 200` task/s. Không mặc định đó là 200 CQL SELECT/s vì một request có thể tạo nhiều task nội bộ.

### Câu 6 — Compaction sau upgrade

Node B có pending compactions tăng, disk free còn 8% và write p99 tăng gấp nhiều lần. Nên tăng compaction concurrency ngay?

**Đáp án:** Không. Disk I/O và temporary space có thể là bottleneck. Dừng rollout, đo resource và giảm áp lực theo runbook trước khi tuning.

### Câu 7 — Streaming

`nodetool netstats` không có session. Có thể kết luận không còn bất kỳ tác vụ nền hoặc network nào không?

**Đáp án:** Không. Compaction, flush, hints, gossip, CQL và một số pha repair không nhất thiết xuất hiện như SSTable stream.

### Câu 8 — Schema agreement và nghiệp vụ

Mọi node có cùng schema version nhưng một cột trong DDL đã bị chuyển sang type không phù hợp trước upgrade. Có thể coi schema đạt không?

**Đáp án:** Schema có thể **agreement**, nhưng **correctness** sai. Phải so DDL với baseline và test codec/query nghiệp vụ.

### Câu 9 — Mixed-version

Sau node đầu, đội muốn dùng ngay một tính năng CQL chỉ có trên release đích. Có nên bật trên toàn ứng dụng không?

**Đáp án:** Không cho đến khi upgrade guide xác nhận feature dùng được trong mixed-version và các node đáp ứng điều kiện. Thường cần chờ đúng phase và test protocol/driver.

### Câu 10 — RF và CL

Keyspace RF=3, ứng dụng dùng `LOCAL_QUORUM` trong DC1. Nếu hai replica DC1 bị dừng đồng thời khi nâng cấp, điều gì xảy ra?

**Đáp án:** Không thể đạt quorum hai trên ba khi chỉ còn một replica có thể phản hồi; request có thể unavailable/timeout. Phải lập lịch outage theo RF/CL và khả năng phục vụ.

### Câu 11 — SSTable format

Một operator muốn chạy `nodetool upgradesstables` ngay sau khi nâng node đầu để “dọn dẹp”. Có phải lệnh đọc trạng thái không?

**Đáp án:** Không. Lệnh có thể rewrite SSTables, tốn I/O và ảnh hưởng rollback/mixed compatibility. Chỉ chạy ở phase/version được hướng dẫn và đã dự trù headroom.

### Câu 12 — Repair và netstats

`netstats` trống, nhưng logs vẫn nói repair đang validation. Có mâu thuẫn không?

**Đáp án:** Không. Repair có nhiều pha; validation không bắt buộc tạo streaming session liên tục. Cần repair status/logs đúng phiên bản.

### Câu 13 — Driver metadata

Java Driver thấy 3 node và keyspace tồn tại. Có thể kết luận mọi prepared statement của ứng dụng đã tương thích version mới không?

**Đáp án:** Không. Metadata view chỉ là một tín hiệu; cần test statement, types/UDT, paging, LWT, retries và protocol negotiation trong workload thật.

### Câu 14 — Kết quả p99 “đẹp hơn” sau nâng cấp

p99 successful reads giảm từ 400 ms xuống 100 ms, nhưng timeout rate tăng từ 0,1% lên 5%. Đây có phải thành công?

**Đáp án:** Không. Các request chậm có thể timeout và bị loại khỏi latency histogram thành công. Gate phải xét **cả latency, error budget và throughput**.

## 21. Checklist tóm tắt trước khi cho node tiếp theo

~~~text
UPGRADE GATE — Cassandra node N
--------------------------------
[ ] Đúng supported source -> target version pair.
[ ] Mixed-version restrictions/rollback đã được đọc và áp dụng.
[ ] Backup/restore, quorum/availability plan sẵn sàng.
[ ] Node có host ID đúng, DC/rack đúng, tokens đúng.
[ ] nodetool status cho node và peers hợp lý; không có topology drift.
[ ] system.local / peers metadata không có sai lệch chưa giải thích.
[ ] Schema agreement đạt theo điều kiện version pair.
[ ] DDL diff đối chiếu baseline; không có thay đổi schema ngoài kế hoạch.
[ ] Java Driver version/protocol và CQL smoke tests đạt.
[ ] tpstats Pending/Dropped không tăng bất thường.
[ ] compactionstats không có backlog/disk pressure nguy hiểm.
[ ] netstats/repair/streaming có trạng thái và owner rõ ràng.
[ ] Commit log replay, flush, hints và I/O errors được kiểm tra.
[ ] Disk free, CPU/GC, network và read/write p99 trong ngưỡng.
[ ] Timeout/unavailable/retry không vượt error budget.
[ ] Có timestamp UTC, evidence, quyết định GO/HOLD và người duyệt.
~~~

Không nên máy móc “chờ tất cả pending bằng 0” nếu một số background task hợp lệ luôn tồn tại. Gate phải dựa trên **mức nền, xu hướng, tác động SLO và quy tắc upgrade**.

## 22. Tổng kết

Kiểm tra nâng cấp Cassandra có ba trụ cột:

1. **Schema:** kiểm tra agreement *và* DDL correctness; metadata cùng version chưa đủ bảo đảm query nghiệp vụ đúng.
2. **Topology:** so host IDs, tokens, DC/rack, RF, peers, gossip và trạng thái `UN`/`UJ` với baseline; không tự sửa system tables hoặc nhầm IP với node identity.
3. **Background task:** theo dõi `tpstats`, `compactionstats`, `netstats`, flush, repair, hints, commit-log replay, SSTable rewrite cùng disk/network/GC.
4. **Version compatibility:** mọi lệnh, bảng metadata, protocol feature và đường rolling upgrade phải được đối chiếu **đúng release pair**; không mặc định 3.x/4.x/5.x giống nhau.
5. **Client correctness:** smoke test Java Driver bằng prepared statements, partition key và CL thật của ứng dụng, thay vì chỉ kiểm tra port CQL đang mở.
6. **Operational gating:** ghi baseline, nâng theo pha có thể kiểm chứng, dùng GO/HOLD theo bằng chứng và giữ rollback/recovery plan.
7. **Quan sát chất lượng người dùng:** p50/p95/p99, throughput, timeouts và error budget là một phần của upgrade success.

Câu hỏi kết thúc mỗi bước không phải **“Cassandra đã chạy lại chưa?”**, mà là **“các node có cùng schema đúng, giữ nguyên topology được kỳ vọng, các tác vụ nền đang trong khả năng chịu tải, và Java client vẫn đọc/ghi đúng theo consistency đã thiết kế hay chưa?”**. Chỉ khi trả lời được bằng số liệu và bằng chứng mới nên tiếp tục nâng cấp node tiếp theo.
