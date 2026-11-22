# Giới hạn của việc suy luận tính đúng đắn chỉ từ thứ tự câu lệnh SQL

Khi đọc một đoạn SQL, ta thường nhìn các câu lệnh theo thứ tự từ trên xuống dưới và hình dung cơ sở dữ liệu sẽ thực hiện đúng lần lượt như vậy. Cách đọc này hữu ích để hiểu **ý định của người viết**, nhưng không đủ để chứng minh chương trình đúng trong môi trường có tối ưu hóa truy vấn, transaction đồng thời, isolation level, khóa, trigger và các ràng buộc dữ liệu.

Một hệ quản trị cơ sở dữ liệu (DBMS) xử lý SQL ở nhiều lớp:

- **Ngữ nghĩa SQL:** kết quả mà câu lệnh được phép tạo ra theo ngôn ngữ và DBMS.
- **Bộ tối ưu truy vấn:** chọn kế hoạch thực thi phù hợp, có thể đổi thứ tự join, cách quét bảng hoặc cách áp dụng phép lọc.
- **Bộ thực thi:** chạy kế hoạch trên dữ liệu và tài nguyên hiện tại.
- **Bộ điều phối đồng thời:** phối hợp nhiều statement và transaction đang chạy.
- **Cơ chế transaction và phục hồi:** xác định thay đổi nào được commit, rollback và nhìn thấy ở thời điểm nào.

Vì vậy, **thứ tự văn bản của câu SQL không tự nó chứng minh thứ tự truy cập vật lý, thứ tự hàng kết quả, khả năng quan sát dữ liệu của transaction khác hoặc tính đúng đắn của nghiệp vụ**. Muốn kết luận, phải xét ngữ nghĩa câu lệnh, ranh giới transaction, constraint, isolation level và những tương tác đồng thời có thể xảy ra.

## 1. Bốn loại “thứ tự” cần phân biệt

Cụm từ “thứ tự thực thi SQL” có thể nói đến nhiều điều khác nhau. Trước khi phân tích một tình huống, hãy xác định đang nói về thứ tự nào.

| Loại thứ tự | Nó mô tả điều gì? | Có thể suy ra chỉ từ văn bản SQL? |
|---|---|---|
| **Thứ tự câu lệnh trong script** | Câu nào được gửi trước, câu nào được gửi sau trong cùng luồng ứng dụng | Có, nếu biết ứng dụng thực sự gửi tuần tự trên cùng connection; vẫn phải xét transaction và lỗi |
| **Thứ tự logic theo ngữ nghĩa SQL** | Quan hệ logic giữa FROM, WHERE, GROUP BY, HAVING, SELECT, ORDER BY... | Có thể suy luận theo quy tắc ngôn ngữ, không phải thứ tự vật lý |
| **Thứ tự thực thi vật lý** | DBMS quét index/bảng nào trước, join theo thuật toán nào, chạy song song ra sao | Không; cần execution plan và trạng thái runtime |
| **Thứ tự giữa các transaction** | Các thao tác của nhiều session xen kẽ, chờ hoặc xung đột như thế nào | Không; phụ thuộc lịch điều phối, khóa, isolation và dữ liệu |

Ví dụ:

```sql
SELECT *
FROM orders o
JOIN customers c ON c.id = o.customer_id
WHERE c.status = 'ACTIVE'
ORDER BY o.created_at DESC;
```

Đọc từ trên xuống không có nghĩa DBMS bắt buộc phải đọc hết bảng `orders` rồi mới đọc `customers`, sau đó mới áp dụng điều kiện. Bộ tối ưu có thể chọn index scan, hash join, nested loop hoặc một kế hoạch khác miễn là bảo toàn ngữ nghĩa kết quả được yêu cầu.

Tương tự, nếu một transaction gửi ba câu lệnh tuần tự thì transaction khác vẫn có thể thực thi xen giữa các khoảng thời gian, trừ khi cơ chế cô lập và đồng bộ thực sự ngăn tương tác đó.

## 2. Thứ tự logic trong một câu SELECT không phải thứ tự chạy vật lý

Một câu `SELECT` có cấu trúc quen thuộc:

```sql
SELECT department_id, COUNT(*) AS employee_count
FROM employees
WHERE active = TRUE
GROUP BY department_id
HAVING COUNT(*) >= 5
ORDER BY employee_count DESC;
```

Có thể hiểu ngữ nghĩa của nó theo các bước khái niệm:

1. Xác định nguồn hàng từ `FROM` và các phép `JOIN`.
2. Lọc hàng theo `WHERE`.
3. Gom nhóm theo `GROUP BY`.
4. Lọc nhóm theo `HAVING`.
5. Tạo các biểu thức đầu ra của `SELECT`.
6. Sắp xếp theo `ORDER BY`.

Đây là mô hình để hiểu **ý nghĩa truy vấn**, không phải cam kết DBMS sẽ thực thi vật lý lần lượt từng giai đoạn đúng theo danh sách đó. Bộ tối ưu có thể đẩy điều kiện lọc xuống gần nơi đọc dữ liệu, đổi thứ tự join, dùng index hoặc loại bỏ phép tính không cần thiết.

### 2.1. Query optimizer có thể đổi thứ tự thao tác

Hai truy vấn có join:

```sql
SELECT o.id, c.name
FROM orders o
JOIN customers c ON c.id = o.customer_id
WHERE c.country = 'VN'
  AND o.total_amount > 1000;
```

```sql
SELECT o.id, c.name
FROM customers c
JOIN orders o ON o.customer_id = c.id
WHERE o.total_amount > 1000
  AND c.country = 'VN';
```

Với điều kiện và kiểu join tương đương, hai truy vấn có thể có cùng ngữ nghĩa dù thứ tự viết bảng và điều kiện khác nhau. DBMS có thể chọn thứ tự join dựa trên thống kê, index, kích thước ước lượng và chi phí.

Điều này cũng có nghĩa: **không nên viết SQL với hy vọng một bảng sẽ luôn được quét trước chỉ vì nó đứng đầu trong FROM**. Nếu nghiệp vụ cần kết quả hoặc tác động cụ thể, hãy diễn đạt bằng constraint, điều kiện, biểu thức, transaction hoặc cơ chế khóa có hợp đồng rõ ràng.

### 2.2. Thứ tự phép tính trong một biểu thức cần theo quy tắc ngôn ngữ

Ví dụ:

```sql
SELECT
    price + tax * quantity AS total
FROM order_lines;
```

SQL áp dụng độ ưu tiên toán tử theo quy tắc của DBMS/ngôn ngữ; không được suy luận từ việc các ký hiệu xuất hiện trái sang phải nếu độ ưu tiên khác nhau. Khi biểu thức phức tạp, hãy dùng ngoặc để thể hiện ý định:

```sql
SELECT
    (price + tax) * quantity AS total
FROM order_lines;
```

Cần phân biệt quy tắc ưu tiên của biểu thức với lịch thực thi vật lý. Ngay cả khi ngữ nghĩa biểu thức đã rõ, DBMS vẫn có quyền chọn cách đánh giá tương đương.

### 2.3. Không dựa vào thứ tự đánh giá của điều kiện để tránh lỗi

Không nên giả định DBMS sẽ luôn đánh giá điều kiện bên trái trước, rồi mới đánh giá điều kiện bên phải trong `WHERE` hoặc `AND`/`OR`.

Ví dụ không an toàn:

```sql
SELECT *
FROM measurements
WHERE denominator <> 0
  AND numerator / denominator > 2;
```

Nếu mục đích của điều kiện đầu tiên là bảo vệ phép chia ở điều kiện sau, việc viết điều kiện trước **không nên được xem là một hàng rào đánh giá bắt buộc**. Bộ tối ưu có thể biến đổi biểu thức; quy tắc cụ thể phụ thuộc DBMS.

Hãy viết phép tính an toàn ngay trong biểu thức:

```sql
SELECT *
FROM measurements
WHERE numerator / NULLIF(denominator, 0) > 2;
```

`NULLIF(denominator, 0)` trả về NULL khi mẫu số bằng 0; phép chia không còn chia cho 0. Điều kiện so sánh với NULL không trở thành TRUE, nên hàng đó không được chọn trong `WHERE`.

Một cách khác là dùng `CASE` khi DBMS bảo đảm ngữ nghĩa đánh giá nhánh phù hợp cho biểu thức đó:

```sql
SELECT CASE
         WHEN denominator = 0 THEN NULL
         ELSE numerator / denominator
       END AS ratio
FROM measurements;
```

Lưu ý: không nên khái quát hành vi đánh giá biểu thức của một DBMS thành cam kết giống hệt cho mọi DBMS; cũng không nên đặt biểu thức có lỗi trong một nhánh rồi giả định mọi hệ quản trị đều không đánh giá nó. Hãy ưu tiên hàm an toàn như `NULLIF`, kiểu dữ liệu hợp lệ và các ràng buộc dữ liệu.

## 3. Thứ tự hàng trả về không được bảo đảm nếu thiếu ORDER BY

Một trong những lỗi phổ biến nhất là suy luận kết quả truy vấn sẽ giữ thứ tự chèn, thứ tự khóa chính hoặc thứ tự mà DBMS từng trả về trong một lần chạy trước.

Ví dụ:

```sql
SELECT id, created_at
FROM orders
LIMIT 10;
```

Không có `ORDER BY` thì DBMS **không bảo đảm thứ tự hàng**. Kết quả có thể thay đổi theo execution plan, index, dữ liệu mới, vacuum/maintenance, song song hóa, phiên bản DBMS hoặc các yếu tố khác.

Muốn lấy 10 đơn hàng mới nhất:

```sql
SELECT id, created_at
FROM orders
ORDER BY created_at DESC, id DESC
LIMIT 10;
```

Việc thêm `id` làm tiêu chí phụ giúp thứ tự xác định khi nhiều hàng có cùng thời điểm. Nếu chỉ sắp xếp theo một cột có giá trị trùng, thứ tự giữa các hàng đồng hạng vẫn chưa xác định đầy đủ.

### 3.1. ORDER BY phải tạo thứ tự đủ xác định

Ví dụ:

```sql
SELECT id, score
FROM exam_results
ORDER BY score DESC
LIMIT 5;
```

Nếu nhiều người có cùng `score` tại vị trí thứ năm, tập hàng trả về có thể khác nhau giữa các lần chạy. Nếu nghiệp vụ yêu cầu quy tắc phân xử, hãy bổ sung tiêu chí:

```sql
SELECT id, score
FROM exam_results
ORDER BY score DESC, submitted_at ASC, id ASC
LIMIT 5;
```

Điều quan trọng không phải chỉ “có ORDER BY”, mà là **thứ tự có đầy đủ khóa phân biệt theo yêu cầu nghiệp vụ hay không**.

### 3.2. ORDER BY trong truy vấn con không tự bảo đảm thứ tự cuối cùng

```sql
SELECT *
FROM (
    SELECT id, created_at
    FROM orders
    ORDER BY created_at DESC
) recent_orders;
```

Không nên dựa vào `ORDER BY` của truy vấn con để bảo đảm kết quả ngoài cùng vẫn có cùng thứ tự. Truy vấn ngoài cần khai báo `ORDER BY` của chính nó nếu thứ tự đầu ra là quan trọng.

### 3.3. Thứ tự trong window function khác thứ tự kết quả

```sql
SELECT
    employee_id,
    department_id,
    salary,
    ROW_NUMBER() OVER (
        PARTITION BY department_id
        ORDER BY salary DESC, employee_id
    ) AS salary_rank
FROM employees;
```

`ORDER BY` bên trong `OVER(...)` quyết định thứ tự logic để tính window function, nhưng không tự sắp xếp toàn bộ hàng đầu ra. Nếu muốn hiển thị theo thứ tự phòng ban và thứ hạng, thêm:

```sql
ORDER BY department_id, salary_rank;
```

## 4. Thứ tự câu lệnh trong một transaction vẫn không đủ chứng minh đúng đắn

Một transaction thường được ứng dụng gửi tuần tự trên cùng connection:

```sql
BEGIN;

UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 101;

INSERT INTO order_items(order_id, product_id, quantity)
VALUES (5001, 101, 1);

COMMIT;
```

Thứ tự văn bản cho biết ứng dụng dự định trừ kho trước, rồi ghi chi tiết đơn hàng. Nhưng câu hỏi quan trọng hơn là:

- Có thực sự còn hàng để trừ không?
- `UPDATE` có cập nhật đúng một hàng không?
- Một request khác đang bán sản phẩm đó có thể đồng thời cập nhật không?
- Nếu `INSERT` thất bại, thay đổi tồn kho có bị rollback không?
- Transaction có bị framework đánh dấu rollback-only hay không?
- Có một transaction khác thay đổi dữ liệu giữa thời điểm đọc và ghi không?

Ví dụ trên thiếu điều kiện kiểm tra số lượng tồn kho:

```sql
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 101
  AND quantity >= 1;
```

Ứng dụng phải kiểm tra số hàng cập nhật. Nếu kết quả không phải 1, không được tiếp tục ghi đơn hàng và commit nghiệp vụ.

### 4.1. Ví dụ an toàn hơn với điều kiện nguyên tử ở câu UPDATE

```sql
BEGIN;

UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 101
  AND quantity >= 1;

-- Ứng dụng kiểm tra đúng 1 hàng được cập nhật.
-- Nếu không, ROLLBACK và trả lỗi hết hàng.

INSERT INTO order_items(order_id, product_id, quantity)
VALUES (5001, 101, 1);

COMMIT;
```

Điều kiện `quantity >= 1` nằm ngay trong thao tác cập nhật giúp DBMS kiểm tra điều kiện và thay đổi hàng trong cùng thao tác ghi. Với cơ sở dữ liệu quan hệ giao dịch, các transaction cạnh tranh cập nhật cùng hàng được điều phối theo khóa và isolation của DBMS.

Tuy nhiên, vẫn cần kiểm tra số hàng và xử lý lỗi insert. **Tính nguyên tử của transaction không tự làm cho điều kiện nghiệp vụ đúng** nếu ứng dụng bỏ qua kết quả lệnh.

## 5. Các transaction đồng thời tạo ra lịch thực thi xen kẽ

Thứ tự câu lệnh trong một session không quyết định toàn bộ thứ tự hành động trên database. Giả sử hai khách hàng cùng mua sản phẩm cuối cùng, tồn kho ban đầu là 1.

Một cách viết ngây thơ:

```sql
-- T1
BEGIN;
SELECT quantity FROM inventory WHERE product_id = 101;
-- Ứng dụng thấy 1.
UPDATE inventory SET quantity = 0 WHERE product_id = 101;
COMMIT;
```

T2 cũng chạy:

```sql
-- T2
BEGIN;
SELECT quantity FROM inventory WHERE product_id = 101;
-- Có thể cũng đã đọc 1 trước khi T1 commit.
UPDATE inventory SET quantity = 0 WHERE product_id = 101;
COMMIT;
```

Nếu hai session xen kẽ đúng thời điểm, cả hai có thể đều dựa vào cùng một giá trị đọc cũ. Cách cập nhật cố định thành 0 còn có thể che mất việc cả hai đều tưởng mình mua thành công.

Một lịch minh họa:

| Thời điểm | T1 | T2 |
|---|---|---|
| t1 | BEGIN | |
| t2 | SELECT quantity → 1 | |
| t3 | | BEGIN |
| t4 | | SELECT quantity → 1 |
| t5 | UPDATE quantity = 0 | |
| t6 | | UPDATE quantity = 0 |
| t7 | COMMIT | |
| t8 | | COMMIT |

Đây là minh họa cho lỗi thiết kế đọc-sửa-ghi; hành vi thực tế còn phụ thuộc isolation, khóa, DBMS và kế hoạch thực thi. Một cách tốt hơn là dùng câu cập nhật có điều kiện:

```sql
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 101
  AND quantity >= 1;
```

Một request chỉ được công nhận thành công nếu câu lệnh cập nhật đúng một hàng và transaction liên quan được commit. Request còn lại sau khi tranh chấp sẽ không đáp ứng điều kiện và không được phép tạo đơn hàng.

## 6. Isolation level quyết định những gì một transaction có thể quan sát

Isolation là thuộc tính ACID mô tả mức độ các transaction đồng thời bị cô lập khỏi nhau. Nó có ảnh hưởng trực tiếp đến việc có thể suy luận kết quả từ lịch câu lệnh hay không.

| Mức cô lập | Khái niệm chính | Rủi ro hoặc giới hạn cần hiểu |
|---|---|---|
| **READ UNCOMMITTED** | Có thể đọc dữ liệu chưa commit ở DBMS hỗ trợ mức này | Dirty read; một số DBMS không triển khai khác biệt thực tế với READ COMMITTED |
| **READ COMMITTED** | Mỗi statement thường chỉ đọc dữ liệu đã commit theo snapshot/điểm nhìn của statement | Các statement trong cùng transaction có thể thấy các ảnh chụp khác nhau |
| **REPEATABLE READ** | Các lần đọc lặp lại có tính ổn định hơn trong phạm vi transaction | Quy tắc phantom và xung đột ghi phụ thuộc DBMS |
| **SERIALIZABLE** | DBMS bảo đảm kết quả tương đương một thứ tự tuần tự hợp lệ, hoặc từ chối transaction không thể tuần tự hóa | Có thể có serialization failure; ứng dụng cần retry |

Tên mức cô lập giống nhau không bảo đảm chi tiết triển khai giống nhau giữa PostgreSQL, MySQL/InnoDB, Oracle và SQL Server. Khi phân tích một lỗi, phải xác định đúng DBMS và cấu hình.

### 6.1. READ COMMITTED: hai SELECT có thể thấy hai kết quả khác nhau

Giả sử T1 chạy:

```sql
BEGIN;

SELECT balance
FROM accounts
WHERE id = 1;

-- Tạm dừng xử lý...

SELECT balance
FROM accounts
WHERE id = 1;

COMMIT;
```

Trong khi đó T2 cập nhật và commit số dư. Ở PostgreSQL `READ COMMITTED`, mỗi câu lệnh đọc có snapshot mới. Vì vậy, SELECT thứ hai trong T1 có thể thấy giá trị mới đã commit bởi T2.

Không thể suy luận rằng “T1 đã SELECT giá trị X ở đầu transaction nên mọi SELECT sau đó sẽ vẫn là X” nếu isolation không bảo đảm điều đó.

### 6.2. REPEATABLE READ không có nghĩa mọi lịch đều đơn giản

Mức này thường giữ snapshot ổn định hơn trong một transaction, nhưng cách xử lý update conflict và phantom phụ thuộc DBMS. Trong PostgreSQL, `REPEATABLE READ` dựa trên snapshot transaction và có thể từ chối thao tác ghi nếu một hàng đã bị transaction khác thay đổi sau snapshot. MySQL/InnoDB có hành vi consistent read và locking read khác nhau.

Vì vậy, phải hiểu cả **loại truy vấn** (consistent read hay locking read) và **cơ chế DBMS**, không chỉ đọc tên isolation level.

### 6.3. SERIALIZABLE không phải “thực hiện tuần tự đúng thứ tự viết”

Serializable yêu cầu kết quả tương đương một thứ tự tuần tự hợp lệ của các transaction. DBMS có thể cho thực thi song song và kiểm tra xung đột; nếu không thể bảo đảm tính tương đương, một transaction có thể bị hủy với lỗi serialization.

Ứng dụng cần có chiến lược retry toàn bộ transaction khi nhận loại lỗi này. Serializable cũng không sửa được logic nghiệp vụ sai, chẳng hạn công thức tính sai hoặc kiểm tra thiếu điều kiện.

## 7. Write skew: từng transaction nhìn hợp lý nhưng kết quả chung sai

Một ví dụ kinh điển cho thấy chỉ xem thứ tự câu lệnh trong từng transaction là chưa đủ.

Giả sử quy định: luôn phải có ít nhất một bác sĩ trực. Bảng:

```sql
CREATE TABLE doctors (
    doctor_id INTEGER PRIMARY KEY,
    on_call BOOLEAN NOT NULL
);

INSERT INTO doctors VALUES
    (1, TRUE),
    (2, TRUE);
```

Hai transaction chạy đồng thời, mỗi người muốn nghỉ trực nếu người còn lại vẫn trực.

**T1:**

```sql
BEGIN;
SELECT COUNT(*) FROM doctors WHERE on_call = TRUE;
-- Thấy 2, nên cho bác sĩ 1 nghỉ.
UPDATE doctors SET on_call = FALSE WHERE doctor_id = 1;
COMMIT;
```

**T2:**

```sql
BEGIN;
SELECT COUNT(*) FROM doctors WHERE on_call = TRUE;
-- Cũng thấy 2, nên cho bác sĩ 2 nghỉ.
UPDATE doctors SET on_call = FALSE WHERE doctor_id = 2;
COMMIT;
```

Nếu isolation cho phép lịch này (chẳng hạn snapshot isolation trong một số hệ quản trị), cả hai transaction cập nhật hai hàng khác nhau và có thể commit. Kết quả: không còn bác sĩ nào trực.

Đây là **write skew**: mỗi transaction thực hiện quyết định từ một snapshot hợp lệ, nhưng các quyết định kết hợp lại vi phạm bất biến toàn cục.

Cách khắc phục tùy mô hình:

- Dùng `SERIALIZABLE` và retry transaction bị từ chối.
- Dùng khóa tường minh trên một hàng đại diện/guard row để tuần tự hóa quyết định.
- Thiết kế lại dữ liệu hoặc constraint để bất biến được biểu đạt và bảo vệ ở DBMS.
- Thực hiện kiểm tra và cập nhật trong một thao tác mà DBMS có thể đồng bộ đúng.

Khóa từng hàng mà mỗi transaction định sửa không đủ nếu điều kiện nghiệp vụ phụ thuộc **nhiều hàng**.

## 8. Những hành vi khác không thể suy ra từ thứ tự văn bản

### 8.1. Trigger có thể tạo thêm thao tác

Một câu:

```sql
INSERT INTO orders(order_id, customer_id)
VALUES (100, 5);
```

có thể kích hoạt trigger ghi audit, cập nhật bảng tổng hợp hoặc thực hiện kiểm tra bổ sung tùy cấu hình DBMS. Đọc script chỉ thấy một câu `INSERT` không có nghĩa chỉ một bảng bị tác động.

Trigger thường chạy trong ngữ cảnh transaction của statement; lỗi trigger có thể khiến statement và transaction bị ảnh hưởng theo quy tắc DBMS. Cần biết trigger nào tồn tại và side effect nào được kích hoạt.

### 8.2. Constraint có thể được kiểm tra ở các thời điểm khác nhau

Một constraint có thể được kiểm tra ngay khi statement thực thi hoặc trì hoãn đến thời điểm commit nếu DBMS và khai báo hỗ trợ. Do đó, câu lệnh ghi thành công chưa chắc transaction sẽ commit thành công.

Ví dụ constraint trì hoãn:

```sql
-- PostgreSQL: chỉ minh họa với FK được khai báo DEFERRABLE.
BEGIN;
SET CONSTRAINTS ALL DEFERRED;

-- Thực hiện các thay đổi có thể tạm thời chưa thỏa FK.
-- Trước COMMIT phải khôi phục trạng thái hợp lệ.

COMMIT;
```

Nếu điều kiện vẫn vi phạm lúc kiểm tra, `COMMIT` sẽ thất bại hoặc transaction bị từ chối commit. Không được suy luận “mọi câu SQL trước commit đều chạy không lỗi nên chắc chắn commit thành công”.

### 8.3. Sequence/identity không nhất thiết quay lui theo transaction

Một số cơ chế cấp số như PostgreSQL sequence có tính chất không transactional theo cách nhiều người kỳ vọng: giá trị đã lấy từ sequence có thể bị tiêu thụ dù transaction rollback. Vì vậy, khoảng trống trong ID không chứng minh mất dữ liệu hay transaction commit một phần.

### 8.4. Thao tác ngoài database không được rollback theo SQL

Nếu một transaction ghi đơn hàng rồi gọi API thanh toán hoặc gửi email, `ROLLBACK` database không tự thu hồi side effect đã xảy ra ở hệ thống ngoài. Một script tuần tự về mặt văn bản không tạo ra một transaction phân tán nguyên tử.

Các hệ thống tích hợp cần thiết kế outbox, idempotency hoặc saga/compensation theo phạm vi nghiệp vụ. Đây là cơ chế phối hợp nhiều tài nguyên, không phải tính chất tự động của SQL transaction.

## 9. Dùng lock để diễn đạt điều kiện đồng thời rõ ràng

Khi nghiệp vụ yêu cầu đọc một hàng rồi quyết định cập nhật, có thể dùng locking read nếu phù hợp với DBMS.

Ví dụ PostgreSQL:

```sql
BEGIN;

SELECT quantity
FROM inventory
WHERE product_id = 101
FOR UPDATE;

-- Ứng dụng kiểm tra quantity trong cùng transaction.
-- Nếu đủ hàng thì cập nhật, nếu không thì ROLLBACK.

UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 101;

COMMIT;
```

`FOR UPDATE` yêu cầu khóa hàng được chọn theo quy tắc DBMS, làm cho transaction cạnh tranh cần cập nhật hàng đó phải chờ hoặc xử lý theo cơ chế tương ứng.

Tuy nhiên, khóa tường minh cần được dùng có chủ đích:

- Giữ transaction càng ngắn càng tốt.
- Thực hiện kiểm tra sau khi đã lấy khóa.
- Nếu nhiều hàng, thống nhất thứ tự khóa để giảm deadlock.
- Không để ứng dụng chờ HTTP hoặc người dùng khi đang giữ khóa.
- Xử lý lỗi timeout/deadlock và retry phù hợp.

Với thao tác đơn giản như trừ hàng tồn, câu `UPDATE ... WHERE quantity >= 1` có thể diễn đạt điều kiện nguyên tử gọn hơn việc SELECT rồi UPDATE thủ công.

## 10. Phân tích kế hoạch thực thi và lịch transaction

Để hiểu DBMS thực sự làm gì, dùng công cụ thích hợp:

### 10.1. EXPLAIN / execution plan

PostgreSQL:

```sql
EXPLAIN
SELECT *
FROM orders
WHERE customer_id = 10;
```

`EXPLAIN ANALYZE` thực thi câu truy vấn để đo runtime (cẩn trọng với câu lệnh có tác động dữ liệu):

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM orders
WHERE customer_id = 10;
```

MySQL:

```sql
EXPLAIN
SELECT *
FROM orders
WHERE customer_id = 10;
```

Execution plan giúp thấy access path, join, ước lượng và số liệu thực thi. Nhưng một execution plan của một lần chạy **không phải cam kết vĩnh viễn**: thống kê, dữ liệu, tham số, cấu hình và phiên bản có thể làm kế hoạch đổi khác.

### 10.2. Quan sát transaction và blocker

PostgreSQL:

```sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    query_start,
    pg_blocking_pids(pid) AS blocking_pids,
    query
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start;
```

MySQL/InnoDB (tùy phiên bản và quyền):

```sql
SELECT * FROM performance_schema.data_locks;
SELECT * FROM performance_schema.data_lock_waits;
```

Để hiểu một lỗi production, kết hợp execution plan với trạng thái transaction, lock wait, thời điểm statement bắt đầu/kết thúc và transaction age. Execution plan không giải thích toàn bộ lịch giữa session; lock view cũng không thay thế việc hiểu ngữ nghĩa truy vấn.

## 11. Cách chứng minh một nghiệp vụ đúng đắn tốt hơn

Đừng dùng câu “câu A viết trước câu B” làm bằng chứng duy nhất. Hãy phân tích theo các lớp sau.

### 11.1. Phát biểu bất biến nghiệp vụ

Ví dụ với tồn kho:

> Số lượng không được âm; một đơn hàng chỉ được xác nhận nếu số hàng thực sự được giữ thành công.

Với chuyển tiền:

> Tổng tiền không đổi trong nghiệp vụ nội bộ; nguồn và đích đều tồn tại; số dư nguồn không âm; cả hai thay đổi phải commit cùng nhau.

Một bất biến rõ ràng giúp chọn constraint, phép cập nhật và isolation phù hợp.

### 11.2. Đưa điều kiện vào thao tác ghi hoặc constraint

Ví dụ:

```sql
UPDATE inventory
SET quantity = quantity - :requested
WHERE product_id = :product_id
  AND quantity >= :requested;
```

Kiểm tra số hàng cập nhật. Dùng CHECK, UNIQUE, FOREIGN KEY hoặc các constraint khác khi bất biến có thể biểu đạt ở schema.

### 11.3. Xác định transaction boundary

Xác định chính xác các thao tác nào cùng commit/rollback, connection nào được dùng và framework có thực sự áp dụng transaction không. Xác định thêm các ngoại lệ như DDL implicit commit, nhiều datasource và lời gọi dịch vụ ngoài.

### 11.4. Xác định isolation và xung đột có thể xảy ra

Liệt kê session cạnh tranh: hai người mua sản phẩm cuối, hai giao dịch rút tiền cùng tài khoản, hai worker xử lý cùng job, hai người sửa cùng bản ghi. Mô phỏng lịch xen kẽ để tìm race condition, lost update, non-repeatable read, phantom hoặc write skew.

### 11.5. Thiết kế nhánh lỗi và retry

Xác định kết quả khi UPDATE 0 hàng, unique violation, deadlock, lock timeout, serialization failure hoặc mất phản hồi COMMIT. Retry toàn transaction khi DBMS yêu cầu, và bảo vệ nghiệp vụ khỏi chạy trùng bằng idempotency key khi cần.

## 12. Ví dụ end-to-end: xác nhận đơn hàng và giữ tồn kho

Một luồng cơ bản có thể được triển khai theo transaction như sau. Cấu trúc bảng chỉ để minh họa.

```sql
BEGIN;

-- Giữ một đơn vị hàng chỉ khi còn hàng.
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 101
  AND quantity >= 1;

-- Ứng dụng phải kiểm tra row count = 1.
-- Nếu không, ROLLBACK và trả về OUT_OF_STOCK.

UPDATE orders
SET status = 'CONFIRMED'
WHERE order_id = 5001
  AND status = 'PENDING';

-- Ứng dụng phải kiểm tra row count đúng theo nghiệp vụ.
-- Nếu không, ROLLBACK.

INSERT INTO order_events(order_id, event_type)
VALUES (5001, 'CONFIRMED');

COMMIT;
```

Điều kiện để luồng này có ý nghĩa:

- Tất cả câu lệnh dùng cùng một transaction và tài nguyên DB phù hợp.
- Kiểm tra số hàng ở **mọi thao tác bắt buộc**, không chỉ câu đầu tiên.
- Nếu một bước thất bại, rollback trước khi trả connection về pool.
- Constraint bảo đảm các quan hệ dữ liệu.
- Nếu cần phát sự kiện cho hệ thống ngoài, ghi một bản ghi outbox trong chính transaction; tiến trình riêng phát sự kiện sau commit.
- Retry có kiểm soát khi gặp lỗi có thể retry và sử dụng mã request để chống xác nhận trùng.

Đoạn SQL là một mô hình luồng, phần kiểm tra row count và nhánh lỗi phải được thực hiện trong ứng dụng hoặc thủ tục DB tương ứng trước khi commit.

## 13. Những nhận định sai thường gặp

| Nhận định | Vì sao không đúng | Cách hiểu chính xác |
|---|---|---|
| Bảng viết trước trong FROM sẽ luôn được đọc trước | Optimizer được quyền chọn join order | FROM mô tả quan hệ logic |
| Điều kiện đầu trong WHERE luôn được đánh giá trước | Không có bảo đảm thứ tự đánh giá tổng quát như vậy | Viết biểu thức an toàn, dùng NULLIF/CASE/constraint |
| SELECT luôn trả theo thứ tự chèn | SQL không bảo đảm output order nếu thiếu ORDER BY | Khai báo thứ tự và tie-breaker |
| Câu SQL chạy trước thì transaction khác không thể xen vào | Session khác có lịch thực thi độc lập | Xét isolation, lock, snapshot |
| Có BEGIN là mọi hàng đã bị khóa | Khóa thường được lấy khi câu lệnh cần | Quan sát tài nguyên thật |
| Một UPDATE không báo lỗi là đã cập nhật đúng dữ liệu | Có thể 0 hàng được cập nhật | Kiểm tra row count và điều kiện |
| Các câu lệnh đều chạy xong là chắc chắn COMMIT thành công | Constraint deferred hoặc lỗi commit có thể xảy ra | Kiểm tra kết quả commit |
| Có transaction là mọi API ngoài cũng rollback | SQL transaction chỉ quản lý tài nguyên tham gia transaction đó | Dùng outbox/saga/idempotency |
| SERIALIZABLE đồng nghĩa DBMS thực hiện vật lý tuần tự | Có thể chạy song song và phát hiện xung đột | Kết quả phải tương đương lịch tuần tự |
| Execution plan hiện tại sẽ luôn giữ nguyên | Plan có thể đổi theo thống kê và dữ liệu | Đo lại trong điều kiện phù hợp |

## 14. Bài tập tư duy theo lịch thực thi

### Bài 1: LIMIT không có ORDER BY

Truy vấn `SELECT id FROM orders LIMIT 5` chạy hôm nay trả năm ID đầu tiên giống lần trước.

**Hỏi:** Có thể xây API phân trang ổn định dựa vào thứ tự đó không?

**Giải thích:** Không. Không có thứ tự được cam kết. Cần sắp xếp theo bộ khóa ổn định và thiết kế pagination phù hợp (ví dụ keyset pagination với khóa duy nhất).

### Bài 2: Hai session cùng mua món cuối

T1 và T2 cùng đọc tồn kho bằng 1, sau đó mỗi transaction ghi số lượng 0 và commit.

**Hỏi:** Vì sao việc mỗi transaction chạy SELECT trước UPDATE vẫn chưa đủ?

**Giải thích:** Hai SELECT có thể đọc cùng snapshot trước khi transaction còn lại commit. Hai quyết định độc lập dựa trên dữ liệu cũ. Dùng UPDATE có điều kiện và kiểm tra row count, hoặc cơ chế khóa thích hợp.

### Bài 3: WHERE có điều kiện bảo vệ phép chia

Câu SQL kiểm tra `denominator <> 0 AND numerator / denominator > 2`.

**Hỏi:** Có thể chắc chắn biểu thức chia chỉ chạy sau khi mẫu số được kiểm tra không?

**Giải thích:** Không nên dựa vào thứ tự đánh giá đó. Dùng `NULLIF(denominator, 0)` hoặc cách viết an toàn được DBMS hỗ trợ.

### Bài 4: Hai bác sĩ cùng nghỉ trực

T1 và T2 cùng đọc số bác sĩ trực bằng 2; mỗi người cập nhật một hàng khác nhau thành FALSE rồi commit.

**Hỏi:** Tại sao khóa hàng được sửa không nhất thiết bảo vệ điều kiện “ít nhất một người trực”?

**Giải thích:** Điều kiện phụ thuộc tập nhiều hàng. Hai transaction có thể sửa hai hàng khác nhau nên không xung đột ghi trực tiếp; cần serializable, guard row, khóa phạm vi phù hợp hoặc thiết kế constraint.

### Bài 5: Kế hoạch thực thi đổi sau khi thêm index

Một truy vấn từng quét bảng theo thứ tự ổn định, sau khi thêm index lại trả hàng theo thứ tự khác dù dữ liệu giống nhau.

**Hỏi:** DBMS có lỗi không?

**Giải thích:** Không nhất thiết. Truy vấn không ORDER BY không yêu cầu thứ tự đầu ra. Thêm index có thể khiến optimizer chọn access path khác.

### Bài 6: UPDATE thành công, COMMIT thất bại

Ứng dụng chạy UPDATE và không nhận lỗi, nhưng lúc COMMIT lại nhận lỗi constraint.

**Hỏi:** Có được trả thành công nghiệp vụ không?

**Giải thích:** Không. Phải xử lý kết quả commit; câu lệnh trước đó chưa đủ chứng minh transaction được xác nhận.

## Kết luận

Thứ tự câu lệnh SQL là một phần của câu chuyện, nhưng không phải bằng chứng đầy đủ về tính đúng đắn. **Ngữ nghĩa SQL** quyết định kết quả logic; **query optimizer** chọn kế hoạch vật lý; **cơ chế transaction và isolation** quyết định cách các phiên nhìn thấy, chờ và xung đột; **constraint và điều kiện cập nhật** bảo vệ bất biến; còn **xử lý lỗi và retry** quyết định ứng dụng có phản ánh đúng kết cục hay không.

Khi đánh giá một nghiệp vụ database, hãy chứng minh bất biến, xác định ranh giới transaction, phân tích các lịch đồng thời khả dĩ, kiểm tra row count/constraint, chọn isolation phù hợp và xử lý mọi kết cục commit/rollback. Đó là cơ sở đáng tin cậy hơn nhiều so với việc chỉ nhìn các câu SQL theo thứ tự từ trên xuống.
