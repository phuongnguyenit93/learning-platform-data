# DELETE, NULL và TTL hết hạn tạo dấu xóa như thế nào

Trong Apache Cassandra, **xóa dữ liệu không giống việc lập tức gỡ một bản ghi khỏi mọi tệp trên đĩa**. Cassandra dùng kiến trúc ghi kiểu *log-structured merge* (LSM): dữ liệu được ghi vào commit log/memtable, flush thành SSTable bất biến và được hợp nhất dần qua compaction. Khi cần xóa, Cassandra ghi **tombstone** — một dấu xóa có thông tin thời gian — để các replica và các SSTable biết rằng phiên bản dữ liệu cũ không còn được phép xuất hiện trong kết quả đọc.

Có ba tình huống thường dẫn đến trạng thái xóa:

1. Một lệnh **`DELETE`** xóa cột, hàng, khoảng hàng hoặc toàn phân vùng.
2. Một thao tác ghi **`NULL`** vào giá trị cột — chẳng hạn `UPDATE ... SET payload = null` — mang ngữ nghĩa xóa giá trị đó.
3. Một giá trị có **TTL** hết hạn: giá trị trở thành dữ liệu đã hết hạn và được xử lý như tombstone khi đọc/thu hồi, **không cần có một câu lệnh `DELETE` mới** tại đúng thời điểm hết hạn.

Tombstone cần thiết để một giá trị cũ còn nằm trên SSTable hoặc replica chậm cập nhật **không tự xuất hiện trở lại**. Nhưng quá nhiều tombstone cũng có thể làm truy vấn tốn CPU/I/O và khiến compaction phức tạp hơn. Đó là lý do chương **Tombstone và thu hồi** cần được hiểu cùng partition key, replication, consistency level, compaction, repair và các thao tác CQL/Java.

Sau bài học, bạn có thể:

- Phân biệt **dữ liệu sống**, **giá trị chưa từng tồn tại**, **NULL** và **tombstone**.
- Giải thích tombstone hình thành từ `DELETE`, ghi `NULL` và TTL hết hạn.
- Phân biệt xóa **một cell, một hàng, một khoảng clustering rows hoặc cả phân vùng**.
- Hiểu cách **write timestamp** và các replica quyết định một giá trị có còn được đọc thấy không.
- Giải thích vì sao hết TTL/xóa **không đồng nghĩa** dữ liệu được thu hồi vật lý tức thì.
- Nhận biết dấu hiệu truy vấn quét nhiều tombstone và cách hạn chế chúng trong thiết kế bảng.
- Thực hành CQL và Java Driver khi xóa hoặc ghi dữ liệu có TTL.

## 1. Tombstone giải quyết vấn đề gì?

Giả sử có một bản ghi `payload = 'temperature=38.1'` đã được ghi thành công. Vì Cassandra có nhiều replica và nhiều SSTable, bản ghi này có thể đang tồn tại ở **nhiều nơi**. Nếu chỉ xóa dữ liệu trong một memtable hoặc SSTable, phiên bản cũ từ nguồn khác vẫn có thể được đọc ra.

Cassandra giải quyết bằng **dấu xóa có write timestamp**:

```text
T0: Ghi payload = "temperature=38.1"   [timestamp ghi = 100]

   Replica A: SSTable-1 chứa payload
   Replica B: SSTable-2 chứa payload
   Replica C: SSTable-3 chứa payload

T1: DELETE payload                     [timestamp xóa = 200]

   Replica A: payload cũ + tombstone mới
   Replica B: payload cũ + tombstone mới
   Replica C: có thể chưa nhận tombstone ngay

T2: Đọc/hòa giải phiên bản theo timestamp
    tombstone ở 200 che giá trị cũ ở 100
```

Dữ liệu cũ có thể vẫn nằm trên SSTable trong một thời gian. **Tombstone là thông tin cần thiết để biết rằng dữ liệu cũ đã bị xóa về mặt logic**. Sau này, khi compaction xác định có thể thu hồi an toàn, những dữ liệu và tombstone tương ứng mới có thể được loại khỏi các tệp lưu trữ.

> **Điểm cốt lõi:** tombstone là một thành phần của mô hình nhất quán và vòng đời dữ liệu trong Cassandra; nó không đơn thuần là một dòng có cột `deleted = true` mà ứng dụng tự thêm.

### Dữ liệu không tồn tại khác dữ liệu bị xóa

| Trạng thái | Ý nghĩa | Có nhất thiết tồn tại tombstone không? |
| --- | --- | --- |
| Cột chưa từng được ghi | Chưa có giá trị cho cột đó | **Không.** |
| Giá trị còn sống | Có cell hợp lệ tại thời điểm đọc | Không cần tombstone đang thắng giá trị đó. |
| Cột đã bị xóa bằng `DELETE` | Có thao tác xóa cần ngăn phiên bản cũ hiện lại | **Có thể có tombstone** trong lưu trữ. |
| Ghi `NULL` vào cột | CQL coi là xóa giá trị cột | Thường tạo tombstone cho cell tương ứng. |
| Cell có TTL đã hết hạn | Giá trị không còn sống và được xử lý như đã xóa | Được coi như tombstone, không cần lệnh DELETE mới. |
| Cột đọc ra `null` | API/CQL không thấy giá trị hiện hành | **Chưa đủ chứng minh** là từng có tombstone: có thể chưa từng ghi. |

Do đó, `SELECT` trả `null` không phải công cụ để suy ra chính xác loại xóa đã diễn ra.

## 2. Một schema dùng xuyên suốt bài học

Ta thiết kế bảng sự kiện cảm biến theo một **partition key ghép**, để thấy rõ phạm vi xóa:

```sql
CREATE TABLE sensor_events_by_day (
    tenant_id   text,
    sensor_id   uuid,
    event_day   date,
    occurred_at timestamp,
    event_id    uuid,
    event_kind  text,
    payload     text,
    note        text STATIC,
    PRIMARY KEY (
        (tenant_id, sensor_id, event_day),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    occurred_at DESC,
    event_id ASC
);
```

Phân tích:

| Thành phần | Cột | Vai trò |
| --- | --- | --- |
| Partition key | `(tenant_id, sensor_id, event_day)` | Chọn phân vùng và tập replica. |
| Clustering columns | `occurred_at`, `event_id` | Xác định hàng sự kiện trong phân vùng. |
| Regular columns | `event_kind`, `payload` | Giá trị riêng của mỗi sự kiện. |
| Static column | `note` | Giá trị chung cho toàn partition ngày của cảm biến. |

Ghi dữ liệu mẫu:

```sql
INSERT INTO sensor_events_by_day (
    tenant_id, sensor_id, event_day, occurred_at, event_id,
    event_kind, payload
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T08:00:00Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    'reading',
    'temperature=38.1'
);

INSERT INTO sensor_events_by_day (
    tenant_id, sensor_id, event_day, occurred_at, event_id,
    event_kind, payload
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T08:05:00Z',
    7c2c4f75-5c44-4be4-99a0-08688b465200,
    'reading',
    'temperature=38.4'
);
```

Hai hàng thuộc **cùng phân vùng ngày** nhưng có clustering keys khác nhau. Thực hành xóa sau đây có thể được chạy riêng trên dữ liệu vừa khởi tạo; nếu chạy nhiều ví dụ liên tiếp, trạng thái thực tế sẽ phụ thuộc thao tác đã thực hiện trước đó.

## 3. `DELETE` một cột: tạo dấu xóa ở phạm vi cell

Để xóa `payload` của sự kiện lúc 08:00 nhưng giữ `event_kind` và định danh hàng:

```sql
DELETE payload
FROM sensor_events_by_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND occurred_at = '2026-11-21T08:00:00Z'
  AND event_id = 8817a208-1858-4144-86e9-b24d9083e478;
```

Ở đây điều kiện `WHERE` định danh **một hàng** bằng đầy đủ partition và clustering key. Phần `DELETE payload` chỉ làm mất giá trị của cột `payload` trong hàng đó.

Sau khi xóa được quan sát theo consistency level phù hợp, truy vấn có thể cho:

| `occurred_at` | `event_kind` | `payload` |
| --- | --- | --- |
| 08:00 | reading | `null` |

Hàng vẫn tồn tại vì `event_kind` hoặc thông tin sống khác còn có giá trị. Đây là một **cell tombstone**, không phải thao tác xóa toàn bộ hàng.

**Quan trọng:** Cassandra không bắt buộc phải đọc trước xem `payload` có tồn tại không. Lệnh xóa có thể được chấp nhận và ghi tombstone ngay cả khi giá trị trước đó không tồn tại; ngữ nghĩa xóa được dùng để bảo vệ khỏi các phiên bản cũ có thể đến muộn.

### Xóa một static column

Vì `note` được khai báo `STATIC`, nó thuộc mức phân vùng. Có thể xóa `note` chỉ bằng partition key:

```sql
DELETE note
FROM sensor_events_by_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21';
```

Thao tác này không xóa các hàng sự kiện. Static column có thể xuất hiện trên nhiều hàng **kết quả** khi SELECT, nhưng về ngữ nghĩa nó vẫn chỉ thuộc **một phân vùng**; không cần phát DELETE cho từng clustering row.

## 4. `DELETE` một hàng, một khoảng hoặc toàn phân vùng

Phạm vi `DELETE` quyết định kiểu tombstone được tạo và vùng dữ liệu mà nó che.

### 4.1. Xóa một hàng theo full primary key

```sql
DELETE FROM sensor_events_by_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND occurred_at = '2026-11-21T08:00:00Z'
  AND event_id = 8817a208-1858-4144-86e9-b24d9083e478;
```

Không nêu tên cột sau `DELETE` nghĩa là xóa **hàng clustering** tương ứng, chứ không chỉ một regular column. Cassandra có thể biểu diễn thao tác qua **row deletion tombstone** để che các cell cũ của hàng đó.

Nếu có static column `note`, xóa một hàng clustering như trên **không mặc nhiên xóa `note`** của phân vùng.

### 4.2. Xóa một đoạn clustering keys

Với schema có clustering `occurred_at` rồi `event_id`, một thao tác xóa theo **khoảng clustering hợp lệ** trong cùng phân vùng có thể được biểu diễn bằng **range tombstone**:

```sql
DELETE FROM sensor_events_by_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND occurred_at >= '2026-11-21T08:00:00Z'
  AND occurred_at <  '2026-11-21T09:00:00Z';
```

Đây là ví dụ về xóa một đoạn **bên trong một partition**, không phải query phân tán toàn bộ bảng. Chi tiết các dạng điều kiện range `DELETE` được hỗ trợ và cách biểu diễn tombstone có thể khác theo phiên bản/schema; cần thử trên phiên bản đang sử dụng trước khi áp dụng trong vận hành.

Một **range tombstone** có thể che nhiều hàng clustering mà không cần một CQL DELETE riêng cho từng hàng. Tuy nhiên, nó vẫn có thể gây chi phí đọc qua đoạn bị xóa, đặc biệt trước khi compaction dọn dữ liệu.

### 4.3. Xóa cả phân vùng

```sql
DELETE FROM sensor_events_by_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21';
```

Đây là **partition deletion**. Nó tác động tới các hàng clustering và static data nằm trong partition key đã nêu. Một partition-level tombstone giúp che dữ liệu cũ của toàn phân vùng ở write timestamp của thao tác xóa.

Bảng so sánh:

| Câu lệnh | Phạm vi logic | Khái niệm tombstone |
| --- | --- | --- |
| `DELETE payload ... WHERE full_primary_key` | Một regular column trong một hàng | Cell tombstone. |
| `DELETE note ... WHERE partition_key` | Một static column của phân vùng | Static-cell tombstone. |
| `DELETE FROM ... WHERE full_primary_key` | Một hàng clustering | Row tombstone. |
| `DELETE FROM ... WHERE partition_key AND clustering_range` | Một khoảng clustering rows | Range tombstone, khi thao tác được hỗ trợ. |
| `DELETE FROM ... WHERE partition_key` | Toàn phân vùng, gồm static data | Partition tombstone. |

**Không nên xem xóa cả partition là một lệnh “xóa vật lý nhanh không tạo tombstone”.** Về mặt lưu trữ phân tán, Cassandra vẫn cần ghi dấu xóa có thông tin thời gian để tránh dữ liệu cũ xuất hiện trở lại.

## 5. `NULL` trong CQL: không phải “không đụng vào cột”

Một nhầm lẫn rất phổ biến là xem `NULL` giống việc bỏ qua cột hoặc giữ nguyên giá trị hiện tại. Trong Cassandra, **ghi `NULL` vào một regular column thường mang ngữ nghĩa xóa giá trị của cột đó**.

Ví dụ:

```sql
UPDATE sensor_events_by_day
SET payload = null
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND occurred_at = '2026-11-21T08:05:00Z'
  AND event_id = 7c2c4f75-5c44-4be4-99a0-08688b465200;
```

Theo ngữ nghĩa CQL, thao tác này xóa cell `payload` của hàng được chỉ định và có thể tạo tombstone, tương tự mục đích của `DELETE payload`.

### Ba tình huống khác nhau

Giả sử hàng đã có `event_kind = 'reading'` và `payload = 'temperature=38.4'`.

**Tình huống A — Không đề cập cột:**

```sql
UPDATE sensor_events_by_day
SET event_kind = 'calibrated-reading'
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND occurred_at = '2026-11-21T08:05:00Z'
  AND event_id = 7c2c4f75-5c44-4be4-99a0-08688b465200;
```

`payload` **không được đề cập**, nên thao tác này không yêu cầu xóa nó.

**Tình huống B — Ghi NULL:**

```sql
UPDATE sensor_events_by_day
SET payload = null
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND occurred_at = '2026-11-21T08:05:00Z'
  AND event_id = 7c2c4f75-5c44-4be4-99a0-08688b465200;
```

`payload` bị xóa theo ngữ nghĩa CQL; giá trị cũ có thể bị che bởi tombstone.

**Tình huống C — Truyền UNSET qua driver:**

Trong prepared statement, Cassandra hỗ trợ trạng thái **UNSET** cho các bind variables được phép không gửi giá trị. `UNSET` có nghĩa *không thực hiện mutation cho cột đó*, khác hẳn `NULL`. Cơ chế và API cụ thể tùy driver/version; với Java Driver, hãy dùng chức năng *unset* của bound statement khi thật sự cần bỏ qua cập nhật, thay vì bind `null` rồi hy vọng cột được giữ nguyên.

| Trường hợp | Ý nghĩa mong muốn | Tác động điển hình |
| --- | --- | --- |
| Bỏ hẳn tên cột khỏi `INSERT`/`UPDATE` | Không cập nhật cột | Không tạo tombstone **chỉ vì thiếu cột**. |
| Ghi `payload = null` | Xóa giá trị cột | Có thể tạo cell tombstone. |
| Bind biến dạng `UNSET` | Không gửi mutation cho cột đó | Không thay đổi cell tương ứng. |
| Ghi chuỗi rỗng `''` vào cột `text` | Lưu giá trị text rỗng | Không tương đương `NULL`. |
| Đọc `payload` và nhận `null` | Không thấy giá trị hiện hành | Không chứng minh nguyên nhân là NULL/DELETE/TTL. |

**Không thể ghi NULL làm thành phần của primary key** để biểu diễn một hàng “chưa có khóa”; Cassandra yêu cầu các thành phần khóa cần thiết hợp lệ.

### `INSERT` với cột nhận NULL

`INSERT` không nhất thiết có nghĩa “chèn đủ mọi cột”. Nếu một cột được truyền rõ ràng dưới dạng `null`, nó có semantics xóa cell đó. Nếu **không liệt kê cột** trong danh sách INSERT, thao tác không tự tạo tombstone cho cột bị bỏ qua.

Đối với JSON API hoặc mapper Java, cần phân biệt rõ trường **không xuất hiện** và trường **có giá trị NULL** trước khi tạo CQL. Nếu tầng mapping biến mọi thuộc tính vắng mặt thành `null` rồi ghi lại toàn bộ object, nó có thể sinh rất nhiều tombstone ngoài ý muốn.

## 6. TTL: hết hạn là xóa logic, không phải một DELETE mới

TTL (*time to live*) cho phép một giá trị tự hết hạn sau số giây được cấu hình. Ví dụ ghi sự kiện với TTL một giờ:

```sql
INSERT INTO sensor_events_by_day (
    tenant_id, sensor_id, event_day, occurred_at, event_id,
    event_kind, payload
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T09:00:00Z',
    4e52e99a-178e-4d5b-9a31-027d5956e5b8,
    'reading',
    'temperature=38.7'
) USING TTL 3600;
```

Đây là TTL **3.600 giây** cho các giá trị được ghi bởi thao tác, theo semantics TTL của Cassandra. Khi hết hạn, các giá trị đó không còn được xem là sống trong quá trình đọc. **Không có một client nào phải gửi `DELETE` đúng ở giây thứ 3.600.**

```text
Thời điểm ghi                      Thời điểm hết TTL
     |                                   |
     v                                   v
 Cell sống, mang TTL               Cell đã hết hạn
     |                                   |
     |------ được SELECT thấy -----------|
                                         |
                                         v
                              Được xử lý như tombstone
                                         |
                                         v
                          Chờ điều kiện thu hồi khi compaction
```

Điểm tinh tế: TTL thường được lưu dưới dạng **thông tin hết hạn gắn với cell**. Khi hết hạn, Cassandra xử lý cell đó như dữ liệu đã xóa. Không nhất thiết có một mutation `DELETE` mới được phát tới các replica vào thời điểm hết hạn; do đó không nên hình dung cluster phải lên lịch hàng triệu câu lệnh DELETE.

### `USING TTL` trên UPDATE

Có thể đặt TTL cho giá trị mới trong thao tác cập nhật:

```sql
UPDATE sensor_events_by_day
USING TTL 1800
SET payload = 'temporary-reading'
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND occurred_at = '2026-11-21T08:05:00Z'
  AND event_id = 7c2c4f75-5c44-4be4-99a0-08688b465200;
```

TTL mới áp dụng cho **cell được viết lại**. Nó không có nghĩa mọi hàng trong cùng partition tự hết hạn sau 1.800 giây. Nếu `event_kind` chưa được thay đổi và không có TTL, cell này có thể vẫn còn sau khi `payload` hết hạn.

### TTL mặc định ở mức bảng

Cassandra cũng có tùy chọn schema `default_time_to_live`. Ví dụ:

```sql
ALTER TABLE sensor_events_by_day
WITH default_time_to_live = 86400;
```

Tùy chọn này đặt TTL mặc định cho các ghi thuộc bảng theo semantics của phiên bản, trừ trường hợp ghi có chỉ định TTL phù hợp. **Thay đổi TTL mặc định không phải thao tác xóa vật lý toàn bộ dữ liệu cũ.** Cần kiểm tra tác động với ghi mới, dữ liệu đang sống và các cột có TTL riêng trước khi áp dụng production.

> **Lưu ý:** nếu chạy thực hành theo thứ tự, `ALTER TABLE ... default_time_to_live` làm thay đổi hành vi ghi tiếp theo. Hãy thực hiện trên bảng thử nghiệm, không tự ý áp dụng lên bảng đang phục vụ hệ thống.

## 7. Xem TTL và write timestamp bằng CQL

Có thể kiểm tra metadata của một giá trị hiện hành:

```sql
SELECT occurred_at, event_id,
       payload,
       TTL(payload),
       WRITETIME(payload)
FROM sensor_events_by_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND occurred_at = '2026-11-21T09:00:00Z'
  AND event_id = 4e52e99a-178e-4d5b-9a31-027d5956e5b8;
```

Diễn giải:

- `TTL(payload)` cho số giây TTL **còn lại** nếu cell hiện hành có TTL và còn sống; kết quả có thể là `null` nếu cell không còn giá trị, hoặc không có TTL.
- `WRITETIME(payload)` cho write timestamp của giá trị theo đơn vị **microsecond** khi khả dụng; nó không phải `occurred_at` (thời điểm nghiệp vụ).
- Sau khi cell hết hạn, truy vấn thông thường có thể không còn trả ra giá trị của cell; `TTL`/`WRITETIME` **không phải công cụ liệt kê đầy đủ tombstone vật lý**.
- Nếu các cell trong cùng hàng có TTL khác nhau, không thể suy toàn bộ trạng thái hàng từ TTL của riêng `payload`.

### TTL tính từ lúc ghi, không nhất thiết từ event time

Giả sử một sự kiện `occurred_at = 2026-11-20T10:00:00Z` nhưng đến cluster vào `2026-11-21T10:00:00Z`. Nếu lúc đến mới ghi `USING TTL 86400`, nó hết hạn theo thời gian ghi, **không tự hết hạn ở 2026-11-21T10:00:00Z** chỉ vì event time nằm trước một ngày.

Đối với retention tính theo thời điểm nghiệp vụ, ứng dụng cần chủ động tính TTL còn lại hoặc dùng chính sách vòng đời phù hợp, đặc biệt với sự kiện đến trễ và backfill.

## 8. Timestamp quyết định giá trị hay dấu xóa nào thắng

Cassandra gắn write timestamp với cell/mutation. Khi nhiều phiên bản của cùng dữ liệu tồn tại, quá trình hòa giải dùng timestamp và các quy tắc xử lý trường hợp hòa để xác định trạng thái hợp lệ.

Ví dụ ý tưởng:

```text
Cell payload = "A"            write timestamp 100
Cell payload = "B"            write timestamp 150
DELETE payload               write timestamp 200

Khi đọc/merge: tombstone tại 200 che A và B.

Sau đó:
Cell payload = "C"            write timestamp 250

Khi đọc/merge: C có thể hiện diện vì timestamp mới hơn tombstone.
```

**Các giá trị timestamp này chỉ để minh họa thứ tự**, không phải giá trị microsecond thực dùng trong production. Trong Cassandra, thao tác DELETE không có nghĩa “cấm vĩnh viễn mọi lần ghi vào khóa này”; một lần ghi hợp lệ với write timestamp mới hơn có thể tạo giá trị hiện hành mới.

Những điều cần nhớ:

1. **Tombstone cần được giữ đủ lâu** để che các phiên bản cũ có timestamp thấp hơn ở replica/SSTable.
2. Ghi nhiều lần vào cùng primary key có thể tạo nhiều phiên bản cell trên các SSTable cho đến khi compaction.
3. Write timestamps không nhất thiết trùng thứ tự nhận request theo đồng hồ ứng dụng; ghi với timestamp do client chỉ định cần được kiểm soát rất cẩn thận.
4. Một lệnh `DELETE` không biết gì về ý định nghiệp vụ “vĩnh viễn xóa” nếu ứng dụng sau đó lại ghi dữ liệu với timestamp mới hơn.
5. Nếu client clock sai hoặc ghi timestamp thủ công ở tương lai, một tombstone có thể che cả các lần ghi sau theo thời gian thực cho đến khi timestamp ghi mới vượt nó.

Đặc biệt, không nên gán write timestamp quá xa tương lai chỉ để “đảm bảo DELETE thắng”. Điều đó có thể gây các lỗi khó khắc phục khi dữ liệu hợp lệ được ghi sau này.

## 9. Vì sao replica chậm cập nhật có thể làm dữ liệu sống lại?

Cassandra phân phối dữ liệu theo partition key và replication strategy. Với replication factor `3`, giả sử ba replica chịu trách nhiệm cho một partition.

```text
T0: Cả A, B, C đều có payload = "A" (timestamp 100).

T1: C bị mất kết nối tạm thời.
    DELETE payload (timestamp 200) đến A và B.
    A, B giữ tombstone; C vẫn giữ "A".

T2: Client đọc theo consistency phù hợp và hòa giải:
    tombstone mới có thể che giá trị "A" cũ.

T3: Trong giai đoạn an toàn:
    Repair/đồng bộ giúp C nhận dấu xóa trước khi dấu xóa được
    thu hồi khỏi mọi nơi có thể dùng để hòa giải.

T4: Sau khi điều kiện an toàn được đáp ứng:
    Compaction có thể dọn tombstone/dữ liệu cũ.
```

Nếu C không nhận được xóa trong thời gian quá dài và các replica khác **đã thu hồi tombstone trước khi sửa chữa sai khác**, giá trị cũ trên C có nguy cơ được xem như dữ liệu còn sống trở lại. Trường hợp này thường được gọi là **zombie data** (*dữ liệu sống lại*).

Cassandra dùng cơ chế retention của tombstone, kết hợp repair và các điều kiện compaction, để giảm rủi ro đó.

### `gc_grace_seconds` là gì?

`gc_grace_seconds` là tham số của bảng liên quan đến **khoảng an toàn trước khi có thể thu hồi tombstone**, thường được diễn tả bằng số giây. Tham số này liên quan trực tiếp đến kế hoạch vận hành replica và repair.

**Không được hiểu**:

- “Sau đúng `gc_grace_seconds`, mọi tombstone chắc chắn biến mất khỏi đĩa.”
- “Giảm `gc_grace_seconds` luôn làm đọc nhanh hơn mà không có rủi ro.”
- “Cứ chạy compaction thủ công là mọi DELETE đã được thu hồi an toàn.”
- “`LOCAL_QUORUM` làm repair không còn cần thiết trong mọi tình huống.”

Tombstone chỉ có thể được loại đi khi các điều kiện thu hồi an toàn thỏa mãn, tùy cấu hình, trạng thái SSTable, khoảng grace và chiến lược thu hồi của phiên bản Cassandra. Repair phải được lên lịch và vận hành nhất quán với chính sách này; không nên tùy ý giảm grace trong hệ thống có replica có thể gián đoạn lâu.

### Consistency level không thay thế tombstone

Consistency level quy định số replica cần tham gia xác nhận/đọc theo chính sách truy vấn. Nó ảnh hưởng khả năng nhìn thấy trạng thái mới tại một thời điểm, nhưng **không tự biến các dữ liệu cũ trên mọi replica thành dữ liệu đã xóa vật lý**.

Thao tác xóa có thể được xác nhận ở một consistency level trong khi replica khác còn đang chậm; cơ chế tombstone, repair và compaction vẫn có vai trò thiết yếu. Để điều tra kết quả đọc “đã xóa nhưng vẫn thấy”, cần xét **replica trạng thái nào, thời điểm ghi, CL, timestamp và lịch repair** thay vì chỉ dựa trên một truy vấn thử.

## 10. Thu hồi vật lý diễn ra khi nào?

Tombstone làm dữ liệu không còn sống **về mặt logic**, nhưng thu hồi vật lý là một quá trình khác. Cassandra dùng compaction để xem xét dữ liệu từ nhiều SSTable và loại bỏ các phiên bản không còn cần thiết khi đủ điều kiện.

```text
DELETE / NULL / TTL expiry
           |
           v
  Tombstone hoặc cell đã hết hạn
           |
           v
  Đọc: không trả giá trị bị xóa
           |
           +---> Replica khác có thể còn giá trị cũ
           |          |
           |          v
           |      cần được hòa giải/repair an toàn
           |
           v
  Đủ điều kiện grace và kiểm tra overlap/phiên bản
           |
           v
  Compaction có thể thu hồi tombstone và dữ liệu đã xóa
           |
           v
  Giảm footprint vật lý trên SSTable
```

Các điều kiện thu hồi có thể phụ thuộc vào:

- **Tuổi tombstone** so với `gc_grace_seconds` và chính sách tương ứng.
- **SSTable overlap:** một SSTable khác có thể vẫn chứa phiên bản cũ mà tombstone phải che. Việc loại bỏ tombstone quá sớm khi dữ liệu cũ còn tồn tại có thể làm bản ghi xuất hiện lại.
- **Repair và trạng thái replica:** nguy cơ một replica đã bỏ lỡ xóa.
- **Chiến lược compaction, TTL và kiểu ghi:** thời gian dữ liệu được hợp nhất hoặc một SSTable đủ điều kiện được dọn.
- **Khác biệt phiên bản/cơ chế tombstone garbage collection:** cần xem cấu hình triển khai thực, không áp công thức cố định cho mọi cluster.

Vì vậy, sau `DELETE` hoặc sau khi TTL hết hạn, số byte trên đĩa có thể **chưa giảm ngay**, thậm chí tạm tăng vì thao tác mới ghi thêm dấu xóa. Điều này là hành vi có thể xảy ra trong lưu trữ LSM, không tự chứng minh DELETE thất bại.

## 11. Những thao tác dễ sinh nhiều tombstone ngoài ý muốn

### Xóa từng hàng trong một phân vùng cực lớn

Ví dụ một ứng dụng thực hiện một triệu lệnh `DELETE ... WHERE full_primary_key` để xóa một triệu sự kiện cũ. Nó có thể tạo nhiều row tombstones hoặc cell tombstones, làm đọc đoạn dữ liệu ấy và compaction tốn tài nguyên.

Nếu yêu cầu thực sự là xóa **cả một phân vùng** và không cần giữ lại dữ liệu nào bên trong, partition-level DELETE có thể khác đáng kể về số mutation/tombstone so với xóa từng hàng. Nhưng **không xóa cả phân vùng** nếu nó còn chứa các hàng hợp lệ hoặc static data cần giữ.

### Cập nhật nhiều cột bằng NULL

Một API cập nhật một trường nhưng vô tình gửi `null` cho toàn bộ trường còn lại có thể phát sinh hàng loạt cell tombstones.

Ví dụ request JSON chỉ gửi `payload` nhưng mapper ghi thêm `event_kind = null`. Đây không phải “không thay đổi `event_kind`”; nó là thao tác xóa giá trị cột này.

### TTL rất ngắn trên dữ liệu ghi dày

Nếu hàng triệu cell hết hạn sau vài phút, một thời gian ngắn sau khi ghi có thể xuất hiện rất nhiều dữ liệu hết hạn/tombstone để đọc path và compaction xử lý.

TTL không xấu tự thân; vấn đề là **tỷ lệ tạo cell, tỷ lệ hết hạn, dạng truy vấn và cách dữ liệu được nhóm theo partition**. Với time-series, có thể cần time bucketing và chiến lược compaction phù hợp thay vì dồn toàn bộ lịch sử vào một partition.

### Collection lớn và nhiều thao tác sửa/xóa phần tử

Với các collection không `frozen`, xóa phần tử hoặc thay thế collection có thể tạo tombstone ở mức element/collection. Một hàng chứa collection liên tục phình to hoặc bị thay thế nhiều lần sẽ gây chi phí không giống vài cột scalar nhỏ.

Ví dụ về bảng thử nghiệm:

```sql
CREATE TABLE session_attributes_by_id (
    session_id uuid PRIMARY KEY,
    attributes map<text, text>
);

INSERT INTO session_attributes_by_id (session_id, attributes)
VALUES (
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    {'theme': 'dark', 'locale': 'vi'}
);

DELETE attributes['locale']
FROM session_attributes_by_id
WHERE session_id = 327a71e9-f562-4b54-94b9-2138a9e30b12;
```

Xóa một phần tử của map có thể tạo tombstone cho phần tử tương ứng. Với workload cập nhật collection liên tục, nên đánh giá việc mô hình hóa từng thuộc tính thành hàng riêng hoặc giữ collection nhỏ, tùy đường truy vấn.

## 12. Tombstone ảnh hưởng đến đọc/ghi và vận hành như thế nào?

### Đường đọc

Một câu `SELECT` có `LIMIT 20` không bảo đảm replica chỉ xét đúng 20 cell. Nếu nhiều hàng gần đầu dải clustering đã bị xóa hoặc hết TTL, Cassandra có thể phải duyệt **rất nhiều tombstone** mới tìm đủ 20 hàng sống.

```text
Truy vấn 20 sự kiện mới nhất

[expired][deleted][deleted][expired][deleted]...[live #1]
[expired][deleted][expired]...[live #2]
... nhiều marker khác ...
[live #20]

Kết quả: 20 hàng
Công việc đọc: có thể phải xử lý nhiều hơn 20 vị trí dữ liệu
```

Dấu hiệu thường gặp:

- Độ trễ p95/p99 tăng dù số hàng trả về thấp.
- Read timeout hoặc warning liên quan tombstone trong log/tracing.
- Đọc theo khoảng thời gian có nhiều dữ liệu TTL hết hạn chậm hơn khoảng khác.
- CPU/I/O tăng khi cần merge nhiều SSTable và so sánh tombstone.

### Đường ghi

Ghi tombstone thường là một mutation trong cơ chế LSM, **không yêu cầu quét ngay mọi SSTable để xóa dữ liệu cũ**. Điều đó giúp ghi có thể nhanh, nhưng chi phí của tombstone xuất hiện **về sau** khi đọc hoặc compaction.

Không nên hiểu tombstone là nguyên nhân làm mọi DELETE chậm ngay tại thời điểm ghi; cần quan sát cả lưu lượng mutation, tải replica và công việc nền.

### Compaction, repair và streaming

Tombstone phải tồn tại đủ lâu để giữ ngữ nghĩa xóa giữa các SSTable/replica. Khi số lượng lớn, công việc compaction và quá trình quản lý dữ liệu trên replica có thể tốn I/O, CPU, thời gian và disk headroom.

Khi xử lý dữ liệu xóa trong hệ thống có replication, các quy trình repair và chính sách tombstone retention phải phối hợp. Không cố “dọn sạch” bằng việc hạ grace hoặc compaction ồ ạt khi chưa xác định điều kiện an toàn.

## 13. Quan sát tombstone bằng công cụ và CQL

### `nodetool tablestats`

Ví dụ với keyspace `app_ks`:

```bash
nodetool tablestats app_ks.sensor_events_by_day
```

Tùy phiên bản, output có thể gồm các trường mô tả **average live cells per slice**, **average tombstones per slice**, read latency, SSTable count và thông tin bảng khác. Các chỉ số này hữu ích để thấy truy vấn trên bảng đang gặp nhiều tombstone hay không.

Điểm giới hạn: đây là số liệu thống kê ở **mức bảng/node và cửa sổ quan sát**, không phải danh sách đầy đủ tombstone của mọi partition key.

### `nodetool tablehistograms`

```bash
nodetool tablehistograms app_ks sensor_events_by_day
```

Histogram có thể cho thấy phân bố partition size, cell count, read latency và các thống kê được phiên bản hỗ trợ. Kết hợp nó với tablestats, metrics ứng dụng và log để tránh nhầm giữa **phân vùng lớn** và **tombstone-heavy**.

### Tracing một truy vấn nghi ngờ

Trong `cqlsh`, có thể bật tracing cho một truy vấn đọc giới hạn:

```sql
TRACING ON;

SELECT occurred_at, event_id, event_kind
FROM sensor_events_by_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
LIMIT 20;

TRACING OFF;
```

Traces có thể giúp xem các bước xử lý truy vấn và lượng dữ liệu/tombstone được quét khi phiên bản cung cấp thông tin liên quan. Tracing có overhead; không bật liên tục cho mọi request production.

### Warning/failure thresholds

Một số phiên bản Cassandra cung cấp tham số cảnh báo hoặc ngưỡng thất bại khi một truy vấn đọc gặp quá nhiều tombstone; tên cấu hình thường được nhắc đến là `tombstone_warn_threshold` và `tombstone_failure_threshold` trong các phiên bản phù hợp.

**Các giá trị/định dạng cụ thể phụ thuộc phiên bản và cấu hình.** Không nên sao chép một “ngưỡng chuẩn” từ môi trường khác rồi dùng như quy tắc an toàn tuyệt đối. Nếu nhận warning, cần kiểm tra query pattern, dữ liệu xóa/hết TTL, phân vùng, mức độ SSTable overlap và trạng thái compaction trước khi quyết định chỉnh ngưỡng.

### `COUNT(*)` không đo được số tombstone

```sql
SELECT COUNT(*)
FROM sensor_events_by_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21';
```

Kết quả là số hàng được truy vấn quan sát theo semantics đọc, **không** phải số tombstone tồn tại trên đĩa. Đếm trên partition lớn cũng có thể tạo tải đáng kể. Vì vậy không dùng `COUNT(*)` làm công cụ đo tombstone định kỳ.

## 14. Java Driver: phân biệt xóa cột và ghi TTL

Ví dụ Java Driver 4.x dùng các `PreparedStatement` rõ ràng cho hai mục đích:

- `DELETE payload`: chủ động xóa giá trị của một event.
- `INSERT ... USING TTL ?`: ghi một event chỉ tồn tại trong số giây đã định.

Giả định `CqlSession` đã kết nối tới keyspace chứa `sensor_events_by_day`.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public final class SensorEventRepository {
    private final CqlSession session;
    private final PreparedStatement deletePayload;
    private final PreparedStatement insertWithTtl;

    public SensorEventRepository(CqlSession session) {
        this.session = session;

        this.deletePayload = session.prepare(
            "DELETE payload FROM sensor_events_by_day " +
            "WHERE tenant_id = ? AND sensor_id = ? AND event_day = ? " +
            "AND occurred_at = ? AND event_id = ?"
        );

        this.insertWithTtl = session.prepare(
            "INSERT INTO sensor_events_by_day " +
            "(tenant_id, sensor_id, event_day, occurred_at, event_id, " +
            "event_kind, payload) " +
            "VALUES (?, ?, ?, ?, ?, ?, ?) USING TTL ?"
        );
    }

    public void removePayload(
            String tenantId, UUID sensorId, LocalDate eventDay,
            Instant occurredAt, UUID eventId) {

        session.execute(deletePayload.bind(
            tenantId, sensorId, eventDay, occurredAt, eventId
        ));
    }

    public void insertExpiringEvent(
            String tenantId, UUID sensorId, LocalDate eventDay,
            Instant occurredAt, UUID eventId,
            String eventKind, String payload, int ttlSeconds) {

        if (ttlSeconds <= 0) {
            throw new IllegalArgumentException("TTL must be positive");
        }

        session.execute(insertWithTtl.bind(
            tenantId, sensorId, eventDay, occurredAt, eventId,
            eventKind, payload, ttlSeconds
        ));
    }
}
```

Đoạn mã cố ý dùng `DELETE payload` thay vì bind `null` để thể hiện rõ ý định nghiệp vụ. Nếu code cần phân biệt “không cập nhật payload” và “xóa payload”, hãy thiết kế API hoặc DTO có **trạng thái vắng mặt** riêng với giá trị `null`, thay vì để framework mapping quyết định ngầm.

Những điểm vận hành:

1. Java bind **đầy đủ partition key và clustering key** cho thao tác xóa cột.
2. TTL truyền theo **giây**; phải có chính sách retention rõ ràng. TTL không dựa vào `occurredAt` trừ khi ứng dụng tự tính từ event time.
3. Giữ `eventId` và `occurredAt` ổn định giữa các lần retry để tránh tạo các hàng mới.
4. Timeout của `DELETE` hoặc `INSERT` không chứng minh mutation chưa được áp dụng; ứng dụng phải có chính sách retry/backoff và consistency phù hợp.
5. Nếu dùng mapper/driver với bind variable `UNSET`, hãy kiểm tra semantics của version cụ thể; **`NULL` và `UNSET` không tương đương**.
6. Ghi cùng event với TTL mới khi retry có thể **thay đổi thời gian hết hạn** tùy mutation và timestamp; idempotency của định danh hàng chưa đồng nghĩa “TTL được áp dụng đúng một lần”.
7. Một câu `DELETE` trên Cassandra không xóa dữ liệu ngay khỏi đĩa của mọi replica; cần phối hợp vận hành compaction/repair.

## 15. Thiết kế để hạn chế tombstone không cần thiết

Cách hiệu quả nhất thường là **giảm các mẫu ghi tạo tombstone hàng loạt**, thay vì chỉ tăng ngưỡng cảnh báo.

### 15.1. Chọn partition key và time bucket theo vòng đời

Dữ liệu time-series thường được truy vấn theo thiết bị, khách hàng và khoảng thời gian. Dùng partition key có bucket ngày/giờ giúp giới hạn lượng dữ liệu và tombstone mà một truy vấn theo bucket phải xem xét.

Ví dụ bảng hiện tại dùng `(tenant_id, sensor_id, event_day)` nên khi đọc ngày `2026-11-21` không phải quét toàn lịch sử của cảm biến. Nếu sự kiện ghi cực dày trong một ngày, có thể cân nhắc bucket giờ hoặc shard sau khi đo tải và fan-out.

**Bucket không tự xóa tombstone**. Nó giúp nhóm dữ liệu theo thời gian và giảm phạm vi truy vấn; TTL/compaction và mô hình mutation vẫn quyết định vòng đời.

### 15.2. Tránh delete theo từng hàng khi có thể thay đổi mô hình retention

Nếu chính sách chỉ giữ dữ liệu trong một thời hạn cố định, có thể đánh giá TTL đồng nhất, time bucketing và compaction strategy phù hợp. Một số workload chuỗi thời gian append-mostly với TTL gần đồng đều có thể thích hợp để đánh giá **TimeWindowCompactionStrategy (TWCS)**, vì SSTable có thể chứa dữ liệu gần nhau về vòng đời.

Tuy nhiên:

- TWCS không đổi partition key và **không bảo đảm** dọn tombstone ngay khi hết TTL.
- Ghi sự kiện đến trễ, cập nhật dữ liệu cũ hoặc TTL quá khác nhau có thể làm việc thu hồi khó hơn.
- Không xóa toàn partition chỉ vì nó “trông cũ” nếu còn dữ liệu sống hoặc quy định retention khác.
- Không giảm `gc_grace_seconds` tùy tiện để khiến dữ liệu vật lý biến mất sớm hơn.

### 15.3. Chỉ ghi giá trị thật sự thay đổi

Đối với API PATCH, phân biệt:

- **Field vắng mặt**: không thay đổi cell.
- **Field chứa giá trị**: cập nhật cell.
- **Field được yêu cầu xóa**: phát `DELETE col` hoặc dùng `null` có chủ đích.

Điều này giúp tránh sinh tombstone do serialize toàn bộ DTO với hàng chục thuộc tính `null` không liên quan.

### 15.4. Kiểm soát collection và payload

Giữ collection có kích thước phù hợp; nếu một map/set/list bị cập nhật hoặc xóa từng phần tử liên tục, cân nhắc chuyển sang nhiều hàng có primary key rõ ràng. Không lưu payload cực lớn vào một cell nếu đường truy vấn và nhu cầu lưu trữ phù hợp mô hình tham chiếu đến object storage.

### 15.5. Thử tải có TTL, xóa và replica failure

Một benchmark chỉ gồm `INSERT` và `SELECT` trên dữ liệu mới chưa phản ánh chi phí tombstone. Cần thử:

- Tỷ lệ `DELETE` theo cell/row/partition.
- Tốc độ TTL hết hạn và phân bố tuổi dữ liệu.
- Độ rộng clustering range và số hàng sống cần trả.
- Hành vi p95/p99 khi compaction, repair hoặc một replica gián đoạn.
- Cơ chế recovery sau thời gian replica bị offline, đặc biệt liên quan tombstone grace.

Mục tiêu là ngăn **độ trễ và rủi ro mất ngữ nghĩa xóa**, không chỉ làm số tombstone được báo xuống thấp trong một lần đo.

## 16. Checklist xử lý một truy vấn chậm vì tombstone

| Câu hỏi kiểm tra | Vì sao cần? |
| --- | --- |
| Query có **đủ partition key** không? | Tránh đọc qua nhiều phân vùng ngoài ý muốn. |
| Khoảng clustering có quá rộng không? | Đọc một dải lớn có thể gặp nhiều dữ liệu đã xóa. |
| Bao nhiêu hàng sống trả về, và bao nhiêu tombstone bị xét? | `LIMIT` không phản ánh chi phí scan thực tế. |
| Tombstone đến từ `DELETE`, ghi `NULL` hay TTL? | Mỗi nguồn có hướng sửa khác nhau. |
| Có map/list/set bị sửa/xóa liên tục không? | Collection có thể tạo nhiều tombstone nội bộ. |
| Có SSTable overlap hoặc compaction backlog không? | Ảnh hưởng việc dọn/merge dữ liệu cũ. |
| Có replica bỏ lỡ delete, repair chậm hoặc cấu hình grace bất thường không? | Liên quan nguy cơ dữ liệu sống lại. |
| Có cần bucket lại partition hoặc thiết kế đường đọc khác không? | Giảm phạm vi dữ liệu mà truy vấn phải xử lý. |
| Metrics/logs/tracing có hỗ trợ kết luận không? | Không thay đổi cấu hình chỉ dựa vào phỏng đoán. |

Một quy trình xử lý hợp lý:

1. Chọn **một truy vấn chậm đại diện** và xác định đúng partition key/đoạn clustering.
2. Xem read latency, tombstones per slice, SSTables per read và các warning liên quan.
3. Đối chiếu nguồn phát sinh xóa/hết hạn từ lịch sử ứng dụng và retention.
4. Xác minh cơ chế compaction, repair và tình trạng replica trước khi can thiệp.
5. Thử thay đổi query/partitioning/TTL trên workload tái hiện được.
6. Theo dõi sau thay đổi: p95/p99, timeout, tombstone scans, CPU/I/O và tính đúng dữ liệu.

**Không nên** xử lý bằng cách tăng `tombstone_failure_threshold` hoặc giảm `gc_grace_seconds` mà không giải quyết nguyên nhân, vì có thể che khuất lỗi hiệu năng hoặc làm giảm an toàn xóa.

## 17. Bài tập tình huống

Một hệ thống lưu truy cập thiết bị với schema:

```sql
CREATE TABLE accesses_by_device_day (
    device_id  uuid,
    event_day  date,
    seen_at    timestamp,
    access_id  uuid,
    ip         text,
    user_agent text,
    PRIMARY KEY ((device_id, event_day), seen_at, access_id)
);
```

Ứng dụng ghi 100.000 hàng/ngày cho một thiết bị. Một ngày sau, nó:

- Xóa `user_agent` của 30.000 hàng vì yêu cầu riêng tư.
- Ghi `ip = null` vào 10.000 hàng khác.
- Ghi một số hàng mới với `USING TTL 86400`.
- Đọc `LIMIT 20` để lấy 20 hàng gần nhất.

**Câu hỏi:**

1. Xóa `user_agent` ở 30.000 hàng có tạo tombstone không? Ở phạm vi nào?
2. Ghi `ip = null` khác gì bỏ hẳn `ip` khỏi câu `UPDATE`?
3. Sau 86.400 giây, các cell được ghi với TTL có cần một job gửi `DELETE` riêng không?
4. Vì sao `SELECT LIMIT 20` vẫn có thể quét nhiều tombstone?
5. Nếu chỉ còn `ip` còn sống ở một hàng, việc xóa `user_agent` có làm cả hàng biến mất không?
6. Xóa toàn partition ngày khác gì xóa `user_agent` của một số hàng?
7. Nếu một replica offline đúng thời điểm xóa và offline rất lâu, cần lo ngại điều gì?
8. Vì sao hạ `gc_grace_seconds` quá thấp có thể gây nguy cơ?
9. `TTL(user_agent)` sau khi giá trị đã bị xóa có cung cấp danh sách tombstone trên SSTable không?
10. Để giảm chi phí tombstone, hai thay đổi ở thiết kế API hoặc vòng đời dữ liệu nào đáng cân nhắc?

**Đáp án và giải thích:**

1. **Có thể tạo nhiều cell tombstones** cho `user_agent` tại các full primary keys được chỉ định, theo semantics xóa cell.
2. `ip = null` mang ý nghĩa **xóa giá trị**; bỏ cột khỏi UPDATE nghĩa là **không yêu cầu cập nhật cell đó**.
3. **Không.** TTL được lưu cùng giá trị; khi hết hạn, Cassandra xử lý giá trị như tombstone mà không cần request DELETE mới đúng thời điểm.
4. Vì trong dải clustering mới nhất có thể có nhiều cell/hàng đã xóa hoặc hết hạn, phải xử lý chúng để tìm đủ hàng hợp lệ.
5. **Không**, nếu còn cell sống khác hoặc thông tin liveness phù hợp; xóa một regular column không tương đương row deletion.
6. Partition deletion che **mọi hàng clustering và static data** của partition đó; xóa cột chỉ tác động đến cell được nêu trong các hàng tương ứng.
7. Replica có thể còn giá trị cũ, dẫn đến **nguy cơ zombie data** nếu tombstone được thu hồi trước khi trạng thái xóa được đồng bộ an toàn.
8. Vì thời gian bảo vệ khỏi replica bỏ lỡ xóa bị rút ngắn, trong khi repair/compaction có thể chưa đồng bộ đủ.
9. **Không.** Hàm TTL trên giá trị CQL không phải công cụ quét tombstone vật lý hoặc chứng minh vì sao cell không còn sống.
10. Ví dụ: **tránh gửi NULL cho field không được cập nhật**, và **thiết kế retention bằng TTL/bucket/compaction phù hợp** thay vì xóa từng cell ồ ạt khi không cần thiết.

### Bài tập thực hành CQL

Hãy tạo bảng thử nghiệm `accesses_by_device_day`, ghi hai hàng, rồi quan sát khác biệt giữa:

```sql
-- Xóa đúng một cột:
DELETE user_agent
FROM accesses_by_device_day
WHERE device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND seen_at = '2026-11-21T10:00:00Z'
  AND access_id = 8817a208-1858-4144-86e9-b24d9083e478;

-- Xóa cả một hàng clustering:
DELETE FROM accesses_by_device_day
WHERE device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND seen_at = '2026-11-21T10:00:00Z'
  AND access_id = 8817a208-1858-4144-86e9-b24d9083e478;
```

Đọc lại các cột với đầy đủ partition key, phân biệt **hàng còn sống nhưng cột rỗng** với **hàng đã bị xóa**. Sau đó thử TTL ngắn trên một bảng lab và quan sát giá trị hết hạn. Việc còn thấy dung lượng SSTable hoặc các cảnh báo liên quan tombstone sau khi hết TTL **không chứng minh dữ liệu còn sống**.

## 18. Ghi nhớ

- **`DELETE`** ghi dấu xóa để che dữ liệu cũ; phạm vi có thể là cell, static column, row, clustering range hoặc partition.
- **Ghi `NULL` vào cột** là thao tác xóa giá trị theo semantics CQL. **Không ghi cột** hoặc bind **UNSET** khác với NULL.
- **TTL hết hạn** làm cell không còn sống và được xử lý như tombstone; **không cần mutation DELETE mới** phát đúng thời điểm hết hạn.
- Tombstone có **write timestamp** để thắng các phiên bản dữ liệu cũ và ngăn dữ liệu chưa được đồng bộ xuất hiện lại.
- **Xóa logic** xảy ra trước; **thu hồi vật lý** phụ thuộc compaction, grace, SSTable overlap và an toàn của replica/repair.
- Hạ `gc_grace_seconds` tùy tiện hoặc bỏ qua repair có thể tạo nguy cơ **zombie data**.
- Tombstone làm tăng chi phí đọc khi query phải quét qua nhiều dữ liệu đã xóa; `LIMIT` và paging không giải quyết tận gốc.
- Hạn chế tombstone bằng thiết kế partition key/bucket, TTL phù hợp, không sinh NULL ngoài ý muốn và kiểm soát collection/update/delete.
- Đánh giá thực tế bằng `nodetool`, metrics, tracing, log warning và benchmark có TTL/xóa thay vì chỉ nhìn số hàng còn sống.
- Trong ứng dụng Java, tách rõ ý định **giữ nguyên cột**, **xóa cột** và **ghi giá trị có TTL**, đồng thời duy trì full primary key ổn định khi retry.

Nắm rõ cơ chế dấu xóa giúp bạn lý giải các tình huống tưởng như mâu thuẫn trong Apache Cassandra: dữ liệu đã xóa nhưng SSTable chưa nhỏ đi, truy vấn trả ít hàng mà vẫn chậm, hoặc replica cũ có thể làm dữ liệu xuất hiện lại khi vận hành sai grace/repair. Đây là nền tảng để đi sâu vào tombstone reclamation, compaction, replication và xử lý lỗi trong hệ thống Cassandra phân tán.

