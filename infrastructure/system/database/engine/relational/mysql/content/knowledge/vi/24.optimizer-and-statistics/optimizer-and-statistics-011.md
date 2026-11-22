# optimizer_switch, optimizer hint và phạm vi query block

MySQL chọn cách thực thi câu SQL dựa trên thống kê, chi phí ước tính và các quy tắc tối ưu. Khi cần điều tra một kế hoạch chưa phù hợp, DBA có thể điều chỉnh hành vi tối ưu ở cấp session bằng `optimizer_switch`, hoặc dùng **optimizer hint** để tác động có chủ đích lên một câu lệnh. Với câu SQL chứa subquery, derived table, CTE hay nhiều nhánh `UNION`, cần hiểu **query block** để biết hint đang áp dụng ở phần nào.

Bài học thuộc phần **Bộ tối ưu và thống kê** của MySQL. Bạn sẽ đọc và thay đổi một số switch, dùng hint về index và thứ tự join, đặt tên query block, điều khiển merge/materialization, phát hiện hint bị bỏ qua và so sánh kế hoạch bằng `EXPLAIN`. Mọi thay đổi đều cần được kiểm chứng trên workload đại diện trước khi áp dụng rộng.

## 1. Phân biệt ba cơ chế điều khiển optimizer

MySQL có một số cách để tác động đến optimizer. Chúng có phạm vi và mức độ cụ thể khác nhau:

| Cơ chế | Phạm vi | Ví dụ | Mục đích |
| --- | --- | --- | --- |
| `optimizer_switch` | GLOBAL hoặc SESSION | `index_merge=off` | Bật/tắt một nhóm chiến lược tối ưu được hỗ trợ trong phiên bản đang chạy. |
| Optimizer hint | Một câu SQL hoặc query block cụ thể | `/*+ INDEX(o ix_orders_customer) */` | Gợi ý cách truy cập, thứ tự join, merge hoặc chiến lược tối ưu cho câu lệnh. |
| Index hint kiểu SQL | Một table reference trong câu SQL | `USE INDEX (ix_orders_customer)` | Tác động đến tập index optimizer cân nhắc cho table reference đó. |

`optimizer_switch` không phải danh sách kế hoạch cố định. Tắt một switch chỉ loại bỏ hoặc thay đổi một chiến lược; optimizer vẫn có thể chọn một kế hoạch khác dựa trên thống kê và chi phí. Optimizer hint cũng không bảo đảm kế hoạch luôn nhanh hơn: hint có thể bị bỏ qua nếu không hợp lệ, không áp dụng được hoặc xung đột với cấu trúc câu truy vấn.

Khi hint và `optimizer_switch` cùng điều khiển một tối ưu hóa, hint cụ thể của câu lệnh thường có độ ưu tiên cao hơn switch. Dù vậy, cần kiểm tra hint có thực sự được nhận và kế hoạch có thay đổi như mong muốn hay không.

## 2. Đọc và thay đổi optimizer_switch

`optimizer_switch` là system variable có phạm vi GLOBAL và SESSION. Giá trị SESSION được dùng khi optimizer lập kế hoạch cho câu lệnh trong session đó. Để xem cấu hình hiện tại:

```sql
SELECT @@GLOBAL.optimizer_switch;
SELECT @@SESSION.optimizer_switch;
```

Hoặc:

```sql
SHOW VARIABLES LIKE 'optimizer_switch';
```

Giá trị là danh sách các cặp `tên_switch=on|off|default`, phân tách bằng dấu phẩy. Danh sách switch thay đổi theo phiên bản MySQL; hãy xem giá trị trên máy chủ thay vì giả định mọi phiên bản có cùng tập switch.

### Thay đổi một switch trong session

Ví dụ tạm tắt `index_merge` để so sánh kế hoạch:

```sql
SET @saved_optimizer_switch = @@SESSION.optimizer_switch;

SET SESSION optimizer_switch = 'index_merge=off';

-- Chạy EXPLAIN cho truy vấn cần kiểm tra tại đây.

SET SESSION optimizer_switch = @saved_optimizer_switch;
```

Khi chỉ chỉ định một switch, các switch khác không được nêu sẽ giữ nguyên giá trị hiện tại. Có thể dùng `default` để đặt một switch về giá trị mặc định của phiên bản:

```sql
SET SESSION optimizer_switch = 'index_merge=default';
```

Nên lưu giá trị cũ và khôi phục ngay sau thí nghiệm. Thay đổi SESSION chỉ ảnh hưởng kết nối hiện tại; nó không tác động đến các session đang chạy khác. Thay đổi GLOBAL ảnh hưởng các kết nối mới hoặc session đọc cấu hình global, có thể tác động diện rộng nên cần quy trình kiểm soát thay đổi.

### Một số switch thường gặp

Tên switch và trạng thái mặc định phụ thuộc phiên bản. Các ví dụ sau là những nhóm thường gặp trong MySQL 8.0:

| Switch | Ảnh hưởng khái quát |
| --- | --- |
| `index_merge` | Cho phép optimizer cân nhắc kết hợp nhiều lần truy cập index của cùng một bảng. |
| `index_merge_union` | Điều khiển chiến lược Index Merge Union. |
| `index_merge_intersection` | Điều khiển chiến lược Index Merge Intersection. |
| `index_merge_sort_union` | Điều khiển biến thể Sort-Union của Index Merge. |
| `mrr` | Cho phép Multi-Range Read trong các trường hợp phù hợp. |
| `mrr_cost_based` | Cho optimizer cân nhắc chi phí khi quyết định dùng MRR. |
| `batched_key_access` | Cho phép chiến lược Batched Key Access trong các điều kiện phù hợp. |
| `derived_merge` | Cho phép merge derived table hoặc view vào query block bên ngoài khi hợp lệ. |
| `semijoin` | Cho phép các phép biến đổi semijoin cho một số subquery. |
| `condition_fanout_filter` | Cho optimizer dùng ước lượng điều kiện lọc để cải thiện ước lượng số dòng truyền qua join. |
| `skip_scan` | Cho phép Index Skip Scan trong những điều kiện phù hợp. |

Không nên tắt nhiều switch cùng lúc rồi kết luận switch nào gây ra thay đổi. Hãy thay đổi từng yếu tố, ghi lại `EXPLAIN`, thời gian chạy và số dòng thực tế, sau đó khôi phục cấu hình.

## 3. Chuẩn bị dữ liệu để thử nghiệm

Các ví dụ sử dụng bảng khách hàng và đơn hàng. Có thể tạo bảng lab riêng trong schema thử nghiệm:

```sql
CREATE TABLE optimizer_lab_customers (
    customer_id BIGINT NOT NULL,
    region_code CHAR(2) NOT NULL,
    customer_name VARCHAR(120) NOT NULL,
    PRIMARY KEY (customer_id),
    KEY ix_region (region_code)
) ENGINE = InnoDB;

CREATE TABLE optimizer_lab_orders (
    order_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY ix_customer_created (customer_id, created_at),
    KEY ix_status_created (status, created_at)
) ENGINE = InnoDB;
```

Để so sánh kế hoạch có ý nghĩa, dữ liệu nên có phân bố đủ đa dạng: nhiều khách hàng ở nhiều vùng, đơn hàng trải trên nhiều trạng thái và thời điểm. Bảng chỉ có vài dòng thường không thể hiện rõ khác biệt giữa các access path.

Sau khi nạp dữ liệu lab, cập nhật thống kê khi cần:

```sql
ANALYZE TABLE optimizer_lab_customers, optimizer_lab_orders;
```

Không chạy lệnh nạp hàng triệu dòng hoặc thay đổi thống kê trên production chỉ để tái tạo ví dụ. Hãy dùng bản sao hoặc môi trường benchmark có dữ liệu gần với workload thật.

## 4. Optimizer hint: cú pháp và nguyên tắc đặt

Optimizer hint của MySQL được viết trong comment đặc biệt `/*+ ... */`. Với `SELECT`, hint thường được đặt ngay sau từ khóa `SELECT`:

```sql
SELECT /*+ MAX_EXECUTION_TIME(1000) */
       order_id, total_amount
FROM optimizer_lab_orders
WHERE customer_id = 1001;
```

`MAX_EXECUTION_TIME(1000)` đặt giới hạn thời gian thực thi truy vấn SELECT tính bằng mili giây trong phạm vi hỗ trợ. Hint này không thay thế timeout ở ứng dụng và không áp dụng cho mọi loại câu lệnh.

Một comment thông thường như `/* ghi chú */` không phải optimizer hint. Hint phải dùng dấu cộng ngay sau `/*`, đặt ở vị trí MySQL quy định và có cú pháp hợp lệ. Với các câu có nhiều query block, hint được gắn với block nơi comment xuất hiện; có thể tham chiếu block khác bằng tên query block.

Một câu lệnh có thể có nhiều hint trong cùng comment:

```sql
SELECT /*+ INDEX(o ix_customer_created) JOIN_ORDER(c, o) */
       c.customer_name, o.order_id, o.created_at
FROM optimizer_lab_customers AS c
JOIN optimizer_lab_orders AS o
  ON o.customer_id = c.customer_id
WHERE c.customer_id = 1001;
```

Trong ví dụ, `INDEX` hướng optimizer đến index được chỉ định cho alias `o`; `JOIN_ORDER` gợi ý thứ tự join của các table reference trong query block. Hai hint điều khiển hai khía cạnh khác nhau của kế hoạch.

## 5. Hint về index và cách truy cập bảng

Một số hint liên quan đến index trong MySQL 8.0:

- `INDEX(table_alias index_name)` gợi ý sử dụng index được nêu.
- `NO_INDEX(table_alias index_name)` loại index được nêu khỏi lựa chọn.
- `JOIN_INDEX`, `GROUP_INDEX` và `ORDER_INDEX` có thể giới hạn index theo mục đích join, group hoặc order trong các phiên bản hỗ trợ.
- `INDEX_MERGE` và `NO_INDEX_MERGE` điều khiển việc cân nhắc Index Merge cho table reference.

Ví dụ:

```sql
EXPLAIN FORMAT = TREE
SELECT /*+ INDEX(o ix_customer_created) */
       o.order_id, o.created_at
FROM optimizer_lab_orders AS o
WHERE o.customer_id = 1001
  AND o.created_at >= '2026-01-01';
```

Để so sánh, thử bỏ hint và xem kế hoạch tự nhiên của optimizer. Nếu hint làm kế hoạch dùng index khác nhưng số page đọc hoặc thời gian thực thi tăng, hãy bỏ hint. Hint index không tạo index mới và không sửa thống kê.

### Optimizer hint và USE/FORCE/IGNORE INDEX

MySQL còn có cú pháp index hint kiểu SQL đặt sau table reference:

```sql
SELECT o.order_id, o.created_at
FROM optimizer_lab_orders AS o
  FORCE INDEX FOR JOIN (ix_customer_created)
WHERE o.customer_id = 1001;
```

`USE INDEX`, `FORCE INDEX` và `IGNORE INDEX` là index hint kiểu SQL; chúng khác comment optimizer hint. Có thể giới hạn mục đích `FOR JOIN`, `FOR ORDER BY` hoặc `FOR GROUP BY`. Tránh áp dụng đồng thời nhiều cơ chế điều khiển index nếu chưa hiểu cách chúng tương tác, vì việc đọc kế hoạch và chẩn đoán trở nên khó hơn.

## 6. Hint điều khiển thứ tự join

Optimizer thường chọn thứ tự join dựa trên ước lượng số dòng và chi phí. Có thể dùng các hint sau trong phiên bản hỗ trợ:

- `JOIN_ORDER(t1, t2, ...)`: gợi ý thứ tự join của các bảng được nêu.
- `JOIN_PREFIX(t1, t2, ...)`: chỉ định phần đầu của thứ tự join.
- `JOIN_SUFFIX(t1, t2, ...)`: chỉ định phần cuối của thứ tự join.
- `JOIN_FIXED_ORDER()`: yêu cầu dùng thứ tự bảng như trong mệnh đề `FROM`.

Ví dụ:

```sql
EXPLAIN FORMAT = TREE
SELECT /*+ JOIN_ORDER(c, o) */
       c.customer_name, o.order_id, o.total_amount
FROM optimizer_lab_customers AS c
JOIN optimizer_lab_orders AS o
  ON o.customer_id = c.customer_id
WHERE c.region_code = 'HN'
  AND o.status = 'PAID';
```

`JOIN_ORDER(c, o)` gợi ý optimizer xử lý `c` trước `o` trong block này. Hint không bảo đảm access method hoặc index cụ thể; optimizer vẫn cần chọn cách truy cập từng bảng. Nếu điều kiện lọc vùng khách hàng trả về phần lớn bảng nhưng trạng thái đơn hàng rất chọn lọc, ép thứ tự có thể làm kế hoạch tệ hơn.

Thứ tự join phụ thuộc dữ liệu thực tế, thống kê, index và điều kiện. Hãy kiểm tra `EXPLAIN ANALYZE` trên truy vấn SELECT an toàn để so sánh actual rows, loops và thời gian từng iterator.

## 7. Query block là gì?

**Query block** là một khối truy vấn SELECT độc lập trong câu SQL. Một câu lệnh có thể chứa nhiều query block:

- SELECT ngoài cùng.
- SELECT bên trong subquery hoặc `EXISTS`.
- SELECT tạo derived table trong `FROM`.
- SELECT bên trong CTE.
- Các nhánh SELECT của `UNION`.

Ví dụ:

```sql
SELECT c.customer_id, c.customer_name
FROM optimizer_lab_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM optimizer_lab_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
```

Truy vấn có ít nhất hai query block: block ngoài đọc `optimizer_lab_customers`, block trong đọc `optimizer_lab_orders`. Hint đặt ngay sau SELECT của block ngoài không tự động áp dụng cho block SELECT bên trong.

### Đặt tên query block bằng QB_NAME

Hint `QB_NAME(name)` đặt tên cho query block chứa hint. Ví dụ:

```sql
SELECT /*+ QB_NAME(customer_list) */
       c.customer_id, c.customer_name
FROM optimizer_lab_customers AS c
WHERE EXISTS (
    SELECT /*+ QB_NAME(paid_order_check) */ 1
    FROM optimizer_lab_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
```

Tên `customer_list` xác định block ngoài; `paid_order_check` xác định block trong. Tên block phải được dùng nhất quán và không nên trùng nhau trong cùng câu lệnh. Nếu không đặt tên, MySQL vẫn có tên mặc định dạng `select#N`, nhưng tên tường minh giúp hint dễ đọc và ít phụ thuộc cấu trúc câu truy vấn hơn.

### Tham chiếu query block khác bằng @name

Khi một hint ở block này cần tác động đến table reference trong block khác, dùng `@query_block_name`. Ví dụ, hint index cho alias `o` trong subquery:

```sql
EXPLAIN FORMAT = TREE
SELECT /*+
          QB_NAME(customer_list)
          INDEX(@paid_order_check o ix_status_created)
       */
       c.customer_id, c.customer_name
FROM optimizer_lab_customers AS c
WHERE EXISTS (
    SELECT /*+ QB_NAME(paid_order_check) */ 1
    FROM optimizer_lab_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
```

`@paid_order_check` chỉ ra query block chứa alias `o`; `ix_status_created` là index được gợi ý cho alias đó. Khi đổi alias hoặc đổi tên query block, phải cập nhật hint tương ứng. Nếu table reference không tồn tại trong block được chỉ định, hint không áp dụng được.

## 8. Hint cho derived table: MERGE và NO_MERGE

Derived table là SELECT xuất hiện trong mệnh đề `FROM`. Khi hợp lệ, optimizer có thể **merge** derived table vào query block bên ngoài để mở rộng cơ hội tối ưu. Trong một số trường hợp, optimizer giữ derived table thành một kết quả trung gian được materialize.

Ví dụ:

```sql
SELECT c.customer_id, d.order_count
FROM optimizer_lab_customers AS c
JOIN (
    SELECT customer_id, COUNT(*) AS order_count
    FROM optimizer_lab_orders
    WHERE status = 'PAID'
    GROUP BY customer_id
) AS d
  ON d.customer_id = c.customer_id;
```

Có thể dùng `MERGE(d)` hoặc `NO_MERGE(d)` để gợi ý cách xử lý derived table `d`:

```sql
EXPLAIN FORMAT = TREE
SELECT /*+ NO_MERGE(d) */
       c.customer_id, d.order_count
FROM optimizer_lab_customers AS c
JOIN (
    SELECT customer_id, COUNT(*) AS order_count
    FROM optimizer_lab_orders
    WHERE status = 'PAID'
    GROUP BY customer_id
) AS d
  ON d.customer_id = c.customer_id;
```

`NO_MERGE(d)` yêu cầu không merge derived table `d` khi hint hợp lệ; optimizer có thể materialize kết quả trung gian. `MERGE(d)` gợi ý merge khi cấu trúc truy vấn cho phép. Một số cấu trúc như aggregate, `GROUP BY`, `DISTINCT`, `LIMIT` hoặc window function có thể ngăn merge theo quy tắc của MySQL; hint không thể làm một biến đổi vốn không hợp lệ trở nên hợp lệ.

Materialization có thể có lợi khi kết quả trung gian nhỏ và được tái sử dụng, nhưng cũng có thể tạo chi phí ghi/đọc tạm. Merge có thể mở rộng khả năng đẩy điều kiện và chọn join order. Không có lựa chọn nào luôn nhanh hơn.

## 9. Hint cho subquery và các tối ưu hóa khác

MySQL có các hint chuyên biệt cho một số chiến lược subquery, semijoin và derived condition pushdown. Tên và phạm vi hỗ trợ tùy phiên bản. Ví dụ nhóm hint `SEMIJOIN`/`NO_SEMIJOIN` điều khiển việc dùng semijoin cho subquery phù hợp; các chiến lược có thể gồm `FIRSTMATCH`, `LOOSESCAN`, `MATERIALIZATION` và `DUPSWEEDOUT`.

Không nên áp dụng hint semijoin chỉ dựa vào tên. Trước hết hãy kiểm tra subquery có được biến đổi thành semijoin hay không trong `EXPLAIN FORMAT=JSON` hoặc `EXPLAIN FORMAT=TREE`. Nếu cấu trúc truy vấn không đủ điều kiện, hint có thể không có tác dụng.

Một số hint khác:

| Hint | Công dụng khái quát |
| --- | --- |
| `MAX_EXECUTION_TIME(ms)` | Giới hạn thời gian cho SELECT trong phạm vi hỗ trợ. |
| `SET_VAR(var_name = value)` | Đặt tạm một system variable được phép cho thời gian thực thi câu lệnh. |
| `DERIVED_CONDITION_PUSHDOWN` / `NO_DERIVED_CONDITION_PUSHDOWN` | Điều khiển việc đẩy điều kiện vào derived table trong trường hợp hỗ trợ. |
| `RESOURCE_GROUP(name)` | Gợi ý resource group cho câu lệnh trong các phiên bản/cấu hình hỗ trợ. |

Ví dụ `SET_VAR`:

```sql
SELECT /*+ SET_VAR(sort_buffer_size = 262144) */
       order_id, created_at
FROM optimizer_lab_orders
ORDER BY created_at;
```

`SET_VAR` chỉ áp dụng cho biến được phép dùng với hint này; biến không hợp lệ hoặc không có phạm vi thích hợp sẽ bị bỏ qua và có thể tạo warning. Không dùng hint để đặt biến hệ thống tùy ý hoặc thay đổi cấu hình lâu dài của server.

## 10. Phát hiện hint bị bỏ qua hoặc xung đột

Một câu SQL có thể chạy thành công dù một optimizer hint bị bỏ qua. Vì vậy, không được xem việc truy vấn không báo lỗi là bằng chứng hint đã được áp dụng.

Kiểm tra kế hoạch:

```sql
EXPLAIN FORMAT = TREE
SELECT /*+ INDEX(o ix_customer_created) */
       o.order_id, o.created_at
FROM optimizer_lab_orders AS o
WHERE o.customer_id = 1001;

SHOW WARNINGS;
```

`SHOW WARNINGS` ngay sau EXPLAIN có thể hiển thị ghi chú về hint không hợp lệ, xung đột hoặc không áp dụng được. Nội dung warning phụ thuộc phiên bản. Đồng thời, đọc plan để xác định index, join order, materialization và các iterator thực sự được chọn.

Các nguyên nhân thường gặp:

- Gõ sai tên hint, tên index, alias hoặc query block.
- Đặt hint trong comment thường thay vì comment `/*+ ... */`.
- Đặt hint ở query block không chứa table reference mà hint nhắm đến.
- Hai hint mâu thuẫn hoặc nhiều hint cùng điều khiển một lựa chọn.
- Cấu trúc truy vấn không cho phép tối ưu hóa được yêu cầu.
- Hint không được hỗ trợ trong phiên bản MySQL đang chạy.
- Table alias đã đổi nhưng hint vẫn tham chiếu tên cũ.

Nếu có nhiều hint chồng lấn, không dựa vào thứ tự viết để đoán kết quả. Hãy bỏ các hint dư thừa, chỉ giữ một mục tiêu rõ ràng và kiểm tra warnings cùng kế hoạch thực thi.

## 11. Đo tác động bằng EXPLAIN và EXPLAIN ANALYZE

Optimizer hint chỉ hữu ích khi cải thiện kết quả có thể đo được. Quy trình so sánh nên gồm:

1. Chạy `EXPLAIN FORMAT=TREE` cho truy vấn gốc.
2. Ghi lại access path, join order, estimated rows, filter và materialization.
3. Thêm một hint duy nhất hoặc thay đổi một switch trong session.
4. Chạy lại EXPLAIN và đọc `SHOW WARNINGS`.
5. Với truy vấn SELECT an toàn, dùng `EXPLAIN ANALYZE` để xem actual rows, loops và thời gian từng iterator.
6. So sánh trên cùng dữ liệu, cùng điều kiện cache và nhiều lần chạy đại diện.
7. Khôi phục switch cũ và bỏ hint nếu lợi ích không ổn định hoặc làm truy vấn khác xấu đi.

Ví dụ:

```sql
EXPLAIN ANALYZE
SELECT /*+ JOIN_ORDER(c, o) */
       c.customer_name, o.order_id, o.total_amount
FROM optimizer_lab_customers AS c
JOIN optimizer_lab_orders AS o
  ON o.customer_id = c.customer_id
WHERE c.region_code = 'HN'
  AND o.status = 'PAID';
```

`EXPLAIN ANALYZE` thực sự thực thi câu truy vấn để đo số liệu thực tế. Chỉ dùng với SELECT phù hợp, giới hạn dữ liệu và môi trường kiểm thử; không dùng tùy tiện cho truy vấn có tác dụng phụ hoặc workload quá nặng.

Ước lượng `rows` khác xa `actual rows` có thể chỉ ra thống kê chưa phù hợp hoặc tương quan giữa các cột mà optimizer chưa mô hình hóa tốt. Hint có thể che triệu chứng trong một câu truy vấn, nhưng cập nhật thống kê, tạo index đúng hoặc viết lại điều kiện có thể giải quyết nguyên nhân rộng hơn.

## 12. Quy tắc sử dụng hint trong môi trường thật

- **Bắt đầu từ plan và số liệu.** Xác định iterator gây tốn thời gian, số dòng ước lượng và số dòng thực tế trước khi thêm hint.
- **Chỉ thay đổi một yếu tố.** Nếu cùng lúc ép index, join order và tắt nhiều switch, sẽ khó biết điều gì tạo ra kết quả.
- **Giới hạn phạm vi.** Ưu tiên optimizer hint trong câu lệnh hoặc query block cụ thể thay vì đổi GLOBAL switch cho toàn server.
- **Dùng alias và query block name rõ ràng.** Khi đổi cấu trúc truy vấn, cập nhật hint và kiểm tra lại phạm vi.
- **Kiểm tra warnings.** Hint bị bỏ qua có thể khiến kế hoạch không thay đổi dù SQL vẫn chạy bình thường.
- **Đo trên dữ liệu đại diện.** Một hint tốt trên tập dữ liệu nhỏ có thể trở thành lựa chọn tệ khi phân bố dữ liệu thay đổi.
- **Theo dõi sau triển khai.** Thống kê, lượng dữ liệu và phiên bản MySQL thay đổi có thể làm hint cũ không còn phù hợp.
- **Ghi lại lý do.** Nêu rõ vấn đề plan, số liệu trước/sau, phiên bản MySQL và điều kiện để gỡ hint.

Hint là công cụ kiểm soát có chủ đích, không thay thế việc thiết kế schema, index, thống kê và SQL hợp lý. Càng nhiều hint cố định, chi phí bảo trì khi dữ liệu hoặc phiên bản thay đổi càng cao.

## 13. Bài tập tự kiểm tra

1. `optimizer_switch` khác optimizer hint ở phạm vi và mục đích như thế nào?
2. Vì sao tắt `index_merge` không đồng nghĩa optimizer sẽ dùng một index cụ thể?
3. Làm thế nào lưu và khôi phục giá trị `@@SESSION.optimizer_switch` trong một thí nghiệm?
4. Query block là gì? Một câu SQL có subquery thường có bao nhiêu block?
5. `QB_NAME(name)` và cú pháp `@name` giải quyết vấn đề gì?
6. Phân biệt `INDEX(alias index_name)` với `FORCE INDEX`.
7. Khi nào `NO_MERGE` có thể làm derived table được materialize, và vì sao điều đó chưa chắc nhanh hơn?
8. Vì sao phải kiểm tra `SHOW WARNINGS` sau EXPLAIN khi dùng optimizer hint?
9. `EXPLAIN ANALYZE` khác `EXPLAIN FORMAT=TREE` ở điểm nào?
10. Hãy thiết kế một phép thử chỉ thay đổi một hint và ghi lại bằng chứng cho thấy kế hoạch tốt hơn.

Khi điều khiển optimizer, hãy theo chuỗi **xác định query block → đặt hint đúng phạm vi → kiểm tra warning → đọc execution plan → đo actual rows và thời gian → đánh giá lại trên workload đại diện**. Chuỗi này giúp hint trở thành một quyết định có bằng chứng và có thể bảo trì.
