# Cấu trúc SELECT, chọn cột và biểu thức kết quả trong Apache Cassandra

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Đọc và viết câu lệnh `SELECT` bằng Cassandra Query Language (CQL), phân biệt phần **chọn dữ liệu** với phần **chọn cột kết quả**.
2. Chọn một số cột, dùng `*`, đặt bí danh bằng `AS` và hiểu hình dạng dữ liệu được trả về.
3. Tạo biểu thức kết quả bằng phép toán, `CAST`, hàm vô hướng, `WRITETIME`, `TTL` và hàm tổng hợp.
4. Phân biệt `SELECT JSON`, `toJson()` và `SELECT DISTINCT`; nhận biết giới hạn của chúng.
5. Nhận ra một câu `SELECT` tuy hợp lệ về cú pháp nhưng không phù hợp với mô hình phân vùng của Cassandra.

Bài thuộc mô-đun `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Trong cơ sở dữ liệu wide-column phân tán như Apache Cassandra, `SELECT` phải được đặt trong bối cảnh **partition key, clustering columns, truy vấn theo thiết kế bảng, replication và consistency**. Danh sách cột muốn trả về không thay thế được việc xác định partition cần đọc.

## 1. Mô hình tư duy: tìm dòng trước, tạo kết quả sau

Với một truy vấn CQL, hãy tách hai câu hỏi:

- **Đọc những dòng nào?** `FROM` xác định bảng; `WHERE` xác định partition và tập dòng trong partition; `ORDER BY`, `LIMIT` thu hẹp hoặc sắp thứ tự kết quả trong các giới hạn của Cassandra.
- **Trả về những gì từ các dòng đó?** Phần nằm giữa `SELECT` và `FROM` là *selection clause* (còn gọi là projection): tên cột, `*`, bí danh, hàm hoặc biểu thức tạo cột kết quả.

Ví dụ:

```sql
SELECT ordered_at, status, amount_cents
FROM orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_day = '2026-11-20'
LIMIT 20;
```

Trong ví dụ này, cặp `(customer_id, order_day)` trong `WHERE` giúp định vị **một partition**; danh sách `ordered_at, status, amount_cents` chỉ xác định **ba cột xuất hiện trong kết quả**. Dù `customer_id` dùng để lọc, nó không tự xuất hiện trong kết quả nếu không được nêu trong `SELECT`.

> Quy tắc thực hành: thiết kế bảng dựa trên các truy vấn và khóa phân vùng trước; sau đó mới quyết định những cột cần chiếu ra cho từng API hoặc màn hình.

## 2. Cú pháp tổng quát của SELECT

Khung cú pháp thường dùng trong CQL:

```sql
SELECT [JSON | DISTINCT] (* | selector [AS alias] [, selector [AS alias] ...])
FROM [keyspace_name.]table_name
[WHERE condition [AND condition ...]]
[GROUP BY column_name [, column_name ...]]
[ORDER BY clustering_column [ASC | DESC] [, ...]]
[PER PARTITION LIMIT n]
[LIMIT n]
[ALLOW FILTERING];
```

Các thành phần:

| Thành phần | Vai trò | Điều cần nhớ trong Cassandra |
| --- | --- | --- |
| `SELECT ...` | Xác định cột và biểu thức kết quả | Có thể dùng `*` hoặc một danh sách selector. |
| `JSON` | Mã hóa mỗi dòng kết quả thành một đối tượng JSON | Đặt ngay sau `SELECT`; khác với gọi `toJson()` trên một cột. |
| `DISTINCT` | Lấy kết quả duy nhất theo partition | Không phải `DISTINCT` tùy ý trên mọi cột như SQL quan hệ. |
| `FROM` | Chọn đúng một bảng (có thể kèm keyspace) | CQL `SELECT` không hỗ trợ `JOIN` hay subquery trong `FROM`. |
| `WHERE` | Quy định partition và lát cắt dữ liệu | Thường bắt đầu từ partition key; các điều kiện trên clustering key phải tuân thủ thứ tự khóa. |
| `GROUP BY` | Gom nhóm các dòng và áp dụng hàm tổng hợp | Bị giới hạn bởi các cột của primary key và thứ tự của chúng. |
| `ORDER BY` | Sắp xếp theo clustering columns | Bị giới hạn bởi clustering order của bảng; không sắp tùy ý theo cột thường. |
| `PER PARTITION LIMIT` | Giới hạn số dòng trên mỗi partition | Khác với giới hạn tổng số dòng. |
| `LIMIT` | Giới hạn số dòng kết quả | Không tương đương page size hoặc SQL `OFFSET`. |
| `ALLOW FILTERING` | Cho phép một số truy vấn phải lọc/scan rộng | Có thể kéo theo chi phí đọc khó dự đoán, không phải cách sửa thiết kế bảng. |

`JSON` và `DISTINCT` ở cùng một vị trí tùy chọn trong cú pháp; không ghép chúng thành `SELECT JSON DISTINCT ...`. Bài này tập trung vào **selection clause** và biểu thức kết quả; các điều kiện lọc, thứ tự và phân trang sẽ được phân tích sâu trong các bài riêng.

## 3. Bảng ví dụ có thể thực hành trong cqlsh

Giả sử ứng dụng thương mại điện tử cần hiển thị đơn hàng của **một khách trong một ngày**. Mỗi ngày của khách là một partition; `ordered_at` là clustering column để sắp đơn mới trước.

```sql
-- Chỉ dùng replication_factor = 1 với môi trường học tập một node.
CREATE KEYSPACE IF NOT EXISTS cql_select_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

USE cql_select_lab;

CREATE TABLE IF NOT EXISTS orders_by_customer (
    customer_id uuid,
    order_day date,
    ordered_at timeuuid,
    status text,
    amount_cents bigint,
    note text,
    tags set<text>,
    attributes map<text, text>,
    PRIMARY KEY ((customer_id, order_day), ordered_at)
) WITH CLUSTERING ORDER BY (ordered_at DESC);

INSERT INTO orders_by_customer
    (customer_id, order_day, ordered_at, status, amount_cents, note, tags, attributes)
VALUES
    (11111111-1111-4111-8111-111111111111,
     '2026-11-20', now(), 'CREATED', 125050, 'Giao gio hanh chinh',
     {'online'}, {'channel': 'web'});

INSERT INTO orders_by_customer
    (customer_id, order_day, ordered_at, status, amount_cents, note, tags, attributes)
VALUES
    (11111111-1111-4111-8111-111111111111,
     '2026-11-20', now(), 'PAID', 259900, 'Da thanh toan',
     {'mobile', 'priority'}, {'channel': 'app'});
```

**Giải thích thiết kế:**

- `PRIMARY KEY ((customer_id, order_day), ordered_at)`: hai cột trong cặp ngoặc tròn bên trong tạo **composite partition key**; mỗi giá trị `ordered_at` phân biệt các dòng trong partition.
- `ordered_at timeuuid` với `now()` giúp tạo giá trị sắp theo thời gian; `CLUSTERING ORDER BY (ordered_at DESC)` định nghĩa thứ tự đọc mặc định trong partition.
- `status`, `amount_cents`, `note`, `tags`, `attributes` là các cột dữ liệu; việc chúng được chọn trong `SELECT` không biến chúng thành khóa.
- `SimpleStrategy` với một replica chỉ tiện cho lab. Trong triển khai đa node hoặc đa datacenter, chọn replication phù hợp (thường `NetworkTopologyStrategy`) và cấu hình consistency ở cqlsh/driver theo yêu cầu hệ thống; consistency không nằm trong danh sách selector.

Hai câu `INSERT` dùng `now()` nên giá trị `ordered_at` thực tế khác nhau giữa các lần chạy. Các ví dụ truy vấn bên dưới sử dụng partition đã biết, không cần đoán UUID thời gian vừa tạo.

## 4. Chọn cột và đặt bí danh

### 4.1. Chọn đúng các cột cần dùng

```sql
SELECT ordered_at, status, amount_cents
FROM orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_day = '2026-11-20';
```

Kết quả có **ba cột** theo danh sách `SELECT`. Đối với màn hình lịch sử đơn hàng, đây là cách tốt để tránh gửi cả `note`, `tags` hay `attributes` khi chúng chưa cần thiết. Chọn ít cột thường giảm dữ liệu trả qua mạng và công việc ánh xạ ở ứng dụng Java; mức tiết kiệm đọc đĩa phụ thuộc cấu trúc lưu trữ và truy vấn thực tế.

```sql
SELECT *
FROM orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_day = '2026-11-20';
```

`*` trả về tất cả cột được định nghĩa trong bảng. Nó tiện khi khám phá dữ liệu bằng cqlsh nhưng có ba nhược điểm với API chạy lâu dài: payload có thể lớn, thay đổi schema có thể thay đổi tập cột trả về, và ứng dụng dễ phụ thuộc vào những cột không thực sự cần.

**Lưu ý:** `SELECT *` với `WHERE` định vị một partition vẫn khác xa `SELECT * FROM orders_by_customer;` không có `WHERE`. Câu thứ hai có thể phải duyệt dữ liệu trên nhiều node; thay `*` bằng hai cột không tự làm truy vấn toàn bảng trở nên an toàn.

### 4.2. Bí danh với AS

```sql
SELECT ordered_at AS created_time,
       amount_cents AS total_in_cents,
       status AS order_status
FROM orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_day = '2026-11-20';
```

`AS` đổi **tên cột trong result set**, không đổi tên cột trong schema và không làm thay đổi dữ liệu. Đây là cách đặt tên rõ hơn cho DTO hoặc cho biểu thức có tên mặc định khó đọc.

Không thể dùng alias như một tên cột nguồn trong `WHERE` hoặc `ORDER BY` của cùng câu lệnh:

```sql
-- Sai: "order_status" chỉ là tên kết quả, không phải cột bảng.
SELECT status AS order_status
FROM orders_by_customer
WHERE order_status = 'PAID';

-- Đúng về mặt tham chiếu tên cột; việc lọc theo status
-- vẫn phải phù hợp với khóa/chỉ mục và kế hoạch truy vấn.
SELECT status AS order_status
FROM orders_by_customer
WHERE status = 'PAID' ALLOW FILTERING;
```

Ví dụ thứ hai chỉ để chỉ ra cách gọi **tên cột gốc**, không phải truy vấn được khuyên dùng: quét/lọc theo `status` trên bảng này có thể rất tốn kém. Trong ứng dụng, thường cần bảng riêng theo mẫu truy vấn trạng thái nếu phải tìm đơn theo trạng thái trên nhiều khách/ngày.

Tên không đặt trong dấu nháy kép được CQL xử lý không phân biệt chữ hoa/thường. Với tên hiển thị có phân biệt hoa/thường, có thể dùng alias được trích dẫn:

```sql
SELECT amount_cents AS "amountCents"
FROM orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_day = '2026-11-20';
```

## 5. Biểu thức kết quả: selector trả về giá trị gì?

Một selector có thể là **tên cột**, **literal/term**, **phép chuyển kiểu**, **phép toán**, **hàm** hoặc **hàm tổng hợp**. CQL có nhiều khả năng biểu thức, nhưng chúng có quy tắc kiểu dữ liệu và phạm vi khác SQL tổng quát.

| Dạng selector | Ví dụ trong danh sách `SELECT` | Ý nghĩa |
| --- | --- | --- |
| Cột gốc | `status` | Giá trị đang lưu của cột. |
| Giá trị cố định | `'orders' AS source` | Cùng một literal cho mỗi dòng được trả về; không tự tạo thêm dòng. |
| Phép toán | `amount_cents / 100` | Tính giá trị từ các operand theo quy tắc kiểu CQL. |
| Chuyển kiểu | `CAST(amount_cents AS decimal)` | Đổi sang kiểu tương thích. |
| Hàm vô hướng | `abs(amount_cents)` | Áp dụng cho giá trị của mỗi dòng. |
| Hàm metadata | `ttl(note)`, `writetime(status)` | Đọc thông tin TTL/timestamp của cell tương ứng. |
| Hàm tổng hợp | `count(*)`, `sum(amount_cents)` | Gộp nhiều dòng thành một giá trị tổng hợp. |

### 5.1. Phép toán số học và thứ tự thực hiện

Từ Apache Cassandra **4.0**, CQL hỗ trợ `+`, `-`, `*`, `/`, `%` trên các kiểu số phù hợp và dấu `-` một ngôi. `*`, `/`, `%` có độ ưu tiên cao hơn `+`, `-`; dùng dấu ngoặc để biểu đạt ý định.

```sql
SELECT ordered_at,
       amount_cents,
       amount_cents / 100 AS units_truncated,
       CAST(amount_cents AS decimal) / 100 AS units_decimal
FROM orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_day = '2026-11-20';
```

Với `amount_cents = 125050` (kiểu `bigint`):

- `amount_cents / 100` thực hiện chia kiểu nguyên và cho `1250`, mất phần lẻ.
- `CAST(amount_cents AS decimal) / 100` tính theo kiểu thập phân, cho giá trị tương ứng `1250.5`.

Do đó, nếu cần tính tỷ lệ, giá tiền hoặc phần trăm, hãy xét **kiểu của toán hạng** trước khi chọn phép chia. `CAST` không hồi phục phần thập phân đã mất nếu được áp dụng *sau* phép chia nguyên. Với tiền tệ, cân nhắc biểu diễn số nguyên nhỏ nhất (ví dụ cents) trong dữ liệu gốc và chỉ đổi đơn vị tại tầng hiển thị.

### 5.2. Hàm vô hướng và CAST

```sql
SELECT ordered_at,
       CAST(amount_cents AS text) AS amount_text,
       abs(amount_cents) AS absolute_amount
FROM orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_day = '2026-11-20';
```

`CAST(selector AS type)` chỉ hỗ trợ **các cặp kiểu chuyển đổi hợp lệ**, không phải mọi kiểu bất kỳ. Tên hàm và kiểu kết quả của hàm được xác định bởi phiên bản Cassandra và chữ ký hàm. Những hàm tự định nghĩa (UDF) còn phụ thuộc cấu hình bật UDF của cluster; không giả định chúng luôn sẵn có.

Khi đọc kết quả trong Java driver, kiểu CQL của **biểu thức sau chuyển đổi** quyết định phương thức getter tương ứng; chẳng hạn một selector trả về `decimal` được ánh xạ khác một selector trả về `bigint`.

### 5.3. Đọc TTL và thời điểm ghi của từng cell

```sql
SELECT ordered_at,
       status,
       writetime(status) AS status_write_us,
       ttl(note) AS note_ttl_seconds
FROM orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_day = '2026-11-20';
```

- `writetime(status)` là timestamp ghi của **giá trị cột `status`** theo đơn vị microsecond tính từ Unix epoch; đây không mặc nhiên là thời điểm tạo đơn và có thể khác timestamp của cột khác trong cùng dòng.
- `ttl(note)` là **số giây còn lại** trước khi giá trị `note` hết hạn; nếu giá trị không có TTL, kết quả là `null`.
- Không áp dụng `writetime`/`ttl` tùy ý lên cột primary key. Các kiểu đặc biệt như counter và collection/UDT nhiều cell có quy tắc riêng theo phiên bản; ví dụ trên cố ý dùng cột `text` đơn giản.
- Apache Cassandra 5.0 còn có `maxwritetime(column)` để lấy timestamp ghi lớn nhất trong trường hợp cột gồm nhiều cell; khi cần tương thích phiên bản cũ, hãy kiểm tra cú pháp được cluster hỗ trợ.

Tại mức phân tán, việc đọc giá trị nào còn phụ thuộc **consistency level** được cấu hình cho truy vấn, tình trạng replica và xung đột ghi. `WRITETIME` giúp quan sát metadata của giá trị trả về chứ không chứng minh mọi replica đã đồng bộ.

### 5.4. Chọn phần tử từ collection và trả về JSON của một cột

Bảng ví dụ có `attributes map<text,text>` và `tags set<text>`. Với CQL hỗ trợ collection element selector, bạn có thể lấy phần tử của map theo khóa:

```sql
SELECT ordered_at,
       attributes['channel'] AS sales_channel,
       toJson(tags) AS tags_json
FROM orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_day = '2026-11-20';
```

`attributes['channel']` lấy giá trị gắn với khóa `channel` (hoặc `null` khi không có). `toJson(tags)` trả về **chuỗi text mã hóa JSON** của riêng cột `tags`, ví dụ dạng chuỗi `["mobile","priority"]`. Thứ tự hiển thị phần tử của set không phải thứ tự do ứng dụng nhập vào.

Tên hàm `toJson()` dùng được với các phiên bản Cassandra trước đây; ở Cassandra 5.0 còn có dạng tên `to_json()`. Khi dùng collection selector, slice hoặc UDT field selector, cần đối chiếu khả năng của phiên bản Cassandra và driver cụ thể, nhất là với cluster cũ.

### 5.5. COUNT và các hàm tổng hợp

```sql
SELECT count(*) AS total_orders,
       min(amount_cents) AS min_amount,
       max(amount_cents) AS max_amount,
       sum(amount_cents) AS sum_amount,
       avg(CAST(amount_cents AS decimal)) AS avg_amount
FROM orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_day = '2026-11-20';
```

`COUNT(*)` đếm dòng khớp truy vấn. `COUNT(column)` đếm giá trị không null của cột đó; `MIN`, `MAX`, `SUM` và `AVG` tổng hợp những giá trị phù hợp. `CAST` trước `AVG` giúp tránh mất độ chính xác do kiểu số nguyên. Phép tổng hợp chạy trên các dòng được đọc, không có một bộ đếm chính xác tức thời được duy trì cho mọi truy vấn tùy ý.

Truy vấn tổng hợp **trên một partition có kích thước đã được kiểm soát** dễ dự đoán hơn truy vấn thống kê toàn bảng. Không dùng `COUNT(*)` trên bảng dữ liệu lớn trong request thời gian thực chỉ để vẽ tổng số đơn; cân nhắc bảng tổng hợp hoặc luồng cập nhật số liệu riêng.

Nếu trộn cột thường với hàm aggregate nhưng không nhóm tương ứng, Cassandra có thể chọn giá trị cột thường từ **dòng đầu tiên** của tập được tổng hợp. Ví dụ `SELECT status, count(*) ...` không có nghĩa là đếm theo từng `status`; nếu cần nhóm theo trạng thái, phải thiết kế mô hình dữ liệu phục vụ kiểu truy vấn đó.

## 6. SELECT JSON và DISTINCT: hai kiểu đầu ra đặc biệt

### 6.1. SELECT JSON: mỗi dòng thành một đối tượng JSON

```sql
SELECT JSON ordered_at, status, amount_cents
FROM orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_day = '2026-11-20';
```

Mỗi dòng trong result set có một trường JSON (thường được cqlsh hiển thị là `[json]`) chứa **đối tượng JSON mã hóa các selector**. Nó không biến Cassandra thành cơ sở dữ liệu document và không thay đổi schema. Phân biệt:

| Câu lệnh | Hình dạng dữ liệu trả về |
| --- | --- |
| `SELECT status, tags ...` | Hai cột CQL có kiểu gốc `text`, `set<text>`. |
| `SELECT status, toJson(tags) AS tags_json ...` | Một cột `text` cùng một cột `text` chứa chuỗi JSON. |
| `SELECT JSON status, tags ...` | Một cột chứa chuỗi JSON đại diện cho cả dòng được chọn. |

Trong ứng dụng Java, `SELECT` thường với kiểu CQL gốc giúp mapping kiểu dữ liệu rõ ràng. `SELECT JSON` thuận tiện khi tích hợp hoặc quan sát dữ liệu, nhưng cần xét chi phí mã hóa/giải mã và quy ước tên key trong JSON.

### 6.2. SELECT DISTINCT: chỉ với các cột thích hợp

```sql
-- Hai cột này cấu thành partition key của bảng ví dụ.
SELECT DISTINCT customer_id, order_day
FROM orders_by_customer;
```

`DISTINCT` của Cassandra chủ yếu dùng để lấy kết quả duy nhất cho **partition key** (và trong các trường hợp hợp lệ có thể gồm static columns). Không thể áp dụng tùy ý như `SELECT DISTINCT status FROM ...` để đếm các trạng thái khác nhau. Ví dụ trên không giới hạn partition, vì vậy vẫn có thể phải duyệt dữ liệu trên nhiều node; chỉ nên dùng khi biết rõ kích thước và yêu cầu vận hành.

## 7. Quan hệ giữa biểu thức SELECT và phân trang

Hãy phân biệt ba khái niệm:

1. **Projection**: `SELECT ordered_at, status` chọn cột xuất ra.
2. **Giới hạn truy vấn**: `LIMIT 20` giới hạn số dòng kết quả; `PER PARTITION LIMIT 20` giới hạn trên mỗi partition.
3. **Paging**: ứng dụng Java driver thường đọc kết quả qua nhiều page bằng cấu hình page size và paging state. Page size không phải số dòng tối đa của toàn truy vấn.

Ví dụ lấy tối đa 20 đơn trong một ngày, mới nhất trước:

```sql
SELECT ordered_at, status, amount_cents
FROM orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_day = '2026-11-20'
ORDER BY ordered_at DESC
LIMIT 20;
```

Trong bảng đã định nghĩa `CLUSTERING ORDER BY (ordered_at DESC)`, thứ tự trên phù hợp với clustering order. Cassandra không cung cấp mô hình `LIMIT 20 OFFSET 20` kiểu SQL để phân trang sâu tùy ý. Khi xây API Java, dùng cơ chế paging của driver và lưu paging state phù hợp với truy vấn; cần hiểu rằng tập dữ liệu có thể thay đổi giữa các lượt đọc.

## 8. Những nhầm lẫn phổ biến

| Mong đợi hoặc cách viết sai | Vấn đề | Cách xử lý |
| --- | --- | --- |
| `SELECT *` luôn hiệu quả nếu có `LIMIT 10` | Có thể vẫn chạm nhiều partition hoặc quét dữ liệu để tìm 10 dòng. | Truy vấn theo partition key, giới hạn partition và chỉ chọn cột cần. |
| `SELECT status FROM ... WHERE status = 'PAID'` | `status` không nằm trong khóa bảng ví dụ; truy vấn này không có đường truy cập phù hợp. | Tạo bảng phục vụ truy vấn theo trạng thái hoặc cân nhắc chỉ mục đúng mục tiêu, đánh giá kế hoạch đọc. |
| `SELECT status AS s ... WHERE s = 'PAID'` | Alias chỉ là tên kết quả, không dùng được trong `WHERE`. | Dùng tên cột gốc và điều kiện lọc hợp lệ. |
| `ORDER BY amount_cents DESC` | `amount_cents` là cột thường, không phải clustering key. | Thiết kế thêm bảng có clustering key tương ứng nếu thực sự cần cách sắp xếp này. |
| `SELECT DISTINCT status FROM ...` | `DISTINCT` không dùng tùy ý trên non-key column. | Thiết kế bảng/luồng tổng hợp cho tập giá trị trạng thái. |
| `amount_cents / 100` luôn cho số thập phân | Chia hai kiểu nguyên làm mất phần lẻ. | `CAST(amount_cents AS decimal) / 100` trước khi chia. |
| `COUNT(*)` toàn bảng rẻ vì kết quả một ô | Cassandra vẫn cần đọc các dòng liên quan để đếm. | Giới hạn tập dữ liệu hoặc duy trì số liệu tổng hợp. |
| `ALLOW FILTERING` làm truy vấn theo mọi cột chạy nhanh | Nó có thể cho phép scan rộng với độ trễ không ổn định. | Sửa mẫu truy vấn, schema và chỉ mục cho phù hợp. |
| `SELECT JSON` tương đương `toJson(tags)` | Một bên mã hóa cả dòng; một bên mã hóa đúng một giá trị. | Chọn cấu trúc trả về phù hợp API. |

Một hệ quả quan trọng khác: đổi danh sách cột trong `SELECT` **không đổi partition được định tuyến đến**. Tính hiệu quả của Cassandra chủ yếu đến từ việc tìm đúng partition, tránh partition quá lớn, hạn chế scan không cần thiết và chọn consistency đáp ứng yêu cầu đọc.

## 9. Bài thực hành ngắn và gợi ý đáp án

**Bài 1.** Từ partition của khách `11111111-1111-4111-8111-111111111111` ngày `2026-11-20`, trả `ordered_at`, `status` với bí danh `state`, tối đa 10 dòng.

```sql
SELECT ordered_at, status AS state
FROM orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_day = '2026-11-20'
LIMIT 10;
```

**Bài 2.** Trả số tiền theo đơn vị lớn hơn `cents`, giữ phần thập phân.

```sql
SELECT ordered_at,
       CAST(amount_cents AS decimal) / 100 AS amount_units
FROM orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_day = '2026-11-20';
```

**Bài 3.** Xem timestamp lần ghi gần nhất của `status` và TTL còn lại của `note`.

```sql
SELECT ordered_at,
       writetime(status) AS write_timestamp_us,
       ttl(note) AS remaining_ttl_s
FROM orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_day = '2026-11-20';
```

**Tự kiểm tra:** Tại sao `SELECT status FROM orders_by_customer WHERE status = 'PAID'` không thể được sửa bằng cách chỉ thêm `LIMIT 10`? Vì `LIMIT` giới hạn **kết quả**, nhưng không cung cấp partition key hay đường truy cập theo `status`. Để truy vấn nhiều khách/ngày theo `status` với độ trễ ổn định, phải thiết kế cách lưu và truy cập dữ liệu tương ứng.

## 10. Ghi nhớ khi sử dụng trong ứng dụng Java

Một câu `SELECT` có thể trả về cột gốc, cột alias hoặc biểu thức với **kiểu kết quả mới**. Khi triển khai với Java driver:

- Chuẩn bị câu lệnh có bind marker `?` cho các giá trị `customer_id`, `order_day`; không nối chuỗi dữ liệu người dùng vào CQL.
- Ánh xạ đúng kiểu CQL, ví dụ `uuid` → `UUID`, `date` → `LocalDate`, `bigint` → `long`/`Long`, `decimal` → `BigDecimal`.
- Cấu hình consistency level và page size ở tầng driver/request; danh sách selector không điều khiển chúng.
- Khi đổi alias hoặc kiểu biểu thức, kiểm tra phần code đọc cột trong `Row`/mapper vì tên và kiểu cột trả về có thể thay đổi.

Tư duy cần giữ lại là: **`WHERE` quyết định phạm vi đọc theo data model; `SELECT` quyết định cấu trúc và phép biến đổi của kết quả**. Hai phần phải cùng phục vụ một use case cụ thể, đặc biệt khi hệ thống Cassandra được phân vùng và nhân bản trên nhiều node.

## Tài liệu tham khảo

- [Apache Cassandra 5.0 — CQL Data Manipulation: SELECT](https://cassandra.apache.org/doc/5.0/cassandra/developing/cql/dml.html)
- [Apache Cassandra 5.0 — CQL Functions](https://cassandra.apache.org/doc/5.0/cassandra/developing/cql/functions.html)
- [Apache Cassandra 5.0 — Arithmetic Operators](https://cassandra.apache.org/doc/5.0/cassandra/developing/cql/operators.html)
- [Apache Cassandra 5.0 — JSON Support](https://cassandra.apache.org/doc/5.0/cassandra/developing/cql/json.html)
- [Apache Cassandra — Using Arithmetic Operators in Cassandra 4.0](https://cassandra.apache.org/_/blog/Using-Arithmetic-Operators-in-Cassandra-4.0.html)
