# Tập kết quả lớn, kích thước lấy dữ liệu và giới hạn tài nguyên

Một câu SQL có thể đúng về mặt logic nhưng vẫn làm ứng dụng chậm, đầy bộ nhớ hoặc ảnh hưởng cả hệ thống nếu nó trả về quá nhiều hàng, mỗi hàng quá rộng, hoặc được đọc nhanh hơn khả năng xử lý của ứng dụng. Khi một endpoint gọi `SELECT *` rồi chuyển toàn bộ kết quả thành danh sách object, chi phí không chỉ nằm ở câu truy vấn. Dữ liệu phải được database đọc, sắp xếp hoặc JOIN, truyền qua mạng, giải mã ở driver, giữ trong bộ nhớ ứng dụng, chuyển thành JSON, rồi có thể tiếp tục đi qua nhiều lớp khác.

**Quản lý tập kết quả lớn** là thiết kế toàn bộ đường đi của dữ liệu: chọn đúng cột và hàng, giới hạn số lượng, phân trang hoặc đọc tuần tự, đặt kích thước fetch/batch phù hợp, điều tiết tốc độ tiêu thụ, hủy công việc khi không còn cần, và giới hạn thời gian/tài nguyên. Mục tiêu không chỉ là “query nhanh”, mà là **một truy vấn có chi phí hữu hạn, có thể dự đoán và không làm cạn tài nguyên của database, connection pool, mạng hoặc ứng dụng**.

> **Nguyên tắc:** trước khi lấy dữ liệu, xác định rõ người gọi cần bao nhiêu hàng, bao nhiêu cột, trong khoảng nào và xử lý chúng theo cách nào. Dùng LIMIT, pagination, cursor/stream hoặc batch phù hợp; đặt timeout và giới hạn đồng thời; đo trên dữ liệu đại diện. Không dựa vào việc “máy chủ có nhiều RAM” để cho phép kết quả không giới hạn.

Bài học thuộc **Database SQL → SQL trong ứng dụng**. Phần thực hành dùng PostgreSQL và ví dụ Java/JDBC, Python, Node.js; đồng thời so sánh MySQL, SQL Server, Oracle và SQLite. Các chủ đề chính gồm cardinality, row width, projection, OFFSET/keyset pagination, cursor streaming, fetch size, backpressure, export, query timeout, connection pool, cancellation, execution plan, index, transaction snapshot và 30 bài tập.

## 1. Vì sao tập kết quả lớn là một vấn đề tài nguyên?

Xét một endpoint:

```sql
SELECT *
FROM orders
WHERE tenant_id = $1;
```

Nếu tenant có vài trăm đơn, truy vấn có thể ổn. Nếu tenant có vài chục triệu đơn, câu SQL không có giới hạn có thể tạo ra một lượng dữ liệu rất lớn. Ngay cả khi database tìm được hàng bằng index, ứng dụng vẫn phải nhận và xử lý tất cả kết quả.

Một yêu cầu đọc lớn tiêu thụ nhiều loại tài nguyên:

| Tài nguyên | Chi phí có thể phát sinh |
| --- | --- |
| CPU database | JOIN, sort, aggregate, biểu thức, chuyển kiểu |
| RAM database | Hash table, sort memory, cursor/portal, buffer cache |
| Disk I/O | Đọc bảng/index, temporary files, spill khi sort/hash |
| Network | Bytes truyền từ database đến ứng dụng |
| RAM ứng dụng | Driver buffers, object graph, list, DTO, JSON serialization |
| CPU ứng dụng | Decode, mapping ORM, validation, compression, format |
| Connection pool | Connection bị giữ trong lúc đọc stream dài |
| Transaction | Snapshot lâu, row versions cũ, vacuum/purge bị cản trở |
| Người dùng khác | Lock, queue, connection starvation, CPU/I/O contention |
| Log/monitoring | Payload lớn, log chậm, dữ liệu nhạy cảm bị ghi quá mức |

### 1.1. Số hàng không phải yếu tố duy nhất

Hai truy vấn đều trả 100.000 hàng nhưng chi phí có thể rất khác:

```sql
SELECT order_id
FROM orders
WHERE tenant_id = $1;
```

và:

```sql
SELECT *
FROM orders
WHERE tenant_id = $1;
```

Truy vấn thứ hai có thể đọc và truyền thêm nhiều cột, JSON lớn, binary, ghi chú dài hoặc dữ liệu không cần dùng. Vì vậy, cần nhìn cả:

- **Cardinality:** có bao nhiêu hàng.
- **Row width:** mỗi hàng rộng bao nhiêu byte.
- **Selectivity:** điều kiện lọc giữ lại tỷ lệ bao nhiêu hàng.
- **Result bytes:** tổng dung lượng dữ liệu trả về.
- **Consumption rate:** ứng dụng đọc và xử lý nhanh đến đâu.
- **Lifetime:** connection, cursor và transaction bị giữ bao lâu.

### 1.2. Ước lượng thô dung lượng

Giả sử một kết quả có 500.000 hàng, trung bình 1,5 KB dữ liệu sau khi decode:

\[
500\,000 \times 1.5\text{ KB} \approx 750\text{ MB}
\]

Con số thực tế có thể cao hơn vì mỗi object trong Java/Python/JavaScript còn có overhead, string encoding, pointer, collection capacity, DTO, JSON buffer và bản sao tạm. Một ứng dụng có thể dùng RAM gấp nhiều lần kích thước payload nhận được.

Không nên dùng phép tính này làm số đo chính xác. Nó giúp thấy vì sao một query “chỉ vài trăm nghìn hàng” có thể làm heap tăng nhanh.

### 1.3. Database trả kết quả nhanh không có nghĩa endpoint nhanh

Thời gian người dùng cảm nhận có thể gồm:

```text
Request
  -> kiểm quyền và validate
  -> lấy connection
  -> parse/plan/execute SQL
  -> database đọc dữ liệu
  -> truyền kết quả qua network
  -> driver decode
  -> ứng dụng map object
  -> serialize JSON/CSV
  -> gửi response
```

Nếu database chạy 100 ms nhưng ứng dụng map 2 triệu object trong 15 giây, tối ưu index không giải quyết được toàn bộ vấn đề. Hãy đo từng chặng, không chỉ nhìn duration của SQL.

## 2. Xác định hợp đồng dữ liệu trước khi truy vấn

Trước khi viết query, hãy trả lời:

1. Người gọi cần **một hàng**, một trang, một báo cáo tổng hợp hay toàn bộ dữ liệu?
2. Có giới hạn nghiệp vụ tối đa không?
3. Những cột nào thực sự cần?
4. Khoảng thời gian hoặc phạm vi tenant nào được phép?
5. Thứ tự kết quả có cần ổn định không?
6. Có thể xử lý tuần tự từng hàng không, hay cần giữ toàn bộ kết quả để tính toán?
7. Người dùng có thể hủy request giữa chừng không?
8. Có cần một snapshot nhất quán xuyên nhiều trang không?
9. Tác vụ chạy đồng bộ trong HTTP request hay nền theo job?
10. Thời gian, RAM, network và số connection tối đa là bao nhiêu?

### 2.1. Các kiểu yêu cầu khác nhau cần cách đọc khác nhau

| Nhu cầu | Cách truy xuất thường phù hợp |
| --- | --- |
| Chi tiết một bản ghi | SELECT theo khóa, tối đa một hàng |
| Danh sách trên giao diện | Pagination, page size có giới hạn |
| Autocomplete | Prefix/search có giới hạn nhỏ, timeout ngắn |
| Dashboard | Aggregate trong database, trả số liệu đã thu gọn |
| Export hàng trăm nghìn dòng | Streaming/cursor hoặc job nền theo batch |
| Đồng bộ dữ liệu | Keyset/checkpoint, batch, idempotency |
| Tính toán cần toàn bộ tập | Đưa aggregate/join vào SQL hoặc xử lý theo partition/batch |
| Báo cáo nhiều trang cần snapshot | Transaction/snapshot hoặc materialized report theo thiết kế |
| Queue worker | Claim một batch, xử lý và xác nhận theo trạng thái |
| Tải file lớn | Job nền, object storage, link tải có thời hạn |

Một endpoint danh sách thông thường không nên âm thầm trở thành công cụ export không giới hạn chỉ vì query có thể trả mọi hàng.

## 3. Tạo dữ liệu PostgreSQL thực hành

Các ví dụ dưới đây dùng bảng `TEMP` trong một session PostgreSQL. Chạy các lệnh tạo bảng và truy vấn trên **cùng session**. Nếu chạy qua JDBC, Python hoặc Node bằng một connection khác, hãy tạo lại dữ liệu mẫu trong chính connection đó hoặc dùng schema lab riêng.

```sql
CREATE TEMP TABLE demo_large_customers (
    tenant_id INTEGER NOT NULL,
    customer_id INTEGER NOT NULL,
    display_name TEXT NOT NULL,
    email TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, customer_id)
);

CREATE TEMP TABLE demo_large_orders (
    tenant_id INTEGER NOT NULL,
    order_id BIGINT NOT NULL,
    customer_id INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('PAID', 'PENDING', 'CANCELED')
    ),
    amount NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
    note TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, order_id),
    FOREIGN KEY (tenant_id, customer_id)
        REFERENCES demo_large_customers (tenant_id, customer_id)
);

INSERT INTO demo_large_customers VALUES
    (10, 1, 'An', 'an@example.com', '2026-10-01 08:00:00+07'),
    (10, 2, 'Bình', 'binh@example.com', '2026-10-02 08:00:00+07'),
    (10, 3, 'Chi', 'chi@example.com', '2026-10-03 08:00:00+07'),
    (20, 1, 'An tenant 20', 'an20@example.com', '2026-10-01 08:00:00+07');

INSERT INTO demo_large_orders (
    tenant_id, order_id, customer_id, status, amount,
    note, payload, created_at
)
SELECT
    10,
    n,
    ((n - 1) % 3) + 1,
    CASE
        WHEN n % 10 = 0 THEN 'CANCELED'
        WHEN n % 3 = 0 THEN 'PENDING'
        ELSE 'PAID'
    END,
    (n % 10000)::NUMERIC / 10,
    CASE
        WHEN n % 5 = 0 THEN repeat('Long note ', 30)
        ELSE 'Short note'
    END,
    jsonb_build_object(
        'source', CASE WHEN n % 2 = 0 THEN 'web' ELSE 'mobile' END,
        'sequence', n,
        'tags', jsonb_build_array('demo', 'order')
    ),
    TIMESTAMPTZ '2026-10-01 00:00:00+07'
        + n * INTERVAL '1 second'
FROM generate_series(1, 10000) AS n;

INSERT INTO demo_large_orders (
    tenant_id, order_id, customer_id, status, amount,
    note, payload, created_at
)
VALUES
    (20, 1, 1, 'PAID', 999.00, 'Other tenant',
     '{"source":"partner"}', '2026-10-15 10:00:00+07');
```

Kiểm kích thước lab:

```sql
SELECT
    tenant_id,
    COUNT(*) AS order_count,
    MIN(order_id) AS min_order_id,
    MAX(order_id) AS max_order_id
FROM demo_large_orders
GROUP BY tenant_id
ORDER BY tenant_id;
```

Tenant 10 có 10.000 đơn. Tenant 20 có một đơn. Sự lệch phân bố này hữu ích khi thảo luận plan, phân trang và giới hạn phạm vi.

## 4. Chỉ lấy những cột cần thiết

`SELECT *` thường thuận tiện khi thử nghiệm, nhưng là lựa chọn kém cho endpoint hoặc export có contract rõ.

Ví dụ chỉ cần danh sách order:

```sql
SELECT
    order_id,
    status,
    amount,
    created_at
FROM demo_large_orders
WHERE tenant_id = $1
ORDER BY created_at DESC, order_id DESC
LIMIT $2;
```

Không cần tải `note` dài và `payload` JSONB nếu response không sử dụng chúng.

### 4.1. Projection giảm row width

Projection là chọn các cột cần thiết trong `SELECT`. Nó có thể giảm:

- Số byte đọc/truyền.
- Công việc decode ở driver.
- Số object/string tạo trong ứng dụng.
- Dung lượng response và chi phí serialize.
- Rủi ro lộ dữ liệu không cần thiết.

Một số DBMS có thể tận dụng covering/index-only access nếu index chứa đủ cột cần thiết và điều kiện khác phù hợp. Nhưng không thêm mọi cột vào index chỉ để tránh table lookup: index lớn làm tăng dung lượng, chi phí ghi và cache pressure.

### 4.2. Tránh tải blob/JSON lớn ở danh sách

Nếu giao diện chỉ hiển thị tên, trạng thái và ngày, hãy để endpoint chi tiết lấy payload lớn theo khóa sau khi người dùng mở một bản ghi.

Mẫu hai bước:

```sql
-- Danh sách nhẹ
SELECT order_id, status, amount, created_at
FROM demo_large_orders
WHERE tenant_id = $1
ORDER BY created_at DESC, order_id DESC
LIMIT $2;

-- Chi tiết chỉ khi cần
SELECT order_id, note, payload
FROM demo_large_orders
WHERE tenant_id = $1
  AND order_id = $2;
```

Cần bảo đảm cả query chi tiết cũng kiểm tenant/quyền. Không tải payload lớn cho tất cả hàng chỉ để một số ít người dùng mở chi tiết.

### 4.3. Không chuyển toàn bộ bảng thành JSON trong SQL nếu không cần

`json_agg`/`jsonb_agg` có thể hữu ích khi trả cấu trúc JSON nhỏ, nhưng gom hàng trăm nghìn hàng thành một JSON array duy nhất có thể tạo một giá trị rất lớn trong database và ứng dụng. Việc kết quả chỉ có **một hàng SQL** không có nghĩa payload nhỏ.

Nếu cần export lớn, hãy cân nhắc stream từng hàng hoặc chia file theo batch thay vì một JSON document khổng lồ.

## 5. LIMIT là hàng rào đầu tiên, nhưng không phải toàn bộ giải pháp

Một query danh sách nên có giới hạn:

```sql
SELECT order_id, status, amount, created_at
FROM demo_large_orders
WHERE tenant_id = 10
ORDER BY order_id
LIMIT 50;
```

`LIMIT 50` giới hạn số hàng được trả về cho client. Tuy nhiên, nó không đảm bảo database chỉ đọc 50 hàng: nếu cần sort nhiều hàng hoặc lọc kém chọn lọc, engine vẫn có thể phải xử lý một tập lớn trước khi biết 50 hàng đầu.

### 5.1. LIMIT không thay thế predicate

Sai về phạm vi:

```sql
SELECT *
FROM demo_large_orders
ORDER BY order_id
LIMIT 50;
```

Nếu endpoint thuộc tenant 10, query phải có điều kiện tenant được xác thực. `LIMIT` không bảo đảm 50 hàng ấy thuộc đúng tenant.

### 5.2. Giới hạn từ ứng dụng

Không để client tùy ý yêu cầu page size vô hạn. Ví dụ contract:

```text
default page size = 25
minimum page size = 1
maximum page size = 100
maximum export rows per synchronous request = 5,000
```

Đây chỉ là các giá trị minh họa. Chọn giới hạn dựa trên kích thước hàng, latency, khả năng server, UX và SLA thực tế.

Validate trước khi bind:

```java
int limit = requestedLimit == null ? 25 : requestedLimit;
if (limit < 1 || limit > 100) {
    throw new IllegalArgumentException("Page size must be 1..100");
}
```

Một `LIMIT 100000000` được bind hoàn toàn an toàn khỏi injection, nhưng vẫn có thể làm cạn RAM, network hoặc thời gian xử lý.

### 5.3. LIMIT cần ORDER BY ổn định

```sql
SELECT order_id, created_at
FROM demo_large_orders
WHERE tenant_id = 10
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Nếu chỉ `ORDER BY created_at DESC` và nhiều hàng có cùng timestamp, database có thể trả các hàng đồng hạng theo thứ tự không xác định. Thêm khóa duy nhất làm tie-breaker để kết quả trang có thứ tự xác định trên cùng snapshot.

Không dựa vào thứ tự vật lý của bảng, thứ tự insert hoặc index tình cờ.

## 6. Pagination: OFFSET/LIMIT

OFFSET pagination thường dễ dùng cho giao diện có số trang:

```sql
SELECT order_id, status, amount, created_at
FROM demo_large_orders
WHERE tenant_id = 10
ORDER BY created_at DESC, order_id DESC
LIMIT 25 OFFSET 0;
```

Trang tiếp theo:

```sql
SELECT order_id, status, amount, created_at
FROM demo_large_orders
WHERE tenant_id = 10
ORDER BY created_at DESC, order_id DESC
LIMIT 25 OFFSET 25;
```

Trang thứ ba dùng OFFSET 50, v.v.

### 6.1. OFFSET lớn có thể đắt

Giả sử cần trang 20.000 với 25 hàng/trang. Database có thể phải xác định/đi qua khoảng 500.000 hàng trước khi bỏ chúng và trả 25 hàng tiếp theo, tùy plan/index.

OFFSET không phải một vị trí miễn phí trong bảng. Nó thường là số hàng phải bỏ qua trong kết quả đã sắp xếp.

### 6.2. Dữ liệu thay đổi giữa các trang

Giả sử trang đầu trả các ID:

```text
100, 99, 98, 97, 96
```

Trước khi lấy trang hai bằng `OFFSET 5`, một hàng mới được thêm vào đầu thứ tự:

```text
101, 100, 99, 98, 97, 96, ...
```

OFFSET 5 có thể bắt đầu ở 96; người dùng thấy 96 lặp lại. Nếu một hàng bị xóa trước vị trí offset, có thể bỏ sót một hàng.

Ngay cả khi có ORDER BY ổn định, **các trang chạy ở những snapshot khác nhau** vẫn có thể thay đổi do insert/delete/update.

### 6.3. Khi OFFSET phù hợp

OFFSET thường hợp lý khi:
- Tập kết quả nhỏ hoặc vừa.
- Người dùng cần nhảy đến số trang cụ thể.
- Page number không quá sâu.
- Dữ liệu ít biến động hoặc contract chấp nhận thay đổi giữa trang.
- Index và query plan đáp ứng SLA.

Đối với danh sách lớn, deep pagination hoặc export, hãy cân nhắc keyset/cursor.

## 7. Keyset pagination (seek pagination)

Keyset pagination dùng **giá trị cuối cùng của trang trước** làm cursor để tìm trang tiếp theo, thay vì đếm và bỏ qua một số hàng lớn.

Ví dụ sắp xếp mới nhất trước:

```sql
SELECT order_id, created_at, status, amount
FROM demo_large_orders
WHERE tenant_id = $1
  AND (created_at, order_id) < ($2, $3)
ORDER BY created_at DESC, order_id DESC
LIMIT $4;
```

Tham số:
- `$1`: tenant đã được xác thực.
- `$2`: `created_at` của hàng cuối trang trước.
- `$3`: `order_id` của hàng cuối trang trước.
- `$4`: page size đã giới hạn.

Lần đầu chưa có cursor thì dùng query shape riêng:

```sql
SELECT order_id, created_at, status, amount
FROM demo_large_orders
WHERE tenant_id = $1
ORDER BY created_at DESC, order_id DESC
LIMIT $2;
```

### 7.1. Vì sao cần cả hai cột trong cursor?

Nếu chỉ dùng:

```sql
WHERE created_at < $last_created_at
```

các hàng có timestamp bằng `last_created_at` nhưng order_id khác có thể bị bỏ qua. Thứ tự `(created_at DESC, order_id DESC)` được xác định bởi cả hai giá trị; cursor phải mang đủ hai giá trị.

### 7.2. Cách viết tương đương không dùng row comparison

Trong PostgreSQL, với cả hai cột không NULL và cùng thứ tự DESC:

```sql
WHERE created_at < $last_created_at
   OR (
       created_at = $last_created_at
       AND order_id < $last_order_id
   )
```

Điều kiện tương quan phải phản ánh đúng từng hướng sort. Nếu một cột ASC và cột khác DESC, phải viết điều kiện lexicographic tương ứng; không sao chép máy móc dấu `<`.

### 7.3. Cursor cần được đóng gói an toàn

API có thể trả cursor opaque chứa:
- Giá trị sort cuối cùng.
- Các tie-breaker.
- Phiên bản cấu trúc cursor.
- Có thể cả bộ lọc hoặc fingerprint của query.
- Chữ ký/HMAC nếu client không được sửa nội dung.

Ví dụ payload nội bộ:

```json
{
  "v": 1,
  "createdAt": "2026-10-01T02:46:40Z",
  "orderId": 10000
}
```

Đừng tin cursor do client sửa. Validate định dạng, kiểu, độ dài và gắn cursor với filter/tenant thích hợp. Nếu cursor chứa dữ liệu nhạy cảm, không trả nguyên nội dung chưa bảo vệ.

### 7.4. Keyset không giải quyết mọi thay đổi dữ liệu

Keyset giảm vấn đề deep offset và thường tránh lặp/bỏ sót do insert mới đứng trước cursor. Nhưng nếu cột sort của một hàng **bị cập nhật vượt qua vị trí cursor**, hàng đó có thể xuất hiện lặp hoặc bị bỏ qua. Hãy dùng cột sort bất biến khi có thể, hoặc định nghĩa snapshot/version semantics.

### 7.5. Khi nào keyset phù hợp?

- Feed và danh sách lớn theo thứ tự thời gian.
- Export tiếp tục từ checkpoint.
- Job đồng bộ từng batch.
- Không cần nhảy thẳng đến page number rất sâu.
- Có khóa sort ổn định, unique tie-breaker và index phù hợp.

## 8. Snapshot nhất quán giữa nhiều trang

Một vấn đề khác là **cùng một tập dữ liệu tại một thời điểm**. Nếu người dùng duyệt nhiều trang trong vài phút, dữ liệu có thể được thêm/sửa/xóa trong lúc họ đọc.

Có nhiều contract:

| Contract | Ý nghĩa | Đánh đổi |
| --- | --- | --- |
| Mỗi trang đọc snapshot mới | Dữ liệu cập nhật liên tục | Trang có thể thay đổi/thiếu/lặp |
| Snapshot trong một transaction dài | Các trang nhìn cùng snapshot theo isolation phù hợp | Giữ connection và snapshot lâu |
| Snapshot/materialized report | Tạo tập dữ liệu báo cáo cố định | Cần storage, lifecycle và refresh |
| Watermark/checkpoint | Chỉ đọc dữ liệu đến một mốc xác định | Cần khóa sort và quy tắc dữ liệu late-arriving |
| Versioned dataset | Mỗi lần đọc gắn với phiên bản dữ liệu | Phức tạp hơn nhưng rõ semantics |

### 8.1. Transaction dài có chi phí

Trong PostgreSQL, transaction giữ snapshot lâu có thể khiến VACUUM không thu hồi được một số row versions cũ còn cần cho snapshot. Ở hệ khác có cơ chế versioning/undo riêng, nhưng transaction dài cũng tiêu thụ tài nguyên và connection.

Không giữ một transaction HTTP mở hàng chục phút chỉ để người dùng bấm qua từng trang, trừ khi có thiết kế và lý do rõ ràng.

### 8.2. Watermark

Một job có thể xác định mốc:

```sql
SELECT MAX(order_id)
FROM demo_large_orders
WHERE tenant_id = 10;
```

Sau đó chỉ xử lý các hàng có `order_id <= watermark`. Cách này hữu ích nếu ID tăng đơn điệu và quy tắc dữ liệu đảm bảo hàng đến muộn không mang ID nhỏ hơn watermark. Nếu ID có thể được nhập lại, sort key không bất biến hoặc hàng cũ được sửa, watermark đơn giản chưa đủ.

### 8.3. Export cần snapshot rõ ràng

Nếu export phải phản ánh đúng cùng một thời điểm, có thể:
- Tạo bảng staging/materialized snapshot theo export job.
- Dùng transaction isolation phù hợp trong một worker có thời hạn.
- Chốt watermark và ghi rõ semantics của dữ liệu đến muộn.
- Lưu report version rồi stream từ phiên bản ấy.

Chọn theo yêu cầu nghiệp vụ và khả năng vận hành; không mặc định một cách pagination tự cung cấp snapshot toàn bộ.

## 9. Cursor và streaming: đọc tuần tự thay vì giữ toàn bộ kết quả

Pagination chia kết quả thành các request/trang. Streaming đọc kết quả liên tục theo từng phần nhỏ, thường hữu ích cho export hoặc xử lý tuần tự.

### 9.1. Streaming ở mức ý tưởng

```text
Mở query/cursor
  -> database trả một phần hàng
  -> ứng dụng xử lý phần ấy
  -> driver lấy phần tiếp theo
  -> lặp cho tới hết hoặc cancel
Đóng ResultSet/cursor/connection đúng lifecycle
```

Streaming có thể giảm peak memory vì ứng dụng không cần giữ toàn bộ kết quả. Nhưng nó không miễn phí:
- Connection có thể bị giữ suốt thời gian stream.
- Transaction/snapshot có thể tồn tại lâu.
- Network chậm khiến cursor sống lâu.
- Nếu ứng dụng dừng tiêu thụ mà không đóng, tài nguyên có thể bị giữ.
- Driver có thể buffer nhiều hơn mong đợi nếu cấu hình sai.

### 9.2. Streaming không đồng nghĩa database không cần RAM

Database vẫn có thể cần sort/hash/temporary data để tạo kết quả. Nếu query có `ORDER BY` trên cột không được index hỗ trợ, server có thể phải xử lý và sort tập lớn trước khi gửi hàng đầu tiên.

Streaming chủ yếu kiểm soát **đường truyền và bộ nhớ phía client**, không tự làm execution plan rẻ hơn.

### 9.3. Cursor khác pagination

| Đặc điểm | Pagination | Cursor/stream |
| --- | --- | --- |
| Đơn vị | Một trang theo request | Một luồng đọc liên tục |
| Connection | Có thể trả về pool giữa các trang | Thường giữ connection khi cursor hoạt động |
| Resume | Cursor token/keyset có thể lưu | Có thể cần mở lại từ checkpoint |
| UI | Phù hợp page controls | Phù hợp export/worker |
| Hủy | Dừng request/trang hiện tại | Cần cancel và đóng cursor |
| Snapshot | Mỗi trang có thể là snapshot khác | Có thể giữ snapshot transaction lâu |
| Backpressure | Theo request/page | Theo tốc độ consumer và fetch |

Không chọn cursor chỉ vì “nghe streaming tiết kiệm RAM”; hãy xét connection lifetime, transaction, driver và tốc độ consumer.

## 10. JDBC: ResultSet, fetch size và cursor

Trong JDBC, `Statement.setFetchSize()` là **gợi ý cho driver** về số hàng nên lấy mỗi lượt. Ý nghĩa thực tế tùy driver/database. Nó không phải `LIMIT` và không bảo đảm mọi driver sẽ stream đúng cách.

Ví dụ PostgreSQL JDBC với cursor-based fetching thường cần:
- Autocommit tắt.
- ResultSet forward-only.
- Fetch size dương.
- Transaction còn mở trong khi đọc.
- Đóng ResultSet/Statement/commit hoặc rollback đúng cách.

```java
String sql = """
    SELECT order_id, status, amount, created_at
    FROM demo_large_orders
    WHERE tenant_id = ?
    ORDER BY order_id
    """;

try (Connection conn = dataSource.getConnection()) {
    conn.setAutoCommit(false);

    try (PreparedStatement ps = conn.prepareStatement(
            sql,
            ResultSet.TYPE_FORWARD_ONLY,
            ResultSet.CONCUR_READ_ONLY
    )) {
        ps.setInt(1, 10);
        ps.setFetchSize(500);

        try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                long orderId = rs.getLong("order_id");
                String status = rs.getString("status");
                BigDecimal amount = rs.getBigDecimal("amount");

                processOneOrder(orderId, status, amount);
            }
        }

        conn.commit();
    } catch (Exception ex) {
        conn.rollback();
        throw ex;
    }
}
```

`processOneOrder` là hàm ứng dụng giả định. Nếu nó gọi dịch vụ chậm hoặc làm công việc rất lâu, connection/transaction vẫn bị giữ. Trong thực tế cần thiết kế timeout, cancellation, error handling và resource lifecycle theo framework/pool.

### 10.1. Fetch size là batch transfer hint

`setFetchSize(500)` không có nghĩa database chỉ trả tối đa 500 hàng. Nó thường là gợi ý lấy kết quả theo từng nhóm, trong khi ResultSet vẫn có thể duyệt hết hàng triệu hàng.

- Fetch size quá nhỏ: nhiều round trips.
- Fetch size quá lớn: nhiều buffer và memory.
- Fetch size vừa phải: cân bằng network latency, memory và tốc độ consumer.

Hãy benchmark theo kích thước hàng thực tế, không chọn số 500 như một chuẩn cố định.

### 10.2. PostgreSQL JDBC và autocommit

Với PostgreSQL JDBC, cursor-based fetching thường yêu cầu transaction không autocommit. Nếu để autocommit mặc định và đặt fetch size, driver có thể không dùng server cursor như bạn mong đợi và có thể buffer toàn bộ kết quả. Kiểm tài liệu driver/version và xác minh bằng đo memory/network.

### 10.3. ResultSet phải đóng trước khi trả connection về pool

Không trả connection về pool khi ResultSet/Statement còn mở. Không giữ ResultSet qua nhiều thread hoặc sau khi connection đã đóng. Dùng try-with-resources hoặc framework quản lý stream có lifecycle rõ.

### 10.4. Đừng map toàn bộ kết quả vào List

Mẫu tốn bộ nhớ:

```java
List<OrderDto> all = new ArrayList<>();
while (rs.next()) {
    all.add(map(rs));
}
return all;
```

Nếu kết quả lớn, `all` giữ mọi DTO cho đến khi request kết thúc. Thay bằng xử lý tuần tự hoặc stream có giới hạn, hoặc job nền ghi từng batch vào output.

## 11. Python: fetchone, fetchmany, fetchall và server-side cursor

DB-API thường cung cấp:
- `fetchone()`: lấy một hàng.
- `fetchmany(size)`: lấy một nhóm.
- `fetchall()`: lấy toàn bộ phần còn lại.

`fetchmany()` giúp code xử lý theo batch, nhưng **không phải mọi driver đều bảo đảm server chỉ gửi từng batch**. Một số cursor mặc định vẫn buffer toàn bộ kết quả ở client. Cần phân biệt cursor client-side và server-side của driver.

### 11.1. fetchall có thể làm tăng peak memory

```python
cur.execute(
    "SELECT order_id, amount FROM orders WHERE tenant_id = %s",
    (tenant_id,),
)
rows = cur.fetchall()
```

Nếu hàng triệu dòng, `rows` chứa toàn bộ tập kết quả. Nếu sau đó còn tạo thêm list DTO và JSON string, có thể giữ nhiều bản sao trong RAM.

### 11.2. fetchmany xử lý theo batch

```python
cur.execute(
    """
    SELECT order_id, amount
    FROM orders
    WHERE tenant_id = %s
    ORDER BY order_id
    """,
    (tenant_id,),
)

while True:
    batch = cur.fetchmany(500)
    if not batch:
        break

    process_batch(batch)
```

Đoạn này minh họa batch ở API DB-API. Tính streaming thực tế còn phụ thuộc cursor/driver. `process_batch` không nên giữ lại tất cả batch trong một list khác, nếu mục tiêu là giới hạn memory.

### 11.3. Psycopg named cursor

Với psycopg, server-side cursor (named cursor) có thể giúp lấy dữ liệu theo từng phần:

```python
import psycopg

with psycopg.connect("dbname=training user=training_user") as conn:
    with conn.cursor(name="large_order_export") as cur:
        cur.itersize = 500
        cur.execute(
            """
            SELECT order_id, status, amount
            FROM demo_large_orders
            WHERE tenant_id = %s
            ORDER BY order_id
            """,
            (10,),
        )

        for row in cur:
            process_one(row)
```

Đây là ví dụ theo API psycopg; cách cursor, transaction và `itersize` cụ thể khác giữa psycopg 2/3 và driver. Hãy kiểm tài liệu phiên bản đang dùng. Named cursor thường gắn với transaction/connection; đừng đóng transaction giữa lúc duyệt.

### 11.4. Generator không tự bảo đảm driver streaming

Một hàm Python `yield` có thể phát từng row, nhưng nếu trước đó gọi `fetchall()` rồi mới yield, toàn bộ kết quả đã được buffer. Hãy xem **nguồn dữ liệu** của generator, không chỉ hình thức `yield`.

## 12. Node.js: stream, async iteration và backpressure

Node.js có thể dùng cursor/stream APIs tùy package. Một cách xử lý theo async iterator:

```javascript
for await (const row of queryStream) {
  await processRow(row);
}
```

Đây chỉ là dạng minh họa; `queryStream` phải là stream/cursor thực sự từ driver hoặc thư viện hỗ trợ. `pool.query()` thông thường có thể thu thập tất cả rows trước khi trả `result.rows`, không nên giả định nó stream chỉ vì code có `async`.

### 12.1. Backpressure

Nếu database phát 10.000 hàng/giây nhưng ứng dụng chỉ xử lý 500 hàng/giây, buffer sẽ tăng dần nếu producer không bị điều tiết.

**Backpressure** là cơ chế để consumer chậm có thể làm producer tạm dừng hoặc giảm tốc. Với Node stream, cần tôn trọng tín hiệu `write()` trả `false`, sự kiện `drain`, `pipeline()` và cơ chế hủy/error theo thư viện.

### 12.2. Không dùng async callback của forEach để xử lý stream

Mẫu dễ sai:

```javascript
rows.forEach(async (row) => {
  await processRow(row);
});
```

`forEach` không đợi các Promise callback hoàn tất. Ứng dụng có thể khởi tạo hàng nghìn tác vụ song song, vượt giới hạn connection/API hoặc báo hoàn thành trước khi xử lý xong.

Nếu cần tuần tự:

```javascript
for (const row of rows) {
  await processRow(row);
}
```

Nếu cần concurrency giới hạn, dùng worker pool/semaphore có giới hạn rõ ràng, không tạo Promise không giới hạn.

### 12.3. Stream ra HTTP response cần xử lý client disconnect

Nếu client đóng kết nối giữa lúc export, ứng dụng cần:
- Hủy query/cursor nếu không còn cần.
- Đóng ResultSet/stream.
- Giải phóng connection.
- Không tiếp tục serialize hàng triệu dòng vào buffer vô ích.
- Ghi nhận trạng thái job phù hợp.

Không phải mọi framework tự cancel database query khi HTTP client disconnect; phải xác minh wiring thực tế.

## 13. Batch processing và checkpoint

Đối với job xử lý hàng triệu bản ghi, batch thường là một lựa chọn dễ vận hành hơn một transaction khổng lồ hoặc một request HTTP kéo dài.

Mô hình:

```text
last_key = checkpoint đã xác nhận

lặp:
    lấy tối đa B hàng sau last_key
    xử lý batch
    ghi kết quả/checkpoint trong transaction phù hợp
    commit
    last_key = khóa cuối đã xử lý thành công
    nếu batch rỗng: kết thúc
```

### 13.1. Keyset batch

```sql
SELECT order_id, status, amount
FROM demo_large_orders
WHERE tenant_id = $1
  AND order_id > $2
ORDER BY order_id
LIMIT $3;
```

Trong đó:
- `$1`: tenant.
- `$2`: last order ID.
- `$3`: batch size.

Mỗi batch có kích thước hữu hạn. Khi thành công, job lưu checkpoint mới.

### 13.2. Checkpoint phải gắn với kết quả đã commit

Nếu job cập nhật checkpoint trước khi kết quả batch được commit, crash có thể khiến một đoạn dữ liệu bị bỏ qua. Nếu commit dữ liệu xong nhưng checkpoint chưa commit, job có thể xử lý lại batch. Vì vậy cần transaction chung khi có thể, hoặc thiết kế thao tác **idempotent** và có trạng thái chống trùng.

### 13.3. Batch không có nghĩa atomic toàn job

Nếu mỗi batch commit riêng, job có thể hoàn thành một phần trước khi lỗi. Điều này khác một transaction duy nhất all-or-nothing. Hãy quyết định:
- Có chấp nhận partial progress?
- Có thể chạy lại batch?
- Kết quả có idempotent không?
- Có thể resume từ checkpoint?
- Có bảng reject/error records không?
- Khi hủy, trạng thái job là gì?

### 13.4. Chọn batch size bằng đo đạc

Batch size 100, 500, 2.000 hay 10.000 không có đáp án chung. Nó phụ thuộc row width, số index phải cập nhật, trigger, WAL/transaction log, network, thời gian xử lý mỗi hàng và concurrency. Bắt đầu vừa phải rồi đo throughput, p95 latency, memory, lock time và replication lag.

### 13.5. OFFSET không lý tưởng cho checkpoint trên tập thay đổi

Nếu job vừa đọc vừa cập nhật/xóa các hàng nằm trong tập query, vị trí OFFSET có thể dịch chuyển. Keyset trên khóa ổn định thường dễ resume và tránh bỏ qua hàng do thay đổi vị trí.

## 14. Giới hạn tài nguyên: timeout, row cap, byte cap và concurrency

Một hệ thống nên có nhiều hàng rào, vì mỗi hàng rào giải quyết một kiểu chi phí khác nhau.

| Hàng rào | Giới hạn điều gì? | Ví dụ |
| --- | --- | --- |
| Predicate/scope | Tập dữ liệu được phép | tenant, trạng thái, khoảng ngày |
| LIMIT/page size | Số hàng trả về | tối đa 100 |
| Projection | Số cột mỗi hàng | chỉ ID, status, amount |
| Byte/field size cap | Dữ liệu quá rộng | giới hạn blob/note |
| Query timeout | Thời gian SQL | statement timeout |
| Request timeout | Thời gian endpoint | HTTP deadline |
| Pool size | Số connection đồng thời | max pool |
| Worker concurrency | Số tác vụ đang chạy | tối đa N export |
| Rate limit | Tần suất gọi | requests/minute |
| Job quota | Khối lượng export | max rows/bytes per job |
| Cancellation | Công việc không còn cần | client disconnect/cancel |
| Monitoring | Phát hiện vượt ngưỡng | memory, latency, pool wait |

### 14.1. Timeout ở database

PostgreSQL có `statement_timeout` và các cơ chế timeout liên quan. Có thể thiết lập theo session/transaction hoặc cấu hình role/database tùy chính sách. Ví dụ trong session lab:

```sql
SET statement_timeout = '5s';

SELECT COUNT(*)
FROM demo_large_orders
WHERE tenant_id = 10;

RESET statement_timeout;
```

Giá trị 5 giây chỉ là ví dụ. Không nên đặt một timeout chung quá ngắn cho mọi query nếu hệ thống có tác vụ báo cáo hợp lệ cần thời gian dài; có thể tách workload/report role hoặc job queue với deadline khác.

### 14.2. Lock timeout khác statement timeout

`lock_timeout` giới hạn thời gian chờ lock trong PostgreSQL; `statement_timeout` giới hạn thời gian statement tổng thể. Query có thể chờ lock hoặc chạy CPU/I/O lâu. Chọn đúng loại timeout và xử lý lỗi tương ứng.

### 14.3. Timeout ở application không tự dừng database query

Nếu HTTP server trả timeout nhưng câu SQL vẫn chạy ở database, tài nguyên vẫn bị chiếm. Driver/framework cần hỗ trợ cancel statement; application phải gọi cancellation khi request hết hạn hoặc client disconnect, rồi đóng tài nguyên. Cần kiểm thử thực tế, không giả định timeout của reverse proxy sẽ hủy query.

### 14.4. Connection pool là hàng rào quan trọng

Nếu mỗi request export mở một connection và giữ 10 phút, vài chục export có thể chiếm hết pool. Các request ngắn khác phải chờ hoặc timeout.

Giải pháp có thể gồm:
- Export chạy trong worker pool riêng.
- Giới hạn số export đồng thời.
- Dùng connection pool/reporting role riêng khi kiến trúc phù hợp.
- Timeout và quota theo job.
- Không giữ connection khi đang chờ người dùng hoặc dịch vụ ngoài DB.
- Đóng cursor/statement ngay khi xong hoặc cancel.

### 14.5. Đừng tăng pool size để che query chậm

Pool lớn hơn có thể tăng concurrency đến database và làm CPU/I/O/lock contention nghiêm trọng hơn. Hãy đo pool wait, active connections, query latency và DB saturation trước khi tăng.

## 15. COUNT(*) và total count cho pagination

UI thường muốn hiển thị “trang 3 trên 200” hoặc “10.000 kết quả”. Để làm vậy, ứng dụng có thể chạy:

```sql
SELECT COUNT(*)
FROM demo_large_orders
WHERE tenant_id = $1
  AND status = $2;
```

COUNT chính xác có thể tốn chi phí lớn trên tập dữ liệu rộng hoặc predicate phức tạp, dù kết quả chỉ là một hàng.

### 15.1. Không phải lúc nào cũng cần total count

Một giao diện infinite scroll thường chỉ cần biết **có trang tiếp theo không**. Có thể lấy `page_size + 1` hàng:
- Trả `page_size` hàng đầu.
- Nếu có hàng thứ `page_size + 1`, đánh dấu `hasNext = true`.
- Bỏ hàng phụ khỏi response.

Ví dụ:

```sql
SELECT order_id, created_at, amount
FROM demo_large_orders
WHERE tenant_id = $1
ORDER BY order_id
LIMIT $2; -- application truyền page_size + 1
```

Cách này tránh yêu cầu total count chính xác ở mỗi lần tải trang.

### 15.2. Exact count và approximate count

Nếu business bắt buộc số chính xác, chạy COUNT phù hợp với filter và snapshot/transaction semantics. Nếu chỉ cần ước lượng dashboard, có thể dùng thống kê hoặc cache/summary table, nhưng phải ghi rõ **đây là số gần đúng hoặc có độ trễ**.

Không thay exact count bằng approximate count mà không thông báo thay đổi contract.

### 15.3. COUNT(*) OVER() có thể vẫn xử lý toàn bộ tập

Một mẫu:

```sql
SELECT
    order_id,
    amount,
    COUNT(*) OVER() AS total_count
FROM demo_large_orders
WHERE tenant_id = 10
ORDER BY order_id
LIMIT 25;
```

Có thể tiện vì trả total cùng trang, nhưng window count thường cần tính trên toàn bộ tập phù hợp trước khi kết quả trang hoàn tất. Nó không đảm bảo rẻ hơn một COUNT riêng và có thể làm mất lợi ích early-stop của LIMIT. Hãy xem plan và workload.

## 16. Aggregate trong database thay vì kéo mọi hàng về ứng dụng

Nếu cần tổng doanh thu theo trạng thái, không cần lấy từng order để cộng trong Java/Python:
 
```sql
SELECT
    status,
    COUNT(*) AS order_count,
    SUM(amount) AS total_amount
FROM demo_large_orders
WHERE tenant_id = 10
GROUP BY status
ORDER BY status;
```

Kết quả chỉ có vài hàng. Database có thể dùng aggregate và truyền kết quả nhỏ hơn nhiều.

### 16.1. Đẩy phép tính gần dữ liệu khi hợp lý

Các phép lọc, GROUP BY, SUM, COUNT, MIN/MAX, JOIN và window function có thể giảm dữ liệu cần truyền. Tuy nhiên, không nên nhồi mọi logic vào một query khó kiểm soát. Cần cân nhắc tính đúng, plan, readability và khả năng bảo trì.

### 16.2. Aggregate vẫn có thể tốn tài nguyên

Một GROUP BY trên hàng trăm triệu bản ghi vẫn có thể tốn CPU, sort/hash memory, disk spill và I/O. Kết quả nhỏ không chứng minh công việc tính toán nhỏ. Cần index, partition pruning, summary/materialized view hoặc job nền theo workload.

### 16.3. Tổng hợp theo khoảng ngày

```sql
SELECT
    date_trunc('day', created_at) AS day,
    COUNT(*) AS order_count,
    SUM(amount) AS total_amount
FROM demo_large_orders
WHERE tenant_id = 10
  AND created_at >= $1
  AND created_at < $2
GROUP BY date_trunc('day', created_at)
ORDER BY day;
```

Hai mốc thời gian được bind. Với bảng lớn, điều kiện range trên cột gốc `created_at` có thể hỗ trợ index/partition pruning; việc áp dụng hàm ở SELECT/GROUP BY là một chuyện khác với bọc cột trong WHERE.

## 17. ORM và nguy cơ materialize toàn bộ kết quả

Một ORM có thể chuyển mỗi hàng thành entity có nhiều object liên quan. Nếu query trả 100.000 orders và eager-load customer/items, số object thực tế có thể tăng nhiều lần.

### 17.1. Entity graph có overhead

Một entity có thể giữ:
- Các field scalar.
- Proxy/lazy-loading state.
- Collection liên quan.
- Snapshot phục vụ dirty checking.
- Identity map/persistence context.
- Reference tới entity khác.

Tải hàng trăm nghìn entity vào một persistence context có thể dùng RAM lớn hơn nhiều so với raw rows.

### 17.2. Dùng projection/DTO khi chỉ đọc

Nếu endpoint chỉ cần `order_id`, `status`, `amount`, hãy dùng projection/DTO query thay vì hydrate toàn entity graph. Điều này có thể giảm object count, dirty tracking và dữ liệu kéo theo.

### 17.3. N+1 query khác với tập kết quả lớn

Một query có 100 hàng, sau đó mỗi hàng lazy-load một customer, có thể tạo 101 queries. Ngược lại, một JOIN duy nhất có thể nhân bản dữ liệu và trả rất nhiều hàng. Hãy kiểm cả:
- Số query/round trips.
- Cardinality sau JOIN.
- Row width.
- Object graph materialized.
- Số hàng thật sự cần.

Không sửa N+1 bằng cách JOIN mọi quan hệ nếu kết quả sẽ phình to và duplicate dữ liệu.

### 17.4. Clear persistence context khi batch

Một số ORM hỗ trợ flush/clear theo batch để không giữ mọi entity trong persistence context. Phải hiểu lifecycle transaction, lazy relations và việc entity detached. Không gọi clear tùy tiện khi còn các entity cần dirty checking hoặc liên kết chưa ghi.

## 18. Export lớn: đồng bộ hay job nền?

Một export vài trăm nghìn hoặc vài triệu hàng thường không phù hợp để chạy như request HTTP đồng bộ có deadline ngắn.

### 18.1. Export đồng bộ

Có thể phù hợp khi:
- Kết quả nhỏ và có row/byte cap.
- Dự kiến hoàn thành nhanh.
- Người dùng cần file ngay.
- Có timeout và cancellation.
- Không giữ pool connection quá lâu.

### 18.2. Export nền

Mô hình job:

```text
Client gửi yêu cầu export
        |
        v
Validate quyền, filter, quota
        |
        v
Tạo export job (PENDING)
        |
        v
Worker claim job
        |
        v
Query theo cursor/keyset/batch
        |
        v
Stream CSV/JSONL ra file tạm hoặc object storage
        |
        v
Kiểm số hàng, checksum, dung lượng
        |
        v
Đánh dấu COMPLETED / FAILED
        |
        v
Client nhận trạng thái và link có thời hạn
```

Ưu điểm:
- Không giữ HTTP request mở quá lâu.
- Có thể retry/resume theo checkpoint.
- Có quota, concurrency và thời gian chạy riêng.
- Có thể báo tiến độ, số hàng, dung lượng.
- Có thể cancel job.

### 18.3. File export cũng cần giới hạn

Một job nền không có nghĩa được tạo file vô hạn. Cần:
- Max rows/bytes.
- Max duration.
- Max jobs per user/tenant.
- Disk/object storage quota.
- TTL và cleanup.
- Kiểm quyền khi tạo và tải file.
- Bảo vệ dữ liệu nhạy cảm trong file.
- Không tạo link public vĩnh viễn nếu file có dữ liệu riêng tư.

### 18.4. CSV injection là vấn đề khác SQL injection

Khi xuất dữ liệu ra CSV mở bằng spreadsheet, giá trị bắt đầu bằng một số ký tự như `=`, `+`, `-`, `@` có thể bị ứng dụng bảng tính hiểu như formula. Đây là **CSV/formula injection**, khác SQL injection. Nếu export có dữ liệu do người dùng kiểm soát, cần quy tắc neutralize/escape theo contract của file và người nhận; đồng thời tránh làm hỏng dữ liệu hợp lệ ngoài ý muốn.

## 19. Query cancellation và client disconnect

Khi người dùng đổi trang, đóng tab hoặc hủy export, query không còn cần thiết. Nếu chỉ ngừng chờ HTTP response nhưng database vẫn chạy, tài nguyên tiếp tục bị tiêu thụ.

### 19.1. Những gì phải đóng/hủy

- JDBC `Statement.cancel()` nếu driver hỗ trợ và connection còn hợp lệ.
- Cursor/ResultSet/Statement.
- Transaction theo chính sách rollback/commit.
- Connection trả về pool sau cleanup.
- Stream và output buffers.
- Background job state/checkpoint nếu tác vụ có thể resume.

### 19.2. Cancellation không phải rollback tự động trong mọi tình huống

Hủy SELECT thường dừng truy vấn, nhưng DML có transaction/side effects riêng. Nếu statement bị cancel, cần kiểm transaction đang ở trạng thái nào và rollback khi cần. Với thao tác ghi, không giả định “client đã timeout thì DB chắc chắn không commit”.

### 19.3. Cancel cần đi xuyên các lớp

Một request deadline có thể được truyền từ HTTP layer sang service, repository và driver. Nếu tầng repository không nhận cancellation signal, database query có thể tiếp tục. Kiểm thử client disconnect thật trên framework/driver triển khai.

## 20. Connection pool và concurrency

Mỗi cursor/stream thường giữ connection lâu hơn query ngắn. Một pool có 20 connections mà 20 export đang đọc chậm có thể khiến endpoint đăng nhập hoặc giao dịch thông thường không lấy được connection.

### 20.1. Tính thời gian giữ connection

Nếu:
- 10 export đồng thời.
- Mỗi export giữ một connection trong 3 phút.
- Pool chỉ có 20 connections.

Một nửa pool có thể bị export chiếm liên tục. Khi traffic tăng, các request ngắn chờ pool dù query của chúng rất nhanh.

### 20.2. Tách workload khi phù hợp

Có thể dùng:
- Pool riêng cho request ngắn.
- Pool/role riêng cho báo cáo.
- Worker concurrency cap.
- Queue có giới hạn.
- Rate limit theo tenant.
- Query timeout và export deadline.

Nhưng tách pool không tăng tổng năng lực database vô hạn. Tổng số connections phải nằm trong khả năng DB và các giới hạn của proxy/pooler.

### 20.3. Không giữ connection khi gọi API ngoài

Nếu xử lý mỗi hàng gồm đọc SQL rồi gọi HTTP service chậm, đừng mặc định giữ transaction/connection suốt thời gian gọi bên ngoài. Có thể đọc batch nhỏ, đóng transaction phù hợp, xử lý ngoài DB rồi ghi kết quả theo idempotency/checkpoint. Cần cân nhắc consistency và khả năng dữ liệu thay đổi giữa các bước.

### 20.4. Semaphore và queue

Một worker pool có giới hạn concurrency giúp giữ số tác vụ đang chạy trong mức kiểm soát. Queue cũng cần bounded capacity; nếu producer nhanh hơn consumer mà queue không giới hạn, RAM vẫn tăng dù database streaming tốt.

## 21. Index và execution plan cho truy vấn lấy nhiều hàng

Với lab PostgreSQL:

```sql
CREATE INDEX idx_demo_large_orders_tenant_created
ON demo_large_orders (
    tenant_id,
    created_at DESC,
    order_id DESC
);

CREATE INDEX idx_demo_large_orders_tenant_status_created
ON demo_large_orders (
    tenant_id,
    status,
    created_at DESC,
    order_id DESC
);
```

Query theo tenant và thứ tự thời gian:

```sql
EXPLAIN
SELECT order_id, status, amount, created_at
FROM demo_large_orders
WHERE tenant_id = 10
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
```

Đo thực tế:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, status, amount, created_at
FROM demo_large_orders
WHERE tenant_id = 10
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
```

Bảng lab có 10.000 hàng; plan có thể khác dữ liệu production. Đừng giả định index mới chắc chắn được dùng.

### 21.1. Index order phải phù hợp filter và sort

Index `(tenant_id, created_at DESC, order_id DESC)` có thể hỗ trợ:
- Equality filter tenant.
- Thứ tự thời gian và tie-breaker.
- Một số keyset predicates.

Nếu query filter thêm status, index `(tenant_id, status, created_at, order_id)` có thể hữu ích cho query ấy. Không có một index tối ưu cho mọi tổ hợp filter; quá nhiều index làm INSERT/UPDATE chậm và tốn storage.

### 21.2. Covering/index-only scan

Một index có thể chứa cột trả về để giảm table access (ví dụ PostgreSQL `INCLUDE` trong một số thiết kế), nhưng thêm `note` dài hoặc JSONB lớn vào index thường không hợp lý. Index-only scan còn phụ thuộc visibility map và điều kiện thực tế.

### 21.3. Sort có thể phải spill ra disk

Nếu query sắp xếp nhiều hàng và memory cho sort không đủ, DBMS có thể dùng temporary files. Hãy xem EXPLAIN/ANALYZE và log/temp file metrics; không tăng memory toàn cục chỉ để một query hiếm chạy nhanh hơn nếu sẽ ảnh hưởng concurrency.

### 21.4. Đọc ít hàng không đồng nghĩa đọc ít dữ liệu

`LIMIT 50` có thể vẫn sort/filter toàn bộ tập trước khi trả 50 hàng nếu index không hỗ trợ thứ tự và điều kiện. Hãy xem plan để biết có early stop hay không.

## 22. Giới hạn bộ nhớ ở database và ứng dụng

### 22.1. Phía database

Các thao tác sort/hash/aggregate có thể dùng memory theo cấu hình như `work_mem` của PostgreSQL. Đây là mức theo operation, không phải một ngân sách tổng cố định cho toàn server; nhiều query và nhiều node có thể dùng đồng thời nhiều lần mức này. Không tăng `work_mem` toàn cục tùy tiện để chữa một query.

### 22.2. Phía ứng dụng

Những thứ làm tăng heap:
- `fetchall()`/`ResultSet` bị materialize.
- ORM entities và relation collections.
- Danh sách DTO giữ toàn bộ kết quả.
- String JSON/CSV lớn.
- Buffer compression.
- Nhiều bản sao khi mapping/serialization.
- Queue không giới hạn.
- Nhiều export chạy song song.

Giải pháp:
- Projection nhỏ.
- Streaming thật ở driver.
- Batch có giới hạn.
- Output streaming hoặc file tạm.
- Backpressure.
- Bounded queue/concurrency.
- Max rows/bytes.
- Profiling heap và load test.

### 22.3. Không nhầm page size với batch size

- **Page size**: số hàng trả cho một trang API.
- **Fetch size**: gợi ý số hàng driver lấy mỗi lượt.
- **Batch size**: số hàng ứng dụng xử lý/commit trong một batch.
- **Max rows**: giới hạn tổng số hàng được phép.
- **Byte cap**: giới hạn tổng payload hoặc file.

Các giá trị này có thể khác nhau. Ví dụ page size 25, JDBC fetch size 200, worker batch 1.000, export max 100.000 hàng, file cap 50 MB — tất cả là những giới hạn riêng cần đo và giải thích.

## 23. Khác biệt giữa các hệ quản trị

| Nhu cầu | PostgreSQL | MySQL | SQL Server | Oracle | SQLite |
| --- | --- | --- | --- | --- | --- |
| Giới hạn hàng | `LIMIT` | `LIMIT` | `TOP`, `OFFSET/FETCH` | `FETCH FIRST`, `ROWNUM` theo version | `LIMIT` |
| Keyset | Predicate theo sort keys/row comparison | Predicate theo sort keys | Predicate theo sort keys | Predicate theo sort keys | Predicate theo sort keys |
| Server cursor | Portal/cursor, driver support | Cursor/stored program và driver support tùy cách dùng | Server cursors, driver options | REF CURSOR, fetch arrays | Thường step qua prepared statement |
| Fetch size | Driver-specific; JDBC/psycopg | Driver-specific | JDBC/ODBC driver-specific | Driver-specific | API fetch/step |
| Query timeout | `statement_timeout` | Timeout/optimizer settings theo version | Driver/`SET LOCK_TIMEOUT`/query timeout; phân biệt wait | Resource Manager/driver timeout | Host application/interrupt |
| Explain | `EXPLAIN ANALYZE` | `EXPLAIN ANALYZE` theo version | Actual execution plan | `DBMS_XPLAN`/runtime stats | `EXPLAIN QUERY PLAN` |
| Transaction snapshot | MVCC/isolation | InnoDB isolation | Locking/versioning tùy isolation | Read consistency | Locking/WAL mode tùy cấu hình |

Bảng là định hướng. Cú pháp, cursor behavior, fetch-size semantics, timeout và isolation phải kiểm theo **DBMS version và driver đang triển khai**.

### 23.1. MySQL

MySQL hỗ trợ `LIMIT` và nhiều driver có chế độ streaming result. Một số driver cần cấu hình cursor/server-side fetching hoặc chế độ đặc biệt để không buffer toàn bộ kết quả. `fetchSize` trong JDBC MySQL có thể có quy tắc riêng, ví dụ chế độ streaming phụ thuộc driver flags/statement settings. Đừng giả định `Statement.setFetchSize(500)` luôn có cùng hiệu quả như PostgreSQL JDBC.

### 23.2. SQL Server

SQL Server hỗ trợ `TOP` và `ORDER BY ... OFFSET ... FETCH NEXT`. JDBC/ODBC có fetch size và cursor options riêng. Có thể dùng keyset predicate theo khóa sort để tránh OFFSET lớn. Actual Execution Plan và Query Store giúp nghiên cứu plan; query timeout của driver khác lock timeout của engine.

### 23.3. Oracle

Oracle hỗ trợ `FETCH FIRST ... ROWS ONLY` và `OFFSET ... FETCH` trong các phiên bản hiện đại; các phiên bản cũ có thể dùng `ROWNUM` pattern. REF CURSOR và driver fetch arrays là các cách đọc theo phần. Đừng sao chép cú pháp `LIMIT` PostgreSQL sang Oracle.

### 23.4. SQLite

SQLite thường được ứng dụng nhúng đọc qua prepared statement và gọi step/fetch theo API. SQLite không có server cursor client–server giống PostgreSQL trong kiến trúc thông thường. Tuy nhiên, ứng dụng vẫn có thể tự materialize toàn bộ kết quả và cạn RAM; `LIMIT`, projection và đọc từng hàng vẫn quan trọng.

## 24. Timeout và quota theo từng lớp

Một chính sách tài nguyên tốt có nhiều deadline:

```text
HTTP request deadline: 10 seconds
Connection acquisition timeout: 1 second
SQL statement timeout: 5 seconds
Per-row processing budget: bounded
Export job deadline: 20 minutes
Maximum page size: 100
Maximum export rows: business-defined
Maximum export bytes: business-defined
Maximum concurrent exports per tenant: bounded
```

Các con số chỉ là ví dụ, không phải cấu hình khuyến nghị chung.

### 24.1. Phân biệt các loại timeout

- **Pool acquisition timeout:** chờ connection.
- **Connect timeout:** mở kết nối database.
- **Query/statement timeout:** thực thi câu SQL.
- **Lock timeout:** chờ lock.
- **Socket/network timeout:** chờ dữ liệu qua mạng.
- **HTTP/request timeout:** thời gian request.
- **Job deadline:** tổng thời gian tác vụ nền.

Nếu tất cả chỉ có một timeout, lỗi thường khó phân loại và cleanup không rõ.

### 24.2. Timeout phải có cleanup

Khi timeout:
1. Gửi cancel nếu driver hỗ trợ.
2. Đóng result/statement/cursor.
3. Rollback transaction nếu cần.
4. Đánh dấu connection không còn an toàn để tái sử dụng nếu driver báo lỗi trạng thái.
5. Trả/loại connection theo pool contract.
6. Ghi metric và error class, không log bí mật.

### 24.3. Quota ngăn một tenant chiếm hết hệ thống

Một tenant có thể khởi chạy nhiều export cùng lúc. Rate limit và max concurrent jobs theo tenant giúp công bằng. Nếu chỉ giới hạn tổng server, một tenant có thể chiếm toàn bộ quota chung trước các tenant khác.

## 25. Monitoring: theo dõi cả database và application

| Metric | Câu hỏi |
| --- | --- |
| Rows returned | Query trả bao nhiêu hàng? |
| Bytes returned | Network truyền bao nhiêu dữ liệu? |
| Row width | Hàng có cột lớn không? |
| Query duration p50/p95/p99 | Độ trễ điển hình và tail latency? |
| Rows scanned vs returned | Có quét quá nhiều hàng? |
| Sort/hash spill/temp bytes | Có vượt memory và ghi temp? |
| Buffer hits/reads | Dữ liệu lấy từ cache hay disk? |
| Pool active/idle/wait time | Pool có bị chiếm hết? |
| Cursor/transaction age | Có reader giữ snapshot quá lâu? |
| App heap/GC | Materialization có gây áp lực RAM? |
| Event loop lag/worker queue | Consumer có theo kịp producer? |
| Cancellation count | Request/job bị hủy có dừng query? |
| Export size/duration | Có vượt quota? |
| Per-tenant concurrency | Tenant nào chiếm tài nguyên? |

### 25.1. Log query fingerprint, không log payload nhạy cảm
Có thể ghi:
- Query name/fingerprint.
- Duration, rows, bytes.
- Tenant ID nội bộ theo chính sách bảo mật.
- Request/job ID.
- Timeout/cancel reason.
- Plan identifier hoặc query tag nếu được phép.

Không log toàn bộ hàng, token, email/điện thoại hoặc payload nhạy cảm chỉ để debug một query chậm. Dùng sampling, redaction và retention theo chính sách.

### 25.2. Slow query không phải lúc nào do thiếu index
Có thể do:
- Kết quả quá lớn.
- Row width quá rộng.
- Sort/aggregate spill.
- Consumer đọc chậm.
- Connection pool cạn.
- Network chậm.
- ORM materialization.
- Lock wait hoặc transaction dài.
- Một tenant có data skew lớn.

Hãy xác định bottleneck trước khi thêm index.

## 26. Các anti-pattern cần tránh

| Anti-pattern | Hậu quả | Cách thay |
| --- | --- | --- |
| `SELECT *` cho list endpoint | Tải cột thừa/PII/blob | Projection |
| Không có LIMIT | Kết quả không giới hạn | Page size cap |
| OFFSET rất sâu | Bỏ qua nhiều hàng | Keyset |
| Không ORDER BY | Thứ tự không ổn định | Sort + unique tie-breaker |
| `fetchAll()` cho hàng triệu dòng | Peak memory lớn | Streaming/batch |
| Generator nhưng nguồn đã fetchall | Vẫn materialize toàn bộ | Cursor/driver stream |
| ORM hydrate mọi entity | Persistence context phình | DTO/projection/clear batch |
| COUNT chính xác trên mọi request | Query phụ tốn kém | hasNext/page+1/cache/summary khi phù hợp |
| Aggregate ở application | Kéo dữ liệu thô qua mạng | GROUP BY/aggregate |
| JSON array khổng lồ một hàng | Buffer lớn hai phía | Stream rows/JSONL/batch |
| Stream không đóng | Connection/cursor bị giữ | Lifecycle rõ |
| Consumer chậm, queue không giới hạn | RAM tăng dần | Backpressure/bounded queue |
| Nhiều export đồng thời | Pool starvation | Quota/concurrency cap |
| Timeout HTTP nhưng query còn chạy | DB tiếp tục tốn tài nguyên | Driver cancellation |
| Transaction đọc nhiều giờ | Snapshot/connection lâu | Job snapshot/batch theo contract |
| Batch checkpoint trước commit | Bỏ sót dữ liệu khi crash | Commit/checkpoint atomic hoặc idempotent |
| Tăng pool size tùy tiện | DB quá tải | Đo và giới hạn concurrency |
| Tăng `work_mem` toàn cục | Tổng memory vượt kiểm soát | Tối ưu query/điều chỉnh scope |
| Index mọi cột output | Index nặng, ghi chậm | Index theo filter/sort |
| Export file vô hạn | Disk/network/PII risk | Row/byte/duration quota |
| Không cancel khi client rời | Công việc vô ích vẫn chạy | Propagate cancellation |
| Dùng LIMIT nhưng thiếu tenant filter | Sai quyền dữ liệu | Authorization + predicate |
| Tính rằng một trang là snapshot ổn định | Trang lặp/bỏ sót khi dữ liệu đổi | Cursor/snapshot contract |

## 27. Bài tập thực hành

Dùng `demo_large_customers` và `demo_large_orders` trong cùng PostgreSQL session tạo bảng. Các bài Java/Python/Node là fragment, cần tạo schema lab trên connection ứng dụng để chạy.

### Bài 1 — Cardinality và row width
So sánh `SELECT *` với chỉ `order_id, status, amount` cho tenant 10. Cột nào không cần cho một danh sách đơn cơ bản? Giải thích tác động lên network và heap.

### Bài 2 — LIMIT
Viết query lấy 50 đơn mới nhất tenant 10. Vì sao phải có ORDER BY và tie-breaker unique?

### Bài 3 — Deep OFFSET
Viết query `LIMIT 25 OFFSET 5000`. Giải thích vì sao database có thể phải đi qua nhiều hàng trước khi trả trang.

### Bài 4 — Keyset
Viết truy vấn lấy trang sau dựa trên `(created_at, order_id)` của hàng cuối trang trước. Chứng minh điều kiện đúng với hai cột DESC.

### Bài 5 — Cursor tie-breaker
Tạo nhiều hàng cùng timestamp. Điều gì xảy ra nếu chỉ dùng `created_at` làm cursor? Sửa bằng order_id.

### Bài 6 — Data thay đổi giữa trang
Mô phỏng insert một order mới đứng đầu sau khi tải trang đầu. OFFSET có thể lặp hàng nào? Keyset giảm vấn đề gì?

### Bài 7 — Snapshot
So sánh đọc mỗi trang trong transaction mới với giữ một snapshot dài. Vì sao transaction dài có chi phí vận hành?

### Bài 8 — JDBC fetch size
Viết ResultSet forward-only/read-only, tắt autocommit, đặt fetch size 500 và duyệt tuần tự. Giải thích vì sao fetch size không phải LIMIT.

### Bài 9 — JDBC lifecycle
Nếu ResultSet còn mở mà connection được trả về pool, có rủi ro gì? Viết try-with-resources đúng thứ tự.

### Bài 10 — fetchall và fetchmany
Viết Python `fetchall()` và `fetchmany(500)` cho cùng query. So sánh peak memory và lý do fetchmany chưa chắc server-side streaming.

### Bài 11 — Server-side cursor
Dùng named cursor của psycopg theo version đang dùng. Vì sao cursor/transaction có thể giữ connection lâu?

### Bài 12 — Node backpressure
Thiết kế stream đọc database rồi ghi file. Nếu consumer chậm, ứng dụng cần làm gì để producer không tiếp tục đẩy vô hạn?

### Bài 13 — Async concurrency
Vì sao `rows.forEach(async row => await process(row))` có thể tạo concurrency không giới hạn? Viết vòng lặp tuần tự hoặc semaphore có cap.

### Bài 14 — Count chính xác
Đo `COUNT(*)` trên tenant 10. Vì sao một kết quả scalar có thể tốn nhiều công việc database?

### Bài 15 — hasNext bằng page+1
Với page size 25, lấy 26 hàng rồi tính `hasNext`. Vì sao cách này có thể phù hợp với infinite scroll?

### Bài 16 — COUNT OVER
Viết `COUNT(*) OVER()` cùng LIMIT. Vì sao nó có thể cần xử lý toàn bộ tập trước khi trả trang?

### Bài 17 — Aggregate
Tính count và sum theo status ở database. So sánh số hàng phải truyền với cách tải mọi order về ứng dụng rồi cộng.

### Bài 18 — Index
Tạo index `(tenant_id, created_at DESC, order_id DESC)`. Dùng EXPLAIN để xem query mới nhất 50 hàng. Vì sao bảng nhỏ có thể vẫn Seq Scan?

### Bài 19 — Sort spill
Một query sort hàng triệu hàng nhưng trả 20. Tìm các chỉ số plan/temp file cần xem. Vì sao LIMIT không bảo đảm sort chỉ xử lý 20 hàng?

### Bài 20 — Batch checkpoint
Thiết kế worker lấy `order_id > last_id LIMIT batch_size`. Khi nào cập nhật checkpoint? Điều gì xảy ra nếu crash trước hoặc sau commit?

### Bài 21 — Batch size
Thử 100, 500, 2.000 hàng mỗi batch trên dữ liệu lab mở rộng. Đo throughput, memory, transaction duration. Vì sao không có một batch size tối ưu chung?

### Bài 22 — Timeout
Đặt `statement_timeout` trong session lab. Phân biệt statement timeout, lock timeout, pool acquisition timeout và HTTP timeout.

### Bài 23 — Cancellation
Thiết kế xử lý client disconnect để hủy query, đóng cursor và trả connection. Vì sao timeout reverse proxy không tự chứng minh database đã dừng?

### Bài 24 — Pool starvation
Pool có 20 connections, 15 export giữ connection dài. Các request ngắn sẽ gặp gì? Đề xuất export concurrency cap hoặc pool/workload isolation.

### Bài 25 — ORM materialization
Giải thích tại sao 100.000 entity với relation/proxy/dirty tracking có thể dùng RAM lớn hơn raw result. Viết projection DTO phù hợp.

### Bài 26 — JSON payload lớn
Một query trả `payload JSONB` vài MB mỗi hàng. Thiết kế list endpoint nhẹ và detail endpoint riêng. Nêu byte cap cần thiết cho export.

### Bài 27 — Export nền
Vẽ trạng thái job PENDING/RUNNING/COMPLETED/FAILED/CANCELED, checkpoint, file tạm, quota và TTL. Vì sao không nên giữ HTTP request mở hàng chục phút?

### Bài 28 — CSV injection
Một trường note bắt đầu bằng `=...` được export CSV. Phân biệt CSV/formula injection với SQL injection và nêu biện pháp cho consumer spreadsheet.

### Bài 29 — Multi-tenant fairness
Một tenant tạo nhiều export lớn. Thiết kế max jobs, rate limit, byte quota và concurrency per tenant để các tenant khác vẫn phục vụ được.

### Bài 30 — Thiết kế tổng hợp
Thiết kế API export 2 triệu order gồm:
1. Scope tenant lấy từ principal.
2. Projection chỉ các cột cần.
3. Keyset cursor ổn định và watermark/snapshot semantics.
4. Server-side cursor hoặc batch theo driver.
5. Backpressure và file streaming.
6. Max rows/bytes/duration.
7. Job concurrency và pool budget.
8. Query timeout, cancel và cleanup.
9. Checkpoint/idempotency/retry.
10. EXPLAIN, index, memory/network/latency monitoring.
11. Quyền tải file, link có thời hạn, cleanup.
12. Kiểm thử client disconnect, worker crash và dữ liệu thay đổi giữa job.

## 28. Checklist triển khai

### Hợp đồng dữ liệu
- [ ] Đã xác định số hàng tối đa và cột cần thiết?
- [ ] Có predicate tenant/quyền và khoảng thời gian?
- [ ] Có ORDER BY ổn định với tie-breaker?
- [ ] Pagination semantics có nói rõ dữ liệu thay đổi giữa trang?
- [ ] Có cần total count chính xác hay chỉ `hasNext`?

### Truy xuất và bộ nhớ
- [ ] Page size/fetch size/batch size/max rows được phân biệt?
- [ ] Driver có thực sự stream hoặc cursor theo cấu hình?
- [ ] Không materialize toàn bộ kết quả không cần thiết?
- [ ] Row width/JSON/blob được giới hạn?
- [ ] ORM dùng projection khi chỉ đọc?
- [ ] Queue và concurrency có giới hạn?

### Resource và transaction
- [ ] Query/request/job có timeout?
- [ ] Có cancellation khi client rời?
- [ ] Cursor/ResultSet/Statement được đóng?
- [ ] Connection pool có budget cho workload dài?
- [ ] Transaction/snapshot không giữ quá lâu?
- [ ] Checkpoint chỉ phản ánh batch đã commit hoặc có idempotency?

### Hiệu năng và vận hành
- [ ] Có EXPLAIN/actual plan trên dữ liệu đại diện?
- [ ] Có đo rows/bytes, buffers, sort spill, app heap và GC?
- [ ] Có monitor pool wait, active connections, cursor age?
- [ ] Có quota export theo user/tenant?
- [ ] File export có byte cap, TTL, quyền tải và cleanup?
- [ ] Có xử lý lỗi/cancel/retry và audit phù hợp?

## 29. Sơ đồ lựa chọn chiến lược

```text
                  CẦN ĐỌC TẬP KẾT QUẢ
                           |
                           v
              Chỉ cần một phần dữ liệu?
                    /             \
                  Có               Không
                  |                  |
                  v                  v
          LIMIT + projection    Có cần xử lý từng hàng?
                  |              /          \
                  v            Có            Không
          Pagination/keyset     |              |
                  |             v              v
                  v        Cursor/stream   Aggregate trong SQL
        Page size và max cap       |        hoặc report snapshot
                  |               v              |
                  +---------+-----+--------------+
                            |
                            v
               Consumer có thể chậm/hủy?
                      /            \
                    Có              Không
                    |                 |
                    v                 v
            Backpressure/cancel   Đọc theo batch
                    |                 |
                    +--------+--------+
                             |
                             v
          Timeout + pool/concurrency + row/byte quota
                             |
                             v
                EXPLAIN + monitoring + load test
```

## 30. Tổng kết

Tập kết quả lớn là một bài toán **đầu cuối**, từ cách database tìm hàng cho tới cách ứng dụng đọc, map, xử lý và gửi dữ liệu. Giới hạn bằng `LIMIT` là bước đầu; cần chọn cột bằng projection, có thứ tự xác định, dùng OFFSET cho tập vừa phải hoặc keyset cho danh sách sâu, và dùng cursor/stream/batch cho export hay worker. `fetchSize`, page size, batch size, max rows và byte cap là những khái niệm khác nhau, không nên dùng thay thế cho nhau.

Streaming có thể giảm peak memory phía client, nhưng vẫn có thể giữ connection và transaction lâu; database vẫn phải sort/hash/aggregate theo execution plan. Batch có thể tạo tiến độ và checkpoint, nhưng không tự atomic cho toàn job. Một timeout ở HTTP không tự dừng SQL; cancellation cần đi qua driver và cleanup đúng cursor, statement, transaction, connection. Pool size và worker concurrency phải được quản lý như tài nguyên hữu hạn.

Một query trả 20 hàng vẫn có thể tốn kém nếu phải sort hàng triệu hàng; một query chỉ trả một hàng vẫn có thể tạo JSON khổng lồ; một prepared query vẫn có thể làm cạn tài nguyên nếu limit quá lớn. Hãy đo **rows, bytes, duration, plan, buffers, heap, pool wait, transaction age và concurrency** trên workload đại diện.

Thiết kế tốt bắt đầu từ câu hỏi: **người gọi thực sự cần bao nhiêu dữ liệu, theo thứ tự nào, trong thời gian bao lâu và có thể tiếp tục/hủy ra sao?** Khi câu trả lời được thể hiện thành projection, giới hạn, pagination/cursor, backpressure, quota, timeout và checkpoint rõ ràng, ứng dụng sẽ đọc dữ liệu lớn có kiểm soát mà vẫn giữ được tính đúng và khả năng phục vụ các request khác.
