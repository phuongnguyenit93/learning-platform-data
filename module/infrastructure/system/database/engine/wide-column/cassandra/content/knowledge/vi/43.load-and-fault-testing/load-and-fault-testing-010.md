# Thử replica vắng mặt rồi hội tụ bằng hint/repair

## 1. Tình huống: ghi thành công khi một replica tắt, nhưng dữ liệu đã đồng bộ chưa?

Hệ thống Java lưu sự kiện thiết bị trong **Apache Cassandra**. Keyspace có `NetworkTopologyStrategy`, **replication factor (RF) = 3** trong datacenter `dc1`; ứng dụng ghi ở **`LOCAL_QUORUM`**. Một node replica đang bảo trì nên tạm thời không nhận mutation. Client tiếp tục ghi hàng trăm sự kiện, nhận phản hồi thành công, và dashboard API vẫn bình thường. Vài phút sau node trở lại trạng thái `UN` trong `nodetool status`.

Nhóm vận hành có thể vội kết luận: **“Cassandra đã tự đồng bộ xong; không cần làm gì nữa.”** Đây là kết luận không được chứng minh. Với RF=3, `LOCAL_QUORUM` chỉ cần **hai full replicas** phản hồi; replica thứ ba có thể chưa có một số mutation. **Hinted handoff** có thể chuyển các mutation bị bỏ lỡ sau khi node hồi phục, nhưng chỉ là cơ chế **best-effort**. **Anti-entropy repair** so sánh dữ liệu thuộc cùng token ranges và chuyển các khác biệt; nó là cơ chế cần có để bảo đảm quá trình hội tụ lâu dài, đặc biệt khi hint thiếu hoặc cửa sổ hint đã hết.

~~~mermaid
sequenceDiagram
    participant Java as Java Driver / Client
    participant C as Coordinator
    participant R1 as Replica R1
    participant R2 as Replica R2
    participant R3 as Replica R3 (down)
    Java->>C: INSERT / UPDATE tại LOCAL_QUORUM
    C->>R1: Mutation
    C->>R2: Mutation
    C--xR3: Không thể giao mutation
    R1-->>C: ACK
    R2-->>C: ACK
    C-->>Java: Thành công với quorum 2/3
    Note over C: Nếu điều kiện cho phép, lưu hint cho R3
    Note over R3: Node hồi phục
    C->>R3: Phát lại hint còn hợp lệ
    Note over R1,R3: Repair vẫn cần theo lịch và khi có sai lệch
~~~

Bài thuộc chương **Đo tải và lỗi phân tán**, trong mô-đun **`DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`**: kiến trúc phân tán, token, partition key, wide-column, nhất quán đọc ghi, compaction/repair và kết nối từ Java.

**Mục tiêu học tập:**

1. Giải thích **coordinator**, **natural replica**, RF và `LOCAL_ONE`/`LOCAL_QUORUM`/`ALL` khi một replica vắng mặt.
2. Phân biệt **commit log**, **hinted handoff**, **read repair** và **full/incremental anti-entropy repair**.
3. Dựng hoặc mô phỏng **ba node Cassandra** an toàn trong cluster test riêng; chèn một fault có điểm bắt đầu/kết thúc và rollback rõ ràng.
4. Tạo fixture CQL có partition key xác định, **operation ID** ổn định và ledger đối chiếu số lượng/giá trị/TTL/delete.
5. Đo throughput, p95/p99, timeout và hint backlog **trước–trong–sau** fault, không xem client ACK là bằng chứng mọi replica cập nhật.
6. Tách hai thử nghiệm: **hồi phục nhanh với hint** và **vắng mặt vượt hint window/không còn hint phải dùng repair**.
7. Đọc tín hiệu vận hành để biết **handoff hoàn tất, repair hoàn tất và dữ liệu có chứng cứ hội tụ**; nêu giới hạn của mỗi tín hiệu.
8. Xử lý `gc_grace_seconds`, tombstone, nhiều DC, lỗi chồng lấp và các nguyên tắc fault injection trong production-like staging.

**Phạm vi và giới hạn:** ví dụ CQL/Java tập trung vào Cassandra 4.x/5.x với **full replicas**, Java Driver 4.x. Tên `cassandra.yaml` và `nodetool` có thể thay theo version: Cassandra 3.x thường dùng các key kết thúc bằng `_in_ms`, trong khi những bản mới có key thân thiện với đơn vị như `max_hint_window`. **Không copy config khi chưa đối chiếu tài liệu cùng version.** Đây là bài học/thiết kế thí nghiệm; không thực thi dừng node, làm nghẽn mạng, chạy stress hoặc repair trên production.

## 2. Mô hình replica: token placement, coordinator và điều kiện ghi thành công

### 2.1. Natural replicas được chọn theo partition key

Với bảng `events_by_device_day`:

~~~sql
PRIMARY KEY ((device_id, event_day), event_time, event_id)
~~~

- `(device_id,event_day)` là **composite partition key**. Cassandra hash cả hai thành token; natural replica placement phụ thuộc keyspace strategy, topology/racks và token ring.
- `event_time,event_id` là **clustering keys** quyết định thứ tự bên trong partition, **không** tự tạo partition mới.
- `NetworkTopologyStrategy` quy định RF **riêng từng DC**, không phải một số replica toàn hệ thống không phân biệt vị trí.
- **Coordinator** là node nhận CQL request, có thể **không** phải natural replica của key. Driver chọn coordinator theo load balancing/token awareness và node health; coordinator định tuyến tới các replica phù hợp.

~~~mermaid
flowchart TD
    A["Java: partition key (device-7, 2026-11-21)"] --> B["Token theo partitioner"]
    B --> C["NetworkTopologyStrategy + topology"]
    C --> R1["Full replica R1"]
    C --> R2["Full replica R2"]
    C --> R3["Full replica R3"]
    D["Coordinator nhận request"] --> R1
    D --> R2
    D -.-> R3
    R1 --> E["CL quyết định số ACK đủ để trả client"]
    R2 --> E
    R3 -.-> E
~~~

### 2.2. Một DC với RF=3

| CL | Full replica responses cần cho một operation (RF=3) | Khi đúng một replica không sẵn sàng |
| --- | ---: | --- |
| `LOCAL_ONE` | 1 trong local DC | Có thể thành công nếu còn một replica phù hợp. |
| `LOCAL_QUORUM` | `floor(3/2)+1=2` trong local DC | **Có thể thành công** với hai replica còn khỏe. |
| `ALL` | Cả ba full replicas (với chỉ một DC của ví dụ) | Thường **không thể** hoàn tất khi một replica down. |
| `ANY` (write đặc biệt) | Có thể ghi nhận hint trong những tình huống hạn chế | **Không** là bằng chứng dữ liệu đã nằm trên replica hoặc đọc lại được; không dùng để “đảm bảo hội tụ” trong lab này. |

Không đánh đồng **quorum ACK** với “ba bản sao đã giống hệt”. `LOCAL_QUORUM` có lợi thế read/write quorum intersection với điều kiện topology và operation thích hợp, nhưng một `SELECT LOCAL_QUORUM` thành công **không chứng minh replica thứ ba có đủ mọi mutation**, không thay repair.

### 2.3. Hai DC không có “quorum tổng” khi dùng `LOCAL_QUORUM`

Nếu `dc1:3`, `dc2:3`, request `LOCAL_QUORUM` từ `dc1` cần quorum **ở `dc1`**, không phải hai phản hồi chia bất kỳ giữa hai DC. Replica ở `dc2` có thể chậm hoặc không nhận một số writes; cần hiểu cross-DC replication, hint configuration và repair scope. Một bài test một DC **không** được dùng để kết luận bảo đảm active-active đa DC.

## 3. Bốn cơ chế dễ bị nhầm thành “Cassandra tự sửa”

| Cơ chế | Xảy ra khi nào? | Đích/điều được bảo vệ | Giới hạn quan trọng |
| --- | --- | --- | --- |
| **Commit log** | Khi một node nhận mutation hợp lệ và theo write path/durability settings của nó. | Độ bền cục bộ của node đó, cùng memtable/SSTable. | Không giao mutation đã thiếu sang một replica khác. |
| **Hinted handoff** | Coordinator không thể giao write cho một replica, khi hinting hợp lệ và trong window. | **Hint lưu tạm ở node khác**, được phát lại cho replica đích khi trở lại. | Best-effort; hint có thể thiếu/mất/không được tạo; không thay anti-entropy repair. |
| **Read repair** | Một số đường đọc phát hiện khác biệt giữa replica đã được hỏi, tùy CL/version/config. | Sửa khác biệt trong phạm vi dữ liệu được đọc theo behavior thực. | Không quét toàn bộ token ranges hay đảm bảo mọi partition ít truy cập được đồng bộ. |
| **Anti-entropy repair** | Vận hành lên lịch hoặc kích hoạt repair cho token ranges/tables/DCs. | So sánh replica datasets, dùng Merkle trees và streaming differences. | Tốn tài nguyên; cần coverage, topology khỏe, lịch và quy trình; không khôi phục dữ liệu nếu mọi bản sao đều mất. |

**Chốt phân biệt:** **Hint làm giảm thời gian lệch; repair giảm nguy cơ lệch kéo dài** và là một phần bắt buộc của chiến lược eventual consistency/anti-entropy. Không nói “repair chỉ dùng khi hint thất bại”: repair còn cần cho deletes, writes bị missed do nhiều tình huống và các partition không được đọc.

## 4. Timeline của một replica vắng mặt

| Mốc | R1/R2/R3 | Client và coordinator | Dữ liệu/repair |
| --- | --- | --- | --- |
| T0 baseline | Cả ba `UN`. | Ghi/đọc theo `LOCAL_QUORUM`. | Fixture đã được xác minh; chưa chèn fault. |
| T1 inject fault | R3 tạm dừng và bị xem là down. | Driver chọn coordinator khỏe trong local DC. | R3 không nhận mutation mới trong khoảng vắng mặt. |
| T2 load trong outage | R1, R2 còn hoạt động. | `LOCAL_QUORUM` có thể ACK 2/3. | Một/số coordinators có thể lưu hint cho R3. |
| T3 recovery | R3 khởi động, gossip lại `UN`. | Traffic tiếp tục; có thể tăng load khi handoff. | R3 **có thể vẫn thiếu** mutation dù `UN`. |
| T4 handoff | Hint ở coordinator được phát lại theo budget/throttle. | Latency có thể tăng khi hệ vừa replay vừa phục vụ online. | Sai lệch được thu hẹp; cần quan sát hints pending/failures. |
| T5 anti-entropy | Các node đủ khỏe cho repair. | Có thể throttle backfill để tránh vượt SLO. | Repair so/token range và stream differences khi cần. |
| T6 verify | Cluster ổn định. | So ledger/correctness, latency, error, topology. | Chỉ kết luận hội tụ với bằng chứng và phạm vi đã test. |

Không dùng `sleep 30` rồi khẳng định handoff xong. **Node `UN` chỉ là một tín hiệu membership/availability**. Nó không chứng minh mọi hint đã được dispatch/ACK, mọi range đã repair hay tombstone được xử lý an toàn.

## 5. Rào chắn an toàn trước khi làm fault injection

**Bắt buộc dùng cluster test cô lập hoặc staging được phê duyệt**. Việc dừng replica trên production có thể giảm fault tolerance thực, gây timeout/đánh mất dữ liệu khi có lỗi thứ hai, làm tăng hint disk usage, hoặc tác động repair, streaming và khách hàng.

### 5.1. Điều kiện tiền đề

~~~text
[ ] Có quyền và môi trường test riêng, xác minh cluster ID/DC và không có data thật.
[ ] Cassandra version + JDK + Java Driver + cấu hình hints/repair đã pin.
[ ] RF=3 full replicas trong dc1 với ba Cassandra nodes thật, không phải RF3 trên một node.
[ ] Token/rack/DC metadata đúng; nắm node ID của R3 và coordinator candidates.
[ ] Disk headroom, RAM, network, logs/metrics đầy đủ, đồng hồ đồng bộ.
[ ] Backup/snapshot nếu dùng persistent test volumes có dữ liệu cần giữ.
[ ] Chốt query shape, row size, traffic rate, CL và expected operation IDs.
[ ] Chốt stop criteria: lỗi, disk, p99, pending hints, JVM OOM, replica lag.
[ ] Có người chịu trách nhiệm phục hồi node, kiểm handoff và repair.
[ ] Chỉ một fault được inject ở một thời điểm trong bài test cơ sở.
~~~

### 5.2. Không dùng các thao tác phá hủy làm “shortcut”

- **Không** dùng `nodetool truncatehints` để “làm trống backlog” trong production; nó làm mất hint chưa phát.
- **Không** xóa `hints_directory`, commit log hoặc SSTable để ép tình huống phục hồi: đó là **fault khác**, có rủi ro mất dữ liệu.
- **Không** chỉnh `gc_grace_seconds=0` và ép compaction để test zombie trong cluster có dữ liệu thật.
- **Không** `docker compose down -v` nếu còn cần volume/dữ liệu để chứng minh hội tụ; `-v` xóa volumes và thay đổi bản chất bài test.
- **Không** chạy full repair mọi node đồng thời ngay khi node mới online: có thể gây contention I/O/network/GC và làm SLO xấu hơn.
- **Không** nhầm stop một **coordinator** với stop natural replica của key: hai lỗi có thể ảnh hưởng đường write khác nhau.

## 6. Môi trường lab ba node: mô hình Docker Compose

Để tái lập, có thể chạy ba Cassandra containers trên **một host test có đủ RAM/disk**. Đây là bài lab khả dụng chức năng, **không mô phỏng ba failure domains vật lý**: nếu host/Docker daemon chết, cả ba node mất.

### 6.1. Compose tham khảo

~~~yaml
# docker-compose.yml minh họa: dùng trong thư mục lab RIÊNG.
# Pin image digest/patch đã duyệt trong CI thực.
services:
  cassandra1:
    image: cassandra:4.1
    hostname: cassandra1
    environment:
      CASSANDRA_CLUSTER_NAME: fault-lab
      CASSANDRA_DC: dc1
      CASSANDRA_RACK: rack1
      CASSANDRA_ENDPOINT_SNITCH: GossipingPropertyFileSnitch
      CASSANDRA_SEEDS: cassandra1
      CASSANDRA_NUM_TOKENS: "16"
      MAX_HEAP_SIZE: 768M
      HEAP_NEWSIZE: 128M
    volumes:
      - cassandra1-data:/var/lib/cassandra

  cassandra2:
    image: cassandra:4.1
    hostname: cassandra2
    environment:
      CASSANDRA_CLUSTER_NAME: fault-lab
      CASSANDRA_DC: dc1
      CASSANDRA_RACK: rack2
      CASSANDRA_ENDPOINT_SNITCH: GossipingPropertyFileSnitch
      CASSANDRA_SEEDS: cassandra1
      CASSANDRA_NUM_TOKENS: "16"
      MAX_HEAP_SIZE: 768M
      HEAP_NEWSIZE: 128M
    depends_on:
      - cassandra1
    volumes:
      - cassandra2-data:/var/lib/cassandra

  cassandra3:
    image: cassandra:4.1
    hostname: cassandra3
    environment:
      CASSANDRA_CLUSTER_NAME: fault-lab
      CASSANDRA_DC: dc1
      CASSANDRA_RACK: rack3
      CASSANDRA_ENDPOINT_SNITCH: GossipingPropertyFileSnitch
      CASSANDRA_SEEDS: cassandra1
      CASSANDRA_NUM_TOKENS: "16"
      MAX_HEAP_SIZE: 768M
      HEAP_NEWSIZE: 128M
    depends_on:
      - cassandra1
    volumes:
      - cassandra3-data:/var/lib/cassandra

volumes:
  cassandra1-data:
  cassandra2-data:
  cassandra3-data:
~~~

`depends_on` chỉ điều phối start order, **không** đảm bảo Cassandra đã join ring. Dùng health/wait loop có deadline, `nodetool status` từ node khỏe và xác minh có **ba node `UN` thuộc `dc1`** trước khi tạo keyspace. Nếu Docker host không đủ RAM, dùng VM/cluster test chuyên dụng; **không dùng một node với RF=3** để thay ba replicas.

### 6.2. Lệnh trên môi trường lab được phê duyệt

~~~bash
docker compose up -d
docker compose exec -T cassandra1 nodetool status
docker compose exec -T cassandra1 nodetool info
docker compose exec -T cassandra2 nodetool status
docker compose exec -T cassandra3 nodetool status
~~~

Các lệnh chạy trong container để tránh lỗi driver topology: Java process chạy **trên host** chỉ có một port forward có thể nhận topology IP nội bộ Docker không định tuyến được. Đối với Java test, chạy test runner trong **cùng Docker network** hoặc dùng mạng/port mappings tương thích với địa chỉ Cassandra node quảng bá. Không “sửa” bằng cách hạ TLS/auth khi chuyển từ Docker lab sang staging.

## 7. CQL fixture để thấy mutation bị missed

### 7.1. Keyspace `NetworkTopologyStrategy` với RF=3

~~~sql
CREATE KEYSPACE IF NOT EXISTS fault_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS fault_lab.events_by_device_day (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  event_type text,
  payload text,
  deleted boolean,
  PRIMARY KEY ((device_id,event_day),event_time,event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

Tất cả ba node trong lab này là natural replicas cho mỗi partition vì RF=3/3 nodes trong một DC. Nếu là cluster có nhiều hơn ba node, phải xác định **natural replica set** cho partition được test; dừng một node bất kỳ có thể không ảnh hưởng key ấy. `event_id` ổn định là **khóa phân biệt sự kiện** khi producer retry, không tự sinh ID mới cho cùng operation sau timeout.

### 7.2. Seed baseline đã được xác nhận

~~~sql
-- Lệnh cqlsh, không gửi nguyên dòng CONSISTENCY vào Java Driver.
CONSISTENCY LOCAL_QUORUM;

INSERT INTO fault_lab.events_by_device_day
  (device_id,event_day,event_time,event_id,event_type,payload,deleted)
VALUES
  ('device-7','2026-11-21','2026-11-21T08:00:00Z',
   123e4567-e89b-42d3-a456-426614174001,'BASELINE','before-fault',false);

SELECT event_time,event_id,event_type,payload
FROM fault_lab.events_by_device_day
WHERE device_id='device-7' AND event_day='2026-11-21'
LIMIT 100;
~~~

**Dữ liệu thực nghiệm có nguồn chân lý riêng:** ngoài dữ liệu trên, Java writer tạo **ledger expected mutations** với `operationId/eventId`, primary key, value, phase (`BEFORE/DURING/AFTER`), thời điểm gửi/ACK, exception và CL. Nếu chỉ kiểm một `COUNT(*)`, bạn có thể không phát hiện **thiếu 1 ID nhưng trùng/ghi đè 1 ID khác**.

### 7.3. Phạm vi của bảng

- Dùng một partition ngày với số hàng vừa phải để kiểm tra đầy đủ identity/values.
- Dùng thêm nhiều `device_id` nếu cần đo nhiều token/replica sets ở cluster hơn ba node.
- Không dùng `ALLOW FILTERING` hoặc truy vấn `SELECT *` mọi partition để kiểm chứng. Quét rộng trên Cassandra có thể làm chính phép test gây overload.
- Khi thử TTL/delete, dùng **fixture riêng**; không lẫn với baseline “toàn bộ event là immutable và phải tồn tại”.

## 8. Ba phép đo: correctness, availability và recovery

| Trục | Câu hỏi cần trả lời | Tín hiệu tối thiểu |
| --- | --- | --- |
| **Availability** | Trong lúc R3 down, bao nhiêu writes/reads ở CL đã chọn thành công? | Sent/ACK/fail/timeout theo request, CL, p50/p95/p99, in-flight. |
| **Correctness** | Những operation đã ACK có được đọc lại đầy đủ, đúng payload/version không? | So **set event IDs/values** với ledger tại scope partition/time; tách timeout unknown. |
| **Recovery/convergence** | R3 đã bắt kịp những mutations missed và các replica đã đối soát chưa? | Membership + hint service metrics + repair completed/validated + bằng chứng read/replica scope. |

**Một metric đứng riêng không đủ**. `nodetool status` `UN` chỉ chứng minh membership; `LOCAL_QUORUM` read đúng có thể sử dụng hai replicas khỏe; hints queue rỗng không chứng minh mọi hint từng được tạo; repair report thành công chỉ chứng minh **phạm vi token/table/DC mà job xử lý**.

## 9. Phase A — Baseline không fault: đủ replicas và đường đo ổn định

Trước khi dừng node, chạy **cùng workload** sẽ dùng trong outage:

~~~text
Topology:
  dc1: R1=UN, R2=UN, R3=UN
  keyspace RF=3
  write/read CL=LOCAL_QUORUM
  workload  = CQL insert events (bound PK), fixed row payload, stable UUIDs

Baseline duration:
  warmup  : có giới hạn (ví dụ 2 phút)
  steady  : có giới hạn (ví dụ 5 phút)
  cooldown: thu hết outstanding requests

Capture:
  request rate / achieved throughput / in-flight
  p50, p95, p99 write + read latencies
  success, unavailable, timeout, client overload
  CPU/JVM GC, disk I/O, network RTT, pending queues
  hint backlog = bình thường gần như không đáng kể trong cluster khỏe
  ledger of expected ACKed event IDs/values
~~~

**Thời gian là con số minh họa**, không phải phép đo chuẩn. Nếu baseline không đạt SLO, không nên cố tình dừng replica rồi mới debug; phải giải quyết query model, resource saturation, driver routing, RF/CL hoặc schema trước.

### 9.1. Nhiệt độ tải phải có giới hạn

Trước khi thử faults:

- Chọn **rate cap** và **bounded in-flight**, ví dụ 100 CQL writes/s và tối đa 32 requests đang xử lý trên một runner lab; con số phải phù hợp tài nguyên thực.
- Giữ **row bytes, TTL, CL, number of clients** không đổi giữa các phases khi so sánh; không đổi nhiều biến cùng lúc.
- Tránh workload đóng vòng `while(true)` gửi async futures không giới hạn: nó đo overload của client/driver trước khi đo replica failure.
- Bổ sung **zero-load canary** ghi vài ID trước thử fault để xác minh logic/ledger test đúng.

## 10. Phase B — Làm R3 vắng mặt có kiểm soát

### 10.1. Chọn đúng replica và ghi marker fault

Với ba node và RF=3 ở cùng DC, **mọi node đều là natural replica** của các partition trong lab. Nếu node count lớn hơn RF, trước hết phải xác định replica set thực (metadata/driver token map hoặc công cụ/kiểm chứng phù hợp), không dừng ngẫu nhiên một node.

~~~bash
# Chỉ thực hiện trên cluster test của riêng bạn:
docker compose exec -T cassandra1 nodetool status
docker compose stop cassandra3

# Đợi với deadline và kiểm tra R3 được những node còn lại xem là down:
docker compose exec -T cassandra1 nodetool status
docker compose exec -T cassandra2 nodetool status
~~~

**Đừng giả định `docker compose stop` lập tức đồng nghĩa mọi coordinator đã nhận biết node down.** Gossip/failure detector có thể cần thời gian; có thể có request timeout trong giai đoạn chuyển trạng thái. Ghi **`fault_start_utc`**, thời điểm `R3=DN` được quan sát và phiên bản Cassandra.

### 10.2. Dừng node khác với ngắt một đường mạng

| Fault | Điều xảy ra | Rủi ro/ý nghĩa |
| --- | --- | --- |
| **Stop R3 process/container** | Node R3 không ACK và không nhận direct writes. | Đơn giản, rõ thời điểm phục hồi; hinting có thể được kích hoạt. |
| **Chặn traffic R3 ↔ các node khác** | R3 có thể vẫn chạy nhưng bị network partition. | Có thể tạo split visibility/gossip delay; cần thu hồi toàn bộ network rules sau test. |
| **Chặn client → R3 nhưng internode traffic còn** | Driver không dùng R3 làm coordinator, nhưng R3 vẫn có thể nhận replica mutations. | **Không** phải test “replica missed writes”; chỉ là client-path failure. |
| **Chặn coordinator → R3 một chiều** | Phức tạp hơn vì ACK/gossip/path asymmetry. | Kết quả phụ thuộc topology; cần chuyên môn chaos/network và kiểm tra no hidden routes. |
| **Dừng R1 và R2 cùng lúc** | Không còn quorum local RF=3. | Lỗi khác hẳn; không dùng làm test cơ sở, có thể khiến writes thất bại. |

Trong thí nghiệm cơ sở, dùng **stop R3**. Nếu muốn kiểm thử network partition, tách case và có cleanup script/rollback được thử trước; **không** chèn quy tắc firewall phá hoại tùy tiện lên host production.

### 10.3. Kỳ vọng vào lúc R3 down

~~~text
R1  UP/NORMAL
R2  UP/NORMAL
R3  DOWN/NORMAL (quan sát trên peers, tùy trạng thái hiển thị)

LOCAL_QUORUM on RF3:
  -> cần hai full replica ACK
  -> có thể thành công trên R1/R2

ALL on RF3:
  -> cần cả ba ACK
  -> không đáp ứng khi R3 down
~~~

**Không phải tất cả request sẽ thành công ngay**: nếu R1/R2 bận, network chập chờn, driver chưa chọn lại coordinator, hoặc có lỗi thứ hai, `LOCAL_QUORUM` vẫn có thể timeout/`Unavailable`.

## 11. Phase C — Ghi trong outage bằng Java Driver, giữ danh tính sự kiện ổn định

### 11.1. Prepared insert với một `CqlSession`

Ví dụ cho Java Driver 4.x, chạy client **cùng mạng với các contact points** hoặc trong staging có địa chỉ được driver discovery đúng. Client cần dùng `CqlSession` sống lâu và account ít quyền:

~~~java
// FaultEventWriter.java
package example.cassandra.faultlab;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;

public final class FaultEventWriter {
    public record Event(
        String deviceId, LocalDate day, Instant at,
        UUID eventId, String type, String payload) {}

    private final CqlSession session;
    private final PreparedStatement insert;
    private final Semaphore permits = new Semaphore(16);

    public FaultEventWriter(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO fault_lab.events_by_device_day " +
            "(device_id,event_day,event_time,event_id,event_type,payload,deleted) " +
            "VALUES (?,?,?,?,?,?,false)");
    }

    // Stable identity for retry of the SAME logical operation:
    public static UUID stableEventId(String runId, int sequence) {
        byte[] key = (runId + ":" + sequence)
            .getBytes(StandardCharsets.UTF_8);
        return UUID.nameUUIDFromBytes(key);
    }

    public CompletionStage<UUID> writeAsync(Event event) {
        if (!permits.tryAcquire()) {
            return CompletableFuture.failedFuture(
                new RejectedExecutionException("fault-lab in-flight limit"));
        }
        try {
            BoundStatement statement = insert.bind(
                    event.deviceId(), event.day(), event.at(),
                    event.eventId(), event.type(), event.payload())
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
                .setIdempotent(true);

            return session.executeAsync(statement)
                .thenApply(ignored -> event.eventId())
                .whenComplete((id, error) -> permits.release());
        } catch (RuntimeException dispatchError) {
            permits.release();
            return CompletableFuture.failedFuture(dispatchError);
        }
    }
}
~~~

**Giải thích quan trọng:**

1. `stableEventId(runId,sequence)` dùng để cùng **logical event** có khóa nhất quán giữa các lần retry. Nếu mỗi retry sinh UUID mới, test có thể tăng số rows nhưng vẫn tưởng “ghi bền”.
2. `event_time` cũng là một phần primary key; retry **phải giữ nguyên timestamp/partition day**, không chỉ UUID.
3. `setIdempotent(true)` là khai báo cho **driver** phục vụ chính sách retry/speculative execution, **không tự biến mọi câu CQL thành idempotent**. Ví dụ plain insert với cùng full key/values, không TTL/counter, thích hợp để minh họa; nếu có custom timestamp, TTL, LWT, batches hay side effects, phải đánh giá lại.
4. `Semaphore(16)` là **admission gate cho writer instance**, không phải trần trên cả fleet. Nếu vượt slot, trả lỗi rõ, không tạo queue vô hạn; điều chỉnh theo SLO/capacity và chia budget với những workloads khác.
5. `whenComplete` trả slot khi stage hoàn tất, kể cả khi exception. **Không block trong callback driver**.
6. Stage trả lỗi `WriteTimeout` không có nghĩa mutation chưa tới replica nào. Ledger phải phân biệt **ACKed**, **failed definitely** và **unknown outcome** để reconciliation.
7. Java code chỉ là write path; trách nhiệm close `CqlSession` thuộc application lifecycle **sau khi drain work**, không đóng ngay sau mỗi async call.

### 11.2. Gửi workload trong outage

Trong runner đã chặn input rate, phát các `Event` sau khi **R3 đã được peers xem là down**. Ví dụ:

~~~text
runId   = faultlab-20261121-A
device  = device-fault-7
day     = 2026-11-21
events  = 20..200 logical IDs (không tạo thêm ID khi retry)
CL      = LOCAL_QUORUM
payload = 100..500 bytes, không TTL
rate    = giới hạn phù hợp cluster test, không fan-out vô hạn

Ledger một record:
  eventId       = UUID ổn định
  fullPK        = (deviceId, day, eventTime, eventId)
  phase         = DURING_R3_DOWN
  startUtc      = ...
  acknowledged  = true/false/unknown
  errorClass    = ...
  responseTime  = ...
  attemptedCL   = LOCAL_QUORUM
~~~

**Mục tiêu phase này:** chứng minh những writes có đủ hai ACK vẫn được client chấp nhận khi R3 down; đồng thời tạo một khoảng mutation R3 **không trực tiếp nhận được**. Chỉ tính những IDs đã có **ACK** vào tập “chắc chắn đã được ghi đạt CL”; với timeout, ghi riêng để đối soát.

### 11.3. Đừng tăng tốc trước khi đo correct behavior

Chạy 20–100 events nhỏ để test correctness, sau đó mới tăng tải cho đo hiệu năng. Nếu ngay phase nhỏ đã sai IDs, gặp `Unavailable` bất thường hoặc schema mismatch, dừng và sửa; một triệu inserts/s sẽ khiến phân tích khó hơn.

## 12. Đọc trong outage: thấy dữ liệu không có nghĩa R3 đã có dữ liệu

Sau khi `writeAsync` được ACK ở `LOCAL_QUORUM`:

~~~sql
-- Thực hiện cqlsh từ node khỏe; đây không phải CQL embedded trong Java.
CONSISTENCY LOCAL_QUORUM;

SELECT event_time,event_id,event_type,payload
FROM fault_lab.events_by_device_day
WHERE device_id='device-fault-7' AND event_day='2026-11-21'
LIMIT 500;
~~~

Nếu các expected IDs đều có mặt, phép đo chứng minh **đường đọc quorum đạt được kết quả trong tình huống thử**. **Nó chưa chứng minh R3 đã có mutation**, vì R3 đang vắng mặt và read được phục vụ bởi R1/R2.

### 12.1. Vì sao thử `LOCAL_ONE` cũng không đủ?

`LOCAL_ONE` có thể chọn **bất kỳ full replica phù hợp** trong local DC. Khi R3 trở lại nhưng chưa bắt kịp, một read `LOCAL_ONE` **có thể** trả phiên bản cũ nếu chọn R3; một read khác từ R1/R2 có thể trả dữ liệu mới.

Tuy nhiên:

- Chỉ pin **coordinator node** trong Java Driver `Statement.setNode` **không bảo đảm** server chọn chính coordinator đó làm **replica đọc cục bộ**.
- Các lần `SELECT LOCAL_ONE` trả giống nhau không chứng minh mọi replica đã hội tụ: có thể cùng được phục vụ từ node khỏe.
- `LOCAL_QUORUM` có thể sử dụng cơ chế read repair cho phần dữ liệu được hỏi, vô tình giảm sai lệch của chính partition probe; nó **không** thay test anti-entropy cho toàn token range.
- Nếu muốn khảo sát “mỗi replica có cell gì”, cần **thiết kế test chuyên biệt có kiểm soát cách định tuyến/isolated replica hoặc công cụ validation phù hợp**, không suy từ driver contact point mà không kiểm chứng read path.

### 12.2. Phân biệt ba lớp chứng cứ

~~~text
Client:
  200 OK / ACK ở LOCAL_QUORUM
    => Operation đạt contract CL.

Cluster service:
  Hints delivered, no pending hints báo cáo
    => Handoff tiến triển trên scope đã quan sát.

Replica correctness:
  Full repair/validation + kiểm dữ liệu theo phạm vi replica
    => Bằng chứng mạnh hơn về hội tụ; vẫn có giới hạn nếu dữ liệu đổi song song.
~~~

Một công cụ `nodetool status` không trả từng key replica có gì, và `COUNT(*)` của quorum read chỉ đếm logic rows. Cần tránh mọi báo cáo “100% replicas consistent” nếu chưa có chứng cứ phù hợp.

## 13. Hint được tạo và giữ ở đâu?

Khi coordinator phát hiện một target replica không nhận được mutation trong điều kiện cho phép, Cassandra có thể lưu **hint trên filesystem của chính coordinator** để giao sau. Mỗi hint liên quan **replica đích**, serialized mutation, timestamp và metadata. Không nên mô tả hint như một hàng bình thường trong `system` keyspace hay commit log của replica đang down.

### 13.1. Các điều kiện ảnh hưởng hint

| Điều kiện | Ý nghĩa |
| --- | --- |
| `hinted_handoff_enabled` | Feature bật/tắt theo version/config. |
| `hinted_handoff_disabled_datacenters` | Có thể tắt handoff với những DC cụ thể. |
| `max_hint_window` / `max_hint_window_in_ms` | **Khoảng thời gian tối đa sau khi một node down mà các hint mới còn được tạo**, không phải TTL bảo đảm mọi hint tồn tại/được giao. |
| Coordinator disk/retention | Hints cần local storage; disk full/corruption/loss có thể khiến thiếu hints. |
| Coordinator lifetime | Hints có thể được giữ qua restart khi storage bền và xử lý đúng, nhưng mất coordinator/disk cũng có thể mất hint. |
| Giao tiếp tới replica đích | Replica phải trở lại và có thể nhận được hint replay; network/permissions/throughput có thể làm delivery chậm. |
| Keyspace/table mutation semantics | Hints giữ mutation timestamp gốc, giúp áp dụng lại tương thích hòa giải timestamp; **không** bảo đảm sửa mọi sai lệch do expired tombstone hoặc state đã mất nguồn. |

**Quy tắc nhớ:** nếu R3 down lâu quá hint window, Cassandra thường **ngừng tạo hints mới cho R3**; không suy rằng những hints đã tạo trước đó tự biến mất ngay tại mốc window. Ngược lại, hints có thể bị mất/thiếu vì các nguyên nhân vận hành khác dù outage ngắn hơn window.

### 13.2. Cửa sổ hint phụ thuộc phiên bản

~~~yaml
# cassandra.yaml — biểu diễn Ý ĐỊNH, KHÔNG copy nguyên vào mọi version.
hinted_handoff_enabled: true
hinted_handoff_disabled_datacenters: []

# Cassandra đời mới có tên kiểu:
max_hint_window: 3h

# Cassandra đời cũ có thể dùng:
# max_hint_window_in_ms: 10800000
~~~

Mức `3h` là mặc định được tài liệu Cassandra nêu cho nhiều dòng phát hành, **không phải lời hứa tất cả deployments đều dùng đúng 3 giờ**. Kiểm tra **effective configuration** từng node: operator có thể override/runtime modify hoặc disable hints theo DC.

### 13.3. Hints không miễn phí

Hints chiếm **disk** trên coordinator, CPU để serialize/compress, network để replay và I/O trên target. Khi R3 trở lại, replay một backlog lớn có thể làm **p99 của traffic online tăng**, chưa kể compaction và repair đồng thời.

**Không dùng hinted handoff như message queue vô hạn hoặc hệ thống backup**. Nó được thiết kế để giảm sai lệch trong các outage hữu hạn, không bảo đảm mọi write lịch sử luôn có thể hồi phục chỉ từ hints.

## 14. Hints configuration và lệnh quan sát theo phiên bản

### 14.1. Những setting cần biết

| Nhóm | Tên cấu hình thường gặp (Cassandra đời mới) | Ý nghĩa |
| --- | --- | --- |
| Bật/tắt | `hinted_handoff_enabled` | Có tạo/giao hints hay không. |
| DC policy | `hinted_handoff_disabled_datacenters` | Vô hiệu handoff đến DC liệt kê. |
| Cửa sổ | `max_hint_window` | Khoảng outage tiếp tục tạo hints mới. |
| Tốc độ | `hinted_handoff_throttle` | Giới hạn tốc độ giao hint, ảnh hưởng thời gian catch-up. |
| Luồng giao | `max_hints_delivery_threads` | Số thread delivery, cần cân nhắc multi-DC/traffic. |
| Storage | `hints_directory`, `max_hints_file_size` | Đường dữ liệu và kích cỡ segment hints. |
| Flush/compress | `hints_flush_period`, `hints_compression` | Overhead lưu trữ/delivery. |

Ở Cassandra 3.x nhiều setting tương đương có hậu tố **`_in_ms`**, **`_in_kb`**, **`_in_mb`**. Đừng đọc một doc v5 rồi đặt `max_hint_window` vào Cassandra 3.11 mà không kiểm tra parser/config.

### 14.2. `nodetool` để xem, không tự sửa

~~~bash
# Chạy trên TỪNG coordinator/điểm lưu hints của cluster lab:
nodetool status
nodetool statushandoff
nodetool getmaxhintwindow
nodetool info
nodetool tpstats
nodetool compactionstats
~~~

`getmaxhintwindow` được thêm từ Cassandra 4.0. `statushandoff` phản ánh trạng thái handoff theo node; **không** phải khẳng định tất cả hints cho R3 đã được phát thành công. Phải kết hợp **hints metrics, logs, backlog và read/repair validation**.

### 14.3. Những lệnh thay đổi trạng thái có rủi ro

~~~text
nodetool pausehandoff       # Dừng delivery (không tự dừng ghi mới).
nodetool resumehandoff      # Tiếp tục delivery.
nodetool disablehandoff     # Tắt lưu/giao hints theo behavior bản đang chạy.
nodetool enablehandoff      # Bật lại.
nodetool truncatehints      # Xóa hints — NGUY HIỂM, không dùng để dọn backlog.
nodetool setmaxhintwindow   # Sửa hint window runtime, áp dụng đúng phạm vi.
~~~

**Các lệnh trên chỉ là bản đồ chức năng**; không chạy thay đổi cấu hình trên production ngoài change request đã duyệt. Nếu có nhiều coordinator giữ hints, chỉ thay một node có thể tạo **config drift** và test sai. Tạo fault “hint bị mất” bằng việc `truncatehints` là một test **destructive riêng**, không phải bước bắt buộc của flow cơ bản.

## 15. Phase D — Khôi phục R3 và quan sát hinted handoff

### 15.1. Cho node trở lại bằng đúng persistent volume

~~~bash
# Trên cluster Docker lab, SAU khi đã dừng writer phase outage:
docker compose start cassandra3

# Đợi ring/gossip ổn định có deadline:
docker compose exec -T cassandra1 nodetool status
docker compose exec -T cassandra2 nodetool status
docker compose exec -T cassandra3 nodetool status
~~~

**Giữ volume `cassandra3-data` gốc.** Nếu xóa volume rồi tạo node mới, đây là **node replacement/bootstrap**, không còn là thử “replica cũ trở lại và nhận hints”. Replacement cần token/host ID/streaming/repair runbook riêng.

Chỉ bắt đầu phase đo phục hồi sau khi:

1. R3 chạy với đúng **cluster name**, `dc1`, rack/token/host ID dự kiến và không ở trạng thái join/move/replace bất thường.
2. Cassandra native transport/internode communication đã trở lại và peers thấy R3 `UN`.
3. Disk/heap/compaction không ở ngưỡng nguy hiểm ngay khi startup.
4. Các coordinator còn giữ hint files và feature handoff đang bật theo effective config.

### 15.2. Quan sát handoff ở **coordinators**, không chỉ ở R3

~~~bash
docker compose exec -T cassandra1 nodetool statushandoff
docker compose exec -T cassandra2 nodetool statushandoff
docker compose exec -T cassandra1 nodetool tpstats
docker compose exec -T cassandra2 nodetool tpstats
docker compose exec -T cassandra3 nodetool tpstats
docker compose exec -T cassandra3 nodetool compactionstats
~~~

Khi hint delivery bắt đầu, theo dõi **metrics/JMX và logs** theo phiên bản:

- Tổng số hints **created**, pending/file bytes, dispatched/received, failed/dropped, delivered latency nếu available.
- Backlog theo target node và tốc độ **delivery bytes/s**.
- Disk free/headroom trên coordinator và R3; CPU, GC, compaction trên R3.
- Application request throughput, error rate và p95/p99 lúc handoff chạy.
- Nếu có **DC hint exclusion** hoặc handoff bị pause, xác minh không đặt lại sai sau test.

Các tên metric MBean cụ thể có thể khác giữa Cassandra 3.11/4.x/5.x; tài liệu Hints chính thức và metrics reference của bản triển khai là nguồn đúng. **Không chỉ dùng kích thước thư mục `hints` tại một node** để khẳng định toàn cluster đã catch up.

### 15.3. Cùng lúc phục vụ traffic và nhận hints

~~~mermaid
flowchart LR
    A["CQL request bình thường"] --> B["R1/R2/R3 phục vụ workload"]
    C["Hints backlog trên coordinators"] --> D["Hint delivery threads"]
    D --> E["R3 replay mutations"]
    E --> F["Memtable/SSTable/compaction của R3"]
    B --> G["Disk/CPU/network budgets chung"]
    F --> G
    G --> H["p95/p99 và recovery lag"]
~~~

Replay có thể tranh tài nguyên với reads/writes, compaction, repair. Không tăng `max_hints_delivery_threads` hoặc handoff throttle vô hạn để “càng nhanh càng tốt”: cần giữ **SLO online và disk/network headroom**. Nếu p99 tăng quá stop criteria, giảm batch/backfill hoặc điều chỉnh handoff bằng runbook đã duyệt.

### 15.4. Ghi nhận trạng thái hint catch-up

~~~text
R3 returned at (UTC)         = ...
R3 observed UN at            = ...
last hint queued             = ...
last hint delivered/acked    = ...
pending hint bytes per host  = ...
handoff failures/retries     = ...
ACKed event IDs from outage  = ...
validation query count/hash  = ...
repair scope/status          = ...
~~~

**Hint counters về 0 không chứng minh một mutation chưa từng được hinted đã được sửa**; tiếp tục bước validation/anti-entropy đúng phạm vi.

## 16. Thí nghiệm A — Outage ngắn, hints được phát lại

### 16.1. Giả thuyết

Khi R3 down ngắn hơn effective `max_hint_window`, các coordinators khỏe, hints được bật và lưu giữ, R3 trở lại thì các hints **có thể** giúp R3 bắt kịp những writes đã bị missed. Đây là một **giả thuyết cần đo**, không phải lời hứa giao đủ 100% từ Cassandra.

### 16.2. Thực thi theo mốc

1. **Baseline:** ba nodes `UN`, keyspace RF=3 và fixture riêng, xác minh đọc/ghi `LOCAL_QUORUM` ổn định.
2. **Fault:** dừng R3; chờ peers thấy R3 down, ghi mốc UTC.
3. **Write:** phát N event IDs trong outage với `LOCAL_QUORUM`, ledger phân loại ACK/fail/unknown.
4. **Restore:** khởi động lại đúng R3/volume; quan sát membership và handoff logs/metrics trên tất cả coordinators.
5. **Wait bounded:** đợi delivery gần hoàn tất hoặc hết deadline thử; **không** đợi vô hạn.
6. **Validate:** so ACKed IDs/values với read sau recovery ở scope xác định, quan sát hinted delivery/repair preview.
7. **Report:** cho biết có bao nhiêu IDs được ACK, bao nhiêu hints được tạo/giao, duration, p99 impact, phần còn không được chứng minh.

### 16.3. Kết luận phù hợp từ test A

**Có thể kết luận:** `LOCAL_QUORUM` đáp ứng availability trong một-fault case, hints được tạo/giao theo metrics, và các IDs được xác minh đọc lại đạt kết quả theo hợp đồng test.

**Không được kết luận chỉ từ test A:** mọi token range/table trong cluster đã được repaired, mọi replica đã hoàn toàn nhất quán, hoặc R3 có thể down vô thời hạn rồi vẫn được hồi phục chỉ bằng hints.

## 17. Thí nghiệm B — Không còn hints đầy đủ, vẫn phải repair

### 17.1. Hai cách tạo tình huống trong **lab riêng**

**Cách 1: chủ động vô hiệu hinted handoff trên các node có thể làm coordinator**, sau đó dừng R3 và ghi workload kiểm soát. Cần bật lại sau case, đồng thời nhận thức rằng việc bật lại **không tự tạo những hints đã bỏ lỡ**:

~~~bash
# CHỈ trong lab cô lập, trước khi bắt đầu writes của case B:
docker compose exec -T cassandra1 nodetool disablehandoff
docker compose exec -T cassandra2 nodetool disablehandoff

docker compose stop cassandra3
# Ghi fixture bằng LOCAL_QUORUM qua R1/R2, lưu ledger.
docker compose start cassandra3

# Phục hồi cấu hình handoff ở các coordinators:
docker compose exec -T cassandra1 nodetool enablehandoff
docker compose exec -T cassandra2 nodetool enablehandoff
~~~

**Cách 2:** đặt **hint window ngắn có chủ đích trong test** (tất cả coordinators) và giữ R3 down vượt cửa sổ, rồi viết thêm mutations sau mốc ấy. Không cần giữ production node down 3 giờ; **đừng giảm tombstone grace** để “rút ngắn bài test”. Một số version có runtime `nodetool setmaxhintwindow`, version khác cần sửa `cassandra.yaml` và rolling restart trước thí nghiệm. Cần verify effective settings trên từng node.

### 17.2. Vì sao một số mutations có thể vẫn thiếu?

`disablehandoff` khiến hints không được tạo/giao theo scope của lệnh. Nếu R3 down lúc write, R1/R2 đủ `LOCAL_QUORUM` nhưng R3 không nhận mutation. Khi R3 quay lại, bật handoff **không replay được một hint chưa từng tồn tại**. Tương tự, viết quá hint window có thể không tạo hint mới cho endpoint down.

**Vẫn cần phân biệt**: read repair hay workload khác có thể tình cờ sửa partition probe trước khi bạn đo. Khi muốn chứng minh riêng tác động anti-entropy, hạn chế các read có thể kích hoạt read repair và ghi lại các thao tác đã làm trong lab.

### 17.3. Mục tiêu của test B

| Câu hỏi | Kiểm tra |
| --- | --- |
| Quorum write trong outage còn thành công không? | Ledger ACKed IDs với `LOCAL_QUORUM`. |
| Hint pipeline có đủ để làm R3 bắt kịp không? | Effective handoff config, hints metrics, phát hiện no-hint phase. |
| Các replicas còn lệch dữ liệu trước repair không? | Repair preview/validation theo token/table, hoặc phương pháp replica-scoped đã xác minh đường đọc. |
| Anti-entropy repair có xử lý đúng phạm vi sai lệch không? | Repair logs, Merkle/streaming, completions, post-repair validation. |
| Sau repair, client đọc có kết quả đúng không? | So ACKed ledger IDs/values, CL và partition range đúng; không nuốt timeout. |

**Kết quả mong đợi:** test cho thấy **có thể ghi đạt quorum khi replica down mà vẫn cần repair để hội tụ đầy đủ**. Đây là minh họa trực tiếp vì sao hints không thay anti-entropy.

## 18. Anti-entropy repair: Merkle trees, streaming và phạm vi công việc

### 18.1. Repair không phải “đẩy toàn bộ DB từ một node sang node khác”

Cassandra repair phối hợp các nodes có cùng **token ranges**; so sánh dữ liệu, thường dùng cấu trúc **Merkle trees** cho ranges, để nhận diện sai khác rồi stream phần cần thiết. Điều này khác hint:

~~~mermaid
flowchart TD
    A["Chọn keyspace/table + token ranges/DCs"] --> B["Repair session/participants"]
    B --> C["Xây so sánh Merkle trees"]
    C --> D{"Có sai khác?"}
    D -->|Không| E["Hoàn thành validation của phạm vi đó"]
    D -->|Có| F["Streaming data chênh lệch"]
    F --> G["Replica cùng range bắt kịp theo repair protocol"]
    G --> H["Ghi repair result và tiếp tục range khác"]
~~~

Repair không khôi phục được event nếu **không replica/bản sao backup/nguồn dữ liệu nào còn giữ event ấy**, hoặc tombstone đã bị thu hồi khiến hệ không còn đủ thông tin delete. Vì vậy correctness còn phụ thuộc retention, backup và repair cadence.

### 18.2. Full, incremental, preview, validate

| Loại | Phạm vi thực chất | Khi sử dụng |
| --- | --- | --- |
| **Incremental repair** | Theo unrepaired data kể từ những đợt incremental trước theo semantics/version. | Lịch anti-entropy định kỳ cho cluster có incremental repair strategy. |
| **Full repair** (`--full`) | So sánh toàn bộ data thuộc token ranges được chọn, không chỉ phần unrepaired. | Đối chiếu sau nghi ngờ sai lệch kéo dài, disk corruption/restore, change RF hay policy định kỳ. |
| **Preview repair** (`--preview`) | Xây so sánh/ước lượng streaming, **không stream dữ liệu sửa**. | Đoán phạm vi sai khác trước khi áp repair; vẫn có CPU/disk/network cost. |
| **Validation** (`--validate`) | Kiểm tra dữ liệu **đã marked repaired** theo semantics tool, không stream sửa. | Kiểm chứng repaired data, điều tra; không thay một full repair khi có unrepaired ranges. |

Trong nhiều bản Cassandra hiện đại, `nodetool repair` mặc định làm **incremental**; muốn **full** phải thêm `--full`. Không dùng một repair command đơn lẻ rồi kết luận cả cluster repaired: mỗi lệnh có scope node/token ranges/table/DC, một node không nhất thiết bao quát cả ring.

### 18.3. Lệnh chỉ cho cluster lab

~~~bash
# Đợi R1/R2/R3 đều UN, kiểm RAM/disk/network headroom.
# Preview một full repair cho table được giao, không sửa dữ liệu:
docker compose exec -T cassandra1 nodetool repair --full --preview fault_lab events_by_device_day

# Full repair primary token ranges của từng node:
# LẬP LỊCH tuần tự, không ồ ạt chạy cả ba song song.
docker compose exec -T cassandra1 nodetool repair --full --partitioner-range fault_lab events_by_device_day
docker compose exec -T cassandra2 nodetool repair --full --partitioner-range fault_lab events_by_device_day
docker compose exec -T cassandra3 nodetool repair --full --partitioner-range fault_lab events_by_device_day
~~~

**`--partitioner-range` / `-pr`** giới hạn primary token ranges của node gọi lệnh, giúp giảm công việc trùng khi chạy lịch qua các nodes để bao phủ ring. Nếu repair tool/orchestrator của tổ chức đã quản lý toàn bộ token ranges, dùng tool ấy thay vì tự chạy ba lệnh; thứ tự, concurrency, exclusions và retry đều phải được kiểm soát.

### 18.4. Đừng quên repair scope trong multi-DC

`nodetool repair --in-local-dc` hoặc các tùy chọn DC-specific có thể giới hạn đối tượng tham gia. Nếu cần **hội tụ giữa hai datacenters**, chỉ chạy local repair trong từng DC có thể chưa đáp ứng mục tiêu cross-DC đã định. Cần kế hoạch cross-DC repair an toàn theo version/topology và WAN bandwidth/SLO; không “chạy `--force` bỏ qua down endpoints” rồi tuyên bố mọi replica hội tụ.

### 18.5. Lịch repair không phải tùy chọn xóa khỏi vận hành

Repair định kỳ phải đủ thường xuyên để những deletes/tombstones không mất thông tin trước khi các replica chậm được đồng bộ, xét `gc_grace_seconds` của từng table và outage/maintenance window. Cassandra documentation đưa ra các mốc lịch ví dụ, **không phải one-size-fits-all**; hạ tầng có dữ liệu lớn nên chia **token subranges**, phân bổ jobs, tránh overlaps/GC/disk saturation và theo dõi **coverage**, không chỉ số lệnh đã chạy.

## 19. Kiểm chứng hội tụ: cần biết bằng chứng nào thực sự chứng minh điều gì

### 19.1. Năm tầng validation

| Tầng | Bằng chứng | Suy luận hợp lệ | Chưa đủ để suy |
| --- | --- | --- | --- |
| 1. Membership | R3 `UN` trên peers. | Node đã join lại và peers coi là up. | Mọi mutation missed đã có ở R3. |
| 2. Client CL | `SELECT LOCAL_QUORUM` trả ACKed IDs. | Read quorum trả kết quả đúng ở thời điểm/partition kiểm. | R3 đồng bộ với R1/R2. |
| 3. Hints | Handoff metrics cho thấy queued/delivered/failed. | Hints còn được lưu đã được xử lý theo scope. | Hints không bao giờ bị thiếu/mất ngoài quan sát. |
| 4. Repair | Repair/preview/validate logs qua đúng ranges/tables, finished. | Sai khác của những participants/ranges đã được so/sửa theo job. | Những keyspaces/ranges ngoài scope hoặc dữ liệu đã mất hoàn toàn. |
| 5. Logical ledger | Mọi ACKed ID/value (cả UPDATE/DELETE theo semantics) được đối chiếu. | Nghiệp vụ query cho kết quả đúng trên tập test. | Tự chứng minh một node riêng đã lưu mọi cell nếu read path không pin replica. |

**Kết luận cần đặt tên rõ:** “Quorum reads passed all fixture partitions and full repair for `fault_lab.events_by_device_day` primary token ranges completed”, không viết trống “Cassandra đã hội tụ 100%” khi chỉ kiểm một partition.

### 19.2. Đối chiếu ledger bằng Java hoặc query bounded

~~~java
// Pseudocode trong test harness, không phải API Java Driver có sẵn:
Set<UUID> expectedAcked = ledger.ackedEventIds("DURING_R3_DOWN");
Set<UUID> actual = reader.selectEventIds(
    "device-fault-7", LocalDate.of(2026, 11, 21),
    DefaultConsistencyLevel.LOCAL_QUORUM);

Set<UUID> missing = new HashSet<>(expectedAcked);
missing.removeAll(actual);

assertTrue(missing.isEmpty(),
    "Missing ACKed event IDs: " + redactOrSummarize(missing));
~~~

**Pseudocode được đánh dấu rõ**: `ledger`, `reader`, `redactOrSummarize` là helpers của project, không nằm trong Java Driver. Với fixture nhỏ, có thể đọc hết partition rồi so keys/values. Với bảng lớn, không chạy `COUNT(*)` toàn keyspace hoặc `SELECT *` không có partition scope để “check convergence”. Đối chiếu theo **bounded token/key ranges** và nguồn ledger đã được kiểm toán.

### 19.3. “Đọc từ R3” không đơn giản là chọn contact point R3

Điều quan trọng cho kỹ sư Java: `new InetSocketAddress("cassandra3",9042)` chỉ giúp driver **kết nối khám phá topology**; coordinator do driver chọn và replica được coordinator hỏi có thể khác. `setNode(R3)` ép coordinator nhưng **không mặc định ép read request chỉ dùng storage local R3**. Nếu cần test nội dung storage R3 độc lập, thiết kế environment/replica isolation hoặc validation/repair-specific tooling, ghi rõ ảnh hưởng tới CL và không dùng thử nghiệm gây cô lập làm chỉ số production availability.

## 20. TTL, tombstone và vì sao repair trễ có thể sinh zombie data

### 20.1. Xóa trong lúc R3 down

Giả sử trước outage, một hàng đã tồn tại ở cả R1/R2/R3. Khi R3 down:

~~~sql
-- CQL thực hành, cần đủ full primary key của hàng đã seed.
DELETE FROM fault_lab.events_by_device_day
WHERE device_id='device-7'
  AND event_day='2026-11-21'
  AND event_time='2026-11-21T08:00:00Z'
  AND event_id=123e4567-e89b-42d3-a456-426614174001;
~~~

Nếu delete đạt `LOCAL_QUORUM` trên R1/R2, các replicas đó ghi **tombstone** còn R3 có thể giữ **giá trị cũ**. Khi hint delivery/repair thực hiện đúng lúc, tombstone được đưa tới R3 để xóa logic row ấy.

### 20.2. Phản ví dụ khi xóa tombstone quá sớm

~~~mermaid
sequenceDiagram
    participant R1 as R1
    participant R2 as R2
    participant R3 as R3 (down)
    R1->>R1: DELETE -> tombstone
    R2->>R2: DELETE -> tombstone
    Note over R3: Vẫn giữ live row cũ
    Note over R1,R2: Không repair trước khi grace hết
    Note over R1,R2: Compaction có thể thu hồi tombstone
    R3-->>R1: Replica cũ trở lại với row
    Note over R1,R3: Có nguy cơ zombie data tái xuất hiện
~~~

**`gc_grace_seconds`** là một rào an toàn trong quá trình quản lý tombstone/anti-entropy, không phải “TTL bao lâu” của một hàng. Nếu các replica không repair khi dữ liệu delete còn được giữ, tombstone có thể được dọn sau grace/compaction và một bản copy cũ có thể tái xuất hiện khi đồng bộ. Đây là một lý do repair phải **đủ thường xuyên so với gc grace**, và outage kéo dài cần xử lý theo runbook.

### 20.3. Test TTL và delete an toàn

| Case | Điều nên đo | Điều không làm |
| --- | --- | --- |
| Write có `USING TTL`, R3 down. | Thời gian row sống, hints/repair, TTL reconciliation. | Không tự kỳ vọng hint replay gia hạn TTL từ lúc replay. |
| Delete trong outage. | Tombstone được đồng bộ qua handoff/repair, read trả deleted state theo CL. | Không coi `SELECT` không thấy hàng từ R1/R2 là bằng chứng R3 đã xóa. |
| Node down gần grace. | Alert repair deadline/lag, quyết định recovery/replace. | Không ép grace cực nhỏ để tạo bug trên production. |
| Repair quá trễ. | Báo data-risk, đánh giá backup/restore và full repair. | Không khẳng định repair có thể khôi phục thông tin tombstone đã mất hoàn toàn. |

Hãy dùng một **fixture riêng** cho tombstone/TTL, vì ledger event immutable ở những bài test trước có assertion “mọi ACKed insert phải còn sống”. Không áp cùng assertion đó cho sự kiện cố ý xóa/hết hạn.

## 21. Multi-datacenter: local outage không tự chứng minh hội tụ liên vùng

Giả sử:

~~~sql
CREATE KEYSPACE IF NOT EXISTS fault_lab_multidc
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3,
  'dc2': 3
};
~~~

### 21.1. `LOCAL_QUORUM` và `QUORUM` khác nhau

| CL | Điều được yêu cầu | Ảnh hưởng khi DC khác tạm mất kết nối |
| --- | --- | --- |
| `LOCAL_ONE` | Một full replica tại local DC. | Có thể thành công local nhưng remote chưa bắt kịp. |
| `LOCAL_QUORUM` | Đa số full replicas của **local DC** (2/3 trong ví dụ). | Không cần remote quorum ACK, nên remote có thể lag. |
| `QUORUM` | Đa số tổng full replicas của keyspace theo operation (với 6 full replicas là 4). | Có thể yêu cầu liên quan WAN/remote replicas, khác local latency/availability. |
| `EACH_QUORUM` (write) | Đa số full replicas **từng DC**. | Nhạy khi một DC không đủ replica; không thay persistence/repair plan. |

Mức CL quyết định **phản hồi cần thiết**, không quyết định có tạo hint không hay mọi replica đều hội tụ ngay. Multi-DC test cần kiểm **DC-aware routing**, network latency, role/secret/cert, failure detectors và DC-specific hint configuration.

### 21.2. `hinted_handoff_disabled_datacenters`

Một số tổ chức có thể vô hiệu hinted handoff tới remote DC vì bandwidth/chiến lược vận hành. Điều đó làm **anti-entropy repair xuyên DC** càng quan trọng: `LOCAL_QUORUM` ở dc1 vẫn có thể ACK writes, trong khi một phần dc2 chưa nhận mutation.

**Không** cho rằng `nodetool repair --in-local-dc` ở từng DC đương nhiên đồng bộ dữ liệu giữa hai DC: local-only repair scope có thể bỏ qua khác biệt xuyên DC. Kế hoạch repair cần tính **tất cả DCs và ranges cần hội tụ**.

## 22. Hai replica down, mất coordinator, và kết quả không rõ: test phải phân loại

### 22.1. Hai R1/R2 down ở RF=3

Với chỉ một replica sống, write `LOCAL_QUORUM` **không thể có đủ hai full replica ACK**. Driver/coordinator có thể báo `Unavailable` hoặc timeout tùy lúc phát hiện failure/network. Test cần phân biệt **số replica thực sự sẵn sàng** với timeout do I/O và client.

### 22.2. Coordinator ngã giữa request

Nếu coordinator đã gửi mutation tới một số replicas rồi bị stop trước khi trả response:

~~~text
Client sees: timeout / connection lost
Replica state: có thể một hoặc nhiều replica đã ghi
Hint state   : có thể chưa kịp lưu, hoặc hint nằm trên coordinator down
Outcome     : unknown, KHÔNG suy chắc chắn failed
~~~

Client cần **stable primary key/event ID**, idempotent retry phù hợp và reconciliation. Khi resume, không tạo event ID ngẫu nhiên mới cho cùng logical operation chỉ vì không nhận ACK. Không retry `counter`/conditional side effects/batches theo cùng giả định của simple insert.

### 22.3. `ANY` không phải giải pháp để né quorum

`ANY` có semantics đặc biệt cho writes, có thể trả ACK nhờ hint trong những điều kiện cụ thể **mà chưa có full replica sẵn sàng cho read**. Nếu giao diện cần đọc lại ngay và nghiệp vụ cần quorum durability, không chuyển âm thầm từ `LOCAL_QUORUM` sang `ANY`; việc đó **thay đổi consistency contract**.

### 22.4. Fault matrix mở rộng

| Fault | Kỳ vọng về CL | Hành vi cần quan sát |
| --- | --- | --- |
| Một full replica R3 down, RF3. | `LOCAL_QUORUM` có thể còn thành công. | Hints có thể tạo và phát lại. |
| Hai full replicas down, RF3. | `LOCAL_QUORUM` không đủ ACK. | Unavailable/timeout theo detector; không “thành công ảo”. |
| Coordinator down nhưng replicas khỏe. | Driver reroute/retry tùy policy. | Unknown write outcome, idempotency, retries/timeouts. |
| Hints disabled hoặc ngoài window. | Quorum ACK không tự thay đổi. | R3 có thể không catch up cho đến repair. |
| Target up nhưng disk full. | Handoff/repair có thể fail/throttle. | Tăng errors, pending hints, storage metrics. |
| Network partition một chiều. | Phụ thuộc path và failure detection. | Coordinator/replica behavior, retry amplification. |
| Remote DC unreachable. | `LOCAL_QUORUM` local có thể tiếp tục. | Cross-DC divergence và repair coverage. |

## 23. Tổ chức integration/fault test Java: điều phối tách khỏi dữ liệu

Một test cần tách **(a) nguồn mutation và ledger**, **(b) fault controller có quyền dừng/start node**, **(c) client reader**, **(d) validation/repair**. Không đặt `docker compose stop` trong một production service method hoặc để CI nhầm cluster test với production.

### 23.1. Hợp đồng của một test harness có quyền hạn rõ

~~~java
// PSEUDOCODE hướng thiết kế harness; các interface là của ỨNG DỤNG,
// KHÔNG phải class có sẵn trong Apache Cassandra Java Driver.
interface FaultController {
    void assertIsDedicatedTestCluster();
    void stopReplica(String nodeId);
    void startReplica(String nodeId);
    boolean awaitNodeDown(String nodeId, java.time.Duration timeout);
    boolean awaitNodeUp(String nodeId, java.time.Duration timeout);
    boolean awaitHandoffIdle(java.time.Duration timeout);
    void ensureRestored();
}

interface EventLedger {
    void recordAttempt(String runId, java.util.UUID eventId);
    void recordAck(String runId, java.util.UUID eventId);
    void recordUnknown(String runId, java.util.UUID eventId, Throwable error);
    java.util.Set<java.util.UUID> ackedIds(String runId);
}

interface ReplicaValidation {
    void assertAckedIdsVisibleAtQuorum(
        String runId, java.util.Set<java.util.UUID> expected);
    void recordRepairScopeAndResult(String runId);
}
~~~

**Ý tưởng:** `FaultController` phải có **allowlist cluster ID/DC và lease thử nghiệm**, deadline, cleanup luôn chạy và không bao giờ được trỏ tới production. `EventLedger` nên bền trong phạm vi test, nếu runner chết giữa outage vẫn biết mutation nào đã ACK; `ReplicaValidation` không được coi một `SELECT LOCAL_QUORUM` đơn lẻ là chứng cứ mọi replica đã hội tụ.

### 23.2. Mẫu JUnit có cleanup dù assertion lỗi

~~~java
// PSEUDOCODE test orchestration, dùng adapters/harness của project.
// Không copy trực tiếp khi chưa implement các interface kể trên.
@Test
@Tag("destructive-isolated-cluster")
void oneReplicaOutageThenRecoveryNeedsConvergenceEvidence() {
    String runId = "fault-run-" + UUID.randomUUID();
    faults.assertIsDedicatedTestCluster();

    try {
        assertTrue(topology.allThreeReplicasUp());
        workload.writeBaseline(runId, 20);

        faults.stopReplica("R3");
        assertTrue(faults.awaitNodeDown(
            "R3", Duration.ofSeconds(60)));

        workload.writeBoundedQuorumEvents(runId, 100, ledger);
        // Không assert tất cả 100 succeeded: kiểm accepted/failed/unknown.
        assertTrue(ledger.ackedIds(runId).size() > 0);

        faults.startReplica("R3");
        assertTrue(faults.awaitNodeUp(
            "R3", Duration.ofMinutes(5)));

        boolean hintsDrained = faults.awaitHandoffIdle(
            Duration.ofMinutes(10));
        metrics.recordHintDrainResult(runId, hintsDrained);

        validation.assertAckedIdsVisibleAtQuorum(
            runId, ledger.ackedIds(runId));
        // Anti-entropy preview/full repair và convergence scope
        // được thực thi bởi runbook/runner chuyên dụng, ghi lại kết quả.
        validation.recordRepairScopeAndResult(runId);
    } finally {
        // Làm được kể cả khi exception, có operator escalation nếu fail.
        faults.ensureRestored();
    }
}
~~~

`faults`, `topology`, `workload`, `ledger`, `metrics` và `validation` là đối tượng **do test framework của dự án cung cấp**; đây là mẫu orchestration có chủ đích, **không phải file JUnit standalone đã biên dịch**. Mục đích là làm nổi bật thứ tự **stop → awaitDown → boundedWrites → start → awaitUp → handoff → ledger/repair validation**, kèm `finally` để không bỏ node down khi CI fail.

### 23.3. Điều kiện test có thể tự động hóa an toàn

| Check | Vì sao bắt buộc |
| --- | --- |
| Cluster ID = dedicated test cluster, không có allowlist production host. | Ngăn fault injector stop nhầm node thật. |
| R1/R2/R3 đều `UN` trước start, RF3/DC metadata đúng. | Giữ điều kiện so sánh và natural replica set. |
| Ledger ghi ngay sau ACK, unknown lưu riêng. | Không báo mất dữ liệu giả do timeout/retry ID mới. |
| `awaitDown`/`awaitUp` có deadline và log. | Không để test vô hạn hoặc đo nhầm thời điểm. |
| Cleanup/finalizer luôn restore R3 và handoff config. | Không để cluster test ở trạng thái suy giảm sau case. |
| Repair job chỉ chạy khi cả participants cần thiết đã up. | Tránh false evidence do bỏ qua down endpoints. |
| Kết quả test gắn version/image/config hash. | Cho phép tái lập và so sánh giữa các build. |

## 24. Phương pháp đo tải: baseline, fault, recovery, post-recovery

### 24.1. Bốn pha có cùng query shape

| Phase | Điều kiện | Mục tiêu | Cần ghi |
| --- | --- | --- | --- |
| **A — Baseline** | 3 replicas `UN`, hint backlog không đáng kể. | Điểm tham chiếu latency/throughput/correctness. | Arrival rate, achieved throughput, CL, error, p95/p99, resource. |
| **B — Outage** | R3 down, RF3 `LOCAL_QUORUM`, hinting enabled. | Availability dưới một fault. | Quorum success rate, timeouts, hint creation, R1/R2 resource. |
| **C — Recovery** | R3 `UN`, handoff/repair có thể chạy. | Thời gian bắt kịp và ảnh hưởng tới online traffic. | Backlog bytes, replay rate, repair progress, p99, disk/GC. |
| **D — Stabilized** | Handoff/repair jobs hoàn tất theo scope đã định. | Xác minh data correctness và SLO sau sự cố. | ACKed ledger match, full-range evidence, p99, errors. |

**Không đổi CQL, table compaction, row size, client concurrency, datacenter hoặc CL** giữa baseline và outage nếu muốn biết riêng tác động replica failure. Nếu cần đánh giá nhiều mức tải, chạy **nhiều lượt tách biệt** với thứ tự và fixture/reset đã định.

### 24.2. Open-loop và closed-loop workload

- **Closed-loop**: một client gửi request tiếp theo sau khi request trước hoàn thành. Khi latency tăng, offered rate tự giảm, có thể che hiện tượng backend quá tải.
- **Open-loop / fixed arrival rate**: workload phát yêu cầu theo một lịch tốc độ đã chọn; phản ánh áp lực đầu vào tốt hơn, nhưng **phải có bounded queue/in-flight và stop criteria** để không làm mất kiểm soát cluster.
- **Coordinated omission**: nếu load generator bỏ qua các khoảng thời gian hệ thống bị chậm vì chính nó chờ kết quả, histogram latency có thể đánh giá quá tốt. Dùng load tool/reporting methodology có điều chỉnh phù hợp, đồng thời báo achieved rate và số request rejected/queued.

Không chỉ công bố “10.000 requests/s” khi đó là **tốc độ generator cố phát**, còn thực tế chỉ 6.000 requests/s đã hoàn tất và 4.000 bị queued/rejected. Phải ghi **offered, accepted, completed, timed-out và rejected** riêng.

### 24.3. Little's Law và in-flight budget

Ở trạng thái tương đối ổn định:

~~~text
L ≈ lambda × W
  L       : số request đang tồn tại trung bình
  lambda  : throughput hoàn tất mỗi giây
  W       : thời gian request tồn tại trung bình (giây)

Ví dụ tại lambda=500 requests/s:
  mean W=0.040s => L≈20 requests
  mean W=0.200s => L≈100 requests
~~~

Nếu outage khiến latency tăng 5 lần ở cùng arrival rate, số in-flight cần thiết để giữ rate có thể tăng tương ứng. Khi service đã bão hòa, quan hệ cân bằng có thể không áp dụng ngay; **không thay mean W bằng p99** trong công thức. Lấy số thực từ driver/app metrics để định giới hạn admission, không phát vô hạn futures.

### 24.4. Không thay consistency contract để lấy số đẹp

`LOCAL_QUORUM` của RF3 khác `LOCAL_ONE` về số phản hồi replica cần thiết. Nếu baseline đo `LOCAL_ONE` rồi outage đo `LOCAL_QUORUM`, latency p99 không còn so sánh cùng workload. Có thể benchmark cả hai CL, nhưng phải **ghi thành hai test series riêng** và nêu trade-off correctness/availability.

### 24.5. Đo tail latency thay vì chỉ mean

| Metric | Lý do |
| --- | --- |
| `write_latency_p50/p95/p99` theo phase/CL. | Client SLO và tails khi coordinator/replica chậm. |
| `read_latency_p95/p99` trên partition truy vấn thật. | Chứng minh quorums/read path còn đáp ứng. |
| `hint_replay_duration`/bytes/s. | Mất bao lâu R3 bắt kịp bằng hint pipeline. |
| `repair_duration`/bytes streamed/ranges covered. | Chi phí repair và progress hội tụ. |
| `read/write timeout/unavailable` theo loại. | Tách overload, CL insufficiency và error handling. |
| `client queue/in-flight/driver retries`. | Phát hiện backpressure/retry storm. |
| JVM heap/GC, disk await/free, network, compaction. | Phân biệt vấn đề client với storage. |
| Ledger mismatch count/ID hashes. | Tính đúng dữ liệu, không chỉ hiệu năng. |

## 25. Dự toán backlog hint và thời gian replay

Giả sử một replica bị missed mutation liên tục trong outage. Một xấp xỉ để lập **capacity budget**:

~~~text
estimated_hint_bytes ≈
  missed_mutations_per_sec
  × average_serialized_mutation_bytes
  × outage_seconds
  × hint_overhead_factor

replay_time_lower_bound ≈
  hint_bytes_to_deliver / effective_delivery_bytes_per_sec
~~~

Đây **không** phải công thức chính xác của Cassandra: phân bố coordinator/token, LZ4 compression, coalescing, batching, hint eligibility, window, node discovery, parallelism, read/write workload và network congestion đều làm số thực khác đi.

### 25.1. Ví dụ định lượng

~~~text
Giả định riêng để học:
  1.000 mutations/giây missed bởi R3
  1 KiB serialized hint trung bình (chưa tính overhead)
  outage 10 phút = 600 giây
  uncompressed estimate = 1.000 × 1 KiB × 600
                        ≈ 586 MiB

Nếu effective replay chỉ 2 MiB/s:
  586 MiB / 2 MiB/s ≈ 293 giây ~ 4,9 phút
  (không gồm queue/startup/retries/compaction)
~~~

**Các con số hoàn toàn giả lập.** Một hint stream có thể tốn lâu hơn nhiều nếu throttle per delivery thread, số nodes hoặc network/replica disk bão hòa. Hints cũng phân tán trên nhiều coordinators, nên một node có 0 bytes chưa có nghĩa toàn cluster 0.

### 25.2. Điều gì xảy ra nếu recovery chậm?

Khi R3 lên và nhận hints, nó đồng thời phục vụ client reads/writes, replay mutations và compaction/flush. Nếu **tốc độ tạo công việc mới > khả năng xử lý tổng**, backlog hoặc p99 có thể không giảm. Giải pháp:

- Giảm **batch/backfill/offline analytical traffic**, giữ latency của online workload.
- Kiểm disk headroom, GC và stream throughput trước khi tăng handoff throttle.
- Đặt **deadline recovery** và cảnh báo nếu backlog không giảm theo baseline.
- Nếu hint window đã hết/loss, chuyển sang **repair/replace recovery plan**, không cố đợi hints mãi.
- Đánh giá hỏng đĩa/corruption hoặc thiếu replicas trước khi repair; không coi repair là giải pháp tự động cho disk failure.

## 26. Dashboard và bộ lệnh chẩn đoán theo từng tầng

### 26.1. Correlate ba timeline: ứng dụng, hint và repair

~~~mermaid
flowchart TD
    A["Fault marker UTC: R3 down/up"] --> B["Client: accepted, p95/p99, errors"]
    A --> C["Coordinators: hints created/pending/delivery"]
    A --> D["R3: disk/GC/compaction, hint replay"]
    B --> E["Cùng window UTC + query name + CL"]
    C --> E
    D --> E
    E --> F["Repair: token ranges, Merkle/streaming, finished/failed"]
    F --> G["Ledger: ACKed IDs và payloads, mutation/delete states"]
~~~

Mọi dashboard cần có **fault marker** (`start/stop/startup/handoff_begin/handoff_end/repair_begin/repair_end`) và phiên bản deployment. Nếu metrics không được gắn cùng time window, rất dễ quy p99 tăng cho hinted handoff trong khi thực tế một compaction hoặc GC pause xuất hiện sớm hơn.

### 26.2. Các nguồn dữ liệu cần quan sát

| Tầng | Đo gì | Không suy diễn |
| --- | --- | --- |
| **Java API/worker** | RPS offered/achieved, ACK/timeout/unavailable, retry, queue, p95/p99, pending futures. | `HTTP 200` không chứng minh tất cả replicas đã ghi. |
| **Driver 4.x** | Node/coordinator distribution, request latency, in-flight, error class, retry/speculative attempts nếu bật. | Số `executeAsync` không bằng số RPC server khi có retry. |
| **Hint service trên R1/R2** | Hints created, pending, dispatched, failed, oldest age, delivery duration theo metric version. | `statushandoff` hoặc một backlog bằng 0 không chứng minh mọi mutation đã được hinted. |
| **Replica R3** | Hint receive/replay, SSTable writes, compaction/flush, disk free, CPU/GC. | R3 `UN` không chứng minh có cùng bytes/cells với R1/R2. |
| **Repair** | Ranges/jobs scheduled/completed/failed, streaming bytes, preview/validate result, participant scope. | Repair một node/table không có nghĩa cả cluster/mọi table được so. |
| **Data/ledger** | Set expected ACKed IDs, values, deleted vs live, unknown outcomes. | `COUNT` giống nhau không chứng minh row IDs/values giống nhau. |

### 26.3. Lệnh vận hành thường dùng

~~~bash
# Trên node đã được kiểm tra quyền, theo runbook:
nodetool status
nodetool info
nodetool tpstats
nodetool netstats
nodetool compactionstats
nodetool gcstats
nodetool proxyhistograms
nodetool tablestats fault_lab.events_by_device_day
nodetool statushandoff
nodetool getmaxhintwindow
~~~

- `status`: node/rack/DC/membership, không phải bằng chứng data convergence.
- `netstats`: trạng thái streams/network operations theo version, hữu ích khi repair/streaming.
- `tpstats`: pending/completed/dropped tasks, dấu hiệu queue; không phải “đọc ra đúng cell nào”.
- `compactionstats`: pressure I/O do compaction, cần so disk latency/GC.
- `proxyhistograms`: latency phân phối request trên node, không bao gồm mọi xử lý Java/HTTP.
- `tablestats`: thống kê table, SSTables, tombstones và dữ liệu local theo version, **không so từng cell giữa replicas**.
- `getmaxhintwindow`: chỉ khả dụng với version hỗ trợ (4.0+); một số settings thay tên giữa các release.

**CQL role không cấp quyền `nodetool`**: nodetool dùng JMX/OS/security controls riêng. Không đưa password JMX vào shell history/log, không mở JMX port công khai để chạy thí nghiệm.

### 26.4. CQL tracing dùng có chọn lọc

~~~sql
-- Lệnh cqlsh trên lab; không bật tracing toàn production traffic.
CONSISTENCY LOCAL_QUORUM;
TRACING ON;

SELECT event_time,event_id,event_type
FROM fault_lab.events_by_device_day
WHERE device_id='device-fault-7'
  AND event_day='2026-11-21'
LIMIT 100;

TRACING OFF;
~~~

Trace có thể cho biết coordinator và hoạt động đọc replica của statement mẫu, nhưng **không thay** metrics hint replay, repair ranges, disk GC hay ledger comparison. Hạn chế tracing ở mức samples khi hệ đang bị tải.

## 27. Runbook khi replica quay lại nhưng dữ liệu chưa hội tụ

### 27.1. Triệu chứng và chẩn đoán đầu tiên

| Triệu chứng | Giả thuyết hợp lý | Kiểm chứng trước khi hành động |
| --- | --- | --- |
| R3 `UN`, ứng dụng đọc `LOCAL_ONE` đôi lúc thấy giá trị cũ. | Một replica còn lag hoặc coordinator chọn đường đọc khác. | Query/CL/coordinator/range, hint/repair logs; không coi `UN` đủ. |
| R3 trở lại, pending hints không giảm. | Delivery throttle, network, disk, node quá tải, paused/disabled handoff. | `statushandoff`, hint metrics, logs, disk free/GC, DC exclusions. |
| Hints queue rỗng nhưng repair preview báo khác biệt. | Missed mutations không có hints, hints mất/hết window, sai token ranges. | Effective hint config, outage duration, preview scope/participants. |
| `LOCAL_QUORUM` fails khi R3 down. | R1/R2 không đủ khỏe/CL/DC sai hoặc coordinator routing thất bại. | `nodetool status`, driver errors, CL, CPU/GC/disk/network. |
| Read `LOCAL_QUORUM` đúng nhưng data checker “R3 stale”. | Quorum có thể dùng R1/R2; replica-specific checker có thể đo state khác. | Đảm bảo phương pháp checker thực sự đọc storage R3; preview/full repair. |
| Repair kéo dài, streaming tăng, p99 xấu. | Network/disk/compaction contention, quá nhiều concurrent ranges/jobs. | `netstats`, repair logs, disk await, GC, load plan và throttles. |
| Delete xuất hiện lại sau outage rất dài. | Tombstone không còn đủ để suppress stale replica (zombie risk). | gc grace, repair history, compaction, backup, CQL timestamps. |
| Client insert timeout rồi count tăng bất thường. | Retry sinh UUID/timestamp mới hoặc double enqueue. | Stable primary key, ledger operation IDs, driver retry policy. |
| Multi-DC data khác nhau sau local-only repair. | Repair scope không bao phủ cross-DC differences. | DC participants và topology strategy trong repair plan. |

### 27.2. Thứ tự xử lý khi đang có sự cố thật

1. **Đánh giá độ an toàn:** có bao nhiêu full replicas khỏe trong từng DC, disk/network/GC, khách hàng bị ảnh hưởng, có nguy cơ lỗi thứ hai không?
2. **Ngừng fault injection hoặc maintenance đang gây ra lỗi**; không tiếp tục chạy tải để “thử cho chắc” khi cluster đang degraded.
3. **Giảm tải có chọn lọc** từ backfill/analytics jobs, không drop event bắt buộc lưu nếu pipeline cần durable ack/queue.
4. **Phục hồi node/đường mạng bằng đúng runbook**, không tự xóa data dir hoặc đổi host ID/token không kiểm soát.
5. **Quan sát hints và resource pressure** trên cả coordinators/target; xác định window/disabled DC/delivery errors.
6. **Phân loại unknown writes** trong client ledger; không retry với event IDs mới khi outcome chưa rõ.
7. **Đánh giá anti-entropy repair cần thiết:** keyspace/table/ranges/DC, preview/validate phù hợp, replication health, disk headroom và gc grace.
8. **Chạy repair theo lịch/tốc độ được phê duyệt**, không kích hoạt trùng job/full repair đồng loạt trên toàn cluster.
9. **Xác minh hậu điều kiện**: membership, ACKed IDs/values, hint/repair evidence, p99/errors/GC/disk trở lại SLO.
10. **Kết thúc incident** sau khi tài liệu hóa coverage/known gaps, hành động phòng ngừa và khách hàng impacted (nếu có).

### 27.3. Nếu đã vượt `gc_grace_seconds`

Không đơn giản chạy `repair --full` rồi tuyên bố hết nguy cơ zombie. Cần kiểm tra **tombstone retention, last successful repair coverage, tình trạng replica cũ, cơ chế backup/restore và dữ liệu từng bị hard delete**. Có thể phải làm kế hoạch **rebuild/restore/reconciliation với nguồn chân lý ngoài cluster**. Đây là tình huống cần DBA/SRE đánh giá kỹ và phê duyệt, không áp dụng “một lệnh cứu toàn bộ”.

## 28. Ma trận fault/load test theo mục tiêu chứng minh

### 28.1. Không fault và một fault

| Test ID | Fixture/fault | Assertions đúng | Không được tự suy |
| --- | --- | --- | --- |
| F01 | RF3, cả ba `UN`, `LOCAL_QUORUM`. | Baseline ACKed ledger = bounded reads, p99/throughput được ghi. | Có khả năng chịu mọi loại fault. |
| F02 | Dừng R3, đợi peers đánh dấu down. | Node status và fault marker trùng nhau; quorum writes có thể thành công. | Ngay lập tức mọi request đều không lỗi. |
| F03 | Ghi 100 IDs ổn định trong outage. | ACK/fail/unknown ledger đầy đủ; `LOCAL_QUORUM` successes được đọc lại. | `100/100` đều đã nằm trên R3. |
| F04 | Khởi động lại đúng R3 volume. | R3 `UN`, host ID/token đúng; không bị bootstrap nhầm. | Hints đã phát hết. |
| F05 | Handoff enabled + outage ngắn. | Hints metrics/lag, bounded drain wait, post-check result. | Mọi table/range đã repaired. |
| F06 | Handoff disabled trên coordinators khi R3 down. | Quorum ACK vẫn có thể; R3 không có mọi missed writes chỉ vì được up. | Bật lại handoff sẽ tạo lại hints không tồn tại. |
| F07 | Hint window ngắn rồi write ngoài window. | Phân biệt event trước/sau window, metrics/handoff coverage. | Toàn bộ events sẽ được hinted. |
| F08 | R3 khỏe, chạy full preview. | Nhìn estimated differences và participants/scope; chưa stream. | Preview đã sửa dữ liệu. |
| F09 | Full repair `--partitioner-range` qua tất cả nodes. | Job completed/ranges covered/streaming/verification. | Những table không chọn cũng được repaired. |
| F10 | Post-repair query theo ledger. | Các expected ACKed IDs/values còn sống được xác minh. | Mọi unknown write chắc chắn thất bại/thành công. |

### 28.2. Cases cần môi trường chuyên biệt

| Test ID | Fault | Điều phải chú ý |
| --- | --- | --- |
| F11 | Hai full replicas down, RF3. | `LOCAL_QUORUM` không đủ replicas; không downgrade để che lỗi. |
| F12 | Coordinator mất connection sau gửi write. | Outcome unknown, stable key, idempotent retry/reconciliation. |
| F13 | R3 down khi DELETE/TTL. | Tombstone propagation và gc grace; test tách fixture. |
| F14 | R3 down dài gần/vượt gc grace. | **Chỉ ở lab dài hạn** và có chuyên gia; cần risk/restore plan, không ép compaction xóa tombstone prod. |
| F15 | Network partition giữa dc1 và dc2. | Cross-DC hint/repair/CL semantics; WAN latency. |
| F16 | Handoff quá lớn, recovery R3 bão hòa disk. | Bounded replay/traffic, p99/GC, abort/slowdown criteria. |
| F17 | Hints mất do coordinator disk loss. | Anti-entropy restore, không nhầm với target restart ngắn. |
| F18 | Repair job fail giữa các token ranges. | Theo dõi coverage và retry từng range, không công bố complete. |
| F19 | Node replacement thay vì return same node. | Bootstrap/streaming/host ID khác, cần runbook riêng. |
| F20 | Repeated fault injection nhiều lần. | Kiểm no hidden hints backlog, health/p99 post-run và resource leaks. |

### 28.3. Tiêu chí pass/fail có thể công bố

**Pass phần availability** khi số request thành công/thất bại trong một-fault case phù hợp RF/CL và **threshold đã chốt**, không có mất control session/overload ngoài phạm vi. **Pass phần correctness** khi các writes đã ACK trong fixture, ngoại trừ dữ liệu cố ý xóa/hết TTL, được đối chiếu đúng ID/value; unknown writes được báo riêng. **Pass phần recovery** khi các job hint/repair có evidence completed với đúng token/table/DC scope, performance trở về baseline theo ngưỡng và không còn mismatch được quan sát trong phạm vi kiểm chứng.

**Không pass** chỉ vì một lần `SELECT LOCAL_QUORUM` trả 200 hoặc `nodetool status` có ba dòng `UN`.

## 29. Phản mẫu phổ biến khi thử mất một replica

| Phản mẫu | Vì sao sai | Thay bằng |
| --- | --- | --- |
| RF3 trên một node rồi stop container. | Không có hai replicas thật để thỏa quorum. | Ba full replicas test với NTS/DC đúng. |
| Dừng node không thuộc natural replica set. | Không tạo missed mutation cho partition test. | Xác minh token placement trước fault. |
| Chỉ test `LOCAL_ONE` rồi tuyên bố `LOCAL_QUORUM` pass. | CL khác availability/correctness contract. | Test đúng CL sản phẩm. |
| Node `UN` = dữ liệu đồng bộ. | Membership không đo per-range data equality. | Handoff/repair validation + ledger. |
| Hints = backup vĩnh viễn. | Hints best-effort, window/storage/failure giới hạn. | Repair cadence + backup/reconciliation. |
| Đợi hết 3 giờ để “đến lúc repair” trên production. | Outage chủ động làm mất fault tolerance và có rủi ro lớn. | Short-window setup trong lab, runbook approved. |
| `truncatehints` để giảm disk khi có backlog lớn. | Mất mutations pending, tăng divergence. | Điều chỉnh tải/replay, repair plan, không xóa mù. |
| Tăng hint throttle vô hạn. | Target disk/GC/network có thể bão hòa. | Benchmark/throttle có SLO và safety margins. |
| Một `SELECT QUORUM` chứng minh R3 đã có dữ liệu. | Có thể đọc từ hai replicas khỏe. | Per-replica scope/repair evidence. |
| Pin coordinator R3 = đọc storage chỉ từ R3. | Coordinator có thể gửi read tới replica khác. | Thiết kế replica isolation/validation đúng. |
| Chạy full repair song song trên mọi node. | Work duplication và I/O/CPU/network contention. | Lịch primary ranges/subranges, concurrency có kiểm soát. |
| Bật lại hints sau khi đã disable rồi coi missed writes được replay. | Hints không tồn tại không tự được tạo lại. | Anti-entropy repair và verify. |
| `--in-local-dc` đầy đủ cho mọi multi-DC divergence. | Có thể không bao phủ replica ở DC khác. | Cross-DC repair topology plan. |
| Dùng raw count để chứng minh đúng hàng. | Thiếu ID này, thêm ID khác vẫn giữ nguyên count. | Ledger full PK IDs + value digest. |
| Timeout = chưa mutation nào được ghi. | Replica có thể đã apply trước lỗi. | Unknown outcome handling, stable keys. |
| Retry tạo UUID mới. | Tạo duplicate logical events. | Reuse full primary key và idempotency contract. |
| Hạ CL sang `ANY` để mọi write đều trả 200. | Đổi durability/read visibility contract. | Giữ CL được duyệt, trả overload/unavailable rõ. |
| Giảm `gc_grace_seconds` để dọn tombstone nhanh. | Zombie data risk khi replicas chưa repair. | Retention/repair cadence đúng. |
| Chạy `COUNT(*)` toàn keyspace để verify dưới load. | Scan dữ liệu lớn, tăng tải lên chính cluster test. | Bounded queries/ledger/tokens. |
| Không restore handoff/không cleanup fault khi test fail. | Cluster test còn degraded, kết quả test sau nhiễu. | `finally`/teardown/alert và verified restoration. |

## 30. Bài tập thực hành có đáp án

**Bài 1.** RF=3 trong một DC, client dùng `LOCAL_QUORUM`. R3 down, R1/R2 đều khỏe. Có thể ghi thành công không, và cần bao nhiêu ACK?

**Đáp án:** **Có thể**, khi có **hai ACK full replicas** ở local DC. Điều này không chứng minh R3 đã nhận mutation; hinted handoff/repair có thể cần để R3 bắt kịp.

**Bài 2.** Vì sao coordinator không nhất thiết là một trong những natural replicas của key?

**Đáp án:** Coordinator là node **nhận yêu cầu CQL** và điều phối; natural replica được chọn từ **token của partition key + replication strategy/topology**. Driver load balancing có thể chọn coordinator không sở hữu key và coordinator định tuyến tới replicas.

**Bài 3.** Node R3 khởi động lại và hiển thị `UN`. Có thể tuyên bố dữ liệu đã hội tụ không?

**Đáp án:** **Không.** `UN` chứng minh membership/availability, không chứng minh hints đã giao đủ, repair đã so tất cả ranges hay các ID/values đều giống nhau.

**Bài 4.** Một `SELECT LOCAL_QUORUM` trả đủ 100 event IDs sau outage. Đã chứng minh R3 giữ đủ 100 IDs chưa?

**Đáp án:** **Chưa.** Quorum read có thể dùng R1/R2. Cần hint/repair validation và **phương pháp xác minh replica đúng scope** nếu khẳng định storage R3 đã bắt kịp.

**Bài 5.** Hinted handoff khác anti-entropy repair về cách biết dữ liệu nào bị thiếu?

**Đáp án:** Hint dựa trên mutation mà coordinator biết **không gửi được tới replica đích** trong điều kiện cho phép, lưu tạm rồi replay. Repair so **datasets của replica có cùng token ranges** qua Merkle trees/streaming, không phụ thuộc việc một hint từng được tạo.

**Bài 6.** Outage dài hơn `max_hint_window`. Mọi hint cũ bị xóa đúng thời điểm đó phải không?

**Đáp án:** **Không.** Window thường giới hạn **thời gian tiếp tục tạo hints mới** cho một endpoint đã down, không phải lời hứa mọi hint cũ bị xóa ngay tại mốc đó. Cần kiểm effective config và hint delivery state.

**Bài 7.** Khi R3 down, một phần hints được lưu ở R1, phần khác ở R2. Chỉ kiểm backlog R1 bằng 0 có đủ không?

**Đáp án:** **Không.** Phải xem **mọi coordinators có thể giữ hints**, metrics delivery/failure và repair coverage; backlog 0 cũng không chứng minh các mutation chưa từng được hinted đã hội tụ.

**Bài 8.** Tại sao `disablehandoff` trên cả R1/R2 trước outage giúp chứng minh cần repair?

**Đáp án:** Khi R3 down, writes vẫn có thể đạt `LOCAL_QUORUM` với R1/R2 nhưng **không có hints được lưu** cho missed writes. Bật lại handoff khi R3 lên **không tự tái tạo hints cũ**, nên anti-entropy repair là đường đối soát thiếu hụt.

**Bài 9.** Dùng `nodetool truncatehints` để giải quyết disk gần đầy trong production có an toàn không?

**Đáp án:** **Không.** Lệnh có thể làm mất toàn bộ hints chưa giao và tăng sai lệch. Cần giảm tải/điều tiết replay, kiểm disk headroom và lập repair plan được phê duyệt; không xóa hints tùy tiện.

**Bài 10.** Khi hai full replicas down trong RF3, `LOCAL_QUORUM` write còn khả năng đủ quorum không?

**Đáp án:** **Không.** Chỉ còn một full replica không đạt quorum 2/3. Driver có thể báo `Unavailable` hoặc timeout tùy failure detection/network, không nên downgrade CL âm thầm để trả 200.

**Bài 11.** `LOCAL_ONE` đôi lúc đọc stale sau khi R3 quay lại. Có nhất thiết là bug Driver Java không?

**Đáp án:** **Không.** `LOCAL_ONE` chỉ cần một replica. Nếu chọn replica chưa nhận missed write, có thể thấy state cũ. Xem CL, replica divergence, hints, repair và routing trước khi kết luận.

**Bài 12.** Vì sao ép Java statement coordinator tới R3 bằng `setNode(R3)` chưa đủ để chứng minh đang đọc dữ liệu trên chính R3?

**Đáp án:** Coordinator nhận request vẫn có thể gửi read tới các natural replicas theo CL/read path. Muốn xác minh storage node cụ thể, cần phương pháp test **thực sự kiểm soát/quan sát replica được hỏi** hoặc anti-entropy validation, không chỉ contact point/coordinator pinning.

**Bài 13.** Lệnh `nodetool repair --preview` có stream sửa dữ liệu không?

**Đáp án:** **Không.** Preview so sánh/ước lượng dữ liệu cần stream, có chi phí xây Merkle trees nhưng **không thực hiện repair streaming**. Muốn sửa cần repair thật theo phạm vi đã định.

**Bài 14.** Tại sao một `nodetool repair --full` trên một node chưa chắc bao quát cả ring?

**Đáp án:** Lệnh repair những token ranges liên quan **node được gọi**, không tự điều phối mọi node của cluster. Để bao phủ toàn ring nên lập lịch token/primary ranges trên các nodes cần thiết hoặc dùng orchestrator có coverage tracking.

**Bài 15.** Khi chạy `nodetool repair --full --partitioner-range` trên từng node theo lịch, ích lợi của `--partitioner-range`?

**Đáp án:** Giới hạn **primary token ranges** của node để giảm công việc trùng; chạy qua các nodes/ranges cần thiết để có coverage, không tự chạy mọi node đồng thời. Cần theo dõi failed ranges/retry và version-specific behavior.

**Bài 16.** Incremental repair mặc định và full repair khác nhau thế nào?

**Đáp án:** Incremental theo **unrepaired data** kể từ những đợt repair tương ứng, tiết kiệm I/O nếu chạy đều; full so cả dữ liệu trong token ranges được giao. Khi nghi ngờ stale/corruption lâu ngày, chỉ incremental có thể không đủ; cần full theo policy.

**Bài 17.** Tại sao không tăng hint delivery throttle vô hạn khi R3 trở lại?

**Đáp án:** Hints replay tranh disk, CPU, GC, network với reads/writes, compaction và repair. Tăng quá mức có thể làm p99/timeout xấu hơn; cần theo dõi target headroom và SLO, điều chỉnh có stop criteria.

**Bài 18.** Một client ghi sự kiện với UUID mới ở mỗi lần retry sau `WriteTimeout`. Điều gì có thể sai trong ledger?

**Đáp án:** Một attempt cũ có thể đã áp dụng trên replica; retry dùng **full primary key mới** tạo event logic trùng. Giữ stable `eventId,eventTime,partition` và phân loại timeout là **unknown** trước reconciliation.

**Bài 19.** `COUNT(*)` của partition là 100 trước outage, 100 sau repair. Có đủ xác minh correctness?

**Đáp án:** **Chưa.** Có thể thiếu ID A nhưng thêm ID B hoặc payload đổi. So **full expected primary keys/operation IDs và value hashes**, có kiểm tra deletes/TTLs theo contract.

**Bài 20.** R3 bỏ lỡ DELETE, R1/R2 đã ghi tombstone. Nếu R3 down lâu hơn grace và tombstone được thu hồi trước repair, rủi ro gì?

**Đáp án:** **Zombie data**: replica cũ có live row mà những replica còn lại không còn tombstone đủ để chặn, dữ liệu đã xóa có thể tái xuất hiện. Sắp lịch repair trước gc grace và có restore/reconciliation plan khi quá hạn.

**Bài 21.** `LOCAL_QUORUM` từ dc1 với `dc1:3,dc2:3` cần bao nhiêu ACK ở dc2?

**Đáp án:** **Không bắt buộc ACK từ dc2** để đạt local quorum ở dc1; cần hai full replica ACK của dc1. Remote DC có thể lag, nên cần multi-DC hint/repair plan và không nhầm `LOCAL_QUORUM` với `EACH_QUORUM`.

**Bài 22.** Nên dùng `nodetool repair --in-local-dc` ở mỗi DC và tự tin mọi khác biệt xuyên DC đã sửa chưa?

**Đáp án:** **Không mặc định.** Tùy repair scope/participants, local-only repair có thể bỏ khác biệt giữa DC. Phải lập kế hoạch cross-DC repair với băng thông/WAN/CL và coverage đúng.

**Bài 23.** Lúc R3 down, `LOCAL_QUORUM` write ACK 90/100 requests, 10 request timeout. Có thể nói chắc chắn 10 event không được ghi?

**Đáp án:** **Không.** Timeout không cho biết mutation chưa tới replica nào; có thể một/số write đã áp dụng. Ledger đánh dấu **unknown** và đối soát bằng stable keys. Không coi chúng là ACKed hay definitely failed tùy tiện.

**Bài 24.** Vì sao chạy closed-loop load tester có thể làm outage nhìn “ít ảnh hưởng”?

**Đáp án:** Khi latency tăng, closed-loop clients tự gửi ít request hơn, làm offered load giảm và có thể che queue saturation. Báo **offered vs achieved throughput, p99, rejected/timeouts** và cân nhắc open-loop có budget, tránh coordinated omission.

**Bài 25.** Tại `500 requests/s`, mean latency tăng từ `40 ms` lên `200 ms`. Theo Little's Law trong trạng thái ổn định, in-flight trung bình tăng từ bao nhiêu lên bao nhiêu?

**Đáp án:** `L=λW`: từ `500×0.040=20` lên `500×0.200=100` requests. Đây là xấp xỉ ở steady state, không dùng p99 thay mean hoặc giả định hệ đã quá tải vẫn ổn định.

**Bài 26.** Một node R3 đã `UN`, nhưng hints backlog không giảm và disk await của R3 cao. Bước kế nên làm gì?

**Đáp án:** Kiểm handoff enabled/paused, hint delivery errors/throttle, disk/GC/compaction, network và online load; **không** kết luận data converged từ `UN`, cũng không tăng throttle mù. Giảm tải có chọn lọc và lập repair plan nếu hints không đủ.

**Bài 27.** Vì sao stop R3 rồi xóa Docker volume trước start là một test khác?

**Đáp án:** Xóa volume làm mất local data, node identity/token có thể đổi và biến sự cố thành **replacement/bootstrap/data-loss recovery**, không phải “same replica returns and receives hints”. Phải có runbook riêng và backup/streaming validation.

**Bài 28.** Một team chạy fault test không đánh dấu mốc UTC và không lưu version/config. Vì sao khó so sánh hai lần thử?

**Đáp án:** Không thể correlate p99 với thời điểm down/up/handoff/repair hay biết setting/version nào thay đổi. Lưu **fault markers, Cassandra/driver versions, CL/RF, row bytes, rates và config hash**.

**Bài 29.** Có thể dùng hint replay như backup lâu dài thay vì repair định kỳ không?

**Đáp án:** **Không.** Hints best-effort, giới hạn window/storage/availability và có thể thiếu. Repair anti-entropy + backup/restore và lịch đúng so với gc grace là phần vận hành cần thiết.

**Bài 30.** Một test chỉ xác minh `nodetool status=UN` và HTTP response 200, vậy thiếu tối thiểu những loại bằng chứng nào?

**Đáp án:** Thiếu ledger **ACKed vs unknown**, so expected IDs/values theo query scope, hint/repair metrics với token/DC coverage, p95/p99/resource và chứng cứ cleanup/restore; do đó chưa chứng minh correctness/recovery.

## 31. Checklist bàn giao và sơ đồ quyết định

~~~text
CONTEXT / TEST CLUSTER
[ ] Cluster ID và environment được xác nhận là test/staging được phê duyệt.
[ ] Cassandra/JDK/Driver/config versions được pin, không dùng nguồn bí mật thật.
[ ] RF3 full replicas tại đúng dc1, có ba nodes thật và racks/token metadata.
[ ] Natural replica set của partition được kiểm chứng trước khi chọn R3.
[ ] Disk/RAM/network headroom, backup và rollback/cleanup đã diễn tập.

FIXTURE / CORRECTNESS
[ ] CQL schema dùng partition key + clustering keys đúng query workload.
[ ] Event IDs, event_time và full primary key ổn định giữa các retries.
[ ] Ledger phân loại ACKed/unknown/definitely failed + CL/timestamp.
[ ] Có baseline không fault, so IDs/values, không chỉ row count.
[ ] Fixture TTL/delete riêng và có quy tắc đối soát tombstone.

FAULT / AVAILABILITY
[ ] Fault start/end UTC rõ; một replica down và peers xác nhận DN.
[ ] Test LOCAL_QUORUM 2/3, không downgrade CL hoặc sửa data model giữa lượt.
[ ] Client load bounded, request throttle, deadline/retry budget.
[ ] Đo offered/achieved rate, success, timeout, unavailable, p95/p99.
[ ] Không quên coordinator routing/retry khi stop một Cassandra node.

HINT / REPAIR
[ ] hinted_handoff_enabled, disabled DCs và max_hint_window được xác minh.
[ ] Hints ở tất cả relevant coordinators được quan sát qua metrics/logs.
[ ] Node R3 được start lại với original volume/identity; không xóa hints.
[ ] Có outage ngắn (hints) và outage thiếu hints (repair) là hai case riêng.
[ ] Repair preview/full/incremental được phân biệt theo version/semantics.
[ ] Repair token ranges/tables/DC participants có coverage và completion logs.
[ ] Lịch repair/cadence giữ an toàn so với gc_grace_seconds.
[ ] Không chạy full repair mọi nodes đồng thời, không --force che endpoints down.

CONVERGENCE / OPERATIONS
[ ] Không kết luận hội tụ chỉ vì R3=UN hoặc quorum SELECT trả đủ rows.
[ ] Expected ACKed event IDs/values được đối chiếu tại scope bounded.
[ ] Có phương pháp chứng minh replica-specific khi claim per-replica equality.
[ ] Hints + repair + ledger + performance được xem chung timeline UTC.
[ ] R3 disk/GC/compaction và client p99 trở về giới hạn được duyệt.
[ ] Unknown writes được reconciliation, không sinh duplicate event IDs.
[ ] Multi-DC local vs cross-DC repair được kiểm chứng nếu có nhiều DCs.
[ ] Restore handoff settings và stop fault injection ngay cả khi test fail.
[ ] Hậu kiểm ghi known gaps, risk, duration, rollback và next actions.
~~~

~~~mermaid
flowchart TD
    A["Muốn thử replica R3 vắng mặt"] --> B["Chỉ trong cluster test có RF3 full replicas"]
    B --> C["Baseline: ledger + CL + p99/metrics"]
    C --> D["Dừng R3, chờ peers thấy down"]
    D --> E["Ghi bounded writes LOCAL_QUORUM, lưu ACK/unknown"]
    E --> F["R3 trở lại đúng volume, đợi UN"]
    F --> G{"Hints có đầy đủ và delivery thành công?"}
    G -->|Có vẻ đủ| H["Xác minh handoff metrics + query ledger"]
    G -->|Thiếu/hết window/disabled| I["Preview/plan anti-entropy repair"]
    H --> J{"Repair coverage/validation theo policy đạt?"}
    I --> K["Full/incremental repair đúng token/table/DC scope"]
    K --> J
    J -->|Chưa| L["Điều tra lag/disk/GC/tombstone, repair lại có kiểm soát"]
    L --> I
    J -->|Đạt| M["Kiểm ledger IDs/values + p99 + cleanup"]
    M --> N["Báo cáo đúng mức chứng cứ hội tụ"]
~~~

## 32. Nguồn tham khảo chính thức và kết luận

Tài liệu quan trọng cần đối chiếu với **Cassandra version và Java Driver version chính xác** trong cluster:

1. [Apache Cassandra — Hints](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/hints.html): hinted handoff, cửa sổ tạo hints, lưu trữ, delivery, settings, nodetool và hạn chế best-effort.
2. [Apache Cassandra — Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html): Merkle trees, full/incremental, repair frequency, `--partitioner-range`, `--preview`, `--validate`, phạm vi token.
3. [Apache Cassandra — nodetool repair](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/repair.html): cú pháp/tùy chọn theo version, DC/host/token scopes và repair warnings.
4. [Apache Cassandra — Consistency Guarantees](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html): kiến trúc Dynamo, replication, coordinator, consistency và eventual convergence.
5. [Apache Cassandra — Data replication](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html): token/ring/natural replicas và replication strategy.
6. [Apache Cassandra — Tombstones](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/index.html): compaction/tombstone retention và liên hệ repair; đối chiếu hướng dẫn grace theo bảng/version.
7. [Apache Cassandra Java Driver 4.18 — Paging and Async](https://apache.github.io/cassandra-java-driver/4.18.0/core/paging/): `CqlSession`, `CompletionStage`, paging và behavior driver client.
8. [Apache Cassandra — CQL](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): `INSERT`, `UPDATE`, `DELETE`, TTL và mutation/primary key semantics.

**Tổng kết:** Thử một replica Cassandra vắng mặt không dừng ở thao tác `stop` và kiểm tra `nodetool status`. Với **RF=3 và `LOCAL_QUORUM`**, coordinator có thể trả ACK khi **hai** full replicas khỏe nhận mutation, trong khi replica thứ ba bị missed writes. **Hinted handoff** có thể phát lại những mutation được ghi tạm trên coordinator khi replica trở lại, nhưng đó là **best-effort** với giới hạn window, disk và delivery; nó **không thay anti-entropy repair**. **Repair** so datasets theo token ranges bằng Merkle trees/streaming và cần lịch, coverage, resources và giám sát riêng để tránh sai lệch kéo dài/tombstone zombie. Một fault test có giá trị cần **operation IDs ổn định, ledger ACK/unknown, CL/topology đúng, stress bounded, fault markers UTC, đo hint backlog/repair coverage, kiểm ID/value và cleanup an toàn**. Chỉ tuyên bố hội tụ trong **đúng phạm vi đã có bằng chứng**; đừng dùng `UN`, một lần read quorum hoặc backlog bằng 0 làm kết luận thay dữ liệu thực.





