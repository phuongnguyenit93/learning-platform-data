# CASE dạng đơn giản và CASE theo điều kiện

Trong nhiều truy vấn SQL, giá trị cần hiển thị hoặc tính toán phụ thuộc vào một quy tắc: đơn hàng có trạng thái `NEW` được hiển thị là “Mới”, đơn có giá trị từ 500 trở lên được xếp vào nhóm “Lớn”, còn những đơn chưa có số tiền cần được ghi nhận riêng. Để biểu diễn những lựa chọn như vậy **ngay trong một biểu thức SQL**, ta dùng `CASE`.

SQL có **hai cách viết CASE**:

1. **`CASE` dạng đơn giản** (*simple CASE*): so sánh **một biểu thức** với từng giá trị `WHEN`.
2. **`CASE` theo điều kiện** (*searched CASE*): kiểm tra **nhiều điều kiện Boolean** có thể dùng phép so sánh, `AND`, `OR`, `IS NULL`, khoảng giá trị và nhiều cột.

Cả hai đều trả về **một giá trị** cho mỗi hàng hoặc mỗi lần đánh giá biểu thức. Chúng không tự tạo câu lệnh điều khiển luồng kiểu `IF/ELSE` trong ứng dụng; SQL tiếp tục xử lý tập dữ liệu theo ngữ nghĩa truy vấn.

Bài học thuộc **Database SQL → Rẽ nhánh trong SQL**, dùng PostgreSQL làm môi trường thực hành. Cú pháp `CASE` cốt lõi là một phần của SQL phổ biến và được nhiều hệ quản trị hỗ trợ, nhưng chi tiết kiểu dữ liệu và một số hàm đi kèm có thể khác nhau.

## 1. Cú pháp tổng quát và cách đọc

### 1.1. CASE dạng đơn giản (simple CASE)

~~~sql
CASE bieu_thuc
    WHEN gia_tri_1 THEN ket_qua_1
    WHEN gia_tri_2 THEN ket_qua_2
    ...
    ELSE ket_qua_mac_dinh
END
~~~

Đầu tiên, SQL đánh giá `bieu_thuc`. Sau đó lần lượt so sánh giá trị ấy với `gia_tri_1`, `gia_tri_2`, ... bằng ngữ nghĩa phép so sánh bằng tương ứng. Nhánh đầu tiên khớp được chọn; giá trị đứng sau `THEN` của nhánh đó trở thành kết quả.

Ví dụ một biểu thức đầy đủ:

~~~sql
CASE order_status
    WHEN 'NEW' THEN 'Moi'
    WHEN 'PAID' THEN 'Da thanh toan'
    ELSE 'Khac'
END
~~~

Nếu `order_status = 'NEW'`, kết quả là `'Moi'`; nếu `order_status = 'PAID'` thì là `'Da thanh toan'`; các trường hợp khác dùng `ELSE`.

### 1.2. CASE theo điều kiện (searched CASE)

~~~sql
CASE
    WHEN dieu_kien_1 THEN ket_qua_1
    WHEN dieu_kien_2 THEN ket_qua_2
    ...
    ELSE ket_qua_mac_dinh
END
~~~

Ở dạng này, mỗi `WHEN` chứa **một điều kiện độc lập**. SQL chọn kết quả ở `THEN` của **điều kiện đầu tiên có giá trị TRUE**.

Ví dụ:

~~~sql
CASE
    WHEN amount IS NULL THEN 'Chua co so tien'
    WHEN amount >= 500 THEN 'Lon'
    WHEN amount >= 100 THEN 'Vua'
    ELSE 'Nho'
END
~~~

Dạng theo điều kiện phù hợp khi cần xét **ngưỡng**, **khoảng**, **nhiều cột**, **NULL** hoặc các quy tắc phối hợp.

### 1.3. Những thành phần chung

| Thành phần | Vai trò |
| --- | --- |
| `CASE` | Bắt đầu biểu thức lựa chọn |
| `WHEN` | Giá trị cần so sánh (dạng đơn giản) hoặc điều kiện Boolean (dạng theo điều kiện) |
| `THEN` | Giá trị trả về nếu nhánh tương ứng được chọn |
| `ELSE` | Giá trị trả về khi không có nhánh nào phù hợp; có thể bỏ |
| `END` | Kết thúc **biểu thức CASE**, bắt buộc |
| `AS alias` | Đặt tên cho cột kết quả khi sử dụng `CASE` trong `SELECT` |

Nếu không viết `ELSE` và không có `WHEN` nào phù hợp, biểu thức `CASE` trả về **`NULL`**. `END` kết thúc biểu thức, còn dấu chấm phẩy `;` thường kết thúc **toàn bộ câu SQL**; không cần thêm dấu `;` sau từng `THEN`.

## 2. Tạo dữ liệu mẫu để thử cả hai dạng CASE

Sử dụng database **PostgreSQL thực hành**, với quyền tạo bảng. Chạy đoạn sau **một lần** trong database chưa có bảng `lab_case_orders_151`:

~~~sql
CREATE TABLE lab_case_orders_151 (
    order_id INTEGER PRIMARY KEY,
    customer_name VARCHAR(80) NOT NULL,
    order_status VARCHAR(12)
        CHECK (order_status IN ('NEW', 'PAID', 'SHIPPED', 'CANCELLED')),
    amount NUMERIC(12, 2) CHECK (amount >= 0),
    due_on DATE
);

INSERT INTO lab_case_orders_151
    (order_id, customer_name, order_status, amount, due_on)
VALUES
    (101, 'An',   'NEW',       120.00, DATE '2026-11-20'),
    (102, 'Binh', 'PAID',      450.00, DATE '2026-11-12'),
    (103, 'Chi',  'CANCELLED',   0.00, DATE '2026-11-05'),
    (104, 'Dung', 'SHIPPED',   950.00, DATE '2026-11-09'),
    (105, 'Ha',   'NEW',        80.00, DATE '2026-11-11'),
    (106, 'Lan',  NULL,        300.00, DATE '2026-11-10'),
    (107, 'Minh', 'PAID',       NULL,  DATE '2026-11-13'),
    (108, 'Nga',  'NEW',      1000.00, NULL);
~~~

Xem dữ liệu ở thứ tự ID rõ ràng:

~~~sql
SELECT order_id, customer_name, order_status, amount, due_on
FROM lab_case_orders_151
ORDER BY order_id;
~~~

| order_id | customer_name | order_status | amount | due_on |
| ---: | --- | --- | ---: | --- |
| 101 | An | NEW | 120.00 | 2026-11-20 |
| 102 | Binh | PAID | 450.00 | 2026-11-12 |
| 103 | Chi | CANCELLED | 0.00 | 2026-11-05 |
| 104 | Dung | SHIPPED | 950.00 | 2026-11-09 |
| 105 | Ha | NEW | 80.00 | 2026-11-11 |
| 106 | Lan | `NULL` | 300.00 | 2026-11-10 |
| 107 | Minh | PAID | `NULL` | 2026-11-13 |
| 108 | Nga | NEW | 1000.00 | `NULL` |

Từ bảng này có thể thấy:

- Một cột trạng thái có nhiều **giá trị cố định** phù hợp với `CASE` dạng đơn giản.
- Một cột tiền có **nhiều ngưỡng** và có thể `NULL`, phù hợp với `CASE` theo điều kiện.
- Ngày đến hạn, trạng thái và số tiền có thể kết hợp để đưa ra kết luận theo **nhiều cột**.
- Dòng 106 có trạng thái `NULL`, dòng 107 có số tiền `NULL` và dòng 108 có ngày đến hạn `NULL`, giúp nhận diện tác động của logic ba giá trị.

Các ví dụ bên dưới giả định chưa chỉnh sửa dữ liệu mẫu. Trong truy vấn hiển thị kết quả, ta dùng `ORDER BY order_id` khi muốn giữ thứ tự xác định.

## 3. CASE dạng đơn giản: ánh xạ mã sang nhãn hiển thị

Đây là trường hợp điển hình: một cột chứa **mã trạng thái** và ta muốn đổi sang nhãn dễ đọc.

~~~sql
SELECT
    order_id,
    customer_name,
    order_status,
    CASE order_status
        WHEN 'NEW' THEN 'Moi tao'
        WHEN 'PAID' THEN 'Da thanh toan'
        WHEN 'SHIPPED' THEN 'Da giao'
        WHEN 'CANCELLED' THEN 'Da huy'
        ELSE 'Chua xac dinh'
    END AS status_label
FROM lab_case_orders_151
ORDER BY order_id;
~~~

Kết quả:

| order_id | order_status | status_label |
| ---: | --- | --- |
| 101 | NEW | Moi tao |
| 102 | PAID | Da thanh toan |
| 103 | CANCELLED | Da huy |
| 104 | SHIPPED | Da giao |
| 105 | NEW | Moi tao |
| 106 | `NULL` | Chua xac dinh |
| 107 | PAID | Da thanh toan |
| 108 | NEW | Moi tao |

Diễn giải:

1. `CASE order_status` xác định biểu thức sẽ được so sánh với các giá trị `WHEN`.
2. Mỗi `WHEN '...' THEN '...'` ánh xạ **một giá trị** sang **một kết quả**.
3. `ELSE 'Chua xac dinh'` là nhánh dự phòng; trong dữ liệu mẫu, dòng có `order_status IS NULL` đi vào nhánh này.
4. `END AS status_label` đóng `CASE` và đặt tên cho cột kết quả. Nó **không đổi** tên hoặc dữ liệu của cột `order_status` trong bảng.

`CASE` trong `SELECT` chỉ tạo ra **giá trị được trả về** khi truy vấn; lần chạy này không cập nhật các giá trị gốc.

### 3.1. Có thể viết cùng ý tưởng bằng CASE theo điều kiện

~~~sql
SELECT
    order_id,
    CASE
        WHEN order_status = 'NEW' THEN 'Moi tao'
        WHEN order_status = 'PAID' THEN 'Da thanh toan'
        WHEN order_status = 'SHIPPED' THEN 'Da giao'
        WHEN order_status = 'CANCELLED' THEN 'Da huy'
        ELSE 'Chua xac dinh'
    END AS status_label
FROM lab_case_orders_151
ORDER BY order_id;
~~~

Với dữ liệu và ngữ nghĩa so sánh trên PostgreSQL, kết quả giống ví dụ `CASE order_status WHEN ...`. Điểm khác nằm ở cách biểu diễn:

- Dạng đơn giản viết biểu thức `order_status` **một lần** rồi liệt kê giá trị khớp.
- Dạng theo điều kiện viết **đầy đủ phép so sánh** trong từng `WHEN` và có thể mở rộng bằng `AND`, `OR`, `IS NULL`, `>=`, v.v.

Khi tất cả nhánh chỉ là “một cột bằng một trong vài mã cố định”, `CASE` đơn giản thường dễ đọc hơn. Khi các nhánh có quy tắc khác nhau, dạng theo điều kiện rõ nghĩa hơn.

## 4. CASE theo điều kiện: phân loại bằng ngưỡng và khoảng

Yêu cầu: phân nhóm số tiền:

- Chưa biết số tiền: `amount IS NULL` → “Chưa có giá trị”.
- Từ **500 trở lên** → “Lớn”.
- Từ **100 đến dưới 500** → “Vừa”.
- Dưới **100** → “Nhỏ”.

Viết bằng dạng theo điều kiện:

~~~sql
SELECT
    order_id,
    customer_name,
    amount,
    CASE
        WHEN amount IS NULL THEN 'Chua co gia tri'
        WHEN amount >= 500 THEN 'Lon'
        WHEN amount >= 100 THEN 'Vua'
        ELSE 'Nho'
    END AS amount_group
FROM lab_case_orders_151
ORDER BY order_id;
~~~

Kết quả:

| order_id | amount | amount_group |
| ---: | ---: | --- |
| 101 | 120.00 | Vua |
| 102 | 450.00 | Vua |
| 103 | 0.00 | Nho |
| 104 | 950.00 | Lon |
| 105 | 80.00 | Nho |
| 106 | 300.00 | Vua |
| 107 | `NULL` | Chua co gia tri |
| 108 | 1000.00 | Lon |

Ở đây có ba đặc điểm của `CASE` theo điều kiện:

1. `WHEN amount IS NULL` không dùng phép so sánh bằng, mà kiểm tra **sự thiếu giá trị**.
2. Các nhánh dùng điều kiện khoảng `amount >= ...`, không phải chỉ so sánh với một mã cố định.
3. Khi xét nhánh `amount >= 100`, những hàng có `amount >= 500` đã được xử lý bởi nhánh **đứng trước**, nên không cần viết thêm `AND amount < 500` trong ví dụ này.

### 4.1. Thứ tự WHEN làm thay đổi kết quả

`CASE` chọn **nhánh đầu tiên có điều kiện TRUE**. Vì vậy thứ tự nhánh từ cụ thể/ưu tiên cao xuống thấp rất quan trọng:

~~~sql
-- SAI ve logic neu muon phan loai 500 tro len la "Lon".
CASE
    WHEN amount >= 100 THEN 'Vua'
    WHEN amount >= 500 THEN 'Lon'
    ELSE 'Nho'
END
~~~

Với `amount = 950`, điều kiện đầu tiên `amount >= 100` đã là TRUE, nên kết quả **“Vừa”**. Nhánh `amount >= 500` không còn cơ hội được chọn.

Cách đúng là xét ngưỡng cao trước:

~~~sql
CASE
    WHEN amount >= 500 THEN 'Lon'
    WHEN amount >= 100 THEN 'Vua'
    ELSE 'Nho'
END
~~~

Ví dụ này vẫn cần nhánh `amount IS NULL` nếu nghiệp vụ muốn phân biệt “chưa có giá trị” với nhóm nhỏ. Nếu bỏ nhánh đó, `amount = NULL` không thỏa `>= 500` hoặc `>= 100` và sẽ rơi vào `ELSE 'Nho'`, gây hiểu sai dữ liệu.

### 4.2. WHEN có thể dùng AND, OR và BETWEEN

Một điều kiện `WHEN` có thể phối hợp nhiều phép kiểm tra:

~~~sql
CASE
    WHEN order_status = 'NEW' AND amount >= 500
        THEN 'Moi tao - Gia tri cao'
    WHEN order_status = 'NEW' AND amount >= 100
        THEN 'Moi tao - Gia tri vua'
    WHEN order_status IN ('PAID', 'SHIPPED')
        THEN 'Da xu ly'
    ELSE 'Can xem lai'
END
~~~

Nếu dùng `BETWEEN 100 AND 499` trên cột `NUMERIC` có hai chữ số thập phân, điều kiện sẽ **không bao phủ 499.50**, vì `BETWEEN` bao gồm cả hai đầu mút nhưng giới hạn trên chỉ là 499. Nên ưu tiên `amount >= 100 AND amount < 500` hoặc cấu trúc ngưỡng như ví dụ trước để mô tả khoảng một cách chính xác.

**Đừng xem `CASE` là cơ chế tự hiểu ý định:** nếu quy tắc nghiệp vụ thay đổi từ “≥500” sang “>500”, phải sửa toán tử tương ứng và kiểm tra giá trị biên 500.

## 5. CASE và logic ba giá trị: TRUE, FALSE, UNKNOWN

Trong SQL, điều kiện Boolean có thể là **TRUE**, **FALSE** hoặc **UNKNOWN** do `NULL`. Với dạng `CASE WHEN dieu_kien THEN ...`:

- `TRUE` → chọn nhánh đó (nếu chưa có nhánh TRUE nào trước).
- `FALSE` → bỏ qua nhánh.
- `UNKNOWN` → cũng bỏ qua nhánh, không coi là TRUE.

Ví dụ:

~~~sql
SELECT
    order_id,
    order_status,
    CASE
        WHEN order_status = 'NEW' THEN 'Moi'
        WHEN order_status <> 'NEW' THEN 'Khong moi'
        ELSE 'Chua biet'
    END AS status_check
FROM lab_case_orders_151
ORDER BY order_id;
~~~

Dòng 106 có `order_status IS NULL`, nên cả `order_status = 'NEW'` lẫn `order_status <> 'NEW'` đều cho **UNKNOWN**. Kết quả dòng 106 là **“Chưa biết”**, không phải “Không mới”.

### 5.1. Vì sao CASE cot WHEN NULL THEN ... không đúng?

Một lỗi thường gặp:

~~~sql
-- SAI neu muon bat nhanh gia tri NULL.
CASE order_status
    WHEN NULL THEN 'Chua co trang thai'
    ELSE 'Da co trang thai'
END
~~~

Với PostgreSQL và ngữ nghĩa SQL thông thường, phép kiểm tra khớp ở dạng đơn giản dựa trên so sánh bằng. `NULL = NULL` có kết quả **UNKNOWN**, nên `WHEN NULL` **không khớp** hàng `order_status IS NULL`. Câu trên sẽ trả về `'Da co trang thai'` ngay cả khi dữ liệu là `NULL`.

Viết đúng bằng dạng theo điều kiện:

~~~sql
CASE
    WHEN order_status IS NULL THEN 'Chua co trang thai'
    ELSE 'Da co trang thai'
END
~~~

Hoặc kết hợp điều kiện `IS NULL` với các mã trạng thái khác:

~~~sql
CASE
    WHEN order_status IS NULL THEN 'Chua xac dinh'
    WHEN order_status = 'CANCELLED' THEN 'Da huy'
    WHEN order_status = 'NEW' THEN 'Moi tao'
    ELSE 'Da xu ly'
END
~~~

**Quy tắc dễ nhớ:** khi cần nhận diện `NULL`, dùng `IS NULL` hoặc `IS NOT NULL` trong `CASE WHEN`. Không dùng `= NULL`, `<> NULL` hay `CASE x WHEN NULL` để bắt giá trị thiếu.

### 5.2. ELSE bị bỏ thì nhận gì?

~~~sql
SELECT
    order_id,
    CASE order_status
        WHEN 'PAID' THEN 'Da thanh toan'
    END AS payment_label
FROM lab_case_orders_151
ORDER BY order_id;
~~~

Chỉ các đơn 102 và 107 có `payment_label = 'Da thanh toan'`. Sáu đơn còn lại nhận **`NULL`** trong cột kết quả.

Đó là hành vi mặc định của biểu thức `CASE` khi không có nhánh khớp và không có `ELSE`. `NULL` ở đây là **giá trị của biểu thức truy vấn**, không phải dữ liệu gốc bị cập nhật thành `NULL`.

## 6. CASE theo nhiều cột: trạng thái xử lý và hạn thanh toán

Một tình huống thường gặp là quy tắc phụ thuộc cả **trạng thái** lẫn **ngày hạn**. Giả sử quy ước báo cáo như sau:

1. Đơn `CANCELLED` → “Đã hủy”, không xét quá hạn.
2. Đơn `PAID` hoặc `SHIPPED` → “Đã xử lý”.
3. Chưa biết trạng thái → “Chưa xác định”.
4. Chưa có ngày hạn → “Chưa có hạn”.
5. Ngày hạn **trước ngày đánh giá** → “Quá hạn”.
6. Còn lại → “Còn hạn”.

Để kết quả bài thực hành không thay đổi theo ngày bạn chạy, dùng **mốc giả định cố định ngày 14/11/2026**, thay vì `CURRENT_DATE`:

~~~sql
SELECT
    order_id,
    customer_name,
    order_status,
    due_on,
    CASE
        WHEN order_status = 'CANCELLED' THEN 'Da huy'
        WHEN order_status IN ('PAID', 'SHIPPED') THEN 'Da xu ly'
        WHEN order_status IS NULL THEN 'Chua xac dinh'
        WHEN due_on IS NULL THEN 'Chua co han'
        WHEN due_on < DATE '2026-11-14' THEN 'Qua han'
        ELSE 'Con han'
    END AS processing_label
FROM lab_case_orders_151
ORDER BY order_id;
~~~

| order_id | order_status | due_on | processing_label |
| ---: | --- | --- | --- |
| 101 | NEW | 2026-11-20 | Con han |
| 102 | PAID | 2026-11-12 | Da xu ly |
| 103 | CANCELLED | 2026-11-05 | Da huy |
| 104 | SHIPPED | 2026-11-09 | Da xu ly |
| 105 | NEW | 2026-11-11 | Qua han |
| 106 | `NULL` | 2026-11-10 | Chua xac dinh |
| 107 | PAID | 2026-11-13 | Da xu ly |
| 108 | NEW | `NULL` | Chua co han |

Câu SQL này không thể được diễn đạt gọn bằng dạng `CASE order_status WHEN ...` đơn giản, vì nhiều nhánh so sánh **ngày**, kiểm tra `NULL` và phối hợp nhiều điều kiện. Dạng `CASE WHEN ...` phù hợp hơn.

Thứ tự nhánh cũng là **quy tắc ưu tiên nghiệp vụ**: đơn đã thanh toán nhưng hạn quá khứ được gán “Đã xử lý” trước khi xét quá hạn. Nếu đặt `WHEN due_on < ...` lên trước, đơn 102/104/107 có thể bị đánh dấu “Quá hạn” dù chúng đã xử lý, trái với quy ước đang minh họa.

Trong hệ thống thật, khái niệm “đã xử lý”, “đã thanh toán” và “quá hạn” phải được định nghĩa theo dữ liệu thực tế; không tự coi mọi trạng thái `SHIPPED` là đã thanh toán nếu quy trình kinh doanh của ứng dụng không bảo đảm điều đó.

## 7. CASE trả về giá trị, không phải câu lệnh điều khiển độc lập

`CASE` được đặt tại nơi SQL cần **một biểu thức**:

~~~sql
SELECT
    order_id,
    CASE WHEN amount >= 500 THEN 'Lon' ELSE 'Khac' END AS amount_group
FROM lab_case_orders_151;
~~~

Trong đó, `CASE ... END` là biểu thức tạo giá trị cho cột `amount_group`. Nó có thể được sử dụng trong `SELECT`, `ORDER BY`, `GROUP BY`, `HAVING`, biểu thức của `UPDATE`, các hàm tổng hợp và những nơi cho phép biểu thức phù hợp.

Không thể viết `CASE ... THEN UPDATE ... ELSE DELETE ... END` rồi coi các nhánh là những câu lệnh SQL độc lập. Đó là sự nhầm lẫn giữa **biểu thức lựa chọn giá trị** và **điều khiển luồng thủ tục**. Những hệ quản trị có ngôn ngữ stored procedure riêng có thể cung cấp `IF`/`ELSIF`/`ELSE` hoặc cú pháp khác để điều khiển luồng, nhưng đó là một chủ đề khác.

### 7.1. Các nhánh nên cùng kiểu kết quả tương thích

Một `CASE` trả về **một giá trị có kiểu dữ liệu xác định**. Trong PostgreSQL, các biểu thức ở `THEN` và `ELSE` phải có khả năng quy về một kiểu chung.

Ví dụ phù hợp:

~~~sql
SELECT
    order_id,
    CASE
        WHEN amount >= 500 THEN 'Gia tri lon'
        ELSE 'Gia tri khac'
    END AS description,
    CASE
        WHEN amount >= 500 THEN amount * 0.90
        ELSE amount
    END AS suggested_amount
FROM lab_case_orders_151
ORDER BY order_id;
~~~

`description` có kiểu chuỗi, còn `suggested_amount` có kiểu số vì cả hai nhánh số đều tương thích với `amount NUMERIC`. Với dòng có `amount IS NULL`, điều kiện `amount >= 500` là UNKNOWN, nên nhánh `ELSE amount` trả về `NULL`.

Ví dụ dễ sai:

~~~sql
-- SAI ve kieu du lieu tren PostgreSQL.
SELECT
    CASE WHEN amount >= 500 THEN 'Lon' ELSE 0 END AS mixed_value
FROM lab_case_orders_151;
~~~

`'Lon'` là chuỗi văn bản trong khi `0` là số nguyên. PostgreSQL có thể cố quy về kiểu số và báo lỗi chuyển chuỗi thành số. Để thống nhất kết quả dạng nhãn, dùng:

~~~sql
SELECT
    CASE WHEN amount >= 500 THEN 'Lon' ELSE '0' END AS value_label
FROM lab_case_orders_151;
~~~

Ở ví dụ sau, cả hai nhánh là chuỗi. Tùy mục tiêu nghiệp vụ, `ELSE 'Khac'` có thể có nghĩa rõ ràng hơn `'0'`.

### 7.2. CASE và xử lý phép chia cho 0

Khi cần tính một tỷ lệ, có thể viết:

~~~sql
SELECT
    CASE
        WHEN 0 = 0 THEN NULL
        ELSE 10.0 / 0
    END AS ratio;
~~~

Nhưng **không nên dựa vào việc đặt phép tính lỗi trong nhánh không chọn để bảo đảm mọi truy vấn đều an toàn**. Ở PostgreSQL, bộ lập kế hoạch có thể đánh giá sớm một số biểu thức hằng hoặc hàm, ngay cả khi người viết kỳ vọng nhánh `CASE` sẽ không đi tới đó. `CASE` cũng không làm mọi biểu thức/hàm trở thành có thể kiểm soát thứ tự tác dụng phụ.

Cách rõ ràng để xử lý mẫu số có thể bằng 0 trong biểu thức số học là:

~~~sql
SELECT
    10.0 / NULLIF(0, 0) AS safe_ratio;
~~~

Kết quả `NULL` biểu thị tỷ số không xác định trong ví dụ. Với dữ liệu thật, có thể dùng `NULLIF(denominator, 0)`, kết hợp `CASE` để gắn nhãn nguyên nhân nếu cần. Phần này chỉ minh họa giới hạn của `CASE`; không coi `CASE` là thay thế cho ràng buộc dữ liệu hoặc logic nghiệp vụ đúng.

## 8. CASE trong ORDER BY: sắp xếp theo ưu tiên nghiệp vụ

`ORDER BY` thông thường sắp xếp văn bản theo quy tắc collation hoặc số theo giá trị. Nhưng đôi khi yêu cầu là **NEW trước PAID, rồi SHIPPED, CANCELLED và cuối cùng trạng thái chưa biết**; thứ tự này không phải thứ tự chữ cái.

Sử dụng `CASE` để tạo khóa sắp xếp:

~~~sql
SELECT
    order_id,
    order_status,
    CASE order_status
        WHEN 'NEW' THEN 1
        WHEN 'PAID' THEN 2
        WHEN 'SHIPPED' THEN 3
        WHEN 'CANCELLED' THEN 4
        ELSE 5
    END AS status_rank
FROM lab_case_orders_151
ORDER BY status_rank ASC, order_id ASC;
~~~

Thứ tự ID kết quả:

~~~text
101, 105, 108, 102, 107, 104, 103, 106
~~~

| Nhóm | status_rank | ID theo thứ tự |
| --- | ---: | --- |
| NEW | 1 | 101, 105, 108 |
| PAID | 2 | 102, 107 |
| SHIPPED | 3 | 104 |
| CANCELLED | 4 | 103 |
| `NULL` | 5 | 106 |

Trong PostgreSQL, `ORDER BY` có thể dùng bí danh `status_rank` đã tạo trong danh sách `SELECT`. `order_id ASC` là tiêu chí phụ để phân định các hàng cùng nhóm trạng thái, bảo đảm thứ tự ổn định khi dữ liệu không đổi.

Có thể đặt biểu thức `CASE ... END` trực tiếp bên trong `ORDER BY` mà không cần trả `status_rank` ra danh sách `SELECT`:

~~~sql
SELECT order_id, customer_name, order_status
FROM lab_case_orders_151
ORDER BY
    CASE order_status
        WHEN 'NEW' THEN 1
        WHEN 'PAID' THEN 2
        WHEN 'SHIPPED' THEN 3
        WHEN 'CANCELLED' THEN 4
        ELSE 5
    END ASC,
    order_id ASC;
~~~

Hai truy vấn có cùng thứ tự ID theo ví dụ. Dùng biểu thức trong `ORDER BY` phù hợp khi thứ tự nghiệp vụ là một **quy tắc sắp xếp**, không phải dữ liệu cần lưu trong bảng.

## 9. CASE và tổng hợp có điều kiện

`CASE` thường được đặt **bên trong hàm tổng hợp** để đếm hoặc cộng theo điều kiện.

### 9.1. Đếm số đơn theo trạng thái

~~~sql
SELECT
    COUNT(*) AS total_orders,
    SUM(CASE WHEN order_status = 'NEW' THEN 1 ELSE 0 END) AS new_orders,
    SUM(CASE WHEN order_status = 'PAID' THEN 1 ELSE 0 END) AS paid_orders,
    SUM(CASE WHEN order_status = 'CANCELLED' THEN 1 ELSE 0 END) AS cancelled_orders,
    SUM(CASE WHEN order_status IS NULL THEN 1 ELSE 0 END) AS unknown_orders
FROM lab_case_orders_151;
~~~

Kết quả:

| total_orders | new_orders | paid_orders | cancelled_orders | unknown_orders |
| ---: | ---: | ---: | ---: | ---: |
| 8 | 3 | 2 | 1 | 1 |

Mỗi hàng đóng góp **1 nếu điều kiện đúng**, **0 nếu điều kiện sai hoặc UNKNOWN**. Hàm `SUM` cộng những chỉ báo đó.

Một cách viết khác để đếm đơn PAID:

~~~sql
SELECT
    COUNT(CASE WHEN order_status = 'PAID' THEN 1 END) AS paid_orders
FROM lab_case_orders_151;
~~~

Kết quả bằng **2** vì `CASE` không có `ELSE` trả về `NULL` cho các hàng khác PAID, còn `COUNT(expression)` chỉ đếm giá trị **khác `NULL`**.

Đừng nhầm với câu sau:

~~~sql
-- SAI neu muon dem rieng don PAID.
SELECT
    COUNT(CASE WHEN order_status = 'PAID' THEN 1 ELSE 0 END) AS count_result
FROM lab_case_orders_151;
~~~

Kết quả là **8**: cả `1` và `0` đều khác `NULL`, nên `COUNT(...)` đếm **mọi hàng**, không chỉ hàng PAID. Nếu muốn dạng có `ELSE 0`, dùng `SUM(...)`.

### 9.2. Tính tổng tiền theo điều kiện

~~~sql
SELECT
    SUM(
        CASE
            WHEN order_status = 'PAID' THEN COALESCE(amount, 0)
            ELSE 0
        END
    ) AS paid_amount,
    SUM(
        CASE
            WHEN order_status = 'NEW' THEN COALESCE(amount, 0)
            ELSE 0
        END
    ) AS new_amount
FROM lab_case_orders_151;
~~~

Kết quả: `paid_amount = 450.00` và `new_amount = 1200.00`.

- PAID có đơn 102 số tiền 450 và đơn 107 `amount IS NULL`; ở đây `COALESCE(amount, 0)` dùng quy ước **thiếu số tiền đóng góp 0 vào tổng**.
- NEW có các đơn 101 (120), 105 (80) và 108 (1000); tổng `120 + 80 + 1000 = 1200`.

Quy ước biến `NULL` thành 0 là **lựa chọn báo cáo**, không phải một sự thật bắt buộc về nghiệp vụ. Nếu thiếu số tiền nghĩa là dữ liệu chưa hoàn thiện, hệ thống có thể cần báo cáo riêng **bao nhiêu đơn chưa có tiền**, thay vì che mất thông tin đó:

~~~sql
SELECT
    COUNT(*) AS missing_amount_count
FROM lab_case_orders_151
WHERE amount IS NULL;
~~~

Kết quả là **1**.

Trong PostgreSQL, một cách viết khác cho đếm/cộng có điều kiện là cú pháp `FILTER`:

~~~sql
SELECT
    COUNT(*) FILTER (WHERE order_status = 'NEW') AS new_orders,
    COUNT(*) FILTER (WHERE order_status = 'PAID') AS paid_orders
FROM lab_case_orders_151;
~~~

`FILTER` không được hỗ trợ giống nhau trên mọi hệ quản trị. `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` là mẫu phổ biến, nhưng cũng cần cân nhắc trường hợp tập đầu vào rỗng: `SUM` có thể trả về `NULL` khi không có hàng để tổng hợp, còn `COUNT` trả về 0.

## 10. CASE trong GROUP BY và HAVING

Nếu muốn nhóm các đơn theo **nhóm giá tiền**, có thể dùng cùng biểu thức `CASE` để sinh nhãn rồi tổng hợp. Một cách dễ đọc là tạo nhãn trong truy vấn con, sau đó nhóm ở truy vấn ngoài:

~~~sql
SELECT
    amount_group,
    COUNT(*) AS order_count
FROM (
    SELECT
        CASE
            WHEN amount IS NULL THEN 'Chua co gia tri'
            WHEN amount >= 500 THEN 'Lon'
            WHEN amount >= 100 THEN 'Vua'
            ELSE 'Nho'
        END AS amount_group
    FROM lab_case_orders_151
) AS classified_orders
GROUP BY amount_group
ORDER BY amount_group;
~~~

Kết quả nhóm:

| amount_group | order_count |
| --- | ---: |
| Chua co gia tri | 1 |
| Lon | 2 |
| Nho | 2 |
| Vua | 3 |

Các nhóm được hình thành từ **giá trị đầu ra của CASE**, không yêu cầu bảng nguồn thật sự có cột `amount_group`. Truy vấn con được đặt bí danh `classified_orders` để câu SQL ngoài có thể tham chiếu các cột kết quả của nó.

Nếu chỉ muốn nhóm có ít nhất 3 đơn, đặt `HAVING COUNT(*) >= 3` sau `GROUP BY` trong truy vấn ngoài:

~~~sql
SELECT
    amount_group,
    COUNT(*) AS order_count
FROM (
    SELECT
        CASE
            WHEN amount IS NULL THEN 'Chua co gia tri'
            WHEN amount >= 500 THEN 'Lon'
            WHEN amount >= 100 THEN 'Vua'
            ELSE 'Nho'
        END AS amount_group
    FROM lab_case_orders_151
) AS classified_orders
GROUP BY amount_group
HAVING COUNT(*) >= 3
ORDER BY amount_group;
~~~

Kết quả chỉ còn nhóm **Vua (3)**. `HAVING` lọc **nhóm sau tổng hợp**; `WHERE` lọc **hàng trước tổng hợp**. `CASE` có thể tham gia cả quá trình tạo nhãn và biểu thức điều kiện tổng hợp, nhưng cần hiểu đúng cấp xử lý dữ liệu.

## 11. CASE trong UPDATE: chọn giá trị sẽ ghi

Ngoài `SELECT`, `CASE` có thể xuất hiện trong phần `SET` của câu `UPDATE` để tính **giá trị mới** cho cột. Đây là thao tác **thay đổi dữ liệu thật**, cần cẩn thận với `WHERE`.

Ví dụ nghiệp vụ giả định: chỉ những đơn `NEW` có số tiền từ 500 trở lên được giảm 10%. Ta muốn xem điều đó tác động thế nào tới đơn 108:

~~~sql
BEGIN;

UPDATE lab_case_orders_151
SET amount = CASE
    WHEN order_status = 'NEW' AND amount >= 500
        THEN ROUND(amount * 0.90, 2)
    ELSE amount
END
WHERE order_id = 108;

SELECT order_id, order_status, amount
FROM lab_case_orders_151
WHERE order_id = 108;

ROLLBACK;
~~~

Trong transaction, hàng 108 ban đầu có `amount = 1000.00`; sau `UPDATE` có **900.00**, rồi `ROLLBACK` hoàn tác thay đổi trở về 1000.00. Đây là ví dụ PostgreSQL với dữ liệu thử nghiệm; không nên chạy sửa giá trong bảng sản xuất nếu chưa có yêu cầu nghiệp vụ rõ ràng.

Ở câu lệnh trên:

- `CASE` quyết định **giá trị sẽ gán** vào `amount`.
- `WHERE order_id = 108` quyết định **hàng được cập nhật**.
- `ELSE amount` giữ giá trị cũ nếu không thỏa điều kiện giảm giá.

Nếu không có `ELSE` và không có nhánh phù hợp, giá trị `CASE` có thể là `NULL`; việc cập nhật cột thành `NULL` có thể gây lỗi `NOT NULL` hoặc làm mất dữ liệu cần giữ. Với `UPDATE`, thường nên ghi rõ nhánh dự phòng.

Không dùng `CASE` để thay thế điều kiện giới hạn hàng: một câu `UPDATE` thiếu `WHERE` có thể động chạm mọi hàng, dù chỉ một số hàng thực sự có giá trị thay đổi. Điều đó vẫn có tác động về khóa, trigger hoặc nhật ký ghi tùy hệ quản trị.

## 12. CASE trong WHERE và cách biểu đạt điều kiện

Vì `CASE` trả về một biểu thức, PostgreSQL cho phép dùng kết quả kiểu Boolean của nó trong `WHERE`:

~~~sql
SELECT order_id, customer_name, order_status, amount
FROM lab_case_orders_151
WHERE CASE
    WHEN order_status = 'NEW' AND amount > 100 THEN TRUE
    ELSE FALSE
END
ORDER BY order_id;
~~~

Kết quả là đơn **101** và **108**. Với yêu cầu này, cách viết ngắn và dễ hiểu hơn là dùng điều kiện trực tiếp:

~~~sql
SELECT order_id, customer_name, order_status, amount
FROM lab_case_orders_151
WHERE order_status = 'NEW'
  AND amount > 100
ORDER BY order_id;
~~~

Hai câu cho cùng kết quả trên bảng mẫu. `CASE` có ích khi thực sự cần **chọn giữa nhiều giá trị hoặc quy tắc**; một điều kiện lọc đơn giản thường không cần bọc trong `CASE`. Điều này giúp truy vấn dễ đọc và có thể giúp bộ tối ưu nhận ra điều kiện lọc trực tiếp hơn.

## 13. CASE có thể lồng nhau, nhưng cần giữ quy tắc dễ đọc

Một nhánh `THEN` có thể chứa một biểu thức `CASE` khác. Chẳng hạn:

~~~sql
SELECT
    order_id,
    CASE
        WHEN order_status = 'NEW' THEN
            CASE
                WHEN amount IS NULL THEN 'Moi - Chua co tien'
                WHEN amount >= 500 THEN 'Moi - Gia tri lon'
                ELSE 'Moi - Gia tri thuong'
            END
        ELSE 'Khong phai NEW'
    END AS label
FROM lab_case_orders_151
ORDER BY order_id;
~~~

Trong ví dụ, đơn 108 có nhãn `Moi - Gia tri lon`; đơn 101 và 105 có nhãn `Moi - Gia tri thuong`. Các đơn không phải NEW nhận `Khong phai NEW`, kể cả khi `order_status IS NULL`.

Mỗi `CASE` được đóng bằng một `END` riêng. Nếu lồng quá nhiều cấp, truy vấn trở nên khó đọc và dễ sai thứ tự ưu tiên. Có thể thay bằng một `CASE WHEN` duy nhất với điều kiện phối hợp `AND`, hoặc tách phần phân loại thành view/truy vấn con khi nhiều báo cáo cùng dùng quy tắc đó.

## 14. Những lỗi thường gặp với CASE

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `CASE amount WHEN amount >= 500 THEN ...` | Dạng **đơn giản** mong một giá trị để so sánh với `amount`; `amount >= 500` là biểu thức Boolean, không cùng ý nghĩa | Dùng `CASE WHEN amount >= 500 THEN ...` |
| `CASE status WHEN NULL THEN ...` không bắt được NULL | `NULL = NULL` cho UNKNOWN, không phải TRUE | Dùng `CASE WHEN status IS NULL THEN ...` |
| Nhánh `amount >= 100` đặt trước `amount >= 500` | Nhánh đầu đã chọn cả giá trị 500 trở lên | Đặt ngưỡng cao/ưu tiên cao trước |
| Thiếu `ELSE` nên xuất hiện NULL | Không có nhánh TRUE/khớp và `ELSE` mặc định NULL | Bổ sung `ELSE` phù hợp với nghiệp vụ |
| Gán nhãn “Nhỏ” cho `amount IS NULL` | So sánh với NULL cho UNKNOWN và rơi vào ELSE | Thêm `WHEN amount IS NULL` trước nhánh ngưỡng |
| `THEN 'VIP' ELSE 0` gây lỗi kiểu trên PostgreSQL | Hai nhánh không thể dùng chung kiểu kết quả theo ý nghĩa mong muốn | Dùng chuỗi ở cả hai nhánh, hoặc số ở cả hai nhánh |
| `COUNT(CASE WHEN ... THEN 1 ELSE 0 END)` đếm mọi hàng | `COUNT(expression)` đếm cả 0 vì nó khác NULL | Dùng `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` hoặc `COUNT(CASE WHEN ... THEN 1 END)` |
| Coi `CASE` trong `SELECT` là thay đổi dữ liệu | Biểu thức chỉ tạo giá trị kết quả | Cần `UPDATE` có điều kiện phù hợp nếu thực sự muốn ghi |
| Coi `CASE` luôn ngăn được lỗi ở nhánh không chọn | Một số biểu thức có thể được đánh giá sớm khi lập kế hoạch | Dùng toán tử/hàm an toàn phù hợp, ví dụ `NULLIF` khi chia |
| Không đóng `END` hoặc đặt `;` giữa các `WHEN` | Cấu trúc biểu thức chưa hoàn chỉnh | Đóng từng `CASE` bằng `END`; kết thúc câu SQL ở cuối |
| Gọi mọi dòng không khớp là “Khác” dù có NULL | Bỏ mất ý nghĩa dữ liệu thiếu | Tách nhánh `IS NULL` hoặc chọn nhãn dự phòng rõ ràng |

### Một lưu ý về so sánh chuỗi

`CASE order_status WHEN 'NEW'` phụ thuộc ngữ nghĩa so sánh chuỗi của cơ sở dữ liệu, gồm quy tắc collation và cách phân biệt chữ hoa/chữ thường. Trong PostgreSQL với kiểu `VARCHAR`/`TEXT` và so sánh thông thường, `'NEW'` và `'new'` thường khác nhau. Các hệ quản trị hoặc collation khác có thể so sánh không phân biệt hoa/thường.

Nếu mã trạng thái là dữ liệu quan trọng, nên dùng giá trị được chuẩn hóa và ràng buộc phù hợp thay vì dựa vào một cơ chế ép kiểu/collation ngầm. Ví dụ bảng thực hành dùng `CHECK` để giới hạn tập mã được phép, nhưng vì `order_status` không có `NOT NULL`, giá trị `NULL` vẫn được chấp nhận.

## 15. Khác biệt giữa các hệ quản trị SQL

Hai dạng `CASE` thuộc các cấu trúc phổ biến của SQL và có thể dùng trong PostgreSQL, MySQL, SQL Server, SQLite, Oracle Database với cú pháp cơ bản rất gần nhau:

~~~sql
-- Dạng đơn giản
CASE status
    WHEN 'NEW' THEN 'Moi'
    WHEN 'PAID' THEN 'Da thanh toan'
    ELSE 'Khac'
END

-- Dạng theo điều kiện
CASE
    WHEN score IS NULL THEN 'Chua co diem'
    WHEN score >= 80 THEN 'Gioi'
    WHEN score >= 50 THEN 'Dat'
    ELSE 'Chua dat'
END
~~~

Đây là **hai biểu thức minh họa**, không phải các câu SQL độc lập để chạy ngay nếu thiếu `SELECT` hoặc vị trí sử dụng biểu thức phù hợp.

| Hệ quản trị | `CASE` cơ bản | Điểm cần để ý |
| --- | --- | --- |
| PostgreSQL | Cả hai dạng | Kết quả các nhánh phải quy về kiểu chung; `CASE` có thể dùng ở `SELECT`, `ORDER BY`, `UPDATE`, v.v.; hỗ trợ `FILTER` như lựa chọn tổng hợp |
| MySQL | Cả hai dạng trong biểu thức | Cũng có cấu trúc `CASE` cho stored program, với hình thức và ngữ nghĩa điều khiển luồng riêng; không nhầm với biểu thức `CASE ... END` trong `SELECT` |
| SQL Server | Cả hai dạng | `CASE` là **biểu thức**, không phải câu điều khiển luồng thay thế `IF...ELSE` của T-SQL; quy tắc ưu tiên/ép kiểu dữ liệu cần lưu ý |
| SQLite | Cả hai dạng | Có thêm hàm tiện ích như `iif(...)` ở các phiên bản thích hợp, nhưng `CASE` là cú pháp rõ ràng và phổ biến hơn khi cần nhiều nhánh |
| Oracle Database | Cả hai dạng | Có hàm `DECODE` cho một số trường hợp ánh xạ bằng nhau, nhưng `CASE` theo điều kiện linh hoạt hơn; có quy tắc kiểu và NULL riêng |

Ví dụ minh họa trong bài sử dụng `DATE '2026-11-14'` và `NUMERIC` của PostgreSQL. Khi chuyển sang hệ khác, cách viết literal ngày hoặc ép kiểu có thể khác, còn **ý nghĩa hai dạng CASE** vẫn dựa trên so sánh giá trị hoặc điều kiện đầu tiên TRUE.

## 16. Bài tập thực hành

Các bài sau sử dụng tám dòng trong `lab_case_orders_151` ở mục 2. Hãy tự viết biểu thức, dự đoán kết quả rồi đối chiếu với đáp án. Với lệnh có thể thay đổi dữ liệu, chỉ thực hiện trong database thử nghiệm.

### Bài 1 — CASE đơn giản để ánh xạ trạng thái

**Yêu cầu:** hiển thị `order_id` và cột `short_label`. `NEW` → `'N'`, `PAID` → `'P'`, `SHIPPED` → `'S'`, `CANCELLED` → `'C'`, còn lại → `'?'`.

**Đáp án tham khảo:**

~~~sql
SELECT
    order_id,
    CASE order_status
        WHEN 'NEW' THEN 'N'
        WHEN 'PAID' THEN 'P'
        WHEN 'SHIPPED' THEN 'S'
        WHEN 'CANCELLED' THEN 'C'
        ELSE '?'
    END AS short_label
FROM lab_case_orders_151
ORDER BY order_id;
~~~

Kết quả nhãn theo ID 101–108: **N, P, C, S, N, ?, P, N**.

### Bài 2 — CASE theo điều kiện để phân nhóm số tiền

**Yêu cầu:** nếu `amount` là `NULL`, ghi `'UNKNOWN'`; nếu `amount >= 500` ghi `'HIGH'`; nếu `amount >= 100` ghi `'MEDIUM'`; còn lại `'LOW'`.

**Đáp án:**

~~~sql
SELECT
    order_id,
    CASE
        WHEN amount IS NULL THEN 'UNKNOWN'
        WHEN amount >= 500 THEN 'HIGH'
        WHEN amount >= 100 THEN 'MEDIUM'
        ELSE 'LOW'
    END AS amount_band
FROM lab_case_orders_151
ORDER BY order_id;
~~~

Kết quả theo ID: **MEDIUM, MEDIUM, LOW, HIGH, LOW, MEDIUM, UNKNOWN, HIGH**.

### Bài 3 — Vì sao đảo thứ tự WHEN gây sai?

~~~sql
CASE
    WHEN amount >= 100 THEN 'MEDIUM'
    WHEN amount >= 500 THEN 'HIGH'
    ELSE 'LOW'
END
~~~

**Câu hỏi:** giá trị `amount = 950` được phân loại thế nào? Vì sao?

**Đáp án:** **MEDIUM**, vì `950 >= 100` đã TRUE và là nhánh đầu tiên. Muốn `950` là HIGH, đưa `WHEN amount >= 500` lên trước. Nếu có `NULL`, cần nhánh riêng nếu muốn giữ nhãn UNKNOWN.

### Bài 4 — Bắt NULL đúng cách

**Yêu cầu:** phân biệt trạng thái đang thiếu và đang có. Một người viết:

~~~sql
CASE order_status
    WHEN NULL THEN 'MISSING'
    ELSE 'PRESENT'
END
~~~

**Đáp án sửa:**

~~~sql
SELECT
    order_id,
    CASE
        WHEN order_status IS NULL THEN 'MISSING'
        ELSE 'PRESENT'
    END AS state
FROM lab_case_orders_151
ORDER BY order_id;
~~~

Chỉ đơn **106** có nhãn MISSING. `CASE x WHEN NULL` không bắt được `NULL` theo ngữ nghĩa so sánh bằng thông thường.

### Bài 5 — Đếm số đơn NEW và PAID trong một lần SELECT

**Đáp án:**

~~~sql
SELECT
    SUM(CASE WHEN order_status = 'NEW' THEN 1 ELSE 0 END) AS count_new,
    SUM(CASE WHEN order_status = 'PAID' THEN 1 ELSE 0 END) AS count_paid
FROM lab_case_orders_151;
~~~

Kết quả **count_new = 3**, **count_paid = 2**. Nếu dùng `COUNT(CASE WHEN ... THEN 1 ELSE 0 END)`, cần nhớ rằng cả `1` lẫn `0` đều được đếm.

### Bài 6 — Sắp xếp trạng thái theo mức độ ưu tiên

**Yêu cầu:** hiện đơn `NEW` trước, `PAID` thứ hai, các trạng thái khác sau cùng; trong nhóm dùng ID tăng dần.

**Đáp án:**

~~~sql
SELECT order_id, order_status
FROM lab_case_orders_151
ORDER BY
    CASE order_status
        WHEN 'NEW' THEN 1
        WHEN 'PAID' THEN 2
        ELSE 3
    END ASC,
    order_id ASC;
~~~

Các ID ở hai nhóm đầu: **101, 105, 108**, sau đó **102, 107**. Nhóm còn lại gồm **103, 104, 106** theo ID.

### Bài 7 — ELSE thiếu dẫn đến kết quả gì?

~~~sql
SELECT
    order_id,
    CASE
        WHEN amount >= 500 THEN 'HIGH'
    END AS amount_flag
FROM lab_case_orders_151
ORDER BY order_id;
~~~

**Đáp án:** các đơn **104** và **108** có `amount_flag = 'HIGH'`, các đơn còn lại có **`NULL`**. Khi thiếu `ELSE`, SQL mặc định kết quả NULL nếu không có nhánh nào TRUE, kể cả trường hợp `amount` không có giá trị.

### Bài 8 — Tính tiền giảm giá bằng CASE, không thay đổi dữ liệu

**Yêu cầu:** hiển thị `order_id`, `amount` và `suggested_amount`, trong đó đơn NEW có `amount >= 500` được giảm 10%; các trường hợp khác giữ nguyên giá trị. Không ghi lại bảng.

**Đáp án:**

~~~sql
SELECT
    order_id,
    amount,
    CASE
        WHEN order_status = 'NEW' AND amount >= 500
            THEN ROUND(amount * 0.90, 2)
        ELSE amount
    END AS suggested_amount
FROM lab_case_orders_151
ORDER BY order_id;
~~~

Chỉ đơn **108** có số tiền thay đổi trong **kết quả SELECT**, từ 1000.00 thành **900.00**. Đơn 107 vẫn có số tiền `NULL`. Không có dòng nào trong bảng bị cập nhật.

### Bài 9 — CASE theo điều kiện với mốc thời gian cố định

**Yêu cầu:** chỉ đối với đơn NEW, phân loại `due_on IS NULL` → `'NO_DUE'`, ngày trước `DATE '2026-11-14'` → `'LATE'`, còn lại → `'ON_TIME'`. Với trạng thái khác NEW, ghi `'NOT_NEW'`.

**Đáp án:**

~~~sql
SELECT
    order_id,
    CASE
        WHEN order_status IS DISTINCT FROM 'NEW' THEN 'NOT_NEW'
        WHEN due_on IS NULL THEN 'NO_DUE'
        WHEN due_on < DATE '2026-11-14' THEN 'LATE'
        ELSE 'ON_TIME'
    END AS due_label
FROM lab_case_orders_151
ORDER BY order_id;
~~~

`IS DISTINCT FROM` là cú pháp PostgreSQL (và một số hệ khác) dùng phép so sánh xác định ngay cả khi có `NULL`. Với bảng mẫu: đơn 101 **ON_TIME**, 105 **LATE**, 108 **NO_DUE**; các đơn còn lại **NOT_NEW**, gồm đơn 106 có `order_status IS NULL`. Nếu muốn mã SQL dễ chuyển sang hệ không hỗ trợ `IS DISTINCT FROM`, có thể dùng `WHEN order_status <> 'NEW' OR order_status IS NULL THEN 'NOT_NEW'`.

## 17. Ghi nhớ

| Tình huống | Cách viết phù hợp |
| --- | --- |
| Một cột so với nhiều giá trị cụ thể | `CASE status WHEN 'NEW' THEN ... WHEN 'PAID' THEN ... END` |
| Nhiều phép so sánh, khoảng giá trị, nhiều cột | `CASE WHEN amount >= 500 THEN ... WHEN ... END` |
| Kiểm tra giá trị thiếu | `WHEN col IS NULL THEN ...` |
| Có nhiều điều kiện cùng TRUE | Nhánh **TRUE đầu tiên** được chọn |
| Không nhánh nào phù hợp và không có ELSE | Kết quả là **NULL** |
| Muốn nhãn hiển thị | `CASE ... END AS label` trong `SELECT` |
| Muốn sắp xếp theo ưu tiên riêng | `ORDER BY CASE ... END, id` |
| Muốn đếm có điều kiện | `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` |
| Muốn tính giá trị ghi khi UPDATE | `SET col = CASE ... END`, kết hợp `WHERE` |

Điểm quan trọng nhất là chọn đúng **loại CASE**: dùng **dạng đơn giản** khi các nhánh chỉ so khớp một biểu thức với nhiều giá trị; dùng **dạng theo điều kiện** khi cần ngưỡng, logic kết hợp hoặc kiểm tra `NULL`. Sau đó hãy đọc các `WHEN` **theo đúng thứ tự**, xác định kiểu kết quả `THEN/ELSE` và quyết định trường hợp không khớp cần giá trị gì. Làm rõ ba điều này sẽ giúp biểu thức `CASE` thực hiện đúng rẽ nhánh mà nghiệp vụ mong muốn.
