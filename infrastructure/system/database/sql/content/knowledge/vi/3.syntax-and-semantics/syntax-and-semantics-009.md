# Tập hợp nhiều phần tử trùng, DISTINCT và ngữ nghĩa bản sao trong SQL

Trong toán học, một **tập hợp (set)** không chứa hai phần tử giống hệt nhau. Nhưng khi truy vấn cơ sở dữ liệu quan hệ bằng SQL, kết quả thường hoạt động như một **tập hợp đa phần tử (multiset, còn gọi là bag)**: cùng một giá trị hoặc cùng một hàng kết quả có thể xuất hiện nhiều lần. SQL giữ các lần xuất hiện đó theo mặc định; người viết truy vấn phải yêu cầu loại bản sao nếu thực sự cần.

Hiểu **bag semantics**, **SELECT DISTINCT** và ý nghĩa của các bản sao là nền tảng để dự đoán số dòng kết quả, giải thích kết quả **JOIN**, tính đúng **COUNT/SUM**, và phân biệt **UNION** với **UNION ALL**. Đây là một chủ đề thuộc phần **Cú pháp và ngữ nghĩa** của module **Database SQL**: không chỉ học câu lệnh viết thế nào, mà còn hiểu chính xác câu lệnh *có nghĩa gì*.

## 1. Tập hợp (set) khác tập hợp đa phần tử (bag) thế nào?

Xét hai tập hợp chứa chữ A, B:

- **Set:** {A, B}. Một phần tử chỉ được tính một lần, kể cả khi đầu vào cung cấp A nhiều lần.
- **Bag:** [A, A, B]. A xuất hiện **hai lần**, còn B xuất hiện **một lần**.

Số lần một giá trị xuất hiện được gọi là **bội số** (*multiplicity*). Ta có thể ký hiệu **m(v)** là bội số của giá trị **v** trong một bag:

| Giá trị | Bội số trong bag [A, A, B] | Có mặt trong set {A, B}? |
| --- | ---: | --- |
| A | 2 | Có, một lần |
| B | 1 | Có, một lần |
| C | 0 | Không |

Với một bag có nhiều cột, “phần tử” là **toàn bộ hàng kết quả**. Hai hàng được xem là bản sao khi mọi biểu thức được chọn trong hai hàng không phân biệt được với nhau theo quy tắc loại trùng của SQL.

Ví dụ, bảng đơn hàng có thể có khóa chính **order_id**, nhưng truy vấn chỉ lấy **customer_id** sẽ trả lại cùng mã khách hàng nhiều lần nếu người đó đặt nhiều đơn:

~~~sql
SELECT customer_id
FROM orders;
~~~

Điều này không có nghĩa là cơ sở dữ liệu lưu khách hàng trùng. Nhiều **đơn hàng khác nhau** có thể cùng thuộc về một khách hàng. Bản sao phát sinh bởi **phép chiếu** (projection), tức là ta chỉ giữ một phần các cột của những hàng gốc.

### Bag semantics là hành vi mặc định của SQL

~~~sql
SELECT ALL customer_id
FROM orders;
~~~

**SELECT ALL** giữ mọi lần xuất hiện và là hành vi mặc định:

~~~sql
SELECT customer_id
FROM orders;
~~~

Hai truy vấn trên tương đương về những hàng và bội số mà chúng trả về. **ALL** ít khi được viết tường minh trong câu SELECT thông thường, nhưng rất quan trọng để hiểu sự khác biệt với **DISTINCT**.

## 2. Tạo dữ liệu minh họa để thực hành

Các ví dụ sau dùng **PostgreSQL**. Để có thể chạy chúng độc lập với bảng của những bài khác, hãy mở một phiên kết nối mới và tạo hai **bảng tạm** có tiền tố **bag_demo_**. Bảng tạm tự biến mất khi phiên kết nối kết thúc.

~~~sql
CREATE TEMP TABLE bag_demo_orders (
    order_id    INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    status      VARCHAR(20),
    amount      NUMERIC(12, 2) NOT NULL
);

INSERT INTO bag_demo_orders
    (order_id, customer_id, status, amount)
VALUES
    (1, 10, 'paid',    100000),
    (2, 10, 'paid',    120000),
    (3, 20, 'paid',    100000),
    (4, 30, 'pending',  50000),
    (5, 30, 'pending',  50000),
    (6, 40, NULL,     100000),
    (7, 40, NULL,     100000);

CREATE TEMP TABLE bag_demo_order_items (
    order_id   INTEGER NOT NULL REFERENCES bag_demo_orders(order_id),
    product_id INTEGER NOT NULL,
    quantity   INTEGER NOT NULL,
    PRIMARY KEY (order_id, product_id)
);

INSERT INTO bag_demo_order_items
    (order_id, product_id, quantity)
VALUES
    (1, 101, 1),
    (1, 102, 2),
    (2, 101, 1),
    (3, 103, 1),
    (4, 102, 2),
    (5, 102, 1),
    (6, 104, 1),
    (7, 104, 1);
~~~

Tập dữ liệu có **7 đơn hàng** và **8 dòng chi tiết**. Khóa chính làm cho mỗi **order_id** là duy nhất. Tuy vậy, khách hàng 10 có hai đơn, khách hàng 30 có hai đơn, khách hàng 40 có hai đơn; các giá trị **status** và **amount** cũng lặp lại.

Để thấy một bảng **thực sự chứa các hàng giống hệt nhau** nếu không có ràng buộc ngăn trùng, ta tạo thêm bảng tạm:

~~~sql
CREATE TEMP TABLE bag_demo_tags (
    tag TEXT
);

INSERT INTO bag_demo_tags (tag)
VALUES ('SQL'), ('SQL'), ('JOIN'), (NULL), (NULL);
~~~

Bảng **bag_demo_tags** chứa năm hàng, trong đó **SQL** xuất hiện hai lần và **NULL** xuất hiện hai lần. Không có PRIMARY KEY hay UNIQUE nên bảng cho phép các bản sao này.

> Các bảng tạm chỉ tồn tại trong phiên kết nối hiện tại. Nếu đóng phiên và mở lại, hãy chạy đoạn tạo dữ liệu một lần nữa trước các ví dụ bên dưới. Nếu chạy lại trong cùng phiên, tên bảng tạm đã tồn tại; có thể mở phiên mới hoặc xóa riêng các bảng tạm đã tạo.

## 3. SELECT thông thường giữ các bản sao

Chạy:

~~~sql
SELECT customer_id
FROM bag_demo_orders
ORDER BY customer_id;
~~~

Kết quả có **7 dòng**:

| customer_id |
| ---: |
| 10 |
| 10 |
| 20 |
| 30 |
| 30 |
| 40 |
| 40 |

Tuy có bốn giá trị customer_id khác nhau, truy vấn vẫn trả về bảy dòng, vì mỗi dòng gốc tạo ra một dòng kết quả. **ORDER BY** chỉ yêu cầu cách sắp xếp; nó **không xóa trùng**.

Tiếp theo:

~~~sql
SELECT status
FROM bag_demo_orders;
~~~

Kết quả gồm ba lần **paid**, hai lần **pending** và hai giá trị **NULL**. Thứ tự của các dòng **không được đảm bảo** vì không có ORDER BY, nhưng bội số của từng giá trị vẫn như vậy.

**Hai kiểu “trùng” cần phân biệt:**

1. **Trùng trong dữ liệu gốc:** nhiều hàng nguồn giống nhau ở tất cả cột có liên quan; ví dụ hai hàng có tag = 'SQL' trong bag_demo_tags.
2. **Trùng trong kết quả:** các hàng nguồn khác nhau nhưng giống nhau ở những cột được SELECT; ví dụ hai đơn của khách hàng 10 cùng cho ra giá trị 10 khi SELECT customer_id.

Trong cả hai trường hợp, SELECT mặc định giữ các lần xuất hiện.

## 4. DISTINCT loại bản sao của toàn bộ hàng kết quả

Thêm **DISTINCT** ngay sau SELECT:

~~~sql
SELECT DISTINCT customer_id
FROM bag_demo_orders
ORDER BY customer_id;
~~~

Kết quả:

| customer_id |
| ---: |
| 10 |
| 20 |
| 30 |
| 40 |

Từ bảy dòng ban đầu, kết quả còn **bốn dòng**, vì mỗi giá trị customer_id chỉ giữ một lần.

### DISTINCT xét tổ hợp của tất cả biểu thức SELECT

~~~sql
SELECT DISTINCT customer_id, status
FROM bag_demo_orders
ORDER BY customer_id;
~~~

Kết quả:

| customer_id | status |
| ---: | --- |
| 10 | paid |
| 20 | paid |
| 30 | pending |
| 40 | NULL |

DISTINCT ở đây xét **cặp (customer_id, status)**. Cặp (10, paid) xuất hiện hai lần trong dữ liệu đầu vào nhưng chỉ còn một hàng ở kết quả. Không tồn tại nghĩa “DISTINCT chỉ áp dụng cho cột đầu tiên” trong cú pháp **SELECT DISTINCT col1, col2**.

Ví dụ khác:

~~~sql
SELECT DISTINCT order_id, customer_id
FROM bag_demo_orders;
~~~

Truy vấn vẫn trả về **7 dòng**: order_id là khóa chính, vì vậy không có hai hàng nào trùng nhau khi biểu thức được chọn chứa order_id. Dùng DISTINCT trong trường hợp này không làm giảm số hàng.

### DISTINCT được áp dụng sau bước tạo giá trị đầu ra

Một mô hình logic rút gọn để đọc SELECT:

1. **FROM/JOIN:** xác định nguồn và kết hợp các hàng.
2. **WHERE:** lọc những hàng thỏa điều kiện.
3. **GROUP BY/HAVING** nếu có: gom nhóm và lọc nhóm.
4. **SELECT:** tính các biểu thức đầu ra.
5. **DISTINCT** nếu có: chỉ giữ một lần cho mỗi hàng kết quả khác nhau.
6. **ORDER BY**, **OFFSET/LIMIT** nếu có: sắp xếp và giới hạn đầu ra.

Đây là **thứ tự ngữ nghĩa** để hiểu kết quả, không phải cam kết về thứ tự thực thi vật lý của bộ tối ưu truy vấn.

Chẳng hạn:

~~~sql
SELECT DISTINCT status
FROM bag_demo_orders
WHERE amount >= 100000;
~~~

Các đơn có amount dưới 100000 bị lọc trước; DISTINCT chỉ xử lý các giá trị status còn lại. Nếu thay WHERE, tập giá trị mà DISTINCT nhìn thấy cũng đổi.

## 5. NULL và ngữ nghĩa “không phân biệt được” khi loại trùng

NULL biểu thị giá trị chưa biết hoặc chưa có. Trong biểu thức điều kiện SQL thông thường, phép so sánh **NULL = NULL** không cho TRUE mà cho **UNKNOWN**:

~~~sql
SELECT
    CAST(NULL AS INTEGER) = CAST(NULL AS INTEGER)
        AS ordinary_equal,
    CAST(NULL AS INTEGER) IS NOT DISTINCT FROM CAST(NULL AS INTEGER)
        AS null_safe_equal;
~~~

Trong PostgreSQL, **ordinary_equal** là NULL (UNKNOWN), còn **null_safe_equal** là TRUE.

Tuy nhiên, khi **DISTINCT** loại các bản sao, SQL xem các giá trị NULL ở cùng vị trí là **không phân biệt được**. Vì vậy:

~~~sql
SELECT DISTINCT tag
FROM bag_demo_tags;
~~~

Kết quả gồm đúng **ba giá trị khác nhau theo quy tắc DISTINCT**: **'SQL'**, **'JOIN'** và **một NULL**. Hai hàng NULL chỉ tạo một hàng NULL trong kết quả. Nếu chọn nhiều cột, phép loại trùng xem xét toàn bộ tổ hợp; ví dụ **(10, NULL)** và **(10, NULL)** được gộp, nhưng **(10, NULL)** và **(20, NULL)** thì không.

Quy tắc này cũng xuất hiện trong **GROUP BY** và các phép tập hợp như **UNION**. Nó không làm thay đổi logic ba giá trị của WHERE; để lọc NULL, vẫn dùng:

~~~sql
SELECT *
FROM bag_demo_orders
WHERE status IS NULL;
~~~

**Lưu ý:** cách ràng buộc **UNIQUE** xử lý nhiều giá trị NULL có thể khác nhau theo hệ quản trị và theo tùy chọn ràng buộc. Không nên suy ra quy tắc của UNIQUE chỉ từ quy tắc DISTINCT.

## 6. COUNT, SUM và DISTINCT bên trong hàm tổng hợp

**SELECT DISTINCT** và **COUNT(DISTINCT ...)** làm hai việc khác nhau:

- **SELECT DISTINCT** loại hàng trùng khỏi **kết quả SELECT**.
- **COUNT(DISTINCT expression)** đếm số **giá trị expression khác NULL và không trùng nhau** trong đầu vào của phép tổng hợp.

Ví dụ:

~~~sql
SELECT
    COUNT(*) AS all_rows,
    COUNT(status) AS non_null_status_rows,
    COUNT(DISTINCT status) AS unique_non_null_statuses,
    COUNT(DISTINCT customer_id) AS unique_customers
FROM bag_demo_orders;
~~~

| all_rows | non_null_status_rows | unique_non_null_statuses | unique_customers |
| ---: | ---: | ---: | ---: |
| 7 | 5 | 2 | 4 |

Giải thích:

- **COUNT(*) = 7**: đếm mọi hàng, kể cả hàng có NULL.
- **COUNT(status) = 5**: bỏ qua hai hàng có status NULL, nhưng **vẫn đếm từng lần** của paid và pending.
- **COUNT(DISTINCT status) = 2**: có hai status khác NULL là paid và pending.
- **COUNT(DISTINCT customer_id) = 4**: có bốn khách hàng có đơn.

So sánh thêm:

~~~sql
SELECT
    SUM(amount) AS sum_all_amount,
    SUM(DISTINCT amount) AS sum_distinct_amount
FROM bag_demo_orders;
~~~

| sum_all_amount | sum_distinct_amount |
| ---: | ---: |
| 620000 | 270000 |

**SUM(amount)** cộng tiền của cả bảy đơn. **SUM(DISTINCT amount)** chỉ cộng các mức tiền **50000 + 100000 + 120000**, mỗi giá trị một lần, bất kể có bao nhiêu đơn mang giá trị ấy. Do đó, **SUM(DISTINCT amount) thường không phải cách khắc phục việc JOIN nhân bản hàng khi tính doanh thu**. Hai đơn hoàn toàn hợp lệ có thể bằng tiền nhau và vẫn phải được cộng hai lần.

Khi có nhóm, DISTINCT trong hàm tổng hợp được đánh giá **trong từng nhóm**:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS order_count,
    COUNT(DISTINCT amount) AS different_amount_count,
    SUM(amount) AS total_amount
FROM bag_demo_orders
GROUP BY customer_id
ORDER BY customer_id;
~~~

Khách hàng **40** có **hai đơn** cùng trị giá 100000, nên **order_count = 2**, **different_amount_count = 1**, và **total_amount = 200000**. Điều đó cho thấy “hai giá trị bằng nhau” không đồng nghĩa với “một giao dịch”.

## 7. GROUP BY và DISTINCT giống nhau ở điểm nào, khác nhau ở đâu?

Hai câu dưới đây đều có thể tạo ra danh sách customer_id duy nhất:

~~~sql
SELECT DISTINCT customer_id
FROM bag_demo_orders;
~~~

~~~sql
SELECT customer_id
FROM bag_demo_orders
GROUP BY customer_id;
~~~

Nhưng mục đích chính khác nhau:

| Đặc điểm | DISTINCT | GROUP BY |
| --- | --- | --- |
| Câu hỏi thường gặp | “Những hàng đầu ra khác nhau là gì?” | “Mỗi nhóm có thống kê gì?” |
| Cách nhóm xét giá trị NULL | Các bản sao NULL được gộp | Các hàng cùng giá trị nhóm NULL được gom trong một nhóm |
| Hàm tổng hợp | Có thể dùng DISTINCT bên trong hàm tổng hợp | Thường kết hợp COUNT, SUM, AVG, MIN, MAX |
| Kết quả khi chỉ chọn cột phân nhóm | Mỗi tổ hợp một hàng | Mỗi tổ hợp một hàng |

Ví dụ muốn biết mỗi trạng thái có bao nhiêu đơn:

~~~sql
SELECT status, COUNT(*) AS order_count
FROM bag_demo_orders
GROUP BY status
ORDER BY status NULLS LAST;
~~~

Kết quả gồm **paid = 3**, **pending = 2**, **NULL = 2**. **SELECT DISTINCT status** chỉ có thể cho biết các giá trị trạng thái, còn COUNT theo từng nhóm giúp biết số lần xuất hiện.

**GROUP BY** không phải một cách viết thay thế mọi trường hợp của DISTINCT. Khi cần chỉ **một dòng đại diện** từ các dòng khác nhau về order_id/amount, bạn phải xác định *chọn dòng nào*; việc nhóm theo customer_id rồi chọn tùy ý order_id không được phép trong SQL chuẩn.

## 8. JOIN có thể tăng bội số của hàng như thế nào?

**JOIN** không tự loại bản sao. Một hàng ở bảng bên trái sẽ ghép với **mỗi** hàng khớp ở bảng bên phải. Vì vậy, kết quả JOIN có thể nhiều hàng hơn từng bảng đầu vào.

~~~sql
SELECT
    o.order_id,
    o.customer_id,
    o.amount,
    i.product_id,
    i.quantity
FROM bag_demo_orders AS o
JOIN bag_demo_order_items AS i
    ON i.order_id = o.order_id
ORDER BY o.order_id, i.product_id;
~~~

Đơn **1** có hai sản phẩm (101 và 102), nên các thông tin ở bảng orders của đơn 1 xuất hiện **hai lần** trong kết quả JOIN. Các đơn 2–7 mỗi đơn có một dòng chi tiết, vì vậy kết quả có **8 hàng**.

Nếu bỏ product_id và quantity khỏi danh sách SELECT:

~~~sql
SELECT o.order_id, o.customer_id, o.amount
FROM bag_demo_orders AS o
JOIN bag_demo_order_items AS i
    ON i.order_id = o.order_id
ORDER BY o.order_id;
~~~

Kết quả vẫn có **8 hàng**. Trong đó hàng **(1, 10, 100000)** xuất hiện **hai lần**, vì DISTINCT chưa được yêu cầu. Những hàng trùng nhau xuất phát từ **hai dòng chi tiết khác nhau**.

### Vì sao cộng tiền sau JOIN dễ bị sai?

~~~sql
SELECT SUM(o.amount) AS possibly_overcounted
FROM bag_demo_orders AS o
JOIN bag_demo_order_items AS i
    ON i.order_id = o.order_id;
~~~

Truy vấn trên cộng **amount của đơn 1 hai lần**, do nó có hai sản phẩm. Trong dữ liệu mẫu, phép cộng cho **720000**, trong khi tổng amount của bảy đơn là **620000**.

Không sửa bằng cách thêm **SUM(DISTINCT o.amount)**: các đơn 1, 3, 6 và 7 đều có amount = 100000 và vẫn phải được tính riêng. Cách đúng phụ thuộc điều đang muốn đo:

**Tổng tiền theo từng đơn, không cần bảng chi tiết:**

~~~sql
SELECT SUM(amount) AS total_amount
FROM bag_demo_orders;
~~~

**Tổng tiền của những đơn có ít nhất một dòng chi tiết:**

~~~sql
SELECT SUM(o.amount) AS total_amount
FROM bag_demo_orders AS o
WHERE EXISTS (
    SELECT 1
    FROM bag_demo_order_items AS i
    WHERE i.order_id = o.order_id
);
~~~

**EXISTS** kiểm tra sự tồn tại của dòng khớp mà không nhân số lần xuất hiện của đơn hàng. Nếu mục tiêu là tính tổng từ từng dòng chi tiết thật, hãy dùng **số lượng × đơn giá lưu ở từng dòng chi tiết**, rồi nhóm đúng cấp cần tính; không cộng lại tổng đơn trên mỗi dòng.

### COUNT(*) và COUNT(DISTINCT key) sau JOIN

~~~sql
SELECT
    COUNT(*) AS joined_rows,
    COUNT(DISTINCT o.order_id) AS distinct_orders
FROM bag_demo_orders AS o
JOIN bag_demo_order_items AS i
    ON i.order_id = o.order_id;
~~~

| joined_rows | distinct_orders |
| ---: | ---: |
| 8 | 7 |

Đây là hai câu hỏi khác nhau: có bao nhiêu **hàng ghép thành công**, và có bao nhiêu **đơn hàng khác nhau xuất hiện sau phép ghép**. COUNT(DISTINCT key) rất hữu ích cho câu hỏi thứ hai; nó không tự làm cho các phép tính trên thuộc tính của hàng cha trở nên đúng.

## 9. UNION và UNION ALL: hai cách kết hợp kết quả

Để gộp kết quả của hai truy vấn có cùng số cột và kiểu dữ liệu tương thích, SQL cung cấp **UNION** và **UNION ALL**.

~~~sql
SELECT customer_id
FROM bag_demo_orders
WHERE status = 'paid'

UNION ALL

SELECT customer_id
FROM bag_demo_orders
WHERE amount >= 100000;
~~~

Nhánh thứ nhất trả về **[10, 10, 20]**. Nhánh thứ hai trả về **[10, 10, 20, 40, 40]**. **UNION ALL** giữ tất cả các lần xuất hiện từ cả hai nhánh, nên trả về **8 hàng** với bội số:

| customer_id | Số lần trong UNION ALL |
| ---: | ---: |
| 10 | 4 |
| 20 | 2 |
| 40 | 2 |

Nếu thay **UNION ALL** bằng **UNION**, kết quả chỉ còn **ba giá trị**: 10, 20, 40. **UNION** mặc định loại hàng trùng trên toàn bộ kết quả kết hợp; có thể hiểu nó tương đương **UNION DISTINCT**.

| Toán tử | Xử lý bản sao |
| --- | --- |
| UNION ALL | Giữ mọi lần xuất hiện từ cả hai nhánh |
| UNION (DISTINCT) | Chỉ giữ mỗi hàng khác nhau một lần |

**Không có ORDER BY thì không được giả định thứ tự kết quả** của UNION hay UNION ALL, dù các nhánh được viết theo thứ tự nào. Khi cần sắp xếp kết quả chung, thêm ORDER BY phù hợp ở cuối biểu thức kết hợp.

### Bội số trong phép tập hợp

Trong ngữ nghĩa bag, có thể xem các phép sau qua số lần xuất hiện của một giá trị x. Gọi **a** và **b** là bội số của x trong hai đầu vào:

| Phép toán | Bội số đầu ra của x |
| --- | --- |
| UNION ALL | a + b |
| UNION | 1 nếu a + b > 0, ngược lại 0 |
| INTERSECT ALL | min(a, b) |
| INTERSECT | 1 nếu cả a và b đều > 0, ngược lại 0 |
| EXCEPT ALL | max(a − b, 0) |
| EXCEPT | 1 nếu a > 0 và b = 0, ngược lại 0 |

Ví dụ, cho **A = [A, A, B]** và **B = [A, C]**:

- **UNION ALL** cho [A, A, A, B, C].
- **UNION** cho [A, B, C].
- **INTERSECT ALL** cho [A].
- **EXCEPT ALL** cho [A, B].

PostgreSQL hỗ trợ **INTERSECT ALL** và **EXCEPT ALL**. Hỗ trợ và cú pháp của hai biến thể này có thể khác ở một số hệ quản trị khác; cần tra cứu tài liệu của hệ đang dùng.

Ví dụ thực thi INTERSECT ALL trong PostgreSQL:

~~~sql
WITH
    left_input(x) AS (VALUES ('A'), ('A'), ('B')),
    right_input(x) AS (VALUES ('A'), ('C'))
SELECT x FROM left_input
INTERSECT ALL
SELECT x FROM right_input;
~~~

Kết quả chỉ có một hàng A, vì nhánh trái có hai A nhưng nhánh phải chỉ có một A. Với phép **UNION**, **INTERSECT** và **EXCEPT** mặc định, các hàng trùng nhau (bao gồm NULL tương ứng) được xử lý theo quy tắc phân biệt hàng của phép tập hợp.

## 10. Diễn giải ngữ nghĩa bag theo từng phép toán

Có thể hiểu cách các toán tử tác động lên bội số như sau:

| Phép SQL | Bội số được xử lý ra sao? |
| --- | --- |
| FROM một bảng | Mỗi hàng xuất hiện theo số lần của nó trong đầu vào |
| WHERE | Hàng thỏa điều kiện TRUE được giữ nguyên bội số; hàng khác bị loại |
| SELECT biểu thức/cột | Những hàng gốc khác nhau có thể chiếu thành cùng một hàng đầu ra, và bội số của chúng cộng lại |
| INNER JOIN | Mỗi cặp hàng khớp tạo một hàng; nhiều cặp có thể cho cùng đầu ra |
| UNION ALL | Cộng bội số của hai đầu vào |
| DISTINCT | Đưa mọi bội số lớn hơn 0 về 1 |
| GROUP BY | Tạo một hàng kết quả cho mỗi tổ hợp khóa nhóm; các hàm tổng hợp đọc toàn bộ các hàng thuộc nhóm |

Nếu cần biểu thức ngắn gọn, gọi **m_R(r)** là số lần hàng r xuất hiện trong đầu vào R. Với một phép chiếu lấy các cột X, bội số của hàng kết quả x là:

\[
m_{\pi_X(R)}(x)
=\sum_{\{r:\,\pi_X(r)=x\}}m_R(r).
\]

Nói bằng lời: **cộng số lần xuất hiện của mọi hàng nguồn trở thành cùng một hàng kết quả** khi chỉ giữ các cột X. Điều đó lý giải vì sao có thể phát sinh bản sao ngay cả khi bảng gốc có khóa chính.

Với INNER JOIN, mỗi cặp hàng thỏa điều kiện nối đều góp một lần xuất hiện tương ứng. Chẳng hạn, nếu một mã có **2 hàng** trong bảng A và **3 hàng** trong bảng B, nối theo mã đó có thể tạo **2 × 3 = 6 hàng** cho mã ấy. Đây là hệ quả của số cặp khớp, không phải lỗi của JOIN.

### SQL có phải lúc nào cũng là bag không?

Không. SQL cho phép chọn ngữ nghĩa phù hợp theo từng phép toán:

- Một SELECT thông thường giữ bản sao.
- SELECT DISTINCT và UNION mặc định loại bản sao.
- GROUP BY gom những hàng cùng khóa nhóm trước khi tổng hợp.
- Một bảng có PRIMARY KEY ngăn các hàng trùng nhau ở cột khóa, nhưng phép chiếu hoặc JOIN vẫn có thể sinh bản sao trong kết quả.

Vì vậy, nhận định chính xác là **SQL sử dụng ngữ nghĩa bag làm mặc định cho nhiều phép truy vấn, đồng thời cung cấp các toán tử chuyển kết quả về ngữ nghĩa set khi cần**.

## 11. Khi cần một hàng đại diện cho mỗi nhóm

Một nhu cầu thực tế là “lấy **một đơn** có amount lớn nhất của mỗi khách hàng, đồng thời hiển thị order_id của đơn ấy”. Đây **không phải** tác vụ chỉ loại những hàng giống hệt nhau. Các đơn của cùng khách khác nhau ở order_id hoặc amount; DISTINCT thông thường không biết bạn muốn chọn đơn nào.

### Cách phổ biến: ROW_NUMBER()

~~~sql
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        amount,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY amount DESC, order_id DESC
        ) AS rn
    FROM bag_demo_orders
)
SELECT customer_id, order_id, amount
FROM ranked_orders
WHERE rn = 1
ORDER BY customer_id;
~~~

**PARTITION BY customer_id** chia các đơn thành nhóm theo khách. Trong mỗi nhóm, **ORDER BY amount DESC, order_id DESC** xác định thứ tự ưu tiên: tiền cao nhất trước; nếu cùng số tiền, lấy order_id lớn nhất để quyết định ổn định. **ROW_NUMBER() = 1** giữ đúng một đơn đại diện của mỗi khách.

### Cú pháp đặc thù PostgreSQL: DISTINCT ON

PostgreSQL cung cấp **DISTINCT ON**:

~~~sql
SELECT DISTINCT ON (customer_id)
    customer_id, order_id, amount
FROM bag_demo_orders
ORDER BY customer_id, amount DESC, order_id DESC;
~~~

Khác với SELECT DISTINCT chuẩn, **DISTINCT ON (customer_id)** giữ hàng đầu tiên của mỗi customer_id theo quy tắc ORDER BY. Trong PostgreSQL, các biểu thức của DISTINCT ON phải khớp với những biểu thức đứng đầu ORDER BY. Nếu thiếu sắp xếp đủ rõ ràng, “hàng đầu tiên” có thể không ổn định. **DISTINCT ON không phải cú pháp SQL chuẩn phổ biến ở mọi hệ quản trị**; khi cần tính chuyển đổi, có thể ưu tiên ROW_NUMBER().

### Muốn biết chỉ số tổng hợp thì dùng GROUP BY

Nếu không cần order_id đại diện, muốn biết **mức tiền đơn lớn nhất của mỗi khách**, hãy dùng:

~~~sql
SELECT
    customer_id,
    MAX(amount) AS max_order_amount
FROM bag_demo_orders
GROUP BY customer_id
ORDER BY customer_id;
~~~

Chọn giữa DISTINCT, GROUP BY và ROW_NUMBER() tùy **ý nghĩa của câu hỏi**, không chỉ vì cả ba đều có thể tạo ra số dòng ít hơn.

## 12. DISTINCT, ORDER BY và LIMIT

Việc loại trùng **không đồng nghĩa với sắp xếp**. Nếu cần danh sách mã khách hàng tăng dần:

~~~sql
SELECT DISTINCT customer_id
FROM bag_demo_orders
ORDER BY customer_id ASC;
~~~

Nếu thêm LIMIT:

~~~sql
SELECT DISTINCT customer_id
FROM bag_demo_orders
ORDER BY customer_id ASC
LIMIT 2;
~~~

Kết quả là **10** và **20**. Nếu bỏ ORDER BY, hai giá trị nào xuất hiện đầu tiên không được SQL bảo đảm. Điều này đặc biệt quan trọng khi phân trang.

Trong PostgreSQL, với **SELECT DISTINCT**, biểu thức dùng trong ORDER BY phải có trong danh sách SELECT. Ví dụ, muốn lấy mỗi customer_id một lần nhưng sắp theo đơn lớn nhất, hãy biểu diễn yêu cầu bằng GROUP BY:

~~~sql
SELECT
    customer_id,
    MAX(amount) AS largest_order_amount
FROM bag_demo_orders
GROUP BY customer_id
ORDER BY largest_order_amount DESC, customer_id ASC;
~~~

Việc thêm **amount** thẳng vào SELECT DISTINCT để có thể ORDER BY amount sẽ thay đổi khóa loại trùng thành **(customer_id, amount)**; một khách có nhiều mức amount khi đó có thể xuất hiện nhiều lần. Đó là một thay đổi **ngữ nghĩa**, không chỉ thay đổi cách hiển thị.

## 13. Chi phí xử lý và cách chọn công cụ đúng

Để thực hiện DISTINCT, hệ quản trị thường phải xác định các hàng giống nhau bằng cơ chế như **sắp xếp** hoặc **bảng băm**. Công việc này có thể tốn CPU, bộ nhớ và thời gian khi đầu vào lớn. Bộ tối ưu truy vấn cũng có thể bỏ bớt công việc nếu chứng minh dữ liệu đã duy nhất nhờ khóa hoặc các ràng buộc.

Vì thế, không nên thêm DISTINCT theo thói quen vào mọi truy vấn. Hãy xác định trước:

1. **Đơn vị kết quả là gì?** Một hàng đại diện cho khách hàng, đơn hàng, dòng chi tiết hay một tổ hợp giá trị?
2. **Vì sao có các lần xuất hiện giống nhau?** Dữ liệu nguồn thực sự trùng, phép chiếu bỏ khóa, hay JOIN một–nhiều/nhiều–nhiều?
3. **Có cần giữ số lần xuất hiện không?** Tính số giao dịch, số sản phẩm bán được hoặc tổng tiền thường cần giữ đúng bội số.
4. **Có cần một đại diện theo tiêu chí chọn không?** Nếu có, xác định ORDER BY và dùng ROW_NUMBER()/DISTINCT ON thay vì DISTINCT thông thường.

Một truy vấn chẩn đoán dễ dùng để tìm giá trị xuất hiện nhiều lần:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS occurrences
FROM bag_demo_orders
GROUP BY customer_id
HAVING COUNT(*) > 1
ORDER BY occurrences DESC, customer_id;
~~~

Kết quả cho thấy các khách hàng **10, 30 và 40** đều có hai đơn. Đây là quan hệ nghiệp vụ hợp lệ, không nhất thiết là bản ghi lỗi.

Khi quan hệ thực tế bị nhân dòng do JOIN thiếu điều kiện, cần xem lại **khóa và điều kiện JOIN**, thay vì chỉ chèn DISTINCT để che kết quả bất thường. Nếu mục tiêu là kiểm tra “có hay không” bản ghi liên quan, **EXISTS** thường diễn đạt ý định chính xác hơn JOIN rồi DISTINCT.

## 14. Các lỗi hiểu nhầm thường gặp

| Hiểu nhầm | Giải thích đúng |
| --- | --- |
| “Bảng có PRIMARY KEY thì truy vấn không có bản sao.” | PRIMARY KEY đảm bảo duy nhất ở cấp khóa. SELECT bỏ khóa hoặc JOIN có thể sinh các hàng kết quả giống nhau. |
| “SELECT DISTINCT a, b chỉ loại trùng ở a.” | DISTINCT xét **cả cặp (a, b)**. |
| “ORDER BY sẽ sắp xếp và loại trùng.” | ORDER BY chỉ sắp xếp; muốn loại trùng dùng DISTINCT hoặc phép toán tương ứng. |
| “DISTINCT không giữ NULL.” | SELECT DISTINCT giữ **một NULL** trong mỗi tổ hợp tương ứng; COUNT(DISTINCT col) lại **không đếm NULL**. |
| “COUNT(col) và COUNT(*) luôn bằng nhau.” | COUNT(col) bỏ qua các hàng mà col là NULL; COUNT(*) đếm mọi hàng. |
| “JOIN tạo thêm dòng là dữ liệu bị trùng sai.” | JOIN tạo một dòng cho **mỗi cặp khớp**; một–nhiều và nhiều–nhiều tự nhiên làm tăng số hàng. |
| “SUM(DISTINCT amount) sửa được doanh thu bị nhân đôi.” | Nó bỏ cả các số tiền bằng nhau thuộc những giao dịch khác nhau; có thể làm sai tổng tiền. |
| “UNION và UNION ALL tương đương.” | UNION loại hàng trùng; UNION ALL giữ các lần xuất hiện. |
| “LIMIT tự chọn những dòng đầu theo thứ tự chèn.” | Không có ORDER BY phù hợp thì thứ tự kết quả không được bảo đảm. |
| “DISTINCT chọn hàng mới nhất của mỗi khách.” | DISTINCT không có quy tắc chọn hàng đại diện theo thời gian; hãy dùng ROW_NUMBER() hoặc DISTINCT ON với thứ tự rõ ràng. |

## 15. Bài thực hành củng cố

Sử dụng ba bảng tạm đã tạo ở phần 2 để tự viết các truy vấn sau:

1. Liệt kê mỗi **status** đúng một lần. Quan sát sự xuất hiện của NULL và phân biệt kết quả với **COUNT(DISTINCT status)**.
2. Đếm số **customer_id khác nhau** trong bag_demo_orders, rồi so sánh với **COUNT(*)**.
3. Thống kê số đơn của mỗi khách hàng và chỉ giữ những khách có **ít nhất hai đơn**.
4. JOIN bag_demo_orders với bag_demo_order_items rồi giải thích vì sao **COUNT(*) = 8** nhưng **COUNT(DISTINCT order_id) = 7**.
5. Tính tổng **amount** của các đơn bằng hai cách: trực tiếp từ bag_demo_orders và từ JOIN với bag_demo_order_items. Giải thích vì sao có chênh lệch.
6. Tạo một danh sách customer_id của đơn paid và một danh sách của đơn có amount >= 100000. Dùng UNION ALL rồi UNION và giải thích vì sao số hàng thay đổi.
7. Từ bag_demo_tags, so sánh số hàng trả về bởi **SELECT tag** và **SELECT DISTINCT tag**. Chú ý hai hàng NULL.
8. Lấy **một đơn có số tiền cao nhất cho mỗi khách**, nếu hòa thì ưu tiên order_id lớn hơn. So sánh kết quả của ROW_NUMBER() với cú pháp DISTINCT ON trong PostgreSQL.
9. Viết truy vấn trả về **mỗi customer_id một lần**, xếp theo **tổng amount của khách giảm dần**. Giải thích vì sao dùng GROUP BY và SUM phù hợp.

### Ghi nhớ để áp dụng

Trong SQL, một hàng xuất hiện nhiều lần có thể mang ý nghĩa nghiệp vụ thật: nhiều đơn của cùng khách, nhiều sản phẩm trong cùng đơn, hoặc nhiều giao dịch trùng số tiền. **SELECT mặc định giữ bội số; DISTINCT đưa mỗi hàng kết quả khác nhau về một lần; GROUP BY tổng hợp theo khóa nhóm; JOIN tạo một lần xuất hiện cho mỗi cặp khớp; UNION ALL cộng các lần xuất hiện còn UNION mặc định loại trùng.** Chỉ khi xác định rõ đơn vị dữ liệu và mục tiêu truy vấn, bạn mới biết lúc nào nên giữ bản sao và lúc nào cần loại chúng.
