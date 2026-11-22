# Lập lịch repair dựa trên phạm vi dữ liệu và thời gian giữ dấu xóa

> **Chương:** Tự động hóa vận hành  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Phạm vi:** Lập lịch, theo dõi và nghiệm thu anti-entropy repair của Apache Cassandra theo keyspace, table, token range, replica/DC và thời gian giữ tombstone; kết hợp CQL, Java Driver, RF/CL, compaction, TTL và xử lý lỗi vận hành.  
> **Mục tiêu vận hành:** Bảo đảm những replica có trách nhiệm lưu cùng dữ liệu được đối soát đủ thường xuyên, không chỉ “đã chạy lệnh repair”.

## 1. Vấn đề: lịch repair mỗi tuần nhưng dữ liệu vẫn có thể sống lại

Một cụm Cassandra phục vụ sự kiện đơn hàng theo tenant. Bảng có **gc_grace_seconds = 864000** (10 ngày). Đội vận hành đặt một cron job repair vào Chủ nhật mỗi tuần và thấy lịch chạy đều đặn. Tuy nhiên:

- Một node chứa replica của partition K bị DOWN hơn 10 ngày.
- Job Chủ nhật vẫn khởi chạy, nhưng một số **token ranges** hoặc node bị lỗi nên không được repair đầy đủ.
- DELETE của K đã được xác nhận ở các replica còn khỏe, nhưng node DOWN chưa nhận tombstone.
- Tombstone đủ điều kiện purge sau grace và có thể bị compaction loại bỏ.
- Node cũ trở lại với dữ liệu chưa biết đã bị xóa; trong điều kiện phù hợp, dữ liệu có thể **hồi sinh (zombie)**.

Điều cần đo không phải “cron chạy bao nhiêu lần” mà là **từng phạm vi dữ liệu đã được repair thành công khi nào, với những replica nào, và có còn nằm trong cửa sổ bảo vệ tombstone không**.

Hai khái niệm cần tách:

1. **Job schedule:** Khi nào orchestrator tạo một công việc repair.
2. **Verified coverage:** Keyspace/table, token ranges, DC/replica đã thực sự hoàn thành repair phù hợp và được ghi nhận thành công.

Một công việc trả exit code 0 chưa đủ nếu chỉ xử lý một tập range nhỏ, bỏ qua một DC, hoặc metadata/worker báo thành công sai phạm vi.

### Mục tiêu học tập

Hoàn thành bài học, bạn có thể:

- Giải thích repair, tombstone, TTL, gc_grace_seconds và điều kiện zombie.
- Xác định **đơn vị lập lịch** theo keyspace/table/token range/replica/DC thay vì một lịch cron chung.
- Tính **ngân sách thời gian** từ grace window, thời gian thực thi repair, lỗi và thời gian node không khả dụng.
- Thiết kế **coverage ledger** và điều kiện đánh dấu COMPLETED/PARTIAL/FAILED/STALE.
- Lập lịch theo mức độ rủi ro, độ lớn dữ liệu và capacity, có admission, backoff và stop gates.
- Phân biệt repair incremental/full và lựa chọn phạm vi theo phiên bản Cassandra.
- Dùng CQL và lệnh nodetool chỉ đọc để xác minh schema, RF, TTL, compaction và tiến độ.
- Viết Java code minh họa chấm điểm hạn repair, theo dõi ledger và kiểm thử scheduler.
- Xây dựng runbook cho missed repair, node outage, thay topology và deadline sắp hết.
- Tránh các lỗi như giảm gc_grace để dọn tombstone, chạy nhiều repair tranh I/O, hoặc bỏ qua failed ranges.

> **Quy tắc an toàn:** Các lệnh làm thay đổi cluster (repair, rebuild, decommission, thay RF, compaction cưỡng bức, xóa snapshot) chỉ được kích hoạt bởi công cụ/runbook có quyền phê duyệt trên môi trường phù hợp. Bài không hướng dẫn chạy repair tùy ý trên production; ví dụ cấu hình là thiết kế lab, phải xác minh với đúng phiên bản Cassandra/operator.

## 2. Vì sao cần repair trong Cassandra phân tán?

Cassandra phân dữ liệu bằng **partition key → token → tập replica** theo replication strategy. Trong một DC dùng **NetworkTopologyStrategy**, RF=3 nghĩa là mỗi partition được đặt trên ba replica theo placement strategy. Một coordinator nhận CQL rồi làm việc với những replica được chọn.

Giả sử client ghi DELETE K với **LOCAL_QUORUM** khi một replica DOWN:

~~~text
Partition K, RF=3 trong dc1

A (UP):  nhận DELETE K, giữ tombstone
B (UP):  nhận DELETE K, giữ tombstone
C (DOWN): vẫn giữ bản dữ liệu K cũ

LOCAL_QUORUM: A+B đủ xác nhận write trong ví dụ.
Nhưng C chưa được bảo đảm đã nhận DELETE.
~~~

Repair dùng cơ chế **anti-entropy**, so sánh trạng thái dữ liệu theo token ranges giữa những replica liên quan và đồng bộ khác biệt. Nó giúp phòng ngừa một replica trở về với phiên bản cũ sau khi dấu xóa đã mất.

Tuy nhiên:

- Repair **không phải backup**; nó không hoàn tác một DELETE hợp lệ nhưng sai nghiệp vụ.
- Repair **không sửa** một câu INSERT mới với timestamp cao hơn tombstone theo ý nghĩa nghiệp vụ.
- Repair **không tự suy** row nào đáng lẽ đã xóa sau khi tombstone và bằng chứng xóa đều không còn.
- Một phiên repair **partial** không chứng minh toàn table, DC hay cluster đã hội tụ.
- Hinted handoff/read repair có giới hạn theo version/path; **không thay thế chiến lược anti-entropy repair định kỳ đã được kiểm chứng**.

### 2.1. Tombstone và gc_grace_seconds

DELETE được biểu diễn bằng **tombstone** mang timestamp. TTL expiration cũng tạo trạng thái dữ liệu hết hạn cần được xét an toàn khi hợp nhất dữ liệu. **gc_grace_seconds** là thời gian grace của table liên quan đến điều kiện loại tombstone khỏi SSTable.

Ví dụ:

~~~text
gc_grace_seconds = 864000 giây = 10 ngày

DELETE K tại T0:
  Tombstone giúp chặn những phiên bản K cũ.

Trong cửa sổ bảo vệ:
  Replica bỏ lỡ xóa cần có cơ hội được đồng bộ.

Sau khi tombstone đủ điều kiện purge:
  Compaction có thể loại dấu xóa nếu các điều kiện khác cho phép.

Nếu stale replica quay lại khi dấu xóa đã mất:
  K có nguy cơ sống lại.
~~~

**Không coi 10 ngày là mốc chắc chắn tombstone biến mất.** Purge còn tùy compaction, SSTable overlap và điều kiện an toàn khác của version. Nhưng cũng **không dùng sự chậm trễ purge làm cam kết an toàn** nếu lịch repair đã vượt cửa sổ grace.

### 2.2. Phân biệt ba thời gian

| Khái niệm | Ý nghĩa | Không nên nhầm với |
|---|---|---|
| **TTL** | Thời gian sống của cell được ghi với TTL, tính theo giây | Lịch repair |
| **gc_grace_seconds** | Cửa sổ bảo vệ tombstone trước khi đủ điều kiện garbage collection | Thời gian chạy một lần compaction |
| **Repair interval/coverage lag** | Thời gian giữa những lần phạm vi dữ liệu được repair hoàn tất hợp lệ | Chỉ số cron đã phát lệnh |

TTL ngắn không có nghĩa nên đặt gc_grace_seconds ngắn tương ứng. Một table dữ liệu TTL vài giờ vẫn có thể cần grace và repair phù hợp để tránh replica cũ mang dữ liệu đã hết hạn trở lại trong những điều kiện nhất định.

### 2.3. Compaction không phải lịch repair

Compaction hợp nhất SSTables, loại dữ liệu obsolete/tombstone khi đủ điều kiện và ảnh hưởng disk/CPU/read p99. Repair làm công việc đối chiếu replica. **Compaction không biết replica ở DC khác đã bỏ lỡ DELETE hay chưa**, nên không thể lấy “compaction vừa chạy” làm bằng chứng tất cả token ranges đã được repair.

## 3. Đơn vị phải được theo dõi: table × token range × replica scope

Một cron job cấp cluster không cho biết phạm vi thực sự được bảo vệ. Hệ điều phối nên có **coverage ledger** tối thiểu theo:

| Thành phần | Ý nghĩa |
|---|---|
| **Cluster/environment** | Tránh nhầm staging với production |
| **Keyspace/table** | Mỗi table có gc_grace, TTL, compaction và khối lượng khác nhau |
| **Token range / subrange** | Phạm vi partition keys được so sánh giữa replica |
| **DC/replica scope** | Những replica nào phải được xét theo chiến lược repair/version |
| **Repair mode** | Full/incremental hoặc cơ chế operator quản lý |
| **Topology generation** | Đánh dấu rằng ownership thay đổi sau bootstrap/replace/decommission |
| **Last verified success** | Thời điểm phạm vi hoàn tất và được xác minh, không chỉ job start |
| **Previous failures** | Ranges còn thiếu, retry budget và nguyên nhân lỗi |
| **Next deadline** | Grace window trừ safety margin và thời gian hoàn tất dự kiến |
| **Evidence** | Repair session ID, log/metrics, version, manifest thành công |

Một range có thể rất nóng/lớn, một range khác ít dữ liệu. **Lịch riêng theo table/range** cho phép:

- Ưu tiên phạm vi sắp hết hạn bảo vệ tombstone.
- Chia repair lớn thành subranges theo khả năng phiên bản/công cụ.
- Theo dõi failed ranges mà không báo “toàn bộ table OK”.
- Thay đổi thứ tự khi repair duration và replica availability khác nhau.
- Phân bổ nguồn lực tránh nhiều job cùng đánh vào một node.

### 3.1. Coverage không phải số phần trăm bytes đơn thuần

Một báo cáo “repair 99% số byte” có thể bỏ sót range nhỏ chứa tombstones quan trọng. Coverage cần được xác định theo **tập phạm vi bắt buộc**: những ranges nào, table nào, DC/replica nào. Đếm bytes giúp đo tiến độ nhưng không thay thế danh sách phạm vi đã hoàn tất.

Ví dụ:

~~~text
Table events_by_tenant_day
  dc1 / range R1: COMPLETED
  dc1 / range R2: COMPLETED
  dc1 / range R3: FAILED
  dc1 / range R4: PENDING

Result:
  Table repair = PARTIAL, không phải VERIFIED COMPLETE.
  R3/R4 phải có deadline và owner xử lý riêng.
~~~

### 3.2. Topology thay đổi khiến ledger phải được đánh giá lại

Khi thêm/thay node, ownership token ranges và tập replica có thể thay đổi. Bằng chứng “range R được sửa giữa A/B/C tuần trước” chưa chắc bao phủ các replica mới sau bootstrap.

Orchestrator cần:

1. Ghi topology generation/cluster metadata ở thời điểm bắt đầu.
2. Phát hiện thay đổi owner/DC/rack/RF trước khi nhận job success.
3. Xác định phạm vi cần kiểm tra/repair lại theo runbook version-specific.
4. Không tự đánh dấu toàn bộ range covered chỉ vì bytes đã streamed sang node mới.
5. Tránh repair overlapping khi topology chưa ổn định và operator yêu cầu đợi.

## 4. Tạo catalog table theo rủi ro tombstone và workload

Không phải mọi table cần cùng độ ưu tiên vận hành. Catalog nên thu thập:

| Thuộc tính | Câu hỏi |
|---|---|
| **Data purpose** | Order, session TTL, event history hay audit? |
| **Delete/TTL pattern** | Xóa nhiều, TTL ngắn hay ít tombstone? |
| **gc_grace_seconds** | Giá trị thực trên mỗi table là bao nhiêu? |
| **Size / SSTables / partition distribution** | Range/table lớn đến mức nào, có hot partitions? |
| **Compaction strategy** | STCS/LCS/TWCS hoặc lựa chọn version-specific |
| **RF/DC** | Data nằm ở DC nào, những replica nào có thể lỗi? |
| **Availability requirement** | Node có thể DOWN tối đa bao lâu? |
| **Repair coverage SLA** | Mỗi scope phải được xác minh lại trong bao lâu? |
| **Historical failures** | Phạm vi nào thường timeout/skipped? |
| **Load sensitivity** | Peak traffic, read p99, compaction/backup windows? |

### 4.1. Ví dụ catalog, không phải lịch chuẩn

| Table giả định | Pattern | Grace giả định | Nguy cơ | Hướng lập lịch |
|---|---|---:|---|---|
| **order_state_by_id** | DELETE/UPDATE, yêu cầu đúng trạng thái | 10 ngày | Cao khi missing replica | Phạm vi ưu tiên, coverage xác minh thường xuyên |
| **sessions_by_id** | TTL ngắn, nhiều expires | 10 ngày | Tombstone pressure và stale replica | Repair có budget I/O, theo dõi TTL/compaction riêng |
| **events_by_tenant_day** | Append/bucket, TTL theo retention | 10 ngày | Dữ liệu lớn và late writes | Chia ranges/cửa sổ repair, theo dõi TWCS nếu dùng |
| **test_fixture** | Dữ liệu lab có thể xóa | Theo cấu hình lab | Thấp về nghiệp vụ, vẫn cần an toàn cluster | Lịch riêng, không ảnh hưởng production |

**Grace giả định không phải khuyến nghị mặc định cho mọi table.** Phải đọc schema thực tế và chọn lịch dựa trên khả năng hoàn tất repair ở topology cụ thể.

### 4.2. Dữ liệu bất biến không có nghĩa miễn repair một cách tùy tiện

Một bảng append-only vẫn có thể có TTL expiration, tombstones do retention, late writes, failed replica và nhiều SSTables. Chỉ khi thiết kế, khả năng mất dữ liệu, dữ liệu bất biến và hướng dẫn Cassandra/compaction strategy đã được đánh giá đầy đủ, mới cân nhắc chính sách khác. Không dùng nhãn “append-only” để bỏ repair mà không có evidence và approval.

## 5. Ngân sách thời gian: hoàn tất trước hạn, không chỉ bắt đầu trước hạn

Đặt:

- **G:** gc_grace_seconds của table, đổi thành thời gian cho phép.
- **I:** thời gian từ một lịch khởi động đến lịch khởi động tiếp theo của cùng phạm vi.
- **Dmax:** thời lượng repair lớn nhất dự kiến cho phạm vi, từ bắt đầu đến hoàn tất/verified.
- **F:** độ trễ dự phòng vì job lỗi, retry có kiểm soát hoặc hàng đợi.
- **O:** thời gian/độ trễ bổ sung khi replica không khả dụng hoặc topology đang chuyển tiếp.
- **B:** safety buffer cho jitter lịch chạy, metric delay, timezone, sai số clock và biến động vận hành.

Một ước lượng **bảo thủ để thiết kế lịch**:

\[
L_{budget} = I + D_{max} + F + O + B
\]

Yêu cầu mục tiêu:

\[
L_{budget} < G
\]

**Cảnh báo:** Bất đẳng thức này **không phải chứng minh an toàn dữ liệu**. Nó chỉ giúp hoạch định khi các phạm vi được repair đầy đủ, node availability phù hợp và các điều kiện version-specific được đáp ứng. Nếu một replica DOWN lâu hơn cửa sổ bảo vệ hoặc coverage không hoàn tất, lịch đẹp vẫn không đủ.

### 5.1. Ví dụ ngân sách trên table grace 10 ngày

| Thành phần | Dự phòng |
|---|---:|
| Grace G | 10 ngày |
| Khoảng lịch I | 3 ngày |
| Repair duration Dmax | 1,5 ngày |
| Retry/queue F | 1 ngày |
| Outage/maintenance O | 2 ngày |
| Buffer B | 1 ngày |
| **Tổng Lbudget** | **8,5 ngày** |
| **Headroom** | **1,5 ngày** |

Phương án giả định có margin theo công thức, nhưng chỉ là **design input**. Nếu node outage kéo dài thêm 2 ngày hoặc job có failed ranges, phạm vi phải chuyển sang **AT_RISK**/escalation chứ không đợi cron kế tiếp.

### 5.2. Theo dõi tuổi của lần repair được xác minh

Một đồng hồ vận hành hữu ích:

~~~text
coverage_age = now - last_verified_success_at
coverage_headroom = grace - coverage_age - repair_eta - buffer

Nếu coverage_headroom <= 0:
    không thể hứa hoàn tất an toàn theo lịch hiện tại;
    phát cảnh báo ưu tiên, điều tra replica/repair.

Nếu job PENDING nhưng grace vẫn còn nhiều:
    đưa vào queue theo priority + resource budget.

Nếu job FAILED hoặc topology thay đổi:
    không coi lần START trước đó là coverage mới.
~~~

Có thể dùng **ngày/giờ UTC** và duration thực, không dựa vào “đã đến Chủ nhật”. Trong production cần biết **thời điểm tombstone cũ nhất chưa được phổ biến đầy đủ**, điều này thường không dễ đo trực tiếp; vì vậy coverage-age là chỉ báo bảo thủ giúp không bỏ quên scope chứ không phải lời xác nhận mọi delete đã an toàn.

### 5.3. Ước lượng Dmax từ dữ liệu thật

Không tính Dmax từ số GB một cách máy móc. Repair gồm validation, so sánh và có thể streaming dữ liệu khác biệt; thời gian phụ thuộc:

- Số SSTables/ranges và kích thước dữ liệu.
- Network sender/receiver, cross-DC link.
- Disk read/write IOPS và latency.
- GC/heap/offheap và pending compaction.
- Number of concurrent sessions, repair mode và topology.
- Dữ liệu khác biệt giữa replica, số node DOWN/lag.
- Thời điểm backup/bootstrap/streaming khác trùng lịch.

Lấy **p95/p99 thời lượng repair thực tế theo table/range**, có giới hạn đủ bảo thủ; sửa Dmax khi topology/data size thay đổi. Không giả định repair 10 TB xong trong 1 giờ chỉ vì lần đầu của table trống chạy nhanh.
## 6. Chọn full, incremental và subrange repair theo phiên bản

Cassandra hỗ trợ nhiều cơ chế/biến thể repair tùy version và công cụ vận hành. Những tên thường gặp là **full repair**, **incremental repair**, **primary-range repair**, lựa chọn DC/host/range, cùng các cơ chế operator/repair service chuyên biệt.

### 6.1. Không có một lệnh repair đúng cho mọi cluster

| Quyết định | Mục tiêu | Điều phải xác minh |
|---|---|---|
| **Full repair** | So sánh phạm vi dữ liệu theo cơ chế full trên những replica liên quan | Version, ảnh hưởng SSTable repaired/unrepaired, I/O, duration |
| **Incremental repair** | Giảm công việc theo cơ chế repaired data và lịch của phiên bản | Preconditions, bookkeeping, failure recovery và compatibility |
| **Subrange repair** | Chia công việc lớn thành nhiều phạm vi token | Cú pháp ranges, ownership và khả năng coverage không hở |
| **Primary-range repair** | Phân công repair trên phạm vi chủ quản theo cơ chế tool | Liệu tất cả ranges và replica/DC được bao phủ sau toàn lịch? |
| **DC-scoped repair** | Giới hạn phạm vi được repair trong DC cụ thể | Business invariant/multi-DC data, DC khác có bỏ lỡ deletes? |
| **Operator-managed repair** | Điều phối jobs/locks/metrics tự động | Tool có thực sự theo dõi completed ranges, topology và retries? |

Không dùng **incremental** chỉ vì tên nghe nhẹ hơn. Cách đánh dấu/reconcile repaired SSTables, khả năng recover sau job lỗi và cách phối hợp full/incremental thay đổi theo Cassandra version. Lập lịch theo tài liệu chính thức của **version đã pin** và bằng chứng từ staging.

### 6.2. Vì sao subrange giúp tự động hóa?

Một full-table repair rất lớn có thể kéo dài, không thể đoán trước ETA và làm read p99 xấu khi trùng giờ cao điểm. Chia theo token ranges hỗ trợ:

1. Phát hiện phạm vi nào đã xong.
2. Xếp thứ tự phạm vi sắp hết ngân sách grace.
3. Giới hạn concurrency trên nodes liên quan.
4. Retry riêng phạm vi lỗi (khi công cụ/version hỗ trợ an toàn).
5. Pausing scheduling tasks mới theo SLO, không xóa bằng chứng đang có.

**Bẫy:** Một range bị bỏ qua không tự biến thành thành công vì 99 range khác đã xong. Tổng coverage phải là **hợp của tất cả ranges bắt buộc tại topology hiện tại**, không trùng lặp sai hoặc để lỗ hổng token ownership.

### 6.3. Đừng pha trộn repaired/unrepaired state tùy tiện

Một số chế độ incremental có metadata về SSTables repaired/unrepaired hoặc trạng thái pending repair. Nếu job bị gián đoạn, thao tác nào có thể resume/retry và phạm vi nào đã thực sự finalized phụ thuộc version.

Runbook cần ghi:

- Repair mode và version của từng job.
- SSTable/repair pending state nếu công cụ có hiển thị.
- Những phạm vi hoàn tất đủ tiêu chí tool, không chỉ validation started.
- Hành vi khi session lỗi, coordinator chết, topology đổi.
- Thủ tục khôi phục/sửa bookkeeping đã được vendor/version chấp thuận.

Không chỉnh sửa trực tiếp system tables/SSTable metadata để “đánh dấu repaired” khi thiếu bằng chứng.

## 7. CQL lab: đọc grace, TTL và phạm vi dữ liệu

### 7.1. Keyspace và bảng theo truy vấn

Ví dụ lab dùng một DC **dc1**, RF=3; chỉ chạy khi cluster lab có đủ replica tương ứng.

~~~sql
CREATE KEYSPACE IF NOT EXISTS repair_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

-- Lịch sử sự kiện theo tenant + ngày, phục vụ truy vấn phân vùng.
CREATE TABLE IF NOT EXISTS repair_lab.events_by_tenant_day (
    tenant_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((tenant_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (
    occurred_at DESC, event_id ASC
) AND gc_grace_seconds = 864000;

-- Point lookup theo logical request.
CREATE TABLE IF NOT EXISTS repair_lab.state_by_request (
    tenant_id uuid,
    request_id uuid,
    state text,
    updated_at timestamp,
    PRIMARY KEY ((tenant_id, request_id))
) WITH gc_grace_seconds = 864000;
~~~

**Giải thích:**

- **(tenant_id, event_day)** là composite partition key của events; query theo ngày phải bind cả hai.
- **(tenant_id, request_id)** xác định một logical request. Nó hỗ trợ đối soát yêu cầu ghi/xóa khi timeout, tránh sinh ID mới sau retry.
- Cả hai table có thể chứa tombstones do DELETE/TTL và cần repair theo phạm vi token/replica.
- Trường **gc_grace_seconds** ở đây là lựa chọn giả định cho lab, không phải giá trị nên copy production.
- Data size, số partition và tỷ lệ tombstone của hai table khác nhau, nên Dmax và ưu tiên repair khác nhau.

### 7.2. Đọc metadata thực tế thay vì đoán default

~~~sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'repair_lab';

SELECT keyspace_name, table_name, gc_grace_seconds,
       default_time_to_live, compaction
FROM system_schema.tables
WHERE keyspace_name = 'repair_lab';

SELECT column_name, kind, position, type
FROM system_schema.columns
WHERE keyspace_name = 'repair_lab'
  AND table_name = 'events_by_tenant_day';
~~~

Một hệ thống catalog tự động cần **đọc schema định kỳ** vì table mới hoặc ALTER TABLE có thể thay đổi grace/TTL/compaction mà scheduler chưa biết. Nếu metadata chưa đồng bộ giữa nodes, phải xử lý **schema agreement** trước khi tin coverage hoặc lập lịch dựa trên giá trị mới.

### 7.3. Ghi có TTL, xóa và quan sát cell

~~~sql
-- Fixture có request ID xác định, TTL chỉ để lab.
INSERT INTO repair_lab.state_by_request (
    tenant_id, request_id, state, updated_at
) VALUES (
    11111111-1111-4111-8111-111111111111,
    22222222-2222-4222-8222-222222222222,
    'ACTIVE', '2026-11-21T08:00:00Z'
) USING TTL 600;

SELECT state,
       TTL(state) AS state_ttl_seconds,
       WRITETIME(state) AS state_write_micros
FROM repair_lab.state_by_request
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND request_id = 22222222-2222-4222-8222-222222222222;

DELETE FROM repair_lab.state_by_request
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND request_id = 22222222-2222-4222-8222-222222222222;
~~~

**TTL(state)** cho số giây còn lại của cell khi có TTL; **WRITETIME(state)** cho timestamp ghi cell (microseconds). Sau DELETE/expiration, CQL thông thường không cho đọc toàn bộ lịch sử tombstone/replica của row, nên không thể dùng một kết quả SELECT để chứng minh repair an toàn.

**Chú ý:** Cột **updated_at** là metadata nghiệp vụ; vì lấy một timestamp lịch sử cố định, nó không làm TTL hết hạn ngay. TTL áp theo mutation time, không đọc giá trị updated_at.

### 7.4. Data scope không chỉ là row count

Khi chọn repair ranges, cần biết:

- Partition key distribution, token ownership và replication topology.
- SSTable bytes, tombstone density, disk I/O và compaction backlog.
- Table dùng TTL/default TTL, delete-heavy hay append-only.
- Ngưỡng partition size/hot partition.
- Các table khác cùng node/volume có workload lớn hay không.

Số rows ít không bảo đảm repair nhẹ nếu có SSTables/tombstones lớn hoặc đĩa nghẽn. Không cho scheduler dùng **ALLOW FILTERING**/full-table scan để đếm row làm preflight; dùng schema, metrics, token/range estimates và read-only monitoring phù hợp.

## 8. Phạm vi DC/replica và sự khác nhau của LOCAL_QUORUM

Giả sử keyspace dùng **NetworkTopologyStrategy**:

~~~text
dc1: RF = 3
dc2: RF = 3

Một phân vùng K có:
  dc1: A, B, C
  dc2: D, E, F
~~~

Một DELETE với **LOCAL_QUORUM** từ dc1 có thể đạt điều kiện đáp ứng tại các replica local mà không đồng nghĩa mọi replica của dc2 đã nhận xóa. Nếu ứng dụng đọc ở dc2 hoặc có writers khác, chiến lược repair cần xem xét **sự nhất quán và phạm vi xuyên DC** theo cấu hình/version.

### 8.1. Những câu hỏi bắt buộc trước khi chọn DC scope

1. Dữ liệu cần bảo toàn ở những DC nào, có cross-DC replication không?
2. API đọc/ghi **LOCAL_ONE, LOCAL_QUORUM, QUORUM** hay CL khác?
3. Những DC nào có quyền ghi và có thao tác LWT/serial consistency?
4. Công cụ repair được định nghĩa **local-DC only** hay có so sánh các replica xuyên DC?
5. Có network partition/WAN outage kéo dài gần vượt grace không?
6. Một phạm vi hoàn thành ở dc1 có đủ theo chính sách coverage toàn cluster không?
7. Có yêu cầu data residency làm hạn chế repair/streaming xuyên vùng không?

### 8.2. Tránh kết luận sai từ một DC khỏe

Một dashboard dc1 “repair 100%” không chứng minh dc2 được đối soát đầy đủ. Scheduler phải biểu diễn **scope của từng DC** và báo trạng thái toàn hệ thống dựa trên business consistency policy, chứ không tự sao chép thành công dc1 sang dc2.

Tương tự, tăng consistency level không thể tái tạo tombstone đã bị purge. Nếu có zombie, cần audit/deletion ledger hoặc nguồn sự thật nghiệp vụ và kế hoạch reconciliation.

### 8.3. Replica downtime dài hơn grace là trường hợp đặc biệt

Nếu một replica không khả dụng vượt quá gc_grace_seconds và đã có deletes trong thời gian đó:

- **Không tự đưa node trở lại phục vụ** chỉ vì gossip báo UP.
- Không mặc định chạy một phiên repair sau đó là đủ nếu tombstones đã có thể bị purge.
- DBA/SRE phải đánh giá dữ liệu có thể zombie, rebuild/replace/quarantine và nguồn sự thật theo runbook version-specific.
- Giữ logs, snapshots/backup, repair sessions và topology evidence.
- Phân loại trạng thái **AT_RISK / ESCALATE** ngay cả khi cron kỳ sau vẫn chưa đến.

## 9. Kiến trúc tự động hóa: planner, runner, ledger và verifier

~~~mermaid
flowchart TD
    A["Schema & topology discovery"] --> B["Coverage ledger per table/range/DC"]
    C["Repair metrics & job history"] --> B
    B --> D["Planner: risk/deadline & duration estimate"]
    D --> E{"Eligibility: health, capacity, change window"}
    E -->|Không| F["DEFER + alert + updated deadline"]
    E -->|Có| G["Acquire shared lease/fencing"]
    G --> H["Repair runner via approved operator/tool"]
    H --> I["Collect range/session result + logs"]
    I --> J{"Verified coverage matches plan?"}
    J -->|Có| K["Update last_verified_success_at"]
    J -->|Partial/failed| L["Record uncovered ranges, retry/escalation"]
    K --> B
    L --> B
~~~

### 9.1. Phân tách trách nhiệm rõ ràng

| Thành phần | Vai trò | Không nên làm |
|---|---|---|
| **Discovery** | Đọc schema options, RF/DC, topology, table catalog | Tự sửa schema cho khớp lịch |
| **Planner** | Tính deadline và ưu tiên, chọn phạm vi eligible | Coi một job start là thành công |
| **Admission** | Kiểm tra node health, SLO, headroom, maintenance overlap | Start nhiều jobs khi disk đã đầy |
| **Runner** | Gọi công cụ repair được phê duyệt, theo dõi session | Gọi CQL để giả repair replica |
| **Verifier** | Xác minh repair status/coverage per scope | Đánh dấu toàn table complete từ một range |
| **Ledger** | Lưu scope, last success, failures và evidence | Chỉ lưu timestamp gần nhất của cron |
| **Alerting** | Cảnh báo near-deadline, stale/failed coverage | Chỉ cảnh báo khi cron process exit nonzero |

### 9.2. Trạng thái cần hỗ trợ

~~~text
DISCOVERED
  -> ELIGIBLE
  -> PLANNED
  -> RUNNING
  -> VERIFYING
  -> COMPLETED (verified scope)
  -> STALE (theo thời gian/topology)

RUNNING/VERIFYING
  -> PARTIAL (một số ranges chưa hoàn tất)
  -> FAILED (job không thể hoàn tất)
  -> UNKNOWN (thiếu evidence, mất coordinator/scheduler)

FAILED/PARTIAL/STALE/UNKNOWN
  -> RETRY_ELIGIBLE hoặc ESCALATED
  -> PLANNED nếu còn an toàn và được duyệt
~~~

**Quy tắc:** Chỉ **COMPLETED** sau khi verifier có bằng chứng rằng table/ranges/DC/replica scope của plan đã hoàn tất theo công cụ/version. Một timer, network retry hoặc worker reboot không được tự biến UNKNOWN thành COMPLETE.

### 9.3. Ledger phải bền vững và tránh tranh chấp

Scheduler có thể crash sau khi repair thật sự hoàn tất nhưng trước khi cập nhật ledger. Ngược lại, ledger có thể ghi “RUNNING” trong khi repair server-side thất bại. Vì vậy cần:

- **Run ID/plan ID** bất biến cho mỗi logical repair scope.
- Cơ chế lấy lease/lock/fencing theo scope để tránh hai runners cùng repair quá mức trên các node chung.
- **Reconcile khi khởi động lại**: xem trạng thái thật của repair job/session trước khi phát job mới.
- Ghi **evidence pointer** (logs, session IDs, verifier output) để audit.
- Không dựa vào TTL của một lock Cassandra như một transaction cross-system bảo đảm exactly-once. Cần chiến lược fencing và idempotency cho runner.
- Không đặt toàn bộ metadata của hàng triệu scopes vào **một partition nóng** nếu dùng Cassandra làm ledger; chọn data model theo query và capacity.

### 9.4. Dùng service owner review chính sách

Repair planner không nên tự quyết định thay gc_grace, RF, compaction strategy hoặc repair mode khi gần hết deadline. Những thay đổi đó là quyết định DBA/SRE cần đánh giá ảnh hưởng dữ liệu và version. Scheduler chỉ **đo, ưu tiên, từ chối job nguy hiểm, báo động và kích hoạt runbook đã phê duyệt**.

## 10. Admission control: không repair khi cluster không còn headroom

Một repair đúng hạn nhưng làm tất cả request Cassandra timeout hoặc khiến disk full không phải tự động hóa tốt. Planner nên có **resource gate** trước khi runner khởi động công việc mới.

### 10.1. Những chỉ số gate tối thiểu

| Tầng | Metric/kiểm tra | Vì sao quan trọng |
|---|---|---|
| **Topology** | Node UP/NORMAL, schema agreement, DC/rack, ownership | Không khởi động khi cluster đang transition ngoài runbook |
| **Replica availability** | Số replica có thể phục vụ CL | Không làm tăng nguy cơ mất quorum |
| **Storage headroom** | Disk free tuyệt đối và %, forecast SSTables | Streaming/compaction có thể tốn thêm disk |
| **Disk performance** | Read/write IOPS, queue, await/p99 | Repair validation cạnh tranh I/O với CQL |
| **Network** | Bytes/s, retransmits, cross-DC link | Streaming repair có thể dùng WAN/NIC |
| **JVM** | GC pauses, heap/off-heap, CPU | Validation/streaming có thể tăng pressure |
| **Cassandra internals** | Pending compactions, thread pools, dropped tasks | Nút thắt nền đang tồn tại |
| **User-facing** | Successful RPS, p95/p99, timeout/error budget | Bảo vệ dịch vụ Java |
| **Maintenance** | Bootstrap, upgrade, backup copy, restore | Tránh tác vụ nền chồng lấp ngoài kế hoạch |
| **Repair operations** | Session đã chạy, failed ranges, duration | Không chạy chồng scopes/nodes |

### 10.2. Quy tắc concurrency phải tính theo node, không chỉ số job

Hai token ranges khác nhau có thể cùng chạm vào node A/B. Cho chạy đồng thời hai repair vì “khác range” vẫn có thể làm ổ đĩa của A bị tranh tài nguyên.

Nên lập **conflict graph**: mỗi job có tập nodes liên quan; chỉ chạy cùng lúc nếu tài nguyên tổng còn đủ. Với DC WAN, phải có ngân sách link chung. Có thể:

- Giới hạn số repair jobs toàn cluster và mỗi node/DC.
- Giới hạn streaming bandwidth khi công cụ/version cho phép.
- Dành cửa sổ cho backup, bootstrap, upgrade và DR drills.
- Ưu tiên job sát deadline nhưng không ép job khởi chạy khi cluster mất quorum.
- Kích hoạt escalation nếu deadline xung đột với SLO/capacity, thay vì bỏ qua lặng lẽ.

### 10.3. Trạng thái GO / DEFER / STOP / ESCALATE

| Trạng thái | Khi nào | Hành động |
|---|---|---|
| **GO** | Scope hợp lệ, node healthy, capacity đủ, còn deadline | Acquire lease và start theo runbook |
| **DEFER** | Chưa có maintenance window hoặc tạm thiếu headroom nhưng vẫn còn margin | Reschedule rõ thời điểm, giữ cảnh báo nếu lag tăng |
| **THROTTLE** | Repair đang chạy gây p99/IO tăng, tool hỗ trợ điều tiết | Giảm tốc theo cơ chế version-specific |
| **STOP/PAUSE** | Correctness/quorum/SLO/disk an toàn bị đe dọa | Ngừng phát jobs mới; can thiệp job chạy theo runbook |
| **ESCALATE** | Near grace, failed coverage kéo dài, stale replica quá lâu | DBA/SRE quyết định fix-forward/quarantine/rebuild/reconciliation |

**STOP không đồng nghĩa kill Cassandra process.** Một repair session đang chạy có thể cần quy trình terminate/resume đặc thù; không tự xóa metadata repair hoặc SSTables.

### 10.4. Một profile SLO minh họa

~~~yaml
example_policy_only:
  app_read_p99_ms_max: 250
  logical_error_percent_max: 1.0
  min_successful_rps: 900
  disk_free_min_percent: 20
  disk_free_absolute_gib_min: "<estimated-stream-and-compaction-headroom>"
  max_repair_jobs_per_node: 1
  max_cluster_concurrent_repairs: 2
  pause_new_repairs_during:
    - "bootstrap"
    - "restore"
    - "heavy-backup-copy"
  escalate_when_remaining_grace_hours_below: 48
~~~

Các số **250 ms, 900 RPS, 20%, 1 hoặc 2 jobs** đều là giả định của môi trường minh họa, không phải chuẩn Cassandra. Chọn threshold từ SLO và capacity measurements của cluster thật. Với ổ đĩa lớn, % free một mình không đủ dự đoán nhu cầu sửa/stream SSTables.

## 11. Lập lịch không chỉ là CronJob

### 11.1. Cron chỉ đánh thức planner

Kubernetes CronJob hoặc cron máy chủ có thể định kỳ gọi **repair planner**, nhưng planner mới là nơi đánh giá deadline, coverage, health và quyết định scope.

~~~mermaid
sequenceDiagram
    participant T as Cron trigger
    participant P as Repair planner
    participant L as Coverage ledger
    participant H as Health & metrics
    participant R as Approved repair runner
    participant V as Verifier
    T->>P: Wake up
    P->>L: Read table/range/DC coverage
    P->>H: Read RF/topology, p99, disk, active jobs
    P->>P: Compute deadlines & select eligible scope
    P->>R: Acquire lease and execute approved plan
    R-->>P: Execution status + run ID
    P->>V: Verify ranges, replica scope and evidence
    V-->>L: Persist verified success or uncovered scopes
    P-->>T: Summary + alerts
~~~

Nếu cron bỏ lỡ một lần chạy, scheduler cần alert; không chờ lần sau nếu scope đã gần grace. Một trigger có thể gửi lặp, vậy runner phải idempotent theo plan ID và có global lease/fencing.

### 11.2. Mẫu Kubernetes CronJob mang tính minh họa

~~~yaml
# SKELETON: cần triển khai image, RBAC, service account,
# secrets, HA state/lease và approved repair orchestrator riêng.
apiVersion: batch/v1
kind: CronJob
metadata:
  name: cassandra-repair-planner
spec:
  schedule: "0 2 * * *"
  timeZone: "Etc/UTC"
  concurrencyPolicy: Forbid
  startingDeadlineSeconds: 3600
  successfulJobsHistoryLimit: 7
  failedJobsHistoryLimit: 7
  jobTemplate:
    spec:
      backoffLimit: 0
      activeDeadlineSeconds: 7200
      template:
        spec:
          serviceAccountName: cassandra-repair-planner
          restartPolicy: Never
          containers:
            - name: planner
              image: registry.example.invalid/cassandra-repair-planner:<pinned-tag>
              command: ["/app/repair-planner"]
              args:
                - "--mode=plan-and-dispatch"
                - "--policy=approved-staging"
              resources:
                requests:
                  cpu: "100m"
                  memory: "128Mi"
                limits:
                  cpu: "500m"
                  memory: "512Mi"
~~~

**Không áp dụng trực tiếp mẫu này lên cluster thật.** Image và binary ở đây chỉ là placeholder; ví dụ **không cung cấp** một repair runner thực sự và không cấp quyền vào Cassandra. Thuộc tính **spec.timeZone** phụ thuộc Kubernetes version; kiểm tra cluster API hỗ trợ trước khi dùng. CronJob **Forbid** chỉ tránh chồng lấp jobs do **cùng CronJob** quản lý; nó **không phải distributed lock trên các repair tools khác**.

### 11.3. Nếu planner mất kết nối hoặc chạy quá deadline

- **STARTED** không đồng nghĩa COMPLETE.
- Planner restart phải đọc ledger và trạng thái operator repair session trước khi quyết định retry.
- Một job quá **activeDeadlineSeconds** có thể bị Kubernetes kết thúc ở tầng container trong khi repair server-side vẫn đang chạy hoặc cần cleanup theo tool.
- Nếu scheduler downtime kéo dài, **coverage age** tăng; alert đánh giá scope nào quá hạn/không đủ margin.
- Phải đánh dấu **UNKNOWN** cho scope chưa có bằng chứng thành công, không ghi success bằng suy đoán.

### 11.4. Fencing tránh double-execution

Global lease cần bảo vệ khỏi:

1. Hai schedulers cùng nhận một scope.
2. Worker A giữ lease nhưng bị pause, lease hết hạn và worker B nhận scope.
3. Worker A “tỉnh lại” và tiếp tục phát lệnh repair dù không còn quyền.

Giải pháp có thể dùng **lease + fencing token/epoch** được runner kiểm tra trước khi phát thao tác mới, hoặc một repair operator đã hỗ trợ concurrency control; dù dùng cách nào vẫn phải chịu lỗi partial và reconcile.

TTL của một row lock trong Cassandra **không tự bảo đảm exactly-once toàn workflow**. Với LWT claim lock, cần hiểu **[applied] true/false/UNKNOWN**, serial consistency và khả năng lease hết khi job vẫn chạy.

## 12. Java: tính hạn repair và ưu tiên scope không cần chạy nodetool

**Java Driver không cung cấp một câu CQL REPAIR** để gọi trực tiếp. Nhiệm vụ planner có thể viết bằng Java thuần, đọc metadata/ledger/metrics rồi nhờ **operator hoặc công cụ repair được phê duyệt** thực thi.

Ví dụ hàm đánh giá một scope từ thời điểm thành công được xác minh. Chúng ta cố ý không gọi hệ điều hành hoặc thay cluster trong snippet.

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

public final class RepairDeadlinePolicy {
    public enum Urgency {
        MISSING_COVERAGE,
        STALE_TOPOLOGY,
        CRITICAL,
        SCHEDULE_SOON,
        NORMAL
    }

    public static final class Decision {
        public final Urgency urgency;
        public final Instant latestSafeStartEstimate;
        public final Duration timeUntilLatestStart;

        public Decision(Urgency urgency,
                Instant latestSafeStartEstimate,
                Duration timeUntilLatestStart) {
            this.urgency = urgency;
            this.latestSafeStartEstimate =
                latestSafeStartEstimate;
            this.timeUntilLatestStart =
                timeUntilLatestStart;
        }
    }

    private RepairDeadlinePolicy() {}

    public static Decision evaluate(
            Instant now,
            Instant lastVerifiedSuccess,
            Duration gcGrace,
            Duration estimatedRepairDuration,
            Duration retryReserve,
            Duration safetyBuffer,
            Duration notifyWindow,
            boolean scopeVerified,
            boolean topologyMatches) {

        Objects.requireNonNull(now);
        Objects.requireNonNull(gcGrace);
        Objects.requireNonNull(estimatedRepairDuration);
        Objects.requireNonNull(retryReserve);
        Objects.requireNonNull(safetyBuffer);
        Objects.requireNonNull(notifyWindow);

        if (gcGrace.isNegative() || gcGrace.isZero()
                || estimatedRepairDuration.isNegative()
                || retryReserve.isNegative()
                || safetyBuffer.isNegative()
                || notifyWindow.isNegative()) {
            throw new IllegalArgumentException(
                "Durations must be nonnegative; gcGrace > 0");
        }

        if (!topologyMatches) {
            return new Decision(
                Urgency.STALE_TOPOLOGY, null, null);
        }
        if (!scopeVerified || lastVerifiedSuccess == null) {
            return new Decision(
                Urgency.MISSING_COVERAGE, null, null);
        }

        // Estimate only; NOT an assertion of tombstone safety.
        Instant latest = lastVerifiedSuccess
            .plus(gcGrace)
            .minus(estimatedRepairDuration)
            .minus(retryReserve)
            .minus(safetyBuffer);
        Duration remaining = Duration.between(now, latest);

        if (!now.isBefore(latest)) {
            return new Decision(Urgency.CRITICAL, latest, remaining);
        }
        if (remaining.compareTo(notifyWindow) <= 0) {
            return new Decision(
                Urgency.SCHEDULE_SOON, latest, remaining);
        }
        return new Decision(Urgency.NORMAL, latest, remaining);
    }
}
~~~

**Giới hạn rất quan trọng:**

- **lastVerifiedSuccess** phản ánh phạm vi hợp lệ, đúng topology; không lấy timestamp job started.
- **latestSafeStartEstimate** chỉ là deadline kế hoạch mang tính bảo thủ, không bảo đảm tombstones chưa purge.
- Khi **scopeVerified=false** hoặc topology đổi, hàm trả yêu cầu điều tra, không tự khởi repair hay gán thời gian thành công giả.
- Hàm không kiểm tra **node health, RF/DC, disk headroom, maintenance overlap, failed repair sessions**; admission gate bên ngoài phải kiểm tra trước khi runner chạy.
- Một node DOWN quá grace cần escalation ngay cả khi thời gian last success của những replica khác còn mới.
- Production cần clock UTC đồng bộ và thông tin repaired coverage/duration thực tế; không dùng local wall-clock không kiểm soát.

### 12.1. Ví dụ áp dụng policy

~~~java
Instant now = Instant.parse("2026-11-21T08:00:00Z");
Instant lastOk = now.minus(Duration.ofDays(7));

RepairDeadlinePolicy.Decision decision =
    RepairDeadlinePolicy.evaluate(
        now,
        lastOk,
        Duration.ofDays(10),
        Duration.ofHours(12),
        Duration.ofHours(12),
        Duration.ofDays(1),
        Duration.ofDays(2),
        true,
        true);

System.out.println(
    "Repair urgency = " + decision.urgency);
// Expected: SCHEDULE_SOON, vì khoảng latest start còn ít.
~~~

Đây là tính toán theo thời gian trong ví dụ, không có I/O hoặc thao tác sửa cluster. Khi có hàng nghìn scopes, planner có thể sắp xếp theo **timeUntilLatestStart tăng dần**, rồi qua admission control để loại các scope chưa đủ điều kiện. Không bỏ qua **CRITICAL/MISSING_COVERAGE** chỉ vì không được start do cluster overloaded; phải cảnh báo owner.

### 12.2. JUnit kiểm thử tình huống hết ngân sách

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.time.Duration;
import java.time.Instant;

import org.junit.jupiter.api.Test;

public class RepairDeadlinePolicyTest {
    private static final Instant NOW =
        Instant.parse("2026-11-21T08:00:00Z");

    @Test
    void marksCriticalWhenNoBudgetToFinish() {
        RepairDeadlinePolicy.Decision result =
            RepairDeadlinePolicy.evaluate(
                NOW, NOW.minus(Duration.ofDays(10)),
                Duration.ofDays(10), Duration.ofDays(1),
                Duration.ofHours(2), Duration.ofHours(12),
                Duration.ofDays(2), true, true);

        assertEquals(
            RepairDeadlinePolicy.Urgency.CRITICAL,
            result.urgency);
    }

    @Test
    void missingCoverageIsNotTreatedAsSuccess() {
        RepairDeadlinePolicy.Decision result =
            RepairDeadlinePolicy.evaluate(
                NOW, NOW.minus(Duration.ofDays(1)),
                Duration.ofDays(10), Duration.ofDays(1),
                Duration.ofDays(1), Duration.ofDays(1),
                Duration.ofDays(2), false, true);

        assertEquals(
            RepairDeadlinePolicy.Urgency.MISSING_COVERAGE,
            result.urgency);
        assertNull(result.latestSafeStartEstimate);
    }

    @Test
    void topologyChangeInvalidatesOldCoverage() {
        RepairDeadlinePolicy.Decision result =
            RepairDeadlinePolicy.evaluate(
                NOW, NOW.minus(Duration.ofHours(3)),
                Duration.ofDays(10), Duration.ofDays(1),
                Duration.ZERO, Duration.ofDays(1),
                Duration.ofDays(2), true, false);

        assertEquals(
            RepairDeadlinePolicy.Urgency.STALE_TOPOLOGY,
            result.urgency);
    }

    @Test
    void marksNormalWhenSufficientPlanningMargin() {
        RepairDeadlinePolicy.Decision result =
            RepairDeadlinePolicy.evaluate(
                NOW, NOW.minus(Duration.ofDays(1)),
                Duration.ofDays(10), Duration.ofDays(1),
                Duration.ofHours(12), Duration.ofDays(1),
                Duration.ofDays(2), true, true);

        assertEquals(
            RepairDeadlinePolicy.Urgency.NORMAL,
            result.urgency);
    }
}
~~~

Unit tests trên chỉ kiểm tra **logic thời gian và coverage**, không chứng minh repair thực sự đồng bộ Cassandra. Các test tích hợp cần replica/failed repair/topology evidence và xác minh kết quả công cụ theo version.

## 13. Java Driver 4.x: đọc schema để lập catalog an toàn

Java Driver dùng để **đọc CQL/schema và quan sát workload**, không phải một API thay thế nodetool repair. Bên dưới là một probe đọc table metadata, phân loại table và chuyển thông tin tới planner.

~~~java
import java.net.InetSocketAddress;
import java.util.ArrayList;
import java.util.List;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class RepairTableCatalogReader {
    public static final class TableOptions {
        public final String tableName;
        public final int gcGraceSeconds;
        public final int defaultTtlSeconds;

        public TableOptions(String tableName,
                int gcGraceSeconds, int defaultTtlSeconds) {
            this.tableName = tableName;
            this.gcGraceSeconds = gcGraceSeconds;
            this.defaultTtlSeconds = defaultTtlSeconds;
        }
    }

    public static List<TableOptions> read(
            CqlSession session, String keyspace) {
        PreparedStatement query = session.prepare(
            "SELECT table_name, gc_grace_seconds, " +
            "default_time_to_live " +
            "FROM system_schema.tables " +
            "WHERE keyspace_name = ?");

        List<TableOptions> results = new ArrayList<>();
        for (Row row : session.execute(query.bind(keyspace))) {
            results.add(new TableOptions(
                row.getString("table_name"),
                row.getInt("gc_grace_seconds"),
                row.getInt("default_time_to_live")));
        }
        return results;
    }

    public static void main(String[] args) {
        // LAB ONLY. Production: configure TLS/auth, DC and secrets.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            List<TableOptions> catalog =
                read(session, "repair_lab");

            for (TableOptions option : catalog) {
                System.out.printf(
                    "table=%s grace=%ds defaultTTL=%ds%n",
                    option.tableName,
                    option.gcGraceSeconds,
                    option.defaultTtlSeconds);
            }
        }
    }
}
~~~

### 13.1. Điều probe này làm được và không làm được

**Làm được:**

- Đọc gc_grace_seconds/default TTL trên những table session đang nhìn thấy.
- Phát hiện table mới, thay đổi grace hoặc retention policy cần planner review.
- Tạo thông tin đầu vào cho **deadline budget** sau khi kết hợp ledger và repair duration.
- Chạy read-only với quyền tối thiểu thích hợp.

**Không làm được:**

- Biết chính xác mọi node trong mọi DC đã nhận một tombstone.
- Chứng minh repair range bao phủ đầy đủ; thông tin này phải đến từ operator/session verifier.
- Kết luận một table có thể hạ grace chỉ từ default TTL.
- Tự đo data size/compaction hoặc token ownership từ schema option duy nhất.
- Khởi động anti-entropy repair qua câu SELECT/CQL thông thường.
- Tự suy **source of truth** của một DELETE nghiệp vụ nếu tombstone đã mất.

### 13.2. Caching catalog và schema changes

Không cần query system_schema cho mỗi request của ứng dụng Java. Scheduler có thể làm **discovery định kỳ** kèm sự kiện schema/topology thay đổi. Tuy nhiên, nếu một ALTER TABLE giảm grace hoặc một table mới được tạo giữa hai lần discovery, cần đánh dấu những scope liên quan **REVIEW_REQUIRED** và đánh giá lại deadline trước khi lập lịch.

Trong trường hợp schema metadata giữa các nodes khác nhau, cần xác minh schema agreement; **đừng start repair với một catalog không ổn định**.

### 13.3. Quản lý credentials

Dùng tài khoản chỉ đọc cho catalog/metrics khi có thể, và tài khoản riêng có quyền sửa cho operator repair. Không cho ứng dụng API của người dùng quyền kích hoạt nodetool repair. Secrets phải qua cơ chế quản lý được phê duyệt; không hardcode password/contact point production trong tài liệu hoặc log.

## 14. Metrics và nodetool: bằng chứng cho coverage, không chỉ CPU

### 14.1. Lệnh quan sát chỉ đọc

Theo cú pháp và khả năng hỗ trợ của Cassandra version:

~~~bash
# Node status, DC/rack và trạng thái JOINING/UP/DOWN.
nodetool status

# Thông tin node và resource usage.
nodetool info

# Streaming/repair network activity (phụ thuộc version).
nodetool netstats

# Pending/dropped thread pool tasks.
nodetool tpstats

# Active compactions và backlog.
nodetool compactionstats

# SSTable/read/write/tombstone statistics của table.
nodetool tablestats repair_lab.events_by_tenant_day

# Partition-size/row-size histograms nếu phiên bản hỗ trợ.
nodetool tablehistograms repair_lab events_by_tenant_day

# Snapshot retention nếu cần giải thích disk headroom.
nodetool listsnapshots
~~~

Chỉ nhìn một snapshot của **nodetool netstats** không đủ tính streaming throughput; cần các mẫu theo thời gian và phân biệt bytes sent/received/failed sessions. Tương tự, **nodetool status = UN** không chứng minh anti-entropy repair đã hoàn thành.

### 14.2. Repair runner phải ghi bằng chứng hoàn tất

| Nhóm dữ liệu | Trường cần có |
|---|---|
| **Plan identity** | Cluster, planId, runId, mode/version |
| **Scope** | Keyspace/table, token ranges, DC/replicas |
| **Timing** | Enqueued, started, completed, verified timestamps |
| **Result** | COMPLETED/PARTIAL/FAILED/UNKNOWN và failed scopes |
| **Progress** | Validation ranges, streaming sessions/bytes, pending tasks |
| **Resource** | Per-node disk/CPU/GC/network, compaction backlog |
| **Service** | Successful RPS, p95/p99, Read/WriteTimeout, Unavailable |
| **Audit** | Tool/operator version, repair command profile, log pointers |
| **Topology** | Token ownership/replica scope khi bắt đầu và xác minh |
| **Safety** | Quorum, disk headroom và stop-gate decisions |

Một verifier tốt **đối chiếu scope dự kiến với scope đã được tool thực sự đánh dấu complete**. Nếu một table có 10 ranges và chỉ 9 thành công, đánh dấu PARTIAL và giữ range thứ 10 trong queue/alert.

### 14.3. Correlate repair với lỗi của ứng dụng Java

Giả sử repair làm disk await tăng; ứng dụng Java thấy **DriverTimeoutException/ReadTimeoutException/OverloadedException**. Cần kết hợp timeline:

~~~text
T0  : healthy baseline p99
T1  : repair R1 start
T2  : disk read + pending compactions tăng
T3  : read p99 & client timeouts tăng
T4  : operator điều tiết/pause theo runbook
T5  : latency và backlog phục hồi
T6  : repair R1 completed hoặc PARTIAL được verifier ghi nhận
~~~

**Không** tự đồng nhất correlation với causation; kiểm tra backup/ETL, hot partition, GC và traffic changes cùng thời điểm. Dù repair có vẻ là nguyên nhân, các thao tác can thiệp vẫn phải theo **change/incident protocol**.

### 14.4. Alert nên gắn với scope và hành động

Ví dụ alert:

~~~json
{
  "alert": "REPAIR_COVERAGE_NEAR_DEADLINE",
  "cluster": "staging-cassandra-a",
  "keyspace": "repair_lab",
  "table": "events_by_tenant_day",
  "dc": "dc1",
  "range_id": "range-07",
  "last_verified_success_utc": "2026-11-14T12:00:00Z",
  "gc_grace_seconds": 864000,
  "estimated_repair_hours": 18,
  "remaining_start_budget_hours": 36,
  "last_job_state": "PARTIAL",
  "next_action": "DBA review failed ranges and health gates"
}
~~~

JSON chỉ là **mẫu dữ liệu giả định**, không phải metric/alert mặc định của Cassandra. Trong production, cần lưu **cấu hình thực, UTC, source metrics và owner**; tránh log raw tenant keys, payload, secrets hoặc IP/hostname nhạy cảm vào kênh rộng.

## 15. Xử lý job lỗi: partial, retry, unknown và resume

### 15.1. Bảng quyết định theo trạng thái

| Sự kiện | Ledger | Hành động đúng |
|---|---|---|
| Job đã scheduled nhưng chưa chạy | PLANNED | Kiểm tra trigger/queue và deadline |
| Job đang chạy bình thường | RUNNING | Theo dõi SLO, I/O, progress và lease |
| Một số ranges complete, số khác fail | PARTIAL | Giữ completed evidence; lập plan cho uncovered ranges |
| Node/coordinator chết giữa repair | UNKNOWN hoặc FAILED theo evidence | Đọc session/tool status trước khi phát lại |
| Chỉ validation xong, streaming fail | PARTIAL/FAILED | Không ghi whole-range success |
| Ledger không update dù tool hoàn tất | VERIFYING/UNKNOWN | Reconcile bằng runId/session evidence |
| Topology đổi giữa job | STALE_TOPOLOGY hoặc ESCALATE | Đánh giá lại owners/ranges, không dùng scope cũ |
| Outage vượt grace, stale replica quay lại | AT_RISK/ESCALATE | Theo runbook DBA, không repair mù |
| Disk/correctness SLO vượt stop gate | PAUSE/STOP | Dừng dispatch job mới, can thiệp job đang chạy theo tool |
| Job lặp do scheduler restart | DEDUP/RECONCILE | Kiểm tra lease/fencing, không khởi chồng |

### 15.2. Exponential backoff chỉ là điều kiện phụ

Retry repair session có thể có ảnh hưởng tài nguyên lớn, không giống retry SELECT. Tăng số lần thử không làm thay đổi node DOWN, TLS/auth sai, disk full hoặc WAN partition.

Một chính sách minh họa:

~~~text
on FAILED:
  1. Record exact uncovered scopes and error taxonomy.
  2. If configuration/auth/disk/full quorum issue:
       ESCALATE, do not blind-retry.
  3. If transient and still enough grace/deadline:
       schedule retry with bounded backoff/jitter.
  4. Before retry:
       recheck topology, health, active sessions and lease.
  5. After completion:
       verify full scope, update last_verified_success.
  6. On repeated failures or near deadline:
       page DBA/SRE; do not silently wait for next cron.
~~~

**Không khẳng định một retry có thể bắt đầu từ byte/step đã chạy dở.** Resume behavior phụ thuộc version, tool và repair mode. Nếu phải chạy lại scope hoàn chỉnh, tính thêm Dmax và capacity vào deadline.

### 15.3. Dừng giữa chừng khác xóa công việc đã làm

- Dừng planner chỉ ngăn **phát job mới**, không bảo đảm server-side sessions đã dừng.
- Khi coordinator disconnect, repair có thể có state cần cleanup/inspection.
- Không xóa log/temporary metadata/SSTables bằng tay khi chưa được DBA xác nhận.
- Một token range hoàn thành trước khi job fail có thể hoặc không được công cụ xem như committed tùy mode/version; verifier phải dựa trên semantics của tool.
- Đừng đánh dấu success cho cả table chỉ vì job đã chạy đủ thời lượng dự kiến.

### 15.4. Fail-open và fail-closed

Khi hệ monitoring/ledger không trả lời, có hai lựa chọn xấu:

- **Fail-open:** cứ chạy repair mà không kiểm tra scope, health hay conflict; có thể làm cluster quá tải.
- **Fail-closed tuyệt đối:** bỏ mọi repair trong nhiều ngày, khiến coverage quá hạn.

Cách đúng là **UNKNOWN + escalation có owner**, cho phép vận hành qua runbook có kiểm soát/override có audit khi cần. Không tự cấp quyền sửa cluster từ một code path fallback.

## 16. Tác vụ nền chồng lấp: repair, bootstrap, compaction và backup

Cassandra dùng chung disk/network/CPU cho CQL reads/writes và maintenance. Khi repair chạy với các tác vụ khác:

~~~text
CQL read/write       -> coordinator + replica disk/commitlog/memtable
Repair validation    -> SSTable reads + CPU/IO
Repair streaming     -> Network + disk read/write
Bootstrap/replace    -> Token ownership + SSTable streaming
Compaction           -> SSTable reads/writes + CPU
Backup snapshot      -> SSTable hard-link retention
Backup copy/upload   -> Disk reads + network/compression
~~~

Nếu scheduler chỉ biết deadline mà không có health/capacity gate, nó có thể kích hoạt nhiều repairs khi bootstrap/backup đang tiêu thụ phần lớn I/O.

### 16.1. Test tác vụ riêng trước khi thử chồng lấp

| Test | Condition | Chỉ số cần giữ |
|---|---|---|
| **C0** | Baseline, không start maintenance mới | Successful RPS, p99, errors, disk, GC |
| **R1** | Một repair scope | Duration, validation/stream bytes, p99 impact |
| **R2** | Hai repairs không conflict dự kiến | Per-node disk/network, queue, p99 |
| **B1** | Backup copy riêng | Disk read/network impact |
| **X1** | Repair + backup được phê duyệt | Phi tuyến queue, SLO, stop gates |
| **C1** | Recovery after maintenance | Backlog/latency trở về baseline |

Nếu một repair đơn lẻ đã vi phạm SLO, không thử tăng concurrency như “tối ưu throughput” trước khi sửa capacity/điều tiết.

### 16.2. Một ví dụ headroom disk

Giả sử một node có disk read khoảng **300 MiB/s** khi API đang chạy, repair validation dự kiến thêm **220 MiB/s**, trong khi năng lực hiệu dụng với workload tương tự khoảng **450 MiB/s**:

~~~text
Nhu cầu sơ bộ = 300 + 220 = 520 MiB/s
Headroom hiệu dụng = 450 - 300 = 150 MiB/s
Thiếu so với nhu cầu ước lượng = 70 MiB/s
~~~

Đây là **ước lượng sơ bộ**, không phải quy tắc IOPS/latency chính xác. Nếu workload gồm random read/write, queue và p99 I/O có thể xấu trước khi chạm giới hạn MiB/s tuần tự. Scheduler phải xem **latency/queue** và thử load trên staging.

## 17. Lịch vận hành thực tế: một vòng đời đầy đủ

### 17.1. Preflight trước khi khởi repair

- Cluster/topology ổn định, không có node DOWN bất thường.
- Schema agreement, keyspace/table options và RF/DC được xác minh.
- Kỳ repair trước có ledger đầy đủ, scope còn thiếu được biết.
- Backup/recovery point hiện có theo chính sách.
- Không có restore/bootstrap/upgrade overlap ngoài cửa sổ chấp thuận.
- Có disk/network/CPU/GC headroom và SLO green.
- Kế hoạch nêu full/incremental/subrange/DC scope phù hợp tool/version.
- Có quyền operator, lease/fencing, log correlation, rollback/stop plan.
- Có ước lượng duration và điều kiện hết grace/STOP.
- Có người chịu trách nhiệm nếu repair partial/unknown.

### 17.2. Trong khi chạy

1. Ghi **start UTC, runId, planId, topology generation**.
2. Theo dõi từng range, status và replica participants.
3. Thu progress của validation, bytes streamed, retry/failure.
4. Theo dõi app p95/p99, successful RPS, error budget, disk/GC/compaction.
5. Đừng tự đổi consistency level của app để che lỗi.
6. Nếu stop gates vượt, chặn job mới và xử lý session theo runbook.
7. Nếu node mất, phân loại partial/unknown, không để cron gọi job khác chồng lên.
8. Ghi lại mọi quyết định DEFER/PAUSE/ESCALATE và lý do.

### 17.3. Sau khi kết thúc

1. Xác minh actual scope = planned scope theo tool/version.
2. Chỉ cập nhật **last_verified_success_at** cho các scopes thật sự hoàn tất.
3. Giữ failed/uncovered scopes với next deadline; không tự xóa alert.
4. Xác minh node health, schema/topology, SSTable/compaction backlog.
5. Đo recovery window tới khi p99/throughput/error ổn định.
6. Đối soát các khóa mẫu/partition theo CQL nếu test có fixture.
7. Review duration/IO so với Dmax và điều chỉnh lịch/hàng đợi.
8. Lưu evidence, dashboard, incident notes và change record.
9. Cập nhật backup/repair calendar để tránh overlap lần tiếp.
10. Báo kết quả **COMPLETED, PARTIAL, FAILED hoặc UNKNOWN** rõ ràng.

## 18. Năm tình huống vận hành và quyết định lịch

### 18.1. Ca A — Cron báo xanh nhưng một range bị bỏ sót

**Bối cảnh giả định:** Một table có 20 token ranges theo chính sách chia việc. Cron Chủ nhật chạy đều, dashboard job xanh, nhưng verifier thấy:

~~~text
Run 2026-W47:
  19 ranges COMPLETED
   1 range FAILED: dc1/range-R11
  Job controller exit: 0
  Coverage ledger: R11 chưa có verified success 11 ngày
  Table gc_grace_seconds: 864000 (10 ngày)
~~~

**Phân tích:** Exit code 0 không chứng minh repair toàn table. **R11 đã vượt ngân sách theo grace**; cần xem node outage, repairs trước đó, tombstone purge và dữ liệu thực. Nếu R11 chứa deletes chưa phổ biến đủ, có nguy cơ zombie, nhưng chưa kết luận chỉ từ coverage age.

**Quyết định:** **ESCALATE**, DBA điều tra failed range, replica và dữ liệu; giữ evidence, xử lý theo repair/recovery/reconciliation runbook. Sửa verifier để controller không báo COMPLETE khi còn failed scopes.

### 18.2. Ca B — Replica DOWN gần hết grace

~~~text
Table grace = 10 ngày
Node C DOWN 8 ngày
DELETE vẫn được ghi qua quorum A+B
Next regular repair = 3 ngày nữa
Estimated duration = 1 ngày
~~~

Nếu đợi lịch, C có thể vượt grace trước khi đồng bộ. **Cron đúng giờ không đủ.**

**Quyết định:**

1. Chuyển scope thành **AT_RISK** dựa trên outage và repair budget.
2. DBA/SRE xác minh node health, token ownership, delete history và recovery path.
3. Không tự buộc node C quay lại phục vụ khi nghi stale data.
4. Ưu tiên phục hồi an toàn, repair/rebuild/reconciliation qua runbook.
5. Cảnh báo sớm hơn để không đợi tới ngày thứ 10.

### 18.3. Ca C — Repair trùng backup copy làm p99 vượt SLO

~~~text
Baseline read p99 = 140 ms
Repair riêng     = 200 ms
Backup copy riêng= 190 ms
Cả hai đồng thời = 480 ms, có ReadTimeout
SLO đã duyệt     = 250 ms
~~~

Chi phí tài nguyên có thể **phi tuyến** do disk, queue, compaction, GC và network. Không dùng tổng số học p99 để dự báo.

**Quyết định:** Nếu vượt stop gate, ngừng dispatch mới, điều tiết tác vụ theo công cụ được duyệt, dời maintenance và đo lại staging. Nếu coverage gần grace, **ESCALATE capacity/scheduling**, không âm thầm đẩy repair sang tuần sau.

### 18.4. Ca D — Replace node làm ledger không còn đúng

~~~text
Trước replace:
  range R7 owners = A, B, C
  last verified repair = 2 ngày trước

Sau replace:
  range R7 owners = A, B, D
  ledger vẫn ghi A, B, C và status COMPLETE
~~~

Coverage cũ không tự bảo đảm replica D đã nhận đủ dữ liệu/tombstones, dù bootstrap streaming được báo xong.

**Quyết định:** Đánh dấu **STALE_TOPOLOGY**, kiểm tra replace/streaming/schema/token placement, rồi chạy bước repair/verification version-specific. Không sao chép timestamp thành công cũ sang scope mới.

### 18.5. Ca E — Grace bị ALTER xuống thấp hơn lịch

~~~text
T0: gc_grace_seconds = 864000 (10 ngày)
I + D + F + O + B = 8,5 ngày
T1: ALTER TABLE xuống 432000 (5 ngày)
Planner chưa refresh catalog
~~~

Lịch cũ không còn đủ ngân sách. Schema change có thể khiến scope NORMAL trở thành **CRITICAL/AT_RISK**.

**Quyết định:** Schema change phải invalidation catalog và policy review ngay; không đợi cron kỳ sau. Thay grace cần DBA đánh giá với outage/repair/compaction, không chữa bằng cách tăng timeout của repair runner.

## 19. Kiểm thử tích hợp scheduler trên staging

### 19.1. Tách unit tests, orchestrator tests và Cassandra cluster tests

| Loại test | Mục đích | Không chứng minh |
|---|---|---|
| **Java unit tests** | Deadline math, state transition, priority, null/error handling | Anti-entropy repair thực sự chạy |
| **Scheduler integration** | Cron, lease/fencing, ledger persistence, missed runs, retries | Replica hội tụ đúng theo dữ liệu |
| **Repair operator integration** | Tool call, session progress, range verification, failure recovery | Tất cả production topology đều tương đương |
| **Multi-node Cassandra lab** | RF/CL, repair ranges, nodes tạm unavailable, tombstone behavior | Mọi outage dài đều an toàn |
| **Load/fault testing** | p99, throughput, disk/network pressure, stop gates | Source of truth nghiệp vụ tự đúng |
| **Recovery drill** | Restore, reconciliation, coverage after failure | Recovery sẽ luôn đúng nếu version/data khác |

Một **Testcontainers một node RF1** phù hợp kiểm tra CQL schema/TTL cơ bản, không thể chứng minh rằng repair giữa replica RF3 hoặc hai DC đã đầy đủ.

### 19.2. Test mất một lịch chạy

~~~text
T0: ledger R1 verified success gần nhất.
T1: planner CronJob không chạy vì controller downtime.
T2: timeUntilLatestStart giảm dần.
T3: controller phục hồi và quét tất cả scopes.
Expected:
  - Không tự cập nhật R1 last success.
  - R1 được ưu tiên nếu near deadline.
  - Alert missed-run/cadence.
  - Chỉ dispatch sau health gate và acquire lease.
~~~

Điểm xác minh là **ledger và hành động**, không phải số lần CronJob được tạo.

### 19.3. Test repair chỉ hoàn tất 9/10 ranges

~~~text
Plan has R1..R10.
Tool result:
  R1..R9 = COMPLETED
  R10 = FAILED

Expected:
  Table = PARTIAL.
  R1..R9 have verified timestamps only if tool semantics allow.
  R10 retains old last success (or UNKNOWN).
  Alert R10 near deadline.
  No table-wide green status.
~~~

Cần mô phỏng trường hợp **tool exit code 0 nhưng dữ liệu coverage report có failed ranges**. Verifier không được chỉ tin exit code.

### 19.4. Test crash sau thành công nhưng trước khi cập nhật ledger

~~~text
1. Repair runner hoàn tất scope R2 theo tool.
2. Planner crash trước khi ghi ledger.
3. Planner restart, thấy R2 = VERIFYING/UNKNOWN.
4. Query repair operator/session evidence theo runId.
5. Nếu có bằng chứng scope hoàn tất:
     cập nhật last_verified_success_at với completed time thực.
   Nếu không có:
     giữ UNKNOWN và escalates, không giả định success.
6. Không phát hai repair sessions trùng scope khi không chắc
   session cũ còn chạy.
~~~

Đây là **at-least-once trigger với idempotent orchestration**, không phải exactly-once execution tự động do CronJob cung cấp.

### 19.5. Test topology change và RF/DC

Trong staging multi-node, có thể giả lập metadata topology generation đổi (hoặc thực hiện replace qua runbook được phê duyệt). Kiểm tra:

- Ledger cũ được đánh dấu **STALE_TOPOLOGY**.
- Scheduler không tự dùng old owner set để xác nhận mới.
- Planner chờ cluster stable và thực hiện discovery lại.
- Verifier đánh giá ranges/replicas theo topology mới.
- Cross-DC coverage được ghi đúng nếu RF tại nhiều DC khác nhau.
- Không lấy success ở dc1 làm success cho dc2.

### 19.6. Test stop gates khi repair gặp quá tải

Dùng workload Java Driver 4.x có **arrival rate và in-flight giới hạn**, đo baseline p95/p99/success RPS. Chạy một repair scope staging đã được duyệt rồi quan sát:

- Read/WriteTimeout, Unavailable, Overloaded và retry amplification.
- Disk await/queue, compaction backlog, network traffic.
- Repair progress/streaming bytes và tool status.
- Gate **PAUSE dispatch** khi SLO hoặc disk headroom vượt ngưỡng.
- Recovery window sau pause/completion.
- Không tự hạ consistency level của test khi đo, vì sẽ mất tính so sánh.

Nếu fault injection không tạo được tình huống mong muốn hoặc monitoring thiếu, đánh dấu **INCONCLUSIVE**, không buộc PASS bằng cách đổi ngưỡng ngay trong test.

### 19.7. Không tạo zombie trên production để test

Kịch bản nguy cơ zombie yêu cầu missed replica/tombstone purge trong điều kiện đặc biệt. Chỉ xét tái hiện trên **cluster disposable**, dữ liệu tổng hợp, runbook/phê duyệt và recovery path. Không đưa câu lệnh kill node, chỉnh gc_grace_seconds về 0 hoặc sửa SSTable trực tiếp thành “bước chuẩn” của bài học.

Một test an toàn hơn là cho một replica lab tạm không khả dụng trong thời gian **nhỏ hơn grace**, chạy DELETE với CL thích hợp, phục hồi replica và thực hiện repair theo runbook để xác minh dữ liệu không xuất hiện lại. Điều này chứng minh **kịch bản đã thử**, không chứng minh mọi outage an toàn.

## 20. Những lỗi lập lịch repair thường gặp

| Anti-pattern | Hậu quả | Cách sửa |
|---|---|---|
| **Cron thành công = repair thành công** | Failed ranges bị bỏ qua | Xác minh coverage từng scope |
| **Một timestamp last_repair cho toàn cluster** | Không biết table/DC/range nào chưa được sửa | Ledger theo table/range/replica scope |
| **Repair khởi chạy trước grace là đủ** | Job có thể hoàn tất sau hạn | Tính I + Dmax + F + O + B |
| **Dùng average duration thay worst-case** | Range lớn/quá tải vượt deadline | p95/p99 duration, buffer và alert |
| **Hạ gc_grace_seconds để giảm tombstone** | Stale replica có thể gây zombie | Đánh giá outage/repair/compaction |
| **gc_grace_seconds=0 cho mọi TTL table** | Bỏ qua missed replica/late writes | Version-specific review và test |
| **Tin read repair/hints thay anti-entropy** | Không phủ những partition chưa đọc hoặc outage dài | Lịch repair có coverage |
| **Một DC repaired, đánh dấu mọi DC xanh** | Cross-DC replica có thể thiếu delete | Ghi policy/DC coverage rõ |
| **Bỏ qua topology generation** | Success cũ áp cho replica owner mới | Invalidate scope khi topology đổi |
| **Full/incremental pha trộn không hiểu mode** | Repaired state/verification sai | Runbook theo Cassandra version |
| **Coi bytes repaired 99% là 100% an toàn** | Range ít byte nhưng quan trọng bị lỡ | Verify mọi range bắt buộc |
| **Retry repair ngay khi disk full** | Tăng I/O và availability risk | Sửa capacity, admission và backoff |
| **Chạy nhiều jobs khác range nhưng cùng node** | I/O/GC/network contention | Conflict graph và per-node limit |
| **Repair trùng bootstrap/backup heavy** | Tail latency, streaming overload | Maintenance calendar và gates |
| **Tự kill repair session khi p99 tăng** | Partial/pending states cần cleanup | Tool/version-approved pause/stop |
| **Xóa snapshot để trống disk trong incident** | Có thể mất recovery point | Backup verification và retention approval |
| **Tự restart node quá grace rồi repair ngay** | Có nguy cơ lan truyền stale values | DBA risk assessment, quarantine/rebuild nếu cần |
| **Không lưu failure history** | Job lỗi lặp lại mỗi tuần mà không ai biết | Alerts, owner, escalation deadline |
| **Bỏ timestamp complete khi planner crash** | Ledger không khớp trạng thái thật | Reconcile runId/session evidence |
| **Chỉ kiểm tra nodetool status UN** | Node UP nhưng repair/data/SLO chưa đúng | Metrics + verified coverage |
| **Coi repair là backup** | DELETE nhầm hoặc mất DC không phục hồi được | Backup ngoài miền lỗi + restore drill |
| **Bật repair trên service Java HTTP trực tiếp** | Rủi ro quyền và tải, không có governance | Operator riêng, least privilege |
| **Thay CL của app để repair trông ít ảnh hưởng** | Không còn so sánh cùng SLO/consistency | Giữ hợp đồng CL, đo thành thật |
| **Dùng thời gian local/DST cho deadline** | Lịch bị lệch/bỏ chạy | UTC + timezone cấu hình rõ |
| **Giấu UNKNOWN thành COMPLETE** | Các range chưa xác minh bị xóa khỏi queue | State machine và verifier fail-closed với escalation |

### 20.1. Phân biệt sửa dữ liệu với sửa lịch

Nếu đã xuất hiện dữ liệu zombie, **sửa lịch repair tương lai không tự xóa dữ liệu sai hiện tại**. Phải có nguồn sự thật nghiệp vụ/audit/deletion ledger và reconciliation. Ngược lại, chỉ xóa lại một row mà không sửa coverage/outage policy có thể tái diễn sự cố.

### 20.2. Sự phụ thuộc vào version là bắt buộc

Thay Cassandra major/minor version, kiểu compaction, repair tool/operator hoặc topology có thể thay đổi:

- Các repair flags/partitioning/range semantics.
- Cách incremental/full quản lý SSTables.
- Cách tool báo progress, partial failure và resumed state.
- Chi phí validation/streaming và safety khi topology change.
- Monitoring schema và khả năng từ chối repair trong trạng thái thiếu replica.

Do đó một lịch được kiểm chứng trên phiên bản cũ phải được **revalidate** sau upgrade, không giả định mọi cấu hình và thống kê còn giống trước.

## 21. Bài tập tình huống và đáp án gợi ý

### Bài 1 — Lịch 7 ngày có an toàn với grace 10 ngày?

Table có **G=10 ngày**, repair start-to-start **I=7 ngày**, Dmax=2 ngày, retry delay F=1 ngày, outage allowance O=1 ngày, buffer B=1 ngày.

**Hỏi:** Ngân sách theo công thức trong bài có đáp ứng không?

**Đáp án:** Lbudget = 7 + 2 + 1 + 1 + 1 = **12 ngày**, lớn hơn 10 ngày. **Không đạt tiêu chí thiết kế**. Cần rút cadence, giảm duration, tăng headroom, xử lý outage hoặc review lại grace với DBA. Không chỉ thay cron ngày mà bỏ qua failed ranges.

### Bài 2 — Đã chạy repair nhưng không có last verified success

Cron hoàn tất năm phút trước; ledger cho range R7 vẫn là UNKNOWN vì verifier mất kết nối với operator.

**Hỏi:** Có cập nhật last_success_at = hiện tại không?

**Đáp án:** Không. Phải reconcile bằng runId/session results, chứng minh R7 và replica scope đã hoàn tất. Nếu không có evidence thì vẫn UNKNOWN/ESCALATE.

### Bài 3 — Một range không có nhiều bytes

100 ranges, 99 ranges chứa 99,9% bytes đã repair thành công; range còn lại chứa 0,1% bytes nhưng FAILED.

**Hỏi:** Có thể báo 99,9% an toàn?

**Đáp án:** Có thể báo progress theo bytes nhưng **không được báo full coverage**. Range thiếu vẫn có thể chứa tombstones; phải giữ PARTIAL và deadline riêng.

### Bài 4 — GC grace bị giảm bởi migration

Scheduler lập lịch dựa trên gc_grace_seconds=864000. Migration đổi table thành 432000 mà catalog chỉ refresh mỗi tuần.

**Hỏi:** Rủi ro và giải pháp?

**Đáp án:** Lịch theo 10 ngày có thể vượt grace 5 ngày, tạo risk. Schema change cần invalidate/recalculate plan ngay và approval; không chỉ đợi cache refresh định kỳ.

### Bài 5 — Repair chủ yếu validation, ít streaming

Team thấy netstats chỉ có vài MiB streamed nên cho rằng repair không tốn tải.

**Hỏi:** Đúng không?

**Đáp án:** Không. Validation vẫn đọc SSTables, dùng CPU/IO để so sánh dữ liệu; phải đo disk await, CPU/GC, compaction và app p99. Dữ liệu ít khác biệt không đồng nghĩa repair rẻ.

### Bài 6 — Node DOWN 12 ngày, grace 10 ngày

DELETE được ghi khi node C DOWN. Node C quay lại sau 12 ngày, orchestrator muốn tự chạy repair để “bắt kịp”.

**Hỏi:** Có nên tự động xử lý như bình thường?

**Đáp án:** Không. Có nguy cơ tombstone đã bị purge; stale replica có thể lan truyền dữ liệu cũ. Cần **AT_RISK/ESCALATE**, giữ bằng chứng, DBA đánh giá rebuild/quarantine/reconciliation theo runbook. Không mặc định repair sẽ khôi phục delete đã mất.

### Bài 7 — Dùng LOCAL_QUORUM có cần repair không?

RF3 trong dc1, tất cả deletes đều được xác nhận LOCAL_QUORUM.

**Hỏi:** Có thể bỏ repair?

**Đáp án:** Không. Một replica vẫn có thể bỏ lỡ DELETE dù hai replica đủ ACK. Repair phục vụ anti-entropy và phòng rủi ro khi tombstone bị purge; cần coverage theo replica/range.

### Bài 8 — Hinted handoff đã bật

Hệ thống có hinted handoff và nhiều SELECT ở LOCAL_QUORUM. Có thể dùng chúng thay toàn bộ lịch repair?

**Đáp án:** Không. Hints có thời hạn/lifecycle, read repair phụ thuộc đường đọc/version và không bao phủ tất cả partition. Anti-entropy repair theo scope vẫn cần chiến lược đã được DBA kiểm chứng.

### Bài 9 — DC1 đạt 100%, DC2 chưa sửa

Một keyspace có NTS RF3 tại dc1 và RF3 tại dc2. Ledger chỉ có success của dc1.

**Hỏi:** Có thể đánh dấu toàn keyspace repaired không?

**Đáp án:** Không nếu coverage policy yêu cầu dữ liệu ở cả hai DC. Cần hiểu tool semantics/DC scope và ghi kết quả đúng từng replica group, không copy timestamp từ dc1 sang dc2.

### Bài 10 — Hot partition và repair deadline

Một table theo tenant có partition key chỉ là tenant_id, một tenant lớn tạo partition cực nóng khiến repair job chậm hơn Dmax.

**Hỏi:** Cờ SCHEDULE_SOON có đủ sửa vấn đề không?

**Đáp án:** Không. Scheduler chỉ ưu tiên. Cần đo partition size, token skew, disk pressure, có thể redesign bucketing/sharding theo truy vấn. Nếu deadline không thể đạt, ESCALATE capacity/data model thay vì retry vô hạn.

### Bài 11 — Dùng TTL ngắn để bỏ repair?

Bảng session dùng TTL 1 giờ, team đề xuất gc_grace_seconds=0 và không repair vì “mọi dữ liệu đều tự hết”.

**Đáp án:** Chưa đủ cơ sở. TTL expiration, replica offline, late writes, compaction strategy và tombstone purge tương tác phức tạp. Cần review trường hợp immutable/TTL/TWCS cụ thể theo version và yêu cầu đúng đắn; không áp chính sách chung.

### Bài 12 — Overlap trên node A

R1 và R2 là hai token ranges khác nhau, nhưng cả hai cần đọc SSTables trên node A. Scheduler chỉ cho phép tối đa hai jobs toàn cluster nên chạy đồng thời.

**Hỏi:** Vì sao vẫn có thể quá tải?

**Đáp án:** Hai jobs cạnh tranh disk/CPU/network cùng node A. Cần resource conflict graph/per-node concurrency, không chỉ max jobs toàn cluster.

### Bài 13 — Mất kết nối sau job completion

Runner nhận tín hiệu disconnect; sau đó operator báo repair completed, nhưng ledger còn RUNNING.

**Hỏi:** Có nên lập tức chạy lại cùng scope?

**Đáp án:** Không. Phải đối chiếu operator evidence/runId và trạng thái thật, rồi cập nhật last verified success nếu hợp lệ. Tránh double execution do reconnect và concurrency races.

### Bài 14 — Repair và backup cùng giờ

Baseline p99 140 ms; repair riêng 200 ms; backup riêng 190 ms; cả hai cùng lúc p99 480 ms và SLO 250 ms.

**Hỏi:** Thao tác đúng?

**Đáp án:** Tuân thủ stop gate, ngừng dispatch mới và điều tiết/dời maintenance qua runbook, đo lại. Nếu coverage gần hết grace, cần escalation và capacity plan thay vì bỏ lịch im lặng.

### Bài 15 — Full và incremental repair

Team đang chạy incremental repair trên một phiên bản Cassandra, rồi muốn đổi sang full mỗi tuần mà không đánh giá repaired SSTable metadata.

**Hỏi:** Có chấp nhận được không?

**Đáp án:** Không tự động. Phải review version-specific semantics, duration/capacity, state của các sessions đang chạy, phạm vi full/incremental và migration plan. Đảm bảo không để coverage gaps hoặc làm hỏng bookkeeping.

### Bài 16 — CronJob Forbid có thay distributed lease không?

Một Kubernetes CronJob đặt concurrencyPolicy=Forbid nhưng một operator repair khác cũng đang chạy ở cluster.

**Hỏi:** Có chặn overlapping repairs không?

**Đáp án:** Không. Forbid chỉ điều chỉnh những jobs của cùng CronJob; cần shared lease/fencing hoặc operator coordination toàn hệ để phát hiện job khác.

### Bài 17 — Repair xong nhưng data zombie đã có

Một row bị xóa nay xuất hiện lại. Team sửa lịch repair và chạy một phiên repair thành công.

**Hỏi:** Điều đó có đảm bảo xóa row zombie không?

**Đáp án:** Không. Nếu tombstone đã mất, repair có thể làm replica hội tụ trên row cũ. Cần nguồn sự thật nghiệp vụ, audit/deletion ledger, reconciliation và xử lý incident riêng. Sửa lịch chỉ ngăn nguy cơ tương lai.

### Bài 18 — Có nên ưu tiên job có bytes lớn nhất?

Queue có R1 lớn nhưng grace còn 7 ngày; R2 nhỏ nhưng latest safe start chỉ còn 12 giờ.

**Hỏi:** Nên chọn job nào?

**Đáp án:** R2 có deadline cấp bách hơn nếu sức khỏe/lease cho phép. Ưu tiên theo **risk/timeUntilLatestStart** trước, sau đó xét tài nguyên và phân công jobs để tránh starvation. R1 vẫn cần plan đủ duration.

### Bài 19 — Một job chạy lâu hơn Cron interval

Cron chạy mỗi ngày lúc 02:00, repair scope A mất 36 giờ, không có global lock và planner tạo job mới mỗi ngày.

**Hỏi:** Rủi ro gì?

**Đáp án:** Overlap validation/streaming, tăng disk/network/p99, làm ledger mâu thuẫn. Cần scope lease, active session reconciliation, scheduling theo actual duration và tránh phát job mới khi job cũ còn chạy.

### Bài 20 — Số giờ từ last success không kể topology

Range R7 được repair 1 ngày trước; hôm nay node C bị replace bằng D. Scheduler thấy coverage age=1 ngày và đánh NORMAL.

**Đáp án:** Sai nếu ownership đã đổi và scope không được xác minh lại. Phải đánh STALE_TOPOLOGY, cập nhật owner set và thực hiện runbook cho node replacement/bootstrap rồi verify coverage mới.

### Bài 21 — Repair partial nhưng dashboard không cảnh báo

Job FAILED 3 ranges vào thứ Hai, thứ Ba cron được chạy lại nhưng chỉ sửa range đã thành công. Dashboard “weekly run success”.

**Hỏi:** Sửa thuật toán scheduling ở đâu?

**Đáp án:** Ledger phải lưu **failed/uncovered scopes** và ưu tiên chính chúng; verifier so planned vs actual, không dùng cron success làm tiêu chí. Cần alerts/owner theo deadline và test cho partial coverage.

### Bài 22 — Dung lượng tombstone cao, GC grace còn dài

p99 đọc tăng vì nhiều tombstones, team muốn hạ grace từ 10 ngày xuống 1 ngày.

**Đáp án:** Cần chẩn đoán data model, TTL/delete rate, tombstone scans, compaction strategy, repair/outage SLA và disk. Hạ grace có thể tạo zombie risk; chỉ đổi khi đánh giá an toàn và có change approval. Có thể cần bucket/TTL/retention design thay vì “xóa dấu xóa nhanh”.

## 22. Checklist triển khai tự động hóa repair

### 22.1. Chính sách dữ liệu và coverage

- [ ] Catalog đầy đủ table/keyspace, RF/DC, compaction, TTL và gc_grace_seconds thực tế.
- [ ] Phân loại delete-heavy, TTL-heavy, hot partitions và table có yêu cầu correctness đặc biệt.
- [ ] Định nghĩa scope theo **table/token range/replica/DC** và mode/version.
- [ ] Có owner cho mỗi repair policy và quyền review khi grace/schema đổi.
- [ ] Định nghĩa last_verified_success_at từ actual coverage, không từ cron start.
- [ ] Invalidate coverage khi topology/ownership/RF đổi.
- [ ] Có quy tắc coverage toàn DC/multi-DC, không đánh dấu xanh từ một DC.
- [ ] Xác định ngân sách I + Dmax + F + O + B, có buffer thực.
- [ ] Ghi nhận failed/partial/skipped ranges với thời gian và trạng thái.
- [ ] Không dùng TTL ngắn/compaction như bằng chứng có thể bỏ repair.

### 22.2. Scheduler và an toàn vận hành

- [ ] Cron chỉ trigger planner; planner kiểm tra từng scope/deadline.
- [ ] Có shared lease/fencing để tránh duplicate runners.
- [ ] Có health gates cho node status, quorum, schema agreement và topology.
- [ ] Có capacity gates cho disk free/await, GC, compaction, network và app p99.
- [ ] Có per-node/per-DC concurrency, không chỉ global job limit.
- [ ] Không overlap bootstrap/restore/upgrade/backup nặng ngoài policy.
- [ ] Có bounded backoff/retry budget và deadline-aware escalation.
- [ ] Không tự reissue repair khi runner mất connection và chưa xác minh session cũ.
- [ ] Không tự kill repair/nodetool hoặc chỉnh system tables để giải phóng lock.
- [ ] Có PAUSE/STOP/ESCALATE runbook và owner phê duyệt.
- [ ] Có kiểm tra version-specific full/incremental/subrange options.
- [ ] Không dùng một lock TTL làm bảo đảm exactly-once toàn hệ.

### 22.3. Evidence, observability và sự cố

- [ ] Lưu planId, runId, mode/version, topology generation và timestamps UTC.
- [ ] Verifier đối chiếu planned vs actual scopes, không chỉ process exit code.
- [ ] Có alerts near grace, failed ranges, missed cron, stale topology và long outage.
- [ ] Theo dõi validation/streaming, compaction, disk/network/GC và client p99/errors.
- [ ] Có recovery window sau repair và evidence khi backlog trở lại ngưỡng.
- [ ] Có integration tests cho partial repair, planner crash, failed retry và topology change.
- [ ] Có staging multi-node và test CL/RF, không chỉ Testcontainers RF1.
- [ ] Có backup ngoài miền lỗi và restore drill; repair không thay thế backup.
- [ ] Có runbook xử lý replica DOWN lâu hơn grace, suspected zombie/reconciliation.
- [ ] Chỉ log operation IDs và metadata được phép; không lộ secrets/tenant payload.
- [ ] Báo cáo phân biệt COMPLETED, PARTIAL, FAILED, UNKNOWN, STALE và AT_RISK.
- [ ] Không tuyên bố đã QA học thuật hay dữ liệu chắc chắn an toàn chỉ từ job status.

## 23. Tổng kết

**Repair scheduling trong Apache Cassandra là bài toán coverage và thời hạn an toàn**, không đơn thuần là một cron expression. **gc_grace_seconds** cho biết cửa sổ bảo vệ tombstone ở table; nếu replica bỏ lỡ DELETE và repair không phủ đúng phạm vi trước khi dấu xóa có thể bị purge, dữ liệu cũ có nguy cơ sống lại. TTL, compaction và hinted handoff không thay thế được việc hiểu replica/repair coverage.

Một thiết kế tự động hóa bền vững cần **catalog theo table → scope theo token range/replica/DC → ledger với last verified success → ngân sách grace có buffer → scheduler ưu tiên deadline → capacity/quorum gates → runner qua công cụ được duyệt → verifier xác nhận từng scope → retry/escalation khi partial/unknown**.

Với Java Driver, ứng dụng có thể đọc schema/metadata và theo dõi lỗi/tải, còn thao tác repair thực sự phải đi qua **operator/nodetool có quyền và runbook**. Đo p99/read-write throughput, disk/network/GC/compaction cùng tình trạng repair để không đánh đổi availability lấy một job “xanh”. Khi scope đã quá grace hoặc zombie có thể xảy ra, **repair không tự khôi phục business truth**: cần nguồn sự thật, bằng chứng và kế hoạch đối soát có kiểm soát.

**Tiêu chí hoàn thành cuối cùng không phải “job đã chạy”, mà là “đúng dữ liệu và đúng replica scope đã được đối soát trong ngân sách an toàn, có evidence, và hệ thống Java/Cassandra vẫn đáp ứng yêu cầu vận hành”.**
