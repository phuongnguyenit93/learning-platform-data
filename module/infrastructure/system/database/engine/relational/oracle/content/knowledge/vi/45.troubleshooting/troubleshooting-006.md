# ORA-01400, ORA-01438, ORA-12899 và dữ liệu vượt miền cho phép

Khi INSERT hoặc UPDATE dữ liệu vào Oracle Database, giá trị đầu vào phải thỏa mãn kiểu dữ liệu, độ dài, precision/scale, tính bắt buộc và các ràng buộc nghiệp vụ của cột. Nếu dữ liệu không phù hợp, Oracle từ chối thao tác và trả về lỗi. Ba lỗi thường gặp là:

- **ORA-01400: cannot insert NULL into (...)** — thao tác đang đưa giá trị NULL vào cột không cho phép NULL.
- **ORA-01438: value larger than specified precision allowed for this column** — giá trị số vượt precision mà cột NUMBER cho phép.
- **ORA-12899: value too large for column (...)** — giá trị ký tự vượt độ dài cột, xét theo BYTE hoặc CHAR semantics.

Ngoài ba lỗi này, dữ liệu có thể vi phạm CHECK constraint (ORA-02290), khóa ngoại (ORA-02291/ORA-02292), unique constraint (ORA-00001), hoặc lỗi chuyển đổi như ORA-01722 và ORA-01861. Những lỗi này có nguyên nhân khác nhau nên cách sửa cũng khác nhau.

Nguyên tắc xử lý là xác định chính xác cột và giá trị gây lỗi, đọc định nghĩa schema thực tế, kiểm tra dữ liệu nguồn và ranh giới nghiệp vụ, sau đó quyết định sửa dữ liệu hay thay đổi schema. Không nên tự động thay NULL bằng 0, cắt chuỗi hoặc làm tròn số chỉ để câu lệnh chạy thành công; các thao tác đó có thể làm thay đổi ý nghĩa dữ liệu.

## 1. Miền giá trị của một cột Oracle

Một cột có thể giới hạn dữ liệu theo nhiều lớp:

| Lớp | Ví dụ | Lỗi thường gặp |
|---|---|---|
| Cho phép NULL hay không | CUSTOMER_ID NOT NULL | ORA-01400 |
| Kiểu dữ liệu | NUMBER, DATE, VARCHAR2 | ORA-01722, ORA-01861, lỗi chuyển đổi |
| Precision/scale | NUMBER(7,2) | ORA-01438 |
| Độ dài chuỗi | VARCHAR2(30 BYTE) | ORA-12899 |
| Miền nghiệp vụ | CHECK (amount >= 0) | ORA-02290 |
| Tham chiếu | FOREIGN KEY đến CUSTOMER | ORA-02291, ORA-02292 |
| Tính duy nhất | UNIQUE (email) | ORA-00001 |

Miền giá trị của cột không chỉ là kiểu dữ liệu. Một cột NUMBER có thể nhận rất nhiều số, nhưng NUMBER(7,2) giới hạn độ chính xác và số chữ số thập phân. Một cột VARCHAR2 có thể lưu chuỗi, nhưng chỉ đến độ dài được khai báo. CHECK constraint có thể thu hẹp miền hơn nữa, ví dụ trạng thái chỉ được là OPEN, PAID hoặc CANCELLED.

Ví dụ thiết kế:

~~~sql
CREATE TABLE order_lines (
    order_line_id NUMBER(19) NOT NULL,
    order_id      NUMBER(19) NOT NULL,
    quantity      NUMBER(8, 3) NOT NULL,
    unit_price    NUMBER(12, 2) NOT NULL,
    status        VARCHAR2(20 CHAR) NOT NULL,
    note          VARCHAR2(500 CHAR),
    CONSTRAINT pk_order_lines
        PRIMARY KEY (order_line_id),
    CONSTRAINT ck_order_lines_quantity
        CHECK (quantity > 0),
    CONSTRAINT ck_order_lines_price
        CHECK (unit_price >= 0),
    CONSTRAINT ck_order_lines_status
        CHECK (status IN ('OPEN', 'FULFILLED', 'CANCELLED'))
);
~~~

Trong ví dụ, quantity phải có giá trị và lớn hơn 0; unit_price không âm; status bắt buộc và chỉ nhận các giá trị được liệt kê; note được phép NULL. Mỗi điều kiện giải quyết một loại dữ liệu không hợp lệ riêng.

## 2. ORA-01400: không thể chèn NULL vào cột NOT NULL

ORA-01400 xuất hiện khi INSERT tạo ra giá trị NULL cho một cột có ràng buộc NOT NULL. Error message thường nêu schema, table và column bị vi phạm, giúp khoanh vùng nơi cần kiểm tra.

Ví dụ:

~~~sql
CREATE TABLE customers (
    customer_id   NUMBER(19) NOT NULL,
    customer_name VARCHAR2(100 CHAR) NOT NULL,
    email         VARCHAR2(200 CHAR)
);
~~~

Câu lệnh sau thiếu customer_name:

~~~sql
INSERT INTO customers (customer_id, email)
VALUES (1001, 'customer@example.com');
~~~

Vì customer_name không được chỉ định và không có default, Oracle tạo giá trị NULL cho cột đó và từ chối INSERT.

Ví dụ khác truyền NULL tường minh:

~~~sql
INSERT INTO customers (
    customer_id,
    customer_name,
    email
)
VALUES (
    1002,
    NULL,
    'another@example.com'
);
~~~

Cột customer_name nhận NULL nên thao tác cũng thất bại.

### 2.1. Phân biệt bỏ qua cột và truyền NULL

Đây là khác biệt quan trọng khi dùng DEFAULT:

~~~sql
CREATE TABLE payment_methods (
    method_id   NUMBER(19) NOT NULL,
    method_name VARCHAR2(50 CHAR)
        DEFAULT 'UNSPECIFIED' NOT NULL
);
~~~

Nếu bỏ qua method_name:

~~~sql
INSERT INTO payment_methods (method_id)
VALUES (1);
~~~

Oracle dùng giá trị default 'UNSPECIFIED'.

Nếu truyền NULL tường minh:

~~~sql
INSERT INTO payment_methods (method_id, method_name)
VALUES (2, NULL);
~~~

Với DEFAULT thông thường, giá trị NULL tường minh vẫn là NULL và vi phạm NOT NULL. Trên Oracle hỗ trợ cú pháp này, DEFAULT ON NULL có thể chỉ định default được áp dụng cả khi INSERT truyền NULL:

~~~sql
CREATE TABLE payment_methods_v2 (
    method_id   NUMBER(19) NOT NULL,
    method_name VARCHAR2(50 CHAR)
        DEFAULT ON NULL 'UNSPECIFIED' NOT NULL
);
~~~

DEFAULT ON NULL là một quyết định về nghiệp vụ. Chỉ dùng khi NULL thực sự có nghĩa là “hãy dùng giá trị mặc định”. Nếu NULL có nghĩa là thiếu dữ liệu bắt buộc, nên để database từ chối thay vì âm thầm gán giá trị.

### 2.2. Chuỗi rỗng trong Oracle

Oracle xử lý chuỗi có độ dài bằng 0 trong các kiểu ký tự như VARCHAR2/CHAR như NULL. Vì vậy:

~~~sql
INSERT INTO customers (customer_id, customer_name)
VALUES (1003, '');
~~~

có thể dẫn đến ORA-01400 nếu customer_name là NOT NULL. Chuỗi chỉ gồm dấu cách, ví dụ '   ', không giống chuỗi rỗng; nó vẫn là một giá trị ký tự nếu không được ứng dụng hoặc constraint chuẩn hóa.

Nếu nghiệp vụ không chấp nhận chuỗi trắng, có thể kiểm soát bằng CHECK:

~~~sql
ALTER TABLE customers
  ADD CONSTRAINT ck_customers_name_not_blank
  CHECK (TRIM(customer_name) IS NOT NULL);
~~~

CHECK constraint chỉ kiểm tra điều kiện; với cột bắt buộc, vẫn nên khai báo NOT NULL riêng. Cần thử nghiệm điều kiện với dữ liệu và quy tắc chuẩn hóa của ứng dụng.

### 2.3. Nguyên nhân phổ biến

- INSERT không liệt kê cột bắt buộc và cột không có default.
- Ứng dụng bind NULL do trường DTO bị thiếu.
- Mapping ORM không gán giá trị trước khi persist.
- ETL/import có ô trống hoặc nguồn không có trường tương ứng.
- Trigger BEFORE INSERT gán NULL cho cột.
- INSERT INTO ... SELECT lấy NULL từ nguồn hoặc biểu thức CASE/NVL không đúng.
- Một view có INSTEAD OF trigger chuyển dữ liệu xuống bảng thật và tạo NULL cho cột bắt buộc.
- Giá trị chuỗi rỗng được Oracle xem như NULL.

Kiểm tra cả DML gốc và trigger. Không nên chỉ nhìn object mà ứng dụng gọi vì lỗi có thể xảy ra trong trigger hoặc procedure phía sau.

### 2.4. Cách xử lý ORA-01400

Chọn cách sửa theo ý nghĩa nghiệp vụ:

1. Nếu dữ liệu bắt buộc nhưng nguồn có giá trị hợp lệ, truyền đúng giá trị.
2. Nếu cột có giá trị mặc định hợp lý, khai báo DEFAULT và quyết định có cần DEFAULT ON NULL hay không.
3. Nếu NULL là trạng thái hợp lệ, xem xét bỏ NOT NULL sau khi đánh giá tác động tới ứng dụng, constraint và truy vấn.
4. Nếu dữ liệu nguồn bị thiếu, đưa bản ghi vào vùng reject/quarantine để bổ sung hoặc xử lý.
5. Nếu trigger hoặc biểu thức tạo NULL ngoài ý muốn, sửa logic ở đúng nơi tạo giá trị.

Không tự động thay mọi NULL bằng 0, 'UNKNOWN' hoặc một ngày giả. Những giá trị thay thế đó có thể khiến báo cáo, tính toán và logic nghiệp vụ sai.

## 3. ORA-01438: số vượt precision của NUMBER

ORA-01438 xuất hiện khi giá trị số sau khi được chuyển đổi/làm tròn theo scale không thể biểu diễn trong precision khai báo của cột.

Oracle NUMBER có thể được khai báo với precision và scale:

~~~sql
NUMBER(p, s)
~~~

- **p (precision)** là số chữ số có nghĩa tối đa.
- **s (scale)** là số chữ số ở bên phải dấu thập phân khi scale dương.
- Nếu scale bằng 0, cột lưu số nguyên theo precision.
- Scale âm cho phép làm tròn về bên trái dấu thập phân.
- NUMBER không chỉ định precision/scale có miền biểu diễn rộng hơn, nhưng vẫn có giới hạn của kiểu NUMBER Oracle.

Với NUMBER(p,s) có scale dương thường gặp, số chữ số phần nguyên tối đa là p - s.

Ví dụ:

~~~sql
CREATE TABLE invoices (
    invoice_id NUMBER(19) NOT NULL,
    amount     NUMBER(5, 2) NOT NULL
);
~~~

NUMBER(5,2) có tối đa 5 chữ số có nghĩa với 2 chữ số thập phân; miền giá trị dương thường gặp tối đa là 999.99. Các ví dụ:

| Giá trị đầu vào | Kết quả |
|---|---|
| 12.34 | Hợp lệ |
| 999.99 | Hợp lệ |
| 1000.00 | Vượt precision |
| 12.345 | Oracle làm tròn theo scale 2 trước khi lưu, nếu kết quả vẫn nằm trong precision |
| 999.995 | Làm tròn có thể đẩy giá trị vượt miền NUMBER(5,2) |

Ví dụ gây lỗi:

~~~sql
INSERT INTO invoices (invoice_id, amount)
VALUES (1, 1234.56);
~~~

Giá trị có 4 chữ số phần nguyên trong khi NUMBER(5,2) chỉ dành 3 chữ số phần nguyên. Oracle trả ORA-01438.

### 3.1. Phân biệt precision và scale

Với NUMBER(8,2):

- Có tối đa 8 chữ số có nghĩa theo precision.
- Có 2 chữ số thập phân theo scale.
- Có thể chứa tối đa 6 chữ số phần nguyên trong trường hợp thông thường.
- Giá trị như 123456.78 vừa miền.
- Giá trị 1234567.89 vượt miền.

Scale không phải số chữ số phần nguyên. Ví dụ NUMBER(8,2) không có nghĩa là “8 chữ số trước dấu phẩy và 2 chữ số sau dấu phẩy”; tổng precision mới là 8.

Với NUMBER(6,0), số được lưu không có phần thập phân. Với NUMBER(6,3), miền phần nguyên nhỏ hơn vì 3 chữ số precision dành cho phần thập phân. Với scale âm, Oracle làm tròn về bội số của 10, 100... tùy giá trị scale; hãy xem định nghĩa cột và test dữ liệu biên.

### 3.2. Oracle làm gì với phần thập phân vượt scale?

Nếu giá trị có nhiều chữ số thập phân hơn scale, Oracle thường làm tròn theo scale của cột khi lưu, thay vì luôn trả lỗi. Ví dụ NUMBER(5,2) có thể lưu 12.345 thành 12.35. Tuy nhiên, sau khi làm tròn, nếu số chữ số vượt precision, thao tác vẫn có thể lỗi.

Không nên dựa vào hành vi làm tròn ngầm nếu quy tắc tài chính cần được xác định rõ. Hãy quyết định rounding mode ở tầng nghiệp vụ và kiểm tra miền trước khi ghi.

### 3.3. Cách xử lý ORA-01438

- Xác định giá trị đầu vào có hợp lệ theo nghiệp vụ hay không.
- Nếu giá trị đúng và cột khai báo quá hẹp, cân nhắc tăng precision.
- Nếu giá trị sai do nhập nhầm đơn vị, chuyển đổi hoặc dấu thập phân, sửa dữ liệu nguồn.
- Nếu số chữ số thập phân không hợp lệ, áp dụng quy tắc làm tròn/từ chối đã thống nhất.
- Nếu cột dùng để lưu số lượng, tiền, tỷ lệ hoặc mã, chọn precision/scale phù hợp ngay từ thiết kế.

Ví dụ tăng precision:

~~~sql
ALTER TABLE invoices
  MODIFY (amount NUMBER(12, 2));
~~~

Trước khi đổi, kiểm tra tất cả ứng dụng, view, package, trigger, ETL, index/function-based index và hợp đồng dữ liệu sử dụng cột. Tăng precision thường mở rộng miền lưu, nhưng thay đổi kiểu vẫn cần review và triển khai tương thích.

Nếu nghiệp vụ không cho phép số âm hoặc số quá lớn, tăng precision không giải quyết điều kiện nghiệp vụ. Dùng CHECK constraint để biểu diễn miền hợp lệ:

~~~sql
ALTER TABLE invoices
  ADD CONSTRAINT ck_invoices_amount
  CHECK (amount BETWEEN 0 AND 9999999999.99);
~~~

CHECK constraint có thể trả ORA-02290 khi giá trị ngoài miền. Cột cần NOT NULL riêng nếu NULL không được phép vì biểu thức CHECK có thể cho kết quả UNKNOWN khi giá trị là NULL.

## 4. ORA-12899: chuỗi vượt độ dài cột

ORA-12899 xuất hiện khi giá trị ký tự được ghi dài hơn giới hạn cột. Error message thường nêu tên owner/table/column và actual/max length. Đơn vị độ dài phụ thuộc khai báo BYTE hay CHAR và thông tin phiên bản Oracle trong message.

Ví dụ:

~~~sql
CREATE TABLE contacts (
    contact_id NUMBER(19) NOT NULL,
    full_name  VARCHAR2(20 BYTE) NOT NULL
);
~~~

Giá trị sau có thể vượt 20 byte:

~~~sql
INSERT INTO contacts (contact_id, full_name)
VALUES (1, 'Nguyễn Văn An');
~~~

Tên có thể chỉ gồm một số ký tự nhìn thấy, nhưng trong bộ ký tự đa byte như AL32UTF8, một ký tự có thể chiếm nhiều byte. Do đó độ dài theo byte có thể lớn hơn số ký tự.

### 4.1. BYTE semantics và CHAR semantics

Oracle cho phép khai báo độ dài VARCHAR2 theo byte hoặc ký tự:

~~~sql
CREATE TABLE byte_columns (
    code VARCHAR2(20 BYTE)
);

CREATE TABLE char_columns (
    display_name VARCHAR2(20 CHAR)
);
~~~

- **BYTE semantics** giới hạn số byte được lưu trong database character set.
- **CHAR semantics** giới hạn số ký tự theo semantics của Oracle, trong khi vẫn chịu giới hạn byte tối đa mà kiểu dữ liệu/database cho phép.

Nếu database dùng AL32UTF8, chữ có dấu hoặc ký tự ngoài ASCII có thể dùng nhiều byte. Một cột VARCHAR2(20 BYTE) vì vậy có thể chứa ít hơn 20 ký tự tiếng Việt. VARCHAR2(20 CHAR) phù hợp hơn khi yêu cầu nghiệp vụ là tối đa 20 ký tự, nhưng vẫn cần lưu ý giới hạn byte tối đa của Oracle.

Nếu không ghi rõ BYTE/CHAR trong DDL, semantics mặc định có thể chịu ảnh hưởng của tham số NLS_LENGTH_SEMANTICS tại thời điểm tạo cột. Để schema rõ ràng và nhất quán giữa môi trường, nên chỉ định tường minh trong DDL.

### 4.2. LENGTH và LENGTHB

Oracle cung cấp các hàm để kiểm tra độ dài:

~~~sql
SELECT LENGTH('Nguyễn Văn An')  AS char_length,
       LENGTHB('Nguyễn Văn An') AS byte_length
FROM dual;
~~~

- LENGTH trả số ký tự theo semantics của Oracle.
- LENGTHB trả số byte trong database character set.
- LENGTHC trả số Unicode complete characters.
- LENGTH2 và LENGTH4 đo theo UCS2/UCS4 code points tương ứng trong các trường hợp cần phân biệt Unicode supplementary characters.

Khi điều tra cột BYTE, LENGTHB là chỉ số cần so sánh. Với cột CHAR, LENGTH hoặc LENGTHC có thể hữu ích tùy yêu cầu về Unicode. Đừng suy luận từ số ký tự nhìn thấy trên màn hình hoặc từ String.length() của Java.

Kiểm tra character set của database:

~~~sql
SELECT parameter,
       value
FROM nls_database_parameters
WHERE parameter IN (
    'NLS_CHARACTERSET',
    'NLS_NCHAR_CHARACTERSET'
);
~~~

AL32UTF8 là character set Unicode thường gặp. Nếu database dùng character set khác, số byte của cùng một chuỗi có thể khác.

### 4.3. Kiểm tra định nghĩa cột

Dùng data dictionary để xem độ dài và semantics:

~~~sql
SELECT owner,
       table_name,
       column_name,
       data_type,
       data_length,
       char_length,
       char_used,
       nullable
FROM all_tab_columns
WHERE owner = 'APP'
  AND table_name = 'CONTACTS'
ORDER BY column_id;
~~~

Các cột đáng chú ý:

- DATA_LENGTH: giới hạn độ dài theo byte.
- CHAR_LENGTH: độ dài khai báo theo character semantics.
- CHAR_USED: B cho BYTE, C cho CHAR, có thể NULL với kiểu không áp dụng.
- NULLABLE: Y nếu cột cho phép NULL, N nếu không.

Tên bảng/column trong dictionary thường được lưu uppercase nếu không tạo bằng quoted identifier. Dùng owner đúng và kiểm tra quyền truy cập.

### 4.4. Xử lý ORA-12899

Có ba hướng:

1. Nếu giá trị nguồn sai, sửa nguồn hoặc reject bản ghi.
2. Nếu schema khai báo quá ngắn so với yêu cầu nghiệp vụ, tăng độ dài hoặc đổi sang CHAR semantics sau khi đánh giá tác động.
3. Nếu nghiệp vụ thực sự cần giới hạn, yêu cầu người dùng rút gọn hoặc dùng một trường khác để lưu phần nội dung dài.

Ví dụ tăng độ dài:

~~~sql
ALTER TABLE contacts
  MODIFY (full_name VARCHAR2(100 CHAR));
~~~

Không tự động dùng SUBSTR để cắt dữ liệu trước khi insert. Cắt chuỗi có thể làm mất tên, mã định danh, địa chỉ hoặc dữ liệu kiểm toán. Nếu nghiệp vụ cho phép rút gọn, cần quy định rõ cách cắt, thông báo cho người dùng và lưu dữ liệu gốc nếu cần.

## 5. Dữ liệu vượt miền nghiệp vụ và CHECK constraint

Một giá trị có thể vừa kiểu và độ dài nhưng vẫn không hợp lệ theo nghiệp vụ. Ví dụ:

- Số lượng phải lớn hơn 0.
- Tiền thanh toán không âm.
- Trạng thái chỉ thuộc tập giá trị xác định.
- Ngày kết thúc không trước ngày bắt đầu.
- Tỷ lệ phần trăm nằm trong khoảng 0 đến 100.

Dùng CHECK constraint để bảo vệ miền dữ liệu ở database:

~~~sql
CREATE TABLE promotions (
    promotion_id NUMBER(19) NOT NULL,
    discount_pct NUMBER(5, 2) NOT NULL,
    start_date   DATE NOT NULL,
    end_date     DATE NOT NULL,
    status       VARCHAR2(20 CHAR) NOT NULL,

    CONSTRAINT ck_promo_discount
        CHECK (discount_pct BETWEEN 0 AND 100),

    CONSTRAINT ck_promo_dates
        CHECK (end_date >= start_date),

    CONSTRAINT ck_promo_status
        CHECK (status IN ('DRAFT', 'ACTIVE', 'EXPIRED'))
);
~~~

Giá trị discount_pct bằng 150 không gây ORA-01438 nếu NUMBER(5,2) đủ rộng, nhưng vi phạm CHECK và gây ORA-02290. Điều này cho thấy giới hạn kiểu dữ liệu và giới hạn nghiệp vụ là hai lớp khác nhau.

### 5.1. CHECK và NULL

CHECK constraint không thay thế NOT NULL. Trong SQL, điều kiện CHECK chỉ từ chối khi biểu thức là FALSE; kết quả UNKNOWN do NULL có thể được chấp nhận.

Ví dụ:

~~~sql
CREATE TABLE products (
    product_id NUMBER NOT NULL,
    price      NUMBER CHECK (price >= 0)
);
~~~

price = -1 bị từ chối, nhưng price = NULL có thể được chấp nhận. Nếu price bắt buộc, khai báo:

~~~sql
price NUMBER NOT NULL CHECK (price >= 0)
~~~

### 5.2. Constraint và trigger

CHECK constraint phù hợp cho điều kiện trên cùng một dòng và biểu thức được Oracle hỗ trợ. Nếu quy tắc cần tra cứu bảng khác hoặc kiểm tra trạng thái phức tạp, cần cân nhắc foreign key, unique constraint, trigger hoặc logic nghiệp vụ trong transaction. Tránh dùng trigger thay cho constraint đơn giản vì trigger khó quan sát và có thể làm phát sinh lỗi ở thời điểm khác với câu lệnh gọi.

Không nên đặt CHECK constraint gọi user-defined function có kết quả thay đổi theo thời gian hoặc phụ thuộc dữ liệu bảng khác; điều đó có thể làm tính nhất quán khó bảo đảm.

## 6. Các lỗi dữ liệu liên quan cần phân biệt

| Mã lỗi | Ý nghĩa thường gặp | Hướng điều tra |
|---|---|---|
| ORA-01400 | NULL vào cột NOT NULL | Giá trị bind, default, trigger, nguồn dữ liệu |
| ORA-01438 | NUMBER vượt precision | DATA_PRECISION, DATA_SCALE, giá trị số |
| ORA-12899 | Chuỗi vượt độ dài cột | DATA_LENGTH, CHAR_LENGTH, CHAR_USED, LENGTHB |
| ORA-02290 | CHECK constraint bị vi phạm | Điều kiện CHECK và giá trị đầu vào |
| ORA-02291 | Không tìm thấy khóa cha cho foreign key | Parent key, thứ tự load dữ liệu |
| ORA-02292 | Không thể xóa/sửa parent vì còn child | Quan hệ tham chiếu và quy tắc xóa |
| ORA-00001 | Trùng unique/primary key | Key bị trùng, sequence, retry |
| ORA-01722 | Chuyển đổi chuỗi sang NUMBER không hợp lệ | Format, NLS, bind type, dữ liệu nguồn |
| ORA-01861 | Literal không khớp format date/time | Format mask và giá trị ngày |
| ORA-01843 | Tháng không hợp lệ | Format ngày và NLS_DATE_LANGUAGE |

Không nên xử lý mọi lỗi bằng cách mở rộng cột hoặc bỏ constraint. ORA-02291 là lỗi tham chiếu, không phải lỗi precision; ORA-01722 là lỗi chuyển đổi, không phải lỗi NUMBER column quá nhỏ.

### 6.1. Lỗi chuyển đổi số

Nếu ứng dụng truyền chuỗi vào cột NUMBER, Oracle có thể phải implicit convert. Chuỗi như '12,50' phụ thuộc NLS_NUMERIC_CHARACTERS; chuỗi không phải số hợp lệ có thể gây ORA-01722.

Nên bind giá trị kiểu NUMBER từ ứng dụng thay vì ghép chuỗi SQL. Nếu buộc phải parse text trong SQL, dùng format model và NLS parameter rõ ràng:

~~~sql
SELECT TO_NUMBER(
         :amount_text,
         '999999D99',
         'NLS_NUMERIC_CHARACTERS=''.,'''
       )
FROM dual;
~~~

Cách này chỉ đúng khi định dạng đầu vào khớp mask đã quy định. Với dữ liệu có nhiều format nguồn, hãy chuẩn hóa ở bước staging và reject giá trị không parse được.

### 6.2. Lỗi chuyển đổi ngày

Không dựa vào định dạng ngày mặc định của session. Dùng bind kiểu DATE/TIMESTAMP từ JDBC; nếu nhận chuỗi, parse bằng format mask tường minh:

~~~sql
INSERT INTO events (event_id, event_date)
VALUES (
    :event_id,
    TO_DATE(:date_text, 'YYYY-MM-DD')
);
~~~

Nếu dữ liệu có timezone hoặc phần giờ, cân nhắc TIMESTAMP WITH TIME ZONE và API JDBC tương ứng. Không dùng chuỗi ngày phụ thuộc NLS_DATE_FORMAT trong migration hoặc ETL.

## 7. Quy trình chẩn đoán lỗi theo từng bước

Khi gặp lỗi ở ứng dụng, SQL script hoặc job import, thu thập đầy đủ câu lệnh, bind values, error stack và transaction context trước khi sửa.

### Bước 1: đọc chính xác error message

Ghi nhận:

- Mã ORA.
- Owner, table và column được nêu trong message.
- Câu SQL hoặc procedure đang chạy.
- Giá trị bind và kiểu bind.
- Thời điểm lỗi xảy ra: execute, flush, commit hay batch.
- Có trigger, view hoặc procedure trung gian hay không.

Nếu dùng Hibernate, lỗi có thể xuất hiện ở flush hoặc lúc transaction commit chứ không phải đúng dòng persist. Đặt log SQL và bind parameter trong môi trường kiểm thử để tìm câu DML thực tế.

### Bước 2: đọc định nghĩa cột

Ví dụ kiểm tra bảng CONTACTS:

~~~sql
SELECT owner,
       table_name,
       column_name,
       data_type,
       data_length,
       char_length,
       char_used,
       data_precision,
       data_scale,
       nullable,
       data_default
FROM all_tab_columns
WHERE owner = 'APP'
  AND table_name = 'CONTACTS'
ORDER BY column_id;
~~~

Với NUMBER, xem DATA_PRECISION và DATA_SCALE. Với VARCHAR2/CHAR, xem DATA_LENGTH, CHAR_LENGTH và CHAR_USED. Với cột bắt buộc, xem NULLABLE. DATA_DEFAULT có thể được hiển thị như kiểu dữ liệu dictionary đặc biệt theo phiên bản; khi truy vấn cần xử lý giới hạn kiểu cột của view.

### Bước 3: kiểm tra constraint

~~~sql
SELECT c.owner,
       c.table_name,
       c.constraint_name,
       c.constraint_type,
       c.status,
       c.validated,
       cc.column_name,
       c.search_condition
FROM all_constraints c
LEFT JOIN all_cons_columns cc
  ON cc.owner = c.owner
 AND cc.constraint_name = c.constraint_name
 AND cc.table_name = c.table_name
WHERE c.owner = 'APP'
  AND c.table_name = 'CONTACTS'
ORDER BY c.constraint_name, cc.position;
~~~

Với CHECK constraint, xem SEARCH_CONDITION hoặc SEARCH_CONDITION_VC tùy phiên bản và view. Nếu dictionary không hiển thị đầy đủ điều kiện do kiểu LONG, dùng DBMS_METADATA hoặc công cụ DDL extraction để lấy định nghĩa.

### Bước 4: kiểm tra trigger và object trung gian

~~~sql
SELECT owner,
       trigger_name,
       triggering_event,
       trigger_type,
       status
FROM all_triggers
WHERE table_owner = 'APP'
  AND table_name = 'CONTACTS'
ORDER BY trigger_name;
~~~

Nếu DML chạy qua view, package hoặc procedure, kiểm tra trigger INSTEAD OF, logic gán biến và các câu INSERT/UPDATE nội bộ. Một cột có thể nhận giá trị khác với giá trị ứng dụng gửi do trigger hoặc biểu thức chuyển đổi.

### Bước 5: kiểm tra dữ liệu nguồn

Đối với ORA-12899, kiểm tra cả ký tự và byte:

~~~sql
SELECT customer_id,
       full_name,
       LENGTH(full_name)  AS char_length,
       LENGTHB(full_name) AS byte_length
FROM app.customer_import_stage
WHERE LENGTHB(full_name) > 20;
~~~

Ví dụ trên dùng 20 byte chỉ khi đích thực sự là VARCHAR2(20 BYTE). Nếu đích là CHAR semantics, so sánh theo số ký tự và xác nhận quy tắc Unicode phù hợp.

Đối với ORA-01438, kiểm tra giá trị lớn nhất và số chữ số:

~~~sql
SELECT MAX(ABS(amount)) AS max_abs_amount,
       MAX(LENGTH(TO_CHAR(ABS(amount)))) AS max_rendered_length
FROM app.invoice_stage;
~~~

Độ dài TO_CHAR phụ thuộc format và NLS nên chỉ dùng để xem sơ bộ; cách chính xác là kiểm tra từng giá trị với precision/scale đích và quy tắc làm tròn nghiệp vụ.

Đối với ORA-01400:

~~~sql
SELECT COUNT(*) AS missing_customer_name
FROM app.customer_import_stage
WHERE customer_name IS NULL;
~~~

Nếu chuỗi rỗng đã được Oracle chuẩn hóa thành NULL khi lưu trong VARCHAR2, truy vấn IS NULL cũng phát hiện trường hợp đó. Nếu dữ liệu còn nằm ngoài database, cần kiểm tra file/API nguồn trước khi load.

### Bước 6: tái hiện với một bản ghi

Dùng một bản ghi đại diện trong môi trường test để xác nhận nguyên nhân. Không lặp lại thử nghiệm trực tiếp trên production nếu có thể tạo dữ liệu ngoài ý muốn. Kiểm tra cả trường hợp biên hợp lệ và trường hợp biên không hợp lệ.

### Bước 7: chọn cách khắc phục và xác minh

Sau khi xác định nguyên nhân, sửa ở nguồn dữ liệu, mapping, logic PL/SQL hoặc DDL. Chạy lại test có kiểm soát, xác nhận số bản ghi hợp lệ/reject và kiểm tra constraint vẫn bảo vệ đúng miền dữ liệu.

## 8. Kiểm soát dữ liệu ở tầng ứng dụng Java/JDBC

Database là lớp bảo vệ cuối cùng, nhưng ứng dụng nên kiểm tra dữ liệu sớm để trả thông báo dễ hiểu. Không nên đợi ORA-01400 hoặc ORA-12899 rồi trả nguyên stack trace cho người dùng cuối.

### 8.1. NUMBER và BigDecimal

Dùng BigDecimal cho tiền, tỷ lệ hoặc NUMBER cần độ chính xác thập phân. Tránh dùng double để biểu diễn tiền vì binary floating point có thể tạo sai số biểu diễn.

Ví dụ kiểm tra amount cho NUMBER(12,2):

~~~java
public static BigDecimal validateAmount(BigDecimal value) {
    if (value == null) {
        throw new IllegalArgumentException("Amount is required");
    }

    BigDecimal normalized = value.setScale(
        2,
        RoundingMode.UNNECESSARY
    );

    BigDecimal max = new BigDecimal("9999999999.99");

    if (normalized.signum() < 0 || normalized.compareTo(max) > 0) {
        throw new IllegalArgumentException("Amount is outside the allowed range");
    }

    return normalized;
}
~~~

RoundingMode.UNNECESSARY từ chối nếu cần làm tròn để có đúng 2 chữ số thập phân. Nếu nghiệp vụ cho phép làm tròn, chọn một rounding mode được quy định rõ, ví dụ HALF_UP hoặc HALF_EVEN, rồi kiểm tra miền sau khi làm tròn. Không để mỗi tầng ứng dụng và database tự làm tròn theo quy tắc không được thống nhất.

Bind bằng BigDecimal:

~~~java
preparedStatement.setBigDecimal(1, amount);
~~~

Nếu giá trị NULL được phép:

~~~java
preparedStatement.setNull(1, Types.NUMERIC);
~~~

Nếu không được phép, validate trước khi gọi JDBC và vẫn giữ NOT NULL trong schema.

### 8.2. VARCHAR2 và Unicode

Với cột VARCHAR2(20 CHAR), kiểm tra số ký tự theo quy tắc Unicode mà ứng dụng chọn. Với VARCHAR2(20 BYTE), cần kiểm tra byte theo database character set.

Java String.length() đếm UTF-16 code units, không phải số byte trong Oracle database character set và cũng không luôn bằng số Unicode code point. Ví dụ một ký tự ngoài BMP có thể chiếm hai code unit trong Java.

Nếu database character set là AL32UTF8 và cột dùng BYTE semantics, có thể kiểm tra sơ bộ số byte UTF-8:

~~~java
int utf8Bytes = value.getBytes(StandardCharsets.UTF_8).length;
~~~

Chỉ dùng phép đo này khi database character set thực sự tương thích UTF-8 như AL32UTF8. Nếu database dùng character set khác, số byte có thể khác. Kiểm tra cuối cùng ở Oracle bằng LENGTHB là cách chắc chắn hơn.

Với CHAR semantics, có thể đếm code point:

~~~java
int codePoints = value.codePointCount(0, value.length());
~~~

Tuy nhiên, cách đếm này vẫn có thể khác khái niệm grapheme cluster mà người dùng nhìn thấy, ví dụ một ký tự hiển thị được tạo bởi chữ cái và dấu kết hợp. Hãy thống nhất quy tắc giới hạn với nghiệp vụ và kiểm tra ở database.

JDBC bind chuỗi bằng setString:

~~~java
preparedStatement.setString(1, fullName);
~~~

Với cột NVARCHAR2/NCHAR, dùng API bind national character set phù hợp như setNString khi driver hỗ trợ. Không dựa vào implicit conversion giữa VARCHAR2 và NVARCHAR2 mà chưa kiểm tra character set.

### 8.3. Bean Validation không thay thế database constraint

Có thể dùng Bean Validation để trả lỗi sớm:

~~~java
public record CustomerRequest(
    @NotNull
    Long customerId,

    @NotBlank
    @Size(max = 100)
    String customerName,

    @DecimalMin("0.00")
    @Digits(integer = 10, fraction = 2)
    BigDecimal creditLimit
) {}
~~~

Các annotation như @Size và @Digits giúp kiểm tra ở tầng Java nhưng không thay thế schema constraint. @Size trên String thường dựa trên độ dài CharSequence trong Java, không kiểm tra số byte theo BYTE semantics. @Digits kiểm tra precision/scale theo quy tắc Bean Validation; cần đồng bộ với NUMBER(p,s) thực tế.

Database constraint vẫn cần thiết vì dữ liệu có thể đến từ batch job, script DBA, integration service hoặc ứng dụng khác.

## 9. Xử lý lỗi trong JDBC và batch insert

Lỗi có thể xuất hiện khi gọi executeUpdate, executeBatch, flush hoặc commit. Hãy giữ nguyên vendor error code và message để log phục vụ điều tra, đồng thời trả thông báo nghiệp vụ đã được chuẩn hóa cho client.

Ví dụ:

~~~java
try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO customers(customer_id, customer_name) VALUES (?, ?)")) {

    ps.setLong(1, customerId);
    ps.setString(2, customerName);

    ps.executeUpdate();
} catch (SQLException e) {
    log.error(
        "Insert customer failed. SQLState={}, vendorCode={}, message={}",
        e.getSQLState(),
        e.getErrorCode(),
        e.getMessage(),
        e
    );
    throw e;
}
~~~

Không ghi password, token hoặc dữ liệu cá nhân nhạy cảm vào log. Với dữ liệu nghiệp vụ, chỉ log khóa tham chiếu và thông tin đủ để điều tra theo chính sách bảo mật.

### 9.1. BatchUpdateException

Khi batch có một số bản ghi lỗi, driver có thể ném BatchUpdateException. getUpdateCounts() cho biết trạng thái thực thi các lệnh trước hoặc trong batch theo hành vi driver; không giả định tất cả lệnh sau lỗi đều đã chạy hoặc chưa chạy nếu chưa đọc tài liệu driver.

~~~java
try {
    ps.executeBatch();
} catch (BatchUpdateException e) {
    int[] counts = e.getUpdateCounts();

    log.error(
        "Batch failed; processed statement count={}, vendorCode={}",
        counts.length,
        e.getErrorCode()
    );

    connection.rollback();
    throw e;
}
~~~

Nếu cần giữ lại bản ghi hợp lệ và tách bản ghi lỗi, hãy thiết kế cơ chế reject riêng. Đừng commit một phần chỉ vì driver trả update count dương; transaction semantics và batch behavior phải được kiểm tra theo driver, auto-commit và cấu hình database.

### 9.2. Transaction và rollback

Nếu nhiều DML phải thành công cùng nhau, đặt autoCommit=false và rollback khi một thao tác vi phạm constraint:

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        insertCustomer(connection, customer);
        insertOrders(connection, orders);
        connection.commit();
    } catch (SQLException e) {
        connection.rollback();
        throw e;
    }
}
~~~

Với Oracle, DDL thường implicit commit. Không trộn DDL và DML vào transaction ứng dụng rồi kỳ vọng rollback khôi phục cả hai. Với JPA/Hibernate, lỗi constraint có thể được ném lúc flush hoặc commit; cần rollback transaction và không tiếp tục dùng persistence context đã ở trạng thái lỗi.

## 10. Kiểm tra dữ liệu trước khi load hàng loạt

Khi import từ CSV, Excel, external system hoặc staging table, nên tách bước tiếp nhận và bước đưa vào bảng nghiệp vụ.

Luồng xử lý:

~~~text
File / API / External source
            |
            v
     Staging table
            |
            v
  Validate type, null, length,
  precision, scale, domain
        /         \
       /           \
      v             v
 Valid rows      Reject rows
      |             |
      v             v
 Target tables   Error detail,
                 source row,
                 reason
~~~

Staging table nên giữ dữ liệu nguồn đủ để điều tra, có thể lưu giá trị dưới dạng VARCHAR2/CLOB cho bước parse ban đầu tùy thiết kế. Sau khi validate, chuyển dữ liệu hợp lệ sang kiểu đích bằng conversion tường minh.

### 10.1. Tách bản ghi lỗi bằng SQL

Ví dụ kiểm tra chuỗi tên vượt 100 ký tự:

~~~sql
SELECT source_row_id,
       customer_name,
       LENGTH(customer_name) AS char_length
FROM customer_stage
WHERE customer_name IS NULL
   OR LENGTH(customer_name) > 100;
~~~

Nếu cột đích dùng BYTE semantics, kiểm tra LENGTHB thay cho LENGTH và dùng đúng character set.

Ví dụ kiểm tra số tiền:

~~~sql
SELECT source_row_id,
       amount_text
FROM payment_stage
WHERE amount_text IS NULL
   OR VALIDATE_CONVERSION(
        amount_text AS NUMBER,
        '9999999999D99',
        'NLS_NUMERIC_CHARACTERS=''.,'''
      ) = 0;
~~~

VALIDATE_CONVERSION có sẵn trên các phiên bản Oracle hỗ trợ; xác nhận phiên bản database trước khi dùng. Sau khi parse, kiểm tra range và scale theo miền cột đích.

### 10.2. Dùng DML error logging

Oracle hỗ trợ cơ chế DML error logging cho một số thao tác INSERT/UPDATE/MERGE để ghi lỗi từng dòng vào error table thay vì dừng toàn bộ statement ngay ở lỗi đầu tiên.

Tạo error table:

~~~sql
BEGIN
  DBMS_ERRLOG.CREATE_ERROR_LOG(
    dml_table_name => 'CUSTOMERS',
    err_log_table_name => 'ERR$_CUSTOMERS'
  );
END;
/
~~~

Thực hiện insert:

~~~sql
INSERT INTO customers (
    customer_id,
    customer_name
)
SELECT customer_id,
       customer_name
FROM customer_stage
LOG ERRORS INTO err$_customers ('CUSTOMER_LOAD')
REJECT LIMIT UNLIMITED;
~~~

Error table lưu thông tin lỗi và dữ liệu dòng theo giới hạn hỗ trợ của DBMS_ERRLOG. Một số kiểu dữ liệu/đối tượng và thao tác không được hỗ trợ hoặc có hạn chế; kiểm tra tài liệu Oracle đúng phiên bản. DML error logging không thay thế kiểm tra nghiệp vụ, và không phải mọi lỗi statement đều có thể được ghi thành lỗi từng dòng.

Sau load, đối chiếu số dòng nguồn, số dòng insert thành công và số dòng trong error table. Cần có quy trình xử lý reject, sửa nguồn và chạy lại có kiểm soát.

## 11. Sửa schema khi giới hạn cột không còn phù hợp

Nếu lỗi phản ánh schema quá hẹp so với yêu cầu nghiệp vụ đã thay đổi, cần tạo migration để mở rộng cột. Trước khi sửa, kiểm tra mọi consumer của schema và tương thích ngược.

### 11.1. Tăng độ dài chuỗi

~~~sql
ALTER TABLE customers
  MODIFY (customer_name VARCHAR2(200 CHAR));
~~~

Đổi từ BYTE sang CHAR có thể thay đổi semantics và giới hạn byte. Cần kiểm tra phiên bản Oracle, MAX_STRING_SIZE, character set, index key length, view, package và ứng dụng.

### 11.2. Tăng precision NUMBER

~~~sql
ALTER TABLE invoices
  MODIFY (amount NUMBER(14, 2));
~~~

Kiểm tra dữ liệu hiện có, check constraint, function-based index, view và code mapping. Nếu cột được dùng trong tính toán, cân nhắc precision của biểu thức trung gian và OUT parameter.

### 11.3. Bổ sung NOT NULL an toàn

Nếu cột hiện cho phép NULL nhưng nghiệp vụ yêu cầu bắt buộc, không nên thêm NOT NULL ngay khi bảng đang có dữ liệu NULL.

Trước tiên tìm dữ liệu:

~~~sql
SELECT COUNT(*)
FROM customers
WHERE customer_name IS NULL;
~~~

Xác định giá trị cần backfill dựa trên nguồn đáng tin cậy. Sau khi backfill và xác minh:

~~~sql
ALTER TABLE customers
  MODIFY (customer_name NOT NULL);
~~~

Nếu không thể khôi phục giá trị, phải quyết định rõ bản ghi nào cần reject, sửa thủ công hoặc giữ nullable theo nghiệp vụ. Không dùng chuỗi giả để làm sạch constraint nếu ứng dụng coi đó là tên thật.

### 11.4. Thay đổi schema qua migration

Mọi thay đổi nên được ghi thành migration versioned, review và test trước khi production. Với Oracle, DDL thường implicit commit nên migration phải có cách tiếp tục sau partial failure. Khi rolling deployment, dùng expand-and-contract để code cũ và mới cùng hoạt động trong giai đoạn chuyển tiếp.

## 12. Trường hợp lỗi phát sinh từ ORM hoặc PL/SQL

### Hibernate/JPA

Với JPA, giá trị có thể không được ghi ngay tại lệnh save. Hibernate thường trì hoãn SQL đến flush. Vì vậy, lỗi ORA-01400, ORA-01438 hoặc ORA-12899 có thể xuất hiện tại:

- entityManager.flush()
- repository.flush()
- trước một query cần đồng bộ persistence context
- transaction commit

Để xác định bản ghi gây lỗi, bật SQL log và bind logging trong môi trường test, giảm kích thước batch hoặc chia chunk để khoanh vùng. Khi dùng batch, một lỗi có thể làm cả transaction rollback tùy cấu hình và driver.

Mapping phải tương thích schema:

~~~java
@Column(name = "CUSTOMER_NAME", nullable = false, length = 100)
private String customerName;

@Column(name = "AMOUNT", precision = 12, scale = 2)
private BigDecimal amount;
~~~

Các thuộc tính length, precision và scale mô tả mapping/DDL generation. Nếu migration tool là source of truth, mapping cần khớp schema nhưng không nên dùng Hibernate ddl-auto=update để tự sửa production.

### PL/SQL procedure

Procedure có thể gán giá trị vào biến hoặc cột với kiểu khác. Lỗi có thể xảy ra ở câu INSERT/UPDATE bên trong procedure chứ không phải bind của caller.

Giữ lại stack trace bằng:

~~~sql
EXCEPTION
  WHEN OTHERS THEN
    DBMS_OUTPUT.PUT_LINE(SQLERRM);
    DBMS_OUTPUT.PUT_LINE(DBMS_UTILITY.FORMAT_ERROR_BACKTRACE);
    RAISE;
END;
~~~

Trong production, nên ghi lỗi vào logging/audit phù hợp thay vì chỉ dùng DBMS_OUTPUT. Quan trọng là RAISE lại lỗi nếu caller cần biết transaction thất bại; không bắt rồi bỏ qua exception.

## 13. Các ví dụ chẩn đoán tổng hợp

### ORA-01400

Giả sử error message báo không thể insert NULL vào APP.CUSTOMERS.CUSTOMER_NAME.

Kiểm tra:

~~~sql
SELECT column_name,
       nullable,
       data_default,
       data_type,
       data_length
FROM all_tab_columns
WHERE owner = 'APP'
  AND table_name = 'CUSTOMERS'
  AND column_name = 'CUSTOMER_NAME';
~~~

Sau đó kiểm tra câu INSERT, bind value, trigger và dữ liệu nguồn. Nếu tên khách hàng là bắt buộc, sửa producer/import để gửi tên hợp lệ. Nếu nghiệp vụ cho phép chưa biết tên, cân nhắc thay đổi constraint và tất cả consumer phụ thuộc.

### ORA-01438

Giả sử error message chỉ ra APP.INVOICES.AMOUNT.

Kiểm tra:

~~~sql
SELECT data_type,
       data_precision,
       data_scale
FROM all_tab_columns
WHERE owner = 'APP'
  AND table_name = 'INVOICES'
  AND column_name = 'AMOUNT';
~~~

Nếu là NUMBER(5,2), kiểm tra giá trị lớn hơn 999.99 hoặc kết quả sau làm tròn. Nếu giá trị hợp lệ về nghiệp vụ, tạo migration tăng precision; nếu không hợp lệ, reject hoặc sửa dữ liệu nguồn.

### ORA-12899

Giả sử error message báo APP.CONTACTS.FULL_NAME, actual length 28, maximum 20.

Kiểm tra:

~~~sql
SELECT data_length,
       char_length,
       char_used
FROM all_tab_columns
WHERE owner = 'APP'
  AND table_name = 'CONTACTS'
  AND column_name = 'FULL_NAME';
~~~

Đo dữ liệu nguồn bằng LENGTH và LENGTHB. Nếu cột là BYTE semantics, actual length có thể vượt do ký tự đa byte. Nếu nghiệp vụ cho phép 20 ký tự, cân nhắc CHAR semantics hoặc tăng giới hạn; nếu không, reject giá trị quá dài với thông báo rõ ràng.

### ORA-02290

Giả sử constraint CK_PROMO_DISCOUNT báo lỗi:

~~~sql
SELECT constraint_name,
       search_condition
FROM all_constraints
WHERE owner = 'APP'
  AND table_name = 'PROMOTIONS'
  AND constraint_type = 'C';
~~~

Xem điều kiện và giá trị đầu vào. Nếu discount_pct phải từ 0 đến 100, giá trị 150 là lỗi nghiệp vụ dù NUMBER(5,2) có thể lưu được. Không tăng precision để “sửa” lỗi này.

## 14. Thiết kế thông báo lỗi cho người dùng

Không nên trả toàn bộ ORA error hoặc tên bảng nội bộ cho người dùng cuối. Có thể ánh xạ lỗi kỹ thuật sang lỗi validation:

| Lỗi database | Thông báo nghiệp vụ gợi ý |
|---|---|
| ORA-01400 | Trường bắt buộc chưa được cung cấp |
| ORA-01438 | Giá trị số vượt phạm vi cho phép |
| ORA-12899 | Nội dung trường vượt độ dài tối đa |
| ORA-02290 | Giá trị không thỏa điều kiện nghiệp vụ |
| ORA-02291 | Bản ghi tham chiếu không tồn tại |
| ORA-00001 | Giá trị đã tồn tại hoặc bị trùng |

Ở tầng service, validate trước để thông báo field cụ thể. Nếu database vẫn từ chối, ghi vendor error code và correlation/request ID vào log, trả lỗi chung có thể hành động được. Không tiết lộ SQL, schema name, dữ liệu nhạy cảm hoặc stack trace cho client.

## 15. Nguyên tắc xử lý an toàn

- Đọc chính xác ORA code và owner/table/column trước khi sửa.
- Kiểm tra định nghĩa thực tế trong data dictionary, không dựa vào entity hoặc tài liệu cũ.
- Phân biệt NULL, chuỗi rỗng và chuỗi chỉ có dấu cách.
- Phân biệt precision với scale; kiểm tra cả giá trị trước và sau quy tắc làm tròn.
- Với ORA-12899, kiểm tra BYTE/CHAR semantics và database character set; dùng LENGTHB khi cần.
- Dùng BigDecimal cho Oracle NUMBER cần độ chính xác và bind đúng kiểu JDBC.
- Dùng format mask/NLS tường minh khi buộc phải chuyển chuỗi thành số hoặc ngày.
- Dùng NOT NULL, CHECK, UNIQUE và FOREIGN KEY để bảo vệ dữ liệu ở database.
- Không âm thầm cắt chuỗi, thay NULL bằng giá trị giả hoặc làm tròn số ngoài quy tắc nghiệp vụ.
- Với import lớn, staging và reject table giúp giữ lại dữ liệu lỗi để điều tra.
- Khi sửa schema, tạo migration có version, kiểm thử và đánh giá mọi ứng dụng phụ thuộc.
- Với Oracle DDL, chuẩn bị cho implicit commit và partial failure.
- Ghi log đủ thông tin kỹ thuật nhưng không để lộ dữ liệu nhạy cảm.
- Sau khi sửa, xác minh số dòng thành công, số dòng reject, constraint và dữ liệu biên.

ORA-01400, ORA-01438 và ORA-12899 đều cho biết dữ liệu không phù hợp với định nghĩa cột, nhưng mỗi lỗi phản ánh một giới hạn khác nhau: tính bắt buộc, precision số hoặc độ dài ký tự. Kết hợp kiểm tra schema, dữ liệu nguồn, quy tắc nghiệp vụ và kiểu bind ở ứng dụng sẽ giúp tìm đúng nguyên nhân, giữ nguyên ý nghĩa dữ liệu và ngăn lỗi lặp lại trong các lần ghi tiếp theo.
