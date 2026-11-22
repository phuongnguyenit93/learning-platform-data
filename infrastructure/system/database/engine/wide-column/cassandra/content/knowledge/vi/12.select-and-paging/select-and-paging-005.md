# ORDER BY và các điều kiện tương thích với khóa phân cụm

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao `ORDER BY` trong Apache Cassandra dựa trên **clustering columns**, khác với sắp xếp tùy ý trên SQL quan hệ.
2. Đọc `PRIMARY KEY` và `CLUSTERING ORDER BY` để dự đoán **thứ tự mặc định** của các dòng trong một partition.
3. Viết `ORDER BY` hợp lệ theo chiều khai báo hoặc chiều đảo ngược; nhận diện các tổ hợp cột, chiều sắp xếp không được hỗ trợ.
4. Kết hợp điều kiện `WHERE` trên **partition key** và tiền tố **clustering key** với `=`, phạm vi thời gian, tuple và `LIMIT`.
5. Dùng ranh giới khóa đầy đủ để phân trang ổn định khi nhiều dòng có cùng timestamp.
6. Phân tích tác động của `IN` nhiều partition, kích thước partition, consistency level và Java driver đối với thời gian phản hồi.

Đây là bài thuộc chương **SELECT và phân trang** của mô-đun `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Cassandra là cơ sở dữ liệu wide-column phân tán; nó được tối ưu cho mô hình **thiết kế bảng theo truy vấn**, sử dụng partition key để xác định nơi lưu dữ liệu và clustering columns để xác định thứ tự các dòng **bên trong partition**. Hiểu đúng `ORDER BY` giúp viết CQL dự đoán được chi phí đọc, đồng thời tránh nhầm lẫn khi xây API Java có replication, consistency, paging và cơ chế xử lý lỗi.

## 1. ORDER BY trong Cassandra thực sự sắp xếp cái gì?

Trong nhiều cơ sở dữ liệu SQL, người dùng thường viết:

```sql
-- Minh họa tư duy SQL quan hệ, KHÔNG phải truy vấn
-- được bảo đảm hợp lệ với schema Cassandra bên dưới.
SELECT *
FROM events
WHERE event_type = 'LOGIN'
ORDER BY created_at DESC;
```

Hệ quản trị quan hệ có thể xây kế hoạch quét/chỉ mục/sort để trả tập dòng được yêu cầu. Còn Cassandra ưu tiên truy vấn mà đường đọc đã được mã hóa trong **primary key**:

```text
                         PRIMARY KEY
                              |
             +----------------+----------------+
             |                                 |
        partition key                    clustering columns
             |                                 |
   chọn partition/replica          chọn, sắp và duyệt dòng
             |                                 |
             +----------------+----------------+
                              |
                            SELECT
```

Vì thế:

- `WHERE` với **partition key đầy đủ** thường giúp định vị rõ partition cần đọc.
- Các **clustering columns** tạo thứ tự có sẵn của các dòng trong partition.
- `ORDER BY` trong CQL chỉ phục vụ các kiểu thứ tự tương thích với các clustering columns ấy; không yêu cầu Cassandra sắp xếp tùy ý theo mọi cột.
- `ORDER BY` không tạo thêm secondary index, không biến cột thường thành clustering key và không tự sửa truy vấn thiếu partition key.

> Quy tắc nhớ nhanh: trong Cassandra, thứ tự truy vấn quan trọng cần được **thiết kế khi tạo bảng**. `ORDER BY` chủ yếu chọn cách duyệt thứ tự đã được clustering key hỗ trợ.

## 2. Dựng bảng thực hành và nhìn thứ tự clustering

Giả sử ứng dụng cần màn hình lịch sử hoạt động của **một tài khoản trong một ngày**. Nhu cầu phổ biến là lấy các sự kiện **mới nhất trước**, đồng thời có thể đảo sang **cũ nhất trước**.

### 2.1. Lược đồ CQL

```sql
-- Cấu hình chỉ dành cho lab một node.
CREATE KEYSPACE IF NOT EXISTS cassandra_order_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

USE cassandra_order_lab;

CREATE TABLE IF NOT EXISTS events_by_account_day (
    account_id uuid,
    event_day date,
    created_at timestamp,
    event_id uuid,
    event_type text,
    detail text,
    PRIMARY KEY ((account_id, event_day), created_at, event_id)
) WITH CLUSTERING ORDER BY (created_at DESC, event_id DESC);
```

Các thành phần:

| Thành phần | Kiểu khóa | Vai trò |
| --- | --- | --- |
| `(account_id, event_day)` | Composite partition key | Cả hai giá trị cùng xác định một partition. |
| `created_at` | Clustering column thứ nhất | Sắp theo thời điểm, mới nhất trước theo mặc định. |
| `event_id` | Clustering column thứ hai | Tạo thứ tự xác định khi hai sự kiện có cùng thời điểm. |
| `event_type`, `detail` | Cột thường | Mang nội dung; không dùng được làm `ORDER BY` tùy ý. |

Ở đây `created_at` và `event_id` đều được khai báo `DESC`. Do đó, thứ tự đọc mặc định của một partition là:

```text
created_at từ lớn đến nhỏ
     |
     +-- khi created_at bằng nhau:
           event_id từ lớn đến nhỏ
```

### 2.2. Thêm dữ liệu mẫu có timestamp trùng nhau

```sql
INSERT INTO events_by_account_day
    (account_id, event_day, created_at, event_id, event_type, detail)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 08:00:00+0000',
    00000000-0000-4000-8000-000000000001,
    'LOGIN', 'Dang nhap'
);

INSERT INTO events_by_account_day
    (account_id, event_day, created_at, event_id, event_type, detail)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 09:30:00+0000',
    00000000-0000-4000-8000-000000000002,
    'VIEW', 'Xem don hang'
);

INSERT INTO events_by_account_day
    (account_id, event_day, created_at, event_id, event_type, detail)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 09:30:00+0000',
    00000000-0000-4000-8000-000000000003,
    'CLICK', 'Mo chi tiet don'
);

INSERT INTO events_by_account_day
    (account_id, event_day, created_at, event_id, event_type, detail)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 11:00:00+0000',
    00000000-0000-4000-8000-000000000004,
    'PAY', 'Thanh toan'
);

INSERT INTO events_by_account_day
    (account_id, event_day, created_at, event_id, event_type, detail)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 12:00:00+0000',
    00000000-0000-4000-8000-000000000005,
    'LOGOUT', 'Dang xuat'
);

-- Một partition khác của cùng account.
INSERT INTO events_by_account_day
    (account_id, event_day, created_at, event_id, event_type, detail)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21', '2026-11-21 07:30:00+0000',
    00000000-0000-4000-8000-000000000006,
    'LOGIN', 'Ngay tiep theo'
);

-- Một account khác, một partition khác.
INSERT INTO events_by_account_day
    (account_id, event_day, created_at, event_id, event_type, detail)
VALUES (
    22222222-2222-4222-8222-222222222222,
    '2026-11-20', '2026-11-20 10:00:00+0000',
    00000000-0000-4000-8000-000000000007,
    'LOGIN', 'Tai khoan thu hai'
);
```

Trong dữ liệu mẫu có **ba partition có dữ liệu**: tài khoản A ngày 20 (5 dòng), tài khoản A ngày 21 (1 dòng), tài khoản B ngày 20 (1 dòng). Các ví dụ chính bên dưới chỉ đọc **partition của tài khoản A ngày 20/11/2026**. Vì sử dụng khóa cố định, chạy lại `INSERT` với cùng primary key là upsert, không tạo thêm dòng trùng.

**Quy ước:** `created_at` dùng timestamp có offset `+0000` (UTC). Tại Java, nên ánh xạ kiểu CQL `timestamp` sang `Instant`; ngày trong `event_day` cần tuân theo timezone nghiệp vụ đã quy định.

## 3. Thứ tự mặc định khi không viết ORDER BY

```sql
SELECT created_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20';
```

Vì bảng được khai báo `CLUSTERING ORDER BY (created_at DESC, event_id DESC)`, các dòng của partition này xuất hiện theo thứ tự:

| Vị trí | `created_at` (UTC) | `event_id` (đuôi) | `event_type` |
| ---: | --- | --- | --- |
| 1 | 12:00 | `...0005` | `LOGOUT` |
| 2 | 11:00 | `...0004` | `PAY` |
| 3 | 09:30 | `...0003` | `CLICK` |
| 4 | 09:30 | `...0002` | `VIEW` |
| 5 | 08:00 | `...0001` | `LOGIN` |

Hai dòng lúc `09:30` không có thứ tự ngẫu nhiên: `event_id` phân định thứ tự thứ cấp. Khi xây API thời gian thực, **thứ tự đầy đủ bằng bộ clustering key** là điều kiện quan trọng để có cursor phân trang không bỏ sót dòng.

Đổi `SELECT created_at, event_id` thành `SELECT event_type` chỉ đổi **các cột kết quả**, không đổi clustering order. Nếu muốn duyệt “các sự kiện `PAY` trước”, cần thiết kế mẫu khóa/truy vấn mới, không thể chỉ dựa vào `SELECT`.

## 4. ORDER BY hợp lệ: cùng chiều khai báo hoặc chiều đảo

### 4.1. Viết rõ thứ tự mặc định

```sql
SELECT created_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY created_at DESC, event_id DESC;
```

Với partition này, kết quả giống truy vấn không có `ORDER BY`. Viết tường minh giúp API và tài liệu thể hiện ý định đọc mới nhất trước, nhưng nó **không tạo một thao tác sort tùy ý mới**.

### 4.2. Đảo ngược cả bộ clustering order

```sql
SELECT created_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY created_at ASC, event_id ASC;
```

Kết quả theo thứ tự:

| Vị trí | `created_at` (UTC) | `event_id` (đuôi) | `event_type` |
| ---: | --- | --- | --- |
| 1 | 08:00 | `...0001` | `LOGIN` |
| 2 | 09:30 | `...0002` | `VIEW` |
| 3 | 09:30 | `...0003` | `CLICK` |
| 4 | 11:00 | `...0004` | `PAY` |
| 5 | 12:00 | `...0005` | `LOGOUT` |

Đây là **chiều đảo ngược đồng bộ** của thứ tự `DESC, DESC` trong schema. Cassandra có thể duyệt ngược thứ tự clustering; hiệu năng thực tế, nhất là trên partition lớn, cần đo thay vì giả định đọc xuôi và đọc ngược luôn có chi phí như nhau.

### 4.3. Các trường hợp không phù hợp

Đối với bảng đã khai báo hai cột `DESC`:

```sql
-- Không hợp lệ: event_type là cột thường, không phải clustering column.
SELECT created_at, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY event_type ASC;

-- Không hợp lệ: đảo chiều event_id riêng lẻ, trong khi
-- created_at vẫn theo chiều khai báo; không khớp bộ thứ tự
-- ban đầu (DESC, DESC) hay bộ đảo (ASC, ASC).
SELECT created_at, event_id
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY created_at DESC, event_id ASC;

-- Không phù hợp: bỏ qua created_at đầu tiên để
-- yêu cầu sắp trực tiếp theo event_id trên cả partition.
SELECT created_at, event_id
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY event_id DESC;
```

Về nguyên tắc, các cột trong `ORDER BY` phải tuân theo **thứ tự clustering key** đã định nghĩa; việc bỏ qua một clustering column đứng trước không tạo ra khả năng sắp xếp toàn bộ partition theo cột đứng sau. Dù một phiên bản CQL có cho phép một số dạng rút gọn khi những cột đứng trước đã được cố định bằng, hãy dùng mẫu rõ ràng và kiểm tra cú pháp trên phiên bản cluster đang chạy.

### 4.4. Nếu schema có thứ tự trộn ASC và DESC thì sao?

Cassandra cho phép định nghĩa clustering order hỗn hợp. Ví dụ một bảng khác có thể được tạo như sau:

```sql
CREATE TABLE IF NOT EXISTS events_mixed_order (
    account_id uuid,
    event_day date,
    created_at timestamp,
    event_id uuid,
    event_type text,
    PRIMARY KEY ((account_id, event_day), created_at, event_id)
) WITH CLUSTERING ORDER BY (created_at DESC, event_id ASC);
```

Đây là bảng **riêng** dùng để minh họa quy tắc, chưa có dữ liệu mẫu. Khi schema có `(DESC, ASC)`, hai hướng hợp logic là:

| Hướng đọc | Thứ tự các clustering columns |
| --- | --- |
| Cùng chiều khai báo | `ORDER BY created_at DESC, event_id ASC` |
| Đảo toàn bộ chiều khai báo | `ORDER BY created_at ASC, event_id DESC` |
| Chỉ đổi một cột | Không tương thích với cách duyệt thứ tự đã khai báo hoặc đảo ngược của toàn bộ khóa. |

Không đổi chiều một cột rồi giả định Cassandra sẽ sắp tự do như engine SQL có thể sort bảng tạm. Nếu một API thường xuyên cần cả hai bộ thứ tự không phải là đối ngẫu, cân nhắc một **bảng đọc bổ sung** với clustering order phù hợp.

## 5. WHERE tương thích với ORDER BY: partition key phải rõ

Với bảng `events_by_account_day`, cách đọc cơ bản hợp lệ là:

```sql
SELECT created_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY created_at DESC, event_id DESC
LIMIT 20;
```

Đây là truy vấn **một partition**, dùng đầy đủ composite partition key rồi duyệt theo thứ tự clustering. CQL `ORDER BY` không giải quyết được các truy vấn thiếu đường định vị partition.

### 5.1. Một vài ví dụ được/không được

| Điều kiện và yêu cầu | Đánh giá | Lý do |
| --- | --- | --- |
| `account_id = A AND event_day = D ORDER BY created_at DESC` | Phù hợp | Đầy đủ partition key; sắp theo clustering column đầu. |
| `account_id = A AND event_day = D ORDER BY created_at ASC, event_id ASC` | Phù hợp | Đảo toàn bộ chiều `DESC, DESC`. |
| `account_id = A AND event_day = D AND created_at >= T ORDER BY created_at DESC` | Phù hợp | Phạm vi trên clustering column đầu trong một partition. |
| `account_id = A AND event_day = D AND created_at = T AND event_id > I` | Phù hợp | Sau khi cố định clustering column đầu, có thể giới hạn cột kế tiếp. |
| `account_id = A ORDER BY created_at DESC` | Thiếu partition key | Không chỉ rõ `event_day` của composite partition key. |
| `event_day = D ORDER BY created_at DESC` | Thiếu partition key | Bỏ `account_id` trong partition key. |
| `account_id = A AND event_day >= D ORDER BY created_at DESC` | Không phải range scan hợp lệ trên partition key | `event_day` thuộc khóa phân vùng, không phải clustering column. |
| `account_id = A AND event_day = D ORDER BY event_type DESC` | Không tương thích | `event_type` là cột thường. |

**Chi tiết quan trọng:** thứ tự `WHERE` liệt kê điều kiện không nhất thiết phải giống thứ tự cột trong `PRIMARY KEY`; **cột và kiểu điều kiện** mới quyết định khả năng truy vấn. Đối với range scan theo clustering, thứ tự cột trong schema quyết định các tiền tố phải được ràng buộc như thế nào.

## 6. WHERE trên clustering columns: đi từ tiền tố đến khoảng

Trong partition đã biết, Cassandra giữ dữ liệu theo cặp `(created_at, event_id)`. Những điều kiện hiệu quả thường là **bằng trên các cột đứng trước**, sau đó **phạm vi trên cột tiếp theo**.

### 6.1. Khoảng nửa mở theo thời gian

```sql
SELECT created_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND created_at >= '2026-11-20 09:00:00+0000'
  AND created_at < '2026-11-20 12:00:00+0000'
ORDER BY created_at DESC, event_id DESC;
```

Đây là khoảng **`[09:00, 12:00)`** trên *giá trị timestamp*. Kết quả lần lượt là `PAY 11:00`, `CLICK 09:30`, `VIEW 09:30`. Không lấy `LOGOUT 12:00` vì điều kiện đầu trên là `<`.

**`DESC` trong schema không đảo ý nghĩa toán tử:** `created_at >= 09:00` vẫn có nghĩa timestamp từ 09:00 trở về sau, kể cả khi cách duyệt dòng là mới nhất trước. Tách bạch **điều kiện chọn dòng** và **chiều trình bày**.

### 6.2. Lọc theo thời điểm bằng rồi mới theo ID

```sql
SELECT created_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND created_at = '2026-11-20 09:30:00+0000'
  AND event_id > 00000000-0000-4000-8000-000000000002
ORDER BY created_at DESC, event_id DESC;
```

Kết quả là sự kiện `CLICK` có ID kết thúc bằng `...0003`. Điều kiện này hợp lệ vì đã cố định `created_at`, là clustering column đứng **trước** `event_id`.

Trái lại, truy vấn sau không tạo được lát cắt thông thường theo thứ tự clustering:

```sql
-- Thiếu điều kiện trên clustering column đầu created_at.
SELECT created_at, event_id
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_id > 00000000-0000-4000-8000-000000000002;
```

Ngay cả khi đã biết partition, các `event_id` khác nhau được nhóm theo từng `created_at`; không có một khoảng duy nhất theo riêng `event_id` xuyên qua toàn bộ partition. Muốn đáp ứng kiểu truy vấn này thường xuyên, cần một bảng có clustering key phù hợp, hoặc đường tra cứu khác.

### 6.3. Vì sao không viết hai phạm vi rời rạc?

```sql
-- Không phải cách đúng để mô tả "sau bộ khóa (T, I)".
SELECT created_at, event_id
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND created_at < '2026-11-20 09:30:00+0000'
  AND event_id < 00000000-0000-4000-8000-000000000003;
```

Điều kiện trên không đồng nghĩa một ranh giới chung: nó đòi **cả timestamp và ID đều nhỏ hơn**. Nó còn thường không được CQL hỗ trợ như một slice tiêu chuẩn khi đã có range trên clustering column đứng trước. Để biểu diễn ranh giới gồm nhiều clustering columns, hãy dùng **tuple comparison** khi phiên bản CQL và thứ tự clustering phù hợp.

Ví dụ với hai cột `DESC`, xem tiếp mục phân trang dưới đây.

## 7. ORDER BY khi có IN trên partition key

Truy vấn một partition là trường hợp dễ dự đoán nhất. Để lấy các ngày cụ thể của cùng tài khoản, có thể sử dụng `IN` trên thành phần cuối của composite partition key:

```sql
SELECT event_day, created_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day IN ('2026-11-20', '2026-11-21');
```

Câu này nhắm đến **hai partition**: `(account A, ngày 20)` và `(account A, ngày 21)`. Khác với truy vấn một partition, thứ tự clustering trong từng partition **không tự chứng minh có một timeline toàn cục** khi ghép các ngày.

Trong các phiên bản CQL cho phép kết hợp `IN` trên partition key với `ORDER BY`, việc sắp/ghép dữ liệu từ nhiều partition có thể làm tăng chi phí, kể cả sắp xếp trong bộ nhớ ở phía coordinator. Vì vậy, dù một truy vấn như dưới đây được cluster chấp nhận, vẫn cần kiểm tra giới hạn phiên bản và đo độ trễ:

```sql
-- Cân nhắc kỹ chi phí khi IN có nhiều partition.
SELECT event_day, created_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day IN ('2026-11-20', '2026-11-21')
ORDER BY created_at DESC, event_id DESC
LIMIT 20;
```

Nếu API cần “20 sự kiện mới nhất của tài khoản trên **mọi ngày**” ở quy mô lớn, lựa chọn ổn định hơn thường là:

1. Giới hạn danh sách bucket ngày phải đọc theo khoảng lịch sử thực tế.
2. Đọc có giới hạn từng partition, rồi hợp nhất các dòng theo khóa `(created_at, event_id)` ở tầng ứng dụng theo một quy tắc rõ ràng, hoặc
3. Tạo bảng đọc khác nếu nhu cầu sắp xếp qua mọi ngày là đường truy vấn chủ yếu.

Không mặc định `LIMIT 20` sẽ khiến Cassandra chỉ phải đọc đúng 20 dòng hoặc chỉ liên hệ một partition. Phải phân biệt **số partition ứng viên**, **số dòng được kiểm tra** và **số dòng trả về**.

## 8. LIMIT, PER PARTITION LIMIT và thứ tự trả về

Đọc tối đa ba sự kiện mới nhất trong một ngày:

```sql
SELECT created_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY created_at DESC, event_id DESC
LIMIT 3;
```

Với dữ liệu mẫu, kết quả là `LOGOUT 12:00`, `PAY 11:00`, `CLICK 09:30`. `LIMIT 3` giới hạn **tổng số dòng kết quả**, không đổi thứ tự schema hay vị trí partition.

Khi đọc nhiều partition, `PER PARTITION LIMIT` có ý nghĩa khác:

```sql
SELECT event_day, created_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day IN ('2026-11-20', '2026-11-21')
PER PARTITION LIMIT 1;
```

Lúc này mỗi partition được lấy tối đa **một dòng** theo cách duyệt của nó, nên với hai partition có dữ liệu sẽ có tối đa hai dòng. Có thể kết hợp `PER PARTITION LIMIT 1 LIMIT 1` để áp đồng thời giới hạn **mỗi partition** và giới hạn **toàn kết quả**. Nếu cần chọn “một sự kiện mới nhất toàn tài khoản” qua nhiều ngày, đừng mặc định `PER PARTITION LIMIT 1` một mình đáp ứng yêu cầu đó.

**Page size** của Java driver là khái niệm thứ ba: nó chỉ kiểm soát kích thước mỗi lần fetch dữ liệu, không phải điều kiện chọn partition hay giới hạn kết quả toàn truy vấn. `ORDER BY` + `LIMIT` + page size cần được thiết kế theo mục tiêu API thay vì coi chúng là các từ đồng nghĩa.

## 9. Phân trang theo clustering key: xử lý timestamp trùng

Giả sử API hiển thị **hai sự kiện mỗi trang**, mới nhất trước. Bởi vì hai sự kiện có cùng timestamp `09:30`, chỉ dùng timestamp làm cursor sẽ gây bỏ sót hoặc lặp dữ liệu.

### 9.1. Trang đầu

```sql
SELECT created_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY created_at DESC, event_id DESC
LIMIT 3;
```

Ví dụ lấy **ba dòng** để thấy rõ ranh giới:

| Vị trí | `created_at` | `event_id` | `event_type` |
| ---: | --- | --- | --- |
| 1 | 12:00 | `...0005` | `LOGOUT` |
| 2 | 11:00 | `...0004` | `PAY` |
| 3 | 09:30 | `...0003` | `CLICK` |

Trang sau cần bắt đầu từ **sau** khóa cuối `(09:30, ...0003)` theo hướng giảm dần, nghĩa là lấy những bộ khóa có giá trị từ điển **nhỏ hơn** cặp đó.

### 9.2. Trang tiếp theo bằng tuple boundary

```sql
SELECT created_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND (created_at, event_id) < (
      '2026-11-20 09:30:00+0000',
      00000000-0000-4000-8000-000000000003
  )
ORDER BY created_at DESC, event_id DESC
LIMIT 3;
```

Theo thứ tự khóa đã chọn, kết quả tiếp theo là `VIEW 09:30 / ...0002` rồi `LOGIN 08:00 / ...0001`. Điều kiện so sánh **tuple** bảo toàn ranh giới kép:

```text
DESC:
12:00 / id-5
11:00 / id-4
09:30 / id-3   <-- cursor: dòng cuối trang đầu
----------------
09:30 / id-2   <-- trang kế tiếp vẫn lấy được
08:00 / id-1
```

Nếu dùng đơn giản `created_at < '2026-11-20 09:30:00+0000'`, dòng `VIEW` trùng `09:30` sẽ bị bỏ qua. Nếu dùng `<=` mà không xét `event_id`, có thể lặp lại `CLICK`. Điều kiện tuple chỉ nên sử dụng khi các cột và thứ tự clustering tương thích; với schema có chiều trộn `ASC`/`DESC`, kiểm tra lại semantics để xây cursor chính xác.

### 9.3. Keyset cursor và paging state của Java driver

| Cơ chế | Cách tiếp tục | Điều cần lưu ý |
| --- | --- | --- |
| **Keyset/tuple cursor** | Request tiếp thêm ranh giới từ bộ clustering key cuối. | Ứng dụng tự quản lý hướng duyệt, khóa cuối và giới hạn phạm vi. |
| **Driver paging state** | Driver tiếp tục từng page của **cùng truy vấn** qua trạng thái giao thức. | Phải giữ truy vấn/giá trị bind tương ứng; tránh sửa, trộn hoặc dùng lại tùy tiện paging state. |
| **SQL OFFSET** | Bỏ qua N dòng rồi lấy dòng kế tiếp. | Cassandra CQL không có mẫu `LIMIT ... OFFSET ...` để nhảy trang tùy ý. |

Không một cơ chế nào ở trên tự tạo snapshot bất biến nếu dữ liệu thay đổi giữa những request. Sự kiện mới, xóa, TTL và replication lag có thể làm kết quả các trang thay đổi. Với API yêu cầu lịch sử có tính ổn định cao, cân nhắc cố định cửa sổ truy vấn và quy ước cursor theo nghiệp vụ.

## 10. Tình huống thực tế: thiết kế sai ORDER BY và cách sửa

Giả sử sản phẩm đặt ra hai yêu cầu:

- **A.** “Với một tài khoản và một ngày, lấy 50 sự kiện mới nhất.”
- **B.** “Với một tài khoản và một ngày, lấy 50 sự kiện có `event_type` theo thứ tự chữ cái, rồi mới theo `created_at`.”

Bảng `events_by_account_day` đáp ứng **A** trực tiếp:

```sql
SELECT created_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY created_at DESC, event_id DESC
LIMIT 50;
```

Nó không đáp ứng **B** bằng cách thêm `ORDER BY event_type ASC, created_at DESC`, vì `event_type` không nằm trong clustering key.

Nếu B là truy vấn quan trọng, một bảng theo truy vấn có thể được thiết kế như sau:

```sql
CREATE TABLE IF NOT EXISTS events_by_account_day_type (
    account_id uuid,
    event_day date,
    event_type text,
    created_at timestamp,
    event_id uuid,
    detail text,
    PRIMARY KEY ((account_id, event_day), event_type, created_at, event_id)
) WITH CLUSTERING ORDER BY (
    event_type ASC,
    created_at DESC,
    event_id DESC
);
```

Với schema này, `event_type` là clustering column **đầu tiên**, nên trong partition đã biết có thể duyệt theo loại rồi theo thời điểm. Nếu yêu cầu mới lại là “mới nhất của **một loại sự kiện**” và dữ liệu mỗi tenant/ngày lớn, cũng có thể cân nhắc đưa `event_type` vào partition key của bảng phục vụ truy vấn riêng. Đây là quyết định thiết kế schema và chi phí ghi/đồng bộ dữ liệu, không phải khả năng `ORDER BY` tự bổ sung.

**Trade-off:** nhiều bảng đọc giúp phục vụ nhiều hướng truy vấn hiệu quả, nhưng ứng dụng phải duy trì các bản ghi denormalized và xử lý việc ghi, retry, TTL, sửa dữ liệu, backfill và consistency phù hợp. Các bảng không tự động tạo quan hệ đồng bộ kiểu join.

## 11. Tích hợp Java: truy vấn được chuẩn bị và sắp xếp

Ví dụ dưới đây dùng **Apache Cassandra Java Driver 4.x**, Java 15+ (text blocks), giả định đã có `CqlSession session` kết nối vào keyspace `cassandra_order_lab`.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

UUID accountId = UUID.fromString(
    "11111111-1111-4111-8111-111111111111"
);
LocalDate eventDay = LocalDate.parse("2026-11-20");

PreparedStatement prepared = session.prepare("""
    SELECT created_at, event_id, event_type
    FROM events_by_account_day
    WHERE account_id = ?
      AND event_day = ?
      AND created_at >= ?
      AND created_at < ?
    ORDER BY created_at DESC, event_id DESC
    LIMIT ?
    """);

BoundStatement statement = prepared.bind(
    accountId,
    eventDay,
    Instant.parse("2026-11-20T08:00:00Z"),
    Instant.parse("2026-11-20T12:00:00Z"),
    50
).setPageSize(20);

for (Row event : session.execute(statement)) {
    System.out.printf("%s %s %s%n",
        event.getInstant("created_at"),
        event.getUuid("event_id"),
        event.getString("event_type"));
}
```

Trong ví dụ:

- `UUID` được bind vào `uuid`, `LocalDate` vào `date`, `Instant` vào `timestamp`.
- `LIMIT 50` là **tối đa 50 dòng** của truy vấn CQL; `setPageSize(20)` là kích thước mỗi lần fetch của driver.
- `session.execute(statement)` là API đồng bộ; duyệt `ResultSet` có thể tự fetch trang tiếp theo. Muốn expose từng trang cho client, dùng cơ chế paging do driver cung cấp và quy ước token của API.
- Điều kiện `created_at < 12:00` loại `LOGOUT` lúc 12:00 ra khỏi kết quả, bất kể `ORDER BY DESC`.
- Vì chỉ truy vấn một partition xác định, quá trình đọc và sắp xếp dễ dự đoán hơn truy vấn trên nhiều ngày/partition.

**Consistency:** Java driver có thể cấu hình read consistency level ở session hoặc statement, ví dụ `LOCAL_ONE` hay `LOCAL_QUORUM` tùy replication và yêu cầu nghiệp vụ. Consistency ảnh hưởng số replica phải phản hồi và tính mới của dữ liệu, **không thay cú pháp `ORDER BY` và không tạo quyền sắp theo cột thường**. Khi truy vấn gặp `InvalidQuery` vì điều kiện khóa/`ORDER BY`, tăng timeout hoặc retry sẽ không sửa được schema. Với lỗi timeout/unavailable, cần đánh giá lại sức khỏe replica, tải, consistency và retry policy.

## 12. Lỗi thường gặp khi sử dụng ORDER BY

| Câu viết hoặc kỳ vọng | Vấn đề | Cách xử lý |
| --- | --- | --- |
| `ORDER BY event_type ASC` | `event_type` là cột thường. | Thiết kế bảng đọc có `event_type` trong clustering key nếu đây là nhu cầu chính. |
| `ORDER BY event_id DESC` mà không cố định/đề cập `created_at` | Bỏ qua cột clustering đứng trước, không mô tả thứ tự toàn partition. | Sắp theo tiền tố clustering key hoặc thiết kế bảng khác. |
| `ORDER BY created_at DESC, event_id ASC` trên schema `DESC,DESC` | Không phải chiều mặc định hay chiều đảo toàn bộ. | Dùng `DESC,DESC` hoặc `ASC,ASC`. |
| `WHERE account_id = A ORDER BY created_at DESC` | Thiếu `event_day` của composite partition key. | Cung cấp ngày/bucket hoặc thay thiết kế bảng. |
| `WHERE event_day >= D ORDER BY created_at DESC` | Range trên thành phần partition key không thay thế đường truy vấn theo một partition. | Liệt kê bucket hữu hạn hoặc tạo bảng phù hợp với range. |
| `WHERE created_at >= T AND event_id > I` | Không phải ranh giới tuple phù hợp với hai clustering columns. | Dùng điều kiện tiền tố hoặc tuple comparison hợp lệ. |
| `ORDER BY created_at DESC LIMIT 10` bảo đảm quét chỉ 10 dòng trên toàn cluster | `LIMIT` chỉ giới hạn kết quả và không tự định vị partition. | Giới hạn partition bằng `WHERE`, đo chi phí đọc. |
| `ORDER BY` tự sắp toàn cục khi truy vấn nhiều partition qua `IN` | Đọc nhiều partition có thể phải ghép/sắp với chi phí cao; không nên suy từ thứ tự trong một partition. | Giới hạn fan-out, benchmark hoặc hợp nhất qua ứng dụng/bảng đọc khác. |
| Cursor chỉ lưu `created_at` | Các sự kiện có cùng timestamp có thể bị lặp hoặc bỏ sót. | Lưu cả `created_at` và `event_id`, hoặc sử dụng driver paging state. |
| `ALLOW FILTERING` sẽ cho phép ORDER BY bất kỳ cột | `ALLOW FILTERING` chỉ có thể cho phép một số dạng lọc; không làm cột thường thành clustering key. | Thiết kế truy vấn và schema tương thích. |

## 13. Bài tập và đáp án

### Bài 1. Lấy ba sự kiện mới nhất trong ngày

**Yêu cầu:** Với bảng và dữ liệu mẫu, lấy ba sự kiện mới nhất của tài khoản A ngày 20/11.

**Đáp án:**

```sql
SELECT created_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY created_at DESC, event_id DESC
LIMIT 3;
```

Kết quả dự kiến: `LOGOUT`, `PAY`, `CLICK`.

### Bài 2. Đảo thứ tự nhưng vẫn giữ hai sự kiện cùng giờ

**Yêu cầu:** Lấy toàn bộ sự kiện ngày 20 theo thứ tự cũ nhất trước; tại `09:30`, `VIEW` đứng trước `CLICK`.

**Đáp án:**

```sql
SELECT created_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY created_at ASC, event_id ASC;
```

Kết quả: `LOGIN` → `VIEW` → `CLICK` → `PAY` → `LOGOUT`.

### Bài 3. Phân tích một truy vấn sai

```sql
SELECT created_at, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY event_type ASC, created_at DESC;
```

**Hỏi:** Vì sao truy vấn không phù hợp, dù đã biết đầy đủ partition key?

**Đáp án:** `event_type` là cột thường, không phải clustering column. Partition key đầy đủ giúp chọn đúng partition, nhưng không tạo ra một thứ tự lưu trữ theo `event_type`. Muốn truy vấn này trở thành đường đọc chính, cần thiết kế bảng với `event_type` trong khóa clustering hoặc xử lý sắp xếp trên tập dữ liệu nhỏ tại tầng ứng dụng nếu thật sự chấp nhận được.

### Bài 4. Đi tiếp sau một sự kiện trùng timestamp

**Yêu cầu:** Trang đầu của danh sách mới nhất trước kết thúc tại khóa `(09:30, ...0003)`. Viết điều kiện không bỏ sót `VIEW` lúc 09:30.

**Đáp án:**

```sql
SELECT created_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND (created_at, event_id) < (
      '2026-11-20 09:30:00+0000',
      00000000-0000-4000-8000-000000000003
  )
ORDER BY created_at DESC, event_id DESC
LIMIT 3;
```

Kết quả tiếp là `VIEW`, `LOGIN`. Ranh giới tuple loại đúng dòng cuối trang trước nhưng giữ những dòng khác có cùng timestamp và `event_id` nhỏ hơn.

### Bài 5. Nhận diện nhầm lẫn về phạm vi

**Tình huống:** Một API hỏi “20 sự kiện mới nhất của tài khoản trong 90 ngày” và định dùng `event_day IN (90 ngày) ORDER BY created_at DESC LIMIT 20`.

**Đáp án gợi ý:** Truy vấn nhắm đến **90 composite partition keys**. Ngay cả khi cú pháp được cluster chấp nhận, cần kiểm soát lượng đọc và chi phí hợp nhất/sort từ nhiều partition. Cân nhắc chia thành đợt có giới hạn, benchmark với dữ liệu và consistency thực tế, hoặc tạo bảng đọc được tối ưu cho lịch sử mới nhất của tài khoản. `LIMIT 20` không tự giới hạn số partition ứng viên xuống 20.

## 14. Checklist trước khi đưa ORDER BY vào API Java

1. Xác nhận **partition key đầy đủ** hoặc danh sách partition hữu hạn đã biết; khi dùng `IN`, đếm số partition ứng viên.
2. Kiểm tra cột trong `ORDER BY` có phải **clustering columns** và theo đúng thứ tự khai báo không.
3. Kiểm tra chiều sắp xếp là bộ chiều khai báo hoặc **chiều đảo tương thích**; không trộn tự do.
4. Nếu thêm phạm vi trong `WHERE`, xác nhận các clustering columns đứng trước đã được cố định phù hợp và cận `<`/`<=`/`>`/`>=` biểu đạt đúng khoảng mong muốn.
5. Nếu phân trang, sử dụng một bộ khóa có **thứ tự xác định**, gồm cột phân biệt khi nhiều dòng có cùng timestamp; hiểu sự khác biệt giữa cursor nghiệp vụ và paging state của driver.
6. Kiểm soát `LIMIT`, `PER PARTITION LIMIT`, page size, partition size và số request đồng thời; theo dõi p95/p99 latency, tombstones và tác động của compaction/repair.
7. Chọn replication và consistency theo cam kết đọc ghi; xử lý timeout và invalid query riêng biệt thay vì retry mọi lỗi giống nhau.

**Ghi nhớ:** `ORDER BY` của Cassandra không phải công cụ sort mọi cột trên mọi dòng. Nó sử dụng **thứ tự clustering đã được xây vào bảng**. Khi `WHERE` định vị đúng partition và điều kiện clustering hợp lệ, đọc mới nhất/cũ nhất và phân trang trở nên rõ ràng. Nếu cần một kiểu thứ tự khác làm đường đọc chính, hãy thiết kế bảng hoặc mô hình truy vấn đáp ứng kiểu thứ tự ấy.

## Tài liệu tham khảo

- [Apache Cassandra Documentation — CQL Data Manipulation: SELECT và ORDER BY](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html)
- [Apache Cassandra Documentation — CQL Data Definition: PRIMARY KEY và CLUSTERING ORDER](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html)
- [Apache Cassandra Documentation — Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html)
- [Apache Cassandra Java Driver 4.x — Paging](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/paging/index.html)
