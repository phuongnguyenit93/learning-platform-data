# INSERT, UPDATE và ngữ nghĩa ghi theo primary key trong Apache Cassandra

Trong Apache Cassandra, `INSERT` và `UPDATE` đều là thao tác **upsert**: một lệnh ghi có thể tạo dữ liệu mới hoặc thay thế giá trị của những cột được chỉ định. Cassandra không dùng khái niệm “bản ghi đã tồn tại thì `INSERT` phải báo trùng khóa” như nhiều cơ sở dữ liệu quan hệ. Điều quyết định vị trí dữ liệu được ghi là **primary key** của bảng, đặc biệt là **partition key** và các **clustering column**.

Bài học này thuộc chương **Ghi và xóa bằng CQL**. Sau khi học, bạn cần có khả năng:

- Xác định một lệnh ghi sẽ tác động đến phân vùng và hàng nào dựa trên primary key.
- Viết đúng `INSERT`, `UPDATE`, hiểu trường hợp tạo mới và trường hợp ghi đè.
- Phân biệt cột bị bỏ qua, cột được gán giá trị và cột được gán `NULL`.
- Giải thích kết quả khi nhiều bản ghi cạnh tranh ghi cùng một ô dữ liệu, khi có TTL và khi dùng điều kiện `IF`.
- Chọn cách ghi phù hợp với mô hình bảng thiết kế theo truy vấn, replication và consistency level.

## 1. Primary key quyết định nơi lệnh ghi đi tới

Giả sử ứng dụng bán hàng cần tra cứu đơn hàng theo khách hàng và tháng. Một bảng theo hướng truy vấn có thể được tạo như sau (keyspace `shop` được giả định đã tồn tại):

```sql
CREATE TABLE shop.orders_by_customer (
    customer_id   uuid,
    order_month   text,
    order_id      uuid,
    ordered_at    timestamp,
    status        text,
    total         decimal,
    delivery_note text,
    PRIMARY KEY ((customer_id, order_month), order_id)
);
```

Đọc định nghĩa khóa từ trong ra ngoài:

| Thành phần | Trong ví dụ | Vai trò |
| --- | --- | --- |
| Partition key | `(customer_id, order_month)` | Xác định phân vùng logic; Cassandra dùng token của partition key để phân phối dữ liệu đến các replica. |
| Clustering column | `order_id` | Phân biệt các hàng bên trong cùng phân vùng và quyết định thứ tự sắp xếp của hàng trong phân vùng. |
| Full primary key | `(customer_id, order_month, order_id)` | Định danh duy nhất **một hàng** của bảng. |
| Regular column | `ordered_at`, `status`, `total`, `delivery_note` | Lưu dữ liệu có thể được ghi/cập nhật mà không thay đổi định danh hàng. |

Ví dụ, hai đơn hàng của cùng một khách trong tháng `2026-11` sẽ nằm trong cùng phân vùng nếu `order_id` khác nhau. Hai lần ghi với **cùng cả ba giá trị khóa** sẽ nhắm tới cùng một hàng.

```text
Partition key: (customer A, "2026-11")
  |
  +-- Clustering key: order_id X --> status, total, ordered_at, ...
  |
  +-- Clustering key: order_id Y --> status, total, ordered_at, ...

Partition key: (customer A, "2026-12")
  |
  +-- Clustering key: order_id Z --> status, total, ordered_at, ...
```

Đây là điểm nối giữa CQL và kiến trúc wide-column phân tán: primary key không chỉ dùng để kiểm tra tính duy nhất; nó còn điều khiển cách đặt và truy cập dữ liệu. `order_month` là một phần của partition key nên giúp phân vùng dữ liệu theo thời gian. Việc chọn khóa phải bắt đầu từ truy vấn mà ứng dụng cần phục vụ; Cassandra không tự tạo một mã hàng ẩn để thay thế primary key đã định nghĩa.

## 2. INSERT: ghi một hàng theo full primary key

Cú pháp thông dụng:

```sql
INSERT INTO keyspace_name.table_name (pk_column, ..., regular_column, ...)
VALUES (pk_value, ..., column_value, ...);
```

Với bảng ví dụ:

```sql
INSERT INTO shop.orders_by_customer (
    customer_id, order_month, order_id,
    ordered_at, status, total, delivery_note
)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11',
    22222222-2222-4222-8222-222222222222,
    '2026-11-21 09:30:00+0700',
    'CREATED',
    1200000.00,
    'Giao giờ hành chính'
);
```

Lệnh trên ghi hàng có khóa đầy đủ:

```text
(customer_id = 11111111-1111-4111-8111-111111111111,
 order_month = '2026-11',
 order_id = 22222222-2222-4222-8222-222222222222)
```

Để `INSERT` một hàng thông thường, phải cung cấp đầy đủ các thành phần primary key. Giá trị primary key không được là `NULL`. Các cột dữ liệu thường có thể được bỏ qua.

### INSERT lại cùng khóa không gây lỗi trùng khóa

Giả sử sau lệnh đầu tiên, hệ thống thực hiện:

```sql
INSERT INTO shop.orders_by_customer (
    customer_id, order_month, order_id, status
)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11',
    22222222-2222-4222-8222-222222222222,
    'PAID'
);
```

Vì **full primary key giống nhau**, Cassandra ghi vào hàng cũ. Nếu lần ghi thứ hai có timestamp mới hơn, `status` trở thành `PAID`. Các cột `total`, `ordered_at` và `delivery_note` không được nhắc tới trong lần ghi thứ hai nên vẫn giữ các giá trị đang có. Không xuất hiện một hàng thứ hai và cũng không tự phát sinh lỗi “duplicate primary key”.

Ngược lại, nếu thay `order_id` bằng một UUID khác nhưng giữ nguyên partition key, Cassandra sẽ ghi một **hàng khác trong cùng phân vùng**.

> **Quy tắc cốt lõi:** `INSERT` của Cassandra được hiểu là “ghi các giá trị này tại khóa này”, không mặc định là “chỉ thêm khi khóa chưa tồn tại”. Khi thực sự cần chỉ tạo nếu chưa có, sử dụng `IF NOT EXISTS` (phần 6).

## 3. UPDATE: thay giá trị cột, không thay primary key

Cú pháp:

```sql
UPDATE keyspace_name.table_name
SET column_name = value, ...
WHERE partition_key_component = value
  AND clustering_key_component = value;
```

Ví dụ cập nhật trạng thái và ghi chú giao hàng của đúng một đơn:

```sql
UPDATE shop.orders_by_customer
SET status = 'SHIPPING',
    delivery_note = 'Gọi trước khi giao'
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11'
  AND order_id = 22222222-2222-4222-8222-222222222222;
```

Ở bảng không có cột `static` này, `UPDATE` cột thường phải xác định đầy đủ các thành phần primary key trong `WHERE`. Đây không phải kiểu `UPDATE ... WHERE status = 'CREATED'` tùy ý giống ở SQL quan hệ: `status` là cột thường nên không thể dùng làm điều kiện định vị hàng để ghi. Khi cần cập nhật theo tiêu chí khác, ứng dụng phải biết khóa của các hàng cần cập nhật hoặc thiết kế bảng phục vụ đúng truy vấn đó.

Lệnh `UPDATE` trên **không sửa** `total` và `ordered_at`. Nếu hàng chưa tồn tại, `UPDATE` thông thường vẫn có thể **tạo hàng mới** tại primary key được chỉ định. Chẳng hạn:

```sql
UPDATE shop.orders_by_customer
SET status = 'CREATED'
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11'
  AND order_id = 33333333-3333-4333-8333-333333333333;
```

Sau lệnh này, hàng có `order_id` kết thúc bằng `3333...` có thể xuất hiện với `status = 'CREATED'`, còn các cột thường chưa từng được ghi sẽ đọc ra `null`.

### Không thể UPDATE một thành phần primary key

Các thao tác sau không hợp lệ về ý nghĩa:

```sql
-- SAI: primary key không được đặt trong SET.
UPDATE shop.orders_by_customer
SET order_id = 44444444-4444-4444-8444-444444444444
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11'
  AND order_id = 22222222-2222-4222-8222-222222222222;

-- SAI: thiếu clustering key khi cập nhật cột thường.
UPDATE shop.orders_by_customer
SET status = 'PAID'
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11';
```

Muốn đổi `order_id` hoặc chuyển đơn sang `order_month` khác thì thực chất là đổi định danh hàng: cần ghi hàng ở khóa mới và xử lý xóa dữ liệu khóa cũ theo quy trình nghiệp vụ. Cassandra không cung cấp câu lệnh “đổi primary key tại chỗ”. Đối với bảng có `static column`, quy tắc `WHERE` cho cập nhật riêng cột `static` có ngoại lệ; ví dụ bài này chỉ xét các cột thường.

## 4. Tại sao INSERT và UPDATE đều là upsert?

Mô hình lưu trữ của Cassandra xem các giá trị cột như các ô dữ liệu (cell) gắn với một khóa. Một lệnh ghi thường gửi mutation đến các replica phụ trách phân vùng, thay vì bắt buộc đọc hàng trước để quyết định thực hiện `INSERT` hay `UPDATE`.

Giả sử hàng hiện có các giá trị sau:

| Khóa (rút gọn) | `status` | `total` | `delivery_note` |
| --- | --- | --- | --- |
| `customer A / 2026-11 / order X` | `CREATED` | `1200000.00` | `Giao giờ hành chính` |

Sau khi thực hiện `UPDATE ... SET status = 'PAID' WHERE <đúng full primary key>`, ta có:

| Khóa (rút gọn) | `status` | `total` | `delivery_note` |
| --- | --- | --- | --- |
| `customer A / 2026-11 / order X` | `PAID` | `1200000.00` | `Giao giờ hành chính` |

Điều tương tự xảy ra với `INSERT` chỉ cung cấp khóa và `status`. Các giá trị không được viết trong mutation không bị thay bằng `null` chỉ vì chúng vắng mặt trong câu lệnh.

Phân biệt ba tình huống:

| Hành động | Ý nghĩa với cột thường |
| --- | --- |
| Không nêu cột trong `INSERT`, `UPDATE` | Không ghi lại cột đó; giá trị trước đó không bị thay đổi bởi chính lệnh này. |
| Gán `status = 'PAID'` | Ghi giá trị mới tại cell `status` của khóa tương ứng. |
| Gán `status = NULL` | Tạo dấu xóa (*tombstone*) cho dữ liệu cột đó; không phải “không cập nhật”. |

Ví dụ:

```sql
UPDATE shop.orders_by_customer
SET delivery_note = NULL
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11'
  AND order_id = 22222222-2222-4222-8222-222222222222;
```

Sau khi việc xóa có hiệu lực và được nhìn thấy ở mức nhất quán đọc đang dùng, cột `delivery_note` được đọc ra `null`. Cassandra phải duy trì tombstone trong một khoảng thời gian để replica chưa nhận được bản ghi xóa không làm dữ liệu cũ xuất hiện lại; quản lý tombstone, compaction và repair được tìm hiểu sâu ở các bài riêng.

Khi dùng Java Driver với prepared statement, **không bind** một tham số hoặc dùng trạng thái **UNSET** có thể giữ nguyên cột, trong khi bind **NULL** có ý nghĩa xóa cột. Ứng dụng nên phân biệt rõ “không gửi giá trị mới” và “muốn xóa giá trị hiện tại”.

## 5. Ghi đồng thời: timestamp và last-write-wins

Cassandra là cơ sở dữ liệu phân tán, nên nhiều replica hoặc client có thể xử lý những lần ghi cạnh tranh. Với các ô thông thường, Cassandra hòa giải phiên bản theo **timestamp của cell** (*last-write-wins theo timestamp*), không đơn thuần theo thứ tự mà người dùng thấy câu lệnh đến server.

Ví dụ hai client cùng ghi `status` của một hàng:

```text
Client A: status = 'PAID'     @timestamp = 1000000
Client B: status = 'CANCELLED' @timestamp = 2000000

Khi các phiên bản được hòa giải:
status = 'CANCELLED' (timestamp lớn hơn)
```

Các số timestamp phía trên chỉ minh họa thứ tự so sánh. Timestamp ghi của Cassandra có độ phân giải **microsecond** tính từ Unix epoch; số timestamp lớn hơn được ưu tiên cho cùng cell. Nếu timestamp bằng nhau, Cassandra có quy tắc giải quyết xung đột riêng, vì vậy không nên chủ động dựa vào timestamp trùng nhau để quyết định giá trị nghiệp vụ.

Những hệ quả cần nhớ:

- Các cột có thể có timestamp khác nhau. Cập nhật `status` không bắt buộc ghi đè `total` của cùng hàng.
- Một yêu cầu đến muộn nhưng mang timestamp lớn hơn vẫn có thể thắng; ngược lại một ghi mới đến với timestamp cũ có thể không thay đổi giá trị được đọc.
- Sai lệch đồng hồ giữa client/nút, đặc biệt khi tự cấp timestamp, có thể gây kết quả bất ngờ. Chỉ dùng timestamp tùy chỉnh khi hiểu rõ cơ chế đồng bộ đồng hồ và giải quyết xung đột.
- Lệnh upsert mặc định không kiểm tra “trạng thái trước đó phải là X”. Nếu nhiều người cùng cập nhật một đơn, có nguy cơ mất cập nhật theo ý nghĩa nghiệp vụ. Cần dùng điều kiện `IF` khi yêu cầu chuyển trạng thái có kiểm soát.

CQL hỗ trợ `USING TIMESTAMP <microseconds_since_epoch>` trên các lệnh ghi thông thường, nhưng trong ứng dụng phổ biến nên để cơ chế cấp timestamp được cấu hình của hệ thống/driver đảm nhiệm. Không áp dụng cách tự cấp timestamp đó cho mọi dạng thao tác, ví dụ conditional writes hoặc counter có giới hạn riêng.

## 6. Ghi có điều kiện bằng IF: khi upsert chưa đủ

Để yêu cầu “chỉ tạo nếu khóa này chưa có”, dùng `IF NOT EXISTS`:

```sql
INSERT INTO shop.orders_by_customer (
    customer_id, order_month, order_id, status, total
)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11',
    22222222-2222-4222-8222-222222222222,
    'CREATED',
    1200000.00
)
IF NOT EXISTS;
```

Để yêu cầu “chỉ cập nhật nếu hàng đang tồn tại”, dùng `IF EXISTS`:

```sql
UPDATE shop.orders_by_customer
SET delivery_note = 'Giao sau 18h'
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11'
  AND order_id = 22222222-2222-4222-8222-222222222222
IF EXISTS;
```

Điều kiện cũng có thể dựa trên giá trị cũ của cột, ví dụ chỉ cho phép chuyển từ `CREATED` sang `PAID`:

```sql
UPDATE shop.orders_by_customer
SET status = 'PAID'
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11'
  AND order_id = 22222222-2222-4222-8222-222222222222
IF status = 'CREATED';
```

Các lệnh `IF` thuộc nhóm **lightweight transaction (LWT)** và sử dụng cơ chế đồng thuận để kiểm soát điều kiện khi nhiều client tranh chấp. Kết quả CQL cho biết `applied = true` nếu điều kiện được thỏa, hoặc `applied = false` nếu không; khi điều kiện thất bại, có thể kèm các giá trị hiện tại để ứng dụng quyết định bước tiếp theo.

LWT có chi phí phối hợp và độ trễ cao hơn upsert thông thường. Dùng khi cần bảo đảm tính duy nhất của thao tác tạo mới hoặc chuyển trạng thái có điều kiện; không nên biến mọi lần ghi thành LWT chỉ để mô phỏng SQL quan hệ.

## 7. TTL: giá trị ghi có thể tự hết hạn

`INSERT` và `UPDATE` thông thường hỗ trợ thời gian tồn tại (*time to live*, TTL) tính bằng giây:

```sql
INSERT INTO shop.orders_by_customer (
    customer_id, order_month, order_id, status
)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11',
    55555555-5555-4555-8555-555555555555,
    'TEMPORARY'
)
USING TTL 3600;

UPDATE shop.orders_by_customer USING TTL 1800
SET delivery_note = 'Ghi chú tạm thời'
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11'
  AND order_id = 22222222-2222-4222-8222-222222222222;
```

Trong ví dụ, `status` được ghi với TTL một giờ ở hàng tạm; `delivery_note` được ghi với TTL 30 phút ở hàng đã có. TTL chủ yếu áp dụng cho **các giá trị cột được ghi**; các phần primary key không tự mang TTL như cột thường. Một lần ghi lại cột với TTL mới có thể thay đổi thời điểm hết hạn của giá trị đó. Khi TTL hết hạn, giá trị không còn hiện diện khi đọc và Cassandra xử lý việc hết hạn thông qua cơ chế tombstone.

Có thể kiểm tra timestamp ghi và TTL còn lại:

```sql
SELECT status, WRITETIME(status), TTL(status)
FROM shop.orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11'
  AND order_id = 55555555-5555-4555-8555-555555555555;
```

`WRITETIME(status)` trả timestamp ghi của cell; `TTL(status)` cho biết số giây còn lại nếu cell đang có TTL, còn khi không có TTL thường cho kết quả `null`. Không nên hiểu TTL như một cơ chế xóa hàng tức thì khỏi mọi tệp lưu trữ vật lý.

## 8. Consistency level không thay đổi nghĩa của primary key

Replication cho phép Cassandra giữ các bản sao dữ liệu trên nhiều node; **write consistency level** xác định số replica phải xác nhận để một lần ghi được coi là thành công từ góc nhìn client. Chẳng hạn với replication factor 3, `QUORUM` thường đòi hỏi phản hồi thành công của 2 replica trong phạm vi áp dụng mức nhất quán đó.

Trong `cqlsh`, có thể đặt mức nhất quán trước khi chạy các lệnh ghi:

```sql
CONSISTENCY QUORUM;
```

Tuy nhiên, đổi từ `ONE` sang `QUORUM` không thay đổi full primary key, không khiến `INSERT` báo lỗi khóa trùng và không tự biến `UPDATE` thành thao tác kiểm tra-đổi-trạng-thái nguyên tử theo điều kiện. Consistency level ảnh hưởng đến mức xác nhận và khả năng quan sát kết quả đọc/ghi; xung đột giá trị vẫn gắn với timestamp, còn điều kiện cạnh tranh cần LWT.

Trong hệ thống thực tế, khi client bị timeout, không thể kết luận chắc chắn mutation đã được ghi hay chưa chỉ từ timeout. Retry một upsert có cùng khóa và giá trị thường thuận lợi hơn retry một thao tác kiểu cộng dồn, nhưng timestamp, TTL, LWT và yêu cầu nghiệp vụ vẫn cần được xem xét để thiết kế retry an toàn.

## 9. Thực hành kiểm chứng từng tình huống

Sau khi tạo bảng và chạy `INSERT` đầu tiên ở phần 2, thực hiện lần lượt:

**Bước 1 — Đọc hàng theo đúng primary key**

```sql
SELECT customer_id, order_month, order_id,
       status, total, delivery_note
FROM shop.orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11'
  AND order_id = 22222222-2222-4222-8222-222222222222;
```

Kỳ vọng: một hàng có `status = 'CREATED'`, `total = 1200000.00` và ghi chú giao hàng ban đầu.

**Bước 2 — Upsert một cột bằng INSERT**

```sql
INSERT INTO shop.orders_by_customer (
    customer_id, order_month, order_id, status
)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11',
    22222222-2222-4222-8222-222222222222,
    'PAID'
);
```

Chạy lại `SELECT` ở bước 1: nếu không có ghi cạnh tranh và không có timestamp khác thường, `status` là `PAID` nhưng `total` và `delivery_note` vẫn giữ nguyên.

**Bước 3 — UPDATE một khóa chưa có**

```sql
UPDATE shop.orders_by_customer
SET status = 'CREATED'
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11'
  AND order_id = 33333333-3333-4333-8333-333333333333;

SELECT order_id, status, total
FROM shop.orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11'
  AND order_id = 33333333-3333-4333-8333-333333333333;
```

Kỳ vọng: có hàng mới, `status = 'CREATED'` và `total = null`.

**Bước 4 — Kiểm tra điều kiện chuyển trạng thái**

```sql
UPDATE shop.orders_by_customer
SET status = 'PAID'
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11'
  AND order_id = 22222222-2222-4222-8222-222222222222
IF status = 'CREATED';
```

Nếu bước 2 đã chuyển `status` của hàng này sang `PAID`, điều kiện `status = 'CREATED'` sai nên kết quả sẽ là `applied = false`. Thay vì âm thầm cập nhật, ứng dụng nhận được tín hiệu rằng trạng thái đã không còn như kỳ vọng.

### Các lỗi tư duy thường gặp

| Suy đoán sai | Cách hiểu đúng |
| --- | --- |
| `INSERT` trùng khóa phải lỗi như SQL quan hệ. | Mặc định `INSERT` là upsert; cần `IF NOT EXISTS` nếu muốn kiểm tra tồn tại. |
| `UPDATE` không có hàng thì không làm gì. | `UPDATE` thông thường có thể tạo hàng mới tại full primary key. |
| Không truyền một cột nghĩa là đặt nó thành `NULL`. | Bỏ qua cột nghĩa là không ghi cột đó; truyền `NULL` có thể tạo tombstone. |
| Có thể sửa partition key bằng `UPDATE SET`. | Thay đổi khóa nghĩa là định danh hàng khác, phải xử lý ghi sang khóa mới. |
| Client gửi lệnh sau luôn thắng. | Cassandra so sánh timestamp của từng cell, không chỉ thứ tự yêu cầu đến. |
| `QUORUM` đảm bảo chỉ một client có thể thay trạng thái. | `QUORUM` quy định mức xác nhận replica; dùng LWT khi cần điều kiện cạnh tranh. |

## 10. Liên hệ với thiết kế ứng dụng Java

Khi ứng dụng Java dùng prepared statement để ghi Cassandra, hãy đóng gói đầy đủ full primary key trong tham số của lệnh `INSERT`/`UPDATE`. Hãy xác định rõ API nào có nghĩa **upsert** và API nào đòi hỏi **create-if-absent** hoặc **compare-and-set**. Với yêu cầu cập nhật từng phần, phải phân biệt trường không được client gửi với trường được gửi `null`; nếu không, một request cập nhật `status` rất dễ vô tình xóa `delivery_note`.

Đối với retry và xử lý lỗi mạng, dùng một khóa ổn định cho cùng một đơn hàng giúp các lần ghi lặp lại nhắm đến cùng hàng. Nếu cần thao tác “chỉ chuyển từ `CREATED` sang `PAID` đúng một lần”, nên thiết kế bằng LWT và kiểm tra kết quả `applied`, thay vì đọc trước rồi `UPDATE` không điều kiện: giữa hai thao tác đọc và ghi, client khác vẫn có thể thay trạng thái.

**Ghi nhớ:** trong Cassandra, primary key quyết định *ghi vào đâu*, danh sách cột quyết định *ghi giá trị nào*, timestamp quyết định *phiên bản nào thắng*, TTL quyết định *giá trị tồn tại bao lâu*, và `IF` quyết định *có được phép ghi khi trạng thái hiện tại không như mong đợi hay không*. Nắm vững năm yếu tố này là nền tảng để hiểu xóa dữ liệu, tombstone, compaction, repair và consistency ở các phần tiếp theo.
