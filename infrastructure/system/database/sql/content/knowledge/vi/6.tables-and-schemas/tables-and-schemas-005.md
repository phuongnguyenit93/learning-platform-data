# Cột sinh từ biểu thức và giới hạn theo phương ngữ SQL

Trong thiết kế bảng, có những giá trị không cần nhập độc lập vì có thể **tính ra từ các cột khác của cùng một hàng**. Ví dụ, nếu một dòng đơn hàng đã có số lượng và đơn giá, thì thành tiền có thể tính bằng **số lượng × đơn giá**. SQL cung cấp một cơ chế đưa quy tắc tính toán ấy vào **lược đồ bảng**: *cột sinh từ biểu thức* (*generated column*, đôi khi gọi là *computed column*).

Cơ chế này giúp nhiều câu truy vấn và ứng dụng dùng cùng một định nghĩa tính toán. Tuy nhiên, **cú pháp, cách lưu trữ, kiểu biểu thức được phép, khả năng tạo chỉ mục và cách thay đổi lược đồ không hoàn toàn giống nhau giữa các hệ quản trị cơ sở dữ liệu**. Vì vậy, khi thiết kế bảng cần hiểu đồng thời ý nghĩa của cột sinh và **giới hạn theo phương ngữ** (*SQL dialect*).

Bài học thuộc chương **Bảng và lược đồ** của module **Database SQL**. Các ví dụ chính được viết cho **PostgreSQL 16–17**, sử dụng cột sinh kiểu **STORED**. Phần so sánh sau trình bày cách làm tương ứng trên MySQL 8.0, SQLite 3.31+ và SQL Server; không nên chạy nguyên một ví dụ của hệ này trên hệ khác.

## 1. Sau bài này cần nắm được gì?

Bạn sẽ học cách:

1. Phân biệt cột thông thường, cột có **DEFAULT**, cột **IDENTITY** và cột **generated/computed**.
2. Tạo cột có giá trị được suy ra từ các cột nguồn trong cùng hàng.
3. Hiểu hai kiểu lưu trữ phổ biến **STORED/PERSISTED** và **VIRTUAL**.
4. Dự đoán dữ liệu thay đổi thế nào khi **INSERT** hoặc **UPDATE** cột nguồn.
5. Xác định những biểu thức không phù hợp với cột sinh: hàm không xác định, truy vấn bảng khác, tổng hợp nhiều hàng, v.v.
6. Đọc sự khác biệt về cú pháp và khả năng hỗ trợ giữa PostgreSQL, MySQL, SQLite và SQL Server.
7. Chọn giữa cột sinh, biểu thức trong **SELECT**, **VIEW**, **INDEX theo biểu thức** hoặc các cơ chế xử lý nghiệp vụ khác.

## 2. Cột sinh từ biểu thức là gì?

Giả sử một bảng chứa dữ liệu sau:

| line_id | quantity | unit_price | line_total |
| ---: | ---: | ---: | ---: |
| 1 | 2 | 125.000 | 250.000 |
| 2 | 3 | 40.000 | 120.000 |

Nếu **line_total** được lưu như một cột nhập tay, ứng dụng có thể vô tình ghi **quantity = 2**, **unit_price = 125000** nhưng **line_total = 240000**. Khi đó, dữ liệu mất tính nhất quán.

Với cột sinh, thay vì cho phép ứng dụng nhập line_total tùy ý, ta **khai báo công thức ngay trong CREATE TABLE**:

~~~sql
line_total NUMERIC(14, 2)
    GENERATED ALWAYS AS (quantity * unit_price) STORED
~~~

Hệ quản trị chịu trách nhiệm tính line_total từ quantity và unit_price. Khi một trong hai cột nguồn đổi, giá trị sinh được cập nhật theo quy tắc của hệ quản trị.

Có thể hình dung quan hệ phụ thuộc:

~~~text
quantity ────┐
             ├──► quantity * unit_price ──► line_total
unit_price ──┘
~~~

Điểm quan trọng là **line_total phụ thuộc vào dữ liệu gốc**, thay vì là nguồn dữ liệu độc lập. Tính chất này gọi là *dữ liệu dẫn xuất* (*derived data*).

Một cột sinh thường được:

- Khai báo bằng biểu thức trong định nghĩa bảng.
- Tính tự động khi cần theo cơ chế của hệ quản trị.
- Đọc bằng **SELECT** như một cột thông thường.
- Không cho phép gán một giá trị tùy ý qua **INSERT/UPDATE**.
- Có thể được đưa vào chỉ mục hoặc ràng buộc nếu phương ngữ và biểu thức đáp ứng điều kiện.

**Đừng nhầm cột sinh với giá trị chỉ được tính trong SELECT.** Ví dụ:

~~~sql
SELECT quantity, unit_price,
       quantity * unit_price AS line_total
FROM order_lines;
~~~

Cột **line_total** ở truy vấn trên chỉ là **bí danh của một biểu thức trong kết quả**. Nó không tự thêm cột vào lược đồ bảng. Cột generated mới là phần được định nghĩa trong **CREATE TABLE** hoặc **ALTER TABLE**.

## 3. Phân biệt generated, DEFAULT, IDENTITY và VIEW

Những cơ chế sau thường bị gọi chung là “cột tự động”, nhưng mục đích và ngữ nghĩa khác nhau:

| Cơ chế | Cách tạo giá trị | Khi cột nguồn thay đổi | Ví dụ |
| --- | --- | --- | --- |
| **DEFAULT** | Điền giá trị mặc định khi INSERT không cung cấp giá trị | Không tự tính lại dựa trên cột khác | created_at mặc định thời gian hiện tại |
| **IDENTITY/AUTO_INCREMENT** | Hệ quản trị cấp mã tăng dần theo cơ chế định danh | Không liên quan đến các cột dữ liệu còn lại | order_id |
| **Generated/computed column** | Áp dụng biểu thức khai báo trên dữ liệu của hàng | Giá trị dẫn xuất phản ánh dữ liệu nguồn mới | quantity × unit_price |
| **Biểu thức trong SELECT** | Tính vào lúc chạy truy vấn cụ thể | Truy vấn sau đọc dữ liệu mới sẽ tính lại | SELECT price * qty |
| **VIEW** | Định nghĩa truy vấn có thể tái sử dụng dưới dạng bảng logic | Truy vấn view thông thường đọc dữ liệu nguồn hiện tại | VIEW chứa line_total |
| **TRIGGER** | Chạy mã khi có sự kiện dữ liệu, có thể ghi nhiều cột hoặc bảng | Phụ thuộc mã trigger và các sự kiện đã cấu hình | Ghi nhật ký biến động giá |

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE demo_distinctions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL,
    line_total NUMERIC(14, 2)
        GENERATED ALWAYS AS (quantity * unit_price) STORED
);
~~~

Ở đây có **ba kiểu tự động khác nhau**:

1. **id** là cột định danh do hệ quản trị sinh số.
2. **created_at** có DEFAULT là thời điểm chèn hàng, **không tự đổi theo mỗi lần UPDATE**.
3. **line_total** được tính lại từ quantity và unit_price khi các giá trị nguồn thay đổi.

Đặc biệt, **GENERATED ALWAYS AS IDENTITY** là cú pháp tạo **identity**, còn **GENERATED ALWAYS AS (biểu thức) STORED** là cú pháp tạo **generated column**. Chúng dùng chung các từ khóa nhưng là **hai tính năng khác nhau**.

## 4. STORED, VIRTUAL và PERSISTED

Các phương ngữ thường phân biệt cách giữ giá trị của cột sinh:

**STORED (lưu vật lý):** Giá trị được tính khi ghi hoặc cập nhật hàng và được lưu vào dữ liệu bảng. Khi đọc, hệ quản trị có thể lấy giá trị đã lưu. Cách này thường dùng thêm không gian lưu trữ nhưng giảm nhu cầu tính biểu thức lúc đọc.

**VIRTUAL (tính khi đọc):** Giá trị không được lưu như dữ liệu của cột thông thường; hệ quản trị tính nó từ các cột nguồn khi truy vấn. Cách này tiết kiệm chỗ chứa giá trị cột nhưng có thể tăng chi phí đọc. Khi có chỉ mục trên cột virtual, chỉ mục vẫn có thể chứa giá trị phục vụ tra cứu, tùy hệ quản trị.

**PERSISTED (SQL Server):** Từ khóa gần với ý tưởng **STORED**: lưu kết quả tính toán của cột computed theo quy tắc SQL Server.

| Tiêu chí | STORED/PERSISTED | VIRTUAL |
| --- | --- | --- |
| Giá trị cột được lưu trong hàng | Có | Thông thường không |
| Khi cột nguồn thay đổi | Tính lại để lưu giá trị dẫn xuất | Lần đọc sau phản ánh nguồn mới |
| Chi phí ghi | Có thể cao hơn do tính và ghi | Thường giảm phần lưu giá trị dẫn xuất |
| Chi phí đọc | Có thể thấp hơn nếu biểu thức đắt | Có thể phải tính lại biểu thức |
| Dung lượng dữ liệu bảng | Tăng theo kích thước giá trị lưu | Không giữ thêm giá trị vật lý trong hàng |
| Chỉ mục | Tùy hệ quản trị và biểu thức | Tùy hệ quản trị; không phải mọi trường hợp đều hỗ trợ |

Không có kiểu nào luôn nhanh hơn. **Độ phức tạp của biểu thức, tần suất đọc/ghi, chỉ mục, độ lớn dữ liệu và bộ tối ưu của hệ quản trị** đều ảnh hưởng tới lựa chọn.

## 5. Thực hành với PostgreSQL: định nghĩa một bảng có hai cột sinh

Để thực hành độc lập, tạo **bảng tạm** PostgreSQL trong một phiên kết nối. Ví dụ này dùng **NUMERIC** cho tiền, giảm rủi ro làm tròn của số thực dấu phẩy động.

~~~sql
CREATE TEMP TABLE demo_order_lines (
    line_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_code VARCHAR(20) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    discount_percent NUMERIC(5, 2) NOT NULL DEFAULT 0
        CHECK (discount_percent BETWEEN 0 AND 100),

    gross_amount NUMERIC(14, 2)
        GENERATED ALWAYS AS (
            quantity * unit_price
        ) STORED,

    payable_amount NUMERIC(14, 2)
        GENERATED ALWAYS AS (
            ROUND(
                quantity * unit_price
                * (100 - discount_percent) / 100,
                2
            )
        ) STORED
);
~~~

Hai cột sinh có ý nghĩa:

- **gross_amount**: thành tiền trước giảm giá, bằng quantity × unit_price.
- **payable_amount**: thành tiền sau giảm giá theo tỷ lệ phần trăm, được làm tròn đến hai chữ số thập phân.

Vì ràng buộc **NOT NULL** và **CHECK** trên cột gốc, các giá trị quantity, unit_price và discount_percent đều có ý nghĩa xác định. Mọi ví dụ giá trong bài được hiểu là **VND**, không bao gồm thuế, phí vận chuyển hoặc các quy tắc kế toán phức tạp.

**Vì sao payable_amount không dùng gross_amount trong công thức?** Trong PostgreSQL 16–17, biểu thức của một cột generated **không được tham chiếu cột generated khác**. Vì vậy, công thức payable_amount phải dùng trực tiếp các cột nguồn **quantity**, **unit_price** và **discount_percent**, dù nó lặp lại một phần biểu thức.

### 5.1. INSERT chỉ ghi các cột đầu vào

~~~sql
INSERT INTO demo_order_lines
    (product_code, quantity, unit_price, discount_percent)
VALUES
    ('P001', 2, 125000, 10),
    ('P002', 3,  40000,  0),
    ('P003', 1,  99900,  5);

SELECT
    line_id,
    product_code,
    quantity,
    unit_price,
    discount_percent,
    gross_amount,
    payable_amount
FROM demo_order_lines
ORDER BY line_id;
~~~

Kết quả dự kiến khi bảng tạm mới được tạo:

| line_id | product_code | quantity | unit_price | discount_percent | gross_amount | payable_amount |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | P001 | 2 | 125000.00 | 10.00 | 250000.00 | 225000.00 |
| 2 | P002 | 3 | 40000.00 | 0.00 | 120000.00 | 120000.00 |
| 3 | P003 | 1 | 99900.00 | 5.00 | 99900.00 | 94905.00 |

Không có cột gross_amount hay payable_amount trong danh sách INSERT, nhưng SELECT vẫn đọc được các giá trị dẫn xuất.

### 5.2. UPDATE cột nguồn làm thay đổi cột sinh

~~~sql
UPDATE demo_order_lines
SET unit_price = 135000
WHERE product_code = 'P001';

SELECT
    product_code,
    quantity,
    unit_price,
    gross_amount,
    payable_amount
FROM demo_order_lines
WHERE product_code = 'P001';
~~~

Dòng P001 lúc này có **gross_amount = 270000.00** và **payable_amount = 243000.00**. Hệ quản trị tính giá trị dẫn xuất từ **2 × 135000** và mức giảm **10%**, không cần ứng dụng gửi thêm lệnh UPDATE cho hai cột sinh.

Điều này cũng cho thấy vì sao phải xác định ý nghĩa của giá sản phẩm: trong bảng **dòng đơn hàng**, unit_price nên là giá tại thời điểm giao dịch. Không nên tự động đồng bộ giá lịch sử của đơn hàng với giá niêm yết hiện tại trong danh mục sản phẩm.

### 5.3. Không gán tùy ý giá trị cho cột generated

Cú pháp dưới đây minh họa một thao tác **không hợp lệ** và chỉ nên xem như ví dụ lỗi:

~~~sql
-- Ví dụ lỗi: không được tự nhập số khác vào cột generated.
INSERT INTO demo_order_lines
    (product_code, quantity, unit_price, gross_amount)
VALUES
    ('P004', 2, 100000, 1);
~~~

PostgreSQL từ chối vì **gross_amount** được quản lý bởi biểu thức sinh. Cách đúng là chỉ nhập những cột nguồn:

~~~sql
INSERT INTO demo_order_lines
    (product_code, quantity, unit_price)
VALUES
    ('P004', 2, 100000);
~~~

Với PostgreSQL, từ khóa **DEFAULT** có thể xuất hiện ở vị trí cột generated trong INSERT/UPDATE, nhưng không có nghĩa là ứng dụng có thể chỉ định giá trị tùy chọn cho cột ấy. Thông thường, **nên bỏ hẳn cột generated khỏi danh sách ghi** để ý định rõ ràng.

### 5.4. Dùng cột sinh trong truy vấn

~~~sql
SELECT product_code, gross_amount, payable_amount
FROM demo_order_lines
WHERE payable_amount >= 100000
ORDER BY payable_amount DESC, product_code;
~~~

Ứng dụng có thể **SELECT, WHERE, ORDER BY, GROUP BY** theo giá trị sinh như những cột thông thường, trong phạm vi cú pháp và quy định của hệ quản trị.

Ví dụ tính tổng tiền từ dữ liệu dòng:

~~~sql
SELECT
    SUM(gross_amount) AS total_before_discount,
    SUM(payable_amount) AS total_after_discount
FROM demo_order_lines;
~~~

Phép **SUM** ở đây nằm trong **truy vấn SELECT**, không nằm trong biểu thức định nghĩa cột. Cột payable_amount chỉ tính cho **một hàng**; tổng của nhiều hàng được tính khi truy vấn.

## 6. Những biểu thức nào được phép trong generated column?

Nguyên tắc chung là công thức cột sinh phải mô tả **giá trị xác định từ dữ liệu của hàng**, còn giới hạn cụ thể tùy hệ quản trị và phiên bản.

### 6.1. Những biểu thức thường phù hợp

Các nhóm ví dụ sau dễ hiểu và tương đối phổ biến (cú pháp hàm có thể thay đổi theo phương ngữ):

| Dữ liệu nguồn | Biểu thức dẫn xuất | Ý nghĩa |
| --- | --- | --- |
| quantity, unit_price | quantity * unit_price | Thành tiền của một dòng |
| first_name, last_name | ghép chuỗi và chuẩn hóa khoảng trắng | Tên đầy đủ |
| email | LOWER(email) | Email dạng chuẩn hóa để tìm kiếm |
| width, height | width * height | Diện tích hình chữ nhật |
| start_date, end_date | tính chênh lệch theo quy tắc được hỗ trợ | Khoảng thời gian |
| một cột số | phép toán và CASE có thể xác định | Phân loại theo ngưỡng |

Ví dụ PostgreSQL với cột chuẩn hóa email:

~~~sql
CREATE TEMP TABLE demo_contacts (
    contact_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL,
    email_key TEXT GENERATED ALWAYS AS (
        LOWER(TRIM(email))
    ) STORED
);

INSERT INTO demo_contacts (email)
VALUES ('  Student@Example.Test  ');

SELECT email, email_key
FROM demo_contacts;
~~~

Giá trị **email** gốc được giữ nguyên, còn **email_key** sẽ là **student@example.test**. Có thể dùng email_key cho một số phép tìm kiếm hoặc ràng buộc duy nhất, tùy yêu cầu. Tuy nhiên, việc chuẩn hóa email trong hệ thống thực tế phải xét chính sách về phân biệt chữ hoa, tên miền, Unicode và cách người dùng xác thực địa chỉ; LOWER/TRIM không giải quyết mọi trường hợp.

### 6.2. Những giới hạn phổ biến

| Nhóm giới hạn | Vì sao cần chú ý? |
| --- | --- |
| **Hàm phụ thuộc thời điểm** như thời gian hiện tại | Cùng dữ liệu nguồn nhưng kết quả có thể thay đổi theo thời gian |
| **Hàm ngẫu nhiên** | Không xác định duy nhất giá trị từ cột nguồn |
| **Subquery** hoặc đọc bảng khác | Công thức không còn là phép tính thuần trên cùng hàng |
| **Hàm tổng hợp** như SUM, COUNT, AVG | Các phép này cần nhìn nhiều hàng |
| **Hàm cửa sổ** như ROW_NUMBER, RANK | Phụ thuộc tập hàng và thứ tự |
| **Tham chiếu cột generated khác** | Có thể bị cấm hoặc giới hạn thứ tự phụ thuộc tùy phương ngữ |
| **Thay đổi chính cột sinh bằng UPDATE** | Mâu thuẫn với định nghĩa hệ quản trị tự tính |
| **Kiểu dữ liệu, độ dài, độ chính xác** | Biểu thức phải chuyển được sang kiểu cột và không tràn phạm vi |

Trong PostgreSQL 16–17, biểu thức cột generated chỉ được dùng các **hàm được đánh dấu IMMUTABLE**, không được có truy vấn con và không được tham chiếu hàng khác. Hàm **CURRENT_TIMESTAMP**, **NOW()**, **RANDOM()** không phù hợp để làm biểu thức generated theo quy tắc này.

Ví dụ ý tưởng **không hợp lệ**:

~~~sql
-- Ví dụ minh họa lỗi, KHÔNG chạy khi chuẩn bị bảng thực hành:
CREATE TABLE invalid_example (
    created_at TIMESTAMP GENERATED ALWAYS AS (CURRENT_TIMESTAMP) STORED
);
~~~

Nếu cần ghi **thời điểm tạo bản ghi**, dùng **DEFAULT CURRENT_TIMESTAMP**:

~~~sql
CREATE TEMP TABLE demo_events (
    event_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Nếu cần tính **tuổi hiện tại** từ ngày sinh, không nên lưu một cột generated bằng công thức chứa ngày hiện tại rồi cho rằng nó tự tăng mỗi ngày. Hãy tính tuổi vào lúc truy vấn hoặc ở tầng ứng dụng theo quy tắc ngày/giờ thích hợp.

### 6.3. Không dùng generated column để cộng nhiều hàng

Giả sử có hai bảng:

~~~text
orders(order_id, customer_id, ...)
order_items(order_id, product_id, quantity, unit_price)
~~~

Không thể coi **SUM(quantity × unit_price) của mọi dòng trong một đơn** là biểu thức generated thông thường trên bảng orders: phép tính phải đọc **nhiều hàng ở bảng order_items**, vượt phạm vi cột sinh của một hàng.

Cách tính tại thời điểm đọc:

~~~sql
SELECT
    order_id,
    SUM(quantity * unit_price) AS order_total
FROM order_items
GROUP BY order_id;
~~~

Trong hệ thống cần lưu tổng của nhiều hàng để truy cập nhanh, có thể cân nhắc **bảng tổng hợp, materialized view, trigger hoặc quy trình cập nhật có kiểm soát**. Các lựa chọn ấy có trách nhiệm đồng bộ riêng và không tương đương với một cột generated đơn giản.

## 7. NULL, kiểu dữ liệu, làm tròn và CHECK

### 7.1. Biểu thức sinh thường chịu quy tắc NULL như biểu thức SQL khác

Nếu quantity hoặc unit_price có thể NULL, thì phép nhân thông thường **quantity * unit_price** sẽ cho NULL khi một toán hạng NULL. Đây không phải lỗi kỹ thuật; đó là ngữ nghĩa phép tính khi đầu vào chưa xác định.

~~~sql
SELECT
    2 * NULL::NUMERIC        AS amount_unknown,
    2 * COALESCE(NULL::NUMERIC, 0) AS amount_assumed_zero;
~~~

Cột thứ nhất là NULL; cột thứ hai là 0 do **ta chủ động thay NULL bằng 0**. Hai cách diễn đạt **khác nghĩa nghiệp vụ**: “chưa biết đơn giá” không nhất thiết tương đương “đơn giá bằng 0”.

Ở bảng demo_order_lines, ba cột nguồn được khai báo **NOT NULL** để giá trị dẫn xuất không bị thiếu do các đầu vào này.

### 7.2. Khai báo kiểu cột sinh rõ ràng

Không nên mặc định rằng hệ quản trị tự suy ra kiểu biểu thức theo cùng một cách trên mọi nền tảng. Một số phương ngữ yêu cầu kiểu cột được khai báo; một số phương ngữ có cơ chế khác. Ở PostgreSQL, khai báo:

~~~sql
gross_amount NUMERIC(14, 2)
    GENERATED ALWAYS AS (quantity * unit_price) STORED
~~~

có nghĩa là kết quả phải phù hợp kiểu **NUMERIC(14,2)**. Giá trị ngoài phạm vi hoặc không chuyển đổi được sẽ gây lỗi khi ghi dữ liệu nguồn; kết quả cần được làm tròn theo quy tắc của biểu thức và kiểu đích.

Với tiền, **NUMERIC/DECIMAL** thường phù hợp hơn **FLOAT/REAL/DOUBLE** nếu cần biểu diễn thập phân chính xác. Trong ứng dụng yêu cầu quy tắc làm tròn chặt chẽ, hãy quy định rõ lúc nào làm tròn, trước hay sau thuế/giảm giá, và cách phân bổ số lẻ.

### 7.3. Ràng buộc áp dụng cho dữ liệu nguồn và dữ liệu sinh

~~~sql
quantity INTEGER NOT NULL CHECK (quantity > 0),
unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
discount_percent NUMERIC(5, 2) NOT NULL DEFAULT 0
    CHECK (discount_percent BETWEEN 0 AND 100)
~~~

Các ràng buộc trên ngăn những đầu vào rõ ràng không hợp lệ. Tuy vậy, **CHECK** không thay được toàn bộ kiểm tra nghiệp vụ: ví dụ “khuyến mãi không được áp dụng cho một số sản phẩm” cần thông tin khác ngoài ba cột này.

Một cột sinh cũng có thể tham gia ràng buộc hoặc chỉ mục khi hệ quản trị cho phép, nhưng cần xét khả năng sinh NULL, cách so sánh, tính xác định của công thức và quy tắc của phương ngữ.

## 8. Chỉ mục trên cột sinh và chỉ mục theo biểu thức

Giả sử hệ thống thường lọc các dòng có payable_amount lớn:

~~~sql
SELECT *
FROM demo_order_lines
WHERE payable_amount >= 500000;
~~~

Trong PostgreSQL, có thể lập chỉ mục B-tree trên cột generated dạng STORED như một cột dữ liệu:

~~~sql
CREATE INDEX idx_demo_order_lines_payable
    ON demo_order_lines (payable_amount);
~~~

Chỉ mục có thể giúp truy vấn chọn lọc trên bảng lớn; với bảng mẫu vài dòng, bộ tối ưu có thể không dùng nó vì quét tuần tự rẻ hơn.

**Nếu chỉ cần tăng tốc tìm kiếm theo biểu thức mà không cần một cột xuất hiện trong lược đồ, có thể dùng chỉ mục theo biểu thức**:

~~~sql
CREATE INDEX idx_demo_order_lines_gross_expression
    ON demo_order_lines ((quantity * unit_price));
~~~

Hai cơ chế giải quyết những nhu cầu có phần khác nhau:

| Nhu cầu | Cột generated | Chỉ mục theo biểu thức |
| --- | --- | --- |
| Muốn có tên cột để SELECT hoặc công cụ báo cáo đọc | Phù hợp | Không tự tạo cột đầu ra |
| Muốn thống nhất công thức trong lược đồ | Phù hợp | Định nghĩa nằm trong biểu thức chỉ mục |
| Muốn tối ưu tìm theo biểu thức | Có thể lập chỉ mục nếu hỗ trợ | Trực tiếp phục vụ nhu cầu này |
| Muốn giảm lưu trữ khi không cần cột | VIRTUAL có thể có ích | Không cần cột, nhưng chỉ mục vẫn tốn dung lượng |
| Muốn so sánh khả năng di chuyển phương ngữ | Cú pháp generated khác nhau | Cú pháp/chức năng expression index cũng khác nhau |

Không thêm chỉ mục một cách máy móc. **Chỉ mục có chi phí lưu trữ và cập nhật**, nên cần dựa vào mẫu truy vấn thực tế, độ chọn lọc và kế hoạch thực thi.

## 9. Cú pháp theo từng phương ngữ

SQL có nhiều phương ngữ. Những ví dụ dưới đây là **những cách viết riêng biệt**, không phải các khối có thể chạy tuần tự trong cùng một database.

### 9.1. PostgreSQL 16–17: GENERATED ALWAYS AS (...) STORED

~~~sql
CREATE TABLE order_line_pg (
    line_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL,
    line_total NUMERIC(14, 2)
        GENERATED ALWAYS AS (quantity * unit_price) STORED
);
~~~

Với PostgreSQL 16–17:

- Dạng cột sinh được dùng là **STORED**.
- Công thức phải dùng các hàm/toán tử phù hợp yêu cầu **IMMUTABLE** và chỉ tham chiếu cột phù hợp trên cùng hàng.
- Không dùng subquery, aggregate hoặc window function trong biểu thức sinh.
- Một cột generated không được khai báo **DEFAULT** hay **IDENTITY** cho chính cột ấy; hai cột khác nhau trong bảng có thể lần lượt là identity và generated.
- Không thể viết đè giá trị generated bằng INSERT/UPDATE thông thường.

**Ghi chú về phiên bản:** PostgreSQL có thay đổi khả năng hỗ trợ cột sinh giữa các phiên bản. Ví dụ trong bài cố ý dùng **STORED** để tương thích PostgreSQL 16–17; nếu muốn dùng **VIRTUAL** ở phiên bản mới hơn, cần kiểm tra tài liệu chính xác của phiên bản triển khai, nhất là những hạn chế về hàm, kiểu dữ liệu và biểu thức.

### 9.2. MySQL 8.0: VIRTUAL hoặc STORED

~~~sql
CREATE TABLE order_line_mysql (
    line_id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    quantity INT NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    line_total DECIMAL(14, 2)
        GENERATED ALWAYS AS (quantity * unit_price) STORED
);
~~~

MySQL còn cho phép:

~~~sql
line_total DECIMAL(14, 2)
    GENERATED ALWAYS AS (quantity * unit_price) VIRTUAL
~~~

Trong MySQL 8.0, **VIRTUAL** là lựa chọn mặc định nếu bỏ từ khóa VIRTUAL/STORED trong định nghĩa generated column. Dạng STORED lưu giá trị đã tính, còn dạng VIRTUAL tính theo cơ chế của MySQL. MySQL hỗ trợ chỉ mục trên generated column trong các điều kiện cho phép, kể cả nhiều trường hợp VIRTUAL.

MySQL đặt các giới hạn đối với biểu thức, đặc biệt các hàm không xác định và truy vấn con. Một số khả năng tham chiếu cột sinh khác, ràng buộc và index phụ thuộc vào **phiên bản MySQL** và **storage engine**. Hãy tránh giả định rằng những gì hợp lệ trên PostgreSQL sẽ hợp lệ nguyên văn trên MySQL.

### 9.3. SQLite 3.31+: VIRTUAL hoặc STORED

~~~sql
CREATE TABLE order_line_sqlite (
    line_id INTEGER PRIMARY KEY,
    quantity INTEGER NOT NULL,
    unit_price INTEGER NOT NULL,
    line_total INTEGER
        GENERATED ALWAYS AS (quantity * unit_price) VIRTUAL
);
~~~

Ví dụ SQLite dùng **số nguyên theo đơn vị đồng** để minh họa. SQLite có quy tắc kiểu dữ liệu khác hệ SQL dùng DECIMAL cố định; nếu bài toán tiền yêu cầu chính xác, lưu bằng đơn vị nguyên nhỏ nhất có thể là một lựa chọn thiết kế phù hợp.

SQLite hỗ trợ generated column **VIRTUAL** và **STORED** từ phiên bản **3.31.0**. VIRTUAL là mặc định khi không chỉ định loại. Một giới hạn đáng chú ý: **ALTER TABLE ... ADD COLUMN** có thể thêm cột generated VIRTUAL nhưng **không trực tiếp thêm cột generated STORED** bằng cú pháp đó; việc bổ sung STORED thường cần quy trình xây dựng lại bảng.

Biểu thức generated trong SQLite phải phù hợp quy tắc biểu thức scalar có tính xác định, không dùng subquery, aggregate, window function hoặc truy cập bảng khác. SQLite cho phép tạo chỉ mục trên generated column theo những quy tắc của hệ.

### 9.4. SQL Server: computed column, tùy chọn PERSISTED

~~~sql
CREATE TABLE dbo.order_line_sqlserver (
    line_id INT IDENTITY(1,1) PRIMARY KEY,
    quantity INT NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    line_total AS CAST(
        quantity * unit_price AS DECIMAL(14, 2)
    ) PERSISTED
);
~~~

SQL Server thường gọi đây là **computed column**, dùng cú pháp **column_name AS expression**. Nếu muốn lưu kết quả, có thể thêm **PERSISTED** khi biểu thức đáp ứng yêu cầu. Không có PERSISTED, giá trị thường được tính khi cần theo cơ chế computed column.

Các yêu cầu về **tính xác định (determinism)**, **độ chính xác (precision)**, kiểu dữ liệu, tùy chọn phiên và khả năng tạo **index trên computed column** có quy tắc riêng. Cú pháp PostgreSQL **GENERATED ALWAYS AS (...) STORED** không chạy nguyên văn trên SQL Server.

### 9.5. Bảng so sánh nhanh

| Hệ quản trị / phiên bản minh họa | Tên tính năng phổ biến | Cú pháp cốt lõi | Kiểu lưu trữ | Lưu ý nổi bật |
| --- | --- | --- | --- | --- |
| PostgreSQL 16–17 | Generated column | GENERATED ALWAYS AS (...) STORED | STORED trong các phiên bản này | Biểu thức IMMUTABLE, giới hạn tham chiếu cùng hàng |
| MySQL 8.0 | Generated column | GENERATED ALWAYS AS (...) VIRTUAL/STORED | VIRTUAL, STORED | VIRTUAL thường là mặc định; giới hạn phụ thuộc biểu thức và engine |
| SQLite 3.31+ | Generated column | GENERATED ALWAYS AS (...) VIRTUAL/STORED | VIRTUAL, STORED | Không ADD COLUMN STORED trực tiếp bằng ALTER TABLE ADD COLUMN |
| SQL Server | Computed column | column AS expression [PERSISTED] | Không persisted hoặc PERSISTED | Quy tắc index/determinism/precision đặc thù |

**Các tên cùng ý nghĩa gần nhau không bảo đảm hành vi giống hệt nhau.** Bảng này chỉ đối chiếu khái niệm; quyết định triển khai phải dựa vào **hệ và phiên bản thực tế**, nhất là khi tổ chức dùng nhiều database hoặc cần chuyển đổi hệ quản trị.

## 10. Những khác biệt thường gây lỗi khi di chuyển schema

### 10.1. Khác cú pháp định nghĩa cột

Ví dụ PostgreSQL:

~~~sql
line_total NUMERIC(14, 2)
    GENERATED ALWAYS AS (quantity * unit_price) STORED
~~~

Ví dụ SQL Server:

~~~sql
line_total AS CAST(quantity * unit_price AS DECIMAL(14, 2)) PERSISTED
~~~

Ngay cả khi công thức toán học giống nhau, cú pháp tên kiểu, cách khai báo cột và từ khóa lưu trữ khác nhau. Không thể sao chép nguyên CREATE TABLE rồi chỉ thay tên database.

### 10.2. Khác về hàm và tính xác định

**LOWER**, **TRIM**, xử lý thời gian, làm tròn và chuyển kiểu có thể có cú pháp hoặc quy tắc khác nhau. Một hệ cho phép một hàm trong biểu thức generated nhưng hệ khác có thể từ chối, hoặc đánh giá khác khi collation/kiểu dữ liệu khác.

Ví dụ “định nghĩa ngày hiện tại” thường là một biểu thức **thay đổi theo thời gian**, không phù hợp với cột sinh cần được xác định từ dữ liệu gốc. Nếu cần snapshot thời gian tại INSERT, dùng **DEFAULT** hoặc cơ chế ghi dữ liệu phù hợp.

### 10.3. Khác về kiểu số và làm tròn

Giá trị tính ra có thể bị ảnh hưởng bởi:

- **DECIMAL/NUMERIC** so với kiểu số thực dấu phẩy động.
- Độ chính xác và số chữ số phần thập phân.
- Phép chia số nguyên hay thập phân.
- Quy tắc làm tròn của hàm và kiểu đích.
- Giới hạn lớn nhất có thể lưu trong cột.

Khi chuyển schema giữa các hệ, hãy thống nhất trước **quy tắc tính toán nghiệp vụ** và **độ chính xác dữ liệu**, không chỉ chuyển được cú pháp.

### 10.4. Khác về NULL và ràng buộc

Biểu thức **quantity * unit_price** thường cho NULL khi một đầu vào NULL. Tuy nhiên, cách suy ra khả năng NULL của computed column, cách dùng NOT NULL và khả năng lập index có thể khác giữa các phương ngữ.

Chọn **COALESCE** để ép NULL thành số 0 chỉ khi nghiệp vụ xác nhận rằng thiếu đầu vào có thể được hiểu là 0. Việc dùng COALESCE để làm biểu thức “không còn NULL” có thể che giấu dữ liệu thiếu giá.

### 10.5. Khác về chỉ mục và điều kiện tạo index

Một số hệ cho phép lập index trên STORED và VIRTUAL, nhưng điều kiện về biểu thức, tính xác định, kiểu dữ liệu và cấu hình có thể khác. Đặc biệt, **computed column trong SQL Server** có quy tắc riêng về deterministic/precise expression và tùy chọn kết nối khi tạo hoặc sử dụng index.

Khi di chuyển, không nên coi việc **CREATE TABLE thành công** là bằng chứng rằng **mọi index và constraint** cũ cũng sẽ được hỗ trợ theo cách tương đương.

### 10.6. Khác về ALTER TABLE và migration

Việc **thêm, đổi biểu thức, chuyển VIRTUAL ↔ STORED hoặc xóa cột generated** không có một cú pháp chuẩn duy nhất được mọi hệ hỗ trợ. Chẳng hạn, SQLite hạn chế thêm STORED bằng ALTER TABLE ADD COLUMN; PostgreSQL và MySQL có cơ chế riêng để thêm hoặc thay đổi định nghĩa cột.

Các hệ lưu vật lý có thể phải tính hoặc ghi lại giá trị cho những hàng hiện có. Trên bảng lớn, điều này có thể tốn thời gian, phát sinh khóa hoặc yêu cầu triển khai theo nhiều bước. Vì vậy, hãy xem thay đổi generated column là **thay đổi lược đồ cần kế hoạch migration**, thay vì chỉ sửa một công thức trong mã nguồn ứng dụng.

## 11. Chọn generated column hay các giải pháp khác?

| Tình huống | Giải pháp thường phù hợp | Lý do |
| --- | --- | --- |
| Tính thành tiền từ quantity × unit_price trên cùng hàng | Generated column | Quy tắc ổn định, dễ tái sử dụng ở nhiều nơi |
| Tạo mã tăng tự động | IDENTITY/AUTO_INCREMENT | Đây là nhu cầu cấp định danh, không phải công thức từ cột nguồn |
| Ghi ngày tạo khi INSERT | DEFAULT CURRENT_TIMESTAMP | Cần lưu thời điểm sự kiện, không tính lại mỗi lần đọc |
| Tính tuổi hiện tại theo ngày sinh | Biểu thức trong SELECT hoặc tầng ứng dụng | Kết quả phụ thuộc ngày hiện tại |
| Tổng tiền đơn hàng từ nhiều dòng chi tiết | SELECT với GROUP BY, view hoặc bảng tổng hợp | Cần dữ liệu nhiều hàng/bảng |
| Chỉ cần biểu thức trong một báo cáo | SELECT hoặc VIEW | Không cần thêm cột vào schema |
| Chỉ cần tăng tốc WHERE LOWER(email) | Expression index hoặc generated + index tùy hệ | Quyết định dựa vào nhu cầu truy vấn và tính di động |
| Tự động ghi nhật ký mỗi lần giá thay đổi | Trigger hoặc cơ chế sự kiện | Cần ghi thêm bản ghi, không chỉ tính giá trị trong cùng hàng |

**Một cột generated không thay thế hệ thống xử lý nghiệp vụ.** Nó tốt nhất cho công thức rõ ràng, ổn định, phụ thuộc dữ liệu của cùng hàng và đáp ứng giới hạn biểu thức của hệ quản trị.

## 12. Ví dụ thiết kế lược đồ bán hàng thực tế hơn

Giả sử một đơn hàng có nhiều dòng. Ta muốn bảo đảm mỗi dòng có thành tiền đáng tin cậy, nhưng tổng đơn còn phụ thuộc nhiều dòng và trạng thái thanh toán.

~~~text
products
  product_id, current_price
          │
          │ được tra cứu khi khách đặt
          ▼
order_items
  order_id
  product_id
  quantity
  unit_price_at_order
  discount_percent
  line_amount  ◄── generated từ ba cột cùng hàng
          │
          │ SUM(line_amount) theo order_id
          ▼
SELECT / VIEW báo cáo tổng đơn
~~~

Ví dụ lược đồ PostgreSQL tối giản:

~~~sql
CREATE TABLE example_order_items (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_at_order NUMERIC(12, 2) NOT NULL
        CHECK (unit_price_at_order >= 0),
    discount_percent NUMERIC(5, 2) NOT NULL DEFAULT 0
        CHECK (discount_percent BETWEEN 0 AND 100),
    line_amount NUMERIC(14, 2)
        GENERATED ALWAYS AS (
            ROUND(
                quantity * unit_price_at_order
                * (100 - discount_percent) / 100,
                2
            )
        ) STORED,
    PRIMARY KEY (order_id, line_no)
);
~~~

**Lưu ý:** Ví dụ chỉ tập trung vào cột sinh. Trong cơ sở dữ liệu hoàn chỉnh, order_id và product_id thường phải được ràng buộc **FOREIGN KEY** tới các bảng orders/products tương ứng.

Mỗi dòng có giá tại thời điểm đặt **unit_price_at_order**. Khi giá niêm yết của sản phẩm đổi, lịch sử đơn vẫn giữ giá gốc. Từ đó:

~~~sql
SELECT order_id, SUM(line_amount) AS order_total
FROM example_order_items
GROUP BY order_id
ORDER BY order_id;
~~~

Truy vấn trên cộng các **line_amount đã tính đúng ở cấp dòng**, trong khi phép SUM vẫn nằm ở lớp truy vấn vì nó cần đọc **nhiều dòng**. Nếu đơn có phí giao hàng, thuế hoặc hoàn tiền, cần định nghĩa công thức tổng phù hợp, thay vì tự giả định SUM(line_amount) là số tiền thanh toán cuối cùng trong mọi hệ thống.

## 13. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| INSERT báo không thể ghi vào cột generated | Đã truyền trực tiếp giá trị cho cột hệ thống tự tính | Bỏ cột sinh khỏi danh sách INSERT |
| UPDATE cột sinh bị từ chối | Thử chỉnh kết quả dẫn xuất | UPDATE cột nguồn; xem lại công thức nếu quy tắc sai |
| CREATE TABLE báo hàm không hợp lệ | Công thức dùng hàm không xác định hoặc không được hỗ trợ | Dùng biểu thức deterministic/immutable phù hợp phương ngữ |
| CREATE TABLE báo lỗi ở subquery hoặc SUM | Công thức đọc nhiều hàng hoặc bảng khác | Chuyển sang SELECT, VIEW, bảng tổng hợp hoặc cơ chế khác |
| Cột mới không cho tham chiếu cột generated trước đó | Hệ quản trị hạn chế phụ thuộc giữa cột sinh | Dùng trực tiếp cột nguồn hoặc thiết kế lại công thức |
| Kết quả thành tiền bị NULL | Có cột nguồn NULL hoặc biểu thức chủ động trả NULL | Kiểm tra quy định NOT NULL và ý nghĩa dữ liệu thiếu |
| Thành tiền chênh do làm tròn | Khác kiểu dữ liệu/cấp độ làm tròn | Quy định kiểu DECIMAL và công thức làm tròn nhất quán |
| Ví dụ PostgreSQL không chạy trên SQL Server | Khác phương ngữ và tên cú pháp | Chuyển sang computed column AS ... PERSISTED |
| SQLite không thêm được STORED qua ALTER TABLE ADD COLUMN | Hạn chế schema migration của SQLite | Tạo lại bảng theo quy trình migration hỗ trợ |
| Có index nhưng truy vấn vẫn chậm | Khả năng chọn lọc thấp, biểu thức khác hoặc dữ liệu quá nhỏ | Xem kế hoạch thực thi và mẫu truy vấn thực tế |
| Giá lịch sử của đơn bị thay đổi | Dùng giá sản phẩm hiện tại như dữ liệu nguồn thay cho giá tại thời điểm đặt | Lưu unit_price_at_order trong order_items |

## 14. Bài thực hành

Các bài 1–7 dùng **PostgreSQL** và bảng tạm **demo_order_lines** ở phần 5:

1. Tạo bảng demo_order_lines có **gross_amount** và **payable_amount** là cột generated dạng STORED.
2. Chèn ba dòng dữ liệu P001, P002, P003 và đọc lại các cột sinh bằng SELECT. Giải thích tại sao không cần gửi line_total từ ứng dụng.
3. Đổi unit_price của P001 từ 125000 lên 135000. Quan sát gross_amount và payable_amount thay đổi thế nào.
4. Thử INSERT trực tiếp một giá trị vào gross_amount. Ghi lại lỗi và giải thích vì sao thao tác này bị từ chối.
5. Thêm một dòng có discount_percent = 100 và một dòng có discount_percent = 0. So sánh payable_amount của hai dòng.
6. Tạo chỉ mục trên payable_amount, rồi viết truy vấn lọc dòng có payable_amount từ 100000 trở lên. Giải thích việc tạo index không bảo đảm nó được dùng trong mọi truy vấn.
7. Thiết kế một cột generated mới tính **số tiền giảm** bằng quantity × unit_price × discount_percent / 100, có làm tròn hai chữ số. Không tham chiếu gross_amount hay payable_amount trong biểu thức khi dùng PostgreSQL 16–17.

Các bài suy luận/so sánh phương ngữ:

8. Vì sao **CURRENT_TIMESTAMP** phù hợp hơn với DEFAULT cho created_at, thay vì công thức generated cần thời điểm hiện tại?
9. Một cột **order_total** cần SUM nhiều order_items. Vì sao không thể thay bằng generated column đơn giản trên bảng orders?
10. Viết lại định nghĩa cột **line_total** từ PostgreSQL sang **MySQL 8.0** với VIRTUAL, rồi với STORED.
11. Viết định nghĩa cột tương đương trên **SQL Server** bằng computed column PERSISTED. Từ khóa **IDENTITY** khác gì với PERSISTED?
12. Giả sử dùng **SQLite 3.31+**, cần bổ sung một cột generated STORED vào bảng đang có dữ liệu. Vì sao không thể chỉ dùng ALTER TABLE ADD COLUMN STORED?
13. Khi chuyển một ứng dụng giữa PostgreSQL và SQLite, cần xem lại những yếu tố nào liên quan đến kiểu tiền, hàm được phép, ràng buộc và thay đổi lược đồ?
14. Với một trường email dùng thường xuyên trong WHERE LOWER(TRIM(email)) = ..., khi nào nên chọn **expression index**, khi nào nên chọn **generated column + index**?

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Cột generated có phải là một biểu thức SELECT được đặt bí danh bằng AS không?

**Trả lời:** Không. Bí danh SELECT chỉ tồn tại trong kết quả truy vấn; cột generated là một phần của **lược đồ bảng** và được hệ quản trị tính theo biểu thức đã khai báo.

**Câu 2.** DEFAULT CURRENT_TIMESTAMP và generated column có ý nghĩa giống nhau không?

**Trả lời:** Không. DEFAULT cung cấp giá trị khi INSERT không chỉ định cột. Cột generated phụ thuộc vào biểu thức và dữ liệu nguồn, thường được cập nhật cùng các thay đổi nguồn.

**Câu 3.** Có thể lưu tổng SUM của tất cả dòng order_items vào cột generated của orders không?

**Trả lời:** Không thể thực hiện trực tiếp bằng biểu thức cột generated thông thường, vì phép tổng hợp cần nhiều hàng và một bảng khác.

**Câu 4.** STORED có luôn tốt hơn VIRTUAL không?

**Trả lời:** Không. STORED thường tốn thêm dung lượng và công tính khi ghi; VIRTUAL có thể tốn công tính khi đọc. Cần xét tải đọc/ghi, chỉ mục và hỗ trợ của hệ quản trị.

**Câu 5.** Định nghĩa GENERATED ALWAYS AS (...) STORED trên PostgreSQL có thể dùng nguyên văn trên SQL Server không?

**Trả lời:** Không. SQL Server dùng cú pháp **computed column AS expression**, có tùy chọn **PERSISTED**, cùng các giới hạn riêng.

**Câu 6.** Nếu quantity = 2 còn unit_price = NULL, quantity × unit_price sẽ là gì?

**Trả lời:** **NULL** theo phép nhân SQL thông thường. Muốn cấm tình huống này, định nghĩa unit_price **NOT NULL**; chỉ dùng COALESCE nếu doanh nghiệp thực sự chấp nhận quy ước giá thiếu bằng 0.

## 16. Ghi nhớ cốt lõi

**Cột sinh từ biểu thức** đưa một quy tắc tính toán vào **lược đồ bảng**, giúp giá trị dẫn xuất luôn đi theo các cột nguồn và tránh nhập lại thủ công. Nó phù hợp nhất cho công thức **ổn định, tính từ dữ liệu của cùng một hàng**. **STORED/PERSISTED** và **VIRTUAL** khác nhau ở cách lưu và chi phí tính toán.

Mỗi phương ngữ có **cú pháp, giới hạn biểu thức, kiểu dữ liệu, chỉ mục và khả năng ALTER TABLE** riêng. Trước khi triển khai, hãy xác định **hệ quản trị cùng phiên bản**, kiểm tra dữ liệu nguồn có thể NULL hay không, thống nhất quy tắc làm tròn và lựa chọn cột generated chỉ khi nó thực sự đáp ứng ý nghĩa nghiệp vụ. Với phép tính phụ thuộc **nhiều hàng, bảng khác hoặc thời điểm hiện tại**, hãy cân nhắc SELECT, VIEW, DEFAULT, trigger hay các cơ chế tổng hợp phù hợp.
