# Kiểm tra tiến độ hội tụ và dữ liệu còn thiếu

## Mục tiêu và bối cảnh

Apache Cassandra phân phối dữ liệu theo **partition key** và sao chép mỗi partition lên các replica theo **replication factor (RF)**. Khi node hoặc mạng gặp sự cố, một số replica có thể bỏ lỡ thao tác ghi, cập nhật hoặc xóa. Việc node hoạt động trở lại **không đồng nghĩa** dữ liệu đã giống nhau ngay lập tức. Người vận hành cần biết quá trình **hội tụ (convergence)** tiến triển tới đâu, bản ghi nào còn thiếu và phải sửa thế nào.

Đây là bài học của chương **Đồng bộ bản sao** trong module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Kiến thức sử dụng gồm mô hình wide-column, token/partition key, thiết kế bảng theo truy vấn, mức nhất quán đọc/ghi, replication, CQL, compaction, repair, xử lý lỗi và truy cập từ ứng dụng Java.

Sau bài này, bạn sẽ:

1. Phân biệt **cluster khỏe**, **đọc thấy dữ liệu** và **replica đã hội tụ**.
2. Hiểu phạm vi của **hinted handoff**, **read repair** và **anti-entropy repair**.
3. Thiết kế phép thử có dữ liệu **kỳ vọng độc lập** để phát hiện bản ghi còn thiếu.
4. Theo dõi tiến độ dựa trên log, metrics, trạng thái repair, số lỗi và kết quả truy vấn tại các consistency level.
5. Thực hành dừng một replica trong lab RF=3, ghi lúc node down, cho node trở lại, repair và đối chiếu.
6. Xây Java client ghi nhận ACK/UNKNOWN và kiểm chứng theo khóa mà không báo “đã đồng bộ” quá mức bằng chứng có được.

> **Môi trường:** các thao tác dừng node/repair trong bài chỉ dành cho **lab ba node được phép gây lỗi**. Không áp dụng trực tiếp lên cluster sản xuất khi chưa có kế hoạch vận hành, giám sát và khôi phục.

## 1. “Hội tụ” nghĩa là gì?

Một partition có thể có nhiều bản sao. Khi các replica nhận cập nhật không đồng thời, nội dung tạm thời khác nhau. **Hội tụ** nghĩa là các bản sao dần có đủ thông tin cần thiết để các phép đọc và quá trình hòa giải cho ra cùng dữ liệu logic theo quy tắc của Cassandra.

Giả sử ba node `R1`, `R2`, `R3` giữ partition của `run_id='sync-01'`:

| Thời điểm | R1 | R2 | R3 |
| --- | --- | --- | --- |
| T0: đã ghi `event A` ở `ALL` | A | A | A |
| T1: R3 ngừng hoạt động | A | A | A, nhưng node down |
| T2: ghi `event B` ở `LOCAL_QUORUM` | A, B | A, B | Chưa có B |
| T3: R3 khởi động | A, B | A, B | Có thể còn thiếu B |
| T4: đồng bộ hoàn tất | A, B | A, B | A, B |

**T3 không tự bằng T4.** `nodetool status` hiển thị `UN` (*Up/Normal*) cho R3 chỉ phản ánh membership/trạng thái node, chưa chứng minh R3 đã nhận `event B`.

~~~mermaid
flowchart LR
    A["Ghi vào partition"] --> B["Replica còn sống xác nhận"]
    B --> C["Replica mất kết nối bỏ lỡ ghi"]
    C --> D["Replica hoạt động lại"]
    D --> E["Hints / read repair / anti-entropy repair"]
    E --> F["Đối soát bản ghi kỳ vọng"]
    F --> G{"Dữ liệu đủ và phép đồng bộ hoàn tất?"}
    G -->|Có bằng chứng phù hợp| H["Đạt tiêu chí hội tụ"]
    G -->|Chưa| I["Điều tra missing / lag / lỗi"]
~~~

### Ba loại bằng chứng thường bị nhầm

| Bằng chứng | Điều có thể kết luận | Điều **chưa** thể kết luận |
| --- | --- | --- |
| Node `UN` trong `nodetool status` | Node tham gia cluster và đang hoạt động | Dữ liệu local của nó đã đủ, repair đã hoàn tất |
| `SELECT` trả đúng dữ liệu tại `LOCAL_QUORUM` | Truy vấn đủ replica để trả giá trị theo CL đã chọn | Mọi replica đều chứa giá trị; mọi khóa khác cũng đúng |
| Repair hoàn tất không lỗi, phạm vi phù hợp | Các replica/range thuộc phiên repair đã được đối chiếu theo cơ chế repair | Toàn bộ pipeline nghiệp vụ không thiếu sự kiện hoặc dữ liệu ngoài phạm vi repair cũng đủ |

**Đọc từ địa chỉ R3 không ép Cassandra chỉ dùng dữ liệu local của R3.** R3 có thể đóng vai coordinator và đọc các replica khác. Vì thế một truy vấn `cqlsh` hướng tới R3 thành công không chứng minh riêng SSTable của R3 đã có đủ dữ liệu.

## 2. RF, consistency level và giới hạn suy luận

Xét lab có **một datacenter**, `RF=3` và mỗi partition có ba replica. Với write consistency `LOCAL_QUORUM`, coordinator cần **hai xác nhận** từ các replica trong DC local. Khi một node down, hai node còn lại có thể ACK nếu cả hai đều đáp ứng.

| CL | RF=3, một DC | Ý nghĩa cho phép thử |
| --- | --- | --- |
| `ONE` / `LOCAL_ONE` | Cần một replica xác nhận | Có thể thành công dù bản sao khác chưa có mutation |
| `LOCAL_QUORUM` | Cần hai replica trong DC local | Nếu ghi thành công, có ít nhất hai replica đã xác nhận |
| `ALL` | Cần cả ba replica | Không thể thành công khi một replica không thể phản hồi |

Trong trường hợp một DC/RF3, `W=2` và `R=2` có `W+R=4>3`, nên hai tập quorum phải giao nhau. Điều này giúp đọc ở quorum có thể thấy các ghi đã ACK tại quorum, nhưng **không có nghĩa một lần đọc ở quorum chứng minh mọi replica đã được sửa**.

Các giới hạn phải nhớ:

- Truy vấn ở `LOCAL_ONE` có thể đọc từ replica còn cũ; điều đó không tự xác định chính xác replica nào có dữ liệu thiếu.
- Truy vấn `ALL` khi một node down có thể báo `Unavailable`; **lỗi truy vấn không phải bằng chứng dữ liệu đã mất**.
- `ALL` đọc thành công sau khi ba node lên có thể hòa giải nội dung của nhiều replica; đó không phải bản dump độc lập của từng replica.
- Với **nhiều datacenter**, `LOCAL_QUORUM` chỉ áp dụng quorum trong DC local. Cần kiểm tra replication của từng DC và dùng consistency phù hợp khi mục tiêu là hội tụ toàn cluster.
- Với ghi cạnh tranh trên cùng một khóa, Cassandra hòa giải theo timestamp/tombstone; quorum không tự cung cấp giao dịch cập nhật có điều kiện. Khi cần chống lost update, dùng mô hình LWT/`IF` phù hợp.
- Nếu client gặp timeout, mutation vẫn có thể tồn tại trên một số replica. Hãy phân biệt **được ACK**, **kết quả chưa rõ** và **chưa từng gửi**, tránh đánh đồng.

## 3. Ba cơ chế đưa replica gần nhau

### 3.1. Hinted handoff: bù ghi sau outage ngắn

Khi replica không nhận được mutation, một node còn sống có thể lưu **hint** và phát lại sau khi replica trở lại, tùy cấu hình, tài nguyên và khoảng thời gian lưu hint. Hints giúp giảm thời gian replica thiếu dữ liệu trong một số tình huống downtime.

**Không coi hinted handoff là cơ chế sửa mọi thiếu hụt**:

- Hints có thể hết hạn, bị vô hiệu hóa, hết dung lượng hoặc không bao phủ toàn bộ khoảng thời gian node ngừng hoạt động.
- Queue hints rỗng chỉ chứng tỏ không còn hints đang chờ trong phạm vi quan sát, **không chứng minh** mọi replica giống nhau.
- Hints không thay thế kế hoạch anti-entropy repair định kỳ.

### 3.2. Read repair: sửa một phần dữ liệu phát hiện khi đọc

Đường đọc có thể phát hiện khác biệt giữa các replica tham gia và, theo phiên bản/cấu hình, thực hiện sửa chữa trong phạm vi dữ liệu được đọc. Tuy nhiên, một lần `SELECT` một partition không có tác dụng quét và đối chiếu toàn bộ token range.

Không thiết kế quy trình khôi phục dựa trên giả định “đọc qua tất cả khóa sẽ tự repair hoàn toàn”. Tải đọc, tùy chọn `read_repair`, phiên bản Cassandra và các replica được chọn quyết định việc gì có thể xảy ra. Cần dùng repair được quản lý khi mục tiêu là đồng bộ có hệ thống.

### 3.3. Anti-entropy repair: đối chiếu phạm vi replica

`nodetool repair` khởi chạy quá trình đối chiếu theo token range giữa replica, trao đổi dữ liệu/khác biệt cần thiết. Nó có thể sử dụng Merkle trees và streaming; triển khai cụ thể khác theo phiên bản, hình thức repair và topology.

Repair có hai khía cạnh không được trộn:

1. **Hoàn tất công việc:** phiên repair báo thành công, có phạm vi keyspace/table/token range xác định, không có lỗi chưa xử lý.
2. **Chứng minh dữ liệu nghiệp vụ đủ:** mọi sự kiện/khóa mà ứng dụng đã ACK hoặc nguồn sự thật đã phát sinh đều có mặt. Repair không thể tạo ra một sự kiện nếu nó **không tồn tại trên bất kỳ replica/nguồn nào còn tin cậy**.

Nếu dữ liệu đã bị xóa, tombstone phải còn tồn tại và được truyền an toàn. Replica nghỉ quá lâu so với `gc_grace_seconds` và tombstone đã bị purge có thể làm **dữ liệu zombie** xuất hiện trở lại; không giải quyết bằng cách repair mù quáng node stale.

| Cơ chế | Phạm vi chính | Theo dõi | Khi nào chưa đủ |
| --- | --- | --- | --- |
| Hints | Mutation đã được giữ để phát lại cho node vắng mặt | Hints pending, failed/delivered, logs theo node | Outage vượt thời hạn giữ hints, không phải mọi ghi đều có hint |
| Read repair | Khác biệt phát hiện trong đường đọc | Mismatch, read repair metrics/logs khi phiên bản cung cấp | Partition chưa được đọc, chỉ một phần replica tham gia |
| Anti-entropy repair | Token ranges/replica trong phiên sửa | Trạng thái session, range coverage, lỗi, streaming | Repair chưa bao phủ phạm vi, tombstone đã bị purge, sự kiện vắng ở tất cả replica |
| Đối soát nguồn nghiệp vụ | Các ID/sự kiện đáng lẽ phải có | Tập expected vs actual, checksum theo bucket | Nguồn kỳ vọng không đầy đủ hoặc không đáng tin |

## 4. Đặt tiêu chí hội tụ đo được

Trước khi tạo lỗi, cần xác định **thế nào là đã hoàn thành**, thay vì chỉ chờ mọi node hiển thị `UN`.

Ví dụ tiêu chí cho lab `replication_lab.sync_probe`:

1. Tất cả node liên quan ở `UN`, schema/keyspace/replication đúng.
2. Dữ liệu **đã nhận ACK** trong nhật ký client có marker/khóa kỳ vọng.
3. Hints và repair đã hoàn thành theo phạm vi lab, không còn lỗi đang chờ xử lý liên quan.
4. Truy vấn xác minh có giới hạn theo `run_id` và từng `event_id` trả về giá trị đúng tại consistency level đã định.
5. Không có thao tác ghi/xóa cạnh tranh hoặc TTL làm thay đổi dữ liệu trong thời gian đo.

**Kết luận đúng:** đã đạt các tiêu chí quan sát và đồng bộ đã định nghĩa cho **bảng, khóa, thời điểm, topology và CL cụ thể**. Để chứng minh chính xác toàn bộ nội dung vật lý của từng replica, cần thêm công cụ/kiểm tra ở cấp storage hoặc repair coverage chi tiết; chỉ một truy vấn CQL không đủ.

### Chỉ số tiến độ tham khảo

| Chỉ số | Cách diễn giải |
| --- | --- |
| Thời gian từ `node UN` đến `repair hoàn tất` | Độ trễ hoàn thành quy trình đồng bộ có kiểm soát |
| Hints queued/delivered/failed | Xu hướng phát lại mutation; phải đọc cả lỗi và giới hạn giữ hints |
| Repair sessions/ranges completed vs failed | Phần phạm vi được đối chiếu thành công, không chỉ tổng số request |
| Streaming bytes và thời gian | Lượng dữ liệu trao đổi để đồng bộ, tải mạng/đĩa |
| Read mismatch / read repair metrics | Dấu hiệu replica khác biệt, phụ thuộc bản Cassandra và cách đo |
| `expected_count`, `found_count`, `missing_count`, `mismatch_count` | Đối chiếu các khóa đã biết từ nguồn bên ngoài cluster |
| Disk I/O, compaction backlog, p95/p99 read/write | Chi phí đồng bộ và ảnh hưởng tới ứng dụng |

Một tỷ lệ ví dụ có thể tính là `found_count / expected_count` khi danh sách expected là **đầy đủ và đáng tin**. Nếu thiếu danh sách expected, không thể kết luận “không mất dữ liệu” chỉ vì `SELECT COUNT(*)` trả một số hay vì không còn hints pending. Đối soát toàn bảng lớn bằng `COUNT(*)` cũng có thể gây quét rộng và tải không cần thiết.

## 5. Chuẩn bị lab ba node và bộ dữ liệu kỳ vọng

### 5.1. Kiểm tra topology

Giả sử cluster lab có ba node `cass-1`, `cass-2`, `cass-3` cùng datacenter `datacenter1`; thay tên cho phù hợp môi trường thực tế.

~~~bash
# Chạy trong môi trường lab trên một node đang hoạt động.
nodetool status
~~~

Kỳ vọng ba node có trạng thái `UN` (*Up/Normal*), không đang bootstrap/decommission hoặc thực hiện bảo trì nặng. `cqlsh` kiểm tra phiên bản/DC của node kết nối:

~~~sql
SELECT release_version, data_center, host_id
FROM system.local;
~~~

Kiểm tra từng node khi cần, bởi `system.local` chỉ mô tả node trả lời. Nếu datacenter không mang tên `datacenter1`, sửa tên DC trong câu tạo keyspace. Cấu hình phần mềm/cluster và lệnh quản trị có thể khác giữa các phiên bản Cassandra.

### 5.2. Tạo keyspace RF=3 và bảng theo một partition thử nghiệm

~~~sql
CREATE KEYSPACE IF NOT EXISTS replication_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS replication_lab.sync_probe (
    run_id text,
    event_id uuid,
    marker text,
    source_version int,
    payload text,
    PRIMARY KEY ((run_id), event_id)
);
~~~

`run_id` là **partition key**; `event_id` là clustering key. Mỗi lần chạy lab phải có `run_id` **mới**. Dữ liệu kỳ vọng được định nghĩa bởi `event_id` và `marker` có giá trị ổn định để đối chiếu sau sự cố. `source_version` chỉ là metadata do ứng dụng gửi; nó **không tự bảo vệ chống cập nhật cạnh tranh**. Trong lab cơ bản, không cập nhật cùng khóa nhiều lần, không dùng counter, TTL hoặc xóa, để có thể kết luận rõ ràng.

Nếu keyspace/bảng đã tồn tại, `IF NOT EXISTS` không sửa cấu hình cũ. Xác minh RF và durable writes:

~~~sql
SELECT keyspace_name, replication, durable_writes
FROM system_schema.keyspaces
WHERE keyspace_name = 'replication_lab';
~~~

Xác định những node dự kiến giữ một partition bằng công cụ quản trị của phiên bản đang chạy. Trong topology lab RF=3 ba node, mỗi node sẽ là replica của partition thử. Trên cluster lớn, có thể dùng `nodetool getendpoints` theo **partition key** để liệt kê endpoints; kết quả chỉ phản ánh **placement**, không chứng minh endpoint đã chứa đủ dữ liệu.

### 5.3. Lưu bộ dữ liệu kỳ vọng bên ngoài Cassandra

Trước thí nghiệm, viết một biên bản phía client với ít nhất các trường:

| run_id | event_id | marker | Mục đích | ACK dự kiến |
| --- | --- | --- | --- | --- |
| `sync-demo-01` | `11111111-1111-4111-8111-111111111111` | `baseline-A` | Ghi khi mọi replica đang chạy | Ghi ở `ALL` |
| `sync-demo-01` | `22222222-2222-4222-8222-222222222222` | `during-outage-B` | Ghi khi node 3 down | Ghi ở `LOCAL_QUORUM` |
| `sync-demo-01` | `33333333-3333-4333-8333-333333333333` | `after-recovery-C` | Ghi sau khi node 3 trở lại | Ghi ở `LOCAL_QUORUM` |

Biên bản còn phải ghi **kết quả thực nhận** của mỗi INSERT. Nếu một lệnh timeout, đánh dấu `UNKNOWN`, không đưa nó vào tập “đã ACK” chỉ vì sau đó đọc thấy hàng. Để biết hệ thống đã tiếp nhận **đủ sự kiện nghiệp vụ**, cần đối soát với nguồn sự kiện đáng tin (event log/transactional source) chứ không chỉ tập các write thành công tại Cassandra.

## 6. Thí nghiệm A: tạo một replica thiếu dữ liệu

### Bước 1 — Ghi baseline khi cluster còn đủ node

Trong `cqlsh` kết nối một node sống:

~~~text
CONSISTENCY ALL
~~~

~~~sql
INSERT INTO replication_lab.sync_probe
    (run_id, event_id, marker, source_version, payload)
VALUES (
    'sync-demo-01',
    11111111-1111-4111-8111-111111111111,
    'baseline-A', 1, 'created-when-three-up'
);
~~~

Chỉ ghi vào biên bản **ACK_ALL** nếu client nhận thành công. `ALL` yêu cầu ba replica xác nhận mutation; nó không tạo snapshot logic cho các thao tác ghi đồng thời khác.

### Bước 2 — Dừng replica thứ ba

~~~bash
# Lệnh mẫu chỉ chạy trên lab Docker, thay đúng tên container.
docker kill --signal=KILL cass-3
~~~

Kết nối node `cass-1` hoặc `cass-2` để kiểm tra:

~~~bash
nodetool status
~~~

Hai node còn lại phải `UN`, `cass-3` xuống `DN` (*Down/Normal*). Chờ failure detection phản ánh trạng thái trước khi diễn giải kết quả; `SIGKILL` của tiến trình không mô phỏng đầy đủ sự cố mất nguồn vật lý hoặc mất dữ liệu trên ổ.

### Bước 3 — Ghi B khi chỉ còn hai replica

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
INSERT INTO replication_lab.sync_probe
    (run_id, event_id, marker, source_version, payload)
VALUES (
    'sync-demo-01',
    22222222-2222-4222-8222-222222222222,
    'during-outage-B', 1, 'written-while-cass-3-down'
);
~~~

Ở RF3 một DC, nếu cả hai node sống xác nhận, lệnh được ACK tại `LOCAL_QUORUM`. Vì `cass-3` đã down trước lệnh này, nó **chưa trực tiếp xử lý INSERT B**; điều này tạo tình huống thiếu dữ liệu tạm thời để quan sát khi node quay lại.

Đọc bằng quorum lúc `cass-3` còn down:

~~~sql
SELECT event_id, marker, source_version, payload
FROM replication_lab.sync_probe
WHERE run_id = 'sync-demo-01';
~~~

Nếu cả A và B đã ACK, dự kiến đọc thấy cả hai. Ở giai đoạn này **không nên dùng `CONSISTENCY ALL`** để chứng minh tính đầy đủ: một replica đang down nên ALL không thể hoàn thành bình thường.

### Bước 4 — Khởi động lại replica đã down

~~~bash
docker start cass-3
~~~

Kiểm tra `nodetool status` cho tới khi cả ba node `UN`. Có thể đọc lại A và B với `LOCAL_QUORUM`. Nếu vẫn thấy đủ, đó là kết quả của phép đọc tại quorum, **không phải bằng chứng B đã được sao chép vào node 3**.

### Bước 5 — Ghi C sau khi cả ba node lên

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
INSERT INTO replication_lab.sync_probe
    (run_id, event_id, marker, source_version, payload)
VALUES (
    'sync-demo-01',
    33333333-3333-4333-8333-333333333333,
    'after-recovery-C', 1, 'written-when-three-up'
);
~~~

Sau khi A/B/C được client xác nhận theo CL tương ứng, ta có bộ marker cần kiểm chứng. **Để quan sát quá trình bắt kịp của replica**, hãy ghi mốc thời gian node trở lại, hint delivery và repair, không chỉ dựa vào một `SELECT`.

## 7. Thí nghiệm B: quan sát hints, sửa khác biệt và xác minh

### 7.1. Quan sát tiến độ trước repair

Trên node phù hợp trong lab:

~~~bash
nodetool status
nodetool netstats
nodetool compactionstats
~~~

- `nodetool status` cho biết trạng thái node và topology, **không cho tỷ lệ phần trăm đồng bộ dữ liệu**.
- `nodetool netstats` hữu ích khi có streaming; **không phải một phép đếm đầy đủ mọi hint**.
- `nodetool compactionstats` cho thấy tải compaction, nhưng compaction không tự thay thế anti-entropy repair.
- Theo dõi log/JMX/metrics về hints đã giao, hints còn chờ, repair sessions và lỗi theo phiên bản thực tế. Không suy ra dữ liệu đầy đủ chỉ từ một chỉ số bằng 0.

Nếu hints đã phát lại thành công, B có thể đã đến R3 rất nhanh. Do đó **không nhất thiết quan sát được kết quả thiếu qua CQL ở `LOCAL_ONE`**. Trong Cassandra, việc kết nối tới R3 cũng không ép truy vấn lấy bản copy local; dữ liệu có thể được lấy hoặc hòa giải từ replica khác.

### 7.2. Chạy anti-entropy repair trong lab

Sau khi ba node đều khỏe và không có job bảo trì xung đột, thử:

~~~bash
# Chạy trên node phù hợp của lab; điều chỉnh theo phiên bản/topology.
nodetool repair -full replication_lab sync_probe
~~~

Lệnh có thể tốn CPU, disk I/O, network và thời gian. Phải ghi lại thời điểm bắt đầu/kết thúc, exit status, lỗi trong logs, các range và replica mà phiên repair bao phủ. Tùy phiên bản, `-full` yêu cầu full repair; trên cluster lớn, chạy một lệnh ở một node **không tự chứng minh** toàn bộ cluster/table trên mọi token range đã được repair. Cần quy trình bao phủ đúng toàn bộ phạm vi.

**Repair thành công có phạm vi là bằng chứng mạnh hơn “node UN”**, nhưng vẫn chưa kiểm chứng một sự kiện đã từng tồn tại hay chưa nếu tất cả bản sao đều thiếu nó.

### 7.3. Đọc kiểm chứng bằng khóa xác định

Trong `cqlsh`:

~~~text
CONSISTENCY ALL
~~~

~~~sql
SELECT event_id, marker, source_version, payload
FROM replication_lab.sync_probe
WHERE run_id = 'sync-demo-01';
~~~

Trên lab nhỏ, có thể so sánh kết quả với ba marker trong biên bản. Đọc ở `ALL` yêu cầu đủ replica để đáp ứng; **nếu trả lỗi vì node chưa sẵn sàng, đó là lỗi tính sẵn sàng/đọc chưa hoàn tất, không thể gán ngay là missing**.

**Kiểm chứng chi tiết từng khóa** khi phát hiện thiếu:

~~~sql
SELECT marker, source_version, payload
FROM replication_lab.sync_probe
WHERE run_id = 'sync-demo-01'
  AND event_id = 22222222-2222-4222-8222-222222222222;
~~~

Nếu đọc được `during-outage-B` sau repair, ghi nhận **FOUND_MATCH** ở CL đang dùng. Nếu không có hàng, ghi **MISSING_AT_SELECTED_CL**. Nếu có hàng nhưng marker khác, ghi **MISMATCH** và kiểm tra ghi đè/timestamp. Timeout hoặc `Unavailable` phải ghi **READ_ERROR**, **không** coi là “MISSING”.

Đọc ở `ALL` vẫn có thể hòa giải dữ liệu qua các replica; nó không cho ảnh chụp vật lý độc lập từng node. Nếu cần bằng chứng nghiêm ngặt về trạng thái **SSTable/memtable của từng replica**, phải dùng quy trình quản trị/chẩn đoán phù hợp phiên bản hoặc công cụ kiểm tra dữ liệu local chuyên biệt, kèm giám sát repair. Không diễn giải CQL thành phép kiểm chứng per-replica chắc chắn.

### 7.4. Biên bản tiến độ

| Mốc | Node | Hints/repair | Đọc tại CL | Kết quả | Kết luận |
| --- | --- | --- | --- | --- | --- |
| T0: trước lỗi | 3 `UN` | Chưa cần | `ALL` | A khớp | Baseline |
| T1: R3 down | 2 `UN`, 1 `DN` | Có thể giữ hints | `LOCAL_QUORUM` | A, B khớp | B đã có quorum ACK |
| T2: R3 lên | 3 `UN` | Hints có thể đang giao | `LOCAL_QUORUM` | A, B khớp | Chưa đủ chứng minh R3 đồng bộ |
| T3: repair xong | 3 `UN` | Phiên repair thành công | `ALL` | A, B, C khớp | Đạt tiêu chí hội tụ trong phạm vi kiểm chứng |

Không tự điền kết quả “khớp” nếu lab thực tế chưa đo. Mỗi hàng phải lưu **giá trị quan sát**, thời gian, CL, trạng thái lỗi và thông tin phiên repair. Nếu hết thời gian kiểm tra mà còn bất thường, báo **INCOMPLETE/UNKNOWN** kèm khóa/range chưa được xác minh.

## 8. Phát hiện bản ghi còn thiếu bằng nguồn kỳ vọng

Sự khác nhau giữa **convergence** và **completeness** đặc biệt quan trọng:

- **Replica convergence:** các replica có cùng thông tin logic trên phạm vi đã được sửa/kiểm chứng.
- **Business completeness:** tất cả sự kiện nghiệp vụ bắt buộc có mặt trong hệ thống lưu trữ.

Nếu một sự kiện `D` bị mất **trước khi bất kỳ replica nào chấp nhận** hoặc trước khi được ghi vào nguồn tin cậy, repair không thể tạo lại D. Các replica có thể hoàn toàn giống nhau nhưng **cùng thiếu D**.

Để xác định thiếu dữ liệu, cần một tập expected bên ngoài cluster (ví dụ log sự kiện có `event_id`, danh sách request đã được xác nhận, snapshot nguồn đáng tin hoặc outbox). Đối soát:

~~~text
expected = {A, B, C, D}
actual   = {A, B, C}
missing  = expected - actual = {D}
extra    = actual - expected = {}
~~~

Trên bảng Cassandra lớn, tránh `SELECT COUNT(*)` toàn tập hoặc quét mọi partition cho mỗi lần kiểm tra. Hãy dùng `event_id` ổn định, bucket theo `run_id`/thời gian và **truy vấn có partition key rõ ràng**. Khi số sự kiện rất lớn, có thể xuất checksum/count theo bucket từ pipeline tin cậy, sau đó kiểm tra chi tiết các bucket sai lệch. Checksum/count bằng nhau là tín hiệu tốt, nhưng **không phải chứng minh duy nhất** hai tập có mọi phần tử bằng nhau khi không có cơ chế kiểm chứng phù hợp.

| Dấu hiệu | Nguyên nhân khả dĩ | Bước tiếp theo |
| --- | --- | --- |
| Một marker từng ACK không còn thấy ở quorum | Sai keyspace/partition, xóa/TTL/ghi đè, node lỗi, dữ liệu chưa đồng bộ | Kiểm tra manifest và lịch sử mutation, CL/RF, logs và repair |
| Một marker chỉ thấy qua một số cách đọc | Replica lệch, routing và chọn CL khác nhau | Kiểm tra endpoints, traces/logs/metrics; repair đúng phạm vi |
| `nodetool status` đều `UN` nhưng hints pending lớn | Node đã lên nhưng phát lại mutation chưa xong | Theo dõi delivery, lỗi và thời hạn hints; cân nhắc repair |
| Repair báo hoàn thành nhưng còn thiếu event nguồn | Event chưa từng đến Cassandra, bị xóa hoặc nằm ngoài phạm vi repair | Đối soát nguồn/outbox, backfill có kiểm soát |
| Một hàng đã xóa xuất hiện lại | Tombstone stale, replica offline lâu, timestamp mới, restore sai | Điều tra `gc_grace_seconds`, repair history và nguồn ghi trước khi sửa |
| Đọc timeout trong lúc streaming/repair | Quá tải hoặc replica không đủ đáp ứng CL | Ghi READ_ERROR, giảm tải/khôi phục rồi thử lại; không đếm là missing |

## 9. Ghi và đối soát trong Java Driver 4.x

Ví dụ bên dưới dùng **Java Driver 4.x** và keyspace/bảng đã tạo. Phần ghi marker cố định và phần kiểm tra là hai thao tác riêng; chính **ACK từ lời gọi client** quyết định nhãn ghi đã xác nhận.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.util.UUID;

public final class ReplicaConvergenceProbe {
    private final CqlSession session;
    private final PreparedStatement insert;
    private final PreparedStatement read;

    public enum WriteResult { ACKNOWLEDGED, UNKNOWN }
    public enum CheckResult { FOUND_MATCH, MISSING, MISMATCH, READ_ERROR }

    public ReplicaConvergenceProbe(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO replication_lab.sync_probe " +
            "(run_id, event_id, marker, source_version, payload) " +
            "VALUES (?, ?, ?, ?, ?)");
        this.read = session.prepare(
            "SELECT marker, source_version, payload " +
            "FROM replication_lab.sync_probe " +
            "WHERE run_id = ? AND event_id = ?");
    }

    public WriteResult insertAtQuorum(
            String runId, UUID eventId, String marker, String payload) {
        BoundStatement statement = insert.bind(
                runId, eventId, marker, 1, payload)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotence(false);
        try {
            session.execute(statement);
            System.out.printf("WRITE_ACK run=%s event=%s%n", runId, eventId);
            return WriteResult.ACKNOWLEDGED;
        } catch (RuntimeException error) {
            System.err.printf("WRITE_UNKNOWN run=%s event=%s cause=%s%n",
                runId, eventId, error.getClass().getSimpleName());
            return WriteResult.UNKNOWN;
        }
    }

    public CheckResult checkAtAll(
            String runId, UUID eventId, String expectedMarker) {
        BoundStatement statement = read.bind(runId, eventId)
            .setConsistencyLevel(DefaultConsistencyLevel.ALL);
        try {
            Row row = session.execute(statement).one();
            if (row == null) {
                return CheckResult.MISSING;
            }
            return expectedMarker.equals(row.getString("marker"))
                ? CheckResult.FOUND_MATCH
                : CheckResult.MISMATCH;
        } catch (RuntimeException error) {
            System.err.printf("READ_ERROR run=%s event=%s cause=%s%n",
                runId, eventId, error.getClass().getSimpleName());
            return CheckResult.READ_ERROR;
        }
    }
}
~~~

Đoạn mã minh họa các nguyên tắc:

- `PreparedStatement` và `CqlSession` được tái sử dụng; tham số hóa giúp tránh ghép trực tiếp dữ liệu người dùng vào câu CQL.
- Dữ liệu `eventId/marker` phải **ổn định** giữa các lần ghi/kiểm tra; dùng một `runId` mới cho mỗi lượt lab.
- Với thao tác ghi không nhận ACK, kết quả là `UNKNOWN`, không phải “chắc chắn chưa ghi”; retry tùy tiện có thể ghi đè nếu dùng cùng khóa mà payload/timestamp khác.
- `ALL` chỉ thực hiện được khi đủ replica đang đáp ứng; `READ_ERROR` không bao giờ được tính vào `MISSING` khi tổng hợp số liệu.
- `FOUND_MATCH` nghĩa là hàng đọc tại `ALL` có marker đúng, **không tự chứng minh** storage local trên từng node giống nhau.
- Lớp gọi phải lưu **manifest các event kỳ vọng** bên ngoài bảng đang thử, cùng CL, thời điểm, ACK/UNKNOWN, thời điểm restart/repair và mã lỗi để so sánh được qua nhiều lần kiểm tra.

Trong hệ thống thật, các lỗi `Unavailable`, read timeout, write timeout, connection error và lỗi truy vấn/schema nên được phân loại chi tiết. Việc nuốt mọi ngoại lệ thành “mất dữ liệu” vừa sai ngữ nghĩa vừa gây retry không kiểm soát.

## 10. Vận hành hội tụ an toàn trong môi trường nhiều node

### Theo dõi xuyên thời gian

Một phép thử sau khi node phục hồi nên lấy nhiều mốc: khi node bắt đầu `UN`, khi hints giảm, khi streaming/repair chạy và khi đối soát ổn định. Ghi thêm latency của ứng dụng: streaming và compaction có thể làm p95/p99 tăng ngay cả khi dữ liệu đang tiến tới hội tụ.

### Đảm bảo repair thực sự bao phủ phạm vi

Trong cluster có nhiều token range và nhiều DC, phải lập lịch repair sao cho **mọi range và replica cần thiết** đều được đối chiếu với tần suất phù hợp. Full/incremental repair, kết quả session và trạng thái hoàn tất phụ thuộc phiên bản/tùy chọn; không đánh đồng “lệnh chạy thành công trên một node” với “toàn hệ thống được đồng bộ”.

### Chú ý TTL, tombstone và node offline lâu

Nếu bảng dùng TTL hoặc `DELETE`, **tombstone là thông tin cần truyền**, không chỉ các hàng còn sống. Với replica nghỉ quá lâu, đặc biệt vượt thời gian grace và tombstone có khả năng đã bị purge, cần đánh giá nguy cơ zombie trước khi đưa node stale trở lại. Một quy trình thay thế/rebuild từ replica khỏe hoặc khôi phục từ nguồn tin cậy có thể cần thiết; không xóa SSTable bằng tay.

### Không nhầm compaction với repair

Compaction hợp nhất SSTable **trên một node** và có thể thu hồi dữ liệu cũ/tombstone theo điều kiện; repair đối chiếu dữ liệu **giữa các replica**. Repair có thể sinh streaming và SSTable mới, kéo theo compaction, nhưng không vì thế mà hai công việc là một. Replication factor/consistency level quyết định placement và ACK, cũng **không tự bảo đảm hội tụ tức thời** sau downtime.

### Khi nào cần backfill thay vì chỉ repair?

Nếu đối soát phát hiện một `event_id` có ở nguồn nghiệp vụ nhưng **không có trên bất cứ replica nào**, phải tìm nguồn phục hồi: event log bền vững, outbox, backup hoặc hệ thống upstream. Backfill cần giữ ID ổn định và tránh ghi đè cập nhật mới hơn. Nếu yêu cầu idempotency hoặc chuyển trạng thái, sử dụng điều kiện ghi/LWT và thiết kế theo nhu cầu nghiệp vụ.

## 11. Bài thực hành và câu hỏi tự kiểm tra

**Bài 1 — Dự đoán trước khi thử.** Với RF=3 một DC, ghi A ở `ALL`, dừng R3 rồi ghi B ở `LOCAL_QUORUM`. Hãy chỉ rõ replica nào chắc chắn ACK B sau khi client báo thành công. Vì sao không thể kết luận B đã xuất hiện ở R3 ngay khi R3 chuyển sang `UN`?

**Bài 2 — Ghi biên bản tiến độ.** Thực hiện lab, lưu mốc `T_down`, `T_write_ack`, `T_up`, `T_hints_drained` (nếu metrics có), `T_repair_done` và `T_verified`. Thêm trường `UNKNOWN` khi write timeout. Giải thích vì sao số hints còn chờ bằng 0 chưa đủ làm tiêu chí hoàn thành.

**Bài 3 — Phân biệt read result với dữ liệu per-replica.** Kết nối `cqlsh` tới R3 và đọc B ở `ALL`. Kết quả trả đúng marker B. Điều nào đã được chứng minh? Điều nào **chưa** được chứng minh về SSTable/memtable của riêng R3?

**Bài 4 — Missing event.** Manifest nguồn gồm A, B, C, D nhưng Cassandra chỉ trả A, B, C. Repair chạy thành công trên phạm vi lab. Bạn cần làm gì để quyết định D chưa từng ghi, đang thiếu trên replica, đã hết TTL, hay nằm ngoài phạm vi truy vấn?

**Bài 5 — Sự kiện xóa và outage dài.** Một replica nghỉ lâu hơn `gc_grace_seconds`, có khả năng đã bỏ lỡ `DELETE` và tombstone ở replica khác đã bị purge. Vì sao chạy repair ngay không luôn an toàn? Phác thảo quy trình đánh giá, rebuild và đối soát.

**Bài 6 — Java và false positives.** Thay đổi đoạn mã để đếm `FOUND_MATCH`, `MISSING`, `MISMATCH` và `READ_ERROR` riêng biệt, giới hạn tổng request đồng thời. Vì sao gộp `READ_ERROR` vào `MISSING` khiến dashboard báo sai rằng cluster mất dữ liệu?

## Ghi nhớ

**Hội tụ replica là quá trình có thể quan sát và kiểm chứng theo phạm vi, không phải một trạng thái được bảo đảm chỉ vì các node đang `UN`.** Dùng RF/CL để hiểu ACK và đường đọc, theo dõi hints/repair/streaming, đối soát từng khóa đã biết với manifest ngoài cluster, và phân loại rõ kết quả đọc thiếu với lỗi đọc. Repair giúp đồng bộ thông tin **còn tồn tại trên replica**, còn việc xác minh không thiếu sự kiện nghiệp vụ đòi nguồn kỳ vọng và kế hoạch backfill khi cần.
