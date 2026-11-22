# Ghi giá trị của static column trong Apache Cassandra

Trong một bảng Apache Cassandra có nhiều hàng thuộc cùng một phân vùng, đôi khi mọi hàng cần dùng chung một thông tin: đơn vị tiền tệ của tháng, nhãn phân loại của nhóm dữ liệu hoặc cấu hình áp dụng cho cả phân vùng. **Static column** là cơ chế lưu một giá trị **ở cấp phân vùng (partition)** thay vì lặp lại thành các giá trị độc lập tại từng hàng theo clustering key.

Bài học thuộc chương **Ghi và xóa bằng CQL** trong module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**, tập trung vào cách khai báo, ghi, đọc và xóa static column bằng CQL, đồng thời giải thích ảnh hưởng của partition key, replication, consistency level, TTL và cập nhật cạnh tranh. Ví dụ Java Driver ở cuối bài giúp chuyển kiến thức này thành thao tác an toàn trong ứng dụng Java.

Sau bài này, bạn cần có thể:

- Phân biệt **partition key**, **clustering column**, **regular column** và **static column**.
- Dự đoán chính xác hàng nào nhìn thấy giá trị static khi ghi bằng `INSERT` hoặc `UPDATE`.
- Viết mutation **chỉ với partition key** khi chỉ cập nhật static column.
- Hiểu chuyện gì xảy ra nếu ghi static khi phân vùng chưa có hàng clustering nào.
- Phân biệt xóa một hàng, xóa một static column và xóa cả phân vùng.
- Biết các lưu ý khi dùng TTL, timestamp, LWT và Java Driver với dữ liệu ở cấp phân vùng.

## 1. Vì sao cần static column?

Giả sử một ứng dụng bán hàng cần đọc **các đơn của một khách theo từng tháng**. Mỗi đơn có trạng thái riêng, nhưng các đơn của cùng khách trong tháng đều dùng chung đơn vị tiền tệ báo cáo và ghi chú đối soát.

Nếu lưu `billing_currency` vào từng hàng đơn, ta phải lặp lại cùng giá trị nhiều lần. Khi đổi đơn vị báo cáo cho một tháng, ứng dụng phải tìm và sửa toàn bộ hàng đơn của phân vùng. **Static column** giải quyết trường hợp dữ liệu thực sự thuộc về **phân vùng**.

```text
Partition: (customer A, 2026-11)
|
+-- Static: billing_currency = "VND"
|           month_note = "Đang đối soát"
|
+-- Row order X: status = CREATED, total = 250000
+-- Row order Y: status = PAID,    total = 750000

Partition: (customer A, 2026-12)
|
+-- Static: billing_currency = "USD"
|           month_note = "Đơn tháng 12"
|
+-- Row order Z: status = CREATED, total = 40
```

**Một giá trị static** được gắn với mỗi phân vùng logic, dù nhiều hàng trong phân vùng cùng nhìn thấy giá trị đó khi đọc. Static column **không phải** cột toàn cục áp dụng cho cả bảng.

## 2. Khai báo bảng có static column

Giả định keyspace `shop` đã tồn tại. Tạo bảng theo truy vấn “liệt kê đơn hàng của khách theo tháng”:

```sql
CREATE TABLE shop.orders_by_customer_month (
    customer_id      uuid,
    order_month      text,
    order_id         uuid,
    ordered_at       timestamp,
    order_status     text,
    total            decimal,
    billing_currency text static,
    month_note       text static,
    month_budget     decimal static,
    PRIMARY KEY ((customer_id, order_month), order_id)
);
```

Phân tích schema:

| Thành phần | Cột | Ý nghĩa |
| --- | --- | --- |
| **Partition key ghép** | `(customer_id, order_month)` | Xác định phân vùng; các replica chịu trách nhiệm cho phân vùng được chọn bằng token của partition key. |
| **Clustering column** | `order_id` | Phân biệt các hàng đơn bên trong cùng phân vùng. |
| **Regular column** | `ordered_at`, `order_status`, `total` | Mỗi hàng đơn có giá trị riêng. |
| **Static column** | `billing_currency`, `month_note`, `month_budget` | Mỗi phân vùng có giá trị dùng chung, không phụ thuộc `order_id`. |

Hai đơn có cùng `customer_id`, `order_month` nhưng khác `order_id` là **hai hàng khác nhau**, chia sẻ giá trị static. Hai đơn có `order_month` khác nhau thuộc **hai phân vùng khác nhau**, nên giá trị static **không chia sẻ** giữa chúng.

### Điều kiện khai báo

- Chỉ khai báo `static` ở **cột không thuộc primary key**.
- Bảng cần có **ít nhất một clustering column** để phân biệt được dữ liệu cấp phân vùng với dữ liệu cấp hàng. Một bảng chỉ có partition key, chẳng hạn `PRIMARY KEY (customer_id)` và không có clustering column, không dùng static column theo cách này.
- Static column có thể lưu kiểu scalar như `text`, `decimal` và nhiều kiểu dữ liệu CQL khác theo ràng buộc schema; ví dụ này dùng scalar để tách rõ ngữ nghĩa ghi.
- `static` **không phải chỉ thị nhân bản**: replication được cấu hình ở keyspace, áp dụng cho dữ liệu phân vùng thông qua cơ chế replica bình thường.

Các phiên bản Cassandra có thể có chi tiết khác nhau về kiểu dữ liệu và tính năng CQL. Khi áp dụng sang schema khác, hãy kiểm tra cú pháp của phiên bản đang triển khai.

## 3. Ghi static column bằng UPDATE chỉ với partition key

Đây là đặc điểm quan trọng nhất của static column. Với regular column, ta thường cần định danh **một hàng đầy đủ**, bao gồm clustering key. Với **static column**, chỉ cần đủ các thành phần **partition key**:

```sql
UPDATE shop.orders_by_customer_month
SET billing_currency = 'VND',
    month_note = 'Dang doi soat'
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11';
```

Lệnh không có `order_id`. Nó cập nhật dữ liệu chung của phân vùng:

```text
Full partition key = (11111111-1111-4111-8111-111111111111, '2026-11')
    billing_currency = 'VND'
    month_note = 'Dang doi soat'
```

Nếu phân vùng đã có hàng đơn X và Y, **cả X lẫn Y sẽ nhìn thấy** `billing_currency = 'VND'` và ghi chú mới khi được đọc. Cassandra không thực hiện N lần `UPDATE` riêng cho N đơn; mutation ghi các cell static ở cấp phân vùng.

### Ghi regular column phải định vị hàng

Để cập nhật trạng thái của **một đơn**, cần đủ khóa:

```sql
UPDATE shop.orders_by_customer_month
SET order_status = 'PAID'
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11'
  AND order_id = 22222222-2222-4222-8222-222222222222;
```

Ngược lại, lệnh sau **không hợp lệ** khi chỉ muốn cập nhật regular column:

```sql
-- SAI: thiếu clustering key order_id cho regular column order_status.
UPDATE shop.orders_by_customer_month
SET order_status = 'PAID'
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11';
```

Lỗi tư duy thường gặp là xem ghi static với `WHERE` chỉ có partition key như “update tất cả hàng”. Ý nghĩa đúng là: **ghi một giá trị ở cấp phân vùng**. Nếu cần đổi `order_status` của nhiều đơn, phải xây dựng thao tác riêng theo khóa hàng hoặc thiết kế bảng và quy trình khác; không thể lấy cách viết static để áp dụng cho mọi regular column.

### Khi chỉ biết một phần partition key

Partition key của ví dụ là tổ hợp `(customer_id, order_month)`. Chỉ biết `customer_id` vẫn **chưa đủ** để định danh một phân vùng:

```sql
-- SAI: thiếu thành phần order_month của partition key ghép.
UPDATE shop.orders_by_customer_month
SET billing_currency = 'VND'
WHERE customer_id = 11111111-1111-4111-8111-111111111111;
```

Static có phạm vi là **một partition key đầy đủ**, không phải một phần của khóa và càng không phải mọi phân vùng của khách hàng.

## 4. Ghi static column bằng INSERT

`INSERT` của Cassandra cũng có thể ghi các static column. Nếu ghi một hàng đơn kèm metadata của tháng, nêu **full primary key** và các cột tương ứng:

```sql
INSERT INTO shop.orders_by_customer_month (
    customer_id, order_month, order_id,
    ordered_at, order_status, total,
    billing_currency, month_note
)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11',
    22222222-2222-4222-8222-222222222222,
    '2026-11-21 10:15:00+0700',
    'CREATED',
    250000.00,
    'VND',
    'Dang doi soat'
);
```

Trong cùng mutation có hai nhóm dữ liệu:

- `order_status`, `total`, `ordered_at` thuộc hàng có `order_id` cụ thể.
- `billing_currency` và `month_note` thuộc **phân vùng của tháng**, được chia sẻ bởi mọi đơn cùng partition key.

Nếu sau đó thêm đơn thứ hai:

```sql
INSERT INTO shop.orders_by_customer_month (
    customer_id, order_month, order_id,
    ordered_at, order_status, total
)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11',
    33333333-3333-4333-8333-333333333333,
    '2026-11-21 10:30:00+0700',
    'PAID',
    750000.00
);
```

Lần `INSERT` thứ hai **không nhắc tới** static column, nên không xóa hoặc ghi đè metadata của phân vùng. Khi đọc cả hai hàng, `billing_currency` vẫn là `'VND'`.

### INSERT chỉ chứa partition key và static column

Một ngoại lệ quan trọng so với `INSERT` regular column: **nếu chỉ ghi static column**, có thể không cung cấp clustering key.

```sql
INSERT INTO shop.orders_by_customer_month (
    customer_id, order_month, billing_currency, month_note
)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-12',
    'USD',
    'Chuan bi chot thang'
);
```

Câu này hợp lệ vì phần dữ liệu ngoài partition key **chỉ gồm static column**. Nó tạo hoặc cập nhật metadata của phân vùng tháng `2026-12`, **không tạo một đơn hàng có `order_id` thật**. Không thể áp dụng cách bỏ `order_id` tương tự cho `INSERT` một regular column như `order_status`.

Ví dụ sai:

```sql
-- SAI: regular column order_status cần khóa hàng có order_id.
INSERT INTO shop.orders_by_customer_month (
    customer_id, order_month, order_status
)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-12',
    'CREATED'
);
```

Đây là lý do cần phân biệt static column và regular column trước khi sinh câu lệnh từ ứng dụng.

## 5. Static-only partition: ghi trước khi có hàng clustering

Hãy xét phân vùng tháng `2026-12` vừa được tạo chỉ bằng các static column. Chưa có hàng nào có `order_id` cụ thể. Cassandra vẫn có thể lưu metadata static của phân vùng.

Đọc bằng:

```sql
SELECT customer_id, order_month, order_id,
       billing_currency, month_note, order_status
FROM shop.orders_by_customer_month
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-12';
```

Với phân vùng chỉ có dữ liệu static và không có hàng clustering, Cassandra có thể hiển thị một **hàng kết quả biểu diễn static-only partition**, trong đó **clustering column `order_id` và regular column `order_status` được đọc là null**. Đây là cách kết quả CQL biểu diễn metadata cấp phân vùng, **không phải một đơn hàng nghiệp vụ có order_id null**.

Sau khi ghi thêm đơn tháng 12:

```sql
INSERT INTO shop.orders_by_customer_month (
    customer_id, order_month, order_id,
    order_status, total
)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-12',
    44444444-4444-4444-8444-444444444444,
    'CREATED',
    40.00
);
```

Hàng đơn thật được thêm vào cùng phân vùng và có thể đọc cùng `billing_currency = 'USD'`.

**Lưu ý cho code Java:** Nếu ứng dụng đọc danh sách đơn, đừng biến một kết quả **static-only** với clustering key null thành đơn hàng giả. Kiểm tra sự hiện diện của clustering key khi ánh xạ dữ liệu, hoặc tách rõ API đọc metadata và API đọc danh sách đơn.

## 6. Đọc static column: giá trị xuất hiện cùng nhiều hàng

Với hai đơn ở tháng 11, thực hiện:

```sql
SELECT order_id, order_status, total,
       billing_currency, month_note
FROM shop.orders_by_customer_month
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11';
```

Kết quả minh họa:

| order_id (rút gọn) | order_status | total | billing_currency | month_note |
| --- | --- | ---: | --- | --- |
| `2222...2222` | CREATED | 250000.00 | VND | Dang doi soat |
| `3333...3333` | PAID | 750000.00 | VND | Dang doi soat |

Vì cả hai hàng cùng phân vùng, hai dòng kết quả cùng hiển thị metadata static. **Việc lặp lại trên kết quả SELECT không có nghĩa giá trị được lưu thành hai cell regular tách biệt.**

Có thể đọc dữ liệu cấp phân vùng bằng `SELECT DISTINCT` trên các cột partition key và static column:

```sql
SELECT DISTINCT customer_id, order_month,
       billing_currency, month_note
FROM shop.orders_by_customer_month
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11';
```

`DISTINCT` trong CQL có quy tắc riêng: trường được chọn phải phù hợp với **partition key và static column**; không dùng nó như `SELECT DISTINCT` tùy ý trên regular column kiểu SQL quan hệ.

### Static column không áp dụng cho mọi phân vùng của khách

Ví dụ thay đổi metadata tháng 12:

```sql
UPDATE shop.orders_by_customer_month
SET billing_currency = 'EUR'
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-12';
```

Lệnh này không làm đổi `billing_currency` của tháng `2026-11`, cũng không làm đổi dữ liệu của khách khác. Phạm vi static column **chính xác bằng partition key đầy đủ**.

## 7. Xóa static column, xóa hàng, xóa phân vùng

Ba thao tác dưới đây có phạm vi khác nhau, dù đều liên quan đến cùng bảng.

### A. Xóa riêng một giá trị static

```sql
DELETE month_note
FROM shop.orders_by_customer_month
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11';
```

Lệnh này xóa giá trị `month_note` ở cấp phân vùng. Khi đọc các đơn tháng 11, `month_note` được đọc là `null` sau khi dấu xóa đã được quan sát, nhưng `billing_currency`, `order_status` và `total` không bị chính lệnh này xóa.

Với static column scalar, có thể diễn đạt ý định xóa bằng `UPDATE ... SET month_note = NULL`:

```sql
UPDATE shop.orders_by_customer_month
SET month_note = NULL
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11';
```

Hai câu lệnh minh họa cùng **ý định xóa một static column**, chỉ cần dùng một trong hai. Cassandra ghi tombstone để đảm bảo phiên bản static cũ không xuất hiện lại khi đọc/hòa giải dữ liệu.

### B. Xóa một hàng theo clustering key

```sql
DELETE FROM shop.orders_by_customer_month
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11'
  AND order_id = 22222222-2222-4222-8222-222222222222;
```

Đây là thao tác xóa **hàng đơn X**. Nó không tự động xóa `billing_currency` hay `month_budget` của phân vùng. Đơn Y vẫn có thể đọc cùng metadata static, vì static data tồn tại độc lập với từng hàng clustering.

### C. Xóa cả phân vùng

```sql
-- CHỈ chạy khi thật sự muốn xóa toàn bộ tháng của khách này.
DELETE FROM shop.orders_by_customer_month
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11';
```

Lệnh `DELETE` không nêu cột và chỉ có partition key là **xóa phân vùng**: nó làm vô hiệu cả các hàng đơn lẫn dữ liệu static của phân vùng đó. Đây là khác biệt quan trọng với `UPDATE` chỉ sửa static column theo partition key.

| Lệnh | Hàng đơn | Static column |
| --- | --- | --- |
| `DELETE month_note ... WHERE <partition key>` | Không tự xóa | Xóa `month_note` |
| `DELETE FROM ... WHERE <partition key + order_id>` | Xóa một hàng | Không tự xóa |
| `DELETE FROM ... WHERE <partition key>` | Xóa các hàng của phân vùng | Xóa các giá trị static của phân vùng |

Các lệnh xóa tạo **tombstone** theo phạm vi thích hợp. Compaction có thể thu gom dữ liệu đã xóa khi an toàn; repair giúp các replica hội tụ. Không nên xem lệnh `DELETE` thành công là dữ liệu đã bị loại khỏi mọi tệp SSTable ngay lập tức.

## 8. Timestamp, TTL và cập nhật cạnh tranh trên static column

Static column dùng cơ chế hòa giải phiên bản tương tự các cell thông thường. Giá trị mới được quyết định theo **write timestamp** của cell; đồng hồ hoặc timestamp tự cấp không phù hợp có thể gây xung đột khó dự đoán.

Ví dụ hai client cùng thay `month_note` cho một phân vùng:

```text
Client A: month_note = 'Dang doi soat', timestamp 1000000
Client B: month_note = 'Da chot',       timestamp 2000000

Khi các phiên bản hội tụ, 'Da chot' thắng vì timestamp lớn hơn.
```

Những timestamp trên chỉ để minh họa thứ tự; timestamp thực của Cassandra có đơn vị **microsecond từ Unix epoch**. Ghi vào `month_note` của tháng 11 không tranh chấp cell với `month_note` của tháng 12, vì đó là hai phân vùng khác nhau.

### TTL cho một static column

Có thể ghi static column với TTL, tính bằng giây:

```sql
UPDATE shop.orders_by_customer_month USING TTL 3600
SET month_note = 'Ghi chu tam thoi'
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-12';
```

Lệnh này đặt TTL cho giá trị `month_note` vừa ghi. **Nó không tự đặt TTL lên `billing_currency`, `month_budget` hoặc các regular column của đơn hàng**, vì các cột đó không có trong mutation.

Kiểm tra thông tin của cell:

```sql
SELECT DISTINCT customer_id, order_month,
       month_note, billing_currency
FROM shop.orders_by_customer_month
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-12';

SELECT month_note, TTL(month_note), WRITETIME(month_note)
FROM shop.orders_by_customer_month
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-12';
```

`TTL(month_note)` cho biết thời gian còn lại nếu cell đang có TTL; `WRITETIME(month_note)` cho biết timestamp ghi. Với phân vùng có hàng đơn, kết quả truy vấn thông thường có thể lặp giá trị static trên mỗi hàng được chọn. Khi TTL hết hạn, giá trị static không còn sống và có thể được đọc là `null`.

Nếu keyspace/bảng đang có thay đổi đồng thời, kết quả đọc phụ thuộc mức nhất quán và replica được hỏi. `CONSISTENCY QUORUM` trong `cqlsh` (với replication factor thích hợp) có thể yêu cầu nhiều replica phản hồi hơn so với `ONE`, nhưng **không biến việc cập nhật static thành khóa giao dịch cho mọi hàng đơn**.

### Khi cần điều kiện trước khi ghi

Nếu nghiệp vụ yêu cầu “chỉ chốt ghi chú khi hiện vẫn là `Dang doi soat`”, một `SELECT` rồi `UPDATE` thường có khoảng trống tranh chấp. Có thể dùng **lightweight transaction (LWT)** trên static column:

```sql
UPDATE shop.orders_by_customer_month
SET month_note = 'Da chot'
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11'
IF month_note = 'Dang doi soat';
```

Kết quả cho biết `[applied]` là `true` hoặc `false`. LWT cần cơ chế đồng thuận và có chi phí phối hợp cao hơn ghi thông thường, nên dùng khi điều kiện cạnh tranh thật sự quan trọng. Lưu ý: điều kiện `IF` ở trên chỉ bảo vệ **giá trị đang kiểm tra**; nó không tự đảm bảo mọi `order_status` trong phân vùng đều ở trạng thái đã đối soát.

### Ghi lặp lại và lỗi timeout

Nếu client nhận timeout khi cập nhật `billing_currency` hoặc `month_note`, không thể suy ra chắc chắn mutation chưa tới replica nào. Khi retry, lệnh ghi cùng khóa với timestamp mới có thể thắng một mutation cạnh tranh vừa được client khác thực hiện. Với thao tác có ý nghĩa nghiệp vụ như “chốt sổ tháng”, hãy thiết kế trạng thái chuyển đổi và điều kiện LWT phù hợp thay vì retry vô hạn một upsert không điều kiện.

## 9. Java Driver: ghi metadata của phân vùng

Một ứng dụng Java thường có hai luồng ghi khác nhau:

1. Lưu/cập nhật **đơn hàng** theo full primary key `(customer_id, order_month, order_id)`.
2. Lưu/cập nhật **metadata tháng** theo partition key `(customer_id, order_month)`.

Nên thể hiện hai thao tác này bằng những câu prepared statement có khóa và danh sách cột rõ ràng, để việc sửa thông tin của tháng không vô tình đòi hỏi hoặc ghi đè dữ liệu của một đơn.

### Prepared UPDATE chỉ cập nhật static column

Ví dụ Apache Cassandra Java Driver 4.x, giả sử ứng dụng đã có `CqlSession session` và `UUID customerId`:

```java
PreparedStatement updateMonth = session.prepare(
    "UPDATE shop.orders_by_customer_month " +
    "SET billing_currency = :currency, month_note = :note " +
    "WHERE customer_id = :customer_id AND order_month = :month"
);

BoundStatementBuilder builder = updateMonth.boundStatementBuilder()
    .setUuid("customer_id", customerId)
    .setString("month", "2026-11")
    .setString("currency", "VND")
    .unset("note");  // Khong muon sua month_note

session.execute(builder.build());
```

Không có marker `order_id`, vì câu lệnh này chỉ ghi static column. `unset("note")` giữ nguyên `month_note` của phân vùng; nếu dùng `setToNull("note")`, ứng dụng sẽ **xóa giá trị static** bằng tombstone. Đây là điểm quan trọng đối với API cập nhật từng phần metadata.

Nếu API cho phép client gửi JSON:

```json
{
  "billingCurrency": "USD"
}
```

thì yêu cầu có nghĩa “đổi `billing_currency`, không động vào `month_note`”. Cần phân biệt trường **không xuất hiện** và trường được gửi **rõ ràng là null**, chẳng hạn qua `JsonNode.has(...)`/`isNull()` hoặc cơ chế theo dõi sự hiện diện của trường. Với metadata bắt buộc như đơn vị tiền tệ, có thể từ chối null bằng validation thay vì cho phép xóa.

### Prepared INSERT khi tạo metadata trước các đơn

```java
PreparedStatement insertMonth = session.prepare(
    "INSERT INTO shop.orders_by_customer_month " +
    "(customer_id, order_month, billing_currency, month_budget) " +
    "VALUES (?, ?, ?, ?)"
);

BoundStatement statement = insertMonth.bind(
    customerId,
    "2027-01",
    "VND",
    new java.math.BigDecimal("20000000.00")
);

session.execute(statement);
```

Câu CQL bên trong chỉ ghi **partition key và static column**, nên không cần `order_id`. Nếu thao tác tạo tháng cần “chỉ tạo khi chưa có metadata” theo ràng buộc nghiệp vụ, hãy xác định cẩn thận thế nào là “đã tồn tại” với static-only partition và cân nhắc điều kiện LWT thích hợp; đừng giả sử `INSERT` mặc định từ chối một partition key đã có.

### Đọc và ánh xạ kết quả

```java
PreparedStatement readMonth = session.prepare(
    "SELECT DISTINCT customer_id, order_month, " +
    "billing_currency, month_note, month_budget " +
    "FROM shop.orders_by_customer_month " +
    "WHERE customer_id = ? AND order_month = ?"
);

Row row = session.execute(
    readMonth.bind(customerId, "2026-11")
).one();

if (row != null) {
    String currency = row.getString("billing_currency");
    String note = row.getString("month_note");
    java.math.BigDecimal budget = row.getBigDecimal("month_budget");
    // Xu ly metadata theo hop dong API.
}
```

Các import, cấu hình session, validation và xử lý lỗi mạng được lược bỏ để tập trung vào CQL. `SELECT DISTINCT` này chọn partition key và static column nên không vô tình trả một metadata object cho mỗi đơn. Cần xử lý trường hợp không có hàng trả về hoặc cột static chưa được ghi (trả null) theo ý nghĩa nghiệp vụ của ứng dụng.

## 10. Thực hành từng bước: một giá trị static cho nhiều hàng

Chạy trên môi trường học tập với bảng `shop.orders_by_customer_month` đã tạo ở phần 2. Dùng một partition key riêng là khách `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa` trong tháng `2027-02` để không phụ thuộc các ví dụ trước.

### Bước 1 — Tạo static-only partition

```sql
INSERT INTO shop.orders_by_customer_month (
    customer_id, order_month, billing_currency, month_note
)
VALUES (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    '2027-02',
    'VND',
    'Moi khoi tao'
);

SELECT order_id, order_status, billing_currency, month_note
FROM shop.orders_by_customer_month
WHERE customer_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND order_month = '2027-02';
```

**Dự đoán:** dữ liệu metadata cấp phân vùng có thể xuất hiện ngay cả khi `order_id` chưa có hàng thật; nếu nhìn thấy hàng với clustering key null, đó là biểu diễn static-only partition.

### Bước 2 — Thêm hai đơn, không ghi lại static

```sql
INSERT INTO shop.orders_by_customer_month (
    customer_id, order_month, order_id, order_status, total
)
VALUES (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    '2027-02',
    bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb,
    'CREATED',
    100000.00
);

INSERT INTO shop.orders_by_customer_month (
    customer_id, order_month, order_id, order_status, total
)
VALUES (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    '2027-02',
    cccccccc-cccc-4ccc-8ccc-cccccccccccc,
    'PAID',
    200000.00
);

SELECT order_id, order_status, total, billing_currency, month_note
FROM shop.orders_by_customer_month
WHERE customer_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND order_month = '2027-02';
```

**Dự đoán:** có hai hàng đơn thật với `billing_currency = 'VND'` và `month_note = 'Moi khoi tao'`. Metadata không bị xóa dù hai lần `INSERT` chỉ liệt kê regular column.

### Bước 3 — Đổi static, quan sát cả hai hàng

```sql
UPDATE shop.orders_by_customer_month
SET month_note = 'Dang duyet'
WHERE customer_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND order_month = '2027-02';

SELECT order_id, order_status, billing_currency, month_note
FROM shop.orders_by_customer_month
WHERE customer_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND order_month = '2027-02';
```

**Dự đoán:** cả hai dòng kết quả đều có `month_note = 'Dang duyet'`. Không có vòng lặp cập nhật theo từng `order_id`.

### Bước 4 — Đổi regular column của đúng một đơn

```sql
UPDATE shop.orders_by_customer_month
SET order_status = 'SHIPPING'
WHERE customer_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND order_month = '2027-02'
  AND order_id = bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb;
```

**Dự đoán:** chỉ trạng thái của đơn `bbbb...` đổi. `month_note` của cả phân vùng không thay đổi.

### Bước 5 — Xóa một hàng, metadata vẫn còn

```sql
DELETE FROM shop.orders_by_customer_month
WHERE customer_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND order_month = '2027-02'
  AND order_id = bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb;

SELECT order_id, order_status, billing_currency, month_note
FROM shop.orders_by_customer_month
WHERE customer_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND order_month = '2027-02';
```

**Dự đoán:** đơn `cccc...` vẫn tồn tại và vẫn nhìn thấy metadata static.

### Bước 6 — Xóa chỉ một static column

```sql
DELETE month_note
FROM shop.orders_by_customer_month
WHERE customer_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND order_month = '2027-02';

SELECT order_id, billing_currency, month_note
FROM shop.orders_by_customer_month
WHERE customer_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND order_month = '2027-02';
```

**Dự đoán:** `month_note` đọc là null; `billing_currency` vẫn là VND và đơn `cccc...` vẫn tồn tại.

### Bước 7 — Phân biệt xóa phân vùng

Chỉ trên dữ liệu thực hành có thể xóa, thử:

```sql
DELETE FROM shop.orders_by_customer_month
WHERE customer_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND order_month = '2027-02';
```

**Dự đoán:** đây là thao tác xóa **toàn bộ phân vùng**, gồm mọi hàng clustering và metadata static. Không chạy kiểu xóa này trên phân vùng chứa dữ liệu cần giữ.

### Bảng kết quả kỳ vọng

| Sau bước | Hàng đơn còn sống | `billing_currency` | `month_note` |
| --- | --- | --- | --- |
| 1 | Chưa có đơn thật | VND | Moi khoi tao |
| 2 | `bbbb...`, `cccc...` | VND (cùng cho hai đơn) | Moi khoi tao |
| 3 | `bbbb...`, `cccc...` | VND | Dang duyet |
| 4 | `bbbb...`, `cccc...` | VND | Dang duyet |
| 5 | `cccc...` | VND | Dang duyet |
| 6 | `cccc...` | VND | null |
| 7 | Không còn | Không còn | Không còn |

Các kỳ vọng giả định không có ghi cạnh tranh, TTL khác hay timestamp bất thường. Dấu xóa có thể còn tồn tại trong bộ lưu trữ vật lý cho đến khi đủ điều kiện được thu gom.

## 11. Khi nào nên dùng static column và lỗi thường gặp

Static column phù hợp khi một thuộc tính **thực sự phụ thuộc vào partition key, không phụ thuộc clustering key**, và được đọc cùng hoặc đọc riêng với dữ liệu trong phân vùng đó.

| Tình huống | Dùng static column? | Lý do |
| --- | --- | --- |
| Mỗi khách và tháng có một đơn vị tiền tệ báo cáo | Có thể phù hợp | Phụ thuộc `(customer_id, order_month)` |
| Mỗi đơn có một trạng thái giao hàng riêng | Không | Trạng thái phụ thuộc `order_id` |
| Giá bán của từng sản phẩm khác nhau trong một giỏ | Không, nếu mỗi sản phẩm là một hàng | Giá thuộc từng clustering row |
| Một ghi chú chung cho tất cả sự kiện của một phiên | Có thể phù hợp | Ghi chú thuộc phiên/partition |
| Cấu hình toàn cục áp dụng cho mọi khách của bảng | Không phù hợp chỉ vì dùng `static` | Static là **theo phân vùng**, không phải toàn bảng |

### Lỗi thường gặp

1. **Nhầm static với regular column.** Dùng `WHERE` thiếu clustering key để sửa regular column dẫn đến lỗi; chỉ ghi static mới có ngoại lệ theo partition key.
2. **Nhầm static với trường toàn bảng.** Ghi metadata tháng 11 không làm thay đổi tháng 12 hoặc khách khác.
3. **Cho rằng INSERT luôn cần clustering key.** `INSERT` chỉ chứa partition key và static column có thể hợp lệ; `INSERT` regular column thì vẫn cần xác định hàng.
4. **Xem kết quả static-only là một hàng nghiệp vụ thật.** Một hàng hiển thị `order_id = null` là biểu diễn metadata, không phải đơn hàng hợp lệ.
5. **Xóa hàng rồi tưởng static cũng bị xóa.** Xóa một clustering row không làm mất metadata static; xóa cả partition mới ảnh hưởng toàn bộ.
6. **Dựa vào static để giải quyết phân vùng quá lớn.** Static giảm lặp giá trị metadata nhưng **không** giảm số hàng hoặc kích thước dữ liệu giao dịch của phân vùng; thiết kế partition key, phân bố tải và số lượng hàng vẫn cần được kiểm soát.
7. **Đổi static bằng upsert không điều kiện trong luồng có tranh chấp.** Nhiều client có thể ghi cạnh tranh; dùng `IF`/LWT khi cần điều kiện trạng thái cũ.
8. **Bind null cho trường bị thiếu trong API PATCH.** `NULL` có thể xóa static và tạo tombstone, còn `UNSET` giữ nguyên cell static không được cập nhật.

### Tự kiểm tra

**Câu 1.** Một phân vùng có 10.000 hàng và một `billing_currency static`. Chạy `UPDATE ... SET billing_currency = 'USD' WHERE <full partition key>` sẽ ghi 10.000 ô regular khác nhau?

**Trả lời:** Không. Mutation ghi giá trị static ở cấp phân vùng; 10.000 hàng có thể cùng nhìn thấy giá trị đó khi đọc.

**Câu 2.** Ghi `INSERT` với chỉ partition key và `month_note static` nhưng không có `order_id` có hợp lệ không?

**Trả lời:** Có, khi những cột không thuộc khóa được ghi đều là static column và bảng có định nghĩa static hợp lệ.

**Câu 3.** Chạy `DELETE FROM ... WHERE <partition key + order_id>` thì static column của phân vùng có bị xóa không?

**Trả lời:** Không do chính thao tác xóa hàng đó. Xóa riêng static column hoặc xóa cả phân vùng là những thao tác khác.

**Câu 4.** Đổi `month_note` của tháng 11 có ảnh hưởng đơn của tháng 12 không?

**Trả lời:** Không. Hai tháng tương ứng hai partition key khác nhau.

**Câu 5.** Một client muốn đổi `month_note` khi nó vẫn là `Dang doi soat`, trong khi client khác cũng có thể sửa cùng trường. Nên làm gì?

**Trả lời:** Dùng conditional update `IF month_note = 'Dang doi soat'` và kiểm tra kết quả `[applied]` nếu ràng buộc này quan trọng.

**Ghi nhớ:** **Static column thuộc về partition key, còn regular column thuộc về hàng xác định bởi full primary key.** Với static column, bạn có thể ghi bằng `UPDATE` chỉ có full partition key hoặc `INSERT` không có clustering key nếu chỉ ghi dữ liệu static. Mọi hàng của cùng phân vùng sẽ nhìn thấy giá trị static đó; đọc, xóa, TTL, timestamp và LWT vẫn tuân theo các cơ chế dữ liệu phân tán của Cassandra. Hiểu rõ ranh giới cấp phân vùng và cấp hàng giúp thiết kế bảng theo truy vấn đúng và tránh mutation vô tình ảnh hưởng phạm vi lớn hơn ý định của ứng dụng Java.
