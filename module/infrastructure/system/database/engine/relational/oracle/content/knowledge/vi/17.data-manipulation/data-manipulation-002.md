# INSERT ALL, INSERT FIRST và chèn có điều kiện trong Oracle Database

## 1. Khi một dòng nguồn cần được đưa vào nhiều bảng

Trong quy trình nạp dữ liệu, một dòng nguồn đôi khi phải tạo ra nhiều dòng đích hoặc được chuyển đến một trong nhiều bảng tùy theo điều kiện. Ví dụ:

- Một bản ghi người dùng được ghi vào bảng cha PEOPLE; nếu là bệnh nhân thì ghi thêm vào PATIENTS, nếu là nhân viên thì ghi thêm vào STAFF.
- Đơn hàng được phân loại vào bảng đơn nhỏ, vừa, lớn hoặc ưu tiên.
- Dữ liệu doanh số theo tuần có nhiều cột ngày được chuyển thành nhiều dòng doanh số theo ngày.
- Một giao dịch cần được ghi vào bảng lịch sử và bảng báo cáo.
- Dữ liệu staging cần được chia theo loại nghiệp vụ hoặc trạng thái.

Có thể viết nhiều câu INSERT ... SELECT, nhưng Oracle hỗ trợ **multitable insert** để phân phối các dòng của một truy vấn nguồn tới nhiều bảng:

- **INSERT ALL:** thực hiện tất cả nhánh INTO phù hợp cho mỗi dòng nguồn.
- **INSERT FIRST:** kiểm tra điều kiện theo thứ tự và chỉ thực hiện nhánh đầu tiên đúng cho mỗi dòng nguồn.
- **WHEN ... THEN:** xác định điều kiện chèn.
- **ELSE:** xác định nhánh mặc định khi không có điều kiện WHEN nào đúng.

Các câu lệnh này hữu ích cho ETL, staging, phân loại dữ liệu và chuyển đổi cấu trúc bảng. Bài học dùng cú pháp Oracle Database 19c.

> Các bảng *_LAB là ví dụ minh họa. Chỉ chạy DDL/DML trong schema lab được phép; kiểm tra bảng đích và transaction trước khi thực hiện.

## 2. Multitable INSERT hoạt động như thế nào?

Khác với một câu INSERT INTO ... SELECT thông thường chỉ ghi vào một bảng đích, multitable insert lấy từng dòng từ truy vấn nguồn rồi áp dụng các nhánh INTO.

~~~text
                    SELECT nguồn
                         |
             +-----------+-----------+
             |           |           |
           row 1       row 2       row 3
             |           |           |
        đánh giá các điều kiện / nhánh INTO
             |           |           |
       +-----+-----+     |       +---+---+
       |           |     |       |       |
     bảng A     bảng B  bảng B  bảng A  bảng C
~~~

Một dòng nguồn có thể được chèn vào một bảng, nhiều bảng, hoặc không bảng nào nếu không có nhánh phù hợp và không có ELSE. Một dòng nguồn cũng có thể được chèn nhiều lần vào cùng một bảng qua các nhánh INTO khác nhau.

Nếu truy vấn nguồn trả 100 dòng và câu lệnh có ba nhánh INTO không điều kiện, tổng số dòng chèn là 300.

~~~sql
-- Chèn vô điều kiện vào nhiều bảng.
INSERT ALL
    INTO target_a (id, value_a) VALUES (source_id, source_value)
    INTO target_b (id, value_b) VALUES (source_id, source_value)
SELECT id AS source_id,
       value AS source_value
FROM source_table;

-- Chèn có điều kiện.
INSERT ALL
    WHEN amount < 1000 THEN
        INTO small_orders (order_id, amount)
        VALUES (order_id, amount)
    WHEN amount >= 1000 THEN
        INTO large_orders (order_id, amount)
        VALUES (order_id, amount)
SELECT order_id, amount
FROM orders;
~~~

Nếu truy vấn nguồn không trả dòng nào, không có dòng nào được chèn.

## 3. INSERT ALL vô điều kiện

### 3.1. Cú pháp

~~~sql
INSERT ALL
    INTO table_a (column_a1, column_a2)
    VALUES (source_expr_1, source_expr_2)
    INTO table_b (column_b1, column_b2)
    VALUES (source_expr_1, source_expr_2)
SELECT source_expr_1, source_expr_2, ...
FROM source_table
WHERE ...;
~~~

ALL theo sau là nhiều nhánh INTO. Oracle thực hiện từng nhánh một lần cho mỗi dòng do truy vấn nguồn trả về.

### 3.2. Một bản ghi được ghi vào hai bảng

Giả sử hệ thống cần ghi đơn hàng vào cả bảng vận hành lẫn bảng audit:

~~~sql
INSERT ALL
    INTO orders_live (order_id, customer_id, order_total)
    VALUES (order_id, customer_id, order_total)
    INTO orders_audit (order_id, customer_id, order_total, copied_at)
    VALUES (order_id, customer_id, order_total, SYSDATE)
SELECT order_id,
       customer_id,
       order_total
FROM order_source
WHERE import_batch_id = :batch_id;
~~~

Với mỗi dòng nguồn thỏa import_batch_id, Oracle chèn một dòng vào ORDERS_LIVE và một dòng vào ORDERS_AUDIT. Hai dòng có thể dùng chung ORDER_ID. Bảng audit có thể nhận thêm thời điểm sao chép hoặc thông tin nguồn.

### 3.3. Một nguồn, nhiều bảng có cấu trúc khác nhau

Các bảng đích không cần có cùng số cột hoặc cùng cấu trúc. Mỗi nhánh INTO khai báo danh sách cột và giá trị riêng:

~~~sql
INSERT ALL
    INTO people_lab (person_id, full_name, person_type)
    VALUES (person_id, full_name, person_type)
    INTO person_contact_lab (person_id, email_address)
    VALUES (person_id, email_address)
    INTO person_status_lab (person_id, status_code, created_at)
    VALUES (person_id, status_code, SYSDATE)
SELECT person_id,
       full_name,
       person_type,
       email_address,
       status_code
FROM person_import_stage;
~~~

Nhánh thứ nhất dùng ba cột, nhánh thứ hai dùng hai cột, nhánh thứ ba dùng ba cột. Oracle ánh xạ giá trị theo thứ tự cột đã khai báo trong từng nhánh.

**Luôn ghi rõ column list.** Nếu bỏ danh sách cột, biểu thức phải cung cấp giá trị cho mọi cột theo thứ tự định nghĩa của bảng. Cách đó dễ hỏng khi schema thay đổi.

## 4. INSERT ALL có điều kiện

### 4.1. Cú pháp và cách đánh giá

~~~sql
INSERT ALL
    WHEN condition_1 THEN
        INTO table_a (column_a1, column_a2)
        VALUES (source_expr_1, source_expr_2)
    WHEN condition_2 THEN
        INTO table_b (column_b1, column_b2)
        VALUES (source_expr_1, source_expr_2)
    ELSE
        INTO fallback_table (column_x, column_y)
        VALUES (source_expr_1, source_expr_2)
SELECT source_expr_1, source_expr_2, ...
FROM source_table;
~~~

INSERT ALL có điều kiện đánh giá **tất cả** điều kiện WHEN cho từng dòng nguồn. Mỗi điều kiện đúng sẽ kích hoạt danh sách INTO tương ứng.

Nếu không có điều kiện WHEN nào đúng:

- Có ELSE: chạy các nhánh INTO trong ELSE.
- Không có ELSE: bỏ qua dòng nguồn đó, không chèn vào bảng nào.

Oracle Database 19c cho phép tối đa 127 mệnh đề WHEN trong một câu multitable insert.

### 4.2. Phân loại đơn hàng vào các bảng

Giả sử quy tắc:

| Giá trị đơn hàng | Bảng đích |
| --- | --- |
| Dưới 1.000 | SMALL_ORDERS |
| Từ 1.000 đến dưới 10.000 | MEDIUM_ORDERS |
| Từ 10.000 trở lên | LARGE_ORDERS |

~~~sql
INSERT ALL
    WHEN order_total < 1000 THEN
        INTO small_orders (order_id, customer_id, order_total)
        VALUES (order_id, customer_id, order_total)
    WHEN order_total >= 1000 AND order_total < 10000 THEN
        INTO medium_orders (order_id, customer_id, order_total)
        VALUES (order_id, customer_id, order_total)
    WHEN order_total >= 10000 THEN
        INTO large_orders (order_id, customer_id, order_total)
        VALUES (order_id, customer_id, order_total)
SELECT order_id,
       customer_id,
       order_total
FROM orders
WHERE order_date >= DATE '2026-01-01';
~~~

Các khoảng không chồng lấn và bao phủ mọi giá trị số khác NULL. Mỗi đơn hàng được phân vào đúng một bảng.

### 4.3. Một dòng nguồn có thể vào nhiều bảng

Điểm quan trọng của INSERT ALL là điều kiện không loại trừ lẫn nhau. Ví dụ muốn:

- Đưa mọi đơn từ 1.000 trở lên vào ORDERS_OVER_1000.
- Đồng thời đưa đơn từ 10.000 trở lên vào ORDERS_VIP.
- Đơn dưới 1.000 vào ORDERS_SMALL.

~~~sql
INSERT ALL
    WHEN order_total >= 1000 THEN
        INTO orders_over_1000 (order_id, order_total)
        VALUES (order_id, order_total)
    WHEN order_total >= 10000 THEN
        INTO orders_vip (order_id, order_total)
        VALUES (order_id, order_total)
    ELSE
        INTO orders_small (order_id, order_total)
        VALUES (order_id, order_total)
SELECT order_id, order_total
FROM orders;
~~~

Với đơn hàng 15.000, cả hai điều kiện WHEN đều đúng nên đơn đó được chèn vào **cả hai** bảng ORDERS_OVER_1000 và ORDERS_VIP. ELSE không chạy vì đã có điều kiện đúng.

Đây là cách biểu diễn một dòng thuộc nhiều nhóm nghiệp vụ. Nếu muốn mỗi đơn chỉ nằm trong một nhóm, phải viết điều kiện loại trừ lẫn nhau hoặc dùng INSERT FIRST.

### 4.4. ELSE là nhánh mặc định

~~~sql
INSERT ALL
    WHEN order_total <= 100000 THEN
        INTO small_orders (order_id, order_total)
        VALUES (order_id, order_total)
    WHEN order_total > 100000 AND order_total <= 200000 THEN
        INTO medium_orders (order_id, order_total)
        VALUES (order_id, order_total)
    ELSE
        INTO large_orders (order_id, order_total)
        VALUES (order_id, order_total)
SELECT order_id, order_total
FROM orders;
~~~

ELSE được dùng nếu không điều kiện WHEN nào đúng. Vì vậy các đơn lớn hơn 200.000 vào LARGE_ORDERS. Nếu ORDER_TOTAL là NULL, các phép so sánh đều UNKNOWN, không phải TRUE; dòng đó cũng đi vào ELSE. Nếu NULL phải được xử lý riêng, thêm điều kiện:

~~~sql
WHEN order_total IS NULL THEN
    INTO invalid_orders (order_id, order_total)
    VALUES (order_id, order_total)
~~~

INSERT ALL đánh giá mọi điều kiện nên thứ tự các nhánh không phải quy tắc ưu tiên.

## 5. INSERT FIRST: chỉ thực hiện nhánh đầu tiên đúng

### 5.1. Khác biệt với INSERT ALL

INSERT FIRST là conditional multitable insert. Oracle kiểm tra các điều kiện WHEN theo thứ tự xuất hiện. Với mỗi dòng nguồn:

1. Kiểm tra WHEN thứ nhất.
2. Nếu đúng, thực hiện danh sách INTO của nhánh đó và bỏ qua mọi WHEN sau.
3. Nếu sai, kiểm tra nhánh tiếp theo.
4. Nếu không nhánh nào đúng, thực hiện ELSE nếu có; nếu không, bỏ qua dòng nguồn.

| Đặc điểm | INSERT ALL | INSERT FIRST |
| --- | --- | --- |
| Đánh giá WHEN | Tất cả điều kiện | Theo thứ tự, dừng khi gặp điều kiện đúng đầu tiên |
| Nhiều điều kiện cùng đúng | Có thể chạy nhiều nhánh | Chỉ chạy nhánh đầu tiên đúng |
| ELSE | Chạy khi không WHEN nào đúng | Chạy khi không WHEN nào đúng |
| Dùng để | Phân phối một row vào nhiều đích | Phân loại ưu tiên, chọn một nhánh |

### 5.2. Phân loại theo mức ưu tiên

Giả sử đơn hàng được phân loại:

- Từ 50.000 trở lên: VIP.
- Từ 10.000 đến dưới 50.000: lớn.
- Từ 1.000 đến dưới 10.000: trung bình.
- Còn lại: nhỏ.

~~~sql
INSERT FIRST
    WHEN order_total >= 50000 THEN
        INTO vip_orders (order_id, order_total)
        VALUES (order_id, order_total)
    WHEN order_total >= 10000 THEN
        INTO large_orders (order_id, order_total)
        VALUES (order_id, order_total)
    WHEN order_total >= 1000 THEN
        INTO medium_orders (order_id, order_total)
        VALUES (order_id, order_total)
    ELSE
        INTO small_orders (order_id, order_total)
        VALUES (order_id, order_total)
SELECT order_id, order_total
FROM orders;
~~~

Đơn hàng 75.000 thỏa cả ba điều kiện đầu, nhưng chỉ được chèn vào VIP_ORDERS vì đó là nhánh đúng đầu tiên. Đơn 20.000 vào LARGE_ORDERS; đơn 2.000 vào MEDIUM_ORDERS.

### 5.3. Thứ tự WHEN làm thay đổi kết quả

~~~sql
-- Thứ tự sai nếu muốn tách riêng VIP:
INSERT FIRST
    WHEN order_total >= 1000 THEN
        INTO regular_orders (order_id, order_total)
        VALUES (order_id, order_total)
    WHEN order_total >= 50000 THEN
        INTO vip_orders (order_id, order_total)
        VALUES (order_id, order_total)
SELECT order_id, order_total
FROM orders;
~~~

Điều kiện ORDER_TOTAL >= 1000 đã bao phủ các đơn VIP. Vì INSERT FIRST dừng ở nhánh đầu tiên đúng, nhánh VIP không nhận đơn từ 50.000 trở lên.

Đặt điều kiện cụ thể hơn trước:

~~~sql
INSERT FIRST
    WHEN order_total >= 50000 THEN
        INTO vip_orders (order_id, order_total)
        VALUES (order_id, order_total)
    WHEN order_total >= 1000 THEN
        INTO regular_orders (order_id, order_total)
        VALUES (order_id, order_total)
    ELSE
        INTO small_orders (order_id, order_total)
        VALUES (order_id, order_total)
SELECT order_id, order_total
FROM orders;
~~~

Với INSERT FIRST, hãy đọc các điều kiện như một chuỗi ưu tiên. Nhánh tổng quát đặt trước nhánh đặc biệt có thể làm nhánh đặc biệt không bao giờ chạy.

## 6. Nhiều INTO trong cùng một nhánh WHEN

Một điều kiện có thể kích hoạt nhiều bảng đích:

~~~sql
INSERT ALL
    WHEN admission_date IS NOT NULL THEN
        INTO patients_lab (patient_id, admission_date)
        VALUES (person_id, admission_date)
        INTO patient_audit_lab (person_id, event_type, logged_at)
        VALUES (person_id, 'ADMISSION', SYSDATE)
    WHEN hired_date IS NOT NULL THEN
        INTO staff_lab (staff_id, hired_date)
        VALUES (person_id, hired_date)
        INTO staff_audit_lab (person_id, event_type, logged_at)
        VALUES (person_id, 'HIRED', SYSDATE)
SELECT person_id, admission_date, hired_date
FROM person_import_stage;
~~~

Nếu một người có ADMISSION_DATE khác NULL, cả PATIENTS_LAB và PATIENT_AUDIT_LAB đều nhận dòng tương ứng. Nếu HIRED_DATE cũng khác NULL, INSERT ALL còn chạy nhánh nhân viên. Một người có thể đồng thời là bệnh nhân và nhân viên.

Với INSERT FIRST, nếu cả hai điều kiện đều đúng, chỉ nhánh đầu tiên đúng được thực hiện. Hãy chọn ALL hay FIRST theo quan hệ nghiệp vụ.

## 7. Biến đổi cấu trúc dữ liệu bằng INSERT ALL

Một ứng dụng phổ biến của INSERT ALL là chuyển dữ liệu dạng cột thành nhiều dòng, còn gọi là unpivot thủ công.

### 7.1. Từ doanh số theo ngày trong cột thành dòng

Bảng nguồn có cấu trúc:

| PRODUCT_ID | WEEK_START | SALES_MON | SALES_TUE | SALES_WED |
| ---: | --- | ---: | ---: | ---: |
| 101 | 2026-11-02 | 100 | 120 | 90 |
| 102 | 2026-11-02 | 80 | 75 | 110 |

Bảng đích DAILY_SALES có cấu trúc PRODUCT_ID, SALES_DATE, AMOUNT. Dùng INSERT ALL:

~~~sql
INSERT ALL
    INTO daily_sales (product_id, sales_date, amount)
    VALUES (product_id, week_start, sales_mon)
    INTO daily_sales (product_id, sales_date, amount)
    VALUES (product_id, week_start + 1, sales_tue)
    INTO daily_sales (product_id, sales_date, amount)
    VALUES (product_id, week_start + 2, sales_wed)
SELECT product_id,
       week_start,
       sales_mon,
       sales_tue,
       sales_wed
FROM weekly_sales;
~~~

Mỗi dòng tuần tạo ba dòng doanh số ngày. Cùng một bảng đích có thể xuất hiện trong nhiều nhánh INTO; đây là kỹ thuật hợp lệ và hữu ích cho unpivot.

### 7.2. Bỏ qua giá trị NULL

Nếu cột ngày không có doanh số có thể chứa NULL và ta không muốn tạo dòng đích:

~~~sql
INSERT ALL
    WHEN sales_mon IS NOT NULL THEN
        INTO daily_sales (product_id, sales_date, amount)
        VALUES (product_id, week_start, sales_mon)
    WHEN sales_tue IS NOT NULL THEN
        INTO daily_sales (product_id, sales_date, amount)
        VALUES (product_id, week_start + 1, sales_tue)
    WHEN sales_wed IS NOT NULL THEN
        INTO daily_sales (product_id, sales_date, amount)
        VALUES (product_id, week_start + 2, sales_wed)
SELECT product_id,
       week_start,
       sales_mon,
       sales_tue,
       sales_wed
FROM weekly_sales;
~~~

Vì các điều kiện độc lập, một dòng tuần có thể kích hoạt một, hai hoặc ba nhánh. Nếu cả ba giá trị đều NULL, dòng nguồn không tạo dòng đích.

### 7.3. So sánh với UNPIVOT

Oracle còn có toán tử UNPIVOT trong SELECT. Nếu chỉ cần biến đổi cột thành dòng trong truy vấn nguồn, UNPIVOT có thể biểu đạt ngắn gọn:

~~~sql
SELECT product_id,
       week_start + CASE weekday
           WHEN 'MON' THEN 0
           WHEN 'TUE' THEN 1
           WHEN 'WED' THEN 2
       END AS sales_date,
       amount
FROM weekly_sales
UNPIVOT EXCLUDE NULLS (
    amount FOR weekday IN (
        sales_mon AS 'MON',
        sales_tue AS 'TUE',
        sales_wed AS 'WED'
    )
);
~~~

Có thể kết hợp kết quả UNPIVOT với INSERT INTO ... SELECT để lưu vào bảng đích. Chọn công cụ theo mục tiêu:

- INSERT ALL: tiện khi một dòng nguồn cần tạo nhiều dòng đích, nhiều bảng hoặc nhiều nhánh tính toán.
- UNPIVOT: phù hợp khi mục tiêu chính là chuyển một nhóm cột thành các dòng trong truy vấn nguồn.

## 8. Dùng SELECT list để chuẩn bị biểu thức nguồn

Các điều kiện WHEN và biểu thức VALUES tham chiếu các cột do select list của truy vấn nguồn trả về. Nếu cần dùng một phép tính có alias bảng nguồn, hãy đưa phép tính đó vào select list và đặt alias cho nó.

### 8.1. Alias cho biểu thức

~~~sql
INSERT ALL
    WHEN adjusted_total >= 10000 THEN
        INTO high_value_orders (order_id, adjusted_total)
        VALUES (source_order_id, adjusted_total)
    ELSE
        INTO normal_orders (order_id, adjusted_total)
        VALUES (source_order_id, adjusted_total)
SELECT o.order_id AS source_order_id,
       o.order_total * 1.05 AS adjusted_total
FROM orders o;
~~~

ADJUSTED_TOTAL được tính trong truy vấn nguồn. Cả WHEN và VALUES sử dụng tên cột được xuất ra từ select list.

Không dựa vào alias bảng nguồn như O trong WHEN hoặc VALUES. Oracle quy định các biểu thức phụ thuộc select list tham chiếu cột do select list trả về. Cách rõ ràng là xuất O.ORDER_TOTAL * 1.05 thành ADJUSTED_TOTAL rồi dùng tên đó.

### 8.2. Alias nguồn và alias bảng đích

- Alias của biểu thức trong select list có thể được tham chiếu trong WHEN và VALUES.
- Không khai báo alias cho bảng đích trong nhánh INTO của multitable insert.
- Thứ tự giá trị trong VALUES phải khớp thứ tự cột trong danh sách đích.

~~~sql
INSERT ALL
    WHEN normalized_status = 'ACTIVE' THEN
        INTO active_users (user_id, display_name)
        VALUES (source_user_id, normalized_name)
SELECT u.user_id AS source_user_id,
       TRIM(u.full_name) AS normalized_name,
       UPPER(TRIM(u.status)) AS normalized_status
FROM users u;
~~~

## 9. Điều kiện WHEN, NULL và biểu thức

### 9.1. Chuẩn bị điều kiện trong truy vấn nguồn

~~~sql
INSERT ALL
    WHEN is_valid = 1 THEN
        INTO accepted_rows (record_id, normalized_value)
        VALUES (record_id, normalized_value)
    ELSE
        INTO rejected_rows (record_id, raw_value, reason_code)
        VALUES (record_id, raw_value, 'INVALID')
SELECT record_id,
       raw_value,
       TRIM(raw_value) AS normalized_value,
       CASE
         WHEN raw_value IS NOT NULL
          AND LENGTH(TRIM(raw_value)) <= 100
         THEN 1
         ELSE 0
       END AS is_valid
FROM import_stage;
~~~

Phần chuẩn hóa và kiểm tra được thực hiện trong truy vấn nguồn. WHEN chỉ cần đọc IS_VALID.

### 9.2. NULL không phải FALSE

Trong SQL, điều kiện có thể nhận TRUE, FALSE hoặc UNKNOWN. Nếu AMOUNT là NULL, biểu thức AMOUNT > 1000 trả UNKNOWN. Điều kiện WHEN chỉ chạy khi biểu thức là TRUE; UNKNOWN không kích hoạt nhánh.

Nếu muốn phân loại NULL riêng:

~~~sql
INSERT ALL
    WHEN amount IS NULL THEN
        INTO invalid_orders (order_id, amount, reason)
        VALUES (order_id, amount, 'MISSING_AMOUNT')
    WHEN amount >= 1000 THEN
        INTO valid_orders (order_id, amount)
        VALUES (order_id, amount)
    ELSE
        INTO small_orders (order_id, amount)
        VALUES (order_id, amount)
SELECT order_id, amount
FROM order_stage;
~~~

INSERT ALL đánh giá mọi điều kiện nên thứ tự hai nhánh đầu không phải quy tắc ưu tiên. INSERT FIRST thì có thứ tự ưu tiên; đặt điều kiện NULL trước giúp nhánh tổng quát không bắt row đó trước.

### 9.3. Điều kiện chồng lấn

~~~sql
WHEN amount >= 1000 THEN ...
WHEN amount >= 5000 THEN ...
~~~

Với INSERT ALL, amount 6.000 thỏa cả hai. Với INSERT FIRST, chỉ nhánh đầu tiên đúng chạy. Khi viết điều kiện, hãy xác định các nhánh có loại trừ lẫn nhau không, một row có chủ đích được chèn vào nhiều bảng không, có cần ELSE không và NULL được xử lý thế nào.

## 10. Chèn dữ liệu cha và con trong một câu lệnh

Một trường hợp quan trọng là một dòng nguồn tạo dữ liệu ở bảng cha và một hoặc nhiều bảng con. Ví dụ một người luôn được lưu trong PEOPLE; người có ngày nhập viện được lưu thêm trong PATIENTS; người có ngày tuyển dụng được lưu thêm trong STAFF.

### 10.1. Tạo bảng lab

Chỉ chạy trong schema lab:

~~~sql
CREATE TABLE people_lab (
    person_id   NUMBER PRIMARY KEY,
    given_name  VARCHAR2(50 CHAR) NOT NULL,
    family_name VARCHAR2(50 CHAR) NOT NULL,
    person_type VARCHAR2(20 CHAR)
);

CREATE TABLE patients_lab (
    patient_id NUMBER PRIMARY KEY
               REFERENCES people_lab(person_id),
    admission_date DATE
);

CREATE TABLE staff_lab (
    staff_id NUMBER PRIMARY KEY
             REFERENCES people_lab(person_id),
    hired_date DATE
);
~~~

### 10.2. Chèn tất cả vào bảng cha, chèn có điều kiện vào bảng con

Với multitable insert có điều kiện, dùng WHEN 1=1 để biểu diễn nhánh luôn đúng cho bảng cha:

~~~sql
INSERT ALL
    WHEN 1 = 1 THEN
        INTO people_lab (person_id, given_name, family_name, person_type)
        VALUES (person_id, given_name, family_name, 'PERSON')
    WHEN admission_date IS NOT NULL THEN
        INTO patients_lab (patient_id, admission_date)
        VALUES (person_id, admission_date)
    WHEN hired_date IS NOT NULL THEN
        INTO staff_lab (staff_id, hired_date)
        VALUES (person_id, hired_date)
WITH names AS (
    SELECT 1 AS person_id, 'Ruth' AS given_name, 'Fox' AS family_name,
           DATE '2026-01-10' AS admission_date,
           CAST(NULL AS DATE) AS hired_date
    FROM dual
    UNION ALL
    SELECT 2, 'Isabelle', 'Squirrel',
           DATE '2026-02-15', CAST(NULL AS DATE)
    FROM dual
    UNION ALL
    SELECT 3, 'Justin', 'Frog',
           CAST(NULL AS DATE), DATE '2026-03-01'
    FROM dual
    UNION ALL
    SELECT 4, 'Lisa', 'Owl',
           CAST(NULL AS DATE), CAST(NULL AS DATE)
    FROM dual
)
SELECT person_id, given_name, family_name, admission_date, hired_date
FROM names;
~~~

Kết quả:

- Cả bốn người được chèn vào PEOPLE_LAB.
- Người 1 và 2 được chèn vào PATIENTS_LAB.
- Người 3 được chèn vào STAFF_LAB.
- Người 4 chỉ có dòng ở bảng cha.

Một source row có thể tạo một dòng cha và một hoặc nhiều dòng con. Ví dụ dùng ID từ nguồn nên các khóa ngoại có cùng giá trị. Oracle có ví dụ chính thức về cách dùng INSERT ALL để ghi vào bảng PEOPLE và các bảng PATIENTS, STAFF liên quan.

### 10.3. Một người vừa là bệnh nhân vừa là nhân viên

Vì dùng INSERT ALL, cả hai điều kiện có thể cùng đúng:

~~~text
admission_date IS NOT NULL
hired_date     IS NOT NULL
        |
        +--> chèn PEOPLE
        +--> chèn PATIENTS
        +--> chèn STAFF
~~~

Nếu yêu cầu mỗi người chỉ được xếp vào một loại ưu tiên, đổi sang INSERT FIRST và sắp xếp WHEN theo thứ tự ưu tiên. SQL thực thi quy tắc đã viết; mô hình dữ liệu vẫn phải xác định một người có thể vừa là staff vừa là patient hay không.

## 11. Sequence và khóa sinh tự động

Khi một dòng nguồn được chèn vào nhiều bảng, đôi khi các bảng cần dùng chung một ID. Oracle sequence có semantics đặc biệt trong multitable insert.

### 11.1. NEXTVAL trong VALUES

Theo tài liệu Oracle 19c về Sequence Pseudocolumns, với multitable insert, tham chiếu NEXTVAL đặt trong VALUES và sequence được tăng **một lần cho mỗi dòng đầu vào từ SELECT**. Nếu tham chiếu NEXTVAL nhiều lần trong các nhánh của cùng một input row, các lần tham chiếu đó nhận cùng giá trị sequence cho row ấy.

Ví dụ về ý tưởng tạo cùng một ID cho bảng cha và bảng con:

~~~sql
INSERT ALL
    WHEN 1 = 1 THEN
        INTO people_lab (person_id, given_name, family_name, person_type)
        VALUES (people_seq.NEXTVAL, given_name, family_name, 'PERSON')
    WHEN admission_date IS NOT NULL THEN
        INTO patients_lab (patient_id, admission_date)
        VALUES (people_seq.NEXTVAL, admission_date)
SELECT given_name, family_name, admission_date
FROM person_import_stage;
~~~

Với mỗi dòng nguồn, các tham chiếu PEOPLE_SEQ.NEXTVAL trong các nhánh được dùng cho dòng đó trả cùng một số. Điều này có thể giúp chia sẻ khóa cha/con.

**Không giả định mỗi nhánh INTO tự tăng sequence một lần.** Nếu một source row được chèn vào ba bảng, sequence không tự tạo ba ID khác nhau chỉ vì có ba nhánh. Sequence tăng theo từng source row, và các tham chiếu lặp trong cùng row dùng cùng giá trị.

### 11.2. Nếu các bảng cần ID khác nhau

Nếu mỗi bảng đích cần khóa riêng, hãy thiết kế việc cấp ID riêng một cách tường minh:

- Dùng các sequence khác nhau cho các bảng có miền ID độc lập.
- Chuẩn bị các ID cần thiết trong staging trước khi multitable insert.
- Dùng trigger, default hoặc identity theo thiết kế và kiểm tra hành vi trên release Oracle đang chạy.
- Tách thành các câu DML riêng nếu cần kiểm soát thứ tự hoặc kết quả sinh khóa.

Đối với multitable insert, không đặt NEXTVAL trong select list nguồn để mong có một số mới cho mỗi nhánh.

### 11.3. Sequence không rollback

Sequence không phải dữ liệu transactional thông thường. Số đã cấp bởi NEXTVAL không được trả lại khi transaction rollback; khoảng trống trong dãy số là bình thường. Không dùng sequence để đếm số dòng đã commit hoặc yêu cầu số liên tục không có gap.

## 12. Giá trị mặc định, kiểu dữ liệu và ánh xạ cột

### 12.1. Mỗi INTO có column list và VALUES tương ứng

~~~sql
INSERT ALL
    INTO table_a (id, amount, created_at)
    VALUES (source_id, source_amount, SYSDATE)
    INTO table_b (id, description)
    VALUES (source_id, source_description)
SELECT id AS source_id,
       amount AS source_amount,
       description AS source_description
FROM source_table;
~~~

Số lượng giá trị trong VALUES phải khớp số cột trong danh sách cột. Kiểu dữ liệu phải tương thích. Nếu dùng biểu thức hoặc conversion, nên ghi rõ để tránh implicit conversion theo NLS.

### 12.2. Bỏ cột để dùng default

Nếu một cột không xuất hiện trong column list, Oracle áp dụng default của cột nếu có; nếu không có default thì giá trị thường là NULL và có thể vi phạm NOT NULL.

~~~sql
CREATE TABLE event_archive_lab (
    event_id   NUMBER PRIMARY KEY,
    event_text VARCHAR2(100 CHAR),
    created_at DATE DEFAULT SYSDATE
);

INSERT ALL
    INTO event_archive_lab (event_id, event_text)
    VALUES (event_id, event_text)
SELECT event_id, event_text
FROM event_stage;
~~~

CREATED_AT được bỏ khỏi column list nên dùng default SYSDATE.

Oracle cho phép từ khóa DEFAULT trong VALUES của INSERT theo cú pháp hỗ trợ. Đối với cột identity, hãy xác nhận quy tắc sinh giá trị và chế độ GENERATED ALWAYS/BY DEFAULT của bảng.

### 12.3. Tránh phụ thuộc thứ tự cột của bảng

Không nên bỏ column list khi chèn vào bảng có cấu trúc thay đổi. Nếu bảng đích thêm một cột, câu lệnh không khai báo column list có thể lỗi hoặc ánh xạ không còn đúng như dự kiến. Ghi rõ cột đích giúp câu lệnh dễ bảo trì.

## 13. INSERT ALL, INSERT FIRST và CASE

Ba công cụ này có liên quan nhưng vai trò khác nhau.

### 13.1. CASE tạo một giá trị

~~~sql
SELECT order_id,
       CASE
         WHEN order_total >= 50000 THEN 'VIP'
         WHEN order_total >= 10000 THEN 'LARGE'
         WHEN order_total >= 1000 THEN 'MEDIUM'
         ELSE 'SMALL'
       END AS order_class
FROM orders;
~~~

CASE chọn một biểu thức kết quả cho mỗi row. CASE không tự chèn vào nhiều bảng.

### 13.2. INSERT FIRST chọn nhánh chèn

INSERT FIRST thực hiện danh sách INTO của nhánh đầu tiên có điều kiện TRUE. Đây là cách thích hợp khi phân loại một row vào một nhóm đích ưu tiên.

### 13.3. INSERT ALL có thể chạy nhiều nhánh

INSERT ALL đánh giá từng điều kiện độc lập. Một row có thể vào nhiều nhóm. Nó phù hợp khi một record cần được ghi vào nhiều bảng hoặc đồng thời thỏa nhiều tiêu chí.

| Mục tiêu | Cách thường dùng |
| --- | --- |
| Tính nhãn/giá trị phân loại trên từng row | CASE |
| Chèn mỗi row vào một nhóm ưu tiên | INSERT FIRST |
| Chèn mỗi row vào tất cả nhóm mà nó thỏa | INSERT ALL |
| Ghi một row vào mọi bảng đích không điều kiện | INSERT ALL không có WHEN |

## 14. So sánh với nhiều câu INSERT ... SELECT

Có thể thay multitable insert bằng nhiều câu riêng:

~~~sql
INSERT INTO small_orders (order_id, order_total)
SELECT order_id, order_total
FROM orders
WHERE order_total < 1000;

INSERT INTO large_orders (order_id, order_total)
SELECT order_id, order_total
FROM orders
WHERE order_total >= 1000;
~~~

| Tiêu chí | Nhiều INSERT ... SELECT | Multitable INSERT |
| --- | --- | --- |
| Số câu DML | Nhiều câu | Một câu |
| Nguồn logic | Có thể đọc/biến đổi nguồn nhiều lần | Một query nguồn cấp dữ liệu cho các nhánh |
| Phân nhánh | Mỗi câu có WHERE riêng | WHEN/ELSE trong một câu |
| Chia một row vào nhiều bảng | Làm được bằng nhiều câu | Tự nhiên qua nhiều INTO |
| Transaction | Có thể commit/rollback từng bước nếu chủ động | Một statement, nguyên tử ở cấp câu lệnh |
| Debug | Dễ cô lập từng câu | Cần đọc toàn bộ nhánh và điều kiện |

Nếu cần một giao dịch gồm nhiều bước có kiểm soát, nhiều câu DML trong transaction có thể dễ quản lý hơn. Nếu cần fan-out hoặc routing từ cùng một tập nguồn, multitable insert thường gọn hơn.

## 15. Transaction, constraint và trigger

### 15.1. Tính nguyên tử của một câu lệnh

Multitable insert là một câu DML. Khi một lỗi không được xử lý bằng cơ chế error logging làm câu lệnh thất bại, Oracle rollback các thay đổi do **câu lệnh đó** tạo ra. Các câu lệnh trước đó trong transaction không tự động bị rollback chỉ vì câu multitable insert hiện tại lỗi; transaction vẫn do ứng dụng hoặc người chạy kiểm soát.

### 15.2. Constraint vẫn được kiểm tra

Mỗi bảng đích vẫn áp dụng các quy tắc của nó:

- PRIMARY KEY và UNIQUE.
- NOT NULL.
- CHECK.
- FOREIGN KEY.
- Kiểu dữ liệu, độ dài và precision/scale.

Một dòng có thể thỏa WHEN nhưng vẫn thất bại khi chèn vì vi phạm constraint. Điều kiện WHEN chỉ quyết định có thực hiện nhánh hay không; nó không thay thế kiểm tra integrity của bảng.

### 15.3. Trigger

Các trigger INSERT được định nghĩa trên bảng đích có thể được kích hoạt bởi các dòng chèn tương ứng. Nếu một source row được chèn vào hai bảng, hãy kiểm tra trigger trên cả hai bảng, nhất là khi trigger sinh khóa, ghi audit, thay đổi dữ liệu hoặc gọi package.

Không thiết kế trigger với giả định rằng mỗi source row chỉ tạo đúng một dòng đích. Với INSERT ALL, một source row có thể tạo nhiều lần chèn.

### 15.4. Kiểm tra dữ liệu trước khi commit

~~~sql
SELECT COUNT(*) FROM small_orders;
SELECT COUNT(*) FROM medium_orders;
SELECT COUNT(*) FROM large_orders;
~~~

Sau khi đối chiếu số dòng và giá trị:

~~~sql
COMMIT;
~~~

Nếu phát hiện kết quả sai và chưa commit:

~~~sql
ROLLBACK;
~~~

DDL như CREATE TABLE, ALTER TABLE, DROP TABLE có implicit commit trong Oracle; không dùng ROLLBACK để mong hoàn tác DDL.

## 16. Error logging và xử lý lỗi nạp dữ liệu

Oracle hỗ trợ error_logging_clause trong cú pháp INSERT, bao gồm multitable insert. Error logging có thể hữu ích khi muốn ghi lại một số lỗi DML và tiếp tục xử lý các row khác theo REJECT LIMIT.

Quy trình tổng quát:

1. Tạo bảng error log bằng DBMS_ERRLOG.CREATE_ERROR_LOG cho bảng đích cần theo dõi.
2. Thêm LOG ERRORS INTO và REJECT LIMIT theo cú pháp được hỗ trợ.
3. Đọc bảng error log để xác định row, thông báo lỗi và tag.
4. Sửa dữ liệu nguồn hoặc quy tắc mapping rồi chạy lại phần bị lỗi.

Ví dụ cơ chế log với một bảng đích:

~~~sql
BEGIN
    DBMS_ERRLOG.CREATE_ERROR_LOG(
        dml_table_name => 'ORDER_ARCHIVE',
        err_log_table_name => 'ERR_ORDER_ARCHIVE'
    );
END;
/

INSERT INTO order_archive (order_id, order_total)
SELECT order_id, order_total
FROM order_stage
LOG ERRORS INTO err_order_archive ('BATCH_20261114')
REJECT LIMIT UNLIMITED;
~~~

Đây là ví dụ cho INSERT một bảng để minh họa cơ chế log. Khi áp dụng LOG ERRORS cho multitable insert, hãy kiểm tra cách tạo và chỉ định error log table phù hợp cho các bảng đích và các giới hạn error logging của release. Một số lỗi, chẳng hạn vi phạm deferred constraint hoặc một số trường hợp direct-path/unique-index, có thể làm statement thất bại mà không đi qua error logging.

Error logging không thay thế validation dữ liệu. Với import quan trọng, vẫn nên có staging, kiểm tra chất lượng dữ liệu, đối soát số lượng và audit batch.

## 17. Những giới hạn của multitable insert trong Oracle 19c

Các giới hạn đáng nhớ theo SQL Language Reference:

- Multitable insert chỉ chèn vào table, không chèn trực tiếp vào view hoặc materialized view.
- Không chèn trực tiếp vào remote table bằng multitable insert.
- Không dùng TABLE collection expression trong multitable insert.
- Không thể dùng RETURNING clause cho multitable insert.
- Table alias không được khai báo cho bảng đích trong nhánh INTO.
- Các biểu thức WHEN phải tham chiếu cột do select list của truy vấn nguồn trả về.
- Một câu có tối đa 127 mệnh đề WHEN.
- Nếu bất kỳ bảng đích nào là index-organized table hoặc có bitmap index, multitable insert không được parallel hóa theo điều kiện Oracle nêu.
- Plan stability không được hỗ trợ cho multitable insert.

### 17.1. Lưu ý riêng về sequence

Tài liệu Sequence Pseudocolumns của Oracle 19c mô tả NEXTVAL có thể xuất hiện trong VALUES của multitable insert và tăng một lần cho mỗi row nguồn; các tham chiếu lặp trong các nhánh cùng input row nhận cùng giá trị. Hãy theo đúng vị trí VALUES và kiểm tra kết quả trên release đang chạy. Không đặt NEXTVAL trong select list nguồn để mong một số mới cho mỗi nhánh.

### 17.2. Không có RETURNING

Multitable insert không hỗ trợ RETURNING. Nếu ứng dụng cần lấy khóa được sinh hoặc xác nhận từng dòng đích, thiết kế quy trình khác: chuẩn bị ID ở nguồn/staging, dùng sequence đúng semantics, hoặc dùng các câu INSERT riêng có RETURNING khi phù hợp.

## 18. Hiệu năng và thiết kế nguồn SELECT

### 18.1. Giảm row nguồn trước khi phân phối

~~~sql
INSERT ALL
    WHEN is_valid = 1 THEN
        INTO accepted_orders (order_id, amount)
        VALUES (order_id, amount)
    ELSE
        INTO rejected_orders (order_id, amount, reason)
        VALUES (order_id, amount, 'INVALID')
SELECT order_id,
       amount,
       CASE
         WHEN amount IS NOT NULL AND amount >= 0 THEN 1
         ELSE 0
       END AS is_valid
FROM order_stage
WHERE batch_id = :batch_id;
~~~

WHERE lọc các batch cần xử lý. WHEN phân phối từng row trong batch. Tránh đưa dữ liệu không thuộc batch vào câu lệnh.

### 18.2. Đừng lặp lại phép tính ở từng nhánh

Nếu nhiều nhánh cần cùng một phép chuẩn hóa, tính trong select list:

~~~sql
SELECT raw_code,
       UPPER(TRIM(raw_code)) AS normalized_code,
       amount,
       amount * exchange_rate AS converted_amount
FROM import_stage;
~~~

Sau đó tham chiếu NORMALIZED_CODE hoặc CONVERTED_AMOUNT trong WHEN/VALUES. Cách này giảm lặp và giúp quy tắc mapping rõ hơn.

### 18.3. Kiểm tra số dòng fan-out

Nếu có N dòng nguồn và mỗi dòng có thể đi vào nhiều bảng đích, tổng DML có thể tăng nhanh. Trước batch lớn, hãy ước lượng số dòng nguồn, số nhánh có thể kích hoạt, điều kiện chồng lấn, số bảng cần audit và các index/trigger/constraint của bảng đích.

### 18.4. Xem execution plan

~~~sql
EXPLAIN PLAN FOR
INSERT ALL
    WHEN amount < 1000 THEN
        INTO small_orders (order_id, amount)
        VALUES (order_id, amount)
    WHEN amount >= 1000 THEN
        INTO large_orders (order_id, amount)
        VALUES (order_id, amount)
SELECT order_id, amount
FROM order_stage;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

EXPLAIN PLAN thể hiện kế hoạch dự kiến. Khi cần số liệu runtime, dùng công cụ và quyền phù hợp trong môi trường DBA; không suy hiệu năng chỉ từ số lượng nhánh INTO.

## 19. Bộ dữ liệu lab tự chứa

Phần này tạo các bảng nhỏ để thực hành phân loại đơn hàng. Chỉ chạy trong schema lab. Nếu bảng đã tồn tại, dùng tên khác hoặc dọn đúng các object do bạn tạo.

### 19.1. Tạo bảng nguồn và bảng đích

~~~sql
CREATE TABLE order_stage_lab (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    order_total NUMBER(12,2),
    batch_id NUMBER NOT NULL
);

CREATE TABLE small_orders_lab (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    order_total NUMBER(12,2)
);

CREATE TABLE medium_orders_lab AS
SELECT * FROM small_orders_lab WHERE 1 = 0;

CREATE TABLE large_orders_lab AS
SELECT * FROM small_orders_lab WHERE 1 = 0;

CREATE TABLE vip_orders_lab AS
SELECT * FROM small_orders_lab WHERE 1 = 0;

CREATE TABLE invalid_orders_lab (
    order_id NUMBER,
    reason_code VARCHAR2(30 CHAR)
);
~~~

### 19.2. Nạp dữ liệu nguồn

~~~sql
INSERT INTO order_stage_lab VALUES (101, 10, 500, 1);
INSERT INTO order_stage_lab VALUES (102, 11, 2500, 1);
INSERT INTO order_stage_lab VALUES (103, 12, 12000, 1);
INSERT INTO order_stage_lab VALUES (104, 13, 75000, 1);
INSERT INTO order_stage_lab VALUES (105, 14, NULL, 1);
INSERT INTO order_stage_lab VALUES (106, 15, 900, 2);

COMMIT;
~~~

### 19.3. INSERT ALL phân loại một batch

~~~sql
INSERT ALL
    WHEN order_total IS NULL THEN
        INTO invalid_orders_lab (order_id, reason_code)
        VALUES (order_id, 'MISSING_TOTAL')
    WHEN order_total < 1000 THEN
        INTO small_orders_lab (order_id, customer_id, order_total)
        VALUES (order_id, customer_id, order_total)
    WHEN order_total >= 1000 AND order_total < 10000 THEN
        INTO medium_orders_lab (order_id, customer_id, order_total)
        VALUES (order_id, customer_id, order_total)
    WHEN order_total >= 10000 THEN
        INTO large_orders_lab (order_id, customer_id, order_total)
        VALUES (order_id, customer_id, order_total)
SELECT order_id, customer_id, order_total
FROM order_stage_lab
WHERE batch_id = 1;
~~~

Đơn có ORDER_TOTAL NULL được chuyển vào INVALID_ORDERS_LAB. Các đơn còn lại được phân loại theo khoảng số tiền.

### 19.4. INSERT FIRST với ưu tiên VIP

~~~sql
INSERT FIRST
    WHEN order_total IS NULL THEN
        INTO invalid_orders_lab (order_id, reason_code)
        VALUES (order_id, 'MISSING_TOTAL')
    WHEN order_total >= 50000 THEN
        INTO vip_orders_lab (order_id, customer_id, order_total)
        VALUES (order_id, customer_id, order_total)
    WHEN order_total >= 10000 THEN
        INTO large_orders_lab (order_id, customer_id, order_total)
        VALUES (order_id, customer_id, order_total)
    WHEN order_total >= 1000 THEN
        INTO medium_orders_lab (order_id, customer_id, order_total)
        VALUES (order_id, customer_id, order_total)
    ELSE
        INTO small_orders_lab (order_id, customer_id, order_total)
        VALUES (order_id, customer_id, order_total)
SELECT order_id, customer_id, order_total
FROM order_stage_lab
WHERE batch_id = 2;
~~~

Với batch 2, order 106 có amount 900 và được đưa vào SMALL_ORDERS_LAB. Các điều kiện VIP được đặt trước điều kiện tổng quát hơn.

### 19.5. Đối chiếu kết quả

~~~sql
SELECT 'SMALL' AS bucket, COUNT(*) AS row_count
FROM small_orders_lab
UNION ALL
SELECT 'MEDIUM', COUNT(*) FROM medium_orders_lab
UNION ALL
SELECT 'LARGE', COUNT(*) FROM large_orders_lab
UNION ALL
SELECT 'VIP', COUNT(*) FROM vip_orders_lab
UNION ALL
SELECT 'INVALID', COUNT(*) FROM invalid_orders_lab;
~~~

Nếu chạy lại cùng batch, các khóa chính có thể gây duplicate key. Để luyện tập lại, rollback trước commit nếu còn trong transaction, hoặc xóa đúng dữ liệu lab đã nạp theo batch. Không chạy lại mù quáng trên bảng nghiệp vụ.

### 19.6. Dọn bảng lab (tùy chọn)

~~~sql
DROP TABLE order_stage_lab PURGE;
DROP TABLE small_orders_lab PURGE;
DROP TABLE medium_orders_lab PURGE;
DROP TABLE large_orders_lab PURGE;
DROP TABLE vip_orders_lab PURGE;
DROP TABLE invalid_orders_lab PURGE;
~~~

DDL có implicit commit. Bỏ qua bước này nếu muốn giữ dữ liệu để luyện tập.

## 20. Những lỗi thường gặp

| Lỗi/hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| ORA-00928: missing SELECT keyword | Thiếu truy vấn nguồn ở cuối multitable insert hoặc sai cấu trúc | Kiểm tra SELECT cuối câu lệnh |
| ORA-00913: too many values | Số biểu thức trong VALUES không khớp số cột đích | So sánh column list và VALUES theo từng nhánh |
| ORA-00947: not enough values | Thiếu biểu thức so với số cột đích | Bổ sung giá trị hoặc bỏ cột có default khỏi column list |
| ORA-01400: cannot insert NULL | Giá trị nguồn NULL vào cột NOT NULL | Kiểm tra NULL, default và điều kiện WHEN |
| ORA-00001: unique constraint violated | Dữ liệu nguồn trùng khóa hoặc batch đã được nạp | Kiểm tra khóa, duplicate source và tính idempotent |
| Một row xuất hiện ở nhiều bảng | Dùng INSERT ALL với các WHEN chồng lấn | Xác định có chủ đích fan-out hay cần INSERT FIRST |
| Nhánh VIP không chạy | Nhánh tổng quát đứng trước trong INSERT FIRST | Đặt điều kiện cụ thể trước điều kiện tổng quát |
| Row không được chèn ở đâu | Không WHEN nào đúng và không có ELSE | Thêm ELSE hoặc xử lý riêng các trường hợp bỏ qua |
| Điều kiện WHEN không nhận alias mong muốn | Alias biểu thức chưa được xuất từ select list | Đưa biểu thức vào select list với alias rồi tham chiếu alias đó |
| Ngày/số bị chuyển đổi sai | Implicit conversion phụ thuộc NLS | Dùng datatype và conversion tường minh |
| Khóa cha/con không khớp | Hiểu sai semantics NEXTVAL giữa các nhánh | NEXTVAL tăng một lần mỗi source row; các nhánh cùng row nhận cùng giá trị |
| Không lấy được ID trả về | Multitable insert không hỗ trợ RETURNING | Chuẩn bị ID ở nguồn hoặc dùng quy trình DML khác |
| Kết quả batch không đối soát được | Không ghi batch ID hoặc audit metadata | Đưa batch key vào source và các bảng đích cần truy vết |

## 21. Checklist trước khi chạy multitable insert

1. **Truy vấn nguồn trả những cột nào?** Đặt alias cho biểu thức được dùng trong WHEN/VALUES.
2. **Mỗi nhánh INTO ghi vào bảng nào?** Ghi rõ column list và thứ tự giá trị.
3. **Dùng ALL hay FIRST?** Một row có thể đi vào nhiều nhánh hay chỉ một nhánh ưu tiên?
4. **Các điều kiện có chồng lấn không?** Nếu có, xác nhận đó là hành vi mong muốn.
5. **ELSE có cần thiết không?** Xác định rõ row không khớp điều kiện sẽ bị bỏ qua hay đưa vào bảng mặc định.
6. **NULL được xử lý ra sao?** UNKNOWN không kích hoạt WHEN.
7. **Sequence có cần dùng chung ID giữa các nhánh không?** NEXTVAL tăng một lần mỗi input row và các nhánh trong row đó nhận cùng giá trị.
8. **Bảng đích có constraint, trigger, index nào?** Kiểm tra duplicate, NOT NULL, FK và tác động phụ.
9. **Có cần RETURNING không?** Nếu có, multitable insert không phù hợp trực tiếp.
10. **Có cần error logging không?** Chuẩn bị bảng lỗi và hiểu giới hạn.
11. **Đã lọc đúng batch chưa?** Tránh chèn nhầm toàn bộ staging.
12. **Đã đối soát kết quả trước COMMIT chưa?** Kiểm tra số lượng và các giá trị quan trọng.

## 22. Câu hỏi tự kiểm tra

**Câu 1.** Multitable insert dùng phần nào để tạo các dòng đầu vào?

**Câu 2.** Với INSERT ALL không có WHEN, một source row được chèn vào bao nhiêu nhánh INTO?

**Câu 3.** Nếu hai điều kiện WHEN cùng đúng trong INSERT ALL, điều gì xảy ra?

**Câu 4.** Nếu hai điều kiện WHEN cùng đúng trong INSERT FIRST, điều gì xảy ra?

**Câu 5.** Khi nào nhánh ELSE được thực hiện?

**Câu 6.** Nếu không có ELSE và không WHEN nào đúng, dòng nguồn được xử lý thế nào?

**Câu 7.** Một WHEN có thể tham chiếu trực tiếp alias bảng nguồn như O.AMOUNT không? Cách viết rõ ràng hơn là gì?

**Câu 8.** Một điều kiện WHEN trả UNKNOWN do cột NULL có kích hoạt nhánh không?

**Câu 9.** Có thể lặp lại cùng một bảng đích trong nhiều nhánh INTO không?

**Câu 10.** Trong multitable insert, NEXTVAL được tăng theo từng nhánh hay từng dòng nguồn?

**Câu 11.** Vì sao các tham chiếu NEXTVAL lặp ở nhiều nhánh cùng một source row có thể nhận cùng giá trị?

**Câu 12.** Multitable insert có hỗ trợ RETURNING không?

**Câu 13.** Vì sao cần column list cho từng INTO?

**Câu 14.** Khi nào nên dùng UNPIVOT thay cho INSERT ALL?

<details>
<summary>Gợi ý đáp án</summary>

1. Truy vấn SELECT ở cuối câu lệnh.
2. Mỗi nhánh INTO vô điều kiện được thực hiện một lần cho mỗi source row.
3. Tất cả nhánh có điều kiện TRUE đều chạy.
4. Chỉ nhánh đầu tiên có điều kiện TRUE chạy.
5. Khi không có WHEN nào TRUE cho source row hiện tại.
6. Bỏ qua source row đó, không chèn vào bảng nào.
7. Biểu thức phụ thuộc select list nên dùng cột được xuất từ select list; đưa O.AMOUNT hoặc phép tính vào select list với alias rồi tham chiếu alias.
8. Không. UNKNOWN không phải TRUE.
9. Có. Đây là cách phổ biến để chuyển nhiều cột nguồn thành nhiều dòng cùng một bảng đích.
10. Một lần cho mỗi dòng nguồn, không phải một lần cho mỗi nhánh INTO.
11. Oracle dùng cùng giá trị NEXTVAL cho các tham chiếu của một input row trong một multitable insert.
12. Không.
13. Để ánh xạ đúng giá trị, tránh phụ thuộc thứ tự cột của bảng và dễ bảo trì.
14. Khi mục tiêu chính là chuyển một nhóm cột thành dòng trong truy vấn nguồn; sau đó có thể dùng INSERT INTO ... SELECT để lưu kết quả.

</details>

## 23. Tài liệu Oracle chính thức

1. [Oracle Database 19c SQL Language Reference — INSERT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/INSERT.html): cú pháp multitable insert, ALL/FIRST, WHEN/ELSE, ánh xạ VALUES, giới hạn và ví dụ chính thức.
2. [Oracle Database 19c SQL Language Reference — Sequence Pseudocolumns](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Sequence-Pseudocolumns.html): vị trí dùng NEXTVAL/CURRVAL và cách sequence hoạt động trong multitable insert.
3. [Oracle Database 19c SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): cú pháp SELECT và UNPIVOT để chuyển cột thành dòng.
4. [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_ERRLOG](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_ERRLOG.html): tạo bảng ghi lỗi cho DML error logging.
5. [Oracle Database 19c SQL Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/): execution plan và đánh giá hiệu năng câu lệnh DML.

**Nguyên tắc cần nhớ:** INSERT ALL đánh giá mọi nhánh phù hợp nên một dòng nguồn có thể được ghi vào nhiều bảng; INSERT FIRST dừng ở nhánh WHEN đầu tiên đúng. ELSE xử lý dòng không khớp điều kiện nào. Truy vấn nguồn cung cấp các cột để WHEN và VALUES sử dụng, vì vậy cần đặt alias rõ ràng, ánh xạ đúng column list, kiểm soát NULL và xác định semantics sequence. Chọn ALL hay FIRST theo đúng quy tắc phân phối dữ liệu, rồi đối soát kết quả trước khi commit.
