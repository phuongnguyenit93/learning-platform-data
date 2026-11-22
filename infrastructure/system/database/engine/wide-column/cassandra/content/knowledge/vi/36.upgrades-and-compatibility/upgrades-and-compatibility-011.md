# Kiểm chứng dữ liệu, truy vấn, độ trễ và lỗi trước/sau

## Mục tiêu và bối cảnh

Không thể xem một đợt nâng cấp Apache Cassandra là thành công chỉ vì mọi node đã chạy phiên bản mới và `nodetool status` hiển thị `UN` (*Up/Normal*). Các node có thể tham gia cluster bình thường nhưng **một số bản ghi không còn đọc đúng**, câu CQL của ứng dụng không còn tương thích, p99 latency tăng mạnh hoặc tỷ lệ timeout vượt ngưỡng vận hành.

Trong chương **Nâng cấp và tương thích** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`, bài này trình bày cách **kiểm chứng có thể lặp lại trước, trong và sau nâng cấp**. Các phép đo bao phủ bốn mặt:

1. **Dữ liệu:** bản ghi đã ACK có còn và có đúng giá trị ở consistency level cần thiết không?
2. **Truy vấn:** CQL, schema, prepared statement, paging, LWT và các thao tác đọc/ghi mà ứng dụng Java dùng có giữ ngữ nghĩa không?
3. **Độ trễ/tài nguyên:** p50/p95/p99, throughput, số trang đọc, disk I/O, CPU, compaction, repair và network có đáp ứng SLO không?
4. **Lỗi:** timeout, unavailable, read/write failure, protocol/driver incompatibility và các trạng thái **UNKNOWN_WRITE** có thay đổi sau nâng cấp không?

Bài liên hệ trực tiếp đến mô hình wide-column, partition key, thiết kế bảng theo truy vấn, replication theo DC, consistency level, CQL, compaction, repair, chẩn đoán lỗi và Cassandra Java Driver 4.x.

Sau khi học, bạn có thể thiết kế **baseline và tiêu chí PASS/FAIL trước khi thay đổi**, chạy cùng bộ kiểm thử tại các checkpoint rolling upgrade, đối chiếu dữ liệu theo manifest, lập báo cáo sai lệch có nguyên nhân và xác định khi nào cần **dừng rollout** thay vì tiếp tục nâng cấp bằng cảm tính.

> **Phạm vi an toàn:** lệnh CQL và ví dụ code hướng tới **lab/staging**. Không tự nâng cấp hoặc hạ phiên bản trên cluster production theo các bước giản lược trong bài. **Đường nâng cấp được hỗ trợ, tương thích mixed-version, định dạng SSTable, Java runtime, driver, công cụ backup và khả năng rollback** phải được xác minh theo tài liệu chính thức của **đúng cặp phiên bản nguồn–đích** và bản phân phối đang dùng. Bài này không giả định mọi phiên bản Cassandra hỗ trợ nâng/hạ trực tiếp.

## 1. “Nâng cấp thành công” gồm nhiều lớp

### 1.1. Node khỏe chưa đủ

Hãy phân biệt bốn lớp kiểm chứng:

| Lớp | Bằng chứng | Không thể suy ra chỉ từ bằng chứng đó |
| --- | --- | --- |
| **Process và ring** | Service chạy; node `UN`; gossip/schema agreement ổn | Tất cả partition/cell trên mọi replica đều giống nhau |
| **Dữ liệu và consistency** | Truy vấn theo primary key và CL trả đúng marker từ manifest | Mọi query shape, paging hoặc LWT đều không lỗi |
| **Ứng dụng** | CQL/Java Driver chạy đầy đủ luồng nghiệp vụ | p99, tỷ lệ timeout và chi phí tài nguyên vẫn trong SLO |
| **Vận hành và recovery** | Repair/streaming/backup/restore/drill được kiểm chứng | Nâng cấp có thể đảo ngược bằng downgrade tại mọi thời điểm |

Một request được ACK ở `LOCAL_QUORUM` chỉ xác nhận đủ replica **local** trả ACK, không chứng minh remote DC đã nhận cùng mutation. Một câu `SELECT` đúng ở quorum cũng không chứng minh **mọi replica trên toàn cluster đã hội tụ**. Để kết luận đủ dữ liệu, cần xác định chính xác **tập khóa kỳ vọng, loại ghi/đọc, thời điểm và phạm vi replica/DC**.

### 1.2. Những thay đổi có thể xảy ra

Tùy phiên bản nguồn–đích, nâng cấp có thể tác động đến:

- **CQL và schema:** chức năng được hỗ trợ, validation, index, giới hạn truy vấn hoặc giá trị mặc định của table options.
- **Read/write path:** compaction, read repair, tombstone, page fetching, internode messaging hoặc metadata.
- **Client protocol:** protocol version được thương lượng, authentication/TLS, contact points và node discovery.
- **Java Driver:** binary/API compatibility, policy, codec, timeout, retry/speculative execution và cách xử lý exception.
- **Tài nguyên:** CPU/heap/GC, memory, disk/compaction, băng thông inter-node, streaming/repair sau rolling restart.
- **Vận hành:** lệnh `nodetool`, metrics/JMX names, SSTable format và quy trình khôi phục.

Không tự nhận định một trong những thay đổi trên **chắc chắn** xảy ra ở mọi đợt nâng cấp. Mỗi đợt phải có **compatibility matrix** và tập regression tests phản ánh môi trường thực.

## 2. Định nghĩa tiêu chí PASS/FAIL trước khi đo

Trước khi nâng cấp, nhóm chịu trách nhiệm phải chốt **định nghĩa thành công**. Một số đo sau nâng cấp chỉ có ý nghĩa khi nó được so với baseline cùng tải và ngưỡng đã được phê duyệt.

| Hạng mục | Tiêu chí ví dụ cho lab | Vì sao cần |
| --- | --- | --- |
| Ring/topology | Các node dự kiến đều `UN`; không có topology change ngoài kế hoạch | Phát hiện node chưa tham gia hoặc restart thất bại |
| Schema | Schema/query contract đã kiểm chứng tại mọi checkpoint | Tránh lỗi prepared statement hoặc khác biệt schema |
| Dữ liệu bắt buộc | 100% marker đã ACK trong tập kiểm chứng trọng yếu `FOUND_MATCH` | Chặn việc bỏ qua dữ liệu sai/thiếu |
| Truy vấn nghiệp vụ | 100% test cases được định nghĩa trước chạy đúng | Bảo vệ query shapes, paging, LWT, TTL/DELETE |
| Error rate | Không vượt ngưỡng SLO và không xuất hiện loại lỗi nghiêm trọng mới | Nhận biết regression ẩn sau p50 tốt |
| Latency p95 | Không quá 1,25 lần baseline trong điều kiện tương đương | Kiểm chất lượng số đông request |
| Latency p99 | Không quá 1,5 lần baseline trong điều kiện tương đương | Bắt tail latency từ GC/I/O/repair |
| Read/write throughput | Đạt mức tải mục tiêu với error budget chấp nhận | Tránh đánh giá trên môi trường gần như rảnh |
| Phục hồi | Backup/restore và rollback/forward recovery có runbook được xác minh | Tránh bị kẹt trong trạng thái hỏng |

**Các tỷ lệ 1,25 và 1,5 chỉ là ngưỡng minh họa, không phải chuẩn Cassandra.** Ứng dụng thanh toán, telemetry và báo cáo có SLO khác nhau; không tự thay đổi mục tiêu sau khi thấy kết quả.

### Đặt tiêu chí theo từng giai đoạn

- **Trước nâng cấp:** đủ baseline và backup/restore; số lỗi chưa giải quyết được đánh dấu rõ.
- **Sau node canary:** ring, connection, CL và test đọc/ghi từ coordinator/node đã đổi version phải PASS.
- **Trong mixed-version window:** các query/driver vẫn hoạt động khi coordinator và replica có phiên bản khác nhau **nếu đường nâng cấp hỗ trợ**.
- **Sau khi mọi node đã lên version mới:** dữ liệu và nghiệp vụ PASS; latency/error rate được đo trên tải ổn định đủ lâu.
- **Sau bảo trì hậu nâng cấp:** streaming/repair/compaction/backup/restore trong phiên bản mới có tình trạng rõ ràng.

**Không lấy “các lệnh đều không báo lỗi” làm PASS** nếu kết quả query sai, số row bị thiếu hoặc dữ liệu bị ghi đè.

## 3. Bản kiểm kê trước nâng cấp

### 3.1. Lưu đúng ngữ cảnh để so trước/sau

Biên bản trước nâng cấp nên chứa:

| Nhóm | Cần ghi |
| --- | --- |
| Cluster | Cluster ID/tên, datacenter/rack, số node, RF theo DC, snitch, token ownership |
| Phần mềm | Cassandra version trên **từng node**, JVM version, OS/container image, Java Driver version |
| Schema | Keyspace, bảng, primary/clustering keys, UDT, index, materialized view nếu có, TTL, compaction/read repair options |
| CQL | Top query shapes, CL đọc/ghi, LWT/serial CL, paging size, batch/counter workload |
| Dữ liệu | Manifest các bản ghi đã ACK, source event IDs, expected versions, tombstone/TTL cases |
| Tài nguyên | CPU/heap/GC, disk free/I/O, compaction pending, streaming/repair, network |
| Truy cập | TLS, authentication, authorization, driver local DC, connection pools, retry budgets |
| Recovery | Backup set bên ngoài cluster, schema export, restore drill, điều kiện rollback/forward recovery |

**Không đọc version của một node rồi gán cho toàn cluster.** Trong quá trình rolling upgrade, một số node có thể đã đổi version trong khi node khác chưa đổi. Luôn ghi mapping `node → version → DC/rack → thời điểm`.

### 3.2. Các lệnh quan sát cơ bản

~~~bash
# Chạy ở node quản trị phù hợp trên cluster lab.
nodetool status
nodetool describecluster
nodetool version
nodetool netstats
nodetool compactionstats
nodetool tpstats
~~~

Trong `cqlsh` kết nối tới từng node mục tiêu nếu cần đối chiếu:

~~~sql
SELECT release_version, data_center, host_id
FROM system.local;
~~~

`system.local` trả metadata của **node đang xử lý truy vấn**, không phải danh sách mọi node. Tên và định dạng một số lệnh/metrics có thể khác giữa các phiên bản; dùng tài liệu của bản đang vận hành.

Với keyspace cụ thể:

~~~sql
SELECT keyspace_name, replication, durable_writes
FROM system_schema.keyspaces
WHERE keyspace_name = 'upgrade_verify_lab';
~~~

Nếu keyspace chưa tồn tại, truy vấn chỉ trả rỗng; không tạo schema production chỉ vì muốn đo kiểm.

### 3.3. Backup là điều kiện trước, không phải phương án rollback mặc định

Một bản snapshot nằm trên cùng volume **không** bảo vệ trước mất node/cluster. Cần backup **ngoài failure domain**, manifest file/checksum, schema, KMS/credential và restore drill. Không suy ra có thể downgrade trực tiếp từ version mới về version cũ: SSTable format, schema, commit log, protocol và trạng thái streaming có thể không tương thích.

**Rollback khả thi có thể là** chuyển traffic về cluster cũ vẫn được duy trì, restore sang cluster sạch với version hỗ trợ, hoặc **forward-fix** lỗi trên version mới. Phải có kế hoạch **write ownership/fencing** và đối soát các ghi phát sinh trong khi hai môi trường cùng tồn tại; không tạo “hai nguồn sự thật” khi failback.

## 4. Bộ dữ liệu kỳ vọng: manifest độc lập với Cassandra

### 4.1. Vì sao so count không đủ?

Giả sử trước nâng cấp có:

~~~text
expected:
  E1 -> status=PAID,   version=3
  E2 -> status=NEW,    version=1
  E3 -> DELETE đã ACK, không được trả hàng

after:
  E1 -> status=PAID,   version=3
  E2 -> status=PAID,   version=2 (sai)
  E3 -> không có hàng
~~~

Số hàng còn sống trước/sau có thể **bằng nhau**, nhưng E2 đã thay đổi ngoài hợp đồng. `COUNT(*)` trên bảng lớn vừa tốn tài nguyên vừa không chỉ ra **ID và giá trị cụ thể** bị sai.

Một manifest đáng tin lưu ở nguồn **độc lập với cluster đích**:

| Trường | Mục đích |
| --- | --- |
| `test_run_id`, `event_id`, full primary key | Xác định chính xác row cần đối soát |
| Expected columns + canonical hash | Kiểm giá trị, tránh sai thứ tự/định dạng |
| ACK/UNKNOWN, write CL và thời điểm ACK | Không biến write timeout thành ACK |
| Loại row | Thường, delete/tombstone, TTL, LWT, giá trị Unicode/decimal |
| Schema contract version | Biết cách diễn giải type/scale/timezone |
| Read CL, coordinator/DC, timestamp kiểm tra | Định nghĩa phạm vi kết luận |
| Kết quả và mã lỗi | Tách `FOUND_MATCH`, `MISSING`, `MISMATCH`, `READ_ERROR` |

**Source of truth** có thể là event log/outbox, dữ liệu đã xuất từ hệ thống nguồn hoặc manifest ACK được ghi trong kho audit phù hợp. Không lập “expected” bằng chính SELECT từ cluster **sau nâng cấp** rồi tự báo 100% đúng.

### 4.2. Phân loại kết quả để tránh kết luận sai

| Kết quả | Ý nghĩa | Có phải mất dữ liệu vĩnh viễn? |
| --- | --- | --- |
| `FOUND_MATCH` | Query hoàn tất và field/marker khớp manifest | Không, đây là PASS cho khóa/CL được kiểm |
| `MISSING_AT_CL` | Query hoàn tất nhưng không có hàng expected | Chưa chắc; cần xem delete/TTL, replication và nguồn |
| `MISMATCH` | Query hoàn tất nhưng giá trị khác expected | Là regression cần điều tra; có thể do concurrent writer/contract |
| `READ_ERROR` | Timeout, unavailable, failure hoặc lỗi đọc khác | **Không**; chưa biết hàng có tồn tại hay không |
| `UNKNOWN_WRITE` | Write không nhận ACK cuối cùng, có thể đã tới một số replica | Chưa biết; cần đối soát trước retry |
| `EXPECTED_ABSENT_MATCH` | Một hàng đã DELETE/TTL đúng quy tắc và query không trả hàng | PASS theo loại dữ liệu này |

**Nguyên tắc:** báo riêng số khóa kiểm được, khóa chưa xác minh và những khóa đã ACK bị sai/thiếu. Đừng gộp `READ_ERROR` vào `MISSING` hoặc suy từ một lần đọc lỗi rằng repair/upgrade đã xóa dữ liệu.

### 4.3. Các nhóm test data nên có

- Text UTF-8 có dấu tiếng Việt, Unicode normalization theo hợp đồng.
- `uuid`, `decimal`, `bigint`, timestamp UTC/offset, null và empty string.
- Các partition kích thước nhỏ/lớn vừa phải; clustering range, page boundary và row/column projection.
- TTL chưa hết, TTL vừa hết, tombstone do DELETE; **đo theo thời điểm**.
- Dữ liệu ghi gần thời điểm nâng cấp và dữ liệu cũ đã nằm trong nhiều SSTable.
- Một số partition không được truy vấn thường xuyên để không chỉ kiểm những replica được read repair vô tình sửa.
- Test cases LWT `IF NOT EXISTS`/`IF version = ...` với **khóa riêng cho mỗi lượt**, không để kiểm thử ghi đè dữ liệu production.

Với các phép thử dùng clock, phải đồng bộ thời gian trên node và client, và phải ghi rõ độ chính xác millisecond của CQL `timestamp` so với microsecond write timestamp.

## 5. Lab CQL: tạo baseline có primary key rõ ràng

### 5.1. Giả định topology

Lab minh họa có ba node Cassandra trong DC tên `datacenter1`, dùng `NetworkTopologyStrategy` với RF=3. Nếu lab thực tế chỉ có một node hoặc tên DC khác, **điều chỉnh RF/CL/tên DC theo topology**, không mong `LOCAL_QUORUM` RF3 có đủ hai replica trên một node.

Trước lab:

~~~bash
nodetool status
~~~

Chỉ tiến hành bước test baseline cần `ALL` khi **cả ba replica khỏe**, không có topology change hay streaming lớn ngoài kế hoạch.

### 5.2. Tạo keyspace và bảng chuyên dụng

~~~sql
CREATE KEYSPACE IF NOT EXISTS upgrade_verify_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS upgrade_verify_lab.events_by_run_day (
    run_id text,
    event_day date,
    event_ts timestamp,
    event_id uuid,
    status text,
    version int,
    amount decimal,
    payload text,
    PRIMARY KEY ((run_id, event_day), event_ts, event_id)
) WITH CLUSTERING ORDER BY (event_ts DESC, event_id DESC);
~~~

`(run_id, event_day)` là **composite partition key**; `event_ts` và `event_id` là clustering keys. Bảng này cố tình lưu **một tập nhỏ** theo run ID/ngày để dễ đối soát. **Không** dùng một `run_id` khổng lồ chứa hàng triệu event cho workload production; cần bucket/shard theo truy vấn và lưu lượng thực.

`IF NOT EXISTS` không sửa schema đã tồn tại. Trước khi diễn giải kết quả, kiểm tra RF và metadata bảng thực tế, tránh vô tình dùng keyspace từ lần thử trước.

~~~sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'upgrade_verify_lab';
~~~

### 5.3. Ghi dữ liệu baseline

Trong `cqlsh` kết nối tới node thuộc `datacenter1`:

~~~text
CONSISTENCY ALL
~~~

~~~sql
INSERT INTO upgrade_verify_lab.events_by_run_day
    (run_id, event_day, event_ts, event_id,
     status, version, amount, payload)
VALUES (
    'upgrade-lab-01', '2026-11-21',
    '2026-11-21T08:00:00.000Z',
    11111111-1111-4111-8111-111111111111,
    'PAID', 3, 123.4500, 'Đơn hàng: Cà phê'
);

INSERT INTO upgrade_verify_lab.events_by_run_day
    (run_id, event_day, event_ts, event_id,
     status, version, amount, payload)
VALUES (
    'upgrade-lab-01', '2026-11-21',
    '2026-11-21T08:05:00.000Z',
    22222222-2222-4222-8222-222222222222,
    'NEW', 1, 100.00, 'event-baseline-B'
);
~~~

Chỉ ghi vào manifest `ACKNOWLEDGED` nếu từng INSERT thực sự thành công tại `ALL`. Nếu gặp timeout, **đánh dấu UNKNOWN_WRITE** và xác minh; không tự ghi nhận ACK để “làm đẹp baseline”.

Trong production, không cần chọn `ALL` cho mọi truy vấn chỉ để chứng minh nâng cấp; đây là test dễ hiểu trong lab RF3 khỏe. Ở nhiều DC, `ALL` có thể buộc chờ tất cả replica toàn cluster, làm mất khả năng phục vụ khi DC nào đó lỗi.

### 5.4. Hai kiểu đọc baseline

Đọc một hàng có **đầy đủ primary key**:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
SELECT status, version, amount, payload
FROM upgrade_verify_lab.events_by_run_day
WHERE run_id = 'upgrade-lab-01'
  AND event_day = '2026-11-21'
  AND event_ts = '2026-11-21T08:00:00.000Z'
  AND event_id = 11111111-1111-4111-8111-111111111111;
~~~

Đọc **range theo clustering timestamp** trong một partition:

~~~sql
SELECT event_ts, event_id, status, version
FROM upgrade_verify_lab.events_by_run_day
WHERE run_id = 'upgrade-lab-01'
  AND event_day = '2026-11-21'
  AND event_ts >= '2026-11-21T08:00:00.000Z'
  AND event_ts <  '2026-11-21T09:00:00.000Z'
LIMIT 20;
~~~

Ghi **cả giá trị và thứ tự** của các hàng trả về, không chỉ số hàng. Với clustering order DESC, ứng dụng có thể dựa vào thứ tự này; một thay đổi query/driver khiến sắp xếp sai sẽ là regression dù dữ liệu vẫn đủ.

### 5.5. Cases cho DELETE, TTL và LWT

Không chạy đi chạy lại bài test ghi lên cùng primary key khi so trước/sau. Dùng **run ID riêng** cho mỗi giai đoạn, chốt danh sách expected và mốc thời gian.

**DELETE marker:** tạo thêm một row ở run thử riêng bằng `INSERT` thành công, sau đó `DELETE` tại CL đã chọn:

~~~sql
DELETE FROM upgrade_verify_lab.events_by_run_day
WHERE run_id = 'upgrade-delete-01'
  AND event_day = '2026-11-21'
  AND event_ts = '2026-11-21T08:10:00.000Z'
  AND event_id = 33333333-3333-4333-8333-333333333333;
~~~

Sau DELETE ACK, kiểm thử phải kỳ vọng **không thấy row** tại thời điểm/CL phù hợp. Nhưng nếu chưa từng INSERT row trước đó, lệnh DELETE trên không kiểm chứng được điều kiện tombstone che dữ liệu cũ; hãy tạo một row thực tế rồi mới xóa.

**TTL marker:** ở run khác, dùng `INSERT ... USING TTL 120` với thời điểm bắt đầu đo do client ghi lại. TTL test chỉ đúng nếu đo trước hạn và sau hạn có vùng đệm phù hợp; không so hai lần đọc cách nhau quá lâu rồi gọi dữ liệu hết TTL là “mất vì upgrade”.

**LWT marker:** chạy `INSERT ... IF NOT EXISTS` với **khóa chưa dùng** rồi kiểm cột `[applied]`. Chạy lại với cùng khóa sẽ trả `[applied]=false` nếu row đã tồn tại; đó là **ngữ nghĩa đúng**, không phải regression. Các lệnh LWT cần được so theo **kịch bản trạng thái đầu vào** và serial consistency thích hợp, không chỉ so chuỗi output.

## 6. Ma trận regression truy vấn trước/sau

Một bộ regression tốt không chỉ kiểm câu SQL mẫu, mà phải chứa **query shapes thật mà ứng dụng Java gửi**.

| Nhóm | Test trước nâng cấp | Kiểm sau nâng cấp |
| --- | --- | --- |
| **Point read** | WHERE đủ partition + clustering key; CL rõ ràng | Row/field/latency và metadata trả đúng |
| **Range read** | Clustering range + `LIMIT` + ORDER phù hợp schema | Tập ID, thứ tự, page boundary không đổi |
| **Projection** | `SELECT` danh sách cột cụ thể, null/empty cases | Codec/type mapping không đổi |
| **Paging** | Page size, iteration, paging state có kiểm soát | Không mất/trùng hàng khi đọc toàn bộ tập ổn định |
| **Prepared statement** | Prepare/bind các kiểu số, UUID, timestamp, decimal | Không phát sinh lỗi protocol/codec/schema sau rolling |
| **Write** | INSERT/UPDATE với ID ổn định, CL rõ | ACK/UNKNOWN, read-after-write và giá trị đúng |
| **Conditional write (LWT)** | `IF NOT EXISTS` / `IF version = ...` | `[applied]` và giá trị sau LWT đúng |
| **TTL và DELETE** | Test trước/sau thời hạn, tombstone | Không coi expiry đúng thời điểm là mất dữ liệu |
| **Counter**, nếu dùng | Kiểm thao tác tăng, retry semantics | Không kiểm bằng retry mù quáng hoặc so snapshot số cứng |
| **Secondary index/SAI**, nếu dùng | Truy vấn được version/schema hỗ trợ | Kết quả, latency, rebuild/index status tương thích |
| **Multi-DC** | LOCAL_ONE/LOCAL_QUORUM theo đúng local DC | Phạm vi ACK, remote lag, failover/readback đúng |
| **Authentication/TLS** | Kết nối bằng role ứng dụng, quyền denied cases | Driver/PKI/CQL permissions không bị thay đổi trái phép |

**Không lấy paging state cũ trước nâng cấp gửi sang version mới rồi mặc nhiên đòi tương thích** nếu cặp phiên bản/driver không cam kết điều đó. Một token paging có thể gắn với query, bind parameters và protocol. Kiểm thử **hành vi phân trang** bằng cách đọc cùng tập dữ liệu ổn định trong mỗi phiên, đồng thời tách trường hợp cố ý kiểm tính tương thích token giữa phiên bản nếu có yêu cầu riêng.

### Kiểm thử ngữ nghĩa và kiểm thử hiệu năng là hai bài khác nhau

Trong test chức năng:

- Với dữ liệu bất biến, so **event IDs, thứ tự, các trường và kiểu dữ liệu**.
- Với dòng có TTL, ghi rõ **thời điểm quan sát**; không dùng giá trị kỳ vọng đã hết hạn.
- Với LWT, dùng khóa mới/trạng thái chuẩn bị giống nhau ở hai giai đoạn.
- Với counter, phải tạo trạng thái bắt đầu và số mutation xác định; tránh retry làm tăng nhiều lần.
- Với ghi đang diễn ra, cần **cửa sổ cắt dữ liệu hoặc event log có version** để không kết luận thay đổi hợp lệ là regression.

Trong test hiệu năng:

- Chạy workload đủ tương đương về số request/giây, phân phối partition key, tỷ lệ read/write, payload và CL.
- Thu p95/p99, error rate, tải node; không lấy số lượng hàng thay cho độ trễ.
- Tách **warm-up, cache lạnh sau restart, bootstrap/streaming/compaction** với trạng thái ổn định.

## 7. Đo latency, throughput và error rate công bằng

### 7.1. Ba cửa sổ cần tách

~~~mermaid
flowchart LR
    B["Baseline ổn định trước nâng cấp"] --> R["Rolling/mixed-version\nchịu restart và warm-up"]
    R --> S["Post-upgrade ổn định\nđã qua warm-up"]
    B -. "So cùng tải/SLO" .-> S
    R --> I["Báo cáo tác động trong bảo trì riêng"]
~~~

**Không chỉ đo “trước khi restart” so với “ngay khi node vừa lên”.** Khi node khởi động, page cache lạnh và network/compaction/streaming có thể làm latency biến động. Phải **báo riêng ảnh hưởng trong rolling window** và regression còn tồn tại ở trạng thái ổn định sau nâng cấp.

### 7.2. Các chỉ số phải thu

| Tầng | Chỉ số | Ý nghĩa |
| --- | --- | --- |
| Client Java | Request rate, success/error count, p50/p95/p99, retries, speculative executions | Trải nghiệm thật và khuếch đại tải |
| CQL operation | Read/write/LWT latency tách theo query shape/CL | Tránh một query nặng làm che nhiều query nhẹ |
| Cassandra | Read/write timeout, unavailable, failures, dropped messages | Mức độ đáp ứng và tình trạng quá tải |
| Node | CPU, heap/GC pauses, disk latency/IOPS, network, file descriptor | Nguồn tài nguyên giới hạn |
| SSTable/compaction | Pending compactions, tombstones/SSTables read, disk free | Thay đổi đọc/ghi và workload nền |
| Topology | Node `UN`/`DN`, streaming, repair/hints progress | Phân biệt regression với node chưa hồi phục |
| Dữ liệu | Expected rows, match/missing/mismatch/read error | Đảm bảo tối ưu tốc độ không đánh đổi dữ liệu |

Đo với độ phân giải và cửa sổ đủ lớn, ví dụ từng 1–5 phút và tổng cả giai đoạn, nhưng ngưỡng cụ thể tùy SLO. Một vài chục request không đủ để ước lượng p99 tin cậy. Ghi cách tạo tải, concurrency, request mix và công cụ thu metrics để có thể tái lập.

### 7.3. Số minh họa — không phải benchmark Cassandra

| Chỉ số ở cùng workload | Baseline | Sau nâng cấp | Diễn giải |
| --- | ---: | ---: | --- |
| Read QPS | 1.000 | 1.000 | Tải mục tiêu giống nhau |
| p50 read | 8 ms | 8 ms | Không đổi |
| p95 read | 20 ms | 23 ms | Tăng 15% |
| p99 read | 45 ms | 82 ms | Tăng khoảng 82% |
| Read errors/10.000 requests | 2 | 18 | Cần phân loại loại lỗi |
| CPU trung bình | 52% | 60% | Cần so theo node/rack |
| Pending compactions | 5 | 220 | Có thể gây tail latency; cần xác minh |

Nếu mục tiêu p99 không quá 1,5 lần baseline, ngưỡng là **67,5 ms**; giá trị **82 ms không đạt**. Không vì p50 vẫn là 8 ms mà tuyên bố nâng cấp thành công. Nếu request lỗi bị loại khỏi histogram, p99 của các request thành công còn có thể **che khuất timeout**; phải báo error rate kèm latency.

### 7.4. Loại sai lệch trong so sánh

- Không đổi đồng thời **query, CL, RF, page size, retry policy, heap, JDK, compaction strategy** rồi gán tác động cho Cassandra version.
- Nếu buộc đổi nhiều thành phần để đáp ứng compatibility, **ghi rõ từng thay đổi** và tách phép thử khi khả thi.
- Không so p95 trong giờ rảnh với p95 giờ cao điểm.
- Không dùng latency của `cqlsh` trên cùng node làm thay thế latency của Java Driver chạy từ ứng dụng qua mạng.
- Không so một workload đã nóng cache với workload mới restart chưa warm-up mà quên chú thích.
- Không bỏ những request timeout khỏi mẫu theo cách làm giảm artificial p99.
- Với multi-DC, so trong cùng local DC/đường mạng; độ trễ WAN có thể lớn hơn khác biệt engine.

## 8. Lỗi phải được phân loại, không chỉ đếm “5xx”

Cùng một tỷ lệ lỗi có thể đến từ các nguyên nhân hoàn toàn khác nhau.

| Lớp lỗi | Dấu hiệu điển hình | Khả năng liên quan nâng cấp | Xử lý đầu tiên |
| --- | --- | --- | --- |
| **Bootstrap/driver** | NoNodeAvailable, không mở được session | Discovery, TLS/protocol, local DC, phiên bản driver | Kiểm endpoint, phiên bản, SSL/auth, logs |
| **Schema/query** | InvalidQuery, unknown column/table, prepare thất bại | Schema agreement, DDL/codec không tương thích | So schema và query contract |
| **ReadTimeout** | Coordinator không nhận đủ phản hồi kịp hạn | Replica chậm, compaction, mạng, CL | Ghi `READ_ERROR`, xem node/trace |
| **WriteTimeout** | Không nhận đủ write ACK trong hạn | Replica/disk/network chậm | Ghi `UNKNOWN_WRITE`; không tự retry tùy tiện |
| **Unavailable** | Không đủ replica sống cho CL | Rolling node down, topology/rack/DC | Kiểm RF/CL và `nodetool status` |
| **ReadFailure/WriteFailure** | Replica báo lỗi xử lý | Storage/network/phiên bản | Đọc lỗi theo node và timestamp |
| **Unauthorized/Auth** | Quyền/credential/cert không hợp lệ | Thay config security hoặc client | Kiểm TLS/roles/secret rotation |
| **Protocol/codec** | Đọc/ghi sai type, handshake khác | Driver/Native Protocol/JDK | Compatibility matrix và integration test |
| **Data mismatch** | Query thành công nhưng marker khác | Concurrent writers, timestamp/tombstone hoặc regression | So manifest, CL, repair và lịch ghi |
| **Service/API** | HTTP 5xx nhưng CQL chưa được gửi | Logic ứng dụng, queue/cache/dependency | Tách log tầng HTTP khỏi Cassandra |

**Một `WriteTimeout` không bảo đảm ghi chưa xảy ra.** Mutation có thể đã đến một số replica mà client không nhận ACK; không được thử lại LWT/counter/batch hoặc tạo UUID mới mà không đánh giá idempotency. Đối với `ReadTimeout`, query chưa hoàn tất nên không được báo bản ghi vắng mặt.

Lưu log theo **request ID, query shape (không kèm PII), partition bucket/khóa đã ẩn danh, CL, coordinator/DC, elapsed, retry count, exception category và thời điểm**. Không ghi trực tiếp password, token hoặc payload khách hàng vào log benchmark.

## 9. Java Driver 4.x: kiểm chứng marker và lấy số đo end-to-end

Đoạn mã sau giả định **Java 17, Cassandra Java Driver 4.x**, bảng lab đã được tạo, và một `CqlSession` dùng lại trong ứng dụng. Nó **không tự mở cluster hoặc nâng cấp node**; nhiệm vụ của nó là đọc một hàng bằng full primary key, so với expected marker và đo thời gian ở client.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.ExecutionInfo;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

public final class UpgradeReadProbe {
    public enum State { FOUND_MATCH, MISSING_AT_CL, MISMATCH, READ_ERROR }
    public record Expected(
        String runId,
        LocalDate eventDay,
        Instant eventTs,
        UUID eventId,
        String status,
        int version,
        BigDecimal amount,
        String payload) {}
    public record Result(
        State state, long latencyMicros,
        String coordinator, String errorType) {}

    private final CqlSession session;
    private final PreparedStatement read;

    public UpgradeReadProbe(CqlSession session) {
        this.session = session;
        this.read = session.prepare(
            "SELECT status, version, amount, payload " +
            "FROM upgrade_verify_lab.events_by_run_day " +
            "WHERE run_id = ? AND event_day = ? " +
            "AND event_ts = ? AND event_id = ?");
    }

    public Result verify(Expected expected) {
        BoundStatement statement = read.bind(
                expected.runId(), expected.eventDay(),
                expected.eventTs(), expected.eventId())
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotence(true);
        long started = System.nanoTime();
        try {
            ResultSet result = session.execute(statement);
            ExecutionInfo info = result.getExecutionInfo();
            String coordinator = info.getCoordinator() == null
                ? "unknown" : info.getCoordinator().getEndPoint().toString();
            Row row = result.one();
            long elapsed = elapsedMicros(started);

            if (row == null) {
                return new Result(
                    State.MISSING_AT_CL, elapsed, coordinator, null);
            }
            BigDecimal actualAmount = row.getBigDecimal("amount");
            boolean amountMatches =
                actualAmount != null && expected.amount() != null
                && actualAmount.compareTo(expected.amount()) == 0;
            boolean matches =
                Objects.equals(expected.status(), row.getString("status"))
                && expected.version() == row.getInt("version")
                && amountMatches
                && Objects.equals(expected.payload(), row.getString("payload"));
            return new Result(
                matches ? State.FOUND_MATCH : State.MISMATCH,
                elapsed, coordinator, null);
        } catch (RuntimeException error) {
            return new Result(
                State.READ_ERROR, elapsedMicros(started),
                "unknown", error.getClass().getSimpleName());
        }
    }

    private static long elapsedMicros(long started) {
        return TimeUnit.NANOSECONDS.toMicros(System.nanoTime() - started);
    }
}
~~~

**Giải thích cần lưu ý:**

- `LOCAL_QUORUM` cần RF và local DC được thiết lập phù hợp. Không dùng kết quả một local read làm bằng chứng replica của tất cả DC đã nhận mutation.
- `getInstant()/Instant`, `UUID`, `LocalDate` và `BigDecimal` giúp giữ đúng ý nghĩa của kiểu dữ liệu, tránh so timestamp theo chuỗi hiển thị khác timezone.
- `BigDecimal.compareTo` so **giá trị số**; nếu hợp đồng yêu cầu giữ **scale** gốc, phải so thêm `scale()` hoặc representation canonical.
- `MISSING_AT_CL` chỉ xuất hiện khi câu SELECT **thành công** mà không có hàng; `READ_ERROR` ghi riêng các exception. Dữ liệu đã xóa/TTL hợp lệ phải dùng loại expected riêng, không gọi missing là lỗi.
- `System.nanoTime()` đo **duration monotonic**; thời gian client bao gồm driver/network/server. Muốn p95/p99 phải thu nhiều kết quả, có histogram và tách lỗi.
- `ExecutionInfo.getCoordinator()` cho biết coordinator của lần thực thi được báo bởi driver; nó không tự cho biết mọi replica đã tham gia hoặc có repair không.
- Code chỉ log **loại lỗi**, không log nội dung nhạy cảm. Trong production phải có request IDs, metrics, retry budgets, circuit breaker/backpressure và phân loại exception chi tiết.
- `setIdempotence(true)` phù hợp `SELECT` thuần trong ví dụ, **không** được sao chép sang mutation có side effect khi chưa có chính sách idempotency.

### Cấu hình phiên ứng dụng để so trước/sau

Ví dụ cấu trúc kết nối trong một DC:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import java.net.InetSocketAddress;

// Dùng IP/hostname lab thực tế và cấu hình TLS/auth từ secret manager.
try (CqlSession session = CqlSession.builder()
        .addContactPoint(new InetSocketAddress("10.10.0.11", 9042))
        .addContactPoint(new InetSocketAddress("10.10.0.12", 9042))
        .withLocalDatacenter("datacenter1")
        .build()) {
    UpgradeReadProbe probe = new UpgradeReadProbe(session);
    // Đọc danh sách Expected từ manifest độc lập và gọi probe.verify(...).
    // Thu kết quả ở hệ metrics/audit có kiểm soát.
}
~~~

Các địa chỉ là ví dụ private trong lab. Ứng dụng thật cần TLS, authentication, hostname validation, Java runtime, native protocol và timeout settings tương thích với cặp version đang chạy. **Tái sử dụng session** trên request path thật; không mở session mới cho từng bản ghi.

## 10. Kiểm chứng phiên bản hỗn hợp trong rolling upgrade

Một đợt **rolling upgrade** thường thay đổi từng node hoặc từng nhóm nhỏ, nhằm giữ dịch vụ tiếp tục hoạt động. Tuy nhiên, không phải mọi cặp phiên bản đều được phép chạy lẫn nhau; phải đọc upgrade path/mixed-version guidance **trước** khi bắt đầu.

### 10.1. Các checkpoint

~~~mermaid
flowchart TD
    A["Chốt compatibility + backup + baseline"] --> B["Canary trong staging"]
    B --> C{"Query/data/SLO PASS?"}
    C -->|Không| X["Dừng, điều tra, áp dụng rollback/forward recovery đã duyệt"]
    C -->|Có| D["Nâng cấp một node/rack nhỏ"]
    D --> E["Đo node/ring/schema, dữ liệu, Java và metrics"]
    E --> F{"Đạt gate mixed-version?"}
    F -->|Không| X
    F -->|Có| G["Tiếp tục từng node theo failure domain"]
    G --> H["Đo post-upgrade ổn định"]
    H --> I{"Go / No-Go"}
    I -->|Go| J["Theo dõi + verify backup/restore"]
    I -->|No-Go| X
~~~

### 10.2. Tại sao việc chọn một node để nâng cấp quan trọng?

Giả sử RF3 trong một DC và client dùng `LOCAL_QUORUM`. Khi **một node down để nâng cấp**, hai replica còn sống của một partition có thể vừa đủ quorum. Nếu đồng thời một replica khác bị lỗi, quorum có thể không đạt. Với `ALL`, một node down có thể khiến truy vấn trên các partition liên quan không đủ điều kiện trả thành công.

Trong nhiều DC, cần tính RF và CL **theo datacenter**. `LOCAL_QUORUM` của coordinator `dc_a` không thể lấy ACK từ `dc_b` để bù quorum local. Không lên lịch dừng nhiều node/rack chỉ dựa trên tổng số node toàn cluster.

Các kiểm tra giữa mỗi vòng gồm:

~~~bash
nodetool status
nodetool netstats
nodetool compactionstats
nodetool tpstats
~~~

Kết hợp log Cassandra, Java Driver metrics, schema agreement và synthetic CQL. `UN` không có nghĩa quá trình repair/streaming đã xong hay dữ liệu remote đã hội tụ.

### 10.3. Kiểm tra client trong môi trường mixed-version

Trong window được **tài liệu version xác nhận hỗ trợ**, thực hiện cùng một bộ kiểm thử từ Java Driver:

1. Dùng prepared SELECT có đầy đủ partition key; xem coordinator thực tế đang chạy version nào.
2. Ghi marker mới với CL được thiết kế; phân loại ACK/UNKNOWN.
3. Đọc lại marker sau ACK ở CL/địa bàn đúng và kiểm giá trị.
4. Kiểm LWT, paging, null/codec, authentication/TLS với workload có sử dụng.
5. So phân bố latency/error theo coordinator version, node/DC và thời điểm.

Không tự ép coordinator chỉ dùng version mới bằng cách đưa một IP mới vào contact points. Sau discovery, Java Driver có thể chọn node khác. Nếu cần đo canary theo version, dùng công cụ quan sát/routing kiểm soát được, có ghi rõ limitations, không thay policy production tùy tiện.

## 11. Tracing, repair, compaction và tương thích dữ liệu

Khi thấy latency tăng sau nâng cấp, không mặc định đây là “engine mới chậm hơn”. Có thể:

- Một số node đang **warm cache** và đọc nhiều SSTable từ đĩa hơn.
- **Compaction/streaming/repair** tăng I/O và network sau restart.
- **Digest mismatch/read repair** xuất hiện do replica từng down trong rolling window.
- Java Driver retry/speculative execution làm tăng số request thực tế khi một node chậm.
- Schema/index/codec có thay đổi hoặc chưa sẵn sàng tại mọi node.
- Tên metric/stage khác version khiến dashboard tưởng giá trị bằng 0 hoặc mất dữ liệu quan sát.

### Lệnh chẩn đoán có chọn lọc

Trong một phiên `cqlsh` cho **một partition có giới hạn**:

~~~text
TRACING ON
~~~

~~~sql
SELECT event_ts, event_id, status, version
FROM upgrade_verify_lab.events_by_run_day
WHERE run_id = 'upgrade-lab-01'
  AND event_day = '2026-11-21'
LIMIT 20;
~~~

~~~text
TRACING OFF
~~~

Trace có thể giúp tìm data/digest requests, đọc bổ sung, read repair, replica phản hồi chậm và coordinator. Nó có overhead, nên **không bật đại trà trên production**. Khi phân tích, đối chiếu trace ID với metrics/logs của đúng node/version và trạng thái CL.

### Repair không phải phép kiểm dữ liệu nghiệp vụ

`nodetool repair` giúp anti-entropy giữa replica theo phạm vi/vận hành được hỗ trợ, nhưng:

- Không tự tạo event **chưa từng được ghi vào replica nào**.
- Không thay manifest expected IDs hoặc các kiểm thử query/LWT/driver.
- Có thể tốn disk I/O, CPU, network và kéo dài p99; không chạy repair lớn cùng một đợt upgrade nếu chưa được lập kế hoạch.
- Không sửa vấn đề **tombstone đã purge ở các replica khác** khi node cũ vắng quá lâu; nguy cơ zombie cần quy trình xử lý theo thời gian down và `gc_grace_seconds`.

Tương tự, compaction tạo SSTable mới **cục bộ** và không tự chứng minh các replica hoặc toàn bộ tập dữ liệu ứng dụng đã khớp.

### SSTable format và các bước không nên tự làm

Một số đường nâng cấp có bước thay đổi format/upgrade SSTable (chẳng hạn các công cụ quản trị khi phiên bản hỗ trợ). Những bước này có thể làm **khả năng quay về phiên bản cũ bị giới hạn hoặc mất hẳn**. Chỉ thực hiện sau khi xác minh chính xác runbook, có backup ngoài cluster và hiểu **khi nào rollback còn khả thi**. Không gắn lệnh “nâng cấp SSTable” vào một checklist chung cho mọi bản mà thiếu kiểm compatibility.

## 12. Báo cáo so sánh trước/sau có thể kiểm toán

### 12.1. Mẫu biên bản

~~~text
CHANGE_ID:                 CHG-EXAMPLE-001
CLUSTER/DC:                lab-cassandra / datacenter1
SOURCE_VERSION:            <actual version per node>
TARGET_VERSION:            <approved target version>
DRIVER/JVM_VERSION:        <actual versions>
UPGRADE_PATH_SUPPORTED:    verified / unknown / not supported
BACKUP_RESTORE_DRILL:      pass / fail / not tested
BASELINE_WINDOW:           <start UTC> .. <end UTC>
ROLLING_WINDOW:            <start UTC> .. <end UTC>
POST_STABLE_WINDOW:        <start UTC> .. <end UTC>
QUERY_SHAPES_TESTED:       ...
EXPECTED_ACKED_KEYS:       ...
FOUND_MATCH:               ...
EXPECTED_ABSENT_MATCH:     ...
MISSING_AT_CL:             ...
MISMATCH:                  ...
READ_ERROR:                ...
UNKNOWN_WRITE:             ...
P50/P95/P99_READ:          before -> after
P50/P95/P99_WRITE:         before -> after
ERROR_RATE_BY_CATEGORY:    before -> after
NODE/REPLICA_HEALTH:       ...
SCHEMA_AGREEMENT:          ...
COMPACTION/STREAMING:      ...
OPEN_GAPS:                 ...
DECISION:                  GO / NO_GO / INVESTIGATE
OWNER/APPROVAL:            ...
~~~

**Mọi dấu `...` trong mẫu trên là placeholder**, không phải kết quả đo. Cùng biên bản cần đính kèm tập test IDs, kết quả theo query shape, thống kê latency với sample size, thời điểm node restart và lý do loại bỏ mẫu.

### 12.2. Ví dụ kết quả giả định

| Hạng mục | Quan sát | Quyết định |
| --- | --- | --- |
| Ring | 3/3 node `UN` sau nâng cấp | PASS sơ bộ |
| Schema/driver | 24/24 query cases thành công | PASS chức năng |
| Dữ liệu | 999 `FOUND_MATCH`, 1 `MISMATCH`, 0 lỗi đọc | **FAIL dữ liệu**, điều tra ID sai |
| p95 | 20 ms → 23 ms | PASS nếu giới hạn 1,25 lần |
| p99 | 45 ms → 82 ms | **FAIL** nếu giới hạn 1,5 lần |
| Errors | 2 → 18/10.000 requests | Cần phân loại và so ngưỡng |
| Recovery | Có backup nhưng restore drill chưa được thử | **GAP**, chưa đủ bằng chứng DR |

Kết quả này **không đạt điều kiện GO**, dù node/ring đều ổn và các câu CQL mẫu chạy thành công. Một lỗi giá trị có thể là dữ liệu bị ghi đổi trong lúc đo chứ không nhất thiết do version mới: **phải giữ ID, expected value, write history và CL** để điều tra. Nhưng trước khi xác minh nguyên nhân, không được bỏ qua mismatch và tiếp tục rollout như thể đã PASS.

### 12.3. Một đồ thị hữu ích

~~~mermaid
flowchart LR
    D["Mọi kết quả readback"] --> M["FOUND_MATCH"]
    D --> A["EXPECTED_ABSENT_MATCH"]
    D --> X["MISSING / MISMATCH"]
    D --> E["READ_ERROR"]
    X --> H["Điều tra data/replica/contract"]
    E --> T["Điều tra timeout/availability"]
    M --> G["Gate chất lượng"]
    A --> G
    H --> G
    T --> G
    G --> Z{"GO / NO-GO?"}
~~~

Không lấy **tỷ lệ FOUND_MATCH trên những request thành công** rồi quên `READ_ERROR`. Tập dữ liệu chưa đọc được phải giữ trong mẫu số các record chưa xác minh, nhưng được **báo riêng**, không dán nhãn là missing.

## 13. Runbook kiểm chứng ở mỗi checkpoint

### Checkpoint A — Trước nâng cấp

1. Chốt version path/compatibility, cluster topology và mục tiêu SLO.
2. Kiểm chứng backup ngoài cluster, khả năng decrypt và restore drill.
3. Freeze/bảo vệ schema thay đổi ngoài kế hoạch; lập query catalog.
4. Đo baseline ổn định với tải đại diện, thu cả successful requests và errors.
5. Chốt manifest expected rows/DELETE/TTL/LWT, ký nhận trạng thái ACK.
6. Chuẩn bị fault budget: tối đa bao nhiêu node down ở mỗi DC/rack, ngưỡng dừng, rollback/forward recovery.

### Checkpoint B — Sau canary / một node

1. Kiểm node/version/metadata và khả năng kết nối internode/driver.
2. Chạy **read-only regression** trước; chỉ mở mutating tests ở bảng/run ID dành riêng cho thử nghiệm.
3. Kiểm CL tại local DC, schema agreement, prepared queries, paging và TLS/auth.
4. Đối soát một tập marker cũ và marker mới vừa ACK.
5. Ghi latency và error category theo coordinator/node; quan sát compaction/streaming.
6. **Dừng tiếp tục** nếu xuất hiện mismatch nghiêm trọng, không đủ quorum, error rate hoặc p99 vượt ngưỡng.

### Checkpoint C — Sau từng node tiếp theo

1. Lặp lại cùng checklist ngắn, không chờ đến hết cluster mới phát hiện lỗi.
2. Theo dõi node từng down, hinted handoff/repair, schema metadata và token placement.
3. Không nâng node kế tiếp khi điều kiện quorum/health hoặc gate trước chưa đạt.
4. Ghi chính xác thời điểm restart/version change để so incident với metrics.

### Checkpoint D — Sau nâng cấp toàn cluster

1. Đợi hệ thống về trạng thái **ổn định được định nghĩa trước**, không áp một thời gian chờ cố định cho mọi cụm.
2. Chạy đủ regression suite và đối soát dữ liệu theo manifest/CL.
3. Đo p50/p95/p99, throughput, error rate tại cùng workload, kiểm tài nguyên theo node.
4. Xác minh công cụ vận hành, backup, restore, repair schedule và cảnh báo.
5. Chỉ chốt GO khi các tiêu chí bắt buộc PASS và các gap đã có chủ sở hữu/quyết định.

## 14. Tình huống chẩn đoán thường gặp

| Triệu chứng | Giả thuyết cần phân biệt | Bằng chứng nên lấy |
| --- | --- | --- |
| Node `UN` nhưng SELECT sai | Concurrent mutation, TTL/tombstone, replica divergence, schema/codec | Manifest, CL, tracing, write history |
| Test read sau upgrade timeout | Quorum thiếu trong rolling, node chậm, disk I/O, WAN | `status`, client errors, coordinator, node metrics |
| p99 tăng, p50 không đổi | GC pause, compaction backlog, streaming, retry | p99 theo query/node, GC, I/O, retries |
| Query syntax bị từ chối | CQL feature/option không tương thích, schema chưa hội tụ | Error message, schema/query catalog, version matrix |
| Java session không khởi tạo | TLS/auth, native protocol, local DC, driver/runtime | Driver logs, endpoints, certificates |
| Paging thiếu/trùng hàng | Dataset đang biến đổi, token/page handling, query shape | Freeze dataset, paging state contract, row IDs |
| LWT kết quả khác baseline | Không tạo cùng trạng thái đầu vào, serial CL hoặc thực sự regression | `[applied]`, PK, prior state, LWT logs |
| Giá trị decimal/timestamp khác | Scale/codec/timezone hoặc nguồn bị chuẩn hóa khác | Typed readback, BigDecimal/Instant, contract |
| Remote DC không thấy write mới | LOCAL_QUORUM chỉ ACK local; WAN/replication lag | DC routing, CL, hints/repair, manifest |
| Repair quá lâu sau upgrade | Token range quá rộng, tài nguyên thiếu, version/config | repair logs, streaming, compaction, network |
| Rollback không chạy được | SSTable/schema/protocol đã thay đổi, downgrade unsupported | Upgrade path, backup, restore validation |

### Khi nào cần NO-GO ngay?

- Bản ghi đã ACK thuộc tập **bắt buộc** có `MISSING`/`MISMATCH` chưa được giải thích.
- Không đủ replica để đáp ứng CL của nghiệp vụ hoặc nhiều node mất kết nối ngoài dự kiến.
- LWT/DDL/query contract quan trọng hoạt động sai, đặc biệt liên quan dữ liệu tài chính/định danh.
- Error rate hoặc latency vượt **ngưỡng dừng đã thống nhất**, kể cả khi các request thành công vẫn nhanh.
- Backup/restore/khả năng phục hồi không đáp ứng điều kiện thay đổi.
- Phát hiện đường nâng cấp/mixed-version không được hỗ trợ hoặc kế hoạch quay lui thực tế không khả thi.

**NO-GO không đồng nghĩa lập tức “downgrade node”.** Trước hết phải giữ dữ liệu/manifest/logs, ổn định traffic và chọn biện pháp **rollback, failover, restore hoặc forward-fix** đúng khả năng tương thích.

## 15. Bài tập thực hành

**Bài 1 — Định nghĩa gate.** Một nhóm đề xuất “nâng cấp xong khi mọi node `UN`”. Hãy viết thêm tiêu chí dữ liệu, query, latency/error và restore cần có, giải thích mỗi tiêu chí bảo vệ vấn đề nào.

**Bài 2 — Manifest.** Có 100 event đã ACK trước upgrade; sau đó 97 `FOUND_MATCH`, 1 `MISSING_AT_CL`, 2 `READ_ERROR`. Bạn có thể kết luận có ba event mất vĩnh viễn không? Cần thêm bằng chứng gì?

**Bài 3 — Primary key và projection.** Với bảng `events_by_run_day`, viết SELECT đọc một event cụ thể và SELECT range 08:00–09:00 ở cùng partition, chỉ lấy `event_ts`, `event_id` và `status`. Vì sao không nên dùng `ALLOW FILTERING` hoặc full-table scan để đo regression?

**Bài 4 — TTL/DELETE.** Test một row hết TTL giữa hai lần chạy. Vì sao nó không tự là bug nâng cấp? Thiết kế nhóm test read-before-expiry, read-after-expiry và DELETE với manifest phản ánh thời điểm.

**Bài 5 — LWT.** Bạn chạy `INSERT ... IF NOT EXISTS` hai lần với cùng khóa và lần thứ hai trả `[applied]=false`. Đây có phải regression? Hãy thiết kế test độc lập cho pre/post với điều kiện ban đầu tương đương.

**Bài 6 — Tail latency.** Baseline p95=20 ms, p99=45 ms; post p95=23 ms, p99=82 ms. Nếu gate giới hạn p95×1,25 và p99×1,5 thì hạng mục nào FAIL? Vì sao cần xem thêm timeout và compaction?

**Bài 7 — Mixed versions.** RF3, `LOCAL_QUORUM`, một node dừng để nâng cấp và một node khác đã down trước đó. Quorum của partition tương ứng còn đạt không? Có được nâng node kế tiếp không?

**Bài 8 — Java Driver.** Dùng `UpgradeReadProbe` để kiểm 20 marker theo manifest ở hai thời điểm. Thu `coordinator`, `latencyMicros`, trạng thái `FOUND_MATCH/MISMATCH/MISSING/READ_ERROR`; so kết quả bằng ID, không chỉ theo số row.

**Bài 9 — Multi-DC.** Cluster có `dc_a:3` và `dc_b:3`. Write ở `dc_a` nhận ACK `LOCAL_QUORUM` trước nâng cấp; đọc ngay ở `dc_b` chưa thấy. Nêu lý do hợp lệ, cách đo replication lag và điều kiện trước failover.

**Bài 10 — Compatibility.** Dự kiến đồng thời đổi Cassandra server, JDK và Java Driver. Bạn sẽ kiểm compatibility matrix, regression tests và cách cô lập nguyên nhân latency như thế nào? Khi nào nên tách các thay đổi thành những đợt riêng?

**Bài 11 — Rollback.** Đã chạy bước chuyển định dạng SSTable được hỗ trợ sau nâng cấp; bản cũ không đọc được format mới. Vì sao không thể mặc định khởi động binary cũ trên cùng data directory? Đề xuất kế hoạch restore/forward-fix đã được kiểm thử.

**Bài 12 — Báo cáo sự cố.** Một query API trả 200 OK, nhưng một hàng có `amount` sai scale/giá trị và p99 tăng 80%. Hãy lập biên bản NO-GO có bằng chứng dữ liệu, error/latency, thời điểm và owner; không quy lỗi cho version mới trước khi loại trừ concurrent writer, codec và tải nền.

## Ghi nhớ

**Kiểm chứng nâng cấp Cassandra phải so đúng bốn mặt: dữ liệu, truy vấn, độ trễ và lỗi — ở baseline, từng checkpoint rolling và trạng thái ổn định sau nâng cấp.** Node `UN` không chứng minh dữ liệu đầy đủ; `COUNT(*)` không chứng minh từng event khớp; p50 đẹp không bù được p99 hoặc timeout; và write timeout không có nghĩa mutation chưa được áp dụng. Hãy chuẩn bị **manifest độc lập các bản ghi đã ACK**, CQL/Java regression suite theo primary key và consistency level, histogram latency/error phân loại theo query/node/DC, cùng **backup/restore và quyết định GO/NO-GO có ngưỡng từ trước**. Chỉ tiếp tục nâng cấp khi có bằng chứng đáp ứng contract; khả năng downgrade phải được xác minh theo đúng version path, không được giả định.
