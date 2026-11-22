# Diễn tập chuyển vùng và đo phạm vi dữ liệu/độ trễ bị ảnh hưởng

## Mục tiêu và phạm vi

Triển khai Apache Cassandra trên nhiều **datacenter (DC)** giúp phân bố bản sao dữ liệu và hỗ trợ vận hành khi một khu vực gặp sự cố. Tuy nhiên, có replica ở DC dự phòng **không tự đồng nghĩa** ứng dụng có thể chuyển vùng ngay mà không mất dữ liệu hoặc không tăng độ trễ. Cần phân biệt: dữ liệu đã được **ACK ở DC nguồn**, dữ liệu đã **hội tụ ở DC đích**, ứng dụng đã **định tuyến đúng coordinator**, và dịch vụ đã **phục hồi ở mức chấp nhận được**.

Bài học thuộc chương **Nhiều trung tâm dữ liệu** trong module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Nội dung sử dụng các khái niệm partition key, thiết kế bảng theo truy vấn, replication, consistency level, CQL, streaming, repair, compaction, xử lý lỗi và kết nối Java Driver. Trọng tâm là **diễn tập chuyển vùng (*regional failover drill*) và đo ảnh hưởng có bằng chứng**, không chỉ thực hiện một thao tác chuyển cấu hình.

Sau bài này, bạn có thể:

1. Xây dựng kế hoạch chuyển truy cập ứng dụng từ **DC A sang DC B** mà không nhầm định tuyến client với thao tác đổi replication factor.
2. Định nghĩa và đo **RTO** (thời gian khôi phục), **RPO** (mức dữ liệu có nguy cơ mất), cùng p95/p99 latency và tỷ lệ lỗi.
3. So sánh dữ liệu kỳ vọng với dữ liệu thực đọc được ở DC đích bằng **manifest các ghi đã nhận ACK**.
4. Phân loại **FOUND, MISSING, MISMATCH, READ_ERROR, UNKNOWN_WRITE** thay vì gộp mọi lỗi thành mất dữ liệu.
5. Chọn mức nhất quán ghi/đọc phù hợp với khả năng chịu gián đoạn WAN và yêu cầu khôi phục.
6. Thực hành CQL/Java trong lab nhiều DC, lập kế hoạch **fencing, failback, repair và backfill** sau sự cố.

> **An toàn:** chỉ cố ý cô lập mạng, dừng DC hoặc chuyển lưu lượng trong **lab/staging có quyền gây lỗi**. Trong production, thực hiện theo runbook đã duyệt, có giám sát, ngưỡng dừng, đường khôi phục và người chịu trách nhiệm. Các địa chỉ, tên DC và thời điểm trong bài chỉ để minh họa.

## 1. Kiến trúc mẫu và ba lớp chuyển vùng

Xét cluster Cassandra gồm **hai DC**, mỗi DC có ba node:

| Thành phần | DC A: `dc_a` | DC B: `dc_b` |
| --- | --- | --- |
| Node | A1, A2, A3 | B1, B2, B3 |
| RF của keyspace | 3 | 3 |
| Ứng dụng ban đầu | Nhận lưu lượng chính | Chờ, hoặc nhận lưu lượng riêng |
| Consistency mặc định minh họa | `LOCAL_QUORUM` | `LOCAL_QUORUM` sau chuyển vùng |
| Điều kiện để đạt local quorum | 2 ACK/đáp ứng trong `dc_a` | 2 ACK/đáp ứng trong `dc_b` |

Sơ đồ luồng bình thường và chuyển vùng:

~~~mermaid
flowchart LR
    U["Client / API Gateway"] --> R{"Điều phối lưu lượng"}
    R -->|Trước chuyển vùng| AA["Ứng dụng A"]
    R -. "Sau quyết định failover" .-> AB["Ứng dụng B"]
    AA --> CA["Coordinator Cassandra dc_a"]
    AB --> CB["Coordinator Cassandra dc_b"]
    CA --> RA["Replica A1, A2, A3"]
    CB --> RB["Replica B1, B2, B3"]
    RA <-. "Replication và repair xuyên DC" .-> RB
    LOG["Manifest / event log độc lập"] -. "Đối soát theo marker" .-> AB
~~~

Một cuộc diễn tập gồm ít nhất **ba lớp**:

1. **Ứng dụng và mạng:** DNS/load balancer, API gateway, endpoint, session, TLS, secrets, connection pools và các phụ thuộc bên ngoài.
2. **Cassandra:** coordinator ở DC nào, local RF/CL, dữ liệu remote đã có chưa, hints/repair và khả năng đáp ứng truy vấn.
3. **Dữ liệu nghiệp vụ:** những ghi nào đã được xác nhận trước sự cố; sau chuyển vùng, marker nào đọc được, thiếu hoặc khác giá trị; có thể tái tạo từ nguồn ngoài hay không.

Chỉ đổi DNS hoặc cấu hình Java Driver không tự truyền dữ liệu còn thiếu từ A sang B. Ngược lại, replica B có dữ liệu đầy đủ nhưng ứng dụng chưa chuyển route cũng **chưa đạt RTO**.

## 2. Xác nhận RF và phạm vi ACK trước diễn tập

Keyspace dùng `NetworkTopologyStrategy` với replication factor riêng cho từng DC:

~~~sql
CREATE KEYSPACE IF NOT EXISTS regional_dr_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc_a': 3,
    'dc_b': 3
}
AND durable_writes = true;
~~~

Kiểm tra lại trên cluster thực nghiệm:

~~~sql
SELECT keyspace_name, replication, durable_writes
FROM system_schema.keyspaces
WHERE keyspace_name = 'regional_dr_lab';

SELECT release_version, data_center, host_id
FROM system.local;
~~~

`system.local` chỉ mô tả **node đang trả lời**, không tự xác minh toàn bộ node trong cluster. Dùng `nodetool status` trên các node phù hợp để đối chiếu tên DC và trạng thái `UN` (*Up/Normal*); các giá trị `dc_a`/`dc_b` phải trùng cấu hình snitch. `IF NOT EXISTS` không sửa keyspace đã tồn tại, vì vậy đừng tự giả định RF=3+3 sau khi chạy lệnh tạo.

### So sánh consistency level trong RF 3+3

| CL | Ghi: cần phản hồi từ đâu? | Đọc: cần phản hồi từ đâu? | Ý nghĩa đối với RPO/RTO |
| --- | --- | --- | --- |
| `LOCAL_ONE` | Ít nhất 1 replica ở DC của coordinator | Ít nhất 1 replica local | Nhanh, nhưng ít bảo đảm về bản sao và dữ liệu mới nhất |
| `LOCAL_QUORUM` | Ít nhất 2/3 replica local | Quorum 2/3 local | Không đòi remote DC xác nhận trước khi trả ACK |
| `QUORUM` | 4/6 replica bất kể cách phân bố giữa hai DC | 4/6 replica | Phải liên lạc đủ nhiều replica, nhưng không bảo đảm quorum ở **mỗi** DC |
| `EACH_QUORUM` | 2/3 trong **từng DC**, tổng ít nhất 4 ACK | Không dùng cho SELECT thông thường | Cho phép thiết kế write cần xác nhận quorum ở cả hai DC, đổi lại phụ thuộc WAN |
| `ALL` | 6/6 replica | 6/6 replica | Ngưỡng mạnh nhưng khó sẵn sàng khi có node/DC lỗi |

**Quan trọng:** `LOCAL_QUORUM` ở `dc_a` **không** phải một quorum ở `dc_b`. Nếu A1 và A2 đã xác nhận ghi nhưng B1/B2/B3 chưa nhận mutation, client ở A vẫn có thể nhận thành công. Bởi vậy, khi **mất toàn bộ `dc_a` ngay sau ACK**, thao tác đọc ở `dc_b` không được bảo đảm nhìn thấy bản ghi mới nhất từ chỉ riêng CL local.

Phát biểu “RF=3+3 nên không bao giờ mất dữ liệu nếu mất một DC” là thiếu điều kiện: cần xem CL đã chọn, trạng thái replication tại thời điểm lỗi, độ bền log/đĩa, và dữ liệu có tồn tại trong nguồn độc lập hay không.

Để nhắm tới RPO chặt hơn, có thể đánh giá write `EACH_QUORUM` hoặc cơ chế xác nhận bền vững ở DC đích **trước khi trả thành công**. Đánh đổi là latency WAN và khả năng ghi giảm khi một DC không đáp ứng; kể cả vậy vẫn cần backup, kiểm tra cấu hình commit log và mô hình lỗi thực tế.

## 3. RTO, RPO và độ trễ: định nghĩa trước khi đo

### 3.1. RTO: mất bao lâu để phục vụ lại?

**Recovery Time Objective (RTO)** là thời gian ngừng dịch vụ tối đa chấp nhận theo mục tiêu. Trong một diễn tập, cần quy định chính xác mốc bắt đầu và kết thúc:

- `T_impact`: thời điểm lỗi **bắt đầu ảnh hưởng người dùng** hoặc hệ thống kiểm tra từ ngoài không thể hoàn thành yêu cầu hợp lệ.
- `T_detect`: hệ thống giám sát phát hiện sự cố.
- `T_decide`: người/hệ thống ra quyết định chuyển vùng.
- `T_route`: thay đổi routing đã có hiệu lực đến ứng dụng/coordinator tại B.
- `T_recovered`: lưu lượng thật hoặc synthetic checks ở B đạt lại tiêu chí **đọc/ghi thành công và latency** trong một cửa sổ quan sát đã định.

~~~text
RTO_observed = T_recovered - T_impact
              = thời gian phát hiện + quyết định
                + chuyển routing + ổn định/kiểm chứng
~~~

Không lấy `T_route - T_detect` rồi tuyên bố đó là RTO nếu đến lúc route đổi, ứng dụng vẫn đang lỗi hoặc độ trễ vượt SLA. Ngược lại, một cuộc diễn tập **chỉ chuyển routing không gây gián đoạn** có thể báo “không quan sát thấy downtime trong độ phân giải đo”, chứ không tự suy ra mọi thảm họa thật đều có RTO bằng 0.

### 3.2. RPO: phần dữ liệu có nguy cơ không có ở DC đích

**Recovery Point Objective (RPO)** là **mức mất dữ liệu tối đa chấp nhận**, thường biểu diễn bằng khoảng thời gian trước sự cố. Cần phân biệt **RPO mục tiêu** với **tổn thất dữ liệu quan sát được**:

1. Lấy tập thao tác **đã thực sự nhận ACK** ở DC A trước `T_impact` từ log/manifest độc lập.
2. Với từng khóa đó, đọc ở DC B **sau failover** tại CL được quy định.
3. Phân loại bản ghi thành **FOUND_MATCH**, **MISSING_AT_CL**, **MISMATCH**, **READ_ERROR**.
4. Chỉ dùng những lần đọc **thành công** để xác định dữ liệu tạm thời chưa xuất hiện; read timeout hoặc unavailable **không phải bằng chứng mất dữ liệu**.
5. Khi báo RPO theo thời gian, xác định **mốc ACK mới nhất đã được khôi phục liên tục** trong luồng sự kiện có thứ tự; báo cả khoảng ACK còn thiếu và các **lỗ hổng không liên tiếp** nếu có.

~~~text
Ví dụ (thời điểm ACK do log độc lập ghi, chỉ để minh họa):
10:00:00  event A  ACK tại dc_a  -> FOUND tại dc_b
10:00:20  event B  ACK tại dc_a  -> FOUND tại dc_b
10:00:40  event C  ACK tại dc_a  -> MISSING tại dc_b
10:00:50  event D  ACK tại dc_a  -> MISSING tại dc_b
10:01:00  T_impact

Tại lần kiểm tra này, B có thể đã thiếu C và D, dù A/B đều
có replication RF=3. Nếu luồng ACK có thứ tự và không có lỗ
hổng trước B, mốc cuối cùng đã thấy liên tục là 10:00:20;
khoảng từ đó tới sự cố là 40 giây. Báo cả 2 event đang thiếu.
~~~

**Không đánh đồng “MISSING ở thời điểm đo” với “đã mất vĩnh viễn”.** Khi WAN/DC A phục hồi, hints hoặc repair có thể bổ sung dữ liệu. Nếu DC A không bao giờ quay lại và dữ liệu đó không có nguồn khác, có thể trở thành mất dữ liệu thực sự. RPO báo cáo nên ghi rõ thời điểm, phương pháp, tập khóa và trạng thái đồng bộ; với sự kiện thiếu rải rác, một con số giây đơn lẻ không mô tả hết tác động.

Ngoài giây dữ liệu, luôn báo **số thao tác đã ACK bị thiếu**, phân nhóm theo tenant/phân vùng, và tác động nghiệp vụ. Một event thanh toán đã ACK bị thiếu có thể nghiêm trọng hơn nhiều event telemetry có thể tái tạo.

### 3.3. Độ trễ và tỷ lệ lỗi

RTO/RPO không thay thế quan sát **chất lượng dịch vụ**:

| Nhóm chỉ số | Cần đo trước, trong và sau chuyển vùng |
| --- | --- |
| API / Java | p50/p95/p99 latency đọc và ghi; throughput; số request timeout/unavailable; pool kết nối |
| Cassandra | CL thực dùng; số node `UN` theo DC; read/write timeout, unavailable, latency theo node/DC |
| Đồng bộ | hints pending/delivered/failed, repair/streaming status, backlog của nguồn sự kiện |
| Dữ liệu | ACKed expected IDs, found/missing/mismatch/read error, tenant/bucket bị ảnh hưởng |
| Hạ tầng | CPU, RAM, disk I/O, free disk, network WAN, compaction/streaming load |
| Người dùng | Tỷ lệ request thành công, khả năng ghi/đọc ở region dự phòng, cảnh báo SLO |

Không so sánh p99 trước/sau nếu tải, phân bố partition, request mix hoặc concurrency thay đổi quá nhiều. Với thời gian request, dùng **đồng hồ monotonic** của cùng tiến trình để đo duration; đồng bộ NTP/clock khi so sánh các timestamp giữa nhiều máy/DC.

## 4. Chọn loại diễn tập và tiêu chí dừng

Không nhất thiết phải làm sập cả DC ngay trong lần đầu. Nên tăng dần mức độ:

| Mức diễn tập | Tác động | Mục tiêu |
| --- | --- | --- |
| **Read-only rehearsal** | Đọc đối soát ở B khi A vẫn phục vụ chính | Đo độ đầy đủ dữ liệu remote và latency B không gây gián đoạn |
| **Routing-only failover** | Chuyển synthetic/canary traffic sang B, không gây lỗi node | Kiểm chứng driver, DNS/gateway, xác thực, secret và CL local ở B |
| **Controlled traffic switch** | Dừng nhận ghi mới ở A rồi chuyển một phần/tất cả ghi sang B | Thử fencing, thời gian cutover, client retry, backpressure |
| **DC outage drill trong lab** | Cô lập hoặc dừng toàn DC A sau khi chuẩn bị | Thử RTO/RPO khi A thật sự không phản hồi |
| **Failback rehearsal** | Khôi phục A và chuyển về sau đối soát | Kiểm chứng repair, nguồn dữ liệu và điều kiện mở ghi |

Các phép thử mạnh chỉ tiến hành khi mức trước đã đạt. Nếu thấy **thiếu dữ liệu đã ACK vượt ngưỡng**, p99 vượt SLA, disk/CPU/streaming có nguy cơ làm cluster mất ổn định hoặc việc fence A không chắc chắn, **dừng mở rộng thử nghiệm** và giữ bằng chứng để phân tích.

## 5. Fencing: chống ghi hai vùng ngoài ý muốn

Vấn đề khó hơn chuyển route là ngăn **hai phía cùng nhận ghi nghiệp vụ mâu thuẫn**. Khi WAN phân vùng, A có thể vẫn xử lý một số client trong khi B đã được kích hoạt cho những client khác. Cassandra sử dụng timestamp và reconciliation cho ghi thường; nó không tự giải quyết mọi xung đột nghiệp vụ kiểu “trừ tồn kho hai lần” hoặc “xác nhận đơn hàng ở hai vùng”.

Một quy trình chuyển vùng có kiểm soát nên có:

1. **Quyền sở hữu ghi rõ ràng:** xác định region nào được phép nhận mutation theo giai đoạn.
2. **Fencing hoặc lease ở lớp điều phối đáng tin:** bảo đảm writer cũ không còn tạo thay đổi có hiệu lực trước khi writer mới hoạt động, hoặc dùng mô hình operation ID/idempotency và xử lý xung đột phù hợp.
3. **Drain yêu cầu đang chạy:** ngừng nhận request mới vào A, chờ/ghi lại in-flight requests đã trả ACK hay chưa.
4. **Gắn operation ID ổn định:** một retry sau timeout không được vô tình biến thành giao dịch mới.
5. **Chuyển read/write routing và local DC:** ứng dụng B phải thực sự dùng coordinator trong `dc_b`.
6. **Kiểm chứng dữ liệu và dịch vụ:** chỉ tăng traffic khi tiêu chí RPO/RTO/latency được đánh giá.

> Fencing không thể mặc nhiên bảo đảm chỉ bằng một flag lưu trong cùng Cassandra cluster đang bị chia cắt. Trong bài toán yêu cầu exactly-once/ownership nghiêm ngặt, cần một control plane/lease có tính nhất quán phù hợp hoặc quy trình chặn writer cũ được kiểm chứng; nếu không thể fence chắc chắn, **không nhận ghi xung đột ở cả hai vùng**.

~~~mermaid
sequenceDiagram
    participant O as Điều phối / vận hành
    participant A as API + coordinator dc_a
    participant B as API + coordinator dc_b
    participant M as Manifest độc lập
    O->>A: Ngừng nhận ghi mới / fence writer A
    A-->>O: Thống kê in-flight, ACK/UNKNOWN
    O->>M: Chốt manifest và mốc T_impact/cutover
    O->>B: Kiểm tra B khỏe, CL và dữ liệu cần thiết
    O->>B: Cho phép writer B và chuyển traffic
    B-->>O: Synthetic checks thành công, latency đạt ngưỡng
    O->>M: Đối soát ACK ở A với đọc tại B
    O-->>O: Báo RTO, dữ liệu thiếu và quyết định tiếp tục
~~~

## 6. Chuẩn bị lab hai DC và dữ liệu kiểm chứng

### 6.1. Kiểm tra topology, cấu hình

Lab minh họa gồm `dc_a` với A1/A2/A3 và `dc_b` với B1/B2/B3. Mỗi DC có ba replica cho keyspace `regional_dr_lab`. Trước thử nghiệm:

~~~bash
# Thao tác trên các node lab phù hợp.
nodetool status
nodetool describecluster
nodetool netstats
nodetool compactionstats
~~~

Đảm bảo node cần thiết đang `UN`, schema đã hội tụ, không có repair/streaming lớn không liên quan. Dùng hai phiên `cqlsh` kết nối riêng đến một coordinator `dc_a` và một coordinator `dc_b`. Có thể dùng `SELECT data_center FROM system.local` trong mỗi phiên để kiểm tra local DC.

### 6.2. Tạo bảng có partition key rõ ràng

~~~sql
CREATE TABLE IF NOT EXISTS regional_dr_lab.events_by_run (
    run_id text,
    event_id uuid,
    marker text,
    origin_dc text,
    emitted_at timestamp,
    payload text,
    PRIMARY KEY ((run_id), event_id)
);
~~~

`run_id` là **partition key** giúp truy vấn đúng một tập event của lượt thử; `event_id` là clustering key định danh ổn định. Bài lab dùng vài chục marker trong một partition. **Không** đưa mọi sự kiện production của mọi tenant vào một partition `run_id` duy nhất: với dữ liệu thật, thiết kế bucket theo tenant/thời gian và partition key phù hợp tải, tránh partition quá rộng.

`emitted_at` là timestamp phía ứng dụng để hỗ trợ đối soát, **không phải bằng chứng commit/ACK do Cassandra phát ra**. Nhật ký ACK ở client phải lưu riêng; so sánh timestamp giữa DC cần đồng bộ đồng hồ.

### 6.3. Manifest ngoài Cassandra

Lập bảng expected trước khi tạo outage, lưu ở log hoặc nguồn tin cậy **không phụ thuộc việc đọc DC A bị lỗi**:

| run_id | event_id | marker | ACK ở A? | Thời điểm ACK | Kết quả đọc ở B |
| --- | --- | --- | --- | --- | --- |
| `dr-20261121-01` | `11111111-1111-4111-8111-111111111111` | `base-A` | Chưa thử | — | — |
| `dr-20261121-01` | `22222222-2222-4222-8222-222222222222` | `recent-B` | Chưa thử | — | — |
| `dr-20261121-01` | `33333333-3333-4333-8333-333333333333` | `recent-C` | Chưa thử | — | — |

Khi chạy thật, thay các ô “Chưa thử” bằng **ACK, UNKNOWN hoặc ERROR thực nhận**, không tự giả định tất cả thành công. Nếu có một nguồn sự kiện nghiệp vụ riêng (outbox/event log) thì lưu cả ID và trạng thái nguồn để đánh giá *completeness*, không chỉ những request đã hoàn thành tại Cassandra.

## 7. Kịch bản CQL: ghi A, đọc B và quan sát trước khi failover

### 7.1. Ghi qua coordinator tại `dc_a`

Trong phiên `cqlsh` đã kiểm tra thuộc `dc_a`:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
INSERT INTO regional_dr_lab.events_by_run
    (run_id, event_id, marker, origin_dc, emitted_at, payload)
VALUES (
    'dr-20261121-01',
    11111111-1111-4111-8111-111111111111,
    'base-A', 'dc_a', '2026-11-21T09:00:00Z', 'first-event'
);

INSERT INTO regional_dr_lab.events_by_run
    (run_id, event_id, marker, origin_dc, emitted_at, payload)
VALUES (
    'dr-20261121-01',
    22222222-2222-4222-8222-222222222222,
    'recent-B', 'dc_a', '2026-11-21T09:01:00Z', 'second-event'
);

INSERT INTO regional_dr_lab.events_by_run
    (run_id, event_id, marker, origin_dc, emitted_at, payload)
VALUES (
    'dr-20261121-01',
    33333333-3333-4333-8333-333333333333,
    'recent-C', 'dc_a', '2026-11-21T09:01:10Z', 'third-event'
);
~~~

`CONSISTENCY` là **lệnh của cqlsh**, không phải một câu CQL. Chỉ ghi ACK vào manifest nếu từng `INSERT` được client xác nhận thành công. Với RF=3 trong `dc_a`, `LOCAL_QUORUM` cần hai replica local ACK; không bắt buộc B1/B2/B3 đã nhận dữ liệu.

Trong bài lab, các giá trị `emitted_at` cố định để dễ đọc nhưng **thời điểm ACK thực tế** phải do client ghi theo lúc thực thi. Không dùng ba timestamp mẫu này như số liệu RPO đo được.

### 7.2. Đọc đối chiếu qua coordinator tại `dc_b`

Trong phiên `cqlsh` kết nối node thuộc `dc_b`:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
SELECT event_id, marker, origin_dc, emitted_at
FROM regional_dr_lab.events_by_run
WHERE run_id = 'dr-20261121-01';
~~~

Nếu cả ba marker xuất hiện ở B, đó là **quan sát dữ liệu đã tới B tại CL đã chọn**, không phải bằng chứng ba lần ghi ở A đã đợi ACK của B. Nếu thiếu một marker, ghi nhận **MISSING_AT_DC_B_AT_TIME_T** rồi điều tra: replication lag, lỗi node, khác biệt timestamp, ghi xóa khác, sai run ID hoặc lỗi kết nối.

Kiểm tra riêng một khóa giúp tránh suy luận từ số lượng hàng:

~~~sql
SELECT marker, origin_dc
FROM regional_dr_lab.events_by_run
WHERE run_id = 'dr-20261121-01'
  AND event_id = 33333333-3333-4333-8333-333333333333;
~~~

Đọc ở `LOCAL_ONE` có thể rẻ hơn nhưng có thể phản ánh một replica local chậm; khi đo hội tụ, ghi rõ CL và lựa chọn `LOCAL_QUORUM` hoặc phương pháp quản trị/repair phù hợp. **Kết nối thẳng vào B1 không ép Cassandra chỉ đọc bản sao vật lý tại B1**: B1 vẫn đóng vai coordinator và có thể hỏi các replica khác.

## 8. Diễn tập chuyển vùng theo các giai đoạn

### Giai đoạn 0 — Baseline

Đo ít nhất một khoảng thời gian đủ đại diện cho request mix của ứng dụng:

- Tỷ lệ thành công và latency p50/p95/p99 đọc/ghi ở DC A.
- Số ACK và `UNKNOWN_WRITE` trong manifest.
- Health của cả hai DC, hints, read/write timeout, free disk, compaction backlog.
- Tập marker đã ACK và trạng thái đọc được ở B.
- Sẵn sàng của các phụ thuộc: API gateway, chứng chỉ, secret, DNS, service discovery, queue, cache.

Ghi rõ mục tiêu ví dụ: **RTO không quá 5 phút, RPO mục tiêu không quá 30 giây, p95 sau chuyển vùng không quá 1,5 lần baseline**. Các ngưỡng này **chỉ là số mẫu cho bài thực hành**, không phải khuyến nghị chung; nhóm vận hành phải chọn SLA và yêu cầu dữ liệu của chính mình.

### Giai đoạn 1 — Fencing và chốt điểm quan sát

Trong lab có kiểm soát, dừng writer mới tại A, ghi lại yêu cầu đang chạy, chốt manifest, ghi `T_impact`/`T_detect` và nguồn định danh tất cả event cần đối soát. Nếu mục tiêu là test **đột ngột mất DC**, có thể không fence A được từ bên ngoài; cần thiết kế route/write ownership chống split-brain **trước** khi thử tình huống này.

Nếu một thao tác trả write timeout lúc chuyển vùng, gắn trạng thái **UNKNOWN_WRITE**. Không tự đếm nó như ACK hoặc chắc chắn chưa được ghi; khi retry qua B, cần operation ID/idempotency logic.

### Giai đoạn 2 — Chuyển coordinator/app sang B

Thay định tuyến tại gateway/orchestrator và cấu hình Java Driver của **dịch vụ B** để chọn `dc_b` làm local datacenter. Không chỉ sửa tên host rồi giữ driver local DC là `dc_a`. Kiểm tra request mới thực sự đi đến coordinator tại B, đồng thời chặn traffic viết còn lọt vào A.

Ngay sau cutover, chạy synthetic checks:

1. Đọc một marker baseline đã tồn tại.
2. Ghi **một event ID mới** ở B với `LOCAL_QUORUM` và đợi ACK.
3. Đọc lại event đó ở B với `LOCAL_QUORUM`.
4. Kiểm tra p95/p99 và lỗi trong khoảng thời gian đã định.

Chỉ đánh dấu `T_recovered` khi ứng dụng đã phục vụ được cả **đường đọc và đường ghi** theo tiêu chí đã định, không chỉ khi DNS thay đổi.

### Giai đoạn 3 — Đối soát RPO

Dùng session local ở B đọc những `event_id` đã được ACK tại A trước thời điểm ảnh hưởng, và những event mới được ACK ở B. Báo rõ:

~~~text
expected_acked_count       = số event được xác nhận từ manifest
found_match_count          = số event đọc đúng marker ở dc_b
missing_at_selected_cl     = số event đọc thành công nhưng không có hàng
mismatch_count             = số event trả marker sai
read_error_count           = số lần kiểm tra lỗi/timeout
unknown_write_count        = số write ban đầu chưa xác định kết quả
checked_at                = thời điểm/cửa sổ đối soát
consistency               = LOCAL_QUORUM trên coordinator dc_b
~~~

`FOUND_MATCH + MISSING + MISMATCH` chỉ phản ánh những khóa **đã đọc thành công**, không cộng `READ_ERROR` vào missing. Nếu thiếu marker, **giữ cả ID và thời điểm ACK** để ước lượng RPO và phạm vi dữ liệu chịu ảnh hưởng; đừng chỉ trả tổng `COUNT(*)` toàn bảng.

### Giai đoạn 4 — Tình huống DC A thật sự down (chỉ lab)

Sau khi đã tập routing/fencing, có thể diễn tập một failure domain hoàn chỉnh bằng cách làm **các node DC A trong lab** không thể phục vụ request, dưới sự điều khiển của người vận hành. Không cần cố tình phá dữ liệu/ổ đĩa; có thể dùng mô phỏng mất đường kết nối hoặc tắt service/container trong lab.

Theo dõi:

- B còn đáp ứng `LOCAL_QUORUM` cho RF3 của chính B không?
- Các write mới tại B có ACK khi A không phản hồi không?
- Có request bị gửi nhầm đến A do pool/route chưa cập nhật không?
- Có event từng ACK ở A mà B chưa nhận không?
- Khi A không thể phục hồi, có nguồn log/backup đáng tin để backfill không?

Với `LOCAL_QUORUM` ở B, **ACK từ A không cần thiết** để B trả lời; nhưng nếu dữ liệu cũ chỉ có ở A, B không tự tái tạo chúng. Không ép `QUORUM` hay `ALL` để “kiểm chứng” ngay trong khi A down: các mức này có thể tăng lỗi/unavailability và không giải quyết dữ liệu vắng mặt.

## 9. Java Driver 4.x: tách session theo DC và đo kết quả

Ứng dụng Java sử dụng `CqlSession` với **local datacenter tường minh**. Ví dụ dưới dùng Java 17 và Apache Cassandra Java Driver 4.x. Các IP chỉ là ví dụ private của lab; cấu hình thật cần TLS, authentication, contact points dự phòng, load balancing và timeouts phù hợp.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.net.InetSocketAddress;
import java.time.Instant;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

public final class MultiDcFailoverProbe {
    public record Event(String runId, UUID eventId,
                        String marker, String originDc, Instant emittedAt) {}
    public enum WriteState { ACKNOWLEDGED, UNKNOWN_WRITE }
    public enum ReadState { FOUND_MATCH, MISSING, MISMATCH, READ_ERROR }
    public record ReadSample(ReadState state, long latencyMillis) {}

    private final CqlSession session;
    private final PreparedStatement put;
    private final PreparedStatement get;

    public static CqlSession connect(String ip, String localDc) {
        return CqlSession.builder()
            .addContactPoint(new InetSocketAddress(ip, 9042))
            .withLocalDatacenter(localDc)
            .withKeyspace("regional_dr_lab")
            .build();
    }

    public MultiDcFailoverProbe(CqlSession session) {
        this.session = session;
        this.put = session.prepare(
            "INSERT INTO regional_dr_lab.events_by_run " +
            "(run_id, event_id, marker, origin_dc, emitted_at, payload) " +
            "VALUES (?, ?, ?, ?, ?, ?)");
        this.get = session.prepare(
            "SELECT marker FROM regional_dr_lab.events_by_run " +
            "WHERE run_id = ? AND event_id = ?");
    }

    public WriteState writeAtLocalQuorum(Event event, String payload) {
        BoundStatement statement = put.bind(
                event.runId(), event.eventId(), event.marker(),
                event.originDc(), event.emittedAt(), payload)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotence(false);
        try {
            session.execute(statement);
            System.out.printf("ACK run=%s id=%s at=%s%n",
                event.runId(), event.eventId(), Instant.now());
            return WriteState.ACKNOWLEDGED;
        } catch (RuntimeException error) {
            System.err.printf("UNKNOWN_WRITE run=%s id=%s error=%s%n",
                event.runId(), event.eventId(),
                error.getClass().getSimpleName());
            return WriteState.UNKNOWN_WRITE;
        }
    }

    public ReadSample verifyAtLocalQuorum(Event expected) {
        long started = System.nanoTime();
        try {
            Row row = session.execute(get.bind(
                    expected.runId(), expected.eventId())
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM))
                .one();

            ReadState state = row == null
                ? ReadState.MISSING
                : expected.marker().equals(row.getString("marker"))
                    ? ReadState.FOUND_MATCH : ReadState.MISMATCH;

            return new ReadSample(state, elapsedMillis(started));
        } catch (RuntimeException error) {
            System.err.printf("READ_ERROR event=%s error=%s%n",
                expected.eventId(), error.getClass().getSimpleName());
            return new ReadSample(ReadState.READ_ERROR, elapsedMillis(started));
        }
    }

    private static long elapsedMillis(long started) {
        return TimeUnit.NANOSECONDS.toMillis(
            System.nanoTime() - started);
    }
}
~~~

Minh họa hai session phục vụ hai local DC:

~~~java
try (CqlSession a = MultiDcFailoverProbe.connect("10.10.0.11", "dc_a");
     CqlSession b = MultiDcFailoverProbe.connect("10.20.0.11", "dc_b")) {

    MultiDcFailoverProbe writerA = new MultiDcFailoverProbe(a);
    MultiDcFailoverProbe readerB = new MultiDcFailoverProbe(b);

    var event = new MultiDcFailoverProbe.Event(
        "dr-java-01",
        UUID.fromString("44444444-4444-4444-8444-444444444444"),
        "check-001",
        "dc_a",
        Instant.now()
    );

    var ack = writerA.writeAtLocalQuorum(event, "lab-payload");
    var observation = readerB.verifyAtLocalQuorum(event);
    System.out.printf("write=%s remoteRead=%s latencyMs=%d%n",
        ack, observation.state(), observation.latencyMillis());
}
~~~

**Lưu ý về đoạn mã:**

- `withLocalDatacenter("dc_a")` hoặc `"dc_b"` điều khiển load balancing/nhận biết local DC; việc kết nối tới một IP ngẫu nhiên của DC A rồi kỳ vọng `LOCAL_QUORUM` tính ở B là sai.
- `CqlSession` phải **tái sử dụng** trong service thật. Không mở/đóng session trên mỗi request; ví dụ chỉ mô phỏng hai cấu hình DC trong một chương trình ngắn.
- `writeAtLocalQuorum` chỉ trả `ACKNOWLEDGED` khi nhận thành công. `UNKNOWN_WRITE` phải được lưu vào manifest và xử lý theo chính sách idempotency, không suy đoán chưa ghi.
- `verifyAtLocalQuorum` trả `MISSING` khi query thành công nhưng không có hàng; với timeout trả `READ_ERROR`, **không đánh dấu mất dữ liệu**.
- `latencyMillis` đo duration theo đồng hồ monotonic nhưng **một mẫu không phải p95/p99**; cần nhiều phép đo theo cùng tải và nhiều mốc thời gian.
- `origin_dc` chỉ là metadata do client gửi, không chứng minh coordinator thực tế ở đúng DC. Cần xác minh topology/driver metrics và routing.
- Manifest phải lưu trên một hệ thống **độc lập đủ tin cậy**; ghi nhật ký console như ví dụ không phải giải pháp audit bền vững.

## 10. Báo cáo mẫu về RTO, RPO và vùng ảnh hưởng

Giả sử mục tiêu của lab là RTO tối đa 5 phút, RPO tối đa 30 giây và latency p95 sau chuyển vùng không vượt 1,5 lần baseline. **Các số dưới đây là ví dụ tính toán giả định, không phải kết quả chạy Cassandra thật.**

| Quan sát giả định | Giá trị |
| --- | --- |
| `T_impact` | 10:00:00 |
| `T_detect` | 10:00:20 |
| `T_route` | 10:01:10 |
| `T_recovered` | 10:02:00 |
| **RTO quan sát** | **120 giây** |
| Số write ACK trước lỗi trong manifest | 1.000 |
| Đọc tại B: found match | 995 |
| Đọc tại B: missing | 3 |
| Đọc tại B: mismatch | 0 |
| Đọc tại B: read error | 2 |
| Write chưa có kết quả ACK trước lỗi | 4, **không gộp** vào 1.000 |
| p95 read trước / sau | 18 ms / 31 ms |

Cách diễn giải:

- **RTO 120 giây**: đạt mục tiêu 5 phút nếu cách xác định `T_impact` và `T_recovered` đã được thống nhất.
- **Độ trễ p95 từ 18 lên 31 ms**: tăng khoảng 1,72 lần, nên **không đạt** ngưỡng thử nghiệm 1,5 lần; phải xem tải/cold cache và hiệu năng B.
- **3 MISSING**: dữ liệu từng ACK không thấy tại B ở CL/thời điểm kiểm tra, cần xem ID/ACK timestamp, replication lag, repair và nguồn khôi phục. Chưa được tự ghi “mất vĩnh viễn”.
- **2 READ_ERROR**: không kết luận đủ/thiếu; cần retry xác minh có kiểm soát sau khi ổn định.
- **4 UNKNOWN_WRITE**: không cộng là ghi đã ACK hoặc bị mất; tra operation ID, nguồn sự kiện và retry có kiểm soát.
- **RPO theo giây**: chưa thể tính từ các số tổng hợp trên vì thiếu **mốc ACK và thứ tự** của ba event MISSING. Phải mở manifest cụ thể để xác định khoảng mất/thiếu dữ liệu và các lỗ hổng.

Một báo cáo đầy đủ phải bổ sung: DC nào lỗi, service/tenant nào chịu ảnh hưởng, mốc phục hồi, các khóa thiếu, RPO đo được theo từng luồng nếu có, nguồn backfill, dữ liệu còn chưa kiểm chứng và bài học cải tiến runbook.

## 11. Failback và phục hồi dữ liệu sau diễn tập

**Failback** (chuyển lưu lượng từ B về A) là một thao tác mới, không phải đơn giản đảo ngược DNS sau khi A có trạng thái `UN`. Trong thời gian A ngừng hoạt động, B có thể đã nhận rất nhiều write mới. A có thể còn thiếu các mutation đó.

Quy trình an toàn:

1. **Xác nhận A đã phục hồi thật:** node/replica khỏe, disk và commit log bình thường, đường mạng WAN ổn định; đừng chỉ nhìn một node `UN`.
2. **Đối soát cả hai chiều:** event đã ACK trước failover ở A có tại B? Event đã ACK trong thời gian B phục vụ có tại A?
3. **Xử lý repair/hints/streaming:** theo dõi phạm vi, lỗi, độ trễ và tài nguyên; không dùng một phép `SELECT` hoặc `nodetool status` như chứng cứ mọi replica đã hội tụ.
4. **Kiểm tra tombstone/TTL:** nếu một DC vắng mặt quá lâu, đặc biệt vượt `gc_grace_seconds` và tombstone có thể đã purge, **không cho replica stale tái gia nhập tùy tiện**, tránh zombie data. Cân nhắc rebuild/replace theo quy trình phiên bản.
5. **Backfill thiếu dữ liệu từ nguồn đáng tin:** chỉ khi xác định event ở nguồn nghiệp vụ nhưng vắng tại Cassandra; dùng ID ổn định và cơ chế tránh ghi đè dữ liệu mới.
6. **Fencing writer B và chuyển quyền lại:** ngừng ghi mới tại B theo quy trình, đợi in-flight, rồi chuyển request sang A.
7. **Synthetic checks và theo dõi:** ghi ACK và đọc marker ở A, p95/p99, error rate, lag và trạng thái hệ thống sau chuyển.

`nodetool repair` có thể tốn CPU/disk/network và cần chạy với phạm vi token range đúng phiên bản/topology. **Repair không tái tạo được dữ liệu không tồn tại trên bất kỳ replica còn tin cậy nào**; cũng không sửa được lỗi một external event log bị thiếu. Đừng chạy hàng loạt full repair trong giờ cao điểm chỉ để hoàn thành checklist.

### Những lỗi phổ biến cần tránh

| Hiểu sai | Cách hiểu đúng |
| --- | --- |
| “RF=3 ở mỗi DC nên failover luôn có RPO=0.” | `LOCAL_QUORUM` tại A không cần ACK ở B; cần đo dữ liệu thực có tại B. |
| “Chỉ cần driver chuyển địa chỉ IP sang B.” | Phải bảo đảm **local DC, coordinator routing, app/gateway, auth** và đường đọc/ghi đúng. |
| “DNS đã đổi nghĩa là RTO hoàn thành.” | RTO kết thúc khi dịch vụ thực sự đáp ứng tiêu chí phục hồi đã định. |
| “Read timeout ở B chứng minh event đã mất.” | Đây là **READ_ERROR**, chưa phải MISSING. |
| “`COUNT(*)` hai DC bằng nhau nghĩa là không thiếu dữ liệu.” | Count không chỉ ra ID bị thiếu/nhầm; quét toàn bảng còn tốn tài nguyên. |
| “Thấy marker ở B nghĩa là write A đã chờ ACK B.” | Remote có thể nhận dữ liệu sau hoặc trước ACK local; điều kiện ACK vẫn tính ở A. |
| “A quay lại `UN` thì lập tức failback.” | Cần đối soát dữ liệu B→A, repair/hints/TTL và fencing writer trước. |
| “`QUORUM` tổng RF6 bảo đảm quorum ở cả hai DC.” | `QUORUM` có thể đạt 4/6 mà không đủ 2 ACK tại từng DC; `EACH_QUORUM` có điều kiện khác. |

## 12. Bài thực hành

**Bài 1 — Tính phạm vi ACK.** Cluster có `dc_a:3` và `dc_b:3`. A thực hiện `INSERT LOCAL_QUORUM` nhận ACK từ A1/A2. Có thể kết luận gì về B1/B2/B3? Nếu muốn write phải nhận hai ACK ở mỗi DC, CL nào cần xem xét và đánh đổi về WAN là gì?

**Bài 2 — Runbook chuyển vùng.** Vẽ timeline `T_impact`, `T_detect`, `T_decide`, `T_route`, `T_recovered` cho một ca giả định. Liệt kê cách xác minh writer A đã bị fence trước khi B nhận ghi và tính RTO quan sát.

**Bài 3 — Phân tích manifest.** Một luồng có 200 event đã ACK ở A, B đọc được 197 event đúng marker, một event missing và hai read error. Tính số event **được xác minh đúng** và giải thích vì sao không thể tuyên bố có ba event mất vĩnh viễn hoặc suy ra RPO theo giây chỉ từ các số đó.

**Bài 4 — Thử routing.** Dùng hai `CqlSession` Java với `withLocalDatacenter("dc_a")` và `"dc_b"`. Ghi một event ở A, đọc cùng event tại B, lưu latency và kết quả `FOUND_MATCH/MISSING/READ_ERROR`. Tại sao lần đọc remote thấy dữ liệu không thay đổi định nghĩa của write ACK local?

**Bài 5 — WAN phân vùng.** Giả sử A và B đều còn ba replica local khỏe nhưng không liên lạc qua WAN. `LOCAL_QUORUM` ở B có thể tiếp tục phục vụ các ghi mới không? Điều gì xảy ra nếu cả hai vùng đồng thời ghi trái ngược lên cùng primary key? Đề xuất cơ chế fencing và xử lý xung đột.

**Bài 6 — Đo p95/p99.** Baseline p95 đọc 20 ms, sau chuyển vùng p95 48 ms trong cùng request mix; p99 tăng mạnh do compaction và cold cache. Hãy chọn tiêu chí kết luận dịch vụ đã hồi phục: chỉ “đọc được” hay phải đạt SLO độ trễ, throughput và tỷ lệ lỗi?

**Bài 7 — Failback an toàn.** DC A trở lại sau outage dài, có thể đã bỏ lỡ nhiều `DELETE` và một phần tombstone đã hết grace. Vì sao không mở writer A ngay? Trình bày kế hoạch kiểm tra, rebuild/repair và đối soát dữ liệu trước failback.

## Ghi nhớ

**Diễn tập chuyển vùng là bài kiểm tra đồng thời tính sẵn sàng, định tuyến và tính đầy đủ dữ liệu.** Với `LOCAL_ONE` hoặc `LOCAL_QUORUM`, ACK được tính tại DC của coordinator; một ghi đã được ACK ở DC A không bắt buộc có mặt tức thời ở DC B. Vì vậy phải đặt mục tiêu **RTO/RPO**, lưu manifest các event đã ACK ở nguồn độc lập, đo dữ liệu hiện có tại DC đích theo khóa/CL cụ thể, phân biệt missing với read error, theo dõi p95/p99 và áp dụng **fencing + đối soát + repair/backfill** trước khi cho ghi hai chiều hoặc failback.
