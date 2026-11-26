# Đọc từ replica, sửa khác biệt và ảnh hưởng của repair

> **Chương:** Tính nhất quán  
> **Công nghệ:** Apache Cassandra, CQL, Spring Data Cassandra, `CassandraRepository`, `CassandraTemplate` và Java driver.  
> **Trọng tâm:** cơ chế coordinator đọc dữ liệu từ replica, phát hiện digest mismatch, reconciliation và read repair; phân biệt read repair với anti-entropy repair, đồng thời đánh giá consistency, chi phí, tombstone, TTL và tác động vận hành.

## 1. Tình huống: cùng một thiết bị nhưng hai lần đọc ra hai giá trị

Một nền tảng IoT lưu thông tin trạng thái thiết bị trên ba bản sao trong cùng datacenter:

~~~text
Replication factor (RF) = 3

Replica A: battery_percent = 68
Replica B: battery_percent = 68
Replica C: battery_percent = 72  (chưa nhận write mới)
~~~

Ứng dụng vừa ghi giá trị pin `68`, nhưng một số request GET sau đó vẫn trả `72`. Nguyên nhân có thể nằm ở replica được chọn, consistency level, replica chưa nhận mutation, write đã timeout sau khi ghi một phần, hoặc một sự cố đồng bộ.

Những câu hỏi cần giải đáp:

1. Coordinator có thể hỏi bao nhiêu replica cho mỗi read?
2. Nếu kết quả từ các replica không giống nhau, Cassandra chọn dữ liệu nào?
3. **Read repair** có sửa mọi replica không, có làm GET chậm hơn không?
4. **Anti-entropy repair** sử dụng Merkle trees khác read repair ra sao?
5. Nếu dữ liệu đã xóa bằng TTL/tombstone, sửa khác biệt không đúng lúc có thể làm dữ liệu cũ xuất hiện lại không?

Trong Spring Data Cassandra, repository, template và driver chỉ cung cấp API thực thi truy vấn. Chính **server Cassandra, replication strategy và consistency policy** quyết định bản sao nào được đọc và sửa.

## 2. Mục tiêu sau bài học

Sau khi đọc bài, bạn có thể:

- Phân biệt **replica**, **coordinator**, **partition key**, **RF**, **CL**, **full read** và **digest read**.
- Giải thích vì sao `LOCAL_ONE` có thể thấy giá trị cũ hơn so với `LOCAL_QUORUM`.
- Mô tả digest mismatch, hòa giải theo mutation timestamp/tombstone và read repair.
- So sánh `read_repair = 'BLOCKING'` và `'NONE'` từ Cassandra 4.0 cùng đánh đổi monotonic quorum reads với partition-level write atomicity.
- Phân biệt **read repair**, **hinted handoff** và **anti-entropy repair**.
- Giải thích cách incremental/full repair so sánh token ranges qua Merkle trees và đồng bộ dữ liệu bằng streaming.
- Hiểu quan hệ giữa repair interval, `gc_grace_seconds`, TTL và zombie data.
- Đặt CL phù hợp trong Spring Data repository/Java driver và xây test trên cluster nhiều replica.
- Đề xuất cách giám sát repair mà không làm quá tải cluster.

**Điểm mấu chốt:** một read thành công không chứng minh toàn bộ cluster đã đồng bộ, và một job repair được lên lịch không chứng minh nó đã hoàn thành mọi token range.

## 3. Schema ví dụ và nơi dữ liệu được nhân bản

Giả sử có ba node trong datacenter `dc1`. Keyspace dưới đây chỉ là mẫu; chỉ chạy nếu cluster có topology phù hợp:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry.device_state_by_id (
    tenant_id       uuid,
    device_id       uuid,
    battery_percent int,
    firmware        text,
    updated_at      timestamp,
    PRIMARY KEY ((tenant_id), device_id)
);
~~~

Tên datacenter phải lấy từ server thực tế. `NetworkTopologyStrategy` phân phối replica theo datacenter được cấu hình; `RF=3` nghĩa là dữ liệu liên quan được nhân bản trên ba replica của datacenter trong ví dụ.

Với bảng trên:

- `tenant_id` là partition key.
- `device_id` là clustering column, giúp định vị row trong partition của tenant.
- Các cột `battery_percent`, `firmware` và `updated_at` là dữ liệu của row.

Đây là mô hình **đơn giản để giải thích replication**. Với tenant có hàng triệu thiết bị, partition chỉ theo `tenant_id` có thể rất lớn. Production phải thiết kế partition key theo access pattern và kích thước partition thực tế, không copy schema demo vô điều kiện.

Query đọc một row:

~~~sql
SELECT battery_percent, firmware, updated_at
FROM telemetry.device_state_by_id
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND device_id = 22222222-2222-4222-8222-222222222222;
~~~

Dù API dùng `findById`, `@Query` hay `CqlSession`, Cassandra vẫn định tuyến query theo partition key và thực thi read ở CL được cấu hình.

## 4. Replica không nhất thiết đồng nhất tại mọi thời điểm

Trong một write thông thường, coordinator gửi mutation tới replica liên quan. Nhưng hệ thống phân tán có những tình huống:

- Một node tạm offline hoặc mất kết nối.
- Một replica nhận mutation nhưng replica còn lại chưa kịp nhận.
- Write request timeout trong khi một phần replica đã ghi.
- Hints không còn được giữ hoặc chưa được phát lại.
- Node vừa phục hồi sau downtime dài.
- Có update/delete/TTL khiến một số replica có cell/tombstone mới hơn.
- Dữ liệu bị mất hoặc hỏng trên một node, cần đồng bộ lại.
- Các writer đồng thời ghi các cell với mutation timestamps khác nhau.

Cassandra dùng nhiều cơ chế giúp replica hội tụ: read repair khi đọc, hinted handoff cho những write bị lỡ và anti-entropy repair theo token ranges.

Điều quan trọng không phải “có khi nào replica lệch?” mà là **người dùng cần độ mới dữ liệu đến mức nào, và hệ thống có cơ chế/giám sát để sửa sai lệch kéo dài hay không**.

## 5. Consistency level: một, quorum và tất cả replica

Với RF=3 trong cùng datacenter:

| CL | Số phản hồi cần thiết trong ví dụ | Ý nghĩa vận hành |
| --- | --- | --- |
| `ONE` | 1 replica | Ít replica tham gia, có nguy cơ stale read |
| `LOCAL_ONE` | 1 replica local | Đọc tại datacenter gần ứng dụng |
| `TWO` | 2 replica | Số lượng đặt tường minh |
| `QUORUM` | 2 replica | Đa số trên tập replica theo phạm vi QUORUM |
| `LOCAL_QUORUM` | 2/3 replica local | Đa số trong datacenter local |
| `ALL` | Cả 3 | Khó đáp ứng khi một replica bị lỗi/chậm |

Quorum của RF=3:

~~~text
quorum = floor(RF / 2) + 1
       = floor(3 / 2) + 1
       = 2
~~~

Với write `LOCAL_QUORUM` và read `LOCAL_QUORUM`, cả hai thao tác đều yêu cầu hai replica local xác nhận. Trong điều kiện RF ổn định, không có write đồng thời xung đột và các timestamp được quản lý đúng:

~~~text
W + R > RF

W=2, R=2, RF=3
2 + 2 = 4 > 3
~~~

Tập replica đọc và tập đã xác nhận write có ít nhất một replica giao nhau. Điều này hỗ trợ tính chất đọc thấy một write đã hoàn tất ở quorum.

**Cảnh báo:** công thức giao nhau không biến Cassandra thành transaction SQL. Với nhiều datacenter, `QUORUM` và `LOCAL_QUORUM` có phạm vi khác; write timeout có thể đã ghi một phần; timestamp/tombstone và write đồng thời vẫn phải được phân tích.

## 6. Coordinator, full-data read và digest read

Một request GET ở CL cần nhiều replica thường có luồng đơn giản hóa:

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant Coord as Coordinator
    participant A as Replica A
    participant B as Replica B
    App->>Coord: SELECT, CL=LOCAL_QUORUM
    Coord->>A: Full-data read
    Coord->>B: Digest read
    A-->>Coord: Dữ liệu row
    B-->>Coord: Digest/hash
    Note over Coord: So sánh hash
    Coord-->>App: Trả dữ liệu nếu khớp và đạt CL
~~~

Trong đường đọc thông thường, coordinator nhận **full data** từ một replica và digest từ replica khác để so sánh mà không cần truyền toàn bộ dữ liệu nhiều lần. Nó tính digest của full data và đối chiếu với các digest.

Nếu digest khớp, coordinator có thể trả kết quả sau khi đủ CL. Nếu digest khác, nó yêu cầu thêm full data, hòa giải và có thể tiến hành read repair.

Tùy Cassandra version, dynamic snitch, speculative retry và topology, coordinator có thể liên hệ những replica khác nhau. Sơ đồ mô tả cơ chế căn bản, không phải cam kết thứ tự RPC trong mọi cluster.

Ở `ONE`/`LOCAL_ONE`, một replica trả full data có thể đã đủ CL; thông thường không cần thêm digest để so sánh, nên một lần đọc `ONE` không tự phát hiện khác biệt giữa tất cả replica.

## 7. Digest mismatch và reconciliation

Giả sử hai replica trả trạng thái khác nhau:

~~~text
Replica A:
  battery_percent = 68, write timestamp t2
  firmware        = 1.2.3, write timestamp t1

Replica B:
  battery_percent = 72, write timestamp t1
  firmware        = 1.2.4, write timestamp t3

t3 > t2 > t1
~~~

Coordinator không đơn giản lấy nguyên row của “node mới nhất”. Cassandra hòa giải dữ liệu theo cơ chế mutation/cell timestamps, tombstones, TTL và quy tắc xử lý xung đột.

Kết quả hợp nhất trong ví dụ:

~~~text
battery_percent = 68   (t2 thắng t1)
firmware        = 1.2.4 (t3 thắng t1)
~~~

Một tombstone có timestamp phù hợp có thể thắng giá trị cũ. Không thể kết luận “node nào có nhiều cột hơn thì đúng hơn” hoặc “replica trả lời sau cùng thì giá trị mới nhất”.

**Cần phân biệt `updated_at` của domain và Cassandra writetime:** cột thời gian do ứng dụng lưu không tự quyết định xung đột của cell. Nếu client tự đặt write timestamp, sai lệch đồng hồ hoặc chính sách timestamp không thống nhất có thể làm các giá trị hội tụ không như người dùng mong đợi.

## 8. Read repair: sửa replica trong lúc đọc

Nếu digest mismatch, coordinator có thể yêu cầu full data từ replica khác, so sánh phiên bản, rồi gửi mutation để sửa bản sao lạc hậu trong phạm vi truy vấn.

~~~mermaid
sequenceDiagram
    participant App as Client
    participant Coord as Coordinator
    participant A as A (battery=68)
    participant B as B (battery=72)
    App->>Coord: SELECT, LOCAL_QUORUM
    Coord->>A: Full-data read
    Coord->>B: Digest read
    A-->>Coord: battery=68
    B-->>Coord: Digest khác
    Coord->>B: Full-data read
    B-->>Coord: battery=72
    Note over Coord: Reconcile theo timestamp
    Coord->>B: Repair mutation battery=68
    B-->>Coord: Ack
    Coord-->>App: battery=68
~~~

Ở chế độ `BLOCKING` của Cassandra 4.0+, read repair được thực hiện trong foreground và read chờ đủ xác nhận repair theo CL trước khi trả kết quả.

Nhưng repair qua một lần đọc **có phạm vi hạn chế**:

- Chỉ những replica được đọc/liên hệ phù hợp với yêu cầu và cơ chế repair mới có cơ hội được sửa.
- Chỉ phạm vi row/cell mà query liên quan được xem xét.
- Replica C không tham gia read quorum vẫn có thể lưu bản cũ.
- Những partition chưa từng đọc không tự được sửa.

Read repair giúp cải thiện hội tụ cho **dữ liệu nóng được truy cập**, nhưng không thay thế anti-entropy repair của toàn cluster.

## 9. Vì sao LOCAL_ONE có thể trả dữ liệu cũ?

Giả sử:

~~~text
Replica A: 68
Replica B: 68
Replica C: 72

GET #1 tại LOCAL_ONE chọn A -> 68
GET #2 tại LOCAL_ONE chọn C -> 72
~~~

Hai lần GET có thể trông như dữ liệu “quay về” giá trị cũ, vì chỉ một replica đủ trả lời và không có bước so digests với replica khác trong read thông thường.

Điều này **không** có nghĩa LOCAL_ONE luôn stale. Cluster ổn định có thể khiến mọi replica đã đồng bộ và trả cùng kết quả. Vấn đề là consistency level không yêu cầu kiểm chứng nhiều replica cho một read, nên API không được hứa độ mới mà nó không bảo đảm.

Dữ liệu ít nhạy với độ mới có thể dùng `LOCAL_ONE` để giảm chi phí/latency. Với workflow cần xác nhận write vừa hoàn tất trước khi bước tiếp, nên chọn CL đọc/ghi phù hợp với yêu cầu và kiểm thử latency/availability.

## 10. Table option read_repair: BLOCKING và NONE

Từ **Apache Cassandra 4.0**, tùy chọn bảng `read_repair` có hai giá trị quan trọng:

| Mode | Cơ chế | Tính chất cung cấp | Đánh đổi |
| --- | --- | --- | --- |
| `BLOCKING` | Khi read repair bắt đầu, coordinator chờ repair writes đạt CL trước khi trả | **Monotonic quorum reads** | Read có thể chậm khi replica lệch hoặc chậm; không giữ tính chất partition-level write atomicity theo trường hợp mô tả |
| `NONE` | Coordinator hòa giải phiên bản để trả kết quả nhưng không phát repair mutations do read đó | **Partition-level write atomicity** theo tài liệu | Không cung cấp monotonic quorum reads theo cùng nghĩa |

Theo tài liệu Cassandra 4.x/5.x, `BLOCKING` là mặc định. Cassandra 3.x có hành vi/cấu hình read repair cũ, **không** áp hai table options của 4.x cho 3.x mà không xác minh phiên bản.

Ví dụ schema:

~~~sql
CREATE TABLE IF NOT EXISTS telemetry.read_repair_demo (
    id uuid PRIMARY KEY,
    status text
) WITH read_repair = 'BLOCKING';
~~~

Ví dụ thay policy sau khi đã đánh giá (chỉ trên môi trường cho phép):

~~~sql
ALTER TABLE telemetry.read_repair_demo
WITH read_repair = 'NONE';
~~~

Không tự đổi hàng loạt table sang `NONE` để làm p99 đẹp hơn. Đó là sự thay đổi tính chất consistency mà application có thể đang dựa vào.

## 11. Monotonic quorum reads: hai lần đọc không “lùi” trong kịch bản được bảo vệ

Ví dụ:

~~~text
RF=3. A, B, C ban đầu đều giữ v1.

Write v2 bị timeout:
  A đã nhận v2
  B và C vẫn giữ v1

Read quorum #1 chọn A và B:
  Digest mismatch.
  Reconcile ra v2.
  Với BLOCKING, read repair đưa v2 sang B để đạt quorum.
  Client nhìn thấy v2.

Read quorum #2 chọn B và C:
  B đã có v2.
  Trong kịch bản này, client không quay về v1.
~~~

Đây là ý nghĩa của monotonic quorum reads được mô tả trong tài liệu. Nếu `read_repair='NONE'`, coordinator có thể trả v2 ở Read #1 nhưng không sửa B; lần đọc tiếp theo gặp B+C có thể trả v1 trong một số tình huống.

Monotonic quorum reads **không đồng nghĩa linearizability đầy đủ**. Một write đồng thời mới, timestamp client bất thường hoặc nhiều partition vẫn cần cơ chế giải quyết riêng.

## 12. Tính nguyên khối khi ghi nhiều row trong một partition

Cassandra cố gắng cung cấp tính chất write atomicity trên phạm vi partition cho một số kiểu mutation/batch. Nhưng read repair chỉ tác động tới dữ liệu **được SELECT**.

Giả sử một mutation/batch tác động đến hai clustering rows cùng partition:

~~~sql
BEGIN UNLOGGED BATCH
  INSERT INTO telemetry.events_by_device_day
    (tenant_id, device_id, event_day, event_time, event_id, event_type)
  VALUES (
    11111111-1111-4111-8111-111111111111,
    22222222-2222-4222-8222-222222222222,
    '2026-11-25', '2026-11-25T08:00:00Z',
    33333333-3333-4333-8333-333333333333, 'STARTED'
  );
  INSERT INTO telemetry.events_by_device_day
    (tenant_id, device_id, event_day, event_time, event_id, event_type)
  VALUES (
    11111111-1111-4111-8111-111111111111,
    22222222-2222-4222-8222-222222222222,
    '2026-11-25', '2026-11-25T08:01:00Z',
    44444444-4444-4444-8444-444444444444, 'COMPLETED'
  );
APPLY BATCH;
~~~

Nếu write bị phân tán không hoàn toàn giữa replicas và read chỉ truy vấn một clustering row, blocking read repair có thể sửa row đã đọc nhưng chưa sửa row còn lại. Theo tài liệu Cassandra, điều đó tạo đánh đổi giữa monotonic quorum reads và partition-level write atomicity.

`NONE` được dùng khi ứng dụng cần bảo tồn tính chất write atomicity trong bối cảnh này. Nó **không phải công cụ tạo transaction đa partition/đa bảng**; batch Cassandra không tương đương SQL transaction.

## 13. Read repair khác anti-entropy repair ở đâu?

| Tiêu chí | Read repair | Anti-entropy repair |
| --- | --- | --- |
| Trigger | Một query đọc gặp replica khác nhau | Lịch vận hành/auto-repair hoặc thao tác operator |
| Phạm vi | Replica và row/cell trong đường đọc | Token ranges, nhiều partition |
| Cách so sánh | Digest/full data của read | Merkle trees trên dữ liệu được repair |
| Cách sửa | Mutation cho replica tham gia cần sửa | Streaming/hòa giải dữ liệu khác biệt giữa replicas |
| Chi phí | Tăng latency của read khi blocking | CPU, disk I/O, network, compaction trong lúc repair |
| Có phủ cold data? | Không nếu không được đọc | Có khi repair range tương ứng |
| Có thay thế nhau không? | Không | Không |

Một dashboard đọc hot partition mỗi phút có thể giúp repair những phần dữ liệu được chạm tới, nhưng không chạm đến hàng triệu cold partitions khác. Vì vậy **thành công của các read gần đây không đồng nghĩa toàn bộ replica đã nhất quán**.

## 14. Anti-entropy repair: Merkle trees và streaming

Anti-entropy repair là quy trình đối chiếu dữ liệu của các replica cùng sở hữu token ranges:

~~~mermaid
flowchart TD
    A["Lập lịch repair cho node/keyspace/token ranges"] --> B["Replica xây Merkle trees"]
    B --> C{"So sánh hash có khác biệt?"}
    C -->|Không| D["Vùng đó không cần đồng bộ thêm"]
    C -->|Có| E["Xác định các vùng dữ liệu lệch"]
    E --> F["Streaming dữ liệu cần đồng bộ"]
    F --> G["Cập nhật replicas trong phạm vi repair"]
    D --> H["Ghi kết quả/metrics"]
    G --> H
~~~

**Merkle tree** là cấu trúc hash phân cấp giúp nhận diện vùng dữ liệu khác nhau mà không truyền toàn bộ dữ liệu từng row chỉ để so sánh. Cassandra sau đó thực hiện streaming những khác biệt cần thiết.

Repair tốn tài nguyên vì phải đọc dữ liệu/SSTables, tính hash, truyền dữ liệu, ghi dữ liệu và có thể kéo theo compaction. Dù có thể chạy khi cluster hoạt động, nên lên kế hoạch không làm quá tải node hoặc tranh I/O với API online.

**Repair một token range thành công không bảo đảm mọi token range và mọi datacenter đã được kiểm tra.** Cần orchestration và theo dõi phạm vi đã hoàn tất.

## 15. Hinted handoff là best-effort, không thay repair

Khi replica C offline trong lúc ghi:

~~~text
Client -> Coordinator
            |-> A: ghi thành công
            |-> B: ghi thành công
            |-> C: không liên lạc được
~~~

Nếu RF=3, write CL `LOCAL_QUORUM`, A+B có thể đủ xác nhận. Cassandra có cơ chế **hinted handoff**: một node có thể giữ thông tin mutation mà C bỏ lỡ để thử phát lại khi C trở lại.

Nhưng hints có giới hạn thời gian và dung lượng, có thể không được ghi/phát lại đầy đủ và không quét toàn bộ dữ liệu để tìm khác biệt lâu ngày.

Vì vậy:

- Hints giúp giảm khoảng cách nhất quán sau các sự cố ngắn.
- Read repair xử lý những khác biệt phát hiện trên đường đọc.
- Anti-entropy repair đồng bộ dữ liệu trong các token ranges, kể cả partition ít hoặc chưa được đọc.

**Không viết runbook “đã bật hints nên không cần repair”.** Cần đo quá trình phát lại hints và vẫn bảo đảm lịch repair phù hợp.

## 16. Incremental repair và full repair

Apache Cassandra có hai dạng repair quan trọng:

| Loại repair | Tập dữ liệu được so sánh | Ưu điểm | Giới hạn |
| --- | --- | --- | --- |
| **Incremental** | Dữ liệu chưa được đánh dấu repaired từ lần incremental trước | Giảm khối lượng nếu chạy đều đặn | Không tự rà lại toàn bộ dữ liệu đã được đánh dấu repaired |
| **Full** | Toàn bộ dữ liệu thuộc token ranges được chọn | Phát hiện chênh lệch ở cả dữ liệu cũ | CPU/I/O/network và thời gian thường lớn hơn |

Ví dụ lệnh chỉ dành cho môi trường được phép:

~~~bash
# Incremental repair theo mặc định của những phiên bản hiện đại:
nodetool repair telemetry

# Full repair:
nodetool repair --full telemetry
~~~

Một incremental repair có thể hoàn thành nhanh vì xử lý dữ liệu mới hơn, nhưng không phải bằng chứng không có hỏng/mất dữ liệu trong SSTable đã được repaired từ lâu. Vì thế full repair định kỳ vẫn có vai trò tùy workload và chính sách.

**Không chạy lệnh thực tế trên production chỉ từ ví dụ bài học.** Operator phải kiểm tra phiên bản, topology, storage, concurrency và khung giờ thích hợp.

## 17. nodetool repair trên một node không phải repair toàn cluster

Lệnh repair được gọi trên một node sẽ xử lý những token ranges thuộc phạm vi mà node đó nhân bản/sở hữu theo tùy chọn. Nó **không tự sửa toàn bộ token ranges trên mọi datacenter**.

Ví dụ `-pr`/`--partitioner-range`:

~~~bash
# Chỉ primary ranges của node được gọi:
nodetool repair -pr telemetry

# Full repair trên primary ranges của node:
nodetool repair --full -pr telemetry
~~~

Một kế hoạch repair toàn cluster có thể điều phối chạy `-pr` trên từng node/từng DC cần thiết, để tránh lặp công việc và bảo đảm phủ mọi ranges. Cần đối chiếu hướng dẫn chính thức cho phiên bản đang dùng, đặc biệt với các tính năng incremental, transient replication hay auto-repair.

Không nên chỉ kiểm tra “có cron chạy repair mỗi tuần” mà phải biết **node nào, token range nào, keyspace/table nào và đã hoàn thành thành công hay chưa**.

## 18. Preview, validate và metrics trong repair

Tùy phiên bản Cassandra, `nodetool repair` có các tùy chọn:

~~~bash
# Xây/so Merkle trees để ước lượng streaming,
# không thực hiện streaming dữ liệu thật:
nodetool repair --preview telemetry

# Xác thực tính nhất quán của dữ liệu đã repaired
# trong phạm vi tính năng hỗ trợ:
nodetool repair --validate telemetry
~~~

Không coi preview là phép đo chính xác tuyệt đối thời gian chạy hoặc bytes thực sẽ truyền. Validate có phạm vi kiểm tra riêng, không thay full repair khi cần chữa chênh lệch dữ liệu cũ.

Các nhóm metrics quan trọng:

- Repair sessions và token ranges: hoàn thành, chưa chạy, lỗi, retry.
- Merkle tree generation time, streaming bytes và network throughput.
- CPU, disk IOPS, read/write latency và disk space dự phòng.
- Pending compactions và SSTables/partition.
- p50/p95/p99 của traffic online trong khung giờ repair.
- Node unavailable, dropped requests và timeout.
- Thời điểm **repair thành công gần nhất** trên các phạm vi cần thiết.

Nếu repair kéo dài hoặc thất bại, cần có runbook dừng/thử lại theo phạm vi phù hợp, không chỉ tiếp tục mở thêm nhiều phiên repair song song.

## 19. Tombstone và nguy cơ dữ liệu đã xóa xuất hiện lại

Cassandra không xóa ngay dữ liệu trên mọi replica khi có `DELETE`. Nó ghi **tombstone** để các replica chưa thấy lệnh xóa vẫn có thể được hòa giải về sau.

Giả sử:

~~~text
Ban đầu:
  A: firmware=1.2.3
  B: firmware=1.2.3
  C: firmware=1.2.3

C offline, client xóa firmware:
  A: tombstone DELETE ở t2
  B: tombstone DELETE ở t2
  C: giá trị cũ ở t1
~~~

Khi C quay lại đủ sớm, hints/repair có thể chuyển thông tin tombstone đến C. Nhưng nếu A và B đã **purge tombstone** trong khi C còn giữ giá trị cũ, một repair sau đó có nguy cơ mang giá trị cũ quay trở lại: **zombie data / tombstone resurrection**.

Đó là lý do `gc_grace_seconds` và lịch anti-entropy repair phải được đánh giá **cùng nhau**. Không nên giảm thời gian giữ tombstone để giảm dung lượng đĩa rồi bỏ qua các node offline lâu.

## 20. gc_grace_seconds và điều kiện dọn tombstone

Cassandra có table option `gc_grace_seconds`. Tài liệu nêu giá trị mặc định thường là **864.000 giây (10 ngày)**.

~~~sql
CREATE TABLE IF NOT EXISTS telemetry.retention_demo (
    device_id uuid PRIMARY KEY,
    description text
) WITH gc_grace_seconds = 864000;
~~~

Grace period giúp bảo vệ thông tin xóa trong khoảng thời gian replica có thể đang vắng mặt. Khi grace kết thúc, tombstone **có thể** được dọn nếu đáp ứng điều kiện compaction và an toàn; không phải đúng đến giây thứ 864.001 là mọi dấu xóa biến mất.

Ví dụ timeline rủi ro:

~~~text
Ngày 0: C offline
Ngày 1: DELETE được A/B ghi nhận, C giữ dữ liệu cũ
Ngày 2-9: Không repair đầy đủ cho token range
Ngày 11+: Tombstone A/B có thể đủ điều kiện purge
Ngày 12: C trở lại, dữ liệu cũ có nguy cơ xuất hiện lại
~~~

Tài liệu repair khuyến nghị tối thiểu phải repair đủ thường xuyên để **grace period không hết hạn trên dữ liệu chưa được đồng bộ**. Lịch cụ thể cần xét RF, downtime tối đa, kiểu compaction, khả năng vận hành và các ngoại lệ quản trị.

Không áp dụng lời khuyên “đặt `gc_grace_seconds=0` để giảm tombstones” trên production khi chưa có phân tích đầy đủ. Một số workload đặc biệt có thể có chính sách khác, nhưng đó là quyết định vận hành chuyên sâu.

## 21. TTL không đồng nghĩa dữ liệu biến mất ngay khỏi SSTable

Ví dụ event tự hết hạn sau bảy ngày:

~~~sql
INSERT INTO telemetry.events_by_device_day (
    tenant_id, device_id, event_day,
    event_time, event_id, event_type
) VALUES (
    11111111-1111-4111-8111-111111111111,
    22222222-2222-4222-8222-222222222222,
    '2026-11-25',
    '2026-11-25T08:00:00Z',
    33333333-3333-4333-8333-333333333333,
    'TEMPERATURE'
) USING TTL 604800;
~~~

TTL hết hạn khiến dữ liệu được xem là không còn sống; Cassandra phải xử lý expired data/tombstones trong lưu trữ và compaction. Không nên kỳ vọng sau đúng 7 ngày mọi byte đã bị xóa vật lý.

Cần tách rõ:

| Khái niệm | Mục đích |
| --- | --- |
| **TTL** | Xác định thời gian sống của dữ liệu được ghi |
| **Tombstone** | Đánh dấu dữ liệu đã bị xóa/hết hạn theo semantics Cassandra |
| **gc_grace_seconds** | Giữ khả năng đồng bộ xóa qua một khoảng grace |
| **Compaction** | Hợp nhất SSTables và có thể dọn dữ liệu hết hạn đủ điều kiện |
| **Repair** | Đồng bộ replica theo phạm vi token ranges |

Với dữ liệu time-series và TTL thường xuyên, có thể đánh giá `TimeWindowCompactionStrategy` theo workload, nhưng nó không thay cho repair hay policy bảo vệ tombstones.

## 22. Vì sao read repair và repair job làm tăng latency?

Cả hai loại repair đều sử dụng tài nguyên:

| Công việc | Chi phí chính | Biểu hiện |
| --- | --- | --- |
| Full-data read | SSTable reads, network payload | Tăng latency khi replica chậm |
| Digest read | Hash/CPU và network | Thêm tải nhẹ để so sánh phiên bản |
| Digest mismatch | Fetch thêm full data, reconciliation | Đôi lúc request chậm bất thường |
| Blocking read repair | Repair mutation + chờ acks | p99 tăng khi replica không ổn định |
| Merkle tree build | Đọc dữ liệu, hash/CPU | Tranh tài nguyên với online reads |
| Streaming dữ liệu repair | Network, disk I/O | Tăng load và compaction backlog |
| Nhiều repair sessions cùng lúc | CPU, disk, network, threads | Timeout/retry và thời gian hoàn thành kéo dài |

Khi p99 tăng, đừng kết luận ngay “do repair”: một truy vấn thiếu partition key, tombstone scan lớn, network mất gói hoặc hot partition cũng có thể gây hiện tượng tương tự. Cần đối chiếu query ID, read CL, read repair events/tracing, streaming metrics và thời điểm compaction.

Không tắt anti-entropy repair vô thời hạn chỉ để giảm tải. Hãy điều phối lịch, concurrency, phạm vi và ngân sách I/O theo runbook có quan sát.

## 23. Cấu hình consistency trong Spring Data Cassandra

Với repository:

~~~java
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface DeviceStateRepository
        extends CassandraRepository<DeviceState, DeviceStateKey> {
}
~~~

`DeviceState` và `DeviceStateKey` phải được định nghĩa theo `@Table`, `@PrimaryKeyClass` và `@PrimaryKeyColumn` khớp schema của mục 3.

Để chỉ định consistency cho một query method:

~~~java
import java.util.UUID;

import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import org.springframework.data.cassandra.repository.Consistency;
import org.springframework.data.cassandra.repository.Query;

public interface DeviceStateRepository
        extends CassandraRepository<DeviceState, DeviceStateKey> {

    @Consistency(DefaultConsistencyLevel.LOCAL_QUORUM)
    @Query("SELECT * FROM device_state_by_id "
         + "WHERE tenant_id = ?0 AND device_id = ?1")
    DeviceState findAtLocalQuorum(UUID tenantId, UUID deviceId);
}
~~~

Annotation này áp dụng cho **method cụ thể**. Không suy từ nó rằng `save` hoặc `findById` kế thừa cũng tự động dùng `LOCAL_QUORUM`. Nếu cần consistency đồng nhất cho read/write, phải kiểm tra cấu hình driver, repository, template và policy của từng loại thao tác.

Tương tự, thay `@Query` bằng `CassandraTemplate` không làm server tự repair thêm; chỉ thay cách client xây/gửi statement.

## 24. Java driver: consistency theo statement

Nếu ứng dụng cần điều khiển CL của một statement:

~~~java
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class DeviceBatteryLookup {
    private final CqlSession session;
    private final PreparedStatement select;

    public DeviceBatteryLookup(CqlSession session) {
        this.session = session;
        this.select = session.prepare(
            "SELECT battery_percent "
          + "FROM telemetry.device_state_by_id "
          + "WHERE tenant_id = ? AND device_id = ?");
    }

    public Integer find(UUID tenantId, UUID deviceId) {
        Row row = session.execute(
            select.bind(tenantId, deviceId)
                  .setConsistencyLevel(
                      DefaultConsistencyLevel.LOCAL_QUORUM))
            .one();

        if (row == null || row.isNull("battery_percent")) {
            return null;
        }
        return row.getInt("battery_percent");
    }
}
~~~

`setConsistencyLevel` chọn yêu cầu số replica cho lần đọc. Nó không thay đổi replication factor, bảng, hoặc lịch repair.

Đoạn ví dụ trả null cho cả row không tồn tại và cột battery null. Trong API production, nếu hai trạng thái đó khác về nghiệp vụ, cần kiểu trả về rõ ràng như `Optional<DeviceState>`/DTO thay vì gộp vô tình.

## 25. Phân biệt kết quả rỗng, stale value và lỗi hạ tầng

Một read Cassandra có thể:

1. Trả giá trị đúng mới nhất trong phạm vi consistency đã cấu hình.
2. Trả giá trị cũ vì replica chưa hội tụ ở CL yếu hơn.
3. Trả empty vì row thật sự chưa tồn tại, đã bị xóa hoặc TTL hết hạn.
4. Ném lỗi timeout/unavailable/network/schema.

**Không bắt mọi exception rồi trả `Optional.empty()`:**

~~~java
// Anti-pattern: che lỗi Cassandra thành dữ liệu không tồn tại.
try {
    return repository.findById(key);
} catch (RuntimeException ignored) {
    return java.util.Optional.empty();
}
~~~

Nếu một read ở LOCAL_QUORUM không đủ phản hồi, đó là vấn đề availability/timeout, không phải bằng chứng row không tồn tại. Tầng API phải phân loại lỗi, log theo correlation ID, quan sát metrics và retry có kiểm soát.

CL không sửa được access pattern sai: một `SELECT ... WHERE event_type = ? ALLOW FILTERING` trên bảng theo device/day vẫn có thể quét rất rộng dù chọn LOCAL_QUORUM.

## 26. Kiểm thử read repair khác kiểm thử repository thông thường

### Kiểm thử mapping và CQL

Một Cassandra Testcontainers một node thường đủ để xác minh:

- Entity/primary key mapping và câu `@Query`.
- Read/write theo partition key, UTC/day bucket, timestamp precision.
- `Optional.empty()` khi row chưa có.
- Hành vi TTL cơ bản, phân trang và projection.
- Cấu trúc schema do migration tạo.

Nhưng **một node RF=1 không chứng minh read repair giữa ba replica**.

### Kiểm thử hội tụ trên cluster test nhiều replica

Một integration/chaos test có kiểm soát nên:

1. Tạo cluster RF=3 trong một datacenter thử nghiệm.
2. Ghi giá trị ban đầu và xác minh replica khỏe.
3. Mô phỏng một replica không liên lạc được bằng công cụ test phù hợp.
4. Gửi một write với CL đã định, ghi nhận thành công/timeout và timestamp.
5. Đọc với LOCAL_ONE và LOCAL_QUORUM, theo dõi giá trị, latency và tracing.
6. Kiểm tra read repair khi có mismatch, đối chiếu `BLOCKING` và `NONE`.
7. Chạy anti-entropy repair ở cluster test và xác minh dữ liệu hội tụ.
8. Thử tình huống DELETE/TTL, node offline và grace period bằng cách an toàn.

Không cố ép một test luôn thấy dữ liệu stale từ một node cụ thể: coordinator selection và trạng thái timing có thể làm kết quả khác nhau. Test nên quan sát **tính chất được bảo đảm** và metrics, không dựa vào lịch request cố định thiếu kiểm soát.

**Không chạy các thao tác node down/network partition/repair cưỡng bức trên production** để chứng minh một bài học.

## 27. Checklist vận hành repair theo token ranges

Một quy trình bền vững nên có:

1. Ghi lại version, node/DC, RF, keyspace/table và token ranges cần repair.
2. Kiểm tra downtime cho phép, retention, TTL, tombstones và `gc_grace_seconds`.
3. Quyết định incremental repair thường xuyên và full repair định kỳ theo chính sách/version.
4. Lập lịch bao phủ toàn bộ node/datacenter phù hợp; cân nhắc `-pr`.
5. Có giới hạn CPU/I/O/network/concurrency và disk headroom.
6. Giám sát Merkle tree build, streaming bytes, pending tasks và compaction.
7. Xác minh **repair hoàn thành thành công**, không chỉ job đã bắt đầu.
8. Xử lý riêng node trở lại sau downtime dài bằng runbook repair/rebuild.
9. Đối soát các bảng có xóa/TTL nhiều hoặc dữ liệu nghiệp vụ quan trọng.
10. Đánh giá tác động đến p95/p99 của API và điều chỉnh lịch nếu cần.

Một số phiên bản mới có cơ chế auto-repair hoặc công cụ orchestration. Cần xem rõ đã bật hay chưa và phạm vi có phủ đủ token ranges không; không chạy chồng các repair thủ công gây tăng tải khi công cụ hiện tại đã làm việc đó.

## 28. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Hiểu lầm | Hướng xử lý |
| --- | --- | --- |
| Hai read LOCAL_ONE ra hai giá trị | “Spring Data cache sai” | Kiểm tra RF, CL, replica state, timestamp |
| Read LOCAL_QUORUM trả bản mới | “Tất cả replica đã cập nhật” | Có thể còn replica chưa tham gia read |
| `read_repair='NONE'` trả bản mới | “Replica được repair rồi” | NONE chỉ reconcile read, không gửi mutation sửa |
| BLOCKING làm p99 tăng | “Tắt repair là giải pháp” | Đo mismatch/replica latency và đánh đổi consistency |
| Có hinted handoff | “Không cần anti-entropy repair” | Hints best-effort, vẫn cần lịch repair |
| Chạy repair trên một node | “Đã repair toàn cluster” | Kiểm tra phạm vi ranges/node/DC |
| Incremental repair chạy đều | “Full repair không bao giờ cần” | Full có giá trị phát hiện lệch dữ liệu cũ |
| Giảm `gc_grace_seconds` | “Tombstone không còn quan trọng” | Rủi ro zombie data khi replica lỡ DELETE |
| TTL đến hạn | “Đĩa được giải phóng ngay” | Còn tombstone/compaction |
| SELECT thiếu partition key chậm | “Tăng consistency sẽ nhanh hơn” | Thiết kế bảng theo truy vấn |
| Catch timeout và trả empty | “Không có dữ liệu” | Phản ánh đúng lỗi hạ tầng |
| RF=1 test xanh | “Read repair RF=3 đã được kiểm thử” | Cần môi trường đa replica cô lập |

## 29. Bài tập thực hành

### Bài A — Tính quorum

Datacenter có RF=3. Write thành công ở LOCAL_QUORUM, read sau đó ở LOCAL_QUORUM. Tính W, R, kiểm tra `W+R>RF`; nêu các điều kiện cần để diễn giải độ mới.

**Gợi ý:** 2+2>3 nên hai tập replica giao nhau; không suy thành transaction ACID đa partition.

### Bài B — Digest mismatch

Replica A giữ `battery=68` tại t2, B giữ `battery=72` tại t1, t2>t1. Vẽ full read/digest read, bước lấy thêm dữ liệu và repair ở BLOCKING.

### Bài C — Monotonic quorum reads

Một write v2 chỉ đến A rồi timeout. Read quorum #1 A+B thấy v2; Read quorum #2 B+C có thể thấy gì trong hai chế độ BLOCKING/NONE? Giải thích vai trò repair tới quorum.

### Bài D — Partition-level write atomicity

Một batch cập nhật hai clustering rows trong cùng partition. Vì sao read repair chỉ nhắm một row có thể tạo đánh đổi với write atomicity? Trong trường hợp nào cân nhắc read_repair NONE?

### Bài E — Hints không thay repair

Replica C offline 12 giờ. Hints được bật. Hãy giải thích tại sao vẫn cần kiểm tra repair thành công, đồng thời liệt kê metrics cần thu trước khi cho C phục vụ đọc bình thường.

### Bài F — Tombstone resurrection

Một node offline 12 ngày và bỏ lỡ DELETE, còn `gc_grace_seconds=864000`. Vẽ timeline và giải thích tại sao dữ liệu đã xóa có thể xuất hiện lại sau compaction và repair.

### Bài G — Incremental/full

So sánh incremental và full repair, một ví dụ mất SSTable đã repaired và vì sao lịch full repair định kỳ vẫn có ý nghĩa.

### Bài H — Spring Data CL

Viết một repository method `@Consistency(DefaultConsistencyLevel.LOCAL_QUORUM)` và một prepared statement `setConsistencyLevel` tương đương. Vì sao không được suy rằng `save` kế thừa cũng dùng LOCAL_QUORUM?

### Bài I — Repair và hiệu năng

Trong khung giờ repair, read p99 tăng từ 40ms lên 250ms. Nêu ít nhất 8 metrics cần đối chiếu để xác định mismatch/read repair, streaming, compaction, hot partition hay query filtering.

### Bài J — Test RF=3

Thiết kế một test nhiều replica: tạo sai khác có kiểm soát, so LOCAL_ONE/LOCAL_QUORUM, BLOCKING/NONE, rồi chạy anti-entropy repair. Nêu vì sao Cassandra một node RF=1 không thể kiểm chứng cơ chế này.

**Tiêu chí đạt:** người học giải thích được full/digest read, reconciliation, read repair và phạm vi sửa, phân biệt anti-entropy/hints, hiểu BLOCKING/NONE, đặt CL phù hợp và nêu được lịch repair bảo vệ tombstones/TTL.

## 30. Checklist trước khi chốt chính sách consistency và repair

- [ ] RF và replication strategy đúng với topology các datacenter?
- [ ] Các đường đọc/ghi qua Spring Data/driver có CL được chốt và ghi nhận?
- [ ] Hiểu LOCAL_ONE không bắt buộc so digests giữa nhiều replica?
- [ ] Phân biệt digest mismatch, hòa giải cell và sửa replica theo read repair?
- [ ] Bảng Cassandra 4.0+ dùng BLOCKING hay NONE theo invariant nghiệp vụ?
- [ ] Có hiểu monotonic quorum reads và đánh đổi partition-level write atomicity?
- [ ] Anti-entropy repair được lập lịch phủ đầy đủ node/DC/token ranges?
- [ ] Incremental và full repair có kế hoạch phù hợp server version?
- [ ] Hints chỉ được xem là best-effort, không thay repair?
- [ ] `gc_grace_seconds`, TTL và repair interval đã được đánh giá cùng nhau?
- [ ] Có xác nhận repair thành công thay vì chỉ có lịch chạy?
- [ ] Có metrics p95/p99, mismatches, streaming, compaction, timeout?
- [ ] Lỗi unavailable/timeout không bị chuyển thành kết quả rỗng?
- [ ] Có test multi-replica cô lập thay vì chỉ dựa vào RF=1?
- [ ] Mọi `nodetool repair` và thay đổi table options được operator xem xét?

## Tài liệu tham khảo

- [Apache Cassandra — Read Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/read_repair.html): full/digest reads, mismatch, BLOCKING/NONE, monotonic quorum reads và write atomicity.
- [Apache Cassandra 4.1 — Read Repair](https://cassandra.apache.org/doc/4.1/cassandra/operating/read_repair.html): phạm vi hành vi được mô tả cho nhánh 4.1.
- [Apache Cassandra — Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html): incremental/full repair, Merkle trees và nodetool.
- [Apache Cassandra — Tombstones](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/tombstones.html): gc_grace_seconds, compaction và zombie data.
- [Apache Cassandra — Dynamo Architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html): hinted handoff, read repair và anti-entropy.
- [Apache Cassandra — Data Definition](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html): table options, replication và read_repair.
- [Spring Data Cassandra — Repository Query Methods](https://docs.spring.io/spring-data/cassandra/reference/cassandra/repositories/query-methods.html): @Query, consistency và repository.
- [Spring Data Cassandra — CassandraTemplate](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html): mapping/query operations.
- [Java Driver 4 — Statements](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/statements/): prepared/bound statements và consistency level.
