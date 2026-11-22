# Giá trị mặc định, cột sinh tự động và cột bỏ qua trong INSERT

Khi thêm một hàng vào MySQL, ứng dụng không nhất thiết phải cung cấp giá trị cho mọi cột. Một số cột có thể nhận giá trị mặc định, một số được MySQL cấp số tự tăng, và một số được tính từ các cột khác. Hiểu đúng các cơ chế này giúp câu lệnh INSERT ngắn gọn, bảo đảm dữ liệu nhất quán và tránh nhầm lẫn giữa “không truyền giá trị”, “truyền NULL” và “yêu cầu dùng DEFAULT”.

Trong MySQL có ba khái niệm cần phân biệt:

- **DEFAULT**: giá trị được dùng khi cột bị bỏ qua trong INSERT hoặc được chỉ định rõ bằng từ khóa DEFAULT.
- **AUTO_INCREMENT**: cơ chế cấp giá trị số tự tăng, thường dùng làm định danh hàng.
- **Generated column**: cột được tính từ biểu thức dựa trên các cột khác của cùng hàng; người dùng không tự gán giá trị tùy ý cho cột này.

Ngoài ra, một cột có thể bị bỏ qua trong danh sách INSERT. Khi đó MySQL áp dụng quy tắc mặc định theo định nghĩa cột và SQL mode hiện hành. Bài học này giải thích từng trường hợp, cách kiểm tra kết quả và những lỗi thường gặp khi nhập dữ liệu.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Khai báo DEFAULT literal và DEFAULT expression trong MySQL.
- Phân biệt bỏ qua cột, chỉ định DEFAULT và truyền NULL.
- Giải thích ảnh hưởng của NOT NULL và strict SQL mode khi thiếu giá trị.
- Dùng AUTO_INCREMENT và lấy ID vừa sinh trong cùng connection.
- Phân biệt AUTO_INCREMENT với generated column.
- Khai báo generated column ở dạng VIRTUAL hoặc STORED.
- Bỏ qua generated column trong INSERT và hiểu giới hạn khi cố gán giá trị.
- Dùng DEFAULT trong INSERT nhiều hàng, INSERT ... SET và INSERT ... SELECT.
- Hiểu DEFAULT và ON UPDATE CURRENT_TIMESTAMP có vai trò khác nhau.
- Kiểm tra schema, giá trị mặc định và dữ liệu thực tế trước khi triển khai.

## 1. Chuẩn bị bảng thực hành

Bảng dưới đây mô phỏng dòng hàng của một đơn đặt hàng. Mỗi dòng có mã tự tăng, số lượng mặc định là 1, trạng thái mặc định là NEW, thời điểm tạo tự động và thành tiền được tính từ số lượng nhân đơn giá.

    CREATE TABLE order_line_default_demo (
        line_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        order_code VARCHAR(30) NOT NULL,
        quantity INT UNSIGNED NOT NULL DEFAULT 1,
        unit_price DECIMAL(12,2) NOT NULL,
        line_total DECIMAL(14,2)
            GENERATED ALWAYS AS (quantity * unit_price) STORED,
        line_status VARCHAR(20) NOT NULL DEFAULT 'NEW',
        note VARCHAR(200) NULL DEFAULT NULL,
        created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        updated_at DATETIME(6) NOT NULL
            DEFAULT CURRENT_TIMESTAMP(6)
            ON UPDATE CURRENT_TIMESTAMP(6),
        PRIMARY KEY (line_id),
        UNIQUE KEY uq_order_line_default_order_code (order_code)
    ) ENGINE = InnoDB;

Trong bảng này:

- line_id được cấp tự động bởi AUTO_INCREMENT.
- quantity dùng 1 nếu INSERT không cung cấp giá trị.
- unit_price bắt buộc phải có vì NOT NULL và không có DEFAULT.
- line_total do MySQL tính từ quantity và unit_price.
- line_status dùng NEW nếu bị bỏ qua.
- note cho phép NULL và có DEFAULT NULL.
- created_at nhận thời điểm insert.
- updated_at nhận thời điểm insert và tự cập nhật khi hàng thay đổi theo quy tắc ON UPDATE.

Kiểm tra định nghĩa bảng:

    SHOW CREATE TABLE order_line_default_demo;

Có thể xem metadata của các cột:

    SHOW COLUMNS FROM order_line_default_demo;

## 2. Bỏ qua cột trong INSERT

Khi câu lệnh INSERT có danh sách cột, các cột không được liệt kê sẽ không nhận giá trị từ câu lệnh. MySQL sẽ áp dụng giá trị mặc định hoặc quy tắc sinh giá trị của từng cột.

Ví dụ:

    INSERT INTO order_line_default_demo
        (order_code, unit_price)
    VALUES
        ('ORD-001', 25.00);

Ứng dụng chỉ gửi order_code và unit_price. MySQL xử lý các cột còn lại:

| Cột | Kết quả |
|---|---|
| line_id | Cấp giá trị AUTO_INCREMENT |
| order_code | ORD-001 |
| quantity | 1 theo DEFAULT |
| unit_price | 25.00 từ INSERT |
| line_total | 25.00 do generated expression tính |
| line_status | NEW theo DEFAULT |
| note | NULL theo DEFAULT |
| created_at | Thời điểm insert |
| updated_at | Thời điểm insert |

Kiểm tra:

    SELECT
        line_id,
        order_code,
        quantity,
        unit_price,
        line_total,
        line_status,
        note,
        created_at,
        updated_at
    FROM order_line_default_demo;

Điểm quan trọng: bỏ qua một cột không có nghĩa là MySQL luôn tự chọn một giá trị hợp lệ theo ý nghiệp vụ. Kết quả phụ thuộc vào định nghĩa cột, loại cột, ràng buộc và SQL mode.

### 2.1. Vì sao nên viết danh sách cột?

Nên dùng:

    INSERT INTO order_line_default_demo
        (order_code, unit_price)
    VALUES
        ('ORD-002', 18.50);

Hạn chế dùng INSERT không có danh sách cột:

    INSERT INTO order_line_default_demo
    VALUES (DEFAULT, 'ORD-003', DEFAULT, 18.50, DEFAULT,
            DEFAULT, DEFAULT, DEFAULT, DEFAULT);

Khi không ghi danh sách cột, người viết phải cung cấp giá trị theo thứ tự toàn bộ cột của bảng. Việc thêm, xóa hoặc sắp xếp lại cột có thể làm câu lệnh cũ sai hoặc gán dữ liệu nhầm vị trí. Generated column cũng cần được xử lý theo đúng vị trí nếu câu lệnh không có danh sách cột.

Với ứng dụng, migration và script import, danh sách cột tường minh giúp câu lệnh bền vững hơn trước thay đổi schema.

## 3. Bỏ qua cột, DEFAULT và NULL không giống nhau

Ba cách dưới đây có ý nghĩa khác nhau:

    -- Bỏ qua note
    INSERT INTO order_line_default_demo (order_code, unit_price)
    VALUES ('ORD-010', 12.00);

    -- Yêu cầu MySQL dùng default của note
    INSERT INTO order_line_default_demo (order_code, unit_price, note)
    VALUES ('ORD-011', 12.00, DEFAULT);

    -- Truyền NULL một cách tường minh
    INSERT INTO order_line_default_demo (order_code, unit_price, note)
    VALUES ('ORD-012', 12.00, NULL);

Trong bảng mẫu, note cho phép NULL và có DEFAULT NULL nên cả ba cách đều cho kết quả note là NULL. Tuy nhiên, chúng không phải cùng một quy tắc:

- Bỏ qua cột: MySQL áp dụng default theo định nghĩa cột.
- DEFAULT: yêu cầu dùng giá trị mặc định của cột ngay tại vị trí đó.
- NULL: gửi một giá trị NULL tường minh; không yêu cầu MySQL thay bằng default khác.

Sự khác biệt rõ hơn với cột NOT NULL có default:

    INSERT INTO order_line_default_demo
        (order_code, unit_price, line_status)
    VALUES
        ('ORD-013', 10.00, DEFAULT);

line_status nhận NEW. Nhưng:

    INSERT INTO order_line_default_demo
        (order_code, unit_price, line_status)
    VALUES
        ('ORD-014', 10.00, NULL);

thất bại trong strict SQL mode vì line_status khai báo NOT NULL. DEFAULT không đồng nghĩa với NULL và NULL không tự kích hoạt giá trị DEFAULT.

### 3.1. Cột nullable bị bỏ qua

Nếu cột cho phép NULL và không khai báo DEFAULT riêng, MySQL dùng NULL làm giá trị mặc định ngầm định khi cột bị bỏ qua.

    CREATE TABLE nullable_default_demo (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        optional_text VARCHAR(100) NULL,
        PRIMARY KEY (id)
    ) ENGINE = InnoDB;

    INSERT INTO nullable_default_demo () VALUES ();

Hàng mới có optional_text là NULL. Có thể viết rõ định nghĩa để người đọc schema hiểu chủ ý:

    optional_text VARCHAR(100) NULL DEFAULT NULL

Khai báo DEFAULT NULL là tường minh, nhưng với cột nullable không có default khác thì NULL cũng là giá trị mặc định ngầm định.

### 3.2. Cột NOT NULL không có DEFAULT

Nếu cột NOT NULL không có DEFAULT và không phải cột tự sinh như AUTO_INCREMENT hoặc generated column, ứng dụng phải cung cấp giá trị khi INSERT.

Ví dụ unit_price trong bảng thực hành:

    INSERT INTO order_line_default_demo (order_code)
    VALUES ('ORD-MISSING-PRICE');

Trong strict SQL mode, câu lệnh bị từ chối vì unit_price không có giá trị mặc định và không được cung cấp. Đây là hành vi nên mong muốn đối với dữ liệu bắt buộc: lỗi được phát hiện ngay thay vì âm thầm lưu một giá trị không có ý nghĩa.

## 4. SQL mode và implicit default

Hành vi khi bỏ qua cột NOT NULL không có DEFAULT còn phụ thuộc SQL mode.

Trong MySQL 8.0, strict mode thường được bật mặc định. Với bảng transactional như InnoDB, khi INSERT thiếu giá trị cho cột NOT NULL không có DEFAULT, MySQL báo lỗi thay vì tự chèn giá trị ngầm định.

Kiểm tra SQL mode của session:

    SELECT @@SESSION.sql_mode;

Kiểm tra thêm global mode:

    SELECT @@GLOBAL.sql_mode;

Các mode strict thường gặp là STRICT_TRANS_TABLES và STRICT_ALL_TABLES.

Nếu strict mode bị tắt, MySQL có thể dùng implicit default theo kiểu dữ liệu và phát warning khi thiếu giá trị bắt buộc. Ví dụ, giá trị ngầm định có thể là 0 cho kiểu số, chuỗi rỗng cho kiểu chuỗi hoặc giá trị zero date tùy kiểu và các SQL mode liên quan. Không nên dựa vào hành vi này để thiết kế ứng dụng.

| Định nghĩa cột | Khi bỏ qua trong INSERT |
|---|---|
| Có DEFAULT literal hoặc expression | Dùng giá trị DEFAULT |
| Nullable, không khai báo DEFAULT khác | Dùng NULL |
| AUTO_INCREMENT | Cấp giá trị tự tăng |
| Generated column | MySQL tính từ biểu thức |
| NOT NULL, không DEFAULT, strict mode | Thường báo lỗi với InnoDB |
| NOT NULL, không DEFAULT, non-strict mode | Có thể dùng implicit type default và phát warning |

Nếu chạy thử trên môi trường non-strict, hãy kiểm tra warning ngay sau INSERT:

    SHOW WARNINGS;

Không tắt strict mode chỉ để một câu INSERT thiếu dữ liệu chạy được. Hãy sửa danh sách cột hoặc định nghĩa DEFAULT theo quy tắc nghiệp vụ. Implicit default có thể làm dữ liệu sai nhưng trông vẫn hợp lệ về mặt kiểu.

## 5. Khai báo DEFAULT literal

DEFAULT literal là giá trị cố định được khai báo trong định nghĩa cột:

    CREATE TABLE account_preference_demo (
        account_id BIGINT UNSIGNED NOT NULL,
        language_code VARCHAR(10) NOT NULL DEFAULT 'vi',
        page_size INT UNSIGNED NOT NULL DEFAULT 20,
        is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
        time_zone VARCHAR(64) NULL DEFAULT 'Asia/Ho_Chi_Minh',
        PRIMARY KEY (account_id)
    ) ENGINE = InnoDB;

Khi bỏ qua các cột có default:

    INSERT INTO account_preference_demo (account_id)
    VALUES (1001);

MySQL tạo hàng với language_code = 'vi', page_size = 20, is_enabled = TRUE và time_zone = 'Asia/Ho_Chi_Minh'.

DEFAULT nên phản ánh một quy tắc nghiệp vụ ổn định, chẳng hạn ngôn ngữ mặc định, trạng thái ban đầu hoặc số lượng mặc định. Không dùng default tùy tiện chỉ để tránh lỗi thiếu dữ liệu.

### 5.1. DEFAULT với các kiểu dữ liệu

Giá trị mặc định phải tương thích với kiểu dữ liệu và ràng buộc của cột:

    CREATE TABLE typed_default_demo (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        display_name VARCHAR(100) NOT NULL DEFAULT '',
        retry_count INT UNSIGNED NOT NULL DEFAULT 0,
        amount DECIMAL(12,2) NOT NULL DEFAULT 0.00,
        is_active TINYINT(1) NOT NULL DEFAULT 1,
        metadata JSON NULL DEFAULT NULL,
        PRIMARY KEY (id)
    ) ENGINE = InnoDB;

Không nên dùng 0 hoặc chuỗi rỗng để đại diện cho “chưa biết” nếu nghiệp vụ cần phân biệt trạng thái chưa có dữ liệu. Trong trường hợp đó, NULL hoặc một trạng thái riêng có thể chính xác hơn.

## 6. DEFAULT expression

Từ MySQL 8.0.13, có thể khai báo biểu thức làm giá trị mặc định cho nhiều kiểu cột. Biểu thức phải được đặt trong dấu ngoặc đơn để phân biệt với literal mặc định.

Ví dụ tạo thời điểm nhắc việc sau thời điểm hiện tại hai ngày:

    CREATE TABLE reminder_default_demo (
        reminder_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        title VARCHAR(150) NOT NULL,
        created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        remind_at DATETIME(6) NOT NULL
            DEFAULT (CURRENT_TIMESTAMP(6) + INTERVAL 2 DAY),
        PRIMARY KEY (reminder_id)
    ) ENGINE = InnoDB;

created_at dùng cú pháp temporal default đặc biệt CURRENT_TIMESTAMP(6). remind_at dùng một biểu thức tính toán nên được đặt trong ngoặc:

    DEFAULT (CURRENT_TIMESTAMP(6) + INTERVAL 2 DAY)

Khi INSERT:

    INSERT INTO reminder_default_demo (title)
    VALUES ('Kiểm tra đơn hàng');

MySQL tự tạo created_at và remind_at theo thời điểm insert.

### 6.1. Biểu thức mặc định được tính khi nào?

Biểu thức mặc định được áp dụng khi INSERT bỏ qua cột hoặc chỉ định DEFAULT. Giá trị được tạo cho hàng được insert tại thời điểm đó; nó không phải một biểu thức được tính lại mỗi lần SELECT.

Nếu muốn một cột thay đổi theo thời gian mỗi khi hàng được đọc, DEFAULT không phải cơ chế phù hợp. Hãy tính giá trị trong truy vấn hoặc ứng dụng. Nếu muốn cột được cập nhật tự động khi hàng thay đổi, xem quy tắc ON UPDATE CURRENT_TIMESTAMP ở phần sau.

### 6.2. Giới hạn của DEFAULT expression

Default expression có các giới hạn. Không thể dùng nó như một biểu thức tham chiếu tùy ý đến cột khác trong cùng hàng. Ví dụ, không thể dùng DEFAULT để tính thành tiền từ quantity và unit_price:

    -- Ý tưởng không phù hợp cho DEFAULT:
    -- line_total DECIMAL(14,2) DEFAULT (quantity * unit_price)

Nếu giá trị cần được tính từ các cột khác của cùng hàng, hãy dùng generated column:

    line_total DECIMAL(14,2)
        GENERATED ALWAYS AS (quantity * unit_price) STORED

Default expression cũng bị giới hạn về loại biểu thức được phép; không thể đưa subquery, parameter, biến hoặc stored function tùy ý vào default. Hãy kiểm tra tài liệu đúng phiên bản MySQL và thử CREATE TABLE trên phiên bản triển khai trước khi dùng biểu thức phức tạp.

### 6.3. Khả năng tương thích phiên bản

DEFAULT expression được hỗ trợ từ MySQL 8.0.13. Nếu ứng dụng cần chạy trên MySQL 5.7 hoặc các phiên bản cũ hơn, không giả định cú pháp biểu thức mặc định sẽ hoạt động. Hãy kiểm tra phiên bản server:

    SELECT VERSION();

Với hệ thống có nhiều môi trường, migration phải được kiểm tra trên đúng phiên bản MySQL của môi trường thấp nhất được hỗ trợ.

## 7. DEFAULT trong câu lệnh INSERT

Có thể yêu cầu dùng giá trị mặc định cho một cột bằng từ khóa DEFAULT:

    INSERT INTO order_line_default_demo
        (order_code, quantity, unit_price, line_status)
    VALUES
        ('ORD-020', DEFAULT, 30.00, DEFAULT);

quantity nhận 1 và line_status nhận NEW.

Nếu bỏ qua cả cột, kết quả mặc định cũng được áp dụng:

    INSERT INTO order_line_default_demo
        (order_code, unit_price)
    VALUES
        ('ORD-021', 30.00);

DEFAULT hữu ích khi câu INSERT được sinh động và cần biểu đạt rõ rằng một cột phải dùng default, hoặc khi một câu lệnh nhiều hàng có những hàng cần dùng giá trị mặc định ở vị trí cụ thể.

### 7.1. DEFAULT trong INSERT nhiều hàng

Mỗi hàng có thể dùng DEFAULT ở vị trí tương ứng:

    INSERT INTO order_line_default_demo
        (order_code, quantity, unit_price, line_status)
    VALUES
        ('ORD-030', DEFAULT, 10.00, DEFAULT),
        ('ORD-031', 3,        12.00, 'READY'),
        ('ORD-032', 5,        15.00, DEFAULT);

Hàng ORD-030 và ORD-032 dùng default quantity/status; hàng ORD-031 cung cấp giá trị cụ thể.

Nếu một cột được bỏ khỏi danh sách cột INSERT thì nó bị bỏ qua cho tất cả các hàng trong câu lệnh đó. Nếu cần giá trị khác nhau theo từng hàng, hãy liệt kê cột và dùng DEFAULT hoặc giá trị cụ thể tại từng vị trí.

### 7.2. DEFAULT trong INSERT ... SET

MySQL hỗ trợ dạng INSERT ... SET:

    INSERT INTO order_line_default_demo
    SET
        order_code = 'ORD-040',
        unit_price = 45.00,
        quantity = DEFAULT,
        line_status = DEFAULT;

Dạng này có thể dễ đọc khi chỉ insert một hàng và muốn gán từng cột bằng tên. Với nhiều hàng, INSERT ... VALUES thường gọn và phù hợp hơn.

### 7.3. DEFAULT trong INSERT ... SELECT

INSERT ... SELECT có thể dùng danh sách cột đích để chỉ rõ dữ liệu được chèn vào đâu:

    CREATE TABLE order_import_stage (
        source_code VARCHAR(30) NOT NULL,
        source_price DECIMAL(12,2) NOT NULL
    ) ENGINE = InnoDB;

    INSERT INTO order_import_stage (source_code, source_price)
    VALUES
        ('SRC-001', 11.00),
        ('SRC-002', 22.00);

    INSERT INTO order_line_default_demo (order_code, unit_price)
    SELECT source_code, source_price
    FROM order_import_stage;

Các cột khác của bảng đích tiếp tục dùng default, AUTO_INCREMENT hoặc generated expression. Số cột và thứ tự biểu thức trong SELECT phải khớp danh sách cột đích.

Nếu cần biểu thức DEFAULT rõ ràng trong danh sách SELECT, hãy kiểm tra cú pháp và ngữ cảnh phiên bản MySQL đang dùng; cách dễ bảo trì thường là chỉ liệt kê các cột nguồn cần chèn và để các cột đích còn lại được bỏ qua.

## 8. AUTO_INCREMENT: cấp ID tự động

AUTO_INCREMENT là thuộc tính của cột số nguyên, thường dùng để cấp định danh mới cho mỗi hàng. Đây không phải generated column: nó không tính giá trị từ các cột khác mà sử dụng bộ cấp số của bảng.

Ví dụ:

    CREATE TABLE support_ticket_demo (
        ticket_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        subject VARCHAR(160) NOT NULL,
        created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        PRIMARY KEY (ticket_id)
    ) ENGINE = InnoDB;

Bỏ qua ticket_id:

    INSERT INTO support_ticket_demo (subject)
    VALUES ('Không đăng nhập được');

MySQL cấp ticket_id mới. Có thể lấy ID vừa tạo trong cùng connection:

    SELECT LAST_INSERT_ID();

LAST_INSERT_ID() là giá trị gắn với connection hiện tại, phù hợp để ứng dụng lấy ID của INSERT vừa thực hiện trên cùng kết nối. Không lấy ID bằng cách SELECT MAX(ticket_id), vì một connection khác có thể insert đồng thời và làm kết quả không còn thuộc về hàng của request hiện tại.

### 8.1. Bỏ qua, NULL và 0 trong AUTO_INCREMENT

Với cột AUTO_INCREMENT:

- Bỏ qua cột hoặc truyền NULL thường yêu cầu MySQL cấp giá trị kế tiếp.
- Truyền 0 cũng thường yêu cầu cấp giá trị kế tiếp.
- Nếu bật SQL mode NO_AUTO_VALUE_ON_ZERO, giá trị 0 được lưu như giá trị tường minh thay vì yêu cầu cấp số.
- Truyền một số dương tường minh có thể được chấp nhận nếu không vi phạm khóa; bộ đếm sẽ điều chỉnh để các giá trị cấp sau không đụng giá trị đã dùng.

Ví dụ:

    INSERT INTO support_ticket_demo (subject)
    VALUES ('Ticket A');

    INSERT INTO support_ticket_demo (ticket_id, subject)
    VALUES (NULL, 'Ticket B');

Kiểm tra mode:

    SELECT @@SESSION.sql_mode;

Không dùng 0 làm một giá trị sentinel cho AUTO_INCREMENT nếu không kiểm soát NO_AUTO_VALUE_ON_ZERO. Với ứng dụng thông thường, hãy bỏ qua cột ID hoặc truyền NULL để yêu cầu cấp ID.

### 8.2. AUTO_INCREMENT không bảo đảm số liên tục

AUTO_INCREMENT cấp số duy nhất theo cơ chế của storage engine, nhưng không phải bộ đếm chứng từ liên tục không có khoảng trống. Có thể xuất hiện khoảng trống do transaction rollback, insert lỗi, thao tác xóa hoặc cấp phát số trong các tình huống đồng thời.

Không dùng:

- MAX(id) để suy ra số hàng.
- ID cuối cùng trừ ID đầu tiên để suy ra số bản ghi.
- AUTO_INCREMENT để đánh số hóa đơn pháp lý cần liên tục theo quy định.
- Giả định thứ tự ID luôn giống thứ tự commit của transaction.

Nếu nghiệp vụ cần số chứng từ liên tục hoặc có quy tắc đánh số riêng, phải thiết kế một quy trình cấp số và kiểm soát đồng thời riêng.

### 8.3. Giới hạn và thiết kế AUTO_INCREMENT

Thông thường, một bảng chỉ có một cột AUTO_INCREMENT; cột này phải được index và cần có kiểu số nguyên phù hợp. Với InnoDB, nó thường là PRIMARY KEY.

Chọn INT hay BIGINT theo quy mô và tuổi thọ bảng. Nếu ID tăng nhanh, INT có thể hết miền giá trị sớm hơn dự kiến. Kiểu của khóa ngoại tham chiếu phải tương thích với cột ID, bao gồm thuộc tính UNSIGNED.

Không thay đổi giá trị AUTO_INCREMENT tùy tiện trên production. Việc điều chỉnh bộ đếm cần được thực hiện qua DDL có kế hoạch và kiểm tra dữ liệu hiện có.

## 9. Generated column: cột được tính từ cột khác

Generated column là cột có giá trị được tính từ một biểu thức dựa trên dữ liệu của cùng hàng. Ví dụ, thành tiền có thể được tính từ số lượng và đơn giá:

    CREATE TABLE invoice_line_generated_demo (
        invoice_line_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        quantity INT UNSIGNED NOT NULL,
        unit_price DECIMAL(12,2) NOT NULL,
        line_total DECIMAL(14,2)
            GENERATED ALWAYS AS (quantity * unit_price) STORED,
        PRIMARY KEY (invoice_line_id)
    ) ENGINE = InnoDB;

Khi insert:

    INSERT INTO invoice_line_generated_demo
        (quantity, unit_price)
    VALUES
        (3, 12.50);

MySQL tính line_total = 37.50. Ứng dụng không cần tự tính và gửi lại thành tiền, tránh việc quantity/unit_price và line_total lệch nhau.

### 9.1. Không gán giá trị tùy ý cho generated column

Generated column được quản lý bởi biểu thức. Trong INSERT, có thể bỏ qua cột generated; nếu liệt kê nó, giá trị được cung cấp phải là DEFAULT:

    INSERT INTO invoice_line_generated_demo
        (quantity, unit_price, line_total)
    VALUES
        (2, 20.00, DEFAULT);

Không được cung cấp một giá trị tính toán tùy ý:

    -- Không hợp lệ: line_total được MySQL sinh ra
    INSERT INTO invoice_line_generated_demo
        (quantity, unit_price, line_total)
    VALUES
        (2, 20.00, 999.00);

Tương tự, không thể cập nhật generated column thành một giá trị tùy ý bằng UPDATE. Hãy cập nhật các cột đầu vào; MySQL tự tính lại generated value.

### 9.2. VIRTUAL và STORED

MySQL hỗ trợ hai loại generated column:

- VIRTUAL: giá trị được tính khi đọc; không lưu giá trị cột trong phần dữ liệu hàng.
- STORED: giá trị được tính khi insert/update và lưu trong hàng.

Nếu không chỉ định loại, generated column mặc định là VIRTUAL.

Ví dụ VIRTUAL:

    CREATE TABLE product_price_virtual_demo (
        product_id BIGINT UNSIGNED NOT NULL,
        unit_price DECIMAL(12,2) NOT NULL,
        tax_rate DECIMAL(5,4) NOT NULL DEFAULT 0.1000,
        price_with_tax DECIMAL(14,2)
            GENERATED ALWAYS AS (unit_price * (1 + tax_rate)) VIRTUAL,
        PRIMARY KEY (product_id)
    ) ENGINE = InnoDB;

Ví dụ STORED:

    CREATE TABLE product_price_stored_demo (
        product_id BIGINT UNSIGNED NOT NULL,
        unit_price DECIMAL(12,2) NOT NULL,
        tax_rate DECIMAL(5,4) NOT NULL DEFAULT 0.1000,
        price_with_tax DECIMAL(14,2)
            GENERATED ALWAYS AS (unit_price * (1 + tax_rate)) STORED,
        PRIMARY KEY (product_id)
    ) ENGINE = InnoDB;

| Tiêu chí | VIRTUAL | STORED |
|---|---|---|
| Lưu giá trị trong phần dữ liệu hàng | Không | Có |
| Thời điểm tính | Khi đọc giá trị | Khi insert/update hàng |
| Dung lượng hàng | Ít hơn | Tăng theo kích thước cột |
| Chi phí ghi | Không phải lưu generated value trong hàng | Phải tính và lưu khi ghi |
| Chi phí đọc | Có thể phải tính biểu thức khi đọc | Đọc giá trị đã lưu |
| Index | Có thể tạo index trên generated column | Có thể tạo index |

Chọn loại nào phụ thuộc tần suất đọc, chi phí biểu thức, dung lượng và workload. VIRTUAL không có nghĩa luôn nhanh hơn hoặc luôn chậm hơn; nếu có index trên virtual generated column, InnoDB vẫn lưu giá trị index trong secondary index để phục vụ truy vấn.

### 9.3. Generated expression phải phù hợp quy tắc

Generated expression không phải nơi chạy một đoạn chương trình tùy ý. Biểu thức bị giới hạn: không dùng subquery, biến, parameter hoặc stored/loadable function tùy ý; các hàm và phép toán phải đáp ứng quy tắc deterministic của generated column. Không dùng hàm phụ thuộc thời điểm hiện tại như NOW() để tạo generated column.

Generated column phù hợp với biểu thức ổn định từ dữ liệu cùng hàng, ví dụ:

- quantity * unit_price.
- CONCAT(first_name, ' ', last_name).
- LOWER(email) khi quy tắc chuẩn hóa email đã được xác định.
- Trích xuất một giá trị từ JSON bằng hàm được phép.

Nếu cần giá trị thay đổi theo thời gian, dữ liệu ngoài hàng hoặc kết quả truy vấn bảng khác, hãy tính ở ứng dụng, trigger hoặc quy trình cập nhật phù hợp thay vì ép vào generated column.

### 9.4. Generated column và index

Có thể tạo index trên generated column để hỗ trợ truy vấn theo giá trị đã tính:

    CREATE INDEX idx_invoice_line_total
    ON invoice_line_generated_demo (line_total);

Sau đó:

    SELECT invoice_line_id, quantity, unit_price, line_total
    FROM invoice_line_generated_demo
    WHERE line_total >= 100.00;

Index có thể giúp MySQL tìm các hàng theo generated value. Hiệu quả cần được kiểm tra bằng EXPLAIN trên dữ liệu thực tế. Một index bổ sung cũng làm tăng dung lượng và chi phí ghi.

Generated column thường hữu ích khi cùng một biểu thức được dùng lặp lại trong nhiều truy vấn và cần một điểm định nghĩa thống nhất. Không tạo generated column cho mọi biểu thức chỉ xuất hiện một lần.

## 10. Phân biệt DEFAULT, AUTO_INCREMENT và generated column

Ba cơ chế có mục đích khác nhau:

| Cơ chế | Giá trị đến từ đâu? | Ứng dụng có thể gửi giá trị riêng? | Ví dụ |
|---|---|---|---|
| DEFAULT | Giá trị cố định hoặc biểu thức mặc định của cột | Có thể cung cấp giá trị khác nếu hợp lệ | status DEFAULT 'NEW' |
| AUTO_INCREMENT | Bộ cấp số của bảng | Có thể bỏ qua/NULL để cấp tự động; có thể chèn ID tường minh nếu hợp lệ | order_id BIGINT AUTO_INCREMENT |
| Generated column | Biểu thức từ các cột cùng hàng | Không được gán giá trị tùy ý; có thể bỏ qua hoặc dùng DEFAULT | line_total = quantity * unit_price |

Ví dụ trong một INSERT:

    INSERT INTO order_line_default_demo
        (order_code, unit_price)
    VALUES
        ('ORD-050', 15.00);

line_id được cấp từ bộ AUTO_INCREMENT, quantity và line_status dùng DEFAULT, line_total được tính từ quantity và unit_price, created_at và updated_at nhận thời điểm hiện tại.

Không dùng DEFAULT để thay thế generated column nếu giá trị phải luôn phản ánh các cột nguồn. DEFAULT là giá trị áp dụng khi insert; generated column được tính theo dữ liệu hàng và được tính lại khi các cột nguồn thay đổi.

## 11. DEFAULT và ON UPDATE CURRENT_TIMESTAMP

DEFAULT CURRENT_TIMESTAMP và ON UPDATE CURRENT_TIMESTAMP là hai hành vi khác nhau.

- DEFAULT CURRENT_TIMESTAMP: cung cấp thời điểm ban đầu khi INSERT bỏ qua cột hoặc dùng DEFAULT.
- ON UPDATE CURRENT_TIMESTAMP: tự cập nhật thời điểm khi một cột khác trong hàng thay đổi theo điều kiện cập nhật của MySQL.

Ví dụ:

    CREATE TABLE audit_timestamp_demo (
        record_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        description VARCHAR(200) NOT NULL,
        created_at DATETIME(6) NOT NULL
            DEFAULT CURRENT_TIMESTAMP(6),
        updated_at DATETIME(6) NOT NULL
            DEFAULT CURRENT_TIMESTAMP(6)
            ON UPDATE CURRENT_TIMESTAMP(6),
        PRIMARY KEY (record_id)
    ) ENGINE = InnoDB;

INSERT:

    INSERT INTO audit_timestamp_demo (description)
    VALUES ('Tạo bản ghi');

created_at và updated_at được gán thời điểm hiện tại. Khi cập nhật description:

    UPDATE audit_timestamp_demo
    SET description = 'Đã chỉnh sửa'
    WHERE record_id = 1;

updated_at tự đổi theo thời điểm cập nhật; created_at giữ nguyên.

Nếu ứng dụng tự gán updated_at trong UPDATE, giá trị tường minh đó được dùng. Nếu cập nhật hàng mà không thay đổi giá trị thực tế của cột khác, quy tắc auto-update có thể không kích hoạt như trường hợp có thay đổi; hãy kiểm thử đúng câu lệnh của ứng dụng.

Không nhầm ON UPDATE CURRENT_TIMESTAMP với generated column. Nó là cơ chế tự cập nhật temporal column khi hàng thay đổi, không phải biểu thức tính từ các cột khác.

## 12. Dùng DEFAULT trong UPDATE

MySQL cho phép gán default của một cột trong UPDATE bằng từ khóa DEFAULT:

    UPDATE order_line_default_demo
    SET line_status = DEFAULT
    WHERE order_code = 'ORD-050';

line_status trở về giá trị mặc định đã khai báo, tức NEW.

Có thể dùng hàm DEFAULT(column_name) trong biểu thức để lấy giá trị mặc định của cột:

    SELECT DEFAULT(line_status)
    FROM order_line_default_demo
    LIMIT 1;

Điều này hữu ích khi cần tham chiếu default trong biểu thức SQL. Hãy nhớ rằng đổi định nghĩa default bằng ALTER TABLE không tự động sửa các hàng đã lưu; UPDATE ... SET column = DEFAULT mới áp dụng default hiện tại cho các hàng được cập nhật.

## 13. Thay đổi DEFAULT bằng ALTER TABLE

Có thể thay giá trị mặc định của cột mà không thay đổi giá trị các hàng hiện có:

    ALTER TABLE order_line_default_demo
        ALTER COLUMN line_status SET DEFAULT 'PENDING';

Từ thời điểm thay đổi có hiệu lực, các INSERT bỏ qua line_status hoặc chỉ định DEFAULT sẽ dùng PENDING.

Để bỏ default tường minh:

    ALTER TABLE order_line_default_demo
        ALTER COLUMN line_status DROP DEFAULT;

Nếu cột vẫn NOT NULL và không có default sau khi DROP DEFAULT, các INSERT bỏ qua cột sẽ cần cung cấp giá trị trong strict mode.

Thay đổi default không cập nhật ngược các hàng cũ. Ví dụ các hàng đã có line_status = NEW vẫn giữ NEW sau khi default đổi thành PENDING. Nếu cần chuẩn hóa dữ liệu lịch sử, phải chạy UPDATE riêng với điều kiện và kế hoạch phù hợp.

Trên bảng lớn, ALTER TABLE có thể tốn tài nguyên hoặc cần metadata lock. Hãy xem xét phiên bản MySQL, thuật toán DDL có thể áp dụng, thời gian khóa và kế hoạch triển khai trước khi thay đổi schema production.

## 14. INSERT IGNORE không phải cách thay thế DEFAULT

INSERT IGNORE có thể hạ một số lỗi thành warning và cho phép câu lệnh tiếp tục với dữ liệu đã được điều chỉnh hoặc hàng bị bỏ qua tùy loại lỗi. Điều này không đồng nghĩa với việc mọi cột thiếu giá trị đều được xử lý đúng nghiệp vụ.

Không dùng INSERT IGNORE chỉ để che lỗi thiếu cột bắt buộc. Nếu dữ liệu không hợp lệ, ứng dụng cần biết hàng nào bị từ chối hoặc giá trị nào bị điều chỉnh. Hãy dùng DEFAULT khi muốn default, truyền giá trị hợp lệ khi cột bắt buộc và xử lý lỗi duplicate theo chính sách riêng.

Sau INSERT IGNORE, nếu được dùng có chủ đích trong quy trình import, cần kiểm tra số hàng affected và SHOW WARNINGS. Không giả định tất cả hàng đầu vào đã được ghi thành công.

## 15. Kiểm tra kết quả và metadata

Để xác minh giá trị thực tế:

    SELECT
        line_id,
        order_code,
        quantity,
        unit_price,
        line_total,
        line_status,
        note,
        created_at,
        updated_at
    FROM order_line_default_demo
    ORDER BY line_id;

Để xem default và generated expression:

    SHOW CREATE TABLE order_line_default_demo;

Có thể truy vấn INFORMATION_SCHEMA:

    SELECT
        COLUMN_NAME,
        COLUMN_TYPE,
        IS_NULLABLE,
        COLUMN_DEFAULT,
        EXTRA,
        GENERATION_EXPRESSION
    FROM information_schema.columns
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'order_line_default_demo'
    ORDER BY ORDINAL_POSITION;

Các trường hữu ích:

| Trường | Ý nghĩa |
|---|---|
| COLUMN_NAME | Tên cột |
| COLUMN_TYPE | Kiểu dữ liệu đầy đủ |
| IS_NULLABLE | Cột có cho phép NULL hay không |
| COLUMN_DEFAULT | Giá trị mặc định được metadata hiển thị |
| EXTRA | Thuộc tính bổ sung như auto_increment hoặc generated |
| GENERATION_EXPRESSION | Biểu thức của generated column |

Metadata hiển thị default expression có thể khác cách hiển thị literal tùy phiên bản. Dùng SHOW CREATE TABLE để kiểm tra định nghĩa DDL đầy đủ và xác nhận bằng một INSERT thử nghiệm trong sandbox.

## 16. Những lỗi thường gặp

- Nghĩ bỏ qua cột tương đương với truyền NULL.
- Nghĩ truyền NULL vào cột NOT NULL sẽ tự kích hoạt DEFAULT.
- Bỏ qua cột NOT NULL không có DEFAULT rồi kỳ vọng MySQL tự chọn giá trị nghiệp vụ hợp lý.
- Tắt strict mode để che lỗi dữ liệu thiếu.
- Dùng implicit default như 0 hoặc chuỗi rỗng mà không xác định ý nghĩa.
- Dùng DEFAULT expression trên phiên bản MySQL cũ hơn 8.0.13.
- Viết biểu thức DEFAULT có tham chiếu đến cột khác trong cùng hàng.
- Nhầm DEFAULT với generated column.
- Cố gán giá trị tùy ý cho generated column.
- Nhầm VIRTUAL là không thể tạo index.
- Dùng AUTO_INCREMENT như số chứng từ liên tục không có khoảng trống.
- Dùng SELECT MAX(id) để lấy ID vừa insert thay cho LAST_INSERT_ID().
- Không hiểu ảnh hưởng của NO_AUTO_VALUE_ON_ZERO khi insert 0 vào AUTO_INCREMENT.
- Dùng INSERT không có danh sách cột khiến thứ tự giá trị phụ thuộc cấu trúc bảng.
- Nghĩ ALTER TABLE đổi DEFAULT sẽ cập nhật dữ liệu cũ.
- Nhầm DEFAULT CURRENT_TIMESTAMP với ON UPDATE CURRENT_TIMESTAMP.
- Dùng INSERT IGNORE để bỏ qua lỗi mà không kiểm tra warning và số hàng thực tế.

## 17. Checklist thiết kế và sử dụng INSERT

- Đã liệt kê rõ các cột ứng dụng cần cung cấp trong INSERT.
- Đã xác định cột nào có DEFAULT, AUTO_INCREMENT hoặc generated expression.
- Đã cung cấp giá trị cho mọi cột NOT NULL không có cơ chế sinh tự động.
- Đã phân biệt bỏ qua cột, DEFAULT và NULL.
- Đã kiểm tra SQL mode của môi trường triển khai, đặc biệt strict mode.
- Đã dùng DEFAULT literal hoặc expression phù hợp với phiên bản MySQL.
- Đã bảo đảm default expression không tham chiếu cột khác hoặc chứa thành phần bị cấm.
- Đã chọn VIRTUAL hay STORED theo workload và dung lượng.
- Đã không gửi giá trị tùy ý vào generated column.
- Đã dùng LAST_INSERT_ID() trên cùng connection nếu cần ID vừa cấp.
- Đã không dựa vào AUTO_INCREMENT để tạo dãy liên tục.
- Đã hiểu quy tắc ON UPDATE CURRENT_TIMESTAMP.
- Đã kiểm tra định nghĩa bằng SHOW CREATE TABLE và metadata INFORMATION_SCHEMA.
- Đã kiểm thử INSERT bỏ qua cột, dùng DEFAULT, truyền NULL và thiếu cột bắt buộc.
- Đã xem warning và số hàng affected khi dùng cơ chế import có thể bỏ qua lỗi.

Giá trị mặc định, AUTO_INCREMENT và generated column giúp MySQL tự cung cấp hoặc tính một phần dữ liệu khi INSERT. Muốn sử dụng an toàn, hãy phân biệt rõ cột bị bỏ qua với cột nhận NULL, thiết kế DEFAULT theo quy tắc nghiệp vụ, dùng AUTO_INCREMENT cho định danh thay vì số chứng từ liên tục, và dùng generated column cho giá trị phụ thuộc các cột cùng hàng. Danh sách cột tường minh trong INSERT, strict SQL mode và việc kiểm tra metadata sẽ giúp phát hiện sớm lỗi nhập dữ liệu và giữ schema dễ bảo trì.
