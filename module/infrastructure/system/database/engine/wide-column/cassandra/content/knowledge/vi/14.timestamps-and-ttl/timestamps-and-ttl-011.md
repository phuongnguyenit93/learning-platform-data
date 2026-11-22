# Dữ liệu hết hạn logic, tombstone và thu hồi vật lý trong Apache Cassandra

## 1. Vì sao TTL hết mà dung lượng đĩa chưa giảm?

**Apache Cassandra** là hệ quản trị cơ sở dữ liệu **wide-column phân tán**. Một partition có thể được lưu trên nhiều replica; dữ liệu được ghi vào memtable, sau đó nằm trong các tệp **SSTable** bất biến. Vì vậy, “dữ liệu hết hạn” không đồng nghĩa “byte dữ liệu được xóa khỏi đĩa ngay lúc đó”.

Giả sử ứng dụng lưu một token trong **60 giây** bằng CQL:

```sql
-- Ví dụ minh họa trong một keyspace thử nghiệm đã được chọn.
CREATE TABLE IF NOT EXISTS session_token_by_id (
    session_id uuid PRIMARY KEY,
    token_hash text
);

INSERT INTO session_token_by_id (session_id, token_hash)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'demo-hash-not-a-real-token'
)
USING TTL 60;
```

Sau khoảng 60 giây, Cassandra không còn trả `token_hash` như một giá trị **đang sống**. Tuy nhiên, các SSTable có thể vẫn chứa cell đã hết hạn, metadata xóa và cả các phiên bản cũ. Chúng chỉ được dọn **sau này**, trong các lần compaction phù hợp và khi điều kiện an toàn dữ liệu được thỏa mãn.

Có **ba mốc** cần phân biệt:

1. **Hết hạn logic (*logical expiration*):** cell không còn có hiệu lực để trả về như dữ liệu sống.
2. **Tombstone/metadata xóa:** Cassandra ghi nhớ giá trị đã hết hạn hoặc bị xóa để tránh các bản cũ từ replica/SSTable khác tái xuất hiện.
3. **Thu hồi vật lý (*physical reclamation*):** dữ liệu/tombstone hết vai trò bảo vệ được loại khỏi SSTable khi compaction có thể thực hiện việc đó an toàn.

Các mốc này có thể cách nhau đáng kể; đặc biệt **TTL không phải cam kết xóa vật lý tại một thời điểm chính xác**.

## 2. Timeline: từ cell sống đến compaction

Với một cell ghi lúc `t0` có `TTL = 300 giây` và bảng có `gc_grace_seconds = 864000` (10 ngày, giá trị mặc định phổ biến cho bảng Cassandra), có thể hình dung:

```text
        t0                    t0 + 300 giây                Sau grace + compaction
        |                            |                                |
        v                            v                                v
  GHI CELL MỚI                 HẾT HẠN LOGIC               CÓ THỂ THU HỒI VẬT LÝ
  - value                     - không còn là live         - cần tombstone đủ tuổi
  - write timestamp           - expiration metadata      - xét SSTable chồng lấp
  - TTL = 300 giây            - che phiên bản cũ          - xét an toàn replica
        |                            |
        +-- ttl() giảm dần ----------+
                                     |
                                gc_grace_seconds
                              là khoảng bảo vệ,
                              KHÔNG phải TTL cộng thêm
```

| Thời điểm | Kết quả đọc thông thường | Trạng thái lưu trữ có thể có |
|---|---|---|
| Sau `t0`, trước hết TTL | Cell còn sống; `ttl(col)` dương | Memtable hoặc SSTable chứa expiring cell |
| Khi tới hạn hết TTL | Cell không còn là dữ liệu sống | Expired cell được xử lý như tombstone |
| Trong thời gian grace | Cell vẫn không xuất hiện như live | Metadata xóa còn cần cho reconciliation |
| Sau grace | Cell vẫn không xuất hiện như live | Tombstone **có thể đủ tuổi** để dọn, chưa bảo đảm được dọn |
| Sau compaction an toàn | Cell vẫn không xuất hiện như live | Byte liên quan **có thể được thu hồi** khỏi SSTable |

**Cảnh báo về cách đọc bảng:** `gc_grace_seconds` không có nghĩa “người dùng vẫn đọc được dữ liệu thêm 10 ngày”. Dữ liệu hết TTL đã **vô hiệu logic** trước khi bắt đầu giai đoạn có thể dọn tombstone. Và `TTL + gc_grace_seconds` **không phải** ngày Cassandra chắc chắn xóa xong dữ liệu vật lý.

## 3. Metadata của cell có TTL được dùng thế nào?

Đối với một giá trị thông thường, Cassandra phải theo dõi các thông tin có vai trò khác nhau:

| Metadata | Đơn vị | Mục đích |
|---|---|---|
| **Mutation timestamp** | Micro giây từ Unix epoch | Hòa giải phiên bản theo **last-write-wins (LWW)** |
| **TTL được gán** | Giây | Khoảng thời gian sống của phiên bản cell |
| **Thời điểm hết hạn / local deletion time** | Thời gian ở độ phân giải giây | Xác định khi nào cell hết hạn và thời điểm liên quan thu gom |
| **Thông tin tombstone** | Theo phạm vi xóa | Ngăn bản ghi cũ hiện lại khi hòa giải |

Khi ghi cell có TTL, Cassandra xác lập thông tin expiration từ thời điểm xử lý mutation và TTL. **TTL không được tính bằng cách lấy mutation timestamp cộng số giây TTL**. Client có thể đặt `USING TIMESTAMP` là một mốc lịch sử để hòa giải dữ liệu nhưng giá trị vừa ghi với `USING TTL 60` vẫn có thời gian sống mới xấp xỉ 60 giây, nếu mutation thắng.

Ví dụ minh họa:

```text
value = "active"
write_timestamp = 1700000000000000 µs      # Metadata LWW từ quá khứ
ttl = 60 giây
expiration = thời điểm Cassandra xử lý ghi + 60 giây
```

Độ chính xác của mutation timestamp (µs) cũng **khác** với độ phân giải TTL (giây). Đồng hồ máy tạo timestamp và đồng hồ các node Cassandra cần được đồng bộ; sai lệch đồng hồ có thể gây cả lỗi LWW lẫn quan sát expiration lệch kỳ vọng.

## 4. Tombstone là gì và vì sao không thể xóa ngay?

**Tombstone** là thông tin đánh dấu một giá trị hoặc phạm vi dữ liệu đã bị xóa. Cassandra cần nó bởi replica có thể tạm thời bị mất kết nối, và dữ liệu nằm trong nhiều SSTable **bất biến**.

Ví dụ một partition có bản cũ ở SSTable A:

```text
SSTable A: status = "PENDING" @ timestamp 100
SSTable B: status = "PAID"    @ timestamp 200, TTL 60

Tại thời điểm hết TTL:
  "PAID" không còn là giá trị sống;
  expiration/tombstone của phiên bản timestamp 200
  phải che phiên bản "PENDING" @ timestamp 100.
```

Nếu hệ thống xóa sạch thông tin `PAID@200` mà không bảo đảm phiên bản `PENDING@100` đã bị loại bỏ/che an toàn, dữ liệu cũ có thể **hiện trở lại**. Đây là lý do **xóa logic** và **thu hồi vật lý** cần được tách ra.

### Các phạm vi tombstone thường gặp

- **Cell tombstone:** xóa một cột thông thường hoặc một thành phần của collection.
- **Row tombstone:** xóa một hàng với đầy đủ khóa.
- **Partition tombstone:** xóa phạm vi một partition.
- **Range tombstone:** xóa một dải clustering rows.
- **Expired TTL cell:** giá trị có TTL tự hết hạn; metadata expiration được dùng trong hòa giải và thu gom.

Những dạng xóa này không có cùng chi phí hoặc phạm vi tác động. Xóa một dải hàng lớn, xóa nhiều phần tử collection hay liên tục ghi dữ liệu TTL ngắn có thể tạo nhiều thông tin cần xử lý trong đọc và compaction.

## 5. Expired TTL cell so với `DELETE`: giống và khác

| Đặc điểm | Cell hết TTL | `DELETE` tường minh |
|---|---|---|
| Tác nhân | Thời gian sống của phiên bản cell kết thúc | Một mutation xóa do client gửi |
| Cần thêm request xóa lúc hết hạn? | **Không**, vì hạn đã nằm trong metadata | **Có** một request `DELETE` ban đầu |
| Có vai trò tombstone? | Có, expiration giúp che các bản cũ | Có, deletion marker giúp che các bản cũ |
| Cách xác định thời điểm xóa | Từ metadata TTL/expiration khi ghi | Từ thao tác xóa và thời gian/timestamp tương ứng |
| Có tự giải phóng byte ngay? | Không | Không |
| Quan sát bằng `ttl(col)` sau khi không còn cell sống | Không nhận số âm | Không đọc được timestamp tombstone bằng `ttl()` |

Một điểm tinh tế: replica **đã nhận cell có TTL** có thể tự đánh giá cell đó hết hạn theo expiration metadata mà không cần chờ một request `DELETE` mới. Nhưng nếu một replica **chưa từng nhận phiên bản có TTL mới**, replica đó có thể vẫn giữ **bản cũ không có TTL**. Tombstone/expiration của phiên bản mới và repair vẫn có ý nghĩa quan trọng để ngăn dữ liệu cũ trở lại.

Vì vậy không nên kết luận “TTL không cần tombstone” chỉ vì nó tự hết hạn. Ngược lại, cũng không nên khẳng định mọi replica phải nhận một gói `DELETE` mới khi TTL đến hạn.

## 6. Thực hành CQL: hết hạn logic nhưng hàng vẫn còn

Sử dụng một **keyspace thử nghiệm** đã được tạo và chọn bằng `USE <keyspace>;`. Các ví dụ không sửa dữ liệu production; nếu bảng đã tồn tại với schema khác, dùng tên riêng hoặc kiểm tra schema thay vì giả định `IF NOT EXISTS` sẽ thay đổi định nghĩa.

### 6.1. Tạo bảng

```sql
CREATE TABLE IF NOT EXISTS ttl_gc_lab_by_key (
    cache_key text PRIMARY KEY,
    payload text,
    retained_note text
);
```

### 6.2. Giữ một cell không TTL, ghi một cell có TTL

```sql
-- Bảng không có default_time_to_live nên note không có TTL.
INSERT INTO ttl_gc_lab_by_key (cache_key, retained_note)
VALUES ('expiry-demo-001', 'Keep row visible for inspection');

UPDATE ttl_gc_lab_by_key
USING TTL 20
SET payload = 'temporary-value'
WHERE cache_key = 'expiry-demo-001';

SELECT cache_key,
       payload,
       ttl(payload) AS remaining_seconds,
       writetime(payload) AS payload_write_us,
       retained_note,
       ttl(retained_note) AS note_remaining_seconds
FROM ttl_gc_lab_by_key
WHERE cache_key = 'expiry-demo-001';
```

Ngay sau cập nhật, `payload` còn sống; `remaining_seconds` gần 20. Cột `retained_note` vẫn có giá trị và `note_remaining_seconds` là `null` vì nó không có TTL.

Sau khi TTL 20 giây kết thúc, chạy lại `SELECT`. Khi đó:

- Row vẫn có thể được trả về do `retained_note` còn sống.
- `payload` trở thành `null` trong kết quả đọc; `ttl(payload)` và `writetime(payload)` không trả metadata của một giá trị sống.
- **Không thể kết luận** byte `temporary-value` đã bị xóa khỏi mọi SSTable chỉ bằng kết quả `SELECT` này.

### 6.3. Khi mọi cell dữ liệu cùng hết hạn

```sql
INSERT INTO ttl_gc_lab_by_key (cache_key, payload)
VALUES ('expiry-demo-002', 'short-lived-only')
USING TTL 10;

SELECT cache_key, payload, ttl(payload)
FROM ttl_gc_lab_by_key
WHERE cache_key = 'expiry-demo-002';
```

Ngay sau ghi, row có dữ liệu sống. Khi đã quá khoảng 10 giây và không có mutation khác, truy vấn sẽ không còn trả giá trị `payload` sống; với row chỉ có cell hết hạn, row thường không còn xuất hiện trong kết quả. **Không nên nhầm việc không thấy row với việc Cassandra đã xóa file SSTable.**

**Thực hành có thể đo được:** dùng thời gian chờ đủ dài và xác nhận bằng `ttl()` trước/sau, nhưng không viết assertion “bằng đúng 20 hoặc 0 giây”. Độ phân giải TTL theo giây, thời gian request và đồng hồ server làm số đếm dao động.

## 7. Thực hành CQL: tombstone che một mutation cũ

Ví dụ dùng timestamp thủ công để chứng minh tombstone phải tồn tại để chống một lần ghi **cũ hơn**. Không áp dụng các timestamp giả lập này lên dữ liệu thực.

```sql
INSERT INTO ttl_gc_lab_by_key (cache_key, retained_note)
VALUES ('delete-demo-003', 'Permanent note');

-- Tạo cell payload ở timestamp cố định cũ.
UPDATE ttl_gc_lab_by_key
USING TIMESTAMP 1700000000001000
SET payload = 'old-value'
WHERE cache_key = 'delete-demo-003';

-- Xóa payload bằng tombstone có timestamp lớn hơn.
DELETE payload FROM ttl_gc_lab_by_key
USING TIMESTAMP 1700000000002000
WHERE cache_key = 'delete-demo-003';

-- Một mutation tới sau nhưng mang timestamp thấp hơn tombstone.
UPDATE ttl_gc_lab_by_key
USING TIMESTAMP 1700000000001500
SET payload = 'stale-retry'
WHERE cache_key = 'delete-demo-003';

SELECT payload, writetime(payload), retained_note
FROM ttl_gc_lab_by_key
WHERE cache_key = 'delete-demo-003';
```

`payload` vẫn không có giá trị sống bởi tombstone `@1700000000002000` che `stale-retry@1700000000001500`. Cột `retained_note` còn để giúp quan sát row.

**Lưu ý:** `writetime(payload)` không cho phép nhìn trực tiếp timestamp của tombstone sau khi cell bị xóa. Muốn kiểm tra metadata xóa thực tế cần lịch sử mutation, log hoặc công cụ SSTable phù hợp.

Ví dụ này cũng làm rõ tại sao **thu hồi một tombstone quá sớm** có thể nguy hiểm: trên replica hoặc SSTable khác, phiên bản `old-value` có thể vẫn tồn tại.

## 8. `gc_grace_seconds` làm gì và không làm gì?

`gc_grace_seconds` là thuộc tính **của bảng**, đơn vị **giây**, dùng để xác định khoảng bảo vệ trước khi tombstone đủ tuổi cho việc thu gom. Một giá trị mặc định thường gặp là **864000 giây (10 ngày)**; phải đọc cấu hình thực tế của bảng và phiên bản Cassandra, không mặc định mọi hệ thống đều giữ nguyên.

Ví dụ tạo bảng thử nghiệm có cấu hình rõ ràng:

```sql
CREATE TABLE IF NOT EXISTS ttl_grace_demo_by_id (
    item_id uuid PRIMARY KEY,
    payload text
) WITH gc_grace_seconds = 864000;
```

Hiểu đúng:

- **Không phải TTL:** `USING TTL 60` vẫn làm cell hết hạn logic sau khoảng 60 giây; `gc_grace_seconds` không khiến ứng dụng đọc được cell thêm 10 ngày.
- **Không phải lịch dọn dẹp:** sau grace, Cassandra **có thể** xem xét loại tombstone trong compaction nếu an toàn; không có cam kết rằng đĩa phải giảm dung lượng đúng mốc đó.
- **Không thay thế repair:** nếu một replica đã bỏ lỡ mutation xóa và trở lại quá muộn, việc dọn tombstone có thể khiến dữ liệu cũ được hòa giải trở lại.
- **Không áp dụng như thời gian bảo lưu dữ liệu sống:** cell không có TTL vẫn tồn tại cho tới khi bị mutation khác thay thế/xóa hoặc có quy tắc vòng đời khác.

Với **TTL expiration**, thời điểm gắn với việc đủ tuổi tombstone thường được xét từ **mốc hết hạn**, không đơn giản là “thời gian `INSERT` + grace”. Với **DELETE** tường minh, mốc deletion gắn với thời điểm xóa. Cả hai cần được diễn giải theo metadata nội bộ và thời gian hệ thống; không lấy `writetime()` rồi cộng máy móc `gc_grace_seconds` để suy ngày dọn vật lý.

**Không tự đặt `gc_grace_seconds = 0` để ép Cassandra dọn ngay.** Điều này làm giảm khoảng bảo vệ chống bản ghi cũ từ replica, đặc biệt nguy hiểm khi node bị mất kết nối, repair bị trì hoãn hoặc có snapshot/SSTable chồng lấp.

## 9. Zombie data: kịch bản một replica bỏ lỡ cập nhật có TTL

Xét một partition trên **RF = 3** với ba replica A, B, C. Giả sử ban đầu cả ba đều có `status = OLD@100` **không TTL**.

```text
Thời điểm t0:
       A: OLD @100            B: OLD @100          C: OLD @100
                                                      |
                                                  C mất kết nối

Thời điểm t1:
       A: NEW @200, TTL 60   B: NEW @200, TTL 60   C: OLD @100

Thời điểm t1 + 60 giây:
       A: NEW hết hạn         B: NEW hết hạn        C: OLD vẫn sống
          tombstone @200         tombstone @200

Nếu tombstone được dọn thiếu an toàn và C quay lại:
       C có thể phát tán OLD @100, làm dữ liệu cũ hiện trở lại.
```

Trong lúc các tombstone `@200` còn hiệu lực và được hòa giải, chúng che `OLD@100`. Nhưng nếu chúng đã bị thu gom trước khi trạng thái của C được đối chiếu, hệ thống có thể không còn đủ dấu vết về phiên bản mới đã hết hạn để loại bản cũ.

Tình huống minh họa không khẳng định **mọi** cell TTL sẽ sống lại khi mất node. Replica nào đã có expiration metadata của `NEW@200` có thể tự xác định nó hết hạn. Rủi ro phụ thuộc mutation mà replica đã nhận, bản cũ nào còn tồn tại, thời gian mất kết nối, repair và chính sách thu gom tombstone.

**Nguyên tắc vận hành:** lên lịch repair và quản lý thời gian node offline sao cho các replica được đồng bộ **trước khi thông tin xóa có thể bị loại bỏ an toàn theo chính sách**. Đừng giả định hinted handoff đủ thay thế repair trong mọi tình huống.

## 10. Từ đủ tuổi đến thu hồi: compaction cần điều kiện gì?

Cassandra lưu dữ liệu trong các **SSTable bất biến**. Việc xóa một giá trị không lập tức chỉnh sửa byte trong mọi SSTable; hệ thống cần compaction để hợp nhất phiên bản và loại dữ liệu/tombstone không còn cần thiết.

Một tombstone **đủ tuổi** không phải lúc nào cũng **được purge ngay**:

1. Tombstone đã vượt khoảng bảo vệ do cấu hình cho phép.
2. Cassandra phải tránh để lộ một phiên bản cũ hơn còn nằm trong **SSTable khác có phạm vi dữ liệu chồng lấp**.
3. Compaction strategy và các SSTable được chọn quyết định lúc nào việc đối chiếu và dọn thực sự diễn ra.
4. Replica phân tán và lịch repair cần được vận hành tương thích với quy tắc thu gom.

```text
SSTable 1              SSTable 2                 SSTable 3
old-value @100         tombstone @200             dữ liệu khác
     |                       |
     +----------+------------+
                |
       Compaction đủ điều kiện
                |
     Đối chiếu old-value với tombstone
                |
     Nếu an toàn mới bỏ cả dữ liệu bị che
     và marker không còn cần thiết.
```

Nếu chỉ xem SSTable 2 mà dọn tombstone, bản `old-value@100` ở SSTable 1 có thể bị lộ ra. Đó là lý do compaction phải xét sự chồng lấp và cơ chế an toàn, không chỉ kiểm tra tuổi tombstone bằng phép so sánh đơn giản.

### Các thuật ngữ liên quan

- **Memtable:** dữ liệu đang ở bộ nhớ trước khi flush.
- **SSTable:** tập tin dữ liệu trên đĩa, không chỉnh sửa tại chỗ.
- **Compaction:** hợp nhất SSTable và lọc các phiên bản/tombstone có thể dọn an toàn.
- **Repair:** trao đổi/đối chiếu dữ liệu giữa replica để phát hiện và sửa bất đồng.
- **Garbage collection của tombstone:** loại bỏ thông tin xóa không còn cần thiết; khác với việc Java GC giải phóng heap.

`nodetool compact` (khi được hỗ trợ ở phiên bản đang chạy) có thể yêu cầu công việc compaction, nhưng **không bảo đảm mọi expired cell sẽ biến mất**. Không ép compaction trên production như một cách kiểm thử vô hại: nó gây I/O đáng kể và có thể ảnh hưởng cách các SSTable được tổ chức cho những lần compaction sau.

## 11. Compaction strategy cho workload có nhiều TTL

Một bảng ghi nhiều TTL có thể tạo đáng kể tombstone/expired cells. Chọn **compaction strategy** phù hợp có thể giúp các SSTable đồng thời hết hạn được dọn hiệu quả hơn.

| Chiến lược / kiểu workload | Điểm cần hiểu |
|---|---|
| **SizeTieredCompactionStrategy (STCS)** | Hợp nhất theo nhóm kích thước; phù hợp một số workload ghi, nhưng expired cells có thể nằm trong các SSTable chồng lấp lâu |
| **LeveledCompactionStrategy (LCS)** | Kiểm soát sự chồng lấp theo level; thường phù hợp nhiều mẫu truy vấn đọc, nhưng có chi phí ghi/compaction |
| **TimeWindowCompactionStrategy (TWCS)** | Thường hữu ích cho **time-series/append-only** với TTL tương đối đồng nhất, hạn chế dữ liệu khác thời kỳ trộn vào cùng SSTable |

Ví dụ schema hướng tới dữ liệu cảm biến theo thiết bị và ngày:

```sql
CREATE TABLE IF NOT EXISTS sensor_events_by_device_day (
    device_id text,
    event_day date,
    event_time timeuuid,
    reading double,
    PRIMARY KEY ((device_id, event_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC)
  AND default_time_to_live = 604800
  AND compaction = {
      'class': 'TimeWindowCompactionStrategy',
      'compaction_window_unit': 'DAYS',
      'compaction_window_size': '1'
  };
```

Ở đây TTL mặc định là **604800 giây = 7 ngày**, còn TWCS nhóm theo cửa sổ một ngày trong ví dụ. **Đây không phải một cấu hình phổ quát**; phải cân nhắc độ trễ dữ liệu đến, tần suất update/delete, kích thước SSTable và phân bố TTL.

TWCS hiệu quả nhất khi các ghi mang thời gian tương ứng cửa sổ và dữ liệu chủ yếu **append-only**, có TTL đồng đều. **Backfill rất cũ, out-of-order writes, cập nhật ngẫu nhiên** hoặc các TTL rất khác nhau có thể làm việc dọn expired SSTable kém hiệu quả và giữ tombstone lâu hơn.

**Chọn clustering key theo truy vấn**, ví dụ `event_time`, không theo `writetime(reading)`; mutation timestamp dùng cho LWW, không là cơ chế truy vấn lịch sử sự kiện. Với lượng dữ liệu cao, cần điều chỉnh time bucket để partition không quá lớn.

## 12. Chẩn đoán: khi nào cần nghĩ tới tombstone pressure?

Các triệu chứng thường gặp ở bảng nhiều TTL hoặc DELETE:

- **Đọc chậm** dù số hàng trả về ít: truy vấn phải duyệt nhiều cell đã xóa/hết hạn.
- **Compaction backlog cao**, I/O đĩa và dung lượng SSTable tăng dù TTL ngắn.
- **Truy vấn xuất hiện tombstone warnings** hoặc chạm ngưỡng bảo vệ theo cấu hình Cassandra.
- **Replica repair kéo dài** hay node bị offline khiến độ an toàn của việc dọn tombstone trở thành vấn đề.
- **Dữ liệu biến mất khỏi SELECT nhưng đĩa không giảm** như người vận hành mong đợi.

Hãy thu thập bằng chứng theo bảng, partition và thời điểm thay vì đoán:

| Câu hỏi | Hướng kiểm tra |
|---|---|
| Cell còn sống không? | `SELECT value, ttl(value), writetime(value) ... WHERE partition_key = ...` |
| TTL có thực sự được đặt không? | `USING TTL` trong CQL, `default_time_to_live` của bảng |
| Có DELETE/overwrites liên tục không? | Log ứng dụng, tombstone/độ trễ truy vấn và lịch sử mutation |
| Tombstone đang được giữ bao lâu? | `gc_grace_seconds`, schema, replica downtime, lịch repair |
| Compaction có bị nghẽn không? | Metrics và `nodetool compactionstats` theo phiên bản |
| Tỷ lệ tombstone/đọc thế nào? | Thống kê bảng, metrics truy vấn, cảnh báo tombstone |
| Có SSTable chồng lấp làm chậm purge không? | Compaction strategy và công cụ quan sát SSTable phù hợp |
| Có snapshot/backup giữ dung lượng? | Chính sách snapshot/backup và cách đo dung lượng đĩa |

Các lệnh kiểm tra vận hành thường gặp, **không chạy trên production nếu chưa được cấp quyền và nắm tác động**:

```bash
# Chạy ở môi trường quản trị Cassandra phù hợp.
nodetool status
nodetool compactionstats
nodetool tablestats my_keyspace.ttl_gc_lab_by_key
```

Đầu ra, trường metrics và cú pháp tùy phiên bản Cassandra. `nodetool tablestats` hữu ích để nắm thống kê bảng, nhưng không tự đưa ra lịch “đến ngày nào mọi tombstone sẽ được dọn”. Với điều tra sâu, có thể cần công cụ đọc metadata/SSTable ngoại tuyến của đúng phiên bản hoặc tracing có kiểm soát.

## 13. Java Driver: phân biệt không có dữ liệu sống với không có byte trên đĩa

Ứng dụng Java sử dụng **Apache/DataStax Cassandra Java Driver 4.x** có thể đọc TTL và write timestamp. Ví dụ repository dưới đây chỉ thực hiện truy vấn theo partition key, không quét bảng:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class TtlGcReader {
    private final CqlSession session;
    private final PreparedStatement putTemporary;
    private final PreparedStatement get;

    public TtlGcReader(CqlSession session) {
        this.session = session;
        this.putTemporary = session.prepare(
            "UPDATE ttl_gc_lab_by_key USING TTL ? " +
            "SET payload = ? WHERE cache_key = ?"
        );
        this.get = session.prepare(
            "SELECT payload, ttl(payload) AS ttl_s, " +
            "writetime(payload) AS write_us, retained_note " +
            "FROM ttl_gc_lab_by_key WHERE cache_key = ?"
        );
    }

    public void write(String key, String value, int ttlSeconds) {
        if (ttlSeconds <= 0) {
            throw new IllegalArgumentException("TTL must be positive");
        }
        session.execute(putTemporary.bind(ttlSeconds, value, key));
    }

    public void inspect(String key) {
        Row row = session.execute(get.bind(key)).one();
        if (row == null) {
            System.out.println("No live row visible");
            return;
        }

        String payload = row.getString("payload");
        Integer remaining = row.isNull("ttl_s")
            ? null : row.getInt("ttl_s");
        Long writeTimestampMicros = row.isNull("write_us")
            ? null : row.getLong("write_us");
        String note = row.getString("retained_note");

        System.out.printf(
            "payload=%s, ttlSeconds=%s, writeMicros=%s, note=%s%n",
            payload, remaining, writeTimestampMicros, note
        );
    }
}
```

**Diễn giải chính xác:**

- `row == null` nghĩa là truy vấn không trả row sống phù hợp tại thời điểm/mức nhất quán đó. Không thể từ đây kết luận SSTable không còn byte.
- `payload == null` với `note != null` có thể do payload chưa từng được ghi, hết TTL hoặc bị xóa. `ttl(payload)` và `writetime(payload)` không hiển thị thông tin tombstone.
- `ttl_s` là **số giây còn lại**, không phải epoch timestamp; `write_us` là **epoch microseconds**, không phải thời điểm xóa vật lý.
- Nếu nhiều replica khác nhau tạm giữ phiên bản khác nhau, consistency level và reconciliation có thể ảnh hưởng lần đọc. Không dùng `ONE` và `ALL` như công cụ thay quy tắc LWW.

Nếu nghiệp vụ phải thực thi hạn chót thật chính xác (token, chứng từ hoặc quyền truy cập), lưu thêm **`expires_at` theo UTC** và kiểm tra trong ứng dụng. TTL giúp Cassandra dọn dữ liệu tự động, **không thay thế logic hết hạn và bảo mật** ở tầng nghiệp vụ.

## 14. Vận hành an toàn: repair trước, đừng giảm grace để “giải phóng đĩa”

Một quy trình vận hành nên giải quyết theo đúng bản chất vấn đề:

1. **Xác nhận dữ liệu đã hết hạn logic.** Đọc đúng partition key và cột, so `ttl()` trước/sau, lưu ý cột chưa có TTL hoặc bị ghi lại.
2. **Xác nhận bảng và chiến lược compaction.** Kiểm tra `default_time_to_live`, `gc_grace_seconds`, compaction strategy, tỷ lệ ghi đè/xóa và kích thước partition.
3. **Đối chiếu tình trạng replica.** Xem node down, dữ liệu replica chưa đồng bộ, lịch repair, backup và sự kiện thay đổi topology.
4. **Xác định lý do byte còn trên đĩa.** Có thể do SSTable chưa compact, tombstone chưa đủ tuổi, SSTable chồng lấp hoặc snapshot/backup vẫn giữ file.
5. **Ước lượng tác động trước thay đổi.** Chuyển compaction strategy, thay grace period hay ép compaction cần đánh giá I/O, write amplification và an toàn dữ liệu.
6. **Giám sát sau xử lý.** Theo dõi tombstone warning, độ trễ đọc, compaction pending, dung lượng đĩa và repair.

### Vì sao không nên dùng `gc_grace_seconds = 0` tùy tiện?

Giảm thời gian grace không làm cell hết TTL “nhanh hơn”: cell đã hết hạn theo TTL từ trước. Nó chỉ **rút ngắn khoảng bảo vệ** trước khi tombstone có thể được dọn. Trong môi trường nhiều replica, node mất kết nối lâu hoặc repair không bảo đảm, đó là một đánh đổi nghiêm trọng với rủi ro dữ liệu cũ quay lại.

Một số kiến trúc hoặc điều kiện vận hành đặc biệt có thể cho phép cấu hình grace thấp hơn, nhưng chỉ sau khi kiểm tra đầy đủ semantics của workload, khả năng mất node, chính sách repair và quy trình khôi phục. Không sao chép một “công thức tăng tốc dọn tombstone” cho mọi cluster.

### Vì sao ép compaction cũng không bảo đảm reclaim ngay?

Ngay cả khi tombstone đủ tuổi, Cassandra còn cần đảm bảo không có phiên bản cũ ở SSTable chồng lấp có thể bị lộ; compaction có thể tốn I/O và không chọn tất cả SSTable cùng lúc. Ngoài ra snapshot, backup hoặc các phiên bản dữ liệu khác có thể giữ dung lượng đĩa. Cần đo đúng phần dung lượng muốn thu hồi, không đồng nhất dung lượng thư mục với số row sống.

## 15. Thiết kế bảng giảm chi phí TTL ngay từ đầu

Trong Cassandra, **thiết kế bảng theo truy vấn** là yếu tố then chốt. Nếu mô hình buộc Cassandra quét nhiều dữ liệu đã hết hạn để trả rất ít dữ liệu sống, ngay cả TTL đúng cũng có thể làm hệ thống chậm.

Một số hướng thiết kế:

| Mẫu workload | Hướng cân nhắc | Điều cần tránh |
|---|---|---|
| Dữ liệu thời gian có cùng retention | Time bucket + TTL tương đối đồng nhất + TWCS khi phù hợp | Backfill ngẫu nhiên làm trộn cửa sổ compaction |
| Trạng thái hiện tại cập nhật nhiều lần | Bảng latest-state riêng, kiểm soát TTL/retry | Ghi đè cùng cell liên tục với TTL rất ngắn nếu không cần |
| Lịch sử sự kiện chỉ append | Mỗi event một row, clustering key theo thời gian | Một list/map vô hạn trong một partition |
| Dữ liệu “tồn tại tới hạn chót” | `expires_at` trong logic nghiệp vụ, TTL để hỗ trợ lưu trữ | Tin rằng TTL quyết định chính xác giờ xóa vật lý |
| Cần tra cứu khóa cụ thể | Query có partition key rõ ràng | `ALLOW FILTERING`/full scan để tìm hàng hết TTL |

**TTL tạo ra công việc compaction trong tương lai**. Khi ấn định retention 1 giờ cho hàng triệu cell mỗi phút, phải tính dung lượng cho cả dữ liệu sống, dữ liệu hết hạn chưa dọn, overhead tombstone, compaction tạm và các bản sao/snapshot. Không thể lấy đơn giản “tốc độ ghi × TTL” làm giới hạn tuyệt đối của dung lượng đĩa.

## 16. Các hiểu lầm cần loại bỏ

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| “TTL hết là dữ liệu biến mất khỏi ổ đĩa.” | TTL hết làm cell **không còn sống logic**; byte có thể tồn tại tới compaction an toàn |
| “TTL 60, grace 10 ngày nghĩa là đọc được 10 ngày + 60 giây.” | Grace phục vụ an toàn **tombstone**, không kéo dài thời gian dữ liệu sống |
| “Sau `gc_grace_seconds` sẽ dọn đúng giờ.” | Tombstone chỉ có thể **đủ tuổi**; cần compaction và điều kiện an toàn |
| “Cứ chạy compaction là mọi tombstone hết ngay.” | Overlap SSTable, tuổi tombstone, strategy và an toàn dữ liệu đều ảnh hưởng |
| “TTL không cần tombstone vì mỗi replica tự hết hạn.” | Replica có expiration tự hết hạn; bản cũ ở replica khác vẫn có thể cần được che |
| “`writetime()` cho biết lúc tombstone bị xóa.” | Nó là write timestamp của **cell sống** quan sát được |
| “Repair tự sửa chính sách TTL sai.” | Repair giúp replica hội tụ, không thay định nghĩa TTL/ngữ nghĩa nghiệp vụ |
| “Hạ grace xuống 0 chắc chắn an toàn.” | Có thể tăng nguy cơ **zombie data** nếu replica chưa hội tụ |
| “Không có row trong SELECT nghĩa là không còn dữ liệu trong backup.” | Truy vấn live data không đại diện cho SSTable, snapshot và backup |

## 17. Bài tập tình huống và đáp án

**Câu 1.** Ghi một cell bằng `USING TTL 60`. Sau 65 giây, `SELECT` không còn thấy giá trị, nhưng dung lượng đĩa không đổi. Đây có phải lỗi TTL không?

**Đáp án:** Không nhất thiết. Cell đã **hết hạn logic**; byte/tombstone có thể còn trong SSTable chờ compaction và điều kiện thu hồi an toàn.

**Câu 2.** Bảng có `gc_grace_seconds = 864000`. Một cell TTL 30 giây sẽ còn đọc được thêm 10 ngày không?

**Đáp án:** Không. Cell hết hạn logic sau khoảng 30 giây; grace không cộng vào thời gian sống của người dùng.

**Câu 3.** Sau khi đã quá `gc_grace_seconds`, có chắc dữ liệu hết hạn được xóa vật lý ngay không?

**Đáp án:** Không. Còn phụ thuộc compaction, SSTable chồng lấp, replica/repair và các tệp snapshot/backup ngoài tập dữ liệu sống.

**Câu 4.** Một replica không nhận phiên bản mới `VALUE@200 TTL 60` và vẫn giữ `OLD@100` không TTL. Vì sao expiration/tombstone của bản `@200` quan trọng?

**Đáp án:** Nó giúp ngăn `OLD@100` trở lại khi replica được hòa giải. Nếu marker bị dọn thiếu an toàn trước khi sửa khác biệt, có thể xuất hiện **zombie data**.

**Câu 5.** `writetime(payload) = null` sau khi payload hết TTL. Có thể kết luận tombstone đã bị purge không?

**Đáp án:** Không. `writetime()` không hiển thị tombstone; `null` chỉ cho biết không có write timestamp của cell sống trong kết quả đó.

**Câu 6.** Vì sao giảm `gc_grace_seconds` không làm dữ liệu hết hạn được ẩn khỏi `SELECT` nhanh hơn?

**Đáp án:** Quy tắc **TTL/expiration** đã làm dữ liệu không còn sống đúng hạn. Grace chỉ liên quan khoảng bảo vệ trước khi tombstone được thu gom.

**Câu 7.** Workload append-only theo ngày với retention 7 ngày, có nên cân nhắc TWCS không?

**Đáp án:** Có thể, nếu mẫu ghi và TTL phù hợp, dữ liệu chủ yếu theo dòng thời gian và ít out-of-order/backfill. Phải kiểm tra kích thước partition, tần suất update và chiến lược vận hành thực tế.

**Câu 8.** Hàng có `retained_note` không TTL và `payload` TTL 10 giây. Sau 10 giây, có nhất thiết cả hàng biến mất không?

**Đáp án:** Không. `payload` không còn sống nhưng `retained_note` có thể giữ row xuất hiện trong kết quả.

**Câu 9.** Một ứng dụng cần chắc chắn token không được dùng sau `12:05:00`. Có nên chỉ dựa vào TTL của Cassandra?

**Đáp án:** Không. Nên kiểm tra **`expires_at`/hạn chót nghiệp vụ** khi xác thực, đồng thời dùng TTL cho việc hết hiệu lực và quản lý lưu trữ.

---

**Ghi nhớ:** Trong Cassandra, **hết hạn logic → tombstone/expiration bảo vệ tính đúng đắn → compaction đủ điều kiện mới thu hồi vật lý** là ba bước khác nhau. `gc_grace_seconds` không kéo dài thời gian dữ liệu sống và không đặt lịch xóa byte cố định; nó giúp bảo vệ việc hòa giải replica trước nguy cơ zombie data. Thiết kế bảng theo truy vấn, chọn TTL/compaction phù hợp, vận hành repair và quan sát metrics là các điều kiện để dữ liệu hết hạn được dọn **đúng và an toàn**.
