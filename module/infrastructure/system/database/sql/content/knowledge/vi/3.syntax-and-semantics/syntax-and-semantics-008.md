# Thứ tự xử lý logic của SELECT và sự khác biệt với kế hoạch thực thi

Một câu truy vấn SQL thường được **viết** bắt đầu bằng SELECT, nhưng để hiểu kết quả, người học cần hình dung dữ liệu được **xử lý về mặt logic** theo thứ tự khác: xác định nguồn dữ liệu, kết hợp bảng, lọc dòng, nhóm, lọc nhóm, tính các biểu thức đầu ra, loại trùng, sắp xếp rồi giới hạn kết quả. Khi thực sự chạy câu SQL, hệ quản trị cơ sở dữ liệu (DBMS) còn có quyền lựa chọn **kế hoạch thực thi vật lý** khác với trình tự minh họa ấy để tiết kiệm CPU, I/O, bộ nhớ và thời gian chờ.

Ba góc nhìn cần tách biệt ngay từ đầu:

| Góc nhìn | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| **Thứ tự cú pháp** | Người lập trình viết các mệnh đề theo thứ tự nào? | SELECT → FROM → WHERE → GROUP BY → HAVING → ORDER BY → LIMIT |
| **Thứ tự xử lý logic** | Mỗi mệnh đề tác động lên tập dữ liệu nào để quyết định kết quả? | FROM/JOIN → WHERE → GROUP BY → HAVING → SELECT → DISTINCT → ORDER BY → LIMIT |
| **Kế hoạch thực thi vật lý** | DBMS thực sự đọc, lọc, nối, tổng hợp và sắp xếp bằng thuật toán nào? | Index Scan → Hash Join → HashAggregate → Sort → Limit, hoặc kế hoạch khác |

**Điểm cốt lõi:** thứ tự xử lý logic là **mô hình giải thích ý nghĩa câu truy vấn**, không phải cam kết DBMS sẽ đọc từng dòng hoặc tính từng biểu thức đúng theo một chuỗi bước cố định. Những phép biến đổi của bộ tối ưu phải bảo toàn ngữ nghĩa SQL, ngoại trừ những phần mà câu truy vấn vốn không quy định, chẳng hạn thứ tự trả về khi thiếu ORDER BY.

Ví dụ trong bài dùng cú pháp **PostgreSQL**. SQL có chuẩn chung nhưng khác biệt giữa PostgreSQL, MySQL, SQL Server, Oracle và các hệ khác có thể xuất hiện ở LIMIT/FETCH/TOP, tên cột được phép dùng trong GROUP BY/HAVING, hàm cửa sổ, cách hiện kế hoạch và quy tắc sắp xếp NULL.

## 1. Vì sao không thể suy luận từ thứ tự viết câu SQL?

Xem câu lệnh:

~~~sql
SELECT customer_id, COUNT(*) AS number_of_orders
FROM orders
WHERE status = 'PAID'
GROUP BY customer_id
HAVING COUNT(*) >= 2
ORDER BY number_of_orders DESC;
~~~

Nếu xử lý SELECT theo đúng thứ tự xuất hiện trong văn bản thì **COUNT(*)** sẽ được tính trước khi biết bảng nào là nguồn dữ liệu, bản ghi nào có status = 'PAID', hoặc các dòng được chia thành nhóm customer_id ra sao. Cách hiểu đó không khả thi.

Thay vào đó, nên diễn giải:

1. **FROM** chỉ định tập bản ghi của orders.
2. **WHERE** chỉ giữ bản ghi có trạng thái PAID.
3. **GROUP BY** chia các bản ghi đã lọc theo customer_id.
4. **HAVING** chỉ giữ những nhóm có ít nhất hai dòng.
5. **SELECT** tạo hai cột kết quả: customer_id và số lượng đơn.
6. **ORDER BY** sắp xếp các hàng kết quả theo số lượng giảm dần.

Từ đây dễ giải thích vì sao **WHERE COUNT(*) >= 2** không hợp lệ trong cùng khối SELECT: WHERE lọc *dòng trước khi nhóm*, còn COUNT(*) ở đây là kết quả tổng hợp của *nhóm*.

## 2. Sơ đồ thứ tự xử lý logic phổ biến

Một câu truy vấn điển hình:

~~~sql
WITH candidate_orders AS (...)
SELECT DISTINCT expression_1, expression_2, ...
FROM source_a
JOIN source_b ON join_condition
WHERE row_condition
GROUP BY grouping_expression
HAVING group_condition
ORDER BY sort_expression
OFFSET 10 ROWS
FETCH NEXT 20 ROWS ONLY;
~~~

Với các mệnh đề liên quan, có thể học theo mô hình sau:

~~~mermaid
flowchart TD
    A["WITH: đặt tên truy vấn phụ, nếu có"] --> B["FROM: tạo nguồn hàng"]
    B --> C["JOIN / ON: kết hợp và xác định hàng khớp"]
    C --> D["WHERE: lọc từng hàng"]
    D --> E["GROUP BY: tạo nhóm, tính tổng hợp khi cần"]
    E --> F["HAVING: lọc nhóm"]
    F --> G["Biểu thức SELECT và hàm cửa sổ: tạo cột kết quả"]
    G --> H["DISTINCT: loại hàng kết quả trùng"]
    H --> I["ORDER BY: sắp thứ tự kết quả"]
    I --> J["OFFSET / FETCH / LIMIT: chọn số hàng trả về"]
~~~

| Giai đoạn logic | Đối tượng thao tác | Kết quả chính |
| --- | --- | --- |
| **WITH**, nếu có | Định nghĩa các tên truy vấn phụ (CTE) | Cung cấp nguồn dữ liệu có thể được tham chiếu; không bảo đảm được materialize thành bảng trung gian |
| **FROM / JOIN / ON** | Nguồn hàng và điều kiện ghép | Tập hàng sau phép kết hợp; LEFT/RIGHT/FULL JOIN có quy tắc bù hàng không khớp |
| **WHERE** | Từng hàng sau FROM/JOIN | Loại hàng có điều kiện không phải TRUE |
| **GROUP BY** | Các hàng còn lại | Phân thành nhóm; các hàm tổng hợp làm việc trên nhóm |
| **HAVING** | Từng nhóm sau GROUP BY | Loại nhóm không thỏa điều kiện |
| **SELECT**, bao gồm xử lý hàm cửa sổ khi có | Các hàng/nhóm còn lại | Tính giá trị biểu thức và chọn các cột đầu ra |
| **DISTINCT**, nếu có | Các hàng đầu ra | Loại bản ghi đầu ra trùng nhau |
| **ORDER BY**, nếu có | Các hàng kết quả | Xác định thứ tự đầu ra theo khóa sắp xếp |
| **OFFSET / FETCH / LIMIT**, nếu có | Kết quả theo thứ tự đã xác định | Bỏ qua hoặc lấy số hàng yêu cầu |

Đây là **mô hình học tập giản lược cho một khối SELECT**. Trong câu lệnh thực, có thể có subquery, tập hợp bằng UNION/INTERSECT/EXCEPT, LATERAL, DISTINCT ON, GROUPING SETS hoặc các mở rộng riêng của DBMS. Chúng tạo thêm tầng ngữ nghĩa. Hàm tổng hợp và hàm cửa sổ cũng không được hiểu là mọi biểu thức luôn tính tuần tự đúng vị trí trong sơ đồ: bộ tối ưu có thể dời, gộp hoặc loại bỏ phép tính nếu phép biến đổi hợp lệ.

Một số tài liệu đặt **WINDOW** thành giai đoạn riêng giữa HAVING và SELECT. Cách diễn giải tương thích là: **hàm cửa sổ nhìn thấy tập hàng sau WHERE/GROUP BY/HAVING và được tính trước DISTINCT, ORDER BY ngoài cùng, LIMIT**; giá trị của hàm cửa sổ được đưa vào biểu thức SELECT hoặc ORDER BY theo quy tắc của hệ quản trị.

## 3. Ví dụ xuyên suốt với dữ liệu thực hành

Giả sử có ba khách hàng và bảy đơn hàng. Để có ví dụ tự chứa, có thể tạo hai bảng tạm trong một phiên PostgreSQL:

~~~sql
CREATE TEMP TABLE demo_customers (
    customer_id INTEGER PRIMARY KEY,
    customer_name TEXT NOT NULL
);

CREATE TEMP TABLE demo_orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES demo_customers(customer_id),
    status TEXT NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL,
    created_at DATE NOT NULL
);

INSERT INTO demo_customers (customer_id, customer_name)
VALUES
    (1, 'An'),
    (2, 'Binh'),
    (3, 'Chi');

INSERT INTO demo_orders
    (order_id, customer_id, status, total_amount, created_at)
VALUES
    (101, 1, 'PAID',     200.00, DATE '2026-03-01'),
    (102, 1, 'PAID',     150.00, DATE '2026-03-02'),
    (103, 1, 'CANCELED', 900.00, DATE '2026-03-03'),
    (104, 2, 'PAID',     300.00, DATE '2026-03-04'),
    (105, 2, 'PAID',      75.00, DATE '2026-03-05'),
    (106, 3, 'PAID',     120.00, DATE '2026-03-06'),
    (107, 2, 'PENDING',   50.00, DATE '2026-03-07');
~~~

Bài toán: **tìm khách hàng có ít nhất hai đơn đã thanh toán từ ngày 01/03/2026, xếp theo tổng doanh thu giảm dần và chỉ lấy khách hàng đứng đầu**.

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(*) AS paid_order_count,
    SUM(o.total_amount) AS revenue
FROM demo_customers AS c
INNER JOIN demo_orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
  AND o.created_at >= DATE '2026-03-01'
GROUP BY c.customer_id, c.customer_name
HAVING COUNT(*) >= 2
ORDER BY revenue DESC, c.customer_id ASC
LIMIT 1;
~~~

### 3.1. Theo dấu các hàng qua từng giai đoạn

**Bước 1 — FROM + INNER JOIN + ON.** Mỗi đơn khớp với khách hàng của nó qua customer_id. Có 7 hàng kết hợp, vẫn bao gồm CANCELED và PENDING. INNER JOIN chỉ giữ các cặp có điều kiện ON là TRUE.

**Bước 2 — WHERE.** Điều kiện o.status = 'PAID' và ngưỡng ngày lọc còn 5 hàng: 101, 102, 104, 105, 106. Đơn 103 và 107 bị loại trước khi đếm và tính tổng.

**Bước 3 — GROUP BY.** Năm hàng được gom thành ba nhóm:

| Khách hàng | Các đơn PAID thuộc nhóm | COUNT(*) | SUM(total_amount) |
| --- | --- | ---: | ---: |
| An | 101, 102 | 2 | 350.00 |
| Binh | 104, 105 | 2 | 375.00 |
| Chi | 106 | 1 | 120.00 |

**Bước 4 — HAVING.** Điều kiện COUNT(*) >= 2 giữ An và Binh, loại Chi.

**Bước 5 — SELECT.** Kết quả được trình bày dưới các tên cột customer_id, customer_name, paid_order_count và revenue. Phép tổng hợp SUM áp dụng cho các nhóm sau WHERE.

**Bước 6 — ORDER BY.** Binh có doanh thu 375.00 đứng trước An 350.00. Tiêu chí thứ hai customer_id ASC giúp xác định thứ tự nếu doanh thu bằng nhau.

**Bước 7 — LIMIT.** Chỉ còn một hàng:

| customer_id | customer_name | paid_order_count | revenue |
| ---: | --- | ---: | ---: |
| 2 | Binh | 2 | 375.00 |

Một điểm quan trọng: thứ tự trên là cách **chứng minh vì sao kết quả đúng**. Không thể từ ví dụ này kết luận DBMS bắt buộc phải tạo đủ 7 hàng JOIN rồi mới bắt đầu lọc status trong lúc chạy.

## 4. FROM, JOIN, ON và WHERE: giống nhau ở đâu, khác nhau ở đâu?

FROM hình thành tập đầu vào. JOIN xác định cách kết hợp các nguồn; ON mô tả điều kiện ghép. WHERE lọc những hàng đã hình thành sau phép JOIN.

Với **INNER JOIN**, điều kiện trên bảng bên phải có thể thường xuyên được chuyển tương đương giữa ON và WHERE. Với **OUTER JOIN**, điều đó có thể thay đổi kết quả, vì OUTER JOIN sinh thêm những hàng chứa NULL cho bên không khớp.

Giả sử muốn hiển thị **mọi khách hàng**, kể cả khách chưa có đơn PAID.

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS paid_order_count
FROM demo_customers AS c
LEFT JOIN demo_orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
~~~

Điều kiện status nằm trong **ON**: những khách không có đơn PAID vẫn xuất hiện, nhưng các cột của o nhận NULL. COUNT(o.order_id) đếm giá trị khác NULL, nên kết quả bằng 0 cho khách không có đơn phù hợp. **COUNT(*)** trong trường hợp này có thể trả về 1 vì hàng được bù bằng NULL vẫn là một hàng kết quả của LEFT JOIN.

Nếu thay bằng:

~~~sql
FROM demo_customers AS c
LEFT JOIN demo_orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
~~~

WHERE loại hàng mà o.status là NULL (biểu thức so sánh cho kết quả UNKNOWN). Khách không có đơn PAID sẽ biến mất khỏi kết quả, làm mất tác dụng giữ mọi khách của LEFT JOIN cho yêu cầu này.

Trong dữ liệu demo cả ba khách đều có đơn PAID, nên để quan sát khác biệt rõ ràng có thể xét thêm khách thứ tư không có đơn hàng. Khi đó cách đặt điều kiện trong ON và WHERE tạo kết quả khác nhau ngay cả khi phần SELECT và GROUP BY giữ nguyên.

### 4.1. Bộ lọc SQL có ba trạng thái logic

Trong SQL, điều kiện có thể là **TRUE**, **FALSE** hoặc **UNKNOWN** (thường phát sinh từ NULL). WHERE và HAVING chỉ giữ hàng/nhóm khi điều kiện là TRUE.

~~~sql
-- Không đúng cách để tìm giá trị NULL:
WHERE some_column = NULL

-- Đúng:
WHERE some_column IS NULL
~~~

Biểu thức NULL = NULL không cho TRUE mà cho UNKNOWN. Khi lý giải JOIN, WHERE và HAVING, bỏ qua logic ba giá trị sẽ dễ dẫn đến sai số lượng bản ghi.

## 5. WHERE, GROUP BY và HAVING: dòng trước, nhóm sau

Ba mệnh đề này giải quyết ba nhiệm vụ riêng:

| Mệnh đề | Tác dụng | Có thể tham chiếu COUNT/SUM của nhóm hiện tại? |
| --- | --- | --- |
| WHERE | Chọn hàng nguồn đủ điều kiện để đưa vào nhóm | Không |
| GROUP BY | Định nghĩa các khóa chia nhóm | Đang hình thành nhóm |
| HAVING | Chọn nhóm thỏa điều kiện, thường dựa trên tổng hợp | Có |

Ví dụ:

~~~sql
SELECT customer_id, SUM(total_amount) AS paid_revenue
FROM demo_orders
WHERE status = 'PAID'
GROUP BY customer_id
HAVING SUM(total_amount) >= 300;
~~~

WHERE loại đơn chưa thanh toán trước khi tính doanh thu. HAVING chỉ giữ những **khách có tổng tiền đã thanh toán ít nhất 300**.

Phản ví dụ:

~~~sql
-- Sai ngữ nghĩa và không hợp lệ trong cùng khối SELECT:
SELECT customer_id, COUNT(*)
FROM demo_orders
WHERE COUNT(*) >= 2
GROUP BY customer_id;
~~~

Đổi COUNT(*) sang HAVING mới phù hợp:

~~~sql
SELECT customer_id, COUNT(*) AS order_count
FROM demo_orders
GROUP BY customer_id
HAVING COUNT(*) >= 2;
~~~

Điều kiện chỉ phụ thuộc hàng nguồn, như status = 'PAID', thường nên được ghi rõ trong WHERE để ý định lọc trước nhóm được thể hiện trực tiếp. Đối với điều kiện trên tổng hợp, HAVING là nơi phù hợp. Bộ tối ưu đôi khi có thể đẩy điều kiện từ HAVING xuống bước lọc sớm khi chứng minh được tương đương, nhưng người viết SQL không nên dựa vào giả định này để hiểu kết quả.

### 5.1. Sau GROUP BY, không phải cột nào cũng có thể SELECT tùy ý

Trong truy vấn tổng hợp, một cột nguồn muốn xuất hiện ở kết quả thường phải:

- Nằm trong khóa GROUP BY;
- Hoặc nằm trong hàm tổng hợp như COUNT, SUM, MIN, MAX;
- Hoặc được DBMS chấp nhận vì có phụ thuộc hàm đã được chứng minh từ khóa nhóm (khả năng và luật cụ thể tùy DBMS).

~~~sql
-- Không hợp lệ theo cách hiểu tổng hợp thông thường:
SELECT customer_id, order_id, COUNT(*)
FROM demo_orders
GROUP BY customer_id;
~~~

Mỗi khách có nhiều order_id; SQL không có căn cứ chọn order_id nào làm đại diện. Có thể GROUP BY thêm order_id nếu cần mỗi đơn một nhóm, hoặc chọn MIN(order_id)/MAX(order_id) nếu đúng ý định nghiệp vụ.

Khi không có GROUP BY nhưng có hàm tổng hợp trong SELECT, toàn bộ tập dòng sau WHERE có thể được coi là **một nhóm duy nhất**. Hàm COUNT(*) đếm 0 nếu không có hàng; SUM trên tập không có giá trị hợp lệ thường trả NULL, vì vậy cần hiểu khác biệt giữa COUNT và SUM.

### 5.2. JOIN trước GROUP BY có thể nhân bản số liệu

Nếu JOIN orders với các dòng order_items rồi tính SUM(orders.total_amount), mỗi đơn có nhiều dòng hàng có thể bị cộng lặp. Đây là lỗi ngữ nghĩa do số hàng sau JOIN tăng, không phải lỗi của hàm SUM.

Nguyên tắc xử lý là xác định đúng **độ hạt dữ liệu** (một hàng đại diện cho đơn, dòng hàng hay khách hàng) trước khi tổng hợp. Có thể tổng hợp bảng con về cùng độ hạt trước khi JOIN, hoặc tổng hợp ở bảng nguồn phù hợp; dùng DISTINCT tùy tiện để chữa số tổng thường che lấp lỗi mô hình.

## 6. SELECT, bí danh và phạm vi tham chiếu

SELECT tạo ra các cột đầu ra và có thể đặt tên bằng **AS**:

~~~sql
SELECT
    customer_id,
    total_amount * 1.10 AS amount_with_fee
FROM demo_orders;
~~~

Vì WHERE được hiểu trước bước tạo bí danh SELECT, cách viết dưới đây không được PostgreSQL cho phép:

~~~sql
-- Không dùng alias của SELECT trong WHERE cùng mức:
SELECT
    total_amount * 1.10 AS amount_with_fee
FROM demo_orders
WHERE amount_with_fee >= 300;
~~~

Có thể viết lại biểu thức hoặc dùng truy vấn con:

~~~sql
SELECT x.order_id, x.amount_with_fee
FROM (
    SELECT
        order_id,
        total_amount * 1.10 AS amount_with_fee
    FROM demo_orders
) AS x
WHERE x.amount_with_fee >= 300;
~~~

Trong PostgreSQL, **ORDER BY** có thể sử dụng bí danh đầu ra:

~~~sql
SELECT
    customer_id,
    SUM(total_amount) AS revenue
FROM demo_orders
GROUP BY customer_id
ORDER BY revenue DESC;
~~~

Việc dùng bí danh SELECT trong GROUP BY và HAVING có sự khác biệt đáng kể giữa các DBMS; một số hệ cho phép một số dạng tham chiếu, một số hệ hạn chế. Để viết SQL dễ chuyển đổi, nên tham chiếu rõ cột nguồn hoặc lặp biểu thức tổng hợp ở HAVING:

~~~sql
HAVING SUM(total_amount) >= 300
~~~

Thứ tự logic cũng không phải lời hứa rằng biểu thức SELECT được tính **đúng một lần**, hay mọi toán tử AND/OR được thực thi theo thứ tự văn bản. Bộ tối ưu có thể biến đổi biểu thức, tối giản điều kiện hoặc tính ở bước khác khi hợp lệ. Nếu cần tránh phép chia cho 0, hãy viết xử lý dữ liệu bất hợp lệ trực tiếp, chẳng hạn dùng NULLIF(denominator, 0), thay vì dựa vào “điều kiện bên trái chắc chắn chạy trước”.

## 7. Hàm cửa sổ (window functions) nằm ở đâu?

Hàm tổng hợp như SUM với GROUP BY **gộp nhiều hàng thành ít hàng hơn**. Ngược lại, hàm cửa sổ như ROW_NUMBER, RANK, SUM(...) OVER (...) có thể tính trên một cửa sổ hàng mà vẫn **giữ mỗi hàng nguồn**.

Ví dụ tìm đơn PAID mới nhất của **mỗi khách hàng**:

~~~sql
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        total_amount,
        created_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY created_at DESC, order_id DESC
        ) AS rn
    FROM demo_orders
    WHERE status = 'PAID'
)
SELECT
    order_id,
    customer_id,
    total_amount,
    created_at
FROM ranked_orders
WHERE rn = 1
ORDER BY customer_id;
~~~

Ở khối SELECT bên trong:

1. WHERE chỉ giữ đơn PAID.
2. ROW_NUMBER đánh số hàng trong từng customer_id theo ngày giảm dần rồi order_id giảm dần.
3. SELECT đưa giá trị rn vào tập kết quả của CTE.

Ở **khối SELECT bên ngoài**, rn đã là một cột từ nguồn ranked_orders nên WHERE rn = 1 là hợp lệ. Không thể đưa WHERE rn = 1 vào cùng khối nơi ROW_NUMBER được tính, bởi WHERE chạy trước giai đoạn hàm cửa sổ và chưa thấy rn.

Một số DBMS có mệnh đề **QUALIFY** để lọc trên kết quả hàm cửa sổ sau khi chúng được tính. PostgreSQL không hỗ trợ QUALIFY như một mệnh đề SELECT phổ thông; CTE/truy vấn con là cách diễn đạt thông dụng ở PostgreSQL.

Hàm cửa sổ cũng có thể chạy trên **kết quả đã nhóm**. Ví dụ:

~~~sql
SELECT
    customer_id,
    SUM(total_amount) AS revenue,
    RANK() OVER (
        ORDER BY SUM(total_amount) DESC
    ) AS revenue_rank
FROM demo_orders
WHERE status = 'PAID'
GROUP BY customer_id
ORDER BY revenue_rank, customer_id;
~~~

Ở đây mỗi khách đã được gom thành một hàng doanh thu; RANK xếp hạng **các nhóm**, không đánh số bảy đơn hàng ban đầu.

**ORDER BY trong OVER** chỉ định thứ tự phục vụ hàm cửa sổ. Nó không bảo đảm thứ tự hiển thị cuối cùng. Muốn có thứ tự trả về xác định, vẫn cần **ORDER BY ngoài cùng**.

## 8. DISTINCT, ORDER BY và LIMIT/FETCH

### 8.1. DISTINCT loại trùng sau khi tạo cột kết quả

~~~sql
SELECT DISTINCT status
FROM demo_orders;
~~~

Kết quả có mỗi giá trị status duy nhất một lần. DISTINCT xét hàng đầu ra theo các biểu thức SELECT, không tự hiểu “mỗi khách chọn một đơn gần nhất”.

Khi SELECT DISTINCT nhiều cột, một hàng chỉ bị xem là trùng nếu **toàn bộ tổ hợp cột đầu ra** trùng theo quy tắc DISTINCT. Câu sau không bảo đảm chỉ một hàng cho mỗi khách:

~~~sql
SELECT DISTINCT customer_id, order_id
FROM demo_orders;
~~~

Vì order_id đã duy nhất, không có dòng nào bị loại. PostgreSQL có DISTINCT ON để chọn một hàng theo khóa, nhưng đây là tính năng riêng, cần ORDER BY phù hợp; không nên nhầm nó với DISTINCT chuẩn.

### 8.2. ORDER BY phải ở đúng cấp truy vấn cần sắp xếp

~~~sql
SELECT order_id, created_at
FROM demo_orders
ORDER BY created_at DESC, order_id DESC;
~~~

Đây là cách quy định thứ tự kết quả. Nếu **không có ORDER BY ngoài cùng**, DBMS có thể trả hàng theo bất kỳ thứ tự nào; thứ tự quan sát được từ một lần chạy hoặc từ khóa chính không phải cam kết.

Không được suy ra rằng ORDER BY trong CTE, view hoặc subquery luôn bảo toàn thứ tự của truy vấn cha. ORDER BY ở truy vấn con có thể cần để xác định những hàng được LIMIT/FETCH hoặc để tính hàm cửa sổ, nhưng chỉ **ORDER BY ở khối ngoài cùng** mới điều khiển thứ tự trả về cuối cùng.

Khi nhiều hàng bằng nhau theo toàn bộ khóa ORDER BY, thứ tự giữa các hàng ấy không xác định. Nếu phân trang hoặc lấy hàng đầu, thêm **khóa phụ duy nhất** (như order_id) để tránh kết quả thay đổi khi có các giá trị created_at giống nhau.

### 8.3. LIMIT không có ORDER BY không có nghĩa “những hàng đầu tiên”

~~~sql
-- Không xác định rõ ba đơn nào sẽ được lấy:
SELECT order_id
FROM demo_orders
LIMIT 3;

-- Xác định ba đơn mới nhất:
SELECT order_id
FROM demo_orders
ORDER BY created_at DESC, order_id DESC
LIMIT 3;
~~~

Trong mô hình logic, LIMIT/FETCH được áp dụng sau khi xác định thứ tự. Bộ tối ưu có thể sử dụng chỉ mục theo thứ tự mong muốn và **dừng sớm** khi đủ ba hàng, không cần sắp xếp toàn bộ tập kết quả.

OFFSET bỏ qua một số hàng đã sắp xếp rồi mới trả kết quả. OFFSET lớn có thể làm DBMS phải đi qua rất nhiều hàng; với phân trang sâu, **keyset pagination** dựa trên khóa sắp xếp và bản ghi cuối của trang trước thường là lựa chọn cần xem xét.

LIMIT là cú pháp phổ biến của PostgreSQL/MySQL. Chuẩn SQL sử dụng **OFFSET ... ROWS FETCH FIRST/NEXT ... ROWS ONLY**; SQL Server còn có TOP và OFFSET/FETCH với quy tắc riêng. Với FETCH ... WITH TIES ở những hệ hỗ trợ, số hàng trả về có thể nhiều hơn giới hạn để giữ các hàng đồng hạng.

## 9. Thứ tự logic không phải kế hoạch thực thi vật lý

Trở lại truy vấn doanh thu trong mục 3. Về ngữ nghĩa, nó JOIN rồi WHERE, GROUP BY, HAVING, ORDER BY, LIMIT. Nhưng PostgreSQL có thể chọn cách:

- Quét **demo_orders** và áp dụng bộ lọc PAID/ngày ngay trong khi đọc, trước khi thực hiện JOIN;
- Sử dụng chỉ mục để lấy đúng những hàng có khả năng thỏa điều kiện;
- Dùng **Hash Join**, **Nested Loop** hoặc **Merge Join** tùy kích thước, phân bố dữ liệu và chỉ mục;
- Dùng **HashAggregate** hoặc **GroupAggregate** để gom nhóm;
- Tận dụng đầu vào đã có thứ tự hoặc thực hiện **Sort**;
- Chọn thuật toán **top-N** để lấy ít hàng mà không phải lưu toàn bộ kết quả đã sắp xếp;
- Thực thi một số thao tác theo lô hoặc song song nếu hệ và kế hoạch hỗ trợ.

Đây là quyền lựa chọn của **query planner/optimizer**. Các thuật toán thay đổi cách thực hiện mà không được làm sai quy tắc kết quả của câu SQL.

### 9.1. Một cây kế hoạch minh họa

Cây sau chỉ là **mô phỏng các kiểu toán tử có thể gặp**, không phải đầu ra EXPLAIN đã đo trên dữ liệu demo:

~~~text
Limit
  Sort (revenue DESC, customer_id ASC)
    HashAggregate (GROUP BY customer_id, customer_name)
      Filter ở mức aggregate (COUNT(*) >= 2)
        Hash Join (orders.customer_id = customers.customer_id)
          Scan demo_orders (lọc status, created_at)
          Scan demo_customers
~~~

Trong kế hoạch PostgreSQL thực tế, bộ lọc HAVING có thể xuất hiện là thuộc tính **Filter** của node Aggregate, chứ không nhất thiết là node con riêng biệt. Trật tự trình bày các node ở trên dùng để giúp nhìn từ toán tử trên cùng xuống các thao tác cung cấp dữ liệu bên dưới.

Khi đọc cây kế hoạch dạng văn bản, các toán tử **con cung cấp dữ liệu cho toán tử cha**, nhưng không thể hiểu đơn giản rằng mỗi node con phải chạy xong 100% rồi cha mới bắt đầu. Nhiều toán tử có thể trả hàng theo dòng (pipelining), trong khi Sort hoặc một số kiểu Aggregate có thể cần tích lũy thêm dữ liệu trước khi xuất hàng. Hash Join có thể xây dựng bảng băm ở một phía rồi dò từ phía kia. Kế hoạch thực tế có thể khác hoàn toàn cây minh họa.

### 9.2. Quan hệ giữa mệnh đề logic và toán tử thực thi

| Ý nghĩa logic | Các cách thực thi có thể gặp trong PostgreSQL | Điều cần chú ý |
| --- | --- | --- |
| FROM | Seq Scan, Index Scan, Index Only Scan, Bitmap Heap Scan | Cách đọc bảng tùy số hàng cần lấy và đặc tính dữ liệu |
| JOIN/ON | Nested Loop, Hash Join, Merge Join | Một phép JOIN logic có nhiều thuật toán |
| WHERE | Filter tại Scan, Index Cond, điều kiện tại JOIN | Điều kiện có thể được đẩy xuống để giảm số hàng từ sớm |
| GROUP BY và hàm tổng hợp | HashAggregate, GroupAggregate, Partial/Finalize Aggregate | Có thể tổng hợp theo hash, theo dữ liệu đã sắp, hoặc xử lý song song |
| HAVING | Filter tại node Aggregate | Nhóm bị loại sau khi có kết quả tổng hợp cần thiết |
| SELECT | Projection trong nhiều node, Result khi thích hợp | Không bắt buộc có một node SELECT tương ứng |
| DISTINCT | Unique, HashAggregate hoặc toán tử tương đương | Có thể khai thác tính duy nhất có sẵn |
| ORDER BY | Sort, Incremental Sort, hoặc đường truy cập đã có thứ tự | Không phải truy vấn có ORDER BY nào cũng cần một node Sort |
| LIMIT/FETCH | Limit, top-N khi phù hợp | Có thể dừng đọc sớm nếu kế hoạch cho phép |

Các tên toán tử ở bảng là ví dụ cụ thể của PostgreSQL, không phải cấu trúc chung bắt buộc cho mọi DBMS.

### 9.3. Các biến đổi tối ưu hợp lệ

**Đẩy bộ lọc xuống gần nguồn dữ liệu (predicate pushdown).** Điều kiện o.status = 'PAID' trong WHERE của INNER JOIN có thể được áp dụng ngay khi quét demo_orders, tránh chuyển nhiều hàng thừa qua JOIN.

**Đổi thứ tự nối bảng (join reordering).** Với nhiều INNER JOIN, DBMS thường có thể ghép các bảng theo thứ tự ít tốn kém hơn thứ tự người viết đặt trong FROM. Tuy nhiên, các ràng buộc do OUTER JOIN, LATERAL, phụ thuộc tương quan hoặc biểu thức đặc biệt có thể giới hạn việc đổi thứ tự.

**Cắt bớt cột (projection pruning).** Nếu kết quả chỉ cần customer_id và SUM(total_amount), DBMS có thể tránh mang theo nhiều cột không cần thiết.

**Gộp hoặc bỏ toán tử dư thừa.** Khi có khóa duy nhất hoặc ràng buộc hỗ trợ, optimizer có thể nhận ra DISTINCT, SORT hoặc JOIN nào không cần thiết cho kết quả.

**Gộp/hiện thực hóa CTE.** WITH tạo tên cho truy vấn phụ, không đồng nghĩa luôn chạy riêng và lưu toàn bộ kết quả; PostgreSQL có các quy tắc về inlining/materialization tùy tính chất CTE, số lần tham chiếu và chỉ dẫn MATERIALIZED/NOT MATERIALIZED. Quy tắc chi tiết khác nhau theo hệ và phiên bản.

**Tối ưu ORDER BY + LIMIT.** Nếu có chỉ mục phù hợp, DBMS có thể đọc theo thứ tự và lấy đủ N hàng; nếu không, nó có thể dùng sort hoặc top-N. Tuy nhiên, khi có GROUP BY và SUM, DBMS vẫn phải tính những nhóm có khả năng ảnh hưởng đến thứ hạng trừ khi có phép biến đổi khác đã chứng minh an toàn.

### 9.4. Những phép đổi chỗ sẽ làm sai kết quả

Người học thường nhầm rằng vì optimizer được “đổi thứ tự”, nên có thể tự hoán đổi các mệnh đề tùy ý. Không đúng.

| Thay đổi | Vì sao không tương đương? |
| --- | --- |
| Đưa LIMIT 1 vào trước ORDER BY revenue DESC | Có thể lấy bất kỳ khách nào trước khi tìm khách doanh thu cao nhất |
| Chuyển o.status = 'PAID' từ ON sang WHERE trong LEFT JOIN giữ mọi khách | Có thể loại khách không có đơn PAID |
| Đưa SUM(total_amount) >= 300 vào WHERE cùng khối | WHERE không lọc trên kết quả nhóm |
| Đẩy HAVING COUNT(*) >= 2 xuống một điều kiện từng hàng | Không có thông tin về số hàng của cả nhóm ở từng hàng riêng lẻ |
| Tính tổng đơn trước/sau JOIN với bảng dòng hàng mà không xét độ hạt | Có thể nhân bản số tiền đơn |
| Dùng DISTINCT để chọn “mỗi khách một đơn mới nhất” | DISTINCT không biết điều kiện “mới nhất” nếu không có logic xếp hạng/chọn hàng |

Optimizer chỉ được phép thực hiện phép biến đổi bảo toàn các tính chất có nghĩa của truy vấn. Khi dữ liệu có NULL, hàng trùng, OUTER JOIN, LIMIT hay thứ tự phụ thuộc, việc chứng minh tương đương cần đặc biệt cẩn trọng.

## 10. Dùng EXPLAIN để quan sát kế hoạch thực thi

Trong PostgreSQL, EXPLAIN hiển thị kế hoạch mà bộ tối ưu dự kiến dùng:

~~~sql
EXPLAIN
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(*) AS paid_order_count,
    SUM(o.total_amount) AS revenue
FROM demo_customers AS c
JOIN demo_orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
  AND o.created_at >= DATE '2026-03-01'
GROUP BY c.customer_id, c.customer_name
HAVING COUNT(*) >= 2
ORDER BY revenue DESC, c.customer_id
LIMIT 1;
~~~

EXPLAIN thông thường cho biết kế hoạch **ước lượng** mà không thực thi truy vấn SELECT đang giải thích. Trong PostgreSQL có thể dùng:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    customer_id,
    COUNT(*) AS paid_order_count
FROM demo_orders
WHERE status = 'PAID'
GROUP BY customer_id;
~~~

Với ANALYZE, PostgreSQL **thực sự chạy câu truy vấn** để thu thập thời gian và số hàng đã xử lý; BUFFERS cung cấp thêm thông tin truy cập bộ đệm và I/O liên quan. Hãy dùng trên môi trường và dữ liệu phù hợp. Nếu áp dụng EXPLAIN ANALYZE cho câu lệnh UPDATE/DELETE/INSERT, những thay đổi ấy cũng có thể được thực thi; không dùng tùy tiện trên dữ liệu thật. Ngay cả SELECT cũng có thể tiêu thụ tài nguyên hoặc kích hoạt những hàm có tác dụng phụ nếu truy vấn chứa chúng.

### 10.1. Đọc gì trong một kế hoạch?

Một số thuộc tính đáng quan tâm:

| Thuộc tính | Ý nghĩa khi phân tích |
| --- | --- |
| Node type | DBMS đã chọn cách quét bảng, nối, tổng hợp hay sắp xếp nào? |
| cost và estimated rows | Ước lượng chi phí và số dòng của planner; cost là đơn vị tương đối, không phải mili giây |
| actual time và actual rows | Số đo khi thực thi với ANALYZE |
| loops | Số lần node được chạy; nhiều vòng lặp có thể làm khuếch đại chi phí |
| Filter / Index Cond / Join Filter | Điều kiện được áp dụng ở đâu trong kế hoạch? |
| Rows Removed by Filter | Có bao nhiêu hàng không thỏa điều kiện tại node đó? |
| Buffers | Mức truy cập dữ liệu qua shared/local/temp buffers, giúp nhận diện áp lực bộ nhớ và I/O |
| Sort Method, Disk, Memory | Cách sắp xếp và dấu hiệu tràn xuống đĩa nếu được báo cáo |

Khi nhìn thấy Seq Scan, không nên kết luận ngay rằng “thiếu index”. Trên bảng rất nhỏ như dữ liệu demo, quét toàn bảng có thể là lựa chọn rẻ nhất. Chỉ mục cũng có thể không được dùng khi điều kiện không chọn lọc hoặc thống kê cho thấy chi phí dùng chỉ mục cao hơn.

**So sánh số dòng ước lượng với số dòng thực tế** là điểm khởi đầu quan trọng: chênh lệch lớn có thể khiến DBMS chọn loại JOIN, bộ nhớ cấp phát hoặc thứ tự xử lý không phù hợp. Cần xem thống kê, phân bố dữ liệu, mối tương quan giữa cột và giá trị tham số thực tế.

### 10.2. Vì sao cùng một câu SQL có thể có kế hoạch khác nhau?

- **Quy mô:** bảng 7 dòng và bảng 70 triệu dòng thường có chiến lược truy cập khác nhau.
- **Chỉ mục:** tạo hoặc xóa index làm thay đổi các đường truy cập khả dụng.
- **Thống kê:** dữ liệu mới nhập, phân bố lệch hoặc thống kê cũ có thể làm sai ước lượng.
- **Giá trị tham số:** lọc một customer_id rất hiếm khác với customer_id có hàng triệu đơn; kế hoạch chung và kế hoạch theo giá trị cụ thể có thể khác.
- **Điều kiện môi trường:** cấu hình planner, bộ nhớ, độ song song, loại lưu trữ, tải đồng thời và phiên bản DBMS.
- **Mục tiêu lấy dữ liệu:** LIMIT 10 khác với việc cần đọc toàn bộ kết quả; ORDER BY có hoặc không có thể làm đổi hướng chọn index.

Kế hoạch thực thi là sản phẩm của **câu truy vấn + schema/index + thống kê + tham số + cấu hình + điều kiện runtime**. Không có một “thứ tự thực thi cố định” chung cho mọi SQL SELECT.

## 11. Khi nào mô hình logic hữu ích, khi nào cần xem kế hoạch?

| Tình huống | Dùng thứ tự logic để kiểm tra | Dùng kế hoạch thực thi để kiểm tra |
| --- | --- | --- |
| Tổng doanh thu cao bất thường | JOIN có tạo dòng lặp trước SUM? WHERE đã lọc đúng status? | JOIN nào làm tăng số hàng, số dòng thực tế tại từng node? |
| Một khách hàng biến mất | Điều kiện WHERE có loại hàng bù NULL của LEFT JOIN? | Filter/Join Filter được đặt ở đâu, có bảo toàn ngữ nghĩa outer join? |
| Alias báo “không tồn tại” | Alias SELECT đã được dùng sai trong WHERE cùng khối? | Không cần EXPLAIN nếu truy vấn không phân tích cú pháp/ngữ nghĩa được |
| Trang lịch sử lúc đúng lúc sai | LIMIT có ORDER BY đủ khóa phân biệt? | Index hay sort nào được dùng, tải/đồng thời có ảnh hưởng tốc độ? |
| Truy vấn hợp lệ nhưng chậm | Có lọc trước khi nhóm? Có lấy thừa hàng/cột? | Scan, join, sort, aggregate, ước lượng sai, buffer/I/O và thời gian? |
| Một phép đếm có kết quả 1 thay vì 0 | COUNT(*) trên hàng NULL được bù bởi LEFT JOIN? | Kế hoạch chỉ giúp kiểm tra thao tác; nguyên nhân cốt lõi là ngữ nghĩa COUNT |

Một trình tự chẩn đoán hiệu quả là:

1. **Xác nhận câu hỏi nghiệp vụ:** muốn đếm đơn nào, nhóm theo chiều nào, có giữ bản ghi không khớp không?
2. **Diễn giải SQL bằng pipeline logic:** ghi lại tập hàng sau FROM/JOIN, WHERE, GROUP BY, HAVING, SELECT, DISTINCT và ORDER/LIMIT.
3. **Kiểm tra dữ liệu biên:** NULL, nhiều dòng con, giá trị sắp xếp trùng, nhóm không có hàng, khách hàng không khớp JOIN.
4. **Khi kết quả đã đúng, quan sát kế hoạch:** dùng EXPLAIN và số đo phù hợp với dữ liệu đại diện.
5. **Tối ưu có đo lường:** điều chỉnh truy vấn, chỉ mục, thống kê hoặc mô hình dữ liệu, rồi so sánh độ trễ và chi phí ghi/đọc thực tế.

## 12. Các tình huống luyện tập

### Tình huống A — Lọc trước hay sau khi nhóm?

Viết hai truy vấn trên demo_orders: (1) đếm số đơn PAID của mỗi khách; (2) tìm khách có từ hai đơn PAID trở lên. Hãy giải thích vì sao status = 'PAID' thuộc WHERE còn COUNT(*) >= 2 thuộc HAVING.

Gợi ý: câu đầu dùng WHERE + GROUP BY; câu sau thêm HAVING COUNT(*) >= 2. Không đưa COUNT(*) vào WHERE.

### Tình huống B — Khách chưa từng mua hàng

Thêm một khách hàng mới không có dòng nào trong demo_orders. So sánh hai câu LEFT JOIN: điều kiện status = 'PAID' nằm trong ON và trong WHERE. Hãy dự đoán khách mới có xuất hiện không, và vì sao COUNT(o.order_id) khác COUNT(*) khi hàng của bảng o được bù NULL.

### Tình huống C — Chọn đơn hàng mới nhất

Mỗi khách có nhiều đơn với created_at có thể trùng. Viết truy vấn lấy đúng một đơn PAID mới nhất cho mỗi khách. Phân biệt:

- ORDER BY trong ROW_NUMBER() OVER (...), dùng để xếp thứ tự trong từng nhóm khách;
- WHERE rn = 1 ở truy vấn ngoài;
- ORDER BY ngoài cùng, dùng để sắp xếp kết quả trả về.

### Tình huống D — SQL logic giống nhau, plan khác nhau

Giả sử demo_orders tăng lên 10 triệu dòng. Chạy truy vấn lấy 20 đơn gần nhất của một customer_id. Hãy đề xuất chỉ mục ứng viên và mô tả hai kế hoạch có thể có: quét rồi sắp xếp, hoặc quét chỉ mục theo điều kiện và thứ tự. Cần xem gì trong EXPLAIN (ANALYZE, BUFFERS) để quyết định?

Ví dụ chỉ mục ứng viên trong PostgreSQL:

~~~sql
CREATE INDEX idx_demo_orders_customer_created_id
ON demo_orders (customer_id, created_at DESC, order_id DESC);
~~~

Nên đánh giá với dữ liệu đủ lớn và phân bố đại diện. Việc có index không bảo đảm planner luôn chọn nó; index còn phát sinh chi phí lưu trữ và cập nhật.

### Tình huống E — Sai lầm với LIMIT

Hai truy vấn sau có cùng ý nghĩa không?

~~~sql
-- Truy vấn 1: lấy 10 đơn mới nhất toàn hệ thống.
SELECT order_id, created_at
FROM demo_orders
ORDER BY created_at DESC, order_id DESC
LIMIT 10;

-- Truy vấn 2: xác định tối đa 10 đơn trước khi sắp xếp chúng.
SELECT order_id, created_at
FROM (
    SELECT order_id, created_at
    FROM demo_orders
    LIMIT 10
) AS chosen_orders
ORDER BY created_at DESC, order_id DESC;
~~~

Không tương đương. Ở truy vấn 2, tập 10 dòng bên trong được chọn **không có ORDER BY**, nên không xác định 10 đơn mới nhất; ORDER BY ngoài chỉ sắp lại tập đã chọn. Đây là lỗi kết quả, không phải chỉ là khác biệt tốc độ.

## 13. Ghi nhớ để đọc và viết SELECT chính xác

Thứ tự viết quen thuộc là:

~~~sql
SELECT ...
FROM ...
JOIN ... ON ...
WHERE ...
GROUP BY ...
HAVING ...
ORDER BY ...
LIMIT ...;
~~~

Khi cần lý giải kết quả, hãy dùng mô hình:

~~~text
Nguồn và JOIN
    → lọc hàng (WHERE)
    → tạo nhóm và tổng hợp (GROUP BY)
    → lọc nhóm (HAVING)
    → biểu thức đầu ra và hàm cửa sổ (SELECT / OVER)
    → bỏ trùng đầu ra (DISTINCT)
    → sắp xếp (ORDER BY)
    → phân trang/giới hạn (OFFSET, FETCH, LIMIT)
~~~

Khi cần giải thích **vì sao truy vấn chạy nhanh hay chậm**, hãy chuyển sang kế hoạch thực thi cụ thể: scan, index, join algorithm, aggregate, sort, giới hạn, thống kê và số đo runtime.

**Hai cách nhìn bổ sung cho nhau:** thứ tự logic giúp bảo đảm câu truy vấn *trả đúng dữ liệu*, còn kế hoạch thực thi giúp hiểu DBMS *lấy được dữ liệu đó bằng cách nào và tốn bao nhiêu tài nguyên*. Người viết SQL vững ngữ nghĩa sẽ tránh được các lỗi WHERE/HAVING, LEFT JOIN, DISTINCT và LIMIT; người đọc được EXPLAIN sẽ biết cách kiểm chứng, tối ưu mà không làm thay đổi kết quả nghiệp vụ.
