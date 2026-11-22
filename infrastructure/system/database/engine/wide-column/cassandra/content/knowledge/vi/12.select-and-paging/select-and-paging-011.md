# Projection và giảm dữ liệu truyền về ứng dụng trong Apache Cassandra

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **projection** trong CQL `SELECT`: chỉ lấy những cột/biểu thức cần dùng, thay vì mặc định lấy toàn bộ hàng.
2. So sánh `SELECT *` với `SELECT` liệt kê tường minh các cột theo nhu cầu màn hình/API.
3. Phân biệt **số partition được đọc**, **số dòng kết quả**, **số cột được trả về** và **số byte truyền về client**.
4. Kết hợp projection với partition key, clustering range, `LIMIT` và phân trang; biết giữ đủ khóa để tạo cursor không mất dòng.
5. Hiểu sự khác biệt giữa giảm payload truyền qua mạng và giảm I/O nội bộ, CPU, tombstone scan hay chi phí replica.
6. Áp dụng prepared statement và typed getters của Java Driver 4.x; tránh đọc, chuyển đổi hoặc lưu các trường lớn không cần thiết.
7. Quyết định khi nào cần tách bảng phục vụ danh sách/chi tiết hoặc đưa payload lớn ra kho lưu trữ khác.

Bài thuộc chương **SELECT và phân trang** của mô-đun `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Với Apache Cassandra, một cơ sở dữ liệu wide-column phân tán, partition key quyết định vị trí dữ liệu, clustering columns quyết định thứ tự đọc trong một partition, và replication/consistency ảnh hưởng đường thực thi. Projection là một tối ưu **đầu ra** quan trọng cho ứng dụng Java, nhưng phải đi cùng thiết kế bảng theo truy vấn, phân trang và đo đạc thực tế.

## 1. Projection là gì?

**Projection** là lựa chọn **các cột hoặc biểu thức xuất hiện trong kết quả `SELECT`**.

Ví dụ cùng một tập sự kiện:

```sql
-- Lấy mọi cột mà bảng cung cấp.
SELECT *
FROM events_by_account_day
WHERE account_id = ?
  AND event_day = ?;

-- Chỉ lấy cột mà danh sách sự kiện cần hiển thị.
SELECT occurred_at, event_id, event_type, summary
FROM events_by_account_day
WHERE account_id = ?
  AND event_day = ?;
```

Điểm khác biệt:

| Thành phần | `SELECT *` | Projection tường minh |
| --- | --- | --- |
| Các cột kết quả | Toàn bộ cột thuộc schema | Chỉ những cột được liệt kê |
| Có thể trả trường `blob`/`text` lớn | Có | Không, nếu không chọn |
| Bị ảnh hưởng khi schema thêm cột | Có thể thay đổi hình dạng response | Hợp đồng cột ổn định hơn |
| Khả năng giảm network payload | Không tối ưu cho endpoint chỉ cần ít trường | Thường tốt hơn |
| Thay đổi partition được chọn | Không | **Không** — do `WHERE` quyết định |
| Thay đổi thứ tự các dòng | Không | **Không** — do clustering order/`ORDER BY` |
| Bảo đảm giảm toàn bộ I/O đĩa | Không | **Không thể bảo đảm** |

Với một API màn hình danh sách, người dùng thường chỉ cần thời gian, loại sự kiện và một câu tóm tắt. Nếu lấy cả payload chi tiết chỉ để Java bỏ đi, hệ thống có thể tốn băng thông, giải mã, cấp phát đối tượng và bộ nhớ không cần thiết.

> Quy tắc: **đưa dữ liệu cần hiển thị vào projection**, nhưng **đưa điều kiện xác định dữ liệu cần đọc vào `WHERE`**. Hai phần làm những công việc khác nhau.

## 2. Lab CQL: cùng một dòng có trường ngắn và trường lớn

Giả sử sản phẩm ghi lịch sử hoạt động cho từng tài khoản và ngày. Màn hình danh sách chỉ dùng một số trường, còn màn hình chi tiết mới cần thuộc tính mở rộng và nội dung thô.

### 2.1. Tạo keyspace và bảng

```sql
-- Lab một node; SimpleStrategy và RF=1 không phải cấu hình
-- khuyến nghị cho môi trường production đa node/datacenter.
CREATE KEYSPACE IF NOT EXISTS cassandra_projection_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

USE cassandra_projection_lab;

CREATE TABLE IF NOT EXISTS events_by_account_day (
    account_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    summary text,
    attributes map<text, text>,
    raw_payload blob,
    PRIMARY KEY ((account_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id DESC);
```

Ý nghĩa các cột:

| Cột | Loại | Vai trò trong truy vấn |
| --- | --- | --- |
| `account_id`, `event_day` | Composite partition key | Cả cặp định vị một partition và replica liên quan. |
| `occurred_at`, `event_id` | Clustering columns | Định danh/sắp xếp các sự kiện trong partition. |
| `event_type` | Cột thường | Tên loại sự kiện để hiển thị. |
| `summary` | Cột thường | Mô tả ngắn cho danh sách. |
| `attributes` | Cột collection | Map metadata mở rộng; không phải màn hình nào cũng cần. |
| `raw_payload` | Cột `blob` | Nội dung nhị phân thô; dễ trở nên lớn trong dữ liệu thật. |

**Chú ý mô hình:** Mọi hàng có cùng `(account_id, event_day)` nằm trong cùng một partition. Việc chỉ chọn `event_type` không cho phép truy cập trực tiếp “mọi sự kiện VIEW trên toàn hệ thống” nếu cột này chưa có đường truy vấn thích hợp.

### 2.2. Nạp dữ liệu nhỏ, có sự kiện trùng timestamp

```sql
-- Account A, ngày 20/11: bốn dòng trong cùng một partition.
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id,
     event_type, summary, attributes, raw_payload)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 09:00:00+0000',
    00000000-0000-4000-8000-000000000001,
    'LOGIN', 'Dang nhap',
    {'device': 'web', 'source': 'browser'},
    0x01020304
);

INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id,
     event_type, summary, attributes, raw_payload)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 10:00:00+0000',
    00000000-0000-4000-8000-000000000002,
    'VIEW', 'Xem chi tiet don',
    {'device': 'mobile', 'source': 'app'},
    0x05060708
);

-- Một dòng cùng timestamp 10:00 nhưng event_id khác.
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id,
     event_type, summary, attributes, raw_payload)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 10:00:00+0000',
    00000000-0000-4000-8000-000000000003,
    'CLICK', 'Mo trang thanh toan',
    {'device': 'mobile'},
    0x090a0b0c
);

-- Cố ý không ghi attributes và raw_payload ở dòng này.
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 11:00:00+0000',
    00000000-0000-4000-8000-000000000004,
    'PAY', 'Thanh toan thanh cong'
);

-- Account A, ngày 21/11: partition khác.
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21', '2026-11-21 08:00:00+0000',
    00000000-0000-4000-8000-000000000005,
    'LOGIN', 'Dang nhap ngay tiep theo'
);

-- Account B, ngày 20/11: partition thứ ba.
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    22222222-2222-4222-8222-222222222222,
    '2026-11-20', '2026-11-20 07:00:00+0000',
    00000000-0000-4000-8000-000000000006,
    'LOGIN', 'Dang nhap tai khoan B'
);
```

Tóm tắt:

| Partition key | Số dòng | Thứ tự trong partition |
| --- | ---: | --- |
| Account A, ngày 20/11 | 4 | 11:00/id4, 10:00/id3, 10:00/id2, 09:00/id1 |
| Account A, ngày 21/11 | 1 | 08:00/id5 |
| Account B, ngày 20/11 | 1 | 07:00/id6 |
| **Toàn bộ lab** | **6** | **3 partition** |

Các lệnh `INSERT` dùng full primary key cố định; chạy lại trên bảng đã tạo với đúng dữ liệu này là upsert, không tự thêm dòng trùng. Kết quả dự kiến giả định không có ghi/xóa khác. Payload trong lab chỉ dài bốn byte để tiện chạy CQL; trong thực tế, trường nhị phân có thể lớn hơn nhiều và cần chính sách giới hạn kích thước.

## 3. So sánh SELECT * và projection bằng kết quả cụ thể

### 3.1. SELECT * trả toàn bộ các cột được định nghĩa

```sql
SELECT *
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20';
```

CQL có thể trả các cột `account_id`, `event_day`, `occurred_at`, `event_id`, `event_type`, `summary`, `attributes` và `raw_payload` của **bốn dòng** trong partition A/ngày 20.

Đối với dòng `PAY`, `attributes` và `raw_payload` không được ghi; trong kết quả chúng có thể được biểu diễn như giá trị `null`. Dù là `null`, bản thân metadata và biểu diễn kết quả vẫn có overhead. Với các dòng khác, `SELECT *` mang cả trường nhị phân mà màn hình danh sách có thể không cần.

### 3.2. SELECT chỉ cột phục vụ màn hình danh sách

```sql
SELECT occurred_at, event_id, event_type, summary
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20';
```

Kết quả logic:

| `occurred_at` UTC | `event_id` (đuôi) | `event_type` | `summary` |
| --- | --- | --- | --- |
| 11:00 | `...0004` | `PAY` | Thanh toan thanh cong |
| 10:00 | `...0003` | `CLICK` | Mo trang thanh toan |
| 10:00 | `...0002` | `VIEW` | Xem chi tiet don |
| 09:00 | `...0001` | `LOGIN` | Dang nhap |

Vẫn là **một partition và bốn dòng**. Điều thay đổi là **cấu trúc mỗi dòng kết quả**:

- Không trả `account_id`, `event_day` nếu endpoint đã cố định hai giá trị đó trong request và không cần lặp lại ở mỗi dòng.
- Không trả `attributes` hoặc `raw_payload`.
- Giữ `occurred_at` và `event_id` vì chúng cần cho **thứ tự và cursor phân trang**.

Đây là một hợp đồng đầu ra phù hợp với API danh sách. Trong endpoint khác, nếu cần hỗ trợ trộn nhiều tenant/ngày hoặc truy vấn nhiều bucket, nên trả thêm cột khóa liên quan để biết mỗi dòng thuộc partition nào.

### 3.3. SELECT chỉ một cột không thay phạm vi đọc

```sql
SELECT event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20';
```

Truy vấn này vẫn có **bốn dòng kết quả**, chỉ mỗi dòng chứa một giá trị `event_type`. Cassandra không tự thực hiện `DISTINCT` chỉ vì bạn chọn một cột và cũng không tự trả **một dòng duy nhất**.

Muốn ít **dòng**, hãy dùng điều kiện khóa, clustering range và `LIMIT` phù hợp. Muốn ít **cột**, hãy dùng projection. Muốn ít **partition**, hãy xác định chính xác partition key trong `WHERE`.

## 4. Ba lớp giảm dữ liệu: partition, row và column

Với Cassandra, hãy tối ưu theo thứ tự tư duy:

| Lớp | Câu hỏi | Công cụ CQL | Phần được giảm chủ yếu |
| --- | --- | --- | --- |
| **Partition** | Đọc những partition nào? | Full partition key, tập `IN` hữu hạn | Phạm vi phân tán, replica/token fan-out |
| **Row** | Trong partition, lấy những dòng nào? | Clustering range, `LIMIT`, `PER PARTITION LIMIT` | Số dòng khớp/trả về |
| **Column** | Trên mỗi dòng, cần những trường nào? | Danh sách cột trong `SELECT` | Số giá trị và bytes trả về |

Ví dụ kết hợp cả ba:

```sql
SELECT occurred_at, event_id, event_type, summary
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at >= '2026-11-20 09:30:00+0000'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 2;
```

Ý nghĩa:

1. `account_id = ... AND event_day = ...` chọn **một partition**.
2. `occurred_at >= 09:30` giới hạn dòng ứng viên trong partition bằng clustering column.
3. `ORDER BY ... DESC` chọn chiều duyệt các dòng theo thứ tự clustering mà schema hỗ trợ.
4. `LIMIT 2` trả **tối đa hai dòng** đầu theo thứ tự đó.
5. Projection chỉ trả **bốn cột**, không trả `attributes` và `raw_payload`.

Với dữ liệu mẫu, hai dòng được chọn là **PAY 11:00** và **CLICK 10:00/id3**. Dòng **VIEW 10:00/id2** không xuất hiện vì `LIMIT 2`, mặc dù thời gian của nó vẫn nằm trong khoảng.

**Không nhầm:** `LIMIT 2` không bảo đảm storage engine chỉ đọc đúng hai cell vật lý. Khi có TTL/tombstone, các bước kiểm tra hoặc reconciliation có thể vẫn cần xử lý nhiều hơn số dòng trả về.

## 5. Ước lượng payload mạng: số dòng × kích thước cột

Để ra quyết định thiết kế, ước lượng độ lớn tương đối:

```text
Số byte kết quả thô (ước lượng)
  ≈ tổng qua mỗi dòng kết quả [
        kích thước các giá trị cột được chọn
        + overhead mã hóa / null / protocol
    ]

Tổng thời gian phản hồi còn phụ thuộc:
  + công việc đọc và lọc tại replica
  + phối hợp coordinator / consistency
  + mã hóa, nén, truyền mạng, giải mã
  + chuyển đổi DTO / serialize HTTP response
```

### 5.1. Ví dụ giả định có trường blob lớn

Giả sử trong dữ liệu thực tế, một trang danh sách có **500 dòng** và:

- Các trường danh sách cộng lại khoảng **150 byte/dòng** (không kể overhead).
- `raw_payload` trung bình **3.000 byte/dòng**.

So sánh phần giá trị dữ liệu được chọn:

| Cách lấy | Giá trị dữ liệu ước tính |
| --- | ---: |
| Projection danh sách: `500 × 150` | **75.000 byte** |
| Lấy thêm `raw_payload`: `500 × (150 + 3.000)` | **1.575.000 byte** |
| Chênh lệch do payload bị loại khỏi kết quả | **1.500.000 byte** |

Con số chỉ minh họa **byte của giá trị logic**, không phải số byte chính xác trên dây. Cassandra native protocol có overhead, có thể dùng compression; kích thước thực phụ thuộc kiểu giá trị, encoding, network, page size và cấu hình driver. Nhưng ví dụ cho thấy tại sao **bỏ một cột lớn** có thể hữu ích hơn cố gắng rút vài byte ở cột nhỏ.

### 5.2. Giá trị của giảm số cột ở tầng Java

Nếu API Java thực hiện:

```text
SELECT * -- lấy cả blob và map
     |
     v
Row trong Java driver
     |
     v
DTO chỉ giữ occurred_at, event_id, event_type, summary
     |
     v
HTTP JSON danh sách
```

thì việc bỏ `blob` **sau khi** nhận dữ liệu không xóa được chi phí truyền dữ liệu từ Cassandra về driver. Projection phải được đặt **trong CQL**:

```text
SELECT occurred_at, event_id, event_type, summary
     |
     v
Row chỉ chứa những cột được chọn
     |
     v
DTO / HTTP JSON danh sách
```

Không nhất thiết Cassandra đọc ít disk blocks hơn tương ứng từng byte được loại khỏi response; storage engine có thể vẫn phải đọc metadata, kiểm tra tombstones hoặc nội dung dữ liệu liên quan. **Network payload**, **CPU deserialize** và **memory footprint ở client** thường là các lợi ích dễ quan sát hơn và nên được đo.

### 5.3. SELECT * còn làm hợp đồng API dễ thay đổi

Ví dụ về sau schema được thêm:

```sql
ALTER TABLE events_by_account_day
ADD debug_trace text;
```

Nếu code dùng `SELECT *`, cột mới có thể được trả trong CQL result set, cho dù DTO/API không cần. Khi thay đổi schema hoặc thêm trường chứa dữ liệu nội bộ, một projection tường minh giúp giới hạn **dữ liệu không cần thiết** đi tới tầng ứng dụng. Tuy nhiên projection **không thay thế** phân quyền truy cập, kiểm soát nhạy cảm dữ liệu và giới hạn logging.

## 6. Chọn cột nào cho danh sách và chi tiết?

Một API có thể có hai đường đọc:

| Endpoint | Cột cần thiết | Lý do |
| --- | --- | --- |
| `GET /accounts/{id}/events?day=...` | `occurred_at`, `event_id`, `event_type`, `summary` | Vẽ danh sách và tạo cursor |
| `GET /accounts/{id}/events/{eventId}?day=...&at=...` | Các cột trên, `attributes`, `raw_payload` | Hiển thị/đọc nội dung chi tiết |

### 6.1. Truy vấn danh sách

```sql
SELECT occurred_at, event_id, event_type, summary
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 20;
```

Mặc định không lấy `raw_payload`, vì màn hình chỉ yêu cầu tóm tắt.

### 6.2. Truy vấn chi tiết theo full primary key

```sql
SELECT occurred_at, event_id, event_type, summary, attributes, raw_payload
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at = '2026-11-20 10:00:00+0000'
  AND event_id = 00000000-0000-4000-8000-000000000003;
```

Đây là **full primary-key lookup**, trả tối đa một dòng. Chi tiết được tải **khi người dùng mở bản ghi**, không phải cho mọi bản ghi của danh sách.

Nếu chỉ có `event_id` nhưng không biết `account_id`, `event_day` hoặc `occurred_at`, bảng hiện tại **không** hỗ trợ point lookup chỉ bằng `event_id`. Ứng dụng cần truyền đủ khóa từ danh sách/cursor hoặc duy trì đường tra cứu khác. Projection không thay đổi các quy tắc khóa.

### 6.3. Khi nào nên tách payload thành bảng hoặc kho khác?

Nếu `raw_payload` lớn hoặc thường xuyên không cần, một cách thiết kế là:

```sql
-- Bảng đọc dành cho danh sách: không chứa blob.
CREATE TABLE IF NOT EXISTS event_headers_by_account_day (
    account_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    summary text,
    PRIMARY KEY ((account_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id DESC);

-- Bảng dành cho chi tiết theo cùng full primary key.
CREATE TABLE IF NOT EXISTS event_details_by_account_day (
    account_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    attributes map<text, text>,
    raw_payload blob,
    PRIMARY KEY ((account_id, event_day), occurred_at, event_id)
);
```

Đây là **hai bảng mới chưa được nạp dữ liệu**; việc tạo bảng không tự sao chép các dòng mẫu. Ứng dụng/pipeline phải ghi, xóa, cập nhật TTL và backfill các bảng theo chính sách idempotent và nhất quán đã lựa chọn.

Đánh đổi:

- **Ưu:** Màn hình danh sách không phải mang theo cột payload trong bảng list, kể cả khi dùng code đọc nhầm toàn bộ cột của bảng list.
- **Nhược:** Tăng chi phí ghi/lưu trữ, khó giữ hai bảng đồng bộ hoàn hảo khi một bước ghi thất bại; cần retry/đối soát.
- Với payload rất lớn, cân nhắc lưu trong **object storage** và lưu metadata/tham chiếu trong Cassandra; tránh coi Cassandra là kho blob vô hạn. Phải quản lý quyền truy cập, URL/key, TTL và quá trình dọn dẹp đối tượng.

Không cần tách bảng chỉ vì trong schema có một cột lớn: **projection tường minh trên cùng bảng có thể đã đáp ứng** mục tiêu network của API. Quyết định tách bảng dựa vào đo đạc chi phí đọc, cập nhật và vận hành.

## 7. Projection và phân trang: giữ đủ khóa để tiếp tục

Projection chỉ chọn cột nào được trả về, nhưng **cursor keyset** cần dữ liệu từ những cột clustering xác định thứ tự. Nếu endpoint chọn quá ít cột, nó có thể không dựng được cursor an toàn.

### 7.1. Ví dụ timestamp trùng

Trong partition account A/ngày 20, thứ tự mặc định theo `(occurred_at DESC, event_id DESC)`:

```text
11:00 / event 0004 / PAY
10:00 / event 0003 / CLICK
10:00 / event 0002 / VIEW
09:00 / event 0001 / LOGIN
```

Trang đầu lấy hai dòng:

```sql
SELECT occurred_at, event_id, event_type, summary
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 2;
```

Kết quả là `PAY/0004` và `CLICK/0003`. Cursor của trang tiếp theo cần **cả hai cột** `occurred_at` và `event_id` từ dòng cuối:

```text
lastCursor = (2026-11-20T10:00:00Z, ...0003)
```

Trang kế:

```sql
SELECT occurred_at, event_id, event_type, summary
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND (occurred_at, event_id) < (
      '2026-11-20 10:00:00+0000',
      00000000-0000-4000-8000-000000000003
  )
ORDER BY occurred_at DESC, event_id DESC
LIMIT 2;
```

Kết quả tiếp là `VIEW/0002` rồi `LOGIN/0001`. Điều kiện tuple loại đúng khóa cuối trang trước nhưng vẫn giữ sự kiện còn lại có cùng timestamp.

Nếu projection chỉ có `event_type` và `summary`:

```sql
-- Có thể hiển thị được nhưng không đủ thông tin
-- để xây cursor theo clustering key ở tầng ứng dụng.
SELECT event_type, summary
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
LIMIT 2;
```

thì phía Java thiếu `occurred_at` và `event_id` để xác định vị trí cuối trang. **Đừng hy sinh khóa cursor chỉ để giảm vài byte**, trừ khi dùng cơ chế phân trang khác đã có cách lưu trạng thái an toàn.

### 7.2. Driver paging state khác keyset cursor

Java Driver hỗ trợ `setPageSize(n)` và paging state để tiếp tục fetch **cùng một truy vấn CQL**. Trong cơ chế đó, ứng dụng không nhất thiết phải trả toàn bộ khóa clustering ra response HTTP để lấy trang tiếp; nhưng:

- Paging state cần gắn với query và bind values tương ứng, không dùng cho một projection/`WHERE` mới tùy tiện.
- Paging state không phải thứ có thể tự dựng hoặc sửa, và có thể không được dùng lại giữa các thay đổi cấu trúc/truy vấn không tương thích.
- State không tự tạo snapshot cố định giữa những lần đọc khi có ghi/xóa/TTL.
- Nếu gửi paging state tới client, phải ràng buộc quyền truy cập và bảo vệ tính toàn vẹn, tránh lộ hoặc trộn token giữa tenant.

Đừng coi **page size** là giới hạn tổng kết quả. Ví dụ `setPageSize(2)` có thể fetch hai dòng trong một page, rồi fetch các page kế tiếp cho tới khi hết query.

### 7.3. Nhiều partition và danh sách IN

```sql
SELECT account_id, event_day, occurred_at, event_id, event_type, summary
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day IN ('2026-11-20', '2026-11-21');
```

Vì `event_day` là thành phần cuối composite partition key, truy vấn chọn **hai partition ứng viên**, tổng cộng năm dòng theo lab. Ở đây projection thêm `event_day` vì ứng dụng cần phân biệt dòng thuộc ngày nào. Nhưng:

- Không có thứ tự thời gian **toàn cục** chỉ từ clustering order của từng partition.
- Giảm số cột không giảm số partition đã nêu trong `IN`.
- Nếu cần trộn các sự kiện theo thời gian trên nhiều ngày, ứng dụng phải có chiến lược merge/cursor hoặc bảng đọc được thiết kế cho cách truy vấn đó.

## 8. Projection có giảm I/O, CPU và tombstone scan không?

Câu trả lời phù hợp là: **có thể giảm một số chi phí, nhưng không có bảo đảm tuyến tính hay áp dụng cho mọi trường hợp**.

### 8.1. Nơi projection thường mang lại lợi ích

| Nguồn chi phí | Lợi ích có thể có |
| --- | --- |
| Bytes Cassandra gửi về Java | Thường giảm khi bỏ trường dài hoặc `blob`. |
| CPU mã hóa/giải mã CQL protocol | Có thể giảm khi cần xử lý ít giá trị hơn. |
| Bộ nhớ ở driver/DTO/HTTP layer | Có thể giảm vì ít dữ liệu phải giữ/chuyển đổi. |
| Mạng giữa các thành phần ứng dụng | Có thể giảm nếu response API cũng không chứa trường thừa. |
| Độ ổn định khi thêm cột schema | Projection tường minh giữ hợp đồng query rõ ràng. |

### 8.2. Nơi projection không thể thay thế cách tối ưu khác

| Nguồn chi phí | Vì sao chỉ đổi `SELECT *` không đủ |
| --- | --- |
| Nhiều partition trong `WHERE` | Projection không thay hash token hay fan-out sang replica. |
| Tìm dòng theo regular column | Không tạo index, không sửa được `ALLOW FILTERING` quét rộng. |
| Đọc một partition cực lớn | Phải dùng clustering range, paging, bucket hoặc thiết kế khác. |
| Tombstone/TTL và reconciliation | Storage engine vẫn phải xác định dòng nào còn hiệu lực. |
| Compaction/repair và SSTable read amplification | Việc có ít cột trả về không làm các hoạt động nền biến mất. |
| Consistency cao hoặc replica chậm | Cần xem topology, replica, timeout và tải. |
| Truy vấn `COUNT(*)` toàn bảng | Aggregate vẫn phải xét tập dòng liên quan, dù chỉ trả một số. |

Không khẳng định “bỏ 80% cột sẽ làm truy vấn nhanh gấp năm lần”. Với bảng có dữ liệu rất nhỏ hoặc tải chủ yếu do tìm partition/tombstones, lợi ích có thể nhỏ. Với cột payload lớn và mạng là nút thắt, lợi ích có thể rất rõ. Cần **đo**, không suy từ số cột.

### 8.3. SELECT JSON không mặc nhiên làm kết quả nhỏ hơn

CQL có khả năng trả dữ liệu dưới dạng JSON:

```sql
SELECT JSON occurred_at, event_id, event_type, summary
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20';
```

`SELECT JSON` thay đổi **cách trình bày/serialization** kết quả: các cột được mã hóa vào chuỗi JSON. Nó không tự chọn ít dòng hay ít cột, và JSON có thể tăng overhead vì key names và escaping. Nếu API vốn dùng Java DTO để tạo JSON HTTP, cần đo xem đẩy serialization JSON xuống Cassandra có lợi không; không mặc định đây là cách nén dữ liệu.

Tương tự, `AS` để đặt alias:

```sql
SELECT occurred_at AS event_time,
       event_id,
       event_type,
       summary
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20';
```

giúp đặt tên kết quả dễ đọc nhưng **không tự giảm số byte giá trị**. Các biểu thức phức tạp, hàm hoặc user-defined function trong projection có thể thêm CPU; chỉ dùng khi phục vụ nhu cầu thực.

## 9. Java Driver: prepared statement và DTO mỏng

Ví dụ dùng **Apache Cassandra Java Driver 4.x** với Java 17. Giả định đã có `CqlSession session` kết nối keyspace `cassandra_projection_lab`.

### 9.1. Đường đọc dành cho danh sách

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

// Giả định đã có CqlSession session kết nối cassandra_projection_lab.
UUID accountId = UUID.fromString(
    "11111111-1111-4111-8111-111111111111"
);
LocalDate day = LocalDate.parse("2026-11-20");

PreparedStatement listQuery = session.prepare("""
    SELECT occurred_at, event_id, event_type, summary
    FROM events_by_account_day
    WHERE account_id = ?
      AND event_day = ?
    ORDER BY occurred_at DESC, event_id DESC
    LIMIT ?
    """);

int requestedLimit = 20;
int safeLimit = Math.max(1, Math.min(requestedLimit, 100));
BoundStatement bound = listQuery.bind(accountId, day, safeLimit)
    .setPageSize(50);

ResultSet result = session.execute(bound);
for (Row row : result) {
    Instant time = row.getInstant("occurred_at");
    UUID eventId = row.getUuid("event_id");
    String type = row.getString("event_type");
    String summary = row.getString("summary");
    System.out.printf("%s %s %s %s%n", time, eventId, type, summary);
}
```

Điểm cần chú ý:

- `SELECT` chỉ có **bốn cột**; driver không nhận `raw_payload` dù bảng có cột ấy.
- `LIMIT ?` dùng bind marker, không ghép chuỗi input người dùng vào CQL.
- `setPageSize(50)` thiết lập **kích thước fetch**, không thay `LIMIT 20`. Với bốn dòng dữ liệu mẫu, query chỉ trả bốn dòng.
- `getInstant` phù hợp CQL `timestamp`, `getUuid` phù hợp `uuid`, `getString` phù hợp `text`.
- Ví dụ duyệt `ResultSet` để minh họa; trong API thật, nên chuyển thành DTO và chỉ trả những trường đã được xác định bởi hợp đồng của endpoint.

Không cần `SELECT *` rồi kiểm tra `row.getString("summary")`: getter chỉ chọn dữ liệu **sau khi driver đã nhận result set**.

### 9.2. Đường đọc chi tiết

```java
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.util.UUID;

PreparedStatement detailQuery = session.prepare("""
    SELECT occurred_at, event_id, event_type, summary,
           attributes, raw_payload
    FROM events_by_account_day
    WHERE account_id = ?
      AND event_day = ?
      AND occurred_at = ?
      AND event_id = ?
    """);

BoundStatement detailBound = detailQuery.bind(
    accountId,
    day,
    Instant.parse("2026-11-20T10:00:00Z"),
    UUID.fromString("00000000-0000-4000-8000-000000000003")
);

Row detail = session.execute(detailBound).one();
if (detail != null) {
    String detailType = detail.getString("event_type");
    String detailSummary = detail.getString("summary");
    // Chỉ khi endpoint thật sự cần: đọc attributes/raw_payload
    // theo đúng kiểu CQL và kiểm soát dung lượng trước khi sử dụng.
    System.out.printf("%s: %s%n", detailType, detailSummary);
}
```

Nếu `raw_payload` có thể chứa dữ liệu bí mật, việc nó nằm trong projection của **endpoint chi tiết** cũng không đồng nghĩa người gọi được phép nhìn thấy. Authorization theo tài khoản/sự kiện, kiểm soát logging và chính sách bảo vệ dữ liệu vẫn là bắt buộc.

### 9.3. Phân trang bằng keyset cursor

Với một partition và schema có clustering order `DESC, DESC`, có thể chuẩn bị query tiếp theo:

```java
PreparedStatement nextPage = session.prepare("""
    SELECT occurred_at, event_id, event_type, summary
    FROM events_by_account_day
    WHERE account_id = ?
      AND event_day = ?
      AND (occurred_at, event_id) < (?, ?)
    ORDER BY occurred_at DESC, event_id DESC
    LIMIT ?
    """);

BoundStatement nextBound = nextPage.bind(
    accountId,
    day,
    Instant.parse("2026-11-20T10:00:00Z"),
    UUID.fromString("00000000-0000-4000-8000-000000000003"),
    2
);
```

Câu lệnh giữ `occurred_at` và `event_id` trong projection **vì chính hai cột ấy tạo cursor**. Trong production, cursor nên được xác nhận thuộc đúng account/day, có thể ký số hoặc mã hóa để tránh người dùng chỉnh sửa, và chịu các giới hạn truy cập tương ứng.

### 9.4. Đo payload và latency trong ứng dụng

Đừng dựa hoàn toàn vào benchmark một request. Khi so sánh projection:

1. Chạy **cùng partition set, cùng `WHERE`, cùng `LIMIT` và cùng consistency** cho hai phiên bản query.
2. Dùng dữ liệu có phân phối gần production: có trường `blob` thực tế, partition lớn/nhỏ, nhiều request đồng thời.
3. Theo dõi bytes response hoặc network throughput nếu hệ thống đo được; đo cả thời gian giải mã và serialize JSON.
4. Quan sát p50/p95/p99 latency, timeouts, GC/memory và throughput khi tăng concurrency.
5. Kiểm tra sự khác biệt do cache nóng/lạnh, compaction, repair, tombstone và retry.
6. Xác nhận API không vô tình bỏ những trường cần cho cursor, auditing hay chức năng khác.

Các metrics có sẵn phụ thuộc Java driver, hệ thống giám sát và phiên bản Cassandra. Không khẳng định một con số bytes chính xác chỉ từ `row.getColumnDefinitions().size()`: số cột chỉ là **số lượng trường**, không thể thay thế đo kích thước serialized values.

## 10. Projection và tính nhất quán đọc ghi

Projection không thay đổi semantics của consistency level. Ví dụ một câu `SELECT occurred_at, event_id, event_type` chạy ở `LOCAL_ONE` và cùng câu đó chạy ở `LOCAL_QUORUM` (trong cluster cấu hình replication phù hợp) có thể khác nhau về replica cần phản hồi và dữ liệu quan sát khi có ghi chưa hội tụ.

Những điều cần hiểu:

- **Replication factor** không làm output bị nhân số lần replica. Kết quả là những dòng logic của bảng, không phải bản sao từ mỗi replica.
- **Consistency level** chọn các bảo đảm đọc và mức phải phản hồi; projection không sửa được việc replica chậm hay mất kết nối.
- **TTL và tombstone:** không chọn `raw_payload` có thể giảm output nhưng không đồng nghĩa mọi chi phí kiểm tra dữ liệu hết hạn/xóa sẽ biến mất.
- **Compaction và repair:** ảnh hưởng phân mảnh dữ liệu, reconciliation và độ trễ đọc; không được thay thế chỉ bằng cắt cột ở `SELECT`.
- **Paging state:** trả dữ liệu theo từng trang không tạo snapshot bất biến, dù chọn ít cột hay nhiều cột.

Nếu một endpoint chậm vì đọc rộng, ưu tiên xác minh đường truy vấn theo khóa, độ lớn partition, tombstones và replica health **trước khi** gán mọi chậm trễ cho payload mạng. Nếu endpoint chậm do blob/map lớn, projection là điểm cải thiện có chi phí triển khai thấp và rõ ràng.

## 11. Các lỗi thường gặp

| Cách hiểu hoặc thực hiện | Vấn đề | Cách sửa |
| --- | --- | --- |
| `SELECT *` rồi bỏ cột trong Java DTO | Dữ liệu đã được gửi từ Cassandra đến driver. | Projection ngay trong CQL. |
| “Chỉ lấy một cột nghĩa là chỉ đọc một partition.” | Partition được xác định bởi `WHERE`, không bởi projection. | Dùng full partition key phù hợp. |
| “Chọn ít cột thì `ALLOW FILTERING` hết chậm.” | Vẫn có thể cần quét nhiều dòng/partition để tìm kết quả. | Thiết kế bảng/index hoặc giới hạn clustering range. |
| “`LIMIT 20` bảo đảm chỉ đọc 20 cell.” | Tombstones, TTL, filtering và reconciliation có thể cần xem nhiều hơn. | Phân biệt output với read work. |
| “`setPageSize(20)` tương đương `LIMIT 20`.” | Page size chỉ chia quá trình fetch. | Dùng `LIMIT` cho trần tổng; page size cho tải trang. |
| “Bỏ hết cột khóa khỏi `SELECT` vẫn phân trang keyset được.” | Không còn giá trị khóa cuối trang để tạo cursor. | Giữ các clustering columns tạo thứ tự xác định. |
| “`SELECT JSON` chắc chắn nhỏ hơn `SELECT` thường.” | JSON có overhead và serialization cost. | Đo trên dữ liệu và protocol thực tế. |
| “`SELECT event_type` trả các loại duy nhất.” | Nó trả một giá trị **cho mỗi dòng** được đọc. | Thiết kế truy vấn `DISTINCT`/nhóm hợp lệ hoặc bảng khác. |
| “Thêm cột mới không ảnh hưởng code dùng `SELECT *`.” | Result set có thể thay đổi và tăng payload. | Liệt kê cột tường minh theo hợp đồng API. |
| “Projection làm COUNT(*) toàn bảng O(1).” | Aggregate vẫn phải đánh giá tập dòng cần đếm. | Giới hạn `WHERE` hoặc dùng summary. |
| “Chỉ cần event_id để lấy chi tiết.” | Full key của schema còn account, ngày, timestamp. | Truyền đủ khóa hoặc thiết kế bảng tra cứu event ID riêng. |
| “Không trả blob qua API nên blob không ra khỏi Cassandra.” | Nếu CQL dùng `SELECT *`, blob vẫn được gửi đến driver. | Chỉ chọn blob trong query chi tiết. |

## 12. Bài tập thực hành và đáp án

### Bài 1. Viết projection cho màn hình danh sách

**Đề:** Account A ngày 20/11 cần hiển thị thời gian, mã sự kiện, loại và tóm tắt, không cần blob/map. Viết query với tối đa ba sự kiện mới nhất.

**Đáp án:**

```sql
SELECT occurred_at, event_id, event_type, summary
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 3;
```

Kết quả là `PAY/0004`, `CLICK/0003` và `VIEW/0002`. Truy vấn chỉ dùng **một partition**, trả **ba dòng** và **bốn cột mỗi dòng**.

### Bài 2. Projection không làm giảm số partition

**Đề:** Cùng account A, hỏi hai ngày `2026-11-20` và `2026-11-21`, chỉ lấy `event_type`. Có bao nhiêu partition ứng viên và bao nhiêu dòng trên lab?

**Đáp án:**

```sql
SELECT event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day IN ('2026-11-20', '2026-11-21');
```

Có **hai partition ứng viên**, kết quả tổng **năm dòng** trên dữ liệu mẫu. Chọn một cột không biến truy vấn thành một partition và không loại trùng loại sự kiện.

### Bài 3. Tại sao cần giữ event_id cho cursor?

**Đề:** Trang đầu lấy hai dòng mới nhất của account A ngày 20, kết thúc ở `10:00/id3`. Có thể chỉ lưu `occurred_at = 10:00` rồi dùng `occurred_at < 10:00` để lấy trang tiếp không?

**Đáp án:** Không. Nó bỏ qua `VIEW/0002` cũng xảy ra lúc `10:00`. Dùng ranh giới tuple `(occurred_at, event_id) < (10:00, id3)` trong hướng duyệt giảm dần và giữ cả hai cột trong projection.

### Bài 4. Ước lượng payload

**Đề:** Endpoint trả 500 dòng; trường danh sách khoảng 150 byte/dòng, payload thêm 3.000 byte/dòng. Bỏ payload tiết kiệm khoảng bao nhiêu byte giá trị logic?

**Đáp án:** `500 × 3.000 = 1.500.000 byte`. Đây là ước lượng giá trị dữ liệu trước overhead giao thức/nén, không phải đo thực tế trên dây. Cần benchmark để biết thay đổi p95/p99 và throughput.

### Bài 5. SELECT JSON có luôn tối ưu hơn không?

**Đề:** API Java đã chuyển các cột ngắn sang JSON HTTP. Có nên tự động thay mọi câu CQL bằng `SELECT JSON` để tối ưu băng thông?

**Đáp án:** Không. `SELECT JSON` đổi cách biểu diễn dữ liệu, thêm key names và escaping, có thể làm kết quả lớn hơn hoặc thêm CPU. Projection tường minh các trường cần dùng và đo payload thực tế thường là bước ưu tiên; chỉ dùng JSON trong CQL khi có nhu cầu và benchmark chứng minh phù hợp.

### Bài 6. Đọc chi tiết khi người dùng mở một dòng

**Đề:** Người dùng chọn `CLICK/0003` lúc 10:00 ngày 20 của account A. Query nào chỉ lấy chi tiết đúng một sự kiện?

**Đáp án:**

```sql
SELECT occurred_at, event_id, event_type, summary, attributes, raw_payload
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at = '2026-11-20 10:00:00+0000'
  AND event_id = 00000000-0000-4000-8000-000000000003;
```

Đã cung cấp **full primary key**, nên trả tối đa một dòng; projection chi tiết được phép gồm map/blob vì endpoint thật sự cần chúng. Không dùng câu `SELECT *` cho toàn bộ danh sách chỉ vì một dòng có thể được mở chi tiết.

### Bài 7. Trường hợp giảm cột chưa đủ

**Đề:** Query có `WHERE event_type = 'VIEW' ALLOW FILTERING` nhưng thiếu partition key. API chuyển từ `SELECT *` sang `SELECT event_type` và thấy network giảm; có thể kết luận hết rủi ro quét rộng?

**Đáp án:** Không. Projection có thể giảm số byte trả về nhưng điều kiện lọc trên regular column vẫn có thể yêu cầu quét nhiều partition/dòng. Cần thiết kế đường truy cập theo khóa hoặc index phù hợp, đo fan-out, tombstones và latency.

## 13. Checklist projection cho API Cassandra

1. **Mục tiêu endpoint:** client cần những trường nào? Có thể tách danh sách và chi tiết không?
2. **Partition:** `WHERE` đã chỉ rõ full partition key hoặc tập partition hữu hạn chưa? Có giới hạn fan-out?
3. **Row:** Có clustering range, `ORDER BY` hợp lệ, `LIMIT` và chính sách paging rõ ràng chưa?
4. **Column:** Query đã dùng projection tường minh, tránh `SELECT *` ở đường đọc thường xuyên chưa?
5. **Cursor:** Các trường cần xác định khóa cuối trang, nhất là timestamp và ID phân biệt, có trong kết quả khi dùng keyset không?
6. **Payload lớn:** `blob`/collection/map có được tải đúng lúc cần? Có cần tách bảng hoặc tham chiếu object storage không?
7. **Kết quả thực:** Đã đo bytes truyền, deserialize, heap/GC, p95/p99 latency và throughput chưa? Có so sánh cùng `WHERE`, `LIMIT`, consistency và tập dữ liệu?
8. **Phân tán:** Có phân biệt lợi ích payload với chi phí tombstone/TTL, compaction, repair, replication và consistency không?
9. **Java:** Prepared statement và typed getters đã đúng? Có tránh fetch kết quả lớn vào collection không giới hạn không?
10. **Bảo mật và thay đổi schema:** Có giới hạn dữ liệu nhạy cảm ở projection, logging, authorization và hợp đồng API không?

**Ghi nhớ:** Projection giảm **số cột và giá trị trả về**; `WHERE` giảm **phạm vi partition/dòng phải tìm**; `LIMIT` và paging kiểm soát **số dòng/trang kết quả**. Cả ba phải được thiết kế cùng nhau. Trong Cassandra, một câu `SELECT` tốt không chỉ trả đúng dữ liệu, mà còn **không truyền những dữ liệu ứng dụng không cần**, giữ được khóa phân trang và tránh truy vấn phân tán khó dự đoán.

## Tài liệu tham khảo

- [Apache Cassandra Documentation — CQL Data Manipulation: SELECT, WHERE, ORDER BY, LIMIT](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html)
- [Apache Cassandra Documentation — CQL Data Definition: PRIMARY KEY và CLUSTERING ORDER](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html)
- [Apache Cassandra Documentation — Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html)
- [Apache Cassandra Java Driver 4.x — Prepared Statements](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/statements/prepared/index.html)
- [Apache Cassandra Java Driver 4.x — Paging](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/paging/index.html)
