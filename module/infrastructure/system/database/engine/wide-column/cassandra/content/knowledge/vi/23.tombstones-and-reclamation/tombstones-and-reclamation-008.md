# Dữ liệu TTL trộn nhiều thời hạn và các SSTable khó thu hồi

> **Chương:** Tombstone và thu hồi  
> **Phạm vi:** Apache Cassandra — cơ sở dữ liệu phân tán theo mô hình *wide-column* — với trọng tâm là vòng đời TTL, tombstone, SSTable và compaction. Ví dụ sử dụng CQL, công cụ quản trị node và Java Driver 4.x.

## 1. Tình huống: dữ liệu hết TTL nhưng dung lượng đĩa vẫn không giảm

Một hệ thống thu thập sự kiện thiết bị lưu hai loại bản ghi:

- Sự kiện chi tiết: chỉ cần **1 ngày** để hiển thị nhanh và điều tra tức thời.
- Sự kiện quan trọng: cần **30 ngày** để phục vụ hỗ trợ khách hàng.

Hai loại được ghi vào **cùng một bảng Cassandra**, cùng partition key theo thiết bị và ngày. Hệ thống đặt `USING TTL 86400` cho bản ghi ngắn hạn, `USING TTL 2592000` cho bản ghi dài hạn.

Sau hai ngày, truy vấn không còn trả về các sự kiện có TTL một ngày. Tuy nhiên, số SSTable và dung lượng đĩa vẫn cao. Việc “đã hết hạn” và “đã được xóa khỏi tệp SSTable” là **hai sự kiện khác nhau**.

Giả sử hai mutation đã được flush vào cùng một SSTable:

```text
SSTable S1 (ví dụ minh họa)
┌─────────────────────────────────────────────────────────┐
│ event A  | TTL 1 ngày  | hết hạn ngày D+1  | đã expired │
│ event B  | TTL 30 ngày | hết hạn ngày D+30 | còn sống   │
│ event C  | TTL 1 ngày  | hết hạn ngày D+1  | đã expired │
└─────────────────────────────────────────────────────────┘

Ngày D+2:
- SELECT không còn trả A, C theo điều kiện TTL.
- B vẫn còn sống -> S1 không thể bị bỏ toàn bộ chỉ vì A, C hết hạn.
- Muốn thu hồi phần A, C cần compaction đủ điều kiện để tạo lại SSTable
  chỉ với dữ liệu cần giữ; còn phải xét grace và an toàn tombstone.
```

Đây là điểm cốt lõi của bài:

> **Một SSTable chứa dữ liệu có thời hạn sống khác nhau có thể không đạt điều kiện “toàn bộ đã hết hạn” trong thời gian rất dài.** Ngay cả khi phần lớn byte trong tệp đã hết TTL, Cassandra không thể xóa cả tệp khi vẫn còn dữ liệu sống bên trong.

Không nên kết luận “TTL không hoạt động” chỉ dựa vào dung lượng thư mục data không giảm.

## 2. TTL trong Cassandra hoạt động ở mức nào?

Cassandra dùng TTL (*time to live*) để giới hạn thời gian sống của dữ liệu. TTL của một mutation được tính bằng **giây** và áp dụng cho các cell có giá trị được ghi bằng mutation đó, theo cấu trúc/kiểu dữ liệu được hỗ trợ. Primary key xác định danh tính hàng; không được hiểu rằng mỗi thành phần khóa chính cũng là một cell sẽ hết hạn độc lập giống cột dữ liệu.

Ví dụ:

```cql
INSERT INTO lab.telemetry_mixed_ttl
  (device_id, event_day, event_time, event_id, payload)
VALUES
  ('device-01', '2026-11-21', '2026-11-21T03:00:00Z',
   11111111-1111-4111-8111-111111111111, 'detail')
USING TTL 86400;
```

Với `payload` được ghi kèm TTL một ngày, sau khi hết hạn, giá trị không còn được coi là dữ liệu sống trong kết quả đọc. Việc hết hạn tạo ngữ nghĩa **xóa logic**; metadata TTL/expiration cần tiếp tục được xử lý như dữ liệu đã bị xóa cho đến khi đủ điều kiện thu hồi vật lý.

Một mutation không phải lúc nào cũng làm hết hạn mọi cột của hàng. Ví dụ nếu chỉ cập nhật `payload` với TTL, những cột không được ghi lại trong mutation đó có thể giữ TTL khác hoặc không có TTL.

### Ba mốc thời gian phải phân biệt

| Mốc | Ý nghĩa | Có nghĩa dung lượng đĩa giảm ngay? |
| --- | --- | --- |
| **Thời điểm ghi** | Cassandra nhận mutation, gắn TTL/metadata hết hạn phù hợp | Không |
| **Thời điểm TTL hết hạn** | Cell không còn sống về mặt logic; đọc thông thường không trả lại giá trị đó | **Không** |
| **Thời điểm được GC/compaction thu hồi** | SSTable được ghi lại hoặc tệp hoàn toàn hết hiệu lực được loại bỏ khi điều kiện an toàn thỏa | **Có thể** giảm dung lượng, tùy snapshot/backup, compaction và hệ thống tệp |

Ví dụ sự kiện A ghi lúc 10:00 ngày D với TTL một ngày. A hết hạn logic khoảng 10:00 ngày D+1; nó không nhất thiết biến mất khỏi SSTable lúc đó. Ngưỡng `gc_grace_seconds`, những phiên bản ghi khác, tập SSTable chồng lấp và quá trình compaction tiếp tục ảnh hưởng thời điểm thu hồi.

### `TTL(column)` và `WRITETIME(column)` kiểm tra điều gì?

Trong CQL, bạn có thể xem số giây TTL còn lại và timestamp ghi của một cột:

```cql
SELECT payload, TTL(payload), WRITETIME(payload)
FROM lab.telemetry_mixed_ttl
WHERE device_id = 'device-01'
  AND event_day = '2026-11-21';
```

Khi cell còn sống, `TTL(payload)` thể hiện số giây còn lại (xấp xỉ theo thời điểm đọc); với cell không có TTL, kết quả TTL thường là `null`. Khi cell đã hết hạn, nó không được trả như một giá trị sống, vì vậy **không thể dùng `TTL(column)` sau khi hết hạn để kiểm kê toàn bộ tombstone vật lý**.

`WRITETIME` là timestamp của giá trị cell được đọc, không cho biết cell nằm trong SSTable nào hay lần compaction nào sẽ dọn nó.

## 3. Vì sao trộn TTL làm SSTable khó thu hồi?

### 3.1. SSTable là tệp bất biến

Dữ liệu trong memtable được flush thành SSTable bất biến. Một SSTable có thể chứa hàng triệu cell từ nhiều partition, các cell có TTL khác nhau và cả dữ liệu không TTL. Cassandra **không xóa từng byte bên trong SSTable ngay khi một cell hết hạn**.

Nếu có cell sống và cell đã hết hạn trong cùng SSTable, thường có hai hướng:

1. **Giữ lại SSTable** chờ compaction, bởi nó vẫn chứa dữ liệu sống.
2. **Compaction SSTable** với các tệp liên quan, bỏ dữ liệu đã đủ điều kiện GC rồi ghi SSTable mới; tệp cũ chỉ bị giải phóng sau khi tệp mới được thay thế an toàn.

Hướng thứ hai tốn I/O đọc và ghi, CPU, dung lượng đĩa tạm thời và có thể gây áp lực lên hiệu năng truy vấn trong lúc compaction.

### 3.2. Điều kiện xóa nguyên SSTable (*whole-SSTable expiration*)

Với workload TTL đều và thích hợp, nhất là dùng **TimeWindowCompactionStrategy (TWCS)**, Cassandra có thể nhận biết một SSTable đã hết hiệu lực toàn bộ, từ đó bỏ tệp mà không cần ghi lại từng hàng.

Nhưng “toàn bộ hết hạn” là điều kiện mạnh hơn “đa số hàng hết hạn”:

- **Không còn dữ liệu sống cần giữ** trong SSTable.
- Các dấu xóa/TTL cần thiết đã đủ điều kiện thu hồi theo quy tắc GC của phiên bản và cấu hình.
- Việc bỏ tệp an toàn đối với dữ liệu/phiên bản có thể còn ở SSTable khác, cùng những điều kiện liên quan đến repair/replica.
- Tệp không bị giữ bởi một cơ chế khác như snapshot/hard link ở mức lưu trữ.

Vì vậy, chỉ một cell có TTL 30 ngày xen vào SSTable chủ yếu có TTL 1 ngày cũng có thể đẩy thời điểm SSTable đủ điều kiện bỏ nguyên tệp tới rất xa.

**Không nhầm “đã đủ điều kiện loại bỏ tệp” với “tệp chắc chắn được xóa ngay”.** Thời điểm dọn thực tế còn tùy compaction strategy, lịch kiểm tra, trạng thái node và cơ chế quản lý SSTable.

### 3.3. Ví dụ định lượng

Giả sử SSTable S1 được tạo ngày D với dữ liệu:

| Thành phần trong S1 | Kích thước minh họa | TTL | Hết hạn logic |
| --- | ---: | ---: | --- |
| Sự kiện chi tiết | 900 MiB | 1 ngày | D+1 |
| Sự kiện quan trọng | 100 MiB | 30 ngày | D+30 |
| **Tổng** | **1.000 MiB** | **TTL hỗn hợp** | **Không có một ngày hết hạn chung** |

Vào D+2, **90% dữ liệu trong ví dụ đã hết hạn**, nhưng 100 MiB còn sống có thể khiến cả tệp 1.000 MiB chưa thể bị xóa nguyên tệp. Phần 900 MiB chỉ có thể thu hồi khi có compaction phù hợp, đủ điều kiện xóa và hoàn tất an toàn.

Con số này là minh họa, không phải tỷ lệ tối ưu hay dự báo hiệu năng thực. Nếu compaction không được chọn sớm, mức lưu trữ vật lý có thể tiến gần tới vòng đời của dữ liệu lâu nhất, cộng thời gian grace/hoạt động vận hành.

## 4. Một SSTable hỗn hợp có thể đến từ những cách ghi nào?

TTL trộn không nhất thiết do hai bảng khác nhau. Những nguyên nhân thường gặp:

| Cách phát sinh | Ví dụ | Hậu quả |
| --- | --- | --- |
| Hai nhóm bản ghi trong cùng bảng | Sự kiện thường `TTL 1 ngày`, sự kiện quan trọng `TTL 30 ngày` | SSTable nhận các mutation với thời điểm hết hạn rất khác |
| Cùng hàng, các cột có TTL khác nhau | `summary` có TTL ngắn, `audit_ref` tồn tại lâu | Một hàng có cell sống xen cell hết hạn |
| TTL mặc định và TTL chỉ định khác nhau | Bảng `default_time_to_live=86400`, một số mutation được ghi với TTL khác theo phiên bản/cú pháp | Dữ liệu bị phân tán theo nhiều thời hạn |
| Có dữ liệu **không TTL** | Phần lớn sự kiện có TTL, một ít bản ghi không hết hạn | SSTable chứa dữ liệu sống rất lâu, không đạt điều kiện hết hạn toàn bộ |
| Ghi cập nhật, ghi trễ hoặc backfill | Ghi dữ liệu mới vào partition cũ, timestamp đến trễ | Các thế hệ dữ liệu có thể nằm trong tệp/nhóm compaction không còn đồng nhất |
| Repair/streaming | Dữ liệu hoặc SSTable được truyền giữa replica | Cần xét lại phân phối SSTable và khả năng chồng lấp, không suy ra tệp luôn thuần một khoảng TTL |

Đặc biệt, một bảng có `default_time_to_live` không bảo đảm mọi cell thực tế đều hết hạn vào cùng lúc. Thời điểm ghi khác nhau tạo thời điểm hết hạn khác nhau; thêm TTL chỉ định khác giá trị mặc định càng làm phân phối kéo dài.

## 5. Tombstone, `gc_grace_seconds` và phiên bản cũ

Khi TTL hết hạn, cell không còn sống logic. Nhưng trong hệ Cassandra phân tán có **nhiều replica** và SSTable bất biến, metadata xóa vẫn có vai trò ngăn các giá trị cũ bị nhìn nhận là dữ liệu còn sống.

### `gc_grace_seconds` không phải thời điểm xóa file

`gc_grace_seconds` là cấu hình cấp bảng tạo **khoảng bảo vệ** đối với việc thu hồi tombstone. Ví dụ:

```cql
CREATE TABLE lab.telemetry_mixed_ttl (
    device_id text,
    event_day date,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)
  AND gc_grace_seconds = 864000;
```

Giá trị 864000 giây là **10 ngày minh họa**, không phải chỉ định mặc định áp dụng cho mọi cluster. Bản ghi TTL một ngày có thể hết hạn logic từ ngày D+1 nhưng metadata xóa/expiration vẫn cần được lưu giữ theo chính sách GC.

Tuy nhiên, tombstone vượt ngưỡng grace **chỉ trở thành ứng viên thu hồi**: còn phải có compaction hoặc cơ chế drop SSTable thích hợp, đồng thời không để dữ liệu cũ trong SSTable/replica khác tái xuất hiện.

### Vì sao cần giữ dấu xóa?

Giả sử RF=3 và replica C offline khi một row bị xóa trên A, B:

```text
T0  A,B,C đều giữ row v1
T1  C offline; DELETE được A,B nhận -> tombstone
T2  A,B purge dấu xóa trước khi C được đồng bộ
T3  C trở lại, vẫn giữ row v1
T4  Đọc/repair có thể đưa row v1 trở lại -> zombie data
```

Đây là rủi ro điển hình của việc purge tombstone trước khi mọi replica cần thiết đã được hòa giải. Hinted handoff có phạm vi thời gian và không thay thế repair; CL của một lệnh cũng không tự chứng minh mọi replica đã nhận dấu xóa.

Với **TTL thuần túy**, mọi replica từng nhận cùng cell có TTL đúng có thể tự xác định thời điểm hết hạn; vì thế các kiểu workload chỉ ghi bất biến với TTL đồng nhất có cơ hội tối ưu thu hồi hơn so với xóa/cập nhật tùy ý. Nhưng nếu replica bỏ lỡ mutation, có các phiên bản ghi đè, timestamp lệch hoặc xóa thủ công, vẫn phải giữ mô hình an toàn dựa trên grace, SSTable overlap và repair. Không đặt `gc_grace_seconds=0` như quy tắc chung chỉ vì bảng dùng TTL.

### Tại sao SSTable chồng lấp vẫn quan trọng?

Giả sử có:

```text
SSTable S_old: payload='v1' @timestamp 100
SSTable S_new: DELETE payload @timestamp 200 (đã quá gc_grace)
```

Nếu compaction chỉ xử lý `S_new` và bỏ tombstone mà `S_old` còn giá trị v1, v1 có thể lộ ra lại. Cassandra cần xem xét thông tin liên quan về **những SSTable khác có thể chứa giá trị bị che khuất** trước khi quyết định purge.

Trường hợp hỗn hợp TTL làm việc này khó hơn ở hai hướng: có cell còn sống ngăn drop whole-SSTable; có dữ liệu hết hạn/dấu xóa phải chờ compaction đủ điều kiện mới được dọn ở mức cell.

## 6. Vai trò của compaction strategy

### STCS — SizeTieredCompactionStrategy

STCS thường gom những SSTable có kích thước tương tự. SSTable hỗn hợp TTL sẽ được giữ tới khi nó tham gia lần compaction thích hợp hoặc hết hạn toàn bộ theo điều kiện an toàn.

**Điểm đáng chú ý:** thời điểm một tệp được chọn compact chủ yếu dựa trên chính sách kích thước và số lượng tệp, không phải mong muốn “vừa hết TTL thì dọn ngay”. Một SSTable đã có nhiều cell chết có thể chưa được chọn, khiến dung lượng không giảm như dự kiến.

### LCS — LeveledCompactionStrategy

LCS quản lý SSTable theo level, giảm chồng lấp trong từng level nhất định và có thể cải thiện số tệp cần đọc. Nhưng LCS vẫn phải ghi lại SSTable khi compaction và tôn trọng quy tắc xóa an toàn. Nó **không** tạo bảo đảm dữ liệu TTL khác nhau được dọn đúng ngày hết hạn.

### TWCS — TimeWindowCompactionStrategy

TWCS tổ chức compaction theo cửa sổ thời gian, phù hợp với luồng **time-series ghi theo thời gian, chủ yếu append-only, TTL tương đối đồng nhất**.

Khi dữ liệu trong cùng cửa sổ có thời gian sống gần nhau, toàn bộ SSTable của cửa sổ có thể hết hạn gần cùng thời điểm. Điều này tăng khả năng dọn **nguyên tệp** với chi phí thấp.

Ngược lại:

```text
Window W1: dữ liệu ghi cùng ngày
  95% TTL 1 ngày
   5% TTL 30 ngày

Toàn bộ window W1 vẫn có dữ liệu sống tới khoảng D+30.
TWCS không thể bỏ SSTable chỉ vì 95% hàng đã hết hạn.
```

Cửa sổ compaction theo thời gian **không tự chia dữ liệu theo chính sách retention**. Nếu business logic trộn TTL ngắn và dài trong các mutation thuộc cùng cửa sổ, TWCS vẫn nhận các SSTable hỗn hợp.

### Vấn đề dữ liệu đến muộn

TWCS có giả định quan trọng về thời gian ghi/timestamp. Dữ liệu đến muộn, cập nhật hàng cũ, backfill hay mutation với timestamp khác biệt lớn có thể dẫn tới SSTable chứa dữ liệu của các cửa sổ/tuổi khác nhau. Do đó:

- Không đánh giá TWCS chỉ theo việc có cột `event_time`.
- Xác nhận workload chủ yếu append-only, tỷ lệ update/delete thấp, TTL tương đối đồng nhất.
- Có chiến lược riêng cho backfill và late-arriving events.
- Đo SSTable expiration, compacted bytes và tombstone read thực tế.

### Tóm tắt so sánh

| Chiến lược | Khi TTL hỗn hợp | Ý nghĩa vận hành |
| --- | --- | --- |
| STCS | SSTable có thể giữ bản ghi hết TTL tới khi tham gia compaction phù hợp | Theo dõi tombstone và dung lượng chưa thu hồi |
| LCS | Có thể hòa giải nhiều bản dữ liệu qua các level; vẫn phải xử lý cell còn sống | Đánh đổi đọc/ghi/space amplification |
| TWCS | Tốt khi cùng cửa sổ có tuổi dữ liệu/TTL đồng nhất; kém hiệu quả nếu trộn TTL dài ngắn | Ưu tiên tách retention và tránh ghi trễ sai giả định |

Không có compaction strategy nào biến một SSTable còn dữ liệu sống thành tệp có thể xóa an toàn chỉ vì đa số cell đã expired.

## 7. Thực hành CQL: tạo dữ liệu TTL hỗn hợp

Các lệnh dưới đây dùng **keyspace `lab` đã tồn tại** trên cluster thử nghiệm; dữ liệu, timestamp và UUID chỉ để minh họa. Không chạy thay đổi TTL/compaction trên production khi chưa đánh giá dung lượng, repair và SLO.

### Bước A — Tạo bảng

```cql
CREATE TABLE IF NOT EXISTS lab.telemetry_mixed_ttl (
    device_id text,
    event_day date,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)
  AND gc_grace_seconds = 864000;
```

Partition key `(device_id, event_day)` giúp truy vấn sự kiện theo thiết bị/ngày. Nó **không** bảo đảm dữ liệu có cùng TTL trong một partition.

### Bước B — Ghi hai thời hạn khác nhau

```cql
INSERT INTO lab.telemetry_mixed_ttl
  (device_id, event_day, event_time, event_id, payload)
VALUES
  ('device-01', '2026-11-21', '2026-11-21T03:00:00Z',
   11111111-1111-4111-8111-111111111111, 'short-lived')
USING TTL 86400;

INSERT INTO lab.telemetry_mixed_ttl
  (device_id, event_day, event_time, event_id, payload)
VALUES
  ('device-01', '2026-11-21', '2026-11-21T03:01:00Z',
   22222222-2222-4222-8222-222222222222, 'long-lived')
USING TTL 2592000;
```

Lưu ý timestamp của `event_time` là dữ liệu nghiệp vụ; **TTL được tính theo thời điểm ghi mutation/cơ chế TTL**, không lấy trực tiếp từ cột `event_time` để làm mốc. Nếu bạn chạy thử nhiều ngày sau ngày trong ví dụ, hai hàng **vẫn có TTL mới tính từ lúc ghi thử**.

### Bước C — Quan sát TTL còn lại

```cql
SELECT event_time, event_id, payload, TTL(payload)
FROM lab.telemetry_mixed_ttl
WHERE device_id = 'device-01'
  AND event_day = '2026-11-21';
```

Kết quả ban đầu dự kiến có hai hàng với TTL khác nhau. Sau hơn một ngày, hàng `short-lived` không còn được xem là sống và thường không xuất hiện trong kết quả; hàng `long-lived` còn tới gần 30 ngày sau thời điểm ghi.

**Kết quả đọc không cho biết tệp SSTable nào đã đủ điều kiện drop.** Để kiểm tra cách dữ liệu được flush và phân nhóm, cần dùng metrics/công cụ SSTable trên node thử nghiệm.

### Bước D — Quan sát memtable, SSTable và compaction

Ví dụ các lệnh quan sát trên node lab:

```bash
nodetool tablestats lab.telemetry_mixed_ttl
nodetool compactionstats
```

Các chỉ số có thể khác theo phiên bản, nhưng thường cần xem số SSTable, disk space used, số lần flush, compaction pending/active và tombstone scanned. Có thể đối chiếu metrics/JMX, tracing CQL có kiểm soát và metadata SSTable nếu phiên bản có công cụ phù hợp.

Nếu muốn minh họa dữ liệu được flush:

```bash
nodetool flush lab telemetry_mixed_ttl
```

Không có bảo đảm chỉ hai mutation này chắc chắn nằm trong một tệp riêng: các replica, thời điểm flush, compaction nền và SSTable khác có thể thay đổi bố cục. Giả thuyết “TTL hỗn hợp cùng SSTable” nên được **kiểm chứng bằng metadata/công cụ của node**, không suy ra chỉ từ hai lệnh `INSERT`.

Đừng chạy `nodetool compact` liên tục để “ép xóa TTL”. Compaction có thể tạo I/O và dung lượng tạm thời lớn, trong khi điều kiện GC hoặc dữ liệu dài hạn vẫn ngăn thu hồi triệt để.

## 8. Thiết kế lại theo chính sách retention

Khi có hai nhóm TTL rất khác nhau, cách tiếp cận hữu ích là **tách nhóm retention thành bảng riêng** hoặc ít nhất tách luồng ghi sao cho mỗi SSTable có vòng đời đồng nhất hơn.

### Phương án A — Hai bảng theo retention

Ví dụ tách dữ liệu chi tiết một ngày và dữ liệu quan trọng 30 ngày:

```cql
CREATE TABLE lab.telemetry_recent (
    device_id text,
    event_day date,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)
  AND default_time_to_live = 86400
  AND compaction = {
      'class': 'TimeWindowCompactionStrategy',
      'compaction_window_unit': 'HOURS',
      'compaction_window_size': '6'
  };

CREATE TABLE lab.telemetry_retained (
    device_id text,
    event_day date,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)
  AND default_time_to_live = 2592000
  AND compaction = {
      'class': 'TimeWindowCompactionStrategy',
      'compaction_window_unit': 'DAYS',
      'compaction_window_size': '1'
  };
```

Cả hai `compaction_window_size` chỉ là **giá trị thử nghiệm minh họa**. Cửa sổ tối ưu phụ thuộc tốc độ ghi, TTL, kích thước SSTable, lưu lượng và dữ liệu đến trễ. Khi có nhiều retention class, bảng riêng giúp thiết kế và vận hành từng lớp theo access pattern.

Với sự kiện quan trọng cũng cần hiện ở màn hình thời gian thực, ứng dụng có thể ghi nó vào **cả hai bảng**, nếu hai đường đọc đòi hỏi điều đó. Khi ghi kép, cần xử lý retry idempotent, lỗi ghi một bảng nhưng bảng kia thành công và cơ chế đối soát. Cassandra không tự đồng bộ các bảng nghiệp vụ độc lập.

### Phương án B — Không nhân bản nếu không cần

Nếu chỉ cần truy vấn sự kiện quan trọng 30 ngày, có thể ghi **chỉ** vào `telemetry_retained` và ứng dụng truy vấn hai bảng tùy màn hình. Không nhất thiết nhân đôi mọi sự kiện.

Phải nêu rõ giao diện đọc: “hiển thị mọi sự kiện trong 24 giờ” có cần hợp nhất hai luồng không? Nếu có, cần cân nhắc việc đọc hai bảng và merge ở application so với ghi thêm một projection.

### Phương án C — Bucket theo thời gian để kiểm soát partition

Partition key `(device_id, event_day)` trong ví dụ giúp giới hạn kích thước partition theo ngày. Tuy nhiên, bucket **không thay thế việc tách retention**: nếu trong mỗi bucket vẫn có cả TTL 1 và 30 ngày, một SSTable chứa dữ liệu của bucket đó vẫn có thể mang TTL hỗn hợp.

Đối với thiết bị phát hàng triệu event/ngày, có thể cần bucket giờ hoặc shard để tránh partition nóng/quá lớn. Quy tắc vẫn là chọn khóa theo **truy vấn và phân phối tải**, không chỉ theo mong muốn GC.

### So sánh quyết định

| Phương án | Ưu điểm | Chi phí/rủi ro |
| --- | --- | --- |
| Một bảng, `USING TTL` khác nhau theo hàng | Triển khai đơn giản, một nguồn đọc | TTL hỗn hợp; compaction phải tái ghi để bỏ cell chết; có thể giữ SSTable lâu |
| Hai bảng theo retention | SSTable dễ đạt vòng đời tương đồng; cấu hình TWCS độc lập | Nhiều bảng và thao tác ghi/đọc; có thể phải đối soát giữa các projection |
| Một bảng với TTL thống nhất và pre-aggregation | Có thể giảm byte và độ phức tạp GC | Mất chi tiết hoặc cần pipeline tổng hợp/kiến trúc dữ liệu khác |
| Phân vùng theo bucket và retention class | Giới hạn partition, dễ hướng query vào đúng phạm vi | Query nhiều bucket/class có thể cần hợp nhất và paging phía ứng dụng |

**Nguyên tắc thực hành:** Khi TTL khác nhau theo **bậc độ lớn** (ví dụ giờ so với tháng), hãy đo chi phí lưu trữ và compaction của phương án một bảng trước khi mặc định chọn thiết kế đó.

## 9. Ví dụ Java Driver 4.x: ghi theo loại retention

Ứng dụng Java có thể quyết định retention theo business event, thay vì cho người gọi tùy ý truyền một TTL không kiểm soát.

Ví dụ với bảng `lab.telemetry_mixed_ttl` khi cần minh họa sự khác biệt:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class TelemetryWriter {
    public enum Retention {
        QUICK(86_400),
        IMPORTANT(2_592_000);

        private final int ttlSeconds;

        Retention(int ttlSeconds) {
            this.ttlSeconds = ttlSeconds;
        }

        public int ttlSeconds() {
            return ttlSeconds;
        }
    }

    private final CqlSession session;
    private final PreparedStatement insert;

    public TelemetryWriter(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO lab.telemetry_mixed_ttl " +
            "(device_id, event_day, event_time, event_id, payload) " +
            "VALUES (?, ?, ?, ?, ?) USING TTL ?"
        );
    }

    public UUID write(
            String deviceId,
            LocalDate eventDay,
            Instant eventTime,
            String payload,
            Retention retention) {

        UUID eventId = UUID.randomUUID();
        BoundStatement statement = insert.bind(
                deviceId,
                eventDay,
                eventTime,
                eventId,
                payload,
                retention.ttlSeconds())
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

        session.execute(statement);
        return eventId;
    }
}
```

Đoạn code giả định `CqlSession` được cấu hình đúng keyspace/cluster và bảng đã tồn tại. `LOCAL_QUORUM` chỉ là ví dụ mức nhất quán; chọn thực tế tùy replication factor và yêu cầu hệ thống.

Nếu nghiệp vụ cần retry sau timeout, tạo `eventId` **trước** khi thực hiện và giữ nguyên ID ở những lần thử lại của **cùng sự kiện**. Việc tạo UUID mới ở mỗi lần thử lại như phương thức ví dụ có thể tạo nhiều hàng logic. Cũng cần lưu ý ghi lại cùng cell với TTL có thể **làm thay đổi thời điểm hết hạn** của cell; idempotency nghiệp vụ không thể suy ra đơn giản từ việc dùng cùng khóa. Với yêu cầu TTL tính từ thời điểm sự kiện ban đầu, cần chính sách rõ ràng cho retry/backfill và timestamp/expiration.

Khi tách thành hai bảng với `default_time_to_live`, Java có thể dùng hai prepared statement có bảng đích cố định, thay vì động hóa tên bảng trong một prepared CQL statement. Cấu trúc này giúp tránh việc người gọi tự chọn TTL ngoài chính sách retention đã thống nhất.

## 10. Đo dung lượng và nguyên nhân không được thu hồi

Để xác định vấn đề thật, nên trả lời các câu hỏi theo thứ tự:

1. **Dữ liệu đã hết hạn logic chưa?** Kiểm tra một số hàng bằng `SELECT`/`TTL` trước khi hết hạn và xác thực chính sách TTL.
2. **SSTable có chứa dữ liệu chưa hết TTL hoặc không TTL không?** Đo phân phối thời hạn ghi và kiểm tra metadata trên môi trường phù hợp.
3. **Đã qua ngưỡng GC và có compaction thích hợp chưa?** Xem `gc_grace_seconds`, compaction strategy, pending compactions và thời điểm tạo SSTable.
4. **Có SSTable khác chứa phiên bản bị tombstone che khuất không?** Đánh giá overlap và workload update/delete.
5. **Có replica vắng mặt/chưa repair không?** Không đổi GC theo giả định mọi replica luôn đồng bộ.
6. **Dung lượng đĩa đang được giữ bởi snapshot/backup không?** Trên hệ thống tệp hỗ trợ hard link, snapshot có thể giữ tệp cũ dù Cassandra đã thay SSTable trong đường dữ liệu hoạt động.

### Chỉ số nên đo

| Tín hiệu | Diễn giải |
| --- | --- |
| `Live disk space used` và `Total disk space used` theo bảng (nếu phiên bản xuất metrics) | Phân biệt dữ liệu hoạt động và phần dung lượng vẫn được lưu giữ |
| Số lượng SSTable, kích thước từng SSTable | Xem có nhiều tệp chưa được compact hoặc tệp rất lớn |
| Tombstones scanned khi đọc | Nhận diện chi phí đọc do dữ liệu chết dù query trả ít hàng |
| Compaction pending/active, bytes compacted, write amplification | Xem cluster có cơ hội và tài nguyên để dọn dữ liệu |
| Tỷ lệ TTL ngắn/dài và số byte ghi/ngày | Ước lượng mức “giữ nhờ” dữ liệu dài hạn |
| Lịch repair, node offline, hints và lỗi I/O | Đảm bảo điều kiện thu hồi trong môi trường phân tán |
| Snapshot/backup retention và disk headroom | Giải thích vì sao OS chưa hoàn trả dung lượng |

Cần quan sát xu hướng nhiều ngày và so sánh với lịch TTL. Ví dụ dữ liệu dài hạn 30 ngày còn sống thì ở ngày thứ ba không thể kỳ vọng toàn bộ SSTable chứa nó được loại bỏ.

### Ước lượng dung lượng theo lớp retention

Giả sử có 100 GiB/ngày ở TTL 1 ngày và 2 GiB/ngày ở TTL 30 ngày:

- Về mặt **dữ liệu còn sống**, gần trạng thái ổn định sẽ có khoảng `100 × 1 + 2 × 30 = 160 GiB` trước khi tính replica, compression, tombstone và hệ số vận hành.
- Nếu hai lớp bị ghi đan xen và nhiều SSTable giữ tới vòng đời TTL dài, dung lượng **vật lý** có thể lớn hơn rất nhiều so với 160 GiB trong giai đoạn chưa có compaction/GC thu hồi phần ngắn hạn.

Đây là mô hình để thấy nguy cơ, **không phải công thức chính xác dự báo dung lượng Cassandra**. Dung lượng thực tế còn phụ thuộc RF, compaction strategy, gc grace, tombstone, nén, snapshot, backup và nhịp ghi. Khi đo cluster, luôn phân biệt byte logic với byte trên mỗi replica và byte OS còn giữ.

## 11. Quy trình chẩn đoán an toàn khi disk tăng

### Trường hợp A — Đọc không thấy bản ghi TTL 1 ngày nhưng disk không giảm

**Giải thích có khả năng:** bản ghi đã expired logic; SSTable vẫn chứa dữ liệu TTL 30 ngày hoặc chưa được compact/GC.  
**Làm gì:** kiểm tra retention distribution, SSTable metadata, compaction và snapshot. Không xóa SSTable thủ công.

### Trường hợp B — Nhiều tombstone scanned và p99 đọc tăng

**Giải thích có khả năng:** query duyệt nhiều cell đã hết hạn, partition hoặc dải clustering quá rộng.  
**Làm gì:** sửa access pattern/partition bucketing, cân nhắc tách retention class, đánh giá compaction thích hợp và đo lại p95/p99.

### Trường hợp C — TWCS nhưng vẫn giữ SSTable rất lâu

**Giải thích có khả năng:** TTL ngắn/dài trộn trong cùng cửa sổ, dữ liệu đến trễ, update dữ liệu cũ hoặc tệp chứa dữ liệu không TTL.  
**Làm gì:** phân tích nhóm write, kích thước cửa sổ, timestamp, backfill và tỷ lệ dữ liệu sống; TWCS không tự giải quyết TTL hỗn hợp.

### Trường hợp D — Muốn hạ `gc_grace_seconds` để dọn nhanh

**Rủi ro:** purge tombstone quá sớm trong hệ thống có replica bỏ lỡ delete, chưa repair hoặc còn SSTable chồng lấp có thể gây zombie data.  
**Làm gì:** chứng minh tính an toàn bằng RF, thời gian replica có thể offline, lịch repair và đặc tính workload trước khi thay đổi chính sách; không áp dụng giá trị 0 một cách tùy tiện.

### Trường hợp E — Compaction hoàn tất nhưng dung lượng OS không giảm

**Giải thích có khả năng:** tệp được giữ bởi snapshot/backup, compaction vẫn tạo đầu ra lớn vì còn dữ liệu sống, hoặc các tệp khác tiếp tục nhận ghi.  
**Làm gì:** kiểm tra thống kê live/total, snapshot retention và disk headroom theo quy trình quản trị; không xóa file của Cassandra bằng tay.

## 12. Lựa chọn kiến trúc cho hệ thống thực

Có thể dùng bảng quyết định sau trước khi chọn một bảng hay nhiều bảng:

| Câu hỏi | Nếu câu trả lời là “có” | Hướng xử lý |
| --- | --- | --- |
| TTL khác nhau rất lớn, ví dụ giờ và tháng? | Nhiều hàng hết hạn rất sớm so với phần còn lại | Ưu tiên thử tách bảng theo retention |
| Workload append-only và timestamp tương đối tuần tự? | Cơ hội gom SSTable theo cửa sổ thời gian | Đánh giá TWCS và cửa sổ phù hợp |
| Có nhiều update/delete/backfill trên dữ liệu cũ? | SSTable chồng lấp và mốc TTL khó đồng nhất | Thử STCS/LCS hoặc thiết kế lại luồng, benchmark kỹ trước khi dùng TWCS |
| Có truy vấn cần hợp nhất cả hai loại sự kiện? | Tách bảng có thể làm API phức tạp hơn | Đánh giá merge/read model hoặc projection, ghi rõ ràng buộc phân trang |
| Dữ liệu đã TTL-expire nhưng partition vẫn có row sống? | Một phần SSTable không thể drop whole-file | Quan sát compaction và cân nhắc tách retention |
| Repair/replica offline chưa ổn định? | Không thể tự tin rút ngắn grace | Ưu tiên sửa quy trình repair/khôi phục |
| SLO ghi nhạy với compaction I/O? | Tái ghi nhiều SSTable hỗn hợp gây write amplification | Thiết kế dữ liệu dễ drop nguyên SSTable hơn |

Tách dữ liệu theo retention phải được đánh giá cùng **thiết kế bảng theo truy vấn** của Cassandra. Không tạo hàng loạt bảng chỉ để “dễ dọn rác” nếu API sẽ cần quét qua nhiều bảng, nhiều bucket, nhiều datacenter; hãy cân bằng chi phí đọc, ghi, vận hành và nhất quán dữ liệu.

## 13. Những ngộ nhận cần tránh

**“TTL hết nghĩa là byte đã biến mất khỏi SSTable.”** Sai. TTL hết làm cell không còn sống logic; thu hồi vật lý có thể chậm hơn rất lâu.

**“90% dữ liệu trong SSTable đã hết TTL nên có thể xóa cả tệp.”** Sai. Nếu 10% còn sống, xóa nguyên tệp sẽ làm mất dữ liệu cần giữ.

**“TWCS luôn giải quyết bảng nhiều TTL.”** Sai. TWCS nhóm theo cửa sổ thời gian; không tự chia theo độ dài TTL.

**“Đặt partition key theo ngày là đủ để mỗi SSTable chỉ chứa dữ liệu ngày đó.”** Sai. Một SSTable có thể chứa nhiều partition và nhiều ngày; partition key và ranh giới SSTable là hai lớp khác nhau.

**“`gc_grace_seconds` là thời gian bắt buộc file sẽ bị xóa.”** Sai. Nó liên quan điều kiện GC của metadata xóa; compaction và SSTable overlap vẫn quyết định lúc thu hồi.

**“Repair xong là mọi tombstone biến mất.”** Sai. Repair đồng bộ replica, không bắt buộc compaction xóa toàn bộ metadata trong SSTable ngay.

**“Một bảng có `default_time_to_live` thì mọi bản ghi hết hạn cùng lúc.”** Sai. TTL tính cho mutation/cell theo thời điểm ghi; giá trị có thể bị thay bằng TTL khác.

**“Ép compaction sẽ luôn thu hồi toàn bộ phần hết hạn.”** Sai. Cell chưa đủ điều kiện GC, dữ liệu sống, tệp chồng lấp hoặc snapshot vẫn có thể giữ dung lượng; ép compaction còn tạo tải lớn.

**“Ghi lại cùng khóa với TTL giúp retry hoàn toàn idempotent.”** Sai nếu lần retry tạo timestamp/thời điểm hết hạn mới hoặc thay đổi giá trị và ngữ nghĩa nghiệp vụ.

## 14. Câu hỏi và bài tập tự kiểm tra

1. Một SSTable chứa 95% dữ liệu TTL 1 ngày và 5% dữ liệu TTL 90 ngày. Sau ngày thứ ba, tại sao nó chưa thể bị xóa nguyên tệp?
2. Giải thích sự khác nhau giữa `TTL(payload)=null` khi cell chưa từng đặt TTL, khi cell đã hết hạn và khi cột không còn giá trị sống.
3. Nếu dùng TWCS với cửa sổ 1 ngày nhưng ghi TTL 1 ngày và 30 ngày trong cùng cửa sổ, TWCS có tự biến hai nhóm thành hai SSTable riêng không? Vì sao?
4. Phân tích ba mốc: ghi mutation, TTL hết hạn, tombstone/SSTable được GC. Mốc nào được xác định bởi `USING TTL`?
5. Vì sao sau khi `DELETE` hoặc TTL expire vẫn phải cân nhắc replica bị offline và lịch repair trước khi thay `gc_grace_seconds`?
6. Một ứng dụng retry bản ghi sau timeout bằng cách sinh UUID mới và dùng TTL 1 ngày. Có những rủi ro nào về trùng dữ liệu và thời điểm hết hạn?
7. Khi thiết kế hai bảng retention, làm sao đáp ứng API “xem toàn bộ sự kiện trong 24 giờ” nếu cả hai loại sự kiện phải hiển thị?
8. Hãy nêu bốn chỉ số đủ để phân biệt “TTL không áp dụng” với “TTL đã hết nhưng dữ liệu vật lý chưa được thu hồi”.
9. Một SSTable không còn trong danh sách dữ liệu active nhưng đĩa vẫn đầy. Vì sao snapshot hoặc backup có thể là nguyên nhân?
10. Nếu có 100 GiB/ngày ở TTL 1 ngày và 2 GiB/ngày ở TTL 30 ngày, vì sao dự báo disk chỉ theo 160 GiB live data là thiếu?

## 15. Ghi nhớ theo dòng thời gian

```text
WRITE với TTL khác nhau
        |
        v
Memtable -> flush -> SSTable có cả cell TTL ngắn và dài
        |
        +--> TTL ngắn hết hạn: không còn xuất hiện như dữ liệu sống
        |                  |
        |                  +--> metadata hết hạn vẫn có thể nằm trong SSTable
        |
        +--> TTL dài còn sống: SSTable chưa thể drop whole-file
                           |
                           +--> compaction an toàn có thể bỏ các cell đủ điều kiện
                           |
                           +--> khi toàn bộ tệp hết hạn, đủ điều kiện GC/overlap:
                                có cơ hội xóa nguyên SSTable
```

**Kết luận:** Trộn TTL rất ngắn và rất dài trong cùng bảng có thể dẫn đến **SSTable còn sống vì một phần dữ liệu dài hạn**, khiến nhiều byte đã hết hạn không được thu hồi nhanh. TTL quyết định **khả năng hiển thị logic**, còn compaction, `gc_grace_seconds`, SSTable overlap, repair và chính sách lưu trữ quyết định **khả năng xóa vật lý**. Với workload time-series, hãy thử tách retention class và dùng TWCS phù hợp khi dữ liệu có vòng đời đồng nhất; xác nhận lựa chọn bằng metrics dung lượng, tombstone và p99 đọc/ghi thực tế.
