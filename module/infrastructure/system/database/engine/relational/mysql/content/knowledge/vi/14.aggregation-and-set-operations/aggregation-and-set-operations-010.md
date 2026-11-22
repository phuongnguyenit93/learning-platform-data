# INTERSECT, EXCEPT và điều kiện hỗ trợ theo phiên bản

`INTERSECT` và `EXCEPT` là hai phép toán tập hợp dùng để so sánh kết quả của hai truy vấn `SELECT`. `INTERSECT` trả về những hàng xuất hiện ở cả hai kết quả; `EXCEPT` trả về những hàng có ở kết quả bên trái nhưng không có ở kết quả bên phải. Chúng bổ sung cho `UNION`, vốn kết hợp các hàng từ nhiều truy vấn.

Với MySQL, mốc phiên bản rất quan trọng: **`INTERSECT` và `EXCEPT` được hỗ trợ từ MySQL 8.0.31**. MySQL 8.0.30 trở xuống không hỗ trợ các toán tử này; câu lệnh dùng chúng sẽ gặp lỗi cú pháp. Từ 8.0.31, có thể chọn `DISTINCT` hoặc `ALL` để điều khiển việc loại bỏ hay giữ số lần xuất hiện của hàng. Cần kiểm tra phiên bản của mọi môi trường trước khi đưa truy vấn vào ứng dụng.

## 1. Phép toán tập hợp trong SQL

Các phép toán tập hợp làm việc trên kết quả của nhiều truy vấn có cấu trúc tương thích:

| Toán tử | Ý nghĩa | Hàng được trả về |
| --- | --- | --- |
| `UNION` | Hợp hai tập kết quả | Hàng xuất hiện ở bên trái hoặc bên phải; mặc định loại trùng |
| `UNION ALL` | Hợp và giữ số lần xuất hiện | Tất cả hàng từ hai phía, kể cả trùng lặp |
| `INTERSECT` | Giao hai tập kết quả | Hàng xuất hiện ở cả hai phía |
| `EXCEPT` | Hiệu hai tập kết quả | Hàng xuất hiện bên trái nhưng không xuất hiện bên phải |

Ví dụ về mục tiêu nghiệp vụ:

- `UNION`: danh sách khách hàng có đơn hàng hoặc có phiếu hỗ trợ.
- `INTERSECT`: khách hàng vừa có đơn hàng đã thanh toán vừa có phiếu hỗ trợ ưu tiên cao.
- `EXCEPT`: khách hàng có đơn hàng đã thanh toán nhưng chưa có phiếu hỗ trợ ưu tiên cao.

Các toán tử so sánh toàn bộ các cột được chọn theo vị trí tương ứng. Chúng không tự tìm khóa nối giữa hai bảng như `JOIN`.

## 2. Điều kiện hỗ trợ theo phiên bản MySQL

`INTERSECT` và `EXCEPT` được bổ sung trong MySQL 8.0.31. Có thể dùng trên MySQL 8.0.31 trở lên, bao gồm dòng MySQL 8.4. Trên MySQL 8.0.30 và cũ hơn, cú pháp này chưa được hỗ trợ.

Kiểm tra phiên bản:

```sql
SELECT VERSION() AS mysql_version;
```

Nếu ứng dụng phải chạy trên nhiều môi trường, hãy kiểm tra phiên bản của tất cả server có thể thực thi truy vấn, gồm primary, replica có thể được promote, môi trường staging và job ETL. Không dựa vào phiên bản của máy phát triển để kết luận production có hỗ trợ.

Ví dụ cú pháp sau chỉ chạy trên MySQL 8.0.31 trở lên:

```sql
SELECT customer_id
FROM paid_orders
INTERSECT
SELECT customer_id
FROM priority_tickets;
```

Trên phiên bản cũ hơn, MySQL báo lỗi cú pháp tại toán tử `INTERSECT`. Tương tự, `EXCEPT` cũng không được nhận diện như một phép toán tập hợp.

## 3. INTERSECT: lấy phần giao của hai kết quả

`INTERSECT` trả về những hàng có mặt trong cả truy vấn bên trái và bên phải.

Ví dụ tìm khách hàng vừa có đơn hàng đã thanh toán vừa có phiếu hỗ trợ ưu tiên cao:

```sql
SELECT customer_id
FROM orders
WHERE status = 'paid'

INTERSECT

SELECT customer_id
FROM support_tickets
WHERE priority = 'high'
ORDER BY customer_id;
```

Kết quả chỉ gồm các `customer_id` thỏa cả hai điều kiện. Với dạng mặc định, kết quả loại bỏ các giá trị trùng lặp.

`INTERSECT` không yêu cầu hai truy vấn đọc cùng bảng. Hai phía có thể lấy dữ liệu từ bảng, view hoặc các biểu thức truy vấn khác, miễn số cột và kiểu dữ liệu tương ứng tương thích.

### 3.1. INTERSECT so sánh toàn bộ hàng

Nếu chọn nhiều cột, MySQL so sánh cả hàng theo thứ tự cột:

```sql
SELECT customer_id, region_code
FROM current_customers

INTERSECT

SELECT customer_id, region_code
FROM eligible_customers;
```

Một hàng chỉ xuất hiện trong kết quả nếu cả `customer_id` và `region_code` cùng khớp với một hàng bên phải. Nếu chỉ muốn giao theo `customer_id`, hãy chỉ chọn cột đó ở cả hai phía.

Tên cột trong kết quả được lấy từ truy vấn `SELECT` đầu tiên. Vì vậy, nên đặt alias có ý nghĩa ở phía đầu tiên nếu kết quả sẽ được dùng tiếp trong ứng dụng hoặc truy vấn lồng nhau.

## 4. EXCEPT: lấy hàng chỉ có ở truy vấn bên trái

`EXCEPT` trả về hàng có trong kết quả bên trái nhưng không có trong kết quả bên phải. Thứ tự hai toán hạng có ý nghĩa; đổi chỗ hai truy vấn có thể làm thay đổi hoàn toàn kết quả.

Ví dụ tìm khách hàng có đơn hàng đã thanh toán nhưng chưa có phiếu hỗ trợ ưu tiên cao:

```sql
SELECT customer_id
FROM orders
WHERE status = 'paid'

EXCEPT

SELECT customer_id
FROM support_tickets
WHERE priority = 'high'
ORDER BY customer_id;
```

Kết quả là phần chênh lệch theo hướng `orders` trừ `support_tickets`. `EXCEPT` không có nghĩa là “khác nhau ở bất kỳ cột nào”; nó loại các hàng bên trái nếu có hàng tương ứng ở bên phải.

Ví dụ đổi thứ tự:

```sql
SELECT customer_id
FROM support_tickets
WHERE priority = 'high'

EXCEPT

SELECT customer_id
FROM orders
WHERE status = 'paid';
```

Truy vấn thứ hai tìm khách hàng có phiếu ưu tiên cao nhưng không có đơn hàng đã thanh toán. Đây là tập hợp khác với ví dụ trước.

## 5. DISTINCT và ALL: xử lý hàng trùng lặp

Trong MySQL, `DISTINCT` là mặc định của `INTERSECT` và `EXCEPT`. Có thể viết rõ:

```sql
SELECT customer_id FROM orders
INTERSECT DISTINCT
SELECT customer_id FROM support_tickets;
```

Hoặc dùng `ALL` để giữ số lần xuất hiện theo ngữ nghĩa đa tập (multiset/bag):

```sql
SELECT customer_id FROM orders
INTERSECT ALL
SELECT customer_id FROM support_tickets;
```

Khác biệt:

- `INTERSECT DISTINCT`: mỗi hàng chung chỉ xuất hiện một lần.
- `INTERSECT ALL`: số lần xuất hiện của một hàng trong kết quả bằng số nhỏ hơn giữa số lần xuất hiện ở hai phía.
- `EXCEPT DISTINCT`: trả mỗi hàng bên trái một lần nếu hàng đó không xuất hiện ở bên phải.
- `EXCEPT ALL`: số lần xuất hiện còn lại bằng số lần ở bên trái trừ số lần ở bên phải, nhưng không nhỏ hơn 0.

`ALL` quan trọng khi đầu vào có thể chứa nhiều hàng giống nhau, chẳng hạn log, sự kiện hoặc dữ liệu giao dịch chưa được khử trùng.

## 6. Ví dụ đếm số lần xuất hiện với INTERSECT ALL và EXCEPT ALL

Dùng các truy vấn literal để nhìn rõ số lần xuất hiện:

```sql
(
    SELECT 1 AS item_id
    UNION ALL SELECT 1
    UNION ALL SELECT 1
    UNION ALL SELECT 2
)
INTERSECT ALL
(
    SELECT 1 AS item_id
    UNION ALL SELECT 1
    UNION ALL SELECT 3
)
ORDER BY item_id;
```

Giá trị `1` xuất hiện ba lần ở bên trái và hai lần ở bên phải, nên kết quả có hai hàng `1`. Giá trị `2` và `3` không xuất hiện ở cả hai phía nên không được trả về.

Với `EXCEPT ALL`:

```sql
(
    SELECT 1 AS item_id
    UNION ALL SELECT 1
    UNION ALL SELECT 1
    UNION ALL SELECT 2
)
EXCEPT ALL
(
    SELECT 1 AS item_id
    UNION ALL SELECT 1
    UNION ALL SELECT 3
)
ORDER BY item_id;
```

Bên trái có ba hàng `1`, bên phải có hai hàng `1`, nên kết quả còn một hàng `1`. Hàng `2` chỉ có bên trái nên cũng được giữ lại. Hàng `3` chỉ có bên phải không được thêm vào kết quả.

Khi dùng `DISTINCT` hoặc bỏ qua từ khóa, kết quả sẽ loại trùng. Đừng chọn `ALL` hay `DISTINCT` chỉ theo thói quen; hãy xác định dữ liệu đầu vào là tập giá trị hay đa tập có số lần xuất hiện mang ý nghĩa.

## 7. Điều kiện cấu trúc của hai truy vấn

Hai phía của `INTERSECT` hoặc `EXCEPT` phải trả về cùng số lượng cột. Các cột tương ứng cần có kiểu dữ liệu có thể kết hợp/so sánh được.

Ví dụ hợp lệ về số lượng cột:

```sql
SELECT customer_id, region_code
FROM current_customers
INTERSECT
SELECT customer_id, region_code
FROM archived_customers;
```

Ví dụ sai vì số cột không bằng nhau:

```sql
-- Sai: bên trái trả về hai cột, bên phải chỉ có một
SELECT customer_id, region_code
FROM current_customers
INTERSECT
SELECT customer_id
FROM archived_customers;
```

Tên cột không cần giống nhau; phép toán ghép theo vị trí. Tuy nhiên, nên chọn các cột cùng ý nghĩa nghiệp vụ để tránh so sánh nhầm dữ liệu.

Nếu kiểu dữ liệu khác nhau, MySQL có thể chuyển đổi về kiểu kết quả chung. Để tránh chuyển đổi ngầm bất ngờ, hãy dùng `CAST()` rõ ràng:

```sql
SELECT CAST(customer_code AS CHAR(20)) AS customer_key
FROM legacy_customers

INTERSECT

SELECT CAST(customer_id AS CHAR(20)) AS customer_key
FROM current_customers;
```

Ví dụ trên chỉ hợp lý nếu mã chuỗi và ID số thực sự cùng biểu diễn một miền khóa. Trong thiết kế thật, tốt hơn là chuẩn hóa kiểu dữ liệu từ nguồn hoặc chuyển đổi theo quy tắc được xác định rõ.

## 8. NULL trong phép toán tập hợp

Trong các phép toán tập hợp có xử lý loại trùng, MySQL xem các giá trị `NULL` tương ứng là bằng nhau cho mục đích so sánh hàng. Điều này khác với phép so sánh thông thường bằng `=` trong SQL, vì `NULL = NULL` trả về `UNKNOWN`.

Ví dụ:

```sql
SELECT NULL AS value
INTERSECT
SELECT NULL AS value;
```

Kết quả có một hàng `NULL`, vì hai phía đều chứa cùng một hàng theo quy tắc của phép toán tập hợp.

Ví dụ EXCEPT:

```sql
SELECT NULL AS value
EXCEPT
SELECT NULL AS value;
```

Kết quả rỗng vì hàng `NULL` bên trái cũng có ở bên phải.

Khi thay thế phép toán tập hợp bằng `JOIN`, `EXISTS` hoặc `NOT EXISTS`, cần chú ý khác biệt này. Điều kiện `a.col = b.col` không khớp hai giá trị `NULL`; nếu muốn so sánh null-safe trong MySQL, dùng toán tử `<=>`.

## 9. Collation và quy tắc so sánh chuỗi

Các hàng chuỗi được so sánh theo character set và collation của biểu thức. Với collation không phân biệt hoa/thường, những chuỗi chỉ khác chữ hoa/chữ thường có thể được xem là trùng khi `INTERSECT DISTINCT` hoặc `EXCEPT DISTINCT` loại trùng.

Ví dụ minh họa:

```sql
SELECT _utf8mb4'A' COLLATE utf8mb4_0900_ai_ci AS label
INTERSECT
SELECT _utf8mb4'a' COLLATE utf8mb4_0900_ai_ci AS label;
```

Với collation `utf8mb4_0900_ai_ci` trên MySQL 8.0, so sánh không phân biệt hoa/thường và dấu; hai giá trị có thể được xem là tương đương trong phép toán tập hợp. Nếu nghiệp vụ yêu cầu phân biệt hoa/thường, cần chọn collation phù hợp, ví dụ một collation `_as_cs` có sẵn trên phiên bản.

Khi hai phía dùng collation không tương thích, MySQL có thể báo lỗi hoặc cần quy tắc chuyển đổi rõ ràng. Có thể chỉ định collation tường minh cho cả hai phía, nhưng phải đảm bảo charset tương thích và hiểu tác động đến ngữ nghĩa so sánh.

## 10. Thứ tự ưu tiên khi kết hợp nhiều phép toán

MySQL áp dụng thứ tự ưu tiên sau:

1. `INTERSECT` có độ ưu tiên cao hơn `UNION` và `EXCEPT`.
2. `UNION` và `EXCEPT` có cùng độ ưu tiên; khi không có ngoặc, chúng được kết hợp từ trái sang phải.
3. Dùng ngoặc để thể hiện rõ thứ tự mong muốn và tránh người đọc hiểu nhầm.

Ví dụ:

```sql
SELECT id FROM set_a
UNION
SELECT id FROM set_b
INTERSECT
SELECT id FROM set_c;
```

Do `INTERSECT` có ưu tiên cao hơn, biểu thức tương đương:

```sql
SELECT id FROM set_a
UNION
(
    SELECT id FROM set_b
    INTERSECT
    SELECT id FROM set_c
);
```

Nếu muốn lấy hợp của A và B trước, rồi trừ C, hãy viết rõ:

```sql
(
    SELECT id FROM set_a
    UNION
    SELECT id FROM set_b
)
EXCEPT
SELECT id FROM set_c;
```

Không dựa vào trí nhớ khi biểu thức có từ ba toán tử trở lên. Dùng ngoặc và định dạng truy vấn để thể hiện chính xác thứ tự kết hợp.

## 11. ORDER BY và LIMIT với kết quả tập hợp

`ORDER BY` và `LIMIT` ở cuối biểu thức áp dụng cho kết quả tập hợp cuối cùng:

```sql
SELECT customer_id FROM orders
INTERSECT
SELECT customer_id FROM support_tickets
ORDER BY customer_id DESC
LIMIT 20;
```

Truy vấn lấy tối đa 20 ID chung, sắp xếp giảm dần. Không có `ORDER BY` thì thứ tự kết quả không được bảo đảm.

Nếu muốn `ORDER BY` hoặc `LIMIT` áp dụng riêng cho từng toán hạng, đặt query block trong ngoặc:

```sql
(
    SELECT customer_id
    FROM orders
    ORDER BY created_at DESC
    LIMIT 100
)
INTERSECT
(
    SELECT customer_id
    FROM support_tickets
    ORDER BY created_at DESC
    LIMIT 100
)
ORDER BY customer_id;
```

Ở ví dụ này, mỗi phía giới hạn tập đầu vào trước khi tính giao; `ORDER BY customer_id` cuối cùng sắp xếp kết quả giao. Hai ý nghĩa khác nhau cần được phân biệt: giới hạn từng nguồn trước khi giao không tương đương với giao toàn bộ rồi mới giới hạn.

## 12. So sánh với JOIN, EXISTS và NOT EXISTS

`INTERSECT` và `EXCEPT` diễn đạt phép toán tập hợp trên toàn bộ hàng. Trong nhiều trường hợp, có thể viết truy vấn tương đương bằng `EXISTS` hoặc `NOT EXISTS`, đặc biệt khi chỉ so sánh một khóa.

### 12.1. Thay INTERSECT DISTINCT bằng EXISTS

```sql
SELECT DISTINCT o.customer_id
FROM orders AS o
WHERE o.status = 'paid'
  AND EXISTS (
      SELECT 1
      FROM support_tickets AS t
      WHERE t.priority = 'high'
        AND t.customer_id <=> o.customer_id
  );
```

Toán tử `<=>` là so sánh null-safe của MySQL. Nó giúp hai giá trị `NULL` khớp nhau, phù hợp hơn với ngữ nghĩa so sánh hàng của phép toán tập hợp. Nếu `customer_id` được khai báo `NOT NULL`, có thể dùng `=`.

### 12.2. Thay EXCEPT DISTINCT bằng NOT EXISTS

```sql
SELECT DISTINCT o.customer_id
FROM orders AS o
WHERE o.status = 'paid'
  AND NOT EXISTS (
      SELECT 1
      FROM support_tickets AS t
      WHERE t.priority = 'high'
        AND t.customer_id <=> o.customer_id
  );
```

Truy vấn trả về các ID có ở nguồn đơn hàng nhưng không có ở nguồn phiếu hỗ trợ. Dùng `NOT EXISTS` thường an toàn hơn `NOT IN` khi tập bên phải có thể chứa `NULL`, vì `NOT IN` có thể cho kết quả `UNKNOWN` và loại bỏ nhiều hàng ngoài dự kiến.

### 12.3. Vì sao JOIN không luôn tương đương?

Một `INNER JOIN` có thể tạo nhiều hàng khi bên trái hoặc bên phải có khóa trùng. `INTERSECT DISTINCT` loại trùng cả hàng kết quả. Muốn thay thế chính xác, cần hiểu dữ liệu có duplicate hay không và có cần giữ multiplicity hay không.

Các truy vấn `EXISTS` ở trên mô phỏng ngữ nghĩa distinct cho một cột khóa. Chúng không tự mô phỏng `INTERSECT ALL` hoặc `EXCEPT ALL`; muốn giữ số lần xuất hiện phải tính multiplicity ở từng phía và trừ/lấy số nhỏ hơn theo quy tắc ALL.

## 13. Thay thế khi MySQL chưa hỗ trợ INTERSECT/EXCEPT

Với MySQL 8.0.30 trở xuống, hãy viết lại theo mục tiêu nghiệp vụ bằng `EXISTS`/`NOT EXISTS`, `JOIN`, hoặc phép nhóm. Ví dụ tìm ID chung:

```sql
SELECT DISTINCT a.customer_id
FROM paid_orders AS a
WHERE EXISTS (
    SELECT 1
    FROM priority_tickets AS b
    WHERE b.customer_id <=> a.customer_id
);
```

Tìm ID chỉ có bên đơn hàng:

```sql
SELECT DISTINCT a.customer_id
FROM paid_orders AS a
WHERE NOT EXISTS (
    SELECT 1
    FROM priority_tickets AS b
    WHERE b.customer_id <=> a.customer_id
);
```

Hai mẫu này giả định mục tiêu là tập distinct theo `customer_id`. Nếu cần so sánh nhiều cột, phải đưa tất cả cặp cột tương ứng vào điều kiện so sánh null-safe. Nếu cần giữ duplicate theo `ALL`, phải xây dựng logic đếm số lần xuất hiện; `DISTINCT` và `EXISTS` sẽ làm mất thông tin số lượng.

Không nên dùng `NOT IN` một cách máy móc để thay `EXCEPT`, nhất là khi cột có thể nullable. Kiểm tra ngữ nghĩa NULL trước khi chọn cách viết tương đương.

## 14. Hiệu năng và kế hoạch thực thi

`INTERSECT` và `EXCEPT` là cú pháp tập hợp, không bảo đảm nhanh hơn `JOIN`, `EXISTS` hoặc `NOT EXISTS`. MySQL cần so sánh các hàng từ hai phía và có thể cần cấu trúc trung gian để loại trùng hoặc tính toán kết quả.

Hãy kiểm tra truy vấn bằng `EXPLAIN`:

```sql
EXPLAIN
SELECT customer_id
FROM orders
WHERE status = 'paid'
INTERSECT
SELECT customer_id
FROM support_tickets
WHERE priority = 'high';
```

Một số điểm cần xem:

- Index có hỗ trợ điều kiện lọc ở từng phía hay không.
- Số hàng ước tính sau lọc có quá lớn không.
- Có bước materialization, temporary table hoặc loại trùng tốn kém không.
- Kiểu dữ liệu/collation có khiến phải chuyển đổi nhiều hàng không.
- `EXPLAIN ANALYZE` trên phiên bản hỗ trợ cho biết thời gian và số hàng thực tế của các iterator.

Index theo khóa lọc hoặc khóa so sánh có thể giúp giảm số hàng cần xử lý. Ví dụ, nếu thường lọc `orders` theo `status` rồi lấy `customer_id`, có thể đánh giá index `(status, customer_id)`; nếu lọc phiếu theo `priority`, đánh giá `(priority, customer_id)`. Đây chỉ là điểm bắt đầu: cần đo trên phân bố dữ liệu thật và xét các truy vấn khác đang dùng bảng.

## 15. Kiểm tra dữ liệu trước khi dùng phép toán tập hợp

Trước khi viết `INTERSECT` hoặc `EXCEPT`, hãy xác nhận:

1. Hai phía trả về cùng số cột.
2. Các cột cùng vị trí có ý nghĩa tương ứng.
3. Kiểu dữ liệu có thể kết hợp mà không gây chuyển đổi sai.
4. Collation có quy tắc so sánh đúng với nghiệp vụ.
5. Có cần giữ duplicate (`ALL`) hay chỉ cần tập giá trị (`DISTINCT`).
6. `NULL` có ý nghĩa gì và có cần so sánh null-safe khi viết phương án thay thế.
7. Thứ tự kết hợp nhiều phép toán đã được thể hiện bằng ngoặc khi cần.
8. `ORDER BY`/`LIMIT` đang áp dụng cho toàn kết quả hay riêng từng nhánh.
9. Phiên bản MySQL trên mọi môi trường có hỗ trợ cú pháp hay không.

## 16. Những lỗi và hiểu nhầm thường gặp

| Hiểu nhầm / lỗi | Thực tế | Cách xử lý |
| --- | --- | --- |
| MySQL 8.0 nào cũng hỗ trợ INTERSECT và EXCEPT | Chỉ được hỗ trợ từ 8.0.31 | Kiểm tra `VERSION()` trên server đích |
| INTERSECT chỉ so sánh một khóa | Nó so sánh toàn bộ cột được chọn theo vị trí | Chỉ chọn các cột cần đối chiếu |
| EXCEPT không phụ thuộc thứ tự hai phía | `A EXCEPT B` khác `B EXCEPT A` | Xác định rõ tập nguồn và tập cần loại |
| INTERSECT mặc định giữ duplicate | Mặc định là DISTINCT | Dùng `ALL` nếu cần multiplicity |
| INTERSECT ALL trả mọi duplicate của cả hai phía | Số lần xuất hiện là giá trị nhỏ hơn giữa hai phía | Tính multiplicity theo bag semantics |
| EXCEPT ALL giống anti-join DISTINCT | Nó trừ số lần xuất hiện của bên phải khỏi bên trái | Không dùng EXISTS nếu cần giữ duplicate |
| NULL không bao giờ khớp NULL | Set operations xem NULL tương ứng là bằng nhau khi so sánh hàng | Dùng `<=>` trong phương án thay thế |
| UNION, EXCEPT và INTERSECT có cùng precedence | INTERSECT có precedence cao hơn; UNION/EXCEPT cùng mức | Dùng ngoặc để rõ ý định |
| ORDER BY ở nhánh đầu quyết định thứ tự kết quả cuối | ORDER BY cuối áp dụng cho tập hợp; nhánh riêng cần ngoặc | Đặt ORDER BY ở đúng phạm vi |
| NOT IN luôn thay EXCEPT an toàn | NULL trong tập con có thể làm kết quả UNKNOWN | Ưu tiên NOT EXISTS với so sánh phù hợp |

## 17. Bài tập thực hành

1. Kiểm tra `SELECT VERSION()` và xác định server có hỗ trợ `INTERSECT`/`EXCEPT` không.
2. Tạo hai truy vấn `SELECT` có cùng một cột; dùng `INTERSECT` để tìm các giá trị chung.
3. Đổi thứ tự hai phía của `EXCEPT` và giải thích vì sao kết quả thay đổi.
4. Dùng `INTERSECT DISTINCT` và `INTERSECT ALL` trên dữ liệu có duplicate; đếm số hàng của mỗi kết quả.
5. Dùng `EXCEPT DISTINCT` và `EXCEPT ALL` với số lần xuất hiện khác nhau ở hai phía.
6. Thử hai truy vấn có `NULL`; quan sát cách set operation xử lý NULL.
7. Thử chuỗi khác hoa/thường dưới collation `_ai_ci` và `_as_cs`; so sánh kết quả `INTERSECT`.
8. Kết hợp `UNION`, `EXCEPT`, `INTERSECT`; sau đó dùng ngoặc để thay đổi thứ tự đánh giá.
9. Viết lại một truy vấn `INTERSECT DISTINCT` bằng `EXISTS` và một truy vấn `EXCEPT DISTINCT` bằng `NOT EXISTS`.
10. Dùng `EXPLAIN` so sánh kế hoạch của set operation với phương án EXISTS/NOT EXISTS trên dữ liệu đủ lớn.
11. Trên MySQL 8.0.30 hoặc cũ hơn nếu có môi trường lab, thử cú pháp và ghi nhận lỗi; sau đó chạy trên 8.0.31 trở lên.

## 18. Ghi nhớ

`INTERSECT` lấy các hàng có ở cả hai truy vấn; `EXCEPT` lấy hàng có ở bên trái nhưng không có ở bên phải. MySQL hỗ trợ hai toán tử từ phiên bản 8.0.31. Mặc định chúng dùng `DISTINCT`; `ALL` giữ multiplicity, với `INTERSECT ALL` lấy số lần xuất hiện nhỏ hơn giữa hai phía và `EXCEPT ALL` trừ số lần xuất hiện bên phải khỏi bên trái.

Hai truy vấn phải trả về cùng số cột theo đúng vị trí và có kiểu dữ liệu tương thích. Phép toán so sánh toàn bộ hàng, chịu ảnh hưởng của kiểu dữ liệu và collation; `NULL` tương ứng được xem là bằng nhau trong so sánh tập hợp. `INTERSECT` có precedence cao hơn `UNION` và `EXCEPT`; dùng ngoặc khi cần kiểm soát thứ tự. Với MySQL cũ hơn 8.0.31, có thể thay bằng `EXISTS`/`NOT EXISTS` cho ngữ nghĩa distinct, nhưng phải xử lý NULL và duplicate có chủ đích. Luôn kiểm tra phiên bản, dữ liệu, `EXPLAIN` và kết quả thực tế trước khi triển khai.
