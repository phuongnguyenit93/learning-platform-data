# Index Condition Pushdown và điều kiện được đẩy xuống storage engine

Một bảng khách hàng có vài triệu dòng. Ứng dụng cần tìm người ở một khu vực, đang hoạt động, có họ chứa một chuỗi nhất định và phần mô tả hồ sơ cũng chứa từ khóa. Index ghép có thể giúp MySQL tìm nhanh phạm vi khu vực/trạng thái, nhưng nếu mọi hàng trong phạm vi đều phải đọc đầy đủ rồi mới kiểm tra họ, MySQL vẫn có thể phải truy cập rất nhiều record.

Index Condition Pushdown (ICP) là tối ưu hóa cho phép MySQL đẩy một phần điều kiện có thể đánh giá chỉ bằng các cột nằm trong index xuống storage engine. Engine kiểm tra điều kiện ngay khi đọc index entry và chỉ lấy full row cho những entry vượt qua điều kiện đó. Nhờ vậy, ICP có thể giảm số lần đọc record đầy đủ, đặc biệt khi index không bao phủ toàn bộ cột mà truy vấn cần.

ICP không làm mọi điều kiện WHERE tự động chạy trong index, không thay thế thiết kế index và cũng không đồng nghĩa với covering index. Hiểu rõ phần điều kiện dùng để định vị index, phần có thể push xuống engine và phần còn phải lọc sau khi đọc row là chìa khóa để đánh giá lợi ích thực tế.

## 1. Index Condition Pushdown là gì?

Trong một truy vấn dùng secondary index, MySQL thường phải thực hiện hai bước:

1. Duyệt index để tìm các entry phù hợp với điều kiện truy cập.
2. Với mỗi entry cần thiết, đọc record đầy đủ từ clustered index (InnoDB) hoặc vị trí row tương ứng (MyISAM), rồi kiểm tra các điều kiện còn lại.

Nếu một điều kiện chỉ cần các cột đã có trong index, việc đọc full row trước khi kiểm tra điều kiện đó là lãng phí. ICP cho phép storage engine đánh giá điều kiện này ngay trên index entry.

Quy trình khái quát:

1. Optimizer chọn một index và xác định điều kiện truy cập.
2. Server tạo index condition từ các predicate có thể đánh giá bằng cột index.
3. Storage engine duyệt index entry và kiểm tra index condition.
4. Entry không đạt bị loại ngay tại engine, không cần đọc full row.
5. Entry đạt được dùng để đọc full row nếu truy vấn còn cần các cột không có trong index.
6. Server tiếp tục kiểm tra các điều kiện còn lại và tạo kết quả.

ICP thường có ích khi truy vấn dùng index để tìm một tập entry tương đối rộng, có thêm điều kiện lọc trên cột index, nhưng vẫn cần đọc các cột ngoài index để trả kết quả hoặc kiểm tra điều kiện khác.

## 2. Ví dụ: lọc index entry trước khi đọc full row

Tạo bảng hồ sơ khách hàng:

```sql
CREATE TABLE customers (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    region_code CHAR(2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    profile_text TEXT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    KEY idx_customer_region_status_lastname
        (region_code, status, last_name)
) ENGINE=InnoDB;
```

Truy vấn:

```sql
SELECT
    id,
    first_name,
    profile_text
FROM customers
WHERE region_code = 'VN'
  AND status = 'ACTIVE'
  AND last_name LIKE '%nguyen%'
  AND profile_text LIKE '%architect%';
```

Index `idx_customer_region_status_lastname` chứa ba cột: `region_code`, `status` và `last_name`. Điều kiện `region_code = 'VN'` và `status = 'ACTIVE'` giúp xác định phạm vi index. Điều kiện `last_name LIKE '%nguyen%'` không tạo được range prefix hữu ích vì wildcard đứng đầu, nhưng giá trị last_name vẫn có sẵn trong index entry nên storage engine có thể kiểm tra điều kiện này bằng ICP.

Ngược lại, `profile_text` không nằm trong index. Engine không thể kiểm tra điều kiện này chỉ bằng index entry. Các entry vượt qua index condition vẫn cần đọc full row để server kiểm tra `profile_text LIKE '%architect%'` và lấy `first_name`, `profile_text` trả về.

Nếu nhiều khách hàng ở VN có trạng thái ACTIVE nhưng chỉ một tỷ lệ nhỏ có họ chứa chuỗi cần tìm, ICP có thể tránh nhiều lần đọc full row.

## 3. ICP khác với điều kiện dùng để tìm range trong index

Không phải mọi predicate trên cột index đều có cùng vai trò.

Với index ghép:

```sql
KEY idx_orders_customer_status_created
    (customer_id, status, created_at)
```

Truy vấn:

```sql
SELECT id, total_amount
FROM orders
WHERE customer_id = 120
  AND status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at < '2026-02-01';
```

Cả ba điều kiện có thể tham gia định vị phạm vi index theo thứ tự key part. Nếu index đã giới hạn được phạm vi rất hẹp, ICP có thể không đem lại thêm nhiều lợi ích.

Một ví dụ khác:

```sql
KEY idx_people_zip_last_first
    (postal_code, last_name, first_name)
```

```sql
SELECT *
FROM people
WHERE postal_code = '700000'
  AND last_name LIKE '%tran%'
  AND address LIKE '%District 1%';
```

`postal_code` giúp định vị vùng index. Điều kiện `last_name` có thể được đánh giá trên index entry bằng ICP dù không giúp thu hẹp range theo prefix do wildcard đầu chuỗi. `address` không nằm trong index nên cần full row để kiểm tra.

Hãy phân biệt:

| Loại điều kiện | Vai trò |
|---|---|
| Access condition / range condition | Giúp tìm điểm bắt đầu và phạm vi cần duyệt trong index |
| Index condition | Được engine kiểm tra ngay trên index entry nhờ ICP |
| Residual WHERE condition | Còn phải kiểm tra sau khi đọc row hoặc ở tầng server |

Một predicate có thể được dùng để định vị index, được dùng làm ICP, hoặc được giữ lại làm residual condition. Việc phân loại phụ thuộc index, biểu thức, access method và khả năng đánh giá của storage engine.

## 4. ICP hoạt động ở đâu trong kiến trúc MySQL?

Optimizer nằm ở tầng server quyết định có thể dùng ICP hay không. Server chuyển index condition xuống storage engine thông qua cơ chế handler. Storage engine đọc index entry và đánh giá điều kiện trên các trường có sẵn trong entry.

Với InnoDB:

- Secondary index leaf entry chứa giá trị các cột index cùng primary key của row.
- Khi không dùng ICP, engine có thể phải dùng primary key để truy cập clustered index lấy full row cho mỗi entry cần kiểm tra ở tầng server.
- Khi dùng ICP, engine kiểm tra trước các điều kiện phù hợp trên secondary index entry.
- Chỉ entry vượt qua index condition mới cần truy cập clustered index nếu truy vấn còn cần full row.

Với MyISAM, engine cũng có thể dùng ICP để tránh đọc row từ vị trí dữ liệu khi index condition không đạt.

ICP là tối ưu hóa giữa server và storage engine. Nó không thay đổi kết quả logic của SQL; nó thay đổi thời điểm và nơi đánh giá một phần điều kiện để giảm I/O.

## 5. Điều kiện để MySQL có thể sử dụng ICP

ICP chỉ có thể áp dụng khi các yếu tố phù hợp:

1. Truy vấn có đường truy cập qua index mà MySQL hỗ trợ cho ICP.
2. Một phần điều kiện có thể đánh giá chỉ bằng các cột có trong index được chọn.
3. Truy vấn vẫn cần đọc full row hoặc có lợi khi loại index entry trước bước đọc row.
4. Predicate có dạng mà storage engine có thể đánh giá.
5. Tùy loại bảng và index, không vướng các giới hạn của engine hoặc biểu thức.

Các access method thường có thể dùng ICP gồm `range`, `ref`, `eq_ref` và `ref_or_null`. ICP không phải cơ chế áp dụng cho full table scan.

### 5.1. InnoDB chỉ dùng ICP trên secondary index

Trong InnoDB, clustered index leaf page đã chứa dữ liệu đầy đủ của row. Nếu truy cập qua clustered index, việc đọc index entry cũng đã đưa đến full row; không có bước lookup row riêng để ICP tránh được.

Vì vậy, ICP có ý nghĩa với secondary index của InnoDB. Khi truy vấn dùng primary key/clustered index, optimizer thường không có lợi ích ICP theo cơ chế tránh lookup full row.

### 5.2. Query được covering index có thể không cần ICP

Nếu tất cả cột cần cho điều kiện và kết quả đều nằm trong index, storage engine có thể trả kết quả chỉ từ index. Khi đó không cần đọc full row, nên ICP thường không mang lại lợi ích bổ sung.

Ví dụ:

```sql
SELECT region_code, status, last_name
FROM customers
WHERE region_code = 'VN'
  AND status = 'ACTIVE'
  AND last_name LIKE '%nguyen%';
```

Với index `(region_code, status, last_name)`, truy vấn này có thể được bao phủ hoàn toàn bởi index. `Using index` thường cho biết truy vấn dùng covering index. Đây là trường hợp khác với `Using index condition`.

### 5.3. Biểu thức không thể push xuống engine

Một điều kiện không thể push nếu storage engine không thể đánh giá nó từ index entry hoặc biểu thức không được hỗ trợ cho ICP. Các trường hợp thường gặp:

- Điều kiện tham chiếu cột không có trong index.
- Điều kiện cần kết quả của subquery.
- Điều kiện phụ thuộc stored function hoặc biểu thức cần xử lý ở tầng server.
- Truy vấn không dùng access method/index phù hợp.
- Truy vấn đã được covering index phục vụ hoàn toàn nên không còn full-row lookup để tiết kiệm.
- InnoDB không hỗ trợ ICP cho secondary index trên virtual generated column.

Không nên cố viết lại mọi predicate để ép ICP. Hãy ưu tiên ngữ nghĩa đúng, index phù hợp và kiểm tra kế hoạch thực thi.

## 6. Nhận biết ICP bằng EXPLAIN

Cách cơ bản:

```sql
EXPLAIN
SELECT
    id,
    first_name,
    profile_text
FROM customers
WHERE region_code = 'VN'
  AND status = 'ACTIVE'
  AND last_name LIKE '%nguyen%'
  AND profile_text LIKE '%architect%';
```

Trong output dạng tabular, cột `Extra` có thể chứa:

```text
Using index condition
```

Đây là dấu hiệu MySQL đang dùng Index Condition Pushdown cho truy vấn.

Output cũng có thể đồng thời chứa `Using where`. Điều này không mâu thuẫn:

- `Using index condition` cho biết có predicate được kiểm tra tại storage engine trên index entry.
- `Using where` cho biết còn điều kiện lọc ở tầng server sau khi lấy row hoặc sau các bước truy cập.

Không thấy `Using index condition` nghĩa là truy vấn hiện tại không dùng ICP. Nguyên nhân có thể là optimizer không chọn index phù hợp, không có predicate đủ điều kiện pushdown, access method không hỗ trợ hoặc query đã được covering index phục vụ.

### 6.1. EXPLAIN FORMAT=JSON

Có thể xem kế hoạch dạng JSON:

```sql
EXPLAIN FORMAT=JSON
SELECT
    id,
    first_name,
    profile_text
FROM customers
WHERE region_code = 'VN'
  AND status = 'ACTIVE'
  AND last_name LIKE '%nguyen%'
  AND profile_text LIKE '%architect%';
```

Tùy phiên bản và cấu trúc kế hoạch, JSON có thể thể hiện phần điều kiện index trong thuộc tính như `index_condition`, cùng với `attached_condition` hoặc thông tin lọc liên quan. Đọc cả `access_type`, `key`, `used_key_parts` và điều kiện được gắn với table access để hiểu vai trò từng predicate.

Không nên dựa vào một trường JSON riêng lẻ để kết luận toàn bộ query đã được pushdown. Đối chiếu với index được chọn và kết quả dạng tabular.

### 6.2. EXPLAIN FORMAT=TREE và EXPLAIN ANALYZE

MySQL 8.0 hỗ trợ:

```sql
EXPLAIN FORMAT=TREE
SELECT
    id,
    first_name,
    profile_text
FROM customers
WHERE region_code = 'VN'
  AND status = 'ACTIVE'
  AND last_name LIKE '%nguyen%'
  AND profile_text LIKE '%architect%';
```

Từ MySQL 8.0.18, `EXPLAIN ANALYZE` thực thi câu SELECT và cung cấp số hàng/thời gian thực tế của các iterator:

```sql
EXPLAIN ANALYZE
SELECT
    id,
    first_name,
    profile_text
FROM customers
WHERE region_code = 'VN'
  AND status = 'ACTIVE'
  AND last_name LIKE '%nguyen%'
  AND profile_text LIKE '%architect%';
```

EXPLAIN ANALYZE thực sự chạy truy vấn. Chỉ dùng với câu SELECT có thể thực thi an toàn và dữ liệu phù hợp. Số hàng thực tế giúp so sánh ước lượng với kết quả, nhưng không phải mọi kế hoạch đều hiển thị một bộ đếm trực tiếp cho số full-row lookup đã được ICP tránh. Hãy kết hợp kế hoạch, thời gian chạy và benchmark trên dữ liệu đại diện.

## 7. Phân biệt Using index condition, Using index và Using where

Ba thông tin này thường bị nhầm lẫn:

| Extra | Ý nghĩa | Có cần đọc full row không? |
|---|---|---|
| `Using index condition` | ICP kiểm tra predicate trên index entry trước row lookup | Có thể vẫn cần, nếu SELECT hoặc residual condition cần cột ngoài index |
| `Using index` | Covering index: truy vấn có thể lấy các cột cần thiết từ index | Thường không cần lookup full row |
| `Using where` | Có điều kiện lọc còn được thực hiện ở tầng server | Tùy index và cột được truy cập |

Các giá trị có thể xuất hiện cùng nhau. Ví dụ `Using index condition; Using where` có nghĩa một phần predicate được push xuống engine, phần còn lại vẫn lọc ở tầng server.

### 7.1. Minh họa ba trường hợp

**Trường hợp A — Không có ICP, không covering**

Index giúp tìm một phạm vi entry. Server cần đọc row rồi mới kiểm tra điều kiện trên cột index còn lại hoặc cột không có trong index. Nhiều full-row lookup có thể xảy ra.

**Trường hợp B — Có ICP**

Engine kiểm tra điều kiện có thể đánh giá từ index entry. Chỉ các entry vượt qua mới cần đọc full row để lấy cột SELECT hoặc kiểm tra residual condition.

**Trường hợp C — Covering index**

Mọi cột cần thiết đều nằm trong index. Engine có thể trả dữ liệu từ index mà không cần lookup full row. Lúc này lợi ích đến từ covering index, không phải việc giảm row lookup bằng ICP.

## 8. ICP không làm giảm mọi loại công việc

ICP giảm số lần truy cập full row cho những index entry bị loại bởi index condition. Nó không nhất thiết giảm:

- Số index entry phải duyệt trong phạm vi truy cập.
- Chi phí đọc các leaf page của index.
- Chi phí kiểm tra predicate còn lại trên full row.
- Chi phí sort, group hoặc join sau bước truy cập bảng.
- Số hàng cuối cùng cần trả về.

Ví dụ `LIKE '%nguyen%'` không có wildcard prefix phù hợp để tìm range theo nội dung họ. MySQL vẫn có thể phải duyệt mọi entry thuộc vùng `region_code/status`, sau đó ICP mới loại các entry không khớp họ. Vì vậy, ICP giảm full-row lookup nhưng không biến tìm kiếm substring thành một index range scan hẹp.

Nếu phần lớn index entry đều vượt qua ICP, lợi ích có thể nhỏ. Nếu rất ít entry vượt qua, số full-row lookup tránh được có thể đáng kể.

## 9. Thiết kế composite index để ICP có cơ hội phát huy

Index ghép cần được thiết kế theo mẫu truy vấn thực tế:

1. Đưa các cột equality có tính chọn lọc phù hợp lên đầu index.
2. Cân nhắc cột range hoặc cột dùng để sắp xếp tiếp theo.
3. Đưa cột có thể dùng làm ICP vào index nếu lợi ích lọc trước row lookup đủ lớn.
4. Cân nhắc cột cần SELECT nếu muốn tạo covering index, nhưng tránh làm index quá rộng.

Ví dụ:

```sql
KEY idx_orders_customer_status_created
    (customer_id, status, created_at)
```

Truy vấn:

```sql
SELECT id, total_amount
FROM orders
WHERE customer_id = 120
  AND status = 'PAID'
  AND created_at >= '2026-01-01';
```

Index có thể định vị theo `customer_id`, `status` và phạm vi `created_at`. Nếu `total_amount` không nằm trong index, InnoDB có thể cần lookup clustered row cho các entry phù hợp.

Nếu có thêm điều kiện trên một cột index khác mà không thể dùng để thu hẹp range, ICP có thể lọc nó trước lookup. Tuy nhiên, thêm cột vào index làm tăng dung lượng, chi phí INSERT/UPDATE/DELETE và buffer pool footprint. Chỉ tạo index dựa trên workload, độ chọn lọc và benchmark.

### 9.1. Thứ tự cột và leftmost prefix

Với index:

```sql
KEY idx_a_b_c (a, b, c)
```

MySQL tổ chức index theo thứ tự `(a, b, c)`. Predicate trên `a` có thể định vị prefix; predicate trên `b` hữu ích khi phạm vi `a` phù hợp; predicate trên `c` có thể dùng cho range hoặc ICP tùy phần prefix và access method.

ICP không xóa bỏ quy tắc leftmost prefix. Nếu truy vấn không có điều kiện phù hợp trên cột đầu, optimizer có thể không dùng index theo cách mong đợi. ICP chỉ tối ưu bước lọc các entry sau khi đã chọn một đường truy cập index.

### 9.2. Index rộng không phải lúc nào cũng tốt

Thêm nhiều cột vào index có thể:

- Làm index lớn và tốn buffer pool.
- Tăng chi phí ghi và bảo trì index.
- Làm page fan-out giảm, tăng số page phải đọc.
- Tăng thời gian build index và tác động DDL.
- Tạo index gần như trùng lặp với index hiện có.

Đôi khi một index nhỏ định vị phạm vi tốt hơn và ICP lọc phần còn lại là đủ. Trong trường hợp khác, covering index đem lại lợi ích lớn hơn. Phải đo trên dữ liệu có phân bố gần production.

## 10. Bật/tắt ICP để kiểm chứng

ICP được điều khiển bằng optimizer switch `index_condition_pushdown`. Có thể xem trạng thái:

```sql
SELECT @@SESSION.optimizer_switch;
```

Thử tắt trong session hiện tại:

```sql
SET SESSION optimizer_switch = 'index_condition_pushdown=off';
```

Sau đó chạy lại EXPLAIN cho cùng truy vấn. Bật lại:

```sql
SET SESSION optimizer_switch = 'index_condition_pushdown=on';
```

Chỉ thay đổi session để thử nghiệm, tránh đổi GLOBAL trên production chỉ nhằm kiểm tra một query. Khi so sánh, giữ nguyên dữ liệu, tham số, isolation level và trạng thái cache càng nhiều càng tốt; chạy lặp lại nhiều lần để tránh kết luận từ một lần đo nhiễu.

Nếu tắt ICP mà kế hoạch không thay đổi hoặc thời gian gần như không đổi, có thể query không được hưởng lợi đáng kể, index condition không chọn lọc hoặc chi phí nằm ở phần khác.

## 11. Những predicate thường không push được

Một điều kiện chỉ có thể push nếu engine có đủ dữ liệu và khả năng đánh giá. Các ví dụ sau thường phải giữ ở tầng server:

```sql
-- profile_text không nằm trong index.
WHERE profile_text LIKE '%architect%'
```

```sql
-- Điều kiện có subquery.
WHERE last_name = (
    SELECT preferred_last_name
    FROM user_preferences
    WHERE user_id = 10
)
```

```sql
-- Điều kiện gọi stored function.
WHERE normalize_name(last_name) = 'nguyen'
```

Ngay cả khi `last_name` có trong index, biểu thức gọi function có thể không được storage engine đánh giá bằng ICP. Ngoài ra, việc bọc cột index trong function cũng có thể làm giảm khả năng dùng index để định vị range.

Không nên suy luận rằng “cột nằm trong index thì mọi phép tính trên cột đều được push”. Predicate phải nằm trong tập biểu thức mà optimizer/storage engine hỗ trợ.

## 12. ICP và các kỹ thuật tối ưu khác

| Kỹ thuật | Tác dụng chính | Khác biệt với ICP |
|---|---|---|
| Composite index | Tạo đường truy cập theo nhiều cột | Là cấu trúc index; ICP là cách lọc entry khi đã dùng index |
| Covering index | Trả kết quả chỉ từ index | Tránh full-row lookup hoàn toàn khi mọi cột cần thiết đều có trong index |
| Index range scan | Chỉ duyệt một phạm vi index | Thu hẹp entry cần duyệt |
| Index Condition Pushdown | Lọc entry bằng predicate trên cột index trước row lookup | Giảm full-row lookup trong phạm vi đã duyệt |
| Multi-Range Read (MRR) | Tổ chức row lookup theo thứ tự/nhóm để cải thiện I/O | Tối ưu cách lấy row, không phải cùng cơ chế lọc predicate |
| Partition pruning | Loại partition không cần truy cập | Giảm phạm vi dữ liệu ở cấp partition |

Các kỹ thuật có thể phối hợp trong cùng kế hoạch. Ví dụ partition pruning giảm số partition, range scan tìm vùng index, ICP lọc entry, rồi MRR tối ưu việc lấy các row còn lại.

## 13. ICP trong JOIN

ICP cũng có thể có ích khi bảng được truy cập qua index trong kế hoạch JOIN. Ví dụ bảng orders nối với customers:

```sql
SELECT
    o.id,
    o.customer_id,
    o.created_at,
    o.total_amount
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.id
WHERE c.region_code = 'VN'
  AND o.status = 'PAID'
  AND o.note LIKE '%priority%';
```

Nếu index của `orders` có `(customer_id, status, note)` và `note` phù hợp với điều kiện được push, engine có thể lọc index entry trước khi đọc full row. Khả năng thực tế phụ thuộc join order, access method, kiểu index và predicate.

Không phải cứ điều kiện trong ON là được push hoặc cứ điều kiện trong WHERE là không được push. Optimizer phân tích biểu thức sau khi áp dụng các quy tắc biến đổi và chọn kế hoạch. Hãy xem EXPLAIN trên truy vấn hoàn chỉnh.

## 14. Đánh giá lợi ích ICP bằng dữ liệu thực tế

Một quy trình kiểm tra:

1. Chọn truy vấn chậm có dùng secondary index và cần full row.
2. Đọc EXPLAIN, xác định index, access type và `Using index condition`.
3. Xác định predicate nào được push và predicate nào còn residual.
4. Xem phân bố dữ liệu: bao nhiêu entry vượt qua điều kiện index?
5. Chạy EXPLAIN ANALYZE để quan sát rows/timing thực tế.
6. So sánh khi bật/tắt ICP trong session thử nghiệm.
7. Đo nhiều lần với cùng tham số và workload đại diện.
8. Kiểm tra ảnh hưởng của index bổ sung đến ghi và dung lượng.

Không chỉ so sánh thời gian một lần. Cache nóng/lạnh, concurrency, buffer pool, I/O và phân bố tham số có thể làm kết quả khác nhau. Query tối ưu cho một giá trị tham số có thể không tối ưu cho giá trị khác.

### 14.1. Ví dụ tư duy định lượng

Giả sử index scan phải duyệt 100.000 entry trong vùng khách hàng hoạt động:

| Giai đoạn | Không có ICP | Có ICP |
|---|---:|---:|
| Index entry được duyệt | 100.000 | 100.000 |
| Entry đạt điều kiện họ | 100.000 cần lookup trước khi lọc | 2.000 |
| Full row lookup ước tính | 100.000 | 2.000 |
| Kiểm tra profile_text | 100.000 row | 2.000 row |

Các con số chỉ minh họa. Thực tế phụ thuộc predicate, index, engine, optimizer và dữ liệu. Điểm cốt lõi là ICP có thể giữ nguyên số index entry được duyệt nhưng giảm số lần phải lấy full row.

## 15. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
|---|---|
| ICP giúp MySQL bỏ qua toàn bộ index entry không liên quan | ICP kiểm tra điều kiện trên entry đã được duyệt; nó không nhất thiết thu hẹp range scan |
| Cột có trong index thì mọi predicate trên nó đều push được | Predicate còn phải được optimizer và storage engine hỗ trợ |
| `Using index condition` nghĩa là covering index | Nó báo ICP; truy vấn vẫn có thể cần đọc full row |
| `Using index` và `Using index condition` giống nhau | `Using index` thường biểu thị covering index; ICP lọc entry trước row lookup |
| ICP loại bỏ mọi residual WHERE | Điều kiện trên cột ngoài index vẫn cần kiểm tra ở tầng server |
| ICP luôn làm query nhanh hơn | Nếu điều kiện ít chọn lọc hoặc chi phí khác chi phối, lợi ích có thể nhỏ |
| ICP thay thế composite index | ICP bổ trợ cho đường truy cập index, không thay thế cấu trúc index phù hợp |
| InnoDB dùng ICP như nhau trên mọi index | ICP hữu ích trên secondary index; clustered index đã chứa full row |
| Tắt ICP toàn server là cách sửa query | Nên kiểm tra trong session và tối ưu theo kế hoạch cụ thể |

## 16. Checklist khi phân tích Index Condition Pushdown

- Query đang dùng access method nào: range, ref, eq_ref hay ref_or_null?
- Index được chọn có phải secondary index của InnoDB không?
- Những cột nào có trong index và thứ tự key part ra sao?
- Predicate nào dùng để định vị range?
- Predicate nào có thể kiểm tra chỉ bằng index entry?
- Predicate nào cần full row hoặc phải xử lý ở tầng server?
- EXPLAIN có hiển thị `Using index condition` không?
- Có `Using where` cùng lúc không và nó đại diện cho phần lọc nào?
- Query có thực sự cần full row hay có thể trở thành covering index?
- Điều kiện ICP có đủ chọn lọc để giảm row lookup không?
- EXPLAIN ANALYZE có cho thấy số hàng/thời gian phù hợp kỳ vọng không?
- Benchmark bật/tắt ICP có được thực hiện trong cùng điều kiện không?
- Index bổ sung có làm tăng đáng kể write cost và storage không?

## Kết luận

Index Condition Pushdown cho phép storage engine kiểm tra các predicate có thể đánh giá từ index entry trước khi đọc full row. Với InnoDB, lợi ích chủ yếu xuất hiện khi truy cập secondary index và truy vấn vẫn cần cột ngoài index. `Using index condition` là dấu hiệu ICP; `Using index` thường biểu thị covering index; `Using where` cho biết còn điều kiện lọc ở tầng server. ICP có thể giảm full-row lookup nhưng không nhất thiết giảm số index entry phải duyệt hoặc thay thế residual filter. Hãy thiết kế composite index theo mẫu truy vấn, phân biệt access condition với index condition, đọc EXPLAIN và đo trên dữ liệu đại diện trước khi kết luận hiệu năng.
