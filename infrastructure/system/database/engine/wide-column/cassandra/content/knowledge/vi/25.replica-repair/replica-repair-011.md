# Subrange repair và chia công việc thành các phần nhỏ

## 1. Bài toán: repair một vùng dữ liệu lớn mà không làm quá tải cluster

Trong **Apache Cassandra**, cùng một partition thường được lưu trên nhiều replica. Nếu một replica từng offline, mạng chập chờn hoặc hinted handoff không chuyển hết mutation, các replica có thể tạm giữ những phiên bản dữ liệu khác nhau. **Anti-entropy repair** giúp so sánh và đồng bộ dữ liệu trên các replica cho những vùng dữ liệu được chỉ định.

Khi keyspace có hàng terabyte dữ liệu, việc sửa một phạm vi quá lớn trong một lượt có thể gây áp lực lên CPU, ổ đĩa, mạng, lưu trữ tạm và thời gian chạy. Nếu tác vụ thất bại gần cuối, người vận hành còn khó xác định **vùng nào đã xử lý xong**. Vì vậy, một cách tổ chức phổ biến là **subrange repair**: chia vùng token cần repair thành các **khoảng nhỏ, không bỏ sót**, rồi lần lượt sửa, ghi nhận và kiểm chứng từng phần.

Bài học này trả lời bốn câu hỏi:

1. **Subrange repair** là gì, khác gì với sửa toàn bộ phạm vi hoặc chỉ repair primary ranges?
2. Làm sao chia **token ring** thành các khoảng con để không bỏ sót hoặc làm nhiều lần không chủ ý?
3. Dùng `nodetool repair -st ... -et ...` và quản lý trạng thái thành công/thất bại như thế nào?
4. Vì sao chọn phần nhỏ **chưa đủ** để bảo đảm hiệu năng, tính đúng đắn và an toàn tombstone?

**Mục tiêu học tập:** có thể lập một kế hoạch repair theo token range, hiểu phạm vi replica/DC, theo dõi tiến độ, retry có kiểm soát, giữ lịch repair an toàn với TTL và `gc_grace_seconds`, đồng thời phân biệt repair với đọc ở quorum, compaction và backup.

**Phạm vi:** Cassandra sử dụng các full replica thông thường, thường với `Murmur3Partitioner`. Lệnh và chế độ mặc định của `nodetool repair` phụ thuộc phiên bản; các ví dụ là bài lab, không phải lệnh khuyến nghị chạy nguyên xi trên production.

## 2. Vì sao repair cần thiết dù ứng dụng dùng QUORUM?

Giả sử keyspace có replication factor **RF = 3** trong data center `dc1`; partition `(sensor-7, 2026-11-21)` được lưu ở N1, N2 và N3.

~~~mermaid
sequenceDiagram
    participant App as Java client
    participant Coord as Coordinator
    participant N1 as Replica N1
    participant N2 as Replica N2
    participant N3 as Replica N3 (offline)
    App->>Coord: INSERT ở LOCAL_QUORUM
    Coord->>N1: Mutation t2
    Coord->>N2: Mutation t2
    Coord-xN3: Mutation không đến
    N1-->>Coord: ACK
    N2-->>Coord: ACK
    Coord-->>App: Success (2/3)
    Note over N3: Vẫn có dữ liệu cũ t1
    Note over N1,N3: Anti-entropy repair về sau đối chiếu vùng token
~~~

Với RF = 3, write `LOCAL_QUORUM` chỉ cần **hai** ACK tại DC cục bộ. Read `LOCAL_QUORUM` cũng cần hai phản hồi; các tập quorum trong **cùng DC và cùng replica set** phải giao nhau. Tuy nhiên:

- Replica N3 vẫn có thể chưa được cập nhật.
- Read repair chỉ có thể xử lý dữ liệu mà đường đọc thực sự chạm tới, theo cơ chế và phiên bản đang dùng.
- Partition ít được đọc, range chứa tombstone hoặc một DC khác chưa nhận mutation vẫn có thể lệch.

**Anti-entropy repair** so sánh dữ liệu trong những token ranges thuộc các replica tham gia, rồi truyền các khác biệt cần thiết. Nó không chỉ sửa partition mà ứng dụng đang truy vấn. Cơ chế so sánh có thể sử dụng Merkle tree và các pha xác thực/streaming dữ liệu, nhưng chi tiết thực thi tùy phiên bản và lựa chọn repair.

> Quorum giúp một thao tác đọc/ghi đạt ngưỡng nhất quán đã yêu cầu; repair giúp **những bản sao chưa bắt kịp có cơ hội hội tụ** trên phạm vi được sửa. Hai chức năng bổ sung cho nhau.

## 3. Token range là đơn vị chia việc, không phải khoảng giá trị nghiệp vụ

### 3.1. Từ partition key đến token

Một bảng time series có thể dùng:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry_lab.readings_by_sensor_day (
  sensor_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  reading decimal,
  PRIMARY KEY ((sensor_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

`(sensor_id, event_day)` là **partition key kép**. Cassandra hash toàn bộ partition key thành một **token**, rồi dựa vào token, replication strategy và topology để chọn các replica lưu partition. Các hàng thuộc partition đó, dù có `event_time` khác nhau, vẫn nằm trong cùng **token range**.

**Không có quan hệ thứ tự trực tiếp** giữa token với ngày, tên cảm biến hay thứ tự `event_time`. Vì thế repair khoảng token `(a, b]` **không có nghĩa** sửa “các ngày từ a đến b”, và không thể chọn `a, b` bằng khoảng thời gian kinh doanh.

### 3.2. Minh họa các khoảng trên vòng

Mô hình vòng token thường dùng khoảng **mở bên trái, đóng bên phải**:

~~~text
           token A           token B           token C           token D
         ──────┬────────────────┬────────────────┬────────────────┬───── ...
                (A, B]           (B, C]           (C, D]

Một partition có token chính xác B thuộc (A, B], không thuộc (B, C].
~~~

Với `Murmur3Partitioner`, miền token dựa trên số nguyên có dấu 64-bit và vòng **quay lại đầu** tại ranh giới của miền. Cần đặc biệt cẩn thận với đoạn vòng qua token cực đại/cực tiểu; không được mặc định mọi khoảng đều có `start < end` theo so sánh số thông thường.

Khi dùng nhiều virtual nodes (**vnodes**), một Cassandra node có thể sở hữu **nhiều dải token không liên tiếp**. Một node có 16 token không có nghĩa nó là 16 replica của cùng partition; số full replica do RF và topology quyết định.

### 3.3. Subrange, primary range và replica set khác nhau

| Khái niệm | Ý nghĩa | Điểm phải chú ý |
| --- | --- | --- |
| **Token range** | Khoảng vị trí token trên vòng | Có thể chứa rất nhiều partition. |
| **Subrange repair** | Repair phạm vi token do người vận hành chỉ rõ bằng start/end | Có thể là một phần của vùng lớn hơn; cần tự quản lý việc bao phủ toàn bộ. |
| **Primary range** | Vùng token mà node là chủ sở hữu chính theo quy tắc ring | `-pr` là lựa chọn phạm vi repair riêng; không phải từ đồng nghĩa của `-st/-et`. |
| **Replica set** | Các node giữ bản sao của partition trong một đoạn token | Có thể thay đổi khi vượt ranh giới token hoặc topology thay đổi. |
| **Repair coordinator** | Node khởi phát/điều phối phiên repair | Không đồng nghĩa với coordinator của mọi truy vấn ứng dụng. |

Đặc biệt, chạy lệnh repair trên một node **không tự chứng minh rằng mọi token range của toàn cluster đã được sửa**. Phạm vi thực tế phụ thuộc node khởi phát, token ownership, các tùy chọn DC/hosts/primary range và phiên bản. Muốn có kế hoạch hoàn chỉnh, phải xác định **tập range cần bao phủ cùng các replica tham gia đối chiếu**.

## 4. Cách subrange repair vận hành

### 4.1. Pha xử lý logic

~~~mermaid
flowchart TD
    A["Xác định token ranges cần repair"] --> B["Chọn một subrange (start, end]"]
    B --> C["Chọn repair coordinator / participant replicas"]
    C --> D["Đối chiếu dữ liệu của subrange"]
    D --> E{"Có phần dữ liệu khác nhau?"}
    E -->|Có| F["Đồng bộ các phần thiếu / khác"]
    E -->|Không| G["Không cần truyền dữ liệu khác biệt"]
    F --> H["Xác nhận phiên repair hoàn tất"]
    G --> H
    H --> I["Lưu kết quả và chuyển sang subrange tiếp theo"]
~~~

Đây là luồng ý nghĩa, không phải bản mô tả chính xác mọi RPC nội bộ. Validation thường cần quét dữ liệu liên quan trên các replica, tạo đối chiếu và có thể phải streaming giữa các node. **Không có dữ liệu khác nhau** vẫn có chi phí kiểm tra. Nếu repair thất bại giữa chừng, không thể tự gán toàn bộ subrange là `DONE`.

### 4.2. Tại sao nên chia nhỏ?

| Lợi ích | Giải thích thực tế |
| --- | --- |
| **Giới hạn phạm vi mỗi lần chạy** | Mỗi đơn vị công việc có thể giám sát, dừng hoặc thử lại độc lập. |
| **Dễ checkpoint** | Biết subrange nào hoàn tất, subrange nào cần retry. |
| **Kiểm soát cạnh tranh tài nguyên** | Có thể hạn chế số repair đồng thời và tránh tranh tài nguyên với read/write. |
| **Tối ưu kế hoạch thời gian** | Phân bố subrange qua khung bảo trì, ưu tiên vùng có nguy cơ tombstone. |
| **Khoanh vùng lỗi** | Giảm phạm vi cần điều tra khi timeout, node down hoặc streaming thất bại. |

**Giới hạn:** chia càng nhỏ càng tạo nhiều phiên/overhead lập lịch, metadata, validation và giao tiếp; nếu mỗi subrange quá nhỏ, chi phí cố định có thể lớn hơn lợi ích. **Token range nhỏ về mặt số học không nhất thiết ít dữ liệu**: partition phân phối không đều, kích thước dữ liệu khác nhau, tombstone và hot partition đều ảnh hưởng. Một partition khổng lồ **không thể bị cắt đôi chỉ bằng việc chia token range**, vì cả partition có cùng token.

## 5. Lập kế hoạch chia các phần không bị hở

### 5.1. Dùng các ranh giới chung

Giả sử chỉ cần sửa đoạn token từ `A` tới `D` theo chiều tăng và nó **không quấn qua cuối vòng**. Chọn các điểm cắt `B` và `C` nằm bên trong:

~~~text
Mục tiêu cần repair:       (A, D]

Subrange 1:                (A, B]
Subrange 2:                (B, C]
Subrange 3:                (C, D]

Hợp ba subrange:           (A, D]
Không hở tại B, C; không đếm trùng chính các điểm biên.
~~~

Trong thực tế, chuẩn khoảng mà `nodetool` áp dụng phải được kiểm tra theo phiên bản/partitioner, và phải chú ý đặc biệt ranh giới vòng. **Không nên sửa mù một dãy số từ minimum đến maximum rồi mặc định đã bao phủ toàn cluster** nếu chưa xác minh phạm vi ownership và ý nghĩa điểm wrap.

### 5.2. Ví dụ hai phần trên một đoạn con của Murmur3 token space

Chọn hai phần minh họa, **không đại diện toàn bộ vòng**:

| ID công việc | Khoảng token dự kiến | Mức độ hoàn thành |
| --- | --- | --- |
| `repair-A` | `(-4611686018427387904, 0]` | Cần hoàn thành và ghi log riêng. |
| `repair-B` | `(0, 4611686018427387903]` | Cần hoàn thành và ghi log riêng. |

Hai công việc kết hợp thành `(-4611686018427387904, 4611686018427387903]` **chứ không phải toàn bộ miền Murmur3**. Đây chỉ là ví dụ an toàn để làm rõ ranh giới; khi lập lịch thật cần dùng token map/ownership thực tế và kế hoạch bao phủ.

### 5.3. Khối lượng không bằng bề rộng token

Một bản kế hoạch tối thiểu cần ước lượng:

- Số byte/SSTable, số partition và tombstone ở phạm vi liên quan nếu có thể quan sát.
- Số replica tham gia, rack/DC, băng thông truyền dữ liệu và áp lực streaming.
- Mức giao nhau giữa các subrange và những tác vụ repair đang chạy.
- Khung thời gian chịu tải, năng lực CPU/I/O và dung lượng dự phòng.

Thay vì cắt thành 100 khoảng bằng nhau rồi tin rằng mỗi phần chạy bằng nhau, nên **đo thời gian và lượng dữ liệu thực tế**, sau đó điều chỉnh ranh giới/độ song song ở vòng vận hành kế tiếp. Việc thiết kế partition key theo truy vấn, tránh partition quá lớn và cấu hình compaction/TTL hợp lý góp phần làm công việc repair dễ dự đoán hơn.

## 6. Thực hành `nodetool repair -st/-et`

### 6.1. Kiểm tra môi trường trước

Trên node trong môi trường lab/staging:

~~~bash
nodetool status
nodetool ring
nodetool help repair
~~~

`status` giúp xem node/DC/rack và tình trạng hoạt động; `ring` giúp nhìn token ownership; `help repair` giúp **xác nhận cú pháp của chính phiên bản** đang chạy. Không dựa vào một ví dụ trên internet để áp các tùy chọn của một phiên bản khác.

Ví dụ dùng keyspace/table ở mục 3, trên node được chọn phù hợp làm repair coordinator:

~~~bash
# Chỉ repair phần token thứ nhất trên node được chỉ định.
nodetool repair -st -4611686018427387904 -et 0 telemetry_lab readings_by_sensor_day

# Sau khi phần thứ nhất thành công và được ghi nhận,
# repair phần token thứ hai trong ví dụ.
nodetool repair -st 0 -et 4611686018427387903 telemetry_lab readings_by_sensor_day
~~~

**Ý nghĩa:** `-st` (*start token*) và `-et` (*end token*) định nghĩa phạm vi token cần xem xét. Phần sau là `keyspace` và `table`. Những con số trên là ranh giới minh họa cho **hai subrange**, không phải giá trị nên dùng mặc định.

Các lệnh này **không bảo đảm** hai điều sau nếu không kiểm chứng:

1. Node khởi chạy thực sự tham gia/bao phủ đúng tất cả token ranges cần sửa theo topology.
2. Cả cluster, mọi DC và mọi bảng đã được repair — phạm vi tác vụ phụ thuộc các tùy chọn, các participant replicas và lịch repair tổng thể.

Trên production, hãy dùng runbook được phê duyệt, giới hạn đồng thời, lựa chọn coordinator đúng, và xác minh chế độ **incremental/full repair** cùng tập replica/DC tham gia. Không tự ghép `-pr`, `-local`, `-dc`, `-full` hay các cờ khác khi chưa kiểm tra tương tác của chúng trên phiên bản đang chạy.

### 6.2. Full repair, incremental repair và phạm vi

| Phân biệt | Ý nghĩa khái quát | Nguy cơ khi nhầm |
| --- | --- | --- |
| **Full repair** | Xem xét phạm vi dữ liệu cần repair không chỉ phần chưa được đánh dấu repaired | Chi phí lớn hơn; cần lịch phù hợp và hiểu trạng thái repaired/unrepaired. |
| **Incremental repair** | Tận dụng tracking/trạng thái repaired của SSTable theo cơ chế phiên bản | Không thể coi mọi lần chạy nhỏ là tương đương full repair. |
| **`-pr` (primary ranges)** | Giới hạn việc repair theo phạm vi primary ranges của node | Không tương đương chia subrange tùy ý bằng `-st/-et`. |
| **Giới hạn DC/host** | Chọn tập replica tham gia theo yêu cầu topology | Có thể bỏ qua replica cần đồng bộ nếu chỉ sửa một phần phạm vi. |

Ở một số phiên bản, incremental repair có các bước xử lý SSTable như **anti-compaction** và duy trì trạng thái repaired. Thay đổi chế độ, dừng giữa chừng hoặc chạy nhiều lượt chồng nhau cần thận trọng vì có thể tăng I/O và phát sinh trạng thái repair phức tạp. Bài này **không khẳng định chế độ mặc định** của `nodetool repair`; điều đó phải kiểm tra từ bản Cassandra thực tế.

### 6.3. Quan sát sau lệnh

~~~bash
nodetool netstats
nodetool compactionstats
nodetool tpstats
nodetool status
~~~

- **`netstats`**: kiểm tra streaming hoặc truyền dữ liệu đang xảy ra, khi phiên bản hiển thị thông tin phù hợp.
- **`compactionstats`**: xem công việc compaction/validation liên quan và backlog.
- **`tpstats`**: quan sát một số thread pools/pending tasks để phát hiện áp lực thực thi.
- **`status`**: xác nhận không có node tham gia đột ngột rơi vào trạng thái down/transition.

Tùy phiên bản, kết quả repair chi tiết còn nằm trong **log của node, log tác vụ và hệ thống metrics/monitoring**. Một lệnh chạy xong nhưng không có xác nhận đủ phạm vi **không nên tự động được coi là “toàn cluster repaired”**.

## 7. Thiết kế scheduler và checkpoint theo subrange

Subrange repair có giá trị nhất khi được vận hành như **một danh sách công việc có trạng thái**, không phải một chuỗi lệnh gõ thủ công mà không lưu kết quả.

### 7.1. Một bản ghi trạng thái tối thiểu

~~~text
repair_run_id     : repair-2026-11-21-dc1-01
keyspace          : telemetry_lab
table             : readings_by_sensor_day
partitioner       : Murmur3Partitioner
topology_snapshot : version-of-token-map-at-planning-time
repair_mode       : confirmed-full-or-incremental-mode
scope             : participant DCs/nodes according to runbook

task_id    start_token             end_token             state
--------   ----------------------  --------------------  ---------
range-A    -4611686018427387904    0                     DONE
range-B    0                       4611686018427387903   PENDING

Mỗi task: coordinator_node, started_at, finished_at, attempt_count,
         tool_exit_status, repair_session_id/log_reference, failure_reason.
~~~

Các trường trên là **mô hình checkpoint của hệ điều phối**, không phải schema được Cassandra tự tạo. Vùng `DONE` phải có bằng chứng phiên repair **thành công cho phạm vi dự kiến**; `RUNNING` hoặc `FAILED` không được coi là hoàn tất.

### 7.2. State machine đề xuất

~~~mermaid
flowchart TD
    P["PENDING"] --> R["RUNNING"]
    R -->|Repair hoàn tất và kiểm tra OK| D["DONE"]
    R -->|Timeout / failed / node down| F["FAILED"]
    F --> I["Điều tra nguyên nhân"]
    I -->|Topology còn hợp lệ, retry an toàn| P
    I -->|Topology/ownership thay đổi| X["REPLAN toàn bộ phạm vi liên quan"]
    D --> V["Kiểm tra coverage của repair run"]
~~~

**Quy tắc quan trọng:**

1. **Chạy có giới hạn đồng thời.** Ưu tiên nối tiếp trong lab; trên production chỉ tăng concurrency khi đã đo khả năng chịu tải và hạn chế các phiên trùng participant replicas.
2. **Giữ phạm vi bất biến trong một run.** Mọi task phải dùng cùng snapshot token map/topology và cùng chính sách full/incremental/DC trừ khi đã replan rõ ràng.
3. **Retry có kiểm soát.** Nếu không chắc một phiên đã hoàn tất, phải đối chiếu log/trạng thái thật trước khi khởi chạy lại; không đánh dấu DONE chỉ vì lệnh từng được khởi phát.
4. **Không bỏ qua failed subrange.** Kết quả tổng của run chỉ hoàn tất khi mọi phần trong coverage đã đạt điều kiện thành công.
5. **Xử lý thay đổi topology.** Bootstrap, decommission, move token hoặc replace node có thể đổi ownership/participant set. Khi xảy ra, dừng suy luận trên snapshot cũ và lập kế hoạch mới theo runbook.

### 7.3. Pseudocode cho scheduler

~~~text
plan = load_validated_subranges()
assert coverage_has_no_gaps(plan)
assert topology_and_repair_scope_confirmed(plan)

for task in plan.in_order():
    if task.state == DONE:
        continue

    if topology_changed_since_plan():
        mark_run_needs_replan()
        stop

    mark(task, RUNNING)
    outcome = run_repair_on_approved_coordinator(
        keyspace, table, task.start_token, task.end_token,
        verified_mode_and_dc_scope
    )

    if outcome.completed_successfully_and_verified:
        save_logs_and_mark(task, DONE)
    else:
        save_logs_and_mark(task, FAILED)
        stop_or_retry_under_policy()

assert every_task_verified_done()
assert final_coverage_matches_intended_scope()
~~~

Pseudocode chỉ mô tả luồng điều phối; **không phải một script thực thi**. Hệ thống điều phối thực cần tính đúng ranh giới vòng, chọn node có trách nhiệm, triển khai kiểm tra trạng thái và xử lý phiên đã bị ngắt.

## 8. Tombstone và `gc_grace_seconds`: deadline làm repair trở nên quan trọng

Khi ứng dụng `DELETE` hoặc TTL hết hạn, Cassandra giữ **tombstone** để che dữ liệu cũ. Nếu một replica bỏ lỡ deletion và các replica khác dọn tombstone quá sớm, dữ liệu cũ có thể xuất hiện lại (*zombie data*) khi replica lạc hậu trở lại.

~~~mermaid
flowchart LR
    A["N1/N2 nhận DELETE t2"] --> B["Tombstone che giá trị cũ t1"]
    C["N3 offline, còn t1"] --> D["Chưa được đồng bộ xóa"]
    B --> E{"Repair hoàn tất khi tombstone còn hiệu lực?"}
    D --> E
    E -->|Có| F["N3 có cơ hội nhận deletion"]
    E -->|Không| G["Có nguy cơ dữ liệu t1 sống lại khi tombstone bị purge"]
~~~

`gc_grace_seconds` của bảng liên quan tới thời gian bảo vệ tombstone trước khi được dọn trong những điều kiện phù hợp. Ví dụ bảng dùng `gc_grace_seconds = 864000` (10 ngày) **không** có nghĩa Cassandra tự chạy repair sau 10 ngày, hoặc toàn bộ tombstone tự biến mất đúng ngày thứ mười.

**Kế hoạch chia nhỏ phải hoàn tất kịp**, chứ không chỉ bắt đầu trước mốc grace. Nếu job gồm 200 subrange và 199 phần đã hoàn thành nhưng một vùng chứa replica offline còn bị bỏ sót, vùng đó vẫn có rủi ro đối với tombstone.

Chính sách thực tế cần thời gian dự phòng cho retry, lỗi node và bảo trì, đồng thời phải hiểu các trường hợp đặc biệt của phiên bản/cấu hình hiện tại. Nếu node đã offline quá lâu, cân nhắc quy trình rebuild/replace an toàn thay vì cho node quá cũ quay lại và trông chờ một repair thông thường tự sửa mọi tình huống.

**Không nên giảm `gc_grace_seconds` để bù cho lịch repair quá chậm.** Việc dọn byte ở SSTable, dù bằng compaction hay TTL, không thay nghĩa vụ đồng bộ tombstone trên các replica trước khi xóa marker có nguy cơ gây zombie.

## 9. Repair khác compaction, streaming và backup

| Cơ chế | Mục đích | Liên hệ với subrange repair |
| --- | --- | --- |
| **Anti-entropy repair** | So sánh và đồng bộ dữ liệu giữa replica | Subrange repair là cách giới hạn **phạm vi token** của công việc này. |
| **Compaction** | Hợp nhất SSTable, dọn phiên bản/tombstone đủ điều kiện trên **một node** | Không tự sửa replica khác; có thể tạo áp lực I/O cùng lúc repair. |
| **Bootstrap/replace streaming** | Chuyển dữ liệu phục vụ node/topology mới | Không thay thế yêu cầu kiểm tra và hội tụ replica lâu dài. |
| **Hinted handoff** | Phát lại một số mutation mà replica tạm bỏ lỡ | Có thời hạn/giới hạn; không bù mọi sai lệch của các replica. |
| **Read repair** | Sửa mismatch được phát hiện trong đường đọc theo chính sách/phiên bản | Không quét toàn bộ token ranges như anti-entropy repair. |
| **Snapshot/backup** | Phục hồi một điểm dữ liệu trước lỗi vận hành hoặc mất mát lớn | Repair có thể nhân bản cả dữ liệu đã bị xóa sai; backup là biện pháp khác. |

Thực hành tốt là **không chạy nhiều tác vụ nặng chồng nhau** mà thiếu kế hoạch: repair, compaction mạnh, streaming khi mở rộng cluster và backup toàn dung lượng đều có thể tranh CPU, ổ đĩa, mạng và không gian tạm.

Subrange repair không phải biện pháp xử lý một partition cực lớn đang gây timeout; việc chia theo token không tách các hàng của cùng partition. Cần xem lại partition key/bucketing, giới hạn dữ liệu và read/write workload từ đầu.

## 10. CQL và Java: kiểm tra dữ liệu mà không nhầm với repair

### 10.1. Thử thao tác CQL trên partition cụ thể

Sau khi tạo bảng `telemetry_lab.readings_by_sensor_day` trong lab:

~~~sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO telemetry_lab.readings_by_sensor_day
    (sensor_id, event_day, event_time, event_id, reading)
VALUES
    ('sensor-7', '2026-11-21', '2026-11-21T03:00:00Z',
     123e4567-e89b-42d3-a456-426614174001, 22.50);

SELECT event_time, event_id, reading
FROM telemetry_lab.readings_by_sensor_day
WHERE sensor_id = 'sensor-7'
  AND event_day = '2026-11-21';
~~~

`CONSISTENCY` là lệnh của **cqlsh**, không phải một phần của CQL gửi nguyên văn từ Java. `LOCAL_QUORUM` khi RF = 3 ở DC cục bộ yêu cầu đủ hai phản hồi replica; nó không kích hoạt repair toàn bộ dải token đang xét.

Đọc trong CQL cho biết **kết quả logic mà client thấy**; nó không chứng minh mọi full replica đã đồng nhất. Hãy kết hợp kết quả nghiệp vụ với trạng thái phiên repair, topology và chỉ số vận hành.

### 10.2. Java Driver 4.x: dùng CL đúng cho truy vấn ứng dụng

Đây là ví dụ Java nhỏ, độc lập với scheduler repair:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.net.InetSocketAddress;
import java.time.LocalDate;

public final class ReadAfterRepairExample {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement query = session.prepare(
                "SELECT event_time, event_id, reading " +
                "FROM telemetry_lab.readings_by_sensor_day " +
                "WHERE sensor_id = ? AND event_day = ?");

            BoundStatement read = query.bind(
                    "sensor-7", LocalDate.of(2026, 11, 21))
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

            for (Row row : session.execute(read)) {
                System.out.println(row.getInstant("event_time")
                        + ": " + row.getBigDecimal("reading"));
            }
        }
    }
}
~~~

**Điểm cần phân biệt:** `withLocalDatacenter("dc1")` giúp driver chọn DC cục bộ phù hợp; `setConsistencyLevel(LOCAL_QUORUM)` xác định ngưỡng đáp ứng cho **request đọc này**. Không có API `SELECT` đơn lẻ nào trong đoạn code trên thay thế việc chạy repair qua các token ranges còn lệch.

Để vận hành repair từ hệ thống điều phối, thông thường dùng **công cụ quản trị/automation có quyền hạn riêng** thay vì cấp cho mọi ứng dụng Java quyền chạy `nodetool repair`. Việc khởi chạy lệnh với quyền cao từ API người dùng có thể tạo rủi ro về tải và an ninh.

## 11. Xử lý sự cố: một phần fail, cả run tính thế nào?

| Tình huống | Không nên làm | Cách xử lý |
| --- | --- | --- |
| Subrange A DONE, B FAILED | Đánh dấu cả run hoàn tất | Giữ A DONE, điều tra B, retry B theo chính sách và kiểm chứng. |
| Một replica down giữa phiên | Bỏ qua lỗi, coi dữ liệu đã repair | Kiểm tra kết quả phiên, replica participants; sửa node rồi chạy lại vùng liên quan. |
| Dải token đổi vì thêm node | Tiếp tục chạy nguyên kế hoạch cũ mà không kiểm tra | Replan theo ownership mới và đánh giá coverage đã/đang sửa. |
| Repair chạy quá lâu | Tăng song song vô hạn | Đo I/O, mạng, tombstone, dữ liệu hot; điều chỉnh số job, thời gian và kích thước subrange. |
| Chỉ một vài task thiếu log xác nhận | Suy luận “chắc là xong” | Đánh trạng thái `UNKNOWN`/FAILED và đối chiếu log trước khi khởi chạy lại. |
| Lỗi vượt `gc_grace_seconds` | Cố repair cũ như không có rủi ro | Áp dụng runbook an toàn tombstone, cân nhắc rebuild/replace nếu node quá cũ. |
| Job chỉ chạy ở một DC | Kết luận mọi DC đã đồng bộ | Xem lại scope DC/host và kế hoạch bao phủ multi-DC. |

### Quy trình điều tra tối thiểu

1. **Xác định task:** keyspace, table, start/end token, coordinator, participants, kiểu repair, thời điểm và log phiên.
2. **Xác nhận topology:** node up/down, token map, phạm vi DC và thay đổi membership kể từ lúc lập kế hoạch.
3. **Đo tải:** streaming, compaction, CPU/I/O, dung lượng còn trống và backlog.
4. **Phân loại lỗi:** timeout, không đủ replica, validation/streaming failure, hủy bởi operator hoặc topology thay đổi.
5. **Quyết định:** retry cùng scope, điều chỉnh độ song song, tách phần lớn hơn nữa hoặc replan theo topology.
6. **Đóng task:** chỉ chuyển `DONE` khi repair thật sự hoàn tất và lưu bằng chứng; cập nhật bản đồ coverage.

Một task chạy lại có thể tạo thêm chi phí validation/streaming dù dữ liệu đã hội tụ; **retry có kiểm soát** không có nghĩa chạy vô hạn mà không xem nguyên nhân gốc.

## 12. Sai lầm thường gặp

| Nhận định | Đúng hay sai? | Giải thích |
| --- | --- | --- |
| “Dùng `LOCAL_QUORUM` thì không cần repair.” | **Sai** | Replica không thuộc tập ACK hoặc vùng ít được đọc vẫn có thể lệch. |
| “Subrange là khoảng theo `event_day`.” | **Sai** | Ranh giới `-st/-et` là token, không phải thời gian hay clustering key. |
| “Cắt token range thành 8 phần thì mỗi phần có đúng 1/8 dữ liệu.” | **Sai** | Phân bố partition, kích thước và tombstone không đồng đều. |
| “Repair một khoảng trên một node luôn sửa mọi DC.” | **Sai** | Phải xem scope participant replicas, node/DC và phiên bản. |
| “`-pr` tương đương `-st/-et`.” | **Sai** | Primary ranges và subrange chỉ định tường minh là hai kiểu giới hạn phạm vi khác nhau. |
| “Task timeout nhưng không có exception cuối cùng nghĩa là DONE.” | **Sai** | Cần bằng chứng kết thúc/hoàn thành từ phiên và công cụ quản trị. |
| “Repair sửa được dữ liệu đã `DELETE` nhầm.” | **Sai** | Repair có thể lan tombstone; phục hồi lỗi logic cần backup/nguồn dữ liệu khác. |
| “Repair có thể bỏ qua grace vì tombstone sẽ tồn tại mãi.” | **Sai** | Tombstone có thể bị purge theo điều kiện, và replica quá cũ gây nguy cơ zombie. |
| “Subrange nhỏ luôn tiết kiệm tài nguyên.” | **Sai** | Quá nhỏ làm tăng chi phí lập lịch/validation, trong khi partition lớn vẫn không thể tách. |
| “Có thể ghi checkpoint ở từng subrange và resume phần chưa xong.” | **Đúng, có điều kiện** | Chỉ khi kế hoạch coverage/topology hợp lệ và trạng thái hoàn tất được xác minh. |

## 13. Bài tập có đáp án

**Bài 1.** Muốn repair khoảng token `(-100, 200]` bằng hai phần, cắt tại `50`. Hãy viết hai khoảng không hở.

**Đáp án:** `(-100, 50]` và `(50, 200]`. Token đúng bằng `50` thuộc phần đầu. Đây là ví dụ phạm vi con **không quấn vòng**, không chứng minh đã sửa toàn ring.

**Bài 2.** Có RF = 3 trong một DC. Write `LOCAL_QUORUM` nhận ACK từ N1, N2; N3 offline. Vì sao subrange repair vẫn hữu ích?

**Đáp án:** N3 có thể chưa nhận mutation. Quorum write thành công chỉ đòi hai replica ACK; khi N3 trở lại, repair có thể đồng bộ các partition thuộc range mà N3 đã bỏ lỡ.

**Bài 3.** Repair run gồm 50 subrange. 49 task `DONE`, một task `FAILED` do streaming timeout. Có nên đánh dấu cả bảng đã được repair?

**Đáp án:** **Không.** Còn một vùng chưa có xác nhận repair thành công. Cần điều tra, retry theo chính sách hoặc replan; kết quả chung chỉ đầy đủ khi coverage đã được xác minh.

**Bài 4.** Hai khoảng token có độ rộng bằng nhau, nhưng một khoảng chứa một partition 200 GB, khoảng kia nhiều partition nhỏ tổng 2 GB. Có thể giả định cả hai có cùng thời gian repair không?

**Đáp án:** **Không.** Token width không đại diện chính xác cho byte, số SSTable, tombstone hay chi phí truyền. Khoảng chứa partition rất lớn vẫn có thể là điểm nghẽn dù tiếp tục chia token.

**Bài 5.** Một replica bỏ lỡ deletion và offline lâu hơn khoảng grace. Vì sao không thể chỉ đổi `gc_grace_seconds` xuống thấp hơn để “giúp repair nhanh”?

**Đáp án:** Grace thấp có thể làm tombstone bị purge quá sớm, khiến replica mang dữ liệu cũ quay lại và tạo zombie. Cần xử lý replica/repair bằng quy trình an toàn và đủ thời gian dự phòng.

**Bài 6.** Trong cluster có hai DC, một task `nodetool repair` được cấu hình chỉ tham gia replica của DC1. Có thể khẳng định DC2 đã đồng bộ hoàn toàn không?

**Đáp án:** **Không.** Phạm vi đã hạn chế participant ở DC1; phải lập/kiểm tra kế hoạch đồng bộ DC2 theo topology và yêu cầu thực tế.

**Bài 7.** Khi đang chạy 100 subrange, cluster thêm node mới. Cách an toàn hơn là tiếp tục mọi khoảng cũ hay đánh giá lại ownership?

**Đáp án:** **Đánh giá lại ownership** và token map, xác định những khoảng/replica có thay đổi rồi replan theo runbook. Không đánh đồng kế hoạch lập trước bootstrap với topology hiện tại.

## 14. Checklist thực hành trước khi báo “repair hoàn tất”

~~~text
[ ] Xác định keyspace, bảng, partitioner và topology thực tế.
[ ] Kiểm tra token map, phạm vi cần bao phủ và ranh giới vòng.
[ ] Chia subrange không hở, ghi lại start/end token từng task.
[ ] Xác định coordinator/participants, DC scope, full/incremental mode.
[ ] Chọn concurrency và khung thời gian theo khả năng chịu tải.
[ ] Theo dõi session/log, validation và streaming của từng task.
[ ] Đánh dấu DONE chỉ khi kết quả hoàn tất đã được xác minh.
[ ] Retry/replan mọi task FAILED/UNKNOWN; không bỏ qua khoảng token nào.
[ ] Xác nhận repair kịp lịch an toàn tombstone và xử lý replica offline lâu.
[ ] Kiểm tra đủ coverage của mọi vùng/replica theo kế hoạch, lưu bằng chứng.
~~~

**Ghi nhớ:** *Subrange repair* không tạo ra một loại consistency mới; nó **chia công việc anti-entropy repair theo khoảng token** để theo dõi, kiểm soát tải và retry dễ hơn. Repair đúng không chỉ là chạy nhiều lệnh `nodetool`, mà là **xác định phạm vi dữ liệu/replica cần đồng bộ, không bỏ sót token range, kiểm chứng từng phần và hoàn tất trước khi tombstone không còn an toàn**. Muốn đạt được điều đó, hãy dựa vào token ownership, replication theo DC, metrics và trạng thái task thay vì suy từ số lượng lệnh đã chạy.
