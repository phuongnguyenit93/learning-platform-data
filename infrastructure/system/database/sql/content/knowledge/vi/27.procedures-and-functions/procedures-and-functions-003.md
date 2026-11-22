# Tham số đầu vào, đầu ra và kiểu trả về

Khi viết một câu `SELECT`, ta đặt điều kiện và công thức ngay trong truy vấn. Nhưng trong một ứng dụng lớn, nhiều thao tác cần được **đặt tên, tái sử dụng và nhận dữ liệu từ bên ngoài**: tính giá sau chiết khấu, trả tổng số đơn hàng của một khách, lấy danh sách đơn đạt ngưỡng hoặc bổ sung tồn kho.

**Thủ tục** (*stored procedure*) và **hàm** (*function*) giúp đóng gói những thao tác đó trong cơ sở dữ liệu. Để sử dụng đúng, trước tiên phải trả lời:

1. **Đầu vào là gì?** Người gọi phải cung cấp những tham số nào và theo kiểu dữ liệu gì?
2. **Đầu ra nằm ở đâu?** Kết quả trả qua `RETURN`, qua tham số `OUT`/`INOUT` hay qua một tập các hàng?
3. **Hình dạng kết quả là gì?** Một số, một giá trị văn bản, nhiều cột trên một hàng, nhiều hàng hay không có giá trị có ý nghĩa?
4. **Gọi bằng câu lệnh nào?** Trong PostgreSQL, một hàm thường được gọi qua `SELECT`; một thủ tục được gọi qua `CALL`.

Ví dụ:

~~~sql
-- Ham: nhan gia va phan tram giam, tra mot gia tri.
SELECT lab_r337_final_price(200.00, 15);

-- Ham tra bang: nhan ma khach, tra nhieu hang don hang.
SELECT *
FROM lab_r337_paid_orders(1);

-- Thu tuc: nhan ma hang, so luong tang va tra ton moi qua INOUT.
CALL lab_r337_add_stock('PEN', 3, NULL);
~~~

Các hàm và thủ tục trong ba dòng trên sẽ được **tạo đầy đủ** ở những mục tiếp theo; không chạy trước khi tạo bảng và routine mẫu.

Bài thuộc **Database SQL → Thủ tục và hàm**, tập trung vào **tham số đầu vào, tham số đầu ra, tham số hai chiều và kiểu trả về**. Ví dụ chính dùng **PostgreSQL với ngôn ngữ PL/pgSQL và SQL**. Cuối bài so sánh các phương ngữ MySQL, SQL Server, Oracle và SQLite để tránh nhầm một cú pháp là quy tắc chung của tất cả hệ quản trị.

## 1. Phân biệt parameter, argument và return value

Khi **định nghĩa** routine, ta khai báo **tham số** (*parameter*). Khi **gọi** routine, ta truyền **đối số** (*argument*).

~~~sql
-- p_price, p_discount_pct la PARAMETERS o phan dinh nghia.
CREATE FUNCTION some_function(
    p_price NUMERIC,
    p_discount_pct NUMERIC
)
RETURNS NUMERIC
...

-- 200.00, 15 la ARGUMENTS tai noi goi.
SELECT some_function(200.00, 15);
~~~

Đoạn trên chỉ minh họa cấu trúc, **không phải một câu `CREATE FUNCTION` hoàn chỉnh** vì thiếu phần thân thực thi.

| Khái niệm | Nghĩa |
| --- | --- |
| **Parameter** | Tên và kiểu dữ liệu được khai báo trong chữ ký hàm/thủ tục |
| **Argument** | Giá trị/biểu thức được truyền vào ở lúc gọi |
| **Parameter mode** | Cách tham số được dùng: `IN`, `OUT`, `INOUT`, đôi khi `VARIADIC` theo dialect |
| **Return type** | Kiểu dữ liệu mà hàm công bố sẽ trả về |
| **Return value** | Giá trị thực tế được gửi ra từ hàm |
| **Result set** | Tập hàng trả ra; có thể gồm một, nhiều hoặc không hàng |
| **Signature** | Thông tin định danh routine, chủ yếu gồm tên và các kiểu đối số đầu vào theo quy tắc hệ quản trị |

**Không nhầm “OUT parameter” với “RETURN expression”.** Chúng đều có thể cung cấp kết quả nhưng là hai cơ chế khác nhau. Một hàm PostgreSQL có thể trả một số qua `RETURN 42`, hoặc trả nhiều trường qua những tham số `OUT`, hoặc trả nhiều hàng qua `RETURNS TABLE`.

## 2. Ba chế độ tham số quan trọng: IN, OUT, INOUT

Trong PostgreSQL, các chế độ cơ bản là:

| Chế độ | Khi gọi truyền dữ liệu vào? | Routine đưa kết quả ra? | Ý nghĩa |
| --- | --- | --- | --- |
| **`IN`** | **Có** | Không thông qua chính tham số ấy | Nhận giá trị đầu vào |
| **`OUT`** | Không nhận giá trị đầu vào theo nghĩa nghiệp vụ | **Có** | Định nghĩa trường đầu ra |
| **`INOUT`** | **Có** | **Có** | Vừa nhận giá trị ban đầu vừa trả giá trị cuối |

Sơ đồ:

~~~text
NGUOI GOI                   HAM / THU TUC

gia tri ------- IN -------> doc va su dung

ket qua <------ OUT -------- gan gia tri trong routine

ban dau ------ INOUT -----> doc, tinh, gan lai
cuoi cung <--- INOUT ------ tra gia tri sau xu ly
~~~

### 2.1. IN: đầu vào chỉ dùng để tính hoặc lọc

Ví dụ tính giá sau giảm cần hai đầu vào: giá gốc và phần trăm giảm.

~~~sql
-- Hinh dung:
IN p_price NUMERIC
IN p_discount_pct NUMERIC
~~~

Người gọi truyền `200.00` và `15`. Routine sử dụng hai giá trị đó để tính giá **170.00**, nhưng không trả kết quả bằng cách “sửa giá trị của `p_price` trên máy người gọi”.

Trong PL/pgSQL, tên tham số đầu vào có thể được sử dụng như biến bên trong routine theo quy tắc ngôn ngữ; dù logic nội bộ có gán lại biến, điều đó **không có nghĩa tham số IN tự trở thành đầu ra của lệnh gọi**. Giao diện của routine vẫn phải được đọc theo mode và kiểu trả về.

### 2.2. OUT: định nghĩa kết quả theo tên

Một hàm tính thống kê khách có thể cần trả **hai giá trị**: số đơn PAID và tổng tiền PAID.

~~~sql
OUT p_order_count BIGINT
OUT p_total NUMERIC
~~~

Khi tạo hàm PostgreSQL với hai `OUT`, kiểu trả về được suy ra từ các trường đầu ra này. Người gọi cung cấp **đầu vào** như mã khách, còn kết quả xuất hiện dưới dạng **hàng có các cột được đặt tên**.

### 2.3. INOUT: một tham số vừa vào vừa ra

Giả sử routine nhận một số `7`, nhân đôi rồi trả `14` qua cùng tham số:

~~~sql
INOUT p_number INTEGER
~~~

Đây là **giao diện hai chiều**. Với hàm PostgreSQL, người gọi truyền giá trị qua `SELECT function_name(7)` rồi nhận kết quả của hàm; nó không trực tiếp sửa một biến SQL bên ngoài. Với `CALL` trong PL/pgSQL, một đối số `INOUT` có thể là **biến** và được gán giá trị trả về sau khi thủ tục kết thúc.

### 2.4. Mode nào là mặc định?

Trong PostgreSQL, nếu khai báo:

~~~sql
p_customer_id INTEGER
~~~

thì tham số của hàm/thủ tục có vai trò **`IN`** theo mặc định. Viết `IN p_customer_id INTEGER` làm ý định rõ hơn nhưng không bắt buộc ở mọi định nghĩa.

Đừng mặc định rằng cú pháp này có cùng ý nghĩa ở mọi SQL dialect: MySQL, SQL Server và Oracle có quy tắc khai báo đầu ra khác nhau.

## 3. Chuẩn bị bộ dữ liệu thực hành

Bài dùng hai bảng:

- `lab_r337_orders` để luyện **hàm có đầu vào, đầu ra và nhiều dạng trả về**.
- `lab_r337_inventory` để luyện **thủ tục cập nhật tồn kho, xuất giá trị qua INOUT**.

Chạy script sau **một lần trong database PostgreSQL thực hành riêng** khi chưa có hai bảng. Các routine được tạo trong bài sẽ có tiền tố `lab_r337_` để dễ phân biệt. Không thực hành các câu ghi dữ liệu trên database sản xuất.

### 3.1. Bảng đơn hàng

~~~sql
CREATE TABLE lab_r337_orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    order_status VARCHAR(12) NOT NULL
        CHECK (order_status IN ('PAID', 'PENDING', 'CANCELLED'))
);

INSERT INTO lab_r337_orders
    (order_id, customer_id, amount, order_status)
VALUES
    (1001, 1, 120.00, 'PAID'),
    (1002, 1,  80.00, 'PAID'),
    (1003, 1,  40.00, 'CANCELLED'),
    (1004, 2, 250.00, 'PAID'),
    (1005, 2,  50.00, 'PENDING'),
    (1006, 3,  90.00, 'PAID'),
    (1007, 1, 200.00, 'PAID'),
    (1008, 2,  75.00, 'PAID');
~~~

Kiểm tra:

~~~sql
SELECT order_id, customer_id, amount, order_status
FROM lab_r337_orders
ORDER BY order_id;
~~~

| Khách | Đơn PAID | Tổng PAID | Đơn không PAID |
| ---: | --- | ---: | --- |
| 1 | 1001, 1002, 1007 | 400.00 | 1003 CANCELLED |
| 2 | 1004, 1008 | 325.00 | 1005 PENDING |
| 3 | 1006 | 90.00 | Không có |
| 4 | Không có | 0.00 theo quy tắc tổng hợp | Không có |

**Số tiền trong bài là đơn vị minh họa**, không cần chuyển đổi tiền tệ. Hàm thống kê sẽ chỉ tính những hàng `order_status = 'PAID'`.

### 3.2. Bảng tồn kho

~~~sql
CREATE TABLE lab_r337_inventory (
    sku TEXT PRIMARY KEY,
    product_name TEXT NOT NULL,
    stock_qty INTEGER NOT NULL CHECK (stock_qty >= 0)
);

INSERT INTO lab_r337_inventory (sku, product_name, stock_qty)
VALUES
    ('PEN', 'Bút bi xanh', 12),
    ('NOTE', 'Sổ ghi chú', 5),
    ('MOUSE', 'Chuột máy tính', 0);
~~~

~~~sql
SELECT sku, product_name, stock_qty
FROM lab_r337_inventory
ORDER BY sku;
~~~

| sku | product_name | stock_qty |
| --- | --- | ---: |
| MOUSE | Chuột máy tính | 0 |
| NOTE | Sổ ghi chú | 5 |
| PEN | Bút bi xanh | 12 |

Trong các ví dụ thay đổi tồn kho, ta sẽ dùng **`BEGIN ... ROLLBACK`** để thử mà không làm thay đổi dữ liệu đầu vào cho các bài sau.

## 4. Hàm có tham số IN và trả về một giá trị

Mục tiêu: nhận giá gốc và phần trăm giảm; trả giá sau giảm.

### 4.1. Định nghĩa hàm PostgreSQL

~~~sql
CREATE OR REPLACE FUNCTION lab_r337_final_price(
    IN p_price NUMERIC,
    IN p_discount_pct NUMERIC
)
RETURNS NUMERIC
LANGUAGE plpgsql
IMMUTABLE
AS $fn$
BEGIN
    IF p_price IS NULL OR p_discount_pct IS NULL THEN
        RETURN NULL;
    END IF;

    IF p_price < 0 THEN
        RAISE EXCEPTION 'Price must not be negative';
    END IF;

    IF p_discount_pct < 0 OR p_discount_pct > 100 THEN
        RAISE EXCEPTION 'Discount must be between 0 and 100';
    END IF;

    RETURN ROUND(
        p_price * (1 - p_discount_pct / 100),
        2
    );
END;
$fn$;
~~~

Giải thích:

| Thành phần | Nghĩa |
| --- | --- |
| `CREATE OR REPLACE FUNCTION` | Tạo hàm hoặc thay thân/thuộc tính phù hợp khi hàm cùng chữ ký đã tồn tại |
| `IN p_price NUMERIC` | Tham số đầu vào là giá |
| `IN p_discount_pct NUMERIC` | Tham số đầu vào là phần trăm giảm |
| `RETURNS NUMERIC` | Hàm công bố kết quả thuộc kiểu số `NUMERIC` |
| `LANGUAGE plpgsql` | Phần thân viết bằng ngôn ngữ thủ tục PL/pgSQL của PostgreSQL |
| `IMMUTABLE` | Khai báo kết quả phụ thuộc cùng đầu vào trong các điều kiện xác định, không đọc trạng thái bảng/đồng hồ |
| `AS $fn$ ... $fn$` | Dollar-quoted body, tránh phải escape mọi nháy đơn trong phần thân |
| `RETURN biểu_thức;` | Kết thúc hàm và trả giá trị scalar |

`RETURN` phải phù hợp với `RETURNS NUMERIC`. Trong ví dụ, phép tính và `ROUND(..., 2)` trả số phù hợp.

### 4.2. Gọi hàm trong SELECT

~~~sql
SELECT lab_r337_final_price(200.00, 15) AS final_amount;
~~~

Kết quả:

| final_amount |
| ---: |
| 170.00 |

Vì `200 × (1 − 15/100) = 170`.

Một lời gọi khác:

~~~sql
SELECT lab_r337_final_price(125.50, 20) AS final_amount;
~~~

Kết quả **100.40**.

### 4.3. Dùng hàm với các cột của bảng

Hàm có thể được gọi trong một biểu thức của `SELECT`:

~~~sql
SELECT
    order_id,
    amount,
    lab_r337_final_price(amount, 10) AS after_10_pct_discount
FROM lab_r337_orders
WHERE order_status = 'PAID'
ORDER BY order_id;
~~~

Hàm nhận `amount` của từng hàng, tính giá sau giảm 10%. Đây là cách **tái sử dụng logic** mà không lặp công thức ở mọi truy vấn.

Không nên suy luận rằng vì hàm được viết bằng PL/pgSQL nên nó nhất định nhanh hơn biểu thức SQL trực tiếp. Lời gọi hàm có chi phí và khả năng tối ưu khác nhau; hãy đánh giá hiệu năng sau khi bảo đảm nghiệp vụ đúng.

### 4.4. Truyền NULL có ý nghĩa gì?

~~~sql
SELECT lab_r337_final_price(100.00, NULL) AS final_amount;
~~~

Hàm ở trên **chủ động trả `NULL`** nếu một tham số thiếu giá trị. Không hiểu `NULL` như số 0 hoặc như “xin dùng tham số mặc định”.

Trong ứng dụng thật, chính sách có thể khác: báo lỗi khi thiếu giảm giá, áp dụng giảm 0% hoặc trả NULL. Quan trọng là **thiết kế và ghi rõ quy tắc**, thay vì để chương trình ngầm hiểu.

## 5. Giá trị mặc định của tham số IN: DEFAULT

Không phải mọi tham số đều cần được cung cấp ở từng lần gọi. Nếu phần trăm giảm thường là **0%**, có thể khai báo:

~~~sql
CREATE OR REPLACE FUNCTION lab_r337_price_with_default(
    IN p_price NUMERIC,
    IN p_discount_pct NUMERIC DEFAULT 0
)
RETURNS NUMERIC
LANGUAGE plpgsql
IMMUTABLE
AS $fn$
BEGIN
    IF p_price IS NULL OR p_discount_pct IS NULL THEN
        RETURN NULL;
    END IF;

    IF p_price < 0
       OR p_discount_pct < 0
       OR p_discount_pct > 100 THEN
        RAISE EXCEPTION 'Invalid price or discount';
    END IF;

    RETURN ROUND(
        p_price * (1 - p_discount_pct / 100),
        2
    );
END;
$fn$;
~~~

Khi gọi:

~~~sql
SELECT lab_r337_price_with_default(200.00) AS no_discount;

SELECT lab_r337_price_with_default(200.00, 15) AS with_discount;
~~~

Kết quả lần lượt **200.00** và **170.00**.

### 5.1. DEFAULT chỉ áp dụng khi đối số được bỏ qua phù hợp

So sánh:

~~~sql
SELECT lab_r337_price_with_default(200.00);
-- p_discount_pct = 0 do DEFAULT

SELECT lab_r337_price_with_default(200.00, 0);
-- p_discount_pct = 0 do nguoi goi truyen tuong minh

SELECT lab_r337_price_with_default(200.00, NULL);
-- p_discount_pct = NULL do nguoi goi truyen; ham tra NULL
~~~

Ba lời gọi **không có cùng ý nghĩa giao diện**, dù hai lời gọi đầu có cùng giá trị đầu ra. Khi đối số được truyền `NULL` rõ ràng, PostgreSQL **không thay bằng DEFAULT**.

### 5.2. Tham số có DEFAULT thường đặt sau tham số bắt buộc

Một khai báo dễ dùng:

~~~sql
CREATE FUNCTION example(
    p_required INTEGER,
    p_optional INTEGER DEFAULT 10
)
RETURNS INTEGER ...
~~~

Trong PostgreSQL, các tham số **đầu vào** đứng sau một tham số đầu vào đã có mặc định cũng phải tuân theo quy tắc mặc định thích hợp. Đây là lý do đặt **tham số bắt buộc trước, tham số tùy chọn sau** giúp chữ ký dễ hiểu và dễ gọi theo vị trí.

Đoạn `example` chỉ minh họa bố cục chữ ký; dấu `...` không phải thân hàm hợp lệ để chạy.

## 6. Gọi theo vị trí và gọi theo tên

### 6.1. Positional notation

~~~sql
SELECT lab_r337_price_with_default(200.00, 15);
~~~

PostgreSQL ghép:

~~~text
200.00 --> p_price
15     --> p_discount_pct
~~~

Nếu đổi thứ tự hai giá trị, câu lệnh vẫn có thể **đúng kiểu số** nhưng tính sai nghiệp vụ:

~~~sql
-- Co the chay nhung khong phai y muon giam 15% cua 200:
SELECT lab_r337_price_with_default(15, 200);
~~~

Với hàm mẫu, `200` vượt ngưỡng phần trăm và gây lỗi. Trong hàm không kiểm tra giới hạn, việc đảo tham số cùng kiểu có thể tạo kết quả sai mà database không tự nhận ra.

### 6.2. Named notation

PostgreSQL có thể truyền theo tên với `=>`:

~~~sql
SELECT lab_r337_price_with_default(
    p_discount_pct => 15,
    p_price => 200.00
) AS final_amount;
~~~

Kết quả vẫn **170.00**, dù thứ tự viết đã đảo. Gọi theo tên đặc biệt hữu ích khi routine có nhiều tham số cùng kiểu, hoặc có các tham số tùy chọn.

Cũng có thể viết:

~~~sql
SELECT lab_r337_price_with_default(
    p_price => 200.00
) AS final_amount;
~~~

Tham số `p_discount_pct` không được chỉ định nên nhận `DEFAULT 0`.

### 6.3. Mixed notation

PostgreSQL cho phép phối hợp đối số vị trí và đối số tên trong những quy tắc nhất định, nhưng **các đối số vị trí cần được đặt trước phần gọi theo tên** để tránh mơ hồ. Để dễ bảo trì, hãy ưu tiên hoặc viết hoàn toàn theo vị trí khi đơn giản, hoặc theo tên khi có nhiều trường tùy chọn.

### 6.4. Tên tham số là một phần giao diện cho named call

Nếu ứng dụng gọi:

~~~sql
SELECT lab_r337_price_with_default(
    p_discount_pct => 15,
    p_price => 200.00
);
~~~

thì đổi tên `p_discount_pct` trong chữ ký có thể làm lời gọi theo tên **không còn hợp lệ**, dù số lượng và kiểu tham số không đổi. Xem tên tham số như một phần hợp đồng API nếu các ứng dụng phụ thuộc vào named notation.

## 7. Hàm có OUT: trả nhiều cột kết quả

Yêu cầu: nhập `customer_id`, trả **số đơn PAID** và **tổng số tiền PAID**.

Trong PostgreSQL, hai `OUT` có thể mô tả hình dạng bản ghi trả về.

### 7.1. Định nghĩa hàm

~~~sql
CREATE OR REPLACE FUNCTION lab_r337_paid_summary(
    IN p_customer_id INTEGER,
    OUT p_order_count BIGINT,
    OUT p_total NUMERIC
)
LANGUAGE plpgsql
STABLE
AS $fn$
BEGIN
    SELECT
        COUNT(*),
        COALESCE(SUM(o.amount), 0)
    INTO
        p_order_count,
        p_total
    FROM lab_r337_orders AS o
    WHERE o.customer_id = p_customer_id
      AND o.order_status = 'PAID';
END;
$fn$;
~~~

Để ý hàm này **không ghi `RETURNS RECORD` tường minh**. PostgreSQL suy ra kiểu kết quả từ **hai tham số `OUT`**. Với hai trường đầu ra, kết quả có dạng composite/record gồm `p_order_count` và `p_total`.

Trong PL/pgSQL, khi hàm có `OUT`, các tham số đó hoạt động như **biến đầu ra**. Trong ví dụ, `SELECT ... INTO ...` gán các giá trị kết quả vào biến. Hàm đi tới cuối thân và trả những giá trị đầu ra đã gán.

**Lưu ý về `SELECT ... INTO`:** trong **PL/pgSQL**, cú pháp trên là **gán kết quả truy vấn vào biến**, khác với `SELECT INTO` theo ngữ cảnh SQL dùng tạo bảng ở một số hệ hoặc phiên bản. Khi viết routine, luôn xác định ngôn ngữ thực thi.

### 7.2. Gọi hàm có OUT

~~~sql
SELECT *
FROM lab_r337_paid_summary(1);
~~~

Kết quả:

| p_order_count | p_total |
| ---: | ---: |
| 3 | 400.00 |

Với khách 2:

~~~sql
SELECT *
FROM lab_r337_paid_summary(2);
~~~

| p_order_count | p_total |
| ---: | ---: |
| 2 | 325.00 |

Người gọi truyền **một đối số** `p_customer_id`. Hai `OUT` **không phải các đối số đầu vào cần cung cấp** khi gọi hàm qua `SELECT`.

### 7.3. Nếu khách không có đơn PAID?

~~~sql
SELECT *
FROM lab_r337_paid_summary(4);
~~~

Kết quả:

| p_order_count | p_total |
| ---: | ---: |
| 0 | 0.00 |

Vì `COUNT(*)` trên tập rỗng cho **0**, `SUM(amount)` trên tập rỗng cho **NULL**, còn `COALESCE(..., 0)` đưa tổng về **0 theo quy tắc báo cáo của bài**.

Hàm **trả một hàng thống kê với số 0**, không phải “trả tập rỗng”. Sự khác biệt với hàm `RETURNS TABLE` khi không có đơn hàng sẽ được giải thích sau.

### 7.4. OUT khác RETURN expression như thế nào?

Với hàm scalar:

~~~sql
RETURN ROUND(..., 2);
~~~

đối tượng trả về là **giá trị của biểu thức**. Với hàm có `OUT`:

~~~sql
p_order_count := 3;
p_total := 400;
RETURN;
~~~

`RETURN;` (không có biểu thức) trả các **biến OUT hiện tại**. Trong PL/pgSQL, `RETURN biểu_thức;` **không phải cách phù hợp** cho một hàm đã khai báo đầu ra bằng `OUT`/`INOUT`.

Không cần viết `RETURN;` ở cuối ví dụ `lab_r337_paid_summary` vì hàm có OUT có thể kết thúc thân và trả trạng thái các biến OUT. Viết `RETURN;` tường minh cũng có thể làm luồng xử lý dễ nhận diện hơn khi thoát sớm.

## 8. Hàm INOUT: nhận và trả cùng một tham số

Tạo một hàm nhỏ:

~~~sql
CREATE OR REPLACE FUNCTION lab_r337_double(
    INOUT p_number INTEGER
)
LANGUAGE plpgsql
IMMUTABLE
AS $fn$
BEGIN
    IF p_number IS NOT NULL THEN
        p_number := p_number * 2;
    END IF;
END;
$fn$;
~~~

Gọi:

~~~sql
SELECT lab_r337_double(7) AS doubled;
~~~

Kết quả:

| doubled |
| ---: |
| 14 |

`p_number` ban đầu nhận **7**, được gán lại thành **14**, và giá trị cuối của tham số `INOUT` được dùng làm kết quả của hàm.

### 8.1. INOUT có phải là cơ chế sửa biến của SQL Editor?

Không. Khi viết:

~~~sql
SELECT lab_r337_double(7);
~~~

`7` là một literal; PostgreSQL trả kết quả **14** cho truy vấn. Nó không thể “sửa literal 7” hay tự thay đổi một biến bên ngoài. `INOUT` mô tả giao diện hai chiều của routine; hình thức nhận kết quả cụ thể phụ thuộc **hàm hay thủ tục** và **ngữ cảnh gọi**.

### 8.2. Nếu đầu vào là NULL?

~~~sql
SELECT lab_r337_double(NULL::INTEGER) AS doubled;
~~~

Hàm ở trên không thực hiện phép nhân và trả **NULL**. Việc ghi `::INTEGER` làm kiểu đối số rõ ràng; nó cũng hữu ích nếu có nhiều overload cùng tên mà `NULL` không tự xác định được kiểu đích.

### 8.3. Khi nào nên dùng INOUT?

`INOUT` có thể thuận tiện cho một phép biến đổi trên một giá trị đang có. Tuy nhiên, với **hàm scalar thuần túy**, giao diện:

~~~sql
CREATE FUNCTION double_number(p_number INTEGER)
RETURNS INTEGER ...
~~~

thường dễ hiểu với người dùng SQL hơn một `INOUT` nếu đầu ra chỉ là kết quả số. `INOUT` được sử dụng rất rõ ràng trong thủ tục, nơi các biến đầu vào có thể được trả giá trị mới sau `CALL` trong ngôn ngữ thủ tục của hệ quản trị.

## 9. RETURNS: hàm phải khai báo kiểu trả về phù hợp

Trong PostgreSQL, hàm có thể khai báo nhiều hình dạng kết quả:

| Khai báo | Hình dạng kết quả | Ví dụ |
| --- | --- | --- |
| `RETURNS INTEGER` | Một giá trị nguyên | Đếm theo cách trả scalar |
| `RETURNS NUMERIC` | Một giá trị số thập phân | Tính giá |
| `RETURNS TEXT` | Một chuỗi | Chuẩn hóa/định dạng mã |
| `RETURNS BOOLEAN` | Một giá trị TRUE/FALSE/NULL | Kiểm tra điều kiện |
| `RETURNS DATE` / `TIMESTAMP` | Một ngày/thời điểm | Tính kỳ hạn |
| `RETURNS VOID` | Không có giá trị nghiệp vụ cần lấy | Hàm thực hiện hành động được cho phép |
| `RETURNS RECORD` | Một bản ghi có cấu trúc được xác định khi sử dụng | Trả nhiều trường không khai báo OUT |
| `RETURNS TABLE (c1 type, ...)` | **Tập các hàng** có cột đặt tên | Danh sách đơn hàng |
| `RETURNS SETOF INTEGER` | **Tập các giá trị nguyên** | Danh sách ID đơn |
| `RETURNS SETOF some_composite_type` | **Tập các hàng theo một kiểu composite** | Các hàng của bảng/kiểu đã khai báo |

**Kết quả một giá trị** khác **kết quả nhiều hàng**. Một hàm trả `NUMERIC` thông thường không tự biến thành danh sách nếu bên trong nó viết một truy vấn có nhiều bản ghi.

### 9.1. Kiểu dữ liệu cần phù hợp với RETURN

Ví dụ:

~~~sql
CREATE OR REPLACE FUNCTION lab_r337_plus_one(
    IN p_number INTEGER
)
RETURNS INTEGER
LANGUAGE sql
IMMUTABLE
AS $sql$
    SELECT p_number + 1;
$sql$;
~~~

~~~sql
SELECT lab_r337_plus_one(9) AS result;
~~~

Kết quả **10**.

Nếu phần thân trả giá trị không tương thích với kiểu đã khai báo, PostgreSQL có thể báo lỗi ở **lúc tạo hàm hoặc lúc chạy**, tùy ngôn ngữ và dạng kiểm tra. Một kiểu có thể ép ngầm được cũng không nên là lý do thiết kế giao diện mơ hồ.

### 9.2. Số liệu tài chính: ưu tiên NUMERIC

Trong ví dụ giá tiền, `NUMERIC` giúp biểu diễn số thập phân chính xác theo quy tắc decimal, phù hợp nhiều phép tính tiền tệ. `REAL`/`DOUBLE PRECISION` là số dấu phẩy động nhị phân, có thể có sai số biểu diễn và cần chính sách làm tròn.

Hàm trả `NUMERIC` không tự giải quyết mọi yêu cầu tài chính: vẫn cần quy định đơn vị tiền, thời điểm tính, thuế, quy tắc làm tròn và xử lý ngoại lệ.

### 9.3. OUT parameters và RETURNS TABLE không dùng chồng lên nhau tùy ý

Trong PostgreSQL, `RETURNS TABLE (column_name type, ...)` là cách khai báo **các cột đầu ra** của hàm trả tập hàng, với ngữ nghĩa tương đương một nhóm đầu ra được định nghĩa cho tập kết quả. Vì vậy không viết đồng thời `RETURNS TABLE(...)` và danh sách `OUT`/`INOUT` riêng như thể có hai schema đầu ra độc lập.

Hãy chọn một hình thức phù hợp:

- Muốn **một hàng có nhiều trường**: các tham số `OUT` là lựa chọn rõ.
- Muốn **tập hàng có cột đặt tên**: `RETURNS TABLE(...)`.
- Muốn **tập scalar cùng kiểu**: `RETURNS SETOF type`.

## 10. RETURNS TABLE: đầu ra gồm nhiều hàng, nhiều cột

Giả sử cần lấy những đơn PAID của một khách, có thể lọc theo **giá trị tối thiểu**.

### 10.1. Định nghĩa hàm trả bảng

~~~sql
CREATE OR REPLACE FUNCTION lab_r337_paid_orders(
    IN p_customer_id INTEGER,
    IN p_min_amount NUMERIC DEFAULT 0
)
RETURNS TABLE (
    order_id INTEGER,
    paid_amount NUMERIC
)
LANGUAGE plpgsql
STABLE
AS $fn$
BEGIN
    RETURN QUERY
    SELECT
        o.order_id,
        o.amount
    FROM lab_r337_orders AS o
    WHERE o.customer_id = p_customer_id
      AND o.order_status = 'PAID'
      AND o.amount >= p_min_amount
    ORDER BY o.order_id;
END;
$fn$;
~~~

Các thành phần:

- `p_customer_id`: tham số **IN bắt buộc**.
- `p_min_amount`: tham số **IN tùy chọn** với mặc định 0.
- `RETURNS TABLE(order_id INTEGER, paid_amount NUMERIC)`: kết quả có **hai cột** với tên/kiểu xác định.
- `RETURN QUERY SELECT ...`: bổ sung các **hàng từ truy vấn** vào tập kết quả của hàm PL/pgSQL.

Ở hàm này, `order_id` trong `RETURNS TABLE` cũng là một **tên biến đầu ra** trong PL/pgSQL, nên câu `SELECT` viết `o.order_id` với bí danh bảng rõ ràng. Điều này tránh mơ hồ giữa cột trong bảng và biến của hàm.

### 10.2. Gọi hàm trả bảng

~~~sql
SELECT *
FROM lab_r337_paid_orders(1)
ORDER BY order_id;
~~~

Kết quả:

| order_id | paid_amount |
| ---: | ---: |
| 1001 | 120.00 |
| 1002 | 80.00 |
| 1007 | 200.00 |

Gọi với ngưỡng:

~~~sql
SELECT *
FROM lab_r337_paid_orders(1, 100)
ORDER BY order_id;
~~~

| order_id | paid_amount |
| ---: | ---: |
| 1001 | 120.00 |
| 1007 | 200.00 |

Đơn 1002 có giá trị 80 nên không đạt ngưỡng 100. Đơn 1003 CANCELLED nên không được trả dù thuộc khách 1.

### 10.3. Không có hàng phù hợp thì trả gì?

~~~sql
SELECT *
FROM lab_r337_paid_orders(4);
~~~

Kết quả là **tập rỗng, 0 hàng**. Nó **không tự trả một hàng gồm hai giá trị NULL** và cũng không tự trả một hàng tổng bằng 0.

So với:

~~~sql
SELECT *
FROM lab_r337_paid_summary(4);
~~~

hàm thống kê dùng `COUNT/SUM` với `OUT` trả **một hàng `0, 0`**. Một bên là **danh sách đơn hàng**, một bên là **bản ghi tổng hợp**; hai hợp đồng đầu ra khác nhau.

### 10.4. RETURNS TABLE có thể dùng trực tiếp trong JOIN

~~~sql
SELECT
    p.order_id,
    p.paid_amount
FROM lab_r337_paid_orders(2) AS p
WHERE p.paid_amount >= 100
ORDER BY p.order_id;
~~~

Khách 2 có hai đơn PAID: 250 và 75. Sau lọc ngưỡng 100, chỉ còn **order_id 1004** với số tiền **250.00**.

Một hàm trả bảng có thể xuất hiện trong `FROM` như một nguồn hàng, nhưng điều đó không có nghĩa nó là một bảng thường trực lưu dữ liệu. Các hàng vẫn được tạo theo ngữ nghĩa thực thi hàm tại thời điểm gọi.

## 11. RETURNS SETOF: trả nhiều giá trị hoặc nhiều hàng

`SETOF` cho biết hàm có thể trả **nhiều phần tử** thuộc cùng kiểu.

### 11.1. SETOF INTEGER

~~~sql
CREATE OR REPLACE FUNCTION lab_r337_paid_order_ids(
    IN p_customer_id INTEGER
)
RETURNS SETOF INTEGER
LANGUAGE sql
STABLE
AS $sql$
    SELECT o.order_id
    FROM lab_r337_orders AS o
    WHERE o.customer_id = p_customer_id
      AND o.order_status = 'PAID'
    ORDER BY o.order_id;
$sql$;
~~~

Gọi qua `FROM`:

~~~sql
SELECT id.order_id
FROM lab_r337_paid_order_ids(2) AS id(order_id)
ORDER BY id.order_id;
~~~

Kết quả là **1004** và **1008**, mỗi ID là một hàng.

### 11.2. SETOF không phải ARRAY

Hai hợp đồng khác nhau:

| Khai báo | Ý nghĩa |
| --- | --- |
| `RETURNS SETOF INTEGER` | Trả nhiều **hàng**, mỗi hàng chứa một integer |
| `RETURNS INTEGER[]` | Trả **một giá trị kiểu mảng integer**; mảng có thể chứa nhiều phần tử |

Khi dùng SQL, một hàm trả tập hàng thường dễ kết hợp với `FROM`, `JOIN`, `WHERE` và các thao tác quan hệ. Một mảng phù hợp khi người gọi thực sự cần **một giá trị cấu trúc array**. Không chọn kiểu chỉ vì cả hai “có nhiều số”.

### 11.3. SETOF kiểu composite

PostgreSQL còn có thể trả tập các hàng với cấu trúc của một bảng:

~~~sql
CREATE OR REPLACE FUNCTION lab_r337_customer_order_rows(
    IN p_customer_id INTEGER
)
RETURNS SETOF lab_r337_orders
LANGUAGE sql
STABLE
AS $sql$
    SELECT o.*
    FROM lab_r337_orders AS o
    WHERE o.customer_id = p_customer_id
    ORDER BY o.order_id;
$sql$;
~~~

~~~sql
SELECT order_id, amount, order_status
FROM lab_r337_customer_order_rows(1)
ORDER BY order_id;
~~~

Kết quả gồm các đơn **1001, 1002, 1003, 1007** của khách 1, bao gồm cả đơn CANCELLED vì hàm này **không lọc `order_status`**. Khác `lab_r337_paid_orders`, nó trả **toàn bộ cột của kiểu hàng bảng nguồn**.

**Đánh đổi:** khi gắn kiểu trả về trực tiếp với kiểu của một bảng, thay đổi cấu trúc bảng có thể ảnh hưởng các routine phụ thuộc. `RETURNS TABLE(...)` với cột chọn rõ ràng thường tạo giao diện ổn định hơn nếu không muốn public toàn bộ schema nội bộ.

## 12. RETURN, RETURN NEXT và RETURN QUERY khác nhau thế nào?

Đây là ba cú pháp dễ nhầm trong PL/pgSQL:

| Cú pháp | Dùng với | Tác động |
| --- | --- | --- |
| `RETURN expression;` | Hàm trả **một giá trị** không qua OUT | Kết thúc hàm và trả giá trị đó |
| `RETURN;` | Hàm có OUT/INOUT, hàm set-returning khi muốn kết thúc | Kết thúc, trả giá trị OUT hiện tại hoặc hoàn tất tập kết quả |
| `RETURN NEXT expression;` | Hàm `RETURNS SETOF ...` | Bổ sung **một phần tử/hàng** vào tập kết quả |
| `RETURN QUERY SELECT ...;` | Hàm trả tập kết quả | Bổ sung **nhiều hàng từ truy vấn** vào tập kết quả |

### 12.1. Ví dụ RETURN scalar

~~~sql
CREATE OR REPLACE FUNCTION lab_r337_is_large(
    IN p_amount NUMERIC
)
RETURNS BOOLEAN
LANGUAGE plpgsql
IMMUTABLE
AS $fn$
BEGIN
    IF p_amount IS NULL THEN
        RETURN NULL;
    END IF;

    RETURN p_amount >= 100;
END;
$fn$;
~~~

~~~sql
SELECT
    lab_r337_is_large(120.00) AS large_120,
    lab_r337_is_large(80.00) AS large_80,
    lab_r337_is_large(NULL) AS large_null;
~~~

Kết quả logic: **TRUE**, **FALSE**, **NULL**.

### 12.2. Ví dụ RETURN NEXT

~~~sql
CREATE OR REPLACE FUNCTION lab_r337_sequence(
    IN p_max INTEGER
)
RETURNS SETOF INTEGER
LANGUAGE plpgsql
IMMUTABLE
AS $fn$
DECLARE
    v_num INTEGER;
BEGIN
    IF p_max IS NULL OR p_max < 1 THEN
        RETURN;
    END IF;

    FOR v_num IN 1..p_max LOOP
        RETURN NEXT v_num;
    END LOOP;

    RETURN;
END;
$fn$;
~~~

~~~sql
SELECT number_value
FROM lab_r337_sequence(4) AS s(number_value);
~~~

Kết quả gồm bốn hàng **1, 2, 3, 4**. `RETURN NEXT` **không kết thúc toàn bộ hàm ngay**; nó thêm một phần tử vào tập kết quả, rồi vòng lặp có thể tiếp tục. `RETURN;` cuối cùng kết thúc hàm.

Với `p_max = 0`, ví dụ trả **tập rỗng**, không trả một hàng chứa số 0.

### 12.3. Ví dụ RETURN QUERY

Hàm `lab_r337_paid_orders` đã sử dụng:

~~~sql
RETURN QUERY
SELECT o.order_id, o.amount
FROM lab_r337_orders AS o
WHERE ...;
~~~

`RETURN QUERY` đưa toàn bộ các hàng do truy vấn trả về vào tập kết quả. Nếu cần, một hàm PL/pgSQL có thể dùng nhiều `RETURN QUERY` hoặc kết hợp `RETURN NEXT` để tích lũy các phần tử theo logic rõ ràng.

**Không viết `RETURN QUERY` trong một hàm chỉ khai báo `RETURNS INTEGER` rồi kỳ vọng nó được phép trả nhiều hàng.** Phần khai báo kiểu trả về và cách `RETURN` phải tương thích.

## 13. RETURNS RECORD: kiểu bản ghi linh hoạt nhưng cần mô tả đầu ra

`RECORD` là kiểu bản ghi có cấu trúc không được cố định bằng một định nghĩa composite riêng ở thời điểm khai báo hàm.

Ví dụ:

~~~sql
CREATE OR REPLACE FUNCTION lab_r337_one_order_record(
    IN p_order_id INTEGER
)
RETURNS RECORD
LANGUAGE sql
STABLE
AS $sql$
    SELECT
        o.order_id,
        o.amount
    FROM lab_r337_orders AS o
    WHERE o.order_id = p_order_id;
$sql$;
~~~

Để PostgreSQL biết **tên và kiểu các cột** khi dùng hàm trả `RECORD` không có OUT cố định, người gọi có thể cung cấp danh sách định nghĩa cột:

~~~sql
SELECT r.order_id, r.amount
FROM lab_r337_one_order_record(1001)
    AS r(order_id INTEGER, amount NUMERIC);
~~~

Kết quả **1001, 120.00**.

### 13.1. Vì sao RECORD khó dùng hơn RETURNS TABLE?

So sánh:

~~~sql
-- RETURNS TABLE da co thong tin cot:
SELECT * FROM lab_r337_paid_orders(1);

-- RECORD chua biet cau truc khi goi trong FROM:
SELECT * FROM lab_r337_one_order_record(1001)
    AS r(order_id INTEGER, amount NUMERIC);
~~~

Với `RETURNS TABLE`, interface đã nói rõ các cột. Với `RETURNS RECORD` tổng quát, người gọi có thể cần khai báo cấu trúc cụ thể và đảm bảo nó khớp kết quả thực.

**Nên ưu tiên kiểu đầu ra cụ thể khi hợp đồng dữ liệu ổn định.** `RECORD` hữu ích trong một số routine động, nhưng không tự làm cho mọi thay đổi schema trở nên an toàn.

### 13.2. OUT nhiều cột cũng liên quan tới bản ghi

Hàm `lab_r337_paid_summary` có **hai OUT** nên tự tạo giao diện kết quả composite/record có tên cột. Đừng nhầm việc PostgreSQL suy ra kết quả từ `OUT` với một hàm `RETURNS RECORD` không khai báo hình dạng đầu ra.

## 14. RETURNS VOID: không có giá trị nghiệp vụ, nhưng vẫn là FUNCTION

Một hàm có thể công bố `RETURNS VOID`:

~~~sql
CREATE OR REPLACE FUNCTION lab_r337_debug_notice(
    IN p_message TEXT
)
RETURNS VOID
LANGUAGE plpgsql
VOLATILE
AS $fn$
BEGIN
    RAISE NOTICE 'Debug: %', p_message;
END;
$fn$;
~~~

Gọi:

~~~sql
SELECT lab_r337_debug_notice('Hello SQL');
~~~

PostgreSQL phát một thông báo `NOTICE`, tùy công cụ khách hàng có thể hiển thị ở vùng Messages/Logs. Hàm trả kiểu **`VOID`**, không có một giá trị nghiệp vụ như số tiền hay danh sách đơn.

### 14.1. VOID không biến FUNCTION thành PROCEDURE

| Khai báo | Cách gọi PostgreSQL |
| --- | --- |
| `CREATE FUNCTION ... RETURNS VOID` | `SELECT function_name(...)` |
| `CREATE PROCEDURE ...` | `CALL procedure_name(...)` |

Một hàm `RETURNS VOID` **vẫn là function**. Ngược lại, thủ tục PostgreSQL **không khai báo `RETURNS VOID`**: cú pháp `CREATE PROCEDURE` không có một mệnh đề `RETURNS` giống `CREATE FUNCTION`.

### 14.2. Có nên dùng FUNCTION VOID để thay mọi thủ tục?

Không. Nên chọn routine theo:

- Cách gọi cần thiết.
- Khả năng trả giá trị/tập kết quả.
- Tác dụng phụ cho phép.
- Quy tắc quản lý transaction.
- Thiết kế API của ứng dụng và SQL dialect.

PostgreSQL function có thể thực hiện một số thao tác thay đổi dữ liệu khi được định nghĩa/đánh dấu thích hợp, nhưng **không được dùng `COMMIT`/`ROLLBACK` để tự kết thúc transaction của người gọi** như khả năng điều khiển transaction trong một số procedure được gọi đúng ngữ cảnh.

## 15. PROCEDURE: dùng CALL thay vì SELECT

PostgreSQL hỗ trợ **stored procedure** từ phiên bản **11**. Phần khai báo:

~~~sql
CREATE PROCEDURE procedure_name(...)
LANGUAGE plpgsql
AS $body$
BEGIN
    -- SQL va logic nghiep vu
END;
$body$;
~~~

Khác với hàm, thủ tục PostgreSQL **không có mệnh đề `RETURNS kiểu`**. Thủ tục được gọi bằng `CALL`:

~~~sql
CALL procedure_name(...);
~~~

Thủ tục có thể có tham số `IN`, `INOUT` và, ở các phiên bản PostgreSQL hỗ trợ, `OUT`. Kết quả đầu ra của `CALL` có thể xuất hiện như một hàng kết quả với các cột OUT/INOUT.

### 15.1. PROCEDURE không phải “hàm trả void có tên khác”

| Đặc điểm | FUNCTION PostgreSQL | PROCEDURE PostgreSQL |
| --- | --- | --- |
| Định nghĩa | `CREATE FUNCTION` | `CREATE PROCEDURE` |
| Gọi thông thường | Trong `SELECT` hoặc biểu thức SQL phù hợp | `CALL` |
| Công bố kiểu trả về | `RETURNS type`, `RETURNS TABLE`, `SETOF`, hoặc suy ra từ OUT | Không có `RETURNS` của function |
| Có thể trả tập hàng như một nguồn `FROM`? | Có, nếu là set-returning function | Không theo cú pháp `SELECT * FROM procedure(...)` |
| OUT/INOUT | Có | Có theo phiên bản và cú pháp |
| Điều khiển transaction | Không tự `COMMIT`/`ROLLBACK` | Có khả năng trong **điều kiện gọi hạn chế** |
| Phù hợp | Tính toán, truy vấn có interface kết quả | Thao tác nghiệp vụ nhiều câu lệnh, kết quả qua tham số nếu cần |

Một thủ tục **không phải** lời đảm bảo rằng mọi thao tác bên trong tự động được commit. Transaction vẫn phải được quản lý theo ngữ cảnh và quy tắc PostgreSQL.

## 16. Thủ tục IN và INOUT: tăng tồn kho và trả tồn mới

Ta tạo thủ tục có ba tham số:

1. `IN p_sku TEXT`: mã sản phẩm cần cập nhật.
2. `IN p_increase INTEGER`: số lượng tăng thêm, phải lớn hơn 0.
3. `INOUT p_new_stock INTEGER`: nhận một đối số lúc gọi và trả **tồn mới** sau khi thay đổi; trong ví dụ giá trị đầu vào của tham số này không được sử dụng.

### 16.1. Định nghĩa

~~~sql
CREATE OR REPLACE PROCEDURE lab_r337_add_stock(
    IN p_sku TEXT,
    IN p_increase INTEGER,
    INOUT p_new_stock INTEGER
)
LANGUAGE plpgsql
AS $proc$
BEGIN
    IF p_sku IS NULL OR p_sku = '' THEN
        RAISE EXCEPTION 'SKU is required';
    END IF;

    IF p_increase IS NULL OR p_increase <= 0 THEN
        RAISE EXCEPTION 'Increase must be positive';
    END IF;

    UPDATE lab_r337_inventory AS inv
    SET stock_qty = inv.stock_qty + p_increase
    WHERE inv.sku = p_sku
    RETURNING inv.stock_qty INTO p_new_stock;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'SKU % does not exist', p_sku;
    END IF;
END;
$proc$;
~~~

Giải thích:

- `UPDATE ... SET stock_qty = stock_qty + p_increase` thực sự thay đổi bảng.
- `RETURNING ... INTO p_new_stock` lấy tồn mới và gán vào biến `INOUT`.
- `IF NOT FOUND` giúp báo lỗi nếu không tìm thấy sản phẩm có mã đã nhập.
- Phần thân **không có `RETURNS INTEGER`** và cũng không `RETURN p_new_stock`; kết quả được đưa ra bằng tham số `INOUT` của thủ tục.

### 16.2. Gọi CALL và quan sát kết quả

~~~sql
BEGIN;

CALL lab_r337_add_stock('PEN', 3, NULL);

SELECT sku, stock_qty
FROM lab_r337_inventory
WHERE sku = 'PEN';

ROLLBACK;
~~~

Với dữ liệu ban đầu, `PEN` có tồn 12. `CALL` tăng thêm 3 và trả hàng kết quả có cột `p_new_stock = 15`. Câu `SELECT` tiếp theo trong cùng transaction cũng nhìn thấy `stock_qty = 15`.

Sau `ROLLBACK`, `PEN` trở về tồn **12**.

**Tại sao `CALL` viết `NULL` ở đối số thứ ba?** Vì `p_new_stock` là `INOUT`, cú pháp `CALL` từ SQL yêu cầu một đối số tương ứng; ví dụ không cần giá trị ban đầu nên truyền `NULL`, thủ tục sẽ gán lại tồn mới. Điều đó không có nghĩa PostgreSQL không trả kết quả: hàng `CALL` vẫn có giá trị `p_new_stock` sau thủ tục.

### 16.3. Gọi cùng thủ tục với biến PL/pgSQL

Trong một khối PL/pgSQL, đối số `INOUT` phải là biến có thể nhận giá trị trả về:

~~~sql
BEGIN;

DO $do$
DECLARE
    v_new_stock INTEGER := NULL;
BEGIN
    CALL lab_r337_add_stock('NOTE', 2, v_new_stock);
    RAISE NOTICE 'New stock is %', v_new_stock;
END;
$do$;

ROLLBACK;
~~~

Trong ví dụ, `NOTE` từ 5 tăng tạm lên **7**; `v_new_stock` được gán 7, rồi transaction ngoài rollback nên tồn kho trở về 5.

So sánh hai tình huống:

| Nơi gọi | Đối số cho INOUT | Cách nhận giá trị |
| --- | --- | --- |
| SQL trực tiếp | `CALL ... (..., NULL)` | Hàng kết quả từ `CALL` |
| Khối PL/pgSQL | `CALL ... (..., v_new_stock)` | Biến `v_new_stock` được gán giá trị trả về |

Đừng nhầm một literal `NULL` ở lệnh gọi SQL với một biến được phép gán trong ngôn ngữ PL/pgSQL.

### 16.4. Chỉ số hàng cập nhật không thay thế OUT

Một thủ tục có thể sửa hàng nhưng không công bố tham số OUT/INOUT. Khi ấy `CALL` có thể không trả hàng dữ liệu nào. Nếu ứng dụng cần biết tồn mới, hãy thiết kế **OUT/INOUT** rõ ràng hoặc đọc lại dữ liệu trong transaction phù hợp. Không đoán tồn mới bằng cách cộng số lượng ở ứng dụng mà bỏ qua kiểm tra thành công thực tế.

## 17. Thủ tục với OUT: trả thống kê không cần biến đầu vào hai chiều

PostgreSQL **14 trở lên** hỗ trợ tham số `OUT` cho thủ tục. Với phiên bản không hỗ trợ, có thể dùng `INOUT` hoặc cách khác phù hợp.

### 17.1. Định nghĩa thủ tục OUT

~~~sql
CREATE OR REPLACE PROCEDURE lab_r337_get_paid_stats(
    IN p_customer_id INTEGER,
    OUT p_paid_count BIGINT,
    OUT p_paid_total NUMERIC
)
LANGUAGE plpgsql
AS $proc$
BEGIN
    SELECT
        COUNT(*),
        COALESCE(SUM(o.amount), 0)
    INTO
        p_paid_count,
        p_paid_total
    FROM lab_r337_orders AS o
    WHERE o.customer_id = p_customer_id
      AND o.order_status = 'PAID';
END;
$proc$;
~~~

Đây là **procedure**, không phải function, dù bên trong thực hiện một truy vấn thống kê. Nó không dùng `RETURNS TABLE`; đầu ra gồm hai tham số `OUT`.

### 17.2. Gọi từ SQL

~~~sql
CALL lab_r337_get_paid_stats(2, NULL, NULL);
~~~

Với PostgreSQL ở ngữ cảnh `CALL` từ SQL, cần cung cấp vị trí đối số cho những `OUT` chưa có mặc định; theo thực hành thông dụng dùng `NULL` làm **placeholder**. Các đối số `OUT` này **không được đánh giá như giá trị đầu vào**. Kết quả `CALL` có một hàng:

| p_paid_count | p_paid_total |
| ---: | ---: |
| 2 | 325.00 |

Trong PL/pgSQL thì khác:

~~~sql
DO $do$
DECLARE
    v_count BIGINT;
    v_total NUMERIC;
BEGIN
    CALL lab_r337_get_paid_stats(1, v_count, v_total);
    RAISE NOTICE 'Paid orders: %, total: %', v_count, v_total;
END;
$do$;
~~~

Hai biến `v_count` và `v_total` nhận **3** và **400.00**.

### 17.3. OUT của function và OUT của procedure: giống mục đích, khác lối gọi

| Routine | Khai báo đầu ra | Lệnh gọi |
| --- | --- | --- |
| `lab_r337_paid_summary` (function) | Hai tham số `OUT` | `SELECT * FROM lab_r337_paid_summary(1);` |
| `lab_r337_get_paid_stats` (procedure) | Hai tham số `OUT` | `CALL lab_r337_get_paid_stats(1, NULL, NULL);` |

Không dùng `CALL lab_r337_paid_summary(...)` hoặc `SELECT * FROM lab_r337_get_paid_stats(...)`: PostgreSQL phân biệt loại routine khi phân tích cú pháp và gọi.

## 18. Function và procedure khác nhau về transaction

Một điểm quan trọng khi chọn thủ tục là **khả năng điều khiển giao dịch** theo ngữ cảnh. Trong PostgreSQL:

- **Function** không thể tự gọi `COMMIT`/`ROLLBACK` để kết thúc transaction của câu SQL đang gọi nó.
- **Procedure** có thể thực hiện điều khiển transaction trong **những điều kiện được PostgreSQL cho phép**, ví dụ lời gọi `CALL` ở ngữ cảnh top-level thích hợp, không nằm trong một explicit transaction block cấm điều khiển transaction bên trong.
- Nếu gọi `CALL` bên trong `BEGIN ... COMMIT` do ứng dụng mở, **procedure không được tự tùy ý COMMIT/ROLLBACK transaction đó**.
- Một số thuộc tính của procedure, chẳng hạn `SECURITY DEFINER` hoặc mệnh đề `SET` gắn với routine, có thể hạn chế khả năng điều khiển transaction.

### 18.1. Ví dụ thủ tục của bài không tự commit

~~~sql
BEGIN;

CALL lab_r337_add_stock('PEN', 3, NULL);

-- Neu chua COMMIT, thay doi van thuoc transaction nay.
ROLLBACK;
~~~

Thủ tục `lab_r337_add_stock` không chứa `COMMIT`, nên việc nó thực thi một `UPDATE` **không khiến thay đổi tự lưu vĩnh viễn** khi transaction ngoài chưa commit.

### 18.2. Không tạo procedure chỉ để gọi COMMIT

Nếu nghiệp vụ chỉ cần tính một giá trị, function thường là interface tự nhiên hơn. Nếu cần thực thi nhiều bước ghi có transaction, procedure có thể phù hợp, nhưng không phải procedure nào cũng nên chứa lệnh commit. Quy tắc transaction cần được thiết kế cùng ứng dụng và cơ chế xử lý lỗi.

Không nên lạm dụng `COMMIT` bên trong routine vì một ứng dụng muốn kiểm soát **nhiều thao tác như một giao dịch duy nhất** có thể không cho phép routine tự chia nhỏ transaction.

## 19. NULL, DEFAULT và đầu ra chưa được gán

### 19.1. NULL là một đối số thật

~~~sql
SELECT lab_r337_price_with_default(100.00, NULL);
~~~

Ở đây tham số thứ hai nhận `NULL`; không thay bằng mặc định 0. Khi định nghĩa, bạn quyết định kết quả:

- Trả `NULL`.
- Dùng `COALESCE` để quy về một giá trị.
- `RAISE EXCEPTION` nếu đầu vào thiếu là lỗi.

Không có quy tắc áp dụng mặc định tự động chỉ vì một đối số có giá trị `NULL`.

### 19.2. OUT chưa được gán có thể là NULL

Trong PL/pgSQL, biến OUT có kiểu dữ liệu và có trạng thái ban đầu tương tự biến PL/pgSQL; nếu thân routine không gán giá trị trước khi trả, nó có thể trả **`NULL`**.

Vì thế:

~~~sql
-- Pseudocode:
IF dieu_kien THEN
    p_result := 10;
END IF;
-- Neu dieu_kien sai, p_result se ra sao?
~~~

Nếu `p_result` chưa được khởi tạo hoặc chưa được gán, kết quả có thể là NULL. Với đầu ra bắt buộc, hãy bảo đảm **mọi nhánh logic đều gán giá trị hợp lệ** hoặc có quy tắc xử lý lỗi.

### 19.3. STRICT cho hàm

PostgreSQL có thể khai báo hàm là `STRICT` (tương đương `RETURNS NULL ON NULL INPUT`) để khi **một đối số đầu vào NULL**, hàm tự trả NULL mà không cần thực thi thân hàm:

~~~sql
CREATE OR REPLACE FUNCTION lab_r337_plus_one_strict(
    IN p_number INTEGER
)
RETURNS INTEGER
LANGUAGE sql
IMMUTABLE
STRICT
AS $sql$
    SELECT p_number + 1;
$sql$;
~~~

~~~sql
SELECT
    lab_r337_plus_one_strict(9) AS value_9,
    lab_r337_plus_one_strict(NULL::INTEGER) AS value_null;
~~~

Kết quả **10** và **NULL**.

**Không dùng STRICT khi cần biến NULL thành một đầu ra khác**, ví dụ trả 0 hoặc thông báo có cấu trúc. `STRICT` là một **hợp đồng về cách hàm xử lý NULL**, không phải thuộc tính luôn nên bật để “an toàn hơn”.

### 19.4. Đầu ra tập hàng rỗng khác NULL

Ba lời gọi:

~~~sql
SELECT lab_r337_price_with_default(100.00, NULL);
SELECT * FROM lab_r337_paid_summary(4);
SELECT * FROM lab_r337_paid_orders(4);
~~~

có ý nghĩa kết quả lần lượt:

1. **Một scalar NULL**.
2. **Một hàng** chứa số đơn 0 và tổng 0.
3. **Không hàng nào**.

Đây là những hợp đồng khác nhau mà ứng dụng gọi routine phải xử lý đúng.

## 20. Kiểu tham số và ép kiểu: đừng dựa vào chuyển đổi ngầm

Routine trong PostgreSQL có **chữ ký tham số**; các kiểu được dùng để tìm hàm/thủ tục phù hợp. Một số giá trị có thể ép kiểu ngầm; những trường hợp khác bị lỗi hoặc làm lời gọi mơ hồ.

### 20.1. Kiểu số nguyên và số thập phân

~~~sql
SELECT lab_r337_plus_one(9);
~~~

`9` phù hợp với tham số `INTEGER` trong ví dụ. Với hàm giá:

~~~sql
SELECT lab_r337_final_price(200.00::NUMERIC, 15::NUMERIC);
~~~

Kiểu được viết rõ ràng. Trong ứng dụng, chuẩn bị truy vấn có tham số đúng kiểu, ví dụ `BigDecimal` cho giá trị tiền trong JDBC, thường an toàn hơn ghép chuỗi số.

### 20.2. NULL có thể làm overload mơ hồ

Giả sử có hai overload cùng tên nhưng khác kiểu tham số:

~~~sql
-- Minh hoa, khong can tao de hoc bai:
-- f(IN value INTEGER)
-- f(IN value TEXT)
~~~

Lời gọi `f(NULL)` không phải lúc nào cũng cho biết nên chọn overload nào. Viết ép kiểu:

~~~sql
-- Minh hoa cach chi ro kieu:
-- f(NULL::INTEGER)
-- f(NULL::TEXT)
~~~

giúp bộ phân giải routine biết ý định. Khi ứng dụng dùng parameterized query, cũng nên đặt **kiểu tham số cụ thể** thay vì dựa vào database suy đoán từ một giá trị `NULL`.

### 20.3. Không ghép chuỗi đầu vào thành SQL động tùy tiện

Truyền một tên, một giá hoặc một mã khách vào routine **không có nghĩa** routine phải dùng string concatenation tạo SQL:

~~~sql
-- Y TUONG KHONG AN TOAN:
-- EXECUTE 'SELECT ... WHERE name = ''' || p_name || '''';
~~~

Trong PL/pgSQL, khi dùng SQL tĩnh có tham số/biến thì PostgreSQL xử lý giá trị như dữ liệu. Nếu thực sự cần SQL động cho **tên bảng/cột**, phải phân biệt **identifier** với **giá trị**, sử dụng cơ chế quoting/`format('%I', ...)` và `EXECUTE ... USING` phù hợp, thay vì tự nối nội dung không tin cậy.

## 21. Overloading: cùng tên, khác kiểu đầu vào

PostgreSQL cho phép nhiều function có cùng tên nhưng khác **danh sách kiểu tham số đầu vào**.

Ví dụ:

~~~sql
CREATE OR REPLACE FUNCTION lab_r337_add(
    IN p_a INTEGER,
    IN p_b INTEGER
)
RETURNS INTEGER
LANGUAGE sql
IMMUTABLE
AS $sql$
    SELECT p_a + p_b;
$sql$;

CREATE OR REPLACE FUNCTION lab_r337_add(
    IN p_a NUMERIC,
    IN p_b NUMERIC
)
RETURNS NUMERIC
LANGUAGE sql
IMMUTABLE
AS $sql$
    SELECT p_a + p_b;
$sql$;
~~~

Hai lời gọi:

~~~sql
SELECT lab_r337_add(3, 4) AS int_sum;

SELECT lab_r337_add(
    3.5::NUMERIC,
    4.2::NUMERIC
) AS numeric_sum;
~~~

Kết quả **7** và **7.7**.

### 21.1. Không overload chỉ bằng kiểu trả về

Không thể tạo hai function PostgreSQL **cùng tên, cùng kiểu đầu vào** rồi chỉ khác:

~~~text
RETURNS INTEGER
RETURNS TEXT
~~~

để mong SQL chọn overload dựa vào nơi nhận kết quả. **Kiểu trả về không tự tạo một chữ ký overload độc lập** như một tham số đầu vào.

### 21.2. OUT không làm khác chữ ký gọi function

Ví dụ:

~~~sql
-- Minh hoa:
-- foo(IN p_id INTEGER, OUT p_name TEXT)
-- foo(IN p_id INTEGER, OUT p_amount NUMERIC)
~~~

Hai hàm chỉ khác kiểu của tham số `OUT` nhưng cùng kiểu đầu vào `INTEGER` không được xem là hai overload độc lập có thể chọn bằng cùng lời gọi `foo(1)`. PostgreSQL xác định định danh function chủ yếu theo các kiểu tham số **đầu vào**, bao gồm phần vào của `INOUT`, không dựa vào OUT thuần túy.

### 21.3. DEFAULT có thể khiến lời gọi bị nhập nhằng

Nếu tạo các overload có cùng tên mà một overload có tham số mặc định, một lời gọi bỏ qua tham số có thể phù hợp với nhiều chữ ký. Khi thiết kế API, tránh đặt các overload/default chồng chéo khó phân giải; nếu cần, dùng tên hàm khác rõ nghĩa.

## 22. Hàm truy vấn bảng và đặc tính IMMUTABLE, STABLE, VOLATILE

Trong PostgreSQL, hàm có một khai báo **volatility** giúp bộ tối ưu hiểu mức phụ thuộc vào trạng thái bên ngoài. Đó **không phải mode tham số**, nhưng liên quan trực tiếp tới kết quả mà hàm hứa trả.

| Đánh dấu | Ý nghĩa khái quát | Ví dụ |
| --- | --- | --- |
| `IMMUTABLE` | Với cùng đối số, kết quả được xem là ổn định độc lập trạng thái database trong mọi lần gọi thích hợp | Phép toán thuần túy như cộng số |
| `STABLE` | Không thay đổi kết quả trong phạm vi một statement cho cùng đầu vào theo quy tắc snapshot và không sửa database | Đọc dữ liệu để tính thống kê |
| `VOLATILE` | Có thể thay đổi theo mỗi lần gọi, đọc trạng thái biến đổi hoặc có tác dụng phụ | Dùng giá trị ngẫu nhiên, thao tác thay đổi dữ liệu khi được phép |

Đối chiếu:

~~~sql
-- Tinh gia theo hai gia tri dau vao, khong doc bang:
-- IMMUTABLE phu hop voi logic duoc khai bao.

-- Dem don PAID tu bang lab_r337_orders:
-- STABLE phu hop khi ham chi doc du lieu.

-- Ham co tac dung phu hoac gia tri thay doi theo lan goi:
-- VOLATILE phu hop.
~~~

### 22.1. Khai báo volatility sai có thể làm kết quả không đúng

Không đánh dấu một hàm đọc bảng nghiệp vụ đang thay đổi là `IMMUTABLE` chỉ để mong PostgreSQL tối ưu nhanh hơn. Bộ tối ưu có thể áp dụng những giả định mạnh về hàm immutable; nếu hàm thật sự phụ thuộc dữ liệu đang đổi, kết quả hoặc hành vi có thể không còn phản ánh ý định.

Chọn thuộc tính theo **ngữ nghĩa thật** của routine, không phải để ép tối ưu.

### 22.2. Function đọc bảng khác procedure thay đổi bảng

`lab_r337_paid_summary` và `lab_r337_paid_orders` chỉ đọc dữ liệu nguồn để trả kết quả, vì vậy được khai báo `STABLE`. Thủ tục `lab_r337_add_stock` thực hiện `UPDATE`; procedure không khai báo volatility bằng `RETURNS`/`STABLE` theo cùng giao diện function. Phân biệt đây là **thuộc tính function**, không phải chế độ truyền đầu ra.

## 23. Giá trị trả về và số lượng hàng: hai cam kết khác nhau

Hãy xem bốn loại interface:

~~~sql
-- Mot scalar:
SELECT lab_r337_final_price(200.00, 15);

-- Mot hang gom nhieu cot OUT:
SELECT * FROM lab_r337_paid_summary(1);

-- Nhieu hang:
SELECT * FROM lab_r337_paid_orders(1);

-- Thu tuc co ket qua OUT/INOUT:
CALL lab_r337_get_paid_stats(1, NULL, NULL);
~~~

| Trường hợp | Số hàng dự kiến | Hình dạng |
| --- | ---: | --- |
| Hàm tính giá | 1 | 1 cột NUMERIC |
| Hàm OUT thống kê | 1 | 2 cột: count, total |
| Hàm bảng lấy đơn | 3 với khách 1 | 2 cột: order_id, paid_amount |
| Thủ tục OUT thống kê | 1 hàng kết quả của CALL | 2 cột OUT |

**“Có nhiều OUT” không mặc định đồng nghĩa “trả nhiều hàng”.** Hai OUT thường mô tả **nhiều cột của một bản ghi**. Muốn trả tập hàng, dùng interface set-returning như `RETURNS TABLE`/`SETOF`.

### 23.1. Hàm scalar trả NULL khác hàm tập hàng rỗng

Nếu function trả `INTEGER` và nhánh logic trả `NULL`, người gọi có thể nhận một hàng chứa giá trị NULL. Nếu function `RETURNS SETOF INTEGER` không phát ra phần tử nào, người gọi nhận **0 hàng** khi dùng trong `FROM`. Ứng dụng cần phân biệt “không có dòng dữ liệu” với “có một giá trị NULL”.

### 23.2. Hàm bảng không phải bảng vật lý

`RETURNS TABLE(...)` công bố **hình dạng tập kết quả của function**, không tự tạo `CREATE TABLE` hoặc giữ những hàng đó giữa các lần gọi. Nếu cần cache kết quả trong session hoặc lưu bền vững, đó là bài toán **bảng tạm, bảng trung gian hoặc kết quả vật chất hóa**, không phải mệnh đề `RETURNS TABLE`.

## 24. Kiểm tra lỗi: kiểu trả về, số cột và số hàng

### 24.1. Trả giá trị không đúng kiểu

Ví dụ minh họa lỗi:

~~~sql
-- Khong chay: y tuong sai, RETURNS INTEGER ma tra chuoi khong chuyen duoc.
-- CREATE FUNCTION bad() RETURNS INTEGER AS $$
-- BEGIN
--     RETURN 'not a number';
-- END;
-- $$ LANGUAGE plpgsql;
~~~

Nếu kiểu kết quả không thể chuyển thành kiểu công bố, database sẽ từ chối ở thời điểm thích hợp. Không nên dựa vào ép kiểu ngầm ngoài hợp đồng.

### 24.2. RETURN QUERY khác cấu trúc RETURNS TABLE

Giả sử:

~~~sql
RETURNS TABLE(order_id INTEGER, paid_amount NUMERIC)
~~~

thì một `RETURN QUERY` phải đưa ra **hai cột tương thích theo thứ tự**. Ví dụ chỉ trả một cột `order_id` hoặc đổi vị trí khiến kiểu không tương thích có thể gây lỗi.

Đặc biệt với PL/pgSQL, PostgreSQL có thể yêu cầu kiểu cột trả **khớp chính xác hơn** so với kỳ vọng về ép kiểu ngầm. Khi cần, hãy dùng `CAST`/`::type` trong `SELECT` để khớp đúng kiểu đã công bố.

### 24.3. Scalar subquery nhiều hàng không phù hợp

Một function scalar có thể chạy nhiều câu lệnh bên trong, nhưng **giá trị trả ra** vẫn phải là một giá trị theo `RETURNS`. Không nên:

~~~sql
-- Pseudocode:
-- RETURN (SELECT amount FROM orders WHERE customer_id = 1);
~~~

nếu truy vấn đó có thể trả **nhiều hàng**. Hãy xác định lại nghiệp vụ:

- Muốn **tổng** → `SUM` hoặc aggregate.
- Muốn **một đơn mới nhất** → chọn rõ `ORDER BY ... LIMIT 1` với khóa phá hòa.
- Muốn **danh sách đơn** → `RETURNS TABLE` hoặc `SETOF`.

### 24.4. OUT chưa gán và kiểm tra trạng thái

Với thủ tục ghi dữ liệu, nếu `UPDATE ... RETURNING INTO` không tìm thấy hàng, tham số OUT/INOUT có thể không mang giá trị hợp lệ. Thủ tục `lab_r337_add_stock` chủ động dùng `IF NOT FOUND THEN RAISE EXCEPTION` để tránh trả một số tồn không có ý nghĩa. Đó là một phần quan trọng của hợp đồng đầu ra: **không hứa trả thành công khi thao tác ghi thất bại**.

## 25. Tham số đầu ra và transaction trong ứng dụng

Trong một ứng dụng, có hai đường để nhận kết quả từ database:

1. **Function trả giá trị hoặc tập hàng:** ứng dụng đọc kết quả của câu `SELECT`.
2. **Procedure có OUT/INOUT:** ứng dụng gọi routine theo API của driver hoặc `CALL`, đọc các cột/giá trị đầu ra phù hợp.

### 25.1. PostgreSQL và JDBC

Với PostgreSQL/JDBC, các ứng dụng có thể dùng `PreparedStatement` cho câu `SELECT function(...)`, hoặc cơ chế gọi thủ tục/`CallableStatement` theo khả năng JDBC driver. Nhưng không nên giả định cú pháp escape call kiểu `{? = call ...}` được mọi driver xử lý giống nhau đối với function và procedure.

Ví dụ nguyên tắc với một hàm scalar, **không nối trực tiếp đầu vào người dùng vào chuỗi SQL**:

~~~java
String sql = "SELECT lab_r337_final_price(?, ?) AS final_price";

try (PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setBigDecimal(1, new BigDecimal("200.00"));
    ps.setBigDecimal(2, new BigDecimal("15"));

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            BigDecimal result = rs.getBigDecimal("final_price");
            System.out.println(result);
        }
    }
}
~~~

Đoạn Java là **minh họa** khi `conn` đã là kết nối JDBC hợp lệ và các lớp cần thiết đã được import; không phải một chương trình độc lập. Ưu điểm là đối số được truyền qua tham số có kiểu, không xây câu SQL bằng cách ghép chuỗi đầu vào.

### 25.2. Chọn kiểu đầu ra ổn định cho API

Hàm trả `RECORD` linh hoạt có thể gây khó cho driver/ORM vì caller phải biết cấu trúc. Với API ổn định, `RETURNS TABLE(order_id INTEGER, paid_amount NUMERIC)` hay một composite type có tên có thể dễ tích hợp hơn.

Các thay đổi như đổi kiểu `NUMERIC` thành `TEXT`, đổi tên cột OUT hoặc thay số cột của `RETURNS TABLE` cần được xem là **thay đổi hợp đồng**, không đơn thuần là sửa nội bộ không ảnh hưởng người dùng.

## 26. Phiên bản routine, CREATE OR REPLACE và phụ thuộc

Trong PostgreSQL, `CREATE OR REPLACE FUNCTION` hữu ích khi cần thay **thân hàm** hoặc một số thuộc tính được hỗ trợ cho **cùng định danh hàm**. Nhưng không nên giả định có thể đổi tự do **kiểu trả về** của function hiện có bằng `CREATE OR REPLACE`.

Ví dụ muốn đổi:

~~~text
ham f(INTEGER) RETURNS INTEGER
           |
           v
ham f(INTEGER) RETURNS TABLE(...)
~~~

Đó là thay đổi lớn về giao diện; PostgreSQL thường yêu cầu **xóa/đổi routine phù hợp rồi tạo lại**, và còn có thể có view, function, trigger hoặc quyền đang phụ thuộc.

### 26.1. DROP FUNCTION dùng kiểu đối số đầu vào

Ví dụ **chỉ minh họa cú pháp dọn routine**:

~~~sql
-- Chi chay khi thuc su muon xoa ham thuc hanh.
DROP FUNCTION lab_r337_final_price(NUMERIC, NUMERIC);
~~~

Với hàm có OUT, `DROP FUNCTION` thường nhận diện bằng **kiểu tham số đầu vào**, không bởi những kiểu OUT thuần túy:

~~~sql
-- Chi chay neu muon xoa ham thong ke.
DROP FUNCTION lab_r337_paid_summary(INTEGER);
~~~

Hãy thận trọng với phụ thuộc và quyền; **không dùng `CASCADE` một cách tùy tiện** để “dọn nhanh” khi chưa hiểu những đối tượng bị xóa theo.

### 26.2. Tên tham số có thể là hợp đồng của named notation

Nếu ứng dụng gọi theo `p_customer_id => 1`, đổi tên tham số có thể phá lời gọi. Nếu API được chia sẻ cho nhiều nhóm, cần có cơ chế versioning hoặc migration thay vì chỉnh sửa interface không kiểm soát.

### 26.3. Function/procedure cùng tên có thể gây nhầm

PostgreSQL phân giải routine dựa trên loại, chữ ký và ngữ cảnh. Đặt tên rõ nghĩa như `get_paid_orders` cho function và `add_stock` cho procedure giúp code dễ đọc hơn. Đừng dựa vào `RETURNS` hay mode OUT để cố overload những routine chỉ khác đầu ra mà không có chữ ký đầu vào khác nhau.

## 27. Quyền truy cập và tính an toàn

Routine có thể truy cập dữ liệu nhạy cảm hoặc thực hiện cập nhật. Người được cấp quyền **EXECUTE** trên routine không nhất thiết nên được quyền tùy ý đọc/ghi mọi bảng.

Trong PostgreSQL, cần hiểu:

- **`SECURITY INVOKER`** (thường là mặc định): quyền thực thi các thao tác bên trong dựa trên ngữ cảnh người gọi theo quy tắc database.
- **`SECURITY DEFINER`**: routine có thể chạy với quyền của người sở hữu routine, thích hợp một số API được kiểm soát nhưng có rủi ro nâng quyền nếu viết sai.
- `search_path`, tên schema và SQL động cần được xử lý cẩn thận ở những routine quyền cao; nên schema-qualify những đối tượng cần bảo vệ.
- Tham số nhập liệu vẫn cần kiểm tra hợp lệ, không đưa trực tiếp vào dynamic SQL.

Ví dụ routine `lab_r337_add_stock` cần xác minh số lượng tăng là số dương và SKU tồn tại. Trong ứng dụng thật, còn có thể cần kiểm tra người dùng có được phép sửa tồn kho, ghi audit, chống chạy lặp và bảo đảm transaction cùng các bảng liên quan.

**Đầu vào hợp lệ, đầu ra rõ nghĩa và quyền thực thi đúng là ba phần của cùng một hợp đồng routine.**

## 28. Khác biệt giữa các SQL dialect

Các khái niệm `IN`, `OUT`, `INOUT` phổ biến trong thế giới stored routines, nhưng **không phải mọi hệ quản trị hỗ trợ cùng kiểu routine hoặc cùng cú pháp trả kết quả**.

### 28.1. PostgreSQL

PostgreSQL có:

~~~sql
-- Function scalar:
CREATE FUNCTION f(IN x INTEGER)
RETURNS INTEGER LANGUAGE sql
AS $sql$ SELECT x + 1; $sql$;

-- Function ra nhieu cot:
CREATE FUNCTION g(IN x INTEGER, OUT y INTEGER, OUT z TEXT)
LANGUAGE plpgsql
AS $fn$
BEGIN
    y := x + 1;
    z := 'OK';
END;
$fn$;

-- Function ra nhieu hang:
CREATE FUNCTION h(IN x INTEGER)
RETURNS TABLE(value INTEGER)
LANGUAGE sql
AS $sql$ SELECT x; $sql$;
~~~

Các tên `f`, `g`, `h` là ví dụ cú pháp bổ sung; chỉ tạo khi bạn đang dùng database thực hành và không có routine trùng tên. Trong PostgreSQL:

- Function được gọi qua `SELECT`.
- Procedure được gọi qua `CALL`.
- `IN`, `OUT`, `INOUT` có quy tắc rõ; `VARIADIC` là khả năng bổ sung cho một số function.
- Function có thể trả scalar, composite, `RECORD`, `TABLE`, `SETOF` hoặc `VOID`.
- Procedure không có `RETURNS`; pure `OUT` trên procedure yêu cầu phiên bản hỗ trợ (PostgreSQL 14+).

### 28.2. MySQL: FUNCTION và PROCEDURE có giao diện khác

MySQL có stored function với `RETURNS type` và stored procedure với `IN`, `OUT`, `INOUT`. Khác PostgreSQL, tham số của **stored FUNCTION trong MySQL là đầu vào**; các chế độ `OUT`/`INOUT` được dùng với **procedure**, không định nghĩa function trả bảng theo cú pháp `RETURNS TABLE` của PostgreSQL.

Ví dụ procedure MySQL:

~~~sql
-- MySQL command-line client: DELIMITER la lenh client,
-- khong phai mot thanh phan cua SQL server.
DELIMITER //

CREATE PROCEDURE demo_mysql_add(
    IN p_increment INT,
    INOUT p_total INT
)
BEGIN
    SET p_total = p_total + p_increment;
END//

DELIMITER ;

SET @total = 10;
CALL demo_mysql_add(5, @total);
SELECT @total AS result;
~~~

Kết quả **15**. `@total` là **biến session của MySQL** được dùng để nhận kết quả INOUT. Việc dùng `DELIMITER` phụ thuộc client: nếu chạy qua ứng dụng JDBC hoặc một GUI khác, cách gửi câu lệnh tạo procedure có thể không cần hoặc không chấp nhận lệnh `DELIMITER`.

Một stored function MySQL:

~~~sql
-- Minh hoa MySQL:
DELIMITER //
CREATE FUNCTION demo_mysql_double(p_number INT)
RETURNS INT
DETERMINISTIC
BEGIN
    RETURN p_number * 2;
END//
DELIMITER ;

SELECT demo_mysql_double(7);
~~~

Không dùng cú pháp PostgreSQL `RETURNS SETOF` hoặc `RETURNS TABLE` của bài cho một stored function MySQL.

### 28.3. SQL Server: OUTPUT parameter và RETURN code

SQL Server sử dụng T-SQL với tham số thủ tục kiểu:

~~~sql
@ParameterName INT OUTPUT
~~~

Ví dụ:

~~~sql
-- T-SQL minh hoa, bang dbo.Orders co cot customer_id,
-- amount va order_status.
CREATE OR ALTER PROCEDURE dbo.demo_get_paid_total
    @CustomerId INT,
    @Total DECIMAL(12, 2) OUTPUT
AS
BEGIN
    SELECT @Total = COALESCE(SUM(amount), 0)
    FROM dbo.Orders
    WHERE customer_id = @CustomerId
      AND order_status = 'PAID';
END;
~~~

Gọi:

~~~sql
DECLARE @Result DECIMAL(12, 2);

EXEC dbo.demo_get_paid_total
    @CustomerId = 1,
    @Total = @Result OUTPUT;

SELECT @Result AS paid_total;
~~~

Chú ý **`RETURN` trong T-SQL procedure** thường dùng **mã trạng thái integer**, không phải cơ chế chung để trả một bảng hay số tiền bất kỳ theo kiểu `RETURNS NUMERIC` của PostgreSQL function. SQL Server còn có scalar-valued functions và table-valued functions với cú pháp riêng.

Đừng sao chép `INOUT`, `OUT p INTEGER` PostgreSQL vào T-SQL rồi chờ SQL Server tự hiểu.

### 28.4. Oracle: IN, OUT, IN OUT trong PL/SQL

Oracle PL/SQL hỗ trợ `IN`, `OUT`, `IN OUT` cho tham số routine, và hàm dùng `RETURN type`.

Ví dụ procedure:

~~~sql
-- Oracle PL/SQL minh hoa:
CREATE OR REPLACE PROCEDURE demo_oracle_tax(
    p_amount IN NUMBER,
    p_tax_rate IN NUMBER,
    p_total OUT NUMBER
)
AS
BEGIN
    p_total := p_amount * (1 + p_tax_rate);
END;
/
~~~

Gọi trong khối PL/SQL:

~~~sql
DECLARE
    v_total NUMBER;
BEGIN
    demo_oracle_tax(100, 0.10, v_total);
    DBMS_OUTPUT.PUT_LINE(v_total);
END;
/
~~~

Kết quả là **110**. Ký hiệu `/` trên một dòng riêng là lệnh của một số client Oracle để kết thúc/chạy khối PL/SQL, không phải một phần của thân procedure trên server.

Oracle còn có `REF CURSOR` để đưa kết quả dạng cursor ra cho ứng dụng; kiểu trả tập hàng và quy tắc gọi từ SQL khác PostgreSQL `RETURNS TABLE`. `IN OUT NOCOPY` là một gợi ý tối ưu truyền tham số của PL/SQL, không nên hiểu như bảo đảm tuyệt đối về tránh sao chép hoặc rollback biến ngoài.

### 28.5. SQLite: không có stored procedure SQL native như PostgreSQL

SQLite không có cú pháp server-side `CREATE PROCEDURE` hoặc `CREATE FUNCTION ... LANGUAGE plpgsql` như PostgreSQL. Một ứng dụng có thể:

- Gửi truy vấn SQL có **tham số bind**.
- Đăng ký **user-defined function** từ ngôn ngữ host như Python/C/Java theo API của thư viện SQLite.
- Dùng CTE, view, trigger và transaction để tổ chức các thao tác thích hợp.

Ví dụ SQL thuần:

~~~sql
-- SQLite: cong thuc truc tiep voi bind parameters cua ung dung.
SELECT ROUND(?1 * (1 - ?2 / 100.0), 2) AS final_price;
~~~

`?1` và `?2` là vị trí tham số bind của câu SQL được ứng dụng cung cấp, **không phải tham số IN của một stored procedure được tạo trong SQLite**.

### 28.6. Bảng so sánh

| Tính năng | PostgreSQL | MySQL | SQL Server | Oracle | SQLite |
| --- | --- | --- | --- | --- | --- |
| Stored function | Có, nhiều kiểu kết quả | Có, thường scalar | Có, scalar/table-valued | Có qua PL/SQL | Qua API ứng dụng, không có CREATE FUNCTION native tương đương |
| Stored procedure | `CREATE PROCEDURE` / `CALL` | `CREATE PROCEDURE` / `CALL` | `CREATE PROCEDURE` / `EXEC` | `CREATE PROCEDURE` / gọi PL/SQL | Không có CREATE PROCEDURE SQL native |
| IN | Có | Có | Tham số input qua `@name` | `IN` | Bind parameter câu SQL |
| OUT | Có | Procedure `OUT` | `OUTPUT` | `OUT` | Không phải giao diện stored routine native |
| INOUT | Có | Procedure `INOUT` | Thường tham số `OUTPUT` có thể nhận giá trị ban đầu và trả giá trị cuối | `IN OUT` | Không có |
| Function trả tập hàng | `RETURNS TABLE`, `SETOF` | Không có cùng cơ chế stored function | Table-valued function | Table/pipelined function/cursor theo ngữ cảnh | Query/view/host UDF tùy thiết kế |
| Điều khiển transaction trong procedure | Có giới hạn theo ngữ cảnh CALL | Theo quy tắc MySQL | Theo quy tắc T-SQL | Theo quy tắc PL/SQL | Transaction do ứng dụng/SQL điều khiển |

Khi chuyển hệ, cần đối chiếu **khả năng routine, cách truyền output cho driver, kiểu dữ liệu và transaction** chứ không chỉ đổi từ khóa.

## 29. Những lỗi thường gặp

| Cách viết hoặc suy luận | Vấn đề | Cách đúng |
| --- | --- | --- |
| Gọi function PostgreSQL bằng `CALL` | FUNCTION và PROCEDURE là các loại routine khác nhau | Function dùng `SELECT`; procedure dùng `CALL` |
| Gọi procedure bằng `SELECT procedure(...)` | Procedure không phải biểu thức SQL function | Dùng `CALL` |
| Nghĩ `OUT` phải được truyền như một đầu vào của function | OUT là đầu ra của function | Chỉ truyền các IN/INOUT; đọc cột OUT từ kết quả |
| Nghĩ procedure OUT luôn gọi với cùng số đối số như function OUT | PostgreSQL SQL `CALL` cần placeholder cho OUT theo quy tắc phiên bản | Với thủ tục mẫu: `CALL ... (1, NULL, NULL)` |
| Viết `RETURNS NUMERIC` trong `CREATE PROCEDURE` | Procedure PostgreSQL không có RETURNS như function | Khai báo OUT/INOUT nếu cần kết quả |
| Cho rằng hai OUT đồng nghĩa nhiều hàng | Hai OUT thường tạo nhiều cột của một hàng | Dùng `RETURNS TABLE`/`SETOF` nếu cần tập hàng |
| Dùng `RETURN biểu_thức` trong function có OUT | Giá trị trả thuộc các biến OUT | Gán OUT rồi `RETURN;` hoặc kết thúc thân |
| Dùng `RETURN NEXT` trong function scalar | `RETURN NEXT` phục vụ tập kết quả | Khai báo `RETURNS SETOF`/`TABLE` |
| Dùng `RETURN QUERY` có số cột khác RETURNS TABLE | Kết quả không khớp giao diện | Liệt kê và ép kiểu cột đúng thứ tự |
| Gọi function RECORD trong FROM mà không mô tả cột | PostgreSQL không biết cấu trúc RECORD tổng quát | Cung cấp `AS alias(col type, ...)` hoặc dùng RETURNS TABLE |
| Truyền NULL rồi mong DEFAULT hoạt động | NULL là đối số được truyền tường minh | Bỏ đối số khi có DEFAULT, hoặc tự xử lý NULL |
| Đảo hai tham số cùng kiểu | SQL có thể chấp nhận nhưng nghiệp vụ sai | Dùng tên tham số/kiểm tra thứ tự |
| Overload chỉ bằng kiểu RETURNS | Không phân biệt chữ ký PostgreSQL | Khác kiểu đầu vào hoặc chọn tên mới |
| Cho rằng OUT khác loại làm được overload | OUT thuần không tính như đầu vào để phân giải | Thiết kế signature khác hoặc tên routine khác |
| Đổi kiểu return bằng CREATE OR REPLACE mà không xét phụ thuộc | Có thể bị PostgreSQL từ chối | Migration/drop-recreate có kế hoạch, xem dependency |
| Function tính giá đọc bảng nhưng gắn IMMUTABLE | Khai báo không phản ánh phụ thuộc dữ liệu | Dùng STABLE/VOLATILE phù hợp |
| Procedure cập nhật tồn không báo lỗi nếu SKU vắng | OUT có thể không có giá trị hợp lệ | Kiểm tra FOUND/số hàng và RAISE EXCEPTION |
| Nghĩ CALL tự commit khi đang ở BEGIN | Transaction ngoài chưa tự kết thúc | Quản lý COMMIT/ROLLBACK theo quy tắc |
| Dùng kiểu FLOAT cho mọi số tiền mà bỏ qua sai số | Có thể gặp sai số nhị phân | Ưu tiên NUMERIC và quy tắc làm tròn |
| Đưa đầu vào người dùng vào dynamic SQL bằng nối chuỗi | Nguy cơ injection/sai cú pháp | Parameterized query, EXECUTE USING khi phù hợp |
| Mang `RETURNS TABLE` PostgreSQL sang MySQL function | Không cùng feature | Xem giới hạn stored function và chọn procedure/result-set phù hợp |
| Mong SQLite chạy `CREATE PROCEDURE` | Không có stored procedure native | Xử lý từ host application/transaction/trigger |

## 30. Bài tập thực hành có đáp án

Các bài dùng hai bảng và các routine đã tạo ở mục trước. Những bài gọi procedure có ghi dữ liệu dùng **`BEGIN ... ROLLBACK`** để giữ nguyên dữ liệu mẫu. Nếu một routine chưa tồn tại do bạn bỏ qua phần định nghĩa, hãy tạo nó trước khi chạy lời gọi tương ứng.

### Bài 1 — Nhận diện IN, OUT và kiểu trả về

Cho định nghĩa:

~~~sql
CREATE FUNCTION sample(
    IN p_customer_id INTEGER,
    OUT p_count BIGINT,
    OUT p_total NUMERIC
) ...
~~~

**Yêu cầu:** có bao nhiêu tham số đầu vào và bao nhiêu đầu ra? Truyền mấy đối số khi gọi PostgreSQL function?

**Đáp án:** có **một IN** (`p_customer_id`) và **hai OUT** (`p_count`, `p_total`). Khi gọi function qua `SELECT`, truyền **một đối số**. Hai OUT mô tả **các cột kết quả** của hàm, không phải hai đối số đầu vào.

### Bài 2 — Hàm tính giá có hai IN

**Yêu cầu:** dùng hàm đã tạo để tính giá sau giảm 20% của 150.

**Đáp án:**

~~~sql
SELECT lab_r337_final_price(150.00, 20) AS final_price;
~~~

Kết quả **120.00**.

### Bài 3 — DEFAULT khác NULL

**Yêu cầu:** dự đoán hai kết quả:

~~~sql
SELECT lab_r337_price_with_default(120.00) AS a;
SELECT lab_r337_price_with_default(120.00, NULL) AS b;
~~~

**Đáp án:** `a = 120.00` vì bỏ đối số thứ hai nên nhận mặc định 0%. `b = NULL` vì đối số thứ hai **được truyền NULL tường minh**, và hàm mẫu trả NULL nếu một đầu vào NULL.

### Bài 4 — Gọi named argument đảo thứ tự

**Yêu cầu:** tính giá 250, giảm 10%, nhưng viết tên phần trăm trước tên giá.

**Đáp án:**

~~~sql
SELECT lab_r337_price_with_default(
    p_discount_pct => 10,
    p_price => 250.00
) AS final_price;
~~~

Kết quả **225.00**. PostgreSQL ghép theo **tên tham số**, không dựa vào thứ tự trong câu gọi dạng named.

### Bài 5 — Hàm OUT cho khách 1

**Yêu cầu:** lấy số đơn PAID và tổng tiền của khách 1 bằng hàm OUT.

**Đáp án:**

~~~sql
SELECT *
FROM lab_r337_paid_summary(1);
~~~

Kết quả **p_order_count = 3** và **p_total = 400.00**.

### Bài 6 — Khách không có đơn: một hàng hay không hàng?

**Yêu cầu:** so kết quả:

~~~sql
SELECT * FROM lab_r337_paid_summary(4);
SELECT * FROM lab_r337_paid_orders(4);
~~~

**Đáp án:** hàm thống kê trả **một hàng (0, 0)** vì dùng aggregate. Hàm trả bảng `lab_r337_paid_orders` trả **0 hàng** vì không có đơn PAID cho khách 4. Hai kiểu đầu ra không đồng nghĩa.

### Bài 7 — Hàm INOUT nhân đôi

**Yêu cầu:** dùng một function INOUT để nhân đôi số 9.

**Đáp án:**

~~~sql
SELECT lab_r337_double(9) AS result;
~~~

Kết quả **18**. `p_number` vừa nhận 9 vừa trả 18; literal bên ngoài không bị sửa.

### Bài 8 — Hàm RETURNS TABLE có ngưỡng

**Yêu cầu:** liệt kê các đơn PAID của khách 1 có `amount >= 100`.

**Đáp án:**

~~~sql
SELECT order_id, paid_amount
FROM lab_r337_paid_orders(1, 100)
ORDER BY order_id;
~~~

Kết quả hai hàng **1001 — 120.00**, **1007 — 200.00**. Hàm trả tập hàng với hai cột.

### Bài 9 — SETOF INTEGER

**Yêu cầu:** lấy các ID đơn PAID của khách 2.

**Đáp án:**

~~~sql
SELECT x.order_id
FROM lab_r337_paid_order_ids(2) AS x(order_id)
ORDER BY x.order_id;
~~~

Kết quả **1004** và **1008**. `RETURNS SETOF INTEGER` tạo các hàng kết quả, không trả một mảng integer duy nhất.

### Bài 10 — RETURN NEXT

**Yêu cầu:** dùng `lab_r337_sequence` tạo các số từ 1 đến 5.

**Đáp án:**

~~~sql
SELECT n.value
FROM lab_r337_sequence(5) AS n(value);
~~~

Kết quả năm hàng **1, 2, 3, 4, 5**. `RETURN NEXT` thêm phần tử vào tập kết quả; `RETURN;` kết thúc sau vòng lặp.

### Bài 11 — PROCEDURE INOUT cập nhật tồn

**Yêu cầu:** thêm 4 sản phẩm PEN, nhận tồn mới, rồi rollback.

**Đáp án:**

~~~sql
BEGIN;

CALL lab_r337_add_stock('PEN', 4, NULL);

SELECT stock_qty
FROM lab_r337_inventory
WHERE sku = 'PEN';

ROLLBACK;
~~~

`CALL` trả `p_new_stock = 16` và `SELECT` trong transaction thấy tồn 16. Sau rollback, tồn về **12**.

### Bài 12 — Thủ tục OUT thống kê

**Yêu cầu:** dùng `CALL` để lấy tổng PAID của khách 3.

**Đáp án PostgreSQL 14+:**

~~~sql
CALL lab_r337_get_paid_stats(3, NULL, NULL);
~~~

Kết quả **p_paid_count = 1**, **p_paid_total = 90.00**. Hai `NULL` là placeholder cho đầu ra OUT trong cú pháp SQL CALL của PostgreSQL, không phải dữ liệu đầu vào để tính toán.

### Bài 13 — Phân biệt SELECT gọi FUNCTION và CALL gọi PROCEDURE

**Yêu cầu:** chọn câu gọi đúng:

~~~sql
-- A:
CALL lab_r337_paid_summary(1);

-- B:
SELECT * FROM lab_r337_paid_summary(1);

-- C:
SELECT * FROM lab_r337_add_stock('PEN', 2, NULL);

-- D:
CALL lab_r337_add_stock('PEN', 2, NULL);
~~~

**Đáp án:** **B** gọi đúng function; **D** gọi đúng procedure. A dùng CALL cho function; C dùng SELECT FROM cho procedure nên không đúng PostgreSQL. Khi thực hành D, hãy đặt trong `BEGIN ... ROLLBACK` vì thủ tục thực sự thay đổi tồn kho.

### Bài 14 — Khi nào dùng RECORD?

**Yêu cầu:** gọi hàm `lab_r337_one_order_record` cho đơn 1004 và chỉ rõ hình dạng cột.

**Đáp án:**

~~~sql
SELECT r.order_id, r.amount
FROM lab_r337_one_order_record(1004)
    AS r(order_id INTEGER, amount NUMERIC);
~~~

Kết quả **1004, 250.00**. Do routine công bố `RETURNS RECORD` tổng quát, caller cung cấp danh sách cột tương ứng. Nếu interface cố định và được nhiều ứng dụng dùng, nên cân nhắc `RETURNS TABLE` có schema rõ ràng.

### Bài 15 — Sửa hợp đồng trả về không tương thích

Một người viết (đoạn minh họa, **không chạy**):

~~~sql
CREATE FUNCTION bad_paid_ids(p_customer_id INTEGER)
RETURNS INTEGER
LANGUAGE plpgsql
AS $fn$
BEGIN
    RETURN QUERY
    SELECT order_id
    FROM lab_r337_orders
    WHERE customer_id = p_customer_id;
END;
$fn$;
~~~

**Câu hỏi:** lỗi thiết kế là gì, và khai báo nên đổi ra sao?

**Đáp án:** `RETURN QUERY` dành cho hàm trả **tập kết quả**, nhưng hàm lại công bố một `INTEGER` scalar. Nếu muốn danh sách nhiều ID, sửa khai báo thành `RETURNS SETOF INTEGER` rồi giữ `RETURN QUERY`. Nếu chỉ muốn một ID, phải định nghĩa rõ quy tắc chọn **duy nhất một hàng** và dùng `RETURN expression`. Không giải quyết bằng cách lấy ngẫu nhiên một hàng.

### Bài 16 — So sánh DATE/TEXT/NUMERIC của đầu ra

**Yêu cầu:** một function trả tổng tiền để ứng dụng tiếp tục tính thuế. Nên công bố `RETURNS TEXT` hay `RETURNS NUMERIC`?

**Đáp án:** ưu tiên **`RETURNS NUMERIC`** khi kết quả thực sự là một số dùng để tính toán. `TEXT` phù hợp nếu nhiệm vụ là **định dạng để hiển thị**, ví dụ viết thêm ký hiệu tiền tệ. Tách số liệu gốc khỏi định dạng trình bày giúp tránh phải parse chuỗi tiền sang số ở các bước sau.

### Bài 17 — Overload theo kiểu đầu vào

**Yêu cầu:** giải thích tại sao có thể có `lab_r337_add(INTEGER, INTEGER)` và `lab_r337_add(NUMERIC, NUMERIC)`, nhưng không thể chỉ thay kiểu `RETURNS` để tạo overload mới cho cùng hai tham số INTEGER.

**Đáp án:** PostgreSQL phân giải chữ ký function bằng **tên và các kiểu đầu vào** theo quy tắc hệ quản trị. Hai danh sách kiểu `INTEGER, INTEGER` và `NUMERIC, NUMERIC` khác nhau nên có thể cùng tồn tại. `RETURNS` hoặc `OUT` thuần túy không phân biệt cùng lời gọi với cùng kiểu đầu vào.

### Bài 18 — Bảo vệ trường hợp SKU không tồn tại

**Tình huống:** ứng dụng gọi:

~~~sql
BEGIN;
CALL lab_r337_add_stock('UNKNOWN', 3, NULL);
~~~

**Câu hỏi:** routine nên trả tồn mới bằng 0 hay báo lỗi? Điều gì cần làm sau lỗi PostgreSQL?

**Đáp án:** theo hợp đồng của thủ tục mẫu, `UPDATE` không tìm thấy hàng thì `IF NOT FOUND` phát **EXCEPTION**, không trả một tồn mới giả định. Trong PostgreSQL, transaction gặp lỗi có thể chuyển sang trạng thái aborted; cần **`ROLLBACK`** trước khi tiếp tục với thao tác khác. Không coi SKU không tồn tại là thành công chỉ vì đầu ra có thể là NULL/0.

## 31. Ghi nhớ

| Câu hỏi thực tế | Cách trả lời |
| --- | --- |
| “Hàm cần nhận dữ liệu gì?” | Khai báo tham số **`IN`** và kiểu cụ thể |
| “Một tham số vừa vào vừa ra?” | **`INOUT`** |
| “Muốn đặt tên nhiều trường đầu ra?” | Function có **`OUT`**, hoặc procedure OUT/INOUT |
| “Hàm trả một số?” | `RETURNS NUMERIC`/`INTEGER` và `RETURN expression;` |
| “Hàm trả TRUE/FALSE?” | `RETURNS BOOLEAN` |
| “Hàm không có kết quả nghiệp vụ?” | `RETURNS VOID`; nó vẫn là FUNCTION |
| “Cần danh sách ID?” | `RETURNS SETOF INTEGER` |
| “Cần bảng nhiều hàng, nhiều cột?” | `RETURNS TABLE(column type, ...)` và `RETURN QUERY` |
| “Muốn một bản ghi linh hoạt?” | `RETURNS RECORD`, cần mô tả cấu trúc khi dùng trong nhiều ngữ cảnh |
| “Tham số có thể bỏ qua?” | `DEFAULT`, phân biệt với truyền `NULL` |
| “Sợ đảo thứ tự nhiều tham số giống kiểu?” | Gọi theo tên `p_name => value` khi dialect hỗ trợ |
| “Gọi function PostgreSQL?” | `SELECT function_name(...)` hoặc trong biểu thức phù hợp |
| “Gọi procedure PostgreSQL?” | `CALL procedure_name(...)` |
| “Procedure có kiểu RETURNS không?” | **Không** theo cú pháp PostgreSQL; dùng OUT/INOUT khi cần |
| “OUT của function có tính vào đối số truyền cho SELECT không?” | **Không**; chỉ các tham số đầu vào cần đối số |
| “OUT của procedure gọi bằng SQL?” | PostgreSQL phiên bản hỗ trợ: cung cấp placeholder phù hợp; kết quả từ `CALL` |
| “Không có đơn hàng thì trả NULL, 0 hay rỗng?” | Phụ thuộc **hợp đồng scalar, aggregate và set-returning** |
| “Thay kiểu trả về có phải sửa đơn giản?” | Có thể là **thay đổi API và cần migration**, không chỉ sửa thân hàm |
| “Có dùng nguyên cú pháp cho MySQL/SQL Server/Oracle/SQLite?” | **Không**; đối chiếu mode và cơ chế gọi theo dialect |

Một mẫu tổng kết về hàm trả giá trị:

~~~sql
CREATE OR REPLACE FUNCTION lab_r337_add_tax(
    IN p_amount NUMERIC,
    IN p_rate NUMERIC DEFAULT 0.08
)
RETURNS NUMERIC
LANGUAGE sql
IMMUTABLE
AS $sql$
    SELECT ROUND(p_amount * (1 + p_rate), 2);
$sql$;

SELECT lab_r337_add_tax(100.00) AS amount_with_default_tax;
~~~

Kết quả **108.00**. Trong một hệ thống thật, mức thuế và quy tắc làm tròn là dữ liệu nghiệp vụ cần được quản lý theo thời gian; `0.08` ở đây chỉ là **giá trị mặc định để minh họa tham số**.

**Điểm cốt lõi của bài:** tham số `IN` cho routine **biết dữ liệu cần xử lý**, `OUT` cho người gọi **biết kết quả được trả qua các trường nào**, `INOUT` kết hợp cả hai chiều; còn `RETURNS` của function quyết định **hình dạng và kiểu dữ liệu của giá trị/tập hàng trả về**. Phân biệt rõ các khái niệm này sẽ giúp bạn thiết kế function và procedure có giao diện dễ gọi, ít nhầm, tương thích kiểu dữ liệu và có thể bảo trì khi hệ thống phát triển.
