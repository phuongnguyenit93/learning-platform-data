# TOKEN để chia phạm vi quét có kiểm soát trong Apache Cassandra

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích `token()` hoạt động trên **toàn bộ partition key**, liên quan thế nào đến partitioner, token ring, vnode và replica.
2. Viết `SELECT ... WHERE token(partition_key) ...` để quét một **khoảng token** thay vì quét toàn bảng trong một truy vấn lớn.
3. Chia miền token thành các khoảng **không giao nhau, không để hở**, xử lý đúng hai đầu ranh giới và trường hợp vòng token quay lại điểm đầu.
4. Phân biệt **số khoảng token**, **số partition thực tế** và **số dòng**; giải thích tại sao chia đều giá trị token không bảo đảm chia đều tải.
5. Thiết kế batch scan có **paging, checkpoint, giới hạn concurrency, retry và idempotency** mà không coi paging state là snapshot bất biến.
6. Nhận diện việc dùng `TOKEN` **không phù hợp** để truy vấn một khách hàng/ngày hoặc phân trang lịch sử theo thời gian.
7. Kết nối từ Java Driver, kiểm tra coverage trên dữ liệu lab và xác định ranh giới an toàn cho tác vụ vận hành phân tán.

Đây là bài thuộc chương **SELECT và phân trang** của mô-đun `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Apache Cassandra là hệ cơ sở dữ liệu wide-column phân tán: partition key quyết định cách phân phối dữ liệu trên cluster, clustering columns quyết định thứ tự dòng trong từng partition, và replication/consistency ảnh hưởng cách phục vụ yêu cầu đọc. `TOKEN` hữu ích cho **batch export, kiểm tra hoặc xử lý dữ liệu có kiểm soát**, nhưng không phải một cách thay thế thiết kế bảng theo truy vấn cho API Java thời gian thực.

## 1. Vì sao quét toàn bảng cần được chia nhỏ?

Xem truy vấn:

```sql
-- Ví dụ minh họa truy vấn rất rộng; không chạy tùy tiện ở production.
SELECT tenant_id, event_day, occurred_at, event_id
FROM events_by_tenant_day;
```

Với bảng có hàng triệu partition, câu lệnh này có thể cần:

- Đọc dữ liệu thuộc **nhiều token range** trên nhiều node.
- Điều phối nhiều replica, chịu ảnh hưởng của consistency level và tình trạng cluster.
- Gặp các partition có kích thước khác nhau, nhiều SSTable/tombstone hoặc dữ liệu hết TTL.
- Giữ một tác vụ dài, dễ timeout, khó checkpoint và khó giới hạn tác động đến request giao dịch.

Thêm `LIMIT 100` chỉ yêu cầu tối đa 100 dòng kết quả; nó **không tạo ra kế hoạch quét đầy đủ theo từng phần để lần sau tiếp tục phần chưa làm**. Đối với một công việc quét tất cả dữ liệu, cần thiết kế **đơn vị công việc nhỏ, có thể theo dõi và chạy lại**.

Một cách là tách theo token:

```text
Toàn bộ không gian token
       |
       +-- Task A: quét khoảng 1  --> pages --> checkpoint
       +-- Task B: quét khoảng 2  --> pages --> checkpoint
       +-- Task C: quét khoảng 3  --> pages --> checkpoint
       +-- ...

Điều phối concurrency, retry, tốc độ đọc và ghi kết quả ở tầng ứng dụng.
```

**Lưu ý:** Đây vẫn là công việc **quét rộng** khi cộng tất cả task. Chia nhỏ giúp kiểm soát và khôi phục, **không biến quét toàn bảng thành point lookup rẻ**.

## 2. TOKEN là gì và khác khóa nghiệp vụ thế nào?

### 2.1. Partition key được biến thành token

Giả sử bảng có:

```sql
PRIMARY KEY ((tenant_id, event_day), occurred_at, event_id)
```

Các thành phần:

| Phần khóa | Vai trò | Liên hệ với token |
| --- | --- | --- |
| `tenant_id` + `event_day` | **Composite partition key** | Cả cặp được tuần tự hóa và đưa qua partitioner để tính **một token cho partition**. |
| `occurred_at` | Clustering column thứ nhất | Không tham gia tính token của partition. |
| `event_id` | Clustering column thứ hai | Không tham gia tính token; phân biệt sự kiện cùng timestamp. |
| `event_type`, `detail` | Regular columns | Không tham gia tính token. |

Khái niệm:

```text
  tenant_id = A       event_day = 2026-11-20
       |                        |
       +-----------+------------+
                   |
          composite partition key
                   |
            partitioner/hash
                   |
                TOKEN = T
                   |
             token ring / vnode
                   |
          replica sở hữu partition
                   |
         +---------+---------+
         |         |         |
        row 1     row 2     row 3
       (các clustering keys khác nhau)
```

**Mọi dòng của cùng partition có cùng token.** Nếu partition chứa một triệu dòng, không thể tách các dòng ấy thành những token range khác nhau bằng cách nhìn vào `event_id` hay `occurred_at`. Muốn chia tiếp bên trong một partition lớn, cần thiết kế bucket hoặc clustering-range scan riêng.

### 2.2. Token không giữ thứ tự ngày, UUID hay tenant

Với partitioner phổ biến **Murmur3Partitioner**, token là giá trị băm có thứ tự trong token space. Không suy ra:

```text
event_day 2026-11-20 -> token 20
event_day 2026-11-21 -> token 21
```

Hai ngày liên tiếp của cùng tenant thường cho hai token không liên quan về thứ tự số học. Vì vậy:

- `WHERE token(tenant_id, event_day) >= X` **không** có nghĩa “đọc các ngày từ X trở đi”.
- Quét theo token giúp chia **phân phối lưu trữ**, không phải dải ngày nghiệp vụ.
- Muốn nhật ký theo ngày/thời gian, dùng full partition key và clustering range; muốn quét nhiều partition cho batch, token range có thể phù hợp.

### 2.3. Partitioner quyết định kiểu token

Mỗi cluster sử dụng một partitioner. Ví dụ:

| Partitioner | Kiểu token điển hình | Ý nghĩa vận hành |
| --- | --- | --- |
| `Murmur3Partitioner` | Giá trị số nguyên có dấu 64 bit (CQL `bigint`) | Phổ biến; ví dụ chia nửa miền số bên dưới áp dụng cho trường hợp này. |
| `RandomPartitioner` | Kiểu token khác, liên quan số nguyên lớn | Không tái sử dụng mốc `Long.MIN_VALUE`/`0`/`Long.MAX_VALUE` một cách máy móc. |
| Partitioner khác | Phụ thuộc cấu hình | Phải lấy metadata/token range thực tế để xây boundary. |

Kiểm tra partitioner của cluster và token map trước khi thiết kế công việc. Trong một số môi trường có thể xem metadata:

```sql
-- Kiểm tra trên cluster/lab có quyền truy cập system tables.
SELECT partitioner FROM system.local;
```

Những mốc số 64 bit trong phần thực hành **chỉ minh họa cluster đang dùng Murmur3Partitioner**. Không đổi partitioner hoặc quy ước tuần tự hóa partition key trong khi chạy một job dài rồi mặc định checkpoint cũ còn hợp lệ.

## 3. Lab CQL: nhiều dòng trong cùng partition

### 3.1. Tạo bảng

```sql
-- SimpleStrategy và RF=1 chỉ dành cho lab một node.
CREATE KEYSPACE IF NOT EXISTS cassandra_token_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

USE cassandra_token_lab;

CREATE TABLE IF NOT EXISTS events_by_tenant_day (
    tenant_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    detail text,
    PRIMARY KEY ((tenant_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at ASC, event_id ASC);
```

### 3.2. Nạp tám sự kiện ở bốn partition

```sql
-- Partition (tenant A, 20/11): ba dòng.
INSERT INTO events_by_tenant_day
    (tenant_id, event_day, occurred_at, event_id, event_type, detail)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 08:00:00+0000',
    00000000-0000-4000-8000-000000000001,
    'LOGIN', 'Dang nhap'
);

INSERT INTO events_by_tenant_day
    (tenant_id, event_day, occurred_at, event_id, event_type, detail)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 09:00:00+0000',
    00000000-0000-4000-8000-000000000002,
    'VIEW', 'Xem san pham'
);

INSERT INTO events_by_tenant_day
    (tenant_id, event_day, occurred_at, event_id, event_type, detail)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 10:00:00+0000',
    00000000-0000-4000-8000-000000000003,
    'CLICK', 'Them vao gio'
);

-- Partition (tenant A, 21/11): hai dòng.
INSERT INTO events_by_tenant_day
    (tenant_id, event_day, occurred_at, event_id, event_type, detail)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21', '2026-11-21 11:00:00+0000',
    00000000-0000-4000-8000-000000000004,
    'LOGIN', 'Dang nhap ngay sau'
);

INSERT INTO events_by_tenant_day
    (tenant_id, event_day, occurred_at, event_id, event_type, detail)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21', '2026-11-21 12:00:00+0000',
    00000000-0000-4000-8000-000000000005,
    'LOGOUT', 'Dang xuat'
);

-- Partition (tenant B, 20/11): một dòng.
INSERT INTO events_by_tenant_day
    (tenant_id, event_day, occurred_at, event_id, event_type, detail)
VALUES (
    22222222-2222-4222-8222-222222222222,
    '2026-11-20', '2026-11-20 07:00:00+0000',
    00000000-0000-4000-8000-000000000006,
    'LOGIN', 'Tai khoan B'
);

-- Partition (tenant C, 19/11): hai dòng.
INSERT INTO events_by_tenant_day
    (tenant_id, event_day, occurred_at, event_id, event_type, detail)
VALUES (
    33333333-3333-4333-8333-333333333333,
    '2026-11-19', '2026-11-19 18:00:00+0000',
    00000000-0000-4000-8000-000000000007,
    'VIEW', 'Tai khoan C'
);

INSERT INTO events_by_tenant_day
    (tenant_id, event_day, occurred_at, event_id, event_type, detail)
VALUES (
    33333333-3333-4333-8333-333333333333,
    '2026-11-19', '2026-11-19 18:30:00+0000',
    00000000-0000-4000-8000-000000000008,
    'CLICK', 'Tai khoan C'
);
```

Từ dữ liệu mẫu:

| Partition key | Số dòng |
| --- | ---: |
| (A, 2026-11-20) | 3 |
| (A, 2026-11-21) | 2 |
| (B, 2026-11-20) | 1 |
| (C, 2026-11-19) | 2 |
| **Tổng** | **8 dòng ở 4 partition** |

Vì `INSERT` sử dụng các khóa cố định, chạy lại trên cùng bảng là upsert, không tạo thêm hàng trùng primary key. Các kết quả dự kiến chỉ đúng nếu bảng mới và không có dữ liệu khác hoặc ghi/xóa đồng thời.

## 4. Quan sát token của từng partition

Trong bảng có composite partition key, gọi `token()` với **đúng các thành phần partition key, đúng thứ tự schema**:

```sql
SELECT tenant_id,
       event_day,
       token(tenant_id, event_day) AS partition_token,
       occurred_at,
       event_id,
       event_type
FROM events_by_tenant_day;
```

Trên lab nhỏ, truy vấn này giúp quan sát token. **Không thực hiện truy vấn toàn bảng tương tự chỉ để liệt kê token trong production có nhiều partition.**

Những gì cần kiểm tra:

1. Ba sự kiện của `(A, 2026-11-20)` có **cùng `partition_token`**.
2. Hai sự kiện của `(A, 2026-11-21)` cũng có **cùng token**, nhưng không cần gần token ngày 20.
3. Token không mã hóa giờ `occurred_at`, `event_id` hay loại sự kiện.
4. Giá trị token cụ thể phụ thuộc partitioner và serialization; **không đoán token từ ngày/UUID**.

Đừng nhầm cú pháp:

```sql
-- Đúng: toàn bộ composite partition key.
token(tenant_id, event_day)

-- Sai về mặt đường token của bảng đang dùng:
-- thiếu thành phần event_day trong composite partition key.
token(tenant_id)

-- Sai mục đích: đây là clustering column, không phải partition key.
token(occurred_at)
```

Ba dòng trên chỉ nhằm minh họa biểu thức, **không phải một câu CQL độc lập để chạy**. Với nhu cầu tra cứu một partition đã biết, hãy viết `tenant_id = ... AND event_day = ...`, không đổi sang token range chỉ vì có hàm `token()`.

## 5. Quét một khoảng TOKEN bằng CQL

### 5.1. Điều kiện trên token khác điều kiện trực tiếp trên partition key

Điều kiện phạm vi trên thành phần partition key:

```sql
-- Không phải truy vấn dải ngày hợp lệ với composite partition key.
SELECT tenant_id, event_day, event_id
FROM events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day >= '2026-11-20';
```

không tương đương điều kiện trên token:

```sql
-- Ví dụ CQL về dải token: chỉ dùng khi đã xác nhận Murmur3Partitioner.
SELECT tenant_id, event_day, occurred_at, event_id, event_type
FROM events_by_tenant_day
WHERE token(tenant_id, event_day) >= -9223372036854775808
  AND token(tenant_id, event_day) < 0;
```

Truy vấn thứ hai quét các partition có **token nằm trong nửa âm của miền số có dấu**, không phải “các tenant hay ngày nhỏ hơn một giá trị nghiệp vụ”. Với dữ liệu lab, chưa thể khẳng định partition nào rơi vào dải này nếu không tính token thực tế.

### 5.2. Chia miền Murmur3 thành hai phạm vi không chồng lấn

Đối với minh họa Murmur3 trên miền số nguyên có dấu 64 bit, có thể chia:

```text
Giá trị nhỏ nhất             0                     Giá trị lớn nhất
-9223372036854775808        |                     9223372036854775807
           [----------------) [------------------------------]
             Range A                    Range B

Range A: token >= MIN AND token < 0
Range B: token >= 0
```

Hai câu truy vấn CQL tương ứng:

```sql
-- Range A: từ MIN (bao gồm) đến trước 0.
SELECT tenant_id, event_day, occurred_at, event_id, event_type
FROM events_by_tenant_day
WHERE token(tenant_id, event_day) >= -9223372036854775808
  AND token(tenant_id, event_day) < 0;

-- Range B: từ 0 (bao gồm) đến hết miền số có dấu.
SELECT tenant_id, event_day, occurred_at, event_id, event_type
FROM events_by_tenant_day
WHERE token(tenant_id, event_day) >= 0;
```

Đặc tính của **hai dải số được tự định nghĩa**:

- Token âm thuộc **chính xác Range A**.
- Token bằng 0 thuộc **chính xác Range B**.
- Token dương thuộc **chính xác Range B**.
- Không có lỗ trống tại 0 và không có trùng lặp giữa hai dải.

Ở đây **không dùng điều kiện cận trên lớn hơn `Long.MAX_VALUE`** vì giá trị như vậy không biểu diễn được dưới dạng token `bigint` thông thường. Range cuối dùng điều kiện `>= 0` mà không thêm cận trên.

**Quan trọng:** Cassandra có các quy tắc đặc biệt ở token minimum và vòng ring; khi sử dụng metadata `TokenRange` của driver, quy ước cận của nó **khác** các dải `[start, end)` do chúng ta tự chọn. Phần 7 giải thích cách tránh trộn hai quy ước.

### 5.3. Kiểm tra coverage với dữ liệu lab

Vì có tổng cộng 8 dòng trong 4 partition, kết quả đầy đủ của **Range A cộng Range B** phải có **8 dòng** khi không có ghi/xóa đồng thời và cluster đang dùng partitioner giả định.

Có thể đếm số dòng trong mỗi dải trên lab nhỏ:

```sql
SELECT count(*) AS rows_in_negative_range
FROM events_by_tenant_day
WHERE token(tenant_id, event_day) >= -9223372036854775808
  AND token(tenant_id, event_day) < 0;

SELECT count(*) AS rows_in_nonnegative_range
FROM events_by_tenant_day
WHERE token(tenant_id, event_day) >= 0;
```

Điều cần kiểm tra là:

```text
rows_in_negative_range + rows_in_nonnegative_range = 8
```

**Không có số cụ thể cố định cho từng nửa dải** trong bài: chúng phụ thuộc token băm của composite partition keys, và hai dải không được bảo đảm chứa số partition bằng nhau trên tập mẫu nhỏ. `COUNT(*)` trên token range **vẫn là quét dữ liệu**, vì vậy đừng dùng câu đếm như bước kiểm tra thường xuyên trên production lớn.

## 6. Chia thành nhiều khoảng token: không hở, không trùng

### 6.1. Quy tắc khoảng nửa mở tự quản lý

Giả sử ứng dụng xây các mốc token tăng dần:

```text
B0 < B1 < B2 < ... < Bn
```

Thì có thể lập các khoảng:

```text
[B0, B1)
[B1, B2)
...
[B(n-1), Bn)
```

Mọi khoảng dùng `token >= lower AND token < upper`. Điểm bằng ranh giới `Bi` thuộc **khoảng bắt đầu tại Bi**, không nằm trong khoảng trước. Nếu `B0` là min của miền và muốn quét cả miền, khoảng cuối cần bao gồm đến hết miền; với số nguyên có dấu 64 bit, có thể dùng **dải cuối chỉ có cận dưới** để phủ phần còn lại.

Ví dụ chia Murmur3 theo ba dải số:

```text
Range 1: [Long.MIN_VALUE, -1000)
Range 2: [-1000, 1000)
Range 3: [1000, Long.MAX_VALUE]
```

CQL:

```sql
-- Range 1
SELECT tenant_id, event_day, occurred_at, event_id
FROM events_by_tenant_day
WHERE token(tenant_id, event_day) >= -9223372036854775808
  AND token(tenant_id, event_day) < -1000;

-- Range 2
SELECT tenant_id, event_day, occurred_at, event_id
FROM events_by_tenant_day
WHERE token(tenant_id, event_day) >= -1000
  AND token(tenant_id, event_day) < 1000;

-- Range 3 (không dùng giá trị lớn hơn Long.MAX_VALUE).
SELECT tenant_id, event_day, occurred_at, event_id
FROM events_by_tenant_day
WHERE token(tenant_id, event_day) >= 1000;
```

Đây là **ví dụ cách chia không trùng về mặt ranh giới** chứ không phải cách tối ưu tải: ba khoảng có độ rộng token cực kỳ khác nhau, vì vậy không thích hợp để phân phối công việc đều.

### 6.2. Tránh overflow khi tính boundary

Nếu cần chia miền số 64 bit thành `N` phần, đừng tính trung điểm bằng:

```java
// KHÔNG dùng: độ rộng toàn miền tràn kiểu long.
long width = Long.MAX_VALUE - Long.MIN_VALUE;
long midpoint = Long.MIN_VALUE + width / 2; // suy ra sai
```

Dùng `BigInteger` hoặc API token range của driver để tính boundary. Với bài toán chia đủ miền số có dấu, biểu diễn cận trên **exclusive** dưới dạng `2^63` trong nội bộ tính toán, rồi chuyển khoảng cuối thành câu CQL **không có cận trên**. Đảm bảo các boundary phân biệt, không tạo khoảng rỗng và không tự ép `2^63` về `long` gây overflow.

### 6.3. Không tách một partition bằng token

Ví dụ partition `(A, 2026-11-20)` có ba dòng. Nếu token của partition đó nằm trong Range A, **cả ba dòng** đều nằm trong Range A. Việc tăng số token ranges từ 2 lên 20 **không** tách ba dòng ra nhiều worker.

Trong trường hợp một partition quá lớn khiến một task chậm:

- Có thể quét **clustering range** cho chính partition đó theo một chiến lược phụ riêng nếu schema cho phép.
- Hoặc thiết kế bucket nhỏ hơn trong lần xây mô hình dữ liệu tiếp theo.
- Không suy rằng token scan xử lý được mọi hot partition chỉ nhờ thêm range workers.

## 7. Quy ước TokenRange của Java driver và vòng token ring

### 7.1. TokenRange trong metadata thường là (start, end]

Token ring có tính **vòng**. Khi lấy ranges từ token metadata của Java Driver 4.x, `TokenRange` biểu diễn khoảng:

```text
(start, end]
```

tức **loại trừ start**, **bao gồm end**. Đây là quy ước của cấu trúc metadata và ownership range, khác với dải `[start,end)` được tự xây ở mục 5–6.

Ví dụ:

```text
Range metadata A: (10, 20]  => token > 10 và token <= 20
Range metadata B: (20, 30]  => token > 20 và token <= 30

Token = 20 chỉ thuộc A, không thuộc B.
```

Nếu chọn sử dụng trực tiếp `TokenRange` từ driver, hãy giữ đúng **một quy ước cận** trong toàn bộ job:

```sql
-- CQL mô tả một TokenRange không vòng: (start, end].
SELECT tenant_id, event_day, occurred_at, event_id
FROM events_by_tenant_day
WHERE token(tenant_id, event_day) > 10
  AND token(tenant_id, event_day) <= 20;
```

Đừng biến metadata `(10,20]` thành `>= 10 AND < 20`; như vậy token đúng ở đầu/cuối ranh giới sẽ được phân công sai khi ghép nhiều range.

### 7.2. Vòng ring và unwrap()

Trong ring, một khoảng có thể **quay qua điểm kết thúc miền token**. Ví dụ về mặt khái niệm:

```text
Ring: ... 80 -> 90 -> MAX -> MIN -> ... -> -50 -> -40 ...

TokenRange (80, -40] đi qua chỗ quay vòng.
```

**CQL token range thông thường không tự xử lý một khoảng wrap-around như một dải số tuyến tính.** Với Java Driver `TokenRange`, dùng `unwrap()` để tách thành một hoặc hai khoảng không vòng rồi mới xây CQL theo cận đúng. Khi xử lý minimum token, full-ring range và những khoảng rỗng, sử dụng API token range thay vì tự suy từ dấu âm/dương của hai cận.

Trong Java Driver 4.x:

- `TokenMap.getTokenRanges()` lấy các range mô tả ring.
- `TokenRange.unwrap()` tách range wrap-around.
- `TokenRange.splitEvenly(k)` chia theo **độ rộng miền token**, **không** theo số partition hoặc bytes thực tế.
- `TokenMap` và topology/schema metadata cần được lấy từ session đang hoạt động và làm mới đúng quy định khi topology đổi.

**Quan trọng:** `getTokenRanges(keyspace, replica)` thể hiện các range có bản sao trên một node. Nếu lịch xử lý quét toàn bộ dữ liệu **một lần**, đừng dùng hợp danh sách replica ranges từ mọi node như danh sách task không trùng: vì replication, chúng có thể chồng lấn. Cần xây một tập token intervals **không trùng** cho toàn bộ logical token space rồi phân công worker.

### 7.3. Chia đều token không đồng nghĩa chia đều dữ liệu

Token hash phân phối partition keys, nhưng mỗi partition có kích thước khác nhau. Ví dụ:

| Range | Số partition | Tổng dòng | Nhận xét |
| --- | ---: | ---: | --- |
| R1 | 10.000 | 100.000 | Nhiều partition nhỏ. |
| R2 | 9.000 | 900.000 | Một vài partition lớn. |
| R3 | 11.000 | 120.000 | Số partition cao nhưng ít dòng. |

Ba range có thể rộng bằng nhau trong token space nhưng thời gian scan rất khác nhau. Khi cần cân bằng tải, đo:

- Số partition và kích thước partition thực tế.
- Bytes đã đọc/xử lý, SSTable và tombstone scan.
- Thời gian mỗi range, throughput và replica/coordinator load.
- Token range bị chậm kéo dài; cân nhắc chia tiếp dải nếu không có một partition quá lớn chi phối.

Đừng đặt mặc định “100 range chạy đồng thời = nhanh gấp 100” trên cluster: concurrency quá cao có thể đè I/O, làm tăng compaction backlog, timeout và tail latency của dịch vụ chính.

## 8. So sánh TOKEN scan với WHERE theo khóa

| Nhu cầu | Mẫu truy vấn phù hợp | Vì sao |
| --- | --- | --- |
| Lấy lịch sử tenant A ngày 20 | `tenant_id = A AND event_day = D` | Point-partition read định vị một partition. |
| Lấy một khoảng thời gian trong ngày | Full partition key + range trên `occurred_at` | Chọn lát cắt theo clustering order. |
| Lấy ba ngày đã biết của tenant | `event_day IN (D1,D2,D3)` sau `tenant_id = A` | Đọc danh sách partition cụ thể. |
| Batch export toàn bảng, có giới hạn tải | `token(tenant_id,event_day)` theo các dải | Phân chia công việc trên nhiều partition/token range. |
| Phân trang thời gian mới nhất cho tenant | Clustering order + paging state/keyset cursor | Token không sắp các sự kiện theo thời gian. |
| Tìm mọi sự kiện `VIEW` toàn cluster | Bảng/index/tổng hợp theo truy vấn | Token range vẫn phải đọc rộng rồi lọc nếu không có đường truy cập phù hợp. |

Một truy vấn token range không phải truy vấn “có sẵn partition key” theo nghĩa point lookup. Nó có thể bao phủ rất nhiều partition; vì vậy chạy thường xuyên từ request HTTP đồng bộ là lựa chọn rủi ro nếu chưa đo kỹ.

## 9. LIMIT, page size và checkpoint không thay thế nhau

### 9.1. LIMIT không tạo một lượt quét hoàn chỉnh

```sql
SELECT tenant_id, event_day, occurred_at, event_id
FROM events_by_tenant_day
WHERE token(tenant_id, event_day) >= 0
LIMIT 2;
```

Câu này chỉ trả **tối đa hai dòng**, không có nghĩa “đã hoàn tất quét các partition token không âm”. Trong batch export, nếu task cần xử lý **toàn bộ range**, hãy duyệt hết các page hoặc sử dụng phương thức resume/checkpoint đúng thiết kế, không xem `LIMIT 2` là một chunk tự động có thể lấy chunk kế tiếp bằng `OFFSET`.

### 9.2. Page size và paging state

Driver `setPageSize(n)` yêu cầu fetch theo những page có kích thước mục tiêu, còn **paging state** biểu diễn trạng thái tiếp tục của *cùng truy vấn*.

| Khái niệm | Tác dụng | Không bảo đảm |
| --- | --- | --- |
| **Token range** | Đơn vị phân chia partition space cho task. | Không giới hạn chính xác số dòng/bytes mỗi task. |
| **Page size** | Điều tiết số dòng trả qua một đợt fetch. | Không phải giới hạn tổng số dòng hay một partition. |
| **Paging state** | Tiếp tục vị trí đọc của cùng câu CQL/bind values. | Không phải snapshot bất biến, không dùng thay đổi query tùy ý. |
| **Checkpoint ứng dụng** | Lưu tiến độ task/phạm vi/page đã xử lý. | Không tự tạo xử lý exactly-once nếu sink không idempotent. |

Một paging state **không được dùng lại** cho câu truy vấn với token bounds khác, hoặc tự chỉnh sửa rồi đoán vị trí tiếp theo. Token từ `token(pk)` cũng **không chứa clustering offset**: nếu một partition có nhiều dòng, chỉ checkpoint token cuối cùng có thể khiến job bỏ sót các dòng chưa xử lý của partition đó khi resume.

### 9.3. Khôi phục task sau lỗi

Chiến lược đơn giản, ưu tiên dễ xác minh:

1. Ghi nhận task `range_id`, cận dưới/trên, trạng thái và phiên bản cấu hình.
2. Chạy query **cho đúng range** với page size có giới hạn.
3. Xử lý từng record với sink **idempotent** theo **full primary key** (và phiên bản/sự kiện khi cần).
4. Chỉ checkpoint trạng thái tiếp tục **sau khi đã xác nhận sink lưu thành công** những record thuộc page đã hoàn tất.
5. Khi lỗi/timeout hoặc không thể tin cậy paging state, có thể **quét lại toàn bộ range** từ đầu và loại trùng ở sink.
6. Đánh dấu range hoàn tất chỉ sau khi đã xử lý hết các trang theo giao thức.

Ranh giới và paging state phải được lưu với kiểm tra tính toàn vẹn, bảo vệ token do client cung cấp, và ràng buộc vào query, keyspace, bảng và các tham số tương ứng. Đừng coi checkpoint chỉ gồm “last token” là đủ khi job xử lý từng dòng của một partition.

**At-least-once vs exactly-once:** Cách dễ vận hành là chấp nhận **at-least-once processing** khi retry và bảo vệ sink bằng idempotency/deduplication. Không tuyên bố exactly-once chỉ nhờ driver paging state.

### 9.4. Dữ liệu thay đổi trong khi quét

Token range và paging **không cung cấp snapshot toàn bảng**. Trong lúc job chạy:

- Ghi mới vào một range đã quét có thể không xuất hiện trong kết quả.
- Xóa/TTL có thể khiến record biến mất trước khi range được quét.
- Replica chưa hội tụ có thể làm kết quả khác nhau theo consistency level.
- Topology thay đổi khiến placement/replica ownership khác, dù cách băm partition key vẫn giữ nguyên nếu partitioner không đổi.

Nếu cần xuất dữ liệu “tại một thời điểm”, phải có quy trình riêng: chụp/sao lưu snapshot, khóa cửa sổ dữ liệu, CDC hoặc cơ chế đối soát phù hợp; không suy rằng SELECT qua token range là transaction snapshot toàn cluster.

## 10. Chiến lược chạy batch scan an toàn

### 10.1. Điều phối theo range, không quét vô hạn trong một request

Một lịch chạy có thể biểu diễn:

```text
Planner
  |
  +--> R01 [lower, upper) --> worker #1 --> sink
  +--> R02 [lower, upper) --> worker #2 --> sink
  +--> R03 [lower, upper) --> pending
  +--> ...
  |
  +--> checkpoint store: trạng thái, attempt, page, offset, lỗi
  |
  +--> limiter: tối đa K ranges đang chạy, tối đa Q requests/giây
```

Gợi ý vận hành:

- **Giới hạn concurrency:** bắt đầu nhỏ, tăng dựa trên đo độ trễ và resource usage.
- **Rate limit/throttling:** bảo vệ cluster khỏi batch job gây ảnh hưởng traffic chính.
- **Backoff:** trên timeout/unavailable, retry có giới hạn và jitter; tránh bão retry.
- **Timeout theo phạm vi:** nếu một range quá dài, giảm độ rộng range hoặc kiểm tra partition lớn, không chỉ tăng timeout vô hạn.
- **Tải lệch:** theo dõi những ranges lâu hơn và đánh giá chia lại phần chưa xử lý có an toàn không.
- **Scheduling:** chạy ngoài giờ cao điểm nếu nghiệp vụ cho phép, chia job thành các đợt.

### 10.2. Theo dõi metric nào?

| Nhóm metrics | Mục đích |
| --- | --- |
| Range progress: `scheduled/running/completed/failed` | Biết độ bao phủ và khả năng retry. |
| Rows và bytes xử lý mỗi range/page | Nhận diện range lệch tải, partition lớn. |
| p50/p95/p99 latency, throughput | Đánh giá tác động batch đến đọc thường ngày. |
| Read timeout, unavailable, retries, speculative executions | Xác định quá tải và health của replicas. |
| Tombstone warnings, SSTable read amplification, compaction backlog | Giải thích vì sao range có ít kết quả vẫn chậm. |
| Tracing chọn lọc, node CPU/disk/network | Định vị nút nghẽn thật, không chỉ phỏng đoán bằng độ rộng token. |

Quét token range là workload đọc rộng. Replication factor cao hơn không làm số partition logic tăng, nhưng consistency và replica coordination có thể ảnh hưởng độ trễ. Tương tự, repair/compaction có thể cạnh tranh tài nguyên với batch scan; cần lịch chạy và giám sát.

### 10.3. Chọn khoảng theo token ring metadata thay vì chia số tùy ý

Nếu cluster có vnode và nhiều node, một cách lập kế hoạch chuyên nghiệp là:

1. Lấy token map/topology qua driver, xác định partitioner và token ranges của ring.
2. Chọn **tập range không giao nhau** cho toàn bộ logical token space.
3. Dùng `splitEvenly` hoặc tự chia theo metric thu thập trước đó để cân bằng work, **không** nhầm split theo token với split theo bytes.
4. Unwrap các khoảng đi vòng, xây CQL theo đúng cận và kiểu token.
5. Thực thi dưới một concurrency limit và lưu checkpoint từng range.

Không lấy tất cả range bản sao của mọi node rồi đưa mỗi bản sao thành một task toàn bảng, vì data replication sẽ khiến công việc chồng lấn. Token metadata xác định node sở hữu/replica, còn hệ quét cần một **coverage plan duy nhất** cho dữ liệu logic.

## 11. Java Driver: quét hai nửa miền Murmur3

Ví dụ sau dùng **Apache Cassandra Java Driver 4.x** và Java 15+ (text blocks). Giả định `CqlSession session` đã kết nối keyspace `cassandra_token_lab` và cluster sử dụng **Murmur3Partitioner**. Đoạn mã minh họa **quét đồng bộ tuần tự**, thích hợp lab; trong production cần scheduler/checkpoint/idempotent sink như mục 9–10.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.LocalDate;
import java.util.UUID;

// Giả định biến session đã được khởi tạo và kết nối đúng keyspace.
PreparedStatement negativeHalf = session.prepare("""
    SELECT tenant_id, event_day, occurred_at, event_id, event_type
    FROM events_by_tenant_day
    WHERE token(tenant_id, event_day) >= ?
      AND token(tenant_id, event_day) < ?
    """);

PreparedStatement nonnegativeHalf = session.prepare("""
    SELECT tenant_id, event_day, occurred_at, event_id, event_type
    FROM events_by_tenant_day
    WHERE token(tenant_id, event_day) >= ?
    """);

BoundStatement first = negativeHalf.bind(Long.MIN_VALUE, 0L)
    .setPageSize(128);
BoundStatement second = nonnegativeHalf.bind(0L)
    .setPageSize(128);

long scannedRows = 0;
for (BoundStatement task : new BoundStatement[] { first, second }) {
    ResultSet result = session.execute(task);
    for (Row row : result) {
        UUID tenantId = row.getUuid("tenant_id");
        LocalDate day = row.getLocalDate("event_day");
        UUID eventId = row.getUuid("event_id");

        // Lab: hiển thị; production: thay bằng sink idempotent,
        // quản lý checkpoint và backpressure.
        System.out.printf("%s %s %s%n", tenantId, day, eventId);
        scannedRows++;
    }
}
System.out.println("Rows scanned: " + scannedRows); // 8 với dữ liệu lab
```

**Ý nghĩa của code:**

- `Long.MIN_VALUE` và `0L` là bind values kiểu `bigint` dành cho Murmur3 token; **không** tái sử dụng đoạn code trên partitioner khác.
- Truy vấn đầu chọn khoảng `[MIN, 0)`, truy vấn sau chọn `[0, MAX]`. Hai truy vấn có tập token không giao nhau theo cách chia đã chọn.
- `setPageSize(128)` chỉ điều tiết fetch; vòng lặp trên `ResultSet` có thể tự tải thêm page cho đến khi hoàn tất. Nó **không** giới hạn batch ở 128 dòng.
- `scannedRows = 8` là kỳ vọng trên dữ liệu cố định ở lab, không phải số bắt buộc trên production hoặc khi có dữ liệu ghi/xóa đồng thời.
- Trong code production, không in hàng triệu dòng ra console, không giữ toàn bộ `ResultSet` trong một collection khổng lồ, và phải quản lý timeout/retry/paging có kiểm soát.

### 11.1. Khi dùng TokenMap thay vì tự chọn hai dải

Trong driver 4.x, có thể đọc metadata như sau:

```java
import com.datastax.oss.driver.api.core.metadata.TokenMap;
import com.datastax.oss.driver.api.core.metadata.token.TokenRange;
import java.util.Optional;

Optional<TokenMap> maybeTokenMap = session.getMetadata().getTokenMap();
if (maybeTokenMap.isEmpty()) {
    throw new IllegalStateException("Token metadata chua san sang");
}

TokenMap tokenMap = maybeTokenMap.get();
for (TokenRange ringRange : tokenMap.getTokenRanges()) {
    for (TokenRange linear : ringRange.unwrap()) {
        // Mỗi linear dùng quy ước (start, end] theo TokenRange.
        // Xây CQL với token(pk) > start AND token(pk) <= end,
        // bind đúng kiểu token của partitioner, kiểm tra MIN/full-ring.
        // Đưa task vào scheduler thay vì quét đồng thời không giới hạn.
        System.out.println(linear);
    }
}
```

Đây là **mẫu lấy metadata**, chưa phải một chương trình scanner hoàn chỉnh: cần chọn tập intervals không trùng, kiểm tra full-ring/minimum, giới hạn parallelism, giữ checkpoint và bảo đảm query boundary tương ứng kiểu token thực tế. Tên API có thể thay đổi giữa các phiên bản driver; kiểm tra tài liệu của bản đang dùng.

## 12. Các lỗi thường gặp khi dùng TOKEN

| Quan niệm hoặc truy vấn | Vấn đề | Cách xử lý |
| --- | --- | --- |
| “`TOKEN` trả dữ liệu theo ngày tăng dần.” | Token băm partition key, không giữ thứ tự ngày nghiệp vụ. | Dùng clustering column/date bucket theo nhu cầu đọc. |
| `token(tenant_id)` trên bảng có partition key `(tenant_id,event_day)` | Thiếu thành phần của composite partition key. | Dùng `token(tenant_id,event_day)`. |
| Chia một partition lớn thành nhiều token range | Mọi dòng trong partition có cùng token. | Chia bằng clustering range hoặc bucket mới. |
| Dùng `>= start AND <= end` cho cả hai range kề nhau | Token ở điểm chung có thể thuộc cả hai. | Dùng cận nửa mở nhất quán hoặc driver `(start,end]`. |
| Dùng `> start AND < end` cho hai range kề nhau | Token ở boundary có thể bị bỏ sót. | Chọn rõ điểm nào đóng, điểm nào mở. |
| Trộn `TokenRange (start,end]` với CQL `[start,end)` | Sai cận sẽ gây trùng/bỏ sót. | Giữ đúng một quy ước cho mỗi kế hoạch. |
| Viết một range wrap-around như một khoảng số bình thường | CQL không tự unroll vùng vòng ring. | Dùng `unwrap()` hoặc chia thành các dải tuyến tính. |
| `splitEvenly(16)` nghĩa 16 task có cùng số rows | Chỉ chia độ rộng token, không chia dung lượng. | Theo dõi skew/bytes và điều chỉnh lịch chạy. |
| `LIMIT 100` có nghĩa đã quét hết 100 dòng của một range rồi xong | Nó giới hạn kết quả, có thể còn dữ liệu chưa quét. | Duyệt paging đến kết thúc hoặc resume chính xác. |
| Checkpoint chỉ lưu token cuối | Không biết đang ở dòng clustering nào trong partition. | Lưu paging state phù hợp hoặc quét lại range với sink idempotent. |
| Chạy tất cả ranges của mỗi replica như các task độc lập | Các replica ranges chồng lấn do replication. | Lập một coverage plan duy nhất cho logical ring. |
| Token scan tạo snapshot nhất quán toàn cluster | Ghi/xóa/TTL/repair có thể thay đổi dữ liệu giữa các lần đọc. | Dùng cơ chế snapshot/CDC/đối soát phù hợp. |

## 13. Bài tập thực hành và đáp án

### Bài 1. Đếm partition và dòng theo token

**Đề:** Bảng lab có 4 partition, 8 dòng. Nếu một partition chứa ba dòng và có token thuộc Range A, mấy dòng của partition ấy thuộc Range A? Có thể thuộc cả Range B không?

**Đáp án:** **Cả ba dòng** cùng thuộc Range A vì token được tính từ cùng full partition key; nếu hai range không giao nhau thì partition ấy **không** thể có dòng ở Range B. Token không phụ thuộc clustering columns.

### Bài 2. Tìm lỗi tại ranh giới

**Đề:** Một job chia hai range:

```text
R1: token >= -1000 AND token <= 0
R2: token >= 0 AND token <= 1000
```

Điểm nào sai?

**Đáp án:** Token bằng `0` thuộc **cả hai** range. Có thể sửa thành:

```text
R1: token >= -1000 AND token < 0
R2: token >= 0 AND token <= 1000
```

Nếu muốn quét **toàn miền số**, phải bổ sung phần còn lại ngoài đoạn `[-1000,1000]` hoặc xác định các range khác; sửa ranh giới trùng không tự tạo coverage toàn ring.

### Bài 3. Hai nửa miền token

**Đề:** Viết hai truy vấn để chia toàn miền signed 64-bit của Murmur3 thành hai dải âm và không âm.

**Đáp án:**

```sql
SELECT tenant_id, event_day, occurred_at, event_id
FROM events_by_tenant_day
WHERE token(tenant_id, event_day) >= -9223372036854775808
  AND token(tenant_id, event_day) < 0;

SELECT tenant_id, event_day, occurred_at, event_id
FROM events_by_tenant_day
WHERE token(tenant_id, event_day) >= 0;
```

Khi dữ liệu không đổi, tổng dòng từ hai truy vấn bằng số dòng của toàn bộ bảng lab (**8**).

### Bài 4. Vì sao split theo token vẫn lệch thời gian?

**Đề:** Hai token ranges bằng nhau về độ rộng. Range A có 10.000 partition nhỏ, Range B có một partition chứa 5 triệu dòng. Tại sao A và B không nhất thiết chạy xong cùng lúc?

**Đáp án:** Chi phí quét phụ thuộc số dòng/bytes, tombstone, SSTable, replica và I/O. `splitEvenly` cân bằng **độ rộng miền token**, không cân bằng khối lượng dữ liệu thực. Partition rất lớn vẫn nằm trong **một range**, không thể chia bằng token.

### Bài 5. Checkpoint an toàn hơn

**Đề:** Worker đã gửi 500 dòng sang sink rồi timeout. Vì sao chỉ lưu “last token” và chạy `token(pk) > lastToken` có thể bỏ dữ liệu?

**Đáp án:** Một token đại diện cho **toàn partition**, có thể còn các dòng clustering chưa được gửi. Khi bỏ qua token đó, job bỏ sót phần còn lại. Có thể dùng paging state đúng query và checkpoint sau xác nhận sink, hoặc **quét lại cả range** với sink idempotent để tránh bỏ sót do retry.

### Bài 6. Token range có thay thế truy vấn nghiệp vụ không?

**Đề:** Một endpoint cần “20 sự kiện gần nhất của tenant A trong ngày 20”. Nên dùng `WHERE token(tenant_id,event_day) >= X LIMIT 20`?

**Đáp án:** **Không.** Token range không định vị riêng tenant/ngày, không bảo đảm thứ tự theo thời gian và có thể đọc nhiều partition. Dùng `WHERE tenant_id = A AND event_day = D ORDER BY occurred_at DESC LIMIT 20` với clustering order phù hợp, hoặc bảng đọc được thiết kế cho yêu cầu ấy.

## 14. Checklist trước khi triển khai token-range scan

1. **Đúng mục tiêu:** Đây là batch quét nhiều partition, không phải API tra cứu một partition hay timeline?
2. **Đúng khóa:** `token()` đã dùng **toàn bộ partition key** theo đúng thứ tự cột chưa?
3. **Đúng partitioner:** Đã xác định Murmur3 hay loại khác và kiểu token/boundary tương ứng chưa?
4. **Coverage:** Các ranges có phủ toàn bộ miền cần quét, không chồng lấn, không bỏ mất boundary và đã xử lý wrap-around/min token chưa?
5. **Skew:** Đã hiểu một partition luôn nằm trong một token range và chia đều token không đồng nghĩa chia đều bytes chưa?
6. **Giới hạn tải:** Có concurrency limit, throttling, backoff, timeout, metrics và kế hoạch khi một range quá lớn không?
7. **Paging/checkpoint:** Có phân biệt `LIMIT`, page size, paging state và checkpoint? Sink đã idempotent khi retry chưa?
8. **Dữ liệu biến động:** Có chính sách ghi/xóa/TTL trong lúc quét, tính mới của dữ liệu và đối soát/replay khi cần không?
9. **Replication/consistency:** Có giới hạn read pressure lên coordinator/replica và tránh quét lặp replica ranges không?
10. **Ứng dụng Java:** Đã bind đúng kiểu token, sử dụng API token map của phiên bản driver, giữ authorization và không làm batch ảnh hưởng API nóng chưa?

**Ghi nhớ:** `TOKEN` giúp chia một công việc quét **theo vị trí phân vùng trên token ring**. Tính đúng của job nằm ở **coverage không hở/không trùng** và khả năng resume; hiệu năng nằm ở **khối lượng dữ liệu thực tế, concurrency và sức khỏe replica**. Token range không thay thế partition key trong truy vấn nghiệp vụ, không chia nhỏ một partition lớn và không tự tạo snapshot nhất quán toàn cluster.

## Tài liệu tham khảo

- [Apache Cassandra Documentation — CQL Data Manipulation: WHERE với TOKEN](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html)
- [Apache Cassandra Documentation — CQL Changes: TOKEN trong điều kiện partition key](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/changes.html)
- [Apache Cassandra Documentation — Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html)
- [DataStax Java Driver 4.x — Token metadata và TokenMap](https://docs.datastax.com/en/developer/java-driver/4.2/manual/core/metadata/token/index.html)
- [DataStax Java Driver 4.x — TokenRange API: range boundaries và unwrap](https://docs.datastax.com/en/drivers/java/4.6/com/datastax/oss/driver/api/core/metadata/token/TokenRange.html)
- [Apache Cassandra Java Driver 4.x — Paging](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/paging/index.html)
