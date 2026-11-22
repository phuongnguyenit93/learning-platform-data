# Truy vấn theo khóa đầy đủ hoặc theo khoảng trong phân vùng

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt truy vấn theo **toàn bộ primary key**, theo **toàn bộ partition key**, và theo **một khoảng clustering key bên trong partition**.
2. Viết CQL lấy đúng một dòng, lấy các dòng cùng một thời điểm, hoặc lấy một dải thời gian có điểm bắt đầu và kết thúc rõ ràng.
3. Chọn điều kiện `=`, `>`, `>=`, `<`, `<=` và so sánh tuple trên nhiều clustering columns.
4. Kết hợp thứ tự clustering, `ORDER BY` và `LIMIT` để phục vụ trang lịch sử sự kiện mà không nhầm giữa giới hạn kết quả và giới hạn phạm vi đọc.
5. Dùng khóa cuối cùng của trang làm con trỏ để đi tiếp, phân biệt cách này với paging state của Cassandra Java driver.
6. Nhận diện truy vấn cần quét nhiều partition, bị từ chối do thiếu thành phần khóa, hoặc có rủi ro do partition quá lớn.

Bài thuộc chương **SELECT và phân trang** của mô-đun `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Apache Cassandra phân tán dữ liệu theo **partition key**, lưu các dòng trong mỗi partition theo **clustering columns**, và phục vụ truy vấn hiệu quả nhất khi mô hình bảng được thiết kế theo nhu cầu đọc. Những kiến thức này là nền tảng trước khi đưa CQL vào ứng dụng Java, chọn mức nhất quán đọc/ghi, và đánh giá độ trễ trên cluster nhiều replica.

## 1. Ba cấp độ định vị dữ liệu

Hãy bắt đầu từ một bảng có khóa:

```sql
PRIMARY KEY ((account_id, event_day), occurred_at, event_id)
```

| Phần khóa | Ý nghĩa | Vai trò khi truy vấn |
| --- | --- | --- |
| `account_id`, `event_day` | **Composite partition key** | Cùng xác định partition và các replica chịu trách nhiệm. |
| `occurred_at` | Clustering column thứ nhất | Sắp xếp và giới hạn các dòng theo thời gian trong partition. |
| `event_id` | Clustering column thứ hai | Phân biệt các sự kiện trùng thời gian; tạo vị trí xác định trong thứ tự clustering. |

Ba kiểu truy vấn:

| Truy vấn | Cột cần biết | Số dòng có thể trả về |
| --- | --- | --- |
| **Khóa đầy đủ** | `account_id`, `event_day`, `occurred_at`, `event_id` | Tối đa **một dòng**. |
| **Partition đầy đủ** | `account_id`, `event_day` | Có thể **nhiều dòng** trong cùng partition. |
| **Khoảng trong partition** | Partition key đầy đủ + ràng buộc trên clustering key | Một **lát cắt** gồm các dòng khớp khoảng hoặc bộ khóa. |

Sơ đồ với một partition:

```text
                  account_id=A, event_day=2026-11-20
                              (partition)
                                  |
        +-------------------------+-------------------------+
        |                         |                         |
   08:00 / id-1              09:30 / id-2              09:30 / id-3
        |                         |                         |
    event row                  event row                 event row
                                  |
                             11:00 / id-4
                                  |
                              event row

Khóa đầy đủ            ->  09:30 / id-2
Partition đầy đủ       ->  cả 4 dòng
Khoảng [09:00, 11:00)  ->  09:30 / id-2 và 09:30 / id-3
```

**Lưu ý:** Phạm vi đọc chủ yếu do điều kiện trong `WHERE` quyết định. `SELECT` chỉ định các cột sẽ trả về. Câu `SELECT event_type` không tự tìm được một sự kiện nếu thiếu các điều kiện khóa cần thiết.

## 2. Dựng bảng và dữ liệu mẫu trong cqlsh

Giả sử ứng dụng quản lý hoạt động tài khoản cần hai thao tác: lấy chi tiết **một sự kiện** khi đã biết mã sự kiện, và hiển thị **nhật ký theo ngày với khoảng thời gian**.

```sql
-- Chỉ dùng SimpleStrategy với một replica cho lab một node.
CREATE KEYSPACE IF NOT EXISTS cassandra_range_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

USE cassandra_range_lab;

CREATE TABLE IF NOT EXISTS events_by_account_day (
    account_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((account_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at ASC, event_id ASC);
```

Chọn thứ tự `ASC` ở cả hai clustering columns để thấy rõ nguyên tắc: sự kiện cũ trước, và các sự kiện cùng thời điểm được sắp theo `event_id`.

```sql
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, payload)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 08:00:00+0000',
    00000000-0000-4000-8000-000000000001,
    'LOGIN', 'Dang nhap'
);

INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, payload)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 09:30:00+0000',
    00000000-0000-4000-8000-000000000002,
    'VIEW', 'Xem don hang'
);

INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, payload)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 09:30:00+0000',
    00000000-0000-4000-8000-000000000003,
    'CLICK', 'Bam chi tiet'
);

INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, payload)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 11:00:00+0000',
    00000000-0000-4000-8000-000000000004,
    'LOGOUT', 'Dang xuat'
);

-- Sự kiện của ngày khác nằm trong partition khác.
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, payload)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21', '2026-11-21 07:30:00+0000',
    00000000-0000-4000-8000-000000000005,
    'LOGIN', 'Dang nhap ngay sau'
);
```

Dữ liệu mẫu có bốn dòng ở partition `(1111..., 2026-11-20)` và một dòng ở partition `(1111..., 2026-11-21)`. Các khóa dùng giá trị cố định để chạy lại ví dụ vẫn cho kết quả như nhau: CQL `INSERT` trên cùng primary key là thao tác upsert.

**Quy ước thời gian:** Chuỗi timestamp ghi rõ offset `+0000`, tức UTC. Kiểu `timestamp` lưu một thời điểm, không lưu riêng múi giờ ban đầu. Trong Java, nên dùng `Instant` cho giá trị này và xác định `event_day` theo quy tắc ngày nghiệp vụ; đừng suy ngầm rằng ngày UTC luôn là ngày địa phương của người dùng.

## 3. Truy vấn theo toàn bộ primary key: lấy một dòng

Để xem chi tiết sự kiện `VIEW` đã biết vị trí, cung cấp toàn bộ partition key và mọi clustering column:

```sql
SELECT account_id, event_day, occurred_at, event_id, event_type, payload
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at = '2026-11-20 09:30:00+0000'
  AND event_id = 00000000-0000-4000-8000-000000000002;
```

**Kết quả dự kiến:** đúng một dòng có `event_type = 'VIEW'` và `payload = 'Xem don hang'`.

Quá trình đọc, ở mức khái niệm:

1. Coordinator tính token cho **cặp** `(account_id, event_day)` và xác định những replica liên quan.
2. Bên trong partition, khóa clustering `(occurred_at, event_id)` cho phép định vị chính xác một dòng.
3. Những cột được nêu trong `SELECT` xác định dữ liệu cần trả về.

Không phải cứ biết `event_id` là đủ để tìm sự kiện:

```sql
-- Không có đường truy vấn trực tiếp với schema hiện tại:
SELECT event_type, payload
FROM events_by_account_day
WHERE event_id = 00000000-0000-4000-8000-000000000002;
```

Trong bảng này, `event_id` là clustering column thứ **hai**, không phải partition key và cũng không phải chỉ mục tra cứu toàn cluster. Nếu sản phẩm bắt buộc mở chi tiết chỉ từ một `event_id`, hãy lưu kèm đầy đủ khóa khi tạo liên kết hoặc thiết kế thêm bảng tra cứu theo ID.

### Khi chỉ biết một phần clustering key

Vì dữ liệu mẫu có hai sự kiện tại `09:30`, điều kiện sau trả về **hai dòng**:

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at = '2026-11-20 09:30:00+0000';
```

Điều kiện bằng trên `occurred_at` chọn một **nhóm dòng có cùng tiền tố clustering key**; nó chỉ thành point lookup một dòng nếu cả `event_id` cũng được chỉ định. Đây là lý do cần thêm một cột phân biệt khi nhiều sự kiện có cùng timestamp.

## 4. Truy vấn toàn bộ partition: lấy một tập dòng

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20';
```

Truy vấn chỉ có partition key đầy đủ sẽ trả về **bốn dòng**, theo thứ tự clustering `(occurred_at ASC, event_id ASC)` đã định nghĩa. Không cần điều kiện clustering nếu mong muốn là toàn bộ nhật ký của ngày.

| `occurred_at` (UTC) | `event_id` (đuôi) | `event_type` |
| --- | --- | --- |
| 08:00 | `...0001` | `LOGIN` |
| 09:30 | `...0002` | `VIEW` |
| 09:30 | `...0003` | `CLICK` |
| 11:00 | `...0004` | `LOGOUT` |

Về mặt hiệu năng, biết partition key đầy đủ giúp tránh phải tìm trên mọi partition. Tuy nhiên, **một partition vẫn có thể chứa rất nhiều dòng hoặc nhiều tombstone**. Một truy vấn toàn partition lớn vẫn có thể tốn RAM, I/O và thời gian đọc. Vì vậy cần chọn bucket `event_day` hoặc bucket khác có kích thước phù hợp với lưu lượng thực tế.

Nếu chỉ viết `WHERE account_id = ...` mà bỏ `event_day`, CQL không thể xác định chính xác một partition theo composite partition key; truy vấn thông thường bị từ chối hoặc đòi hỏi cách quét/lọc không nên dùng cho API thời gian thực.

## 5. Truy vấn theo khoảng clustering column trong một partition

Đây là mẫu đọc thường gặp cho màn hình timeline, log hoặc dữ liệu time series.

### 5.1. Khoảng nửa mở `[start, end)`

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at >= '2026-11-20 09:00:00+0000'
  AND occurred_at <  '2026-11-20 11:00:00+0000';
```

Kết quả đúng **hai sự kiện `VIEW` và `CLICK` lúc 09:30**. Dòng `LOGOUT` lúc 11:00 không được lấy vì đầu trên dùng `<`.

Ký hiệu khoảng:

```text
08:00             09:00          09:30                   11:00
  |                  [          VIEW, CLICK                 )
  |                  |             |                        |
 LOGIN           bao gồm      hai dòng trùng giờ     loại trừ LOGOUT
```

Đây là quy ước hữu ích khi chia một ngày thành các cửa sổ không chồng lấn:

- Cửa sổ một: `[09:00, 11:00)`.
- Cửa sổ hai: `[11:00, 13:00)`.

Sự kiện đúng `11:00` chỉ thuộc cửa sổ hai. Nếu dùng `<=` cho cả cửa sổ một thì dòng biên có thể bị đếm hai lần.

### 5.2. Các loại ranh giới

| CQL trên `occurred_at` | Ý nghĩa | Tại mốc đúng bằng |
| --- | --- | --- |
| `>= T` | Lấy từ T trở đi | Bao gồm T. |
| `> T` | Lấy sau T | Không bao gồm T. |
| `<= T` | Lấy đến T | Bao gồm T. |
| `< T` | Lấy trước T | Không bao gồm T. |
| `>= T1 AND < T2` | Khoảng nửa mở `[T1, T2)` | Có T1, không có T2. |

Các so sánh `>`, `>=`, `<`, `<=` này đang áp dụng cho **clustering column `occurred_at`**, sau khi đã cung cấp đủ partition key. Chúng không đồng nghĩa với khả năng truy vấn phạm vi trực tiếp trên `event_day`, vốn là một thành phần của partition key.

### 5.3. Chỉ cần một cận cũng được

```sql
-- Mọi sự kiện bắt đầu từ 09:30 (cả hai dòng cùng thời điểm).
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at >= '2026-11-20 09:30:00+0000';

-- Mọi sự kiện trước 09:30, loại trừ hai dòng 09:30.
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at < '2026-11-20 09:30:00+0000';
```

Cận một phía hữu ích cho hoạt động “xem các sự kiện gần đây” hoặc “xem trước một mốc”, nhưng nếu partition có dữ liệu lớn, hãy bổ sung `LIMIT` phù hợp hoặc tổ chức bucket để giới hạn phạm vi.

## 6. Nhiều clustering columns: tiền tố, tuple và ranh giới chính xác

Trong bảng này, thứ tự clustering là:

```text
occurred_at ASC -> event_id ASC
```

Điều kiện trên clustering columns cần tôn trọng **tiền tố theo thứ tự khai báo**. Ví dụ:

```sql
-- Hợp lệ: cố định occurred_at rồi giới hạn event_id.
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at = '2026-11-20 09:30:00+0000'
  AND event_id > 00000000-0000-4000-8000-000000000002;
```

Kết quả là dòng `CLICK` có `event_id` kết thúc bằng `...0003`. Vì `occurred_at` đã bằng một giá trị, khoảng theo `event_id` tạo được lát cắt đúng trong nhóm này.

Ngược lại:

```sql
-- Không hợp lệ theo đường khóa thông thường: bỏ qua occurred_at.
SELECT event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_id > 00000000-0000-4000-8000-000000000002;

-- Không thể coi hai điều kiện sau là một khoảng clustering liên tục.
SELECT event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at > '2026-11-20 09:00:00+0000'
  AND event_id > 00000000-0000-4000-8000-000000000002;
```

Khi cần so sánh **đầy đủ cặp clustering columns** theo thứ tự từ trái sang phải, CQL hỗ trợ tuple:

```sql
-- Tuple boundary: sau đúng bộ khóa (09:30, ...0002).
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND (occurred_at, event_id) > (
      '2026-11-20 09:30:00+0000',
      00000000-0000-4000-8000-000000000002
  );
```

Với khóa sắp `ASC` ở cả hai cột, biểu thức tuple trên có nghĩa **các dòng đứng sau bộ `(09:30, ...0002)` theo thứ tự từ điển**:

- `(09:30, ...0003)` được lấy vì timestamp bằng nhau và ID lớn hơn.
- `(11:00, ...0004)` được lấy vì timestamp lớn hơn, bất kể ID.
- `(09:30, ...0002)` bị loại trừ vì toán tử `>`.

**Khác biệt quan trọng:** `(occurred_at, event_id) > (T, I)` không tương đương `occurred_at > T AND event_id > I`. Dạng tuple mô tả một ranh giới trên **cặp khóa có thứ tự**; hai điều kiện rời rạc đòi cả hai thành phần đều lớn hơn và có thể không được CQL cho phép theo cách đó.

Khi thay clustering order thành `DESC` hoặc trộn `ASC`/`DESC`, phải xem xét lại ý nghĩa cursor và khả năng hỗ trợ so sánh tuple theo phiên bản Cassandra. Các ví dụ trên cố ý dùng **hai cột ASC** để tránh nhập nhằng.

## 7. Kết hợp ORDER BY và LIMIT

### 7.1. Đọc từ cũ đến mới hoặc đảo ngược

```sql
-- Thứ tự mặc định của bảng: cũ trước.
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY occurred_at ASC, event_id ASC
LIMIT 2;

-- Thứ tự đảo: mới trước.
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 2;
```

Truy vấn đầu trả `LOGIN 08:00`, `VIEW 09:30`. Truy vấn thứ hai trả `LOGOUT 11:00`, `CLICK 09:30`. Cassandra chỉ hỗ trợ `ORDER BY` theo clustering columns với quy tắc phù hợp thứ tự được khai báo (hoặc chiều đảo được hỗ trợ), không sắp tự do theo `event_type` hay `payload`.

### 7.2. LIMIT giới hạn kết quả, không đổi phương án định vị partition

```sql
SELECT occurred_at, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at >= '2026-11-20 09:00:00+0000'
ORDER BY occurred_at ASC
LIMIT 2;
```

Trong dữ liệu mẫu, giới hạn này đủ để trả `VIEW` và `CLICK`. Nhưng `LIMIT 2` không biến `WHERE event_type = 'VIEW'` thành truy vấn định vị partition, cũng không biến một partition cực lớn thành mô hình dữ liệu tốt.

Phân biệt:

- `LIMIT n` là số dòng tối đa của **cả kết quả**.
- `PER PARTITION LIMIT n` là giới hạn số dòng **trên mỗi partition** khi truy vấn chạm nhiều partition.
- **Page size** của Java driver là số dòng dự kiến fetch trong một đợt qua giao thức paging, **không phải** tổng số dòng được phép trả về.

## 8. Phân trang theo khóa: tránh bỏ sót khi timestamp trùng

Giả sử API muốn lấy **hai sự kiện mỗi trang**, từ cũ đến mới. Sau trang đầu, trang tiếp phải bắt đầu *ngay sau khóa đầy đủ của dòng cuối*, không chỉ dựa vào timestamp.

### Trang đầu

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY occurred_at ASC, event_id ASC
LIMIT 2;
```

Trả về:

| `occurred_at` | `event_id` | `event_type` |
| --- | --- | --- |
| 08:00 | `...0001` | `LOGIN` |
| 09:30 | `...0002` | `VIEW` |

Khóa cuối của trang một là `(09:30, ...0002)`.

### Trang sau theo tuple cursor

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND (occurred_at, event_id) > (
      '2026-11-20 09:30:00+0000',
      00000000-0000-4000-8000-000000000002
  )
ORDER BY occurred_at ASC, event_id ASC
LIMIT 2;
```

Trả về:

| `occurred_at` | `event_id` | `event_type` |
| --- | --- | --- |
| 09:30 | `...0003` | `CLICK` |
| 11:00 | `...0004` | `LOGOUT` |

Nếu dùng `occurred_at > '2026-11-20 09:30:00+0000'` cho trang hai, sự kiện `CLICK` lúc 09:30 sẽ **bị bỏ sót**, vì nó có cùng timestamp với `VIEW` ở cuối trang một. Tuple cursor giải quyết tình huống bằng một khóa thứ tự **duy nhất và có tính ổn định**, gồm timestamp cộng ID.

### Tuple cursor và paging state có vai trò khác nhau

| Cơ chế | Cách hoạt động | Phù hợp khi |
| --- | --- | --- |
| **Keyset/tuple cursor** | Ứng dụng lưu bộ clustering key cuối và dùng điều kiện so sánh ở request tiếp. | Muốn cursor giải thích được theo dữ liệu, chủ động chọn ranh giới, truy vấn gắn với một partition. |
| **Driver paging state** | Cassandra Java driver nhận/truyền trạng thái tiếp tục của **cùng một truy vấn**. | Muốn duyệt nhiều page của một câu truy vấn mà không tự xây điều kiện clustering. |
| **OFFSET** | Bỏ qua N dòng rồi lấy N dòng tiếp. | Cassandra CQL không có `LIMIT ... OFFSET ...` theo kiểu SQL. |

Không tráo đổi paging state giữa các câu truy vấn có `WHERE`, bind values, thứ tự và page size khác nhau. Cũng không coi paging state là một token nghiệp vụ an toàn để tự ý chỉnh sửa. Khi API nhận token từ client, hãy giữ tính toàn vẹn của token và ràng buộc nó với phạm vi truy vấn/người dùng phù hợp.

Cả keyset cursor lẫn paging state **không tự tạo snapshot bất biến**. Ghi mới, xóa, TTL và thay đổi dữ liệu giữa các request có thể làm tập kết quả nhìn thấy thay đổi. Tùy bài toán, cân nhắc cố định cửa sổ thời gian và thiết kế chính sách xử lý dữ liệu thay đổi.

## 9. Lấy dữ liệu qua nhiều ngày: mỗi ngày một partition

Do partition key của bảng là `(account_id, event_day)`, không thể dùng một điều kiện phạm vi `event_day >= ...` theo cách vẫn giữ một partition.

```sql
-- Không phải một khoảng clustering, vì event_day là partition key.
SELECT occurred_at, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day >= '2026-11-20'
  AND event_day < '2026-11-22';
```

Nếu chỉ cần hai ngày cụ thể, có thể định vị hai partition:

```sql
SELECT event_day, occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day IN ('2026-11-20', '2026-11-21');
```

Lưu ý rằng `IN` trên thành phần partition key cuối có thể tạo **nhiều thao tác đọc phân tán**. Không dựa vào nó để đòi hỏi thứ tự thời gian toàn cục như trong một partition. Với khoảng ngày dài, cân nhắc truy vấn từng bucket có giới hạn rồi hợp nhất ở tầng ứng dụng, hoặc thêm bảng khác nếu yêu cầu truy vấn không phù hợp cách chia ngày.

**Trade-off khi chọn bucket:**

- Bucket nhỏ (theo ngày/giờ) giữ số dòng mỗi partition ở mức dễ kiểm soát, nhưng truy vấn dài phải đọc nhiều partition.
- Bucket lớn (theo tháng hoặc không chia) có thể giảm số partition phải truy cập cho một lịch sử, nhưng dễ hình thành partition lớn, làm tăng chi phí đọc và compaction/repair.

Bucket cần được chọn dựa trên tốc độ ghi, độ dài lịch sử cần đọc, kích cỡ dòng, các yêu cầu phân trang và hành vi thực tế của cluster.

## 10. Ứng dụng Java: point lookup và range lookup có bind marker

Ví dụ với **Apache Cassandra Java Driver 4.x**; giả định đã có `CqlSession session` kết nối tới keyspace `cassandra_range_lab`.

### 10.1. Point lookup theo primary key đầy đủ

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

UUID accountId = UUID.fromString("11111111-1111-4111-8111-111111111111");
UUID eventId = UUID.fromString("00000000-0000-4000-8000-000000000002");
LocalDate day = LocalDate.parse("2026-11-20");

PreparedStatement byFullKey = session.prepare("""
    SELECT event_type, payload
    FROM events_by_account_day
    WHERE account_id = ?
      AND event_day = ?
      AND occurred_at = ?
      AND event_id = ?
    """);

BoundStatement exact = byFullKey.bind(
    accountId,
    day,
    Instant.parse("2026-11-20T09:30:00Z"),
    eventId
);

Row row = session.execute(exact).one();
if (row != null) {
    System.out.println(row.getString("event_type"));
}
```

Với prepared statement, kiểu dữ liệu được bind phải tương ứng CQL: `uuid` ↔ `UUID`, `date` ↔ `LocalDate`, `timestamp` ↔ `Instant`. `Row == null` thể hiện không có dòng khớp theo kết quả đọc với consistency level hiện tại; không nên coi là bằng chứng mạnh hơn về mọi replica.

### 10.2. Range lookup trong một partition

```java
PreparedStatement byTimeRange = session.prepare("""
    SELECT occurred_at, event_id, event_type
    FROM events_by_account_day
    WHERE account_id = ?
      AND event_day = ?
      AND occurred_at >= ?
      AND occurred_at < ?
    ORDER BY occurred_at ASC, event_id ASC
    LIMIT ?
    """);

BoundStatement range = byTimeRange.bind(
    accountId,
    day,
    Instant.parse("2026-11-20T09:00:00Z"),
    Instant.parse("2026-11-20T11:00:00Z"),
    100
).setPageSize(50);

for (Row event : session.execute(range)) {
    System.out.printf("%s %s %s%n",
        event.getInstant("occurred_at"),
        event.getUuid("event_id"),
        event.getString("event_type")
    );
}
```

Trong ví dụ này, `LIMIT 100` giới hạn **toàn bộ kết quả CQL**, còn `setPageSize(50)` cấu hình việc fetch theo page từ driver. Việc dùng `CqlSession.execute(...)` rồi duyệt `ResultSet` có thể kích hoạt tải thêm page; nếu cần API phân trang có cursor, nên điều khiển rõ số page trả về và paging state thay vì tự động duyệt toàn bộ kết quả.

Đoạn mã dùng Java text blocks (Java 15+). Trong dự án Java cũ hơn, thay text blocks bằng chuỗi Java thông thường.

### 10.3. Consistency không thay đổi ý nghĩa bộ khóa

Trong cluster phân tán, consistency level của request (ví dụ `LOCAL_ONE`, `LOCAL_QUORUM`) được cấu hình ở driver hoặc statement phù hợp với replication và độ mới dữ liệu cần có. Dù đọc theo khóa đầy đủ hay theo khoảng, **cùng một primary key vẫn định vị cùng partition**. Mức consistency quyết định số replica cần xác nhận một phép đọc thành công và ảnh hưởng trade-off độ trễ/khả dụng/độ mới dữ liệu; nó không bổ sung đường truy vấn cho các cột vốn không có trong khóa.

Khi ứng dụng gặp timeout hoặc unavailable, cần phân biệt lỗi liên quan replica/cluster với lỗi `InvalidQuery` do điều kiện khóa. Cố gắng tăng timeout không sửa được truy vấn `WHERE` thiếu partition key.

## 11. Các lỗi và hiểu nhầm phổ biến

| Cách hiểu hoặc câu truy vấn | Vì sao có vấn đề | Cách sửa |
| --- | --- | --- |
| `WHERE event_id = I` | `event_id` không phải partition key; không có đường tra cứu trực tiếp trong schema. | Lưu đầy đủ primary key khi cần lấy chi tiết hoặc bổ sung bảng tra cứu. |
| `WHERE account_id = A` | Thiếu `event_day` trong composite partition key. | Truy vấn các ngày đã biết hoặc tạo bảng cho nhu cầu đọc theo toàn tài khoản. |
| `WHERE account_id = A AND event_day >= D` | `event_day` là một phần partition key, không phải clustering key. | Dùng các bucket ngày xác định; thiết kế lại nếu cần khoảng ngày dài. |
| `WHERE occurred_at BETWEEN T1 AND T2` | Đó là cách nghĩ từ SQL; dùng các toán tử CQL được hỗ trợ để mô tả ranh giới. | `occurred_at >= T1 AND occurred_at < T2` trong partition đã biết. |
| `WHERE account_id = A AND event_day = D AND event_id = I` | Bỏ qua clustering column đầu `occurred_at`. | Cung cấp `occurred_at`, thay truy vấn hoặc thiết kế bảng mới. |
| `WHERE ... AND occurred_at > T AND event_id > I` | Hai điều kiện rời rạc không mô tả đúng ranh giới tuple và thường không được hỗ trợ như một slice. | Dùng `(occurred_at, event_id) > (T, I)` với khóa/clustering order thích hợp. |
| `occurred_at > lastTime` để sang trang | Bỏ sót các dòng trùng timestamp với dòng cuối trang trước. | Lưu cursor gồm cả `occurred_at` và `event_id`, hoặc dùng driver paging state. |
| `SELECT *` hoặc `LIMIT 10` tự làm truy vấn rẻ | Không thay đổi phạm vi đọc hay cách định tuyến partition. | Chọn khóa và bucket phù hợp, giới hạn phạm vi, chỉ lấy cột cần thiết. |
| `ALLOW FILTERING` là giải pháp cho mọi điều kiện | Có thể quét và sàng lọc nhiều dòng, với latency khó dự đoán. | Thiết kế lại bảng theo truy vấn hoặc xem xét chỉ mục phù hợp use case. |

## 12. Bài thực hành và tự kiểm tra

### Bài 1. Point lookup

Lấy `payload` của dòng `CLICK` lúc `09:30` ngày 20/11/2026 cho tài khoản mẫu, biết `event_id` kết thúc bằng `...0003`.

**Đáp án:**

```sql
SELECT payload
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at = '2026-11-20 09:30:00+0000'
  AND event_id = 00000000-0000-4000-8000-000000000003;
```

Kết quả dự kiến: `Bam chi tiet`.

### Bài 2. Range lookup

Lấy các sự kiện của ngày 20/11 từ `08:30` đến **trước** `11:00` UTC.

**Đáp án:**

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at >= '2026-11-20 08:30:00+0000'
  AND occurred_at <  '2026-11-20 11:00:00+0000';
```

Trả về hai dòng `VIEW` và `CLICK` lúc `09:30`, không lấy `LOGIN` lúc 08:00 hay `LOGOUT` lúc 11:00.

### Bài 3. Tiếp tục phân trang từ dòng trùng timestamp

Trang một có dòng cuối là `(09:30, ...0002)`. Viết điều kiện trang hai sao cho không lặp dòng `VIEW` và không bỏ mất `CLICK`.

**Đáp án:**

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND (occurred_at, event_id) > (
      '2026-11-20 09:30:00+0000',
      00000000-0000-4000-8000-000000000002
  )
ORDER BY occurred_at ASC, event_id ASC
LIMIT 2;
```

Trả về `CLICK` và `LOGOUT`.

### Bài 4. Nhận diện điều kiện không phù hợp

Vì sao câu lệnh sau không phải truy vấn theo một khoảng trong partition?

```sql
SELECT occurred_at, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day > '2026-11-20';
```

**Gợi ý:** `event_day` tham gia **partition key**, nên các giá trị ngày khác nhau chọn những partition khác nhau; nó không phải clustering column có thể range-scan sau `account_id`. Muốn đọc nhiều ngày, cần biết danh sách partition hoặc có bảng phục vụ mẫu truy vấn đó.

## 13. Checklist ứng dụng thực tế

Trước khi phát hành endpoint đọc dữ liệu Cassandra:

1. **Truy vấn một dòng:** đã có toàn bộ partition key và clustering key chưa? Nếu chỉ có ID nghiệp vụ, nó có đủ định vị dữ liệu hay cần bảng lookup?
2. **Truy vấn một khoảng:** đã cố định đầy đủ partition key và đặt điều kiện phạm vi trên clustering column phù hợp chưa? Ranh giới có tính bao gồm/loại trừ rõ ràng chưa?
3. **Sắp xếp:** thứ tự trả về có tương thích với clustering order không? Nếu phân trang bằng cursor, đã dùng bộ khóa đủ duy nhất để không bỏ sót timestamp trùng chưa?
4. **Dữ liệu nhiều ngày:** đã tính số partition cần truy vấn và chiến lược hợp nhất kết quả chưa?
5. **Tải thực tế:** kích thước partition, số dòng, tombstone, compaction và repair có thể ảnh hưởng độ trễ như thế nào? `LIMIT` và page size có đáp ứng yêu cầu nhưng vẫn tránh scan quá lớn không?
6. **Java driver:** đã bind đúng kiểu (`UUID`, `LocalDate`, `Instant`), đặt consistency/page size hợp lý và xử lý timeout/retry/paging state theo chính sách ứng dụng chưa?

Điều quan trọng nhất là **truy vấn theo primary key đầy đủ định vị một dòng; truy vấn theo partition key đầy đủ định vị một partition; điều kiện clustering thu hẹp thành lát cắt trong partition đó**. Thiết kế khóa và bucket phù hợp sẽ giúp truy vấn có chi phí dễ dự đoán khi Cassandra chạy phân tán và nhân bản trên nhiều node.

## Tài liệu tham khảo

- [Apache Cassandra Documentation — CQL Data Manipulation (SELECT, WHERE, ORDER BY, LIMIT)](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html)
- [Apache Cassandra Documentation — CQL Data Definition (PRIMARY KEY, CLUSTERING ORDER)](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html)
- [Apache Cassandra Documentation — Data Modeling Overview](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html)
- [Apache Cassandra Java Driver — Paging](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/paging/index.html)
