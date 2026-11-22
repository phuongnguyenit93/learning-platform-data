# Điều kiện trên partition key và clustering column trong Apache Cassandra

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **partition key**, **clustering columns** và **primary key** trong bảng wide-column của Apache Cassandra.
2. Viết điều kiện `WHERE` để truy cập đúng một partition hoặc một số partition xác định, tránh quét dữ liệu không cần thiết.
3. Sử dụng điều kiện bằng, `IN` và phạm vi `>`, `>=`, `<`, `<=` trên các clustering columns đúng thứ tự.
4. Hiểu giới hạn của điều kiện trên composite partition key, nhiều clustering columns, tuple và `token()`.
5. Giải thích vì sao truy vấn bị từ chối hoặc có độ trễ không ổn định, đồng thời chọn thiết kế bảng đáp ứng yêu cầu của ứng dụng Java.

Đây là bài trong chương **SELECT và phân trang**, thuộc mô-đun `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`: học kiến trúc phân tán, mô hình wide-column, khóa phân vùng, thiết kế bảng theo truy vấn, consistency đọc ghi, CQL và kết nối Java. Trọng tâm ở đây là **quy tắc chọn dòng dữ liệu trong `WHERE`**, không chỉ ghi nhớ một số mẫu câu lệnh.

## 1. Hai lớp khóa quyết định cách đọc

Một bảng Cassandra có `PRIMARY KEY` gồm:

- **Partition key**: một cột hoặc nhiều cột cùng xác định partition. Cassandra tính token từ **toàn bộ partition key** để tìm các replica lưu partition.
- **Clustering columns**: các cột theo sau partition key; xác định thứ tự và danh tính của các dòng **bên trong cùng một partition**.

Ví dụ ba cách khai báo:

| Định nghĩa | Partition key | Clustering columns |
| --- | --- | --- |
| `PRIMARY KEY (account_id)` | `account_id` | Không có |
| `PRIMARY KEY (account_id, event_time)` | `account_id` | `event_time` |
| `PRIMARY KEY ((account_id, event_day), event_time, event_id)` | `(account_id, event_day)` | `event_time`, rồi `event_id` |

Ở dòng thứ ba, cặp ngoặc tròn lồng nhau rất quan trọng. Cassandra **hash cả cặp `(account_id, event_day)`** để định vị partition. Các giá trị cùng `account_id` nhưng khác `event_day` thuộc các partition khác nhau, có thể được phục vụ bởi những tập replica khác nhau. Đây không phải chỉ mục có thứ tự theo `account_id` rồi theo `event_day` như cách thường hình dung về B-tree trong SQL.

Sơ đồ mô hình:

```text
PRIMARY KEY ((account_id, event_day), event_time, event_id)
              \__________________/  \________/  \______/
                partition key        clustering columns

(account A, ngày 20)  ──> partition P1 ──> các dòng theo event_time, event_id
(account A, ngày 21)  ──> partition P2 ──> các dòng theo event_time, event_id
(account B, ngày 20)  ──> partition P3 ──> các dòng theo event_time, event_id
```

**Hệ quả trực tiếp:** một truy vấn giới hạn đầy đủ partition key thường có phạm vi đọc dự đoán được. Bỏ bớt một thành phần của composite partition key không có nghĩa là Cassandra có thể “duyệt một nhánh” theo thành phần còn lại.

## 2. Dựng bảng thực hành theo truy vấn

Giả sử ứng dụng cần màn hình lịch sử hoạt động của **một tài khoản trong một ngày**, hiển thị sự kiện mới nhất trước và có thể lọc khoảng thời gian.

Chạy các câu lệnh sau trong `cqlsh` trên môi trường thử nghiệm:

```sql
-- Cấu hình một replica chỉ phục vụ lab Cassandra một node.
CREATE KEYSPACE IF NOT EXISTS cql_where_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

USE cql_where_lab;

CREATE TABLE IF NOT EXISTS events_by_account_day (
    account_id uuid,
    event_day date,
    event_time timestamp,
    event_id uuid,
    event_type text,
    details text,
    PRIMARY KEY ((account_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);

INSERT INTO events_by_account_day
    (account_id, event_day, event_time, event_id, event_type, details)
VALUES
    (11111111-1111-4111-8111-111111111111,
     '2026-11-20', '2026-11-20 09:15:00+0000',
     00000000-0000-4000-8000-000000000001,
     'LOGIN', 'Dang nhap tren web');

INSERT INTO events_by_account_day
    (account_id, event_day, event_time, event_id, event_type, details)
VALUES
    (11111111-1111-4111-8111-111111111111,
     '2026-11-20', '2026-11-20 11:45:00+0000',
     00000000-0000-4000-8000-000000000002,
     'VIEW', 'Mo trang don hang');

INSERT INTO events_by_account_day
    (account_id, event_day, event_time, event_id, event_type, details)
VALUES
    (11111111-1111-4111-8111-111111111111,
     '2026-11-20', '2026-11-20 11:45:00+0000',
     00000000-0000-4000-8000-000000000003,
     'CLICK', 'Chon chi tiet don hang');

INSERT INTO events_by_account_day
    (account_id, event_day, event_time, event_id, event_type, details)
VALUES
    (11111111-1111-4111-8111-111111111111,
     '2026-11-21', '2026-11-21 08:00:00+0000',
     00000000-0000-4000-8000-000000000004,
     'LOGIN', 'Dang nhap ngay moi');
```

**Giải thích thiết kế:**

- `account_id` và `event_day` cùng tạo partition key: tất cả sự kiện của **một tài khoản trong một ngày** nằm trong một partition.
- `event_time` là clustering column đầu tiên, cho phép tìm sự kiện theo phạm vi thời gian và đọc mới nhất trước nhờ `DESC`.
- `event_id` là clustering column thứ hai, bảo đảm hai sự kiện cùng `event_time` vẫn có thể là hai dòng khác nhau.
- `event_type` và `details` là cột dữ liệu thường; chúng **không tự động tạo đường truy cập** hiệu quả trong `WHERE`.
- Mỗi bộ giá trị đầy đủ `(account_id, event_day, event_time, event_id)` định danh một dòng. Ghi cùng primary key là upsert, không tạo dòng thứ hai.

Trong hệ thống nhiều node, thiết kế replication theo datacenter (thường `NetworkTopologyStrategy`) và chọn consistency theo yêu cầu. Những lựa chọn đó ảnh hưởng độ bền và mức độ mới của dữ liệu đọc được, nhưng **không thay đổi quy tắc `WHERE` của CQL**.

## 3. Điều kiện trên partition key

### 3.1. Bằng (=): xác định đúng một partition

```sql
SELECT event_time, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20';
```

Đây là đường đọc phù hợp với bảng:

1. Coordinator nhận `account_id` và `event_day`.
2. Cassandra tính token từ **toàn bộ cặp khóa phân vùng**, xác định các replica chịu trách nhiệm.
3. Tập dữ liệu cần đọc được giới hạn trong partition tương ứng; các dòng được duyệt theo clustering order.

Kết quả từ dữ liệu mẫu có **ba sự kiện của ngày 20/11**, mặc định sắp theo `event_time DESC`, sau đó `event_id DESC`. Không cần đưa partition key vào danh sách cột `SELECT` để sử dụng nó trong `WHERE`.

Nếu chỉ biết `account_id` nhưng chưa biết `event_day`:

```sql
-- Không đáp ứng partition key đầy đủ của bảng ví dụ.
SELECT event_time, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111;
```

Không nên kỳ vọng Cassandra tự truy ra mọi `event_day` của tài khoản. Với bảng hiện tại, truy vấn này không có đường định vị partition đầy đủ và thường bị từ chối nếu không cho phép lọc. Nếu ứng dụng cần “toàn bộ lịch sử tài khoản” thường xuyên, cần một cách đọc được thiết kế riêng: ví dụ dịch vụ lần lượt truy vấn các bucket ngày đã biết hoặc một bảng khác phù hợp với cửa sổ thời gian yêu cầu.

### 3.2. IN: liệt kê một số partition đã biết

`IN` biểu diễn tập giá trị cụ thể, được coi là một loại điều kiện bằng cho mục đích chọn khóa. Với **composite partition key**, có thể áp dụng `IN` trên thành phần cuối sau khi đã cố định các thành phần trước:

```sql
SELECT event_day, event_time, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day IN ('2026-11-20', '2026-11-21');
```

Truy vấn này có thể truy cập **hai partition riêng biệt**. Tập dữ liệu mẫu trả về ba sự kiện ngày 20 và một sự kiện ngày 21; không suy ra rằng tất cả sự kiện từ nhiều partition đã được sắp thứ tự thời gian **toàn cục**.

So sánh:

| Mẫu điều kiện | Phạm vi đọc dự kiến |
| --- | --- |
| `account_id = A AND event_day = D` | Một partition xác định bởi `(A, D)`. |
| `account_id = A AND event_day IN (D1, D2)` | Hai partition cụ thể. |
| `account_id = A` | Không đủ composite partition key. |
| `event_day = D` | Bỏ qua thành phần đầu của composite partition key. |
| `account_id = A AND event_day >= D` | Bất đẳng thức trực tiếp trên partition key không được hỗ trợ theo cách này. |

**Chi phí của `IN`:** danh sách nhiều giá trị có thể tạo nhiều lần đọc tới những partition khác nhau, khiến độ trễ tăng hoặc khó dự đoán. Giới hạn số phần tử, quan sát truy vấn thực tế và cân nhắc tách thành các request có giới hạn thay vì xem `IN` là thay thế cho thiết kế bảng.

### 3.3. Vì sao không dùng khoảng giá trị trực tiếp trên partition key?

```sql
-- Sai về mô hình truy cập: event_day là thành phần của partition key.
SELECT event_time, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day >= '2026-11-20'
  AND event_day < '2026-11-23';
```

Dù `date` có thứ tự thời gian, Cassandra phân vùng theo **token băm của toàn bộ partition key**, không đặt các partition cùng `account_id` cạnh nhau theo `event_day`. Vì vậy, so sánh `>=`/`<` trực tiếp trên thành phần partition key không tạo được một lát cắt liên tục có thể tra cứu như trên clustering column.

Để truy vấn vài ngày đã biết, liệt kê partition qua `IN` hoặc nhiều câu truy vấn riêng. Nếu nhu cầu chính là tìm khoảng ngày dài và biến thiên liên tục, hãy xem xét một bảng đọc khác có partition bucket và clustering theo thời gian phù hợp với lưu lượng và kích cỡ partition.

## 4. Điều kiện trên clustering columns

Sau khi định vị partition, Cassandra đọc các dòng theo thứ tự khai báo trong `PRIMARY KEY`. Trong bảng ví dụ, thứ tự clustering là:

```text
Partition (account_id, event_day)
        |
        +-- event_time DESC
                 |
                 +-- event_id DESC
```

Điều kiện trên clustering columns cần chọn một đoạn liên tục theo thứ tự này, hoặc các tập điểm được CQL hỗ trợ. Cách tư duy thường dùng là **các cột đứng trước dùng điều kiện bằng, sau đó mới đến cột dùng điều kiện phạm vi**.

### 4.1. Bằng trên clustering column đầu tiên

```sql
SELECT event_time, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_time = '2026-11-20 11:45:00+0000';
```

Kết quả trả về **hai dòng** vì `event_time` bằng nhau nhưng `event_id` khác nhau. Đây là ví dụ cho thấy điều kiện bằng trên **một clustering column** chưa chắc xác định một dòng; chỉ bộ **primary key đầy đủ** mới xác định duy nhất.

### 4.2. Định vị một dòng bằng toàn bộ primary key

```sql
SELECT event_type, details
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_time = '2026-11-20 11:45:00+0000'
  AND event_id = 00000000-0000-4000-8000-000000000002;
```

Truy vấn trên chỉ khớp một dòng có `event_type = 'VIEW'`. Tìm một dòng từ toàn bộ primary key là mẫu truy vấn rất cụ thể, dễ dự đoán.

### 4.3. Khoảng giá trị trên clustering column

```sql
SELECT event_time, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_time >= '2026-11-20 09:00:00+0000'
  AND event_time < '2026-11-20 12:00:00+0000';
```

Điều kiện **`>=` ở đầu và `<` ở cuối** tạo khoảng nửa mở `[09:00, 12:00)`, tránh tính trùng sự kiện đúng mốc chuyển sang khoảng kế tiếp. Trong dữ liệu mẫu, ba sự kiện của ngày 20 đều nằm trong khoảng này.

Các phép toán so sánh thường dùng trên clustering column là `=`, `>`, `>=`, `<`, `<=`. CQL không cần cú pháp SQL `BETWEEN` cho trường hợp này; viết hai điều kiện phạm vi để biểu đạt rõ hai đầu.

Vì `event_time` được khai báo `DESC`, những dòng mới hơn sẽ xuất hiện trước khi không chỉ định `ORDER BY`. Phép so sánh `event_time >= ...` vẫn là so sánh **giá trị timestamp**, không có nghĩa đảo dấu điều kiện vì thứ tự lưu trữ giảm dần.

### 4.4. Cột clustering thứ hai chỉ được hạn chế khi phần trước phù hợp

Khi cả partition key và `event_time` đã được cố định bằng, bạn có thể lọc `event_id`:

```sql
SELECT event_time, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_time = '2026-11-20 11:45:00+0000'
  AND event_id > 00000000-0000-4000-8000-000000000002;
```

Với dữ liệu mẫu, truy vấn tìm dòng có `event_id` kết thúc bằng `...0003`. Cấu trúc điều kiện hợp lệ vì đã cố định **tất cả cột clustering đứng trước `event_id`**.

Hai dạng thường không phù hợp:

```sql
-- Sai: bỏ qua event_time nhưng lại lọc event_id.
SELECT event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_id = 00000000-0000-4000-8000-000000000002;

-- Sai: đặt phạm vi trên event_time rồi thêm điều kiện riêng
-- trên clustering column phía sau, không bảo đảm một lát cắt
-- liên tục theo khóa clustering.
SELECT event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_time >= '2026-11-20 09:00:00+0000'
  AND event_id = 00000000-0000-4000-8000-000000000002;
```

Trong truy vấn thứ hai, `event_id` là cột sau `event_time`. Khi `event_time` đã được hạn chế bởi phạm vi, giá trị `event_id` không tạo được một đoạn liên tiếp đơn giản trên toàn bộ khoảng `event_time`. Các điều kiện kiểu này thường bị CQL từ chối trong truy vấn thông thường; `ALLOW FILTERING` nếu được phép cũng không tự tạo chỉ mục mới.

### 4.5. IN trên cột cuối của primary key

Đối với bảng ví dụ, `event_id` là **cột cuối cùng của primary key**. Sau khi cố định những cột đứng trước, có thể chọn nhiều giá trị `event_id`:

```sql
SELECT event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_time = '2026-11-20 11:45:00+0000'
  AND event_id IN (
      00000000-0000-4000-8000-000000000002,
      00000000-0000-4000-8000-000000000003
  );
```

Điều kiện `IN` không phải toán tử khoảng thời gian, và cũng không thể tùy ý đặt lên bất kỳ clustering column nào. Theo quy tắc CQL thông dụng, `IN` được chấp nhận ở **thành phần cuối của partition key** hoặc **cột cuối của toàn bộ primary key**, có xét những điều kiện bằng ở phía trước.

### 4.6. Điều kiện tuple trên nhiều clustering columns

CQL có cú pháp gom một số clustering columns liên tiếp vào một tuple:

```sql
SELECT event_time, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND (event_time, event_id) > (
      '2026-11-20 11:45:00+0000',
      00000000-0000-4000-8000-000000000002
  );
```

Điều kiện `(event_time, event_id) > (...)` là **so sánh một tuple theo thứ tự khóa**, khác hẳn `event_time > ... AND event_id > ...`. Kiểu quan hệ này hữu ích khi cần ranh giới gồm nhiều clustering columns, nhưng phải chọn tuple theo đúng thứ tự cột và kiểm tra semantics của comparator/clustering order khi ứng dụng dùng nó làm cursor.

Một biến thể được CQL hỗ trợ là `(event_time, event_id) IN ((t1, id1), (t2, id2))`, khi cần chọn một số bộ khóa clustering cụ thể trong cùng partition.

## 5. ORDER BY và clustering order

Do bảng được tạo với:

```sql
WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC)
```

Bạn có thể yêu cầu thứ tự mặc định hoặc thứ tự đảo ngược phù hợp với cấu hình:

```sql
-- Sự kiện mới nhất trước: đúng với thứ tự mặc định.
SELECT event_time, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY event_time DESC, event_id DESC
LIMIT 20;

-- Thứ tự ngược lại: cũ nhất trước.
SELECT event_time, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY event_time ASC, event_id ASC
LIMIT 20;
```

`ORDER BY` trong Cassandra **không phải phép sắp xếp tùy ý**. Nó dựa vào clustering columns, thứ tự đã khai báo và chiều đảo hợp lệ. Không thể thay bằng `ORDER BY event_type` vì `event_type` không nằm trong clustering key. Nếu truy vấn chính cần “các sự kiện theo loại rồi theo thời gian”, đó là một mẫu truy vấn khác, thường cần bảng đọc được tổ chức theo khóa khác.

**Lưu ý với `IN` trên partition key:** khi một câu truy vấn đọc nhiều partition, không tự giả định có một thứ tự thời gian toàn cục như khi đọc một partition. Nếu ứng dụng phải trộn sự kiện từ nhiều ngày, cần thiết kế cách gộp/sắp xếp có giới hạn ở tầng ứng dụng hoặc mô hình dữ liệu riêng.

## 6. Điều kiện trên cột thường và ALLOW FILTERING

`event_type` là cột thường, nên truy vấn này không có đường truy cập bằng khóa trên bảng đã tạo:

```sql
-- Không hợp lệ với schema hiện tại trong truy vấn thông thường.
SELECT event_time, event_type
FROM events_by_account_day
WHERE event_type = 'LOGIN';
```

Ngay cả khi đã xác định partition:

```sql
-- Có thể buộc Cassandra lọc các dòng trong partition.
SELECT event_time, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_type = 'LOGIN'
ALLOW FILTERING;
```

`ALLOW FILTERING` cho phép thực thi một số truy vấn phải sàng lọc nhiều dòng, **không tạo index và không bảo đảm truy vấn nhanh**. Ở truy vấn thứ hai, dù partition đã biết, Cassandra vẫn có thể phải kiểm tra nhiều sự kiện trong partition để tìm một `LOGIN`. Nếu bỏ partition key, rủi ro chuyển thành quét qua rất nhiều partition. Chi phí phụ thuộc số dòng, tombstone, phân bố dữ liệu, topology và consistency.

Khi truy vấn theo `event_type` là nhu cầu cốt lõi, có thể cân nhắc:

- **Thiết kế thêm bảng theo truy vấn**, chẳng hạn một bảng có partition key chứa `account_id`, `event_day`, `event_type` và clustering theo `event_time`.
- **Chỉ mục phù hợp** với phiên bản Cassandra và đặc điểm phân bố dữ liệu, ví dụ Storage-Attached Index (SAI) khi được hỗ trợ. Chỉ mục không thay thế toàn bộ việc đánh giá cardinality, fan-out và tính ổn định của truy vấn.
- **Lọc sau khi đọc một tập nhỏ đã giới hạn**, nếu partition thật sự nhỏ và có kiểm soát; đo chi phí trên dữ liệu gần thực tế.

## 7. Ngoại lệ đặc biệt: phạm vi token không phải phạm vi khóa nghiệp vụ

Với partition key, các toán tử bất đẳng thức trực tiếp không xác định một dải partition liên tiếp. Cassandra hỗ trợ một dạng chuyên biệt:

```sql
-- Ví dụ biểu diễn khoảng token, thường dùng cho công cụ quét dữ liệu.
-- Hai bind marker là các token do ứng dụng/công cụ cung cấp.
SELECT account_id, event_day, event_time
FROM events_by_account_day
WHERE token(account_id, event_day) > ?
  AND token(account_id, event_day) <= ?;
```

Ở đây `token(account_id, event_day)` dùng **đúng danh sách thành phần partition key theo đúng thứ tự**. Khoảng token mô tả một phần của không gian phân phối dữ liệu, không phải “các ngày từ ngày A đến ngày B”. Kết quả có thể trải trên nhiều tài khoản, nhiều ngày và nhiều node. Đây chủ yếu là công cụ cho các tác vụ quét/di trú/kiểm tra có kiểm soát, không phải cách thực hiện màn hình lịch sử một khách hàng.

Khi cần đọc một khoảng thời gian nhiều ngày cho cùng tài khoản, hãy ưu tiên mô hình dữ liệu và cơ chế chia bucket phù hợp, thay vì cố dùng `token()` để mô phỏng so sánh ngày.

## 8. Kiểm tra nhanh một số câu WHERE

Giả sử tất cả truy vấn dưới đây chạy trên `events_by_account_day` chưa có chỉ mục bổ sung:

| Điều kiện `WHERE` | Đánh giá | Lý do |
| --- | --- | --- |
| `account_id = A AND event_day = D` | Hợp lệ, đúng một partition | Đủ composite partition key. |
| `account_id = A AND event_day IN (D1, D2)` | Hợp lệ, hai partition | `IN` trên thành phần cuối của partition key. |
| `account_id = A` | Thiếu đường đọc trực tiếp | Thiếu `event_day`, không xác định partition. |
| `event_day = D` | Thiếu đường đọc trực tiếp | Thiếu `account_id` phía trước. |
| `account_id = A AND event_day > D` | Không hợp lệ theo điều kiện khóa thông thường | Không so sánh khoảng trên partition key như clustering key. |
| `account_id = A AND event_day = D AND event_time >= T1 AND event_time < T2` | Hợp lệ | Khoảng theo clustering column đầu tiên. |
| `account_id = A AND event_day = D AND event_time = T AND event_id = I` | Hợp lệ | Xác định đủ primary key. |
| `account_id = A AND event_day = D AND event_id = I` | Không hợp lệ theo đường đọc thông thường | Bỏ qua clustering column đứng trước là `event_time`. |
| `account_id = A AND event_day = D AND event_time = T AND event_id IN (I1, I2)` | Hợp lệ | `IN` trên clustering column cuối sau các điều kiện bằng. |
| `event_type = 'LOGIN'` | Không có đường đọc bằng khóa | Cột thường chưa được lập chỉ mục. |

Từ “không hợp lệ” trong bảng nghĩa là **không được CQL chấp nhận theo đường truy vấn khóa thông thường của schema này**; một số trường hợp có thể có cú pháp khác với `ALLOW FILTERING` hoặc chỉ mục bổ sung. Điều đó không mặc nhiên biến chúng thành truy vấn nên triển khai.

## 9. Ứng dụng Java: bind partition key và khoảng clustering

Trong Java driver 4.x, hãy dùng prepared statement để truyền giá trị khóa, giữ nguyên logic truy vấn và tránh nối chuỗi đầu vào người dùng:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

// session đã kết nối với keyspace cql_where_lab.
PreparedStatement prepared = session.prepare("""
    SELECT event_time, event_id, event_type
    FROM events_by_account_day
    WHERE account_id = ?
      AND event_day = ?
      AND event_time >= ?
      AND event_time < ?
    """);

BoundStatement statement = prepared.bind(
    UUID.fromString("11111111-1111-4111-8111-111111111111"),
    LocalDate.parse("2026-11-20"),
    Instant.parse("2026-11-20T09:00:00Z"),
    Instant.parse("2026-11-20T12:00:00Z")
).setPageSize(50);

for (Row row : session.execute(statement)) {
    Instant eventTime = row.getInstant("event_time");
    UUID eventId = row.getUuid("event_id");
    String eventType = row.getString("event_type");
    System.out.printf("%s %s %s%n", eventTime, eventId, eventType);
}
```

Ví dụ trên dùng Java hỗ trợ **text blocks** (Java 15+). Trong dự án dùng Java phiên bản cũ hơn, thay text block bằng chuỗi thông thường. `setPageSize(50)` đặt kích thước trang fetch từ driver, **không giới hạn tổng số sự kiện trả về**; muốn giới hạn tổng số dòng thì thêm `LIMIT` vào CQL. Với truy vấn chạy ở môi trường phân tán, đặt consistency level phù hợp tại statement/session theo chính sách ứng dụng.

Khi triển khai cursor phân trang, bảo toàn các giá trị đầu vào làm định danh truy vấn (`account_id`, `event_day`, khoảng thời gian) và cơ chế paging state của driver. Việc đọc nhiều ngày bằng `IN` đòi hỏi xử lý thêm vấn đề thứ tự và chi phí của nhiều partition.

## 10. Bài tập tự luyện và đáp án

**Bài 1.** Lấy tất cả sự kiện của tài khoản mẫu trong ngày 20/11/2026, từ 10:00 đến trước 12:00 theo UTC.

```sql
SELECT event_time, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_time >= '2026-11-20 10:00:00+0000'
  AND event_time < '2026-11-20 12:00:00+0000';
```

*Dự kiến:* hai dòng lúc 11:45, khác `event_id`.

**Bài 2.** Lấy đúng sự kiện `CLICK` trong dữ liệu mẫu, sử dụng khóa đầy đủ.

```sql
SELECT event_type, details
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_time = '2026-11-20 11:45:00+0000'
  AND event_id = 00000000-0000-4000-8000-000000000003;
```

*Dự kiến:* đúng một dòng `CLICK`.

**Bài 3.** Giải thích vì sao truy vấn dưới đây không dùng được trực tiếp, dù `event_day` là kiểu `date`:

```sql
SELECT event_time, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day >= '2026-11-20';
```

*Gợi ý đáp án:* `event_day` là một phần của **partition key**, nên không cung cấp thứ tự theo ngày giữa các partition. Nếu thực sự chỉ cần hai ngày cụ thể, liệt kê bằng `IN`; nếu truy vấn khoảng dài là đường đọc chính, thiết kế thêm bảng phù hợp.

**Bài 4.** Vì sao không thêm `LIMIT 20` để “sửa” truy vấn `WHERE event_type = 'LOGIN'`? Vì `LIMIT` giới hạn số dòng trả về; nó không tạo ra partition key, clustering key hay chỉ mục cho `event_type`. Cassandra vẫn thiếu một đường truy cập hiệu quả.

## 11. Checklist khi thiết kế truy vấn SELECT

Trước khi đưa một câu `SELECT` vào đường xử lý chính của ứng dụng:

1. Có biết **đầy đủ partition key** hay chỉ biết một phần? Có thể mô tả chính xác những partition sẽ phải đọc không?
2. Nếu dùng `IN`, số partition phát sinh có nhỏ và được giới hạn không?
3. Nếu dùng điều kiện clustering, các cột có theo **đúng thứ tự primary key** không? Đã cố định các cột trước cột phạm vi chưa?
4. Nếu cần sắp xếp, `ORDER BY` có khớp clustering order (hoặc chiều đảo được hỗ trợ) không?
5. Có cần lọc theo cột thường, scan hoặc `ALLOW FILTERING` không? Nếu có, nên thay đổi bảng đọc, giới hạn phạm vi hay bổ sung chỉ mục?
6. Kích thước partition có được kiểm soát bằng bucket hợp lý không? Trong vận hành phân tán, mức consistency và cơ chế retry có làm thay đổi độ trễ/cảm nhận dữ liệu của API không?
7. Khi dùng Java driver, đã bind đúng kiểu khóa, đặt fetch size/`LIMIT` phù hợp và xử lý phân trang nhất quán với truy vấn chưa?

Điểm cốt lõi: **partition key xác định nơi Cassandra cần tìm dữ liệu; clustering columns xác định cách Cassandra chọn và sắp xếp những dòng trong partition đó**. Câu `WHERE` tốt phải phù hợp với cả hai lớp khóa. Nếu yêu cầu truy vấn khác đi, thường nên thay đổi hoặc bổ sung mô hình bảng phục vụ truy vấn thay vì cố ép một bảng xử lý mọi hướng truy cập.

## Tài liệu tham khảo

- [Apache Cassandra Documentation — Data Manipulation: SELECT và WHERE](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html)
- [Apache Cassandra Documentation — Data Definition: Primary Key và Clustering Columns](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html)
- [Apache Cassandra Documentation — RDBMS Design và Query-driven Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/data-modeling_rdbms.html)
