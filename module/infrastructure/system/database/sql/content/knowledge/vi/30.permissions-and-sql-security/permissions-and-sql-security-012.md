# Che dữ liệu trong kết quả thực hành và thông báo lỗi

Một câu truy vấn có thể chạy đúng nhưng vẫn làm lộ dữ liệu. Ví dụ, người học chỉ cần kiểm tra trạng thái đơn hàng, nhưng kết quả thực hành lại in cả email, số điện thoại và mã định danh cá nhân. Một truy vấn khác thất bại vì email bị trùng; thông báo lỗi hiển thị nguyên giá trị email, tên bảng hoặc chi tiết ràng buộc. Nếu chụp màn hình, sao chép kết quả vào tài liệu hoặc gửi log cho nhóm hỗ trợ, dữ liệu nhạy cảm có thể rời khỏi phạm vi cần thiết.

**Che dữ liệu** (*data masking*) là cách thay thế, ẩn bớt hoặc biến đổi một phần dữ liệu trước khi nó xuất hiện trong một ngữ cảnh cụ thể. Mục tiêu là giúp người thực hành, nhân viên hỗ trợ và hệ thống giám sát hiểu được kết quả mà **không cần nhìn thấy dữ liệu gốc không liên quan**.

Bài học **Database SQL → Quyền và SQL an toàn** tập trung vào hai nơi thường bị bỏ quên:

1. **Kết quả thực hành:** bảng kết quả của SQL client, dữ liệu trả về từ API, kết quả RETURNING, file CSV, ảnh chụp màn hình, notebook, bản ghi debug và ví dụ trong tài liệu.
2. **Thông báo lỗi:** lỗi do constraint, exception trong function, thông tin trả về cho người dùng, log ứng dụng, log database, trace và công cụ giám sát.

Bài sử dụng **PostgreSQL** làm hệ quản trị chính, kèm so sánh SQL Server, Oracle, MySQL và SQLite. Các ví dụ dùng **dữ liệu giả** với tiền tố lab_r384_. Không đưa dữ liệu khách hàng thật, mật khẩu, token hoặc bí mật vận hành vào bài thực hành.

## 1. Vì sao phải che dữ liệu trong kết quả và lỗi?

Một hệ thống thường có nhiều loại thông tin:

| Loại dữ liệu | Ví dụ | Rủi ro nếu xuất hiện không đúng nơi |
| --- | --- | --- |
| Thông tin nhận dạng trực tiếp | Họ tên, email, số điện thoại, địa chỉ | Nhận diện hoặc liên hệ một người |
| Định danh nhạy cảm | Mã số thuế, số giấy tờ, số tài khoản | Mạo danh, gian lận, liên kết hồ sơ |
| Dữ liệu giao dịch | Giá trị đơn, số dư, lịch sử thanh toán | Lộ hoạt động hoặc tình hình tài chính |
| Bí mật xác thực | Mật khẩu, access token, API key, session ID | Truy cập trái phép vào hệ thống |
| Dữ liệu nội bộ | Ghi chú hỗ trợ, đánh giá rủi ro, thông tin điều tra | Lộ quy trình hoặc thông tin nội bộ |
| Chi tiết hạ tầng | Tên schema, đường dẫn file, stack trace, hostname | Hỗ trợ kẻ tấn công dò cấu trúc hệ thống |

Một kết quả SQL thường được xem là “chỉ để học”, nhưng dữ liệu trong đó có thể được:

- Sao chép vào bài tập, README hoặc ticket.
- Xuất thành CSV/XLSX rồi gửi qua email hoặc chat.
- Chụp màn hình và đăng vào diễn đàn.
- Ghi vào log CI/CD, notebook hoặc công cụ giám sát.
- Giữ lại trong lịch sử truy vấn hoặc clipboard.
- Dùng làm dữ liệu mẫu cho những lần đào tạo sau.

Thông báo lỗi cũng là một **đầu ra dữ liệu**. Lỗi duplicate key có thể nêu giá trị khóa bị trùng; lỗi ràng buộc khóa ngoại có thể cho biết đối tượng liên quan; stack trace có thể để lộ tên hàm, bảng, schema hoặc tham số. Vì vậy, bảo vệ kết quả truy vấn mà bỏ qua lỗi là chưa đủ.

### 1.1. Bốn câu hỏi trước khi hiển thị dữ liệu

1. **Ai sẽ nhìn thấy?** Người thực hành, nhà phát triển, quản trị viên, khách hàng hay bên thứ ba?
2. **Họ cần biết điều gì để hoàn thành nhiệm vụ?** Trạng thái, số lượng, mã tham chiếu hay toàn bộ hồ sơ?
3. **Có thể giảm độ chi tiết không?** Chỉ hiện bốn số cuối, một mã giả, một tổng hợp hay một thông báo chung?
4. **Đầu ra sẽ đi đâu tiếp theo?** UI, log, CSV, screenshot, ticket hay hệ thống phân tích?

Che dữ liệu đúng nghĩa là **giảm lượng thông tin được tiết lộ theo mục đích**, chứ không chỉ thay một vài ký tự bằng dấu sao.

## 2. Phân biệt masking, redaction, pseudonymization, anonymization và encryption

Những khái niệm này liên quan nhưng không thể thay thế nhau.

| Khái niệm | Cách hiểu | Có thể khôi phục dữ liệu gốc? | Ví dụ |
| --- | --- | --- | --- |
| **Masking** | Ẩn hoặc thay một phần/toàn bộ giá trị trong một ngữ cảnh | Tùy cách làm | an@example.test → a*********@example.test |
| **Redaction** | Loại bỏ hoặc che thông tin không được phép hiển thị | Thường không qua đầu ra đã redacted | Hiện [redacted] thay số giấy tờ |
| **Pseudonymization** | Thay định danh bằng mã giả để vẫn liên kết bản ghi theo một cơ chế | Có thể, nếu có bảng ánh xạ/khóa | customer_id → CUST-X7Q2 |
| **Anonymization** | Biến đổi để không còn khả năng nhận diện hợp lý theo mô hình rủi ro đã đánh giá | Thiết kế nhằm không khôi phục | Tập dữ liệu tổng hợp/ẩn danh đã xử lý |
| **Encryption** | Mã hóa dữ liệu bằng khóa để người không có khóa không đọc được | Có, với khóa phù hợp | Dữ liệu được mã hóa khi lưu/truyền |
| **Hashing** | Tính giá trị băm một chiều theo thuật toán | Không giải mã trực tiếp; nhưng giá trị dễ đoán có thể dò ngược | Hash của email hoặc mật khẩu |
| **Tokenization** | Thay giá trị bằng token, thường có hệ thống giữ ánh xạ an toàn | Có thể qua token vault | Số tài khoản → token tham chiếu |

### 2.1. Masking không tự biến dữ liệu thành ẩn danh

Ví dụ:

~~~text
Email goc:        an.nguyen@example.test
Email da che:     a**********@example.test
~~~

Người xem vẫn biết tên miền và ký tự đầu. Nếu chỉ có một người trong tổ chức dùng tên miền đó, giá trị đã che vẫn có thể giúp nhận diện. Tương tự, giữ bốn số cuối của số điện thoại có thể đủ để liên kết với thông tin khác.

**Masking giảm mức lộ thông tin, không tự chứng minh dữ liệu đã ẩn danh.** Cần đánh giá các trường có thể kết hợp để nhận diện lại.

### 2.2. Pseudonymization vẫn có thể liên kết các bản ghi

Nếu mọi lần xuất dữ liệu đều thay khách hàng 123 thành CUSTOMER-123, người xem vẫn có thể ghép các giao dịch của cùng một khách hàng. Điều này có ích cho phân tích chuỗi sự kiện, nhưng không phải ẩn danh hoàn toàn.

Nếu token có bảng ánh xạ, người có quyền vào bảng ánh xạ có thể khôi phục định danh. Bảo vệ bảng ánh xạ và khóa token là một phần của mô hình bảo mật.

### 2.3. Hash không phải công cụ masking mặc định

Email, số điện thoại và mã định danh thường có **không gian giá trị có thể đoán được**. Hash không khóa của các giá trị đó có thể bị dò bằng danh sách ứng viên. Salt công khai không tự ngăn việc dò từ điển; HMAC cần khóa bí mật được quản lý an toàn và kết quả vẫn cho phép liên kết các lần xuất nếu dùng cùng khóa.

Không dùng MD5(email) hoặc SHA256(phone) rồi gọi tập dữ liệu là ẩn danh. Nếu cần token ổn định, hãy thiết kế cơ chế tokenization/HMAC có quản lý khóa và giới hạn truy cập.

### 2.4. Encryption không giống masking trong kết quả

Mã hóa ổ đĩa hoặc kết nối TLS bảo vệ dữ liệu ở trạng thái lưu trữ/truyền tải. Khi một truy vấn được phép đọc cột email, database vẫn có thể trả **email rõ** cho người gọi. Để giới hạn kết quả, cần phân quyền, view, policy hoặc cơ chế masking thích hợp.

## 3. Quy tắc chọn cách che

Không có một phép biến đổi phù hợp cho mọi trường dữ liệu. Hãy chọn theo mục đích:

| Mục đích | Đầu ra nên cân nhắc |
| --- | --- |
| Xác nhận email thuộc hồ sơ nào trong giao diện hỗ trợ | Hiện một phần email, nếu phần còn lại đủ để phân biệt và chính sách cho phép |
| Kiểm tra khách gọi đúng số điện thoại | Hiện vài số cuối, không hiện toàn bộ |
| Chụp màn hình bài SQL | Dùng dữ liệu giả hoặc mã giả; loại bỏ cột không cần |
| Đếm số đơn theo trạng thái | Chỉ trả tổng hợp, không trả thông tin cá nhân |
| Kiểm tra lỗi dữ liệu | Trả mã lỗi và mã tham chiếu, không in giá trị nhạy cảm |
| Phân tích liên kết nhiều bảng trong sandbox | Dùng token ổn định được tạo có kiểm soát |
| Kiểm thử tải hoặc logic | Ưu tiên dữ liệu tổng hợp có cấu trúc giống thật |

### 3.1. Che ít nhất nhưng vẫn đủ dùng

Nếu người hỗ trợ chỉ cần biết hồ sơ có email hay không, có thể trả:

~~~sql
SELECT
    customer_id,
    email IS NOT NULL AS has_email
FROM lab_r384.customers;
~~~

Không cần trả email đã che nếu chỉ cần kiểm tra **sự hiện diện**.

Nếu cần phân biệt hồ sơ trong một ticket, có thể dùng mã tham chiếu giả. Mã tham chiếu cũng cần được đánh giá: nếu nó là ID nội bộ tăng tuần tự và có thể truy ngược sang khách hàng, nó vẫn có thể là dữ liệu liên kết.

### 3.2. Ưu tiên dữ liệu giả cho bài học

Đối với tài liệu hướng dẫn SQL, dữ liệu giả thường tốt hơn dữ liệu thật đã che:

- Có thể chủ động tạo tình huống hợp lệ, lỗi, trùng lặp và biên.
- Không cần xử lý bảng ánh xạ hoặc khóa token.
- Dễ chia sẻ ví dụ và tái tạo kết quả.
- Tránh vô tình giữ lại một trường nhận diện trong screenshot.

Dữ liệu giả phải được tạo có chủ đích; không dùng email hoặc số điện thoại thật chỉ vì chúng trông giống dữ liệu thử.

## 4. Chuẩn bị dữ liệu giả cho PostgreSQL

Các ví dụ sử dụng schema riêng lab_r384. Chạy trên database sandbox, bằng role có quyền tạo schema/bảng/function. Nếu schema đã tồn tại, không chạy lại nguyên script tạo bảng.

### 4.1. Tạo bảng khách hàng giả

~~~sql
CREATE SCHEMA lab_r384;

CREATE TABLE lab_r384.customers (
    customer_id INTEGER PRIMARY KEY,
    customer_ref TEXT NOT NULL UNIQUE,
    full_name TEXT,
    email TEXT,
    phone TEXT,
    tax_id TEXT,
    internal_note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO lab_r384.customers (
    customer_id,
    customer_ref,
    full_name,
    email,
    phone,
    tax_id,
    internal_note
)
VALUES
    (1, 'CUST-DEMO-001', 'An Nguyen',
     'an.nguyen@example.test', '+84 900 111 222',
     'TAX-DEMO-001', 'Demo record for support training'),
    (2, 'CUST-DEMO-002', 'Binh Tran',
     'binh.tran@example.test', '+84 900 333 444',
     'TAX-DEMO-002', 'Synthetic record only'),
    (3, 'CUST-DEMO-003', 'Chi Le',
     'chi.le@example.test', '+84 900 555 666',
     'TAX-DEMO-003', 'No real customer data');
~~~

Tên miền .test và mã DEMO được dùng cho ví dụ. **Không thay dữ liệu giả bằng hồ sơ khách hàng thật** khi chạy bài trên máy cá nhân.

### 4.2. Bảng đơn hàng

~~~sql
CREATE TABLE lab_r384.orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES lab_r384.customers(customer_id),
    order_status TEXT NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL
        CHECK (total_amount >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO lab_r384.orders (
    order_id, customer_id, order_status, total_amount
)
VALUES
    (1001, 1, 'PAID', 120000.00),
    (1002, 1, 'NEW',   50000.00),
    (1003, 2, 'PAID', 220000.00),
    (1004, 3, 'CANCELLED', 80000.00);
~~~

### 4.3. Kết quả raw chỉ để minh họa rủi ro

~~~sql
-- KHONG DUNG KIEU SELECT NAY DE CHUP MAN HINH
-- HOAC XUAT FILE CHIA SE.
SELECT *
FROM lab_r384.customers
ORDER BY customer_id;
~~~

Kết quả có cả email, phone, tax_id và internal_note. Dù dữ liệu trong bài là giả, câu truy vấn này cho thấy vì sao SELECT * dễ làm lộ nhiều cột hơn yêu cầu. Trong tài liệu thực hành, hãy **liệt kê rõ cột cần dùng**.

## 5. Masking ngay trong câu SELECT

Với một bài thực hành đơn giản, có thể biến đổi giá trị trong biểu thức SELECT. Cách này giúp kết quả của **câu truy vấn cụ thể** đã được che.

### 5.1. Che email, giữ một phần đầu và tên miền

~~~sql
SELECT
    customer_ref,
    CASE
        WHEN email IS NULL THEN NULL
        WHEN POSITION('@' IN email) <= 1 THEN '[redacted]'
        ELSE
            LEFT(email, 1)
            || REPEAT(
                '*',
                GREATEST(POSITION('@' IN email) - 2, 1)
            )
            || SUBSTRING(email FROM POSITION('@' IN email))
    END AS masked_email
FROM lab_r384.customers
ORDER BY customer_id;
~~~

Kết quả minh họa:

| customer_ref | masked_email |
| --- | --- |
| CUST-DEMO-001 | a********@example.test |
| CUST-DEMO-002 | b********@example.test |
| CUST-DEMO-003 | c*****@example.test |

Đây chỉ là **một quy tắc hiển thị**, không phải chuẩn masking áp dụng cho mọi email. Nó giữ ký tự đầu và tên miền; tên miền có thể là thông tin nhận diện tổ chức. Nếu không cần tên miền, trả [masked-email] hoặc một token giả thay vì giữ lại.

### 5.2. Che số điện thoại, chỉ giữ bốn số cuối

~~~sql
WITH normalized AS (
    SELECT
        customer_ref,
        REGEXP_REPLACE(phone, '[^0-9]', '', 'g') AS digits
    FROM lab_r384.customers
)
SELECT
    customer_ref,
    CASE
        WHEN digits IS NULL OR digits = '' THEN '[redacted]'
        WHEN LENGTH(digits) <= 4
            THEN REPEAT('*', LENGTH(digits))
        ELSE
            REPEAT('*', LENGTH(digits) - 4)
            || RIGHT(digits, 4)
    END AS masked_phone
FROM normalized
ORDER BY customer_ref;
~~~

Kết quả:

| customer_ref | masked_phone |
| --- | --- |
| CUST-DEMO-001 | ********2222 |
| CUST-DEMO-002 | ********4444 |
| CUST-DEMO-003 | ********6666 |

Truy vấn chuẩn hóa về chữ số trước khi che. Dữ liệu thật có thể chứa mã quốc gia, số máy lẻ hoặc định dạng đặc biệt; cần thống nhất quy tắc nghiệp vụ trước khi áp dụng.

### 5.3. Không hiển thị mã định danh và ghi chú nội bộ

Nếu người học chỉ cần xem trạng thái liên hệ:

~~~sql
SELECT
    customer_ref,
    email IS NOT NULL AS has_email,
    phone IS NOT NULL AS has_phone
FROM lab_r384.customers
ORDER BY customer_ref;
~~~

Đây là cách **giảm dữ liệu đầu ra** tốt hơn việc chọn tax_id, internal_note rồi thay bằng chuỗi che. Nếu cột không cần thiết, không trả cột đó.

### 5.4. Kết hợp kết quả thực hành với dữ liệu nghiệp vụ

~~~sql
SELECT
    c.customer_ref,
    CASE
        WHEN POSITION('@' IN c.email) > 1
        THEN LEFT(c.email, 1)
             || REPEAT(
                    '*',
                    GREATEST(POSITION('@' IN c.email) - 2, 1)
                )
             || SUBSTRING(c.email FROM POSITION('@' IN c.email))
        ELSE '[redacted]'
    END AS masked_email,
    o.order_id,
    o.order_status,
    o.total_amount
FROM lab_r384.orders AS o
JOIN lab_r384.customers AS c
    ON c.customer_id = o.customer_id
ORDER BY o.order_id;
~~~

Kết quả có thể dùng để minh họa liên hệ giữa khách và đơn hàng mà không trả phone, tax_id hoặc internal_note. Tuy nhiên customer_ref, email đã che và giá trị đơn vẫn có thể là dữ liệu nhạy cảm tùy người xem và bối cảnh.

### 5.5. Che theo nhóm thay vì lộ số chính xác

Nếu báo cáo chỉ cần phân tích quy mô đơn:

~~~sql
SELECT
    CASE
        WHEN total_amount < 100000 THEN 'Under 100K'
        WHEN total_amount < 200000 THEN '100K-199K'
        ELSE '200K and above'
    END AS amount_band,
    COUNT(*) AS order_count
FROM lab_r384.orders
GROUP BY 1
ORDER BY 1;
~~~

Kết quả là **nhóm giá trị và số lượng**, không cần hiện số tiền từng đơn. Dù vậy, nhóm có quá ít bản ghi vẫn có thể tiết lộ thông tin khi kết hợp với dữ liệu ngoài; cần cân nhắc ngưỡng số lượng tối thiểu hoặc gộp nhóm.

## 6. Tạo hàm masking để dùng lại

Khi nhiều truy vấn cần cùng quy tắc, có thể đóng gói phép biến đổi thành function. Hàm này chỉ giúp **tạo giá trị hiển thị**; nó không tự chặn quyền đọc cột gốc.

### 6.1. Hàm mask_email

~~~sql
CREATE OR REPLACE FUNCTION lab_r384.mask_email(p_email TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
STRICT
AS $fn$
    SELECT CASE
        WHEN POSITION('@' IN p_email) <= 1 THEN '[redacted]'
        ELSE
            LEFT(p_email, 1)
            || REPEAT(
                '*',
                GREATEST(POSITION('@' IN p_email) - 2, 1)
            )
            || SUBSTRING(p_email FROM POSITION('@' IN p_email))
    END;
$fn$;
~~~

- STRICT: nếu đầu vào là NULL, PostgreSQL trả NULL mà không cần thực thi thân hàm.
- IMMUTABLE: kết quả chỉ phụ thuộc đầu vào theo logic của hàm, không đọc bảng hoặc trạng thái thay đổi.
- Kết quả giữ một phần tên miền; chỉ dùng khi chính sách cho phép.

### 6.2. Hàm mask_phone

~~~sql
CREATE OR REPLACE FUNCTION lab_r384.mask_phone(p_phone TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
STRICT
AS $fn$
    SELECT CASE
        WHEN digits = '' THEN '[redacted]'
        WHEN LENGTH(digits) <= 4
            THEN REPEAT('*', LENGTH(digits))
        ELSE
            REPEAT('*', LENGTH(digits) - 4)
            || RIGHT(digits, 4)
    END
    FROM (
        SELECT REGEXP_REPLACE(
            p_phone,
            '[^0-9]',
            '',
            'g'
        ) AS digits
    ) AS normalized;
$fn$;
~~~

### 6.3. Gọi các hàm

~~~sql
SELECT
    customer_ref,
    lab_r384.mask_email(email) AS email_display,
    lab_r384.mask_phone(phone) AS phone_display
FROM lab_r384.customers
ORDER BY customer_ref;
~~~

Việc gọi hàm giúp giảm lặp công thức. Nhưng nếu người dùng có quyền SELECT email, họ vẫn có thể bỏ hàm:

~~~sql
-- Neu caller co SELECT email tren bang goc,
-- cau nay van co the tra email ro.
SELECT email
FROM lab_r384.customers;
~~~

Do đó **function masking không thay thế GRANT/REVOKE**. Muốn giới hạn người gọi chỉ nhìn giá trị đã che, hãy cấp quyền qua view hoặc API được kiểm soát và không cấp quyền đọc cột gốc.

## 7. View là giao diện kết quả đã che

Một view có thể công bố **chỉ các cột cần thiết** và áp dụng masking trước khi dữ liệu đến người dùng báo cáo.

### 7.1. Tạo view hỗ trợ

~~~sql
CREATE OR REPLACE VIEW lab_r384.customer_support_safe AS
SELECT
    customer_ref,
    CASE
        WHEN full_name IS NULL THEN NULL
        WHEN BTRIM(full_name) = '' THEN ''
        ELSE
            LEFT(BTRIM(full_name), 1)
            || REPEAT(
                '*',
                GREATEST(CHAR_LENGTH(BTRIM(full_name)) - 1, 1)
            )
    END AS masked_name,
    lab_r384.mask_email(email) AS masked_email,
    lab_r384.mask_phone(phone) AS masked_phone,
    created_at::DATE AS created_date
FROM lab_r384.customers;
~~~

View không trả tax_id hoặc internal_note. Tên được rút gọn theo ký tự đầu và phần còn lại thành dấu sao; cách này vẫn để lộ độ dài gần đúng nên chỉ là ví dụ.

### 7.2. Cấp quyền trên view

~~~sql
-- Nhom quyen khong dang nhap truc tiep.
CREATE ROLE lab_r384_support_reader NOLOGIN;

GRANT USAGE ON SCHEMA lab_r384
TO lab_r384_support_reader;

GRANT SELECT
ON lab_r384.customer_support_safe
TO lab_r384_support_reader;

GRANT EXECUTE
ON FUNCTION lab_r384.mask_email(TEXT),
            lab_r384.mask_phone(TEXT)
TO lab_r384_support_reader;
~~~

Trong PostgreSQL, quyền truy cập view mặc định được kiểm tra theo **quyền của owner view** đối với những bảng nền trong ngữ cảnh thông thường. Người dùng chỉ được cấp SELECT trên view có thể đọc view mà không có SELECT trực tiếp trên bảng nền, miễn là các quyền liên quan như schema USAGE và EXECUTE cho function được đáp ứng.

**Không cấp**:

~~~sql
-- KHONG CAP CHO support_reader:
-- GRANT SELECT ON lab_r384.customers TO lab_r384_support_reader;
~~~

### 7.3. Kiểm tra đầu ra

~~~sql
SELECT *
FROM lab_r384.customer_support_safe
ORDER BY customer_ref;
~~~

Kết quả minh họa:

| customer_ref | masked_name | masked_email | masked_phone | created_date |
| --- | --- | --- | --- | --- |
| CUST-DEMO-001 | A******** | a*********@example.test | ********2222 | ngày tạo |
| CUST-DEMO-002 | B******** | b*********@example.test | ********4444 | ngày tạo |
| CUST-DEMO-003 | C***** | c*****@example.test | ********6666 | ngày tạo |

Ngày cụ thể phụ thuộc thời điểm chạy script; cột này chỉ để minh họa dữ liệu hiển thị.

### 7.4. Thử đọc bảng gốc

Khi chạy dưới lab_r384_support_reader và không có grant khác:

~~~sql
-- DU KIEN BI TU CHOI:
-- SELECT email, tax_id
-- FROM lab_r384.customers;
~~~

Đây là điểm khác biệt quan trọng:

- **Masking trong SELECT:** người gọi vẫn có thể bỏ phép mask nếu họ có quyền đọc cột gốc.
- **View + quyền giới hạn:** người gọi chỉ có quyền đọc giao diện view, không có quyền trực tiếp đọc cột nhạy cảm của bảng nền.

### 7.5. View PostgreSQL và security_invoker

PostgreSQL hỗ trợ tùy chọn view security_invoker ở các phiên bản hiện đại. View mặc định thường kiểm tra quyền trên bảng nền theo owner của view; khi bật security_invoker, quyền trên bảng nền được xét theo người gọi.

Nếu mục tiêu là cấp quyền đọc view đã che mà **không cấp SELECT bảng gốc**, không bật security_invoker một cách vô thức. Hãy hiểu chính xác owner, quyền bảng nền, function được gọi trong view và chính sách RLS. Cấu hình view không thay thế việc kiểm tra đường truy cập khác.

### 7.6. View không tự đảm bảo mọi hàng đều an toàn

Nếu view trả customer_ref ổn định, người xem có thể liên kết các lần xuất. Nếu view trả giá trị đơn chính xác và ngày/giờ chi tiết, có thể kết hợp để suy ra một giao dịch. Hãy xét **toàn bộ tổ hợp cột**, không chỉ từng cột đã che.

## 8. Masking, quyền cột và Row-Level Security

Ba cơ chế giải quyết ba câu hỏi khác nhau:

| Cơ chế | Câu hỏi |
| --- | --- |
| **Column privileges / view** | Người dùng được xem những cột nào? |
| **Row-Level Security (RLS)** | Người dùng được xem hoặc sửa những hàng nào? |
| **Masking** | Giá trị hiển thị của cột được biến đổi ra sao? |

Ví dụ, role hỗ trợ chỉ được xem thông tin đã che của những khách thuộc tenant mình. Có thể cần:

1. View hoặc function trả **các cột đã che**.
2. RLS giới hạn **hàng theo tenant**.
3. Role không có quyền đọc bảng gốc hoặc các cột nhạy cảm.
4. Kiểm soát chặt identity/tenant context, không để người gọi tự chọn tenant tùy ý.

### 8.1. RLS không tự che cột

Một policy cho phép chỉ đọc hàng của tenant A không có nghĩa email trong hàng đó đã được che. Nếu role được SELECT bảng, nó có thể đọc mọi cột được cấp trong những hàng RLS cho phép.

### 8.2. Masking không tự giới hạn hàng

Một view che email nhưng trả **tất cả tenant** vẫn có thể làm lộ quan hệ khách hàng hoặc dữ liệu giao dịch. Cần lọc hàng bằng policy hoặc view có kiểm soát phù hợp.

### 8.3. Table owner và BYPASSRLS

Trong PostgreSQL, superuser và role có BYPASSRLS bỏ qua RLS; table owner thường cũng có thể bypass trừ khi dùng FORCE ROW LEVEL SECURITY trong trường hợp phù hợp. Kiểm thử bằng tài khoản owner không đại diện hành vi của role ứng dụng bị hạn chế.

## 9. Masking tĩnh cho môi trường thực hành

Masking ở câu SELECT/view là **biến đổi đầu ra**. Nếu cần sao chép dữ liệu sang môi trường học hoặc QA, có thể tạo **bản dữ liệu đã biến đổi trước**.

### 9.1. Tạo bảng demo chỉ chứa dữ liệu đã che

~~~sql
CREATE TABLE lab_r384.customers_training AS
SELECT
    customer_id,
    customer_ref,
    CASE
        WHEN full_name IS NULL THEN NULL
        ELSE LEFT(full_name, 1)
             || REPEAT(
                    '*',
                    GREATEST(CHAR_LENGTH(full_name) - 1, 1)
                )
    END AS display_name,
    lab_r384.mask_email(email) AS email_display,
    lab_r384.mask_phone(phone) AS phone_display,
    created_at::DATE AS created_date
FROM lab_r384.customers;
~~~

Bảng mới chứa các giá trị đã biến đổi tại thời điểm tạo. Nếu dữ liệu nguồn đổi, bảng training **không tự cập nhật**; cần chạy lại quy trình hoặc đồng bộ theo cách có kiểm soát.

### 9.2. Masking tĩnh không phải bản sao hoàn chỉnh cho mọi kiểm thử

Nếu kiểm thử cần:

- Tìm kiếm email theo chính xác giá trị.
- Kiểm tra unique constraint.
- Join theo mã khách.
- Phân tích phân bố dữ liệu.

thì che đơn giản có thể làm thay đổi tính duy nhất hoặc đặc tính thống kê. Ví dụ nhiều email cùng bắt đầu bằng a có thể trở thành cùng chuỗi đã che.

Với kiểm thử nghiệp vụ, **dữ liệu tổng hợp** thường tốt hơn việc che dữ liệu thật rồi dùng làm bản sao.

### 9.3. Sinh dữ liệu giả có cấu trúc hợp lệ

~~~sql
INSERT INTO lab_r384.customers_training (
    customer_id,
    customer_ref,
    display_name,
    email_display,
    phone_display,
    created_date
)
VALUES
    (101, 'TEST-101', 'Test User A',
     'user101@example.test', '0000000101', CURRENT_DATE),
    (102, 'TEST-102', 'Test User B',
     'user102@example.test', '0000000102', CURRENT_DATE);
~~~

Các giá trị trên được thiết kế cho thử nghiệm. Khi cần tạo lượng lớn dữ liệu, hãy dùng generator có quy tắc, tránh trùng khóa, giữ phân bố cần thiết và không vô tình tạo ra số điện thoại/email thật đang hoạt động.

### 9.4. Bản sao dữ liệu phải được che trước khi rời vùng bảo vệ

Nếu export database production sang môi trường QA, masking **sau khi đã import** có thể quá muộn: file dump, bản sao tạm, backup, staging và log nhập dữ liệu đã chứa raw values. Quy trình an toàn cần xác định **điểm biến đổi trước khi dữ liệu đến môi trường có ít quyền kiểm soát hơn**, và kiểm tra cả file tạm/backup.

## 10. Tokenization và mã tham chiếu ổn định

Đôi khi cần liên kết nhiều bảng mà không lộ ID thật. Ví dụ nhóm phân tích muốn biết một khách có bao nhiêu đơn, nhưng không cần biết tên hoặc email.

### 10.1. Token mapping

~~~text
Vung du lieu bao ve:
    customer_id = 12345
           |
           v
    token vault (bang anh xa bi gioi han)
           |
           v
    token = CUST-7KQ2

Vung phan tich:
    CUST-7KQ2 -> order count, amount band
~~~

Token có thể ổn định để join dữ liệu qua nhiều bảng. Nhưng người có quyền đọc vault có thể khôi phục ID; vì thế **vault, khóa và quy trình cấp quyền** cần được bảo vệ.

### 10.2. Không dùng mã tăng tuần tự làm token bảo mật

CUSTOMER-000123 dễ đoán và có thể được thử tuần tự. Nó là mã hiển thị, không phải bí mật. Nếu token phải khó đoán, dùng token ngẫu nhiên có entropy đủ lớn và quản lý ánh xạ trong hệ thống tin cậy.

### 10.3. Không băm trực tiếp giá trị dễ đoán

Một danh sách email hoặc số điện thoại có thể được băm hàng loạt để dò giá trị gốc. Nếu cần mã ổn định để liên kết, cân nhắc HMAC với khóa bí mật, quản lý phiên bản khóa và quyền sử dụng. HMAC vẫn cho phép **liên kết cùng một đầu vào** giữa các bản ghi dùng cùng khóa; nó không tự làm tập dữ liệu vô danh.

### 10.4. Tokenization khác encryption

Encryption lưu giá trị đã mã hóa có thể giải mã bằng khóa. Tokenization thay giá trị bằng một tham chiếu và dựa vào dịch vụ/bảng ánh xạ để đổi lại. Chọn theo yêu cầu nghiệp vụ, khả năng vận hành, hiệu năng và mô hình quản lý khóa.

## 11. Che thông báo lỗi: đừng đưa dữ liệu gốc vào MESSAGE, DETAIL hoặc HINT

Trong PostgreSQL, lỗi có nhiều trường thông tin, ví dụ:

- **SQLSTATE**: mã lỗi ổn định theo nhóm.
- **MESSAGE**: thông điệp chính.
- **DETAIL**: chi tiết bổ sung.
- **HINT**: gợi ý khắc phục.
- **POSITION**: vị trí trong câu lệnh nếu có.
- **CONTEXT**: ngữ cảnh thực thi, có thể chứa tên hàm/trigger/dòng.

Thông báo lỗi có thể được gửi cho SQL client, ứng dụng, API, log hoặc hệ thống giám sát. Vì vậy, **không đặt PII, token, mật khẩu hay toàn bộ input không tin cậy vào thông báo lỗi**.

### 11.1. Mẫu nguy hiểm: in nguyên giá trị

~~~sql
-- KHONG DUNG:
RAISE EXCEPTION
    'Customer email % already exists',
    p_email;
~~~

Nếu email là dữ liệu cá nhân, nó sẽ xuất hiện trong error response hoặc log theo cấu hình. Tương tự, tránh:

~~~sql
-- KHONG DUNG:
RAISE EXCEPTION 'Invalid token: %', p_access_token;
RAISE NOTICE 'Incoming payload: %', NEW.internal_note;
~~~

Không đưa bí mật vào MESSAGE, DETAIL, HINT, NOTICE, WARNING, LOG hoặc nội dung debug.

### 11.2. Thông báo an toàn hơn

~~~sql
RAISE EXCEPTION USING
    ERRCODE = 'PZ001',
    MESSAGE = 'Request could not be completed';
~~~

PZ001 là mã lỗi ứng dụng minh họa gồm năm ký tự. Người gọi biết thao tác thất bại và có thể xử lý theo mã; không cần thấy email, token hay giá trị khóa.

Một ví dụ khác:

~~~sql
RAISE EXCEPTION USING
    ERRCODE = 'PZ404',
    MESSAGE = 'Requested record is unavailable';
~~~

Thông báo không xác nhận một địa chỉ email cụ thể có tồn tại hay không. Trong một số nghiệp vụ, việc phân biệt “không tồn tại” và “không được phép” có thể tạo **user enumeration**; cần cân nhắc trả thông điệp chung cho cả hai trường hợp ở lớp API.

### 11.3. SQLSTATE là hợp đồng kỹ thuật, không phải thông điệp người dùng

Một số SQLSTATE PostgreSQL thường gặp:

| SQLSTATE | Tên/ý nghĩa thường dùng | Ví dụ tình huống |
| --- | --- | --- |
| 23505 | unique_violation | Giá trị khóa duy nhất bị trùng |
| 23503 | foreign_key_violation | Tham chiếu khóa ngoại không hợp lệ |
| 23502 | not_null_violation | Thiếu giá trị bắt buộc |
| 23514 | check_violation | Không thỏa CHECK constraint |
| 22023 | invalid_parameter_value | Tham số không hợp lệ |
| 42501 | insufficient_privilege | Không đủ quyền |
| P0002 | no_data_found | Không tìm thấy dữ liệu trong ngữ cảnh PL/pgSQL |

Ứng dụng có thể dùng SQLSTATE để **phân loại và ánh xạ** sang thông báo an toàn. Đừng phụ thuộc vào việc phân tích chuỗi tiếng Anh của MESSAGE, vì thông điệp có thể thay đổi theo phiên bản, locale hoặc driver.

## 12. Kiểm soát exception trong PL/pgSQL

### 12.1. Báo lỗi đầu vào mà không in giá trị

~~~sql
CREATE OR REPLACE FUNCTION lab_r384_validate_reference(
    p_reference TEXT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $fn$
BEGIN
    IF p_reference IS NULL
       OR BTRIM(p_reference) = '' THEN
        RAISE EXCEPTION USING
            ERRCODE = '22023',
            MESSAGE = 'A valid reference is required';
    END IF;

    RETURN TRUE;
END;
$fn$;
~~~

Lỗi không chứa giá trị thực tế của p_reference. Nếu ứng dụng cần biết nguyên nhân chi tiết hơn, có thể dùng mã lỗi nội bộ hoặc validation code đã được định nghĩa, không phản chiếu input tùy ý.

### 12.2. Không tiết lộ giá trị khóa khi trùng

Ví dụ xử lý trùng mã tham chiếu:

~~~sql
CREATE TABLE lab_r384_unique_demo (
    demo_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    external_ref TEXT NOT NULL UNIQUE
);

CREATE OR REPLACE FUNCTION lab_r384_add_reference(
    p_external_ref TEXT
)
RETURNS VOID
LANGUAGE plpgsql
AS $fn$
BEGIN
    IF p_external_ref IS NULL
       OR BTRIM(p_external_ref) = '' THEN
        RAISE EXCEPTION USING
            ERRCODE = '22023',
            MESSAGE = 'Invalid request';
    END IF;

    INSERT INTO lab_r384_unique_demo(external_ref)
    VALUES (p_external_ref);

EXCEPTION
    WHEN unique_violation THEN
        RAISE EXCEPTION USING
            ERRCODE = 'PZ001',
            MESSAGE = 'Request could not be completed';
END;
$fn$;
~~~

Hàm thay lỗi unique_violation bằng mã/message chung. Giá trị p_external_ref không bị chèn vào thông điệp. **Không phải lúc nào cũng nên bắt mọi unique violation**: nếu function có nhiều INSERT, cần xác định đúng thao tác nào có thể gây trùng, hoặc kiểm tra constraint name qua diagnostics khi thật sự cần.

Trong môi trường API, việc thông báo “đã tồn tại” hay “không thể hoàn tất” phụ thuộc nguy cơ enumeration. Nếu người gọi có quyền biết mã tham chiếu của chính họ, có thể trả mã nghiệp vụ riêng nhưng không nhất thiết trả raw value hoặc thông tin của người khác.

### 12.3. GET STACKED DIAGNOSTICS

PL/pgSQL cho phép lấy thông tin lỗi vừa bắt bằng GET STACKED DIAGNOSTICS:

~~~sql
DO $do$
DECLARE
    v_sqlstate TEXT;
BEGIN
    -- Mot loi du kien trong sandbox:
    PERFORM 1 / 0;

EXCEPTION
    WHEN division_by_zero THEN
        GET STACKED DIAGNOSTICS
            v_sqlstate = RETURNED_SQLSTATE;

        -- Chi log ma loi, khong log input nhay cam.
        RAISE LOG
            'Training operation failed; SQLSTATE=%',
            v_sqlstate;

        RAISE EXCEPTION USING
            ERRCODE = 'PZ001',
            MESSAGE = 'Request could not be completed';
END;
$do$;
~~~

GET STACKED DIAGNOSTICS còn có thể đọc MESSAGE_TEXT, PG_EXCEPTION_DETAIL, PG_EXCEPTION_HINT, PG_EXCEPTION_CONTEXT, CONSTRAINT_NAME, TABLE_NAME, COLUMN_NAME trong ngữ cảnh phù hợp. **Không tự động ghi tất cả các trường này vào log**: MESSAGE_TEXT hoặc DETAIL có thể chứa giá trị dữ liệu gốc.

Ví dụ trên cố ý chỉ log SQLSTATE. Trong ứng dụng thực, nên gắn thêm **correlation ID** hoặc mã thao tác không chứa PII để điều tra sự cố.

### 12.4. RAISE; và RAISE EXCEPTION mới khác nhau

Trong exception handler:

- RAISE; ném lại **exception ban đầu**, bao gồm thông điệp/chi tiết gốc. Điều này hữu ích cho xử lý nội bộ nhưng có thể làm lộ nội dung nếu đi thẳng tới người dùng.
- RAISE EXCEPTION USING ... tạo **exception mới** với SQLSTATE/message do bạn kiểm soát. Cần giữ thông tin chẩn đoán nội bộ an toàn trước khi thay lỗi, nếu chính sách yêu cầu.

Không nên đổi mọi lỗi thành một message chung rồi âm thầm bỏ qua; cần bảo toàn khả năng quan sát thông qua mã lỗi, correlation ID và log được bảo vệ.

### 12.5. Exception block ảnh hưởng transaction thế nào?

Trong PL/pgSQL, một block có EXCEPTION tạo cơ chế xử lý lỗi với rollback các thay đổi **bên trong block đó** trước khi chạy handler (tương tự subtransaction). Nếu handler ném lỗi mới, lỗi vẫn có thể làm statement/transaction bên ngoài thất bại. Nếu handler nuốt lỗi và tiếp tục, hãy hiểu chính xác phần thay đổi nào đã bị hoàn tác và phần nào nằm ngoài block.

Đừng dùng WHEN OTHERS THEN RETURN NULL như cách che mọi lỗi. Nó có thể biến lỗi dữ liệu, quyền hoặc lỗi lập trình thành một kết quả trông như thành công.

## 13. Lỗi constraint có thể tự chứa dữ liệu nhạy cảm

Ngay cả khi không tự RAISE, PostgreSQL có thể tạo lỗi mặc định chứa thông tin về đối tượng và giá trị.

Ví dụ:

~~~sql
CREATE TABLE lab_r384_unique_email_demo (
    record_id INTEGER PRIMARY KEY,
    email TEXT UNIQUE NOT NULL
);

INSERT INTO lab_r384_unique_email_demo
VALUES (1, 'private@example.test');

-- Cau thu hai du kien loi unique_violation:
INSERT INTO lab_r384_unique_email_demo
VALUES (2, 'private@example.test');
~~~

Thông báo lỗi unique_violation có thể có DETAIL dạng khóa bị trùng, chứa **giá trị email**. Đây là lý do không nên đưa nguyên DETAIL database ra UI hoặc ticket.

### 13.1. Không thể luôn che lỗi ở SQL client bằng một câu GRANT

Quyền bảng/cột giới hạn thao tác dữ liệu, nhưng lỗi constraint có thể phát sinh khi người dùng thực hiện một hành động họ **được phép làm**. Nếu driver/SQL client hiển thị nguyên DETAIL, người xem vẫn có thể thấy giá trị.

Giải pháp thường nằm ở nhiều lớp:

- Dùng dữ liệu giả trong môi trường thực hành.
- Thiết kế API/function trả thông báo an toàn.
- Ánh xạ SQLSTATE trong ứng dụng.
- Hạn chế quyền xem log thô.
- Tránh trả DETAIL/stack trace cho người dùng cuối.
- Không ghi giá trị nhạy cảm vào câu SQL/log.

### 13.2. Không bỏ constraint chỉ để lỗi bớt chi tiết

Constraint là lớp bảo vệ tính đúng đắn dữ liệu. Không xóa UNIQUE, CHECK hoặc FOREIGN KEY chỉ vì thông báo lỗi mặc định có thể tiết lộ một giá trị. Hãy **giữ kiểm tra dữ liệu** và kiểm soát nơi thông điệp được hiển thị.

## 14. Thông báo lỗi ở API và ứng dụng

Database exception và thông báo cho người dùng cuối là hai tầng khác nhau.

~~~text
SQL / database
     |
     v
Driver exception
     |
     v
Application error mapper
     |--------------------> Internal diagnostics (restricted)
     |
     v
Safe API response
     |
     v
User interface
~~~

### 14.1. Không trả exception nguyên bản ra HTTP

Một response kiểu:

~~~json
{
  "error": "duplicate key value violates unique constraint ...",
  "detail": "Key (email)=(private@example.test) already exists",
  "where": "SQL function ... line 18"
}
~~~

có thể tiết lộ giá trị email, tên constraint, schema hoặc cấu trúc nội bộ. Đây là **ví dụ response không nên dùng** cho người dùng cuối.

Một response an toàn hơn:

~~~json
{
  "error": "REQUEST_COULD_NOT_BE_COMPLETED",
  "message": "Yêu cầu chưa thể được xử lý.",
  "reference": "req-demo-8f21"
}
~~~

Mã reference là mã tương quan giả trong ví dụ. Ứng dụng dùng nó để tra log nội bộ có kiểm soát, không chứa thông tin cá nhân.

### 14.2. Java/JDBC: log SQLSTATE, trả thông điệp an toàn

~~~java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT lab_r384.mask_email(email) " +
        "FROM lab_r384.customers WHERE customer_id = ?")) {

    ps.setInt(1, customerId);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            return rs.getString(1);
        }
    }
} catch (SQLException ex) {
    String sqlState = ex.getSQLState();

    // Chi ghi ma loi va ma tuong quan.
    // Khong log ex.getMessage(), SQL raw hay tham so nhay cam
    // neu chua co chinh sach log/che du lieu phu hop.
    logger.warn(
        "Customer lookup failed; reference={}, sqlState={}",
        correlationId,
        sqlState
    );

    throw new ServiceException(
        "Yêu cầu chưa thể được xử lý. Mã tham chiếu: "
        + correlationId
    );
}
~~~

Đây là **đoạn minh họa Java/JDBC**, giả định các biến connection, customerId, correlationId, logger và exception của ứng dụng đã được định nghĩa. Ứng dụng thực cần quyết định riêng lỗi nào là not-found, validation, conflict hay server error; không nên đổi mọi lỗi thành cùng một trạng thái HTTP nếu điều đó phá hợp đồng API.

### 14.3. Khi nào log stack trace?

Stack trace hữu ích cho developer và vận hành, nhưng có thể chứa:

- Tên bảng, schema, cột và function.
- Đoạn SQL hoặc tên file.
- Giá trị đầu vào được nối chuỗi.
- Dữ liệu trong exception message.
- Đường dẫn nội bộ, hostname hoặc cấu hình.

Chỉ ghi stack trace vào **kênh nội bộ được kiểm soát**, với quy tắc lọc dữ liệu và thời gian lưu phù hợp. Không đưa stack trace vào response công khai.

### 14.4. Tránh user enumeration

Nếu API trả:

~~~text
Email A không tồn tại.
Email B đã đăng ký.
~~~

kẻ dò quét có thể biết email nào có tài khoản. Với luồng đăng nhập, reset mật khẩu hoặc xác minh hồ sơ, thông điệp có thể cần chung:

~~~text
Nếu thông tin phù hợp, hệ thống sẽ tiếp tục xử lý theo quy trình.
~~~

Thông điệp chung không thay thế rate limiting, xác thực, giám sát và kiểm soát lạm dụng.

## 15. Log database và công cụ giám sát cũng là nơi xuất dữ liệu

Che ở UI nhưng ghi nguyên dữ liệu vào log vẫn là lộ dữ liệu. Cần xem toàn bộ đường đi:

~~~text
SQL parameters
   |                 \
   v                  v
Database error     Application logs
   |                  |
   v                  v
DB server logs      SIEM / observability
   |                  |
   +--------+---------+
            |
            v
      Support ticket / export
~~~

### 15.1. PostgreSQL server log

Một số cấu hình PostgreSQL liên quan:

| Cấu hình | Ảnh hưởng |
| --- | --- |
| log_statement | Quy định nhóm câu lệnh được ghi log |
| log_min_error_statement | Ngưỡng mức lỗi mà câu SQL gây lỗi có thể được ghi |
| log_error_verbosity | Mức chi tiết của thông tin lỗi |
| log_parameter_max_length | Giới hạn ghi tham số trong một số giao thức/trường hợp |
| log_parameter_max_length_on_error | Ảnh hưởng việc ghi giá trị tham số khi có lỗi |
| log_line_prefix | Các trường định danh phiên/tiến trình được thêm vào dòng log |
| application_name | Nhãn ứng dụng/phiên, hữu ích cho điều tra nếu không chứa bí mật |

Tên và hành vi chi tiết của cấu hình phụ thuộc phiên bản PostgreSQL. **Kiểm tra tài liệu đúng phiên bản và cấu hình đang chạy** trước khi thay đổi; không sao chép giá trị mặc định từ một bài viết cũ.

Nếu log ghi toàn bộ statement hoặc bind parameters, email, số tài khoản hay token có thể xuất hiện dù ứng dụng không trả chúng trong response.

### 15.2. Không đưa bí mật vào SQL literal

Không tạo SQL kiểu:

~~~java
// KHONG DUNG:
String sql = "SELECT * FROM users WHERE email = '"
           + email + "'";
~~~

Ngoài nguy cơ SQL injection, câu SQL có thể chứa raw email trong query log hoặc công cụ theo dõi. Dùng prepared statement:

~~~java
String sql =
    "SELECT customer_id FROM lab_r384.customers WHERE email = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, email);
    // Execute theo nhu cau.
}
~~~

Bind parameters giúp tách giá trị khỏi cú pháp câu SQL. **Không đảm bảo mọi hệ thống log đều không ghi tham số**; cần kiểm tra cấu hình driver, database, tracing và APM.

### 15.3. pg_stat_activity và query text

PostgreSQL có view pg_stat_activity cho phép quan sát hoạt động session. Trường query có thể chứa câu SQL hiện tại hoặc gần nhất theo ngữ cảnh. Nếu ứng dụng ghép literal nhạy cảm vào câu SQL, người có quyền xem thống kê có thể nhìn thấy chúng.

Quyền đọc thống kê rộng như pg_read_all_stats cũng cần được cấp có chủ đích. Không cấp quyền xem hoạt động toàn hệ thống cho mọi account hỗ trợ nếu không cần.

### 15.4. Log cần kiểm soát truy cập và vòng đời

Một chính sách log nên nêu:

- Những trường nào được phép ghi.
- Trường nào phải bỏ, mask hoặc tokenize.
- Ai được đọc log thô và ai chỉ được đọc log đã lọc.
- Log được giữ bao lâu, xóa theo quy trình nào.
- Log có được xuất sang bên thứ ba hay không.
- Cách xử lý khi log vô tình chứa bí mật.

**Không xem log là vùng an toàn chỉ vì người dùng cuối không nhìn thấy nó.**

## 16. Masking trong SQL client, kết quả RETURNING và file xuất

### 16.1. Liệt kê cột thay cho SELECT *

Không nên:

~~~sql
SELECT *
FROM lab_r384.customers;
~~~

Nên:

~~~sql
SELECT
    customer_ref,
    lab_r384.mask_email(email) AS email_display
FROM lab_r384.customers;
~~~

Danh sách cột tường minh giúp reviewer biết chính xác thông tin nào được xuất.

### 16.2. RETURNING cũng là đầu ra

Một lệnh ghi dữ liệu có thể làm lộ dữ liệu qua RETURNING:

~~~sql
-- KHONG NEN TRA VE TOAN BO HANG:
-- INSERT INTO ... RETURNING *;
~~~

Nếu ứng dụng chỉ cần ID và trạng thái:

~~~sql
INSERT INTO lab_r384.orders (
    order_id, customer_id, order_status, total_amount
)
VALUES (2001, 1, 'NEW', 50000.00)
RETURNING order_id, order_status;
~~~

Không trả thêm thông tin khách hàng hoặc ghi chú nội bộ nếu caller không cần.

### 16.3. CSV và spreadsheet

Trước khi export:

1. Kiểm tra tiêu đề và toàn bộ cột.
2. Dùng view/masking query đã được phê duyệt.
3. Xem có hidden columns, hidden sheets hoặc metadata chứa raw values không.
4. Kiểm tra tên file, đường dẫn và người nhận.
5. Không đưa raw export lên ticket hoặc chat công khai.
6. Xóa file tạm và bản sao theo quy trình của môi trường.

Một file CSV chỉ có cột email đã che vẫn có thể liên kết với người thật nếu giữ ID, timestamp chi tiết hoặc thông tin hiếm.

### 16.4. Screenshot và notebook

Trước khi chụp màn hình kết quả:

- Thu gọn hoặc bỏ cột không cần.
- Xóa query history/console pane nếu nó hiện literal nhạy cảm.
- Che dữ liệu ở **nguồn truy vấn** hoặc dùng fixture giả; đừng chỉ phủ một hình chữ nhật lên screenshot rồi giữ ảnh gốc ở file khác.
- Kiểm tra cả error pane, tooltip, status bar và tên file.

### 16.5. EXPLAIN và debug output

EXPLAIN, EXPLAIN ANALYZE, debug trace và query plan có thể chứa biểu thức, tên bảng, tên cột, literal hoặc thông tin schema. Trước khi chia sẻ, kiểm tra cả phần plan lẫn query đầu vào. EXPLAIN ANALYZE còn thực thi câu lệnh; dùng transaction rollback khi phù hợp trong sandbox, nhưng nhớ tác động ngoài database không tự hoàn tác.

## 17. Thực hành thiết kế thông báo lỗi an toàn

Giả sử cần tra email của khách theo ID để hỗ trợ. API chỉ cần **email đã che**; nếu không có hồ sơ, trả lỗi chung.

### 17.1. Hàm lookup an toàn

~~~sql
CREATE OR REPLACE FUNCTION lab_r384.safe_support_email(
    p_customer_id INTEGER
)
RETURNS TEXT
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
AS $fn$
DECLARE
    v_email TEXT;
BEGIN
    SELECT c.email
    INTO v_email
    FROM lab_r384.customers AS c
    WHERE c.customer_id = p_customer_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION USING
            ERRCODE = 'PZ404',
            MESSAGE = 'Requested record is unavailable';
    END IF;

    RETURN lab_r384.mask_email(v_email);
END;
$fn$;
~~~

Hàm trả email đã che. Thông báo khi không tìm thấy **không phản chiếu ID đầu vào**. Đây là function SECURITY INVOKER, nên caller cần quyền SELECT cột email trên bảng nguồn; nếu không muốn cấp quyền raw đó, hãy dùng view/API theo mô hình owner quyền đã được đánh giá, hoặc một SECURITY DEFINER function được bảo vệ nghiêm ngặt.

### 17.2. Cẩn thận với SECURITY DEFINER nếu muốn caller không có SELECT raw

Có thể thiết kế một routine SECURITY DEFINER chỉ trả kết quả đã che, nhưng cần:

- Owner là role chuyên biệt, không phải superuser.
- search_path cố định vào schema đáng tin cậy và pg_temp được xử lý an toàn.
- Schema-qualify bảng và function.
- Thu hồi EXECUTE từ PUBLIC rồi cấp cho role đúng.
- Không có nhánh trả raw email, dynamic SQL nguy hiểm hoặc thông báo lỗi chứa input.
- Kiểm thử bằng account thực sự bị hạn chế.

Không biến ví dụ safe_support_email thành SECURITY DEFINER chỉ bằng cách thêm một từ khóa mà bỏ qua các kiểm soát trên.

### 17.3. Thử gọi

~~~sql
SELECT lab_r384.safe_support_email(1);
~~~

Kết quả là email đã che theo quy tắc của mask_email. Với ID không tồn tại:

~~~sql
-- Du kien loi PZ404, message khong co ID:
SELECT lab_r384.safe_support_email(999999);
~~~

Người gọi nhận SQLSTATE PZ404 và message chung. Không có email, tên khách hoặc ID được nhúng vào thông báo.

## 18. Các mức hiển thị lỗi theo đối tượng

Không phải mọi người nhận lỗi đều cần cùng lượng thông tin.

| Người nhận | Thông tin có thể cần | Thông tin nên tránh |
| --- | --- | --- |
| Người dùng cuối | Hành động chưa thành công, bước tiếp theo, mã tham chiếu | SQL text, stack trace, email của người khác, token |
| Nhân viên hỗ trợ | Mã lỗi nghiệp vụ, trạng thái, thông tin đã che, correlation ID | Bí mật xác thực, raw PII không cần thiết |
| Developer | SQLSTATE, tên operation, context kỹ thuật cần thiết | Dữ liệu thật trong payload, mật khẩu, session token |
| DBA/SRE được ủy quyền | Chi tiết kỹ thuật trong log kiểm soát, thông tin constraint phù hợp | Credential rõ, dữ liệu cá nhân ngoài phạm vi sự cố |
| Auditor | Dấu vết truy cập, mã đối tượng giả/token, kết quả kiểm soát | Quyền đọc mặc định mọi dữ liệu raw |

**Chi tiết hơn không đồng nghĩa tốt hơn.** Cung cấp đúng lượng thông tin cho từng vai trò vừa giữ khả năng điều tra, vừa giảm rủi ro tiết lộ.

## 19. Kiểm thử masking và lỗi

Một phép mask cần được thử với **giá trị bình thường, NULL, rỗng, sai định dạng và giá trị biên**.

### 19.1. Kiểm thử email

~~~sql
SELECT
    sample_email,
    lab_r384.mask_email(sample_email) AS masked
FROM (
    VALUES
        ('an.nguyen@example.test'::TEXT),
        ('a@example.test'),
        ('invalid-value'),
        (''),
        (NULL)
) AS samples(sample_email);
~~~

Kết quả dự kiến:

- Email hợp lệ: ký tự đầu và phần còn lại được che theo quy tắc.
- Chuỗi không có @ hoặc chuỗi rỗng: [redacted].
- NULL: NULL do STRICT.

### 19.2. Kiểm thử điện thoại

~~~sql
SELECT
    sample_phone,
    lab_r384.mask_phone(sample_phone) AS masked
FROM (
    VALUES
        ('+84 900 111 222'::TEXT),
        ('1234'),
        ('12'),
        ('not-a-phone'),
        (NULL)
) AS samples(sample_phone);
~~~

Hãy xác định rõ chính sách khi số có ít hơn bốn chữ số, không có chữ số hoặc có số máy lẻ. Ví dụ trong bài che tất cả chữ số nếu chuỗi đã chuẩn hóa có tối đa bốn số.

### 19.3. Kiểm thử lỗi mà không lộ dữ liệu

Tạo một bảng unique demo, chèn giá trị giả rồi thử trùng trong sandbox. Xác nhận:

- SQLSTATE đúng loại.
- Ứng dụng trả thông điệp an toàn.
- Log không ghi raw email/token.
- Log vẫn có correlation ID để điều tra.
- Transaction được rollback hoặc phục hồi đúng.

Không cần đưa raw value vào screenshot để chứng minh masking hoạt động; chỉ cần hiển thị đầu ra đã che và mã lỗi.

### 19.4. Kiểm thử quyền bằng account hạn chế

Một truy vấn mask chạy bằng owner không chứng minh account hỗ trợ bị chặn raw data. Hãy kết nối bằng role được cấp quyền view:

~~~sql
SELECT * FROM lab_r384.customer_support_safe;
~~~

Sau đó thử truy cập bảng gốc trong một lệnh riêng, dự kiến bị từ chối nếu không có quyền khác. Kiểm tra cả membership/PUBLIC và view security mode.

## 20. Khác biệt giữa các SQL dialect

Các hệ quản trị có cách cung cấp dynamic masking/redaction khác nhau. Không nên sao chép một tính năng hoặc cú pháp từ DBMS này sang DBMS khác.

### 20.1. PostgreSQL

PostgreSQL core không có một cú pháp dynamic data masking tổng quát kiểu MASKED WITH cho mọi cột. Các phương pháp thường dùng:

- View chỉ trả cột cần thiết và biểu thức đã che.
- Column privileges và role membership.
- RLS để giới hạn hàng.
- Function có kiểm soát quyền, với SECURITY INVOKER hoặc SECURITY DEFINER được thiết kế an toàn.
- Dữ liệu tổng hợp/đã biến đổi cho sandbox.

Ví dụ:

~~~sql
CREATE VIEW safe_customer_output AS
SELECT
    customer_ref,
    LEFT(email, 1) || '***' AS masked_email
FROM some_schema.customers;
~~~

Ví dụ này chỉ minh họa view; cần xét NULL, định dạng, quyền owner và không cấp quyền raw table cho role chỉ được xem kết quả.

### 20.2. SQL Server

SQL Server có tính năng **Dynamic Data Masking (DDM)**, cho phép khai báo mặt nạ trên cột. Ví dụ khái niệm:

~~~sql
-- SQL Server/T-SQL minh hoa:
CREATE TABLE dbo.CustomerDemo (
    customer_id INT,
    email VARCHAR(120)
        MASKED WITH (FUNCTION = 'email()')
);
~~~

DDM biến đổi giá trị hiển thị cho các principal không có quyền xem dữ liệu chưa mask theo quy tắc SQL Server. Nó **không phải ranh giới bảo mật tuyệt đối**: người dùng vẫn có thể suy luận qua truy vấn, predicate, thống kê hoặc đường truy cập khác tùy quyền và thiết kế. Cần kết hợp GRANT/DENY, RLS khi phù hợp và bảo vệ dữ liệu nguồn.

### 20.3. Oracle Database

Oracle có **Data Redaction** để biến đổi dữ liệu trả về theo policy và ngữ cảnh, với các kiểu redaction phù hợp như che toàn bộ, một phần hoặc theo biểu thức. Cấu hình thường được quản lý qua package/chính sách Oracle như DBMS_REDACT, tùy phiên bản và quyền/edition được cấp.

Redaction ảnh hưởng dữ liệu hiển thị trong truy vấn theo policy; nó không thay thế quản lý quyền đối tượng, bảo vệ backup, log hoặc ứng dụng có quyền đặc biệt. Khi triển khai cần đọc tài liệu đúng phiên bản và kiểm tra các đường truy cập được miễn redaction.

### 20.4. MySQL

MySQL hỗ trợ biểu thức SELECT, view, quyền bảng/cột và các kỹ thuật ứng dụng để che dữ liệu. Một số sản phẩm/phiên bản hoặc thành phần thương mại cung cấp công cụ **Data Masking and De-Identification**; không giả định mọi bản MySQL cài đặt đều có cùng tính năng hoặc cú pháp dynamic masking.

Ví dụ portable ở cấp truy vấn:

~~~sql
-- MySQL minh hoa:
SELECT
    customer_ref,
    CONCAT(LEFT(email, 1), '***') AS masked_email
FROM customers;
~~~

Biểu thức này chỉ che trong kết quả câu SELECT; nếu caller có quyền đọc email, họ có thể truy vấn raw column bằng câu khác. Dùng view và quyền giới hạn khi cần kiểm soát ở database.

### 20.5. SQLite

SQLite không có hệ thống role/grant server-side hoặc dynamic masking native tương đương các tính năng trên. Có thể:

- Dùng truy vấn/view trả cột đã che.
- Dùng dữ liệu giả cho sandbox.
- Thực hiện authorization và redaction ở tầng ứng dụng.
- Bảo vệ file database bằng quyền hệ điều hành, mã hóa theo giải pháp phù hợp và kiểm soát backup.

Nếu người dùng có quyền đọc trực tiếp file SQLite, một lớp che chỉ tồn tại trong UI có thể bị bỏ qua bằng công cụ khác. Phân quyền ứng dụng phải đi cùng kiểm soát file.

### 20.6. Bảng so sánh

| Khả năng | PostgreSQL | SQL Server | Oracle | MySQL | SQLite |
| --- | --- | --- | --- | --- | --- |
| Mask bằng biểu thức SELECT | Có | Có | Có | Có | Có |
| View chỉ trả dữ liệu đã che | Có | Có | Có | Có | Có |
| Dynamic masking/redaction native chuyên biệt | Không có cú pháp core tổng quát tương đương DDM | Có DDM | Có Data Redaction | Tùy sản phẩm/thành phần/phiên bản | Không có tính năng server-side tương đương |
| Quyền cột | Có | Có | Có | Có | Không có GRANT server-side |
| Row filtering | RLS | RLS policy | VPD/các cơ chế policy | Thiết kế theo phiên bản/giải pháp | Thường tại ứng dụng |
| Kiểm soát error output | SQLSTATE, RAISE, application mapping | TRY/CATCH, error number/state | Exception handling PL/SQL | SQL exception handler | Chủ yếu qua API/app |

## 21. Những lỗi thường gặp

| Cách làm hoặc suy luận | Rủi ro | Cách sửa |
| --- | --- | --- |
| SELECT * trong bài thực hành | Lấy cả cột nhạy cảm ngoài mục tiêu | Liệt kê cột cần thiết |
| Chỉ che screenshot sau khi query raw | Raw data vẫn ở result history, clipboard hoặc file | Che ở query/view hoặc dùng dữ liệu giả từ đầu |
| Mask email nhưng giữ tên miền nhạy cảm | Có thể nhận diện tổ chức/người dùng | Cân nhắc [masked-email] hoặc bỏ cả domain |
| Giữ ID tăng tuần tự và gọi dữ liệu anonymous | Có thể liên kết/ngược suy ra người thật | Token ngẫu nhiên, đánh giá khả năng liên kết |
| Hash trực tiếp email/số điện thoại | Có thể dò từ điển | Tokenization/HMAC có quản lý khóa hoặc dữ liệu tổng hợp |
| Nghĩ encryption at rest làm kết quả tự che | User có quyền SELECT vẫn nhận plaintext | View, privileges, RLS, masking |
| Function mask nhưng cấp SELECT raw column | Người dùng bỏ function và đọc raw | Không cấp quyền bảng/cột gốc |
| View che nhưng dùng SELECT * | Cột mới nhạy cảm có thể xuất hiện khi view được sửa | Liệt kê cột và review thay đổi schema |
| Chỉ dùng RLS để che cột | RLS giới hạn hàng, không biến đổi giá trị cột | Kết hợp view/column grants |
| Chỉ dùng masking để giới hạn tenant | Masking không lọc hàng | RLS hoặc cơ chế hàng phù hợp |
| Đưa email/token vào RAISE EXCEPTION | Lộ trong response/log | Message chung, SQLSTATE |
| Đưa raw exception vào HTTP response | Lộ constraint, SQL, schema, giá trị | Error mapper và correlation ID |
| Ghi MESSAGE_TEXT, DETAIL, CONTEXT vào log tự động | Có thể chứa dữ liệu gốc | Chọn trường log có chủ đích |
| Dùng WHEN OTHERS THEN RETURN NULL | Che cả lỗi lập trình và permission | Bắt lỗi dự kiến, log an toàn, ném lại/ánh xạ đúng |
| Ghi toàn bộ SQL bind parameters | Lộ PII và credential | Rà cấu hình log, lọc trường, parameterization |
| Dùng prepared statement rồi cho rằng log không thể lộ | APM/driver/database vẫn có thể ghi bind values | Kiểm tra toàn pipeline |
| Bật log statement ALL mà không rà dữ liệu | Log có thể chứa literal | Chính sách log và quyền truy cập |
| Cho account hỗ trợ đọc mọi DB stats | Có thể nhìn query text của phiên khác | Cấp quyền thống kê đúng nhu cầu |
| Masking sau khi dump đã chuyển ra QA | File dump/tạm đã chứa raw | Mask trước khi dữ liệu rời vùng bảo vệ |
| Dùng dữ liệu đã che cho mọi test | Unique/join/distribution có thể bị phá | Synthetic fixtures theo mục tiêu |
| Coi token là dữ liệu ẩn danh | Có thể liên kết hoặc khôi phục qua vault | Bảo vệ mapping/key và đánh giá linkability |
| Trả lỗi email đã tồn tại trong luồng reset | User enumeration | Thông điệp chung và rate limiting |
| Che giá trị nhưng giữ timestamp/đơn hiếm | Có thể suy ra người từ dữ liệu phụ | Tổng hợp, làm thô thời gian, suppression |
| Dùng RETURNING * | Trả mọi cột của hàng | Chỉ RETURNING cột caller cần |
| Không kiểm thử role thật | Owner có thể thấy nhiều hơn account runtime | Test bằng account hạn chế |

## 22. Bài tập thực hành có đáp án

Các bài dựa trên schema lab_r384 và function đã tạo. Dữ liệu trong bài là dữ liệu giả. Những câu có ghi **dự kiến lỗi** cần chạy riêng trong sandbox; nếu transaction bị aborted, chạy ROLLBACK trước khi tiếp tục.

### Bài 1 — Nhận diện nơi lộ dữ liệu

**Tình huống:** một bài thực hành chỉ cần hiển thị trạng thái đơn nhưng dùng:

~~~sql
SELECT *
FROM lab_r384.customers;
~~~

**Câu hỏi:** vì sao không phù hợp?

**Đáp án:** truy vấn trả cả email, phone, tax_id, internal_note và các cột khác không cần cho mục tiêu. Liệt kê cột cần dùng, dùng dữ liệu giả hoặc view đã che; không chỉ chụp screenshot rồi che thủ công.

### Bài 2 — Che email trong SELECT

**Yêu cầu:** hiển thị customer_ref và email đã che bằng function.

**Đáp án:**

~~~sql
SELECT
    customer_ref,
    lab_r384.mask_email(email) AS email_display
FROM lab_r384.customers
ORDER BY customer_ref;
~~~

### Bài 3 — Che điện thoại

**Yêu cầu:** chỉ giữ bốn số cuối sau khi bỏ dấu cách và dấu cộng.

**Đáp án:**

~~~sql
SELECT
    customer_ref,
    lab_r384.mask_phone(phone) AS phone_display
FROM lab_r384.customers;
~~~

Hàm chuẩn hóa về chữ số trước rồi mới che. Cần kiểm thử thêm số ngắn, NULL và định dạng có extension.

### Bài 4 — Chỉ cần biết email có tồn tại

**Yêu cầu:** không trả email, chỉ trả cờ boolean.

**Đáp án:**

~~~sql
SELECT
    customer_ref,
    email IS NOT NULL AS has_email
FROM lab_r384.customers;
~~~

Không nên lấy email raw rồi che nếu nhu cầu chỉ là kiểm tra NULL.

### Bài 5 — Che theo nhóm giá trị

**Yêu cầu:** nhóm tổng tiền đơn theo ba khoảng dưới 100000, 100000–199999, từ 200000.

**Đáp án:**

~~~sql
SELECT
    CASE
        WHEN total_amount < 100000 THEN 'Under 100K'
        WHEN total_amount < 200000 THEN '100K-199K'
        ELSE '200K and above'
    END AS amount_band,
    COUNT(*) AS order_count
FROM lab_r384.orders
GROUP BY 1;
~~~

Kết quả giảm độ chi tiết so với từng số tiền. Nhóm quá ít hàng vẫn có nguy cơ suy luận.

### Bài 6 — Masking có ngăn đọc raw column không?

**Tình huống:** role được cấp SELECT trên bảng customers, và query dùng mask_email(email).

**Đáp án:** **không**. Caller có thể chạy SELECT email nếu vẫn có quyền raw. Cần view/column grants và thu hồi quyền truy cập cột gốc.

### Bài 7 — Tạo view chỉ trả dữ liệu đã che

**Yêu cầu:** view cho nhóm hỗ trợ cần customer_ref, masked_email và masked_phone.

**Đáp án:**

~~~sql
CREATE VIEW lab_r384.support_contact_safe AS
SELECT
    customer_ref,
    lab_r384.mask_email(email) AS masked_email,
    lab_r384.mask_phone(phone) AS masked_phone
FROM lab_r384.customers;
~~~

Sau đó cấp USAGE schema và SELECT view cho role phù hợp; không cấp SELECT bảng nền nếu muốn view là đường đọc duy nhất.

### Bài 8 — Tại sao không hiển thị tax_id?

**Tình huống:** nhân viên chỉ cần kiểm tra email liên hệ. View hiện cả tax_id đã thay một phần.

**Đáp án:** nếu không cần tax_id, **bỏ cột hoàn toàn**. Masking không phải lý do để giữ mọi cột trong output.

### Bài 9 — Thông báo lỗi an toàn

**Yêu cầu:** thay câu lỗi in email:

~~~sql
-- KHONG DUNG:
RAISE EXCEPTION 'Email % already exists', p_email;
~~~

**Đáp án:**

~~~sql
RAISE EXCEPTION USING
    ERRCODE = 'PZ001',
    MESSAGE = 'Request could not be completed';
~~~

Không đưa email vào MESSAGE, DETAIL hoặc HINT.

### Bài 10 — SQLSTATE của unique violation

**Câu hỏi:** PostgreSQL dùng SQLSTATE nào cho unique_violation?

**Đáp án:** 23505. Ứng dụng nên dựa vào SQLSTATE/mã lỗi có cấu trúc, không parse chuỗi message để xác định lỗi.

### Bài 11 — Lỗi trùng có thể lộ gì?

**Tình huống:** hai bản ghi có cùng email; database trả DETAIL với giá trị key.

**Đáp án:** raw email có thể xuất hiện trong error response hoặc log. Không tắt UNIQUE constraint; hãy ánh xạ lỗi ở API, giới hạn log và không gửi DETAIL cho người dùng cuối.

### Bài 12 — GET STACKED DIAGNOSTICS

**Yêu cầu:** lấy SQLSTATE của exception vừa bắt.

**Đáp án:**

~~~sql
GET STACKED DIAGNOSTICS
    v_sqlstate = RETURNED_SQLSTATE;
~~~

Không mặc định log MESSAGE_TEXT, PG_EXCEPTION_DETAIL hoặc PG_EXCEPTION_CONTEXT, vì chúng có thể chứa dữ liệu nhạy cảm.

### Bài 13 — RAISE; hay exception mới?

**Câu hỏi:** trong handler, RAISE; có thể trả thông báo gốc chứa raw data ra client không?

**Đáp án:** **có**. RAISE; ném lại exception ban đầu. Nếu cần response an toàn, lưu diagnostics nội bộ được kiểm soát rồi ánh xạ sang exception/message chung ở ranh giới phù hợp.

### Bài 14 — Prepared statement có đủ không?

**Tình huống:** ứng dụng dùng bind parameter, nhưng database log đang ghi giá trị tham số khi query lỗi.

**Đáp án:** prepared statement giảm SQL injection và tách data khỏi cú pháp, nhưng **không tự đảm bảo log không ghi bind values**. Rà cấu hình driver, database, APM và chính sách log.

### Bài 15 — Masking và RLS

**Câu hỏi:** RLS chỉ cho tenant A đọc hàng của A. Email trong những hàng đó có tự được che không?

**Đáp án:** **không**. RLS lọc hàng; masking/view/column privileges kiểm soát cột hoặc giá trị. Cần kết hợp theo mục tiêu.

### Bài 16 — Encryption khác masking

**Câu hỏi:** bảng được mã hóa khi lưu trữ, account có SELECT email. Query có thể trả email rõ không?

**Đáp án:** **có**. Encryption at rest không tự thay đổi kết quả truy vấn đã được cấp quyền. Muốn che output cần lớp phân quyền hoặc masking.

### Bài 17 — Hash email có ẩn danh không?

**Câu hỏi:** xuất SHA256(email) rồi coi dữ liệu hoàn toàn vô danh có đúng không?

**Đáp án:** **không**. Email có thể dò từ danh sách ứng viên. Hash không khóa không phải tokenization an toàn; cần đánh giá HMAC/khóa bí mật, linkability và nguy cơ suy luận.

### Bài 18 — API response

**Yêu cầu:** chọn response an toàn hơn khi lỗi database.

**Đáp án:** trả mã lỗi nghiệp vụ và correlation ID, ví dụ REQUEST_COULD_NOT_BE_COMPLETED, không trả raw SQL, DETAIL, stack trace hoặc email trong key trùng.

### Bài 19 — User enumeration

**Tình huống:** endpoint reset password trả “email không tồn tại” và “email đã đăng ký” khác nhau.

**Đáp án:** có thể giúp kẻ tấn công dò danh sách tài khoản. Cân nhắc thông điệp chung, rate limiting, giám sát và xác minh theo quy trình.

### Bài 20 — Masking tĩnh trước khi chia sẻ

**Câu hỏi:** có nên export raw database sang QA rồi mới chạy script mask không?

**Đáp án:** không nếu file dump, bản sao tạm hoặc log đã rời vùng bảo vệ. Thiết kế bước biến đổi **trước khi dữ liệu được chuyển** sang môi trường ít kiểm soát hơn; ưu tiên dữ liệu tổng hợp.

### Bài 21 — RETURNING

**Yêu cầu:** sau INSERT đơn hàng, ứng dụng chỉ cần ID và trạng thái. Có nên dùng RETURNING * không?

**Đáp án:** không. Dùng:

~~~sql
RETURNING order_id, order_status;
~~~

Chỉ trả cột cần thiết.

### Bài 22 — Kiểm thử bằng owner

**Tình huống:** view hoạt động khi chạy bằng owner. Có thể kết luận role hỗ trợ chỉ thấy dữ liệu đã che không?

**Đáp án:** **không**. Owner có quyền khác role hỗ trợ và có thể đọc bảng gốc. Cần kết nối hoặc SET ROLE hợp lệ sang account/role bị hạn chế, kiểm thử view thành công và raw table bị từ chối.

### Bài 23 — Log stack trace

**Câu hỏi:** stack trace có thể chứa thông tin nào ngoài tên class?

**Đáp án:** có thể chứa SQL, tên schema/bảng/cột, file, giá trị tham số trong exception message và đường dẫn nội bộ. Chỉ lưu ở kênh nội bộ có kiểm soát, lọc dữ liệu và không trả cho người dùng cuối.

### Bài 24 — Chọn phương pháp cho bài học

**Yêu cầu:** cần viết tutorial có kết quả tái tạo được và chia sẻ công khai. Nên chọn raw production đã mask hay synthetic fixture?

**Đáp án:** ưu tiên **synthetic fixture** có cấu trúc và tình huống tương tự. Nếu buộc dùng bản sao, phải đánh giá re-identification, token, liên kết, log, backup và quy trình masking trước khi chia sẻ.

## 23. Checklist trước khi chia sẻ kết quả thực hành

- [ ] Dữ liệu là synthetic hoặc đã được phê duyệt để sử dụng.
- [ ] Truy vấn liệt kê cột cụ thể; không dùng SELECT * tùy tiện.
- [ ] Không có email, số điện thoại, mã định danh hoặc ghi chú raw ngoài mục tiêu.
- [ ] RETURNING chỉ trả các cột cần thiết.
- [ ] Kết quả, CSV, screenshot, notebook và query history đều được xem xét.
- [ ] Thông báo lỗi không chứa raw input, token, mật khẩu hoặc DETAIL nhạy cảm.
- [ ] API không trả stack trace/SQL text/constraint detail cho người dùng cuối.
- [ ] Log, APM và pg_stat_activity được kiểm soát quyền và cấu hình.
- [ ] View/role/RLS được thử bằng account hạn chế, không chỉ owner.
- [ ] Các token/mã giả không bị coi nhầm là ẩn danh hoàn toàn.
- [ ] File tạm, bản dump và bản export được xử lý theo quy trình.
- [ ] Có correlation ID hoặc mã sự cố để điều tra mà không cần ghi PII.

## 24. Ghi nhớ

| Câu hỏi | Nguyên tắc |
| --- | --- |
| Masking có đồng nghĩa anonymization? | **Không**; giá trị đã che vẫn có thể liên kết/nhận diện |
| SELECT biểu thức mask có chặn đọc raw không? | **Không**, nếu caller vẫn có quyền cột gốc |
| Cách tạo giao diện đầu ra hẹp? | View/function được kiểm soát cùng column privileges |
| RLS che giá trị cột không? | **Không**; RLS giới hạn hàng |
| Dữ liệu dùng cho tutorial nên lấy ở đâu? | Ưu tiên **synthetic fixtures** |
| Encryption at rest có làm query tự mask? | **Không** |
| Hash email có an toàn để ẩn danh? | Không mặc định; giá trị dễ dò và vẫn linkable |
| Lỗi database có thể lộ PII? | Có, nhất là DETAIL của constraint và exception message |
| Có nên trả RAISE nguyên bản cho API? | Không nếu message/context có thể lộ dữ liệu; ánh xạ ở ranh giới an toàn |
| SQLSTATE dùng làm gì? | Mã kỹ thuật ổn định để phân loại lỗi |
| GET STACKED DIAGNOSTICS có nên log hết? | Không; chọn trường, tránh raw message/detail/context |
| Prepared statement có bảo vệ log? | Không tự động; phải rà driver/database/APM |
| RETURNING * có an toàn? | Không mặc định; chỉ trả cột cần |
| View masking có cần kiểm thử quyền? | Có; test bằng role thật bị giới hạn |
| Masking tĩnh nên chạy lúc nào? | Trước khi dữ liệu rời vùng bảo vệ |
| Error response nên có gì? | Mã lỗi an toàn, thông điệp vừa đủ, correlation ID |

**Điểm cốt lõi:** kết quả truy vấn và thông báo lỗi đều là **đường xuất dữ liệu**. Hãy giảm lượng thông tin ngay từ query/view/API, dùng dữ liệu tổng hợp cho bài thực hành, không đưa giá trị nhạy cảm vào exception hoặc log, và kiểm thử bằng đúng role sẽ nhận kết quả. Masking chỉ là một lớp; nó cần đi cùng **least privilege, kiểm soát hàng/cột, parameterized SQL, quản lý log và thiết kế lỗi an toàn** để giảm nguy cơ dữ liệu bị lộ trong quá trình phát triển, kiểm thử và vận hành.
