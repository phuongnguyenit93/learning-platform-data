# Kiểm chứng truy vấn bằng trace và bộ dữ liệu có trường hợp biên

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Dùng **query tracing** để quan sát đường thực thi một câu `SELECT` trên Apache Cassandra, thay vì chỉ suy đoán từ cú pháp.
2. Phân biệt **truy vấn trả đúng kết quả**, **truy vấn có đường đọc phù hợp** và **truy vấn đáp ứng mục tiêu hiệu năng** — ba điều cần kiểm tra riêng.
3. Tạo một bộ dữ liệu CQL có **partition rỗng, partition ít/nhiều hàng, clustering timestamp trùng, cột thiếu, giới hạn khoảng và nhiều partition**.
4. Viết bộ ca kiểm thử có kỳ vọng rõ ràng cho `WHERE`, `ORDER BY`, `LIMIT`, `PER PARTITION LIMIT`, `ALLOW FILTERING` và phân trang.
5. Đọc kết quả `TRACING ON` trong `cqlsh`, tìm tracing session và hiểu những gì trace **có thể** và **không thể** chứng minh.
6. Bật tracing có chọn lọc trong **Java Driver 4.x**, thu tracing ID, phân biệt page hiện tại với các page tiếp theo.
7. Thử các ca **INSERT, DELETE, UPDATE, TTL và paging** mà không giả định chuỗi nhiều lần đọc tạo snapshot bất biến.
8. Xây checklist kiểm chứng trước khi đưa API Cassandra vào production: độ đúng, phạm vi quét, tính nhất quán, tải và bảo mật.

Bài thuộc chương **SELECT và phân trang** của mô-đun `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Mục tiêu xuyên suốt của mô-đun là hiểu cơ sở dữ liệu wide-column phân tán: partition key, thiết kế bảng theo truy vấn, replication/consistency đọc ghi, CQL, compaction, repair, xử lý lỗi và tích hợp Java. Tracing là công cụ hỗ trợ quan sát các thành phần ấy, nhưng **không thay thế được bộ dữ liệu kiểm thử có trường hợp biên hoặc benchmark trên tải đại diện**.

## 1. Ba câu hỏi phải được kiểm chứng độc lập

Giả sử một API muốn lấy “ba sự kiện mới nhất trong ngày của một tài khoản”. Một truy vấn có vẻ ngắn:

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = ?
  AND event_day = ?
ORDER BY occurred_at DESC, event_id DESC
LIMIT 3;
```

Để kết luận truy vấn đạt yêu cầu, ta cần ba loại bằng chứng:

| Câu hỏi | Bằng chứng phù hợp | Điều không đủ để kết luận |
| --- | --- | --- |
| **Kết quả có đúng không?** | Bộ dữ liệu có giá trị mong đợi, so sánh primary key/giá trị/thứ tự | “Chạy không báo lỗi” |
| **Phạm vi đọc có hợp lý không?** | Phân tích partition key, clustering range; trace và metrics | “Chỉ trả ba dòng” |
| **Đủ nhanh/ổn định không?** | Benchmark p50/p95/p99, throughput, timeout, tải replica trên dữ liệu đại diện | “Một lần chạy lab mất vài ms” |

Một truy vấn dùng `ALLOW FILTERING` có thể **đúng hai dòng kết quả** nhưng quét một partition rất lớn. Ngược lại, một câu `SELECT` có đường đọc rất gọn vẫn có thể trả **sai thứ tự** khi người viết quên clustering key thứ hai dùng để phân biệt timestamp trùng.

Vì vậy, quy trình của bài là:

```text
Xác định hợp đồng truy vấn
      |
      v
Tạo dữ liệu thường + trường hợp biên
      |
      v
Chạy CQL, đối chiếu row keys và thứ tự
      |
      v
Bật trace có chọn lọc để quan sát đường đọc
      |
      v
So sánh trace + metrics, thử paging và dữ liệu biến động
      |
      v
Đánh giá trên workload gần production trước khi phát hành
```

**Nguyên tắc:** Một trace không tự nói cho ta truy vấn nghiệp vụ có đúng hay không; một bộ test đúng kết quả cũng không tự chứng minh truy vấn vận hành rẻ.

## 2. Những thông tin cần cố định trước khi thử

Kết quả và chi phí của cùng câu CQL có thể thay đổi theo cấu hình cluster và trạng thái dữ liệu. Nên ghi lại:

| Nhóm | Những gì cần biết | Vì sao |
| --- | --- | --- |
| Schema | Partition key, clustering columns, clustering order, kiểu cột, index | Quyết định điều kiện nào định vị dữ liệu. |
| CQL | Query string, bind values, projection, `ORDER BY`, `LIMIT` | Xác định hợp đồng kết quả chính xác. |
| Dữ liệu | Bao nhiêu partition, kích thước lớn/nhỏ, timestamp trùng, null, TTL, tombstone | Tạo các trường hợp mà dữ liệu đẹp thường bỏ sót. |
| Phiên bản | Cassandra, Java Driver, native protocol | Một số hành vi và trace event thay đổi theo phiên bản. |
| Phân tán | Replication strategy/factor, datacenter, consistency level | Ảnh hưởng replica được liên hệ và độ mới dữ liệu quan sát. |
| Vận hành | Cache, compaction, repair, QPS, số truy vấn đồng thời | Ảnh hưởng read amplification và tail latency. |

Bài dùng **Cassandra lab một node** để kiểm tra kết quả CQL một cách tái lập. Nó **không thể mô phỏng đầy đủ** tình huống replica chưa hội tụ, mất node hay `LOCAL_QUORUM` trên cluster nhiều node. Những tính chất phân tán phải được kiểm tra riêng trên môi trường có topology tương ứng.

## 3. Bộ dữ liệu chuẩn: mười dòng, ba partition và trường hợp biên

### 3.1. Tạo keyspace và bảng

Hãy dùng **một keyspace chỉ dành cho thực hành**. Các lệnh sau không được chạy trên bảng production có dữ liệu thật.

```sql
-- Lab một node: RF=1/SimpleStrategy chỉ dành cho thực hành.
CREATE KEYSPACE IF NOT EXISTS cassandra_trace_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

USE cassandra_trace_lab;

CREATE TABLE IF NOT EXISTS events_by_account_day (
    account_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    summary text,
    PRIMARY KEY ((account_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id DESC);
```

Khóa của bảng:

| Cột | Vai trò | Hệ quả cho `SELECT` |
| --- | --- | --- |
| `account_id`, `event_day` | **Composite partition key** | Cần đủ cả hai để định vị đúng một partition. |
| `occurred_at` | Clustering column thứ nhất | Có thể dùng điều kiện khoảng trong partition. |
| `event_id` | Clustering column thứ hai | Phân biệt hai sự kiện có cùng `occurred_at`. |
| `event_type`, `summary` | Regular columns | Không tự tạo index/đường đọc theo hai cột này. |

Với schema này, các dòng của cùng `(account_id,event_day)` có thứ tự mặc định `occurred_at DESC, event_id DESC`.

### 3.2. Đưa bảng lab về trạng thái đầu

Nếu đây là **bảng dùng riêng cho thực hành và bạn đã xác nhận không có dữ liệu cần giữ**, có thể đặt lại trước mỗi vòng thí nghiệm:

```sql
-- NGUY HIỂM nếu áp dụng cho dữ liệu thật.
-- CHỈ dùng trên bảng lab riêng, sau khi xác nhận đích.
TRUNCATE events_by_account_day;
```

`TRUNCATE` xóa dữ liệu của bảng, nên không đưa lệnh này vào migration hoặc endpoint ứng dụng. Nếu không có quyền xóa bảng lab, hãy dùng keyspace/bảng thực hành mới và đảm bảo dữ liệu ban đầu không bị lẫn với lần chạy trước.

### 3.3. Tạo bảy dòng ở account A/ngày 20

```sql
-- Một partition: (A, 2026-11-20), các event_id cố định.
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 08:00:00+0000',
    00000000-0000-4000-8000-000000000001,
    'LOGIN', 'Dang nhap'
);

INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 09:00:00+0000',
    00000000-0000-4000-8000-000000000002,
    'VIEW', 'Xem danh sach'
);

INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 10:00:00+0000',
    00000000-0000-4000-8000-000000000003,
    'CLICK', 'Mo chi tiet'
);

-- Cùng timestamp 10:00 nhưng primary key khác.
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 10:00:00+0000',
    00000000-0000-4000-8000-000000000004,
    'PAY', 'Thanh toan'
);

INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 11:00:00+0000',
    00000000-0000-4000-8000-000000000005,
    'VIEW', 'Xem hoa don'
);

INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 12:00:00+0000',
    00000000-0000-4000-8000-000000000006,
    'SHIP', 'Giao van chuyen'
);

INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 13:00:00+0000',
    00000000-0000-4000-8000-000000000007,
    'LOGOUT', 'Dang xuat'
);
```

### 3.4. Thêm partition ít dòng và cột thiếu

```sql
-- Account A, ngày 21: partition thứ hai, hai dòng.
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21', '2026-11-21 07:00:00+0000',
    00000000-0000-4000-8000-000000000008,
    'LOGIN', 'Ngay moi'
);

-- Cố ý KHÔNG ghi summary: cột thường thiếu giá trị.
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21', '2026-11-21 08:00:00+0000',
    00000000-0000-4000-8000-000000000009,
    'VIEW'
);

-- Account B, ngày 20: partition thứ ba, một dòng.
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    22222222-2222-4222-8222-222222222222,
    '2026-11-20', '2026-11-20 06:00:00+0000',
    00000000-0000-4000-8000-000000000010,
    'LOGIN', 'Account B'
);
```

**Dữ liệu gốc sau bước này:**

| Partition key | Số dòng | Trường hợp cần kiểm tra |
| --- | ---: | --- |
| Account A, ngày 20/11 | 7 | Timestamp 10:00 trùng; hai `VIEW` |
| Account A, ngày 21/11 | 2 | Một `summary` không có giá trị |
| Account B, ngày 20/11 | 1 | Partition chỉ có một dòng |
| Account A, ngày 22/11 | 0 | Partition không tồn tại/có kết quả rỗng |
| **Tổng dữ liệu thực có** | **10** | **3 partition có dòng** |

Thứ tự dự kiến của partition A/ngày 20:

| Vị trí | Thời gian UTC | `event_id` (đuôi) | Loại sự kiện |
| ---: | --- | --- | --- |
| 1 | 13:00 | `...0007` | `LOGOUT` |
| 2 | 12:00 | `...0006` | `SHIP` |
| 3 | 11:00 | `...0005` | `VIEW` |
| 4 | 10:00 | `...0004` | `PAY` |
| 5 | 10:00 | `...0003` | `CLICK` |
| 6 | 09:00 | `...0002` | `VIEW` |
| 7 | 08:00 | `...0001` | `LOGIN` |

Vì primary key được đặt cố định, chạy lại các `INSERT` trên chính các khóa ấy là **upsert** chứ không thêm dòng trùng. Tuy nhiên, để bộ test thực sự tái lập sau các bước DELETE/TTL, nên reset **bảng lab riêng** và nạp lại dữ liệu gốc trước vòng thử tiếp theo.

## 4. Trước khi trace: định nghĩa bảng kiểm kết quả

Đừng mở tracing rồi mới tự hỏi dữ liệu “đúng” là như thế nào. Hãy lập **test matrix** trước:

| ID | Tình huống | Kỳ vọng trên dữ liệu gốc |
| --- | --- | --- |
| T01 | Một partition, `LIMIT 3` | `0007, 0006, 0005` theo thứ tự |
| T02 | Range `[10:00,12:00)` | `0005, 0004, 0003` |
| T03 | Hai dòng cùng `10:00` | `0004` trước `0003` |
| T04 | Partition ngày 22 không có dữ liệu | 0 dòng, không lỗi |
| T05 | Account B/ngày 20 | 1 dòng `0010` |
| T06 | Account A/ngày 21 chọn `summary` | 2 dòng, một `summary = null` |
| T07 | Hai partition ngày 20–21 + `PER PARTITION LIMIT 2` | 4 dòng tổng, 2 mỗi ngày |
| T08 | Lọc `event_type = 'VIEW'` trong partition A/ngày 20 | 2 dòng, thường cần `ALLOW FILTERING` |
| T09 | Keyset sau `11:00/0005`, `LIMIT 3` | `0004, 0003, 0002` |
| T10 | Fetch size 2, duyệt hết partition A/ngày 20 | 7 dòng toàn truy vấn; có thể nhiều protocol pages |

**Lưu ý định danh:** `0010` ở bảng trên chỉ là cách viết tắt dễ nhìn của UUID kết thúc bằng các chữ số `0010`; trong CQL luôn dùng UUID đầy đủ.

Mọi kỳ vọng ở đây dựa trên **bảng gốc chưa bị thay đổi**. Đừng chạy các bước ghi/xóa ở mục 10 rồi dùng bảng này để phán định sai query.

## 5. Kiểm chứng SELECT theo khóa và clustering range

### 5.1. T01 — đúng partition, đúng thứ tự và LIMIT

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 3;
```

**Kỳ vọng:** `LOGOUT/0007`, `SHIP/0006`, `VIEW/0005`.

Phép kiểm chứng:

- `WHERE` cung cấp **toàn bộ composite partition key**; truy vấn nhắm một partition.
- `ORDER BY` dùng đúng hai clustering columns theo chiều schema hỗ trợ.
- `LIMIT 3` giới hạn tối đa ba dòng tổng kết quả, không phải ba dòng mỗi protocol page.
- `SELECT` chỉ trả cột cần dùng; không kéo theo `summary` không cần thiết.

### 5.2. T02 — kiểm tra tính mở/đóng của cận thời gian

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at >= '2026-11-20 10:00:00+0000'
  AND occurred_at <  '2026-11-20 12:00:00+0000'
ORDER BY occurred_at DESC, event_id DESC;
```

**Kỳ vọng:** `VIEW/0005` (11:00), `PAY/0004` (10:00) và `CLICK/0003` (10:00).

| Ranh giới | Giá trị mẫu | Có được lấy? |
| --- | --- | --- |
| Cận dưới `>= 10:00` | `10:00/0004` và `10:00/0003` | **Có** |
| Bên trong khoảng | `11:00/0005` | **Có** |
| Cận trên `< 12:00` | `12:00/0006` | **Không** |

Nếu viết `<= 12:00`, kết quả có thêm `SHIP/0006`. Kiểm thử với hàng **đúng tại ranh giới** giúp phát hiện lỗi off-by-one mà dữ liệu ngẫu nhiên có thể bỏ qua.

### 5.3. T03 — cùng timestamp nhưng khác clustering key

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at = '2026-11-20 10:00:00+0000'
ORDER BY occurred_at DESC, event_id DESC;
```

**Kỳ vọng:** hai hàng, `PAY/0004` trước `CLICK/0003`.

Vì cả hai có cùng `occurred_at`, `event_id` tạo thứ tự xác định. Ứng dụng phân trang keyset chỉ lưu timestamp mà không lưu `event_id` có thể **bỏ sót** một trong hai hàng. Trace không thể “sửa” lỗi hợp đồng cursor này; nó phải được phát hiện bằng bộ dữ liệu biên.

### 5.4. T04 và T05 — partition rỗng, partition chỉ có một hàng

```sql
-- Partition được yêu cầu nhưng không có dữ liệu ở ngày 22.
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-22';

-- Partition của account B chỉ có một hàng.
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 22222222-2222-4222-8222-222222222222
  AND event_day = '2026-11-20'
LIMIT 3;
```

**Kỳ vọng:** truy vấn thứ nhất trả **0 hàng**; truy vấn thứ hai trả **1 hàng** (`LOGIN/0010`). `LIMIT 3` là trần trên, không bắt buộc có đủ ba hàng.

Đừng coi “0 hàng” nghĩa query không có chi phí: Cassandra vẫn có thể cần định vị replica và kiểm tra xem partition có dữ liệu còn sống hay không. Trace giúp quan sát hành trình đọc ấy, nhưng không nên suy số bytes đĩa chính xác từ riêng một trace event.

### 5.5. T06 — regular column không có giá trị

```sql
SELECT occurred_at, event_id, event_type, summary
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
ORDER BY occurred_at DESC, event_id DESC;
```

Có **2 hàng**. `VIEW/0009` lúc 08:00 có `summary = null` vì bản ghi chưa có giá trị cột này; `LOGIN/0008` lúc 07:00 có `summary = 'Ngay moi'`.

Điều cần kiểm tra ở Java:

- Getter `getString("summary")` có thể trả `null`; không dùng `summary.length()` khi chưa kiểm tra.
- Hai hàng **không bị gộp hoặc loại đi** chỉ vì một cột thường thiếu dữ liệu.
- Nếu dùng `COUNT(summary)`, ý nghĩa khác `COUNT(*)`; không suy dữ liệu bị mất hàng.

## 6. Bật tracing trong cqlsh và đọc kết quả

### 6.1. TRACING là lệnh của cqlsh

Trên **lab**, có thể làm:

```sql
USE cassandra_trace_lab;

-- Cách hiển thị/trình bày trong cqlsh, không phải mệnh đề SELECT.
PAGING OFF;
TRACING ON;

SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 3;

TRACING OFF;
```

Khi tracing bật, `cqlsh` thường hiển thị **tracing session ID** và các sự kiện diễn ra trên các node tham gia query. Tên/thứ tự sự kiện cụ thể phụ thuộc phiên bản Cassandra, cache và đường đọc. Không viết bài kiểm thử theo kiểu “bắt buộc trace phải có đúng 12 event theo cùng thứ tự” vì cách thực thi có thể thay đổi.

`TRACING ON` áp dụng cho những query trong **phiên cqlsh hiện tại** cho tới khi tắt; không phải lệnh thay đổi vĩnh viễn schema, partition key hay cấu hình tracing mặc định của mọi request toàn cluster.

### 6.2. Những trường nên quan sát trong trace

Một tracing output thường giúp xem:

| Thông tin | Cách đọc | Không được suy ra |
| --- | --- | --- |
| **Tracing session ID** | Mã liên kết các event của lần thực thi | Đây không phải paging state hay transaction ID nghiệp vụ. |
| **Coordinator** | Node nhận và điều phối truy vấn | Nó không nhất thiết là node duy nhất phải làm việc. |
| **Source/node** của event | Node phát sinh bước xử lý | Không bằng số partition logic hay toàn bộ replica hiện hữu. |
| **Elapsed/duration** | Thời gian từ mốc trace/query | Không phải benchmark p99 của workload. |
| **Activity/message** | Một số bước thực thi/đọc/trao đổi | Không phải bản kê đầy đủ từng block đĩa/cell. |
| **Replica messages** | Các bước trao đổi giữa coordinator/replicas nếu có | Không có nghĩa mỗi replica tạo một bản ghi kết quả trùng. |

Ví dụ cách diễn giải **khái niệm**:

```text
Query nhận tại coordinator
  -> xác định replica phụ trách token của (A, 2026-11-20)
  -> gửi/nhận các thông điệp đọc theo consistency
  -> quét clustering slice, xử lý các row phù hợp
  -> tạo trang kết quả trả cho client
```

Đây **không phải trace output nguyên văn**; các event trong hệ thống thực có thể nhiều hơn/ít hơn và thay đổi theo phiên bản.

### 6.3. Xem lại tracing session

Nếu bạn đã ghi lại UUID tracing session mà `cqlsh` hiển thị, có thể mở lại nó:

```text
SHOW SESSION <tracing-session-uuid>;
```

Thay `<tracing-session-uuid>` bằng UUID thật từ output trước đó. Đây là **cú pháp minh họa cần thay tham số**, không phải câu lệnh có thể chạy nguyên văn.

Thông tin trace được lưu trong keyspace hệ thống `system_traces`. Trong môi trường có quyền đọc phù hợp, có thể xem bằng một session ID **thật**:

```sql
-- Chỉ minh họa cú pháp: thay UUID bên dưới bằng tracing ID thực tế.
SELECT session_id, request, duration
FROM system_traces.sessions
WHERE session_id = 00000000-0000-0000-0000-000000000000;

SELECT activity, source, source_elapsed
FROM system_traces.events
WHERE session_id = 00000000-0000-0000-0000-000000000000;
```

UUID toàn số không ở trên là **placeholder**, sẽ không tìm thấy trace của thí nghiệm. Ghi trace thường diễn ra bất đồng bộ và dữ liệu trace có TTL; truy vấn ngay sau khi request kết thúc có thể tạm chưa có đủ events. Không coi đó là lỗi kết quả `SELECT`.

**Vận hành:** Tracing tạo thêm work và dữ liệu trong `system_traces`, có thể tác động latency. Chỉ bật **có chọn lọc** khi điều tra; không để `TRACING ON` khi chạy thử tải lớn hay mọi request production.

## 7. So sánh trace của hai đường đọc

### 7.1. Đọc một partition theo khóa

```sql
TRACING ON;

SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at >= '2026-11-20 10:00:00+0000'
  AND occurred_at <  '2026-11-20 12:00:00+0000';

TRACING OFF;
```

Đây là trường hợp **đã có toàn bộ partition key** và một đoạn clustering. Kỳ vọng **3 hàng logic** trong dải. Khi đọc trace, hãy xác nhận request được thực thi thành công và xem các bước coordinator/replica; **không bắt buộc** trace phải có một event đúng tên “Read 3 rows” thì mới coi query hợp lệ.

### 7.2. Đọc partition rồi lọc một cột thường

```sql
TRACING ON;

SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_type = 'VIEW'
ALLOW FILTERING;

TRACING OFF;
```

Trên dữ liệu gốc, chỉ **2 hàng** khớp `VIEW`: `0005` và `0002`. Nhưng `event_type` là **regular column** không có index trong schema lab. Vì vậy Cassandra có thể cần kiểm tra nhiều hàng ứng viên trong partition rồi loại các hàng không khớp.

So sánh:

| Tiêu chí | Clustering range | `ALLOW FILTERING` theo `event_type` |
| --- | --- | --- |
| Partition key | Một partition đã biết | Một partition đã biết |
| Cách thu hẹp hàng | Theo thứ tự clustering | Kiểm tra cột thường sau khi đọc ứng viên |
| Hàng khớp trong lab | 3 | 2 |
| Kết luận từ số hàng output | Không đủ để suy I/O | Càng không đủ để suy I/O |
| Điều phải đo ở scale lớn | Clustering slice, partition size, tombstone, latency | Tập ứng viên, tỷ lệ khớp, tombstone, latency |

**Không nên so sánh một lần chạy rồi tuyên bố một query luôn nhanh hơn query kia gấp X lần.** Trên lab mười dòng, các khác biệt thời gian rất nhỏ và dễ bị cache, scheduling và overhead tracing chi phối.

### 7.3. Một câu SELECT toàn bảng trong lab

```sql
-- CHỈ trong lab nhỏ: không áp dụng tùy tiện cho production.
SELECT account_id, event_day, occurred_at, event_id
FROM events_by_account_day;
```

Với dữ liệu gốc, trả **10 hàng thuộc 3 partition**. Câu truy vấn không xác định partition key, nên ở bảng production lớn nó có thể chạm nhiều token range và node. Một trace nhỏ không phản ánh được toàn bộ rủi ro khi số partition và số hàng tăng nhiều bậc độ lớn.

**Đừng nhầm** “10 dòng trên lab” với “10 dòng trong production”: trace chỉ là một mẫu thực thi trong trạng thái dữ liệu/tải cụ thể.

## 8. T07–T09: nhiều partition, filtering và cursor

### 8.1. T07 — PER PARTITION LIMIT

```sql
SELECT event_day, occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day IN ('2026-11-20', '2026-11-21')
PER PARTITION LIMIT 2;
```

Theo dữ liệu gốc:

| Partition | Hàng góp vào kết quả |
| --- | --- |
| A/ngày 20 | `0007`, `0006` |
| A/ngày 21 | `0009`, `0008` |
| **Tổng** | **4 hàng** |

Đây là hai partition ứng viên. Không khẳng định kết quả bốn hàng được sắp theo **một timeline toàn cục**, bởi clustering order định nghĩa thứ tự **bên trong mỗi partition**, không phải giữa các partition.

Thử thêm `LIMIT 3` **sau** `PER PARTITION LIMIT 2`:

```sql
SELECT event_day, occurred_at, event_id
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day IN ('2026-11-20', '2026-11-21')
PER PARTITION LIMIT 2
LIMIT 3;
```

Khi đó toàn truy vấn không quá **3 hàng**; không partition nào góp nhiều hơn **2 hàng**. Không đoán “hàng thứ ba thuộc ngày nào” chỉ từ thứ tự viết trong `IN`.

### 8.2. T08 — ALLOW FILTERING không phải một index

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_type = 'VIEW'
ALLOW FILTERING;
```

Kết quả logic: hai hàng `VIEW/0005` và `VIEW/0002`. Nếu một phiên bản hoặc chính sách Cassandra từ chối một dạng filtering, phải **ghi lại lỗi, phiên bản và schema** thay vì lặng lẽ thêm điều kiện khác cho đến khi truy vấn chạy mà không hiểu kế hoạch đọc.

Để hỗ trợ truy vấn theo `event_type` thường xuyên ở scale lớn, xem xét **bảng theo truy vấn** hoặc **index phù hợp** với phiên bản/độ chọn lọc; không dùng `ALLOW FILTERING` như cách tối ưu mặc định.

### 8.3. T09 — keyset phải dùng toàn bộ clustering key

Giả sử trang đầu:

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 3;
```

Kết thúc ở `11:00/0005`. Để lấy ba hàng kế tiếp:

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND (occurred_at, event_id) < (
      '2026-11-20 11:00:00+0000',
      00000000-0000-4000-8000-000000000005
  )
ORDER BY occurred_at DESC, event_id DESC
LIMIT 3;
```

Kỳ vọng `0004, 0003, 0002`. Kiểm thử tiếp một trang nữa bằng ranh giới `(09:00,0002)` sẽ thấy `0001`.

**Lỗi cần cố tình thử:** nếu trang đầu kết thúc ở `10:00/0004` và câu tiếp theo chỉ có `occurred_at < 10:00`, nó **bỏ mất `10:00/0003`**. Bộ dữ liệu chứa timestamp trùng chính là để bắt loại lỗi này.

## 9. T10: kiểm chứng phân trang và trace theo từng lần fetch

### 9.1. cqlsh với page size 2

```sql
PAGING 2;
TRACING ON;

SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY occurred_at DESC, event_id DESC;

TRACING OFF;
PAGING OFF;
```

Mục tiêu fetch là hai hàng/page, nhưng số hàng **thực** trong mỗi page được quyết định khi server thực thi. Với bảy hàng không đổi, tổng khi duyệt hết phải là **bảy**, dù chia thành bao nhiêu page.

Khi trace truy vấn phân trang:

- Phân biệt trace của **fetch đầu** với các fetch tiếp nếu giao thức/driver tạo trace riêng cho chúng.
- Lưu tracing ID tương ứng từng lần fetch nếu cần phân tích.
- Đừng đánh đồng **số page** với số partition.
- Đừng khẳng định page size 2 chắc chắn tạo đúng bốn lần fetch trên mọi phiên bản/đường thực thi.

### 9.2. Paging state không phải snapshot

Giả sử đã đọc ba hàng đầu: `0007,0006,0005`. Nếu trước khi fetch tiếp, một bản ghi mới với `occurred_at = 14:00` được ghi, nó đứng **trước** vị trí đã đi qua. Việc tiếp tục bằng paging state **không bảo đảm** quay lại đầu để trả sự kiện ấy.

Ngược lại, một bản ghi ghi muộn với timestamp `10:30` có thể xuất hiện trong phần **chưa duyệt**, tùy thời điểm và replica nhìn thấy dữ liệu. `DELETE` hoặc TTL hết hạn cũng có thể thay đổi tập hàng của các page sau.

Trace sẽ cho thấy những bước đã diễn ra trong **một lần đọc**, không cung cấp bằng chứng rằng toàn bộ chuỗi page chia sẻ cùng snapshot dữ liệu.

### 9.3. Bẫy khi chỉ xử lý nửa page

```text
Protocol page hiện tại: A, B, C
Paging state S_next: vị trí sau C, cho page tiếp theo

API xử lý A, B nhưng bỏ C
API trả S_next
Request tiếp dùng S_next  --> C bị bỏ sót
```

Phải **xử lý hết/buffer mọi hàng** trong protocol page trước khi cấp state cho lần fetch tiếp. Nếu API cần đúng N item bất chấp số hàng protocol page, cần buffer/cursor ở tầng ứng dụng hoặc keyset pagination phù hợp.

## 10. Những trường hợp biên có dữ liệu đang thay đổi

**Quan trọng:** Các thao tác trong mục này làm thay đổi bảng lab. Chạy mỗi tình huống **sau khi reset dữ liệu gốc** bằng quy trình ở mục 3; không cộng dồn chúng rồi kỳ vọng kết quả ở mục 4 vẫn chính xác.

### 10.1. Xóa một hàng chưa được đọc

```sql
-- Thử trên bảng lab riêng.
DELETE FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at = '2026-11-20 10:00:00+0000'
  AND event_id = 00000000-0000-4000-8000-000000000004;
```

Sau khi xóa được quan sát, truy vấn theo `occurred_at = 10:00` có thể chỉ còn `CLICK/0003`. Kết quả cuối của cả partition có thể từ 7 xuống **6 hàng sống**. Trace/latency không bắt buộc giảm: thao tác xóa tạo tombstone, và Cassandra có thể phải xử lý dấu xóa để biết hàng nào còn hiệu lực.

Muốn đưa lab về trạng thái chuẩn, reset bảng lab riêng rồi nạp lại đủ mười hàng, hoặc khôi phục dòng bằng thao tác ghi hợp lệ. Đừng suy từ “còn 6 hàng sống” rằng dữ liệu vật lý chỉ có đúng sáu records.

### 10.2. INSERT mới ở đầu thứ tự

```sql
-- Sự kiện mới hơn mọi sự kiện gốc của ngày 20.
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 14:00:00+0000',
    00000000-0000-4000-8000-000000000011,
    'REVIEW', 'Moi xuat hien'
);
```

Một câu `SELECT` **mới từ đầu** sẽ có `REVIEW/0011` đứng đầu. Nhưng một chuỗi paging đã qua những hàng mới nhất **có thể không trả hàng ấy** ở các page còn lại. Không gọi đó là lỗi nếu hợp đồng chỉ là “tiếp tục dữ liệu có thể thay đổi”; nếu sản phẩm yêu cầu không bỏ sót event mới, cần cơ chế thông báo/làm mới danh sách hoặc luồng sự kiện riêng.

### 10.3. INSERT ghi muộn nằm trong khoảng chưa đọc

```sql
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 10:30:00+0000',
    00000000-0000-4000-8000-000000000012,
    'BACKFILL', 'Ghi sau nhung timestamp cu'
);
```

Đây là một **event được ghi sau nhưng có clustering key cũ**. Nó có thể đi vào phần còn lại của một cuộc duyệt đang thực hiện, tùy ranh giới/state và dữ liệu replica. Vì vậy đặt cận `occurred_at < :asOf` chỉ ngăn những hàng có timestamp sau `asOf`, **không tạo snapshot theo thời điểm ghi/commit**.

### 10.4. UPDATE cột thường

```sql
UPDATE events_by_account_day
SET summary = 'Da cap nhat'
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at = '2026-11-20 09:00:00+0000'
  AND event_id = 00000000-0000-4000-8000-000000000002;
```

Khóa của `VIEW/0002` không đổi, nhưng một trang được đọc **sau update** có thể trả `summary` mới. Việc giữ nguyên query và paging state **không bảo đảm** dữ liệu regular column giống page trước.

Muốn “đổi” một clustering key, không cập nhật khóa tại chỗ như một regular column; phải mô hình hóa xóa hàng khóa cũ và ghi hàng khóa mới, có thể thay đổi vị trí trong kết quả phân trang.

### 10.5. TTL tạo hàng tạm thời

```sql
-- Chạy trên dữ liệu lab đã reset, không dùng như kiểm tra thời gian tuyệt đối.
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 14:30:00+0000',
    00000000-0000-4000-8000-000000000013,
    'TEMP', 'Se het han'
) USING TTL 120;

SELECT occurred_at, event_id, event_type, TTL(summary)
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at = '2026-11-20 14:30:00+0000'
  AND event_id = 00000000-0000-4000-8000-000000000013;
```

Trong khoảng TTL còn hiệu lực, hàng `TEMP/0013` có thể xuất hiện; sau khi các giá trị hết hạn và việc hết hạn được quan sát, nó không còn là một hàng sống có dữ liệu thường. Không so sánh “đúng 120 giây” bằng một lần gọi trễ không kiểm soát; thời gian trôi, lịch hệ thống và trạng thái replica đều cần lưu ý.

Số hàng trả về giảm **không** chứng minh tombstone hoặc công việc đọc biến mất ngay. Compaction, TTL và repair có các điều kiện xử lý riêng; trace chỉ cho một phần tín hiệu tại thời điểm đọc.

### 10.6. Các kỳ vọng nên và không nên có

| Biến động giữa hai page | Có thể quan sát | Không được khẳng định |
| --- | --- | --- |
| Ghi mới trước vị trí đã đi qua | Hàng mới không xuất hiện trong phần còn lại | “Mọi insert đều được thấy khi tiếp tục.” |
| Ghi muộn trong vùng chưa duyệt | Kết quả của page tiếp có thể thay đổi | “Paging giữ snapshot T0.” |
| Xóa hàng chưa duyệt | Hàng vắng ở các page sau | “Trang sau luôn có các ID cũ.” |
| Cột thường được update | Nội dung mới có thể xuất hiện | “Cùng paging state là cùng phiên bản cell.” |
| TTL hết hạn | Ít hàng sống hơn, có thể tăng chi phí tombstone | “Ít hàng thì đọc ít cell vật lý.” |
| Replica chưa hội tụ | Các lần đọc có thể quan sát khác nhau | “Consistency level tạo snapshot xuyên page.” |

## 11. Java Driver 4.x: bật trace có chọn lọc và kiểm tra từng page

Ví dụ với **Java 17** và **Apache Cassandra Java Driver 4.x**. Giả định `CqlSession session` đã kết nối với keyspace `cassandra_trace_lab`. Tracing **không được bật trong mọi request thực tế**.

### 11.1. Bật trace cho đúng một prepared statement

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.ExecutionInfo;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.LocalDate;
import java.util.UUID;

// Giả định session đã được cấu hình và kết nối cassandra_trace_lab.
PreparedStatement prepared = session.prepare("""
    SELECT occurred_at, event_id, event_type
    FROM events_by_account_day
    WHERE account_id = ?
      AND event_day = ?
    ORDER BY occurred_at DESC, event_id DESC
    LIMIT ?
    """);

UUID accountId = UUID.fromString(
    "11111111-1111-4111-8111-111111111111"
);
LocalDate day = LocalDate.parse("2026-11-20");

BoundStatement request = prepared.bind(accountId, day, 3)
    .setPageSize(2)
    .setTracing(true); // Chỉ bật để chẩn đoán có kiểm soát.

ResultSet result = session.execute(request);
ExecutionInfo executionInfo = result.getExecutionInfo();

// Java Driver 4.17: getTracingId() trả UUID hoặc null.
UUID traceId = executionInfo.getTracingId();
System.out.println("Trace ID: " + traceId);

for (Row row : result) {
    System.out.printf("%s | %s | %s%n",
        row.getInstant("occurred_at"),
        row.getUuid("event_id"),
        row.getString("event_type"));
}
```

Với dữ liệu gốc, vòng lặp đọc **3 dòng tổng cộng** do `LIMIT 3`, dù page size là `2`. `ResultSet` đồng bộ có thể **tự fetch page tiếp theo** khi được duyệt hết; nó không dừng sau hai dòng.

**Chi tiết API quan trọng:** Trên Java Driver 4.17, `ExecutionInfo.getTracingId()` trả `UUID` hoặc **`null`** nếu request không có tracing. Nó không phải `Optional<UUID>`. Các setter của statement tạo/cung cấp statement đã cập nhật, vì vậy phải dùng **giá trị trả về** của `setTracing(true)`.

### 11.2. Lấy thông tin trace chi tiết khi cần

Trong Java Driver 4.17, `ExecutionInfo` có API lấy query trace:

```java
import com.datastax.oss.driver.api.core.cql.ExecutionInfo;
import com.datastax.oss.driver.api.core.cql.QueryTrace;
import com.datastax.oss.driver.api.core.cql.TraceEvent;

ExecutionInfo info = result.getExecutionInfo();
if (info.getTracingId() != null) {
    QueryTrace trace = info.getQueryTrace();
    System.out.printf("Coordinator: %s, duration: %d us%n",
        trace.getCoordinatorAddress(),
        trace.getDurationMicros());

    for (TraceEvent event : trace.getEvents()) {
        System.out.printf("%d us | %s | %s%n",
            event.getSourceElapsedMicros(),
            event.getSource(),
            event.getActivity());
    }
}
```

Lấy `QueryTrace` có thể cần các query phụ đến `system_traces`; bản ghi trace được ghi **bất đồng bộ** nên driver có thể thử đọc lại. Đừng gọi API này trên mọi request production: nó tăng công việc, và đối tượng trace có thể chưa sẵn hoặc không đầy đủ khi gặp lỗi/quyền truy cập/hết TTL. Nếu chỉ cần liên kết log với trace, **UUID trace ID** thường là thông tin nhẹ hơn.

### 11.3. Kiểm tra từng trang bất đồng bộ

```java
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.concurrent.CompletionStage;

BoundStatement paged = prepared.bind(accountId, day, 7)
    .setPageSize(2)
    .setTracing(true);

CompletionStage<AsyncResultSet> firstFuture =
    session.executeAsync(paged);

firstFuture.thenAccept(first -> {
    int actualRows = 0;
    for (Row row : first.currentPage()) {
        actualRows++;
        System.out.println(row.getUuid("event_id"));
    }

    UUID firstTraceId = first.getExecutionInfo().getTracingId();
    System.out.println("First page rows: " + actualRows);
    System.out.println("First trace ID: " + firstTraceId);
    System.out.println("More pages: " + first.hasMorePages());

    // Không fetch tiếp ở đây: chỉ minh họa trang đầu.
});
```

`AsyncResultSet.currentPage()` chỉ chứa **trang hiện tại**. Nếu muốn fetch trang sau, gọi `fetchNextPage()` khi `hasMorePages()` là true; trace từng fetch phải được quan sát từ `getExecutionInfo()` của response tương ứng, thay vì suy mọi page có cùng ID/cùng thời gian thực thi.

Ví dụ này **không gọi `join()` hay block**; code async chỉ xử lý trang đầu. Trong production, tránh giữ thread không cần thiết và thiết kế timeout/backpressure hợp lý.

### 11.4. So sánh kết quả ở Java bằng full primary key

Đối với một API có thứ tự theo `(occurred_at DESC,event_id DESC)`, test đừng chỉ so sánh:

```text
result.size() == 3
```

Cần so sánh **đúng cặp giá trị khóa và thứ tự**:

```java
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.List;
import java.util.UUID;

// Một lần chạy MỚI dành riêng cho assertion, không bật trace.
ResultSet resultForAssertion = session.execute(
    request.setTracing(false)
);
List<UUID> actualIds = resultForAssertion.all().stream()
    .map(row -> row.getUuid("event_id"))
    .toList();

List<UUID> expectedIds = List.of(
    UUID.fromString("00000000-0000-4000-8000-000000000007"),
    UUID.fromString("00000000-0000-4000-8000-000000000006"),
    UUID.fromString("00000000-0000-4000-8000-000000000005")
);

if (!actualIds.equals(expectedIds)) {
    throw new AssertionError("Thu tu/ket qua SELECT khong nhu ky vong");
}
```

**Lưu ý:** `ResultSet` đã được duyệt trong ví dụ `11.1`, nên đoạn assertion mở **một truy vấn mới** với tracing tắt. Không gọi `all()` trên result set đã tiêu thụ rồi kỳ vọng có lại ba dòng. Trong bài test thực tế, có thể dùng chính danh sách hàng đã thu từ một lần chạy, tránh query trùng nếu không cần thiết.

## 12. Phân biệt tracing với benchmark, metrics và log ứng dụng

### 12.1. Trace giải thích một lần chạy, benchmark cho biết phân phối

| Công cụ | Trả lời tốt câu hỏi nào? | Giới hạn |
| --- | --- | --- |
| **CQL assertions** | Dòng/thứ tự/cột nào phải xuất hiện? | Không đo read amplification. |
| **Query tracing** | Request này đã đi qua những bước/nodes nào? | Overhead và độ chi tiết phụ thuộc phiên bản; không là thống kê p99. |
| **Driver metrics** | Latency, requests, retry, timeout, in-flight của ứng dụng? | Không tự thay giải thích toàn bộ bước storage. |
| **Node/JMX/monitoring metrics** | Read latency, tombstone, SSTable, compaction, repair, CPU/disk? | Cần correlate theo workload/thời gian. |
| **Load test có kiểm soát** | p50/p95/p99/throughput khi QPS và dữ liệu tăng? | Phải thiết kế workload và môi trường đại diện. |
| **Application logs** | Người dùng nào gọi query shape nào, timeout/error nào? | Cần kiểm soát PII, tránh log query params/tokens nhạy cảm. |

Một trace có thời gian nhanh không đủ chứng minh query đạt p99 ở QPS lớn. Ngược lại, p99 chậm không cho biết trực tiếp nguyên nhân nếu không liên hệ tới trace/metrics và thiết kế khóa.

### 12.2. Thử nghiệm công bằng

Để so sánh hai query shape, ví dụ `SELECT *` với projection tường minh:

1. Dùng **cùng cluster/topology, consistency, partition key và bộ dữ liệu**.
2. Cố định page size/`LIMIT`, số request đồng thời và chính sách timeout.
3. Chạy cả với **cache ấm** và khi dữ liệu chưa vào cache nếu nghiệp vụ cần.
4. Lặp nhiều lần và đo **phân phối** thay vì một thời gian đơn lẻ.
5. Ghi số hàng/bytes và kết quả đúng; giảm payload không có nghĩa giảm mọi disk reads.
6. Tracing chỉ trên **một mẫu nhỏ** các request, không bật trên toàn bộ run load test.
7. Theo dõi compaction, repair, tombstone, node saturation và retry.

Khi so sánh `WHERE` đủ partition key với lọc trên regular column, số hàng trả về có thể khác nhau. Vì vậy phải ghi rõ hai truy vấn **khác mục đích** hay cùng mục đích; không so latency đơn thuần rồi coi kết quả ngang nhau.

### 12.3. Mẫu bảng lưu kết quả thí nghiệm

| Test ID | Query shape | Expected keys | Actual keys | Tracing ID | Latency | Kết luận |
| --- | --- | --- | --- | --- | --- | --- |
| T01 | Full PK + `LIMIT 3` | `0007,0006,0005` | Ghi khi chạy | UUID thực | Ghi khi đo | Đúng/sai |
| T02 | PK + clustering `[10,12)` | `0005,0004,0003` | Ghi khi chạy | UUID thực | Ghi khi đo | Đúng/sai |
| T04 | PK ngày không có dữ liệu | Rỗng | Ghi khi chạy | UUID thực | Ghi khi đo | Đúng/sai |
| T08 | PK + `VIEW ALLOW FILTERING` | `0005,0002` | Ghi khi chạy | UUID thực | Ghi khi đo | Đúng/sai |

**Không bịa latency hoặc tracing ID.** Những ô “Ghi khi chạy” chỉ được điền từ kết quả của cluster thực tế. Một tài liệu hướng dẫn có thể dự báo **kết quả logic** từ dữ liệu mẫu, nhưng không thể dự báo chính xác ID trace hay thời gian/nội dung event của máy đang chạy.

## 13. Sự khác biệt giữa lab một node và cluster nhiều replica

Trong lab `SimpleStrategy`/RF=1:

- Không kiểm tra được tình huống hai replica trả phiên bản khác nhau.
- Không thể dùng nó để chứng minh bảo đảm của `LOCAL_QUORUM` trong topology đa replica.
- Không thấy đầy đủ chi phí mạng, speculative execution, coordinator overload và repair khi node có sự cố.

Khi triển khai hệ thống thực:

| Tình huống | Môi trường phù hợp | Điều cần kiểm chứng |
| --- | --- | --- |
| CQL hợp lệ, thứ tự clustering | Lab một node | Kết quả cụ thể và trường hợp biên. |
| Paging state, page size, cursor trùng timestamp | Lab một node + Java Driver | Không bỏ/lặp hàng khi không có biến động dữ liệu. |
| Tác động của ghi/xóa/TTL giữa trang | Lab có thay đổi kiểm soát | Không hứa snapshot; xử lý đúng theo hợp đồng API. |
| Đọc `LOCAL_ONE`/`LOCAL_QUORUM` | Cluster nhiều replica | Độ mới dữ liệu, latency/availability theo RF. |
| Replica chưa hội tụ, node down, timeout/retry | Môi trường fault-test | Hành vi lỗi và khả năng phục hồi. |
| Quét rộng, hot partition, tombstone | Data set/tải gần production | p95/p99, read amplification, rate limit. |

Ở cluster nhiều datacenter, phải phân biệt `ONE`/`QUORUM` với `LOCAL_ONE`/`LOCAL_QUORUM` theo replication strategy. Một trace có nhiều node chưa đủ kết luận consistency “đúng nghiệp vụ”; cần đối chiếu mức consistency, topology và chính sách ghi ứng dụng.

## 14. Những lỗi thường gặp khi kiểm chứng Cassandra SELECT

| Nhận định hoặc cách test | Vì sao sai/thiếu | Cách làm tốt hơn |
| --- | --- | --- |
| “Query chạy được nên đúng.” | Có thể sai thứ tự, cận khoảng hoặc bỏ hàng trùng timestamp. | Assertion theo full primary key và trường hợp biên. |
| “Trả 3 dòng nghĩa là chỉ đọc 3 dòng.” | Tombstones/filtering có thể buộc xử lý nhiều hơn. | Trace + metrics + phân tích đường đọc. |
| “Một trace nhanh chứng minh p99 nhanh.” | Trace là một mẫu, lại có overhead. | Benchmark nhiều request với tải đại diện. |
| “Bật `TRACING ON` cho mọi request production.” | Tạo thêm work/tracing data, có thể gây tải. | Bật trên tỷ lệ nhỏ hoặc request điều tra. |
| “Trace nào cũng phải có cùng activity line.” | Event phụ thuộc phiên bản, cache và đường thực thi. | Đánh giá ý nghĩa, không hardcode chuỗi event. |
| “Không thấy events nên query sai.” | Trace được ghi bất đồng bộ, có TTL/quyền hạn. | Kiểm tra tracing ID, retry đọc phù hợp và trạng thái. |
| “Trace cho biết chính xác bytes vật lý trên đĩa.” | Không phải bộ đếm từng block/cell trong mọi phiên bản. | Kết hợp node metrics và benchmark. |
| “`LIMIT 3` là 3 hàng mỗi page.” | Giới hạn toàn truy vấn, không phải page size. | Tách `LIMIT` và driver `setPageSize`. |
| “`PER PARTITION LIMIT 2` nghĩa 2 partition.” | Đó là 2 hàng **mỗi partition**. | Đếm full partition keys ứng viên từ `WHERE`. |
| “Danh sách `IN` cho thứ tự toàn cục.” | Clustering order nằm trong từng partition. | Xác định merge/cursor nếu cần timeline toàn cục. |
| “Timestamp đủ để phân trang keyset.” | Hai hàng cùng timestamp gây bỏ/lặp. | Dùng tuple clustering key `(occurred_at,event_id)`. |
| “Page rỗng tức query kết thúc.” | Có thể còn paging state sau filtering/tombstone. | Kiểm tra `hasMorePages()`. |
| “Tái sử dụng paging state khi đổi ngày/tenant.” | State thuộc query/bind values cụ thể. | Giữ nguyên query, bảo vệ và scope token. |
| “Paging state là snapshot.” | Ghi/xóa/TTL và replica có thể đổi dữ liệu. | Có policy dữ liệu động hoặc cơ chế snapshot riêng. |
| “Lab RF=1 chứng minh behavior quorum.” | Không có nhiều replica để kiểm thử. | Dùng topology nhiều node có RF phù hợp. |
| “`ALLOW FILTERING` đã được trace nên an toàn.” | Cho phép scan không phải tối ưu. | Giới hạn ứng viên, thiết kế bảng/index và đo p99. |
| “Lấy `getTracingId()` bằng `Optional`.” | Driver 4.17 trả nullable `UUID`. | Kiểm tra `null` trước khi dùng. |
| “Cứ chèn/xóa mẫu rồi dùng lại expected baseline.” | Dữ liệu đã bị thay đổi. | Reset bảng lab giữa các thử nghiệm. |

## 15. Bài tập thực hành có đáp án

### Bài 1. Kiểm chứng TOP 3

**Đề:** Với bảng gốc, lấy ba sự kiện mới nhất của account A/ngày 20. Nêu đủ các ID, không chỉ số hàng.

**Đáp án:**

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 3;
```

Kết quả có **`0007, 0006, 0005`** theo thứ tự. Kiểm tra cả số hàng, ID và chiều thời gian.

### Bài 2. Cận trên và cận dưới

**Đề:** Truy vấn các sự kiện trong `[10:00, 12:00)`. Hai hàng 10:00 có được tính? Hàng 12:00 có được tính?

**Đáp án:** Cả `PAY/0004` và `CLICK/0003` đều được lấy vì cận dưới **bao gồm** 10:00. `VIEW/0005` lúc 11:00 cũng được lấy. `SHIP/0006` lúc 12:00 bị loại vì cận trên **không bao gồm**. Thứ tự `DESC` là `0005, 0004, 0003`.

### Bài 3. Partition không có dữ liệu

**Đề:** Account A/ngày 22 chưa có sự kiện. `SELECT ... LIMIT 10` sẽ trả bao nhiêu hàng? Có thể mặc định suy chi phí I/O bằng 0 không?

**Đáp án:** Trả **0 hàng**. Không mặc định chi phí đọc bằng 0, vì Cassandra vẫn có thể phải định vị replica và kiểm tra dữ liệu. Cần metrics/trace khi đánh giá hiệu năng, nhưng không yêu cầu trace phải có số dòng vật lý cụ thể.

### Bài 4. IN và PER PARTITION LIMIT

**Đề:** Account A đọc ngày 20 và 21, `PER PARTITION LIMIT 2`, không có `LIMIT` tổng. Dữ liệu gốc cho tối đa bao nhiêu hàng?

**Đáp án:** **4 hàng**: ngày 20 có `0007, 0006` và ngày 21 có `0009, 0008`. Không khẳng định thứ tự thời gian toàn cục giữa hai partition.

### Bài 5. Đọc trace đúng cách

**Đề:** Một trace trên lab hiển thị vài sự kiện và thời gian rất nhỏ. Có thể kết luận `ALLOW FILTERING` sẽ đạt p99 tốt trên bảng 100 triệu hàng không?

**Đáp án:** **Không.** Trace chỉ phản ánh một request trên dữ liệu/tải cụ thể. `ALLOW FILTERING` trên regular column có thể phải kiểm tra số ứng viên rất lớn. Cần dữ liệu đại diện, benchmark nhiều request, kiểm tra fan-out, tombstone và saturation của replica.

### Bài 6. Cùng timestamp khi keyset

**Đề:** Một trang kết thúc tại `10:00/0004`. Vì sao cursor chỉ có `occurred_at < 10:00` làm mất dữ liệu?

**Đáp án:** Hàng `10:00/0003` cùng timestamp nhưng có `event_id` nhỏ hơn, phải xuất hiện ở trang kế theo thứ tự `DESC`. Cursor đúng cần tuple `(occurred_at,event_id) < (10:00,0004)`.

### Bài 7. TTL và test baseline

**Đề:** Sau khi thêm dòng `TEMP` dùng TTL, một test `COUNT(*)` trên partition ngày 20 lúc thấy 8 hàng, vài phút sau lại thấy 7. Điều gì cần kiểm tra?

**Đáp án:** Dòng TTL có thể đã hết hiệu lực, nên số **hàng còn sống** giảm. Không nhầm với mất dữ liệu ngoài ý muốn; kiểm tra thời điểm ghi, TTL, consistency và dữ liệu đang thay đổi. Không dùng bài test với TTL chạy song song để khẳng định baseline bảy hàng phải đúng mọi lúc.

### Bài 8. Trace từng trang

**Đề:** Java Driver đặt `setPageSize(2)` và `LIMIT 7`. Vòng lặp đồng bộ `for (Row row : resultSet)` có chỉ in hai hàng không? Trace ID ban đầu có đại diện mặc nhiên cho mọi lần fetch không?

**Đáp án:** **Không.** Vòng lặp đồng bộ có thể tự tải page tiếp theo và in đến **7 hàng**. Khi cần trace các lần fetch, quan sát `ExecutionInfo` của từng response/page tương ứng. Không suy mọi lần fetch có cùng trace ID hoặc thời gian từ trace đầu.

### Bài 9. Data mutation và snapshot

**Đề:** Client đọc trang đầu rồi ứng dụng chèn sự kiện lúc 14:00 đứng trước các hàng đã xem. Paging state có đảm bảo trả event mới ở các trang còn lại không?

**Đáp án:** **Không.** State tiếp tục theo vị trí đã duyệt, không bắt buộc quay lại các hàng mới đứng trước cursor. Paging không tạo snapshot cũng không phải cơ chế thông báo sự kiện mới; cần làm mới danh sách hoặc đường cập nhật chuyên biệt.

### Bài 10. Khi nào phải dùng nhiều replica?

**Đề:** Lab `SimpleStrategy`/RF=1 cho kết quả đúng. Có đủ để khẳng định `LOCAL_QUORUM` trên production nhiều replica luôn đọc cùng dữ liệu trong mọi lần paging không?

**Đáp án:** **Không.** Lab một node không mô phỏng được replication/consistency đa replica. Ngay cả trên cluster RF phù hợp, consistency cao hơn không tạo snapshot xuyên các lần đọc khi dữ liệu có thể đổi.

## 16. Checklist trước khi chấp nhận một truy vấn SELECT

1. **Hợp đồng:** Kết quả cần bao nhiêu dòng, cột gì, sắp theo khóa nào, ranh giới thời gian mở hay đóng?
2. **Schema:** Đã hiểu full partition key, clustering columns và thứ tự khóa không?
3. **Bộ dữ liệu:** Có ca rỗng, một hàng, nhiều hàng, timestamp trùng, regular column thiếu, partition khác và giá trị ngay cận không?
4. **Kỳ vọng:** Test có assert **full primary key và thứ tự**, không chỉ assert count không?
5. **Phạm vi:** Query có định vị partition/range rõ ràng? Nếu `IN`, có bao nhiêu partition? Có `ALLOW FILTERING` không?
6. **Trace:** Có bật tracing chọn lọc, lưu tracing ID và đọc đúng ý nghĩa coordinator/replica events không?
7. **Metrics:** Có phân biệt một trace với p95/p99, benchmark, tombstones, bytes và read amplification không?
8. **Paging:** Có kiểm tra `LIMIT` vs page size, `hasMorePages()`, cursor trùng timestamp và việc xử lý hết protocol page không?
9. **Dữ liệu động:** Đã thử INSERT/DELETE/UPDATE/TTL giữa trang, không tuyên bố snapshot sai không?
10. **Tính nhất quán:** Có kiểm tra trên topology RF/consistency thực tế khi nghiệp vụ cần không?
11. **Java:** Prepared statement, typed getters, nullable fields, trace API và error handling có đúng phiên bản driver không?
12. **Bảo mật:** Tracing, query log và paging token có tránh làm lộ tenant, PII, session ID nhạy cảm hoặc token chưa xác thực không?
13. **Khả năng vận hành:** Có budget request, timeout/retry hợp lý, giám sát và phương án rollback/cải thiện schema khi query chậm không?
14. **Tái lập:** Mỗi thử nghiệm đã reset đúng **bảng lab riêng**, không bị ảnh hưởng của các thao tác ghi/xóa trước đó chưa?

**Ghi nhớ:** Trong Cassandra, kiểm chứng một câu `SELECT` cần **hai chân bằng chứng**: (1) bộ dữ liệu có trường hợp biên để xác minh **độ đúng của kết quả**, và (2) trace kết hợp metrics/benchmark để đánh giá **đường đọc và chi phí thực tế**. `TRACING` không thay kiểm thử nghiệp vụ; một bộ test đúng trên mười dòng cũng không thay được đo hiệu năng trên hệ phân tán có replica, TTL và dữ liệu biến động.

## Tài liệu tham khảo

- [Apache Cassandra Documentation — cqlsh: TRACING, PAGING và SHOW SESSION](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html)
- [Apache Cassandra Documentation — CQL SELECT, WHERE, ORDER BY, LIMIT, PER PARTITION LIMIT và ALLOW FILTERING](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html)
- [Apache Cassandra Documentation — Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html)
- [DataStax Java Driver 4.17 — Query Tracing](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/tracing/index.html)
- [Java Driver 4.17 — ExecutionInfo API](https://docs.datastax.com/en/latest-java-driver-api/com/datastax/oss/driver/api/core/cql/ExecutionInfo.html)
- [DataStax Java Driver 4.17 — Paging](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/paging/index.html)
