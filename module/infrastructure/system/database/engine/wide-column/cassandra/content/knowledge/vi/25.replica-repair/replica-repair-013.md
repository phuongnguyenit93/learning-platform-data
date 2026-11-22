# Đối chiếu dữ liệu trước/sau và các giới hạn không thể khôi phục bằng repair trong Apache Cassandra

> **Chương:** Repair  
> **Phạm vi:** Apache Cassandra phân tán với nhiều replica; cách lập bằng chứng trước/sau `nodetool repair`, diễn giải khác biệt replica, phân biệt kết quả đồng bộ kỹ thuật với tính đúng đắn nghiệp vụ, và nhận biết các tình huống cần backup/restore hoặc nguồn dữ liệu độc lập. Ví dụ dùng Cassandra 4.x/5.0; cú pháp tùy chọn phải đối chiếu với bản đang chạy.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **anti-entropy repair** đồng bộ những gì giữa các replica và không làm được những gì.
2. Lập **baseline trước repair** cho một số khóa/partition, token range, table và datacenter thay vì chỉ chạy lệnh rồi giả định đã sửa xong.
3. Dùng CQL, tracing, `nodetool`, log và số liệu vận hành để **đối chiếu trước–sau** mà không nhầm “đọc QUORUM thấy đúng” với “mọi replica đã đúng”.
4. Phân biệt **dữ liệu hội tụ** với **dữ liệu đúng theo nguồn sự thật**; biết vì sao repair không tự phục hồi hàng bị mất trên mọi replica.
5. Phân tích các giới hạn liên quan **tombstone đã purge, zombie data, clock skew, timestamp sai, dữ liệu hỏng, schema và bảng denormalized**.
6. Thiết kế runbook repair an toàn cùng các tiêu chí thành công/rollback cho ứng dụng Java.

Điểm xuyên suốt: Cassandra là cơ sở dữ liệu **wide-column phân tán**. Partition key quyết định token và tập replica; ghi/đọc sử dụng consistency level (CL); SSTable bất biến chứa nhiều phiên bản; compaction dọn dữ liệu đủ điều kiện. **Repair là công cụ đưa các replica của cùng dữ liệu về trạng thái hội tụ**, không phải bộ máy xác định sự thật nghiệp vụ.

## 2. Repair thật sự làm gì?

Với RF=3 trên một datacenter, partition `tenant-a` có ba replica A, B, C. Khi C mất kết nối trong một lần UPDATE, nó có thể giữ phiên bản cũ:

~~~text
                   RF=3, partition tenant-a

                        Coordinator
                             |
                    UPDATE state='PAID'
                    write timestamp = 200
                       /      |      \
                      v       v       x
                  Replica A Replica B Replica C
                  PAID 200  PAID 200   NEW 100
                      \       |       /
                       \   anti-entropy repair
                        \     |     /
                          hòa giải
                             |
                  PAID 200 ở A, B và C
~~~

**Anti-entropy repair** đối chiếu dữ liệu giữa các replica phụ trách những token range tương ứng, phát hiện khác biệt và thực hiện streaming/sửa dữ liệu khi cần. Cassandra dùng cấu trúc như **Merkle tree** để so sánh theo phạm vi, giảm việc chuyển toàn bộ dữ liệu khi nhiều đoạn đã giống nhau. Hệ thống vẫn dựa trên **quy tắc hòa giải của Cassandra** (write timestamp, tombstone, TTL, cấu trúc dữ liệu) để xác định trạng thái cuối.

Không nên hiểu `nodetool repair` là:

- Lệnh khôi phục một bản ghi đã mất **không còn ở bất kỳ replica nào**.
- Công cụ truy xuất lịch sử DELETE/UPDATE đã bị garbage collect.
- Cơ chế kiểm tra dữ liệu có hợp lệ với **quy tắc nghiệp vụ**.
- Bản sao backup hoặc PITR (point-in-time recovery).
- Công cụ tự sửa mọi lỗi phần cứng, phân vùng không đọc được hoặc file SSTable hỏng không có bản dữ liệu tốt.
- Công cụ chuyển schema, xây lại secondary index hoặc sửa các bảng khác do ứng dụng nhân bản dữ liệu.

### 2.1. Hội tụ không đồng nghĩa chính xác

| Trạng thái trước repair | Repair có thể làm gì? | Đã đúng nghiệp vụ chưa? |
|---|---|---|
| A/B có `PAID, ts=200`; C có `NEW, ts=100` | Đồng bộ C tới PAID | **Có thể**, nếu PAID là trạng thái mong muốn |
| A/B/C đều có `PAID` nhưng đơn đã được hoàn tiền | Không phát hiện khác biệt replica | **Không**; thiếu sự kiện hoàn tiền ở cả ba |
| A có hàng đúng, B/C thiếu hàng | Có thể truyền dữ liệu hợp lệ từ A sang B/C | Cần xác nhận hàng ở A là phiên bản đúng |
| A/B/C đều thiếu hàng vì lỗi ghi hoặc mất dữ liệu | Không thể tạo lại hàng từ hư không | Phải tìm backup/CDC/audit/nguồn độc lập |
| A/B/C cùng giữ giá trị do client có timestamp sai cực lớn | Có thể chỉ thấy chúng đã giống nhau | Vẫn có thể sai; repair không sửa logic timestamp |
| A/B đã purge tombstone, C có bản ghi cũ | Có thể coi dữ liệu cũ là phiên bản sống và phát tán | Nguy cơ **zombie data** |

**Phép kiểm tra bắt buộc phải có hai tầng:** (1) các replica có hội tụ? (2) kết quả có khớp một **nguồn sự thật độc lập** hoặc bất biến nghiệp vụ được kiểm chứng?

## 3. Hiểu phạm vi: partition, token range, replica và datacenter

Để đối chiếu đúng, trước tiên phải biết **cần so sánh ai với ai**.

~~~text
Keyspace orders
  Replication: NetworkTopologyStrategy
  dc1: RF=3
  dc2: RF=2

Một partition key
    |
  partitioner -> token
    |
    +-- dc1: ba natural replicas
    +-- dc2: hai natural replicas

Repair/đối chiếu phải xác định rõ DC, bảng và token range
thay vì suy từ một node làm coordinator.
~~~

### 3.1. Các phạm vi cần ghi lại trong baseline

| Phạm vi | Điều phải xác định | Lỗi thường gặp |
|---|---|---|
| Keyspace | Replication strategy, RF theo DC | Tưởng RF chỉ có một số chung cho mọi DC |
| Table | Schema, `gc_grace_seconds`, TTL, compaction | Repair một table rồi tuyên bố mọi table đã sửa |
| Partition key | Giá trị khóa dùng để tính token | Đọc sai partition hoặc query không chỉ định khóa |
| Natural replicas | Các node thực sự lưu token range | Nhầm coordinator với node lưu bản sao |
| Token range | Range nào đã repair, range nào fail | Chạy `-pr` trên một node rồi coi đã phủ cluster |
| Datacenter | DC nào tham gia repair | `LOCAL_QUORUM` ở dc1 không chứng minh dữ liệu dc2 |
| Thời gian | Thời gian mutation, thời gian downtime, grace | Repair quá muộn sau khi mất tombstone |

Lệnh hữu ích cho khảo sát:

~~~bash
nodetool status
nodetool describecluster
nodetool version
nodetool getendpoints repair_lab orders tenant-a
~~~

`getendpoints` giúp tìm **natural endpoints của partition key** theo ring; **không chứng minh dữ liệu trên các endpoint đã giống nhau**. Đối với partition key phức hợp, kiểm tra cú pháp CLI của phiên bản đang dùng và cách biểu diễn key.

### 3.2. Consistency level có thể che khác biệt

Giả sử:

~~~text
Replica A: status=PAID, ts=200
Replica B: status=PAID, ts=200
Replica C: status=NEW,  ts=100
~~~

Một lần `SELECT ...` ở `QUORUM` có thể trả `PAID`, bởi RF=3 cần hai phản hồi và giá trị mới hơn thắng khi hòa giải. Điều này **không chứng minh C đã đồng bộ**. Ngược lại, `ONE` có thể trả `NEW` nếu lần đọc trúng C.

Ngay cả khi bạn kết nối cqlsh tới C và đặt `CONSISTENCY ONE`, Cassandra **không cam kết** đáp án chắc chắn đến từ dữ liệu cục bộ của C trong mọi trạng thái cluster/query plan. Coordinator có thể chọn một natural replica khác theo chiến lược đọc. Khi cần khẳng định chính xác dữ liệu một replica cụ thể, cần kết hợp **tracing, công cụ quan sát replica, chỉ số repair** hoặc quy trình kiểm định chuyên dụng của đúng phiên bản; không giả danh SELECT thông thường là “đọc trực tiếp SSTable trên node C”.

## 4. Chuẩn bị baseline trước khi repair

Một kết quả repair “thành công” thiếu baseline rất khó kiểm toán. Cần tối thiểu ba nhóm bằng chứng:

1. **Trạng thái kỳ vọng của bản ghi:** có/không có, giá trị cột, phiên bản nghiệp vụ, timestamp/xóa từ hệ thống ghi nhận sự kiện hoặc sổ kiểm toán.
2. **Trạng thái của Cassandra trước khi sửa:** kết quả đọc cùng một tập primary key, CL, DC, node coordinator, thời điểm, `WRITETIME`/TTL nơi phù hợp, logs/tracing và repair history.
3. **Sức khỏe và phạm vi cluster:** node/rack/DC, token range, keyspace/table, kết quả repair cũ, tuổi tombstone, compaction, streaming và dung lượng đĩa.

### 4.1. Lập danh mục khóa có chủ đích

Chọn tập kiểm tra:

- **Các khóa bị báo lỗi:** ví dụ đơn hàng đáng lẽ là PAID nhưng một client nhìn thấy NEW.
- **Một số partition rải đều token range:** tránh chỉ lấy hàng nóng của một tenant.
- **Hàng đã DELETE:** phải kiểm tra **không xuất hiện trở lại** chứ không chỉ kiểm các hàng sống.
- **Hàng có TTL:** ghi thời điểm hết hạn và kết quả kỳ vọng tại thời điểm kiểm tra.
- **Hàng vừa INSERT/UPDATE, hàng cũ ít được đọc:** giúp bắt những chênh lệch không được read repair thường xuyên chạm tới.
- **Trường hợp ứng dụng có nhiều bảng denormalized:** ghi rõ mỗi bảng là một đối tượng cần đối soát riêng.

Ví dụ bảng bằng chứng **độc lập với dữ liệu cần repair**, được lưu trong ticket vận hành hoặc hệ thống audit tin cậy:

| Primary key | Nguồn kỳ vọng | Trước repair (quan sát) | Sau repair (yêu cầu) |
|---|---|---|---|
| (`tenant-a`, `order-001`) | PAID, business_version=7 | Đôi lúc NEW | PAID, version 7 |
| (`tenant-a`, `order-002`) | Không còn tồn tại sau DELETE | Một số lần đọc vẫn thấy | Không còn hàng |
| (`tenant-b`, `order-003`) | Total=150 | Total=120 trên một luồng đọc | Total=150 |
| (`tenant-c`, `order-004`) | Đã hết TTL | Vẫn còn trên một replica chưa đồng bộ mutation khác | Không còn giá trị sống |

**Nguồn kỳ vọng phải thực sự độc lập** hoặc có lý do đáng tin: chỉ lấy SELECT QUORUM trước repair rồi gọi đó là “ground truth” có thể hợp thức hóa giá trị sai do timestamp cao hơn.

### 4.2. Chụp bằng chứng schema và topology

Trong cqlsh:

~~~sql
DESCRIBE KEYSPACE repair_lab;
DESCRIBE TABLE repair_lab.orders;
~~~

Trong shell:

~~~bash
nodetool status
nodetool tablestats repair_lab.orders
nodetool compactionstats
~~~

Lưu lại thời điểm chụp, version Cassandra, CL của từng query, local DC và event ID. `tablestats` cho biết thống kê table như số SSTable và một số metrics đọc/tombstone, **không phải danh sách từng cell lệch giữa replica**. Tránh diễn giải sai counter tổng hợp.

### 4.3. Không dùng COUNT(*) như phép chứng minh duy nhất

`SELECT COUNT(*) FROM ...` trên tập dữ liệu lớn có thể quét phạm vi rộng, gây tải cao và không chứng minh hai tập hàng bằng nhau: cùng số lượng vẫn có thể **khác khóa, giá trị hoặc tombstone**.

Đối chiếu tốt hơn là:

- So sánh **cùng primary key** và các cột quan trọng, phiên bản nghiệp vụ, write timestamp nơi phù hợp.
- Giới hạn query theo partition key; phân trang khi một partition lớn.
- Dùng checksum/hash ở tầng ứng dụng **chỉ khi** dữ liệu đã được canonicalize và phạm vi chọn rõ ràng; cùng checksum chỉ là tín hiệu phụ, không thay audit nguồn sự thật.
- Ghi rõ việc đối soát là **toàn bộ**, **theo sampling** hay **theo tập khóa nghi ngờ**. Không nói “đã kiểm 100% dữ liệu” nếu chỉ chọn 20 khóa.

## 5. Cách quan sát trạng thái trước–sau mà không tự làm sai kết quả

Một số đường đọc có thể kích hoạt **read repair**, khiến replica thay đổi ngay trong lúc bạn đang kiểm tra. Đây là lý do cần xác định “đo kiểm” là **quan sát nguyên trạng** hay **kiểm thử khả năng hội tụ**.

### 5.1. CQL có thể cho biết gì?

~~~sql
CONSISTENCY ONE;

SELECT order_id, status, amount, business_version,
       WRITETIME(status) AS status_write_ts
FROM repair_lab.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;

CONSISTENCY QUORUM;

SELECT order_id, status, amount, business_version,
       WRITETIME(status) AS status_write_ts
FROM repair_lab.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

`WRITETIME(status)` trả timestamp ở mức **microsecond** của **cell sống**, không phải lịch sử DELETE hoặc toàn bộ phiên bản trong tất cả SSTable. Nếu dữ liệu bị tombstone che, một SELECT không cho bạn trực tiếp bản ghi tombstone ở từng replica.

### 5.2. Tracing hữu ích nhưng có giới hạn

~~~sql
TRACING ON;

SELECT order_id, status
FROM repair_lab.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;

TRACING OFF;
~~~

Tracing có thể chỉ ra các endpoint tham gia, digest mismatch hoặc hoạt động read repair tùy phiên bản và query. **Không bật tracing đại trà ở production** vì tăng overhead; và một trace không thể chứng minh toàn bộ token range đã hội tụ.

### 5.3. Phân biệt ba cách kiểm tra

| Phương pháp | Phát hiện được gì? | Không kết luận được gì? |
|---|---|---|
| SELECT nhiều CL/đầu kết nối | Triệu chứng lệch mà client trải nghiệm | Không chắc đã đọc đúng từng replica |
| Trace có kiểm soát | Replica phối hợp và dấu hiệu mismatch của query đó | Không bao phủ mọi hàng hoặc thời điểm |
| Repair logs, preview/digest/Merkle tree | Phạm vi so sánh và khác biệt theo token range | Không chứng minh dữ liệu đúng nghiệp vụ |
| Đối chiếu nguồn audit theo primary key | Chênh lệch cụ thể với điều ứng dụng kỳ vọng | Chỉ đúng phạm vi audit/khóa đã kiểm tra |
| Kiểm tra SSTable cục bộ theo runbook offline | Metadata/dữ liệu vật lý của node cụ thể | Không tự xét đồng thời toàn cluster, có rủi ro vận hành |

Nếu yêu cầu xác định rõ “C hiện giữ giá trị gì **trước** khi bị repair”, nên thu thập bằng chứng trước bất kỳ read có khả năng sửa mismatch hoặc job repair; với dữ liệu nhạy cảm, dùng quy trình **snapshot/kiểm định offline** trên môi trường cô lập thay vì chạy thử thay đổi topology trên production.

## 6. Full repair, incremental repair và preview repair

Cassandra có nhiều chế độ repair. Hành vi chi tiết được điều chỉnh qua các dòng 3.x, 4.x và 5.0, nên phải dùng `nodetool help repair`/tài liệu đúng bản trước khi tự động hóa.

| Chế độ | Mục tiêu | Cần thận trọng |
|---|---|---|
| **Full repair** (`--full`) | Đối chiếu lại dữ liệu của phạm vi chọn, không chỉ phần unrepaired | Tốn I/O, CPU, network; cần xác định token range và DC |
| **Incremental repair** | Tập trung dữ liệu chưa đánh dấu repaired, quản lý metadata repaired/pending repair và quá trình anti-compaction theo version | Không tương đương audit toàn bộ lịch sử; sai lịch repair có thể bỏ sót phạm vi |
| **Preview repair** (`--preview` nếu phiên bản hỗ trợ) | So sánh/ước lượng khác biệt mà không thực hiện streaming sửa dữ liệu | Chỉ là tín hiệu chẩn đoán; không thay đối chiếu khóa hoặc repair thành công |
| **Primary-range repair** (`-pr`/`--partitioner-range`) | Giới hạn các primary ranges do node đảm nhận | Chỉ chạy trên **một** node không tự bao phủ cả ring |

Ví dụ trên cluster thử nghiệm:

~~~bash
# Kiểm tra các tùy chọn trước khi chạy theo runbook.
nodetool help repair

# Preview trước khi sửa nếu binary hỗ trợ:
nodetool repair --preview repair_lab orders

# Full repair cho primary ranges của node được gọi:
nodetool repair --full -pr repair_lab orders
~~~

Không tự chạy ba lệnh trên liên tiếp trong production. Với nhiều DC/node, cần một **repair orchestrator** hoặc kế hoạch rõ ràng theo DC, rack, số phiên chạy đồng thời, băng thông và headroom đĩa. Nếu chọn `-pr`, phải hoàn thành kế hoạch trên **tất cả node thích hợp** để bao phủ các primary ranges; không đo coverage bằng số dòng log “repair completed” mà không biết range nào thực sự hoàn tất.

### 6.1. Một repair job chạy xong vẫn chưa đủ

Điều kiện cần để tuyên bố repair có ích:

1. Đúng keyspace, table, datacenter và token ranges đã lên lịch.
2. Tất cả phiên/child tasks cần thiết đều **thành công**, không chỉ coordinator in ra câu bắt đầu/kết thúc.
3. Không có node unreachable, streaming error, compaction/pending repair bất thường hoặc disk full bị bỏ qua.
4. Có bằng chứng đối chiếu sau repair trong phạm vi mục tiêu.
5. Repair hoàn tất **trước khi tombstone có thể bị purge** nếu mục tiêu là tránh zombie data.

**Repair session không xác nhận đúng–sai nghiệp vụ**: nó chỉ đồng bộ theo dữ liệu và timestamp hiện có.

## 7. Chỉ số và bằng chứng nên giữ lại sau mỗi lần repair

| Chỉ số/nhật ký | Trước repair | Sau repair | Cách diễn giải |
|---|---|---|---|
| Node `UN` / unavailable | Ghi topology ban đầu | Xác nhận node tham gia hoạt động | Một node `UN` không chứng minh data synchronized |
| Range cần sửa | Danh sách token range/table/DC | Danh sách range hoàn thành | Tránh “sót một góc ring” |
| Repair job status | Lỗi cũ, phiên đang chạy | Thành công/thất bại, retry | Lệnh trả về không đủ nếu child sessions lỗi |
| Merkle tree/differences | Dự đoán mismatch | Mismatch giảm/hết theo phạm vi | Digest giống nhau không chứng minh business correctness |
| Streaming bytes/errors | Baseline I/O | Lượng truyền và lỗi | Byte bằng 0 có thể là không có khác biệt, **hoặc** phạm vi không thực sự được xử lý |
| Repaired/pending repair metadata | Cần kiểm phiên bản | Xác minh không có trạng thái bất thường | Repair state có thể ảnh hưởng compaction |
| Kiểm tra hàng sống | Giá trị/`WRITETIME`/version | Cùng key, cùng CL và nguồn audit | Chú ý concurrent writes giữa hai lần đo |
| Kiểm tra hàng đã xóa | Không còn hàng? Có nguy cơ zombie? | Vẫn không còn sau repair và qua chu kỳ compaction | Tombstone bị purge có thể khiến repair quá muộn |
| Read latency và tombstones | p95/p99, timeout | Không phát sinh hồi quy | Repair có thể gây tải và ảnh hưởng ứng dụng |

Khuyến nghị lưu một **mã đợt repair**, thời điểm bắt đầu/kết thúc, phạm vi, phiên bản Cassandra, cấu hình, kết quả theo range, đường dẫn log vận hành, số liệu streaming, cùng báo cáo chênh lệch khóa mẫu. Đây là đầu vào thiết yếu cho điều tra sau này.

## 8. Các giới hạn không thể khôi phục bằng repair

### 8.1. Mọi replica đều mất cùng một bản ghi

Giả sử đơn hàng `order-100` đã được API báo ghi thành công, nhưng vì lỗi đường ghi, xóa nhầm hay thao tác vận hành sau đó, tất cả natural replicas hiện không còn hàng:

~~~text
Nguồn nghiệp vụ/audit:
    order-100 tồn tại, state=PAID, version=9

Cassandra tại thời điểm repair:
    A: không có hàng
    B: không có hàng
    C: không có hàng
                   |
             Anti-entropy repair
                   |
       A/B/C vẫn không có hàng
~~~

Merkle trees hoặc các phép so sánh có thể cho thấy các replica **giống nhau hoàn toàn**, vì không replica nào có bản đúng để stream. Không có “lịch sử ẩn” mà repair truy ra từ một bản ghi đã biến mất mọi nơi.

**Cách xử lý:** kiểm tra backup, snapshot, CDC, nguồn sự kiện, write audit hoặc hệ thống chủ dữ liệu; xác định chính xác khóa và phiên bản cần khôi phục; sau đó ghi/restore một cách có kiểm soát và repair nếu cần để đồng bộ replica.

### 8.2. Các replica đều có cùng giá trị sai

~~~text
Ứng dụng mong: trạng thái REFUNDED, version=8

Replica A: PAID, ts=9000
Replica B: PAID, ts=9000
Replica C: PAID, ts=9000

Repair: không phát hiện khác biệt đáng sửa.
~~~

Ngay cả khi một replica có REFUNDED ở timestamp thấp hơn, reconciliation **last-write-wins** có thể ưu tiên PAID vì timestamp cao hơn. Repair có thể làm tình trạng sai **nhất quán hơn**, chứ không “chọn ý định nghiệp vụ đúng”.

Nguyên nhân điển hình: timestamp do client cấp quá lớn, clock skew, sự kiện được xử lý sai thứ tự, replay dữ liệu lịch sử với timestamp không phù hợp hoặc application bug.

**Cách xử lý:** điều tra nguồn phát timestamp, xác định sự kiện hợp lệ từ audit/version nghiệp vụ, khắc phục nguồn ghi sai trước khi sửa dữ liệu. Không giải quyết bằng cách luôn tăng timestamp lên một số cực lớn: hành vi đó có thể tiếp tục che các mutation tương lai.

### 8.3. Tombstone đã bị garbage collect và sinh zombie data

Một replica C bỏ lỡ DELETE; A/B giữ tombstone. Nếu C mất kết nối lâu hơn khoảng `gc_grace_seconds` và A/B **đã purge tombstone** qua compaction đủ điều kiện, C có thể đưa dữ liệu cũ quay lại:

~~~text
T0: A/B/C giữ order-200, ts=100
T1: DELETE order-200, ts=200, CL=QUORUM
    A/B giữ tombstone, C down giữ order-200
T2: Grace hết + compaction đủ điều kiện ở A/B
    A/B không còn bằng chứng xóa
T3: C trở lại, mang order-200 ts=100
T4: Repair/streaming có thể truyền order-200 sang A/B
    => DỮ LIỆU ĐÃ XÓA XUẤT HIỆN LẠI (zombie)
~~~

Tại T4, repair không còn tombstone `ts=200` để biết C là replica sai. Việc **các replica lại giống nhau** có thể chính là thất bại về tính đúng đắn.

**Bài học vận hành:** lịch repair có coverage phải hoàn thành **trước** khi hết grace, với khoảng đệm cho retry. Node down quá lâu cần được đánh giá trước khi cho quay lại/được stream hoặc repair; có thể cần thay node và rebuild từ các replica lành tùy topology. Nếu zombie đã lan, phải dùng log xóa hoặc nguồn sự thật độc lập để xác định và áp dụng lại xóa đúng.

### 8.4. Không có bản replica nào còn đọc được hoặc bản sao đều hỏng

Repair dựa vào replica có dữ liệu hợp lệ để trao đổi. Nếu SSTable corruption, ổ đĩa lỗi hoặc thiếu file khiến **mọi bản sao liên quan đều không đọc được phần dữ liệu đó**, repair không tự sinh lại nội dung. Nếu một số replica vẫn còn bản tốt, khả năng khôi phục phụ thuộc phạm vi corruption, topology và lộ trình vận hành được hỗ trợ.

**Cách xử lý:** ưu tiên bảo toàn bằng chứng, xác minh checksum/disk và backup; dùng quy trình thay node, khôi phục backup/SSTable hoặc công cụ cứu dữ liệu đúng phiên bản. Không xóa các file SSTable nghi lỗi bằng tay để ép repair nếu chưa biết còn bản tốt nào khác.

### 8.5. Schema thiếu, sai mapping hoặc dữ liệu ở bảng khác

Nếu ứng dụng ghi hai bảng phục vụ hai truy vấn:

~~~text
orders_by_id       PK((tenant_id), order_id)
orders_by_customer PK((customer_id), order_id)
~~~

và code chỉ INSERT vào `orders_by_id` mà bỏ qua `orders_by_customer`, repair `orders_by_customer` **không biết** cần tạo hàng từ bảng kia. Hai bảng có tập replica, primary key và mutation riêng.

Tương tự, repair không:

- Chạy migration schema để thêm cột/chỉ mục/bảng bị thiếu.
- Tự sửa lỗi encoding/serialization của client Java.
- Khôi phục một cột đã `DROP` khỏi schema từ source code cũ.
- Xây lại SAI/secondary index khi bài toán là **index cục bộ** (xem lệnh rebuild index đúng version).
- Biến dữ liệu query trả về thành dữ liệu hợp lệ theo constraint nghiệp vụ.

**Cách xử lý:** phân biệt sự cố **replica inconsistency**, **schema inconsistency**, **derived table inconsistency** và **logical data corruption**; mỗi loại cần quy trình phù hợp.

### 8.6. Snapshot/backup cũng có giới hạn riêng

Repair không thể thay cho **point-in-time restore**. Nếu mọi replica đã nhận một DELETE nhầm, hệ thống hiện đúng theo mutation DELETE; repair sẽ không “đoán” rằng người dùng muốn rollback lệnh ấy.

Khôi phục từ snapshot cũ cũng cần kiểm tra:

- Snapshot được chụp **trước hay sau** mutation mong muốn.
- Có mutation hợp lệ sau snapshot cần được replay từ CDC/commit log/audit không?
- Dữ liệu snapshot chứa các hàng đã bị xóa **sau** thời điểm snapshot không? Restore thiếu kiểm soát có thể **tạo zombie mới**.
- Schema, SSTable format, binary version, encryption, replication và token ownership có tương thích không?
- RPO/RTO mong muốn và khả năng phục hồi một tập key chính xác.

Khi cần khôi phục có chọn lọc, ưu tiên chuẩn hóa dữ liệu từ nguồn đã kiểm chứng rồi ghi lại qua CQL/ứng dụng với timestamp được kiểm soát, thay vì chép file SSTable giữa các replica đang sống.

## 9. Repair khác gì với các cơ chế đồng bộ và cứu dữ liệu khác?

| Công cụ/cơ chế | Thực sự làm gì? | Có thay repair được không? |
|---|---|---|
| **Hinted handoff** | Phát lại mutation tạm bị bỏ lỡ trong cửa sổ giữ hint | Không: hint có thời hạn, không bao phủ mọi sai lệch |
| **Read repair** | Sửa mismatch ở dữ liệu thực sự được truy vấn, theo phiên bản/cấu hình | Không: không quét mọi token range |
| **Anti-entropy repair** | So sánh replica trong các range, streaming khác biệt | Chính công cụ đồng bộ replica; không suy sự thật nghiệp vụ |
| **Compaction** | Hợp nhất SSTable, purge tombstone/dữ liệu đủ điều kiện | Không: compaction cục bộ không đối chiếu một replica đang down |
| **Snapshot/backup restore** | Đưa bản dữ liệu từ thời điểm cũ trở lại | Không: có thể mang lại dữ liệu đã xóa, cần đối soát |
| **Node rebuild/bootstrap/replace** | Tạo lại dữ liệu node từ cluster theo topology | Có thể là giải pháp cho node cũ nguy hiểm; không sửa logic sai của nguồn |
| **Rebuild index** | Tái xây chỉ mục cục bộ dựa trên dữ liệu bảng | Không: không truyền dữ liệu base thiếu giữa replica |
| **CDC / event replay** | Phát lại nguồn mutation độc lập nếu còn đầy đủ | Có thể phục hồi dữ liệu logic, nhưng cần idempotency, timestamp và thứ tự đúng |
| **Ứng dụng ghi lại key sai** | Sửa theo nguồn sự thật đáng tin | Có thể giải quyết sự cố nghiệp vụ; vẫn phải xác minh replica hội tụ |

### 9.1. Vì sao compaction và repair phải được phối hợp?

Compaction có thể purge tombstone khi qua grace và các điều kiện an toàn **cục bộ**. Nếu một replica ở xa chưa nhận DELETE, compaction của node khỏe không có quyền chắc chắn về dữ liệu cũ trên node đang down. Vì thế repair phải đồng bộ tombstone kịp thời.

Ngược lại, repair có thể phát sinh SSTable streaming và metadata repaired/pending repair, tác động tới compaction. Theo dõi I/O, disk free và repair/compaction backlog cùng lúc, nhất là khi nhiều bảng có TTL hoặc cập nhật liên tục.

### 9.2. Giới hạn của Merkle tree và “preview không thấy khác biệt”

Merkle tree là cấu trúc hash để so sánh hiệu quả **nội dung hiện có** của replica theo range. Preview không có mismatch chỉ gợi ý những replica/ranges được xét đang đồng nhất theo thuật toán, **không** chứng minh:

1. Một hàng bị xóa nhầm trước đây đã được phục hồi.
2. Mọi partition trong toàn keyspace đều đã tham gia lần preview đó.
3. Dữ liệu hiện có đúng với hệ thống thanh toán hoặc nguồn giao dịch.
4. Không có concurrent write đang thay đổi kết quả.
5. Mọi secondary index, bảng denormalized và backup đều đồng bộ.

Vì vậy cần kết hợp **repair status + kiểm tra mẫu có đối chiếu audit + theo dõi lâu dài**, không tách riêng một metric rồi coi là hoàn tất.

## 10. Khi nào một bản ghi “xuất hiện lại” không phải do repair?

Không phải mọi giá trị bất ngờ sau repair là zombie do tombstone GC.

| Hiện tượng | Lời giải thích khả dĩ | Cách xác minh |
|---|---|---|
| Giá trị cũ xuất hiện sau UPDATE | Bản cũ có write timestamp **cao hơn** do clock skew | `WRITETIME`, client timestamp generator, audit |
| Hàng đã DELETE lại có trạng thái mới | Có INSERT/UPDATE **thật sự mới hơn** tombstone | Request log, timestamp, event sequence |
| Hàng biến mất sau TTL | TTL đã hết hiệu lực theo dữ liệu ghi ban đầu | `TTL(col)` trước khi hết hạn và audit |
| Hai SELECT ONE trả khác nhau | Coordinator chọn các replica khác, chưa hội tụ | Tracing và repair range |
| Quorum trước repair đúng, sau repair vẫn đúng | Có thể trước đó C đã cũ nhưng bị che bởi quorum | Tham khảo logs/repair coverage, không suy C đã sửa chỉ qua SELECT |
| Count thay đổi | Concurrent writes/deletes hoặc phạm vi query thay đổi | Chốt mốc dữ liệu, phạm vi và version |
| Một bảng bị thiếu hàng, bảng khác có | Ứng dụng bỏ sót dual-write hoặc consumer chưa xử lý | Trạng thái CDC/outbox, audit theo hai bảng |
| Hàng cũ tái xuất hiện sau node restart rất lâu | Tombstone đã purge khi node vắng mặt | Timeline downtime, `gc_grace_seconds`, repair history |

**Phân tích timestamp phải cẩn thận:** `WRITETIME` là timestamp của cell sống, không tiết lộ mọi tombstone; một bản ghi có thể bị xóa bởi row/partition/range tombstone với timestamp khác. Dùng log từ nguồn ghi và event ID để tránh kết luận sai.

## 11. Bài thực hành CQL: lập baseline, chạy repair, đối chiếu lại

**Môi trường:** cluster lab Apache Cassandra 4.x hoặc 5.0, ba node cùng datacenter có tên **thực tế** là `dc1`, `cqlsh`, quyền chạy `nodetool` trên cả ba node. Ví dụ RF=3 chỉ dành cho lab; production phải dùng cấu hình đúng topology, không tạo keyspace RF=3 trên cluster chỉ có một node.

### Bước 1 — Tạo bảng phục vụ hai bản ghi mẫu

~~~sql
CREATE KEYSPACE IF NOT EXISTS repair_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': '3'
};

CREATE TABLE IF NOT EXISTS repair_lab.orders (
    tenant_id text,
    order_id uuid,
    status text,
    amount int,
    business_version int,
    note text,
    PRIMARY KEY ((tenant_id), order_id)
) WITH gc_grace_seconds = 864000;
~~~

**Lưu ý:** `tenant_id` là partition key; `order_id` là clustering key. Hai order cùng tenant có thể nằm trên cùng tập replica. Khi cần phân tích bao phủ ring, chọn thêm tenant có token phân bố ở các vùng khác nhau.

### Bước 2 — Ghi dữ liệu có lịch sử xác định được

Để dễ quan sát `WRITETIME`, trong **lab trống** dùng timestamp microsecond cố định. Không copy timestamp minh họa này vào nghiệp vụ production.

~~~sql
CONSISTENCY QUORUM;

INSERT INTO repair_lab.orders
    (tenant_id, order_id, status, amount, business_version, note)
VALUES (
    'tenant-a',
    11111111-1111-1111-1111-111111111111,
    'NEW', 500, 1, 'created'
) USING TIMESTAMP 1700000000000100;

UPDATE repair_lab.orders
USING TIMESTAMP 1700000000000200
SET status = 'PAID', business_version = 2
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;

INSERT INTO repair_lab.orders
    (tenant_id, order_id, status, amount, business_version)
VALUES (
    'tenant-a',
    22222222-2222-2222-2222-222222222222,
    'CANCELLED', 100, 1
) USING TIMESTAMP 1700000000000300;

DELETE FROM repair_lab.orders
USING TIMESTAMP 1700000000000400
WHERE tenant_id = 'tenant-a'
  AND order_id = 22222222-2222-2222-2222-222222222222;
~~~

Trong ví dụ này, order `1111...` phải có `status='PAID'` và `business_version=2`, trong khi `amount=500` vẫn mang timestamp của INSERT ban đầu. Order `2222...` có tombstone mới hơn dữ liệu sống nên **không còn được trả về**.

### Bước 3 — Lập baseline độc lập với cluster

Trước khi repair, lưu một bảng xác nhận **kỳ vọng nghiệp vụ** từ nguồn audit thử nghiệm, không suy ra chỉ từ CQL:

| Khóa | Kỳ vọng | Lý do |
|---|---|---|
| `tenant-a/1111...` | PAID, amount=500, business_version=2 | Sự kiện cập nhật thanh toán hợp lệ |
| `tenant-a/2222...` | Không còn hàng | Sự kiện DELETE đã xác nhận |

Sau đó đọc Cassandra, ghi CL, thời điểm, coordinator, kết quả:

~~~sql
CONSISTENCY ONE;

SELECT order_id, status, amount, business_version,
       WRITETIME(status) AS status_ts,
       WRITETIME(amount) AS amount_ts
FROM repair_lab.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;

CONSISTENCY QUORUM;

SELECT order_id, status, amount, business_version,
       WRITETIME(status) AS status_ts,
       WRITETIME(amount) AS amount_ts
FROM repair_lab.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;

SELECT order_id, status
FROM repair_lab.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 22222222-2222-2222-2222-222222222222;
~~~

**Kỳ vọng trong cluster khỏe:** PAID, amount 500, version 2; status timestamp `1700000000000200`, amount timestamp `1700000000000100`; order 2222 không có hàng. Chạy `SELECT ONE` ở nhiều coordinator có thể mang lại các kết quả giống nhau khi không có lỗi; bài này không đòi phải cố tạo inconsistency.

### Bước 4 — Xem replica và phạm vi repair

~~~bash
nodetool status
nodetool getendpoints repair_lab orders tenant-a
nodetool tablestats repair_lab.orders
nodetool help repair
~~~

Ghi nhận danh sách endpoint, version, các node đang Up/Normal và token range phục vụ table. Trong lab nhiều DC, mặc dù `getendpoints` cho biết endpoint, không suy rằng tất cả replica thuộc cùng DC.

### Bước 5 — Preview/đo trước nếu binary hỗ trợ

~~~bash
# Lệnh chỉ minh họa tùy chọn; xác nhận trong "nodetool help repair".
nodetool repair --preview repair_lab orders
~~~

Preview là công cụ **chẩn đoán**, không được xem là repair đã xảy ra. Nó có thể tốn I/O/network để tạo Merkle trees. Nếu log báo không có khác biệt, điều đó phù hợp lab đang đồng bộ, nhưng **không chứng minh độ đúng nghiệp vụ** của cả bảng.

### Bước 6 — Repair với phạm vi có kiểm soát

~~~bash
# Trên một node lab, sau khi được phép thực hiện repair.
nodetool repair --full -pr repair_lab orders
~~~

Để phủ **toàn bộ primary ranges**, điều phối cùng mẫu lệnh trên **những node cần thiết** theo lịch, không chạy tất cả đồng thời tùy tiện. Với ba node lab, việc chỉ hoàn tất lệnh trên node A không chứng minh mọi range của B/C đã được sửa.

Theo dõi:

- Kết quả command và các dòng về range/session thành công hay lỗi.
- Node availability, streaming, disk free, compaction.
- Phạm vi token range còn lại chưa repair.
- Tình trạng repair fail/retry và nguyên nhân.

Chỉ khi tất cả range theo kế hoạch đã hoàn tất mới ghi `repair coverage = COMPLETE`; nếu chưa, ghi `PARTIAL` kèm danh sách thiếu.

### Bước 7 — Kiểm tra sau repair

Chạy lại **cùng các câu SELECT**, cùng tập khóa, ghi mốc thời gian và CL. So sánh theo mẫu:

| Phép đối chiếu | Trước | Sau (kỳ vọng) | Tiêu chí |
|---|---|---|---|
| `order 1111 status` | PAID hoặc có thể cũ ở replica lệch | PAID | Khớp audit, không chỉ khớp đa số replica |
| `WRITETIME(status)` | 1700000000000200 hoặc cũ | 1700000000000200 | Mutation mới nhất theo mô hình lab |
| `amount` | 500 | 500 | Giá trị không bị update ngoài ý muốn |
| `business_version` | 2 | 2 | Khớp audit nghiệp vụ |
| `order 2222` | Có thể còn trên replica trễ | Không có hàng | Không zombie; tombstone vẫn đủ tuổi/đã lan |
| Repair range coverage | Chưa ghi nhận | Toàn bộ phạm vi mục tiêu hoàn tất | Không chỉ một node |
| Error/timeout | Baseline | Không có lỗi mới | Theo dõi cả dịch vụ Java |

**Tình huống không có khác biệt từ đầu:** Lệnh repair vẫn có thể chạy bình thường, streaming gần như không phát sinh. Đây không phải thất bại của bài thực hành. Giá trị bài học nằm ở **quy trình kiểm chứng và giải thích giới hạn**, không phải tạo lỗi nhân tạo bằng cách phá cluster.

### Bước 8 — Tình huống tư duy: C bỏ lỡ UPDATE

Không cần thật sự ngắt node, hãy điền kết quả mong đợi:

~~~text
A: PAID, ts=200; business_version=2
B: PAID, ts=200; business_version=2
C: NEW,  ts=100; business_version=1

Khi repair đầy đủ:
  Nếu dữ liệu ở A/B còn nguyên, C hội tụ về PAID/version 2.

Nếu A/B cũng đã mất cả hai mutation hoặc cùng giữ trạng thái sai:
  Repair không có nguồn nào để tạo lại sự kiện đúng.
~~~

Với lab đã được cho phép thử lỗi thực tế, nếu muốn kiểm chứng C bị gián đoạn cần thiết kế riêng fault injection, kiểm C nhận hint hay không, trạng thái mutation sau khi hồi phục, repair theo phạm vi và rollback lab. **Không thử giữ node offline lâu hơn grace trên production để tái hiện zombie.**

## 12. Đối chiếu từ ứng dụng Java

Ứng dụng Java dùng Cassandra Driver 4.x có thể thu thập snapshot logic của một hàng, kèm write timestamp của một số cột, rồi so với **nguồn nghiệp vụ đáng tin**. Driver không có API “đọc cả ba bản sao nội bộ và tự tìm bản đúng” dành cho một câu SELECT thông thường.

Ví dụ Java 17 (nhận `CqlSession` đã cấu hình local DC và tái sử dụng):

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import java.util.UUID;

public final class RepairVerification {
    public record OrderView(
            String status,
            Integer amount,
            Integer businessVersion,
            Long statusTimestampMicros) {}

    public static OrderView read(
            CqlSession session, String tenantId, UUID orderId) {
        SimpleStatement statement = SimpleStatement.builder(
                "SELECT status, amount, business_version, " +
                "WRITETIME(status) AS status_ts " +
                "FROM repair_lab.orders " +
                "WHERE tenant_id = ? AND order_id = ?")
            .addPositionalValues(tenantId, orderId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .build();

        Row row = session.execute(statement).one();
        if (row == null) {
            return null; // Không có hàng sống ở CL được chọn.
        }
        Integer amount = row.isNull("amount")
                ? null : row.getInt("amount");
        Integer version = row.isNull("business_version")
                ? null : row.getInt("business_version");
        Long ts = row.isNull("status_ts")
                ? null : row.getLong("status_ts");
        return new OrderView(row.getString("status"), amount, version, ts);
    }
}
~~~

Một phép xác minh có tính nghiệp vụ dùng **expected state** từ event log, không dùng kết quả của cùng SELECT làm chuẩn:

~~~java
import java.util.Objects;
import java.util.UUID;

UUID orderId = UUID.fromString(
        "11111111-1111-1111-1111-111111111111");

RepairVerification.OrderView actual =
        RepairVerification.read(session, "tenant-a", orderId);

boolean matchesAuditedState = actual != null
        && Objects.equals(actual.status(), "PAID")
        && Objects.equals(actual.amount(), 500)
        && Objects.equals(actual.businessVersion(), 2);
~~~

Đoạn trên là **code đặt trong một phương thức sẵn có biến `session`**; không phải chương trình Java chạy độc lập. Trong production nên:

1. Đọc đúng primary key, query có giới hạn kích thước và page size nếu partition lớn.
2. Dùng CL phù hợp topology; `LOCAL_QUORUM` không chứng minh DC từ xa đã cập nhật.
3. Gắn correlation ID, schema version, DC, thời điểm và audit event version vào log đối chiếu.
4. So sánh cấu trúc dữ liệu canonicalized; đặc biệt chú ý NULL, TTL, collection, timestamp và value encoding.
5. Không tự động ghi bù dữ liệu chỉ dựa vào một lần mismatch: phải xác minh nguồn kỳ vọng và tránh ghi đè mutation hợp lệ mới hơn.
6. Theo dõi timeout và retry; repair có thể làm I/O tăng, khiến ứng dụng Java chậm dù dữ liệu đã hội tụ.

### 12.1. Vì sao không dùng SELECT QUORUM làm chứng chỉ repair?

Với RF=3 một DC, `LOCAL_QUORUM`/`QUORUM` thường chỉ cần hai replica. Nếu A/B có bản đúng, C chưa được sửa, ứng dụng vẫn có thể nhận đúng dữ liệu. Tốt nhất là:

- Dùng kết quả CL cao hơn như **phép kiểm tra trải nghiệm ứng dụng**.
- Dùng **repair completion/coverage** để xác minh đã thực hiện đồng bộ.
- Dùng **audit/business expected state** để xác minh tính đúng.
- Dùng tracing/kiểm tra chuyên dụng khi cần điều tra một replica cụ thể.

Ba bằng chứng này **bổ trợ**, không thể thay thế nhau.

## 13. Runbook đối chiếu trước–sau repair trên production

Mục tiêu của runbook không phải “chạy xong command” mà là **biết tập dữ liệu nào đã được kiểm, có sửa được không và còn rủi ro gì chưa xử lý**.

### 13.1. Giai đoạn trước repair: xác nhận an toàn

1. **Định danh sự cố:** ticket, thời điểm phát hiện, tenant/primary keys, nguồn báo lỗi, business impact.
2. **Đánh giá cluster:** node/rack/DC, RF, trạng thái gossip/schema, available disk, streaming/compaction hiện có, version.
3. **Đánh giá tombstone:** `gc_grace_seconds` của các bảng, thời gian node vắng mặt, lần repair thành công gần nhất. Nếu downtime đã vượt grace, **không tự đưa node cũ vào repair**.
4. **Lấy baseline:** primary keys mẫu, trường quan trọng, `WRITETIME` nơi phù hợp, CL/DC, audit expected state, số liệu latency.
5. **Chốt coverage:** keyspace, table, token ranges, replica/DC, full hay incremental, job concurrency, người chịu trách nhiệm.
6. **Sao lưu theo runbook:** snapshot/backup trước thao tác lớn nếu rủi ro cao; lưu schema/config và kế hoạch rollback/restore. Snapshot không thay anti-entropy repair.
7. **Đặt điều kiện dừng:** disk free thấp, node mới down, streaming failures, p99 latency vượt SLA hoặc phạm vi repair không còn hợp lệ.

### 13.2. Trong lúc repair

~~~text
   Kiểm tra node và phạm vi
             |
       Preview nếu phù hợp
             |
      Repair từng batch
        /           \
    Thành công     Thất bại
        |             |
  Ghi coverage    Dừng/điều tra/retry
        |             |
        +-------> Tổng hợp phạm vi
                       |
          Nếu coverage chưa đầy đủ:
          KHÔNG báo "repair hoàn tất".
~~~

Ghi vào ticket:

- Lệnh thực tế và node thực hiện, start/end UTC, phiên bản Cassandra.
- Range/job ID, lỗi hoặc cảnh báo, lượng streaming, CPU/network/disk.
- Các node không tham gia vì lỗi; phạm vi còn phải retry.
- Có concurrent writes, topology changes, backup/restore hay compaction đáng chú ý không.

Không cố tăng vô hạn số job để “kịp deadline”; repair dồn dập có thể làm cluster mất khả dụng và khiến việc xác minh dữ liệu càng khó.

### 13.3. Sau repair: ba cổng kiểm soát

| Cổng | Câu hỏi | Điều kiện đạt |
|---|---|---|
| A — Kỹ thuật | Đã sửa đúng phạm vi replica/range? | Job success theo từng range, không sót node/DC/table trong mục tiêu |
| B — Dữ liệu | Giá trị đọc có khớp kỳ vọng? | Những khóa đối soát đã xác minh, gồm cả khóa DELETE/TTL; chênh lệch được giải thích |
| C — Dịch vụ | Ứng dụng còn hoạt động bình thường? | CL, p95/p99 latency, timeout, disk và repair backlog đạt giới hạn vận hành |

**Chỉ khi cả ba cổng đều đạt mới tuyên bố hoàn tất trong phạm vi kiểm tra đã công bố.** Nếu cổng A đạt nhưng B không đạt, **đừng lặp repair vô hạn**: rất có thể vấn đề là dữ liệu sai ở tất cả replica, timestamp, zombie, nguồn kỳ vọng hoặc bảng ứng dụng khác.

### 13.4. Phân loại kết quả thành bốn nhóm

| Kết quả | Diễn giải | Bước tiếp theo |
|---|---|---|
| `SYNCED_AND_VALID` | Repair coverage đủ, audit mẫu khớp, SLA ổn | Đóng đợt, tiếp tục lịch repair định kỳ |
| `SYNCED_BUT_INVALID` | Replica đã giống nhau nhưng sai nghiệp vụ | Khôi phục theo nguồn sự thật, không chỉ repair lại |
| `PARTIAL_REPAIR` | Range/node chưa được sửa hoặc job lỗi | Retry đúng phạm vi, giữ cảnh báo |
| `UNKNOWN` | Không đủ bằng chứng audit, topology hoặc timestamp | Không khẳng định dữ liệu đúng; mở điều tra bổ sung |

Danh mục này là **quy ước runbook** của bài học, không phải trạng thái API được Cassandra tự xuất ra.

## 14. Chẩn đoán những ca repair không xử lý được

### Ca A: “Repair SUCCESS nhưng đơn hàng vẫn mất”

**Dấu hiệu:** API lưu được order nhưng mọi CL đọc Cassandra đều không thấy; repair báo không còn khác biệt.

**Phân tích:** Có thể order chưa từng được ghi đúng vào tập replica, đã bị xóa trên mọi replica, hoặc restore/TTL làm trạng thái hiện tại thiếu hàng. Repair **không có bản sống nào để stream**.

**Hành động:** tra audit event, CDC/outbox, backup/snapshot, truy vấn CQL xác nhận đúng primary key; xác minh mutation không bị tombstone mới hơn che. Sau khi xác định bản đúng, khôi phục qua quy trình kiểm soát.

### Ca B: “Repair xong hàng đã DELETE lại xuất hiện”

**Dấu hiệu:** node cũ down lâu, khi quay lại rồi repair, hàng bị xóa tái xuất hiện.

**Phân tích:** tombstone có thể đã bị purge trên các replica khỏe, trong khi node cũ vẫn giữ giá trị cũ. Repair **không biết lịch sử DELETE đã mất**.

**Hành động:** cô lập/đánh giá node vừa hồi phục, kiểm timeline `gc_grace_seconds` và repair, đối chiếu audit xóa, xác minh phạm vi ảnh hưởng, áp dụng lại deletion đã kiểm chứng; xem xét chính sách rebuild node quá grace.

### Ca C: “Repair khiến tất cả replica giống giá trị sai”

**Dấu hiệu:** một service Java gửi UPDATE với write timestamp tương lai, từ đó giá trị cũ/không mong muốn lấn át mọi cập nhật sau.

**Phân tích:** LWW so sánh timestamp; repair lan truyền mutation có timestamp cao nhất **theo dữ liệu hiện có**, không xét sự kiện thanh toán đến trước/sau theo nghiệp vụ.

**Hành động:** sửa nguồn timestamp sai, kiểm lịch sử event và lập kế hoạch cập nhật có kiểm soát. Tránh tự ghi timestamp “vô cùng lớn” để cưỡng ép giá trị.

### Ca D: “Repair bảng gốc thành công nhưng trang khách hàng vẫn thiếu”

**Dấu hiệu:** bảng `orders_by_id` có order, nhưng bảng `orders_by_customer` không có.

**Phân tích:** đây là hai bảng denormalized được ứng dụng ghi riêng; anti-entropy repair của mỗi bảng không tự chuyển row từ bảng này sang bảng kia.

**Hành động:** sửa pipeline dual-write/CDC, replay nguồn sự kiện theo idempotent key, đối soát hai mô hình bảng độc lập.

### Ca E: “Preview sạch, nhưng vẫn có hàng sai”

**Dấu hiệu:** Merkle comparison không báo khác biệt; audit chứng minh giá trị chưa đúng.

**Phân tích:** cả ba replica có thể thống nhất trên trạng thái sai, hoặc preview chưa bao phủ dữ liệu cần hỏi.

**Hành động:** đối chiếu phạm vi preview, token ranges và primary key; khi coverage đã đúng, chuyển sang điều tra **logical data corruption**, không mặc định do repair bug.

## 15. Câu hỏi tự đánh giá

**Câu 1.** A/B giữ `status=PAID, ts=200`; C giữ `status=NEW, ts=100`. Full repair còn thông tin đầy đủ sẽ đưa chúng về đâu?  
**Định hướng:** PAID thắng theo timestamp, C có thể hội tụ với A/B.

**Câu 2.** A/B/C đều thiếu cùng một order vốn đã xuất hiện trong audit. Chạy repair nhiều lần có tái tạo order được không?  
**Định hướng:** Không. Phải tìm nguồn dữ liệu sống khác như backup/CDC/event log.

**Câu 3.** SELECT QUORUM trả PAID trước repair. Có thể kết luận C đã giữ PAID chưa?  
**Định hướng:** Không, hai replica có bản mới đã có thể đủ quorum.

**Câu 4.** Một repair command với `-pr` thành công trên node A. Điều đó có nghĩa toàn keyspace đã repair không?  
**Định hướng:** Không; cần chứng minh coverage mọi primary ranges của kế hoạch.

**Câu 5.** Tại sao COUNT(*) bằng nhau ở hai lần đọc không chứng minh dữ liệu đúng?  
**Định hướng:** Số hàng bằng vẫn có thể khác primary key, giá trị, timestamp hoặc tombstone.

**Câu 6.** Nếu C down lâu hơn grace và A/B đã purge tombstone, repair sau khi C trở lại có thể dẫn tới gì?  
**Định hướng:** Zombie data: C phát tán bản ghi cũ khi không còn dấu xóa mới hơn.

**Câu 7.** Ứng dụng Java nhận timestamp không mong muốn ở `WRITETIME(status)`. Repair có tự sửa timestamp theo giờ thực tế không?  
**Định hướng:** Không; phải xác định nguồn timestamp sai và sửa dữ liệu theo nghiệp vụ.

**Câu 8.** Vì sao preview repair không thể thay việc so sánh với audit log?  
**Định hướng:** Nó so sánh replica/ranges, không biết giá trị có hợp lệ với nghiệp vụ hay không.

**Câu 9.** Có nên ngừng repair vì bảng chỉ dùng `LOCAL_QUORUM`, không có truy vấn `ONE`?  
**Định hướng:** Không. Tombstone và replica cũ vẫn có thể gây zombie, read repair không bao phủ mọi range.

**Câu 10.** Một bảng có sai lệch vì consumer không ghi dữ liệu denormalized; repair bảng gốc có cứu bảng đó được không?  
**Định hướng:** Không. Cần sửa consumer và replay nguồn mutation độc lập.

**Câu 11.** Khi nào có thể đóng ticket `SYNCED_AND_VALID`?  
**Định hướng:** Coverage repair thành công, audit mẫu khớp, ứng dụng ổn định, và phạm vi xác minh được ghi rõ.

**Câu 12.** Một snapshot cũ được restore sau DELETE có thể tạo nguy cơ gì?  
**Định hướng:** Đưa dữ liệu đã xóa trở lại nếu không xét timeline, tombstone và nguồn sự thật.

## 16. Tổng kết

~~~text
                   ĐỐI CHIẾU TRƯỚC REPAIR
                     /       |         \
               Audit     Replica/range  CL/trace
               truth      & node state   & timestamps
                     \       |         /
                      \      |        /
                         REPAIR
                  Merkle comparison + streaming
                             |
                      COVERAGE CHECK
                        /         \
                      đủ       chưa đủ
                       |           |
                 ĐỐI CHIẾU SAU    retry/escalate
                       |
             +---------+----------+
             |                    |
      Replicas hội tụ?       Dữ liệu đúng audit?
             |                    |
             +---------+----------+
                       |
               SỨC KHỎE DỊCH VỤ
                       |
                 Kết luận có phạm vi

Repair không thể tạo lại:
  - Bản ghi đã mất ở mọi replica.
  - Ý định DELETE khi tombstone đã purge.
  - Giá trị đúng theo nghiệp vụ khi timestamp sai đã thắng.
  - Hàng do application bỏ ghi vào bảng denormalized khác.
  - Dữ liệu gốc hỏng khi không còn bản/backup tốt.
~~~

**Thông điệp quan trọng nhất:** `nodetool repair` làm các replica **hội tụ theo những mutation còn tồn tại**, chứ không tự tái hiện lịch sử, không biết ràng buộc nghiệp vụ và không thay backup/restore. Vì vậy, cách vận hành đúng là **baseline có nguồn kỳ vọng → repair có coverage → kiểm tra sau bằng cùng tập khóa + audit → xác nhận dịch vụ khỏe**, đồng thời nhận diện sớm khi nhiệm vụ cần chuyển từ *replica synchronization* sang *data recovery*.

## Tài liệu tham khảo

- [Apache Cassandra — Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html) — anti-entropy repair, incremental/full repair, Merkle trees và lý do cần repair định kỳ.
- [Apache Cassandra — nodetool repair](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/repair.html) — các tùy chọn repair, phạm vi node/range và cách thao tác theo phiên bản.
- [Apache Cassandra — Tombstones](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/tombstones.html) — `gc_grace_seconds`, zombie data và compaction.
- [Apache Cassandra — Dynamo architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html) — replication, consistency, hinted handoff, read repair.
- [Apache Cassandra — Storage engine](https://cassandra.apache.org/doc/stable/cassandra/architecture/storage-engine.html) — commit log, memtable, SSTable, LWW và compaction.
- [Apache Cassandra — CQL Data Manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html) — `WRITETIME`, `USING TIMESTAMP`, TTL, UPDATE và DELETE.
- [Apache Cassandra — CQL Data Definition](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html) — replication strategy, primary key, schema và thuộc tính bảng.
